# cogs/slash_commands/confesser.py
import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from datetime import datetime, timezone
from utils.datetime_utils import format_iso_str
from utils.config import get_bot_config
import asyncio
import logging
import threading
from typing import Optional, Dict, Any, Tuple
import time

CONFESSION_FILE = "confessions.json"
BANS_FILE = "confession_bans.json"
CONFIG_FILE = "confession_config.json"

# Centralized configuration
_BOT_CFG = get_bot_config()
ADMIN_LOG_CHANNEL_ID = _BOT_CFG.get("ADMIN_LOG_CHANNEL_ID")
COMMAND_LOG_CHANNEL_ID = _BOT_CFG.get("COMMAND_LOG_CHANNEL_ID")
REPORT_LOG_CHANNEL_ID = _BOT_CFG.get("REPORT_LOG_CHANNEL_ID")

# Rate limiting: max confessions per user per hour
RATE_LIMIT_CONFESSIONS = 5
RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds

# File locks for thread safety
_file_locks = {
    CONFESSION_FILE: threading.Lock(),
    BANS_FILE: threading.Lock(),
    CONFIG_FILE: threading.Lock()
}

# Setup logging
logger = logging.getLogger(__name__)

# -------------------------
# Utilitaires fichiers JSON avec verrouillage
# -------------------------
def ensure_file(path: str, default: Dict[str, Any]) -> None:
    """Assure qu'un fichier existe avec des données par défaut."""
    if not os.path.exists(path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erreur lors de la création du fichier {path}: {e}")
            raise

def load_json_safe(filepath: str, default: Dict[str, Any]) -> Dict[str, Any]:
    """Charge un fichier JSON de manière sécurisée avec verrouillage."""
    lock = _file_locks.get(filepath)
    if not lock:
        logger.warning(f"Aucun verrou trouvé pour {filepath}")
        lock = threading.Lock()
    
    with lock:
        try:
            ensure_file(filepath, default)
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Validation basique de la structure
                if not isinstance(data, dict):
                    logger.warning(f"Structure invalide dans {filepath}, utilisation des valeurs par défaut")
                    return default.copy()
                return data
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f"Erreur lors du chargement de {filepath}: {e}")
            return default.copy()
        except Exception as e:
            logger.error(f"Erreur inattendue lors du chargement de {filepath}: {e}")
            return default.copy()

def save_json_safe(filepath: str, data: Dict[str, Any]) -> bool:
    """Sauvegarde un fichier JSON de manière sécurisée avec verrouillage."""
    lock = _file_locks.get(filepath)
    if not lock:
        logger.warning(f"Aucun verrou trouvé pour {filepath}")
        lock = threading.Lock()
    
    with lock:
        try:
            # Sauvegarde temporaire pour éviter la corruption
            temp_file = f"{filepath}.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Remplace le fichier original seulement si la sauvegarde temporaire réussit
            os.replace(temp_file, filepath)
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde de {filepath}: {e}")
            # Nettoie le fichier temporaire en cas d'erreur
            try:
                if os.path.exists(f"{filepath}.tmp"):
                    os.remove(f"{filepath}.tmp")
            except Exception:
                pass
            return False

def load_confessions() -> Dict[str, Any]:
    """Charge les confessions avec gestion d'erreurs."""
    return load_json_safe(CONFESSION_FILE, {"confessions": [], "message_channels": {}})

def save_confessions(data: Dict[str, Any]) -> bool:
    """Sauvegarde les confessions avec gestion d'erreurs."""
    return save_json_safe(CONFESSION_FILE, data)

def load_bans() -> Dict[str, Any]:
    """Charge les bannissements avec gestion d'erreurs."""
    return load_json_safe(BANS_FILE, {"banned": []})

def save_bans(data: Dict[str, Any]) -> bool:
    """Sauvegarde les bannissements avec gestion d'erreurs."""
    return save_json_safe(BANS_FILE, data)

def load_config() -> Dict[str, Any]:
    """Charge la configuration avec gestion d'erreurs."""
    return load_json_safe(CONFIG_FILE, {"rate_limits": {}})

