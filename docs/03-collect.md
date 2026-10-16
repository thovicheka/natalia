# Stage 3 — Collect and clean

**Tasks:** 1.3 · **Status:** ✅ done

**What you'll have working by the end:** `uv run python -m natalia.collect` reads every enabled feed, drops old items and duplicates, extracts the article text where that's allowed, and stores each story once in PostgreSQL, as full text or as headline + excerpt + link. Running it again stores nothing twice, and one failing feed doesn't stop the others. A run with little new to fetch takes 20–40 s and peaks around 100 MB.

| Placeholder | In this build |
|---|---|
| `<feed-name>` | part of a feed's `name`, e.g. `CamboJA News` |
| user agent | `natalia/0.1 (personal news reader)` |

## Prerequisites
- [Stage 1](01-sources.md): `config/sources.yaml`.
- [Stage 2](02-database.md): PostgreSQL with the schema, `DATABASE_URL` in `.env`.

## How it works

1. **Sources:** `config/sources.yaml` is upserted into `sources` by feed URL on every run. A feed removed from the file is disabled, not deleted (articles point to it).
2. **Feeds:** each enabled feed is read with `feedparser`; entries older than 48 h are dropped. Order: free feeds first, then paywalled ones, so when one story is in several feeds, the stored copy is the one that can have full text.
3. **Duplicates** (against the database and within the run):
   - **canonical URL:** lowercase host, https, no fragment, no tracking parameters (`utm_*`, `fbclid`, `at_*`, `oc`…), sorted query, no trailing slash;
   - **headline:** lowercase, no punctuation, " - Publisher" suffix removed; an **exact** match merges always, a **near-identical** one (similarity ≥ 0.9, 5+ words, last 3 days) only when it comes from a **different site** ([why](decisions.md#headline-duplicates-near-identical-only-across-sites)).
   - A duplicate from another topic's feed adds its topic to the stored article's `topics`.
4. **Not news:** stock-ticker pages ("`(ORK.HA) | Stock Price & Latest News - Reuters`") are dropped.
5. **Full text, only when all of these hold:** the source isn't paywalled; the site isn't on `EXCERPT_ONLY_DOMAINS` (Reuters, AP and the paywalled sites); the link isn't a Google News redirect; robots.txt allows the page (checked on every redirect hop); the page is HTML with no `"isAccessibleForFree": false` marker; `trafilatura` extracts ≥ 300 characters. Otherwise the article keeps the feed's headline + excerpt + link. Paywalled pages are never requested ([why](decisions.md#paywalls-headline--excerpt--link-only)).

**Politeness rules** ([why](decisions.md#robotstxt-respected-for-pages-and-feeds-google-news-dropped)):

| Rule | Value |
|---|---|
| User agent | `natalia/0.1 (personal news reader)`; robots.txt rules matched for `natalia` |
| robots.txt | checked for every page and every redirect hop; every enabled feed is allowed by its site's robots.txt |
| Timeout, size cap | 15 s, 3 MB |
| Per site | one request at a time, ≥ 1 s apart (more if robots.txt sets `Crawl-delay`; above 30 s, no page fetches) |
| At once | at most 4 sites |
| Refusals | a site that refuses (401/403/405/429) or times out twice isn't asked again that run |

## Steps

### 1. Add the text extractor
```bash
uv add trafilatura
```
*What it does:* `trafilatura` pulls the article text out of a page's HTML (brings `lxml`, `justext`, `htmldate`, `courlan`).

<details><summary>Example from this build</summary>

```console
$ uv add trafilatura
 + lxml==6.1.3
 + trafilatura==2.3.1
 (+ courlan, dateparser, htmldate, justext, lxml-html-clean, …)
```
**Result:** ✅
</details>

### 2. Smoke test: one feed, twice
```bash
uv run python -m natalia.collect --feed "<feed-name>"
uv run python -m natalia.collect --feed "<feed-name>"
```
*What it does:* `--feed` limits the run to feeds whose name contains the text. The second run must store nothing. Other options: `--no-text` (excerpts only, fetch no pages), `--max-age-hours 48`.

<details><summary>Example from this build</summary>

```console
$ uv run python -m natalia.collect --feed "CamboJA News"
feeds done: 5 new articles to store
cambodia            1    0      10     5      0        0      5     5       0
run time 7 s, 7 HTTP requests, peak memory (max RSS) 64 MB
$ uv run python -m natalia.collect --feed "CamboJA News"
feeds done: 0 new articles to store
cambodia            1    0      10     5      5        0      0     0       0
run time 1 s, 1 HTTP requests, peak memory (max RSS) 46 MB
```
**Result:** ✅ 5 stored with full text (4–9 k characters each), 5 too old; the second run found 5 URL duplicates and stored nothing.
</details>

### 3. Tests
```bash
uv run pytest -q
```
*What it does:* `tests/test_collect.py` runs with no network: a fake fetcher serves feeds, pages and robots.txt from memory and records every URL requested. It covers URL canonicalization, headline normalization (Khmer marks kept), near-identical headlines (including the real wrong merges of step 7), junk headlines, robots.txt (disallow, 403, 404, redirects, crawl delay), refusals, extraction (full, paywall marker, not HTML, too short, network error), and a whole run twice against the real database, rolled back.

> **If you see** `assert [',', 'a', 'a...'c', 'c', ...] == ['cambodia', 'economics']`, **it means** psycopg returned the `topic[]` domain array as a string. Read it as `topics::text[]`.

<details><summary>Example from this build</summary>

```console
$ uv run pytest -q
FAILED tests/test_collect.py::test_collect_twice_stores_each_article_once
E       AssertionError: assert [',', 'a', 'a...'c', 'c', ...] == ['cambodia', 'economics']
```
**Result:** ❌ → fixed (cast to `text[]` in the test). Final: `67 passed`.
</details>

### 4. First full run, and why it was slow
```bash
/usr/bin/time -v uv run python -m natalia.collect
```
*What it does:* collects every enabled feed and prints a per-site progress line, then a report: per topic, entries, too old, URL and headline duplicates, stored, full text, excerpt-only; why articles are excerpt-only; run time, HTTP requests and peak memory. `/usr/bin/time -v` adds the true peak memory ("Maximum resident set size").

<details><summary>Example from this build: run 1 (74 feeds, including 10 Google News feeds)</summary>

```console
$ /usr/bin/time -v uv run python -m natalia.collect
feeds done: 1719 new articles to store
topic           feeds fail entries   old dupURL dupTitle stored  full excerpt
economics           9    0     581   365     32        3    181    49     132
world-politics      9    0     366    21    167        4    174    97      77
technology          6    0     131    19      4        2    106    23      83
science             9    0     309   146      7        2    154    42     112
sport               5    0     275    37     18        1    219   115     104
crypto              6    0     121     7      0        0    114    93      21
markets             9    0     311    41      5       16    249    61     188
cambodia           14    0     448   254      5       27    162    65      97
general             7    0     400    25     10        5    360   109     251
TOTAL              74    0    2942   915    248       60   1719   654    1065

excerpt-only, why:
    514  Google News link (not followed: robots.txt)
    413  paywalled source
     58  HTTP 403
     26  robots.txt disallows
     25  too little text on page
     20  HTTP 405
      9  paywall marker on page

run time 1373 s, 897 HTTP requests, peak memory (max RSS) 162 MB
	Elapsed (wall clock) time (h:mm:ss or m:ss): 22:52.99
	Maximum resident set size (kbytes): 166160
	Exit status: 0
```
**Result:** ⚠️ correct, but **22.9 minutes** for 897 requests. Timing single requests showed two causes:
- **Slow refusing sites.** A site that refuses still answers slowly (a Phys.org 403 took 32 s) and was asked again for every queued article (29 for Phys.org). **Fix:** a site that refuses (401/403/405/429) or times out twice isn't asked again that run. Politer, too.
- **NPR's user-agent stall** (next step).

Guardian and BBC pages took ~1 s each, so the 1 s per-site gap was not the problem.
</details>

> **If** a run takes many minutes, **look at** the per-site progress lines: a site with many queued articles and `0/N full text` is refusing. The refusal cut-off handles it.

### 5. The user agent: NPR stalls anything with "robots" in it
The first user agent was browser-like (`Mozilla/5.0 (compatible; …)`); NPR's front end stalled it, so NPR's robots.txt timed out (15 s) and was read as "disallow all". The next try, `natalia/0.1 (personal news reader; respects robots.txt)`, stalled too.

<details><summary>Example from this build</summary>

```console
UA only   TimeoutError 10.0s      # natalia/0.1 (personal news reader; respects robots.txt)
short UA  200 0.1s                # natalia/0.1
natalia/0.1 personal-news-reader       200 0.1s
natalia/0.1 (personal news reader)     200 0.0s
```
**Result:** ❌ → fixed: NPR's bot rules catch the word "robots". Final user agent: **`natalia/0.1 (personal news reader)`**, defined once in `natalia/feeds.py` and shared by the collector. A side-by-side check of one article per free site (34 sites) gave the same status codes for the browser-like and the honest user agent, so nothing else changed, and from run 5 NPR served full text.
</details>

> **If you see** one site's robots.txt or pages time out while `curl` gets them in a second, **it means** the site's bot filter dislikes your user agent. Try shorter variants, as above; keep it honest.

### 6. Run it twice: no duplicates; junk found
<details><summary>Example from this build: runs 2 and 3</summary>

Run 2 (with the refusal cut-off):
```console
feeds done: 112 new articles to store
  www.investing.com: 0/10 full text, 2 s
  www.theguardian.com: 5/5 full text, 7 s
  phys.org: 0/1 full text, 2 s
  (…)
TOTAL              74    0    2939   924   1831       72    112    22      90
run time 85 s, 120 HTTP requests, peak memory (max RSS) 125 MB
```
Headlines stored twice (SQL): **0**. The 112 new rows were new feed items: Google News search feeds returned a different 100 of the day's matches on each fetch (60 of the 112 came from them).

**Result:** ✅ no duplicates. ❌ **found junk:** 99 stored rows were Reuters stock-quote pages from Google News (`3ZV.MU - Reuters`, `(ORK.HA) | Stock Price & Latest News - Reuters`). **Fix:** a junk-headline rule, checked against all 1,836 stored titles: it matches exactly those 99 and nothing else. The 99 rows were deleted later, with the human's approval (`99 deleted`).

Run 3 (junk filter), with one feed failing:
```console
feeds done: 14 new articles to store
TOTAL              74    1    2859   937   1856       52     14     0      14
not news, dropped (stock-quote pages): 90
feed errors:
  Post Khmer: HTTP 500
run time 136 s, 84 HTTP requests, peak memory (max RSS) 68 MB
```
**Result:** ✅ Post Khmer's server error didn't stop the other 73 feeds.
</details>

### 7. Google News: disallowed by robots.txt, so disabled
Reuters and AP have no public RSS, so 1.1 reached them through Google News search feeds. Their links (`news.google.com/rss/articles/CBMi…`) are redirects, and the ids no longer contain the article URL.

<details><summary>Example from this build</summary>

```console
$ curl -s -A "natalia" https://news.google.com/robots.txt | head -14
User-agent: *
Disallow: /
Allow: /$
Allow: /?
Allow: /home$
(…)
Allow: /topics/
Allow: /publications/
Allow: /stories/
```
`/rss/articles/` (the redirect) and `/rss/search` (the feeds) are both disallowed. Of 935 Google News links in run 1, 0 could be decoded offline (all new-style ids). They were stored with the Google link as headline + excerpt, and run 4 spent most of its 182 s waiting on Google: the 10 feeds share one site, so they're fetched one by one, and an uncached search took 18–48 s on Google's side.

**Result:** ⚠️ → decided by the human: **all 10 Google News feeds disabled** ([why](decisions.md#robotstxt-respected-for-pages-and-feeds-google-news-dropped)). Engadget and Rest of World were added to technology instead (see [stage 1](01-sources.md#6-changes-made-in-task-13-the-humans-decisions-2026-10-15)). Run 5 then took 35 s.
</details>

### 8. False headline duplicates, and the fix
The near-identical rule (similarity ≥ 0.9) merged real rewordings across outlets, but in run 5 it also merged two different articles from the same site.

<details><summary>Example from this build: run 5 (66 feeds, no Google News)</summary>

```console
$ /usr/bin/time -v uv run python -m natalia.collect
feeds done: 76 new articles to store
  www.theguardian.com: 5/5 full text, 6 s
  restofworld.org: 2/2 full text, 2 s
  www.bbc.co.uk: 8/8 full text, 8 s
  www.npr.org: 1/1 full text, 1 s
  www.engadget.com: 20/20 full text, 21 s
  (…)
TOTAL              66    1    2021   751   1181       13     76    43      33
near-identical headlines dropped (new -> kept), first few:
  'uk threatens to ban eritreans over returns policy'
    -> 'uk threatens to ban eritreans over migrant return policy'
  'connections sports edition today hints and answers for oct 14 2026 puz'
    -> 'connections sports edition today hints and answers for oct 15 2026 puz'
  'the 9 best movies to stream this month october 2026'
    -> 'the 9 best tv shows to stream this month october 2026'
feed errors:
  Post Khmer: HTTP 500
run time 35 s, 136 HTTP requests, peak memory (max RSS) 91 MB
```
**Result:** ❌ the first merge is right (BBC and The Guardian, one story); the other two are wrong: The Athletic's puzzle hints for Oct 14 into Oct 15's, and Wired's "best movies" into "best TV shows". Both wrong pairs came from one site each: a series of similar posts, not one story.

**Fix** (the human's decision): exact headline matches merge from any site; near-identical ones only when the **sites differ** (`site_of`: the host without `www.`; "site", not "feed", so two feeds of one site count as one). Tests: the Wired and Athletic pairs (each first asserted ≥ 0.9 similar, so the old rule would merge them) stay apart; the BBC/Guardian pair still merges; exact matches from one site still merge.

Run 6, with the fix:
```console
feeds done: 23 new articles to store
TOTAL              66    1    2023   753   1234       13     23     5      18
near-identical headlines dropped (new -> kept), first few:
  'uk threatens to ban eritreans over returns policy'
    -> 'uk threatens to ban eritreans over migrant return policy'
run time 22 s, 89 HTTP requests, peak memory (max RSS) 104 MB
```
In the database:
```console
('The 9 Best TV Shows to Stream This Month (October 2026)', 'Wired', False, 10:42:32)
('The 9 Best Movies to Stream This Month (October 2026)', 'Wired', False, 11:23:43)
('Connections: Sports Edition today: Hints and answers for Oct. 15, 2026, puzzle No. 752', 'The Athletic', False, 10:42:32)
('Connections: Sports Edition today: Hints and answers for Oct. 14, 2026, puzzle No. 751', 'The Athletic', False, 11:23:43)
dup title_norm: 0 | total: (1863, 732)
```
(columns: title, source, has full text, collected at UTC)

**Result:** ✅ both wrongly dropped articles restored (as headline + excerpt: Wired and The Athletic are paywalled); the cross-source pair still merges; no headline stored twice.
</details>

## Real runs (2026-10-15)

| Run | Code | Feeds | Stored | Full | Excerpt | Dup URL | Dup headline | Not news | Time | HTTP requests | Peak RSS |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | first version | 74 | 1,719 | 654 | 1,065 | 248 | 60 | – | **1,373 s** | 897 | 166 MB |
| 2 | + refusal cut-off | 74 | 112 | 22 | 90 | 1,831 | 72 | – | 85 s | 120 | 128 MB |
| 3 | + junk filter | 74 | 14 | 0 | 14 | 1,856 | 52 | 90 | 136 s | 84 | 69 MB |
| 4 | final user agent | 74 | 13 | 3 | 10 | 1,855 | 54 | 87 | 182 s | 87 | 88 MB |
| 5 | Google News off, + Engadget, Rest of World | 66 | 76 | 43 | 33 | 1,181 | 13 | 0 | 35 s | 136 | 91 MB |
| 6 | cross-site-only near-duplicates | 66 | 23 | 5 | 18 | 1,234 | 13 | – | 22 s | 89 | 104 MB |

Peak RSS is `/usr/bin/time -v`'s "Maximum resident set size". The daily flow's budget is ≤ 700 MB. Runs 2–6 had little new to fetch; a cold run with today's code is estimated at ~6–7 minutes (the longest queue is ~160 Guardian pages at ~2.4 s each), to be confirmed by the first 07:00 run (task 1.9).

**Sites that refuse full text** (kept as headline + excerpt + link): Ars Technica (HTTP 405); Phys.org, The Block, Investing.com, Sky News (HTTP 403). Reuters and AP never get a page request.

> **Adapting:** to keep a source as excerpt-only without marking it paywalled, add its domain to `EXCERPT_ONLY_DOMAINS` in `natalia/collect.py`.

## Verify it worked
```bash
cd ~/projects/natalia
uv run python -m natalia.collect          # twice in a row: the second stores (almost) nothing
uv run python -c "
from natalia import db
with db.connect() as c:
    print('articles, full text, Khmer:', c.execute(\"select count(*), count(body), count(*) filter (where language='km') from articles\").fetchone())
    print('headlines stored twice:', c.execute('select count(*) from (select title_norm from articles group by title_norm having count(*) > 1) x').fetchone()[0])
"
```
Expected: the report ends with `run time …`, exit 0 even if a feed fails (listed under `feed errors:`), and **0** headlines stored twice. A second run right after the first stores only items published in between.

<details><summary>Example from this build (2026-10-16, database check only)</summary>

```console
articles, full text, Khmer: (1863, 732, 22)
headlines stored twice: 0
```
**Result:** ✅ 1,863 articles, 732 with full text, 22 in Khmer; 66 of 87 sources enabled.
</details>

## Later changes
- **Task 1.4:** when the collector drops an identical or near-identical headline from another site, it now records that site in the kept article's `also_seen` (migration `0002`). The top-stories score counts those sites as coverage. Test: `test_collect_twice_stores_each_article_once` checks `also_seen == ["other.test"]` after both runs. See [Stage 4](04-topics.md).
- **Run 7 (2026-10-16, before 1.4's tagging):** 66 feeds, 0 failed, 2,064 entries → 751 stored (439 full text, 312 excerpt-only), 482 URL and 9 headline duplicates, 879 s, 598 HTTP requests, peak 152 MB. The slow part was full text from a few sites (The Guardian 85 articles in 487 s, France 24 in 406 s, DW in 220 s), one request at a time per site.
