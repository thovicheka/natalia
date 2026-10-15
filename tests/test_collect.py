"""Tests for the collector (task 1.3). No network: a fake fetcher serves feeds, pages and
robots.txt from memory and records every URL requested. The `collect` tests run against the
real database inside a transaction that is rolled back (see conftest.py)."""

import base64
from datetime import UTC, datetime, timedelta

import pytest

from natalia import collect as c
from natalia.feeds import Source

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
ARTICLE_TEXT = " ".join(
    f"Paragraph {i} of a long and perfectly ordinary news story about rice exports."
    for i in range(12)
)


def page(text: str = ARTICLE_TEXT, extra_head: str = "") -> bytes:
    paras = "".join(f"<p>{s}.</p>" for s in text.split(". "))
    return (
        f"<html><head><title>Story</title>{extra_head}</head><body><nav>Menu</nav>"
        f"<article><h1>Story</h1>{paras}</article><footer>Contact</footer></body></html>"
    ).encode()


def rss(*items: tuple[str, str, datetime], source: tuple[str, str] | None = None) -> bytes:
    src = f'<source url="{source[1]}">{source[0]}</source>' if source else ""
    body = "".join(
        f"<item><title>{t}</title><link>{link}</link>"
        f"<pubDate>{when.strftime('%a, %d %b %Y %H:%M:%S GMT')}</pubDate>"
        f"<description>{t}. A summary that says a little more than the headline does.</description>"
        f"{src}</item>"
        for t, link, when in items
    )
    head = '<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>'
    return f"{head}{body}</channel></rss>".encode()


class FakeFetcher(c.Fetcher):
    """Serves {url: Response | Exception}; unknown URLs are 404. Records each URL requested."""

    def __init__(self, pages: dict):
        super().__init__(delay=0)
        self.pages = pages
        self.seen: list[str] = []

    def _raw_get(self, url, host, delay):
        self.seen.append(url)
        got = self.pages.get(url)
        if isinstance(got, Exception):
            raise got
        if got is None:
            return c.Response(404, url)
        return got


def ok(body: bytes, content_type: str = "text/html; charset=utf-8") -> c.Response:
    return c.Response(200, "", body, content_type)


ROBOTS_OPEN = ok(b"User-agent: *\nDisallow: /private/\n", "text/plain")


# --- cleaning -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            "HTTP://WWW.BBC.co.uk/news/x/?utm_source=rss&b=2&a=1#top",
            "https://www.bbc.co.uk/news/x?a=1&b=2",
        ),
        ("https://example.com/a//b/?at_medium=RSS&fbclid=1", "https://example.com/a/b"),
        (
            "https://news.google.com/rss/articles/CBMiabc?oc=5",
            "https://news.google.com/rss/articles/CBMiabc",
        ),
        ("https://example.com", "https://example.com/"),
    ],
)
def test_canonical_url(raw, expected):
    assert c.canonical_url(raw) == expected


def _gn(payload: bytes) -> str:
    return (
        "https://news.google.com/rss/articles/"
        + base64.urlsafe_b64encode(payload).decode().rstrip("=")
        + "?oc=5"
    )


def test_decode_google_news_old_style_id():
    url = _gn(b'\x08\x13"+https://www.reuters.com/world/some-story-2026/\xd2\x01')
    assert c.decode_google_news(url) == "https://www.reuters.com/world/some-story-2026/"


def test_decode_google_news_new_style_id_stays_unresolved():
    assert c.decode_google_news(_gn(b'\x08\x13"\xa2\x01AU_yqLNc4vGw-W_XPYIG-P3thOL2Wguu9')) is None
    assert c.decode_google_news("https://example.com/rss/articles/abc") is None


def test_normalize_title():
    assert c.normalize_title("Rama won’t resign — protests grow - Reuters", "Reuters") == (
        "rama won t resign protests grow"
    )
    # Khmer vowel signs are combining marks and must survive.
    assert c.normalize_title("ស្ថានីយ៍ទូរទស្សន៍!") == "ស្ថានីយ៍ទូរទស្សន៍"


def test_clean_excerpt():
    title = "Albania's Rama says he will not resign"
    gn = f'<a href="https://news.google.com/x">{title}</a>&nbsp;&nbsp;<font>Reuters</font>'
    assert c.clean_excerpt(gn, title) is None
    assert c.clean_excerpt("", title) is None
    long = "<p>" + "word " * 400 + "</p>"
    out = c.clean_excerpt(long, title)
    assert out.endswith("…") and len(out) <= c.MAX_EXCERPT_CHARS + 1 and "<p>" not in out


def test_title_index_exact_and_near_identical():
    idx = c.TitleIndex(["stocks rise as fed signals a rate cut in december", "rain"])
    assert idx.match("stocks rise as fed signals a rate cut in december") is not None
    assert idx.match("stocks rise as the fed signals a rate cut in december") is not None
    assert idx.match("stocks fall as china reports weak exports in september") is None
    assert idx.match("rain") == "rain"  # short titles: exact only
    assert idx.match("rains") is None


