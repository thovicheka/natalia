"""Filter by topic and pick the day's top stories (task 1.4). No LLM calls.

    uv run python -m natalia.topics tag                 # rule topics + language for recent articles
    uv run python -m natalia.topics tag --all           # ... for every stored article
    uv run python -m natalia.topics top                 # today's top 5 per topic (07:00 cut-off)
    uv run python -m natalia.topics top --now -v        # the 24 h before now, with score reasons

Tagging: every article keeps its feed's topic; keyword rules (RULES) add more, e.g. "cambodia" for
anything that names Cambodia, Phnom Penh, Hun Manet or កម្ពុជា. The topics the rules added are
kept in `rule_topics`, so changed rules can be re-run cleanly. The same pass sets `language` from
the headline's script (some "English" feeds carry Khmer items).

Top stories: the articles of one day (the 24 h before 07:00 Asia/Phnom_Penh) are grouped into
stories (the same news from several sites, by headline similarity), each story is scored, and the
best 5 per topic are kept. The score prefers stories that several sites cover, recent ones, and
ones with full text; it marks down items that are not news (deal posts, puzzle hints, analyst
ratings, listicles). Each story appears under one topic only: "general" (the day's headlines)
picks first, then every other topic in score order.
"""

from __future__ import annotations

import argparse
import math
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import psycopg

from natalia import db
from natalia.collect import GOOGLE_NEWS_HOST, site_of
from natalia.feeds import TOPICS

LOCAL_TZ = ZoneInfo("Asia/Phnom_Penh")
DIGEST_TIME = time(7, 0)  # the digest covers the 24 h before this, local time
WINDOW_HOURS = 24
PER_TOPIC = 5
MAX_PER_SITE = 2  # per topic, so one busy feed can't fill a topic
TAG_DAYS = 3  # `tag` without --all: articles collected this recently

# --- tagging --------------------------------------------------------------------------------

# Khmer place and leader names. Khmer has no spaces between words, so these match anywhere.
# ត/ដ: both spellings of the subscript are in use (សម្តេច / សម្ដេច).
_KM_CAMBODIA = (
    "កម្ពុជា|ខ្មែរ|ភ្នំពេញ|សៀមរាប|ព្រះសីហនុ|បាត់ដំបង|កំពង់ចាម|កំពង់ធំ|កំពង់ស្ពឺ|កំពង់ឆ្នាំង|"
    "កំពត|តាកែវ|ក្រចេះ|ស្ទឹងត្រែង|រតនគិរី|មណ្ឌលគិរី|ព្រះវិហារ|ឧត្តរមានជ័យ|បន្ទាយមានជ័យ|"
    "ពោធិ៍សាត់|កោះកុង|ស្វាយរៀង|ព្រៃវែង|ត្បូងឃ្មុំ|ប៉ៃលិន|អង្គរ|ហ៊ុន\\s*ម៉ាណែត|ហ៊ុន\\s*សែន|"
    "រាជរដ្ឋាភិបាល|សម្[តដ]េច"
)

