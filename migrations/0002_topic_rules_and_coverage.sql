-- 0002: topic rules and coverage (task 1.4).
--
-- rule_topics: the topics that natalia/topics.py's keyword rules added to `topics` (on top of
-- the feed's). Kept apart so the rules can be changed and re-run: the old rule topics are taken
-- out of `topics` first, then the new ones added.
--
-- also_seen: other sites (host without "www.") that published the same headline, recorded by
-- the collector when it drops their copy as a duplicate. A story several sites cover ranks
-- higher in the daily top stories.
ALTER TABLE articles ADD COLUMN rule_topics topic[] NOT NULL DEFAULT '{}';
ALTER TABLE articles ADD COLUMN also_seen   text[]  NOT NULL DEFAULT '{}';
