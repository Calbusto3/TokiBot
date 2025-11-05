import discord
from discord.ext import commands
from discord.utils import get
import json
import os
from datetime import datetime, timezone
from utils.config import get_bot_config
from utils.logger import get_logger

_BOT_CFG = get_bot_config()
MODERATOR_ROLE_ID = _BOT_CFG.get("MODERATOR_ROLE_ID")
LOG_COMMANDS_CHANNEL_ID = _BOT_CFG.get("COMMAND_LOG_CHANNEL_ID")
DATA_FILE = "say_messages.json"

def has_moderator_or_admin():
    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator:
            return True
        mod_role = get(ctx.guild.roles, id=MODERATOR_ROLE_ID)
        return mod_role in ctx.author.roles if mod_role else False
    return commands.check(predicate)

logger = get_logger(__name__)

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
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Auteur", value=f"{ctx.author} ({ctx.author.id})", inline=False)
            embed.add_field(name="Nom d'utilisateur", value=f"{ctx.author.name}#{ctx.author.discriminator}", inline=False)
            embed.add_field(name="Commande", value=str(ctx.command), inline=False)
            embed.add_field(name="Salon", value=f"{ctx.channel} ({ctx.channel.id})", inline=False)
            if reason:
                embed.add_field(name="Raison", value=reason, inline=False)
            try:
                await log_channel.send(embed=embed)
            except Exception as e:
                logger.warning(f"Impossible d'envoyer le log de commande: {e}")

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
        banner_url = None
        try:
            # Tente via fetch_user pour obtenir la bannière si absente
            user = await self.bot.fetch_user(member.id)
            if user and user.banner:
                banner_url = user.banner.url
            elif member.banner:
                banner_url = member.banner.url
        except Exception:
            if member.banner:
                banner_url = member.banner.url

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
            return await ctx.send("❌ Vous devez fournir une raison.")

        try:
            overwrite = channel.overwrites_for(ctx.guild.default_role)
            overwrite.view_channel = False
            await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        except discord.Forbidden:
            return await ctx.send("❌ Je n'ai pas la permission de modifier les permissions de ce salon.")
        except Exception as e:
            return await ctx.send(f"❌ Erreur: {e}")

        await ctx.send(f"🔒 Le salon {channel.mention} a été masqué.\nRaison : {reason}")
        await self.log_command(ctx, reason=reason)

    # ---------------- UNHIDE ----------------
    @commands.command(name="unhide")
    @has_moderator_or_admin()
    async def unhide(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        try:
            overwrite = channel.overwrites_for(ctx.guild.default_role)
            overwrite.view_channel = None  # retour à l'héritage
            await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        except discord.Forbidden:
            return await ctx.send("❌ Je n'ai pas la permission de modifier les permissions de ce salon.")
        except Exception as e:
            return await ctx.send(f"❌ Erreur: {e}")
        await ctx.send(f"✅ Le salon {channel.mention} est de nouveau visible.")
        await self.log_command(ctx)

    # ---------------- LOCK ----------------
    @commands.command(name="lock")
    @has_moderator_or_admin()
    async def lock(self, ctx, channel: discord.TextChannel = None, *, reason: str = None):
        channel = channel or ctx.channel
        if not reason:
            return await ctx.send("❌ Vous devez fournir une raison.")

        try:
            overwrite = channel.overwrites_for(ctx.guild.default_role)
            overwrite.send_messages = False
            await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        except discord.Forbidden:
            return await ctx.send("❌ Je n'ai pas la permission de modifier les permissions de ce salon.")
        except Exception as e:
            return await ctx.send(f"❌ Erreur: {e}")

        await ctx.send(f"🔒 Le salon {channel.mention} a été verrouillé.\nRaison : {reason}")
        await self.log_command(ctx, reason=reason)

    # ---------------- UNLOCK ----------------
    @commands.command(name="unlock")
    @has_moderator_or_admin()
    async def unlock(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        try:
            overwrite = channel.overwrites_for(ctx.guild.default_role)
            overwrite.send_messages = None  # retour à l'héritage
            await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite)
        except discord.Forbidden:
            return await ctx.send("❌ Je n'ai pas la permission de modifier les permissions de ce salon.")
        except Exception as e:
            return await ctx.send(f"❌ Erreur: {e}")
        await ctx.send(f"✅ Le salon {channel.mention} est de nouveau déverrouillé.")
        await self.log_command(ctx)

    @commands.command(name="clear", aliases=["supp"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    @has_moderator_or_admin()
    async def supprimer(self, ctx, nombre: int):
        if nombre <= 0:
            return await ctx.send("❌ Le nombre doit être supérieur à 0.")
        try:
            deleted = await ctx.channel.purge(limit=nombre)
            await ctx.send(f"🧹 {len(deleted)} messages supprimés.")
        except discord.Forbidden:
            await ctx.send("❌ Je n'ai pas la permission de supprimer des messages ici.")
        except Exception as e:
            await ctx.send(f"❌ Erreur: {e}")

    # ===== RESET =====
    @commands.command(name="reset", description="Réinitialise et supprime tous les messages d'un salon.")
    @commands.cooldown(1, 30, commands.BucketType.channel)
    @has_moderator_or_admin()
    async def reset(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        if not ctx.author.guild_permissions.manage_messages:
            return await ctx.send("❌ Vous n'avez pas la permission pour cette commande.")
        # Confirmation interactive
        class ConfirmView(discord.ui.View):
            def __init__(self, author: discord.Member):
                super().__init__(timeout=30)
                self.author = author
                self.value = None

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                if interaction.user.id != self.author.id:
                    await interaction.response.send_message("❌ Seul l'auteur peut confirmer.", ephemeral=True)
                    return False
                return True

            @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.danger)
            async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
                self.value = True
                await interaction.response.defer()
                self.stop()

            @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
            async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
                self.value = False
                await interaction.response.defer()
                self.stop()

        view = ConfirmView(ctx.author)
        prompt = await ctx.send("⚠️ Confirmer la réinitialisation de ce salon ?", view=view)
        await view.wait()
        await prompt.edit(view=None)
        if not view.value:
            return await ctx.send("❎ Réinitialisation annulée.")

        try:
            await channel.purge()
            msg = await channel.send("⚠️ Ce salon a été réinitialisé.")
            await msg.delete(delay=5)
        except discord.Forbidden:
            await ctx.send("❌ Je n'ai pas la permission nécessaire pour réinitialiser ce salon.")
        except Exception as e:
            await ctx.send(f"❌ Erreur: {e}")

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
            return await ctx.send(f"❌ Impossible d'envoyer le message : {e}")

        # Sauvegarde persistance
        self.data["messages"][str(sent.id)] = {
            "content": content,
            "channel_id": sent.channel.id,
            "author_id": ctx.author.id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        save_data(self.data)

        # Log
        await self.log_command(ctx, reason=f"+parler vers {sent.channel.mention} | ID: {sent.id}")

    @commands.command(name="modif_say")
    @commands.has_permissions(administrator=True)
    async def modif_say(self, ctx: commands.Context, message_id: int, *, new_content: str):
        """
        Modifier un message envoyé via +parler (admin only)
        """
        record = self.data["messages"].get(str(message_id))
        if not record:
            return await ctx.send("❌ Aucun message trouvé avec cet ID.")

        channel = self.bot.get_channel(record["channel_id"])
        if not channel:
            return await ctx.send("❌ Salon introuvable.")

        try:
            msg = await channel.fetch_message(message_id)
            await msg.edit(content=new_content)
        except discord.NotFound:
            return await ctx.send("❌ Message introuvable (supprimé ?).")
        except discord.Forbidden:
            return await ctx.send("❌ Je n’ai pas la permission de modifier ce message.")

        # Mettre à jour persistance
        self.data["messages"][str(message_id)]["content"] = new_content
        self.data["messages"][str(message_id)]["edited_at"] = datetime.now(timezone.utc).isoformat()
        save_data(self.data)

        await ctx.send(f"✅ Message `{message_id}` modifié avec succès.")

        # Log
        await self.log_command(ctx, reason=f"+modif_say ID {message_id}")

def load_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({"messages": {}}, f, indent=2)
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

async def setup(bot):
    await bot.add_cog(ExtraCommands(bot))