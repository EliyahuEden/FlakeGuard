import hashlib
import json
from pathlib import PurePath

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from flakeguard.config import Settings
from flakeguard.failures import fingerprint, redact
from flakeguard.models import (
    Artifact,
    Attempt,
    Execution,
    FailurePattern,
    ReportImport,
    Repository,
    Run,
    TestCase,
    utcnow,
)
from flakeguard.parsers import ReportError, parse_report
from flakeguard.schemas import ImportContext, ImportResult, ResultData

FAIL_STATUSES = {"failed", "timedOut"}
ELIGIBLE_STATUSES = {"passed", *FAIL_STATUSES}


class IngestionConflict(ReportError):
    """Existing run or execution conflicts with the incoming observations."""


def stable_id(repository: str, result: ResultData) -> str:
    identity = [
        repository.lower(),
        result.project,
        result.suite.replace("\\", "/"),
        result.file.replace("\\", "/"),
        result.name,
    ]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def get_repository(session: Session, name: str) -> Repository:
    name = name.lower()
    repo = session.scalar(select(Repository).where(Repository.name == name))
    if repo is None:
        repo = Repository(name=name)
        session.add(repo)
        session.flush()
    return repo


def ingest(
    session: Session,
    content: bytes,
    filename: str,
    context: ImportContext,
    settings: Settings | None = None,
) -> ImportResult:
    settings = settings or Settings()
    parsed = parse_report(content, filename, settings.max_report_bytes, settings.max_results)
    digest = hashlib.sha256(content).hexdigest()
    # Caller owns the transaction. Failed imports must be rolled back in their entirety.
    repo = get_repository(session, context.repository)
    run = session.scalar(
        select(Run).where(
            Run.repository_id == repo.id,
            Run.external_id == context.run_id,
            Run.run_attempt == context.run_attempt,
        )
    )
    if run is None:
        date = context.executed_at or parsed.executed_at or utcnow()
        run = Run(
            repository_id=repo.id,
            external_id=context.run_id,
            run_attempt=context.run_attempt,
            branch=context.branch,
            commit_sha=context.commit_sha,
            executed_at=date,
            timestamp_source="provided"
            if context.executed_at
            else "report"
            if parsed.executed_at
            else "ingestion",
            source=context.source,
            provenance=context.provenance,
            ci_url=context.ci_url,
        )
        session.add(run)
        session.flush()
    elif (
        run.branch != context.branch
        or run.commit_sha != context.commit_sha
        or run.provenance != context.provenance
    ):
        raise IngestionConflict(
            "Run identity already exists with different branch, commit, or provenance"
        )
    previous = session.scalar(
        select(ReportImport).where(ReportImport.run_id == run.id, ReportImport.digest == digest)
    )
    if previous:
        return ImportResult(
            run_id=run.id, imported=0, duplicates=len(parsed.results), warnings=previous.warnings
        )
    imported = duplicates = 0
    seen: set[tuple[str, int, str]] = set()
    for result in parsed.results:
        test_id = stable_id(repo.name, result)
        browser = context.browser or result.browser
        environment = context.environment or result.environment
        env_key = hashlib.sha256(json.dumps([browser, environment]).encode()).hexdigest()
        key = (test_id, result.repeat_index, env_key)
        if key in seen:
            raise ReportError(
                "Ambiguous duplicate test identity inside report; parameterize names or split reports into runs"
            )
        seen.add(key)
        existing = session.scalar(
            select(Execution).where(
                Execution.run_id == run.id,
                Execution.test_id == test_id,
                Execution.repeat_index == result.repeat_index,
                Execution.environment_key == env_key,
            )
        )
        status = result.attempts[-1].status if result.attempts else "unknown"
        if existing:
            # Overlapping shards are safe only when their observed results agree.
            signature = [
                (a.status, a.retry_index, a.duration_ms, a.error_message, a.stack_trace)
                for a in existing.attempts
            ]
            incoming = [
                (
                    a.status,
                    a.retry_index,
                    a.duration_ms,
                    redact(a.error_message),
                    redact(a.stack_trace),
                )
                for a in result.attempts
            ]
            if signature != incoming:
                raise IngestionConflict(
                    "Conflicting execution already exists for this run/test/repeat/environment"
                )
            duplicates += 1
            continue
        if session.get(TestCase, test_id) is None:
            session.add(
                TestCase(
                    id=test_id,
                    repository_id=repo.id,
                    project=result.project,
                    suite=result.suite,
                    name=result.name,
                    file=result.file,
                )
            )
            session.flush()
        known = bool(result.attempts) and all(a.retry_index is not None for a in result.attempts)
        first_known = known and result.attempts[0].retry_index == 0
        first_eligible = first_known and result.attempts[0].status in ELIGIBLE_STATUSES
        recovered = status == "passed" and any(
            a.status in FAIL_STATUSES for a in result.attempts[:-1]
        )
        execution = Execution(
            run_id=run.id,
            test_id=test_id,
            repeat_index=result.repeat_index,
            environment_key=env_key,
            browser=browser,
            environment=environment,
            status=status,
            expected_status=result.expected_status,
            duration_ms=sum(a.duration_ms for a in result.attempts if a.duration_ms is not None)
            if result.attempts and all(a.duration_ms is not None for a in result.attempts)
            else None,
            first_attempt_pass=(result.attempts[0].status == "passed") if first_eligible else None,
            retry_recovered=recovered if first_known else None,
            retries=len(result.attempts) - 1 if first_known else None,
        )
        session.add(execution)
        session.flush()
        for ordinal, attempt in enumerate(result.attempts):
            pattern_id = None
            if attempt.status in FAIL_STATUSES:
                pattern_id, normalized = fingerprint(attempt.error_message, attempt.stack_trace)
                if session.get(FailurePattern, pattern_id) is None:
                    session.add(FailurePattern(fingerprint=pattern_id, normalized_text=normalized))
                    session.flush()
            row = Attempt(
                execution_id=execution.id,
                ordinal=ordinal,
                retry_index=attempt.retry_index,
                status=attempt.status,
                duration_ms=attempt.duration_ms,
                started_at=attempt.started_at,
                error_message=redact(attempt.error_message),
                stack_trace=redact(attempt.stack_trace),
                fingerprint=pattern_id,
            )
            session.add(row)
            session.flush()
            for artifact in attempt.artifacts:
                session.add(
                    Artifact(
                        attempt_id=row.id,
                        name=artifact.name,
                        content_type=artifact.content_type,
                        path=redact(artifact.path),
                        url=None,
                    )
                )
        imported += 1
    warnings = list(parsed.warnings)
    if run.timestamp_source == "ingestion":
        warnings.append(
            "Execution time unavailable; ingestion time is explicitly recorded as fallback"
        )
    session.add(
        ReportImport(
            run_id=run.id,
            digest=digest,
            filename=PurePath(filename.replace("\\", "/")).name[:250],
            format=parsed.format,
            warnings=warnings,
        )
    )
    session.flush()
    return ImportResult(run_id=run.id, imported=imported, duplicates=duplicates, warnings=warnings)


def atomic_ingest(
    session: Session,
    content: bytes,
    filename: str,
    context: ImportContext,
    settings: Settings | None = None,
) -> ImportResult:
    try:
        result = ingest(session, content, filename, context, settings)
        session.commit()
        return result
    except IntegrityError as exc:
        session.rollback()
        raise IngestionConflict(
            "Concurrent import conflict; retry the identical import safely"
        ) from exc
    except Exception:
        session.rollback()
        raise
