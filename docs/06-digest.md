# Stage 6 — Summaries and the daily digest

**Tasks:** 1.7 · **Status:** ⏳ switched to Claude Haiku 5.5 on 2026-10-17, because the Gemini project answers `403 PERMISSION_DENIED`. Code, tests and the day's picks are done. The first real call (one `ping`, step 4) waits for the human's approval, and the full digest (step 5) waits for a second one.

**What you'll have working by the end:** `natalia/llm.py`, the one wrapper every LLM call goes through (Claude Haiku 5.5 through the `anthropic` SDK by default; Gemini Flash through `google-genai` with `LLM_PROVIDER=gemini`), and a digest builder that takes the day's top 5 stories per topic ([Stage 4](04-topics.md)), asks the LLM for a short summary and "why it matters" for each (one request per topic, 9 per day), stores them, and renders the digest: headline + link + the source's own text first, then the AI summary.

| Placeholder | In this build |
|---|---|
| `<date>` | `2026-10-16` |
| `<model>` | `claude-haiku-5-5` (`gemini-3.8-flash` with `LLM_PROVIDER=gemini`) |

## Prerequisites
- `ANTHROPIC_API_KEY` in `.env` *(🧑)*, from an Anthropic Console account with **prepaid credits and auto-reload off**, so spending can't go past the balance. `LLM_PROVIDER` can stay unset (default `anthropic`).
- Only for `LLM_PROVIDER=gemini`: [Stage 0](00-project-setup.md#7--gemini-api-key-free-tier-in-your-browser): `GEMINI_API_KEY` in `.env`, from a project with **no billing** (free tier).
- [Stage 4](04-topics.md): tagged articles for the day.

## How it works
- **`natalia/llm.py`** is the only module that imports an LLM SDK (`anthropic` or `google-genai`; a test checks it). `LLM_PROVIDER` (environment or `.env`) picks the backend, `anthropic` by default, and each provider has a pinned model (`MODELS`). `generate(prompt, system=…, json_schema=…)` returns the text and token counts; 429 and 5xx errors are retried up to 3 times after the wait the error asks for (capped at 65 s); `set_max_calls(n)` caps a process's requests, retries included; every request (failed ones too) is one JSON line in `logs/llm-usage.jsonl` (git-ignored). Thinking is turned down: `effort: "low"` on Claude, `thinking_level="low"` on Gemini 3, budget 0 on Gemini 2. Claude gets no `temperature` (Haiku 5.5 answers 400 to non-default sampling values), its JSON comes from structured outputs (`output_config.format`, with `additionalProperties: false` added to every object by `strict_schema()`), a refusal is an error, and the SDK's own retries are off, so every request counts against the cap. Claude's thinking tokens are logged apart from its output tokens.
- **`natalia/digest.py build`**: for each topic, one request with the stories that have no summary yet. The prompt holds news only: id, headline, source, date and up to 2,500 characters of the article (or the feed's excerpt for paywalled sources); no links, nothing about the reader. The reply is JSON (`{"items": [{id, summary, why_it_matters}]}`), checked against the ids sent. Summaries go into `summaries` (one per article and language), so a re-run reuses them and sends nothing; the picks go into `digests` / `digest_items`, with request and token counts. Requests are spaced 13 s apart (≤ 5 a minute).
- **A story left without a summary** (no item for its id, or a reply that isn't valid JSON): the raw reply is saved to `logs/digest-replies/` (git-ignored, news only) with the ids sent and missing and why the model stopped (`stop_reason`, e.g. `max_tokens`), and the build log names the file.
- **`show`** renders a stored digest as Markdown (`--save` writes `docs/digests/<date>.md`). The bot (task 1.8) reads the same stored digest.
- Why Claude Haiku 5.5, its cost, and why one request per topic: [decisions](decisions.md#llm-claude-haiku-55-on-the-anthropic-api-over-gemini-which-was-blocked), [Gemini (superseded)](decisions.md#llm-gemini-flash-on-the-free-tier-over-the-anthropic-api).

## Steps

### 1. Install the SDKs
```bash
uv add anthropic       # Claude, the default provider
uv add google-genai    # Gemini, only for LLM_PROVIDER=gemini
```
<details><summary>Example from this build</summary>

```console
$ uv add google-genai
 + google-auth==2.62.0
 + google-genai==2.31.0
$ uv add anthropic                                   # 2026-10-17
 + anthropic==1.15.0
 + docstring-parser==0.18.0
 + jiter==0.17.0
```
**Result:** ✅
</details>

### 2. Check the limits *(🧑, in your browser)*
**Claude:** in the Anthropic Console, check that *auto-reload* is off under Billing, and note the credit balance and the rate limits for `claude-haiku-5-5` (Settings → Limits). Nine requests a day are far below any tier's limits.

**Gemini (only with `LLM_PROVIDER=gemini`):** open AI Studio → *Usage & limits* (or the "View your active rate limits" link on [ai.google.dev/gemini-api/docs/rate-limits](https://ai.google.dev/gemini-api/docs/rate-limits)) and note requests per minute and per day for `<model>`. Limits are per project, not per key.

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

The 2026-10-17 run, after the switch to Claude (the dry run makes no request with either provider):
```console
$ uv run python -m natalia.digest build --dry-run
[dry run] general: 4 stories, ~2634 input tokens
[dry run] economics: 5 stories, ~3331 input tokens
[dry run] world-politics: 5 stories, ~2937 input tokens
[dry run] technology: 5 stories, ~2915 input tokens
[dry run] science: 5 stories, ~1934 input tokens
[dry run] sport: 5 stories, ~3309 input tokens
[dry run] crypto: 5 stories, ~2677 input tokens
[dry run] markets: 5 stories, ~2759 input tokens
[dry run] cambodia: 5 stories, ~2847 input tokens

digest 2026-10-17: 44 stories, 0 summaries reused, 0 new, 0 missing; 9 requests, 0 input + 0 output tokens, 0 s
```
**Result:** ✅ ~25,300 input tokens (characters ÷ 4; Claude's tokenizer may count more). At Haiku 5.5's $0.10/M input and $0.50/M output, with ~5–8k output tokens including thinking, a full digest costs about **$0.006** (~$0.15–0.25 a month).
</details>

### 4. Check access with one tiny request
```bash
uv run python -m natalia.llm ping
```
*What it does:* sends "Reply with the single word OK." to the provider's pinned model (about 15 input tokens, at most 64 output tokens because thinking counts toward the cap), and prints the reply and token counts, never the key. With Claude it costs well under $0.0001. It proves that the key, the account's access and the model all work.

> **If you see** `ANTHROPIC_API_KEY is not set`, **it means** the key isn't in `.env` (or the environment). Add it as `ANTHROPIC_API_KEY=…` (🧑).

> **If you see** `401` or `authentication_error`, **it means** the key is wrong or revoked. An error about the **credit balance** means the prepaid credits ran out; with auto-reload off, nothing more is spent until the human tops up.

The two notes below are from the Gemini attempt (`LLM_PROVIDER=gemini`).

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

The first real digest, with Claude Haiku 5.5, on 2026-10-17 (approved by the human after a successful `ping`: 18 input / 4 output tokens). Saved to [`digests/2026-10-17.md`](digests/2026-10-17.md):
```console
$ uv run python -m natalia.digest build                       # 2026-10-17, claude-haiku-5-5
general: 4/4 summarized, 3982 in / 1024 out tokens
economics: 5/5 summarized, 4964 in / 1406 out tokens
world-politics: 4/5 summarized, 4451 in / 1042 out tokens
technology: 5/5 summarized, 4448 in / 1283 out tokens
science: 5/5 summarized, 3191 in / 1151 out tokens
sport: 5/5 summarized, 5109 in / 1175 out tokens
crypto: 5/5 summarized, 4229 in / 1178 out tokens
markets: 5/5 summarized, 4335 in / 1132 out tokens
cambodia: 5/5 summarized, 8004 in / 1375 out tokens

digest 2026-10-17: 44 stories, 0 summaries reused, 43 new, 1 missing; 9 requests, 42713 input + 10766 output tokens, 163 s
$ uv run python -m natalia.digest show --save | head -3
# Natalia daily digest — Saturday 17 October 2026

News from the 24 hours before 07:00 Asia/Phnom_Penh. Summaries by claude-haiku-5-5 for 43 of 44 stories (9 requests, 42,713 input + 10,766 output tokens). …
```
**Result:** ✅ 43 of 44 summarized. **Cost:** 42,713 × $0.10/M + 10,766 × $0.50/M = $0.0043 + $0.0054 = **$0.0097** (about $0.29 for 30 days). That is above the dry-run estimate, for two reasons. Claude's tokenizer counted 1.7× the characters ÷ 4 estimate, and Khmer text far more: `cambodia` was 8,004 tokens against an estimate of ~2,850. Output also averaged ~245 tokens per story. The API reported 0 thinking tokens at `effort: "low"`. Billing is on `output_tokens`, which would include any thinking, so the cost above is complete either way.

❌ **1 missing:** `world-politics` came back with 4 of 5 ("They fled Russia, but the West sent them back", BBC). The reply had no item for that id, or the item was dropped by the id check; the raw reply isn't stored, so which one can't be told. **Fix:** re-running `build` sends one request for that story only (the other 43 are reused). It shows as *summary pending* until then.

The rerun (approved by the human, expecting 1 request) sent **2**:
```console
$ uv run python -m natalia.digest build                       # 2026-10-17, rerun for the missing story
general: 2/2 summarized, 2203 in / 534 out tokens
world-politics: 1/1 summarized, 1423 in / 361 out tokens

digest 2026-10-17: 44 stories, 41 summaries reused, 3 new, 0 missing; 2 requests, 3626 input + 895 output tokens, 21 s
```
**Result:** ✅ 44 of 44 summarized; ⚠️ 2 requests instead of 1. **Cost:** 3,626 × $0.10/M + 895 × $0.50/M = **$0.0008** (expected ~$0.0002). **Cause of the extra request:** the picks changed between the two builds with no new articles (last collected 2026-10-16 06:05 UTC). `top_stories` breaks equal scores with `id(story)`, a Python memory address that differs between runs (`natalia/topics.py`, `pick_topics`), and `load_window` has no `ORDER BY`. So in general the Oregon shooting story was now led by the Guardian's article instead of the BBC's, "They fled Russia…" moved from world-politics to general (and was summarized there), and another story moved into world-politics. **Fix (not made, task 1.4 code):** break ties on a stable key such as the lead article's id. Recorded as an open question.

Since then, a request that leaves a story without a summary saves its raw reply to `logs/digest-replies/<date>-<topic>-<HHMMSS>.json` (git-ignored), with the ids sent and missing, the token counts and the model's `stop_reason`. The rerun had nothing missing, so it saved nothing.
</details>

### 6. Tests
```bash
uv run pytest -q tests/test_llm.py tests/test_digest.py
```
*What it does:* the wrapper with a fake provider (token counts and the usage log, a 429 retried after the wait it asks for, retries capped, 400 not retried, the call cap counting retries, a missing key; `LLM_PROVIDER` picking the backend and its model; the Claude backend against a fake SDK client: request shape with no `temperature`, `effort: low`, a strict JSON schema, thinking tokens split out, a 429 keeping its `retry-after`, a refusal raised as an error); the digest against the real database with a fake LLM (one request per topic, summaries stored and reused on the next build, a missing answer reported and shown as pending, `--dry-run` and `--no-llm` sending nothing, the source shown before the summary, prompts holding news only, no links).

<details><summary>Example from this build</summary>

```console
$ uv run pytest -q
119 passed in 2.32s
$ uv run pytest -q                                   # 2026-10-17, with the Claude backend
130 passed in 3.28s
```
**Result:** ✅
</details>

## Verify it worked
```bash
uv run python -m natalia.llm ping
uv run python -m natalia.digest show --date <date> | head -3
```
Expected: `claude-haiku-5-5: 'OK' (… in / … out / … thinking tokens)`, and a header line that starts `Summaries by claude-haiku-5-5 for 44 of 44 stories (9 requests, …` (the story count is the day's).
