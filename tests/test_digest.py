"""Tests for the digest builder (task 1.7): a fake LLM, the real database inside a rolled-back
transaction (see conftest.py), and a day in 2020 so only the test's articles are in the window."""

import json
from datetime import UTC, date, datetime, timedelta

import pytest

from natalia import digest as dg
from natalia import llm
from natalia.collect import normalize_title

DAY = date(2020, 1, 2)
END = datetime(2020, 1, 1, 22, 0, tzinfo=UTC)  # 05:00 Asia/Phnom_Penh on DAY


class FakeLLM:
    """Answers every id in the prompt, except those in `skip`; records prompts."""

    def __init__(self, skip=()):
        self.skip = set(skip)
        self.prompts = []

    def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        ids = [int(line[4:]) for line in prompt.splitlines() if line.startswith("id: ")]
        items = [
            {"id": i, "summary": f"Summary {i}.", "why_it_matters": f"Matters {i}."}
            for i in ids
            if i not in self.skip
        ]
        return llm.Result(json.dumps({"items": items}), "fake-model", 100 * len(ids), 50)


@pytest.fixture(autouse=True)
def fresh(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "usage", llm.Usage())
    monkeypatch.setattr(llm, "USAGE_LOG", tmp_path / "usage.jsonl")
    monkeypatch.setattr(dg, "REPLY_DIR", tmp_path / "replies")
    yield
    llm.use_client(None)


@pytest.fixture
def day_articles(scratch):
    src = scratch.execute(
        "INSERT INTO sources (name, topic, feed_url) VALUES ('Test Digest', 'economics',"
        " 'https://digest.test/feed') RETURNING id"
    ).fetchone()[0]
    ids = {}
    rows = [
        ("Zebra exports hit record", ["economics"], "Body " * 200, "Zebra exports rose."),
        ("Zebra bank holds rates", ["economics"], None, "The bank held rates at 4%."),
        ("Comet seen over Zebraland", ["science"], "Astronomers saw a comet. " * 30, None),
    ]
    for i, (title, topics, body, excerpt) in enumerate(rows):
        ids[title] = scratch.execute(
            """INSERT INTO articles (source_id, url, title, title_norm, excerpt, body, language,
                                     topics, published_at)
               VALUES (%s, %s, %s, %s, %s, %s, 'en', %s::topic[], %s) RETURNING id""",
            (
                src,
                f"https://digest.test/{i}",
                title,
                normalize_title(title),
                excerpt,
                body,
                topics,
                END - timedelta(hours=i + 1),
            ),
        ).fetchone()[0]
    return ids


def test_build_summarizes_stores_and_reuses(scratch, day_articles):
    fake = FakeLLM()
    llm.use_client(fake)
    r = dg.build(scratch, DAY, log=lambda *_: None, sleep=lambda s: None)
    assert (r.stories, r.summarized, r.reused, r.missing) == (3, 3, 0, [])
    assert r.requests == 2  # one per topic with stories: economics, science
    assert "Zebra bank holds rates" in fake.prompts[0] or "Zebra bank" in fake.prompts[1]
    assert all("excerpt only" in p or "full text" in p for p in fake.prompts)

    d = dg.load_digest(scratch, DAY)
    assert (d.requests, d.model) == (2, "fake-model")
    eco = d.by_topic()["economics"]
    assert [it.article.title for it in eco] == [
        "Zebra exports hit record",
        "Zebra bank holds rates",
    ]
    assert eco[0].summary == f"Summary {day_articles['Zebra exports hit record']}."

    # Second build: every summary is reused, nothing is sent, request counts add up (+0).
    again = dg.build(scratch, DAY, log=lambda *_: None, sleep=lambda s: None)
    assert (again.reused, again.summarized, again.requests) == (3, 0, 0)
    assert len(fake.prompts) == 2
    assert dg.load_digest(scratch, DAY).requests == 2


def test_markdown_puts_the_source_before_the_summary(scratch, day_articles):
    llm.use_client(FakeLLM())
    dg.build(scratch, DAY, log=lambda *_: None, sleep=lambda s: None)
    md = dg.to_markdown(dg.load_digest(scratch, DAY))
    head = md.index("[Zebra bank holds rates](https://digest.test/1)")
    assert head < md.index("> The bank held rates at 4%.") < md.index("**Summary:**", head)
    assert md.index("## Economics") < md.index("## Science")


def test_missing_answers_are_reported_and_shown(scratch, day_articles):
    skip = day_articles["Comet seen over Zebraland"]
    llm.use_client(FakeLLM(skip=[skip]))
    r = dg.build(scratch, DAY, log=lambda *_: None, sleep=lambda s: None)
    assert r.missing == [skip]
    md = dg.to_markdown(dg.load_digest(scratch, DAY))
    assert "summary pending" in md


