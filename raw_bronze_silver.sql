-- Create Schemas if they do not exist
CREATE SCHEMA IF NOT EXISTS raw;

CREATE SCHEMA IF NOT EXISTS bronze;

CREATE SCHEMA IF NOT EXISTS silver;

-- Create Raw Schema Tables
CREATE TABLE IF NOT EXISTS raw.dim_carriers (carrier_id TEXT, carrier_name TEXT);

CREATE TABLE IF NOT EXISTS raw.dim_warehouses (warehouse_id TEXT, region TEXT);

CREATE TABLE IF NOT EXISTS raw.fact_shipments (
  shipment_id TEXT,
  order_id TEXT,
  carrier_id TEXT,
  warehouse_id TEXT,
  ship_date TEXT,
  delivery_date TEXT,
  status TEXT,
  weight DOUBLE PRECISION
);

-- Create Bronze Schema Tables
CREATE TABLE IF NOT EXISTS bronze.dim_carriers (
  carrier_id VARCHAR PRIMARY KEY,
  carrier_name VARCHAR
);

CREATE TABLE IF NOT EXISTS bronze.dim_warehouses (warehouse_id VARCHAR PRIMARY KEY, region VARCHAR);

CREATE TABLE IF NOT EXISTS bronze.fact_shipments (
  shipment_id VARCHAR PRIMARY KEY,
  order_id VARCHAR,
  carrier_id VARCHAR,
  warehouse_id VARCHAR,
  ship_date VARCHAR,
  delivery_date VARCHAR,
  status VARCHAR,
  weight NUMERIC,
  copied_at TIMESTAMP
);

