import math
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import asyncpg
from discord.ext import commands

import config


@dataclass
class Team:
    name: str
    code: str
    emoji: str
    guild: int


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


@dataclass
class Match:
    def __post_init__(self):
        self.win_games = math.ceil(self.bestof / 2)
        self.lose_games = self.games - self.win_games

    name: str
    guild: int
    message: int
    running: int
    result: int
    games: int
    team1: str
    team2: str
    tournament: uuid.UUID
    bestof: int
    win_games: int = field(init=False)
    lose_games: int = field(init=False)


@dataclass
class UserMatch:
    user_id: int
    match_name: str
    match_tournament: uuid.UUID
    team: int
    games: int


class DatabaseCog(commands.Cog, name="Database"):
    db_path: Path

    def __init__(self, bot):
        self.bot = bot

    # Team-related queries
    async def insert_team(self, team: Team) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "INSERT INTO teams VALUES ($1, $2, $3, $4);",
            team.name,
            team.code,
            team.emoji,
            team.guild,
        )
        await db.close()

    async def get_team(self, code: str, guild: int) -> Optional[Team]:
        db = await asyncpg.connect(config.postgres)
        tr = await db.fetchrow(
            "SELECT * FROM teams WHERE code=$1 AND guild=$2",
            code,
            guild,
        )
        await db.close()
        if tr is not None:
            return Team(tr[0], tr[1], tr[2], tr[3])

    async def get_teams_by_guild(self, guild: int) -> list[Team]:
        db = await asyncpg.connect(config.postgres)
        records = await db.fetch("SELECT * FROM teams WHERE guild=$1", guild)
        teams: list[Team] = []
        for tr in records:
            teams.append(Team(tr[0], tr[1], tr[2], tr[3]))
        await db.close()
        return teams

    async def update_team(self, original_code, team: Team) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "UPDATE teams SET name=$1, code=$2, emoji=$3 WHERE code=$4 AND guild=$5;",
            team.name,
            team.code,
            team.emoji,
            original_code,
            team.guild,
        )
        await db.close()

    async def delete_team(self, team: Team) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "DELETE FROM teams WHERE code=$1 AND guild=$2;",
            team.code,
            team.guild,
        )
        await db.close()

    # Tournament-related queries
    async def insert_tournament(self, tournament: Tournament) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "INSERT INTO tournaments VALUES ($1, $2, $3, $4, $5, $6);",
            tournament.id,
            tournament.name,
            tournament.channel,
            tournament.guild,
            tournament.message,
            tournament.running,
        )
        await db.close()

    async def get_tournament(self, id: uuid.UUID) -> Optional[Tournament]:
        db = await asyncpg.connect(config.postgres)
        tr = await db.fetchrow("SELECT * FROM tournaments WHERE id=$1", id)
        await db.close()
        if tr is not None:
            return Tournament(tr[0], tr[1], tr[2], tr[3], tr[4], tr[5])

    async def get_tournament_by_name(
        self,
        name: str,
        guild: int,
    ) -> Optional[Tournament]:
        db = await asyncpg.connect(config.postgres)
        tr = await db.fetchrow(
            "SELECT * FROM tournaments WHERE name=$1 AND guild=$2;",
            name,
            guild,
        )
        await db.close()
        if tr is not None:
            return Tournament(tr[0], tr[1], tr[2], tr[3], tr[4], tr[5])

    async def get_tournaments_by_channel(self, channel: int) -> list[Tournament]:
        db = await asyncpg.connect(config.postgres)
        records = await db.fetch("SELECT * FROM tournaments WHERE channel=$1;", channel)
        await db.close()
        tournaments: list[Tournament] = []
        for tr in records:
            tournaments.append(
                Tournament(tr[0], tr[1], tr[2], tr[3], tr[4], tr[5]),
            )
        return tournaments

    async def get_tournaments_by_guild(self, guild: int) -> list[Tournament]:
        db = await asyncpg.connect(config.postgres)
        records = await db.fetch("SELECT * FROM tournaments WHERE guild=$1;", guild)
        await db.close()
        tournaments: list[Tournament] = []
        for tr in records:
            tournaments.append(
                Tournament(tr[0], tr[1], tr[2], tr[3], tr[4], tr[5]),
            )
        return tournaments

    async def get_running_tournament(self, channel: int) -> Optional[Tournament]:
        db = await asyncpg.connect(config.postgres)
        tr = await db.fetchrow(
            "SELECT * FROM tournaments WHERE channel=$1 AND running=1;",
            channel,
        )
        await db.close()
        if tr is not None:
            return Tournament(tr[0], tr[1], tr[2], tr[3], tr[4], tr[5])

    async def update_tournament(self, tournament: Tournament) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "UPDATE tournaments SET name=$2, channel=$3, guild=$4, message=$5, running=$6 WHERE id=$1",
            tournament.id,
            tournament.name,
            tournament.channel,
            tournament.guild,
            tournament.message,
            tournament.running,
        )
        await db.close()

    async def delete_tournament(self, tournament: Tournament) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute("DELETE FROM tournaments WHERE id=$1", tournament.id)
        await db.commit()

    # Match-related queries
    async def insert_match(self, match: Match) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "INSERT INTO matches VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10);",
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
        )
        await db.close()

    async def get_match(self, name: str, tournament: uuid.UUID) -> Optional[Match]:
        db = await asyncpg.connect(config.postgres)
        mr = await db.fetchrow(
            "SELECT * FROM matches WHERE name=$1 AND tournament=$2",
            name,
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
            )

    async def get_match_by_message(self, message: int) -> Optional[Match]:
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
            )

    async def get_matches_by_tournament(
        self,
        tournament: uuid.UUID,
    ) -> list[Match]:
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
                ),
            )
        return matches

    async def get_matches_by_team(
        self,
        team: Team,
    ) -> list[Match]:
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
                ),
            )
        return matches

    async def get_matches_by_state(
        self,
        tournament: uuid.UUID,
        running: int,
    ) -> list[Match]:
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
                ),
            )
        return matches

    async def update_match(self, match: Match) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "UPDATE matches SET guild=$2, message=$3, running=$4, result=$5, games=$6, team1=$7, team2=$8, bestof=$10 WHERE name=$1 AND tournament=$9;",
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
        )
        await db.close()

    async def delete_match(self, match: Match) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "DELETE FROM matches WHERE name=$1 AND tournament=$2;",
            match.name,
            match.tournament,
        )
        await db.close()

    # User-related queries
    async def insert_user(self, user: User) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "INSERT INTO users VALUES ($1, $2);",
            user.id,
            user.name,
        )
        await db.close()

    async def get_user(self, id: int) -> Optional[User]:
        db = await asyncpg.connect(config.postgres)
        ur = await db.fetchrow("SELECT * FROM users WHERE id=$1", id)
        await db.close()
        if ur is not None:
            return User(ur[0], ur[1])

    async def update_user(self, user: User) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute("UPDATE users SET name=$1 WHERE id=$2;", user.name, user.id)
        await db.close()

    async def delete_user(self, user: User) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute("DELETE FROM users WHERE id=$1;", user.id)
        await db.close()

    # UserMatch-related queries
    async def insert_usermatch(self, usermatch: UserMatch):
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "INSERT INTO users_matches VALUES ($1, $2, $3, $4, $5);",
            usermatch.user_id,
            usermatch.match_name,
            usermatch.match_tournament,
            usermatch.team,
            usermatch.games,
        )
        await db.close()

    async def get_usermatch(
        self,
        user_id: int,
        match_name: str,
        match_tournament: uuid.UUID,
    ) -> Optional[UserMatch]:
        db = await asyncpg.connect(config.postgres)
        umr = await db.fetchrow(
            "SELECT * FROM users_matches WHERE user_id=$1 AND match_name=$2 AND match_tournament=$3",
            user_id,
            match_name,
            match_tournament,
        )
        await db.close()
        if umr is not None:
            return UserMatch(umr[0], umr[1], umr[2], umr[3], umr[4])

    async def get_usermatch_by_match(
        self,
        match_name: str,
        match_tournament: uuid.UUID,
    ) -> list[UserMatch]:
        db = await asyncpg.connect(config.postgres)
        records = await db.fetch(
            "SELECT * FROM users_matches WHERE match_name=$1 AND match_tournament=$2",
            match_name,
            match_tournament,
        )
        await db.close()
        usermatches: list[UserMatch] = []
        async for umr in records:
            usermatches.append(
                UserMatch(umr[0], umr[1], umr[2], umr[3], umr[4]),
            )
        return usermatches

    async def update_usermatch(self, usermatch: UserMatch) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "UPDATE users_matches SET team=$1, games=$2 WHERE user_id=$3, match_name=$4, match_tournament=$5;",
            usermatch.team,
            usermatch.games,
            usermatch.user_id,
            usermatch.match_name,
            usermatch.match_tournament,
        )
        await db.close()

    async def delete_usermatch(self, usermatch: UserMatch) -> None:
        db = await asyncpg.connect(config.postgres)
        await db.execute(
            "DELETE FROM users_matches WHERE user_id=$1, match_name=$2, match_tournament=$3;",
            usermatch.user_id,
            usermatch.match_name,
            usermatch.match_tournament,
        )
        await db.close()

    async def get_leaderboard(
        self,
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


def setup(bot):
    bot.add_cog(DatabaseCog(bot))
