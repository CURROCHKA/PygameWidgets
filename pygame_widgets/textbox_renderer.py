from collections import OrderedDict
from dataclasses import dataclass

import pygame.freetype
from pygame.typing import ColorLike

from pygame_widgets.textbox_layout import VisualLine
from pygame_widgets.textbox_style import TextBoxStyle


@dataclass(frozen=True)
class TextBoxRenderState:
    """Everything TextBoxRenderer needs for one frame. Built fresh by TextBox
    each call to draw() — never stored, never mutated by the renderer."""

    # Geometry
    x: int
    y: int
    width: int
    height: int
    actual_x: int
    actual_y: int
    line_height: int
    max_visible_lines: int
    first_visible_line_index: int

    # Appearance
    style: TextBoxStyle
    font: pygame.freetype.Font

    # Content — placeholder-vs-real already resolved by the caller
    display_lines: list[VisualLine]
    display_color: ColorLike
    logical_line_lengths: list[int]
    space_width: int  # width of " " in the current font/style

    # Selection: normalized (start_line, start_col), (end_line, end_col), or None if empty
    selection: tuple[tuple[int, int], tuple[int, int]] | None

    # Cursor
    show_cursor: bool  # already resolved as "widget is focused AND blink-on"
    overwrite_mode: bool
    cursor_visual_line_index: int
    cursor_column: int
    cursor_char: str  # character to paint under an overwrite-mode cursor


