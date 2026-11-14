# Test strategy

## Layers

| Layer | What it validates | Isolation |
|---|---|---|
| Unit | Parser contracts, duration/status/retry edges, normalization, scoring labels/formulas, classification signals, empty histories, evaluation accounting | Pure functions or an in-memory SQLite fixture |
| Integration | Transactional persistence, duplicates/conflicts, multipart API, auth/allowlist, filters, actual CommerceGuard projections, mocked GitHub transports, archive boundaries | Fresh schema per test; no network for mocked GitHub |
| PostgreSQL | Actual migrated relational persistence, retry relationships, duplicate constraints | Isolated `flakeguard_test` database; outer transaction rollback |
| Live API | Seeded PostgreSQL data queried over actual HTTP; exact known metric denominators and summary generation | Opt-in `FLAKEGUARD_E2E=1`; services already running |
| Browser | All five Streamlit pages, real charts/tables, UI report upload and API persistence, JavaScript errors, screenshots | Real headless Chromium + API + PostgreSQL |
| Demonstration/evaluation | Generated reports through the same ingestion path; actual failing pytest reports; classification confusion matrix and import benchmark | Explicit synthetic/injected/real provenance |

## Commands

```bash
pytest
ruff check .
ruff format --check .
mypy src/flakeguard
alembic check
python scripts/check_postgres.py
```

The default run skips PostgreSQL if no isolated test URL is set, and skips live E2E unless explicitly enabled. The PostgreSQL helper applies migrations and schema-drift checks, then runs the suite with that URL. Its fixture checks the database name contains `test` and rolls back writes after each marked test. The application's stored demo is never used as the transactional test fixture.

For live services with the standard demo, set `FLAKEGUARD_E2E=1` and run `pytest tests/e2e`. Run `python -m playwright install chromium` and `python scripts/browser_check.py` for UI verification. The browser script intentionally persists one diagnostic test upload under `e2e/browser-validation`; it does not modify existing project results. Repeated identical uploads are idempotent.

## Important checks

- Valid nested Playwright and JUnit reports; explicit retry histories; absent retry metadata stays null.
- Empty/truncated/incorrect JSON/XML, XXE, missing identities, invalid/negative/non-finite durations, retry ordering, size/result limits.
- Content receipt idempotency, rerun attempts, conflicting overlap, ambiguous duplicates, run context mismatches, rollback after a later bad record.
- Stable identity across path separators and repository case; project variants remain separate.
- Denominators for skipped/unknown outcomes, zero denominators, recovered attempts, missing initial information, limited sample sizes, branch partitioning, consistent regressions.
- Old fingerprints remain old under a date filter; cluster counts distinguish attempts from executions.
- API filter validation, timezone validation, body limits, pagination bounds, missing history, optional read/write API-key enforcement.
- GitHub 401/403/404/410/429/5xx, timeouts, pagination, safe signed redirects, token removal across hosts, traversal paths, archive bounds, absent/expired artifacts, retryable states, per-run atomicity.
- Source fixtures from actual CommerceGuard reports verify expected record counts and duplicate behavior.

## Regressions discovered during implementation

1. `GitHubError` inherited `RuntimeError`, so an archive catch block replaced useful validation errors with a generic ZIP message. Preserve intentional validation exceptions before catching ZIP runtime errors.
2. Headerless HTTP 429 became 403. Preserve 429 independently of optional rate-limit headers.
3. `localhost` selected an unrelated IPv6 service on the development workstation. Default local API clients to explicit IPv4 loopback, matching the API bind address.
4. Windows suite path separators could alter stable IDs across operating systems. Normalize separators in identity input and retain project separation.
5. Rerunning actual injected suites under the same run IDs changes durations. Existing completed demo runs are skipped; explicit demo reset is required to regenerate them.

## Evidence and limits

JUnit platform results, coverage JSON, live API results, browser verification JSON, screenshots, and evaluation JSON are under `docs/evidence`. Coverage reports include the dashboard and CLI; their subprocess/browser execution is not automatically counted in unit-test line coverage. No inflated backend-only percentage is presented as whole-project coverage. Strict mypy applies to backend/service code; the dynamically typed Streamlit module is checked by Ruff and actual browser execution.

Mocks validate GitHub request construction and defensive behavior, not service compatibility under real credentials. Docker and Linux CI jobs are defined but were not executed on the Windows development host. The controlled fixture suite intentionally fails; those failures are input data, not platform test failures. Statistical and classification evaluations are explicitly synthetic, with imperfect recall retained in the published evidence.
