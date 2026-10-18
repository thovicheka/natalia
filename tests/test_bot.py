"""Tests for the Telegram bot (task 1.8). No network, no token: a fake bot records what would
be sent, and handlers get stand-in updates. Digests are made up (no database)."""

import asyncio
import contextlib
import logging
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from natalia import bot as nb
from natalia.digest import ArticleText, Digest, DigestItem

OWNER = 1111
STRANGER = 2222


def item(topic, pos, title="Zebra <exports> & rates", summary="Exports rose 5% & more."):
    a = ArticleText(
        id=pos,
        title=title,
        url=f'https://x.test/{pos}?a=1&b="2"',
        source="Test News",
        paywalled=False,
        published_at=datetime(2026, 10, 15, 10, 0, tzinfo=UTC),
        excerpt="The feed's own words.",
        body=None,
    )
    return DigestItem(topic, pos, a, summary, "It matters." if summary else None)


def digest(items):
    return Digest(date(2026, 10, 16), "en", "fake", 9, 100, 50, items)


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)

    async def send_chat_action(self, **kwargs):
        self.sent.append({"action": kwargs["action"], "chat_id": kwargs["chat_id"]})


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text):
        self.replies.append(text)


def update(chat_id, text=None):
    msg = FakeMessage()
    msg.text = text
    return SimpleNamespace(effective_chat=SimpleNamespace(id=chat_id), effective_message=msg)


def context(args=(), load=None, ask=None):
    data = {"owner": OWNER}
    if load:
        data["load"] = load
    if ask:
        data["ask"] = ask
    return SimpleNamespace(bot=FakeBot(), bot_data=data, args=list(args))


def run(coro):
    return asyncio.run(coro)


# --- rendering ------------------------------------------------------------------------------


def test_render_item_escapes_and_puts_the_source_first():
    text = nb.render_item(item("economics", 1))
    assert "Zebra &lt;exports&gt; &amp; rates" in text
    assert 'href="https://x.test/1?a=1&amp;b=&quot;2&quot;"' in text
    assert text.index("Test News") < text.index("<blockquote>") < text.index("Summary:")
    assert "Exports rose 5% &amp; more." in text and "Why it matters:" in text


def test_render_item_without_summary_says_pending():
    assert "Summary pending" in nb.render_item(item("economics", 1, summary=None))


def test_pack_fits_the_limit_and_keeps_every_block():
    blocks = [f"block {i} " + "x" * 900 for i in range(10)]
    msgs = nb.pack(blocks, limit=2000)
    assert all(len(m) <= 2000 for m in msgs)
    assert len(msgs) == 5
    assert all(any(b in m for m in msgs) for b in blocks)


def test_pack_splits_an_oversized_block_at_line_ends():
    big = "\n".join(f"line {i:03d} " + "y" * 50 for i in range(100))
    msgs = nb.pack(["head", big, "tail"], limit=1000)
    assert all(0 < len(m) <= 1000 for m in msgs)
    assert msgs[0] == "head" and msgs[-1].endswith("tail")
    assert "".join(msgs).count("line 0") == 100


def test_digest_messages_order_and_header():
    d = digest(
        [
            item("economics", 1),
            item("general", 1, title="Big story"),
            item("cambodia", 1, summary=None),
        ]
    )
    msgs = nb.digest_messages(d)
    text = "\n".join(msgs)
    assert "Friday 16 October 2026" in msgs[0] and "2 with summaries so far" in msgs[0]
    assert text.index("Top stories") < text.index("Economics") < text.index("Cambodia")
    assert all(len(m) <= nb.MAX_MESSAGE for m in msgs)


# --- sending and handlers ---------------------------------------------------------------------


def test_send_messages_html_no_previews_and_spaced():
    fake, waits = FakeBot(), []

    async def sleep(s):
        waits.append(s)

    n = run(nb.send_messages(fake, OWNER, ["one", "two"], sleep=sleep))
    assert n == 2 and waits == [nb.SEND_GAP_S]
    assert all(m["parse_mode"] == "HTML" and m["chat_id"] == OWNER for m in fake.sent)
    assert fake.sent[0]["link_preview_options"].is_disabled is True


