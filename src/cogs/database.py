import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from sqlite3 import PARSE_DECLTYPES

import aiosqlite
from discord.ext import commands, tasks

db_cog = None

aiosqlite.register_adapter(uuid.UUID, lambda u: u.bytes_le)
aiosqlite.register_converter("GUID", lambda b: uuid.UUID(bytes_le=b))


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
    message: int
    running: int


@dataclass
class Match:
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
        self.db_path = Path("./persistent/bot.db")
        self.check_database_schema.start()

    @tasks.loop(count=1)
    async def check_database_schema(self):
        if not self.db_path.exists():
            logging.info("Creating Schemas")
            async with aiosqlite.connect(
                self.db_path,
                detect_types=PARSE_DECLTYPES,
            ) as db:
                with open("./src/cogs/database_scripts/schema.sql", "r") as script:
                    await db.executescript(script.read())
                    await db.commit()

    # Team-related queries
    async def insert_team(self, team: Team) -> None:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                "INSERT INTO teams VALUES (:name, :code, :emoji, :guild);",
                {
                    "name": team.name,
                    "code": team.code,
                    "emoji": team.emoji,
                    "guild": team.guild,
                },
            )
            await db.commit()

    async def get_team(self, code: str, guild: int) -> Team:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            async with db.execute(
                "SELECT * FROM teams WHERE code=:code AND guild=:guild",
                {
                    "code": code,
                    "guild": guild,
                },
            ) as cur:
                tr = await cur.fetchone()
        if tr is not None:
            return Team(tr[0], tr[1], tr[2], tr[3])

    async def get_teams_by_guild(self, guild: int) -> list[Team]:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            async with db.execute(
                "SELECT * FROM teams WHERE guild=:guild",
                {
                    "guild": guild,
                },
            ) as cur:
                teams: list[Team] = []
                async for tr in cur:
                    teams.append(Team(tr[0], tr[1], tr[2], tr[3]))
        return teams

    async def update_team(self, original_code, team: Team) -> None:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                "UPDATE teams SET name=:name, code=:code, emoji=:emoji WHERE code=:original_code AND guild=:guild;",
                {
                    "name": team.name,
                    "code": team.code,
                    "emoji": team.emoji,
                    "original_code": original_code,
                    "guild": team.guild,
                },
            )
            await db.commit()

    async def delete_team(self, team: Team) -> None:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            await db.execute(
                "DELETE FROM teams WHERE code = :code AND guild = :guild;",
                {
                    "code": team.code,
                    "guild": team.guild,
                },
            )
            await db.commit()

    # Tournament-related queries
    async def insert_tournament(self, tournament: Tournament) -> None:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                "INSERT INTO tournaments VALUES (:id, :name, :channel, :message, :running);",
                {
                    "id": tournament.id,
                    "name": tournament.name,
                    "channel": tournament.channel,
                    "message": tournament.message,
                    "running": tournament.running,
                },
            )
            await db.commit()

    async def get_tournament(self, id: uuid.UUID) -> Tournament:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            async with db.execute(
                "SELECT * FROM tournaments WHERE id=:id",
                {
                    "id": id,
                },
            ) as cur:
                tr = await cur.fetchone()
        if tr is not None:
            return Tournament(tr[0], tr[1], tr[2], tr[3], tr[4])

    async def get_tournament_by_name(self, name: str, channel: int) -> Tournament:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            async with db.execute(
                "SELECT * FROM tournaments WHERE name=:name AND channel=:channel;",
                {
                    "name": name,
                    "channel": channel,
                },
            ) as cur:
                tr = await cur.fetchone()
        if tr is not None:
            return Tournament(tr[0], tr[1], tr[2], tr[3], tr[4])

    async def get_running_tournament(self, channel: int) -> Tournament:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            async with db.execute(
                "SELECT * FROM tournaments WHERE channel=:channel AND running=1;",
                {
                    "channel": channel,
                },
            ) as cur:
                tr = await cur.fetchone()
        if tr is not None:
            return Tournament(tr[0], tr[1], tr[2], tr[3], tr[4])

    async def update_tournament(self, tournament: Team) -> None:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                "UPDATE tournaments SET name=:name, channel=:channel, message=:message, running=:running WHERE id = :id",
                {
                    "id": tournament.id,
                    "name": tournament.name,
                    "channel": tournament.channel,
                    "message": tournament.message,
                    "running": tournament.running,
                },
            )
            await db.commit()

    async def delete_tournament(self, tournament: Team) -> None:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                "DELETE FROM tournaments WHERE id = :id",
                {
                    "id": tournament.id,
                },
            )
            await db.commit()

    # Match-related queries
    async def insert_match(self, match: Match) -> None:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                "INSERT INTO matches VALUES (:name, :guild, :message, :running, :result, :games, :team1, :team2, :tournament, :bestof);",
                {
                    "name": match.name,
                    "guild": match.guild,
                    "message": match.message,
                    "running": match.running,
                    "result": match.result,
                    "games": match.games,
                    "team1": match.team1,
                    "team2": match.team2,
                    "tournament": match.tournament,
                    "bestof": match.bestof,
                },
            )
            await db.commit()

    async def get_match(self, name: str, tournament: uuid.UUID) -> Match:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            async with db.execute(
                "SELECT * FROM matches WHERE name=:name AND tournament=:tournament",
                {
                    "name": name,
                    "tournament": tournament,
                },
            ) as cur:
                mr = await cur.fetchone()
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

    async def get_match_by_message(self, message: int) -> Match:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            async with db.execute(
                "SELECT * FROM matches WHERE message=:message",
                {
                    "message": message,
                },
            ) as cur:
                mr = await cur.fetchone()
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

    async def get_matches_by_state(
        self,
        tournament: uuid.UUID,
        running: int,
    ) -> list[Match]:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            async with db.execute(
                "SELECT * FROM matches WHERE tournament=:tournament AND running=:running",
                {
                    "tournament": tournament,
                    "running": running,
                },
            ) as cur:
                matches: list[Match] = []
                async for mr in cur:
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
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                "UPDATE matches SET guild=:guild, message=:message, running=:running, result=:result, games=:games, team1=:team1, team2=:team2, bestof=:bestof WHERE name=:name AND tournament=:tournament;",
                {
                    "name": match.name,
                    "guild": match.guild,
                    "message": match.message,
                    "running": match.running,
                    "result": match.result,
                    "games": match.games,
                    "team1": match.team1,
                    "team2": match.team2,
                    "tournament": match.tournament,
                    "bestof": match.bestof,
                },
            )
            await db.commit()

    async def delete_match(self, match: Match) -> None:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                "DELETE FROM matches WHERE name=:name AND tournament=:tournament;",
                {
                    "name": match.name,
                    "tournament": match.tournament,
                },
            )
            await db.commit()

    # User-related queries
    async def insert_user(self, user: User) -> None:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                "INSERT INTO users VALUES (:id, :name);",
                {
                    "id": user.id,
                    "name": user.name,
                },
            )
            await db.commit()

    async def get_user(self, id: int) -> User:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            async with db.execute(
                "SELECT * FROM users WHERE id=:id",
                {
                    "id": id,
                },
            ) as cur:
                ur = await cur.fetchone()
        if ur is not None:
            return User(ur[0], ur[1])

    async def update_user(self, user: User) -> None:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                "UPDATE users SET name=:name WHERE id=:id;",
                {
                    "id": user.id,
                    "name": user.name,
                },
            )
            await db.commit()

    async def delete_user(self, user: User) -> None:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                "DELETE FROM users WHERE id=:id;",
                {
                    "id": user.id,
                },
            )
            await db.commit()

    # UserMatch-related queries
    async def insert_usermatch(self, usermatch: UserMatch):
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                "INSERT INTO users_matches VALUES (:user_id, :match_name, :match_tournament, :team, :games);",
                {
                    "user_id": usermatch.user_id,
                    "match_name": usermatch.match_name,
                    "match_tournament": usermatch.match_tournament,
                    "team": usermatch.team,
                    "games": usermatch.games,
                },
            )
            await db.commit()

    async def get_usermatch(
        self,
        user_id: int,
        match_name: str,
        match_tournament: uuid.UUID,
    ) -> UserMatch:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            async with db.execute(
                "SELECT * FROM users_matches WHERE user_id=:user_id AND match_name=:match_name AND match_tournament=:match_tournament",
                {
                    "user_id": user_id,
                    "match_name": match_name,
                    "match_tournament": match_tournament,
                },
            ) as cur:
                umr = await cur.fetchone()
        if umr is not None:
            return UserMatch(umr[0], umr[1], umr[2], umr[3])

    async def get_usermatch_by_match(
        self,
        match_name: str,
        match_tournament: uuid.UUID,
    ) -> list[UserMatch]:
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            async with db.execute(
                "SELECT * FROM users_matches WHERE match_name=:match_name AND match_tournament=:match_tournament",
                {
                    "match_name": match_name,
                    "match_tournament": match_tournament,
                },
            ) as cur:
                usermatches: list[UserMatch] = []
                async for umr in cur:
                    usermatches.append(
                        UserMatch(umr[0], umr[1], umr[2], umr[3], umr[4])
                    )
        return usermatches

    async def update_usermatch(self, usermatch: UserMatch):
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                "UPDATE users_matches SET team=:team, games=:games WHERE user_id=:user_id, match_name=:match_name, match_tournament=:match_tournament;",
                {
                    "user_id": usermatch.user_id,
                    "match_name": usermatch.match_name,
                    "match_tournament": usermatch.match_tournament,
                    "team": usermatch.team,
                    "games": usermatch.games,
                },
            )
            await db.commit()

    async def delete_usermatch(self, usermatch: UserMatch):
        async with aiosqlite.connect(self.db_path, detect_types=PARSE_DECLTYPES) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute(
                "DELETE FROM users_matches WHERE user_id=:user_id, match_name=:match_name, match_tournament=:match_tournament;",
                {
                    "user_id": usermatch.user_id,
                    "match_name": usermatch.match_name,
                    "match_tournament": usermatch.match_tournament,
                },
            )
            await db.commit()


def setup(bot):
    bot.add_cog(DatabaseCog(bot))
