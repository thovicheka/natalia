# Stage 0 — Project setup

**Tasks:** 0.1, 0.2, 1.6 · **Status:** ✅ done (0.2's live deny-rule check is still the human's, see step 6)

**What you'll have working by the end:** a repo with rules for AI agents, a Python 3.12 project managed by `uv` with tests and lint, agent guardrails, a `.env` for secrets, and a working Gemini free-tier API key.

**How to read this guide:** instructions use placeholders; replace them with your own values. After key steps, an **Example from this build** block shows the real commands and output.

| Placeholder | In this build |
|---|---|
| `<github-username>` | `thovicheka` |
| `<repo>` | `natalia` |
| `<server-name>` (Tailscale name) | `lab` |
| `<username>` (server user) | `thovicheka` |
| `<cloud-project>` (Google Cloud project for the key) | kept private |
| keys, emails, IPs | kept private |

## Prerequisites
- A server you can SSH into, with `git` and `uv` installed. Here: the cloud-ai-lab server (Ubuntu 24.04, 2 vCPU / 4 GB + 4 GB swap), reached over Tailscale. See cloud-ai-lab's `docs/01-server-setup.md`.
- A GitHub account, with an SSH key for the server.
- A Google account (for the Gemini key in step 7).
- Claude Code (or another coding agent) on the server.

> **Adapting:** Natalia shares its server with cloud-ai-lab and uses only its Prefect server. On your own server, everything here is the same; you'll need your own Prefect (or another scheduler) for task 1.9.

## Steps

### 1. Create the repo and clone it *(on the server)*
Create an empty GitHub repo `<repo>` (Python `.gitignore`), then:
```bash
cd ~/projects
git clone git@github.com:<github-username>/<repo>.git
cd <repo>
```
*What it does:* the repo is separate from cloud-ai-lab: its own `.env`, database, bot and docs.

**Work on branches only.** Every task gets a branch `task/<id>-<short-name>` from `origin/main`; agents never commit to `main`, never merge, never force-push. The human reviews and merges each pull request.
```bash
git fetch origin
git switch -c task/<id>-<short-name> origin/main
```

<details><summary>Example from this build</summary>

```console
$ git log --oneline main..origin/main; git log --oneline origin/main..main
(no output: main and origin/main are both at 2dca67b)
$ git switch -c task/0.1-project-setup origin/main
Switched to a new branch 'task/0.1-project-setup'
branch 'task/0.1-project-setup' set up to track 'origin/main'.
```
**Result:** ✅

Later tasks also ran `git branch --unset-upstream` right after branching, so a bare `git push` can never target `main`; `git push -u origin task/<id>-…` then sets the right upstream.
</details>

### 2. Write the rules for agents
Files at the root and in `docs/`:

| File | What it is |
|---|---|
| `CLAUDE.md` | Hard rules for agents (branches only, no `sudo`, no paid APIs without approval, secrets stay in `.env`, no private data to the LLM, message only the human, leave cloud-ai-lab alone). Claude Code reads it at the start of every session. |
| `docs/PLAN.md` | What the human wants. The source of truth for features. |
| `docs/ROADMAP.md` | The task list (IDs, 🧑/🤖 steps, "done when") and the decisions already made. |
| `docs/STATUS.md` | Live progress, updated by the agent after every step. |
| `docs/TASK-TEMPLATE.md` | The prompt format for giving an agent one task. |
| `docs/STYLE.md`, `docs/decisions.md` | How docs are written; why each tool was chosen. |

*What it does:* an agent can work unattended from these alone: it reads the task, does the 🤖 steps, and stops at 🧑 steps with exact commands for the human.

> **Adapting:** start from cloud-ai-lab's CLAUDE.md and change the project-specific parts: what the project is, what it may share with other projects on the machine, and its own extra rules.

### 3. Check `.gitignore` covers secrets and the virtualenv
```bash
git check-ignore -v .env .venv .env.example
```
*What it does:* prints the `.gitignore` rule for each ignored path. `.env` and `.venv` must be listed; `.env.example` must not.

<details><summary>Example from this build</summary>

```console
$ git check-ignore -v .env .venv .env.example
.gitignore:153:.env	.env
.gitignore:155:.venv	.venv
```
**Result:** ✅ GitHub's Python template already ignores both. (Task 1.3 later added `.idea/`, the JetBrains folder.)
</details>

### 4. Check the server's limits
```bash
free -m; nproc
grep VERSION= /etc/os-release; timedatectl | grep 'Time zone'
~/projects/lab-runtime/.venv/bin/prefect version
```
*What it does:* the numbers that shape the decisions: how much RAM is left, which PostgreSQL version apt offers, and the server's time zone.

<details><summary>Example from this build</summary>

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
**Result:** ✅ Ubuntu 24.04 → PostgreSQL 16 from apt. The lab's process pool accepts a `command` job variable, so Natalia's deployment can use its own `.venv` (task 1.9). The clock is UTC, so schedules must name `Asia/Phnom_Penh`.
</details>

### 5. Create `.env` from `.env.example`
```bash
cp .env.example .env && chmod 600 .env
```
*What it does:* `.env.example` (committed) lists every key with a fake value; `.env` (git-ignored, readable only by you) holds the real ones. Fill in each value as its task produces it: `GEMINI_API_KEY` (step 7), `DATABASE_URL` ([stage 2](02-database.md)), the Telegram values (task 1.8).

Never print `.env`. Agents are denied reading it (step 6).

