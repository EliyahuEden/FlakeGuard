from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from flakeguard.config import get_settings


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        Path(".runtime").mkdir(exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def foreign_keys(connection: object, _: object) -> None:
            connection.execute("PRAGMA foreign_keys=ON")  # type: ignore[attr-defined]

        return engine
    return create_engine(url, pool_pre_ping=True)


@lru_cache(maxsize=8)
def _factory(url: str) -> sessionmaker[Session]:
    return sessionmaker(make_engine(url), expire_on_commit=False)


def session_factory(url: str | None = None) -> sessionmaker[Session]:
    return _factory(url or get_settings().database_url)


def get_session() -> Iterator[Session]:
    with session_factory()() as session:
        yield session
