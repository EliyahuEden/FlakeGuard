import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from flakeguard.failures import classify, related_patterns
from flakeguard.ingestion import ELIGIBLE_STATUSES, FAIL_STATUSES
from flakeguard.models import Execution, FailurePattern, Repository, Run, TestCase
from flakeguard.schemas import Metrics


def iso(value: datetime) -> str:
    return value.replace(tzinfo=value.tzinfo or UTC).isoformat()


@dataclass
class Filters:
    repository: str | None = None
    branch: str | None = None
    suite: str | None = None
    status: str | None = None
    browser: str | None = None
    environment: str | None = None
    provenance: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    run_id: int | None = None


def execution_query(filters: Filters) -> Select[Execution]:
    query = select(Execution).join(Run).join(Repository).join(TestCase)
    conditions = [
        (filters.repository, Repository.name),
        (filters.branch, Run.branch),
        (filters.suite, TestCase.suite),
        (filters.status, Execution.status),
        (filters.browser, Execution.browser),
        (filters.environment, Execution.environment),
        (filters.provenance, Run.provenance),
        (filters.run_id, Run.id),
    ]
    for value, column in conditions:
        if value is not None:
            query = query.where(column == value)
    if filters.start:
        query = query.where(Run.executed_at >= filters.start)
    if filters.end:
        query = query.where(Run.executed_at <= filters.end)
    return query.order_by(Run.executed_at, Run.id, Execution.id)


def load_executions(session: Session, filters: Filters) -> list[Execution]:
    return list(session.scalars(execution_query(filters)).unique())


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def wilson(successes: int, total: int) -> list[float] | None:
    if not total:
        return None
    z = 1.96
    p = successes / total
    center = (p + z * z / (2 * total)) / (1 + z * z / total)
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return [round(max(0, center - margin), 4), round(min(1, center + margin), 4)]


def reliability(executions: list[Execution]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[Execution]] = defaultdict(list)
    for ex in executions:
        # Branch/environment/provenance changes must not manufacture alternation.
        grouped[(ex.test_id, ex.run.branch, ex.environment_key, ex.run.provenance)].append(ex)
    output = []
    for history in grouped.values():
        history.sort(key=lambda e: (e.run.executed_at, e.run.id, e.id))
        eligible = [e for e in history if e.status in ELIGIBLE_STATUSES]
        n = len(eligible)
        passed = sum(e.status == "passed" for e in eligible)
        failures = n - passed
        recovered = sum(e.retry_recovered is True for e in eligible)
        known = [e for e in eligible if e.retry_recovered is not None]
        initially_failed_retried = [
            e for e in eligible if e.first_attempt_pass is False and (e.retries or 0) > 0
        ]
        # At most one final observation per CI run contributes to alternation evidence.
        runs: dict[int, list[bool]] = defaultdict(list)
        for e in eligible:
            runs[e.run_id].append(e.status == "passed")
        outcomes = [values[0] for values in runs.values() if len(set(values)) == 1]
        transitions = sum(a != b for a, b in zip(outcomes, outcomes[1:], strict=False))
        alternation = transitions / max(1, len(outcomes) - 1)
        recovery_fraction = recovered / len(known) if known else 0
        suspicion = round(100 * (0.7 * recovery_fraction + 0.3 * alternation), 1)
        if n < 5 or len(runs) < 3:
            label = "insufficient_history"
        elif failures == n:
            label = "consistently_failing"
        elif recovered >= 2 or (
            passed > 0 and failures > 0 and transitions >= 2 and suspicion >= 12
        ):
            label = "suspected_flaky"
        elif failures == 0 and recovered == 0:
            label = "consistently_passing"
        else:
            label = "intermittent_failures"
        first_pass = sum(e.first_attempt_pass is True for e in eligible)
        first_observed = sum(e.first_attempt_pass is not None for e in eligible)
        # Reliability is final passing outcomes minus observed retry-dependent passes.
        reliability_score = round(100 * (passed - recovered) / n, 1) if n else None
        recent = eligible[-5:]
        previous = eligible[-10:-5]
        recent_delta = (
            (
                sum(e.status == "passed" for e in recent) / len(recent)
                - sum(e.status == "passed" for e in previous) / len(previous)
            )
            if previous
            else None
        )
        last = history[-1]
        trailing = 0
        for ex in reversed(eligible):
            if ex.status not in FAIL_STATUSES:
                break
            trailing += 1
        output.append(
            {
                "test_id": last.test_id,
                "name": last.test.name,
                "suite": last.test.suite,
                "project": last.test.project,
                "repository": last.run.repository.name,
                "branch": last.run.branch,
                "browser": last.browser,
                "environment": last.environment,
                "provenance": last.run.provenance,
                "observations": n,
                "distinct_runs": len(runs),
                "failure_frequency": ratio(failures, n),
                "final_failures": failures,
                "retry_recoveries": recovered,
                "known_retry_observations": len(known),
                "retry_recovery_rate": ratio(recovered, len(initially_failed_retried)),
                "first_attempt_pass_rate": ratio(first_pass, first_observed),
                "reliability_score": reliability_score,
                "suspicion_score": suspicion,
                "classification": label,
                "alternations": transitions,
                "pass_rate_interval_95": wilson(passed, n),
                "recent_pass_rate_change": recent_delta,
                "consecutive_failures": trailing,
                "last_execution": iso(last.run.executed_at),
                "priority": "high"
                if label in {"suspected_flaky", "consistently_failing"}
                else "normal",
                "explanation": f"{n} eligible observations in {len(runs)} runs; {failures} final failures; {recovered} observed retry recoveries; {transitions} across-run alternations. Suspicion = 100 × (0.7 × recoveries/known retry observations + 0.3 × alternations/adjacent unambiguous run outcomes). Reliability = 100 × (final passes − observed retry recoveries)/eligible observations. Unknown retry history may overestimate reliability.",
            }
        )
    return sorted(
        output, key=lambda r: (-r["suspicion_score"], r["reliability_score"] or 0, r["name"])
    )


