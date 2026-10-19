"""Chat (tasks 1.9b, 1.9c, 1.9d): language, the daily cap, reply-or-search, memory, retrieval, the
answer and its sources. No LLM, no model: retrieval and the LLM are fakes; the database parts run
in a rolled-back transaction."""

import json
import subprocess
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from natalia import chat, db, llm
from natalia.collect import normalize_title
from natalia.topics import LOCAL_TZ

OWNER = 1111
STRANGER_ID = 2222
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


NEWS = {"kind": "news", "reply": "", "search": "Zebracoin price"}


def chat_reply(text):
    return {"kind": "chat", "reply": text, "search": ""}


class FakeLLM:
    """Replies in order, one per request: a dict (sent as JSON), a raw string, an llm.Result
    (sent as is), or an error."""

    def __init__(self, *replies, error=None):
        self.replies, self.error, self.calls = list(replies), error, []

    def __call__(self, prompt, **kw):
        self.calls.append((prompt, kw))
        if self.error:
            raise self.error
        reply = self.replies.pop(0)
        if isinstance(reply, llm.Result):
            return reply
        return llm.Result(
            text=reply if isinstance(reply, str) else json.dumps(reply),
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


def news_answer(answer="Up.", ids=(), covered=True):
    return {"covered": covered, "answer": answer, "source_ids": list(ids)}


def ask(conn, question="How is Zebracoin doing?", hits=(), fake=None, **kw):
    return chat.answer(
        conn,
        question,
        OWNER,
        retrieve=kw.pop("retrieve", fake_retrieve(list(hits))),
        generate=fake or FakeLLM(NEWS, news_answer()),
        now=kw.pop("now", NOW),
        log=kw.pop("log", lambda *_: None),
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
    a = chat.Answer("en", "news", text="Rates rose <5%> & fell.", covered=True, sources=[src])
    out = chat.render(a)
    assert out.startswith("Rates rose &lt;5%&gt; &amp; fell.")
    assert '1. <a href="https://x.test/?a=1&amp;b=2">A &lt;b&gt; &amp; c</a>' in out
    assert "<b>Sources</b>" in out and "Site &amp; Co · 17 Oct" in out


def test_render_in_khmer_and_the_special_cases():
    km = chat.Answer("km", "news", "ចម្លើយ", True, sources=[chat.Source(1, "T", "u", "S", NOW)])
    assert "<b>ប្រភព</b>" in chat.render(km)
    assert chat.render(chat.Answer("en", over_cap=True), cap=20).startswith("That's 20 messages")
    assert "ថ្ងៃស្អែក" in chat.render(chat.Answer("km", over_cap=True))
    assert chat.render(chat.Answer("en", error="boom")) == chat.TEXTS["en"]["failed"]
    assert chat.render(chat.Answer("en", covered=False)) == chat.TEXTS["en"]["nothing"]


def test_prompt_holds_the_articles_and_the_question():
    src = chat.Source(7, "Title", "u", "Site", NOW, text="word " * 1000)
    p = chat.build_prompt("Why?", [src])
    assert p.startswith("Articles:\n\n[7] Title\nSource: Site, 2026-10-17 09:00\n")
    assert p.endswith("\n\nQuestion: Why?")
    assert len(p) < chat.TEXT_CHARS + 200


def test_prompts_carry_the_conversation_oldest_first():
    history = [chat.Turn("user", "Bitcoin?"), chat.Turn("natalia", "It fell 3%.")]
    p = chat.build_reply_prompt("tell me more", history)
    assert p.index("Them: Bitcoin?") < p.index("Natalia: It fell 3%.") < p.index("New message:")
    src = chat.Source(7, "Title", "u", "Site", NOW, text="x")
    q = chat.build_prompt("tell me more", [src], history)
    assert q.index("[7] Title") < q.index("Them: Bitcoin?") < q.index("Question: tell me more")
    assert chat.build_reply_prompt("hi") == chat.NO_CONVERSATION + "New message: hi"


# --- answering --------------------------------------------------------------------------------


def test_answer_uses_only_retrieved_articles_and_drops_made_up_ids(scratch, articles):
    a1, a2, _ = articles
    fake = FakeLLM(NEWS, news_answer("It rose, then fell.", [a2, 999999, a2]))
    retrieve = fake_retrieve([(a1, 0.1), (a2, 0.12)])
    a = ask(scratch, retrieve=retrieve, fake=fake)
    assert (a.kind, a.covered, a.text) == ("news", True, "It rose, then fell.")
    assert [s.id for s in a.sources] == [a2]
    assert retrieve.asked == ["Zebracoin price"]  # the search query the first request wrote
    assert (a.requests, a.input_tokens, a.output_tokens, a.model) == (2, 1800, 300, "fake-haiku")
    assert fake.calls[0][1]["json_schema"] is chat.REPLY_SCHEMA
    prompt, kw = fake.calls[1]
    assert f"[{a1}] Zebracoin hits <record> & more" in prompt and "Question: How is" in prompt
    assert (
        "English" in kw["system"] and kw["json_schema"] is chat.SCHEMA and kw["purpose"] == "chat"
    )
    out = chat.render(a)
    assert "https://chat.test/1?a=1&amp;b=2" in out and "999999" not in out


def test_a_khmer_question_asks_for_a_khmer_answer(scratch, articles):
    fake = FakeLLM(NEWS, news_answer("ចម្លើយ", [articles[0]]))
    a = ask(scratch, "តម្លៃ Zebracoin ថ្ងៃនេះ?", hits=[(articles[0], 0.1)], fake=fake)
    assert a.language == "km"
    assert all("mostly Khmer" in kw["system"] for _, kw in fake.calls)


def test_nothing_retrieved_means_no_answer_request(scratch, articles):
    fake = FakeLLM(NEWS)
    a = ask(scratch, hits=[], fake=fake)
    assert len(fake.calls) == 1 and a.covered is False
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
        "SELECT kind, language, retrieved, covered, requests, input_tokens, output_tokens, error"
        " FROM chat_questions WHERE chat_id = %s",
        (OWNER,),
    ).fetchall()
    assert row == [("news", "en", 1, True, 2, 1800, 300, None)]


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

    fake = FakeLLM(NEWS)
    a = ask(scratch, retrieve=broken, fake=fake)
    assert a.error.startswith("retrieval") and len(fake.calls) == 1
    assert (
        scratch.execute("SELECT error FROM chat_questions WHERE chat_id = %s", (OWNER,))
        .fetchone()[0]
        .startswith("retrieval")
    )


def test_a_reply_that_isnt_json_is_an_error(scratch, articles):
    fake = FakeLLM("not json")
    a = ask(scratch, hits=[(articles[0], 0.1)], fake=fake)
    assert "isn't the JSON" in a.error and a.kind == ""
    assert len(fake.calls) == 1 and a.retries == 0  # only a cut-off reply is asked again
    b = ask(scratch, hits=[(articles[0], 0.1)], fake=FakeLLM(NEWS, "[1, 2]"))
    assert "isn't the JSON" in b.error and b.sources == []


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
    assert fake.calls == [] and lines[0].endswith("New message: q")
    assert lines[1].startswith("Articles:")
    assert chat.asked_today(scratch, OWNER, NOW) == 0


# --- reply or search (task 1.9c) ---------------------------------------------------------------


def test_small_talk_is_answered_without_searching_or_sources(scratch, articles):
    fake, retrieve = FakeLLM(chat_reply("Not much, twin! You good? 😄")), fake_retrieve([])
    a = ask(scratch, "yo sup twin", retrieve=retrieve, fake=fake)
    assert (a.kind, a.text, a.sources, a.covered) == (
        "chat",
        "Not much, twin! You good? 😄",
        [],
        None,
    )
    assert retrieve.asked == [] and len(fake.calls) == 1 and a.requests == 1
    assert chat.render(a) == "Not much, twin! You good? 😄"  # no "Sources"
    row = scratch.execute(
        "SELECT kind, retrieved, source_ids FROM chat_questions WHERE chat_id = %s", (OWNER,)
    ).fetchone()
    assert row == ("chat", 0, [])


def test_the_reply_prompt_covers_personality_tone_language_and_distress():
    system = chat.REPLY_SYSTEM
    for rule in (
        "Match the person's language and tone",
        "same mix",
        "slang",
        "genuinely upset",
        "someone they trust",
        "emergency services",
        "Never state current facts",
        "No sources",
        "normal, friendly person",
        "specialty is news",
        'always "news"',
    ):
        assert rule in system
    assert "{language}" in system and "{today}" in system


def test_a_general_question_is_answered_from_general_knowledge_and_says_so(scratch, articles):
    steps = "Check the pads first. If the pedal feels soft, have a mechanic bleed the brakes."
    retrieve = fake_retrieve([])
    a = ask(
        scratch,
        "How do I fix my car's brakes?",
        retrieve=retrieve,
        fake=FakeLLM({"kind": "general", "reply": steps, "search": ""}),
    )
    assert (a.kind, a.text, a.sources, a.requests) == ("general", steps, [], 1)
    assert retrieve.asked == []
    out = chat.render(a)
    assert out.startswith("Check the pads first.") and "Sources" not in out
    assert out.endswith("<i>ℹ️ General knowledge, not from today's news.</i>")
    km = chat.render(chat.Answer("km", "general", "ចម្លើយ"))
    assert chat.TEXTS["km"]["general"] in km
    assert chat.TEXTS["en"]["general"] not in chat.render(chat.Answer("en", "chat", "Hey!"))
    row = scratch.execute("SELECT kind FROM chat_questions WHERE chat_id = %s", (OWNER,)).fetchone()
    assert row == ("general",)


def test_an_unknown_kind_is_treated_as_chat(scratch, articles):
    a = ask(scratch, "hm", fake=FakeLLM({"kind": "poem", "reply": "Hi!", "search": ""}))
    assert (a.kind, a.text) == ("chat", "Hi!")


def test_the_news_prompt_asks_for_analysis_and_current_facts_only_from_articles():
    for rule in (
        "only source for facts about current events",
        "out of date",
        "why it matters",
        "connect related stories",
        "compare how they report it",
        "what changed",
        "Don't guess",
        "oldest first",
    ):
        assert rule in chat.SYSTEM


def test_articles_are_listed_oldest_first():
    new = chat.Source(1, "Newer", "u", "A", NOW, text="x")
    old = chat.Source(2, "Older", "u", "B", NOW - timedelta(days=2), text="x")
    undated = chat.Source(3, "Undated", "u", "C", None, text="x")
    p = chat.build_prompt("What changed?", [new, old, undated])
    assert p.index("[3] Undated") < p.index("[2] Older") < p.index("[1] Newer")


def test_an_empty_chat_reply_is_an_error(scratch, articles):
    a = ask(scratch, "hi", fake=FakeLLM(chat_reply("  ")))
    assert a.error == "empty reply" and chat.render(a) == chat.TEXTS["en"]["failed"]


def test_news_search_falls_back_to_the_message_when_the_query_is_empty(scratch, articles):
    retrieve = fake_retrieve([(articles[0], 0.1)])
    ask(
        scratch,
        "zebra news?",
        retrieve=retrieve,
        fake=FakeLLM({**NEWS, "search": " "}, news_answer()),
    )
    assert retrieve.asked == ["zebra news?"]


def test_not_covered_lists_no_sources_even_if_ids_come_back(scratch, articles):
    fake = FakeLLM(NEWS, news_answer("The stored news doesn't cover that.", [articles[0]], False))
    a = ask(scratch, hits=[(articles[0], 0.1)], fake=fake)
    assert a.covered is False and a.sources == []
    assert chat.render(a) == "The stored news doesn't cover that."


# --- memory (task 1.9c) -------------------------------------------------------------------------


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_memory_keeps_the_last_messages_per_chat_and_forgets_when_idle():
    clock = Clock()
    m = chat.Memory(size=4, idle_s=60, clock=clock)
    for i in range(3):
        m.add(OWNER, chat.Turn("user", f"q{i}"), chat.Turn("natalia", f"a{i}"))
    m.add(STRANGER_ID, chat.Turn("user", "other"))
    assert [t.text for t in m.get(OWNER)] == ["q1", "a1", "q2", "a2"]
    assert [t.text for t in m.get(STRANGER_ID)] == ["other"]  # chats are kept apart
    clock.t += 59
    assert len(m.get(OWNER)) == 4
    clock.t += 2
    assert m.get(OWNER) == [] and m.get(STRANGER_ID) == []
    m.add(OWNER, chat.Turn("user", "x"))
    m.forget(OWNER)
    assert m.get(OWNER) == []


def test_a_follow_up_sees_the_previous_exchange(scratch, articles):
    memory, a1 = chat.Memory(), articles[0]
    hits = [(a1, 0.1)]
    ask(
        scratch,
        "How is Zebracoin?",
        hits=hits,
        memory=memory,
        fake=FakeLLM(NEWS, news_answer("It hit a record.", [a1])),
    )
    fake = FakeLLM({**NEWS, "search": "Zebracoin record"}, news_answer("More detail.", [a1]))
    ask(scratch, "tell me more", hits=hits, fake=fake, memory=memory)
    route_prompt, answer_prompt = fake.calls[0][0], fake.calls[1][0]
    for p in (route_prompt, answer_prompt):
        assert "Them: How is Zebracoin?" in p
        assert "Natalia: It hit a record. [sources: Zebracoin hits <record> & more]" in p
    assert [t.role for t in memory.get(OWNER)] == ["user", "natalia", "user", "natalia"]


def test_memory_cuts_long_messages_and_skips_failures(scratch, articles):
    memory = chat.Memory()
    ask(scratch, "y" * 900, fake=FakeLLM(chat_reply("z" * 900)), memory=memory)
    user, natalia = memory.get(OWNER)
    assert len(user.text) == len(natalia.text) == chat.MEMORY_CHARS
    ask(scratch, "hi", fake=FakeLLM(error=llm.LLMError("boom")), memory=memory)
    ask(scratch, "hi", fake=FakeLLM(), memory=memory, cap=2)  # over the cap
    assert len(memory.get(OWNER)) == 2


def test_memory_is_never_written_to_the_database(scratch, articles):
    cols = {
        r[0]
        for r in scratch.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'chat_questions'"
        )
    }
    assert cols == {
        "id",
        "chat_id",
        "asked_at",
        "language",
        "kind",
        "retrieved",
        "covered",
        "source_ids",
        "model",
        "requests",
        "input_tokens",
        "output_tokens",
        "error",
    }


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


