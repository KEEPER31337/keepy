import asyncio
import logging
from datetime import datetime, timedelta, timezone

import discord

import db
from agent.tools.message import NO_MASS_MENTIONS
from config import REMINDER_CUTOFF, REMINDER_INTERVAL

log = logging.getLogger(__name__)


class ReminderWorker:
    """예약된 리마인더를 따로 추가적으로 에이전트를 거치지 않고 채널에 그대로 보내는 Worker"""

    def __init__(self, client: discord.Client):
        self.client = client

    async def start(self):
        await self.client.wait_until_ready()

        while True:
            await self.process()
            await asyncio.sleep(REMINDER_INTERVAL)

    async def process(self):
        now = datetime.now(timezone.utc)

        for r in db.due_reminders(now.isoformat(), (now - timedelta(seconds=REMINDER_CUTOFF)).isoformat()):
            # TaskGroup 안에서 예외가 새면 봇 전체가 죽으므로 실패할 수 있는 전송만 감싼다
            try:
                await self.client.get_partial_messageable(r.channel_id).send(
                    r.content, allowed_mentions=NO_MASS_MENTIONS, suppress_embeds=True
                )
            except Exception as e:
                if not (isinstance(e, discord.HTTPException) and 400 <= e.status < 500):
                    log.warning("reminder %s failed, retrying next tick", r.id, exc_info=True)
                    continue

                # 권한 없음, 지워진 채널, 빈 내용 같은 4xx는 다시 해도 똑같이 실패하므로 포기한다
                log.warning("reminder %s dropped", r.id, exc_info=True)

            db.mark_done(r.id)
