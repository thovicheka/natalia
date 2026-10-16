"""The feed list: load config/sources.yaml, check each feed, print the latest headlines.

    uv run python -m natalia.feeds              # check enabled feeds, 5 latest headlines per topic
    uv run python -m natalia.feeds --all        # also check disabled feeds
    uv run python -m natalia.feeds -n 0         # check only, no headlines

One plain HTTP GET per feed; no article pages are fetched (that's task 1.3).
"""

from __future__ import annotations

import argparse
import calendar
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import feedparser
import yaml

SOURCES_FILE = Path(__file__).resolve().parent.parent / "config" / "sources.yaml"

# The nine topics of docs/PLAN.md, in its order.
TOPICS = (
    "economics",
    "world-politics",
    "technology",
    "science",
    "sport",
    "crypto",
    "markets",
    "cambodia",
    "general",
)
LANGUAGES = ("en", "km")

# Names what we are, without "Mozilla/5.0". NPR (Akamai) stalls until timeout both a fake
# "Mozilla/5.0 (compatible; …)" UA and any UA containing "robots"; this one answers in 0.1 s
# (measured 2026-10-15, task 1.3). Shared with the collector.
USER_AGENT = "natalia/0.1 (personal news reader)"
TIMEOUT_S = 20
MAX_BYTES = 5_000_000
STALE_DAYS = 14


@dataclass(frozen=True)
class Source:
    name: str
    topic: str
    url: str
    language: str = "en"
    paywalled: bool = False
    enabled: bool = True
    note: str = ""


@dataclass
class Check:
    source: Source
    status: int | None = None
    items: int = 0
    latest: datetime | None = None
    error: str = ""
    entries: list[tuple[datetime | None, str, str]] = field(default_factory=list)

    @property
    def working(self) -> bool:
        return self.status == 200 and self.items > 0 and not self.error

    @property
    def stale(self) -> bool:
        if self.latest is None:
            return False
        return (datetime.now(UTC) - self.latest).days > STALE_DAYS


def load_sources(path: Path = SOURCES_FILE) -> list[Source]:
    """Read and validate the feed list."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    sources = []
    for i, row in enumerate(data["sources"]):
        src = Source(**row)
        if src.topic not in TOPICS:
            raise ValueError(f"sources[{i}] {src.name}: unknown topic {src.topic!r}")
        if src.language not in LANGUAGES:
            raise ValueError(f"sources[{i}] {src.name}: unknown language {src.language!r}")
        if not src.url.startswith("https://"):
            raise ValueError(f"sources[{i}] {src.name}: feed URL must be https")
        sources.append(src)
    urls = [s.url for s in sources]
    dupes = {u for u in urls if urls.count(u) > 1}
    if dupes:
        raise ValueError(f"duplicate feed URLs: {sorted(dupes)}")
    return sources


def _entry_time(entry) -> datetime | None:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime.fromtimestamp(calendar.timegm(t), UTC) if t else None


def check_feed(src: Source) -> Check:
    """GET the feed once and parse it. Never raises."""
    result = Check(src)
    req = urllib.request.Request(src.url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            result.status = resp.status
            body = resp.read(MAX_BYTES)
    except urllib.error.HTTPError as e:
        result.status, result.error = e.code, f"HTTP {e.code}"
        return result
    except Exception as e:  # DNS, TLS, timeout: a broken feed must not stop the others
        result.error = f"{type(e).__name__}: {e}"[:120]
        return result

    parsed = feedparser.parse(body)
    result.items = len(parsed.entries)
    if not result.items:
        result.error = "no items" + (f" ({parsed.bozo_exception})"[:100] if parsed.bozo else "")
    for entry in parsed.entries:
        when = _entry_time(entry)
        result.entries.append((when, entry.get("title", "").strip(), entry.get("link", "")))
    dates = [when for when, _, _ in result.entries if when]
    result.latest = max(dates) if dates else None
    return result


def check_all(sources: list[Source], workers: int = 8) -> list[Check]:
    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(check_feed, sources))


def _verdict(c: Check) -> str:
    if not c.working:
        return f"❌ {c.error}"
    return "⚠️ stale" if c.stale else "✅"


def print_checks(checks: list[Check]) -> None:
    print(f"{'topic':<15} {'source':<34} {'pay':<4} {'items':>5}  {'latest (UTC)':<16}  result")
    for c in checks:
        s = c.source
        latest = c.latest.strftime("%Y-%m-%d %H:%M") if c.latest else "-"
        pay = "yes" if s.paywalled else "no"
        print(f"{s.topic:<15} {s.name[:34]:<34} {pay:<4} {c.items:>5}  {latest:<16}  {_verdict(c)}")
    ok = sum(c.working for c in checks)
    print(f"\n{ok}/{len(checks)} feeds working")


def print_headlines(checks: list[Check], n: int) -> None:
    for topic in TOPICS:
        items = [
            (when, title, c.source.name)
            for c in checks
            if c.source.topic == topic and c.working
            for when, title, _ in c.entries
        ]
        items.sort(key=lambda x: x[0] or datetime.min.replace(tzinfo=UTC), reverse=True)
        print(f"\n## {topic}")
        for when, title, name in items[:n]:
            stamp = when.strftime("%m-%d %H:%M") if when else "--"
            print(f"  {stamp}  [{name}] {title[:100]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--all", action="store_true", help="also check disabled feeds")
    parser.add_argument("-n", type=int, default=5, help="headlines per topic (0 = none)")
    parser.add_argument("--file", type=Path, default=SOURCES_FILE)
    args = parser.parse_args(argv)

    sources = [s for s in load_sources(args.file) if args.all or s.enabled]
    checks = check_all(sources)
    print_checks(checks)
    if args.n:
        print_headlines(checks, args.n)
    return 0 if all(c.working for c in checks if c.source.enabled) else 1


if __name__ == "__main__":
    raise SystemExit(main())
