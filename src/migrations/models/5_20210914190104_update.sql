-- upgrade --
ALTER TABLE "team" ADD "info" TEXT;
-- downgrade --
ALTER TABLE "team" DROP COLUMN "info";
