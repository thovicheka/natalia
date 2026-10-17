# Decisions

Why each tool and rule was picked, and what it was picked over. The short version of each decision is in [`ROADMAP.md`](ROADMAP.md) ("Decisions already made"); agents don't swap any of them without asking the human. Updated as the build goes.

## LLM: Claude Haiku 5.5 on the Anthropic API (over Gemini, which was blocked)
- **Decided 2026-10-17 by the human (task 1.7)**, replacing the Gemini decision below.
- **Why:** Gemini was blocked for the whole account. Every `generateContent` request answered `403 PERMISSION_DENIED … Your project has been denied access` whatever the model (2026-10-16, 3 requests, 0 tokens; see [Stage 6](06-digest.md)), so the digest could not be built. Claude Haiku 5.5 is Anthropic's small, fast model and costs very little at this volume.
- **Model:** `claude-haiku-5-5`, pinned in `natalia/llm.py` (`MODELS`). Official `anthropic` SDK; key `ANTHROPIC_API_KEY` in `.env`.
- **Cost:** $0.10 per million input tokens, $0.50 per million output tokens (prompts up to 100k tokens; the digest's are ~3k). The human estimated **~$0.15/month** for the digest. The 2026-10-17 dry run gives 9 requests and ~27k input tokens a day (counted as characters ÷ 4; Claude's tokenizer may count more), plus ~5–8k output tokens. That works out to about $0.15–0.25 a month. Questions from the bot (task 2.3) come on top. **Measured on the first real digest (2026-10-17):** 42,713 input + 10,766 output tokens = **$0.0097**, so about **$0.29 a month**. Claude's tokenizer counts about 1.7× the characters ÷ 4 estimate, and Khmer text counts much more.
- **Spend limit:** prepaid credits with **auto-reload off**, so the most it can ever spend is the credit balance. Every real call still needs the human's approval while building (CLAUDE.md rule 4). `generate()` caps the requests per process (`max_calls`, retries included), and the digest caps them at 12 per build.
- **Request settings:** `output_config.effort = "low"`, because summaries need little thinking and thinking is billed as output. No `temperature`, because Haiku 5.5 answers 400 to non-default sampling values. JSON comes from structured outputs (`output_config.format`), and `strict_schema()` adds the `additionalProperties: false` this needs. The SDK's own retries are off, so `generate()` does the retrying and every request counts against the cap.
- **Gemini kept as an option:** `LLM_PROVIDER=gemini` in `.env` switches back with no code change (same `generate()` interface, same usage log).
- **Privacy:** CLAUDE.md rule 10 still holds: news only, never private data. The Gemini free-tier notice planned for the bot (2.1) and website (5.3) will need rewording for Anthropic (🧑 to confirm the account's data-use settings in the Console).
- **Alternatives considered:** Gemini on a new Google account or project (it might be blocked again, and it isn't an agent step anyway); the paid Gemini tier (needs billing on a project that is already denied); Claude Sonnet or Opus (better writing, but 20–40× the price per token for 2–3 sentence summaries).

## LLM: Gemini Flash on the free tier (over the Anthropic API)
- **Superseded on 2026-10-17** by the Claude Haiku 5.5 decision above. The project was denied access (403). Kept for the record, and because `LLM_PROVIDER=gemini` still works.
- **Why:** it costs nothing. Natalia is a personal project; the daily digest and a few questions a day fit the free tier's quota, so there's no bill and no spend limit to watch. Official `google-genai` SDK; key `GEMINI_API_KEY` from AI Studio, with no billing attached to its Google Cloud project.
- **Changed on 2026-10-15**, before task 0.1 was merged: the first draft used the Anthropic API.
- **Alternatives considered:**
  - **Anthropic API (Claude):** strong at summaries and Khmer, but paid per token from the first request, so every digest and every family question costs money and needs a spend limit.
  - **Paid Gemini tier:** same SDK and models, and Google doesn't use paid-tier prompts to improve its models. The fallback if the free tier's privacy terms become a problem for family and friends' messages.
  - **A local model:** ruled out by the server: 4 GB of RAM shared with cloud-ai-lab.
- **Trade-offs we accept:**
  - The free tier may use prompts and responses to improve Google's models. So: never send private data (CLAUDE.md rule 10); news content is fine. The bot's `/start` message and the website's chat page will tell people, in English and Khmer (tasks 2.1, 5.3).
  - Rate limits per minute and per day, shared by the digest and chat. So: the digest is batched into few requests (1.7), and chat gets a per-user daily cap (2.3).
- **Escape hatch:** every call goes through one thin wrapper, `natalia/llm.py`; no other module imports `google-genai` (a test checks it). Switching provider means changing one file.
- **Model, 2026-10-16 (task 1.7):** `gemini-3.8-flash`, pinned in `natalia/llm.py`. The human asked for Gemini 2.5 Flash, but the API answered `404 … gemini-2.5-flash is no longer available to new users. Please update your code to use models/gemini-3.8-flash`. ROADMAP's decision is "Gemini Flash, free tier", so the agent used the current Flash model and flagged it for the human. Pinned rather than `gemini-flash-latest`, so a model change shows up in review. Its free-tier limits are per project and shown only in AI Studio (🧑 to check).
- **Digest batching (1.7):** one request per topic (9 a day, ~24k input and ~4k output tokens), JSON output, summaries stored per article and reused. One request for all 45 stories would save 8 requests but risks a truncated or malformed reply losing the whole day; per-topic requests fail alone and retry cheaply.

## Embeddings: a small local model on CPU (over an embedding API)
- **Why:** free, no key, no quota, and the text never leaves the server. That matters less for news than for **questions**: in RAG, every question family and friends ask is embedded, and a local model keeps those on the box.
- **Planned model:** `intfloat/multilingual-e5-small` (384 dimensions; multilingual, so Khmer questions can find English articles). The schema's `vector(384)` matches it.
- **Alternatives considered:** a hosted embedding API (Gemini, OpenAI, …): no memory cost on the server, but another key, quota or bill, and questions sent to a third party. Kept as the fallback if the local model fails on memory or quality.
- **Risk:** PyTorch alone can take several hundred MB, and the daily flow must stay under ~700 MB inside the lab worker's `MemoryMax=900M`. Task 1.5 measures it (PyTorch vs ONNX runtime) before anything depends on it.
- **Measured in 1.5 (2026-10-16), recommended: keep the local model, as int8 ONNX** (`onnx/model_qint8_avx512_vnni.onnx` from the model's repo) on ONNX Runtime, tokenized with SentencePiece. Peak 407–438 MB while embedding (PyTorch: 1,298 MB; ONNX fp32: 949 MB), 2.9 s per 100 articles, 4 ms per query, 0.8 s to load; no PyTorch in `.venv`. Quality on 40 labeled queries over 2,614 real articles: English → English 15/15 at rank 1; Khmer → Khmer 9/10; Khmer → English 4/10 (6/10 in the top 5); English → Khmer 1/5. int8 vectors are within cosine 0.99 of fp32; fp32 equals PyTorch exactly. The bigger `multilingual-e5-base` was no better (Khmer → English 3/10) and twice as slow. Details: [Stage 5](05-embeddings.md).
- **The weak spot is Khmer questions about English news:** a Khmer query ranks Khmer articles first whatever their topic. Plan for 2.3/3.2 (not built yet): when a question is in Khmer, retrieve with both the Khmer question and an English rewording of it (the LLM already sees the question; the rewording can be one short extra request, counted against the free tier), and/or add keyword search. An embedding API stays the fallback if that isn't enough; it would mean a 🧑 account and key, and sending questions to a third party.
- **Why not the alternatives measured:** PyTorch: same vectors, 3× the memory and 1.2 GB of packages. fp32: slightly better Khmer → English (5/10 vs 4/10), more than double the memory. `tokenizers` + `tokenizer.json`: same token ids as SentencePiece but ~290 MB vs ~63 MB of RAM.

## Database: PostgreSQL + pgvector on this server
- **Why:** one database for rows *and* vectors. Articles, summaries, digests, chat memory (2.4) and the library (5.2) are relational; RAG needs nearest-neighbour search. pgvector does both in one place, with one backup and one connection string. Ubuntu 24.04 ships both as packages (`postgresql-16`, `postgresql-16-pgvector`).
- **Measured cost:** 52.8 MB idle, peak 68.6 MB after 1,863 articles (target ≤ 250 MB), with `shared_buffers=64MB`, `max_connections=20`, `jit=off`.
- **Alternatives considered:**
  - **SQLite + a vector extension:** no server process, but weaker with several writers (the daily flow, the bot and the website at once).
  - **A separate vector database** (Qdrant, Chroma): a second service using RAM, and articles split across two stores.
  - **Hosted PostgreSQL** (Supabase, Neon): no install, but data leaves the server and free tiers have limits.
- **Trade-offs:** installing it needs `sudo` (a 🧑 step). pgvector isn't a "trusted" extension, so the human creates it once as superuser; the migration only checks for it. Localhost only.

## Scheduling: the lab's self-hosted Prefect (over cron and GitHub Actions)
- **Why:** it's already running on this server (~300 MB for server + worker), so Natalia adds no service and no memory. Runs get states (scheduled, running, completed, failed), retries, logs and a UI at `http://lab:4200`, over Tailscale. Natalia only adds its own deployment to the shared work pool `lab`, scheduled at 07:00 Asia/Phnom_Penh.
- **Alternatives considered:**
  - **cron** (PLAN.md's first idea): nothing to set up, but no run history, no UI, and failures are silent unless we build alerting.
  - **GitHub Actions:** runs on GitHub's machines, which can't reach a database that only listens on localhost behind a firewall.
  - **A `systemd` timer:** fine, but needs `sudo` for every change, and gives less visibility than Prefect.
- **Trade-offs:** the lab worker runs at most 2 flows at once and its `MemoryMax=900M` is shared with lab flows; a lab GPU flow paused for approval at 07:00 holds a slot and could delay the digest (watched in 1.9). Natalia's deployment will run from its own runtime worktree and `.venv`, so branch switches never change what runs. Natalia never touches the lab's deployments or unit files.

## Website: Tailscale-only (no public URL)
- **Why:** it's for the human only. The server's firewall already blocks all incoming internet traffic and Tailscale is already how the human reaches it, so the site is private with no domain, TLS certificate, login system or tunnel to maintain. Nothing to attack from the internet.
- **Alternatives considered:** a public URL with a login (domain, HTTPS, auth, and a firewall change); a Cloudflare Tunnel (no open port, but a third party in front, and still needs auth).
- **Trade-off:** the phone needs the Tailscale app to open it. Family and friends use Telegram instead.

## Telegram: Natalia's own bot (not the lab's alert bot)
- **Why:** different audience and purpose. The lab's bot sends job alerts to the human; Natalia's talks to family and friends. Separate bots mean separate tokens (one can be revoked without the other), separate chat allowlists, and no chance that a family member gets a lab alert or the lab's `.env` is read (CLAUDE.md rule 9).
- **Long polling, not a webhook:** a webhook needs a public HTTPS URL; this server has none. Long polling only makes outgoing requests, which the firewall allows.
- **Alternatives considered:** reusing the lab bot (rejected for the reasons above).

## Paywalls: headline + excerpt + link only
- **Rule:** for paywalled sources, store only what their feed publishes (headline, excerpt, link). Never request the article page, never bypass a paywall. Prefer free sources for full detail.
- **Which:** the hard paywalls named in PLAN.md (Bloomberg, Financial Times, WSJ, The Athletic), plus metered ones marked in 1.1: The Economist, Foreign Affairs, Wired, MIT Technology Review, Nature, Scientific American, New Scientist, MarketWatch. A page that says `"isAccessibleForFree": false` is treated as paywalled too, whatever the source.
- **Why:** respects the publishers' terms; the excerpt plus the link is enough to know a story exists and open it with the human's own access. The AI summary sits next to the source and never replaces it.
- **Alternatives considered:** scraping past the paywall or through archive sites (rejected: against the sites' terms); dropping paywalled sources (rejected: their headlines still show what the financial press is covering).

## robots.txt: respected for pages *and* feeds (Google News dropped)
- **Rule:** the collector checks robots.txt for every page it fetches, on every redirect hop, for the agent token `natalia`, and honours `Crawl-delay` (above 30 s: no page fetches that run). On 2026-10-15 the human extended this to feeds: every enabled feed must be allowed by its site's robots.txt.
- **User agent:** `natalia/0.1 (personal news reader)`: honest, names the project, no "Mozilla". (NPR's servers stall any user agent containing the word "robots", so the first wording, "…respects robots.txt", had to go.)
- **Google News dropped:** Reuters and AP publish no public RSS, so 1.1 reached them through 10 Google News search feeds. news.google.com's robots.txt disallows both `/rss/search` (the feeds) and `/rss/articles/` (the redirect links), and current Google News link ids don't contain the article URL. **Decision:** disable all 10 Google News feeds.
- **Cost:** Reuters and AP are gone as sources, and so is Nikkei Asia's Cambodia feed. Other free feeds cover the same topics: every topic still has 4–11 free feeds.
- **Alternatives considered:** keep the Google News feeds (common practice for feed readers, but against the site's stated rules); decode links through Google's API (also disallowed); fetch Reuters directly (it blocks non-browser clients: HTTP 401).

## Topics: a list per article (over one topic column)
- **Rule:** `articles.topics` is a `topic[]` array (with a GIN index), not a single `topic` column.
- **Why:** one story often belongs to several topics. BBC repeats items across its section feeds, a business story can be about Cambodia, and 1.4 adds rule-based topics on top of the feed's. After 1.3's first run, 253 articles already had more than one topic. An array keeps "the article is stored once" true and makes "today's crypto items" one indexed query.
- **Alternatives considered:** one topic column (forces a choice, or stores the article twice); an `article_topics` join table (the textbook design, but more code and joins for a fixed list of 9 values). Confirmed by the human on 2026-10-15.

## Headline duplicates: near-identical only across sites
- **Rule:** after URL de-duplication, an article is a duplicate if its normalized headline (lowercase, no punctuation, no " - Publisher" suffix) matches one from the last 3 days **exactly** (any site), or is **near-identical** (similarity ≥ 0.9, headlines of 5+ words) **and comes from a different site** (host without `www.`).
- **Why:** near-identical matching across outlets catches the same story worded slightly differently ("…over returns policy" vs "…over migrant return policy"; "defence" vs "defense"). But within one site, near-identical headlines are usually a *series*, not a repeat: run 5 wrongly merged Wired's "The 9 best **movies** to stream this month" into "The 9 best **TV shows**…", and The Athletic's puzzle hints for Oct 14 into Oct 15's. Every good merge seen so far was across sites. Decided by the human on 2026-10-15.
- **Alternatives considered:** exact matches only (misses cross-outlet rewordings); similarity everywhere (the wrong merges above); grouping by embeddings (possible after 1.5, but heavier).
- **Cost:** a site that edits a headline and re-publishes it under a new URL could be stored twice.

## Agent guardrails: deny rules as a seatbelt, with real backstops behind them
- **Rule:** `.claude/settings.json` denies the risky actions (sudo, pushes to `main`, force-push, merge, recursive deletes, reading or writing any `.env`, editing cloud-ai-lab, Modal, destructive rclone, Prefect runs). Task 0.4 checked every rule in a live session with harmless probes and closed 9 gaps (other spellings of the same action).
- **Why both layers:** Claude Code matches Bash rules against the command text, so no list can cover every spelling (a script file that opens `.env` isn't caught). The rules stop the common and accidental cases; the backstops stop the rest: `sudo` needs a password the agent doesn't have, and GitHub branch protection on `main` (🧑, suggested in 0.4) refuses direct and force pushes whatever the command looks like.
- **Alternatives considered:** a sandboxed agent user without access to `.env` (stronger, but `sudo` to set up, and the collector needs `DATABASE_URL`); an allowlist instead of a denylist (safer, but every new tool needs a settings change, and auto mode already asks about unknown commands).
- **Cost:** broad patterns block some harmless commands: `git push … main…`, any `rm -r`, and any command line that contains `python` and `'.env` (e.g. a heredoc that writes docs mentioning `.env`). The agent then uses a narrower command or a script file.

## Top stories: coverage first, no LLM
- **Rule:** each day's top 5 per topic are picked by a transparent score (task 1.4): +2.5 per extra site covering the story, up to +1 for recency, +1 for full text, minus points for items that aren't news, and −4 under Cambodia for items that don't mention Cambodia. "General" (the day's headlines) picks first; each story then appears under one topic only. Topic tags come from the feed plus keyword rules (no rules for world-politics and general).
- **Why:** how many independent outlets carry a story is the best free signal of importance, and it needs no LLM call (the free tier's daily quota goes to summaries and questions). Every score can be printed and explained (`top -v`). One story per topic list keeps the digest short and spends one summary per story.
- **Alternatives considered:** ask the LLM to rank (uses quota, harder to check, varies run to run); rank by recency only (a flood of small items from busy feeds like Investing.com wins); embeddings to group stories (better at rewordings; possible after 1.5, but grouping by headline words already catches most); show a story under every topic it touches (repeats the day's biggest story in 3–4 sections).
- **Same data, same picks (task 1.4b, 2026-10-17):** on equal scores, the story whose lead article has the lowest id wins. When an article fits several stories equally well, it joins the earliest one. Articles load in a fixed order (publication time, then id). Before this, ties fell to memory addresses (`id(story)`) and to the order of a set of words, which Python's per-process hash seed changes. So a re-run of the 2026-10-17 digest picked 2 different stories and sent an extra paid request. Ids are arbitrary but stable, which is all a tie-break needs; a "better" tie-break (e.g. by source) would be a ranking change, not a fix.
- **Cost:** stories with very differently worded headlines aren't grouped; topics with few free full-text feeds (science, markets) get weaker picks. The human judges the picks (1.4's 🧑 step).
