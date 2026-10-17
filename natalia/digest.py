"""The daily digest: top stories + an AI summary and "why it matters" for each (task 1.7).

    uv run python -m natalia.digest build --dry-run         # show the requests, call nothing
    uv run python -m natalia.digest build                   # today's digest (calls the LLM)
    uv run python -m natalia.digest build --topics economics --max-requests 1
    uv run python -m natalia.digest show --date 2026-10-16  # print a stored digest (Markdown)

Build: pick the day's top stories (natalia.topics), then for each topic send ONE request with its
stories that have no summary yet (headline, source and text; news only, nothing private), asking
for JSON: a 2–3 sentence summary and 1–2 sentences on why it matters. Results go into `summaries`
(one per article and language, so a re-run reuses them and calls nothing), the picks into
`digests` / `digest_items` with the request and token counts. The summary always sits next to
the source: the headline, link and the feed's own detail are shown first.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import psycopg

from natalia import db, llm
from natalia.feeds import TOPICS
from natalia.topics import LOCAL_TZ, PER_TOPIC, Story, day_window, top_stories

ROOT = Path(__file__).resolve().parent.parent
DIGEST_DIR = ROOT / "docs" / "digests"
# Raw LLM replies that left a story without a summary, to see why (git-ignored, news only).
REPLY_DIR = ROOT / "logs" / "digest-replies"
TEXT_CHARS = 2500  # of an article's text sent to the LLM
DETAIL_CHARS = 320  # of the feed's detail shown under the headline
REQUEST_GAP_S = 13.0  # between requests: at most ~5 a minute, under the free tier's limit
MAX_REQUESTS = 12  # per build, retries included: 9 topics + a little room

TOPIC_NAMES = {
    "economics": "Economics",
    "world-politics": "World politics",
    "technology": "Technology",
    "science": "Science",
    "sport": "Sport",
    "crypto": "Crypto",
    "markets": "Stock market & trading",
    "cambodia": "Cambodia",
    "general": "Top stories",
}
# The digest shows the day's headlines first, then the topics in PLAN.md's order.
DIGEST_ORDER = ("general", *[t for t in TOPICS if t != "general"])

SYSTEM = """You write a short daily news digest for one reader.
For each article you get an id, its headline, source and text. For each one, write:
- summary: 2 to 3 sentences in plain English: what happened, with the key names, numbers and
  places from the text.
- why_it_matters: 1 to 2 sentences: the consequences or context, who is affected, or what to
  watch next.
