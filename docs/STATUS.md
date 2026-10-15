# Status

Live progress for agent work. The agent updates this after every step and pushes it (see "Working unattended" in [`CLAUDE.md`](../CLAUDE.md)). Task definitions live in [`ROADMAP.md`](ROADMAP.md).

## Summary

**Run of 2026-10-15 (fourth): 1.1 done (branch `task/1.1-sources`, from `origin/main` at 97a159f, where 0.2 is merged). Stopping here.** `config/sources.yaml` lists 85 feeds across the 9 topics: 74 enabled, 11 disabled with the reason (dead, broken XML, redirect duplicate). Every enabled feed returned items on 2026-10-15. Each topic has 4–13 working free feeds; Cambodia has 14 enabled (10 English, 1 of them paywalled; 4 Khmer). `uv run python -m natalia.feeds` checks every feed and prints the 5 latest headlines per topic. Added `feedparser` and `pyyaml`; 21 tests pass offline. Only plain HTTP GETs to public feeds and homepages: no Gemini call, no accounts, no sudo, no money spent.

**Human must:**
1. **1.1:** review the feed list (the table under 1.1 below), especially the choices in "Open questions". Then review and merge `task/1.1-sources` and tick 1.1 in ROADMAP.
2. The earlier steps below still stand (tick 0.2 and 1.6; the 0.2 deny-rule check; 1.2, 1.5, 1.7, 1.8, 1.9).

