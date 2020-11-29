from asyncio import Lock
from copy import copy
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional

import discord
from discord.ext import commands, tasks  # For implementation of bot commands.

import travus_bot_base as tbb  # TBB functions and classes.


def setup(bot: tbb.TravusBotBase):
    """Setup function ran when module is loaded."""
    bot.add_cog(UtilsCog(bot))  # Add cog and command help info.
    bot.add_module("Utils", "[Travus](https://github.com/Travus):\n\tCommands", UtilsCog.usage,
                   """This module includes various utility commands, such as setting server info, user count, setting
                   reminders, etc. There commands are meant for use by both regular users and moderators and the
                   commands are intended to provide some value, opposed to just give fun responses.""")
    bot.add_command_help(UtilsCog.usercount, "Utility", None, [""])
    bot.add_command_help(UtilsCog.guildinfo, "Utility", None, [""])
    bot.add_command_help(UtilsCog.remindme, "Utility", None, ["2h Check for a response", "2h30m Do the dishes"])


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
        self.reminders: Dict[Tuple[Optional[int], Optional[int], int], Tuple[datetime, str]] = {}
        self.reminder_lock: Lock = Lock()

        async def async_init(reminder_dict: Dict[Tuple[Optional[int], Optional[int], int], Tuple[datetime, str]]):
            """Runs the asynchronous part of the initialization."""
            async with self.bot.db.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("CREATE TABLE IF NOT EXISTS reminders(guild TEXT, channel TEXT, reminding_user "
                                       "TEXT NOT NULL, until TIMESTAMP NOT NULL, message TEXT NOT NULL)")
                reminders = await conn.fetch("SELECT * FROM reminders")
            async with self.reminder_lock:
                for reminder in reminders:
                    try:
                        guild = None if reminder["guild"] is None else int(reminder["guild"])
                        channel = None if reminder["channel"] is None else int(reminder["channel"])
                        reminding_user = int(reminder["reminding_user"])
                        reminder_dict[(guild, channel, reminding_user)] = (reminder["until"], reminder["message"])
                    except ValueError:
                        continue

        self.bot.loop.create_task(async_init(self.reminders))
        self.remind_sender.start()

    def cog_unload(self):
        """Function that stops the task when the cog unloads."""
        self.remind_sender.cancel()

    @staticmethod
    def usage() -> str:
        """Returns the usage text."""
        return ("**How To Use The Utils Module:**\nThis module holds miscellaneous utility commands. It has features "
                "such as getting information about the server, the amount of users in the server, setting reminders "
                "and more. For information on how to use the commands in this module, check their respective help "
                "entries.")

    @tasks.loop(minutes=1)
    async def remind_sender(self):
        """Function that checks if any reminders should be sent every minute, and sends them if so."""

        async def remove():
            """Remove a reminder."""
            del self.reminders[(guild_id, channel_id, user_id)]
            async with self.bot.db.acquire() as conn:
                if guild_id:
                    await conn.execute("DELETE FROM reminders WHERE guild = $1 AND channel = $2 "
                                       "AND reminding_user = $3 AND until = $4 AND message = $5", str(guild_id),
                                       str(channel_id), str(user_id), when, text)
                else:
                    await conn.execute("DELETE FROM reminders WHERE guild IS NULL AND channel IS NULL "
                                       "AND reminding_user = $1 AND until = $2 AND message = $3", str(user_id), when,
                                       text)

        if not self.bot.is_connected:
            return

        async with self.reminder_lock:
            for (guild_id, channel_id, user_id), (when, text) in copy(self.reminders).items():
                if when > datetime.utcnow():
                    continue
                user = self.bot.get_user(user_id)
                if user is None:
                    self.bot.log.warning(f"Could not retrieve user {user_id}.")
                    await remove()
                    continue
                if guild_id is None:
                    await user.send(f"Hey {user.mention}, you told me to remind you:\n"
                                    f"{tbb.clean_no_ctx(self.bot, None, text, False)}")
                    await remove()
                    continue
                guild = self.bot.get_guild(guild_id)
                if guild is None:
                    self.bot.log.warning(f"Could not retrieve guild {guild_id}.")
                    await remove()
                    continue
                channel = guild.get_channel(channel_id)
                if channel is None:
                    self.bot.log.warning(f"Could not retrieve channel {channel_id}.")
                    await remove()
                    continue
                user = guild.get_member(user.id)
                if user is None:
                    self.bot.log.warning(f"Could not retrieve member {user_id} from guild {guild_id}.")
                    await remove()
                    continue
                perms = channel.permissions_for(user)
                if not perms.send_messages:
                    self.bot.log.warning(f"Member {user_id} does not have sending permissions in channel {channel_id}.")
                    await remove()
                    continue
                await channel.send(f"Hey {user.mention}, you told me to remind you:\n"
                                   f"{tbb.clean_no_ctx(self.bot, guild, text, False)}")
                await remove()

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

    @commands.guild_only()
    @commands.command(name="serverinfo", aliases=["guildinfo"])
    async def guildinfo(self, ctx: commands.Context):
        """This command lets you see the server information of the current server. It returns various statistics such
        as id, owner, member count, boost state, and more."""
        members = 0
        bots = 0
        for member in ctx.guild.members:
            if not member.bot:
                members += 1
            else:
                bots += 1
        creation_time = ctx.guild.created_at.strftime('%b %d, %Y %I:%M %p UTC')

        embed = discord.Embed(colour=discord.Color(0x4a4a4a), timestamp=datetime.utcnow())
        embed.set_author(name=ctx.guild.name, icon_url=ctx.guild.icon_url)
        embed.set_thumbnail(url=ctx.guild.icon_url)
        embed.set_footer(text=ctx.message.author.display_name, icon_url=ctx.author.avatar_url)
        embed.add_field(name="Information", value=f"**Server ID**: {ctx.guild.id}\n"
                                                  f"**Server Owner**: {ctx.guild.owner.mention}\n"
                                                  f"**Creation Time**: {creation_time}\n"
                                                  f"**Boost Level**: {ctx.guild.premium_tier} "
                                                  f"({ctx.guild.premium_subscription_count} boosts)", inline=False)
        embed.add_field(name="Statistics", value=f"**Member Count**: {members} users, {bots} bots\n"
                                                 f"**Text Channels**: {len(ctx.guild.text_channels)}\n"
                                                 f"**Voice Channels**: {len(ctx.guild.voice_channels)}\n"
                                                 f"**Roles**: {len(ctx.guild.roles)}", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="remindme", aliases=["reminder"], usage="<TIME UNTIL REMINDER> <TEXT>")
    async def remindme(self, ctx: commands.Context, duration: str, *, text: str):
        """This command will make the bot post a message in the channel it is used after some period of time, with
        a given message. It is intended to make set reminders. The command works in both DMs and channels. The time
        until the reminder should go off should be given as a duration such as `12h`, where `w` is weeks, `d` is days,
        `h` is hours, `m` is minutes and `s` is seconds. More than 1 type of time can be supplied as such; `1d12h`.
        The bot checks every minute is a reminder should go off. The reminder will not be sent if you do not have
        sending permissions in the channel at the time of the reminder."""
        try:
            duration = datetime.utcnow() + timedelta(seconds=tbb.parse_time(duration, 1))
        except ValueError:
            await ctx.send("Invalid duration. Must be valid duration and at least 1 second.")
            return
        async with self.reminder_lock:
            (guild, guild_str) = (None, None) if ctx.guild is None else (ctx.guild.id, str(ctx.guild.id))
            (channel, channel_str) = (None, None) if ctx.guild is None else (ctx.channel.id, str(ctx.channel.id))
            (user, user_str) = (ctx.author.id, str(ctx.author.id))
            self.reminders[(guild, channel, user)] = (duration, text)
            async with self.bot.db.acquire() as conn:
                await conn.execute("INSERT INTO reminders VALUES ($1, $2, $3, $4, $5)",
                                   guild_str, channel_str, user_str, duration, text)
        await ctx.send(f"Ok, will do {ctx.author.mention}!")
