"""Collect and clean: feeds -> articles in PostgreSQL (task 1.3).

    uv run python -m natalia.collect                 # load sources, fetch every enabled feed, store
    uv run python -m natalia.collect --no-text       # feeds only: store excerpts, fetch no pages
    uv run python -m natalia.collect --feed BBC      # only feeds whose name contains "BBC"

Steps: load config/sources.yaml into `sources`; read each enabled feed with feedparser; drop
entries older than --max-age-hours; drop duplicates (canonical URL, then near-identical
headline, against the database and within the run); extract the article text with trafilatura
where that is allowed; store the rest in `articles`. Running it again stores nothing twice.

Full text is fetched only when all of these hold; otherwise the article keeps the feed's
headline + excerpt + link:
- the source is not paywalled (config/sources.yaml) and the link's site is not on
  EXCERPT_ONLY_DOMAINS (Reuters and AP block readers; the rest are paywalled);
- the link is not a Google News redirect (news.google.com's robots.txt disallows following it);
- the site's robots.txt allows the page for our user agent;
- the page is HTML, has no "isAccessibleForFree: false" paywall marker, and yields enough text.

Polite: one user agent that names the project, timeouts, a size cap, at most WORKERS sites at
once, one request at a time per site with a delay between them (longer if robots.txt asks), and
a site that refuses or times out MAX_REFUSALS times is not asked again in the same run.
"""

from __future__ import annotations

import argparse
import base64
import calendar
import difflib
import html
import re
import resource
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import urllib.robotparser
from collections import Counter, defaultdict
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import feedparser
import psycopg

from natalia import db
from natalia.feeds import SOURCES_FILE, TOPICS, USER_AGENT, Source, load_sources

ROBOTS_AGENT = "natalia"  # the token robots.txt rules are matched against
TIMEOUT_S = 15
MAX_BYTES = 3_000_000
WORKERS = 4  # sites fetched at once
HOST_DELAY_S = 1.0  # between two requests to the same site
MAX_CRAWL_DELAY_S = 30.0  # a site asking for more gets no full-text fetches this run
MAX_REDIRECTS = 5
MAX_REFUSALS = 2  # refusals or timeouts from one site before we stop asking it this run
REFUSAL_STATUSES = (401, 403, 405, 429)
MAX_AGE_HOURS = 48
TITLE_WINDOW_DAYS = 3  # headlines compared against articles collected this recently
NEAR_DUP_RATIO = 0.9
NEAR_DUP_MIN_TOKENS = 5  # shorter (or unspaced, e.g. Khmer) headlines: exact match only
MIN_BODY_CHARS = 300  # less than this is a teaser, cookie wall or paywall, not an article
MAX_BODY_CHARS = 100_000
MAX_EXCERPT_CHARS = 1_000

# Sites whose links stay headline + excerpt + link, whatever feed they arrive through:
# Reuters and AP refuse plain clients; the others are paywalled (see config/sources.yaml).
EXCERPT_ONLY_DOMAINS = (
    "reuters.com",
    "apnews.com",
    "bloomberg.com",
    "ft.com",
    "wsj.com",
    "nytimes.com",
    "economist.com",
    "marketwatch.com",
    "barrons.com",
    "nikkei.com",
    "foreignaffairs.com",
    "wired.com",
    "technologyreview.com",
    "nature.com",
    "scientificamerican.com",
    "newscientist.com",
    "washingtonpost.com",
)

GOOGLE_NEWS_HOST = "news.google.com"
# Query parameters that only track the click; dropped from canonical URLs.
TRACKING_PARAMS = re.compile(
    r"^(utm_.*|fbclid|gclid|mc_cid|mc_eid|cmpid|cmp|ocid|ito|at_.*|rss|ref|src|oc|"
    r"guccounter|_ga|xtor|sr_share|taid)$",
    re.I,
)
# Not news: stock-quote pages that Reuters' Google News search returns ("3ZV.MU - Reuters",
# "(ORK.HA) | Stock Price & Latest News - Reuters"). Matched after the " - Publisher" suffix.
JUNK_TITLE = re.compile(
    r"^\(?[A-Z0-9]{1,6}(\.[A-Z]{1,4})?\)?(\s*-?\s*\|?\s*Stock Price (&|and) Latest News)?\s*-?$"
)
PAYWALL_MARKER = re.compile(rb'"isAccessibleForFree"\s*:\s*"?false', re.I)


