import { Download, Search } from "lucide-react"
import { useMemo, useState } from "react"
import { Link } from "react-router-dom"
import type { Reliability } from "../api"
import { dateTime, humanize, score, toCsv } from "../format"
import { useApi, useDebounced, usePageTitle } from "../state"
import { DataTable, Empty, ErrorState, Meter, Notice, Panel, Skeleton } from "../ui"

const CATEGORIES = [
  "suspected_flaky",
  "intermittent_failures",
  "consistently_failing",
  "insufficient_history",
  "consistently_passing",
]

const rowId = (r: Reliability) => [r.test_id, r.project, r.branch, r.browser, r.provenance].join("|")

function interval(value: unknown): string {
  if (Array.isArray(value) && value.length === 2 && value.every((v) => typeof v === "number"))
    return `${(value[0] * 100).toFixed(1)}% – ${(value[1] * 100).toFixed(1)}%`
  if (value && typeof value === "object") {
    const v = value as Record<string, unknown>
    const low = v.low ?? v.lower
    const high = v.high ?? v.upper
    if (typeof low === "number" && typeof high === "number")
      return `${(low * 100).toFixed(1)}% – ${(high * 100).toFixed(1)}%`
  }
  return "Not enough observations to estimate"
}

export function Flaky() {
  usePageTitle("Flaky Tests")
  const { data, error, reload } = useApi<Reliability[]>("/reliability")
  const [search, setSearch] = useState("")
  const [category, setCategory] = useState("")
  const [selected, setSelected] = useState<string | null>(null)
  const query = useDebounced(search).toLowerCase()

  const rows = useMemo(
    () =>
      (data ?? []).filter(
        (r) => (!query || `${r.name} ${r.suite}`.toLowerCase().includes(query)) && (!category || r.classification === category),
      ),
    [data, query, category],
  )
  const chosen = rows.find((r) => rowId(r) === selected) ?? null

  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data) return <Skeleton rows={9} height={22} />

  const exportCsv = () => {
    const blob = new Blob([toCsv(rows as unknown as Record<string, unknown>[])], { type: "text/csv" })
    const link = document.createElement("a")
    link.href = URL.createObjectURL(blob)
    link.download = "flakeguard-reliability.csv"
    link.click()
    URL.revokeObjectURL(link.href)
  }

  return (
    <div className="stack">
      <Notice>
        One row per test, branch, environment/browser and provenance. Reliability can be overstated where retry history is
        unknown.
      </Notice>
      <div className="toolbar">
        <label className="search">
          <Search size={15} aria-hidden="true" />
          <span className="sr-only">Search test or suite</span>
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search test or suite…"
            autoComplete="off"
          />
        </label>
        <label className="field inline">
          <span>Evidence category</span>
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All categories</option>
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {humanize(c)}
              </option>
            ))}
          </select>
        </label>
        <button className="btn" onClick={exportCsv} disabled={!rows.length}>
          <Download size={14} aria-hidden="true" /> Export CSV
        </button>
        <p className="muted small" aria-live="polite">
          {rows.length.toLocaleString()} of {data.length.toLocaleString()} tests
        </p>
      </div>

      <div className={`split ${chosen ? "has-detail" : ""}`}>
        <Panel>
          <DataTable
            caption="Test reliability evidence"
            rows={rows}
            rowKey={rowId}
            selectedKey={selected}
            initialSort={{ key: "suspicion", dir: "desc" }}
            empty={
              <Empty
                title="No tests match"
                action={
                  <button
                    className="btn"
                    onClick={() => {
                      setSearch("")
                      setCategory("")
                    }}
                  >
                    Clear search and category
                  </button>
                }
              >
                Adjust the search, category or workspace filters.
              </Empty>
            }
            columns={[
              {
                key: "name",
                header: "Test",
                sort: (r) => r.name,
                render: (r) => (
                  <button className="link-button" onClick={() => setSelected(rowId(r))} aria-pressed={rowId(r) === selected}>
                    {r.name}
                    <span className="muted small block">
                      {r.suite} · {r.project}
                    </span>
                  </button>
                ),
              },
              { key: "browser", header: "Browser", render: (r) => r.browser ?? "unknown" },
              { key: "branch", header: "Branch", render: (r) => r.branch },
              { key: "obs", header: "Observations", sort: (r) => r.observations, render: (r) => r.observations, numeric: true },
              {
                key: "reliability",
                header: "Reliability",
                sort: (r) => r.reliability_score,
                numeric: true,
                render: (r) => (
                  <span className="inline-meter">
                    <Meter value={r.reliability_score === null ? null : r.reliability_score / 100} label="Reliability score" />
                    {score(r.reliability_score)}
                  </span>
                ),
              },
              { key: "suspicion", header: "Suspicion", sort: (r) => r.suspicion_score, numeric: true, render: (r) => score(r.suspicion_score) },
              { key: "class", header: "Evidence", sort: (r) => r.classification, render: (r) => <span className="tag">{humanize(r.classification)}</span> },
            ]}
          />
        </Panel>

        {chosen && (
          <aside className="detail" aria-label="Scoring evidence">
            <Panel
              title="Scoring evidence"
              actions={
                <button className="btn" onClick={() => setSelected(null)}>
                  Close
                </button>
              }
            >
              <h3>{chosen.name}</h3>
              <p className="muted small">
                {chosen.suite} · {chosen.project} · {chosen.browser ?? "browser unknown"} · {chosen.branch}
              </p>
              <p>{chosen.explanation}</p>
              <dl className="pairs">
                <div>
                  <dt>Observations</dt>
                  <dd>
                    {chosen.observations} in {chosen.distinct_runs} runs
                  </dd>
                </div>
                <div>
                  <dt>Retry recoveries</dt>
                  <dd>
                    {chosen.retry_recoveries} of {chosen.known_retry_observations} known
                  </dd>
                </div>
                <div>
                  <dt>95% Wilson interval</dt>
                  <dd>{interval(chosen.pass_rate_interval_95)}</dd>
                </div>
                <div>
                  <dt>Priority</dt>
                  <dd>{chosen.priority ? humanize(chosen.priority) : "—"}</dd>
                </div>
                <div>
                  <dt>Last execution</dt>
                  <dd>{dateTime(chosen.last_execution)}</dd>
                </div>
              </dl>
              <p className="muted small">
                The interval estimates a proportion under independent observations; correlated CI runs can make it
                optimistic. It is not the probability that a test is flaky.
              </p>
              <Link className="btn primary" to={`/tests/${chosen.test_id}`}>
                Open execution history
              </Link>
            </Panel>
          </aside>
        )}
      </div>
    </div>
  )
}
