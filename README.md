# predictions-bot
Discord bot for prediction tournaments

## Requirements
Python 3.9+ \
[discord.py](https://pypi.org/project/discord.py/) \
[emojis](https://pypi.org/project/emojis/) \
[asyncpg](https://pypi.org/project/asyncpg//) 

## Usage
Set up a PostgreSQL database and create a user and a database on it. \
Create config.py in the root directory. 
```py
postgres = "" # your postgresql link (format: "postgresql://[user[:password]@][ip][:port][/dbname]")
token = "" # your discord bot token
```
Install the requirements: `pip install -r requirements.txt` \
Run `python main.py`  \
Enter your token 

If you wish to change your token at a later time, you can do so in `./persistent/config.json`
