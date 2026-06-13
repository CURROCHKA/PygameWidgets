from enum import Enum
import pygame
import time


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
    _refreshTime = 0.01
    _multiClickThreshold = 0.4
    _multiClickRadius = 5

    lastLeftClick = 0
    lastRightClick = 0
    leftClickElapsedTime = 0
    rightClickElapsedTime = 0
    _leftClickCount = 0
    _rightClickCount = 0
    _lastLeftClickPos = (0, 0)
    _lastRightClickPos = (0, 0)

    # Wheel scroll accumulated by handleEvent, consumed once per frame
    _wheelDelta = 0
    _pendingWheelDelta = 0

    _mouseState = MouseState.HOVER

    @staticmethod
    def listen():
        listening = True
        while listening:
            try:
                Mouse.updateMouseState()
            except pygame.error:
                listening = False
            time.sleep(Mouse._refreshTime)

    @staticmethod
    def updateMouseState():
        mousePressed = pygame.mouse.get_pressed()
        leftPressed = mousePressed[0]
        wheelPressed = mousePressed[1]
        rightPressed = mousePressed[2]

        # Consume scroll accumulated since last frame. Scroll is instantaneous:
        # it lives for exactly one frame and never "sticks".
        scrolled = Mouse._pendingWheelDelta != 0
        Mouse._wheelDelta = Mouse._pendingWheelDelta
        Mouse._pendingWheelDelta = 0

        if scrolled:
            Mouse._mouseState = MouseState.WHEEL_MOTION
            return

        if leftPressed:
            Mouse._mouseState = (
                MouseState.DRAG
                if Mouse._mouseState in (MouseState.CLICK, MouseState.DRAG)
                else MouseState.CLICK
            )

        elif wheelPressed:
            Mouse._mouseState = (
                MouseState.WHEEL_DRAG
                if Mouse._mouseState in (MouseState.WHEEL_CLICK, MouseState.WHEEL_DRAG)
                else MouseState.WHEEL_CLICK
            )

        elif rightPressed:
            Mouse._mouseState = (
                MouseState.RIGHT_DRAG
                if Mouse._mouseState in (MouseState.RIGHT_CLICK, MouseState.RIGHT_DRAG)
                else MouseState.RIGHT_CLICK
            )

        else:
            # Button(s) released this frame -> resolve final state
            if Mouse._mouseState in (MouseState.CLICK, MouseState.DRAG):
                Mouse._registerLeftRelease()
            elif Mouse._mouseState in (MouseState.WHEEL_CLICK, MouseState.WHEEL_DRAG):
                Mouse._mouseState = MouseState.WHEEL_RELEASE
            elif Mouse._mouseState in (MouseState.RIGHT_CLICK, MouseState.RIGHT_DRAG):
                Mouse._registerRightRelease()
            else:
                Mouse._expireClickCounters()
                Mouse._mouseState = MouseState.HOVER

    @staticmethod
    def _isWithinRadius(pos1, pos2) -> bool:
        dx = pos1[0] - pos2[0]
        dy = pos1[1] - pos2[1]
        return dx * dx + dy * dy <= Mouse._multiClickRadius * Mouse._multiClickRadius

    @staticmethod
    def _registerLeftRelease():
        now = time.time()
        pos = pygame.mouse.get_pos()

        inTime = now - Mouse.lastLeftClick <= Mouse._multiClickThreshold
        inPlace = Mouse._isWithinRadius(pos, Mouse._lastLeftClickPos)
        if inTime and inPlace:
            Mouse._leftClickCount += 1
        else:
            Mouse._leftClickCount = 1
        Mouse.lastLeftClick = now
        Mouse._lastLeftClickPos = pos

        if Mouse._leftClickCount >= 3:
            Mouse._mouseState = MouseState.TRIPLE_CLICK
            Mouse._leftClickCount = 0
        elif Mouse._leftClickCount == 2:
            Mouse._mouseState = MouseState.DOUBLE_CLICK
        else:
            Mouse._mouseState = MouseState.RELEASE

    @staticmethod
    def _registerRightRelease():
        now = time.time()
        pos = pygame.mouse.get_pos()

        inTime = now - Mouse.lastRightClick <= Mouse._multiClickThreshold
        inPlace = Mouse._isWithinRadius(pos, Mouse._lastRightClickPos)
        if inTime and inPlace:
            Mouse._rightClickCount += 1
        else:
            Mouse._rightClickCount = 1
        Mouse.lastRightClick = now
        Mouse._lastRightClickPos = pos

        if Mouse._rightClickCount >= 3:
            Mouse._mouseState = MouseState.TRIPLE_RIGHT_CLICK
            Mouse._rightClickCount = 0
        elif Mouse._rightClickCount == 2:
            Mouse._mouseState = MouseState.DOUBLE_RIGHT_CLICK
        else:
            Mouse._mouseState = MouseState.RIGHT_RELEASE

    @staticmethod
    def _expireClickCounters():
        now = time.time()
        if (
            Mouse._leftClickCount
            and now - Mouse.lastLeftClick > Mouse._multiClickThreshold
        ):
            Mouse._leftClickCount = 0
        if (
            Mouse._rightClickCount
            and now - Mouse.lastRightClick > Mouse._multiClickThreshold
        ):
            Mouse._rightClickCount = 0

    @staticmethod
    def handleEvents(events: list[pygame.Event]):
        """Feed pygame events here so wheel scroll can be tracked.

        Only scroll needs the event queue; the middle-button click/drag/release
        is handled by polling in updateMouseState, like the left/right buttons.
        """
        for event in events:
            if event.type == pygame.MOUSEWHEEL:
                Mouse._pendingWheelDelta = event.y

    @staticmethod
    def updateElapsedTime():
        if Mouse._mouseState in (MouseState.CLICK, MouseState.DRAG):
            Mouse.leftClickElapsedTime = time.time() - Mouse.lastLeftClick
        elif Mouse._mouseState in (MouseState.RIGHT_CLICK, MouseState.RIGHT_DRAG):
            Mouse.rightClickElapsedTime = time.time() - Mouse.lastRightClick

    @staticmethod
    def getMouseState() -> MouseState:
        return Mouse._mouseState

    @staticmethod
    def getMousePos() -> tuple[int, int]:
        return pygame.mouse.get_pos()

    @staticmethod
    def getWheelDelta() -> int:
        """Scroll amount for the current frame (valid while state is WHEEL_MOTION)."""
        return Mouse._wheelDelta

    @staticmethod
    def setRefreshRatePerSec(refreshRate):
        Mouse._refreshTime = 1 / refreshRate if refreshRate != 0 else 0

    @staticmethod
    def setMultiClickThreshold(seconds):
        Mouse._multiClickThreshold = max(0.0, seconds)

    @staticmethod
    def setMultiClickRadius(pixels):
        Mouse._multiClickRadius = max(0, pixels)


if __name__ == '__main__':
    pygame.init()
    win = pygame.display.set_mode((600, 600))

    Mouse.setMultiClickThreshold(0.4)
    Mouse.setMultiClickRadius(5)

    run = True
    while run:
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                pygame.quit()
                run = False
                quit()

            Mouse.handleEvent(event)

        win.fill((255, 255, 255))

        Mouse.updateMouseState()

        state = Mouse.getMouseState()
        print(state, "wheel:", Mouse.getWheelDelta())

        pygame.display.update()
        time.sleep(0.1)
