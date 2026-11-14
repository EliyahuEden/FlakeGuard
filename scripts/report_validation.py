"""Summarize recorded evidence; fails instead of documenting a failing test run as green."""

import json
import subprocess
from pathlib import Path

from defusedxml import ElementTree

evidence = Path("docs/evidence")
root = ElementTree.parse(evidence / "platform-tests.xml").getroot()
suites = root.findall("testsuite")
totals = {
    key: sum(int(s.get(key, "0")) for s in suites)
    for key in ("tests", "failures", "errors", "skipped")
}
assert totals["failures"] == totals["errors"] == 0, totals
passed = totals["tests"] - totals["skipped"]
elapsed = sum(float(s.get("time", "0")) for s in suites)
evaluation = json.loads((evidence / "evaluation.json").read_text(encoding="utf-8"))
coverage = json.loads((evidence / "coverage.json").read_text(encoding="utf-8"))["totals"]
browser = json.loads((evidence / "browser-check.json").read_text(encoding="utf-8"))
environment = json.loads((evidence / "environment.json").read_text(encoding="utf-8"))
assert browser["browser_upload_to_api_and_postgresql"] and not browser["javascript_errors"]
benchmark = evaluation["import_benchmark"]
classification = evaluation["classification"]
confusion = classification["confusion_matrix_rows_actual_columns_predicted"]
live = ElementTree.parse(evidence / "live-api-tests.xml").getroot().findall("testsuite")
live_passed = sum(
    int(s.get("tests", "0"))
    - int(s.get("skipped", "0"))
    - int(s.get("failures", "0"))
    - int(s.get("errors", "0"))
    for s in live
)
body = f"""# Verified validation results

Recorded on 14 November 2026. Raw evidence lives beside this document in `evidence/`.

## Environment and checks

- Windows, CPython {environment["python"]}, actual PostgreSQL {environment["postgresql_version"]} on loopback.
- Platform suite: **{passed} passed, {totals["skipped"]} skipped, zero failures/errors**, {elapsed:.2f} seconds. The skipped item is the separately enabled live API check.
- Live HTTP suite: **{live_passed} passed**, against the seeded PostgreSQL-backed API.
- Chromium: **{len(browser["pages"])}/5 pages rendered**, zero JavaScript errors, report uploaded through Streamlit and retrieved through the API/PostgreSQL.
- Ruff lint and formatting passed; strict mypy passed for 15 backend/service modules (dashboard excluded from strict typing).
- Alembic migration and PostgreSQL schema-drift checks passed. `pip check` found no incompatible installed requirements.
- Whole-package pytest line coverage: **{coverage["percent_covered"]:.2f}%** ({coverage["covered_lines"]}/{coverage["num_statements"]} statements). Browser/CLI subprocess coverage is not combined into this figure.
- One upstream TestClient/httpx deprecation warning remains; it does not indicate a failed test.

## Data imported and correctness

| Source | Records | Provenance |
|---|---:|---|
| Seeded daily Playwright histories | 720 | synthetic |
| 12 actually executed controlled pytest runs | 72 | injected |
| Three existing actual CommerceGuard report projections | 119 | 118 real + 1 injected |
| Browser validation upload | 1 | injected; reserved E2E repository |

The repeat demo invocation imported zero new synthetic rows and reported 720 duplicates. Existing executed injected demo runs were skipped. The actual CommerceGuard fixtures are independently checked for expected execution counts and idempotency. XML and JSON are tested through normal parsers, not dashboard constants. Demo reset preservation is covered by integration tests.

## Import throughput

One local **{benchmark["executions"]:,}-execution PostgreSQL import** took **{benchmark["seconds"]:.4f} s**, or **{benchmark["executions_per_second"]:.2f} executions/s**. All {benchmark["verified_rows_before_rollback"]:,} rows were counted before rollback. Exact reimport recognized {benchmark["duplicate_reimport_count"]:,} duplicates in {benchmark["duplicate_seconds"]:.4f} s.

Scope: {benchmark["scope"]} This is one workstation measurement, not a load-test claim or service capacity guarantee.

## Reliability behavior on the seeded dataset

- 720 total / 600 eligible executions, 456 final passes, 144 final failures, 60 skipped and 60 unknown.
- Final pass rate 76%; first-attempt pass rate 70%; 36 observed retry recoveries from 36 initially failed executions actually retried.
- Six suspected flaky test identities across two explicit browsers, representing three distinct scenario types.
- Scenario detection: **100% precision, 75% recall** over four authored intermittent scenario types. Timing recovery, connection recovery, and shared-state contamination were detected; lower-frequency fixture setup failures remained below the threshold.
- Deterministic regression remained consistently failing. A late sustained regression was not labeled suspected flaky merely because it followed passing runs.

## Synthetic classification evaluation

**{classification["cases"]} authored diagnostic cases**, four labels with eight cases each. Accuracy **{classification["accuracy"]:.3%}**, macro precision **{classification["macro_precision"]:.2%}**, macro recall **{classification["macro_recall"]:.3%}**.

Rows are injected ground-truth labels; columns are heuristic predictions:

| Actual / predicted | Application | Automation | Infrastructure | Unknown |
|---|---:|---:|---:|---:|
"""
labels = list(confusion)
for label in labels:
    body += f"| {label} | " + " | ".join(str(confusion[label][p]) for p in labels) + " |\n"
