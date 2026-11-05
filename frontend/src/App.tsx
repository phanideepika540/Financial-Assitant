import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Bookmark,
  Check,
  ChevronDown,
  CircleHelp,
  Coins,
  Compass,
  Leaf,
  LoaderCircle,
  LogOut,
  MessageCircle,
  Send,
  ShieldCheck,
  Sparkles,
  TrendingUp,
  Trash2,
  UserRound,
  Users,
  WalletCards,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import AdminProfiles from "./AdminProfiles";
import PortfolioDashboard from "./PortfolioDashboard";

type Profile = {
  learning_level: "Beginner" | "Intermediate" | "Advanced";
  goal: string;
  time_horizon: string;
  risk_comfort: "Not specified" | "Low" | "Moderate" | "High";
};

type Message = {
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  chart_data?: MarketChartData | null;
  streaming?: boolean;
  sources?: string[];
  citations?: Citation[];
  agent_label?: string;
  retrieval_filter?: string[];
};

type Citation = {
  article_id: string;
  title: string;
  publisher: string;
  source_url: string;
  reviewed_date: string;
  specialist?: string;
};

type ChatResponse = {
  question: string;
  answer: string;
  sources: string[];
  citations: Citation[];
  agent: string;
  agent_label: string;
  retrieval_filter?: string[];
  market_chart?: MarketChartData | null;
};

type MarketChartData = {
  symbol: string;
  dates: string[];
  closes: number[];
  retrieved_at: string;
  provider: string;
};

type GoalRequest = {
  goal: string;
  time_horizon: string;
  target_amount: string;
  current_savings: string;
  monthly_contribution: string;
};

type Session = {
  authenticated: boolean;
  username?: string;
  role?: "user" | "admin";
  profile?: Profile;
  history?: Message[];
};

type WorkspaceView = "learn" | "planning" | "market" | "portfolio" | "admin";

const VIEW_LABELS: Record<WorkspaceView, string> = {
  learn: "Ask & Learn",
  planning: "Goal planner",
  market: "Market planner",
  portfolio: "Portfolio dashboard",
  admin: "Admin profiles",
};

const initialProfile: Profile = {
  learning_level: "Beginner",
  goal: "",
  time_horizon: "",
  risk_comfort: "Not specified",
};

