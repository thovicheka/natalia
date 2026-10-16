# Stage 1 — Sources and feeds

**Tasks:** 1.1 (updated in 1.3) · **Status:** ✅ done

**What you'll have working by the end:** `config/sources.yaml`, a checked list of RSS/Atom feeds for Natalia's nine topics (every topic has at least 4 working free feeds), and a command that checks every feed and prints the latest headlines per topic.

| Placeholder | In this build |
|---|---|
| `<feed-url>` | e.g. `https://feeds.bbci.co.uk/news/business/rss.xml` |
| `<homepage>` | e.g. `https://www.khmertimeskh.com/` |

## Prerequisites
- [Stage 0](00-project-setup.md): the `uv` project.
- Outgoing HTTPS from the server. Fetching public feeds is free.

## Steps

### 1. Add the feed libraries
```bash
uv add feedparser pyyaml
```
*What it does:* `feedparser` reads RSS and Atom (and is used again by the collector); `pyyaml` reads the config.

<details><summary>Example from this build</summary>

```console
$ uv add feedparser pyyaml
 + feedparser==6.0.14
 + feedparser-sgmllib==2.1.0
 + pyyaml==6.0.3
```
**Result:** ✅
</details>

### 2. Find each source's feed URL
For each source in PLAN.md, fetch its homepage once and read the `<link rel="alternate" type="application/rss+xml">` tags. Most WordPress sites (many Cambodian outlets) serve `/feed/`.

*What it does:* finds the feed the site itself advertises, instead of guessing URLs.

<details><summary>Example from this build (33 homepages, one GET each)</summary>

```console
https://www.khmertimeskh.com/ [200] -> ['https://www.khmertimeskh.com/feed/', ...]
https://www.phnompenhpost.com/ [200] -> ['https://phnompenhpost.com/feed/', ...]
https://cambodianess.com/ [200] -> []
https://www.postkhmer.com/ [200] -> ['https://postkhmer.com/feed', ...]
https://www.freshnewsasia.com/ ERROR HTTPError: HTTP Error 403: Forbidden
https://www.quantamagazine.org/ [200] -> ['https://www.quantamagazine.org/quanta/feed/']
https://apnews.com/ ERROR HTTPError: HTTP Error 403: Forbidden
https://www.reuters.com/ ERROR HTTPError: HTTP Error 401: HTTP Forbidden
(…25 more)
```
**Result:** ✅ AP and Reuters block plain clients and publish no RSS. In 1.1 they were reached through Google News search feeds; those were disabled in 1.3 (step 6).
</details>

### 3. Write `config/sources.yaml`
One entry per feed:
```yaml
sources:
  - {name: BBC News Business, topic: economics, url: "https://feeds.bbci.co.uk/news/business/rss.xml"}
  - {name: Bloomberg Economics, topic: economics, url: "https://feeds.bloomberg.com/economics/news.rss", paywalled: true}
  - {name: Post Khmer, topic: cambodia, url: "https://postkhmer.com/feed", language: km}
  - {name: Yahoo Finance, topic: markets, url: "…", enabled: false, note: "HTTP 404 (3 URLs tried)"}
```
Fields: `name`, `topic` (one of the 9: `economics`, `world-politics`, `technology`, `science`, `sport`, `crypto`, `markets`, `cambodia`, `general`), `url`, `language` (`en`|`km`, default `en`), `paywalled` (default `false`), `enabled` (default `true`), `note`.

