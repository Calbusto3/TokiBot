import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from utils.config import get_bot_config

_BOT_CFG = get_bot_config()
STAFF_ROLE_ID = _BOT_CFG.get("STAFF_ROLE_ID")

# -------------------- OUTILS --------------------
def is_staff_or_admin():
    async def predicate(ctx: commands.Context) -> bool:
        if getattr(ctx.author.guild_permissions, "administrator", False):
            return True
        role = discord.utils.get(ctx.guild.roles, id=STAFF_ROLE_ID)
        return role in ctx.author.roles if role else False
    return commands.check(predicate)

def format_usage_prefix(cmd: commands.Command) -> str:
    parts = [f"+{cmd.qualified_name}"]
    if cmd.signature:
        parts.append(cmd.signature)
    return " ".join(parts)

def command_summary_prefix(cmd: commands.Command) -> str:
    return cmd.brief or (cmd.help.split("\n")[0] if cmd.help else "Commande préfixe")

def command_details_prefix(cmd: commands.Command) -> str:
    lines = []
    # Description simple (première ligne du help si disponible)
    if cmd.help:
        first_line = cmd.help.strip().split("\n")[0]
        lines.append(f"**Description :** {first_line}")
    else:
        lines.append("**Description :** Commande préfixe du bot")
    # Usage clair
    lines.append(f"**Usage :** `{format_usage_prefix(cmd)}`")
    return "\n".join(lines)

def format_params_slash(cmd: app_commands.Command) -> str:
    if not cmd.parameters:
        return "(aucun)"
    parts = []
    for p in cmd.parameters:
        # p is app_commands.transformers.CommandParameter
        req = "obligatoire" if p.required else "optionnel"
        parts.append(f"`{p.display_name}` ({req})")
    return ", ".join(parts)

def command_summary_slash(cmd: app_commands.Command) -> str:
    return cmd.description or "Commande slash"

def command_details_slash(cmd: app_commands.Command) -> str:
    lines = [
        f"**Description :** {cmd.description or 'Commande slash'}",
        f"**Paramètres :** {format_params_slash(cmd)}"
    ]
    return "\n".join(lines)

