import { describe, expect, it } from "vitest"
import { duration, humanize, pct, shortSha, toCsv } from "./format"

describe("format", () => {
  it("keeps missing values distinct from zero", () => {
    expect(pct(null)).toBe("—")
    expect(pct(0)).toBe("0.0%")
    expect(duration(undefined)).toBe("—")
  })
  it("formats durations across scales", () => {
    expect(duration(420)).toBe("420 ms")
    expect(duration(1500)).toBe("1.50 s")
    expect(duration(125_000)).toBe("2m 5s")
  })
  it("humanizes snake and camel case", () => {
    expect(humanize("suspected_flaky")).toBe("Suspected flaky")
    expect(humanize("timedOut")).toBe("Timed Out")
  })
  it("truncates commits and handles unknown", () => {
    expect(shortSha("0123456789abcdef")).toBe("01234567")
    expect(shortSha(null)).toBe("unknown")
  })
  it("escapes CSV cells and neutralizes spreadsheet formulas", () => {
    const csv = toCsv([{ a: 'x,"y"', b: "=SUM(A1)", c: null }])
    expect(csv).toBe(`a,b,c\n"x,""y""",'=SUM(A1),`)
  })
})
