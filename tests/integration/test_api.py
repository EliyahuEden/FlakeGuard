import json

import pytest
from conftest import report

from flakeguard.config import get_settings


def upload(client, content=None, context=None, filename="a.json"):
    return client.post(
        "/api/imports",
        files={"file": (filename, report() if content is None else content)},
        data={"context": json.dumps(context or {"repository": "a/b", "run_id": "1"})},
    )


def test_end_to_end_api(client):
    imported = upload(client, report(["failed", "passed"]))
    assert imported.status_code == 201, imported.text
    run_id = imported.json()["run_id"]
    results = client.get("/api/results").json()
    test_id = results[0]["test_id"]
    assert client.get("/api/metrics").json()["retry_recoveries"] == 1
    assert client.get(f"/api/tests/{test_id}/history").json()["total"] == 1
    assert len(client.get("/api/failures").json()["clusters"]) == 1
    assert client.get("/api/classifications").json()[0]["category"] == "suspected_automation"
    assert client.get("/api/dashboard").json()["metrics"]["passed"] == 1
    assert client.get("/api/runs").json()[0]["id"] == run_id
    assert "quality gates" in client.get(f"/api/runs/{run_id}/summary").text
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/openapi.json").status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/api/metrics",
        "/api/reliability",
        "/api/failures",
        "/api/dashboard",
        "/api/runs",
        "/api/results",
        "/api/options",
        "/api/imports",
        "/api/repositories",
    ],
)
def test_empty_api(client, path):
    assert client.get(path).status_code == 200


def test_validation_and_errors_recorded(client):
    assert upload(client, b"{").status_code == 422
    assert client.get("/api/imports").json()["errors"]
    assert upload(client, context={"repository": "a/b"}).status_code == 422
    assert (
        upload(
            client, context={"repository": "a/b", "run_id": "1", "executed_at": "2026-10-01"}
        ).status_code
        == 422
    )
    assert client.get("/api/results?limit=0").status_code == 422
    assert client.get("/api/results?status=invalid").status_code == 422
    assert client.get("/api/metrics?start=2026-10-01T00:00:00").status_code == 422
    assert (
        client.get("/api/metrics?start=2026-10-02T00:00:00Z&end=2026-10-01T00:00:00Z").status_code
        == 422
    )
    assert client.get("/api/tests/missing/history").status_code == 404


def test_body_and_report_limits(client, monkeypatch):
    monkeypatch.setenv("MAX_REPORT_BYTES", "64")
    get_settings.cache_clear()
    assert upload(client).status_code == 413
    assert client.post("/api/imports", content=b"x" * 70_000).status_code == 413


def test_api_key_protects_read_and_write(client, monkeypatch):
    monkeypatch.setenv("FLAKEGUARD_API_KEY", "test-only-secret")
    get_settings.cache_clear()
    assert client.get("/api/results").status_code == 401
    assert upload(client).status_code == 401
    assert client.get("/api/results", headers={"X-API-Key": "test-only-secret"}).status_code == 200


def test_configure_requires_server_allowlist(client, monkeypatch):
    assert client.post("/api/repositories", json={"name": "owner/project"}).status_code == 403
    monkeypatch.setenv("GITHUB_REPOSITORIES", "owner/project")
    get_settings.cache_clear()
    assert client.post("/api/repositories", json={"name": "owner/project"}).status_code == 201
    assert client.get("/api/repositories").json()[0]["github_enabled"] is True


def test_duplicate_api(client):
    assert upload(client).json()["imported"] == 1
    assert upload(client).json()["duplicates"] == 1
    assert len(client.get("/api/results").json()) == 1
    assert upload(client, report(["failed"])).status_code == 409


def test_read_only_demo_blocks_writes_before_ingestion(client, monkeypatch):
    monkeypatch.setenv("FLAKEGUARD_READ_ONLY", "true")
    get_settings.cache_clear()
    assert upload(client).status_code == 403
    assert client.post("/api/github/sync", json={"repository": "a/b"}).status_code == 403
    assert client.post("/api/repositories", json={"name": "a/b"}).status_code == 403
    assert client.get("/api/results").json() == []
    assert client.get("/api/metrics").status_code == 200
