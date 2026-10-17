"""Embeddings: a small multilingual model on CPU, through ONNX Runtime (task 1.5).

    uv run python -m natalia.embeddings embed            # embed articles that have none yet
    uv run python -m natalia.embeddings search "query"   # the 10 nearest articles (any language)

The model is intfloat/multilingual-e5-small (384 dimensions, MIT licence), int8-quantized ONNX
export from its Hugging Face repo, downloaded once into ~/.cache/huggingface. Tokenized with the
repo's SentencePiece file (5 MB, ~63 MB in memory; the same ids as its tokenizer.json, which takes
~290 MB in memory with the `tokenizers` library). e5 wants a prefix:
"query: " for what someone asks, "passage: " for what is stored. Vectors are mean-pooled and
L2-normalized, so cosine distance in pgvector (`<=>`) ranks them.

Why ONNX Runtime and not PyTorch (sentence-transformers): same vectors, a fraction of the memory
and disk (measured in task 1.5, see docs/05-embeddings.md). Nothing is sent anywhere: questions
and articles are embedded on this server.
"""

from __future__ import annotations

import argparse
import os
import time
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import psycopg

from natalia import db

MODEL_REPO = "intfloat/multilingual-e5-small"
MODEL_FILES = {
    "int8": "onnx/model_qint8_avx512_vnni.onnx",
    "fp32": "onnx/model.onnx",
}
DEFAULT_VARIANT = "int8"
MAX_TOKENS = 256  # headline + excerpt + the start of the text; e5 allows 512
BATCH = 8  # texts per model run: 8 peaks ~50 MB lower than 16, same speed (task 1.9b)
PASSAGE_CHARS = 1500  # characters of excerpt + body put after the headline
BOS_ID, PAD_ID, EOS_ID, UNK_ID = 0, 1, 2, 3  # XLM-R's special tokens


def model_name(variant: str = DEFAULT_VARIANT, repo: str = MODEL_REPO) -> str:
    """What `embeddings.model` records, so a change of model or variant is visible."""
    return f"{repo}:{variant}"


def passage_text(title: str, excerpt: str | None = None, body: str | None = None) -> str:
    """The text embedded for an article: headline, then excerpt and the start of the body."""
    rest = " ".join(x.strip() for x in (excerpt, body) if x and x.strip())
    return f"{title.strip()}\n{rest[:PASSAGE_CHARS]}".strip()


def model_file(filename: str, repo: str = MODEL_REPO) -> str:
    """Path of a file from the model repo: the local cache if it's there, else download it."""
    from huggingface_hub import hf_hub_download

    try:
        return hf_hub_download(repo, filename, local_files_only=True)
    except Exception:
        return hf_hub_download(repo, filename)


class Embedder:
    """multilingual-e5-small on ONNX Runtime, CPU only."""

    def __init__(
        self, variant: str = DEFAULT_VARIANT, threads: int | None = None, repo: str = MODEL_REPO
    ):
        import onnxruntime as ort
        import sentencepiece as spm

        self.variant = variant
        self.name = model_name(variant, repo)
        self.sp = spm.SentencePieceProcessor(model_file=model_file("sentencepiece.bpe.model", repo))
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads or min(2, os.cpu_count() or 1)
        opts.inter_op_num_threads = 1
        # The memory arena keeps the largest batch's buffers forever; off keeps RSS flat.
        opts.enable_cpu_mem_arena = False
        self.session = ort.InferenceSession(
            model_file(MODEL_FILES[variant], repo), opts, providers=["CPUExecutionProvider"]
        )
        self.inputs = {i.name for i in self.session.get_inputs()}
        self.dim = self.session.get_outputs()[0].shape[-1]  # 384 for e5-small

    def token_ids(self, text: str) -> list[int]:
        """XLM-R ids: <s> text </s>, SentencePiece ids shifted by one (fairseq), unknown = 3."""
        ids = [i + 1 if i else UNK_ID for i in self.sp.encode(text)][: MAX_TOKENS - 2]
        return [BOS_ID, *ids, EOS_ID]

    def _run(self, texts: Sequence[str]) -> np.ndarray:
        encoded = [self.token_ids(t) for t in texts]
        width = max(len(e) for e in encoded)
        ids = np.full((len(encoded), width), PAD_ID, dtype=np.int64)
        mask = np.zeros((len(encoded), width), dtype=np.int64)
        for row, e in enumerate(encoded):
            ids[row, : len(e)] = e
            mask[row, : len(e)] = 1
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        hidden = self.session.run(None, feed)[0]  # (batch, tokens, 384)
        m = mask[:, :, None].astype(np.float32)
        pooled = (hidden * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)
        return pooled / np.linalg.norm(pooled, axis=1, keepdims=True)

    def embed(self, texts: Sequence[str], kind: str = "passage", batch: int = BATCH) -> np.ndarray:
        """Unit vectors (n, 384) for `texts`; kind is "passage" (stored) or "query" (asked)."""
        if kind not in ("passage", "query"):
            raise ValueError(f"kind must be passage or query, not {kind!r}")
        prefixed = [f"{kind}: {t}" for t in texts]
        # Similar lengths in one batch: less padding, faster.
        order = sorted(range(len(prefixed)), key=lambda i: len(prefixed[i]))
        out = np.zeros((len(prefixed), self.dim), dtype=np.float32)
        for start in range(0, len(order), batch):
            idx = order[start : start + batch]
            out[idx] = self._run([prefixed[i] for i in idx])
        return out


