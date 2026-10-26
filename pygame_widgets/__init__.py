from pygame.event import Event

from pygame_widgets.widget import WidgetHandler

__version__ = "1.3.2"


def update(events: list[Event]):
    WidgetHandler.main(events)


def version():
    print(f"PygameWidgets v{__version__}")