# Each rule: (topic, pattern). English words match on word boundaries, case-insensitively,
# except the few that need case (AI, the Fed). Kept precise on purpose: a rule that fires on
# loose words ("war", "president") would put half the news under every topic.
RULES: list[tuple[str, re.Pattern]] = [
    (
        "cambodia",
        re.compile(
            r"\b(cambodian?s?|khmer|phnom penh|siem reap|sihanoukville|battambang|kampot|"
            r"angkor|hun manet|hun sen|tonle sap)\b|" + _KM_CAMBODIA,
            re.I,
        ),
    ),
    (
        "crypto",
        re.compile(
            r"\b(bitcoins?|btc|ethereum|ether|crypto|cryptocurrenc(y|ies)|cryptos|stablecoins?|"
            r"blockchains?|solana|xrp|dogecoin|binance|coinbase|tether|usdt|usdc|defi|nfts?|"
            r"memecoins?|web3|digital assets?)\b",
            re.I,
        ),
    ),
    (
        "markets",
        re.compile(
            r"\b(stock markets?|stocks|equities|s&p 500|nasdaq|dow jones|wall street|ftse|"
            r"nikkei 225|hang seng|stoxx|dax|bond yields?|treasury yields?|treasuries|forex|"
            r"oil prices?|gold prices?|brent crude|commodit(y|ies)|ipo|etfs?|hedge funds?|"
            r"investors|share prices?)\b",
            re.I,
        ),
    ),
    (
        "economics",
        re.compile(
            r"\b(inflation|gdp|central banks?|federal reserve|interest rates?|recession|"
            r"unemployment|jobs report|payrolls|tariffs?|trade war|trade deal|imf|world bank|"
            r"ecb|bank of england|bank of japan|consumer prices|economic growth|economy|"
            r"national debt)\b|\bthe Fed\b",
            re.I,
        ),
    ),
    (
        "technology",
        re.compile(
            r"\b(artificial intelligence|openai|chatgpt|nvidia|semiconductors?|chipmakers?|"
            r"smartphones?|iphone|android|cyberattacks?|cybersecurity|hackers?|data breach|"
            r"robotics|spacex|starlink|tsmc)\b",
            re.I,
        ),
    ),
    (
        "science",
        re.compile(
            r"\b(nasa|astronomers?|physicists?|telescope|asteroids?|genome|fossils?|"
            r"species|archaeolog\w*|space station|climate science)\b",
            re.I,
        ),
    ),
    (
        "sport",
        re.compile(
            r"\b(football|soccer|premier league|champions league|nba|nfl|mlb|nhl|tennis|"
            r"cricket|rugby|olympics?|world cup|formula 1|f1|golf|boxing|ufc|wimbledon|"
            r"grand prix|sea games)\b",
            re.I,
        ),
    ),
]
# Case-sensitive extras (as words): "AI" the abbreviation, not "ai" inside other words.
CASED_RULES: list[tuple[str, re.Pattern]] = [("technology", re.compile(r"\bAI\b"))]

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿"))


def clean_text(text: str | None) -> str:
    """NFC, no zero-width spaces (Khmer sites put them between words)."""
    return unicodedata.normalize("NFC", text or "").translate(_ZERO_WIDTH)


def _hits(pattern: re.Pattern, text: str) -> int:
    return sum(1 for _ in pattern.finditer(text))


def rule_topics(title: str, excerpt: str | None = None, body: str | None = None) -> set[str]:
    """Topics the keyword rules give an article.

    A topic counts when its words are in the headline, or at least twice in the excerpt.
    Cambodia is wider ("anything in or related to Cambodia", PLAN.md): once in the excerpt,
    or twice in the article text, is enough.
    """
    title, excerpt, body = clean_text(title), clean_text(excerpt), clean_text(body)
    found = set()
    for topic, pattern in RULES + CASED_RULES:
        if pattern.search(title):
            found.add(topic)
            continue
        in_excerpt = _hits(pattern, excerpt)
        if topic == "cambodia":
            if in_excerpt >= 1 or _hits(pattern, body[:20_000]) >= 2:
                found.add(topic)
        elif in_excerpt >= 2:
            found.add(topic)
    return found


def mentions_cambodia(title: str, excerpt: str | None = None, body: str | None = None) -> bool:
    return "cambodia" in rule_topics(title, excerpt, body)


def is_khmer(c: str) -> bool:
    return "ក" <= c <= "៿" or "᧠" <= c <= "᧿"


def detect_language(text: str) -> str | None:
    """'km' if most letters are Khmer, 'en' if most are Latin, None if there are too few."""
    letters = [c for c in clean_text(text) if c.isalpha() or unicodedata.category(c) == "Mn"]
    if len(letters) < 8:
        return None
    khmer = sum(is_khmer(c) for c in letters)
    return "km" if khmer / len(letters) >= 0.5 else "en"


@dataclass
class TagStats:
    articles: int = 0
    changed: int = 0
    added: Counter = field(default_factory=Counter)  # topic -> articles that gained it
    removed: Counter = field(default_factory=Counter)  # topic -> articles a rule no longer gives
    language_fixed: Counter = field(default_factory=Counter)  # "en->km" -> n
    examples: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))


