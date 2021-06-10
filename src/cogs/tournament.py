import asyncio
import math
import re
import uuid
from datetime import datetime, timedelta
from typing import Optional

import discord
from discord.abc import Messageable
from discord.errors import HTTPException
from discord.ext import commands, tasks

from src.aiomediawiki.aiomediawiki import APIException, leaguepedia
from src.aiomediawiki.tables.matchschedule import MatchScheduleRow
from src.aiomediawiki.tables.teams import TeamsRow
from src.utils import decorators
from src.utils.converters import BestOfXConverter, CodeConverter
from src.utils.database import Database, Match, Team, Tournament, User, UserMatch


# Exceptions
class TournamentAlreadyRunning(Exception):
    tournament: Tournament

    def __init__(self, tournament: Tournament):
        self.tournament = tournament
        super().__init__()


class TournamentAlreadyExists(Exception):
    tournament: Tournament

    def __init__(self, tournament: Tournament):
        self.tournament = tournament
        super().__init__()


class TournamentNotRunning(Exception):
    def __init__(self):
        super().__init__()


class NoTournament(Exception):
    reason: str

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__()


class CantEndTournament(Exception):
    tournament: Tournament
    reason: str

    def __init__(self, tournament: Tournament, reason: str):
        self.tournament = tournament
        self.reason = reason
        super().__init__()


class MatchAlreadyExists(Exception):
    match: Match

    def __init__(self, match: Match):
        self.match = match
        super().__init__()


class CantEndMatch(Exception):
    match: Match
    reason: str

    def __init__(self, match: Match, reason: str):
        self.match = match
        self.reason = reason
        super().__init__()


class CantCloseMatch(Exception):
    match: Match
    reason: str

    def __init__(self, match: Match, reason: str):
        self.match = match
        self.reason = reason
        super().__init__()


class MatchDoesntExist(Exception):
    def __init__(self):
        super().__init__()


