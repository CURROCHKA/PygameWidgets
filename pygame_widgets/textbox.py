import pyperclip
import sys

import pygame
import pygame.freetype
from pygame.typing import ColorLike

import pygame_widgets
from pygame_widgets.widget import WidgetBase
from pygame_widgets.mouse import Mouse, MouseState

from dataclasses import dataclass, field, replace
from collections import OrderedDict

from typing import Literal, NamedTuple


def _emptyCallback() -> None:
    pass


@dataclass(order=True)
class Cursor:
    line: int = 0
    column: int = 0
    preferredColumn: int = field(default=0, compare=False)

    def clamp(self, lines: list[str]) -> None:
        self.line = max(0, min(self.line, len(lines) - 1))
        self.column = max(0, min(self.column, len(lines[self.line])))

    def set(self, line: int, column: int, lines: list[str]) -> None:
        self.line = line
        self.column = column
        self.clamp(lines)


class VisualLine(NamedTuple):
    text: str
    lineIndex: int
    startAt: int
    prefixWidths: list[int]

    def getOffset(self, column: int) -> int:
        """Return the x offset for a cursor column within this visual line.

        ``column`` is local to this visual fragment, not the original logical
        line. Out-of-range values are clamped so drawing code can safely ask for
        the start or end offset without repeating bounds checks.

        Args:
            column: Cursor column local to this visual line.

        Returns:
            Pixel offset from the visual line's left edge.
        """
        column = max(0, min(column, len(self.prefixWidths) - 1))
        return self.prefixWidths[column]


