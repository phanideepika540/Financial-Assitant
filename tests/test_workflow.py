from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables import RunnableLambda
import pytest

from src.workflow.graph import AGENT_NAMES, AgentRoute, build_workflow


def test_all_six_specialists_are_registered():
    assert set(AGENT_NAMES) == {
        "finance_qa",
        "portfolio_analysis",
        "market_analysis",
        "goal_planning",
        "news_synthesizer",
        "tax_education",
    }


@pytest.mark.parametrize(
    ("question", "expected_agent"),
    [
        ("Explain compound interest", "finance_qa"),
        ("Explain my portfolio diversification", "portfolio_analysis"),
        (
            "Please explain how diversified this example portfolio is. Compare "
            "the asset types, geography, and concentration in individual companies. "
            "Point out possible overlap between the broad-market fund and the "
            "individual stocks. Use only the information below—don't guess the "
            "funds' exact holdings or recommend trades.\n\n"
            "- 40% US total-market stock index fund\n"
            "- 20% international stock index fund\n"
            "- 15% Company A (technology)\n"
            "- 10% Company B (technology)\n"
            "- 5% Company C (bank)\n"
            "- 10% US Treasury bond fund\n\n"
            "These percentages represent 100% of a hypothetical portfolio.",
            "portfolio_analysis",
        ),
        ("What is the stock price for AAPL?", "market_analysis"),
        ("Tell me the latest news on Pegasystems stock, ticker PEGA", "news_synthesizer"),
        ("Any headline about Peg Systems?", "news_synthesizer"),
        ("Build an emergency fund, 2 years, $5,000", "goal_planning"),
        ("Summarize the latest finance news", "news_synthesizer"),
        ("Explain US capital gains tax", "tax_education"),
        ("Ticker: msft", "market_analysis"),
    ],
)
def test_workflow_dispatches_each_specialist(question, expected_agent):
    class Store:
        def similarity_search(self, query, k, filter=None):
            assert filter["$or"] == [
                {"specialist": expected_agent},
                {"specialist": "general"},
            ]
            return [
                Document(
                    page_content="Educational context. Source: https://example.com/finance",
                    metadata={
                        "article_id": "test-article",
                        "title": "Test article",
                        "publisher": "Example",
                        "source_url": "https://example.com/finance",
                        "source": "https://example.com/finance",
                    },
                )
            ]

    class MarketProvider:
        def snapshot(self, symbol):
            return f"Test quote for {symbol}"

        def snapshot_with_chart(self, symbol):
            chart = {
                "symbol": symbol,
                "dates": ["2026-10-29", "2026-10-30"],
                "closes": [100.0, 101.0],
                "retrieved_at": "2026-10-30T12:00:00+00:00",
                "provider": "Test market data",
            }
            return self.snapshot(symbol), chart

    class NewsProvider:
        def headlines(self):
            return "Test news headline"

    workflow = build_workflow(
        llm=FakeListChatModel(
            responses=[
                *(
                    []
                    if expected_agent == "news_synthesizer"
                    else [f'{{"agents":["{expected_agent}"]}}']
                ),
                "General educational response.",
            ]
        ),
        vector_store=Store(),
        market_provider=MarketProvider(),
        news_provider=NewsProvider(),
    )
    result = workflow.invoke({"question": question})

    assert result["agent"] == expected_agent
    if expected_agent == "market_analysis":
        assert result["market_chart"]["symbol"] in {"AAPL", "MSFT"}
        assert "**AAPL recent market snapshot:**" in result["answer"] or (
            "**MSFT recent market snapshot:**" in result["answer"]
        )
        assert "latest available close was 101.00 on 2026-10-30" in result["answer"]
        assert "General educational response." in result["answer"]
    else:
        assert result["answer"] == "General educational response."
    if expected_agent == "news_synthesizer":
        assert result["sources"] == []
    else:
        assert "https://example.com/finance" in result["sources"]


