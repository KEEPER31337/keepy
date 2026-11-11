import asyncio
import logging
import time

import discord
from pydantic_ai import RunContext, ToolCallPart, ToolDefinition
from pydantic_ai.capabilities import Hooks

from config import TYPING_INTERVAL, TYPING_TIMEOUT

log = logging.getLogger(__name__)

# 디스코드에는 타이핑을 끄는 API가 없으므로, 한 번 켜면 10초가 지나거나 봇이 그 채널에 메시지를 보내야 꺼진다
REPLY_TOOLS = {"send_message", "react_message"}


class TypingKeeper:
    """채널마다 '입력 중...'을 주기적으로 다시 켜는 태스크를 하나씩 둔다"""

    def __init__(self, client: discord.Client):
        self.client = client
        self.tasks: dict[int, asyncio.Task] = {}

    def start(self, channel_id: int):
        if channel_id not in self.tasks:
            self.tasks[channel_id] = asyncio.create_task(self._loop(channel_id))

    def stop(self, channel_id: int):
        if task := self.tasks.pop(channel_id, None):
            task.cancel()

    async def stop_all(self):
        tasks = list(self.tasks.values())
        self.tasks.clear()
        
        for task in tasks:
            task.cancel()

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _loop(self, channel_id: int):
        channel = self.client.get_partial_messageable(channel_id)
        deadline = time.monotonic() + TYPING_TIMEOUT

        while time.monotonic() < deadline:
            try:
                await channel.trigger_typing()
            except discord.HTTPException:
                # 권한 없음 같은 오류는 반복해도 똑같이 실패하므로 이 채널만 포기한다
                log.warning("typing failed in %s", channel_id, exc_info=True)
                return

            await asyncio.sleep(TYPING_INTERVAL)

    def hooks(self) -> Hooks:
        """답장 도구가 실행되기 직전에 그 채널의 타이핑을 멈춘다.

        전송 뒤에 멈추면 그 사이 날아간 재전송 요청이 메시지보다 늦게 처리되어 표시가 되살아날 수 있다
        """

        async def before_tool_execute(
            ctx: RunContext, *, call: ToolCallPart, tool_def: ToolDefinition, args: dict
        ) -> dict:
            if tool_def.name in REPLY_TOOLS:
                self.stop(args["channel_id"])

            return args

        return Hooks(before_tool_execute=before_tool_execute)
