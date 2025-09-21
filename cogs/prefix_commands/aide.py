import discord
from discord.ext import commands

STAFF_ROLE_ID = 1418345309377003551

# -------------------- DONNÉES COMMANDES --------------------
COMMANDS_INFO = {
    "ban": {
        "summary": "Bannir un membre du serveur",
        "details": (
            "**Action :** Bannir un membre définitivement ou temporairement\n"
            "**Exemples :** `+ban @user 1h` ou `/ban user:123456789 temps:1h`\n"
            "**Permissions :** Modérateur ou Administrateur\n"
            "**Disponibilité :** Préfixe et Slash"
        )
    },
    "kick": {
        "summary": "Expulser un membre du serveur",
        "details": (
            "**Action :** Expulser un membre du serveur\n"
            "**Exemples :** `+kick @user` ou `/kick user:123456789`\n"
            "**Permissions :** Modérateur ou Administrateur\n"
            "**Disponibilité :** Préfixe et Slash"
        )
    },
    "mute": {
        "summary": "Muter un membre (temporaire ou permanent)",
        "details": (
            "**Action :** Empêche un membre de parler sur le serveur\n"
            "**Exemples :** `+mute @user 10m raison` ou avec le /\n"
            "**Permissions :** Modérateur ou Administrateur\n"
            "**Disponibilité :** Préfixe et Slash"
        )
    },
    "unmute": {
        "summary": "Démuter un membre",
        "details": (
            "**Action :**Réactive la possibilité de parler pour un membre\n"
            "**Exemples :** `+unmute @user raison ou avec le /\n"
            "**Permissions :** Modérateur ou Administrateur\n"
            "**Disponibilité :** Préfixe et Slash"
        )
    },
    "unban": {
        "summary": "Débannir un membre",
        "details": (
            "**Action :** Retire un ban actif sur un membre\n"
            "**Exemples :** `+unban 123456789` ou avec le /\n"
            "**Permissions :** Modérateur ou Administrateur\n"
            "**Disponibilité :** Préfixe et Slash"
        )
    },
    "confesser": {
        "summary": "Envoyer une confession anonyme",
        "details": (
            "**Action :** Permet d'envoyer une confession anonymement\n"
            "**Exemples :** `/confesser` (remplir le modal)\n"
            "**Fonctionnalités :**Envoyer un message anonymement\n"
            "**Disponibilité :** Slash uniquement"
        )
    },

    "parler": {
            "summary": "Faire parler le bot",
            "details": (
                "**Action :**Envoie le message que vous fournisser sous l'identité du bot\n"
                "**Exemples :** `+parler bonjour c'est le bot ! #salon (optionnel)`\n"
                "**Permissions :** Admin\n"
                "**Disponibilité :** Préfixe uniquement"
            )
        },

    "avatar": {
        "summary": "Afficher l'avatar d'un membre",
        "details": (
            "**Action :** Montre l'avatar Discord d'un membre\n"
            "**Exemples :** `+avatar @user`\n"
            "**Disponibilité :** Préfixe uniquement"
        )
    },
    "banner": {
        "summary": "Afficher la bannière d'un membre",
        "details": (
            "**Action :** Montre la bannière Discord d'un membre si disponible\n"
            "**Exemples :** `+banner @user`\n"
            "**Disponibilité :** Préfixe uniquement"
        )
    },
    "userinfo": {
        "summary": "Afficher les informations d'un membre",
        "details": (
            "**Action :** Donne les informations principales d'un membre\n"
            "**Exemples :** `+userinfo @user`\n"
            "**Disponibilité :** Préfixe uniquement"
        )
    },
    "hide": {
        "summary": "Masquer un salon pour tout le monde sauf le staff",
        "details": (
            "**Action :** Retire la permission de voir le salon à tous sauf modérateurs/admin\n"
            "**Exemples :** `+hide #salon Raison`\n"
            "**Permissions :** Modérateur/Admin\n"
            "**Disponibilité :** Préfixe uniquement"
        )
    },
    "unhide": {
        "summary": "Rendre un salon caché visible à tous",
        "details": (
            "**Action :** Rétablit les permissions par défaut pour tous\n"
            "**Exemples :** `+unhide #salon`\n"
            "**Permissions :** Modérateur/Admin\n"
            "**Disponibilité :** Préfixe uniquement"
        )
        },
    "lock": {
        "summary": "Verrouiller un salon",
        "details": (
            "**Action :** Retire la permission d'envoyer des messages à tous sauf modérateurs/admin\n"
            "**Exemples :** `+lock #salon Raison`\n"
            "**Permissions :** Modérateur/Admin\n"
            "**Disponibilité :** Préfixe uniquement"
        )
    },
    "unlock": {
        "summary": "Déverrouiller un salon",
        "details": (
            "**Action :** Rétablit les permissions d'envoi de messages par défaut\n"
            "**Exemples :** `+unlock #salon`\n"
            "**Permissions :** Modérateur/Admin\n"
            "**Disponibilité :** Préfixe uniquement"
        )
    },
}

# -------------------- COG --------------------
class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def is_staff_or_admin():
        async def predicate(ctx):
            if ctx.author.guild_permissions.administrator:
                return True
            role = discord.utils.get(ctx.guild.roles, id=STAFF_ROLE_ID)
            return role in ctx.author.roles if role else False
        return commands.check(predicate)

    @commands.command(name="aide")
    @is_staff_or_admin()
    async def aide(self, ctx):
        # Embed principal
        main_embed = discord.Embed(
            title="📖 Guide des commandes (préfixe du bot : +)",
            description="Sélectionnez une commande dans le menu ci-dessous pour voir les détails.",
            color=discord.Color.green()
        )
        for cmd, info in COMMANDS_INFO.items():
            main_embed.add_field(name=cmd, value=info["summary"], inline=False)

        # Création du menu déroulant
        options = [discord.SelectOption(label=cmd, description=info["summary"]) for cmd, info in COMMANDS_INFO.items()]
        select = discord.ui.Select(placeholder="Sélectionnez une commande", options=options)

        view = discord.ui.View()

        async def select_callback(interaction: discord.Interaction):
            selected = interaction.data["values"][0]
            # Embed détaillé de la commande
            details_embed = discord.Embed(
                title=f"📖 Détails de {selected}",
                description=COMMANDS_INFO[selected]["details"],
                color=discord.Color.blue()
            )

            # Bouton retour
            back_button = discord.ui.Button(label="<- Retour", style=discord.ButtonStyle.gray)
            details_view = discord.ui.View()
            details_view.add_item(back_button)

            async def back_callback(btn_interaction: discord.Interaction):
                # Remet l'embed principal et le menu déroulant
                view.clear_items()
                view.add_item(select)
                await btn_interaction.response.edit_message(embed=main_embed, view=view)

            back_button.callback = back_callback

            # Éditer le message avec l'embed détaillé et le bouton retour
            await interaction.response.edit_message(embed=details_embed, view=details_view)

        select.callback = select_callback
        view.add_item(select)

        await ctx.send(embed=main_embed, view=view)


async def setup(bot):
    await bot.add_cog(Help(bot))
