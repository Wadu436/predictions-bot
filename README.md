# predictions-bot
Discord bot for prediction tournaments

## Requirements
Python 3.9+ \
[discord.py](https://pypi.org/project/discord.py/) \
[emojis](https://pypi.org/project/emojis/) \
[aiosqlite](https://pypi.org/project/aiosqlite/) 

## Usage
Create config.py in the root directory. \

```py
postgres = "" # your postgresql link
token = "" # your discord bot token
```

Install the requirements: `pip install -r requirements.txt` \
Run `python main.py`  \
Enter your token 

If you wish to change your token at a later time, you can do so in `./persistent/config.json`
