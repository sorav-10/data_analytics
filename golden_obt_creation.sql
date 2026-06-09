-- 1. Install, load, and attach the PostgreSQL database
INSTALL postgres;

LOAD postgres;

ATTACH 'dbname=logistics_db user=postgres password=saurav7kush host=/tmp port=5432' AS pg (TYPE postgres);

-- 2. Create the golden schema and build the OBT table
CREATE SCHEMA IF NOT EXISTS golden;

CREATE OR REPLACE TABLE golden.obt_shipments AS
SELECT
    f.* EXCLUDE (copied_at),
    c.* EXCLUDE (carrier_id, copied_at),
    w.* EXCLUDE (warehouse_id, copied_at),
    NOW() AS copied_at
FROM
    pg.silver.fact_shipments f
    LEFT JOIN pg.silver.dim_carriers c ON f.carrier_id = c.carrier_id
    LEFT JOIN pg.silver.dim_warehouses w ON f.warehouse_id = w.warehouse_id;