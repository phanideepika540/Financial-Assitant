from __future__ import annotations

import hashlib
import hmac
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
    inspect,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.exc import IntegrityError


_ITERATIONS = 310_000
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
_METADATA = MetaData()

_USERS = Table(
    "users",
    _METADATA,
    Column("id", Integer, primary_key=True),
    Column("username", String(32), nullable=False),
    Column("password_hash", String(256), nullable=False),
    Column("role", String(16), nullable=False, server_default="user"),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
)
Index("uq_users_username_lower", func.lower(_USERS.c.username), unique=True)

_PROFILES = Table(
    "profiles",
    _METADATA,
    Column(
        "user_id",
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("learning_level", String(32), nullable=False, server_default="Beginner"),
    Column("goal", String(300), nullable=False, server_default=""),
    Column("time_horizon", String(120), nullable=False, server_default=""),
    Column("risk_comfort", String(32), nullable=False, server_default=""),
)

_MESSAGES = Table(
    "messages",
    _METADATA,
    Column("id", Integer, primary_key=True),
    Column(
        "user_id",
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("role", String(16), nullable=False),
    Column("content", Text, nullable=False),
    Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
)
Index("idx_messages_user_id_id", _MESSAGES.c.user_id, _MESSAGES.c.id)

_PORTFOLIO_HOLDINGS = Table(
    "portfolio_holdings",
    _METADATA,
    Column("id", Integer, primary_key=True),
    Column(
        "user_id",
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("name", String(80), nullable=False),
    Column("asset_class", String(32), nullable=False),
    Column("sector", String(40), nullable=False),
    Column("market_value", Float, nullable=False),
)
Index("idx_portfolio_holdings_user_id_id", _PORTFOLIO_HOLDINGS.c.user_id, _PORTFOLIO_HOLDINGS.c.id)


class AccountError(ValueError):
    """Raised for invalid account operations."""


def _database_url(value: str | Path | URL) -> URL:
    if isinstance(value, URL):
        return value
    raw = str(value)
    if "://" not in raw:
        path = Path(raw).resolve()
        return URL.create("sqlite", database=str(path))
    if raw.startswith("postgres://"):
        raw = "postgresql+psycopg://" + raw.removeprefix("postgres://")
    elif raw.startswith("postgresql://"):
        raw = raw.replace("postgresql://", "postgresql+psycopg://", 1)
    return make_url(raw)


class Database:
    def __init__(self, path_or_url: str | Path | URL):
        url = _database_url(path_or_url)
        if url.get_backend_name() == "sqlite" and url.database not in (None, "", ":memory:"):
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        connect_args = (
            {"timeout": 10, "check_same_thread": False}
            if url.get_backend_name() == "sqlite"
            else {}
        )
        self.engine: Engine = create_engine(
            url,
            connect_args=connect_args,
            pool_pre_ping=True,
        )
        self.initialize()

    def initialize(self) -> None:
        _METADATA.create_all(self.engine)
        if self.engine.dialect.name == "postgresql":
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                        "role VARCHAR(16) NOT NULL DEFAULT 'user'"
                    )
                )
        elif "role" not in {
            column["name"] for column in inspect(self.engine).get_columns("users")
        }:
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN role "
                        "VARCHAR(16) NOT NULL DEFAULT 'user'"
                    )
                )

    def register(self, username: str, password: str) -> int:
        username = username.strip()
        if not _USERNAME_RE.fullmatch(username):
            raise AccountError("Username must be 3-32 characters: letters, numbers, '.', '_' or '-'.")
        if len(password) < 12:
            raise AccountError("Password must contain at least 12 characters.")
        password_hash = _hash_password(password)
        try:
            with self.engine.begin() as connection:
                result = connection.execute(
                    insert(_USERS)
                    .values(username=username, password_hash=password_hash)
                    .returning(_USERS.c.id)
                )
                user_id = int(result.scalar_one())
                connection.execute(insert(_PROFILES).values(user_id=user_id))
                return user_id
        except IntegrityError as exc:
            raise AccountError("That username is already registered.") from exc

    def authenticate(self, username: str, password: str) -> int | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(_USERS.c.id, _USERS.c.password_hash).where(
                    func.lower(_USERS.c.username) == username.strip().lower()
                )
            ).mappings().one_or_none()
        if row is None:
            return None
        return int(row["id"]) if _verify_password(password, row["password_hash"]) else None

    def get_username(self, user_id: int) -> str:
        with self.engine.connect() as connection:
            username = connection.execute(
                select(_USERS.c.username).where(_USERS.c.id == user_id)
            ).scalar_one_or_none()
        if username is None:
            raise AccountError("Account no longer exists.")
        return str(username)

    def get_role(self, user_id: int) -> str:
        with self.engine.connect() as connection:
            role = connection.execute(
                select(_USERS.c.role).where(_USERS.c.id == user_id)
            ).scalar_one_or_none()
        if role is None:
            raise AccountError("Account no longer exists.")
        return str(role)

    def promote_user(self, username: str) -> None:
        with self.engine.begin() as connection:
            result = connection.execute(
                update(_USERS)
                .where(func.lower(_USERS.c.username) == username.strip().lower())
                .values(role="admin")
            )
        if result.rowcount != 1:
            raise AccountError(f"No account exists for username '{username}'.")

    def list_user_profiles(self) -> list[dict[str, str]]:
        statement = (
            select(
                _USERS.c.username,
                _USERS.c.role,
                _PROFILES.c.learning_level,
                _PROFILES.c.goal,
                _PROFILES.c.time_horizon,
                _PROFILES.c.risk_comfort,
            )
            .join(_PROFILES, _PROFILES.c.user_id == _USERS.c.id)
            .order_by(func.lower(_USERS.c.username))
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]

    def get_profile(self, user_id: int) -> dict[str, str]:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(
                    _PROFILES.c.learning_level,
                    _PROFILES.c.goal,
                    _PROFILES.c.time_horizon,
                    _PROFILES.c.risk_comfort,
                ).where(_PROFILES.c.user_id == user_id)
            ).mappings().one_or_none()
        if row is None:
            raise AccountError("Account profile was not found.")
        return dict(row)

    def save_profile(self, user_id: int, profile: dict[str, str]) -> None:
        fields = ("learning_level", "goal", "time_horizon", "risk_comfort")
        values = {field: profile[field].strip() for field in fields}
        with self.engine.begin() as connection:
            result = connection.execute(
                update(_PROFILES).where(_PROFILES.c.user_id == user_id).values(**values)
            )
            if result.rowcount != 1:
                raise AccountError("Account profile was not found.")

    def save_message(self, user_id: int, role: str, content: str) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("role must be 'user' or 'assistant'")
        if not content.strip():
            raise ValueError("message content cannot be empty")
        with self.engine.begin() as connection:
            connection.execute(
                insert(_MESSAGES).values(
                    user_id=user_id,
                    role=role,
                    content=content,
                )
            )

    def recent_messages(self, user_id: int, limit: int = 12) -> list[dict[str, Any]]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        statement = (
            select(
                _MESSAGES.c.role,
                _MESSAGES.c.content,
                _MESSAGES.c.created_at,
            )
            .where(_MESSAGES.c.user_id == user_id)
            .order_by(_MESSAGES.c.id.desc())
            .limit(limit)
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [
            {
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"].isoformat(),
            }
            for row in reversed(rows)
        ]

    def get_portfolio(self, user_id: int) -> list[dict[str, Any]]:
        statement = (
            select(
                _PORTFOLIO_HOLDINGS.c.id,
                _PORTFOLIO_HOLDINGS.c.name,
                _PORTFOLIO_HOLDINGS.c.asset_class,
                _PORTFOLIO_HOLDINGS.c.sector,
                _PORTFOLIO_HOLDINGS.c.market_value,
            )
            .where(_PORTFOLIO_HOLDINGS.c.user_id == user_id)
            .order_by(_PORTFOLIO_HOLDINGS.c.id)
        )
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]

    def replace_portfolio(
        self, user_id: int, holdings: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if len(holdings) > 100:
            raise AccountError("A portfolio can contain at most 100 holdings.")
        with self.engine.begin() as connection:
            user_exists = connection.execute(
                select(_USERS.c.id).where(_USERS.c.id == user_id)
            ).scalar_one_or_none()
            if user_exists is None:
                raise AccountError("Account no longer exists.")
            connection.execute(
                _PORTFOLIO_HOLDINGS.delete().where(
                    _PORTFOLIO_HOLDINGS.c.user_id == user_id
                )
            )
            if holdings:
                connection.execute(
                    insert(_PORTFOLIO_HOLDINGS),
                    [
                        {
                            "user_id": user_id,
                            "name": holding["name"].strip(),
                            "asset_class": holding["asset_class"],
                            "sector": holding["sector"],
                            "market_value": float(holding["market_value"]),
                        }
                        for holding in holdings
                    ],
                )
        return self.get_portfolio(user_id)

    def dispose(self) -> None:
        self.engine.dispose()


def migrate_sqlite_to_database(
    sqlite_path: str | Path,
    destination_url: str | Path | URL,
) -> None:
    source_path = Path(sqlite_path)
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite database not found: {source_path}")

    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row
    try:
        existing_tables = {
            row["name"]
            for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        required_tables = {"users", "profiles", "messages"}
        if not required_tables.issubset(existing_tables):
            missing = ", ".join(sorted(required_tables - existing_tables))
            raise ValueError(f"SQLite database is missing tables: {missing}")
        records = {
            "users": [dict(row) for row in source.execute("SELECT * FROM users ORDER BY id")],
            "profiles": [
                dict(row)
                for row in source.execute("SELECT * FROM profiles ORDER BY user_id")
            ],
            "messages": [dict(row) for row in source.execute("SELECT * FROM messages ORDER BY id")],
            "portfolio_holdings": (
                [
                    dict(row)
                    for row in source.execute(
                        "SELECT * FROM portfolio_holdings ORDER BY id"
                    )
                ]
                if "portfolio_holdings" in existing_tables
                else []
            ),
        }
    finally:
        source.close()

    destination = Database(destination_url)
    tables = {
        "users": _USERS,
        "profiles": _PROFILES,
        "messages": _MESSAGES,
        "portfolio_holdings": _PORTFOLIO_HOLDINGS,
    }
    try:
        with destination.engine.begin() as connection:
            counts = {
                name: connection.execute(select(func.count()).select_from(table)).scalar_one()
                for name, table in tables.items()
            }
            if any(counts.values()):
                raise ValueError(
                    "Destination database must have empty users, profiles, and messages tables."
                )
            for table_name in ("users", "profiles", "messages", "portfolio_holdings"):
                table = tables[table_name]
                for record in records[table_name]:
                    for column_name in ("created_at",):
                        value = record.get(column_name)
                        if isinstance(value, str):
                            record[column_name] = datetime.fromisoformat(value)
                    connection.execute(insert(table).values(**record))

            if destination.engine.dialect.name == "postgresql":
                for table_name in ("users", "messages", "portfolio_holdings"):
                    connection.execute(
                        text(
                            "SELECT setval(pg_get_serial_sequence(:table_name, 'id'), "
                            "COALESCE((SELECT MAX(id) FROM " + table_name + "), 1), "
                            "EXISTS (SELECT 1 FROM " + table_name + "))"
                        ),
                        {"table_name": table_name},
                    )
    finally:
        destination.dispose()


def _hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"pbkdf2_sha256${_ITERATIONS}${salt.hex()}${digest.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iteration_text, salt_hex, digest_hex = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iteration_text)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False