def test_excerpt_only_reasons():
    free = Source("Free", "general", "https://free.test/feed")
    pay = Source("Pay", "markets", "https://pay.test/feed", paywalled=True)

    def item(src, link, host=None):
        return c.Item(src, 1, link, link, "t", "t", None, None, host or c.urlsplit(link).hostname)

    assert c.excerpt_only_reason(item(pay, "https://pay.test/a")) == "paywalled source"
    gn = item(free, "https://news.google.com/rss/articles/x", "www.reuters.com")
    assert "Google News" in c.excerpt_only_reason(gn)
    assert (
        c.excerpt_only_reason(item(free, "https://www.apnews.com/a")) == "blocked or paywalled site"
    )
    assert c.excerpt_only_reason(item(free, "https://www.marketwatch.com/a")) is not None
    assert c.excerpt_only_reason(item(free, "https://free.test/a")) is None


# --- fetching -----------------------------------------------------------------------------


def test_robots_disallow_and_missing_robots():
    f = FakeFetcher({"https://a.test/robots.txt": ROBOTS_OPEN, "https://a.test/ok": ok(b"x")})
    assert f.get("https://a.test/ok").status == 200
    with pytest.raises(c.Blocked):
        f.get("https://a.test/private/x")
    assert "https://a.test/private/x" not in f.seen
    # robots.txt 404: everything allowed. robots.txt 403: nothing allowed.
    f = FakeFetcher({"https://b.test/robots.txt": c.Response(403, "")})
    with pytest.raises(c.Blocked):
        f.get("https://b.test/page")
    assert f.get("https://c.test/page").status == 404  # no robots.txt, page fetched


def test_robots_checked_on_every_redirect_hop():
    f = FakeFetcher(
        {
            "https://a.test/robots.txt": ROBOTS_OPEN,
            "https://a.test/go": c.Response(301, "", location="https://b.test/private/x"),
            "https://b.test/robots.txt": ROBOTS_OPEN,
        }
    )
    with pytest.raises(c.Blocked):
        f.get("https://a.test/go")
    assert "https://b.test/private/x" not in f.seen


def test_long_crawl_delay_blocks():
    f = FakeFetcher(
        {"https://slow.test/robots.txt": ok(b"User-agent: *\nCrawl-delay: 120\n", "text/plain")}
    )
    with pytest.raises(c.Blocked, match="crawl delay"):
        f.get("https://slow.test/a")


def _item(link: str, paywalled: bool = False) -> c.Item:
    src = Source("S", "general", "https://s.test/feed", paywalled=paywalled)
    return c.Item(src, 1, link, link, "Story", "story", None, None, c.urlsplit(link).hostname)


def test_extract_text_full_and_refusals():
    good, wall, pdf, thin = (f"https://n.test/{x}" for x in ("good", "wall", "pdf", "thin"))
    marker = '<script type="application/ld+json">{"isAccessibleForFree": false}</script>'
    f = FakeFetcher(
        {
            "https://n.test/robots.txt": ROBOTS_OPEN,
            good: ok(page()),
            wall: ok(page(extra_head=marker)),
            pdf: ok(b"%PDF-1.7", "application/pdf"),
            thin: ok(page("Subscribe to read")),
        }
    )
    items = {k: _item(k) for k in (good, wall, pdf, thin)}
    for it in items.values():
        c.extract_text(f, it)
    assert items[good].text_status == "full" and "rice exports" in items[good].body
    assert "<p>" not in items[good].body and "Menu" not in items[good].body
    assert items[wall].text_status == "paywall marker on page" and items[wall].body is None
    assert items[pdf].text_status == "not HTML"
    assert items[thin].text_status == "too little text on page"


def test_extract_text_never_fetches_paywalled_or_google_news():
    f = FakeFetcher({})
    for it in (
        _item("https://pay.test/a", paywalled=True),
        _item("https://news.google.com/rss/articles/x"),
    ):
        c.extract_text(f, it)
        assert it.body is None
    assert f.seen == []


def test_extract_text_survives_network_errors():
    f = FakeFetcher(
        {"https://n.test/robots.txt": ROBOTS_OPEN, "https://n.test/a": TimeoutError("slow")}
    )
    it = _item("https://n.test/a")
    c.extract_text(f, it)
    assert it.body is None and it.text_status == "fetch failed (TimeoutError)"


# --- a whole run, against the real database (rolled back) --------------------------------


FREE = Source("Test Free", "economics", "https://free.test/feed")
OTHER = Source("Test Other", "cambodia", "https://other.test/feed")
PAY = Source("Test Pay", "markets", "https://pay.test/feed", paywalled=True)
GN = Source("Test GN", "general", "https://news.google.com/rss/search?q=test")
BROKEN = Source("Test Broken", "science", "https://broken.test/feed")
OFF = Source("Test Off", "sport", "https://off.test/feed", enabled=False)
SOURCES = [FREE, OTHER, PAY, GN, BROKEN, OFF]
GN_LINK = _gn(b'\x08\x13"\xa2\x01AU_yqLopaque')


