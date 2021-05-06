import asyncio
import logging
import math
import uuid

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

    async def save_votes(self, match: Match, tournament: Tournament):
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

    async def calculate_leaderboard(
        self, tournament: Tournament
    ) -> list[tuple[int, str]]:
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        # Scoring table

        finished_matches: list[Match] = await db_cog.get_matches_by_state(
            tournament.id, 0
        )
        user_scores: dict[int, tuple[int, str]] = dict()  # (user_id, (score, name))
        for match in finished_matches:
            team_result = match.result
            games_result = match.games
            usermatches: set[UserMatch] = await db_cog.get_usermatch_by_match(
                match.name, match.tournament
            )

            for um in usermatches:
                user_entry = user_scores.get(um.user_id, (0, None))
                user_score = user_entry[0]
                user_name = (
                    (await db_cog.get_user(um.user_id)).name
                    if user_entry[1] is None
                    else user_entry[1]
                )

                if team_result == um.team:
                    if match.bestof == 1:
                        user_score += self.score_table["bo1_team"]
                    elif match.bestof == 3:
                        user_score += self.score_table["bo3_team"]
                    elif match.bestof == 5:
                        user_score += self.score_table["bo5_team"]

                if games_result == um.games:
                    if match.bestof == 3:
                        user_score += self.score_table["bo3_games"]
                    elif match.bestof == 5:
                        user_score += self.score_table["bo5_games"]
                user_scores[um.user_id] = (user_score, user_name)

        scores_name_sorted = sorted(list(user_scores.values()), key=lambda x: x[1])
        return sorted(scores_name_sorted, key=lambda x: x[0], reverse=True)

    async def generate_tournament_message(self, tournament: Tournament):
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        channel = self.bot.get_channel(tournament.channel)
        if channel is None:
            return ""
        guild = channel.guild

        teams: dict[Team] = dict()
        for team in await db_cog.get_teams_by_guild(guild.id):
            teams[team.code] = team

        # Header
        if tournament.running == 0:
            content_header = f"**{tournament.name}** - Ended\n\n"
        else:
            content_header = f"**{tournament.name}**\n\n"

        # Scoring table
        content_scoring_table = f"***Scoring Table***\n```Correct team - BO1: {self.score_table['bo1_team']}\nCorrect team - BO3: {self.score_table['bo3_team']}\tCorrect number of games - BO3: {self.score_table['bo3_games']}\nCorrect team - BO5: {self.score_table['bo5_team']}\tCorrect number of games - BO5: {self.score_table['bo5_games']}```\n"

        # Leaderboard
        leaderboard = await self.calculate_leaderboard(tournament)
        leaderboard_strings = []
        rank = 0
        prev_rank_score = -1
        players = 0
        if len(leaderboard) > 0:
            for entry in leaderboard:
                user_score, user_name = entry

                players += 1
                if prev_rank_score != user_score:
                    prev_rank_score = user_score
                    rank = players

                leaderboard_strings.append(f"{rank} - {user_name}: {user_score}")
            leaderboard_str = "\n".join(leaderboard_strings)
        else:
            leaderboard_str = " "

        content_leaderboard = f"***Leaderboard***\n```{leaderboard_str}```\n"

        # Combine
        content = (
            f"{content_header}{content_scoring_table}{content_leaderboard}".strip()
        )
        content += "\n------------------------------------------------------------------------------------------------"

        return content

    async def generate_match_message(self, match: Match):
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        teams: dict[Team] = dict()
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

        tournament: Tournament = await db_cog.get_tournament(match.tournament)

        tournament_channel = self.bot.get_channel(tournament.channel)
        if tournament_channel is None:
            return

        try:
            match_message = await tournament_channel.fetch_message(match.message)
        except (discord.NotFound, discord.Forbidden):
            return

        content = await self.generate_match_message(match)

        await match_message.edit(content=content)

    # ---------------------------- COMMANDS ----------------------------

    @commands.command(
        name="tournament_start",
        brief="Starts a tournament.",
        description="Creates a new tournament in this channel.",
        aliases=["tr_start"],
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

    @commands.command(
        name="tournament_end",
        brief="Ends a tournament.",
        description="Ends the running tournament.",
        aliases=["tr_end"],
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

    @commands.command(
        name="tournament_show",
        brief="Shows the running tournament.",
        description="Shows info about the currently running tournament in this channel.",
        aliases=["tr_show"],
        usage="",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def tournament_show(self, ctx):
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        # Check if tournament running
        tournament = await db_cog.get_running_tournament(ctx.channel.id)
        if tournament is None:
            msg = await ctx.send("No tournament is running.")
            await asyncio.sleep(5)
            await msg.delete()
            return

        content = await self.generate_tournament_message(tournament)
        await ctx.send(content + "\n`This message does not get updated.`")
        await ctx.message.delete()

    @commands.command(
        name="match_start",
        brief="Starts a match.",
        description="Creates a new match between two teams. Match is Best Of 1, 3, or 5.",
        aliases=["m_start"],
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

        team1: Team = await db_cog.get_team(team1_code, ctx.guild.id)
        team2: Team = await db_cog.get_team(team2_code, ctx.guild.id)

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

    @commands.command(
        name="match_close",
        brief="Closes predictions for a match.",
        description="Closes new predictions on the specified match.",
        aliases=["m_close"],
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

    @commands.command(
        name="match_end",
        brief="Ends a match.",
        description="Ends the match.",
        aliases=["m_end"],
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

    # ----------------------------- EVENTS -----------------------------

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Removes other reactions in the same category as the new reaction from a match post. Basically turns the reactions into a (shitty) radio button."""  # Check if message is a match
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        # We don't care about our own reactions
        if payload.user_id == self.bot.user.id:
            return False

        # We only care about running matches
        match: Match = await db_cog.get_match_by_message(payload.message_id)
        if match is None:
            return
        if match.running != 1:
            return

        # Fetch channel and message
        channel = self.bot.get_channel(payload.channel_id)
        message: discord.Message = await channel.fetch_message(payload.message_id)

        team1: Team = await db_cog.get_team(match.team1, match.guild)
        team2: Team = await db_cog.get_team(match.team2, match.guild)

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
