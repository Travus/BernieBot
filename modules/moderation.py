from datetime import datetime, timedelta
from io import StringIO
from typing import Optional, List

from discord import Colour, Embed, File, Forbidden, HTTPException, Member, Message, NotFound, TextChannel
from discord.ext import commands

import travus_bot_base as tbb


def setup(bot: tbb.TravusBotBase):
    """Setup function ran when module is loaded."""
    bot.add_cog(ModerationCog(bot))  # Add cog and command help info.
    bot.add_module("Moderation", "[Travus](https://github.com/Travus):\n\tCommands", ModerationCog.usage,
                   """This module includes commands helpful for moderation, such as retrieving info about users, 
                   mass-deleting messages, etc. This module is intended to be used by moderators, and as such the 
                   commands in this section are locked behind permissions and/or roles.""")
    bot.add_command_help(ModerationCog.whois, "Moderation", {"perms": ["Manage Server"]},
                         ["Travus#8888", "118954681241174016"])
    bot.add_command_help(ModerationCog.purge, "Moderation", {"perms": ["Manage Messages"]},
                         ["50", "50 penguin_pen", "25 Travus#8888", "25 bot_room BernieBot#4328"])


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
    async def whois(self, ctx: commands.Context, user):
        """Supplies information about a user on the server, such as join date, registration date, ID and similar."""
        try:
            user = await commands.MemberConverter().convert(ctx, user)
        except commands.BadArgument:
            await ctx.send("Could not find matching member.")
            return
        join_position = sorted(ctx.guild.members, key=lambda mem: mem.joined_at).index(user) + 1
        boost_date = None if user.premium_since is None else user.premium_since.strftime('%a, %b %d, %Y %I:%M %p')
        if boost_date is not None:
            boost_date = f"**Boosting:** {boost_date}"
        messages = 0
        last_message = None
        for channel in ctx.guild.text_channels:  # Count messages by user across all channels, remember newest.
            if not channel.guild.me.permissions_in(channel).read_message_history:
                continue
            async for message in channel.history(limit=10000, after=datetime.utcnow() - timedelta(hours=12)):
                if message.author == user:
                    messages += 1
                    if last_message is None or message.created_at > last_message.created_at:
                        last_message = message
        embed = Embed(colour=Colour(0x4a4a4a), description=f"**{user.mention}**", timestamp=datetime.utcnow())
        embed.set_thumbnail(url=user.avatar_url)
        embed.set_author(name=str(user), icon_url=user.avatar_url)
        embed.set_footer(text=ctx.author.name, icon_url=ctx.author.avatar_url)
        embed.add_field(name="Information", value=f"**Name**: {user}\n**Nickname:**: {user.nick}\n**ID:** {user.id}\n"
                                                  f"**Profile Picture:** [Link]({user.avatar_url})\n"
                                                  f"**Status:** {user.status}\n**Bot:** "
                                                  f"{'Yes' if user.bot else 'No'}\n", inline=False)
        embed.add_field(name="Dates", value=f"**Registered:** {user.created_at.strftime('%a, %b %d, %Y %I:%M %p')}\n"
                                            f"**Joined:** {user.joined_at.strftime('%a, %b %d, %Y %I:%M %p')}\n"
                                            f"**Join Position:** {join_position}\n"
                                            f"{'' if boost_date is None else boost_date}", inline=False)
        role_mentions = [role.mention if role.name != '@everyone' else role.name for role in user.roles]
        embed.add_field(name="Roles", value=", ".join(role_mentions), inline=False)
        embed.add_field(name="Last Message", value="None in 12 hours!" if last_message is None
                        else f"In {last_message.channel.mention}\nAt {str(last_message.created_at)[0:16]}"
                        f"\n[Link To Message]({last_message.jump_url})", inline=True)
        embed.add_field(name="Messages Last 12H", value=f"{messages} messages", inline=True)
        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.command(name="purge", aliases=["prune"], usage="<AMOUNT> (CHANNEL) (USER)")
    async def purge(self, ctx: commands.Context, amount: int, channel: Optional[TextChannel], user: Optional[Member]):
        """This command can mass-delete messages. The bot will attempt to delete the past X messages from the current
        channel. If a channel is passed along then the bot will remove messages from that channel instead. If a user
        is passed along then among the X messages only messages by that user are deleted. The bot will generate a log
        of deleted messages and post it in the alerts channel."""

        def check_user(message: Message) -> bool:
            return message.author == user

        alert_id = 353246496952418305
        channel = channel or ctx.channel
        if channel.guild != ctx.guild:
            await ctx.send(f"The `{tbb.clean(ctx, channel.name)}` channel is not part of this server.")
            return
        if not channel.permissions_for(ctx.author).manage_messages:
            await ctx.send(f"You do not have permissions to delete messages in {tbb.clean(ctx, channel.name)}.")
            return
        deleted_messages: List[Message] = []
        try:
            if user is None:
                deleted_messages = await channel.purge(limit=amount)
            else:
                deleted_messages = await channel.purge(limit=amount, check=check_user)
        except (HTTPException, NotFound, Forbidden):
            await ctx.send("Something went wrong during deletion.\nPosting log of deleted messages.")
        finally:
            if len(deleted_messages) == 0:
                await ctx.send("Nothing to delete.")
                return
            msg_log = []
            for msg in deleted_messages:
                msg_time = f"[{str(msg.edited_at)[0:16]} (edit)]" if msg.edited_at else f"[{str(msg.created_at)[0:16]}]"
                text = f"{msg_time} Message {msg.id} by {msg.author} ({msg.author.id}):\n"
                text += (msg.clean_content or "NO TEXT CONTENT IN MESSAGE.") + "\n\n"
                if msg.attachments:
                    attachments = "\n".join([attachment.proxy_url for attachment in msg.attachments])
                    text += f"Attachments:\n{attachments}\n\n"
                msg_log.append(text)
            header = f"Messages deleted by {ctx.author.name} ({ctx.author.id}) in {ctx.channel.name} " \
                     f"({ctx.channel.id}) on {tbb.cur_time()}:\n\n"
            msg_log.append(header)
            try:
                alerts = self.bot.get_channel(alert_id) or await self.bot.fetch_channel(alert_id)
            except (HTTPException, NotFound, Forbidden):
                await ctx.send("Could not retrieve alerts channel.")
                return
            output = "".join(reversed(msg_log))
            await alerts.send(content=f"Deletion log by {ctx.author.mention} from {ctx.channel.name}:",
                              file=File(StringIO(output), filename="Deletion log.txt"))
