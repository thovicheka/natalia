-- 0004: what kind of message each chat row was (task 1.9c).
--
-- 'chat': small talk, answered by the first LLM request alone (no search, no sources).
-- 'news': searched the stored articles, then a second request answered with sources.
-- NULL: rows from 1.9b (all news) and messages that failed before the first reply.
-- Still no message text: conversation memory lives in the bot's RAM only (natalia/chat.py).
ALTER TABLE chat_questions ADD COLUMN kind text;
