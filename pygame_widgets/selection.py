import math

import pygame

import pygame_widgets
from pygame_widgets.mouse import Mouse, MouseState
from pygame_widgets.widget import WidgetBase


class Checkbox(WidgetBase):
    def __init__(self, win, x, y, width, height, items, **kwargs):
        """A list of buttons that allows multiple selections

        :param win: Surface on which to draw
        :type win: pygame.Surface
        :param x: X-coordinate of top left
        :type x: int
        :param y: Y-coordinate of top left
        :type y: int
        :param width: Width of list
        :type width: int
        :param height: Height of list
        :type height: int
        :param items: Names of list items
        :type items: tuple of str
        :param kwargs: Optional parameters
        """
        super().__init__(win, x, y, width, height)

        self.items = items
        self.rows = len(items)
        self.row_height = self._height // self.rows
        self.selected = [False for _ in range(self.rows)]

        # Border
        self.border_thickness = kwargs.get("border_thickness", 3)
        self.border_color = kwargs.get("border_color", (0, 0, 0))
        self.radius = kwargs.get("radius", 0)

        # Checkbox
        self.box_size = int(kwargs.get("box_size", self._height / self.rows // 3))
        self.box_thickness = kwargs.get("box_thickness", 3)
        self.box_color = kwargs.get("box_color", (0, 0, 0))
        # TODO: selected image (tick) / color

        # Color
        self.color = kwargs.get("color", (255, 255, 255))

        # Alternating colors: overrides color
        self.color1 = kwargs.get("color1", self.color)
        self.color2 = kwargs.get("color2", self.color)

        # Text
        self.text_color = kwargs.get("text_color", (0, 0, 0))
        self.font_size = kwargs.get("font_size", 20)
        self.font = kwargs.get("font", pygame.font.SysFont("calibri", self.font_size))
        self.texts = [
            self.font.render(self.items[row], True, self.text_color)
            for row in range(self.rows)
        ]
        self.text_rects = self.create_text_rects()

        self.clicked = False

        self.boxes = self.create_box_locations()

    def create_text_rects(self):
        text_rects = []
        for row in range(self.rows):
            text_rects.append(
                self.texts[row].get_rect(
                    center=(
                        self._x
                        + self.box_size * 2
                        + (self._width - self.box_size * 2) // 2,
                        self._y + self.row_height * row + self.row_height // 2,
                    )
                )
            )

        return text_rects

    def create_box_locations(self):
        boxes = []
        for row in range(self.rows):
            boxes.append(
                pygame.Rect(
                    self._x + self.box_size,
                    self._y + self.row_height * row + self.box_size,
                    self.box_size,
                    self.box_size,
                )
            )
        return boxes

    def listen(self, events):
        """Wait for inputs

        :param events: Use pygame.event.get()
        :type events: list of pygame.event.Event
        """
        if not self._hidden and not self._disabled:
            mouse_state = Mouse.get_mouse_state()
            x, y = Mouse.get_mouse_pos()

            if self.contains(x, y) and mouse_state == MouseState.CLICK:
                for row in range(self.rows):
                    if self.boxes[row].collidepoint(x, y):
                        self.selected[row] = not self.selected[row]

    def draw(self):
        """Display to surface"""
        if not self._hidden:
            for row in range(self.rows):
                color = self.color1 if not row % 2 else self.color2

                if row == 0:
                    pygame.draw.rect(
                        self.win,
                        color,
                        (
                            self._x,
                            self._y + self.row_height * row,
                            self._width,
                            self.row_height,
                        ),
                        border_top_left_radius=self.radius,
                        border_top_right_radius=self.radius,
                    )

                elif row == self.rows - 1:
                    pygame.draw.rect(
                        self.win,
                        color,
                        (
                            self._x,
                            self._y + self.row_height * row,
                            self._width,
                            self.row_height,
                        ),
                        border_bottom_left_radius=self.radius,
                        border_bottom_right_radius=self.radius,
                    )

                else:
                    pygame.draw.rect(
                        self.win,
                        color,
                        (
                            self._x,
                            self._y + self.row_height * row,
                            self._width,
                            self.row_height,
                        ),
                    )

                width = 0 if self.selected[row] else self.box_thickness
                pygame.draw.rect(self.win, self.box_color, self.boxes[row], width)

                self.win.blit(self.texts[row], self.text_rects[row])

    def get_selected(self):
        return [self.items[row] for row in range(self.rows) if self.selected[row]]


class Radio(WidgetBase):
    def __init__(self, win, x, y, width, height, items, **kwargs):
        """A list of buttons that allows a single selections

        :param win: Surface on which to draw
        :type win: pygame.Surface
        :param x: X-coordinate of top left
        :type x: int
        :param y: Y-coordinate of top left
        :type y: int
        :param width: Width of list
        :type width: int
        :param height: Height of list
        :type height: int
        :param items: Names of list items
        :type items: tuple of str
        :param kwargs: Optional parameters
        """
        super().__init__(win, x, y, width, height)

        self.items = items
        self.rows = len(items)
        self.row_height = self._height // self.rows
        self.selected = kwargs.get("default", 0)

        # Border
        self.border_thickness = kwargs.get("border_thickness", 3)
        self.border_color = kwargs.get("border_color", (0, 0, 0))
        self.radius = kwargs.get("radius", 0)

        # Radio
        self.circle_radius = int(
            kwargs.get("circle_radius", self._height / self.rows // 6)
        )
        self.circle_thickness = kwargs.get("circle_thickness", 3)
        self.circle_color = kwargs.get("circle_color", (0, 0, 0))

        # Color
        self.color = kwargs.get("color", (255, 255, 255))

        # Alternating colors: overrides color
        self.color1 = kwargs.get("color1", self.color)
        self.color2 = kwargs.get("color2", self.color)

        # Text
        self.text_color = kwargs.get("text_color", (0, 0, 0))
        self.font_size = kwargs.get("font_size", 20)
        self.font = kwargs.get(
            "font", pygame.font.SysFont("sans-serif", self.font_size)
        )
        self.texts = [
            self.font.render(self.items[row], True, self.text_color)
            for row in range(self.rows)
        ]
        self.text_rects = self.create_text_rects()

        self.clicked = False

        self.circles = self.create_circle_locations()

    def create_text_rects(self):
        text_rects = []
        for row in range(self.rows):
            text_rects.append(
                self.texts[row].get_rect(
                    center=(
                        self._x
                        + self.circle_radius * 6
                        + (self._width - self.circle_radius * 6) // 2,
                        self._y + self.row_height * row + self.row_height // 2,
                    )
                )
            )

        return text_rects

    def create_circle_locations(self):
        circles = []
        for row in range(self.rows):
            circles.append(
                (
                    self._x + self.circle_radius * 3,
                    self._y + self.row_height * row + self.row_height // 2,
                )
            )
        return circles

    def listen(self, events):
        """Wait for inputs

        :param events: Use pygame.event.get()
        :type events: list of pygame.event.Event
        """
        if not self._hidden and not self._disabled:
            mouse_state = Mouse.get_mouse_state()
            x, y = Mouse.get_mouse_pos()

            if self.contains(x, y) and mouse_state == MouseState.CLICK:
                for row in range(self.rows):
                    if (
                        math.sqrt(
                            (self.circles[row][0] - x) ** 2
                            + (self.circles[row][1] - y) ** 2
                        )
                        <= self.circle_radius
                    ):
                        self.selected = row

    def draw(self):
        """Display to surface"""
        if not self._hidden:
            for row in range(self.rows):
                color = self.color1 if not row % 2 else self.color2

                if row == 0:
                    pygame.draw.rect(
                        self.win,
                        color,
                        (
                            self._x,
                            self._y + self.row_height * row,
                            self._width,
                            self.row_height,
                        ),
                        border_top_left_radius=self.radius,
                        border_top_right_radius=self.radius,
                    )

                elif row == self.rows - 1:
                    pygame.draw.rect(
                        self.win,
                        color,
                        (
                            self._x,
                            self._y + self.row_height * row,
                            self._width,
                            self.row_height,
                        ),
                        border_bottom_left_radius=self.radius,
                        border_bottom_right_radius=self.radius,
                    )

                else:
                    pygame.draw.rect(
                        self.win,
                        color,
                        (
                            self._x,
                            self._y + self.row_height * row,
                            self._width,
                            self.row_height,
                        ),
                    )

                width = 0 if row == self.selected else self.circle_thickness
                pygame.draw.circle(
                    self.win,
                    self.circle_color,
                    self.circles[row],
                    self.circle_radius,
                    width,
                )

                self.win.blit(self.texts[row], self.text_rects[row])


if __name__ == "__main__":
    import sys

    pygame.init()
    win = pygame.display.set_mode((1000, 800))

    checkbox = Checkbox(
        win,
        100,
        100,
        400,
        300,
        ("Apples", "Bananas", "Pears"),
        color1=(0, 180, 0),
        color2=(0, 50, 200),
        font_size=30,
        radius=10,
    )
    radio = Radio(
        win,
        550,
        400,
        400,
        300,
        ("Apples", "Bananas", "Pears"),
        color1=(0, 180, 0),
        color2=(0, 50, 200),
        font_size=30,
        radius=10,
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
