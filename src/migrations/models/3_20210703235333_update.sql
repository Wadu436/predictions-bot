-- upgrade --
CREATE UNIQUE INDEX "uid_match_tournam_b56033" ON "match" ("tournament_id", "fandom_tab", "fandom_initialn_matchintab");
-- downgrade --
DROP INDEX "uid_match_tournam_b56033";
