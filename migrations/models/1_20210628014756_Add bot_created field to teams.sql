-- upgrade --
ALTER TABLE "team" ADD "bot_created" BOOL NOT NULL  DEFAULT False;
-- downgrade --
ALTER TABLE "team" DROP COLUMN "bot_created";
