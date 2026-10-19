# Roadmap

The task list for building Natalia, from the five build phases in [`PLAN.md`](PLAN.md). Each task has an ID, a goal, steps marked **🧑 human** or **🤖 agent**, and a **done when** check.

**How to use it:** give an agent one task at a time, using the prompt format in [`TASK-TEMPLATE.md`](TASK-TEMPLATE.md) (or simply: *"Read CLAUDE.md and docs/ROADMAP.md, then do task 1.3 on a new branch."*). The agent stops when it reaches a 🧑 step and tells you exactly what to do. Tick tasks here when they're merged.

**Who does what, always:** 🧑 accounts, payments, API keys, `sudo`, approving any paid API call, merging to `main`. 🤖 code, config files, tests, docs.

**Order:** Stage 0 → Phase 1 → 2 → 3 → 4 → 5, as in the plan. Each phase ends with a working, usable agent, so the project stays finishable at every step.

**Stage docs:** numbered by build stage, in build order (`00-project-setup.md`, `01-sources.md`, `02-database.md`, `03-collect.md`, `04-topics.md`, `05-embeddings.md`, `06-digest.md`, `07-bot.md`, …; decided by the human on 2026-10-16). Each task names its doc with `→`; a task without one goes into the next free number. Each phase's "Document" task reviews and completes that phase's stage docs; it doesn't write a separate phase doc.

---

## Decisions already made

Don't swap these without asking the human.

| Area | Decision |
|---|---|
| LLM | **Google Gemini Flash, free tier**, through the official `google-genai` Python SDK. Key `GEMINI_API_KEY` from aistudio.google.com (🧑); no paid account, no billing. All calls go through one thin wrapper, `natalia/llm.py`, so the provider can be swapped later without touching other code. |
| Embeddings | **Stay local: a small multilingual model on CPU** (start with `intfloat/multilingual-e5-small`, 384 dimensions), checked on Khmer too. Fall back to an embedding API only if the local model fails on memory or quality (task 1.5). |
| Database | **PostgreSQL + pgvector on this server**, localhost only. Installing it is a 🧑 `sudo` step. |
| Scheduling | **The lab's self-hosted Prefect server, in Natalia's own work pool `natalia`** with its own worker (`natalia-worker.service`), so lab flows paused for approval can't block the digest (decided in 1.9; was pool `lab`). The digest is built daily at **05:00 Asia/Phnom_Penh** (was 07:00), ready before the human wakes; nothing is pushed, the bot's `/digest` serves it. Not GitHub Actions, not cron. |
| Telegram | **Natalia's own new bot**, separate from the lab's alert bot. Long polling, run as a `systemd` service. |
| Website | **Personal, Tailscale-only.** No public URL, no tunnel, no domain. |
| Voice | **Later phase (4)**, via a speech API or a Modal GPU job. The server CPU is too small for Whisper. |
| Sources | **Paywalled sources (Bloomberg, FT, WSJ, The Athletic): headline + excerpt + link only.** Never scrape past a paywall. Prefer free sources (Reuters, AP, BBC, …) for full detail. |
| Server | **2 vCPU / 4 GB RAM** + 4 GB swap, shared with cloud-ai-lab. Prefect already uses ~300 MB. |

### Privacy and limits on the Gemini free tier

- **The free tier may use prompts and responses to improve Google's models.** Never send private data: no secrets, no `.env` values, no personal notes. News content is fine.
- What people type to the bot or the website chat (and later, say in voice messages) is sent to Gemini too. The bot's `/start` message and the website's chat page say so, in English and Khmer, and ask people not to share private details (tasks 2.1 and 5.3).
- The free tier has rate limits (requests per minute and per day; check the current numbers in AI Studio). The digest is batched to use few requests, and chat has a per-user daily cap, so the bot can't use up the day's quota.

### Memory budget (target, measured as each part is built)

