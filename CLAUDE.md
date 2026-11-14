# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Windows / PowerShell, run from the repo root with the `.venv` virtualenv active (`.\.venv\Scripts\Activate.ps1`).

```powershell
python -m pip install -r requirements.txt
npm --prefix frontend install

# Run: FastAPI serves the built React app at http://127.0.0.1:8000
npm --prefix frontend run build
python -m uvicorn src.web_app.api:app --reload

# Frontend hot reload: run alongside uvicorn; Vite (127.0.0.1:5173) proxies /api to :8000
npm --prefix frontend run dev

# Tests (pytest, tests/ directory)
python -m pytest
python -m pytest tests/test_workflow.py
python -m pytest tests/test_api.py::test_chat_requires_authentication

# Frontend type-check + build (there is no linter or frontend test suite)
npm --prefix frontend run build

# Ops
python -m src.data.manage_admin <username>          # promote existing user to admin
python -m src.rag.reindex_knowledge_base --yes      # full Chroma rebuild (stop the API first)
python -m src.data.migrate_sqlite --source data\finance_assistant.sqlite3   # SQLite -> empty Postgres
docker build -t ai-finance-assistant .
```

Secrets come from `.env` (see `.env.example`): `OPENAI_API_KEY` is required. `SESSION_SECRET`, `DATABASE_URL`, `TAVILY_API_KEY`, `GEMINI_API_KEY`, `LANGSMITH_API_KEY` and `ALPHA_VANTAGE_API_KEY` are optional. Non-secret defaults (model, paths, data providers) are in `config.yaml` and loaded by `src/core/config.py`.

## Architecture

An educational (not advisory) finance assistant. React SPA → FastAPI → LangGraph workflow → OpenAI, with Chroma RAG, yfinance and Tavily. `docs/TECHNICAL_DESIGN.md` has the full design.

### Backend (`src/`)

- **`web_app/api.py`** holds the whole HTTP layer: auth (cookie sessions, hashed passwords), profile, admin, portfolio, and chat/goal endpoints. It also serves `frontend/dist` through a catch-all route.
  - Dependencies are `@lru_cache` factory functions (`get_settings`, `get_database`, `get_vector_store`, `get_workflow`), not FastAPI `Depends`. Tests swap them with `monkeypatch.setattr(api, "get_database", ...)` / `get_workflow`.
  - `/api/chat` and `/api/goal` return JSON. Their `/stream` variants send Server-Sent Events, built by `_sse_event`, and the frontend reads them with `response.body.getReader()` in `App.tsx`.
  - There is a process-local, 15-minute answer cache keyed by user and profile (`_answer_cache_key`). Follow-ups and live news/market questions bypass it, and clearing history also clears that user's cache entries.
  - Admin authorization is enforced server-side (`_admin_user_id`). Hiding things in the UI is not the security boundary.
  - The chat model is OpenAI with an optional Gemini fallback (`_build_chat_model`). Embeddings are always OpenAI.
- **`workflow/graph.py`** is the LangGraph `StateGraph` (`build_workflow`), which takes injected `llm`, `vector_store`, `market_provider`, `news_provider` and `web_search_provider`:
  1. `START → router`. A regex shortcut sends news requests straight to `news_synthesizer`. Everything else goes through an LLM structured-output router that picks one or two of the six specialists: `finance_qa`, `portfolio_analysis`, `market_analysis`, `goal_planning`, `news_synthesizer`, `tax_education`.
  2. `retrieval` filters Chroma by specialist metadata. News-only requests take `skip_retrieval` instead.
  3. Each chosen specialist runs in parallel through `Send`.
  4. If two specialists ran, `synthesize` merges their answers and sources. Market chart data (`market_chart`) is carried through to the response.
- **`agents/prompts.py`** has `EDUCATION_POLICY`, a shared system prompt, plus `SPECIALIST_INSTRUCTIONS` per specialist. Adding a specialist means touching the prompts, `AGENT_NAMES`, the router prompt text and the retrieval specialist values.
- **`rag/knowledge_base.py`** indexes `src/data/knowledge_base/*.md`. Each article has YAML frontmatter (stable id, title, publisher, source URL, specialist, topic). The index syncs added, changed and removed articles on startup by id and content hash.
- **`data/`**:
  - `database.py` is SQLAlchemy Core, with SQLite (`data/finance_assistant.sqlite3`) by default or Postgres through `DATABASE_URL`. There is no migration framework: schema changes are additive `ALTER TABLE` statements in `Database.initialize()`, written for both dialects.
  - The external providers are `market_data.py` (yfinance), `web_search.py` (Tavily), `news_data.py` (RSS / Alpha Vantage) and `retry.py` (bounded retries; rate limits are not retried).
- **`mcp_server.py`** is a standalone stdio MCP server for Claude Desktop that exposes the Tavily `web_search` tool. The web app calls the provider directly, not through MCP.

### Frontend (`frontend/`, React 19 + TypeScript + Vite)

- There is no router or state library. `App.tsx` owns session, chat and goal state, and switches screens with an `activeView` state (`learn`, `portfolio`, `planning`, `market`, `admin`, `docs`). `PortfolioDashboard.tsx`, `AdminProfiles.tsx` and `Documentation.tsx` are the larger views.
- All styling is in one file, `src/styles.css`. The base rules come first, then a later block of overrides that defines the purple sidebar theme.
- **Theming:** every color in `styles.css` is a `light-dark(<light>, <dark>)` pair, and `ThemeToggle.tsx` switches between them by setting `data-theme` on `<html>`. A matching pre-paint script in `index.html` must use the same `finch-theme` localStorage key. Write any new color as a `light-dark()` pair or it will not adapt. Sidebar colors are intentionally the same in both themes.

### Deployment

The multi-stage `Dockerfile` builds the frontend and serves it from the FastAPI container on port 8000, with a `/api/health` check. SQLite and Chroma live in `/app/data`, so mount a volume. Chroma is local-disk only, so multi-instance deploys need durable storage. `tools/aws-deploy/deploy-ec2.bat` pipes `deploy-ec2.sh` over SSH to an EC2 host, which runs `git pull` and rebuilds the container.
