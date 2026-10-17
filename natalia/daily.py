"""Natalia's daily flow (task 1.9): collect, embed, then build and store the day's digest.

    uv run python -m natalia.daily deploy    # register it, schedule OFF (from natalia-runtime)

Runs on the lab's self-hosted Prefect, in Natalia's own work pool `natalia` (its own worker,
`deploy/natalia-worker.service`, so lab flows waiting for approval can't hold its slot). The
schedule is 05:00 Asia/Phnom_Penh, the digest's cut-off (natalia.topics.DIGEST_TIME), and it is
registered OFF: the owner turns it on after a manual test run.

Memory (task 1.9b): collect (~210 MB) and embed (~440 MB, the local model) each run in their own
child process, one after the other, so each one's memory is freed when it exits; the flow's own
process holds only Prefect (~95 MB) and the digest build. In one process, Python would keep
collect's memory and the embed step would add to it. Embed failing doesn't stop the digest
(only chat search misses the new articles): the owner is alerted and the run ends Failed.

On success nothing is sent: the bot's /digest serves the stored digest. The owner gets one short
Telegram message only when something needs a look: a step failed, the plan was over the request
cap (nothing sent to the LLM), or the digest came out empty or with stories left unsummarized.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from collections import deque
from datetime import date, datetime
from pathlib import Path

from prefect import flow

from natalia import bot, db, digest
from natalia.topics import DIGEST_TIME, LOCAL_TZ

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = Path.home() / "projects" / "natalia-runtime"  # the worktree on main that runs flows
POOL = "natalia"
DEPLOYMENT = "natalia-daily"
SCHEDULE = f"{DIGEST_TIME.minute} {DIGEST_TIME.hour} * * *"  # 05:00, in LOCAL_TZ
DAILY_MAX_REQUESTS = 12  # one request per topic (at most 9) + room for retries; ~$0.013 at most
FLOW_TIMEOUT_S = 3600
ALERT_CHARS = 300  # of an error message quoted in an alert
STEP_TIMEOUT_S = {"collect": 2400, "embed": 900}


class DailyError(RuntimeError):
    """The run needs the owner's attention (already alerted); the flow run is marked Failed."""


class StepError(RuntimeError):
    """A child process (collect or embed) failed."""