body += "\n| Class | Precision | Recall | F1 | Support |\n|---|---:|---:|---:|---:|\n"
for label, row in classification["per_class"].items():
    body += f"| {label} | {row['precision']:.3f} | {row['recall']:.3f} | {row['f1']:.3f} | {row['support']} |\n"
body += """
Three ambiguous cases were labeled unknown: an application deadlock with timeout-only diagnostics, a stale selector without explanatory diagnostics, and infrastructure packet loss reported only as a timeout. This is useful abstention but still a recall miss against known injected ground truth.

The set is small, authored, and not independently held out. It shares design assumptions with the rules. These numbers are not estimates of production defect detection accuracy.

## Fingerprinting

Twelve authored diagnostic pairs: six known text-equivalent pairs correctly grouped, six meaningfully different pairs kept separate, zero false merges/splits in that set. Precision and recall 1.0 on these examples. This measures deterministic normalization, not root-cause clustering quality in real incidents.

## Unverified or incomplete scope

- Docker image/Compose startup and Linux behavior: configuration and CI smoke job provided, not locally executed because Docker was unavailable.
- Live authenticated GitHub synchronization: implemented with transport/error/archive tests; no authorized live repository sync performed.
- GitHub Actions workflow definitions have not been run on hosted Actions during this local build.
- Browser-specific failures in the seeded history are synthetic, not executed Firefox/WebKit regressions.
- No PR-comment writer, scheduled background sync, artifact file hosting, multi-user authorization, calibrated classifier, or deployment.
- Real CommerceGuard reports verify ingestion, not real-world classification accuracy; CommerceGuard was not rerun.

See `COMMANDS_EXECUTED.md`, `TEST_STRATEGY.md`, and the raw JUnit/coverage/evaluation/browser artifacts for audit details.
"""
hosted_file = evidence / "hosted-actions.json"
if hosted_file.exists():
    hosted = json.loads(hosted_file.read_text(encoding="utf-8"))
    if hosted["conclusion"] == "success":
        body = body.replace(
            "- Docker image/Compose startup and Linux behavior: configuration and CI smoke job provided, not locally executed because Docker was unavailable.",
            "- Docker image/Compose startup, PostgreSQL migrations, demo seeding, API/dashboard health, and cleanup passed on GitHub-hosted Linux. Docker remains unavailable on the local Windows machine.",
        ).replace(
            "- GitHub Actions workflow definitions have not been run on hosted Actions during this local build.",
            f"- Hosted GitHub Actions validation passed: [{hosted['run_id']}]({hosted['url']}), code commit `{hosted['code_commit'][:8]}`. Both `validate` and `compose` jobs succeeded.",
        )
        body += f"\n## Hosted CI evidence\n\nRepository: [EliyahuEden/FlakeGuard](https://github.com/EliyahuEden/FlakeGuard). [Verified workflow run]({hosted['url']}); exact code commit `{hosted['code_commit']}`. Metadata and individual step outcomes are recorded in `evidence/hosted-actions.json`.\n"
Path("docs/VALIDATION.md").write_text(body, encoding="utf-8")
structure_path = Path("docs/FILE_STRUCTURE.md")
structure_path.touch(exist_ok=True)
files = subprocess.run(
    [
        "rg",
        "--files",
        "--hidden",
        "-g",
        "!.git",
        "-g",
        "!.env",
        "-g",
        "!.venv",
        "-g",
        "!.runtime",
        "-g",
        "!.pytest_cache",
        "-g",
        "!.mypy_cache",
        "-g",
        "!.ruff_cache",
        "-g",
        "!.coverage",
        "-g",
        "!*.egg-info",
        "-g",
        "!**/__pycache__/**",
    ],
    capture_output=True,
    text=True,
    encoding="utf-8",
    check=True,
).stdout.splitlines()
structure_path.write_text(
    "# Complete project file structure\n\nSource, configuration, fixtures, tests, and deliverable evidence. Local secrets, dependencies, caches, generated runtime reports, and database files are intentionally excluded.\n\n```text\n"
    + "\n".join(sorted(path.replace("\\", "/") for path in files))
    + "\n```\n",
    encoding="utf-8",
)
print(
    f"Recorded validation: {passed} passed, {totals['skipped']} skipped; {live_passed} live API check; five browser pages."
)