# --- fixes from real use (task 1.9d) ------------------------------------------------------------


def cut_off(text='{"covered": true, "answer": "ចម្លើយ', output_tokens=None):
    """A reply that stopped at max_tokens: incomplete JSON."""
    return llm.Result(
        text=text,
        model="fake-haiku",
        input_tokens=4391,
        output_tokens=output_tokens or chat.MAX_OUTPUT_TOKENS,
        requests=1,
        stop_reason="max_tokens",
    )


def test_a_reply_cut_off_at_max_tokens_is_asked_again_once_with_more_room(scratch, articles):
    a1 = articles[0]
    full = "ចាស ចម្លើយពេញលេញ។ " * 50
    fake, lines = FakeLLM(NEWS, cut_off(), news_answer(full.strip(), [a1])), []
    a = ask(
        scratch,
        "តម្លៃ Zebracoin ថ្ងៃនេះ?",
        hits=[(a1, 0.1)],
        fake=fake,
        log=lines.append,
    )
    assert (a.error, a.text, a.retries, a.requests) == ("", full.strip(), 1, 3)
    assert [s.id for s in a.sources] == [a1]
    limits = [kw["max_output_tokens"] for _, kw in fake.calls]
    assert limits == [
        chat.REPLY_OUTPUT_TOKENS,
        chat.MAX_OUTPUT_TOKENS,
        chat.MAX_OUTPUT_TOKENS * chat.RETRY_FACTOR,
    ]
    assert fake.calls[1][0] == fake.calls[2][0]  # the same prompt, more room
    assert a.input_tokens == 900 + 4391 + 900  # every request is counted
    assert any("stopped at max_tokens" in line for line in lines)  # logged


