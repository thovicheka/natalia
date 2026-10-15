-- 0001: Natalia's first schema (task 1.2).
-- Applied by `uv run python -m natalia.db migrate`, once, in one transaction.
--
-- pgvector is not a "trusted" extension, so the human creates it once as the postgres
-- superuser (see docs/STATUS.md, task 1.2). This line is then a no-op that documents the need
-- and fails loudly if the extension is missing.
CREATE EXTENSION IF NOT EXISTS vector;

-- The nine topics of docs/PLAN.md (same list as natalia/feeds.py TOPICS) and the two languages.
CREATE DOMAIN topic AS text CHECK (VALUE IN (
    'economics', 'world-politics', 'technology', 'science', 'sport',
    'crypto', 'markets', 'cambodia', 'general'
));
CREATE DOMAIN lang AS text CHECK (VALUE IN ('en', 'km'));

-- One row per feed in config/sources.yaml, matched by feed URL.
CREATE TABLE sources (
    id          integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text        NOT NULL,
    topic       topic       NOT NULL,
    feed_url    text        NOT NULL UNIQUE,
    language    lang        NOT NULL DEFAULT 'en',
    paywalled   boolean     NOT NULL DEFAULT false,
    enabled     boolean     NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- One row per story, deduplicated by canonical URL (unique) and normalized title (indexed).
-- source_id is the feed it was first seen in. Paywalled sources keep only the feed's
-- excerpt: `body` stays NULL for them (no scraping past a paywall).
-- topics: from the feed first, then rules (task 1.4); an article can have several.
CREATE TABLE articles (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id     integer     NOT NULL REFERENCES sources (id),
    url           text        NOT NULL UNIQUE,
    title         text        NOT NULL,
    title_norm    text        NOT NULL,
    excerpt       text,
    body          text,
    language      lang        NOT NULL,
    topics        topic[]     NOT NULL DEFAULT '{}',
    published_at  timestamptz,
    collected_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX articles_title_norm_idx   ON articles (title_norm);
CREATE INDEX articles_published_at_idx ON articles (published_at DESC);
CREATE INDEX articles_topics_idx       ON articles USING gin (topics);

-- One embedding per article, from the local model (multilingual-e5-small: 384 dimensions,
-- compared by cosine distance). Changing the model to another dimension needs a migration.
CREATE TABLE embeddings (
    article_id  bigint      PRIMARY KEY REFERENCES articles (id) ON DELETE CASCADE,
    model       text        NOT NULL,
    embedding   vector(384) NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX embeddings_hnsw_idx ON embeddings USING hnsw (embedding vector_cosine_ops);

-- The AI summary and "why it matters" for an article, one per output language (Phase 3 adds
-- Khmer). It sits next to the source, never replaces it: the article row keeps title + url.
CREATE TABLE summaries (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    article_id      bigint      NOT NULL REFERENCES articles (id) ON DELETE CASCADE,
    language        lang        NOT NULL,
    summary         text        NOT NULL,
    why_it_matters  text        NOT NULL,
    model           text        NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (article_id, language)
);

-- One digest per day and language, with the LLM use it cost (task 1.7 logs these).
CREATE TABLE digests (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    digest_date    date        NOT NULL,
    language       lang        NOT NULL DEFAULT 'en',
    model          text,
    requests       integer     NOT NULL DEFAULT 0,
    input_tokens   integer     NOT NULL DEFAULT 0,
    output_tokens  integer     NOT NULL DEFAULT 0,
    created_at     timestamptz NOT NULL DEFAULT now(),
    sent_at        timestamptz,
    UNIQUE (digest_date, language)
);

-- The articles in a digest, in order, per topic.
CREATE TABLE digest_items (
    digest_id   bigint  NOT NULL REFERENCES digests (id) ON DELETE CASCADE,
    topic       topic   NOT NULL,
    position    integer NOT NULL CHECK (position >= 1),
    article_id  bigint  NOT NULL REFERENCES articles (id),
    PRIMARY KEY (digest_id, topic, position),
    UNIQUE (digest_id, topic, article_id)
);
