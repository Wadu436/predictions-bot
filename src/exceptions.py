from discord.ext import commands


class EmojiNotFound(commands.BadArgument):
    def __init__(self):
        super().__init__()


class EmojiNotInGuild(commands.BadArgument):
    def __init__(self):
        super().__init__()


class TeamExist(commands.BadArgument):
    def __init__(self, code):
        super().__init__(code)


class TeamDoesntExist(commands.BadArgument):
    def __init__(self, code):
        super().__init__(code)
