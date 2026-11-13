import re

import discord

import db

from .decision import Decision, decide
from .worker import Worker

KEYWORD = re.compile(r"키피|keepy", re.IGNORECASE)


def replies_to(msg: discord.Message, user: discord.ClientUser) -> bool:
    # 답장할 때 멘션 알림을 끄면 msg.mentions에 잡히지 않으므로 답장 대상의 작성자를 직접 본다
    ref = msg.reference and msg.reference.resolved

    return isinstance(ref, discord.Message) and ref.author == user


async def on_message(msg: discord.Message, *, client: discord.Client, worker: Worker, guild_id: int):
    if not msg.guild or msg.guild.id != guild_id: # DM 혹은 설정한 서버가 아닐 시 모두 무시 
        return

    db.insert(msg)

    if msg.author == client.user:
        decision = Decision.save_only
    elif client.user in msg.mentions or KEYWORD.search(msg.content) or replies_to(msg, client.user):
        decision = Decision.rtbp
    else:
        decision = await decide(db.recent(msg.id, 6, msg.channel.id), client.user.id)

    db.set_decision(msg.id, decision)

    worker.notify()
