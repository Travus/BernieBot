from asyncio import Lock
from datetime import datetime, timedelta
from io import BytesIO
from typing import Dict, List, Optional, Tuple

import discord.utils
from discord import Colour, Embed, File, Forbidden, HTTPException, Member, Message, NotFound, TextChannel
from discord.ext import commands, tasks

import travus_bot_base as tbb


async def setup(bot: tbb.TravusBotBase):
    """Setup function ran when module is loaded."""
    mutes_dict: Dict[Tuple[int, int], Optional[datetime]] = {}
    async with bot.db.acquire() as conn:
        async with conn.transaction():
            await conn.execute("CREATE TABLE IF NOT EXISTS mutes(guild TEXT NOT NULL, muted_user TEXT "
                               "NOT NULL, until TIMESTAMPTZ, PRIMARY KEY(guild, muted_user))")
        mutes = await conn.fetch("SELECT * FROM mutes")
        for mute in mutes:
            try:
                guild = int(mute["guild"])
                muted_user = int(mute["muted_user"])
                mutes_dict[(guild, muted_user)] = mute["until"]
            except ValueError:
                continue

    await bot.add_cog(ModerationCog(bot, mutes_dict))  # Add cog and command help info.
    bot.add_module("Moderation", "[Travus](https://github.com/Travus):\n\tCommands", ModerationCog.usage,
                   """This module includes commands helpful for moderation, such as retrieving info about users,
                   mass-deleting messages, etc. This module is intended to be used by moderators, and as such the
                   commands in this section are locked behind permissions and/or roles.""")
    bot.add_command_help(ModerationCog.whois, "Moderation", {"perms": ["Manage Server"]},
                         ["Travus#8888", "118954681241174016"])
    bot.add_command_help(ModerationCog.purge, "Moderation", {"perms": ["Manage Messages"]},
                         ["50", "50 penguin_pen", "25 Travus#8888", "25 bot_room BernieBot#4328"])
    bot.add_command_help(ModerationCog.mute, "Moderation", {"perms": ["Manage Roles"]},
                         ["Travus#8888", "Travus#8888 12h"])
    bot.add_command_help(ModerationCog.unmute, "Moderation", {"perms": ["Manage Roles"]}, ["Travus#8888"])


async def teardown(bot: tbb.TravusBotBase):
    """Teardown function ran when module is unloaded."""
    await bot.remove_cog("ModerationCog")  # Remove cog and command help info.
    bot.remove_module("Moderation")
    bot.remove_command_help(ModerationCog)


