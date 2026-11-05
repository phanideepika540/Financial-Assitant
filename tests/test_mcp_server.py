from src import mcp_server


def test_web_search_tool_uses_shared_provider(monkeypatch):
    captured = {}

    def fake_search(query, max_results, topic):
        captured.update(
            query=query,
            max_results=max_results,
            topic=topic,
        )
        return [{"title": "Company news", "url": "https://example.com/news"}]

    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setattr(mcp_server.search_provider, "search", fake_search)

    results = mcp_server.web_search(
        "latest company news",
        max_results=3,
        topic="finance",
    )

    assert captured == {
        "query": "latest company news",
        "max_results": 3,
        "topic": "finance",
    }
    assert results == [{"title": "Company news", "url": "https://example.com/news"}]
