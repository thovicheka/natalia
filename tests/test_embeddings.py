"""Tests for embeddings (task 1.5). The database code runs with a fake embedder inside a
rolled-back transaction; one test loads the real model, and skips if it isn't downloaded."""

import numpy as np
import pytest

from natalia import embeddings as em
from natalia.db import EMBEDDING_DIM


class FakeEmbedder:
    """Deterministic unit vectors: texts sharing their first word point the same way."""

    name = "test:fake"
    dim = EMBEDDING_DIM

    def embed(self, texts, kind="passage"):
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            first = text.split()[0].lower() if text.split() else ""
            out[row, sum(map(ord, first)) % self.dim] = 1.0
            out[row, (row * 7 + 3) % self.dim] += 0.1
        return out / np.linalg.norm(out, axis=1, keepdims=True)


def test_passage_text():
    assert em.passage_text("Headline", "Excerpt.", "Body " * 1000).startswith(
        "Headline\nExcerpt. Body"
    )
    assert len(em.passage_text("H", None, "x" * 5000)) == len("H\n") + em.PASSAGE_CHARS
    assert em.passage_text("Only a headline", None, None) == "Only a headline"


def test_model_name():
    assert em.model_name() == "intfloat/multilingual-e5-small:int8"


@pytest.fixture
def test_articles(scratch):
    src = scratch.execute(
        "INSERT INTO sources (name, topic, feed_url) VALUES ('Test Emb', 'science',"
        " 'https://emb.test/feed') RETURNING id"
    ).fetchone()[0]
    ids = []
    for i, title in enumerate(["Zebras migrate early", "Volcano erupts again", "Zebras win cup"]):
        ids.append(
            scratch.execute(
                """INSERT INTO articles (source_id, url, title, title_norm, language)
                   VALUES (%s, %s, %s, %s, 'en') RETURNING id""",
                (src, f"https://emb.test/{i}", title, title.lower()),
            ).fetchone()[0]
        )
    return ids


def test_embed_missing_stores_once_and_search_finds(scratch, test_articles):
    fake = FakeEmbedder()
    logs = []
    n = em.embed_missing(scratch, fake, article_ids=test_articles, log=logs.append)
    assert n == 3 and logs == ["  3/3 embedded"]
    assert em.embed_missing(scratch, fake, article_ids=test_articles, log=logs.append) == 0
    rows = scratch.execute(
        "SELECT model, vector_dims(embedding) FROM embeddings WHERE article_id = ANY(%s)",
        (test_articles,),
    ).fetchall()
    assert rows == [("test:fake", EMBEDDING_DIM)] * 3
    hits = em.search(scratch, fake, "zebras", k=2)
    assert {h[1] for h in hits} == {"Zebras migrate early", "Zebras win cup"}


def test_a_new_model_replaces_the_old_vector(scratch, test_articles):
    class Other(FakeEmbedder):
        name = "test:other"

    em.embed_missing(scratch, FakeEmbedder(), article_ids=test_articles, log=lambda _: None)
    assert em.embed_missing(scratch, Other(), article_ids=test_articles, log=lambda _: None) == 3
    models = scratch.execute(
        "SELECT DISTINCT model FROM embeddings WHERE article_id = ANY(%s)", (test_articles,)
    ).fetchall()
    assert models == [("test:other",)]


@pytest.fixture(scope="module")
def real_model():
    try:
        from huggingface_hub import hf_hub_download

        for f in ("sentencepiece.bpe.model", em.MODEL_FILES["int8"]):
            hf_hub_download(em.MODEL_REPO, f, local_files_only=True)
    except Exception:
        pytest.skip("model not downloaded (uv run python -m natalia.embeddings embed does it)")
    return em.Embedder()


def test_real_model_vectors(real_model):
    passages = [
        "Pakistan school roof collapse kills dozens of pupils",
        "Bitcoin falls after hotter-than-expected US inflation data",
        "ដំរីព្រៃជាន់កុមារស្លាប់នៅខេត្តព្រះវិហារ",  # wild elephants trample a child
    ]
    p = real_model.embed(passages, "passage")
    assert p.shape == (3, EMBEDDING_DIM)
    assert np.allclose(np.linalg.norm(p, axis=1), 1.0, atol=1e-5)
    q = real_model.embed(["school building collapse in Pakistan", "ហ្វូងដំរីព្រៃ"], "query")
    assert int(np.argmax(p @ q[0])) == 0
    assert int(np.argmax(p @ q[1])) == 2
    # XLM-R token ids: <s> … </s>, capped at MAX_TOKENS
    ids = real_model.token_ids("word " * 1000)
    assert ids[0] == em.BOS_ID and ids[-1] == em.EOS_ID and len(ids) == em.MAX_TOKENS
