import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  ArrowLeft,
  BookOpen,
  ChevronDown,
  CircleHelp,
  ExternalLink,
  FileCode2,
  LifeBuoy,
  Server,
  Settings,
  ShieldCheck,
  Workflow,
} from "lucide-react";

export type DocumentationSection =
  | "overview"
  | "architecture"
  | "setup"
  | "api"
  | "usage"
  | "troubleshooting"
  | "operations";

type DocumentationPageProps = {
  target: DocumentationSection;
  onNavigate: (section: DocumentationSection) => void;
  onBack: () => void;
  publicPage?: boolean;
};

const documentationLinks: {
  id: DocumentationSection;
  label: string;
  description: string;
  icon: typeof BookOpen;
}[] = [
  { id: "overview", label: "Documentation overview", description: "Start here", icon: BookOpen },
  { id: "architecture", label: "Architecture", description: "Components and request flow", icon: Workflow },
  { id: "setup", label: "Setup and deployment", description: "Local, Docker, and AWS", icon: Settings },
  { id: "api", label: "API reference", description: "Routes, payloads, and streaming", icon: FileCode2 },
  { id: "usage", label: "Usage examples", description: "Learn and plan with Finch", icon: Server },
  { id: "troubleshooting", label: "Troubleshooting", description: "Diagnose common failures", icon: LifeBuoy },
  { id: "operations", label: "Production operations", description: "Security and reliability checklist", icon: ShieldCheck },
];

export function DocumentationMenu({
  onSelect,
}: {
  onSelect: (section: DocumentationSection) => void;
}) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (event.target instanceof Node && !menuRef.current?.contains(event.target)) {
        setOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="documentation-menu" ref={menuRef}>
      <button
        className="documentation-menu-trigger"
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <BookOpen size={15} />
        <span>Documentation</span>
        <ChevronDown size={14} className={open ? "documentation-chevron open" : "documentation-chevron"} />
      </button>
      {open && (
        <nav className="documentation-menu-panel" aria-label="Documentation" role="menu">
          {documentationLinks.map(({ id, label, description, icon: Icon }) => (
            <button
              key={id}
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onSelect(id);
              }}
            >
              <span className="documentation-menu-icon"><Icon size={16} /></span>
              <span className="documentation-menu-copy">
                <strong>{label}</strong>
                <small>{description}</small>
              </span>
            </button>
          ))}
        </nav>
      )}
    </div>
  );
}

function DocSection({
  id,
  eyebrow,
  title,
  children,
}: {
  id: DocumentationSection;
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="documentation-section" id={`docs-${id}`}>
      <div className="documentation-eyebrow">{eyebrow}</div>
      <h2>{title}</h2>
      {children}
    </section>
  );
}

