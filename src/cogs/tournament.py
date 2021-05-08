import asyncio
import logging
import math
import uuid
from typing import Optional

import aiosqlite
import discord
from discord.ext import commands

from src.cogs.database import DatabaseCog, Match, Team, Tournament, User, UserMatch
from src.converters import BestOfXConverter, CodeConverter


class TournamentCog(commands.Cog, name="Tournament"):
    score_table: dict[str, int] = {
        "bo1_team": 1,
        "bo3_team": 2,
        "bo3_games": 1,
        "bo5_team": 3,
        "bo5_games": 1,
    }

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
                match.name,
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
            content_leaderboard = f"***Leaderboard***\n```{leaderboard_str}```\n"
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

        if match.running != 0:
            match_message_header = f"**{match.name}** - *BO{match.bestof}*"
            if match.running == 2:
                match_message_header += " - Closed"
            match_message_footer = (
                f"{team1.emoji} {team1.name} vs {team2.name} {team2.emoji}"
            )
        else:
            win_games = math.ceil(match.bestof / 2)
            lose_games = match.games - win_games
            if match.result == 1:
                match_message_header = f"**{match.name}** - *BO{match.bestof}* - Result: {win_games}-{lose_games}"
                match_message_footer = (
                    f"**{team1.emoji} {team1.name}** vs {team2.name} {team2.emoji}"
                )
            else:
                match_message_header = f"**{match.name}** - *BO{match.bestof}* - Result: {lose_games}-{win_games}"
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

    @commands.group(name="tournament", aliases=["tr"])
    async def tournament_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.invoked_with)

    @commands.group(name="match", aliases=["m"])
    async def match_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.invoked_with)

    # ---------------------------- COMMANDS ----------------------------

    @tournament_group.command(
        name="start",
        brief="Starts a tournament.",
        description="Creates a new tournament in this channel.",
        usage="<tournament name>",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def tournament_start(self, ctx, *, name: str):
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        tournament = await db_cog.get_running_tournament(ctx.channel.id)

        # Check if tournament already running
        if tournament is not None:
            msg = await ctx.send(
                f"Tournament **{tournament.name}** already running.",
            )
            await asyncio.sleep(5)
            await msg.delete()
            return

        # Check if other tournament of same name already exists
        tournament = await db_cog.get_tournament_by_name(name, ctx.channel.id)
        if tournament is not None:
            msg = await ctx.send(
                f"Tournament **{tournament.name}** already exists.",
            )
            await asyncio.sleep(5)
            await msg.delete()
            return

        message = await ctx.send("Tournament is starting...")

        try:
            tournament = Tournament(
                uuid.uuid4(), name.strip(), ctx.channel.id, message.id, 1
            )
            await db_cog.insert_tournament(tournament)
        except Exception as e:
            await message.delete()
            raise e
        await self.update_tournament_message(tournament)
        await ctx.message.delete()

    @tournament_group.command(
        name="end",
        brief="Ends a tournament.",
        description="Ends the running tournament.",
        usage="",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def tournament_end(self, ctx):
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        # Check if tournament running
        tournament = await db_cog.get_running_tournament(ctx.channel.id)
        if tournament is None:
            msg = await ctx.send("No tournament is running.")
            await asyncio.sleep(5)
            await msg.delete()
            return

        # Check if there are still matches not ended
        running_matches = await db_cog.get_matches_by_state(tournament.id, 1)
        closed_matches = await db_cog.get_matches_by_state(tournament.id, 2)

        if (len(running_matches) + len(closed_matches)) > 0:
            msg = await ctx.send("There are still matches that haven't been ended.")
            await asyncio.sleep(5)
            await msg.delete()
            return

        tournament.running = 0
        await db_cog.update_tournament(tournament)

        await self.update_tournament_message(tournament)
        await ctx.send(f"Tournament **{tournament.name}** ended.")
        await ctx.message.delete()

    @tournament_group.command(
        name="show",
        brief="Shows info on a tournament.",
        description="Shows info on a tournament in this channel. If no name is given, it shows info on the currently running tournament.",
        aliases=["tr_show"],
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def tournament_show(self, ctx, *, name: Optional[str]):
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        if name is not None:
            tournament = await db_cog.get_tournament_by_name(name, ctx.channel.id)
            txt = "No tournament with this name exists in this channel."
        else:
            tournament = await db_cog.get_running_tournament(ctx.channel.id)
            txt = "No tournament is running."

        # Check if tournament exists
        if tournament is None:
            msg = await ctx.send(txt)
            await asyncio.sleep(5)
            await msg.delete()
            return

        content = await self.generate_tournament_message(tournament)
        await ctx.send(content + "\n`This message does not get updated.`")
        await ctx.message.delete()

    @tournament_group.command(
        name="list",
        brief="Lists tournaments in a channel.",
        description="Lists all current and past tournaments in this channel.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def tournament_list(self, ctx):
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        tournaments: list[Tournament] = await db_cog.get_tournaments_by_channel(
            ctx.channel.id
        )

        if tournaments:
            await ctx.send(
                "Tournaments:\n"
                + "\n".join([tournament.name for tournament in tournaments])
            )
        else:
            msg = ctx.send("There are no tournaments in this channel.")
            await asyncio.sleep(5)
            await msg.delete()

    @match_group.command(
        name="start",
        brief="Starts a match.",
        description="Creates a new match between two teams. Match is Best Of 1, 3, or 5.",
        usage="<short code team 1> <short code team 2> bo<X> <match name>",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def match_start(
        self,
        ctx,
        team1_code: CodeConverter(True),
        team2_code: CodeConverter(True),
        bestof: BestOfXConverter,
        *,
        name: str,
    ):
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        # Check if tournament running
        tournament = await db_cog.get_running_tournament(ctx.channel.id)
        if tournament is None:
            msg = await ctx.send("No tournament is running.")
            await asyncio.sleep(5)
            await msg.delete()
            return

        # Check if game with this name already exists
        existing_match = await db_cog.get_match(name, tournament.id)
        if existing_match is not None:
            msg = await ctx.send(
                f"A match in this tournament with the name {name} already exists.",
            )
            await asyncio.sleep(5)
            await msg.delete()
            return

        team1: Optional[Team] = await db_cog.get_team(team1_code, ctx.guild.id)
        team2: Optional[Team] = await db_cog.get_team(team2_code, ctx.guild.id)

        # Send message
        message = await ctx.send("Match is starting...")

        # Insert
        match = Match(
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

        await self.update_tournament_message(tournament)
        await ctx.message.delete()

    @match_group.command(
        name="close",
        brief="Closes predictions for a match.",
        description="Closes new predictions on the specified match.",
        usage="<name>",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def match_close(self, ctx, *, name):
        # Validate input
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        # Check if tournament running
        tournament = await db_cog.get_running_tournament(ctx.channel.id)
        if tournament is None:
            msg = await ctx.send("No tournament is running.")
            await asyncio.sleep(5)
            await msg.delete()
            return

        # Is name a running match
        match = await db_cog.get_match(name, tournament.id)
        if (match is None) or (match.running != 1):
            await ctx.send("Message is not a running match.")
            return

        await self.save_votes(match, tournament)

        match.running = 2
        await db_cog.update_match(match)

        await self.update_match_message(match)
        await self.update_tournament_message(tournament)
        await ctx.message.delete()

    @match_group.command(
        name="end",
        brief="Ends a match.",
        description="Ends the match.",
        usage="<winning team code> <amount of games> <name>",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def match_end(
        self,
        ctx,
        code: CodeConverter(True),
        num_games: int,
        *,
        name,
    ):
        # Validate input
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        # Check if tournament running
        tournament = await db_cog.get_running_tournament(ctx.channel.id)
        if tournament is None:
            msg = await ctx.send("No tournament is running.")
            await asyncio.sleep(5)
            await msg.delete()
            return

        # Is reference a running or closed match
        match = await db_cog.get_match(name, tournament.id)
        if (match is None) or (match.running not in (1, 2)):
            msg = await ctx.send(
                "Provided name does not exist or is not a running or closed match"
            )
            await asyncio.sleep(5)
            await msg.delete()
            return

        # Is team code one of the participants
        if code == match.team1:
            match.result = 1
        elif code == match.team2:
            match.result = 2
        else:
            msg = await ctx.send(f"Team {code} is not a participant.")
            await asyncio.sleep(5)
            await msg.delete()
            return

        # Is valid score
        lower_bound = math.ceil(match.bestof / 2)
        upper_bound = match.bestof
        if not ((lower_bound <= num_games) and (num_games <= upper_bound)):
            msg = await ctx.send(
                f"{num_games} is not a valid number of games for a BO{match.bestof}.",
            )
            await asyncio.sleep(5)
            await msg.delete()
            return

        if match.running == 1:
            await self.save_votes(match, tournament)

        match.running = 0
        match.games = num_games

        if match.team1 == code:
            match.result = 1
        elif match.team2 == code:
            match.result = 2

        await db_cog.update_match(match)

        await self.update_match_message(match)
        await ctx.message.delete()
        await self.update_tournament_message(tournament)

    @match_group.command(
        name="fix",
        brief="Fix match.",
        description="Fixes emotes on a match.",
        usage="<name>",
    )
    @commands.guild_only()
    @commands.is_owner()
    async def match_fix(self, ctx: commands.Context, *, name: str):
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        tournament: Optional[Tournament] = await db_cog.get_running_tournament(
            ctx.channel.id
        )
        if tournament is None:
            msg = await ctx.send("No tournament is running.")
            await asyncio.sleep(5)
            await msg.delete()
            return

        match: Optional[Match] = await db_cog.get_match(name, tournament.id)
        if match is None:
            msg = await ctx.send("Match does not exist.")
            await asyncio.sleep(5)
            await msg.delete()
            return

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

        await ctx.message.delete()

    # ----------------------------- EVENTS -----------------------------

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Removes other reactions in the same category as the new reaction from a match post. Basically turns the reactions into a (shitty) radio button."""  # Check if message is a match
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        # We don't care about our own reactions
        if payload.user_id == self.bot.user.id:
            return False

        # We only care about running matches
        match: Optional[Match] = await db_cog.get_match_by_message(payload.message_id)
        if match is None:
            return
        if match.running != 1:
            return

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
                await message.remove_reaction(reaction, discord.Object(payload.user_id))


def setup(bot):
    bot.add_cog(TournamentCog(bot))
