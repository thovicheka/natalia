# Stage 5 — Embeddings

**Tasks:** 1.5 · **Status:** 🧑 measured; waiting on the human's pick (recommendation: keep the local model, int8 ONNX)

**What you'll have working by the end:** every stored article has a 384-dimension vector from `intfloat/multilingual-e5-small`, computed on the server's CPU with ONNX Runtime (no API, nothing leaves the server), and `natalia.embeddings search` finds the nearest articles to a question in English or Khmer. The model was measured three ways (PyTorch, ONNX fp32, ONNX int8) on memory, speed and retrieval quality over Natalia's real articles.

| Placeholder | In this build |
|---|---|
| `<scratch>` | a throwaway folder outside the repo |

## Prerequisites
- [Stage 3](03-collect.md) and [Stage 4](04-topics.md): stored articles (the evaluation uses the 2,614 collected by 2026-10-16 07:00 UTC).
- About 450 MB of free RAM while embedding, and ~600 MB of disk for the model files.

## Results (2026-10-16, 2 vCPU AMD EPYC Genoa, 2 threads)

| | ONNX int8 ✅ chosen | ONNX fp32 | PyTorch 2.14 (sentence-transformers 6.1) | e5-**base** ONNX int8 |
|---|---|---|---|---|
| Model file | 118 MB | 470 MB | 470 MB | 279 MB (768 dims) |
| Packages on disk | `.venv` 270 MB in all | same | throwaway venv **1.2 GB** | same as int8 |
| Load time | **0.8 s** | 1.8 s | 8.8 s | 13.8 s |
| Speed | **2.9 s per 100 articles**, 4 ms per query | 4.7 s, 7 ms | 5.1 s, 8 ms | 9.5 s, 7 ms |
| Peak RSS, whole evaluation | **407 MB** | 949 MB | 1,298 MB | 682 MB |
| hit@1 / hit@5, en → en (15) | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 | 1.00 / 1.00 |
| hit@1 / hit@5, km → en (10) | 0.40 / 0.60 | 0.50 / 0.60 | 0.50 / 0.60 | 0.30 / 0.60 |
| hit@1 / hit@5, km → km (10) | 0.90 / 1.00 | 0.90 / 1.00 | 0.90 / 1.00 | 0.70 / 1.00 |
| hit@1 / hit@5, en → km (5) | 0.20 / 0.40 | 0.20 / 0.40 | 0.20 / 0.40 | 0.20 / 0.40 |
| MRR, all 40 | 0.77 | 0.79 | 0.79 | 0.73 |

- PyTorch and ONNX fp32 give the **same vectors** (cosine 1.0000 on all 2,614 articles). int8 stays within cosine ≥ 0.9916 of fp32 (mean 0.9963).
- The production run (`embed`, all 2,614 articles): 75 s, **438 MB peak**, 312 MB after; a query process (`search`): 333 MB peak.
- English questions work very well. **Khmer questions find Khmer articles well but English articles poorly**: a Khmer query ranks Khmer articles first whatever their topic (see step 5). Why it's still the pick, and what to do about Khmer questions: [decisions](decisions.md#embeddings-a-small-local-model-on-cpu-over-an-embedding-api).

## Steps

### 1. Install the runtime *(on the server, in `~/projects/natalia`)*
```bash
uv add onnxruntime sentencepiece huggingface-hub numpy
```
*What it does:* ONNX Runtime runs the model on CPU; SentencePiece tokenizes; `huggingface-hub` downloads the model files once into `~/.cache/huggingface`. No PyTorch.

> **If** the embedding process uses ~300 MB more than expected, **check the tokenizer**: loading the model repo's `tokenizer.json` with the `tokenizers` library takes ~290 MB of RAM (a 250,000-word vocabulary). The repo's `sentencepiece.bpe.model` gives the same token ids in ~63 MB. Natalia uses SentencePiece.

<details><summary>Example from this build</summary>