def tag_articles(conn: psycopg.Connection, *, days: float | None = TAG_DAYS) -> TagStats:
    """Apply the rules (and the language check) to articles collected in the last `days` days,
    or to all articles when `days` is None. Idempotent: running it twice changes nothing."""
    stats = TagStats()
    where = "" if days is None else "WHERE collected_at >= now() - make_interval(secs => %s)"
    params = () if days is None else (days * 86400,)
    rows = conn.execute(
        "SELECT id, title, excerpt, body, language, topics::text[], rule_topics::text[]"
        " FROM articles " + where,
        params,
    ).fetchall()
    updates = []
    for art_id, title, excerpt, body, lang, topics, old_rule in rows:
        stats.articles += 1
        feed_topics = [t for t in topics if t not in old_rule]
        new_rule = sorted(rule_topics(title, excerpt, body) - set(feed_topics))
        new_topics = feed_topics + [t for t in TOPICS if t in new_rule]
        new_lang = detect_language(title) or lang
        if new_topics == list(topics) and new_rule == sorted(old_rule) and new_lang == lang:
            continue
        stats.changed += 1
        for t in set(new_rule) - set(old_rule):
            stats.added[t] += 1
            if len(stats.examples[t]) < 8:
                stats.examples[t].append(title)
        for t in set(old_rule) - set(new_rule):
            stats.removed[t] += 1
        if new_lang != lang:
            stats.language_fixed[f"{lang}->{new_lang}"] += 1
        updates.append((new_topics, new_rule, new_lang, art_id))
    with conn.transaction():
        for u in updates:
            conn.execute(
                "UPDATE articles SET topics = %s::topic[], rule_topics = %s::topic[],"
                " language = %s WHERE id = %s",
                u,
            )
    return stats


# --- stories --------------------------------------------------------------------------------

STOPWORDS = frozenset(
    """a an the and or but of to in on at for from by with as is are was were be been has have
    had it its this that these those after before over under into about amid against new says
    say said will would could can may might not no more most than up down out off what who why
    how when where which while his her their they he she we you our your us i s vs""".split()
)

# Not news, or low value for a digest: marked down, never deleted.
LOW_VALUE = [
    (re.compile(r"\b(wordle|connections|strands|crossword|sudoku|quiz|horoscope)\b", re.I), 4.0),
    (re.compile(r"\bobituary\b", re.I), 2.0),
    (re.compile(r"\b(deals?|discount|coupon|promo code|% off|on sale|best buy)\b", re.I), 3.0),
    (
        re.compile(
            r"\b(price target|reiterates|upgrades|downgrades|initiates coverage|"
            r"earnings call transcript|slides:|agm|stock rating|fair value)\b",
            re.I,
        ),
        3.0,
    ),
    (
        re.compile(r"(\branked!|\breview:|\bbest \w+ to (stream|watch|buy)\b|\bpodcast\b)", re.I),
        2.0,
    ),
    (re.compile(r"(\s[–-]\s?live$|\blive updates?\b|^live:|\bas it happened\b)", re.I), 1.0),
    # Guardian opinion pieces end in " | First Last".
    (re.compile(r"\s\|\s[A-Z][\w'’-]+(\s[A-Z][\w'’-]+){1,3}$"), 1.5),
]

SIMILAR_SHARE = 0.5  # see similar()
W_SITE = 2.5  # per extra site covering the story
MAX_EXTRA_SITES = 4
W_RECENT = 1.0  # a story published at the cut-off; 0 for one 24 h old
W_FULL_TEXT = 1.0
W_EXCERPT = 0.3
W_NOT_CAMBODIA = 4.0  # a Cambodian feed's item that doesn't mention Cambodia (world news in Khmer)


def article_site(url: str, title: str) -> str:
    """The site an article comes from. Google News links (stored before those feeds were
    disabled in 1.3) name the publisher only in the headline: "… - Reuters" -> "reuters"."""
    site = site_of(url)
    if site == GOOGLE_NEWS_HOST and " - " in title:
        return title.rsplit(" - ", 1)[1].strip().lower()
    return site


def title_tokens(title_norm: str) -> frozenset[str]:
    """Content words of a normalized headline, crudely singular ("tariffs" -> "tariff")."""
    out = set()
    for w in title_norm.split():
        if w in STOPWORDS or len(w) < 2:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.add(w)
    return frozenset(out)


