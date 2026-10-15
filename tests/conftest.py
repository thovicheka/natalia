"""Fixtures for tests against the real database (DATABASE_URL). They skip when PostgreSQL isn't
reachable, and never leave data behind: `scratch` is a transaction that is always rolled back."""

import psycopg
import pytest

from natalia import db


@pytest.fixture(scope="module")
def db_url():
    try:
        url = db.database_url()
    except RuntimeError:
        pytest.skip("DATABASE_URL not set")
    try:
        with db.connect(url, connect_timeout=3):
            pass
    except psycopg.OperationalError:
        # The message can name the host but never the password; keep it out anyway.
        pytest.skip("PostgreSQL not reachable at DATABASE_URL (not installed yet?)")
    return url


@pytest.fixture
def conn(db_url):
    with db.connect(db_url) as conn:
        yield conn


@pytest.fixture
def scratch(conn):
    """A transaction that is always rolled back."""
    if db.pending_migrations(conn):
        pytest.fail("pending migrations: run `uv run python -m natalia.db migrate` first")
    with conn.transaction(force_rollback=True):
        yield conn
