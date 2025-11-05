from __future__ import annotations
import platform
from datetime import datetime, timezone
import discord

BRAND_COLOR = discord.Color.blurple()

def brand_embed(title: str | None = None, description: str | None = None, *, color: discord.Color | None = None) -> discord.Embed:
    emb = discord.Embed(
        title=title or discord.Embed.Empty,
        description=description or discord.Embed.Empty,
        color=color or BRAND_COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    emb.set_footer(text="TokiBot • Qualité professionnelle")
    return emb

def add_kv_fields(emb: discord.Embed, fields: dict[str, str], *, inline: bool = False) -> None:
    for k, v in fields.items():
        emb.add_field(name=str(k)[:256], value=str(v)[:1024], inline=inline)

def format_platform() -> str:
    return f"Python {platform.python_version()} • {platform.system()} {platform.release()}"
