from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

Status = Literal["passed", "failed", "timedOut", "skipped", "interrupted", "unknown"]
Provenance = Literal["real", "injected", "synthetic"]


class ImportContext(BaseModel):
    repository: str = Field(min_length=1, max_length=200, pattern=r"^[\w./-]+$")
    run_id: str = Field(min_length=1, max_length=250)
    branch: str = Field(default="unknown", min_length=1, max_length=250)
    commit_sha: str | None = Field(default=None, max_length=64)
    run_attempt: int = Field(default=1, ge=1)
    executed_at: datetime | None = None
    environment: str | None = Field(default=None, max_length=250)
    browser: str | None = Field(default=None, max_length=100)
    source: Literal["local", "github", "demo"] = "local"
    provenance: Provenance = "real"
    ci_url: str | None = None

    @field_validator("executed_at")
    @classmethod
    def aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("executed_at must contain a timezone")
        return value

    @field_validator("ci_url")
    @classmethod
    def safe_ci_url(cls, value: str | None) -> str | None:
        if value is not None:
            parsed = urlparse(value)
            if (
                parsed.scheme != "https"
                or parsed.hostname != "github.com"
                or parsed.username
                or parsed.port not in {None, 443}
                or parsed.query
                or any(c.isspace() for c in value)
            ):
                raise ValueError("ci_url must be an HTTPS github.com URL")
        return value


class AttachmentData(BaseModel):
    name: str
    content_type: str | None = None
    path: str | None = None
    url: str | None = None


class AttemptData(BaseModel):
    status: Status
    retry_index: int | None = Field(default=None, ge=0)
    duration_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    started_at: datetime | None = None
    error_message: str | None = None
    stack_trace: str | None = None
    artifacts: list[AttachmentData] = Field(default_factory=list)


class ResultData(BaseModel):
    project: str
    suite: str
    name: str
    file: str = ""
    repeat_index: int = Field(default=0, ge=0)
    browser: str | None = None
    environment: str | None = None
    expected_status: str | None = None
    attempts: list[AttemptData]


class ParsedReport(BaseModel):
    format: str
    results: list[ResultData]
    executed_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)


class ImportResult(BaseModel):
    run_id: int
    imported: int
    duplicates: int
    warnings: list[str]


class RepositoryConfig(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", max_length=200)
    github_enabled: bool = True


class SyncRequest(BaseModel):
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    max_runs: int = Field(default=20, ge=1, le=100)
    artifact_pattern: str = Field(default="*", max_length=100)


class RunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    external_id: str
    run_attempt: int
    branch: str
    commit_sha: str | None
    executed_at: datetime
    provenance: str
    source: str
    timestamp_source: str
    ci_url: str | None


class Metrics(BaseModel):
    total_executions: int
    eligible_executions: int
    passed: int
    failed: int
    skipped: int
    excluded: int
    pass_rate: float | None
    failure_rate: float | None
    first_attempt_observations: int
    first_attempt_pass_rate: float | None
    known_retry_observations: int
    initially_failed_with_retries: int
    retry_recoveries: int
    retry_recovery_rate: float | None
    average_duration_ms: float | None
    suspected_flaky_tests: int
