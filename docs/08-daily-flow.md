# Stage 8 — The daily build on Prefect

**Tasks:** 1.9 · **Status:** 🧑 code and tests done; installing the worker, registering the deployment, the first run and turning the schedule on are the human's

**What you'll have working by the end:** every day at 05:00 Asia/Phnom_Penh, a Prefect flow `natalia-daily` collects the news and builds the day's digest (summaries by Claude Haiku, capped at 12 requests), so it's stored before you wake. Nothing is pushed: `/digest` in Telegram sends yesterday's and today's digests. You get a short Telegram message only when something needs a look. It runs in Natalia's own work pool and worker on the lab's Prefect server, so lab flows can't hold it up.

| Placeholder | In this build |
|---|---|
| `<date>` | `2026-10-17` |
| `<schedule-id>` | the id `prefect deployment schedule ls` prints |

## Prerequisites
- [Stage 6](06-digest.md) and [Stage 7](07-bot.md): digests build, and the bot runs from the runtime worktree `~/projects/natalia-runtime` with its own `.env`.
- The lab's Prefect server running (`systemctl is-active prefect-server`), UI at `http://lab:4200` over Tailscale.
- `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN` and `TELEGRAM_OWNER_CHAT_ID` in the runtime's `.env`.

## How it works
```
Prefect server (lab's)  ──05:00 Asia/Phnom_Penh──►  pool "natalia"  ──►  natalia-worker.service
                                                                           │ (limit 1, MemoryMax 600M)
                                                                           ▼
                                   natalia-daily: collect ──► digest build (≤ 12 Haiku requests)
                                                                           │
                         only if something needs a look ──► Telegram message to the owner
```
- **`natalia/daily.py`**: the flow. `collect` (free: public feeds and pages), then `digest build` for today with `max_requests=12`. A full day plans one request per topic (at most 9); the cap leaves room for retries and stops a bug from sending more. Worst case about $0.013 a day.
- **Alerts** (one short plain-text Telegram message to the owner, never to anyone else):
  - a step fails: "collect failed: …" or "digest build failed: …". The run is **Failed**.
  - the plan is over the cap: "digest not built: the plan needs N LLM requests, over the cap of 12. Nothing was sent to the LLM." The run is **Failed**, nothing is sent or stored.
  - the digest is empty, or some stories have no summary. The run is still **Completed**: a rebuild by hand only sends the missing stories.
  - If the alert itself can't be sent, it's logged; the run's own result isn't hidden.
