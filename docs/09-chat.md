# Stage 9 — Chat in Telegram (a friendly assistant, and a news expert)

**Tasks:** 1.9b, 1.9c · **Status:** 1.9b ✅ live. 1.9c 🧑 code and tests done; the first real messages (paid, ~$0.0001–0.001 each) need the human's approval, then merge and a bot restart.

**What you'll have working by the end:** talk to the bot like a person, in English, Khmer or a mix. Natalia comes across as a normal, friendly person whose specialty is news. Small talk ("yo sup twin") gets a short, friendly reply in the same tone, with no news and no sources. A general question ("how do I fix my car's brakes?") gets a helpful answer from general knowledge, marked as not from the news. Ask about the news and it analyzes the stored articles (why it matters, related stories, how sources differ, what changed), with the sources it actually used (headline as a link, site, date). Current facts (prices, who holds a role, recent events) come only from the stored articles; if they don't cover it, it says so. Follow-ups like "tell me more" work, because it remembers the last 6 messages for 30 minutes. If you seem upset, it answers kindly and briefly. Owner only, at most 20 messages a day.

| Placeholder | In this build |
|---|---|
| `<question>` | `Bitcoin price this week` |
| `<chat-id>` | kept private (`TELEGRAM_OWNER_CHAT_ID`) |

## Prerequisites
- [Stage 5](05-embeddings.md): every article has a vector (the daily flow now embeds new ones, [Stage 8](08-daily-flow.md)).
- [Stage 6](06-digest.md): Claude Haiku through `natalia/llm.py`, `ANTHROPIC_API_KEY` in `.env`.
- [Stage 7](07-bot.md): the bot runs as a service from `~/projects/natalia-runtime`.

## How it works
```
owner's message ──► bot: owner? text? under 20 today? ──► count it (chat_questions: kind, tokens; no text)
                                    │
                                    ▼
   request 1 (small): last 6 messages + the new one ──► JSON {kind, reply, search}
          │                                   │
  kind = chat / general                   kind = news
          │                                   │
          ▼                                   ▼
   reply as written:          child process: embed `search` (local e5) ──► 8 nearest articles, 30 days
   no search, no sources;                     │   (~1 s, 332 MB, freed when it exits)
   general adds "General knowledge,           ▼
   not from today's news."    request 2: articles (oldest first) + last 6 messages + the question
                                         ──► JSON {covered, answer, source_ids}
                                              │
                                              ▼
                              the answer, then "Sources": only if covered, only the ids it used,
                              headline links from the database (made-up ids dropped)
          │                                   │
          └──────────► remember both messages (RAM, 30 min) ◄───┘
```
- **`natalia/chat.py`**:
  - **Personality (1.9c):** both prompts describe Natalia as a normal, friendly person whose specialty is news: collecting, analyzing and reporting it.
  - **Reply or search (1.9c):** the first request picks one of three kinds:
    - `chat`: small talk, greetings, jokes, thanks, questions about Natalia. A reply right there: one request, no search.
    - `general`: questions answered from lasting general knowledge (how-to, science, history, advice; "how do I fix my car's brakes?"). A helpful answer right there, then a fixed line: *ℹ️ General knowledge, not from today's news.* (Khmer: *នេះជាចំណេះដឹងទូទៅ មិនមែនមកពីព័ត៌មានថ្ងៃនេះទេ។*). The line is added by the code, so it can't be forgotten.
    - `news`: news and **current facts** (prices, scores, who holds a role now, recent events), or a follow-up on them. The prompt says Haiku's own knowledge of these is out of date, so they are always `news`, even when it thinks it knows. Chat and general replies must not state current facts either.
    For `news` it writes a **standalone search query** instead of a reply, with names filled in from the conversation ("tell me more" after Bitcoin → "Bitcoin price this week"). Without this step, every message was a news search: "yo sup twin" retrieved two Reuters stock pages and a motorbike story (step 2).
  - **Tone and language:** both prompts say to match the latest message: Khmer, English or the same mix, casual or formal, slang if they use it. The script count (`language()`) is only a hint in the prompt ("mostly Khmer") and picks the language of the fixed replies (cap, failure).
  - **Upset:** the reply prompt says to be kind and brief, with no jokes and no news, and to gently suggest talking to someone they trust; if they might hurt themselves or are in danger, to urge contacting local emergency services or someone near them. Nothing about it is logged: such a message is `kind=chat` like any other.
  - **Retrieval:** the search query is embedded with the same local model as the articles. The 8 nearest articles of the last 30 days are kept (cosine distance ≤ 0.25).
  - **The answer:** Haiku gets each article's headline, site, date and its first 1,200 characters, **oldest first**, plus the conversation. Facts come only from the articles; if they don't cover the question it says so instead of guessing. It **analyzes** rather than repeats, each only when the articles support it: why it matters, related stories among the articles, how different sources report it, what changed over the days. Its explanation may use general understanding (how markets usually react), never as a new fact. About 3 to 8 sentences. On a follow-up it adds new detail instead of repeating itself.
  - **Sources only when used (1.9c):** if the answer says the news doesn't cover the question, no sources are shown, whatever ids come back. 1.9b showed 3 sources under a "not covered" answer (bot log, 2026-10-17 16:28: `covered=False sources=3`).
