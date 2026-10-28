import os
import functools
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import pygame
import pygame.freetype
from pygame.typing import ColorLike

from pygame_widgets.widget import MouseEvent, Signal, WidgetBase, WidgetHandler

Anchor = Literal[
    "topleft",
    "midtop",
    "topright",
    "midleft",
    "center",
    "midright",
    "bottomleft",
    "midbottom",
    "bottomright",
]

# TODO: align by group (image, text)


@functools.cache
def _default_font() -> pygame.freetype.Font:
    return pygame.freetype.Font(None)


@dataclass(frozen=True, kw_only=True, slots=True)
class ButtonStyle:
    # Background
    color: ColorLike = (150, 150, 150)
    hover_color: ColorLike = (125, 125, 125)
    pressed_color: ColorLike = (100, 100, 100)
    disabled_color: ColorLike = (180, 180, 180)
    # Border
    border_width: int = 0
    border_radius: int = 0
    border_color: ColorLike = (0, 0, 0)
    hover_border_color: ColorLike = (80, 80, 80)
    pressed_border_color: ColorLike = (100, 100, 100)
    disabled_border_color: ColorLike = (0, 0, 0)
    # Shadow
    shadow_offset: int = 0
    shadow_color: ColorLike = (210, 210, 180)
    # Content
    padding: int = 0
    font: pygame.freetype.Font | None = None
    font_size: int = 20
    text_color: ColorLike = (0, 0, 0)
    disabled_text_color: ColorLike = (120, 120, 120)
    text_anchor: Anchor = "center"
    image_anchor: Anchor = "center"


class Button(WidgetBase):
    def __init__(
        self,
        surface: pygame.Surface,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        text: str = "",
        image: pygame.Surface | str | os.PathLike | None = None,
        style: ButtonStyle | None = None,
        on_click: Callable[[], None] | None = None,
        is_sub_widget: bool = False,
    ):
        super().__init__(surface, x, y, width, height, is_sub_widget)

        self._text = text
        self._image = image
        self._style = style if style is not None else ButtonStyle()

        self._text_surface: pygame.Surface
        self._disabled_text_surface: pygame.Surface
        self._render_text()

        self._pressed = False

        self.pressed = Signal()
        self.released = Signal()
        self.clicked = Signal()
        if on_click is not None:
            self.clicked.connect(on_click)

    @property
    def text(self) -> str:
        return self._text

    @text.setter
    def text(self, value: str) -> None:
        self._text = value
        self._render_text()

    @property
    def image(self) -> pygame.Surface | None:
        return self._image

    @image.setter
    def image(self, value: pygame.Surface | None) -> None:
        if isinstance(value, (str, os.PathLike)):
            value = pygame.image.load(value).convert_alpha()
        self._image = value

    @property
    def style(self) -> ButtonStyle:
        return self._style

    @style.setter
    def style(self, value: ButtonStyle) -> None:
        self._style = value
        self._render_text()

    def _render_text(self) -> None:
        font = self._style.font if self._style.font is not None else _default_font()
        self._text_surface, _ = font.render(
            self._text, self._style.text_color, size=self._style.font_size
        )
        self._disabled_text_surface, _ = font.render(
            self._text, self._style.disabled_text_color, size=self._style.font_size
        )

    def _place(self, size: tuple[float, float], anchor: Anchor) -> pygame.FRect:
        content = self._rect.inflate(-2 * self._style.padding, -2 * self._style.padding)
        rect = pygame.FRect((0, 0), size)
        setattr(rect, anchor, getattr(content, anchor))
        return rect

    def on_mouse_down(self, event: MouseEvent) -> None:
        self._pressed = event.button == 1
        if self._pressed:
            self.pressed.emit()

    def on_mouse_up(self, event: MouseEvent) -> None:
        if event.button != 1 or not self._pressed:
            return
        self._pressed = False
        self.released.emit()
        if self.is_hovered():
            self.clicked.emit()

    def _is_pressed(self) -> bool:
        return self._pressed and WidgetHandler.get_captured() is self

    def _colors(self) -> tuple[ColorLike, ColorLike]:
        if not self.is_enabled():
            return self._style.disabled_color, self._style.disabled_border_color
        if self.is_hovered():
            if self._is_pressed():
                return self._style.pressed_color, self._style.pressed_border_color
            return self._style.hover_color, self._style.hover_border_color
        return self._style.color, self._style.border_color

    def draw(self):
        if self._style.shadow_offset != 0:
            pygame.draw.rect(
                self.surface,
                self._style.shadow_color,
                (
                    self.x + self._style.shadow_offset,
                    self.y + self._style.shadow_offset,
                    self.width,
                    self.height,
                ),
                border_radius=self._style.border_radius,
            )

        color, border_color = self._colors()
        pygame.draw.rect(
            self.surface,
            color,
            (
                self.x,
                self.y,
                self.width,
                self.height,
            ),
            border_radius=self._style.border_radius,
        )

        if self._style.border_width > 0:
            pygame.draw.rect(
                self.surface,
                border_color,
                (self.x, self.y, self.width, self.height),
                width=self._style.border_width,
                border_radius=self._style.border_radius,
            )

        if self._image is not None:
            self.surface.blit(
                self._image,
                self._place(self._image.get_size(), self._style.image_anchor),
            )

        text_surface = (
            self._text_surface if self.is_enabled() else self._disabled_text_surface
        )
        self.surface.blit(
            text_surface,
            self._place(text_surface.get_size(), self._style.text_anchor),
        )
