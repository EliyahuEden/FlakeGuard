"""Exercise every workspace page against the live API: render, axe, screenshots, upload."""

import json
import os
import re
from pathlib import Path

import httpx
from playwright.sync_api import Page, expect, sync_playwright

from flakeguard.config import get_settings

settings = get_settings()
base = os.environ.get("FLAKEGUARD_URL", "http://127.0.0.1:8000")
headers = {"X-API-Key": settings.flakeguard_api_key.get_secret_value()}
directory = Path("docs/evidence/screenshots")
directory.mkdir(parents=True, exist_ok=True)
AXE = Path("web/node_modules/axe-core/axe.min.js")

PAGES = [
    ("Overview", "#/", "Recent test runs", "overview.png"),
    ("Flaky Tests", "#/flaky", "Test reliability evidence", "flaky-tests.png"),
    ("Failure Analysis", "#/failures", "Normalized diagnostic", "failure-analysis.png"),
    ("Test Details", "#/tests", "Choose a test", "test-details.png"),
    ("CI Integration", "#/integration", "Ingestion activity", "ci-integration.png"),
]


def axe_violations(page: Page) -> list[dict]:
    # Evaluated through the DevTools protocol so the app's strict CSP stays enforced.
    page.evaluate(AXE.read_text(encoding="utf-8"))
    result = page.evaluate(
        "axe.run(document, {runOnly: ['wcag2a','wcag2aa','wcag21aa','wcag22aa']})"
        ".then(r => r.violations.map(v => ({id: v.id, impact: v.impact, nodes: v.nodes.length})))"
    )
    return result


def open_page(page: Page, route: str, sentinel: str) -> None:
    page.goto(f"{base}/{route}")
    expect(page.get_by_text(sentinel, exact=True).first).to_be_visible(timeout=60_000)
    expect(page.get_by_role("status", name="Loading")).to_have_count(0, timeout=60_000)


observations = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console",
        lambda m: errors.append(m.text) if m.type == "error" else None,
    )
    if settings.flakeguard_api_key.get_secret_value():
        page.goto(base)
        page.get_by_label("API key").fill(settings.flakeguard_api_key.get_secret_value())
        page.get_by_role("button", name="Open workspace").click()
    for title, route, sentinel, filename in PAGES:
        open_page(page, route, sentinel)
        expect(page.get_by_role("heading", level=1, name=title, exact=True)).to_be_visible()
        violations = axe_violations(page)
        assert not violations, f"{title}: {violations}"
        page.screenshot(path=str(directory / filename), full_page=True)
        observations.append(
            {"page": title, "screenshot": filename, "rendered": True, "axe_violations": 0}
        )

    # Browser upload imports a real bundled report with explicit injected provenance.
    open_page(page, "#/integration", "Ingestion activity")
    page.locator("input[type=file]").set_input_files("examples/reports/commerceguard-injected.json")
    page.get_by_label("Repository", exact=True).fill("e2e/browser-validation")
    page.get_by_label("Unique run identifier").fill("browser-upload-validation")
    page.get_by_label("Report provenance").select_option("injected")
    page.get_by_role("button", name="Import report", exact=True).click()
    expect(
        page.get_by_text(re.compile(r"Imported [01] executions; [01] duplicates"))
    ).to_be_visible(timeout=60_000)
    response = httpx.get(
        base + "/api/results",
        params={"repository": "e2e/browser-validation"},
        headers=headers,
    )
    response.raise_for_status()
    assert len(response.json()) == 1 and response.json()[0]["status"] == "failed"
    assert not errors, errors
    browser.close()

Path("docs/evidence/browser-check.json").write_text(
    json.dumps(
        {
            "pages": observations,
            "axe_ruleset": "wcag2a, wcag2aa, wcag21aa, wcag22aa (automated; not a certification)",
            "browser_upload_to_api_and_database": True,
            "javascript_errors": errors,
        },
        indent=2,
    ),
    encoding="utf-8",
)
print("Five workspace pages rendered with zero axe violations; upload persisted; no JS errors.")
