import asyncio
import logging
import time

import discord
from pydantic_ai import ModelMessage

import db
from agent import keepy
from config import BATCH, MAX_TOKENS, RESET_AFTER, RUN_TIMEOUT

from .serialize import serialize

log = logging.getLogger(__name__)


class Worker:
    def __init__(self, client: discord.Client):
        self.client = client
        self.cursor = db.newest_id()
        self.context: list[ModelMessage] = []
        self.last_active = 0.0
        self.wake = asyncio.Event()

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
        
        if not self.context:
            prompt = f"<recent>\n{serialize(db.recent(rows[0].id - 1, BATCH), bot_id)}\n</recent>\n\n<new>\n{prompt}\n</new>"

        # '입력 중...' 표시는 디스코드가 10초 뒤 알아서 끄고, 메시지를 보내면 즉시 지운다. 재전송 루프를 두면 보낸 뒤에도 되살아나므로 한 번만 보낸다
        for cid in {m.channel_id for m in rows if m.decision == "rtbp"}:
            try:
                await self.client.get_partial_messageable(cid).trigger_typing()
            except discord.HTTPException:
                log.warning("typing failed in %s", cid, exc_info=True)

        try:
            result = await keepy.run(prompt, deps=self.client, message_history=self.context, timeout=RUN_TIMEOUT)
        except Exception:
            log.exception("worker run failed")
            return
       
        self.context, self.last_active = result.all_messages(), time.time()
       
        if result.response.usage.total_tokens > MAX_TOKENS:
            self.context = []
