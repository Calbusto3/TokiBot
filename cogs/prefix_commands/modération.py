import discord
from discord.ext import commands, tasks
import asyncio
import json
import re
import os
import time
from datetime import datetime, timedelta, timezone
from utils.config import get_bot_config
from utils.logger import get_logger
from utils.config import read_json, write_json

# === CONFIG ===
_BOT_CFG = get_bot_config()
LOG_CHANNEL_ID = _BOT_CFG.get("COMMAND_LOG_CHANNEL_ID")
MODERATOR_ROLE_ID = _BOT_CFG.get("MODERATOR_ROLE_ID")
DATA_FILE = "mod_data.json"
MAX_TIMEOUT_SECONDS = 28 * 24 * 3600  # 28 jours en secondes

# === UTILS PERSISTENCE ===

def load_mod_data():
    data = read_json(DATA_FILE, {"temp_mutes": [], "temp_bans": []})
    # Validation basique
    if not isinstance(data, dict):
        return {"temp_mutes": [], "temp_bans": []}
    data.setdefault("temp_mutes", [])
    data.setdefault("temp_bans", [])
    return data

def save_mod_data(data):
    ok = write_json(DATA_FILE, data)
    if not ok:
        logger = get_logger(__name__)
        logger.warning("Échec de sauvegarde de mod_data.json")
    return ok

# === PARSING DURÉES ===

def parse_duration(duration_str):
    match = re.match(r"^(\d+)([smhj])$", duration_str.lower())
    if not match:
        return 0
    num, unit = match.groups()
    num = int(num)
    mult = {"s": 1, "m": 60, "h": 3600, "j": 86400}
    return num * mult[unit]

# === RESOLUTION MEMBRE ===

async def resolve_member(ctx, arg):
    # Mention
    if ctx.message.mentions:
        return ctx.message.mentions[0]
    # ID
    try:
        member = ctx.guild.get_member(int(arg))
        if member:
            return member
    except (ValueError, TypeError):
        pass
    # Pseudo / Surnom
    arg = arg.lower()
    for m in ctx.guild.members:
        if m.name.lower() == arg or m.display_name.lower() == arg:
            return m
    return None

# === EMBED DM ===

async def notify_dm(user, title, description, color):
    embed = discord.Embed(title=title, description=description, color=color)
    try:
        await user.send(embed=embed)
    except Exception:
        pass  # DM fermé ou impossible

# === EMBED LOGS ===

async def log_action(guild, action, moderator, target, reason):
    log_channel = guild.get_channel(LOG_CHANNEL_ID)
    if not log_channel:
        return
    embed = discord.Embed(
        title=f"Modération : {action}",
        description=f"Cible : {getattr(target, 'mention', str(target))}\nRaison : {reason}",
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )
    try:
        mod_text = getattr(moderator, 'mention', str(moderator))
    except Exception:
        mod_text = str(moderator)
    embed.set_footer(text=f"Par {mod_text}")
    await log_channel.send(embed=embed)

# === DROITS MODÉRATEUR ===

def has_mod_rights(member):
    if member.guild_permissions.administrator:
        return True
    for r in member.roles:
        if r.id == MODERATOR_ROLE_ID:
            return True
    return False

def bot_has_permissions(ctx, perms: list):
    bot_member = ctx.guild.me
    chan_perms = ctx.channel.permissions_for(bot_member)
    for perm in perms:
        if not getattr(chan_perms, perm, False):
            return False
    return True

def role_hierarchy_check(ctx, target: discord.Member):
    # Protéger le propriétaire du serveur
    if target == ctx.guild.owner:
        return False
    # Hiérarchie vs BOT
    bot_top = ctx.guild.me.top_role.position
    target_top = target.top_role.position
    if target_top >= bot_top:
        return False
    # Hiérarchie vs AUTEUR (modérateur qui lance la commande)
    author_top = ctx.author.top_role.position
    if target_top >= author_top and ctx.author != ctx.guild.owner:
        return False
    return True

# === COG PRINCIPAL ===
logger = get_logger(__name__)

