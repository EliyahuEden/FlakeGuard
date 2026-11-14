import io
import zipfile

import httpx
import pytest
from conftest import report
from sqlalchemy import func, select

from flakeguard.config import Settings
from flakeguard.github import GitHubClient, GitHubError, archive_reports, sync_repository
from flakeguard.ingestion import get_repository
from flakeguard.models import Execution, SyncState


def zip_content(name="results.json", content=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, report() if content is None else content)
    return buffer.getvalue()


@pytest.mark.parametrize(
    "status,expected", [(401, 401), (403, 403), (404, 404), (410, 410), (429, 429), (500, 502)]
)
def test_github_error_statuses(status, expected):
    transport = httpx.MockTransport(lambda _: httpx.Response(status))
    client = GitHubClient(Settings(), httpx.Client(transport=transport))
    with pytest.raises(GitHubError) as error:
        client.runs("a/b", 20)
    assert error.value.status == expected


def test_github_pagination():
    pages = []

    def handler(request):
        page = int(request.url.params["page"])
        pages.append(page)
        return httpx.Response(
            200, json={"artifacts": [{"id": i} for i in range(100 if page == 1 else 2)]}
        )

    client = GitHubClient(Settings(), httpx.Client(transport=httpx.MockTransport(handler)))
    assert len(client.artifacts("a/b", "1")) == 102
    assert pages == [1, 2]


def test_token_not_forwarded_to_storage():
    observed = []

    def handler(request):
        observed.append((request.url.host, request.headers.get("authorization")))
        if request.url.host == "api.github.com":
            return httpx.Response(
                302,
                headers={"location": "https://storage.blob.core.windows.net/report?sig=private"},
            )
        return httpx.Response(200, content=zip_content())

    client = GitHubClient(
        Settings(github_token="test-only-token"),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert client.download("a/b", 1)
    assert observed == [
        ("api.github.com", "Bearer test-only-token"),
        ("storage.blob.core.windows.net", None),
    ]


@pytest.mark.parametrize(
    "location",
    [
        "http://localhost/report",
        "https://evil.example/report",
        "https://api.github.com.evil.example/report",
        "https://user@x.blob.core.windows.net/report",
    ],
)
def test_untrusted_redirects_rejected(location):
    client = GitHubClient(
        Settings(),
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(302, headers={"location": location})
            )
        ),
    )
    with pytest.raises(GitHubError, match="Untrusted"):
        client.download("a/b", 1)


@pytest.mark.parametrize(
    "name", ["../escape.json", "/absolute.json", "C:\\escape.json", "x/../../escape.xml"]
)
def test_unsafe_archives(name):
    with pytest.raises(GitHubError, match="Unsafe"):
        archive_reports(zip_content(name), Settings())


def test_archive_limits_and_invalid_zip():
    with pytest.raises(GitHubError, match="member count"):
        archive_reports(zip_content(), Settings(max_archive_files=0))
    with pytest.raises(GitHubError, match="byte limit"):
        archive_reports(zip_content(), Settings(max_archive_bytes=10))
    with pytest.raises(GitHubError, match="readable ZIP"):
        archive_reports(b"not zip", Settings())


def mock_github(artifact, archive=None):
    def handler(request):
        path = request.url.path
        if path.endswith("/actions/runs"):
            return httpx.Response(
                200,
                json={
                    "workflow_runs": [
                        {
                            "id": 42,
                            "head_branch": "main",
                            "head_sha": "abc",
                            "run_attempt": 1,
                            "created_at": "2026-10-01T12:00:00Z",
                        }
                    ]
                },
            )
        if path.endswith("/artifacts"):
            return httpx.Response(200, json={"artifacts": [artifact] if artifact else []})
        if path.endswith("/zip"):
            return httpx.Response(200, content=archive or zip_content())
        raise AssertionError(path)

    return GitHubClient(Settings(), httpx.Client(transport=httpx.MockTransport(handler)))


def test_sync_import_and_skip_processed(session):
    repo = get_repository(session, "a/b")
    repo.github_enabled = True
    session.commit()
    github = mock_github({"id": 7, "name": "test-results", "expired": False})
    settings = Settings(github_repositories="a/b")
    first = sync_repository(session, settings, "a/b", client=github)
    assert first["runs"][0]["imported"] == 1
    assert (
        sync_repository(session, settings, "a/b", client=github)["runs"][0]["status"]
        == "already_processed"
    )
    assert session.scalar(select(func.count(Execution.id))) == 1


@pytest.mark.parametrize("artifact", [None, {"id": 7, "name": "report", "expired": True}])
def test_missing_expired_not_marked_processed(session, artifact):
    repo = get_repository(session, "a/b")
    repo.github_enabled = True
    session.commit()
    result = sync_repository(
        session, Settings(github_repositories="a/b"), "a/b", client=mock_github(artifact)
    )
    assert result["runs"][0]["status"] == "error"
    assert session.scalar(select(SyncState.status)) == "error"


def test_sync_transaction_rollback_on_malformed_second_report(session):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("good.json", report())
        archive.writestr("bad.xml", "<broken")
    repo = get_repository(session, "a/b")
    repo.github_enabled = True
    session.commit()
    result = sync_repository(
        session,
        Settings(github_repositories="a/b"),
        "a/b",
        client=mock_github({"id": 7, "name": "report"}, buffer.getvalue()),
    )
    assert result["runs"][0]["status"] == "error"
    assert session.scalar(select(func.count(Execution.id))) == 0


def test_sync_allowlist_and_timeout(session):
    with pytest.raises(GitHubError, match="allowlist"):
        sync_repository(session, Settings(), "a/b")

    def timeout(request):
        raise httpx.ReadTimeout("private request detail", request=request)

    client = GitHubClient(Settings(), httpx.Client(transport=httpx.MockTransport(timeout)))
    with pytest.raises(GitHubError, match="timed out"):
        client.runs("a/b", 10)
