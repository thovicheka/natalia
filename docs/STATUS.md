# Status

Live progress for agent work. The agent updates this after every step and pushes it (see "Working unattended" in [`CLAUDE.md`](../CLAUDE.md)). Task definitions live in [`ROADMAP.md`](ROADMAP.md).

## Summary

**Run of 2026-10-15: 0.1 done (branch `task/0.1-project-setup`, from `origin/main` at 2dca67b). Stopping here.** `docs/PLAN.md` is clean Markdown (wording unchanged). `CLAUDE.md` has the cloud-ai-lab hard rules adapted to Natalia, plus two new ones: leave cloud-ai-lab alone, and message only the human. `docs/ROADMAP.md` turns the plan's 5 build phases into tasks 1.1–5.5, with the agreed decisions and a memory budget. `.env.example` added; `.gitignore` already covered `.env` and `.venv`. Nothing installed, no accounts created, no paid API called, no money spent.

**Human must:** review and merge `task/0.1-project-setup`. Then the 🧑 steps for Phase 1, in the order the tasks need them:
1. **1.1:** review the feed list the agent writes, and decide how to handle paywalled sources (Bloomberg, FT, WSJ, The Athletic): headline + excerpt + link only, or drop them.
2. **1.2:** install PostgreSQL 16 + pgvector (`sudo apt install postgresql postgresql-16-pgvector`), run the role/database commands the agent writes, and put `DATABASE_URL` in `.env`.
3. **1.5:** pick the embedding option from the agent's measurements. An API account is needed only if the local model fails.
4. **1.6:** Anthropic account at console.anthropic.com, **set a monthly spend limit**, create a key, add `ANTHROPIC_API_KEY` to `.env`.
5. **1.7:** approve and run one real digest (the agent gives the command and the cost estimate).
6. **1.8:** create a **new** bot with @BotFather (not the lab's alert bot), add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_OWNER_CHAT_ID` to `.env`, and send the bot `/start`.
7. **1.9:** register the `natalia-daily` deployment and turn on its 07:00 Asia/Phnom_Penh schedule (it spends money daily).

`.env` setup, once: `cp .env.example .env && chmod 600 .env`, then fill in the values as each step above produces them.

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
- **State:** done, committed and pushed; waiting for the human's review and merge
- **Done:** `docs/PLAN.md` restored as Markdown; `CLAUDE.md`, `docs/ROADMAP.md`, `docs/STATUS.md`, `.env.example` written; `.gitignore` checked.
- **Next:** 0.2 (Python project and agent guardrails), then Phase 1.
- **Human must:** review and merge. Tick 0.1 in ROADMAP once merged.

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
</details>

**Noticed, not done (out of scope):**
- The lab worker's 2 flow slots and `MemoryMax=900M` are shared with lab flows. A paused lab GPU approval at 07:00 could delay the digest, and a heavy embedding step could hit the memory cap. Both are flagged in ROADMAP 1.5 and 1.9; changing the worker is the lab's business, not Natalia's.
- Several PLAN.md sources are paywalled (Bloomberg, FT, WSJ, The Athletic), so "full detail" isn't possible for them. That's the 🧑 decision in 1.1.
- The repo has no `.claude/settings.json` deny rules yet; that's task 0.2.
