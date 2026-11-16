# Publication and hosting

## GitHub repositories

- FlakeGuard: [EliyahuEden/FlakeGuard](https://github.com/EliyahuEden/FlakeGuard), public portfolio repository.
- CommerceGuard: [EliyahuEden/CommerceGuard](https://github.com/EliyahuEden/CommerceGuard), already public with hosted CI and downloadable diagnostic artifacts.

Publishing source code and running GitHub Actions do not deploy an application server. Neither project is presented as a live public application until a hosting provider returns a verified application URL.

## Recommendation

**FlakeGuard is worth deploying as a read-only portfolio demo.** A recruiter can explore real analysis output, filters, explanations, histories, and failure diagnostics without running local infrastructure. The full writable platform remains independently usable locally through Docker Compose or native Python/PostgreSQL.

**CommerceGuard does not require a public merchant deployment to demonstrate SDET work.** Its primary product is the QA framework: API/UI/SQL checks, defect-injection evidence, reproducible setup, and hosted quality gates. The FORME storefront can be hosted as an optional separate demonstration, but it needs its own Next.js/Medusa/PostgreSQL services and should use disposable demo accounts and manual payments. Do not describe the test framework itself as a deployed store. Its existing README and hosted regression evidence already provide a useful portfolio entry.

## FlakeGuard deployment shape

```mermaid
flowchart LR
    Visitor[Portfolio visitor] --> TLS[HTTPS / hosting provider]
    TLS --> API[FastAPI + bundled React workspace]
    API --> DB[(Dedicated demo PostgreSQL)]
```

Use a dedicated demo database. Initialize it through the real CLI ingestion pipeline, then make the HTTP-facing service read-only (`FLAKEGUARD_READ_ONLY=true`; the workspace then labels itself a read-only demonstration):

```bash
flakeguard migrate
flakeguard demo
python scripts/import_examples.py
```

Required API environment:

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/DATABASE?sslmode=require
FLAKEGUARD_API_KEY=GENERATE_A_LONG_RANDOM_SECRET_IN_THE_HOSTING_PROVIDER
FLAKEGUARD_READ_ONLY=true
GITHUB_TOKEN=
GITHUB_REPOSITORIES=
```

Required dashboard environment:

```dotenv
FLAKEGUARD_API_URL=https://YOUR_API_HOST
FLAKEGUARD_API_KEY=THE_SAME_PROVIDER_MANAGED_SECRET
FLAKEGUARD_READ_ONLY=true
```

Never commit actual values. The dashboard sends the API key from its server process. The API rejects POST/PUT/PATCH/DELETE requests under `/api/` when read-only mode is enabled, even if the caller has the API key. The dashboard disables report-upload and synchronization controls and labels the instance as a read-only demo. CLI administration remains possible for the owner. Read-only mode does not anonymize data: import only deliberately public demonstration reports, not private repository diagnostics.

Build either service from this repository:

```bash
pip install -r requirements.lock
pip install --no-deps .
```

Start command (after migration/seed setup and `npm run build` in `web/`, or use the Docker image, which builds the workspace in its own stage):

```bash
uvicorn flakeguard.api:app --host 0.0.0.0 --port "$PORT"
```

Health path: `/health`. One process serves the API and the static workspace, so no WebSocket support or second service is needed. If `FLAKEGUARD_API_KEY` is set the workspace asks visitors for it, so leave it unset for a public read-only demo and rely on `FLAKEGUARD_READ_ONLY`. PostgreSQL is not exposed publicly by the local Compose configuration.

## Hosting options and actual tradeoffs

| Option | Suitable use | Limit or requirement |
|---|---|---|
| Render Python services + a separate managed PostgreSQL provider such as Neon | Single web service (the Docker image) with a dedicated demo DB | Requires connected hosting/database accounts; verify the selected plans, quotas, and spend controls before creating resources |
| Docker Compose on a VM | Straightforward full platform using the existing deployment shape | VM hosting may have ongoing cost; add TLS and authentication before writable/shared use |
| Sites / static hosting | Documentation or a separately labeled static showcase | Hosts only a pre-built static copy of the React bundle; it cannot run the Python API or PostgreSQL |

Current official provider documentation was checked on 14 November 2026. [Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud) offers free app hosting. [Render free services](https://render.com/docs/free) sleep after 15 minutes of inactivity, lose local filesystem changes on restart, and share a monthly free-hour allowance. **Render's free PostgreSQL database expires after 30 days**, so it is a temporary demonstration option rather than a durable portfolio database. A sleeping API can delay the first dashboard request. Do not silently upgrade plans or assume a free tier is a production availability guarantee.

The Render and Neon integrations were discovered and suggested because neither was connected during preparation. No hosting resource, paid plan, database account, or external deployment was created. Connect the chosen provider and review the concrete resource plans before launch; GitHub publication is independent of this step.
