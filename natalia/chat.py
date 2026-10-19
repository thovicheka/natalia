"""Chat with Natalia (tasks 1.9b, 1.9c, 1.9d): a friendly assistant that is also a news expert.

    uv run python -m natalia.chat ask "yo" "Bitcoin price this week" "tell me more"   # real
    uv run python -m natalia.chat ask "Bitcoin price this week" --dry-run   # prompts only, no LLM
    echo "question" | uv run python -m natalia.chat retrieve                # the search child

How a message is answered:
1. **Cap**: at most DAILY_MESSAGES per chat per day (Asia/Phnom_Penh). The message is counted
   before anything is sent, so a failing one still counts.
2. **Reply or search** (one Haiku request, small): Haiku gets the last few messages of the chat
   (`Memory`) and the new one, and decides. Small talk ("chat") and questions answered from lasting
   general knowledge ("general", e.g. how to fix brakes; the reply says it isn't from the news):
   it writes the reply itself, in the person's language and tone; no search, no sources. A
   follow-up with nothing to follow ("tell me more" right after /forget) or a message too vague
   to act on ("clarify"): it asks what they mean. News and current facts (prices, who holds a
   role, recent events, or a follow-up like "tell me more"): it writes a standalone search query
   instead, because its own knowledge of them is out of date. Two more kinds get their own
   second request (1.9d): questions about Natalia's own data ("data": which days, how many
   articles, which sources) are answered from counts read from the database, and a request to
   translate her previous answer ("translate") translates the full answer, not the cut copy kept
   for context.
3. **Search**, in a child process (`retrieve`): embed the query with the local e5 model and take
   the nearest stored articles of the last RETRIEVE_DAYS days (pgvector). The model takes ~300
   MB; in a child it is freed as soon as the search is done, so the bot stays small. The query
   goes to the child on stdin, never on the command line (visible in `ps`).
4. **Answer** (a second Haiku request): the articles (oldest first), the conversation and the
   message; JSON back: covered or not, the answer, the ids of the articles it used. Facts only
   from the articles; the answer analyzes them (why it matters, related stories, how sources
   differ, what changed over the days) and says so when they don't cover the question.
5. **Reply**: the answer, then the sources it used (headline as a link, source, date), taken from
   the database, so every link is a real stored article. Ids the LLM made up are dropped, and an
   answer that says the news doesn't cover the question lists no sources.

Every request runs with thinking off and room for a Khmer reply (Khmer takes ~3-4x the tokens of
English); a reply that still stops at max_tokens is asked again once with twice the room (1.9d).

Memory: the last MEMORY_MESSAGES messages of each chat (the owner's and Natalia's, each cut to
MEMORY_CHARS for the prompts; Natalia's also kept whole, with its sources, for "translate"), in
the bot's RAM only. Forgotten after MEMORY_IDLE_S without a message, on /forget,
or when the bot restarts. Never written to the database or the logs: `chat_questions` keeps
counts and tokens only. The messages are sent to the LLM provider (Anthropic) to be answered:
that is the feature, and it's the owner's own text.
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import psycopg

from natalia import db, llm
from natalia.topics import LOCAL_TZ

DAILY_MESSAGES = 50  # per chat per day; ~$0.0001 (small talk) to ~$0.002 each, ≤ ~$0.1 a day
RETRIEVE_K = 8  # articles given to the LLM
RETRIEVE_DAYS = 30  # only articles from the last 30 days
MAX_DISTANCE = 0.25  # cosine distance; farther articles aren't related enough to send
TEXT_CHARS = 1200  # of each article's text sent to the LLM
# Output room per request; thinking is off (1.9d), so it is all reply. A Khmer news answer took
# 868 tokens for less than half of it (bot log, 2026-10-19 12:19 UTC); Khmer uses ~3-4x the
# tokens of English. A reply that still stops at the limit is asked again once with twice as much.
MAX_OUTPUT_TOKENS = 4000  # a news answer
REPLY_OUTPUT_TOKENS = 3000  # the reply-or-search request (a how-to answer in Khmer)
DATA_OUTPUT_TOKENS = 3000  # an answer about Natalia's own data (may list the sources)
TRANSLATE_OUTPUT_TOKENS = 4000  # a translation of a previous answer
RETRY_FACTOR = 2  # the one retry after max_tokens gets this many times the room
RETRIEVE_TIMEOUT_S = 120
QUESTION_CHARS = 1000  # a longer message is cut
DATA_DAYS = 30  # days of article counts in the data facts
MEMORY_MESSAGES = 6  # remembered per chat: 3 of the owner's and 3 of Natalia's
MEMORY_CHARS = 600  # of each remembered message
SOURCES_CHARS = 300  # of the headlines remembered with a news answer
MEMORY_IDLE_S = 30 * 60  # a chat silent this long starts afresh

# In every prompt (1.9d): Natalia is a woman, and Khmer marks the speaker's gender. A Khmer reply
# said "បាទ" (what men say) in real use.
PERSONA = """You are a woman. In Khmer, always speak as a woman does: say ចាស (or ចាស៎) for \
"yes" and as the polite particle, and refer to yourself as ខ្ញុំ (នាងខ្ញុំ when formal). Never \
use បាទ or ខ្ញុំបាទ: those are what men say."""

REPLY_SYSTEM = (
    """You are Natalia, chatting with one person on Telegram. You're a normal, \
friendly person, and your specialty is news: every day you collect articles on economics, world \
politics, technology, science, sport, crypto, stock markets, Cambodia and the top stories, then \
analyze them and report what matters. """
    + PERSONA
    + """

Decide what the new message needs:
- "clarify": the message only makes sense as a follow-up ("tell me more", "why?", "what about the \
second one?", "translate that") but the conversation so far has nothing it could refer to, or \
it is too vague to know what they want. Don't guess a topic. In "reply", briefly and warmly ask \
what they mean (for example which story or topic), and mention /digest for the day's top \
stories. Leave "search" empty.
- "news": anything about news or current facts: recent events, prices, scores, who holds a role \
now, what someone did lately, or a follow-up on news already discussed ("tell me more", "why?", \
"and Ethereum?"). Your own knowledge of these is out of date, so they are always "news", even \
when you think you know. Leave "reply" empty. In "search", write a short standalone search query \
for the stored articles, with names and topics filled in from the conversation (after Bitcoin's \
price, "tell me more" becomes "Bitcoin price this week"). Keep the query in the message's \
language.
- "data": a question about your own stored data rather than about the news itself: which days \
you have news or digests for, how many articles you have (today, per day, in total), which \
sources or topics you use, how often you collect. Leave "reply" and "search" empty: the answer \
is written from your database.
- "translate": a request to translate your previous answer, or say it again in another language \
("in Khmer please", "translate to English"). Leave "reply" and "search" empty: the full previous \
answer is translated for you. If you haven't answered anything yet, it's "clarify".
- "general": a question you can answer from lasting general knowledge that doesn't depend on \
recent events: how-to, how things work, science, history, definitions, advice ("how do I fix my \
car's brakes?"). Answer it helpfully in "reply": clear and practical, a few sentences, or short \
steps if that helps; mention safety when it matters. Don't add a note that it's general \
knowledge: one is added for you. Leave "search" empty.
- "chat": greetings, small talk, jokes, slang, thanks, how you are, questions about you. Write \
"reply" and leave "search" empty.

How to write a "chat", "general" or "clarify" reply:
- Like a friendly person texting back: natural and warm. Chat replies are usually one to three \
short sentences.
- Match the person's language and tone: Khmer, English, or the same mix of both; casual if they \
are casual, slang if they use slang, polite if they are formal.
- No sources or links. Never state current facts (prices, who holds a role, recent events) from \
your own knowledge; if they come up, offer to check the news, or mention /digest for the day's \
top stories.
- If they seem genuinely upset, sad or stressed: be kind and brief, no jokes and no news, and \
gently suggest talking to someone they trust. If they say they might hurt themselves or are in \
danger, urge them to contact local emergency services or someone near them right away.
The latest message is mostly {language}.
Today is {today} (Asia/Phnom_Penh)."""
)