def metrics(executions: list[Execution]) -> Metrics:
    eligible = [e for e in executions if e.status in ELIGIBLE_STATUSES]
    passed = sum(e.status == "passed" for e in eligible)
    first = [e for e in eligible if e.first_attempt_pass is not None]
    retried_failures = [
        e for e in eligible if e.first_attempt_pass is False and (e.retries or 0) > 0
    ]
    recovered = sum(e.retry_recovered is True for e in retried_failures)
    durations = [e.duration_ms for e in eligible if e.duration_ms is not None]
    flaky = {
        r["test_id"] for r in reliability(executions) if r["classification"] == "suspected_flaky"
    }
    return Metrics(
        total_executions=len(executions),
        eligible_executions=len(eligible),
        passed=passed,
        failed=len(eligible) - passed,
        skipped=sum(e.status == "skipped" for e in executions),
        excluded=len(executions) - len(eligible),
        pass_rate=ratio(passed, len(eligible)),
        failure_rate=ratio(len(eligible) - passed, len(eligible)),
        first_attempt_observations=len(first),
        first_attempt_pass_rate=ratio(sum(e.first_attempt_pass is True for e in first), len(first)),
        known_retry_observations=sum(e.retry_recovered is not None for e in eligible),
        initially_failed_with_retries=len(retried_failures),
        retry_recoveries=recovered,
        retry_recovery_rate=ratio(recovered, len(retried_failures)),
        average_duration_ms=sum(durations) / len(durations) if durations else None,
        suspected_flaky_tests=len(flaky),
    )


def execution_view(ex: Execution, include_attempts: bool = True) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": ex.id,
        "test_id": ex.test_id,
        "name": ex.test.name,
        "suite": ex.test.suite,
        "project": ex.test.project,
        "run_id": ex.run_id,
        "external_run_id": ex.run.external_id,
        "repository": ex.run.repository.name,
        "branch": ex.run.branch,
        "commit_sha": ex.run.commit_sha,
        "executed_at": iso(ex.run.executed_at),
        "provenance": ex.run.provenance,
        "timestamp_source": ex.run.timestamp_source,
        "browser": ex.browser,
        "environment": ex.environment,
        "status": ex.status,
        "expected_status": ex.expected_status,
        "duration_ms": ex.duration_ms,
        "first_attempt_pass": ex.first_attempt_pass,
        "retry_recovered": ex.retry_recovered,
        "retries": ex.retries,
        "repeat_index": ex.repeat_index,
        "ci_url": ex.run.ci_url,
    }
    if include_attempts:
        result["attempts"] = [
            {
                "ordinal": a.ordinal,
                "retry_index": a.retry_index,
                "status": a.status,
                "duration_ms": a.duration_ms,
                "started_at": iso(a.started_at) if a.started_at else None,
                "error_message": a.error_message,
                "stack_trace": a.stack_trace,
                "fingerprint": a.fingerprint,
                "artifacts": [
                    {"name": f.name, "content_type": f.content_type, "path": f.path, "url": f.url}
                    for f in a.artifacts
                ],
            }
            for a in ex.attempts
        ]
    return result


