# predictions-bot
Discord bot for prediction tournaments
## Requirements
Python 3.9+ \
[discord.py](https://pypi.org/project/discord.py/) \
[emojis](https://pypi.org/project/emojis/) \
[colorthief](https://pypi.org/project/colorthief/) \
[tortoise-orm](https://pypi.org/project/tortoise-orm/) \
[asyncpg](https://pypi.org/project/asyncpg/)
## Usage
Set up a database (This can be any database supported by Tortoise, but this bot will only be tested on a PostgreSQL database). \
Create config.py in the root directory and enter your information.
```py
database = "" # your database link (format: https://tortoise-orm.readthedocs.io/en/latest/databases.html#db-url)
token = "" # your discord bot token
```
Install the requirements: `pip install -r requirements.txt` \
Initialize the database tables by running `python init.py` \
Run `python main.py`

Alternatively, if you want to run it with Docker, you can use `docker-compose run predictions python init.py` to initialize the database, followed by `docker-compose up -d` to start the bot. This should be done after creating config.py.
## Different database
The above procedure will automatically install interfaces for Sqlite and PostgreSQL databases. If you want to use a MySQL database instead, you will have to install either [aiomysql](https://pypi.org/project/aiomysql/0.0.21/) or [asyncmy](https://pypi.org/project/asyncmy/)
## Credits
For automated tournaments, it uses the amazing Leaguepedia database. Big thanks to them! (https://lol.fandom.com/)