REPLY_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {
            "type": "string",
            "enum": ["chat", "general", "clarify", "news", "data", "translate"],
        },
        "reply": {"type": "string"},
        "search": {"type": "string"},
    },
    "required": ["kind", "reply", "search"],
}

SYSTEM = (
    """You are Natalia, a friendly news analyst, answering a question in a Telegram chat. \
The numbered news articles given with it are your only source for facts about current events; \
they are listed oldest first. """
    + PERSONA
    + """ Rules:
- Facts (what happened, numbers, prices, names, who holds a role, dates) come only from those \
articles. Never add them from your own knowledge, which is out of date.
- Analyze, don't just repeat: say why it matters; connect related stories among the articles; \
when several sources report it, compare how they report it (numbers, emphasis, tone); when the \
articles span several days, say what changed. Do each only when the articles support it. Your \
explanation may use general understanding (how markets or politics usually work), but never as \
a new fact.
- If the articles don't answer the question, set "covered" to false and say briefly that the \
stored news doesn't cover it (you may name what the articles are about). Don't guess.
- The conversation so far is given for context: for a follow-up ("tell me more"), add new \
details and analysis instead of repeating what was already said.
- Keep it readable on a phone: about 3 to 8 sentences, plain words, in one or two short \
paragraphs; no headings.
- Don't put article numbers, ids or links in the answer text. In "source_ids", list only the \
articles whose facts are in your answer, most important first; none if "covered" is false.
- Reply in the language and tone of the latest message: Khmer, English, or the same mix. It is \
mostly {language}.
Today is {today} (Asia/Phnom_Penh)."""
)

