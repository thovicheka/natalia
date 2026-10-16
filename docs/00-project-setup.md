# Stage 0 — Project setup

**Tasks:** 0.1, 0.2, 0.4, 1.6 · **Status:** ✅ done

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

### 6b. Check the deny rules really block, and close the gaps *(task 0.4)*
The test above checks the file's content, not that Claude Code applies it. Do this once, in a Claude Code session **started in** `~/projects/natalia` (a session started elsewhere loads that folder's rules instead):
```bash
cd ~/projects/natalia && claude
```
Then ask the agent to try each guarded action with a **harmless** command, one that does nothing even if the rule fails:

| Guarded action | Harmless probe |
|---|---|
| `sudo`, `su` | `sudo -n true` (never prompts; fails without a cached password), `su --help` |
| push to `main` | `git push origin main --dry-run` |
| force-push | `git push --force --dry-run origin <your-branch>` |
| `git merge`, `git reset --hard` | `git merge --help`, `git reset --hard --help` |
| `rm -rf` | `rm -rf <scratch-dir>/does-not-exist` |
| reading `.env` | a **decoy** `.env` with fake content (`mkdir .deny-check && printf 'DECOY=x\n' > .deny-check/.env`), then the Read tool and `cat` on it |
| Modal, rclone, Prefect runs | `modal run --help`, `rclone purge --help`, `<lab-venv>/bin/prefect deployment run --help` |

*What it does:* each probe must come back as `Permission to use Bash with command … has been denied` (or, for the Read tool, `File is in a directory that is denied by your permission settings`). Then try **other spellings of the same action** (table below): Claude Code's Bash rules match the command text, so `git push origin main` being blocked says nothing about `git push origin task/x:main`.

> **Don't** test the `.env` rule on the real `.env`: if the rule didn't apply, your keys would land in the conversation. Use the decoy, then delete it.

> **If** a `Write(...)` deny rule doesn't block the Write tool, **it's because** Claude Code has no `Write` rule type: `Edit(...)` rules cover every tool that writes files (Edit and Write). Use `Edit(path)` to protect a path from writes.

> **If** a rule you just added doesn't block yet, wait a second: the session reloads `.claude/settings.json` on change, but a command sent in the same batch as the edit still sees the old rules.

> **If you see** an edit to `.claude/settings.json` refused with `[Self-Modification]`, **it means** Claude Code's auto mode classifier stopped the agent from changing its own permissions (here: removing two deny rules). Adding rules was allowed; removing them needs the human.

<details><summary>Example from this build (2026-10-16, session started in <code>~/projects/natalia</code>)</summary>

The rules from 0.2 all block:
```console
$ sudo -n true
Permission to use Bash with command sudo -n true has been denied.
$ git push origin main --dry-run
Permission to use Bash with command git push origin main --dry-run has been denied.
$ git push --force --dry-run origin task/0.4-deny-check
Permission to use Bash with command git push --force --dry-run origin task/0.4-deny-check has been denied.
$ git merge --help
Permission to use Bash with command git merge --help has been denied.
Read(.deny-check/.env)
File is in a directory that is denied by your permission settings.
$ cd .deny-check && cat .env
Permission to use Bash with command cd …/.deny-check && cat .env has been denied.
```
Also denied: `su --help`, `rm -rf …/does-not-exist`, `git reset --hard --help`, `modal run --help`, `rclone purge --help`, `…/lab-runtime/.venv/bin/prefect deployment run --help`, `true && sudo -n true` (Claude Code checks each part of `&&`), and `head .env`, `grep DECOY .deny-check/.env`, `cat /full/path/.env` (Claude Code applies `Read` rules to file-reading shell commands too).

**Result:** ✅ for every rule in the file.

Then the gaps. Each of these **ran** under 0.2's rules (all dry runs or decoys, so nothing happened):

| Probe | Under 0.2's rules | Rule added | After |
|---|---|---|---|
| `bash -c 'sudo -n true'` | ran (`sudo: a password is required`) | `Bash(*sh -c *sudo*)` (+ `env`, `xargs`, `timeout`, `nohup`, `sudo -S`, `pkexec`, `doas`) | denied |
| `git push --dry-run origin task/0.4-deny-check:main` | ran (`Everything up-to-date`) | `Bash(git push*:main*)` | denied |
| `git push --dry-run -u origin main` | ran (git: `rejected … non-fast-forward`) | `Bash(git push* main)`, `Bash(git push* main *)` | denied |
| `git push --dry-run origin HEAD:refs/heads/main` | ran | `Bash(git push*refs/heads/main*)` | denied |
| `git push --dry-run origin +task/0.4-deny-check` (force via `+`) | ran (`* [new branch]`, dry run) | `Bash(git push* +*)`, `Bash(git push* --force*)`, `Bash(git push* -f*)` | denied |
| `rm -fr <scratch>/rmtest` | ran | `Bash(rm -fr*)`, `rm -r*`, `rm -R*`, `rm * -r*`, … | denied |
| `git clean -n` | ran | `Bash(git clean*)` (`git clean -fdx` would delete `.env` and `.venv`) | denied |
| `python3 -c "print(open('.deny-check/.env').read())"` | **printed the decoy** | `Bash(*python*'.env*)`, `Bash(*python*".env*)`, `Bash(*python*/.env*)` | denied |
| Read tool on a decoy `.env` **outside** the project | **printed the decoy** | `Read(~/**/.env)`, `Read(//**/.env)` | denied |

The last one matters most: `Read(**/.env)` in a project's settings only covers the project, so `~/projects/cloud-ai-lab/.env` was readable. Also added: `Edit(**/.env)` and `Edit(~/**/.env)` (no writes to any `.env`), `Edit(~/projects/cloud-ai-lab/**)` and `Edit(~/projects/lab-runtime/**)` (CLAUDE.md rule 9), `Bash(find *-delete*)`, and `prefect deployment delete` / `work-pool delete` / `work-pool pause`.

```console
$ git ls-remote origin main task/0.4-deny-check     # nothing reached GitHub
993e652850c842b5d6f7cfc638a3dc557d868b1f	refs/heads/main
```

Problems hit:
- ❌ A first, broad `Bash(*python*.env*)` also blocked `python3 -c "…os.environ…"` (`os.environ` contains `.env`). **Fix:** match `'.env`, `".env` and `/.env` only. ✅ `os.environ ok: True`.
- ❌ `Write(~/projects/…/**)` and `Write(//…/**)` rules didn't block the Write tool (probe files on a test path were created). **Cause:** no `Write` rule type. **Fix:** `Edit(...)` rules; re-test: Write on both test paths and on a decoy `.env` → `File is in a directory that is denied`. ✅
- ⚠️ Removing the now-useless `Write(**/.env)` and `Write(~/**/.env)` lines was refused (`[Self-Modification]`); they're harmless no-ops and stay.

False-positive checks: `git push --dry-run -u origin task/0.4-deny-check` still runs; `uv run pytest` passes.

**Result:** ✅ 81 deny rules; every probe above is refused.
</details>

**Limits.** Deny rules match command text, so they're a seatbelt, not a wall: `cp .env x && cat x` is blocked (the `.env` read is caught), but a script file that opens `.env` is not. The real backstops are elsewhere: `sudo` needs a password the agent doesn't have, and GitHub can refuse pushes to `main` (branch protection, a 🧑 step in the GitHub web UI: *Settings → Branches → Add rule* for `main`, "Require a pull request before merging", no force pushes).

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
