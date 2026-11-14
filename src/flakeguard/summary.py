from html import escape
from typing import Any

from sqlalchemy.orm import Session

from flakeguard.analytics import Filters, failure_clusters, load_executions, metrics, reliability


def safe(value: Any) -> str:
    return escape(str(value)).replace("|", "&#124;").replace("\n", " ").replace("`", "&#96;")


def quality_summary(session: Session, run_id: int) -> str:
    current = load_executions(session, Filters(run_id=run_id))
    if not current:
        return "# FlakeGuard quality summary\n\nNo executions found for this run.\n"
    run = current[0].run
    history = load_executions(
        session,
        Filters(
            repository=run.repository.name,
            branch=run.branch,
            provenance=run.provenance,
            end=run.executed_at,
        ),
    )
    scores = reliability(history)
    clusters = failure_clusters(session, current)["clusters"]
    historical_patterns = {
        c["fingerprint"]: c["classification"]
        for c in failure_clusters(session, history)["clusters"]
    }
    metric = metrics(current)
    text = [
        "# FlakeGuard quality summary",
        "",
        f"Repository **{safe(run.repository.name)}**, branch **{safe(run.branch)}**, commit `{safe(run.commit_sha or 'unknown')}`.",
        f"Provenance: **{run.provenance}**. {metric.total_executions} executions; {metric.failed} final failures; {metric.retry_recoveries} observed retry recoveries.",
        "",
        "Suspected flakiness is an investigation signal. Required quality gates remain authoritative.",
        "",
        "## Failed tests",
        "",
        "| Test | Status | Historical context |",
        "|---|---|---|",
    ]
    for ex in current:
        if ex.status in {"failed", "timedOut"}:
            score = next(
                (
                    s
                    for s in scores
                    if s["test_id"] == ex.test_id
                    and s["browser"] == ex.browser
                    and s["environment"] == ex.environment
                ),
                {},
            )
            label = f"{ex.test.name} [{ex.test.project}; {ex.browser or 'browser unknown'}]"
            text.append(
                f"| {safe(label)} | {ex.status} | {score.get('observations', 0)} observations; {safe(score.get('classification', 'unknown'))} |"
            )
    if not metric.failed:
        text.append("| None | — | — |")
    text.extend(["", "## Suspected flaky tests", ""])
    suspects = [
        s
        for s in scores
        if s["classification"] == "suspected_flaky" and s["test_id"] in {e.test_id for e in current}
    ]
    text.extend(
        [
            f"- {safe(s['name'])} [{safe(s['project'])}; {safe(s['browser'] or 'browser unknown')}]: {s['retry_recoveries']} observed retry recoveries across {s['observations']} observations."
            for s in suspects
        ]
        or ["No tests meet the evidence threshold."]
    )
    text.extend(["", "## Failure patterns and next steps", ""])
    for cluster in clusters:
        classification = historical_patterns.get(cluster["fingerprint"], cluster["classification"])
        text.append(
            f"- `{cluster['fingerprint'][:12]}` — {cluster['occurrences']} failed attempts; "
            f"{'new in this repository/provenance history' if cluster['new_in_selection'] else 'previously observed'}; "
            f"{classification['category']} ({classification['evidence_strength']} evidence). "
            + safe(classification["investigation_steps"][0])
        )
    if run.ci_url:
        text.extend(["", f"[CI run and diagnostic artifacts]({run.ci_url})"])
    text.extend(
        [
            "",
            "Fingerprints group diagnostic text, not proven root causes. Unknown retry data is excluded from retry denominators.",
            "",
        ]
    )
    return "\n".join(text)
