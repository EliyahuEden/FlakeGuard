export const pct = (value: number | null | undefined, digits = 1): string =>
  value === null || value === undefined ? "—" : `${(value * 100).toFixed(digits)}%`

export const score = (value: number | null | undefined): string =>
  value === null || value === undefined ? "—" : value.toFixed(1)

export function duration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—"
  if (ms < 1000) return `${Math.round(ms)} ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(2)} s`
  return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "—"
  return date.toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  })
}

export const shortSha = (sha: string | null | undefined): string => (sha ? sha.slice(0, 8) : "unknown")

export const humanize = (value: string): string =>
  value
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/^./, (c) => c.toUpperCase())

/** RFC 4180 CSV with formula-injection protection for spreadsheet imports. */
export function toCsv(rows: Record<string, unknown>[]): string {
  if (!rows.length) return ""
  const headers = Object.keys(rows[0])
  const cell = (raw: unknown): string => {
    let text = raw === null || raw === undefined ? "" : typeof raw === "object" ? JSON.stringify(raw) : String(raw)
    if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`
    return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
  }
  return [headers.join(","), ...rows.map((row) => headers.map((h) => cell(row[h])).join(","))].join("\n")
}
