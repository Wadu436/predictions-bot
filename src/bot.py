import asyncio
import json
import logging
import sqlite3
import traceback
from pathlib import Path

import discord
from discord.ext import commands

from src import exceptions

PREFIX = "+"


def get_prefix(bot, message):
    return PREFIX


initial_extensions = ["database", "team", "tournament"]  # "team", "tournament",

intents = discord.Intents.default()

help_command = commands.DefaultHelpCommand(no_category="General")

bot = commands.Bot(
    command_prefix=get_prefix,
    description="Prediction tournament bot",
    help_command=help_command,
    intents=intents,
)

loaded_extensions = []


def load_extension_wrapper(ext):
    bot.load_extension(f"src.cogs.{ext}")
    loaded_extensions.append(ext)


def unload_extension_wrapper(ext):
    bot.unload_extension(f"src.cogs.{ext}")
    loaded_extensions.remove(ext)


def reload_extension_wrapper(ext):
    loaded_extensions.remove(ext)
    bot.reload_extension(f"src.cogs.{ext}")
    loaded_extensions.append(ext)


@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user}")
    logging.info(f"Connected to {len(bot.guilds)} servers.")


# commands
@bot.command(
    name="reload",
    brief="Reloads extensions.",
    description="Reloads all or specified extensions, based on (lack of) arguments.",
)
@commands.is_owner()
async def reload(ctx, *extensions):
    ext_list = loaded_extensions.copy() if len(extensions) == 0 else extensions

    if not (len(ext_list) > 0):
        await ctx.send("There are no extensions to reload.")
        return

    msg = f"Attempting to reload extension(s) {', '.join(ext_list)}."
    logging.info(msg)

    success_list = []
    unloaded_list = []
    fail_list = []

    for ext in ext_list:
        try:
            reload_extension_wrapper(ext)
            success_list.append(ext)
        except commands.ExtensionNotLoaded:
            unloaded_list.append(ext)
        except commands.ExtensionError:
            fail_list.append(ext)

    msg = []
    if len(success_list) > 0:
        msg.append(f"Successfully reloaded: {', '.join(success_list)}.")
    if len(unloaded_list) > 0:
        msg.append(f"Unloaded/non-existing extensions: {', '.join(unloaded_list)}.")

    msg = "\n".join(msg)

    logging.info(msg)
    await ctx.send(msg)


@bot.command(
    name="load",
    brief="Loads extensions.",
    description="Attempts to load specified extensions.",
)
@commands.is_owner()
async def load(ctx, *extensions):
    if not (len(extensions) > 0):
        raise commands.BadArgument()

    msg = f"Attempting to load extension(s) {', '.join(extensions)}."
    logging.info(msg)

    success_list = []
    not_found_list = []
    already_loaded_list = []
    fail_list = []

    for ext in extensions:
        try:
            load_extension_wrapper(ext)
            success_list.append(ext)
        except commands.ExtensionNotFound:
            not_found_list.append(ext)
        except commands.ExtensionAlreadyLoaded:
            already_loaded_list.append(ext)
        except commands.ExtensionError:
            fail_list.append(ext)

    msg = []
    if len(success_list) > 0:
        msg.append(f"Successfully loaded: {', '.join(success_list)}.")
    if len(not_found_list) > 0:
        msg.append(f"Extension not found: {', '.join(not_found_list)}.")
    if len(already_loaded_list) > 0:
        msg.append(f"Extension already loaded: {', '.join(already_loaded_list)}.")
    if len(fail_list) > 0:
        msg.append(f"Failed loading: {', '.join(fail_list)}.")

    msg = "\n".join(msg)

    logging.info(msg)
    await ctx.send(msg)