| Part | Target | Notes |
|---|---|---|
| Prefect server + worker (lab) | ~300 MB | already running |
| PostgreSQL | ≤ 250 MB | small `shared_buffers`, few connections |
| Telegram bot service | ≤ 550 MB (`MemoryMax`) | ~80 MB idle; each news question (1.9b) runs a ~330 MB search child for ~1 s, one at a time; small talk (1.9c) runs none. Conversation memory (1.9c): ≤ 6 × ~0.9 KB per chat; 1.9d also keeps Natalia's replies whole for translations, ≤ ~15 KB per chat |
| Website service | ≤ 250 MB | Phase 5 |
| Natalia's Prefect worker + daily flow | ≤ 700 MB (`MemoryMax`) | own cgroup since 1.9. First real run (no embed): **290 MiB peak**, **145 MiB idle** (82 MiB worker + 56 MiB reclaimable cache). With 1.9b's embed step, collect and embed run as child processes: expected peak ~570 MB at the embed step (`MemoryHigh=600M`). |

The embedding model is the biggest risk: PyTorch alone can take several hundred MB. Task 1.5 measures it before anything depends on it.

---

## Stage 0 — Project setup

- [x] **0.1 Project setup** — 🤖
  - 🤖 `CLAUDE.md` (hard rules from cloud-ai-lab, adapted), this roadmap, `docs/STATUS.md`, `docs/TASK-TEMPLATE.md`, `.env.example`; check `.gitignore` covers `.env` and `.venv`. PLAN.md restored as Markdown.
  - **Done when:** the files are on branch `task/0.1-project-setup`, ready for review.

- [x] **0.2 Python project and agent guardrails** — 🤖
  - 🤖 `uv init` (Python 3.12), package `natalia/`, `pytest` and `ruff` set up, one passing test.
  - 🤖 `.claude/settings.json` with `permissions.deny` rules like cloud-ai-lab's (`sudo`, push to main, force-push, `git merge`, `rm -rf`, reading `.env`, `prefect deployment run`).
  - **Done when:** `uv run pytest` passes and a denied command is blocked.

