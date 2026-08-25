from collections.abc import Callable
from typing import NamedTuple


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

        self._cursor = Cursor(0, 0)
        self._selection_anchor: Cursor | None = None

        self.tab_spaces = tab_spaces

        # TODO: Perhaps these attributes should be moved from here. Outdated callback pattern
        self.on_text_changed = on_text_changed
        self.on_text_changed_params = on_text_changed_params

        self._overwrite_mode = False

        if initial_text:
            self._set_text(initial_text, False)

    def _validate_cursor_coord(self, line: int, column: int) -> None:
        if not (0 <= line < len(self._lines)):
            raise ValueError(
                f"Line index {line} out of range (0 - {len(self._lines) - 1})"
            )

        if not (0 <= column <= len(self._lines[line])):
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
        self._set_text(value, True)

    def _set_text(self, text: str, call_on_text_changed: bool) -> None:
        self._lines = [""]
        self._cursor = Cursor(0, 0)
        self.reset_selection()
        self.add_text(text, call_on_text_changed)

    def is_empty_lines(self) -> bool:
        return self._lines == [""]

    @staticmethod
    def is_word_char(character: str) -> bool:
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

    def get_lines_from_text(self, text: str) -> list[str]:
        text = text.replace("\t", " " * self.tab_spaces)
        lines = text.splitlines(keepends=True)
        return lines

    def add_text(self, text: str, call_on_text_changed: bool = True) -> None:
        if (
            self.overwrite_mode
            and len(text) == 1
            and text not in "\r\n"
            and self.is_empty_selection()
        ):
            offset = 1
        else:
            offset = 0

        self.delete_selected_text(call_on_text_changed=False)

        lines = self.get_lines_from_text(text)
        cursor_line, cursor_column = self.cursor

        left_part = self._lines[cursor_line][:cursor_column]
        right_part = self._lines[cursor_line][cursor_column + offset :]

        if len(lines) == 1:
            self._lines[cursor_line] = left_part + lines[0] + right_part
            self._cursor = Cursor(cursor_line, cursor_column + len(lines[0]))
        else:
            lines[0] = left_part + lines[0]
            lines[-1] = lines[-1] + right_part

            self._lines[cursor_line : cursor_line + 1] = lines

            self._cursor = Cursor(
                cursor_line + len(lines) - 1, len(lines[-1]) - len(right_part)
            )

        if call_on_text_changed:
            self.on_text_changed(*self.on_text_changed_params)

    def delete_left(self) -> str:
        deleted_selected_text = self.delete_selected_text()
        if deleted_selected_text:
            return deleted_selected_text

        deleted_text = ""
        if self.cursor.column > 0:
            deleted_text = self._lines[self.cursor.line][self.cursor.column - 1]
            self._lines[self.cursor.line] = (
                self._lines[self.cursor.line][: self.cursor.column - 1]
                + self._lines[self.cursor.line][self.cursor.column :]
            )
            self._cursor = Cursor(self.cursor.line, self.cursor.column - 1)

            self.on_text_changed(*self.on_text_changed_params)

        elif self.cursor.line > 0:
            deleted_text = "\n"
            previous_line_length = len(self._lines[self.cursor.line - 1])
            self._lines[self.cursor.line - 1] += self._lines[self.cursor.line]
            self._lines.pop(self.cursor.line)
            self._cursor = Cursor(self.cursor.line - 1, previous_line_length)

            self.on_text_changed(*self.on_text_changed_params)

        self.reset_selection()
        return deleted_text

    def delete_right(self) -> str:
        deleted_selected_text = self.delete_selected_text()
        if deleted_selected_text:
            return deleted_selected_text

        deleted_text = ""
        if self.cursor.column < len(self._lines[self.cursor.line]):
            deleted_text = self._lines[self.cursor.line][self.cursor.column]
            self._lines[self.cursor.line] = (
                self._lines[self.cursor.line][: self.cursor.column]
                + self._lines[self.cursor.line][self.cursor.column + 1 :]
            )

            self.on_text_changed(*self.on_text_changed_params)

        elif self.cursor.line < len(self._lines) - 1:
            deleted_text = "\n"
            self._lines[self.cursor.line] += self._lines[self.cursor.line + 1]
            self._lines.pop(self.cursor.line + 1)

            self.on_text_changed(*self.on_text_changed_params)

        self.reset_selection()
        return deleted_text

    def delete_selected_text(self, call_on_text_changed: bool = True) -> str:
        selection = self.selection
        if not selection:
            return ""

        start, end = selection
        deleted_text = self.selected_text

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

        self._cursor = Cursor(start.line, start.column)
        self.reset_selection()

        if call_on_text_changed:
            self.on_text_changed(*self.on_text_changed_params)

        return deleted_text

    def select_all(self) -> None:
        self._selection_anchor = Cursor(0, 0)
        self._cursor = Cursor(len(self._lines) - 1, len(self._lines[-1]))

    def reset_selection(self) -> None:
        self._selection_anchor = None

    def _clamp_cursor(self, line: int, column: int) -> None:
        line = max(0, min(len(self._lines) - 1, line))
        column = max(0, min(len(self._lines[line]), column))
        self._cursor = Cursor(line, column)

    def _apply_cursor_move(self, line: int, column: int, select: bool) -> None:
        self._clamp_cursor(line, column)

        if not select or self.is_empty_selection():
            self.reset_selection()

    def move_cursor_word_left(self, select: bool = False) -> None:
        line, column = self.cursor
        current_line = self._lines[line]

        if column == 0 and line > 0:
            line -= 1
            current_line = self._lines[line]
            column = len(current_line)

        if self.is_empty_selection() and select:
            self._selection_anchor = Cursor(*self.cursor)

        while 0 <= column - 1 and not self.is_word_char(current_line[column - 1]):
            column -= 1

        while 0 <= column - 1 and self.is_word_char(current_line[column - 1]):
            column -= 1

        self._apply_cursor_move(line, column, select)

    def move_cursor_word_right(self, select: bool = False) -> None:
        line, column = self.cursor
        current_line = self._lines[line]

        if column == len(current_line) and line < len(self._lines) - 1:
            line += 1
            current_line = self._lines[line]
            column = 0

        if self.is_empty_selection() and select:
            self._selection_anchor = Cursor(*self.cursor)

        while column < len(current_line) and not self.is_word_char(
            current_line[column]
        ):
            column += 1

        while column < len(current_line) and self.is_word_char(current_line[column]):
            column += 1

        self._apply_cursor_move(line, column, select)

    def move_cursor_left(self, select: bool = False) -> None:
        line, column = self.cursor
        selection = self.selection

        if selection and not select:
            line, column = selection[0]
        elif column == 0 and line > 0:
            line -= 1
            column = len(self._lines[line])
        else:
            column = max(column - 1, 0)

        if not selection and select:
            self._selection_anchor = Cursor(*self.cursor)

        self._apply_cursor_move(line, column, select)

    def move_cursor_right(self, select: bool = False) -> None:
        line, column = self.cursor
        selection = self.selection

        if selection and not select:
            line, column = selection[1]
        elif column == len(self._lines[line]) and line < len(self._lines) - 1:
            line += 1
            column = 0
        else:
            column += 1

        if not selection and select:
            self._selection_anchor = Cursor(*self.cursor)

        self._apply_cursor_move(line, column, select)

    @property
    def overwrite_mode(self) -> bool:
        return self._overwrite_mode

    def enable_overwrite_mode(self) -> None:
        self._overwrite_mode = True

    def disable_overwrite_mode(self) -> None:
        self._overwrite_mode = False

    def switch_overwrite_mode(self) -> None:
        self._overwrite_mode = not self.overwrite_mode


if __name__ == "__main__":
    text_buffer = TextBuffer()
    text_buffer.add_text("hello world")
    print("text:", repr(text_buffer.text))
    text_buffer.enable_overwrite_mode()
    text_buffer.set_cursor_coord(0, 5)
    text_buffer.add_text("a\nb")
    print("text:", repr(text_buffer.text))
    text_buffer.set_selection_anchor_coord(0, 1)
    text_buffer.set_cursor_coord(0, 5)
    print("selected text:", repr(text_buffer.selected_text))
    text_buffer.delete_left()
    print("text:", repr(text_buffer.text))
    text_buffer.delete_left()
    print("text:", repr(text_buffer.text))
    text_buffer.delete_right()
    print("text:", repr(text_buffer.text))
    print(text_buffer.cursor)
    text_buffer.add_text("glue ")
    print("text:", repr(text_buffer.text))
    text_buffer.disable_overwrite_mode()
    text_buffer.add_text("cold")
    print("text:", repr(text_buffer.text))
