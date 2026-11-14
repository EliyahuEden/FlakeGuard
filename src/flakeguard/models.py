from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Repository(Base):
    __tablename__ = "repositories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    github_enabled: Mapped[bool] = mapped_column(default=False)


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (UniqueConstraint("repository_id", "external_id", "run_attempt"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(250))
    run_attempt: Mapped[int] = mapped_column(default=1)
    branch: Mapped[str] = mapped_column(String(250), index=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(30))
    provenance: Mapped[str] = mapped_column(String(30))
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    timestamp_source: Mapped[str] = mapped_column(String(30))
    ci_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    repository: Mapped[Repository] = relationship(lazy="joined")


class ReportImport(Base):
    __tablename__ = "report_imports"
    __table_args__ = (UniqueConstraint("run_id", "digest"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    digest: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(250))
    format: Mapped[str] = mapped_column(String(30))
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TestCase(Base):
    __tablename__ = "test_cases"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    project: Mapped[str] = mapped_column(String(250))
    suite: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    file: Mapped[str] = mapped_column(Text)


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint("run_id", "test_id", "repeat_index", "environment_key"),
        Index("ix_execution_test_run", "test_id", "run_id"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), index=True)
    test_id: Mapped[str] = mapped_column(ForeignKey("test_cases.id"), index=True)
    repeat_index: Mapped[int] = mapped_column(default=0)
    browser: Mapped[str | None] = mapped_column(String(100))
    environment: Mapped[str | None] = mapped_column(String(250))
    environment_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(30), index=True)
    expected_status: Mapped[str | None] = mapped_column(String(30))
    duration_ms: Mapped[float | None] = mapped_column(Float)
    first_attempt_pass: Mapped[bool | None]
    retry_recovered: Mapped[bool | None]
    retries: Mapped[int | None]
    test: Mapped[TestCase] = relationship(lazy="joined")
    run: Mapped[Run] = relationship(lazy="joined")
    attempts: Mapped[list["Attempt"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", order_by="Attempt.ordinal"
    )


class FailurePattern(Base):
    __tablename__ = "failure_patterns"
    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    normalized_text: Mapped[str] = mapped_column(Text)
    algorithm: Mapped[str] = mapped_column(String(50), default="normalize-v1")


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (UniqueConstraint("execution_id", "ordinal"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("executions.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    retry_index: Mapped[int | None]
    status: Mapped[str] = mapped_column(String(30))
    duration_ms: Mapped[float | None] = mapped_column(Float)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    stack_trace: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str | None] = mapped_column(
        ForeignKey("failure_patterns.fingerprint"), index=True
    )
    artifacts: Mapped[list["Artifact"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempts.id"), index=True)
    name: Mapped[str] = mapped_column(String(250))
    content_type: Mapped[str | None] = mapped_column(String(250))
    path: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    # Only metadata is persisted; never arbitrary attachment bodies.


class SyncState(Base):
    __tablename__ = "sync_states"
    __table_args__ = (UniqueConstraint("repository_id", "external_id", "run_attempt"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(250))
    run_attempt: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(30))
    detail: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class IngestionError(Base):
    __tablename__ = "ingestion_errors"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(250))
    detail: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