def _pages() -> dict:
    recent, old = NOW - timedelta(hours=3), NOW - timedelta(days=5)
    return {
        "https://free.test/robots.txt": ROBOTS_OPEN,
        FREE.url: ok(
            rss(
                (
                    "Cambodia rice exports jump to a record high in September",
                    "https://free.test/rice?utm_source=rss",
                    recent,
                ),
                ("Central bank holds rates steady again", "https://free.test/rates", recent),
                ("An old story from last week", "https://free.test/old", old),
            )
        ),
        "https://free.test/rice?utm_source=rss": ok(page()),
        "https://free.test/rates": ok(page()),
        # Same rice story: same URL (other tracking), and a near-identical headline elsewhere.
        OTHER.url: ok(
            rss(
                (
                    "Cambodia rice exports jump to a record high in September",
                    "https://free.test/rice?ref=x",
                    recent,
                ),
                (
                    "Cambodia's rice exports jump to record high in September",
                    "https://other.test/rice",
                    recent,
                ),
                ("Floods close schools in Pursat province", "https://other.test/floods", recent),
            )
        ),
        "https://other.test/robots.txt": ok(b"User-agent: natalia\nDisallow: /\n", "text/plain"),
        PAY.url: ok(rss(("Markets slide on tariff fears", "https://pay.test/markets", recent))),
        GN.url: ok(
            rss(
                ("Albania's Rama says he will not resign over protests - Reuters", GN_LINK, recent),
                source=("Reuters", "https://www.reuters.com"),
            )
        ),
        BROKEN.url: TimeoutError("feed down"),
    }


def _rows(conn):
    return conn.execute(
        """SELECT a.url, a.topics::text[], a.body IS NOT NULL, a.excerpt IS NOT NULL, s.name
           FROM articles a JOIN sources s ON s.id = a.source_id
           WHERE s.feed_url LIKE '%.test/%' OR s.feed_url LIKE '%q=test'
           ORDER BY a.url"""
    ).fetchall()


def test_collect_twice_stores_each_article_once(scratch):
    pages = _pages()
    f = FakeFetcher(pages)
    s1 = c.collect(scratch, SOURCES, fetcher=f, now=NOW, workers=2, log=lambda *_: None)

    rows = {
        url: (topics, body, excerpt, name) for url, topics, body, excerpt, name in _rows(scratch)
    }
    assert set(rows) == {
        "https://free.test/rice",
        "https://free.test/rates",
        "https://other.test/floods",
        "https://pay.test/markets",
        c.canonical_url(GN_LINK),
    }
    # The duplicate from the Cambodia feed added its topic to the stored copy.
    assert sorted(rows["https://free.test/rice"][0]) == ["cambodia", "economics"]
    assert rows["https://free.test/rice"][1] is True  # full text
    assert rows["https://other.test/floods"][1] is False  # robots.txt disallows natalia
    assert rows["https://pay.test/markets"][1:3] == (False, True)  # excerpt only
    assert rows[c.canonical_url(GN_LINK)][1] is False  # GN: headline + excerpt + link only
    # Never requested: paywalled pages, Google News redirects, robots-disallowed pages, old ones.
    for url in (
        "https://pay.test/markets",
        GN_LINK,
        "https://other.test/floods",
        "https://free.test/old",
    ):
        assert url not in f.seen
    assert "https://off.test/feed" not in f.seen

    t = s1.topics
    assert (t["economics"].stored, t["economics"].full_text, t["economics"].too_old) == (2, 2, 1)
    assert (t["cambodia"].dup_url, t["cambodia"].dup_title, t["cambodia"].stored) == (1, 1, 1)
    assert t["science"].feeds_failed == 1 and "Test Broken" in s1.feed_errors[0]
    assert s1.excerpt_reasons["robots.txt disallows"] == 1

    # Second run: nothing new is stored, and no article page is fetched again.
    f2 = FakeFetcher(pages)
    s2 = c.collect(scratch, SOURCES, fetcher=f2, now=NOW, workers=2, log=lambda *_: None)
    assert sum(ts.stored for ts in s2.topics.values()) == 0
    assert len(_rows(scratch)) == 5
    assert not [u for u in f2.seen if "/feed" not in u and "q=test" not in u and "robots" not in u]


def test_sync_sources_upserts_and_disables_missing(scratch):
    ids = c.sync_sources(scratch, SOURCES)
    assert set(ids) >= {s.url for s in SOURCES}
    renamed = Source("Renamed", "economics", FREE.url, paywalled=True)
    c.sync_sources(scratch, [renamed])
    row = scratch.execute(
        "SELECT name, paywalled, enabled FROM sources WHERE feed_url = %s", (FREE.url,)
    ).fetchone()
    assert row == ("Renamed", True, True)
    (enabled,) = scratch.execute(
        "SELECT enabled FROM sources WHERE feed_url = %s", (OTHER.url,)
    ).fetchone()
    assert enabled is False
