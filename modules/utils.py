import random
import time
from asyncio import Lock
from copy import copy
from datetime import datetime, timedelta

import discord
import travus_bot_base as tbb  # TBB functions and classes.
from discord import app_commands
from discord.ext import commands, tasks  # For implementation of bot commands.


async def setup(bot: tbb.TravusBotBase):
    """Setup function ran when module is loaded."""
    random.seed(time.time())
    reminder_dict: dict[tuple[int | None, int | None, int], tuple[datetime, str]] = {}
    async with bot.db.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS reminders(guild TEXT, channel TEXT, reminding_user "
                "TEXT NOT NULL, until TIMESTAMPTZ NOT NULL, message TEXT NOT NULL)"
            )
        reminders = await conn.fetch("SELECT * FROM reminders")
        for reminder in reminders:
            try:
                guild = None if reminder["guild"] is None else int(reminder["guild"])
                channel = None if reminder["channel"] is None else int(reminder["channel"])
                reminding_user = int(reminder["reminding_user"])
                reminder_dict[(guild, channel, reminding_user)] = (reminder["until"], reminder["message"])
            except ValueError:
                continue

    await bot.add_cog(UtilsCog(bot, reminder_dict))  # Add cog and command help info.
    bot.add_module(
        "Utils",
        "[Travus](https://github.com/Travus):\n\tCommands",
        UtilsCog.usage,
        """This module includes various utility commands, such as setting server info, user count, setting
        reminders, etc. There commands are meant for use by both regular users and moderators and the
        commands are intended to provide some value, opposed to just give fun responses.""",
    )
    bot.add_command_help(UtilsCog.usercount, "Utility", None, [""])
    bot.add_command_help(UtilsCog.guildinfo, "Utility", None, [""])
    bot.add_command_help(UtilsCog.remindme, "Utility", None, ["2h Check for a response", "2h30m Do the dishes"])
    bot.add_command_help(UtilsCog.choose, "Utility", None, ["Option 1, Option 2, Option 3", "Heads, Tails"])


async def teardown(bot: tbb.TravusBotBase):
    """Teardown function ran when module is unloaded."""
    await bot.remove_cog("UtilsCog")  # Remove cog and command help info.
    bot.remove_module("Utils")
    bot.remove_command_help(UtilsCog)


