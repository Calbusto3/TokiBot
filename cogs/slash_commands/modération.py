import discord
from discord import app_commands
from discord.ext import commands
from datetime import timedelta, datetime, timezone
from utils.config import get_bot_config

_BOT_CFG = get_bot_config()
LOG_CHANNEL_ID = _BOT_CFG.get("COMMAND_LOG_CHANNEL_ID")

class ModerationSlash(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ======================
    # Utils
    # ======================
    async def dm_user(self, user: discord.User, title: str, description: str, color=discord.Color.blue()):
        """Envoie un embed simple en DM au membre"""
        embed = discord.Embed(title=title, description=description, color=color)
        try:
            await user.send(embed=embed)
        except:
            pass  # Si DM impossible, on ignore

    async def log_action(self, interaction: discord.Interaction, action: str, target: discord.User, reason: str = None):
        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(
                title=f"🛡️ {action}",
                color=discord.Color.blurple(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Modérateur", value=f"{interaction.user} ({interaction.user.id})", inline=False)
            embed.add_field(name="Cible", value=f"{target} ({target.id})", inline=False)
            embed.add_field(name="Raison", value=reason or "Aucune raison fournie", inline=False)
            await log_channel.send(embed=embed)

    # ======================
    # BAN / UNBAN
    # ======================
    @app_commands.command(name="ban", description="Ban un membre du serveur.")
    @app_commands.checks.cooldown(1, 5.0)
    @app_commands.describe(member="Membre à bannir", reason="Raison du ban")
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        # Vérifications de permissions de l'appelant et du bot
        if not (interaction.user.guild_permissions.ban_members or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("❌ Tu n'as pas la permission de bannir.", ephemeral=True)
        bot_perms = interaction.channel.permissions_for(interaction.guild.me)
        if not bot_perms.ban_members:
            return await interaction.response.send_message("❌ Je n'ai pas la permission de bannir ici.", ephemeral=True)
        # Hiérarchie vs bot
        if member.top_role >= interaction.guild.me.top_role or member == interaction.guild.owner:
            return await interaction.response.send_message("❌ Je ne peux pas bannir cette cible (hiérarchie).", ephemeral=True)
        await self.dm_user(
            member,
            "🚫 Vous avez été banni",
            f"Raison : {reason or 'Aucune'}",
            discord.Color.red()
        )

        try:
            await member.ban(reason=reason)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Échec du ban: permission refusée.", ephemeral=True)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Erreur lors du ban: {e}", ephemeral=True)

        await interaction.response.send_message(f"🚫 {member} a été banni. Raison: {reason or 'Aucune'}")
        await self.log_action(interaction, "Ban", member, reason)

    @app_commands.command(name="unban", description="Unban un utilisateur avec son ID.")
    @app_commands.checks.cooldown(1, 5.0)
    @app_commands.describe(user_id="ID du membre à débannir")
    async def unban(self, interaction: discord.Interaction, user_id: str):
        if not (interaction.user.guild_permissions.ban_members or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("❌ Tu n'as pas la permission de débannir.", ephemeral=True)
        bot_perms = interaction.channel.permissions_for(interaction.guild.me)
        if not bot_perms.ban_members:
            return await interaction.response.send_message("❌ Je n'ai pas la permission de débannir ici.", ephemeral=True)
        user = await self.bot.fetch_user(int(user_id))
        try:
            await interaction.guild.unban(user, reason="Unban manuel")
        except discord.NotFound:
            return await interaction.response.send_message("❌ Cet utilisateur n'est pas banni.", ephemeral=True)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Échec du unban: permission refusée.", ephemeral=True)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Erreur lors du unban: {e}", ephemeral=True)

        await self.dm_user(
            user,
            "✅ Vous avez été débanni",
            "Vous pouvez à nouveau rejoindre le serveur",
            discord.Color.green()
        )

        await interaction.response.send_message(f"✅ {user} a été débanni.")
        await self.log_action(interaction, "Unban", user, "Manuel")

    # ======================
    # KICK
    # ======================
    @app_commands.command(name="kick", description="Expulse un membre du serveur.")
    @app_commands.checks.cooldown(1, 5.0)
    @app_commands.describe(member="Membre à expulser", reason="Raison du kick")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        if not (interaction.user.guild_permissions.kick_members or interaction.user.guild_permissions.administrator):
            return await interaction.response.send_message("❌ Tu n'as pas la permission de kick.", ephemeral=True)
        bot_perms = interaction.channel.permissions_for(interaction.guild.me)
        if not bot_perms.kick_members:
            return await interaction.response.send_message("❌ Je n'ai pas la permission d'expulser ici.", ephemeral=True)
        if member.top_role >= interaction.guild.me.top_role or member == interaction.guild.owner:
            return await interaction.response.send_message("❌ Je ne peux pas expulser cette cible (hiérarchie).", ephemeral=True)
        await self.dm_user(
            member,
            "👢 Vous avez été expulsé",
            f"Raison : {reason or 'Aucune'}",
            discord.Color.orange()
        )

        try:
            await member.kick(reason=reason)
        except discord.Forbidden:
            return await interaction.response.send_message("❌ Échec du kick: permission refusée.", ephemeral=True)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Erreur lors du kick: {e}", ephemeral=True)

        await interaction.response.send_message(f"{member} a été expulsé. Raison: {reason or 'Aucune'}")
        await self.log_action(interaction, "Kick", member, reason)

async def setup(bot):
    await bot.add_cog(ModerationSlash(bot))