def test_raw_reply_is_saved_only_when_a_story_is_missing(scratch, day_articles):
    skip = day_articles["Comet seen over Zebraland"]
    llm.use_client(FakeLLM(skip=[skip]))
    lines = []
    dg.build(scratch, DAY, log=lines.append, sleep=lambda s: None)
    files = list(dg.REPLY_DIR.glob("*.json"))
    assert len(files) == 1 and files[0].name.startswith("2020-01-02-science-")
    saved = json.loads(files[0].read_text())
    assert saved["missing_ids"] == [skip] and saved["sent_ids"] == [skip]
    assert json.loads(saved["reply"]) == {"items": []}
    assert any("raw reply saved to" in line for line in lines)


def test_dry_run_calls_nothing(scratch, day_articles):
    llm.use_client(FakeLLM())
    lines = []
    r = dg.build(scratch, DAY, dry_run=True, log=lines.append)
    assert r.requests == 2 and llm.usage.requests == 0
    assert dg.load_digest(scratch, DAY) is None
    assert lines[0] == "plan: 2 requests (economics, science); limit 12"
    assert lines[1].startswith("[dry run]")


def test_build_prints_the_plan_before_sending(scratch, day_articles):
    fake = FakeLLM()
    lines = []

    def log(line):
        lines.append((line, len(fake.prompts)))

    llm.use_client(fake)
    r = dg.build(scratch, DAY, log=log, sleep=lambda s: None)
    assert lines[0] == ("plan: 2 requests (economics, science); limit 12", 0)  # nothing sent yet
    assert (r.planned, r.requests, r.stopped) == (2, 2, False)


def test_plan_bigger_than_max_requests_sends_and_stores_nothing(scratch, day_articles):
    fake = FakeLLM()
    llm.use_client(fake)
    lines = []
    r = dg.build(scratch, DAY, max_requests=1, log=lines.append, sleep=lambda s: None)
    assert r.stopped and r.planned == 2 and r.requests == 0
    assert fake.prompts == [] and llm.usage.requests == 0
    assert dg.load_digest(scratch, DAY) is None
    assert sorted(r.missing) == sorted(day_articles.values())
    assert lines[-1] == "stopped: the plan is over --max-requests 1; sent nothing"


def test_plan_equal_to_max_requests_goes_ahead(scratch, day_articles):
    llm.use_client(FakeLLM())
    r = dg.build(scratch, DAY, max_requests=2, log=lambda *_: None, sleep=lambda s: None)
    assert not r.stopped and r.requests == 2 and r.summarized == 3


def test_dry_run_says_a_real_build_would_stop(scratch, day_articles):
    llm.use_client(FakeLLM())
    lines = []
    r = dg.build(scratch, DAY, max_requests=1, dry_run=True, log=lines.append)
    assert r.stopped and llm.usage.requests == 0
    assert "a real build would stop here" in lines[1]


def test_nothing_to_summarize_plans_zero_requests(scratch, day_articles):
    llm.use_client(FakeLLM())
    dg.build(scratch, DAY, log=lambda *_: None, sleep=lambda s: None)
    lines = []
    r = dg.build(scratch, DAY, max_requests=0, log=lines.append, sleep=lambda s: None)
    assert lines[0] == "plan: 0 requests (nothing to summarize); limit 0"
    assert not r.stopped and r.requests == 0


def test_cli_exits_3_when_the_plan_is_too_big(monkeypatch, capsys):
    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(dg.db, "connect", lambda **kw: Conn())
    seen = {}

    def fake_build(conn, day, **kw):
        seen.update(kw)
        return dg.BuildReport(day=day, model="fake", planned=9, stopped=True)

    monkeypatch.setattr(dg, "build", fake_build)
    assert dg.main(["build", "--max-requests", "3"]) == 3
    assert seen["max_requests"] == 3
    assert "not built (9 requests planned); nothing sent" in capsys.readouterr().out


def test_parse_reply_ignores_unknown_and_empty():
    text = json.dumps(
        {
            "items": [
                {"id": 1, "summary": "S", "why_it_matters": "W"},
                {"id": 2, "summary": "", "why_it_matters": "W"},
                {"id": 99, "summary": "S", "why_it_matters": "W"},
                {"summary": "no id"},
            ]
        }
    )
    assert dg.parse_reply(text, {1, 2}) == {1: ("S", "W")}


def test_prompt_holds_news_only():
    a = dg.ArticleText(
        7,
        "Headline",
        "https://x.test/a",
        "Source",
        False,
        datetime(2026, 10, 16, tzinfo=UTC),
        "Excerpt",
        "Body text " * 1000,
    )
    p = dg.build_prompt([a])
    assert p.count("id: 7") == 1 and "full text (start)" in p
    assert len(p) < dg.TEXT_CHARS + 300
    assert "https://" not in p  # links aren't needed by the model


def test_no_llm_stores_the_picks_only(scratch, day_articles):
    llm.use_client(FakeLLM())
    r = dg.build(scratch, DAY, no_llm=True, log=lambda *_: None)
    assert (r.requests, r.summarized, len(r.missing)) == (0, 0, 3)
    d = dg.load_digest(scratch, DAY)
    assert len(d.items) == 3 and all(it.summary is None for it in d.items)
    # A later build adds the summaries.
    assert dg.build(scratch, DAY, log=lambda *_: None, sleep=lambda s: None).summarized == 3
