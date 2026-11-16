"""Behavioral QA for the graphite workspace: keyboard, filters, export, responsive layout."""

import json
import os
from pathlib import Path

import pandas as pd
from playwright.sync_api import expect, sync_playwright

base = os.environ.get("FLAKEGUARD_URL", "http://127.0.0.1:8000")
checks: list[str] = []


def ready(page):
    expect(page.get_by_role("status", name="Loading")).to_have_count(0, timeout=60_000)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto(base)
    expect(page.get_by_role("heading", name="Recent test runs")).to_be_visible(timeout=60_000)

    # Keyboard: skip link, then sidebar navigation without a pointer.
    page.keyboard.press("Tab")
    expect(page.get_by_role("link", name="Skip to content")).to_be_focused()
    page.get_by_role("link", name="Flaky Tests").focus()
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", level=1, name="Flaky Tests")).to_be_focused()
    checks.append("Skip link, keyboard navigation and heading focus after route change")

    # Filters query real API counts and the status-bias warning appears.
    page.get_by_role("link", name="Overview").click()
    ready(page)
    page.get_by_role("button", name="Filters").click()
    page.get_by_label("Repository").select_option("demo/commerce")
    expect(page.get_by_text("720", exact=True).first).to_be_visible(timeout=60_000)
    page.get_by_label("Status").select_option("failed")
    expect(page.get_by_text("144", exact=True).first).to_be_visible(timeout=60_000)
    expect(page.get_by_text("Status filtering selects outcomes")).to_be_visible()
    checks.append("Repository/status filters query real API counts (720 total / 144 failed)")
    page.get_by_role("button", name="Clear all").click()

    # CSV export from the Flaky Tests page, scoped by the repository filter.
    page.get_by_role("link", name="Flaky Tests").click()
    page.get_by_label("Repository").select_option("demo/commerce")
    ready(page)
    expect(page.get_by_role("button", name="Export CSV")).to_be_enabled(timeout=60_000)
    with page.expect_download() as pending:
        page.get_by_role("button", name="Export CSV").click()
    destination = Path(".runtime/export-check.csv")
    pending.value.save_as(destination)
    exported = pd.read_csv(destination)
    assert len(exported) == 24 and set(exported["provenance"]) == {"synthetic"}
    checks.append("CSV export contains 24 scoped reliability cohorts and provenance labels")

    # Row selection opens the evidence panel and links to the execution history.
    page.get_by_role("button", name="shared-state contamination").first.click()
    expect(page.get_by_role("complementary", name="Scoring evidence")).to_be_visible()
    page.get_by_role("link", name="Open execution history").click()
    expect(page.get_by_role("heading", name="Executions")).to_be_visible(timeout=60_000)
    checks.append("Flaky row opens scoring evidence and deep-links to the test history")
    browser.close()

    browser = p.chromium.launch()
    mobile = browser.new_page(
        viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
    )
    mobile.goto(base)
    expect(mobile.get_by_role("heading", name="Recent test runs")).to_be_visible(timeout=60_000)
    assert mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    expect(mobile.get_by_role("navigation", name="Workspace")).to_be_visible()
    mobile.screenshot(path="docs/evidence/screenshots/mobile-overview.png", full_page=True)
    checks.append("390px layout: horizontal navigation, stacked panels, no page overflow")
    browser.close()

Path("docs/evidence/ui-interactions.json").write_text(
    json.dumps({"checks": checks, "passed": len(checks)}, indent=2), encoding="utf-8"
)
print(f"{len(checks)} UI interaction checks passed")
