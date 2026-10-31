import sqlite3
from datetime import datetime

import pytest

from src.data.database import AccountError, Database, migrate_sqlite_to_database


def test_registration_authentication_and_profile_persistence(tmp_path):
    database = Database(tmp_path / "assistant.sqlite3")
    user_id = database.register("learner_01", "correct-horse-battery")

    assert database.authenticate("learner_01", "correct-horse-battery") == user_id
    assert database.authenticate("learner_01", "wrong-password") is None

    database.save_profile(
        user_id,
        {
            "learning_level": "Intermediate",
            "goal": "Learn about retirement",
            "time_horizon": "20 years",
            "risk_comfort": "Moderate",
        },
    )
    assert database.get_profile(user_id)["learning_level"] == "Intermediate"
    assert database.get_role(user_id) == "user"


def test_admin_can_be_promoted_and_list_profiles(tmp_path):
    database = Database(tmp_path / "assistant.sqlite3")
    admin_id = database.register("profile_admin", "correct-horse-battery")
    user_id = database.register("profile_user", "correct-horse-battery")
    database.save_profile(
        user_id,
        {
            "learning_level": "Advanced",
            "goal": "Understand retirement accounts",
            "time_horizon": "15 years",
            "risk_comfort": "Moderate",
        },
    )

    database.promote_user("PROFILE_ADMIN")

    assert database.get_role(admin_id) == "admin"
    assert database.get_role(user_id) == "user"
    assert database.list_user_profiles() == [
        {
            "username": "profile_admin",
            "role": "admin",
            "learning_level": "Beginner",
            "goal": "",
            "time_horizon": "",
            "risk_comfort": "",
        },
        {
            "username": "profile_user",
            "role": "user",
            "learning_level": "Advanced",
            "goal": "Understand retirement accounts",
            "time_horizon": "15 years",
            "risk_comfort": "Moderate",
        },
    ]

    with pytest.raises(AccountError, match="No account exists"):
        database.promote_user("not_registered")


def test_existing_database_gets_default_user_role(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username VARCHAR(32) NOT NULL,
                password_hash VARCHAR(256) NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO users (username, password_hash)
            VALUES ('legacy_user', 'not-used-for-auth');
            """
        )

    database = Database(path)

    assert database.get_role(1) == "user"


def test_password_is_not_stored_in_plaintext(tmp_path):
    path = tmp_path / "assistant.sqlite3"
    database = Database(path)
    database.register("safe_user", "long-password-123")

    with sqlite3.connect(path) as connection:
        stored = connection.execute(
            "SELECT password_hash FROM users WHERE username = ?", ("safe_user",)
        ).fetchone()[0]
    assert stored != "long-password-123"
    assert stored.startswith("pbkdf2_sha256$")


def test_rejects_weak_password_and_invalid_username(tmp_path):
    database = Database(tmp_path / "assistant.sqlite3")
    with pytest.raises(AccountError, match="12 characters"):
        database.register("valid_user", "short")
    with pytest.raises(AccountError, match="Username"):
        database.register("x", "a-long-enough-password")


def test_persists_conversation_in_chronological_order(tmp_path):
    database = Database(tmp_path / "assistant.sqlite3")
    user_id = database.register("chat_user", "long-password-123")
    database.save_message(user_id, "user", "What is a bond?")
    database.save_message(user_id, "assistant", "A bond is a loan to an issuer.")

    messages = database.recent_messages(user_id)
    assert [
        {key: message[key] for key in ("role", "content")}
        for message in messages
    ] == [
        {"role": "user", "content": "What is a bond?"},
        {"role": "assistant", "content": "A bond is a loan to an issuer."},
    ]
    assert all(datetime.fromisoformat(message["created_at"]) for message in messages)


def test_portfolio_holdings_are_saved_per_account_and_can_be_replaced(tmp_path):
    database = Database(tmp_path / "assistant.sqlite3")
    first_user = database.register("portfolio_one", "long-password-123")
    second_user = database.register("portfolio_two", "long-password-123")
    holdings = [
        {
            "name": "Broad-market fund",
            "asset_class": "Stocks",
            "sector": "Diversified / not applicable",
            "market_value": 12500.5,
        }
    ]

    saved = database.replace_portfolio(first_user, holdings)

    assert len(saved) == 1
    assert saved[0]["name"] == "Broad-market fund"
    assert saved[0]["market_value"] == 12500.5
    assert database.get_portfolio(second_user) == []
    assert database.replace_portfolio(first_user, []) == []


def test_migrates_sqlite_accounts_profiles_and_messages(tmp_path):
    source_path = tmp_path / "source.sqlite3"
    source = Database(source_path)
    user_id = source.register("migration_user", "long-password-123")
    source.save_profile(
        user_id,
        {
            "learning_level": "Advanced",
            "goal": "Learn about bonds",
            "time_horizon": "5 years",
            "risk_comfort": "Low",
        },
    )
    source.save_message(user_id, "user", "Explain bonds")
    source.save_message(user_id, "assistant", "A bond is a debt instrument.")
    source.replace_portfolio(
        user_id,
        [
            {
                "name": "Treasury fund",
                "asset_class": "Bonds",
                "sector": "Diversified / not applicable",
                "market_value": 2400.0,
            }
        ],
    )
    source.dispose()

    destination_path = tmp_path / "destination.sqlite3"
    migrate_sqlite_to_database(source_path, destination_path)

    migrated = Database(destination_path)
    assert migrated.authenticate("MIGRATION_USER", "long-password-123") == user_id
    assert migrated.get_profile(user_id) == {
        "learning_level": "Advanced",
        "goal": "Learn about bonds",
        "time_horizon": "5 years",
        "risk_comfort": "Low",
    }
    assert [
        {key: message[key] for key in ("role", "content")}
        for message in migrated.recent_messages(user_id)
    ] == [
        {"role": "user", "content": "Explain bonds"},
        {"role": "assistant", "content": "A bond is a debt instrument."},
    ]
    assert migrated.get_portfolio(user_id)[0]["name"] == "Treasury fund"


def test_migration_refuses_non_empty_destination(tmp_path):
    source_path = tmp_path / "source.sqlite3"
    source = Database(source_path)
    source.register("migration_user", "long-password-123")
    source.dispose()

    destination_path = tmp_path / "destination.sqlite3"
    destination = Database(destination_path)
    destination.register("existing_user", "long-password-123")
    destination.dispose()

    with pytest.raises(ValueError, match="must have empty"):
        migrate_sqlite_to_database(source_path, destination_path)


def test_migration_supports_older_sqlite_database_without_portfolio_table(tmp_path):
    source_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(source_path) as connection:
        connection.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE profiles (
                user_id INTEGER PRIMARY KEY,
                learning_level TEXT NOT NULL,
                goal TEXT NOT NULL,
                time_horizon TEXT NOT NULL,
                risk_comfort TEXT NOT NULL
            );
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )

    destination = tmp_path / "postgres-placeholder.sqlite3"
    migrate_sqlite_to_database(source_path, destination)

    assert Database(destination).get_portfolio(1) == []
