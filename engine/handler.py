import re

import discord

import db

from .decision import Decision, decide
from .worker import Worker

KEYWORD = re.compile(r"키피야|keepy", re.IGNORECASE)


async def on_message(msg: discord.Message, *, client: discord.Client, worker: Worker, guild_id: int):
    if not msg.guild or msg.guild.id != guild_id: # DM 혹은 설정한 서버가 아닐 시 모두 무시 
        return

    db.insert(msg)

    if msg.author == client.user:
        decision = Decision.save_only
    elif client.user in msg.mentions or KEYWORD.search(msg.content):
        decision = Decision.rtbp
    else:
        decision = await decide(db.recent(msg.id, 6, msg.channel.id), client.user.id)

    db.set_decision(msg.id, decision)

    worker.notify()