function DocTable({
  headers,
  rows,
}: {
  headers: string[];
  rows: ReactNode[][];
}) {
  return (
    <div className="documentation-table-wrap">
      <table className="documentation-table">
        <thead><tr>{headers.map((header) => <th key={header} scope="col">{header}</th>)}</tr></thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function DocumentationPage({
  target,
  onNavigate,
  onBack,
  publicPage = false,
}: DocumentationPageProps) {
  useEffect(() => {
    const section = document.getElementById(`docs-${target}`);
    section?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [target]);

  const jumpTo = (section: DocumentationSection) => {
    onNavigate(section);
    document.getElementById(`docs-${section}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className={publicPage ? "documentation-page public-documentation" : "documentation-page"}>
      <div className="documentation-heading">
        <div>
          <div className="documentation-eyebrow"><BookOpen size={14} /> FINCH PRODUCT & OPERATIONS GUIDE</div>
          <h1>How Finch works.</h1>
          <p>Product, API, deployment, and operational documentation for this application.</p>
        </div>
        <button type="button" className="documentation-back" onClick={onBack}>
          <ArrowLeft size={15} /> {publicPage ? "Back to sign in" : "Back to workspace"}
        </button>
      </div>

      <div className="documentation-layout">
        <nav className="documentation-toc" aria-label="On this page">
          <strong>ON THIS PAGE</strong>
          {documentationLinks.map(({ id, label, icon: Icon }) => (
            <button key={id} type="button" className={target === id ? "selected" : ""} onClick={() => jumpTo(id)}>
              <Icon size={15} /> {label}
            </button>
          ))}
        </nav>

        <article className="documentation-content">
          <DocSection id="overview" eyebrow="START HERE" title="What this application is">
            <p>
              Finch is a financial education application. A React and TypeScript browser interface
              communicates with a Python FastAPI service. The API manages signed-in sessions,
              user profiles, conversation history, and manually entered portfolio holdings, and
              calls a LangGraph workflow for educational answers.
            </p>
            <div className="documentation-callout">
              <ShieldCheck size={18} />
              <p><strong>Educational use only.</strong> Finch is not a financial, investment, tax,
                or legal adviser. It does not execute trades, connect to brokerage accounts,
                determine suitability, or guarantee that generated information is complete or current.</p>
            </div>
            <DocTable
              headers={["Topic", "What you will find"]}
              rows={[
                [<a href="#docs-architecture">Architecture</a>, "How browser, API, database, AI workflow, and external providers fit together."],
                [<a href="#docs-setup">Setup and deployment</a>, "Local development, Docker, AWS/EC2 networking, configuration, and storage."],
                [<a href="#docs-api">API reference</a>, "HTTP endpoints, authentication expectations, payload examples, and streaming events."],
                [<a href="#docs-usage">Usage examples</a>, "Account, learning profile, chat, goal, market, and portfolio workflows."],
                [<a href="#docs-troubleshooting">Troubleshooting</a>, "Common startup, API, database, model, and browser symptoms."],
                [<a href="#docs-operations">Production operations</a>, "Security, deployment, monitoring, backup, and release considerations."],
              ]}
            />
            <p className="documentation-note">The running application and its source code are the authority for exact behavior. External provider availability and model output can change.</p>
          </DocSection>

          <DocSection id="architecture" eyebrow="SYSTEM DESIGN" title="Architecture and request flow">
            <p>
              In local development, Vite serves the React development UI on port 5173 and proxies
              <code>/api</code> requests to FastAPI on port 8000. In the production Docker image,
              Node builds the React files during the image build; the final Python image includes
              those static files and starts Uvicorn. Node and the Vite development server are not
              running in the production container.
            </p>
            <div className="documentation-diagram" role="img" aria-label="Browser React UI to FastAPI, session and database, LangGraph specialists, retrieval and external data providers">
              <div className="diagram-row"><span>Customer browser</span><b>HTTPS</b><span>React UI (built static files)</span></div>
              <div className="diagram-down">↓ same-origin requests</div>
              <div className="diagram-row"><span>Uvicorn</span><b>ASGI</b><span>FastAPI routes and signed session cookie</span></div>
              <div className="diagram-branches">
                <div><strong>Application data</strong><span>PostgreSQL in deployment</span><span>SQLite for local development</span></div>
                <div><strong>LangGraph workflow</strong><span>Router → specialist(s) → optional synthesis</span><span>Chroma retrieval for knowledge-based questions</span></div>
                <div><strong>Optional providers</strong><span>OpenAI / Gemini fallback</span><span>yfinance / Tavily / RSS</span></div>
              </div>
              <p>Docker build only: Node + Vite → <code>frontend/dist</code> → copied into the Python runtime image</p>
            </div>
            <h3>Typical chat request</h3>
            <ol>
              <li>The browser sends a same-origin request with its session cookie.</li>
              <li>FastAPI requires an authenticated user, validates the question, and loads the user's saved profile and recent history.</li>
              <li>The LangGraph router selects one or two of the six specialists: finance Q&amp;A, portfolio analysis, market analysis, goal planning, news synthesis, or tax education.</li>
              <li>Relevant requests retrieve curated educational references from Chroma. Market or current-news requests may consult external data providers.</li>
              <li>If two specialists are selected, the workflow synthesizes their drafts. The API returns the answer, source metadata, specialist label, and optional market chart.</li>
              <li>The completed question and answer are saved to the user's conversation history. Streaming routes send answer tokens as Server-Sent Events.</li>
            </ol>
            <h3>Runtime boundaries</h3>
            <DocTable
              headers={["Component", "Responsibility", "Where it runs"]}
              rows={[
                ["React / Vite", "User interface; Vite is used only for local development and frontend builds.", "Browser static files; build stage in Docker."],
                ["Uvicorn / FastAPI", "HTTP server, API routes, cookie sessions, static frontend serving.", "Python process in the runtime container."],
                ["LangGraph", "Question routing, specialist workflows, optional synthesis.", "Inside the Python API process."],
                ["SQL database", "Accounts, profiles, chat history, portfolio holdings.", "SQLite locally; PostgreSQL recommended for production."],
                ["Chroma", "Local vector index for curated educational knowledge articles.", "Persistent data directory; multi-instance caveat in operations."],
              ]}
            />
          </DocSection>

          <DocSection id="setup" eyebrow="INSTALL & DEPLOY" title="Setup and deployment">
            <h3>Local development prerequisites</h3>
            <ul>
              <li>Python 3.10 or later (the Docker runtime uses Python 3.12).</li>
              <li>Node.js and npm for the React development server and production frontend build.</li>
              <li>An OpenAI API key for chat and embeddings. Optional integrations need their own provider keys.</li>
            </ul>
            <h3>Windows PowerShell: first-time setup</h3>
            <pre><code>{`py -3.11 -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
npm --prefix frontend install`}</code></pre>
            <p>Edit <code>.env</code> and set at least <code>OPENAI_API_KEY</code>. Set a private persistent
              <code>SESSION_SECRET</code> so sessions survive restarts. Never commit <code>.env</code> or put
              secrets in <code>config.yaml</code>.</p>
            <h3>Run local development servers</h3>
            <p>Use two terminals from the repository root. Start the API:</p>
            <pre><code>{`.\\.venv\\Scripts\\python.exe -m uvicorn src.web_app.api:app --reload`}</code></pre>
            <p>Then start Vite:</p>
            <pre><code>{`npm --prefix frontend run dev`}</code></pre>
            <p>Open <code>http://127.0.0.1:5173</code>. Vite proxies <code>/api</code> to the API at
              <code>http://127.0.0.1:8000</code>. You can instead build the UI with
              <code>npm --prefix frontend run build</code> and have FastAPI serve it on port 8000.</p>
            <h3>Build and run the production Docker image</h3>
            <p>Run commands from the repository root, where the Dockerfile is located:</p>
            <pre><code>{`docker build -t ai-finance-assistant .
docker run --name ai-finance-assistant --env-file .env \\
  -p 8000:8000 \\
  -v finance-assistant-data:/app/data \\
  ai-finance-assistant`}</code></pre>
            <p>Visit <code>http://localhost:8000</code>. The port mapping publishes container port 8000
              on the Docker host. <code>EXPOSE 8000</code> documents the container port but does not publish
              it by itself. The named volume preserves files under <code>/app/data</code> if you replace the container.</p>
            <h3>Deploying on one EC2 instance</h3>
            <ol>
              <li>Install Docker on the EC2 host and deploy the built image. EC2 is the virtual machine; the container is a separate process environment running on that machine.</li>
              <li>Publish the app port (for example, <code>-p 8000:8000</code>) and allow inbound traffic only as needed. For a public production website, prefer HTTPS through a load balancer or reverse proxy rather than exposing the app directly.</li>
              <li>Set the service's container port to 8000 (or set <code>PORT</code> and map that port). Uvicorn binds to <code>0.0.0.0</code> inside the container.</li>
              <li>Inject secrets through a secret manager or protected runtime environment; do not bake credentials into the image.</li>
              <li>Configure PostgreSQL, preferably a private RDS database. The default SQLite database and Chroma vector index are files under <code>/app/data</code>.</li>
              <li>Persist the data volume, configure TLS and health monitoring, and verify <code>/api/health</code> after deployment.</li>
            </ol>
            <div className="documentation-callout">
              <CircleHelp size={18} />
              <p>Multiple containers can run on one EC2 host. Each container needs an available host port, or use a reverse proxy/load balancer to route hostnames to the containers. The app container itself does not configure EC2 security groups, DNS, TLS certificates, or a reverse proxy.</p>
            </div>
            <h3>Configuration reference</h3>
            <DocTable
              headers={["Variable", "Purpose", "Required?"]}
              rows={[
                ["OPENAI_API_KEY", "OpenAI chat model and embeddings.", "Yes for assistant workflows."],
                ["SESSION_SECRET", "Signs the HTTP-only session cookie; keep stable between restarts.", "Strongly recommended; required for persistent sessions."],
                ["DATABASE_URL", "SQLAlchemy connection URL; when unset, SQLite is used.", "No locally; PostgreSQL recommended in production."],
                ["COOKIE_SECURE", "Set to true when the app is served over HTTPS.", "Production HTTPS."],
                ["PORT", "Uvicorn listen port; defaults to 8000.", "No."],
                ["GEMINI_API_KEY / GEMINI_MODEL", "Optional fallback for chat and intent classification; default model is gemini-2.5-flash.", "No."],
                ["TAVILY_API_KEY", "Optional current, company-specific news/web search.", "No."],
                ["ALPHA_VANTAGE_API_KEY", "Optional fallback for the RSS news provider.", "No."],
                ["LANGSMITH_API_KEY / LANGSMITH_TRACING", "Optional workflow tracing; review data implications before enabling.", "No."],
              ]}
            />
            <p>Non-secret defaults such as the model, local database path, Chroma path, and retrieval corpus are in <code>config.yaml</code>. <code>OPENAI_MODEL</code> can override the configured chat model. See <code>.env.example</code> for the current list of optional variables.</p>
          </DocSection>

          <DocSection id="api" eyebrow="INTEGRATION REFERENCE" title="API reference">
            <p>All application endpoints use the same origin as the web UI. Authentication is a signed session cookie
              maintained by the browser; requests made from scripts or API clients must retain cookies after login.
              JSON error responses use a <code>detail</code> field. Protected routes return 401 when not signed in;
              the administrator route returns 403 to non-admin users.</p>
            <DocTable
              headers={["Method and path", "Access", "Purpose / body"]}
              rows={[
                ["GET /api/health", "Public", "Liveness check; returns { status: \"ok\" }."],
                ["GET /api/session", "Public", "Returns authenticated state, username, role, profile, and recent history when signed in."],
                ["POST /api/auth/register", "Public", "JSON: { username, password, confirmation }. Creates and signs in an account."],
                ["POST /api/auth/login", "Public", "JSON: { username, password }. Starts a session."],
                ["POST /api/auth/logout", "Public/session", "Clears the current session; returns 204."],
                ["PATCH /api/profile", "Signed-in", "JSON profile: { learning_level, goal, time_horizon, risk_comfort }."],
                ["GET /api/admin/profiles", "Admin", "Lists user learning profiles; authorization is enforced by the API."],
                ["GET /api/portfolio", "Signed-in", "Returns the current user's manually entered holdings."],
                ["PUT /api/portfolio", "Signed-in", "Replaces holdings: { holdings: [{ name, asset_class, sector, market_value }] }."],
                ["POST /api/chat", "Signed-in", "JSON: { question }. Returns a completed answer, sources, citations, and specialist label."],
                ["POST /api/chat/stream", "Signed-in", "JSON: { question }. Streams answer tokens and completion metadata as SSE."],
                ["POST /api/goal", "Signed-in", "JSON goal fields; returns a completed educational response."],
                ["POST /api/goal/stream", "Signed-in", "JSON goal fields; streams an educational response as SSE."],
                ["DELETE /api/chat/history", "Signed-in", "Deletes this user's saved messages and cached answers; returns 204."],
              ]}
            />
            <h3>Authentication and profile examples</h3>
            <pre><code>{`# Register (cookies must be retained for later protected requests)
curl -i -c cookies.txt -H "Content-Type: application/json" \\
  -d '{"username":"learner01","password":"a-long-password-here","confirmation":"a-long-password-here"}' \\
  http://localhost:8000/api/auth/register

# Fetch the signed-in session
curl -b cookies.txt http://localhost:8000/api/session`}</code></pre>
            <p>Registration passwords must be 12–128 characters; usernames are limited to 32 characters. The application stores password hashes, not raw passwords.</p>
            <h3>Chat request and response shape</h3>
            <pre><code>{`POST /api/chat
Content-Type: application/json
Cookie: finance_session=...

{ "question": "Explain the difference between saving and investing." }

{
  "question": "...",
  "answer": "...",
  "sources": ["..."],
  "citations": [{ "article_id": "...", "title": "...", "publisher": "...", "source_url": "...", "reviewed_date": "..." }],
  "agent": "finance_qa",
  "agent_label": "Finance Q&A"
}`}</code></pre>
            <p>Market questions may also include <code>market_chart</code>. Retrieval diagnostics may include <code>retrieval_filter</code> when <code>SHOW_RETRIEVAL_METADATA=true</code>.</p>
            <h3>Streaming protocol</h3>
            <p><code>/api/chat/stream</code> and <code>/api/goal/stream</code> respond as <code>text/event-stream</code>.
              Each event contains a JSON payload in a <code>data:</code> line:</p>
            <pre><code>{`event: token
data: {"content":"The first part of the answer"}

event: done
data: {"question":"...","answer":"...","sources":[],"citations":[],"agent":"finance_qa","agent_label":"Finance Q&A"}

event: error
data: {"detail":"A readable error message"}`}</code></pre>
            <p>Token events can be followed by exactly one terminal <code>done</code> or <code>error</code> event. Clients should not treat partial tokens as a completed or persisted answer until receiving <code>done</code>.</p>
            <h3>Validation and error handling</h3>
            <DocTable
              headers={["Status", "Typical meaning"]}
              rows={[
                ["400", "Malformed or invalid input, profile/portfolio validation, or business-rule error."],
                ["401", "Endpoint requires a valid signed-in session."],
                ["403", "Authenticated account lacks administrator permission."],
                ["404", "Unknown route or frontend build not available."],
                ["502", "A workflow or external-provider failure."],
                ["503", "Required application configuration is missing or unavailable."],
              ]}
            />
            <p>The FastAPI service exposes <a href="/docs" target="_blank" rel="noreferrer">interactive OpenAPI documentation</a> at <code>/docs</code> and its schema at <code>/openapi.json</code> when available. API consumers can use the generated schema to inspect concrete request models.</p>
          </DocSection>

          <DocSection id="usage" eyebrow="USER GUIDE" title="Usage examples">
            <h3>Create an account and choose a learning profile</h3>
            <ol>
              <li>Choose <strong>Create account</strong> and register with a username and a password of at least 12 characters.</li>
              <li>Set an optional learning level, goal, time horizon, and self-described risk comfort in the sidebar.</li>
              <li>Save the profile. It is included as learning context for future questions; it is not an eligibility or suitability assessment.</li>
            </ol>
            <h3>Ask a question and inspect its sources</h3>
            <p>In <strong>Ask &amp; Learn</strong>, try: <code>What is the difference between an emergency fund and investing?</code>
              The answer identifies the specialist and may include citations to the curated knowledge base. Open conversation history to view prior messages; clear history to delete your saved conversations.</p>
            <h3>Plan a savings goal</h3>
            <p>In <strong>Goal planner</strong>, enter a goal such as emergency savings, then optionally enter a target, months available, current savings, and monthly contribution.
              The snapshot calculates progress, remaining amount, a straight-line monthly pace, and milestones. Choose <strong>Explore this goal</strong> to ask the goal-planning specialist for educational context.</p>
            <pre><code>{`Example: target $12,000; already saved $2,000; 20 months
Remaining: $10,000
Illustrative monthly pace: $10,000 / 20 = $500
Assumption: regular contributions; no interest, fees, or growth.`}</code></pre>
            <h3>Ask about market context</h3>
            <p>In <strong>Market planner</strong>, ask a concept question or request recent prices for one ticker, for example:
              <code>What is the recent price history for ticker: AAPL?</code> A chart may appear when market data is available. It shows recent closing prices, not a real-time quote, forecast, or buy/sell signal.</p>
            <h3>Explore a manually entered portfolio</h3>
            <p>The portfolio dashboard accepts holding name, asset class, sector, and market value. It presents a self-reported snapshot and visual breakdown.
              It does not connect to a brokerage, verify holdings, estimate returns, or recommend an allocation. Changes are saved for the signed-in account.</p>
            <h3>Example of a useful follow-up</h3>
            <pre><code>{`Question: What is a bond fund?
Follow-up: How might interest-rate changes affect its price?
Follow-up: Which part of that explanation is general, and which details should I verify from a primary source?`}</code></pre>
            <p>Model answers are educational and may be incorrect or incomplete. Verify important claims using the cited primary sources and qualified professionals.</p>
          </DocSection>

          <DocSection id="troubleshooting" eyebrow="DIAGNOSIS" title="Troubleshooting guide">
            <DocTable
              headers={["Symptom", "Likely cause", "What to check"]}
              rows={[
                ["Browser cannot open the app", "Server is stopped, wrong port, or host port was not published.", <>Check the terminal/container logs, <code>docker ps</code>, and the <code>-p host:container</code> mapping. In cloud, check EC2/security-group/load-balancer routing.</>],
                ["Frontend loads, API requests fail", "FastAPI is down, API route is inaccessible, or the Vite proxy target is wrong.", <>Check <code>http://127.0.0.1:8000/api/health</code>; local Vite proxies <code>/api</code> to port 8000. Inspect browser Network and API logs.</>],
                ["401 from chat/profile/portfolio", "No signed-in session cookie or cookie is no longer valid.", "Sign in again; confirm the browser retains same-origin cookies and the deployment uses a stable SESSION_SECRET."],
                ["Secure cookie is not sent over HTTP", "COOKIE_SECURE=true while using plain HTTP.", "Use HTTPS in production; only disable the secure-cookie setting for local non-HTTPS development."],
                ["Assistant reports OPENAI_API_KEY missing", "The API process/container did not receive the key.", "Check the runtime secret/environment configuration. Recreate the container after changing environment variables; never print or paste the secret into logs."],
                ["OpenAI embedding/provider error", "Invalid key, quota, network, or provider availability; retrieval depends on embeddings.", "Check provider status, key validity, billing/quota, outbound network, and API logs. Gemini fallback covers chat model calls, not OpenAI embeddings."],
                ["Chat returns 502 or provider errors", "Workflow, model, retrieval, market, or news provider failed.", "Inspect backend logs and provider status. Optional market/news data can be unavailable; do not assume unavailable data was generated."],
                ["Market chart is missing", "No unambiguous ticker, usable history unavailable, or market provider failed.", "Try one clearly named ticker; confirm yfinance/network availability. The answer may still be educational without a chart."],
                ["News results are missing", "Tavily is not configured or search/provider request failed.", "Set TAVILY_API_KEY if current company-news search is needed; inspect API logs and provider availability."],
                ["Users or history disappear after container replacement", "SQLite data volume was not mounted or persisted.", "Mount persistent storage at /app/data or configure PostgreSQL and verify the database backup/restore process."],
                ["Chroma knowledge retrieval fails", "Index files are unavailable, unwritable, or inconsistent.", "Confirm data volume permissions and configured knowledge-base paths; check logs. Reindex only after reviewing the data and backup implications."],
                ["Admin profiles returns 403", "Signed-in user is not an administrator.", <>Promote only a trusted existing account with <code>python -m src.data.manage_admin username</code> using the same database configuration.</>],
                ["UI says frontend is not built", "FastAPI is serving the production route but dist/index.html is absent.", "Run npm --prefix frontend run build, or build the Docker image from the repository root so its Node stage copies frontend/dist."],
              ]}
            />
            <h3>Useful checks</h3>
            <pre><code>{`# API health check
curl -i http://127.0.0.1:8000/api/health

# Container state and recent logs
docker ps
docker logs --tail 100 ai-finance-assistant

# Frontend production build
npm --prefix frontend run build

# Python test suite
.\\.venv\\Scripts\\python.exe -m pytest`}</code></pre>
            <p>For Docker builds, remember the final image uses Python and serves the React build itself; the frontend development server on port 5173 is not part of that production runtime.</p>
          </DocSection>

          <DocSection id="operations" eyebrow="PRODUCTION READINESS" title="Production operations and safety">
            <h3>Before exposing the app to customers</h3>
            <ul>
              <li>Terminate TLS at a managed load balancer or trusted reverse proxy; set <code>COOKIE_SECURE=true</code> behind HTTPS and correctly configure trusted proxy behavior if needed.</li>
              <li>Use PostgreSQL/RDS with private networking, encryption in transit and at rest, restricted security groups, automated backups, and tested restore procedures.</li>
              <li>Use a long, random, private, stable <code>SESSION_SECRET</code>. Store all provider keys in a managed secret store, rotate them, and do not bake them into images or expose them to the browser.</li>
              <li>Configure persistent, permission-restricted storage for the Chroma index. The current Chroma store is local to the application data directory; multiple replicas do not automatically share or coordinate it.</li>
              <li>Set resource limits, restart behavior, health checks, log collection, alerts, and a deployment rollback strategy. The Docker image runs as a non-root user and checks <code>/api/health</code>.</li>
              <li>Review retention, account deletion, privacy notices, access controls, vulnerability management, rate limiting, and legal/compliance obligations before handling real user financial information.</li>
              <li>Admin users can view all users' learning profiles. Grant administrator access only to trusted operators and document that access for users.</li>
            </ul>
            <h3>Data and availability boundaries</h3>
            <p>SQLite is the default local database and should not be used as shared storage for an autoscaling service. Chroma currently persists to local storage, so production replicas need a deliberate shared or managed vector-store plan. Docker's <code>VOLUME</code> instruction marks <code>/app/data</code> as a mount point; it does not provision durable AWS EBS storage.</p>
            <p>External model, market, and news providers can incur cost, enforce quotas, return delayed or incomplete data, or become unavailable. Gemini is an optional chat-model fallback; OpenAI embeddings remain required for the current retrieval setup. LangSmith traces may include user prompts, conversation context, retrieved documents, and generated responses—enable tracing only after reviewing data-handling requirements.</p>
            <h3>Release and recovery checklist</h3>
            <ol>
              <li>Run the Python tests and frontend production build.</li>
              <li>Build a versioned Docker image from a reviewed source revision and scan it using the organization's image security process.</li>
              <li>Deploy with injected secrets and persistent/managed data services; verify health, login, chat, and database connectivity.</li>
              <li>Monitor logs, health checks, resource usage, provider errors, and database capacity. Keep sensitive values out of logs.</li>
              <li>Back up relational data and persistent vector data as appropriate. Test restores and document recovery-time and recovery-point expectations.</li>
              <li>For rollback, redeploy the previous image while preserving compatible database and data-volume state.</li>
            </ol>
            <p className="documentation-note">
              <ExternalLink size={14} /> This is an application-level guide, not a substitute for AWS architecture review,
              security testing, financial-services compliance advice, or a deployment-specific runbook.
            </p>
          </DocSection>

          <footer className="documentation-footer">
            <span>FINCH · PRODUCT AND OPERATIONS GUIDE</span>
            <button type="button" onClick={onBack}><ArrowLeft size={14} /> {publicPage ? "Back to sign in" : "Return to Finch"}</button>
          </footer>
        </article>
      </div>
    </div>
  );
}