def test_a_reply_cut_off_twice_fails_after_one_retry(scratch, articles):
    fake = FakeLLM(NEWS, cut_off(), cut_off())
    a = ask(scratch, hits=[(articles[0], 0.1)], fake=fake)
    assert "stop reason max_tokens" in a.error and a.retries == 1 and len(fake.calls) == 3
    assert chat.render(a) == chat.TEXTS["en"]["failed"]
    row = scratch.execute(
        "SELECT requests, error FROM chat_questions WHERE chat_id = %s", (OWNER,)
    ).fetchone()
    assert row[0] == 3 and "max_tokens" in row[1]


def test_every_chat_request_runs_with_thinking_off_and_room_for_khmer(scratch, articles):
    fake = FakeLLM(NEWS, news_answer())
    ask(scratch, hits=[(articles[0], 0.1)], fake=fake)
    assert [kw["thinking"] for _, kw in fake.calls] == [False, False]
    # 868 output tokens held less than half of a Khmer answer in real use (2026-10-19)
    assert chat.MAX_OUTPUT_TOKENS >= 4000 and chat.REPLY_OUTPUT_TOKENS >= 3000
    assert chat.TRANSLATE_OUTPUT_TOKENS >= 4000


def test_natalia_speaks_khmer_as_a_woman_in_every_prompt():
    for system in (chat.REPLY_SYSTEM, chat.SYSTEM, chat.DATA_SYSTEM, chat.TRANSLATE_SYSTEM):
        assert "You are a woman" in system and "ចាស" in system
        assert "Never use បាទ or ខ្ញុំបាទ" in system
    for t in chat.TEXTS["km"].values():
        assert "បាទ" not in t


