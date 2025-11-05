import discord
from discord.ext import commands
import os
import sys
from utils.config import get_bot_config

_BOT_CFG = get_bot_config()
EXTRA_OWNER_IDS = set(_BOT_CFG.get("EXTRA_OWNER_IDS", []))

def is_owner_or_specific_user():
    async def predicate(ctx):
        try:
            if await ctx.bot.is_owner(ctx.author):
                return True
        except Exception:
            pass
        return ctx.author.id in EXTRA_OWNER_IDS
    return commands.check(predicate)

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Commande pour éteindre le bot
    @commands.command(name="off")
    @is_owner_or_specific_user()
    async def off(self, ctx):
        await ctx.send("🛑 Extinction du bot...")
        await self.bot.close()

    # Commande pour redémarrer le bot
    @commands.command(name="reboot")
    @is_owner_or_specific_user()
    async def reboot(self, ctx):
        await ctx.send("🔄 Redémarrage du bot...")
        await self.bot.close()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # Commande pour afficher l’état des cogs
    @commands.command(name="cogs")
    async def list_cogs(self, ctx):
        loaded = []
        unloaded = []

        # Parcourir récursivement ./cogs
        for root, _, files in os.walk("./cogs"):
            for file in files:
                if file.endswith(".py"):
                    rel_path = os.path.relpath(os.path.join(root, file), "./cogs")
                    cog_name = rel_path[:-3].replace(os.sep, ".")  # format dossier.sousdossier.fichier
                    full_name = f"cogs.{cog_name}"

                    if full_name in self.bot.extensions:
                        loaded.append(f"✅ {full_name}")
                    else:
                        unloaded.append(f"❌ {full_name}")

        if not loaded and not unloaded:
            await ctx.send("Aucun cog trouvé dans ./cogs")
            return

        message = ""
        if loaded:
            message += "**Cogs chargés :**\n" + "\n".join(loaded) + "\n\n"
        if unloaded:
            message += "**Cogs non chargés :**\n" + "\n".join(unloaded)

        await ctx.send(message)

    # Commande pour recharger un cog spécifique
    @commands.command(name="reload")
    @is_owner_or_specific_user()
    async def reload_cog(self, ctx, cog: str):
        """Recharge un cog (ex: +reload hello)"""
        try:
            await self.bot.reload_extension(f"cogs.{cog}")
            await ctx.send(f"🔁 Cog `{cog}` rechargé avec succès ✅")
        except commands.ExtensionNotLoaded:
            try:
                await self.bot.load_extension(f"cogs.{cog}")
                await ctx.send(f"✅ Cog `{cog}` chargé (il ne l’était pas avant)")
            except Exception as e:
                await ctx.send(f"❌ Impossible de charger `{cog}` : {e}")
        except Exception as e:
            await ctx.send(f"❌ Erreur lors du reload de `{cog}` : {e}")

async def setup(bot):
    await bot.add_cog(Admin(bot))