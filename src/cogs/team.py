from typing import Optional

import discord
from discord.ext import commands

from src import decorators
from src.cogs.database import DatabaseCog, Match, Team
from src.cogs.tournament import TournamentCog
from src.converters import CodeConverter, EmojiConverter


class EditException(Exception):
    team: Team
    reason: str

    def __init__(self, team: Team, reason: str):
        self.team = team
        self.reason = reason
        super().__init__(team, reason)


class TeamsCog(commands.Cog, name="Teams"):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(
        name="team",
        brief="Commands for creating, updating, listing or deleting teams.",
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
        code: CodeConverter(True),
        *,
        name: str,
    ):
        db_cog: DatabaseCog = self.bot.get_cog("Database")
        tr_cog: TournamentCog = self.bot.get_cog("Tournament")

        team: Team = await db_cog.get_team(code, ctx.guild.id)

        if name == team.name:
            raise EditException(
                team,
                "New name is the same as the current name.",
            )

        original_name = team.name
        team.name = name

        await db_cog.update_team(code, team)

        if tr_cog is not None:
            # Update matches
            to_update: list[Match] = await db_cog.get_matches_by_team(team)
            for match in to_update:
                await tr_cog.update_match_message(match)

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
        old_code: CodeConverter(True),
        new_code: CodeConverter(False),
    ):
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        team: Team = await db_cog.get_team(old_code, ctx.guild.id)

        if new_code == old_code:
            raise EditException(
                team,
                "New code is the same as the current code.",
            )

        team.code = new_code

        await db_cog.update_team(old_code, team)

        await ctx.send(f'Changed code:\n "{old_code}" => "{new_code}"')

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
        code: CodeConverter(True),
        emoji: EmojiConverter,
    ):
        # TODO: only edit code if there are no running games with this team
        db_cog: DatabaseCog = self.bot.get_cog("Database")

        team: Team = await db_cog.get_team(code, ctx.guild.id)
        matches: list[Match] = await db_cog.get_matches_by_team(team)

        if len(matches) > 0:
            raise EditException(
                team,
                "Cannot edit emoji for a team that is already in matches.",
            )

        if emoji == team.emoji:
            raise EditException(
                team,
                "New emoji is the same as the current emoji.",
            )

        old_emoji = team.emoji
        team.emoji = emoji

        await db_cog.update_team(code, team)
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
        code: CodeConverter(False),
        emoji: EmojiConverter,
    ):
        db_cog: DatabaseCog = ctx.bot.get_cog("Database")
        await db_cog.insert_team(Team(name.strip(), code, emoji, ctx.guild.id))
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
    async def team_remove(self, ctx, code: CodeConverter(True)):
        db_cog: DatabaseCog = ctx.bot.get_cog("Database")

        team: Optional[Team] = await db_cog.get_team(code, ctx.guild.id)
        if team is not None:
            await db_cog.delete_team(team)

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

    async def cog_command_error(self, ctx, error):
        message = ""

        if isinstance(error, commands.CommandInvokeError):
            if isinstance(error.original, EditException):
                message = f"Could not edit team {error.original.team.code}"
                if error.original.reason is not None:
                    message += f" ({error.original.reason})"

        if len(message) > 0:
            await ctx.send(f"`{message}`")
            ctx.handled = True
            return


def setup(bot):
    bot.add_cog(TeamsCog(bot))
