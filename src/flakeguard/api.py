import hmac
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from flakeguard.analytics import (
    Filters,
    breakdown,
    execution_query,
    execution_view,
    failure_clusters,
    load_executions,
    metrics,
    newly_failing,
    reliability,
    trends,
)
from flakeguard.config import get_settings
from flakeguard.db import get_session
from flakeguard.github import GitHubError, sync_repository
from flakeguard.ingestion import IngestionConflict, atomic_ingest, get_repository
from flakeguard.models import Execution, IngestionError, ReportImport, Repository, Run, SyncState
from flakeguard.parsers import ReportError
from flakeguard.schemas import (
    ImportContext,
    ImportResult,
    Metrics,
    RepositoryConfig,
    RunView,
    SyncRequest,
)
from flakeguard.summary import quality_summary


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["path"].startswith("/api/")
            and scope["method"] in {"POST", "PUT", "PATCH", "DELETE"}
            and get_settings().flakeguard_read_only
        ):
            await JSONResponse(
                {
                    "detail": "This demonstration is read-only. Run the full platform locally to import or synchronize reports."
                },
                403,
            )(scope, receive, send)
            return
        if scope["type"] != "http" or scope["method"] not in {"POST", "PUT", "PATCH"}:
            await self.app(scope, receive, send)
            return
        maximum = get_settings().max_report_bytes + 64 * 1024
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > maximum:
                await JSONResponse({"detail": "Request exceeds configured byte limit"}, 413)(
                    scope, receive, send
                )
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


def authorize(x_api_key: Annotated[str | None, Header()] = None) -> None:
    expected = get_settings().flakeguard_api_key.get_secret_value()
    if expected and (x_api_key is None or not hmac.compare_digest(expected, x_api_key)):
        raise HTTPException(401, "A valid X-API-Key is required")


def filters(
    repository: str | None = None,
    branch: str | None = None,
    suite: str | None = None,
    status: str | None = Query(
        None, pattern="^(passed|failed|timedOut|skipped|interrupted|unknown)$"
    ),
    browser: str | None = None,
    environment: str | None = None,
    provenance: str | None = Query(None, pattern="^(real|injected|synthetic)$"),
    start: datetime | None = None,
    end: datetime | None = None,
    run_id: int | None = None,
) -> Filters:
    if any(d is not None and d.tzinfo is None for d in (start, end)):
        raise HTTPException(422, "Date filters require timezone offsets")
    if start and end and start > end:
        raise HTTPException(422, "start must not be after end")
    return Filters(
        repository, branch, suite, status, browser, environment, provenance, start, end, run_id
    )


DB = Annotated[Session, Depends(get_session)]
Filter = Annotated[Filters, Depends(filters)]
router = APIRouter(prefix="/api", dependencies=[Depends(authorize)])


@router.post("/imports", response_model=ImportResult, status_code=201, tags=["ingestion"])
async def import_report(
    file: UploadFile, context: Annotated[str, Form()], session: DB
) -> ImportResult:
    # A multipart JSON context avoids ambiguous timestamp/metadata inference.
    try:
        import_context = ImportContext.model_validate_json(context)
    except ValidationError as exc:
        raise HTTPException(
            422,
            "Invalid context: repository and run_id are required; timestamps need timezone offsets",
        ) from exc
    content = await file.read(get_settings().max_report_bytes + 1)
    if len(content) > get_settings().max_report_bytes:
        raise HTTPException(413, "Report exceeds configured byte limit")
    try:
        return atomic_ingest(
            session, content, file.filename or "report.json", import_context, get_settings()
        )
    except ReportError as exc:
        session.add(IngestionError(filename="uploaded-report", detail=str(exc)))
        session.commit()
        raise HTTPException(409 if isinstance(exc, IngestionConflict) else 422, str(exc)) from exc


