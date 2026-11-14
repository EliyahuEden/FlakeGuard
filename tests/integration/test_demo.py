from datetime import UTC, datetime

from conftest import report
from sqlalchemy import func, select

from flakeguard.analytics import Filters, load_executions, metrics
from flakeguard.demo import generate_reports, reset_demo, seed_demo
from flakeguard.ingestion import atomic_ingest
from flakeguard.models import Execution, Run
from flakeguard.parsers import parse_report
from flakeguard.schemas import ImportContext


def test_seeded_reports_reproducible_and_import_idempotent(session, tmp_path):
    files = generate_reports(tmp_path / "first", rounds=6, seed=2026)
    again = generate_reports(tmp_path / "second", rounds=6, seed=2026)
    assert [p.read_bytes() for p in files] == [p.read_bytes() for p in again]
    assert all(len(parse_report(p.read_bytes(), p.name).results) == 24 for p in files)
    result = seed_demo(session, tmp_path / "import", rounds=6)
    assert result["imported"] == 144
    duplicate = seed_demo(session, tmp_path / "import", rounds=6)
    assert duplicate["imported"] == 0 and duplicate["duplicates"] == 144
    metric = metrics(load_executions(session, Filters(repository="demo/commerce")))
    assert metric.total_executions == 144 and metric.excluded == 24


def test_reset_preserves_non_demo_imports_including_same_repository(session, tmp_path):
    seed_demo(session, tmp_path, rounds=3)
    for repository in ["acme/real", "demo/commerce"]:
        atomic_ingest(
            session,
            report(name="preserved"),
            "real.json",
            ImportContext(
                repository=repository,
                run_id="real-run",
                source="local",
                provenance="real",
                executed_at=datetime(2026, 11, 1, tzinfo=UTC),
            ),
        )
    assert reset_demo(session) == 3
    assert session.scalar(select(func.count(Execution.id))) == 2
    assert set(session.scalars(select(Run.source))) == {"local"}
    assert reset_demo(session) == 0