Rules: use only facts stated in the given text; never invent numbers, quotes, dates or reactions.
If the text is only a short excerpt, keep the summary short and don't guess beyond it. Neutral
tone, no opinions, no hype, no markdown. Answer for every id, in JSON."""

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "summary": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                },
                "required": ["id", "summary", "why_it_matters"],
            },
        }
    },
    "required": ["items"],
}


@dataclass
class ArticleText:
    id: int
    title: str
    url: str
    source: str
    paywalled: bool
    published_at: datetime
    excerpt: str | None
    body: str | None
    sites: list[str] = field(default_factory=list)


@dataclass
class BuildReport:
    day: date
    model: str
    stories: int = 0
    reused: int = 0
    summarized: int = 0
    missing: list[int] = field(default_factory=list)
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    per_request: list[dict] = field(default_factory=list)


def _clip(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


def load_articles(conn: psycopg.Connection, ids: list[int]) -> dict[int, ArticleText]:
    rows = conn.execute(
        """SELECT a.id, a.title, a.url, s.name, s.paywalled, a.published_at, a.excerpt, a.body
           FROM articles a JOIN sources s ON s.id = a.source_id WHERE a.id = ANY(%s)""",
        (ids,),
    ).fetchall()
    return {r[0]: ArticleText(*r) for r in rows}


def existing_summaries(conn: psycopg.Connection, ids: list[int], language: str) -> set[int]:
    rows = conn.execute(
        "SELECT article_id FROM summaries WHERE article_id = ANY(%s) AND language = %s",
        (ids, language),
    ).fetchall()
    return {r[0] for r in rows}


def article_block(a: ArticleText) -> str:
    """One article as the LLM sees it: news content only."""
    text = a.body or a.excerpt or ""
    kind = "full text (start)" if a.body else ("excerpt only" if a.excerpt else "headline only")
    return (
        f"id: {a.id}\nheadline: {a.title}\nsource: {a.source}\n"
        f"published: {a.published_at:%Y-%m-%d}\ntext ({kind}): {_clip(text, TEXT_CHARS)}"
    )


def build_prompt(articles: list[ArticleText]) -> str:
    return "Articles:\n\n" + "\n\n---\n\n".join(article_block(a) for a in articles)


def parse_reply(text: str, wanted: set[int]) -> dict[int, tuple[str, str]]:
    """{article id: (summary, why it matters)} for the wanted ids found in the JSON reply."""
    data = json.loads(text)
    out = {}
    for item in data.get("items", []):
        try:
            art_id = int(item["id"])
        except (KeyError, TypeError, ValueError):
            continue
        summary = " ".join(str(item.get("summary", "")).split())
        why = " ".join(str(item.get("why_it_matters", "")).split())
        if art_id in wanted and summary and why:
            out[art_id] = (summary, why)
    return out


def save_reply(day: date, topic: str, r: llm.Result, sent: list[int], missing: list[int]):
    """Write the raw reply of a request that left stories without a summary to REPLY_DIR, with
    the ids sent and missing and why the model stopped. Returns the path, or None on failure."""
    now = datetime.now().astimezone()
    path = REPLY_DIR / f"{day}-{topic}-{now:%H%M%S}.json"
    entry = {
        "at": now.isoformat(timespec="seconds"),
        "day": str(day),
        "topic": topic,
        "model": r.model,
        "stop_reason": r.stop_reason,
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
        "sent_ids": sent,
        "missing_ids": missing,
        "reply": r.text,
    }
    try:
        REPLY_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entry, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    except OSError:
        return None  # a diagnostic must never break a digest
    return path


def store_summaries(conn, results: dict[int, tuple[str, str]], language: str, model: str) -> None:
    with conn.transaction():
        for art_id, (summary, why) in results.items():
            conn.execute(
                """INSERT INTO summaries (article_id, language, summary, why_it_matters, model)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (article_id, language) DO UPDATE SET summary = EXCLUDED.summary,
                       why_it_matters = EXCLUDED.why_it_matters, model = EXCLUDED.model,
                       created_at = now()""",
                (art_id, language, summary, why, model),
            )


def store_digest(
    conn, day: date, language: str, picks: dict[str, list[Story]], report: BuildReport
) -> int:
    """Create or replace the day's digest; requests and tokens add up across re-runs."""
    with conn.transaction():
        digest_id = conn.execute(
            """INSERT INTO digests (digest_date, language, model, requests, input_tokens,
                                    output_tokens)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (digest_date, language) DO UPDATE SET model = EXCLUDED.model,
                   requests = digests.requests + EXCLUDED.requests,
                   input_tokens = digests.input_tokens + EXCLUDED.input_tokens,
                   output_tokens = digests.output_tokens + EXCLUDED.output_tokens
               RETURNING id""",
            (
                day,
                language,
                report.model,
                report.requests,
                report.input_tokens,
                report.output_tokens,
            ),
        ).fetchone()[0]
        conn.execute("DELETE FROM digest_items WHERE digest_id = %s", (digest_id,))
        for topic, stories in picks.items():
            for pos, story in enumerate(stories, 1):
                conn.execute(
                    """INSERT INTO digest_items (digest_id, topic, position, article_id)
                       VALUES (%s, %s, %s, %s)""",
                    (digest_id, topic, pos, story.lead.id),
                )
    return digest_id


