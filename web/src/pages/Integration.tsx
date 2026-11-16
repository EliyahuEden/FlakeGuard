import { UploadCloud } from "lucide-react"
import { useState, type FormEvent } from "react"
import { ApiError, post, uploadReport, type Activity } from "../api"
import { dateTime } from "../format"
import { useApi, useApp, usePageTitle } from "../state"
import { DataTable, Empty, ErrorState, Notice, Panel, Skeleton } from "../ui"

type Message = { tone: "ok" | "error"; text: string } | null

function Feedback({ message }: { message: Message }) {
  return (
    <p className={`feedback ${message?.tone ?? ""}`} role={message?.tone === "error" ? "alert" : "status"} aria-live="polite">
      {message?.text}
    </p>
  )
}

export function Integration() {
  usePageTitle("CI Integration")
  const { config, refresh } = useApp()
  const locked = config.read_only
  const activity = useApi<Activity>("/imports", undefined, false)

  const [file, setFile] = useState<File | null>(null)
  const [form, setForm] = useState({ repository: "local/project", run_id: "", branch: "main", commit_sha: "", provenance: "real" })
  const [uploading, setUploading] = useState(false)
  const [uploadMessage, setUploadMessage] = useState<Message>(null)

  const [github, setGithub] = useState({ repository: "", pattern: "*test-results*", max_runs: 20 })
  const [syncing, setSyncing] = useState(false)
  const [githubMessage, setGithubMessage] = useState<Message>(null)

  const [tab, setTab] = useState<"imports" | "errors" | "syncs">("imports")

  const fail = (error: unknown): Message => ({ tone: "error", text: error instanceof ApiError ? error.message : "Request failed. Check import status before retrying." })

  async function submitUpload(event: FormEvent) {
    event.preventDefault()
    if (!file || !form.run_id.trim()) {
      setUploadMessage({ tone: "error", text: "Choose a report and supply a stable run identifier." })
      return
    }
    setUploading(true)
    setUploadMessage(null)
    try {
      const result = await uploadReport(file, {
        repository: form.repository,
        run_id: form.run_id,
        branch: form.branch,
        commit_sha: form.commit_sha || null,
        provenance: form.provenance,
      })
      setUploadMessage({ tone: "ok", text: `Imported ${result.imported} executions; ${result.duplicates} duplicates ignored.` })
      refresh()
    } catch (error) {
      setUploadMessage(fail(error))
    } finally {
      setUploading(false)
    }
  }

  async function github_(action: "configure" | "sync") {
    setSyncing(true)
    setGithubMessage(null)
    try {
      if (action === "configure") {
        await post("/repositories", { name: github.repository, github_enabled: true })
        setGithubMessage({ tone: "ok", text: "Repository configured for synchronization." })
      } else {
        const result = await post<{ runs: unknown[] }>("/github/sync", {
          repository: github.repository,
          max_runs: github.max_runs,
          artifact_pattern: github.pattern,
        })
        setGithubMessage({ tone: "ok", text: `Checked ${result.runs.length} recent runs.` })
        refresh()
      }
    } catch (error) {
      setGithubMessage(fail(error))
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="stack">
      {locked && (
        <Notice tone="warn">
          Read-only demonstration. Import and GitHub synchronization are available in the full local platform; this
          instance only displays its labeled demonstration history.
        </Notice>
      )}
      <div className="grid-even">
        <Panel title="Import a local report" note="Standard Playwright JSON or JUnit XML. Retry metadata is preserved only when supplied.">
          <form className="form" onSubmit={submitUpload}>
            <label className={`dropzone ${file ? "filled" : ""}`}>
              <UploadCloud size={20} aria-hidden="true" />
              <span>{file ? file.name : "Choose a .json or .xml report"}</span>
              <small className="muted">{file ? `${(file.size / 1024).toFixed(1)} KB` : "Up to 20 MiB"}</small>
              <input type="file" accept=".json,.xml" disabled={locked} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </label>
            <label className="field">
              <span>Repository</span>
              <input value={form.repository} onChange={(e) => setForm({ ...form, repository: e.target.value })} disabled={locked} required />
            </label>
            <label className="field">
              <span>Unique run identifier</span>
              <input
                value={form.run_id}
                onChange={(e) => setForm({ ...form, run_id: e.target.value })}
                placeholder="local-2026-11-14-001"
                disabled={locked}
                required
              />
              <small className="muted">Reuse the same identifier to re-import the same execution safely.</small>
            </label>
            <div className="row">
              <label className="field">
                <span>Branch</span>
                <input value={form.branch} onChange={(e) => setForm({ ...form, branch: e.target.value })} disabled={locked} />
              </label>
              <label className="field">
                <span>Commit SHA (optional)</span>
                <input value={form.commit_sha} onChange={(e) => setForm({ ...form, commit_sha: e.target.value })} disabled={locked} />
              </label>
            </div>
            <label className="field">
              <span>Report provenance</span>
              <select value={form.provenance} onChange={(e) => setForm({ ...form, provenance: e.target.value })} disabled={locked}>
                <option value="real">Real</option>
                <option value="injected">Injected</option>
                <option value="synthetic">Synthetic</option>
              </select>
            </label>
            <button className="btn primary" disabled={locked || uploading}>
              {uploading ? "Importing…" : "Import report"}
            </button>
            <Feedback message={uploadMessage} />
          </form>
        </Panel>

        <Panel title="GitHub Actions" note="The server must allowlist the repository in GITHUB_REPOSITORIES. Read-only token scope is enough.">
          <form className="form" onSubmit={(e) => { e.preventDefault(); void github_("sync") }}>
            <label className="field">
              <span>GitHub repository</span>
              <input value={github.repository} onChange={(e) => setGithub({ ...github, repository: e.target.value })} placeholder="owner/repository" disabled={locked} required />
            </label>
            <label className="field">
              <span>Report artifact name pattern</span>
              <input value={github.pattern} onChange={(e) => setGithub({ ...github, pattern: e.target.value })} disabled={locked} />
              <small className="muted">Export JSON into a dedicated artifact so HTML and duplicate JUnit files are not imported.</small>
            </label>
            <label className="field">
              <span>Recent completed runs</span>
              <input
                type="number"
                min={1}
                max={100}
                value={github.max_runs}
                onChange={(e) => setGithub({ ...github, max_runs: Number(e.target.value) })}
                disabled={locked}
              />
            </label>
            <div className="row">
              <button type="button" className="btn" disabled={locked || syncing || !github.repository} onClick={() => void github_("configure")}>
                Configure repository
              </button>
              <button className="btn primary" disabled={locked || syncing || !github.repository}>
                {syncing ? "Working…" : "Synchronize now"}
              </button>
            </div>
            <Feedback message={githubMessage} />
            <p className="muted small">Choose one report format per suite so JSON and JUnit are not counted as separate test identities.</p>
          </form>
        </Panel>
      </div>

      <Panel title="Ingestion activity">
        <div className="tabs" role="tablist" aria-label="Ingestion activity">
          {(["imports", "errors", "syncs"] as const).map((key) => (
            <button key={key} role="tab" id={`tab-${key}`} aria-selected={tab === key} aria-controls="activity-panel" onClick={() => setTab(key)}>
              {{ imports: "Reports", errors: "Errors", syncs: "GitHub runs" }[key]}
              {activity.data && <span className="count">{activity.data[key].length}</span>}
            </button>
          ))}
        </div>
        <div id="activity-panel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
          {activity.error ? (
            <ErrorState message={activity.error} onRetry={activity.reload} />
          ) : !activity.data ? (
            <Skeleton rows={4} />
          ) : tab === "imports" ? (
            <DataTable
              caption="Imported reports"
              rows={activity.data.imports}
              rowKey={(r) => String(r.id)}
              empty={<Empty title="No reports imported yet">Upload a report above to see its receipt here.</Empty>}
              columns={[
                { key: "run", header: "Run", render: (r) => r.run_id, numeric: true },
                { key: "file", header: "File", render: (r) => r.filename },
                { key: "fmt", header: "Format", render: (r) => r.format },
                { key: "warn", header: "Warnings", render: (r) => (Array.isArray(r.warnings) ? r.warnings.length : r.warnings ? 1 : 0), numeric: true },
                { key: "at", header: "Imported (UTC)", render: (r) => dateTime(r.imported_at), numeric: true },
              ]}
            />
          ) : tab === "errors" ? (
            <DataTable
              caption="Ingestion errors"
              rows={activity.data.errors}
              rowKey={(r) => String(r.id)}
              empty={<Empty title="No ingestion errors">Rejected or conflicting reports are recorded here.</Empty>}
              columns={[
                { key: "detail", header: "Detail", render: (r) => r.detail },
                { key: "at", header: "Recorded (UTC)", render: (r) => dateTime(r.created_at), numeric: true },
              ]}
            />
          ) : (
            <DataTable
              caption="GitHub synchronization state"
              rows={activity.data.syncs}
              rowKey={(r) => `${r.run_id}-${r.run_attempt}`}
              empty={<Empty title="No GitHub runs synchronized">Configure a repository to start importing CI artifacts.</Empty>}
              columns={[
                { key: "run", header: "Run", render: (r) => `${r.run_id} · attempt ${r.run_attempt}` },
                { key: "status", header: "Status", render: (r) => r.status },
                { key: "detail", header: "Detail", render: (r) => r.detail ?? "—" },
                { key: "at", header: "Updated (UTC)", render: (r) => dateTime(r.updated_at), numeric: true },
              ]}
            />
          )}
        </div>
      </Panel>
    </div>
  )
}