# --- cleaning: URLs, titles, excerpts -----------------------------------------------------


def canonical_url(url: str) -> str:
    """One spelling per page: lowercase host, no fragment, no tracking parameters, sorted
    query, no trailing slash, https. Google News links keep only their article id."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    path = re.sub(r"/{2,}", "/", parts.path) or "/"
    if len(path) > 1:
        path = path.rstrip("/")
    query = sorted((k, v) for k, v in parse_qsl(parts.query) if not TRACKING_PARAMS.match(k))
    return urlunsplit(("https", host, path, urlencode(query), ""))


def decode_google_news(url: str) -> str | None:
    """The publisher's URL inside an old-style Google News article id, or None.

    Old ids are base64 protobufs that carry the URL. Newer ids ("AU_yqL…") are opaque and need
    a request to news.google.com, which its robots.txt disallows, so those stay unresolved.
    """
    parts = urlsplit(url)
    if parts.hostname != GOOGLE_NEWS_HOST or "/articles/" not in parts.path:
        return None
    article_id = parts.path.rsplit("/", 1)[-1]
    try:
        raw = base64.urlsafe_b64decode(article_id + "=" * (-len(article_id) % 4))
    except ValueError:
        return None
    m = re.search(rb"https?://[\x21-\x7e]+", raw)
    if not m:
        return None
    found = m.group(0).decode("ascii")
    # A trailing protobuf field can follow the URL; it starts with a control byte, which the
    # character class above already stops at, or with "\xd2\x01" + a second (AMP) URL.
    return found if urlsplit(found).hostname else None


def _strip_marks(text: str) -> str:
    """Keep letters, numbers and combining marks (Khmer vowels are marks); the rest -> space."""
    return "".join(
        ch if unicodedata.category(ch)[0] in "LNM" else " "
        for ch in unicodedata.normalize("NFKC", text)
    )


def normalize_title(title: str, publisher: str = "") -> str:
    """Lowercase, no punctuation, single spaces; drops a trailing " - Publisher" suffix."""
    title = html.unescape(title).strip()
    if publisher:
        for sep in (" - ", " | ", " — ", " – "):
            if title.endswith(sep + publisher):
                title = title[: -len(sep + publisher)]
                break
    return " ".join(_strip_marks(title).casefold().split())


def is_junk_title(title: str, publisher: str = "") -> bool:
    """True for headlines that are not news (stock-quote pages)."""
    title = html.unescape(title).strip()
    if publisher and title.endswith(" - " + publisher):
        title = title[: -len(" - " + publisher)]
    return bool(JUNK_TITLE.match(title.strip()))


def clean_excerpt(summary: str, title: str) -> str | None:
    """Feed summary as plain text, or None when it only repeats the headline (Google News)."""
    if not summary:
        return None
    text = re.sub(r"<[^>]+>", " ", summary)
    text = " ".join(html.unescape(text).split())
    if not text:
        return None
    rest = normalize_title(text).removeprefix(normalize_title(title)).strip()
    if len(rest) < 40:
        return None
    if len(text) > MAX_EXCERPT_CHARS:
        text = text[:MAX_EXCERPT_CHARS].rsplit(" ", 1)[0] + "…"
    return text


def domain_matches(host: str, domains: Iterable[str]) -> bool:
    host = host.lower()
    return any(host == d or host.endswith("." + d) for d in domains)


class TitleIndex:
    """Normalized headlines seen so far, for exact and near-identical matching."""

    def __init__(self, titles: Iterable[str] = ()):
        self._exact: set[str] = set()
        self._by_token: dict[str, list[int]] = defaultdict(list)
        self._titles: list[str] = []
        for t in titles:
            self.add(t)

    def add(self, norm: str) -> None:
        if not norm or norm in self._exact:
            return
        self._exact.add(norm)
        tokens = set(norm.split())
        if len(tokens) >= NEAR_DUP_MIN_TOKENS:
            idx = len(self._titles)
            self._titles.append(norm)
            for tok in tokens:
                self._by_token[tok].append(idx)

    def match(self, norm: str) -> str | None:
        """The stored headline this one duplicates, or None."""
        if norm in self._exact:
            return norm
        tokens = set(norm.split())
        if len(tokens) < NEAR_DUP_MIN_TOKENS:
            return None
        shared = Counter(i for tok in tokens for i in self._by_token.get(tok, ()))
        for idx, n in shared.most_common(20):
            if n < 0.6 * len(tokens):
                break
            other = self._titles[idx]
            if difflib.SequenceMatcher(None, norm, other).ratio() >= NEAR_DUP_RATIO:
                return other
        return None


# --- polite fetching ----------------------------------------------------------------------


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # follow redirects by hand (robots per hop)
        return None


_opener = urllib.request.build_opener(_NoRedirect)


@dataclass
class Response:
    status: int
    url: str
    body: bytes = b""
    content_type: str = ""
    location: str = ""


class Blocked(Exception):
    """robots.txt (or its crawl delay) says no."""


class SiteRefused(Exception):
    """The site refused (401/403/405/429) or timed out MAX_REFUSALS times this run."""


class Fetcher:
    """GETs with one user agent, timeouts, robots.txt, and one request at a time per site."""

    def __init__(self, delay: float = HOST_DELAY_S, timeout: float = TIMEOUT_S):
        self.delay = delay
        self.timeout = timeout
        self.requests = 0
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._guard = threading.Lock()
        self._last: dict[str, float] = {}
        self._refusals: Counter = Counter()

    def _host_lock(self, host: str) -> threading.Lock:
        with self._guard:
            return self._locks[host]

    def _raw_get(self, url: str, host: str, delay: float) -> Response:
        """One GET, waiting until `delay` has passed since the last request to `host`."""
        with self._host_lock(host):
            wait = self._last.get(host, 0.0) + delay - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            req = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en,km;q=0.8"}
            )
            try:
                self.requests += 1
                with _opener.open(req, timeout=self.timeout) as resp:
                    return Response(
                        resp.status,
                        url,
                        resp.read(MAX_BYTES),
                        resp.headers.get("Content-Type", ""),
                    )
            except urllib.error.HTTPError as e:  # 3xx land here too (no auto-redirects)
                location = e.headers.get("Location", "") if e.headers else ""
                return Response(e.code, url, location=location)
            finally:
                self._last[host] = time.monotonic()

    def robots(self, scheme: str, host: str) -> urllib.robotparser.RobotFileParser | None:
        """The site's robots.txt, fetched once per run. None means "no rules" (404)."""
        key = f"{scheme}://{host}"
        with self._host_lock("robots:" + key):
            if key in self._robots:
                return self._robots[key]
            rp = urllib.robotparser.RobotFileParser(key + "/robots.txt")
            try:
                resp = self.get(key + "/robots.txt", obey_robots=False)
                status = resp.status
            except Exception:
                status = 0
            if status == 200:
                rp.parse(resp.body.decode("utf-8", "replace").splitlines())
            elif status in (401, 403) or status == 0 or status >= 500 or 300 <= status < 400:
                rp.disallow_all = True  # unreachable, refused, or redirect loop: assume no
            else:
                rp = None  # 404 and other 4xx: no robots.txt, everything allowed
            self._robots[key] = rp
            return rp

    def get(self, url: str, *, obey_robots: bool = True) -> Response:
        """GET, following redirects by hand so each hop's robots.txt is checked. Raises
        Blocked when robots.txt disallows a hop, SiteRefused when the site has already refused
        us MAX_REFUSALS times this run; network errors propagate."""
        for _ in range(MAX_REDIRECTS + 1):
            parts = urlsplit(url)
            host = parts.hostname or ""
            delay = self.delay
            if obey_robots:
                if self._refusals[host] >= MAX_REFUSALS:
                    raise SiteRefused(host)
                rp = self.robots(parts.scheme, host)
                if rp is not None and not rp.can_fetch(ROBOTS_AGENT, url):
                    raise Blocked(f"robots.txt disallows {host}{parts.path[:60]}")
                crawl_delay = float(rp.crawl_delay(ROBOTS_AGENT) or 0) if rp else 0.0
                if crawl_delay > MAX_CRAWL_DELAY_S:
                    raise Blocked(f"{host} asks for a {crawl_delay:.0f}s crawl delay")
                delay = max(delay, crawl_delay)
            try:
                resp = self._raw_get(url, host, delay)
            except OSError:  # timeouts, resets, DNS: count like a refusal
                self._refusals[host] += 1
                raise
            if resp.status in REFUSAL_STATUSES:
                self._refusals[host] += 1
            if resp.status in (301, 302, 303, 307, 308) and resp.location:
                url = urljoin(url, resp.location)
                continue
            return resp
        raise urllib.error.URLError(f"more than {MAX_REDIRECTS} redirects")


