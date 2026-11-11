import asyncio
import logging
import time

import discord
from pydantic_ai import ModelMessage

import db
from agent import keepy
from config import BATCH, MAX_TOKENS, RESET_AFTER, RUN_TIMEOUT

from .serialize import serialize
from .typing import TypingKeeper

log = logging.getLogger(__name__)


class Worker:
    def __init__(self, client: discord.Client):
        self.client = client
        self.cursor = db.newest_id()
        self.context: list[ModelMessage] = []
        self.last_active = 0.0
        self.wake = asyncio.Event()

    def notify(self):
        """decision이 하나 확정됐음을 worker에게 알림."""
        self.wake.set()

    async def start(self):
        while True:
            await self.wake.wait()
            self.wake.clear()

            rows = db.batch(self.cursor, BATCH)
            
            if any(m.decision == "rtbp" for m in rows):
                await self.process(rows)
                self.cursor = rows[-1].id

    async def process(self, rows: list[db.Msg]):
        if time.time() - self.last_active > RESET_AFTER:
            self.context = []

        bot_id = self.client.user.id
        prompt = serialize(rows, bot_id)
        
        if self.context:
            prompt = f"<recent>\n{serialize(db.recent(rows[0].id - 1, BATCH), bot_id)}\n</recent>\n\n<new>\n{prompt}\n</new>"

        # rtbp 채널마다 '입력 중...'을 계속 켜 두고, 그 채널에 답장을 보내는 순간 끈다 (답장 후 되살아나면 유령 타이핑이 된다)
        # 같은 채널에 rtbp가 여럿이면 첫 답장 이후로는 표시가 없다. 하네스는 모델이 몇 번 답할지 모르므로 감수한다
        typing = TypingKeeper(self.client)

        for channel_id in {m.channel_id for m in rows if m.decision == "rtbp"}:
            typing.start(channel_id)

        try:
            result = await keepy.run(
                prompt, deps=self.client, message_history=self.context, timeout=RUN_TIMEOUT, capabilities=[typing.hooks()]
            )
        except Exception:
            log.exception("worker run failed")
            return
        finally:
            await typing.stop_all()
       
        self.context, self.last_active = result.all_messages(), time.time()
       
        if result.response.usage.total_tokens > MAX_TOKENS:
            self.context = []
