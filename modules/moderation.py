from io import StringIO
from typing import Optional, List

from discord import File, Forbidden, HTTPException, Member, Message, NotFound, TextChannel
from discord.ext import commands

import travus_bot_base as tbb


def setup(bot: tbb.TravusBotBase):
    """Setup function ran when module is loaded."""
    bot.add_cog(ModerationCog(bot))  # Add cog and command help info.
    bot.add_module("Moderation", "[Travus](https://github.com/Travus):\n\tCommands", ModerationCog.usage, """This module includes commands
                   helpful for moderation, such as retrieving info about users, mass-deleting messages, etc. This module is intended to be
                   used by moderators, and as such the commands in this section are locked behind permissions and/or roles.""")
    bot.add_command_help(ModerationCog.whois, "Moderation", {"perms": ["Manage Server"]}, ["Travus#8888", "118954681241174016"])
    bot.add_command_help(ModerationCog.purge, "Moderation", {"perms": ["Manage Messages"]}, ["50", "50 penguin_pen", "25 Travus#8888",
                                                                                             "25 bot_room BernieBot#4328"])


def teardown(bot: tbb.TravusBotBase):
    """Teardown function ran when module is unloaded."""
    bot.remove_cog("ModerationCog")  # Remove cog and command help info.
    bot.remove_module("Moderation")
    bot.remove_command_help(ModerationCog)


class ModerationCog(commands.Cog):
    """Cog that holds moderation functionality."""

    def __init__(self, bot: tbb.TravusBotBase):
        """Initialization function loading bot object for cog."""
        self.bot = bot

    @staticmethod
    def usage() -> str:
        """Returns the usage text."""
        return "For information on how to use the commands in this module, check their help entries."

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.command(name="whois", usage="<USER>")
    async def whois(self, ctx: commands.Context, user: Member):
        """Supplies information about a user on the server, such as join date, registration date, ID and similar."""
        pass

    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.command(name="purge", aliases=["prune"], usage="<AMOUNT> (CHANNEL) (USER)")
    async def purge(self, ctx: commands.Context, amount: int, channel: Optional[TextChannel], user: Optional[Member]):
        """This command can mass-delete messages. The bot will attempt to delete the past X messages from the current channel.
        If a channel is passed along then the bot will remove messages from that channel instead. If a user is passed along
        then among the X messages only messages by that user are deleted. The bot will generate a log of deleted messages and
        post it in the alerts channel."""
        def check_user(message: Message) -> bool:
            return message.author == user

        alert_id = 585588234499653663
        channel = channel or ctx.channel
        if channel.guild != ctx.guild:
            await ctx.send(f"The `{tbb.clean(ctx, channel.name)}` channel is not part of this server.")
            return
        if not channel.permissions_for(ctx.author).manage_messages:
            await ctx.send(f"You do not have permissions to delete messages in {tbb.clean(ctx, channel.name)}.")
            return
        text = ""
        deleted_messages: List[Message] = []
        try:
            if user is None:
                deleted_messages = await channel.purge(limit=amount)
            else:
                deleted_messages = await channel.purge(limit=amount, check=check_user)
            text += f"Messages deleted by {ctx.author.name}#{ctx.author.discriminator} ({ctx.author.id}) in " \
                   f"{ctx.channel.name} ({ctx.channel.id}) on {tbb.cur_time()}:\n\n"
        except (HTTPException, NotFound, Forbidden):
            await ctx.send("Something went wrong during deletion.\nPosting log of deleted messages.")
        finally:
            if len(deleted_messages) == 0:
                await ctx.send("Nothing to delete.")
                return
            for msg in deleted_messages:  # ToDo: Handle files.
                text += f"[{str(msg.created_at)[0:16]}] Message {msg.id} by {msg.author} ({msg.author.id}):\n{msg.clean_content}\n\n"
            try:
                alerts = self.bot.get_channel(alert_id) or await self.bot.fetch_channel(alert_id)
            except (HTTPException, NotFound, Forbidden):
                await ctx.send("Could not retrieve alerts channel.")
                return
            await alerts.send(content=f"Deletion log by {ctx.author.mention} from {ctx.channel.name}:",
                              file=File(StringIO(text), filename="Deletion log.txt"))
