# cogs/hybrid_commands/moderation.py
import discord
from discord.ext import commands
from discord import app_commands
from datetime import timedelta, datetime, timezone
from utils.config import get_bot_config

_BOT_CFG = get_bot_config()
COMMAND_LOG_CHANNEL_ID = _BOT_CFG.get("COMMAND_LOG_CHANNEL_ID")

# -------------------------
# Utils
# -------------------------
def parse_duration(duration_str: str) -> timedelta | None:
    """
    Convertit une durée (ex: 10s, 5m, 2h, 1j) en timedelta.
    """
    try:
        unit = duration_str[-1]
        value = int(duration_str[:-1])
        if unit == "s":
            return timedelta(seconds=value)
        elif unit == "m":
            return timedelta(minutes=value)
        elif unit == "h":
            return timedelta(hours=value)
        elif unit == "j":
            return timedelta(days=value)
    except Exception:
        return None
    return None


async def send_dm_safe(user: discord.User, embed: discord.Embed):
    try:
        await user.send(embed=embed)
    except Exception:
        pass


async def log_command(bot, title: str, description: str, moderator: discord.User | None = None, color=discord.Color.blue()):
    try:
        ch = bot.get_channel(COMMAND_LOG_CHANNEL_ID)
        if not ch:
            return
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(timezone.utc))
        if moderator:
            embed.add_field(name="Modérateur", value=f"{moderator} ({moderator.id})", inline=True)
        await ch.send(embed=embed)
    except Exception:
        pass


# -------------------------
# Cog Moderation
# -------------------------
class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---- Commande mute ----
    @commands.hybrid_command(name="mute", description="Mute un membre pendant une durée définie")
    @commands.has_permissions(moderate_members=True)
    async def mute(self, ctx: commands.Context, member: discord.Member, duration: str, *, reason: str = "Non spécifiée"):
        td = parse_duration(duration)
        if not td:
            return await ctx.reply("⚠️ Durée invalide. Utilise `10s`, `5m`, `2h`, ou `1j`.", ephemeral=True if ctx.interaction else False)

        try:
            await member.timeout(td, reason=reason)
        except discord.Forbidden:
            return await ctx.reply("❌ Je n’ai pas la permission de mute ce membre.", ephemeral=True if ctx.interaction else False)
        except Exception as e:
            return await ctx.reply(f"❌ Erreur lors du mute : {e}", ephemeral=True if ctx.interaction else False)

        # MP au membre
        dm = discord.Embed(
            title="🚫 Tu as été mute",
            description=f"Durée : **{duration}**\nRaison : {reason}",
            color=discord.Color.red()
        )
        await send_dm_safe(member, dm)

        # Confirmation publique
        await ctx.reply(f"✅ {member.mention} a été mute pour {duration}.", ephemeral=False)

        # Logs
        await log_command(
            self.bot,
            "Mute exécuté",
            f"{member} ({member.id}) a été mute {duration}\n**Raison :** {reason}",
            moderator=ctx.author,
            color=discord.Color.orange()
        )

    # ---- Commande unmute ----
    @commands.hybrid_command(name="unmute", description="Démute un membre")
    @commands.has_permissions(moderate_members=True)
    async def unmute(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Non spécifiée"):
        try:
            await member.timeout(None, reason=reason)
        except discord.Forbidden:
            return await ctx.reply("❌ Je n’ai pas la permission de démute ce membre.", ephemeral=True if ctx.interaction else False)
        except Exception as e:
            return await ctx.reply(f"❌ Erreur lors du démute : {e}", ephemeral=True if ctx.interaction else False)

        # MP au membre
        dm = discord.Embed(
            title="✅ Tu as été démute",
            description=f"Raison : {reason}",
            color=discord.Color.green()
        )
        await send_dm_safe(member, dm)

        # Confirmation publique
        await ctx.reply(f"✅ {member.mention} a été démute.", ephemeral=False)

        # Logs
        await log_command(
            self.bot,
            "Unmute exécuté",
            f"{member} ({member.id}) a été démute\n**Raison :** {reason}",
            moderator=ctx.author,
            color=discord.Color.green()
        )

    # ---- Erreurs ----
    @mute.error
    @unmute.error
    async def on_mod_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply("❌ Tu n’as pas la permission d’utiliser cette commande.", ephemeral=True if ctx.interaction else False)
        elif isinstance(error, commands.BadArgument):
            await ctx.reply("⚠️ Mauvais argument. Vérifie la syntaxe.", ephemeral=True if ctx.interaction else False)
        else:
            await ctx.reply(f"⚠️ Une erreur est survenue : {error}", ephemeral=True if ctx.interaction else False)


async def setup(bot):
    await bot.add_cog(Moderation(bot))