import logging
from pathlib import Path

import config
import src.bot

log_handlers = [logging.StreamHandler()]

logfile = getattr(config, "logfile", None)
if logfile:
    log_handlers.append(logging.FileHandler(Path.cwd() / logfile))

logging.basicConfig(
    level=getattr(config, "logging_level", logging.INFO),
    style="{",
    format="{asctime:19s} [{levelname:8s}] {message}",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=log_handlers,
)


def main():
    src.bot.PREFIX = "+"
    src.bot.launch()


if __name__ == "__main__":
    main()
