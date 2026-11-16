import { Bug, FlaskConical, KeyRound, LayoutDashboard, ListChecks, GitBranch, ExternalLink, RefreshCw, SlidersHorizontal, X } from "lucide-react"
import { lazy, Suspense, useEffect, useState, type FormEvent } from "react"
import { HashRouter, NavLink, Route, Routes, Link } from "react-router-dom"
import { getConfig, getKey, setKey, type AppConfig, type Options } from "./api"
import { humanize } from "./format"
const Failures = lazy(() => import("./pages/Failures").then((m) => ({ default: m.Failures })))
const Flaky = lazy(() => import("./pages/Flaky").then((m) => ({ default: m.Flaky })))
const Integration = lazy(() => import("./pages/Integration").then((m) => ({ default: m.Integration })))
const Overview = lazy(() => import("./pages/Overview").then((m) => ({ default: m.Overview })))
const TestDetail = lazy(() => import("./pages/TestDetail").then((m) => ({ default: m.TestDetail })))
import { AppProvider, useApi, useApp } from "./state"
import { STATUSES } from "./theme"
import { ErrorState, Skeleton } from "./ui"

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/flaky", label: "Flaky Tests", icon: FlaskConical },
  { to: "/failures", label: "Failure Analysis", icon: Bug },
  { to: "/tests", label: "Test Details", icon: ListChecks },
  { to: "/integration", label: "CI Integration", icon: GitBranch },
]

const TITLES: Record<string, { title: string; subtitle: string }> = {
  "/": { title: "Overview", subtitle: "Reliability across the selected history. Every number traces back to a test execution." },
  "/flaky": { title: "Flaky Tests", subtitle: "Find the tests that need a closer look, and follow the evidence behind every score." },
  "/failures": { title: "Failure Analysis", subtitle: "Connect recurring diagnostics, inspect their evidence and plan the next investigation." },
  "/tests": { title: "Test Details", subtitle: "One test, its complete execution story from first attempt to final outcome." },
  "/integration": { title: "CI Integration", subtitle: "Bring execution history together from local reports and authorized GitHub runs." },
}

function Logo() {
  return (
    <svg viewBox="0 0 28 28" width="24" height="24" fill="none" aria-hidden="true" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2 25 8v12L14 26 3 20V8L14 2Z" />
      <path d="m9 14 3.2 3.1L19 10" />
    </svg>
  )
}

