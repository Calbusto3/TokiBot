import discord
from discord.ext import commands
from discord.utils import get
import json
import os
from datetime import datetime

MODERATOR_ROLE_ID = 1362049467934838985
LOG_COMMANDS_CHANNEL_ID = 1418322935789392110
DATA_FILE = "say_messages.json"

def has_moderator_or_admin():
    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator:
            return True
        mod_role = get(ctx.guild.roles, id=MODERATOR_ROLE_ID)
        return mod_role in ctx.author.roles if mod_role else False
    return commands.check(predicate)


class ExtraCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = load_data()

    async def log_command(self, ctx, reason: str = None):
        """Log la commande dans le salon de log avec raison si fournie"""
        log_channel = self.bot.get_channel(LOG_COMMANDS_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(
                title="Commande exécutée",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="Auteur", value=f"{ctx.author} ({ctx.author.id})", inline=False)
            embed.add_field(name="Nom d'utilisateur", value=f"{ctx.author.name}#{ctx.author.discriminator}", inline=False)
            embed.add_field(name="Commande", value=ctx.command, inline=False)
            embed.add_field(name="Salon", value=f"{ctx.channel} ({ctx.channel.id})", inline=False)
            if reason:
                embed.add_field(name="Raison", value=reason, inline=False)
            await log_channel.send(embed=embed)

    # ---------------- AVATAR ----------------
    @commands.command(name="avatar")
    async def avatar(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(title=f"Avatar de {member}", color=discord.Color.blurple())
        embed.set_image(url=member.display_avatar.url)
        await ctx.send(embed=embed)
        await self.log_command(ctx)

    # ---------------- BANNIÈRE ----------------
    @commands.command(name="banner")
    async def bannier(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        banner_url = member.banner.url if member.banner else None
        if banner_url:
            embed = discord.Embed(title=f"Bannière de {member}", color=discord.Color.blurple())
            embed.set_image(url=banner_url)
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"{member} n'a pas de bannière Discord.")
        await self.log_command(ctx)

    # ---------------- USERINFO ----------------
    @commands.command(name="userinfo")
    async def userinfo(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(title=f"Info utilisateur : {member}", color=discord.Color.blurple())
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Nom complet", value=f"{member} ({member.id})", inline=False)
        embed.add_field(name="Compte créé le", value=member.created_at.strftime("%d/%m/%Y %H:%M:%S"), inline=True)
        embed.add_field(name="A rejoint le serveur", value=member.joined_at.strftime("%d/%m/%Y %H:%M:%S") if member.joined_at else "Inconnu", inline=True)
        roles = [role.mention for role in member.roles if role.name != "@everyone"]
        embed.add_field(name=f"Rôles ({len(roles)})", value=", ".join(roles) if roles else "Aucun", inline=False)
        await ctx.send(embed=embed)
        await self.log_command(ctx)

    # ---------------- HIDE ----------------
    @commands.command(name="hide")
    @has_moderator_or_admin()
    async def hide(self, ctx, channel: discord.TextChannel = None, *, reason: str = None):
        channel = channel or ctx.channel
        if not reason:
            return await ctx.send("❌ Vous devez fournir une raison >.<", ephemeral=True)

        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.view_channel = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)

        for role in ctx.guild.roles:
            if role.id in [MODERATOR_ROLE_ID] or ctx.author.guild_permissions.administrator:
                continue
            await channel.set_permissions(role, overwrite=overwrite)

        await ctx.send(f"🔒 Le salon {channel.mention} a été masqué par vous :3\nRaison : {reason}", ephemeral=True)
        await self.log_command(ctx, reason=reason)

    # ---------------- UNHIDE ----------------
    @commands.command(name="unhide")
    @has_moderator_or_admin()
    async def unhide(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await channel.set_permissions(ctx.guild.default_role, overwrite=None)
        for role in ctx.guild.roles:
            if role.id in [MODERATOR_ROLE_ID] or ctx.author.guild_permissions.administrator:
                continue
            await channel.set_permissions(role, overwrite=None)
        await ctx.send(f"✅ Le salon {channel.mention} est de nouveau visible :D", ephemeral=True)
        await self.log_command(ctx)

    # ---------------- LOCK ----------------
    @commands.command(name="lock")
    @has_moderator_or_admin()
    async def lock(self, ctx, channel: discord.TextChannel = None, *, reason: str = None):
        channel = channel or ctx.channel
        if not reason:
            return await ctx.send("❌ Vous devez fournir une raison >.<", ephemeral=True)

        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)

        for role in ctx.guild.roles:
            if role.id in [MODERATOR_ROLE_ID] or ctx.author.guild_permissions.administrator:
                continue
            await channel.set_permissions(role, overwrite=overwrite)

        await ctx.send(f"🔒 Le salon {channel.mention} a été verrouillé.\nRaison : {reason}", ephemeral=True)
        await self.log_command(ctx, reason=reason)

    # ---------------- UNLOCK ----------------
    @commands.command(name="unlock")
    @has_moderator_or_admin()
    async def unlock(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await channel.set_permissions(ctx.guild.default_role, overwrite=None)
        for role in ctx.guild.roles:
            if role.id in [MODERATOR_ROLE_ID] or ctx.author.guild_permissions.administrator:
                continue
            await channel.set_permissions(role, overwrite=None)
        await ctx.send(f"✅ Le salon {channel.mention} est de nouveau déverrouillé.", ephemeral=True)
        await self.log_command(ctx)


    @commands.command(name="clear", aliases = ["supp"])
    @has_moderator_or_admin()
    async def supprimer(ctx, nombre: int):
        if nombre <= 1:
            await ctx.send("Il faut que le nombre soit supérieur à 1 >.<")
            return
        
        deleted = await ctx.channel.purge(limit=nombre)
        await ctx.send(f"{len(deleted)} messages supprimés.", delete_after=5)
        
    # ===== RESET =====
    @commands.command(name="reset", description="Réinitialise et supprime tous les messages d'un salon.")
    @has_moderator_or_admin()
    async def reset(ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        if not ctx.author.guild_permissions.manage_messages:
            await ctx.send("❌ Vous n'avez pas la permission pour cette commande ;)")
            return

        await channel.purge()
        reset_message = await channel.send("⚠️ Ce salon a été réinitialisé.")
        await reset_message.delete(delay=5)

# cogs/prefix_commands/extra.py
def load_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"messages": {}}, f, indent=2)
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


async def log_command(bot, title: str, description: str, author: discord.User, color=discord.Color.blue()):
    channel = bot.get_channel(LOG_COMMANDS_CHANNEL_ID)
    if not channel:
        return
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.utcnow()
    )
    embed.set_author(name=str(author), icon_url=author.display_avatar.url)
    try:
        await channel.send(embed=embed)
    except Exception:
        pass

    @commands.command(name="parler")
    @commands.has_permissions(administrator=True)
    async def parler(self, ctx: commands.Context, *, content: str):
        """
        Faire parler le bot. Admin seulement.
        Ex:
        +parler Salut tout le monde #général
        """
        await ctx.message.delete()

        # Vérifie si la fin contient un salon mentionné
        target_channel = ctx.channel
        if ctx.message.channel_mentions:
            target_channel = ctx.message.channel_mentions[-1]
            content = content.replace(f"<#{target_channel.id}>", "").strip()

        try:
            sent = await target_channel.send(content)
        except Exception as e:
            return await ctx.send(f"❌ Impossible d'envoyer le message : {e}", delete_after=5)

        # Sauvegarde persistance
        self.data["messages"][str(sent.id)] = {
            "content": content,
            "channel_id": sent.channel.id,
            "author_id": ctx.author.id,
            "timestamp": datetime.utcnow().isoformat()
        }
        save_data(self.data)

        # Log
        await log_command(
            self.bot,
            "Commande +parler exécutée",
            f"Message envoyé dans {sent.channel.mention}\nID: {sent.id}\nContenu: {content}",
            author=ctx.author,
            color=discord.Color.green()
        )

    @commands.command(name="modif_say")
    @commands.has_permissions(administrator=True)
    async def modif_say(self, ctx: commands.Context, message_id: int, *, new_content: str):
        """
        Modifier un message envoyé via +parler (admin only)
        """
        record = self.data["messages"].get(str(message_id))
        if not record:
            return await ctx.send("❌ Aucun message trouvé avec cet ID.", delete_after=5)

        channel = self.bot.get_channel(record["channel_id"])
        if not channel:
            return await ctx.send("❌ Salon introuvable.", delete_after=5)

        try:
            msg = await channel.fetch_message(message_id)
            await msg.edit(content=new_content)
        except discord.NotFound:
            return await ctx.send("❌ Message introuvable (supprimé ?).", delete_after=5)
        except discord.Forbidden:
            return await ctx.send("❌ Je n’ai pas la permission de modifier ce message.", delete_after=5)

        # Mettre à jour persistance
        self.data["messages"][str(message_id)]["content"] = new_content
        self.data["messages"][str(message_id)]["edited_at"] = datetime.utcnow().isoformat()
        save_data(self.data)

        await ctx.send(f"✅ Message `{message_id}` modifié avec succès.", delete_after=5)

        # Log
        await log_command(
            self.bot,
            "Commande +modif_say exécutée",
            f"Message ID {message_id} modifié\nNouveau contenu: {new_content}",
            author=ctx.author,
            color=discord.Color.orange()
        )

async def setup(bot):
    await bot.add_cog(ExtraCommands(bot))