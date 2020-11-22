from datetime import datetime

import discord
from discord.ext import commands  # For implementation of bot commands.

import travus_bot_base as tbb  # TBB functions and classes.


def setup(bot: tbb.TravusBotBase):
    """Setup function ran when module is loaded."""
    bot.add_cog(UtilsCog(bot))  # Add cog and command help info.
    bot.add_module("Utils", "[Travus](https://github.com/Travus):\n\tCommands", UtilsCog.usage,
                   """This module includes various utility commands, such as setting server info, user count, setting
                   reminders, etc. There commands are meant for use by both regular users and moderators and the
                   commands are intended to provide some value, opposed to just give fun responses.""")
    bot.add_command_help(UtilsCog.usercount, "Utility", None, [""])


def teardown(bot: tbb.TravusBotBase):
    """Teardown function ran when module is unloaded."""
    bot.remove_cog("UtilsCog")  # Remove cog and command help info.
    bot.remove_module("Utils")
    bot.remove_command_help(UtilsCog)


class UtilsCog(commands.Cog):
    """Cog that holds utils functionality."""

    def __init__(self, bot: tbb.TravusBotBase):
        """Initialization function loading bot object for cog."""
        self.bot = bot

    @staticmethod
    def usage() -> str:
        """Returns the usage text."""
        return ("**How To Use The Utils Module:**\nThis module holds miscellaneous utility commands. It has features "
                "such as getting information about the server, the amount of users in the server, setting reminders "
                "and more. For information on how to use the commands in this module, check their respective help "
                "entries.")

    @commands.guild_only()
    @commands.command(name="usercount", aliases=["users"])
    async def usercount(self, ctx: commands.Context):
        """This command lets you see the amount of users in the server. It lists both regular users and bot users."""
        members = 0
        bots = 0
        for member in ctx.guild.members:
            if not member.bot:
                members += 1
            else:
                bots += 1

        embed = discord.Embed(colour=discord.Color(0x4a4a4a), timestamp=datetime.utcnow())
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon_url)
        embed.set_footer(text=ctx.message.author.display_name, icon_url=ctx.author.avatar_url)
        embed.add_field(name="Members", value=f"{members}", inline=True)
        embed.add_field(name="Bots", value=f"{bots}", inline=True)
        await ctx.send(embed=embed)
