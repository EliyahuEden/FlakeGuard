# Local setup

The README has the fastest path (Docker Compose, or Python plus the built workspace).
This page covers the native setup in more detail.

## Native Python and PostgreSQL

Requires **Python 3.13**. Windows PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install --no-deps -e .
Copy-Item .env.example .env
# Configure DATABASE_URL for an existing local PostgreSQL database.
flakeguard migrate
flakeguard demo --with-local
python scripts/import_examples.py
uvicorn flakeguard.api:app --host 127.0.0.1 --port 8000
```

Linux and macOS:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.lock
pip install --no-deps -e .
cp .env.example .env
```

Then use the same `flakeguard` and `uvicorn` commands after configuring PostgreSQL.

## Building the workspace

Build the React workspace once (Node 20.19+ or 22) and the API serves it at
<http://127.0.0.1:8000>:

```bash
cd web
npm ci
npm run build   # typechecks, then writes src/flakeguard/web
```

For frontend development run `npm run dev` in `web/` (port 5173, proxying the API on
8000). Without a build the API still works; only the browser workspace is absent.

## A local PostgreSQL on Windows

An optional helper initializes a separate cluster from an existing PostgreSQL binary
distribution:

```powershell
# Run before creating .env; it generates a local password into ignored .env.
./scripts/postgres.ps1 -PostgresBin 'C:\path\to\postgres\bin'
# Stop only this FlakeGuard cluster:
./scripts/postgres.ps1 -PostgresBin 'C:\path\to\postgres\bin' -Action stop
```

The helper stores the cluster under `%LOCALAPPDATA%\FlakeGuard`, uses loopback port
54330, and creates application and isolated test databases. It requires the virtual
environment and installed dependencies. PostgreSQL binaries are not bundled.

Without `.env` or `DATABASE_URL`, the explicit convenience fallback is SQLite in
`.runtime/flakeguard.db`. PostgreSQL is the primary database and database-specific tests
run against it; SQLite is used for fast isolated tests and zero-service exploration.

## Running the checks

```bash
pytest
ruff check .
ruff format --check .
mypy src/flakeguard
alembic check
cd web && npm run typecheck && npm test && npm run build
```

PostgreSQL validation uses an isolated database whose name contains `test`:

```powershell
# Local helper initializes flakeguard_test using the same ignored local credentials.
python scripts/create_databases.py
python scripts/check_postgres.py
```

For an already configured test database, set `FLAKEGUARD_TEST_DATABASE_URL`, run
migrations against that database, then run pytest. Never point it at application data.

Live API and browser checks need running services and seeded demo data:

```powershell
$env:FLAKEGUARD_E2E='1'
pytest tests/e2e -q
python -m playwright install chromium
python scripts/browser_check.py
python scripts/ui_interactions.py
```

The browser check visits every page, runs axe-core, saves screenshots, uploads a report
through the UI and verifies API persistence, using a reserved `e2e/browser-validation`
repository. `ui_interactions.py` covers the skip link, keyboard navigation, filters, CSV
export, evidence deep links and the 390px layout. See [TEST_STRATEGY](TEST_STRATEGY.md)
for isolation, coverage scope and regression cases.