class UtilsCog(commands.Cog):
    """Cog that holds utility functionality."""

    def __init__(
        self,
        bot: tbb.TravusBotBase,
        reminder_dict: dict[tuple[int | None, int | None, int], tuple[datetime, str]],
    ):
        """Initialization function loading the bot object and other variables for cog."""
        self.bot = bot
        self.reminders: dict[tuple[int | None, int | None, int], tuple[datetime, str]] = reminder_dict
        self.reminder_lock: Lock = Lock()
        self.remind_sender.start()

    async def cog_unload(self):
        """Function that stops the task when the cog unloads."""
        self.remind_sender.cancel()

    @staticmethod
    def usage() -> str:
        """Returns the usage text."""
        return (
            "**How To Use The Utils Module:**\nThis module holds miscellaneous utility commands. It has features "
            "such as getting information about the server, the amount of users in the server, setting reminders "
            "and more. For information on how to use the commands in this module, check their respective help "
            "entries."
        )

    @tasks.loop(minutes=1)
    async def remind_sender(self):
        """Function that checks if any reminders should be sent every minute, and sends them if so."""

        async def remove():
            """Remove a reminder."""
            del self.reminders[(guild_id, channel_id, user_id)]
            async with self.bot.db.acquire() as conn:
                if guild_id:
                    await conn.execute(
                        "DELETE FROM reminders WHERE guild = $1 AND channel = $2 "
                        "AND reminding_user = $3 AND until = $4 AND message = $5",
                        str(guild_id),
                        str(channel_id),
                        str(user_id),
                        when,
                        text,
                    )
                else:
                    await conn.execute(
                        "DELETE FROM reminders WHERE guild IS NULL AND channel IS NULL "
                        "AND reminding_user = $1 AND until = $2 AND message = $3",
                        str(user_id),
                        when,
                        text,
                    )

        if not self.bot.is_connected:
            return

        async with self.reminder_lock:
            for (guild_id, channel_id, user_id), (when, text) in copy(self.reminders).items():
                if when > discord.utils.utcnow():
                    continue
                user = self.bot.get_user(user_id)
                if user is None:
                    self.bot.log.warning(f"Could not retrieve user {user_id}.")
                    await remove()
                    continue
                if guild_id is None:
                    await user.send(
                        f"Hey {user.mention}, you told me to remind you:\n"
                        f"{tbb.clean_no_ctx(self.bot, None, text, False)}"
                    )
                    await remove()
                    continue
                guild = self.bot.get_guild(guild_id)
                if guild is None:
                    self.bot.log.warning(f"Could not retrieve guild {guild_id}.")
                    await remove()
                    continue
                assert channel_id is not None
                channel = guild.get_channel(channel_id)
                if not isinstance(
                    channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel, discord.StageChannel)
                ):
                    self.bot.log.warning(f"Could not retrieve channel {channel_id}.")
                    await remove()
                    continue
                member = guild.get_member(user.id)
                if member is None:
                    self.bot.log.warning(f"Could not retrieve member {user_id} from guild {guild_id}.")
                    await remove()
                    continue
                perms = channel.permissions_for(member)
                if not perms.send_messages:
                    self.bot.log.warning(f"Member {user_id} does not have sending permissions in channel {channel_id}.")
                    await remove()
                    continue
                await channel.send(
                    f"Hey {member.mention}, you told me to remind you:\n"
                    f"{tbb.clean_no_ctx(self.bot, guild, text, False)}"
                )
                await remove()

    def make_timestamp(self, timestamp: datetime) -> str:
        """Returns a discord timestamp with both absolute and relative time."""
        return f"<t:{int(timestamp.timestamp())}:f> (<t:{int(timestamp.timestamp())}:R>)"

    @commands.guild_only()
    @commands.command(name="usercount", aliases=["users"])
    async def usercount(self, ctx: commands.Context):
        """This command lets you see the amount of users in the server. It lists both regular users and bot users."""
        guild = ctx.guild
        assert guild is not None
        members = 0
        bots = 0
        for member in guild.members:
            if not member.bot:
                members += 1
            else:
                bots += 1

        embed = discord.Embed(colour=discord.Color(0x4A4A4A), timestamp=discord.utils.utcnow())
        embed.set_author(name=guild.name, icon_url=guild.icon)
        embed.set_footer(text=ctx.author.display_name, icon_url=ctx.author.display_avatar)
        embed.add_field(name="Members", value=f"{members}", inline=True)
        embed.add_field(name="Bots", value=f"{bots}", inline=True)
        await ctx.send(embed=embed)

    @commands.guild_only()
    @commands.command(name="serverinfo", aliases=["guildinfo"])
    async def guildinfo(self, ctx: commands.Context):
        """This command lets you see the server information of the current server. It returns various statistics such
        as id, owner, member count, boost state, and more."""
        guild = ctx.guild
        assert guild is not None
        members = 0
        bots = 0
        for member in guild.members:
            if not member.bot:
                members += 1
            else:
                bots += 1
        creation_time = guild.created_at.strftime("%b %d, %Y %I:%M %p UTC")
        owner_mention = guild.owner.mention if guild.owner is not None else "Unknown"

        embed = discord.Embed(colour=discord.Color(0x4A4A4A), timestamp=discord.utils.utcnow())
        embed.set_author(name=guild.name, icon_url=guild.icon)
        embed.set_thumbnail(url=guild.icon)
        embed.set_footer(text=ctx.author.display_name, icon_url=ctx.author.display_avatar)
        embed.add_field(
            name="Information",
            value=f"**Server ID**: {guild.id}\n"
            f"**Server Owner**: {owner_mention}\n"
            f"**Creation Time**: {creation_time}\n"
            f"**Boost Level**: {guild.premium_tier} "
            f"({guild.premium_subscription_count} boosts)",
            inline=False,
        )
        embed.add_field(
            name="Statistics",
            value=f"**Member Count**: {members} users, {bots} bots\n"
            f"**Text Channels**: {len(guild.text_channels)}\n"
            f"**Voice Channels**: {len(guild.voice_channels)}\n"
            f"**Roles**: {len(guild.roles)}",
            inline=False,
        )
        await ctx.send(embed=embed)

    @commands.command(name="remindme", aliases=["reminder"], usage="<TIME UNTIL REMINDER> <TEXT>")
    async def remindme(self, ctx: commands.Context, duration_str: str, *, text: str):
        """This command will make the bot post a message in the channel it is used after some period of time, with
        a given message. It is intended to make set reminders. The command works in both DMs and channels. The time
        until the reminder should go off should be given as a duration such as `12h`, where `w` is weeks, `d` is days,
        `h` is hours, `m` is minutes and `s` is seconds. More than 1 type of time can be supplied as such; `1d12h`.
        The bot checks every minute if a reminder should go off. The reminder will not be sent if you do not have
        sending permissions in the channel at the time of the reminder."""
        try:
            duration = discord.utils.utcnow() + timedelta(seconds=tbb.parse_time(duration_str, 1))
        except ValueError:
            await ctx.reply("Invalid duration. Must be valid duration and at least 1 second.", mention_author=False)
            return
        async with self.reminder_lock:
            guild, guild_str = (None, None) if ctx.guild is None else (ctx.guild.id, str(ctx.guild.id))
            channel, channel_str = (None, None) if ctx.guild is None else (ctx.channel.id, str(ctx.channel.id))
            user, user_str = (ctx.author.id, str(ctx.author.id))
            self.reminders[(guild, channel, user)] = (duration, text)
            async with self.bot.db.acquire() as conn:
                await conn.execute(
                    "INSERT INTO reminders VALUES ($1, $2, $3, $4, $5)",
                    guild_str,
                    channel_str,
                    user_str,
                    duration,
                    text,
                )
        await ctx.reply(f"Ok, I will remind you at {self.make_timestamp(duration)}!", mention_author=False)

    @commands.command(name="choose", usage="<OPTION>[,<OPTION>,...]")
    async def choose(self, ctx: commands.Context, *, options_str: str):
        """This command lets the bot pick a random option for you. It takes any amount of options separated by
        commas."""
        options = [elem.strip() for elem in options_str.split(",")]
        choice = random.choice(options)
        await ctx.reply(f"Random choice: {choice}", mention_author=False)

    @app_commands.command(name="archive")
    @app_commands.guild_only()
    @tbb.required_config(["archive_role_id"])
    async def archive(self, interaction: discord.Interaction) -> None:
        """Toggle the archive role."""
        assert isinstance(interaction.user, discord.Member)
        guild = interaction.guild
        assert guild is not None
        role = guild.get_role(int(self.bot.config["archive_role_id"]))
        if role is None:
            await interaction.response.send_message("The role could not be found.", ephemeral=True)
            return
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role, reason="User removed role using archive command.")
            await interaction.response.send_message("You no longer have access to archived channels.", ephemeral=True)
            return
        await interaction.user.add_roles(role, reason="User added role using archive command.")
        await interaction.response.send_message("You now have access to archived channels.", ephemeral=True)
