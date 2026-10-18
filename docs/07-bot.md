# Stage 7 — Natalia's Telegram bot

**Tasks:** 1.8 · **Status:** 🧑 code and tests done; the bot itself (BotFather, token, chat ID, first message, service) is the human's

**What you'll have working by the end:** Natalia's own Telegram bot (not cloud-ai-lab's alert bot), running as a `systemd` service with long polling. It sends the stored digest to the owner's chat and answers the owner's `/start`, `/help` and `/digest [date]`. Anyone else gets one short refusal and nothing more. The commands make no LLM calls: they read digests that [Stage 6](06-digest.md) stored. Since task 1.9b, any other text from the owner is a question, answered by Haiku from the stored articles ([Stage 9](09-chat.md)); since 1.9c, small talk gets a friendly reply instead, follow-ups work, and `/forget` clears the conversation memory.

| Placeholder | In this build |
|---|---|
| `<bot-token>` | kept private (`TELEGRAM_BOT_TOKEN`) |
| `<chat-id>` | kept private (`TELEGRAM_OWNER_CHAT_ID`) |
| `<username>` | `thovicheka` |
| `<date>` | `2026-10-16` |

## Prerequisites
- [Stage 6](06-digest.md): a stored digest (with or without summaries).
- A Telegram account on your phone.

## How it works
- `natalia/bot.py`: `send` renders a stored digest as Telegram HTML (a header, then each topic's stories: **headline as a link**, *source · time*, the source's own words in a quote, then the AI summary and why it matters), packs it into as few messages as fit Telegram's 4,096-character limit, and sends them about one a second with link previews off. `run` is the long-polling bot.
- **Owner only** (until task 2.1's allowlist): every handler checks the chat ID; a stranger gets "Sorry, this is a private bot." once per run and nothing else (no LLM call, no data).
- **The token stays secret:** it's read from `.env` inside the process, never printed; `httpx` (which logs every request URL, token included, at INFO) is kept at WARNING. The unit file holds no secrets (unit files are world-readable).
- **Long polling, not a webhook:** only outgoing HTTPS, which the firewall allows; no open port, no public URL ([decisions](decisions.md#telegram-natalias-own-bot-not-the-labs-alert-bot)).

## Steps

### 1. 🧑 Create the bot *(on your phone or Telegram Desktop)*
1. Open a chat with **@BotFather**, send `/newbot`, give it a name (`Natalia`) and a username ending in `bot`.
2. BotFather replies with the token, `<bot-token>`. Treat it like a password.
3. Put it in `.env` *(on the server, in your own terminal, not through the agent)*: `nano ~/projects/natalia/.env`, set `TELEGRAM_BOT_TOKEN=<bot-token>`.

*What it does:* a new, separate bot, so its token can be revoked without touching the lab's alert bot.

### 2. 🧑 Find your chat ID
1. In Telegram, open your new bot and send `/start` (it won't answer yet: nothing is running).
2. *(On the server, in your own terminal)* read the bot's pending updates; the token stays in your shell:
   ```bash
   cd ~/projects/natalia
   set -a; . ./.env; set +a          # loads .env into this shell only; prints nothing
   curl -s "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getUpdates" | grep -o '"chat":{"id":[0-9-]*' | head -1
   ```
3. Put the number in `.env` as `TELEGRAM_OWNER_CHAT_ID=<chat-id>`.

*What it does:* `getUpdates` returns the `/start` you just sent, with your chat's ID. (Alternative: message **@userinfobot**.)

> **If** `getUpdates` prints nothing, **send the bot another message and run it again**: updates are kept only until something reads them, and stage 7's `run` drops old ones when it starts.

### 3. Preview the messages *(no token needed)*
```bash
uv run python -m natalia.bot send --dry-run --date <date>
```
*What it does:* prints the HTML messages the digest would be sent as, with their lengths. Nothing is sent.

<details><summary>Example from this build (the 2026-10-16 digest, summaries still pending)</summary>

```console
$ uv run python -m natalia.bot send --dry-run --date 2026-10-16
--- message 1/6 (3850 characters)
<b>📰 Natalia · Friday 16 October 2026</b>
45 stories (0 with summaries so far). The AI summary sits under each source: tap the headline to read it.

<b>━━ Top stories ━━</b>

<b>1. <a href="https://www.aljazeera.com/news/2026/10/15/school-roof-collapses-in-northwestern-pakistan-killing-at-least-29-people?traffic_source=rss">School roof collapses in northwestern Pakistan, killing at least 29 people</a></b>
<i>Al Jazeera · 15 Oct 15:30</i>
<blockquote>At least 28 students and one teacher killed in incident at Al-Khair Education Centre, a private school in Peshawar.</blockquote>
<i>Summary pending.</i>
…
--- message 2/6 (3834 characters)
--- message 3/6 (3623 characters)
--- message 4/6 (4001 characters)
--- message 5/6 (3770 characters)
--- message 6/6 (1940 characters)
```
**Result:** ✅ 6 messages for 45 stories. With summaries (~400 more characters each) expect about 10–11 messages a morning.
</details>

### 4. 🧑 Send yourself the digest once
```bash
uv run python -m natalia.bot send --date <date>
```
*What it does:* sends the stored digest to `TELEGRAM_OWNER_CHAT_ID` only. Expected: `sent the <date> digest: 6 messages` (or more, with summaries), and the messages in your chat.

> **If you see** `TELEGRAM_BOT_TOKEN is not set` or `TELEGRAM_OWNER_CHAT_ID is not set to a chat id`, **it means** `.env` still has the example values from `.env.example`. Do steps 1–2.

> **If you see** `Forbidden: bot can't initiate conversation with a user`, **it means** you haven't sent the bot `/start` yet. Do step 2.1.

<details><summary>Example from this build</summary>

Not run: creating the bot and sending messages are the human's steps. **Result:** ⏳
</details>

### 5. Try the bot in the foreground
```bash
uv run python -m natalia.bot run       # Ctrl+C to stop
```
Then, in Telegram: `/start`, `/digest` (yesterday's digest, then today's; a missing one gets "No digest stored for <date> yet." and the other is still sent), `/digest <date>` (that day only). From another account (a friend's phone), any message gets "Sorry, this is a private bot." once.

### 6. 🧑 Run it as a service
The service runs from a **runtime worktree** on `main` (as cloud-ai-lab's `lab-runtime` does), so switching branches in `~/projects/natalia` never changes what runs. Task 1.9 uses the same worktree for the daily flow.
```bash
# once (no sudo): the runtime worktree, its .venv and its .env
git -C ~/projects/natalia worktree add ~/projects/natalia-runtime main
cd ~/projects/natalia-runtime && uv sync --no-dev
cp ~/projects/natalia/.env ~/projects/natalia-runtime/.env && chmod 600 ~/projects/natalia-runtime/.env

# the service (sudo)
sudo cp ~/projects/natalia/deploy/natalia-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now natalia-bot
systemctl status natalia-bot --no-pager
```
*What it does:* starts the bot now and at every boot, restarts it 10 s after a crash, and caps it at `MemoryMax=200M` (`MemoryHigh=160M` starts reclaiming before that). Since task 1.9b: `MemoryHigh=450M`, `MemoryMax=550M`, for chat's search child ([Stage 9](09-chat.md) step 5). After a merge to `main`: `git -C ~/projects/natalia-runtime pull && sudo systemctl restart natalia-bot`.

> **If** `systemctl status` shows `status=203/EXEC`, **it means** the runtime's `.venv` is missing: run `uv sync --no-dev` in `~/projects/natalia-runtime`.

<details><summary>Example from this build</summary>

```console
$ systemd-analyze verify deploy/natalia-bot.service
natalia-bot.service: Command /home/thovicheka/projects/natalia-runtime/.venv/bin/python is not executable: No such file or directory
```
**Result:** ⚠️ the unit parses; the only complaint is the runtime worktree that doesn't exist yet (step 6's first block). Memory measured in-process (imports, app built with a fake token, the 2026-10-16 digest loaded and rendered, no network):
```console
python: (46.1, 46.1)
imports: (52.6, 52.6)
app built: (73.4, 73.4)
digest loaded and rendered (6 messages): (79.3, 79.3)
```
~80 MB, under the 200 MB budget. The live service's memory is the human's to record: `systemctl show natalia-bot -p MemoryCurrent -p MemoryPeak`.
</details>

### 7. Tests
```bash
uv run pytest -q tests/test_bot.py
```
*What it does:* HTML escaping (headlines, summaries, link quotes), source before summary, packing (limit respected, every block kept, oversized blocks cut at line ends), message order, sending (HTML, previews off, ~1 s apart), handlers (owner answered; a stranger refused once and nothing else; `/digest` with a date, a bad date, no digest), config (example values rejected without echoing them), quiet `httpx` logs, and building the app without network.

<details><summary>Example from this build</summary>

```console
$ uv run pytest -q
132 passed in 2.74s
```
**Result:** ✅
</details>

## Verify it worked
```bash
systemctl is-active natalia-bot
journalctl -u natalia-bot -n 5 --no-pager | grep -c "api.telegram.org/bot"   # must print 0
```
Expected: `active`, and `0` (no request URL, so no token, in the logs). Then `/digest` in Telegram returns yesterday's and today's digests.
