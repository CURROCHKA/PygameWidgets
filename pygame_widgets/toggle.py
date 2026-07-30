import pygame

import pygame_widgets
from pygame_widgets.mouse import Mouse, MouseState
from pygame_widgets.widget import WidgetBase


class Toggle(WidgetBase):
    def __init__(self, win, x, y, width, height, **kwargs):
        super().__init__(win, x, y, width, height)

        self.value = kwargs.get("startOn", False)
        self.on_color = kwargs.get("on_color", (141, 185, 244))
        self.off_color = kwargs.get("off_color", (150, 150, 150))
        self.handle_on_color = kwargs.get("handle_on_color", (26, 115, 232))
        self.handle_off_color = kwargs.get("handle_off_color", (200, 200, 200))
        self.on_click = kwargs.get("on_click", lambda *args: None)
        self.on_click_params = kwargs.get("on_click_params", ())

        self.handle_radius = kwargs.get("handle_radius", int(self._height / 1.3))
        self.radius = self._height // 2

        self.color = self.on_color if self.value else self.off_color
        self.handle_color = (
            self.handle_on_color if self.value else self.handle_off_color
        )

    def toggle(self):
        self.value = not self.value
        self.color = self.on_color if self.value else self.off_color
        self.handle_color = (
            self.handle_on_color if self.value else self.handle_off_color
        )

    def listen(self, events):
        if not self._hidden and not self._disabled:
            mouse_state = Mouse.get_mouse_state()
            x, y = Mouse.get_mouse_pos()

            if self.contains(x, y) and mouse_state == MouseState.CLICK:
                self.toggle()
                self.on_click(*self.on_click_params)

    def draw(self):
        if not self._hidden:
            pygame.draw.rect(
                self.win,
                self.color,
                (self._x, self._y, self._width, self._height),
                border_radius=self.radius,
            )

            circle_center_coord = (
                self._x
                + (
                    self._width - self.handle_radius + self.radius
                    if self.value
                    else self.handle_radius - self.radius
                ),
                self._y + self._height // 2,
            )

            pygame.draw.aacircle(
                self.win, self.handle_color, circle_center_coord, self.handle_radius
            )

    def get_value(self) -> bool:
        return self.value


if __name__ == "__main__":
    import sys

    pygame.init()
    win = pygame.display.set_mode((1000, 600))

    toggle = Toggle(win, 100, 100, 100, 40)
    toggle.on_click = lambda: print(toggle.get_value())

    run = True
    while run:
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                pygame.quit()
                run = False
                sys.exit()

        win.fill((255, 255, 255))

        pygame_widgets.update(events)
        pygame.display.update()
