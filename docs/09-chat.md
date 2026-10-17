# Stage 9 — Chat in Telegram (answers from the stored news)

**Tasks:** 1.9b · **Status:** 🧑 code and tests done; the first real questions (paid, ~$0.001 each) and the new memory caps (`sudo`) are the human's

**What you'll have working by the end:** send the bot any text message, in English or Khmer, and it answers in the same language from the articles Natalia has stored, with the sources it used (headline as a link, site, date). If the stored news doesn't cover the question, it says so instead of guessing. Owner only, at most 20 questions a day.

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
owner's message ──► bot: owner? text? under 20 today? ──► count it (chat_questions, no text)
                                    │
                                    ▼
        child process: embed the question (local e5 model) ──► 8 nearest articles, last 30 days
                                    │         (~1 s, 332 MB, freed when it exits)
                                    ▼
        one Haiku request: the articles + the question ──► JSON {covered, answer, source_ids}
                                    │
                                    ▼
        reply: the answer, then "Sources": headline links from the database (ids it made up are dropped)
```
- **`natalia/chat.py`**:
  - **Language:** Khmer if the question is mostly Khmer script, otherwise English. The answer is asked for in that language; headlines stay as published.
  - **Retrieval:** the question is embedded with the same local model as the articles. The 8 nearest articles of the last 30 days are kept (cosine distance ≤ 0.25).
  - **The answer:** Haiku gets each article's headline, site, date and its first 1,200 characters. It answers only from them and says which it used; the sources come from the database, never from the reply.
- **Why a child process for the search:** the embedding model takes ~330 MB. Loaded in the bot, it would stay there all day. In a child (`python -m natalia.chat retrieve`), it's freed a second later. The question goes to the child on stdin, never on its command line (other users can read command lines with `ps`). One question is answered at a time, so only one child runs.
- **Haiku decides "covered", not a score cut-off.** e5's scores are bunched together: unrelated questions still score 0.79–0.81 against the best article, related ones 0.82–0.89 (measured, step 2). A hard cut-off would drop good articles, so the 0.25 distance only drops junk and the prompt tells Haiku to say when the articles don't answer.
- **Daily cap:** 20 questions per chat per day (Asia/Phnom_Penh). A question counts before anything is sent, so failures count too. Over the cap: "That's 20 questions today, the daily limit."
- **Privacy:** the question's text is not stored; `chat_questions` keeps the chat id, time, language, how many articles were retrieved, covered or not, the source ids, and tokens. The question itself goes to Anthropic to be answered (that's the feature). Strangers still get only "Sorry, this is a private bot."
- **Cost:** ~4,000 input tokens (8 articles) + a few hundred output tokens ≈ **$0.001 a question**; at the cap, ~$0.02 a day.

## Steps

### 1. Database table *(no sudo)*
```bash
uv run python -m natalia.db migrate
```
*What it does:* creates `chat_questions` (`migrations/0003_chat_questions.sql`).

<details><summary>Example from this build</summary>

```console
$ uv run python -m natalia.db migrate
PostgreSQL 16.15 (Ubuntu 16.15-0ubuntu0.24.04.1), pgvector 0.6.0
applied migrations: 0001_initial_schema, 0002_topic_rules_and_coverage, 0003_chat_questions
pending migrations: none
```
**Result:** ✅
</details>

### 2. See what a question would retrieve *(free: local model, no LLM)*
```bash
uv run python -m natalia.chat ask "<question>" --dry-run
```
*What it does:* runs the search child and prints the prompt Haiku would get. Nothing is sent, nothing is counted.

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
**Result:** ✅ related questions find the right articles (Bitcoin, Cambodia in Khmer). Unrelated ones score almost as high (0.79–0.81), so no cut-off can tell them apart; Haiku does. Khmer → English is the weak case ("stock market today" in Khmer found trading and memecoins): measured in [Stage 5](05-embeddings.md) (km→en hit@1 0.40).
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

Not run yet: waiting for the human's approval of the first real call. **Result:** ⏳
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

### 6. 🧑 Ask the bot
In Telegram, send a question (no `/`). Expected: "typing…", then within ~5–10 s the answer and its sources. Try one in Khmer, and one the news can't answer ("How do I fix my car's brakes?"): it should say the stored news doesn't cover it.
```bash
journalctl -u natalia-bot -n 20 --no-pager | grep "chat:"
```
*Expected:* one line per question: `chat: lang=en retrieved=8 covered=True sources=3 tokens=…`. The question's text is never logged.

### 7. Tests
```bash
uv run pytest -q tests/test_chat.py tests/test_bot.py
```
*What it does:* language detection; HTML escaping and numbered sources; the prompt; answers from retrieved articles only with made-up ids dropped; a Khmer question asking for a Khmer answer; no LLM call when nothing is retrieved; the row recorded without the question's text; the cap (failures count, nothing runs over the cap, resets the next local day); retrieval and LLM failures and a non-JSON reply becoming a "sorry"; the date and distance filter on real pgvector rows; the question passed on stdin, never in the child's arguments; in the bot, typing then an HTML reply, long answers split, photos and unknown commands, a stranger never reaching chat. Retrieval and the LLM are fakes; database tests roll back.

## Verify it worked
- A question in Telegram gets an answer with linked sources, in its language.
- `SELECT count(*), sum(input_tokens), sum(output_tokens) FROM chat_questions WHERE asked_at > now() - interval '1 day';` matches what you asked.
- `systemctl show natalia-bot -p MemoryPeak` stays under 550M.
