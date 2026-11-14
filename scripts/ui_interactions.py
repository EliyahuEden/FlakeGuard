"""Behavioral QA for the graphite workspace, including responsive and keyboard flows."""

import json
from pathlib import Path

import pandas as pd
from playwright.sync_api import expect, sync_playwright

checks = []


def idle(page):
    expect(page.get_by_test_id("stApp")).to_have_attribute(
        "data-test-script-state", "notRunning", timeout=60_000
    )
    expect(page.get_by_test_id("stException")).to_have_count(0)


def choose(page, label, value):
    control = page.get_by_role("combobox", name=label, exact=True)
    control.locator("..").get_by_role("button").click()
    option = page.get_by_role("option", name=value, exact=True)
    try:
        expect(option).to_be_visible(timeout=5_000)
    except AssertionError:
        Path(".runtime/ui-debug.txt").write_text(
            page.locator("body").inner_text(), encoding="utf-8"
        )
        page.screenshot(path=".runtime/ui-debug.png", full_page=True)
        raise
    option.click()


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto("http://127.0.0.1:8501")
    expect(page.get_by_role("heading", name="Your test suite, in focus.")).to_be_visible(
        timeout=60_000
    )
    idle(page)
    radio = page.get_by_test_id("stSidebar").get_by_role("radio", name="Overview", exact=True)
    radio.focus()
    page.keyboard.press("ArrowDown")
    expect(page.get_by_role("heading", name="Flaky Tests", exact=True)).to_be_visible(
        timeout=60_000
    )
    idle(page)
    checks.append("Keyboard arrow navigation changes workspace page")
    page.get_by_test_id("stSidebar").get_by_text("Overview", exact=True).click()
    expect(page.get_by_role("heading", name="Your test suite, in focus.")).to_be_visible(
        timeout=60_000
    )
    idle(page)
    page.get_by_role("button", name="Import report", exact=True).click()
    expect(page.get_by_role("heading", name="CI Integration", exact=True)).to_be_visible(
        timeout=60_000
    )
    idle(page)
    expect(page.get_by_test_id("stFileUploader")).to_be_visible()
    checks.append("Header import action opens the working upload form")
    # Isolate the filter/export workflow from the keyboard-focus navigation workflow.
    browser.close()
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto("http://127.0.0.1:8501")
    expect(page.get_by_role("heading", name="Your test suite, in focus.")).to_be_visible(
        timeout=60_000
    )
    idle(page)
    page.get_by_text("Filter workspace", exact=True).click()
    choose(page, "Repository", "demo/commerce")
    metric = page.get_by_test_id("stMetric").filter(
        has=page.get_by_text("Test executions", exact=True)
    )
    expect(metric.get_by_test_id("stMetricValue")).to_have_text("720", timeout=60_000)
    idle(page)
    choose(page, "Status", "failed")
    expect(metric.get_by_test_id("stMetricValue")).to_have_text("144", timeout=60_000)
    idle(page)
    expect(
        page.get_by_text(
            "Status filtering selects outcomes and can bias reliability history.", exact=True
        )
    ).to_be_visible()
    checks.append("Repository/status filters query real API counts (720 total / 144 failed)")
    choose(page, "Status", "All")
    expect(metric.get_by_test_id("stMetricValue")).to_have_text("720", timeout=60_000)
    idle(page)
    page.get_by_test_id("stSidebar").get_by_text("Flaky Tests", exact=True).click()
    expect(page.get_by_role("heading", name="Flaky Tests", exact=True)).to_be_visible(
        timeout=60_000
    )
    idle(page)
    with page.expect_download() as pending:
        page.get_by_role("button", name="Export reliability data", exact=True).click()
    download = pending.value
    destination = Path(".runtime/export-check.csv")
    download.save_as(destination)
    exported = pd.read_csv(destination)
    assert len(exported) == 24 and set(exported["provenance"]) == {"synthetic"}
    checks.append("CSV export contains 24 scoped reliability cohorts and provenance labels")
    browser.close()
    browser = p.chromium.launch()
    mobile = browser.new_page(
        viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
    )
    mobile.goto("http://127.0.0.1:8501")
    expect(mobile.get_by_role("heading", name="Your test suite, in focus.")).to_be_visible(
        timeout=60_000
    )
    idle(mobile)
    mobile.get_by_test_id("stSidebarCollapseButton").get_by_role("button").click()
    assert mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    cards = mobile.get_by_test_id("stMetric")
    boxes = [cards.nth(i).bounding_box() for i in range(4)]
    assert abs(boxes[0]["y"] - boxes[1]["y"]) < 3
    assert boxes[2]["y"] > boxes[0]["y"]
    mobile.screenshot(path="docs/evidence/screenshots/mobile-overview.png", full_page=True)
    checks.append(
        "390px mobile layout: collapsible navigation, two-column metric grid, no page overflow"
    )
    browser.close()
Path("docs/evidence/ui-interactions.json").write_text(
    json.dumps({"checks": checks, "passed": len(checks)}, indent=2), encoding="utf-8"
)
print(f"{len(checks)} UI interaction checks passed")
