from __future__ import annotations

import logging
import json
import os
import re
import sys
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.sessions import SessionMiddleware

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
if os.getenv("LANGSMITH_API_KEY") and "LANGSMITH_TRACING" not in os.environ:
    os.environ["LANGSMITH_TRACING"] = "true"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.config import ConfigurationError, Settings
from src.core.errors import FinanceAssistantError
from src.core.logging_config import configure_logging
from src.data.database import AccountError, Database
from src.data.market_data import MarketDataProvider
from src.data.news_data import NewsProvider
from src.data.web_search import TavilySearchProvider
from src.rag.knowledge_base import open_or_create_vector_store
from src.utils.input_validation import build_goal_planning_question, validate_question
from src.workflow.graph import build_workflow, to_langchain_messages

configure_logging()
logger = logging.getLogger(__name__)

AGENT_LABELS = {
    "finance_qa": "Finance Q&A",
    "portfolio_analysis": "Portfolio analysis",
    "market_analysis": "Market analysis",
    "goal_planning": "Goal planning",
    "news_synthesizer": "News synthesis",
    "tax_education": "Tax education",
}
_ANSWER_CACHE_TTL_SECONDS = 15 * 60
_ANSWER_CACHE_MAX_ENTRIES = 256
_ANSWER_CACHE: OrderedDict[
    tuple[str, int, str, str], tuple[float, dict]
] = OrderedDict()
_ANSWER_CACHE_LOCK = threading.Lock()
_DYNAMIC_QUESTION_RE = re.compile(
    r"\b(?:current(?:ly)?|latest|recent|today|yesterday|tomorrow|"
    r"right now|news|headlines?|stock price|share price|quote|"
    r"market snapshot|market update|market performance)\b",
    re.IGNORECASE,
)
_FOLLOW_UP_QUESTION_RE = re.compile(
    r"\b(?:it|that|these|those|them|they|above|previous|earlier|"
    r"same|instead|also|what about|how about|based on|as mentioned|"
    r"continue|follow[- ]?up)\b",
    re.IGNORECASE,
)


class RegisterRequest(BaseModel):
    username: str = Field(max_length=32)
    password: str = Field(min_length=12, max_length=128)
    confirmation: str = Field(max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(max_length=32)
    password: str = Field(max_length=1024)


class ProfileRequest(BaseModel):
    learning_level: Literal["Beginner", "Intermediate", "Advanced"]
    goal: str = Field(max_length=300)
    time_horizon: str = Field(max_length=120)
    risk_comfort: Literal["Not specified", "Low", "Moderate", "High"]


class ChatRequest(BaseModel):
    question: str


class GoalRequest(BaseModel):
    goal: str
    time_horizon: str = ""
    target_amount: str = ""
    current_savings: str = Field(default="", max_length=32)
    monthly_contribution: str = Field(default="", max_length=32)


class PortfolioHoldingInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    asset_class: Literal["Stocks", "Bonds", "Cash", "Real estate", "Other"]
    sector: Literal[
        "Technology",
        "Healthcare",
        "Financials",
        "Consumer discretionary",
        "Consumer staples",
        "Industrials",
        "Energy",
        "Materials",
        "Utilities",
        "Communication services",
        "Real estate",
        "Diversified / not applicable",
    ]
    market_value: float = Field(
        gt=0, le=1_000_000_000_000, allow_inf_nan=False
    )

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Holding name cannot be blank.")
        return normalized


class PortfolioRequest(BaseModel):
    holdings: list[PortfolioHoldingInput] = Field(max_length=100)


@lru_cache
def get_settings() -> Settings:
    return Settings.load(ROOT / "config.yaml")


@lru_cache
def get_database() -> Database:
    return Database(get_settings().database_url)


@lru_cache
def get_vector_store():
    settings = get_settings()
    return open_or_create_vector_store(
        settings.knowledge_base_path,
        settings.chroma_path,
        settings.embedding_model,
    )


def _build_chat_model(settings: Settings):
    from langchain_openai import ChatOpenAI

    primary = ChatOpenAI(
        model=settings.model,
        temperature=settings.temperature,
        timeout=30,
        max_retries=2,
    )
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        return primary

    from langchain_google_genai import ChatGoogleGenerativeAI

    fallback = ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        api_key=gemini_api_key,
        temperature=settings.temperature,
        max_retries=2,
    )
    logger.info(
        "Gemini chat fallback enabled with model %s",
        os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    )
    return primary.with_fallbacks([fallback], exceptions_to_handle=(Exception,))


