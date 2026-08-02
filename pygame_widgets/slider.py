import math
from dataclasses import dataclass, replace

import pygame

import pygame_widgets
from pygame_widgets.mouse import Mouse, MouseState
from pygame_widgets.widget import WidgetBase


@dataclass
class SliderStyle:
    color: tuple[int, int, int] = (200, 200, 200)
    value_color: tuple[int, int, int] = (0, 35, 255)
    handle_color: tuple[int, int, int] = (0, 0, 0)
    border_thickness: int = 3
    border_color: tuple[int, int, int] = (0, 0, 0)

    min: float = 0.0
    max: float = 99.0
    step: float = 1.0

    curved: bool = True
    handle_curved: bool = True
    vertical: bool = False
    draggable_anywhere: bool = True

    radius: int | None = None
    handle_radius: int | None = None
    handle_border_radius: int | None = None


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

        style_kwargs = {
            k: v for k, v in kwargs.items() if k in SliderStyle.__dataclass_fields__
        }
        if style is None:
            self.style = SliderStyle(**style_kwargs)
        else:
            self.style = replace(style, **style_kwargs)

        initial_value = kwargs.get("initial", (self.style.max + self.style.min) / 2)
        self.value = self.round(initial_value)
        self.value = max(min(self.value, self.style.max), self.style.min)

        self.radius = 0
        self.handle_radius = 0
        self.reconfigure_layout()

    def reconfigure_layout(self) -> None:
        if self.style.radius is not None:
            self.radius = self.style.radius

        elif self.style.curved:
            if self.style.vertical:
                self.radius = self._width // 2
            else:
                self.radius = self._height // 2
        else:
            self.radius = 0

        if self.style.handle_radius is not None:
            self.handle_radius = self.style.handle_radius
        else:
            if self.style.vertical:
                self.handle_radius = int(self._width / 1.3)
            else:
                self.handle_radius = int(self._height / 1.3)

        if self.style.handle_border_radius is not None:
            self.handle_border_radius = self.style.handle_border_radius
        else:
            self.handle_border_radius = self.radius

    def listen(self, events: list[pygame.event.Event]) -> None:
        if not self._hidden and not self._disabled:
            mouse_state = Mouse.get_mouse_state()
            x, y = Mouse.get_mouse_pos()

            if self.contains(x, y) and mouse_state == MouseState.CLICK:
                self.selected = True

            if mouse_state == MouseState.RELEASE:
                self.selected = False

            if self.selected:
                if self.style.vertical:
                    self.value = self.style.max - self.round(
                        (y - self._y) / self._height * (self.style.max - self.style.min)
                    )
                    self.value = max(min(self.value, self.style.max), self.style.min)
                else:
                    self.value = self.round(
                        (x - self._x) / self._width * (self.style.max - self.style.min)
                        + self.style.min
                    )
                    self.value = max(min(self.value, self.style.max), self.style.min)

    def draw(self) -> None:
        if self._hidden:
            return

        pygame.draw.rect(
            self.win,
            self.style.color,
            (self._x, self._y, self._width, self._height),
            border_radius=self.radius,
        )

        value_range = self.style.max - self.style.min
        if value_range == 0:
            value_range = 1

        if self.style.vertical:
            value_height = (self.style.max - self.value) / value_range * self._height
            clip_rect = pygame.Rect(
                self._x,
                self._y + value_height,
                self._width,
                self._height - value_height,
            )
            handle_center = (self._x + self._width / 2, self._y + value_height)
        else:
            value_width = (self.value - self.style.min) / value_range * self._width
            clip_rect = pygame.Rect(self._x, self._y, max(0, value_width), self._height)
            handle_center = (self._x + value_width, self._y + self._height / 2)

        old_clip = self.win.get_clip()
        self.win.set_clip(clip_rect)

        pygame.draw.rect(
            self.win,
            self.style.value_color,
            (self._x, self._y, self._width, self._height),
            border_radius=self.radius,
        )

        self.win.set_clip(old_clip)

        if self.style.handle_curved:
            pygame.draw.aacircle(
                self.win, self.style.handle_color, handle_center, self.handle_radius
            )
        else:
            pygame.draw.rect(
                self.win,
                self.style.handle_color,
                (
                    handle_center[0] - self.handle_radius,
                    handle_center[1] - self.handle_radius,
                    self.handle_radius * 2,
                    self.handle_radius * 2,
                ),
                border_radius=self.handle_border_radius,
            )

    def contains(self, x: int, y: int) -> bool:
        if self.style.vertical:
            handle_x = self._x + self._width // 2
            handle_y = int(
                self._y
                + (self.style.max - self.value)
                / (self.style.max - self.style.min)
                * self._height
            )
        else:
            handle_x = int(
                self._x
                + (self.value - self.style.min)
                / (self.style.max - self.style.min)
                * self._width
            )
            handle_y = self._y + self._height // 2

        if math.sqrt((handle_x - x) ** 2 + (handle_y - y) ** 2) <= self.handle_radius:
            return True

        if self.style.draggable_anywhere:
            return pygame.rect.Rect(
                self._x, self._y, self._width, self._height
            ).collidepoint(x, y)

        return False

    def round(self, value: float) -> float:
        return self.style.step * round(value / self.style.step)

    def get_value(self) -> float:
        return self.value

    def set_value(self, value: float) -> None:
        self.value = value


if __name__ == "__main__":
    import sys

    from pygame_widgets.textbox_legacy import TextBox

    pygame.init()
    win = pygame.display.set_mode((1000, 600))

    # dark_theme = SliderStyle(
    #     color=(240, 240, 240),
    #     value_color=(30, 30, 30),
    #     handle_color=(30, 30, 30),
    #     border_thickness=3,
    #     border_color=(0, 0, 0),
    #     min=100,
    #     max=200,
    #     step=1,
    #     curved=True,
    #     handle_curved=True,
    #     vertical=False,
    #     draggable_anywhere=True,
    # )

    slider = Slider(win, 100, 100, 800, 5, min=100, max=200, step=1, handle_radius=15)
    # slider = Slider(win, 100, 100, 800, 5, style=dark_theme, handle_radius=15)
    output = TextBox(win, 475, 200, 100, 50, fontSize=30)

    vertical_slider = Slider(
        win, 900, 200, 40, 300, min=100, max=200, step=1, vertical=True
    )
    # vertical_slider = Slider(win, 900, 200, 40, 300, style=dark_theme, vertical=True)
    vertical_slider_output = TextBox(win, 750, 320, 100, 50, fontSize=30)

    output.disable()
    vertical_slider_output.disable()

    run = True
    while run:
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                pygame.quit()
                run = False
                sys.exit()

        win.fill((255, 255, 255))

        output.set_text(slider.get_value())
        vertical_slider_output.set_text(vertical_slider.get_value())

        pygame_widgets.update(events)
        pygame.display.update()
