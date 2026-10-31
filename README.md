# AI Finance Assistant

An educational finance assistant built with React, FastAPI, LangGraph, OpenAI
`gpt-4o-mini`, Chroma, PostgreSQL (SQLite for local development), and yfinance. It includes six specialist
workflows, retrieved educational references, optional market/news context,
conversation history, and persisted user profiles.

> **Education only:** This application is not a financial, investment, tax, or
> legal adviser. It does not provide individualized investment recommendations.
> Market data may be delayed, incomplete, or unavailable. Verify important
> information with qualified professionals and primary sources.

## Features

- Finance Q&A, portfolio education, market context, goal planning, news
  summaries, and US tax education, selected by a LangGraph router.
- Cross-domain questions can use two specialists concurrently, with one
  synthesized answer and combined source references; straightforward questions
  keep the single-specialist path.
- A visible goal-planning form in the app for starting and testing an
  educational planning conversation.
- A portfolio dashboard for manually entered holdings, with asset-class,
  sector, and position-weight visualizations. Entries are saved per account
  and are not linked to brokerage accounts.
- Chroma retrieval over the included educational corpus, with source references
  shown alongside the assistant response.
- Financial-goal guidance curated from CFPB educational resources, covering
  goal definition, cash-flow planning, emergency savings, and trade-offs.
- Knowledge articles use YAML frontmatter for stable IDs, titles, publishers,
  source URLs, review dates, jurisdiction, specialist, and topic. Retrieval
  filters by specialist and citations show article titles and publishers.
- The starter knowledge base contains 50 original summaries sourced from
  federal financial education and market-information resources, covering all
  six specialists. Tax and market details can change; each article links to
  its source for current information.
- Market snapshots via yfinance and company-specific financial-news search via Tavily.
- Accounts, hashed passwords, saved learning profile, and chat history in a
  relational database. PostgreSQL is supported for deployment; SQLite remains
  the zero-setup local development default.
- Configuration in `config.yaml`; API secrets are read from environment.
- Responsive React interface served by a FastAPI backend. The Python workflow,
  database accounts, profile, chat history, and data providers stay on the server.
- Chat and goal answers stream into the interface as the model generates them;
  JSON API endpoints remain available for non-streaming clients.

## Quick start

