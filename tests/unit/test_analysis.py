from datetime import UTC, datetime

import pytest
from conftest import report

from flakeguard.analytics import (
    Filters,
    failure_clusters,
    load_executions,
    metrics,
    reliability,
    trends,
)
from flakeguard.failures import classify, fingerprint, normalize
from flakeguard.ingestion import atomic_ingest
from flakeguard.schemas import ImportContext


def test_empty_dataset(session):
    assert metrics([]).pass_rate is None
    assert reliability([]) == [] and trends([]) == []
    assert failure_clusters(session, [])["clusters"] == []


@pytest.mark.parametrize(
    "statuses,expected",
    [
        ([["passed"]] * 8, "consistently_passing"),
        ([["failed"]] * 8, "consistently_failing"),
        ([["failed", "passed"], ["passed"]] * 4, "suspected_flaky"),
        ([["failed"], ["passed"]] * 4, "suspected_flaky"),
        ([["passed"]] * 4, "insufficient_history"),
        ([["passed"]] * 6 + [["failed"]] * 2, "intermittent_failures"),
    ],
)
def test_reliability_categories(session, ingest_history, statuses, expected):
    ingest_history(statuses)
    assert reliability(load_executions(session, Filters()))[0]["classification"] == expected


def test_metrics_denominators(session, ingest_history):
    ingest_history([["passed"], ["failed", "passed"], ["failed", "failed"], ["skipped"], []])
    m = metrics(load_executions(session, Filters()))
    assert m.total_executions == 5 and m.eligible_executions == 3
    assert m.pass_rate == pytest.approx(2 / 3)
    assert m.first_attempt_pass_rate == pytest.approx(1 / 3)
    assert m.retry_recovery_rate == 0.5 and m.excluded == 2


def test_junit_unknown_retry_excluded(session):
    atomic_ingest(
        session,
        b'<testsuite><testcase name="a" time="1"/></testsuite>',
        "a.xml",
        ImportContext(repository="a/b", run_id="1"),
    )
    m = metrics(load_executions(session, Filters()))
    assert m.pass_rate == 1 and m.first_attempt_pass_rate is None
    assert m.retry_recovery_rate is None and m.known_retry_observations == 0


def test_no_alternation_across_branches(session):
    for index in range(8):
        atomic_ingest(
            session,
            report(["passed"] if index % 2 else ["failed"]),
            "a.json",
            ImportContext(
                repository="a/b",
                run_id=str(index),
                branch="main" if index % 2 else "release",
                executed_at=datetime(2026, 10, index + 1, tzinfo=UTC),
            ),
        )
    rows = reliability(load_executions(session, Filters()))
    assert len(rows) == 2 and all(row["alternations"] == 0 for row in rows)


def test_filtering_and_trends(session, ingest_history):
    ingest_history([["passed"], ["failed"]])
    assert len(load_executions(session, Filters(status="failed"))) == 1
    assert load_executions(session, Filters(repository="missing/repo")) == []
    trend = trends(load_executions(session, Filters()))
    assert [r["pass_rate"] for r in trend] == [1, 0]


def test_fingerprint_volatile_normalization():
    left = "Error request-id=abc-123 at 2026-10-01T12:30:44Z 123e4567-e89b-12d3-a456-426614174000"
    right = "Error request-id=xyz-456 at 2026-11-02T01:00:00Z 123e4567-e89b-12d3-a456-426614174001"
    assert fingerprint(left)[0] == fingerprint(right)[0]
    assert (
        fingerprint("AssertionError expected: 400 received: 500")[0]
        != fingerprint("AssertionError expected: 200 received: 500")[0]
    )
    assert "\x1b" not in normalize("\x1b[31mError\x1b[0m")


@pytest.mark.parametrize(
    "text,kwargs,category",
    [
        ("connect ECONNREFUSED localhost", {}, "suspected_infrastructure"),
        ("browser crashed", {}, "suspected_infrastructure"),
        ("fixture setup failed", {}, "suspected_automation"),
        ("strict mode violation", {}, "suspected_automation"),
        ("AssertionError: expected: 10", {"consecutive_failures": 4}, "suspected_application"),
        ("TimeoutError", {}, "unknown"),
        ("TimeoutError", {"recovered": True}, "suspected_automation"),
        ("something unusual", {}, "unknown"),
    ],
)
def test_classifications(text, kwargs, category):
    result = classify(text, **kwargs)
    assert result.category == category
    assert result.investigation_steps and result.explanation


def test_old_pattern_not_new_after_date_filter(session, ingest_history):
    ingest_history([["failed"], ["failed"]])
    rows = load_executions(session, Filters(start=datetime(2026, 10, 2, tzinfo=UTC)))
    cluster = failure_clusters(session, rows)["clusters"][0]
    assert cluster["new_in_selection"] is False
    assert cluster["occurrences"] == 1


def test_clusters_count_failed_attempts(session, ingest_history):
    ingest_history([["failed", "passed"], ["failed", "failed"]])
    cluster = failure_clusters(session, load_executions(session, Filters()))["clusters"][0]
    assert cluster["occurrences"] == 3 and cluster["executions"] == 2