- **No retries**: a retry could resend LLM requests. Rebuilding by hand is cheap, because a build only sends stories without a summary.
- **The 05:00 cut-off.** A day's digest covers the 24 h before 05:00 Asia/Phnom_Penh (`natalia.topics.DIGEST_TIME`, 07:00 before this stage). The window ends when the build runs; with the old 07:00 cut-off, articles from 05:00–07:00 would fall in a window that was already built.
- **Its own pool and worker** ([why](decisions.md#daily-run-natalias-own-prefect-pool-and-worker-built-at-0500-alerts-only-task-19)): the lab worker's 2 slots can be held for up to 24 h by GPU flows waiting for approval, and its 900M cap is shared with lab training. `natalia-worker.service` runs from `~/projects/natalia-runtime` (a git worktree on `main`), so branch switches in `~/projects/natalia` never change what runs; the deployment reads its code from there at each run. The worker creates the pool `natalia` on its first heartbeat.
- **Secrets** stay in the runtime's `.env`, read by the flow itself. The unit file holds none (unit files are world-readable).

## Steps

### 1. 🧑 Update the runtime worktree *(after merging `task/1.9-daily`)*
```bash
git -C ~/projects/natalia-runtime pull
```
```bash
cd ~/projects/natalia-runtime && uv sync --no-dev
```
```bash
sudo systemctl restart natalia-bot
```
*What it does:* brings `main` into the runtime, installs Prefect 3.8.8 into its `.venv` (same version as the lab's server), and restarts the bot so `/digest` sends yesterday's and today's digests.

### 2. 🧑 Install the worker *(sudo)*
```bash
sudo cp ~/projects/natalia/deploy/natalia-worker.service /etc/systemd/system/
```
```bash
sudo systemctl daemon-reload
```
```bash
sudo systemctl enable --now natalia-worker
```
```bash
systemctl status natalia-worker --no-pager
```
*What it does:* starts the worker now and at every boot, restarts it 10 s after a crash, caps it (and the flow it runs) at `MemoryMax=600M`. Expected: `active (running)`, and a log line saying the worker started and is polling pool `natalia`.

> **If** `systemctl status` shows `status=203/EXEC`, **it means** the runtime's `.venv` has no Prefect yet: do step 1.

```bash
cd ~/projects/natalia-runtime && .venv/bin/prefect work-pool ls
```
*Expected:* `natalia` (type `process`) next to `lab`.

> **If** a Prefect command starts a temporary server or can't find the pool, **it means** `PREFECT_API_URL` isn't set for it: put `PREFECT_API_URL=http://127.0.0.1:4200/api ` in front of the command (Natalia's `.env` sets it, and Prefect reads `.env` from the current folder).

### 3. 🧑 Register the deployment, schedule OFF
```bash
cd ~/projects/natalia-runtime && .venv/bin/python -m natalia.daily deploy
```
*What it does:* registers `natalia-daily/natalia-daily` in pool `natalia`, with a 05:00 Asia/Phnom_Penh schedule that is **inactive**. Nothing runs yet, nothing is uploaded: each run reads the code from `~/projects/natalia-runtime`. It refuses to run from any other checkout.
```bash
cd ~/projects/natalia-runtime && .venv/bin/prefect deployment schedule ls natalia-daily/natalia-daily
```
*Expected:* one schedule, `cron: 0 5 * * *`, timezone `Asia/Phnom_Penh`, **Active: False**.

### 4. 🧑 Run it once by hand
```bash
cd ~/projects/natalia-runtime && .venv/bin/prefect deployment run natalia-daily/natalia-daily
```
*What it does:* one run now (or **Quick run** on the deployment's page in the UI). It collects (~15 minutes), then builds today's digest. **Cost:** only the stories without a summary are sent; a full day is ~9 requests, ~$0.01. A run on a day whose digest was stored before this stage (07:00 window) replaces it with the 05:00-window picks, ~9 requests. See today's plan first, for free: `uv run python -m natalia.digest build --dry-run` in `~/projects/natalia`.

Watch it:
```bash
journalctl -u natalia-worker -f
```
Expected: the run is **Completed** at `http://lab:4200` (Flow runs), no Telegram message (nothing needed a look), and `/digest` in Telegram sends the new digest.

```bash
systemctl show natalia-worker -p MemoryCurrent -p MemoryPeak
```
*What it does:* the worker's memory, the flow included. Record the peak in `docs/STATUS.md`.

### 5. 🧑 Turn the schedule on
In the UI: **Deployments → natalia-daily → the schedule's toggle**. Or:
```bash
cd ~/projects/natalia-runtime && .venv/bin/prefect deployment schedule resume natalia-daily/natalia-daily <schedule-id>
```
*What it does:* from now on the flow runs every day at 05:00 Asia/Phnom_Penh. To stop it: `prefect deployment schedule pause natalia-daily/natalia-daily <schedule-id>`.

### 6. Tests
```bash
uv run pytest -q tests/test_daily.py tests/test_daily_flow.py
```
*What it does:* `test_daily.py` runs the steps with fakes: collect then build with the cap, no message on success, an alert and a Failed run when collect or the build fails or the plan is over the cap, an alert without failing for an empty or incomplete digest, a failing alert never hiding the error, long errors cut. `test_daily_flow.py` runs the real flow on Prefect's temporary local test server (not the lab's), down to `bot.send_text` (~15 s).

### 7. Memory and time, measured without Prefect or Haiku
The flow's work run in one process: Prefect and Natalia imported, a real `collect` (free), then a **dry-run** build of today (nothing sent).
```bash
/usr/bin/time -v uv run python measure_daily.py      # a throwaway script in the agent's scratch folder
```
<details><summary>Example from this build (2026-10-17, ~08:30 UTC)</summary>

```console
imports (prefect + natalia): 94 MB
run time 929 s, 661 HTTP requests, peak memory (max RSS) 208 MB
after collect: 208 MB peak, 931 s
plan: 9 requests (general, economics, world-politics, technology, science, sport, crypto, markets, cambodia); limit 12
[dry run] general: 5 stories, ~2633 input tokens
…
[dry run] cambodia: 5 stories, ~2818 input tokens
after dry-run build of 2026-10-17: planned 9, 211 MB peak, 931 s
	Elapsed (wall clock) time (h:mm:ss or m:ss): 15:31.40
	Maximum resident set size (kbytes): 216336
```
**Result:** ✅ **211 MB peak**, with the worker (~80–100 MB) about 310 MB, well under `MemoryMax=600M`. Collect takes **~15.5 minutes**, so the digest is stored by about 05:20; the flow's timeout is 60 minutes. With the new 05:00 cut-off every topic of 2026-10-17 has new picks, so a build of that day plans 9 requests (~$0.01) and replaces the stored 07:00-window digest.
</details>

## Verify it worked
After the schedule is on, two mornings in a row:
- `http://lab:4200` → Flow runs: `natalia-daily` **Completed** a few minutes after 05:00.
- `/digest` in Telegram sends yesterday's and today's digests.
- `systemctl show natalia-worker -p MemoryPeak` stays well under 600 MB.