Requirements: Python 3.10+, Node.js 18+, npm, and an OpenAI API key.
PostgreSQL connections use SQLAlchemy and Psycopg; these dependencies are
installed from `requirements.txt`.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
npm --prefix frontend install
npm --prefix frontend run build
python -m uvicorn src.web_app.api:app --reload
```

The app is available at http://127.0.0.1:8000. For frontend development with
hot reload, run the API and Vite in separate terminals:

```powershell
python -m uvicorn src.web_app.api:app --reload
npm --prefix frontend run dev
```

The development UI is available at http://127.0.0.1:5173 and proxies API
requests to FastAPI. The API loads `.env` automatically. Copy `.env.example` to
`.env` and set `OPENAI_API_KEY`; set a private, persistent `SESSION_SECRET` to
keep signed-in sessions valid across server restarts. Optionally set
`GEMINI_API_KEY` to enable Gemini as a fallback for chat and intent
classification when OpenAI model calls fail. `GEMINI_MODEL` defaults to
`gemini-2.5-flash`. Embeddings continue to use OpenAI and are not switched or
re-created when the chat fallback runs. The local `.env` file is ignored by
Git. Never share or commit real secrets.

The Gemini fallback applies to chat-model calls, not OpenAI embedding requests.
If OpenAI embeddings are unavailable, retrieval can still fail before the chat
model is called. Review Google's API data-use terms before sending user prompts
to Gemini.

To trace LangGraph runs in LangSmith, set `LANGSMITH_API_KEY` in `.env` and
choose a `LANGSMITH_PROJECT` name. Tracing is enabled with
`LANGSMITH_TRACING=true`; the API also enables it by default when an API key is
present, unless `LANGSMITH_TRACING=false` is explicitly set. LangSmith traces
can include user questions, conversation history, profile context, retrieved
documents, and model responses. Do not enable external tracing for sensitive
user data unless you have reviewed the data-handling requirements and informed
users appropriately.

Financial-news questions use Tavily web search for recent, company-specific
results. The app adds generic financial-news context to the user's query and
uses Tavily's basic search mode for better relevance, without maintaining a
company-by-company alias list. Set `TAVILY_API_KEY` in `.env`; the news specialist includes result
URLs with its response. Tavily search failures are reported rather than
replaced with unrelated general headlines. A separate RSS provider remains
available for basic feed-based use and can optionally fall back to Alpha
Vantage when `ALPHA_VANTAGE_API_KEY` is configured. Transient external-provider
failures are retried up to three times with bounded backoff; rate limits are
surfaced without immediate retries to avoid worsening throttling.

### Admin access to learning profiles

Every new account has the `user` role and can view or update only its own
learning profile. To grant an existing account administrator access, run this
command from the project root after setting up `.env`:

```powershell
python -m src.data.manage_admin <username>
```

The command uses the configured `DATABASE_URL` (or local SQLite database) and
promotes only an existing username. Admins see an **Admin profiles** page with
all users' learning-level, goal, time-horizon, and risk-comfort fields.
Authorization is enforced by the API on every request; hiding the admin link in
the UI is not the security boundary. Grant admin access only to trusted
operators.

### MCP web-search server for Claude Desktop

The same Tavily search provider is available as a local stdio MCP server. Install
the project requirements, set `TAVILY_API_KEY` in the Claude Desktop MCP server
environment (or the process environment), then add a server entry to
`%APPDATA%\Claude\claude_desktop_config.json`. Replace the paths with your
project and Python virtual-environment paths:

```json
{
  "mcpServers": {
    "finance-web-search": {
      "command": "C:\\path\\to\\project\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\project\\src\\mcp_server.py"],
      "env": {
        "TAVILY_API_KEY": "your-tavily-api-key"
      }
    }
  }
}
```

Restart Claude Desktop after saving the configuration. The server exposes
`web_search(query, max_results, topic)`; `topic` can be `news`, `finance`, or
`general`. Results include source titles, dates, summaries, and URLs. Keep the
API key private. The app's graph calls the same
provider directly; it does not spawn an MCP subprocess for each chat request.

## Run with Docker

Build the production image from the project root:

```powershell
docker build -t ai-finance-assistant .
```

Create a `.env` file with `OPENAI_API_KEY` and a private, stable
`SESSION_SECRET`, then start the container:

```powershell
docker run --name ai-finance-assistant --env-file .env -p 8000:8000 -v finance-assistant-data:/app/data ai-finance-assistant
```

Open http://127.0.0.1:8000. The image builds the React app and serves it from
the FastAPI container; no separate Vite server is needed. The named Docker volume keeps local SQLite fallback data and Chroma outside
the replaceable container. When `DATABASE_URL` points to PostgreSQL, account
and conversation data are stored there instead. The container exposes port
`8000`, runs as a non-root user, and provides `/api/health` for health checks.

For AWS, configure the service to listen on container port `8000` and provide
`DATABASE_URL` for RDS PostgreSQL, `OPENAI_API_KEY`, a stable `SESSION_SECRET`,
and (if enabled) `GEMINI_API_KEY` and `LANGSMITH_API_KEY` through the service's
secret manager, not the image. Set `LANGSMITH_TRACING`, `LANGSMITH_PROJECT`,
and optionally `GEMINI_MODEL` as environment variables. SQLite is only the
local development default; do not use it as persistent storage for an
autoscaling AWS deployment. Chroma also currently uses local storage under
`/app/data`, so use durable storage or migrate the vector store before running
multiple tasks.

Create an account or sign in from the React UI. The Chroma collection is built
from `src\data\knowledge_base` the first time the assistant is used. It
synchronizes added, changed, and removed articles on startup by article ID and
content hash. To explicitly rebuild the complete collection, stop the API and
run this command from the project root (it replaces only the
`finance_education` collection and uses OpenAI embeddings):

```powershell
python -m src.rag.reindex_knowledge_base --yes
```

Without a
`DATABASE_URL`, local accounts and chat history use
`data\finance_assistant.sqlite3`; the vector index is stored in the configured
data directory.

## PostgreSQL and AWS RDS

The app reads the SQLAlchemy connection string from `DATABASE_URL`. For an AWS
RDS PostgreSQL database, set it in `.env` for local testing, or inject it from
AWS Secrets Manager/your deployment platform:

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/finance_assistant?sslmode=require
```

URL-encode special characters in the username or password. Keep the database
private, restrict its security group to the application, and use TLS. Do not
put real database credentials in source control or the Docker image.

To migrate the existing local SQLite accounts, password hashes, profiles, and
chat messages, first take a backup and set `DATABASE_URL` to an **empty**
PostgreSQL database, then run:

```powershell
python -m src.data.migrate_sqlite --source data\finance_assistant.sqlite3
```

The migration preserves user IDs and password hashes, so existing accounts
keep their passwords. It refuses to copy into a destination containing users,
profiles, or messages. After migration, start the app with the same
`DATABASE_URL`. Leave the old SQLite file backed up until you have verified
sign-in and chat history against PostgreSQL.

To try goal planning, use the **Start with a goal** form on the main screen.
Enter a goal (optionally include an approximate time horizon and target amount)
and select **Explore this goal**. The assistant response labels the
specialist it used. Alternatively, ask in chat, for example: “Help me think
through saving for a home over the next five years.” Keep any amounts
approximate and never enter account numbers or credentials.

To run the tests and build the frontend:

```powershell
python -m pytest
npm --prefix frontend run build
```

## Configuration

`config.yaml` contains non-secret defaults such as model name, database and
vector-store paths, and data-source settings. `OPENAI_API_KEY` is required in
`.env` or the process environment. `OPENAI_MODEL` can override the configured
chat model. Do not put secrets in `config.yaml` or commit them.

## Project layout

```text
src/
  agents/        Specialist prompts and response policy
  core/          Configuration, logging, and shared errors
  data/          Database persistence and external data providers, including Tavily search
  mcp_server.py  Local stdio MCP web-search server for Claude Desktop
  rag/           Knowledge ingestion and retrieval
  web_app/       FastAPI API and static frontend hosting
  utils/         Shared input and formatting helpers
  workflow/      LangGraph routing and specialist nodes
frontend/        React + TypeScript UI (Vite)
tests/           Unit tests for routing, persistence, and input handling
docs/            Technical design and operational limitations
```

See [docs/TECHNICAL_DESIGN.md](docs/TECHNICAL_DESIGN.md) for the architecture,
data flow, and deployment considerations.
