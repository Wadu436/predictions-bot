import io
import itertools
import math
from typing import Optional

import colorthief
import discord
import tortoise.functions
from discord.embeds import Embed
from tortoise.transactions import in_transaction

from src import models
from src.aiomediawiki.aiomediawiki import leaguepedia


class TournamentManager:
    client: discord.Client

    def __init__(self, client: discord.Client):
        self.client = client

    async def generate_leaderboard_text(
        self, tournament: models.Tournament, tabs: Optional[list[str]] = None
    ):
        # Header
        content_header = f"**{tournament.name} Leaderboard{' - ' + ' '.join(tabs) if tabs is not None else ''}**"

        content_header += "\n\n"

        leaderboard = await tournament.calculate_leaderboard(tabs=tabs)

        # Calculate formatting
        rank_size = len(str(len(leaderboard)))
        name_size = 0
        score_size = 0
        correct_size = 0
        percent_size = 0  # 100.0%

        for entry in leaderboard:
            name_size = max(len(entry.user.name), name_size)
            score_size = max(len(str(entry.score)), score_size)
            correct_size = max(len(str(f"{entry.correct}/{entry.total}")), correct_size)
            percent_size = max(len(f"{entry.percentage:.1f}%"), percent_size)

        # Format the leaderboard
        counter = itertools.count(1)
        str_list = []
        for entry in leaderboard:
            entry_correct = f"{entry.correct}/{entry.total}"

            str_list.append(f"{next(counter):>{rank_size}}")
            str_list.append("  -  ")
            str_list.append(f"{entry.user.name:<{name_size}}  ")
            str_list.append(f"{entry.score:>{score_size}} points")
            str_list.append("  -  ")
            str_list.append(f"{entry_correct:>{correct_size}} correct ")
            percentage_str = f"{entry.percentage:.1f}%"
            str_list.append(f"({percentage_str:>{percent_size}})\n")

        leaderboard_str = "".join(str_list)
        if leaderboard_str:
            content_leaderboard = f"```c\n{leaderboard_str}```\n"
        else:
            content_leaderboard = ""

        # Combine
        content = f"{content_header}{content_leaderboard}".strip()

        return content

    async def generate_tournament_text(self, tournament: models.Tournament):
        # Header
        content_header = f"**{tournament.name}**"

        if tournament.is_fandom:
            content_header += f" (<{leaguepedia.wiki_url}{tournament.fandom_overview_page.replace(' ', '_')}>)"

        if tournament.running == 0:
            content_header += " - Ended"

        content_header += "\n\n"

        # Scoring table
        str_list = []
        str_list.append("***Scoring Table***")
        str_list.append("\n```")
        str_list.append(f"Correct team - BO1: {tournament.score_bo1_team}")
        str_list.append(f"\nCorrect team - BO3: {tournament.score_bo3_team}\t")
        str_list.append(f"Correct number of games - BO3: {tournament.score_bo3_games}")
        str_list.append(f"\nCorrect team - BO5: {tournament.score_bo5_team}\t")
        str_list.append(f"Correct number of games - BO5: {tournament.score_bo5_games}")
        str_list.append("```\n")
        content_scoring_table = "".join(str_list)

        leaderboard = await tournament.calculate_leaderboard()

        # Calculate formatting
        rank_size = len(str(len(leaderboard)))
        name_size = 0
        score_size = 0
        correct_size = 0
        percent_size = 0  # 100.0%

        for entry in leaderboard:
            name_size = max(len(entry.user.name), name_size)
            score_size = max(len(str(entry.score)), score_size)
            correct_size = max(len(str(f"{entry.correct}/{entry.total}")), correct_size)
            percent_size = max(len(f"{entry.percentage:.1f}%"), percent_size)

        # Format the leaderboard
        counter = itertools.count(1)
        str_list = []
        for entry in leaderboard:
            entry_correct = f"{entry.correct}/{entry.total}"

            str_list.append(f"{next(counter):>{rank_size}}")
            str_list.append("  -  ")
            str_list.append(f"{entry.user.name:<{name_size}}  ")
            str_list.append(f"{entry.score:>{score_size}} points")
            str_list.append("  -  ")
            str_list.append(f"{entry_correct:>{correct_size}} correct ")
            percentage_str = f"{entry.percentage:.1f}%"
            str_list.append(f"({percentage_str:>{percent_size}})\n")

        leaderboard_str = "".join(str_list)
        if leaderboard_str:
            content_leaderboard = f"***Leaderboard***\n```c\n{leaderboard_str}```\n"
        else:
            content_leaderboard = ""

        # Combine
        content = (
            f"{content_header}{content_scoring_table}{content_leaderboard}".strip()
        )

        return content

    async def generate_match_text(self, match: models.Match):
        await match.fetch_related("team1", "team2")
        team1_emoji = self.client.get_emoji(match.team1.emoji)
        team2_emoji = self.client.get_emoji(match.team2.emoji)

        str_list_header = []
        str_list_footer = []

        str_list_header.append(f"{match.id_in_tournament}. {match.name}")
        if match.running == models.MatchRunningEnum.CLOSED:
            str_list_header.append(" - Closed")
        elif match.running == models.MatchRunningEnum.ENDED:
            str_list_header.append(" - Result: ")
            str_list_header.append("0")
            str_list_header.append("-")
            str_list_header.append("0")
        str_list_footer.append(f"{team1_emoji} {match.team1.name}")
        str_list_footer.append(" vs ")
        str_list_footer.append(f"{match.team2.name} {team2_emoji}")

        if match.running == models.MatchRunningEnum.ENDED:
            if match.result == 1:
                str_list_header[2] = str(match.win_games)
                str_list_header[4] = str(match.lose_games)

                str_list_footer[0] = f"{team1_emoji} **{match.team1.name}**"
                str_list_footer[2] = f"~~{match.team2.name}~~ {team2_emoji}"
            else:
                str_list_header[4] = str(match.win_games)
                str_list_header[2] = str(match.lose_games)

                str_list_footer[0] = f"{team1_emoji} ~~{match.team1.name}~~"
                str_list_footer[2] = f"**{match.team2.name}** {team2_emoji}"

        return "".join(str_list_header) + "\n" + "".join(str_list_footer)

    async def generate_match_end_embeds(
        self,
        match: models.Match,
        team_correct: list[tuple[str, int]],  # (name, score)
        game_correct: Optional[list[tuple[str, int]]] = None,  # (name, score)
    ) -> list[Embed]:
        await match.fetch_related("team1", "team2", "tournament")
        if match.result == 1:
            team_winners = match.team1
            team_losers = match.team2
        if match.result == 2:
            team_winners = match.team2
            team_losers = match.team1

        emoji: discord.Emoji = self.client.get_emoji(team_winners.emoji)

        try:
            img_bytes = await emoji.url.read()
        except Exception:
            img_bytes = None

        embed_color = discord.Colour.blurple()
        if img_bytes:
            img = io.BytesIO(img_bytes)
            color = colorthief.ColorThief(img).get_color(quality=1)
            embed_color = discord.Colour.from_rgb(*color)

        embeds = []

        base_embed = discord.Embed(
            title=f"Results: {match.tournament.name} Match {match.id_in_tournament} ({match.name})",
            description=f"**{team_winners.name}** defeated **{team_losers.name}** by **{match.win_games}-{match.lose_games}**",
            colour=embed_color,
        )
        base_embed.set_thumbnail(url=emoji.url)

        current_embed: discord.Embed = base_embed.copy()
        if len(team_correct) > 0:
            current_embed.add_field(
                name="**The following player(s) predicted the correct winning team:**",
                value="\u2800",
                inline=False,
            )

            for (name, score) in team_correct:
                if len(current_embed.fields) == 25:
                    embeds.append(current_embed)
                    current_embed = base_embed.copy()
                    current_embed.add_field(
                        name="**The following player(s) predicted the correct winning team:**",
                        value="*Continued*",
                        inline=False,
                    )

                current_embed.add_field(name=name, value=f"{score} points")
        else:
            current_embed.add_field(
                name="**No one predicted the correct team**",
                value="\u2800",
                inline=False,
            )

        if match.bestof != 1:
            if len(current_embed.fields) > 20:
                embeds.append(current_embed)
                current_embed = base_embed.copy()

            if len(game_correct) > 0:
                current_embed.add_field(
                    name="**The following player(s) predicted the correct amount of games:**",
                    value="\u2800",
                    inline=False,
                )

                for (name, score) in game_correct:
                    if len(current_embed.fields) == 25:
                        embeds.append(current_embed)
                        current_embed = base_embed.copy()
                        current_embed.add_field(
                            name="**The following player(s) predicted the correct amount of games:**",
                            value="*Continued*",
                            inline=False,
                        )

                    current_embed.add_field(name=name, value=f"{score} points")
            else:
                current_embed.add_field(
                    name="**No one predicted the correct amount of games**",
                    value="\u2800",
                    inline=False,
                )

        embeds.append(current_embed)

        return embeds

    async def start_tournament(
        self,
        name: str,
        channel: int,
        guild: int,
        fandom_overview_page: Optional[str] = None,
    ) -> models.Tournament:
        tournament = models.Tournament(
            name=name.replace(":", " "),
            channel=channel,
            guild=guild,
            message=0,
            running=models.TournamentRunningEnum.RUNNING,
            fandom_overview_page=fandom_overview_page,
        )

        message_text = await self.generate_tournament_text(tournament)

        # Send message
        channel: discord.abc.Messageable = self.client.get_channel(channel)
        message: discord.Message = await channel.send(content=message_text)
        tournament.message = message.id

        await tournament.save()

        return tournament

    async def end_tournament(self, tournament: models.Tournament):
        tournament.running = models.TournamentRunningEnum.ENDED
        await tournament.save()

        # Update tournament message
        await self.update_tournament_message(tournament)

    async def update_tournament_message(self, tournament: models.Tournament):
        channel: discord.TextChannel = self.client.get_channel(tournament.channel)
        tournament_message: discord.Message = await channel.fetch_message(
            tournament.message
        )
        new_content = await self.generate_tournament_text(tournament)
        await tournament_message.edit(content=new_content)

    async def update_match_message(self, match: models.Match):
        await match.fetch_related("tournament")
        channel: discord.TextChannel = self.client.get_channel(
            match.tournament.channel,
        )
        match_message: discord.Message = await channel.fetch_message(match.message)
        new_content = await self.generate_match_text(match)
        await match_message.edit(content=new_content)

    async def start_match(
        self,
        tournament: models.Tournament,
        name,
        bestof,
        team1: models.Team,
        team2: models.Team,
        fandom_tab: Optional[str] = None,
        fandom_initialn_matchintab: Optional[int] = None,
    ) -> models.Match:
        max_id = (
            await models.Match.filter(tournament=tournament)
            .annotate(max_id=tortoise.functions.Max("id_in_tournament"))
            .first()
            .values_list("max_id")
        )[0][0]
        match = models.Match(
            id_in_tournament=1 if max_id is None else max_id + 1,
            name=name,
            message=0,
            running=models.MatchRunningEnum.RUNNING,
            fandom_tab=fandom_tab,
            fandom_initialn_matchintab=fandom_initialn_matchintab,
            team1=team1,
            team2=team2,
            bestof=bestof,
            tournament=tournament,
        )

        message_text = await self.generate_match_text(match)

        # Send message
        channel: discord.abc.Messageable = self.client.get_channel(tournament.channel)
        message: discord.Message = await channel.send(content=message_text)
        match.message = message.id

        try:
            await match.save()
        except Exception as e:
            await message.delete()
            raise e

        # Add emoji
        await message.add_reaction(self.client.get_emoji(team1.emoji))
        await message.add_reaction(self.client.get_emoji(team2.emoji))

        games_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

        if bestof > 1:
            for i in range(math.floor(bestof / 2), bestof):
                await message.add_reaction(games_emojis[i])

        return match

    async def close_match(self, match: models.Match, update_message=True):
        # Safeguard
        if match.running != models.MatchRunningEnum.RUNNING:
            return

        # Load related fields
        await match.fetch_related("tournament", "team1", "team2")

        channel: discord.TextChannel = self.client.get_channel(match.tournament.channel)
        message: discord.Message = await channel.fetch_message(match.message)

        team_emojis: list[int] = [match.team1.emoji, match.team2.emoji]
        games_emojis: list[str] = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        games_emojis = games_emojis[math.floor(match.bestof / 2) : match.bestof]

        # Create predictions
        predictions: dict[discord.User, models.Prediction] = {}  # {User: Prediction}

        for reaction in message.reactions:
            if reaction.custom_emoji and (reaction.emoji.id in team_emojis):
                # Team prediction
                team = team_emojis.index(reaction.emoji.id) + 1
                users: list[discord.User] = await reaction.users().flatten()
                for user in users:
                    if user.bot == False:
                        if user in predictions:
                            predictions[user].team = team
                        else:
                            predictions[user] = models.Prediction(
                                team=team, games=0, match=match
                            )

            if not reaction.custom_emoji and (reaction.emoji in games_emojis):
                # Games prediction
                games = games_emojis.index(reaction.emoji) + math.ceil(match.bestof / 2)
                users: list[discord.User] = await reaction.users().flatten()
                for user in users:
                    if user.bot == False:
                        if user in predictions:
                            predictions[user].games = games
                        else:
                            predictions[user] = models.Prediction(
                                team=0, games=games, match=match
                            )

        # Add db users to the predictions
        discord_ids = {u.id for u in predictions}
        users_db = await models.User.filter(discord_id__in=discord_ids)
        users_db = {u.discord_id: u for u in users_db}

        predictions_list: list[models.Prediction] = []
        for user, prediction in predictions.items():
            # Add or update user
            if not ((user.id in users_db) and (users_db[user.id].name == user.name)):
                new_user, _ = await models.User.update_or_create(
                    {"name": user.name},
                    discord_id=user.id,
                )
                users_db[user.id] = new_user

            prediction.user = users_db[user.id]
            predictions_list.append(prediction)

        # Close the match
        match.running = models.MatchRunningEnum.CLOSED

        # Save changes to database
        async with in_transaction():
            await models.Prediction.bulk_create(predictions_list)
            await match.save()

        if update_message:
            await self.update_match_message(match)

    async def end_match(
        self, match: models.Match, team: int, games: int, update_tournament_message=True
    ):
        if match.running == models.MatchRunningEnum.RUNNING:
            await self.close_match(match, update_message=False)

        await match.fetch_related("tournament")

        match.running = models.MatchRunningEnum.ENDED
        match.games = games
        match.result = team

        await match.save()

        channel: discord.TextChannel = self.client.get_channel(match.tournament.channel)
        await self.update_match_message(match)

        if update_tournament_message:
            tournament_message: discord.Message = await channel.fetch_message(
                match.tournament.message
            )
            new_content = await self.generate_tournament_text(match.tournament)
            await tournament_message.edit(content=new_content)

        # Send update message if necesary
        if match.tournament.updates_channel is not None:
            channel = self.client.get_channel(match.tournament.updates_channel)

            # Fetch predictions
            # await match.fetch_related("predictions")

            leaderboard: list[models.ScoreboardEntry]
            leaderboard = await match.tournament.calculate_leaderboard()
            leaderboard_dict = {se.user: se for se in leaderboard}

            winners_team: list[models.Prediction] = await models.Prediction.filter(
                match=match, team=match.result
            ).select_related("user")
            team_winners = [
                (p.user.name, leaderboard_dict[p.user].score) for p in winners_team
            ]
            team_winners.sort(key=lambda x: x[0])

            game_winners = []
            if match.bestof > 1:
                winners_games: list[models.Prediction] = await models.Prediction.filter(
                    match=match, games=match.games
                ).select_related("user")
                game_winners = [
                    (p.user.name, leaderboard_dict[p.user].score) for p in winners_games
                ]
                game_winners.sort()

            embeds = await self.generate_match_end_embeds(
                match, team_winners, game_winners
            )
            for embed in embeds:
                await channel.send(embed=embed)

            tab_running_match_count = await models.Match.filter(
                tournament=match.tournament,
                fandom_tab=match.fandom_tab,
                running__not=models.MatchRunningEnum.ENDED,
            ).count()

            if tab_running_match_count == 0:
                content = await self.generate_leaderboard_text(
                    match.tournament,
                    [match.fandom_tab],
                )
                await channel.send(content)
