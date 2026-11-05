import json

from langchain_core.messages import AIMessageChunk
from fastapi.testclient import TestClient
import pytest

from src.data.database import Database
from src.web_app import api


def _client(monkeypatch, tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    monkeypatch.setattr(api, "get_database", lambda: database)
    return TestClient(api.app), database


def test_register_profile_and_logout(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)

    response = client.post(
        "/api/auth/register",
        json={
            "username": "learner_01",
            "password": "a-very-long-password",
            "confirmation": "a-very-long-password",
        },
    )
    assert response.status_code == 201
    assert response.json()["authenticated"] is True
    assert response.json()["username"] == "learner_01"

    profile = {
        "learning_level": "Intermediate",
        "goal": "Learn about saving",
        "time_horizon": "3 years",
        "risk_comfort": "Low",
    }
    response = client.patch("/api/profile", json=profile)
    assert response.status_code == 200
    assert response.json()["profile"] == profile

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/session").json() == {"authenticated": False}
    assert (
        client.post(
            "/api/auth/login",
            json={"username": "learner_01", "password": "incorrect-password"},
        ).status_code
        == 401
    )
    response = client.post(
        "/api/auth/login",
        json={"username": "learner_01", "password": "a-very-long-password"},
    )
    assert response.status_code == 200
    assert response.json()["authenticated"] is True


def test_only_admin_can_read_all_user_profiles(monkeypatch, tmp_path):
    client, database = _client(monkeypatch, tmp_path)
    admin_id = database.register("admin_user", "a-very-long-password")
    user_id = database.register("regular_user", "a-very-long-password")
    database.promote_user("admin_user")
    database.save_profile(
        user_id,
        {
            "learning_level": "Intermediate",
            "goal": "Save for a home",
            "time_horizon": "8 years",
            "risk_comfort": "Low",
        },
    )

    user_login = client.post(
        "/api/auth/login",
        json={"username": "regular_user", "password": "a-very-long-password"},
    )
    assert user_login.status_code == 200
    assert user_login.json()["role"] == "user"
    assert user_login.json()["profile"]["goal"] == "Save for a home"
    assert client.get("/api/admin/profiles").status_code == 403

    admin_login = client.post(
        "/api/auth/login",
        json={"username": "admin_user", "password": "a-very-long-password"},
    )
    assert admin_login.status_code == 200
    assert admin_login.json()["role"] == "admin"

    response = client.get("/api/admin/profiles")

    assert response.status_code == 200
    profiles = response.json()["profiles"]
    assert [profile["username"] for profile in profiles] == [
        "admin_user",
        "regular_user",
    ]
    assert profiles[1]["goal"] == "Save for a home"
    assert database.get_role(admin_id) == "admin"


def test_admin_profiles_endpoint_requires_authentication(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)

    assert client.get("/api/admin/profiles").status_code == 401


def test_chat_requires_authentication(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)

    response = client.post("/api/chat", json={"question": "Explain compound interest"})

    assert response.status_code == 401


def test_clear_chat_history_deletes_only_current_users_messages_and_cache(
    monkeypatch,
    tmp_path,
):
    client, database = _client(monkeypatch, tmp_path)
    assert client.delete("/api/chat/history").status_code == 401

    client.post(
        "/api/auth/register",
        json={
            "username": "history_owner",
            "password": "a-very-long-password",
            "confirmation": "a-very-long-password",
        },
    )
    workflow_calls = 0

    class Workflow:
        def invoke(self, state):
            nonlocal workflow_calls
            workflow_calls += 1
            return {
                "answer": "A general educational answer.",
                "agent": "finance_qa",
                "sources": [],
            }

    monkeypatch.setattr(api, "get_workflow", lambda: Workflow())
    question = {"question": "Explain compound interest"}
    assert client.post("/api/chat", json=question).status_code == 200
    assert client.post("/api/chat", json=question).status_code == 200
    assert workflow_calls == 1

    second_client = TestClient(api.app)
    second_client.post(
        "/api/auth/register",
        json={
            "username": "other_history",
            "password": "a-very-long-password",
            "confirmation": "a-very-long-password",
        },
    )
    assert second_client.post("/api/chat", json=question).status_code == 200
    other_user_id = database.authenticate("other_history", "a-very-long-password")
    assert other_user_id is not None

    response = client.delete("/api/chat/history")

    assert response.status_code == 204
    assert client.get("/api/session").json()["history"] == []
    assert len(database.recent_messages(other_user_id)) == 2
    assert client.post("/api/chat", json=question).status_code == 200
    assert workflow_calls == 3


def test_portfolio_requires_authentication(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)

    assert client.get("/api/portfolio").status_code == 401
    assert client.put("/api/portfolio", json={"holdings": []}).status_code == 401


def test_portfolio_api_persists_manual_holdings(monkeypatch, tmp_path):
    client, database = _client(monkeypatch, tmp_path)
    user_id = database.register("portfolio_user", "a-very-long-password")
    client.post(
        "/api/auth/login",
        json={"username": "portfolio_user", "password": "a-very-long-password"},
    )
    payload = {
        "holdings": [
            {
                "name": "Broad-market fund",
                "asset_class": "Stocks",
                "sector": "Diversified / not applicable",
                "market_value": 12500.5,
            },
            {
                "name": "Treasury fund",
                "asset_class": "Bonds",
                "sector": "Diversified / not applicable",
                "market_value": 4000,
            },
        ]
    }

    response = client.put("/api/portfolio", json=payload)

    assert response.status_code == 200
    saved = response.json()["holdings"]
    assert [holding["name"] for holding in saved] == [
        "Broad-market fund",
        "Treasury fund",
    ]
    assert client.get("/api/portfolio").json()["holdings"] == saved
    assert database.get_portfolio(user_id) == saved

    empty_response = client.put("/api/portfolio", json={"holdings": []})
    assert empty_response.status_code == 200
    assert empty_response.json() == {"holdings": []}


@pytest.mark.parametrize(
    "holding",
    [
        {
            "name": "   ",
            "asset_class": "Stocks",
            "sector": "Technology",
            "market_value": 100,
        },
        {
            "name": "Invalid value",
            "asset_class": "Stocks",
            "sector": "Technology",
            "market_value": 0,
        },
        {
            "name": "Invalid class",
            "asset_class": "Crypto",
            "sector": "Technology",
            "market_value": 100,
        },
    ],
)
def test_portfolio_api_rejects_invalid_holding_values(monkeypatch, tmp_path, holding):
    client, _ = _client(monkeypatch, tmp_path)
    client.post(
        "/api/auth/register",
        json={
            "username": "invalid_portfolio",
            "password": "a-very-long-password",
            "confirmation": "a-very-long-password",
        },
    )

    response = client.put("/api/portfolio", json={"holdings": [holding]})

    assert response.status_code == 422


def test_health_endpoint():
    client = TestClient(api.app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_and_persists_assistant_response(monkeypatch, tmp_path):
    monkeypatch.delenv("SHOW_RETRIEVAL_METADATA", raising=False)
    client, _ = _client(monkeypatch, tmp_path)
    client.post(
        "/api/auth/register",
        json={
            "username": "learner_02",
            "password": "a-very-long-password",
            "confirmation": "a-very-long-password",
        },
    )

    class Workflow:
        def invoke(self, state):
            assert state["question"] == "Explain compound interest"
            return {
                "answer": "Interest can earn interest over time.",
                "agent": "finance_qa",
                "sources": ["investing_basics.md"],
            }

    monkeypatch.setattr(api, "get_workflow", lambda: Workflow())
    response = client.post(
        "/api/chat", json={"question": "  Explain compound interest  "}
    )

    assert response.status_code == 200
    assert response.json() == {
        "question": "Explain compound interest",
        "answer": "Interest can earn interest over time.",
        "sources": ["investing_basics.md"],
        "citations": [],
        "agent": "finance_qa",
        "agent_label": "Finance Q&A",
    }
    history = client.get("/api/session").json()["history"]
    assert [
        {key: message[key] for key in ("role", "content")}
        for message in history
    ] == [
        {"role": "user", "content": "Explain compound interest"},
        {"role": "assistant", "content": "Interest can earn interest over time."},
    ]
    assert all(message["created_at"] for message in history)


def test_market_chart_is_returned_and_saved_with_chat_history(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)
    client.post(
        "/api/auth/register",
        json={
            "username": "market_chart_user",
            "password": "a-very-long-password",
            "confirmation": "a-very-long-password",
        },
    )
    chart = {
        "symbol": "AAPL",
        "dates": ["2026-10-29", "2026-10-30"],
        "closes": [100.0, 101.0],
        "retrieved_at": "2026-10-30T12:00:00+00:00",
        "provider": "Test market data",
    }

    class Workflow:
        def invoke(self, state):
            return {
                "answer": "AAPL recently closed at 101.",
                "agent": "market_analysis",
                "sources": [],
                "market_chart": chart,
            }

    monkeypatch.setattr(api, "get_workflow", lambda: Workflow())
    response = client.post(
        "/api/chat", json={"question": "Ticker: AAPL market chart test"}
    )

    assert response.status_code == 200
    assert response.json()["market_chart"] == chart
    history = client.get("/api/session").json()["history"]
    assert history[-1]["chart_data"] == chart


def test_chat_reuses_cached_answer_for_same_user_and_question(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)
    client.post(
        "/api/auth/register",
        json={
            "username": "cache_user",
            "password": "a-very-long-password",
            "confirmation": "a-very-long-password",
        },
    )
    calls = 0

    class Workflow:
        def invoke(self, state):
            nonlocal calls
            calls += 1
            return {
                "answer": "Compound interest earns interest on prior interest.",
                "agent": "finance_qa",
                "sources": ["https://example.com/interest"],
                "citations": [],
            }

    monkeypatch.setattr(api, "get_workflow", lambda: Workflow())
    first = client.post("/api/chat", json={"question": "Explain compound interest"})
    second = client.post(
        "/api/chat",
        json={"question": "  EXPLAIN   COMPOUND INTEREST  "},
    )

    assert first.status_code == second.status_code == 200
    assert second.json()["answer"] == first.json()["answer"]
    assert calls == 1
    assert len(client.get("/api/session").json()["history"]) == 4

    profile_update = client.patch(
        "/api/profile",
        json={
            "learning_level": "Intermediate",
            "goal": "Learn about investing",
            "time_horizon": "",
            "risk_comfort": "Not specified",
        },
    )
    assert profile_update.status_code == 200
    client.post("/api/chat", json={"question": "Explain compound interest"})
    assert calls == 2

    other_client = TestClient(api.app)
    other_client.post(
        "/api/auth/register",
        json={
            "username": "other_cache_user",
            "password": "a-very-long-password",
            "confirmation": "a-very-long-password",
        },
    )
    other_client.post("/api/chat", json={"question": "Explain compound interest"})
    assert calls == 3


@pytest.mark.parametrize(
    "question",
    [
        "What is the latest financial news?",
        "What does that mean?",
    ],
)
def test_chat_does_not_cache_dynamic_or_follow_up_questions(
    monkeypatch,
    tmp_path,
    question,
):
    client, _ = _client(monkeypatch, tmp_path)
    client.post(
        "/api/auth/register",
        json={
            "username": "uncached_user",
            "password": "a-very-long-password",
            "confirmation": "a-very-long-password",
        },
    )
    calls = 0

    class Workflow:
        def invoke(self, state):
            nonlocal calls
            calls += 1
            return {
                "answer": f"Response {calls}.",
                "agent": "finance_qa",
                "sources": [],
            }

    monkeypatch.setattr(api, "get_workflow", lambda: Workflow())
    client.post("/api/chat", json={"question": question})
    client.post("/api/chat", json={"question": question})

    assert calls == 2


def test_chat_labels_all_selected_specialists(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)
    client.post(
        "/api/auth/register",
        json={
            "username": "multi_agent_user",
            "password": "a-very-long-password",
            "confirmation": "a-very-long-password",
        },
    )

    class Workflow:
        def invoke(self, state):
            return {
                "answer": "Combined educational response.",
                "agent": "portfolio_analysis",
                "agents": ["portfolio_analysis", "tax_education"],
                "sources": [],
            }

    monkeypatch.setattr(api, "get_workflow", lambda: Workflow())
    response = client.post(
        "/api/chat", json={"question": "Explain portfolio and tax considerations"}
    )

    assert response.status_code == 200
    assert response.json()["agent_label"] == "Portfolio analysis + Tax education"


def test_streaming_chat_sends_tokens_and_persists_final_answer(monkeypatch, tmp_path):
    monkeypatch.setenv("SHOW_RETRIEVAL_METADATA", "true")
    client, database = _client(monkeypatch, tmp_path)
    user_id = database.register("stream_user", "a-very-long-password")
    client.post(
        "/api/auth/login",
        json={"username": "stream_user", "password": "a-very-long-password"},
    )

    class Workflow:
        def stream(self, workflow_input, stream_mode):
            assert workflow_input["question"] == "Explain bonds"
            assert stream_mode == ["messages", "updates"]
            yield "updates", {
                "router": {
                    "agents": ["finance_qa"],
                    "agent": "finance_qa",
                }
            }
            yield "messages", (
                AIMessageChunk(content="A bond "),
                {"langgraph_node": "finance_qa"},
            )
            yield "messages", (
                AIMessageChunk(content="is a loan."),
                {"langgraph_node": "finance_qa"},
            )
            yield "updates", {
                "finance_qa": {
                    "answer": "A bond is a loan.",
                    "sources": ["https://example.com/bonds"],
                    "citations": [],
                    "agent": "finance_qa",
                    "agents": ["finance_qa"],
                    "retrieval_filter": ["finance_qa", "general"],
                }
            }

    monkeypatch.setattr(api, "get_workflow", lambda: Workflow())
    response = client.post(
        "/api/chat/stream",
        json={"question": "Explain bonds"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = []
    for block in response.text.strip().split("\n\n"):
        lines = block.splitlines()
        event_name = next(line[7:] for line in lines if line.startswith("event: "))
        payload = json.loads(next(line[6:] for line in lines if line.startswith("data: ")))
        events.append((event_name, payload))

    assert [payload["content"] for name, payload in events if name == "token"] == [
        "A bond ",
        "is a loan.",
    ]
    completion = next(payload for name, payload in events if name == "done")
    assert completion["answer"] == "A bond is a loan."
    assert completion["agent_label"] == "Finance Q&A"
    assert completion["retrieval_filter"] == ["finance_qa", "general"]
    assert database.recent_messages(user_id)[-1]["content"] == "A bond is a loan."
    repeated_response = client.post(
        "/api/chat/stream",
        json={"question": "Explain bonds"},
    )
    repeated_events = [
        json.loads(next(line[6:] for line in block.splitlines() if line.startswith("data: ")))
        for block in repeated_response.text.strip().split("\n\n")
    ]
    assert [event["content"] for event in repeated_events if "content" in event] == [
        "A bond is a loan."
    ]
    assert repeated_events[-1]["answer"] == "A bond is a loan."


def test_goal_request_uses_existing_prompt_builder(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)
    client.post(
        "/api/auth/register",
        json={
            "username": "learner_03",
            "password": "a-very-long-password",
            "confirmation": "a-very-long-password",
        },
    )

    class Workflow:
        def invoke(self, state):
            assert "build an emergency fund" in state["question"]
            assert "2 years" in state["question"]
            assert "$1,000" in state["question"]
            assert "$250 per month" in state["question"]
            return {
                "answer": "Start by exploring your savings options.",
                "agent": "goal_planning",
                "sources": [],
            }

    monkeypatch.setattr(api, "get_workflow", lambda: Workflow())
    response = client.post(
        "/api/goal",
        json={
            "goal": "build an emergency fund",
            "time_horizon": "2 years",
            "target_amount": "$5,000",
            "current_savings": "$1,000",
            "monthly_contribution": "$250",
        },
    )

    assert response.status_code == 200
    assert response.json()["agent_label"] == "Goal planning"


def test_goal_request_rejects_empty_goal(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path)
    client.post(
        "/api/auth/register",
        json={
            "username": "learner_04",
            "password": "a-very-long-password",
            "confirmation": "a-very-long-password",
        },
    )

    response = client.post(
        "/api/goal", json={"goal": "  ", "time_horizon": "", "target_amount": ""}
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Enter a goal to start a planning conversation."
