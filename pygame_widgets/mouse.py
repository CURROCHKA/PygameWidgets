import time
from enum import Enum

import pygame


class MouseState(Enum):
    HOVER = 0
    CLICK = 1
    RIGHT_CLICK = 2
    DRAG = 3
    RIGHT_DRAG = 4
    RELEASE = 5
    RIGHT_RELEASE = 6
    DOUBLE_CLICK = 7
    DOUBLE_RIGHT_CLICK = 8
    TRIPLE_CLICK = 9
    TRIPLE_RIGHT_CLICK = 10
    WHEEL_CLICK = 11
    WHEEL_RELEASE = 12
    WHEEL_DRAG = 13
    WHEEL_MOTION = 14


class Mouse:
    _refresh_time = 0.01
    _multi_click_threshold = 0.4
    _multi_click_radius = 5

    last_left_click = 0
    last_right_click = 0
    left_click_elapsed_time = 0
    right_click_elapsed_time = 0
    _left_click_count = 0
    _right_click_count = 0
    _last_left_click_pos = (0, 0)
    _last_right_click_pos = (0, 0)

    # Wheel scroll accumulated by handleEvent, consumed once per frame
    _wheel_delta = 0
    _pending_wheel_delta = 0

    _mouse_state = MouseState.HOVER

    @staticmethod
    def listen():
        listening = True
        while listening:
            try:
                Mouse.update_mouse_state()
            except pygame.error:
                listening = False
            time.sleep(Mouse._refresh_time)

    @staticmethod
    def update_mouse_state():
        mouse_pressed = pygame.mouse.get_pressed()
        left_pressed = mouse_pressed[0]
        wheel_pressed = mouse_pressed[1]
        right_pressed = mouse_pressed[2]

        # Consume scroll accumulated since last frame. Scroll is instantaneous:
        # it lives for exactly one frame and never "sticks".
        scrolled = Mouse._pending_wheel_delta != 0
        Mouse._wheel_delta = Mouse._pending_wheel_delta
        Mouse._pending_wheel_delta = 0

        if scrolled:
            Mouse._mouse_state = MouseState.WHEEL_MOTION
            return

        if left_pressed:
            Mouse._mouse_state = (
                MouseState.DRAG
                if Mouse._mouse_state in (MouseState.CLICK, MouseState.DRAG)
                else MouseState.CLICK
            )

        elif wheel_pressed:
            Mouse._mouse_state = (
                MouseState.WHEEL_DRAG
                if Mouse._mouse_state in (MouseState.WHEEL_CLICK, MouseState.WHEEL_DRAG)
                else MouseState.WHEEL_CLICK
            )

        elif right_pressed:
            Mouse._mouse_state = (
                MouseState.RIGHT_DRAG
                if Mouse._mouse_state in (MouseState.RIGHT_CLICK, MouseState.RIGHT_DRAG)
                else MouseState.RIGHT_CLICK
            )

        else:
            # Button(s) released this frame -> resolve final state
            if Mouse._mouse_state in (MouseState.CLICK, MouseState.DRAG):
                Mouse._register_left_release()
            elif Mouse._mouse_state in (MouseState.WHEEL_CLICK, MouseState.WHEEL_DRAG):
                Mouse._mouse_state = MouseState.WHEEL_RELEASE
            elif Mouse._mouse_state in (MouseState.RIGHT_CLICK, MouseState.RIGHT_DRAG):
                Mouse._register_right_release()
            else:
                Mouse._expire_click_counters()
                Mouse._mouse_state = MouseState.HOVER

    @staticmethod
    def _is_within_radius(pos1, pos2) -> bool:
        dx = pos1[0] - pos2[0]
        dy = pos1[1] - pos2[1]
        return (
            dx * dx + dy * dy <= Mouse._multi_click_radius * Mouse._multi_click_radius
        )

    @staticmethod
    def _register_left_release():
        now = time.time()
        pos = pygame.mouse.get_pos()

        in_time = now - Mouse.last_left_click <= Mouse._multi_click_threshold
        in_place = Mouse._is_within_radius(pos, Mouse._last_left_click_pos)
        if in_time and in_place:
            Mouse._left_click_count += 1
        else:
            Mouse._left_click_count = 1
        Mouse.last_left_click = now
        Mouse._last_left_click_pos = pos

        if Mouse._left_click_count >= 3:
            Mouse._mouse_state = MouseState.TRIPLE_CLICK
            Mouse._left_click_count = 0
        elif Mouse._left_click_count == 2:
            Mouse._mouse_state = MouseState.DOUBLE_CLICK
        else:
            Mouse._mouse_state = MouseState.RELEASE

    @staticmethod
    def _register_right_release():
        now = time.time()
        pos = pygame.mouse.get_pos()

        in_time = now - Mouse.last_right_click <= Mouse._multi_click_threshold
        in_place = Mouse._is_within_radius(pos, Mouse._last_right_click_pos)
        if in_time and in_place:
            Mouse._right_click_count += 1
        else:
            Mouse._right_click_count = 1
        Mouse.last_right_click = now
        Mouse._last_right_click_pos = pos

        if Mouse._right_click_count >= 3:
            Mouse._mouse_state = MouseState.TRIPLE_RIGHT_CLICK
            Mouse._right_click_count = 0
        elif Mouse._right_click_count == 2:
            Mouse._mouse_state = MouseState.DOUBLE_RIGHT_CLICK
        else:
            Mouse._mouse_state = MouseState.RIGHT_RELEASE

    @staticmethod
    def _expire_click_counters():
        now = time.time()
        if (
            Mouse._left_click_count
            and now - Mouse.last_left_click > Mouse._multi_click_threshold
        ):
            Mouse._left_click_count = 0
        if (
            Mouse._right_click_count
            and now - Mouse.last_right_click > Mouse._multi_click_threshold
        ):
            Mouse._right_click_count = 0

    @staticmethod
    def handle_events(events: list[pygame.Event]):
        """Feed pygame events here so wheel scroll can be tracked.

        Only scroll needs the event queue; the middle-button click/drag/release
        is handled by polling in update_mouse_state, like the left/right buttons.
        """
        for event in events:
            if event.type == pygame.MOUSEWHEEL:
                Mouse._pending_wheel_delta = event.y

    @staticmethod
    def update_elapsed_time():
        if Mouse._mouse_state in (MouseState.CLICK, MouseState.DRAG):
            Mouse.left_click_elapsed_time = time.time() - Mouse.last_left_click
        elif Mouse._mouse_state in (MouseState.RIGHT_CLICK, MouseState.RIGHT_DRAG):
            Mouse.right_click_elapsed_time = time.time() - Mouse.last_right_click

    @staticmethod
    def get_mouse_state() -> MouseState:
        return Mouse._mouse_state

    @staticmethod
    def get_mouse_pos() -> tuple[int, int]:
        return pygame.mouse.get_pos()

    @staticmethod
    def get_wheel_delta() -> int:
        """Scroll amount for the current frame (valid while state is WHEEL_MOTION)."""
        return Mouse._wheel_delta

    @staticmethod
    def set_refresh_rate_per_sec(refresh_rate):
        Mouse._refresh_time = 1 / refresh_rate if refresh_rate != 0 else 0

    @staticmethod
    def set_multi_click_threshold(seconds):
        Mouse._multi_click_threshold = max(0.0, seconds)

    @staticmethod
    def set_multi_click_radius(pixels):
        Mouse._multi_click_radius = max(0, pixels)


if __name__ == "__main__":
    import sys

    pygame.init()
    win = pygame.display.set_mode((600, 600))

    Mouse.set_multi_click_threshold(0.4)
    Mouse.set_multi_click_radius(5)

    run = True
    while run:
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                pygame.quit()
                run = False
                sys.exit()

            Mouse.handleEvent(event)

        win.fill((255, 255, 255))

        Mouse.update_mouse_state()

        state = Mouse.get_mouse_state()
        print(state, "wheel:", Mouse.get_wheel_delta())

        pygame.display.update()
        time.sleep(0.1)
