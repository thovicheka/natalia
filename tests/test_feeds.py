"""Tests for the feed list and the feed checker. No network: feeds are served from memory."""

import io
from pathlib import Path

import pytest

from natalia import feeds
from natalia.feeds import TOPICS, Source, check_feed, load_sources

# Paywalled per CLAUDE.md: headline + excerpt + link only.
PAYWALLED = ("Bloomberg", "Financial Times", "WSJ", "The Athletic")

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Test</title>
<item><title>Older</title><link>https://example.com/1</link>
  <pubDate>Mon, 12 Oct 2026 08:00:00 GMT</pubDate></item>
<item><title>Newer</title><link>https://example.com/2</link>
  <pubDate>Wed, 14 Oct 2026 08:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_sources_file_is_valid():
    sources = load_sources()
    assert {s.topic for s in sources} == set(TOPICS)


@pytest.mark.parametrize("topic", TOPICS)
def test_each_topic_has_two_free_feeds(topic):
    free = [s for s in load_sources() if s.topic == topic and s.enabled and not s.paywalled]
    assert len(free) >= 2, f"{topic}: {[s.name for s in free]}"


def test_known_paywalled_sources_are_flagged():
    for s in load_sources():
        if s.name.startswith(PAYWALLED):
            assert s.paywalled, s.name


def test_disabled_feeds_say_why():
    for s in load_sources():
        if not s.enabled:
            assert s.note, s.name


def test_unknown_topic_is_rejected(tmp_path: Path):
    bad = tmp_path / "sources.yaml"
    bad.write_text('sources:\n  - {name: X, topic: gossip, url: "https://x.example/feed"}\n')
    with pytest.raises(ValueError, match="unknown topic"):
        load_sources(bad)


def test_duplicate_urls_are_rejected(tmp_path: Path):
    bad = tmp_path / "sources.yaml"
    row = '  - {name: X, topic: sport, url: "https://x.example/feed"}\n'
    bad.write_text("sources:\n" + row + row)
    with pytest.raises(ValueError, match="duplicate"):
        load_sources(bad)


class _Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_check_feed_parses_items(monkeypatch):
    monkeypatch.setattr(feeds.urllib.request, "urlopen", lambda req, timeout: _Resp(RSS))
    c = check_feed(Source(name="T", topic="sport", url="https://x.example/feed"))
    assert c.working and c.items == 2
    assert c.latest.isoformat() == "2026-10-14T08:00:00+00:00"


def test_check_feed_never_raises(monkeypatch):
    def boom(req, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(feeds.urllib.request, "urlopen", boom)
    c = check_feed(Source(name="T", topic="sport", url="https://x.example/feed"))
    assert not c.working and "TimeoutError" in c.error


def test_user_agent_is_honest_and_shared():
    # NPR stalls a fake "Mozilla/5.0" user agent and any containing "robots" (task 1.3).
    from natalia import collect

    assert "mozilla" not in feeds.USER_AGENT.lower()
    assert "robots" not in feeds.USER_AGENT.lower()
    assert collect.USER_AGENT is feeds.USER_AGENT