@dataclass
class Article:
    id: int
    title: str
    title_norm: str
    url: str
    source: str
    paywalled: bool
    language: str
    topics: list[str]
    feed_topics: list[str]
    excerpt: str | None
    has_body: bool
    published_at: datetime
    also_seen: list[str]
    mentions_cambodia: bool = False

    @property
    def site(self) -> str:
        return article_site(self.url, self.title)


@dataclass
class Story:
    """One piece of news: the articles about it from one or more sites."""

    articles: list[Article]
    score: float = 0.0
    reasons: dict[str, float] = field(default_factory=dict)

    @property
    def lead(self) -> Article:
        """The article shown first: full text over excerpt, free over paywalled, then earliest."""
        return min(
            self.articles,
            key=lambda a: (not a.has_body, a.paywalled, not a.excerpt, a.published_at, a.id),
        )

    @property
    def sites(self) -> list[str]:
        found = {a.site for a in self.articles}
        for a in self.articles:
            found.update(a.also_seen)
        return sorted(found)

    @property
    def topics(self) -> list[str]:
        """The lead's topics, plus any most of the story's articles share. One article's topic
        isn't enough: a politics story Wired also covered isn't technology news."""
        n = len(self.articles)
        return [
            t
            for t in TOPICS
            if t in self.lead.topics or 2 * sum(t in a.topics for a in self.articles) > n
        ]

    @property
    def feed_topics(self) -> set[str]:
        return {t for a in self.articles for t in a.feed_topics}

    @property
    def published_at(self) -> datetime:
        return min(a.published_at for a in self.articles)


def token_weights(token_sets: Iterable[frozenset[str]]) -> dict[str, float]:
    """How telling each word is, from how many of the day's headlines use it (IDF): "trump" or
    "ukraine" are in dozens and say little; "albania" or "resign" say a lot."""
    sets = list(token_sets)
    df = Counter(t for s in sets for t in s)
    return {t: math.log(1 + len(sets) / n) for t, n in df.items()}


def similar(a: frozenset[str], b: frozenset[str], weights: dict[str, float] | None = None) -> bool:
    """Two headlines tell the same story: they share at least 3 content words, and the shared
    words carry at least half the weight of the shorter headline (`weights`: token_weights of
    the day; every word weighs 1 without it). Tuned on 2026-10-16's articles."""
    shared = a & b
    if len(shared) < 3:
        return False

    def weight(words):
        return sum(weights.get(w, 1.0) for w in words) if weights else float(len(words))

    return weight(shared) / min(weight(a), weight(b)) >= SIMILAR_SHARE


def same_news(a: Story, b: Story) -> bool:
    """A second, plainer check used when picking: some headline pairs of the two stories share
    4+ content words and half of the shorter one. It catches the day's biggest stories split
    in two, whose words are so common that day that similar() weighs them down."""
    for x in a.articles:
        tx = title_tokens(x.title_norm)
        for y in b.articles:
            ty = title_tokens(y.title_norm)
            shared = len(tx & ty)
            if shared >= 4 and shared / min(len(tx), len(ty)) >= 0.5:
                return True
    return False


def group_stories(articles: list[Article]) -> list[Story]:
    """Group articles from *different* sites whose headlines are similar to a headline already
    in the story. Articles go in publication order; each joins at most one story."""
    stories: list[Story] = []
    keys: list[list[frozenset[str]]] = []
    by_token: dict[str, list[int]] = defaultdict(list)
    ordered = sorted(articles, key=lambda a: (a.published_at, a.id))
    tokens = [title_tokens(a.title_norm) for a in ordered]
    weights = token_weights(tokens)
    for art, toks in zip(ordered, tokens, strict=True):
        placed = False
        if len(toks) >= 3:
            candidates = Counter(i for t in toks for i in set(by_token.get(t, ())))
            for idx, n in candidates.most_common():
                if n < 3:
                    break
                story = stories[idx]
                if art.site in {a.site for a in story.articles}:
                    continue
                if any(similar(toks, k, weights) for k in keys[idx]):
                    story.articles.append(art)
                    keys[idx].append(toks)
                    for t in toks:
                        by_token[t].append(idx)
                    placed = True
                    break
        if not placed:
            stories.append(Story([art]))
            keys.append([toks])
            for t in toks:
                by_token[t].append(len(stories) - 1)
    return stories


