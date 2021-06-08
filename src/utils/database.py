import math
import uuid
from dataclasses import dataclass, field
from typing import Optional

import asyncpg

import config


@dataclass
class Team:
    name: str
    code: str
    emoji: str
    guild: int
    isfandom: bool = False
    fandomName: str = None


@dataclass
class User:
    id: int
    name: str


@dataclass
class Tournament:
    id: uuid.UUID
    name: str
    channel: int
    guild: int
    message: int
    running: int
    isfandom: bool = False
    fandomOverviewPage: str = None
    updatesChannel: int = None


@dataclass
class Match:
    def __post_init__(self):
        self.win_games = math.ceil(self.bestof / 2)
        self.lose_games = self.games - self.win_games

    id: int
    name: str
    guild: int
    message: int
    running: bool
    result: int
    games: int
    team1: str
    team2: str
    tournament: uuid.UUID
    bestof: int
    win_games: int = field(init=False)
    lose_games: int = field(init=False)
    fandomMatchId: str = None


@dataclass
class UserMatch:
    user_id: int
    match_id: int
    match_tournament: uuid.UUID
    team: int
    games: int


class Database:
    # Team-related queries
    @staticmethod
    async def insert_team(team: Team) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "INSERT INTO teams VALUES ($1, $2, $3, $4, $5, $6);",
            team.name,
            team.code,
            team.emoji,
            team.guild,
            team.isfandom,
            team.fandomOverviewPage,
        )
        await db.close()

    @staticmethod
    async def get_team(code: str, guild: int) -> Optional[Team]:
        db = await asyncpg.connect(config.postgres)
        tr = await db.fetchrow(
            "SELECT * FROM teams WHERE code=$1 AND guild=$2",
            code,
            guild,
        )
        await db.close()
        if tr is not None:
            return Team(tr[0], tr[1], tr[2], tr[3], tr[4], tr[5])

    @staticmethod
    async def get_teams_by_guild(guild: int) -> list[Team]:
        db = await asyncpg.connect(config.postgres)
        records = await db.fetch("SELECT * FROM teams WHERE guild=$1", guild)
        teams: list[Team] = []
        for tr in records:
            teams.append(Team(tr[0], tr[1], tr[2], tr[3], tr[4], tr[5]))
        await db.close()
        return teams

    @staticmethod
    async def update_team(original_code, team: Team) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "UPDATE teams SET name=$1, code=$2, emoji=$3, isfandom=$6, fandomName=$7 WHERE code=$4 AND guild=$5;",
            team.name,
            team.code,
            team.emoji,
            original_code,
            team.guild,
            team.isfandom,
            team.fandomName,
        )
        await db.close()

    @staticmethod
    async def delete_team(team: Team) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "DELETE FROM teams WHERE code=$1 AND guild=$2;",
            team.code,
            team.guild,
        )
        await db.close()

    # Tournament-related queries
    @staticmethod
    async def insert_tournament(tournament: Tournament) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "INSERT INTO tournaments VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9);",
            tournament.id,
            tournament.name,
            tournament.channel,
            tournament.guild,
            tournament.message,
            tournament.running,
            tournament.isfandom,
            tournament.fandomOverviewPage,
            tournament.updatesChannel,
        )
        await db.close()

    @staticmethod
    async def get_tournament(id: uuid.UUID) -> Optional[Tournament]:
        db = await asyncpg.connect(config.postgres)
        tr = await db.fetchrow("SELECT * FROM tournaments WHERE id=$1", id)
        await db.close()
        if tr is not None:
            return Tournament(
                tr[0],
                tr[1],
                tr[2],
                tr[3],
                tr[4],
                tr[5],
                tr[6],
                tr[7],
                tr[8],
            )

    @staticmethod
    async def get_tournament_by_name(name: str, guild: int) -> Optional[Tournament]:
        db = await asyncpg.connect(config.postgres)
        tr = await db.fetchrow(
            "SELECT * FROM tournaments WHERE name=$1 AND guild=$2;",
            name,
            guild,
        )
        await db.close()
        if tr is not None:
            return Tournament(
                tr[0],
                tr[1],
                tr[2],
                tr[3],
                tr[4],
                tr[5],
                tr[6],
                tr[7],
                tr[8],
            )

    @staticmethod
    async def get_tournaments_by_channel(channel: int) -> list[Tournament]:
        db = await asyncpg.connect(config.postgres)
        records = await db.fetch("SELECT * FROM tournaments WHERE channel=$1;", channel)
        await db.close()
        tournaments: list[Tournament] = []
        for tr in records:
            tournaments.append(
                Tournament(
                    tr[0],
                    tr[1],
                    tr[2],
                    tr[3],
                    tr[4],
                    tr[5],
                    tr[6],
                    tr[7],
                    tr[8],
                ),
            )
        return tournaments

    @staticmethod
    async def get_tournaments_by_guild(guild: int) -> list[Tournament]:
        db = await asyncpg.connect(config.postgres)
        records = await db.fetch("SELECT * FROM tournaments WHERE guild=$1;", guild)
        await db.close()
        tournaments: list[Tournament] = []
        for tr in records:
            tournaments.append(
                Tournament(
                    tr[0],
                    tr[1],
                    tr[2],
                    tr[3],
                    tr[4],
                    tr[5],
                    tr[6],
                    tr[7],
                    tr[8],
                ),
            )
        return tournaments

    @staticmethod
    async def get_running_tournament(channel: int) -> Optional[Tournament]:
        db = await asyncpg.connect(config.postgres)
        tr = await db.fetchrow(
            "SELECT * FROM tournaments WHERE channel=$1 AND running=1;",
            channel,
        )
        await db.close()
        if tr is not None:
            return Tournament(
                tr[0],
                tr[1],
                tr[2],
                tr[3],
                tr[4],
                tr[5],
                tr[6],
                tr[7],
                tr[8],
            )

    @staticmethod
    async def update_tournament(tournament: Tournament) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "UPDATE tournaments SET name=$2, channel=$3, guild=$4, message=$5, running=$6, isfandom=$7, fandomOverviewPage=$8, updatesChannel=$9 WHERE id=$1",
            tournament.id,
            tournament.name,
            tournament.channel,
            tournament.guild,
            tournament.message,
            tournament.running,
            tournament.isfandom,
            tournament.fandomOverviewPage,
            tournament.updatesChannel,
        )
        await db.close()

    @staticmethod
    async def delete_tournament(tournament: Tournament) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute("DELETE FROM tournaments WHERE id=$1", tournament.id)
        await db.commit()

    # Match-related queries
    @staticmethod
    async def insert_match(match: Match) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "INSERT INTO matches VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12);",
            match.id,
            match.name,
            match.guild,
            match.message,
            match.running,
            match.result,
            match.games,
            match.team1,
            match.team2,
            match.tournament,
            match.bestof,
            match.fandomMatchId,
        )
        await db.close()

    @staticmethod
    async def get_match(id: int, tournament: uuid.UUID) -> Optional[Match]:
        db = await asyncpg.connect(config.postgres)
        mr = await db.fetchrow(
            "SELECT * FROM matches WHERE id=$1 AND tournament=$2",
            id,
            tournament,
        )
        await db.close()
        if mr is not None:
            return Match(
                mr[0],
                mr[1],
                mr[2],
                mr[3],
                mr[4],
                mr[5],
                mr[6],
                mr[7],
                mr[8],
                mr[9],
                mr[10],
                mr[11],
            )

    @staticmethod
    async def get_match_by_message(message: int) -> Optional[Match]:
        db = await asyncpg.connect(config.postgres)
        mr = await db.fetchrow("SELECT * FROM matches WHERE message=$1", message)
        await db.close()
        if mr is not None:
            return Match(
                mr[0],
                mr[1],
                mr[2],
                mr[3],
                mr[4],
                mr[5],
                mr[6],
                mr[7],
                mr[8],
                mr[9],
                mr[10],
                mr[11],
            )

    @staticmethod
    async def get_matches_by_tournament(tournament: uuid.UUID) -> list[Match]:
        db = await asyncpg.connect(config.postgres)
        records = await db.fetch(
            "SELECT * FROM matches WHERE tournament=$1",
            tournament,
        )
        await db.close()
        matches: list[Match] = []
        for mr in records:
            matches.append(
                Match(
                    mr[0],
                    mr[1],
                    mr[2],
                    mr[3],
                    mr[4],
                    mr[5],
                    mr[6],
                    mr[7],
                    mr[8],
                    mr[9],
                    mr[10],
                    mr[11],
                ),
            )
        return matches

    @staticmethod
    async def get_matches_by_team(team: Team) -> list[Match]:
        db = await asyncpg.connect(config.postgres)
        records = await db.fetch(
            "SELECT * FROM matches WHERE (team1 = $1 OR team2 = $1) AND guild = $2;",
            team.code,
            team.guild,
        )
        await db.close()
        matches: list[Match] = []
        for mr in records:
            matches.append(
                Match(
                    mr[0],
                    mr[1],
                    mr[2],
                    mr[3],
                    mr[4],
                    mr[5],
                    mr[6],
                    mr[7],
                    mr[8],
                    mr[9],
                    mr[10],
                    mr[11],
                ),
            )
        return matches

    @staticmethod
    async def get_matches_by_state(tournament: uuid.UUID, running: int) -> list[Match]:
        db = await asyncpg.connect(config.postgres)
        records = await db.fetch(
            "SELECT * FROM matches WHERE tournament=$1 AND running=$2",
            tournament,
            running,
        )
        await db.close()
        matches: list[Match] = []
        for mr in records:
            matches.append(
                Match(
                    mr[0],
                    mr[1],
                    mr[2],
                    mr[3],
                    mr[4],
                    mr[5],
                    mr[6],
                    mr[7],
                    mr[8],
                    mr[9],
                    mr[10],
                    mr[11],
                ),
            )
        return matches

    @staticmethod
    async def update_match(match: Match) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "UPDATE matches SET name=$1, guild=$2, message=$3, running=$4, result=$5, games=$6, team1=$7, team2=$8, bestof=$9, fandomMatchId=$12 WHERE id=$10 AND tournament=$11;",
            match.name,
            match.guild,
            match.message,
            match.running,
            match.result,
            match.games,
            match.team1,
            match.team2,
            match.bestof,
            match.id,
            match.tournament,
            match.fandomMatchId,
        )
        await db.close()

    @staticmethod
    async def delete_match(match: Match) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "DELETE FROM matches WHERE name=$1 AND tournament=$2;",
            match.name,
            match.tournament,
        )
        await db.close()

    # User-related queries
    @staticmethod
    async def insert_user(user: User) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "INSERT INTO users VALUES ($1, $2);",
            user.id,
            user.name,
        )
        await db.close()

    @staticmethod
    async def get_user(id: int) -> Optional[User]:
        db = await asyncpg.connect(config.postgres)
        ur = await db.fetchrow("SELECT * FROM users WHERE id=$1", id)
        await db.close()
        if ur is not None:
            return User(ur[0], ur[1])

    @staticmethod
    async def update_user(user: User) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute("UPDATE users SET name=$1 WHERE id=$2;", user.name, user.id)
        await db.close()

    @staticmethod
    async def delete_user(user: User) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute("DELETE FROM users WHERE id=$1;", user.id)
        await db.close()

    # UserMatch-related queries
    @staticmethod
    async def insert_usermatch(usermatch: UserMatch):
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "INSERT INTO users_matches VALUES ($1, $2, $3, $4, $5);",
            usermatch.user_id,
            usermatch.match_id,
            usermatch.match_tournament,
            usermatch.team,
            usermatch.games,
        )
        await db.close()

    @staticmethod
    async def get_usermatch(
        user_id: int,
        match_id: int,
        match_tournament: uuid.UUID,
    ) -> Optional[UserMatch]:
        db = await asyncpg.connect(config.postgres)
        umr = await db.fetchrow(
            "SELECT * FROM users_matches WHERE user_id=$1 AND match_id=$2 AND match_tournament=$3",
            user_id,
            match_id,
            match_tournament,
        )
        await db.close()
        if umr is not None:
            return UserMatch(umr[0], umr[1], umr[2], umr[3], umr[4])

    @staticmethod
    async def get_usermatch_by_match(
        match_id: str,
        match_tournament: uuid.UUID,
    ) -> list[UserMatch]:
        db = await asyncpg.connect(config.postgres)
        records = await db.fetch(
            "SELECT * FROM users_matches WHERE match_id=$1 AND match_tournament=$2",
            match_id,
            match_tournament,
        )
        await db.close()
        usermatches: list[UserMatch] = []
        for umr in records:
            usermatches.append(
                UserMatch(umr[0], umr[1], umr[2], umr[3], umr[4]),
            )
        return usermatches

    @staticmethod
    async def update_usermatch(usermatch: UserMatch) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "UPDATE users_matches SET team=$1, games=$2 WHERE user_id=$3, match_id=$4, match_tournament=$5;",
            usermatch.team,
            usermatch.games,
            usermatch.user_id,
            usermatch.match_id,
            usermatch.match_tournament,
        )
        await db.close()

    @staticmethod
    async def delete_usermatch(usermatch: UserMatch) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "DELETE FROM users_matches WHERE user_id=$1, match_id=$2, match_tournament=$3;",
            usermatch.user_id,
            usermatch.match_id,
            usermatch.match_tournament,
        )
        await db.close()

    @staticmethod
    async def get_leaderboard(
        tournament: uuid.UUID,
        scoring_table: dict[str, int],
    ) -> list[tuple[str, int]]:
        db = await asyncpg.connect(config.postgres)
        with open("./src/database-scripts/leaderboard.sql", "r") as script:
            records = await db.fetch(
                script.read(),
                tournament,
                scoring_table["bo1_team"],
                scoring_table["bo3_team"],
                scoring_table["bo5_team"],
                scoring_table["bo3_games"],
                scoring_table["bo5_games"],
            )
        leaderboard = [list(record) for record in records]
        return leaderboard

    @staticmethod
    async def get_num_matches(tournament: uuid.UUID):
        db = await asyncpg.connect(config.postgres)
        row = await db.fetchrow(
            "SELECT COUNT(*) FROM matches WHERE tournament=$1",
            tournament,
        )
        return int(row[0])
