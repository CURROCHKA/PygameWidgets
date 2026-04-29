import pyperclip

import pygame
import pygame_widgets
from pygame_widgets.widget import WidgetBase
from pygame_widgets.mouse import Mouse, MouseState

from dataclasses import dataclass


@dataclass
class Cursor:
    line: int = 0
    column: int = 0
    preferredColumn: int = 0

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

    def __init__(
            self,
            win: pygame.Surface,
            x: int,
            y: int, 
            width: int,
            minHeight: int,
            maxHeight: int,
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
        :param height: Height of button
        :type height: int
        :param kwargs: Optional parameters
        '''
        super().__init__(win, x, y, width, minHeight, isSubWidget)

        # Widget state
        self.selected = False
        self.readOnly = kwargs.get('readOnly', False)
        self.originalRepeat = pygame.key.get_repeat()

        # Cursor state and style
        self.cursor = Cursor()
        self.cursorWidth = kwargs.get('cursorWidth', 2)
        self.cursorColour = kwargs.get('cursorColour', (0, 0, 0))
        self.showCursor = not self.readOnly
        self.cursorTime = 0

        self.lastClickTime = 0
        self.isDoubleClick = False

        # Text state
        self.text = ['']
        self.cachedVisualLines = [{'text': '', 'lineIndex': 0, 'startAt': 0}]
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
        self._actualWidth = (
            self._width
            - self.textOffsetRight
            - self.textOffsetLeft
            - self.borderThickness * 2
        )
        self._actualHeight = (
            self._height
            - self.textOffsetTop
            - self.borderThickness * 2
        )
        self._actualX = self._x + self.textOffsetLeft + self.borderThickness
        self._actualY = self._y + self.textOffsetTop + self.borderThickness
        self._minHeight = minHeight
        self._maxHeight = maxHeight
        self.firstVisibleLineIndex = 0
        self.maxVisibleLines = self._actualHeight // self.fontSize

    def listen(self, events) -> None:
        '''Wait for inputs

        :param events: Use pygame.event.get()
        :type events: list of pygame.event.Event
        '''
        if self._hidden or self._disabled:
            return

        # Selection
        mouseState = Mouse.getMouseState()
        x, y = Mouse.getMousePos()

        if mouseState == MouseState.CLICK:
            if self.contains(x, y):
                now = pygame.time.get_ticks()

                self.isDoubleClick = (now - self.lastClickTime) < self.DOUBLE_CLICK_INTERVAL
                self.lastClickTime = now

                self.selected = True
                self.showCursor = True
                self.cursorTime = now

                self._setColumnFromMouse(x, y)
                if self.isDoubleClick:
                    self._moveCursorWordLeft()
                    self.selectionStart.set(self.cursor.line, self.cursor.column, self.text)
                    self._moveCursorWordRight()
                    self.selectionEnd.set(self.cursor.line, self.cursor.column, self.text)
                else:
                    self.resetSelection()
                self._setPreferredColumn()

                pygame.key.set_repeat(self.REPEAT_DELAY, self.REPEAT_INTERVAL)
            else:
                self.escape()

        elif mouseState == MouseState.DRAG and self.selected and not self.isDoubleClick:
            self.cursorTime = pygame.time.get_ticks()
            self._setColumnFromMouse(x, y)
            self.selectionEnd.set(self.cursor.line, self.cursor.column, self.text)
            self._setPreferredColumn()

        # Keyboard Input
        if self.selected:
            for event in events:
                if event.type == pygame.MOUSEWHEEL and self.contains(x, y):
                    self.firstVisibleLineIndex -= event.y  # * speedOfScroll
                    maxScroll = max(0, len(self.cachedVisualLines) - self.maxVisibleLines)
                    self.firstVisibleLineIndex = max(0, min(self.firstVisibleLineIndex, maxScroll))

                if event.type == pygame.KEYDOWN:
                    self.showCursor = True
                    self.cursorTime = pygame.time.get_ticks()

                    if event.key == pygame.K_BACKSPACE:
                        self._handleBackspace(event)

                    elif event.key == pygame.K_DELETE:
                        self._handleDelete(event)

                    elif event.key == pygame.K_RETURN:
                        if (
                            event.mod & pygame.KMOD_SHIFT
                            or event.mod & pygame.KMOD_CTRL
                        ):
                            self.addText('\n')
                        else:
                            self.onSubmit(*self.onSubmitParams)

                    elif event.key in [
                        pygame.K_UP,
                        pygame.K_KP_8 if not event.mod & pygame.KMOD_NUM else -1,
                    ]:
                        self._handleUp()

                    elif event.key in [
                        pygame.K_DOWN,
                        pygame.K_KP_2 if not event.mod & pygame.KMOD_NUM else -1,
                    ]:
                        self._handleDown()

                    elif event.key in [
                        pygame.K_LEFT,
                        pygame.K_KP_4 if not event.mod & pygame.KMOD_NUM else -1,
                    ]:
                        self._handleLeft(event)

                    elif event.key in [
                        pygame.K_RIGHT,
                        pygame.K_KP_6 if not event.mod & pygame.KMOD_NUM else -1,
                    ]:
                        self._handleRight(event)

                    elif event.key in [
                        pygame.K_HOME,
                        pygame.K_KP_7 if not event.mod & pygame.KMOD_NUM else -1,
                    ]:
                        self._handleHome(event)

                    elif event.key in [
                        pygame.K_END,
                        pygame.K_KP_1 if not event.mod & pygame.KMOD_NUM else -1,
                    ]:
                        self._handleEnd(event)

                    elif event.key == pygame.K_a and event.mod & pygame.KMOD_CTRL:
                        self.selectionStart.set(0, 0, self.text)
                        self.selectionEnd.set(
                            len(self.text) - 1, len(self.text[-1]), self.text
                        )
                        self.cursor.set(
                            len(self.text) - 1, len(self.text[-1]), self.text
                        )

                    elif event.key == pygame.K_c and event.mod & pygame.KMOD_CTRL:
                        self.copySelectedText()

                    elif event.key == pygame.K_v and event.mod & pygame.KMOD_CTRL:
                        text = pyperclip.paste()
                        if text:
                            self.addText(text)

                    elif event.key == pygame.K_x and event.mod & pygame.KMOD_CTRL:
                        self.copySelectedText()
                        self.eraseSelectedText()

                    elif event.key == pygame.K_INSERT:
                        self.insertOn = not self.insertOn  # TODO: add insert logic

                    elif event.key == pygame.K_ESCAPE:
                        self.escape()

                    elif not self.readOnly:
                        if event.unicode:
                            self.addText(event.unicode)

    def _handleBackspace(self, event: pygame.Event) -> None:
        if not self.isEmptySelection():
            self.eraseSelectedText()

        elif event.mod & pygame.KMOD_CTRL:
            # This is necessary in order to set the start of the selection at the point
            if self.isEmptySelection():
                self.resetSelection()

            self._moveCursorWordLeft()
            self.selectionEnd.set(self.cursor.line, self.cursor.column, self.text)
            self.eraseSelectedText()

        elif self.cursor.column > 0:
            self.text[self.cursor.line] = (
                self.text[self.cursor.line][: self.cursor.column - 1]
                + self.text[self.cursor.line][self.cursor.column :]
            )
            self.cursor.set(self.cursor.line, self.cursor.column - 1, self.text)

            self._setVisualLines()
            self._setPreferredColumn()
            self.onTextChanged(*self.onTextChangedParams)

        elif self.cursor.line > 0:
            previousLineLength = len(self.text[self.cursor.line - 1])
            self.text[self.cursor.line - 1] += self.text[self.cursor.line]
            self.text.pop(self.cursor.line)
            self.cursor.set(self.cursor.line - 1, previousLineLength, self.text)

            self._setVisualLines()
            self._setPreferredColumn()
            self.onTextChanged(*self.onTextChangedParams)

        self._ensureCursorVisible()

    def _handleDelete(self, event: pygame.Event) -> None:
        if not self.isEmptySelection():
            self.eraseSelectedText()

        elif event.mod & pygame.KMOD_CTRL:
            if self.isEmptySelection():
                self.resetSelection()

            self._moveCursorWordRight()
            self.selectionEnd.set(self.cursor.line, self.cursor.column, self.text)
            self.eraseSelectedText()

        elif self.cursor.column < len(self.text[self.cursor.line]):

            self.text[self.cursor.line] = (
                self.text[self.cursor.line][: self.cursor.column]
                + self.text[self.cursor.line][self.cursor.column + 1 :]
            )

            self._setVisualLines()
            self._setPreferredColumn()
            self.onTextChanged(*self.onTextChangedParams)

        elif self.cursor.line < len(self.text) - 1:
            self.text[self.cursor.line] += self.text[self.cursor.line + 1]
            self.text.pop(self.cursor.line + 1)

            self._setVisualLines()
            self._setPreferredColumn()
            self.onTextChanged(*self.onTextChangedParams)

        self._ensureCursorVisible()

    def _handleUp(self) -> None:
        self.resetSelection()

        visualLineIndex = self.getCurrentVisualLineIndex()

        if visualLineIndex != -1:
            if visualLineIndex > 0:
                previousLine = self.cachedVisualLines[visualLineIndex - 1]

                desiredColumn = min(
                    previousLine['startAt'] + self.cursor.preferredColumn,
                    previousLine['startAt'] + len(previousLine['text']),
                )

                self.cursor.set(
                    line=previousLine['lineIndex'],
                    column=desiredColumn,
                    lines=self.text,
                )

            else:
                self.cursor.set(self.cursor.line, 0, self.text)
                self._setPreferredColumn()
        
        self._ensureCursorVisible()

    def _handleDown(self) -> None:
        self.resetSelection()

        visualLineIndex = self.getCurrentVisualLineIndex()

        if visualLineIndex != -1:
            if visualLineIndex < len(self.cachedVisualLines) - 1:
                nextLine = self.cachedVisualLines[visualLineIndex + 1]

                desiredColumn = min(
                    nextLine['startAt'] + self.cursor.preferredColumn,
                    nextLine['startAt'] + len(nextLine['text']),
                )

                self.cursor.set(
                    line=nextLine['lineIndex'], column=desiredColumn, lines=self.text
                )

            else:
                visualLine = self.cachedVisualLines[visualLineIndex]
                self.cursor.set(
                    line=self.cursor.line,
                    column=visualLine['startAt'] + len(visualLine['text']),
                    lines=self.text,
                )
                self._setPreferredColumn()
        
        self._ensureCursorVisible()

    def _handleLeft(self, event: pygame.Event) -> None:
        if self.isEmptySelection():
            self.resetSelection()

        if event.mod & pygame.KMOD_CTRL:
            self._moveCursorWordLeft()

        elif self.cursor.column == 0 and self.cursor.line > 0:
            self.cursor.set(
                self.cursor.line - 1, len(self.text[self.cursor.line - 1]), self.text
            )
        else:
            self.cursor.set(self.cursor.line, max(self.cursor.column - 1, 0), self.text)

        if event.mod & pygame.KMOD_SHIFT:
            self.selectionEnd.set(self.cursor.line, self.cursor.column, self.text)
        else:
            self.resetSelection()

        self._setPreferredColumn()
        self._ensureCursorVisible()

    def _handleRight(self, event: pygame.Event) -> None:
        if self.isEmptySelection():
            self.resetSelection()

        if event.mod & pygame.KMOD_CTRL:
            self._moveCursorWordRight()

        elif self.cursor.column == len(
            self.text[self.cursor.line]
        ) and self.cursor.line + 1 < len(self.text):
            self.cursor.set(self.cursor.line + 1, 0, self.text)
        else:
            self.cursor.set(self.cursor.line, self.cursor.column + 1, self.text)

        if event.mod & pygame.KMOD_SHIFT:
            self.selectionEnd.set(self.cursor.line, self.cursor.column, self.text)
        else:
            self.resetSelection()

        self._setPreferredColumn()
        self._ensureCursorVisible()

    def _handleHome(self, event: pygame.Event) -> None:
        if self.isEmptySelection():
            self.resetSelection()

        if event.mod & pygame.KMOD_CTRL:
            self.cursor.set(0, 0, self.text)
            
            if event.mod & pygame.KMOD_SHIFT:
                self.selectionEnd.set(self.cursor.line, self.cursor.column, self.text)
            else:
                self.resetSelection()

        else:
            visualLineIndex = self.getCurrentVisualLineIndex()

            if visualLineIndex != -1:
                visualLine = self.cachedVisualLines[visualLineIndex]
                self.cursor.set(self.cursor.line, visualLine['startAt'], self.text)
                self._setPreferredColumn()

            self.resetSelection()
        
        self._ensureCursorVisible()

    def _handleEnd(self, event: pygame.Event) -> None:
        if self.isEmptySelection():
            self.resetSelection()

        if event.mod & pygame.KMOD_CTRL:
            self.cursor.set(len(self.text) - 1, len(self.text[-1]), self.text)
            
            if event.mod & pygame.KMOD_SHIFT:
                self.selectionEnd.set(self.cursor.line, self.cursor.column, self.text)
            else:
                self.resetSelection()

        else:
            visualLineIndex = self.getCurrentVisualLineIndex()

            if visualLineIndex != -1:
                visualLine = self.cachedVisualLines[visualLineIndex]
                self.cursor.set(
                    self.cursor.line,
                    visualLine['startAt'] + len(visualLine['text']),
                    self.text,
                )
                self._setPreferredColumn()

            self.resetSelection()

        self._ensureCursorVisible()

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
            if not (self.firstVisibleLineIndex <= i < self.firstVisibleLineIndex + self.maxVisibleLines):
                continue

            lineY = self._actualY + (i - self.firstVisibleLineIndex) * self.fontSize

            textSurface = self.font.render(visualLine['text'], True, colour)
            self.win.blit(textSurface, (self._actualX, lineY))

    def _drawCursor(self) -> None:
        if self.selected and self.showCursor:
            visualLineIndex = self.getCurrentVisualLineIndex()

            if not (self.firstVisibleLineIndex <= visualLineIndex < self.firstVisibleLineIndex + self.maxVisibleLines):
                return

            if visualLineIndex != -1:
                visualLine = self.cachedVisualLines[visualLineIndex]

                relativeColumn = self.cursor.column - visualLine['startAt']
                text = visualLine['text'][:relativeColumn]

                startX = self._actualX + self.font.size(text)[0]
                endX = startX

                startY = self._actualY + self.fontSize * (visualLineIndex - self.firstVisibleLineIndex)
                endY = startY + self.fontSize

                pygame.draw.line(
                    self.win,
                    self.cursorColour,
                    (startX, startY),
                    (endX, endY),
                    self.cursorWidth,
                )

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

        start, end = self.getNormalizedSelection()

        for i, visualLine in enumerate(self.cachedVisualLines):
            if not (self.firstVisibleLineIndex <= i < self.firstVisibleLineIndex + self.maxVisibleLines):
                continue

            lineIndex = visualLine['lineIndex']

            if not (start.line <= lineIndex <= end.line):
                continue

            lineY = self._actualY + self.fontSize * (i - self.firstVisibleLineIndex)

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

            textBefore = visualLine['text'][:localStart]
            textBeforeWidth = self.font.size(textBefore)[0]

            textUpToEnd = visualLine['text'][:localEnd]
            textUpToEndWidth = self.font.size(textUpToEnd)[0]

            textWidth = textUpToEndWidth - textBeforeWidth

            if isEmptyLine or isEndOfLogicalLine:
                textWidth += self.font.size(' ')[0]

            pygame.draw.rect(
                self.win,
                self.selectionColour,
                (self._actualX + textBeforeWidth, lineY, textWidth, self.fontSize),
            )

    def _ensureCursorVisible(self) -> None:
        visualLineIndex = self.getCurrentVisualLineIndex()
        if visualLineIndex == -1:
            return

        if visualLineIndex < self.firstVisibleLineIndex:
            self.firstVisibleLineIndex = visualLineIndex
        
        elif visualLineIndex >= self.firstVisibleLineIndex + self.maxVisibleLines:
            self.firstVisibleLineIndex = visualLineIndex - self.maxVisibleLines + 1
            
        maxScroll = max(0, len(self.cachedVisualLines) - self.maxVisibleLines)
        self.firstVisibleLineIndex = max(0, min(self.firstVisibleLineIndex, maxScroll))

    def _updateLayout(self) -> None:
        neededHeight = len(self.cachedVisualLines) * self.fontSize + self.textOffsetTop + self.borderThickness * 2
        
        self._height = max(self._minHeight, min(neededHeight, self._maxHeight))
        
        self._actualHeight = (
            self._height
            - self.textOffsetTop
            - self.borderThickness * 2
        )
        
        self.maxVisibleLines = self._actualHeight // self.fontSize
        if self.maxVisibleLines == 0:
            self.maxVisibleLines = 1

    def addText(self, text: str) -> None:
        if not self.isEmptySelection():
            self.eraseSelectedText()

        text = text.replace('\t', ' ' * self.tabSpaces).replace('\r', '')
        lines = text.split('\n')

        rightPart = self.text[self.cursor.line][self.cursor.column :]

        for i, line in enumerate(lines):
            self.text[self.cursor.line] = (
                self.text[self.cursor.line][: self.cursor.column] + line
            )
            self.cursor.set(self.cursor.line, self.cursor.column + len(line), self.text)

            if i != len(lines) - 1:
                self.text.insert(self.cursor.line + 1, '')
                self.cursor.set(self.cursor.line + 1, 0, self.text)

        self.text[self.cursor.line] += rightPart

        self._setVisualLines()
        self._setPreferredColumn()
        self._ensureCursorVisible()
        self.onTextChanged(*self.onTextChangedParams)

    def eraseSelectedText(self) -> None:
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

        self._setVisualLines()
        self._setPreferredColumn()
        self.onTextChanged(*self.onTextChangedParams)

    def getNormalizedSelection(self) -> tuple[Cursor, Cursor]:
        start = self.selectionStart
        end = self.selectionEnd

        if (start.line, start.column) > (end.line, end.column):
            start, end = end, start

        return start, end

    def _setVisualLines(self) -> None:
        self.cachedVisualLines = []
        for lineIndex, line in enumerate(self.text):
            if line == '':
                self.cachedVisualLines.append(
                    {'text': '', 'lineIndex': lineIndex, 'startAt': 0}
                )
                continue

            start = 0
            while start < len(line):
                end = start
                lastSpace = -1

                while end < len(line):
                    if line[end] == ' ':
                        lastSpace = end

                    testSegment = line[start : end + 1]
                    if self.font.size(testSegment)[0] > self._actualWidth:
                        break
                    end += 1

                if end == len(line):
                    self.cachedVisualLines.append(
                        {
                            'text': line[start:end],
                            'lineIndex': lineIndex,
                            'startAt': start,
                        }
                    )
                    break

                if end == start:
                    end = start + 1
                    self.cachedVisualLines.append(
                        {
                            'text': line[start:end],
                            'lineIndex': lineIndex,
                            'startAt': start,
                        }
                    )
                    start = end

                elif lastSpace >= start and line[start:lastSpace].strip() != '':
                    self.cachedVisualLines.append(
                        {
                            'text': line[start : lastSpace + 1],
                            'lineIndex': lineIndex,
                            'startAt': start,
                        }
                    )
                    start = lastSpace + 1

                else:
                    self.cachedVisualLines.append(
                        {
                            'text': line[start:end],
                            'lineIndex': lineIndex,
                            'startAt': start,
                        }
                    )
                    start = end

        self._updateLayout()

    def resetSelection(self) -> None:
        self.selectionStart.set(self.cursor.line, self.cursor.column, self.text)
        self.selectionEnd.set(self.cursor.line, self.cursor.column, self.text)

    def getCurrentVisualLineIndex(self) -> int:
        for lineIndex, visualLine in enumerate(self.cachedVisualLines):
            if visualLine['lineIndex'] != self.cursor.line:
                continue
            lineWidth = visualLine['startAt'] + len(visualLine['text'])
            if visualLine['startAt'] <= self.cursor.column <= lineWidth:
                if (
                    self.cursor.column == lineWidth != 0
                    and lineIndex + 1 < len(self.cachedVisualLines)
                    and self.cachedVisualLines[lineIndex + 1]['lineIndex']
                    == self.cursor.line
                ):
                    return lineIndex + 1
                return lineIndex
        return -1

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

    def isEmptySelection(self) -> bool:
        return (self.selectionStart.line, self.selectionStart.column) == (
            self.selectionEnd.line,
            self.selectionEnd.column,
        )

    def escape(self) -> None:
        self.selected = False
        self.showCursor = False
        self.resetSelection()
        pygame.key.set_repeat(*self.originalRepeat)

    def setText(self, text: str) -> None:
        self.text = ['']
        self.cursor.set(0, 0, self.text)
        self.resetSelection()
        self.addText(text)

    def _setPreferredColumn(self) -> None:
        visualLineIndex = self.getCurrentVisualLineIndex()

        if visualLineIndex != -1:
            visualLine = self.cachedVisualLines[visualLineIndex]
            relativeColumn = self.cursor.column - visualLine['startAt']

            self.cursor.preferredColumn = relativeColumn

    def _moveCursorWordLeft(self) -> None:
        if self.cursor.column == 0 and self.cursor.line > 0:
            self.cursor.set(
                self.cursor.line - 1,
                len(self.text[self.cursor.line - 1]),
                self.text,
            )

        while (
            self.cursor.column - 1 >= 0
            and not self.text[self.cursor.line][self.cursor.column - 1].isalnum()
        ):
            self.cursor.set(self.cursor.line, self.cursor.column - 1, self.text)

        while (
            self.cursor.column - 1 >= 0
            and self.text[self.cursor.line][self.cursor.column - 1].isalnum()
        ):
            self.cursor.set(self.cursor.line, self.cursor.column - 1, self.text)

    def _moveCursorWordRight(self) -> None:
        if self.cursor.column == len(
            self.text[self.cursor.line]
        ) and self.cursor.line + 1 < len(self.text):
            self.cursor.set(self.cursor.line + 1, 0, self.text)

        while (
            self.cursor.column < len(self.text[self.cursor.line])
            and not self.text[self.cursor.line][self.cursor.column].isalnum()
        ):
            self.cursor.set(self.cursor.line, self.cursor.column + 1, self.text)

        while (
            self.cursor.column < len(self.text[self.cursor.line])
            and self.text[self.cursor.line][self.cursor.column].isalnum()
        ):
            self.cursor.set(self.cursor.line, self.cursor.column + 1, self.text)

    def _setColumnFromMouse(self, mouseX: int, mouseY: int) -> None:
        if not self.cachedVisualLines:
            return

        minVisibleY = self._actualY + self.fontSize // 2
        maxVisibleY = self._actualY + self._actualHeight - self.fontSize // 2
        mouseY = max(minVisibleY, min(mouseY, maxVisibleY))

        for i, visualLine in enumerate(self.cachedVisualLines):
            if not (self.firstVisibleLineIndex <= i < self.firstVisibleLineIndex + self.maxVisibleLines):
                continue

            lineY = self._actualY + self.fontSize * (i - self.firstVisibleLineIndex)

            if lineY < mouseY < lineY + self.fontSize:
                if visualLine['lineIndex'] != self.cursor.line:
                    self.cursor.set(
                        visualLine['lineIndex'], self.cursor.column, self.text
                    )

                if len(visualLine['text']) == 0:
                    self.cursor.set(self.cursor.line, visualLine['startAt'], self.text)
                    break

                firstLetter = visualLine['text'][0]
                firstLetterWidth = self.font.size(firstLetter)[0]

                if self._actualX <= mouseX < self._actualX + firstLetterWidth // 2:
                    self.cursor.set(self.cursor.line, visualLine['startAt'], self.text)
                    break

                wholeLine = visualLine['text']
                wholeLineWidth = self.font.size(wholeLine)[0]

                if self._actualX + wholeLineWidth <= mouseX:
                    self.cursor.set(
                        self.cursor.line,
                        visualLine['startAt'] + len(visualLine['text']),
                        self.text,
                    )
                    break

                count = 0

                while True:

                    count += 1
                    textBefore = visualLine['text'][: count - 1]
                    textCurrent = visualLine['text'][:count]
                    textAfter = visualLine['text'][: count + 1]

                    x1 = (
                        self._actualX
                        + (
                            self.font.size(textBefore)[0]
                            + self.font.size(textCurrent)[0]
                        )
                        / 2
                    )
                    x2 = (
                        self._actualX
                        + (
                            self.font.size(textCurrent)[0]
                            + self.font.size(textAfter)[0]
                        )
                        / 2
                    )

                    if x1 <= mouseX <= x2:
                        self.cursor.set(
                            self.cursor.line, visualLine['startAt'] + count, self.text
                        )
                        break

                    if mouseX < self._actualX:
                        self.cursor.set(
                            self.cursor.line, visualLine['startAt'], self.text
                        )
                        break

                break

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
        450,
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
