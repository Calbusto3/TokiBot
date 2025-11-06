import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from utils.embed_utils import brand_embed, add_kv_fields, format_platform
from utils.uptime import format_uptime

class Info(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="ping", description="Voir la latence du bot")
    async def ping(self, interaction: discord.Interaction):
        gateway_ms = round(self.bot.latency * 1000)
        emb = brand_embed("🏓 Pong", "Statut de la latence")
        add_kv_fields(
            emb,
            {
                "Gateway": f"{gateway_ms} ms",
            },
            inline=True,
        )
        await interaction.response.send_message(embed=emb)

    @app_commands.command(name="health", description="État de santé du bot (uptime, latence)")
    async def health(self, interaction: discord.Interaction):
        gateway_ms = round(self.bot.latency * 1000)
        emb = brand_embed("✅ Health")
        add_kv_fields(
            emb,
            {
                "Uptime": format_uptime(),
                "Gateway": f"{gateway_ms} ms",
            },
            inline=True,
        )
        await interaction.response.send_message(embed=emb, ephemeral=True)

    @app_commands.command(name="botinfo", description="Informations sur le bot")
    async def botinfo(self, interaction: discord.Interaction):
        guilds = len(self.bot.guilds)
        users = sum(g.member_count or 0 for g in self.bot.guilds)
        emb = brand_embed("🤖 Informations sur TokiBot")
        add_kv_fields(
            emb,
            {
                "Uptime": format_uptime(),
                "Serveurs": str(guilds),
                "Utilisateurs (approx)": str(users),
                "Plateforme": format_platform(),
            },
            inline=False,
        )
        if self.bot.user and self.bot.user.display_avatar:
            emb.set_thumbnail(url=self.bot.user.display_avatar.url)
        await interaction.response.send_message(embed=emb)

    @app_commands.command(name="serverinfo", description="Informations sur le serveur courant")
    async def serverinfo(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message(
                "❌ Cette commande doit être utilisée dans un serveur.", ephemeral=True
            )
        created = guild.created_at.replace(tzinfo=timezone.utc) if guild.created_at.tzinfo is None else guild.created_at
        emb = brand_embed("🛡️ Informations du serveur")
        add_kv_fields(
            emb,
            {
                "Nom": guild.name,
                "ID": str(guild.id),
                "Créé le": created.strftime("%d/%m/%Y %H:%M UTC"),
                "Propriétaire": str(guild.owner) if guild.owner else "Inconnu",
                "Membres": str(guild.member_count),
                "Rôles": str(len(guild.roles) if guild.roles else 0),
                "Salon texte": str(len([c for c in guild.channels if isinstance(c, discord.TextChannel)])),
            },
            inline=False,
        )
        if guild.icon:
            emb.set_thumbnail(url=guild.icon.url)
        await interaction.response.send_message(embed=emb)

async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))
