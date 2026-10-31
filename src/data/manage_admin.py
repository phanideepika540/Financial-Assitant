from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.config import Settings
from src.data.database import AccountError, Database


def main() -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(
        description="Grant the admin role to an existing Finance Assistant account."
    )
    parser.add_argument("username", help="Username of the existing account to promote")
    args = parser.parse_args()

    database = Database(Settings.load(ROOT / "config.yaml").database_url)
    try:
        database.promote_user(args.username)
    except AccountError as exc:
        parser.error(str(exc))
    finally:
        database.dispose()

    print(f"Granted admin role to '{args.username}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
