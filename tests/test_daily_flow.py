"""The daily flow under a real Prefect engine (a temporary local server, not the lab's): fake
steps, the real alert path down to bot.send_text. Slow (~10 s), so it is one test."""

from datetime import date

import pytest
from prefect.testing.utilities import prefect_test_harness

from natalia import daily
from natalia.digest import BuildReport


@pytest.fixture(scope="module")
def harness():
    with prefect_test_harness(server_startup_timeout=60):
        yield


def test_flow_runs_the_steps_and_alerts_through_the_bot(harness, monkeypatch):
    calls, sent = [], []

    def build(day, max_requests):
        calls.append((day, max_requests))
        return BuildReport(day=day, model="fake", stories=44, planned=9, stopped=False, missing=[7])

    async def send_text(text):
        sent.append(text)

    monkeypatch.setattr(daily, "collect_step", lambda: calls.append("collect"))
    monkeypatch.setattr(daily, "embed_step", lambda: calls.append("embed"))
    monkeypatch.setattr(daily, "build_step", build)
    monkeypatch.setattr(daily.bot, "send_text", send_text)
    state = daily.natalia_daily(day="2026-10-18", return_state=True)
    assert state.is_completed()
    assert calls == ["collect", "embed", (date(2026, 10, 18), daily.DAILY_MAX_REQUESTS)]
    assert len(sent) == 1 and "1 of 44 stories have no summary" in sent[0]


def test_flow_is_failed_when_the_cap_stops_the_build(harness, monkeypatch):
    sent = []

    async def send_text(text):
        sent.append(text)

    stopped = BuildReport(day=date(2026, 10, 18), model="fake", planned=14, stopped=True)
    monkeypatch.setattr(daily, "collect_step", lambda: None)
    monkeypatch.setattr(daily, "embed_step", lambda: None)
    monkeypatch.setattr(daily, "build_step", lambda day, m: stopped)
    monkeypatch.setattr(daily.bot, "send_text", send_text)
    state = daily.natalia_daily(day="2026-10-18", return_state=True)
    assert state.is_failed()
    assert len(sent) == 1 and "over the cap" in sent[0]
