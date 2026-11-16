import { ArrowRight } from "lucide-react"
import { useMemo, useState } from "react"
import { Link } from "react-router-dom"
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import type { Dashboard, Reliability, Run } from "../api"
import { dateTime, duration, pct, shortSha } from "../format"
import { useApi, usePageTitle } from "../state"
import { CHART } from "../theme"
import { DataTable, Empty, ErrorState, Meter, Panel, Segmented, Skeleton } from "../ui"

const WINDOWS: Record<string, number | null> = { "7 days": 7, "14 days": 14, "30 days": 30, All: null }

export function Overview() {
  usePageTitle("Overview")
  const dash = useApi<Dashboard>("/dashboard")
  const runs = useApi<Run[]>("/runs", { limit: 8 })
  const reliability = useApi<Reliability[]>("/reliability")
  const [window, setWindow] = useState("All")

  const trend = useMemo(() => {
    const all = (dash.data?.trends ?? []).filter((t) => t.pass_rate !== null)
    const days = WINDOWS[window]
    if (!days || !all.length) return all
    const end = new Date(all[all.length - 1].date).getTime()
    return all.filter((t) => new Date(t.date).getTime() >= end - (days - 1) * 86_400_000)
  }, [dash.data, window])

  const suspects = useMemo(
    () =>
      (reliability.data ?? [])
        .filter((r) => r.classification === "suspected_flaky")
        .sort((a, b) => (b.suspicion_score ?? 0) - (a.suspicion_score ?? 0))
        .slice(0, 5),
    [reliability.data],
  )

  if (dash.error) return <ErrorState message={dash.error} onRetry={dash.reload} />
  if (!dash.data) return <Skeleton rows={8} height={22} />
  const { metrics: m } = dash.data

  if (m.total_executions === 0)
    return (
      <Empty
        title="No executions in this scope"
        action={
          <Link className="btn primary" to="/integration">
            Import a report
          </Link>
        }
      >
        Import a Playwright JSON or JUnit report, or widen the filters. Every number here traces back to a test
        execution.
      </Empty>
    )

  return (
    <div className="stack">
      <ul className="metric-strip">
        <li>
          <span className="m-label">Test executions</span>
          <strong className="m-value">{m.total_executions.toLocaleString()}</strong>
          <span className="m-note">{m.eligible_executions.toLocaleString()} eligible for pass/fail rates</span>
        </li>
        <li>
          <span className="m-label">Final failures</span>
          <strong className="m-value">{m.failed.toLocaleString()}</strong>
          <span className="m-note">{pct(m.failure_rate)} of eligible executions</span>
        </li>
        <li>
          <span className="m-label">Suspected flaky tests</span>
          <strong className="m-value">{m.suspected_flaky_tests}</strong>
          <span className="m-note">Prioritized for investigation</span>
        </li>
        <li>
          <span className="m-label">Average duration</span>
          <strong className="m-value">{duration(m.average_duration_ms)}</strong>
          <span className="m-note">Eligible executions with complete timing</span>
        </li>
      </ul>

      <div className="grid-main">
        <Panel
          title="Reliability over time"
          note={`Final pass rate ${pct(m.pass_rate)} · ${m.passed.toLocaleString()} of ${m.eligible_executions.toLocaleString()} eligible executions`}
          actions={<Segmented label="Trend window" options={Object.keys(WINDOWS)} value={window} onChange={setWindow} />}
        >
          {trend.length ? (
            <div
              className="chart"
              role="img"
              aria-label={`Daily final pass rate from ${trend[0].date} to ${trend[trend.length - 1].date}, ending at ${pct(trend[trend.length - 1].pass_rate)}`}
            >
              <ResponsiveContainer width="100%" height={250}>
                <AreaChart data={trend} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
                  <defs>
                    <linearGradient id="passFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={CHART.line} stopOpacity={0.14} />
                      <stop offset="100%" stopColor={CHART.line} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid vertical={false} stroke={CHART.grid} />
                  <XAxis
                    dataKey="date"
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: CHART.axis, fontSize: 11 }}
                    tickFormatter={(d: string) => d.slice(5)}
                    minTickGap={32}
                  />
                  <YAxis
                    domain={[0, 1]}
                    ticks={[0, 0.5, 1]}
                    tickLine={false}
                    axisLine={false}
                    tick={{ fill: CHART.axis, fontSize: 11 }}
                    tickFormatter={(v: number) => `${v * 100}%`}
                  />
                  <Tooltip
                    cursor={{ stroke: "rgba(255,255,255,.2)" }}
                    contentStyle={{ background: "#232327", border: "1px solid #414148", borderRadius: 8, fontSize: 12 }}
                    labelStyle={{ color: "#a0a0a5" }}
                    formatter={(v: number) => [pct(v), "Pass rate"]}
                  />
                  <Area
                    type="monotone"
                    dataKey="pass_rate"
                    stroke={CHART.line}
                    strokeWidth={1.75}
                    fill="url(#passFill)"
                    isAnimationActive={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <Empty title="No trend data yet">Eligible executions with dates will appear here.</Empty>
          )}
          <p className="muted small">
            {m.excluded.toLocaleString()} skipped, interrupted or unknown outcomes are excluded. The window ends at the
            latest observed execution.
          </p>
        </Panel>

        <Panel title="First-attempt reliability" note="Observed retry data only">
          <p className="figure">{pct(m.first_attempt_pass_rate)}</p>
          <Meter value={m.first_attempt_pass_rate} label="First-attempt pass rate" />
          <dl className="pairs">
            <div>
              <dt>Initial attempts known</dt>
              <dd>{m.first_attempt_observations.toLocaleString()}</dd>
            </div>
            <div>
              <dt>Retry recoveries</dt>
              <dd>{m.retry_recoveries.toLocaleString()}</dd>
            </div>
            <div>
              <dt>Recovery rate</dt>
              <dd>{pct(m.retry_recovery_rate)}</dd>
            </div>
          </dl>
          <p className="muted small">
            Recovery denominator: {m.initially_failed_with_retries} initially failed executions that were retried.
            Missing retry information stays unknown, never zero.
          </p>
        </Panel>
      </div>

      <div className="grid-main">
        <Panel title="Recent test runs">
          {runs.error ? (
            <ErrorState message={runs.error} onRetry={runs.reload} />
          ) : !runs.data ? (
            <Skeleton rows={5} />
          ) : (
            <DataTable
              caption="Recent test runs"
              rows={runs.data}
              rowKey={(r) => String(r.id)}
              empty={<Empty title="No runs in this scope" />}
              columns={[
                { key: "run", header: "Run", render: (r) => <span className="mono">{r.external_id}</span> },
                { key: "branch", header: "Branch", render: (r) => r.branch },
                { key: "commit", header: "Commit", render: (r) => <span className="mono">{shortSha(r.commit_sha)}</span> },
                { key: "source", header: "Source", render: (r) => r.provenance },
                { key: "at", header: "Executed (UTC)", render: (r) => dateTime(r.executed_at), numeric: true },
              ]}
            />
          )}
        </Panel>

        <Panel title="Investigation queue" note="In the selected history">
          <dl className="pairs flush">
            <div>
              <dt>Suspected flaky tests</dt>
              <dd>{m.suspected_flaky_tests}</dd>
            </div>
            <div>
              <dt>Newly failing observations</dt>
              <dd>{dash.data.newly_failing.length}</dd>
            </div>
          </dl>
          {suspects.length > 0 ? (
            <ol className="queue">
              {suspects.map((s) => (
                <li key={`${s.test_id}-${s.branch}-${s.browser}`}>
                  <Link to={`/tests/${s.test_id}`}>{s.name}</Link>
                  <span className="muted small">
                    Suspicion {s.suspicion_score?.toFixed(0) ?? "—"} · {s.suite} · {s.browser ?? "browser unknown"}
                  </span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="muted small">No test currently meets the suspected-flaky evidence threshold.</p>
          )}
          <Link className="btn" to="/flaky">
            Review test evidence <ArrowRight size={14} aria-hidden="true" />
          </Link>
          <p className="muted small">
            Signals prioritize investigation. Suspected flakiness never bypasses a quality gate.
          </p>
        </Panel>
      </div>

      <Panel title="Suites needing attention">
        <DataTable
          caption="Suites ordered by failure rate"
          rows={dash.data.suites}
          rowKey={(s) => s.name}
          initialSort={{ key: "failure", dir: "desc" }}
          columns={[
            { key: "suite", header: "Suite", render: (s) => s.name, sort: (s) => s.name },
            { key: "exec", header: "Executions", render: (s) => s.total_executions.toLocaleString(), sort: (s) => s.total_executions, numeric: true },
            { key: "failed", header: "Failures", render: (s) => s.failed.toLocaleString(), sort: (s) => s.failed, numeric: true },
            { key: "failure", header: "Failure rate", render: (s) => pct(s.failure_rate), sort: (s) => s.failure_rate, numeric: true },
            {
              key: "pass",
              header: "Pass rate",
              render: (s) => (
                <span className="inline-meter">
                  <Meter value={s.pass_rate} label={`${s.name} pass rate`} />
                  {pct(s.pass_rate)}
                </span>
              ),
              sort: (s) => s.pass_rate,
              numeric: true,
            },
          ]}
        />
      </Panel>

      <details className="disclosure">
        <summary>Breakdowns by browser and branch, and newly failing tests</summary>
        <div className="grid-even">
          {[
            ["Browser", dash.data.browsers],
            ["Branch", dash.data.branches],
          ].map(([label, rows]) => (
            <DataTable
              key={label as string}
              caption={`Breakdown by ${(label as string).toLowerCase()}`}
              rows={rows as Dashboard["browsers"]}
              rowKey={(r) => r.name}
              columns={[
                { key: "n", header: label as string, render: (r) => r.name },
                { key: "e", header: "Executions", render: (r) => r.total_executions.toLocaleString(), numeric: true },
                { key: "p", header: "Pass rate", render: (r) => pct(r.pass_rate), numeric: true },
              ]}
            />
          ))}
        </div>
        <DataTable
          caption="Failures after the previous eligible observation passed"
          rows={dash.data.newly_failing}
          rowKey={(r) => `${r.test_id}-${r.run_id}`}
          empty={<p className="muted small">No newly failing observations in this scope.</p>}
          columns={[
            { key: "t", header: "Test", render: (r) => <Link to={`/tests/${r.test_id}`}>{r.name}</Link> },
            { key: "r", header: "Failing run", render: (r) => r.run_id, numeric: true },
            { key: "l", header: "Last passing run", render: (r) => r.last_passing_run_id, numeric: true },
            { key: "c", header: "Commit", render: (r) => <span className="mono">{shortSha(r.commit_sha)}</span> },
          ]}
        />
      </details>
    </div>
  )
}
