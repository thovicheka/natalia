# Roadmap

The task list for building Natalia, from the five build phases in [`PLAN.md`](PLAN.md). Each task has an ID, a goal, steps marked **🧑 human** or **🤖 agent**, and a **done when** check.

**How to use it:** give an agent one task at a time: *"Read CLAUDE.md and docs/ROADMAP.md, then do task 1.3 on a new branch."* The agent stops when it reaches a 🧑 step and tells you exactly what to do. Tick tasks here when they're merged.

**Who does what, always:** 🧑 accounts, payments, API keys, `sudo`, approving any paid API call, merging to `main`. 🤖 code, config files, tests, docs.

**Order:** Stage 0 → Phase 1 → 2 → 3 → 4 → 5, as in the plan. Each phase ends with a working, usable agent, so the project stays finishable at every step.

---

## Decisions already made

Don't swap these without asking the human.

| Area | Decision |
|---|---|
| LLM | **Anthropic API.** A key with a **monthly spend limit** (🧑). All calls go through one wrapper that logs tokens and cost. |
| Embeddings | **A small local multilingual model on CPU** (start with `intfloat/multilingual-e5-small`, 384 dimensions), checked on Khmer too. Fall back to an embedding API only if the local model fails on memory or quality (task 1.5). |
| Database | **PostgreSQL + pgvector on this server**, localhost only. Installing it is a 🧑 `sudo` step. |
| Scheduling | **The lab's self-hosted Prefect**: work pool `lab`, daily at **07:00 Asia/Phnom_Penh**. Not GitHub Actions, not cron. |
| Telegram | **Natalia's own new bot**, separate from the lab's alert bot. Long polling, run as a `systemd` service. |
| Website | **Personal, Tailscale-only.** No public URL, no tunnel, no domain. |
| Voice | **Later phase (4)**, via a speech API or a Modal GPU job. The server CPU is too small for Whisper. |
| Server | **2 vCPU / 4 GB RAM** + 4 GB swap, shared with cloud-ai-lab. Prefect already uses ~300 MB. |

### Memory budget (target, measured as each part is built)

| Part | Target | Notes |
|---|---|---|
| Prefect server + worker (lab) | ~300 MB | already running |
| PostgreSQL | ≤ 250 MB | small `shared_buffers`, few connections |
| Telegram bot service | ≤ 200 MB | idle most of the time |
| Website service | ≤ 250 MB | Phase 5 |
| Daily flow (collect + embed + summarize) | ≤ 700 MB peak | runs inside the lab worker's cgroup (`MemoryMax=900M`, shared with lab flows) |

The embedding model is the biggest risk: PyTorch alone can take several hundred MB. Task 1.5 measures it before anything depends on it.

---

## Stage 0 — Project setup

- [ ] **0.1 Project setup** — 🤖
  - 🤖 `CLAUDE.md` (hard rules from cloud-ai-lab, adapted), this roadmap, `docs/STATUS.md`, `.env.example`; check `.gitignore` covers `.env` and `.venv`. PLAN.md restored as Markdown.
  - **Done when:** the files are on branch `task/0.1-project-setup`, ready for review.

- [ ] **0.2 Python project and agent guardrails** — 🤖
  - 🤖 `uv init` (Python 3.12), package `natalia/`, `pytest` and `ruff` set up, one passing test.
  - 🤖 `.claude/settings.json` with `permissions.deny` rules like cloud-ai-lab's (`sudo`, push to main, force-push, `git merge`, `rm -rf`, reading `.env`, `prefect deployment run`).
  - **Done when:** `uv run pytest` passes and a denied command is blocked.

---

## Phase 1 — Daily digest

Goal: every morning at 07:00 the human gets a digest on Telegram: headline, link, detail, AI summary and "why it matters", for each topic.

- [ ] **1.1 Sources and feeds** — 🤖 + 🧑
  - 🤖 Find RSS/Atom feed URLs for the sources in PLAN.md, per topic. Fetch each once (free) and record: works / broken / paywalled / no feed. Write `config/sources.yaml` (topic, source, feed URL, language, paywalled).
  - 🧑 Review the list. Decide how to handle paywalled sources (Bloomberg, FT, WSJ, The Athletic): feed headline + excerpt + link only, or drop them.
  - **Done when:** every topic has at least 2 working feeds, and a script prints the 5 latest headlines per topic.

