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
    }
    table = "MatchSchedule"

    team1: str
    team2: str
    winner: int

    team1_score: str
    team2_score: str
    best_of: int

    start: datetime

    match_id: str

    @classmethod
    def from_row(cls, row):
        return MatchScheduleRow(
            team1=row["Team1"],
            team2=row["Team2"],
            winner=row["Winner"],
            team1_score=row["Team1Score"],
            team2_score=row["Team2Score"],
            best_of=row["BestOf"],
            start=datetime.strptime(row["DateTime UTC"], "%Y-%m-%d %H:%M:%S"),
            match_id=row["MatchId"],
        )
