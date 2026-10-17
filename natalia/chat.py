"""Plain-language chat (task 1.9b): Haiku answers the owner from stored articles, with sources.

    uv run python -m natalia.chat ask "What happened with rice exports?" --dry-run   # no LLM
    uv run python -m natalia.chat ask "What happened with rice exports?"             # ~$0.001
    echo "question" | uv run python -m natalia.chat retrieve                         # the child

How a question is answered:
1. **Cap**: at most DAILY_QUESTIONS per chat per day (Asia/Phnom_Penh). The question is counted
   before anything is sent, so a failing question still counts.
2. **Retrieve**, in a child process (`retrieve`): embed the question with the local e5 model and
   take the nearest stored articles of the last RETRIEVE_DAYS days (pgvector). The model takes
   ~300 MB; in a child it is freed as soon as the search is done, so the bot stays small. The
   question goes to the child on stdin, never on the command line (visible in `ps`).
3. **Answer**: one Haiku request with the articles (headline, source, date, the start of the
   text) and the question, asking for JSON: covered or not, the answer, the ids it used. The
   answer is in the question's language (Khmer if it's written in Khmer script, else English).
4. **Reply**: the answer, then the sources it used (headline as a link, source, date), taken
   from the database, so every link is a real stored article. Ids the LLM made up are dropped.

The question's text is not stored (`chat_questions` keeps counts and tokens only). It is sent to
the LLM provider (Anthropic) to be answered: that is the feature, and it's the owner's own text.
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime

import psycopg

from natalia import db, llm
from natalia.topics import LOCAL_TZ

DAILY_QUESTIONS = 20  # per chat per day; ~$0.001 each, so at most ~$0.02 a day
RETRIEVE_K = 8  # articles given to the LLM
RETRIEVE_DAYS = 30  # only articles from the last 30 days
MAX_DISTANCE = 0.25  # cosine distance; farther articles aren't related enough to send
TEXT_CHARS = 1200  # of each article's text sent to the LLM
MAX_OUTPUT_TOKENS = 2000  # thinking included
RETRIEVE_TIMEOUT_S = 120
QUESTION_CHARS = 1000  # a longer message is cut

SYSTEM = """You answer one reader's question about the news, using only the numbered news \
articles given with it. Rules:
- Use only facts from those articles. Never add facts from your own knowledge.
- If the articles don't answer the question, set "covered" to false and say in one or two \
sentences that the stored news doesn't cover it (you may name what the articles are about).
- Keep it short: 2 to 6 sentences, plain words, no headings, no lists unless they help.
- Don't put article numbers, ids or links in the answer text. List the ids of the articles you \
actually used in "source_ids", most important first.
- Write the answer in {language}.
Today is {today} (Asia/Phnom_Penh)."""

SCHEMA = {
    "type": "object",
    "properties": {
        "covered": {"type": "boolean"},
        "answer": {"type": "string"},
        "source_ids": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["covered", "answer", "source_ids"],
}

LANGUAGES = {"en": "English", "km": "Khmer (ភាសាខ្មែរ)"}
TEXTS = {
    "en": {
        "sources": "Sources",
        "cap": "That's {cap} questions today, the daily limit. Ask again tomorrow.",
        "failed": "Sorry, I couldn't answer just now. Please try again later.",
        "nothing": "I couldn't find anything about that in the stored news.",
    },
    "km": {
        "sources": "ប្រភព",
        "cap": "ថ្ងៃនេះអ្នកបានសួរ {cap} សំណួរហើយ ដែលជាចំនួនកំណត់ប្រចាំថ្ងៃ។ សូមសួរម្តងទៀតនៅថ្ងៃស្អែក។",
        "failed": "សូមអភ័យទោស ខ្ញុំមិនអាចឆ្លើយបានទេឥឡូវនេះ។ សូមព្យាយាមម្តងទៀតនៅពេលក្រោយ។",
        "nothing": "ខ្ញុំរកមិនឃើញព័ត៌មានអំពីរឿងនេះក្នុងព័ត៌មានដែលបានរក្សាទុកទេ។",
    },
}


class ChatError(RuntimeError):
    """Retrieval failed (the child process); the question can't be answered now."""


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
        """UPDATE chat_questions SET retrieved = %s, covered = %s, source_ids = %s, model = %s,
           requests = %s, input_tokens = %s, output_tokens = %s, error = %s WHERE id = %s""",
        (
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
    text: str = ""
    covered: bool | None = None
    sources: list[Source] = field(default_factory=list)  # the ones the answer used
    retrieved: list[int] = field(default_factory=list)
    model: str = ""
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    error: str = ""
    over_cap: bool = False


def load_sources(conn: psycopg.Connection, ids: list[int]) -> dict[int, Source]:
    rows = conn.execute(
        """SELECT a.id, a.title, a.url, s.name, coalesce(a.published_at, a.collected_at),
                  concat_ws(E'\\n', nullif(a.excerpt, ''), left(a.body, %s))
           FROM articles a JOIN sources s ON s.id = a.source_id WHERE a.id = ANY(%s)""",
        (TEXT_CHARS, ids),
    ).fetchall()
    return {r[0]: Source(*r) for r in rows}


def build_prompt(question: str, articles: list[Source]) -> str:
    blocks = []
    for a in articles:
        when = "?"
        if a.published_at:
            when = a.published_at.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")
        text = " ".join(a.text.split())[:TEXT_CHARS]
        blocks.append(f"[{a.id}] {a.title}\nSource: {a.source}, {when}\n{text}")
    return "Articles:\n\n" + "\n\n".join(blocks) + f"\n\nQuestion: {question}"


def answer(
    conn: psycopg.Connection,
    question: str,
    chat_id: int,
    *,
    retrieve=retrieve,
    generate=llm.generate,
    cap: int = DAILY_QUESTIONS,
    now: datetime | None = None,
    dry_run: bool = False,
    log=print,
) -> Answer:
    """Answer one question (see the module docstring). Never raises for a failed retrieval or
    LLM call: the Answer carries the error, and the bot says sorry."""
    question = question.strip()[:QUESTION_CHARS]
    lang = language(question)
    a = Answer(language=lang)
    if not dry_run:
        if asked_today(conn, chat_id, now) >= cap:
            a.over_cap = True
            return a
        qid = record_question(conn, chat_id, lang)
    try:
        hits = retrieve(question)
    except ChatError as e:
        a.error = str(e)
        log(f"chat: {e}")
    else:
        a.retrieved = [i for i, _ in hits]
        found = load_sources(conn, a.retrieved)
        articles = [found[i] for i in a.retrieved if i in found]
        if not articles:
            a.covered = False
        elif dry_run:
            log(build_prompt(question, articles))
        else:
            today = (now or datetime.now(LOCAL_TZ)).astimezone(LOCAL_TZ).date()
            _ask_llm(a, question, articles, today, generate, log)
    if not dry_run:
        record_answer(conn, qid, a)
    return a


def _ask_llm(a: Answer, question, articles: list[Source], today: date, generate, log) -> None:
    try:
        r = generate(
            build_prompt(question, articles),
            system=SYSTEM.format(language=LANGUAGES[a.language], today=today.isoformat()),
            json_schema=SCHEMA,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            purpose="chat",
        )
    except llm.LLMError as e:
        a.error = str(e)
        log(f"chat: {e}")
        return
    a.model, a.requests = r.model, r.requests
    a.input_tokens, a.output_tokens = r.input_tokens, r.output_tokens + r.thinking_tokens
    try:
        reply = json.loads(r.text)
        a.covered = bool(reply["covered"])
        a.text = str(reply["answer"]).strip()
        used = [int(i) for i in reply.get("source_ids", [])]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        a.error = f"reply isn't the JSON asked for (stop reason {r.stop_reason or '?'})"
        log(f"chat: {a.error}")
        return
    by_id = {s.id: s for s in articles}
    seen: set[int] = set()
    for i in used:
        if i in by_id and i not in seen:  # an id that wasn't sent is dropped, never linked
            seen.add(i)
            a.sources.append(by_id[i])


# --- rendering ------------------------------------------------------------------------------


def render(a: Answer, cap: int = DAILY_QUESTIONS) -> str:
    """The reply as Telegram HTML: the answer, then its sources (headline as a link)."""
    t = TEXTS[a.language]
    if a.over_cap:
        return html.escape(t["cap"].format(cap=cap), quote=False)
    if a.error:
        return html.escape(t["failed"], quote=False)
    if not a.text:
        return html.escape(t["nothing"], quote=False)
    parts = [html.escape(a.text, quote=False)]
    if a.sources:
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
    q = sub.add_parser("ask", help="answer one question as the owner (counts toward the cap)")
    q.add_argument("question")
    q.add_argument("--dry-run", action="store_true", help="retrieve and print the prompt only")
    args = parser.parse_args(argv)

    if args.command == "retrieve":
        hits = retrieve_here(sys.stdin.read().strip()[:QUESTION_CHARS], k=args.k)
        print(json.dumps(hits))
        return 0

    from natalia.bot import config

    _, owner = config()
    t0 = time.monotonic()
    with db.connect(autocommit=True) as conn:
        a = answer(conn, args.question, owner, dry_run=args.dry_run)
    print(f"\nretrieved {len(a.retrieved)} articles: {a.retrieved}")
    if not args.dry_run:
        print(render(a))
        print(
            f"\ncovered={a.covered}, {len(a.sources)} sources, {a.requests} requests, "
            f"{a.input_tokens} in + {a.output_tokens} out tokens, {time.monotonic() - t0:.1f} s"
        )
    return 0 if not a.error else 2


if __name__ == "__main__":
    raise SystemExit(main())
