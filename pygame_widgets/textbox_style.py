from dataclasses import dataclass

import pygame.freetype
from pygame.typing import ColorLike


@dataclass
class TextBoxStyle:
    color: ColorLike = (220, 220, 220)
    border_thickness: int = 3
    border_color: ColorLike = (0, 0, 0)
    radius: int = 0

    font_size: int = 20
    font: pygame.freetype.Font | None = None
    text_color: ColorLike = (0, 0, 0)

    cursor_width: int = 2
    cursor_color: ColorLike = (0, 0, 0)
    cursor_alpha: int = 63

    selection_color: ColorLike = (166, 210, 255)
    text_color_under_selection: ColorLike = (
        255,
        255,
        255,
    )

    placeholder_text_color: ColorLike = (10, 10, 10)

    read_only: bool = False
    tab_spaces: int = 4

    lines_per_scroll: int = 1