function FilterPanel() {
  const { filters, setFilter, clearFilters } = useApp()
  const options = useApi<Options>("/options", undefined, false)
  const [open, setOpen] = useState(false)
  const active = Object.entries(filters)
  const fields: [string, string, string[]][] = options.data
    ? [
        ["repository", "Repository", options.data.repositories],
        ["provenance", "Data provenance", options.data.provenances],
        ["branch", "Branch", options.data.branches],
        ["suite", "Suite", options.data.suites],
        ["browser", "Browser", options.data.browsers],
        ["environment", "Environment", options.data.environments],
        ["status", "Status", [...STATUSES]],
      ]
    : []
  const dateToIso = (value: string, end: boolean) => (value ? `${value}T${end ? "23:59:59" : "00:00:00"}+00:00` : "")

  return (
    <div className="filters">
      <div className="scope">
        <button className="btn" aria-expanded={open} aria-controls="filter-panel" onClick={() => setOpen(!open)}>
          <SlidersHorizontal size={14} aria-hidden="true" /> Filters{active.length > 0 && <span className="count">{active.length}</span>}
        </button>
        <ul className="chips" aria-label="Active filters">
          {active.length === 0 && <li className="chip muted">All repositories and branches · includes synthetic and injected demo data</li>}
          {active.map(([key, value]) => (
            <li className="chip" key={key}>
              {humanize(key === "start" ? "from" : key === "end" ? "to" : key)}: {key === "start" || key === "end" ? value.slice(0, 10) : value}
              <button aria-label={`Remove ${key} filter`} onClick={() => setFilter(key, "")}>
                <X size={12} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
        {active.length > 0 && (
          <button className="btn quiet" onClick={clearFilters}>
            Clear all
          </button>
        )}
      </div>
      {open && (
        <div id="filter-panel" className="filter-grid">
          {fields.map(([key, label, values]) => (
            <label className="field" key={key}>
              <span>{label}</span>
              <select value={filters[key] ?? ""} onChange={(e) => setFilter(key, e.target.value)}>
                <option value="">All</option>
                {values.map((v) => (
                  <option key={v} value={v}>
                    {key === "status" ? humanize(v) : v}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <label className="field">
            <span>From (UTC)</span>
            <input type="date" value={filters.start?.slice(0, 10) ?? ""} onChange={(e) => setFilter("start", dateToIso(e.target.value, false))} />
          </label>
          <label className="field">
            <span>To (UTC)</span>
            <input type="date" value={filters.end?.slice(0, 10) ?? ""} onChange={(e) => setFilter("end", dateToIso(e.target.value, true))} />
          </label>
          {options.error && <ErrorState message={options.error} onRetry={options.reload} />}
        </div>
      )}
      {filters.status && (
        <p className="notice warn" role="note">
          Status filtering selects outcomes and can bias reliability history.
        </p>
      )}
    </div>
  )
}

function Shell({ onSignOut, authed }: { onSignOut: () => void; authed: boolean }) {
  const { config, refresh } = useApp()
  const route = (path: string) => TITLES[path] ?? TITLES["/"]
  return (
    <HashRouter>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <div className="shell">
        <aside className="sidebar">
          <Link to="/" className="brand">
            <Logo /> FlakeGuard
          </Link>
          <nav aria-label="Workspace">
            <ul>
              {NAV.map(({ to, label, icon: Icon, end }) => (
                <li key={to}>
                  <NavLink to={to} end={end}>
                    <Icon size={16} aria-hidden="true" />
                    {label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
          <div className="side-foot">
            <a href="/docs" target="_blank" rel="noreferrer noopener">
              API documentation <ExternalLink size={12} aria-hidden="true" />
            </a>
            {authed && (
              <button className="btn quiet" onClick={onSignOut}>
                <KeyRound size={13} aria-hidden="true" /> Forget API key
              </button>
            )}
            <p className="muted small">{config.read_only ? "Read-only demonstration" : "Evidence before assumptions"}</p>
          </div>
        </aside>
        <div className="content">
          <Routes>
            {["/", "/flaky", "/failures", "/tests", "/tests/:id", "/integration"].map((path) => (
              <Route
                key={path}
                path={path}
                element={
                  <main id="main">
                    <header className="page-head">
                      <div>
                        <h1 id="page-title" tabIndex={-1}>
                          {route(path.replace(/\/:id$/, "")).title}
                        </h1>
                        <p className="muted">{route(path.replace(/\/:id$/, "")).subtitle}</p>
                      </div>
                      <div className="head-actions">
                        <button className="btn" onClick={refresh}>
                          <RefreshCw size={14} aria-hidden="true" /> Refresh
                        </button>
                        <Link className="btn primary" to="/integration">
                          {config.read_only ? "Data sources" : "Import report"}
                        </Link>
                      </div>
                    </header>
                    {path !== "/integration" && <FilterPanel />}
                    <Suspense fallback={<Skeleton rows={8} height={22} />}>
                      <Page path={path} />
                    </Suspense>
                  </main>
                }
              />
            ))}
            <Route path="*" element={<main id="main"><h1 id="page-title" tabIndex={-1}>Page not found</h1><p><Link to="/">Back to the overview</Link></p></main>} />
          </Routes>
        </div>
      </div>
    </HashRouter>
  )
}

function Page({ path }: { path: string }) {
  switch (path) {
    case "/flaky":
      return <Flaky />
    case "/failures":
      return <Failures />
    case "/tests":
    case "/tests/:id":
      return <TestDetail />
    case "/integration":
      return <Integration />
    default:
      return <Overview />
  }
}

function KeyGate({ onSubmit, rejected }: { onSubmit: (key: string) => void; rejected: boolean }) {
  const [value, setValue] = useState("")
  const submit = (event: FormEvent) => {
    event.preventDefault()
    onSubmit(value.trim())
  }
  return (
    <main className="gate" id="main">
      <form onSubmit={submit} className="gate-card">
        <h1>
          <Logo /> FlakeGuard
        </h1>
        <p className="muted">This instance requires an API key. It is kept for this browser tab only and is sent only to this server.</p>
        <label className="field">
          <span>API key</span>
          <input type="password" value={value} onChange={(e) => setValue(e.target.value)} autoComplete="off" autoFocus required aria-describedby="gate-error" />
        </label>
        <p id="gate-error" className="feedback error" role="alert">
          {rejected ? "That key was not accepted. Check it and try again." : ""}
        </p>
        <button className="btn primary">Open workspace</button>
      </form>
    </main>
  )
}

export function App() {
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const [needsKey, setNeedsKey] = useState(false)
  const [rejected, setRejected] = useState(false)
  const [authed, setAuthed] = useState(Boolean(getKey()))

  useEffect(() => {
    getConfig()
      .then((c) => {
        setConfig(c)
        setNeedsKey(c.auth_required && !getKey())
      })
      .catch(() => setFailed("Cannot reach the FlakeGuard API. Check that the server is running."))
    const onUnauthorized = () => {
      setKey("")
      setAuthed(false)
      setRejected(true)
      setNeedsKey(true)
    }
    window.addEventListener("fg-unauthorized", onUnauthorized)
    return () => window.removeEventListener("fg-unauthorized", onUnauthorized)
  }, [])

  if (failed) return <main className="gate"><ErrorState message={failed} onRetry={() => location.reload()} /></main>
  if (!config) return <main className="gate"><Skeleton rows={3} /></main>
  if (needsKey)
    return (
      <KeyGate
        rejected={rejected}
        onSubmit={(key) => {
          setKey(key)
          setAuthed(true)
          setRejected(false)
          setNeedsKey(false)
        }}
      />
    )
  return (
    <AppProvider config={config}>
      <Shell
        authed={authed}
        onSignOut={() => {
          setKey("")
          setAuthed(false)
          setNeedsKey(config.auth_required)
        }}
      />
    </AppProvider>
  )
}
