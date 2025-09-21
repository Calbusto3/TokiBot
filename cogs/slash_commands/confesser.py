# cogs/slash_commands/confesser.py
import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from datetime import datetime
import asyncio

CONFESSION_FILE = "confessions.json"
BANS_FILE = "confession_bans.json"

ADMIN_LOG_CHANNEL_ID = 1418956399404122132
COMMAND_LOG_CHANNEL_ID = 1418322935789392110
REPORT_LOG_CHANNEL_ID = 1418956399404122132

# -------------------------
# Utilitaires fichiers JSON
# -------------------------
def ensure_file(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)

def load_confessions():
    ensure_file(CONFESSION_FILE, {"confessions": []})
    with open(CONFESSION_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_confessions(data):
    with open(CONFESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def load_bans():
    ensure_file(BANS_FILE, {"banned": []})
    with open(BANS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_bans(data):
    with open(BANS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def next_conf_id(data):
    if not data["confessions"]:
        return 1
    return data["confessions"][-1]["id"] + 1

def user_conf_count(data, user_id):
    return sum(1 for c in data["confessions"] if c.get("author_id") == user_id)

# -------------------------
# Cog
# -------------------------
class Confessions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ------ helpers ------
    def is_banned(self, user_id: int) -> bool:
        bans = load_bans()
        return user_id in bans.get("banned", [])

    async def log_admin(self, title: str, description: str, author: discord.User = None, extra_fields: dict | None = None, color=discord.Color.blurple()):
        ch = self.bot.get_channel(ADMIN_LOG_CHANNEL_ID)
        if not ch: 
            return
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.utcnow())
        if author:
            embed.set_author(name=str(author), icon_url=getattr(author, "display_avatar", None).url if hasattr(author, "display_avatar") else None)
            embed.add_field(name="Auteur", value=f"{author} ({author.id})", inline=True)
        if extra_fields:
            for n, v in extra_fields.items():
                embed.add_field(name=n, value=v, inline=False)
        try:
            await ch.send(embed=embed)
        except Exception:
            pass

    async def log_command(self, title: str, description: str, moderator: discord.User | None = None, color=discord.Color.blue()):
        ch = self.bot.get_channel(COMMAND_LOG_CHANNEL_ID)
        if not ch:
            return
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.utcnow())
        if moderator:
            embed.add_field(name="Modérateur", value=f"{moderator} ({moderator.id})", inline=True)
        try:
            await ch.send(embed=embed)
        except Exception:
            pass

    async def send_dm_safe(self, user: discord.User, embed: discord.Embed):
        try:
            await user.send(embed=embed)
        except Exception:
            pass

    # -------------------------
    # Persistent dynamic view factory
    # -------------------------
    class DynamicConfessView(discord.ui.View):
        """
        View dynamique : construit des boutons 'Signaler' et 'Répondre' selon reply_enabled.
        Les custom_id sont stables pour persistance : 'confess_report:{id}', 'confess_reply:{id}'
        """
        def __init__(self, cog: "Confessions", confession_id: int, reply_enabled: bool = True):
            super().__init__(timeout=None)
            self.cog = cog
            self.confession_id = confession_id
            self.reply_enabled = reply_enabled

            # Bouton Signaler (toujours présent)
            report_id = f"confess_report:{confession_id}"
            btn_report = discord.ui.Button(style=discord.ButtonStyle.danger, label="Signaler", custom_id=report_id)
            btn_report.callback = self._report_callback
            self.add_item(btn_report)

            # Bouton Répondre (optionnel)
            if reply_enabled:
                reply_id = f"confess_reply:{confession_id}"
                btn_reply = discord.ui.Button(style=discord.ButtonStyle.primary, label="Répondre", custom_id=reply_id)
                btn_reply.callback = self._reply_callback
                self.add_item(btn_reply)

        async def _report_callback(self, interaction: discord.Interaction):
            # check ban
            if self.cog.is_banned(interaction.user.id):
                return await interaction.response.send_message("🚫 Tu es banni du système de confessions.", ephemeral=True)
            # open Report modal
            await interaction.response.send_modal(self.cog.ReportModal(self.cog, self.confession_id, interaction.user))

        async def _reply_callback(self, interaction: discord.Interaction):
            if self.cog.is_banned(interaction.user.id):
                return await interaction.response.send_message("🚫 Tu es banni du système de confessions.", ephemeral=True)
            # open Reply modal
            await interaction.response.send_modal(self.cog.ReplyModal(self.cog, self.confession_id, interaction.user))

    # -------------------------
    # Modal: Confess (slash)
    # -------------------------
    class ConfessModal(discord.ui.Modal, title="Confession Anonyme"):
        confession = discord.ui.TextInput(label="Ta confession", style=discord.TextStyle.long, required=True, max_length=2000)

        def __init__(self, cog: "Confessions", author: discord.User):
            super().__init__()
            self.cog = cog
            self.author = author

        async def on_submit(self, interaction: discord.Interaction):
            # immediate ack to avoid "Unknown interaction"
            await interaction.response.send_message("✅ Confession reçue, publication en cours...", ephemeral=True)

            if self.cog.is_banned(self.author.id):
                # Inform again with followup (ephemeral already sent) — we can also ignore
                await interaction.followup.send("🚫 Tu es banni du système de confessions.", ephemeral=True)
                return

            # Save confession
            data = load_confessions()
            cid = next_conf_id(data)
            now = datetime.utcnow().isoformat()
            conf_obj = {
                "id": cid,
                "author_id": self.author.id,
                "author_tag": str(self.author),
                "text": self.confession.value,
                "responses": [],    # list of response IDs
                "timestamp": now,
                "message_id": None,
                "reply_to": None
            }
            data["confessions"].append(conf_obj)
            save_confessions(data)

            # Determine reply_enabled based on channel type
            channel = interaction.channel
            reply_enabled = not isinstance(channel, discord.Thread)

            # Build embed
            embed = discord.Embed(title=f"Confession #{cid}", description=self.confession.value,
                                  color=discord.Color.purple(), timestamp=datetime.utcnow())
            embed.set_footer(text="message anonyme.")

            # send public message
            try:
                view = self.cog.DynamicConfessView(self.cog, cid, reply_enabled=reply_enabled)
                public_msg = await channel.send(embed=embed, view=view)
                # persist message_id in confession
                conf_obj["message_id"] = public_msg.id
                save_confessions(data)
            except Exception:
                # if sending fails, log and exit gracefully
                await interaction.followup.send("❌ Erreur lors de la publication publique.", ephemeral=True)
                return

            # admin log
            await self.cog.log_admin(f"Confession #{cid} (log admin)", self.confession.value, author=self.author,
                                     extra_fields={"Timestamp": now}, color=discord.Color.dark_red())

            # DM confirmation (non-blocking)
            total = user_conf_count(data, self.author.id)
            dm_embed = discord.Embed(title="Confession enregistrée !",
                                     description=f"Tu as envoyé {total} confession(s).",
                                     color=discord.Color.green())
            asyncio.create_task(self.cog.send_dm_safe(self.author, dm_embed))

    # -------------------------
    # Modal: Report
    # -------------------------
    class ReportModal(discord.ui.Modal, title="Signaler une confession"):
        reason = discord.ui.TextInput(label="Raison (optionnel)", style=discord.TextStyle.short, required=False, max_length=500)

        def __init__(self, cog: "Confessions", confession_id: int, reporter: discord.User):
            super().__init__()
            self.cog = cog
            self.confession_id = confession_id
            self.reporter = reporter

        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.send_message("✅ Signalement reçu, merci.", ephemeral=True)

            # fetch confession text
            data = load_confessions()
            confession = next((c for c in data["confessions"] if c["id"] == self.confession_id), None)
            if not confession:
                await interaction.followup.send("Confession introuvable.", ephemeral=True)
                return

            # admin report log (red)
            embed = discord.Embed(title=f"🚨 Signalement Confession #{self.confession_id}",
                                  description=f"**Raison:** {self.reason.value or 'Aucune'}",
                                  color=discord.Color.red(), timestamp=datetime.utcnow())
            embed.add_field(name="Signalée par", value=f"{self.reporter} ({self.reporter.id})", inline=False)
            embed.add_field(name="Texte original", value=confession["text"], inline=False)
            ch = self.cog.bot.get_channel(REPORT_LOG_CHANNEL_ID)
            if ch:
                try:
                    await ch.send(embed=embed)
                except Exception:
                    pass

    # -------------------------
    # Modal: Reply (counts as a confession)
    # -------------------------
    class ReplyModal(discord.ui.Modal, title="Répondre à la confession"):
        response = discord.ui.TextInput(label="Ta réponse", style=discord.TextStyle.long, required=True, max_length=2000)

        def __init__(self, cog: "Confessions", confession_id: int, replier: discord.User):
            super().__init__()
            self.cog = cog
            self.confession_id = confession_id
            self.replier = replier

        async def on_submit(self, interaction: discord.Interaction):
            # ack quickly
            await interaction.response.send_message("✅ Réponse reçue, publication en cours...", ephemeral=True)

            if self.cog.is_banned(self.replier.id):
                await interaction.followup.send("🚫 Tu es banni du système de confessions.", ephemeral=True)
                return

            data = load_confessions()
            parent = next((c for c in data["confessions"] if c["id"] == self.confession_id), None)
            if not parent:
                await interaction.followup.send("Confession introuvable.", ephemeral=True)
                return

            # create new confession entry for the response
            new_id = next_conf_id(data)
            now = datetime.utcnow().isoformat()
            resp_obj = {
                "id": new_id,
                "author_id": self.replier.id,
                "author_tag": str(self.replier),
                "text": self.response.value,
                "responses": [],
                "timestamp": now,
                "message_id": None,
                "reply_to": self.confession_id
            }
            data["confessions"].append(resp_obj)
            # link in parent
            parent.setdefault("responses", []).append(new_id)
            save_confessions(data)

            # Build embed for response (title shows it's a response)
            embed = discord.Embed(title=f"Confession #{new_id} (réponse à #{self.confession_id})",
                                  description=self.response.value,
                                  color=discord.Color.gold(), timestamp=datetime.utcnow())
            embed.set_footer(text="message anonyme.")

            channel = interaction.channel

            # If in a thread -> just send the embed in the thread, only Signaler button
            if isinstance(channel, discord.Thread):
                view = self.cog.DynamicConfessView(self.cog, new_id, reply_enabled=False)
                try:
                    msg = await channel.send(embed=embed, view=view)
                    resp_obj["message_id"] = msg.id
                    save_confessions(data)
                except Exception:
                    await interaction.followup.send("❌ Erreur lors de la publication dans le fil.", ephemeral=True)
                    return

                # admin log & DM original author
                await self.cog.log_admin(f"Réponse #{new_id} (log admin)", self.response.value, author=self.replier,
                                         extra_fields={"Réponse à": str(self.confession_id), "Timestamp": now},
                                         color=discord.Color.teal())
                # notify original author by DM if possible
                try:
                    orig_user = await self.cog.bot.fetch_user(parent["author_id"])
                    link = None
                    try:
                        link = f"https://discord.com/channels/{channel.guild.id}/{channel.id}"
                    except Exception:
                        pass
                    dm_embed = discord.Embed(title="Tu as reçu une réponse !",
                                             description=f"Ta confession #{self.confession_id} a reçu une réponse.\n{('Voir le fil: ' + link) if link else ''}",
                                             color=discord.Color.orange())
                    await self.cog.send_dm_safe(orig_user, dm_embed)
                except Exception:
                    pass

            else:
                # not in a thread: find parent message by parent['message_id'] and create a thread
                parent_msg_id = parent.get("message_id")
                if not parent_msg_id:
                    await interaction.followup.send("Impossible de retrouver le message original pour créer le fil.", ephemeral=True)
                    return

                try:
                    pub_channel = channel
                    parent_msg = await pub_channel.fetch_message(parent_msg_id)
                except Exception:
                    await interaction.followup.send("Impossible de récupérer le message original.", ephemeral=True)
                    return

                # create thread from parent_msg and post response there
                try:
                    thread = await parent_msg.create_thread(name=f"Réponses Confession #{self.confession_id}", auto_archive_duration=60)
                    view = self.cog.DynamicConfessView(self.cog, new_id, reply_enabled=False)
                    thread_msg = await thread.send(embed=embed, view=view)
                    resp_obj["message_id"] = thread_msg.id
                    save_confessions(data)

                    # remove buttons from original parent message (so no more replies there)
                    try:
                        await parent_msg.edit(view=None)
                    except Exception:
                        pass

                    # admin log
                    await self.cog.log_admin(f"Réponse #{new_id} (log admin)", self.response.value, author=self.replier,
                                             extra_fields={"Réponse à": str(self.confession_id), "Thread": str(thread.id), "Timestamp": now},
                                             color=discord.Color.teal())

                    # DM original author with link to thread
                    try:
                        orig_user = await self.cog.bot.fetch_user(parent["author_id"])
                        link = f"https://discord.com/channels/{parent_msg.guild.id}/{thread.id}"
                        dm_embed = discord.Embed(title="Tu as reçu une réponse !",
                                                 description=f"Ta confession #{self.confession_id} a reçu une réponse.\n[Voir le fil]({link})",
                                                 color=discord.Color.orange())
                        await self.cog.send_dm_safe(orig_user, dm_embed)
                    except Exception:
                        pass

                except Exception:
                    await interaction.followup.send("❌ Erreur lors de la création du fil.", ephemeral=True)
                    return

            # DM to replier (confirmation)
            dm_embed = discord.Embed(title="✅ Réponse publiée", description=f"Ta réponse a été envoyé !.", color=discord.Color.green())
            await self.cog.send_dm_safe(self.replier, dm_embed)

    # -------------------------
    # Slash command: /confesser
    # -------------------------
    @app_commands.command(name="confesser", description="Envoyer une confession anonyme")
    async def confesser(self, interaction: discord.Interaction):
        # quick ban check
        if self.is_banned(interaction.user.id):
            return await interaction.response.send_message("🚫 Tu es banni du système de confessions.", ephemeral=True)
        await interaction.response.send_modal(self.ConfessModal(self, interaction.user))

    # -------------------------
    # Prefix commands: ban / unban / list
    # -------------------------
    @commands.command(name="banconfession")
    async def banconfession(self, ctx, member: discord.Member):
        bans = load_bans()
        if member.id in bans.get("banned", []):
            return await ctx.send(f"⚠️ {member.mention} est déjà banni.")
        bans.setdefault("banned", []).append(member.id)
        save_bans(bans)

        dm = discord.Embed(title="🚫 Bannissement Confession", description="Tu as été banni du système de confessions.", color=discord.Color.red())
        asyncio.create_task(self.send_dm_safe(member, dm))

        await ctx.send(f"✅ {member.mention} banni du système de confessions.")
        await self.log_command("Ban Confession", f"{ctx.author} a banni {member} ({member.id})", moderator=ctx.author, color=discord.Color.orange())

    @commands.command(name="unbanconfession")
    async def unbanconfession(self, ctx, member: discord.Member):
        bans = load_bans()
        if member.id not in bans.get("banned", []):
            return await ctx.send(f"⚠️ {member.mention} n'était pas banni.")
        bans["banned"].remove(member.id)
        save_bans(bans)

        dm = discord.Embed(title="✅ Débannissement Confession", description="Tu peux de nouveau utiliser le système de confessions.", color=discord.Color.green())
        asyncio.create_task(self.send_dm_safe(member, dm))

        await ctx.send(f"✅ {member.mention} débanni du système de confessions.")
        await self.log_command("Unban Confession", f"{ctx.author} a débanni {member} ({member.id})", moderator=ctx.author, color=discord.Color.green())

    @commands.command(name="listbanconfession")
    async def listbanconfession(self, ctx):
        bans = load_bans()
        banned = bans.get("banned", [])
        if not banned:
            return await ctx.send("Aucun utilisateur banni du système de confessions.")
        lines = []
        for uid in banned:
            try:
                u = await self.bot.fetch_user(uid)
                lines.append(f"{u} ({uid})")
            except Exception:
                lines.append(str(uid))
        # send as paged message if too long, but basic send OK
        await ctx.send("Utilisateurs bannis :\n" + "\n".join(lines))

    # -------------------------
    # on_ready: re-register dynamic persistent views for every confession message
    # -------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        # rebuild views for each confession that has a message_id and is not inside a thread by itself.
        data = load_confessions()
        count = 0
        for conf in data.get("confessions", []):
            msg_id = conf.get("message_id")
            if not msg_id:
                continue
            # Determine whether reply button should be enabled by checking the channel where message is located:
            # we need to fetch message; try to find it across guilds where bot is
            found = False
            for guild in self.bot.guilds:
                try:
                    # try to fetch from likely channels by searching recent channels
                    # Note: this is best-effort (we don't store channel_id originally in this simplified file),
                    # but when using the standard flow message was posted into the interaction.channel we can record channel id if desired.
                    # To be robust we'll try to search channels in the guild for that message_id.
                    for channel in guild.text_channels + [t for t in guild.threads]:
                        try:
                            msg = await channel.fetch_message(msg_id)
                            # If message found:
                            # reply_enabled should be False if the message is inside a Thread
                            reply_enabled = not isinstance(channel, discord.Thread)
                            view = self.DynamicConfessView(self, conf["id"], reply_enabled=reply_enabled)
                            self.bot.add_view(view)   # register persistent view
                            found = True
                            count += 1
                            break
                        except Exception:
                            continue
                    if found:
                        break
                except Exception:
                    continue
        # print summary
        print(f"[Confessions] Views rechargées : {count}")

async def setup(bot):
    await bot.add_cog(Confessions(bot))