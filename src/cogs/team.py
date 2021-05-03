import discord
from discord.ext import commands

from src.converters import CodeConverter, EmojiConverter


class TeamsCog(commands.Cog, name="Teams"):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name="team_create",
        brief="Creates a new team.",
        description="Creates a new team and adds it to this server's list of teams. The code cannot contain spaces. You can only use default discord emoji or emoji from this server.",
        aliases=["team_add", "tm_create", "tm_add"],
        usage="<code> <emoji> <name>",
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
        db_cog = ctx.bot.get_cog("Database")
        cur = db_cog.con.cursor()

        cur.execute(
            "INSERT INTO teams VALUES (:name, :code, :emoji, :guild);",
            {
                "name": name.strip(),
                "code": code,
                "emoji": emoji,
                "guild": ctx.guild.id,
            },
        )

        await ctx.send(f"Added team `{code}`")

    @commands.command(
        name="team_remove",
        brief="Removes a team.",
        description="Removes a team from this server's list of teams.",
        aliases=["team_delete", "tm_remove", "tm_delete"],
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def team_remove(self, ctx, code: CodeConverter(True)):
        db_cog = ctx.bot.get_cog("Database")
        cur = db_cog.con.cursor()

        cur.execute(
            "SELECT * FROM teams WHERE code = :code AND guild = :guild;",
            {
                "code": code,
                "guild": ctx.guild.id,
            },
        )
        team_name = cur.fetchone()[0]

        cur.execute(
            "DELETE FROM teams WHERE code = :code AND guild = :guild;",
            {
                "code": code,
                "guild": ctx.guild.id,
            },
        )

        await ctx.send(f"Deleted team {team_name}.")

    @commands.command(
        name="team_list",
        brief="Lists available teams.",
        aliases=["tm_list"],
        description="Lists all teams on this server.",
    )
    @commands.guild_only()
    async def team_list(self, ctx):
        db_cog = ctx.bot.get_cog("Database")
        cur = db_cog.con.cursor()

        teams = list(
            cur.execute(
                "SELECT * FROM teams WHERE guild = :guild;",
                {"guild": ctx.guild.id},
            ),
        )

        if not (len(teams) > 0):
            await ctx.send("`No teams found.`")
            return

        embed = discord.Embed(title="Teams")

        for team in teams:
            embed.add_field(
                name=f"{team[2]} {team[0]}",
                value=f"Code: `{team[1]}`",
            )
        await ctx.send(embed=embed)

    def get_team(self, server_id, code):
        return self.teams.get(server_id, {}).get(code, None)


def setup(bot):
    bot.add_cog(TeamsCog(bot))
