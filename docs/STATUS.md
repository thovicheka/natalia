# Status

Live progress for agent work. The agent updates this after every step and pushes it (see "Working unattended" in [`CLAUDE.md`](../CLAUDE.md)). Task definitions live in [`ROADMAP.md`](ROADMAP.md).

## Summary

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
