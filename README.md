# natalia

Natalia is a personal AI news agent that gathers, summarizes and explains the day's news, in English and Khmer.

Every day it collects news on nine topics (economics, world politics, technology, science, sport, crypto, markets, Cambodia, general) from real sources and stores it. Next to each article it writes an AI summary and a "why it matters". The source always stays: headline, link and detail. People reach it through a Telegram bot (the owner, family and friends) and a personal website (the owner only), and can ask it questions and talk to it. One engine, several interfaces.

> **Status:** being built in phases ([roadmap](docs/ROADMAP.md), [live status](docs/STATUS.md)). ✅ Project setup, feeds, database and collector are done: 66 feeds, 1,863 articles stored, each story once. Next: topic filtering, local embeddings, the morning digest on Telegram.

---

## How it fits together

```
  News sites (RSS/Atom feeds, public pages)
              │  collect: feeds + article text where allowed
              ▼                (robots.txt respected, paywalls never bypassed)
 ┌──────────────── shared server (2 vCPU / 4 GB, Tailscale-only) ────────────────┐
 │                                                                               │
 │  Prefect (lab's server,       ──05:00 Asia/Phnom_Penh──►  natalia-daily flow  │
 │   Natalia's pool "natalia")                               collect → filter →  │
 │                                                           store → summarize   │
 │                                                           (alert on failure)  │
 │                                                                │              │
 │  PostgreSQL + pgvector  ◄──── articles, embeddings, summaries ─┘              │
 │        ▲            ▲                                                         │
 │        │            │      local embedding model (CPU)                        │
 │  Telegram bot    website (Streamlit, later React)                             │
 │  (long polling)  (Tailscale only)                                             │
 └───────┬───────────────┬─────────────────────────────────┬─────────────────────┘
         │               │                                 │ news text and questions only
         ▼               ▼                                 ▼
  owner, family,    owner's laptop / phone          Google Gemini Flash (free tier)
  friends           on Tailscale                    summaries, explanations, answers
```

| Part | Tool | Role |
|---|---|---|
| Feeds | `feedparser`, `config/sources.yaml` | 87 feeds listed, 66 enabled; paywalled ones give headline + excerpt + link only |
| Article text | `trafilatura` | full text where robots.txt and the site allow it |
| Database | PostgreSQL 16 + pgvector | articles, embeddings, summaries, digests; localhost only |
| Embeddings | `multilingual-e5-small`, int8, ONNX Runtime on CPU (measured in 1.5) | search across English and Khmer, without an API |
| LLM | Gemini Flash, free tier, via `google-genai` | summaries, "why it matters", answers; all calls through `natalia/llm.py` |
| Scheduling | cloud-ai-lab's self-hosted Prefect, Natalia's own pool and worker | the daily build at 05:00 Asia/Phnom_Penh |
| Telegram | Natalia's own bot, long polling | push digest, commands, questions, conversation |
| Website | Streamlit, later React | feed, personal library, chat; reachable only over Tailscale |

Design rules:
- **The AI summary sits next to the source, never replaces it.**
- **Never scrape past a paywall; respect robots.txt.**
- **No private data to the LLM.** The Gemini free tier may use prompts to improve Google's models; news is fine, secrets and personal notes are not.
- **No money spent without the human's approval.** Agents work on branches; the human reviews and merges.
- **Secrets live only in `.env` on the server**, never in git.

---

## Docs

| Doc | What's in it |
|---|---|
| [docs/00-project-setup.md](docs/00-project-setup.md) ✅ | Repo, agent rules, Python setup, guardrails, Gemini key |
| [docs/01-sources.md](docs/01-sources.md) ✅ | The feed list and how it was checked |
| [docs/02-database.md](docs/02-database.md) ✅ | PostgreSQL + pgvector install, tuning, schema, memory |
| [docs/03-collect.md](docs/03-collect.md) ✅ | The collector, its politeness rules, real runs and problems |
| [docs/04-topics.md](docs/04-topics.md) ✅ | Topic rules and the day's top 5 stories per topic |
| [docs/05-embeddings.md](docs/05-embeddings.md) 🧑 | The local embedding model: memory, speed and quality measured |
| [docs/06-digest.md](docs/06-digest.md) 🧑 | The LLM wrapper, summaries and the daily digest ([first digest](docs/digests/2026-10-16.md)) |
| [docs/07-bot.md](docs/07-bot.md) 🧑 | Natalia's Telegram bot: sending the digest, owner-only commands, the service |
| [docs/08-daily-flow.md](docs/08-daily-flow.md) 🧑 | The daily build on Prefect: Natalia's pool and worker, the 05:00 schedule, alerts |
| [docs/PLAN.md](docs/PLAN.md) | What Natalia should do (the source of truth for features) |
| [docs/ROADMAP.md](docs/ROADMAP.md) | The task list for humans and agents, and the decisions made |
| [docs/STATUS.md](docs/STATUS.md) | Live progress: every step of every task, with real output |
| [docs/decisions.md](docs/decisions.md) | Why each tool and rule was chosen, and the alternatives |
| [docs/STYLE.md](docs/STYLE.md) | How these docs are written |
| [docs/TASK-TEMPLATE.md](docs/TASK-TEMPLATE.md) | How to give an agent one task |
| [CLAUDE.md](CLAUDE.md) | Rules for AI agents working in this repo |

Natalia shares a server, and its Prefect server, with [cloud-ai-lab](https://github.com/thovicheka/cloud-ai-lab); everything else (repo, `.env`, database, bot) is its own.