# -------------------- COG --------------------
class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    class HelpView(discord.ui.View):
        def __init__(self, cog: "Help", ctx: commands.Context, query: Optional[str] = None, type_filter: str = "all", page: int = 0):
            super().__init__(timeout=120)
            self.cog = cog
            self.ctx = ctx
            self.query = (query or "").strip().lower()
            self.type_filter = type_filter  # all | prefix | slash
            self.page = page
            self.per_page = 20
            self.items: List[Tuple[str, str, str]] = []  # (type, qualified_name, summary)
            self._build_items()
            self._build_components()

        def _build_items(self):
            self.items.clear()
            # Prefix commands
            if self.type_filter in ("all", "prefix"):
                for cmd in sorted(self.cog.bot.commands, key=lambda c: c.qualified_name):
                    if cmd.hidden:
                        continue
                    name = cmd.qualified_name
                    summary = command_summary_prefix(cmd)
                    text = f"{name} {summary or ''}".lower()
                    if self.query and self.query not in text:
                        continue
                    self.items.append(("prefix", name, summary))

            # Slash commands
            if self.type_filter in ("all", "slash"):
                try:
                    for scmd in sorted(self.cog.bot.tree.walk_commands(), key=lambda c: c.qualified_name):
                        if scmd.name.startswith("_"):
                            continue
                        name = scmd.qualified_name
                        summary = command_summary_slash(scmd)
                        text = f"{name} {summary or ''}".lower()
                        if self.query and self.query not in text:
                            continue
                        self.items.append(("slash", name, summary))
                except Exception:
                    pass

        def _page_slice(self) -> Tuple[int, int]:
            start = self.page * self.per_page
            end = start + self.per_page
            return start, end

        def _build_components(self):
            self.clear_items()

            # Header select for type filter
            type_select = discord.ui.Select(placeholder="Filtrer par type (Tous, Préfixe, Slash)", min_values=1, max_values=1, options=[
                discord.SelectOption(label="Tous", value="all", default=(self.type_filter=="all")),
                discord.SelectOption(label="Préfixe", value="prefix", default=(self.type_filter=="prefix")),
                discord.SelectOption(label="Slash", value="slash", default=(self.type_filter=="slash")),
            ])

            async def on_type_change(inter: discord.Interaction):
                self.type_filter = inter.data.get("values", ["all"])[0]
                self.page = 0
                self._build_items()
                self._build_components()
                await self.refresh(inter)

            type_select.callback = on_type_change
            self.add_item(type_select)

            # Paged select of commands
            start, end = self._page_slice()
            page_items = self.items[start:end]
            options: List[discord.SelectOption] = []
            for t, name, summary in page_items[:25]:  # cap at 25 options
                label = f"/{name}" if t == "slash" else f"+{name}"
                desc = (summary or "").strip()
                options.append(discord.SelectOption(label=label[:100], description=desc[:100], value=f"{t}:{name}"))

            if not options:
                options.append(discord.SelectOption(label="Aucune commande trouvée", value="none", description="Modifie le filtre ou la recherche"))

            cmd_select = discord.ui.Select(placeholder="Sélectionnez une commande (+préfixe ou /slash)", options=options, min_values=1, max_values=1)

            async def on_select(inter: discord.Interaction):
                val = inter.data.get("values", ["none"])[0]
                if val == "none":
                    return await inter.response.defer()
                t, qname = val.split(":", 1)
                if t == "prefix":
                    cmd = self.cog.bot.get_command(qname)
                    if not cmd:
                        return await inter.response.send_message("Commande introuvable.", ephemeral=True)
                    emb = discord.Embed(title=f"📖 +{cmd.qualified_name}", description=command_details_prefix(cmd), color=discord.Color.blurple(), timestamp=datetime.now(timezone.utc))
                    await inter.response.edit_message(embed=emb, view=self)
                else:
                    # slash
                    try:
                        scmd = discord.utils.get(list(self.cog.bot.tree.walk_commands()), qualified_name=qname)
                    except Exception:
                        scmd = None
                    if not scmd:
                        return await inter.response.send_message("Commande introuvable.", ephemeral=True)
                    emb = discord.Embed(title=f"📖 /{scmd.qualified_name}", description=command_details_slash(scmd), color=discord.Color.green(), timestamp=datetime.now(timezone.utc))
                    await inter.response.edit_message(embed=emb, view=self)

            cmd_select.callback = on_select
            self.add_item(cmd_select)

            # Pagination buttons
            total_pages = max(1, (len(self.items) + self.per_page - 1) // self.per_page)

            prev_btn = discord.ui.Button(style=discord.ButtonStyle.secondary, label="Précédent", disabled=(self.page<=0))
            next_btn = discord.ui.Button(style=discord.ButtonStyle.secondary, label="Suivant", disabled=(self.page>=total_pages-1))
            refresh_btn = discord.ui.Button(style=discord.ButtonStyle.primary, label="Rafraîchir")

            async def on_prev(inter: discord.Interaction):
                self.page = max(0, self.page - 1)
                self._build_components()
                await self.refresh(inter)

            async def on_next(inter: discord.Interaction):
                self.page = min(total_pages - 1, self.page + 1)
                self._build_components()
                await self.refresh(inter)

            async def on_refresh(inter: discord.Interaction):
                self._build_items()
                self._build_components()
                await self.refresh(inter)

            prev_btn.callback = on_prev
            next_btn.callback = on_next
            refresh_btn.callback = on_refresh

            self.add_item(prev_btn)
            self.add_item(next_btn)
            self.add_item(refresh_btn)

        async def refresh(self, inter: discord.Interaction):
            await inter.response.edit_message(embed=self.cog.build_main_embed(self.query, self.type_filter, self.page, len(self.items), self.per_page), view=self)

    def build_main_embed(self, query: str, type_filter: str, page: int, total_items: int, per_page: int) -> discord.Embed:
        desc = [
            "Utilise le sélecteur pour filtrer et choisir une commande.",
            "- Tape `+aide <recherche> (slash ou prefix)` pour filtrer directement.",
            "- Préfixe: `+` • Slash: `/`",
        ]
        if query:
            desc.append(f"\nFiltre actif: `{query}`")
        if type_filter != "all":
            desc.append(f"\nFiltre type: `{type_filter}`")

        emb = discord.Embed(
            title="📖 Guide des commandes TokiBot",
            description="\n".join(desc),
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        emb.set_footer(text=f"Page {page+1} • Résultats: {total_items}")
        return emb

    @commands.command(name="aide")
    @is_staff_or_admin()
    async def aide(self, ctx: commands.Context, *, recherche: Optional[str] = None):
        view = self.HelpView(self, ctx, query=recherche or "")
        await ctx.send(embed=self.build_main_embed(recherche or "", "all", 0, len(view.items), view.per_page), view=view)


async def setup(bot):
    await bot.add_cog(Help(bot))
