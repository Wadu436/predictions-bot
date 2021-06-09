from dataclasses import dataclass


@dataclass
class TeamsRow:
    fields = {
        "Name",
        "OverviewPage",
        "Short",
        "Image",
    }
    table = "Teams"

    name: str
    overviewPage: str
    short: str
    image: str

    @classmethod
    def from_row(cls, row):
        return TeamsRow(
            name=row["Name"],
            overviewPage=row["OverviewPage"],
            short=row["Short"],
            image=row["Image"],
        )
