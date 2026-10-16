"""Tests for topic tagging and top stories (task 1.4). Pure functions run on made-up articles;
the database tests run inside a transaction that is rolled back (see conftest.py)."""

from datetime import UTC, date, datetime, timedelta

import pytest

from natalia import topics as tp
from natalia.collect import normalize_title

END = datetime(2026, 10, 16, 0, 0, tzinfo=UTC)  # 07:00 Asia/Phnom_Penh
_ids = iter(range(1, 10_000))


def art(
    title: str,
    url: str,
    topics=("world-politics",),
    *,
    hours_old: float = 2,
    body: bool = True,
    excerpt: str | None = "An excerpt.",
    paywalled: bool = False,
    also_seen=(),
    cambodia: bool | None = None,
) -> tp.Article:
    return tp.Article(
        id=next(_ids),
        title=title,
        title_norm=normalize_title(title),
        url=url,
        source=url.split("/")[2],
        paywalled=paywalled,
        language="en",
        topics=list(topics),
        feed_topics=list(topics),
        excerpt=excerpt,
        has_body=body,
        published_at=END - timedelta(hours=hours_old),
        also_seen=list(also_seen),
        mentions_cambodia=tp.mentions_cambodia(title) if cambodia is None else cambodia,
    )


# --- tagging --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "title, excerpt, body, expected",
    [
        ("Hun Manet meets Thai leader over border", None, None, {"cambodia"}),
        ("Cambodian rice farmers count flood losses", None, None, {"cambodia"}),
        # Khmer, with the zero-width spaces Khmer sites put between words
        ("រដ្ឋបាល​ខេត្ត​សៀមរាប រៀបចំ​ពិធី", None, None, {"cambodia"}),
        (
            "Mekong dams cut fish catch",
            "A study of fishing in Cambodia and Laos.",
            None,
            {"cambodia"},
        ),
        ("Mekong dams cut fish catch", None, "Phnom Penh ... later in Phnom Penh.", {"cambodia"}),
        ("Mekong dams cut fish catch", None, "One mention of Cambodia only.", set()),
        ("Bitcoin tops $150,000", None, None, {"crypto"}),
        ("Stocks slide as Nasdaq falls", None, None, {"markets"}),
        ("Company results", "Investors cheered. Investors bought.", None, {"markets"}),
        ("Company results", "Investors cheered.", None, set()),  # once in the excerpt: no
        ("Inflation cools in the eurozone", None, None, {"economics"}),
        ("New AI model writes code", None, None, {"technology"}),
        ("Officials said the plan failed", None, None, set()),  # "ai" inside words: no
        ("Whether the deal holds is unclear", None, None, set()),  # "ether" inside a word: no
        ("NASA telescope spots a new comet", None, None, {"science"}),
        ("Premier League: Arsenal win again", None, None, {"sport"}),
    ],
)
def test_rule_topics(title, excerpt, body, expected):
    assert tp.rule_topics(title, excerpt, body) == expected


def test_detect_language():
    assert tp.detect_language("កម្ពុជា-អាស៊ែបៃហ្សង់ លើកកម្ពស់កិច្ចប្រតិបត្តិការ") == "km"
    assert tp.detect_language("German mine clearance support benefits Cambodians") == "en"
    assert tp.detect_language("AI?") is None


# --- stories --------------------------------------------------------------------------------


def test_similar_headlines():
    t = lambda s: tp.title_tokens(normalize_title(s))  # noqa: E731
    albania = t("Albania's prime minister vows not to resign over student-led protests")
    rama = t("Albania's Rama says he will not resign over protests")
    strikes = t("Russia and Ukraine resume energy strikes despite Trump warnings")
    talks = t("Trump warns Russia over Ukraine peace talks")
    assert tp.similar(albania, rama)
    # Without weights the shared names (russia, ukraine, trump) make these look alike ...
    assert tp.similar(strikes, talks)
    # ... but on a real day those names are in many headlines, so they weigh little.
    day = [strikes, talks, albania, rama] + [
        t(f"Trump says Russia Ukraine item {i}") for i in range(20)
    ]
    weights = tp.token_weights(day)
    assert not tp.similar(strikes, talks, weights)
    assert tp.similar(albania, rama, weights)


