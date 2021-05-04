PRAGMA foreign_keys = OFF;
BEGIN;
CREATE TABLE new_matches (
    name TEXT NOT NULL,
    guild INTEGER NOT NULL,
    message INTEGER NOT NULL UNIQUE,
    running INTEGER NOT NULL,
    result INTEGER NOT NULL,
    games INTEGER NOT NULL,
    team1 TEXT NOT NULL,
    team2 TEXT NOT NULL,
    tournament GUID NOT NULL,
    bestof INTEGER NOT NULL,
    PRIMARY KEY(name, tournament),
    FOREIGN KEY (team1, guild) REFERENCES teams (code, guild) ON UPDATE CASCADE,
    FOREIGN KEY (team2, guild) REFERENCES teams (code, guild) ON UPDATE CASCADE,
    FOREIGN KEY (tournament) REFERENCES tournaments (id) ON DELETE CASCADE
);
INSERT INTO new_matches
SELECT *
FROM matches;
DROP TABLE matches;
ALTER TABLE new_matches
    RENAME TO matches;
CREATE TABLE new_users_matches (
    user_id INTEGER NOT NULL,
    match_name TEXT NOT NULL,
    match_tournament GUID NOT NULL,
    team INTEGER NOT NULL,
    games INTEGER NOT NULL,
    PRIMARY KEY(user_id, match_name, match_tournament),
    FOREIGN KEY (user_id) REFERENCES users (id) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (match_name, match_tournament) REFERENCES matches (name, tournament) ON UPDATE CASCADE ON DELETE CASCADE
);
INSERT INTO new_users_matches
SELECT *
FROM users_matches;
DROP TABLE users_matches;
ALTER TABLE new_users_matches
    RENAME TO users_matches;
COMMIT;
PRAGMA foreign_keys = ON;
PRAGMA user_version = 1;