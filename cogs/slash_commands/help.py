import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone

class HelpSlash(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    class HelpSelect(discord.ui.Select):
        def __init__(self, bot: commands.Bot, entries: list[tuple[str, str, str]]):
            self.bot = bot
            options = [
                discord.SelectOption(label=label[:100], description=(desc or "Commande")[:100], value=value)
                for label, desc, value in entries[:25]
            ]
            super().__init__(placeholder="Choisissez une commande…", min_values=1, max_values=1, options=options)

        async def callback(self, interaction: discord.Interaction):
            value = self.values[0]
            prefix = False
            if value.startswith("prefix::"):
                prefix = True
                name = value.split("::", 1)[1]
            else:
                name = value

            if prefix:
                cmd = self.bot.get_command(name)
                if not cmd:
                    return await interaction.response.edit_message(content="Commande introuvable.")
                sig = f"+{cmd.qualified_name}"
                if cmd.signature:
                    sig += f" {cmd.signature}"
                emb = discord.Embed(
                    title=f"❖ {sig}",
                    description=(cmd.help or "Commande préfixe"),
                    color=discord.Color.blurple(),
                    timestamp=datetime.now(timezone.utc),
                )
                return await interaction.response.edit_message(embed=emb)
            else:
                # slash
                found = None
                for c in self.bot.tree.walk_commands():
                    if c.qualified_name == name:
                        found = c
                        break
                if not found:
                    return await interaction.response.edit_message(content="Commande introuvable.")
                sig = f"/{found.qualified_name}"
                emb = discord.Embed(
                    title=f"❖ {sig}",
                    description=(found.description or "Commande slash"),
                    color=discord.Color.blurple(),
                    timestamp=datetime.now(timezone.utc),
                )
                return await interaction.response.edit_message(embed=emb)

    class HelpView(discord.ui.View):
        def __init__(self, bot: commands.Bot, entries: list[tuple[str, str, str]]):
            super().__init__(timeout=120)
            self.add_item(HelpSlash.HelpSelect(bot, entries))

    @app_commands.command(name="help", description="Aide interactive: recherche et sélection de commandes")
    @app_commands.describe(recherche="Filtrer par nom de commande")
    async def help(self, interaction: discord.Interaction, recherche: str | None = None):
        query = (recherche or "").strip().lower()

        slash_cmds = []
        try:
            for c in self.bot.tree.walk_commands():
                if c.name.startswith("_"):
                    continue
                label = c.qualified_name
                desc = c.description or ""
                text = f"{label} {desc}".lower()
                if query and query not in text:
                    continue
                slash_cmds.append((label, desc, label))
        except Exception:
            pass

        prefix_cmds = []
        try:
            for c in self.bot.commands:
                if not getattr(c, "hidden", False):
                    label = c.qualified_name
                    desc = c.help or ""
                    text = f"{label} {desc}".lower()
                    if query and query not in text:
                        continue
                    prefix_cmds.append((label, desc, f"prefix::{label}"))
        except Exception:
            pass

        entries = [(f"/{n}", d, v) for n, d, v in slash_cmds] + [(f"+{n}", d, v) for n, d, v in prefix_cmds]
        entries.sort(key=lambda x: x[0].lower())

        emb = discord.Embed(
            title="📖 Aide interactive",
            description=("Sélectionnez une commande dans le menu pour voir ses détails.\n"
                         "Astuce: `/help recherche:<mot>` pour filtrer."
            ),
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        if not entries:
            emb.add_field(name="Résultats", value="Aucune commande trouvée.")
            return await interaction.response.send_message(embed=emb, ephemeral=True)

        view = self.HelpView(self.bot, entries)
        await interaction.response.send_message(embed=emb, view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpSlash(bot))
