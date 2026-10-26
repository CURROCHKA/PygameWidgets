import weakref
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Iterable, Iterator, MutableSet
from dataclasses import dataclass
from typing import Any

import pygame
from pygame.typing import Point, RectLike


class OrderedSet(MutableSet):
    def __init__(self, values: Iterable[Any] = ()):
        self._od = OrderedDict.fromkeys(values)

    def __len__(self) -> int:
        return len(self._od)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._od)

    def __contains__(self, value: object) -> bool:
        return value in self._od

    def add(self, value: object) -> None:
        self._od[value] = None

    def discard(self, value: object) -> None:
        self._od.pop(value, None)

    def move_to_end(self, value: object) -> None:
        self._od.move_to_end(value)

    def move_to_start(self, value: object) -> None:
        self._od.move_to_end(value, last=False)

    def copy(self) -> "OrderedSet":
        return OrderedSet(values=self._od.keys())


class OrderedWeakset(weakref.WeakSet):
    """WeakSet that keeps insertion order and can move items to either end."""

    _remove = ...  # Set by weakref.WeakSet.__init__()

    def __init__(self, values: Iterable = ()):
        super().__init__()

        self.data = OrderedSet()
        for elem in values:
            self.add(elem)

    def move_to_end(self, item: object) -> None:
        self.data.move_to_end(weakref.ref(item, self._remove))

    def move_to_start(self, item: object) -> None:
        self.data.move_to_start(weakref.ref(item, self._remove))


@dataclass(frozen=True, slots=True)
class MouseEvent:
    """Mouse event passed to the ``on_mouse_*`` handlers.

    ``pos`` is in the coordinates of the widget's surface, not the window.
    ``button`` is 0 for motion; ``clicks`` is 2 for a double click, 3 for a triple.
    """

    pos: Point
    button: int = 0
    clicks: int = 0
    mod: int = 0