# --- one feed -----------------------------------------------------------------------------


@dataclass
class Item:
    """A feed entry, cleaned, before it is stored."""

    source: Source
    source_id: int
    url: str
    link: str  # where the text would be fetched from (the publisher's URL when known)
    title: str
    title_norm: str
    excerpt: str | None
    published_at: datetime | None
    publisher_host: str
    topics: list[str] = field(default_factory=list)
    body: str | None = None
    text_status: str = ""  # "full" or why it is excerpt-only


@dataclass
class TopicStats:
    feeds: int = 0
    feeds_failed: int = 0
    entries: int = 0
    too_old: int = 0
    dup_url: int = 0
    dup_title: int = 0
    stored: int = 0
    full_text: int = 0
    excerpt_only: int = 0


@dataclass
class RunStats:
    topics: dict[str, TopicStats] = field(default_factory=lambda: {t: TopicStats() for t in TOPICS})
    excerpt_reasons: Counter = field(default_factory=Counter)
    feed_errors: list[str] = field(default_factory=list)
    dup_examples: list[tuple[str, str]] = field(default_factory=list)
    junk: int = 0  # entries dropped as not news (see JUNK_TITLE)
    gn_items: int = 0
    gn_resolved: int = 0
    topics_merged: int = 0


def _entry_time(entry) -> datetime | None:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime.fromtimestamp(calendar.timegm(t), UTC) if t else None


