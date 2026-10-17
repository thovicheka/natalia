"""Natalia's Telegram bot (task 1.8): sends the stored digest to the owner, answers the owner.

    uv run python -m natalia.bot send --dry-run           # print the messages, send nothing
    uv run python -m natalia.bot send --date 2026-10-16   # send a stored digest to the owner's chat
    uv run python -m natalia.bot run                      # long polling (the systemd service)

Natalia's own bot (not cloud-ai-lab's alert bot): TELEGRAM_BOT_TOKEN and TELEGRAM_OWNER_CHAT_ID
from the environment or `.env`. Long polling only makes outgoing requests, so no webhook and no
open port. Until task 2.1 adds family and friends' allowlist, only the owner's chat gets answers;
anyone else gets one short refusal and nothing else (no LLM call, nothing stored).

The token is a secret: it is never printed, and the HTTP library's request log (which would show
it inside every API URL) is kept at WARNING.

Commands (owner only): /start, /digest (yesterday's and today's digests, or /digest 2026-10-16
for one day), /help. They read stored digests: no LLM call. Task 2.2 adds /today and the
per-topic commands. `send_text` is the daily flow's alert to the owner (task 1.9).

Chat (task 1.9b, owner only): any other text message is a question, answered by Haiku from the
stored articles, with sources (natalia/chat.py; one LLM request, ~$0.001, at most 20 a day).
Questions are answered one at a time, so only one retrieval process (~330 MB) runs at once.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from natalia import db
from natalia.digest import DIGEST_ORDER, TOPIC_NAMES, Digest, DigestItem, detail, load_digest
from natalia.topics import LOCAL_TZ

ROOT = Path(__file__).resolve().parent.parent
MAX_MESSAGE = 4096  # Telegram's limit per message, in characters
SEND_GAP_S = 1.1  # between messages to one chat (Telegram allows about 1 a second)

log = logging.getLogger("natalia.bot")

START_TEXT = (
    "Hi, I'm Natalia, your news agent. Every morning I send a digest of the day's top stories, "
    "each with its source, a short summary and why it matters.\n\n"
    "/digest: yesterday's and today's digests\n/digest 2026-10-16: one day's\n/help: this message"
    "\n\nOr just ask me about the news, in English or Khmer, and I'll answer from the stored "
    "articles, with links."
)
NOT_TEXT = "I can only read text messages for now."

REFUSAL_TEXT = "Sorry, this is a private bot."


class ConfigError(RuntimeError):
    pass


def config() -> tuple[str, int]:
    """(token, owner chat id) from the environment or `.env`. Never logs the token."""
    load_dotenv(ROOT / ".env", override=False)
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    owner = os.environ.get("TELEGRAM_OWNER_CHAT_ID", "").strip()
    if not token or token.endswith("fake-bot-token"):
        raise ConfigError("TELEGRAM_BOT_TOKEN is not set (environment or .env); see task 1.8")
    if not owner.lstrip("-").isdigit() or owner == "123456789":
        raise ConfigError("TELEGRAM_OWNER_CHAT_ID is not set to a chat id; see task 1.8")
    return token, int(owner)


def quiet_http_logs() -> None:
    """httpx logs every request URL at INFO, and Telegram URLs contain the bot token."""
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)


# --- rendering ------------------------------------------------------------------------------


def _e(text: str) -> str:
    return html.escape(text, quote=False)


def render_item(it: DigestItem) -> str:
    """One story in Telegram HTML: the source first (headline, link, its own words), then the
    AI summary and why it matters."""
    a = it.article
    when = a.published_at.astimezone(LOCAL_TZ).strftime("%d %b %H:%M")
    pay = " · paywalled" if a.paywalled else ""
    parts = [
        f'<b>{it.position}. <a href="{html.escape(a.url)}">{_e(a.title)}</a></b>',
        f"<i>{_e(a.source)} · {when}{pay}</i>",
    ]
    if detail(a):
        parts.append(f"<blockquote>{_e(detail(a))}</blockquote>")
    if it.summary:
        parts.append(f"<b>Summary:</b> {_e(it.summary)}")
        parts.append(f"<b>Why it matters:</b> {_e(it.why_it_matters or '')}")
    else:
        parts.append("<i>Summary pending.</i>")
    return "\n".join(parts)


def _split(block: str, limit: int) -> list[str]:
    """A block longer than one message, cut at line ends (a single huge line is hard-cut)."""
    out, cur = [], ""
    for line in block.split("\n"):
        while len(line) > limit:
            if cur:
                out.append(cur)
                cur = ""
            out.append(line[:limit])
            line = line[limit:]
        if cur and len(cur) + 1 + len(line) > limit:
            out.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        out.append(cur)
    return out


def pack(blocks: list[str], limit: int = MAX_MESSAGE) -> list[str]:
    """Join blocks into as few messages as fit, never splitting a block that fits in one."""
    messages: list[str] = []
    cur = ""
    for block in blocks:
        if len(block) > limit:
            if cur:
                messages.append(cur)
                cur = ""
            messages.extend(_split(block, limit))
            continue
        joined = f"{cur}\n\n{block}" if cur else block
        if len(joined) > limit:
            messages.append(cur)
            cur = block
        else:
            cur = joined
    if cur:
        messages.append(cur)
    return messages


def digest_messages(d: Digest) -> list[str]:
    """The digest as Telegram messages: a header, then each topic's stories, packed."""
    done = sum(1 for it in d.items if it.summary)
    header = f"<b>📰 Natalia · {d.day:%A %d %B %Y}</b>\n{len(d.items)} stories"
    if done < len(d.items):
        header += f" ({done} with summaries so far)"
    header += ". The AI summary sits under each source: tap the headline to read it."
    blocks = [header]
    for topic in DIGEST_ORDER:
        items = d.by_topic()[topic]
        if not items:
            continue
        blocks.append(f"<b>━━ {_e(TOPIC_NAMES[topic])} ━━</b>")
        blocks.extend(render_item(it) for it in items)
    return pack(blocks)


