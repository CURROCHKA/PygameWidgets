import sys
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from typing import Literal, NamedTuple

import pygame
import pygame.freetype
import pyperclip
from pygame.typing import ColorLike

import pygame_widgets
from pygame_widgets.mouse import Mouse, MouseState
from pygame_widgets.widget import WidgetBase


def _empty_callback() -> None:
    pass


@dataclass(order=True)
class Cursor:
    line: int = 0
    column: int = 0
    preferred_column: int = field(default=0, compare=False)

    def clamp(self, lines: list[str]) -> None:
        self.line = max(0, min(self.line, len(lines) - 1))
        self.column = max(0, min(self.column, len(lines[self.line])))

    def set(self, line: int, column: int, lines: list[str]) -> None:
        self.line = line
        self.column = column
        self.clamp(lines)


class VisualLine(NamedTuple):
    text: str
    line_index: int
    start_at: int
    prefix_widths: list[int]

    def get_offset(self, column: int) -> int:
        """Return the x offset for a cursor column within this visual line.

        ``column`` is local to this visual fragment, not the original logical
        line. Out-of-range values are clamped so drawing code can safely ask for
        the start or end offset without repeating bounds checks.

        Args:
            column: Cursor column local to this visual line.

        Returns:
            Pixel offset from the visual line's left edge.
        """
        column = max(0, min(column, len(self.prefix_widths) - 1))
        return self.prefix_widths[column]


@dataclass
class TextBoxStyle:
    color: tuple[int, int, int] = (220, 220, 220)
    border_thickness: int = 3
    border_color: tuple[int, int, int] = (0, 0, 0)
    radius: int = 0

    font_size: int = 20
    font: pygame.freetype.Font | None = None
    text_color: tuple[int, int, int] = (0, 0, 0)

    cursor_width: int = 2
    cursor_color: tuple[int, int, int] = (0, 0, 0)
    cursor_alpha: int = 63

    selection_color: tuple[int, int, int] = (166, 210, 255)
    text_color_under_selection: tuple[int, int, int] = (
        255,
        255,
        255,
    )

    placeholder_text_color: tuple[int, int, int] = (10, 10, 10)

    read_only: bool = False
    tab_spaces: int = 4

    lines_per_scroll: int = 1