@dataclass
class TextBoxStyle:
    colour: tuple[int, int, int] = (220, 220, 220)
    borderThickness: int = 3
    borderColour: tuple[int, int, int] = (0, 0, 0)
    radius: int = 0

    fontSize: int = 20
    font: pygame.freetype.Font | None = None
    textColour: tuple[int, int, int] = (0, 0, 0)

    cursorWidth: int = 2
    cursorColour: tuple[int, int, int] = (0, 0, 0)
    cursorAlpha: int = 63

    selectionColour: tuple[int, int, int] = (166, 210, 255)
    textColourUnderSelection: tuple[int, int, int] = (
        255,
        255,
        255,
    )

    placeholderTextColour: tuple[int, int, int] = (10, 10, 10)

    readOnly: bool = False
    tabSpaces: int = 4

    linesPerScroll: int = 1


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
        placeholderText: str = '',
        repeatDelay: float = REPEAT_DELAY,
        repeatInterval: float = REPEAT_INTERVAL,
        cursorInterval: float = CURSOR_INTERVAL,
        doubleClickInterval: float = DOUBLE_CLICK_INTERVAL,
        onSubmit: callable = _emptyCallback,
        onSubmitParams: tuple = (),
        onTextChanged: callable = _emptyCallback,
        onTextChangedParams: tuple = (),
        style: TextBoxStyle = None,
        isSubWidget=False,
        **kwargs,
    ) -> None:
        super().__init__(win, x, y, width, height, isSubWidget)

        if not pygame.get_init():
            pygame.init()

        styleKwargs = {
            k: v for k, v in kwargs.items() if k in TextBoxStyle.__dataclass_fields__
        }
        if style is None:
            self.style = TextBoxStyle(**styleKwargs)
        else:
            self.style = replace(style, **styleKwargs)

        if isinstance(self.style.font, pygame.freetype.Font):
            self.font = self.style.font
        else:
            if self.style.font is not None:
                print('Use pygame.freetype.Font or pygame.freetype.SysFont')
            self.font = pygame.freetype.SysFont('calibri', self.style.fontSize)
        self.font.pad = True

        # Widget state
        self.selected = False
        self.keyDown = False
        self.repeatTime = 0
        self.repeatEvent = None
        self.firstRepeat = True
        self.insertOn = False
        self.showCursor = not self.style.readOnly
        self.cursorTime = 0
        self.lastClickTime = 0

        self.repeatDelay = repeatDelay
        self.repeatInterval = repeatInterval
        self.cursorInterval = cursorInterval
        self.doubleClickInterval = doubleClickInterval

        # Cursor state and style
        self.cursor = Cursor()
        self.selectionStart = Cursor()
        self.selectionEnd = Cursor()

        # Text state
        self.text = ['']
        self.placeholderText = placeholderText
        self.cachedVisualLines: list[VisualLine] = [
            VisualLine(text='', lineIndex=0, startAt=0, prefixWidths=[0])
        ]
        self.visualLineRanges: dict[int, tuple[int, int]] = {0: (0, 1)}

        # Margins
        self.textOffsetTop = self.style.fontSize // 3
        self.textOffsetLeft = self.style.fontSize // 3
        self.textOffsetRight = self.style.fontSize // 2

        # Callback
        self.onSubmit = onSubmit
        self.onSubmitParams = onSubmitParams
        self.onTextChanged = onTextChanged
        self.onTextChangedParams = onTextChangedParams

        # Cache
        self._widthCache = OrderedDict()
        self._renderedTextCache = OrderedDict()

        # Layout
        self.firstVisibleLineIndex = 0
        self.reconfigureLayout()

    def reconfigureLayout(self) -> None:
        self._actualWidth = (
            self._width
            - self.textOffsetRight
            - self.textOffsetLeft
            - self.style.borderThickness * 2
        )
        self._actualHeight = (
            self._height - self.textOffsetTop - self.style.borderThickness * 2
        )
        self.lineHeight = self.style.fontSize
        self._actualX = self._x + self.textOffsetLeft + self.style.borderThickness
        self._actualY = self._y + self.textOffsetTop + self.style.borderThickness

        self.maxVisibleLines = max(1, self._actualHeight // self.lineHeight)

        self.setVisualLines()

    def listen(self, events: list[pygame.event.Event]) -> None:
        if self._hidden or self._disabled:
            return

        if self.keyDown:
            self.updateRepeatEvent()

        self.handleMouse()

        if self.selected:
            for event in events:
                if event.type == pygame.KEYDOWN:
                    self.handleKeyDown(event)

                elif event.type == pygame.TEXTINPUT:
                    self.handleTextInput(event)

                elif event.type == pygame.KEYUP:
                    if (
                        self.repeatEvent is not None
                        and self.repeatEvent.type == pygame.KEYDOWN
                        and event.key == self.repeatEvent.key
                    ):
                        self.repeatEvent = None
                        self.keyDown = False
                        self.firstRepeat = True

    def handleMouse(self) -> None:
        mouseState = Mouse.getMouseState()
        x, y = Mouse.getMousePos()

        if mouseState == MouseState.CLICK:
            self.processMouseClick(x, y)

        if self.selected:
            if mouseState == MouseState.DRAG:
                self.processMouseDrag(x, y)

            elif mouseState == MouseState.DOUBLE_CLICK:
                self.processMouseDoubleClick()

            elif mouseState == MouseState.TRIPLE_CLICK:
                self.processMouseTripleClick()

        if mouseState == MouseState.WHEEL_MOTION and self.contains(x, y):
            self.processMouseScroll()

    def handleKeyDown(self, event: pygame.Event) -> None:
        if event.mod & pygame.KMOD_ALT:
            return

        now = pygame.time.get_ticks()
        self.showCursor = True
        self.cursorTime = now
        self.keyDown = True
        self.repeatEvent = event
        self.repeatTime = now

        if event.key == pygame.K_BACKSPACE:
            self.eraseText(event, direction=-1)

        elif event.key == pygame.K_DELETE:
            self.eraseText(event, direction=1)

        elif event.key == pygame.K_RETURN:
            self.processReturn(event)

        elif event.key == pygame.K_UP or (
            event.key == pygame.K_KP_8 and not event.mod & pygame.KMOD_NUM
        ):
            self.moveCursorVertical(event, direction=-1)

        elif event.key == pygame.K_DOWN or (
            event.key == pygame.K_KP_2 and not event.mod & pygame.KMOD_NUM
        ):
            self.moveCursorVertical(event, direction=1)

        elif event.key == pygame.K_LEFT or (
            event.key == pygame.K_KP_4 and not event.mod & pygame.KMOD_NUM
        ):
            self.moveCursorHorizontal(event, direction=-1)

        elif event.key == pygame.K_RIGHT or (
            event.key == pygame.K_KP_6 and not event.mod & pygame.KMOD_NUM
        ):
            self.moveCursorHorizontal(event, direction=1)

        elif event.key == pygame.K_HOME or (
            event.key == pygame.K_KP_7 and not event.mod & pygame.KMOD_NUM
        ):
            self.jumpToEdge(event, direction=-1)

        elif event.key == pygame.K_END or (
            event.key == pygame.K_KP_1 and not event.mod & pygame.KMOD_NUM
        ):
            self.jumpToEdge(event, direction=1)

        elif event.key == pygame.K_a and event.mod & pygame.KMOD_CTRL:
            self.selectAll()

        elif event.key == pygame.K_c and event.mod & pygame.KMOD_CTRL:
            self.copy()

        elif event.key == pygame.K_v and event.mod & pygame.KMOD_CTRL:
            self.paste()

        elif event.key == pygame.K_x and event.mod & pygame.KMOD_CTRL:
            self.cut()

        elif event.key == pygame.K_INSERT or (
            event.key == pygame.K_KP_0 and not event.mod & pygame.KMOD_NUM
        ):
            self.processInsert()

        elif event.key == pygame.K_ESCAPE:
            self.escape()

    def handleTextInput(self, event: pygame.Event) -> None:
        if not self.style.readOnly:
            now = pygame.time.get_ticks()
            self.showCursor = True
            self.cursorTime = now
            if len(event.text) != 0:
                self.addText(event.text)

    def draw(self) -> None:
        if self._hidden:
            return
        if self.selected:
            self.updateCursor()
        self._drawBorder()
        self._drawBackground()
        self._drawSelection()
        self._drawText()
        self._drawCursor()

    def _drawText(self) -> None:
        if self.isEmptyText(self.text):
            displayLines = [
                VisualLine(
                    text=self.placeholderText,
                    lineIndex=0,
                    startAt=0,
                    prefixWidths=[0],
                )
            ]
            colour = self.style.placeholderTextColour
        else:
            displayLines = self.cachedVisualLines
            colour = self.style.textColour

        if not self.isEmptySelection():
            start, end = self.getNormalizedSelection()

        for i in range(
            self.firstVisibleLineIndex,
            min(self.firstVisibleLineIndex + self.maxVisibleLines, len(displayLines)),
        ):
            visualLine = displayLines[i]

            lineY = self._actualY + (i - self.firstVisibleLineIndex) * self.lineHeight

            if (
                self.isEmptySelection()
                or not start.line <= visualLine.lineIndex <= end.line
            ):
                textSurface = self.getRenderedTextSurface(visualLine.text, colour)
                self.win.blit(textSurface, (self._actualX, lineY))

            else:
                startColumn = start.column if visualLine.lineIndex == start.line else 0
                endColumn = (
                    end.column
                    if visualLine.lineIndex == end.line
                    else len(self.text[visualLine.lineIndex])
                )

                localStart = max(0, startColumn - visualLine.startAt)
                localEnd = min(len(visualLine.text), endColumn - visualLine.startAt)

                textBeforeSelection = visualLine.text[:localStart]
                textUnderSelection = visualLine.text[localStart:localEnd]
                textAfterSelection = visualLine.text[localEnd:]

                if textBeforeSelection:
                    textSurface = self.getRenderedTextSurface(
                        textBeforeSelection, colour
                    )
                    self.win.blit(textSurface, (self._actualX, lineY))

                if textUnderSelection:
                    textSurface = self.getRenderedTextSurface(
                        textUnderSelection, self.style.textColourUnderSelection
                    )
                    self.win.blit(
                        textSurface,
                        (self._actualX + visualLine.getOffset(localStart), lineY),
                    )

                if textAfterSelection:
                    textSurface = self.getRenderedTextSurface(
                        textAfterSelection, colour
                    )
                    self.win.blit(
                        textSurface,
                        (self._actualX + visualLine.getOffset(localEnd), lineY),
                    )

    def _drawCursor(self) -> None:
        if self.selected and self.showCursor:
            visualLineIndex = self.getVisualLineIndex(self.cursor)

            if not (
                self.firstVisibleLineIndex
                <= visualLineIndex
                < self.firstVisibleLineIndex + self.maxVisibleLines
            ):
                return

            if visualLineIndex != -1:
                visualLine = self.cachedVisualLines[visualLineIndex]

                localStart = self.cursor.column - visualLine.startAt
                startX = self._actualX + visualLine.getOffset(localStart)
                endX = startX

                startY = self._actualY + self.lineHeight * (
                    visualLineIndex - self.firstVisibleLineIndex
                )
                endY = startY + self.lineHeight

                if not self.insertOn:
                    pygame.draw.line(
                        self.win,
                        self.style.cursorColour,
                        (startX, startY),
                        (endX, endY),
                        self.style.cursorWidth,
                    )
                else:
                    if self.cursor.column == len(self.text[self.cursor.line]):
                        textSurface = self.getRenderedTextSurface(
                            ' ', self.style.textColour
                        )
                    else:
                        textSurface = self.getRenderedTextSurface(
                            self.text[self.cursor.line][self.cursor.column],
                            self.style.textColour,
                        )
                    cursorSurface = pygame.Surface(textSurface.get_size())
                    cursorSurface.fill(self.style.cursorColour)
                    cursorSurface.set_alpha(self.style.cursorAlpha)
                    self.win.blit(cursorSurface, (startX, startY))

    def _drawBorder(self) -> None:
        pygame.draw.rect(
            self.win,
            self.style.borderColour,
            (self._x, self._y, self._width, self._height),
            border_radius=self.style.radius,
        )

    def _drawBackground(self) -> None:
        rect = (
            self._x + self.style.borderThickness,
            self._y + self.style.borderThickness,
            self._width - self.style.borderThickness * 2,
            self._height - self.style.borderThickness * 2,
        )
        pygame.draw.rect(
            self.win, self.style.colour, rect, border_radius=self.style.radius
        )

    def _drawSelection(self) -> None:
        if self.isEmptySelection():
            return

        start, end = self.getNormalizedSelection()

        for i in range(
            self.firstVisibleLineIndex,
            min(
                self.firstVisibleLineIndex + self.maxVisibleLines,
                len(self.cachedVisualLines),
            ),
        ):
            visualLine = self.cachedVisualLines[i]

            lineIndex = visualLine.lineIndex

            if not (start.line <= lineIndex <= end.line):
                continue

            lineY = self._actualY + self.lineHeight * (i - self.firstVisibleLineIndex)

            lineStart = visualLine.startAt

            selectionStart = start.column if lineIndex == start.line else 0
            selectionEnd = (
                end.column if lineIndex == end.line else len(self.text[lineIndex])
            )

            localStart = max(0, selectionStart - lineStart)
            localEnd = min(len(visualLine.text), selectionEnd - lineStart)

            if localStart > localEnd:
                continue

            isEmptyLine = len(self.text[lineIndex]) == 0

            isEndOfLogicalLine = (
                lineIndex < end.line
                and localEnd == len(visualLine.text)
                and visualLine.startAt + len(visualLine.text)
                == len(self.text[lineIndex])
            )

            if localStart == localEnd and not (isEmptyLine or isEndOfLogicalLine):
                continue

            textBeforeWidth = visualLine.getOffset(localStart)
            textUpToEndWidth = visualLine.getOffset(localEnd)

            textWidth = textUpToEndWidth - textBeforeWidth

            if isEmptyLine or isEndOfLogicalLine:
                textWidth += self.getTextWidth(' ')

            pygame.draw.rect(
                self.win,
                self.style.selectionColour,
                (self._actualX + textBeforeWidth, lineY, textWidth, self.lineHeight),
            )

    def processMouseClick(self, x: int, y: int) -> None:
        if self.contains(x, y):
            now = pygame.time.get_ticks()
            self.lastClickTime = now

            self.selected = True
            self.showCursor = True
            self.cursorTime = now

            self.setCursorFromMouse(x, y)
            self.resetSelection()
            self.setPreferredColumn()
        else:
            self.escape()

    def processMouseDrag(self, x: int, y: int) -> None:
        self.cursorTime = pygame.time.get_ticks()
        self.setCursorFromMouse(x, y)
        self.selectionEnd.set(self.cursor.line, self.cursor.column, self.text)
        self.setPreferredColumn()

        if y < self._actualY:
            self.firstVisibleLineIndex = max(0, self.firstVisibleLineIndex - 1)
        elif y > self._actualY + self._actualHeight:
            maxScroll = max(0, len(self.cachedVisualLines) - self.maxVisibleLines)
            self.firstVisibleLineIndex = min(maxScroll, self.firstVisibleLineIndex + 1)

    def processMouseDoubleClick(self) -> None:
        self.moveCursorWord(direction=-1)
        self.selectionStart.set(self.cursor.line, self.cursor.column, self.text)
        self.moveCursorWord(direction=1)
        self.selectionEnd.set(self.cursor.line, self.cursor.column, self.text)

    def processMouseTripleClick(self) -> None:
        self.selectionStart.set(self.cursor.line, 0, self.text)
        self.selectionEnd.set(
            self.cursor.line, len(self.text[self.cursor.line]), self.text
        )

    def processMouseScroll(self) -> None:
        self.firstVisibleLineIndex -= Mouse.getWheelDelta() * self.style.linesPerScroll
        maxScroll = max(0, len(self.cachedVisualLines) - self.maxVisibleLines)
        self.firstVisibleLineIndex = max(0, min(self.firstVisibleLineIndex, maxScroll))

    def processReturn(self, event: pygame.Event) -> None:
        if self.style.readOnly:
            return
        if event.mod & pygame.KMOD_SHIFT or event.mod & pygame.KMOD_CTRL:
            self.addText('\n')
        else:
            self.onSubmit(*self.onSubmitParams)

    def processBackspace(self) -> None:
        if self.cursor.column > 0:
            self.text[self.cursor.line] = (
                self.text[self.cursor.line][: self.cursor.column - 1]
                + self.text[self.cursor.line][self.cursor.column :]
            )
            self.cursor.set(self.cursor.line, self.cursor.column - 1, self.text)

            self.setVisualLines()
            self.setPreferredColumn()
            self.onTextChanged(*self.onTextChangedParams)

        elif self.cursor.line > 0:
            previousLineLength = len(self.text[self.cursor.line - 1])
            self.text[self.cursor.line - 1] += self.text[self.cursor.line]
            self.text.pop(self.cursor.line)
            self.cursor.set(self.cursor.line - 1, previousLineLength, self.text)

            self.setVisualLines()
            self.setPreferredColumn()
            self.onTextChanged(*self.onTextChangedParams)

    def processDelete(self) -> None:
        if self.cursor.column < len(self.text[self.cursor.line]):
            self.text[self.cursor.line] = (
                self.text[self.cursor.line][: self.cursor.column]
                + self.text[self.cursor.line][self.cursor.column + 1 :]
            )

            self.setVisualLines()
            self.setPreferredColumn()
            self.onTextChanged(*self.onTextChangedParams)

        elif self.cursor.line < len(self.text) - 1:
            self.text[self.cursor.line] += self.text[self.cursor.line + 1]
            self.text.pop(self.cursor.line + 1)

            self.setVisualLines()
            self.setPreferredColumn()
            self.onTextChanged(*self.onTextChangedParams)

    def eraseText(self, event: pygame.Event, direction: Literal[-1, 1]) -> None:
        if self.style.readOnly:
            return

        if not self.isEmptySelection():
            self.eraseSelectedText()
            return

        if event.mod & pygame.KMOD_CTRL:
            self.selectionStart.set(self.cursor.line, self.cursor.column, self.text)
            self.moveCursorWord(direction)
            self.selectionEnd.set(self.cursor.line, self.cursor.column, self.text)
            self.eraseSelectedText()
            return

        if direction == -1:
            self.processBackspace()

        elif direction == 1:
            self.processDelete()

        self.ensureCursorVisible()

    def eraseSelectedText(self, callOnTextChanged: bool = True) -> None:
        start, end = self.getNormalizedSelection()

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
        self.resetSelection()

        self.setVisualLines()
        self.setPreferredColumn()
        self.ensureCursorVisible()
        if callOnTextChanged:
            self.onTextChanged(*self.onTextChangedParams)

    def jumpToEdge(self, event: pygame.Event, direction: Literal[-1, 1]) -> None:
        shiftPressed = bool(event.mod & pygame.KMOD_SHIFT)

        if shiftPressed and self.isEmptySelection():
            self.selectionStart.set(self.cursor.line, self.cursor.column, self.text)

        if event.mod & pygame.KMOD_CTRL:
            line = 0 if direction == -1 else len(self.text) - 1
            column = 0 if direction == -1 else len(self.text[-1])
            self.cursor.set(line, column, self.text)
        else:
            visualLineIndex = self.getVisualLineIndex(self.cursor)
            if visualLineIndex != -1:
                visualLine = self.cachedVisualLines[visualLineIndex]
                column = visualLine.startAt
                if direction == 1:
                    column += len(visualLine.text)

                self.cursor.set(self.cursor.line, column, self.text)

        if event.mod & pygame.KMOD_SHIFT:
            self.selectionEnd.set(self.cursor.line, self.cursor.column, self.text)
        else:
            self.resetSelection()

        self.setPreferredColumn()
        self.ensureCursorVisible()

    def moveCursorVertical(
        self, event: pygame.Event, direction: Literal[-1, 1]
    ) -> None:
        shiftPressed = bool(event.mod & pygame.KMOD_SHIFT)

        if shiftPressed and self.isEmptySelection():
            self.selectionStart.set(self.cursor.line, self.cursor.column, self.text)

        baseCursor = Cursor(self.cursor.line, self.cursor.column)
        if not shiftPressed and not self.isEmptySelection():
            start, end = self.getNormalizedSelection()
            baseCursor = start if direction == -1 else end
            self.cursor.set(baseCursor.line, baseCursor.column, self.text)
            self.resetSelection()

        visualLineIndex = self.getVisualLineIndex(baseCursor)
        if visualLineIndex == -1:
            return

        targetIndex = visualLineIndex + direction

        if 0 <= targetIndex < len(self.cachedVisualLines):
            targetLine = self.cachedVisualLines[targetIndex]
            desiredColumn = min(
                targetLine.startAt + self.cursor.preferredColumn,
                targetLine.startAt + len(targetLine.text),
            )
            self.cursor.set(targetLine.lineIndex, desiredColumn, self.text)
        else:
            if direction == -1:
                self.cursor.set(self.cursor.line, 0, self.text)
            else:
                currentLine = self.cachedVisualLines[visualLineIndex]
                self.cursor.set(
                    self.cursor.line,
                    currentLine.startAt + len(currentLine.text),
                    self.text,
                )
            self.setPreferredColumn()

        if shiftPressed:
            self.selectionEnd.set(self.cursor.line, self.cursor.column, self.text)

        self.ensureCursorVisible()

    def moveCursorHorizontal(
        self, event: pygame.Event, direction: Literal[-1, 1]
    ) -> None:
        shiftPressed = bool(event.mod & pygame.KMOD_SHIFT)
        ctrlPressed = bool(event.mod & pygame.KMOD_CTRL)

        if not shiftPressed and not self.isEmptySelection():
            start, end = self.getNormalizedSelection()
            boundary = start if direction == -1 else end
            self.cursor.set(boundary.line, boundary.column, self.text)
            self.resetSelection()
            self.setPreferredColumn()
            self.ensureCursorVisible()
            return

        if shiftPressed and self.isEmptySelection():
            self.selectionStart.set(self.cursor.line, self.cursor.column, self.text)

        if ctrlPressed:
            self.moveCursorWord(direction)
        else:
            line = self.cursor.line
            col = self.cursor.column

            if direction == -1:
                if col == 0 and line > 0:
                    line -= 1
                    col = len(self.text[line])
                else:
                    col = max(col - 1, 0)
            elif direction == 1:
                if col == len(self.text[line]) and line < len(self.text) - 1:
                    line += 1
                    col = 0
                else:
                    col += 1

            self.cursor.set(line, col, self.text)

        if shiftPressed:
            self.selectionEnd.set(self.cursor.line, self.cursor.column, self.text)

        self.setPreferredColumn()
        self.ensureCursorVisible()

    def selectAll(self) -> None:
        self.selectionStart.set(0, 0, self.text)
        self.selectionEnd.set(len(self.text) - 1, len(self.text[-1]), self.text)
        self.cursor.set(len(self.text) - 1, len(self.text[-1]), self.text)

    def copy(self) -> None:
        if not self.isEmptySelection():
            pyperclip.copy(self.getSelectedText())

    def paste(self) -> None:
        if not self.style.readOnly:
            text = pyperclip.paste()
            if text:
                self.addText(text)

    def cut(self) -> None:
        self.copy()
        if not self.style.readOnly and not self.isEmptySelection():
            self.eraseSelectedText()

    def processInsert(self) -> None:
        self.insertOn = not self.insertOn

    def updateRepeatEvent(self) -> None:
        if self.repeatEvent is None:
            return

        now = pygame.time.get_ticks()

        if self.firstRepeat:
            if now - self.repeatTime >= self.repeatDelay:
                self.firstRepeat = False
                self.repeatTime = now
                self.handleKeyDown(self.repeatEvent)

        elif now - self.repeatTime >= self.repeatInterval:
            self.repeatTime = now
            self.handleKeyDown(self.repeatEvent)

    def ensureCursorVisible(self) -> None:
        visualLineIndex = self.getVisualLineIndex(self.cursor)
        if visualLineIndex == -1:
            return

        if visualLineIndex < self.firstVisibleLineIndex:
            self.firstVisibleLineIndex = visualLineIndex

        elif visualLineIndex >= self.firstVisibleLineIndex + self.maxVisibleLines:
            self.firstVisibleLineIndex = visualLineIndex - self.maxVisibleLines + 1

        maxScroll = max(0, len(self.cachedVisualLines) - self.maxVisibleLines)
        self.firstVisibleLineIndex = max(0, min(self.firstVisibleLineIndex, maxScroll))

    def updateLayout(self) -> None:
        self._actualHeight = (
            self._height - self.textOffsetTop - self.style.borderThickness * 2
        )

        self.maxVisibleLines = max(1, self._actualHeight // self.lineHeight)

    def addText(self, text: str, callOnTextChanged: bool = True) -> None:
        if not self.isEmptySelection():
            self.eraseSelectedText(callOnTextChanged=False)

        text = str(text).replace('\t', ' ' * self.style.tabSpaces).replace('\r', '')
        lines = text.split('\n')

        if not self.insertOn:
            rightPart = self.text[self.cursor.line][self.cursor.column :]

            for i, line in enumerate(lines):
                self.text[self.cursor.line] = (
                    self.text[self.cursor.line][: self.cursor.column] + line
                )
                self.cursor.set(
                    self.cursor.line, self.cursor.column + len(line), self.text
                )

                if i != len(lines) - 1:
                    self.text.insert(self.cursor.line + 1, '')
                    self.cursor.set(self.cursor.line + 1, 0, self.text)

            self.text[self.cursor.line] += rightPart

        else:
            for i, line in enumerate(lines):
                rightPart = self.text[self.cursor.line][
                    self.cursor.column + len(line) :
                ]

                self.text[self.cursor.line] = (
                    self.text[self.cursor.line][: self.cursor.column] + line
                )
                self.cursor.set(
                    self.cursor.line, self.cursor.column + len(line), self.text
                )

                if i != len(lines) - 1:
                    self.text.insert(self.cursor.line + 1, '')
                    self.cursor.set(self.cursor.line + 1, 0, self.text)

                self.text[self.cursor.line] += rightPart

        self.setVisualLines()
        self.setPreferredColumn()
        self.ensureCursorVisible()
        if callOnTextChanged:
            self.onTextChanged(*self.onTextChangedParams)

    def getNormalizedSelection(self) -> tuple[Cursor, Cursor]:
        if self.selectionStart > self.selectionEnd:
            return self.selectionEnd, self.selectionStart
        return self.selectionStart, self.selectionEnd

    def setVisualLines(self) -> None:
        """Rebuild the soft-wrapped visual-line cache from ``self.text``.

        ``self.text`` stores logical lines split only by hard newlines. This
        method derives ``cachedVisualLines`` for drawing, cursor navigation,
        selection and scrolling. ``visualLineRanges`` maps each logical line
        index to a half-open range in ``cachedVisualLines`` so lookups can scan
        only that line's wrapped fragments.

        Call this after text changes, or after layout/font changes once the
        widget's text area measurements have been refreshed.
        """
        self.cachedVisualLines = []
        self.visualLineRanges = {}

        for lineIndex, line in enumerate(self.text):
            rangeStart = len(self.cachedVisualLines)

            for visualLine in self._wrapLogicalLine(line, lineIndex):
                self.cachedVisualLines.append(visualLine)

            rangeEnd = len(self.cachedVisualLines)
            self.visualLineRanges[lineIndex] = (rangeStart, rangeEnd)

        self.updateLayout()

    def _wrapLogicalLine(self, line: str, lineIndex: int) -> list[VisualLine]:
        """Soft-wrap a single logical line into ``VisualLine`` fragments.

        ``line`` is one entry of ``self.text``. The returned fragments are in
        drawing order and all point back to ``lineIndex``; ``startAt`` stores
        the fragment's starting column in the original logical line.

        The loop asks ``findVisualLineEnd`` for the largest substring that fits
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
            lineIndex: Index of ``line`` inside ``self.text``.

        Returns:
            Visual-line fragments that cover the whole logical line.
        """
        if line == '':
            return [self._makeVisualLine('', lineIndex, 0)]

        visualLines = []
        start = 0

        while start < len(line):
            end = self.findVisualLineEnd(line, start)

            if end == len(line):
                visualLines.append(
                    self._makeVisualLine(line[start:end], lineIndex, start)
                )
                break

            if end == start:
                end = start + 1
                visualLines.append(
                    self._makeVisualLine(line[start:end], lineIndex, start)
                )
                start = end
                continue

            lastSpace = line.rfind(' ', start, end + 1)
            canWrapBySpace = lastSpace >= start and line[start:lastSpace].strip() != ''

            if canWrapBySpace:
                visualLines.append(
                    self._makeVisualLine(line[start : lastSpace + 1], lineIndex, start)
                )
                start = lastSpace + 1
            else:
                visualLines.append(
                    self._makeVisualLine(line[start:end], lineIndex, start)
                )
                start = end

        return visualLines

    def _makeVisualLine(self, text: str, lineIndex: int, startAt: int) -> VisualLine:
        """Create a ``VisualLine`` and precompute cursor offsets for its text.

        ``startAt`` is the column where ``text`` begins inside the original
        logical line. ``prefixWidths`` has one more entry than ``text``: index 0
        is the left edge, and every later index is the x offset after that many
        characters. The drawing and hit-testing paths use those offsets instead
        of remeasuring the same substrings repeatedly.

        Args:
            text: Text displayed by this visual line fragment.
            lineIndex: Index of the source logical line in ``self.text``.
            startAt: Starting column of ``text`` in the source logical line.

        Returns:
            A ``VisualLine`` with precomputed prefix widths.
        """
        return VisualLine(
            text=text,
            lineIndex=lineIndex,
            startAt=startAt,
            prefixWidths=self.buildPrefixWidths(text),
        )

    def findVisualLineEnd(self, line: str, start: int) -> int:
        """Return the exclusive end column of the widest substring that fits.

        The search checks candidate end columns with binary search. ``low`` is
        the largest known fitting end column, while ``high`` is the first known
        non-fitting end column or the sentinel just after ``len(line)``. The
        returned value is suitable for Python slicing, so
        ``line[start:return_value]`` is the measured fragment.

        If the first character is already too wide, no candidate slice is
        accepted and the method returns ``start``. ``_wrapLogicalLine`` handles
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
            candidateEnd = (low + high) // 2
            if self.getTextWidth(line[start:candidateEnd]) <= self._actualWidth:
                low = candidateEnd
            else:
                high = candidateEnd

        return low

    def resetSelection(self) -> None:
        self.selectionStart.set(self.cursor.line, self.cursor.column, self.text)
        self.selectionEnd.set(self.cursor.line, self.cursor.column, self.text)

    def getVisualLineIndex(self, cursor: Cursor) -> int:
        """Find the cached visual line that contains ``cursor``.

        The lookup first narrows the scan with ``visualLineRanges`` for the
        cursor's logical line. Cursor columns are logical-line columns, so each
        visual fragment is matched by
        ``startAt <= column <= startAt + len(text)``.

        When the cursor sits exactly at the end of a wrapped fragment and
        another fragment from the same logical line follows, this returns the
        next fragment. That draws the caret at the start of the next screen row,
        matching normal wrapped-text editing behavior.

        Args:
            cursor: Logical cursor position to locate.

        Returns:
            Index in ``cachedVisualLines``, or -1 if no matching visual line is
            cached.
        """
        startIndex, endIndex = self.visualLineRanges.get(
            cursor.line, (0, len(self.cachedVisualLines))
        )

        for lineIndex in range(startIndex, endIndex):
            visualLine = self.cachedVisualLines[lineIndex]
            if visualLine.lineIndex != cursor.line:
                continue

            lineWidth = visualLine.startAt + len(visualLine.text)
            if visualLine.startAt <= cursor.column <= lineWidth:
                if (
                    cursor.column == lineWidth != 0
                    and lineIndex + 1 < len(self.cachedVisualLines)
                    and self.cachedVisualLines[lineIndex + 1].lineIndex == cursor.line
                ):
                    return lineIndex + 1
                return lineIndex
        return -1

    def getTextWidth(self, text: str, style: int = 0) -> int:
        cacheKey = (text, style)

        if cacheKey in self._widthCache:
            self._widthCache.move_to_end(cacheKey)
            return self._widthCache[cacheKey]

        if len(self._widthCache) >= self.WIDTH_CACHE_SIZE:
            self._widthCache.popitem(last=False)

        width = self.font.get_rect(text, style=style).width
        self._widthCache[cacheKey] = width

        return width

    def buildPrefixWidths(self, text: str) -> list[int]:
        """Build x offsets for every cursor position inside ``text``.

        The returned list always starts with 0 and contains one entry per cursor
        position, including the position after the last character. For example,
        ``prefixWidths[3]`` is the pixel offset after the first three
        characters.

        Most characters use freetype glyph advance from ``get_metrics``. If
        metrics are missing for a character, the code falls back to measuring
        that character through ``getTextWidth``.

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
                cumulative += self.getTextWidth(text[i])
            widths.append(cumulative)
        return widths

    def getRenderedTextSurface(
        self,
        text: str,
        colour: ColorLike,
        style: int = 0,
    ) -> pygame.Surface:
        cacheKey = (text, colour, style)

        if cacheKey in self._renderedTextCache:
            self._renderedTextCache.move_to_end(cacheKey)
            return self._renderedTextCache[cacheKey]

        if len(self._renderedTextCache) >= self.RENDER_CACHE_SIZE:
            self._renderedTextCache.popitem(last=False)

        rendered = self.font.render(text, fgcolor=colour, style=style)[0]
        self._renderedTextCache[cacheKey] = rendered
        return rendered

    def updateCursor(self) -> None:
        now = pygame.time.get_ticks()
        if now - self.cursorTime >= self.cursorInterval:
            self.showCursor = not self.showCursor
            self.cursorTime = now

    def isEmptyText(self, text: list[str]) -> bool:
        return len(text) == 1 and text[0] == ''

    def isWordChar(self, character: str) -> bool:
        return character.isalnum() or character == '_'

    def isEmptySelection(self) -> bool:
        return (self.selectionStart.line, self.selectionStart.column) == (
            self.selectionEnd.line,
            self.selectionEnd.column,
        )

    def escape(self) -> None:
        self.repeatEvent = None
        self.keyDown = False
        self.firstRepeat = True
        self.selected = False
        self.showCursor = False
        self.resetSelection()

    def setText(self, text: str) -> None:
        self.text = ['']
        self.cursor.set(0, 0, self.text)
        self.resetSelection()
        self.addText(text, callOnTextChanged=False)

    def setPreferredColumn(self) -> None:
        """Remember the cursor's visual-column target for vertical movement.

        Horizontal movement and mouse placement update this value. Up/down
        movement then tries to keep the same local column inside the next visual
        line, clamping only when that target line is shorter.
        """
        visualLineIndex = self.getVisualLineIndex(self.cursor)

        if visualLineIndex != -1:
            visualLine = self.cachedVisualLines[visualLineIndex]
            relativeColumn = self.cursor.column - visualLine.startAt

            self.cursor.preferredColumn = relativeColumn

    def moveCursorWord(self, direction: Literal[-1, 1]) -> None:
        line = self.cursor.line
        col = self.cursor.column
        currentLine = self.text[line]

        if direction == -1 and col == 0 and line > 0:
            line -= 1
            currentLine = self.text[line]
            col = len(currentLine)
        elif direction == 1 and col == len(currentLine) and line < len(self.text) - 1:
            line += 1
            currentLine = self.text[line]
            col = 0

        offset = -1 if direction == -1 else 0
        while 0 <= col + offset < len(currentLine) and not self.isWordChar(
            currentLine[col + offset]
        ):
            col += direction

        while 0 <= col + offset < len(currentLine) and self.isWordChar(
            currentLine[col + offset]
        ):
            col += direction

        self.cursor.set(line, col, self.text)

    def setCursorFromMouse(self, mouseX: int, mouseY: int) -> None:
        """Move the cursor to the text position closest to a mouse coordinate.

        The y coordinate selects a visible ``VisualLine`` after clamping to the
        text area. The x coordinate is compared with midpoint positions between
        adjacent prefix widths, which chooses the nearest insertion column
        inside that visual fragment. The final cursor column is converted back
        to a logical-line column by adding ``visualLine.startAt``.

        Args:
            mouseX: Mouse x coordinate in window space.
            mouseY: Mouse y coordinate in window space.
        """
        if not self.cachedVisualLines:
            return

        clampedY = max(
            self._actualY, min(mouseY, self._actualY + self._actualHeight - 1)
        )

        rawIndex = (
            self.firstVisibleLineIndex + (clampedY - self._actualY) // self.lineHeight
        )
        visualLineIndex = max(
            self.firstVisibleLineIndex,
            min(
                rawIndex,
                self.firstVisibleLineIndex + self.maxVisibleLines - 1,
                len(self.cachedVisualLines) - 1,
            ),
        )

        visualLine = self.cachedVisualLines[visualLineIndex]

        if visualLine.lineIndex != self.cursor.line:
            self.cursor.set(visualLine.lineIndex, self.cursor.column, self.text)

        if len(visualLine.text) == 0:
            self.cursor.set(self.cursor.line, visualLine.startAt, self.text)
            return

        relativeX = mouseX - self._actualX
        prefixWidths = visualLine.prefixWidths
        relativeColumn = len(visualLine.text)

        for column in range(len(visualLine.text)):
            midpoint = (prefixWidths[column] + prefixWidths[column + 1]) / 2
            if relativeX < midpoint:
                relativeColumn = column
                break

        self.cursor.set(
            self.cursor.line,
            visualLine.startAt + relativeColumn,
            self.text,
        )

    def getText(self) -> str:
        return '\n'.join(self.text)

    def getSelectedText(self) -> str:
        start, end = self.getNormalizedSelection()

        if start.line == end.line:
            return self.text[start.line][start.column : end.column]

        result = []

        result.append(self.text[start.line][start.column :])

        for line in self.text[start.line + 1 : end.line]:
            result.append(line)

        result.append(self.text[end.line][: end.column])

        return '\n'.join(result)

    def set(self, attr: str, value: int) -> None:
        super().set(attr, value)
        self.reconfigureLayout()

    def setX(self, x: int) -> None:
        super().setX(x)
        self.reconfigureLayout()

    def setY(self, y: int) -> None:
        super().setY(y)
        self.reconfigureLayout()

    def setWidth(self, width: int) -> None:
        super().setWidth(width)
        self.reconfigureLayout()

    def setHeight(self, height: int) -> None:
        super().setHeight(height)
        self.reconfigureLayout()


if __name__ == '__main__':

    def output():
        print(textbox.getText())
        textbox.setText('')

    pygame.init()
    win = pygame.display.set_mode((1000, 600))

    clock = pygame.time.Clock()

    # modernDarkTheme = TextBoxStyle(
    #     colour=(30, 30, 30), textColour=(240, 240, 240), fontSize=24
    # )

    # inputLogin = TextBox(win, 100, 100, 400, 50, style=modernDarkTheme)
    # inputPassword = TextBox(win, 100, 200, 400, 50, style=modernDarkTheme)

    textbox = TextBox(
        win,
        x=100,
        y=100,
        width=800,
        height=400,
        fontSize=50,
        borderColour=(255, 0, 0),
        textColour=(0, 200, 0),
        onSubmit=output,
        radius=10,
        borderThickness=5,
        placeholderText='Enter something:',
    )

    run = True
    while run:
        outerEvents = pygame.event.get()
        for outerEvent in outerEvents:
            if outerEvent.type == pygame.QUIT:
                pygame.quit()
                run = False
                sys.exit()
            # elif outerEvent.type == pygame.KEYDOWN:
            #     if outerEvent.key == pygame.K_k:
            #         modernDarkTheme.colour = (255, 255, 255)
            #         modernDarkTheme.textColour = (0, 0, 0)

        win.fill((255, 255, 255))

        pygame_widgets.update(outerEvents)
        pygame.display.update()

        clock.tick(60)
