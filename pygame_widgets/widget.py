import weakref
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Iterable, Iterator, MutableSet
from typing import Any

import pygame

from pygame_widgets.mouse import Mouse


class OrderedSet(MutableSet):
    """Insertion-ordered set backed by an ``OrderedDict``.

    This preserves the order in which elements are added, and supports
    moving existing elements to the front or back of the iteration order.
    """

    def __init__(self, values: Iterable[Any] = ()):
        """Initialise the set with optional ``values``."""
        self._od = OrderedDict().fromkeys(values)

    def __len__(self) -> int:
        return len(self._od)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._od)

    def __contains__(self, value: object) -> bool:
        return value in self._od

    def add(self, value: object) -> None:
        """Add *value* to the set (at the end if new)."""
        self._od[value] = None

    def discard(self, value: object) -> None:
        """Remove *value* from the set if it is present."""
        self._od.pop(value, None)

    def move_to_end(self, value: object) -> None:
        """Move *value* to the end of the iteration order."""
        self._od.move_to_end(value)

    def move_to_start(self, value: object) -> None:
        """Move *value* to the start of the iteration order."""
        self._od.move_to_end(value, last=False)

    def copy(self) -> "OrderedSet":
        """Return a shallow copy of the set."""
        return OrderedSet(values=self._od.keys())


class OrderedWeakset(weakref.WeakSet):
    """WeakSet whose elements can be reordered.

    Wraps an :class:`OrderedSet` internally so that iteration order can be
    controlled via :meth:`move_to_end` / :meth:`move_to_start`.
    """

    _remove = ...  # Set by weakref.WeakSet.__init__()

    def __init__(self, values: Iterable = ()):
        """Initialise the weak set with optional *values*."""
        super().__init__()

        self.data = OrderedSet()
        for elem in values:
            self.add(elem)

    def move_to_end(self, item: object) -> None:
        """Move *item* to the end of the iteration order."""
        self.data.move_to_end(weakref.ref(item, self._remove))

    def move_to_start(self, item: object) -> None:
        """Move *item* to the start of the iteration order."""
        self.data.move_to_start(weakref.ref(item, self._remove))


class WidgetBase(ABC):
    """Base class for all pygame-widgets controls.

    ``WidgetBase`` stores the shared geometry, visibility and enabled state used
    by concrete widgets. Top-level widgets automatically register with
    ``WidgetHandler`` so they can receive events and be drawn in z-order.
    Sub-widgets are owned by another widget and are not registered separately.
    """

    def __init__(
        self,
        surface: pygame.Surface,
        x: float,
        y: float,
        width: float,
        height: float,
        is_sub_widget: bool = False,
    ) -> None:
        """Initialize common widget state.

        Args:
            surface: Surface on which the widget is drawn.
            x: X-coordinate of the widget's top-left corner.
            y: Y-coordinate of the widget's top-left corner.
            width: Widget width.
            height: Widget height.
            is_sub_widget: Whether this widget is owned and drawn by another
                widget instead of being managed directly by ``WidgetHandler``.
        """
        self.surface = surface
        self.x = x
        self.y = y
        self._width = width
        self._height = height
        self._is_sub_widget = is_sub_widget

        self._hidden = False
        self._disabled = False

        if not is_sub_widget:
            WidgetHandler.add_widget(self)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(x = {self.x}, y = {self.y}, width = {self._width}, height = {self._height})"

    @property
    def width(self) -> float:
        return self._width

    @width.setter
    def width(self, value: float) -> None:
        self._width = value
        # TODO: call widget width setter

    @property
    def height(self) -> float:
        return self._height

    @height.setter
    def height(self, value: float) -> None:
        self._height = value
        # TODO: call widget height setter

    @property
    def is_sub_widget(self) -> bool:
        return self._is_sub_widget

    @is_sub_widget.setter
    def is_sub_widget(self, value: bool) -> None:
        """Update sub-widget ownership and global handler registration."""
        self._is_sub_widget = value
        if value:
            WidgetHandler.remove_widget(self)
        else:
            WidgetHandler.add_widget(self)

    @abstractmethod
    def listen(self, events: list[pygame.Event]) -> None:
        """Handle input events for this frame."""

    @abstractmethod
    def draw(self) -> None:
        """Draw the widget's current state to ``self.surface``."""

    def contains(self, x: float, y: float) -> bool:
        """Return whether a point lies inside the widget bounds.

        Args:
            x: X-coordinate in window space.
            y: Y-coordinate in window space.

        Returns:
            ``True`` when the point is strictly inside this widget's rectangle.
        """
        return (
            self.x < x - self.surface.get_abs_offset()[0] < self.x + self._width
        ) and (self.y < y - self.surface.get_abs_offset()[1] < self.y + self._height)

    def hide(self) -> None:
        """Hide the widget and move it behind other top-level widgets."""
        self._hidden = True
        if not self.is_sub_widget:
            WidgetHandler.move_to_bottom(self)

    def show(self) -> None:
        """Show the widget and move it above other top-level widgets."""
        self._hidden = False
        if not self.is_sub_widget:
            WidgetHandler.move_to_top(self)

    def disable(self) -> None:
        """Prevent the widget from handling input."""
        self._disabled = True

    def enable(self) -> None:
        """Allow the widget to handle input."""
        self._disabled = False

    def move_to_top(self) -> None:
        """Move this widget to the top of the global draw/event order."""
        WidgetHandler.move_to_top(self)

    def move_to_bottom(self) -> None:
        """Move this widget to the bottom of the global draw/event order."""
        WidgetHandler.move_to_bottom(self)

    def is_visible(self) -> bool:
        """Return whether the widget is visible."""
        return not self._hidden

    def is_enabled(self) -> bool:
        """Return whether the widget can handle input."""
        return not self._disabled


