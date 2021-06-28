# predictions-bot
Discord bot for prediction tournaments
## Requirements
Python 3.9+ \
[discord.py](https://pypi.org/project/discord.py/) \
[emojis](https://pypi.org/project/emojis/) \
[colorthief](https://pypi.org/project/colorthief/) \
[tortoise-orm](https://pypi.org/project/tortoise-orm/) \
[asyncpg](https://pypi.org/project/asyncpg/)
[aerich](https://pypi.org/project/aerich/)
## Usage
Set up a database (This can be any database supported by Tortoise, but this bot will only be tested on a PostgreSQL database). \
Create config.py in the root directory and enter your information.
```py
database = "" # your database link (format: https://tortoise-orm.readthedocs.io/en/latest/databases.html#db-url)
token = "" # your discord bot token
```
Install the requirements: `pip install -r requirements.txt` \
Initialize the database tables by running `aerich upgrade` \
Run `python main.py`

Alternatively, if you want to run it with Docker you can simply run `docker-compose up --build -d` to start the bot. The same command can be used to upgrade it. This should be done after creating `config.py`. The Docker image automatically initializes the database. It also performs any possible migrations.
## Different database
The above procedure will automatically install interfaces for Sqlite and PostgreSQL databases. If you want to use a MySQL database instead, you will have to install either [aiomysql](https://pypi.org/project/aiomysql/0.0.21/) or [asyncmy](https://pypi.org/project/asyncmy/)
## Migrations
To perform migrations, run `aerich upgrade`. As mentioned above, the Docker image automatically performs migrations when upgrading.
## Credits
For automated tournaments, it uses the amazing Leaguepedia database. Big thanks to them! (https://lol.fandom.com/)