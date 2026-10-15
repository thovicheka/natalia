"""The database: connection from DATABASE_URL, and a small migration runner.

    uv run python -m natalia.db status     # versions of PostgreSQL and pgvector; migrations
    uv run python -m natalia.db migrate    # apply pending migrations/NNNN_*.sql, in order

DATABASE_URL comes from the environment, or from the repo's `.env` (git-ignored) when it isn't
set there. It holds the role's password, so it is never printed or logged.

Migrations are plain SQL files in `migrations/`, named `NNNN_<what>.sql`. Each pending file runs
in its own transaction and is recorded in `schema_migrations`; applied files are never edited,
changes go in a new file.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Iterable
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
MIGRATIONS_DIR = ROOT / "migrations"

EMBEDDING_DIM = 384  # intfloat/multilingual-e5-small; must match vector(384) in the schema
CONNECT_TIMEOUT_S = 5
# Any constant works; it keeps two `migrate` runs from applying the same file at once.
MIGRATE_LOCK_ID = 0x6E61_7461  # "nata"


def database_url(env_file: Path = ENV_FILE) -> str:
    """DATABASE_URL from the environment, else from `.env`. Raises if neither has it."""
    load_dotenv(env_file, override=False)
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(f"DATABASE_URL is not set (environment or {env_file})")
    return url


def connect(url: str | None = None, **kwargs) -> psycopg.Connection:
    """Open a connection to Natalia's database. Use it as a context manager."""
    kwargs.setdefault("connect_timeout", CONNECT_TIMEOUT_S)
    return psycopg.connect(url or database_url(), **kwargs)


def to_vector(values: Iterable[float]) -> str:
    """Format an embedding as a pgvector literal, for use as `%s::vector` in a query."""
    values = list(values)
    if len(values) != EMBEDDING_DIM:
        raise ValueError(f"expected {EMBEDDING_DIM} dimensions, got {len(values)}")
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


def migration_files(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    """The migration files, in the order they apply."""
    files = sorted(directory.glob("*.sql"))
    for f in files:
        prefix = f.stem.split("_", 1)[0]
        if len(prefix) != 4 or not prefix.isdigit():
            raise ValueError(f"migration file must be named NNNN_<what>.sql: {f.name}")
    prefixes = [f.stem[:4] for f in files]
    dupes = {p for p in prefixes if prefixes.count(p) > 1}
    if dupes:
        raise ValueError(f"duplicate migration numbers: {sorted(dupes)}")
    return files


def _ensure_migrations_table(conn: psycopg.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
               version     text        PRIMARY KEY,
               applied_at  timestamptz NOT NULL DEFAULT now()
           )"""
    )


def applied_migrations(conn: psycopg.Connection) -> set[str]:
    _ensure_migrations_table(conn)
    return {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}


def pending_migrations(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[Path]:
    done = applied_migrations(conn)
    return [f for f in migration_files(directory) if f.stem not in done]


def migrate(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations, each in its own transaction. Returns the versions applied."""
    applied = []
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATE_LOCK_ID,))
        pending = pending_migrations(conn, directory)
    for f in pending:
        with conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (MIGRATE_LOCK_ID,))
            if f.stem in applied_migrations(conn):  # another run got there first
                continue
            # No parameters: psycopg sends it as one simple query, so a file may hold
            # several statements.
            conn.execute(f.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (f.stem,))
        applied.append(f.stem)
    return applied


def status(conn: psycopg.Connection) -> dict:
    server = conn.execute("SHOW server_version").fetchone()[0]
    row = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()
    with conn.transaction():
        done = sorted(applied_migrations(conn))
        pending = [f.stem for f in pending_migrations(conn)]
    return {
        "server": server,
        "pgvector": row[0] if row else None,
        "applied": done,
        "pending": pending,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["status", "migrate"])
    args = parser.parse_args(argv)

    try:
        conn = connect()
    except (RuntimeError, psycopg.OperationalError) as e:
        # psycopg's message names the host and port, never the password.
        print(f"cannot connect: {e}".strip())
        return 1
    with conn:
        if args.command == "migrate":
            applied = migrate(conn)
            print("applied: " + ", ".join(applied) if applied else "nothing to apply")
        info = status(conn)
    print(f"PostgreSQL {info['server']}, pgvector {info['pgvector'] or 'not installed'}")
    print(f"applied migrations: {', '.join(info['applied']) or 'none'}")
    print(f"pending migrations: {', '.join(info['pending']) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
