import os

import httpx
import pytest

from flakeguard.config import get_settings

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.environ.get("FLAKEGUARD_E2E") != "1",
        reason="Set FLAKEGUARD_E2E=1 with live API and seeded demo",
    ),
]


def test_live_api_seeded_history():
    settings = get_settings()
    with httpx.Client(
        base_url=settings.flakeguard_api_url,
        headers={"X-API-Key": settings.flakeguard_api_key.get_secret_value()},
        timeout=60,
    ) as client:
        assert client.get("/health").json()["status"] == "ok"
        params = {"repository": "demo/commerce", "provenance": "synthetic"}
        metrics = client.get("/api/metrics", params=params)
        metrics.raise_for_status()
        assert metrics.json()["total_executions"] == 720
        assert metrics.json()["retry_recoveries"] == 36
        assert metrics.json()["pass_rate"] == 0.76
        reliability = client.get("/api/reliability", params=params).json()
        assert sum(row["classification"] == "suspected_flaky" for row in reliability) == 6
        run = client.get("/api/runs", params=params).json()[0]
        assert "quality gates" in client.get(f"/api/runs/{run['id']}/summary").text
