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

    def set(self, line: int, column: int, lines: list[str], updatePreferredColumn: bool = True) -> None:
        self.line = line
        self.column = column
        self.clamp(lines)
        if updatePreferredColumn:
            self.preferredColumn = self.column


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
        self.showCursor = not self.isLabel
        self.cursorTime = 0

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

        self.highlightStart = Cursor()
        self.highlightEnd = Cursor()
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
        self._actualX = self._x + self.textOffsetLeft + self.borderThickness
        self._actualY = self._y + self.textOffsetTop + self.borderThickness

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

                self._setColumnFromMouse(x, y)

                pygame.key.set_repeat(self.REPEAT_DELAY, self.REPEAT_INTERVAL)
            else:
                self.escape()
            
        elif mouseState == MouseState.DRAG and self.contains(x, y):
            self.cursorTime = pygame.time.get_ticks()
            self._setColumnFromMouse(x, y)

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
                        self.handleLeft(event)
                            
                    elif event.key in [pygame.K_RIGHT, pygame.K_KP_6 if not event.mod & pygame.KMOD_NUM else -1]:
                        self.handleRight(event)

                    elif event.key in [pygame.K_HOME, pygame.K_KP_7 if not event.mod & pygame.KMOD_NUM else -1]:
                        visualLineIndex = self.getCurrentVisualLineIndex()

                        if visualLineIndex != -1:
                            visualLine = self.cachedVisualLines[visualLineIndex]
                            self.cursor.set(self.cursor.line, visualLine['startAt'], self.text)
                            self._setPreferredColumn()

                    elif event.key in [pygame.K_END, pygame.K_KP_1 if not event.mod & pygame.KMOD_NUM else -1]:
                        visualLineIndex = self.getCurrentVisualLineIndex()

                        if visualLineIndex != -1:
                            visualLine = self.cachedVisualLines[visualLineIndex]
                            self.cursor.set(self.cursor.line, visualLine['startAt'] + len(visualLine['text']), self.text)
                            self._setPreferredColumn()

                    elif event.key == pygame.K_a and event.mod & pygame.KMOD_CTRL:
                        self.highlightStart.set(0, 0, self.text)
                        self.highlightEnd.set(len(self.text), len(self.text[-1]), self.text)
                        self.cursor.set(len(self.text), len(self.text[-1]), self.text)

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

    def handleBackspace(self) -> None:
        if self.cursor.column > 0:
            line = self.text[self.cursor.line]
            self.text[self.cursor.line] = line[:self.cursor.column - 1] + line[self.cursor.column:]
            self.cursor.set(self.cursor.line, self.cursor.column - 1, self.text)
            self._setPreferredColumn()
            self.onTextChanged(*self.onTextChangedParams)

        elif self.cursor.line > 0:
            self.cursor.set(self.cursor.line, len(self.text[self.cursor.line - 1]), self.text)
            self.text[self.cursor.line - 1] += self.text[self.cursor.line]
            self.text.pop(self.cursor.line)
            self.cursor.set(self.cursor.line - 1, self.cursor.column, self.text)
            self._setPreferredColumn()
            self.onTextChanged(*self.onTextChangedParams)

    def handleDelete(self) -> None:
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

    def handleUp(self) -> None:
        visualLineIndex = self.getCurrentVisualLineIndex()

        if visualLineIndex - 1 >= 0:
            previousLine = self.cachedVisualLines[visualLineIndex - 1]
            
            desiredColumn = min(
                previousLine['startAt'] + self.cursor.preferredColumn,
                previousLine['startAt'] + len(previousLine['text'])
            )

            self.cursor.set(
                line=previousLine['lineIndex'], 
                column=desiredColumn, 
                lines=self.text, 
                updatePreferredColumn=False
            )
            
    def handleDown(self) -> None:
        visualLineIndex = self.getCurrentVisualLineIndex()

        if visualLineIndex != -1 and visualLineIndex + 1 < len(self.cachedVisualLines):
            nextLine = self.cachedVisualLines[visualLineIndex + 1]

            desiredColumn = min(
                nextLine['startAt'] + self.cursor.preferredColumn,
                nextLine['startAt'] + len(nextLine['text'])
            )

            self.cursor.set(
                line=nextLine['lineIndex'], 
                column=desiredColumn, 
                lines=self.text, 
                updatePreferredColumn=False
            )
            
    def handleLeft(self, event: pygame.Event) -> None:
        if event.mod & pygame.KMOD_CTRL:

            shiftPressed = False
            if event.mod & pygame.KMOD_SHIFT:
                if self.isEmptyHighlight():
                    self.highlightStart.set(self.cursor.line, self.cursor.column, self.text)
                shiftPressed = True
            else:
                self.resetHighlight()

            if self.cursor.column > 0:

                visualLineIndex = self.getCurrentVisualLineIndex()

                if visualLineIndex != -1:
                    visualLine = self.cachedVisualLines[visualLineIndex]
                    relativeColumn = self.cursor.column - visualLine['startAt'] - 1

                    while relativeColumn >= 0 and visualLine['text'][relativeColumn] in ' ();:,./!?':
                        relativeColumn -= 1

                    while relativeColumn >= 0 and visualLine['text'][relativeColumn] not in ' ();:,./!?':
                        relativeColumn -= 1
                    
                    self.cursor.set(self.cursor.line, visualLine['startAt'] + relativeColumn + 1, self.text)

                    if shiftPressed:
                        self.highlightEnd.set(self.cursor.line, self.cursor.column, self.text)

        elif self.cursor.column == 0 and self.cursor.line - 1 >= 0:
            self.cursor.set(self.cursor.line - 1, len(self.text[self.cursor.line]), self.text)
            self.resetHighlight()
        else:
            self.cursor.set(self.cursor.line, max(self.cursor.column - 1, 0), self.text)
            self.resetHighlight()

        self._setPreferredColumn()

    def handleRight(self, event: pygame.Event) -> None:
        if event.mod & pygame.KMOD_CTRL:

            shiftPressed = False
            if event.mod & pygame.KMOD_SHIFT:
                if self.isEmptyHighlight():
                    self.highlightStart.set(self.cursor.line, self.cursor.column, self.text)
                shiftPressed = True
            else:
                self.resetHighlight()

            if self.cursor.column < len(self.text[self.cursor.line]):

                visualLineIndex = self.getCurrentVisualLineIndex()

                if visualLineIndex != -1:
                    visualLine = self.cachedVisualLines[visualLineIndex]
                    relativeColumn = self.cursor.column - visualLine['startAt']

                    while relativeColumn < len(visualLine['text']) and visualLine['text'][relativeColumn] in ' ();:,./!?':
                        relativeColumn += 1

                    while relativeColumn < len(visualLine['text']) and visualLine['text'][relativeColumn] not in ' ();:,./!?':
                        relativeColumn += 1

                    self.cursor.set(self.cursor.line, visualLine['startAt'] + relativeColumn, self.text)

                    if shiftPressed:
                        self.highlightEnd.set(self.cursor.line, self.cursor.column, self.text)
            
        elif self.cursor.column == len(self.text[self.cursor.line]) \
            and self.cursor.line + 1 < len(self.text):
            self.cursor.set(self.cursor.line + 1, 0, self.text)
            self.resetHighlight()
        else:
            self.cursor.set(self.cursor.line, self.cursor.column + 1, self.text)
            self.resetHighlight()

        self._setPreferredColumn()

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

        for i, visualLine in enumerate(displayLines):
            lineY = self._actualY + i * self.fontSize
            
            textSurface = self.font.render(visualLine['text'], True, colour)
            self.win.blit(textSurface, (self._actualX, lineY))

    def drawCursor(self) -> None:
        """ Отрисовка мигающей линии курсора """
        if self.selected and self.showCursor:
            visualLineIndex = self.getCurrentVisualLineIndex()

            if visualLineIndex != -1:
                visualLine = self.cachedVisualLines[visualLineIndex]

                relativeColumn = self.cursor.column - visualLine['startAt']
                text = visualLine['text'][:relativeColumn]

                startX = self._actualX + self.font.size(text)[0]
                endX = startX

                startY = self._actualY + self.fontSize * visualLineIndex
                endY = startY + self.fontSize
            
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
        if self.isEmptyHighlight():
            return

        startLine = min(self.highlightStart.line, self.highlightEnd.line)
        endLine = max(self.highlightStart.line, self.highlightEnd.line)

        startColumn = self.highlightStart.column
        endColumn = self.highlightEnd.column
        
        if self.highlightStart.line > self.highlightEnd.line or \
           (self.highlightStart.line == self.highlightEnd.line and self.highlightStart.column > self.highlightEnd.column):
            startColumn, endColumn = endColumn, startColumn

        for i, visualLine in enumerate(self.cachedVisualLines):
            lineIndex = visualLine['lineIndex']
            
            if startLine <= lineIndex <= endLine:
                lineY = self._actualY + self.fontSize * i
                
                lineStart = visualLine['startAt']
                
                # Вычисляем границы выделения конкретно для этой логической строки
                highlightStart = startColumn if lineIndex == startLine else 0
                highlightEnd = endColumn if lineIndex == endLine else len(self.text[lineIndex])
                
                # Ограничиваем эти границы рамками текущего визуального куска
                localStart = max(0, highlightStart - lineStart)
                localEnd = min(len(visualLine['text']), highlightEnd - lineStart)
                
                # if localStart < localEnd:
                textBefore = visualLine['text'][:localStart]
                textHighlight = visualLine['text'][localStart:localEnd]

                textBeforeWidth = self.font.size(textBefore)[0]
                textWidth = self.font.size(textHighlight)[0]

                if textHighlight == '':
                    textWidth = self.font.size(' ')[0]
                
                pygame.draw.rect(self.win, self.highlightColour,
                                    (self._actualX + textBeforeWidth, lineY, textWidth, self.fontSize))
    
    def addText(self, text: str) -> None:
        text = text.replace('\t', ' ' * self.tabSpaces)
        text = text.replace('\r', '')
        lines = text.split('\n')

        rightPart = self.text[self.cursor.line][self.cursor.column:]

        for i, line in enumerate(lines):
            self.text[self.cursor.line] = self.text[self.cursor.line][:self.cursor.column] + line
            self.cursor.set(self.cursor.line, self.cursor.column + len(line), self.text)

            if i != len(lines) - 1:
                self.text.insert(self.cursor.line + 1, '')
                self.cursor.set(self.cursor.line + 1, 0, self.text)

            self.onTextChanged(*self.onTextChangedParams)

        self.text[self.cursor.line] += rightPart

        self._setPreferredColumn()

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

    def resetHighlight(self) -> None:
        self.highlightStart.set(self.cursor.line, self.cursor.column, self.text)
        self.highlightEnd.set(self.cursor.line, self.cursor.column, self.text)
    
    def getCurrentVisualLineIndex(self) -> int:
        for lineIndex, visualLine in enumerate(self.cachedVisualLines):
            if visualLine['lineIndex'] != self.cursor.line:
                continue
            lineWidth = visualLine['startAt'] + len(visualLine['text'])
            if visualLine['startAt'] <= self.cursor.column <= lineWidth:
                # if self.cursor.column == lineWidth != 0 and lineIndex + 1 < len(self.cachedVisualLines):
                #     return lineIndex + 1
                return lineIndex
        return -1

    def updateCursor(self) -> None:
        now = pygame.time.get_ticks()
        if now - self.cursorTime >= self.CURSOR_INTERVAL:
            self.showCursor = not self.showCursor
            self.cursorTime = now
    
    def isEmptyText(self, text: list[str]) -> bool:
        return len(text) == 1 and text[0] == ''
    
    def isEmptyHighlight(self) -> bool:
        return (self.highlightStart.line == self.highlightEnd.line and 
                self.highlightStart.column == self.highlightEnd.column)
    
    def escape(self) -> None:
        self.selected = False
        self.showCursor = False
        pygame.key.set_repeat(*self.originalRepeat)

    def setText(self, text: str) -> None:
        self.text = ['']
        self.cursor.set(0, 0, self.text)
        self.addText(text)
        self.isChanged = True

    def _setPreferredColumn(self) -> None:
        visualLineIndex = self.getCurrentVisualLineIndex()

        if visualLineIndex != -1:
            visualLine = self.cachedVisualLines[visualLineIndex]
            relativeColumn = self.cursor.column - visualLine['startAt']

            self.cursor.preferredColumn = relativeColumn

    def _setColumnFromMouse(self, mouseX: int, mouseY: int) -> None:
        for i, visualLine in enumerate(self.cachedVisualLines):
            lineY = self._actualY + self.fontSize * i

            if lineY < mouseY < lineY + self.fontSize:
                if visualLine['lineIndex'] != self.cursor.line:
                    self.cursor.set(visualLine['lineIndex'], self.cursor.column, self.text)

                if len(visualLine['text']) == 0:
                    self.cursor.set(self.cursor.line, visualLine['startAt'], self.text)
                    break

                firstLetter = visualLine['text'][0]
                firstLetterWidth = self.font.size(firstLetter)[0]

                if self._x <= mouseX < self._actualX + firstLetterWidth // 2:
                    self.cursor.set(self.cursor.line, visualLine['startAt'], self.text)
                    break
            
                wholeLine = visualLine['text']
                wholeLineWidth = self.font.size(wholeLine)[0]

                if self._actualX + wholeLineWidth <= mouseX:
                    self.cursor.set(self.cursor.line, visualLine['startAt'] + len(visualLine['text']), self.text)
                    break

                count = 0

                while True:

                    count += 1
                    textBefore = visualLine['text'][:count - 1]
                    textCurrent = visualLine['text'][:count]
                    textAfter = visualLine['text'][:count + 1]

                    x1 = self._actualX + (self.font.size(textBefore)[0] + self.font.size(textCurrent)[0]) / 2
                    x2 = self._actualX + (self.font.size(textCurrent)[0] + self.font.size(textAfter)[0]) / 2

                    if x1 <= mouseX <= x2:
                        self.cursor.set(self.cursor.line, visualLine['startAt'] + count, self.text)
                        break

                break

    def getText(self) -> str:
        return '\n'.join(self.text)
    
    def getHighlightedText(self) -> str:
        pass


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
