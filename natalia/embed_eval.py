"""Evaluate an embedding model on Natalia's real articles (task 1.5).

    uv run python -m natalia.embed_eval                   # ONNX int8 (the production setup)
    uv run python -m natalia.embed_eval --variant fp32    # ONNX full precision
    uv run python -m natalia.embed_eval --show-relevant   # print what each query counts as right

The labeled queries are in config/embedding-eval.yaml. For each query: rank every article of the
frozen corpus by cosine similarity, then report hit@1, hit@5 (a right article in the first 1 / 5)
and MRR (1 / rank of the first right article), per set (en-en, km-en, km-km, en-km). Also memory
and speed. scripts/bench_embeddings.py runs the same evaluation for PyTorch.
"""

from __future__ import annotations

import argparse
import re
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

from natalia import db
from natalia.embeddings import passage_text, rss_mb
from natalia.topics import clean_text

EVAL_FILE = Path(__file__).resolve().parent.parent / "config" / "embedding-eval.yaml"
SETS = ("en-en", "km-en", "km-km", "en-km")


@dataclass
class Query:
    q: str
    set: str
    patterns: list[re.Pattern]
    relevant: set[int] = field(default_factory=set)


def load_eval(path: Path = EVAL_FILE) -> tuple[datetime, list[Query]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    until = datetime.fromisoformat(data["corpus_until"].replace("Z", "+00:00"))
    queries = [
        Query(row["q"], row["set"], [re.compile(p, re.I) for p in row["relevant"]])
        for row in data["queries"]
    ]
    for q in queries:
        if q.set not in SETS:
            raise ValueError(f"unknown set {q.set!r} for query {q.q!r}")
    return until, queries


def load_corpus(conn, until: datetime) -> list[tuple[int, str, str, str]]:
    """(id, title, language, passage text) of the articles collected before `until`."""
    rows = conn.execute(
        "SELECT id, title, language, excerpt, left(body, 2000) FROM articles"
        " WHERE collected_at < %s ORDER BY id",
        (until,),
    ).fetchall()
    return [(i, t, lang, passage_text(t, e, b)) for i, t, lang, e, b in rows]


def resolve(queries: list[Query], corpus: list[tuple[int, str, str, str]]) -> None:
    """Fill each query's relevant ids from its headline patterns. Raises if one has none."""
    for q in queries:
        q.relevant = {
            i for i, title, _, _ in corpus if any(p.search(clean_text(title)) for p in q.patterns)
        }
        if not q.relevant:
            raise ValueError(f"no article in the corpus matches query {q.q!r}")


def rank_of_first_hit(scores: np.ndarray, ids: np.ndarray, relevant: set[int]) -> int:
    """1-based rank of the best-scored relevant article."""
    order = np.argsort(-scores)
    for rank, idx in enumerate(order, 1):
        if int(ids[idx]) in relevant:
            return rank
    return len(order) + 1


def evaluate(
    embed: Callable[[list[str], str], np.ndarray],
    queries: list[Query],
    corpus: list[tuple[int, str, str, str]],
) -> dict:
    """Embed corpus and queries with `embed(texts, kind)`; return metrics and timings."""
    ids = np.array([c[0] for c in corpus])
    t0 = time.monotonic()
    passages = embed([c[3] for c in corpus], "passage")
    t_passages = time.monotonic() - t0
    t0 = time.monotonic()
    qvecs = embed([q.q for q in queries], "query")
    t_queries = time.monotonic() - t0
    per_set: dict[str, list[int]] = defaultdict(list)
    ranks = []
    for q, v in zip(queries, qvecs, strict=True):
        r = rank_of_first_hit(passages @ v, ids, q.relevant)
        per_set[q.set].append(r)
        ranks.append((q, r))
    metrics = {}
    for name in [*SETS, "all"]:
        rs = [r for _, r in ranks] if name == "all" else per_set.get(name, [])
        if rs:
            metrics[name] = {
                "n": len(rs),
                "hit@1": sum(r == 1 for r in rs) / len(rs),
                "hit@5": sum(r <= 5 for r in rs) / len(rs),
                "mrr": sum(1 / r for r in rs) / len(rs),
            }
    return {
        "metrics": metrics,
        "ranks": ranks,
        "passages": len(corpus),
        "s_per_100": t_passages / len(corpus) * 100,
        "s_per_query": t_queries / len(queries),
        "vectors": passages,
    }


def print_report(name: str, load_s: float, result: dict, misses_only: bool = True) -> None:
    now, peak = rss_mb()
    print(f"== {name}")
    print(
        f"load {load_s:.1f} s; {result['passages']} articles embedded at "
        f"{result['s_per_100']:.1f} s per 100; {result['s_per_query'] * 1000:.0f} ms per query"
    )
    print(f"memory: {now:.0f} MB now, {peak:.0f} MB peak (RSS)")
    print(f"{'set':<7} {'n':>3} {'hit@1':>6} {'hit@5':>6} {'MRR':>6}")
    for set_name, m in result["metrics"].items():
        print(f"{set_name:<7} {m['n']:>3} {m['hit@1']:>6.2f} {m['hit@5']:>6.2f} {m['mrr']:>6.2f}")
    for q, r in result["ranks"]:
        if r > 5 or not misses_only:
            print(f"  rank {r:>4} [{q.set}] {q.q}")


def main(argv: list[str] | None = None) -> int:
    from natalia.embeddings import MODEL_FILES, MODEL_REPO, Embedder

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--variant", choices=sorted(MODEL_FILES), default="int8")
    parser.add_argument("--repo", default=MODEL_REPO, help="another e5 model, for comparison")
    parser.add_argument("--show-relevant", action="store_true")
    parser.add_argument("--all-ranks", action="store_true", help="print every query's rank")
    parser.add_argument("--save", help="save the corpus vectors to this .npy file")
    args = parser.parse_args(argv)

    until, queries = load_eval()
    with db.connect() as conn:
        corpus = load_corpus(conn, until)
    resolve(queries, corpus)
    if args.show_relevant:
        titles = {c[0]: c[1] for c in corpus}
        for q in queries:
            print(f"[{q.set}] {q.q}")
            for i in sorted(q.relevant):
                print(f"    {titles[i][:110]}")
        return 0
    t0 = time.monotonic()
    embedder = Embedder(args.variant, repo=args.repo)
    load_s = time.monotonic() - t0
    result = evaluate(embedder.embed, queries, corpus)
    print_report(f"{args.repo} onnx {args.variant}", load_s, result, misses_only=not args.all_ranks)
    if args.save:
        np.save(args.save, result["vectors"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