def today() -> date:
    return datetime.now(LOCAL_TZ).date()


# --- sending --------------------------------------------------------------------------------


async def send_messages(bot, chat_id: int, messages: list[str], sleep=asyncio.sleep) -> int:
    """Send each message (HTML, no link previews), about one a second. Returns how many."""
    from telegram import LinkPreviewOptions

    for i, text in enumerate(messages):
        if i:
            await sleep(SEND_GAP_S)
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    return len(messages)


def load(day: date) -> Digest | None:
    with db.connect() as conn:
        return load_digest(conn, day)


async def send_digest(day: date, *, bot=None, chat_id: int | None = None) -> int:
    """Send the stored digest for `day` to the owner. Raises if there is none."""
    d = load(day)
    if d is None:
        raise LookupError(f"no digest stored for {day}")
    if bot is None or chat_id is None:
        from telegram import Bot

        token, owner = config()
        bot, chat_id = Bot(token), owner
        async with bot:
            return await send_messages(bot, chat_id, digest_messages(d))
    return await send_messages(bot, chat_id, digest_messages(d))


async def send_text(text: str, *, bot=None, chat_id: int | None = None) -> None:
    """One plain-text message to the owner (the daily flow's alerts)."""
    if bot is None or chat_id is None:
        from telegram import Bot

        token, owner = config()
        async with Bot(token) as bot:
            await bot.send_message(chat_id=owner, text=text)
        return
    await bot.send_message(chat_id=chat_id, text=text)


# --- the bot (long polling) -------------------------------------------------------------------


def is_owner(update, owner: int) -> bool:
    chat = update.effective_chat
    return chat is not None and chat.id == owner


async def handle_start(update, context) -> None:
    owner = context.bot_data["owner"]
    if not is_owner(update, owner):
        await refuse(update, context)
        return
    await update.effective_message.reply_text(START_TEXT)


