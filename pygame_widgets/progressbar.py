from collections.abc import Callable

import pygame

import pygame_widgets
from pygame_widgets.widget import WidgetBase


class ProgressBar(WidgetBase):
    def __init__(
        self, win, x, y, width, height, progress: Callable[[], float], **kwargs
    ):
        super().__init__(win, x, y, width, height)
        self.progress = progress

        self.curved = kwargs.get("curved", False)

        self.completed_color = kwargs.get("completed_color", (0, 200, 0))
        self.incompleted_color = kwargs.get("incompleted_color", (100, 100, 100))

        self.percent = self.progress()

        self.radius = self._height / 2 if self.curved else 0

        self.disable()

    def listen(self, events):
        pass

    def draw(self):
        """Display to surface"""
        self.percent = min(max(self.progress(), 0), 1)

        if not self._hidden:
            if self.curved:
                if self.percent == 0:
                    pygame.draw.circle(
                        self.win,
                        self.incompleted_color,
                        (self._x, self._y + self._height // 2),
                        self.radius,
                    )
                    pygame.draw.circle(
                        self.win,
                        self.incompleted_color,
                        (self._x + self._width, self._y + self._height // 2),
                        self.radius,
                    )
                elif self.percent == 1:
                    pygame.draw.circle(
                        self.win,
                        self.completed_color,
                        (self._x, self._y + self._height // 2),
                        self.radius,
                    )
                    pygame.draw.circle(
                        self.win,
                        self.completed_color,
                        (self._x + self._width, self._y + self._height // 2),
                        self.radius,
                    )
                else:
                    pygame.draw.circle(
                        self.win,
                        self.completed_color,
                        (self._x, self._y + self._height // 2),
                        self.radius,
                    )
                    pygame.draw.circle(
                        self.win,
                        self.incompleted_color,
                        (self._x + self._width, self._y + self._height // 2),
                        self.radius,
                    )

            pygame.draw.rect(
                self.win,
                self.completed_color,
                (self._x, self._y, int(self._width * self.percent), self._height),
            )
            pygame.draw.rect(
                self.win,
                self.incompleted_color,
                (
                    self._x + int(self._width * self.percent),
                    self._y,
                    int(self._width * (1 - self.percent)),
                    self._height,
                ),
            )


if __name__ == "__main__":
    import sys
    import time

    start_time = time.time()

    pygame.init()
    win = pygame.display.set_mode((1000, 600))

    progress_bar = ProgressBar(
        win, 100, 100, 500, 40, lambda: 1 - (time.time() - start_time) / 10, curved=True
    )

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
