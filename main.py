import logging

import src.bot

logging.basicConfig(
    level=logging.INFO,
    style="{",
    format="{asctime:19s} [{levelname:8s}] {message}",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("persistent\\bot.log"),
        logging.StreamHandler(),
    ],
)

if __name__ == "__main__":
    src.bot.PREFIX = "+"
    src.bot.launch()