def missing(
    conn: psycopg.Connection,
    model: str,
    limit: int | None = None,
    article_ids: list[int] | None = None,
) -> list[tuple]:
    """(id, title, excerpt, body) of articles without an embedding from `model` (only among
    `article_ids`, if given)."""
    sql = """SELECT a.id, a.title, a.excerpt, left(a.body, %s) FROM articles a
             LEFT JOIN embeddings e ON e.article_id = a.id AND e.model = %s
             WHERE e.article_id IS NULL"""
    params: list = [PASSAGE_CHARS, model]
    if article_ids is not None:
        sql += " AND a.id = ANY(%s)"
        params.append(article_ids)
    sql += " ORDER BY a.id"
    if limit:
        sql += " LIMIT %s"
        params.append(limit)
    return conn.execute(sql, params).fetchall()


def store(conn: psycopg.Connection, rows: list[tuple[int, np.ndarray]], model: str) -> int:
    """Upsert vectors (one per article; a new model replaces the old vector)."""
    with conn.transaction():
        for art_id, vec in rows:
            conn.execute(
                """INSERT INTO embeddings (article_id, model, embedding)
                   VALUES (%s, %s, %s::vector)
                   ON CONFLICT (article_id) DO UPDATE
                   SET model = EXCLUDED.model, embedding = EXCLUDED.embedding,
                       created_at = now()""",
                (art_id, model, db.to_vector(vec)),
            )
    return len(rows)


def embed_missing(
    conn: psycopg.Connection,
    embedder,
    *,
    chunk: int = 256,
    limit: int | None = None,
    article_ids: list[int] | None = None,
    log=print,
) -> int:
    """Embed every article that has no vector from this model yet, `chunk` at a time."""
    todo = missing(conn, embedder.name, limit, article_ids)
    done = 0
    for start in range(0, len(todo), chunk):
        part = todo[start : start + chunk]
        vecs = embedder.embed([passage_text(t, e, b) for _, t, e, b in part], "passage")
        done += store(conn, [(r[0], v) for r, v in zip(part, vecs, strict=True)], embedder.name)
        log(f"  {done}/{len(todo)} embedded")
    return done


def search(conn: psycopg.Connection, embedder, query: str, k: int = 10) -> list[tuple]:
    """(distance, title, url, language) of the k articles nearest to `query`."""
    vec = embedder.embed([query], "query")[0]
    return conn.execute(
        """SELECT e.embedding <=> %s::vector AS d, a.title, a.url, a.language
           FROM embeddings e JOIN articles a ON a.id = e.article_id
           WHERE e.model = %s ORDER BY d LIMIT %s""",
        (db.to_vector(vec), embedder.name, k),
    ).fetchall()


def rss_mb() -> tuple[float, float]:
    """(current, peak) resident memory of this process in MB, from /proc (Linux)."""
    fields = {}
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(("VmRSS:", "VmHWM:")):
            key, value = line.split(":")
            fields[key] = int(value.split()[0]) / 1024
    return fields.get("VmRSS", 0.0), fields.get("VmHWM", 0.0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    emb = sub.add_parser("embed", help="embed articles that have no vector yet")
    emb.add_argument("--limit", type=int)
    srch = sub.add_parser("search", help="nearest articles to a query")
    srch.add_argument("query")
    srch.add_argument("-k", type=int, default=10)
    for p in (emb, srch):
        p.add_argument("--variant", choices=sorted(MODEL_FILES), default=DEFAULT_VARIANT)
    args = parser.parse_args(argv)

    try:
        conn = db.connect(autocommit=True)
    except (RuntimeError, psycopg.OperationalError) as e:
        print(f"cannot connect: {e}".strip())
        return 1
    start = time.monotonic()
    embedder = Embedder(args.variant)
    print(f"model {embedder.name} loaded in {time.monotonic() - start:.1f} s")
    with conn:
        if args.command == "embed":
            t0 = time.monotonic()
            n = embed_missing(conn, embedder, limit=args.limit)
            secs = time.monotonic() - t0
            rate = f", {secs / n * 100:.1f} s per 100 articles" if n else ""
            print(f"embedded {n} articles in {secs:.0f} s{rate}")
        else:
            for d, title, url, lang in search(conn, embedder, args.query, args.k):
                print(f"{1 - d:.3f} [{lang}] {title[:100]}\n      {url}")
    now, peak = rss_mb()
    print(f"memory: {now:.0f} MB now, {peak:.0f} MB peak")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
