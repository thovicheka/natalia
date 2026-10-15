# Status

Live progress for agent work. The agent updates this after every step and pushes it (see "Working unattended" in [`CLAUDE.md`](../CLAUDE.md)). Task definitions live in [`ROADMAP.md`](ROADMAP.md).

## Summary

**Run of 2026-10-15 (ninth): 1.3 headline fix (same branch `task/1.3-collect`). Stopping here.** Near-identical headlines now merge only across different sites (the article's host without `www.`); exact matches always merge. Tests added for the two real wrong merges (Wired movies/TV shows, The Athletic Oct 14/15 puzzle hints: same site → kept apart) and a real cross-source pair (BBC/Guardian Eritreans story → merged). **67 tests pass.** One collection (run 6): 66 feeds, 23 new articles (5 full text, 18 excerpt-only), 22 s, peak 105 MB; **both wrongly dropped articles are restored** (still in their feeds), the cross-source pair still merges, no headline stored twice. Database: 1,863 articles, 732 full text. Also: the 0.2 check is rewritten so it can't expose `.env` (see 0.2). No sudo, no accounts, no LLM calls, no money spent.

**Human must:**
1. **1.3:** review and merge `task/1.3-collect`, then tick 1.3 in ROADMAP.
2. **0.2:** the deny-rule check under 0.2 (~2 minutes), then tick nothing new: 0.2 is already ticked.
3. Still open: Phase 1 🧑 steps 1.5, 1.7, 1.8, 1.9.

**Run of 2026-10-15 (eighth): the human's 1.3 decisions applied (same branch `task/1.3-collect`). Stopping here.** (1) The 10 Google News feeds are disabled (`enabled: false` with a note): Natalia now respects robots.txt for feeds as well as pages. (2) The six sites that refuse full text stay headline-only; **Engadget** and **Rest of World** were added to technology after the 1.1-style check plus a full-text check. (3) The 99 stock-quote rows were deleted with the approved command: `99 deleted`. (4) `natalia/feeds.py` now uses the honest user agent `natalia/0.1 (personal news reader)`, shared with the collector. **61 tests pass. One collection: 66 feeds, 76 new articles (43 full text, 33 excerpt-only), 1,181 URL and 13 headline duplicates removed, 35 s, peak 91 MB.** Database: 1,840 articles (727 full text), no headline stored twice. Found during the run: the near-identical headline rule merged two different articles ("9 best movies…" into "9 best TV shows…"); recorded as an open question, not changed. No sudo, no accounts, no LLM calls, no money spent.

**Human must:**
1. **1.3:** review and merge `task/1.3-collect`, then tick 1.3 in ROADMAP.
2. Decide on the near-identical headline fix (open question 3 under 1.3).
3. Still open from earlier: the 0.2 deny-rule check; Phase 1 🧑 steps 1.5, 1.7, 1.8, 1.9.

**Run of 2026-10-15 (seventh): 1.3 done (branch `task/1.3-collect`, from `origin/main` at 9162d25, where 1.2 is merged). Stopping here.** `natalia/collect.py` loads `config/sources.yaml` into `sources` (85 rows, 74 enabled), reads the 74 enabled feeds, drops entries older than 48 h, de-duplicates (canonical URL, then exact or near-identical headline, against the database and within the run), extracts article text with trafilatura where allowed, and stores the rest as headline + excerpt + link. It respects robots.txt for every page it fetches, uses its own user agent, 15 s timeouts, one request at a time per site, at most 4 sites at once, and stops asking a site that refuses twice. **First real run: 2,942 feed entries → 1,719 articles stored (654 full text, 1,065 excerpt-only), 248 URL duplicates and 60 headline duplicates removed, 915 too old; 22.9 min, peak 166 MB.** The second run stored no duplicates (0 repeated headlines in the table; its 112 new rows were new feed items). Fixes after run 1 cut the slow parts; runs 2–4 took 85–182 s and peaked at 69–128 MB. 60 tests pass. Also: `.idea/` added to `.gitignore`; 0.1 ticked in ROADMAP. No sudo, no accounts, no LLM calls, no money spent.

**Human must:**
1. **1.3:** review and merge `task/1.3-collect`, then tick 1.3 in ROADMAP.
2. Optional: delete the 99 stock-quote rows the first runs stored before the junk filter existed (command under 1.3, "Human must"). The agent didn't, since it's a delete on the real database.
3. Answer the 1.3 open questions (Google News robots.txt; sites that refuse full text).
4. Still open from earlier: the 0.2 deny-rule check; Phase 1 🧑 steps 1.5, 1.7, 1.8, 1.9.

**Run of 2026-10-15 (sixth): 1.2 done (branch `task/1.2-database`). Stopping here.** The human installed PostgreSQL 16.15 + pgvector 0.6.0 with the commands below and put `DATABASE_URL` in `.env`; their settings check matched (`jit|off`, `listen_addresses|localhost`, `max_connections|20`, `shared_buffers|8192`). Migration `0001_initial_schema` applied on the real database; a second run applied nothing. **34 tests pass, 0 skipped**, including the 3 against the real database; they left no rows behind. PostgreSQL uses **52.8 MB idle (peak 56.6 MB** during the migration and tests), well under the 250 MB target. Both schema choices confirmed by the human (topics as a list; summaries per article + language). Ticked 0.2, 1.1, 1.2 and 1.6 in ROADMAP. No sudo, no Gemini call, no money spent.

**Human must:**
1. **1.2:** review and merge `task/1.2-database`.
2. Tick 0.1 in ROADMAP too (merged as PR #1; not in this run's list, so left unticked).
3. Next 🧑 steps in Phase 1: 1.5 pick the embedding option (after the agent measures it); 1.7 approve one real digest; 1.8 create Natalia's bot; 1.9 register the daily deployment. The 0.2 deny-rule check still stands.

**Run of 2026-10-15 (fifth): 1.2 agent part done, blocked on 🧑 install (branch `task/1.2-database`, from `origin/main` at 915d1de, where 1.1 is merged). Stopping here.** Schema as one SQL migration (`migrations/0001_initial_schema.sql`: sources, articles, embeddings `vector(384)` with an HNSW cosine index, summaries, digests, digest_items), connection code and a migration runner (`natalia/db.py`, reads `DATABASE_URL` from the environment or `.env`), and a memory-tuned PostgreSQL config (`deploy/postgresql/natalia.conf`: `shared_buffers=64MB`, `max_connections=20`, `jit=off`, localhost only). Added `psycopg[binary]` and `python-dotenv` to the project's `.venv` (nothing system-wide). 31 tests pass; the 3 database tests skip until PostgreSQL is installed. No sudo, no accounts, no Gemini call, no money spent.

**Human must:**
1. **1.2:** run the install and setup commands under "1.2 — Database" below (`sudo`, ~5 minutes), then tell the agent so it can run the migration and the database tests and measure PostgreSQL's memory (or run those 3 commands yourself).
2. The earlier steps still stand: tick 0.2, 1.1 (merged as PR #3) and 1.6 in ROADMAP; the 0.2 deny-rule check; 1.5, 1.7, 1.8, 1.9.

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
- **Human must:** nothing. ~~Tick 0.1 in ROADMAP~~ ticked by the agent in 1.3 (the human's request).

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
- **State:** done, merged to `main` (PR #2, 97a159f); the deny-rule check is still the human's
- **Done:** `uv` project (Python 3.12, `.python-version`, `uv.lock`); package `natalia/` with `__init__.py` and a `llm.py` stub (`generate()` raises `NotImplementedError` until 1.7; no SDK yet); dev group `pytest` + `ruff` (lint rules E, F, W, I, B, UP; line length 100); `tests/` with 5 passing tests; `.claude/settings.json` deny rules.
- **Next:** Phase 1, task 1.1 (sources and feeds).
- **Human must:** run the denied-command check below (2 minutes, free). Merged already.

**Check that a denied command is blocked** (still open; ROADMAP 0.2's "done when"). The deny rules in `.claude/settings.json` are only loaded by a Claude Code session *started in* `~/projects/natalia`. Every agent run so far (0.2 through 1.3) was started in `~/projects/cloud-ai-lab`, so it ran under cloud-ai-lab's rules, and nobody has yet seen Natalia's rules block anything. A test (`test_settings_deny_rules`) checks the file's content, not that Claude Code applies it.

Run, in your own terminal (free: a Claude Code session, no Gemini, nothing on the server changes):
```bash
cd ~/projects/natalia && claude
```
Then, inside that session:
1. Type `/permissions` and check the **Deny** list shows Natalia's rules, e.g. `Bash(git merge:*)`, `Bash(sudo:*)`, `Read(./.env)`, `Bash(*prefect deployment run*)`.
2. Ask it: ``run `git merge --help` `` → expected: refused (permission denied by `Bash(git merge:*)`), not a help page.
3. Optionally ask: ``run `sudo -n true` `` → expected: refused by `Bash(sudo:*)`.

Don't test the `.env` rule by asking it to read `.env` (the earlier version of this check said to): if the rule didn't apply, your keys would land in the conversation. Seeing `Read(./.env)` in the `/permissions` Deny list is enough. Then tell the agent the result, or tick nothing: 0.2 is already ticked in ROADMAP, this only confirms it. To avoid the problem from now on, start Natalia's agent sessions in `~/projects/natalia`.

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
- **State:** done, merged to `main` (PR #3, 915d1de)
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

**Updated in 1.3 (2026-10-15, the human's decisions):** the 10 Google News feeds are disabled (news.google.com's robots.txt disallows them), and Engadget and Rest of World were added to technology. **Now 66 of 87 feeds enabled. Free feeds per topic:** economics 4 · world-politics 6 · technology 6 · science 6 · sport 4 · crypto 5 · markets 4 · cambodia 11 · general 4. Reuters and AP are gone (they only came through Google News).

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

## 1.2 — Database
- **Branch:** `task/1.2-database`
- **State:** done, merged to `main` (PRs #4 and #5, 9162d25)
- **Done:** schema migration, connection code, migration runner, memory-tuned config, tests (details below). The human installed and set up PostgreSQL; the migration ran on the real database, all 34 tests pass against it, and PostgreSQL's memory is measured: 52.8 MB idle, peak 56.6 MB.
- **Next:** 1.3 (collect) stores articles, starting with loading `config/sources.yaml` into `sources`.
- **Human must:** review and merge.

### What's on the branch
| File | What it is |
|---|---|
| `migrations/0001_initial_schema.sql` | The schema. Domains `topic` (the 9 topics) and `lang` (`en`, `km`). Tables `sources` (one per feed, unique feed URL), `articles` (unique canonical `url`, indexed `title_norm` for dedup, `excerpt`, `body` (NULL for paywalled), `language`, `topics topic[]`, `published_at`), `embeddings` (`vector(384)`, model name, HNSW index with cosine distance), `summaries` (summary + why it matters, one per article and language), `digests` (one per day and language, with request and token counts for 1.7), `digest_items` (articles in a digest, per topic, in order). `CREATE EXTENSION IF NOT EXISTS vector` is in the migration. |
| `natalia/db.py` | `database_url()` (environment first, else `.env`; never printed), `connect()`, `migrate()` (each pending `NNNN_*.sql` in its own transaction, recorded in `schema_migrations`, guarded by an advisory lock), `to_vector()` (embedding → pgvector literal), and a CLI: `python -m natalia.db status` / `migrate`. |
| `deploy/postgresql/natalia.conf` | Memory settings, installed into PostgreSQL's `conf.d/` by the human. |
| `tests/test_db.py` | 10 tests without a database (migration names, schema topics and languages match `natalia/feeds.py`, vector size, `DATABASE_URL` loading, `to_vector`), and 3 against the real database (migrations applied and pgvector present; insert → nearest-neighbour search → digest join; constraints reject duplicate URLs, unknown topics and languages, wrong vector size). Database tests roll back everything they write. |

**Schema choices (confirmed by the human on 2026-10-15):**
- `articles.topics` is an array, not one `topic` column: an article gets its feed's topic plus rule-based ones in 1.4 (e.g. a BBC Business story that mentions Cambodia).
- An article is stored once; `source_id` is the feed it was first seen in.
- Summaries are per article and language, not per digest, so a Khmer summary (Phase 3) is written once and reused.
- `vector(384)` fixes the dimension of `multilingual-e5-small`. If 1.5 picks another model, a new migration changes it.

### Memory: expected use and tuning
Ubuntu's defaults are `shared_buffers=128MB`, `max_connections=100`, JIT on. `natalia.conf` sets:

| Setting | Value | Why |
|---|---|---|
| `listen_addresses` | `localhost` | localhost only (also Ubuntu's default) |
| `max_connections` | 20 | the flow, the bot, the website and a psql session need a handful; each connection is a process of ~5–10 MB |
| `shared_buffers` | 64MB | the data is tens of MB in year one; the OS page cache does the rest |
| `work_mem` | 4MB | default, fine for this data |
| `maintenance_work_mem` | 64MB | default; used by the HNSW index build and VACUUM |
| `effective_cache_size` | 512MB | planner hint only, allocates nothing |
| `jit` | off | JIT loads LLVM (tens of MB per backend) for big analytic queries Natalia doesn't run |
| `autovacuum_max_workers` | 2 | default 3; a handful of tables |

**Expected:** ~30–60 MB idle after a restart (shared buffers fill as data is read), ~100–150 MB while the daily flow and the bot are connected, worst case under ~200 MB. Target is ≤ 250 MB. PostgreSQL runs in its own `systemd` unit, so its memory doesn't count against the lab worker's `MemoryMax=900M`; only the Python client side does.

**Measured** (2026-10-15, 35 minutes after start, right after the migration and the test run; empty database, 8 MB on disk): **52.8 MB, peak 56.6 MB**. To measure again once 1.3 stores real data and 1.9 runs the daily flow.

### Install and set up (🧑, `sudo`)
Run these in your own terminal, in order, in **one** shell session (steps 5–11 share a shell variable). Don't run them with Claude Code's `!` prefix: that puts the output into the agent's chat. Nothing below prints the password.

1. Refresh the package lists.
```bash
sudo apt update
```

2. Install PostgreSQL 16 (16.15) and pgvector (0.6.0) from Ubuntu's archive; this creates and starts the `16/main` cluster.
```bash
sudo apt install -y postgresql postgresql-16-pgvector
```

3. Install Natalia's memory settings (needs the `task/1.2-database` branch checked out, or merged).
```bash
sudo install -m 644 -o postgres -g postgres ~/projects/natalia/deploy/postgresql/natalia.conf /etc/postgresql/16/main/conf.d/natalia.conf
```

4. Restart PostgreSQL so the settings take effect.
```bash
sudo systemctl restart postgresql
```

5. Generate the role's password into a shell variable (48 hex characters, safe in a URL; nothing printed).
```bash
NATALIA_DB_PW="$(openssl rand -hex 24)"
```

6. Create the `natalia` login role with that password; it goes to `psql` on stdin, so it never shows in the process list.
```bash
printf "CREATE ROLE natalia LOGIN PASSWORD '%s';\n" "$NATALIA_DB_PW" | sudo -u postgres psql -q -v ON_ERROR_STOP=1
```
If this one fails, generate a new password (step 5) before retrying: PostgreSQL writes a failed statement to its log.

7. Create the `natalia` database, owned by the role, in UTF-8 (needed for Khmer).
```bash
sudo -u postgres createdb --owner=natalia --encoding=UTF8 --template=template0 natalia
```

8. Enable pgvector in that database (it needs a superuser, so the migration can't do it).
```bash
sudo -u postgres psql -d natalia -c 'CREATE EXTENSION IF NOT EXISTS vector;'
```

9. Remove the old (fake) `DATABASE_URL` line from `.env`, if any. No `sudo`.
```bash
sed -i '/^DATABASE_URL=/d' ~/projects/natalia/.env
```

10. Add the real `DATABASE_URL` to `.env` (`printf` is a shell builtin; nothing printed). No `sudo`.
```bash
printf 'DATABASE_URL=postgresql://natalia:%s@127.0.0.1:5432/natalia\n' "$NATALIA_DB_PW" >> ~/projects/natalia/.env
```

11. Forget the password in this shell.
```bash
unset NATALIA_DB_PW
```

12. Check the settings took effect. Expected: `jit|off`, `listen_addresses|localhost`, `max_connections|20`, `shared_buffers|8192` (8192 × 8 kB = 64 MB).
```bash
sudo -u postgres psql -Atc "SELECT name, setting FROM pg_settings WHERE name IN ('shared_buffers','max_connections','jit','listen_addresses') ORDER BY name"
```

`pg_hba.conf` needs no change: Ubuntu's default already allows password (`scram-sha-256`) logins from `127.0.0.1`.

**After that, no `sudo` (the agent can do these in the next run, or you can):**
```bash
cd ~/projects/natalia && uv run python -m natalia.db migrate   # expect: applied: 0001_initial_schema
uv run pytest                                                  # expect: all passed, 0 skipped
systemctl status postgresql@16-main --no-pager                 # the "Memory:" line
```
✅ Done in the sixth run; output below (steps 8–11). Use `postgresql@16-main`, not `postgresql`: on Ubuntu `postgresql.service` is an empty wrapper and shows no memory.

<details><summary>Steps and output from this build</summary>

**1. Branch from `origin/main`.** 1.1 was merged (PR #3).
```console
$ git fetch origin && git log --oneline -1 origin/main
915d1de Merge pull request #3 from thovicheka/task/1.1-sources
$ git switch -c task/1.2-database origin/main
Switched to a new branch 'task/1.2-database'
```
**Result:** ✅

**2. Which packages apt would install** (read-only, no `sudo`):
```console
$ apt-cache policy postgresql postgresql-16 postgresql-16-pgvector
postgresql:
  Installed: (none)
  Candidate: 16+257build1.1
postgresql-16:
  Installed: (none)
  Candidate: 16.15-0ubuntu0.24.04.1
postgresql-16-pgvector:
  Installed: (none)
  Candidate: 0.6.0-1
$ apt-cache show postgresql-16-pgvector | grep Depends
Depends: postgresql-16, postgresql-16-jit-llvm (>= 17), libc6 (>= 2.14)
$ locale | head -1
LANG=en_US.UTF-8
```
**Result:** ✅ pgvector 0.6.0 supports HNSW indexes (0.5+). It pulls in the JIT package, hence `jit = off`. The server locale is UTF-8; `createdb` still sets UTF8 explicitly.

**3. Python dependencies** (project `.venv` only):
```console
$ uv add 'psycopg[binary]' python-dotenv
 + psycopg==3.3.6
 + psycopg-binary==3.3.6
 + python-dotenv==1.2.4
 + typing-extensions==4.16.0
```
**Result:** ✅ `psycopg[binary]` brings its own libpq, so no system `libpq-dev` is needed.

**4. Migration runner check.** A migration file holds several statements; psycopg sends a query without parameters through the simple query protocol, which allows that:
```console
$ sed -n 455,459p .venv/lib/python3.12/site-packages/psycopg/_cursor_base.py
        else:
            # If we can, let's use simple query protocol,
            # as it can execute more than one statement in a single query.
            self._pgconn.send_query(query.query)
```
**Result:** ✅

**5. Tests and lint.**
```console
$ uv run ruff check . ; uv run ruff format --check .
E501 Line too long (101 > 100)
 --> natalia/db.py:3:101
```
**Result:** ❌ → fixed. **Error:** a docstring line was 101 characters. **Fix:** shortened it.
```console
$ uv run ruff check . ; uv run ruff format --check .
All checks passed!
14 files already formatted
$ uv run pytest -v
tests/test_db.py::test_migration_files_are_numbered PASSED
tests/test_db.py::test_migration_files_reject_bad_names PASSED
tests/test_db.py::test_migration_files_reject_duplicate_numbers PASSED
tests/test_db.py::test_schema_topics_match_feed_topics PASSED
tests/test_db.py::test_schema_languages_match_feed_languages PASSED
tests/test_db.py::test_schema_vector_size_matches_embedding_dim PASSED
tests/test_db.py::test_database_url_from_environment PASSED
tests/test_db.py::test_database_url_from_env_file PASSED
tests/test_db.py::test_database_url_missing PASSED
tests/test_db.py::test_to_vector PASSED
tests/test_db.py::test_migrations_applied_and_pgvector_present SKIPPED
tests/test_db.py::test_round_trip_and_nearest_neighbours SKIPPED (PostgreSQL not reachable...)
tests/test_db.py::test_constraints SKIPPED (PostgreSQL not reachable...)
(…21 tests from 0.1–1.1, all PASSED)
======================== 31 passed, 3 skipped in 0.52s =========================
```
**Result:** ✅ The 3 skips are expected until PostgreSQL is installed. The SQL itself has not run on a server yet; the database tests will check it.

**6. The CLI without a server.** First version printed a traceback; changed `main()` to print one line and exit 1.
```console
$ uv run python -m natalia.db status
cannot connect: connection failed: connection to server at "<ip>", port 5432 failed: Connection refused
	Is the server running on that host and accepting TCP/IP connections?
```
**Result:** ✅ No password in the message (psycopg names only host and port).

**7. Commit and push**
```console
$ git log --oneline -1
9d6188b Task 1.2: schema migration (sources, articles, embeddings vector(384), summaries, digests), db connection + migration runner, Postgres memory config, tests
$ git push -u origin task/1.2-database
 * [new branch]      task/1.2-database -> task/1.2-database
```
**Result:** ✅

**8. 🧑 Install and set up** (the human, 2026-10-15, with the commands above). Their check of step 12:
```console
$ sudo -u postgres psql -Atc "SELECT name, setting FROM pg_settings WHERE name IN (...) ORDER BY name"
jit|off
listen_addresses|localhost
max_connections|20
shared_buffers|8192
```
**Result:** ✅ `natalia.conf` is in effect (8192 × 8 kB = 64 MB).

**9. Migrate on the real database**, twice (the second run must do nothing):
```console
$ uv run python -m natalia.db status
PostgreSQL 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1), pgvector 0.6.0
applied migrations: none
pending migrations: 0001_initial_schema
$ uv run python -m natalia.db migrate
applied: 0001_initial_schema
PostgreSQL 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1), pgvector 0.6.0
applied migrations: 0001_initial_schema
pending migrations: none
$ uv run python -m natalia.db migrate
nothing to apply
PostgreSQL 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1), pgvector 0.6.0
applied migrations: 0001_initial_schema
pending migrations: none
```
**Result:** ✅ The `natalia` role connects with the password from `.env`, and `CREATE EXTENSION IF NOT EXISTS vector` is a no-op for it because the human created the extension as superuser.

**10. All tests, against the real database**
```console
$ uv run pytest -v
tests/test_db.py::test_migrations_applied_and_pgvector_present PASSED
tests/test_db.py::test_round_trip_and_nearest_neighbours PASSED
tests/test_db.py::test_constraints PASSED
(…31 more, all PASSED)
============================== 34 passed in 0.48s ==============================
$ uv run ruff check . ; uv run ruff format --check .
All checks passed!
14 files already formatted
```
Then checked that the tests left nothing behind:
```console
sources            rows=0
articles           rows=0
embeddings         rows=0
summaries          rows=0
digests            rows=0
digest_items       rows=0
schema_migrations  rows=1
('embeddings_hnsw_idx',)
8135 kB database size
```
**Result:** ✅

**11. PostgreSQL memory**
```console
$ systemctl status postgresql@16-main --no-pager
● postgresql@16-main.service - PostgreSQL Cluster 16-main
     Active: active (running) since Thu 2026-10-15 09:22:05 UTC; 35min ago
      Tasks: 6 (limit: 4482)
     Memory: 52.8M (peak: 56.6M)
        CPU: 1.652s
     CGroup: /system.slice/system-postgresql.slice/postgresql@16-main.service
             ├─11206 /usr/lib/postgresql/16/bin/postgres -D /var/lib/postgresql/16/main -c config_file=...
             ├─11207 "postgres: 16/main: checkpointer "
             ├─11208 "postgres: 16/main: background writer "
             ├─11210 "postgres: 16/main: walwriter "
             ├─11211 "postgres: 16/main: autovacuum launcher "
             └─11212 "postgres: 16/main: logical replication launcher "
$ systemctl show postgresql@16-main -p MemoryCurrent -p MemoryPeak
MemoryCurrent=55382016
MemoryPeak=59351040
```
**Result:** ✅ 52.8 MB, target ≤ 250 MB. Adding the processes' RSS (~83 MB) counts the shared buffers several times; the cgroup figure above is the true one.

**12. Tick 0.2, 1.1, 1.2 and 1.6 in ROADMAP** (the human's request), commit and push.
**Result:** ✅ (commit below in git log)
</details>

**Noticed, not done (out of scope):**
- ROADMAP 1.2's "done when" says `systemctl status postgresql`; on Ubuntu that unit shows no memory. `postgresql@16-main` is the one to read. Worth a one-word edit in ROADMAP.
- ~~ROADMAP lists a single `topic` per article; the schema uses `topics topic[]`.~~ Confirmed by the human: topics as a list.
- **Server memory is tight right now, but not because of PostgreSQL.** At the measurement, `free -m` showed 999 MB available (2642 MB this morning) and 543 MB of swap used. The biggest process was the JetBrains remote dev server (`remote-dev-serv`, ~2.0 GB RSS, started ~46 minutes earlier), then the two Claude Code sessions (~310 MB and ~225 MB). That leaves less room for the daily flow's ~700 MB peak (1.5, 1.9) while the IDE backend runs. Also, its untracked `.idea/` folder is in the repo; adding `.idea/` to `.gitignore` would keep it out of commits. Left alone (not committed, not ignored).
- No upsert helper yet to load `config/sources.yaml` into the `sources` table; 1.3 (collect) needs it first and is the natural place.
- The test session again started in cloud-ai-lab, so Natalia's `.claude/settings.json` deny rules were not the ones loaded (same as 0.2 and 1.1).

## 1.3 — Collect and clean
- **Branch:** `task/1.3-collect`
- **State:** done, committed and pushed; waiting for the human's review and merge
- **Done:** the collector, its tests, four real runs (numbers below). "Done when" holds: a second run stores no article twice, and a failing feed (Post Khmer, HTTP 500 in runs 3–5) doesn't stop the others. Then the human's decisions (see "Decisions applied" below): Google News feeds disabled, Engadget and Rest of World added, 99 junk rows deleted, honest user agent in `feeds.py`; run 5.
- **Next:** 1.4 (filter by topic) adds rule-based topics to the stored articles.
- **Human must:** review and merge; tick 1.3.

### What's on the branch
| File | What it is |
|---|---|
| `natalia/collect.py` | The collector. `uv run python -m natalia.collect` (all enabled feeds), `--feed BBC` (only feeds whose name contains it), `--no-text` (excerpts only, no pages), `--max-age-hours 48`. Prints a per-site progress line and a report: per-topic counts, why articles are excerpt-only, duplicates dropped, run time, HTTP requests, peak memory. |
| `tests/test_collect.py` | 26 tests, no network (a fake fetcher serves feeds, pages and robots.txt from memory and records every URL requested): URL canonicalization, Google News decoding, headline normalization (Khmer marks kept), excerpts, near-identical headlines, junk headlines, robots.txt (disallow, 403, 404, redirects, crawl delay), refusals, extraction (full, paywall marker, not HTML, too short, network error), and a whole run twice against the real database (rolled back). |
| `tests/conftest.py` | The database fixtures, moved out of `tests/test_db.py` so both files use them. |
| `pyproject.toml`, `uv.lock` | `trafilatura` 2.3.1 (brings `lxml` 6.1.3, `justext`, `htmldate`, `courlan`). |
| `.gitignore` | `.idea/` (the JetBrains folder). |
| `docs/ROADMAP.md` | 0.1 ticked. |

### How it decides
- **Sources:** `config/sources.yaml` is upserted into `sources` by feed URL on every run; a feed removed from the file is disabled, not deleted (articles point to it).
- **Order:** free direct feeds first, then Google News, then paywalled feeds, so when one story is in several feeds, the stored copy is the one that can have full text.
- **Duplicates:** (1) canonical URL: lowercase host, https, no fragment, no tracking parameters (`utm_*`, `fbclid`, `at_*`, `oc`…), sorted query, no trailing slash; (2) headline: lowercase, no punctuation, " - Publisher" suffix removed, compared exactly, and for headlines of 5+ words also by similarity ≥ 0.9 against articles of the last 3 days. A duplicate from another topic's feed adds its topic to the stored article (`topics` array; 253 articles have more than one).
- **Full text only when allowed:** not a paywalled source, not a site on `EXCERPT_ONLY_DOMAINS` (Reuters, AP, the paywalled ones), not a Google News link, robots.txt allows the page (checked on every redirect hop), the page is HTML, has no `"isAccessibleForFree": false` marker, and gives ≥ 300 characters of text. Otherwise: headline + feed excerpt + link. No paywall is ever bypassed: paywalled pages are never requested.
- **Google News feeds are disabled** (the human's decision, run 5 on): their robots.txt disallows the feeds as well as the links. The collector's Google News handling stays and is tested, for any Google link a feed may carry. Before that: **Google News links were not resolved.** news.google.com's robots.txt disallows `/rss/articles/` (the redirect) and the API that decodes new-style ids; current ids (`CBMi…AU_yqL…`) don't contain the URL. The collector decodes old-style ids offline (0 of 935 in this run were old-style); the rest keep the Google link, which opens the article in a browser. Their duplicates are caught by headline.
- **Not news:** headlines that are just a ticker or a "Stock Price & Latest News" page (Reuters' Google News search returns ~90 a run) are dropped.
- **Polite:** user agent `natalia/0.1 (personal news reader)`, robots rules matched for `natalia`; 15 s timeout, 3 MB cap; one request at a time per site, ≥ 1 s apart (more if robots.txt sets `Crawl-delay`; above 30 s, no page fetches); at most 4 sites at once; a site that refuses (401/403/405/429) or times out twice is not asked again that run. Feeds themselves are fetched without the robots.txt check, as feed readers do; the human chose to disable the Google News feeds, whose robots.txt disallows them, so every enabled feed is also allowed by its site's robots.txt rules as far as checked.

### Real runs (2026-10-15)
| Run | When (UTC) | Code | Stored | Full | Excerpt | Dup URL | Dup headline | Not news | Time | HTTP requests | Peak RSS |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 10:19 | first version | 1,719 | 654 | 1,065 | 248 | 60 | – | **1,373 s** | 897 | 166 MB |
| 2 | 10:47 | + refusal cut-off, new UA | 112 | 22 | 90 | 1,831 | 72 | – | 85 s | 120 | 128 MB |
| 3 | 11:05 | + junk filter | 14 | 0 | 14 | 1,856 | 52 | 90 | 136 s | 84 | 69 MB |
| 4 | 11:20 | final UA | 13 | 3 | 10 | 1,855 | 54 | 87 | 182 s | 87 | 88 MB |

Peak RSS is `/usr/bin/time -v`'s "Maximum resident set size" (the Python process). The daily-flow budget is ≤ 700 MB. PostgreSQL after the runs: 56 MB, peak 68.6 MB (`systemctl show postgresql@16-main`); the database is 12 MB.

**In the database after run 4:** 1,863 articles, 684 with full text, 1,179 excerpt-only; 0 headlines stored twice; 21 Khmer articles, all with full text; median body 3,479 characters.

| Topic (articles can have several) | Articles | Full text | Excerpt-only |
|---|---|---|---|
| economics | 224 | 49 | 175 |
| world-politics | 369 | 136 | 233 |
| technology | 112 | 27 | 85 |
| science | 157 | 42 | 115 |
| sport | 251 | 133 | 118 |
| crypto | 117 | 96 | 21 |
| markets | 315 | 66 | 249 |
| cambodia | 171 | 70 | 101 |
| general | 410 | 127 | 283 |

Excerpt-heavy topics are the ones with many paywalled or Google News feeds (markets, economics, general).

**Sites that refuse full text** (excerpt-only, as asked): Ars Technica (HTTP 405), Phys.org, The Block, Investing.com and Sky News (HTTP 403), NPR (pages time out; its robots.txt is fine). Reuters and AP never get a page request.

<details><summary>Steps and output from this build</summary>

**0. Which repo.** The session started in `~/projects/cloud-ai-lab`; the task belongs to Natalia. The human confirmed: work in `~/projects/natalia`, leave cloud-ai-lab alone.
**Result:** ✅

**1. Branch from `origin/main`.** 1.2 was merged (PR #5).
```console
$ git fetch origin && git log --oneline -1 origin/main
9162d25 Merge pull request #5 from thovicheka/task/1.2-database
$ git switch -c task/1.3-collect origin/main
Switched to a new branch 'task/1.3-collect'
$ git branch --unset-upstream    # so a bare `git push` can never target main
```
**Result:** ✅

**2. Google News: what robots.txt allows.**
```console
$ curl -s -A "natalia" https://news.google.com/robots.txt | head -14
User-agent: *
Disallow: /
Allow: /$
Allow: /?
Allow: /home$
(…)
Allow: /topics/
Allow: /publications/
Allow: /stories/
```
A feed link is `https://news.google.com/rss/articles/CBMiogFBVV95cUxO…?oc=5`; its base64 decodes to `\x08\x13"\xa2\x01AU_yqLN…`, an opaque id with no URL in it.
**Result:** ⚠️ `/rss/articles/` (the redirect) is disallowed, so the collector doesn't follow these links; see open question 1. `/rss/search` (the feeds) is disallowed too.

**3. Dependency.**
```console
$ uv add trafilatura
 + lxml==6.1.3
 + trafilatura==2.3.1
 (+ courlan, dateparser, htmldate, justext, lxml-html-clean, …)
```
**Result:** ✅

**4. Smoke run, one feed, twice.**
```console
$ uv run python -m natalia.collect --feed "CamboJA News"
feeds done: 5 new articles to store
cambodia            1    0      10     5      0        0      5     5       0
run time 7 s, 7 HTTP requests, peak memory (max RSS) 64 MB
$ uv run python -m natalia.collect --feed "CamboJA News"
feeds done: 0 new articles to store
cambodia            1    0      10     5      5        0      0     0       0
run time 1 s, 1 HTTP requests, peak memory (max RSS) 46 MB
```
**Result:** ✅ 5 stored with full text (4–9 k characters each), 5 too old; the second run found 5 URL duplicates and stored nothing.

**5. Tests.** First run of the new tests:
```console
$ uv run pytest -q
FAILED tests/test_collect.py::test_collect_twice_stores_each_article_once
E       AssertionError: assert [',', 'a', 'a...'c', 'c', ...] == ['cambodia', 'economics']
```
**Result:** ❌ → fixed. **Cause:** psycopg returns the `topic[]` domain array as a string; **fix:** the test reads `topics::text[]`. Two more test-side fixes: the fake page was served under the clean URL while the collector rightly fetches the feed's own link, and the fake Google News item had a longer excerpt than real ones.

**6. First real run** (all 74 enabled feeds):
```console
$ /usr/bin/time -v uv run python -m natalia.collect
feeds done: 1719 new articles to store
topic           feeds fail entries   old dupURL dupTitle stored  full excerpt
economics           9    0     581   365     32        3    181    49     132
world-politics      9    0     366    21    167        4    174    97      77
technology          6    0     131    19      4        2    106    23      83
science             9    0     309   146      7        2    154    42     112
sport               5    0     275    37     18        1    219   115     104
crypto              6    0     121     7      0        0    114    93      21
markets             9    0     311    41      5       16    249    61     188
cambodia           14    0     448   254      5       27    162    65      97
general             7    0     400    25     10        5    360   109     251
TOTAL              74    0    2942   915    248       60   1719   654    1065

excerpt-only, why:
    514  Google News link (not followed: robots.txt)
    413  paywalled source
     58  HTTP 403
     26  robots.txt disallows
     25  too little text on page
     20  HTTP 405
      9  paywall marker on page

Google News links: 935, resolved offline: 0; topics added to already-stored articles: 237
near-identical headlines dropped (new -> kept), first few:
  'uk threatens to ban eritreans over returns policy'
    -> 'uk threatens to ban eritreans over migrant return policy'
  'germany mine clearance support benefits 500 000 cambodians'
    -> 'german mine clearance support benefits 500 000 cambodians since 1993'
  'vietnamese party state facilitate more substantive defence ties with c'
    -> 'vietnamese party state facilitate more substantive defense ties with c'

run time 1373 s, 897 HTTP requests, peak memory (max RSS) 162 MB
	Elapsed (wall clock) time (h:mm:ss or m:ss): 22:52.99
	Maximum resident set size (kbytes): 166160
	Exit status: 0
```
**Result:** ⚠️ correct, but slow: 22.9 min for 897 requests. **Cause**, found by timing single requests: (a) sites that refuse slowly (a Phys.org 403 took 32 s) were still asked for every queued article (29 for Phys.org); (b) NPR's Akamai front end stalls a client whose user agent says `Mozilla/5.0 (compatible; …)`, so NPR's robots.txt timed out (15 s) and was read as "disallow all". Guardian and BBC pages took ~1 s each, so the 1 s per-site gap is not the problem. **Fix:** a site that refuses (401/403/405/429) or times out twice is not asked again that run (politer too); an honest user agent (step 9).

**7. Second real run** (refusal cut-off; checks "running it twice"):
```console
feeds done: 112 new articles to store
  www.investing.com: 0/10 full text, 2 s
  www.theguardian.com: 5/5 full text, 7 s
  phys.org: 0/1 full text, 2 s
  (…)
TOTAL              74    0    2939   924   1831       72    112    22      90
run time 85 s, 120 HTTP requests, peak memory (max RSS) 125 MB
```
Were the 112 new rows really new? In SQL: headlines stored twice: **0**. 74 of them were published before run 1, but they're not repeats: Google News search feeds return a different 100 of the day's matches on each fetch, and 60 of the 112 came from them.
**Result:** ✅ no duplicates. ❌ found junk: 99 stored rows were Reuters stock-quote pages (`3ZV.MU - Reuters`, `(ORK.HA) | Stock Price & Latest News - Reuters`). **Fix:** a junk-headline rule; checked against all 1,836 stored titles, it matches exactly those 99 and nothing else.

**8. Third real run** (junk filter):
```console
feeds done: 14 new articles to store
TOTAL              74    1    2859   937   1856       52     14     0      14
not news, dropped (stock-quote pages): 90
feed errors:
  Post Khmer: HTTP 500
run time 136 s, 84 HTTP requests, peak memory (max RSS) 68 MB
```
**Result:** ✅ 90 stock-quote entries dropped; Post Khmer's server error didn't stop the other 73 feeds.

**9. User agent.** With the user agent from step 6's fix (`natalia/0.1 (personal news reader; respects robots.txt)`), NPR's robots.txt still timed out:
```console
UA only   TimeoutError 10.0s      # natalia/0.1 (personal news reader; respects robots.txt)
short UA  200 0.1s                # natalia/0.1
natalia/0.1 personal-news-reader       200 0.1s
natalia/0.1 (personal news reader)     200 0.0s
```
**Result:** ❌ → fixed: NPR's bot rules also catch the word "robots". Final user agent `natalia/0.1 (personal news reader)`. A side-by-side check of one article per free site (34 sites) gave the same status codes for the Mozilla and natalia user agents, so nothing else changes.

**10. Fourth real run** (final user agent):
```console
feeds done: 13 new articles to store
TOTAL              74    1    2862   940   1855       54     13     3      10
not news, dropped (stock-quote pages): 87
feed errors:
  Post Khmer: HTTP 500
run time 182 s, 87 HTTP requests, peak memory (max RSS) 86 MB
```
**Result:** ✅ all feeds but Post Khmer (still HTTP 500 on their side) work with the new user agent. Most of the 182 s is Google News: its 10 feeds share one site, so they are fetched one by one, and an uncached `site:… when:1d` search takes 18–48 s on Google's side (3 s when cached; curl sees the same). Not parallelized, to stay polite.

**11. Tests and lint.**
```console
$ uv run ruff check . ; uv run ruff format --check .
All checks passed!
17 files already formatted
$ uv run pytest -q
60 passed in 0.84s
```
**Result:** ✅ 34 earlier tests + 26 new; the database tests roll back everything they write.

**12. `.idea/` in `.gitignore`, 0.1 ticked in ROADMAP.**
```console
$ git check-ignore -v .idea/
.gitignore:191:.idea/	.idea/
```
**Result:** ✅

**13. Commits** (all pushed to `task/1.3-collect`):
```console
05d9b5c Task 1.3: collector (feeds -> articles), trafilatura text where allowed, dedup, robots.txt, tests; ignore .idea/, tick 0.1
551501c Collector: stop asking a site after 2 refusals, honest user agent, per-site progress; ...
0bcd16c Collector: drop stock-quote pages (not news) from Reuters' Google News search
8c2a2b5 Collector: user agent "natalia/0.1 (personal news reader)" (NPR stalls UAs containing "robots")
```
**Result:** ✅
</details>

### Decisions applied (2026-10-15, the human's answers to the open questions)

<details><summary>Steps and output</summary>

**14. Disable the 10 Google News feeds.** `enabled: false` plus a note on each; the file header says why.
```console
$ grep -c "news.google.com" config/sources.yaml
11            # 10 just disabled + Google News Khmer (disabled in 1.1)
```
Free feeds per topic, before → after: economics 5 → 4, world-politics 8 → 6, markets 5 → 4, cambodia 13 → 11, general 7 → 4; the others unchanged (also recorded under 1.1).
**Result:** ✅

**15. Technology sources that allow full text.** Each candidate: feed checked as in 1.1, then the collector's own `extract_text` on its 2 latest articles (robots.txt for `natalia`, paywall marker, text length).
```console
The Register    feed=200 items=50 latest=10-15 10:30 crawl-delay=None pages=['robots.txt disallows:0', 'robots.txt disallows:0']
Engadget        feed=200 items=20 latest=10-15 10:34 crawl-delay=None pages=['full:2445', 'full:2034']
IEEE Spectrum   feed=200 items=30 latest=10-15 10:00 crawl-delay=None pages=['full:2301', 'full:1538']
Rest of World   feed=200 items=12 latest=10-15 10:00 crawl-delay=None pages=['full:6686', 'full:6050']
ZDNET           feed=200 items=25 latest=10-14 13:59 crawl-delay=None pages=['full:3191', 'full:4095']
The Next Web    feed FAIL HTTP 403
Tom's Hardware  feed=200 items=50 latest=10-15 10:30 crawl-delay=None pages=['full:3588', 'full:2400']
9to5Google      feed=200 items=100 latest=10-15 11:00 crawl-delay=None pages=['paywall marker on page:0', 'full:1494']
```
**Result:** ✅ Added **Engadget** (daily tech news, e.g. "Iowa, Nebraska and six other states are suing OpenAI…") and **Rest of World** (tech outside the West, incl. Asia; long articles). Not chosen: The Register (robots.txt disallows us), The Next Web (feed 403), 9to5Google (paywall marker on some pages), IEEE Spectrum (mixes in IEEE announcements), ZDNET and Tom's Hardware (mostly reviews and product news). Easy to add later.

**16. User agent in `natalia/feeds.py`.** `USER_AGENT = "natalia/0.1 (personal news reader)"` is now defined in `feeds.py` and imported by the collector (one definition). New test `test_user_agent_is_honest_and_shared`: no "Mozilla", no "robots", same object in both modules.
**Result:** ✅

**17. Delete the 99 stock-quote rows** (approved by the human). First a look at the target:
```console
99 match; all end in Reuters: True
sample: ['INBAF.PK - Reuters', '(ORK.HA) | Stock Price & Latest News - Reuters', 'CEVI.SG - Reuters', 'CJ2.SG - Reuters', '8750.MU - | Stock Price & Latest News - Reuters']
embeddings refs: 0
summaries refs: 0
digest_items refs: 0
```
Then the exact command:
```console
$ cd ~/projects/natalia && uv run python -c "
from natalia import db, collect
with db.connect() as conn:
    ids = [i for i, t in conn.execute('SELECT id, title FROM articles').fetchall() if collect.is_junk_title(t, 'Reuters')]
    print(conn.execute('DELETE FROM articles WHERE id = ANY(%s)', (ids,)).rowcount, 'deleted')"
99 deleted
$ (check) junk left: 0 | total: 1764
```
**Result:** ✅ 1,863 − 99 = 1,764.

**18. Tests and lint.**
```console
$ uv run ruff check . ; uv run ruff format --check .
All checks passed!
17 files already formatted
$ uv run pytest -q
61 passed in 0.71s
```
**Result:** ✅

**19. Run 5: one collection** with 66 enabled feeds:
```console
$ /usr/bin/time -v uv run python -m natalia.collect
feeds done: 76 new articles to store
  www.investing.com: 0/9 full text, 2 s
  www.theguardian.com: 5/5 full text, 6 s
  restofworld.org: 2/2 full text, 2 s
  www.bbc.co.uk: 8/8 full text, 8 s
  www.npr.org: 1/1 full text, 1 s
  phys.org: 0/1 full text, 2 s
  www.engadget.com: 20/20 full text, 21 s
  (…7 more sites)
topic           feeds fail entries   old dupURL dupTitle stored  full excerpt
economics           8    0     484   369    113        0      2     0       2
world-politics      7    0     159    21    124        3     11    11       0
technology          8    0     163    30    108        2     23    22       1
science             9    0     310   145    159        2      4     1       3
sport               5    0     277    38    225        1     13     1      12
crypto              6    0     121     9    110        0      2     1       1
markets             8    0     211    36    157        4     14     0      14
cambodia           11    1     138    78     59        0      1     1       0
general             4    0     158    25    126        1      6     6       0
TOTAL              66    1    2021   751   1181       13     76    43      33

excerpt-only, why:
     21  paywalled source
      7  site refused earlier requests (not asked again)
      4  HTTP 403
      1  too little text on page

not news, dropped (stock-quote pages): 0
Google News links: 0, resolved offline: 0; topics added to already-stored articles: 11
near-identical headlines dropped (new -> kept), first few:
  'uk threatens to ban eritreans over returns policy'
    -> 'uk threatens to ban eritreans over migrant return policy'
  'connections sports edition today hints and answers for oct 14 2026 puz'
    -> 'connections sports edition today hints and answers for oct 15 2026 puz'
  'the 9 best movies to stream this month october 2026'
    -> 'the 9 best tv shows to stream this month october 2026'
feed errors:
  Post Khmer: HTTP 500

run time 35 s, 136 HTTP requests, peak memory (max RSS) 91 MB
	Elapsed (wall clock) time (h:mm:ss or m:ss): 0:35.28
	Maximum resident set size (kbytes): 93252
```
**Result:** ✅ no Google News request; Engadget 20/20 and Rest of World 2/2 full text; NPR now serves full text with the honest user agent (it timed out before). 35 s instead of 85–182 s (no Google News waits). Post Khmer still HTTP 500. ❌ **Found:** two wrong headline merges (open question 3).

**In the database after run 5:** 1,840 articles, 727 full text, 1,113 excerpt-only; 0 headlines stored twice; 87 sources, 66 enabled, 0 Google News enabled; Engadget 20 stored (20 full), Rest of World 2 (2 full).

| Topic (articles can have several) | Articles | Full text | Excerpt-only |
|---|---|---|---|
| economics | 226 | 49 | 177 |
| world-politics | 389 | 156 | 233 |
| technology | 135 | 49 | 86 |
| science | 161 | 43 | 118 |
| sport | 265 | 135 | 130 |
| crypto | 119 | 97 | 22 |
| markets | 230 | 66 | 164 |
| cambodia | 172 | 71 | 101 |
| general | 417 | 134 | 283 |

These totals still include items stored from Google News feeds in runs 1–4 (kept; nothing asked to delete them).
</details>

### Headline fix (2026-10-15, the human's decision on open question 3)

<details><summary>Steps and output</summary>

**20. The fix.** `TitleIndex` stores each headline with its site (`site_of`: the host without `www.`; for stored rows, from `articles.url`). An exact match merges whatever the site; a near-identical one (similarity ≥ 0.9) only when the sites differ. "Site", not "feed": two feeds of one site (e.g. The Guardian's World and Sport) count as one source, so a site's series posts stay apart however they arrive.
**Result:** ✅

**21. Tests and lint.** New: Wired and The Athletic pairs (real headlines from run 5) are kept apart, and each test first asserts the pair is similar enough (≥ 0.9) that the old rule merged it; the BBC/Guardian Eritreans pair (run 1) still merges; exact headlines merge even from one site; `site_of`; and a whole run where one feed's two near-identical posts are both stored.
```console
$ uv run ruff check . ; uv run ruff format --check .
All checks passed!
17 files already formatted
$ uv run pytest -q
67 passed in 0.84s
```
**Result:** ✅

**22. Run 6: one collection.** The two wrongly dropped articles were still in their feeds (Wired's from 2026-10-13 18:49 UTC, ~41 h old, inside the 48 h window):
```console
Wired [('The 9 Best Movies to Stream This Month (October 2026)', 'Tue, 13 Oct 2026 18:49')]
The Athletic [('Connections: Sports Edition today: Hints and answers for Oct. 15, 2026', 'Thu, 15 Oct 2026 04:00'), ('Connections: Sports Edition today: Hints and answers for Oct. 14, 2026', 'Wed, 14 Oct 2026 04:00')]
$ /usr/bin/time -v uv run python -m natalia.collect
feeds done: 23 new articles to store
  www.investing.com: 0/9 full text, 2 s
  phys.org: 0/1 full text, 2 s
  www.espn.com: 2/2 full text, 3 s
  techcrunch.com: 1/1 full text, 1 s
  www.skysports.com: 2/3 full text, 7 s
topic           feeds fail entries   old dupURL dupTitle stored  full excerpt
economics           8    0     484   370    114        0      0     0       0
world-politics      7    0     159    21    135        3      0     0       0
technology          8    0     163    30    130        1      2     1       1
science             9    0     310   146    161        2      1     0       1
sport               5    0     279    38    233        0      8     4       4
crypto              6    0     121     9    112        0      0     0       0
markets             8    0     211    36    157        6     12     0      12
cambodia           11    1     138    78     60        0      0     0       0
general             4    0     158    25    132        1      0     0       0
TOTAL              66    1    2023   753   1234       13     23     5      18

excerpt-only, why:
      7  site refused earlier requests (not asked again)
      7  paywalled source
      3  HTTP 403
      1  too little text on page

near-identical headlines dropped (new -> kept), first few:
  'uk threatens to ban eritreans over returns policy'
    -> 'uk threatens to ban eritreans over migrant return policy'
feed errors:
  Post Khmer: HTTP 500

run time 22 s, 89 HTTP requests, peak memory (max RSS) 104 MB
	Maximum resident set size (kbytes): 106980
```
Check in the database:
```console
('The 9 Best TV Shows to Stream This Month (October 2026)', 'Wired', False, 10:42:32)
('The 9 Best Movies to Stream This Month (October 2026)', 'Wired', False, 11:23:43)
('Connections: Sports Edition today: Hints and answers for Oct. 15, 2026, puzzle No. 752', 'The Athletic', False, 10:42:32)
('Connections: Sports Edition today: Hints and answers for Oct. 14, 2026, puzzle No. 751', 'The Athletic', False, 11:23:43)
dup title_norm: 0 | total: (1863, 732)
```
(columns: title, source, has full text, collected at UTC)
**Result:** ✅ both restored, as headline + excerpt + link (Wired and The Athletic are paywalled sources); the cross-source pair still merges; no headline stored twice. Database: 1,863 articles, 732 with full text. Post Khmer still HTTP 500 (4th run in a row).
</details>

### Human must
1. Review and merge `task/1.3-collect`; tick 1.3 in ROADMAP.
2. ~~Optional: delete the 99 stock-quote rows.~~ Done (approved): `99 deleted`, step 17.
3. ~~Decide open question 3.~~ Decided: fixed (steps 20–22).

### Open questions for the human
1. ~~Google News and robots.txt.~~ Decided: the 10 Google News feeds are disabled.
2. ~~Sites that refuse full text.~~ Decided: kept as headline-only; Engadget and Rest of World added for technology.
3. ~~**Near-identical headlines can merge different articles.**~~ Decided (the human): merge near-identical headlines only across sites; done in steps 20–22. The question was: The similarity rule (≥ 0.9) merged real updates of one story ("kills at least 10…" → "…at least 29…", "defence"/"defense"), but in run 5 also two different articles: "The 9 best **movies** to stream this month" into "The 9 best **TV shows**…", and a daily puzzle-hints post for Oct 14 into Oct 15's. Both wrong pairs came from one source each (Wired; The Athletic): a series of similar posts, not one story. Proposed fix (not done, waiting for your OK): merge *near*-identical headlines only when they come from different sources (exact matches still merge always). Both wrong merges would have been kept apart, and the good merges in steps 6–7 were all across sources. Cost: a source that edits a headline and re-publishes under a new URL could be stored twice. Or keep it as is: the wrong merges so far are lifestyle and puzzle posts.

**Noticed, not done (out of scope):**
- ~~`natalia/feeds.py` still sends the `Mozilla/5.0` user agent.~~ Fixed (step 16).
- ~~Google News feeds are slow on Google's side.~~ Moot: disabled.
- Post Khmer returned HTTP 500 in runs 3, 4 and 5 (worked in runs 1–2 and in 1.1). If it lasts, `uv run python -m natalia.feeds` will show it; consider disabling it.
- The first cold run took 22.9 min before the fixes. A cold run with today's code should be ~6–7 min (the Guardian queue, ~160 pages at ~2.4 s, is the longest), but that's an estimate: runs 2–4 had little new to fetch. The first 07:00 run in 1.9 will show.
- Wired's coupon posts and The Guardian's reviews are stored like news; topic filtering (1.4) is the place to drop them.
