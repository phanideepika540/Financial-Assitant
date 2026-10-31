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
  streaming?: boolean;
  sources?: string[];
  citations?: Citation[];
  agent_label?: string;
};

type Citation = {
  article_id: string;
  title: string;
  publisher: string;
  source_url: string;
  reviewed_date: string;
};

type ChatResponse = {
  question: string;
  answer: string;
  sources: string[];
  citations: Citation[];
  agent: string;
  agent_label: string;
};

type GoalRequest = {
  goal: string;
  time_horizon: string;
  target_amount: string;
};

type Session = {
  authenticated: boolean;
  username?: string;
  role?: "user" | "admin";
  profile?: Profile;
  history?: Message[];
};

type WorkspaceView = "learn" | "planning" | "portfolio" | "admin";

const VIEW_LABELS: Record<WorkspaceView, string> = {
  learn: "Learn & ask",
  planning: "Goal planner",
  portfolio: "Portfolio dashboard",
  admin: "Admin profiles",
};

const initialProfile: Profile = {
  learning_level: "Beginner",
  goal: "",
  time_horizon: "",
  risk_comfort: "Not specified",
};

const VISIBLE_RECENT_MESSAGES = 4;

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
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState("");
  const [chatError, setChatError] = useState("");
  const [profileNotice, setProfileNotice] = useState("");
  const [profileError, setProfileError] = useState("");
  const [profileOpen, setProfileOpen] = useState(false);
  const [goal, setGoal] = useState("");
  const [horizon, setHorizon] = useState("");
  const [target, setTarget] = useState("");
  const [goalError, setGoalError] = useState("");
  const [showScroll, setShowScroll] = useState(false);
  const chatEnd = useRef<HTMLDivElement>(null);
  const chatArea = useRef<HTMLDivElement>(null);

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

  async function sendQuestion(text: string, goalRequest?: GoalRequest) {
    const clean = text.trim();
    if (!clean || busy) return;
    setBusy(true);
    setChatError("");
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
    setActiveView("learn");
    const summary = [
      `Help me think through: ${description}`,
      horizon.trim() ? `Time horizon: ${horizon.trim()}` : "",
      target.trim() ? `Target amount: ${target.trim()}` : "",
    ].filter(Boolean).join(" · ");
    void sendQuestion(summary, {
      goal: description,
      time_horizon: horizon.trim(),
      target_amount: target.trim(),
    });
    setGoal("");
    setHorizon("");
    setTarget("");
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
  const displayedMessages = messages
    .map((message, index) => ({ message, index }))
    .slice(historyExpanded ? 0 : -VISIBLE_RECENT_MESSAGES);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand-lockup app-brand" href="/">
          <span className="brand-icon"><Leaf size={19} strokeWidth={2.2} /></span>
          <span>finch<span className="brand-period">.</span></span>
        </a>
        <div className="workspace-label">YOUR WORKSPACE</div>
        <nav className="side-nav" aria-label="Main navigation">
          <button type="button" className={`nav-item${activeView === "learn" ? " active" : ""}`} onClick={() => setActiveView("learn")} aria-current={activeView === "learn" ? "page" : undefined} aria-label="Learn and ask">
            <MessageCircle size={17} /> Learn & ask {activeView === "learn" && <span className="nav-active-dot" />}
          </button>
          <button type="button" className={`nav-item${activeView === "planning" ? " active" : ""}`} onClick={() => setActiveView("planning")} aria-current={activeView === "planning" ? "page" : undefined} aria-label="Goal planner">
            <Compass size={17} /> Goal planner {activeView === "planning" && <span className="nav-active-dot" />}
          </button>
          <button type="button" className={`nav-item${activeView === "portfolio" ? " active" : ""}`} onClick={() => setActiveView("portfolio")} aria-current={activeView === "portfolio" ? "page" : undefined} aria-label="Portfolio dashboard">
            <WalletCards size={17} /> Portfolio dashboard {activeView === "portfolio" && <span className="nav-active-dot" />}
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
              <div className="planner-intro"><h2>Start with a goal.</h2><p>Big plans begin with a small question. Share what you’re thinking about, and we’ll help you explore it—without the pressure.</p><div className="planner-footnote"><ShieldCheck size={14} /> Approximate details are all you need.</div></div>
              <form className="goal-form" onSubmit={submitGoal}>
                <label className="goal-field goal-main-field"><span>What are you planning for?</span><input value={goal} onChange={(event) => setGoal(event.target.value)} placeholder="e.g. building an emergency fund" /></label>
                <div className="goal-row">
                  <label className="goal-field"><span>Time horizon <i>OPTIONAL</i></span><input value={horizon} onChange={(event) => setHorizon(event.target.value)} placeholder="e.g. 2 years" /></label>
                  <label className="goal-field"><span>Target amount <i>OPTIONAL</i></span><input value={target} onChange={(event) => setTarget(event.target.value)} placeholder="e.g. $5,000" /></label>
                </div>
                {goalError && <p className="inline-error" role="alert">{goalError}</p>}
                <button className="primary-button goal-submit" type="submit" disabled={busy}><span>Explore this goal</span>{busy ? <LoaderCircle className="spin" size={16} /> : <ArrowRight size={16} />}</button>
              </form>
            </div>
          </section>}

          {activeView === "portfolio" && <PortfolioDashboard />}
          {activeView === "admin" && session.role === "admin" && <AdminProfiles />}

          {activeView === "learn" && <section className="conversation-section">
            <div className="section-heading">
              <div><span className="conversation-kicker"><MessageCircle size={14} /> YOUR CONVERSATION</span><h2>What’s on your mind?</h2></div>
              <span className="history-count">{messages.length > 0 ? `${messages.length} messages` : "A fresh start"}</span>
            </div>
            <div className="conversation-card">
              <div className="chat-scroll" ref={chatArea}>
                {messages.length === 0 ? (
                  <div className="empty-chat">
                    <span className="empty-icon"><MessageCircle size={21} /></span>
                    <h3>A good question can change how things feel.</h3>
                    <p>Ask about budgeting, saving, investing basics, taxes, or anything you’re curious about.</p>
                    <div className="suggestion-row">
                      <button type="button" onClick={() => setQuestion("What is the difference between saving and investing?")}><Coins size={14} /> Saving vs. investing</button>
                      <button type="button" onClick={() => setQuestion("How does compound interest work?")}><Sparkles size={14} /> Compound interest</button>
                      <button type="button" onClick={() => setQuestion("What should I know about a Roth IRA?")}><WalletCards size={14} /> Roth IRA basics</button>
                    </div>
                  </div>
                ) : (
                  <div className="message-list">
                    {messages.length > VISIBLE_RECENT_MESSAGES && (
                      <button
                        type="button"
                        className="history-expand"
                        onClick={() => setHistoryExpanded((expanded) => !expanded)}
                        aria-expanded={historyExpanded}
                      >
                        <ChevronDown
                          size={14}
                          className={historyExpanded ? "history-expand-icon expanded" : "history-expand-icon"}
                        />
                        {historyExpanded
                          ? "Hide older messages"
                          : `Show ${messages.length - VISIBLE_RECENT_MESSAGES} older messages`}
                      </button>
                    )}
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
                            <div className="markdown-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown></div>
                          ) : <p className="user-message-text">{message.content}</p>}
                          {((message.citations && message.citations.length > 0) || (message.sources && message.sources.length > 0)) && (
                            <details className="sources-details">
                              <summary><Bookmark size={13} /> Knowledge-base sources <ChevronDown size={13} /></summary>
                              <ul>
                                {message.citations?.map((citation) => (
                                  <li key={citation.article_id || citation.source_url}>
                                    <a href={citation.source_url} target="_blank" rel="noreferrer">
                                      {citation.title}{citation.publisher ? ` — ${citation.publisher}` : ""}<ArrowUpRight size={12} />
                                    </a>
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
                )}
              </div>
              {showScroll && <button className="scroll-bottom" type="button" onClick={() => chatEnd.current?.scrollIntoView({ behavior: "smooth" })}><ArrowDown size={15} /> Latest message</button>}
              {chatError && <div className="chat-error" role="alert"><CircleHelp size={15} /> {chatError}</div>}
              <form className="composer" onSubmit={submitChat}>
                <textarea value={question} onChange={(event) => setQuestion(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendQuestion(question); } }} maxLength={6000} rows={2} placeholder="Ask a question about your finances…" aria-label="Ask a finance education question" />
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