def build(
    conn: psycopg.Connection,
    day: date,
    *,
    language: str = "en",
    topics: list[str] | None = None,
    per_topic: int = PER_TOPIC,
    max_requests: int = MAX_REQUESTS,
    gap_s: float = REQUEST_GAP_S,
    dry_run: bool = False,
    no_llm: bool = False,
    model: str | None = None,
    log=print,
    sleep=time.sleep,
) -> BuildReport:
    """Pick the day's stories, summarize those without a summary (one request per topic), store
    everything. A failed topic is logged and skipped; its stories are listed in `missing`.
    `no_llm`: store the picks only (a later build adds the summaries). `model`: default, the
    LLM provider's pinned model (natalia.llm, LLM_PROVIDER)."""
    model = model or llm.default_model()
    end = day_window(day)[1]
    picks, _, _ = top_stories(conn, end, per_topic=per_topic)
    if topics:
        picks = {t: (s if t in topics else []) for t, s in picks.items()}
    report = BuildReport(day=day, model=model)
    lead_ids = [s.lead.id for stories in picks.values() for s in stories]
    report.stories = len(lead_ids)
    done = existing_summaries(conn, lead_ids, language)
    report.reused = len(done)
    articles = load_articles(conn, lead_ids)
    llm.set_max_calls(max_requests)
    requests_before = llm.usage.requests
    first = True
    for topic in DIGEST_ORDER:
        todo = [articles[s.lead.id] for s in picks[topic] if s.lead.id not in done]
        if not todo:
            continue
        if no_llm:
            report.missing += [a.id for a in todo]
            continue
        prompt = build_prompt(todo)
        if dry_run:
            log(f"[dry run] {topic}: {len(todo)} stories, ~{len(prompt) // 4} input tokens")
            report.requests += 1
            continue
        if not first:
            sleep(gap_s)
        first = False
        try:
            r = llm.generate(
                prompt,
                system=SYSTEM,
                json_schema=SCHEMA,
                model=model,
                purpose=f"digest {day} {topic}",
            )
        except llm.LLMError as e:
            log(f"{topic}: failed: {e}")
            report.missing += [a.id for a in todo]
            if "cap reached" in str(e):
                break
            continue
        report.model = r.model
        report.input_tokens += r.input_tokens
        report.output_tokens += r.output_tokens + r.thinking_tokens
        report.per_request.append(
            {"topic": topic, "stories": len(todo), "in": r.input_tokens, "out": r.output_tokens}
        )
        try:
            results = parse_reply(r.text, {a.id for a in todo})
        except json.JSONDecodeError:
            results = {}
        store_summaries(conn, results, language, r.model)
        report.summarized += len(results)
        missing = [a.id for a in todo if a.id not in results]
        report.missing += missing
        log(
            f"{topic}: {len(results)}/{len(todo)} summarized, "
            f"{r.input_tokens} in / {r.output_tokens} out tokens"
        )
        if missing:
            saved = save_reply(day, topic, r, [a.id for a in todo], missing)
            if saved:
                log(f"{topic}: missing {missing}, raw reply saved to {saved}")
    if not dry_run:
        report.requests = llm.usage.requests - requests_before  # failed requests count too
        store_digest(conn, day, language, picks, report)
    return report


# --- reading a stored digest ----------------------------------------------------------------


@dataclass
class DigestItem:
    topic: str
    position: int
    article: ArticleText
    summary: str | None
    why_it_matters: str | None


@dataclass
class Digest:
    day: date
    language: str
    model: str | None
    requests: int
    input_tokens: int
    output_tokens: int
    items: list[DigestItem]

    def by_topic(self) -> dict[str, list[DigestItem]]:
        out: dict[str, list[DigestItem]] = {t: [] for t in DIGEST_ORDER}
        for it in self.items:
            out[it.topic].append(it)
        return out


def load_digest(conn: psycopg.Connection, day: date, language: str = "en") -> Digest | None:
    row = conn.execute(
        """SELECT id, model, requests, input_tokens, output_tokens FROM digests
           WHERE digest_date = %s AND language = %s""",
        (day, language),
    ).fetchone()
    if not row:
        return None
    items = conn.execute(
        """SELECT di.topic::text, di.position, di.article_id, s.summary, s.why_it_matters
           FROM digest_items di
           LEFT JOIN summaries s ON s.article_id = di.article_id AND s.language = %s
           WHERE di.digest_id = %s ORDER BY di.topic, di.position""",
        (language, row[0]),
    ).fetchall()
    articles = load_articles(conn, [i[2] for i in items])
    return Digest(
        day,
        language,
        row[1],
        row[2],
        row[3],
        row[4],
        [DigestItem(t, pos, articles[aid], s, w) for t, pos, aid, s, w in items],
    )


