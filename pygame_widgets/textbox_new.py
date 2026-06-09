import pyperclip

import pygame
import pygame_widgets
from pygame_widgets.widget import WidgetBase
from pygame_widgets.mouse import Mouse, MouseState

from bisect import bisect_right
from dataclasses import dataclass, field
from collections import OrderedDict

from typing import Literal


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
        minHeight: int,
        isSubWidget=False,
        **kwargs
    ) -> None:
        '''A customisable textbox for Pygame

        :param win: Surface on which to draw
        :type win: pygame.Surface
        :param x: X-coordinate of top left
        :type x: int
        :param y: Y-coordinate of top left
        :type y: int
        :param width: Width of button
        :type width: int
        :param minHeight: Minimum height of textbox
        :type minHeight: int
        :param maxHeight: Maximum height of textbox. Defaults to minHeight for fixed-height behavior
        :type maxHeight: int
        :param kwargs: Optional parameters
        '''
        super().__init__(win, x, y, width, minHeight, isSubWidget)

        # Widget state
        self.selected = False
        self.readOnly = kwargs.get('readOnly', False)
        self.keyDown = False
        self.repeatTime = 0
        self.repeatEvent = None
        self.firstRepeat = True
        self.insertOn = False

        # Cursor state and style
        self.cursor = Cursor()
        self.cursorWidth = kwargs.get('cursorWidth', 2)
        self.cursorColour = kwargs.get('cursorColour', (0, 0, 0))
        self.cursorAlpha = kwargs.get('cursorAlpha', 63)
        self.showCursor = not self.readOnly
        self.cursorTime = 0

        self.lastClickTime = 0
        self.isDoubleClick = False

        # Text state
        self.text = ['']
        self.cachedVisualLines = [
            {'text': '', 'lineIndex': 0, 'startAt': 0, 'prefixWidths': [0]}
        ]
        self.visualLineRanges = {0: (0, 1)}
        self.tabSpaces = kwargs.get('tabSpaces', 4)

        # Font style
        self.fontSize = kwargs.get('fontSize', 20)
        self.font = kwargs.get('font', pygame.font.SysFont('calibri', self.fontSize))
        self.textColour = kwargs.get('textColour', (0, 0, 0))

        # Margins
        self.textOffsetTop = self.fontSize // 3
        self.textOffsetLeft = self.fontSize // 3
        self.textOffsetRight = self.fontSize // 2

        # Placeholder
        self.placeholderText = kwargs.get('placeholderText', '')
        self.placeholderTextColour = kwargs.get('placeholderTextColour', (10, 10, 10))

        # Widget style
        self.colour = kwargs.get('colour', (220, 220, 220))
        self.borderThickness = kwargs.get('borderThickness', 3)
        self.borderColour = kwargs.get('borderColour', (0, 0, 0))
        self.radius = kwargs.get('radius', 0)

        self.selectionStart = Cursor()
        self.selectionEnd = Cursor()
        self.selectionColour = kwargs.get('selectionColour', (166, 210, 255))

        # Callback
        self.onSubmit = kwargs.get('onSubmit', lambda *args: None)
        self.onSubmitParams = kwargs.get('onSubmitParams', ())
        self.onTextChanged = kwargs.get('onTextChanged', lambda *args: None)
        self.onTextChangedParams = kwargs.get('onTextChangedParams', ())

        # Layout
        self._minHeight = minHeight
        self._maxHeight = kwargs.get('maxHeight')
        self.linesPerScroll = kwargs.get('linesPerScroll', 1)
        if self._maxHeight is None:
            self._maxHeight = self._minHeight
        else:
            self._maxHeight = max(self._minHeight, self._maxHeight)

        self._actualWidth = (
            self._width
            - self.textOffsetRight
            - self.textOffsetLeft
            - self.borderThickness * 2
        )
        self._actualHeight = (
            self._height - self.textOffsetTop - self.borderThickness * 2
        )
        self.lineHeight = self.font.get_linesize()
        self._actualX = self._x + self.textOffsetLeft + self.borderThickness
        self._actualY = self._y + self.textOffsetTop + self.borderThickness

        self.firstVisibleLineIndex = 0
        self.maxVisibleLines = max(1, self._actualHeight // self.lineHeight)

        self._widthCache = OrderedDict()
        self._renderedTextCache = OrderedDict()

    def listen(self, events) -> None:
        '''Wait for inputs

        :param events: Use pygame.event.get()
        :type events: list of pygame.event.Event
        '''
        if self._hidden or self._disabled:
            return

        if self.keyDown:
            self.updateRepeatEvent()

        # Selection
        mouseState = Mouse.getMouseState()
        x, y = Mouse.getMousePos()

        if mouseState == MouseState.CLICK:
            if self.contains(x, y):
                now = pygame.time.get_ticks()

                self.isDoubleClick = (
                    now - self.lastClickTime
                ) < self.DOUBLE_CLICK_INTERVAL
                self.lastClickTime = now

                self.selected = True
                self.showCursor = True
                self.cursorTime = now

                self.setCursorFromMouse(x, y)
                if self.isDoubleClick:
                    self.moveCursorWord(direction=-1)
                    self.selectionStart.set(
                        self.cursor.line, self.cursor.column, self.text
                    )
                    self.moveCursorWord(direction=1)
                    self.selectionEnd.set(
                        self.cursor.line, self.cursor.column, self.text
                    )
                else:
                    self.resetSelection()
                self.setPreferredColumn()

            else:
                self.escape()

        elif mouseState == MouseState.DRAG and self.selected and not self.isDoubleClick:
            self.cursorTime = pygame.time.get_ticks()
            self.setCursorFromMouse(x, y)
            self.selectionEnd.set(self.cursor.line, self.cursor.column, self.text)
            self.setPreferredColumn()

            if y < self._actualY:
                self.firstVisibleLineIndex = max(0, self.firstVisibleLineIndex - 1)
            elif y > self._actualY + self._actualHeight:
                maxScroll = max(0, len(self.cachedVisualLines) - self.maxVisibleLines)
                self.firstVisibleLineIndex = min(
                    maxScroll, self.firstVisibleLineIndex + 1
                )

        # Keyboard Input
        if self.selected:
            for event in events:
                if event.type == pygame.MOUSEWHEEL and self.contains(x, y):
                    self.firstVisibleLineIndex -= event.y * self.linesPerScroll
                    maxScroll = max(
                        0, len(self.cachedVisualLines) - self.maxVisibleLines
                    )
                    self.firstVisibleLineIndex = max(
                        0, min(self.firstVisibleLineIndex, maxScroll)
                    )

                if event.type == pygame.KEYDOWN:
                    self.handleKeyDown(event)

                elif event.type == pygame.TEXTINPUT:
                    self.handleTextInput(event)

                elif event.type == pygame.KEYUP:
                    self.repeatEvent = None
                    self.keyDown = False
                    self.firstRepeat = True

    def handleKeyDown(self, event: pygame.Event) -> None:
        now = pygame.time.get_ticks()
        self.showCursor = True
        self.keyDown = True
        self.repeatEvent = event
        self.repeatTime = now
        self.cursorTime = now

        if event.key == pygame.K_BACKSPACE:
            self.eraseText(event, direction=-1)

        elif event.key == pygame.K_DELETE:
            self.eraseText(event, direction=1)

        elif event.key == pygame.K_RETURN:
            if event.mod & pygame.KMOD_SHIFT or event.mod & pygame.KMOD_CTRL:
                if not self.readOnly:
                    self.addText('\n')
            else:
                self.onSubmit(*self.onSubmitParams)

        elif (
            event.key == pygame.K_UP
            or event.key == pygame.K_KP_8
            and not event.mod & pygame.KMOD_NUM
        ):
            self.moveCursorVertical(event, direction=-1)

        elif (
            event.key == pygame.K_DOWN
            or event.key == pygame.K_KP_2
            and not event.mod & pygame.KMOD_NUM
        ):
            self.moveCursorVertical(event, direction=1)

        elif (
            event.key == pygame.K_LEFT
            or event.key == pygame.K_KP_4
            and not event.mod & pygame.KMOD_NUM
        ):
            self.moveCursorHorizontal(event, direction=-1)

        elif (
            event.key == pygame.K_RIGHT
            or event.key == pygame.K_KP_6
            and not event.mod & pygame.KMOD_NUM
        ):
            self.moveCursorHorizontal(event, direction=1)

        elif (
            event.key == pygame.K_HOME
            or event.key == pygame.K_KP_7
            and not event.mod & pygame.KMOD_NUM
        ):
            self.jumpToEdge(event, direction=-1)

        elif (
            event.key == pygame.K_END
            or event.key == pygame.K_KP_1
            and not event.mod & pygame.KMOD_NUM
        ):
            self.jumpToEdge(event, direction=1)

        elif event.key == pygame.K_a and event.mod & pygame.KMOD_CTRL:
            self.selectionStart.set(0, 0, self.text)
            self.selectionEnd.set(len(self.text) - 1, len(self.text[-1]), self.text)
            self.cursor.set(len(self.text) - 1, len(self.text[-1]), self.text)

        elif event.key == pygame.K_c and event.mod & pygame.KMOD_CTRL:
            self.copySelectedText()

        elif event.key == pygame.K_v and event.mod & pygame.KMOD_CTRL:
            if not self.readOnly:
                text = pyperclip.paste()
                if text:
                    self.addText(text)

        elif event.key == pygame.K_x and event.mod & pygame.KMOD_CTRL:
            self.copySelectedText()
            if not self.readOnly:
                self.eraseSelectedText()

        elif event.key in (pygame.K_INSERT, pygame.K_KP_0):
            self.insertOn = not self.insertOn

        elif event.key == pygame.K_ESCAPE:
            self.escape()

    def handleTextInput(self, event: pygame.Event) -> None:
        if not self.readOnly:
            now = pygame.time.get_ticks()
            self.showCursor = True
            self.keyDown = True
            self.repeatEvent = event
            self.repeatTime = now
            self.cursorTime = now
            if len(event.text) != 0:
                self.addText(event.text)

    def draw(self) -> None:
        '''Display to surface'''
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
                {'text': self.placeholderText, 'lineIndex': 0, 'startAt': 0}
            ]
            colour = self.placeholderTextColour
        else:
            displayLines = self.cachedVisualLines
            colour = self.textColour

        for i, visualLine in enumerate(displayLines):
            if not (
                self.firstVisibleLineIndex
                <= i
                < self.firstVisibleLineIndex + self.maxVisibleLines
            ):
                continue

            lineY = self._actualY + (i - self.firstVisibleLineIndex) * self.lineHeight

            textSurface = self.getRenderedTextSurface(visualLine['text'], colour)
            self.win.blit(textSurface, (self._actualX, lineY))

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

                relativeColumn = self.cursor.column - visualLine['startAt']
                startX = self._actualX + self.getVisualWidth(visualLine, relativeColumn)
                endX = startX

                startY = self._actualY + self.lineHeight * (
                    visualLineIndex - self.firstVisibleLineIndex
                )
                endY = startY + self.lineHeight

                if not self.insertOn:
                    pygame.draw.line(
                        self.win,
                        self.cursorColour,
                        (startX, startY),
                        (endX, endY),
                        self.cursorWidth,
                    )
                else:
                    if self.cursor.column == len(self.text[self.cursor.line]):
                        textSurface = self.getRenderedTextSurface(' ', self.textColour)
                    else:
                        textSurface = self.getRenderedTextSurface(
                            self.text[self.cursor.line][self.cursor.column],
                            self.textColour,
                        )
                    cursorSurface = pygame.Surface(textSurface.get_size())
                    cursorSurface.fill(self.cursorColour)
                    cursorSurface.set_alpha(self.cursorAlpha)
                    self.win.blit(cursorSurface, (startX, startY))

    def _drawBorder(self) -> None:
        pygame.draw.rect(
            self.win,
            self.borderColour,
            (self._x, self._y, self._width, self._height),
            border_radius=self.radius,
        )

    def _drawBackground(self) -> None:
        rect = (
            self._x + self.borderThickness,
            self._y + self.borderThickness,
            self._width - self.borderThickness * 2,
            self._height - self.borderThickness * 2,
        )
        pygame.draw.rect(self.win, self.colour, rect, border_radius=self.radius)

    def _drawSelection(self) -> None:
        if self.isEmptySelection():
            return

        start, end = self.getNormalizeSelection()

        for i, visualLine in enumerate(self.cachedVisualLines):
            if not (
                self.firstVisibleLineIndex
                <= i
                < self.firstVisibleLineIndex + self.maxVisibleLines
            ):
                continue

            lineIndex = visualLine['lineIndex']

            if not (start.line <= lineIndex <= end.line):
                continue

            lineY = self._actualY + self.lineHeight * (i - self.firstVisibleLineIndex)

            lineStart = visualLine['startAt']

            selectionStart = start.column if lineIndex == start.line else 0
            selectionEnd = (
                end.column if lineIndex == end.line else len(self.text[lineIndex])
            )

            localStart = max(0, selectionStart - lineStart)
            localEnd = min(len(visualLine['text']), selectionEnd - lineStart)

            if localStart > localEnd:
                continue

            isEmptyLine = len(self.text[lineIndex]) == 0

            isEndOfLogicalLine = (
                lineIndex < end.line
                and localEnd == len(visualLine['text'])
                and visualLine['startAt'] + len(visualLine['text'])
                == len(self.text[lineIndex])
            )

            if localStart == localEnd and not (isEmptyLine or isEndOfLogicalLine):
                continue

            textBeforeWidth = self.getVisualWidth(visualLine, localStart)
            textUpToEndWidth = self.getVisualWidth(visualLine, localEnd)

            textWidth = textUpToEndWidth - textBeforeWidth

            if isEmptyLine or isEndOfLogicalLine:
                textWidth += self.getTextWidth(' ')

            pygame.draw.rect(
                self.win,
                self.selectionColour,
                (self._actualX + textBeforeWidth, lineY, textWidth, self.lineHeight),
            )

    def processBackspace(self) -> None:
        if self.cursor.column > 0:
            reflowStartColumn = self.cursor.column - 1

            self.text[self.cursor.line] = (
                self.text[self.cursor.line][: self.cursor.column - 1]
                + self.text[self.cursor.line][self.cursor.column :]
            )
            self.cursor.set(self.cursor.line, self.cursor.column - 1, self.text)

            self.setVisualLines(self.cursor.line, reflowStartColumn)
            self.setPreferredColumn()
            self.onTextChanged(*self.onTextChangedParams)

        elif self.cursor.line > 0:
            previousLineLength = len(self.text[self.cursor.line - 1])
            self.text[self.cursor.line - 1] += self.text[self.cursor.line]
            self.text.pop(self.cursor.line)
            self.cursor.set(self.cursor.line - 1, previousLineLength, self.text)

            self.setVisualLines(self.cursor.line, previousLineLength)
            self.setPreferredColumn()
            self.onTextChanged(*self.onTextChangedParams)

    def processDelete(self) -> None:
        if self.cursor.column < len(self.text[self.cursor.line]):
            reflowStartColumn = self.cursor.column

            self.text[self.cursor.line] = (
                self.text[self.cursor.line][: self.cursor.column]
                + self.text[self.cursor.line][self.cursor.column + 1 :]
            )

            self.setVisualLines(self.cursor.line, reflowStartColumn)
            self.setPreferredColumn()
            self.onTextChanged(*self.onTextChangedParams)

        elif self.cursor.line < len(self.text) - 1:
            reflowStartColumn = len(self.text[self.cursor.line])
            self.text[self.cursor.line] += self.text[self.cursor.line + 1]
            self.text.pop(self.cursor.line + 1)

            self.setVisualLines(self.cursor.line, reflowStartColumn)
            self.setPreferredColumn()
            self.onTextChanged(*self.onTextChangedParams)

    def eraseText(self, event: pygame.Event, direction: Literal[-1, 1]) -> None:
        if self.readOnly:
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
        start, end = self.getNormalizeSelection()
        reflowStartLine = start.line
        reflowStartColumn = start.column

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

        self.setVisualLines(reflowStartLine, reflowStartColumn)
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
                column = visualLine['startAt']
                if direction == 1:
                    column += len(visualLine['text'])

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
            start, end = self.getNormalizeSelection()
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
                targetLine['startAt'] + self.cursor.preferredColumn,
                targetLine['startAt'] + len(targetLine['text']),
            )
            self.cursor.set(targetLine['lineIndex'], desiredColumn, self.text)
        else:
            if direction == -1:
                self.cursor.set(self.cursor.line, 0, self.text)
            else:
                currentLine = self.cachedVisualLines[visualLineIndex]
                self.cursor.set(
                    self.cursor.line,
                    currentLine['startAt'] + len(currentLine['text']),
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
            start, end = self.getNormalizeSelection()
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

    def updateRepeatEvent(self) -> None:
        if self.repeatEvent is None:
            return

        now = pygame.time.get_ticks()

        if self.firstRepeat:
            if now - self.repeatTime >= self.REPEAT_DELAY:
                self.firstRepeat = False
                self.repeatTime = now
                if self.repeatEvent.type == pygame.KEYDOWN:
                    self.handleKeyDown(self.repeatEvent)
                elif self.repeatEvent.type == pygame.TEXTINPUT:
                    self.handleTextInput(self.repeatEvent)

        elif now - self.repeatTime >= self.REPEAT_INTERVAL:
            self.repeatTime = now
            if self.repeatEvent.type == pygame.KEYDOWN:
                self.handleKeyDown(self.repeatEvent)
            elif self.repeatEvent.type == pygame.TEXTINPUT:
                self.handleTextInput(self.repeatEvent)

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
        neededHeight = (
            len(self.cachedVisualLines) * self.lineHeight
            + self.textOffsetTop
            + self.borderThickness * 2
        )

        self._height = max(self._minHeight, min(neededHeight, self._maxHeight))

        self._actualHeight = (
            self._height - self.textOffsetTop - self.borderThickness * 2
        )

        self.maxVisibleLines = max(1, self._actualHeight // self.lineHeight)

    def addText(self, text: str, callOnTextChanged: bool = True) -> None:
        if not self.isEmptySelection():
            self.eraseSelectedText(callOnTextChanged=False)

        text = str(text).replace('\t', ' ' * self.tabSpaces).replace('\r', '')
        lines = text.split('\n')
        reflowStartLine = self.cursor.line
        reflowStartColumn = self.cursor.column

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
                if len(line) > len(self.text[self.cursor.line]):
                    rightPart = ''
                else:
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

        self.setVisualLines(reflowStartLine, reflowStartColumn)
        self.setPreferredColumn()
        self.ensureCursorVisible()
        if callOnTextChanged:
            self.onTextChanged(*self.onTextChangedParams)

    def getNormalizeSelection(self) -> tuple[Cursor, Cursor]:
        if self.selectionStart > self.selectionEnd:
            return self.selectionEnd, self.selectionStart
        return self.selectionStart, self.selectionEnd

    def setVisualLines(self, startLine: int = 0, startColumn: int = 0) -> None:
        startLine = max(0, min(startLine, len(self.text) - 1))
        startColumn = max(0, startColumn)

        if (startLine, startColumn) == (0, 0) or not self.cachedVisualLines:
            self.cachedVisualLines = []
            self.visualLineRanges = {}
            lineStartColumn = 0
        else:
            oldLineStart = self.visualLineRanges.get(
                startLine, (len(self.cachedVisualLines), len(self.cachedVisualLines))
            )[0]
            firstChangedVisualLine, lineStartColumn = self._getReflowStart(
                startLine, startColumn
            )
            self.cachedVisualLines = self.cachedVisualLines[:firstChangedVisualLine]
            self.visualLineRanges = {
                lineIndex: visualRange
                for lineIndex, visualRange in self.visualLineRanges.items()
                if lineIndex < startLine
            }
            if firstChangedVisualLine > oldLineStart:
                self.visualLineRanges[startLine] = (
                    oldLineStart,
                    firstChangedVisualLine,
                )

        for lineIndex in range(startLine, len(self.text)):
            line = self.text[lineIndex]

            if line == '':
                self._appendVisualLine('', lineIndex, 0)
                continue

            start = lineStartColumn if lineIndex == startLine else 0
            while start < len(line):
                end = self.findVisualLineEnd(line, start)

                if end == len(line):
                    self._appendVisualLine(line[start:end], lineIndex, start)
                    break

                if end == start:
                    end = start + 1
                    self._appendVisualLine(line[start:end], lineIndex, start)
                    start = end

                else:
                    lastSpace = line.rfind(' ', start, end + 1)

                    if lastSpace >= start and line[start:lastSpace].strip() != '':
                        self._appendVisualLine(
                            line[start : lastSpace + 1], lineIndex, start
                        )
                        start = lastSpace + 1

                    else:
                        self._appendVisualLine(line[start:end], lineIndex, start)
                        start = end

        self.updateLayout()

    def _getReflowStart(self, lineIndex: int, column: int) -> tuple[int, int]:
        lineStart, lineEnd = self.visualLineRanges.get(
            lineIndex, (len(self.cachedVisualLines), len(self.cachedVisualLines))
        )

        for visualLineIndex in range(lineStart, lineEnd):
            visualLine = self.cachedVisualLines[visualLineIndex]
            visualLineEnd = visualLine['startAt'] + len(visualLine['text'])

            if column < visualLineEnd:
                return visualLineIndex, visualLine['startAt']

            if column == visualLineEnd:
                nextVisualLineIndex = visualLineIndex + 1
                if nextVisualLineIndex < lineEnd:
                    return (
                        nextVisualLineIndex,
                        self.cachedVisualLines[nextVisualLineIndex]['startAt'],
                    )
                return visualLineIndex, visualLine['startAt']

        if lineEnd > lineStart:
            lastVisualLine = self.cachedVisualLines[lineEnd - 1]
            return lineEnd - 1, lastVisualLine['startAt']

        return len(self.cachedVisualLines), 0

    def _appendVisualLine(self, text: str, lineIndex: int, startAt: int) -> None:
        visualLineIndex = len(self.cachedVisualLines)
        self.cachedVisualLines.append(
            {
                'text': text,
                'lineIndex': lineIndex,
                'startAt': startAt,
                'prefixWidths': self.buildPrefixWidths(text),
            }
        )

        if lineIndex in self.visualLineRanges:
            self.visualLineRanges[lineIndex] = (
                self.visualLineRanges[lineIndex][0],
                visualLineIndex + 1,
            )
        else:
            self.visualLineRanges[lineIndex] = (visualLineIndex, visualLineIndex + 1)

    def findVisualLineEnd(self, line: str, start: int) -> int:
        return (
            bisect_right(
                range(len(line) + 1),
                self._actualWidth,
                lo=start + 1,
                key=lambda end: self.getTextWidth(line[start:end]),
            )
            - 1
        )

    def resetSelection(self) -> None:
        self.selectionStart.set(self.cursor.line, self.cursor.column, self.text)
        self.selectionEnd.set(self.cursor.line, self.cursor.column, self.text)

    def getVisualLineIndex(self, cursor: Cursor) -> int:
        startIndex, endIndex = self.visualLineRanges.get(
            cursor.line, (0, len(self.cachedVisualLines))
        )

        for lineIndex in range(startIndex, endIndex):
            visualLine = self.cachedVisualLines[lineIndex]

            if visualLine['lineIndex'] != cursor.line:
                continue

            lineWidth = visualLine['startAt'] + len(visualLine['text'])
            if visualLine['startAt'] <= cursor.column <= lineWidth:
                if (
                    cursor.column == lineWidth != 0
                    and lineIndex + 1 < len(self.cachedVisualLines)
                    and self.cachedVisualLines[lineIndex + 1]['lineIndex']
                    == cursor.line
                ):
                    return lineIndex + 1
                return lineIndex
        return -1

    def getTextWidth(self, text: str) -> int:
        if text in self._widthCache:
            self._widthCache.move_to_end(text)
            return self._widthCache[text]

        if len(self._widthCache) >= self.WIDTH_CACHE_SIZE:
            self._widthCache.popitem(last=False)

        width = self.font.size(text)[0]
        self._widthCache[text] = width

        return width

    def buildPrefixWidths(self, text: str) -> list[int]:
        widths = [0]

        for column in range(1, len(text) + 1):
            widths.append(self.getTextWidth(text[:column]))

        return widths

    def getVisualWidth(self, visualLine: dict, column: int) -> int:
        prefixWidths = visualLine['prefixWidths']
        column = max(0, min(column, len(prefixWidths) - 1))
        return prefixWidths[column]

    def getRenderedTextSurface(self, text: str, colour) -> pygame.Surface:
        if text in self._renderedTextCache:
            self._renderedTextCache.move_to_end(text)
            return self._renderedTextCache[text]

        if len(self._renderedTextCache) >= self.RENDER_CACHE_SIZE:
            self._renderedTextCache.popitem(last=False)

        rendered = self.font.render(text, True, colour)
        self._renderedTextCache[text] = rendered
        return rendered

    def updateCursor(self) -> None:
        now = pygame.time.get_ticks()
        if now - self.cursorTime >= self.CURSOR_INTERVAL:
            self.showCursor = not self.showCursor
            self.cursorTime = now

    def isEmptyText(self, text: list[str]) -> bool:
        return len(text) == 1 and text[0] == ''

    def copySelectedText(self) -> None:
        if not self.isEmptySelection():
            pyperclip.copy(self.getSelectedText())

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
        self.addText(text)

    def setPreferredColumn(self) -> None:
        visualLineIndex = self.getVisualLineIndex(self.cursor)

        if visualLineIndex != -1:
            visualLine = self.cachedVisualLines[visualLineIndex]
            relativeColumn = self.cursor.column - visualLine['startAt']

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

        if visualLine['lineIndex'] != self.cursor.line:
            self.cursor.set(visualLine['lineIndex'], self.cursor.column, self.text)

        if len(visualLine['text']) == 0:
            self.cursor.set(self.cursor.line, visualLine['startAt'], self.text)
            return

        relativeX = mouseX - self._actualX
        prefixWidths = visualLine['prefixWidths']
        relativeColumn = len(visualLine['text'])

        for column in range(len(visualLine['text'])):
            midpoint = (prefixWidths[column] + prefixWidths[column + 1]) / 2
            if relativeX < midpoint:
                relativeColumn = column
                break

        self.cursor.set(
            self.cursor.line,
            visualLine['startAt'] + relativeColumn,
            self.text,
        )

    def getText(self) -> str:
        return '\n'.join(self.text)

    def getSelectedText(self) -> str:
        start, end = self.getNormalizeSelection()

        if start.line == end.line:
            return self.text[start.line][start.column : end.column]

        result = []

        result.append(self.text[start.line][start.column :])

        for line in self.text[start.line + 1 : end.line]:
            result.append(line)

        result.append(self.text[end.line][: end.column])

        return '\n'.join(result)


if __name__ == '__main__':

    def output():
        print(textbox.getText())
        textbox.setText('')

    pygame.init()
    win = pygame.display.set_mode((1000, 600))

    clock = pygame.time.Clock()

    textbox = TextBox(
        win,
        100,
        100,
        800,
        100,
        maxHeight=450,
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
                quit()

        win.fill((255, 255, 255))

        pygame_widgets.update(outerEvents)
        pygame.display.update()

        clock.tick(60)