**Run of 2026-10-15 (third): 0.2 done (branch `task/0.2-python-setup`, from `origin/main` at 2669e55, where 0.1 is merged). Stopping here.** `uv` project on Python 3.12 with the package in `natalia/` (flat layout) and a `natalia/llm.py` stub, the only place `google-genai` may be imported (task 1.7 fills it in). `pytest` and `ruff` are the only packages added (dev group); `uv run pytest` passes 5 tests and `ruff` is clean. `.claude/settings.json` denies `sudo`, push to main, force-push, `git merge`, `rm -rf`, reading `.env`, `prefect deployment run`, plus Modal, destructive `rclone` and Prefect flow-run resume, like cloud-ai-lab. 🧑 1.6 is done (the human's report, recorded below). No Gemini call, nothing installed system-wide, no accounts, no money spent.

**Human must:**
1. **0.2:** check that a denied command is blocked (this session was started in cloud-ai-lab, so it can't load Natalia's settings; see the 0.2 entry for the exact check). Then review and merge `task/0.2-python-setup`.
2. Tick 0.1, 0.2 (once merged) and 1.6 in `docs/ROADMAP.md`.
3. Remaining Phase 1 🧑 steps: 1.1 review the feed list; 1.2 install PostgreSQL + pgvector (`sudo`) and add `DATABASE_URL`; 1.5 pick the embedding option; 1.7 approve one real digest; 1.8 create Natalia's own bot and add its token and chat ID; 1.9 register the daily deployment and turn on its schedule.

**Run of 2026-10-15 (second): decision change on 0.1, before merge (same branch `task/0.1-project-setup`). Stopping here.** The LLM is now **Google Gemini Flash on the free tier**, through the official `google-genai` SDK, key `GEMINI_API_KEY`, behind one thin wrapper `natalia/llm.py` so the provider can be swapped later. CLAUDE.md, ROADMAP.md, PLAN.md and `.env.example` were updated. New rules: never send private data to the LLM (the free tier may use prompts to improve Google's models; news is fine), and paywalled sources (Bloomberg, FT, WSJ, The Athletic) are headline + excerpt + link only, with free sources (Reuters, AP, BBC…) for full detail. Embeddings stay local on CPU. `docs/TASK-TEMPLATE.md` added. Nothing installed, no accounts created, no API called, no money spent.

**Human must:** review and merge `task/0.1-project-setup`. Then the 🧑 steps for Phase 1, in the order the tasks need them:
1. **1.1:** review the feed list the agent writes (paywalled sources are already decided: headline + excerpt + link only).
2. **1.2:** install PostgreSQL 16 + pgvector (`sudo apt install postgresql postgresql-16-pgvector`), run the role/database commands the agent writes, and put `DATABASE_URL` in `.env`.
3. **1.5:** pick the embedding option from the agent's measurements. An API account is needed only if the local model fails.
4. **1.6:** sign in at aistudio.google.com, create an API key, add `GEMINI_API_KEY` to `.env`. Free tier: no paid account, no billing, no spend limit. Don't attach billing to the key's project.
5. **1.7:** approve and run one real digest (the agent gives the command and the expected request count).
6. **1.8:** create a **new** bot with @BotFather (not the lab's alert bot), add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_OWNER_CHAT_ID` to `.env`, and send the bot `/start`.
7. **1.9:** register the `natalia-daily` deployment and turn on its 07:00 Asia/Phnom_Penh schedule (it calls Gemini every day).

`.env` setup, once: `cp .env.example .env && chmod 600 .env`, then fill in the values as each step above produces them.

*(Superseded by the run above: the LLM was Anthropic in this first run.)* **Run of 2026-10-15 (first): 0.1 done (branch `task/0.1-project-setup`, from `origin/main` at 2dca67b). Stopping here.** `docs/PLAN.md` is clean Markdown (wording unchanged). `CLAUDE.md` has the cloud-ai-lab hard rules adapted to Natalia, plus two new ones: leave cloud-ai-lab alone, and message only the human. `docs/ROADMAP.md` turns the plan's 5 build phases into tasks 1.1–5.5, with the agreed decisions and a memory budget. `.env.example` added; `.gitignore` already covered `.env` and `.venv`. Nothing installed, no accounts created, no paid API called, no money spent.

---

<!-- Template for each task:

## <id> — <title>
- **Branch:** `task/<id>-<short-name>`
- **State:** in progress / done / blocked
- **Done:** <what's finished>
- **Next:** <the next step>
- **Human must:** <exact commands, keys, approvals, or costs; "nothing" if none>

-->

## 0.1 — Project setup
- **Branch:** `task/0.1-project-setup`
- **State:** done, merged to `main` (PR #1, 2669e55)
- **Done:** `docs/PLAN.md` restored as Markdown; `CLAUDE.md`, `docs/ROADMAP.md`, `docs/STATUS.md`, `docs/TASK-TEMPLATE.md`, `.env.example` written; `.gitignore` checked. Decision change applied before merge: LLM is Gemini Flash (free tier), not Anthropic.
- **Next:** 0.2 (Python project and agent guardrails), then Phase 1.
- **Human must:** tick 0.1 in ROADMAP.

<details><summary>Steps and output from this build</summary>

**1. Restore `docs/PLAN.md` as Markdown.** Headings, numbered lists and bullets added; wording unchanged. Check: with the Markdown markers stripped, the file has the same 84 text lines as the pasted version, and the curly quotes are intact.
```console
$ sed -E 's/^(#+ |- |[0-9]+\. )//' docs/PLAN.md | grep -v '^$' | wc -l
84
```
**Result:** ✅

**2. Branch from `origin/main`.** Nothing had been committed on local `main` (PLAN.md was untracked), so no commit needed moving and `main` needed no reset.
```console
$ git log --oneline main..origin/main; git log --oneline origin/main..main
(no output: main and origin/main are both at 2dca67b)
$ git switch -c task/0.1-project-setup origin/main
Switched to a new branch 'task/0.1-project-setup'
branch 'task/0.1-project-setup' set up to track 'origin/main'.
```
**Result:** ✅

**3. Check `.gitignore`.** It is GitHub's Python template and already ignores both; `.env.example` is not ignored.
```console
$ git check-ignore -v .env .venv .env.example
.gitignore:153:.env	.env
.gitignore:155:.venv	.venv
```
**Result:** ✅ no change needed.

**4. Facts about the shared server, used in ROADMAP.md** (read-only checks):
```console
$ free -m
               total        used        free      shared  buff/cache   available
Mem:            3814        1119        2115           4         816        2695
Swap:           4095           0        4095
$ nproc
2
$ which psql pg_config ffmpeg
(no output: PostgreSQL and ffmpeg are not installed)
$ ~/projects/lab-runtime/.venv/bin/prefect version
Version:              3.8.8
$ prefect work-pool inspect lab   # job variables of the process pool
'command'  'env'  'working_dir'
$ grep VERSION= /etc/os-release; timedatectl | grep 'Time zone'
VERSION="24.04.5 LTS (Noble Numbat)"
                Time zone: Etc/UTC (UTC, +0000)
```
**Result:** ✅ Ubuntu 24.04 → PostgreSQL 16 and `postgresql-16-pgvector` from apt. The lab's process pool accepts a `command` job variable, so Natalia's deployment can use its own `.venv` (to verify in task 1.9). The server clock is UTC, so schedules must name `Asia/Phnom_Penh`.

**5. Commit and push**
```console
$ git commit -m "Task 0.1: project setup (CLAUDE.md, roadmap, status, .env.example)"
$ git log --oneline -2
970304d Task 0.1: project setup (CLAUDE.md, roadmap, status, .env.example)
2dca67b Initial commit
$ git push -u origin task/0.1-project-setup
To github.com:thovicheka/natalia.git
 * [new branch]      task/0.1-project-setup -> task/0.1-project-setup
branch 'task/0.1-project-setup' set up to track 'origin/task/0.1-project-setup'.
```
**Result:** ✅

**6. Decision change: Gemini instead of Anthropic.** Edited CLAUDE.md (hard rule 4, new rule 10 on private data, conventions for the LLM wrapper, paywalls and embeddings), ROADMAP.md (decisions table, a privacy-and-limits note, tasks 1.1, 1.3, 1.6, 1.7, 1.9, 2.1, 2.3, 3.2, 5.3), PLAN.md (paywall note under sources; tech-stack LLM and embeddings lines), `.env.example` (`GEMINI_API_KEY` replaces `ANTHROPIC_API_KEY`). Added `docs/TASK-TEMPLATE.md`. Check for leftovers:
```console
$ grep -rn -i anthropic CLAUDE.md docs/ROADMAP.md docs/PLAN.md .env.example docs/TASK-TEMPLATE.md
(no output)
$ git commit -m "Switch LLM to Gemini free tier; paywall rule; task template"
$ git log --oneline -1
0249f53 Switch LLM to Gemini free tier; paywall rule; task template
$ git push
   b91b54b..0249f53  task/0.1-project-setup -> task/0.1-project-setup
```
**Result:** ✅
</details>

**Noticed, not done (out of scope):**
- The lab worker's 2 flow slots and `MemoryMax=900M` are shared with lab flows. A paused lab GPU approval at 07:00 could delay the digest, and a heavy embedding step could hit the memory cap. Both are flagged in ROADMAP 1.5 and 1.9; changing the worker is the lab's business, not Natalia's.
- ~~Several PLAN.md sources are paywalled, so "full detail" isn't possible for them.~~ Decided: headline + excerpt + link only.
- PLAN.md's tech stack still says "Scheduling: GitHub Actions or cron", but the decision is the lab's Prefect. Left as is, since the plan's wording is yours; worth a one-line edit.
- What family and friends type to the bot goes to Gemini's free tier, which may use it to improve Google's models. ROADMAP 2.1 and 5.3 add a notice on `/start` and the chat page; if that's not enough, a paid Gemini tier (which doesn't train on prompts) is the alternative.
- ~~The repo has no `.claude/settings.json` deny rules yet; that's task 0.2.~~ Done in 0.2.

## 0.2 — Python project and agent guardrails
- **Branch:** `task/0.2-python-setup`
- **State:** done, committed and pushed; waiting for the human's check, review and merge
- **Done:** `uv` project (Python 3.12, `.python-version`, `uv.lock`); package `natalia/` with `__init__.py` and a `llm.py` stub (`generate()` raises `NotImplementedError` until 1.7; no SDK yet); dev group `pytest` + `ruff` (lint rules E, F, W, I, B, UP; line length 100); `tests/` with 5 passing tests; `.claude/settings.json` deny rules.
- **Next:** Phase 1, task 1.1 (sources and feeds).
- **Human must:** run the denied-command check below (2 minutes, free), then review and merge.

**Check that a denied command is blocked.** This agent session was started in `~/projects/cloud-ai-lab`, so Claude Code loaded that repo's settings, not Natalia's; a block seen here would prove nothing about Natalia's file. Run it from a session started in Natalia:
```bash
cd ~/projects/natalia && claude
# then ask it:  run `git merge --help`  and  read the file .env
```
Expected: both are refused with a permission-denied message (rules `Bash(git merge:*)` and `Read(./.env)`). Also check `/permissions` lists the deny rules from `.claude/settings.json`.

<details><summary>Steps and output from this build</summary>

**1. Branch from `origin/main`.** 0.1 was merged (PR #1).
```console
$ git fetch origin && git log --oneline -1 origin/main
2669e55 Merge pull request #1 from thovicheka/task/0.1-project-setup
$ git switch -c task/0.2-python-setup origin/main
Switched to a new branch 'task/0.2-python-setup'
```
**Result:** ✅

**2. `uv init`.**
```console
$ uv --version
uv 0.13.0 (x86_64-unknown-linux-gnu)
$ uv init --app --python 3.12 --name natalia --vcs none
Initialized project `natalia`
```
**Result:** ✅ with two fixes. uv 0.13 made a packaged `src/natalia/` layout with a demo `main()` script, and wrote the git author's email into `authors`. **Fix:** moved the package to `natalia/` (the path CLAUDE.md names), set `[tool.uv.build-backend] module-root = ""`, removed the demo script entry and `authors`. The package is installed editable in `.venv`, so `import natalia` works from any directory (useful for the Prefect flow in 1.9).

**3. Dev tools.** Only the two packages 0.2 needs; no runtime dependencies yet.
```console
$ uv add --dev pytest ruff
 + natalia==0.1.0 (from file:///home/thovicheka/projects/natalia)
 + pytest==9.1.1
 + ruff==0.17.0
```
**Result:** ✅

**4. Tests and lint.** Tests: package imports; the `llm.py` stub raises `NotImplementedError`; the required deny rules are in `.claude/settings.json`; `.env` and `.venv` are git-ignored; no module but `natalia/llm.py` imports `google-genai`.
```console
$ uv run pytest -v
tests/test_guardrails.py::test_settings_deny_rules PASSED                [ 20%]
tests/test_guardrails.py::test_env_is_git_ignored PASSED                 [ 40%]
tests/test_guardrails.py::test_only_llm_wrapper_imports_genai PASSED     [ 60%]
tests/test_package.py::test_package_imports PASSED                       [ 80%]
tests/test_package.py::test_llm_stub_is_not_implemented_yet PASSED       [100%]
============================== 5 passed in 0.01s ===============================
$ uv run ruff check . ; uv run ruff format --check .
All checks passed!
10 files already formatted
```
**Result:** ✅

**5. `.claude/settings.json`.** cloud-ai-lab's deny list, adapted: `sudo`, `su`; push to `main` (also `HEAD:main`), `--force`, `-f`, `--force-with-lease`; `git merge`; `git reset --hard`; `rm -rf`; `Read` and `cat` of `.env`; `modal run/deploy/serve` (Phase 4 may use Modal; never spend money); `rclone delete/deletefile/purge/sync` (the server's R2 data is the lab's); `prefect deployment run` and `prefect flow-run resume` in every form, including the API paths. Lab-only paths (`~/projects/lab-runtime/.venv/bin/prefect …`) are covered by the `*prefect deployment run*` wildcards.
```console
$ uv run python -c "import json;json.load(open('.claude/settings.json'));print('settings.json: valid JSON')"
settings.json: valid JSON
```
**Result:** ✅ file valid and checked by a test. ⏳ The live "denied command is blocked" check is the human's (see above).

**6. Commit and push**
```console
$ git commit -m "Task 0.2: uv project (Python 3.12), natalia package with llm.py stub, pytest + ruff, agent deny rules"
$ git log --oneline -1
bcaf33c Task 0.2: uv project (Python 3.12), natalia package with llm.py stub, pytest + ruff, agent deny rules
$ git push -u origin task/0.2-python-setup
 * [new branch]      task/0.2-python-setup -> task/0.2-python-setup
```
**Result:** ✅
</details>

## 1.6 — Gemini API key
- **Branch:** none (🧑 step)
- **State:** done (reported by the human on 2026-10-15)
- **Done:** `GEMINI_API_KEY` is in `.env`. The human verified it with a model-list request (`GET /v1beta/models`), which returned the model list including `gemini-2.5-flash`. That request lists models only; it generates nothing and uses no generation quota. The agent did not read `.env` or call the API.
- **Next:** 1.7 uses the key (the agent picks the current Flash model then).
- **Human must:** tick 1.6 in ROADMAP. Keep billing off the key's Google project.

## 1.1 — Sources and feeds
- **Branch:** `task/1.1-sources`
- **State:** done, committed and pushed; waiting for the human's review and merge
- **Done:** `config/sources.yaml` (85 feeds: name, topic, url, language, paywalled, enabled, note); `natalia/feeds.py` (load + validate the list, check each feed with one GET, print the 5 latest headlines per topic); `tests/test_feeds.py` (list is valid, every topic has ≥2 enabled free feeds, known paywalled sources are flagged, disabled feeds say why, checker parses RSS and never raises; no network). Runtime deps `feedparser` 6.0.14 and `pyyaml` 6.0.3.
- **Next:** 1.2 (database) needs 🧑 `sudo`; 1.3 (collect) can start from this list.
- **Human must:** review the list below and the open questions; merge.

### Feed check results (2026-10-15, ~07:40 UTC)

✅ works · ⚠️ works but no item in the last 14 days · ❌ broken/dead · ➖ responds but disabled (duplicate or wrong). Paywalled = headline + excerpt + link only. GN = via a Google News search feed (the source has no public RSS).

| Topic | Source | Lang | Working? | Paywalled? | Enabled | Items | Note |
|---|---|---|---|---|---|---|---|
| economics | BBC News Business | en | ✅ | no | yes | 42 | |
| economics | The Guardian Economics | en | ✅ | no | yes | 20 | |
| economics | CNBC Economy | en | ✅ | no | yes | 30 | |
| economics | NPR Economy | en | ✅ | no | yes | 10 | |
| economics | Reuters Business (GN) | en | ✅ | no | yes | 97 | |
| economics | Bloomberg Economics | en | ✅ | yes | yes | 20 | |
| economics | Financial Times Global Economy | en | ✅ | yes | yes | 25 | |
| economics | WSJ Economy | en | ✅ | yes | yes | 36 | |
| economics | The Economist Finance & Economics | en | ✅ | yes | yes | 300 | metered |
| world-politics | BBC News World | en | ✅ | no | yes | 29 | |
| world-politics | Al Jazeera | en | ✅ | no | yes | 25 | all of Al Jazeera, not only politics |
| world-politics | The Guardian World | en | ✅ | no | yes | 45 | |
| world-politics | NPR World | en | ✅ | no | yes | 10 | |
| world-politics | DW World | en | ✅ | no | yes | 13 | |
| world-politics | France 24 | en | ✅ | no | yes | 24 | |
| world-politics | Reuters World (GN) | en | ✅ | no | yes | 100 | |
| world-politics | AP World (GN) | en | ✅ | no | yes | 100 | |
| world-politics | Foreign Affairs | en | ✅ | yes | yes | 20 | metered |
| technology | Ars Technica | en | ✅ | no | yes | 20 | |
| technology | The Verge | en | ✅ | no | yes | 10 | |
| technology | TechCrunch | en | ✅ | no | yes | 20 | |
| technology | BBC News Technology | en | ✅ | no | yes | 21 | |
| technology | Wired | en | ✅ | yes | yes | 50 | metered; many coupon posts |
| technology | MIT Technology Review | en | ✅ | yes | yes | 10 | metered |
| science | ScienceDaily | en | ✅ | no | yes | 60 | |
| science | Quanta Magazine | en | ✅ | no | yes | 5 | `/quanta/feed/` (from the homepage) had 1 item from 2013; `/feed/` is current |
| science | BBC News Science | en | ✅ | no | yes | 42 | |
| science | The Guardian Science | en | ✅ | no | yes | 28 | |
| science | Phys.org | en | ✅ | no | yes | 30 | |
| science | NASA News Releases | en | ✅ | no | yes | 10 | |
| science | Nature | en | ✅ | yes | yes | 75 | papers often paywalled |
| science | Scientific American | en | ✅ | yes | yes | 50 | metered |
| science | New Scientist | en | ✅ | yes | yes | 10 | metered |
| sport | BBC Sport | en | ✅ | no | yes | 67 | |
| sport | ESPN | en | ✅ | no | yes | 38 | |
| sport | Sky Sports | en | ✅ | no | yes | 20 | |
| sport | The Guardian Sport | en | ✅ | no | yes | 48 | |
| sport | The Athletic | en | ✅ | yes | yes | 100 | |
| crypto | CoinDesk | en | ✅ | no | yes | 25 | |
| crypto | Cointelegraph | en | ✅ | no | yes | 30 | |
| crypto | Decrypt | en | ✅ | no | yes | 35 | |
| crypto | The Block | en | ✅ | no | yes | 19 | homepage 403s, feed works |
| crypto | Bitcoin Magazine | en | ✅ | no | yes | 10 | |
| crypto | Bloomberg Crypto | en | ✅ | yes | yes | 2 | |
| markets | CNBC Markets | en | ✅ | no | yes | 30 | |
| markets | Reuters Markets (GN) | en | ✅ | no | yes | 100 | |
| markets | FXStreet News | en | ✅ | no | yes | 30 | forex |
| markets | ForexLive | en | ✅ | no | yes | 25 | forex |
| markets | Investing.com News | en | ✅ | no | yes | 10 | |
| markets | MarketWatch Top Stories | en | ✅ | yes | yes | 10 | Dow Jones, metered |
| markets | Bloomberg Markets | en | ✅ | yes | yes | 20 | |
| markets | WSJ Markets | en | ✅ | yes | yes | 61 | |
| markets | Financial Times Markets | en | ✅ | yes | yes | 25 | |
| markets | Yahoo Finance | en | ❌ | no | no | 0 | HTTP 404 (3 URLs tried) |
| cambodia | Khmer Times | en | ✅ | no | yes | 20 | |
| cambodia | Phnom Penh Post | en | ✅ | no | yes | 10 | |
| cambodia | CamboJA News | en | ✅ | no | yes | 10 | |
| cambodia | The Cambodia Daily | en | ✅ | no | yes | 20 | irregular (latest was 09-08 on the first check) |
| cambodia | Cambodia Investment Review | en | ✅ | no | yes | 10 | |
| cambodia | VOD English | en | ⚠️ | no | yes | 10 | latest item 2026-08-09 |
| cambodia | The Guardian Cambodia | en | ⚠️ | no | yes | 20 | tag feed, a few items a month (latest 09-29) |
| cambodia | Reuters Cambodia (GN) | en | ✅ | no | yes | 100 | |
| cambodia | Google News Cambodia | en | ✅ | no | yes | 100 | aggregator, any outlet |
| cambodia | Nikkei Asia Cambodia (GN) | en | ✅ | yes | yes | 100 | |
| cambodia | Post Khmer | km | ✅ | no | yes | 10 | |
| cambodia | Kohsantepheap Daily | km | ✅ | no | yes | 1 | only 1 item per fetch |
| cambodia | DAP News | km | ✅ | no | yes | 10 | |
| cambodia | RFA Khmer | km | ✅ | no | yes | 27 | latest 10-11 |
| cambodia | The Diplomat Cambodia | en | ⚠️ | no | no | 96 | latest item 2026-05-27 |
| cambodia | VOA Khmer | km | ⚠️ | no | no | 20 | stopped 2025-03-31 |
| cambodia | Cambodianess | en | ❌ | no | no | 0 | no feed (404 on /feed, /rss, /rss.xml) |
| cambodia | Kiripost | en | ❌ | no | no | 0 | malformed XML |
| cambodia | Fresh News English | en | ❌ | no | no | 0 | malformed XML |
| cambodia | Fresh News Khmer | km | ❌ | no | no | 0 | HTTP 403 |
| cambodia | Thmey Thmey | km | ❌ | no | no | 0 | no feed (404) |
| cambodia | CamboJA News Khmer | km | ❌ | no | no | 0 | `/kh/feed/` and `/km/feed/` empty |
| cambodia | Khmer Times Khmer | km | ➖ | no | no | 20 | `/kh/feed/` redirects to the English feed |
| cambodia | Google News Khmer | km | ➖ | no | no | 38 | `hl=km` redirects to US English top stories |
| general | BBC News Top Stories | en | ✅ | no | yes | 34 | |
| general | NPR News | en | ✅ | no | yes | 10 | |
| general | The Guardian International | en | ✅ | no | yes | 115 | includes lifestyle and reviews |
| general | Sky News World | en | ✅ | no | yes | 8 | |
| general | AP Top News (GN) | en | ✅ | no | yes | 100 | |
| general | Reuters (GN) | en | ✅ | no | yes | 100 | |
| general | Google News Top Stories | en | ✅ | no | yes | 38 | US edition |

**Working free feeds per topic (enabled):** economics 5 · world-politics 8 · technology 4 · science 6 · sport 4 · crypto 5 · markets 5 · cambodia 13 · general 7.

### Open questions for the human
1. **Reuters and AP have no public RSS.** They come through Google News search feeds, whose links are `news.google.com/rss/articles/…` redirects. Task 1.3 must resolve them to the real URL before extracting text, and Reuters blocks non-browser clients (its homepage returned HTTP 401 here), so Reuters full text may not be fetchable. If that fails, Reuters/AP stay as headline + Google link only.
2. **Metered paywalls:** besides the four decided ones, I marked The Economist, Foreign Affairs, Wired, MIT Technology Review, Nature, Scientific American, New Scientist, MarketWatch and Nikkei Asia as `paywalled: true` (headline + excerpt + link). Flip any you'd rather treat as free.
3. **No Khmer Google News edition**, and Cambodianess, Thmey Thmey, Fresh News and CamboJA Khmer have no usable feed. Fresh News (403) and Kiripost (broken XML) might work through scraping their pages in 1.3; that's a scraping decision, not a feed one.
4. **VOD English and The Guardian Cambodia** are kept enabled though quiet (⚠️). Cheap to keep; the collector deduplicates.

<details><summary>Steps and output from this build</summary>

**1. Branch from `origin/main`.** 0.2 was merged (PR #2).
```console
$ git fetch origin && git log --oneline -1 origin/main
97a159f Merge pull request #2 from thovicheka/task/0.2-python-setup
$ git switch -c task/1.1-sources origin/main
Switched to a new branch 'task/1.1-sources'
```
**Result:** ✅

**2. Dependencies.** `feedparser` (named in PLAN.md, used again in 1.3) and `pyyaml` for the config.
```console
$ uv add feedparser pyyaml
 + feedparser==6.0.14
 + feedparser-sgmllib==2.1.0
 + pyyaml==6.0.3
```
**Result:** ✅

**3. Find feed URLs.** A throwaway script fetched 33 homepages and printed their `<link rel="alternate" type="application/rss+xml">` tags (one GET each).
```console
https://www.khmertimeskh.com/ [200] -> ['https://www.khmertimeskh.com/feed/', ...]
https://www.phnompenhpost.com/ [200] -> ['https://phnompenhpost.com/feed/', ...]
https://cambodianess.com/ [200] -> []
https://www.postkhmer.com/ [200] -> ['https://postkhmer.com/feed', ...]
https://www.freshnewsasia.com/ ERROR HTTPError: HTTP Error 403: Forbidden
https://www.quantamagazine.org/ [200] -> ['https://www.quantamagazine.org/quanta/feed/']
https://apnews.com/ ERROR HTTPError: HTTP Error 403: Forbidden
https://www.reuters.com/ ERROR HTTPError: HTTP Error 401: HTTP Forbidden
(…25 more)
```
**Result:** ✅ Most Cambodian sites are WordPress with `/feed/`. AP and Reuters block plain clients and publish no RSS.

**4. First check of 85 candidate feeds** (`uv run python -m natalia.feeds -n 0`): `78/85 feeds working`. Suspicious results: Quanta had 1 item from 2013; "Google News Khmer" and "Google News Top Stories" had identical counts and dates; "Khmer Times Khmer" matched "Khmer Times".
**Result:** ⚠️ needed a closer look.

**5. Closer look** (feed title, final URL after redirects, first items):
```console
https://news.google.com/rss?hl=km&gl=KH&ceid=KH:km
  [200] final=https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en items=38 title='Top stories - Google News'
https://www.khmertimeskh.com/kh/feed/
  [200] final=https://www.khmertimeskh.com/feed/ items=20 title='Khmer Times'
https://api.quantamagazine.org/feed/
  [200] final=https://www.quantamagazine.org/feed/ items=5 title='Quanta Magazine'
https://www.rfa.org/arc/outboundfeeds/khmer/rss/
  [200] items=27 title='ខ្មែរ' lang=km
https://finance.yahoo.com/rss/topstories    ERROR HTTPError: HTTP Error 404: Not Found
https://cambodianess.com/rss                ERROR HTTPError: HTTP Error 404: Not Found
https://thmeythmey.com/rss                  ERROR HTTPError: HTTP Error 404: Not Found
https://cambojanews.com/km/feed/
  [200] items=0 title='Comments on:'
```
**Result:** ❌ → fixed. **Error:** wrong or duplicate feeds counted as working. **Cause:** Google News has no Khmer edition and silently redirects; Khmer Times' `/kh/feed/` redirects to the English feed; Quanta's advertised feed URL is stale. **Fix:** Quanta URL changed to `/feed/`; the two redirects and the 9 dead/broken feeds set `enabled: false` with a `note`; Google News feeds got a note about redirect links; MarketWatch marked paywalled.

**6. Tests and lint.**
```console
$ uv run pytest -q
21 passed in 0.26s
$ uv run ruff check . ; uv run ruff format --check .
All checks passed!
12 files already formatted
```
**Result:** ✅

**7. Final check, all feeds, with headlines** (`uv run python -m natalia.feeds --all`, exit 0: every enabled feed works). Table above. Headlines (trimmed to 2 topics):
```console
78/85 feeds working

## crypto
  10-15 07:23  [Cointelegraph] Bitcoin ETFs shed $261M as XRP funds buck weekly outflow trend
  10-15 06:17  [CoinDesk] BlackRock's Fink names a U.S. recession trigger, sounds alarm over $40 trillion national debt
  10-15 05:52  [Cointelegraph] South Korea plans cybersecurity overhaul after attacks hit banks, crypto firms
  10-15 05:49  [Cointelegraph] Here’s what happened in crypto today
  10-15 05:00  [Cointelegraph] Australia seeks feedback on crypto platform rules ahead of 2027 rollout

## cambodia
  10-15 07:40  [The Cambodia Daily] Cambodian unions criticise $2 rise in garment workers’ minimum wage
  10-15 07:33  [Google News Cambodia] CITES reports minimal progress by Cambodia in controlling macaque exports — Mongabay - UA.NEWS
  10-15 07:17  [Google News Cambodia] China’s Military Expansion in Southeast Asia Masks a More Complicated Reality - War on the Rocks
  10-15 06:38  [DAP News] ស្ថានីយ៍ទូរទស្សន៍ Town Full HDTV ស្ថាប័ន FIGHT CLUBBING របស់អ៊ីតាលី រៀបចំព្រឹត្តិការណ៍កម្រិតអន្តរជាត
  10-15 06:26  [Google News Cambodia] Viet Nam-Cambodia trade expo promotes bilateral economic cooperation - Nhan Dan Online
```
"78/85" counts the two disabled redirect duplicates as responding; 74/74 enabled feeds work.
**Result:** ✅
</details>

**Noticed, not done (out of scope):**
- Wired's feed is mostly coupon posts ("Lenovo Coupon Codes…") and The Guardian International mixes in reviews and lifestyle. Topic filtering (1.4) should drop these, or the feeds can be swapped for narrower ones.
- The same story shows up in several topics (e.g. BBC "Anthropic flags revenue surge" in economics, world-politics and technology), because BBC repeats items across section feeds. Deduplication in 1.3 handles it.
- Several feeds run many requests to `news.google.com` (10 GN feeds). Fine once a day; worth a polite delay in 1.3.
- The 0.2 note says this kind of session started in cloud-ai-lab loads cloud-ai-lab's settings, not Natalia's deny rules. That was true again for this run.
