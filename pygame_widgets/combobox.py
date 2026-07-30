import pygame_widgets
from pygame_widgets.dropdown import Dropdown, DropdownChoice
from pygame_widgets.textbox import TextBox
from pygame_widgets.widget import WidgetBase


class ComboBox(Dropdown):
    def __init__(
        self, win, x, y, width, height, choices, textbox_kwargs=None, **kwargs
    ):
        """Initialise a customisable combo box for Pygame. Acts like a searchable dropdown.

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
        :param choices: Possible search values
        :type choices: list(str)
        :param textbox_kwargs: Kwargs to be passed to the search box
        :type textbox_kwargs: dict(str: Any)
        :param max_results: The maximum number of results to display
        :type max_results: int
        :param kwargs: Optional parameters
        """
        WidgetBase.__init__(self, win, x, y, width, height)

        if textbox_kwargs is None:
            textbox_kwargs = {}
        self._dropped = False

        self.choices = choices
        self.suggestions = choices  # Stores the current suggestions

        self._search_algo = kwargs.get("search_algo", self._default_search)

        # Adds params that are not specified in text box
        for key, value in kwargs.items():
            if key not in textbox_kwargs:
                textbox_kwargs[key] = value

        self.text_bar = TextBox(
            win,
            x,
            y,
            width,
            height,
            is_sub_widget=True,
            on_text_changed=self.update_search_results,
            **textbox_kwargs,
        )
        self.__main = self.text_bar
        # Set the number of choices if not given
        self.max_results = kwargs.get("max_results", len(choices))

        self.create_dropdown_choices(x, y, width, height, **kwargs)

        self.get_text = self.text_bar.get_text

        # Function``
        self.on_selected = kwargs.get("on_selected", lambda *args: None)
        self.on_selected_params = kwargs.get("on_selected_params", ())
        self.on_start_search = kwargs.get("on_start_search", lambda *args: None)
        self.on_start_search_params = kwargs.get("on_start_search_params", ())
        self.on_stop_search = kwargs.get("on_stop_search", lambda *args: None)
        self.on_stop_search_params = kwargs.get("on_stop_search_params", ())

    def create_dropdown_choices(self, x, y, width, height, **kwargs):
        """Create the widgets for the choices."""
        # We create the DropdownChoice(s)
        direction = kwargs.get("direction", "down")
        self.__choices = []
        for i, text in enumerate(self.choices):
            if i == self.max_results:
                return

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

            self.__choices.append(
                DropdownChoice(
                    self.win,
                    x,
                    y,
                    width,
                    height,
                    text=text,
                    dropdown=self,
                    value=i,
                    last=(i == self.max_results - 1),
                    **kwargs,
                )
            )

    def listen(self, events):
        """Wait for input.

        :param events: Use pygame.event.get()
        :type events: list of pygame.event.Event
        """
        if not self._hidden and not self._disabled:
            # Keeps state of selected
            previously_selected = self.text_bar.selected
            self.text_bar.listen(events)

            if self._dropped:
                for dropdown_choice in self.__choices:
                    dropdown_choice.listen(events)
                    if dropdown_choice.clicked:
                        # The choice was clicked by user
                        self.text_bar.set_text(dropdown_choice.text)
                        # TODO
                        # If you write some color,
                        # then select it from the drop-down menu,
                        # then double-click on the textbox,
                        # then I have blocked any actions in the textbox itself,
                        # although the cursor is lit, which indicates that the widget is active.
                        # But as soon as I press backspace twice, all the actions become available.
                        # And it doesn't always work like that.
                        # To be honest, I have no idea where the error might be.
                        # It's not even clear who's to blame: combobox or textbox
                        self.on_selected(*self.on_selected_params)

            # Whether the search is started or stopped
            if previously_selected and not self.text_bar.selected:
                self.on_stop_search(*self.on_stop_search_params)
                self._dropped = False

            if not previously_selected and self.text_bar.selected:
                self.on_start_search(*self.on_start_search_params)
                self.update_search_results()

    def draw(self):
        """Draw the widget."""
        if not self._hidden:
            self.text_bar.draw()
            if self._dropped:
                # Find how many choices should be shown
                number_visible = min(len(self.suggestions), self.max_results)
                for i, dropdown_choice in enumerate(self.__choices):
                    # Define if the the dropdown should be shown
                    if i < number_visible:
                        dropdown_choice.show()
                        self.moveToTop()
                        # Choose the text to show
                        dropdown_choice.text = self.suggestions[i]
                    else:
                        dropdown_choice.hide()
                    dropdown_choice.draw()

    def contains(self, x, y):
        return super(Dropdown, self).contains(x, y) or (
            any([c.contains(x, y) for c in self.__choices]) and self._dropped
        )

    def update_search_results(self):
        """Update the suggested results based on selected text.

        Uses a 'contains' research. Could be improved by other
        search algorithms.
        """
        text = self.text_bar.get_text()

        if text != "":
            # Finds all the texts that start with the same text
            self.suggestions = self._search_algo(text, self.choices)
            self._dropped = True
        else:
            self._dropped = False

    def _search_algo(self, text, choices):
        """Return the suggestions of text in choices."""
        raise NotImplementedError("A search method must override this.")

    @staticmethod
    def _default_search(text, choices):
        """Return the suggestions of text in choices."""

        # First add the ones that perfectly match case
        suggestions = [choice for choice in choices if choice.startswith(text)]
        # Then add the ones that include text
        suggestions += [
            choice for choice in choices if text in choice and choice not in suggestions
        ]
        return suggestions


if __name__ == "__main__":
    import sys

    import pygame

    from pygame_widgets.button import Button

    pygame.init()
    win = pygame.display.set_mode((600, 600))

    combo_box = ComboBox(
        win,
        120,
        10,
        250,
        50,
        name="Select Colour",
        choices=pygame.colordict.THECOLORS.keys(),
        max_results=4,
        font=pygame.font.SysFont("calibri", 30),
        border_radius=3,
        colour=(0, 200, 50),
        direction="down",
        text_horizontal_align="left",
    )

    def output():
        combo_box.text_bar.colour = combo_box.get_text()

    button = Button(
        win,
        10,
        10,
        100,
        50,
        text="Set Colour",
        font_size=30,
        margin=15,
        inactive_colour=(200, 0, 100),
        pressed_colour=(0, 255, 0),
        radius=5,
        on_click=output,
        font=pygame.font.SysFont("calibri", 18),
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