class WidgetBase(ABC):
    """Base class for all widgets.

    Top-level widgets register in ``WidgetHandler`` on creation. Sub-widgets
    (``is_sub_widget=True``) are owned by a container and reached through its
    ``children()``.
    """

    focusable: bool = False
    """Whether clicking the widget gives it keyboard focus."""
    # raise_on_click: bool = False # TODO

    def __init__(
        self,
        surface: pygame.Surface,
        x: float,
        y: float,
        width: float,
        height: float,
        is_sub_widget: bool = False,
    ) -> None:
        self.surface = surface
        self._rect = pygame.FRect(x, y, width, height)
        self._is_sub_widget = is_sub_widget

        self._hidden = False
        self._disabled = False

        if not is_sub_widget:
            WidgetHandler.add_widget(self)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(x={self.x}, y={self.y}, width={self.width}, height={self.height})"

    @property
    def rect(self) -> pygame.FRect:
        """Copy of the widget's rect. Assign a new rect to move or resize the widget."""
        return self._rect.copy()

    @rect.setter
    def rect(self, value: RectLike) -> None:
        self._rect = pygame.FRect(value)
        self._on_geometry_changed()

    @property
    def x(self) -> float:
        return self._rect.x

    @x.setter
    def x(self, value: float) -> None:
        self._rect.x = value
        self._on_geometry_changed()

    @property
    def y(self) -> float:
        return self._rect.y

    @y.setter
    def y(self, value: float) -> None:
        self._rect.y = value
        self._on_geometry_changed()

    @property
    def width(self) -> float:
        return self._rect.width

    @width.setter
    def width(self, value: float) -> None:
        self._rect.width = value
        self._on_geometry_changed()

    @property
    def height(self) -> float:
        return self._rect.height

    @height.setter
    def height(self, value: float) -> None:
        self._rect.height = value
        self._on_geometry_changed()

    @property
    def is_sub_widget(self) -> bool:
        return self._is_sub_widget

    @is_sub_widget.setter
    def is_sub_widget(self, value: bool) -> None:
        if value == self.is_sub_widget:
            return

        self._is_sub_widget = value
        if value:
            WidgetHandler.remove_widget(self)
        else:
            WidgetHandler.add_widget(self)

    def _on_geometry_changed(self) -> None:
        """Called after x, y, width, height or rect change. Override to update layout."""

    def children(self) -> Iterable["WidgetBase"]:
        """Sub-widgets in z-order, topmost last. Containers override this."""
        return ()

    def iter_tree(self) -> Iterator["WidgetBase"]:
        """Yield this widget and all its descendants."""
        yield self
        for child in self.children():
            yield from child.iter_tree()

    def contains(self, pos: Point) -> bool:
        """Whether a window-space point is inside the widget.

        Left and top edges count as inside, right and bottom as outside,
        as in ``pygame.Rect``.
        """
        offset_x, offset_y = self.surface.get_abs_offset()
        return self._rect.collidepoint(pos[0] - offset_x, pos[1] - offset_y)

    def path_at(self, pos: Point) -> list["WidgetBase"]:
        """Path from this widget to the deepest widget at window-space ``pos``.

        Returns ``[]`` if ``pos`` misses. Hidden widgets are skipped together with
        their children. A disabled widget returns itself without asking its children.
        """
        if self._hidden:
            return []
        if self._disabled:
            return [self] if self.contains(pos) else []
        for child in reversed(tuple(self.children())):
            path = child.path_at(pos)
            if path:
                return [self, *path]
        return [self] if self.contains(pos) else []

    def to_local(self, pos: Point) -> Point:
        """Convert a window-space point to coordinates of ``self.surface``."""
        offset_x, offset_y = self.surface.get_abs_offset()
        return pos[0] - offset_x, pos[1] - offset_y

    def hide(self) -> None:
        """Hide the widget and its children.

        They are not drawn, don't block the mouse and lose focus and capture.
        The z-order is kept.
        """
        self._hidden = True
        WidgetHandler.forget(self)

    def show(self) -> None:
        """Show the widget again. Its z-order is unchanged."""
        self._hidden = False

    def disable(self) -> None:
        """Stop input for the widget and its children.

        It is still drawn and still takes clicks, so widgets below don't get them.
        """
        self._disabled = True
        WidgetHandler._update_disabled()
        WidgetHandler.forget(self)

    def enable(self) -> None:
        self._disabled = False
        WidgetHandler._update_disabled()

    def is_visible(self) -> bool:
        return not self._hidden

    def is_enabled(self) -> bool:
        return not self._disabled and self not in WidgetHandler._disabled_by_ancestor

    def is_hovered(self) -> bool:
        """Whether the mouse is over this widget or one of its descendants."""
        return WidgetHandler.is_hovered(self)

    def is_focused(self) -> bool:
        return WidgetHandler.is_focused(self)

    def focus(self) -> None:
        WidgetHandler.set_focus(self)

    def move_to_top(self) -> None:
        """Move above all other top-level widgets. Raises ValueError for sub-widgets."""
        WidgetHandler.move_to_top(self)

    def move_to_bottom(self) -> None:
        """Move below all other top-level widgets. Raises ValueError for sub-widgets."""
        WidgetHandler.move_to_bottom(self)

    # Input handlers. WidgetHandler calls them; by default they do nothing.
    def on_mouse_enter(self) -> None: ...
    def on_mouse_leave(self) -> None: ...
    def on_mouse_down(self, event: MouseEvent) -> None: ...
    def on_mouse_up(self, event: MouseEvent) -> None: ...
    def on_mouse_motion(self, event: MouseEvent) -> None: ...
    def on_key_down(self, event: pygame.Event) -> None: ...
    def on_key_up(self, event: pygame.Event) -> None: ...
    def on_text_input(self, text: str) -> None: ...
    def on_focus(self) -> None: ...
    def on_blur(self) -> None: ...

    def update(self) -> None:
        """Called once per frame for time-based logic, e.g. cursor blinking."""

    @abstractmethod
    def draw(self) -> None:
        """Draw the widget on ``self.surface``. Children are drawn by WidgetHandler."""


def _ref(widget: WidgetBase | None) -> "weakref.ref[WidgetBase] | None":
    return weakref.ref(widget) if widget is not None else None


def _deref(ref: "weakref.ref[WidgetBase] | None") -> WidgetBase | None:
    """Widget behind ``ref``, or None if ``ref`` is None or the widget is gone."""
    return ref() if ref is not None else None


