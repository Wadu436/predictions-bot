import re

import emojis
from discord.ext import commands

from src import exceptions
from src.cogs.database import DatabaseCog


class EmojiConverter(commands.Converter):
    async def convert(self, ctx, argument):
        # Check if discord emoji
        match = re.fullmatch("<a?:(.+):(\\d+)>", argument)
        if match is not None:
            emoji_id = int(match.groups()[1])
            emoji = ctx.bot.get_emoji(emoji_id)
            # not found emoji
            if emoji is None:
                raise exceptions.EmojiNotFound()
            # found emoji
            if emoji.guild != ctx.guild:
                raise exceptions.EmojiNotInGuild()
            return str(emoji)

        # Check if Unicode emoji
        if not emojis.db.get_emoji_by_code(argument):
            raise exceptions.EmojiNotFound()

        return argument


class CodeConverter(commands.Converter):
    def __init__(self, exist):
        self.exist = (
            exist  # True if code needs to exist, False if code needs to not exist
        )

    async def convert(self, ctx, argument):
        code = argument.strip().lower()

        db_cog: DatabaseCog = ctx.bot.get_cog("Database")

        code_exists = (await db_cog.get_team(code, ctx.guild.id)) is not None
        if code_exists != self.exist:
            if self.exist:
                raise exceptions.TeamDoesntExist(code)
            else:
                raise exceptions.TeamExist(code)
        return code


class BestOfXConverter(commands.Converter):
    async def convert(self, ctx, argument):
        argument = argument.lower()
        # starts with bo
        if not argument.startswith("bo"):
            raise commands.BadArgument()

        bo = 0
        try:
            bo = int(argument[2:])
        except ValueError:
            raise commands.BadArgument()

        if bo not in [1, 3, 5]:
            raise commands.BadArgument()

        return bo
