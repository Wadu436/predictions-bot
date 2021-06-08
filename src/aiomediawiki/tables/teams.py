from dataclasses import dataclass


@dataclass
class TeamsRow:
    fields = {
        "Name",
        "Short",
        "Image",
    }
    table = "Teams"

    name: str
    short: str
    image: str

    @classmethod
    def from_row(cls, row):
        return TeamsRow(
            name=row["Name"],
            short=row["Short"],
            image=row["Image"],
        )