class WidgetHandler:
    """Global registry and frame dispatcher for top-level widgets.

    Widgets register here through ``WidgetBase`` unless they are marked as
    sub-widgets. The registry preserves z-order: widgets moved to the end are
    considered visually on top, receive mouse events first, and are drawn last.
    """

    _widgets: OrderedWeakset[WidgetBase] = OrderedWeakset()

    @staticmethod
    def main(events: list[pygame.Event]) -> None:
        """Process input and draw every registered widget for one frame.

        Event handling walks the widget stack from top to bottom. Once the mouse
        is over a higher widget, lower widgets are blocked from receiving events
        for that frame. Drawing then walks from bottom to top so later widgets
        appear above earlier ones.

        The widget set is copied before iteration so callbacks may add or remove
        widgets without invalidating the active loop.
        """
        blocked = False

        # Conversion is used to prevent errors when widgets are added/removed during iteration a.k.a safe iteration
        widgets = list(WidgetHandler._widgets)

        for widget in reversed(widgets):
            if not blocked or not widget.contains(*Mouse.get_mouse_pos()):
                widget.listen(events)

            # Ensure widgets covered by others are not affected (widgets created later)
            if widget.contains(*Mouse.get_mouse_pos()):  # TODO: Unless 'transparent'
                blocked = True

        for widget in widgets:
            widget.draw()

    @staticmethod
    def add_widget(widget: WidgetBase) -> None:
        """Register a widget and place it at the top of the stack."""
        if widget not in WidgetHandler._widgets:
            WidgetHandler._widgets.add(widget)
            WidgetHandler.move_to_top(widget)

    @staticmethod
    def remove_widget(widget: WidgetBase) -> None:
        """Remove a widget from the registry."""
        try:
            WidgetHandler._widgets.remove(widget)
        except KeyError:
            print(
                f"Error: Tried to remove {widget} when {widget} not in WidgetHandler."
            )

    @staticmethod
    def move_to_top(widget: WidgetBase) -> None:
        """Move a registered widget above all other widgets."""
        try:
            WidgetHandler._widgets.move_to_end(widget)
        except KeyError:
            print(
                f"Error: Tried to move {widget} to top when {widget} not in WidgetHandler."
            )

    @staticmethod
    def move_to_bottom(widget: WidgetBase) -> None:
        """Move a registered widget below all other widgets."""
        try:
            WidgetHandler._widgets.move_to_start(widget)
        except KeyError:
            print(
                f"Error: Tried to move {widget} to bottom when {widget} not in WidgetHandler."
            )

    @staticmethod
    def get_widgets() -> OrderedWeakset:
        """Return the live widget registry."""
        return WidgetHandler._widgets
