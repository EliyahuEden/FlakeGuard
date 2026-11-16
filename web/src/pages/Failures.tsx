import { useState } from "react"
import type { Failures as FailureData } from "../api"
import { dateTime, humanize } from "../format"
import { useApi, usePageTitle } from "../state"
import { CodeBlock, Empty, ErrorState, Notice, Panel, Skeleton } from "../ui"

export function Failures() {
  usePageTitle("Failure Analysis")
  const { data, error, reload } = useApi<FailureData>("/failures")
  const [selected, setSelected] = useState(0)

  if (error) return <ErrorState message={error} onRetry={reload} />
  if (!data) return <Skeleton rows={9} height={22} />
  const clusters = data.clusters
  const cluster = clusters[Math.min(selected, clusters.length - 1)]

  return (
    <div className="stack">
      <Notice tone="warn">
        A shared fingerprint means matching normalized diagnostics. It does not establish a shared root cause.
      </Notice>
      {!cluster ? (
        <Empty title="No failed attempts match these filters">
          Failure patterns appear once reports containing failed attempts are imported.
        </Empty>
      ) : (
        <div className="split master-detail">
          <Panel title={`${clusters.length} failure pattern${clusters.length === 1 ? "" : "s"}`} className="pattern-list">
            <ul className="pattern-items">
              {clusters.map((c, index) => (
                <li key={c.fingerprint}>
                  <button
                    aria-current={c === cluster ? "true" : undefined}
                    onClick={() => setSelected(index)}
                  >
                    <span className="mono small">{c.fingerprint.slice(0, 12)}</span>
                    <span className="pattern-text">{c.normalized_text}</span>
                    <span className="muted small">
                      {c.occurrences} attempts · {c.affected_tests} tests · {c.runs} runs
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Panel>

          <div className="stack">
            <Panel
              title="Normalized diagnostic"
              note={`First seen ${dateTime(cluster.first_seen)} · last seen ${dateTime(cluster.last_seen)} (UTC)`}
            >
              <CodeBlock label="Normalized failure text">{cluster.normalized_text}</CodeBlock>
              <p className="small">
                <span className="tag">{humanize(cluster.classification.category)}</span>{" "}
                <span className="muted">{cluster.classification.evidence_strength} evidence</span>
              </p>
              <p>{cluster.classification.explanation}</p>
            </Panel>

            <div className="grid-even">
              <Panel title="Supporting evidence">
                <ul className="bullets">
                  {cluster.classification.signals.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </Panel>
              <Panel title="Investigation steps">
                <ol className="bullets">
                  {cluster.classification.investigation_steps.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ol>
              </Panel>
            </div>

            <Panel title="Examples">
              {cluster.examples.map((example, i) => (
                <details className="disclosure" key={`${example.name}-${example.run_id}-${i}`}>
                  <summary>
                    {example.name} <span className="muted small">· run {example.run_id}</span>
                  </summary>
                  <CodeBlock label={`Diagnostic for ${example.name}`}>
                    {example.error_message || example.stack_trace || "No diagnostic text"}
                  </CodeBlock>
                  {example.stack_trace && example.error_message && (
                    <CodeBlock label={`Stack trace for ${example.name}`}>{example.stack_trace}</CodeBlock>
                  )}
                </details>
              ))}
            </Panel>

            {data.similarity_suggestions.length > 0 && (
              <details className="disclosure">
                <summary>Similar wording (kept as separate patterns)</summary>
                <p className="muted small">{data.similarity_note}</p>
                <CodeBlock label="Similarity suggestions">{JSON.stringify(data.similarity_suggestions, null, 2)}</CodeBlock>
              </details>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
