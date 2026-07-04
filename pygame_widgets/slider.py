import pygame
import math

import pygame_widgets
from pygame_widgets.widget import WidgetBase
from pygame_widgets.mouse import Mouse, MouseState


class Slider(WidgetBase):
    def __init__(self, win, x, y, width, height, **kwargs):
        super().__init__(win, x, y, width, height)

        self.selected = False
        self.valueColour = kwargs.get('valueColour', (0, 35, 255))

        self.min = kwargs.get('min', 0)
        self.max = kwargs.get('max', 99)
        self.step = kwargs.get('step', 1)

        self.colour = kwargs.get('colour', (200, 200, 200))
        self.handleColour = kwargs.get('handleColour', (0, 0, 0))

        self.borderThickness = kwargs.get('borderThickness', 3)
        self.borderColour = kwargs.get('borderColour', (0, 0, 0))

        self.value = self.round(kwargs.get('initial', (self.max + self.min) / 2))
        self.value = max(min(self.value, self.max), self.min)

        self.curved = kwargs.get('curved', True)
        self.handleCurved = kwargs.get('handleCurved', True)

        self.vertical = kwargs.get('vertical', False)

        self.draggableAnywhere = kwargs.get('draggableAnywhere', True)

        if self.curved:
            if self.vertical:
                self.radius = self._width // 2
            else:
                self.radius = self._height // 2
        else:
            self.radius = 0

        if self.vertical:
            self.handleRadius = kwargs.get('handleRadius', int(self._width / 1.3))
        else:
            self.handleRadius = kwargs.get('handleRadius', int(self._height / 1.3))

    def listen(self, events):
        if not self._hidden and not self._disabled:
            mouseState = Mouse.getMouseState()
            x, y = Mouse.getMousePos()

            if self.contains(x, y):
                if mouseState == MouseState.CLICK:
                    self.selected = True

            if mouseState == MouseState.RELEASE:
                self.selected = False

            if self.selected:
                if self.vertical:
                    self.value = self.max - self.round(
                        (y - self._y) / self._height * (self.max - self.min)
                    )
                    self.value = max(min(self.value, self.max), self.min)
                else:
                    self.value = self.round(
                        (x - self._x) / self._width * (self.max - self.min) + self.min
                    )
                    self.value = max(min(self.value, self.max), self.min)

    def draw(self):
        if self._hidden:
            return

        pygame.draw.rect(
            self.win,
            self.colour,
            (self._x, self._y, self._width, self._height),
            border_radius=self.radius,
        )

        valueRange = self.max - self.min
        if valueRange == 0:
            valueRange = 1

        if self.vertical:
            valueHeight = int((self.max - self.value) / valueRange * self._height)
            clipRect = pygame.Rect(
                self._x, self._y + valueHeight, self._width, self._height - valueHeight
            )
            handleCenter = (self._x + self._width // 2, self._y + valueHeight)
        else:
            valueWidth = int((self.value - self.min) / valueRange * self._width)
            clipRect = pygame.Rect(self._x, self._y, max(0, valueWidth), self._height)
            handleCenter = (self._x + valueWidth, self._y + self._height // 2)

        old_clip = self.win.get_clip()
        self.win.set_clip(clipRect)

        pygame.draw.rect(
            self.win,
            self.valueColour,
            (self._x, self._y, self._width, self._height),
            border_radius=self.radius,
        )

        self.win.set_clip(old_clip)

        if self.handleCurved:
            pygame.draw.circle(
                self.win, self.handleColour, handleCenter, self.handleRadius
            )
            pygame.draw.aacircle(
                self.win, self.handleColour, handleCenter, self.handleRadius
            )
        else:
            pygame.draw.rect(
                self.win,
                self.handleColour,
                (
                    handleCenter[0] - self.handleRadius,
                    handleCenter[1] - self.handleRadius,
                    self.handleRadius * 2,
                    self.handleRadius * 2,
                ),
            )

    def contains(self, x, y):
        if self.vertical:
            handleX = self._x + self._width // 2
            handleY = int(
                self._y + (self.max - self.value) / (self.max - self.min) * self._height
            )
        else:
            handleX = int(
                self._x + (self.value - self.min) / (self.max - self.min) * self._width
            )
            handleY = self._y + self._height // 2

        if math.sqrt((handleX - x) ** 2 + (handleY - y) ** 2) <= self.handleRadius:
            return True

        if self.draggableAnywhere:
            return pygame.rect.Rect(
                self._x, self._y, self._width, self._height
            ).collidepoint(x, y)

        return False

    def round(self, value):
        return self.step * round(value / self.step)

    def getValue(self):
        return self.value

    def setValue(self, value):
        self.value = value


if __name__ == '__main__':
    from pygame_widgets.textbox import TextBox

    pygame.init()
    win = pygame.display.set_mode((1000, 600))

    slider = Slider(win, 100, 100, 800, 5, min=100, max=200, step=1, handleRadius=15)
    output = TextBox(win, 475, 200, 100, 50, fontSize=30)

    v_slider = Slider(
        win, 900, 200, 40, 300, min=100, max=200, step=1, vertical=True
    )
    v_output = TextBox(win, 750, 320, 100, 50, fontSize=30)

    output.disable()
    v_output.disable()

    run = True
    while run:
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                pygame.quit()
                run = False
                quit()

        win.fill((255, 255, 255))

        output.setText(slider.getValue())
        v_output.setText(v_slider.getValue())

        pygame_widgets.update(events)
        pygame.display.update()
