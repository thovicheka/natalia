"""Database tests.

The first group needs no database. The second runs against the real one from DATABASE_URL and
is skipped when PostgreSQL isn't reachable (before the human installs it, task 1.2). It never
leaves data behind: every write happens in a transaction that is rolled back.
"""

import re

import psycopg
import pytest

from natalia import db, feeds

SCHEMA = (db.MIGRATIONS_DIR / "0001_initial_schema.sql").read_text()


# --- no database needed -------------------------------------------------------------------


def test_migration_files_are_numbered():
    files = db.migration_files()
    assert files, "no migrations found"
    assert files[0].name == "0001_initial_schema.sql"


def test_migration_files_reject_bad_names(tmp_path):
    (tmp_path / "0001_ok.sql").write_text("SELECT 1;")
    (tmp_path / "init.sql").write_text("SELECT 1;")
    with pytest.raises(ValueError, match="NNNN_"):
        db.migration_files(tmp_path)


def test_migration_files_reject_duplicate_numbers(tmp_path):
    (tmp_path / "0001_a.sql").write_text("SELECT 1;")
    (tmp_path / "0001_b.sql").write_text("SELECT 1;")
    with pytest.raises(ValueError, match="duplicate"):
        db.migration_files(tmp_path)


def test_schema_topics_match_feed_topics():
    domain = re.search(r"CREATE DOMAIN topic AS text CHECK \(VALUE IN \((.*?)\)\);", SCHEMA, re.S)
    assert domain
    assert tuple(re.findall(r"'([^']+)'", domain.group(1))) == feeds.TOPICS


def test_schema_languages_match_feed_languages():
    domain = re.search(r"CREATE DOMAIN lang AS text CHECK \(VALUE IN \((.*?)\)\);", SCHEMA)
    assert domain
    assert tuple(re.findall(r"'([^']+)'", domain.group(1))) == feeds.LANGUAGES


def test_schema_vector_size_matches_embedding_dim():
    assert f"vector({db.EMBEDDING_DIM})" in SCHEMA
    assert "CREATE EXTENSION IF NOT EXISTS vector" in SCHEMA


def test_database_url_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/x")
    assert db.database_url(tmp_path / "missing.env") == "postgresql://u:p@127.0.0.1:5432/x"


def test_database_url_from_env_file(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.delenv("DATABASE_URL")
    env = tmp_path / ".env"
    env.write_text("DATABASE_URL=postgresql://u:p@127.0.0.1:5432/fromfile\n")
    assert db.database_url(env) == "postgresql://u:p@127.0.0.1:5432/fromfile"


def test_database_url_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "")
    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        db.database_url(tmp_path / "missing.env")


def test_to_vector():
    vec = db.to_vector([0.5] * db.EMBEDDING_DIM)
    assert vec.startswith("[0.5,0.5,") and vec.endswith("]")
    assert vec.count(",") == db.EMBEDDING_DIM - 1
    with pytest.raises(ValueError, match="384"):
        db.to_vector([1.0, 2.0])


# --- against the real database --------------------------------------------------------------


# Fixtures db_url, conn and scratch are in conftest.py.


def test_migrations_applied_and_pgvector_present(conn):
    info = db.status(conn)
    assert info["server"].startswith("16"), info["server"]
    assert info["pgvector"], "the vector extension is not created in this database"
    assert info["pending"] == [], "run `uv run python -m natalia.db migrate`"
    assert db.migrate(conn) == []  # applying again does nothing


def _vec(*head: float) -> str:
    return db.to_vector(list(head) + [0.0] * (db.EMBEDDING_DIM - len(head)))


def test_round_trip_and_nearest_neighbours(scratch):
    c = scratch
    (source_id,) = c.execute(
        "INSERT INTO sources (name, topic, feed_url) VALUES ('Test', 'cambodia', %s) RETURNING id",
        ("https://example.test/feed",),
    ).fetchone()
    ids = []
    for i, (title, head) in enumerate(
        [("Rice exports rise", (1.0, 0.0)), ("Football final", (0.0, 1.0))]
    ):
        (article_id,) = c.execute(
            """INSERT INTO articles (source_id, url, title, title_norm, language, topics)
               VALUES (%s, %s, %s, %s, 'en', %s::topic[]) RETURNING id""",
            (source_id, f"https://example.test/{i}", title, title.lower(), ["cambodia"]),
        ).fetchone()
        c.execute(
            "INSERT INTO embeddings (article_id, model, embedding) VALUES (%s, 'test', %s::vector)",
            (article_id, _vec(*head)),
        )
        ids.append(article_id)

    nearest = c.execute(
        "SELECT article_id FROM embeddings ORDER BY embedding <=> %s::vector LIMIT 1",
        (_vec(0.9, 0.1),),
    ).fetchone()[0]
    assert nearest == ids[0]

    c.execute(
        """INSERT INTO summaries (article_id, language, summary, why_it_matters, model)
           VALUES (%s, 'km', 'សង្ខេប', 'ហេតុអ្វីសំខាន់', 'test')""",
        (ids[0],),
    )
    (digest_id,) = c.execute(
        "INSERT INTO digests (digest_date) VALUES ('2026-10-15') RETURNING id"
    ).fetchone()
    c.execute(
        "INSERT INTO digest_items (digest_id, topic, position, article_id)"
        " VALUES (%s, 'cambodia', 1, %s)",
        (digest_id, ids[0]),
    )
    row = c.execute(
        """SELECT a.title, s.summary FROM digest_items d
           JOIN articles a ON a.id = d.article_id
           JOIN summaries s ON s.article_id = a.id
           WHERE d.digest_id = %s""",
        (digest_id,),
    ).fetchone()
    assert row == ("Rice exports rise", "សង្ខេប")


def test_constraints(scratch):
    c = scratch
    (source_id,) = c.execute(
        "INSERT INTO sources (name, topic, feed_url) VALUES ('T', 'sport', 'https://e.test/f')"
        " RETURNING id"
    ).fetchone()
    insert_article = (
        "INSERT INTO articles (source_id, url, title, title_norm, language, topics)"
        " VALUES (%s, %s, 't', 't', %s, %s::topic[]) RETURNING id"
    )
    (article_id,) = c.execute(insert_article, (source_id, "https://e.test/1", "en", [])).fetchone()

    with pytest.raises(psycopg.errors.UniqueViolation), c.transaction():
        c.execute(insert_article, (source_id, "https://e.test/1", "en", []))
    with pytest.raises(psycopg.errors.CheckViolation), c.transaction():
        c.execute(insert_article, (source_id, "https://e.test/2", "en", ["weather"]))
    with pytest.raises(psycopg.errors.CheckViolation), c.transaction():
        c.execute(insert_article, (source_id, "https://e.test/3", "fr", []))
    with pytest.raises(psycopg.DataError), c.transaction():
        c.execute(
            "INSERT INTO embeddings (article_id, model, embedding) VALUES (%s, 't', '[1,2,3]')",
            (article_id,),
        )
