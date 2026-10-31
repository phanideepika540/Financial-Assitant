import io
import json
import urllib.error

import pytest

from src.core.errors import ProviderError
from src.data.news_data import NewsProvider


def test_falls_back_to_alpha_vantage_when_rss_returns_404(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request)
        if len(calls) == 1:
            raise urllib.error.HTTPError(
                request.full_url, 404, "Not Found", {}, None
            )
        return io.BytesIO(
            json.dumps(
                {
                    "feed": [
                        {
                            "title": "Market headline",
                            "url": "https://example.com/story",
                            "time_published": "20261027T120000",
                        }
                    ]
                }
            ).encode()
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = NewsProvider(
        "https://finance.yahoo.com/news/rssindex",
        alpha_vantage_api_key="test-key",
    )

    headlines = provider.headlines()

    assert "Source: Alpha Vantage News & Sentiment" in headlines
    assert "Market headline" in headlines
    assert "https://example.com/story" in headlines
    assert len(calls) == 2
    assert "function=NEWS_SENTIMENT" in calls[1].full_url
    assert "apikey=test-key" in calls[1].full_url


def test_logs_missing_fallback_key_and_returns_generic_error(monkeypatch, caplog):
    def fail_rss(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", fail_rss)
    provider = NewsProvider("https://finance.yahoo.com/news/rssindex")

    with pytest.raises(
        ProviderError, match="Financial news is currently unavailable"
    ) as exc_info:
        provider.headlines()

    assert "ALPHA_VANTAGE_API_KEY" not in str(exc_info.value)
    assert "ALPHA_VANTAGE_API_KEY" in caplog.text


def test_uses_rss_headlines_without_calling_fallback(monkeypatch):
    payload = b"""<rss><channel><item>
    <title>RSS headline</title><link>https://example.com/rss</link>
    <pubDate>Tue, 27 Oct 2026 12:00:00 GMT</pubDate>
    </item></channel></rss>"""
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request)
        return io.BytesIO(payload)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = NewsProvider(
        "https://example.com/rss", alpha_vantage_api_key="test-key"
    )

    headlines = provider.headlines()

    assert "Source: Financial news RSS" in headlines
    assert "RSS headline" in headlines
    assert len(calls) == 1


def test_logs_alpha_vantage_access_restriction_without_showing_it_in_error(
    monkeypatch, caplog
):
    def fake_urlopen(request, timeout):
        if "alphavantage.co" in request.full_url:
            return io.BytesIO(
                json.dumps(
                    {
                        "Information": (
                            "This is a premium endpoint. Subscribe to unlock it."
                        )
                    }
                ).encode()
            )
        return io.BytesIO(b"<rss><channel /></rss>")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = NewsProvider(
        "https://example.com/rss", alpha_vantage_api_key="test-key"
    )

    with pytest.raises(
        ProviderError, match="Financial news is currently unavailable"
    ) as exc_info:
        provider.headlines()

    assert "premium endpoint" in caplog.text
    assert "premium endpoint" not in str(exc_info.value)
    assert "test-key" not in caplog.text


def test_rss_retries_temporary_server_failure(monkeypatch):
    payload = b"""<rss><channel><item>
    <title>Recovered headline</title><link>https://example.com/recovered</link>
    </item></channel></rss>"""
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request)
        if len(calls) == 1:
            raise urllib.error.HTTPError(
                request.full_url, 503, "Unavailable", {}, None
            )
        return io.BytesIO(payload)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("src.data.retry.time.sleep", lambda _: None)

    headlines = NewsProvider("https://example.com/rss").headlines()

    assert "Recovered headline" in headlines
    assert len(calls) == 2


def test_alpha_vantage_rate_limit_is_explained_without_provider_details(monkeypatch):
    def fake_urlopen(request, timeout):
        if "alphavantage.co" in request.full_url:
            return io.BytesIO(json.dumps({"Note": "API call frequency limit"}).encode())
        raise urllib.error.HTTPError(
            request.full_url, 503, "Unavailable", {}, None
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("src.data.retry.time.sleep", lambda _: None)
    provider = NewsProvider(
        "https://example.com/rss", alpha_vantage_api_key="test-key"
    )

    with pytest.raises(ProviderError, match="rate limit or access restriction"):
        provider.headlines()
