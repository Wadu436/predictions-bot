-- upgrade --
CREATE TABLE IF NOT EXISTS "team" (
    "id" UUID NOT NULL  PRIMARY KEY,
    "name" TEXT NOT NULL,
    "code" TEXT NOT NULL,
    "emoji" BIGINT NOT NULL,
    "guild" BIGINT NOT NULL,
    "fandom_overview_page" TEXT,
    CONSTRAINT "uid_team_code_86d298" UNIQUE ("code", "guild"),
    CONSTRAINT "uid_team_fandom__58bb11" UNIQUE ("fandom_overview_page", "guild")
);
CREATE TABLE IF NOT EXISTS "tournament" (
    "id" UUID NOT NULL  PRIMARY KEY,
    "name" TEXT NOT NULL,
    "channel" BIGINT NOT NULL,
    "guild" BIGINT NOT NULL,
    "message" BIGINT NOT NULL,
    "running" SMALLINT NOT NULL,
    "fandom_overview_page" TEXT,
    "updates_channel" BIGINT,
    "score_bo1_team" INT NOT NULL  DEFAULT 1,
    "score_bo3_team" INT NOT NULL  DEFAULT 2,
    "score_bo5_team" INT NOT NULL  DEFAULT 3,
    "score_bo3_games" INT NOT NULL  DEFAULT 1,
    "score_bo5_games" INT NOT NULL  DEFAULT 1,
    CONSTRAINT "uid_tournament_name_89ffc2" UNIQUE ("name", "guild")
);
COMMENT ON COLUMN "tournament"."running" IS 'ENDED: 0\nRUNNING: 1';
CREATE TABLE IF NOT EXISTS "match" (
    "id" UUID NOT NULL  PRIMARY KEY,
    "id_in_tournament" INT NOT NULL,
    "name" TEXT NOT NULL,
    "message" BIGINT NOT NULL UNIQUE,
    "running" SMALLINT NOT NULL,
    "result" INT NOT NULL  DEFAULT 0,
    "games" INT NOT NULL  DEFAULT 0,
    "bestof" INT NOT NULL  DEFAULT 0,
    "fandom_match_id" TEXT,
    "team1_id" UUID NOT NULL REFERENCES "team" ("id") ON DELETE CASCADE,
    "team2_id" UUID NOT NULL REFERENCES "team" ("id") ON DELETE CASCADE,
    "tournament_id" UUID NOT NULL REFERENCES "tournament" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_match_id_in_t_9702ad" UNIQUE ("id_in_tournament", "tournament_id"),
    CONSTRAINT "uid_match_tournam_191c1b" UNIQUE ("tournament_id", "fandom_match_id")
);
COMMENT ON COLUMN "match"."running" IS 'ENDED: 0\nRUNNING: 1\nCLOSED: 2';
CREATE TABLE IF NOT EXISTS "user" (
    "id" UUID NOT NULL  PRIMARY KEY,
    "discord_id" BIGINT NOT NULL UNIQUE,
    "name" TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS "prediction" (
    "id" UUID NOT NULL  PRIMARY KEY,
    "team" INT NOT NULL,
    "games" INT NOT NULL,
    "match_id" UUID NOT NULL REFERENCES "match" ("id") ON DELETE CASCADE,
    "user_id" UUID NOT NULL REFERENCES "user" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_prediction_user_id_c035e3" UNIQUE ("user_id", "match_id")
);
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(20) NOT NULL,
    "content" JSONB NOT NULL
);
