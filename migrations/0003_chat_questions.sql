-- 0003: chat questions (task 1.9b).
--
-- One row per question asked in Telegram chat, for the daily question cap and the cost record.
-- The question's text is NOT stored (nothing needs it yet; task 2.4's conversation memory will
-- decide how to keep history). A row is written before the LLM is called, so a question that
-- fails still counts toward the cap.
CREATE TABLE chat_questions (
    id             bigserial   PRIMARY KEY,
    chat_id        bigint      NOT NULL,
    asked_at       timestamptz NOT NULL DEFAULT now(),
    language       text        NOT NULL,            -- 'en' or 'km': the language answered in
    retrieved      integer     NOT NULL DEFAULT 0,  -- articles given to the LLM
    covered        boolean,                         -- the LLM's verdict; NULL if it failed
    source_ids     bigint[]    NOT NULL DEFAULT '{}',
    model          text,
    requests       integer     NOT NULL DEFAULT 0,
    input_tokens   integer     NOT NULL DEFAULT 0,
    output_tokens  integer     NOT NULL DEFAULT 0,  -- thinking included
    error          text
);
CREATE INDEX chat_questions_chat_day_idx ON chat_questions (chat_id, asked_at DESC);