function formatMessageTimestamp(timestamp?: string): string {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    credentials: "same-origin",
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null;
    throw new Error(body?.detail || "Something went wrong. Please try again.");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function streamChat(
  url: string,
  body: object,
  onToken: (content: string) => void,
): Promise<ChatResponse> {
  const response = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const errorBody = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null;
    throw new Error(errorBody?.detail || "Something went wrong. Please try again.");
  }
  if (!response.body) {
    throw new Error("Streaming is unavailable in this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: ChatResponse | null = null;

  function processEvent(block: string) {
    let eventName = "message";
    const dataLines: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
    }
    if (!dataLines.length) return;
    const payload = JSON.parse(dataLines.join("\n")) as
      | { content: string }
      | ChatResponse
      | { detail: string };
    if (eventName === "token" && "content" in payload) {
      onToken(payload.content);
    } else if (eventName === "done" && "answer" in payload) {
      result = payload;
    } else if (eventName === "error" && "detail" in payload) {
      throw new Error(payload.detail);
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        processEvent(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) processEvent(buffer);
  } finally {
    reader.releaseLock();
  }
  if (!result) {
    throw new Error("The assistant stream ended before the answer was complete.");
  }
  return result;
}

function MarketPriceChart({ data }: { data: MarketChartData }) {
  const width = 640;
  const height = 220;
  const left = 58;
  const right = 12;
  const top = 18;
  const bottom = 38;
  const values = data.closes;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || Math.max(Math.abs(max) * 0.02, 1);
  const low = min - range * 0.08;
  const high = max + range * 0.08;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const x = (index: number) =>
    left + (values.length > 1 ? (index / (values.length - 1)) * plotWidth : plotWidth / 2);
  const y = (value: number) =>
    top + ((high - value) / (high - low)) * plotHeight;
  const path = values
    .map((value, index) => `${index === 0 ? "M" : "L"} ${x(index)} ${y(value)}`)
    .join(" ");
  const labelIndices = [...new Set([0, Math.floor((data.dates.length - 1) / 2), data.dates.length - 1])];
  const formatPrice = (value: number) =>
    new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);
  const change = values.length > 1 ? values[values.length - 1] - values[0] : 0;
  const changePercent = values.length > 1 && values[0] !== 0 ? (change / values[0]) * 100 : 0;

  if (
    values.length === 0 ||
    values.length !== data.dates.length ||
    values.some((value) => !Number.isFinite(value))
  ) {
    return null;
  }

  return (
    <figure className="market-chart">
      <figcaption className="market-chart-heading">
        <span><strong>{data.symbol}</strong> recent closing prices</span>
        <span className={change >= 0 ? "market-chart-change positive" : "market-chart-change negative"}>
          {change >= 0 ? "+" : ""}{formatPrice(change)} ({changePercent >= 0 ? "+" : ""}{changePercent.toFixed(2)}%)
        </span>
      </figcaption>
      <svg
        className="market-chart-plot"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${data.symbol} recent closing prices, ranging from ${formatPrice(min)} to ${formatPrice(max)}. Change over period: ${changePercent.toFixed(2)} percent.`}
      >
        <defs>
          <linearGradient id={`market-fill-${data.symbol}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#786bc2" stopOpacity=".2" />
            <stop offset="100%" stopColor="#786bc2" stopOpacity=".01" />
          </linearGradient>
        </defs>
        {[0, 1, 2, 3].map((step) => {
          const value = high - ((high - low) * step) / 3;
          const lineY = y(value);
          return (
            <g key={step}>
              <line x1={left} x2={width - right} y1={lineY} y2={lineY} className="market-chart-grid" />
              <text x={left - 8} y={lineY + 3} textAnchor="end" className="market-chart-axis">
                {formatPrice(value)}
              </text>
            </g>
          );
        })}
        <path d={`${path} L ${x(values.length - 1)} ${height - bottom} L ${x(0)} ${height - bottom} Z`} fill={`url(#market-fill-${data.symbol})`} />
        <path d={path} className="market-chart-line" />
        {values.map((value, index) => (
          <circle key={`${data.dates[index]}-${index}`} cx={x(index)} cy={y(value)} r="3" className="market-chart-point">
            <title>{data.dates[index]}: {formatPrice(value)}</title>
          </circle>
        ))}
        {labelIndices.map((index) => (
          <text key={index} x={x(index)} y={height - 12} textAnchor={index === 0 ? "start" : index === data.dates.length - 1 ? "end" : "middle"} className="market-chart-axis">
            {data.dates[index]}
          </text>
        ))}
      </svg>
      <div className="market-chart-source">{data.provider} · Retrieved {formatMessageTimestamp(data.retrieved_at)}</div>
    </figure>
  );
}

function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeView, setActiveView] = useState<WorkspaceView>("learn");
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [messages, setMessages] = useState<Message[]>([]);
  const [historyExpanded, setHistoryExpanded] = useState(false);
  const [profile, setProfile] = useState<Profile>(initialProfile);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [clearingHistory, setClearingHistory] = useState(false);
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState("");
  const [chatError, setChatError] = useState("");
  const [historyNotice, setHistoryNotice] = useState("");
  const [profileNotice, setProfileNotice] = useState("");
  const [profileError, setProfileError] = useState("");
  const [profileOpen, setProfileOpen] = useState(true);
  const [goal, setGoal] = useState("");
  const [horizon, setHorizon] = useState("");
  const [target, setTarget] = useState("");
  const [currentSavings, setCurrentSavings] = useState("");
  const [monthlyBudget, setMonthlyBudget] = useState("");
  const [goalError, setGoalError] = useState("");
  const [showScroll, setShowScroll] = useState(false);
  const chatEnd = useRef<HTMLDivElement>(null);
  const chatArea = useRef<HTMLDivElement>(null);
  const targetAmount = Number(target);
  const monthsAvailable = Number(horizon);
  const savedAmount = currentSavings.trim() ? Number(currentSavings) : 0;
  const monthlyBudgetAmount = monthlyBudget.trim() ? Number(monthlyBudget) : null;
  const goalPlanReady =
    target.trim() !== "" &&
    horizon.trim() !== "" &&
    Number.isFinite(targetAmount) &&
    targetAmount > 0 &&
    Number.isFinite(monthsAvailable) &&
    monthsAvailable > 0 &&
    Number.isFinite(savedAmount) &&
    savedAmount >= 0 &&
    (monthlyBudgetAmount === null ||
      (Number.isFinite(monthlyBudgetAmount) && monthlyBudgetAmount >= 0));
  const remainingAmount = goalPlanReady
    ? Math.max(targetAmount - savedAmount, 0)
    : 0;
  const monthlyNeeded =
    goalPlanReady && remainingAmount > 0
      ? remainingAmount / monthsAvailable
      : 0;
  const goalProgress =
    goalPlanReady
      ? Math.min((savedAmount / targetAmount) * 100, 100)
      : 0;
  const projectedMonths =
    goalPlanReady &&
    monthlyBudgetAmount !== null &&
    monthlyBudgetAmount > 0 &&
    remainingAmount > 0
      ? Math.ceil(remainingAmount / monthlyBudgetAmount)
      : null;
  const formatCurrency = (amount: number) =>
    new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 2,
    }).format(amount);

  useEffect(() => {
    api<Session>("/api/session")
      .then((data) => {
        setSession(data);
        if (data.authenticated) {
          setProfile(data.profile ?? initialProfile);
          setMessages(data.history ?? []);
        }
      })
      .catch(() => setSession({ authenticated: false }))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  useEffect(() => {
    const area = chatArea.current;
    if (!area) return;
    const onScroll = () => setShowScroll(area.scrollHeight - area.scrollTop - area.clientHeight > 160);
    area.addEventListener("scroll", onScroll);
    return () => area.removeEventListener("scroll", onScroll);
  }, [session, messages.length]);

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthError("");
    setAuthBusy(true);
    const data = new FormData(event.currentTarget);
    const username = String(data.get("username") || "");
    const password = String(data.get("password") || "");
    try {
      const result =
        authMode === "register"
          ? await api<Session>("/api/auth/register", {
              method: "POST",
              body: JSON.stringify({
                username,
                password,
                confirmation: String(data.get("confirmation") || ""),
              }),
            })
          : await api<Session>("/api/auth/login", {
              method: "POST",
              body: JSON.stringify({ username, password }),
            });
      setSession(result);
      setProfile(result.profile ?? initialProfile);
      setMessages(result.history ?? []);
      setHistoryExpanded(false);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Unable to sign in.");
    } finally {
      setAuthBusy(false);
    }
  }

  async function signOut() {
    await api<void>("/api/auth/logout", { method: "POST" });
    setSession({ authenticated: false });
    setMessages([]);
    setProfile(initialProfile);
    setHistoryExpanded(false);
  }

  async function saveProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setProfileError("");
    setProfileNotice("");
    try {
      const result = await api<{ profile: Profile }>("/api/profile", {
        method: "PATCH",
        body: JSON.stringify(profile),
      });
      setProfile(result.profile);
      setProfileNotice("Your learning profile is saved.");
      window.setTimeout(() => setProfileNotice(""), 3200);
    } catch (error) {
      setProfileError(error instanceof Error ? error.message : "Could not save your profile.");
    }
  }

  async function clearHistory() {
    if (busy || clearingHistory) return;
    setChatError("");
    setHistoryNotice("");
    setClearingHistory(true);
    try {
      await api<void>("/api/chat/history", { method: "DELETE" });
      setMessages([]);
      setHistoryExpanded(false);
      setShowScroll(false);
      setHistoryNotice("Conversation history cleared.");
    } catch (error) {
      setChatError(error instanceof Error ? error.message : "Could not clear conversation history.");
    } finally {
      setClearingHistory(false);
    }
  }

  async function sendQuestion(text: string, goalRequest?: GoalRequest) {
    const clean = text.trim();
    if (!clean || busy) return;
    setBusy(true);
    setChatError("");
    setHistoryNotice("");
    setHistoryExpanded(true);
    const messageTimestamp = new Date().toISOString();
    setMessages((current) => [
      ...current,
      { role: "user", content: clean, created_at: messageTimestamp },
      {
        role: "assistant",
        content: "",
        created_at: messageTimestamp,
        streaming: true,
      },
    ]);
    setQuestion("");
    try {
      const result = await streamChat(
        goalRequest ? "/api/goal/stream" : "/api/chat/stream",
        goalRequest ?? { question: clean },
        (content) => {
          setMessages((current) => {
            const lastMessage = current[current.length - 1];
            if (lastMessage?.role !== "assistant" || !lastMessage.streaming) {
              return current;
            }
            return [
              ...current.slice(0, -1),
              { ...lastMessage, content: lastMessage.content + content },
            ];
          });
        },
      );
      setMessages((current) => {
        const lastMessage = current[current.length - 1];
        if (lastMessage?.role !== "assistant" || !lastMessage.streaming) {
          return current;
        }
        return [
          ...current.slice(0, -1),
          {
            ...lastMessage,
            content: result.answer,
            created_at: new Date().toISOString(),
            streaming: false,
            sources: result.sources,
            citations: result.citations,
            agent_label: result.agent_label,
            retrieval_filter: result.retrieval_filter,
            chart_data: result.market_chart,
          },
        ];
      });
    } catch (error) {
      setChatError(error instanceof Error ? error.message : "The assistant could not reply.");
      setMessages((current) => {
        const lastMessage = current[current.length - 1];
        if (lastMessage?.role !== "assistant" || !lastMessage.streaming) {
          return current;
        }
        if (!lastMessage.content) return current.slice(0, -1);
        return [
          ...current.slice(0, -1),
          { ...lastMessage, streaming: false },
        ];
      });
    } finally {
      setBusy(false);
    }
  }

  function submitChat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendQuestion(question);
  }

  function submitGoal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setGoalError("");
    const description = goal.trim();
    if (!description) {
      setGoalError("Add a goal to start a planning conversation.");
      return;
    }
    const summary = [
      `Help me think through: ${description}`,
      horizon.trim() ? `Time horizon: ${horizon.trim()} months` : "",
      target.trim() ? `Target amount: ${target.trim()}` : "",
      currentSavings.trim() ? `Already saved: $${currentSavings.trim()}` : "",
      monthlyBudget.trim() ? `Possible monthly contribution: $${monthlyBudget.trim()}` : "",
    ].filter(Boolean).join(" · ");
    void sendQuestion(summary, {
      goal: description,
      time_horizon: horizon.trim() ? `${horizon.trim()} months` : "",
      target_amount: target.trim(),
      current_savings: currentSavings.trim(),
      monthly_contribution: monthlyBudget.trim(),
    });
  }

  if (loading) {
    return (
      <div className="loading-screen">
        <div className="loading-brand"><Leaf size={19} /> finance, made clearer</div>
        <LoaderCircle className="spin" size={22} />
      </div>
    );
  }

  if (!session?.authenticated) {
    return (
      <main className="auth-page">
        <div className="auth-ambient ambient-one" />
        <div className="auth-ambient ambient-two" />
        <header className="auth-topbar">
          <a className="brand-lockup" href="/">
            <span className="brand-icon"><Leaf size={19} strokeWidth={2.2} /></span>
            <span>finch<span className="brand-period">.</span></span>
          </a>
          <span className="topbar-note"><ShieldCheck size={14} /> Your learning space</span>
        </header>
        <div className="auth-layout">
          <section className="auth-intro">
            <div className="eyebrow"><span className="eyebrow-line" /> A calmer way to get money-smart</div>
            <h1>Make sense of<br />your money<span className="serif-accent">,</span><br /><span className="serif-accent">one question at a time.</span></h1>
            <p>Clear, thoughtful financial education for wherever you are in your journey.</p>
            <div className="auth-points">
              <span><span className="point-icon"><Compass size={16} /></span> Learn at your own pace</span>
              <span><span className="point-icon"><Bookmark size={16} /></span> Keep your conversations close</span>
              <span><span className="point-icon"><ShieldCheck size={16} /></span> Grounded in trusted sources</span>
            </div>
            <div className="auth-quote">
              <span className="quote-mark">“</span>
              <p>Understanding your options is the first step to feeling confident.</p>
              <span className="quote-caption">YOUR FINANCIAL LEARNING COMPANION</span>
            </div>
          </section>
          <section className="auth-card">
            <span className="card-overline">{authMode === "login" ? "WELCOME BACK" : "YOUR NEXT CHAPTER"}</span>
            <h2>{authMode === "login" ? "Pick up where you left off." : "Create your learning space."}</h2>
            <p className="auth-card-copy">{authMode === "login" ? "Sign in to continue your financial learning journey." : "A few details and you're ready to explore."}</p>
            <div className="auth-switch" role="tablist" aria-label="Account action">
              <button type="button" className={authMode === "login" ? "selected" : ""} onClick={() => { setAuthMode("login"); setAuthError(""); }}>Sign in</button>
              <button type="button" className={authMode === "register" ? "selected" : ""} onClick={() => { setAuthMode("register"); setAuthError(""); }}>Create account</button>
            </div>
            <form className="auth-form" onSubmit={submitAuth}>
              <label>Username
                <input name="username" autoComplete="username" minLength={3} maxLength={32} placeholder="Your username" required />
              </label>
              <label>Password
                <input name="password" type="password" autoComplete={authMode === "login" ? "current-password" : "new-password"} minLength={authMode === "register" ? 12 : 1} placeholder={authMode === "register" ? "At least 12 characters" : "Your password"} required />
              </label>
              {authMode === "register" && (
                <label>Confirm password
                  <input name="confirmation" type="password" autoComplete="new-password" minLength={12} placeholder="Enter your password again" required />
                </label>
              )}
              {authError && <p className="inline-error" role="alert">{authError}</p>}
              <button className="primary-button auth-submit" disabled={authBusy} type="submit">
                {authBusy ? <LoaderCircle className="spin" size={17} /> : null}
                {authMode === "login" ? "Sign in to your space" : "Create my account"}
                {!authBusy && <ArrowRight size={17} />}
              </button>
            </form>
            <div className="auth-card-footer"><ShieldCheck size={14} /> Your password is stored securely as a hash.</div>
          </section>
        </div>
        <footer className="auth-footer"><span>FINCH · FINANCIAL LEARNING</span><span>Education for everyone, advice for no one.</span></footer>
      </main>
    );
  }

  const username = session.username ?? "there";
  const displayedMessages = messages.map((message, index) => ({ message, index }));

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand-lockup app-brand" href="/">
          <span className="brand-icon"><Leaf size={19} strokeWidth={2.2} /></span>
          <span>finch<span className="brand-period">.</span></span>
        </a>
        <div className="workspace-label">YOUR WORKSPACE</div>
        <nav className="side-nav" aria-label="Main navigation">
          <button type="button" className={`nav-item${activeView === "portfolio" ? " active" : ""}`} onClick={() => setActiveView("portfolio")} aria-current={activeView === "portfolio" ? "page" : undefined} aria-label="Portfolio dashboard">
            <WalletCards size={17} /> Portfolio dashboard {activeView === "portfolio" && <span className="nav-active-dot" />}
          </button>
          <button type="button" className={`nav-item${activeView === "learn" ? " active" : ""}`} onClick={() => setActiveView("learn")} aria-current={activeView === "learn" ? "page" : undefined} aria-label="Ask and learn">
            <MessageCircle size={17} /> Ask & Learn {activeView === "learn" && <span className="nav-active-dot" />}
          </button>
          <button type="button" className={`nav-item${activeView === "planning" ? " active" : ""}`} onClick={() => setActiveView("planning")} aria-current={activeView === "planning" ? "page" : undefined} aria-label="Goal planner">
            <Compass size={17} /> Goal planner {activeView === "planning" && <span className="nav-active-dot" />}
          </button>
          <button type="button" className={`nav-item${activeView === "market" ? " active" : ""}`} onClick={() => setActiveView("market")} aria-current={activeView === "market" ? "page" : undefined} aria-label="Market planner">
            <TrendingUp size={17} /> Market planner {activeView === "market" && <span className="nav-active-dot" />}
          </button>
          {session.role === "admin" && (
            <button type="button" className={`nav-item${activeView === "admin" ? " active" : ""}`} onClick={() => setActiveView("admin")} aria-current={activeView === "admin" ? "page" : undefined} aria-label="Admin profiles">
              <Users size={17} /> Admin profiles {activeView === "admin" && <span className="nav-active-dot" />}
            </button>
          )}
        </nav>
        <div className="sidebar-rule" />
        <button className="profile-toggle" type="button" onClick={() => setProfileOpen((open) => !open)} aria-expanded={profileOpen}>
          <span className="profile-toggle-icon"><UserRound size={16} /></span>
          <span className="profile-toggle-text"><strong>Learning profile</strong><small>Make it personal to you</small></span>
          <ChevronDown className={profileOpen ? "chevron open" : "chevron"} size={16} />
        </button>
        {profileOpen && (
          <form className="profile-form" onSubmit={saveProfile}>
            <label>Experience level
              <select value={profile.learning_level} onChange={(event) => setProfile({ ...profile, learning_level: event.target.value as Profile["learning_level"] })}>
                <option>Beginner</option><option>Intermediate</option><option>Advanced</option>
              </select>
            </label>
            <label>What are you working toward?
              <input value={profile.goal} maxLength={300} onChange={(event) => setProfile({ ...profile, goal: event.target.value })} placeholder="Optional" />
            </label>
            <label>Time horizon
              <input value={profile.time_horizon} maxLength={120} onChange={(event) => setProfile({ ...profile, time_horizon: event.target.value })} placeholder="Optional" />
            </label>
            <label>Risk comfort
              <select value={profile.risk_comfort} onChange={(event) => setProfile({ ...profile, risk_comfort: event.target.value as Profile["risk_comfort"] })}>
                <option>Not specified</option><option>Low</option><option>Moderate</option><option>High</option>
              </select>
            </label>
            {profileError && <p className="inline-error" role="alert">{profileError}</p>}
            {profileNotice && <p className="inline-success"><Check size={13} /> {profileNotice}</p>}
            <button type="submit" className="sidebar-save">Save profile</button>
            <p className="profile-disclaimer">Your profile is learning context, not a suitability assessment.</p>
          </form>
        )}
        <div className="sidebar-spacer" />
        <div className="sidebar-note">
          <span className="note-icon"><Sparkles size={15} /></span>
          <p>Curiosity is a great place to start.</p>
          <span>Ask anything. Learn at your pace.</span>
        </div>
        <div className="account-row">
          <div className="avatar">{username.slice(0, 1).toUpperCase()}</div>
          <div className="account-info"><strong>{username}</strong><span>Personal space</span></div>
          <button type="button" className="icon-button signout-button" onClick={() => void signOut()} title="Sign out" aria-label="Sign out"><LogOut size={16} /></button>
        </div>
      </aside>

      <main className="main-content">
        <header className="main-header">
          <div className="breadcrumbs"><span>Your workspace</span><span className="crumb-slash">/</span><strong>{VIEW_LABELS[activeView]}</strong></div>
          <div className="header-right"><span className="privacy-chip"><ShieldCheck size={14} /> {session.role === "admin" ? "Admin space" : "Private space"}</span><span className="header-avatar">{username.slice(0, 1).toUpperCase()}</span></div>
        </header>

        <div className="page-content">
          <section className="welcome-row" id="learn">
            <div>
              <div className="eyebrow"><span className="eyebrow-line" /> YOUR FINANCIAL LEARNING SPACE</div>
              <h1>Good to have you here, <span>{username}.</span></h1>
              <p>Bring your questions. We’ll take them one clear step at a time.</p>
            </div>
            <div className="welcome-mark"><span className="welcome-mark-inner"><Leaf size={28} /></span><span className="orbit orbit-one" /><span className="orbit orbit-two" /></div>
          </section>

          <div className="education-banner">
            <span className="banner-icon"><ShieldCheck size={17} /></span>
            <p><strong>A note on what we do.</strong> This is a space for general financial education, not personalized financial, investment, tax, or legal advice. Never share account numbers or passwords.</p>
            <a href="#about" aria-label="About this assistant"><ArrowUpRight size={16} /></a>
          </div>

          {activeView === "planning" && <section className="planner-card" id="planning">
            <div className="planner-topline"><span className="planner-icon"><Compass size={17} /></span><span>THINKING AHEAD</span><span className="optional-pill">OPTIONAL</span></div>
            <div className="planner-layout">
              <div className="planner-intro"><h2>Start with a goal.</h2><p>Share what you’re working toward. Add a target and timeline to see a simple savings estimate, then explore the goal together.</p><div className="planner-footnote"><ShieldCheck size={14} /> Estimates use the details you provide.</div></div>
              <form className="goal-form" onSubmit={submitGoal}>
                <label className="goal-field goal-main-field"><span>What are you planning for?</span><input value={goal} onChange={(event) => setGoal(event.target.value)} placeholder="e.g. building an emergency fund" /></label>
                <div className="goal-row">
                  <label className="goal-field"><span>Time available (months) <i>OPTIONAL</i></span><input type="number" min="1" step="1" inputMode="numeric" value={horizon} onChange={(event) => setHorizon(event.target.value)} placeholder="e.g. 24" /></label>
                  <label className="goal-field"><span>Target amount ($) <i>OPTIONAL</i></span><input type="number" min="0" step="0.01" inputMode="decimal" value={target} onChange={(event) => setTarget(event.target.value)} placeholder="e.g. 20,000" /></label>
                </div>
                <div className="goal-row">
                  <label className="goal-field"><span>Already saved ($) <i>OPTIONAL</i></span><input type="number" min="0" step="0.01" inputMode="decimal" value={currentSavings} onChange={(event) => setCurrentSavings(event.target.value)} placeholder="e.g. 2,000" /></label>
                  <label className="goal-field"><span>Monthly amount you can save ($) <i>OPTIONAL</i></span><input type="number" min="0" step="0.01" inputMode="decimal" value={monthlyBudget} onChange={(event) => setMonthlyBudget(event.target.value)} placeholder="e.g. 500" /></label>
                </div>
                {goalError && <p className="inline-error" role="alert">{goalError}</p>}
                <button className="primary-button goal-submit" type="submit" disabled={busy}><span>Explore this goal</span>{busy ? <LoaderCircle className="spin" size={16} /> : <ArrowRight size={16} />}</button>
              </form>
            </div>
            {goalPlanReady && <div className="goal-plan" aria-live="polite">
              <div className="goal-plan-heading">
                <div><span className="goal-plan-kicker">YOUR SAVINGS SNAPSHOT</span><h3>A simple path to your goal</h3></div>
                <span className="goal-plan-assumption">No investment growth assumed</span>
              </div>
              <div className="goal-plan-stats">
                <div><span>Target</span><strong>{formatCurrency(targetAmount)}</strong></div>
                <div><span>Saved so far</span><strong>{formatCurrency(savedAmount)}</strong></div>
                <div><span>Still to save</span><strong>{formatCurrency(remainingAmount)}</strong></div>
                <div><span>Monthly pace needed</span><strong>{formatCurrency(monthlyNeeded)}</strong></div>
              </div>
              <div className="goal-progress-label"><span>Progress</span><strong>{goalProgress.toFixed(0)}%</strong></div>
              <div className="goal-progress-track" role="progressbar" aria-label="Goal savings progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(goalProgress)}>
                <span style={{ width: `${goalProgress}%` }} />
              </div>
              {remainingAmount === 0 ? <p className="goal-plan-status">You’ve reached this savings target.</p> : <>
                {monthlyBudgetAmount !== null && <p className="goal-plan-status">
                  {monthlyBudgetAmount > 0 && projectedMonths !== null
                    ? <>At {formatCurrency(monthlyBudgetAmount)} per month, the estimate is {projectedMonths} {projectedMonths === 1 ? "month" : "months"} to reach your goal{projectedMonths <= monthsAvailable ? "—within your timeline." : `—about ${projectedMonths - monthsAvailable} months beyond your timeline.`}</>
                    : "Enter a monthly amount above zero to estimate how long your goal may take."}
                  {monthlyBudgetAmount > 0 && monthlyBudgetAmount < monthlyNeeded && <> Your monthly amount is {formatCurrency(monthlyNeeded - monthlyBudgetAmount)} below the pace needed for this timeline.</>}
                  {monthlyBudgetAmount > 0 && monthlyBudgetAmount >= monthlyNeeded && <> This amount meets the estimated monthly pace for your timeline.</>}
                </p>}
                <div className="goal-milestones">
                  <h4>Milestones</h4>
                  <div className="goal-table-wrap">
                    <table>
                      <thead><tr><th scope="col">Checkpoint</th><th scope="col">Target saved</th><th scope="col">By</th></tr></thead>
                      <tbody>{[25, 50, 75, 100].map((percent) => {
                        const milestoneAmount = targetAmount * percent / 100;
                        const contributionToMilestone = Math.max(milestoneAmount - savedAmount, 0);
                        const milestoneMonth = Math.ceil(monthsAvailable * contributionToMilestone / remainingAmount);
                        return <tr key={percent}><th scope="row">{percent}% of goal</th><td>{formatCurrency(milestoneAmount)}</td><td>{contributionToMilestone === 0 ? "Already reached" : `Month ${milestoneMonth}`}</td></tr>;
                      })}</tbody>
                    </table>
                  </div>
                </div>
              </>}
              <p className="goal-plan-disclaimer">Illustrative estimate only. It assumes regular contributions and no investment growth, fees, or changes to your goal.</p>
            </div>}
          </section>}

          {activeView === "market" && <section className="planner-card market-planner-card" id="market-planner">
            <div className="planner-topline"><span className="planner-icon"><TrendingUp size={17} /></span><span>MARKET PLANNER</span></div>
            <div className="market-planner-content">
              <div>
                <h2>Make sense of the markets.</h2>
                <p>Ask about market movements, quotes, or financial concepts. Ticker-specific questions can include a recent closing-price chart when market data is available. We explain context, not what to buy or sell.</p>
              </div>
              <div className="market-question-suggestions" aria-label="Suggested market questions">
                <button type="button" onClick={() => setQuestion("What is the recent price history for ticker: AAPL?")}>Show an AAPL price chart</button>
                <button type="button" onClick={() => setQuestion("How do interest rate changes affect bond prices?")}>How do rate changes affect bonds?</button>
                <button type="button" onClick={() => setQuestion("What should I understand when comparing a stock's price movements over time?")}>Understand price movements</button>
              </div>
            </div>
          </section>}

          {activeView === "portfolio" && <PortfolioDashboard />}
          {activeView === "admin" && session.role === "admin" && <AdminProfiles />}

          {(activeView === "learn" || activeView === "market") && <section className="conversation-section">
            <div className="section-heading">
              <div><span className="conversation-kicker">{activeView === "market" ? <TrendingUp size={14} /> : <MessageCircle size={14} />} {activeView === "market" ? "MARKET CONVERSATION" : "YOUR CONVERSATION"}</span><h2>{activeView === "market" ? "Your market questions." : "What’s on your mind?"}</h2></div>
              <div className="conversation-actions">
                <span className="history-count">{messages.length > 0 ? `${messages.length} messages` : "A fresh start"}</span>
                {messages.length > 0 && (
                  <button
                    className="clear-history-button"
                    type="button"
                    onClick={() => void clearHistory()}
                    disabled={busy || clearingHistory}
                  >
                    {clearingHistory ? <LoaderCircle className="spin" size={13} /> : <Trash2 size={13} />}
                    {clearingHistory ? "Clearing…" : "Clear history"}
                  </button>
                )}
              </div>
            </div>
            {historyNotice && <p className="history-notice" role="status">{historyNotice}</p>}
            <div className="conversation-card">
              {messages.length > 0 && (
                <button
                  type="button"
                  className="history-expand"
                  onClick={() => setHistoryExpanded((expanded) => !expanded)}
                  aria-expanded={historyExpanded}
                  aria-controls="conversation-history"
                >
                  <ChevronDown
                    size={14}
                    className={historyExpanded ? "history-expand-icon expanded" : "history-expand-icon"}
                  />
                  {historyExpanded
                    ? "Hide conversation history"
                    : `Show conversation history (${messages.length} messages)`}
                </button>
              )}
              <div className="chat-scroll" id="conversation-history" ref={chatArea}>
                {messages.length === 0 ? (
                  <div className="empty-chat">
                    <span className="empty-icon"><MessageCircle size={21} /></span>
                    <h3>{activeView === "market" ? "Start with a market question." : "A good question can change how things feel."}</h3>
                    <p>{activeView === "market" ? "Ask for context on market news, prices, or how markets work. Answers are educational, not trade recommendations." : "Ask about budgeting, saving, investing basics, taxes, or anything you’re curious about."}</p>
                    {activeView === "learn" && <div className="suggestion-row">
                      <button type="button" onClick={() => setQuestion("What is the difference between saving and investing?")}><Coins size={14} /> Saving vs. investing</button>
                      <button type="button" onClick={() => setQuestion("How does compound interest work?")}><Sparkles size={14} /> Compound interest</button>
                      <button type="button" onClick={() => setQuestion("What should I know about a Roth IRA?")}><WalletCards size={14} /> Roth IRA basics</button>
                    </div>}
                  </div>
                ) : historyExpanded ? (
                  <div className="message-list">
                    {displayedMessages.map(({ message, index }) => (
                      <article key={`${index}-${message.role}`} className={`message ${message.role}`}>
                        <div className="message-avatar">{message.role === "assistant" ? <Leaf size={15} /> : username.slice(0, 1).toUpperCase()}</div>
                        <div className="message-body">
                          <div className="message-meta">
                            <strong>{message.role === "assistant" ? "Finch" : "You"}</strong>
                            {message.agent_label && <span className="specialist-tag"><Sparkles size={11} /> {message.agent_label}</span>}
                            {formatMessageTimestamp(message.created_at) && (
                              <time className="message-timestamp" dateTime={message.created_at}>
                                {formatMessageTimestamp(message.created_at)}
                              </time>
                            )}
                            {message.streaming && message.content && (
                              <span className="thinking-label"><span /> Writing</span>
                            )}
                          </div>
                          {message.role === "assistant" && message.streaming && !message.content ? (
                            <div className="thinking-dots" aria-label="Waiting for response"><i /><i /><i /></div>
                          ) : message.role === "assistant" ? (
                            <>
                              <div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown></div>
                              {message.chart_data && <MarketPriceChart data={message.chart_data} />}
                            </>
                          ) : <p className="user-message-text">{message.content}</p>}
                          {((message.citations && message.citations.length > 0) || (message.sources && message.sources.length > 0) || message.retrieval_filter !== undefined) && (
                            <details className="sources-details">
                              <summary><Bookmark size={13} /> Knowledge-base sources <ChevronDown size={13} /></summary>
                              {message.retrieval_filter !== undefined && (
                                <p className="retrieval-filter">
                                  Metadata filter (specialist):
                                  {" "}
                                  {message.retrieval_filter.length
                                    ? message.retrieval_filter.join(" OR ")
                                    : "not applied (knowledge-base retrieval skipped)"}
                                </p>
                              )}
                              <ul>
                                {message.citations?.map((citation) => (
                                  <li key={citation.article_id || citation.source_url}>
                                    <a href={citation.source_url} target="_blank" rel="noreferrer">
                                      {citation.title}{citation.publisher ? ` — ${citation.publisher}` : ""}<ArrowUpRight size={12} />
                                    </a>
                                    {citation.specialist && <span className="citation-metadata"> specialist: {citation.specialist}</span>}
                                  </li>
                                ))}
                                {!message.citations?.length && message.sources?.map((source) => (
                                  <li key={source}>{source.startsWith("http") ? <a href={source} target="_blank" rel="noreferrer">{source}<ArrowUpRight size={12} /></a> : source}</li>
                                ))}
                              </ul>
                            </details>
                          )}
                        </div>
                      </article>
                    ))}
                    <div ref={chatEnd} />
                  </div>
                ) : null}
              </div>
              {showScroll && <button className="scroll-bottom" type="button" onClick={() => chatEnd.current?.scrollIntoView({ behavior: "smooth" })}><ArrowDown size={15} /> Latest message</button>}
              {chatError && <div className="chat-error" role="alert"><CircleHelp size={15} /> {chatError}</div>}
              <form className="composer" onSubmit={submitChat}>
                <textarea value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendQuestion(question); } }} maxLength={6000} rows={2} placeholder={activeView === "market" ? "Ask a question about markets…" : "Ask a question about your finances…"} aria-label={activeView === "market" ? "Ask a market education question" : "Ask a finance education question"} />
                <div className="composer-bottom"><span>General education only · Never share sensitive account details</span><button className="send-button" type="submit" disabled={!question.trim() || busy} aria-label="Send question">{busy ? <LoaderCircle className="spin" size={17} /> : <Send size={17} />}</button></div>
              </form>
            </div>
            <p className="conversation-footnote"><ShieldCheck size={13} /> Answers may be incomplete. Verify important information with primary sources and qualified professionals.</p>
          </section>}

          <footer className="page-footer" id="about"><span>FINCH <i>·</i> FINANCIAL LEARNING</span><span>Make room for better questions.</span></footer>
        </div>
      </main>
    </div>
  );
}

export default App;
