import json
import platform
import time
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from flakeguard.analytics import Filters, load_executions, metrics, reliability
from flakeguard.failures import classify, fingerprint
from flakeguard.ingestion import ingest
from flakeguard.models import Execution, Run
from flakeguard.schemas import ImportContext


def classification_evaluation() -> dict[str, Any]:
    dataset = Path("examples/evaluation/classification.json")
    content = json.loads(dataset.read_text(encoding="utf-8"))
    labels = content["labels"]
    matrix = {actual: dict.fromkeys(labels, 0) for actual in labels}
    predictions = []
    for case in content["cases"]:
        actual = case["expected"]
        predicted = classify(
            case["text"],
            **{
                k: case[k]
                for k in ("recovered", "affected_tests", "cofailure_ratio", "consecutive_failures")
                if k in case
            },
        ).category
        matrix[actual][predicted] += 1
        predictions.append({"id": case["id"], "actual": actual, "predicted": predicted})
    per_class = {}
    for label in labels:
        tp = matrix[label][label]
        predicted_count = sum(matrix[actual][label] for actual in labels)
        actual_count = sum(matrix[label].values())
        precision = tp / predicted_count if predicted_count else 0
        recall = tp / actual_count if actual_count else 0
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
            "support": actual_count,
        }
    return {
        "provenance": content["provenance"],
        "cases": len(predictions),
        "accuracy": sum(p["actual"] == p["predicted"] for p in predictions) / len(predictions),
        "macro_precision": sum(c["precision"] for c in per_class.values()) / len(labels),
        "macro_recall": sum(c["recall"] for c in per_class.values()) / len(labels),
        "confusion_matrix_rows_actual_columns_predicted": matrix,
        "per_class": per_class,
        "predictions": predictions,
        "limitation": "Small authored diagnostic set, not independently held out. Rules and text cases share design assumptions; no claim of production accuracy.",
    }


def fingerprint_evaluation() -> dict[str, Any]:
    pairs = [
        ("Error request-id=abc-123 unavailable", "Error request-id=xyz-456 unavailable", True),
        ("Error at 2026-10-01T12:00:00Z", "Error at 2026-11-01T13:00:00Z", True),
        ("Crash 0x123abc", "Crash 0x987def", True),
        (
            "AssertionError expected: 10 received: 9\n at /tmp/a.ts:4:2",
            "AssertionError expected: 10 received: 9\n at /tmp/b.ts:99:8",
            True,
        ),
        (
            "Error 123e4567-e89b-12d3-a456-426614174000",
            "Error 123e4567-e89b-12d3-a456-426614174001",
            True,
        ),
        ("\x1b[31mTimeoutError\x1b[0m", "TimeoutError", True),
        (
            "AssertionError expected: 10 received: 9",
            "AssertionError expected: 20 received: 9",
            False,
        ),
        ("HTTP status 401", "HTTP status 500", False),
        ("locator #checkout missing", "locator #login missing", False),
        ("connect ECONNREFUSED", "getaddrinfo ENOTFOUND", False),
        ("fixture setup failed", "fixture teardown failed", False),
        ("browser crashed", "AssertionError", False),
    ]
    tp = fp = fn = tn = 0
    for left, right, expected in pairs:
        matched = fingerprint(left)[0] == fingerprint(right)[0]
        tp += int(matched and expected)
        fp += int(matched and not expected)
        fn += int(not matched and expected)
        tn += int(not matched and not expected)
    return {
        "provenance": "12 synthetic labeled diagnostic pairs, exact-text grouping only",
        "pairs": len(pairs),
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "precision": tp / (tp + fp) if tp + fp else 0,
        "recall": tp / (tp + fn) if tp + fn else 0,
        "limitation": "Evaluates normalization examples, not shared root-cause detection.",
    }


def benchmark_import(session: Session, size: int = 1000) -> dict[str, Any]:
    specs = [
        {
            "title": f"benchmark-{i}",
            "file": "benchmark.spec.ts",
            "tests": [
                {"projectName": "api", "results": [{"status": "passed", "retry": 0, "duration": 1}]}
            ],
        }
        for i in range(size)
    ]
    data = json.dumps({"suites": [{"title": "benchmark", "specs": specs}]}).encode()
    savepoint = session.begin_nested()
    start = time.perf_counter()
    try:
        result = ingest(
            session,
            data,
            "benchmark.json",
            ImportContext(
                repository="benchmark/local",
                run_id=f"benchmark-{time.time_ns()}",
                provenance="synthetic",
            ),
        )
        elapsed = time.perf_counter() - start
        persisted = session.scalar(
            select(func.count(Execution.id)).where(Execution.run_id == result.run_id)
        )
        duplicate_start = time.perf_counter()
        benchmark_run = session.get(Run, result.run_id)
        assert benchmark_run is not None
        duplicate = ingest(
            session,
            data,
            "benchmark.json",
            ImportContext(
                repository="benchmark/local",
                run_id=benchmark_run.external_id,
                provenance="synthetic",
            ),
        )
        duplicate_seconds = time.perf_counter() - duplicate_start
    finally:
        savepoint.rollback()
        session.expire_all()
    return {
        "database": session.get_bind().dialect.name,
        "executions": result.imported,
        "verified_rows_before_rollback": persisted,
        "duplicate_reimport_count": duplicate.duplicates,
        "seconds": round(elapsed, 4),
        "executions_per_second": round(size / elapsed, 2),
        "duplicate_seconds": round(duplicate_seconds, 4),
        "scope": "Single-process parse, normalize, insert, and flush; savepoint rolled back after verification; excludes outer commit, network transfer, and concurrent writers.",
    }


def evaluate_all(session: Session) -> dict[str, Any]:
    synthetic = load_executions(
        session, Filters(repository="demo/commerce", provenance="synthetic")
    )
    scores = reliability(synthetic)
    expected = {
        "timing recovery",
        "connection recovery",
        "shared-state contamination",
        "fixture setup failure",
    }
    predicted = {s["name"] for s in scores if s["classification"] == "suspected_flaky"}
    true_positive = len(expected & predicted)
    return {
        "python": platform.python_version(),
        "platform": platform.system(),
        "dataset": {
            "provenance": "synthetic seed 2026, 30 daily runs, two explicit browsers",
            "metrics": metrics(synthetic).model_dump(),
            "detected_scenario_names": sorted(predicted),
            "expected_intermittent_scenarios": sorted(expected),
            "scenario_precision": true_positive / len(predicted) if predicted else 0,
            "scenario_recall": true_positive / len(expected),
            "note": "Scenario-level evidence of intermittency, not proof of test-code defects. Metrics meaningful only after the standard demo.",
        },
        "classification": classification_evaluation(),
        "fingerprinting": fingerprint_evaluation(),
        "import_benchmark": benchmark_import(session),
        "observations_by_provenance": {
            provenance: int(
                session.scalar(
                    select(func.count(Execution.id)).join(Run).where(Run.provenance == provenance)
                )
                or 0
            )
            for provenance in ("synthetic", "injected", "real")
        },
    }
