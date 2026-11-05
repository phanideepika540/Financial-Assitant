# Technical Design

## Purpose and scope

The MVP provides beginner-oriented financial education, not regulated
investment, tax, or legal advice. It routes a user message to one or two
specialists, retrieves relevant educational material, optionally adds market
or news context, and returns a grounded explanation.
All six requested domains are included.

## Architecture

```text
React + TypeScript UI (Ask & Learn, goal planner, market planner, portfolio dashboard)
  └─ FastAPI API with signed session cookie
       ├─ Account/profile/chat/portfolio persistence (PostgreSQL in deployment; SQLite locally)
       └─ LangGraph workflow
            ├─ Intent router
            ├─ One or two specialists (parallel when two are selected)
            │    ├─ Finance Q&A / portfolio / market / goal / news / tax
            │    ├─ Chroma retrieval over curated knowledge documents
            │    │    └─ OpenAI embeddings
            │    └─ Market/news providers and Tavily web search when relevant
            └─ Answer synthesis (only when two specialists run)
                 └─ Configured chat model (OpenAI, optional Gemini fallback)
```

Each request is classified into one or two distinct specialists. Straightforward
questions keep the single-specialist path; genuinely cross-domain questions run
their selected specialists concurrently. Chroma retrieval runs once before specialist execution for knowledge-based
questions; news-only requests skip it and use only the latest user message as
optional context, not previous assistant claims.
Each selected agent receives the same passages and source metadata when
retrieval is used. A synthesis step combines parallel specialist drafts into
one response. The LangGraph router uses the configured chat model to select from
the six allowed specialist names; invalid or duplicate structured
classifications fail rather than silently selecting an inappropriate specialist.
The market specialist includes its data provider and retrieval time. The news
specialist uses Tavily web search for current, company-specific stories and
returns result URLs and available publication dates as sources. The same
search provider is exposed through a local stdio MCP server for Claude Desktop.
The UI displays the
participating specialist names and retrieved source references alongside the
final response.
The React interface includes a guided goal-planning form; submitting it creates
an educational prompt routed to the goal-planning specialist. Responses
identify the participating specialist or specialists so routing is visible
during manual testing.

## Components and data flow

1. The user signs in or registers. Passwords are stored as salted PBKDF2-HMAC
   hashes; raw passwords are not persisted.
2. The user may save a learning level, goal, time horizon, and self-reported
   risk comfort, and manually enter portfolio holdings. Profile, holdings, and
   timestamped chat turns are stored in the configured relational database;
   recent chat turns are included in the next request and displayed with their
      local date and time. Market-chart data is stored with its assistant message
      so charts can be restored from conversation history. Existing databases add
      the nullable chart-data column during initialization.
   New accounts receive the `user` role. Existing accounts can be promoted to
   `admin` through `python -m src.data.manage_admin <username>`. Admins can read
   all users' learning profiles; regular users can access only their own
   profile. The API checks the persisted role for every admin request.
3. The LangGraph router asks the configured chat model to select one or two
   distinct specialists. Selected specialist nodes run concurrently.
4. For knowledge-based requests, the workflow queries Chroma once and shares
   the retrieved passages with each selected specialist. News-only requests
   skip that retrieval. Market/news specialists also call their configured
   external providers; the news specialist searches Tavily for up to three
   current-news results, appending generic financial-news context to the user's
   query rather than maintaining a company-by-company alias list. Tavily uses
   basic search for better company-news relevance and a bounded,
   process-local 90-second cache for repeated normalized queries.
   Transient external-provider timeouts, connection failures, and server
   errors receive at most three attempts with bounded backoff and
   `Retry-After` support. Rate limits are not immediately retried; they are
   surfaced as clear errors so the app does not worsen provider throttling.
   Provider failures are logged rather than replaced with fabricated data.
   For ticker-based market requests, yfinance closing prices are also returned
   as structured chart data; the UI shows the recent-price chart and a summary
   of the latest available close alongside the model's explanation. The chart
   is omitted if no unambiguous ticker or usable market history is available.
5. The specialist prompts ask the model to explain concepts in plain language,
   distinguish facts from uncertainty, use provided references, avoid
   individualized recommendations, and say when evidence is insufficient.
6. When two specialists ran, a synthesis node merges their drafts, preserves
   supported distinctions, and combines their source labels. A single
   specialist response skips synthesis to avoid an unnecessary model call.
