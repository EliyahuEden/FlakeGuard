# Interview explanation

## About 90 seconds

“CI systems produce a pass or fail, but engineers still have to decide whether a failure is a product regression, an unreliable test, or a broken environment. Retries often hide the history that would help answer that question.

I built FlakeGuard as a Python modular monolith. FastAPI exposes ingestion and analysis, PostgreSQL stores normalized runs, executions and retry attempts, and a typed React and TypeScript workspace, served by the same FastAPI process, visualizes the same API results. It imports standard Playwright JSON and JUnit XML through a CLI, HTTP API, or a read-only GitHub Actions artifact client.

The hardest parts were preserving the semantics of different report formats, making ingestion idempotent and atomic, and avoiding misleading analytics. JUnit usually cannot tell us about retries, so those metrics stay unknown. I separate branches and environments before scoring, and distinguish a consistent regression from intermittent pass/fail behavior.

The analysis uses explainable retry recovery and across-run alternation signals. Versioned diagnostic fingerprints identify recurring text, and heuristic classifications show evidence and next investigation steps instead of claiming a root cause. I evaluated the implementation with seeded histories, actual controlled pytest runs, and actual CommerceGuard report output. It identified three of four injected intermittent scenario types, and classified 29 of 32 synthetic diagnostic cases correctly. The misses remain documented.

The platform can point an engineer toward useful evidence. It cannot prove that a timeout is harmless, that two similar errors share a cause, or that a particular commit introduced a defect. I deliberately kept the original quality gates authoritative.”

## Technical follow-ups

- **Why no ML?** The dataset is too small to justify an opaque model. Deterministic rules establish a measured baseline and make errors inspectable.
- **How is a retry modeled?** A logical execution belongs to one run; individual attempts retain their source retry index, status, duration, diagnostics, and artifacts. Only observed recovery contributes to retry evidence.
- **How do duplicates work?** Content receipts prevent exact reimports; unique semantic execution keys protect overlapping reports; conflicting observations roll back. Database constraints handle races, with safe retry after a concurrent conflict.
- **How are downloads protected?** Actions-read permissions, server repository allowlist, token stripped from signed-storage redirects, bounded streaming and ZIP decompression, no extraction or execution of downloaded files.
- **How is it tested?** Parser/analysis units, transactional API and mocked-transport integration, actual PostgreSQL persistence, and live HTTP/browser checks. Synthetic evaluation is separated from real ingestion evidence.
- **What would scale first?** Push aggregations into indexed SQL, paginate histories, materialize expensive trends, introduce background sync checkpoints, and add multi-user authentication before shared hosting.
- **What remains unverified?** Live authenticated GitHub artifact synchronization and a hosted application deployment. Docker/Linux startup and platform validation have passed on GitHub-hosted runners; the local Windows machine still has no Docker installation.