class Moderation_prefix(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mod_data = load_mod_data()
        self.temp_bans = self.mod_data.get("temp_bans", [])
        # Initialise également temp_mutes pour éviter les erreurs futures
        self.temp_mutes = self.mod_data.get("temp_mutes", [])
        self.check_temps.start()

    def cog_unload(self):
        self.check_temps.cancel()

    # === BOUCLE CHECK TEMPORAIRES ===
    @tasks.loop(seconds=10)
    async def check_temps(self):
        now = time.time()
        guilds = self.bot.guilds
        changed = False

        # BANS
        for ban in self.temp_bans[:]:
            if ban["end_time"] and now >= ban["end_time"]:
                for guild in guilds:
                    try:
                        await guild.unban(discord.Object(id=ban["user_id"]))
                        await log_action(guild, "Unban (auto)", "Système", f"<@{ban['user_id']}>", "Ban expiré")
                    except Exception:
                        pass
                self.temp_bans.remove(ban)
                changed = True

        if changed:
            self.mod_data["temp_mutes"] = self.temp_mutes
            self.mod_data["temp_bans"] = self.temp_bans
            save_mod_data(self.mod_data)

    # === Ban ===
    @commands.command()
    async def ban(self, ctx, member_arg: str, duration: str = None, *, reason="Aucune raison"):
        if not has_mod_rights(ctx.author):
            await ctx.send("Accès refusé : tu n'es pas modérateur.")
            return
        if not bot_has_permissions(ctx, ["ban_members"]):
            await ctx.send("Le bot n'a pas la permission de bannir.")
            return
        member = await resolve_member(ctx, member_arg)
        if not member:
            await ctx.send("Membre cible introuvable.")
            return
        if not role_hierarchy_check(ctx, member):
            await ctx.send("Impossible : cible trop haut dans la hiérarchie.")
            return
        # Remove ban existant
        self.temp_bans = [b for b in self.temp_bans if b["user_id"] != member.id]
        end_time = None
        if duration:
            seconds = parse_duration(duration)
            if seconds == 0:
                await ctx.send("Durée invalide.")
                return
            if seconds > MAX_TIMEOUT_SECONDS:
                seconds = MAX_TIMEOUT_SECONDS
                await ctx.send("⏱️ Durée trop longue, limitée à 28 jours.")
            end_time = time.time() + seconds
            self.temp_bans.append({
                "user_id": member.id,
                "end_time": end_time,
                "reason": reason,
                "moderator_id": ctx.author.id
            })
            self.mod_data["temp_bans"] = self.temp_bans
            save_mod_data(self.mod_data)
        await notify_dm(member, "Ban", f"Vous êtes banni pour : {reason}\nDurée : {duration if duration else 'définitif'}", discord.Color.red())
        try:
            await ctx.guild.ban(member, reason=reason)
        except Exception:
            await ctx.send("Erreur lors du ban.")
            return
        embed = discord.Embed(title="Ban appliqué", description=f"{member.mention} banni pour {reason}", color=discord.Color.red())
        await ctx.send(embed=embed)
        await log_action(ctx.guild, "Ban", ctx.author, member, reason)

    # === Unban ===
    @commands.command()
    async def unban(self, ctx, user_arg: str, duration: str = None):
        if not has_mod_rights(ctx.author):
            await ctx.send("Accès refusé : tu n'es pas modérateur.")
            return
        if not bot_has_permissions(ctx, ["ban_members"]):
            await ctx.send("Le bot n'a pas la permission de débannir.")
            return
        # Trouver user
        user_id = None
        try:
            user_id = int(user_arg)
        except ValueError:
            pass
        bans = await ctx.guild.bans()
        user = None
        for ban_entry in bans:
            if user_id and ban_entry.user.id == user_id:
                user = ban_entry.user
                break
            if ban_entry.user.name.lower() == user_arg.lower():
                user = ban_entry.user
                break
        if not user:
            await ctx.send("Utilisateur non banni dans ce serveur.")
            return
        # Remove ban
        self.temp_bans = [b for b in self.temp_bans if b["user_id"] != user.id]
        self.mod_data["temp_bans"] = self.temp_bans
        save_mod_data(self.mod_data)
        try:
            await ctx.guild.unban(user)
        except Exception:
            await ctx.send("Erreur lors du unban.")
            return
        await notify_dm(user, "Unban", "Vous avez été débanni du serveur !", discord.Color.green())
        embed = discord.Embed(title="Unban appliqué", description=f"{user.mention} débanni !", color=discord.Color.green())
        await ctx.send(embed=embed)
        await log_action(ctx.guild, "Unban", ctx.author, user, "Unban manuel")
        # Si durée fournie après unban, rebannir plus tard
        if duration:
            seconds = parse_duration(duration)
            if seconds == 0:
                await ctx.send("Durée invalide pour rebannir.")
                return
            if seconds > MAX_TIMEOUT_SECONDS:
                seconds = MAX_TIMEOUT_SECONDS
                await ctx.send("⏱️ Durée trop longue, limitée à 28 jours pour reban.")
            end_time = time.time() + seconds
            self.temp_bans.append({
                "user_id": user.id,
                "end_time": end_time,
                "reason": "Reban temporaire",
                "moderator_id": ctx.author.id
            })
            self.mod_data["temp_bans"] = self.temp_bans
            save_mod_data(self.mod_data)

    # === Kick ===
    @commands.command()
    async def kick(self, ctx, member_arg: str, *, reason="Aucune raison"):
        if not has_mod_rights(ctx.author):
            await ctx.send("Accès refusé : tu n'es pas modérateur.")
            return
        if not bot_has_permissions(ctx, ["kick_members"]):
            await ctx.send("Le bot n'a pas la permission d'expulser (kick).")
            return
        member = await resolve_member(ctx, member_arg)
        if not member:
            await ctx.send("Membre cible introuvable.")
            return
        if not role_hierarchy_check(ctx, member):
            await ctx.send("Impossible : cible trop haut dans la hiérarchie.")
            return
        await notify_dm(member, "Kick", f"Vous êtes expulsé du serveur pour : {reason}", discord.Color.orange())
        try:
            await member.kick(reason=reason)
        except Exception:
            await ctx.send("Erreur lors du kick.")
            return
        embed = discord.Embed(title="Kick appliqué", description=f"{member.mention} expulsé pour {reason}", color=discord.Color.orange())
        await ctx.send(embed=embed)
        await log_action(ctx.guild, "Kick", ctx.author, member, reason)

# === SETUP ===

async def setup(bot):
    await bot.add_cog(Moderation_prefix(bot))