-- upgrade --
CREATE TABLE "tournament_tournament" ("tournament_rel_id" UUID NOT NULL REFERENCES "tournament" ("id") ON DELETE CASCADE,"tournament_id" UUID NOT NULL REFERENCES "tournament" ("id") ON DELETE CASCADE);
-- downgrade --
DROP TABLE IF EXISTS "tournament_tournament";