SCHEMA = {
    "type": "object",
    "properties": {
        "covered": {"type": "boolean"},
        "answer": {"type": "string"},
        "source_ids": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["covered", "answer", "source_ids"],
}

DATA_SYSTEM = (
    """You are Natalia, a friendly person whose specialty is news, chatting on Telegram. \
You collect news articles every day and build a morning digest of the top stories per topic. \
"""
    + PERSONA
    + """ Answer the question about your own stored data using only the facts given with it \
(read from your database just now). Don't guess numbers or dates that aren't there: if the \
facts don't answer it, say what you do know. When asked which days you have news for, give the \
days and how many articles each, and the digests. When asked about sources, name them grouped \
by topic, and say paywalled ones give only a headline and excerpt. Keep it short and readable \
on a phone; no headings. Reply in the language and tone of the latest message: Khmer, English, \
or the same mix. It is mostly {language}.
Today is {today} (Asia/Phnom_Penh)."""
)

DATA_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}

TRANSLATE_SYSTEM = (
    """You are Natalia, translating your own previous answer in a Telegram chat. """
    + PERSONA
    + """ Translate the whole answer into the language the person asks for (if they don't \
name one: into English if the answer is in Khmer, otherwise into Khmer). It must be complete: \
every sentence, story, fact, number, name and date, in the same order and the same paragraphs. \
Don't summarize, shorten, merge, add or leave out anything. Keep names recognizable (the usual \
spelling in that language). Put only the translation in "translation".
Today is {today} (Asia/Phnom_Penh)."""
)

TRANSLATE_SCHEMA = {
    "type": "object",
    "properties": {"translation": {"type": "string"}},
    "required": ["translation"],
}

KINDS = ("chat", "general", "clarify", "news", "data", "translate")
REPLY_KINDS = ("chat", "general", "clarify")  # answered by the first request itself
LANGUAGES = {"en": "English", "km": "Khmer (ភាសាខ្មែរ)"}
TEXTS = {
    "en": {
        "sources": "Sources",
        "cap": "That's {cap} messages today, the daily limit. Talk to you tomorrow!",
        "failed": "Sorry, I couldn't answer just now. Please try again later.",
        "nothing": "I couldn't find anything about that in the stored news.",
        "general": "General knowledge, not from today's news.",
        "no_previous": "I haven't answered anything yet that I could translate. What would you "
        "like to know?",
    },
    "km": {
        "sources": "ប្រភព",
        "cap": "ថ្ងៃនេះអ្នកបានផ្ញើ {cap} សារហើយ ដែលជាចំនួនកំណត់ប្រចាំថ្ងៃ។ ជួបគ្នាថ្ងៃស្អែក!",
        "failed": "សូមអភ័យទោស ខ្ញុំមិនអាចឆ្លើយបានទេឥឡូវនេះ។ សូមព្យាយាមម្តងទៀតនៅពេលក្រោយ។",
        "nothing": "ខ្ញុំរកមិនឃើញព័ត៌មានអំពីរឿងនេះក្នុងព័ត៌មានដែលបានរក្សាទុកទេ។",
        "general": "នេះជាចំណេះដឹងទូទៅ មិនមែនមកពីព័ត៌មានថ្ងៃនេះទេ។",
        "no_previous": "ខ្ញុំមិនទាន់បានឆ្លើយអ្វីដែលអាចបកប្រែបានទេ។ តើអ្នកចង់ដឹងអំពីអ្វីដែរ?",
    },
}


