import discord
import travus_bot_base as tbb  # TBB functions and classes.
from discord import app_commands
from discord.ext import commands  # For implementation of bot commands.


async def setup(bot: tbb.TravusBotBase) -> None:
    """Setup function ran when module is loaded."""
    await bot.add_cog(SpecialCog(bot))  # Add cog and command help info.
    bot.add_module(
        "Special",
        "[Travus](https://github.com/Travus):\n\tCommands",
        SpecialCog.usage,
        """This module includes various special commands, such as event and holiday commands, etc.""",
    )


async def teardown(bot: tbb.TravusBotBase) -> None:
    """Teardown function ran when module is unloaded."""
    await bot.remove_cog("SpecialCog")  # Remove cog and command help info.
    bot.remove_module("Special")
    bot.remove_command_help(SpecialCog)


class SpecialCog(commands.Cog):
    """Cog that holds special functionality."""

    def __init__(self, bot: tbb.TravusBotBase) -> None:
        """Initialization function loading the bot object for cog."""
        self.bot = bot

    @staticmethod
    def usage() -> str:
        """Returns the usage text."""
        return (
            "**How To Use The Special Module:**\nThis module holds miscellaneous special commands. For information "
            "on how to use the commands in this module, check their respective help entries."
        )

    @app_commands.command(name="holiday")
    @app_commands.guild_only()
    @tbb.required_config(["holiday_role_id"])
    async def holiday(self, interaction: discord.Interaction) -> None:
        """Receive the Peppermint Penguin role."""
        assert isinstance(interaction.user, discord.Member)
        guild = interaction.guild
        assert guild is not None
        role = guild.get_role(int(self.bot.config["holiday_role_id"]))
        if role is None:
            await interaction.response.send_message("The role could not be found.", ephemeral=True)
            return
        if role in interaction.user.roles:
            await interaction.response.send_message("You already have the role!", ephemeral=True)
            return
        await interaction.user.add_roles(role, reason="User used the holiday command.")
        await interaction.response.send_message("You now have the role.", ephemeral=True)

    @app_commands.command(name="grinch")
    @app_commands.guild_only()
    @tbb.required_config(["holiday_role_id"])
    async def grinch(self, interaction: discord.Interaction) -> None:
        """Remove the Peppermint Penguin role."""
        assert isinstance(interaction.user, discord.Member)
        guild = interaction.guild
        assert guild is not None
        role = guild.get_role(int(self.bot.config["holiday_role_id"]))
        if role is None:
            await interaction.response.send_message("The role could not be found.", ephemeral=True)
            return
        if role not in interaction.user.roles:
            await interaction.response.send_message("You do not have the role!", ephemeral=True)
            return
        await interaction.user.remove_roles(role, reason="User used the grinch command.")
        await interaction.response.send_message("You no longer have the role.", ephemeral=True)

    @app_commands.command(name="good-girl")
    async def good_girl(self, interaction: discord.Interaction) -> None:
        """Tell BernieBot she's a good bot."""
        await interaction.response.send_message("Yay! :relaxed:")

    @app_commands.command(name="summermode")
    @app_commands.guild_only()
    @tbb.required_config(["e3_role_id"])
    async def summermode(self, interaction: discord.Interaction) -> None:
        """Toggle the StrugglE3rs role."""
        assert isinstance(interaction.user, discord.Member)
        guild = interaction.guild
        assert guild is not None
        role = guild.get_role(int(self.bot.config["e3_role_id"]))
        if role is None:
            await interaction.response.send_message("The role could not be found.", ephemeral=True)
            return
        if role not in interaction.user.roles:
            await interaction.user.add_roles(role, reason="User used the summermode command.")
            await interaction.response.send_message("You now have the StrugglE3rs role. Enjoy!", ephemeral=True)
            return
        await interaction.user.remove_roles(role, reason="User used the summermode command.")
        await interaction.response.send_message("You now no longer have the StrugglE3rs role.", ephemeral=True)
