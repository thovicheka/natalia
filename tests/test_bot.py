"""Tests for the Telegram bot (task 1.8). No network, no token: a fake bot records what would
be sent, and handlers get stand-in updates. Digests are made up (no database)."""

import asyncio
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


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text):
        self.replies.append(text)


def update(chat_id):
    return SimpleNamespace(
        effective_chat=SimpleNamespace(id=chat_id), effective_message=FakeMessage()
    )


def context(args=(), load=None):
    data = {"owner": OWNER}
    if load:
        data["load"] = load
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
    assert len(app.handlers[0]) == 4
