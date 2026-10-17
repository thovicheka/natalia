"""Chat (task 1.9b): language, the daily cap, retrieval, the answer and its sources. No LLM, no
model: retrieval and the LLM are fakes; the database parts run in a rolled-back transaction."""

import json
import subprocess
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from natalia import chat, db, llm
from natalia.collect import normalize_title
from natalia.topics import LOCAL_TZ

OWNER = 1111
NOW = datetime(2026, 10, 17, 9, 0, tzinfo=LOCAL_TZ)


@pytest.fixture
def articles(scratch):
    src = scratch.execute(
        "INSERT INTO sources (name, topic, feed_url) VALUES ('Test Chat', 'crypto',"
        " 'https://chat.test/feed') RETURNING id"
    ).fetchone()[0]
    ids = []
    for i, title in enumerate(["Zebracoin hits <record> & more", "Zebracoin falls", "Old news"]):
        ids.append(
            scratch.execute(
                """INSERT INTO articles (source_id, url, title, title_norm, excerpt, body,
                                         language, published_at)
                   VALUES (%s, %s, %s, %s, %s, %s, 'en', %s) RETURNING id""",
                (
                    src,
                    f"https://chat.test/{i}?a=1&b=2",
                    title,
                    normalize_title(title),
                    f"Excerpt {i}.",
                    "Body text. " * 300,
                    datetime.now(UTC) - timedelta(days=40 if title == "Old news" else i + 1),
                ),
            ).fetchone()[0]
        )
    return ids


class FakeLLM:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    def __call__(self, prompt, **kw):
        self.calls.append((prompt, kw))
        if self.error:
            raise self.error
        return llm.Result(
            text=self.reply if isinstance(self.reply, str) else json.dumps(self.reply),
            model="fake-haiku",
            input_tokens=900,
            output_tokens=120,
            thinking_tokens=30,
            requests=1,
        )


def fake_retrieve(hits):
    asked = []

    def retrieve(question):
        asked.append(question)
        return hits

    retrieve.asked = asked
    return retrieve


def ask(conn, question="How is Zebracoin doing?", hits=(), fake=None, **kw):
    return chat.answer(
        conn,
        question,
        OWNER,
        retrieve=kw.pop("retrieve", fake_retrieve(list(hits))),
        generate=fake or FakeLLM({"covered": True, "answer": "Up.", "source_ids": []}),
        now=kw.pop("now", NOW),
        log=lambda *_: None,
        **kw,
    )


# --- language and rendering -------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, lang",
    [
        ("What happened today?", "en"),
        ("តើមានព័ត៌មានអ្វីខ្លះអំពីកម្ពុជា?", "km"),
        ("តម្លៃ Bitcoin ថ្ងៃនេះ", "km"),  # Khmer with a Latin name
        ("Is ASEAN meeting in ភ្នំពេញ?", "en"),  # English with a Khmer place name
        ("12345 ???", "en"),
    ],
)
def test_language_follows_the_script_of_the_question(text, lang):
    assert chat.language(text) == lang


def test_render_escapes_and_numbers_the_sources():
    src = chat.Source(1, "A <b> & c", "https://x.test/?a=1&b=2", "Site & Co", NOW)
    a = chat.Answer("en", text="Rates rose <5%> & fell.", covered=True, sources=[src])
    out = chat.render(a)
    assert out.startswith("Rates rose &lt;5%&gt; &amp; fell.")
    assert '1. <a href="https://x.test/?a=1&amp;b=2">A &lt;b&gt; &amp; c</a>' in out
    assert "<b>Sources</b>" in out and "Site &amp; Co · 17 Oct" in out


def test_render_in_khmer_and_the_special_cases():
    km = chat.Answer("km", text="ចម្លើយ", covered=True, sources=[chat.Source(1, "T", "u", "S", NOW)])
    assert "<b>ប្រភព</b>" in chat.render(km)
    assert chat.render(chat.Answer("en", over_cap=True), cap=20).startswith("That's 20 questions")
    assert "ថ្ងៃស្អែក" in chat.render(chat.Answer("km", over_cap=True))
    assert chat.render(chat.Answer("en", error="boom")) == chat.TEXTS["en"]["failed"]
    assert chat.render(chat.Answer("en", covered=False)) == chat.TEXTS["en"]["nothing"]


def test_prompt_holds_the_articles_and_the_question():
    src = chat.Source(7, "Title", "u", "Site", NOW, text="word " * 1000)
    p = chat.build_prompt("Why?", [src])
    assert p.startswith("Articles:\n\n[7] Title\nSource: Site, 2026-10-17 09:00\n")
    assert p.endswith("\n\nQuestion: Why?")
    assert len(p) < chat.TEXT_CHARS + 200


# --- answering --------------------------------------------------------------------------------


def test_answer_uses_only_retrieved_articles_and_drops_made_up_ids(scratch, articles):
    a1, a2, _ = articles
    fake = FakeLLM(
        {"covered": True, "answer": "It rose, then fell.", "source_ids": [a2, 999999, a2]}
    )
    a = ask(scratch, hits=[(a1, 0.1), (a2, 0.12)], fake=fake)
    assert (a.covered, a.text, [s.id for s in a.sources]) == (True, "It rose, then fell.", [a2])
    assert (a.input_tokens, a.output_tokens, a.model) == (900, 150, "fake-haiku")
    prompt, kw = fake.calls[0]
    assert f"[{a1}] Zebracoin hits <record> & more" in prompt and "Question: How is" in prompt
    assert (
        "English" in kw["system"] and kw["json_schema"] is chat.SCHEMA and kw["purpose"] == "chat"
    )
    out = chat.render(a)
    assert "https://chat.test/1?a=1&amp;b=2" in out and "999999" not in out