7. Chat and goal responses stream specialist answer tokens to the React client
   over Server-Sent Events, followed by source metadata and any market-chart
   data when the answer is complete. The completed exchange and chart data are
   then persisted. Conversation history is collapsed by default in the UI and
   can be expanded or cleared by the signed-in user. The FastAPI server also
   keeps the JSON endpoints and serves the production Vite build. In local
   development, Vite proxies `/api` requests to FastAPI.

Session state is held in an HTTP-only, signed cookie. Set `SESSION_SECRET` to a
private stable value when sessions must survive server restarts. Enable
`COOKIE_SECURE=true` when serving over HTTPS.

## Knowledge base and citations

The initial corpus contains 50 concise, original educational summaries
covering all six specialists. Sources include CFPB, FDIC, IRS, SEC/Investor.gov,
U.S. Treasury, Federal Reserve, and BEA resources. It is not a comprehensive or
continuously updated reference. Each article records its source URL and review
date; year-sensitive tax rules, rates, procedures, and market information
should be checked at the primary source. Chroma stores document chunks and
source metadata. Retrieval does not guarantee complete coverage or factual
correctness.

Financial-goal guidance is summarized from CFPB educational resources on
goal-setting, savings, cash flow, debt tools, and emergency funds. New Markdown
articles use YAML frontmatter with a stable article ID, title, publisher,
source URL, review date, jurisdiction, specialist, and topic. Chunks preserve
these fields. Retrieval filters by the selected specialist(s), while also
including articles classified as general. Citations returned to the UI are
deduplicated by article ID and display title, publisher, and source URL.

The goal planner calculates a target-progress percentage, remaining amount,
straight-line monthly contribution, and contribution milestones from the
values entered by the user. An optional monthly contribution estimates the
number of months to reach the goal. These are arithmetic illustrations: they
assume regular contributions and no investment growth, fees, or changes in
contribution.

The Chroma collection synchronizes added, updated, and removed articles on
startup using article IDs and content hashes. To fully rebuild the collection,
stop the API and run `python -m src.rag.reindex_knowledge_base --yes`. This
replaces only the `finance_education` collection and recomputes embeddings from
the curated Markdown files.

## Configuration and local storage

`config.yaml` stores non-secret settings. API keys and `DATABASE_URL` are
supplied through the environment. The app uses PostgreSQL when `DATABASE_URL`
is set and a local SQLite file otherwise. Chroma persists its vector index
locally. Local files are not encrypted by this application. Keep them out of
source control and restrict filesystem access.

## Safety and known limitations

- The assistant is educational and does not determine suitability, execute
  trades, or calculate a user's tax liability.
- Portfolio and goal discussions are educational prompts, not personalized
  allocations or guarantees.
- Market data from yfinance is unofficial and can be delayed, inaccurate, or
  unavailable. Market charts show recent closing prices only; they are not
  real-time quotes, forecasts, or trade signals. RSS headlines are not a
  complete news feed.
- Model output and RAG citations can be incorrect or incomplete. Verify
  consequential claims with primary sources and qualified professionals.
- Local SQLite authentication is a development convenience, not a hardened
  identity system. PostgreSQL improves deployment durability but does not add
  email verification, password recovery, account lockout, or production-grade
  session management. Configure RDS encryption at rest and in transit.
- Administrator access exposes user learning levels, goals, time horizons, and
  self-described risk comfort. Grant admin roles only to trusted operators and
  explain this access in the application's privacy notice.
- Before public deployment, add a managed identity provider, encrypted managed
  database, authorization and privacy review, rate limiting, monitoring,
  retention/deletion controls, deployment secrets management, and appropriate
  legal/compliance review. Do not use real sensitive financial account data in
  this MVP.

## Configuration reference

See `config.yaml`. `OPENAI_MODEL` can override the chat model. API credentials
must remain in environment variables or a deployment secret manager.
`TAVILY_API_KEY` enables current financial-news search in the app and the
standalone Claude Desktop MCP server (`python -m src.mcp_server`). The app uses
the shared search-provider module directly; Claude Desktop starts the MCP
server over stdio.

The portfolio dashboard stores user-entered holding name, asset class, sector,
and market value in the authenticated account. It does not connect to brokerage
accounts, validate positions, estimate returns or risk, or provide investment
recommendations. Existing SQLite databases gain the portfolio table on app
startup; the SQLite-to-PostgreSQL migration also copies that table when it
exists in the source database.