```console
$ uv add onnxruntime tokenizers huggingface-hub numpy
 + huggingface-hub==2.2.0
 + numpy==2.5.4
 + onnxruntime==1.31.0
 + tokenizers==0.23.3
 …
$ du -sh .venv
270M	.venv
```
The first evaluation (with `tokenizers`) peaked at **681 MB**. Measuring each phase (`memprobe.py` and `sptest.py` were throwaway scripts in the agent's scratch folder):
```console
$ uv run python memprobe.py int8 16
start (45.8, 45.8)
imports (73.1, 73.1)
tokenizer (359.8, 376.0)          # tokenizer.json: +287 MB
session (497.9, 575.2)            # int8 model: +138 MB (+77 MB more while loading)
one batch of 16 x 256 tokens (513.1, 626.6)
$ uv run python sptest.py sp ; uv run python sptest.py tok
sentencepiece loaded: +63 MB
2616 texts encoded, peak 142 MB
tokenizers loaded: +289 MB
2616 texts encoded, peak 371 MB
2616 texts, 0 differ             # identical token ids on every article
$ uv add sentencepiece && uv remove tokenizers
```
**Result:** ❌ → ✅ after switching to SentencePiece: the evaluation's peak fell from 681 MB to 407 MB, load time from 2.9 s to 0.8 s, and the vectors are identical (max difference 0.0).
</details>

### 2. Embed the stored articles
```bash
uv run python -m natalia.embeddings embed
```
*What it does:* downloads the int8 model on first use (~140 MB with the tokenizer), embeds each article without a vector (headline + excerpt + the first 1,500 characters of text, as `passage: …`, at most 256 tokens), and stores it in `embeddings` with the model name `intfloat/multilingual-e5-small:int8`. Running it again embeds only new articles.

<details><summary>Example from this build</summary>

```console
$ /usr/bin/time -f "wall %e s, max RSS %M KB" uv run python -m natalia.embeddings embed
model intfloat/multilingual-e5-small:int8 loaded in 0.9 s
  256/2614 embedded
  …
embedded 2614 articles in 75 s, 2.9 s per 100 articles
memory: 312 MB now, 438 MB peak
wall 76.68 s, max RSS 448464 KB
$ uv run python -m natalia.embeddings embed
…
embedded 0 articles in 0 s
```
**Result:** ✅ A day's collection (~750 new articles) takes about 25 s.
</details>

### 3. Evaluate on the labeled set
```bash
uv run python -m natalia.embed_eval --show-relevant     # check the labels first
uv run python -m natalia.embed_eval                     # int8 (production)
uv run python -m natalia.embed_eval --variant fp32
```
*What it does:* `config/embedding-eval.yaml` holds 40 queries in four sets (English → English, Khmer → English, Khmer → Khmer, English → Khmer), each with headline patterns for its right answers, over a frozen corpus (articles collected before 2026-10-16 07:00 UTC). For each query, every article is ranked by cosine similarity; the report gives hit@1, hit@5 and MRR per set, speed and memory, and lists queries whose first right answer is below rank 5.

> **If** a Khmer pattern matches nothing, **it's probably zero-width spaces**: Khmer Times puts U+200B between words, which `\s` doesn't match. The evaluation matches against cleaned headlines (`natalia.topics.clean_text`).

<details><summary>Example from this build</summary>

```console
$ /usr/bin/time -f "wall %e s, max RSS %M KB" uv run python -m natalia.embed_eval --variant int8
== intfloat/multilingual-e5-small onnx int8
load 0.8 s; 2614 articles embedded at 2.9 s per 100; 4 ms per query
memory: 284 MB now, 407 MB peak (RSS)
set       n  hit@1  hit@5    MRR
en-en    15   1.00   1.00   1.00
km-en    10   0.40   0.60   0.46
km-km    10   0.90   1.00   0.95
en-km     5   0.20   0.40   0.34
all      40   0.72   0.82   0.77
  rank  315 [km-en] សេដ្ឋកិច្ចចក្រភពអង់គ្លេសកើនឡើងក្នុងខែសីហា
  rank   11 [km-en] អគារសាលារៀនដួលរលំសម្លាប់សិស្សនៅប៉ាគីស្ថាន
  rank   31 [km-en] នាវាឆេះនៅសមុទ្រខ្មៅ
  rank  258 [km-en] កីឡាករវាយកូនបាល់ត្រូវហាមឃាត់២៤ឆ្នាំ ពីបទរៀបចំលទ្ធផលប្រកួត
  rank   20 [en-km] Cambodia and Vietnam aim for 20 billion dollars in bilateral trade
  rank    8 [en-km] plastic waste in rivers after the Pchum Ben festival
  rank   27 [en-km] Cambodia earns 1.7 billion dollars from tyre exports
wall 77.30 s, max RSS 416332 KB

$ uv run python -m natalia.embed_eval --variant fp32
== intfloat/multilingual-e5-small onnx fp32
load 1.8 s; 2614 articles embedded at 4.7 s per 100; 7 ms per query
memory: 672 MB now, 949 MB peak (RSS)
km-en    10   0.50   0.60   0.54
all      40   0.75   0.82   0.79
…
```
**Result:** ✅ Two labels were too loose at first ("coral" matched a coral-spawning story; "Starknet" a privacy feature) and were tightened before any model was compared.
</details>

### 4. Compare with PyTorch *(optional, throwaway venv)*
```bash
uv venv <scratch>/venv-st -p 3.12
uv pip install --python <scratch>/venv-st/bin/python torch --index-url https://download.pytorch.org/whl/cpu
uv pip install --python <scratch>/venv-st/bin/python sentence-transformers -e .
<scratch>/venv-st/bin/python scripts/bench_embeddings.py
```
*What it does:* the same evaluation with `sentence-transformers` on PyTorch (CPU wheels: the default PyPI `torch` pulls GBs of CUDA libraries). Nothing is added to Natalia's `.venv`.

<details><summary>Example from this build</summary>

```console
$ du -sh venv-st venv-onnx
1.2G	venv-st
74M	venv-onnx
$ /usr/bin/time -f "wall %e s, max RSS %M KB" venv-st/bin/python scripts/bench_embeddings.py
== pytorch 2.14.1+cpu
load 8.8 s; 2614 articles embedded at 5.1 s per 100; 8 ms per query
memory: 1286 MB now, 1298 MB peak (RSS)
set       n  hit@1  hit@5    MRR
en-en    15   1.00   1.00   1.00
km-en    10   0.50   0.60   0.54
km-km    10   0.90   1.00   0.93
en-km     5   0.20   0.40   0.34
all      40   0.75   0.82   0.79
wall 152.82 s, max RSS 1328788 KB
cosine(fp32 onnx, pytorch): min 1.0000 mean 1.0000
cosine(int8 onnx, fp32 onnx): min 0.9916 mean 0.9963
```
And the bigger sibling model, to see if it fixes Khmer → English:
```console
$ uv run python -m natalia.embed_eval --repo intfloat/multilingual-e5-base --variant int8
load 13.8 s; 2614 articles embedded at 9.5 s per 100; 7 ms per query
memory: 580 MB now, 682 MB peak (RSS)
km-en    10   0.30   0.60   0.44
km-km    10   0.70   1.00   0.81
all      40   0.65   0.82   0.73
```
**Result:** ✅ PyTorch: same quality as ONNX fp32, 3× the memory of int8 and 1.2 GB of packages. e5-base: no better, twice as slow.
</details>

### 5. Search
```bash
uv run python -m natalia.embeddings search "<question>" -k 5
```
*What it does:* embeds the question (`query: …`) and lists the nearest stored articles by cosine similarity, with their language.

<details><summary>Example from this build</summary>

```console
$ uv run python -m natalia.embeddings search "Cambodia Thailand border dispute at the UN" -k 5
0.909 [en] Cambodia rejects Thai border claims at UN meeting
0.897 [en] UN representatives in fiery exchange over border conflict claims
0.894 [en] Cambodia rejects Thai claims at UNHCR meeting, demands safe return of displaced citizens
0.892 [en] Thai army disputes Cambodia’s displacement claims at UN - Nation Thailand
0.881 [en] Cambodia faces scrutiny over border dispute and online scam crackdown
memory: 265 MB now, 333 MB peak
$ uv run python -m natalia.embeddings search "ជម្លោះព្រំដែនកម្ពុជា-ថៃ" -k 5      # Cambodia–Thailand border dispute
0.884 [km] សង្គ្រាមពាក្យសម្ដី​ កម្ពុជា-ថៃ បន្តនៅអង្គការសហប្រជាជាតិ ជុំវិញជម្លោះព្រំដែន
0.880 [en] Cambodia's Path out of Least Developed Status - Cambodianess
0.880 [km] នាយករដ្ឋមន្រ្តី ៖ បទពិសោធថ្មី របស់កម្ពុជាផ្ទាល់ ពង្រឹងការជឿជាក់ថា សន្តិភាពមិនមែនមកដោយឯកឯង
0.873 [en] Cambodia Shares Pain of Declining Development Finance - Cambodianess
0.867 [en] Cambodia, Azerbaijan seek to deepen bilateral cooperation - Khmer Times
$ uv run python -m natalia.embeddings search "តម្លៃប្រេងនៅលើទីផ្សារពិភពលោក" -k 5  # world oil prices
0.869 [km] តម្លៃប្រេងបានធ្លាក់ចុះ ខណៈវិនិយោគិនកំពុងថ្លឹងថ្លែង …
0.868 [en] Poultry innovation in Cambodia achieves global recognition - The National Tribune
0.851 [km] ផ្សែងពុល​ពី​ភ្លើងឆេះព្រៃ​នៅឥណ្ឌូណេស៊ី …
0.851 [km] IEA ព្រមានថា ពិភពលោកប្រឈម នឹងហានិភ័យនៃការខ្វះខាត ប្រេងម៉ាស៊ូត …
0.848 [km] តម្លៃទំនិញប្រើប្រាស់ នៅសហរដ្ឋអាមេរិក បានកើនឡើង …
```
**Result:** ⚠️ English: excellent. Khmer: the right Khmer article comes first, but the English articles on the same story (four in the first search above) don't make the top 5, and loosely related Cambodia items do. This is the "Khmer → English" weakness in numbers.
</details>

### 6. Tests
```bash
uv run pytest -q tests/test_embeddings.py
```
*What it does:* `passage_text`, storing and re-running with a fake embedder (inside a rolled-back transaction), a new model replacing old vectors, search order; and, if the model is downloaded, the real model: 384-dimension unit vectors, an English and a Khmer query each finding the right passage, token ids capped at 256.

<details><summary>Example from this build</summary>

```console
$ uv run pytest -q
106 passed in 2.10s
```
**Result:** ✅
</details>

## Verify it worked
```bash
uv run python -m natalia.embeddings embed | tail -2
uv run python -m natalia.embeddings search "school roof collapse" -k 3
```
Expected: `embedded 0 articles` (or just today's new ones), then three articles about the story with similarity around 0.9.
