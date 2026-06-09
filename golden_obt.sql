LOAD postgres;

ATTACH 'dbname=logistics_db user=postgres password=saurav7kush host=/tmp port=5432' AS pg (TYPE postgres);

INSERT OR REPLACE INTO
    golden.obt_shipments (
        shipment_id,
        order_id,
        carrier_id,
        warehouse_id,
        ship_date,
        delivery_date,
        status,
        weight,
        carrier_name,
        region,
        copied_at
    )
WITH
    obt_cte AS (
        SELECT
            f.shipment_id AS shipment_id,
        f.order_id AS order_id,
        f.carrier_id AS carrier_id,
        f.warehouse_id AS warehouse_id,
        f.ship_date AS ship_date,
        f.delivery_date AS delivery_date,
        f.status AS status,
        f.weight AS weight,
        c.carrier_name AS carrier_name,
        w.region AS region,
        f.copied_at AS copied_at
        FROM
            pg.silver.fact_shipments f
            LEFT JOIN pg.silver.dim_carriers c ON f.carrier_id = c.carrier_id
            LEFT JOIN pg.silver.dim_warehouses w ON f.warehouse_id = w.warehouse_id
        WHERE
            f.copied_at > (
                SELECT
                    COALESCE(MAX(copied_at), '1970-01-01'::TIMESTAMP)
                FROM
                    golden.obt_shipments
            )
    )
SELECT
    *
FROM
    obt_cte;