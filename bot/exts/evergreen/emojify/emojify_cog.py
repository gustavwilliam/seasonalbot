import io
import json
import logging
import os
import random
import urllib.request
from typing import Dict, List, Union

import discord
from PIL import Image
from discord import Colour, Embed, Guild, HTTPException
from discord.ext.commands import BadArgument, Cog, CommandError, Context, MissingRequiredArgument, command

from bot.constants import ERROR_REPLIES, NEGATIVE_REPLIES
from bot.exts.evergreen.emojify.constants import EMOJIS, REPO_IMG_URLS

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

    def __init__(self, name: str):
        self.name = name  # The emoji identifier used in fonts and files.

    def emoji_id(self, guild: Context.guild) -> Union[int, None]:
        """Returns the emoji's ID, relevant to the server the message was sent from."""
        return discord.utils.get(guild.emojis, name=self.guild_name(guild=guild)).id

    def emoji(self, guild: Guild) -> Union[str, None]:
        """
        Returns the text used to render the emoji on Discord.

        Example return value:
        `<:blank:754688893558718495>`
        """
        if (emoji_id := self.emoji_id(guild)) is not None:
            return f"<:{self.name}:{emoji_id}>"
        else:
            return None

    def guild_name(self, guild: Guild) -> str:
        """Name of emoji in specified guild."""
        return self.tileset.mappings[str(guild.id)][self.name]

    def load_image(self, force_reload: bool = False) -> None:
        """Retrieves emoji's png from GitHub."""
        if not os.path.isfile(self.image_path) or force_reload:
            urllib.request.urlretrieve(self.image_url, self.image_path)


class Tileset:
    """
    Contains all data about a tileset.

    Assigns itself as `tileset` property of the emojis passed in `emojis` at initialization.
    """

    def __init__(self, name: str, guild: Union[Guild, None] = None):
        self.name = name
        self.mappings: Dict[str, Dict[str, str]] = {}
        self.repo_img_url: str = REPO_IMG_URLS[self.name]
        self.emojis: Dict[str, Emoji] = {emoji_name: Emoji(name=emoji_name) for emoji_name in EMOJIS}

        for emoji in self.emojis.values():  # Set attributes for all child emojis.
            emoji.tileset: Tileset = self
            emoji.image_path: str = f"{os.path.dirname(__file__)}/tilesets/{self.name}/{emoji.name}.png"
            emoji.image_url: str = f"{self.repo_img_url}/dist/{emoji.name}.png"

        if guild:
            self.load_guild_mappings(guild=guild)

    def load_guild_mappings(self,
                            guild: Guild,
                            directory: str = f"{os.path.dirname(__file__)}/tileset_config/"
                            ) -> None:
        """
        Loads the tileset mappings.

        If no directory is specified, it looks for the configuration file in `./tileset_config/`. The mapping is
        relevant only to the specified guild (emojis have different IDs in different servers).
        """
        with open(f"{directory}{str(guild.id)}/{self.name}.json") as f:
            self.mappings[str(guild.id)] = json.load(f)

    def to_mapping(self, input_list: List[List[Emoji]], guild: Guild) -> List[List[str]]:
        """Converts an input list with emojis to a list using the guild mapping and returns it."""
        output: List[List[str]] = [[] for _ in range(len(input_list))]

        for row in range(len(input_list)):
            for emoji in input_list[row]:  # For the width of the character.
                output[row].append(self.emojis[emoji.name].emoji(guild=guild))

        return output

    @staticmethod
    def to_image(input_list: List[List[Emoji]]) -> Image.Image:
        """Converts an input list with emojis to an image and returns it."""
        tiles_wide: int = len(input_list[0])
        tiles_high: int = len(input_list)

        input_list[0][0].load_image()
        image = Image.open(input_list[0][0].image_path)
        tile_size = image.size[0]

        output = Image.new('RGBA', (tiles_wide*tile_size, tiles_high*tile_size), (0, 0, 0, 0))

        for row in range(len(input_list)):
            for col, emoji in enumerate(input_list[row]):
                emoji.load_image()
                image = Image.open(emoji.image_path)
                output.paste(image, (col*tile_size, row*tile_size))

        return output
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
    def _add_letter(emoji_list: List[List[Emoji]],
                    letter: str,
                    font: Font,
                    tileset: Tileset
                    ) -> None:
        """
        Adds the emojis needed to create the specified letter to `emoji_list`.

        Modifies the list passed as `emoji_list`.
        """
        for row in range(font.font_height):
            if not (letter_data := font.characters.get(letter)):  # If the letter can't be found in the font.
                raise BadArgument(f"The character `{letter}` is not supported by the font {font.name}")

            for piece in letter_data[row]:  # For the width of the character.
                emoji_list[row].append(tileset.emojis[piece])

    @staticmethod
    def _emojify(text: str, font: Font, tileset: Tileset) -> List[List[Emoji]]:
        """Returns a list of the emoji names corresponding to the input text."""
        letter_data: List[List[str]]
        emoji_list: List[List[Emoji]] = [[] for _ in range(font.font_height)]

        if font.lowercase_only:
            text = text.lower()

        for letter in text:
            Emojify._add_letter(emoji_list=emoji_list, letter=letter, font=font, tileset=tileset)

        return emoji_list
    # endregion

    # region: Commands
    @command(name='emojify', aliases=('emoji',), invoke_without_command=True)
    async def emojify_command(self, ctx: Context, tileset_name: str, *, text: str) -> None:
        """Command that responds with an emoji representation of the input string."""
        tileset = Tileset(name=tileset_name, guild=ctx.guild)
        output = Emojify._emojify(text=text, font=Font(name="rundi"), tileset=tileset)
        # await ctx.send(Emojify._flatten_list(tileset.to_mapping(input_list=output, guild=ctx.guild)))

        result = tileset.to_image(input_list=output)
        data = io.BytesIO()
        result.save(data, format='PNG')
        data.seek(0)
        file = discord.File(data, "output.png")
        await ctx.send(file=file)
    # endregion

    # region: Error handler
    @emojify_command.error
    async def command_error(self, ctx: Context, error: CommandError) -> None:
        """Local error handler for the emojify cog."""
        embed = Embed()
        embed.colour = Colour.red()
        embed.title = random.choice(NEGATIVE_REPLIES)

        actual_error = getattr(error, 'original', error)

        if isinstance(actual_error, FileNotFoundError):
            embed.description = "We can't seem to find that tileset/font."

        if isinstance(actual_error, BadArgument):
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
