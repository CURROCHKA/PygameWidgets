import pygame
import pygame_widgets
from pygame_widgets.widget import WidgetBase
from pygame_widgets.mouse import Mouse, MouseState


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

        self.selected = False
        self.showCursor = False
        self.cursorTime = 0
        self.cursorPosition = 0
        self.oldRelativeCursorPosition = 0
        self.cursorCoords = None
        self.insertOn = False # TODO: проверять статус клавишы

        self.selectedLine = 0
        
        self.isChanged = False
        self.text = ['']
        self.cachedVisualLines = []

        # Border
        self.borderThickness = kwargs.get('borderThickness', 3)
        self.borderColour = kwargs.get('borderColour', (0, 0, 0))
        self.radius = kwargs.get('radius', 0)

        # Colour
        self.colour = kwargs.get('colour', (220, 220, 220))
        self.cursorColour = kwargs.get('cursorColour', (0, 0, 0))

        # Text
        self.isLabel = kwargs.get(
            'isLabel', False
        )  # If you want to highlight, copy and so on without texting
        self.placeholderText = kwargs.get('placeholderText', '')
        self.placeholderTextColour = kwargs.get('placeholderTextColour', (10, 10, 10))
        self.textColour = kwargs.get('textColour', (0, 0, 0))
        self.highlightColour = kwargs.get('highlightColour', (166, 210, 255))
        self.fontSize = kwargs.get('fontSize', 20)
        self.font = kwargs.get('font', pygame.font.SysFont('calibri', self.fontSize))
        self.tabSpaces = kwargs.get('tabSpaces', 4)

        self.textOffsetTop = self.fontSize // 3
        self.textOffsetLeft = self.fontSize // 3
        self.textOffsetRight = self.fontSize // 2

        # Functions
        self.onSubmit = kwargs.get('onSubmit', lambda *args: None)
        self.onSubmitParams = kwargs.get('onSubmitParams', ())
        self.onTextChanged = kwargs.get('onTextChanged', lambda *args: None)
        self.onTextChangedParams = kwargs.get('onTextChangedParams', ())

        self.cursorWidth = kwargs.get('cursorWidth', 2)

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
                        if self.cursorPosition > 0:
                            line = self.text[self.selectedLine]
                            self.text[self.selectedLine] = line[:self.cursorPosition - 1] + line[self.cursorPosition:]
                            self.cursorPosition -= 1
                            self._setOldRelativeCursorPosition()
                            self.onTextChanged(*self.onTextChangedParams)

                        elif self.selectedLine > 0:
                            self.cursorPosition = len(self.text[self.selectedLine - 1])
                            self.text[self.selectedLine - 1] += self.text[self.selectedLine]
                            self.text.pop(self.selectedLine)
                            self.selectedLine -= 1
                            self._setOldRelativeCursorPosition()
                            self.onTextChanged(*self.onTextChangedParams)

                    elif event.key == pygame.K_DELETE:
                        line = self.text[self.selectedLine]
                        if self.cursorPosition < len(line):
                            self.text[self.selectedLine] = line[:self.cursorPosition] + line[self.cursorPosition + 1:]
                            self.onTextChanged(*self.onTextChangedParams)
                        
                        elif self.selectedLine < len(self.text) - 1:
                            self.text[self.selectedLine] += self.text[self.selectedLine + 1]
                            self.text.pop(self.selectedLine + 1)
                            self.onTextChanged(*self.onTextChangedParams)

                    elif event.key == pygame.K_RETURN:
                        if event.mod & pygame.KMOD_SHIFT or event.mod & pygame.KMOD_CTRL:
                            self.addText('\n')
                        else:
                            self.onSubmit(*self.onSubmitParams)

                    elif event.key in [pygame.K_UP, pygame.K_KP_8 if not event.mod & pygame.KMOD_NUM else -1]:
                        visualLineIndex = self.getCurrentVisualLineIndex()

                        if visualLineIndex != -1 and visualLineIndex - 1 >= 0:
                            visualLine = self.cachedVisualLines[visualLineIndex]
                            relativePosition = self.cursorPosition - visualLine['startAt']

                            previousLine = self.cachedVisualLines[visualLineIndex - 1]

                            if visualLine['lineIndex'] != previousLine['lineIndex']:
                                self.selectedLine -= 1

                            self.cursorPosition = max(previousLine['startAt'] + relativePosition,
                                                      previousLine['startAt'] + self.oldRelativeCursorPosition)
                            self.cursorPosition = min(self.cursorPosition,
                                                      previousLine['startAt'] + len(previousLine['text']))
                    
                    elif event.key in [pygame.K_DOWN, pygame.K_KP_2 if not event.mod & pygame.KMOD_NUM else -1]:
                        visualLineIndex = self.getCurrentVisualLineIndex()

                        if visualLineIndex != -1 and visualLineIndex + 1 < len(self.cachedVisualLines):
                            visualLine = self.cachedVisualLines[visualLineIndex]
                            relativePosition = self.cursorPosition - visualLine['startAt']

                            nextLine = self.cachedVisualLines[visualLineIndex + 1]

                            if visualLine['lineIndex'] != nextLine['lineIndex']:
                                self.selectedLine += 1

                            self.cursorPosition = max(nextLine['startAt'] + relativePosition,
                                                      nextLine['startAt'] + self.oldRelativeCursorPosition)
                            self.cursorPosition = min(self.cursorPosition,
                                                      nextLine['startAt'] + len(nextLine['text']))
                            
                    elif event.key in [pygame.K_RIGHT, pygame.K_KP_6 if not event.mod & pygame.KMOD_NUM else -1]:
                        if event.mod & pygame.KMOD_CTRL:
                            if self.cursorPosition < len(self.text[self.selectedLine]):

                                visualLineIndex = self.getCurrentVisualLineIndex()

                                if visualLineIndex != -1:
                                    visualLine = self.cachedVisualLines[visualLineIndex]
                                    relativePosition = self.cursorPosition - visualLine['startAt']

                                    while relativePosition < len(visualLine['text']) and visualLine['text'][relativePosition] in ' ();:,./!?':
                                        relativePosition += 1

                                    while relativePosition < len(visualLine['text']) and visualLine['text'][relativePosition] not in ' ();:,./!?':
                                        relativePosition += 1

                                    self.setCursorPosition(self.selectedLine, visualLine['startAt'] + relativePosition - 1)
                            
                        currentLineLength = len(self.text[self.selectedLine])
                        if self.cursorPosition == currentLineLength and self.selectedLine + 1 < len(self.text):
                            self.selectedLine += 1
                            self.cursorPosition = 0
                        else:
                            self.cursorPosition = min(self.cursorPosition + 1, len(self.text[self.selectedLine]))

                        self._setOldRelativeCursorPosition()

                    elif event.key in [pygame.K_LEFT, pygame.K_KP_4 if not event.mod & pygame.KMOD_NUM else -1]:
                        if event.mod & pygame.KMOD_CTRL:
                            if self.cursorPosition > 0:

                                visualLineIndex = self.getCurrentVisualLineIndex()

                                if visualLineIndex != -1:
                                    visualLine = self.cachedVisualLines[visualLineIndex]
                                    relativePosition = self.cursorPosition - visualLine['startAt'] - 1

                                    while relativePosition >= 0 and visualLine['text'][relativePosition] in ' ();:,./!?':
                                        relativePosition -= 1

                                    while relativePosition >= 0 and visualLine['text'][relativePosition] not in ' ();:,./!?':
                                        relativePosition -= 1

                                    self.setCursorPosition(self.selectedLine, visualLine['startAt'] + relativePosition + 2)

                        if self.cursorPosition == 0 and self.selectedLine - 1 >= 0:
                            self.selectedLine -= 1
                            self.cursorPosition = len(self.text[self.selectedLine])
                        else:
                            self.cursorPosition = max(self.cursorPosition - 1, 0)

                        self._setOldRelativeCursorPosition()

                    elif event.key in [pygame.K_HOME, pygame.K_KP_7 if not event.mod & pygame.KMOD_NUM else -1]:
                        visualLineIndex = self.getCurrentVisualLineIndex()

                        if visualLineIndex != -1:
                            visualLine = self.cachedVisualLines[visualLineIndex]
                            self.cursorPosition = visualLine['startAt']
                            self._setOldRelativeCursorPosition()

                    elif event.key in [pygame.K_END, pygame.K_KP_1 if not event.mod & pygame.KMOD_NUM else -1]:
                        visualLineIndex = self.getCurrentVisualLineIndex()

                        if visualLineIndex != -1:
                            visualLine = self.cachedVisualLines[visualLineIndex]
                            self.cursorPosition = visualLine['startAt'] + len(visualLine['text'])
                            self._setOldRelativeCursorPosition()

                    elif event.key == pygame.K_a and event.mod & pygame.KMOD_CTRL:
                        pass

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

    def draw(self) -> None:
        """ Display to surface """
        if self._hidden:
            return
        if self.selected:
            self.updateCursor()
        self.drawBorder()
        self.drawBackground()
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

        # Сбрасываем координаты курсора перед расчетом
        self.cursorCoords = None

        for i, visualLine in enumerate(displayLines):
            lineY = yBase + i * self.fontSize
            
            # 1. Рендерим саму строку
            textSurface = self.font.render(visualLine['text'], True, colour)
            self.win.blit(textSurface, (xBase, lineY))

            # 2. Логика поиска позиции курсора
            # Проверяем, находится ли курсор в этой логической строке
            if visualLine['lineIndex'] == self.selectedLine:
                relativePosition = self.cursorPosition - visualLine['startAt']
                
                # Попадает ли индекс курсора в текущую визуальную подстроку?
                if 0 <= relativePosition <= len(visualLine['text']):
                    # Идеально точный расчет смещения через font.size
                    textBeforeCursor = visualLine['text'][:relativePosition]
                    cursorOffset = self.font.size(textBeforeCursor)[0]
                    
                    # Сохраняем координаты для метода drawCursor
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

    def addText(self, text: str) -> None:
        text = text.replace('\t', ' ' * self.tabSpaces)
        text = text.replace('\r', '')
        lines = text.split('\n')

        rightPart = self.text[self.selectedLine][self.cursorPosition:]

        for i, line in enumerate(lines):
            currentLine = self.text[self.selectedLine]
            self.text[self.selectedLine] = currentLine[:self.cursorPosition] + line
            self.cursorPosition += len(line)

            if i != len(lines) - 1:
                self.selectedLine += 1
                self.cursorPosition = 0
                self.text.insert(self.selectedLine, '')

            self.onTextChanged(*self.onTextChangedParams)

        self.text[self.selectedLine] += rightPart

        self.oldRelativeCursorPosition = self.cursorPosition

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
    
    def getCurrentVisualLineIndex(self) -> int:
        if self.cursorCoords:
            return (self.cursorCoords[1] - self._y - self.textOffsetTop) // self.fontSize
        return -1

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
        pygame.key.set_repeat(0, 0)

    def setText(self, text: str) -> None:
        self.text = ['']
        self.setCursorPosition(0, 0)
        self.addText(text)
        self.isChanged = True

    def setCursorPosition(self, lineIndex: int, inLineIndex: int) -> None:
        if 0 <= lineIndex <= len(self.text) - 1 \
            and 0 <= inLineIndex <= len(self.text[lineIndex]):

            self.selectedLine = lineIndex
            self.cursorPosition = inLineIndex
            self.oldRelativeCursorPosition = self._setOldRelativeCursorPosition()

    def _setOldRelativeCursorPosition(self) -> None:
        visualLineIndex = self.getCurrentVisualLineIndex()

        if visualLineIndex != -1:
            visualLine = self.cachedVisualLines[visualLineIndex]
            relativePosition = self.cursorPosition - visualLine['startAt']

            self.oldRelativeCursorPosition = relativePosition

    def _setCursorPositionFromMouse(self, mouseX: int, mouseY: int):
        xBase = self._x + self.textOffsetLeft + self.borderThickness
        yBase = self._y + self.textOffsetTop + self.borderThickness
        
        for i, visualLine in enumerate(self.cachedVisualLines):
            lineY = yBase + self.fontSize * i

            if lineY < mouseY < lineY + self.fontSize:
                if visualLine['lineIndex'] != self.selectedLine:
                    self.selectedLine = visualLine['lineIndex']

                firstLetter = visualLine['text'][0]
                firstLetterWidth = self.font.size(firstLetter)[0]

                if self._x <= mouseX < xBase + firstLetterWidth // 2:
                    self.cursorPosition = visualLine['startAt']
                    break
            
                wholeLine = visualLine['text']
                wholeLineWidth = self.font.size(wholeLine)[0]

                if xBase + wholeLineWidth <= mouseX:
                    self.cursorPosition = visualLine['startAt'] + len(visualLine['text'])
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
                        self.cursorPosition = visualLine['startAt'] + count
                        break

                # self.cursorPosition = len(visualLine['text'][:count])
                break

    def getText(self) -> str:
        return '\n'.join(self.text)


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
