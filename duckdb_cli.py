import os
import sys
import duckdb
from dotenv import load_dotenv

def main():
    # Load database configuration
    load_dotenv(override=True)

    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASS = os.getenv("DB_PASS")
    DB_HOST = os.getenv("DB_HOST", "/tmp")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "logistics_db")

    # Connect to a local DuckDB file database
    con = duckdb.connect("logistics_analysis.db")

    # Set extension directory to writeable /tmp space since /home is read-only
    con.execute("SET extension_directory = '/tmp/duckdb_extensions';")

    try:
        con.execute("INSTALL postgres;")
        con.execute("LOAD postgres;")
    except Exception as e:
        print(f"Error: Failed to load postgres extension: {e}")
        sys.exit(1)

    conn_str = f"dbname={DB_NAME} user={DB_USER} password={DB_PASS} host={DB_HOST} port={DB_PORT}"

    try:
        con.execute(f"ATTACH '{conn_str}' AS pg (TYPE postgres);")
    except Exception as e:
        print(f"Error: Failed to attach database: {e}")
        sys.exit(1)

    # Parse arguments to decide mode
    mode = "cli"
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("--init", "--check", "-i"):
            mode = "init"
        elif arg in ("--test", "-t"):
            mode = "test"

    if mode == "init":
        print(f"DuckDB: Connected and attached PostgreSQL database '{DB_NAME}' as 'pg'.")
        con.close()
        return

    if mode == "test":
        print("\n--- Schema Inspection ---")
        schemas = ["raw", "bronze", "silver"]
        for schema in schemas:
            print(f"\nSchema: {schema}")
            try:
                tables_query = f"""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = '{schema}'
                """
                tables = con.execute(tables_query).fetchall()
                if not tables:
                    print("  No tables found.")
                for t in tables:
                    t_name = t[0]
                    count = con.execute(f"SELECT COUNT(*) FROM pg.{schema}.{t_name}").fetchone()[0]
                    print(f"  - Table: {t_name} ({count} rows)")
            except Exception as e:
                print(f"  Error loading schema: {e}")

        print("\n--- Sample Query (Top 5 rows from pg.raw.dim_carriers) ---")
        try:
            df = con.execute("SELECT * FROM pg.raw.dim_carriers LIMIT 5;").df()
            print(df)
        except Exception as e:
            print(f"Error querying table: {e}")
        con.close()
        return

    # Default: Interactive CLI
    print(f"DuckDB CLI: Connected to PostgreSQL '{DB_NAME}' (attached as 'pg').")
    print("Type 'exit' or 'quit' to close.")

    while True:
        try:
            query = input("duckdb> ").strip()
            if not query:
                continue
            if query.lower() in ["exit", "quit", "exit;", "quit;"]:
                break
            
            # Run query and display results
            res = con.execute(query)
            if res.description is not None:
                df = res.df()
                print(df.to_string(index=False))
            else:
                print("Query executed successfully.")
        except KeyboardInterrupt:
            print("\nUse 'exit' or 'quit' to close.")
        except Exception as e:
            print(f"Error: {e}")

    con.close()
    print("DuckDB CLI session closed.")

if __name__ == "__main__":
    main()
