# Personal AI News Agent: Project Plan

## What I Want

A personal AI news agent that keeps me caught up every day on the topics I care about, without visiting dozens of websites. It collects the news, shows me the real articles, and summarizes and explains what happened and why it matters. I can read it, save it, and talk to it like a real conversation, in English or Khmer.

## Topics

1. Economics
2. World Politics
3. Technology
4. Science
5. Sport
6. Crypto
7. Stock Market & Trading (stocks, indices, commodities, forex), separate from crypto
8. Cambodia (anything in or related to Cambodia)
9. General / breaking news

## Example Sources

- Economics: Reuters, Bloomberg, Financial Times, The Economist, WSJ
- World Politics: Reuters, AP, BBC, Al Jazeera, Foreign Affairs
- Technology: Ars Technica, The Verge, TechCrunch, Wired, MIT Technology Review
- Science: Nature, Science Daily, Quanta, Scientific American
- Sport: ESPN, BBC Sport, The Athletic, Sky Sports
- Crypto: CoinDesk, Cointelegraph, The Block, Bloomberg Crypto
- Stock Market & Trading: Bloomberg, Reuters Markets, WSJ, Yahoo Finance, MarketWatch, TradingView
- Cambodia: Khmer Times, Phnom Penh Post, Cambodianess, VOD, CamboJA, Nikkei Asia / Reuters SE Asia

## Core Architecture: One Engine, Multiple Faces

Build the engine (the “brain”) once. Every interface plugs into the same engine.

Engine stages:

1. Collect: pull articles from sources and RSS feeds every day
2. Filter: keep only items matching my topics
3. Store: save articles in a database (PostgreSQL + pgvector)
4. Retrieve + Summarize/Explain: an LLM writes digests, answers questions, explains context

Conversation uses RAG (Retrieval-Augmented Generation): retrieve today’s stored news and give it to the LLM as context, so answers are grounded in real articles.

## News Output Format

Every news item includes:

- Headline
- Link to the original article
- Full detail
- PLUS an AI summary and explanation (“why it matters”)

The summary sits next to the source, never replaces it, so I can catch up fast and verify.

## Interface 1: Personal Website (for me, main interface)

- News feed in the format above
- Personal Library: save/bookmark articles into collections (Read Later, Important, by topic)
- Chat interface like Claude: real conversation with the agent about the news
- Build: Streamlit/Gradio for a quick version, React for the polished version

## Interface 2: Telegram Bot (mainly for family and friends)

Four ways to interact:

1. Commands: /economics, /crypto, /cambodia, /today, etc.
2. Text questions: ask naturally, it answers and explains
3. Voice: send a voice message, it transcribes, answers in text or voice
4. Real conversation: flowing back-and-forth chat with memory of recent messages (rolling window of the last several messages to control cost)

Two separate spaces (via Telegram group topics or a mode toggle):

- News: long, detailed items with headline, link, detail, summary
- Conversation: short, flowing dialogue with its own clean history

## Push and Pull

- Push: every morning (e.g. 7am), automatically send the daily digest
- Pull: anytime, ask via command, text, voice, or web chat

## Language Toggle: English / Khmer

- Toggle at the top switches everything between English and Khmer
- News, summaries, my input, and the agent’s replies all follow the chosen language
- News is collected once in its original language; only the output is translated
- Khmer text works well with modern LLMs; Khmer voice (speech-to-text, text-to-speech) is harder, so it comes in a later phase

## Build Phases

1. Daily digest: collect, filter, store, summarize, push morning digest
2. Conversation: RAG-based Q&A, Telegram commands, real conversation
3. Language toggle: English/Khmer for text
4. Voice: speech-to-text (Whisper) and optional voice replies, then Khmer voice
5. Personal website: feed, save/organize library, Claude-like chat

## Tech Stack

- Language: Python
- Feeds: feedparser, or FreshRSS/Miniflux as the collection layer
- Article cleaning: trafilatura
- Database: PostgreSQL + pgvector
- LLM: any API (OpenAI, Anthropic, Gemini) or a local model
- Telegram: python-telegram-bot
- Scheduling: GitHub Actions or cron
- Web UI: Streamlit/Gradio, later React
- Speech: Whisper for speech-to-text, a TTS engine for replies

## Open-Source Projects to Learn From

- al-strunova/ai-news-digest-agent: small, clean, scheduled digest (best starting point)
- frankzch/ai-news-brief: advanced filtering, scoring, deduplication
- FreshRSS / Miniflux: self-hosted feed collection
- haophancs/crypto-news-agent: crypto-focused agent with LLM assistant

## Project Name

Natalia, your personal AI news agent. English and Khmer.

## Summary

A daily AI news agent: one engine, two interfaces (personal website + Telegram), nine topics, real sources with AI summaries, real conversation, voice, and English/Khmer, built in phases so it stays finishable.