@router.get("/runs", response_model=list[RunView], tags=["history"])
def runs(
    session: DB,
    selection: Filter,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[Run]:
    ids = execution_query(selection).with_only_columns(Execution.run_id).order_by(None).distinct()
    return list(
        session.scalars(
            select(Run)
            .where(Run.id.in_(ids))
            .order_by(Run.executed_at.desc(), Run.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )


@router.get("/results", tags=["history"])
def results(
    session: DB,
    selection: Filter,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    rows = session.scalars(execution_query(selection).limit(limit).offset(offset)).unique()
    return [execution_view(row) for row in rows]


@router.get("/tests/{test_id}/history", tags=["history"])
def history(
    test_id: str,
    session: DB,
    selection: Filter,
    limit: int = Query(200, ge=1, le=2000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    rows = list(
        session.scalars(execution_query(selection).where(Execution.test_id == test_id)).unique()
    )
    if not rows:
        raise HTTPException(404, "No test history matches the filters")
    return {
        "test_id": test_id,
        "total": len(rows),
        "reliability": reliability(rows),
        "history": [execution_view(e) for e in rows[offset : offset + limit]],
    }


@router.get("/metrics", response_model=Metrics, tags=["analysis"])
def metric_view(session: DB, selection: Filter) -> Metrics:
    return metrics(load_executions(session, selection))


@router.get("/reliability", tags=["analysis"])
def reliability_view(session: DB, selection: Filter) -> list[dict[str, Any]]:
    return reliability(load_executions(session, selection))


@router.get("/failures", tags=["analysis"])
def failures(session: DB, selection: Filter) -> dict[str, Any]:
    return failure_clusters(session, load_executions(session, selection))


@router.get("/classifications", tags=["analysis"])
def classifications(session: DB, selection: Filter) -> list[dict[str, Any]]:
    return [
        {"fingerprint": c["fingerprint"], **c["classification"]}
        for c in failure_clusters(session, load_executions(session, selection))["clusters"]
    ]


@router.get("/dashboard", tags=["analysis"])
def dashboard(session: DB, selection: Filter) -> dict[str, Any]:
    rows = load_executions(session, selection)
    return {
        "metrics": metrics(rows).model_dump(),
        "trends": trends(rows),
        "suites": breakdown(rows, "suite"),
        "branches": breakdown(rows, "branch"),
        "browsers": breakdown(rows, "browser"),
        "newly_failing": newly_failing(session, rows)[-100:],
        "note": "Metrics apply to the selected executions. Reliability history is partitioned by branch, environment, and provenance; status filtering can bias history.",
    }


@router.get("/options", tags=["configuration"])
def options(session: DB) -> dict[str, Any]:
    rows = load_executions(session, Filters())
    return {
        "repositories": sorted({e.run.repository.name for e in rows}),
        "branches": sorted({e.run.branch for e in rows}),
        "suites": sorted({e.test.suite for e in rows}),
        "browsers": sorted({e.browser for e in rows if e.browser}),
        "environments": sorted({e.environment for e in rows if e.environment}),
        "provenances": sorted({e.run.provenance for e in rows}),
    }


@router.get("/repositories", tags=["configuration"])
def repositories(session: DB) -> list[dict[str, Any]]:
    return [
        {"id": r.id, "name": r.name, "github_enabled": r.github_enabled}
        for r in session.scalars(select(Repository).order_by(Repository.name))
    ]


@router.post("/repositories", status_code=201, tags=["configuration"])
def configure_repository(config: RepositoryConfig, session: DB) -> dict[str, Any]:
    if config.github_enabled and config.name.lower() not in get_settings().allowed_repositories:
        raise HTTPException(403, "Add repository to server GITHUB_REPOSITORIES allowlist first")
    repo = get_repository(session, config.name)
    repo.github_enabled = config.github_enabled
    session.commit()
    return {"name": repo.name, "github_enabled": repo.github_enabled}


@router.post("/github/sync", tags=["integration"])
def sync(request: SyncRequest, session: DB) -> dict[str, Any]:
    return sync_repository(
        session, get_settings(), request.repository, request.max_runs, request.artifact_pattern
    )


@router.get("/imports", tags=["ingestion"])
def import_status(session: DB, limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    return {
        "imports": [
            {
                "id": i.id,
                "run_id": i.run_id,
                "filename": i.filename,
                "format": i.format,
                "warnings": i.warnings,
                "imported_at": i.imported_at,
            }
            for i in session.scalars(
                select(ReportImport).order_by(ReportImport.id.desc()).limit(limit)
            )
        ],
        "errors": [
            {"id": e.id, "detail": e.detail, "created_at": e.created_at}
            for e in session.scalars(
                select(IngestionError).order_by(IngestionError.id.desc()).limit(limit)
            )
        ],
        "syncs": [
            {
                "run_id": s.external_id,
                "run_attempt": s.run_attempt,
                "status": s.status,
                "detail": s.detail,
                "updated_at": s.updated_at,
            }
            for s in session.scalars(select(SyncState).order_by(SyncState.id.desc()).limit(limit))
        ],
    }


@router.get("/runs/{run_id}/summary", response_class=PlainTextResponse, tags=["integration"])
def summary(run_id: int, session: DB) -> str:
    if session.get(Run, run_id) is None:
        raise HTTPException(404, "Run not found")
    return quality_summary(session, run_id)


WEB_DIR = Path(__file__).parent / "web"
CSP = (
    "default-src 'self'; img-src 'self' data:; font-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"
)
SWAGGER_PATHS = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware:
    """Hardens the bundled workspace; the generated API explorer loads its own CDN assets."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        swagger = scope["path"].startswith(SWAGGER_PATHS)

        async def hardened(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-content-type-options", b"nosniff"))
                headers.append((b"referrer-policy", b"no-referrer"))
                if not swagger:
                    headers.append((b"content-security-policy", CSP.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, hardened)


def create_app() -> FastAPI:
    app = FastAPI(
        title="FlakeGuard",
        version="1.0.0",
        description="Explainable test reliability. Classifications are investigation suggestions, not root-cause claims.",
    )
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.include_router(router)

    @app.get("/config", tags=["health"])
    def config() -> dict[str, bool]:
        """Public bootstrap data so the workspace knows whether to ask for an API key."""
        settings = get_settings()
        return {
            "read_only": settings.flakeguard_read_only,
            "auth_required": bool(settings.flakeguard_api_key.get_secret_value()),
        }

    @app.get("/health", tags=["health"])
    def health(session: DB) -> dict[str, str]:
        session.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.exception_handler(GitHubError)
    async def github_error(_: Request, exc: GitHubError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse({"detail": errors}, status_code=422)

    if (WEB_DIR / "index.html").is_file():
        # Mounted last so every API route above takes precedence.
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="workspace")
    return app


app = create_app()
