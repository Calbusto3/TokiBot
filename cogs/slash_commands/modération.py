import discord
from discord import app_commands
from discord.ext import commands
from datetime import timedelta

LOG_CHANNEL_ID = 1418322935789392110

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
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Modérateur", value=f"{interaction.user} ({interaction.user.id})", inline=False)
            embed.add_field(name="Cible", value=f"{target} ({target.id})", inline=False)
            embed.add_field(name="Raison", value=reason or "Aucune raison fournie", inline=False)
            await log_channel.send(embed=embed)

    # ======================
    # BAN / UNBAN
    # ======================
    @app_commands.command(name="ban", description="Ban un membre du serveur.")
    @app_commands.describe(member="Membre à bannir", reason="Raison du ban")
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        await self.dm_user(
            member,
            "🚫 Vous avez été banni",
            f"Raison : {reason or 'Aucune'}",
            discord.Color.red()
        )

        await member.ban(reason=reason)

        await interaction.response.send_message(f"🚫 {member} a été banni. Raison: {reason or 'Aucune'}")
        await self.log_action(interaction, "Ban", member, reason)

    @app_commands.command(name="unban", description="Unban un utilisateur avec son ID.")
    @app_commands.describe(user_id="ID du membre à débannir")
    async def unban(self, interaction: discord.Interaction, user_id: str):
        user = await self.bot.fetch_user(int(user_id))
        await interaction.guild.unban(user, reason="Unban manuel")

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
    @app_commands.describe(member="Membre à expulser", reason="Raison du kick")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        await self.dm_user(
            member,
            "👢 Vous avez été expulsé",
            f"Raison : {reason or 'Aucune'}",
            discord.Color.orange()
        )

        await member.kick(reason=reason)

        await interaction.response.send_message(f"{member} a été expulsé. Raison: {reason or 'Aucune'}")
        await self.log_action(interaction, "Kick", member, reason)

async def setup(bot):
    await bot.add_cog(ModerationSlash(bot))
