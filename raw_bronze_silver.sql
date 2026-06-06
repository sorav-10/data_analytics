--append to bronze tables from raw tables
INSERT INTO bronze.dim_carriers (carrier_id, carrier_name) 
SELECT carrier_id, carrier_name FROM raw.dim_carriers
ON CONFLICT (carrier_id) DO UPDATE
  SET carrier_name = EXCLUDED.carrier_name;

INSERT INTO bronze.dim_warehouses (warehouse_id, region) 
SELECT warehouse_id, region FROM raw.dim_warehouses
ON CONFLICT (warehouse_id) DO NOTHING;

INSERT INTO bronze.fact_shipments (shipment_id, order_id, carrier_id, warehouse_id, ship_date, delivery_date, status, weight, copied_at) 
SELECT DISTINCT ON (shipment_id) shipment_id, order_id, carrier_id, warehouse_id, ship_date, delivery_date, status, weight, NOW() FROM raw.fact_shipments
ORDER BY shipment_id, 9 DESC
--if there is an update to the status of the order, the following will update the existing record 
ON CONFLICT (shipment_id) DO UPDATE SET
  order_id = EXCLUDED.order_id,
  carrier_id = EXCLUDED.carrier_id,
  warehouse_id = EXCLUDED.warehouse_id,
  ship_date = EXCLUDED.ship_date,
  delivery_date = EXCLUDED.delivery_date,
  status = EXCLUDED.status,
  weight = EXCLUDED.weight,
  copied_at = NOW();

--cleaning bronze data and copying to silver layer 

INSERT INTO silver.dim_carriers (carrier_id, carrier_name, copied_at)
SELECT DISTINCT
    carrier_id,
    CONCAT('Carrier-Group-', CAST(SUBSTRING(carrier_id FROM 4) AS INTEGER)) AS carrier_name,
    NOW() AS copied_at
FROM   bronze.dim_carriers
ON CONFLICT (carrier_id) DO UPDATE
  SET carrier_name = EXCLUDED.carrier_name
  WHERE silver.dim_carriers.carrier_name IS NULL;


INSERT INTO silver.dim_warehouses (warehouse_id, region, copied_at)
SELECT DISTINCT
    warehouse_id,
    region,
    NOW() AS copied_at
FROM bronze.dim_warehouses
ON CONFLICT (warehouse_id) DO UPDATE 
  SET region = EXCLUDED.region 
  WHERE silver.dim_warehouses.region IS NULL;


INSERT INTO silver.fact_shipments (
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
WITH parsed_date AS(
  SELECT
    shipment_id,
    order_id,
    carrier_id,
    warehouse_id,
    silver.safe_cast_date(ship_date) AS ship_date, 
    silver.safe_cast_date(delivery_date) AS delivery_date, 
    status,
    weight
  FROM bronze.fact_shipments 
),
cleaned_data AS (
  SELECT
    shipment_id,
    order_id,
    carrier_id,
    warehouse_id,
    ship_date,
    CASE
      WHEN delivery_date IS NOT NULL 
        AND ship_date IS NOT NULL 
        AND delivery_date < ship_date 
      THEN (ship_date + INTERVAL '2 days')::DATE
      ELSE delivery_date
    END AS delivery_date,
    CASE
      WHEN status LIKE 'D%' THEN 'Delivered'
      WHEN status LIKE 'P%' OR status ILIKE 'In%' THEN 'Pending'
      WHEN status ILIKE 'fail' THEN 'Failed'
    END AS status,
    CASE
      WHEN weight <= 0 THEN NULL
      ELSE weight
    END AS weight,
    NOW()
  FROM parsed_date
)
SELECT *
FROM cleaned_data
ON CONFLICT (shipment_id) DO UPDATE SET
  order_id = EXCLUDED.order_id,
  carrier_id = EXCLUDED.carrier_id,
  warehouse_id = EXCLUDED.warehouse_id,
  ship_date = EXCLUDED.ship_date,
  delivery_date = EXCLUDED.delivery_date,
  status = EXCLUDED.status,
  weight = EXCLUDED.weight,
  copied_at = NOW();
