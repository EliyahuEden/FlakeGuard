import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react"
import { get, qs, type AppConfig, type Params } from "./api"

export type Filters = Record<string, string>

type AppState = {
  config: AppConfig
  filters: Filters
  setFilter: (key: string, value: string) => void
  clearFilters: () => void
  params: Params
  version: number
  refresh: () => void
}

const Context = createContext<AppState | null>(null)

export function AppProvider({ config, children }: { config: AppConfig; children: ReactNode }) {
  const [filters, setFilters] = useState<Filters>({})
  const [version, setVersion] = useState(0)
  const setFilter = useCallback(
    (key: string, value: string) =>
      setFilters((current) => {
        const next = { ...current }
        if (value) next[key] = value
        else delete next[key]
        return next
      }),
    [],
  )
  const value = useMemo<AppState>(
    () => ({
      config,
      filters,
      setFilter,
      clearFilters: () => setFilters({}),
      params: filters,
      version,
      refresh: () => setVersion((v) => v + 1),
    }),
    [config, filters, setFilter, version],
  )
  return <Context.Provider value={value}>{children}</Context.Provider>
}

export function useApp(): AppState {
  const value = useContext(Context)
  if (!value) throw new Error("AppProvider missing")
  return value
}

type Fetched<T> = { data?: T; error?: string; loading: boolean }

/** Fetches an API resource under the active workspace filters. Stale data stays visible while reloading. */
export function useApi<T>(path: string | null, extra?: Params, scoped = true): Fetched<T> & { reload: () => void } {
  const { params, version, refresh } = useApp()
  const merged = scoped ? { ...params, ...extra } : extra
  const key = path ? `${path}${qs(merged)}#${version}` : ""
  const [state, setState] = useState<Fetched<T>>({ loading: Boolean(path) })

  useEffect(() => {
    if (!path) {
      setState({ loading: false })
      return
    }
    const controller = new AbortController()
    setState((s) => ({ ...s, loading: true, error: undefined }))
    get<T>(path, merged, controller.signal)
      .then((data) => setState({ data, loading: false }))
      .catch((error: Error) => {
        if (error.name !== "AbortError") setState((s) => ({ ...s, loading: false, error: error.message }))
      })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  return { ...state, reload: refresh }
}

let firstPage = true

/** Sets the document title; after in-app navigation, moves focus to the page heading. */
export function usePageTitle(title: string): void {
  useEffect(() => {
    document.title = `${title} · FlakeGuard`
    if (firstPage) {
      // The initial load keeps the skip link as the first tab stop.
      firstPage = false
      return
    }
    document.getElementById("page-title")?.focus({ preventScroll: true })
  }, [title])
}

export function useDebounced<T>(value: T, delay = 200): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}