### 6. Python project, tests, lint and agent guardrails
```bash
uv init --app --python 3.12 --name natalia --vcs none
uv add --dev pytest ruff
```
*What it does:* creates `pyproject.toml`, `.python-version` and `uv.lock`; adds the test and lint tools to a dev group in the project's `.venv` (nothing system-wide).

Then lay out the package flat (`natalia/`, not `src/natalia/`): in `pyproject.toml`,
```toml
[tool.uv.build-backend]
module-root = ""
```

> **If you see** a `src/natalia/` folder and a demo `main()` script after `uv init`, **it means** uv 0.13 made a packaged layout. Move the package to `natalia/`, set `module-root = ""` as above, and delete the demo script entry. Also remove the `authors` line uv filled in with your git email, if you don't want it public.

Add `natalia/llm.py` as the **only** module allowed to import `google-genai` (a test enforces it; see [decisions](decisions.md#llm-gemini-flash-on-the-free-tier-over-the-anthropic-api)).

Agent guardrails go in `.claude/settings.json` as `permissions.deny` rules: `sudo`, `su`; push to `main`, force-push; `git merge`; `git reset --hard`; `rm -rf`; reading `.env`; `modal run/deploy/serve`; destructive `rclone`; `prefect deployment run` and `prefect flow-run resume` in every form.

```bash
uv run pytest -q
uv run ruff check . ; uv run ruff format --check .
```

<details><summary>Example from this build</summary>

```console
$ uv --version
uv 0.13.0 (x86_64-unknown-linux-gnu)
$ uv init --app --python 3.12 --name natalia --vcs none
Initialized project `natalia`
$ uv add --dev pytest ruff
 + natalia==0.1.0 (from file:///home/thovicheka/projects/natalia)
 + pytest==9.1.1
 + ruff==0.17.0
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
$ uv run python -c "import json;json.load(open('.claude/settings.json'));print('settings.json: valid JSON')"
settings.json: valid JSON
```
**Result:** ✅ after the layout fix above.
</details>

**Check that a denied command is really blocked** *(🧑, in your own terminal; free)*. The deny rules only load in a Claude Code session **started in** `~/projects/natalia`; a session started elsewhere uses that folder's rules. The test above checks the file, not that Claude Code applies it.
```bash
cd ~/projects/natalia && claude
```
Inside the session: `/permissions` must list Natalia's Deny rules (e.g. `Bash(git merge:*)`, `Bash(sudo:*)`, `Read(./.env)`); asking it to run `git merge --help` must be refused.

> **Don't** test the `.env` rule by asking the agent to read `.env`: if the rule didn't apply, your keys would land in the conversation. Seeing `Read(./.env)` in the Deny list is enough.

<details><summary>Example from this build</summary>

Tasks 0.2 through 1.3 were all run from sessions started in `~/projects/cloud-ai-lab`, so they ran under cloud-ai-lab's rules, and the live check is still open (recorded in STATUS.md under 0.2).

**Result:** ⏳ waiting on the human.
</details>

### 7. 🧑 Gemini API key (free tier) *(in your browser)*
1. Sign in at [aistudio.google.com](https://aistudio.google.com) with a Google account.
2. **Create a Google Cloud project first:** at [console.cloud.google.com](https://console.cloud.google.com), *Select a project → New project*, name it `<cloud-project>`. Don't attach billing.
3. Back in AI Studio, *Get API key → Create API key*, and choose `<cloud-project>`.
4. Put the key in `.env` *(on the server, in your own terminal)*: edit the `GEMINI_API_KEY=` line with `nano .env`.

*What it does:* a free-tier key: no paid account, no billing, no spend limit needed. Keep billing off its project; with billing on, calls past the free quota would be charged.

> **If you see** `Unable to create API key` in AI Studio, **it most likely means** there was no Google Cloud project for the key to live in, and AI Studio couldn't create one for you. Create the project yourself (step 2), then create the key and pick that project.

Then test the key without spending any generation quota: list the models.
```bash
cd ~/projects/natalia
set -a; . ./.env; set +a        # load .env into this shell only; prints nothing
curl -s -H "x-goog-api-key: $GEMINI_API_KEY" \
  https://generativelanguage.googleapis.com/v1beta/models | grep -o '"models/gemini-[^"]*"' | head
```
*What it does:* a `GET /v1beta/models` request, which only lists models; it generates nothing. The key goes in a header, not the URL, and the output shows model names only. Run it in your own terminal, not through the agent (the agent never reads `.env`).

Expected: a list of model names, including `"models/gemini-2.5-flash"`. A bad key gives an `API_KEY_INVALID` error instead (the `grep` then prints nothing; drop it to see the message).

<details><summary>Example from this build (reported by the human, 2026-10-15)</summary>

- Creating a key in AI Studio first failed with **"Unable to create API key"**. ❌
- **Cause:** no Google Cloud project to hold the key. **Fix:** created a Cloud project first, then created the key in AI Studio and chose that project. ✅
- Models-list test (`GET /v1beta/models`): returned the model list, including `gemini-2.5-flash`. ✅
- `GEMINI_API_KEY` added to `.env`. The agent did not read `.env` or call the API.

**Result:** ✅ (task 1.6)
</details>

## Verify it worked
```bash
cd ~/projects/natalia
uv run pytest -q
uv run ruff check .
git check-ignore .env
```
Expected: all tests pass, `All checks passed!`, and `.env` printed (it's ignored).

<details><summary>Example from this build (2026-10-16, after tasks 1.1–1.3 added their tests)</summary>

```console
$ uv run pytest -q
...................................................................      [100%]
67 passed in 0.88s
```
**Result:** ✅
</details>
