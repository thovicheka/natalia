# Documentation style guide

How every doc in this repo is written, so they all read the same way: clear, consistent, and usable by someone who isn't the author. Adapted from cloud-ai-lab's `docs/STYLE.md`, for Natalia.

---

## 1. The README is the front door

Within about 30 seconds, a reader should be able to:
- understand what Natalia is and who it's for,
- see the architecture diagram,
- jump to the stage doc they need.

Keep it short. Detail belongs in the stage docs.

## 2. Three kinds of docs, three jobs

| Doc | Job | Who writes it, when |
|---|---|---|
| `docs/STATUS.md` | The live log: every step of every task as it happened, in order, including dead ends. What's done, blocked, and waiting on the human. | The agent, after every step. |
| `docs/NN-<stage>.md` (stage docs) | The clean, reusable guide: how to build this stage again, with the real output and the real problems from this build. | The agent, when a task finishes, from its STATUS.md record. |
| [`decisions.md`](decisions.md) | Why each tool or rule was picked, and what it was picked over. | Whoever makes or changes a decision. |

**After each task, update the matching stage doc, not only STATUS.md.** STATUS.md says what happened; the stage doc says how to do it. A reader rebuilding Natalia should never need STATUS.md.

Which doc a task goes into:

| Tasks | Stage doc |
|---|---|
| 0.1, 0.2, 0.4, 1.6 (repo, rules, deny-rule check, Python, Gemini key) | [`00-project-setup.md`](00-project-setup.md) |
| 1.1 (feeds) | [`01-sources.md`](01-sources.md) |
| 1.2 (PostgreSQL + pgvector) | [`02-database.md`](02-database.md) |
| 1.3 (collector) | [`03-collect.md`](03-collect.md) |
| 1.4 (topics and top stories) | `04-topics.md` |
| 1.5 (embeddings) | `05-embeddings.md` |
| 1.7 (LLM wrapper, summaries, digest) | `06-digest.md` |
| 1.8 (Telegram bot) | `07-bot.md` |
| 1.9 (daily flow on Prefect) | `08-daily-flow.md` |
| 1.9b (chat in Telegram) | `09-chat.md` (its embed step and memory: `08-daily-flow.md`) |
| 1.9c (natural chat) | `09-chat.md` |
| Later tasks | the doc the task names with `→` in [`ROADMAP.md`](ROADMAP.md); if it names none, a new doc with the next free number. Docs are numbered by build stage, in build order (the human's decision, 2026-10-16); a phase's "Document" task completes its stage docs instead of writing a separate phase doc. Ask the human if unsure. |

A task that changes an earlier stage (e.g. 1.3 disabling feeds from 1.1) also updates that earlier doc.

## 3. Every stage doc has the same shape

Use this order, every time:

1. **What you'll have working by the end** — one or two sentences stating the goal.
2. **Prerequisites** — what must already be done or installed (link earlier stages).
3. **Steps** — numbered, each with real copy-paste commands and a one-line "what this does."
4. **Verify it worked** — a short check with the exact output to expect.

Under the title, add a **Tasks** line (the ROADMAP IDs the doc covers) and a **Status** line (✅ done / ⏳ in progress / 🧑 waiting on the human).

Throughout the steps, add **troubleshooting notes** wherever a step broke or commonly breaks:

> **If you see** `connection to server ... failed: Connection refused`, **it means** PostgreSQL isn't installed or isn't running. Do step 2, then `systemctl status postgresql@16-main`.

Mark who runs each step when it matters: **🧑** for the human (anything with `sudo`, accounts, keys, money, approvals), **🤖** for the agent. A 🧑 step's commands are written so the human can paste them as is.

Copy-ready template:

````markdown
# Stage N — <Title>

**Tasks:** <ROADMAP IDs> · **Status:** ✅ done

**What you'll have working by the end:** <goal>

| Placeholder | In this build |
|---|---|
| `<username>` | `thovicheka` |

## Prerequisites
- <stage or tool>

## Steps

### 1. <Action>
```bash
<command>
```
*What it does:* <one line>

> **If you see** `<error>`, **it means** <cause>. <fix>.

<details><summary>Example from this build</summary>

```console
$ <command as run>
<real output, trimmed with … if long>
```
**Result:** ✅
</details>

## Verify it worked
```bash
<check command>
```
Expected: `<output>`
````

## 4. Keep the "why" separate from the "how"

- Stage docs say **how**. Keep them clean and skimmable.
- Reasoning, trade-offs, and rejected alternatives go in [`decisions.md`](decisions.md).
- If a step needs context, link to the matching section in `decisions.md` instead of explaining inline.

## 5. Write for someone who isn't you

- Spell out what felt obvious in the moment: how long a command takes, what a scary-looking prompt means, which terminal to run it in.
- Add **adaptation notes** so the docs work as a template, not a copy of one setup:

> **Adapting:** on a server with 8 GB of RAM, `shared_buffers = 128MB` (PostgreSQL's default) is fine; everything else is the same.

- Say where each command runs when it isn't obvious: *(on the server, in `~/projects/natalia`)* / *(in your browser)* / *(in your own terminal, not through the agent)*. The last one matters for anything that touches `.env` or a password: the agent's terminal output ends up in its chat.

## 6. Placeholders in instructions, real examples after them

- **Instructions** use placeholders so anyone can follow them: `<username>`, `<github-username>`, `<server-name>`, `<db-password>`, `<chat-id>`. Each doc lists them at the top with the values used in this build.
- **After key steps**, add a collapsible **Example from this build** block with the real commands and real output: actual paths, feed names, counts, timings, and the actual errors hit.
- **Every step records its outcome.** Each example block shows, in order:
  1. the **command** that was run,
  2. its **real output** (trimmed with `…` if long),
  3. **Result:** ✅ success or ❌ failure (⚠️ for "worked, but…"),
  4. if it failed: the **error**, its **cause**, and the **fix** that worked, followed by the successful re-run.
  Failed attempts stay in the docs; they're the most useful part for the next reader.
- Output comes from STATUS.md's records or from a real run. Never write output that wasn't seen. If the human ran a step and reported it in words, say so ("reported by the human") instead of inventing a transcript.
- **Comment commands inline** (`# what this line does`) when the purpose isn't obvious.

## 7. Mask everything private

- **Never** show real secrets, IP addresses (other than `127.0.0.1`), emails, Telegram chat IDs or tokens, or database passwords, even in examples. Mask them: `GEMINI_API_KEY=AIza***`, `postgresql://natalia:***@127.0.0.1:5432/natalia`, `<server-ip>`, `<chat-id>`.
- Secrets live in `.env` (git-ignored, `chmod 600`) on the server only. Every key has a fake-value line in `.env.example`.
- Never put a command in a doc that prints `.env` or a password to the screen. Load values into a shell variable or a program instead.
- News headlines and article text are public and fine to quote; family and friends' messages to the bot are not (see CLAUDE.md rule 10).

## 8. Document right after finishing a task

- Update the stage doc as soon as the task works, while the errors are fresh.
- Real mistakes make the best troubleshooting notes. Include them.
- Tick checklist items only after they've actually been done and verified.

---

## Small conventions

- Commands in fenced code blocks with a language (`bash`, `yaml`, `sql`, …); real output in `console` blocks. One action per block where possible.
- Headings in sentence case; stage docs numbered (`00-project-setup.md`, `01-sources.md`, …).
- Khmer text is quoted as is (UTF-8), never transliterated.
- Times: the server runs in UTC, the human lives in `Asia/Phnom_Penh` (UTC+7). Say which: "07:00 Asia/Phnom_Penh", "10:19 UTC".
- Screenshots only for web-console steps (e.g. AI Studio, @BotFather), saved in `docs/images/`. Never screenshot terminal commands; write them as text so they can be copied.
- Prices, quotas and versions change: date them or say "check the current numbers."
