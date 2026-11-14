"""Import bundled actual CommerceGuard report projections without external dependencies."""

import json
from pathlib import Path

from flakeguard.db import session_factory
from flakeguard.ingestion import atomic_ingest
from flakeguard.schemas import ImportContext

manifest = json.loads(Path("docs/evidence/commerceguard.json").read_text(encoding="utf-8"))
with session_factory()() as session:
    for item in manifest:
        path = Path("examples/reports") / item["file"]
        result = atomic_ingest(
            session,
            path.read_bytes(),
            path.name,
            ImportContext(
                repository="portfolio/commerceguard",
                run_id=path.stem,
                branch="main",
                provenance=item["provenance"],
            ),
        )
        print(json.dumps({"file": path.name, **result.model_dump()}))