@bot.command(
    name="unload",
    brief="Unloads extensions.",
    description="Attempts to unload specified extensions.",
)
@commands.is_owner()
async def unload(ctx, *extensions):
    if not (len(extensions) > 0):
        raise commands.BadArgument()

    msg = f"Attempting to unload extension(s) {', '.join(extensions)}."
    logging.info(msg)

    success_list = []
    unloaded_list = []
    fail_list = []

    for ext in extensions:
        try:
            unload_extension_wrapper(ext)
            success_list.append(ext)
        except commands.ExtensionNotLoaded:
            unloaded_list.append(ext)
        except commands.ExtensionError:
            fail_list.append(ext)

    msg = []
    if len(success_list) > 0:
        msg.append(f"Successfully unloaded: {', '.join(success_list)}.")
    if len(unloaded_list) > 0:
        msg.append(f"Unloaded/non-existing extensions: {', '.join(unloaded_list)}.")
    if len(fail_list) > 0:
        msg.append(f"Failed unloading: {', '.join(fail_list)}.")

    msg = "\n".join(msg)

    logging.info(msg)
    await ctx.send(msg)


@bot.command(
    name="show_loaded",
    brief="Show loaded extensions.",
    description="Shows a list of all currently loaded extensions.",
)
@commands.is_owner()
async def show_loaded(ctx, *extensions):
    if not (len(loaded_extensions) > 0):
        await ctx.send("No extensions loaded.")
        return
    await ctx.send(f"Currently loaded extensions:\n{' '.join(loaded_extensions)}")


@bot.event
async def on_command_error(ctx, error):
    # Prevents commands with local handlers from being handled here
    if hasattr(ctx.command, "on_error"):
        return

    # Prevents commands with cog handlers from being handled here
    cog = ctx.cog
    if cog:
        if cog._get_overridden_method(cog.cog_command_error) is not None:
            return

    if isinstance(error, exceptions.EmojiNotInGuild) or isinstance(
        error,
        exceptions.EmojiNotFound,
    ):
        await ctx.send(
            "You can only use custom emojis from this server.",
        )
        return

    if isinstance(error, exceptions.TeamExist):
        if len(error.args) > 0:
            await ctx.send(
                f"Team with code {error.args[0]} already exists.",
            )
        else:
            await ctx.send("Team already exists.")
        return

    if isinstance(error, exceptions.TeamDoesntExist):
        if len(error.args) > 0:
            await ctx.send(
                f"Team with code {error.args[0]} doesn't exist.",
            )
        else:
            await ctx.send("Team doesn't exist.")
        return

    if isinstance(error, commands.UserInputError):
        await ctx.send_help(ctx.invoked_with)
        return

    if isinstance(error, commands.CommandNotFound):
        msg = await ctx.send(f"`Command {ctx.invoked_with} not found`")
        await asyncio.sleep(10)
        await msg.delete()
        return

    if isinstance(error, commands.CommandInvokeError):
        error = error.original
        if isinstance(error, sqlite3.OperationalError):
            await ctx.send("`Database error.`")
            logging.error("Database error.")

        if isinstance(error, sqlite3.IntegrityError):
            await ctx.send("`Database integrity error.`")
            logging.error("Database integrity error.")
    else:
        await ctx.send("`An error occured while processing the command.`")

    # logging.error(error)
    # logging.error("".join(traceback.format_tb(error.__traceback__)))
    logging.error(
        "".join(traceback.format_exception(type(error), error, error.__traceback__)),
    )


def launch():
    # Load json and token
    logging.debug("Loading config")
    configPath = Path("./persistent/config.json")
    if not configPath.exists():
        config = {"token": None}
        with open(configPath, "w") as f:
            json.dump(config, f)
    else:
        with open(configPath, "r") as f:
            config = json.load(f)
    logging.debug("Finished loading config")

    if config["token"] is None:
        logging.info("Could not find token. Please enter it: ")
        config["token"] = input()
        with open(configPath, "w") as f:
            json.dump(config, f)
        logging.info(f"If this token is incorrect, you can change it in {configPath}")

    # Start bot
    logging.debug("Starting bot")
    for cog in initial_extensions:
        logging.debug(f"Loading extension {cog}")
        load_extension_wrapper(cog)

    bot.run(config["token"], bot=True, reconnect=True)
    logging.debug("Shutting down")
