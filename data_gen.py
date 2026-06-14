import json
import uuid
import random
import os
import pandas as pd
from datetime import datetime, timedelta
from google import genai
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load database configuration from .env file
load_dotenv(override=True)

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "logistics_db")

if not DB_PASS:
    raise ValueError("Database password (DB_PASS) must be configured in the .env file")

# CREATE DATABASE IF NOT EXISTS
if "/" in DB_HOST or DB_HOST.startswith("."):
    db_url_base = f"postgresql://{DB_USER}:{DB_PASS}@/postgres?host={DB_HOST}&port={DB_PORT}"
    db_url_target = f"postgresql://{DB_USER}:{DB_PASS}@/{DB_NAME}?host={DB_HOST}&port={DB_PORT}"
else:
    db_url_base = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/postgres"
    db_url_target = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

base_engine = create_engine(db_url_base)
with base_engine.connect() as conn:
    conn.execute(text("END"))
    
    # Refresh collation versions to handle glibc upgrades (e.g., glibc 2.42 to 2.43)
    try:
        conn.execute(text("ALTER DATABASE postgres REFRESH COLLATION VERSION"))
        conn.execute(text("ALTER DATABASE template1 REFRESH COLLATION VERSION"))
    except Exception as e:
        # Ignore if permissions or connection settings prevent alteration
        pass

    check_db = conn.execute(text(f"SELECT 1 FROM pg_database WHERE datname='{DB_NAME}'")).fetchone()
    if not check_db:
        conn.execute(text(f"CREATE DATABASE {DB_NAME}"))
base_engine.dispose()

# TARGET DATABASE ENGINE
engine = create_engine(db_url_target)

# GEMINI LIVE TOKEN GENERATION (MOCKED LOCAL TO AVOID NETWORK CALLS)
seeds = {
    "carriers": [
        "FedEX Corp!!", "DHL_ERR", "UPS_Deliv_Fail", "U.S. Postal Service?", 
        "AmazonLogistics##", "Maersk Line Inc...", "C.H. Robinson!!!", 
        "XPO Logistics__", "J.B. Hunt Tran*", "Fedex Express - ERR",
        "DHL Express??", "USPS_MESS", "Kintetsu World Express$$",
        "Nippon Express!!", "DB Schenker - BAD"
    ],
    "statuses": ["DELIV@RED", "NULL_VAL", "PNDG_ERR", "UNKNOWN_STATUS", "IN_TRANSIT_ERROR"],
    "dates": ["2026/02/31", "04-06-202X", "2026-13-01", "0000-00-00", "2026-02-30"]
}
bad_carriers = seeds["carriers"]
bad_statuses = seeds["statuses"]
bad_dates = seeds["dates"]

# CONFIGURATION
total_records = random.randint(10, 100)
today_date = datetime.now()

# 1. DIM_CARRIERS DATA
carrier_ids = [f"CR-{i:03d}" for i in range(1, 51)]
clean_carrier_bases = [
    "FedEx", "DHL", "UPS", "USPS", "Amazon Logistics", 
    "Maersk", "C.H. Robinson", "XPO Logistics", "J.B. Hunt", 
    "Kintetsu World Express", "Nippon Express", "DB Schenker", 
    "Schneider National", "Knight-Swift", "Landstar", "Werner Enterprises", 
    "Old Dominion", "Estes Express", "YRC Freight", "DPD", 
    "Royal Mail", "Canada Post", "Australia Post", "Japan Post", "La Poste"
]
clean_carriers = []
suffixes = ["Express", "Logistics", "Freight", "Global", "Ground", "Air", "Solutions", "Services"]
for i in range(50):
    base = clean_carrier_bases[i % len(clean_carrier_bases)]
    suffix = suffixes[i // len(clean_carrier_bases)]
    clean_carriers.append(f"{base} {suffix}")

df_carriers = pd.DataFrame({"carrier_id": carrier_ids, "carrier_name": clean_carriers})

# Set exactly 10% (5 out of 50) of the carriers as error names
for idx in random.sample(range(len(df_carriers)), 5):
    df_carriers.iloc[idx, 1] = random.choice(bad_carriers)

# 2. DIM_WAREHOUSES DATA
warehouse_ids = [f"WH-{i:02d}" for i in range(1, 11)]
regions = ["North", "South", "East", "West", "Central"] * 2
df_warehouses = pd.DataFrame({"warehouse_id": warehouse_ids, "region": regions})

# 3. FACT_SHIPMENTS DATA
fact_data = []
for i in range(total_records):
    shipment_id = f"SHP-{uuid.uuid4().hex[:8].upper()}"
    order_id = f"ORD-{int(today_date.timestamp()) + i}"
    carrier_id = random.choice(carrier_ids)
    warehouse_id = random.choice(warehouse_ids)
    
    days_to_deliver = random.choice([1, 2, 3, 4, -2]) 
    ship_dt = today_date - timedelta(days=random.randint(0, 2))
    delivery_dt = ship_dt + timedelta(days=days_to_deliver)
    
    ship_str = ship_dt.strftime("%Y-%m-%d")
    delivery_str = delivery_dt.strftime("%Y-%m-%d")
    status = "DELIVERED" if days_to_deliver > 0 else "PENDING"
    weight = round(random.uniform(5.0, 500.0), 2)
    
    if random.random() < 0.02:
        status = random.choice(bad_statuses)
    if random.random() < 0.01:
        ship_str = random.choice(bad_dates)
    if random.random() < 0.01:
        delivery_str = None
    if random.random() < 0.01:
        weight = -99.0     
        
    fact_data.append([
        shipment_id, order_id, carrier_id, warehouse_id, 
        ship_str, delivery_str, status, weight
    ])

df_shipments = pd.DataFrame(fact_data, columns=[
    "shipment_id", "order_id", "carrier_id", "warehouse_id",
    "ship_date", "delivery_date", "status", "weight"
])

# PREVENT DUPLICATES FOR DIMENSION TABLES
try:
    existing_carriers = pd.read_sql("SELECT carrier_id FROM raw.dim_carriers", engine)["carrier_id"].tolist()
except Exception:
    existing_carriers = []

try:
    existing_warehouses = pd.read_sql("SELECT warehouse_id FROM raw.dim_warehouses", engine)["warehouse_id"].tolist()
except Exception:
    existing_warehouses = []

df_carriers_new = df_carriers[~df_carriers["carrier_id"].isin(existing_carriers)]
df_warehouses_new = df_warehouses[~df_warehouses["warehouse_id"].isin(existing_warehouses)]

# WRITE TO DATABASE
df_carriers_new.to_sql("dim_carriers", engine, schema="raw", if_exists="append", index=False)
df_warehouses_new.to_sql("dim_warehouses", engine, schema="raw", if_exists="append", index=False)
df_shipments.to_sql("fact_shipments", engine, schema="raw", if_exists="append", index=False)

engine.dispose()