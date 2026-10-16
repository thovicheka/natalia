# Stage 6 — Summaries and the daily digest

**Tasks:** 1.7 · **Status:** 🧑 blocked: the Gemini project answers `403 PERMISSION_DENIED` (step 4). Code, tests and the day's picks are done; summaries wait for the human to restore API access.

**What you'll have working by the end:** `natalia/llm.py`, the one wrapper every LLM call goes through (Gemini Flash, free tier, `google-genai`), and a digest builder that takes the day's top 5 stories per topic ([Stage 4](04-topics.md)), asks the LLM for a short summary and "why it matters" for each (one request per topic, 9 per day), stores them, and renders the digest: headline + link + the source's own text first, then the AI summary.

| Placeholder | In this build |
|---|---|
| `<date>` | `2026-10-16` |
| `<model>` | `gemini-3.8-flash` |

## Prerequisites
- [Stage 0](00-project-setup.md#7--gemini-api-key-free-tier-in-your-browser): `GEMINI_API_KEY` in `.env`, from a project with **no billing** (free tier).
- [Stage 4](04-topics.md): tagged articles for the day.

## How it works
- **`natalia/llm.py`** is the only module that imports `google-genai` (a test checks it). `generate(prompt, system=…, json_schema=…)` returns the text and token counts; 429 and 5xx errors are retried up to 3 times after the wait the error asks for (capped at 65 s); `set_max_calls(n)` caps a process's requests, retries included; every request (failed ones too) is one JSON line in `logs/llm-usage.jsonl` (git-ignored). Thinking is turned down (`thinking_level="low"` on Gemini 3; budget 0 on Gemini 2).
- **`natalia/digest.py build`**: for each topic, one request with the stories that have no summary yet. The prompt holds news only: id, headline, source, date and up to 2,500 characters of the article (or the feed's excerpt for paywalled sources); no links, nothing about the reader. The reply is JSON (`{"items": [{id, summary, why_it_matters}]}`), checked against the ids sent. Summaries go into `summaries` (one per article and language), so a re-run reuses them and sends nothing; the picks go into `digests` / `digest_items`, with request and token counts. Requests are spaced 13 s apart (≤ 5 a minute).
- **`show`** renders a stored digest as Markdown (`--save` writes `docs/digests/<date>.md`). The bot (task 1.8) reads the same stored digest.
- Why one request per topic, and the model: [decisions](decisions.md#llm-gemini-flash-on-the-free-tier-over-the-anthropic-api).

## Steps

### 1. Install the SDK
```bash
uv add google-genai
```
<details><summary>Example from this build</summary>

```console
$ uv add google-genai
 + google-auth==2.62.0
 + google-genai==2.31.0
```
**Result:** ✅
</details>

### 2. Check the free tier's limits *(🧑, in your browser)*
Open AI Studio → *Usage & limits* (or the "View your active rate limits" link on [ai.google.dev/gemini-api/docs/rate-limits](https://ai.google.dev/gemini-api/docs/rate-limits)) and note requests per minute and per day for `<model>`. Limits are per project, not per key.

*What it does:* the digest uses 9 requests a day and spaces them 13 s apart; chat (task 2.3) needs the rest of the daily quota.

<details><summary>Example from this build</summary>

On 2026-10-16 the public rate-limits page no longer lists free-tier numbers; it says they "can be viewed in Google AI Studio" and are "applied per project, not per API key". **Result:** ⏳ the human's to check.
</details>

### 3. Preview the requests without calling anything
```bash
uv run python -m natalia.digest build --dry-run
```
*What it does:* picks the stories and prints one line per request it would send, with a rough input-token count. Nothing is sent or stored.

<details><summary>Example from this build</summary>

```console
$ uv run python -m natalia.digest build --dry-run
[dry run] general: 5 stories, ~3052 input tokens
[dry run] economics: 5 stories, ~2709 input tokens
[dry run] world-politics: 5 stories, ~3105 input tokens
[dry run] technology: 5 stories, ~2639 input tokens
[dry run] science: 5 stories, ~2751 input tokens
[dry run] sport: 5 stories, ~2644 input tokens
[dry run] crypto: 5 stories, ~2722 input tokens
[dry run] markets: 5 stories, ~2445 input tokens
[dry run] cambodia: 5 stories, ~1392 input tokens

digest 2026-10-16: 45 stories, 0 summaries reused, 0 new, 0 missing; 9 requests, 0 input + 0 output tokens, 1 s
```
**Result:** ✅ 9 requests, ~23,500 input tokens (plus ~250 for the instructions each), and an expected ~4,000 output tokens (45 × ~90).
</details>

### 4. Check access with one tiny request
```bash
uv run python -m natalia.llm ping
```
*What it does:* sends "Reply with the single word OK." (~10 tokens). Listing models (stage 0's key test) only proves the key is valid; this proves the project may generate.

> **If you see** `404 NOT_FOUND … models/gemini-2.5-flash is no longer available to new users`, **it means** the model was closed to new keys. Use a current one: `natalia/llm.py`'s `DEFAULT_MODEL` (here `gemini-3.8-flash`, the newest numbered Flash model the key listed), or `--model` on `ping` and `digest build`.

> **If you see** `403 PERMISSION_DENIED … Your project has been denied access. Please contact support.`, **it means** Google has blocked the Cloud project behind the key from generating (it happens with every model, so it isn't the model). Fix it in your browser, not in code: in AI Studio, open *Get API key* and check the project; create a key in a **new** project (no billing) and put it in `.env`; run `ping` again. If a new project is denied too, the Google account itself is restricted: use AI Studio's *Send feedback* / Google Cloud support, or another Google account. Don't attach billing to get around it.

<details><summary>Example from this build (2026-10-16)</summary>

```console
$ uv run python -m natalia.digest build --topics economics --max-requests 1   # model gemini-2.5-flash
economics: failed: LLM request failed (404): 404 NOT_FOUND. {'error': {'code': 404, 'message': 'This model models/gemini-2.5-flash is no longer available to new users. Please update your code to use models/gemini-3.8-flash for the latest features and improvements. …
```
❌ **Cause:** the model is closed to new keys. **Fix:** `DEFAULT_MODEL = "gemini-3.8-flash"` (listed by the key's models endpoint, along with `gemini-flash-latest`, `gemini-3.5-flash`, `gemini-3.1-flash-lite` …); thinking set by level for Gemini 3.
```console
$ uv run python -m natalia.digest build --topics economics --max-requests 1   # gemini-3.8-flash
economics: failed: LLM request failed (403): 403 PERMISSION_DENIED. {'error': {'code': 403, 'message': 'Your project has been denied access. Please contact support.', 'status': 'PERMISSION_DENIED'}}
$ uv run python ping.py gemini-3.1-flash-lite      # one diagnostic request, another model
FAILED: LLM request failed (403): 403 PERMISSION_DENIED. {… 'Your project has been denied access. Please contact support.' …}
```
❌ **Cause:** the Google Cloud project is blocked from generating, whatever the model. The key itself works (the models list answers). **Fix:** 🧑, as above. The agent stopped calling Gemini here.

Requests used in this build: **3** (1 × 404, 2 × 403), **0 tokens**. From `logs/llm-usage.jsonl`:
```console
{"at": "2026-10-16T06:3…", "purpose": "digest 2026-10-16 economics", "model": null, "input_tokens": 0, "output_tokens": 0, "thinking_tokens": 0, "error": "404: 404 NOT_FOUND. …"}
{"at": "2026-10-16T06:34:24+00:00", "purpose": "digest 2026-10-16 economics", "model": null, …, "error": "403: 403 PERMISSION_DENIED. …"}
{"at": "2026-10-16T06:3…", "purpose": "1.7 diagnostic", "model": null, …, "error": "403: 403 PERMISSION_DENIED. …"}
```
**Result:** ❌ blocked on the human.
</details>

### 5. Build the digest
```bash
uv run python -m natalia.digest build --date <date>            # 9 requests
uv run python -m natalia.digest show --date <date> --save      # → docs/digests/<date>.md
```
*What it does:* summarizes the stories that have none yet (one request per topic, 13 s apart, at most 12 requests), stores everything, and prints one line per topic with its token counts, then the totals. Re-running it sends nothing for stories already summarized. `--no-llm` stores the picks without summaries.

<details><summary>Example from this build</summary>

With Gemini blocked, the picks were stored without summaries, and the preview saved to [`digests/2026-10-16.md`](digests/2026-10-16.md):
```console
$ uv run python -m natalia.digest build --no-llm
digest 2026-10-16: 45 stories, 0 summaries reused, 0 new, 45 missing; 0 requests, 0 input + 0 output tokens, 1 s
$ uv run python -m natalia.digest show --save | head -12
# Natalia daily digest — Friday 16 October 2026

News from the 24 hours before 07:00 Asia/Phnom_Penh. Summaries pending: none generated yet for these 45 stories. Each summary sits under the source's own headline, link and text; read the source to check it.

## Top stories

### 1. [School roof collapses in northwestern Pakistan, killing at least 29 people](https://www.aljazeera.com/news/2026/10/15/…)
*Al Jazeera · 15 Oct 15:30*

> At least 28 students and one teacher killed in incident at Al-Khair Education Centre, a private school in Peshawar.

*(summary pending: not generated yet)*
```
**Result:** ⏳ the summaries are the human's step (access first). Running step 5 then fills them in for the same 45 stories.
</details>

### 6. Tests
```bash
uv run pytest -q tests/test_llm.py tests/test_digest.py
```
*What it does:* the wrapper with a fake provider (token counts and the usage log, a 429 retried after the wait it asks for, retries capped, 400 not retried, the call cap counting retries, a missing key); the digest against the real database with a fake LLM (one request per topic, summaries stored and reused on the next build, a missing answer reported and shown as pending, `--dry-run` and `--no-llm` sending nothing, the source shown before the summary, prompts holding news only, no links).

<details><summary>Example from this build</summary>

```console
$ uv run pytest -q
119 passed in 2.32s
```
**Result:** ✅
</details>

## Verify it worked
```bash
uv run python -m natalia.llm ping
uv run python -m natalia.digest show --date <date> | head -3
```
Expected: `gemini-3.8-flash: 'OK' (… in / … out tokens)`, and a header line that starts `Summaries by gemini-3.8-flash for 45 of 45 stories (9 requests, …`.
