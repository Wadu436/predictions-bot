import asyncio
import logging
import math
import re
from datetime import datetime, timedelta, timezone
from traceback import print_exc
from typing import Optional
from uuid import UUID

import discord
import tortoise
import tortoise.exceptions
from discord.channel import TextChannel
from discord.ext import commands, tasks

from src import models
from src.aiomediawiki.aiomediawiki import APIException, ServerException, leaguepedia
from src.aiomediawiki.tables.teams import TeamsRow
from src.managers.tournamentmanager import TournamentManager
from src.utils import decorators


# Exceptions
class TournamentException(Exception):
    tournament: models.Tournament
    reason: str

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


class TournamentCog(commands.Cog, name="Tournament"):
    score_table: dict[str, int] = {
        "bo1_team": 1,
        "bo3_team": 2,
        "bo3_games": 1,
        "bo5_team": 3,
        "bo5_games": 1,
    }
    dialogs: dict[int, int] = {}  # (dialog message, match message)
    fandommatch_errors: set[UUID] = set()

    # http:// or https://
    link_validation_regex = re.compile(r"^(?:http)s?://", re.IGNORECASE)
    tournament_manager: TournamentManager

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tournament_manager = TournamentManager(bot)
        self.update_fandom_matches_task.add_exception_type(
            APIException, ServerException
        )

    def cog_unload(self):
        self.update_fandom_matches_task.stop()

    @commands.Cog.listener()
    async def on_ready(self):
        logging.debug("Starting Fandom task.")
        self.update_fandom_matches_task.start()

    # ------------------------------ TASKS -----------------------------

    @tasks.loop(minutes=5, reconnect=True)
    async def update_fandom_matches_task(self):
        logging.debug("Running Fandom task.")
        fandom_tournaments = await models.Tournament.filter(
            running=models.TournamentRunningEnum.RUNNING
        ).exclude(fandom_overview_page="")
        for tournament in fandom_tournaments:
            await self.update_fandom_matches(tournament)
        logging.debug("Fandom task done.")

    async def update_fandom_matches(self, tournament: models.Tournament):
        fandom_tabs = await leaguepedia.get_tabs_before(
            tournament.fandom_overview_page,
            datetime.now(tz=timezone.utc) + timedelta(days=4),
        )

        fandommatches = await leaguepedia.get_matches_in_tabs(
            tournament.fandom_overview_page,
            fandom_tabs,
        )
        any_ended: bool = False
        matchdays_to_close: set[str, int] = {
            (fandommatch.tab, fandommatch.matchday)
            for fandommatch in fandommatches
            if (fandommatch.start - timedelta(minutes=30))
            < datetime.now(tz=timezone.utc)
        }

        teams = await models.Team.filter(guild=tournament.guild).exclude(
            fandom_overview_page=None
        )
        teams = {t.fandom_overview_page: t for t in teams}

        db_matches = await models.Match.filter(
            tournament=tournament, fandom_tab__in=fandom_tabs
        ).select_related("team1", "team2")
        db_matches = {
            (m.fandom_tab, m.fandom_initialn_matchintab): m for m in db_matches
        }
        for fandommatch in fandommatches:
            # Check if match already exists
            if (
                fandommatch.tab,
                fandommatch.initialn_matchintab,
            ) not in db_matches:
                if fandommatch.winner is None:
                    # Match does not exist yet
                    team1 = teams[fandommatch.team1]
                    team2 = teams[fandommatch.team2]

                    try:
                        await self.tournament_manager.start_match(
                            tournament,
                            name=f"{fandommatch.tab} Match {fandommatch.n_matchintab}",
                            team1=team1,
                            team2=team2,
                            bestof=fandommatch.best_of,
                            fandom_tab=fandommatch.tab,
                            fandom_initialn_matchintab=fandommatch.initialn_matchintab,
                        )
                    except Exception as e:
                        print_exc()
                        pass
            else:
                match = db_matches[(fandommatch.tab, fandommatch.initialn_matchintab)]
                if match.running != models.MatchRunningEnum.ENDED:
                    if (
                        match.running == models.MatchRunningEnum.RUNNING
                        and (fandommatch.tab, fandommatch.matchday)
                        in matchdays_to_close
                        and fandommatch.winner is None
                    ):
                        # Match should be closed, but is not over yet (no result)
                        await self.tournament_manager.close_match(match)

                    if fandommatch.winner is not None:
                        # Match is over (there is a result)

                        # Safety check on the teams
                        if (
                            fandommatch.team1 != match.team1.fandom_overview_page
                            or fandommatch.team2 != match.team2.fandom_overview_page
                        ):
                            # Generate an error message
                            if match.id not in self.fandommatch_errors:
                                channel: TextChannel
                                if tournament.updates_channel is not None:
                                    channel_id = tournament.updates_channel
                                    channel = self.bot.get_channel(channel_id)
                                    message = f"There was a problem closing match {match.id_in_tournament} in tournament {tournament.name} ({channel.mention})."
                                else:
                                    channel_id = tournament.channel
                                    channel = self.bot.get_channel(channel_id)
                                    message = f"There was a problem closing match {match.id_in_tournament}."

                                if channel is not None:
                                    channel.send(message)
                                    self.fandommatch_errors.add(match.id)

                            continue

                        any_ended = True
                        await self.tournament_manager.end_match(
                            match,
                            fandommatch.winner,
                            fandommatch.team1_score + fandommatch.team2_score,
                            update_tournament_message=False,
                        )
        if any_ended:
            await self.tournament_manager.update_tournament_message(tournament)

    # ----------------------------- UTILITY ----------------------------

    async def update_fandom_teams(
        self, tournament_overviewpage: str, guild_id: int
    ) -> bool:
        teams = await leaguepedia.get_teams(tournament_overviewpage)
        guild: discord.Guild = self.bot.get_guild(guild_id)
        guild_teams = await models.Team.filter(guild=guild_id)

        teams_to_create: list[TeamsRow] = []

        # Figure out which teams we need to add
        for team in teams:
            t = discord.utils.get(guild_teams, code=team.short.lower())
            if t is None:
                teams_to_create.append(team)
            elif not t.is_fandom:
                # Take control of teams with the correct name already
                t.fandom_overview_page = team.overviewPage
                await t.save()

        error = False

        # Return true if there was an error
        async def add_team(team: TeamsRow) -> bool:
            # page_info = await leaguepedia.get_page_info(team.overviewPage, ["images"])
            team_image = f"{team.overviewPage}logo square.png"
            img = await leaguepedia.get_file(team_image, size=256)
            try:
                emoji: discord.Emoji = await guild.create_custom_emoji(
                    name=team.short.lower(), image=img
                )
            except discord.errors.HTTPException:
                return True

            await models.Team.create(
                name=team.name,
                code=team.short.lower(),
                emoji=emoji.id,
                guild=guild_id,
                fandom_overview_page=team.overviewPage,
                bot_created=True,
            )

            return False

        coro_list = [add_team(t) for t in teams_to_create]
        return any(await asyncio.gather(*coro_list))

    # ----------------------------- GROUPS -----------------------------

    @commands.group(
        name="tournament",
        brief="Commands for interacting with tournaments.",
        description="Commands for creating, ending and listing information on a tournament.",
        aliases=["tr"],
    )
    @commands.guild_only()
    async def tournament_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @commands.group(
        name="match",
        brief="Commands for interacting with matches.",
        description="Commands for creating, closing, ending and listing information on a match.",
        aliases=["m"],
    )
    @commands.guild_only()
    async def match_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    # ---------------------------- COMMANDS ----------------------------

    @tournament_group.command(
        name="start",
        brief="Starts a tournament.",
        description="Starts a tournament in this channel.\n\nArguments:\n-Tournament name can contain spaces.\n-Tournament link should be a link to the overview page on Leaguepedia",
        aliases=["s"],
        usage="<tournament name>",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def tournament_start(self, ctx: commands.Context, *, name_or_link: str):
        # Check if tournament already running
        tournament = await models.Tournament.get_or_none(
            channel=ctx.channel.id,
            running=models.TournamentRunningEnum.RUNNING,
        )
        if tournament is not None:
            raise TournamentException(
                f"There is already a running tournament in this channel: {tournament}. You can only have one running tournament per channel."
            )

        # Check if argument is a name or a link
        is_link = re.match(self.link_validation_regex, name_or_link) is not None

        tournament_name = name_or_link
        if is_link:
            # Extra checks for leaguepedia tournament
            # Check if link is a leaguepedia link
            link = name_or_link
            if not link.startswith(leaguepedia.wiki_url):
                await ctx.send("That is not a Leaguepedia link.")
                return
            try:
                page_info = await leaguepedia.get_page_info(
                    link.removeprefix(leaguepedia.wiki_url)
                )
            except APIException as e:
                if e.code == "pagecannotexist":
                    await ctx.send("This is not a regular page.")
                if e.code == "missingtitle":
                    await ctx.send("This page doesn't exist.")
                return
            page_title = page_info["title"]

            fandom_tournament = await leaguepedia.get_tournament(page_title)
            if not fandom_tournament:
                await ctx.send(f"This is not a tournament overview page.")
                return

            tournament_name = fandom_tournament.name

        # We have verified the tournament can be started
        async with ctx.typing():
            fandom_overview_page = None
            if is_link:
                error = await self.update_fandom_teams(
                    fandom_tournament.overviewPage,
                    ctx.guild.id,
                )

                if error:
                    await ctx.send(
                        content="There was an error while creating the teams participating in this tournament. Perhaps the bot doesn't have permission to create new emoji or there aren't any emote slots left.",
                    )
                    return

                fandom_overview_page = fandom_tournament.overviewPage

            # Check if tournament by this name already exists
            # If yes, add a number behind it
            base_name = tournament_name
            i = 1
            tournament = await models.Tournament.get_or_none(
                name=tournament_name, guild=ctx.guild.id
            )
            while tournament:
                tournament_name = base_name + f" ({i})"
                i += 1
                tournament = await models.Tournament.get_or_none(
                    name=tournament_name, guild=ctx.guild.id
                )

            tournament = await self.tournament_manager.start_tournament(
                tournament_name,
                ctx.channel.id,
                ctx.guild.id,
                fandom_overview_page,
            )

            await ctx.message.delete()

            if tournament.is_fandom:
                await self.update_fandom_matches(tournament)

    @tournament_group.command(
        name="end",
        brief="Ends the running tournament.",
        description="Ends the running tournament.",
        aliases=["e"],
        usage="",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def tournament_end(self, ctx):
        # Check if tournament running
        tournament = await models.Tournament.get_or_none(
            channel=ctx.channel.id,
            running=models.TournamentRunningEnum.RUNNING,
        )
        if tournament is None:
            raise TournamentException("There is no running tournament in this channel.")

        # Check if there are still matches not ended
        running_matches_count = await models.Match.filter(
            tournament=tournament,
            running=models.MatchRunningEnum.RUNNING,
        ).count()
        closed_matches_count = await models.Match.filter(
            tournament=tournament,
            running=models.MatchRunningEnum.CLOSED,
        ).count()

        if running_matches_count > 0:
            raise TournamentException(
                f"Could not end tournament {tournament} (There are still open matches.)"
            )

        if closed_matches_count > 0:
            raise TournamentException(
                f"Could not end tournament {tournament} (There are still closed matches.)"
            )

        await self.tournament_manager.end_tournament(tournament)

        await ctx.send(f"Tournament **{tournament.name}** ended.")
        await ctx.message.delete()

    @tournament_group.command(
        name="info",
        brief="Shows info on a tournament.",
        description="Shows info on a tournament in this server. If no name is given, it shows info on the currently running tournament in this channel.\n\nArguments:\n-Tournament name can contain spaces.",
        aliases=["i"],
        usage="[tournament name]",
    )
    @commands.guild_only()
    async def tournament_show(self, ctx, *, name: Optional[str]):
        if name is not None:
            tournament = await models.Tournament.get_or_none(
                name=name,
                guild=ctx.guild.id,
            )
            txt = "There is no tournament with this name in this guild."
        else:
            tournament = await models.Tournament.get_or_none(
                channel=ctx.channel.id,
                running=models.TournamentRunningEnum.RUNNING,
            )
            txt = "There is no running tournament in this channel."

        # Check if tournament exists
        if tournament is None:
            raise TournamentException(f"Could not find tournament ({txt})")

        content = await self.tournament_manager.generate_tournament_text(tournament)
        await ctx.send(content + "\n`This message does not get updated.`")

    @tournament_group.command(
        name="setupdates",
        brief="Sets this channel to display updates on the tournament (Who predicted correctly, etc.).",
        description="Sets this channel to display updates on the tournament (Who predicted correctly, etc.).\n\nArguments:\n-Tournament name can contain spaces.",
        usage="<tournament name>",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def tournament_updates(self, ctx, *, name: str):
        tournament = await models.Tournament.get_or_none(
            name=name,
            guild=ctx.guild.id,
        )

        # Check if tournament exists
        if tournament is None:
            raise TournamentException(
                "Could not find tournament (There is no tournament with that name in this server.)"
            )

        tournament.updates_channel = ctx.channel.id
        await tournament.save()
        await ctx.send(
            f"This channel will now display updates on the tournament {tournament.name}."
        )

    @tournament_group.command(
        name="list",
        brief="Lists tournaments in a channel.",
        description="Lists all current and past tournaments in this server.",
        aliases=["l", "ls"],
        usage="",
    )
    @commands.guild_only()
    async def tournament_list(self, ctx: commands.Context):
        tournaments = await models.Tournament.filter(guild=ctx.guild.id)

        paginator = commands.Paginator(max_size=2000, prefix="", suffix="")

        if tournaments:
            paginator.add_line("**Tournaments:**")
            for tournament in tournaments:
                channel: discord.Channel = self.bot.get_channel(tournament.channel)
                line = f"**{tournament.name}** - Channel: {channel.mention}"
                if tournament.running == models.TournamentRunningEnum.ENDED:
                    line += " - Ended"
                paginator.add_line(line)
        else:
            paginator.add_line("There are no tournaments in this server.")

        for page in paginator.pages:
            await ctx.send(page)

    @match_group.command(
        name="start",
        brief="Starts a match.",
        description="Creates a new match between two teams.\n\nArguments:\n-Match name can contain spaces.\n-Short codes must be for teams that exist in this server.\n-X must be 1, 3 or 5.\n\nExample: match start Week 3 Match 2 g2 fnc 3",
        aliases=["s"],
        usage="<match name> <short code team 1> <short code team 2> <best of>",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @decorators.regex_arguments("(.+) (\\S+) (\\S+) (\\S+)")
    async def match_start(
        self,
        ctx,
        name: str,
        team1_code: str,
        team2_code: str,
        bestof: int,
    ):
        # Check if tournament running
        tournament = await models.Tournament.get_or_none(
            channel=ctx.channel.id,
            running=models.MatchRunningEnum.RUNNING,
        )
        if tournament is None:
            raise TournamentException("There is no running tournament in this channel.")

        if bestof not in [1, 3, 5]:
            raise TournamentException(
                f"{bestof} is not a valid value for the 'best of' field."
            )

        try:
            team1 = await models.Team.get(code=team1_code, guild=ctx.guild.id)
        except tortoise.exceptions.DoesNotExist:
            raise TournamentException(f"There is no team with code {team1_code}")

        try:
            team2 = await models.Team.get(code=team2_code, guild=ctx.guild.id)
        except tortoise.exceptions.DoesNotExist:
            raise TournamentException(f"There is no team with code {team2_code}")

        await self.tournament_manager.start_match(
            tournament,
            name.strip(),
            bestof,
            team1,
            team2,
        )

        await ctx.message.delete()

    @match_group.command(
        name="close",
        brief="Closes predictions for a match.",
        description='Closes predictions on the specified matches.\n\nArguments:\n-Match ids, which is the number in the match message before the dot (e.g. in "23. Group Stage Game 4", the match id is 23).\n-The match ids should be seperated by spaces\n-You can also specify a range of match ids with a - (e.g. 22-24 would mean ids 22, 23 and 23)',
        aliases=["c"],
        usage="<ids>",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def match_close(self, ctx, *ids_string: str):
        # Validate input
        # Check if tournament running
        tournament = await models.Tournament.get_or_none(
            channel=ctx.channel.id,
            running=models.MatchRunningEnum.RUNNING,
        )
        if tournament is None:
            raise TournamentException("There is no running tournament in this channel.")

        ids = []
        for id_string in ids_string:
            if id_string.isdigit():
                ids.append(int(id_string))
            else:
                s = id_string.split(sep="-")
                if len(s) == 2 and s[0].isdigit() and s[1].isdigit():
                    start = int(s[0])
                    stop = int(s[1]) + 1
                    ids.extend(list(range(start, stop)))

        matches = await models.Match.filter(
            tournament=tournament,
            id_in_tournament__in=ids,
            running=models.MatchRunningEnum.RUNNING,
        )

        coro_list = [self.tournament_manager.close_match(match) for match in matches]
        asyncio.gather(*coro_list)
        await ctx.message.delete()

    @match_group.command(
        name="end",
        brief="Ends a match.",
        description='Ends the match.\n\nArguments:\n\nArguments:\n-Match ids, which is the number in the match message before the dot (e.g. in "23. Group Stage Game 4", the match id is 23).\n-The match ids should be seperated by spaces-You can also specify a range of match ids with a - (e.g. 22-24 would mean ids 22, 23 and 23)',
        aliases=["e"],
        usage="<ids>",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def match_end(self, ctx, *ids_string: str):
        # Validate input
        # Check if tournament running
        tournament = await models.Tournament.get_or_none(
            channel=ctx.channel.id,
            running=models.MatchRunningEnum.RUNNING,
        )
        if tournament is None:
            raise TournamentException("There is no running tournament in this channel.")

        ids = []
        for id_string in ids_string:
            if id_string.isdigit():
                ids.append(int(id_string))
            else:
                s = id_string.split(sep="-")
                if len(s) == 2 and s[0].isdigit() and s[1].isdigit():
                    start = int(s[0])
                    stop = int(s[1]) + 1
                    ids.extend(list(range(start, stop)))

        # Also open the dialog for already ended matches in case the bot made a mistake
        matches = (
            await models.Match.filter(
                tournament=tournament,
                id_in_tournament__in=ids,
            )
            .order_by("id_in_tournament")
            .select_related("team1", "team2")
        )

        for match in matches:
            if match.running == models.MatchRunningEnum.RUNNING:
                await self.tournament_manager.close_match(match)
            if match.message not in self.dialogs.values():
                txt = f'**Match End:** Which team won in match {match.id_in_tournament} "{match.name}"'
                if match.bestof > 1:
                    txt += " and in how many games"
                txt += "? Press ✅ after you're done to end the match."
                message: discord.Message = await ctx.send(txt)

                self.dialogs[message.id] = match.message

                # Add Team reacts
                await message.add_reaction(self.bot.get_emoji(match.team1.emoji))
                await message.add_reaction(self.bot.get_emoji(match.team2.emoji))

                # Add Games reacts
                games_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

                if match.bestof > 1:
                    for i in range(math.floor(match.bestof / 2), match.bestof):
                        await message.add_reaction(games_emojis[i])

                await message.add_reaction("✅")

        await ctx.message.delete()

    @match_group.command(
        name="fix",
        brief="Fix match.",
        description="Fixes emotes on a match.",
        usage="<id>",
    )
    @commands.guild_only()
    @commands.is_owner()
    async def match_fix(self, ctx: commands.Context, *, id: int):
        tournament = await models.Tournament.get_or_none(
            channel=ctx.channel.id,
            running=models.MatchRunningEnum.RUNNING,
        )
        if tournament is None:
            raise TournamentException("There is no running tournament in this channel.")

        match = (
            await models.Match.filter(
                id_in_tournament=id,
                tournament=tournament,
            )
            .select_related("team1", "team2")
            .first()
        )
        if match is None:
            raise TournamentException("This match does not exist")

        if match.running == models.MatchRunningEnum.RUNNING:
            # Fix emoji
            message: discord.Message = await ctx.channel.fetch_message(match.message)

            for reaction in message.reactions:
                if reaction.me:
                    await reaction.remove(self.bot.user)

            await message.add_reaction(self.bot.get_emoji(match.team1.emoji))
            await message.add_reaction(self.bot.get_emoji(match.team2.emoji))

            # Add Games reacts
            games_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

            if match.bestof > 1:
                for i in range(math.floor(match.bestof / 2), match.bestof):
                    await message.add_reaction(games_emojis[i])

        # Fix name
        await self.tournament_manager.update_match_message(match)

    @match_group.command(
        name="list",
        brief="Lists all matches in a tournament.",
        description="Lists all current and past matches in the provided tournament. If no tournament is provided, lists matches in the currently running tournament.",
        aliases=["l", "ls"],
        usage="[tournament name]",
    )
    @commands.guild_only()
    async def matches_list(self, ctx, *, name: Optional[str]):
        if name is not None:
            tournament = await models.Tournament.get_or_none(
                name=name,
                guild=ctx.guild.id,
            )
            txt = "There is no tournament with this name in this guild."
        else:
            tournament = await models.Tournament.get_or_none(
                channel=ctx.channel.id,
                running=models.TournamentRunningEnum.RUNNING,
            )
            txt = "There is no running tournament in this channel."

        # Check if tournament exists
        if tournament is None:
            raise TournamentException(txt)

        past_matches = await models.Match.filter(
            tournament=tournament,
            running=models.MatchRunningEnum.ENDED,
        ).prefetch_related("team1", "team2")
        closed_matches = await models.Match.filter(
            tournament=tournament,
            running=models.MatchRunningEnum.CLOSED,
        ).prefetch_related("team1", "team2")
        active_matches = await models.Match.filter(
            tournament=tournament,
            running=models.MatchRunningEnum.RUNNING,
        ).prefetch_related("team1", "team2")

        paginator = commands.Paginator(max_size=2000, prefix="", suffix="")
        paginator.add_line(f"***{tournament.name} Matches***")

        if past_matches:
            paginator.add_line("")
            paginator.add_line(f"**Ended Matches:**")
            past_matches.sort(key=lambda x: x.id)
            for match in past_matches:
                team1: models.Team = match.team1
                team2: models.Team = match.team2
                team1_emoji = self.bot.get_emoji(team1.emoji)
                team2_emoji = self.bot.get_emoji(team2.emoji)
                if match.result == 1:
                    match_content = f"{match.id_in_tournament}. {match.name}: **{team1_emoji} {team1.name}** vs {team2.name} {team2_emoji} - BO{match.bestof} - Result: {match.win_games}-{match.lose_games}"
                elif match.result == 2:
                    match_content = f"{match.id_in_tournament}. {match.name}: {team1_emoji} {team1.name} vs **{team2.name} {team2_emoji}** - BO{match.bestof} - Result: {match.lose_games}-{match.win_games}"
                paginator.add_line(match_content)

        if closed_matches:
            paginator.add_line("")
            paginator.add_line(f"**Closed Matches:**")
            closed_matches.sort(key=lambda x: x.id)
            for match in closed_matches:
                team1: models.Team = match.team1
                team2: models.Team = match.team2
                team1_emoji = self.bot.get_emoji(team1.emoji)
                team2_emoji = self.bot.get_emoji(team2.emoji)
                match_content = f"{match.id_in_tournament}. {match.name}: {team1_emoji} {team1.name} vs {team2.name} {team2_emoji} - BO{match.bestof}"
                paginator.add_line(match_content)
        if active_matches:
            paginator.add_line("")
            paginator.add_line(f"**Open Matches:**")
            active_matches.sort(key=lambda x: x.id)
            for match in active_matches:
                team1: models.Team = match.team1
                team2: models.Team = match.team2
                team1_emoji = self.bot.get_emoji(team1.emoji)
                team2_emoji = self.bot.get_emoji(team2.emoji)
                match_content = f"{match.id_in_tournament}. {match.name}: {team1_emoji} {team1.name} vs {team2.name} {team2_emoji} - BO{match.bestof}"
                paginator.add_line(match_content)

        if not (past_matches or closed_matches or active_matches):
            paginator.add_line("There are no matches in this tournament.")

        for page in paginator.pages:
            await ctx.send(page)

    # ----------------------------- EVENTS -----------------------------

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Removes other reactions in the same category as the new reaction from a match post. Basically turns the reactions into a (shitty) radio button."""
        # Check if message is a match
        # We don't care about our own reactions
        if payload.user_id == self.bot.user.id:
            return False

        # Check if message is a match or in dialogs
        match = (
            await models.Match.filter(message=payload.message_id)
            .select_related("team1", "team2")
            .first()
        )
        if match is not None and match.running == models.MatchRunningEnum.RUNNING:
            # Fetch channel and message
            channel = self.bot.get_channel(payload.channel_id)
            message: discord.Message = await channel.fetch_message(payload.message_id)

            to_remove = set()
            emoji: discord.PartialEmoji = payload.emoji

            # Team
            team_emoji = {match.team1.emoji, match.team2.emoji}
            if emoji.id in team_emoji:
                team_emoji.remove(emoji.id)
                to_remove.update({str(self.bot.get_emoji(e)) for e in team_emoji})

            # Games
            if match.bestof > 1:
                games_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"][
                    math.floor(match.bestof / 2) : match.bestof
                ]
                games_emojis = set(games_emojis)
                if str(emoji) in games_emojis:
                    games_emojis.remove(str(emoji))
                    to_remove.update(games_emojis)

            async def reaction_get_users(reaction):
                return (reaction, [u.id for u in await reaction.users().flatten()])

            async def remove_reaction(reaction: discord.Reaction):
                str_react = str(reaction)
                if str_react not in to_remove:
                    return
                await reaction.remove(discord.Object(payload.user_id))

            coro_list = [
                reaction_get_users(r)
                for r in message.reactions
                if str(r.emoji) in to_remove
            ]
            reaction_users = await asyncio.gather(*coro_list)

            coro_list = [
                remove_reaction(r)
                for (r, u_id) in reaction_users
                if payload.user_id in u_id
            ]
            await asyncio.gather(*coro_list)

        # Check if message is a dialog message
        if (payload.message_id in self.dialogs.keys()) and (str(payload.emoji) == "✅"):
            # Fetch channel and message
            channel: discord.abc.Messageable = self.bot.get_channel(payload.channel_id)
            message: discord.Message = await channel.fetch_message(payload.message_id)

            # Check if user has manage messages permission
            perms = payload.member.permissions_in(channel)
            if not perms.manage_messages:
                await message.remove_reaction(
                    payload.emoji, discord.Object(payload.user_id)
                )
                return

            # End match

            # Fetch match
            match = (
                await models.Match.filter(message=self.dialogs[payload.message_id])
                .select_related("team1", "team2")
                .first()
            )

            # Find choices
            team_choice = 0
            game_choice = 1

            games_emojis = []
            # Find games choice
            if match.bestof > 1:
                games_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"][
                    math.floor(match.bestof / 2) : match.bestof
                ]
                game_choice = 0

            for r in message.reactions:
                if r.custom_emoji and r.emoji.id in [
                    match.team1.emoji,
                    match.team2.emoji,
                ]:
                    react_user = await r.users().get(id=payload.user_id)
                    if react_user is not None:
                        if team_choice == 0:
                            if r.emoji.id == match.team1.emoji:
                                team_choice = 1  # team 1
                            else:
                                team_choice = 2  # team 2
                        else:
                            team_choice = -1  # two teams selected -> invalid
                if not r.custom_emoji and str(r.emoji) in games_emojis:
                    react_user = await r.users().get(id=payload.user_id)
                    if react_user is not None:
                        if game_choice == 0:
                            index = games_emojis.index(str(r.emoji))
                            game_choice = math.floor(match.bestof / 2) + index + 1
                        else:
                            game_choice = -1  # two+ game choices selected -> invalid

            if team_choice == -1:
                await channel.send("You can only select one team!")
                await message.remove_reaction("✅", discord.Object(payload.user_id))
                return
            if team_choice == 0:
                await channel.send("You must select a team!")
                await message.remove_reaction("✅", discord.Object(payload.user_id))
                return

            if game_choice == -1:
                await channel.send("You can only select one amount of games!")
                await message.remove_reaction("✅", discord.Object(payload.user_id))
                return
            if game_choice == 0:
                await channel.send("You must select an amount of games!")
                await message.remove_reaction("✅", discord.Object(payload.user_id))
                return

            await self.tournament_manager.end_match(match, team_choice, game_choice)

            # Delete dialog
            await message.delete()
            self.dialogs.pop(payload.message_id)

    async def cog_command_error(self, ctx, error):
        message = ""

        if isinstance(error, commands.CommandInvokeError):
            if isinstance(error.original, TournamentException):
                message = f"ERROR: {error.original.reason}"

        if len(message) > 0:
            await ctx.send(f"`{message}`")
            ctx.handled = True


def setup(bot):
    bot.add_cog(TournamentCog(bot))
