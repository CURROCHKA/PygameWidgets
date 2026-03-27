import pygame
import pygame_widgets
from pygame_widgets.widget import WidgetBase
from pygame_widgets.mouse import Mouse, MouseState

from dataclasses import dataclass


class TextBox(WidgetBase):
    # Times in ms
    REPEAT_DELAY = 400
    REPEAT_INTERVAL = 70
    CURSOR_INTERVAL = 400

    def __init__(self, win, x, y, width, height, isSubWidget=False, **kwargs) -> None:
        """ A customisable textbox for Pygame

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
        """
        super().__init__(win, x, y, width, height, isSubWidget)

        # Widget state
        self.selected = False
        self.isChanged = False
        self.isLabel = kwargs.get('isLabel', False)
        self.originalRepeat = pygame.key.get_repeat()

        # Cursor state and style
        self.cursor = Cursor()
        self.cursorWidth = kwargs.get('cursorWidth', 2)
        self.cursorColour = kwargs.get('cursorColour', (0, 0, 0))

        # Text state
        self.text = ['']
        self.cachedVisualLines = []
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

        # Highlight state and style
        self.highlightedText = ['']
        self.highlightStartLine = 0
        self.highlightEndLine = 0
        self.highlightStartInline = 0
        self.highlightEndInline = 0
        self.highlightColour = kwargs.get('highlightColour', (166, 210, 255))

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

    def listen(self, events) -> None:
        """ Wait for inputs

        :param events: Use pygame.event.get()
        :type events: list of pygame.event.Event
        """
        if self._hidden or self._disabled:
            return

        # Selection
        mouseState = Mouse.getMouseState()
        x, y = Mouse.getMousePos()

        if mouseState == MouseState.CLICK:
            if self.contains(x, y):
                self.selected = True
                self.showCursor = True
                self.cursorTime = pygame.time.get_ticks()

                self._setCursorPositionFromMouse(x, y)

                pygame.key.set_repeat(self.REPEAT_DELAY, self.REPEAT_INTERVAL)
            else:
                self.escape()
            
        elif mouseState == MouseState.DRAG and self.contains(x, y):
            self.cursorTime = pygame.time.get_ticks()
            self._setCursorPositionFromMouse(x, y)

        # Keyboard Input
        if self.selected:
            for event in events:
                if event.type == pygame.KEYDOWN:
                    self.isChanged = True
                    self.showCursor = True
                    self.cursorTime = pygame.time.get_ticks()

                    if event.key == pygame.K_BACKSPACE:
                        self.handleBackspace()

                    elif event.key == pygame.K_DELETE:
                        self.handleDelete()

                    elif event.key == pygame.K_RETURN:
                        if event.mod & pygame.KMOD_SHIFT or event.mod & pygame.KMOD_CTRL:
                            self.addText('\n')
                        else:
                            self.onSubmit(*self.onSubmitParams)

                    elif event.key in [pygame.K_UP, pygame.K_KP_8 if not event.mod & pygame.KMOD_NUM else -1]:
                        self.handleUp()
                    
                    elif event.key in [pygame.K_DOWN, pygame.K_KP_2 if not event.mod & pygame.KMOD_NUM else -1]:
                        self.handleDown()

                    elif event.key in [pygame.K_LEFT, pygame.K_KP_4 if not event.mod & pygame.KMOD_NUM else -1]:
                        self.handleLeft()
                            
                    elif event.key in [pygame.K_RIGHT, pygame.K_KP_6 if not event.mod & pygame.KMOD_NUM else -1]:
                        self.handleRight()

                    elif event.key in [pygame.K_HOME, pygame.K_KP_7 if not event.mod & pygame.KMOD_NUM else -1]:
                        visualLineIndex = self.getCurrentVisualLineIndex()

                        visualLine = self.cachedVisualLines[visualLineIndex]
                        self.cursor.column = visualLine['startAt']
                        self._setOldRelativeCursorPosition()

                    elif event.key in [pygame.K_END, pygame.K_KP_1 if not event.mod & pygame.KMOD_NUM else -1]:
                        visualLineIndex = self.getCurrentVisualLineIndex()

                        visualLine = self.cachedVisualLines[visualLineIndex]
                        self.cursor.column = visualLine['startAt'] + len(visualLine['text'])
                        self._setOldRelativeCursorPosition()

                    elif event.key == pygame.K_a and event.mod & pygame.KMOD_CTRL:
                        self.highlightStartLine = 0
                        self.highlightEndLine = len(self.text)
                        self.highlightStartInline = 0
                        self.highlightEndInline = len(self.text[-1])
                        self.highlight()

                    elif event.key == pygame.K_c and event.mod & pygame.KMOD_CTRL:
                        pass

                    elif event.key == pygame.K_v and event.mod & pygame.KMOD_CTRL:
                        pass

                    elif event.key == pygame.K_x and event.mod & pygame.KMOD_CTRL:
                        pass

                    elif event.key == pygame.K_INSERT:
                        self.insertOn = not self.insertOn # TODO: add insert logic

                    elif event.key == pygame.K_ESCAPE:
                        self.escape()

                    elif not self.isLabel:
                        if event.unicode:
                            self.addText(event.unicode)

    def handleBackspace(self):
        if self.cursor.column > 0:
            line = self.text[self.cursor.line]
            self.text[self.cursor.line] = line[:self.cursor.column - 1] + line[self.cursor.column:]
            self.cursor.column -= 1
            self._setOldRelativeCursorPosition()
            self.onTextChanged(*self.onTextChangedParams)

        elif self.cursor.line > 0:
            self.cursor.column = len(self.text[self.cursor.line - 1])
            self.text[self.cursor.line - 1] += self.text[self.cursor.line]
            self.text.pop(self.cursor.line)
            self.cursor.line -= 1
            self._setOldRelativeCursorPosition()
            self.onTextChanged(*self.onTextChangedParams)

    def handleDelete(self):
        if self.cursor.column < len(self.text[self.cursor.line]):

            self.text[self.cursor.line] = (
                self.text[self.cursor.line][:self.cursor.column] 
                + self.text[self.cursor.line][self.cursor.column + 1:]
            )

            self.onTextChanged(*self.onTextChangedParams)
        
        elif self.cursor.line < len(self.text) - 1:
            self.text[self.cursor.line] += self.text[self.cursor.line + 1]
            self.text.pop(self.cursor.line + 1)
            self.onTextChanged(*self.onTextChangedParams)

    def handleUp(self):
        visualLineIndex = self.getCurrentVisualLineIndex()

        if visualLineIndex - 1 >= 0:
            visualLine = self.cachedVisualLines[visualLineIndex]
            relativePosition = self.cursor.column - visualLine['startAt']

            previousLine = self.cachedVisualLines[visualLineIndex - 1]

            if visualLine['lineIndex'] != previousLine['lineIndex']:
                self.cursor.line -= 1

            self.cursor.column = max(previousLine['startAt'] + relativePosition,
                                        previousLine['startAt'] + self.cursor.prefferedColumn)
            self.cursor.column = min(self.cursor.column,
                                        previousLine['startAt'] + len(previousLine['text']))
            
    def handleDown(self):
        visualLineIndex = self.getCurrentVisualLineIndex()

        if visualLineIndex + 1 < len(self.cachedVisualLines):
            visualLine = self.cachedVisualLines[visualLineIndex]
            relativePosition = self.cursor.column - visualLine['startAt']

            nextLine = self.cachedVisualLines[visualLineIndex + 1]

            if visualLine['lineIndex'] != nextLine['lineIndex']:
                self.cursor.line += 1

            self.cursor.column = max(nextLine['startAt'] + relativePosition,
                                        nextLine['startAt'] + self.cursor.prefferedColumn)
            self.cursor.column = min(self.cursor.column,
                                        nextLine['startAt'] + len(nextLine['text']))
            
    def handleLeft(self):
        if event.mod & pygame.KMOD_CTRL:

            shiftPressed = False
            if event.mod & pygame.KMOD_SHIFT:
                if self.isEmptyText(self.highlightedText):
                    self.highlightStartLine = self.cursor.line
                    self.highlightStartInline = self.cursor.column
                shiftPressed = True
            else:
                self.resetHighlight()

            if self.cursor.column > 0:

                visualLineIndex = self.getCurrentVisualLineIndex()

                visualLine = self.cachedVisualLines[visualLineIndex]
                relativePosition = self.cursor.column - visualLine['startAt'] - 1

                while relativePosition >= 0 and visualLine['text'][relativePosition] in ' ();:,./!?':
                    relativePosition -= 1

                while relativePosition >= 0 and visualLine['text'][relativePosition] not in ' ();:,./!?':
                    relativePosition -= 1
                
                self.cursor.set(self.cursor.line, visualLine['startAt'] + relativePosition + 1, self.text)

                if shiftPressed:
                    self.highlightEndLine = self.cursor.line
                    self.highlightEndInline = self.cursor.column
                    self.highlight()

        elif self.cursor.column == 0 and self.cursor.line - 1 >= 0:
            self.cursor.line -= 1
            self.cursor.column = len(self.text[self.cursor.line])
            self.resetHighlight()
        else:
            self.cursor.column = max(self.cursor.column - 1, 0)
            self.resetHighlight()

        self._setOldRelativeCursorPosition()

    def handleRight(self):
        if event.mod & pygame.KMOD_CTRL:

            shiftPressed = False
            if event.mod & pygame.KMOD_SHIFT:
                if self.isEmptyText(self.highlightedText):
                    self.highlightStartLine = self.cursor.line
                    self.highlightStartInline = self.cursor.column
                shiftPressed = True
            else:
                self.resetHighlight()

            if self.cursor.column < len(self.text[self.cursor.line]):

                visualLineIndex = self.getCurrentVisualLineIndex()

                # if visualLineIndex != -1:
                visualLine = self.cachedVisualLines[visualLineIndex]
                relativePosition = self.cursor.column - visualLine['startAt']

                while relativePosition < len(visualLine['text']) and visualLine['text'][relativePosition] in ' ();:,./!?':
                    relativePosition += 1

                while relativePosition < len(visualLine['text']) and visualLine['text'][relativePosition] not in ' ();:,./!?':
                    relativePosition += 1

                self.cursor.set(self.cursor.line, visualLine['startAt'] + relativePosition, self.text)

                if shiftPressed:
                    self.highlightEndLine = self.cursor.line
                    self.highlightEndInline = self.cursor.column
                    self.highlight()
            
        elif self.cursor.column == len(self.text[self.cursor.line]) \
            and self.cursor.line + 1 < len(self.text):
            self.cursor.line += 1
            self.cursor.column = 0
            self.resetHighlight()
        else:
            self.cursor.column = min(self.cursor.column + 1, len(self.text[self.cursor.line]))
            self.resetHighlight()

        self._setOldRelativeCursorPosition()

    def draw(self) -> None:
        """ Display to surface """
        if self._hidden:
            return
        if self.selected:
            self.updateCursor()
        self.drawBorder()
        self.drawBackground()
        self.drawHighlight()
        self.drawText()
        self.drawCursor()

    def drawText(self) -> None:
        """ Отрисовка текста и расчет позиции курсора """
        xBase = self._x + self.textOffsetLeft + self.borderThickness
        yBase = self._y + self.textOffsetTop + self.borderThickness

        if self.isChanged:
            self.cachedVisualLines = self.getVisualLines()
            self.isChanged = False
        
        # Определяем, что именно мы рисуем (текст или плейсхолдер)
        if self.isEmptyText(self.text):
            displayLines = [{'text': self.placeholderText, 'lineIndex': 0, 'startAt': 0}]
            colour = self.placeholderTextColour
        else:
            displayLines = self.cachedVisualLines
            colour = self.textColour

        self.cursorCoords = None

        for i, visualLine in enumerate(displayLines):
            lineY = yBase + i * self.fontSize
            
            textSurface = self.font.render(visualLine['text'], True, colour)
            self.win.blit(textSurface, (xBase, lineY))

            if visualLine['lineIndex'] == self.cursor.line:
                relativePosition = self.cursor.column - visualLine['startAt']
                
                if 0 <= relativePosition <= len(visualLine['text']):
                    textBeforeCursor = visualLine['text'][:relativePosition]
                    cursorOffset = self.font.size(textBeforeCursor)[0]

                    self.cursorCoords = (xBase + cursorOffset, lineY)

    def drawCursor(self) -> None:
        """ Отрисовка мигающей линии курсора """
        if self.selected and self.showCursor and self.cursorCoords:
            # Используем координаты, рассчитанные в drawText
            startX, startY = self.cursorCoords
            endX, endY = startX, startY + self.fontSize
            
            pygame.draw.line(
                self.win, 
                self.cursorColour, 
                (startX, startY), 
                (endX, endY), 
                self.cursorWidth
            )
            
    def drawBorder(self) -> None:
        pygame.draw.rect(self.win, self.borderColour, (self._x, self._y, self._width, self._height), border_radius=self.radius)

    def drawBackground(self) -> None:
        rect = (self._x + self.borderThickness, self._y + self.borderThickness, 
                      self._width - self.borderThickness * 2, self._height - self.borderThickness * 2)
        pygame.draw.rect(self.win, self.colour, rect, border_radius=self.radius)

    def drawHighlight(self) -> None:
        xBase = self._x + self.textOffsetLeft + self.borderThickness
        yBase = self._y + self.textOffsetTop + self.borderThickness

        startLine = min(self.highlightStartLine, self.highlightEndLine)
        endLine = max(self.highlightStartLine, self.highlightEndLine)

        startInLine = self.highlightStartInline
        endInLine = self.highlightEndInline
        
        if self.highlightStartLine > self.highlightEndLine or \
           (self.highlightStartLine == self.highlightEndLine and self.highlightStartInline > self.highlightEndInline):
            startInLine, endInLine = endInLine, startInLine

        for i, visualLine in enumerate(self.cachedVisualLines):
            LineIndex = visualLine['lineIndex']
            
            if startLine <= LineIndex <= endLine:
                lineY = yBase + self.fontSize * i
                
                lineStart = visualLine['startAt']
                
                # Вычисляем границы выделения конкретно для этой логической строки
                highlightStart = startInLine if LineIndex == startLine else 0
                highlightEnd = endInLine if LineIndex == endLine else len(self.text[LineIndex])
                
                # Ограничиваем эти границы рамками текущего визуального куска
                localStart = max(0, highlightStart - lineStart)
                localEnd = min(len(visualLine['text']), highlightEnd - lineStart)
                
                if localStart < localEnd:
                    textBefore = visualLine['text'][:localStart]
                    textHighlight = visualLine['text'][localStart:localEnd]

                    textBeforeWidth = self.font.size(textBefore)[0]
                    textWidth = self.font.size(textHighlight)[0]
                    
                    pygame.draw.rect(self.win, self.highlightColour,
                                     (xBase + textBeforeWidth, lineY, textWidth, self.fontSize))
       
    def addText(self, text: str) -> None:
        text = text.replace('\t', ' ' * self.tabSpaces)
        text = text.replace('\r', '')
        lines = text.split('\n')

        rightPart = self.text[self.cursor.line][self.cursor.column:]

        for i, line in enumerate(lines):
            currentLine = self.text[self.cursor.line]
            self.text[self.cursor.line] = currentLine[:self.cursor.column] + line
            self.cursor.column += len(line)

            if i != len(lines) - 1:
                self.cursor.line += 1
                self.cursor.column = 0
                self.text.insert(self.cursor.line, '')

            self.onTextChanged(*self.onTextChangedParams)

        self.text[self.cursor.line] += rightPart

        self.cursor.prefferedColumn = self.cursor.column

    def getVisualLines(self) -> list[dict]:
        """ Разбивает логические строки на визуальные с помощью font.size() """
        visualLines = []
        for lineIndex, line in enumerate(self.text):
            if line == '':
                visualLines.append({'text': '', 'lineIndex': lineIndex, 'startAt': 0})
                continue

            start = 0
            currentSegment = ''

            for i, char in enumerate(line):
                # Замеряем реальную ширину строки, которую собираемся отрендерить
                testSegment = currentSegment + char
                segmentWidth = self.font.size(testSegment)[0]

                if segmentWidth > self._actualWidth and currentSegment != '':
                    # Текущий кусок больше не лезет. Сохраняем то, что было ДО этого символа
                    visualLines.append({
                        'text': currentSegment,
                        'lineIndex': lineIndex,
                        'startAt': start
                    })
                    # Начинаем новую визуальную строку с невлезшего символа
                    start = i
                    currentSegment = char
                else:
                    currentSegment = testSegment
            
            # Добавляем остаток строки
            visualLines.append({
                'text': currentSegment,
                'lineIndex': lineIndex,
                'startAt': start
            })
            
        return visualLines
    
    def highlight(self) -> None:
        startLine = min(self.highlightStartLine, self.highlightEndLine)
        endLine = max(self.highlightStartLine, self.highlightEndLine)

        startInLine = self.highlightStartInline
        endInLine = self.highlightEndInline
        
        if self.highlightStartLine > self.highlightEndLine or \
           (self.highlightStartLine == self.highlightEndLine and self.highlightStartInline > self.highlightEndInline):
            startInLine, endInLine = endInLine, startInLine
        
        self.highlightStartLine = startLine
        self.highlightEndLine = endLine
        self.highlightStartInline = startInLine
        self.highlightEndInline = endInLine

    def resetHighlight(self) -> None:
        self.highlightStartLine = self.highlightEndLine   = 0
        self.highlightStartInline = self.highlightEndInline = 0
        self.highlightedText = ['']
    
    def getCurrentVisualLineIndex(self) -> int:
        for lineIndex, visualLine in enumerate(self.cachedVisualLines):
            lineStartAt = visualLine['startAt']
            if lineStartAt <= self.cursor.column <= lineStartAt + len(visualLine['text']):
                return lineIndex

    def updateCursor(self) -> None:
        now = pygame.time.get_ticks()
        if now - self.cursorTime >= self.CURSOR_INTERVAL:
            self.showCursor = not self.showCursor
            self.cursorTime = now
    
    def isEmptyText(self, text: list[str]) -> bool:
        return len(text) == 1 and text[0] == ''
    
    def escape(self) -> None:
        self.selected = False
        self.showCursor = False
        pygame.key.set_repeat(*self.originalRepeat)

    def setText(self, text: str) -> None:
        self.text = ['']
        self.cursor.set(0, 0, self.text)
        self.addText(text)
        self.isChanged = True

    def _setOldRelativeCursorPosition(self) -> None:
        visualLineIndex = self.getCurrentVisualLineIndex()

        visualLine = self.cachedVisualLines[visualLineIndex]
        relativePosition = self.cursor.column - visualLine['startAt']

        self.cursor.prefferedColumn = relativePosition

    def _setCursorPositionFromMouse(self, mouseX: int, mouseY: int):
        xBase = self._x + self.textOffsetLeft + self.borderThickness
        yBase = self._y + self.textOffsetTop + self.borderThickness
        
        for i, visualLine in enumerate(self.cachedVisualLines):
            lineY = yBase + self.fontSize * i

            if lineY < mouseY < lineY + self.fontSize:
                if visualLine['lineIndex'] != self.cursor.line:
                    self.cursor.line = visualLine['lineIndex']

                if len(visualLine['text']) == 0:
                    self.cursor.column = visualLine['startAt']
                    break

                firstLetter = visualLine['text'][0]
                firstLetterWidth = self.font.size(firstLetter)[0]

                if self._x <= mouseX < xBase + firstLetterWidth // 2:
                    self.cursor.column = visualLine['startAt']
                    break
            
                wholeLine = visualLine['text']
                wholeLineWidth = self.font.size(wholeLine)[0]

                if xBase + wholeLineWidth <= mouseX:
                    self.cursor.column = visualLine['startAt'] + len(visualLine['text'])
                    break

                count = 0

                while True:

                    count += 1
                    textBefore = visualLine['text'][:count - 1]
                    textCurrent = visualLine['text'][:count]
                    textAfter = visualLine['text'][:count + 1]

                    x1 = xBase + (self.font.size(textBefore)[0] + self.font.size(textCurrent)[0]) / 2
                    x2 = xBase + (self.font.size(textCurrent)[0] + self.font.size(textAfter)[0]) / 2

                    if x1 <= mouseX <= x2:
                        self.cursor.column = visualLine['startAt'] + count
                        break

                break

    def getText(self) -> str:
        return '\n'.join(self.text)


@dataclass
class Cursor:
    line: int = 0
    column: int = 0
    prefferedColumn: int = 0

    def clamp(self, lines: list[str]) -> None:
        self.line = max(0, min(self.line, len(lines) - 1))
        self.column = max(0, min(self.column, len(lines[self.line])))

    def set(self, line: int, column: int, lines: list[str]) -> None:
        self.line = line
        self.column = column
        self.clamp(lines)
        self.preferredColumn = self.column

if __name__ == '__main__':
    def output():
        print(textbox.getText())
        textbox.setText('')
    
    pygame.init()    
    win = pygame.display.set_mode((1000, 600))

    clock = pygame.time.Clock()

    textbox = TextBox(win, 100, 100, 800, 400, fontSize=50, borderColour=(255, 0, 0),
                      textColour=(0, 200, 0), onSubmit=output, radius=10,
                      borderThickness=5, placeholderText='Enter something:')

    run = True
    while run:
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                pygame.quit()
                run = False
                quit()

        win.fill((255, 255, 255))

        pygame_widgets.update(events)
        pygame.display.update()

        clock.tick(60)