def test_start_answers_the_owner_only_and_refuses_strangers_once():
    ctx = context()
    up = update(OWNER)
    run(nb.handle_start(up, ctx))
    assert up.effective_message.replies == [nb.START_TEXT]

    stranger = update(STRANGER)
    run(nb.handle_start(stranger, ctx))
    run(nb.handle_digest(stranger, ctx))
    run(nb.handle_other(stranger, ctx))
    assert stranger.effective_message.replies == [nb.REFUSAL_TEXT]  # once, nothing else
    assert ctx.bot.sent == []


def test_digest_command_sends_the_stored_digest_to_the_owner():
    days = []

    def load(day):
        days.append(day)
        return digest([item("economics", 1)])

    ctx = context(args=["2026-10-16"], load=load)
    run(nb.handle_digest(update(OWNER), ctx))
    assert days == [date(2026, 10, 16)]
    assert ctx.bot.sent and all(m["chat_id"] == OWNER for m in ctx.bot.sent)


def test_digest_without_a_date_sends_yesterday_then_today(monkeypatch):
    monkeypatch.setattr(nb, "today", lambda: date(2026, 10, 17))
    days = []

    def load(day):
        days.append(day)
        return Digest(day, "en", "fake", 9, 100, 50, [item("economics", 1)])

    up, ctx = update(OWNER), context(load=load)
    run(nb.handle_digest(up, ctx))
    assert days == [date(2026, 10, 16), date(2026, 10, 17)]
    headers = [m["text"] for m in ctx.bot.sent if "📰" in m["text"]]
    assert ["Friday 16 October" in headers[0], "Saturday 17 October" in headers[1]] == [True, True]
    assert up.effective_message.replies == []


@pytest.mark.parametrize("missing", [date(2026, 10, 16), date(2026, 10, 17)])
def test_digest_without_a_date_says_which_day_is_missing_and_sends_the_other(monkeypatch, missing):
    monkeypatch.setattr(nb, "today", lambda: date(2026, 10, 17))

    def load(day):
        return None if day == missing else Digest(day, "en", "fake", 9, 100, 50, [item("sport", 1)])

    up, ctx = update(OWNER), context(load=load)
    run(nb.handle_digest(up, ctx))
    assert up.effective_message.replies == [f"No digest stored for {missing} yet."]
    assert len([m for m in ctx.bot.sent if "📰" in m["text"]]) == 1


def test_digest_command_bad_date_and_missing_digest():
    up = update(OWNER)
    run(nb.handle_digest(up, context(args=["yesterday"], load=lambda d: None)))
    run(nb.handle_digest(up, context(args=["2026-10-01"], load=lambda d: None)))
    assert up.effective_message.replies == [
        "Use /digest or /digest YYYY-MM-DD.",
        "No digest stored for 2026-10-01 yet.",
    ]


def test_send_digest_with_an_injected_bot(monkeypatch):
    monkeypatch.setattr(nb, "load", lambda day: digest([item("sport", 1)]))
    fake = FakeBot()
    assert run(nb.send_digest(date(2026, 10, 16), bot=fake, chat_id=OWNER)) == 1
    monkeypatch.setattr(nb, "load", lambda day: None)
    with pytest.raises(LookupError):
        run(nb.send_digest(date(2026, 10, 16), bot=fake, chat_id=OWNER))


def test_send_text_is_plain_text_to_the_given_chat():
    fake = FakeBot()
    run(nb.send_text("⚠️ <collect> failed", bot=fake, chat_id=OWNER))
    assert fake.sent == [{"chat_id": OWNER, "text": "⚠️ <collect> failed"}]  # no HTML parsing


# --- configuration and secrets -----------------------------------------------------------------


def test_config_rejects_missing_and_example_values(monkeypatch, tmp_path):
    monkeypatch.setattr(nb, "ROOT", tmp_path)  # no .env there
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789:fake-bot-token")
    monkeypatch.setenv("TELEGRAM_OWNER_CHAT_ID", "123456789")
    with pytest.raises(nb.ConfigError, match="TELEGRAM_BOT_TOKEN") as e:
        nb.config()
    assert "fake-bot-token" not in str(e.value)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "999:real-looking-token")
    with pytest.raises(nb.ConfigError, match="TELEGRAM_OWNER_CHAT_ID"):
        nb.config()
    monkeypatch.setenv("TELEGRAM_OWNER_CHAT_ID", "4242")
    assert nb.config() == ("999:real-looking-token", 4242)


