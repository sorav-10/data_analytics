import os
import subprocess
import psycopg2
import duckdb
from dotenv import load_dotenv
from datetime import datetime

def run_pipeline():
    # 1. Run data_gen.py
    print("Step 1: Running data_gen.py...")
    # Using the python executable in the virtual environment to ensure dependencies are loaded
    result_gen = subprocess.run([".venv/bin/python3", "data_gen.py"], capture_output=True, text=True)
    if result_gen.returncode != 0:
        print("Error running data_gen.py:")
        print(result_gen.stderr)
        return False

    # Load environment variables for PostgreSQL
    load_dotenv(override=True)
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASS = os.getenv("DB_PASS")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "logistics_db")

    # 2. Run raw_bronze_silver.sql in PostgreSQL
    if not os.path.exists("raw_bronze_silver.sql"):
        print("Error: raw_bronze_silver.sql not found.")
        return False

    with open("raw_bronze_silver.sql", "r") as f:
        postgres_sql = f.read()

    try:
        conn = psycopg2.connect(
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            host=DB_HOST,
            port=DB_PORT
        )
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(postgres_sql)
        conn.close()
    except Exception as e:
        print("Error executing PostgreSQL queries:")
        print(e)
        return False

    # 3. Run golden_obt.sql in DuckDB
    if not os.path.exists("golden_obt.sql"):
        print("Error: golden_obt.sql not found.")
        return False

    with open("golden_obt.sql", "r") as f:
        duckdb_sql = f.read()

    try:
        con = duckdb.connect("logistics_analysis.db")
        con.execute(duckdb_sql)
        con.close()
    except Exception as e:
        print("Error executing DuckDB queries:")
        print(e)
        return False

    print(f"Data pipeline executed successfully at: {datetime.now()}")
    return True

if __name__ == "__main__":
    run_pipeline()