def parse_feed(body: bytes, src: Source, source_id: int, stats: RunStats) -> list[Item]:
    """Feed bytes -> cleaned items (no age or duplicate filtering yet)."""
    items = []
    for entry in feedparser.parse(body).entries:
        title = " ".join(html.unescape(entry.get("title", "")).split())
        link = entry.get("link", "").strip()
        if not title or not link.startswith(("http://", "https://")):
            continue
        publisher = ""
        if entry.get("source"):
            publisher = (entry.source.get("title") or "").strip()
        if is_junk_title(title, publisher):
            stats.junk += 1
            continue
        url, fetch_from = canonical_url(link), link
        if urlsplit(link).hostname == GOOGLE_NEWS_HOST:
            stats.gn_items += 1
            real = decode_google_news(link)
            if real:
                stats.gn_resolved += 1
                url, fetch_from = canonical_url(real), real
        host = urlsplit(fetch_from).hostname or ""
        if host == GOOGLE_NEWS_HOST and entry.get("source"):
            host = urlsplit(entry.source.get("href", "")).hostname or host
        items.append(
            Item(
                source=src,
                source_id=source_id,
                url=url,
                link=fetch_from,
                title=title,
                title_norm=normalize_title(title, publisher),
                excerpt=clean_excerpt(entry.get("summary", ""), title),
                published_at=_entry_time(entry),
                publisher_host=host,
                topics=[src.topic],
            )
        )
    return items


def excerpt_only_reason(item: Item) -> str | None:
    """Why this item must not have its page fetched, or None if it may."""
    if item.source.paywalled:
        return "paywalled source"
    if urlsplit(item.link).hostname == GOOGLE_NEWS_HOST:
        return "Google News link (not followed: robots.txt)"
    if domain_matches(item.publisher_host, EXCERPT_ONLY_DOMAINS):
        return "blocked or paywalled site"
    return None


