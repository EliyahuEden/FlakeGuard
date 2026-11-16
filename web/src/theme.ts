export const STATUS_COLOR: Record<string, string> = {
  passed: "#9fc6ac",
  failed: "#f0a1a7",
  timedOut: "#dcc39c",
  skipped: "#7f7f89",
  unknown: "#7f7f89",
  interrupted: "#bcb0d7",
}
export const STATUSES = ["passed", "failed", "timedOut", "skipped", "interrupted", "unknown"] as const
export const CHART = { line: "#ededf2", grid: "rgba(255,255,255,.07)", axis: "#8d8d98" }