- [x] **0.3 Documentation** — 🤖
  - 🤖 `docs/STYLE.md` (adapted from cloud-ai-lab's), `docs/decisions.md`, stage docs for what's done (`00-project-setup.md`, `01-sources.md`, `02-database.md`, `03-collect.md`) written from STATUS.md's records, README with the architecture and a docs table, and a CLAUDE.md rule: after each task, update the matching stage doc.
  - **Done when:** the docs are on branch `task/0.3-docs`, ready for review.

- [ ] **0.4 Deny-rule check** — 🤖 → `docs/00-project-setup.md`
  - 🤖 In a Claude Code session started in `~/projects/natalia`, check that `.claude/settings.json` really blocks each guarded action (sudo, push to main, force-push, merge, `rm -rf`, reading `.env`, Modal, rclone, Prefect runs), using harmless probes (`--help`, `--dry-run`, a decoy `.env` with fake content). Probe for gaps (other spellings of the same action) and close them.
  - **Done when:** every guarded action is refused in a live session, gaps found are closed and re-tested, and a test checks the rules stay in the file.

---

## Phase 1 — Daily digest

Goal: every morning at 07:00 the human gets a digest on Telegram: headline, link, detail, AI summary and "why it matters", for each topic.

- [x] **1.1 Sources and feeds** — 🤖 + 🧑 → `docs/01-sources.md`
  - 🤖 Find RSS/Atom feed URLs for the sources in PLAN.md, per topic. Fetch each once (free) and record: works / broken / paywalled / no feed. Write `config/sources.yaml` (topic, source, feed URL, language, paywalled).
  - 🤖 Paywalled sources (Bloomberg, FT, WSJ, The Athletic) are kept as headline + excerpt + link only. Each topic has free sources (Reuters, AP, BBC, …) for full detail.
  - 🧑 Review the list.
  - **Done when:** every topic has at least 2 working free feeds, and a script prints the 5 latest headlines per topic.

- [x] **1.2 Database** — 🧑 + 🤖 → `docs/02-database.md`
  - 🤖 Write the exact install commands and a memory-tuned config (localhost only, small `shared_buffers`, low `max_connections`), plus the role and database setup.
  - 🧑 Install and configure (`sudo`):
    ```bash
    sudo apt install postgresql postgresql-16-pgvector   # PostgreSQL 16 + pgvector on Ubuntu 24.04
    ```
    then the role/database commands the agent wrote; put `DATABASE_URL` in `.env`.
  - 🤖 Schema and migrations: sources, articles (URL, title, text, topic, language, published), embeddings (`vector(384)`), summaries, digests. `CREATE EXTENSION vector` in a migration.
  - **Done when:** migrations run on the real database, tests pass against it, and PostgreSQL's memory is measured (`systemctl status postgresql`).

- [x] **1.3 Collect and clean** — 🤖 → `docs/03-collect.md`
  - 🤖 `feedparser` to read feeds, `trafilatura` to extract article text (never for paywalled sources: they keep the feed's excerpt; no scraping past a paywall). Deduplicate by canonical URL and normalized title. Polite fetching: timeouts, a user agent, no hammering.
  - **Done when:** running it twice stores the day's articles once each, with no duplicates, and failures on one feed don't stop the others.

- [ ] **1.4 Filter by topic and pick top stories** — 🤖 → `docs/04-topics.md`
  - 🤖 Tag each article with topics: from its feed first, then simple rules (e.g. "Cambodia" for anything mentioning Cambodia, Phnom Penh, Khmer…). No LLM calls.
  - 🤖 Rank and keep the top 5 stories per topic per day: prefer stories covered by several sources, recent ones, and ones with full text. No LLM calls.
  - **Done when:** tests on sample articles pass, and a real run's topic counts and top stories look sensible to the human.

- [ ] **1.5 Embeddings: evaluate the local model** — 🤖 (🧑 picks) → `docs/05-embeddings.md`
  - 🤖 Measure `multilingual-e5-small` on this server's CPU: peak RAM, load time, seconds per 100 articles. Compare PyTorch (`sentence-transformers`) with an ONNX runtime if PyTorch is too heavy.
  - 🤖 Check quality on a small labeled set: English queries → English articles, Khmer queries → English articles, Khmer articles. Record the numbers in a short report.
  - 🧑 Pick: keep the local model, or (only if needed) an embedding API, which means 🧑 an account and a key (and a spend limit if it's paid).
  - **Done when:** the choice is recorded with measured numbers, and the daily flow's peak stays inside the memory budget.

- [x] **1.6 Gemini API key** — 🧑 → `docs/00-project-setup.md`
  - 🧑 Sign in at aistudio.google.com with a Google account, create an API key, and add `GEMINI_API_KEY` to `.env`. Free tier: no paid account, no billing, no spend limit needed. Don't attach billing to the key's project.
  - **Done when:** the key is in `.env` (the agent doesn't test it until a task says so).

- [ ] **1.7 Summarize and explain** — 🤖 (🧑 runs it) → `docs/06-digest.md`
  - 🤖 `natalia/llm.py`: a thin wrapper around the `google-genai` SDK (the only module that imports it), with a fake for tests. It logs tokens per call and handles rate-limit errors with a short wait and retry. Digest builder: for each topic, the top items, each with headline, link, detail, AI summary and "why it matters". The summary sits next to the source, never replaces it.
  - 🤖 Pick the current Gemini Flash model, batch items so a digest takes few requests, and count requests and tokens per digest against the free tier's current limits.
  - 🧑 Approve and run one real digest (the agent writes the command and the expected request count).
  - **Done when:** a real digest for today is stored, its request and token counts are logged and well inside the free tier, and the human is happy with its quality.

- [ ] **1.8 Natalia's Telegram bot** — 🧑 + 🤖 → `docs/07-bot.md`
  - 🧑 Create a **new** bot with @BotFather (not the lab's alert bot). Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_OWNER_CHAT_ID` to `.env`; send the bot `/start` once.
  - 🤖 Bot code (long polling) that sends the stored digest to the owner's chat, a `systemd` service file with `MemoryMax`, and tests with a fake Telegram API (no bot is created and no message sent by the agent).
  - **Done when:** the token and chat ID are in `.env`, and the human has received a test digest from the bot.

- [ ] **1.9 Daily build on Prefect** — 🤖 + 🧑 → `docs/08-daily-flow.md`
  - 🤖 A Prefect flow `natalia-daily`: collect → filter → store → summarize (digest build, capped by `--max-requests`). Nothing is sent on success: `/digest` serves the stored digest. The owner gets a short Telegram message only if a step fails, the plan is over the cap (nothing sent to the LLM), or the digest is empty or has stories without a summary. Embedding joins the flow when chat (1.9b) needs the vectors.
  - 🤖 Natalia's own work pool `natalia` and worker unit (`deploy/natalia-worker.service`, `MemoryMax`), running from the runtime worktree `~/projects/natalia-runtime` and its `.venv`. The digest's cut-off moves to 05:00 so the build covers the whole window. `/digest` with no date sends yesterday's digest, then today's.
  - 🧑 Install the worker (`sudo`), register the deployment with its schedule OFF (05:00 Asia/Phnom_Penh), run it once by hand, then turn the schedule on. The schedule calls Haiku every day (~$0.01).
  - **Done when:** the digest is built at 05:00 two mornings in a row, both runs are Completed in the Prefect UI, and peak memory is recorded.

- [ ] **1.9b Chat in Telegram (RAG), owner-only** — 🤖 (🧑 tests it) → `docs/09-chat.md` (embed step: `docs/08-daily-flow.md`)
  - The human's next priority (2026-10-17), pulled forward from Phase 2: it is **task 2.3 (Questions, RAG)** with its daily cap, for the owner only, so it doesn't wait for 2.1's allowlist.
  - 🤖 Any plain text message from the owner is answered by Claude Haiku (`natalia/llm.py`), using only stored articles retrieved with pgvector (plus keyword search if it helps), always with sources (headline + link). Say so when the news doesn't cover the question. Add the embedding step to the daily flow so new articles get vectors.
  - 🤖 A daily question cap (requests per day), so chat can't run up the bill; over the cap, a short reply says so. Strangers still get the one-line refusal and no LLM call.
  - 🤖 **Memory plan for the embed step** (1.9's run measured 290 MiB peak and 145 MiB idle in the worker's cgroup, against `MemoryMax=600M`):
    - **Run collect and embed each in a child process** (`python -m natalia.collect`, `python -m natalia.embeddings embed`), one after the other, so each one's memory is freed when it exits. Moving embed alone isn't enough: the flow process keeps collect's ~210 MB high-water mark, so an embed child on top would peak *higher* (~82 + 210 + 340 ≈ 630 MB).
    - Expected peak with both as children: worker 82 + flow ~94 (Prefect only) + embed child ~340 (model + a day's new articles; 438 MB for all 2,614 articles at once) ≈ **520 MB**, plus page cache the kernel can reclaim.
    - **Also raise the caps in `deploy/natalia-worker.service`: `MemoryHigh` 450M → 550M, `MemoryMax` 600M → 700M** (🧑 `sudo`). Reason: ~520 MB is above `MemoryHigh=450M`, which would throttle the embed step every morning, and a catch-up embed of a big backlog (~440 MB child) would reach ~616 MB, over 600M. A cap reserves nothing: the extra is used only for the minute or two embedding takes at 05:00.
    - Measure the real cgroup peak on the first run (`systemctl show natalia-worker -p MemoryPeak`); if it is well under 550 MB, keep 600M instead.
  - 🧑 Approve the API use and ask it real questions.
  - **Done when:** answers cite real stored articles with links, a question the news doesn't cover gets an honest "not in the news", and the cap works.

- [ ] **1.9c Natural chat** — 🤖 (🧑 tests it) → `docs/09-chat.md`
  - The human's follow-up to 1.9b (2026-10-17): 1.9b answered everything as a news search, so "yo sup twin" got "the news doesn't cover that".
  - 🤖 A friendly general assistant that is also a news expert: small talk, jokes and slang get a natural reply with no search and no sources; only news and current events search the stored articles, answered with sources as in 1.9b.
  - 🤖 Show only the sources the answer used (none when the news doesn't cover it).
  - 🤖 Short conversation memory: the last ~6 messages per chat, so "tell me more" works; message text kept no longer than needed. *Kept in the bot's RAM for 30 minutes, not in PostgreSQL as 2.4 planned (decisions.md, "Chat").*
  - 🤖 Reply in the person's language and tone (Khmer, English or mixed). If someone seems genuinely upset: kind and brief, gently suggest talking to someone they trust.
  - 🤖 Keep owner-only, the daily cap and the cost logging; estimate the cost change from memory.
  - 🤖 Additions (same day): Natalia feels like a normal, friendly person whose specialty is news. General questions ("how do I fix my car's brakes?") get a helpful general-knowledge answer that says it isn't from today's news. News answers analyze (why it matters, related stories, how sources compare, what changed since previous days). Current facts (prices, who holds a role, recent events) only from stored articles; otherwise say so.
  - 🤖 The human's decisions (2026-10-18): cap raised to 50 messages a day; `/forget` clears the conversation memory; the general/news line stays as it is until real use shows mistakes.
  - 🧑 Approve the API use and talk to it.
  - **Done when:** small talk gets a friendly reply with no sources, a general question gets a marked general-knowledge answer, news questions get analyzed, sourced answers, a follow-up works, an uncovered current fact gets "not in the news", and the cap still holds.

- [ ] **1.9d Chat fixes from real use** — 🤖 (🧑 tests it) → `docs/09-chat.md`
  - The human's Telegram test of 1.9c (2026-10-19, bot log ~12:19 UTC) found five problems.
  - 🤖 Khmer replies cut off: a Khmer news answer hit max_tokens (thinking 1,132 + output 868 = 2,000) and the owner got "try again later". Give chat enough output room for Khmer (~3–4× the tokens of English) and limit thinking so it can't eat the answer budget. A reply that still stops at max_tokens is retried once with a higher limit, and logged. Test with a fake max_tokens reply. *Done: thinking off for chat (Haiku 5.5 has no thinking budget), 3,000–4,000 output tokens, one retry with twice the room.*
  - 🤖 Questions about Natalia's own data ("which days do you have news for?", "how many articles today?", "what sources do you use?") are answered from the database (dates with digests and articles, counts per day, the source list), not by article search.
  - 🤖 Vague follow-ups with no conversation memory ("tell me more" right after `/forget`): ask what the person means instead of searching random articles.
  - 🤖 Khmer persona: Natalia is female, so she says ចាស (not បាទ) and uses female polite forms.
  - 🤖 Translations of a previous answer are complete (one dropped the Cambodia–Thailand talks).
  - 🤖 Keep owner-only, the daily cap and the cost logging. Fakes in tests; ask before any real API call.
  - 🧑 Approve the real test (~$0.01, `docs/09-chat.md` step 11) and try it in Telegram.
  - **Done when:** a long Khmer answer arrives whole, data questions get the database's numbers, "tell me more" after `/forget` is asked about, Khmer replies use ចាស, and a translation keeps every part of the answer.

- [ ] **1.10 Document Phase 1** — 🤖 → review and complete Phase 1's stage docs (`01-sources.md` … `08-daily-flow.md`): every step with real output, nothing left only in STATUS.md, README's docs table up to date.

---

## Phase 2 — Conversation

Goal: the Telegram bot answers commands, questions, and follow-ups, grounded in stored articles (RAG).

- [ ] **2.1 Bot as a service, with an allowlist** — 🤖 + 🧑
  - 🤖 `python-telegram-bot` with long polling. Only chat IDs in `TELEGRAM_ALLOWED_CHAT_IDS` get answers; everyone else gets a short refusal and uses no Gemini quota. The `/start` message says, in English and Khmer, that messages are processed by Google Gemini's free tier and may be used to improve Google's models, so don't share private details. `deploy/natalia-bot.service` (auto-restart, start on boot, `MemoryMax`).
  - 🧑 Add family and friends' chat IDs; install and start the service (`sudo`).
  - **Done when:** the bot answers `/start` for allowed users, ignores others, and survives `sudo reboot`.

- [ ] **2.2 Commands** — 🤖
  - 🤖 `/today`, one command per topic (`/economics`, `/crypto`, `/cambodia`, …), `/help`. They read stored digests: no LLM call.
  - **Done when:** every command returns today's items in the news format.

- [ ] **2.3 Questions (RAG)** — 🤖 (🧑 tests it) — *the owner-only version is pulled forward as 1.9b; what's left here is opening it to the allowlist (2.1).*
  - 🤖 Retrieve with pgvector (plus keyword search if it helps), answer with the LLM using only retrieved articles, always with links. Say so when the news doesn't cover the question.
  - 🤖 Quota guard: a daily cap on LLM calls per user, so chat can't use up the free tier's daily quota before the next digest.
  - 🧑 Ask it real questions (approve the API use).
  - **Done when:** answers cite real stored articles, and the cap works.

- [ ] **2.4 Real conversation and two spaces** — 🤖 + 🧑
  - 🤖 Memory: a rolling window of the last N messages per chat, stored in PostgreSQL. *1.9c already keeps the last 6 messages per chat in the bot's RAM (30 minutes); what's left is the two spaces, and whether history should survive a restart.* Two spaces with separate histories: **News** (long items) and **Conversation** (short dialogue), via Telegram group topics or a `/mode` toggle.
  - 🧑 Choose topics or a toggle; if topics, create the group and add the bot.
  - **Done when:** follow-up questions work, and the two spaces never mix histories.

- [ ] **2.5 Document Phase 2** — 🤖 → review and complete Phase 2's stage docs (next free numbers, one per stage, e.g. `09-bot-service.md`, `10-rag.md`, …).

---

## Phase 3 — Language toggle (English / Khmer, text)

Goal: one switch changes everything to Khmer: news, summaries, the human's input, and the agent's replies.

- [ ] **3.1 Language setting** — 🤖
  - 🤖 Per-user language (`/lang`, stored), passed to every output path. News is collected once in its original language; only the output is translated.
  - **Done when:** switching changes every reply's language.

- [ ] **3.2 Khmer output** — 🤖 (🧑 reviews)
  - 🤖 Summaries, explanations and answers written in Khmer by the LLM. Each day's digest is translated once per language and cached, not once per user. Khmer questions retrieve English articles (checked in 1.5).
  - 🤖 Update the request and token counts for the Khmer version.
  - 🧑 Read a week of Khmer digests and answers and judge their quality.
  - **Done when:** the human is happy with the Khmer quality, and the requests per day are recorded and inside the free tier.

- [ ] **3.3 Document Phase 3** — 🤖 → review and complete Phase 3's stage docs (next free numbers).

---

## Phase 4 — Voice

Goal: send a voice message, get an answer in text or voice. English first, Khmer later.

- [ ] **4.1 Design** — 🤖 (🧑 picks)
  - 🤖 Compare speech-to-text through a hosted API against Whisper on a Modal GPU job (cost per minute, cold-start delay, Khmer support), and text-to-speech options for English and Khmer. The server CPU stays out of it.
  - 🧑 Pick one.
  - **Done when:** the choice is written down with costs.

- [ ] **4.2 Voice in** — 🤖 + 🧑
  - 🤖 The bot downloads the voice message, transcribes it with the chosen service, and answers in text through the normal path.
  - 🧑 Account and key (or Modal secret), with a spend limit; `sudo apt install ffmpeg` if audio conversion needs it. Approve test runs.
  - **Done when:** an English voice question gets a correct text answer.

- [ ] **4.3 Voice replies (optional)** — 🤖 + 🧑
  - 🤖 Text-to-speech replies, on demand.
  - **Done when:** the bot can answer with a voice message.

- [ ] **4.4 Khmer voice** — 🤖 + 🧑
  - 🤖 Khmer speech-to-text and text-to-speech with the services from 4.1; measure quality.
  - 🧑 Judge the quality.
  - **Done when:** a Khmer voice question gets a correct answer.

- [ ] **4.5 Document Phase 4** — 🤖 → review and complete Phase 4's stage docs (next free numbers).

---

## Phase 5 — Personal website

Goal: the human's main interface: the news feed, a personal library, and a Claude-like chat, reachable only over Tailscale.

- [ ] **5.1 Quick version: news feed** — 🤖 + 🧑
  - 🤖 Streamlit (or Gradio) app: feed per topic in the news format, language toggle at the top. `deploy/natalia-web.service` (`MemoryMax`). It listens on a port that only Tailscale can reach (the firewall already blocks the internet); no public URL.
  - 🧑 Install and start the service (`sudo`); confirm the firewall rule (`sudo ufw status`).
  - **Done when:** `http://lab:<port>` opens from the laptop on Tailscale, and not from a phone off Tailscale.

- [ ] **5.2 Personal Library** — 🤖
  - 🤖 Save/bookmark articles into collections (Read Later, Important, by topic), stored in PostgreSQL.
  - **Done when:** saved articles survive a restart and can be moved between collections.

- [ ] **5.3 Chat** — 🤖 (🧑 tests it)
  - 🤖 A Claude-like chat page on the same engine as the bot (RAG, memory, language), with the same Gemini privacy notice as the bot.
  - **Done when:** a conversation on the site answers with links to real articles.

- [ ] **5.4 Polished version (React)** — 🤖 + 🧑, later
  - 🤖 Propose a small API (e.g. FastAPI) plus a React front end; 🧑 approves and installs Node if needed.
  - **Done when:** the React site does everything the quick version did.

- [ ] **5.5 Document Phase 5** — 🤖 → review and complete Phase 5's stage docs (next free numbers).

---

## Done

Nothing yet.
