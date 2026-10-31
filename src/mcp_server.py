from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.data.web_search import TavilySearchProvider

mcp = FastMCP("finance-web-search")
search_provider = TavilySearchProvider()


@mcp.tool()
def web_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "news",
) -> list[dict[str, str]]:
    """Search the web and return result titles, dates, summaries, and source URLs."""
    return search_provider.search(
        query,
        max_results=max_results,
        topic=topic,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
