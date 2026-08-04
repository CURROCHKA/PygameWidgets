from collections import OrderedDict
from typing import Literal, NamedTuple

import pygame.freetype


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


class TextLayoutManager:
    """Handles the conversion of logical text lines into soft-wrapped visual lines.

    This class owns the math for font measuring, word wrapping, and mapping
    logical cursor coordinates to visual screen coordinates.
    """

    WIDTH_CACHE_SIZE = 1000

    def __init__(self):
        self.cached_visual_lines: list[VisualLine] = []
        self.visual_line_ranges: dict[int, tuple[int, int]] = {}
        self._width_cache: OrderedDict = OrderedDict()

    def update_visual_lines(
        self, logical_lines: list[str], actual_width: int, font: pygame.freetype.Font
    ) -> None:
        """Rebuild the soft-wrapped visual-line cache."""
        self.cached_visual_lines = []
        self.visual_line_ranges = {}

        if not logical_lines or (len(logical_lines) == 1 and logical_lines[0] == ""):
            # Handle empty state
            line = VisualLine(text="", line_index=0, start_at=0, prefix_widths=[0])
            self.cached_visual_lines.append(line)
            self.visual_line_ranges[0] = (0, 1)
            return

        for line_index, line in enumerate(logical_lines):
            range_start = len(self.cached_visual_lines)

            for visual_line in self._wrap_logical_line(
                line, line_index, actual_width, font
            ):
                self.cached_visual_lines.append(visual_line)

            range_end = len(self.cached_visual_lines)
            self.visual_line_ranges[line_index] = (range_start, range_end)

    def _wrap_logical_line(
        self, line: str, line_index: int, actual_width: int, font: pygame.freetype.Font
    ) -> list[VisualLine]:
        if line == "":
            return [self._make_visual_line("", line_index, 0, font)]

        visual_lines = []
        start = 0

        while start < len(line):
            end = self._find_visual_line_end(line, start, actual_width, font)

            if end == len(line):
                visual_lines.append(
                    self._make_visual_line(line[start:end], line_index, start, font)
                )
                break

            if end == start:
                end = start + 1
                visual_lines.append(
                    self._make_visual_line(line[start:end], line_index, start, font)
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
                        line[start : last_space + 1], line_index, start, font
                    )
                )
                start = last_space + 1
            else:
                visual_lines.append(
                    self._make_visual_line(line[start:end], line_index, start, font)
                )
                start = end

        return visual_lines

    def _make_visual_line(
        self, text: str, line_index: int, start_at: int, font: pygame.freetype.Font
    ) -> VisualLine:
        return VisualLine(
            text=text,
            line_index=line_index,
            start_at=start_at,
            prefix_widths=self._build_prefix_widths(text, font),
        )

    def _find_visual_line_end(
        self, line: str, start: int, actual_width: int, font: pygame.freetype.Font
    ) -> int:
        low = start
        high = len(line) + 1

        while low + 1 < high:
            candidate_end = (low + high) // 2
            if self._get_text_width(line[start:candidate_end], font) <= actual_width:
                low = candidate_end
            else:
                high = candidate_end
        return low

    def _get_text_width(
        self, text: str, font: pygame.freetype.Font, style: int = 0
    ) -> int:
        cache_key = (id(font), text, style)

        if cache_key in self._width_cache:
            self._width_cache.move_to_end(cache_key)
            return self._width_cache[cache_key]

        if len(self._width_cache) >= self.WIDTH_CACHE_SIZE:
            self._width_cache.popitem(last=False)

        width = font.get_rect(text, style=style).width
        self._width_cache[cache_key] = width
        return width

    def _build_prefix_widths(self, text: str, font: pygame.freetype.Font) -> list[int]:
        widths = [0]
        if not text:
            return widths

        metrics = font.get_metrics(text)
        cumulative = 0
        for i, glyph in enumerate(metrics):
            if glyph:
                cumulative += int(glyph[4])
            else:
                cumulative += self._get_text_width(text[i], font)
            widths.append(cumulative)
        return widths

    def get_visual_line_index(self, logical_line: int, logical_column: int) -> int:
        """Find the cached visual line that contains the given logical cursor position."""
        start_index, end_index = self.visual_line_ranges.get(
            logical_line, (0, len(self.cached_visual_lines))
        )

        for line_index in range(start_index, end_index):
            visual_line = self.cached_visual_lines[line_index]
            if visual_line.line_index != logical_line:
                continue

            line_width = visual_line.start_at + len(visual_line.text)
            if visual_line.start_at <= logical_column <= line_width:
                if (
                    logical_column == line_width != 0
                    and line_index + 1 < len(self.cached_visual_lines)
                    and self.cached_visual_lines[line_index + 1].line_index
                    == logical_line
                ):
                    return line_index + 1
                return line_index
        return -1

    def get_cursor_pos_from_mouse(
        self,
        mouse_x: float,
        mouse_y: float,
        actual_x: int,
        actual_y: int,
        actual_height: int,
        line_height: int,
        first_visible_line_index: int,
        max_visible_lines: int,
    ) -> tuple[int, int] | None:
        """Calculate logical (line, column) cursor position from screen mouse coordinates."""
        if not self.cached_visual_lines:
            return

        clamped_y = max(actual_y, min(mouse_y, actual_y + actual_height - 1))

        raw_index = first_visible_line_index + int(
            (clamped_y - actual_y) // line_height
        )
        visual_line_index = max(
            first_visible_line_index,
            min(
                raw_index,
                first_visible_line_index + max_visible_lines - 1,
                len(self.cached_visual_lines) - 1,
            ),
        )

        visual_line = self.cached_visual_lines[visual_line_index]

        if len(visual_line.text) == 0:
            return visual_line.line_index, visual_line.start_at

        relative_x = mouse_x - actual_x
        prefix_widths = visual_line.prefix_widths
        local_column = len(visual_line.text)

        for column in range(len(visual_line.text)):
            midpoint = (prefix_widths[column] + prefix_widths[column + 1]) / 2
            if relative_x < midpoint:
                local_column = column
                break

        return visual_line.line_index, visual_line.start_at + local_column

    def get_vertical_cursor_target(
        self,
        logical_line: int,
        logical_column: int,
        preferred_column: int,
        direction: Literal["up", "down"],
    ) -> tuple[int, int] | None:
        """Calculate target logical (line, column) for vertical cursor movement across visual lines.

        Args:
            logical_line: Current logical line index.
            logical_column: Current logical column index.
            preferred_column: Target visual column offset remembered from horizontal motion/click.
            direction: "up" or "down".

        Returns:
            Tuple of (target_line, target_column) or None if layout is empty.
        """
        visual_line_index = self.get_visual_line_index(logical_line, logical_column)
        if visual_line_index == -1:
            return None

        match direction:
            case "up":
                offset = -1
                fallback_target = logical_line, 0
            case "down":
                offset = 1
                current_line = self.cached_visual_lines[visual_line_index]
                fallback_target = (
                    logical_line,
                    current_line.start_at + len(current_line.text),
                )
            case _:
                raise ValueError(
                    "An incorrect direction value has been entered. Expected Literal['up', 'down']"
                )

        target_index = visual_line_index + offset

        if 0 <= target_index < len(self.cached_visual_lines):
            target_line = self.cached_visual_lines[target_index]
            desired_column = min(
                target_line.start_at + preferred_column,
                target_line.start_at + len(target_line.text),
            )
            return target_line.line_index, desired_column
        return fallback_target
