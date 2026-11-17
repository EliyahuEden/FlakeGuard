# Importing reports

FlakeGuard reads standard Playwright JSON and JUnit XML. This page is the reference for
how reports are imported, what is and is not inferred, and how the HTTP API behaves.

## Command line

```bash
flakeguard import examples/reports/commerceguard-regression.json \
  --repository portfolio/commerceguard --run-id local-regression-001 --branch main
```

Use a stable run ID when re-importing the same execution. GitHub reruns use
`--run-attempt`; test retries remain separate attempts within an execution.
Branch, commit and provenance conflicts, or conflicting overlapping results, are
rejected rather than silently overwritten.

## HTTP API

The API returns 201 for successful or idempotent imports, 409 for conflicting existing
observations, 422 for malformed input and 413 for oversized reports.

```bash
curl -X POST http://127.0.0.1:8000/api/imports \
  -F 'context={"repository":"acme/shop","run_id":"123","branch":"main","provenance":"real"}' \
  -F 'file=@results.json'
```

If `FLAKEGUARD_API_KEY` is set, send `X-API-Key` for all `/api` reads and writes. The
workspace asks for the key once per browser tab (kept in `sessionStorage`, sent only to
its own origin) and drops it on a 401. `/config` is the only unauthenticated endpoint and
exposes just the read-only and key-required flags. See `.env.example` for every setting.
API validation errors omit submitted values, and imported diagnostics redact common
credential patterns; avoid putting secrets in test diagnostics in the first place.

## Report semantics

- **Playwright:** nested suites and specs, project name, repeat index, observed results
  and retry indices, errors and stacks, timestamps, attachment metadata. Browser is read
  only from explicit `config.projects[].use.browserName` or the provided import context.
  A project named `chromium` alone is not proof of browser metadata.
- **JUnit:** nested suites, testcase and classname identity, seconds converted to
  milliseconds, failure, error and skipped outcomes, optional explicit suite properties
  for environment, browser and project. Retry information is **unknown** for ordinary
  JUnit. Retry extensions are warned about and not guessed.
- Missing execution timestamps use a clearly labeled ingestion-time fallback.
  Timezone-less JUnit timestamps are not assumed to be UTC.
- Missing test names and malformed documents are rejected atomically. Missing optional
  data remains null. Tests with no results remain `unknown`.
- Default bounds: 20 MiB report, 100,000 results, 50 MiB archive and decompressed total,
  200 archive entries, compression ratio at most 200. XML entities are disabled. ZIP
  members are inspected in memory and never extracted.
- Import **one report format per suite and run**. JSON and JUnit may use different
  identities and cannot universally be reconciled. Repeated JUnit testcase identities in
  one report are rejected as ambiguous; provide unique parameterized names.

Enable the Playwright reporter with
`reporter: [['json', { outputFile: 'test-results/results.json' }]]`. See the
[official reporter documentation](https://playwright.dev/docs/test-reporters).

## Using CommerceGuard reports

CommerceGuard's `playwright.config.ts` writes both JSON and JUnit reports. FlakeGuard was
tested against **119 execution records from three existing actual reports**: 117
regression records, one controlled injected failure and one restored execution. Source
relative paths, original SHA-256 hashes, provenance and report timestamps are recorded in
[the integration evidence](evidence/commerceguard.json).

The bundled files are sanitized projections: machine paths, stdout and stderr, embedded
attachment bodies and unnecessary configuration are removed. They were ingested and
tested; CommerceGuard itself was not rerun for that evidence.

```bash
python scripts/import_examples.py
# To capture the same reports again from a separate checkout:
python scripts/capture_commerceguard.py ../CommerceGuard
# To import fresh CommerceGuard output:
flakeguard import ../CommerceGuard/test-results/results.json \
  --repository your-owner/CommerceGuard --run-id your-unique-run --branch main
```
