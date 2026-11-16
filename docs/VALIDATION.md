# Verified validation results

> **Frontend update (React rewrite):** the Streamlit UI described in the 14 November record below was replaced by a React + TypeScript workspace. Local re-verification after the rewrite: 104 passed / 2 skipped pytest tests, ruff and strict mypy clean, `npm run typecheck`, 5 Vitest tests and a production build passing, and `scripts/browser_check.py` / `scripts/ui_interactions.py` passing against the SQLite demo with zero axe-core A/AA violations on five pages. Hosted CI has not yet run on this revision. The dated figures below are unchanged historical evidence.

Recorded on 14 November 2026. Raw evidence lives beside this document in `evidence/`.

## Environment and checks

- Windows, CPython 3.13.0, actual PostgreSQL 18.6 on loopback.
- Platform suite: **101 passed, 1 skipped, zero failures/errors**, 19.49 seconds. The skipped item is the separately enabled live API check.
- Live HTTP suite: **1 passed**, against the seeded PostgreSQL-backed API.
- Chromium: **5/5 pages rendered**, zero JavaScript errors, report uploaded through the original Streamlit UI and retrieved through the API/PostgreSQL.
- Ruff lint and formatting passed; strict mypy passed for 15 backend/service modules (dashboard excluded from strict typing).
- Alembic migration and PostgreSQL schema-drift checks passed. `pip check` found no incompatible installed requirements.
- Whole-package pytest line coverage: **71.62%** (1176/1642 statements). Browser/CLI subprocess coverage is not combined into this figure.
- One upstream TestClient/httpx deprecation warning remains; it does not indicate a failed test.

## Data imported and correctness

| Source | Records | Provenance |
|---|---:|---|
| Seeded daily Playwright histories | 720 | synthetic |
| 12 actually executed controlled pytest runs | 72 | injected |
| Three existing actual CommerceGuard report projections | 119 | 118 real + 1 injected |
| Browser validation upload | 1 | injected; reserved E2E repository |

The repeat demo invocation imported zero new synthetic rows and reported 720 duplicates. Existing executed injected demo runs were skipped. The actual CommerceGuard fixtures are independently checked for expected execution counts and idempotency. XML and JSON are tested through normal parsers, not dashboard constants. Demo reset preservation is covered by integration tests.

## Import throughput

One local **1,000-execution PostgreSQL import** took **8.6514 s**, or **115.59 executions/s**. All 1,000 rows were counted before rollback. Exact reimport recognized 1,000 duplicates in 0.0557 s.

Scope: Single-process parse, normalize, insert, and flush; savepoint rolled back after verification; excludes outer commit, network transfer, and concurrent writers. This is one workstation measurement, not a load-test claim or service capacity guarantee.

## Reliability behavior on the seeded dataset

- 720 total / 600 eligible executions, 456 final passes, 144 final failures, 60 skipped and 60 unknown.
- Final pass rate 76%; first-attempt pass rate 70%; 36 observed retry recoveries from 36 initially failed executions actually retried.
- Six suspected flaky test identities across two explicit browsers, representing three distinct scenario types.
- Scenario detection: **100% precision, 75% recall** over four authored intermittent scenario types. Timing recovery, connection recovery, and shared-state contamination were detected; lower-frequency fixture setup failures remained below the threshold.
- Deterministic regression remained consistently failing. A late sustained regression was not labeled suspected flaky merely because it followed passing runs.

## Synthetic classification evaluation

**32 authored diagnostic cases**, four labels with eight cases each. Accuracy **90.625%**, macro precision **93.18%**, macro recall **90.625%**.

Rows are injected ground-truth labels; columns are heuristic predictions:

| Actual / predicted | Application | Automation | Infrastructure | Unknown |
|---|---:|---:|---:|---:|
| suspected_application | 7 | 0 | 0 | 1 |
| suspected_automation | 0 | 7 | 0 | 1 |
| suspected_infrastructure | 0 | 0 | 7 | 1 |
| unknown | 0 | 0 | 0 | 8 |

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| suspected_application | 1.000 | 0.875 | 0.933 | 8 |
| suspected_automation | 1.000 | 0.875 | 0.933 | 8 |
| suspected_infrastructure | 1.000 | 0.875 | 0.933 | 8 |
| unknown | 0.727 | 1.000 | 0.842 | 8 |

Three ambiguous cases were labeled unknown: an application deadlock with timeout-only diagnostics, a stale selector without explanatory diagnostics, and infrastructure packet loss reported only as a timeout. This is useful abstention but still a recall miss against known injected ground truth.

The set is small, authored, and not independently held out. It shares design assumptions with the rules. These numbers are not estimates of production defect detection accuracy.

## Fingerprinting

Twelve authored diagnostic pairs: six known text-equivalent pairs correctly grouped, six meaningfully different pairs kept separate, zero false merges/splits in that set. Precision and recall 1.0 on these examples. This measures deterministic normalization, not root-cause clustering quality in real incidents.

## Unverified or incomplete scope

- Docker image/Compose startup, PostgreSQL migrations, demo seeding, API/dashboard health, and cleanup passed on GitHub-hosted Linux. Docker remains unavailable on the local Windows machine.
- Live authenticated GitHub synchronization: implemented with transport/error/archive tests; no authorized live repository sync performed.
- Hosted GitHub Actions validation passed: [43580648373](https://github.com/EliyahuEden/FlakeGuard/actions/runs/43580648373), code commit `3b74a76f`. Both `validate` and `compose` jobs succeeded.
- Browser-specific failures in the seeded history are synthetic, not executed Firefox/WebKit regressions.
- No PR-comment writer, scheduled background sync, artifact file hosting, multi-user authorization, calibrated classifier, or deployment.
- Real CommerceGuard reports verify ingestion, not real-world classification accuracy; CommerceGuard was not rerun.

See `COMMANDS_EXECUTED.md`, `TEST_STRATEGY.md`, and the raw JUnit/coverage/evaluation/browser artifacts for audit details.

## Hosted CI evidence

Repository: [EliyahuEden/FlakeGuard](https://github.com/EliyahuEden/FlakeGuard). [Verified workflow run](https://github.com/EliyahuEden/FlakeGuard/actions/runs/43580648373); exact code commit `3b74a76fbe53ebca7fe34c2592f8a62662090030`. Metadata and individual step outcomes are recorded in `evidence/hosted-actions.json`.
