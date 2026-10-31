from __future__ import annotations

import logging
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Literal

import httpx

from src.core.errors import ProviderError
from src.data.retry import retry_request

logger = logging.getLogger(__name__)

_TAVILY_ENDPOINT = "https://api.tavily.com/search"
_MAX_QUERY_LENGTH = 400
_MAX_RESULTS = 8
_MAX_CONTENT_LENGTH = 800
_CACHE_TTL_SECONDS = 90
_CACHE_MAX_ENTRIES = 128
SearchTopic = Literal["general", "news", "finance"]


class TavilySearchProvider:
    def __init__(self, api_key: str | None = None, timeout: float = 12.0):
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        self.timeout = timeout
        self._cache: OrderedDict[
            tuple[str, str, int], tuple[float, list[dict[str, str]]]
        ] = OrderedDict()
        self._cache_lock = threading.Lock()

    def search(
        self,
        query: str,
        max_results: int = 5,
        topic: SearchTopic = "news",
    ) -> list[dict[str, str]]:
        normalized_query = " ".join(query.split())
        if not normalized_query:
            raise ValueError("Search query cannot be blank.")
        if len(normalized_query) > _MAX_QUERY_LENGTH:
            raise ValueError(
                f"Search query must be {_MAX_QUERY_LENGTH} characters or fewer."
            )
        result_limit = max(1, min(max_results, _MAX_RESULTS))
        cache_key = (normalized_query.casefold(), topic, result_limit)
        now = time.monotonic()
        with self._cache_lock:
            cached = self._cache.get(cache_key)
            if cached is not None:
                expires_at, results = cached
                if now < expires_at:
                    self._cache.move_to_end(cache_key)
                    return [result.copy() for result in results]
                del self._cache[cache_key]
        if not self.api_key:
            logger.error("Web search is unavailable because TAVILY_API_KEY is not configured.")
            raise ProviderError(
                "Web search is not configured. Set TAVILY_API_KEY to enable it."
            )

        payload: dict[str, Any] = {
            "api_key": self.api_key,
            "query": normalized_query,
            "topic": topic,
            "search_depth": "basic",
            "max_results": result_limit,
            "include_answer": False,
            "include_raw_content": False,
        }

        def send_request() -> httpx.Response:
            response = httpx.post(
                _TAVILY_ENDPOINT,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response

        try:
            response = retry_request(
                send_request,
                is_retryable=_is_retryable_request_error,
            )
            data = response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Tavily search failed with HTTP status %s",
                exc.response.status_code,
            )
            if exc.response.status_code == 429:
                raise ProviderError(
                    "Web search is rate limited right now. Please try again later."
                ) from exc
            raise ProviderError(
                "Web search is currently unavailable. Please try again later."
            ) from exc
        except (httpx.RequestError, ValueError) as exc:
            logger.warning("Tavily search request failed (%s)", type(exc).__name__)
            raise ProviderError(
                "Web search is currently unavailable. Please try again later."
            ) from exc

        results = data.get("results", []) if isinstance(data, dict) else []
        if not isinstance(results, list):
            raise ProviderError("Web search returned an unexpected response.")

        normalized_results: list[dict[str, str]] = []
        for result in results[:_MAX_RESULTS]:
            if not isinstance(result, dict):
                continue
            title = str(result.get("title", "")).strip()
            url = str(result.get("url", "")).strip()
            content = str(result.get("content", "")).strip()
            published_date = str(result.get("published_date") or "").strip()
            if not title or not url.startswith(("https://", "http://")):
                continue
            normalized_results.append(
                {
                    "title": title[:300],
                    "url": url[:2_000],
                    "content": content[:_MAX_CONTENT_LENGTH],
                    "published_date": published_date[:80],
                }
            )
        with self._cache_lock:
            self._cache[cache_key] = (
                time.monotonic() + _CACHE_TTL_SECONDS,
                normalized_results,
            )
            self._cache.move_to_end(cache_key)
            while len(self._cache) > _CACHE_MAX_ENTRIES:
                self._cache.popitem(last=False)
        return [result.copy() for result in normalized_results]


def format_search_results(results: list[dict[str, str]]) -> str:
    if not results:
        return "Web search returned no relevant results."
    return "\n\n".join(
        "\n".join(
            part
            for part in (
                f"Title: {result['title']}",
                f"Published: {result['published_date']}" if result["published_date"] else "",
                f"URL: {result['url']}",
                f"Summary: {result['content']}" if result["content"] else "",
            )
            if part
        )
        for result in results
    )


def _is_retryable_request_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.RequestError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code >= 500
    return False