@lru_cache
def get_workflow():
    if not os.getenv("OPENAI_API_KEY"):
        raise ConfigurationError("Set OPENAI_API_KEY in the environment before using the assistant.")

    settings = get_settings()
    return build_workflow(
        llm=_build_chat_model(settings),
        vector_store=get_vector_store(),
        market_provider=MarketDataProvider(settings.history_period),
        news_provider=NewsProvider(
            settings.news_feed_url,
            settings.news_max_items,
            alpha_vantage_api_key=os.getenv("ALPHA_VANTAGE_API_KEY"),
        ),
        web_search_provider=TavilySearchProvider(),
    )


def _user_id(request: Request) -> int:
    user_id = request.session.get("user_id")
    if not isinstance(user_id, int):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue.")
    return user_id


def _admin_user_id(request: Request) -> int:
    user_id = _user_id(request)
    try:
        role = get_database().get_role(user_id)
    except AccountError as exc:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to continue.",
        ) from exc
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access is required.",
        )
    return user_id


def _session_payload(request: Request) -> dict:
    user_id = request.session.get("user_id")
    if not isinstance(user_id, int):
        return {"authenticated": False}
    try:
        database = get_database()
        return {
            "authenticated": True,
            "username": database.get_username(user_id),
            "role": database.get_role(user_id),
            "profile": database.get_profile(user_id),
            "history": database.recent_messages(
                user_id, get_settings().max_history_messages
            ),
        }
    except AccountError:
        request.session.clear()
        return {"authenticated": False}


app = FastAPI(title="AI Finance Assistant API")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET") or os.urandom(32).hex(),
    session_cookie="finance_session",
    same_site="lax",
    https_only=os.getenv("COOKIE_SECURE", "false").lower() == "true",
    max_age=60 * 60 * 24 * 7,
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/session")
def read_session(request: Request) -> dict:
    return _session_payload(request)


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request) -> dict:
    if payload.password != payload.confirmation:
        raise HTTPException(status_code=400, detail="The passwords do not match.")
    try:
        user_id = get_database().register(payload.username, payload.password)
    except AccountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    request.session.clear()
    request.session["user_id"] = user_id
    return _session_payload(request)


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request) -> dict:
    user_id = get_database().authenticate(payload.username, payload.password)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Username or password is incorrect.")
    request.session.clear()
    request.session["user_id"] = user_id
    return _session_payload(request)


@app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> None:
    request.session.clear()


@app.delete("/api/chat/history", status_code=status.HTTP_204_NO_CONTENT)
def clear_chat_history(request: Request) -> None:
    user_id = _user_id(request)
    get_database().clear_messages(user_id)
    _clear_cached_answers(user_id)


@app.patch("/api/profile")
def save_profile(payload: ProfileRequest, request: Request) -> dict:
    user_id = _user_id(request)
    try:
        get_database().save_profile(user_id, payload.model_dump())
    except AccountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"profile": get_database().get_profile(user_id)}


@app.get("/api/admin/profiles")
def read_all_profiles(request: Request) -> dict:
    _admin_user_id(request)
    return {"profiles": get_database().list_user_profiles()}


@app.get("/api/portfolio")
def read_portfolio(request: Request) -> dict:
    user_id = _user_id(request)
    return {"holdings": get_database().get_portfolio(user_id)}


@app.put("/api/portfolio")
def save_portfolio(payload: PortfolioRequest, request: Request) -> dict:
    user_id = _user_id(request)
    try:
        holdings = get_database().replace_portfolio(
            user_id,
            [holding.model_dump() for holding in payload.holdings],
        )
    except AccountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"holdings": holdings}


@app.post("/api/chat")
def chat(payload: ChatRequest, request: Request) -> dict:
    user_id = _user_id(request)
    return _process_question(user_id, payload.question)


@app.post("/api/chat/stream")
def chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    user_id = _user_id(request)
    question, workflow_input = _prepare_question(user_id, payload.question)
    return _question_stream_response(user_id, question, workflow_input)


