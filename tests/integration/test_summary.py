import pytest
from pydantic import ValidationError

from flakeguard.analytics import Filters, load_executions
from flakeguard.schemas import ImportContext
from flakeguard.summary import quality_summary


def test_summary_uses_historical_evidence_and_names_project(session, ingest_history):
    ingest_history([["failed"]] * 8)
    run_id = load_executions(session, Filters())[-1].run_id
    summary = quality_summary(session, run_id)
    assert "[chromium; chromium]" in summary
    assert "8 observations; consistently_failing" in summary
    assert "suspected_application (moderate evidence)" in summary
    assert "previously observed" in summary


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "https://evil.example/run",
        "http://github.com/a/b",
        "https://user@github.com/a/b",
    ],
)
def test_ci_links_reject_unsafe_targets(url):
    with pytest.raises(ValidationError):
        ImportContext(repository="a/b", run_id="1", ci_url=url)