def score_story(story: Story, topic: str, end: datetime) -> tuple[float, dict[str, float]]:
    """The story's score under `topic`, and the parts it is made of (for -v and tests)."""
    lead = story.lead
    reasons: dict[str, float] = {}
    extra_sites = min(len(story.sites) - 1, MAX_EXTRA_SITES)
    if extra_sites:
        reasons["sites"] = W_SITE * extra_sites
    age_h = max(0.0, (end - story.published_at).total_seconds() / 3600)
    reasons["recent"] = round(W_RECENT * max(0.0, 1 - age_h / WINDOW_HOURS), 2)
    if any(a.has_body for a in story.articles):
        reasons["full text"] = W_FULL_TEXT
    elif any(a.excerpt for a in story.articles):
        reasons["excerpt"] = W_EXCERPT
    penalty = max((w for pat, w in LOW_VALUE if pat.search(lead.title)), default=0.0)
    if penalty:
        reasons["not news"] = -penalty
    if topic == "cambodia" and not any(a.mentions_cambodia for a in story.articles):
        reasons["no Cambodia mention"] = -W_NOT_CAMBODIA
    return round(sum(reasons.values()), 2), reasons


def day_window(day: date) -> tuple[datetime, datetime]:
    """The 24 h a day's digest covers: up to 07:00 Asia/Phnom_Penh on that day."""
    end = datetime.combine(day, DIGEST_TIME, LOCAL_TZ).astimezone(UTC)
    return end - timedelta(hours=WINDOW_HOURS), end


def load_window(conn: psycopg.Connection, start: datetime, end: datetime) -> list[Article]:
    """Articles published (or, without a date, collected) in [start, end). A publication date
    in the future (a few feeds do that) counts as the collection time."""
    rows = conn.execute(
        """SELECT a.id, a.title, a.title_norm, a.url, s.name, s.paywalled, a.language,
                  a.topics::text[], a.rule_topics::text[], a.excerpt, a.body IS NOT NULL,
                  LEAST(coalesce(a.published_at, a.collected_at), a.collected_at),
                  a.also_seen, left(a.body, 20000)
           FROM articles a JOIN sources s ON s.id = a.source_id
           WHERE LEAST(coalesce(a.published_at, a.collected_at), a.collected_at) >= %s
             AND LEAST(coalesce(a.published_at, a.collected_at), a.collected_at) < %s""",
        (start, end),
    ).fetchall()
    out = []
    for r in rows:
        title, excerpt, body = r[1], r[9], r[13]
        out.append(
            Article(
                id=r[0],
                title=title,
                title_norm=r[2],
                url=r[3],
                source=r[4],
                paywalled=r[5],
                language=r[6],
                topics=list(r[7]),
                feed_topics=[t for t in r[7] if t not in r[8]],
                excerpt=excerpt,
                has_body=r[10],
                published_at=r[11],
                also_seen=list(r[12]),
                mentions_cambodia=mentions_cambodia(title, excerpt, body),
            )
        )
    return out


def pick_top(
    stories: Iterable[Story],
    end: datetime,
    *,
    per_topic: int = PER_TOPIC,
    max_per_site: int = MAX_PER_SITE,
    first: str = "general",
) -> dict[str, list[Story]]:
    """The best `per_topic` stories per topic, each story under one topic only.

    `first` (the day's headlines) picks before the others; then all (story, topic) pairs go in
    score order; on equal scores a topic from the story's feeds beats one from the rules, then
    the topic listed first in PLAN.md. At most `max_per_site` stories per topic lead with the
    same site, and a story that is the same news as one already picked (same_news) is skipped.
    """
    pairs = []
    for story in stories:
        feed_topics = story.feed_topics
        for topic in story.topics:
            score, reasons = score_story(story, topic, end)
            key = (topic != first, -score, topic not in feed_topics, TOPICS.index(topic), id(story))
            pairs.append((key, topic, story, score, reasons))
    pairs.sort(key=lambda p: p[0])
    picked: dict[str, list[Story]] = {t: [] for t in TOPICS}
    used: set[int] = set()
    all_picked: list[Story] = []
    for _, topic, story, score, reasons in pairs:
        chosen = picked[topic]
        if id(story) in used or len(chosen) >= per_topic:
            continue
        if sum(s.lead.site == story.lead.site for s in chosen) >= max_per_site:
            continue
        if any(same_news(story, s) for s in all_picked):
            used.add(id(story))
            continue
        pick = Story(story.articles, score, reasons)
        chosen.append(pick)
        all_picked.append(pick)
        used.add(id(story))
    return picked


