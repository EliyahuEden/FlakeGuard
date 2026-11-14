"""Versioned deterministic text patterns are investigation groups, not root causes."""

import hashlib
import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from typing import Any

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def redact(text: str | None) -> str | None:
    if text is None:
        return None
    text = re.sub(
        r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?|(?:token|password|secret|api[_-]?key)\s*[:=]\s*)[^\s,;]+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b", "[REDACTED]", text)
    text = re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", text)
    return text[:32_000]


def normalize(message: str | None, stack: str | None = None) -> str:
    text = ANSI.sub("", redact(message or stack or "Failure without diagnostic text") or "")
    # Keep assertion values, selectors, HTTP status codes, and error types meaningful.
    text = re.sub(r"\b\d{4}-\d\d-\d\d[T ][\d:.]+Z?\b", "<timestamp>", text)
    text = re.sub(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
        "<uuid>",
        text,
        flags=re.I,
    )
    text = re.sub(r"\b0x[0-9a-f]+\b", "<address>", text, flags=re.I)
    text = re.sub(
        r"(?i)(?:[A-Z]:[\\/]|/)(?:[^\s:]+[\\/])*[^\s:]+\.(?:ts|js|py):\d+(?::\d+)?",
        "<location>",
        text,
    )
    text = re.sub(r"(?i)(?:/tmp/|[A-Z]:\\[^\n]*?\\Temp\\)[^\s]+", "<temp-path>", text)
    text = re.sub(r"(?i)\b(request[_ -]?id|trace[_ -]?id)[:= ]+[\w-]+", r"\1=<id>", text)
    text = "\n".join(line for line in text.splitlines() if not line.strip().startswith("at "))
    return re.sub(r"\s+", " ", text).strip().lower()[:8000]


def fingerprint(message: str | None, stack: str | None = None) -> tuple[str, str]:
    normalized = normalize(message, stack)
    return hashlib.sha256(("normalize-v1\0" + normalized).encode()).hexdigest(), normalized


@dataclass
class Classification:
    category: str
    evidence_strength: str
    signals: list[str]
    explanation: str
    investigation_steps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify(
    text: str,
    *,
    recovered: bool = False,
    affected_tests: int = 1,
    cofailure_ratio: float = 0,
    consecutive_failures: int = 0,
) -> Classification:
    text = text.lower()
    signals: list[str] = []
    category, strength = "unknown", "low"
    steps = ["Inspect the original diagnostics and reproduce on the same commit and environment."]
    if any(
        k in text
        for k in [
            "econnrefused",
            "connection refused",
            "enotfound",
            "dns resolution",
            "browser has been closed",
            "browser crashed",
            "out of memory",
            "no space left",
            "service unavailable",
        ]
    ):
        category, strength = "suspected_infrastructure", "moderate"
        signals.append("Explicit transport, resource, or browser-process failure")
        steps = [
            "Check service readiness, worker resources, DNS, and browser process logs.",
            "Compare unrelated tests in the same run before attributing an application defect.",
        ]
    elif any(
        k in text
        for k in [
            "strict mode violation",
            "fixture teardown",
            "fixture setup",
            "shared state",
            "test isolation",
            "locator resolved to",
            "setup failed",
        ]
    ):
        category, strength = "suspected_automation", "moderate"
        signals.append("Fixture, locator ambiguity, or test isolation diagnostic")
        steps = [
            "Run the test alone and in its original order.",
            "Inspect fixture cleanup, selectors, and shared mutable state.",
        ]
    elif any(
        k in text
        for k in ["assertionerror", "toequal", "tobe(", "expected:", "assert ", "assertion failed"]
    ):
        category = "suspected_application"
        signals.append("An assertion compared observed behavior with an expectation")
        strength = "moderate" if consecutive_failures >= 3 else "low"
        steps = [
            "Validate the assertion and test data against the product contract.",
            "Reproduce on the failing commit and compare the last passing commit.",
        ]
    elif "timeout" in text or "timed out" in text:
        signals.append("Timeout alone is ambiguous between product, test, and infrastructure")
        steps = ["Inspect traces, readiness checks, network timings, and application logs."]
    if recovered:
        signals.append("Observed failure followed by a passing retry in the same execution")
        if category in {"unknown", "suspected_application"}:
            category, strength = "suspected_automation", "low"
        steps.append(
            "Compare retry traces; recovery is evidence of intermittency, not a harmless failure."
        )
    if affected_tests >= 3 and cofailure_ratio >= 0.5:
        signals.append(
            "At least three tests and half the eligible executions share this pattern in a run"
        )
        steps.append("Investigate shared dependencies and setup before individual tests.")
    if consecutive_failures >= 3:
        signals.append("At least three consecutive final failures in one test history")
    return Classification(
        category,
        strength,
        signals,
        "Heuristic investigation suggestion; neither text similarity nor retry recovery establishes root cause.",
        steps,
    )


def related_patterns(patterns: dict[str, str], threshold: float = 0.85) -> list[dict[str, Any]]:
    # Bounded optional suggestions. Never merge exact fingerprint groups by similarity.
    keys = sorted(patterns)[:200]
    return [
        {"left": left, "right": right, "similarity": round(score, 3)}
        for i, left in enumerate(keys)
        for right in keys[i + 1 :]
        if (score := SequenceMatcher(None, patterns[left], patterns[right]).ratio()) >= threshold
    ]
