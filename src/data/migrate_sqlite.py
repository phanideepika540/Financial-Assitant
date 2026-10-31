from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from src.data.database import migrate_sqlite_to_database

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(
        description="Copy existing SQLite accounts, profiles, and messages to DATABASE_URL."
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("data/finance_assistant.sqlite3"),
        help="Path to the existing SQLite database.",
    )
    args = parser.parse_args()
    destination_url = os.getenv("DATABASE_URL")
    if not destination_url:
        parser.error("Set DATABASE_URL to the destination PostgreSQL connection URL.")

    migrate_sqlite_to_database(args.source, destination_url)
    print(f"Migrated data from {args.source} to the configured database.")


if __name__ == "__main__":
    main()
