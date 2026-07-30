import pygame

import pygame_widgets
from pygame_widgets.mouse import Mouse, MouseState
from pygame_widgets.widget import WidgetBase


class Button(WidgetBase):
    def __init__(self, win, x, y, width, height, is_sub_widget=False, **kwargs):
        """A customisable button for Pygame

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
        super().__init__(win, x, y, width, height, is_sub_widget)

        # Color
        self.inactive_color = kwargs.get("inactive_color", (150, 150, 150))
        self.hover_color = kwargs.get("hover_color", (125, 125, 125))
        self.pressed_color = kwargs.get("pressed_color", (100, 100, 100))
        self.color = kwargs.get(
            "color", self.inactive_color
        )  # Allows color to override inactive_color
        self.inactive_color = self.color
        self.shadow_distance = kwargs.get("shadow_distance", 0)
        self.shadow_color = kwargs.get("shadow_color", (210, 210, 180))

        # Function
        self.on_click = kwargs.get("on_click", lambda *args: None)
        self.on_release = kwargs.get("on_release", lambda *args: None)
        self.on_hover = kwargs.get("on_hover", lambda *args: None)
        self.on_hover_release = kwargs.get("on_hover_release", lambda *args: None)
        self.on_click_params = kwargs.get("on_click_params", ())
        self.on_release_params = kwargs.get("on_release_params", ())
        self.on_hover_params = kwargs.get("on_hover_params", ())
        self.on_hover_release_params = kwargs.get("on_hover_release_params", ())
        self.clicked = False

        # Text (Remove if using PyInstaller)
        self.text_color = kwargs.get("text_color", (0, 0, 0))
        self.font_size = kwargs.get("font_size", 20)
        self.string = kwargs.get("text", "")
        self.font = kwargs.get("font", pygame.font.SysFont("calibri", self.font_size))
        self.text = self.font.render(self.string, True, self.text_color)
        self.text_horizontal_align = kwargs.get("text_horizontal_align", "centre")
        self.text_vertical_align = kwargs.get("text_vertical_align", "centre")
        self.margin = kwargs.get("margin", 20)

        self.text_rect = self.text.get_rect()
        self.align_text_rect()

        # Image
        self.image = kwargs.get("image", None)
        self.image_horizontal_align = kwargs.get("image_horizontal_align", "centre")
        self.image_vertical_align = kwargs.get("image_vertical_align", "centre")

        if self.image:
            self.image_rect = self.image.get_rect()
            self.align_image_rect()

        # Border
        self.border_thickness = kwargs.get("border_thickness", 0)
        self.inactive_border_color = kwargs.get("inactive_border_color", (0, 0, 0))
        self.hover_border_color = kwargs.get("hover_border_color", (80, 80, 80))
        self.pressed_border_color = kwargs.get("pressed_border_color", (100, 100, 100))
        self.border_color = kwargs.get("border_color", self.inactive_border_color)
        self.inactive_border_color = self.border_color
        self.radius = kwargs.get("radius", 0)

        self.mouse_was_inside = False

    def align_image_rect(self):
        self.image_rect.center = (
            self._x + self._width // 2,
            self._y + self._height // 2,
        )

        if self.image_horizontal_align == "left":
            self.image_rect.left = self._x + self.margin
        elif self.image_horizontal_align == "right":
            self.image_rect.right = self._x + self._width - self.margin

        if self.image_vertical_align == "top":
            self.image_rect.top = self._y + self.margin
        elif self.image_vertical_align == "bottom":
            self.image_rect.bottom = self._y + self._height - self.margin

    def align_text_rect(self):
        self.text_rect.center = (
            self._x + self._width // 2,
            self._y + self._height // 2,
        )

        if self.text_horizontal_align == "left":
            self.text_rect.left = self._x + self.margin
        elif self.text_horizontal_align == "right":
            self.text_rect.right = self._x + self._width - self.margin

        if self.text_vertical_align == "top":
            self.text_rect.top = self._y + self.margin
        elif self.text_vertical_align == "bottom":
            self.text_rect.bottom = self._y + self._height - self.margin

    def listen(self, events):
        """Wait for inputs

        :param events: Use pygame.event.get()
        :type events: list of pygame.event.Event
        """
        if not self._hidden and not self._disabled:
            mouse_state = Mouse.get_mouse_state()
            x, y = Mouse.get_mouse_pos()

            if self.contains(x, y):
                if mouse_state == MouseState.RELEASE and self.clicked:
                    self.clicked = False
                    self.on_release(*self.on_release_params)

                elif mouse_state == MouseState.CLICK:
                    self.clicked = True
                    self.on_click(*self.on_click_params)
                    self.color = self.pressed_color
                    self.border_color = self.pressed_border_color

                elif mouse_state == MouseState.DRAG and self.clicked:
                    self.color = self.pressed_color
                    self.border_color = self.pressed_border_color

                elif mouse_state == MouseState.HOVER or mouse_state == MouseState.DRAG:
                    self.color = self.hover_color
                    self.border_color = self.hover_border_color
                    self.on_hover(*self.on_hover_params)

                self.mouse_was_inside = True

            elif self.mouse_was_inside:
                self.on_hover_release(*self.on_hover_release_params)
                self.mouse_was_inside = False

            else:
                self.clicked = False
                self.color = self.inactive_color
                self.border_color = self.inactive_border_color

    def draw(self):
        """Display to surface"""
        if not self._hidden:
            pygame.draw.rect(
                self.win,
                self.shadow_color,
                (
                    self._x + self.shadow_distance,
                    self._y + self.shadow_distance,
                    self._width,
                    self._height,
                ),
                border_radius=self.radius,
            )

            pygame.draw.rect(
                self.win,
                self.border_color,
                (self._x, self._y, self._width, self._height),
                border_radius=self.radius,
            )

            pygame.draw.rect(
                self.win,
                self.color,
                (
                    self._x + self.border_thickness,
                    self._y + self.border_thickness,
                    self._width - self.border_thickness * 2,
                    self._height - self.border_thickness * 2,
                ),
                border_radius=self.radius,
            )

            if self.image:
                self.image_rect = self.image.get_rect()
                self.align_image_rect()
                self.win.blit(self.image, self.image_rect)

            self.text = self.font.render(self.string, True, self.text_color)
            self.text_rect = self.text.get_rect()
            self.align_text_rect()
            self.win.blit(self.text, self.text_rect)

    def set_text(self, text):
        self.string = text
        self.text = self.font.render(self.string, True, self.text_color)
        self.text_rect = self.text.get_rect()
        self.align_text_rect()

    def set_image(self, image):
        self.image = image
        self.image_rect = self.image.get_rect()
        self.align_image_rect()

    def set_on_click(self, on_click, params=()):
        self.on_click = on_click
        self.on_click_params = params

    def set_on_release(self, on_release, params=()):
        self.on_release = on_release
        self.on_release_params = params

    def set_on_hover(self, on_hover, params=()):
        self.on_hover = on_hover
        self.on_hover_params = params

    def set_inactive_color(self, color):
        self.inactive_color = color

    def set_pressed_color(self, color):
        self.pressed_color = color

    def set_hover_color(self, color):
        self.hover_color = color

    def get(self, attr):
        parent = super().get(attr)
        if parent is not None:
            return parent

        if attr == "color":
            return self.color

    def set(self, attr, value):
        super().set(attr, value)

        if attr == "color":
            self.inactive_color = value


class ButtonArray(WidgetBase):
    def __init__(self, win, x, y, width, height, shape, **kwargs):
        """A collection of buttons

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
        :param shape: The 2d shape of the array (columns, rows)
        :type shape: tuple of int
        :param kwargs: Optional parameters
        """
        super().__init__(win, x, y, width, height)

        self.shape = shape
        self.num_buttons = shape[0] * shape[1]

        # Array
        self.color = kwargs.get("color", (210, 210, 180))
        self.border = kwargs.get("border", 10)
        self.top_border = kwargs.get("top_border", self.border)
        self.bottom_border = kwargs.get("bottom_border", self.border)
        self.left_border = kwargs.get("left_border", self.border)
        self.right_border = kwargs.get("right_border", self.border)
        self.border_radius = kwargs.get("border_radius", 0)
        self.separation_thickness = kwargs.get("separation_thickness", self.border)

        self.button_attributes = {
            # Color
            "inactive_color": kwargs.get("inactive_colors", None),
            "hover_color": kwargs.get("hover_colors", None),
            "pressed_color": kwargs.get("pressed_colors", None),
            "shadow_distance": kwargs.get("shadow_distances", None),
            "shadow_color": kwargs.get("shadow_colors", None),
            # Function
            "on_click": kwargs.get("on_clicks", None),
            "on_release": kwargs.get("on_releases", None),
            "on_hover": kwargs.get("on_hovers", None),
            "on_click_params": kwargs.get("on_click_params", None),
            "on_release_params": kwargs.get("on_release_params", None),
            "on_hover_params": kwargs.get("on_hover_params", None),
            # Text
            "text_color": kwargs.get("text_colors", None),
            "font_size": kwargs.get("font_sizes", None),
            "text": kwargs.get("texts", None),
            "font": kwargs.get("fonts", None),
            "text_horizontal_align": kwargs.get("text_horizontal_aligns", None),
            "text_vertical_align": kwargs.get("text_vertical_aligns", None),
            "margin": kwargs.get("margins", None),
            # Image
            "image": kwargs.get("images", None),
            "image_horizontal_align": kwargs.get("image_horizontal_aligns", None),
            "image_vertical_align": kwargs.get("image_verical_aligns", None),
            "image_rotation": kwargs.get("image_rotations", None),
            "image_fill": kwargs.get("image_fills", None),
            "image_zoom": kwargs.get("image_zooms", None),
            "radius": kwargs.get("radii", None),
        }

        self.buttons = []
        self.create_buttons()

    def create_buttons(self):
        across, down = self.shape
        width = (
            self._width
            - self.separation_thickness * (across - 1)
            - self.left_border
            - self.right_border
        ) // across
        height = (
            self._height
            - self.separation_thickness * (down - 1)
            - self.top_border
            - self.bottom_border
        ) // down

        count = 0
        for i in range(across):
            for j in range(down):
                x = self._x + i * (width + self.separation_thickness) + self.left_border
                y = self._y + j * (height + self.separation_thickness) + self.top_border
                self.buttons.append(
                    Button(
                        self.win,
                        x,
                        y,
                        width,
                        height,
                        is_sub_widget=True,
                        **{
                            k: v[count]
                            for k, v in self.button_attributes.items()
                            if v is not None
                        },
                    )
                )
                count += 1

    def listen(self, events):
        """Wait for inputs

        :param events: Use pygame.event.get()
        :type events: list of pygame.event.Event
        """
        if not self._hidden and not self._disabled:
            for button in self.buttons:
                button.listen(events)

    def draw(self):
        """Display to surface"""
        if not self._hidden:
            rects = [
                (
                    self._x + self.border_radius,
                    self._y,
                    self._width - self.border_radius * 2,
                    self._height,
                ),
                (
                    self._x,
                    self._y + self.border_radius,
                    self._width,
                    self._height - self.border_radius * 2,
                ),
            ]

            circles = [
                (self._x + self.border_radius, self._y + self.border_radius),
                (
                    self._x + self.border_radius,
                    self._y + self._height - self.border_radius,
                ),
                (
                    self._x + self._width - self.border_radius,
                    self._y + self.border_radius,
                ),
                (
                    self._x + self._width - self.border_radius,
                    self._y + self._height - self.border_radius,
                ),
            ]

            for rect in rects:
                pygame.draw.rect(self.win, self.color, rect)

            for circle in circles:
                pygame.draw.circle(self.win, self.color, circle, self.border_radius)

            for button in self.buttons:
                button.draw()

    def get_buttons(self):
        return self.buttons


if __name__ == "__main__":
    import sys

    pygame.init()
    win = pygame.display.set_mode((600, 600))

    button = Button(
        win,
        100,
        100,
        300,
        150,
        text="Hello",
        font_size=50,
        margin=20,
        inactive_color=(255, 0, 0),
        pressed_color=(0, 255, 0),
        radius=20,
        on_click=lambda: print("Click"),
        font=pygame.font.SysFont("calibri", 10),
        text_vertical_align="bottom",
        image_horizontal_align="centre",
        image_vertical_align="centre",
        border_thickness=3,
        on_release=lambda: print("Release"),
        shadow_distance=5,
        border_color=(0, 0, 0),
        on_hover=lambda: print("Hover"),
        on_hover_release=lambda: print("Hover Release"),
    )

    buttonArray = ButtonArray(
        win,
        50,
        50,
        500,
        500,
        (2, 2),
        border=100,
        texts=("1", "2", "3", "4"),
        onClicks=(
            lambda: print(1),
            lambda: print(2),
            lambda: print(3),
            lambda: print(4),
        ),
    )

    buttonArray.hide()

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
