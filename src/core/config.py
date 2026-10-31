from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigurationError(RuntimeError):
    """Raised when application configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    project_dir: Path
    title: str
    max_history_messages: int
    max_input_characters: int
    database_url: str
    chroma_path: Path
    knowledge_base_path: Path
    model: str
    embedding_model: str
    temperature: float
    history_period: str
    news_feed_url: str
    news_max_items: int

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "Settings":
        path = Path(config_path or "config.yaml").resolve()
        if not path.is_file():
            raise ConfigurationError(f"Configuration file not found: {path}")
        try:
            raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigurationError(f"Could not read configuration file: {exc}") from exc
        if not isinstance(raw, dict):
            raise ConfigurationError("Configuration must contain a YAML mapping.")

        try:
            app = raw["app"]
            llm = raw["llm"]
            news = raw["news"]
            market = raw["market_data"]
            project_dir = path.parent
            data_dir = _resolve(project_dir, app["data_dir"])
            database_url = os.getenv("DATABASE_URL")
            if not database_url:
                database_path = data_dir / str(app["database_file"])
                database_url = f"sqlite:///{database_path.as_posix()}"
            return cls(
                project_dir=project_dir,
                title=str(app["title"]),
                max_history_messages=_positive_int(app["max_history_messages"]),
                max_input_characters=_positive_int(app["max_input_characters"]),
                database_url=database_url,
                chroma_path=data_dir / str(app["chroma_dir"]),
                knowledge_base_path=_resolve(project_dir, app["knowledge_base_dir"]),
                model=os.getenv("OPENAI_MODEL", str(llm["model"])),
                embedding_model=str(llm["embedding_model"]),
                temperature=float(llm["temperature"]),
                history_period=str(market["history_period"]),
                news_feed_url=str(news["feed_url"]),
                news_max_items=_positive_int(news["max_items"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError(f"Invalid or incomplete configuration: {exc}") from exc


def _resolve(base: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else (base / candidate).resolve()


def _positive_int(value: Any) -> int:
    result = int(value)
    if result <= 0:
        raise ValueError("expected a positive integer")
    return result