- **Memory (1.9c):** `Memory` keeps the last 6 messages of each chat (3 of the owner's, 3 of Natalia's; each cut to 600 characters, plus up to 300 characters of the headlines a news answer cited). In the bot's RAM only: forgotten after 30 minutes without a message, or when the bot restarts. Never written to the database or the logs. Failed messages and messages over the cap aren't remembered.
- **Why a child process for the search:** the embedding model takes ~330 MB. Loaded in the bot, it would stay there all day. In a child (`python -m natalia.chat retrieve`), it's freed a second later. The query goes to the child on stdin, never on its command line (other users can read command lines with `ps`). One message is answered at a time, so only one child runs.
- **Haiku decides "covered", not a score cut-off.** e5's scores are bunched together: unrelated questions still score 0.79–0.81 against the best article, related ones 0.82–0.89 (measured, step 2). A hard cut-off would drop good articles, so the 0.25 distance only drops junk and the prompt tells Haiku to say when the articles don't answer.
- **Daily cap:** 20 messages per chat per day (Asia/Phnom_Penh), small talk included. A message counts before anything is sent, so failures count too. Over the cap: "That's 20 messages today, the daily limit. Talk to you tomorrow!"
- **Privacy:** no message text is stored; `chat_questions` keeps the chat id, time, language, kind (`chat` or `news`), how many articles were retrieved, covered or not, the source ids, and tokens. The messages go to Anthropic to be answered (that's the feature). Strangers still get only "Sorry, this is a private bot."
- **Cost** (Haiku 5.5: $0.10/M input, $0.50/M output; input tokens from the prompt sizes in step 8, at the 0.42 tokens per character measured in step 4; output tokens guessed):

  | Message | Requests | Input tokens | Output tokens | Cost |
  |---|---|---|---|---|
  | Small talk, no memory | 1 | ~1,000 | ~60 | ~$0.00013 |
  | Small talk, 6 messages remembered | 1 | ~1,500 | ~60 | ~$0.00018 |
  | General question (how-to), memory | 1 | ~1,500 | ~350 | ~$0.0003 |
  | News, no memory (1.9b measured: 1 request, 4,244 in + 185 out, $0.0005) | 2 | ~5,600 | ~380 | ~$0.00075 |
  | News, 6 messages remembered | 2 | ~6,600 | ~380 | ~$0.00085 |
  | News in Khmer, 6 Khmer messages remembered | 2 | ~8,000 | ~500 | ~$0.0011 |

  **What memory adds:** the 6 remembered messages are ~1,200 characters (~510 tokens) in English, sent once for chat and general replies and twice for news: **+$0.00005 to +$0.0001 per message**. Khmer takes ~2–3× the tokens, so up to ~+$0.0003. Other changes from 1.9b: the reply-or-search request (~$0.0001 per news question) and longer, analytical news answers (~+200 output tokens, ~+$0.0001). **At the cap:** 20 news questions with full memory ≈ $0.017 a day (Khmer ~$0.022), against $0.01 in 1.9b. A realistic day (5 news questions, 2 general, 10 small talk) ≈ $0.007, about $0.20 a month.

## Steps

### 1. Database table *(no sudo)*
```bash
uv run python -m natalia.db migrate
```
*What it does:* creates `chat_questions` (`migrations/0003_chat_questions.sql`, 1.9b) and adds its `kind` column (`0004_chat_kind.sql`, 1.9c: `chat` or `news`; empty for 1.9b's rows).

<details><summary>Example from this build</summary>

```console
$ uv run python -m natalia.db migrate
PostgreSQL 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1), pgvector 0.6.0
applied migrations: 0001_initial_schema, 0002_topic_rules_and_coverage, 0003_chat_questions
pending migrations: none
```
1.9c:
```console
$ uv run python -m natalia.db migrate
PostgreSQL 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1), pgvector 0.6.0
applied migrations: 0001_initial_schema, 0002_topic_rules_and_coverage, 0003_chat_questions, 0004_chat_kind
pending migrations: none
```
**Result:** ✅ both applied to the shared database (0004 only adds a nullable column; the 1.9b bot still running ignores it).
</details>

### 2. See what a question would retrieve *(free: local model, no LLM)*
```bash
uv run python -m natalia.chat ask "<question>" --dry-run
```
*What it does:* prints the reply-or-search prompt, then searches with the message itself (as if it were news) and prints the answer prompt. Nothing is sent, nothing is counted or remembered. Since 1.9c, the CLI takes several messages (`ask "<first>" "<follow-up>"`); a real run remembers them in order, like the bot.

<details><summary>Example from this build</summary>

```console
$ uv run python -m natalia.chat ask "Bitcoin price this week" --dry-run
Articles:

[2386] Bitcoin Tests $81,000 as Rate Hike Fears Linger After Hot Inflation Data
Source: Decrypt, 2026-10-15 18:48
Odds of an October Fed hike have climbed to 29% from 18% a week ago, and analysts see Bitcoin range-bound until the picture clears. …

[4337] Bitcoin price steadies around $82K after Fed’s Warsh avoids rate-hike hints
Source: Cointelegraph, 2026-10-16 22:45
…
```
9,425 characters (~2,400 tokens by characters ÷ 4; Claude's tokenizer counts ~1.7× that).

The scores behind the "Haiku decides" choice (`uv run python -m natalia.embeddings search "<question>" -k 4`, similarity = 1 − distance):
```console
== Bitcoin price this week
0.894 [en] Bitcoin Tests $81,000 as Rate Hike Fears Linger After Hot Inflation Data
0.885 [en] Bitcoin price steadies around $82K after Fed’s Warsh avoids rate-hike hints
== What is the recipe for chocolate cake?
0.799 [en] Cheese tart, corn salad, squash with ’nduja, radicchio salad: Joe Otway’s recipes for early autumn
0.792 [en] How to use stale bread to make a classic British pudding – recipe | Waste not
== How do I fix my car's brakes?
0.810 [en] Tesla turns to 50-year-old stunt technology as it tries to Roadster again
== តើមានព័ត៌មានអ្វីខ្លះអំពីកម្ពុជា?
0.860 [km] កម្ពុជាថា រូបភាព Al Jazeera ស្តីពី Long Bay កើតឡើងមុនយុទ្ធនាការបង្ក្រាបឧក្រិដ្ឋកម្មឆបោកអនឡាញ
0.853 [en] An Artist Reflects what Remains a Vital Part of Cambodia: Farming - Cambodianess
== ទីផ្សារភាគហ៊ុនថ្ងៃនេះ
0.848 [en] The rollout of 24-hour* trading
0.839 [en] The Grim Reaper Is Coming Earlier Than Ever for Memecoins
```
Small talk searched as news (1.9c, before the reply-or-search step):
```console
$ uv run python -m natalia.chat ask "yo sup twin" --dry-run
New message: yo sup twin
Articles:

[1304] T2V1n.F - Reuters
Source: Reuters Markets (Google News), 2026-10-15 02:12

[1251] SEBc.F - Reuters
Source: Reuters Markets (Google News), 2026-10-14 20:20

[2528] IN PICTURES: Short, sharp shocks for anarchic teen motorbike gang
…
> yo sup twin
kind=news, retrieved 8: [1304, 1251, 2528, 1248, 1267, 4708, 2261, 1496]
```
**Result:** ✅ related questions find the right articles (Bitcoin, Cambodia in Khmer). Small talk finds noise, which is why 1.9c lets the first request reply without searching. Unrelated ones score almost as high (0.79–0.81), so no cut-off can tell them apart; Haiku does. Khmer → English is the weak case ("stock market today" in Khmer found trading and memecoins): measured in [Stage 5](05-embeddings.md) (km→en hit@1 0.40).
</details>

### 3. The search child's memory and time *(free)*
```bash
echo "<question>" | /usr/bin/time -f "peak %M KB, %e s" uv run python -m natalia.chat retrieve
```
<details><summary>Example from this build</summary>

```console
[[2386, 0.1055], [4337, 0.1154], [304, 0.1155], [362, 0.1172], [263, 0.1175], [658, 0.1177], [289, 0.1177], [2326, 0.1211]]
peak 339840 KB, 1.15 s
```
**Result:** ✅ 332 MiB for ~1 s, then freed. With the bot (~80 MB), ~410 MB at the peak: over the bot's old `MemoryMax=200M`, hence step 5.
</details>

### 4. 🧑 Ask one real question *(paid: ~$0.001)*
```bash
uv run python -m natalia.chat ask "<question>"
```
*What it does:* the same path as the bot, as the owner: counts toward today's 20, retrieves, asks Haiku once, prints the reply (Telegram HTML) and its tokens.

<details><summary>Example from this build</summary>

Run by the human on 2026-10-17:
```console
$ uv run python -m natalia.chat ask "Bitcoin price this week"
retrieved 8 articles: [2386, 4337, 304, 362, 263, 658, 289, 2326]
This week Bitcoin has mostly traded between about $80,000 and $84,000. It dipped to lows near $79,800 to $80,400 on Thursday October 15 after hot U.S. inflation data, then recovered to near $82,000 on Friday October 16. Bitcoin was down about 2.5% to 3% over the past week as of mid-week, and one analyst expects it to trade between $76,000 and $83,000 for the rest of October.

<b>Sources</b>
1. <a href="https://cointelegraph.com/markets/bitcoin-price-steadies-82k-fed-warsh-avoids-rate-hike-hints">Bitcoin price steadies around $82K after Fed’s Warsh avoids rate-hike hints</a> <i>(Cointelegraph · 16 Oct)</i>
2. <a href="https://bitcoinmagazine.com/markets/bitcoin-price-briefly-dips-below-80000">Bitcoin Briefly Slides Below $80,000 On More Hot Inflation Data</a> <i>(Bitcoin Magazine · 15 Oct)</i>
…
5. <a href="https://cointelegraph.com/markets/bitcoin-dips-korea-kospi-lowest-close-since-april">Bitcoin dips to $80.1K as KOSPI closes at its lowest since April</a> <i>(Cointelegraph · 15 Oct)</i>

covered=True, 5 sources, 1 requests, 4244 in + 185 out tokens, 4.7 s
```
The row it left in `chat_questions` (no question text):
```console
(37, 2026-10-17 16:15:24 UTC, 'en', 8, True, [4337, 2326, 263, 2386, 289], 'claude-haiku-5-5', 1, 4244, 185, None)
```
**Result:** ✅ answered from 5 of the 8 articles, every source a stored article. **Cost:** 4,244 × $0.10/M + 185 × $0.50/M = **$0.0005**, half the estimate; at the cap, ~$0.01 a day.
</details>

### 5. 🧑 Update the runtime and raise the memory caps *(sudo, after merging)*
```bash
git -C ~/projects/natalia-runtime pull
```
```bash
sudo cp ~/projects/natalia/deploy/natalia-bot.service ~/projects/natalia/deploy/natalia-worker.service /etc/systemd/system/
```
```bash
sudo systemctl daemon-reload
```
```bash
sudo systemctl restart natalia-bot natalia-worker
```
```bash
systemctl show natalia-bot natalia-worker -p Id -p MemoryHigh -p MemoryMax
```
*What it does:* brings the chat code to the runtime (no new packages; the table is already in the shared database, step 1). The bot's caps go from 160M/200M to **450M/550M** (the search child), the worker's from 450M/600M to **600M/700M** (the embed step, [Stage 8](08-daily-flow.md)). Expected: `MemoryHigh=471859200 MemoryMax=576716800` for the bot, `MemoryHigh=629145600 MemoryMax=734003200` for the worker. Don't restart the worker while a flow run is in progress.

**Pull only after `task/1.9b-chat` is merged:** the runtime follows `main`. Pulled before the merge, it stays on the old code and the bot keeps answering text with "questions come in a later version".

<details><summary>Example from this build</summary>

```console
$ git -C ~/projects/natalia-runtime pull --ff-only origin main
Updating df6fcbc..091e9cc
Fast-forward
 deploy/natalia-worker.service |   2 +-
 docs/08-daily-flow.md         | 157 ++++
 docs/ROADMAP.md               |   7 ++++-
 docs/STATUS.md                |  66 +++++
$ systemctl show natalia-bot natalia-worker -p Id -p MemoryHigh -p MemoryMax
MemoryHigh=471859200
MemoryMax=576716800
Id=natalia-bot.service

MemoryHigh=629145600
MemoryMax=734003200
Id=natalia-worker.service
```
In Telegram, "yo sup twin", "you cant speak english or sum ?" and "How do I fix my car's brakes?" each got: *I only know /digest and /help for now; questions come in a later version.*

**Result:** ✅ caps installed (copied from the working repo, which was on the branch). ❌ chat not live. **Cause:** the pull ran before the merge, so the runtime got `091e9cc` (main, without 1.9b) and the restarted bot is the 1.8 bot. **Fix:** merge `task/1.9b-chat`, then pull the runtime again and restart the bot (no `sudo` for the pull; the restart does).
</details>

### 6. 🧑 Ask the bot
In Telegram, send a question (no `/`). Expected: "typing…", then within ~5–10 s the answer and its sources. Try one in Khmer, and one the news can't answer ("How do I fix my car's brakes?"): it should say the stored news doesn't cover it.
```bash
journalctl -u natalia-bot -n 20 --no-pager | grep "chat:"
```
*Expected:* one line per message: `chat: kind=news lang=en retrieved=8 covered=True sources=3 requests=2 tokens=…` (1.9b's lines have no `kind` or `requests`). The message's text is never logged.

<details><summary>Example from this build (1.9b, the bot's first questions)</summary>

```console
$ journalctl -u natalia-bot -n 30 --no-pager | grep "chat:"
… natalia.bot INFO chat: lang=en retrieved=8 covered=False sources=3 tokens=2018+125
… natalia.bot INFO chat: lang=en retrieved=8 covered=False sources=0 tokens=3733+128
```
**Result:** ✅ answered. ❌ the first reply said the news didn't cover the question but still listed 3 sources. **Cause:** the prompt asked for "the ids you used", and Haiku listed the articles it had looked at. **Fix (1.9c):** no sources when `covered` is false, and the prompt asks only for articles whose facts are in the answer.
</details>

### 7. 🧑 Talk to it (1.9c) *(paid: ~$0.0001–0.001 a message)*
```bash
uv run python -m natalia.chat ask "yo sup twin" "Bitcoin price this week" "tell me more" "How do I fix my car's brakes?" "Who is the prime minister of Japan right now?" "ugh today was rough"
```
*What it does:* six messages as the owner, in order, with memory. Expected:
1. A short casual reply with no sources (`kind=chat`, 1 request).
2. A news answer that analyzes (why it matters, how sources differ, what changed over the days), with sources (`kind=news`, 2 requests).
3. More Bitcoin detail without repeating, its search query filled in from the conversation.
4. Practical brake advice ending with "ℹ️ General knowledge, not from today's news." (`kind=general`, 1 request).
5. `kind=news`: from the stored articles if they cover it, otherwise "the stored news doesn't cover that", never a guess.
6. A kind, brief reply with no news.

About $0.003 in all; 6 of today's 20. Then in Telegram, after the merge and `sudo systemctl restart natalia-bot`: a Khmer message, a Khmer–English mix, and a news question the stored articles can't answer (no sources).

<details><summary>Example from this build</summary>

Not run yet: waiting for the human's approval of the first real 1.9c call. **Result:** ⏳
</details>

### 8. Prompt sizes for the cost estimate *(free, no LLM)*
The characters of each prompt (system + message), with six remembered messages from a realistic chat (small talk, the Bitcoin answer with its sources, a follow-up):

<details><summary>Example from this build</summary>

```console
reply system 1717 chars, news system 957 chars, full history 1211 chars
reply prompt, no history: 1742
reply prompt, full history: 2953
answer prompt, no history: 10314; full history: 11514
```
After the personality, general-knowledge and analysis rules (same script):
```console
reply system 2345 chars, news system 1550 chars, full history 1211 chars
reply prompt, no history: 2370
reply prompt, full history: 3581
answer prompt, no history: 10907; full history: 12107
```
**Result:** ✅ the 1.9b question measured 4,244 tokens for ~10,200 characters, 0.42 tokens per character; the cost table above uses that. The history adds ~1,200 characters per request; the new rules ~600 characters per prompt (~250 tokens, ~$0.000025).
</details>

### 9. Tests
```bash
uv run pytest -q tests/test_chat.py tests/test_bot.py
```
*What it does:* language detection; HTML escaping and numbered sources; the prompts, with the conversation oldest first;
small talk answered in one request with no search and no sources (stored as `kind=chat`); a general question answered in one request with the "not from today's news" line (English and Khmer, stored as `kind=general`), and no such line on small talk; an unknown kind treated as chat; the news prompt's rules (facts only from the articles, analysis, don't guess); articles listed oldest first; an empty reply is a "sorry"; a news query falling back to the message; "not covered" listing no sources even when ids come back; the reply prompt's tone, language and distress rules; memory (last N per chat, chats kept apart, forgotten when idle, long messages cut, failures and over-cap messages not remembered, nothing in the database); a follow-up whose prompts carry the previous exchange and its headlines; the bot's log line without the message's text; answers from retrieved articles only with made-up ids dropped; a Khmer question asking for a Khmer answer; no LLM call when nothing is retrieved; the row recorded without the question's text; the cap (failures count, nothing runs over the cap, resets the next local day); retrieval and LLM failures and a non-JSON reply becoming a "sorry"; the date and distance filter on real pgvector rows; the question passed on stdin, never in the child's arguments; in the bot, typing then an HTML reply, long answers split, photos and unknown commands, a stranger never reaching chat. Retrieval and the LLM are fakes; database tests roll back.

## Verify it worked
- "hi" gets a friendly reply with no sources; "how do I fix my car's brakes?" gets advice marked as general knowledge; a news question gets an analysis with linked sources, in its language; "tell me more" continues it; a current fact the articles don't cover gets "not in the stored news".
- `SELECT kind, count(*), sum(requests), sum(input_tokens), sum(output_tokens) FROM chat_questions WHERE asked_at > now() - interval '1 day' GROUP BY kind;` matches what you sent.
- `systemctl show natalia-bot -p MemoryPeak` stays under 550M.