def extract_text(fetcher: Fetcher, item: Item) -> None:
    """Fill item.body with the article text, or set item.text_status to why not. Never raises."""
    import trafilatura  # loaded on first use: lxml and friends cost ~40 MB

    reason = excerpt_only_reason(item)
    if reason:
        item.text_status = reason
        return
    try:
        resp = fetcher.get(item.link)
    except Blocked:
        item.text_status = "robots.txt disallows"
        return
    except SiteRefused:
        item.text_status = "site refused earlier requests (not asked again)"
        return
    except Exception as e:
        item.text_status = f"fetch failed ({type(e).__name__})"
        return
    if resp.status != 200:
        item.text_status = f"HTTP {resp.status}"
        return
    if "html" not in resp.content_type.lower():
        item.text_status = "not HTML"
        return
    if PAYWALL_MARKER.search(resp.body):
        item.text_status = "paywall marker on page"
        return
    try:
        text = trafilatura.extract(
            resp.body,
            url=resp.url,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
            deduplicate=True,
        )
    except Exception as e:
        item.text_status = f"extraction failed ({type(e).__name__})"
        return
    if not text or len(text) < MIN_BODY_CHARS:
        item.text_status = "too little text on page"
        return
    item.body = text[:MAX_BODY_CHARS]
    item.text_status = "full"


# --- database -----------------------------------------------------------------------------


def sync_sources(conn: psycopg.Connection, sources: list[Source]) -> dict[str, int]:
    """Upsert config/sources.yaml into `sources` (matched by feed URL). Feeds no longer in the
    file are disabled, not deleted (articles point to them). Returns {feed URL: id}."""
    with conn.transaction():
        for s in sources:
            conn.execute(
                """INSERT INTO sources (name, topic, feed_url, language, paywalled, enabled)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (feed_url) DO UPDATE SET
                       name = EXCLUDED.name, topic = EXCLUDED.topic,
                       language = EXCLUDED.language, paywalled = EXCLUDED.paywalled,
                       enabled = EXCLUDED.enabled""",
                (s.name, s.topic, s.url, s.language, s.paywalled, s.enabled),
            )
        conn.execute(
            "UPDATE sources SET enabled = false WHERE NOT (feed_url = ANY(%s))",
            ([s.url for s in sources],),
        )
        rows = conn.execute("SELECT feed_url, id FROM sources").fetchall()
    return dict(rows)


def recent_titles(conn: psycopg.Connection, days: int = TITLE_WINDOW_DAYS) -> list[str]:
    rows = conn.execute(
        "SELECT title_norm FROM articles WHERE collected_at >= now() - make_interval(days => %s)",
        (days,),
    ).fetchall()
    return [r[0] for r in rows]


def existing_urls(conn: psycopg.Connection, urls: list[str]) -> set[str]:
    rows = conn.execute("SELECT url FROM articles WHERE url = ANY(%s)", (urls,)).fetchall()
    return {r[0] for r in rows}


def store(conn: psycopg.Connection, items: list[Item]) -> int:
    """Insert items; a URL stored meanwhile is skipped. Returns how many rows were inserted."""
    stored = 0
    with conn.transaction():
        for it in items:
            cur = conn.execute(
                """INSERT INTO articles (source_id, url, title, title_norm, excerpt, body,
                                         language, topics, published_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s::topic[], %s)
                   ON CONFLICT (url) DO NOTHING""",
                (
                    it.source_id,
                    it.url,
                    it.title,
                    it.title_norm,
                    it.excerpt,
                    it.body,
                    it.source.language,
                    it.topics,
                    it.published_at,
                ),
            )
            stored += cur.rowcount
    return stored


def add_topic(conn: psycopg.Connection, title_norm: str, url: str | None, topic: str) -> int:
    """A duplicate from another topic's feed adds that topic to the stored article."""
    cur = conn.execute(
        """UPDATE articles SET topics = topics || %s::topic
           WHERE (url = %s OR title_norm = %s) AND NOT (%s::topic = ANY(topics))""",
        (topic, url, title_norm, topic),
    )
    return cur.rowcount


# --- the run ------------------------------------------------------------------------------


def _feed_order(src: Source) -> tuple[int, str]:
    """Free direct feeds first, then Google News, then paywalled: when the same story is in
    several feeds, the copy with full text is the one kept."""
    if src.paywalled:
        rank = 2
    elif urlsplit(src.url).hostname == GOOGLE_NEWS_HOST:
        rank = 1
    else:
        rank = 0
    return rank, src.name


def _by_host(jobs: list, host_of) -> list[list]:
    groups: dict[str, list] = defaultdict(list)
    for job in jobs:
        groups[host_of(job)].append(job)
    return sorted(groups.values(), key=len, reverse=True)  # longest queues start first


