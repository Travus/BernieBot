from datetime import datetime, timedelta
from io import StringIO
from typing import Dict, List, Optional

import discord.utils
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
    bot.add_command_help(ModerationCog.mute, "moderation", {"perms": ["Manage Roles"]},
                         ["Travus#8888", "Travus#8888 12h"])


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
        self.mutes: Dict[Member, Optional[datetime]] = {}

        async def async_init(mutes_dict: Dict[Member, Optional[datetime]]):
            """Runs the asynchronous part of the initialization."""
            async with self.bot.db.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("CREATE TABLE IF NOT EXISTS mutes(guild TEXT NOT NULL, muted_user TEXT "
                                       "NOT NULL, until TIMESTAMP, PRIMARY KEY(guild, muted_user))")
                mutes = await conn.fetch("SELECT * FROM mutes")
            for mute in mutes:
                guild = bot.get_guild(int(mute["guild"]))
                if guild is not None:
                    muted_user = guild.get_member(int(mute["muted_user"]))
                    if muted_user:
                        mutes_dict[muted_user] = mute["until"]

        self.bot.loop.create_task(async_init(self.mutes))

    @staticmethod
    def usage() -> str:
        """Returns the usage text."""
        return ("**How To Use The Moderation Module:**\nThis module is meant for use by moderators. It has features "
                "such as muting users, seeing user information, mass deleting messages, and more. For information on "
                "how to use the commands in this module, check their respective help entries.")

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

    @tbb.required_config(("alert_channel", ))
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

        try:
            alert_channel = int(self.bot.config["alert_channel"])
        except ValueError:
            raise ValueError(f"Invalid config for 'alert_channel', should be int:  {self.bot.config['alert_channel']}")

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
                alerts = self.bot.get_channel(alert_channel) or await self.bot.fetch_channel(alert_channel)
            except (HTTPException, NotFound, Forbidden):
                await ctx.send("Could not retrieve alerts channel.")
                return
            output = "".join(reversed(msg_log))
            await alerts.send(content=f"Deletion log by {ctx.author.mention} from {ctx.channel.name}:",
                              file=File(StringIO(output), filename="Deletion log.txt"))

    @tbb.required_config(("mute_role", ))
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.command(name="mute", usage="<USER> (DURATION)")
    async def mute(self, ctx: commands.Context, user: Member, duration: Optional[str]):
        """This command lets you mute a user for some period of time, or until unmuted. The mute duration should be
        given as a duration such as `12h`, where `w` is weeks, `d` is days, `h` is hours, `m` is minutes and `s` is
        seconds. More than 1 type of time can be supplied as such; `1d12h`. The bot checks every minute if a mute has
        expired, and unmutes if that is the case. Newer mutes overwrite older ones, and the `unmute` command cancels
        mutes outright."""
        if ctx.author.top_role <= user.top_role and ctx.author != ctx.guild.owner:
            await ctx.send("You can only mute members below you in the role hierarchy.")
            return

        try:
            mute_role = int(self.bot.config["mute_role"])
        except ValueError:
            raise ValueError(f"Invalid config for 'mute_role', should be int:  {self.bot.config['mute_role']}")
        mute_role = discord.utils.get(ctx.guild.roles, id=mute_role)
        if mute_role is None:
            await ctx.send("Could not retrieve mute role.")

        if duration:
            try:
                duration = datetime.utcnow() + timedelta(seconds=tbb.parse_time(duration, 1))
            except ValueError:
                await ctx.send("Invalid duration. Must be valid duration and at least 1 second.")
                return
        try:
            await user.add_roles(mute_role)
        except Forbidden:
            await ctx.send("Lacking permission to assign mute role.")
            return
        self.mutes[user] = duration
        async with self.bot.db.acquire() as conn:
            await conn.execute("INSERT INTO mutes VALUES ($1, $2, $3) ON CONFLICT (guild, muted_user) "
                               "DO UPDATE SET until = $3", str(ctx.guild.id), str(user.id), duration)

        embed = Embed(colour=Colour(0x4a4a4a), description=f"{user.mention} was{' temporarily' if duration else ''} "
                                                           f"muted by {ctx.author.mention}!",
                      timestamp=(duration if duration else datetime.utcnow()))
        embed.set_author(name="Mute")
        embed.set_footer(text=("Muted Until" if duration else "Muted On"), icon_url=user.avatar_url)
        await ctx.send(embed=embed)
