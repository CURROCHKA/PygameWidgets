import pygame

import pygame_widgets
from pygame_widgets.mouse import Mouse, MouseState
from pygame_widgets.widget import WidgetBase


class Dropdown(WidgetBase):
    def __init__(
        self, win, x, y, width, height, name, choices, is_sub_widget=False, **kwargs
    ):
        super().__init__(win, x, y, width, height, is_sub_widget)

        self._dropped = False
        self.__chosen = None

        values = kwargs.get("values", None)
        if values is None:
            values = choices[:]  # we copy the choices if value is empty

        if len(values) != len(choices):
            raise Exception(
                "'choices' and 'values' arguments should be identical in size"
            )

        # we create the DropdownChoice(s)
        direction = kwargs.get("direction", "down")
        self.__choices = []
        for i, text in enumerate(choices):
            last = i == len(choices) - 1

            if direction == "down":
                x = 0
                y = (i + 1) * height

            elif direction == "up":
                x = 0
                y = -(i + 1) * height

            elif direction == "right":
                x = (i + 1) * width
                y = 0

            elif direction == "left":
                x = -(i + 1) * width
                y = 0

            choice = DropdownChoice(
                self.win,
                x,
                y,
                width,
                height,
                text=text,
                dropdown=self,
                value=values[i],
                last=last,
                **kwargs,
            )
            choice.hide()
            self.__choices.append(choice)

        self.__main = HeadDropdown(
            self.win, 0, 0, width, height, text=name, dropdown=self, **kwargs
        )

        # Function
        self.on_click = kwargs.get("on_click", lambda *args: None)
        self.on_release = kwargs.get("on_release", lambda *args: None)
        self.on_click_params = kwargs.get("on_click_params", ())
        self.on_release_params = kwargs.get("on_release_params", ())

    def listen(self, events):
        """Wait for input

        :param events: Use pygame.event.get()
        :type events: list of pygame.event.Event
        """
        if not self._hidden and not self._disabled:
            mouse_state = Mouse.getMouseState()
            x, y = Mouse.getMousePos()

            if self.contains(x, y):
                if mouse_state == MouseState.CLICK:
                    self.on_click(*self.on_click_params)

                elif mouse_state == MouseState.RELEASE:
                    self.on_release(*self.on_release_params)

            # Then we handle the DropdownChoices
            self.__main.listen(events)
            for c in self.__choices:
                c.listen(events)

    def draw(self):
        if not self._hidden:
            self.__main.draw()
            for c in self.__choices:
                c.draw()

    def contains(self, x, y):
        return super().contains(x, y) or (
            any([c.contains(x, y) for c in self.__choices]) and self._dropped
        )

    def reset(self):
        self.__chosen = None

    def get_selected(self):
        return self.__chosen._value if self.__chosen is not None else None

    def toggle_dropped(self):
        self._dropped = not self._dropped
        if self._dropped:
            for c in self.__choices:
                c.show()
                self.moveToTop()
        else:
            for c in self.__choices:
                c.hide()

    def is_dropped(self):
        return self._dropped

    @property
    def chosen(self):
        return self.__chosen

    @chosen.setter
    def chosen(self, new_chosen):
        if isinstance(new_chosen, DropdownChoice):
            self.__chosen = new_chosen
        else:
            raise TypeError(
                "Wrong type for 'chosen' property, DropdownChoice is expected"
            )

    def set_dropped(self, drop):
        if drop != self._dropped:
            self.toggle_dropped()

    def set_x(self, x):
        self._x = x
        for i, c in enumerate(self.__choices):
            if c.direction == "down" or c.direction == "up":
                c._x = 0
            elif c.direction == "right":
                c._x = (i + 1) * c.getWidth()
            elif c.direction == "left":
                c._x = -(i + 1) * c.getWidth()

    def set_y(self, y):
        self._y = y
        for i, c in enumerate(self.__choices):
            if c.direction == "down":
                c._y = (i + 1) * c.getHeight()
            elif c.direction == "up":
                c._y = -(i + 1) * c.getHeight()
            elif c.direction == "right" or c.direction == "left":
                c._y = 0

    def set_width(self, width):
        self._width = width
        for i, c in enumerate(self.__choices):
            c.set_width(width)
            if c.direction == "down" or c.direction == "up":
                c._x = 0
            elif c.direction == "right":
                c._x = (i + 1) * c.getWidth()
            elif c.direction == "left":
                c._x = -(i + 1) * c.getWidth()
        self.__main.set_width(width)

    def set_height(self, height):
        self._height = height
        for i, c in enumerate(self.__choices):
            c.set_height(height)
            if c.direction == "down":
                c._y = (i + 1) * c.getHeight()
            elif c.direction == "up":
                c._y = -(i + 1) * c.getHeight()
            elif c.direction == "right" or c.direction == "left":
                c._y = 0
        self.__main.set_height(height)