def detail(a: ArticleText) -> str:
    """The source's own words shown under the headline: the feed's excerpt, else the text."""
    return _clip(a.excerpt or a.body or "", DETAIL_CHARS)


def to_markdown(d: Digest) -> str:
    done = sum(1 for it in d.items if it.summary)
    if done:
        llm_note = (
            f"Summaries by {d.model} for {done} of {len(d.items)} stories ({d.requests} requests, "
            f"{d.input_tokens:,} input + {d.output_tokens:,} output tokens)."
        )
    else:
        llm_note = f"Summaries pending: none generated yet for these {len(d.items)} stories."
    lines = [
        f"# Natalia daily digest — {d.day:%A %d %B %Y}",
        "",
        f"News from the 24 hours before 07:00 Asia/Phnom_Penh. {llm_note} Each summary sits "
        "under the source's own headline, link and text; read the source to check it.",
    ]
    for topic, items in d.by_topic().items():
        if not items:
            continue
        lines += ["", f"## {TOPIC_NAMES[topic]}", ""]
        for it in items:
            a = it.article
            when = a.published_at.astimezone(LOCAL_TZ).strftime("%d %b %H:%M")
            pay = " · paywalled: headline and excerpt only" if a.paywalled else ""
            lines += [f"### {it.position}. [{a.title}]({a.url})", f"*{a.source} · {when}{pay}*", ""]
            if detail(a):
                lines += [f"> {detail(a)}", ""]
            if it.summary:
                lines += [
                    f"**Summary:** {it.summary}",
                    "",
                    f"**Why it matters:** {it.why_it_matters}",
                ]
            else:
                lines += ["*(summary pending: not generated yet)*"]
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="pick, summarize and store a day's digest")
    b.add_argument("--date", type=date.fromisoformat)
    b.add_argument("--topics", help="comma-separated topics (default: all)")
    b.add_argument("--max-requests", type=int, default=MAX_REQUESTS)
    b.add_argument("--dry-run", action="store_true", help="show the requests, send nothing")
    b.add_argument("--no-llm", action="store_true", help="store the picks without summaries")
    b.add_argument("--model", help="LLM model (default: the LLM_PROVIDER's pinned model)")
    s = sub.add_parser("show", help="print a stored digest as Markdown")
    s.add_argument("--date", type=date.fromisoformat)
    s.add_argument("--save", action="store_true", help=f"also write it to {DIGEST_DIR}/")
    args = parser.parse_args(argv)
    day = args.date or datetime.now(LOCAL_TZ).date()

    try:
        conn = db.connect(autocommit=True)
    except (RuntimeError, psycopg.OperationalError) as e:
        print(f"cannot connect: {e}".strip())
        return 1
    with conn:
        if args.command == "build":
            topics = args.topics.split(",") if args.topics else None
            t0 = time.monotonic()
            r = build(
                conn,
                day,
                topics=topics,
                max_requests=args.max_requests,
                dry_run=args.dry_run,
                no_llm=args.no_llm,
                model=args.model,
            )
            print(
                f"\ndigest {day}: {r.stories} stories, {r.reused} summaries reused, "
                f"{r.summarized} new, {len(r.missing)} missing; {r.requests} requests, "
                f"{r.input_tokens} input + {r.output_tokens} output tokens, "
                f"{time.monotonic() - t0:.0f} s"
            )
            return 0 if not r.missing else 2
        d = load_digest(conn, day)
    if not d:
        print(f"no digest stored for {day}")
        return 1
    md = to_markdown(d)
    print(md)
    if args.save:
        DIGEST_DIR.mkdir(parents=True, exist_ok=True)
        (DIGEST_DIR / f"{day}.md").write_text(md, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