class WidgetHandler:
    """Global registry and event dispatcher for top-level widgets.

    Registry order is z-order: widgets later in the order are drawn on top and
    get the mouse first.
    """

    _widgets: OrderedWeakset[WidgetBase] = OrderedWeakset()

    _hover_path: list[weakref.ref[WidgetBase]] = []
    _captured: weakref.ref[WidgetBase] | None = None
    _focused: weakref.ref[WidgetBase] | None = None
    _mouse_pos: Point | None = None
    _disabled_by_ancestor: weakref.WeakSet[WidgetBase] = weakref.WeakSet()

    @staticmethod
    def add_widget(widget: WidgetBase) -> None:
        if widget not in WidgetHandler._widgets:
            WidgetHandler._widgets.add(widget)
            WidgetHandler.move_to_top(widget)

    @staticmethod
    def remove_widget(widget: WidgetBase) -> None:
        """Unregister a widget. Does nothing if it isn't registered."""
        WidgetHandler.forget(widget)
        WidgetHandler._widgets.discard(widget)

    @staticmethod
    def move_to_top(widget: WidgetBase) -> None:
        """Move a registered widget above all others, else raise ValueError."""
        try:
            WidgetHandler._widgets.move_to_end(widget)
        except KeyError:
            raise ValueError(f"{widget!r} is not registered in WidgetHandler") from None

    @staticmethod
    def move_to_bottom(widget: WidgetBase) -> None:
        """Move a registered widget below all others, else raise ValueError."""
        try:
            WidgetHandler._widgets.move_to_start(widget)
        except KeyError:
            raise ValueError(f"{widget!r} is not registered in WidgetHandler") from None

    @staticmethod
    def get_widgets() -> list[WidgetBase]:
        return list(WidgetHandler._widgets)

    @staticmethod
    def path_at(pos: Point) -> list[WidgetBase]:
        """Path from a top-level widget to the deepest widget at window-space ``pos``."""
        for widget in reversed(WidgetHandler.get_widgets()):
            path = widget.path_at(pos)
            if path:
                return path
        return []

    @staticmethod
    def widget_at(pos: Point) -> WidgetBase | None:
        """Deepest widget at window-space ``pos``, or None."""
        path = WidgetHandler.path_at(pos)
        return path[-1] if path else None

    @staticmethod
    def get_hover_path() -> list[WidgetBase]:
        """Widgets under the mouse as of the last update, from top-level to deepest."""
        widgets = (ref() for ref in WidgetHandler._hover_path)
        return [widget for widget in widgets if widget is not None]

    @staticmethod
    def get_hovered() -> WidgetBase | None:
        """Deepest widget under the mouse, or None."""
        path = WidgetHandler.get_hover_path()
        return path[-1] if path else None

    @staticmethod
    def is_hovered(widget: WidgetBase) -> bool:
        return widget in WidgetHandler.get_hover_path()

    @staticmethod
    def get_captured() -> WidgetBase | None:
        """Widget that got the current mouse press, or None.

        It receives motion and release events until the button is released.
        """
        return _deref(WidgetHandler._captured)

    @staticmethod
    def get_focused() -> WidgetBase | None:
        return _deref(WidgetHandler._focused)

    @staticmethod
    def is_focused(widget: WidgetBase) -> bool:
        return widget is WidgetHandler.get_focused()

    @staticmethod
    def set_focus(widget: WidgetBase | None) -> None:
        """Give keyboard focus to ``widget`` (None clears it); calls on_blur/on_focus."""
        old = WidgetHandler.get_focused()
        if widget is old:
            return
        WidgetHandler._focused = _ref(widget)
        if old is not None:
            old.on_blur()
        if widget is not None:
            widget.on_focus()

    @staticmethod
    def forget(widget: WidgetBase) -> None:
        """Drop capture and focus from ``widget`` and its descendants.

        Called when the widget is hidden, disabled or removed. Hover needs no reset:
        ``main`` recomputes it every frame.
        """
        tree = list(widget.iter_tree())
        if WidgetHandler.get_captured() in tree:
            WidgetHandler._captured = None
        if WidgetHandler.get_focused() in tree:
            WidgetHandler.set_focus(None)

    @staticmethod
    def main(events: list[pygame.Event]) -> None:
        """Run one frame: dispatch events, refresh hover, update widgets, draw them.

        Widgets are drawn bottom to top; hidden ones are skipped with their children.
        """
        for event in events:
            WidgetHandler.dispatch(event)

        WidgetHandler._update_disabled()
        WidgetHandler._update_hover()

        widgets = WidgetHandler.get_widgets()
        for widget in widgets:
            for node in widget.iter_tree():
                node.update()
        for widget in widgets:
            WidgetHandler._draw_tree(widget)

    @staticmethod
    def _draw_tree(widget: WidgetBase) -> None:
        """Draw a visible widget, then its children on top of it."""
        if not widget.is_visible():
            return
        widget.draw()
        for child in widget.children():
            WidgetHandler._draw_tree(child)

    @staticmethod
    def dispatch(event: pygame.Event) -> None:
        """Send one pygame event to the widget it is meant for."""
        if event.type == pygame.MOUSEMOTION:
            WidgetHandler._mouse_pos = event.pos
            WidgetHandler._update_hover()
            target = WidgetHandler.get_captured() or WidgetHandler.get_hovered()
            if target is not None and target.is_enabled():
                mouse_event = MouseEvent(
                    target.to_local(event.pos),
                    mod=pygame.key.get_mods(),
                )
                target.on_mouse_motion(mouse_event)

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button in (4, 5):
                return
            WidgetHandler._mouse_pos = event.pos
            target = WidgetHandler.widget_at(event.pos)
            if target is not None and not target.is_enabled():
                target = None
            WidgetHandler._captured = _ref(target)
            WidgetHandler.set_focus(
                target if target is not None and target.focusable else None
            )
            if target is not None:
                mouse_event = MouseEvent(
                    target.to_local(event.pos),
                    event.button,
                    event.clicks,
                    pygame.key.get_mods(),
                )
                target.on_mouse_down(mouse_event)

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button in (4, 5):
                return
            WidgetHandler._mouse_pos = event.pos
            WidgetHandler._update_hover()
            target = WidgetHandler.get_captured()
            WidgetHandler._captured = None
            if target is not None:
                mouse_event = MouseEvent(
                    target.to_local(event.pos),
                    event.button,
                    event.clicks,
                    pygame.key.get_mods(),
                )
                target.on_mouse_up(mouse_event)

        elif event.type == pygame.WINDOWLEAVE:
            WidgetHandler._mouse_pos = None

        elif event.type in (pygame.KEYDOWN, pygame.KEYUP, pygame.TEXTINPUT):
            target = WidgetHandler.get_focused()
            if target is None:
                return
            if event.type == pygame.KEYDOWN:
                target.on_key_down(event)
            elif event.type == pygame.KEYUP:
                target.on_key_up(event)
            elif event.type == pygame.TEXTINPUT:
                target.on_text_input(event.text)

    @staticmethod
    def _update_hover() -> None:
        """Recompute the hover path and notify widgets that left or entered it."""
        new = (
            WidgetHandler.path_at(WidgetHandler._mouse_pos)
            if WidgetHandler._mouse_pos is not None
            else []
        )
        old = WidgetHandler.get_hover_path()
        WidgetHandler._hover_path = [weakref.ref(widget) for widget in new]
        for widget in reversed(old):
            if widget not in new and widget.is_enabled():
                widget.on_mouse_leave()
        for widget in new:
            if widget not in old and widget.is_enabled():
                widget.on_mouse_enter()

    @staticmethod
    def _update_disabled() -> None:
        """Remember widgets that have a disabled ancestor."""
        inherited = weakref.WeakSet()

        def walk(widget: WidgetBase, ancestor_disabled: bool) -> None:
            if ancestor_disabled:
                inherited.add(widget)
            for child in widget.children():
                walk(child, ancestor_disabled or widget._disabled)

        for widget in WidgetHandler.get_widgets():
            walk(widget, False)
        WidgetHandler._disabled_by_ancestor = inherited
