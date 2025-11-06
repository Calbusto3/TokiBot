import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

# --------------------
# Static command registry (curated)
# type: 'slash' | 'prefix' | 'hybrid'
# --------------------
COMMAND_REGISTRY: list[dict] = [
    # Info
    {"type": "slash", "name": "ping", "qname": "ping", "category": "Info", "description": "Voir la latence du bot.", "usage": "/ping [ephemeral]", "permissions": "Aucune"},
    {"type": "slash", "name": "health", "qname": "health", "category": "Info", "description": "État de santé du bot (uptime, latence).", "usage": "/health [ephemeral]", "permissions": "Aucune"},
    {"type": "slash", "name": "botinfo", "qname": "botinfo", "category": "Info", "description": "Informations générales sur TokiBot.", "usage": "/botinfo [ephemeral]", "permissions": "Aucune"},
    {"type": "slash", "name": "serverinfo", "qname": "serverinfo", "category": "Info", "description": "Informations sur le serveur courant.", "usage": "/serverinfo [ephemeral]", "permissions": "Être dans un serveur"},

    # Confessions (slash)
    {"type": "slash", "name": "confesser", "qname": "confesser", "category": "Confessions", "description": "Envoyer une confession anonyme.", "usage": "/confesser", "permissions": "Aucune"},
    {"type": "slash", "name": "confession_reports", "qname": "confession_reports", "category": "Confessions", "description": "Lister/exporter les signalements de confessions.", "usage": "/confession_reports [user] [export] [limit]", "permissions": "Gérer les messages"},
    {"type": "slash", "name": "confession_actions", "qname": "confession_actions", "category": "Confessions", "description": "Lister/exporter le journal des actions des confessions.", "usage": "/confession_actions [export] [limit]", "permissions": "Gérer les messages"},
    {"type": "slash", "name": "confession_ban", "qname": "confession_ban", "category": "Confessions", "description": "Bannir un utilisateur du système de confessions.", "usage": "/confession_ban user [duration] [reason]", "permissions": "Gérer les messages"},
    {"type": "slash", "name": "confession_unban", "qname": "confession_unban", "category": "Confessions", "description": "Débannir un utilisateur du système de confessions.", "usage": "/confession_unban user", "permissions": "Gérer les messages"},
    {"type": "slash", "name": "confession_bans", "qname": "confession_bans", "category": "Confessions", "description": "Lister les bannissements du système de confessions.", "usage": "/confession_bans", "permissions": "Gérer les messages"},

    # Moderation (slash)
    {"type": "slash", "name": "ban", "qname": "ban", "category": "Modération", "description": "Bannir un membre.", "usage": "/ban member [reason]", "permissions": "Bannir des membres"},
    {"type": "slash", "name": "unban", "qname": "unban", "category": "Modération", "description": "Débannir un utilisateur par ID.", "usage": "/unban user_id", "permissions": "Bannir des membres"},
    {"type": "slash", "name": "kick", "qname": "kick", "category": "Modération", "description": "Expulser un membre.", "usage": "/kick member [reason]", "permissions": "Expulser des membres"},

    # Hybrids (mute/unmute utilisables en slash et préfixe)
    {"type": "hybrid", "name": "mute", "qname": "mute", "category": "Modération", "description": "Mute un membre pour une durée.", "usage": "/mute member duration [reason] | +mute <membre> <durée> [raison]", "permissions": "Modérer des membres"},
    {"type": "hybrid", "name": "unmute", "qname": "unmute", "category": "Modération", "description": "Démute un membre.", "usage": "/unmute member [reason] | +unmute <membre> [raison]", "permissions": "Modérer des membres"},

    # Prefix: admin/extra/modération
    {"type": "prefix", "name": "off", "qname": "off", "category": "Admin", "description": "Éteindre le bot (owner/EXTRA_OWNER_IDS).", "usage": "+off", "permissions": "Propriétaire"},
    {"type": "prefix", "name": "reboot", "qname": "reboot", "category": "Admin", "description": "Redémarrer le bot (owner/EXTRA_OWNER_IDS).", "usage": "+reboot", "permissions": "Propriétaire"},
    {"type": "prefix", "name": "cogs", "qname": "cogs", "category": "Admin", "description": "Lister les cogs chargés/non chargés.", "usage": "+cogs", "permissions": "Aucune (affichage)"},
    {"type": "prefix", "name": "reload", "qname": "reload", "category": "Admin", "description": "(Re)charger un cog.", "usage": "+reload <cog> (ex: slash_commands.info)", "permissions": "Propriétaire"},

    {"type": "prefix", "name": "avatar", "qname": "avatar", "category": "Utilitaires", "description": "Afficher l'avatar d'un membre.", "usage": "+avatar [membre]", "permissions": "Aucune"},
    {"type": "prefix", "name": "banner", "qname": "banner", "category": "Utilitaires", "description": "Afficher la bannière d'un membre (si disponible).", "usage": "+banner [membre]", "permissions": "Aucune"},
    {"type": "prefix", "name": "userinfo", "qname": "userinfo", "category": "Utilitaires", "description": "Informations sur un utilisateur.", "usage": "+userinfo [membre]", "permissions": "Aucune"},

    {"type": "prefix", "name": "hide", "qname": "hide", "category": "Modération", "description": "Masquer un salon au public.", "usage": "+hide [#salon] <raison>", "permissions": "Admin/Role modération"},
    {"type": "prefix", "name": "unhide", "qname": "unhide", "category": "Modération", "description": "Rendre visible un salon au public.", "usage": "+unhide [#salon]", "permissions": "Admin/Role modération"},
    {"type": "prefix", "name": "lock", "qname": "lock", "category": "Modération", "description": "Verrouiller l'envoi de messages dans un salon.", "usage": "+lock [#salon] <raison>", "permissions": "Admin/Role modération"},
    {"type": "prefix", "name": "unlock", "qname": "unlock", "category": "Modération", "description": "Déverrouiller l'envoi de messages dans un salon.", "usage": "+unlock [#salon]", "permissions": "Admin/Role modération"},
    {"type": "prefix", "name": "clear", "qname": "clear", "category": "Modération", "description": "Supprimer des messages en lot.", "usage": "+clear <nombre>", "permissions": "Admin/Role modération"},
    {"type": "prefix", "name": "reset", "qname": "reset", "category": "Modération", "description": "Réinitialiser un salon (purge totale).", "usage": "+reset [#salon] (confirmation requise)", "permissions": "Admin/Role modération"},
    {"type": "prefix", "name": "parler", "qname": "parler", "category": "Utilitaires", "description": "Faire parler le bot dans un salon cible.", "usage": "+parler <message> [#salon]", "permissions": "Administrateur"},
    {"type": "prefix", "name": "modif_say", "qname": "modif_say", "category": "Utilitaires", "description": "Modifier un message envoyé via +parler.", "usage": "+modif_say <message_id> <nouveau_contenu>", "permissions": "Administrateur"},

    # Prefix moderation (ban/unban/kick)
    {"type": "prefix", "name": "ban", "qname": "ban", "category": "Modération", "description": "Bannir un membre avec durée optionnelle.", "usage": "+ban <membre> [durée] [raison]", "permissions": "Admin/Role modération"},
    {"type": "prefix", "name": "unban", "qname": "unban", "category": "Modération", "description": "Débannir un utilisateur.", "usage": "+unban <user_id|nom>", "permissions": "Admin/Role modération"},
    {"type": "prefix", "name": "kick", "qname": "kick", "category": "Modération", "description": "Expulser un membre.", "usage": "+kick <membre> [raison]", "permissions": "Admin/Role modération"},
]

class HelpSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    class HelpSelect(discord.ui.Select):
        def __init__(self, entries: list[dict]):
            options = []
            for e in entries[:25]:
                prefix = "/" if e["type"] in ("slash", "hybrid") else "+"
                label = f"{prefix}{e['qname']}"
                desc = (e.get("description") or "Commande")[:100]
                options.append(discord.SelectOption(label=label[:100], description=desc, value=e["type"]+":"+e["qname"]))
            super().__init__(placeholder="Choisissez une commande…", min_values=1, max_values=1, options=options)

        async def callback(self, interaction: discord.Interaction):
            try:
                value = self.values[0]
                t, qn = value.split(":", 1)
                entry = next((e for e in COMMAND_REGISTRY if e["qname"] == qn and e["type"] == t), None)
                if not entry:
                    return await interaction.response.edit_message(content="Commande introuvable.")
                prefix = "/" if entry["type"] in ("slash", "hybrid") else "+"
                sig = f"{prefix}{entry['qname']}"
                emb = discord.Embed(
                    title=f"❖ {sig}",
                    description=entry.get("description") or "",
                    color=discord.Color.blurple(),
                    timestamp=datetime.now(timezone.utc),
                )
                if entry.get("category"):
                    emb.add_field(name="Catégorie", value=str(entry["category"])[:256], inline=True)
                if entry.get("usage"):
                    emb.add_field(name="Usage", value=str(entry["usage"])[:1024], inline=False)
                if entry.get("permissions"):
                    emb.add_field(name="Permissions", value=str(entry["permissions"])[:1024], inline=False)
                await interaction.response.edit_message(embed=emb)
            except Exception:
                await interaction.response.edit_message(content="Erreur lors de l'affichage de l'aide.")

    class HelpView(discord.ui.View):
        def __init__(self, entries: list[dict]):
            super().__init__(timeout=120)
            self.add_item(HelpSlash.HelpSelect(entries))

    @app_commands.command(name="help", description="Aide interactive avec filtres, catégories, usages et permissions")
    @app_commands.describe(recherche="Filtrer par nom/description", type="Filtrer par type (slash/prefixe/hybrid/tout)", categorie="Catégorie (Info, Modération, Confessions, Utilitaires, Admin)", ephemeral="Répondre en privé", page="Numéro de page")
    async def help(self, interaction: discord.Interaction, recherche: str | None = None, type: str | None = None, categorie: str | None = None, ephemeral: bool | None = True, page: int | None = 1):
        query = (recherche or "").strip().lower()
        type_filter = (type or "tout").strip().lower()
        cat_filter = (categorie or "").strip().lower()
        page = max(1, page or 1)

        # Filter registry
        entries = []
        for e in COMMAND_REGISTRY:
            if type_filter != "tout" and e["type"].lower() != type_filter:
                continue
            text = f"{e['qname']} {e.get('description','')} {e.get('category','')}".lower()
            if query and query not in text:
                continue
            if cat_filter and cat_filter not in (e.get("category", "").lower()):
                continue
            entries.append(e)

        entries.sort(key=lambda x: (x.get("category","zzzz"), x["qname"]))

        # Pagination
        per_page = 25
        start = (page - 1) * per_page
        end = start + per_page
        page_entries = entries[start:end]

        emb = discord.Embed(
            title="📖 Aide interactive",
            description=(
                "Sélectionnez une commande dans le menu pour voir ses détails.\n"
                "Filtres: `type=slash|prefixe|hybrid|tout`, `categorie=<nom>`, `recherche=<mot>`.\n"
                "Pagination via `page` (25/pg)."
            ),
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        emb.set_footer(text=f"Total: {len(entries)} • Page {page}")
        if not page_entries:
            emb.add_field(name="Résultats", value="Aucune commande trouvée.")
            return await interaction.response.send_message(embed=emb, ephemeral=bool(ephemeral))

        view = self.HelpView(page_entries)
        await interaction.response.send_message(embed=emb, view=view, ephemeral=bool(ephemeral))

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpSlash(bot))
