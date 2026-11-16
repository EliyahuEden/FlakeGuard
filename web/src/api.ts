export type Params = Record<string, string | number | undefined>

const KEY = "fg_api_key"
export const getKey = (): string => {
  try {
    return sessionStorage.getItem(KEY) ?? ""
  } catch {
    return ""
  }
}
export const setKey = (value: string): void => {
  try {
    if (value) sessionStorage.setItem(KEY, value)
    else sessionStorage.removeItem(KEY)
  } catch {
    /* storage unavailable: the key then lives only until reload */
  }
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

export const qs = (params?: Params): string => {
  const entries = Object.entries(params ?? {}).filter(([, v]) => v !== undefined && v !== "")
  return entries.length ? "?" + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString() : ""
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const key = getKey()
  if (key) headers.set("X-API-Key", key)
  let response: Response
  try {
    response = await fetch(path, { ...init, headers })
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error
    throw new ApiError("Cannot reach the FlakeGuard API. Check that the server is running.", 0)
  }
  if (response.ok) return response
  if (response.status === 401) window.dispatchEvent(new Event("fg-unauthorized"))
  let detail = `Request failed (${response.status})`
  try {
    const body = await response.json()
    if (typeof body.detail === "string") detail = body.detail
    else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join("; ")
  } catch {
    /* non-JSON error body */
  }
  throw new ApiError(detail, response.status)
}

export const get = async <T>(path: string, params?: Params, signal?: AbortSignal): Promise<T> =>
  (await request("/api" + path + qs(params), { signal })).json()

export const post = async <T>(path: string, body: unknown): Promise<T> =>
  (
    await request("/api" + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
  ).json()

export async function uploadReport(file: File, context: Record<string, unknown>): Promise<ImportResult> {
  const form = new FormData()
  form.set("context", JSON.stringify(context))
  form.set("file", file)
  return (await request("/api/imports", { method: "POST", body: form })).json()
}

export const getConfig = async (): Promise<AppConfig> => (await fetch("/config")).json()

export type AppConfig = { read_only: boolean; auth_required: boolean }
export type ImportResult = { imported: number; duplicates: number; warnings?: string[] }

export type Metrics = {
  total_executions: number
  eligible_executions: number
  passed: number
  failed: number
  excluded: number
  pass_rate: number | null
  failure_rate: number | null
  first_attempt_pass_rate: number | null
  first_attempt_observations: number
  retry_recoveries: number
  retry_recovery_rate: number | null
  initially_failed_with_retries: number
  known_retry_observations: number
  suspected_flaky_tests: number
  average_duration_ms: number | null
}
export type Breakdown = Metrics & { name: string }
export type Trend = { date: string; total: number; pass_rate: number | null; average_duration_ms: number | null }
export type Dashboard = {
  metrics: Metrics
  trends: Trend[]
  suites: Breakdown[]
  branches: Breakdown[]
  browsers: Breakdown[]
  newly_failing: { test_id: string; name: string; run_id: number; last_passing_run_id: number; commit_sha: string | null }[]
  note: string
}
export type Options = {
  repositories: string[]
  branches: string[]
  suites: string[]
  browsers: string[]
  environments: string[]
  provenances: string[]
}
export type Run = {
  id: number
  external_id: string
  run_attempt: number
  branch: string
  commit_sha: string | null
  executed_at: string
  provenance: string
  ci_url: string | null
}
export type Reliability = {
  test_id: string
  name: string
  suite: string
  project: string
  browser: string | null
  branch: string
  provenance: string
  repository: string
  observations: number
  distinct_runs: number
  failure_frequency: number | null
  retry_recoveries: number
  known_retry_observations: number
  reliability_score: number | null
  suspicion_score: number | null
  classification: string
  priority: string | null
  last_execution: string | null
  explanation: string
  pass_rate_interval_95: unknown
}
export type Attempt = {
  ordinal: number
  retry_index: number | null
  status: string
  duration_ms: number | null
  error_message: string | null
  stack_trace: string | null
  fingerprint: string | null
  artifacts: { name?: string; content_type?: string; path?: string }[]
}
export type Execution = {
  id: number
  test_id: string
  name: string
  run_id: number
  external_run_id: string
  branch: string
  commit_sha: string | null
  executed_at: string
  provenance: string
  browser: string | null
  environment: string | null
  status: string
  duration_ms: number | null
  retries: number | null
  retry_recovered: boolean | null
  ci_url: string | null
  attempts: Attempt[]
}
export type TestHistory = { test_id: string; total: number; history: Execution[] }
export type Cluster = {
  fingerprint: string
  normalized_text: string
  occurrences: number
  affected_tests: number
  runs: number
  first_seen: string
  last_seen: string
  classification: {
    category: string
    evidence_strength: string
    signals: string[]
    explanation: string
    investigation_steps: string[]
  }
  examples: { name: string; run_id: number; error_message: string | null; stack_trace: string | null }[]
}
export type Failures = {
  clusters: Cluster[]
  similarity_suggestions: Record<string, unknown>[]
  similarity_note: string
}
export type Activity = {
  imports: { id: number; run_id: number; filename: string; format: string; warnings: unknown; imported_at: string }[]
  errors: { id: number; detail: string; created_at: string }[]
  syncs: { run_id: string; run_attempt: number; status: string; detail: string | null; updated_at: string }[]
}
