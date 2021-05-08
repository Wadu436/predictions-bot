from typing import Optional

import discord
from discord.ext import commands

from src.cogs.database import DatabaseCog, Team
from src.converters import CodeConverter, EmojiConverter


class TeamsCog(commands.Cog, name="Teams"):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="team", aliases=["tm"])
    async def team_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.invoked_with)

    @team_group.command(
        name="create",
        brief="Creates a new team.",
        description="Creates a new team and adds it to this server's list of teams. The code cannot contain spaces. You can only use default discord emoji or emoji from this server.",
        usage="<name> <code> <emoji> ",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def team_create(
        self,
        ctx,
        code: CodeConverter(False),
        emoji: EmojiConverter,
        *,
        name: str,
    ):
        db_cog: DatabaseCog = ctx.bot.get_cog("Database")
        await db_cog.insert_team(Team(name.strip(), code, emoji, ctx.guild.id))
        await ctx.send(f"Added team `{code}`")

    @team_group.command(
        name="remove",
        brief="Removes a team.",
        description="Removes a team from this server's list of teams.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def team_remove(self, ctx, code: CodeConverter(True)):
        db_cog: DatabaseCog = ctx.bot.get_cog("Database")

        team: Optional[Team] = await db_cog.get_team(code, ctx.guild.id)
        if team is not None:
            await db_cog.delete_team(team)

        await ctx.send(f"Deleted team {team.name}.")

    @team_group.command(
        name="list",
        brief="Lists available teams.",
        description="Lists all teams on this server.",
    )
    @commands.guild_only()
    async def team_list(self, ctx):
        db_cog: DatabaseCog = ctx.bot.get_cog("Database")

        teams = await db_cog.get_teams_by_guild(ctx.guild.id)

        if not (len(teams) > 0):
            await ctx.send("`No teams found.`")
            return

        embed = discord.Embed(title="Teams")

        for team in teams:
            embed.add_field(
                name=f"{team.emoji} {team.name}",
                value=f"Code: `{team.code}`",
            )
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(TeamsCog(bot))
