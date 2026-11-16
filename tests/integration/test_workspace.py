"""The bundled React workspace: bootstrap config, static serving and response hardening."""

import pytest
from fastapi.testclient import TestClient

from flakeguard import api
from flakeguard.config import get_settings
from flakeguard.db import get_session


def test_config_is_public_and_reports_mode(client, monkeypatch):
    assert client.get("/config").json() == {"read_only": False, "auth_required": False}
    monkeypatch.setenv("FLAKEGUARD_API_KEY", "test-only-secret")
    monkeypatch.setenv("FLAKEGUARD_READ_ONLY", "true")
    get_settings.cache_clear()
    # The bootstrap endpoint must answer before the user has supplied a key.
    assert client.get("/config").json() == {"read_only": True, "auth_required": True}
    assert "test-only-secret" not in client.get("/config").text


@pytest.fixture
def workspace(session, tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    monkeypatch.setattr(api, "WEB_DIR", tmp_path)
    app = api.create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as http:
        yield http


def test_workspace_is_served_with_strict_security_headers(workspace):
    page = workspace.get("/")
    assert page.status_code == 200 and 'id="root"' in page.text
    assert "script-src 'self'" in page.headers["content-security-policy"]
    assert page.headers["x-content-type-options"] == "nosniff"
    assert page.headers["referrer-policy"] == "no-referrer"


def test_api_routes_take_precedence_over_the_static_mount(workspace):
    assert workspace.get("/health").json() == {"status": "ok"}
    assert workspace.get("/api/options").status_code == 200
    assert workspace.get("/missing-asset.js").status_code == 404


def test_api_explorer_keeps_its_own_csp(workspace):
    docs = workspace.get("/docs")
    assert docs.status_code == 200
    assert "content-security-policy" not in docs.headers