def save_config(data: Dict[str, Any]) -> bool:
    """Sauvegarde la configuration avec gestion d'erreurs."""
    return save_json_safe(CONFIG_FILE, data)

def next_conf_id(data: Dict[str, Any]) -> int:
    """Génère le prochain ID de confession."""
    confessions = data.get("confessions", [])
    if not confessions:
        return 1
    return max(c.get("id", 0) for c in confessions) + 1

def user_conf_count(data: Dict[str, Any], user_id: int) -> int:
    """Compte le nombre de confessions d'un utilisateur."""
    return sum(1 for c in data.get("confessions", []) if c.get("author_id") == user_id)

def validate_confession_text(text: str) -> Tuple[bool, str]:
    """Valide le texte d'une confession."""
    if not text or not text.strip():
        return False, "Le texte de la confession ne peut pas être vide."
    
    if len(text.strip()) < 10:
        return False, "La confession doit contenir au moins 10 caractères."
    
    if len(text) > 2000:
        return False, "La confession ne peut pas dépasser 2000 caractères."
    
    # Vérification de contenu inapproprié basique
    forbidden_patterns = ['@everyone', '@here']
    text_lower = text.lower()
    for pattern in forbidden_patterns:
        if pattern in text_lower:
            return False, f"Le texte contient un élément interdit: {pattern}"
    
    return True, "Valide"

def check_rate_limit(user_id: int, increment: bool = True) -> Tuple[bool, int]:
    """Vérifie si l'utilisateur respecte la limite de taux.
    Si increment=False, ne consomme pas de quota (mode aperçu).
    Retourne (autorisé, secondes_restant_avant_reset).
    """
    config = load_config()
    rate_limits = config.get("rate_limits", {})
    user_key = str(user_id)
    
    current_time = int(time.time())
    
    if user_key not in rate_limits:
        rate_limits[user_key] = {"count": 0, "reset_time": current_time + RATE_LIMIT_WINDOW}
    
    user_limit = rate_limits[user_key]
    
    # Réinitialise si la fenêtre de temps est écoulée
    if current_time >= user_limit["reset_time"]:
        user_limit["count"] = 0
        user_limit["reset_time"] = current_time + RATE_LIMIT_WINDOW
    
    # Vérifie la limite
    if user_limit["count"] >= RATE_LIMIT_CONFESSIONS:
        time_left = user_limit["reset_time"] - current_time
        return False, time_left
    
    # Incrémente le compteur uniquement si demandé
    if increment:
        user_limit["count"] += 1
        config["rate_limits"] = rate_limits
        save_config(config)
    
    return True, 0

