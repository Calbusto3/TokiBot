import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from utils.embed_utils import brand_embed, add_kv_fields, format_platform
from utils.uptime import format_uptime
from utils.config import get_bot_config

class Info(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cfg = get_bot_config()

    @app_commands.command(name="ping", description="Voir la latence du bot")
    @app_commands.describe(ephemeral="Répondre en privé")
    async def ping(self, interaction: discord.Interaction, ephemeral: bool | None = False):
        gateway_ms = round(self.bot.latency * 1000)
        emb = brand_embed("🏓 Pong", "Statut de la latence")
        add_kv_fields(
            emb,
            {
                "Gateway": f"{gateway_ms} ms",
            },
            inline=True,
        )
        await interaction.response.send_message(embed=emb, ephemeral=bool(ephemeral))

    @app_commands.command(name="health", description="État de santé du bot (uptime, latence)")
    @app_commands.describe(ephemeral="Répondre en privé")
    async def health(self, interaction: discord.Interaction, ephemeral: bool | None = True):
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
        await interaction.response.send_message(embed=emb, ephemeral=bool(ephemeral))

    @app_commands.command(name="botinfo", description="Informations sur le bot")
    @app_commands.describe(ephemeral="Répondre en privé")
    async def botinfo(self, interaction: discord.Interaction, ephemeral: bool | None = False):
        try:
            guilds = len(self.bot.guilds)
        except Exception:
            guilds = 0
        try:
            users = 0
            for g in getattr(self.bot, "guilds", []) or []:
                try:
                    users += int(getattr(g, "member_count", 0) or 0)
                except Exception:
                    continue
        except Exception:
            users = 0

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
        try:
            owners = []
            cfg_ids = self._cfg.get("EXTRA_OWNER_IDS", []) or []
            for oid in cfg_ids:
                try:
                    user = await self.bot.fetch_user(int(oid))
                    owners.append(str(user))
                except Exception:
                    owners.append(str(oid))
            if owners:
                emb.add_field(name="Propriétaires", value=", ".join(owners)[:1024], inline=False)
        except Exception:
            pass

        try:
            if self.bot.user and getattr(self.bot.user, "display_avatar", None):
                emb.set_thumbnail(url=self.bot.user.display_avatar.url)
        except Exception:
            pass

        await interaction.response.send_message(embed=emb, ephemeral=bool(ephemeral))

    @app_commands.command(name="serverinfo", description="Informations sur le serveur courant")
    @app_commands.describe(ephemeral="Répondre en privé")
    async def serverinfo(self, interaction: discord.Interaction, ephemeral: bool | None = False):
        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message(
                "❌ Cette commande doit être utilisée dans un serveur.", ephemeral=True
            )
        try:
            created = guild.created_at.replace(tzinfo=timezone.utc) if guild.created_at and guild.created_at.tzinfo is None else guild.created_at
        except Exception:
            created = None
        emb = brand_embed("🛡️ Informations du serveur")
        try:
            created_txt = created.strftime("%d/%m/%Y %H:%M UTC") if created else "Inconnu"
        except Exception:
            created_txt = "Inconnu"
        try:
            roles_count = len(guild.roles) if guild.roles else 0
        except Exception:
            roles_count = 0
        try:
            text_channels = len([c for c in guild.channels if isinstance(c, discord.TextChannel)])
        except Exception:
            text_channels = 0
        add_kv_fields(
            emb,
            {
                "Nom": getattr(guild, "name", "Inconnu"),
                "ID": str(getattr(guild, "id", "?")),
                "Créé le": created_txt,
                "Propriétaire": str(getattr(guild, "owner", None)) if getattr(guild, "owner", None) else "Inconnu",
                "Membres": str(getattr(guild, "member_count", 0) or 0),
                "Rôles": str(roles_count),
                "Salon texte": str(text_channels),
            },
            inline=False,
        )
        if guild.icon:
            emb.set_thumbnail(url=guild.icon.url)
        await interaction.response.send_message(embed=emb, ephemeral=bool(ephemeral))

async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))
