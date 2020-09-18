from discord.ext import commands

from bot.exts.evergreen.emojify.emojify_cog import Emojify


def setup(bot: commands.Bot) -> None:
    """Load Emojify cog."""
    bot.add_cog(Emojify(bot))
