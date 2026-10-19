# Stage 8 — The daily build on Prefect

**Tasks:** 1.9, 1.9b (embed step) · **Status:** 🧑 code and tests done; installing the worker, registering the deployment, the first run and turning the schedule on are the human's

**What you'll have working by the end:** every day at 05:00 Asia/Phnom_Penh, a Prefect flow `natalia-daily` collects the news, embeds the new articles (for chat, [Stage 9](09-chat.md)) and builds the day's digest (summaries by Claude Haiku, capped at 12 requests), so it's stored before you wake. Nothing is pushed: `/digest` in Telegram sends yesterday's and today's digests. You get a short Telegram message only when something needs a look. It runs in Natalia's own work pool and worker on the lab's Prefect server, so lab flows can't hold it up.

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
                                                                           │ (limit 1, MemoryMax 700M)
                                                                           ▼
          natalia-daily: collect ──► embed ──► digest build (≤ 12 Haiku requests)
                         (child)      (child)   (in the flow's process)
                                                                           │
                         only if something needs a look ──► Telegram message to the owner
```
- **`natalia/daily.py`**: the flow. `collect` (free: public feeds and pages), then `embed` (free: the local model, new articles only), then `digest build` for today with `max_requests=12`. A full day plans one request per topic (at most 9); the cap leaves room for retries and stops a bug from sending more. Worst case about $0.013 a day.
- **Alerts** (one short plain-text Telegram message to the owner, never to anyone else):
  - a step fails: "collect failed: …" or "digest build failed: …". The run is **Failed**.
  - embed fails: "embed failed: … Building the digest anyway". The digest is still built (it doesn't need vectors); only chat misses the new articles until `uv run python -m natalia.embeddings embed` runs. The run ends **Failed** so it shows.
  - the plan is over the cap: "digest not built: the plan needs N LLM requests, over the cap of 12. Nothing was sent to the LLM." The run is **Failed**, nothing is sent or stored.
  - the digest is empty, or some stories have no summary. The run is still **Completed**: a rebuild by hand only sends the missing stories.
  - If the alert itself can't be sent, it's logged; the run's own result isn't hidden.
- **No retries**: a retry could resend LLM requests. Rebuilding by hand is cheap, because a build only sends stories without a summary.
- **The 05:00 cut-off.** A day's digest covers the 24 h before 05:00 Asia/Phnom_Penh (`natalia.topics.DIGEST_TIME`, 07:00 before this stage). The window ends when the build runs; with the old 07:00 cut-off, articles from 05:00–07:00 would fall in a window that was already built.
- **Its own pool and worker** ([why](decisions.md#daily-run-natalias-own-prefect-pool-and-worker-built-at-0500-alerts-only-task-19)): the lab worker's 2 slots can be held for up to 24 h by GPU flows waiting for approval, and its 900M cap is shared with lab training. `natalia-worker.service` runs from `~/projects/natalia-runtime` (a git worktree on `main`), so branch switches in `~/projects/natalia` never change what runs; the deployment reads its code from there at each run. The worker creates the pool `natalia` on its first heartbeat.
- **Collect and embed run in their own processes** (task 1.9b): `python -m natalia.collect`, then `python -m natalia.embeddings embed`, each started by the flow, their output streamed into the flow's log, their memory freed when they exit. In the flow's own process, Python would keep collect's ~210 MB and the model (~390 MB) would add to it. Peak at the embed step: worker 82 + flow ~95 + embed ~390 ≈ **570 MB**, hence `MemoryHigh=600M`, `MemoryMax=700M` (step 8). Timeouts: collect 40 min, embed 15 min.
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
*What it does:* starts the worker now and at every boot, restarts it 10 s after a crash, caps it (and the flow it runs) at `MemoryMax=600M` (700M since task 1.9b, step 8). Expected: `active (running)`, and a log line saying the worker started and is polling pool `natalia`.

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

<details><summary>Example from this build (first manual run, 2026-10-17 09:01 UTC)</summary>

```console
$ systemctl show natalia-worker -p MemoryCurrent -p MemoryPeak -p MemoryMax
MemoryCurrent=152260608
MemoryPeak=304340992
MemoryMax=629145600
$ grep -E "^(anon|file) " /sys/fs/cgroup/system.slice/natalia-worker.service/memory.stat
anon 85778432
file 58679296
```
**Result:** ✅ run `radiant-inchworm` **Completed** in 313 s. Peak **290 MiB** for the worker and the flow together, under the 600M cap. Idle **145 MiB**: 82 MiB of it is the worker's own memory (`anon`), 56 MiB page cache (`file`) that the kernel frees under pressure.
</details>

> **Since the embed step** (task 1.9b): collect and embed run as child processes, and the caps are `MemoryHigh=600M` / `MemoryMax=700M` (step 8).

### 5. 🧑 Turn the schedule on
In the UI: **Deployments → natalia-daily → the schedule's toggle**. Or:
```bash
cd ~/projects/natalia-runtime && .venv/bin/prefect deployment schedule resume natalia-daily/natalia-daily <schedule-id>
```
*What it does:* from now on the flow runs every day at 05:00 Asia/Phnom_Penh. To stop it: `prefect deployment schedule pause natalia-daily/natalia-daily <schedule-id>`.

*Verify:* the next run is already waiting. If this lists nothing, the schedule isn't creating runs (see below):
```bash
curl -s -X POST http://127.0.0.1:4200/api/flow_runs/filter -H 'content-type: application/json' \
  -d '{"flow_runs":{"state":{"type":{"any_":["SCHEDULED"]}}}}' | python3 -c "import json,sys; [print(r['name'], r['expected_start_time']) for r in json.load(sys.stdin)]"
```

<details><summary>Example from this build</summary>

The schedule was turned on 2026-10-17 14:08 UTC. ❌ No run came on the 18th or the 19th, and no alert, because no run was ever created. The deployment looked fine (active, not paused, `READY`, worker polling), but there were 0 scheduled runs on the server. The lab server's log showed the scheduler failing every minute from 14:08:27 on:
```console
$ journalctl -u prefect-server --no-pager -q | grep -A30 "14:08:27.123" | tail -3
… sqlalchemy/ext/hybrid.py", line 1851, in prop
…     raise exc.InvalidRequestError(
… sqlalchemy.exc.InvalidRequestError: Can't evaluate bulk DML statement; please supply a bulk_dml decorated function
```
*Error:* the scheduler can't insert scheduled runs. *Cause:* the lab's Prefect 3.8.8 allows any `sqlalchemy <3.0`, so 2.1.4 was installed. SQLAlchemy 2.1 refuses the bulk insert of `FlowRun` rows that carry `state`, a property with a setter. No lab deployment had a schedule before, so it went unnoticed. *Fix (cloud-ai-lab's side, by the human):* pin SQLAlchemy below 2.1 there and restart the server:
```bash
# 1. In cloud-ai-lab (its repo, its own branch and PR; Natalia's agent doesn't edit it):
cd ~/projects/cloud-ai-lab && uv add "sqlalchemy[asyncio]>=2.0,<2.1"   # locks 2.0.55
# 2. After merging, on the server:
git -C ~/projects/lab-runtime pull --ff-only && (cd ~/projects/lab-runtime && uv sync)
sudo systemctl restart prefect-server
# 3. Check: no new scheduler errors, and natalia-daily's next runs exist
journalctl -u prefect-server --since "-3min" --no-pager | grep -c "Can't evaluate bulk DML"   # expect 0
curl -s -X POST http://127.0.0.1:4200/api/flow_runs/filter -H 'content-type: application/json' \
  -d '{"flow_runs":{"state":{"type":{"any_":["SCHEDULED"]}}}}' | python3 -c "import json,sys; [print(r['name'], r['expected_start_time']) for r in json.load(sys.stdin)]"
```
</details>

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

### 8. The embed step's memory, and the new caps *(task 1.9b)*
The plan (ROADMAP 1.9b) assumed ~340 MB for the embed child. Measured, it was more, and a smaller batch fixed most of it.
```bash
/usr/bin/time -v uv run python -m natalia.embeddings embed
```
<details><summary>Example from this build (2026-10-17: 817 articles without a vector, batch 16)</summary>

```console
  817/817 embedded
embedded 817 articles in 34 s, 4.1 s per 100 articles
memory: 319 MB now, 438 MB peak
	Maximum resident set size (kbytes): 448628
```
**Result:** ⚠️ **438 MB**, as for all 2,614 articles in Stage 5: articles go through in chunks of 256, so the peak doesn't grow with the backlog. With the worker and the flow that's ~615 MB, over the plan's 550M. The batch size (texts per model run) was the cause: 400 real articles, one process each (`batch_probe.py`, a throwaway script in the agent's scratch folder):
```console
batch 16: 400 texts in 11.7 s, peak 402 MB
batch 8: 400 texts in 11.0 s, peak 354 MB
batch 4: 400 texts in 12.2 s, peak 334 MB
```
**Fix:** `BATCH = 8` in `natalia/embeddings.py`: ~50 MB less, no slower. The int8 model quantizes each batch with its own range, so vectors differ slightly: cosine ≥ 0.995 (mean 0.997) between batch 16 and 8 on 64 real articles, far below the 0.03–0.08 between related and unrelated articles ([Stage 9](09-chat.md) step 2). Stored vectors stay valid; nothing is re-embedded. Expected peak now ~390 MB for the child, ~570 MB with the worker and the flow.
</details>

New caps in `deploy/natalia-worker.service`: `MemoryHigh=600M` (above the ~570 MB peak, so the embed step isn't throttled every morning) and `MemoryMax=700M`. Installed with the bot's new caps, [Stage 9](09-chat.md) step 5 (`sudo`). Then, after the next run:
```bash
systemctl show natalia-worker -p MemoryPeak
```
Record it in `docs/STATUS.md`.

## Verify it worked
After the schedule is on, two mornings in a row:
- `http://lab:4200` → Flow runs: `natalia-daily` **Completed** a few minutes after 05:00.
- `/digest` in Telegram sends yesterday's and today's digests.
- `systemctl show natalia-worker -p MemoryPeak` stays under 700 MB (expected ~570 MB with the embed step).
