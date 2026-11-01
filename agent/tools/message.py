import discord
from pydantic_ai import RunContext

NO_MASS_MENTIONS = discord.AllowedMentions(everyone=False, roles=False)


async def send_message(
    ctx: RunContext[discord.Client], channel_id: int, content: str, reply_to: int | None = None
) -> str:
    """채널에 메시지를 보낸다. reply_to에 message_id를 주면 그 메시지에 답장한다."""

    channel = ctx.deps.get_partial_messageable(channel_id)
    ref = discord.MessageReference(message_id=reply_to, channel_id=channel_id) if reply_to else None

    sent = [
        await channel.send(content[i:i + 2000], reference=(ref if i == 0 else None), allowed_mentions=NO_MASS_MENTIONS)
        for i in range(0, len(content), 2000)
    ]

    return "sent " + ", ".join(f"msg_{m.id}" for m in sent)


async def react_message(ctx: RunContext[discord.Client], channel_id: int, message_id: int, emoji: str) -> str:
    """메시지에 유니코드 이모지로 반응을 단다."""

    await ctx.deps.get_partial_messageable(channel_id).get_partial_message(message_id).add_reaction(emoji)

    return f"reacted {emoji} to msg_{message_id}"