class DropdownChoice(WidgetBase):
    def __init__(
        self,
        win,
        x,
        y,
        width,
        height,
        text: str,
        dropdown: Dropdown,
        last: bool,
        **kwargs,
    ):
        super().__init__(win, x, y, width, height, is_sub_widget=True)

        self.__text = text

        self._dropdown = dropdown
        self._value = kwargs.get("value", text)
        # Border
        self.border_thickness = kwargs.get("border_thickness", 3)
        self.border_colour = kwargs.get("border_colour", (0, 0, 0))
        self.border_radius = kwargs.get("border_radius", 0)

        # Colour
        self.inactive_colour = kwargs.get("inactive_colour", (150, 150, 150))
        self.hover_colour = kwargs.get("hover_colour", (125, 125, 125))
        self.pressed_colour = kwargs.get("pressed_colour", (100, 100, 100))
        self.colour = kwargs.get(
            "colour", self.inactive_colour
        )  # Allows colour to override inactive_colour
        self.inactive_colour = self.colour

        # Text
        self.text_colour = kwargs.get("text_colour", (0, 0, 0))
        self.font_size = kwargs.get("font_size", 20)
        self.font = kwargs.get(
            "font", pygame.font.SysFont("sans-serif", self.font_size)
        )
        self.text_horizontal_align = kwargs.get("text_horizontal_align", "centre")

        self.text_offset_left = self.font_size // 5
        self.text_offset_right = self.font_size // 5

        # action
        self.clicked = False

        self.__direction = kwargs.get("direction", "down")
        self.__last = last

    def draw(self):
        if not self._hidden:
            rect = pygame.Rect(
                self.computed_x,
                self.computed_y,
                self._width,
                self._height,
            )
            pygame.draw.rect(
                self.win, self.colour, rect, **self._compute_border_radii()
            )

            text_rendered = self.font.render(self.text, True, self.text_colour)

            if self.text_horizontal_align == "centre":
                text_rect = text_rendered.get_rect(
                    center=(
                        self.computed_x + self._width // 2,
                        self.computed_y + self._height // 2,
                    )
                )
            elif self.text_horizontal_align == "left":
                text_rect = text_rendered.get_rect(
                    center=(
                        self.computed_x
                        + text_rendered.get_width() // 2
                        + self.text_offset_left,
                        self.computed_y + self._height // 2,
                    )
                )
            elif self.text_horizontal_align == "right":
                text_rect = text_rendered.get_rect(
                    center=(
                        self.computed_x
                        - text_rendered.get_width() // 2
                        + self._width
                        - self.text_offset_right,
                        self.computed_y + self._height // 2,
                    )
                )

            self.win.blit(text_rendered, text_rect)

    def listen(self, events):
        """Wait for inputs

        :param events: Use pygame.event.get()
        :type events: list of pygame.event.Event
        """
        if not self._hidden and not self._disabled:
            mouse_state = Mouse.getMouseState()
            x, y = Mouse.getMousePos()

            if self.contains(x, y):
                if mouse_state == MouseState.RELEASE and self.clicked:
                    self.clicked = False
                    self._dropdown.set_dropped(False)
                    self._dropdown.chosen = self

                elif mouse_state == MouseState.CLICK:
                    self.clicked = True
                    self.colour = self.pressed_colour

                elif mouse_state == MouseState.DRAG and self.clicked:
                    self.colour = self.pressed_colour

                elif mouse_state == MouseState.HOVER or mouse_state == MouseState.DRAG:
                    self.colour = self.hover_colour

            else:
                self.clicked = False
                self.colour = self.inactive_colour

    def contains(self, x, y) -> bool:
        return (
            self.computed_x < x < self.computed_x + self._width
            and self.computed_y < y < self.computed_y + self._height
        )

    def _compute_border_radii(self):
        border_radius = {}
        if not self.last:
            return border_radius
        if self.direction == "up":
            border_radius["border_top_left_radius"] = self.border_radius
            border_radius["border_top_right_radius"] = self.border_radius

        elif self.direction == "down":
            border_radius["border_bottom_left_radius"] = self.border_radius
            border_radius["border_bottom_right_radius"] = self.border_radius

        elif self.direction == "right":
            border_radius["border_top_right_radius"] = self.border_radius
            border_radius["border_bottom_right_radius"] = self.border_radius

        elif self.direction == "left":
            border_radius["border_top_left_radius"] = self.border_radius
            border_radius["border_bottom_left_radius"] = self.border_radius

        return border_radius

    @property
    def text(self):
        return self.__text

    @text.setter
    def text(self, newText):
        if isinstance(newText, str):
            self.__text = newText
        else:
            raise TypeError("Wrong type for 'text' property, str is expected")

    @property
    def direction(self):
        return self.__direction

    @property
    def last(self):
        return self.__last

    @last.setter
    def last(self, newLast):
        if isinstance(newLast, bool):
            self.__last = newLast
        else:
            raise TypeError("Wrong type for 'last' property, boolean is expected")

    @direction.setter
    def direction(self, new_direction):
        if isinstance(new_direction, str):
            self.__direction = new_direction
        else:
            raise TypeError("Wrong type for 'direction' property, str is expected")

    @property
    def computed_x(self):
        return self._dropdown.getX() + self._x

    @property
    def computed_y(self):
        return self._dropdown.getY() + self._y


