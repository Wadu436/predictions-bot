CREATE TABLE teams (
    name TEXT NOT NULL,
    code TEXT NOT NULL,
    emoji TEXT NOT NULL,
    guild bigint NOT NULL,
    PRIMARY KEY(code, guild)
);
CREATE TABLE users (
    id bigint NOT NULL,
    name TEXT NOT NULL,
    PRIMARY KEY(id)
);
CREATE TABLE tournaments (
    id UUID NOT NULL,
    name TEXT NOT NULL,
    channel bigint NOT NULL,
    guild bigint NOT NULL,
    message bigint NOT NULL,
    running INTEGER NOT NULL,
    PRIMARY KEY(id),
    UNIQUE(name, guild)
);
CREATE TABLE matches (
    name TEXT NOT NULL,
    guild bigint NOT NULL,
    message bigint NOT NULL UNIQUE,
    running INTEGER NOT NULL,
    result INTEGER NOT NULL,
    games INTEGER NOT NULL,
    team1 TEXT NOT NULL,
    team2 TEXT NOT NULL,
    tournament UUID NOT NULL,
    bestof INTEGER NOT NULL,
    PRIMARY KEY(name, tournament),
    FOREIGN KEY (team1, guild) REFERENCES teams (code, guild) ON UPDATE CASCADE,
    FOREIGN KEY (team2, guild) REFERENCES teams (code, guild) ON UPDATE CASCADE,
    FOREIGN KEY (tournament) REFERENCES tournaments (id) ON DELETE CASCADE
);
CREATE TABLE users_matches (
    user_id bigint NOT NULL,
    match_name TEXT NOT NULL,
    match_tournament UUID NOT NULL,
    team INTEGER NOT NULL,
    games INTEGER NOT NULL,
    PRIMARY KEY(user_id, match_name, match_tournament),
    FOREIGN KEY (user_id) REFERENCES users (id) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (match_name, match_tournament) REFERENCES matches (name, tournament) ON UPDATE CASCADE ON DELETE CASCADE
);