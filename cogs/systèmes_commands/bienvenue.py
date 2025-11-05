import discord
from discord.ext import commands
import json
import os
import datetime
import asyncio
from datetime import datetime as dt, timezone
from utils.config import get_bot_config

CONFIG_FILE = "welcome_config.json"
_BOT_CFG = get_bot_config()
LOG_CHANNEL_ID = _BOT_CFG.get("COMMAND_LOG_CHANNEL_ID")

class WelcomeSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = self.load_config()
        self.invites = {}

    # Charger la config
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"active": False, "channel_id": _BOT_CFG.get("WELCOME_CHANNEL_ID")}

    # Sauvegarder la config
    def save_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4)

    # Logs d’exécution de commande
    async def log_command(self, ctx):
        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(
                title="📜 Commande exécutée",
                color=discord.Color.orange(),
                timestamp=dt.now(timezone.utc)
            )
            embed.add_field(name="Utilisateur", value=f"{ctx.author} ({ctx.author.id})", inline=False)
            embed.add_field(name="Commande", value=ctx.message.content, inline=False)
            embed.add_field(name="Salon", value=f"{ctx.channel} ({ctx.channel.id})", inline=False)
            await log_channel.send(embed=embed)

    # Commande pour définir le salon de bienvenue
    @commands.command(name="c_welcome")
    @commands.has_permissions(administrator=True)
    async def set_welcome_channel(self, ctx, channel_id: int):
        self.config["channel_id"] = channel_id
        self.save_config()
        msg = await ctx.send(f"✅ Salon de bienvenue défini sur <#{channel_id}>")
        await asyncio.sleep(5)
        await msg.delete()
        await self.log_command(ctx)

    # Commande pour activer
    @commands.command(name="c_active")
    @commands.has_permissions(administrator=True)
    async def activate_welcome(self, ctx):
        self.config["active"] = True
        self.save_config()
        msg = await ctx.send("✅ Système de bienvenue activé")
        await asyncio.sleep(5)
        await msg.delete()
        await self.log_command(ctx)

    # Commande pour désactiver
    @commands.command(name="c_desactive")
    @commands.has_permissions(administrator=True)
    async def deactivate_welcome(self, ctx):
        self.config["active"] = False
        self.save_config()
        msg = await ctx.send("🛑 Système de bienvenue désactivé")
        await asyncio.sleep(5)
        await msg.delete()
        await self.log_command(ctx)

    # Ignorer les erreurs de permission pour éviter les crashs
    @set_welcome_channel.error
    @activate_welcome.error
    @deactivate_welcome.error
    async def ignore_errors(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            return  # Ne rien répondre si pas admin

    # Stocker les invites au démarrage
    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            self.invites[guild.id] = await guild.invites()

    # Détecter l’inviteur lors d’un join
    @commands.Cog.listener()
    async def on_member_join(self, member):
        if not self.config.get("active"):
            return

        guild = member.guild
        welcome_channel = self.bot.get_channel(self.config.get("channel_id"))
        if not welcome_channel:
            return

        # Message d’intro fun et divers
        titles = [
            "🚀 Un nouveau membre arrive !",
            f"🎉 {member.name} a atterri parmi nous !",
            "✨ Une nouvelle étoile brille dans le serveur !",
            "🔥 Préparez-vous, quelqu’un débarque !",
            f"👀 Regardez qui vient d’arriver : {member.name} !",
            "T'as pas oublié de prendre une pizza ?",
            f"T'es là, t'as plus le droit de partir, {member.name} !",
            f"Soyez tous les bienvenus à {member.name} !",
            "Wawawawawawa, bonne arrivée !",
        ]
        import random
        title = random.choice(titles)

        # Chercher qui a invité
        inviter = "via un lien vanity"
        try:
            new_invites = await guild.invites()
            old_invites = self.invites.get(guild.id, [])
            for invite in new_invites:
                old_invite = discord.utils.get(old_invites, code=invite.code)
                if old_invite and invite.uses > old_invite.uses:
                    inviter = f"invité par {invite.inviter}"
                    break
            self.invites[guild.id] = new_invites
        except:
            pass

        # Nombre de membres
        member_count = guild.member_count

        # Message
        await welcome_channel.send(f"{member.mention}")
        embed = discord.Embed(
            title=title,
            description=f"Bienvenue sur **{guild.name}** ! Nous t'espérons un bon séjour parmi nous, amuse-toi bien ^^ 🎊\n"
                        f"👥 Tu es le membre n° **{member_count}**\n"
                        f"🔗 {inviter}",
            color=discord.Color.green()
        )
        thumb_url = None
        try:
            if getattr(member, "avatar", None):
                thumb_url = member.avatar.url
            elif getattr(guild, "icon", None):
                thumb_url = guild.icon.url
        except Exception:
            thumb_url = None
        if thumb_url:
            embed.set_thumbnail(url=thumb_url)
        await welcome_channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(WelcomeSystem(bot))