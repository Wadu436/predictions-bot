import json
import re
from dataclasses import dataclass
from typing import Optional

import aiohttp

from src.aiomediawiki.tables.matchschedule import MatchScheduleRow
from src.aiomediawiki.tables.teams import TeamsRow
from src.aiomediawiki.tables.tournaments import TournamentsRow

leaguepedia_site = "https://lol.fandom.com"


class ServerException(Exception):
    pass


@dataclass
class APIException(Exception):
    code: str
    info: str

    def __str__(self):
        return f"API Error '{self.code}'': {self.info}"


def _fields_to_query(fields):
    return ",".join(fields)


def _construct_url(api_endpoint, **kwargs):
    url = api_endpoint + "?" + "&".join(map(lambda t: f"{t[0]}={t[1]}", kwargs.items()))
    return url


class Site:
    site: str
    api_path: str
    wiki_path: str
    limit: int

    @property
    def api_url(self):
        return self.site + self.api_path

    @property
    def wiki_url(self):
        return self.site + self.wiki_path

    def __init__(
        self,
        site: str,
        api_path: str = "/api.php",
        wiki_path: str = "/wiki/",
        limit: int = 500,
    ):
        self.site = site
        self.api_path = api_path
        self.wiki_path = wiki_path
        self.limit = limit

    async def cargo_query(
        self,
        *,
        tables: str,
        fields: str,
        where: str = None,
        join_on: str = None,
        group_by: str = None,
        having: str = None,
        order_by: str = None,
    ):
        # Filter arguments
        kwargs_unfiltered = {
            "action": "cargoquery",
            "limit": self.limit,
            "tables": tables,
            "fields": fields,
            "where": where,
            "join_on": join_on,
            "group_by": group_by,
            "having": having,
            "order_by": order_by,
            "format": "json",
        }
        kwargs = {k: v for (k, v) in kwargs_unfiltered.items() if v is not None}

        results = []

        while len(results) % self.limit == 0:
            kwargs["offset"] = len(results)
            query_url = _construct_url(self.api_url, **kwargs)
            async with aiohttp.ClientSession() as session:
                async with session.get(query_url) as response:
                    if response.status != 200:
                        raise ServerException(
                            f"HTTP Error. Status code: {response.status}.",
                        )
                    if response.content_type != "application/json":
                        raise ServerException(
                            "Response error. Website did not return json format.",
                        )
                    response_json = await response.text()

            response_dict = json.loads(response_json)
            if "error" in response_dict:
                raise APIException(
                    response_dict["error"]["code"],
                    response_dict["error"]["info"],
                )

            new_results = [row["title"] for row in response_dict["cargoquery"]]
            # Exit the loop if no new results were returned
            if not new_results:
                break

            results.extend(new_results)

        return results

    async def parse_query(
        self,
        *,
        page: str = None,
        title: str = None,
        text: str = None,
        prop: str,
        **kwargs,
    ):
        if page:
            query_url = _construct_url(
                self.api_url,
                action="parse",
                page=page,
                prop=prop,
                format="json",
                kwargs=kwargs,
            )
        else:
            query_url = _construct_url(
                self.api_url,
                action="parse",
                title=title,
                text=text,
                prop=prop,
                format="json",
                kwargs=kwargs,
            )

        async with aiohttp.ClientSession() as session:
            async with session.get(query_url) as response:
                if response.status != 200:
                    raise ServerException(
                        f"HTTP Error. Status code: {response.status}.",
                    )
                if response.content_type != "application/json":
                    raise ServerException(
                        "Response error. Website did not return json format.",
                    )
                response_json = await response.text()

        response_dict = json.loads(response_json)
        if "error" in response_dict:
            raise APIException(
                response_dict["error"]["code"],
                response_dict["error"]["info"],
            )

        return response_dict["parse"]


class Leaguepedia(Site):
    def __init__(self):
        super().__init__(leaguepedia_site)

    async def get_file(self, filename, size=None):
        pattern = r".*src\=\"(.+?)\".*"
        size = "|" + str(size) + "px" if size else ""
        to_parse_text = f"[[File:{filename}|link={size}]]"
        result = await self.parse_query(
            title="Main Page",
            text=to_parse_text,
            disablelimitreport=1,
            prop="text",
        )
        parse_result_text = result["text"]["*"]

        url = re.match(pattern, parse_result_text)[1]
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    img_bytes = await resp.read()
                    return img_bytes

    async def get_page_info(self, page: str, prop: list[str] = None):
        """Return requested properties on a page.

        In addition to the requested properties, also always returns the title and pageid.
        The properties are returned in a dictionary.

        For a list of allowed properties, see https://lol.fandom.com/api.php?action=help&modules=parse

        Arguments:
        page -- The page (e.g. LCS/2021 Season/Summer Season)
        prop -- A list of properties (default=[])
        """
        if prop is None:
            prop = []
        return await self.parse_query(page=page, prop="|".join(prop))

    async def get_tournament(self, overviewpage: str) -> Optional[TournamentsRow]:
        result = await self.cargo_query(
            tables=TournamentsRow.table,
            fields=_fields_to_query(TournamentsRow.fields),
            where=f"OverviewPage='{overviewpage}'",
        )
        if len(result) == 0:
            return None
        return TournamentsRow.from_row(result[0])

    async def get_tournaments(self, region: str) -> list[TournamentsRow]:
        result = await self.cargo_query(
            tables=TournamentsRow.table,
            fields=_fields_to_query(TournamentsRow.fields),
            where=f"Region='{region}'",
        )
        return [TournamentsRow.from_row(row) for row in result]

    async def get_match(self, match_id: str) -> Optional[MatchScheduleRow]:
        result = await self.cargo_query(
            tables=MatchScheduleRow.table,
            fields=_fields_to_query(MatchScheduleRow.fields),
            where=f"MatchId='{match_id}'",
        )
        if len(result) == 0:
            return None
        return MatchScheduleRow.from_row(result[0])

    async def get_matches(self, overviewpage: str) -> list[MatchScheduleRow]:
        result = await self.cargo_query(
            tables=MatchScheduleRow.table,
            fields=_fields_to_query(MatchScheduleRow.fields),
            where=f"OverviewPage='{overviewpage}'",
        )
        return [MatchScheduleRow.from_row(row) for row in result]

    async def get_team(self, name: str) -> Optional[TeamsRow]:
        result = await self.cargo_query(
            tables=TeamsRow.table,
            fields=_fields_to_query(TeamsRow.fields),
            where=f"Name='{name}'",
        )
        if len(result) == 0:
            return None
        return TeamsRow.from_row(result[0])

    async def get_teams(self, overviewpage: str) -> list[TeamsRow]:
        result = await self.cargo_query(
            tables=f"{TeamsRow.table}=T,TournamentRosters=TR",
            fields=_fields_to_query({f"T.{v}" for v in TeamsRow.fields}),
            where=f"TR.OverviewPage='{overviewpage}'",
            join_on="T.OverviewPage=TR.Team",
        )
        return [TeamsRow.from_row(row) for row in result]


leaguepedia = Leaguepedia()