async def handle_digest(update, context) -> None:
    owner = context.bot_data["owner"]
    if not is_owner(update, owner):
        await refuse(update, context)
        return
    if context.args:
        try:
            days = [date.fromisoformat(context.args[0])]
        except ValueError:
            await update.effective_message.reply_text("Use /digest or /digest YYYY-MM-DD.")
            return
    else:
        days = [today() - timedelta(days=1), today()]
    loader = context.bot_data.get("load", load)
    for day in days:
        d = loader(day)
        if d is None:
            await update.effective_message.reply_text(f"No digest stored for {day} yet.")
            continue
        await send_messages(context.bot, owner, digest_messages(d))


async def refuse(update, context) -> None:
    """One short refusal per chat per run; nothing else is done for strangers."""
    chat = update.effective_chat
    refused: set = context.bot_data.setdefault("refused", set())
    log.info("refused a message from a chat that isn't the owner's")
    if chat is not None and chat.id not in refused and update.effective_message:
        refused.add(chat.id)
        await update.effective_message.reply_text(REFUSAL_TEXT)


def build_app(token: str, owner: int):
    from telegram.ext import Application, CommandHandler, MessageHandler, filters

    app = Application.builder().token(token).build()
    app.bot_data["owner"] = owner
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("help", handle_start))
    app.add_handler(CommandHandler("digest", handle_digest))
    app.add_handler(MessageHandler(filters.ALL, handle_other))
    return app


async def handle_other(update, context) -> None:
    owner = context.bot_data["owner"]
    if not is_owner(update, owner):
        await refuse(update, context)
        return
    msg = update.effective_message
    if msg is None:
        return
    if not msg.text or msg.text.startswith("/"):
        await msg.reply_text(NOT_TEXT if not msg.text else START_TEXT)
        return
    ask = context.bot_data.get("ask", ask_question)
    lock = context.bot_data.setdefault("chat_lock", asyncio.Lock())
    async with lock:  # one question at a time: one retrieval process, one LLM call
        await context.bot.send_chat_action(chat_id=owner, action="typing")
        reply = await asyncio.to_thread(ask, msg.text, owner)
    for part in pack([reply]):
        await context.bot.send_message(
            chat_id=owner,
            text=part,
            parse_mode="HTML",
            link_preview_options=_no_previews(),
        )


def ask_question(question: str, chat_id: int) -> str:
    """Answer one chat question (blocking: retrieval child + one LLM call); Telegram HTML."""
    from natalia import chat

    with db.connect(autocommit=True) as conn:
        a = chat.answer(conn, question, chat_id, log=log.info)
    log.info(
        "chat: lang=%s retrieved=%d covered=%s sources=%d tokens=%d+%d%s",
        a.language,
        len(a.retrieved),
        a.covered,
        len(a.sources),
        a.input_tokens,
        a.output_tokens,
        " over cap" if a.over_cap else (f" error={a.error[:120]}" if a.error else ""),
    )
    return chat.render(a)


def _no_previews():
    from telegram import LinkPreviewOptions

    return LinkPreviewOptions(is_disabled=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("send", help="send a stored digest to the owner's chat")
    s.add_argument("--date", type=date.fromisoformat)
    s.add_argument("--dry-run", action="store_true", help="print the messages, send nothing")
    sub.add_parser("run", help="long polling (what the systemd service runs)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    quiet_http_logs()

    if args.command == "send":
        day = args.date or today()
        if args.dry_run:
            d = load(day)
            if d is None:
                print(f"no digest stored for {day}")
                return 1
            msgs = digest_messages(d)
            for i, m in enumerate(msgs, 1):
                print(f"--- message {i}/{len(msgs)} ({len(m)} characters)\n{m}")
            return 0
        try:
            n = asyncio.run(send_digest(day))
        except (ConfigError, LookupError) as e:
            print(e)
            return 1
        print(f"sent the {day} digest: {n} messages")
        return 0

    try:
        token, owner = config()
    except ConfigError as e:
        print(e)
        return 1
    log.info("starting long polling (owner-only)")
    build_app(token, owner).run_polling(allowed_updates=["message"], drop_pending_updates=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