class ChatError(RuntimeError):
    """Retrieval failed (the child process); the question can't be answered now."""


# --- conversation memory --------------------------------------------------------------------


@dataclass
class Turn:
    role: str  # "user" or "natalia"
    text: str  # cut to MEMORY_CHARS: what the prompts see
    full: str = ""  # Natalia's whole reply, for "translate" (1.9d)
    kind: str = ""  # of Natalia's reply ("general" keeps its note when translated)
    sources: list[Source] = field(default_factory=list)  # the ones the reply listed


class Memory:
    """The last few messages of each chat, in RAM only (see the module docstring). Thread-safe:
    the bot answers in a worker thread."""

    def __init__(self, size: int = MEMORY_MESSAGES, idle_s: float = MEMORY_IDLE_S, clock=None):
        self.size, self.idle_s = size, idle_s
        self.clock = clock or time.monotonic
        self._chats: dict[int, tuple[float, deque[Turn]]] = {}
        self._lock = threading.Lock()

    def _expire(self, now: float) -> None:
        for chat_id in [c for c, (t, _) in self._chats.items() if now - t > self.idle_s]:
            del self._chats[chat_id]

    def get(self, chat_id: int) -> list[Turn]:
        with self._lock:
            self._expire(self.clock())
            return list(self._chats[chat_id][1]) if chat_id in self._chats else []

    def add(self, chat_id: int, *turns: Turn) -> None:
        with self._lock:
            now = self.clock()
            self._expire(now)
            _, kept = self._chats.get(chat_id, (now, deque(maxlen=self.size)))
            kept.extend(turns)
            self._chats[chat_id] = (now, kept)

    def forget(self, chat_id: int) -> None:
        with self._lock:
            self._chats.pop(chat_id, None)


MEMORY = Memory()  # the bot's; one process, one memory


def language(text: str) -> str:
    """'km' if the text is mostly Khmer script (U+1780–U+17FF, U+19E0–U+19FF), else 'en'."""
    khmer = sum(1 for c in text if "ក" <= c <= "៿" or "᧠" <= c <= "᧿")
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    return "km" if khmer and khmer >= latin else "en"


# --- the daily cap --------------------------------------------------------------------------


def day_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(LOCAL_TZ)
    return datetime.combine(now.astimezone(LOCAL_TZ).date(), datetime.min.time(), LOCAL_TZ)


def asked_today(conn: psycopg.Connection, chat_id: int, now: datetime | None = None) -> int:
    return conn.execute(
        "SELECT count(*) FROM chat_questions WHERE chat_id = %s AND asked_at >= %s",
        (chat_id, day_start(now)),
    ).fetchone()[0]


def record_question(conn: psycopg.Connection, chat_id: int, lang: str) -> int:
    return conn.execute(
        "INSERT INTO chat_questions (chat_id, language) VALUES (%s, %s) RETURNING id",
        (chat_id, lang),
    ).fetchone()[0]


def record_answer(conn: psycopg.Connection, qid: int, a: Answer) -> None:
    conn.execute(
        """UPDATE chat_questions SET kind = %s, retrieved = %s, covered = %s, source_ids = %s,
           model = %s, requests = %s, input_tokens = %s, output_tokens = %s, error = %s
           WHERE id = %s""",
        (
            a.kind or None,
            len(a.retrieved),
            a.covered,
            [s.id for s in a.sources],
            a.model or None,
            a.requests,
            a.input_tokens,
            a.output_tokens,
            a.error or None,
            qid,
        ),
    )


# --- retrieval ------------------------------------------------------------------------------


def nearest(
    conn: psycopg.Connection,
    vector,
    model: str,
    *,
    k: int = RETRIEVE_K,
    days: int = RETRIEVE_DAYS,
    max_distance: float = MAX_DISTANCE,
) -> list[tuple[int, float]]:
    """(article id, cosine distance) of the k nearest articles of the last `days` days."""
    conn.execute("SET hnsw.ef_search = 200")  # the date filter runs after the index scan
    rows = conn.execute(
        """SELECT a.id, e.embedding <=> %s::vector AS d
           FROM embeddings e JOIN articles a ON a.id = e.article_id
           WHERE e.model = %s
             AND coalesce(a.published_at, a.collected_at) >= now() - make_interval(days => %s)
           ORDER BY d LIMIT %s""",
        (db.to_vector(vector), model, days, k),
    ).fetchall()
    return [(i, round(float(d), 4)) for i, d in rows if d <= max_distance]