def test_group_stories_across_sites_only():
    a = art("Albania prime minister will not resign over protests", "https://a.test/1")
    b = art("Albania's prime minister vows not to resign over protests", "https://b.test/1")
    c = art("Albania prime minister vows not to resign over student protests", "https://a.test/2")
    d = art("Brazil approves shorter working week", "https://c.test/1")
    stories = tp.group_stories([a, b, c, d])
    sizes = sorted(len(s.articles) for s in stories)
    assert sizes == [1, 1, 2]  # a+b grouped; c (same site as a) stays apart; d alone
    big = next(s for s in stories if len(s.articles) == 2)
    assert {x.site for x in big.articles} == {"a.test", "b.test"}


def test_google_news_site_is_the_publisher():
    a = art(
        "Pakistan school roof collapse kills 28 - Reuters", "https://news.google.com/rss/articles/X"
    )
    b = art(
        "Children dead after school roof collapse - The New York Times",
        "https://news.google.com/rss/articles/Y",
    )
    assert (a.site, b.site) == ("reuters", "the new york times")


def test_story_sites_include_also_seen_and_lead_prefers_full_text():
    paywalled = art("Big news", "https://pay.test/1", body=False, paywalled=True)
    free = art("Big news again", "https://free.test/1", also_seen=["wire.test", "free.test"])
    story = tp.Story([paywalled, free])
    assert story.sites == ["free.test", "pay.test", "wire.test"]
    assert story.lead is free


def test_score_prefers_coverage_recency_and_full_text():
    one = tp.Story([art("A", "https://a.test/1")])
    three = tp.Story([art("B", "https://a.test/2", also_seen=["b.test", "c.test"])])
    old = tp.Story([art("C", "https://a.test/3", hours_old=23)])
    bare = tp.Story([art("D", "https://a.test/4", body=False, excerpt=None)])
    s = {k: tp.score_story(v, "world-politics", END)[0] for k, v in locals().items() if k != "s"}
    assert s["three"] > s["one"] > s["old"]
    assert s["one"] > s["bare"]
    score, reasons = tp.score_story(three, "world-politics", END)
    assert reasons["sites"] == 2 * tp.W_SITE


@pytest.mark.parametrize(
    "title",
    [
        "Guggenheim reiterates Thermo Fisher Scientific stock Buy rating",
        "Earnings call transcript: UCO Bank posts strong Q2 2026 growth",
        "Today's Wordle hints and answer",
        "The best Prime Day deals on headphones",
        "Your full attention: Jesse Eisenberg's 10 best film performances – ranked!",
        "Norman McCubbin obituary",
        "Sally Rooney's stand on Palestine is brave and humane | Kenan Malik",
    ],
)
def test_low_value_items_are_marked_down(title):
    _, reasons = tp.score_story(tp.Story([art(title, "https://a.test/x")]), "general", END)
    assert reasons["not news"] < 0


def test_cambodia_items_without_a_cambodia_mention_are_marked_down():
    world = tp.Story([art("Oil prices fall", "https://km.test/1", ["cambodia"], cambodia=False)])
    home = tp.Story([art("Flood relief in Siem Reap", "https://km.test/2", ["cambodia"])])
    assert tp.score_story(home, "cambodia", END)[0] > tp.score_story(world, "cambodia", END)[0]