def test_a_follow_up_with_no_conversation_is_asked_about_not_searched(scratch, articles):
    assert "nothing it could refer to" in chat.REPLY_SYSTEM and '"clarify"' in chat.REPLY_SYSTEM
    question = "Which story do you mean? Tell me a topic, or try /digest for today's top stories."
    fake = FakeLLM({"kind": "clarify", "reply": question, "search": ""})
    retrieve = fake_retrieve([(articles[0], 0.1)])
    a = ask(scratch, "tell me more", retrieve=retrieve, fake=fake, memory=chat.Memory())
    assert (a.kind, a.text, a.sources, a.requests) == ("clarify", question, [], 1)
    assert retrieve.asked == []
    assert "Conversation so far: none" in fake.calls[0][0]
    assert chat.render(a) == question  # no note, no sources


def test_a_data_question_is_answered_from_the_database_not_a_search(scratch, articles):
    fake = FakeLLM({"kind": "data", "reply": "", "search": ""}, {"answer": "3 days."})
    retrieve = fake_retrieve([(articles[0], 0.1)])
    a = ask(scratch, "Which days do you have news for?", retrieve=retrieve, fake=fake)
    assert (a.kind, a.text, a.sources, a.requests, a.error) == ("data", "3 days.", [], 2, "")
    assert retrieve.asked == []
    prompt, kw = fake.calls[1]
    assert prompt.startswith("Facts:\nNatalia's stored data, as of 2026-10-17 09:00")
    assert prompt.endswith("Question: Which days do you have news for?")
    assert kw["json_schema"] is chat.DATA_SCHEMA and kw["thinking"] is False
    assert "only the facts given" in kw["system"]
    assert chat.render(a) == "3 days."
    row = scratch.execute("SELECT kind FROM chat_questions WHERE chat_id = %s", (OWNER,)).fetchone()
    assert row == ("data",)


