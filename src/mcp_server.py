from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from langsmith import traceable
from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")
if os.getenv("LANGSMITH_API_KEY") and "LANGSMITH_TRACING" not in os.environ:
    os.environ["LANGSMITH_TRACING"] = "true"

from src.data.web_search import TavilySearchProvider

mcp = FastMCP("finance-web-search")
search_provider = TavilySearchProvider()


@traceable(name="web_search", run_type="tool")
def _traced_web_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "news",
) -> list[dict[str, str]]:
    return search_provider.search(
        query,
        max_results=max_results,
        topic=topic,
    )


@mcp.tool()
def web_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "news",
) -> list[dict[str, str]]:
    """Search the web and return result titles, dates, summaries, and source URLs."""
    return _traced_web_search(query, max_results=max_results, topic=topic)


if __name__ == "__main__":
    mcp.run(transport="stdio")
