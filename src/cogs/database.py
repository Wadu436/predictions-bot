import logging
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

from discord.ext import commands

db_cog = None

sqlite3.register_adapter(uuid.UUID, lambda u: u.bytes_le)
sqlite3.register_converter("GUID", lambda b: uuid.UUID(bytes_le=b))


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
    con = None

    def __init__(self, bot):
        self.bot = bot

    def open(self) -> None:
        logging.info("Opening Database")
        p = Path("./persistent/bot.db")
        new = not p.exists()

        self.con = sqlite3.connect(p, detect_types=sqlite3.PARSE_DECLTYPES)

        # Create schema
        if new:
            logging.info("Creating Schemas")
            cur = self.con.cursor()
            with open("./src/cogs/database_scripts/schema.sql", "r") as script:
                cur.executescript(script.read())

    def close(self) -> None:
        logging.info("Closing Database")
        self.con.commit()
        self.con.close()

    # Team-related queries
    def get_team(self, code: str, guild: int) -> Team:
        cur = self.con.cursor()
        cur.execute(
            "SELECT * FROM teams WHERE code=:code AND guild=:guild",
            {
                "code": code,
                "guild": guild,
            },
        )
        tr = cur.fetchone()

        if tr is not None:
            return Team(tr[0], tr[1], tr[2], tr[3])

    def get_teams_by_guild(self, guild: int) -> list[Team]:
        cur = self.con.cursor()
        cur.execute(
            "SELECT * FROM teams WHERE guild=:guild",
            {
                "guild": guild,
            },
        )
        teams: list[Team] = []
        for tr in cur:
            teams.append(Team(tr[0], tr[1], tr[2], tr[3]))
        return teams

    # Tournament-related queries
    def get_tournament(self, id: uuid.UUID) -> Tournament:
        cur = self.con.cursor()
        cur.execute(
            "SELECT * FROM tournaments WHERE id=:id",
            {
                "id": id,
            },
        )
        tr = cur.fetchone()
        if tr is not None:
            return Tournament(tr[0], tr[1], tr[2], tr[3], tr[4])

    def get_tournament_by_name(self, name: str, channel: int) -> Tournament:
        cur = self.con.cursor()
        cur.execute(
            "SELECT * FROM tournaments WHERE name=:name AND channel=:channel;",
            {
                "name": name,
                "channel": channel,
            },
        )
        tr = cur.fetchone()
        if tr is not None:
            return Tournament(tr[0], tr[1], tr[2], tr[3], tr[4])

    def get_running_tournament(self, channel: int) -> Tournament:
        cur = self.con.cursor()
        cur.execute(
            "SELECT * FROM tournaments WHERE channel=:channel AND running=1;",
            {
                "channel": channel,
            },
        )
        tr = cur.fetchone()

        if tr is not None:
            return Tournament(tr[0], tr[1], tr[2], tr[3], tr[4])

    def insert_tournament(self, tournament: Tournament) -> None:
        cur = self.con.cursor()
        cur.execute(
            "INSERT INTO tournaments VALUES (:id, :name, :channel, :message, :running);",
            {
                "id": tournament.id,
                "name": tournament.name,
                "channel": tournament.channel,
                "message": tournament.message,
                "running": tournament.running,
            },
        )
        self.con.commit()

    def update_tournament(self, tournament: Team) -> None:
        cur = self.con.cursor()
        cur.execute(
            "UPDATE tournaments SET name=:name, channel=:channel, message=:message, running=:running WHERE id = :id",
            {
                "id": tournament.id,
                "name": tournament.name,
                "channel": tournament.channel,
                "message": tournament.message,
                "running": tournament.running,
            },
        )
        self.con.commit()

    # Match-related queries
    def get_match(self, name: str, tournament: uuid.UUID) -> Match:
        cur = self.con.cursor()
        cur.execute(
            "SELECT * FROM matches WHERE name=:name AND tournament=:tournament",
            {
                "name": name,
                "tournament": tournament,
            },
        )
        mr = cur.fetchone()

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

    def get_match_by_message(self, message: int) -> Match:
        cur = self.con.cursor()
        cur.execute(
            "SELECT * FROM matches WHERE message=:message",
            {
                "message": message,
            },
        )
        mr = cur.fetchone()

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

    def get_matches_by_state(self, tournament: uuid.UUID, running: int) -> list[Match]:
        cur = self.con.cursor()
        cur.execute(
            "SELECT * FROM matches WHERE tournament=:tournament AND running=:running",
            {
                "tournament": tournament,
                "running": running,
            },
        )
        matches: list[Match] = []
        for mr in cur:
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

    def insert_match(self, match: Match) -> None:
        cur = self.con.cursor()
        cur.execute(
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
        self.con.commit()

    def update_match(self, match: Match) -> None:
        cur = self.con.cursor()
        cur.execute(
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
        self.con.commit()

    # User-related queries
    def get_user(self, id: int) -> User:
        cur = self.con.cursor()
        cur.execute(
            "SELECT * FROM users WHERE id=:id",
            {
                "id": id,
            },
        )
        ur = cur.fetchone()

        if ur is not None:
            return User(ur[0], ur[1])

    def insert_user(self, user: User) -> None:
        cur = self.con.cursor()
        cur.execute(
            "INSERT INTO users VALUES (:id, :name);",
            {
                "id": user.id,
                "name": user.name,
            },
        )
        self.con.commit()

    def update_user(self, user: User) -> None:
        cur = self.con.cursor()
        cur.execute(
            "UPDATE users SET name=:name WHERE id=:id;",
            {
                "id": user.id,
                "name": user.name,
            },
        )
        self.con.commit()

    # UserMatch-related queries
    def get_usermatch(
        self,
        user_id: int,
        match_name: str,
        match_tournament: uuid.UUID,
    ) -> UserMatch:
        cur = self.con.cursor()
        cur.execute(
            "SELECT * FROM users_matches WHERE user_id=:user_id AND match_name=:match_name AND match_tournament=:match_tournament",
            {
                "user_id": user_id,
                "match_name": match_name,
                "match_tournament": match_tournament,
            },
        )
        umr = cur.fetchone()

        if umr is not None:
            return UserMatch(umr[0], umr[1], umr[2], umr[3])

    def get_usermatch_by_match(
        self,
        match_name: str,
        match_tournament: uuid.UUID,
    ) -> list[UserMatch]:
        cur = self.con.cursor()
        cur.execute(
            "SELECT * FROM users_matches WHERE match_name=:match_name AND match_tournament=:match_tournament",
            {
                "match_name": match_name,
                "match_tournament": match_tournament,
            },
        )

        usermatches: list[UserMatch] = []
        for umr in cur:
            usermatches.append(UserMatch(umr[0], umr[1], umr[2], umr[3], umr[4]))
        return usermatches

    def insert_usermatch(self, usermatch: UserMatch):
        cur = self.con.cursor()
        cur.execute(
            "INSERT INTO users_matches VALUES (:user_id, :match_name, :match_tournament, :team, :games);",
            {
                "user_id": usermatch.user_id,
                "match_name": usermatch.match_name,
                "match_tournament": usermatch.match_tournament,
                "team": usermatch.team,
                "games": usermatch.games,
            },
        )
        self.con.commit()


def setup(bot):
    global db_cog

    db_cog = DatabaseCog(bot)
    db_cog.open()
    bot.add_cog(db_cog)


def teardown(bot):
    global db_cog

    db_cog.close()
    bot.remove_cog(db_cog.name)
    db_cog = None
