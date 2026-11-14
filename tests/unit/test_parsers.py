import json

import pytest
from conftest import report

from flakeguard.parsers import ReportError, parse_report


def test_playwright_retries_and_browser():
    result = parse_report(report(["failed", "passed"]), "results.json")
    case = result.results[0]
    assert [a.retry_index for a in case.attempts] == [0, 1]
    assert case.browser == "chromium"
    assert case.attempts[0].error_message


def test_missing_retry_and_browser_not_inferred():
    data = json.loads(report(retries=False))
    data["config"] = {}
    result = parse_report(json.dumps(data).encode(), "results.json").results[0]
    assert result.attempts[0].retry_index is None
    assert result.browser is None  # Project name is not explicit browser metadata.


@pytest.mark.parametrize(
    "content,filename",
    [
        (b"", "a.json"),
        (b"{", "a.json"),
        (b"[]", "a.json"),
        (b"{}", "a.json"),
        (b"<bad/>", "a.xml"),
        (b"<testsuite>", "a.xml"),
        (b"a", "a.txt"),
        (b"<testsuite><testcase/></testsuite>", "a.xml"),
        (b'<!DOCTYPE x [<!ENTITY x SYSTEM "file:///secret">]><testsuite>&x;</testsuite>', "a.xml"),
    ],
)
def test_invalid_reports(content, filename):
    with pytest.raises(ReportError):
        parse_report(content, filename)


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan"), "not a number"])
def test_invalid_duration(value):
    data = json.loads(report())
    data["suites"][0]["specs"][0]["tests"][0]["results"][0]["duration"] = value
    with pytest.raises(ReportError):
        parse_report(json.dumps(data).encode(), "a.json")


def test_size_and_count_limits():
    with pytest.raises(ReportError, match="byte limit"):
        parse_report(report(), "a.json", max_bytes=4)
    with pytest.raises(ReportError, match="result count"):
        parse_report(report(), "a.json", max_results=0)


def test_nested_junit_and_unknown_retries():
    data = b"""<testsuites><testsuite name="api" timestamp="2026-10-01T12:00:00Z">
    <properties><property name="environment" value="staging"/></properties>
    <testcase name="happy" classname="cart" time="0.25"/>
    <testcase name="sad" time="1"><failure message="expected: 10">trace</failure></testcase>
    <testcase name="setup"><error message="fixture setup failed"/></testcase>
    <testcase name="skip"><skipped/></testcase></testsuite></testsuites>"""
    result = parse_report(data, "a.xml")
    assert [r.attempts[0].status for r in result.results] == [
        "passed",
        "failed",
        "failed",
        "skipped",
    ]
    assert result.results[0].attempts[0].duration_ms == 250
    assert all(r.attempts[0].retry_index is None for r in result.results)
    assert result.results[0].environment == "staging"


def test_junit_timezone_not_guessed():
    result = parse_report(
        b'<testsuite timestamp="2026-10-01T12:00:00"><testcase name="x"/></testsuite>', "a.xml"
    )
    assert result.executed_at is None


def test_no_results_preserved_as_unknown():
    result = parse_report(report([]), "a.json")
    assert result.results[0].attempts == []


def test_retry_order_rejected():
    data = json.loads(report(["failed", "passed"]))
    data["suites"][0]["specs"][0]["tests"][0]["results"][1]["retry"] = 0
    with pytest.raises(ReportError, match="Retry indices"):
        parse_report(json.dumps(data).encode(), "a.json")
