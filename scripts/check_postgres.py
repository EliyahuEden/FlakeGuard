"""Apply migrations and run PostgreSQL tests without printing local secrets."""

import os
import subprocess
import sys

from sqlalchemy.engine import make_url

from flakeguard.config import get_settings

url = make_url(get_settings().database_url)
if url.drivername != "postgresql+psycopg" or url.host not in {"localhost", "127.0.0.1"}:
    raise SystemExit(
        "Requires a local PostgreSQL DATABASE_URL; never points tests at application data"
    )
test_url = url.set(database="flakeguard_test").render_as_string(hide_password=False)
environment = {**os.environ, "DATABASE_URL": test_url, "FLAKEGUARD_TEST_DATABASE_URL": test_url}
subprocess.run([sys.executable, "-m", "flakeguard.cli", "migrate"], env=environment, check=True)
subprocess.run([sys.executable, "-m", "alembic", "check"], env=environment, check=True)
subprocess.run(
    [
        sys.executable,
        "-m",
        "pytest",
        "--cov=flakeguard",
        "--cov-report=term-missing",
        "--cov-report=json:docs/evidence/coverage.json",
        "--junitxml=docs/evidence/platform-tests.xml",
    ],
    env=environment,
    check=True,
)