def test_data_facts_count_articles_per_local_day_and_list_digests_and_sources(scratch):
    src = scratch.execute(
        "INSERT INTO sources (name, topic, feed_url, paywalled) VALUES"
        " ('Zebra Times', 'crypto', 'https://facts.test/feed', true) RETURNING id"
    ).fetchone()[0]
    # 2030-03-02 00:30 in Phnom Penh is still 2030-03-01 in UTC: counted on the local day
    times = [
        datetime(2030, 3, 1, 17, 30, tzinfo=UTC),
        datetime(2030, 3, 2, 3, 0, tzinfo=LOCAL_TZ),
        datetime(2030, 3, 3, 8, 0, tzinfo=LOCAL_TZ),
    ]
    ids = [
        scratch.execute(
            """INSERT INTO articles (source_id, url, title, title_norm, language, collected_at)
               VALUES (%s, %s, %s, %s, 'en', %s) RETURNING id""",
            (src, f"https://facts.test/{i}", f"Fact {i}", f"fact {i}", t),
        ).fetchone()[0]
        for i, t in enumerate(times)
    ]
    d = scratch.execute(
        "INSERT INTO digests (digest_date, language) VALUES ('2030-03-02', 'en') RETURNING id"
    ).fetchone()[0]
    scratch.execute(
        "INSERT INTO digest_items (digest_id, topic, position, article_id) VALUES"
        " (%s, 'crypto', 1, %s), (%s, 'crypto', 2, %s)",
        (d, ids[0], d, ids[1]),
    )
    facts = chat.data_facts(scratch, datetime(2030, 3, 3, 12, 0, tzinfo=LOCAL_TZ))
    assert facts.startswith("Natalia's stored data, as of 2030-03-03 12:00 (Asia/Phnom_Penh):")
    assert "Articles collected today (2030-03-03): 1." in facts
    assert "(articles collected that day): 2030-03-02: 2; 2030-03-03: 1." in facts
    assert "2030-03-02 (en, 2 stories)." in facts
    assert "Zebra Times *" in facts and "paywalled" in facts
    assert f"last {chat.RETRIEVE_DAYS} days" in facts