class TextBoxRenderer:
    """Pure drawer. No reference to TextBox or TextBuffer — only its own
    glyph-surface cache, which is a rendering concern, not a text-model one.
    A single instance can safely be shared across multiple TextBox widgets.
    """

    RENDER_CACHE_SIZE = 500

    def __init__(self, render_cache_size: int = RENDER_CACHE_SIZE) -> None:
        self._rendered_text_cache: OrderedDict = OrderedDict()
        self._render_cache_size = render_cache_size

    def _visible_range(self, state: TextBoxRenderState) -> range:
        return range(
            state.first_visible_line_index,
            min(
                state.first_visible_line_index + state.max_visible_lines,
                len(state.display_lines),
            ),
        )

    def draw(self, surface: pygame.Surface, state: TextBoxRenderState) -> None:
        self._draw_border(surface, state)
        self._draw_background(surface, state)
        self._draw_selection(surface, state)
        self._draw_text(surface, state)
        self._draw_cursor(surface, state)

    def _get_rendered_text_surface(
        self,
        state: TextBoxRenderState,
        text: str,
        color: ColorLike,
        style: int = 0,
    ) -> pygame.Surface:
        cache_key = (id(state.font), text, color, style)

        if cache_key in self._rendered_text_cache:
            self._rendered_text_cache.move_to_end(cache_key)
            return self._rendered_text_cache[cache_key]

        if len(self._rendered_text_cache) >= self._render_cache_size:
            self._rendered_text_cache.popitem(last=False)

        rendered = state.font.render(text, fgcolor=color, style=style)[0]
        self._rendered_text_cache[cache_key] = rendered
        return rendered

    def _draw_border(self, surface: pygame.Surface, state: TextBoxRenderState) -> None:
        pygame.draw.rect(
            surface,
            state.style.border_color,
            (state.x, state.y, state.width, state.height),
            border_radius=state.style.radius,
        )

    def _draw_background(
        self, surface: pygame.Surface, state: TextBoxRenderState
    ) -> None:
        rect = (
            state.x + state.style.border_thickness,
            state.y + state.style.border_thickness,
            state.width - state.style.border_thickness * 2,
            state.height - state.style.border_thickness * 2,
        )
        pygame.draw.rect(
            surface, state.style.color, rect, border_radius=state.style.radius
        )

    def _draw_selection(
        self, surface: pygame.Surface, state: TextBoxRenderState
    ) -> None:
        if state.selection is None:
            return

        (start_line, start_col), (end_line, end_col) = state.selection

        for i in self._visible_range(state):
            visual_line = state.display_lines[i]
            text = visual_line.text
            line_index = visual_line.line_index
            line_start = visual_line.start_at

            if not (start_line <= line_index <= end_line):
                continue

            line_y = state.actual_y + state.line_height * (
                i - state.first_visible_line_index
            )

            col_start = start_col if line_index == start_line else 0
            col_end = (
                end_col
                if line_index == end_line
                else state.logical_line_lengths[line_index]
            )

            local_start = max(0, col_start - line_start)
            local_end = min(len(text), col_end - line_start)

            if local_start > local_end:
                continue

            is_empty_line = state.logical_line_lengths[line_index] == 0
            is_end_of_logical_line = (
                line_index < end_line
                and local_end == len(text)
                and line_start + len(text) == state.logical_line_lengths[line_index]
            )

            if local_start == local_end and not (
                is_empty_line or is_end_of_logical_line
            ):
                continue

            text_before_width = visual_line.get_offset(local_start)
            text_up_to_end_width = visual_line.get_offset(local_end)
            text_width = text_up_to_end_width - text_before_width

            if is_empty_line or is_end_of_logical_line:
                text_width += state.space_width

            pygame.draw.rect(
                surface,
                state.style.selection_color,
                (
                    state.actual_x + text_before_width,
                    line_y,
                    text_width,
                    state.line_height,
                ),
            )

    def _draw_text(self, surface: pygame.Surface, state: TextBoxRenderState) -> None:
        def draw_segment(
            text: str, color: ColorLike, x: float, y: float, style: int = 0
        ) -> None:
            text_surface = self._get_rendered_text_surface(state, text, color, style)
            surface.blit(text_surface, (x, y))

        selection = state.selection

        for i in self._visible_range(state):
            visual_line = state.display_lines[i]
            text = visual_line.text
            line_index = visual_line.line_index
            line_start = visual_line.start_at
            line_y = (
                state.actual_y
                + (i - state.first_visible_line_index) * state.line_height
            )

            if selection is None:
                draw_segment(text, state.display_color, state.actual_x, line_y)
                continue

            (start_line, start_col), (end_line, end_col) = selection

            col_start = start_col if line_index == start_line else 0
            col_end = (
                end_col
                if line_index == end_line
                else state.logical_line_lengths[line_index]
            )

            local_start = max(0, col_start - line_start)
            local_end = min(len(text), col_end - line_start)

            if not start_line <= line_index <= end_line or local_start > local_end:
                draw_segment(text, state.display_color, state.actual_x, line_y)
                continue

            before = text[:local_start]
            under = text[local_start:local_end]
            after = text[local_end:]

            if before:
                draw_segment(before, state.display_color, state.actual_x, line_y)
            if under:
                draw_segment(
                    under,
                    state.style.text_color_under_selection,
                    state.actual_x + visual_line.get_offset(local_start),
                    line_y,
                )
            if after:
                draw_segment(
                    after,
                    state.display_color,
                    state.actual_x + visual_line.get_offset(local_end),
                    line_y,
                )

    def _draw_cursor(self, surface: pygame.Surface, state: TextBoxRenderState) -> None:
        if not state.show_cursor:
            return

        index = state.cursor_visual_line_index

        if not (
            state.first_visible_line_index
            <= index
            < state.first_visible_line_index + state.max_visible_lines
        ):
            return

        if index == -1:
            return

        visual_line = state.display_lines[index]
        local_column = state.cursor_column - visual_line.start_at
        x = state.actual_x + visual_line.get_offset(local_column)
        y = state.actual_y + state.line_height * (
            index - state.first_visible_line_index
        )

        if not state.overwrite_mode:
            pygame.draw.line(
                surface,
                state.style.cursor_color,
                (x, y),
                (x, y + state.line_height),
                state.style.cursor_width,
            )
        else:
            text_surface = self._get_rendered_text_surface(
                state, state.cursor_char, state.style.text_color
            )
            cursor_surface = pygame.Surface(text_surface.get_size())
            cursor_surface.fill(state.style.cursor_color)
            cursor_surface.set_alpha(state.style.cursor_alpha)
            surface.blit(cursor_surface, (x, y))
