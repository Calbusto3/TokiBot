import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from colorama import Fore, Style, init
from keep_alive import keep_alive

keep_alive() 
# Init colorama (pour Windows)
init(autoreset=True)

# Charger les variables d'environnement
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Définir les intents
intents = discord.Intents.all()

# Créer le bot
bot = commands.Bot(command_prefix="+", intents=intents, help_command=None)

# Fonction récursive pour charger tous les cogs
async def load_cogs(bot, path="./cogs", parent="cogs"):
    for entry in os.listdir(path):
        full_path = os.path.join(path, entry)
        if os.path.isdir(full_path):
            # Si c'est un dossier, on l'appelle récursivement
            await load_cogs(bot, full_path, f"{parent}.{entry}")
        elif entry.endswith(".py"):
            cog_name = entry[:-3]
            full_cog_path = f"{parent}.{cog_name}"
            try:
                await bot.load_extension(full_cog_path)
                # Afficher le nombre de commandes dans le cog
                cog_instance = bot.get_cog(cog_name.capitalize())
                nb_commands = len(cog_instance.get_commands()) if cog_instance else "?"
                print(f"{Fore.GREEN}[COG] ✅ '{full_cog_path}' chargé avec succès ({nb_commands} commandes){Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}[COG] ❌ Erreur lors du chargement de '{full_cog_path}' : {e}{Style.RESET_ALL}")

# Charger les cogs et synchroniser les commandes slash
@bot.event
async def setup_hook():
    await load_cogs(bot)

    try:
        synced = await bot.tree.sync()  # Synchronisation globale
        print(f"{Fore.MAGENTA}[SYNC] ✅ {len(synced)} commandes synchronisées avec Discord{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[SYNC] ❌ Erreur lors de la synchronisation des commandes : {e}{Style.RESET_ALL}")

# Quand le bot est prêt
@bot.event
async def on_ready():
    print(f"{Fore.CYAN}🤖 Bot connecté en tant que {bot.user}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}🔹 Commandes préfixées : {len(bot.commands)}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}🔹 Commandes slash : {len(bot.tree.get_commands())}{Style.RESET_ALL}")

# Lancer le bot
bot.run(TOKEN)