def test_pick_top_limits_unique_and_general_first():
    big = art(
        "Iran war talks collapse in Geneva",
        "https://g.test/1",
        ["general", "world-politics"],
        also_seen=["x.test", "y.test"],
    )
    world = [
        art(f"Event{i} hits city{i} region{i}", f"https://w{i % 3}.test/{i}") for i in range(8)
    ]
    same_site = [
        art(f"Crypto story {i} on tokens", f"https://c.test/{i}", ["crypto"]) for i in range(4)
    ]
    picks = tp.pick_top(tp.group_stories([big, *world, *same_site]), END, per_topic=5)
    assert picks["general"][0].lead is big  # the day's headline goes to "general" ...
    assert all(s.lead is not big for s in picks["world-politics"])  # ... and only there
    assert len(picks["world-politics"]) == 5
    assert len(picks["crypto"]) == 2  # at most 2 from one site per topic
    assert picks["science"] == []


def test_day_window():
    start, end = tp.day_window(date(2026, 10, 16))
    assert end == datetime(2026, 10, 16, 0, 0, tzinfo=UTC)
    assert start == datetime(2026, 10, 15, 0, 0, tzinfo=UTC)


# --- database -------------------------------------------------------------------------------


def _insert(conn, src_id, url, title, topics, published, excerpt=None, body=None, lang="en"):
    conn.execute(
        """INSERT INTO articles (source_id, url, title, title_norm, excerpt, body, language,
                                 topics, published_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s::topic[], %s)""",
        (src_id, url, title, normalize_title(title), excerpt, body, lang, topics, published),
    )


@pytest.fixture
def test_source(scratch):
    return scratch.execute(
        """INSERT INTO sources (name, topic, feed_url) VALUES ('Test Topics', 'economics',
           'https://topics.test/feed') RETURNING id"""
    ).fetchone()[0]


def test_tag_articles_adds_rule_topics_fixes_language_and_is_idempotent(scratch, test_source):
    when = datetime(2020, 1, 1, tzinfo=UTC)
    _insert(
        scratch,
        test_source,
        "https://topics.test/1",
        "Cambodia cuts rice export tariffs",
        ["economics"],
        when,
    )
    _insert(
        scratch,
        test_source,
        "https://topics.test/2",
        "រដ្ឋបាលខេត្តសៀមរាប រៀបចំពិធី",
        ["economics"],
        when,
    )  # stored as 'en' by its feed
    scratch.execute(
        "UPDATE articles SET collected_at = now() + interval '1 day' WHERE url LIKE %s",
        ("https://topics.test/%",),
    )
    # Only our rows: "collected" in the future, and the window starts there.
    scratch.execute("SET LOCAL statement_timeout = '20s'")
    tp_days = -0.5  # now - (-0.5 day) = 12 h from now: only rows collected after that
    stats = tp.tag_articles(scratch, days=tp_days)
    rows = {
        url: (topics, rule, lang)
        for url, topics, rule, lang in scratch.execute(
            "SELECT url, topics::text[], rule_topics::text[], language FROM articles"
            " WHERE url LIKE %s",
            ("https://topics.test/%",),
        ).fetchall()
    }
    assert rows["https://topics.test/1"] == (["economics", "cambodia"], ["cambodia"], "en")
    assert rows["https://topics.test/2"] == (["economics", "cambodia"], ["cambodia"], "km")
    assert stats.added["cambodia"] == 2 and stats.language_fixed["en->km"] == 1
    assert tp.tag_articles(scratch, days=tp_days).changed == 0


def test_top_stories_from_the_database(scratch, test_source):
    end = datetime(2020, 1, 2, tzinfo=UTC)
    for i in range(7):
        _insert(
            scratch,
            test_source,
            f"https://topics.test/s{i}",
            f"Zebra economy story {i}",
            ["economics"],
            end - timedelta(hours=i + 1),
            excerpt="x",
            body="y" * 400,
        )
    _insert(
        scratch,
        test_source,
        "https://topics.test/old",
        "Old zebra story",
        ["economics"],
        end - timedelta(hours=30),
    )
    picks, n_articles, _ = tp.top_stories(scratch, end)
    assert n_articles == 7
    assert [s.lead.url for s in picks["economics"]] == [
        "https://topics.test/s0",
        "https://topics.test/s1",
    ]  # newest first; 2 per site
