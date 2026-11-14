"""Exercise all dashboard pages against the live API and save real UI screenshots."""

import json
import os
import re
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

from flakeguard.config import get_settings

settings = get_settings()
base = os.environ.get("FLAKEGUARD_DASHBOARD_URL", "http://127.0.0.1:8501")
directory = Path("docs/evidence/screenshots")
directory.mkdir(parents=True, exist_ok=True)
observations = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 1100}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(base)
    expect(page.get_by_role("heading", name="Your test suite, in focus.")).to_be_visible(
        timeout=60_000
    )
    sidebar = page.get_by_test_id("stSidebar")
    for title, filename in [
        ("Overview", "overview.png"),
        ("Flaky Tests", "flaky-tests.png"),
        ("Failure Analysis", "failure-analysis.png"),
        ("Test Details", "test-details.png"),
        ("CI Integration", "ci-integration.png"),
    ]:
        sidebar.get_by_text(title, exact=True).click()
        heading = "Your test suite, in focus." if title == "Overview" else title
        expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible(timeout=60_000)
        sentinels = {
            "Overview": "Recent test runs",
            "Flaky Tests": "Inspect scoring evidence",
            "Failure Analysis": "Failure pattern",
            "Test Details": "Execution diagnostics",
            "CI Integration": "Ingestion activity",
        }
        expect(page.get_by_text(sentinels[title], exact=True)).to_be_visible(timeout=60_000)
        expect(page.get_by_test_id("stApp")).to_have_attribute(
            "data-test-script-state", "notRunning", timeout=60_000
        )
        expect(page.get_by_test_id("stDataFrame").first).to_be_visible(timeout=60_000)
        expect(page.get_by_test_id("stException")).to_have_count(0)
        page.get_by_role("heading", name=heading, exact=True).click()
        page.screenshot(path=str(directory / filename), full_page=True)
        observations.append(
            {"page": title, "screenshot": filename, "rendered": True, "script_completed": True}
        )
    # Browser upload imports a real bundled report with explicit injected provenance.
    page.get_by_test_id("stFileUploader").locator("input[type=file]").set_input_files(
        "examples/reports/commerceguard-injected.json"
    )
    page.get_by_role("textbox", name="Repository", exact=True).fill("e2e/browser-validation")
    page.get_by_label("Unique run identifier", exact=True).fill("browser-upload-validation")
    page.get_by_label("Report provenance", exact=True).click()
    page.get_by_role("option", name="injected", exact=True).click()
    page.get_by_test_id("stForm").first.get_by_role(
        "button", name="Import report", exact=True
    ).click()
    expect(
        page.get_by_text(re.compile(r"Imported [01] executions; [01] duplicates\."))
    ).to_be_visible(timeout=60_000)
    # The API and database must observe the browser-submitted execution.
    response = httpx.get(
        settings.flakeguard_api_url + "/api/results",
        params={"repository": "e2e/browser-validation"},
        headers={"X-API-Key": settings.flakeguard_api_key.get_secret_value()},
    )
    response.raise_for_status()
    assert len(response.json()) == 1 and response.json()[0]["status"] == "failed"
    assert not errors, errors
    browser.close()
Path("docs/evidence/browser-check.json").write_text(
    json.dumps(
        {
            "pages": observations,
            "browser_upload_to_api_and_postgresql": True,
            "javascript_errors": errors,
        },
        indent=2,
    ),
    encoding="utf-8",
)
print("Five dashboard pages rendered; browser upload persisted through API; no JavaScript errors.")
