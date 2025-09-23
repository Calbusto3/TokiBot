import discord
from discord.ext import commands
from typing import Optional


def is_admin(member: discord.Member) -> bool:
    return bool(getattr(member.guild_permissions, "administrator", False))


def has_role(member: discord.Member, role_id: int) -> bool:
    return any(r.id == role_id for r in member.roles)


def is_admin_or_role(role_id: int):
    async def predicate(ctx: commands.Context) -> bool:
        if is_admin(ctx.author):
            return True
        return has_role(ctx.author, role_id)
    return commands.check(predicate)
