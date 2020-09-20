import json
import logging
import os
import random
from typing import Dict, List, Union

import discord
from discord import Colour, Embed, HTTPException
from discord.ext.commands import BadArgument, Cog, CommandError, Context, MissingRequiredArgument, command

from bot.constants import ERROR_REPLIES, NEGATIVE_REPLIES

log = logging.getLogger(__name__)


# region: Custom Exceptions
class IncompleteConfigurationError(Exception):
    """Exception raised when custom configuration files don't include the required data."""

    pass
# endregion


# region: Helper classes
class Font:
    """Contains all data about a font."""

    def __init__(self, name: str):
        self.name: str = name
        self.load()

    def load(self, directory: str = f"{os.path.dirname(__file__)}/fonts/") -> None:
        """
        Adds font data to the font instance.

        If no directory is specified, it looks for the font file in `./fonts/`.
        """
        with open(f"{directory}{self.name}.json") as f:
            data = json.load(f)
            self.__dict__.update(data)


class Emoji:
    """Contains all data about an emoji."""

    def __init__(self, name: str, guild: Context.guild):
        self.name = name
        self.guild = guild

    @property
    def id(self) -> Union[int, None]:
        """Returns the emoji's ID, relevant to the server the message was sent from."""
        return discord.utils.get(self.guild.emojis, name=self.name).id

    @property
    def emoji(self) -> Union[str, None]:
        """
        Returns the text used to render the emoji on Discord.

        Example return value:
        `<:blank:754688893558718495>`
        """
        if (emoji_id := self.id) is not None:
            return f"<:{self.name}:{emoji_id}>"
        else:
            return None
# endregion


class Emojify(Cog):
    """Commands for turning text into their emoji representation."""

    # region: Helper methods
    @staticmethod
    def _flatten_list(input_list: list) -> str:
        """
        Flattens a list and returns its string representation.

        Adds newline after every flattened sublist.
        """
        output = []
        for element in input_list:
            if type(element) == list:
                output.extend(Emojify._flatten_list(element))
                output.extend("\n")
            else:
                output.append(element)

        return "".join(output)

    @staticmethod
    def _tileset(tileset_name: str,
                 guild: Context.guild,
                 directory: str = f"{os.path.dirname(__file__)}/tileset_config/"
                 ) -> Dict[str, Emoji]:
        """
        Returns dict with tileset mappings to `Emoji` objects, of the specified tileset.

        If no directory is specified, it looks for the configuration file in `./tileset_config/`. The mapping is
        relevant only to the specified guild (emojis have different IDs in different servers).
        """
        with open(f"{directory}{tileset_name}.json") as f:
            emojis = json.load(f)
            return {key: Emoji(name=name, guild=guild) for (key, name) in emojis.items()}

    @staticmethod
    def _get_tileset_configs(guild: Context.guild,
                             directory: str = f"{os.path.dirname(__file__)}/tileset_config/"
                             ) -> Dict[str, Dict[str, Emoji]]:
        """
        Returns dict with all tileset mappings to `Emoji` objects available in the specified directory.

        If no directory is specified, it looks for the configuration files in `./tileset_config/`. The mappings are
        relevant only to the specified guild (emojis have different IDs in different servers).
        """
        tilesets: Dict[str, Dict[str, Emoji]] = {}

        for file_path in os.listdir(directory):
            tileset_name = file_path.split(".")[0]
            tilesets[tileset_name] = Emojify._tileset(tileset_name=tileset_name, guild=guild)

        return tilesets

    @staticmethod
    def _add_letter(emoji_list: List[List[str]],
                    letter: str,
                    font: Font,
                    mapping: Dict[str, Emoji]
                    ) -> None:
        """
        Adds the emojis needed to create the specified letter to `emoji_list`.

        Modifies the list passed as `emoji_list`.
        """
        for row in range(font.font_height):
            if not (letter_data := font.characters.get(letter)):  # If the letter can't be found in the font.
                raise BadArgument(f"The character `{letter}` is not supported by the font {font.name}")
            for col in range(len(letter_data[0])):
                if not (emoji_map := mapping.get(letter_data[row][col])):  # If mapping doesn't support the emoji used.
                    raise IncompleteConfigurationError(f"The tileset configuration file for '{font.name}' does not "
                                                       f"specify a mapping for the emoji '{letter_data[row][col]}'.")
                emoji_list[row].append(f"{emoji_map.emoji}")
    # endregion

    # region: Commands
    @command(name='emojify', aliases=('emoji',), invoke_without_command=True)
    async def emojify(self, ctx: Context, tileset: str, *, text: str) -> None:
        """
        Command that responds with an emoji representation of the input string.

        Defaults to the font 'Rundi'.
        """
        font = Font("rundi")
        letter_data: List[List[str]]
        tileset_mapping: Dict[str, Emoji] = self._tileset(tileset_name=tileset, guild=ctx.guild)
        emoji_array: List[List[str]] = [[] for _ in range(font.font_height)]

        if font.lowercase_only:
            text = text.lower()

        for letter in text:
            self._add_letter(emoji_list=emoji_array, letter=letter, font=font, mapping=tileset_mapping)

        emoji_str = self._flatten_list(emoji_array)
        await ctx.send(emoji_str)
    # endregion

    # region: Error handler
    @emojify.error
    async def command_error(self, ctx: Context, error: CommandError) -> None:
        """Local error handler for the emojify cog."""
        embed = Embed()
        embed.colour = Colour.red()
        embed.title = random.choice(NEGATIVE_REPLIES)

        actual_error = getattr(error, 'original', error)

        if isinstance(actual_error, FileNotFoundError):
            embed.description = "We can't seem to find that tileset/font."

        elif isinstance(actual_error, BadArgument):
            embed.description = str(error)

        elif isinstance(actual_error, IncompleteConfigurationError):
            log.warning(error)
            embed.title = random.choice(ERROR_REPLIES)
            embed.description = "We can't seem to find the required emojis. Sorry for the inconvenience."

        elif isinstance(actual_error, HTTPException) and "Must be 2000 or fewer in length." in actual_error.text:
            embed.description = "That message is far too long to be sent using emojis."

        elif isinstance(actual_error, MissingRequiredArgument):
            await ctx.send_help(ctx.command)
            return

        else:
            log.error(f"Unhandled tag command error: {error}")
            return

        await ctx.send(embed=embed)
    # endregion