class TournamentCog(commands.Cog, name="Tournament"):
    score_table: dict[str, int] = {
        "bo1_team": 1,
        "bo3_team": 2,
        "bo3_games": 1,
        "bo5_team": 3,
        "bo5_games": 1,
    }
    dialogs: dict[int, int] = {}  # (dialog message, match message)
    # http:// or https://
    link_validation_regex = re.compile(r"^(?:http)s?://", re.IGNORECASE)

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_fandom_matches_task.start()

    def cog_unload(self):
        self.update_fandom_matches_task.stop()

    # ------------------------------ TASKS -----------------------------

    @tasks.loop(minutes=5)
    async def update_fandom_matches_task(self):
        fandom_tournaments = await Database.get_running_fandom_tournaments()
        for tournament in fandom_tournaments:
            await self.update_fandom_matches(tournament)

    async def update_fandom_matches(self, tournament: Tournament):
        tabs = await leaguepedia.get_tabs_before(
            tournament.fandomOverviewPage, datetime.now() + timedelta(days=4)
        )

        fandommatches = await leaguepedia.get_matches_in_tabs(
            tournament.fandomOverviewPage,
            tabs,
        )

        any_closed: bool = False

        for fandommatch in fandommatches:
            # Check if match already exists
            match = await Database.get_match_by_fandommatchid(
                fandommatch.match_id, tournament.id
            )
            if match is None:
                if fandommatch.winner is None:
                    # Match does not exist yet
                    team1 = await Database.get_team_by_fandomoverviewpage(
                        fandommatch.team1, tournament.guild
                    )
                    team2 = await Database.get_team_by_fandomoverviewpage(
                        fandommatch.team2, tournament.guild
                    )
                    try:
                        await self.start_match(
                            tournament=tournament,
                            name=f"{fandommatch.tab} Match {fandommatch.n_matchintab}",
                            team1=team1,
                            team2=team2,
                            bestof=fandommatch.best_of,
                            fandomMatchId=fandommatch.match_id,
                        )
                    except Exception:
                        pass
            elif match.running != 0:
                # Match is running or closed, check if we should close/end it
                if (
                    match.running == 1
                    and (fandommatch.start - timedelta(minutes=30)) < datetime.now()
                ):
                    # Close it
                    await self.close_match(match)

                if fandommatch.winner is not None:
                    any_closed = True
                    await self.end_match(
                        match,
                        fandommatch.winner,
                        fandommatch.team1_score + fandommatch.team2_score,
                        update_tournament_message=False,
                    )
        if any_closed:
            await self.update_tournament_message(tournament)

    # ----------------------------- UTILITY ----------------------------

    async def start_match(
        self,
        tournament: Tournament,
        name: str,
        team1: Team,
        team2: Team,
        bestof: int,
        fandomMatchId: str = None,
    ):
        # Calculate match id
        id = await Database.get_num_matches(tournament.id) + 1

        channel: discord.abc.Messageable = self.bot.get_channel(tournament.channel)
        message: discord.Message = await channel.send("A match is starting...")

        # Insert
        match = Match(
            id,
            name,
            tournament.guild,
            message.id,
            1,
            0,
            0,
            team1.code,
            team2.code,
            tournament.id,
            bestof,
            fandomMatchId,
        )
        try:
            await Database.insert_match(match)
        except Exception as e:
            await message.delete()
            raise e

        await self.update_match_message(match)

        # Add Team reacts
        await message.add_reaction(self.bot.get_emoji(team1.emoji))
        await message.add_reaction(self.bot.get_emoji(team2.emoji))

        # Add Games reacts
        games_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

        if bestof > 1:
            for i in range(math.floor(bestof / 2), bestof):
                await message.add_reaction(games_emojis[i])

    async def close_match(
        self,
        match: Match,
    ):
        await self.save_votes(match)

        match.running = 2
        await Database.update_match(match)

        await self.update_match_message(match)

    async def end_match(
        self,
        match: Match,
        team: int,
        games: int,
        update_tournament_message: bool = True,
    ):
        match.running = 0
        match.games = games
        match.result = team
        match.__post_init__()  # Refresh winning and losing games

        await Database.update_match(match)

        tournament = await Database.get_tournament(match.tournament)
        await self.update_match_message(match)
        if update_tournament_message:
            await self.update_tournament_message(tournament)

        # Send update message if necesary
        if tournament.updatesChannel is not None:
            channel = self.bot.get_channel(tournament.updatesChannel)
            # get all winning users
            ums: list[UserMatch] = await Database.get_usermatch_by_match(
                match.id, match.tournament
            )

            team_winners: list[str] = []
            for um in ums:
                if um.team == match.result:
                    user = await Database.get_user(um.user_id)
                    team_winners.append(user.name)
            team_winners.sort()

            msg = f"**Match {match.id} ({match.name}) has ended!**"

            if len(team_winners) == 0:
                msg += "\n**Noone** predicted the correct team."
            elif len(team_winners) == 1:
                msg += f"\n**{team_winners[0]}** predicted the correct team."
            elif len(team_winners) == 2:
                msg += f"\n**{team_winners[0]} and {team_winners[1]}** predicted the correct team."
            else:
                msg += f"\n**{', '.join(team_winners[:-1])}, and {team_winners[-1]}** predicted the correct team."

            if match.bestof > 1:
                game_winners: list[str] = []
                for um in ums:
                    if um.games == match.games:
                        user = await Database.get_user(um.user_id)
                        game_winners.append(user.name)
                game_winners.sort()

                if len(game_winners) == 0:
                    msg += "\n**Noone** predicted the correct amount of games."
                elif len(game_winners) == 1:
                    msg += f"\n**{game_winners[0]}** predicted the correct amount of games."
                elif len(game_winners) == 2:
                    msg += f"\n**{game_winners[0]} and {game_winners[1]}** predicted the correct amount of games."
                else:
                    msg += f"\n**{', '.join(game_winners[:-1])}, and {game_winners[-1]}** predicted the correct amount of games."

            await channel.send(msg)

    async def update_fandom_teams(
        self, tournament_overviewpage: str, guild_id: int
    ) -> bool:
        teams = await leaguepedia.get_teams(tournament_overviewpage)
        guild: discord.Guild = self.bot.get_guild(guild_id)
        guild_teams = await Database.get_teams_by_guild(guild_id)

        teams_to_create: list[TeamsRow] = []

        # Figure out which teams we need to add
        for team in teams:
            t = discord.utils.get(guild_teams, code=team.short.lower())
            if t is None:
                teams_to_create.append(team)
            elif not t.isfandom:
                # Take control of teams with the correct name already
                t.fandomOverviewPage = team.overviewPage
                t.isfandom = True
                await Database.update_team(t.code, t)

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

            await Database.insert_team(
                Team(
                    team.name,
                    team.short.lower(),
                    emoji.id,
                    guild_id,
                    True,
                    team.overviewPage,
                )
            )
            return False

        coro_list = [add_team(t) for t in teams_to_create]
        # for coro in coro_list:
        #     await coro
        for f in asyncio.as_completed(coro_list):
            error = (await f) or error

        return error

    async def save_votes(self, match: Match) -> bool:
        tournament = await Database.get_tournament(match.tournament)
        channel = self.bot.get_channel(tournament.channel)
        message = await channel.fetch_message(match.message)
        reactions: list[discord.Reaction] = message.reactions

        team1 = await Database.get_team(match.team1, match.guild)
        team2 = await Database.get_team(match.team2, match.guild)

        team_emojis = [team1.emoji, team2.emoji]
        games_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        games_emojis = games_emojis[math.floor(match.bestof / 2) : match.bestof]

        user_set = set()
        team_dict: dict[int, int] = dict()
        games_dict: dict[int, int] = dict()

        for reaction in reactions:
            users = await reaction.users().flatten()
            if reaction.custom_emoji and (reaction.emoji.id in team_emojis):
                team = team_emojis.index(reaction.emoji.id) + 1
                for user in users:
                    if user == self.bot.user:
                        continue
                    team_dict[user.id] = team
                    user_set.add(user)
            if not reaction.custom_emoji and (reaction.emoji in games_emojis):
                games = games_emojis.index(reaction.emoji) + math.ceil(match.bestof / 2)
                for user in users:
                    if user == self.bot.user:
                        continue
                    games_dict[user.id] = games
                    user_set.add(user)

        for user in user_set:
            # Update user table
            db_user = await Database.get_user(user.id)
            if db_user is not None:
                if db_user.name != user.name + "#" + user.discriminator:
                    db_user.name = user.name + "#" + user.discriminator
                    await Database.update_user(db_user)
            else:
                db_user = User(user.id, user.name + "#" + user.discriminator)
                await Database.insert_user(db_user)

            # Insert usermatch
            usermatch = UserMatch(
                user.id,
                match.id,
                match.tournament,
                team_dict.get(user.id, 0),
                games_dict.get(user.id, 0),
            )
            await Database.insert_usermatch(usermatch)
        return True

    async def generate_leaderboard(self, tournament: Tournament) -> str:
        # Leaderboard
        leaderboard = await Database.get_leaderboard(tournament.id, self.score_table)
        leaderboard_strings = []
        rank = 0
        prev_rank_score = -1
        players = 0

        rank_size = 0
        name_size = 0
        score_size = 0
        correct_size = 0
        percent_size = 0
        entries = []

        if len(leaderboard) > 0:
            for entry in leaderboard:
                user_name, user_score, user_correct, user_total, user_percent = entry

                players += 1
                if prev_rank_score != user_score:
                    prev_rank_score = user_score
                    rank = players

                user_correct = f"{user_correct}/{user_total}"
                user_percent = f"({user_percent:.1f}%)"

                rank_size = max(len(str(rank)), rank_size)
                name_size = max(len(str(user_name)), name_size)
                score_size = max(len(str(user_score)), score_size)
                correct_size = max(len(str(user_correct)), correct_size)
                percent_size = max(len(str(user_percent)), percent_size)

                entries.append(
                    [
                        rank,
                        user_name,
                        user_score,
                        user_correct,
                        user_percent,
                    ]
                )

            for entry in entries:
                (
                    rank,
                    user_name,
                    user_score,
                    user_correct,
                    user_percent,
                ) = entry
                leaderboard_strings.append(
                    f"{rank:>{rank_size}}  -  {user_name:<{name_size}} {user_score:>{score_size}} points  -  {user_correct:>{correct_size}} correct {user_percent:>{percent_size}}"
                )
            leaderboard_str = "\n".join(leaderboard_strings)
        else:
            leaderboard_str = ""
        return leaderboard_str

    async def generate_tournament_message(self, tournament: Tournament):
        channel = self.bot.get_channel(tournament.channel)
        if channel is None:
            return ""
        guild = channel.guild

        teams: dict[str, Team] = dict()
        for team in await Database.get_teams_by_guild(guild.id):
            teams[team.code] = team

        # Header
        content_header = f"**{tournament.name}**"
        if tournament.isfandom:
            content_header += f" ({leaguepedia.wiki_url}{tournament.fandomOverviewPage.replace(' ', '_')})"
        if tournament.running == 0:
            content_header += f" - Ended"
        content_header += "\n\n"

        # Scoring table
        content_scoring_table = f"***Scoring Table***\n```Correct team - BO1: {self.score_table['bo1_team']}\nCorrect team - BO3: {self.score_table['bo3_team']}\tCorrect number of games - BO3: {self.score_table['bo3_games']}\nCorrect team - BO5: {self.score_table['bo5_team']}\tCorrect number of games - BO5: {self.score_table['bo5_games']}```\n"

        leaderboard_str = await self.generate_leaderboard(tournament)
        if leaderboard_str:
            content_leaderboard = f"***Leaderboard***\n```c\n{leaderboard_str}```\n"
        else:
            content_leaderboard = ""

        # Combine
        content = (
            f"{content_header}{content_scoring_table}{content_leaderboard}".strip()
        )

        return content

    async def generate_match_message(self, match: Match):
        teams: dict[str, Team] = dict()
        for team in await Database.get_teams_by_guild(match.guild):
            teams[team.code] = team

        team1 = teams[match.team1]
        team1_emoji = self.bot.get_emoji(team1.emoji)
        team2 = teams[match.team2]
        team2_emoji = self.bot.get_emoji(team2.emoji)

        match_message_header = f"**{match.id}. {match.name}** - *BO{match.bestof}*"
        if match.running != 0:
            if match.running == 2:
                match_message_header += " - Closed"
            match_message_footer = (
                f"{team1_emoji} {team1.name} vs {team2.name} {team2_emoji}"
            )
        else:
            if match.result == 1:
                match_message_header += (
                    f" - Result: {match.win_games}-{match.lose_games}"
                )
                match_message_footer = (
                    f"**{team1_emoji} {team1.name}** vs {team2.name} {team2_emoji}"
                )
            else:
                match_message_header += (
                    f" - Result: {match.lose_games}-{match.win_games}"
                )
                match_message_footer = (
                    f"{team1_emoji} {team1.name} vs **{team2.name} {team2_emoji}**"
                )

        return match_message_header + "\n" + match_message_footer

    async def update_tournament_message(self, tournament):
        channel = self.bot.get_channel(tournament.channel)
        if channel is None:
            return

        try:
            message = await channel.fetch_message(tournament.message)
        except (discord.NotFound, discord.Forbidden):
            return

        content = await self.generate_tournament_message(tournament)

        await message.edit(content=content)

    async def update_match_message(self, match):
        tournament: Optional[Tournament] = await Database.get_tournament(
            match.tournament
        )

        tournament_channel = self.bot.get_channel(tournament.channel)
        if tournament_channel is None:
            return

        try:
            match_message = await tournament_channel.fetch_message(match.message)
        except (discord.NotFound, discord.Forbidden):
            return

        content = await self.generate_match_message(match)

        await match_message.edit(content=content)

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
        tournament = await Database.get_running_tournament(ctx.channel.id)
        # Check if tournament already running
        if tournament is not None:
            raise TournamentAlreadyRunning(tournament)

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

            fandomTournament = await leaguepedia.get_tournament(page_title)
            if not fandomTournament:
                await ctx.send(f"This is not a tournament overview page.")
                return

            tournament_name = fandomTournament.name

        # We have verified the tournament can be started
        async with ctx.typing():
            if is_link:
                message: discord.Message = await ctx.send("Adding teams...")

                error = await self.update_fandom_teams(
                    fandomTournament.overviewPage,
                    ctx.guild.id,
                )

                if error:
                    await message.edit(
                        content="There was an error while creating the teams. Perhaps the bot doesn't have permission to create new emoji or there aren't any emote slots left."
                    )
                    return

                await message.edit(content="Tournament is starting...")
            else:
                message: discord.Message = await ctx.send("Tournament is starting...")

            # Check if tournament by this name already exists
            # If yes, add a number behind it
            base_name = tournament_name
            i = 1
            tournament = await Database.get_tournament_by_name(
                tournament_name,
                ctx.guild.id,
            )
            while tournament:
                tournament_name = base_name + f" ({i})"
                i += 1
                tournament = await Database.get_tournament_by_name(
                    tournament_name,
                    ctx.guild.id,
                )

            tournament = Tournament(
                uuid.uuid4(),
                tournament_name,
                ctx.channel.id,
                ctx.guild.id,
                message.id,
                1,
            )

            if is_link:
                tournament.isfandom = True
                tournament.fandomOverviewPage = fandomTournament.overviewPage

            try:
                await Database.insert_tournament(tournament)
            except Exception as e:
                await message.delete()
                raise e
            await self.update_tournament_message(tournament)
            await ctx.message.delete()

            if tournament.isfandom:
                # Create matches and stuff
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
        tournament = await Database.get_running_tournament(ctx.channel.id)
        if tournament is None:
            raise TournamentNotRunning

        # Check if there are still matches not ended
        running_matches = await Database.get_matches_by_state(tournament.id, 1)
        closed_matches = await Database.get_matches_by_state(tournament.id, 2)

        if len(running_matches) > 0:
            raise CantEndTournament(tournament, "There are still open matches")

        if len(closed_matches) > 0:
            raise CantEndTournament(tournament, "There are still closed matches")

        tournament.running = 0
        await Database.update_tournament(tournament)

        await self.update_tournament_message(tournament)
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
            tournament = await Database.get_tournament_by_name(name, ctx.guild.id)
            txt = "No tournament with this name exists in this guild."
        else:
            tournament = await Database.get_running_tournament(ctx.channel.id)
            txt = "No tournament is running in this channel."

        # Check if tournament exists
        if tournament is None:
            raise NoTournament(txt)

        content = await self.generate_tournament_message(tournament)
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
        tournament = await Database.get_tournament_by_name(name, ctx.guild.id)
        txt = "No tournament with this name exists in this guild."

        # Check if tournament exists
        if tournament is None:
            raise NoTournament(txt)

        tournament.updatesChannel = ctx.channel.id
        await Database.update_tournament(tournament)
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
        tournaments: list[Tournament] = await Database.get_tournaments_by_guild(
            ctx.guild.id
        )

        paginator = commands.Paginator(max_size=2000, prefix="", suffix="")

        if tournaments:
            paginator.add_line("**Tournaments:**")
            for tournament in tournaments:
                channel: discord.Channel = self.bot.get_channel(tournament.channel)
                line = f"{tournament.name} - Channel: {channel.mention}"
                if tournament.running == 0:
                    line += " - Ended"
                paginator.add_line(line)
        else:
            paginator.add_line("There are no tournaments in this server.")

        for page in paginator.pages:
            await ctx.send(page)

    @match_group.command(
        name="start",
        brief="Starts a match.",
        description="Creates a new match between two teams.\n\nArguments:\n-Match name can contain spaces.\n-Short codes must be for teams that exist in this server.\n-X must be 1, 3 or 5.",
        aliases=["s"],
        usage="<match name> <short code team 1> <short code team 2> bo<X>",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @decorators.regex_arguments("(.+) (\\S+) (\\S+) (\\S+)")
    async def match_start(
        self,
        ctx,
        name: str,
        team1_code: CodeConverter(True),
        team2_code: CodeConverter(True),
        bestof: BestOfXConverter,
    ):
        # Check if tournament running
        tournament = await Database.get_running_tournament(ctx.channel.id)
        if tournament is None:
            raise TournamentNotRunning()

        team1: Optional[Team] = await Database.get_team(team1_code, ctx.guild.id)
        team2: Optional[Team] = await Database.get_team(team2_code, ctx.guild.id)

        await self.start_match(tournament, name.strip(), team1, team2, bestof)

        await ctx.message.delete()

    @match_group.command(
        name="close",
        brief="Closes predictions for a match.",
        description='Closes predictions on the specified matches.\n\nArguments:\n-Match ids, which is the number in the match message before the dot (e.g. in "23. Group Stage Game 4", the match id is 23).\n-The match ids should be seperated by spaces',
        aliases=["c"],
        usage="<ids>",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def match_close(self, ctx, *ids: int):
        # Validate input
        # Check if tournament running
        tournament = await Database.get_running_tournament(ctx.channel.id)
        if tournament is None:
            raise TournamentNotRunning()

        errors = []
        for id in ids:
            # Is name a running match
            match = await Database.get_match(id, tournament.id)
            if match is None:
                errors += [f"Match with id {id} does not exist."]
                continue
            if match.running != 1:
                errors += [f"Match with id {id} is not an open match."]
                continue

            await self.close_match(match)
        if errors:
            await ctx.send("\n".join(errors))
        await ctx.message.delete()

    @match_group.command(
        name="end",
        brief="Ends a match.",
        description='Ends the match.\n\nArguments:\n\nArguments:\n-Match ids, which is the number in the match message before the dot (e.g. in "23. Group Stage Game 4", the match id is 23).\n-The match ids should be seperated by spaces',
        aliases=["e"],
        usage="<ids>",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def match_end(self, ctx, *ids: int):
        # Validate input
        # Check if tournament running
        tournament = await Database.get_running_tournament(ctx.channel.id)
        if tournament is None:
            raise TournamentNotRunning()

        for id in ids:
            # Is reference a running or closed match
            match = await Database.get_match(id, tournament.id)
            if match is None:
                raise MatchDoesntExist()
            if match.running not in (1, 2):
                raise CantEndMatch(match, "This match has already ended.")

            if match.running == 1:
                await self.save_votes(match, tournament)

                match.running = 2
                await Database.update_match(match)

                await self.update_match_message(match)

            # Check if dialog already exists
            if match.message in self.dialogs.values():
                await ctx.send("This match is already being ended!")
                return

            # Create dialog message
            txt = f'**Match End:** Which team won in match {match.id} "{match.name}"'
            if match.bestof > 1:
                txt += " and in how many games"
            txt += "? Press ✅ after you're done to end the match."
            message: discord.Message = await ctx.send(txt)

            self.dialogs[message.id] = match.message

            team1 = await Database.get_team(match.team1, tournament.guild)
            team2 = await Database.get_team(match.team2, tournament.guild)

            # Add Team reacts
            await message.add_reaction(self.bot.get_emoji(team1.emoji))
            await message.add_reaction(self.bot.get_emoji(team2.emoji))

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
        tournament: Optional[Tournament] = await Database.get_running_tournament(
            ctx.channel.id
        )
        if tournament is None:
            raise TournamentNotRunning()

        match: Optional[Match] = await Database.get_match(id, tournament.id)
        if match is None:
            raise MatchDoesntExist()

        if match.running == 1:
            # Fix emoji
            message: discord.Message = await ctx.channel.fetch_message(match.message)

            for reaction in message.reactions:
                if reaction.me:
                    await reaction.remove(self.bot.user)

            team1: Optional[Team] = await Database.get_team(match.team1, match.guild)
            team2: Optional[Team] = await Database.get_team(match.team2, match.guild)

            await message.add_reaction(self.bot.get_emoji(team1.emoji))
            await message.add_reaction(self.bot.get_emoji(team2.emoji))

            # Add Games reacts
            games_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

            if match.bestof > 1:
                for i in range(math.floor(match.bestof / 2), match.bestof):
                    await message.add_reaction(games_emojis[i])

        # Fix name
        await self.update_match_message(match)

    @match_group.command(
        name="list",
        brief="Lists all matches in a tournament.",
        description="Lists all current and past matches in the provided tournament. If no tournament is provided, lists matches in the currently running tournament.",
        aliases=["l", "ls"],
        usage="[tournament name]",
    )
    @commands.guild_only()
    async def matches_list(self, ctx, *, name: Optional[str]):
        tournament: Tournament
        if name is None:
            tournament = await Database.get_running_tournament(ctx.channel.id)
            if tournament is None:
                raise TournamentNotRunning()
        else:
            tournament: Tournament = await Database.get_tournament_by_name(
                name, ctx.guild.id
            )
            if tournament is None:
                raise NoTournament("No tournament by that name exists in this server.")

        teams: dict[str, Team] = dict()
        for team in await Database.get_teams_by_guild(tournament.guild):
            teams[team.code] = team

        past_matches: list[Match] = await Database.get_matches_by_state(
            tournament.id, 0
        )
        closed_matches: list[Match] = await Database.get_matches_by_state(
            tournament.id, 2
        )
        active_matches: list[Match] = await Database.get_matches_by_state(
            tournament.id, 1
        )

        paginator = commands.Paginator(max_size=2000, prefix="", suffix="")
        paginator.add_line(f"***{tournament.name} Matches***")

        if past_matches:
            paginator.add_line("")
            paginator.add_line(f"**Ended Matches:**")
            past_matches.sort(key=lambda x: x.id)
            for match in past_matches:
                team1 = teams[match.team1]
                team2 = teams[match.team2]
                team1_emoji = self.bot.get_emoji(team1.emoji)
                team2_emoji = self.bot.get_emoji(team2.emoji)
                if match.result == 1:
                    match_content = f"{match.id}. {match.name}: **{team1_emoji} {team1.name}** vs {team2.name} {team2_emoji} - BO{match.bestof} - Result: {match.win_games}-{match.lose_games}"
                elif match.result == 2:
                    match_content = f"{match.id}. {match.name}: {team1_emoji} {team1.name} vs **{team2.name} {team2_emoji}** - BO{match.bestof} - Result: {match.lose_games}-{match.win_games}"
                paginator.add_line(match_content)

        if closed_matches:
            paginator.add_line("")
            paginator.add_line(f"**Closed Matches:**")
            closed_matches.sort(key=lambda x: x.id)
            for match in closed_matches:
                team1 = teams[match.team1]
                team2 = teams[match.team2]
                team1_emoji = self.bot.get_emoji(team1.emoji)
                team2_emoji = self.bot.get_emoji(team2.emoji)
                match_content = f"{match.id}. {match.name}: {team1_emoji} {team1.name} vs {team2.name} {team2_emoji} - BO{match.bestof}"
                paginator.add_line(match_content)
        if active_matches:
            paginator.add_line("")
            paginator.add_line(f"**Open Matches:**")
            active_matches.sort(key=lambda x: x.id)
            for match in active_matches:
                team1 = teams[match.team1]
                team2 = teams[match.team2]
                team1_emoji = self.bot.get_emoji(team1.emoji)
                team2_emoji = self.bot.get_emoji(team2.emoji)
                match_content = f"{match.id}. {match.name}: {team1_emoji} {team1.name} vs {team2.name} {team2_emoji} - BO{match.bestof}"
                paginator.add_line(match_content)

        if not (past_matches or closed_matches or active_matches):
            paginator.add_line("There are no matches in this tournament.")

        for page in paginator.pages:
            await ctx.send(page)

    @commands.command(
        name="debug",
    )
    @commands.guild_only()
    async def debug(self, ctx, n: int):
        tournament = await Database.get_running_tournament(ctx.channel.id)
        self.update_fandom_matches(tournament)

    # ----------------------------- EVENTS -----------------------------

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Removes other reactions in the same category as the new reaction from a match post. Basically turns the reactions into a (shitty) radio button."""
        # Check if message is a match
        # We don't care about our own reactions
        if payload.user_id == self.bot.user.id:
            return False

        # Check if message is a match or in dialogs
        match: Optional[Match] = await Database.get_match_by_message(payload.message_id)
        if match is not None and match.running == 1:
            # Fetch channel and message
            channel = self.bot.get_channel(payload.channel_id)
            message: discord.Message = await channel.fetch_message(payload.message_id)

            team1: Optional[Team] = await Database.get_team(match.team1, match.guild)
            team2: Optional[Team] = await Database.get_team(match.team2, match.guild)

            to_remove = set()
            emoji: discord.PartialEmoji = payload.emoji

            # Team
            team_emoji = {team1.emoji, team2.emoji}
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

            reaction_users = []
            for f in asyncio.as_completed(
                [
                    reaction_get_users(r)
                    for r in message.reactions
                    if str(r.emoji) in to_remove
                ]
            ):
                reaction_users.append(await f)

            coro_list = [
                remove_reaction(r)
                for (r, u_id) in reaction_users
                if payload.user_id in u_id
            ]
            for f in asyncio.as_completed(coro_list):
                await f

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
            match: Optional[Match] = await Database.get_match_by_message(
                self.dialogs[payload.message_id]
            )

            team1: Optional[Team] = await Database.get_team(match.team1, match.guild)
            team2: Optional[Team] = await Database.get_team(match.team2, match.guild)

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
                if r.custom_emoji and r.emoji.id in [team1.emoji, team2.emoji]:
                    react_user = await r.users().get(id=payload.user_id)
                    if react_user is not None:
                        if team_choice == 0:
                            if r.emoji.id == team1.emoji:
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

            await self.end_match(match, game_choice, team_choice)

            # Delete dialog
            await message.delete()
            self.dialogs.pop(payload.message_id)

    async def cog_command_error(self, ctx, error):
        message = ""

        if isinstance(error, commands.CommandInvokeError):
            if isinstance(error.original, TournamentAlreadyExists):
                message = f"A tournament with the name {error.original.tournament.name} already exists."
            if isinstance(error.original, TournamentAlreadyRunning):
                message = f"There is already a running tournament in this channel. You can only have one running tournament per channel."
            if isinstance(error.original, TournamentNotRunning):
                message = "No tournament is running."
            if isinstance(error.original, CantEndTournament):
                message = f"Could not end tournament {error.original.tournament.name} ({error.original.reason})."
            if isinstance(error.original, NoTournament):
                message = f"Could not find tournament ({error.original.reason})."
            if isinstance(error.original, MatchAlreadyExists):
                message = f'A match with the name "{error.original.match.name}" already exists.'
            if isinstance(error.original, MatchDoesntExist):
                message = f"No match was found (Maybe you made a typo in the name)."
            if isinstance(error.original, CantEndMatch):
                message = f'Could not end match "{error.original.match.name}" ({error.original.reason}).'
            if isinstance(error.original, CantCloseMatch):
                message = f'Could not close match "{error.original.match.name}" ({error.original.reason}).'

        if len(message) > 0:
            await ctx.send(f"`{message}`")
            ctx.handled = True
            return


def setup(bot):
    bot.add_cog(TournamentCog(bot))
