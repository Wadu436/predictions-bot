import math
import uuid
from os import error
from typing import Optional

import discord
from discord import team
from discord.ext import commands

from src import decorators
from src.cogs.database import DatabaseCog, Match, Team, Tournament, User, UserMatch
from src.converters import BestOfXConverter, CodeConverter


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

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ----------------------------- UTILITY ----------------------------

    async def save_votes(self, match: Match, tournament: Tournament) -> bool:
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        channel = self.bot.get_channel(tournament.channel)
        message = await channel.fetch_message(match.message)
        reactions: list[discord.Reaction] = message.reactions

        team1 = await db_cog.get_team(match.team1, match.guild)
        team2 = await db_cog.get_team(match.team2, match.guild)

        team_emojis = [team1.emoji, team2.emoji]
        games_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        games_emojis = games_emojis[math.floor(match.bestof / 2) : match.bestof]

        user_set = set()
        team_dict: dict[int, int] = dict()
        games_dict: dict[int, int] = dict()

        for reaction in reactions:
            if str(reaction) not in team_emojis + games_emojis:
                continue

            users = await reaction.users().flatten()

            if str(reaction) in team_emojis:
                team = team_emojis.index(str(reaction)) + 1
                for user in users:
                    if user == self.bot.user:
                        continue
                    team_dict[user.id] = team
                    user_set.add(user)

            elif str(reaction) in games_emojis:
                games = games_emojis.index(str(reaction)) + math.ceil(match.bestof / 2)
                for user in users:
                    if user == self.bot.user:
                        continue
                    games_dict[user.id] = games
                    user_set.add(user)

        for user in user_set:
            # Update user table
            db_user = await db_cog.get_user(user.id)
            if db_user is not None:
                if db_user.name != user.name + "#" + user.discriminator:
                    db_user.name = user.name + "#" + user.discriminator
                    await db_cog.update_user(db_user)
            else:
                db_user = User(user.id, user.name + "#" + user.discriminator)
                await db_cog.insert_user(db_user)

            # Insert usermatch
            usermatch = UserMatch(
                user.id,
                match.id,
                match.tournament,
                team_dict.get(user.id, 0),
                games_dict.get(user.id, 0),
            )
            await db_cog.insert_usermatch(usermatch)
        return True

    async def generate_leaderboard(self, tournament: Tournament) -> str:
        db_cog = self.bot.get_cog("Database")

        # Leaderboard
        leaderboard = await db_cog.get_leaderboard(tournament.id, self.score_table)
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
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        channel = self.bot.get_channel(tournament.channel)
        if channel is None:
            return ""
        guild = channel.guild

        teams: dict[str, Team] = dict()
        for team in await db_cog.get_teams_by_guild(guild.id):
            teams[team.code] = team

        # Header
        if tournament.running == 0:
            content_header = f"**{tournament.name}** - Ended\n\n"
        else:
            content_header = f"**{tournament.name}**\n\n"

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
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        teams: dict[str, Team] = dict()
        for team in await db_cog.get_teams_by_guild(match.guild):
            teams[team.code] = team

        team1 = teams[match.team1]
        team2 = teams[match.team2]

        match_message_header = f"**{match.id}. {match.name}** - *BO{match.bestof}*"
        if match.running != 0:
            if match.running == 2:
                match_message_header += " - Closed"
            match_message_footer = (
                f"{team1.emoji} {team1.name} vs {team2.name} {team2.emoji}"
            )
        else:
            if match.result == 1:
                match_message_header += (
                    f" - Result: {match.win_games}-{match.lose_games}"
                )
                match_message_footer = (
                    f"**{team1.emoji} {team1.name}** vs {team2.name} {team2.emoji}"
                )
            else:
                match_message_header += (
                    f" - Result: {match.lose_games}-{match.win_games}"
                )
                match_message_footer = (
                    f"{team1.emoji} {team1.name} vs **{team2.name} {team2.emoji}**"
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
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        tournament: Optional[Tournament] = await db_cog.get_tournament(match.tournament)

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
        description="Starts a tournament in this channel.\n\nArguments:\n-Tournament name can contain spaces.",
        aliases=["s"],
        usage="<tournament name>",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def tournament_start(self, ctx: commands.Context, *, name: str):
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        tournament = await db_cog.get_running_tournament(ctx.channel.id)

        # Check if tournament already running
        if tournament is not None:
            raise TournamentAlreadyRunning(tournament)

        # Check if other tournament of same name already exists
        tournament = await db_cog.get_tournament_by_name(name, ctx.guild.id)
        if tournament is not None:
            raise TournamentAlreadyExists(tournament)

        message = await ctx.send("Tournament is starting...")

        try:
            tournament = Tournament(
                uuid.uuid4(), name.strip(), ctx.channel.id, ctx.guild.id, message.id, 1
            )
            await db_cog.insert_tournament(tournament)
        except Exception as e:
            await message.delete()
            raise e
        await self.update_tournament_message(tournament)
        await ctx.message.delete()

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
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        # Check if tournament running
        tournament = await db_cog.get_running_tournament(ctx.channel.id)
        if tournament is None:
            raise TournamentNotRunning

        # Check if there are still matches not ended
        running_matches = await db_cog.get_matches_by_state(tournament.id, 1)
        closed_matches = await db_cog.get_matches_by_state(tournament.id, 2)

        if len(running_matches) > 0:
            raise CantEndTournament(tournament, "There are still open matches")

        if len(closed_matches) > 0:
            raise CantEndTournament(tournament, "There are still closed matches")

        tournament.running = 0
        await db_cog.update_tournament(tournament)

        await self.update_tournament_message(tournament)
        await ctx.send(f"Tournament **{tournament.name}** ended.")
        await ctx.message.delete()

    @tournament_group.command(
        name="info",
        brief="Shows info on a tournament.",
        description="Shows info on a tournament in this server. If no name is given, it shows info on the currently running tournament in this channel.\n\nArguments:\n-Tournament name can contain spaces.",
        aliases=["i"],
        usage="<tournament name>",
    )
    @commands.guild_only()
    async def tournament_show(self, ctx, *, name: Optional[str]):
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        if name is not None:
            tournament = await db_cog.get_tournament_by_name(name, ctx.guild.id)
            txt = "No tournament with this name exists in this guild."
        else:
            tournament = await db_cog.get_running_tournament(ctx.channel.id)
            txt = "No tournament is running in this channel."

        # Check if tournament exists
        if tournament is None:
            raise NoTournament(txt)

        content = await self.generate_tournament_message(tournament)
        await ctx.send(content + "\n`This message does not get updated.`")

    @tournament_group.command(
        name="list",
        brief="Lists tournaments in a channel.",
        description="Lists all current and past tournaments in this server.",
        aliases=["l", "ls"],
        usage="",
    )
    @commands.guild_only()
    async def tournament_list(self, ctx: commands.Context):
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        tournaments: list[Tournament] = await db_cog.get_tournaments_by_guild(
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
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        # Check if tournament running
        tournament = await db_cog.get_running_tournament(ctx.channel.id)
        if tournament is None:
            raise TournamentNotRunning()

        team1: Optional[Team] = await db_cog.get_team(team1_code, ctx.guild.id)
        team2: Optional[Team] = await db_cog.get_team(team2_code, ctx.guild.id)

        # Send message
        message = await ctx.send("Match is starting...")

        # Calculate match id
        id = await db_cog.get_num_matches(tournament.id) + 1

        # Insert
        match = Match(
            id,
            name,
            ctx.guild.id,
            message.id,
            1,
            0,
            0,
            team1_code,
            team2_code,
            tournament.id,
            bestof,
        )
        try:
            await db_cog.insert_match(match)
        except Exception as e:
            await message.delete()
            raise e

        await self.update_match_message(match)

        # Add Team reacts
        await message.add_reaction(team1.emoji)
        await message.add_reaction(team2.emoji)

        # Add Games reacts
        games_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

        if bestof > 1:
            for i in range(math.floor(bestof / 2), bestof):
                await message.add_reaction(games_emojis[i])

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
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        # Check if tournament running
        tournament = await db_cog.get_running_tournament(ctx.channel.id)
        if tournament is None:
            raise TournamentNotRunning()

        errors = []
        for id in ids:
            # Is name a running match
            match = await db_cog.get_match(id, tournament.id)
            if match is None:
                errors += [f"Match with id {id} does not exist."]
                continue
            if match.running != 1:
                errors += [f"Match with id {id} is not an open match."]
                continue

            await self.save_votes(match, tournament)

            match.running = 2
            await db_cog.update_match(match)

            await self.update_match_message(match)
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
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        # Check if tournament running
        tournament = await db_cog.get_running_tournament(ctx.channel.id)
        if tournament is None:
            raise TournamentNotRunning()

        for id in ids:
            # Is reference a running or closed match
            match = await db_cog.get_match(id, tournament.id)
            if match is None:
                raise MatchDoesntExist()
            if match.running not in (1, 2):
                raise CantEndMatch(match, "This match has already ended.")

            if match.running == 1:
                await self.save_votes(match, tournament)

            # Create dialog message
            message: discord.Message = await ctx.send(
                f"Who won game {match.name} and in how many games?"
            )

            team1 = await db_cog.get_team(match.team1, tournament.guild)
            team2 = await db_cog.get_team(match.team2, tournament.guild)

            # Add Team reacts
            await message.add_reaction(team1.emoji)
            await message.add_reaction(team2.emoji)

            # Add Games reacts
            games_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

            if match.bestof > 1:
                for i in range(math.floor(match.bestof / 2), match.bestof):
                    await message.add_reaction(games_emojis[i])

            await message.add_reaction("✅")
            self.dialogs[message.id] = match.message

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
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        tournament: Optional[Tournament] = await db_cog.get_running_tournament(
            ctx.channel.id
        )
        if tournament is None:
            raise TournamentNotRunning()

        match: Optional[Match] = await db_cog.get_match(id, tournament.id)
        if match is None:
            raise MatchDoesntExist()

        if match.running == 1:
            # Fix emoji
            message: discord.Message = await ctx.channel.fetch_message(match.message)

            for reaction in message.reactions:
                if reaction.me:
                    await reaction.remove(self.bot.user)

            team1: Optional[Team] = await db_cog.get_team(match.team1, match.guild)
            team2: Optional[Team] = await db_cog.get_team(match.team2, match.guild)

            await message.add_reaction(team1.emoji)
            await message.add_reaction(team2.emoji)

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
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        tournament: Tournament
        if name is None:
            tournament = await db_cog.get_running_tournament(ctx.channel.id)
            if tournament is None:
                raise TournamentNotRunning()
        else:
            tournament: Tournament = await db_cog.get_tournament_by_name(
                name, ctx.guild.id
            )
            if tournament is None:
                raise NoTournament("No tournament by that name exists in this server.")

        teams: dict[str, Team] = dict()
        for team in await db_cog.get_teams_by_guild(tournament.guild):
            teams[team.code] = team

        past_matches: list[Match] = await db_cog.get_matches_by_state(tournament.id, 0)
        closed_matches: list[Match] = await db_cog.get_matches_by_state(
            tournament.id, 2
        )
        active_matches: list[Match] = await db_cog.get_matches_by_state(
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

                if match.result == 1:
                    match_content = f"{match.id}. {match.name}: **{team1.emoji} {team1.name}** vs {team2.name} {team2.emoji} - BO{match.bestof} - Result: {match.win_games}-{match.lose_games}"
                elif match.result == 2:
                    match_content = f"{match.id}. {match.name}: {team1.emoji} {team1.name} vs **{team2.name} {team2.emoji}** - BO{match.bestof} - Result: {match.lose_games}-{match.win_games}"
                paginator.add_line(match_content)

        if closed_matches:
            paginator.add_line("")
            paginator.add_line(f"**Closed Matches:**")
            closed_matches.sort(key=lambda x: x.id)
            for match in closed_matches:
                team1 = teams[match.team1]
                team2 = teams[match.team2]
                match_content = f"{match.id}. {match.name}: {team1.emoji} {team1.name} vs {team2.name} {team2.emoji} - BO{match.bestof}"
                paginator.add_line(match_content)
        if active_matches:
            paginator.add_line("")
            paginator.add_line(f"**Open Matches:**")
            active_matches.sort(key=lambda x: x.id)
            for match in active_matches:
                team1 = teams[match.team1]
                team2 = teams[match.team2]
                match_content = f"{match.id}. {match.name}: {team1.emoji} {team1.name} vs {team2.name} {team2.emoji} - BO{match.bestof}"
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
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        # We don't care about our own reactions
        if payload.user_id == self.bot.user.id:
            return False

        # Check if message is a match or in dialogs
        match: Optional[Match] = await db_cog.get_match_by_message(payload.message_id)
        if match is not None and match.running == 1:
            # Fetch channel and message
            channel = self.bot.get_channel(payload.channel_id)
            message: discord.Message = await channel.fetch_message(payload.message_id)

            team1: Optional[Team] = await db_cog.get_team(match.team1, match.guild)
            team2: Optional[Team] = await db_cog.get_team(match.team2, match.guild)

            to_remove = set()
            emoji = str(payload.emoji)

            # Team
            team_emoji = {team1.emoji, team2.emoji}
            if emoji in team_emoji:
                team_emoji.remove(emoji)
                to_remove.update(team_emoji)

            # Games
            if match.bestof > 1:
                games_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
                games_emojis = games_emojis[math.floor(match.bestof / 2) : match.bestof]
                games_emojis = set(games_emojis)
                if emoji in games_emojis:
                    games_emojis.remove(emoji)
                    to_remove.update(games_emojis)

            for reaction in message.reactions:
                if str(reaction) not in to_remove:
                    continue
                react_user = await reaction.users().get(id=payload.user_id)
                if react_user is not None:
                    await message.remove_reaction(
                        reaction, discord.Object(payload.user_id)
                    )

        # Check if message is a dialog message
        if (payload.message_id in self.dialogs.keys()) and (str(payload.emoji) == "✅"):
            # Fetch channel and message
            channel: discord.abc.Messageable = self.bot.get_channel(payload.channel_id)
            message: discord.Message = await channel.fetch_message(payload.message_id)

            # Check if user has manage messages permission
            perms = payload.member.permissions_in(channel)
            if not perms.manage_messages:
                await message.remove_reaction(reaction, discord.Object(payload.user_id))
                return

            # End match

            # Fetch match
            match: Optional[Match] = await db_cog.get_match_by_message(
                self.dialogs[payload.message_id]
            )

            team1: Optional[Team] = await db_cog.get_team(match.team1, match.guild)
            team2: Optional[Team] = await db_cog.get_team(match.team2, match.guild)

            # Find choices
            team_choice = 0
            game_choice = 1

            games_emojis = []
            # Find games choice
            if match.bestof > 1:
                games_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
                games_emojis = games_emojis[math.floor(match.bestof / 2) : match.bestof]
                game_choice = 0

            for r in message.reactions:
                if str(r) in [team1.emoji, team2.emoji]:
                    react_user = await r.users().get(id=payload.user_id)
                    if react_user is not None:
                        if team_choice == 0:
                            if str(r) == team1.emoji:
                                team_choice = 1  # team 1
                            else:
                                team_choice = 2  # team 2
                        else:
                            team_choice = -1  # two teams selected -> invalid
                if str(r) in games_emojis:
                    react_user = await r.users().get(id=payload.user_id)
                    if react_user is not None:
                        if game_choice == 0:
                            index = games_emojis.index(str(r))
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

            match.running = 0
            match.games = game_choice
            match.result = team_choice

            await db_cog.update_match(match)
            match = Match(
                match.id,
                match.name,
                match.guild,
                match.message,
                match.running,
                match.result,
                match.games,
                match.team1,
                match.team2,
                match.tournament,
                match.bestof,
            )  # Refresh match (winning and losing games)

            tournament = await db_cog.get_tournament(match.tournament)
            await self.update_match_message(match)
            await self.update_tournament_message(tournament)

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
