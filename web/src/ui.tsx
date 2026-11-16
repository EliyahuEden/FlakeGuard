import { AlertTriangle, ArrowDown, ArrowUp, ChevronsUpDown, Inbox } from "lucide-react"
import { useMemo, useState, type ReactNode } from "react"
import { humanize } from "./format"
import { STATUS_COLOR } from "./theme"

export function Panel({
  title,
  note,
  actions,
  children,
  className = "",
}: {
  title?: string
  note?: string
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`panel ${className}`} aria-label={title}>
      {(title || actions) && (
        <header className="panel-head">
          <div>
            {title && <h2>{title}</h2>}
            {note && <p className="muted small">{note}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}

export function Skeleton({ rows = 4, height = 18 }: { rows?: number; height?: number }) {
  return (
    <div className="skeleton" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <span key={i} style={{ height, width: `${92 - ((i * 13) % 40)}%` }} />
      ))}
    </div>
  )
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      <Inbox size={20} aria-hidden="true" />
      <strong>{title}</strong>
      {children && <p>{children}</p>}
      {action}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error-state" role="alert">
      <AlertTriangle size={18} aria-hidden="true" />
      <div>
        <strong>Could not load this data</strong>
        <p>{message}</p>
      </div>
      {onRetry && (
        <button className="btn" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  )
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn"; children: ReactNode }) {
  return (
    <p className={`notice ${tone}`} role={tone === "warn" ? "note" : undefined}>
      {children}
    </p>
  )
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className="badge">
      <i style={{ background: STATUS_COLOR[status] ?? STATUS_COLOR.unknown }} aria-hidden="true" />
      {humanize(status)}
    </span>
  )
}

export function Segmented({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: string[]
  value: string
  onChange: (value: string) => void
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button key={option} aria-pressed={option === value} onClick={() => onChange(option)}>
          {option}
        </button>
      ))}
    </div>
  )
}

export function Meter({ value, label }: { value: number | null; label: string }) {
  const width = value === null ? 0 : Math.max(0, Math.min(1, value)) * 100
  return (
    <div
      className="meter"
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(width)}
    >
      <span style={{ width: `${width}%` }} />
    </div>
  )
}

export type Column<T> = {
  key: string
  header: string
  render: (row: T) => ReactNode
  sort?: (row: T) => number | string | null
  numeric?: boolean
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  selectedKey,
  caption,
  initialSort,
  pageSize = 50,
  empty,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  selectedKey?: string | null
  caption: string
  initialSort?: { key: string; dir: "asc" | "desc" }
  pageSize?: number
  empty?: ReactNode
}) {
  const [sort, setSort] = useState(initialSort ?? null)
  const [visible, setVisible] = useState(pageSize)
  const sorted = useMemo(() => {
    const column = columns.find((c) => c.key === sort?.key)
    if (!column?.sort || !sort) return rows
    const get = column.sort
    const direction = sort.dir === "asc" ? 1 : -1
    return [...rows].sort((a, b) => {
      const x = get(a)
      const y = get(b)
      if (x === y) return 0
      if (x === null) return 1
      if (y === null) return -1
      return (x < y ? -1 : 1) * direction
    })
  }, [rows, sort, columns])

  if (!rows.length) return <>{empty}</>
  const toggle = (key: string) =>
    setSort((current) => (current?.key === key && current.dir === "desc" ? { key, dir: "asc" } : { key, dir: "desc" }))

  return (
    <div className="table-wrap" tabIndex={0} role="region" aria-label={caption}>
      <table>
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => {
              const active = sort?.key === column.key
              return (
                <th
                  key={column.key}
                  scope="col"
                  className={column.numeric ? "num" : undefined}
                  aria-sort={active ? (sort!.dir === "asc" ? "ascending" : "descending") : undefined}
                >
                  {column.sort ? (
                    <button className="th-button" onClick={() => toggle(column.key)}>
                      {column.header}
                      {active ? (
                        sort!.dir === "asc" ? <ArrowUp size={12} aria-hidden="true" /> : <ArrowDown size={12} aria-hidden="true" />
                      ) : (
                        <ChevronsUpDown size={12} aria-hidden="true" className="dim" />
                      )}
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.slice(0, visible).map((row) => {
            const key = rowKey(row)
            return (
              <tr key={key} data-selected={key === selectedKey || undefined}>
                {columns.map((column) => (
                  <td key={column.key} className={column.numeric ? "num" : undefined}>
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
      {sorted.length > visible && (
        <div className="table-more">
          <span className="muted small">
            Showing {visible.toLocaleString()} of {sorted.length.toLocaleString()}
          </span>
          <button className="btn" onClick={() => setVisible((v) => v + pageSize)}>
            Show {Math.min(pageSize, sorted.length - visible)} more
          </button>
        </div>
      )}
    </div>
  )
}

export function CodeBlock({ children, label }: { children: string; label: string }) {
  return (
    <pre className="code" tabIndex={0} aria-label={label}>
      {children}
    </pre>
  )
}
