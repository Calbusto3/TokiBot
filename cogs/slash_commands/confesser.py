import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from datetime import datetime, timezone
from utils.datetime_utils import format_iso_str
from utils.config import get_bot_config
from utils.logger import get_logger
import asyncio
import threading
from typing import Optional, Dict, Any, Tuple
import time
import io
import re
# -------------------------
# Constantes
# -------------------------
CONFESSION_FILE = "confessions.json"
BANS_FILE = "confession_bans.json"
CONFIG_FILE = "confession_config.json"
REPORTS_FILE = "confession_reports.json"
ACTIONS_FILE = "confession_actions.json"

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
    CONFIG_FILE: threading.Lock(),
    REPORTS_FILE: threading.Lock(),
    ACTIONS_FILE: threading.Lock(),
}

# Setup logging (centralized)
logger = get_logger(__name__)

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

    # -------------------------
    # Admin slash: lister/exporter les signalements
    # -------------------------
    @app_commands.command(name="confession_reports", description="Lister ou exporter les signalements de confessions")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(user="Filtrer par utilisateur ayant signalé", export="Exporter en fichier .txt", limit="Nombre max de lignes (par défaut 100)")
    async def confession_reports(self, interaction: discord.Interaction, user: Optional[discord.User] = None, export: Optional[bool] = False, limit: Optional[int] = 100):
        if not interaction.user.guild_permissions.manage_messages and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
        try:
            data = load_reports()
            reports = data.get("reports", [])
            if user:
                reports = [r for r in reports if int(r.get("reporter_id", 0)) == user.id]
            # tri du plus récent au plus ancien
            def _key(r):
                try:
                    return r.get("timestamp") or ""
                except Exception:
                    return ""
            reports = sorted(reports, key=_key, reverse=True)
            total = len(reports)
            if total == 0:
                return await interaction.response.send_message("Aucun signalement trouvé.", ephemeral=True)

            # préparation texte
            lines = []
            count = 0
            for r in reports:
                if limit and count >= max(1, int(limit)):
                    break
                count += 1
                cid = r.get("confession_id")
                rid = r.get("reporter_id")
                rtag = r.get("reporter_tag")
                reason = r.get("reason", "")
                ts = r.get("timestamp", "")
                lines.append(f"#{count}. Confession {cid} | Reporter {rtag} ({rid}) | {ts}\nRaison: {reason}")

            text = "\n\n".join(lines)
            if export:
                # export fichier
                try:
                    file = discord.File(io.BytesIO(text.encode("utf-8")), filename="confession_reports.txt")
                    await interaction.response.send_message(content=f"Rapport: {count}/{total} signalement(s)", file=file, ephemeral=True)
                except Exception as e:
                    logger.error(f"Erreur export reports: {e}")
                    await interaction.response.send_message("❌ Erreur lors de l'export du fichier.", ephemeral=True)
                return

            # sinon embed résumé
            desc = text
            if len(desc) > 4000:
                desc = desc[:4000] + "\n... (tronqué)"
            embed = discord.Embed(title="📄 Signalements - Confessions", description=desc, color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
            embed.set_footer(text=f"Total trouvés: {total} | Affichés: {count}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Erreur dans confession_reports: {e}")
            try:
                await interaction.response.send_message("❌ Erreur lors de la récupération des signalements.", ephemeral=True)
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

def load_reports() -> Dict[str, Any]:
    """Charge les signalements persistants."""
    return load_json_safe(REPORTS_FILE, {"reports": []})

def save_reports(data: Dict[str, Any]) -> bool:
    """Sauvegarde les signalements persistants."""
    return save_json_safe(REPORTS_FILE, data)

def load_actions() -> Dict[str, Any]:
    """Charge le journal d'actions persistantes (création, réponse, suppression, ban, unban)."""
    return load_json_safe(ACTIONS_FILE, {"actions": []})

def save_actions(data: Dict[str, Any]) -> bool:
    """Sauvegarde le journal d'actions."""
    return save_json_safe(ACTIONS_FILE, data)

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
        """Vérifie si un utilisateur est banni (supporte anciens et nouveaux formats).
        Nouveaux formats: banned: [user_id, {"user_id": int, "until": int|None}]
        Expire automatiquement les bans dont "until" est passé.
        """
        try:
            bans = load_bans()
            banned_list = bans.get("banned", [])
            changed = False
            now = int(time.time())
            result = False
            new_list = []
            for entry in banned_list:
                if isinstance(entry, int):
                    if entry == user_id:
                        result = True
                    new_list.append(entry)
                else:
                    uid = entry.get("user_id")
                    until = entry.get("until")  # epoch seconds or None
                    if until is not None and now >= int(until):
                        changed = True  # expired
                        continue
                    if uid == user_id:
                        result = True
                    new_list.append({"user_id": uid, "until": until})
            if changed:
                bans["banned"] = new_list
                save_bans(bans)
            return result
        except Exception as e:
            logger.error(f"Erreur lors de la vérification du ban pour {user_id}: {e}")
            return False

    # --- Ban helpers ---
    def _parse_duration_seconds(self, s: Optional[str]) -> Optional[int]:
        if not s:
            return None
        m = re.match(r"^(\d+)([smhj])$", s.strip().lower())
        if not m:
            return None
        num, unit = m.groups()
        mult = {"s":1, "m":60, "h":3600, "j":86400}
        return int(num) * mult[unit]

    def add_ban(self, user_id: int, duration_seconds: Optional[int] = None) -> bool:
        bans = load_bans()
        banned = bans.get("banned", [])
        now = int(time.time())
        until = (now + int(duration_seconds)) if duration_seconds else None
        # Remove existing
        banned = [e for e in banned if (e if isinstance(e,int) else e.get("user_id")) != user_id]
        banned.append({"user_id": user_id, "until": until})
        bans["banned"] = banned
        return save_bans(bans)

    def remove_ban(self, user_id: int) -> bool:
        bans = load_bans()
        banned = bans.get("banned", [])
        banned = [e for e in banned if (e if isinstance(e,int) else e.get("user_id")) != user_id]
        bans["banned"] = banned
        return save_bans(bans)
    
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
    # Modal: Delete confession (owner-only)
    # -------------------------
    class DeleteModal(discord.ui.Modal, title="Supprimer la confession"):
        reason = discord.ui.TextInput(label="Raison (requis)", style=discord.TextStyle.long, required=True, max_length=500)

        def __init__(self, cog: "Confessions", confession_id: int, author: discord.User):
            super().__init__()
            self.cog = cog
            self.confession_id = confession_id
            self.author = author

        async def on_submit(self, interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            try:
                data = load_confessions()
                conf = next((c for c in data.get("confessions", []) if c.get("id") == self.confession_id), None)
                if not conf:
                    return await interaction.followup.send("❌ Confession introuvable.", ephemeral=True)
                if conf.get("author_id") != self.author.id:
                    return await interaction.followup.send("❌ Seul l'auteur peut supprimer sa confession.", ephemeral=True)

                channel_id = conf.get("channel_id")
                message_id = conf.get("message_id")
                thread_id = conf.get("thread_id")
                transcript_text = None

                # Transcript si thread
                if thread_id:
                    try:
                        thread = self.cog.bot.get_channel(thread_id)
                        if thread and isinstance(thread, discord.Thread):
                            lines = []
                            async for m in thread.history(limit=None, oldest_first=True):
                                ts = m.created_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                                author = f"{m.author} ({m.author.id})"
                                content = m.content or ""
                                lines.append(f"[{ts}] {author}: {content}")
                            transcript_text = "\n".join(lines) if lines else "(Aucun message)"
                    except Exception as e:
                        logger.warning(f"Impossible de générer la transcription du thread {thread_id}: {e}")

                # Suppression message + thread
                try:
                    if channel_id and message_id:
                        channel = self.cog.bot.get_channel(channel_id)
                        if channel:
                            try:
                                msg = await channel.fetch_message(message_id)
                                await msg.delete()
                            except Exception:
                                pass
                    if thread_id:
                        thread = self.cog.bot.get_channel(thread_id)
                        if thread and isinstance(thread, discord.Thread):
                            try:
                                await thread.delete(reason=f"Suppression par l'auteur: {self.reason.value}")
                            except Exception:
                                pass
                except Exception:
                    pass

                # Retrait du stockage
                try:
                    data["confessions"] = [c for c in data.get("confessions", []) if c.get("id") != self.confession_id]
                    save_confessions(data)
                except Exception:
                    pass

                # Log admin + transcript
                extra = {
                    "Confession": f"#{self.confession_id}",
                    "Auteur": f"{self.author} ({self.author.id})",
                    "Raison": self.reason.value,
                }
                if transcript_text is not None:
                    try:
                        file = discord.File(io.BytesIO(transcript_text.encode("utf-8")), filename=f"transcript_confession_{self.confession_id}.txt")
                        ch = self.cog.bot.get_channel(ADMIN_LOG_CHANNEL_ID)
                        if ch:
                            await ch.send(content=f"🗑️ Suppression de la confession #{self.confession_id}", file=file)
                    except Exception as e:
                        logger.warning(f"Impossible d'envoyer la transcription: {e}")
                await self.cog.log_admin(
                    title=f"Suppression Confession #{self.confession_id}",
                    description="La confession a été supprimée par son auteur.",
                    author=self.author,
                    extra_fields=extra,
                    color=discord.Color.dark_gray()
                )

                await interaction.followup.send("✅ Ta confession a été supprimée.", ephemeral=True)

                # Journal d'action persistant (suppression)
                try:
                    actions = load_actions()
                    al = actions.get("actions", [])
                    al.append({
                        "type": "delete",
                        "confession_id": int(self.confession_id),
                        "author_id": int(self.author.id),
                        "author_tag": str(self.author),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "thread_id": int(thread_id) if thread_id else None,
                    })
                    actions["actions"] = al
                    save_actions(actions)
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"Erreur dans DeleteModal.on_submit: {e}")
                try:
                    await interaction.followup.send("❌ Erreur lors de la suppression.", ephemeral=True)
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

            # Bouton Supprimer (propriétaire uniquement)
            delete_id = f"confess_delete:{confession_id}"
            btn_delete = discord.ui.Button(style=discord.ButtonStyle.secondary, label="Supprimer", custom_id=delete_id)
            btn_delete.callback = self._delete_callback
            self.add_item(btn_delete)

        async def _report_callback(self, interaction: discord.Interaction):
            # check ban
            if self.cog.is_banned(interaction.user.id):
                return await interaction.response.send_message("🚫 Tu es banni du système de confessions.", ephemeral=True)
            # prevent reporting own confession
            data = load_confessions()
            conf = next((c for c in data.get("confessions", []) if c.get("id") == self.confession_id), None)
            if conf and conf.get("author_id") == interaction.user.id:
                return await interaction.response.send_message("❌ Tu ne peux pas signaler ta propre confession.", ephemeral=True)
            # open Report modal
            await interaction.response.send_modal(self.cog.ReportModal(self.cog, self.confession_id, interaction.user))

        async def _reply_callback(self, interaction: discord.Interaction):
            if self.cog.is_banned(interaction.user.id):
                return await interaction.response.send_message("🚫 Tu es banni du système de confessions.", ephemeral=True)
            # prevent replying to own confession
            data = load_confessions()
            conf = next((c for c in data.get("confessions", []) if c.get("id") == self.confession_id), None)
            if conf and conf.get("author_id") == interaction.user.id:
                return await interaction.response.send_message("❌ Tu ne peux pas répondre à ta propre confession.", ephemeral=True)
            # open Reply modal
            await interaction.response.send_modal(self.cog.ReplyModal(self.cog, self.confession_id, interaction.user))

        async def _delete_callback(self, interaction: discord.Interaction):
            # Only the original author can delete
            data = load_confessions()
            conf = next((c for c in data.get("confessions", []) if c.get("id") == self.confession_id), None)
            if not conf:
                return await interaction.response.send_message("❌ Confession introuvable.", ephemeral=True)
            if conf.get("author_id") != interaction.user.id:
                return await interaction.response.send_message("❌ Seul l'auteur de la confession peut la supprimer.", ephemeral=True)
            await interaction.response.send_modal(self.cog.DeleteModal(self.cog, self.confession_id, interaction.user))

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

                # Journal d'action persistant
                try:
                    actions = load_actions()
                    actions_list = actions.get("actions", [])
                    actions_list.append({
                        "type": "create",
                        "confession_id": int(cid),
                        "author_id": int(self.author.id),
                        "author_tag": str(self.author),
                        "timestamp": now,
                        "channel_id": int(channel.id) if channel else None,
                    })
                    actions["actions"] = actions_list
                    save_actions(actions)
                except Exception:
                    pass
                
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
        reason = discord.ui.TextInput(label="Raison du signalement (optionnel)", style=discord.TextStyle.long, required=False, max_length=500)

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

                # Empêcher le signalement de sa propre confession (vérification côté modal)
                if confession.get("author_id") == self.reporter.id:
                    await interaction.followup.send("❌ Tu ne peux pas signaler ta propre confession.", ephemeral=True)
                    return

                # Mise à jour du message de confirmation
                await interaction.edit_original_response(content="✅ Signalement enregistré avec succès !")

                # Persistance du signalement
                try:
                    rpt = load_reports()
                    reports = rpt.get("reports", [])
                    reports.append({
                        "confession_id": int(self.confession_id),
                        "reporter_id": int(self.reporter.id),
                        "reporter_tag": str(self.reporter),
                        "reason": reason,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    rpt["reports"] = reports
                    save_reports(rpt)
                except Exception as e:
                    logger.warning(f"Impossible d'enregistrer le signalement: {e}")

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

                # Empêcher de répondre à sa propre confession (vérification côté modal)
                if parent.get("author_id") == self.replier.id:
                    await interaction.followup.send("❌ Tu ne peux pas répondre à ta propre confession.", ephemeral=True)
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

                    # Journal d'action persistant (réponse dans thread)
                    try:
                        actions = load_actions()
                        al = actions.get("actions", [])
                        al.append({
                            "type": "reply",
                            "confession_id": int(self.confession_id),
                            "reply_id": int(new_id),
                            "author_id": int(self.replier.id),
                            "author_tag": str(self.replier),
                            "timestamp": now,
                            "thread_id": int(channel.id) if isinstance(channel, discord.Thread) else None,
                        })
                        actions["actions"] = al
                        save_actions(actions)
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

                        # Store thread id in parent for management (delete transcripts, etc.)
                        try:
                            parent["thread_id"] = thread.id
                            save_confessions(data)
                        except Exception:
                            pass

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

                        # Journal d'action persistant (réponse créant thread)
                        try:
                            actions = load_actions()
                            al = actions.get("actions", [])
                            al.append({
                                "type": "reply",
                                "confession_id": int(self.confession_id),
                                "reply_id": int(new_id),
                                "author_id": int(self.replier.id),
                                "author_tag": str(self.replier),
                                "timestamp": now,
                                "thread_id": int(thread.id),
                            })
                            actions["actions"] = al
                            save_actions(actions)
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
    # Admin slash: ban / unban / bans (avec journal persistant)
    # -------------------------
    @app_commands.command(name="confession_ban", description="Bannir un utilisateur du système de confessions (durée optionnelle)")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(user="Utilisateur à bannir", duration="10s, 5m, 2h, 1j (optionnel)", reason="Raison")
    async def confession_ban(self, interaction: discord.Interaction, user: discord.User, duration: Optional[str] = None, reason: Optional[str] = None):
        if not interaction.user.guild_permissions.manage_messages and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
        seconds = self._parse_duration_seconds(duration)
        if duration and seconds is None:
            return await interaction.response.send_message("❌ Durée invalide. Utilise p.ex. 10s, 5m, 2h, 1j.", ephemeral=True)
        ok = self.add_ban(user.id, seconds)
        if not ok:
            return await interaction.response.send_message("❌ Erreur lors de l'enregistrement du ban.", ephemeral=True)
        # DM notify (non bloquant)
        dm = discord.Embed(title="🚫 Bannissement - Confessions", description=f"Tu es banni du système de confessions.{f' Durée: {duration}' if seconds else ''}\nRaison: {reason or 'Aucune'}", color=discord.Color.red(), timestamp=datetime.now(timezone.utc))
        asyncio.create_task(self.send_dm_safe(user, dm))
        await interaction.response.send_message(f"✅ {user} banni du système de confessions{f' pour {duration}' if seconds else ''}.")
        await self.log_command("Ban Confession (slash)", f"{interaction.user} a banni {user} ({user.id}){f' pour {duration}' if seconds else ''}. Raison: {reason or 'Aucune'}", moderator=interaction.user, color=discord.Color.orange())
        # Journal d'action persistant
        try:
            actions = load_actions()
            al = actions.get("actions", [])
            al.append({
                "type": "ban",
                "target_id": int(user.id),
                "moderator_id": int(interaction.user.id),
                "moderator_tag": str(interaction.user),
                "duration": seconds,
                "reason": reason or "",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            actions["actions"] = al
            save_actions(actions)
        except Exception:
            pass

    @app_commands.command(name="confession_unban", description="Débannir un utilisateur du système de confessions")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(user="Utilisateur à débannir")
    async def confession_unban(self, interaction: discord.Interaction, user: discord.User):
        if not interaction.user.guild_permissions.manage_messages and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
        ok = self.remove_ban(user.id)
        if not ok:
            return await interaction.response.send_message("❌ Erreur lors de la suppression du ban.", ephemeral=True)
        dm = discord.Embed(title="✅ Débannissement - Confessions", description="Tu peux de nouveau utiliser les confessions.", color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
        asyncio.create_task(self.send_dm_safe(user, dm))
        await interaction.response.send_message(f"✅ {user} débanni du système de confessions.")
        await self.log_command("Unban Confession (slash)", f"{interaction.user} a débanni {user} ({user.id})", moderator=interaction.user, color=discord.Color.green())
        # Journal d'action persistant
        try:
            actions = load_actions()
            al = actions.get("actions", [])
            al.append({
                "type": "unban",
                "target_id": int(user.id),
                "moderator_id": int(interaction.user.id),
                "moderator_tag": str(interaction.user),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            actions["actions"] = al
            save_actions(actions)
        except Exception:
            pass

    @app_commands.command(name="confession_bans", description="Lister les bannissements du système de confessions")
    @app_commands.default_permissions(manage_messages=True)
    async def confession_bans(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_messages and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
        bans = load_bans()
        now = int(time.time())
        entries = []
        for e in bans.get("banned", []):
            if isinstance(e, int):
                entries.append((e, None))
            else:
                entries.append((e.get("user_id"), e.get("until")))
        if not entries:
            return await interaction.response.send_message("Aucun utilisateur banni.", ephemeral=True)
        lines = []
        for uid, until in entries:
            try:
                user = await self.bot.fetch_user(uid)
                name = str(user)
            except Exception:
                name = f"ID {uid}"
            if until:
                remain = max(0, int(until) - now)
                mins = remain // 60
                lines.append(f"• {name} (reste ~{mins} min)")
            else:
                lines.append(f"• {name} (indéfini)")
        desc = "\n".join(lines)
        await interaction.response.send_message(embed=discord.Embed(title="🚫 Bannissements Confessions", description=desc[:4096], color=discord.Color.orange(), timestamp=datetime.now(timezone.utc)), ephemeral=True)

    # -------------------------
    # Admin slash: export journal d'actions (persistant)
    # -------------------------
    @app_commands.command(name="confession_actions", description="Lister/exporter le journal d'actions des confessions")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.describe(export="Exporter en fichier .txt", limit="Nombre max de lignes (défaut 100)")
    async def confession_actions(self, interaction: discord.Interaction, export: Optional[bool] = False, limit: Optional[int] = 100):
        if not interaction.user.guild_permissions.manage_messages and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Permission insuffisante.", ephemeral=True)
        try:
            data = load_actions()
            actions = data.get("actions", [])
            # tri par timestamp
            def _key(a):
                try:
                    return a.get("timestamp") or ""
                except Exception:
                    return ""
            actions = sorted(actions, key=_key, reverse=True)
            total = len(actions)
            if total == 0:
                return await interaction.response.send_message("Aucune action enregistrée.", ephemeral=True)

            lines = []
            count = 0
            for a in actions:
                if limit and count >= max(1, int(limit)):
                    break
                count += 1
                t = a.get("type")
                ts = a.get("timestamp", "")
                if t == "create":
                    lines.append(f"#{count}. CREATE conf#{a.get('confession_id')} par {a.get('author_tag')} ({a.get('author_id')}) | {ts}")
                elif t == "reply":
                    lines.append(f"#{count}. REPLY conf#{a.get('confession_id')} -> rep#{a.get('reply_id')} par {a.get('author_tag')} ({a.get('author_id')}) | {ts}")
                elif t == "delete":
                    lines.append(f"#{count}. DELETE conf#{a.get('confession_id')} par {a.get('author_tag')} ({a.get('author_id')}) | {ts}")
                elif t == "ban":
                    lines.append(f"#{count}. BAN {a.get('target_id')} par {a.get('moderator_tag')} | dur={a.get('duration')} | {ts}")
                elif t == "unban":
                    lines.append(f"#{count}. UNBAN {a.get('target_id')} par {a.get('moderator_tag')} | {ts}")
                else:
                    lines.append(f"#{count}. {t} | {ts}")

            text = "\n".join(lines)
            if export:
                try:
                    file = discord.File(io.BytesIO(text.encode("utf-8")), filename="confession_actions.txt")
                    await interaction.response.send_message(content=f"Journal: {count}/{total} action(s)", file=file, ephemeral=True)
                except Exception:
                    await interaction.response.send_message("❌ Erreur lors de l'export.", ephemeral=True)
                return

            desc = text if len(text) <= 4000 else (text[:4000] + "\n... (tronqué)")
            emb = discord.Embed(title="🗂️ Journal d'actions - Confessions", description=desc, color=discord.Color.blurple(), timestamp=datetime.now(timezone.utc))
            emb.set_footer(text=f"Total: {total} | Affichés: {count}")
            await interaction.response.send_message(embed=emb, ephemeral=True)
        except Exception as e:
            logger.error(f"Erreur dans confession_actions: {e}")
            try:
                await interaction.response.send_message("❌ Erreur lors de la récupération du journal.", ephemeral=True)
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