class TextBox(WidgetBase):
    # Times in ms
    REPEAT_DELAY = 400
    REPEAT_INTERVAL = 70
    CURSOR_INTERVAL = 400
    DOUBLE_CLICK_INTERVAL = 300
    RENDER_CACHE_SIZE = 500
    WIDTH_CACHE_SIZE = 1000

    def __init__(
        self,
        win: pygame.Surface,
        x: int,
        y: int,
        width: int,
        height: int,
        placeholder_text: str = "",
        repeat_delay: float = REPEAT_DELAY,
        repeat_interval: float = REPEAT_INTERVAL,
        cursor_interval: float = CURSOR_INTERVAL,
        double_click_interval: float = DOUBLE_CLICK_INTERVAL,
        on_submit: callable = _empty_callback,
        on_submit_params: tuple = (),
        on_text_changed: callable = _empty_callback,
        on_text_changed_params: tuple = (),
        style: TextBoxStyle = None,
        is_sub_widget=False,
        **kwargs,
    ) -> None:
        super().__init__(win, x, y, width, height, is_sub_widget)

        if not pygame.get_init():
            pygame.init()

        style_kwargs = {
            k: v for k, v in kwargs.items() if k in TextBoxStyle.__dataclass_fields__
        }
        if style is None:
            self.style = TextBoxStyle(**style_kwargs)
        else:
            self.style = replace(style, **style_kwargs)

        if isinstance(self.style.font, pygame.freetype.Font):
            self.font = self.style.font
        else:
            if self.style.font is not None:
                print("Use pygame.freetype.Font or pygame.freetype.SysFont")
            self.font = pygame.freetype.SysFont("calibri", self.style.font_size)
        self.font.pad = True

        # Widget state
        self.selected = False
        self.key_down = False
        self.repeat_time = 0
        self.repeat_event = None
        self.first_repeat = True
        self.insert_on = False
        self.show_cursor = not self.style.read_only
        self.cursor_time = 0
        self.last_click_time = 0

        self.repeat_delay = repeat_delay
        self.repeat_interval = repeat_interval
        self.cursor_interval = cursor_interval
        self.double_click_interval = double_click_interval

        # Cursor state and style
        self.cursor = Cursor()
        self.selection_start = Cursor()
        self.selection_end = Cursor()

        # Text state
        self.text = [""]
        self.placeholder_text = placeholder_text
        self.cached_visual_lines: list[VisualLine] = [
            VisualLine(text="", line_index=0, start_at=0, prefix_widths=[0])
        ]
        self.visual_line_ranges: dict[int, tuple[int, int]] = {0: (0, 1)}

        # Margins
        self.text_offset_top = self.style.font_size // 3
        self.text_offset_left = self.style.font_size // 3
        self.text_offset_right = self.style.font_size // 2

        # Callback
        self.on_submit = on_submit
        self.on_submit_params = on_submit_params
        self.on_text_changed = on_text_changed
        self.on_text_changed_params = on_text_changed_params

        # Cache
        self._width_cache = OrderedDict()
        self._rendered_text_cache = OrderedDict()

        # Layout
        self.first_visible_line_index = 0
        self.reconfigure_layout()

    def reconfigure_layout(self) -> None:
        self._actual_width = (
            self._width
            - self.text_offset_right
            - self.text_offset_left
            - self.style.border_thickness * 2
        )
        self._actual_height = (
            self._height - self.text_offset_top - self.style.border_thickness * 2
        )
        self.line_height = self.style.font_size
        self._actual_x = self._x + self.text_offset_left + self.style.border_thickness
        self._actual_y = self._y + self.text_offset_top + self.style.border_thickness

        self.max_visible_lines = max(1, self._actual_height // self.line_height)

        self.set_visual_lines()

    def listen(self, events: list[pygame.event.Event]) -> None:
        if self._hidden or self._disabled:
            return

        if self.key_down:
            self.update_repeat_event()

        self.handle_mouse()

        if self.selected:
            for event in events:
                if event.type == pygame.KEYDOWN:
                    self.handle_key_down(event)

                elif event.type == pygame.TEXTINPUT:
                    self.handle_text_input(event)

                elif event.type == pygame.KEYUP and (
                    self.repeat_event is not None
                    and self.repeat_event.type == pygame.KEYDOWN
                    and event.key == self.repeat_event.key
                ):
                    self.repeat_event = None
                    self.key_down = False
                    self.first_repeat = True

    def handle_mouse(self) -> None:
        mouse_state = Mouse.get_mouse_state()
        x, y = Mouse.get_mouse_pos()

        if mouse_state == MouseState.CLICK:
            self.process_mouse_click(x, y)

        if self.selected:
            if mouse_state == MouseState.DRAG:
                self.process_mouse_drag(x, y)

            elif mouse_state == MouseState.DOUBLE_CLICK:
                self.process_mouse_double_click()

            elif mouse_state == MouseState.TRIPLE_CLICK:
                self.process_mouse_triple_click()

        if mouse_state == MouseState.WHEEL_MOTION and self.contains(x, y):
            self.process_mouse_scroll()

    def handle_key_down(self, event: pygame.Event) -> None:
        if event.mod & pygame.KMOD_ALT:
            return

        now = pygame.time.get_ticks()
        self.show_cursor = True
        self.cursor_time = now
        self.key_down = True
        self.repeat_event = event
        self.repeat_time = now

        if event.key == pygame.K_BACKSPACE:
            self.erase_text(event, direction=-1)

        elif event.key == pygame.K_DELETE:
            self.erase_text(event, direction=1)

        elif event.key == pygame.K_RETURN:
            self.process_return(event)

        elif event.key == pygame.K_UP or (
            event.key == pygame.K_KP_8 and not event.mod & pygame.KMOD_NUM
        ):
            self.move_cursor_vertical(event, direction=-1)

        elif event.key == pygame.K_DOWN or (
            event.key == pygame.K_KP_2 and not event.mod & pygame.KMOD_NUM
        ):
            self.move_cursor_vertical(event, direction=1)

        elif event.key == pygame.K_LEFT or (
            event.key == pygame.K_KP_4 and not event.mod & pygame.KMOD_NUM
        ):
            self.move_cursor_horizontal(event, direction=-1)

        elif event.key == pygame.K_RIGHT or (
            event.key == pygame.K_KP_6 and not event.mod & pygame.KMOD_NUM
        ):
            self.move_cursor_horizontal(event, direction=1)

        elif event.key == pygame.K_HOME or (
            event.key == pygame.K_KP_7 and not event.mod & pygame.KMOD_NUM
        ):
            self.jump_to_edge(event, direction=-1)

        elif event.key == pygame.K_END or (
            event.key == pygame.K_KP_1 and not event.mod & pygame.KMOD_NUM
        ):
            self.jump_to_edge(event, direction=1)

        elif event.key == pygame.K_a and event.mod & pygame.KMOD_CTRL:
            self.select_all()

        elif event.key == pygame.K_c and event.mod & pygame.KMOD_CTRL:
            self.copy()

        elif event.key == pygame.K_v and event.mod & pygame.KMOD_CTRL:
            self.paste()

        elif event.key == pygame.K_x and event.mod & pygame.KMOD_CTRL:
            self.cut()

        elif event.key == pygame.K_INSERT or (
            event.key == pygame.K_KP_0 and not event.mod & pygame.KMOD_NUM
        ):
            self.process_insert()

        elif event.key == pygame.K_ESCAPE:
            self.escape()

    def handle_text_input(self, event: pygame.Event) -> None:
        if not self.style.read_only:
            now = pygame.time.get_ticks()
            self.show_cursor = True
            self.cursor_time = now
            if len(event.text) != 0:
                self.add_text(event.text)

    def draw(self) -> None:
        if self._hidden:
            return
        if self.selected:
            self.update_cursor()
        self._draw_border()
        self._draw_background()
        self._draw_selection()
        self._draw_text()
        self._draw_cursor()

    def _draw_text(self) -> None:
        def draw_segment(
            text: str, color: ColorLike, x: float, y: float, style: int = 0
        ):
            text_surface = self.get_rendered_text_surface(text, color, style)
            self.win.blit(text_surface, (x, y))

        if self.is_empty_text(self.text):
            display_lines = [
                VisualLine(
                    text=self.placeholder_text,
                    line_index=0,
                    start_at=0,
                    prefix_widths=[0],
                )
            ]
            color = self.style.placeholder_text_color
        else:
            display_lines = self.cached_visual_lines
            color = self.style.text_color

        if not self.is_empty_selection():
            start, end = self.get_normalized_selection()

        for i in range(
            self.first_visible_line_index,
            min(
                self.first_visible_line_index + self.max_visible_lines,
                len(display_lines),
            ),
        ):
            visual_line = display_lines[i]

            text = visual_line.text
            line_index = visual_line.line_index
            line_start = visual_line.start_at

            line_y = (
                self._actual_y + (i - self.first_visible_line_index) * self.line_height
            )

            if self.is_empty_selection() or not start.line <= line_index <= end.line:
                draw_segment(text, color, self._actual_x, line_y)

            else:
                start_column = start.column if line_index == start.line else 0
                end_column = (
                    end.column if line_index == end.line else len(self.text[line_index])
                )

                local_start = max(0, start_column - line_start)
                local_end = min(len(text), end_column - line_start)

                if local_start > local_end:
                    draw_segment(text, color, self._actual_x, line_y)
                    continue

                text_before_selection = text[:local_start]
                text_under_selection = text[local_start:local_end]
                text_after_selection = text[local_end:]

                if text_before_selection:
                    draw_segment(text_before_selection, color, self._actual_x, line_y)

                if text_under_selection:
                    draw_segment(
                        text_under_selection,
                        self.style.text_color_under_selection,
                        self._actual_x + visual_line.get_offset(local_start),
                        line_y,
                    )

                if text_after_selection:
                    draw_segment(
                        text_after_selection,
                        color,
                        self._actual_x + visual_line.get_offset(local_end),
                        line_y,
                    )

    def _draw_cursor(self) -> None:
        if self.selected and self.show_cursor:
            visual_line_index = self.get_visual_line_index(self.cursor)

            if not (
                self.first_visible_line_index
                <= visual_line_index
                < self.first_visible_line_index + self.max_visible_lines
            ):
                return

            if visual_line_index != -1:
                visual_line = self.cached_visual_lines[visual_line_index]

                local_start = self.cursor.column - visual_line.start_at
                start_x = self._actual_x + visual_line.get_offset(local_start)
                end_x = start_x

                start_y = self._actual_y + self.line_height * (
                    visual_line_index - self.first_visible_line_index
                )
                end_y = start_y + self.line_height

                if not self.insert_on:
                    pygame.draw.line(
                        self.win,
                        self.style.cursor_color,
                        (start_x, start_y),
                        (end_x, end_y),
                        self.style.cursor_width,
                    )
                else:
                    if self.cursor.column == len(self.text[self.cursor.line]):
                        text_surface = self.get_rendered_text_surface(
                            " ", self.style.text_color
                        )
                    else:
                        text_surface = self.get_rendered_text_surface(
                            self.text[self.cursor.line][self.cursor.column],
                            self.style.text_color,
                        )
                    cursor_surface = pygame.Surface(text_surface.get_size())
                    cursor_surface.fill(self.style.cursor_color)
                    cursor_surface.set_alpha(self.style.cursor_alpha)
                    self.win.blit(cursor_surface, (start_x, start_y))

    def _draw_border(self) -> None:
        pygame.draw.rect(
            self.win,
            self.style.border_color,
            (self._x, self._y, self._width, self._height),
            border_radius=self.style.radius,
        )

    def _draw_background(self) -> None:
        rect = (
            self._x + self.style.border_thickness,
            self._y + self.style.border_thickness,
            self._width - self.style.border_thickness * 2,
            self._height - self.style.border_thickness * 2,
        )
        pygame.draw.rect(
            self.win, self.style.color, rect, border_radius=self.style.radius
        )

    def _draw_selection(self) -> None:
        if self.is_empty_selection():
            return

        start, end = self.get_normalized_selection()

        for i in range(
            self.first_visible_line_index,
            min(
                self.first_visible_line_index + self.max_visible_lines,
                len(self.cached_visual_lines),
            ),
        ):
            visual_line = self.cached_visual_lines[i]

            text = visual_line.text
            line_index = visual_line.line_index
            line_start = visual_line.start_at

            if not (start.line <= line_index <= end.line):
                continue

            line_y = self._actual_y + self.line_height * (
                i - self.first_visible_line_index
            )

            start_column = start.column if line_index == start.line else 0
            end_column = (
                end.column if line_index == end.line else len(self.text[line_index])
            )

            local_start = max(0, start_column - line_start)
            local_end = min(len(text), end_column - line_start)

            if local_start > local_end:
                continue

            is_empty_line = len(self.text[line_index]) == 0

            is_end_of_logical_line = (
                line_index < end.line
                and local_end == len(text)
                and line_start + len(text) == len(self.text[line_index])
            )

            if local_start == local_end and not (
                is_empty_line or is_end_of_logical_line
            ):
                continue

            text_before_width = visual_line.get_offset(local_start)
            text_up_to_end_width = visual_line.get_offset(local_end)

            text_width = text_up_to_end_width - text_before_width

            if is_empty_line or is_end_of_logical_line:
                text_width += self.get_text_width(" ")

            pygame.draw.rect(
                self.win,
                self.style.selection_color,
                (
                    self._actual_x + text_before_width,
                    line_y,
                    text_width,
                    self.line_height,
                ),
            )

    def process_mouse_click(self, x: float, y: float) -> None:
        if self.contains(x, y):
            now = pygame.time.get_ticks()
            self.last_click_time = now

            self.selected = True
            self.show_cursor = True
            self.cursor_time = now

            self.set_cursor_from_mouse(x, y)
            self.reset_selection()
            self.set_preferred_column()
        else:
            self.escape()

    def process_mouse_drag(self, x: float, y: float) -> None:
        self.cursor_time = pygame.time.get_ticks()
        self.set_cursor_from_mouse(x, y)
        self.selection_end.set(self.cursor.line, self.cursor.column, self.text)
        self.set_preferred_column()

        if y < self._actual_y:
            self.first_visible_line_index = max(0, self.first_visible_line_index - 1)
        elif y > self._actual_y + self._actual_height:
            max_scroll = max(0, len(self.cached_visual_lines) - self.max_visible_lines)
            self.first_visible_line_index = min(
                max_scroll, self.first_visible_line_index + 1
            )

    def process_mouse_double_click(self) -> None:
        self.move_cursor_word(direction=-1)
        self.selection_start.set(self.cursor.line, self.cursor.column, self.text)
        self.move_cursor_word(direction=1)
        self.selection_end.set(self.cursor.line, self.cursor.column, self.text)

    def process_mouse_triple_click(self) -> None:
        self.selection_start.set(self.cursor.line, 0, self.text)
        self.selection_end.set(
            self.cursor.line, len(self.text[self.cursor.line]), self.text
        )

    def process_mouse_scroll(self) -> None:
        self.first_visible_line_index -= (
            Mouse.get_wheel_delta() * self.style.lines_per_scroll
        )
        max_scroll = max(0, len(self.cached_visual_lines) - self.max_visible_lines)
        self.first_visible_line_index = max(
            0, min(self.first_visible_line_index, max_scroll)
        )

    def process_return(self, event: pygame.Event) -> None:
        if self.style.read_only:
            return
        if event.mod & pygame.KMOD_SHIFT or event.mod & pygame.KMOD_CTRL:
            self.add_text("\n")
        else:
            self.on_submit(*self.on_submit_params)

    def process_backspace(self) -> None:
        if self.cursor.column > 0:
            self.text[self.cursor.line] = (
                self.text[self.cursor.line][: self.cursor.column - 1]
                + self.text[self.cursor.line][self.cursor.column :]
            )
            self.cursor.set(self.cursor.line, self.cursor.column - 1, self.text)

            self.set_visual_lines()
            self.set_preferred_column()
            self.on_text_changed(*self.on_text_changed_params)

        elif self.cursor.line > 0:
            previous_line_length = len(self.text[self.cursor.line - 1])
            self.text[self.cursor.line - 1] += self.text[self.cursor.line]
            self.text.pop(self.cursor.line)
            self.cursor.set(self.cursor.line - 1, previous_line_length, self.text)

            self.set_visual_lines()
            self.set_preferred_column()
            self.on_text_changed(*self.on_text_changed_params)

    def process_delete(self) -> None:
        if self.cursor.column < len(self.text[self.cursor.line]):
            self.text[self.cursor.line] = (
                self.text[self.cursor.line][: self.cursor.column]
                + self.text[self.cursor.line][self.cursor.column + 1 :]
            )

            self.set_visual_lines()
            self.set_preferred_column()
            self.on_text_changed(*self.on_text_changed_params)

        elif self.cursor.line < len(self.text) - 1:
            self.text[self.cursor.line] += self.text[self.cursor.line + 1]
            self.text.pop(self.cursor.line + 1)

            self.set_visual_lines()
            self.set_preferred_column()
            self.on_text_changed(*self.on_text_changed_params)

    def erase_text(self, event: pygame.Event, direction: Literal[-1, 1]) -> None:
        if self.style.read_only:
            return

        if not self.is_empty_selection():
            self.erase_selected_text()
            return

        if event.mod & pygame.KMOD_CTRL:
            self.selection_start.set(self.cursor.line, self.cursor.column, self.text)
            self.move_cursor_word(direction)
            self.selection_end.set(self.cursor.line, self.cursor.column, self.text)
            self.erase_selected_text()
            return

        if direction == -1:
            self.process_backspace()

        elif direction == 1:
            self.process_delete()

        self.ensure_cursor_visible()

    def erase_selected_text(self, call_on_text_changed: bool = True) -> None:
        start, end = self.get_normalized_selection()

        if start.line == end.line:
            self.text[start.line] = (
                self.text[start.line][: start.column]
                + self.text[start.line][end.column :]
            )
        else:
            self.text[start.line] = (
                self.text[start.line][: start.column]
                + self.text[end.line][end.column :]
            )
            del self.text[start.line + 1 : end.line + 1]

        self.cursor.set(start.line, start.column, self.text)
        self.reset_selection()

        self.set_visual_lines()
        self.set_preferred_column()
        self.ensure_cursor_visible()
        if call_on_text_changed:
            self.on_text_changed(*self.on_text_changed_params)

    def jump_to_edge(self, event: pygame.Event, direction: Literal[-1, 1]) -> None:
        shift_pressed = bool(event.mod & pygame.KMOD_SHIFT)

        if shift_pressed and self.is_empty_selection():
            self.selection_start.set(self.cursor.line, self.cursor.column, self.text)

        if event.mod & pygame.KMOD_CTRL:
            line = 0 if direction == -1 else len(self.text) - 1
            column = 0 if direction == -1 else len(self.text[-1])
            self.cursor.set(line, column, self.text)
        else:
            visual_line_index = self.get_visual_line_index(self.cursor)
            if visual_line_index != -1:
                visual_line = self.cached_visual_lines[visual_line_index]
                column = visual_line.start_at
                if direction == 1:
                    column += len(visual_line.text)

                self.cursor.set(self.cursor.line, column, self.text)

        if event.mod & pygame.KMOD_SHIFT:
            self.selection_end.set(self.cursor.line, self.cursor.column, self.text)
        else:
            self.reset_selection()

        self.set_preferred_column()
        self.ensure_cursor_visible()

    def move_cursor_vertical(
        self, event: pygame.Event, direction: Literal[-1, 1]
    ) -> None:
        shift_pressed = bool(event.mod & pygame.KMOD_SHIFT)

        if shift_pressed and self.is_empty_selection():
            self.selection_start.set(self.cursor.line, self.cursor.column, self.text)

        base_cursor = Cursor(self.cursor.line, self.cursor.column)
        if not shift_pressed and not self.is_empty_selection():
            start, end = self.get_normalized_selection()
            base_cursor = start if direction == -1 else end
            self.cursor.set(base_cursor.line, base_cursor.column, self.text)
            self.reset_selection()

        visual_line_index = self.get_visual_line_index(base_cursor)
        if visual_line_index == -1:
            return

        target_index = visual_line_index + direction

        if 0 <= target_index < len(self.cached_visual_lines):
            target_line = self.cached_visual_lines[target_index]
            desired_column = min(
                target_line.start_at + self.cursor.preferred_column,
                target_line.start_at + len(target_line.text),
            )
            self.cursor.set(target_line.line_index, desired_column, self.text)
        else:
            if direction == -1:
                self.cursor.set(self.cursor.line, 0, self.text)
            else:
                current_line = self.cached_visual_lines[visual_line_index]
                self.cursor.set(
                    self.cursor.line,
                    current_line.start_at + len(current_line.text),
                    self.text,
                )
            self.set_preferred_column()

        if shift_pressed:
            self.selection_end.set(self.cursor.line, self.cursor.column, self.text)

        self.ensure_cursor_visible()

    def move_cursor_horizontal(
        self, event: pygame.Event, direction: Literal[-1, 1]
    ) -> None:
        shift_pressed = bool(event.mod & pygame.KMOD_SHIFT)
        ctrl_pressed = bool(event.mod & pygame.KMOD_CTRL)

        if not shift_pressed and not self.is_empty_selection():
            start, end = self.get_normalized_selection()
            boundary = start if direction == -1 else end
            self.cursor.set(boundary.line, boundary.column, self.text)
            self.reset_selection()
            self.set_preferred_column()
            self.ensure_cursor_visible()
            return

        if shift_pressed and self.is_empty_selection():
            self.selection_start.set(self.cursor.line, self.cursor.column, self.text)

        if ctrl_pressed:
            self.move_cursor_word(direction)
        else:
            line = self.cursor.line
            column = self.cursor.column

            if direction == -1:
                if column == 0 and line > 0:
                    line -= 1
                    column = len(self.text[line])
                else:
                    column = max(column - 1, 0)
            elif direction == 1:
                if column == len(self.text[line]) and line < len(self.text) - 1:
                    line += 1
                    column = 0
                else:
                    column += 1

            self.cursor.set(line, column, self.text)

        if shift_pressed:
            self.selection_end.set(self.cursor.line, self.cursor.column, self.text)

        self.set_preferred_column()
        self.ensure_cursor_visible()

    def select_all(self) -> None:
        self.selection_start.set(0, 0, self.text)
        self.selection_end.set(len(self.text) - 1, len(self.text[-1]), self.text)
        self.cursor.set(len(self.text) - 1, len(self.text[-1]), self.text)

    def copy(self) -> None:
        if not self.is_empty_selection():
            pyperclip.copy(self.get_selected_text())

    def paste(self) -> None:
        if not self.style.read_only:
            text = pyperclip.paste()
            if text:
                self.add_text(text)

    def cut(self) -> None:
        self.copy()
        if not self.style.read_only and not self.is_empty_selection():
            self.erase_selected_text()

    def process_insert(self) -> None:
        self.insert_on = not self.insert_on

    def update_repeat_event(self) -> None:
        if self.repeat_event is None:
            return

        now = pygame.time.get_ticks()

        if self.first_repeat:
            if now - self.repeat_time >= self.repeat_delay:
                self.first_repeat = False
                self.repeat_time = now
                self.handle_key_down(self.repeat_event)

        elif now - self.repeat_time >= self.repeat_interval:
            self.repeat_time = now
            self.handle_key_down(self.repeat_event)

    def ensure_cursor_visible(self) -> None:
        visual_line_index = self.get_visual_line_index(self.cursor)
        if visual_line_index == -1:
            return

        if visual_line_index < self.first_visible_line_index:
            self.first_visible_line_index = visual_line_index

        elif (
            visual_line_index >= self.first_visible_line_index + self.max_visible_lines
        ):
            self.first_visible_line_index = (
                visual_line_index - self.max_visible_lines + 1
            )

        max_scroll = max(0, len(self.cached_visual_lines) - self.max_visible_lines)
        self.first_visible_line_index = max(
            0, min(self.first_visible_line_index, max_scroll)
        )

    def update_layout(self) -> None:
        self._actual_height = (
            self._height - self.text_offset_top - self.style.border_thickness * 2
        )

        self.max_visible_lines = max(1, self._actual_height // self.line_height)

    def add_text(self, text: str, call_on_text_changed: bool = True) -> None:
        if not self.is_empty_selection():
            self.erase_selected_text(call_on_text_changed=False)

        text = str(text).replace("\t", " " * self.style.tab_spaces).replace("\r", "")
        lines = text.split("\n")

        if not self.insert_on:
            right_part = self.text[self.cursor.line][self.cursor.column :]

            for i, line in enumerate(lines):
                self.text[self.cursor.line] = (
                    self.text[self.cursor.line][: self.cursor.column] + line
                )
                self.cursor.set(
                    self.cursor.line, self.cursor.column + len(line), self.text
                )

                if i != len(lines) - 1:
                    self.text.insert(self.cursor.line + 1, "")
                    self.cursor.set(self.cursor.line + 1, 0, self.text)

            self.text[self.cursor.line] += right_part

        else:
            for i, line in enumerate(lines):
                right_part = self.text[self.cursor.line][
                    self.cursor.column + len(line) :
                ]

                self.text[self.cursor.line] = (
                    self.text[self.cursor.line][: self.cursor.column] + line
                )
                self.cursor.set(
                    self.cursor.line, self.cursor.column + len(line), self.text
                )

                if i != len(lines) - 1:
                    self.text.insert(self.cursor.line + 1, "")
                    self.cursor.set(self.cursor.line + 1, 0, self.text)

                self.text[self.cursor.line] += right_part

        self.set_visual_lines()
        self.set_preferred_column()
        self.ensure_cursor_visible()
        if call_on_text_changed:
            self.on_text_changed(*self.on_text_changed_params)

    def get_normalized_selection(self) -> tuple[Cursor, Cursor]:
        if self.selection_start > self.selection_end:
            return self.selection_end, self.selection_start
        return self.selection_start, self.selection_end

    def set_visual_lines(self) -> None:
        """Rebuild the soft-wrapped visual-line cache from ``self.text``.

        ``self.text`` stores logical lines split only by hard newlines. This
        method derives ``cached_visual_lines`` for drawing, cursor navigation,
        selection and scrolling. ``visual_line_ranges`` maps each logical line
        index to a half-open range in ``cached_visual_lines`` so lookups can scan
        only that line's wrapped fragments.

        Call this after text changes, or after layout/font changes once the
        widget's text area measurements have been refreshed.
        """
        self.cached_visual_lines = []
        self.visual_line_ranges = {}

        for line_index, line in enumerate(self.text):
            range_start = len(self.cached_visual_lines)

            for visual_line in self._wrap_logical_line(line, line_index):
                self.cached_visual_lines.append(visual_line)

            range_end = len(self.cached_visual_lines)
            self.visual_line_ranges[line_index] = (range_start, range_end)

        self.update_layout()

    def _wrap_logical_line(self, line: str, line_index: int) -> list[VisualLine]:
        """Soft-wrap a single logical line into ``VisualLine`` fragments.

        ``line`` is one entry of ``self.text``. The returned fragments are in
        drawing order and all point back to ``line_index``; ``start_at`` stores
        the fragment's starting column in the original logical line.

        The loop asks ``find_visual_line_end`` for the largest substring that fits
        in the text area. If there is more text after that point, it tries to
        move the break to the last space in the candidate window and keeps that
        space at the end of the current visual line. If no useful space exists,
        it breaks at the measured boundary. When even one character is wider
        than the available width, the method emits that character anyway so the
        loop cannot stall.

        Empty logical lines return one empty visual line so blank rows remain
        addressable by cursor, selection and scrolling code.

        Args:
            line: Logical line text without its trailing newline.
            line_index: Index of ``line`` inside ``self.text``.

        Returns:
            Visual-line fragments that cover the whole logical line.
        """
        if line == "":
            return [self._make_visual_line("", line_index, 0)]

        visual_lines = []
        start = 0

        while start < len(line):
            end = self.find_visual_line_end(line, start)

            if end == len(line):
                visual_lines.append(
                    self._make_visual_line(line[start:end], line_index, start)
                )
                break

            if end == start:
                end = start + 1
                visual_lines.append(
                    self._make_visual_line(line[start:end], line_index, start)
                )
                start = end
                continue

            last_space = line.rfind(" ", start, end + 1)
            can_wrap_by_space = (
                last_space >= start and line[start:last_space].strip() != ""
            )

            if can_wrap_by_space:
                visual_lines.append(
                    self._make_visual_line(
                        line[start : last_space + 1], line_index, start
                    )
                )
                start = last_space + 1
            else:
                visual_lines.append(
                    self._make_visual_line(line[start:end], line_index, start)
                )
                start = end

        return visual_lines

    def _make_visual_line(
        self, text: str, line_index: int, start_at: int
    ) -> VisualLine:
        """Create a ``VisualLine`` and precompute cursor offsets for its text.

        ``start_at`` is the column where ``text`` begins inside the original
        logical line. ``prefix_widths`` has one more entry than ``text``: index 0
        is the left edge, and every later index is the x offset after that many
        characters. The drawing and hit-testing paths use those offsets instead
        of remeasuring the same substrings repeatedly.

        Args:
            text: Text displayed by this visual line fragment.
            line_index: Index of the source logical line in ``self.text``.
            start_at: Starting column of ``text`` in the source logical line.

        Returns:
            A ``VisualLine`` with precomputed prefix widths.
        """
        return VisualLine(
            text=text,
            line_index=line_index,
            start_at=start_at,
            prefix_widths=self.build_prefix_widths(text),
        )

    def find_visual_line_end(self, line: str, start: int) -> int:
        """Return the exclusive end column of the widest substring that fits.

        The search checks candidate end columns with binary search. ``low`` is
        the largest known fitting end column, while ``high`` is the first known
        non-fitting end column or the sentinel just after ``len(line)``. The
        returned value is suitable for Python slicing, so
        ``line[start:return_value]`` is the measured fragment.

        If the first character is already too wide, no candidate slice is
        accepted and the method returns ``start``. ``_wrap_logical_line`` handles
        that case by emitting one character anyway, which guarantees progress.

        Args:
            line: Logical line being wrapped.
            start: Column where the candidate visual line begins.

        Returns:
            Exclusive end column for the largest fitting slice.
        """
        low = start
        high = len(line) + 1

        while low + 1 < high:
            candidate_end = (low + high) // 2
            if self.get_text_width(line[start:candidate_end]) <= self._actual_width:
                low = candidate_end
            else:
                high = candidate_end

        return low

    def reset_selection(self) -> None:
        self.selection_start.set(self.cursor.line, self.cursor.column, self.text)
        self.selection_end.set(self.cursor.line, self.cursor.column, self.text)

    def get_visual_line_index(self, cursor: Cursor) -> int:
        """Find the cached visual line that contains ``cursor``.

        The lookup first narrows the scan with ``visual_line_ranges`` for the
        cursor's logical line. Cursor columns are logical-line columns, so each
        visual fragment is matched by
        ``start_at <= column <= start_at + len(text)``.

        When the cursor sits exactly at the end of a wrapped fragment and
        another fragment from the same logical line follows, this returns the
        next fragment. That draws the caret at the start of the next screen row,
        matching normal wrapped-text editing behavior.

        Args:
            cursor: Logical cursor position to locate.

        Returns:
            Index in ``cached_visual_lines``, or -1 if no matching visual line is
            cached.
        """
        start_index, end_index = self.visual_line_ranges.get(
            cursor.line, (0, len(self.cached_visual_lines))
        )

        for line_index in range(start_index, end_index):
            visual_line = self.cached_visual_lines[line_index]
            if visual_line.line_index != cursor.line:
                continue

            line_width = visual_line.start_at + len(visual_line.text)
            if visual_line.start_at <= cursor.column <= line_width:
                if (
                    cursor.column == line_width != 0
                    and line_index + 1 < len(self.cached_visual_lines)
                    and self.cached_visual_lines[line_index + 1].line_index
                    == cursor.line
                ):
                    return line_index + 1
                return line_index
        return -1

    def get_text_width(self, text: str, style: int = 0) -> int:
        cache_key = (text, style)

        if cache_key in self._width_cache:
            self._width_cache.move_to_end(cache_key)
            return self._width_cache[cache_key]

        if len(self._width_cache) >= self.WIDTH_CACHE_SIZE:
            self._width_cache.popitem(last=False)

        width = self.font.get_rect(text, style=style).width
        self._width_cache[cache_key] = width

        return width

    def build_prefix_widths(self, text: str) -> list[int]:
        """Build x offsets for every cursor position inside ``text``.

        The returned list always starts with 0 and contains one entry per cursor
        position, including the position after the last character. For example,
        ``prefix_widths[3]`` is the pixel offset after the first three
        characters.

        Most characters use freetype glyph advance from ``get_metrics``. If
        metrics are missing for a character, the code falls back to measuring
        that character through ``get_text_width``.

        Args:
            text: Visual-line text whose cursor offsets should be measured.

        Returns:
            Pixel offsets for cursor columns 0 through ``len(text)``.
        """
        widths = [0]
        metrics = self.font.get_metrics(text)
        cumulative = 0
        for i, glyph in enumerate(metrics):
            if glyph:
                cumulative += int(glyph[4])
            else:
                cumulative += self.get_text_width(text[i])
            widths.append(cumulative)
        return widths

    def get_rendered_text_surface(
        self,
        text: str,
        color: ColorLike,
        style: int = 0,
    ) -> pygame.Surface:
        cache_key = (text, color, style)

        if cache_key in self._rendered_text_cache:
            self._rendered_text_cache.move_to_end(cache_key)
            return self._rendered_text_cache[cache_key]

        if len(self._rendered_text_cache) >= self.RENDER_CACHE_SIZE:
            self._rendered_text_cache.popitem(last=False)

        rendered = self.font.render(text, fgcolor=color, style=style)[0]
        self._rendered_text_cache[cache_key] = rendered
        return rendered

    def update_cursor(self) -> None:
        now = pygame.time.get_ticks()
        if now - self.cursor_time >= self.cursor_interval:
            self.show_cursor = not self.show_cursor
            self.cursor_time = now

    def is_empty_text(self, text: list[str]) -> bool:
        return len(text) == 1 and text[0] == ""

    def is_word_char(self, character: str) -> bool:
        return character.isalnum() or character == "_"

    def is_empty_selection(self) -> bool:
        return (self.selection_start.line, self.selection_start.column) == (
            self.selection_end.line,
            self.selection_end.column,
        )

    def escape(self) -> None:
        self.repeat_event = None
        self.key_down = False
        self.first_repeat = True
        self.selected = False
        self.show_cursor = False
        self.reset_selection()

    def set_text(self, text: str) -> None:
        self.text = [""]
        self.cursor.set(0, 0, self.text)
        self.reset_selection()
        self.add_text(text, call_on_text_changed=False)

    def set_preferred_column(self) -> None:
        """Remember the cursor's visual-column target for vertical movement.

        Horizontal movement and mouse placement update this value. Up/down
        movement then tries to keep the same local column inside the next visual
        line, clamping only when that target line is shorter.
        """
        visual_line_index = self.get_visual_line_index(self.cursor)

        if visual_line_index != -1:
            visual_line = self.cached_visual_lines[visual_line_index]
            local_column = self.cursor.column - visual_line.start_at

            self.cursor.preferred_column = local_column

    def move_cursor_word(self, direction: Literal[-1, 1]) -> None:
        line = self.cursor.line
        column = self.cursor.column
        current_line = self.text[line]

        if direction == -1 and column == 0 and line > 0:
            line -= 1
            current_line = self.text[line]
            column = len(current_line)
        elif (
            direction == 1 and column == len(current_line) and line < len(self.text) - 1
        ):
            line += 1
            current_line = self.text[line]
            column = 0

        offset = -1 if direction == -1 else 0
        while 0 <= column + offset < len(current_line) and not self.is_word_char(
            current_line[column + offset]
        ):
            column += direction

        while 0 <= column + offset < len(current_line) and self.is_word_char(
            current_line[column + offset]
        ):
            column += direction

        self.cursor.set(line, column, self.text)

    def set_cursor_from_mouse(self, mouse_x: float, mouse_y: float) -> None:
        """Move the cursor to the text position closest to a mouse coordinate.

        The y coordinate selects a visible ``VisualLine`` after clamping to the
        text area. The x coordinate is compared with midpoint positions between
        adjacent prefix widths, which chooses the nearest insertion column
        inside that visual fragment. The final cursor column is converted back
        to a logical-line column by adding ``visual_line.start_at``.

        Args:
            mouse_x: Mouse x coordinate in window space.
            mouse_y: Mouse y coordinate in window space.
        """
        if not self.cached_visual_lines:
            return

        clamped_y = max(
            self._actual_y, min(mouse_y, self._actual_y + self._actual_height - 1)
        )

        raw_index = (
            self.first_visible_line_index
            + (clamped_y - self._actual_y) // self.line_height
        )
        visual_line_index = max(
            self.first_visible_line_index,
            min(
                raw_index,
                self.first_visible_line_index + self.max_visible_lines - 1,
                len(self.cached_visual_lines) - 1,
            ),
        )

        visual_line = self.cached_visual_lines[visual_line_index]

        if visual_line.line_index != self.cursor.line:
            self.cursor.set(visual_line.line_index, self.cursor.column, self.text)

        if len(visual_line.text) == 0:
            self.cursor.set(self.cursor.line, visual_line.start_at, self.text)
            return

        relative_x = mouse_x - self._actual_x
        prefix_widths = visual_line.prefix_widths
        local_column = len(visual_line.text)

        for column in range(len(visual_line.text)):
            midpoint = (prefix_widths[column] + prefix_widths[column + 1]) / 2
            if relative_x < midpoint:
                local_column = column
                break

        self.cursor.set(
            self.cursor.line,
            visual_line.start_at + local_column,
            self.text,
        )

    def get_text(self) -> str:
        return "\n".join(self.text)

    def get_selected_text(self) -> str:
        start, end = self.get_normalized_selection()

        if start.line == end.line:
            return self.text[start.line][start.column : end.column]

        result = []

        result.append(self.text[start.line][start.column :])

        result.extend(self.text[start.line + 1 : end.line])

        result.append(self.text[end.line][: end.column])

        return "\n".join(result)

    def set(self, attr: str, value: int) -> None:
        super().set(attr, value)
        self.reconfigure_layout()

    def set_x(self, x: int) -> None:
        super().set_x(x)
        self.reconfigure_layout()

    def set_y(self, y: int) -> None:
        super().set_y(y)
        self.reconfigure_layout()

    def set_width(self, width: int) -> None:
        super().set_width(width)
        self.reconfigure_layout()

    def set_height(self, height: int) -> None:
        super().set_height(height)
        self.reconfigure_layout()


if __name__ == "__main__":

    def output():
        print(textbox.get_text())
        textbox.set_text("")

    pygame.init()
    win = pygame.display.set_mode((1000, 600))

    clock = pygame.time.Clock()

    # dark_theme = TextBoxStyle(
    #     color=(30, 30, 30), text_color=(240, 240, 240), font_size=24
    # )

    # input_login = TextBox(win, 100, 100, 400, 50, style=dark_theme)
    # input_password = TextBox(win, 100, 200, 400, 50, style=dark_theme)

    textbox = TextBox(
        win,
        x=100,
        y=100,
        width=800,
        height=400,
        font_size=50,
        border_color=(255, 0, 0),
        text_color=(0, 200, 0),
        on_submit=output,
        radius=10,
        border_thickness=5,
        placeholder_text="Enter something:",
    )

    run = True
    while run:
        outer_events = pygame.event.get()
        for outer_event in outer_events:
            if outer_event.type == pygame.QUIT:
                pygame.quit()
                run = False
                sys.exit()
            # elif outer_event.type == pygame.KEYDOWN:
            #     if outer_event.key == pygame.K_k:
            #         dark_theme.color = (255, 255, 255)
            #         dark_theme.text_color = (0, 0, 0)

        win.fill((255, 255, 255))

        pygame_widgets.update(outer_events)
        pygame.display.update()

        clock.tick(60)
