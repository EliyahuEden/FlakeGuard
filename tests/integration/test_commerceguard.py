import json
from pathlib import Path

from sqlalchemy import func, select

from flakeguard.ingestion import atomic_ingest
from flakeguard.models import Execution
from flakeguard.schemas import ImportContext


def test_actual_commerceguard_report_projections(session):
    manifest = json.loads(Path("docs/evidence/commerceguard.json").read_text(encoding="utf-8"))
    for entry in manifest:
        path = Path("examples/reports") / entry["file"]
        result = atomic_ingest(
            session,
            path.read_bytes(),
            path.name,
            ImportContext(
                repository="portfolio/commerceguard",
                run_id=path.stem,
                branch="main",
                provenance=entry["provenance"],
            ),
        )
        assert result.imported == entry["executions"]
        assert (
            atomic_ingest(
                session,
                path.read_bytes(),
                path.name,
                ImportContext(
                    repository="portfolio/commerceguard",
                    run_id=path.stem,
                    branch="main",
                    provenance=entry["provenance"],
                ),
            ).duplicates
            == entry["executions"]
        )
    assert session.scalar(select(func.count(Execution.id))) == sum(
        e["executions"] for e in manifest
    )