def test_http_request_logs_are_quiet():
    nb.quiet_http_logs()
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


def test_build_app_needs_no_network():
    app = nb.build_app("123:not-a-real-token", OWNER)
    assert app.bot_data["owner"] == OWNER
    assert len(app.handlers[0]) == 5


# --- chat (task 1.9b) ---------------------------------------------------------------------------


def test_owner_text_is_a_question_answered_in_html_after_typing():
    asked = []

    def ask(question, chat_id):
        asked.append((question, chat_id))
        return 'Up &amp; down.\n\n<b>Sources</b>\n1. <a href="u">T</a>'

    ctx = context(ask=ask)
    run(nb.handle_other(update(OWNER, "How is bitcoin?"), ctx))
    assert asked == [("How is bitcoin?", OWNER)]
    assert ctx.bot.sent[0] == {"action": "typing", "chat_id": OWNER}
    reply = ctx.bot.sent[1]
    assert reply["chat_id"] == OWNER and reply["parse_mode"] == "HTML"
    assert reply["text"].startswith("Up &amp; down.")
    assert reply["link_preview_options"].is_disabled is True


def test_a_long_answer_is_split_under_the_limit():
    ctx = context(ask=lambda q, c: "\n".join(["word " * 100] * 30))
    run(nb.handle_other(update(OWNER, "q"), ctx))
    texts = [m["text"] for m in ctx.bot.sent if "text" in m]
    assert len(texts) > 1 and all(len(t) <= nb.MAX_MESSAGE for t in texts)


def test_non_text_and_unknown_commands_ask_nothing():
    asked = []
    ctx = context(ask=lambda q, c: asked.append(q) or "")
    photo, cmd = update(OWNER, None), update(OWNER, "/weather")
    run(nb.handle_other(photo, ctx))
    run(nb.handle_other(cmd, ctx))
    assert asked == []
    assert photo.effective_message.replies == [nb.NOT_TEXT]
    assert cmd.effective_message.replies == [nb.START_TEXT]


def test_a_strangers_question_is_refused_and_never_asked():
    asked = []
    ctx = context(ask=lambda q, c: asked.append(q) or "")
    stranger = update(STRANGER, "What is the news?")
    run(nb.handle_other(stranger, ctx))
    assert asked == [] and ctx.bot.sent == []
    assert stranger.effective_message.replies == [nb.REFUSAL_TEXT]


def test_ask_question_uses_the_shared_memory_and_never_logs_the_text(monkeypatch, caplog):
    from natalia import chat

    seen = {}

    def answer(conn, message, chat_id, *, memory, log):
        seen["memory"] = memory
        return chat.Answer("en", "chat", "Hey! 👋", requests=1, input_tokens=900, output_tokens=40)

    monkeypatch.setattr(chat, "answer", answer)
    monkeypatch.setattr(nb.db, "connect", lambda **kw: contextlib.nullcontext())
    with caplog.at_level(logging.INFO, logger="natalia.bot"):
        assert nb.ask_question("my private words", OWNER) == "Hey! 👋"
    assert seen["memory"] is chat.MEMORY
    assert "kind=chat" in caplog.text and "requests=1" in caplog.text
    assert "private" not in caplog.text


def test_forget_clears_the_owners_memory_and_strangers_are_refused():
    from natalia import chat

    memory = chat.Memory()
    memory.add(OWNER, chat.Turn("user", "Bitcoin?"), chat.Turn("natalia", "It fell."))
    memory.add(STRANGER, chat.Turn("user", "hi"))
    ctx = context()
    ctx.bot_data["memory"] = memory
    stranger = update(STRANGER, "/forget")
    run(nb.handle_forget(stranger, ctx))
    assert stranger.effective_message.replies == [nb.REFUSAL_TEXT]
    assert len(memory.get(OWNER)) == 2

    up = update(OWNER, "/forget")
    run(nb.handle_forget(up, ctx))
    assert up.effective_message.replies == [nb.FORGET_TEXT]
    assert memory.get(OWNER) == [] and len(memory.get(STRANGER)) == 1
    assert ctx.bot.sent == []  # no LLM call, nothing else sent
    assert "/forget" in nb.START_TEXT