def retrieve_here(question: str, k: int = RETRIEVE_K) -> list[tuple[int, float]]:
    """Embed and search in this process (what the child runs)."""
    from natalia.embeddings import Embedder

    embedder = Embedder()
    vec = embedder.embed([question], "query")[0]
    with db.connect(autocommit=True) as conn:
        return nearest(conn, vec, embedder.name, k=k)


def retrieve(question: str, k: int = RETRIEVE_K, run=subprocess.run) -> list[tuple[int, float]]:
    """Embed and search in a child process, so the model's memory is freed right after."""
    try:
        p = run(
            [sys.executable, "-m", "natalia.chat", "retrieve", "-k", str(k)],
            input=question,
            capture_output=True,
            text=True,
            timeout=RETRIEVE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as e:
        raise ChatError(f"retrieval took over {RETRIEVE_TIMEOUT_S} s") from e
    if p.returncode != 0:
        tail = " | ".join(p.stderr.strip().splitlines()[-3:])
        raise ChatError(f"retrieval exited with code {p.returncode}: {tail[:300]}")
    return [(int(i), float(d)) for i, d in json.loads(p.stdout)]


# --- answering ------------------------------------------------------------------------------


@dataclass
class Source:
    id: int
    title: str
    url: str
    source: str
    published_at: datetime | None
    text: str = ""


@dataclass
class Answer:
    language: str
    # "chat", "general", "clarify" (the first request's own reply), "news", "data" or
    # "translate" (a second request); "" if it never got there
    kind: str = ""
    text: str = ""
    covered: bool | None = None
    sources: list[Source] = field(default_factory=list)  # the ones the answer used
    retrieved: list[int] = field(default_factory=list)
    model: str = ""
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    retries: int = 0  # requests asked again after stopping at max_tokens
    error: str = ""
    over_cap: bool = False
    translated_kind: str = ""  # for "translate": the kind of the answer translated


def load_sources(conn: psycopg.Connection, ids: list[int]) -> dict[int, Source]:
    rows = conn.execute(
        """SELECT a.id, a.title, a.url, s.name, coalesce(a.published_at, a.collected_at),
                  concat_ws(E'\\n', nullif(a.excerpt, ''), left(a.body, %s))
           FROM articles a JOIN sources s ON s.id = a.source_id WHERE a.id = ANY(%s)""",
        (TEXT_CHARS, ids),
    ).fetchall()
    return {r[0]: Source(*r) for r in rows}


def conversation(history: list[Turn]) -> str:
    """The remembered messages, oldest first, for a prompt ("" if there are none)."""
    if not history:
        return ""
    lines = [f"{'Natalia' if t.role == 'natalia' else 'Them'}: {t.text}" for t in history]
    return "Conversation so far:\n<conversation>\n" + "\n".join(lines) + "\n</conversation>\n\n"


NO_CONVERSATION = (
    "Conversation so far: none. This is the start of the conversation: there are no earlier "
    "messages to refer to (they may have been forgotten).\n\n"
)


def build_reply_prompt(message: str, history: list[Turn] = ()) -> str:
    """The first request's prompt. It says so when there's no conversation, so a follow-up like
    "tell me more" with nothing to follow is asked about instead of searched (1.9d)."""
    return (conversation(list(history)) or NO_CONVERSATION) + f"New message: {message}"


def build_prompt(question: str, articles: list[Source], history: list[Turn] = ()) -> str:
    """The articles oldest first (so changes over days read in order), the conversation, the
    question."""
    blocks = []
    oldest = datetime.min.replace(tzinfo=LOCAL_TZ)
    for a in sorted(articles, key=lambda a: (a.published_at or oldest, a.id)):
        when = "?"
        if a.published_at:
            when = a.published_at.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")
        text = " ".join(a.text.split())[:TEXT_CHARS]
        blocks.append(f"[{a.id}] {a.title}\nSource: {a.source}, {when}\n{text}")
    return (
        "Articles:\n\n"
        + "\n\n".join(blocks)
        + "\n\n"
        + conversation(list(history))
        + f"Question: {question}"
    )


def data_facts(conn: psycopg.Connection, now: datetime) -> str:
    """What Natalia has stored, read from the database for a "data" question (1.9d): articles
    collected per day (Asia/Phnom_Penh), the digests, and the sources by topic. Public feed names
    and counts only."""
    now = now.astimezone(LOCAL_TZ)
    today = now.date()
    since = day_start(now) - timedelta(days=DATA_DAYS - 1)
    tz = str(LOCAL_TZ)
    per_day = conn.execute(
        """SELECT (collected_at AT TIME ZONE %s)::date, count(*) FROM articles
           WHERE collected_at >= %s GROUP BY 1 ORDER BY 1""",
        (tz, since),
    ).fetchall()
    total, first, last = conn.execute(
        """SELECT count(*), min((collected_at AT TIME ZONE %s)::date),
                  max((collected_at AT TIME ZONE %s)::date) FROM articles""",
        (tz, tz),
    ).fetchone()
    digests = conn.execute(
        """SELECT d.digest_date, d.language, count(i.article_id) FROM digests d
           LEFT JOIN digest_items i ON i.digest_id = d.id
           WHERE d.digest_date >= %s GROUP BY d.id ORDER BY 1, 2""",
        (since.date(),),
    ).fetchall()
    sources = conn.execute(
        "SELECT topic, name, paywalled FROM sources WHERE enabled ORDER BY topic, name"
    ).fetchall()

    counts = dict(per_day)
    lines = [f"Natalia's stored data, as of {now:%Y-%m-%d %H:%M} (Asia/Phnom_Penh):"]
    if total:
        lines.append(f"- Articles: {total:,} stored, collected from {first} to {last}.")
    else:
        lines.append("- Articles: none stored yet.")
    lines.append(f"- Articles collected today ({today}): {counts.get(today, 0):,}.")
    days = "; ".join(f"{d}: {n:,}" for d, n in per_day) or "none"
    lines.append(
        f"- Days with articles in the last {DATA_DAYS} days (articles collected that day): {days}."
    )
    stories = "; ".join(f"{d} ({lang}, {n} stories)" for d, lang, n in digests) or "none"
    lines.append(
        f"- Morning digests (the top stories per topic, built at 05:00) in the last {DATA_DAYS} "
        f"days: {stories}."
    )
    lines.append(f"- Chat answers search the articles of the last {RETRIEVE_DAYS} days.")
    by_topic: dict[str, list[str]] = {}
    for topic, name, paywalled in sources:
        by_topic.setdefault(topic, []).append(name + (" *" if paywalled else ""))
    lines.append(
        f"- Sources: {len(sources)} feeds in {len(by_topic)} topics "
        "(* = paywalled: headline and excerpt only):"
    )
    lines += [f"  {t} ({len(names)}): {', '.join(names)}" for t, names in by_topic.items()]
    return "\n".join(lines)


def build_data_prompt(question: str, facts: str, history: list[Turn] = ()) -> str:
    return f"Facts:\n{facts}\n\n" + conversation(list(history)) + f"Question: {question}"


def previous_answer(history: list[Turn]) -> Turn | None:
    """Natalia's last reply that can be translated (kept whole), or None."""
    for t in reversed(history):
        if t.role == "natalia" and t.full:
            return t
    return None


def build_translate_prompt(message: str, previous: Turn) -> str:
    return (
        f"Your previous answer, in full:\n<answer>\n{previous.full}\n</answer>\n\n"
        f"Request: {message}"
    )


def answer(
    conn: psycopg.Connection,
    message: str,
    chat_id: int,
    *,
    memory: Memory | None = None,
    retrieve=retrieve,
    generate=llm.generate,
    cap: int = DAILY_MESSAGES,
    now: datetime | None = None,
    dry_run: bool = False,
    log=print,
) -> Answer:
    """Answer one message (see the module docstring). Never raises for a failed retrieval or
    LLM call: the Answer carries the error, and the bot says sorry. A dry run prints the
    prompts, searching with the message itself; no LLM call, nothing counted or remembered."""
    message = message.strip()[:QUESTION_CHARS]
    lang = language(message)
    a = Answer(language=lang)
    history = memory.get(chat_id) if memory else []
    if not dry_run:
        if asked_today(conn, chat_id, now) >= cap:
            a.over_cap = True
            return a
        qid = record_question(conn, chat_id, lang)
    now = now or datetime.now(LOCAL_TZ)
    today = now.astimezone(LOCAL_TZ).date()
    reply_prompt = build_reply_prompt(message, history)
    if dry_run:
        log(reply_prompt)
        a.kind, query = "news", message
    else:
        system = _system(REPLY_SYSTEM, a, today)
        route = _call(a, generate, reply_prompt, system, REPLY_SCHEMA, REPLY_OUTPUT_TOKENS, log)
        query = ""
        if route is not None:
            a.kind = route.get("kind") if route.get("kind") in KINDS else "chat"
            query = str(route.get("search") or "").strip()[:QUESTION_CHARS] or message
            if a.kind in REPLY_KINDS:
                a.text = str(route.get("reply") or "").strip()
                if not a.text:
                    a.error = "empty reply"
    if a.kind == "news":
        _news(conn, a, message, query, history, today, retrieve, generate, dry_run, log)
    elif a.kind == "data":
        _data(conn, a, message, history, now, generate, log)
    elif a.kind == "translate":
        _translate(a, message, history, today, generate, log)
    if not dry_run:
        record_answer(conn, qid, a)
        if memory is not None and a.text and not a.error:
            memory.add(chat_id, Turn("user", message[:MEMORY_CHARS]), natalia_turn(a))
    return a


def _system(template: str, a: Answer, today: date) -> str:
    return template.format(language=LANGUAGES[a.language], today=today.isoformat())


def _call(a: Answer, generate, prompt: str, system: str, schema: dict, max_tokens: int, log):
    """One LLM request for JSON, thinking off; its tokens are added to `a`. A reply cut off at
    max_tokens is asked again once with RETRY_FACTOR times the room (1.9d). None (and `a.error`)
    on failure."""
    for attempt in range(2):
        try:
            r = generate(
                prompt,
                system=system,
                json_schema=schema,
                max_output_tokens=max_tokens,
                thinking=False,
                purpose="chat",
            )
        except llm.LLMError as e:
            a.error = str(e)
            log(f"chat: {e}")
            return None
        a.model = r.model
        a.requests += r.requests
        a.input_tokens += r.input_tokens
        a.output_tokens += r.output_tokens + r.thinking_tokens
        try:
            reply = json.loads(r.text)
            if not isinstance(reply, dict):
                raise TypeError
            return reply
        except (json.JSONDecodeError, TypeError):
            pass
        if r.stop_reason == "max_tokens" and attempt == 0:
            a.retries += 1
            log(
                f"chat: reply stopped at max_tokens ({max_tokens}, {r.output_tokens} output + "
                f"{r.thinking_tokens} thinking tokens); asking again with "
                f"{max_tokens * RETRY_FACTOR}"
            )
            max_tokens *= RETRY_FACTOR
            continue
        break
    a.error = f"reply isn't the JSON asked for (stop reason {r.stop_reason or '?'})"
    log(f"chat: {a.error}")
    return None


def _news(conn, a: Answer, message, query, history, today, retrieve, generate, dry_run, log):
    """Search the stored articles for `query` and answer `message` from them."""
    try:
        hits = retrieve(query)
    except ChatError as e:
        a.error = str(e)
        log(f"chat: {e}")
        return
    a.retrieved = [i for i, _ in hits]
    found = load_sources(conn, a.retrieved)
    articles = [found[i] for i in a.retrieved if i in found]
    if not articles:
        a.covered = False
        return
    prompt = build_prompt(message, articles, history)
    if dry_run:
        log(prompt)
        return
    reply = _call(a, generate, prompt, _system(SYSTEM, a, today), SCHEMA, MAX_OUTPUT_TOKENS, log)
    if reply is None:
        return
    try:
        a.covered = bool(reply["covered"])
        a.text = str(reply["answer"]).strip()
        used = [int(i) for i in reply.get("source_ids", [])]
    except (KeyError, TypeError, ValueError):
        a.error = "reply isn't the JSON asked for"
        log(f"chat: {a.error}")
        return
    if not a.covered:
        return  # "the news doesn't cover it": no sources, whatever the ids say
    by_id = {s.id: s for s in articles}
    seen: set[int] = set()
    for i in used:
        if i in by_id and i not in seen:  # an id that wasn't sent is dropped, never linked
            seen.add(i)
            a.sources.append(by_id[i])


def _data(conn, a: Answer, message, history, now, generate, log):
    """Answer a question about Natalia's own data from what the database says now."""
    prompt = build_data_prompt(message, data_facts(conn, now), history)
    system = _system(DATA_SYSTEM, a, now.astimezone(LOCAL_TZ).date())
    reply = _call(a, generate, prompt, system, DATA_SCHEMA, DATA_OUTPUT_TOKENS, log)
    if reply is not None:
        a.text = str(reply.get("answer") or "").strip()
        if not a.text:
            a.error = "empty reply"


def _translate(a: Answer, message, history, today, generate, log):
    """Translate Natalia's previous answer in full, keeping its sources and its note."""
    previous = previous_answer(history)
    if previous is None:  # nothing to translate (e.g. after /forget): ask instead
        a.kind, a.text = "clarify", TEXTS[a.language]["no_previous"]
        return
    prompt = build_translate_prompt(message, previous)
    system = _system(TRANSLATE_SYSTEM, a, today)
    reply = _call(a, generate, prompt, system, TRANSLATE_SCHEMA, TRANSLATE_OUTPUT_TOKENS, log)
    if reply is None:
        return
    a.text = str(reply.get("translation") or "").strip()
    if not a.text:
        a.error = "empty reply"
        return
    a.language = language(a.text)  # the fixed lines ("Sources", the note) follow the translation
    a.translated_kind = previous.kind
    a.sources = list(previous.sources)
    a.covered = True if a.sources else None


def remembered(a: Answer) -> str:
    """What Natalia's reply leaves in the prompts' memory: its text, cut, and the headlines it
    cited, so a follow-up like "tell me more about the second one" can be understood."""
    text = a.text[:MEMORY_CHARS]
    if a.sources:
        text += " [sources: " + "; ".join(s.title for s in a.sources)[:SOURCES_CHARS] + "]"
    return text


def natalia_turn(a: Answer) -> Turn:
    """Natalia's reply as remembered: cut for the prompts, whole (with its sources) for
    "translate"."""
    kind = a.translated_kind if a.kind == "translate" else a.kind
    return Turn("natalia", remembered(a), full=a.text, kind=kind, sources=list(a.sources))


# --- rendering ------------------------------------------------------------------------------


def render(a: Answer, cap: int = DAILY_MESSAGES) -> str:
    """The reply as Telegram HTML: the answer, then the sources it used (headline as a link)."""
    t = TEXTS[a.language]
    if a.over_cap:
        return html.escape(t["cap"].format(cap=cap), quote=False)
    if a.error:
        return html.escape(t["failed"], quote=False)
    if not a.text:
        return html.escape(t["nothing"], quote=False)
    parts = [html.escape(a.text, quote=False)]
    if "general" in (a.kind, a.translated_kind):
        parts.append(f"<i>ℹ️ {html.escape(t['general'], quote=False)}</i>")
    if a.sources and a.covered:
        lines = [f"<b>{t['sources']}</b>"]
        for n, s in enumerate(a.sources, 1):
            when = s.published_at.astimezone(LOCAL_TZ).strftime("%d %b") if s.published_at else ""
            meta = " · ".join(x for x in (html.escape(s.source, quote=False), when) if x)
            lines.append(
                f'{n}. <a href="{html.escape(s.url)}">{html.escape(s.title, quote=False)}</a>'
                f" <i>({meta})</i>"
            )
        parts.append("\n".join(lines))
    return "\n\n".join(parts)


# --- command line ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("retrieve", help="(the bot's child process) question on stdin -> JSON")
    r.add_argument("-k", type=int, default=RETRIEVE_K)
    q = sub.add_parser("ask", help="send messages as the owner, in order (each counts)")
    q.add_argument("messages", nargs="+", help="one or more messages; later ones see earlier ones")
    q.add_argument("--dry-run", action="store_true", help="print the prompts only; no LLM")
    args = parser.parse_args(argv)

    if args.command == "retrieve":
        hits = retrieve_here(sys.stdin.read().strip()[:QUESTION_CHARS], k=args.k)
        print(json.dumps(hits))
        return 0

    from natalia.bot import config

    _, owner = config()
    memory, failed = Memory(), False
    with db.connect(autocommit=True) as conn:
        for message in args.messages:
            t0 = time.monotonic()
            a = answer(conn, message, owner, memory=memory, dry_run=args.dry_run)
            failed = failed or bool(a.error)
            print(f"\n> {message}\nkind={a.kind}, retrieved {len(a.retrieved)}: {a.retrieved}")
            if not args.dry_run:
                print(render(a))
                print(
                    f"covered={a.covered}, {len(a.sources)} sources, {a.requests} requests, "
                    f"{a.input_tokens} in + {a.output_tokens} out tokens, "
                    f"{time.monotonic() - t0:.1f} s"
                )
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
