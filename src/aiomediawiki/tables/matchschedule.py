from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class MatchScheduleRow:
    fields = {
        "Team1",
        "Team2",
        "Winner",
        "Team1Score",
        "Team2Score",
        "DateTime_UTC",
        "BestOf",
        "MatchId",
        "MatchDay",
        "Tab",
        "N_MatchInTab",
        "InitialN_MatchInTab",
        "IsTiebreaker",
    }
    table = "MatchSchedule"

    team1: str
    team2: str
    winner: Optional[int]

    team1_score: Optional[int]
    team2_score: Optional[int]
    best_of: int

    start: datetime

    match_id: str
    tab: str
    n_matchintab: int
    initialn_matchintab: int
    matchday: int

    is_tiebreaker: bool

    @classmethod
    def from_row(cls, row):
        start = datetime.strptime(row["DateTime UTC"], "%Y-%m-%d %H:%M:%S")
        start = start.replace(tzinfo=timezone.utc)
        return MatchScheduleRow(
            team1=row["Team1"],
            team2=row["Team2"],
            winner=None
            if row["Winner"] is None or row["Winner"] == ""
            else int(row["Winner"]),
            team1_score=None
            if row["Team1Score"] is None or row["Team1Score"] == ""
            else int(row["Team1Score"]),
            team2_score=None
            if row["Team2Score"] is None or row["Team2Score"] == ""
            else int(row["Team2Score"]),
            best_of=int(row["BestOf"]),
            start=start,
            match_id=row["MatchId"],
            tab=row["Tab"],
            n_matchintab=int(row["N MatchInTab"]),
            initialn_matchintab=int(row["InitialN MatchInTab"]),
            matchday=int(row["MatchDay"]),
            is_tiebreaker=bool(int(row["IsTiebreaker"])),
        )
