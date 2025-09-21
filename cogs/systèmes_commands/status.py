# cogs/systèmes_commands/status.py
import discord
from discord.ext import commands

class Status(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        activity = discord.Activity(type=discord.ActivityType.watching, name="Calbusto et Tokita.")
        await self.bot.change_presence(status=discord.Status.online, activity=activity)
        print("[Status] Activité définie")

async def setup(bot):
    await bot.add_cog(Status(bot))