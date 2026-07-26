from dataclasses import dataclass, replace

import pygame
import math

import pygame_widgets
from pygame_widgets.widget import WidgetBase
from pygame_widgets.mouse import Mouse, MouseState


@dataclass
class SliderStyle:
    colour: tuple[int, int, int] = (200, 200, 200)
    valueColour: tuple[int, int, int] = (0, 35, 255)
    handleColour: tuple[int, int, int] = (0, 0, 0)
    borderThickness: int = 3
    borderColour: tuple[int, int, int] = (0, 0, 0)

    min: float = 0.0
    max: float = 99.0
    step: float = 1.0

    curved: bool = True
    handleCurved: bool = True
    vertical: bool = False
    draggableAnywhere: bool = True

    radius: int | None = None
    handleRadius: int | None = None
    handleBorderRadius: int | None = None


class Slider(WidgetBase):
    def __init__(
        self,
        win: pygame.Surface,
        x: int,
        y: int,
        width: int,
        height: int,
        style: SliderStyle = None,
        **kwargs,
    ) -> None:
        super().__init__(win, x, y, width, height)

        self.selected = False

        styleKwargs = {
            k: v for k, v in kwargs.items() if k in SliderStyle.__dataclass_fields__
        }
        if style is None:
            self.style = SliderStyle(**styleKwargs)
        else:
            self.style = replace(style, **styleKwargs)

        initialValue = kwargs.get('initial', (self.style.max + self.style.min) / 2)
        self.value = self.round(initialValue)
        self.value = max(min(self.value, self.style.max), self.style.min)

        self.radius = 0
        self.handleRadius = 0
        self.reconfigureLayout()

    def reconfigureLayout(self) -> None:
        if self.style.radius is not None:
            self.radius = self.style.radius

        elif self.style.curved:
            if self.style.vertical:
                self.radius = self._width // 2
            else:
                self.radius = self._height // 2
        else:
            self.radius = 0

        if self.style.handleRadius is not None:
            self.handleRadius = self.style.handleRadius
        else:
            if self.style.vertical:
                self.handleRadius = int(self._width / 1.3)
            else:
                self.handleRadius = int(self._height / 1.3)

        if self.style.handleBorderRadius is not None:
            self.handleBorderRadius = self.style.handleBorderRadius
        else:
            self.handleBorderRadius = self.radius

    def listen(self, events: list[pygame.event.Event]) -> None:
        if not self._hidden and not self._disabled:
            mouseState = Mouse.getMouseState()
            x, y = Mouse.getMousePos()

            if self.contains(x, y):
                if mouseState == MouseState.CLICK:
                    self.selected = True

            if mouseState == MouseState.RELEASE:
                self.selected = False

            if self.selected:
                if self.style.vertical:
                    self.value = self.style.max - self.round(
                        (y - self._y) / self._height * (self.style.max - self.style.min)
                    )
                    self.value = max(min(self.value, self.style.max), self.style.min)
                else:
                    self.value = self.round(
                        (x - self._x) / self._width * (self.style.max - self.style.min) + self.style.min
                    )
                    self.value = max(min(self.value, self.style.max), self.style.min)

    def draw(self) -> None:
        if self._hidden:
            return

        pygame.draw.rect(
            self.win,
            self.style.colour,
            (self._x, self._y, self._width, self._height),
            border_radius=self.radius,
        )

        valueRange = self.style.max - self.style.min
        if valueRange == 0:
            valueRange = 1

        if self.style.vertical:
            valueHeight = (self.style.max - self.value) / valueRange * self._height
            clipRect = pygame.Rect(
                self._x, self._y + valueHeight, self._width, self._height - valueHeight
            )
            handleCenter = (self._x + self._width / 2, self._y + valueHeight)
        else:
            valueWidth = (self.value - self.style.min) / valueRange * self._width
            clipRect = pygame.Rect(self._x, self._y, max(0, valueWidth), self._height)
            handleCenter = (self._x + valueWidth, self._y + self._height / 2)

        old_clip = self.win.get_clip()
        self.win.set_clip(clipRect)

        pygame.draw.rect(
            self.win,
            self.style.valueColour,
            (self._x, self._y, self._width, self._height),
            border_radius=self.radius,
        )

        self.win.set_clip(old_clip)

        if self.style.handleCurved:
            pygame.draw.aacircle(
                self.win, self.style.handleColour, handleCenter, self.handleRadius
            )
        else:
            pygame.draw.rect(
                self.win,
                self.style.handleColour,
                (
                    handleCenter[0] - self.handleRadius,
                    handleCenter[1] - self.handleRadius,
                    self.handleRadius * 2,
                    self.handleRadius * 2,
                ),
                border_radius=self.handleBorderRadius
            )

    def contains(self, x: int, y: int) -> bool:
        if self.style.vertical:
            handleX = self._x + self._width // 2
            handleY = int(
                self._y + (self.style.max - self.value) / (self.style.max - self.style.min) * self._height
            )
        else:
            handleX = int(
                self._x + (self.value - self.style.min) / (self.style.max - self.style.min) * self._width
            )
            handleY = self._y + self._height // 2

        if math.sqrt((handleX - x) ** 2 + (handleY - y) ** 2) <= self.handleRadius:
            return True

        if self.style.draggableAnywhere:
            return pygame.rect.Rect(
                self._x, self._y, self._width, self._height
            ).collidepoint(x, y)

        return False

    def round(self, value: float) -> float:
        return self.style.step * round(value / self.style.step)

    def getValue(self) -> float:
        return self.value

    def setValue(self, value: float) -> None:
        self.value = value


if __name__ == '__main__':
    from pygame_widgets.textbox import TextBox

    pygame.init()
    win = pygame.display.set_mode((1000, 600))

    # modernDarkTheme = SliderStyle(
    #     colour=(240, 240, 240),
    #     valueColour=(30, 30, 30),
    #     handleColour=(30, 30, 30),
    #     borderThickness=3,
    #     borderColour=(0, 0, 0),
    #     min=100,
    #     max=200,
    #     step=1,
    #     curved=True,
    #     handleCurved=True,
    #     vertical=False,
    #     draggableAnywhere=True,
    # )

    slider = Slider(win, 100, 100, 800, 5, min=100, max=200, step=1, handleRadius=15)
    # slider = Slider(win, 100, 100, 800, 5, style=modernDarkTheme, handleRadius=15)
    output = TextBox(win, 475, 200, 100, 50, fontSize=30)

    v_slider = Slider(win, 900, 200, 40, 300, min=100, max=200, step=1, vertical=True)
    # v_slider = Slider(win, 900, 200, 40, 300, style=modernDarkTheme, vertical=True)
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