def run_child(name: str, args: list[str], *, popen=subprocess.Popen, log=print) -> None:
    """Run `python -m <args>` in a child process, its output going to the flow's log line by
    line. Raises StepError (with the last lines) if it fails or runs over its timeout."""
    tail: deque[str] = deque(maxlen=3)
    with popen(
        [sys.executable, "-m", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    ) as p:
        for line in p.stdout:
            line = line.rstrip()
            log(line)
            if line.strip():
                tail.append(line.strip())
        try:
            code = p.wait(timeout=STEP_TIMEOUT_S[name])
        except subprocess.TimeoutExpired:
            p.kill()
            raise StepError(f"{name} ran over {STEP_TIMEOUT_S[name]} s") from None
    if code != 0:
        raise StepError(f"{name} exited with code {code}: {' | '.join(tail)}")


def collect_step() -> None:
    run_child("collect", ["natalia.collect"])


def embed_step() -> None:
    run_child("embed", ["natalia.embeddings", "embed"])


def build_step(day: date, max_requests: int) -> digest.BuildReport:
    with db.connect(autocommit=True) as conn:
        return digest.build(conn, day, max_requests=max_requests, log=print)


def alert_owner(text: str) -> None:
    asyncio.run(bot.send_text(text))


def _short(e: BaseException) -> str:
    text = f"{type(e).__name__}: {e}".strip()
    return text if len(text) <= ALERT_CHARS else text[: ALERT_CHARS - 1] + "…"


def run_daily(
    day: date | None = None,
    *,
    max_requests: int = DAILY_MAX_REQUESTS,
    collect_step=collect_step,
    embed_step=embed_step,
    build_step=build_step,
    alert=alert_owner,
    log=print,
) -> dict:
    """Collect, embed, then build `day`'s digest (default: today, local time). Alerts the owner
    and raises DailyError if collect or the build fails or the build was stopped by the cap; if
    embed fails, alerts, still builds the digest, then raises. Alerts (without failing) if the
    digest is empty or has stories without a summary."""
    day = day or datetime.now(LOCAL_TZ).date()

    def notify(text: str) -> None:
        try:
            alert(f"⚠️ Natalia daily run, {day}: {text}")
        except Exception as e:  # the alert must never hide the run's own result
            log(f"could not send the alert to the owner: {_short(e)}")

    try:
        collect_step()
    except Exception as e:
        notify(f"collect failed: {_short(e)}. No digest built.")
        raise DailyError(f"collect failed: {e}") from e
    embed_error = None
    try:
        embed_step()
    except Exception as e:
        embed_error = e
        notify(
            f"embed failed: {_short(e)}. Building the digest anyway; chat won't find today's "
            "new articles until `uv run python -m natalia.embeddings embed` runs."
        )
    try:
        r = build_step(day, max_requests)
    except Exception as e:
        notify(f"digest build failed: {_short(e)}")
        raise DailyError(f"digest build failed: {e}") from e

    summary = {
        "day": day.isoformat(),
        "stories": r.stories,
        "planned": r.planned,
        "requests": r.requests,
        "summarized": r.summarized,
        "reused": r.reused,
        "missing": len(r.missing),
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
    }
    if r.stopped:
        notify(
            f"digest not built: the plan needs {r.planned} LLM requests, over the cap of "
            f"{max_requests}. Nothing was sent to the LLM. Check with "
            f"`uv run python -m natalia.digest build --dry-run --date {day}`."
        )
        raise DailyError(f"plan of {r.planned} requests is over the cap of {max_requests}")
    if r.stories == 0:
        notify("the digest is empty (no stories in the window). Did collect find anything?")
    elif r.missing:
        notify(
            f"digest built, but {len(r.missing)} of {r.stories} stories have no summary. "
            f"A rebuild fills only those: `uv run python -m natalia.digest build --date {day}`."
        )
    log(
        f"digest {day}: {r.stories} stories, {r.reused} reused, {r.summarized} new, "
        f"{len(r.missing)} missing; {r.requests} requests"
    )
    if embed_error is not None:
        raise DailyError(f"embed failed: {embed_error}") from embed_error
    return summary


@flow(name=DEPLOYMENT, log_prints=True, retries=0, timeout_seconds=FLOW_TIMEOUT_S)
def natalia_daily(day: str | None = None, max_requests: int = DAILY_MAX_REQUESTS) -> dict:
    """Collect, embed, then build and store the day's digest. `day`: YYYY-MM-DD (default:
    today)."""
    return run_daily(
        date.fromisoformat(day) if day else None,
        max_requests=max_requests,
        collect_step=collect_step,
        embed_step=embed_step,
        build_step=build_step,
        alert=alert_owner,
    )


def deploy() -> int:
    """Register the deployment on the Prefect server, schedule OFF. Code is read from
    natalia-runtime when each run starts; nothing is uploaded anywhere."""
    from prefect.schedules import Cron

    if ROOT != RUNTIME:
        print(f"register from {RUNTIME} (the worktree on main), not {ROOT}")
        return 1
    natalia_daily.from_source(source=str(ROOT), entrypoint="natalia/daily.py:natalia_daily").deploy(
        name=DEPLOYMENT,
        work_pool_name=POOL,
        schedules=[Cron(SCHEDULE, timezone=str(LOCAL_TZ), active=False)],
        description="Collect, embed, then build and store the day's digest (tasks 1.9, 1.9b).",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("deploy", help="register the deployment, schedule OFF")
    parser.parse_args(argv)
    return deploy()


if __name__ == "__main__":
    raise SystemExit(main())