- [ ] **1.2 Database** — 🧑 + 🤖
  - 🤖 Write the exact install commands and a memory-tuned config (localhost only, small `shared_buffers`, low `max_connections`), plus the role and database setup.
  - 🧑 Install and configure (`sudo`):
    ```bash
    sudo apt install postgresql postgresql-16-pgvector   # PostgreSQL 16 + pgvector on Ubuntu 24.04
    ```
    then the role/database commands the agent wrote; put `DATABASE_URL` in `.env`.
  - 🤖 Schema and migrations: sources, articles (URL, title, text, topic, language, published), embeddings (`vector(384)`), summaries, digests. `CREATE EXTENSION vector` in a migration.
  - **Done when:** migrations run on the real database, tests pass against it, and PostgreSQL's memory is measured (`systemctl status postgresql`).

- [ ] **1.3 Collect and clean** — 🤖
  - 🤖 `feedparser` to read feeds, `trafilatura` to extract article text (skipped for paywalled sources). Deduplicate by canonical URL and normalized title. Polite fetching: timeouts, a user agent, no hammering.
  - **Done when:** running it twice stores the day's articles once each, with no duplicates, and failures on one feed don't stop the others.

- [ ] **1.4 Filter by topic** — 🤖
  - 🤖 Tag each article with topics: from its feed first, then simple rules (e.g. "Cambodia" for anything mentioning Cambodia, Phnom Penh, Khmer…). No LLM calls.
  - **Done when:** tests on sample articles pass, and a real run's topic counts look sensible to the human.

- [ ] **1.5 Embeddings: evaluate the local model** — 🤖 (🧑 picks)
  - 🤖 Measure `multilingual-e5-small` on this server's CPU: peak RAM, load time, seconds per 100 articles. Compare PyTorch (`sentence-transformers`) with an ONNX runtime if PyTorch is too heavy.
  - 🤖 Check quality on a small labeled set: English queries → English articles, Khmer queries → English articles, Khmer articles. Record the numbers in a short report.
  - 🧑 Pick: keep the local model, or (only if needed) an embedding API, which means 🧑 an account, a spend limit, and a key.
  - **Done when:** the choice is recorded with measured numbers, and the daily flow's peak stays inside the memory budget.

