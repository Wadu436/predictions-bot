PRAGMA foreign_keys = OFF;
BEGIN;
CREATE TABLE new_tournaments (
    id GUID NOT NULL,
    name TEXT NOT NULL,
    channel INTEGER NOT NULL,
    guild INTEGER NOT NULL,
    message INTEGER NOT NULL,
    running INTEGER NOT NULL,
    PRIMARY KEY(id),
    UNIQUE(name, guild)
);
INSERT INTO new_tournaments
SELECT t.id, t.name, t.channel, m.guild,t.message, t.running FROM tournaments t INNER JOIN matches m on t.id = m.tournament GROUP BY t.id;
DROP TABLE tournaments;
ALTER TABLE new_tournaments
    RENAME TO tournaments;
COMMIT;
PRAGMA foreign_keys = ON;
PRAGMA user_version = 2;