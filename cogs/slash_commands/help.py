import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

class HelpSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Aide rapide: trouvez une commande et infos essentielles")
    @app_commands.describe(recherche="Filtrer par nom de commande")
    async def help(self, interaction: discord.Interaction, recherche: str | None = None):
        query = (recherche or "").strip().lower()

        # Récupération des slash commands
        try:
            all_cmds = list(self.bot.tree.walk_commands())
        except Exception:
            all_cmds = []

        items: list[tuple[str, str]] = []  # (qualified_name, description)
        for c in all_cmds:
            if c.name.startswith("_"):
                continue
            name = c.qualified_name
            desc = c.description or ""
            text = f"{name} {desc}".lower()
            if query and query not in text:
                continue
            items.append((name, desc))

        items.sort(key=lambda x: x[0])
        shown = items[:25]
        more = max(0, len(items) - len(shown))

        emb = discord.Embed(
            title="📖 Aide (Slash)",
            description=(
                "Utilise `/help <recherche>` pour filtrer.\n"
                "Pour une aide interactive complète (préfixe + slash), utilise `+aide`."
            ),
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )

        if not shown:
            emb.add_field(name="Résultats", value="Aucune commande trouvée.", inline=False)
        else:
            for name, desc in shown:
                emb.add_field(name=f"/{name}", value=(desc or "Commande slash"), inline=False)
            if more:
                emb.set_footer(text=f"+{more} autres. Affine la recherche ou utilise +aide pour une vue interactive.")
        await interaction.response.send_message(embed=emb, ephemeral=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpSlash(bot))
