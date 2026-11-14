"""Local setup utility; never logs connection URLs or credentials."""

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from flakeguard.config import get_settings

url = make_url(get_settings().database_url)
if url.drivername != "postgresql+psycopg" or url.host not in {"localhost", "127.0.0.1"}:
    raise SystemExit("This helper requires a local PostgreSQL DATABASE_URL")
with psycopg.connect(
    host=url.host,
    port=url.port,
    user=url.username,
    password=url.password,
    dbname="postgres",
    autocommit=True,
) as connection:
    for database in ("flakeguard", "flakeguard_test"):
        if not connection.execute(
            "SELECT 1 FROM pg_database WHERE datname=%s", (database,)
        ).fetchone():
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
print("Local application and isolated test databases are ready.")
