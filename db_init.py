import asyncio

import asyncpg

import config


async def main():
    db = await asyncpg.connect(config.postgres)
    with open("src/database-scripts/schema.sql") as script:
        await db.execute(script.read())
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
