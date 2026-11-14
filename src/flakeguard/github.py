"""Read-only GitHub Actions sync with bounded downloads and atomic run ingestion."""

import fnmatch
import io
import re
import stat
import zipfile
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from flakeguard.config import Settings
from flakeguard.ingestion import ingest
from flakeguard.models import Repository, SyncState
from flakeguard.parsers import ReportError, timestamp
from flakeguard.schemas import ImportContext


class GitHubError(RuntimeError):
    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


def archive_reports(content: bytes, settings: Settings) -> list[tuple[str, bytes]]:
    if len(content) > settings.max_archive_bytes:
        raise GitHubError("Artifact archive exceeds byte limit")
    reports = []
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = archive.infolist()
            if len(members) > settings.max_archive_files:
                raise GitHubError("Artifact archive exceeds member count limit")
            total = 0
            for member in members:
                path = PurePosixPath(member.filename.replace("\\", "/"))
                mode = member.external_attr >> 16
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or ":" in str(path)
                    or stat.S_ISLNK(mode)
                    or member.flag_bits & 1
                ):
                    raise GitHubError("Unsafe artifact archive member")
                total += member.file_size
                if (
                    total > settings.max_archive_bytes
                    or member.file_size > settings.max_report_bytes
                    or member.file_size / max(1, member.compress_size) > 200
                ):
                    raise GitHubError("Artifact archive exceeds decompression limits")
                if not member.is_dir() and path.suffix.lower() in {".json", ".xml"}:
                    # No extraction to disk, no attachment execution, no nested archives.
                    with archive.open(member) as stream:
                        data = stream.read(settings.max_report_bytes + 1)
                    if len(data) > settings.max_report_bytes:
                        raise GitHubError("Artifact report exceeds byte limit")
                    reports.append((str(path), data))
    except GitHubError:
        raise
    except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError) as exc:
        raise GitHubError("Artifact is not a readable ZIP archive") from exc
    return reports


class GitHubClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.Client(
            timeout=settings.http_timeout_seconds, follow_redirects=False
        )
        self.owns_client = client is None

    def close(self) -> None:
        if self.owns_client:
            self.client.close()

    def headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        token = self.settings.github_token.get_secret_value()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    @staticmethod
    def check(response: httpx.Response) -> None:
        if response.status_code == 401:
            raise GitHubError("GitHub authentication failed; check the configured token", 401)
        if response.status_code in {403, 429}:
            retry = response.headers.get("Retry-After")
            reset = response.headers.get("X-RateLimit-Reset")
            detail = "GitHub permission or rate limit rejection"
            if retry and retry.isdigit():
                detail += f"; retry after {retry} seconds"
            if reset and reset.isdigit():
                detail += f"; reset epoch {reset}"
            raise GitHubError(
                detail,
                429
                if response.status_code == 429
                or retry
                or response.headers.get("X-RateLimit-Remaining") == "0"
                else 403,
            )
        if response.status_code == 404:
            raise GitHubError(
                "GitHub repository or artifact unavailable (missing or unauthorized)", 404
            )
        if response.status_code == 410:
            raise GitHubError("GitHub artifact expired", 410)
        if response.status_code >= 400:
            raise GitHubError(f"GitHub request failed with HTTP {response.status_code}")

    def get_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.client.get(
                "https://api.github.com" + path, params=params, headers=self.headers()
            )
            self.check(response)
            if response.is_redirect:
                raise GitHubError("Unexpected redirect from GitHub metadata endpoint")
            data = response.json()
            if not isinstance(data, dict):
                raise GitHubError("Unexpected GitHub response structure")
            return data
        except (httpx.HTTPError, ValueError) as exc:
            raise GitHubError("GitHub metadata request failed or timed out") from exc

    def pages(
        self, path: str, key: str, max_items: int = 1000, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        while len(items) < max_items:
            data = self.get_json(path, {**(params or {}), "per_page": 100, "page": page})
            batch = data.get(key, [])
            if not isinstance(batch, list):
                raise GitHubError("Unexpected GitHub pagination structure")
            items.extend(batch[: max_items - len(items)])
            if len(batch) < 100:
                break
            page += 1
        return items

    def runs(self, repository: str, limit: int) -> list[dict[str, Any]]:
        return self.pages(
            f"/repos/{repository}/actions/runs", "workflow_runs", limit, {"status": "completed"}
        )

    def artifacts(self, repository: str, run_id: str) -> list[dict[str, Any]]:
        return self.pages(f"/repos/{repository}/actions/runs/{run_id}/artifacts", "artifacts")

    def download(self, repository: str, artifact_id: int) -> bytes:
        url = f"https://api.github.com/repos/{repository}/actions/artifacts/{artifact_id}/zip"
        headers = self.headers()
        try:
            for _ in range(4):
                with self.client.stream(
                    "GET", url, headers=headers, follow_redirects=False
                ) as response:
                    self.check(response)
                    if response.is_redirect:
                        target = response.headers.get("location", "")
                        parsed = urlparse(target)
                        hostname = parsed.hostname or ""
                        # GitHub signed artifact storage only; never forward the token.
                        allowed = hostname.endswith(
                            (
                                ".blob.core.windows.net",
                                ".actions.githubusercontent.com",
                                ".githubusercontent.com",
                            )
                        )
                        if (
                            parsed.scheme != "https"
                            or not allowed
                            or parsed.username
                            or parsed.port not in {None, 443}
                        ):
                            raise GitHubError("Untrusted artifact redirect rejected")
                        url, headers = target, {}
                        continue
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > self.settings.max_archive_bytes:
                            raise GitHubError("Artifact download exceeds byte limit")
                        chunks.append(chunk)
                    return b"".join(chunks)
            raise GitHubError("Too many artifact redirects")
        except httpx.HTTPError as exc:
            raise GitHubError("GitHub artifact download failed or timed out") from exc


def sync_repository(
    session: Session,
    settings: Settings,
    repository: str,
    max_runs: int = 20,
    artifact_pattern: str = "*",
    client: GitHubClient | None = None,
) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise GitHubError("Repository must be owner/name", 422)
    repository = repository.lower()
    if repository not in settings.allowed_repositories:
        raise GitHubError("Repository is not in the server GITHUB_REPOSITORIES allowlist", 403)
    repo = session.scalar(select(Repository).where(Repository.name == repository))
    if repo is None or not repo.github_enabled:
        raise GitHubError("Configure and enable this repository before synchronization", 409)
    repo_id = repo.id
    github = client or GitHubClient(settings)
    output: list[dict[str, Any]] = []
    try:
        runs = github.runs(repository, max_runs)
        for run in runs:
            run_id, attempt = str(run["id"]), int(run.get("run_attempt", 1))
            state = session.scalar(
                select(SyncState).where(
                    SyncState.repository_id == repo_id,
                    SyncState.external_id == run_id,
                    SyncState.run_attempt == attempt,
                )
            )
            if state and state.status == "processed":
                output.append({"run_id": run_id, "status": "already_processed"})
                continue
            imported = 0
            try:
                artifacts = [
                    a
                    for a in github.artifacts(repository, run_id)
                    if fnmatch.fnmatchcase(a["name"], artifact_pattern)
                ]
                active = [a for a in artifacts if not a.get("expired")]
                if not active:
                    raise GitHubError(
                        "No matching available artifacts; absent or expired",
                        410 if artifacts else 404,
                    )
                report_count = 0
                for artifact in active:
                    for filename, content in archive_reports(
                        github.download(repository, artifact["id"]), settings
                    ):
                        result = ingest(
                            session,
                            content,
                            filename,
                            ImportContext(
                                repository=repository,
                                run_id=run_id,
                                run_attempt=attempt,
                                branch=run.get("head_branch") or "unknown",
                                commit_sha=run.get("head_sha"),
                                executed_at=timestamp(
                                    run.get("run_started_at") or run.get("created_at")
                                ),
                                source="github",
                                provenance="real",
                                ci_url=f"https://github.com/{repository}/actions/runs/{run_id}",
                            ),
                            settings,
                        )
                        imported += result.imported
                        report_count += 1
                if not report_count:
                    raise GitHubError("No supported reports found in matching artifacts", 422)
                status, detail = (
                    "processed",
                    f"Imported {imported} executions from {report_count} reports",
                )
                if len(active) != len(artifacts):
                    # Do not mark partially available runs fully processed.
                    status, detail = "partial", detail + "; some matching artifacts expired"
            except (GitHubError, ReportError) as exc:
                session.rollback()
                imported = 0
                status, detail = "error", str(exc)
                state = session.scalar(
                    select(SyncState).where(
                        SyncState.repository_id == repo_id,
                        SyncState.external_id == run_id,
                        SyncState.run_attempt == attempt,
                    )
                )
            if state is None:
                state = SyncState(
                    repository_id=repo_id,
                    external_id=run_id,
                    run_attempt=attempt,
                    status=status,
                    detail=detail,
                )
                session.add(state)
            else:
                state.status, state.detail = status, detail
            session.commit()
            output.append(
                {
                    "run_id": run_id,
                    "run_attempt": attempt,
                    "status": status,
                    "detail": detail,
                    "imported": imported,
                }
            )
    finally:
        if client is None:
            github.close()
    return {"repository": repository, "runs": output}