-- Create Silver Schema Tables
CREATE TABLE IF NOT EXISTS silver.dim_carriers (
  carrier_name VARCHAR PRIMARY KEY,
  copied_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS silver.dim_warehouses (
  warehouse_id VARCHAR PRIMARY KEY,
  region VARCHAR,
  copied_at TIMESTAMP
);

-- Create custom date cast function in Silver schema if not exists
CREATE TABLE IF NOT EXISTS silver.fact_shipments (
  shipment_id VARCHAR PRIMARY KEY,
  order_id VARCHAR,
  carrier_name VARCHAR REFERENCES silver.dim_carriers (carrier_name),
  warehouse_id VARCHAR,
  ship_date DATE,
  delivery_date DATE,
  status VARCHAR,
  weight NUMERIC,
  copied_at TIMESTAMP
);

CREATE OR REPLACE FUNCTION silver.safe_cast_date (val text) RETURNS DATE LANGUAGE IMMUTABLE plpgsql AS $$
BEGIN
    RETURN val::date;
EXCEPTION WHEN others THEN
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION silver.normalise_carrier (name TEXT) RETURNS TEXT LANGUAGE IMMUTABLE plpgsql AS $$
BEGIN
  RETURN CASE
    WHEN name ILIKE '%dhl%'THEN 'DHL'
    WHEN name ILIKE '%fed%' THEN 'FedEx'
    WHEN name ILIKE '%ups%' THEN 'UPS'
    WHEN name ILIKE '%usps%' THEN 'USPS'
    WHEN name ILIKE '%amazon%' THEN 'Amazon'
    WHEN name ILIKE '%maersk%' THEN 'Maersk'
    WHEN name ILIKE '%robinson%' THEN 'C.H. Robinson'
    WHEN name ILIKE '%xpo%' THEN 'XPO Logistics'
    WHEN name ILIKE '%hunt%' THEN 'J.B. Hunt'
    WHEN name ILIKE '%kintetsu%' THEN 'Kintetsu World Express'
    WHEN name ILIKE '%nippon%' THEN 'Nippon Express'
    WHEN name ILIKE '%schenker%' THEN 'DB Schenker'
    WHEN name ILIKE '%schneider%' THEN 'Schneider National'
    WHEN name ILIKE '%swift%' THEN 'Knight-Swift'
    WHEN name ILIKE '%landstar%' THEN 'Landstar'
    WHEN name ILIKE '%werner%' THEN 'Werner Enterprises'
    WHEN name ILIKE '%old%' THEN 'Old Dominion'
    WHEN name ILIKE '%estes%' THEN 'Estes Express'
    WHEN name ILIKE '%yrc%' THEN 'YRC Freight'
    WHEN name ILIKE '%dpd%' THEN 'DPD'
    WHEN name ILIKE '%royal%' THEN 'Royal Mail'
    WHEN name ILIKE '%canada%' THEN 'Canada Post'
    WHEN name ILIKE '%australia%' THEN 'Australia Post'
    WHEN name ILIKE '%japan%' THEN 'Japan Post'
    WHEN name ILIKE '%poste%' THEN 'La Poste'
    ELSE name
  END;
END;
$$;

--append to bronze tables from raw tables
INSERT INTO
  bronze.dim_carriers (carrier_id, carrier_name)
SELECT
  carrier_id,
  carrier_name
FROM
  raw.dim_carriers
ON CONFLICT (carrier_id) DO
UPDATE
SET
  carrier_name = EXCLUDED.carrier_name;

INSERT INTO
  bronze.dim_warehouses (warehouse_id, region)
SELECT
  warehouse_id,
  region
FROM
  raw.dim_warehouses
ON CONFLICT (warehouse_id) DO NOTHING;

INSERT INTO
  bronze.fact_shipments (
    shipment_id,
    order_id,
    carrier_id,
    warehouse_id,
    ship_date,
    delivery_date,
    status,
    weight,
    copied_at
  )
SELECT DISTINCT
  ON (shipment_id) shipment_id,
  order_id,
  carrier_id,
  warehouse_id,
  ship_date,
  delivery_date,
  status,
  weight,
  NOW()
FROM
  raw.fact_shipments
ORDER BY
  shipment_id,
  9 DESC
  --if there is an update to the status of the order, the following will update the existing record 
ON CONFLICT (shipment_id) DO
UPDATE
SET
  order_id = EXCLUDED.order_id,
  carrier_id = EXCLUDED.carrier_id,
  warehouse_id = EXCLUDED.warehouse_id,
  ship_date = EXCLUDED.ship_date,
  delivery_date = EXCLUDED.delivery_date,
  status = EXCLUDED.status,
  weight = EXCLUDED.weight,
  copied_at = NOW();

--cleaning bronze data and copying to silver layer 
INSERT INTO
  silver.dim_carriers (carrier_name, copied_at)
SELECT DISTINCT
  silver.normalise_carrier (carrier_name) AS carrier_name,
  NOW() AS copied_at
FROM
  bronze.dim_carriers
ON CONFLICT (carrier_name) DO NOTHING;

INSERT INTO
  silver.dim_warehouses (warehouse_id, region, copied_at)
SELECT DISTINCT
  warehouse_id,
  region,
  NOW() AS copied_at
FROM
  bronze.dim_warehouses
ON CONFLICT (warehouse_id) DO
UPDATE
SET
  region = EXCLUDED.region
WHERE
  silver.dim_warehouses.region IS NULL;

INSERT INTO
  silver.fact_shipments (
    shipment_id,
    order_id,
    carrier_name,
    warehouse_id,
    ship_date,
    delivery_date,
    status,
    weight,
    copied_at
  )
WITH
  parsed AS (
    SELECT
      f.shipment_id,
      f.order_id,
      silver.normalise_carrier (bc.carrier_name) AS carrier_name,
      f.warehouse_id,
      silver.safe_cast_date (f.ship_date) AS ship_date,
      silver.safe_cast_date (f.delivery_date) AS delivery_date,
      f.status,
      f.weight
    FROM
      bronze.fact_shipments f
      LEFT JOIN bronze.dim_carriers bc ON f.carrier_id = bc.carrier_id
  ),
  cleaned_data AS (
    SELECT
      shipment_id,
      order_id,
      carrier_name,
      warehouse_id,
      ship_date,
      CASE
        WHEN delivery_date IS NOT NULL
        AND ship_date IS NOT NULL
        AND delivery_date < ship_date THEN (ship_date + INTERVAL '2 days')::DATE
        ELSE delivery_date
      END AS delivery_date,
      CASE
        WHEN status ILIKE 'D%'
        OR status ILIKE 'del' THEN 'Delivered'
        WHEN status ILIKE 'p%'
        OR status ILIKE 'In%' THEN 'Pending'
        WHEN status ILIKE 'fail' THEN 'Failed'
        ELSE 'NA'
      END AS status,
      CASE
        WHEN weight <= 0 THEN NULL
        ELSE weight
      END AS weight,
      NOW() AS copied_at
    FROM
      parsed
  )
SELECT
  *
FROM
  cleaned_data
ON CONFLICT (shipment_id) DO
UPDATE
SET
  order_id = EXCLUDED.order_id,
  carrier_name = EXCLUDED.carrier_name,
  warehouse_id = EXCLUDED.warehouse_id,
  ship_date = EXCLUDED.ship_date,
  delivery_date = EXCLUDED.delivery_date,
  status = EXCLUDED.status,
  weight = EXCLUDED.weight,
  copied_at = EXCLUDED.copied_at;