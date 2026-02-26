"""
Migrate SQLite data to PostgreSQL (Neon).
Run with: DATABASE_URL=... python migrate_to_postgres.py

Options:
  --truncate    Truncate all tables in PostgreSQL before migrating (recommended
                if target already has data from init_db or previous runs)

Handles schema differences by only inserting columns that exist in the target
PostgreSQL schema (e.g. when SQLite has older/different columns).
"""
import argparse
import os
import sys
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from app.database.models import Base
from app.config import load_config

# Chunk size for bulk inserts (avoids psycopg2 parameter limit with large tables)
CHUNK_SIZE = 100

TABLES = [
    "users",
    "weekly_summary",
    "cycle_data",
    "embodied_infrastructure",
    "embodied_sorbent",
    "system_config",
    "audit_log",
]


def get_pg_columns(engine, table: str) -> set:
    """Get column names that exist in the target PostgreSQL table."""
    inspector = inspect(engine)
    return {c["name"] for c in inspector.get_columns(table)}


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite data to PostgreSQL (Neon)")
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Truncate all tables in PostgreSQL before migrating (use when target has existing data)",
    )
    args = parser.parse_args()

    # 1. SQLite source
    config = load_config()
    db_path = config.db_path
    if not db_path.exists():
        print(f"ERROR: SQLite database not found at {db_path}")
        sys.exit(1)

    sqlite_url = f"sqlite:///{db_path}"
    sqlite_engine = create_engine(sqlite_url)

    # 2. PostgreSQL destination
    pg_url = os.getenv("DATABASE_URL")
    if not pg_url:
        print("ERROR: Set DATABASE_URL to your Neon connection string")
        print("Example: set DATABASE_URL=postgresql://user:pass@host/neondb?sslmode=require")
        sys.exit(1)

    if pg_url.startswith("postgres://"):
        pg_url = pg_url.replace("postgres://", "postgresql://", 1)

    pg_engine = create_engine(pg_url)

    # 3. Create tables in PostgreSQL (if they don't exist)
    print("Creating tables in PostgreSQL...")
    Base.metadata.create_all(bind=pg_engine)

    # 3b. Truncate if requested (ensures clean slate, avoids duplicate key errors)
    if args.truncate:
        print("Truncating existing data in PostgreSQL...")
        with pg_engine.connect() as conn:
            conn.execute(text("TRUNCATE users, weekly_summary, cycle_data, embodied_infrastructure, embodied_sorbent, system_config, audit_log CASCADE"))
            conn.commit()
        print("  Done.")

    # 4. Migrate data (order respects foreign keys)
    for table in TABLES:
        try:
            df = pd.read_sql_table(table, sqlite_engine)
            if len(df) == 0:
                print(f"  {table}: 0 rows (skipped)")
                continue

            # Only keep columns that exist in the target PostgreSQL schema
            # (handles schema drift: SQLite may have older/different columns)
            pg_cols = get_pg_columns(pg_engine, table)
            cols_to_use = [c for c in df.columns if c in pg_cols]
            dropped = set(df.columns) - set(cols_to_use)
            if dropped:
                print(f"  {table}: dropping columns not in target: {sorted(dropped)}")
            df_trimmed = df[cols_to_use]

            df_trimmed.to_sql(
                table,
                pg_engine,
                if_exists="append",
                index=False,
                method="multi",
                chunksize=CHUNK_SIZE,
            )
            print(f"  {table}: {len(df_trimmed)} rows migrated")
        except Exception as e:
            print(f"  {table}: ERROR - {e}")

    # 5. Reset sequences so new inserts get correct IDs
    print("\nResetting PostgreSQL sequences...")
    for table in ["users", "weekly_summary", "cycle_data", "embodied_infrastructure", "embodied_sorbent", "audit_log"]:
        try:
            with pg_engine.connect() as conn:
                conn.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 1))"
                    )
                )
                conn.commit()
            print(f"  {table}.id sequence reset")
        except Exception as e:
            print(f"  {table}: {e}")

    print("\nMigration complete.")


if __name__ == "__main__":
    main()