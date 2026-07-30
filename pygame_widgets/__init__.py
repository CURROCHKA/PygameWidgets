from pygame_widgets.mouse import Mouse
from pygame_widgets.widget import WidgetHandler

from pygame.event import Event

__version__ = "1.3.2"


def update(events: list[Event]):
    Mouse.update_mouse_state()
    Mouse.handle_events(events)
    WidgetHandler.main(events)


def version():
    print(f"PygameWidgets v{__version__}")