- [ ] **1.6 Anthropic API key** — 🧑
  - 🧑 Create an account at console.anthropic.com, **set a monthly spend limit**, create a key, add `ANTHROPIC_API_KEY` to `.env`.
  - **Done when:** the key is in `.env` (the agent doesn't test it without approval).

- [ ] **1.7 Summarize and explain** — 🤖 (🧑 runs it)
  - 🤖 LLM wrapper (logs tokens and cost per call; fake client for tests). Digest builder: for each topic, the top items, each with headline, link, detail, AI summary and "why it matters". The summary sits next to the source, never replaces it.
  - 🤖 Pick the model per job (cheap model for bulk summaries) and estimate the cost per day and per month at current prices.
  - 🧑 Approve and run one real digest (the agent writes the command and the cost estimate).
  - **Done when:** a real digest for today is stored, its cost is logged, and the human is happy with its quality.

- [ ] **1.8 Natalia's Telegram bot** — 🧑
  - 🧑 Create a **new** bot with @BotFather (not the lab's alert bot). Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_OWNER_CHAT_ID` to `.env`; send the bot `/start` once.
  - **Done when:** the token and chat ID are in `.env`.

- [ ] **1.9 Morning push on Prefect** — 🤖 + 🧑
  - 🤖 A Prefect flow `natalia-daily`: collect → filter → store → embed → summarize → send the digest to the owner's chat. Failures send a short message to the owner.
  - 🤖 A runtime worktree `~/projects/natalia-runtime` (like the lab's `lab-runtime`), so branch switches never change what runs. The deployment uses Natalia's own `.venv` through the process pool's `command` job variable; check that the lab's worker (Prefect 3.8.8) runs it that way.
  - 🧑 Register the deployment and its schedule (07:00 Asia/Phnom_Penh). The schedule spends money every day, so the human turns it on.
  - Watch for: the lab worker runs at most 2 flows at once, and paused lab GPU approvals hold slots. A paused run at 07:00 could delay the digest.
  - **Done when:** the digest arrives at 07:00 two mornings in a row, both runs are Completed in the Prefect UI, and peak memory is recorded.

- [ ] **1.10 Document Phase 1** — 🤖 → `docs/01-daily-digest.md`

---

## Phase 2 — Conversation

Goal: the Telegram bot answers commands, questions, and follow-ups, grounded in stored articles (RAG).

- [ ] **2.1 Bot as a service, with an allowlist** — 🤖 + 🧑
  - 🤖 `python-telegram-bot` with long polling. Only chat IDs in `TELEGRAM_ALLOWED_CHAT_IDS` get answers; everyone else gets a short refusal and costs nothing. `deploy/natalia-bot.service` (auto-restart, start on boot, `MemoryMax`).
  - 🧑 Add family and friends' chat IDs; install and start the service (`sudo`).
  - **Done when:** the bot answers `/start` for allowed users, ignores others, and survives `sudo reboot`.

- [ ] **2.2 Commands** — 🤖
  - 🤖 `/today`, one command per topic (`/economics`, `/crypto`, `/cambodia`, …), `/help`. They read stored digests: no LLM call.
  - **Done when:** every command returns today's items in the news format.

- [ ] **2.3 Questions (RAG)** — 🤖 (🧑 tests it)
  - 🤖 Retrieve with pgvector (plus keyword search if it helps), answer with the LLM using only retrieved articles, always with links. Say so when the news doesn't cover the question.
  - 🤖 Cost guard: a daily cap on LLM calls per user, and an estimated cost per answer.
  - 🧑 Ask it real questions (approve the API use).
  - **Done when:** answers cite real stored articles, and the cap works.

- [ ] **2.4 Real conversation and two spaces** — 🤖 + 🧑
  - 🤖 Memory: a rolling window of the last N messages per chat, stored in PostgreSQL. Two spaces with separate histories: **News** (long items) and **Conversation** (short dialogue), via Telegram group topics or a `/mode` toggle.
  - 🧑 Choose topics or a toggle; if topics, create the group and add the bot.
  - **Done when:** follow-up questions work, and the two spaces never mix histories.

- [ ] **2.5 Document Phase 2** — 🤖 → `docs/02-conversation.md`

---

## Phase 3 — Language toggle (English / Khmer, text)

Goal: one switch changes everything to Khmer: news, summaries, the human's input, and the agent's replies.

- [ ] **3.1 Language setting** — 🤖
  - 🤖 Per-user language (`/lang`, stored), passed to every output path. News is collected once in its original language; only the output is translated.
  - **Done when:** switching changes every reply's language.

- [ ] **3.2 Khmer output** — 🤖 (🧑 reviews)
  - 🤖 Summaries, explanations and answers written in Khmer by the LLM. Each day's digest is translated once per language and cached, not once per user. Khmer questions retrieve English articles (checked in 1.5).
  - 🤖 Update the cost estimate for the Khmer version.
  - 🧑 Read a week of Khmer digests and answers and judge their quality.
  - **Done when:** the human is happy with the Khmer quality, and the cost per day is recorded.

- [ ] **3.3 Document Phase 3** — 🤖 → `docs/03-language.md`

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

- [ ] **4.5 Document Phase 4** — 🤖 → `docs/04-voice.md`

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
  - 🤖 A Claude-like chat page on the same engine as the bot (RAG, memory, language).
  - **Done when:** a conversation on the site answers with links to real articles.

- [ ] **5.4 Polished version (React)** — 🤖 + 🧑, later
  - 🤖 Propose a small API (e.g. FastAPI) plus a React front end; 🧑 approves and installs Node if needed.
  - **Done when:** the React site does everything the quick version did.

- [ ] **5.5 Document Phase 5** — 🤖 → `docs/05-website.md`

---

## Done

Nothing yet.
