import json
import os
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from flakeguard.api import create_app
from flakeguard.config import get_settings
from flakeguard.db import get_session, make_engine
from flakeguard.ingestion import atomic_ingest
from flakeguard.models import Base
from flakeguard.schemas import ImportContext


def report(
    statuses: list[str] | None = None,
    *,
    name: str = "cart total",
    message: str = "AssertionError: expected: 10 received: 9",
    retries: bool = True,
    browser: str = "chromium",
) -> bytes:
    statuses = statuses if statuses is not None else ["passed"]
    results = [
        {
            "status": status,
            "duration": 10 + i,
            "errors": [{"message": message, "stack": f"{message}\n at /tmp/tests/cart.ts:22:4"}]
            if status in {"failed", "timedOut"}
            else [],
            **({"retry": i} if retries else {}),
        }
        for i, status in enumerate(statuses)
    ]
    return json.dumps(
        {
            "config": {"projects": [{"name": browser, "use": {"browserName": browser}}]},
            "suites": [
                {
                    "title": "cart",
                    "file": "cart.spec.ts",
                    "specs": [
                        {
                            "title": name,
                            "file": "cart.spec.ts",
                            "tests": [{"projectName": browser, "results": results}],
                        }
                    ],
                }
            ],
            "stats": {"startTime": "2026-10-01T12:00:00Z"},
        }
    ).encode()


@pytest.fixture
def session():
    from sqlalchemy import create_engine, event

    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def fk(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


@pytest.fixture
def client(session, monkeypatch):
    monkeypatch.setenv("FLAKEGUARD_API_KEY", "")
    monkeypatch.setenv("FLAKEGUARD_READ_ONLY", "false")
    get_settings.cache_clear()
    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as http:
        yield http
    get_settings.cache_clear()


@pytest.fixture
def ingest_history(session):
    def populate(statuses: list[list[str]], **kwargs: Any):
        for index, attempts in enumerate(statuses):
            atomic_ingest(
                session,
                report(attempts, **kwargs),
                f"run-{index}.json",
                ImportContext(
                    repository="acme/shop",
                    run_id=f"run-{index}",
                    branch="main",
                    executed_at=datetime(2026, 10, index + 1, tzinfo=UTC),
                ),
            )

    return populate


@pytest.fixture
def postgres_session():
    url = os.environ.get("FLAKEGUARD_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set FLAKEGUARD_TEST_DATABASE_URL to an isolated PostgreSQL test database")
    assert url.startswith("postgresql") and "test" in url.rsplit("/", 1)[-1]
    engine = make_engine(url)
    # Migrations are applied by CI/setup before this test. Each test rolls back its writes.
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(
            connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        ) as db:
            yield db
        transaction.rollback()
    engine.dispose()