def test_workflow_runs_two_specialists_and_synthesizes_their_responses():
    from threading import Lock

    class Store:
        def __init__(self):
            self.search_count = 0
            self.lock = Lock()
            self.search_filter = None

        def similarity_search(self, query, k, filter=None):
            with self.lock:
                self.search_count += 1
                source_number = self.search_count
                self.search_filter = filter
            return [
                Document(
                    page_content=f"Context {source_number}",
                    metadata={"source": f"source-{source_number}.md"},
                )
            ]

    def respond(prompt_value):
        messages = prompt_value.to_messages()
        system_prompt = str(messages[0].content)
        if "Choose one or two distinct specialists" in system_prompt:
            return AIMessage(
                content='{"agents":["portfolio_analysis","tax_education"]}'
            )
        if "Synthesize the specialist responses" in system_prompt:
            synthesis_input = str(messages[-1].content)
            assert "portfolio_analysis:\nPortfolio specialist draft." in synthesis_input
            assert "tax_education:\nTax specialist draft." in synthesis_input
            return AIMessage(content="Combined portfolio and tax explanation.")
        if "Explain portfolio concepts" in system_prompt:
            return AIMessage(content="Portfolio specialist draft.")
        if "Explain general US tax concepts" in system_prompt:
            return AIMessage(content="Tax specialist draft.")
        raise AssertionError(f"Unexpected model prompt: {system_prompt}")

    store = Store()
    workflow = build_workflow(
        llm=RunnableLambda(respond),
        vector_store=store,
        market_provider=object(),
        news_provider=object(),
    )

    result = workflow.invoke(
        {"question": "Explain portfolio diversification and its tax implications"}
    )

    assert result["agents"] == ["portfolio_analysis", "tax_education"]
    assert result["agent"] == "portfolio_analysis"
    assert result["answer"] == "Combined portfolio and tax explanation."
    assert result["sources"] == ["source-1.md"]
    assert result["retrieval_filter"] == [
        "portfolio_analysis",
        "tax_education",
        "general",
    ]
    assert result["citations"][0]["title"] == "source-1.md"
    assert store.search_count == 1
    assert store.search_filter == {
        "$or": [
            {"specialist": "portfolio_analysis"},
            {"specialist": "tax_education"},
            {"specialist": "general"},
        ]
    }


def test_news_specialist_searches_web_and_returns_result_urls():
    class Store:
        def similarity_search(self, query, k, filter=None):
            raise AssertionError("News-only searches should skip vector retrieval.")

    class SearchProvider:
        def __init__(self):
            self.query = None
            self.max_results = None

        def search(self, query, max_results):
            self.query = query
            self.max_results = max_results
            return [
                {
                    "title": "Recent company news",
                    "url": "https://example.com/pega-news",
                    "content": "A company announcement.",
                    "published_date": "2026-10-30",
                }
            ]

    def respond(prompt_value):
        messages = prompt_value.to_messages()
        assert "https://example.com/pega-news" in str(messages[1].content)
        assert [message.content for message in messages[2:-1]] == [
            "recent user question",
        ]
        assert "stale earnings and analyst ratings" not in str(messages)
        return AIMessage(content="A sourced news summary.")

    search_provider = SearchProvider()
    workflow = build_workflow(
        llm=RunnableLambda(respond),
        vector_store=Store(),
        market_provider=object(),
        news_provider=object(),
        web_search_provider=search_provider,
    )

    result = workflow.invoke(
        {
            "question": "Latest news on Pegasystems stock (PEGA)",
            "history": [
                HumanMessage(content=f"old message {index}")
                for index in range(5)
            ]
            + [
                HumanMessage(content="recent user question"),
                AIMessage(content="stale earnings and analyst ratings"),
            ],
        }
    )

    assert search_provider.query == (
        "Latest news on Pegasystems stock (PEGA) "
        "company latest financial news shares earnings"
    )
    assert search_provider.max_results == 3
    assert result["sources"] == ["https://example.com/pega-news"]
    assert result["retrieval_filter"] == []


def test_google_news_search_uses_generic_financial_context_terms():
    class Store:
        def similarity_search(self, query, k, filter=None):
            raise AssertionError("News-only searches should skip vector retrieval.")

    class SearchProvider:
        def __init__(self):
            self.query = None

        def search(self, query, max_results):
            self.query = query
            return [
                {
                    "title": "Alphabet stock update",
                    "url": "https://example.com/alphabet-news",
                    "content": "A current company update.",
                    "published_date": "2026-10-30",
                }
            ]

    search_provider = SearchProvider()
    workflow = build_workflow(
        llm=FakeListChatModel(responses=["A sourced Google stock update."]),
        vector_store=Store(),
        market_provider=object(),
        news_provider=object(),
        web_search_provider=search_provider,
    )

    result = workflow.invoke({"question": "tell me latest news on google stock"})

    assert search_provider.query == (
        "tell me latest news on google stock "
        "company latest financial news shares earnings"
    )
    assert result["sources"] == ["https://example.com/alphabet-news"]


def test_workflow_streams_single_specialist_answer_chunks():
    class Store:
        def similarity_search(self, query, k, filter=None):
            raise AssertionError("News-only searches should skip vector retrieval.")

    class SearchProvider:
        def search(self, query, max_results):
            return []

    workflow = build_workflow(
        llm=FakeListChatModel(responses=["A streamed answer."]),
        vector_store=Store(),
        market_provider=object(),
        news_provider=object(),
        web_search_provider=SearchProvider(),
    )

    tokens = []
    final_answer = None
    for mode, chunk in workflow.stream(
        {"question": "Latest news on PEGA"},
        stream_mode=["messages", "updates"],
    ):
        if mode == "messages":
            message, metadata = chunk
            if metadata.get("langgraph_node") == "news_synthesizer":
                tokens.append(message.content)
        elif "news_synthesizer" in chunk:
            final_answer = chunk["news_synthesizer"]["answer"]

    assert "".join(tokens) == final_answer == "A streamed answer."


def test_agent_route_rejects_duplicate_specialists():
    with pytest.raises(ValueError, match="unique"):
        AgentRoute(agents=["tax_education", "tax_education"])
