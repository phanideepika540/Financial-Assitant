import httpx
import pytest

from src.core.errors import ProviderError
from src.data.web_search import TavilySearchProvider, format_search_results


def test_search_normalizes_query_and_returns_only_web_urls(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured.update(json)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Company news",
                        "url": "https://example.com/news",
                        "content": "A recent company announcement.",
                        "published_date": "2026-10-30",
                    },
                    {
                        "title": "Unsafe link",
                        "url": "javascript:alert(1)",
                        "content": "This must not be returned.",
                    },
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("src.data.web_search.httpx.post", fake_post)
    results = TavilySearchProvider(api_key="test-key").search(
        "  Latest   news about PEGA  ", max_results=20, topic="news"
    )

    assert captured["query"] == "Latest news about PEGA"
    assert captured["topic"] == "news"
    assert captured["search_depth"] == "basic"
    assert captured["max_results"] == 8
    assert len(results) == 1
    assert results[0]["published_date"] == "2026-10-30"
    assert "Title: Company news" in format_search_results(results)
    assert "URL: https://example.com/news" in format_search_results(results)


def test_search_caches_results_and_returns_independent_copies(monkeypatch):
    calls = []

    def fake_post(url, json, timeout):
        calls.append(json["query"])
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Company news",
                        "url": "https://example.com/news",
                        "content": "A recent announcement.",
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("src.data.web_search.httpx.post", fake_post)
    provider = TavilySearchProvider(api_key="test-key")
    first = provider.search("Latest PEGA news")
    first[0]["title"] = "changed by caller"
    second = provider.search(" latest pega NEWS ")

    assert calls == ["Latest PEGA news"]
    assert second[0]["title"] == "Company news"


def test_search_requires_key_and_valid_query(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    provider = TavilySearchProvider(api_key="")

    with pytest.raises(ProviderError, match="TAVILY_API_KEY"):
        provider.search("latest news")
    with pytest.raises(ValueError, match="cannot be blank"):
        provider.search("  ")
    with pytest.raises(ValueError, match="400 characters"):
        provider.search("x" * 401)


def test_search_reports_rate_limit_without_leaking_provider_response(monkeypatch):
    calls = []

    def fake_post(url, json, timeout):
        calls.append(url)
        return httpx.Response(
            429,
            text="provider limit",
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("src.data.web_search.httpx.post", fake_post)
    monkeypatch.setattr("src.data.retry.time.sleep", lambda _: None)

    with pytest.raises(ProviderError, match="rate limited") as exc_info:
        TavilySearchProvider(api_key="test-key").search("latest PEGA news")

    assert len(calls) == 1
    assert "provider limit" not in str(exc_info.value)


def test_search_reports_network_failures(monkeypatch):
    calls = []

    def fail_post(url, json, timeout):
        calls.append(url)
        raise httpx.TimeoutException("private request details")

    monkeypatch.setattr("src.data.web_search.httpx.post", fail_post)
    monkeypatch.setattr("src.data.retry.time.sleep", lambda _: None)

    with pytest.raises(ProviderError, match="currently unavailable") as exc_info:
        TavilySearchProvider(api_key="test-key").search("latest PEGA news")

    assert len(calls) == 3
    assert "private request details" not in str(exc_info.value)


def test_search_retries_server_error_then_succeeds(monkeypatch):
    calls = []

    def fake_post(url, json, timeout):
        calls.append(url)
        if len(calls) == 1:
            return httpx.Response(
                503,
                request=httpx.Request("POST", url),
            )
        return httpx.Response(
            200,
            json={"results": []},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr("src.data.web_search.httpx.post", fake_post)
    monkeypatch.setattr("src.data.retry.time.sleep", lambda _: None)

    assert TavilySearchProvider(api_key="test-key").search("latest PEGA news") == []
    assert len(calls) == 2