# -------------------------
# Cog
# -------------------------
class Confessions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ------ helpers ------
    def is_banned(self, user_id: int) -> bool:
        """Vérifie si un utilisateur est banni."""
        try:
            bans = load_bans()
            return user_id in bans.get("banned", [])
        except Exception as e:
            logger.error(f"Erreur lors de la vérification du ban pour {user_id}: {e}")
            return False
    
    def has_admin_permissions(self, user: discord.User, guild: discord.Guild) -> bool:
        """Vérifie si l'utilisateur a les permissions d'administration."""
        try:
            member = guild.get_member(user.id)
            if not member:
                return False
            return member.guild_permissions.manage_messages or member.guild_permissions.administrator
        except Exception as e:
            logger.error(f"Erreur lors de la vérification des permissions pour {user.id}: {e}")
            return False

    async def log_admin(self, title: str, description: str, author: discord.User = None, extra_fields: Optional[Dict[str, str]] = None, color=discord.Color.blurple()) -> bool:
        """Log administrateur avec gestion d'erreurs améliorée."""
        try:
            ch = self.bot.get_channel(ADMIN_LOG_CHANNEL_ID)
            if not ch:
                logger.warning(f"Canal admin log introuvable: {ADMIN_LOG_CHANNEL_ID}")
                return False
            
            # Utilise la nouvelle méthode datetime
            embed = discord.Embed(title=title[:256], description=description[:4096], color=color, timestamp=datetime.now(timezone.utc))
            
            if author:
                try:
                    avatar_url = author.display_avatar.url if hasattr(author, 'display_avatar') else None
                    embed.set_author(name=str(author)[:256], icon_url=avatar_url)
                    embed.add_field(name="Auteur", value=f"{author} ({author.id})", inline=True)
                except Exception as e:
                    logger.warning(f"Erreur lors de l'ajout de l'auteur au log: {e}")
            
            if extra_fields:
                for name, value in extra_fields.items():
                    try:
                        embed.add_field(name=str(name)[:256], value=str(value)[:1024], inline=False)
                    except Exception as e:
                        logger.warning(f"Erreur lors de l'ajout du champ {name}: {e}")
            
            await ch.send(embed=embed)
            return True
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors du log admin: {e}")
            return False
        except Exception as e:
            logger.error(f"Erreur inattendue lors du log admin: {e}")
            return False

    async def log_command(self, title: str, description: str, moderator: Optional[discord.User] = None, color=discord.Color.blue()) -> bool:
        """Log de commande avec gestion d'erreurs améliorée."""
        try:
            ch = self.bot.get_channel(COMMAND_LOG_CHANNEL_ID)
            if not ch:
                logger.warning(f"Canal command log introuvable: {COMMAND_LOG_CHANNEL_ID}")
                return False
            
            embed = discord.Embed(title=title[:256], description=description[:4096], color=color, timestamp=datetime.now(timezone.utc))
            
            if moderator:
                try:
                    embed.add_field(name="Modérateur", value=f"{moderator} ({moderator.id})", inline=True)
                except Exception as e:
                    logger.warning(f"Erreur lors de l'ajout du modérateur au log: {e}")
            
            await ch.send(embed=embed)
            return True
        except discord.HTTPException as e:
            logger.error(f"Erreur HTTP lors du log de commande: {e}")
            return False
        except Exception as e:
            logger.error(f"Erreur inattendue lors du log de commande: {e}")
            return False

    async def send_dm_safe(self, user: discord.User, embed: discord.Embed) -> bool:
        """Envoie un DM de manière sécurisée avec gestion d'erreurs."""
        try:
            await user.send(embed=embed)
            return True
        except discord.Forbidden:
            logger.info(f"Impossible d'envoyer un DM à {user.id} (DMs fermés)")
            return False
        except discord.HTTPException as e:
            logger.warning(f"Erreur HTTP lors de l'envoi DM à {user.id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Erreur inattendue lors de l'envoi DM à {user.id}: {e}")
            return False

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
            """Traite la soumission d'une confession avec validations complètes."""
            # Accusé de réception immédiat
            await interaction.response.send_message("✅ Confession reçue, vérification en cours...", ephemeral=True)

            try:
                # Vérifications préliminaires
                if self.cog.is_banned(self.author.id):
                    await interaction.followup.send("🚫 Tu es banni du système de confessions.", ephemeral=True)
                    return

                # Validation du texte
                is_valid, error_msg = validate_confession_text(self.confession.value)
                if not is_valid:
                    await interaction.followup.send(f"❌ {error_msg}", ephemeral=True)
                    return

                # Vérification du rate limiting
                can_post, time_left = check_rate_limit(self.author.id)
                if not can_post:
                    minutes_left = max(1, time_left // 60)
                    await interaction.followup.send(
                        f"⏰ Tu as atteint la limite de {RATE_LIMIT_CONFESSIONS} confessions par heure. "
                        f"Réessaie dans {minutes_left} minute(s).", ephemeral=True
                    )
                    return

                # Chargement et sauvegarde des données
                data = load_confessions()
                cid = next_conf_id(data)
                now = datetime.now(timezone.utc).isoformat()
                
                # Stockage du channel_id pour optimiser le rechargement des vues
                channel_id = interaction.channel.id if interaction.channel else None
                
                conf_obj = {
                    "id": cid,
                    "author_id": self.author.id,
                    "author_tag": str(self.author),
                    "text": self.confession.value.strip(),
                    "responses": [],
                    "timestamp": now,
                    "message_id": None,
                    "channel_id": channel_id,
                    "reply_to": None
                }
                
                data["confessions"].append(conf_obj)
                
                # Sauvegarde avec vérification d'erreur
                if not save_confessions(data):
                    await interaction.followup.send("❌ Erreur lors de la sauvegarde. Réessaie plus tard.", ephemeral=True)
                    return

                # Détermination du type de canal
                channel = interaction.channel
                if not channel:
                    await interaction.followup.send("❌ Impossible de déterminer le canal de destination.", ephemeral=True)
                    return
                
                reply_enabled = not isinstance(channel, discord.Thread)

                # Construction de l'embed
                embed = discord.Embed(
                    title=f"Confession #{cid}", 
                    description=self.confession.value,
                    color=discord.Color.purple(), 
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_footer(text="Message anonyme • Système de confessions")

                # Publication du message
                try:
                    view = self.cog.DynamicConfessView(self.cog, cid, reply_enabled=reply_enabled)
                    public_msg = await channel.send(embed=embed, view=view)
                    
                    # Mise à jour avec l'ID du message
                    conf_obj["message_id"] = public_msg.id
                    if not save_confessions(data):
                        logger.warning(f"Impossible de sauvegarder l'ID du message pour la confession {cid}")
                        
                except discord.Forbidden:
                    await interaction.followup.send("❌ Je n'ai pas les permissions pour envoyer des messages dans ce canal.", ephemeral=True)
                    return
                except discord.HTTPException as e:
                    logger.error(f"Erreur HTTP lors de l'envoi de la confession {cid}: {e}")
                    await interaction.followup.send("❌ Erreur lors de la publication. Réessaie plus tard.", ephemeral=True)
                    return
                except Exception as e:
                    logger.error(f"Erreur inattendue lors de l'envoi de la confession {cid}: {e}")
                    await interaction.followup.send("❌ Erreur inattendue lors de la publication.", ephemeral=True)
                    return

                # Mise à jour du message de confirmation
                await interaction.edit_original_response(content="✅ Confession publiée avec succès !")

                # Log administrateur
                await self.cog.log_admin(
                    f"Confession #{cid}", 
                    self.confession.value[:1000] + ("..." if len(self.confession.value) > 1000 else ""),
                    author=self.author,
                    extra_fields={
                        "Canal": f"{channel.name} ({channel.id})" if hasattr(channel, 'name') else str(channel.id),
                        "Date": format_iso_str(now)
                    }, 
                    color=discord.Color.dark_red()
                )

                # Confirmation par DM (non-bloquant)
                total = user_conf_count(data, self.author.id)
                dm_embed = discord.Embed(
                    title="✅ Confession publiée !",
                    description=f"Ta confession #{cid} a été publiée.\nTu as maintenant {total} confession(s) au total.",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc)
                )
                asyncio.create_task(self.cog.send_dm_safe(self.author, dm_embed))
                
            except Exception as e:
                logger.error(f"Erreur critique dans ConfessModal.on_submit: {e}")
                try:
                    await interaction.followup.send("❌ Une erreur critique s'est produite. Contacte un administrateur.", ephemeral=True)
                except Exception:
                    pass

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
            """Traite un signalement de confession."""
            await interaction.response.send_message("✅ Signalement reçu, traitement en cours...", ephemeral=True)

            try:
                # Vérification du ban
                if self.cog.is_banned(self.reporter.id):
                    await interaction.followup.send("🚫 Tu es banni du système de confessions.", ephemeral=True)
                    return

                # Validation de la raison (optionnelle mais si fournie, doit être valide)
                reason = self.reason.value.strip() if self.reason.value else "Aucune raison spécifiée"
                if len(reason) > 500:
                    await interaction.followup.send("❌ La raison du signalement est trop longue (max 500 caractères).", ephemeral=True)
                    return

                # Récupération de la confession
                data = load_confessions()
                confession = next((c for c in data.get("confessions", []) if c.get("id") == self.confession_id), None)
                if not confession:
                    await interaction.followup.send("❌ Confession introuvable.", ephemeral=True)
                    return

                # Mise à jour du message de confirmation
                await interaction.edit_original_response(content="✅ Signalement enregistré avec succès !")

                # Log de signalement pour les administrateurs
                report_embed = discord.Embed(
                    title=f"🚨 Signalement - Confession #{self.confession_id}",
                    description=f"**Raison:** {reason}",
                    color=discord.Color.red(), 
                    timestamp=datetime.now(timezone.utc)
                )
                
                report_embed.add_field(
                    name="Signalé par", 
                    value=f"{self.reporter} ({self.reporter.id})", 
                    inline=False
                )
                
                # Tronque le texte si trop long
                confession_text = confession["text"]
                if len(confession_text) > 1000:
                    confession_text = confession_text[:1000] + "..."
                
                report_embed.add_field(
                    name="Texte de la confession", 
                    value=confession_text, 
                    inline=False
                )
                
                report_embed.add_field(
                    name="Auteur original", 
                    value=f"ID: {confession.get('author_id', 'Inconnu')}", 
                    inline=True
                )
                
                report_embed.add_field(
                    name="Date de création", 
                    value=confession.get('timestamp', 'Inconnue'), 
                    inline=True
                )

                # Envoi du log de signalement
                ch = self.cog.bot.get_channel(REPORT_LOG_CHANNEL_ID)
                if ch:
                    try:
                        await ch.send(embed=report_embed)
                    except discord.HTTPException as e:
                        logger.error(f"Erreur lors de l'envoi du log de signalement: {e}")
                    except Exception as e:
                        logger.error(f"Erreur inattendue lors du log de signalement: {e}")
                else:
                    logger.warning(f"Canal de signalement introuvable: {REPORT_LOG_CHANNEL_ID}")
                    
            except Exception as e:
                logger.error(f"Erreur critique dans ReportModal.on_submit: {e}")
                try:
                    await interaction.followup.send("❌ Erreur lors du traitement du signalement.", ephemeral=True)
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
            """Traite une réponse à une confession avec validations complètes."""
            await interaction.response.send_message("✅ Réponse reçue, vérification en cours...", ephemeral=True)

            try:
                # Vérifications préliminaires
                if self.cog.is_banned(self.replier.id):
                    await interaction.followup.send("🚫 Tu es banni du système de confessions.", ephemeral=True)
                    return

                # Validation du texte de la réponse
                is_valid, error_msg = validate_confession_text(self.response.value)
                if not is_valid:
                    await interaction.followup.send(f"❌ {error_msg}", ephemeral=True)
                    return

                # Vérification du rate limiting
                can_post, time_left = check_rate_limit(self.replier.id)
                if not can_post:
                    minutes_left = max(1, time_left // 60)
                    await interaction.followup.send(
                        f"⏰ Tu as atteint la limite de {RATE_LIMIT_CONFESSIONS} confessions par heure. "
                        f"Réessaie dans {minutes_left} minute(s).", ephemeral=True
                    )
                    return

                # Chargement des données
                data = load_confessions()
                parent = next((c for c in data.get("confessions", []) if c.get("id") == self.confession_id), None)
                if not parent:
                    await interaction.followup.send("❌ Confession introuvable.", ephemeral=True)
                    return

                # Création de la nouvelle entrée de réponse
                new_id = next_conf_id(data)
                now = datetime.now(timezone.utc).isoformat()
                channel_id = interaction.channel.id if interaction.channel else None
                resp_obj = {
                    "id": new_id,
                    "author_id": self.replier.id,
                    "author_tag": str(self.replier),
                    "text": self.response.value.strip(),
                    "responses": [],
                    "timestamp": now,
                    "message_id": None,
                    "channel_id": channel_id,
                    "reply_to": self.confession_id
                }
                data["confessions"].append(resp_obj)
                # Lien dans le parent
                parent.setdefault("responses", []).append(new_id)
                
                # Sauvegarde avec vérification d'erreur
                if not save_confessions(data):
                    await interaction.followup.send("❌ Erreur lors de la sauvegarde. Réessaie plus tard.", ephemeral=True)
                    return

                # Construction de l'embed pour la réponse
                embed = discord.Embed(
                    title=f"Confession #{new_id} (réponse à #{self.confession_id})",
                    description=self.response.value,
                    color=discord.Color.gold(), 
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_footer(text="Message anonyme • Réponse à une confession")

                channel = interaction.channel

                # Si dans un thread -> envoie simplement l'embed dans le thread, bouton Signaler seulement
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
                    await self.cog.log_admin(
                        f"Réponse #{new_id} (log admin)",
                        self.response.value,
                        author=self.replier,
                        extra_fields={"Réponse à": str(self.confession_id), "Date": format_iso_str(now)},
                        color=discord.Color.teal()
                    )
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
                    try:
                        # not in a thread: find parent message by parent['message_id'] and create a thread
                        parent_msg_id = parent.get("message_id")
                        if not parent_msg_id:
                            await interaction.followup.send("Impossible de retrouver le message original pour créer le fil.", ephemeral=True)
                            return

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
                        await self.cog.log_admin(
                            f"Réponse #{new_id} (log admin)",
                            self.response.value,
                            author=self.replier,
                            extra_fields={"Réponse à": str(self.confession_id), "Thread": str(thread.id), "Date": format_iso_str(now)},
                            color=discord.Color.teal()
                        )

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

                    # Mise à jour du message de confirmation
                    await interaction.edit_original_response(content="✅ Réponse publiée avec succès !")

                    # Confirmation par DM au répondeur
                    dm_embed = discord.Embed(
                        title="✅ Réponse publiée !",
                        description=f"Ta réponse à la confession #{self.confession_id} a été publiée.",
                        color=discord.Color.green(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    asyncio.create_task(self.cog.send_dm_safe(self.replier, dm_embed))
                
            except Exception as e:
                logger.error(f"Erreur critique dans ReplyModal.on_submit: {e}")
                try:
                    await interaction.followup.send("❌ Une erreur critique s'est produite. Contacte un administrateur.", ephemeral=True)
                except Exception:
                    pass

    # -------------------------
    # Slash command: /confesser
    # -------------------------
    @app_commands.command(name="confesser", description="Envoyer une confession anonyme")
    async def confesser(self, interaction: discord.Interaction):
        """Commande slash pour envoyer une confession anonyme."""
        try:
            # Vérification du bannissement
            if self.is_banned(interaction.user.id):
                embed = discord.Embed(
                    title="🚫 Accès refusé",
                    description="Tu es banni du système de confessions.",
                    color=discord.Color.red()
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Vérification du rate limiting avant d'ouvrir le modal (sans consommer de quota)
            can_post, time_left = check_rate_limit(interaction.user.id, increment=False)
            if not can_post:
                minutes_left = max(1, time_left // 60)
                embed = discord.Embed(
                    title="⏰ Limite atteinte",
                    description=f"Tu as atteint la limite de {RATE_LIMIT_CONFESSIONS} confessions par heure.\nRéessaie dans {minutes_left} minute(s).",
                    color=discord.Color.orange()
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Ouverture du modal
            await interaction.response.send_modal(self.ConfessModal(self, interaction.user))
            
        except Exception as e:
            logger.error(f"Erreur dans la commande confesser pour {interaction.user.id}: {e}")
            try:
                if interaction.response.is_done():
                    await interaction.followup.send("❌ Une erreur s'est produite. Réessaie plus tard.", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ Une erreur s'est produite. Réessaie plus tard.", ephemeral=True)
            except Exception:
                pass

    # -------------------------
    # Prefix commands: ban / unban / list
    # -------------------------
    @commands.command(name="banconfession")
    async def banconfession(self, ctx, member: discord.Member):
        """Bannit un utilisateur du système de confessions."""
        # Vérification des permissions
        if not self.has_admin_permissions(ctx.author, ctx.guild):
            return await ctx.send("❌ Tu n'as pas les permissions nécessaires pour utiliser cette commande.")
        
        # Vérification que l'utilisateur n'essaie pas de se bannir
        if member.id == ctx.author.id:
            return await ctx.send("❌ Tu ne peux pas te bannir toi-même.")
        
        # Vérification que la cible n'est pas un administrateur
        if self.has_admin_permissions(member, ctx.guild):
            return await ctx.send("❌ Tu ne peux pas bannir un administrateur.")
        
        try:
            bans = load_bans()
            if member.id in bans.get("banned", []):
                return await ctx.send(f"⚠️ {member.mention} est déjà banni du système de confessions.")
            
            bans.setdefault("banned", []).append(member.id)
            if not save_bans(bans):
                return await ctx.send("❌ Erreur lors de la sauvegarde du bannissement.")

            # Notification par DM
            dm_embed = discord.Embed(
                title="🚫 Bannissement - Système de confessions", 
                description="Tu as été banni du système de confessions par un modérateur.",
                color=discord.Color.red(),
                timestamp=datetime.now(timezone.utc)
            )
            asyncio.create_task(self.send_dm_safe(member, dm_embed))

            await ctx.send(f"✅ {member.mention} a été banni du système de confessions.")
            await self.log_command(
                "Ban Confession", 
                f"{ctx.author} a banni {member} ({member.id}) du système de confessions", 
                moderator=ctx.author, 
                color=discord.Color.orange()
            )
            
        except Exception as e:
            logger.error(f"Erreur lors du bannissement de {member.id}: {e}")
            await ctx.send("❌ Une erreur s'est produite lors du bannissement.")

    @commands.command(name="unbanconfession")
    async def unbanconfession(self, ctx, member: discord.Member):
        """Débannit un utilisateur du système de confessions."""
        # Vérification des permissions
        if not self.has_admin_permissions(ctx.author, ctx.guild):
            return await ctx.send("❌ Tu n'as pas les permissions nécessaires pour utiliser cette commande.")
        
        try:
            bans = load_bans()
            if member.id not in bans.get("banned", []):
                return await ctx.send(f"⚠️ {member.mention} n'était pas banni du système de confessions.")
            
            bans["banned"].remove(member.id)
            if not save_bans(bans):
                return await ctx.send("❌ Erreur lors de la sauvegarde du débannissement.")

            # Notification par DM
            dm_embed = discord.Embed(
                title="✅ Débannissement - Système de confessions", 
                description="Tu peux de nouveau utiliser le système de confessions.",
                color=discord.Color.green(),
                timestamp=datetime.now(timezone.utc)
            )
            asyncio.create_task(self.send_dm_safe(member, dm_embed))

            await ctx.send(f"✅ {member.mention} a été débanni du système de confessions.")
            await self.log_command(
                "Unban Confession", 
                f"{ctx.author} a débanni {member} ({member.id}) du système de confessions", 
                moderator=ctx.author, 
                color=discord.Color.green()
            )
            
        except Exception as e:
            logger.error(f"Erreur lors du débannissement de {member.id}: {e}")
            await ctx.send("❌ Une erreur s'est produite lors du débannissement.")

    @commands.command(name="listbanconfession")
    async def listbanconfession(self, ctx):
        """Liste les utilisateurs bannis du système de confessions."""
        # Vérification des permissions
        if not self.has_admin_permissions(ctx.author, ctx.guild):
            return await ctx.send("❌ Tu n'as pas les permissions nécessaires pour utiliser cette commande.")
        
        try:
            bans = load_bans()
            banned = bans.get("banned", [])
            
            if not banned:
                embed = discord.Embed(
                    title="📋 Liste des bannissements",
                    description="Aucun utilisateur n'est actuellement banni du système de confessions.",
                    color=discord.Color.blue(),
                    timestamp=datetime.now(timezone.utc)
                )
                return await ctx.send(embed=embed)
            
            # Construction de la liste avec gestion des erreurs
            lines = []
            for uid in banned:
                try:
                    user = await self.bot.fetch_user(uid)
                    lines.append(f"• {user} (`{uid}`)") 
                except discord.NotFound:
                    lines.append(f"• Utilisateur introuvable (`{uid}`)") 
                except Exception as e:
                    logger.warning(f"Erreur lors de la récupération de l'utilisateur {uid}: {e}")
                    lines.append(f"• ID: `{uid}` (erreur de récupération)")
            
            # Pagination si nécessaire
            description = "\n".join(lines)
            if len(description) > 4000:  # Limite Discord pour les descriptions
                description = description[:4000] + "\n... (liste tronquée)"
            
            embed = discord.Embed(
                title=f"📋 Utilisateurs bannis ({len(banned)})",
                description=description,
                color=discord.Color.orange(),
                timestamp=datetime.now(timezone.utc)
            )
            embed.set_footer(text=f"Total: {len(banned)} utilisateur(s) banni(s)")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Erreur lors de l'affichage de la liste des bannis: {e}")
            await ctx.send("❌ Une erreur s'est produite lors de la récupération de la liste.")

    # -------------------------
    # on_ready: re-register dynamic persistent views for every confession message
    # -------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        """Recharge les vues persistantes au démarrage du bot avec optimisations."""
        logger.info("Rechargement des vues persistantes pour les confessions...")
        
        try:
            data = load_confessions()
            confessions = data.get("confessions", [])
            
            if not confessions:
                logger.info("Aucune confession trouvée, pas de vues à recharger.")
                return
            
            count = 0
            errors = 0
            
            # Optimisation: utilise channel_id si disponible
            for conf in confessions:
                msg_id = conf.get("message_id")
                if not msg_id:
                    continue
                
                try:
                    found = False
                    channel_id = conf.get("channel_id")
                    
                    # Essaie d'abord avec l'ID de canal stocké (plus rapide)
                    if channel_id:
                        try:
                            channel = self.bot.get_channel(channel_id)
                            if channel:
                                msg = await channel.fetch_message(msg_id)
                                reply_enabled = not isinstance(channel, discord.Thread)
                                view = self.DynamicConfessView(self, conf["id"], reply_enabled=reply_enabled)
                                self.bot.add_view(view)
                                found = True
                                count += 1
                        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                            # Message supprimé ou permissions insuffisantes
                            pass
                        except Exception as e:
                            logger.warning(f"Erreur lors de la récupération du message {msg_id} dans le canal {channel_id}: {e}")
                    
                    # Si pas trouvé avec l'ID de canal, recherche dans tous les canaux (fallback)
                    if not found:
                        for guild in self.bot.guilds:
                            if found:
                                break
                            try:
                                # Recherche optimisée: d'abord les canaux texte, puis les threads actifs
                                channels_to_search = guild.text_channels + [t for t in guild.threads if not t.archived]
                                
                                for channel in channels_to_search:
                                    try:
                                        msg = await channel.fetch_message(msg_id)
                                        reply_enabled = not isinstance(channel, discord.Thread)
                                        view = self.DynamicConfessView(self, conf["id"], reply_enabled=reply_enabled)
                                        self.bot.add_view(view)
                                        
                                        # Met à jour le channel_id pour les prochaines fois
                                        if not conf.get("channel_id"):
                                            conf["channel_id"] = channel.id
                                            save_confessions(data)
                                        
                                        found = True
                                        count += 1
                                        break
                                    except (discord.NotFound, discord.Forbidden):
                                        continue
                                    except Exception:
                                        continue
                            except Exception:
                                continue
                    
                    if not found:
                        errors += 1
                        
                except Exception as e:
                    logger.error(f"Erreur lors du traitement de la confession {conf.get('id', 'inconnue')}: {e}")
                    errors += 1
            
            # Résumé du rechargement
            logger.info(f"Rechargement terminé: {count} vues rechargées, {errors} erreurs")
            if errors > 0:
                logger.warning(f"{errors} confessions n'ont pas pu être rechargées (messages supprimés ou inaccessibles)")
                
        except Exception as e:
            logger.error(f"Erreur critique lors du rechargement des vues: {e}")

async def setup(bot):
    """Configure le cog Confessions."""
    try:
        await bot.add_cog(Confessions(bot))
        logger.info("Cog Confessions chargé avec succès")
    except Exception as e:
        logger.error(f"Erreur lors du chargement du cog Confessions: {e}")
        raise