def _run_grouped(groups: list[list], fn, workers: int, done=None) -> list:
    """Run fn on every job; jobs of one site run one after another, WORKERS sites at once.
    done(group, seconds) is called as each site's queue finishes (progress)."""

    def worker(group):
        start = time.monotonic()
        results = [fn(job) for job in group]
        if done:
            done(group, time.monotonic() - start)
        return results

    with ThreadPoolExecutor(workers) as pool:
        return [r for results in pool.map(worker, groups) for r in results]


def _merge_topic(item: Item, topic: str) -> int:
    if topic in item.topics:
        return 0
    item.topics.append(topic)
    return 1


def fetch_feed(fetcher: Fetcher, src: Source) -> tuple[Source, bytes | None, str]:
    # Feeds are fetched without the robots.txt check: they are subscriptions the human chose,
    # like any feed reader (Google's Feedfetcher works the same way). Pages are always checked.
    try:
        resp = fetcher.get(src.url, obey_robots=False)
    except Exception as e:
        return src, None, f"{type(e).__name__}: {e}"[:120]
    if resp.status != 200:
        return src, None, f"HTTP {resp.status}"
    return src, resp.body, ""


def collect(
    conn: psycopg.Connection,
    sources: list[Source],
    *,
    fetch_text: bool = True,
    max_age_hours: float = MAX_AGE_HOURS,
    fetcher: Fetcher | None = None,
    now: datetime | None = None,
    workers: int = WORKERS,
    only: str | None = None,
    log=print,
) -> RunStats:
    """One collection run. A failing feed or page is counted and skipped, never fatal.
    `only`: fetch just the feeds whose name contains it (all sources are still synced)."""
    fetcher = fetcher or Fetcher()
    now = now or datetime.now(UTC)
    stats = RunStats()
    ids = sync_sources(conn, sources)
    enabled = sorted(
        (s for s in sources if s.enabled and (not only or only.lower() in s.name.lower())),
        key=_feed_order,
    )

    # 1. Feeds, in parallel (one at a time per site).
    fetched = _run_grouped(
        _by_host(enabled, lambda s: urlsplit(s.url).hostname),
        lambda s: fetch_feed(fetcher, s),
        workers,
    )
    bodies = {src.url: (body, err) for src, body, err in fetched}

    # 2. Parse and de-duplicate, feed by feed in _feed_order.
    titles = TitleIndex(recent_titles(conn))
    run_by_url: dict[str, Item] = {}  # this run's new items, to give them a duplicate's topic
    run_by_title: dict[str, Item] = {}
    new: list[Item] = []
    cutoff = now - timedelta(hours=max_age_hours)
    for src in enabled:
        ts = stats.topics[src.topic]
        ts.feeds += 1
        body, err = bodies[src.url]
        if body is None:
            ts.feeds_failed += 1
            stats.feed_errors.append(f"{src.name}: {err}")
            continue
        items = parse_feed(body, src, ids[src.url], stats)
        if not items:
            ts.feeds_failed += 1
            stats.feed_errors.append(f"{src.name}: no items")
            continue
        ts.entries += len(items)
        in_db = existing_urls(conn, [it.url for it in items])
        for it in items:
            if it.published_at and it.published_at < cutoff:
                ts.too_old += 1
                continue
            if it.url in run_by_url or it.url in in_db:
                ts.dup_url += 1
                if it.url in run_by_url:
                    stats.topics_merged += _merge_topic(run_by_url[it.url], src.topic)
                else:
                    stats.topics_merged += add_topic(conn, it.title_norm, it.url, src.topic)
                continue
            match = titles.match(it.title_norm)
            if match:
                ts.dup_title += 1
                if match in run_by_title:
                    stats.topics_merged += _merge_topic(run_by_title[match], src.topic)
                else:
                    stats.topics_merged += add_topic(conn, match, None, src.topic)
                if match != it.title_norm and len(stats.dup_examples) < 10:
                    stats.dup_examples.append((it.title_norm, match))
                continue
            run_by_url[it.url] = run_by_title[it.title_norm] = it
            titles.add(it.title_norm)
            new.append(it)
    log(f"feeds done: {len(new)} new articles to store")

    # 3. Article text, in parallel (one at a time per site).
    if fetch_text:

        def site_done(group: list[Item], seconds: float) -> None:
            full = sum(it.body is not None for it in group)
            if full or any(not excerpt_only_reason(it) for it in group):
                host = urlsplit(group[0].link).hostname
                log(f"  {host}: {full}/{len(group)} full text, {seconds:.0f} s")

        _run_grouped(
            _by_host(new, lambda it: urlsplit(it.link).hostname),
            lambda it: extract_text(fetcher, it),
            workers,
            site_done,
        )
    else:
        for it in new:
            it.text_status = excerpt_only_reason(it) or "text not fetched (--no-text)"

    # 4. Store, one transaction per feed, so a bad row only loses its own feed's batch.
    by_source: dict[str, list[Item]] = defaultdict(list)
    for it in new:
        by_source[it.source.url].append(it)
    for src in enabled:
        batch = by_source.get(src.url)
        if not batch:
            continue
        ts = stats.topics[src.topic]
        try:
            ts.stored += store(conn, batch)
        except psycopg.Error as e:
            stats.feed_errors.append(f"{src.name}: store failed ({type(e).__name__})")
            continue
        for it in batch:
            if it.body:
                ts.full_text += 1
            else:
                ts.excerpt_only += 1
                stats.excerpt_reasons[it.text_status] += 1
    return stats


def peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Linux: KB


def print_report(stats: RunStats, seconds: float, requests: int) -> None:
    head = (
        f"{'topic':<15} {'feeds':>5} {'fail':>4} {'entries':>7} {'old':>5} "
        f"{'dupURL':>6} {'dupTitle':>8} {'stored':>6} {'full':>5} {'excerpt':>7}"
    )
    print(head)
    total = TopicStats()
    for topic, t in stats.topics.items():
        print(
            f"{topic:<15} {t.feeds:>5} {t.feeds_failed:>4} {t.entries:>7} {t.too_old:>5} "
            f"{t.dup_url:>6} {t.dup_title:>8} {t.stored:>6} {t.full_text:>5} {t.excerpt_only:>7}"
        )
        for name in vars(total):
            setattr(total, name, getattr(total, name) + getattr(t, name))
    t = total
    print(
        f"{'TOTAL':<15} {t.feeds:>5} {t.feeds_failed:>4} {t.entries:>7} {t.too_old:>5} "
        f"{t.dup_url:>6} {t.dup_title:>8} {t.stored:>6} {t.full_text:>5} {t.excerpt_only:>7}"
    )
    print("\nexcerpt-only, why:")
    for reason, n in stats.excerpt_reasons.most_common():
        print(f"  {n:>5}  {reason}")
    print(f"\nnot news, dropped (stock-quote pages): {stats.junk}")
    print(
        f"Google News links: {stats.gn_items}, resolved offline: {stats.gn_resolved}; "
        f"topics added to already-stored articles: {stats.topics_merged}"
    )
    if stats.dup_examples:
        print("near-identical headlines dropped (new -> kept), first few:")
        for a, b in stats.dup_examples[:5]:
            print(f"  {a[:70]!r}\n    -> {b[:70]!r}")
    if stats.feed_errors:
        print("feed errors:")
        for e in stats.feed_errors:
            print(f"  {e}")
    print(
        f"\nrun time {seconds:.0f} s, {requests} HTTP requests, "
        f"peak memory (max RSS) {peak_rss_mb():.0f} MB"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-text", action="store_true", help="store excerpts, fetch no pages")
    parser.add_argument("--feed", help="only fetch feeds whose name contains this text")
    parser.add_argument("--max-age-hours", type=float, default=MAX_AGE_HOURS)
    args = parser.parse_args(argv)

    sources = load_sources(SOURCES_FILE)
    try:
        conn = db.connect(autocommit=True)
    except (RuntimeError, psycopg.OperationalError) as e:
        print(f"cannot connect: {e}".strip())
        return 1
    start = time.monotonic()
    fetcher = Fetcher()
    with conn:
        stats = collect(
            conn,
            sources,
            fetch_text=not args.no_text,
            max_age_hours=args.max_age_hours,
            fetcher=fetcher,
            only=args.feed,
            log=lambda msg: print(msg, flush=True),
        )
    print_report(stats, time.monotonic() - start, fetcher.requests)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
