"""The daily flow (task 1.9): steps in order, alerts only when something needs a look."""

from datetime import date

import pytest

from natalia import daily
from natalia.digest import BuildReport

DAY = date(2026, 10, 18)


def report(**kw):
    r = BuildReport(day=DAY, model="fake", stories=44, planned=9, requests=9, summarized=44)
    for k, v in kw.items():
        setattr(r, k, v)
    return r


class Run:
    """Fake steps and alert; records what happened, in order."""

    def __init__(
        self, r=None, collect_error=None, build_error=None, alert_error=None, embed_error=None
    ):
        self.r, self.collect_error, self.build_error = r or report(), collect_error, build_error
        self.alert_error, self.embed_error = alert_error, embed_error
        self.calls, self.alerts, self.logs = [], [], []

    def collect(self):
        self.calls.append("collect")
        if self.collect_error:
            raise self.collect_error

    def embed(self):
        self.calls.append("embed")
        if self.embed_error:
            raise self.embed_error

    def build(self, day, max_requests):
        self.calls.append(("build", day, max_requests))
        if self.build_error:
            raise self.build_error
        return self.r

    def alert(self, text):
        self.alerts.append(text)
        if self.alert_error:
            raise self.alert_error

    def __call__(self, **kw):
        return daily.run_daily(
            DAY,
            collect_step=self.collect,
            embed_step=self.embed,
            build_step=self.build,
            alert=self.alert,
            log=self.logs.append,
            **kw,
        )


def test_success_collects_embeds_then_builds_with_the_cap_and_sends_nothing():
    run = Run()
    summary = run()
    assert run.calls == ["collect", "embed", ("build", DAY, daily.DAILY_MAX_REQUESTS)]
    assert run.alerts == []
    assert summary["stories"] == 44 and summary["requests"] == 9 and summary["missing"] == 0


def test_a_custom_cap_reaches_the_build():
    run = Run()
    run(max_requests=3)
    assert run.calls[2] == ("build", DAY, 3)


def test_over_the_cap_alerts_and_fails_without_building():
    run = Run(report(stopped=True, planned=14, requests=0, summarized=0, stories=44))
    with pytest.raises(daily.DailyError, match="over the cap"):
        run(max_requests=12)
    assert len(run.alerts) == 1
    assert "14 LLM requests" in run.alerts[0] and "cap of 12" in run.alerts[0]
    assert "Nothing was sent" in run.alerts[0] and "2026-10-18" in run.alerts[0]


def test_embed_failure_alerts_still_builds_then_fails():
    run = Run(embed_error=daily.StepError("embed exited with code 1: Killed"))
    with pytest.raises(daily.DailyError, match="embed failed"):
        run()
    assert run.calls == ["collect", "embed", ("build", DAY, daily.DAILY_MAX_REQUESTS)]
    assert len(run.alerts) == 1 and "embed failed" in run.alerts[0]
    assert "Building the digest anyway" in run.alerts[0]


def test_collect_failure_alerts_and_skips_the_build():
    run = Run(collect_error=OSError("disk full"))
    with pytest.raises(daily.DailyError, match="collect failed"):
        run()
    assert run.calls == ["collect"]
    assert len(run.alerts) == 1 and "collect failed: OSError: disk full" in run.alerts[0]


def test_build_failure_alerts():
    run = Run(build_error=RuntimeError("cannot connect"))
    with pytest.raises(daily.DailyError, match="digest build failed"):
        run()
    assert len(run.alerts) == 1 and "RuntimeError: cannot connect" in run.alerts[0]


def test_unsummarized_stories_alert_but_do_not_fail():
    run = Run(report(missing=[1, 2], summarized=42))
    summary = run()
    assert summary["missing"] == 2
    assert len(run.alerts) == 1 and "2 of 44 stories have no summary" in run.alerts[0]


def test_an_empty_digest_alerts():
    run = Run(report(stories=0, planned=0, requests=0, summarized=0))
    run()
    assert len(run.alerts) == 1 and "empty" in run.alerts[0]


def test_a_failing_alert_never_hides_the_runs_error():
    run = Run(collect_error=OSError("disk full"), alert_error=ConnectionError("telegram down"))
    with pytest.raises(daily.DailyError, match="collect failed"):
        run()
    assert any("could not send the alert" in line for line in run.logs)


def test_long_errors_are_cut_in_the_alert():
    run = Run(build_error=RuntimeError("x" * 2000))
    with pytest.raises(daily.DailyError):
        run()
    assert len(run.alerts[0]) < daily.ALERT_CHARS + 100


def test_the_flow_and_its_schedule():
    assert daily.natalia_daily.name == "natalia-daily"
    assert daily.natalia_daily.retries == 0  # a retry could resend LLM requests
    assert daily.SCHEDULE == "0 5 * * *"  # 05:00, the digest's cut-off
    assert daily.POOL == "natalia"


def test_deploy_refuses_outside_the_runtime_worktree(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(daily, "RUNTIME", tmp_path / "natalia-runtime")
    assert daily.main(["deploy"]) == 1
    assert "natalia-runtime" in capsys.readouterr().out


# --- child processes ----------------------------------------------------------------------------


class FakePopen:
    """Stands in for subprocess.Popen: prints `lines`, exits with `code` (or hangs)."""

    calls = []

    def __init__(self, lines, code=0, hang=False):
        self.lines, self.code, self.hang, self.killed = lines, code, hang, False

    def __call__(self, args, **kw):
        FakePopen.calls.append(args)
        self.stdout = iter(line + "\n" for line in self.lines)
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def wait(self, timeout=None):
        if self.hang:
            raise daily.subprocess.TimeoutExpired("x", timeout)
        return self.code

    def kill(self):
        self.killed = True


def test_run_child_streams_its_output_and_runs_this_python():
    out = []
    daily.run_child(
        "embed", ["natalia.embeddings", "embed"], popen=FakePopen(["a", "b"]), log=out.append
    )
    assert out == ["a", "b"]
    assert FakePopen.calls[-1] == [daily.sys.executable, "-m", "natalia.embeddings", "embed"]


def test_run_child_failure_quotes_the_last_lines():
    fake = FakePopen(["one", "two", "three", "", "Killed"], code=137)
    with pytest.raises(daily.StepError, match=r"code 137: two \| three \| Killed"):
        daily.run_child("embed", ["x"], popen=fake, log=lambda s: None)


def test_run_child_timeout_kills_it():
    fake = FakePopen([], hang=True)
    with pytest.raises(daily.StepError, match="ran over"):
        daily.run_child("collect", ["x"], popen=fake, log=lambda s: None)
    assert fake.killed


def test_steps_are_child_processes(monkeypatch):
    seen = []
    monkeypatch.setattr(daily, "run_child", lambda name, args: seen.append((name, args)))
    daily.collect_step()
    daily.embed_step()
    assert seen == [("collect", ["natalia.collect"]), ("embed", ["natalia.embeddings", "embed"])]
