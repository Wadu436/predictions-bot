from dataclasses import dataclass
from datetime import datetime


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
        "Tab",
        "N_MatchInTab",
    }
    table = "MatchSchedule"

    team1: str
    team2: str
    winner: int

    team1_score: int
    team2_score: int
    best_of: int

    start: datetime

    match_id: str
    tab: str
    n_matchintab: int

    @classmethod
    def from_row(cls, row):
        return MatchScheduleRow(
            team1=row["Team1"],
            team2=row["Team2"],
            winner=None if row["Winner"] == "" else int(row["Winner"]),
            team1_score=None if row["Team1Score"] == "" else int(row["Team1Score"]),
            team2_score=None if row["Team2Score"] == "" else int(row["Team2Score"]),
            best_of=int(row["BestOf"]),
            start=datetime.strptime(row["DateTime UTC"], "%Y-%m-%d %H:%M:%S"),
            match_id=row["MatchId"],
            tab=row["Tab"],
            n_matchintab=int(row["N MatchInTab"]),
        )
