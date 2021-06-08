from dataclasses import dataclass


@dataclass
class TournamentsRow:
    fields = {
        "Name",
        "OverviewPage",
        "DateStart",
        "Date",
        "StandardName",
        "Region",
        "League",
        "Country",
    }
    table = "Tournaments"

    name: str
    overviewPage: str

    region: str
    country: str
    league: str

    dateStart: str
    dateEnd: str

    @classmethod
    def from_row(cls, row):
        return TournamentsRow(
            name=row["Name"],
            overviewPage=row["OverviewPage"],
            dateStart=row["DateStart"],
            dateEnd=row["Date"],
            region=row["Region"],
            league=row["League"],
            country=row["Country"],
        )
