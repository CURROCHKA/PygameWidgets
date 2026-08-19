from collections.abc import Callable
from typing import Literal, NamedTuple


def _empty_callback(*args) -> None:
    pass


class Cursor(NamedTuple):
    line: int = 0
    column: int = 0


class TextBuffer:
    def __init__(
        self,
        initial_text: str = "",
        tab_spaces: int = 4,
        on_text_changed: Callable = _empty_callback,
        on_text_changed_params: tuple | list = (),
    ) -> None:
        self._lines = [""]

        self._cursor = Cursor()
        self._selection_anchor: Cursor | None = None

        self.tab_spaces = tab_spaces

        # TODO: Perhaps these attributes should be moved from here. Outdated callback pattern
        self.on_text_changed = on_text_changed
        self.on_text_changed_params = on_text_changed_params

        self.overwrite_mode = False

        if initial_text:
            self.text = initial_text

    def _validate_cursor_coord(self, line: int, column: int) -> None:
        if not (0 <= line < len(self.lines)):
            raise ValueError(
                f"Line index {line} out of range (0 - {len(self.lines) - 1})"
            )

        if not (0 <= column <= len(self.lines[line])):
            raise ValueError(f"Column index {column} out of range for line {line}")

    @property
    def cursor(self) -> Cursor:
        return self._cursor

    def set_cursor_coord(self, line: int, column: int) -> None:
        self._validate_cursor_coord(line, column)
        self._cursor = Cursor(line, column)

    @property
    def selection_anchor(self) -> Cursor | None:
        return self._selection_anchor

    def set_selection_anchor_coord(self, line: int, column: int) -> None:
        self._validate_cursor_coord(line, column)
        self._selection_anchor = Cursor(line, column)

    @property
    def selected_text(self) -> str:
        selection = self.selection
        if not selection:
            return ""

        start, end = selection

        if start.line == end.line:
            return self.lines[start.line][start.column : end.column]

        result = []

        result.append(self.lines[start.line][start.column :])
        result.extend(self.lines[start.line + 1 : end.line])
        result.append(self.lines[end.line][: end.column])

        return "\n".join(result)

    @property
    def lines(self) -> list[str]:
        # TODO: Protect for API (text_buffer.lines.clear() may brake the system)
        return self._lines

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @text.setter
    def text(self, value: str) -> None:
        self._lines = [""]
        self._cursor = Cursor(0, 0)
        self.reset_selection()
        self.add_text(
            value, call_on_text_changed=False
        )  # TODO: Maybe it's worth setting a new flag or always pass call_on_text_changed=True

    def is_empty_lines(self, lines: list[str]) -> bool:
        return len(lines) == 1 and lines[0] == ""

    def is_word_char(self, character: str) -> bool:
        return character.isalnum() or character == "_"

    def is_empty_selection(self) -> bool:
        return self.selection_anchor is None or self.selection_anchor == self.cursor

    @property
    def selection(self) -> tuple[Cursor, Cursor] | None:
        if self.is_empty_selection():
            return None
        if self.cursor < self.selection_anchor:
            return self.cursor, self.selection_anchor
        return self.selection_anchor, self.cursor

    def add_text(self, text: str, call_on_text_changed: bool = True) -> None:
        self.erase_selected_text(call_on_text_changed=False)

        text = (
            text.replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\t", " " * self.tab_spaces)
        )
        lines = text.split("\n")

        right_part = self.lines[self.cursor.line][self.cursor.column :]

        for i, line in enumerate(lines):
            if self.overwrite_mode:
                right_part = self.lines[self.cursor.line][
                    self.cursor.column + len(line) :
                ]

            self.lines[self.cursor.line] = (
                self.lines[self.cursor.line][: self.cursor.column] + line
            )
            self._cursor = Cursor(self.cursor.line, self.cursor.column + len(line))

            if i != len(lines) - 1:
                self.lines.insert(self.cursor.line + 1, "")
                self._cursor = Cursor(self.cursor.line + 1, 0)

            if self.overwrite_mode:
                self.lines[self.cursor.line] += right_part

        if not self.overwrite_mode:
            self.lines[self.cursor.line] += right_part

        if call_on_text_changed:
            self.on_text_changed(*self.on_text_changed_params)

    def erase_text(self, direction: Literal["backspace", "delete"]) -> None:
        match direction:
            case "backspace":
                erase_func = self._process_backspace
            case "delete":
                erase_func = self._process_delete
            case _:
                raise ValueError(
                    "An incorrect direction value has been entered. Expected Literal['backspace', 'delete']"
                )

        if self.erase_selected_text():
            return

        erase_func()
        self.reset_selection()

    def _process_backspace(self) -> None:
        if self.cursor.column > 0:
            self.lines[self.cursor.line] = (
                self.lines[self.cursor.line][: self.cursor.column - 1]
                + self.lines[self.cursor.line][self.cursor.column :]
            )
            self._cursor = Cursor(self.cursor.line, self.cursor.column - 1)

            self.on_text_changed(*self.on_text_changed_params)

        elif self.cursor.line > 0:
            previous_line_length = len(self.lines[self.cursor.line - 1])
            self.lines[self.cursor.line - 1] += self.lines[self.cursor.line]
            self.lines.pop(self.cursor.line)
            self._cursor = Cursor(self.cursor.line - 1, previous_line_length)

            self.on_text_changed(*self.on_text_changed_params)

    def _process_delete(self) -> None:
        if self.cursor.column < len(self.lines[self.cursor.line]):
            self.lines[self.cursor.line] = (
                self.lines[self.cursor.line][: self.cursor.column]
                + self.lines[self.cursor.line][self.cursor.column + 1 :]
            )

            self.on_text_changed(*self.on_text_changed_params)

        elif self.cursor.line < len(self.lines) - 1:
            self.lines[self.cursor.line] += self.lines[self.cursor.line + 1]
            self.lines.pop(self.cursor.line + 1)

            self.on_text_changed(*self.on_text_changed_params)

    def erase_selected_text(self, call_on_text_changed: bool = True) -> bool:
        selection = self.selection
        if not selection:
            return False

        start, end = selection

        if start.line == end.line:
            self.lines[start.line] = (
                self.lines[start.line][: start.column]
                + self.lines[start.line][end.column :]
            )
        else:
            self.lines[start.line] = (
                self.lines[start.line][: start.column]
                + self.lines[end.line][end.column :]
            )
            del self.lines[start.line + 1 : end.line + 1]

        self._cursor = Cursor(start.line, start.column)
        self.reset_selection()

        if call_on_text_changed:
            self.on_text_changed(*self.on_text_changed_params)

        return True

    def select_all(self) -> None:
        self._selection_anchor = Cursor(0, 0)
        self._cursor = Cursor(len(self.lines) - 1, len(self.lines[-1]))

    def reset_selection(self) -> None:
        self._selection_anchor = None

    def move_cursor_word(
        self, direction: Literal["left", "right"], select: bool = False
    ) -> None:
        line = self.cursor.line
        column = self.cursor.column
        current_line = self.lines[line]

        match direction:
            case "left":
                step, offset = -1, -1
                if column == 0 and line > 0:
                    line -= 1
                    current_line = self.lines[line]
                    column = len(current_line)
            case "right":
                step, offset = 1, 0
                if column == len(current_line) and line < len(self.lines) - 1:
                    line += 1
                    current_line = self.lines[line]
                    column = 0
            case _:
                raise ValueError(
                    "An incorrect direction value has been entered. Expected Literal['left', 'right']"
                )

        if self.is_empty_selection() and select:
            self._selection_anchor = Cursor(self.cursor.line, self.cursor.column)

        while 0 <= column + offset < len(current_line) and not self.is_word_char(
            current_line[column + offset]
        ):
            column += step

        while 0 <= column + offset < len(current_line) and self.is_word_char(
            current_line[column + offset]
        ):
            column += step

        self._cursor = Cursor(line, column)

        if not select:
            self.reset_selection()

    def move_cursor_horizontal(
        self, direction: Literal["left", "right"], select: bool = False
    ) -> None:
        line = self.cursor.line
        column = self.cursor.column
        selection = self.selection

        match direction:
            case "left":
                if selection and not select:
                    line = selection[0].line
                    column = selection[0].column
                elif column == 0 and line > 0:
                    line -= 1
                    column = len(self.lines[line])
                else:
                    column = max(column - 1, 0)
            case "right":
                if selection and not select:
                    line = selection[1].line
                    column = selection[1].column
                elif column == len(self.lines[line]) and line < len(self.lines) - 1:
                    line += 1
                    column = 0
                else:
                    column += 1
            case _:
                raise ValueError(
                    "An incorrect direction value has been entered. Expected Literal['left', 'right']"
                )

        if not selection and select:
            self._selection_anchor = Cursor(self.cursor.line, self.cursor.column)

        line = max(0, min(len(self.lines) - 1, line))
        column = max(0, min(len(self.lines[line]), column))
        self._cursor = Cursor(line, column)

        if not select:
            self.reset_selection()


if __name__ == "__main__":
    text_buffer = TextBuffer()
    text_buffer.add_text("hello world")
    # text_buffer.lines.clear()
    print("text:", repr(text_buffer.text))
    text_buffer.overwrite_mode = True
    text_buffer.set_cursor_coord(0, 5)
    text_buffer.add_text("a\nb")
    print("text:", repr(text_buffer.text))
    text_buffer.set_selection_anchor_coord(0, 1)
    text_buffer.set_cursor_coord(0, 5)
    print("selected text:", repr(text_buffer.selected_text))
    text_buffer.erase_text(direction="backspace")
    print("text:", repr(text_buffer.text))
    text_buffer.erase_text(direction="backspace")
    print("text:", repr(text_buffer.text))
    text_buffer.erase_text(direction="delete")
    print("text:", repr(text_buffer.text))
    print(text_buffer.cursor)
    text_buffer.add_text("glue ")
    print("text:", repr(text_buffer.text))
    text_buffer.overwrite_mode = True
    text_buffer.add_text("cold")
    print("text:", repr(text_buffer.text))
