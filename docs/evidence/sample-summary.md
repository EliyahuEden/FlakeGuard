# FlakeGuard quality summary

Repository **demo/commerce**, branch **main**, commit `000000000000000000000000000000000000001d`.
Provenance: **synthetic**. 24 executions; 5 final failures; 0 observed retry recoveries.

Suspected flakiness is an investigation signal. Required quality gates remain authoritative.

## Failed tests

| Test | Status | Historical context |
|---|---|---|
| checkout regression [chromium; chromium] | failed | 30 observations; consistently_failing |
| checkout regression [firefox; firefox] | failed | 30 observations; consistently_failing |
| browser-specific failure [firefox; firefox] | failed | 30 observations; consistently_failing |
| new regression [chromium; chromium] | failed | 30 observations; intermittent_failures |
| new regression [firefox; firefox] | failed | 30 observations; intermittent_failures |

## Suspected flaky tests

- shared-state contamination [chromium; chromium]: 0 observed retry recoveries across 30 observations.
- shared-state contamination [firefox; firefox]: 0 observed retry recoveries across 30 observations.
- timing recovery [chromium; chromium]: 10 observed retry recoveries across 30 observations.
- timing recovery [firefox; firefox]: 10 observed retry recoveries across 30 observations.
- connection recovery [chromium; chromium]: 8 observed retry recoveries across 30 observations.
- connection recovery [firefox; firefox]: 8 observed retry recoveries across 30 observations.

## Failure patterns and next steps

- `0b21e6016013` — 2 failed attempts; previously observed; suspected_application (moderate evidence). Validate the assertion and test data against the product contract.
- `fbfeb05327d1` — 2 failed attempts; previously observed; suspected_application (moderate evidence). Validate the assertion and test data against the product contract.
- `ab4e2953bbd0` — 1 failed attempts; previously observed; suspected_application (moderate evidence). Validate the assertion and test data against the product contract.

Fingerprints group diagnostic text, not proven root causes. Unknown retry data is excluded from retry denominators.
