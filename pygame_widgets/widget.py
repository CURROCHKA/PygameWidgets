import weakref

from collections.abc import Iterable, MutableSet, Iterator
from collections import OrderedDict

from abc import abstractmethod, ABC
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
        super(OrderedWeakset, self).__init__()

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
        win: pygame.Surface,
        x: int | float,
        y: int | float,
        width: int | float,
        height: int | float,
        is_sub_widget: bool = False,
    ) -> None:
        """Initialize common widget state.

        Args:
            win: Surface on which the widget is drawn.
            x: X-coordinate of the widget's top-left corner.
            y: Y-coordinate of the widget's top-left corner.
            width: Widget width.
            height: Widget height.
            is_sub_widget: Whether this widget is owned and drawn by another
                widget instead of being managed directly by ``WidgetHandler``.
        """
        self.win = win
        self._x = x
        self._y = y
        self._width = width
        self._height = height
        self._isSubWidget = is_sub_widget

        self._hidden = False
        self._disabled = False

        if not is_sub_widget:
            WidgetHandler.addWidget(self)

    @abstractmethod
    def listen(self, events: list[pygame.Event]) -> None:
        """Handle input events for this frame."""
        pass

    @abstractmethod
    def draw(self) -> None:
        """Draw the widget's current state to ``self.win``."""
        pass

    def __repr__(self) -> str:
        return f"{type(self).__name__}(x = {self._x}, y = {self._y}, width = {self._width}, height = {self._height})"

    def contains(self, x: int | float, y: int | float) -> bool:
        """Return whether a point lies inside the widget bounds.

        Args:
            x: X-coordinate in window space.
            y: Y-coordinate in window space.

        Returns:
            ``True`` when the point is strictly inside this widget's rectangle.
        """
        return (
            self._x < x - self.win.get_abs_offset()[0] < self._x + self._width
        ) and (self._y < y - self.win.get_abs_offset()[1] < self._y + self._height)

    def hide(self) -> None:
        """Hide the widget and move it behind other top-level widgets."""
        self._hidden = True
        if not self._isSubWidget:
            WidgetHandler.moveToBottom(self)

    def show(self) -> None:
        """Show the widget and move it above other top-level widgets."""
        self._hidden = False
        if not self._isSubWidget:
            WidgetHandler.moveToTop(self)

    def disable(self) -> None:
        """Prevent the widget from handling input."""
        self._disabled = True

    def enable(self) -> None:
        """Allow the widget to handle input."""
        self._disabled = False

    def is_sub_widget(self) -> bool:
        """Return whether this widget is managed by a parent widget."""
        return self._isSubWidget

    def moveToTop(self) -> None:
        """Move this widget to the top of the global draw/event order."""
        WidgetHandler.moveToTop(self)

    def moveToBottom(self) -> None:
        """Move this widget to the bottom of the global draw/event order."""
        WidgetHandler.moveToBottom(self)

    def moveX(self, x: int | float) -> None:
        """Move the widget horizontally by ``x`` pixels."""
        self._x += x

    def moveY(self, y: int | float) -> None:
        """Move the widget vertically by ``y`` pixels."""
        self._y += y

    def get(self, attr: str) -> Any | None:
        """Return a supported widget attribute value.

        The base class supports ``'x'``, ``'y'``, ``'width'`` and ``'height'``.
        Subclasses may extend this method with widget-specific attributes and
        should call ``super().get(attr)`` for the shared geometry attributes.

        Args:
            attr: Attribute name to read.

        Returns:
            Attribute value, or ``None`` when the attribute is not supported.
        """
        if attr == "x":
            return self._x
        elif attr == "y":
            return self._y
        elif attr == "width":
            return self._width
        elif attr == "height":
            return self._height

    def getX(self) -> int | float:
        """Return the widget's x-coordinate."""
        return self._x

    def getY(self) -> int | float:
        """Return the widget's y-coordinate."""
        return self._y

    def getWidth(self) -> int | float:
        """Return the widget width."""
        return self._width

    def getHeight(self) -> int | float:
        """Return the widget height."""
        return self._height

    def isVisible(self) -> bool:
        """Return whether the widget is visible."""
        return not self._hidden

    def isEnabled(self) -> bool:
        """Return whether the widget can handle input."""
        return not self._disabled

    def set(self, attr: str, value: Any) -> None:
        """Set a supported widget attribute value.

        The base class supports ``'x'``, ``'y'``, ``'width'`` and ``'height'``.
        Subclasses may extend this method with widget-specific attributes and
        should call ``super().set(attr, value)`` for the shared geometry
        attributes.

        Args:
            attr: Attribute name to update.
            value: New attribute value.
        """
        if attr == "x":
            self._x = value
        elif attr == "y":
            self._y = value
        elif attr == "width":
            self._width = value
        elif attr == "height":
            self._height = value

    def setX(self, x: int | float) -> None:
        """Set the widget's x-coordinate."""
        self._x = x

    def setY(self, y: int | float) -> None:
        """Set the widget's y-coordinate."""
        self._y = y

    def setWidth(self, width: int | float) -> None:
        """Set the widget width."""
        self._width = width

    def setHeight(self, height: int | float) -> None:
        """Set the widget height."""
        self._height = height

    def setIsSubWidget(self, is_sub_widget: bool) -> None:
        """Update sub-widget ownership and global handler registration."""
        self._isSubWidget = is_sub_widget
        if is_sub_widget:
            WidgetHandler.removeWidget(self)
        else:
            WidgetHandler.addWidget(self)


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
    def addWidget(widget: WidgetBase) -> None:
        """Register a widget and place it at the top of the stack."""
        if widget not in WidgetHandler._widgets:
            WidgetHandler._widgets.add(widget)
            WidgetHandler.moveToTop(widget)

    @staticmethod
    def removeWidget(widget: WidgetBase) -> None:
        """Remove a widget from the registry."""
        try:
            WidgetHandler._widgets.remove(widget)
        except KeyError:
            print(
                f"Error: Tried to remove {widget} when {widget} not in WidgetHandler."
            )

    @staticmethod
    def moveToTop(widget: WidgetBase) -> None:
        """Move a registered widget above all other widgets."""
        try:
            WidgetHandler._widgets.move_to_end(widget)
        except KeyError:
            print(
                f"Error: Tried to move {widget} to top when {widget} not in WidgetHandler."
            )

    @staticmethod
    def moveToBottom(widget: WidgetBase) -> None:
        """Move a registered widget below all other widgets."""
        try:
            WidgetHandler._widgets.move_to_start(widget)
        except KeyError:
            print(
                f"Error: Tried to move {widget} to bottom when {widget} not in WidgetHandler."
            )

    @staticmethod
    def getWidgets() -> OrderedWeakset:
        """Return the live widget registry."""
        return WidgetHandler._widgets