class HeadDropdown(DropdownChoice):
    def __init__(self, win, x, y, width, height, text, dropdown, **kwargs):
        super().__init__(win, x, y, width, height, text, dropdown, last=True, **kwargs)
        self.__head_text = text

    def listen(self, events):
        """Wait for inputs

        :param events: Use pygame.event.get()
        :type events: list of pygame.event.Event
        """
        if not self._hidden and not self._disabled:
            mouse_state = Mouse.getMouseState()
            x, y = Mouse.getMousePos()

            if self.contains(x, y):
                if mouse_state == MouseState.CLICK:
                    self.clicked = True
                    self._dropdown.toggle_dropped()

                elif mouse_state == MouseState.DRAG and self.clicked:
                    self.colour = self.pressed_colour

                elif mouse_state == MouseState.RELEASE:
                    self.clicked = False

                elif mouse_state == MouseState.HOVER or mouse_state == MouseState.DRAG:
                    self.colour = self.hover_colour

                elif mouse_state == MouseState.RIGHT_CLICK:
                    self._dropdown.reset()

            else:
                self.clicked = False
                self.colour = self.inactive_colour

    def _compute_border_radii(self):
        border_radius = {}
        if not self.last:
            return border_radius
        if self._dropdown.is_dropped():
            if self.direction == "up":
                border_radius["border_bottom_left_radius"] = self.border_radius
                border_radius["border_bottom_right_radius"] = self.border_radius

            elif self.direction == "down":
                border_radius["border_top_left_radius"] = self.border_radius
                border_radius["border_top_right_radius"] = self.border_radius

            elif self.direction == "left":
                border_radius["border_top_right_radius"] = self.border_radius
                border_radius["border_bottom_right_radius"] = self.border_radius

            elif self.direction == "right":
                border_radius["border_top_left_radius"] = self.border_radius
                border_radius["border_bottom_left_radius"] = self.border_radius
        else:
            border_radius["border_top_left_radius"] = self.border_radius
            border_radius["border_bottom_left_radius"] = self.border_radius
            border_radius["border_top_right_radius"] = self.border_radius
            border_radius["border_bottom_right_radius"] = self.border_radius

        return border_radius

    @property
    def text(self):
        return (
            self._dropdown.chosen.text
            if self._dropdown.chosen is not None
            else self.__head_text
        )


if __name__ == "__main__":
    import sys

    from pygame_widgets.button import Button

    pygame.init()
    win = pygame.display.set_mode((400, 280))
    width, height = pygame.display.get_window_size()

    dropdown = Dropdown(
        win,
        120,
        10,
        100,
        50,
        name="Select Colour",
        choices=["Red", "Blue", "Yellow"],
        colour=(200, 0, 0),
        border_radius=3,
        values=[1, 2, "true"],
        direction="down",
        text_horizontal_align="left",
    )

    def printValue():
        print(dropdown.get_selected())

    button = Button(
        win,
        120,
        100,
        100,
        50,
        text="Print Value",
        font_size=30,
        margin=20,
        inactive_colour=(255, 0, 0),
        pressed_colour=(0, 255, 0),
        radius=5,
        on_click=printValue,
        font=pygame.font.SysFont("calibri", 10),
        text_vertical_align="bottom",
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
