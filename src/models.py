import asyncio
import math
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional
from uuid import UUID

from tortoise import fields
from tortoise.models import Model


class TournamentRunningEnum(IntEnum):
    ENDED = 0
    RUNNING = 1


class MatchRunningEnum(IntEnum):
    ENDED = 0
    RUNNING = 1
    CLOSED = 2


@dataclass
class ScoreboardEntry:
    user: "User"
    score: int = 0
    correct: int = 0
    total: int = 0

    @property
    def percentage(self):
        return 100 * self.correct / self.total

    def __str__(self):
        return f"{self.user.name} = Score: {self.score} - Correct: {self.correct} - Total: {self.total} ({self.percentage:.1f}%)"

    def __add__(self, other: "ScoreboardEntry") -> "ScoreboardEntry":
        return ScoreboardEntry(
            self.user,
            self.score + other.score,
            self.correct + other.correct,
            self.total + other.total,
        )


class UUIDPrimaryKeyModel(Model):
    id = fields.UUIDField(pk=True)

    class Meta:
        abstract = True


class Team(UUIDPrimaryKeyModel):
    name = fields.TextField()
    code = fields.TextField()
    emoji = fields.BigIntField()
    guild = fields.BigIntField()

    fandom_overview_page = fields.TextField(null=True)

    bot_created = fields.BooleanField(default=False)

    matches_team1: fields.ReverseRelation["Match"]
    matches_team2: fields.ReverseRelation["Match"]

    @property
    def is_fandom(self) -> bool:
        return self.fandom_overview_page is not None

    class Meta:
        table = "team"
        unique_together = (
            ("code", "guild"),
            ("fandom_overview_page", "guild"),
        )


class Tournament(UUIDPrimaryKeyModel):
    name = fields.TextField()
    channel = fields.BigIntField()
    guild = fields.BigIntField()
    message = fields.BigIntField()
    running = fields.IntEnumField(TournamentRunningEnum)

    matches: fields.ReverseRelation["Match"]

    fandom_overview_page = fields.TextField(null=True)

    updates_channel = fields.BigIntField(null=True)

    score_bo1_team = fields.SmallIntField(default=1)
    score_bo3_team = fields.SmallIntField(default=2)
    score_bo5_team = fields.SmallIntField(default=3)
    score_bo3_games = fields.SmallIntField(default=1)
    score_bo5_games = fields.SmallIntField(default=1)

    leaderboard_include: fields.ManyToManyRelation[
        "Tournament"
    ] = fields.ManyToManyField("models.Tournament")

    @property
    def is_fandom(self) -> bool:
        return self.fandom_overview_page is not None

    async def __calculate_leaderboard_dict(
        self,
        tabs: Optional[list[str]] = None,
        already_included: list["Tournament"] = None,
    ) -> dict["User", ScoreboardEntry]:
        matches: list[UUID]

        scores: dict["User", ScoreboardEntry] = {}

        if tabs is None and self._saved_in_db:
            if already_included is None:
                already_included = []

            if self not in already_included:
                already_included.append(self)
                leaderboards_to_include = await asyncio.gather(
                    *(
                        t.__calculate_leaderboard_dict(
                            already_included=already_included,
                        )
                        for t in await self.leaderboard_include
                        if t not in already_included
                    ),
                )
                for lb in leaderboards_to_include:
                    for user, entry in lb.items():
                        if user not in scores:
                            scores[user] = ScoreboardEntry(user)
                        scores[user] += entry

        if tabs is None:
            matches = await Match.filter(
                tournament=self,
                running=MatchRunningEnum.ENDED,
            ).values_list("id", flat=True)
        else:
            matches = await Match.filter(
                tournament=self,
                running=MatchRunningEnum.ENDED,
                fandom_tab__in=tabs,
            ).values_list("id", flat=True)

        predictions = await Prediction.filter(
            match_id__in=matches,
        ).select_related("match", "user")

        team_score_table = {
            1: self.score_bo1_team,
            3: self.score_bo3_team,
            5: self.score_bo5_team,
        }
        games_score_table = {
            3: self.score_bo3_games,
            5: self.score_bo5_games,
        }

        for p in predictions:
            # Add user to scores if not already in it
            if p.user not in scores:
                scores[p.user] = ScoreboardEntry(p.user)

            se: ScoreboardEntry = scores[p.user]

            # Update dictionary
            se.total += 1

            if p.match.result == p.team:  # type: ignore
                se.correct += 1
                se.score += team_score_table[p.match.bestof]

            if p.match.games == p.games:  # type: ignore
                se.score += games_score_table[p.match.bestof]

        return scores

    async def calculate_leaderboard(
        self,
        tabs: Optional[list[str]] = None,
    ) -> list[ScoreboardEntry]:
        scores = await self.__calculate_leaderboard_dict(tabs)

        leaderboard = list(scores.values())
        leaderboard.sort(key=lambda entry: entry.user.name)
        leaderboard.sort(key=lambda entry: entry.score, reverse=True)

        return leaderboard

    class Meta:
        table = "tournament"
        unique_together = (("name", "guild"),)


class Prediction(UUIDPrimaryKeyModel):
    user = fields.ForeignKeyField("models.User", related_name="predictions")
    match = fields.ForeignKeyField("models.Match", related_name="predictions")

    team = fields.SmallIntField()
    games = fields.SmallIntField()

    class Meta:
        table = "prediction"
        unique_together = (("user", "match"),)


class Match(UUIDPrimaryKeyModel):
    id_in_tournament = fields.SmallIntField()
    name = fields.TextField()
    message = fields.BigIntField(unique=True)
    running = fields.IntEnumField(MatchRunningEnum)

    result = fields.SmallIntField(default=0)
    games = fields.SmallIntField(default=0)
    bestof = fields.SmallIntField(default=0)

    fandom_match_id = fields.TextField(null=True)
    fandom_tab = fields.TextField(null=True)
    fandom_initialn_matchintab = fields.SmallIntField(null=True)

    users: fields.ManyToManyRelation["User"] = fields.ManyToManyField(
        "models.User",
        through=Prediction.Meta.table,
        related_name="matches",
    )
    predictions: fields.ManyToManyRelation[Prediction]

    team1 = fields.ForeignKeyField("models.Team", related_name="matches_team1")
    team2 = fields.ForeignKeyField("models.Team", related_name="matches_team2")
    tournament = fields.ForeignKeyField("models.Tournament", related_name="matches")

    @property
    def is_fandom(self) -> bool:
        return (
            self.fandom_tab is not None and self.fandom_initialn_matchintab is not None
        )

    @property
    def win_games(self) -> int:
        return math.ceil(self.bestof / 2)

    @property
    def lose_games(self) -> int:
        return self.games - self.win_games

    class Meta:
        table = "match"
        unique_together = (
            ("id_in_tournament", "tournament"),
            ("tournament", "fandom_match_id"),
            ("tournament", "fandom_tab", "fandom_initialn_matchintab"),
        )

    def __str__(self):
        return self.name


class User(UUIDPrimaryKeyModel):
    discord_id = fields.BigIntField(unique=True)
    name = fields.TextField()

    matches: fields.ManyToManyRelation[Match]
    predictions: fields.ManyToManyRelation[Prediction]

    class Meta:
        table = "user"

    def __str__(self):
        return self.name
