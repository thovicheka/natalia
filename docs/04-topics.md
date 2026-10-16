# Stage 4 — Topics and top stories

**Tasks:** 1.4 · **Status:** ✅ done (🧑: judge whether the picks look sensible)

**What you'll have working by the end:** every stored article tagged with all its topics (its feed's, plus keyword rules such as "mentions Cambodia"), and a command that picks the day's top 5 stories per topic, preferring stories several sites cover, recent ones and ones with full text. No LLM calls.

| Placeholder | In this build |
|---|---|
| `<date>` | `2026-10-16` |

## Prerequisites
- [Stage 3](03-collect.md): the collector has stored a day of articles.
- [Stage 2](02-database.md): the database, with migration `0002` applied (step 1).

## How it works

```
articles (feed topic) ──► tag: keyword rules add topics, headline script fixes language
                                  │
day window (24 h before 07:00 Asia/Phnom_Penh)
                                  ▼
group into stories (same news, different sites) ──► score ──► pick 5 per topic
```

- **Tagging** (`natalia/topics.py`, `RULES`): a topic is added when its words are in the headline, or twice in the feed's excerpt. Cambodia is wider ("anything in or related to Cambodia", PLAN.md): once in the excerpt or twice in the article text, in English or Khmer (កម្ពុជា, ភ្នំពេញ, province names, ហ៊ុន ម៉ាណែត…). Rules exist for cambodia, crypto, markets, economics, technology, science and sport; none for world-politics and general (their words, like "president" or "war", are everywhere). The rule-added topics are kept in `articles.rule_topics`, so changing a rule and re-running takes the old ones out cleanly.
- **Language:** the same pass sets `language` from the headline's script: some "English" feeds (Khmer Times) carry Khmer items.
- **Stories:** headlines from *different* sites are the same story when they share 3+ content words and those words carry half the weight of the shorter headline; a word weighs more the fewer of the day's headlines use it ("albania" more than "trump"). Each article's `also_seen` (sites whose identical headline the collector dropped) counts too.
- **Score:** +2.5 per extra site (up to 4), up to +1 for recency, +1 full text (or +0.3 excerpt), minus up to 4 for items that aren't news (puzzle hints, deal posts, analyst ratings, transcripts, listicles, obituaries, opinion columns, live blogs), and −4 under Cambodia for a Cambodian feed's item that doesn't mention Cambodia (Khmer feeds also carry world news).
- **Picking:** "general" (the day's headlines) picks first, then every (story, topic) pair in score order; on equal scores a feed topic beats a rule topic. Each story appears once, at most 2 stories per topic lead with the same site, and a story that plainly repeats one already picked is skipped. Why each choice: [decisions](decisions.md#top-stories-coverage-first-no-llm).

## Steps

### 1. Apply the migration
```bash
uv run python -m natalia.db migrate
```
*What it does:* adds `articles.rule_topics` (topics the rules added) and `articles.also_seen` (other sites with the same headline). Both are metadata-only changes with a constant default, so they're instant and don't block the collector.

<details><summary>Example from this build</summary>

```console
$ uv run python -m natalia.db migrate
applied: 0002_topic_rules_and_coverage
PostgreSQL 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1), pgvector 0.6.0
applied migrations: 0001_initial_schema, 0002_topic_rules_and_coverage
pending migrations: none
```
**Result:** ✅ (applied while a collection run was in progress; it wasn't affected)
</details>

### 2. Tag the articles
```bash
uv run python -m natalia.topics tag --all     # first time: every stored article
uv run python -m natalia.topics tag           # later: articles collected in the last 3 days
```
*What it does:* adds rule topics, fixes `language`, and prints how many articles gained each topic, with examples to check by eye. Running it again changes nothing.

> **If** a rule tags the wrong things (here: `quantum` put Bitcoin "post-quantum" stories under science), **fix the rule in `RULES` and run `tag --all` again**: the old rule topics are removed first, so the fix is clean.

<details><summary>Example from this build (2026-10-16)</summary>

```console
$ uv run python -m natalia.topics tag --all
articles checked: 1863, changed: 239
  economics       +76    -0
  technology      +118   -0
  science         +12    -0
  sport           +10    -0
  crypto          +3     -0
  markets         +33    -0
  language en->km: 3

added science, e.g.:
  Starknet opens vote on potential Ethereum L2 exit over quantum risks
  Things are finally looking up for NASA's first missions to Venus in a generation
  Researchers Build First Working Post-Quantum Defense for Bitcoin’s Lightning Network
  …
added markets, e.g.:
  Anthropic flags revenue surge to investors ahead of stock market debut
  Analysis: Why a $2 trillion deficit and 5% Treasury yields are becoming America's biggest economic challenge
  …
```
**Result:** ⚠️ `quantum` was too loose. **Fix:** removed it from the science rule, re-ran:
```console
$ uv run python -m natalia.topics tag --all
articles checked: 1863, changed: 5
  science         +0     -5
```
No article gained `cambodia`: a check for "cambodia / phnom penh / hun manet" anywhere in the other feeds' headlines, excerpts and text found **0** articles in those 3 days, so the rule had nothing to add (unit tests cover it).

After a new collection run (751 more articles):
```console
$ uv run python -m natalia.topics tag --all
articles checked: 2614, changed: 72
  economics       +21    -0
  technology      +44    -0
  …
$ /usr/bin/time -f "tag: %e s, max RSS %M KB" uv run python -m natalia.topics tag
tag: 1.63 s, max RSS 64376 KB
articles checked: 2614, changed: 0
```
**Result:** ✅ idempotent: the second run changes nothing.
</details>

### 3. Pick the day's top stories
```bash
uv run python -m natalia.topics top                  # today's digest window (until 07:00)
uv run python -m natalia.topics top --date <date> -v # another day, with each score explained
uv run python -m natalia.topics top --now            # the 24 h before now
```
*What it does:* prints 5 stories per topic: headline, source, time (Asia/Phnom_Penh), full text or excerpt, the sites covering it, and the link. `-v` adds the score's parts and the other articles in each story. Nothing is written: the digest (task 1.7) stores its picks.

> **If you see** the same news twice in different topics, **it means** its headlines were too different for the story grouping. The picking step's "same news" check catches the common case (the day's biggest story split in two); if one slips through, tighten `same_news()` in `natalia/topics.py`.

<details><summary>Example from this build (first try and fixes)</summary>

The first run picked well, but `-v` showed three problems:
- ❌ The Pakistan school collapse and the Ukraine refinery strikes each appeared twice. **Cause:** links from the (old, now disabled) Google News feeds all have the site `news.google.com`, so the Reuters and the New York Times copy couldn't join one story. **Fix:** for Google News links the site is the publisher in the headline's " - Reuters" suffix.
- ❌ Still twice, after that fix (general #1 and world-politics #3). **Cause:** word weights: on a day when many outlets cover a story, its own words (pakistan, school, roof) are common, so they weigh little. **Fix:** a plain check when picking (`same_news`: 4+ shared words, half the shorter headline).
- ❌ "White House defends new press secretary…" was picked under technology, because Wired was one of its three sites. **Fix:** a story takes its lead article's topics plus topics most of its articles share. On equal scores a feed topic beats a rule topic (so "Bitcoin wins the AI trade" goes to crypto, not technology).
- ❌ A Nepal floods story (wrongly grouped with Istanbul floods) was Cambodia #4. **Fix:** the "doesn't mention Cambodia" penalty raised from 2 to 4.
- ⚠️ An obituary was science #5. **Fix:** obituaries marked down.

Final run:
```console
$ /usr/bin/time -f "top: %e s, max RSS %M KB" uv run python -m natalia.topics top
window 10-15 07:00 → 10-16 07:00 Asia/Phnom_Penh: 1294 articles, 1201 stories
picked 45 stories, 36 covered by 2+ sites

== economics (5)
1. [ 6.25] UK economy unexpectedly grows in August despite fall in consumer spending
   The Guardian Economics · 10-15 13:04 · full · 3 site(s): bloomberg.com, ft.com, theguardian.com
2. [ 4.18] John Healey poised to raise taxes on banks in budget
3. [ 3.87] Healey says surprise UK growth is 'sign of resilience' ahead of Budget
4. [ 2.86] Oil prices slide as US weighs easing sanctions on 'shadow fleet' - Reuters
5. [ 1.97] I find it quite demoralising in store - why I do all my shopping online
== world-politics (5)
1. [11.11] North Korea and China open new bridge after 12-year delay
   BBC News World · 10-15 09:43 · full · 5 site(s): aljazeera.com, ap news, bbc.co.uk, france24.com, reuters
2. [ 8.90] Romania: 2 ships on fire in Black Sea, 7 crew missing
3. [ 8.81] Asian Cup in Saudi Arabia could be postponed by a year amid Houthi attacks
4. [ 6.83] Houthi attack on palace used by Yemen government in Aden kills five
5. [ 6.27] Police arrest US teen in alleged Illinois Hindu temple mass shooting plot
== technology (5)
1. [ 4.29] Bluesky expands its AI-powered Attie app to let anyone build websites, games, and more
2. [ 4.21] Meta built a huge open-weight AI model for Macs, but you'll need 1TB of RAM to run it
3. [ 3.91] Restrictions expose Ukraine's Starlink dependency in Russia war
4. [ 3.89] FTC subpoenas OpenAI and Anthropic following safety failures
5. [ 3.58] SK Hynix bargains for chip equipment exports to its China facility in return for building a factory …
== science (5)
1. [ 3.69] Musk says US government may be behind slowdown of Ukraine drone speeds
2. [ 2.80] Nearly half of reef-building coral species face higher risk of extinction
3. [ 1.97] Living with a stink? Technology might help
4. [ 1.83] NASA to Help Unlock Mysteries of Mars’ Moons in Upcoming Mission
5. [ 1.75] NASA Satellites Observe Historic 2026 El Niño
== sport (5)
1. [ 4.38] What would a 24-team College Football Playoff bracket look like?
2. [ 4.22] Blood clot rules Eagles QB Hurts out of Panthers game
3. [ 4.21] Amar'e Stoudemire graduates from law enforcement academy, will train as an officer
4. [ 4.12] Alex Scott quits Disney+ role as Women’s Champions League presenter
5. [ 4.11] Serbian tennis player handed 24-year ban for match-fixing
== crypto (5)
1. [ 4.08] Boom or Bust, Bitcoin Wins the AI Trade, Bitwise CIO Says
2. [ 4.00] Ledger Announces Atom Touchscreen Android Device
3. [ 3.93] Starknet opens vote on potential Ethereum L2 exit over quantum risks
4. [ 1.98] Australia releases draft bill to adopt OECD crypto tax reporting framework
5. [ 1.96] Brooklyn DA Pulls the Plug on Crypto Scam Network
== markets (5)
1. [ 4.02] Canada August manufacturing sales +1.5% vs +1.1% expected
2. [ 2.80] Why is Rocket Lab stock tumbling today?
3. [ 1.99] IEA agrees to release of outstanding 100 million barrels of oil
4. [ 1.98] Fed’s Goolsbee warns AI demand could keep inflation running hot
5. [ 1.96] People in China are spending nearly as much of their income as Americans on healthcare
== cambodia (5)
1. [ 6.13] Cambodia rejects Thai border claims at UN meeting
2. [ 3.72] Authorities tracking wild elephants after death of child
3. [ 2.91] Hun Manet: Cambodia supports transforming CICA into full-fledged international organization - Report
4. [ 2.67] Cambodia's Poultry Innovation Earns Global Recognition - Mirage News
5. [ 2.53] We support strengthening solidarity and defense cooperation among Vietnam, Laos, and Cambodia. - Vie…
== general (5)
1. [11.26] School roof collapses in northwestern Pakistan, killing at least 29 people
   Al Jazeera · 10-15 13:10 · full · 5 site(s): aljazeera.com, bbc.co.uk, france24.com, npr.org, reuters
2. [11.25] Ukraine to restart strikes on Russian oil refineries, Zelensky says
3. [ 9.25] Martinez apologises for outburst and fined by Man Utd
4. [ 5.38] Australia v New Zealand: men’s Rugby League World Cup – live
5. [ 4.21] Trump cancels plan to livestream execution after global condemnation
top: 1.08 s, max RSS 59744 KB
```
(source lines and links trimmed after the first of some topics). **Result:** ✅ 45 stories, each once, 36 of them covered by 2+ sites; 1.1 s, 60 MB.

Known weak spots, left as is: science and markets are thin (few free feeds give full text; single-site items score ~2); a feed's own editorial choice still counts (BBC's science feed carried a Ukraine/Starlink story; BBC's top stories carry football); three of Cambodia's picks are old Google News items (those feeds are now disabled, so this goes away with new data).
</details>

### 4. Tests
```bash
uv run pytest -q tests/test_topics.py
```
*What it does:* the rules on sample headlines (English, Khmer with zero-width spaces, words inside other words such as "said" or "whether"), language detection, story grouping (across sites only, Google News publishers), scoring, picking (5 per topic, each story once, general first, 2 per site), the day window, and against the real database (inside a rolled-back transaction): tagging is idempotent and fixes the language; top stories come from the right window.

<details><summary>Example from this build</summary>

```console
$ uv run pytest -q
101 passed in 0.95s
```
**Result:** ✅
</details>

## Verify it worked
```bash
uv run python -m natalia.topics tag | head -1
uv run python -m natalia.topics top | head -2
```
Expected: `changed: 0` right after a full tag, and a window line followed by `picked 45 stories, …` (fewer if a topic had a quiet day).
