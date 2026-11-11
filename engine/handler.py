import re

import discord

import db

from .decision import Decision, decide
from .worker import Worker

KEYWORD = re.compile(r"키피야|keepy", re.IGNORECASE)


async def on_message(msg: discord.Message, *, client: discord.Client, worker: Worker, guild_id: int):
    # DM이 아닌 디스코드 서버의 채팅인지, 그리고 우리가 설정한 서버에서 온 채팅인지 확인
    if not msg.guild or msg.guild.id != guild_id: 
        return

    db.insert(msg)

    if msg.author == client.user:
        decision = Decision.save_only
    elif client.user in msg.mentions or KEYWORD.search(msg.content):
        decision = Decision.rtbp
    else:
        decision = await decide(db.recent(msg.id, 6, msg.channel.id), client.user.id)

    db.set_decision(msg.id, decision)

    worker.wake.set()
