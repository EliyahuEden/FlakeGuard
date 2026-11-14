import json

import pytest
from conftest import report
from sqlalchemy import func, select

from flakeguard.ingestion import atomic_ingest, stable_id
from flakeguard.models import Attempt, Execution, ReportImport, Run
from flakeguard.parsers import ReportError, parse_report
from flakeguard.schemas import ImportContext


def context(**kwargs):
    return ImportContext(repository="acme/shop", run_id="100", **kwargs)


def test_duplicate_and_persistence(session):
    first = atomic_ingest(session, report(["failed", "passed"]), "a.json", context())
    second = atomic_ingest(session, report(["failed", "passed"]), "b.json", context())
    assert (first.imported, second.imported, second.duplicates) == (1, 0, 1)
    assert session.scalar(select(func.count(Execution.id))) == 1
    assert session.scalar(select(func.count(Attempt.id))) == 2
    row = session.scalar(select(Execution))
    assert row.duration_ms == 21 and row.retry_recovered is True and row.first_attempt_pass is False


def test_run_attempt_is_a_separate_execution(session):
    atomic_ingest(session, report(), "a.json", context())
    atomic_ingest(session, report(), "a.json", context(run_attempt=2))
    assert session.scalar(select(func.count(Execution.id))) == 2


def test_conflict_rolls_back_entire_report(session):
    atomic_ingest(session, report(), "a.json", context())
    with pytest.raises(ReportError, match="Conflicting"):
        atomic_ingest(session, report(["failed"]), "b.json", context())
    assert session.scalar(select(func.count(ReportImport.id))) == 1
    assert session.scalar(select(Execution.status)) == "passed"


def test_ambiguous_duplicate_rejects_atomically(session):
    data = json.loads(report())
    data["suites"][0]["specs"].append(data["suites"][0]["specs"][0])
    with pytest.raises(ReportError, match="Ambiguous"):
        atomic_ingest(session, json.dumps(data).encode(), "a.json", context())
    assert session.scalar(select(func.count(Run.id))) == 0
    assert session.scalar(select(func.count(Execution.id))) == 0


def test_unknown_retry_and_empty_result(session):
    atomic_ingest(session, report(retries=False), "a.json", context())
    row = session.scalar(select(Execution))
    assert row.retries is None and row.first_attempt_pass is None and row.retry_recovered is None
    atomic_ingest(session, report([], name="not executed"), "b.json", context())
    unknown = session.scalar(select(Execution).where(Execution.status == "unknown"))
    assert unknown.duration_ms is None and unknown.retries is None


def test_identity_independent_of_line_and_commit():
    parsed = parse_report(report(), "a.json").results[0]
    assert stable_id("ACME/shop", parsed) == stable_id("acme/shop", parsed)
    windows = parsed.model_copy(update={"suite": "ui\\cart.spec.ts", "file": "ui\\cart.spec.ts"})
    posix = parsed.model_copy(update={"suite": "ui/cart.spec.ts", "file": "ui/cart.spec.ts"})
    assert stable_id("acme/shop", windows) == stable_id("acme/shop", posix)
    other = parsed.model_copy(update={"project": "firefox"})
    assert stable_id("acme/shop", parsed) != stable_id("acme/shop", other)


def test_run_metadata_conflict(session):
    atomic_ingest(session, report(), "a.json", context(branch="main"))
    with pytest.raises(ReportError, match="different branch"):
        atomic_ingest(session, report(), "a.json", context(branch="release"))


def test_redaction_before_persistence(session):
    atomic_ingest(
        session,
        report(["failed"], message="Error token=supersecret password=hunter2 ghp_123456"),
        "a.json",
        context(),
    )
    attempt = session.scalar(select(Attempt))
    assert "supersecret" not in attempt.error_message
    assert "hunter2" not in attempt.stack_trace


@pytest.mark.postgres
def test_postgres_persistence_and_idempotency(postgres_session):
    first = atomic_ingest(postgres_session, report(["failed", "passed"]), "a.json", context())
    second = atomic_ingest(postgres_session, report(["failed", "passed"]), "a.json", context())
    assert first.imported == 1 and second.duplicates == 1
    postgres_session.expire_all()
    row = postgres_session.scalar(select(Execution))
    assert row.attempts[1].retry_index == 1
