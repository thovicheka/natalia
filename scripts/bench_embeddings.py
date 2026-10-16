"""Run task 1.5's embedding evaluation with PyTorch (sentence-transformers) instead of ONNX.

PyTorch isn't a Natalia dependency (that's the point of the comparison), so run this from a
throwaway virtualenv, outside the project:

    uv venv /tmp/venv-st -p 3.12
    uv pip install --python /tmp/venv-st/bin/python torch --index-url https://download.pytorch.org/whl/cpu
    uv pip install --python /tmp/venv-st/bin/python sentence-transformers -e .
    /tmp/venv-st/bin/python scripts/bench_embeddings.py

Same queries, corpus and metrics as `python -m natalia.embed_eval` (config/embedding-eval.yaml).
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from natalia import db
from natalia.embed_eval import evaluate, load_corpus, load_eval, print_report, resolve
from natalia.embeddings import BATCH, MAX_TOKENS, MODEL_REPO


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--save", help="save the corpus vectors to this .npy file")
    args = parser.parse_args()

    import torch
    from sentence_transformers import SentenceTransformer

    torch.set_num_threads(args.threads)
    until, queries = load_eval()
    with db.connect() as conn:
        corpus = load_corpus(conn, until)
    resolve(queries, corpus)

    t0 = time.monotonic()
    model = SentenceTransformer(MODEL_REPO, device="cpu")
    model.max_seq_length = MAX_TOKENS
    load_s = time.monotonic() - t0

    def embed(texts: list[str], kind: str) -> np.ndarray:
        return model.encode(
            [f"{kind}: {t}" for t in texts], batch_size=BATCH, normalize_embeddings=True
        )

    with torch.inference_mode():
        result = evaluate(embed, queries, corpus)
    print_report(f"pytorch {torch.__version__}", load_s, result)
    if args.save:
        np.save(args.save, result["vectors"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