*What it does:* `paywalled: true` means headline + excerpt + link only; the collector never requests those pages ([why](decisions.md#paywalls-headline--excerpt--link-only)). `enabled: false` keeps dead or disallowed feeds in the file, with the reason, so nobody re-adds them blindly.

### 4. Check every feed
```bash
uv run python -m natalia.feeds            # enabled feeds + 5 latest headlines per topic
uv run python -m natalia.feeds --all      # also the disabled ones
uv run python -m natalia.feeds -n 0       # check only, no headlines
```
*What it does:* one GET per feed (≈1.5 minutes for all), then a table: items, latest item time, and ✅ / ⚠️ stale (nothing in 14 days) / ❌. Exits 1 if an enabled feed fails.

<details><summary>Example from this build: the first check, and what it hid</summary>

The first check of 85 candidates said `78/85 feeds working`, but three results looked wrong: Quanta's only item was from 2013; "Google News Khmer" and "Google News Top Stories" had identical counts; "Khmer Times Khmer" matched "Khmer Times". A closer look (feed title and final URL after redirects):
```console
https://news.google.com/rss?hl=km&gl=KH&ceid=KH:km
  [200] final=https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en items=38 title='Top stories - Google News'
https://www.khmertimeskh.com/kh/feed/
  [200] final=https://www.khmertimeskh.com/feed/ items=20 title='Khmer Times'
https://api.quantamagazine.org/feed/
  [200] final=https://www.quantamagazine.org/feed/ items=5 title='Quanta Magazine'
https://finance.yahoo.com/rss/topstories    ERROR HTTPError: HTTP Error 404: Not Found
https://cambodianess.com/rss                ERROR HTTPError: HTTP Error 404: Not Found
https://cambojanews.com/km/feed/
  [200] items=0 title='Comments on:'
```
**Result:** ❌ → fixed. **Error:** wrong or duplicate feeds counted as working. **Cause:** Google News has no Khmer edition and silently redirects to US English; Khmer Times' `/kh/feed/` redirects to the English feed; Quanta's advertised feed URL is stale. **Fix:** Quanta changed to `/feed/`; the two redirects and the dead/broken feeds set `enabled: false` with a note.
</details>

> **If you see** a feed that "works" but has the same item count as another, or very old items, **it means** it probably redirects somewhere else. Check the feed's title and final URL, not only the status code.

### 5. Tests
```bash
uv run pytest -q tests/test_feeds.py
```
*What it does:* offline checks: the list is valid, every topic has ≥ 2 enabled free feeds, the known paywalled sources are flagged, disabled feeds say why, the checker parses RSS and never raises, and the user agent is honest (no "Mozilla", no "robots").

<details><summary>Example from this build (end of 1.1)</summary>

```console
$ uv run pytest -q
21 passed in 0.26s
$ uv run ruff check . ; uv run ruff format --check .
All checks passed!
12 files already formatted
```
**Result:** ✅
</details>

### 6. Changes made in task 1.3 (the human's decisions, 2026-10-15)
- **Google News feeds disabled (10).** news.google.com's robots.txt disallows `/rss/search` (the feeds) and `/rss/articles/` (their links). Natalia respects robots.txt for feeds too ([why](decisions.md#robotstxt-respected-for-pages-and-feeds-google-news-dropped)). This removed Reuters, AP and Nikkei Asia, which only came through Google News.
- **Two technology feeds added** after the same feed check plus a full-text check with the collector's own extractor (robots.txt, paywall marker, text length) on each candidate's 2 latest articles:
  ```console
  The Register    feed=200 items=50 latest=10-15 10:30 crawl-delay=None pages=['robots.txt disallows:0', 'robots.txt disallows:0']
  Engadget        feed=200 items=20 latest=10-15 10:34 crawl-delay=None pages=['full:2445', 'full:2034']
  IEEE Spectrum   feed=200 items=30 latest=10-15 10:00 crawl-delay=None pages=['full:2301', 'full:1538']
  Rest of World   feed=200 items=12 latest=10-15 10:00 crawl-delay=None pages=['full:6686', 'full:6050']
  ZDNET           feed=200 items=25 latest=10-14 13:59 crawl-delay=None pages=['full:3191', 'full:4095']
  The Next Web    feed FAIL HTTP 403
  Tom's Hardware  feed=200 items=50 latest=10-15 10:30 crawl-delay=None pages=['full:3588', 'full:2400']
  9to5Google      feed=200 items=100 latest=10-15 11:00 crawl-delay=None pages=['paywall marker on page:0', 'full:1494']
  ```
  **Result:** ✅ **Engadget** and **Rest of World** added. Not chosen: The Register (robots.txt disallows us), The Next Web (feed 403), 9to5Google (paywall marker), IEEE Spectrum, ZDNET and Tom's Hardware (announcements, reviews and product news).
- **User agent** in `natalia/feeds.py`: `natalia/0.1 (personal news reader)`, shared with the collector (was a `Mozilla/5.0` string in 1.1).

## The list today

87 feeds, **66 enabled** (50 free, 16 paywalled), 21 disabled. Khmer: 4 enabled feeds, all Cambodia.

| Topic | Free (enabled) | Paywalled (enabled) | Disabled |
|---|---|---|---|
| economics | 4: BBC Business, Guardian Economics, CNBC Economy, NPR Economy | 4: Bloomberg, FT, WSJ, The Economist | 1 |
| world-politics | 6: BBC World, Al Jazeera, Guardian World, NPR World, DW, France 24 | 1: Foreign Affairs | 2 |
| technology | 6: Ars Technica, The Verge, TechCrunch, BBC Technology, Engadget, Rest of World | 2: Wired, MIT Technology Review | 0 |
| science | 6: ScienceDaily, Quanta, BBC Science, Guardian Science, Phys.org, NASA | 3: Nature, Scientific American, New Scientist | 0 |
| sport | 4: BBC Sport, ESPN, Sky Sports, Guardian Sport | 1: The Athletic | 0 |
| crypto | 5: CoinDesk, Cointelegraph, Decrypt, The Block, Bitcoin Magazine | 1: Bloomberg Crypto | 0 |
| markets | 4: CNBC Markets, FXStreet, ForexLive, Investing.com | 4: MarketWatch, Bloomberg, WSJ, FT | 2 |
| cambodia | 11: Khmer Times, Phnom Penh Post, CamboJA, VOD English, Cambodia Daily, Cambodia Investment Review, Guardian Cambodia; Khmer: Post Khmer, Kohsantepheap, DAP News, RFA Khmer | 0 | 13 |
| general | 4: BBC Top Stories, NPR News, Guardian International, Sky News World | 0 | 3 |

**Disabled, and why** (details in each entry's `note`): Google News feeds (robots.txt; 10); dead or no feed: Yahoo Finance (404), Cambodianess, Thmey Thmey, CamboJA Khmer (empty), VOA Khmer (stopped 2025-03-31), The Diplomat Cambodia (last item 2026-05-27); broken XML: Kiripost, Fresh News English; HTTP 403: Fresh News Khmer; redirects to another feed: Khmer Times Khmer, Google News Khmer.

> **Adapting:** the topics and sources come from PLAN.md. To add a feed, add a line, run `uv run python -m natalia.feeds -n 0`, and check its robots.txt allows feeds if it's an aggregator. The collector picks it up on its next run.

## Verify it worked
```bash
uv run python -m natalia.feeds -n 0; echo "exit=$?"
```
Expected: `66/66 feeds working`, `exit=0`. Quiet feeds show `⚠️ stale` but still count as working.

<details><summary>Example from this build (2026-10-16 05:23 UTC)</summary>

```console
$ time uv run python -m natalia.feeds -n 0
topic           source                             pay  items  latest (UTC)      result
(…)
cambodia        CamboJA News                       no      10  2026-10-15 09:15  ✅
cambodia        VOD English                        no      10  2026-08-09 00:20  ⚠️ stale
cambodia        The Cambodia Daily                 no      20  2026-10-15 08:10  ✅
cambodia        Cambodia Investment Review         no      10  2026-10-16 02:04  ✅
cambodia        The Guardian Cambodia              no      20  2026-09-29 05:00  ⚠️ stale
cambodia        Post Khmer                         no      10  2026-10-16 04:48  ✅
cambodia        Kohsantepheap Daily                no       1  2026-10-15 08:29  ✅
cambodia        DAP News                           no      10  2026-10-16 05:11  ✅
cambodia        RFA Khmer                          no      27  2026-10-11 09:00  ✅
general         BBC News Top Stories               no      35  2026-10-16 05:05  ✅
general         NPR News                           no      10  2026-10-15 20:50  ✅
general         The Guardian International         no     114  2026-10-16 05:00  ✅
general         Sky News World                     no       7  2026-10-15 23:09  ✅

66/66 feeds working

real	1m23.545s
exit=0
```
**Result:** ✅ Post Khmer works again (it returned HTTP 500 in collection runs 3–6 on 2026-10-15). VOD English and The Guardian Cambodia stay enabled though quiet: cheap to keep, and the collector de-duplicates.
</details>
