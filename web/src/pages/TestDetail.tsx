import { ExternalLink } from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import type { Execution, Reliability, TestHistory } from "../api"
import { dateTime, duration, shortSha } from "../format"
import { useApi, usePageTitle } from "../state"
import { CHART, STATUS_COLOR } from "../theme"
import { CodeBlock, DataTable, Empty, ErrorState, Panel, Skeleton, StatusBadge } from "../ui"

export function TestDetail() {
  usePageTitle("Test Details")
  const { id } = useParams()
  const navigate = useNavigate()
  const scores = useApi<Reliability[]>("/reliability")
  const history = useApi<TestHistory>(id ? `/tests/${id}/history` : null, { limit: 2000 })
  const [filter, setFilter] = useState("")
  const [picked, setPicked] = useState<number | null>(null)

  const tests = useMemo(() => {
    const unique = new Map<string, Reliability>()
    for (const row of scores.data ?? []) if (!unique.has(row.test_id)) unique.set(row.test_id, row)
    return [...unique.values()]
  }, [scores.data])
  const options = useMemo(
    () => tests.filter((t) => `${t.name} ${t.project}`.toLowerCase().includes(filter.toLowerCase())).slice(0, 200),
    [tests, filter],
  )

  useEffect(() => setPicked(null), [id])

  if (scores.error) return <ErrorState message={scores.error} onRetry={scores.reload} />
  if (!scores.data) return <Skeleton rows={8} height={22} />
  if (!tests.length)
    return (
      <Empty title="No test history available">Import reports from the CI Integration page to inspect executions.</Empty>
    )

  const rows = history.data?.history ?? []
  const selected: Execution | undefined = rows[picked ?? rows.length - 1]
  const meta = tests.find((t) => t.test_id === id)

  return (
    <div className="stack">
      <div className="toolbar">
        <label className="field grow">
          <span>Find a test</span>
          <input type="search" value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter by name or project…" />
        </label>
        <label className="field grow">
          <span>Test identity</span>
          <select value={id ?? ""} onChange={(e) => navigate(`/tests/${e.target.value}`)}>
            <option value="" disabled>
              Choose a test…
            </option>
            {options.map((t) => (
              <option key={t.test_id} value={t.test_id}>
                {t.name} · {t.project} · {t.repository}
              </option>
            ))}
          </select>
        </label>
      </div>

      {!id ? (
        <Empty title="Choose a test">Pick a test to see its complete execution story, from first attempt to final outcome.</Empty>
      ) : history.error ? (
        <ErrorState message={history.error} onRetry={history.reload} />
      ) : !history.data ? (
        <Skeleton rows={8} height={22} />
      ) : (
        <>
          <p className="muted small">
            {meta ? `${meta.name} · ` : ""}Showing {rows.length.toLocaleString()} of {history.data.total.toLocaleString()} observations.
          </p>
          <div className="grid-even">
            <Panel title="Execution duration" note="Marker colour shows the final outcome">
              <div className="chart" role="img" aria-label={`Duration across ${rows.length} executions`}>
                <ResponsiveContainer width="100%" height={230}>
                  <LineChart data={rows.map((r, i) => ({ ...r, index: i + 1 }))} margin={{ top: 8, right: 8, bottom: 0, left: -4 }}>
                    <CartesianGrid vertical={false} stroke={CHART.grid} />
                    <XAxis dataKey="index" tickLine={false} axisLine={false} tick={{ fill: CHART.axis, fontSize: 11 }} minTickGap={24} />
                    <YAxis
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: CHART.axis, fontSize: 11 }}
                      tickFormatter={(v: number) => duration(v)}
                      width={58}
                    />
                    <Tooltip
                      contentStyle={{ background: "#232327", border: "1px solid #414148", borderRadius: 8, fontSize: 12 }}
                      labelFormatter={(i) => `Execution ${i}`}
                      formatter={(v: number, _n, item) => [duration(v), (item.payload as Execution).status]}
                    />
                    <Line
                      type="linear"
                      dataKey="duration_ms"
                      stroke="rgba(237,237,242,.45)"
                      strokeWidth={1.25}
                      isAnimationActive={false}
                      dot={(props: { cx?: number; cy?: number; payload?: Execution; index?: number }) => (
                        <circle
                          key={props.index}
                          cx={props.cx}
                          cy={props.cy}
                          r={3.5}
                          fill={STATUS_COLOR[props.payload?.status ?? "unknown"] ?? STATUS_COLOR.unknown}
                        />
                      )}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Panel>
            <Panel title="Observed outcomes" note="Oldest to newest · select a square to inspect it">
              <div className="strip">
                {rows.map((r, i) => (
                  <button
                    key={r.id}
                    title={`${r.status} · ${dateTime(r.executed_at)}`}
                    aria-label={`Execution ${i + 1}: ${r.status}`}
                    aria-pressed={r === selected}
                    style={{ background: STATUS_COLOR[r.status] ?? STATUS_COLOR.unknown }}
                    onClick={() => setPicked(i)}
                  />
                ))}
              </div>
              <ul className="legend">
                {Object.entries(STATUS_COLOR)
                  .filter(([s]) => rows.some((r) => r.status === s))
                  .map(([s, c]) => (
                    <li key={s}>
                      <i style={{ background: c }} aria-hidden="true" />
                      {s}
                    </li>
                  ))}
              </ul>
            </Panel>
          </div>

          <Panel title="Executions">
            <DataTable
              caption="Execution history"
              rows={[...rows].reverse()}
              rowKey={(r) => String(r.id)}
              selectedKey={selected ? String(selected.id) : null}
              columns={[
                {
                  key: "run",
                  header: "Run",
                  render: (r) => (
                    <button className="link-button mono" onClick={() => setPicked(rows.indexOf(r))}>
                      {r.external_run_id}
                    </button>
                  ),
                },
                { key: "branch", header: "Branch", render: (r) => r.branch },
                { key: "status", header: "Status", render: (r) => <StatusBadge status={r.status} /> },
                { key: "dur", header: "Duration", render: (r) => duration(r.duration_ms), numeric: true },
                {
                  key: "retries",
                  header: "Retries",
                  render: (r) => (r.retries === null ? "unknown" : r.retry_recovered ? `${r.retries} (recovered)` : r.retries),
                  numeric: true,
                },
                { key: "browser", header: "Browser", render: (r) => r.browser ?? "—" },
                { key: "at", header: "Executed (UTC)", render: (r) => dateTime(r.executed_at), numeric: true },
              ]}
            />
          </Panel>

          {selected && (
            <Panel
              title={`Diagnostics · run ${selected.external_run_id}`}
              note={`${shortSha(selected.commit_sha)} on ${selected.branch}`}
              actions={
                selected.ci_url?.startsWith("https://github.com/") ? (
                  <a className="btn" href={selected.ci_url} target="_blank" rel="noreferrer noopener">
                    Open CI run <ExternalLink size={13} aria-hidden="true" />
                  </a>
                ) : undefined
              }
            >
              {selected.attempts.map((a) => (
                <div className="attempt" key={a.ordinal}>
                  <h3>
                    Attempt {a.ordinal + 1} <StatusBadge status={a.status} />
                    <span className="muted small">
                      {" "}
                      · retry index {a.retry_index ?? "unknown"} · {duration(a.duration_ms)}
                    </span>
                  </h3>
                  {a.fingerprint && <p className="muted small">Related failure pattern: <span className="mono">{a.fingerprint.slice(0, 12)}</span></p>}
                  {(a.error_message || a.stack_trace) && (
                    <CodeBlock label={`Attempt ${a.ordinal + 1} diagnostic`}>{a.error_message || a.stack_trace || ""}</CodeBlock>
                  )}
                  {a.artifacts.length > 0 && (
                    <p className="muted small">
                      Artifacts (metadata only, files are not served): {a.artifacts.map((x) => x.name ?? x.path).join(", ")}
                    </p>
                  )}
                </div>
              ))}
            </Panel>
          )}
        </>
      )}
    </div>
  )
}
