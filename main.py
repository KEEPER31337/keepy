import asyncio
import logging

import discord

import db
from config import DISCORD_TOKEN, GUILD_ID
from engine import handler
from engine.reminder import ReminderWorker
from engine.worker import Worker


async def main():
    db.init()

    intents = discord.Intents.default()
    intents.message_content = True

    client = discord.Client(intents=intents, activity=discord.Game("키피야~ 라고 불러보세요"))
    worker = Worker(client)
    reminder_worker = ReminderWorker(client)

    @client.event
    async def on_message(msg: discord.Message):
        await handler.on_message(msg, client=client, worker=worker, guild_id=GUILD_ID)

    async with client, asyncio.TaskGroup() as tg:
        tg.create_task(worker.start())
        tg.create_task(reminder_worker.start())
        tg.create_task(client.start(DISCORD_TOKEN))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