def top_stories(
    conn: psycopg.Connection, end: datetime, *, hours: float = WINDOW_HOURS, per_topic=PER_TOPIC
) -> tuple[dict[str, list[Story]], int, int]:
    """Top stories for the `hours` before `end`. Returns (picks, articles, stories)."""
    articles = load_window(conn, end - timedelta(hours=hours), end)
    stories = group_stories(articles)
    return pick_top(stories, end, per_topic=per_topic), len(articles), len(stories)


# --- command line -----------------------------------------------------------------------------


def _local(dt: datetime) -> str:
    return dt.astimezone(LOCAL_TZ).strftime("%m-%d %H:%M")


def print_top(picks: dict[str, list[Story]], verbose: bool = False) -> None:
    for topic in TOPICS:
        print(f"\n== {topic} ({len(picks[topic])})")
        for i, s in enumerate(picks[topic], 1):
            lead = s.lead
            text = "full" if lead.has_body else ("excerpt" if lead.excerpt else "headline")
            print(f"{i}. [{s.score:5.2f}] {lead.title[:100]}")
            print(
                f"   {lead.source} · {_local(s.published_at)} · {text} · "
                f"{len(s.sites)} site(s): {', '.join(s.sites[:6])}"
            )
            print(f"   {lead.url}")
            if verbose:
                print(f"   why: {s.reasons}")
                for other in s.articles:
                    if other is not lead:
                        print(f"   + {other.site}: {other.title[:90]}")


def print_tag_stats(stats: TagStats) -> None:
    print(f"articles checked: {stats.articles}, changed: {stats.changed}")
    for topic in TOPICS:
        if stats.added[topic] or stats.removed[topic]:
            print(f"  {topic:<15} +{stats.added[topic]:<5} -{stats.removed[topic]}")
    for change, n in stats.language_fixed.items():
        print(f"  language {change}: {n}")
    for topic, titles in stats.examples.items():
        print(f"\nadded {topic}, e.g.:")
        for t in titles:
            print(f"  {t[:110]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    tag = sub.add_parser("tag", help="apply the topic rules and the language check")
    tag.add_argument("--all", action="store_true", help="every article, not just recent ones")
    tag.add_argument("--days", type=float, default=TAG_DAYS)
    top = sub.add_parser("top", help="print the top stories per topic")
    top.add_argument("--date", type=date.fromisoformat, help="digest date (default: today)")
    top.add_argument("--now", action="store_true", help="the 24 h before now, not before 07:00")
    top.add_argument("-n", type=int, default=PER_TOPIC, help="stories per topic")
    top.add_argument("-v", "--verbose", action="store_true", help="show how each score is made")
    args = parser.parse_args(argv)

    try:
        conn = db.connect(autocommit=True)
    except (RuntimeError, psycopg.OperationalError) as e:
        print(f"cannot connect: {e}".strip())
        return 1
    with conn:
        if args.command == "tag":
            print_tag_stats(tag_articles(conn, days=None if args.all else args.days))
            return 0
        if args.now:
            end = datetime.now(UTC)
        else:
            end = day_window(args.date or datetime.now(LOCAL_TZ).date())[1]
        picks, n_articles, n_stories = top_stories(conn, end, per_topic=args.n)
    start = end - timedelta(hours=WINDOW_HOURS)
    print(
        f"window {_local(start)} → {_local(end)} Asia/Phnom_Penh: "
        f"{n_articles} articles, {n_stories} stories"
    )
    multi = sum(1 for t in picks.values() for s in t if len(s.sites) > 1)
    print(f"picked {sum(len(v) for v in picks.values())} stories, {multi} covered by 2+ sites")
    print_top(picks, args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