class ModerationCog(commands.Cog):
    """Cog that holds moderation functionality."""

    def __init__(self, bot: tbb.TravusBotBase, mutes_dict: Dict[Tuple[int, int], Optional[datetime]]):
        """Initialization function loading bot object for cog."""
        self.bot = bot
        self.mutes: Dict[Tuple[int, int], Optional[datetime]] = mutes_dict
        self.mute_lock: Lock = Lock()
        self.auto_unmuter.start()

    def cog_unload(self):
        """Function that stops the task when the cog unloads."""
        self.auto_unmuter.cancel()

    def _get_mute_role(self, member: Member) -> Optional[discord.Role]:
        """Returns the alarm role set in the config, if there is one. Otherwise returns None."""
        if "mute_role" not in self.bot.config:
            return None
        try:
            mute_role = int(self.bot.config["mute_role"])
            mute_role = member.guild.get_role(mute_role)
            return mute_role
        except ValueError:
            self.bot.log.warning(f"Invalid config for 'mute_role', should be int:  {self.bot.config['mute_role']}")
            self.bot.last_error = f"Invalid config for 'mute_role', should be int:  {self.bot.config['mute_role']}"
            return None

    def _get_alert_channel(self) -> Optional[TextChannel]:
        """Return the alarm channel set in te config, if there is one. Otherwise returns None."""
        if "alert_channel" not in self.bot.config:
            return None
        try:
            alert_channel = int(self.bot.config["alert_channel"])
            alert_channel = self.bot.get_channel(alert_channel)
            return alert_channel
        except ValueError:
            self.bot.log.warning(f"Invalid config for 'alert_channel', should be int: "
                                 f"{self.bot.config['alert_channel']}")
            self.bot.last_error = (f"Invalid config for 'alert_channel', should be int: "
                                   f"{self.bot.config['alert_channel']}")
            return None

    @staticmethod
    def usage() -> str:
        """Returns the usage text."""
        return ("**How To Use The Moderation Module:**\nThis module is meant for use by moderators. It has features "
                "such as muting users, seeing user information, mass deleting messages, and more. For information on "
                "how to use the commands in this module, check their respective help entries.")

    @commands.Cog.listener()
    async def on_member_join(self, member: Member):
        """Function that checks if joining members are supposed to be muted, to prevent re-joining to evade mutes."""
        if (member.guild.id, member.id) not in self.mutes:
            return

        mute_role = self._get_mute_role(member)
        if mute_role is None:
            return
        alert_channel = self._get_alert_channel()

        success = True
        try:
            await member.add_roles(mute_role)
        except (Forbidden, HTTPException):
            success = False

        if alert_channel:
            if success:
                await alert_channel.send(f"{member.mention} re-joined while muted! Re-muted user.")
            else:
                await alert_channel.send(f"{member.mention} re-joined while muted! **Failed to re-mute user!**")

    @tasks.loop(seconds=15)
    async def auto_unmuter(self):
        """Function that checks if any mutes have expired every 15 seconds, and unmutes if they are."""
        if not self.bot.is_connected:
            return

        alert_channel = self._get_alert_channel()

        async with self.mute_lock:
            for (guild_id, member_id), expiry in [((g, m), e) for (g, m), e in self.mutes.items()]:  # Loop over copy.
                if expiry is None or expiry > discord.utils.utcnow():
                    continue
                guild = self.bot.get_guild(guild_id)
                member = guild.get_member(member_id)
                if guild is None or member is None:
                    self.bot.log.warning(f"Could not retrieve member {member_id} from guild {guild_id}.")
                    continue

                mute_role = self._get_mute_role(member)
                if mute_role is None:
                    if "mute_role" in self.bot.config:
                        self.bot.log.warning(f"Could not retrieve mute role {self.bot.config['mute_role']}.")
                    continue

                try:
                    await member.remove_roles(mute_role)
                except Forbidden:
                    self.bot.log.warning(f"Could not unmute {member.name} in {member.guild.name}, missing permission.")
                    if alert_channel:
                        await alert_channel.send(f"Mute of {member.mention} expired. **Lacking permission to unmute!**")
                    continue
                except HTTPException as e:
                    self.bot.log.warning(f"Failed to unmute {member.name}: {e}")
                    if alert_channel:
                        await alert_channel.send(f"Mute of {member.mention} expired. **Failed to unmute!**")
                    continue
                del self.mutes[(guild.id, member.id)]
                async with self.bot.db.acquire() as conn:
                    await conn.execute("DELETE FROM mutes WHERE guild = $1 AND muted_user = $2",
                                       str(guild.id), str(member.id))
                if alert_channel:
                    await alert_channel.send(f"Mute of {member.mention} expired. User unmuted.")

    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.command(name="whois", usage="<USER>")
    async def whois(self, ctx: commands.Context, user: Member):
        """Supplies information about a user on the server, such as join date, registration date, ID and similar."""
        join_position = sorted(ctx.guild.members, key=lambda mem: mem.joined_at).index(user) + 1
        boost_date = None if user.premium_since is None else user.premium_since.strftime('%a, %b %d, %Y %I:%M %p')
        if boost_date is not None:
            boost_date = f"**Boosting:** {boost_date}"
        messages = 0
        last_message = None
        for channel in ctx.guild.text_channels:  # Count messages by user across all channels, remember newest.
            if not channel.permissions_for(channel.guild.me).read_message_history:
                continue
            async for message in channel.history(limit=10000, after=discord.utils.utcnow() - timedelta(hours=12)):
                if message.author == user:
                    messages += 1
                    if last_message is None or message.created_at > last_message.created_at:
                        last_message = message
        embed = Embed(colour=Colour(0x4a4a4a), description=f"**{user.mention}**", timestamp=discord.utils.utcnow())
        embed.set_thumbnail(url=user.display_avatar)
        embed.set_author(name=str(user), icon_url=user.display_avatar)
        embed.set_footer(text=ctx.author.name, icon_url=ctx.author.display_avatar)
        try:
            if self.mutes[(ctx.guild.id, user.id)] is None:
                muted = "Yes"
            else:
                muted = f"Until {self.mutes[(ctx.guild.id, user.id)].strftime('%b %d, %Y %I:%M %p UTC')}"
        except KeyError:
            muted = "No"
        embed.add_field(name="Information", value=f"**Name**: {user}\n**Nickname:**: {user.nick}\n**ID:** {user.id}\n"
                                                  f"**Profile Picture:** [Link]({user.display_avatar})\n"
                                                  f"**Status:** {user.status}\n**Muted:** {muted}\n**Bot:** "
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

        alert_channel = self._get_alert_channel()

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
            if alert_channel is None:
                return
            output = "".join(reversed(msg_log))
            await alert_channel.send(content=f"Deletion log by {ctx.author.mention} from {ctx.channel.name}:",
                                     file=File(BytesIO(output.encode()), filename="Deletion log.txt"))

    @tbb.required_config(("mute_role", ))
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.command(name="mute", usage="<USER> (DURATION)")
    async def mute(self, ctx: commands.Context, member: Member, duration: Optional[str]):
        """This command lets you mute a user for some period of time, or until unmuted. The mute duration should be
        given as a duration such as `12h`, where `w` is weeks, `d` is days, `h` is hours, `m` is minutes and `s` is
        seconds. More than 1 type of time can be supplied as such; `1d12h`. The bot checks every 15 seconds if a mute
        has expired, and unmutes if that is the case. Newer mutes overwrite older ones, and the `unmute` command cancels
        mutes outright."""
        if ctx.author.top_role <= member.top_role and ctx.author != ctx.guild.owner:
            await ctx.send("You can only mute members below you in the role hierarchy.")
            return

        mute_role = self._get_mute_role(member)
        if mute_role is None:
            await ctx.send(f"Could not retrieve mute role: {self.bot.config['mute_role']}")
            return
        alert_channel = self._get_alert_channel()

        if duration:
            try:
                duration = discord.utils.utcnow() + timedelta(seconds=tbb.parse_time(duration, 1))
            except ValueError:
                await ctx.send("Invalid duration. Must be valid duration and at least 1 second.")
                return
        try:
            await member.add_roles(mute_role)
        except Forbidden:
            await ctx.send("Lacking permission to assign mute role.")
            return
        async with self.mute_lock:
            self.mutes[(member.guild.id, member.id)] = duration
            async with self.bot.db.acquire() as conn:
                await conn.execute("INSERT INTO mutes VALUES ($1, $2, $3) ON CONFLICT (guild, muted_user) "
                                   "DO UPDATE SET until = $3", str(member.guild.id), str(member.id), duration)

        embed = Embed(colour=Colour(0x4a4a4a), description=f"{member.mention} was{' temporarily' if duration else ''} "
                                                           f"muted by {ctx.author.mention}!",
                      timestamp=(duration if duration else discord.utils.utcnow()))
        embed.set_author(name="Mute")
        embed.set_footer(text=("Muted Until" if duration else "Muted On"), icon_url=member.display_avatar)
        await ctx.send(embed=embed)
        if alert_channel and alert_channel != ctx.channel.id:
            await alert_channel.send(embed=embed)

    @tbb.required_config(("mute_role",))
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.command(name="unmute", usage="<USER>")
    async def unmute(self, ctx: commands.Context, member: Member):
        """This command lets you unmute a user. Unmuting a user will lift both temporary and permanent mutes."""
        if ctx.author.top_role <= member.top_role and ctx.author != ctx.guild.owner:
            await ctx.send("You can only unmute members below you in the role hierarchy.")
            return

        mute_role = self._get_mute_role(member)
        if mute_role is None:
            await ctx.send(f"Could not retrieve mute role: {self.bot.config['mute_role']}")
            return
        alert_channel = self._get_alert_channel()

        if (member.guild.id, member.id) not in self.mutes:
            await ctx.send("This user is not muted.")
            return
        try:
            await member.remove_roles(mute_role)
        except Forbidden:
            await ctx.send("Lacking permission to unmute.")
            return
        async with self.mute_lock:
            del self.mutes[(member.guild.id, member.id)]
            async with self.bot.db.acquire() as conn:
                await conn.execute("DELETE FROM mutes WHERE guild = $1 AND muted_user = $2",
                                   str(member.guild.id), str(member.id))
        embed = Embed(colour=Colour(0x4a4a4a), description=f"{member.mention} was unmuted by {ctx.author.mention}!",
                      timestamp=discord.utils.utcnow())
        embed.set_author(name="Unmute")
        embed.set_footer(text="Unmuted On", icon_url=member.display_avatar)
        await ctx.send(embed=embed)
        if alert_channel and alert_channel != ctx.channel.id:
            await alert_channel.send(embed=embed)