@app.post("/api/goal")
def plan_goal(payload: GoalRequest, request: Request) -> dict:
    user_id = _user_id(request)
    try:
        question = build_goal_planning_question(
            payload.goal,
            payload.time_horizon,
            payload.target_amount,
            payload.current_savings,
            payload.monthly_contribution,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _process_question(user_id, question)


@app.post("/api/goal/stream")
def plan_goal_stream(payload: GoalRequest, request: Request) -> StreamingResponse:
    user_id = _user_id(request)
    try:
        question = build_goal_planning_question(
            payload.goal,
            payload.time_horizon,
            payload.target_amount,
            payload.current_savings,
            payload.monthly_contribution,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    question, workflow_input = _prepare_question(user_id, question)
    return _question_stream_response(user_id, question, workflow_input)


def _retrieval_debug_fields(result: dict) -> dict[str, list[str]]:
    if os.getenv("SHOW_RETRIEVAL_METADATA", "").lower() != "true":
        return {}
    return {"retrieval_filter": result.get("retrieval_filter", [])}


def _answer_cache_key(
    user_id: int,
    question: str,
    profile_context: str,
    database: Database,
) -> tuple[str, int, str, str] | None:
    if _DYNAMIC_QUESTION_RE.search(question) or _FOLLOW_UP_QUESTION_RE.search(question):
        return None
    normalized_question = " ".join(question.split()).casefold()
    database_key = database.engine.url.render_as_string(hide_password=True)
    return (database_key, user_id, normalized_question, profile_context)


def _get_cached_answer(
    user_id: int,
    question: str,
    profile_context: str,
    database: Database,
) -> dict | None:
    key = _answer_cache_key(user_id, question, profile_context, database)
    if key is None:
        return None
    now = time.monotonic()
    with _ANSWER_CACHE_LOCK:
        cached = _ANSWER_CACHE.get(key)
        if cached is None:
            return None
        expires_at, response = cached
        if now >= expires_at:
            del _ANSWER_CACHE[key]
            return None
        _ANSWER_CACHE.move_to_end(key)
        return deepcopy(response)


def _cache_answer(
    user_id: int,
    question: str,
    profile_context: str,
    database: Database,
    response: dict,
) -> None:
    key = _answer_cache_key(user_id, question, profile_context, database)
    if key is None:
        return
    with _ANSWER_CACHE_LOCK:
        _ANSWER_CACHE[key] = (
            time.monotonic() + _ANSWER_CACHE_TTL_SECONDS,
            deepcopy(response),
        )
        _ANSWER_CACHE.move_to_end(key)
        while len(_ANSWER_CACHE) > _ANSWER_CACHE_MAX_ENTRIES:
            _ANSWER_CACHE.popitem(last=False)


def _clear_cached_answers(user_id: int) -> None:
    with _ANSWER_CACHE_LOCK:
        for key in [key for key in _ANSWER_CACHE if key[1] == user_id]:
            del _ANSWER_CACHE[key]


def _prepare_question(user_id: int, unvalidated_question: str) -> tuple[str, dict]:
    try:
        question = validate_question(
            unvalidated_question, get_settings().max_input_characters
        )
        database = get_database()
        history = database.recent_messages(
            user_id, get_settings().max_history_messages
        )
        profile = database.get_profile(user_id)
        context_profile = (
            f"Learning level: {profile['learning_level']}; "
            f"goal: {profile['goal'] or 'not supplied'}; "
            f"time horizon: {profile['time_horizon'] or 'not supplied'}; "
            f"self-described risk comfort: {profile['risk_comfort'] or 'not supplied'}."
        )
        return question, {
            "question": question,
            "profile": context_profile,
            "history": to_langchain_messages(history),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AccountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except FinanceAssistantError as exc:
        logger.warning("Assistant request could not be prepared: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected failure preparing assistant request")
        raise HTTPException(
            status_code=500,
            detail="The assistant could not complete this request. Please try again later.",
        ) from exc


def _question_stream_response(
    user_id: int,
    question: str,
    workflow_input: dict,
) -> StreamingResponse:
    return StreamingResponse(
        _stream_question(user_id, question, workflow_input),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


def _stream_question(user_id: int, question: str, workflow_input: dict):
    try:
        database = get_database()
        profile_context = workflow_input["profile"]
        cached = _get_cached_answer(
            user_id,
            question,
            profile_context,
            database,
        )
        if cached is not None:
            logger.info("Reusing cached assistant answer.")
            answer = str(cached["answer"])
            database.save_message(user_id, "user", question)
            database.save_message(
                user_id, "assistant", answer, cached.get("market_chart")
            )
            yield _sse_event("token", {"content": answer})
            yield _sse_event(
                "done",
                {
                    **cached,
                    "question": question,
                    **_retrieval_debug_fields(cached),
                },
            )
            return

        final_result = None
        selected_agents: list[str] = []
        for mode, chunk in get_workflow().stream(
            workflow_input,
            stream_mode=["messages", "updates"],
        ):
            if mode == "updates":
                for node_name, update in chunk.items():
                    if node_name == "router":
                        selected_agents = update.get("agents", [])
                    elif isinstance(update, dict) and "answer" in update:
                        final_result = update
            elif mode == "messages":
                message, metadata = chunk
                node_name = metadata.get("langgraph_node")
                should_stream = (
                    len(selected_agents) > 1 and node_name == "synthesize"
                ) or (
                    len(selected_agents) == 1
                    and node_name == selected_agents[0]
                )
                if should_stream:
                    content = message.content
                    if isinstance(content, str) and content:
                        yield _sse_event("token", {"content": content})

        if final_result is None:
            raise RuntimeError("The workflow stream ended without a final answer.")
        answer = str(final_result["answer"])
        database.save_message(user_id, "user", question)
        market_chart = final_result.get("market_chart")
        database.save_message(user_id, "assistant", answer, market_chart)
        agents = final_result.get("agents", [final_result["agent"]])
        response = {
            "question": question,
            "answer": answer,
            "sources": final_result.get("sources", []),
            "citations": final_result.get("citations", []),
            **_retrieval_debug_fields(final_result),
            "agent": final_result["agent"],
            "agent_label": " + ".join(
                AGENT_LABELS.get(agent_name, agent_name) for agent_name in agents
            ),
        }
        if market_chart is not None:
            response["market_chart"] = market_chart
        _cache_answer(
            user_id,
            question,
            workflow_input["profile"],
            database,
            response,
        )
        yield _sse_event("done", response)
    except HTTPException as exc:
        yield _sse_event("error", {"detail": str(exc.detail)})
    except AccountError as exc:
        yield _sse_event("error", {"detail": str(exc)})
    except FinanceAssistantError as exc:
        logger.warning("Streaming assistant request failed: %s", exc)
        yield _sse_event("error", {"detail": str(exc)})
    except Exception:
        logger.exception("Unexpected streaming assistant request failure")
        yield _sse_event(
            "error",
            {
                "detail": (
                    "The assistant could not complete this request. Please try again later."
                )
            },
        )


def _sse_event(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def _process_question(user_id: int, unvalidated_question: str) -> dict:
    try:
        question = validate_question(
            unvalidated_question, get_settings().max_input_characters
        )
        history = get_database().recent_messages(
            user_id, get_settings().max_history_messages
        )
        database = get_database()
        profile = database.get_profile(user_id)
        context_profile = (
            f"Learning level: {profile['learning_level']}; "
            f"goal: {profile['goal'] or 'not supplied'}; "
            f"time horizon: {profile['time_horizon'] or 'not supplied'}; "
            f"self-described risk comfort: {profile['risk_comfort'] or 'not supplied'}."
        )
        cached = _get_cached_answer(
            user_id,
            question,
            context_profile,
            database,
        )
        if cached is not None:
            logger.info("Reusing cached assistant answer.")
            database.save_message(user_id, "user", question)
            database.save_message(
                user_id,
                "assistant",
                str(cached["answer"]),
                cached.get("market_chart"),
            )
            return {**cached, "question": question, **_retrieval_debug_fields(cached)}

        result = get_workflow().invoke(
            {
                "question": question,
                "profile": context_profile,
                "history": to_langchain_messages(history),
            }
        )
        database.save_message(user_id, "user", question)
        market_chart = result.get("market_chart")
        database.save_message(
            user_id, "assistant", result["answer"], market_chart
        )
        agent = result["agent"]
        agents = result.get("agents", [agent])
        response = {
            "question": question,
            "answer": result["answer"],
            "sources": result.get("sources", []),
            "citations": result.get("citations", []),
            **_retrieval_debug_fields(result),
            "agent": agent,
            "agent_label": " + ".join(
                AGENT_LABELS.get(agent_name, agent_name) for agent_name in agents
            ),
        }
        if market_chart is not None:
            response["market_chart"] = market_chart
        _cache_answer(
            user_id,
            question,
            context_profile,
            database,
            response,
        )
        return response
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AccountError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except FinanceAssistantError as exc:
        logger.warning("Assistant request could not be completed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected assistant request failure")
        raise HTTPException(
            status_code=500,
            detail="The assistant could not complete this request. Please try again later.",
        ) from exc


frontend_dist = ROOT / "frontend" / "dist"
app.mount(
    "/assets",
    StaticFiles(directory=frontend_dist / "assets", check_dir=False),
    name="assets",
)


@app.get("/{path:path}", include_in_schema=False)
def serve_frontend(path: str):
    index = frontend_dist / "index.html"
    if not index.is_file():
        raise HTTPException(
            status_code=404,
            detail="Frontend is not built. Run `npm run build` in the frontend directory.",
        )
    return FileResponse(index)
