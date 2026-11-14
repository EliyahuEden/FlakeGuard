"""Strict report boundaries, tolerant optional metadata, no invented retries."""

import json
import math
import re
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from pydantic import ValidationError

from flakeguard.schemas import AttachmentData, AttemptData, ParsedReport, ResultData, Status


class ReportError(ValueError):
    pass


def timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        # Many JUnit producers omit zones. Unknown is more honest than guessing UTC.
        return parsed.astimezone(UTC) if parsed.tzinfo else None
    except ValueError:
        return None


def duration(value: Any, multiplier: int = 1) -> float | None:
    if value is None:
        return None
    number = float(value) * multiplier
    if not math.isfinite(number) or number < 0:
        raise ReportError("Duration must be a finite nonnegative number")
    return number


def relative_file(value: Any, root: str = "") -> str:
    path = str(value or "").replace("\\", "/")
    root = root.replace("\\", "/").rstrip("/")
    if root and path.startswith(root + "/"):
        path = path[len(root) + 1 :]
    # Absolute machine-specific paths are not stable identities.
    if path.startswith("/") or re.match(r"^[A-Za-z]:/", path):
        raise ReportError("Absolute test file requires config.rootDir for a stable identity")
    if ".." in PurePosixPath(path).parts:
        raise ReportError("Test file must not traverse parent directories")
    return path


def playwright(data: dict[str, Any]) -> ParsedReport:
    if not isinstance(data.get("suites"), list):
        raise ReportError("Playwright report requires a suites array")
    config = data.get("config", {})
    root = str(config.get("rootDir", ""))
    projects = {p.get("name", ""): p for p in config.get("projects", [])}
    results: list[ResultData] = []
    warnings: list[str] = []

    def walk(suites: list[Any], parents: list[str]) -> None:
        for suite in suites:
            title = str(suite.get("title", ""))
            chain = [*parents, title] if title else parents
            for spec in suite.get("specs", []):
                if not spec.get("title") or not isinstance(spec.get("tests"), list):
                    raise ReportError("Every Playwright spec needs a title and tests array")
                for test in spec["tests"]:
                    project = str(test.get("projectName", test.get("projectId", "default")))
                    project_data = projects.get(project, {})
                    # Project names such as 'mobile-chromium' are not browser evidence.
                    browser = project_data.get("use", {}).get("browserName")
                    environment = project_data.get("metadata", {}).get("environment")
                    attempts: list[AttemptData] = []
                    previous_retry = -1
                    for result in test.get("results", []):
                        status = result.get("status", "unknown")
                        if status not in {"passed", "failed", "timedOut", "skipped", "interrupted"}:
                            status = "unknown"
                            warnings.append("Unrecognized Playwright status recorded as unknown")
                        retry = result.get("retry")
                        if retry is not None:
                            if not isinstance(retry, int) or retry <= previous_retry:
                                raise ReportError(
                                    "Retry indices must be increasing nonnegative integers"
                                )
                            previous_retry = retry
                        errors = result.get("errors", [])
                        if not errors and result.get("error"):
                            errors = [result["error"]]
                        messages = [
                            str(e.get("message", "")) for e in errors if isinstance(e, dict)
                        ]
                        stacks = [str(e.get("stack", "")) for e in errors if isinstance(e, dict)]
                        attachments = [
                            AttachmentData(
                                name=str(a.get("name", "attachment"))[:250],
                                content_type=a.get("contentType"),
                                path=a.get("path"),
                            )
                            for a in result.get("attachments", [])
                        ]
                        attempts.append(
                            AttemptData(
                                status=status,
                                retry_index=retry,
                                duration_ms=duration(result.get("duration")),
                                started_at=timestamp(result.get("startTime")),
                                error_message="\n".join(messages) or None,
                                stack_trace="\n".join(stacks) or None,
                                artifacts=attachments,
                            )
                        )
                    results.append(
                        ResultData(
                            project=project,
                            suite=" > ".join(chain),
                            name=str(spec["title"]),
                            file=relative_file(spec.get("file", suite.get("file", "")), root),
                            repeat_index=test.get("repeatEachIndex", 0),
                            browser=browser,
                            environment=environment,
                            expected_status=test.get("expectedStatus"),
                            attempts=attempts,
                        )
                    )
            walk(suite.get("suites", []), chain)

    walk(data["suites"], [])
    if data.get("errors"):
        warnings.append(
            "Report contains global errors; inspect the original report for incomplete discovery"
        )
    return ParsedReport(
        format="playwright",
        results=results,
        warnings=warnings,
        executed_at=timestamp(data.get("stats", {}).get("startTime")),
    )


def junit(content: bytes) -> ParsedReport:
    root = ElementTree.fromstring(content)
    if root.tag not in {"testsuites", "testsuite"}:
        raise ReportError("JUnit root must be testsuites or testsuite")
    results: list[ResultData] = []
    dates: list[datetime] = []
    warnings: list[str] = []

    def walk(suite: Any, parents: list[str]) -> None:
        name = suite.get("name", "")
        chain = [*parents, name] if name else parents
        date = timestamp(suite.get("timestamp"))
        if date:
            dates.append(date)
        props = {p.get("name"): p.get("value") for p in suite.findall("./properties/property")}
        for case in suite.findall("testcase"):
            if not case.get("name"):
                raise ReportError("JUnit testcase requires a name")
            failure = case.find("failure")
            error = case.find("error")
            problem = failure if failure is not None else error
            status: Status = "failed" if problem is not None else "passed"
            if case.find("skipped") is not None:
                status = "skipped"
            if case.findall("flakyFailure") or case.findall("rerunFailure"):
                warnings.append(
                    "JUnit retry extensions present: final result imported, retry semantics unsupported"
                )
            attempts = [
                AttemptData(
                    status=status,
                    duration_ms=duration(case.get("time"), 1000),
                    error_message=problem.get("message") if problem is not None else None,
                    stack_trace=problem.text if problem is not None else None,
                )
            ]
            results.append(
                ResultData(
                    project=str(props.get("project") or "junit"),
                    suite=" > ".join([*chain, case.get("classname", "")]).rstrip(" >"),
                    name=case.get("name"),
                    file=relative_file(case.get("file", "")),
                    browser=props.get("browser"),
                    environment=props.get("environment"),
                    attempts=attempts,
                )
            )
        for child in suite.findall("testsuite"):
            walk(child, chain)

    walk(root, [])
    return ParsedReport(
        format="junit",
        results=results,
        warnings=sorted(set(warnings)),
        executed_at=min(dates) if dates else None,
    )


def parse_report(
    content: bytes, filename: str, max_bytes: int = 20 * 1024 * 1024, max_results: int = 100_000
) -> ParsedReport:
    if len(content) > max_bytes:
        raise ReportError("Report exceeds configured byte limit")
    if not content.strip():
        raise ReportError("Report is empty")
    try:
        if filename.lower().endswith(".xml"):
            parsed = junit(content)
        elif filename.lower().endswith(".json"):
            data = json.loads(content)
            if not isinstance(data, dict):
                raise ReportError("JSON report must be an object")
            parsed = playwright(data)
        else:
            raise ReportError("Supported report extensions: .json (Playwright), .xml (JUnit)")
    except ReportError:
        raise
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        DefusedXmlException,
        ElementTree.ParseError,
        ValidationError,
        RecursionError,
    ) as exc:
        raise ReportError("Malformed report: invalid structure or values") from exc
    if len(parsed.results) > max_results:
        raise ReportError("Report exceeds configured result count limit")
    return parsed
