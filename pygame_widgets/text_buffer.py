from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal


def _empty_callback() -> None:
    pass


@dataclass(order=True)
class Cursor:
    _line: int = 0
    _column: int = 0

    @property
    def line(self) -> int:
        return self._line

    @property
    def column(self) -> int:
        return self._column

    def set(self, line: int, column: int, lines: list[str]) -> None:
        if not lines:
            raise ValueError("Cannot set cursor on empty lines list")

        if not (0 <= line < len(lines)):
            raise ValueError(f"Line index {line} out of range (0-{len(lines) - 1})")

        if not (0 <= column <= len(lines[line])):
            raise ValueError(f"Column index {column} out of range for line {line}")

        self._line = line
        self._column = column


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
        self._selection_start = Cursor()
        self._selection_end = Cursor()

        self.tab_spaces = tab_spaces

        # TODO: Perhaps these attributes should be moved from here
        self.on_text_changed = on_text_changed
        self.on_text_changed_params = on_text_changed_params

        self.overwrite_mode = False

        if initial_text:
            self.text = initial_text

    @property
    def cursor(self) -> Cursor:
        return self._cursor

    @property
    def selection_start(self) -> Cursor:
        return self._selection_start

    @property
    def selection_end(self) -> Cursor:
        return self._selection_end

    @property
    def selected_text(self) -> str:
        start, end = self.get_normalized_selection()

        if start.line == end.line:
            return self._lines[start.line][start.column : end.column]

        result = []

        result.append(self._lines[start.line][start.column :])
        result.extend(self._lines[start.line + 1 : end.line])
        result.append(self._lines[end.line][: end.column])

        return "\n".join(result)

    @property
    def text(self) -> str:
        return "\n".join(self._lines)

    @text.setter
    def text(self, value: str) -> None:
        self._lines = [""]
        self.cursor.set(0, 0, self._lines)
        self.reset_selection()
        self.add_text(value, call_on_text_changed=False)

    def is_empty_text(self, text: list[str]) -> bool:
        return len(text) == 1 and text[0] == ""

    def is_word_char(self, character: str) -> bool:
        return character.isalnum() or character == "_"

    def is_empty_selection(self) -> bool:
        return (self.selection_start.line, self.selection_start.column) == (
            self.selection_end.line,
            self.selection_end.column,
        )

    def add_text(self, text: str, call_on_text_changed: bool = True) -> None:
        if not self.is_empty_selection():
            self.erase_selected_text(call_on_text_changed=False)

        text = str(text).replace("\t", " " * self.tab_spaces).replace("\r", "")
        lines = text.split("\n")

        right_part = (
            self._lines[self.cursor.line][self.cursor.column :]
            if not self.overwrite_mode
            else ""
        )

        for i, line in enumerate(lines):
            if self.overwrite_mode:
                right_part = self._lines[self.cursor.line][
                    self.cursor.column + len(line) :
                ]

            self._lines[self.cursor.line] = (
                self._lines[self.cursor.line][: self.cursor.column] + line
            )
            self.cursor.set(
                self.cursor.line, self.cursor.column + len(line), self._lines
            )

            if i != len(lines) - 1:
                self._lines.insert(self.cursor.line + 1, "")
                self.cursor.set(self.cursor.line + 1, 0, self._lines)

            if self.overwrite_mode or i == len(lines) - 1:
                self._lines[self.cursor.line] += right_part

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

        if not self.is_empty_selection():
            self.erase_selected_text()
            return

        erase_func()

    def _process_backspace(self) -> None:
        if self.cursor.column > 0:
            self._lines[self.cursor.line] = (
                self._lines[self.cursor.line][: self.cursor.column - 1]
                + self._lines[self.cursor.line][self.cursor.column :]
            )
            self.cursor.set(self.cursor.line, self.cursor.column - 1, self._lines)

            self.on_text_changed(*self.on_text_changed_params)

        elif self.cursor.line > 0:
            previous_line_length = len(self._lines[self.cursor.line - 1])
            self._lines[self.cursor.line - 1] += self._lines[self.cursor.line]
            self._lines.pop(self.cursor.line)
            self.cursor.set(self.cursor.line - 1, previous_line_length, self._lines)

            self.on_text_changed(*self.on_text_changed_params)

    def _process_delete(self) -> None:
        if self.cursor.column < len(self._lines[self.cursor.line]):
            self._lines[self.cursor.line] = (
                self._lines[self.cursor.line][: self.cursor.column]
                + self._lines[self.cursor.line][self.cursor.column + 1 :]
            )

            self.on_text_changed(*self.on_text_changed_params)

        elif self.cursor.line < len(self._lines) - 1:
            self._lines[self.cursor.line] += self._lines[self.cursor.line + 1]
            self._lines.pop(self.cursor.line + 1)

            self.on_text_changed(*self.on_text_changed_params)

    def erase_selected_text(self, call_on_text_changed: bool = True) -> None:
        start, end = self.get_normalized_selection()

        if start.line == end.line:
            self._lines[start.line] = (
                self._lines[start.line][: start.column]
                + self._lines[start.line][end.column :]
            )
        else:
            self._lines[start.line] = (
                self._lines[start.line][: start.column]
                + self._lines[end.line][end.column :]
            )
            del self._lines[start.line + 1 : end.line + 1]

        self.cursor.set(start.line, start.column, self._lines)
        self.reset_selection()

        if call_on_text_changed:
            self.on_text_changed(*self.on_text_changed_params)

    def get_normalized_selection(self) -> tuple[Cursor, Cursor]:
        if self.selection_start > self.selection_end:
            return self.selection_end, self.selection_start
        return self.selection_start, self.selection_end

    def select_all(self) -> None:
        self.selection_start.set(0, 0, self._lines)
        self.selection_end.set(len(self._lines) - 1, len(self._lines[-1]), self._lines)
        self.cursor.set(len(self._lines) - 1, len(self._lines[-1]), self._lines)

    def reset_selection(self) -> None:
        self.selection_start.set(0, 0, self._lines)
        self.selection_end.set(0, 0, self._lines)

    def move_cursor_word(self, direction: Literal["left", "right"]) -> None:
        line = self.cursor.line
        column = self.cursor.column
        current_line = self._lines[line]

        match direction:
            case "left":
                step, offset = -1, -1
                if column == 0 and line > 0:
                    line -= 1
                    current_line = self._lines[line]
                    column = len(current_line)
            case "right":
                step, offset = 1, 0
                if column == len(current_line) and line < len(self._lines) - 1:
                    line += 1
                    current_line = self._lines[line]
                    column = 0
            case _:
                raise ValueError(
                    "An incorrect direction value has been entered. Expected Literal['left', 'right']"
                )

        while 0 <= column + offset < len(current_line) and not self.is_word_char(
            current_line[column + offset]
        ):
            column += step

        while 0 <= column + offset < len(current_line) and self.is_word_char(
            current_line[column + offset]
        ):
            column += step

        self.cursor.set(line, column, self._lines)

    def move_cursor_horizontal(self, direction: Literal["left", "right"]) -> None:
        line = self.cursor.line
        column = self.cursor.column

        match direction:
            case "left":
                if column == 0 and line > 0:
                    line -= 1
                    column = len(self._lines[line])
                else:
                    column = max(column - 1, 0)
            case "right":
                if column == len(self._lines[line]) and line < len(self._lines) - 1:
                    line += 1
                    column = 0
                else:
                    column += 1
            case _:
                raise ValueError(
                    "An incorrect direction value has been entered. Expected Literal['left', 'right']"
                )

        self.cursor.set(line, column, self._lines)


if __name__ == "__main__":
    text_buffer = TextBuffer()
    text_buffer.add_text("hello\nworld")
    print("text:", text_buffer.text)
    text_buffer.selection_start.set(0, 1, text_buffer._lines)
    text_buffer.selection_end.set(0, 5, text_buffer._lines)
    print("selected text:", text_buffer.selected_text)
    text_buffer.erase_text(direction="backspace")
    print("text:", text_buffer.text)
    text_buffer.erase_text(direction="backspace")
    print("text:", text_buffer.text)
    text_buffer.erase_text(direction="delete")
    print("text:", text_buffer.text)
    print(text_buffer.cursor)
    text_buffer.add_text("glue ")
    print("text:", text_buffer.text)
    text_buffer.overwrite_mode = True
    text_buffer.add_text("cold")
    print("text:", text_buffer.text)
