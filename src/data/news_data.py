from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlencode

from src.core.errors import ProviderError
from src.data.retry import retry_request

logger = logging.getLogger(__name__)

_USER_AGENT = "AIFinanceAssistant/1.0 (educational MVP)"


class NewsProvider:
    def __init__(
        self,
        feed_url: str,
        max_items: int = 6,
        alpha_vantage_api_key: str | None = None,
    ):
        self.feed_url = feed_url
        self.max_items = max_items
        self.alpha_vantage_api_key = alpha_vantage_api_key

    def headlines(self) -> str:
        try:
            return self._rss_headlines()
        except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError, ProviderError) as exc:
            logger.warning(
                "Configured financial news RSS feed unavailable; trying Alpha Vantage fallback (%s)",
                type(exc).__name__,
            )
        return self._alpha_vantage_headlines()

    def _rss_headlines(self) -> str:
        request = urllib.request.Request(
            self.feed_url,
            headers={"User-Agent": _USER_AGENT},
        )

        def fetch_feed() -> bytes:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.read(1_000_000)

        payload = retry_request(
            fetch_feed,
            is_retryable=_is_retryable_url_error,
        )
        root = ET.fromstring(payload)

        items = []
        for item in root.findall(".//item")[: self.max_items]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            published = (item.findtext("pubDate") or "").strip()
            if title and link:
                items.append(f"- {title} ({published}) — {link}")
        if not items:
            raise ProviderError(
                "The configured financial news RSS feed returned no usable headlines."
            )
        return self._format_headlines("Financial news RSS", items)

    def _alpha_vantage_headlines(self) -> str:
        if not self.alpha_vantage_api_key:
            message = (
                "The financial news RSS feed is unavailable, and the Alpha Vantage fallback "
                "is not configured. Set ALPHA_VANTAGE_API_KEY in .env."
            )
            logger.error(message)
            raise ProviderError(
                "Financial news is currently unavailable. Please try again later."
            )

        query = urlencode(
            {
                "function": "NEWS_SENTIMENT",
                "apikey": self.alpha_vantage_api_key,
                "limit": self.max_items,
            }
        )
        request = urllib.request.Request(
            f"https://www.alphavantage.co/query?{query}",
            headers={"User-Agent": _USER_AGENT},
        )

        def fetch_feed() -> bytes:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.read(1_000_000)

        try:
            payload = retry_request(
                fetch_feed,
                is_retryable=_is_retryable_url_error,
            )
            data = json.loads(payload)
        except urllib.error.HTTPError as exc:
            logger.warning(
                "Alpha Vantage news request failed with HTTP status %s",
                exc.code,
            )
            if exc.code == 429:
                raise ProviderError(
                    "Financial news provider is rate limited right now. "
                    "Please try again later."
                ) from exc
            raise ProviderError(
                "The financial news RSS feed is unavailable, and Alpha Vantage could not "
                "provide news. Check the API key, network connection, and provider limits."
            ) from exc
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            logger.warning(
                "Alpha Vantage news request failed (%s)", type(exc).__name__
            )
            raise ProviderError(
                "The financial news RSS feed is unavailable, and Alpha Vantage could not "
                "provide news. Check the API key, network connection, and provider limits."
            ) from exc

        if not isinstance(data, dict):
            raise ProviderError(
                "The financial news RSS feed is unavailable, and Alpha Vantage returned an "
                "unexpected response. Check the API key and provider limits."
            )
        for field in ("Error Message", "Note", "Information"):
            provider_message = data.get(field)
            if provider_message:
                safe_message = str(provider_message)
                if self.alpha_vantage_api_key:
                    safe_message = safe_message.replace(
                        self.alpha_vantage_api_key, "[REDACTED]"
                    )
                logger.warning(
                    "Alpha Vantage rejected the news request (%s): %s",
                    field,
                    safe_message[:500],
                )
                raise ProviderError(
                    "Financial news provider rate limit or access restriction reached. "
                    "Please try again later."
                    if field == "Note"
                    else "Financial news is currently unavailable. Please try again later."
                )
        feed = data.get("feed", [])
        if not isinstance(feed, list):
            feed = []
        items = []
        for item in feed[: self.max_items]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            link = str(item.get("url", "")).strip()
            published = str(item.get("time_published", "")).strip()
            if title and link:
                items.append(f"- {title} ({published}) — {link}")
        if not items:
            logger.warning(
                "Alpha Vantage returned no usable news items; response fields: %s",
                ", ".join(sorted(data.keys())),
            )
            raise ProviderError(
                "The financial news RSS feed is unavailable, and Alpha Vantage returned no "
                "usable headlines. Check the API key and provider limits."
            )
        return self._format_headlines("Alpha Vantage News & Sentiment", items)

    @staticmethod
    def _format_headlines(source: str, items: list[str]) -> str:
        return (
            f"Source: {source}; headlines are not independently verified.\n"
            f"Retrieved at: {datetime.now(timezone.utc).isoformat()}\n"
            + "\n".join(items)
        )


def _is_retryable_url_error(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code >= 500
    return isinstance(
        exc,
        (urllib.error.URLError, TimeoutError, OSError),
    )
