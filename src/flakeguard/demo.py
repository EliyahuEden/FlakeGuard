"""Seeded report generation goes through the same parsers and transactions as uploads."""

import json
import os
import random
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from flakeguard.ingestion import atomic_ingest
from flakeguard.models import (
    Artifact,
    Attempt,
    Execution,
    ReportImport,
    Repository,
    Run,
    SyncState,
    TestCase,
)
from flakeguard.schemas import ImportContext

SCENARIOS = [
    "catalog passes",
    "checkout regression",
    "timing recovery",
    "connection recovery",
    "shared-state contamination",
    "fixture setup failure",
    "browser-specific failure",
    "new regression",
    "slow inventory lookup",
    "skipped contract",
    "unexecuted test",
    "rare one-off failure",
]


def generate_reports(directory: Path, rounds: int = 30, seed: int = 2026) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    files = []
    base = datetime(2026, 10, 1, 9, tzinfo=UTC)
    for run in range(rounds):
        specs = []
        for index, name in enumerate(SCENARIOS):
            for browser in ("chromium", "firefox"):
                status, message, retry = "passed", None, False
                if index == 1:
                    status, message = (
                        "failed",
                        "AssertionError: expected: cart total 120; received: 100",
                    )
                elif index == 2 and run % 3 == 0:
                    message, retry = "TimeoutError: locator checkout button timed out", True
                elif index == 3 and run % 4 == 0:
                    message, retry = "Error: connect ECONNREFUSED 127.0.0.1:8080", True
                elif index == 4 and run % 2 == 0:
                    status, message = (
                        "failed",
                        "AssertionError: shared state from previous cart test",
                    )
                elif index == 5 and run % 5 == 0:
                    status, message = (
                        "failed",
                        "Error: fixture setup failed: seeded customer unavailable",
                    )
                elif index == 6 and browser == "firefox":
                    status, message = (
                        "failed",
                        "AssertionError: expected: accessible menu visible; received: hidden",
                    )
                elif index == 7 and run >= rounds - 5:
                    status, message = (
                        "failed",
                        "AssertionError: expected: promotion applied; received: full price",
                    )
                elif index == 9:
                    status = "skipped"
                elif index == 10:
                    status = "unknown"
                elif index == 11 and run == 7:
                    status, message = "failed", "Error: unexplained worker response"
                ms = round(rng.uniform(30, 200) + (run * 25 if index == 8 else 0), 2)
                started = (base + timedelta(days=run)).isoformat()
                results: list[dict[str, Any]] = []
                if retry:
                    results.append(
                        {
                            "status": "failed",
                            "duration": 1000,
                            "retry": 0,
                            "startTime": started,
                            "errors": [{"message": message}],
                        }
                    )
                if status != "unknown":
                    results.append(
                        {
                            "status": status,
                            "duration": ms,
                            "retry": int(retry),
                            "startTime": started,
                            "errors": [{"message": message}] if message and not retry else [],
                            "attachments": [
                                {
                                    "name": "trace",
                                    "contentType": "application/zip",
                                    "path": f"traces/{run}/{index}.zip",
                                }
                            ]
                            if status == "failed"
                            else [],
                        }
                    )
                specs.append(
                    {
                        "title": name,
                        "file": "shop.spec.ts",
                        "tests": [
                            {
                                "projectName": browser,
                                "expectedStatus": "passed",
                                "repeatEachIndex": 0,
                                "results": results,
                            }
                        ],
                    }
                )
        report = {
            "config": {
                "rootDir": ".",
                "projects": [
                    {
                        "name": b,
                        "use": {"browserName": b},
                        "metadata": {"environment": "seeded-demo"},
                    }
                    for b in ("chromium", "firefox")
                ],
            },
            "suites": [{"title": "commerce", "specs": specs, "suites": []}],
            "stats": {"startTime": (base + timedelta(days=run)).isoformat()},
        }
        path = directory / f"run-{run:03}.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        files.append(path)
    return files


def seed_demo(
    session: Session, directory: Path = Path(".runtime/demo"), rounds: int = 30
) -> dict[str, int]:
    count = duplicates = 0
    for i, path in enumerate(generate_reports(directory, rounds)):
        result = atomic_ingest(
            session,
            path.read_bytes(),
            path.name,
            ImportContext(
                repository="demo/commerce",
                run_id=f"seed-2026-{i}",
                branch="main",
                commit_sha=f"{i:040x}",
                source="demo",
                provenance="synthetic",
            ),
        )
        count += result.imported
        duplicates += result.duplicates
    return {"imported": count, "duplicates": duplicates, "runs": rounds}


def execute_injected(session: Session, rounds: int = 12) -> dict[str, int]:
    root = Path.cwd()
    suite = root / "examples" / "injected" / "test_scenarios.py"
    directory = root / ".runtime" / "injected"
    directory.mkdir(parents=True, exist_ok=True)
    imported = 0
    existing_runs = set(
        session.scalars(
            select(Run.external_id)
            .join(Repository)
            .where(Repository.name == "demo/injected-pytest", Run.source == "demo")
        )
    )
    for index in range(rounds):
        if f"executed-{index}" in existing_runs:
            continue
        report = directory / f"run-{index}.xml"
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(suite),
                "-q",
                "-o",
                "addopts=",
                f"--junitxml={report}",
            ],
            env={**os.environ, "FLAKEGUARD_SCENARIO_RUN": str(index)},
            capture_output=True,
            timeout=60,
            check=False,
        )
        if process.returncode not in {0, 1} or not report.exists():
            raise RuntimeError("Controlled pytest suite could not produce a report")
        result = atomic_ingest(
            session,
            report.read_bytes(),
            report.name,
            ImportContext(
                repository="demo/injected-pytest",
                run_id=f"executed-{index}",
                branch="main",
                source="demo",
                provenance="injected",
                environment="local-python",
                # pytest XML timestamps omit timezone; capture actual execution time explicitly.
                executed_at=datetime.fromtimestamp(report.stat().st_mtime, UTC),
            ),
        )
        imported += result.imported
    return {"runs": rounds, "imported": imported}


def reset_demo(session: Session) -> int:
    # Deliberately limited to reserved demo repositories AND source=demo.
    repo_ids = list(
        session.scalars(
            select(Repository.id).where(
                Repository.name.in_(["demo/commerce", "demo/injected-pytest"])
            )
        )
    )
    run_ids = list(
        session.scalars(select(Run.id).where(Run.repository_id.in_(repo_ids), Run.source == "demo"))
    )
    ex_ids = select(Execution.id).where(Execution.run_id.in_(run_ids))
    attempts = select(Attempt.id).where(Attempt.execution_id.in_(ex_ids))
    session.execute(delete(Artifact).where(Artifact.attempt_id.in_(attempts)))
    session.execute(delete(Attempt).where(Attempt.execution_id.in_(ex_ids)))
    session.execute(delete(Execution).where(Execution.run_id.in_(run_ids)))
    session.execute(delete(ReportImport).where(ReportImport.run_id.in_(run_ids)))
    session.execute(delete(SyncState).where(SyncState.repository_id.in_(repo_ids)))
    session.execute(delete(Run).where(Run.id.in_(run_ids)))
    orphan_tests = select(TestCase.id).where(
        TestCase.repository_id.in_(repo_ids), ~TestCase.id.in_(select(Execution.test_id))
    )
    session.execute(delete(TestCase).where(TestCase.id.in_(orphan_tests)))
    session.commit()
    return len(run_ids)
