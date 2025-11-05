import discord
from discord.ext import commands
from discord import app_commands
from utils.logger import get_logger
from datetime import datetime, timezone

logger = get_logger(__name__)

USER_ERR_PREFIX = "❌ "

class GlobalErrorHandler(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Prefix commands errors
    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        try:
            # Unwrap original
            err = getattr(error, "original", error)

            # Ignore if command has local error handler
            if hasattr(ctx.command, "on_error"):
                return

            # Cooldown
            if isinstance(err, commands.CommandOnCooldown):
                await ctx.reply(f"⏳ Patiente {err.retry_after:.1f}s avant de réutiliser cette commande.")
                return

            # Permissions
            if isinstance(err, commands.MissingPermissions):
                await ctx.reply(USER_ERR_PREFIX + "Tu n'as pas la permission d'utiliser cette commande.")
                return
            if isinstance(err, commands.BotMissingPermissions):
                await ctx.reply(USER_ERR_PREFIX + "Je n'ai pas les permissions nécessaires pour exécuter cela ici.")
                return

            # Mauvais arguments
            if isinstance(err, (commands.BadArgument, commands.MissingRequiredArgument)):
                usage = f"+{ctx.command.qualified_name} {ctx.command.signature}" if ctx.command else "(usage indisponible)"
                await ctx.reply(USER_ERR_PREFIX + f"Arguments invalides. Usage: `{usage}`")
                return

            # Discord API errors
            if isinstance(err, discord.Forbidden):
                await ctx.reply(USER_ERR_PREFIX + "Action interdite par Discord (permissions).")
                return
            if isinstance(err, discord.HTTPException):
                await ctx.reply(USER_ERR_PREFIX + "Erreur Discord inattendue. Réessaie plus tard.")
                logger.warning(f"HTTPException {err.status} in {ctx.command}: {err.text if hasattr(err,'text') else err}")
                return

            # Fallback
            await ctx.reply(USER_ERR_PREFIX + "Une erreur est survenue. L'équipe a été notifiée.")
            logger.exception(f"Unhandled command error in {ctx.command}: {err}")
        except Exception:
            logger.exception("Error while handling on_command_error")

async def setup(bot: commands.Bot):
    cog = GlobalErrorHandler(bot)
    await bot.add_cog(cog)

    # Slash commands errors
    @bot.tree.error
    async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        try:
            err = getattr(error, "original", error)

            # Cooldown
            if isinstance(err, app_commands.CommandOnCooldown):
                await interaction.response.send_message(
                    f"⏳ Patiente {err.retry_after:.1f}s avant de réutiliser cette commande.", ephemeral=True
                )
                return

            # Permissions
            if isinstance(err, app_commands.MissingPermissions):
                await interaction.response.send_message(
                    USER_ERR_PREFIX + "Tu n'as pas la permission d'utiliser cette commande.", ephemeral=True
                )
                return

            # Conversion / validation
            if isinstance(err, app_commands.TransformerError):
                await interaction.response.send_message(
                    USER_ERR_PREFIX + "Arguments invalides.", ephemeral=True
                )
                return

            # Discord API errors
            if isinstance(err, discord.Forbidden):
                await interaction.response.send_message(
                    USER_ERR_PREFIX + "Action interdite par Discord (permissions).", ephemeral=True
                )
                return
            if isinstance(err, discord.HTTPException):
                await interaction.response.send_message(
                    USER_ERR_PREFIX + "Erreur Discord inattendue. Réessaie plus tard.", ephemeral=True
                )
                logger.warning(f"HTTPException {err.status} in slash: {err}")
                return

            # Fallback
            msg = USER_ERR_PREFIX + "Une erreur est survenue. L'équipe a été notifiée."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            logger.exception(f"Unhandled app command error: {err}")
        except Exception:
            logger.exception("Error while handling on_app_command_error")