def test_a_khmer_question_asks_for_a_khmer_answer(scratch, articles):
    fake = FakeLLM({"covered": True, "answer": "ចម្លើយ", "source_ids": [articles[0]]})
    a = ask(scratch, "តម្លៃ Zebracoin ថ្ងៃនេះ?", hits=[(articles[0], 0.1)], fake=fake)
    assert a.language == "km" and "Khmer" in fake.calls[0][1]["system"]


def test_nothing_retrieved_means_no_llm_call(scratch, articles):
    fake = FakeLLM()
    a = ask(scratch, hits=[], fake=fake)
    assert fake.calls == [] and a.covered is False
    assert chat.render(a) == chat.TEXTS["en"]["nothing"]


def test_question_is_recorded_without_its_text(scratch, articles):
    ask(scratch, "my secret question", hits=[(articles[0], 0.1)])
    cols = [
        r[0]
        for r in scratch.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'chat_questions'"
        )
    ]
    assert not any("question" in c or "text" in c for c in cols)
    row = scratch.execute(
        "SELECT language, retrieved, covered, requests, input_tokens, output_tokens, error"
        " FROM chat_questions WHERE chat_id = %s",
        (OWNER,),
    ).fetchall()
    assert row == [("en", 1, True, 1, 900, 150, None)]


def test_daily_cap_counts_failures_and_resets_the_next_local_day(scratch, articles):
    hits = [(articles[0], 0.1)]
    failing = FakeLLM(error=llm.LLMError("LLM request failed (529): overloaded"))
    first = ask(scratch, hits=hits, fake=failing, cap=2)
    assert first.error and chat.render(first) == chat.TEXTS["en"]["failed"]
    ask(scratch, hits=hits, cap=2)

    fake, retrieve = FakeLLM(), fake_retrieve(hits)
    third = ask(scratch, hits=hits, fake=fake, retrieve=retrieve, cap=2)
    assert third.over_cap and fake.calls == [] and retrieve.asked == []  # nothing run or sent

    tomorrow = NOW.replace(hour=0, minute=1) + timedelta(days=1)  # 00:01 local, next day
    scratch.execute("UPDATE chat_questions SET asked_at = %s WHERE chat_id = %s", (NOW, OWNER))
    assert not ask(scratch, hits=hits, cap=2, now=tomorrow).over_cap


def test_retrieval_failure_is_an_answer_with_an_error(scratch, articles):
    def broken(question):
        raise chat.ChatError("retrieval exited with code 1: Killed")

    fake = FakeLLM()
    a = ask(scratch, retrieve=broken, fake=fake)
    assert a.error.startswith("retrieval") and fake.calls == []
    assert (
        scratch.execute("SELECT error FROM chat_questions WHERE chat_id = %s", (OWNER,))
        .fetchone()[0]
        .startswith("retrieval")
    )


def test_a_reply_that_isnt_json_is_an_error(scratch, articles):
    a = ask(scratch, hits=[(articles[0], 0.1)], fake=FakeLLM("not json"))
    assert "isn't the JSON" in a.error and a.sources == []


def test_dry_run_records_nothing_and_calls_no_llm(scratch, articles):
    fake, lines = FakeLLM(), []
    chat.answer(
        scratch,
        "q",
        OWNER,
        retrieve=fake_retrieve([(articles[0], 0.1)]),
        generate=fake,
        dry_run=True,
        log=lines.append,
    )
    assert fake.calls == [] and lines and lines[0].startswith("Articles:")
    assert chat.asked_today(scratch, OWNER, NOW) == 0


# --- retrieval --------------------------------------------------------------------------------


def unit(i, dims=384):
    v = np.zeros(dims, dtype=np.float32)
    v[i] = 1.0
    return v


def test_nearest_keeps_recent_close_articles_only(scratch, articles):
    a1, a2, old = articles
    near = unit(0) * 0.95 + unit(1) * 0.05
    for art, vec in ((a1, unit(0)), (a2, unit(1)), (old, unit(0))):
        scratch.execute(
            "INSERT INTO embeddings (article_id, model, embedding) VALUES (%s, 'test-model', %s)",
            (art, db.to_vector(vec / np.linalg.norm(vec))),
        )
    hits = chat.nearest(scratch, near / np.linalg.norm(near), "test-model", k=5)
    assert [i for i, _ in hits] == [a1]  # a2 is too far, `old` is 40 days old


def test_retrieve_passes_the_question_on_stdin_never_in_argv():
    seen = {}

    def run(args, **kw):
        seen["args"], seen["input"] = args, kw["input"]
        return subprocess.CompletedProcess(args, 0, stdout="[[5, 0.1], [6, 0.2]]", stderr="")

    assert chat.retrieve("private question", k=2, run=run) == [(5, 0.1), (6, 0.2)]
    assert seen["input"] == "private question"
    assert "private question" not in " ".join(seen["args"])
    assert seen["args"][1:] == ["-m", "natalia.chat", "retrieve", "-k", "2"]


def test_retrieve_failure_and_timeout_raise_chat_error():
    def failing(args, **kw):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="a\nb\nMemoryError")

    with pytest.raises(chat.ChatError, match="code 1: a | b | MemoryError"):
        chat.retrieve("q", run=failing)

    def slow(args, **kw):
        raise subprocess.TimeoutExpired(args, kw["timeout"])

    with pytest.raises(chat.ChatError, match="took over"):
        chat.retrieve("q", run=slow)