def failure_clusters(session: Session, executions: list[Execution]) -> dict[str, Any]:
    grouped: dict[str, list[tuple[Execution, Any]]] = defaultdict(list)
    run_totals: dict[int, int] = defaultdict(int)
    for ex in executions:
        if ex.status in ELIGIBLE_STATUSES:
            run_totals[ex.run_id] += 1
        for attempt in ex.attempts:
            if attempt.fingerprint:
                grouped[attempt.fingerprint].append((ex, attempt))
    # Global first seen is scoped by repository and provenance; date filters must not
    # make an old pattern look new. Branches deliberately share pattern history.
    scope = {(ex.run.repository_id, ex.run.provenance) for ex in executions}
    global_first: dict[tuple[str, int, str], datetime] = {}
    if scope and grouped:
        for ex in session.scalars(
            select(Execution)
            .join(Run)
            .where(
                Run.repository_id.in_({s[0] for s in scope}),
                Run.provenance.in_({s[1] for s in scope}),
            )
        ).unique():
            if (ex.run.repository_id, ex.run.provenance) not in scope:
                continue
            for a in ex.attempts:
                if a.fingerprint in grouped:
                    key = (a.fingerprint, ex.run.repository_id, ex.run.provenance)
                    date = ex.run.executed_at
                    global_first[key] = min(date, global_first.get(key, date))
    clusters = []
    patterns: dict[str, str] = {}
    reliability_rows = reliability(executions)
    for fp, occurrences in grouped.items():
        pattern = session.get(FailurePattern, fp)
        assert pattern is not None
        patterns[fp] = pattern.normalized_text
        affected = {ex.test_id for ex, _ in occurrences}
        run_tests: dict[int, set[int]] = defaultdict(set)
        for ex, _ in occurrences:
            run_tests[ex.run_id].add(ex.id)
        max_cofailure = max(len(ids) / max(1, run_totals[r]) for r, ids in run_tests.items())
        trailing = max(
            (r["consecutive_failures"] for r in reliability_rows if r["test_id"] in affected),
            default=0,
        )
        classification = classify(
            pattern.normalized_text,
            recovered=any(ex.retry_recovered for ex, _ in occurrences),
            affected_tests=len(affected),
            cofailure_ratio=max_cofailure,
            consecutive_failures=trailing,
        )
        first = min(ex.run.executed_at for ex, _ in occurrences)
        latest = max(ex.run.executed_at for ex, _ in occurrences)
        historical_first = min(
            global_first[(fp, ex.run.repository_id, ex.run.provenance)] for ex, _ in occurrences
        )
        clusters.append(
            {
                "fingerprint": fp,
                "normalized_text": pattern.normalized_text,
                "occurrences": len(occurrences),
                "affected_tests": len(affected),
                "executions": len({ex.id for ex, _ in occurrences}),
                "runs": len({ex.run_id for ex, _ in occurrences}),
                "first_seen": iso(historical_first),
                "first_in_filter": iso(first),
                "last_seen": iso(latest),
                "new_in_selection": historical_first == first,
                "classification": classification.to_dict(),
                "examples": [
                    {
                        "test_id": ex.test_id,
                        "name": ex.test.name,
                        "run_id": ex.run_id,
                        "ci_url": ex.run.ci_url,
                        "error_message": a.error_message,
                        "stack_trace": a.stack_trace,
                    }
                    for ex, a in occurrences[-5:]
                ],
            }
        )
    return {
        "clusters": sorted(clusters, key=lambda c: -c["occurrences"]),
        "similarity_suggestions": related_patterns(patterns),
        "similarity_note": "Similar wording suggests investigation only; exact clusters remain separate. Suggestions limited to 200 patterns.",
    }


def trends(executions: list[Execution]) -> list[dict[str, Any]]:
    if not executions:
        return []
    frame = pd.DataFrame(
        [
            {
                "date": iso(e.run.executed_at)[:10],
                "eligible": e.status in ELIGIBLE_STATUSES,
                "passed": e.status == "passed",
                "duration_ms": e.duration_ms,
            }
            for e in executions
        ]
    )
    rows = []
    for day, group in frame.groupby("date", sort=True):
        eligible = group[group["eligible"]]
        rows.append(
            {
                "date": str(day),
                "total": len(group),
                "pass_rate": float(eligible["passed"].mean()) if len(eligible) else None,
                "average_duration_ms": float(eligible["duration_ms"].mean())
                if eligible["duration_ms"].notna().any()
                else None,
            }
        )
    return rows


def breakdown(executions: list[Execution], field: str) -> list[dict[str, Any]]:
    groups: dict[str, list[Execution]] = defaultdict(list)
    for ex in executions:
        value = (
            ex.test.suite
            if field == "suite"
            else ex.run.branch
            if field == "branch"
            else ex.browser
        )
        groups[value or "unknown"].append(ex)
    return [{"name": name, **metrics(group).model_dump()} for name, group in sorted(groups.items())]


def newly_failing(session: Session, executions: list[Execution]) -> list[dict[str, Any]]:
    result = []
    for ex in executions:
        if ex.status not in FAIL_STATUSES:
            continue
        previous = session.scalar(
            select(Execution)
            .join(Run)
            .where(
                Execution.test_id == ex.test_id,
                Execution.environment_key == ex.environment_key,
                Run.branch == ex.run.branch,
                Run.provenance == ex.run.provenance,
                Run.executed_at < ex.run.executed_at,
                Execution.status.in_(ELIGIBLE_STATUSES),
            )
            .order_by(Run.executed_at.desc(), Execution.id.desc())
            .limit(1)
        )
        if previous and previous.status == "passed":
            result.append(
                {
                    "test_id": ex.test_id,
                    "name": ex.test.name,
                    "run_id": ex.run_id,
                    "last_passing_run_id": previous.run_id,
                    "commit_sha": ex.run.commit_sha,
                }
            )
    return result
