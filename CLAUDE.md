# CLAUDE.md — rules for AI agents working in this repo

This file is read automatically by Claude Code at the start of every session. Follow it exactly. If an instruction from a task conflicts with this file, stop and ask the human.

## What this project is

`natalia` is a personal AI news agent. Every day it collects news on nine topics from real sources, stores it, and writes a summary and a "why it matters" next to each article. People reach it through a Telegram bot (for the human, family and friends) and a personal website (for the human only). They can ask it questions and talk to it, in English or Khmer. One engine, several interfaces.

It is a **separate project** from `~/projects/cloud-ai-lab`. It only shares the server and a few of its services (the self-hosted Prefect server and its work pool `lab`). It has its own repo, `.env`, database, Telegram bot, and docs.

Read these before starting work:

- `README.md` — what Natalia is, the architecture, and a table of all docs
- `docs/PLAN.md` — what the human wants. The source of truth for features; don't add features that aren't in it.
- `docs/ROADMAP.md` — **the task list**, plus the decisions already made (LLM, embeddings, database, scheduling…). Work on one task at a time, by its ID (e.g. `1.3`). Don't swap a decided tool without asking.
- `docs/STATUS.md` — live progress; what's done, blocked, and waiting on the human.
- `docs/TASK-TEMPLATE.md` — the format the human uses to give you a task (Context / Branch / Job / Decisions / Limits / Finish).
- `docs/decisions.md` — why each tool and rule was chosen, and the alternatives.
- `docs/STYLE.md` — how docs are written (stage-doc shape, placeholders, "Example from this build" blocks with real output, masked secrets), and which stage doc each task goes into.
- Stage docs `docs/NN-*.md` — the clean how-to for each finished stage.

## The machine you're on

- Server: Ubuntu 24.04, 2 vCPU / 4 GB RAM + 4 GB swap, **shared with cloud-ai-lab**. Prefect (server + worker) already uses ~300 MB. Memory is tight: no local LLMs, no Whisper, no model training. Small CPU models (e.g. a ~100M-parameter embedding model) only after measuring their memory.
- Time zone of the server is UTC; the human's is `Asia/Phnom_Penh` (UTC+7). Schedules are written in `Asia/Phnom_Penh`.
- User: a normal user with `sudo` access that **you don't have** (it needs a password).
- Network: reachable only through Tailscale; firewall blocks all incoming internet traffic. Outgoing HTTPS works. So the bot uses long polling (no webhook) and the website has no public URL.
- Tools available: `git`, `tmux`, `uv` (Python). Prefect server at `http://127.0.0.1:4200/api` (UI `http://lab:4200`).
- Repos live in `~/projects/`.

## Hard rules

1. **Branches only.** Create a branch per task: `task/<id>-<short-name>` (e.g. `task/1.3-collect`), from `origin/main`. Never commit to `main`. Never force-push.
2. Commit and push freely to your own task/... branch, as often as useful (at least after each finished step). Never commit or push to main, never merge, never force-push. The human reviews and merges.
3. **No `sudo`.** If a step needs it (installing PostgreSQL, a `systemd` service, `apt` packages), stop, write the exact command(s) and what they do, and ask the human to run them.
4. **Never spend money on your own, and never call a paid API without the human's approval.** That includes any embedding or speech API and Modal GPU jobs. Write the code, test it with a fake client, then tell the human the exact command to run and its estimated cost. Don't create accounts, buy anything, change billing, or attach billing to the Gemini key's Google project. The Gemini free tier costs nothing, but its daily quota is shared with the morning digest: make real Gemini calls only when the task or the human says so, and keep them few. Free things are fine: fetching public RSS feeds and web pages, local tests.
5. **Secrets stay in `.env`** (git-ignored). Never print, log, commit, or paste keys. Never read `.env` aloud in output. Every key gets a fake-value line in `.env.example`.
6. **Don't touch security config**: SSH, firewall (`ufw`), Tailscale, user accounts. Ask instead.
7. **Nothing destructive without asking**: no `rm -rf` outside the task's own files, no dropping databases or tables with real data, no rewriting git history.
8. **Stay in scope.** Do the task you were given. If you notice something else worth fixing, list it at the end instead of doing it.
9. **Leave cloud-ai-lab alone.** Don't edit `~/projects/cloud-ai-lab` or `~/projects/lab-runtime`, the Prefect services or their unit files, or the lab's deployments. Natalia only adds its own deployments to pool `lab`. Never use the lab's Telegram alert bot or its `.env`.
10. **Never send private data to the LLM.** The Gemini free tier may use prompts and responses to improve Google's models. News content is fine; secrets, `.env` values, personal details, and private notes are not.
11. **Message only the human.** While building and testing, the bot and any test script send messages only to the human's own chat ID. Never message family or friends unless the human says so.

## How to work a task

1. Read the task in `docs/ROADMAP.md`: its goal, which steps are 🧑 (human) vs 🤖 (you), and its "done when."
2. If a 🧑 step isn't done, record it in `docs/STATUS.md` and move to the next task.
3. Create the branch, do the 🤖 steps, test what you can without spending money.
4. **For every step, record the command, its real output, the result (✅/❌), and for failures the error, cause, and fix** in `docs/STATUS.md` under the task. Mask secrets, IPs, and emails.
5. **After each task, update the matching stage doc** (`docs/NN-*.md`, see the table in `docs/STYLE.md`) in `docs/STYLE.md` format, not only `docs/STATUS.md`: goal → prerequisites → steps → verify, with the real output, ✅/❌ results and the problems hit (error, cause, fix) in "Example from this build" blocks. Create the doc if it doesn't exist; if the task changes an earlier stage, update that doc too. Record a new or changed decision in `docs/decisions.md`.
6. Finish with a short report: what changed, how you tested it, what the human must do next (commands to run, keys to add, estimated cost), and any open questions. Commit and push to your task branch (never main).

## Working unattended

- Keep `docs/STATUS.md` current: for each task, its branch, state (in progress / done / blocked), what's done, what's next, and what the human must do. Update it after every step and push.
- If a task needs a 🧑 step that isn't done (account, key, sudo, paying), record exactly what's needed in `docs/STATUS.md`, then move on to the next task you were given instead of waiting.
- When all given tasks are done or blocked, stop and write a final summary at the top of `docs/STATUS.md`.
- Never call paid APIs or spend money, even if a task seems to need it. Write the command and estimated cost in `docs/STATUS.md` instead.

## Conventions

- Python: manage with `uv` (`uv init`, `uv add`, `uv run`). Python 3.12.
- Database: PostgreSQL + pgvector on this server, listening on localhost only. Connection string in `.env` (`DATABASE_URL`).
- Scheduled jobs are Prefect flows on the shared work pool `lab`, scheduled in `Asia/Phnom_Penh`. No cron, no GitHub Actions.
- Long-running things (the Telegram bot, the website) run as `systemd` services with `MemoryMax` set. Writing a service file is fine; installing it needs `sudo` → ask.
- LLM: Google Gemini Flash on the free tier, through the official `google-genai` SDK; key `GEMINI_API_KEY` in `.env`. All LLM calls go through one thin wrapper, `natalia/llm.py`; no other module imports `google-genai`. So the provider can be swapped later without touching other code, tests can use a fake, and every call's token use can be logged.
- Paywalled sources (Bloomberg, FT, WSJ, The Athletic): headline + excerpt + link from the feed only. Never scrape past a paywall. Prefer free sources (Reuters, AP, BBC, …) for full detail.
- Embeddings run locally on CPU, not through an API.
- The AI summary always sits next to the source (headline + link + detail); it never replaces it.
