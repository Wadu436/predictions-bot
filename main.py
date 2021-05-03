import logging
from pathlib import Path

import src.bot

persistPath = Path.cwd() / "persistent"
persistPath.mkdir(parents=True, exist_ok=True)

logPath = persistPath / "bot.log"

logging.basicConfig(
    level=logging.INFO,
    style="{",
    format="{asctime:19s} [{levelname:8s}] {message}",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(logPath),
        logging.StreamHandler(),
    ],
)

if __name__ == "__main__":
    src.bot.PREFIX = "+"
    src.bot.launch()