def test_translate_uses_the_whole_previous_answer_and_keeps_its_sources(scratch, articles):
    memory, a1, a2 = chat.Memory(), articles[0], articles[1]
    long_answer = "Zebracoin rose. " * 40 + "Cambodia and Thailand resumed border talks."
    ask(
        scratch,
        "What's new?",
        hits=[(a1, 0.1), (a2, 0.1)],
        memory=memory,
        fake=FakeLLM(NEWS, news_answer(long_answer, [a1, a2])),
    )
    assert len(long_answer) > chat.MEMORY_CHARS  # the prompts' copy is cut...
    khmer = "ចាស Zebracoin បានឡើង។ កម្ពុជា និងថៃ បានបន្តកិច្ចចរចាព្រំដែន។"
    fake = FakeLLM({"kind": "translate", "reply": "", "search": ""}, {"translation": khmer})
    retrieve = fake_retrieve([])
    a = ask(scratch, "translate to Khmer", retrieve=retrieve, fake=fake, memory=memory)
    prompt, kw = fake.calls[1]
    assert long_answer in prompt  # ...but the translation gets all of it
    assert prompt.endswith("Request: translate to Khmer")
    assert kw["json_schema"] is chat.TRANSLATE_SCHEMA and "complete" in kw["system"]
    assert "Don't summarize, shorten, merge, add or leave out anything" in kw["system"]
    assert (a.kind, a.language, a.text, a.requests) == ("translate", "km", khmer, 2)
    assert [s.id for s in a.sources] == [a1, a2] and retrieve.asked == []
    out = chat.render(a)
    assert out.startswith(khmer) and "<b>ប្រភព</b>" in out and "https://chat.test/0" in out
    assert memory.get(OWNER)[-1].full == khmer  # it can be translated back


def test_translating_a_general_answer_keeps_its_note(scratch, articles):
    memory = chat.Memory()
    ask(
        scratch,
        "How do brakes work?",
        memory=memory,
        fake=FakeLLM({"kind": "general", "reply": "Pads press on discs.", "search": ""}),
    )
    a = ask(
        scratch,
        "ជាភាសាខ្មែរ",
        memory=memory,
        fake=FakeLLM({"kind": "translate", "reply": "", "search": ""}, {"translation": "ចាស ..."}),
    )
    assert a.translated_kind == "general" and a.sources == []
    assert chat.TEXTS["km"]["general"] in chat.render(a)


def test_translate_with_nothing_to_translate_asks_instead(scratch, articles):
    fake = FakeLLM({"kind": "translate", "reply": "", "search": ""})
    a = ask(scratch, "translate that", fake=fake, memory=chat.Memory())
    assert (a.kind, a.text, a.requests) == ("clarify", chat.TEXTS["en"]["no_previous"], 1)
