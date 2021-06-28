import discord
import tortoise.exceptions
from discord.ext import commands
from tortoise.query_utils import Q

from src import models
from src.cogs.tournament import TournamentCog
from src.utils import decorators


class TeamException(Exception):
    reason: str

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class TeamsCog(commands.Cog, name="Teams"):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(
        name="team",
        brief="Commands for interacting with teams.",
        description="Commands for creating, updating, listing or deleting teams.",
        aliases=["tm"],
    )
    @commands.guild_only()
    async def team_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @team_group.group(
        name="edit",
        brief="Commands for editing the name, code or emoji of a team.",
        description="Commands for editing the name, code or emoji of a team.",
        aliases=["e"],
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def edit_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @edit_group.group(
        name="name",
        brief="Edits a team's name.",
        description="Edits a team's name.",
        usage="<code> <new name>",
        aliases=["n"],
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def edit_name(
        self,
        ctx: commands.Context,
        code: str,
        *,
        name: str,
    ):
        try:
            team = await models.Team.get(code=code, guild=ctx.guild.id)
        except tortoise.exceptions.DoesNotExist:
            raise TeamException(f"There is no team with code {code}")

        original_name = team.name

        if name != team.name:
            team.name = name
            await team.save()

        tr_cog: TournamentCog = self.bot.get_cog("Tournament")
        if tr_cog is not None:
            # Update matches
            to_update = await models.Match.filter(Q(team1=team) | Q(team2=team))
            for match in to_update:
                await tr_cog.tournament_manager.update_match_message(match)

        await ctx.send(f'Changed name:\n "{original_name}" => "{name}"')

    @edit_group.group(
        name="code",
        brief="Edits a team's code.",
        description="Edits a team's code.",
        usage="<old code> <new code>",
        aliases=["c"],
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def edit_code(
        self,
        ctx: commands.Context,
        old_code: str,
        new_code: str,
    ):
        try:
            team = await models.Team.get(code=old_code, guild=ctx.guild.id)
        except tortoise.exceptions.DoesNotExist:
            raise TeamException(f"There is no team with code {old_code}.")

        try:
            if new_code != team.code:
                team.code = new_code
                await team.save()
        except tortoise.exceptions.IntegrityError:
            raise TeamException(
                f"Could not update team {old_code}. (Maybe the code {new_code} is already in use?)",
            )

        await ctx.send(f"Changed code:\n '{old_code}' => '{new_code}'.")

    @edit_group.group(
        name="emoji",
        brief="Edits a team's emoji.",
        description="Edits a team's emoji.",
        usage="<code> <new emoji>",
        aliases=["e"],
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def edit_emoji(
        self,
        ctx: commands.Context,
        code: str,
        emoji: commands.converter.EmojiConverter,
    ):
        try:
            team = await models.Team.get(code=code, guild=ctx.guild.id)
        except tortoise.exceptions.DoesNotExist:
            raise TeamException(f"There is no team with code {code}.")
        matches = await models.Match.filter(Q(team1=team) | Q(team2=team))

        if len(matches) > 0:
            raise TeamException(
                f"Could not edit team {team.code} (Cannot edit emoji for a team that is already in matches).",
            )

        old_emoji = self.bot.get_emoji(team.emoji)

        if emoji.id != team.emoji:
            team.emoji = emoji.id
            await team.save()

        await ctx.send(f"Changed emoji:\n {old_emoji} => {emoji}")

    @team_group.command(
        name="new",
        brief="Creates a new team.",
        description="Creates a new team and adds it to this server's list of teams. The code cannot contain spaces. You can only use default discord emoji or emoji from this server.",
        usage="<name> <code> <emoji>",
        aliases=["n"],
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @decorators.regex_arguments("(.+) (\\S+) (\\S+)")
    async def team_new(
        self,
        ctx,
        name: str,
        code: str,
        emoji: commands.converter.EmojiConverter,
    ):
        try:
            await models.Team.create(
                name=name.strip(),
                code=code,
                emoji=emoji.id,
                guild=ctx.guild.id,
            )
        except tortoise.exceptions.IntegrityError:
            raise TeamException(
                f"Could not create new team. (Maybe the code {code} is already in use?)",
            )
        await ctx.send(f"Added team `{code}`")

    @team_group.command(
        name="delete",
        brief="Delete a team.",
        description="Deletes a team from this server's list of teams.",
        usage="<code>",
        aliases=["d"],
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def team_remove(self, ctx, code: str):
        try:
            team = await models.Team.get(code=code, guild=ctx.guild.id)
        except tortoise.exceptions.DoesNotExist:
            raise TeamException(f"There is no team with code {code}.")
        await team.delete()
        await ctx.send(f"Deleted team {team.name}.")

    @team_group.command(
        name="list",
        brief="List teams.",
        description="Lists this server's teams.",
        usage="",
        aliases=["l", "ls"],
    )
    @commands.guild_only()
    async def team_list(self, ctx):
        teams = await models.Team.filter(guild=ctx.guild.id)

        if not (len(teams) > 0):
            await ctx.send("`No teams found.`")
            return

        embed = discord.Embed(title="Teams")

        for team in teams:
            emoji = self.bot.get_emoji(team.emoji)
            embed.add_field(
                name=f"{emoji} {team.name}",
                value=f"Code: `{team.code}`",
            )
        await ctx.send(embed=embed)

    async def cog_command_error(self, ctx, error):
        message = ""

        if isinstance(error, commands.CommandInvokeError):
            if isinstance(error.original, TeamException):
                message = error.original.reason

        if len(message) > 0:
            await ctx.send(f"`{message}`")
            ctx.handled = True


def setup(bot):
    bot.add_cog(TeamsCog(bot))
