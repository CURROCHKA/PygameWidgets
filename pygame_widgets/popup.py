import tkinter as tk
from enum import Enum
from tkinter import messagebox

import pygame

import pygame_widgets
from pygame_widgets.widget import WidgetBase

tk.Tk().wm_withdraw()


class PopupType(Enum):
    INFO = 0
    ERROR = 1
    WARNING = 2
    QUESTION = 3
    OK_CANCEL = 4
    YES_NO = 5
    YES_NO_CANCEL = 6
    RETRY_CANCEL = 7


class Popup(WidgetBase):
    def __init__(
        self,
        win: pygame.Surface,
        x: int,
        y: int,
        width: int,
        height: int,
        popup_type: PopupType,
        title: str,
        text: str,
        trigger=lambda *args: None,
        *buttons,
        **kwargs,
    ):
        super().__init__(win, x, y, width, height)
        self.popup_type = popup_type
        self.title = title
        self.text = text
        self.trigger = trigger
        self.buttons = buttons

        self.margin = kwargs.get("margin", 20)

        self.title_color = kwargs.get("title_color", (0, 0, 0))
        self.title_size = kwargs.get("title_size", 40)
        self.title_font = kwargs.get(
            "title_font", pygame.font.SysFont("calibri", self.title_size, True)
        )
        self.title_rect = self.align_title_rect()

        self.text_color = kwargs.get("text_color", (0, 0, 0))
        self.text_size = kwargs.get("text_size", 18)
        self.text_font = kwargs.get(
            "text_font", pygame.font.SysFont("calibri", self.text_size)
        )
        self.text_rect = self.align_text_rect()

        self.radius = kwargs.get("radius", 0)

        self.color = kwargs.get("color", (150, 150, 150))
        self.shadow_distance = kwargs.get("shadow_distance", 0)
        self.shadow_color = kwargs.get("shadow_color", (210, 210, 180))

        self.result = None

        self.hide()

    def align_title_rect(self):
        return pygame.Rect(
            self._x + self.margin,
            self._y + self.margin,
            self._width - self.margin * 2,
            self._height // 3 - self.margin * 2,
        )

    def align_text_rect(self):
        return pygame.Rect(
            self._x + self.margin,
            self._y + self._height // 3,
            self._width - self.margin * 2,
            self._height // 2 - self.margin * 2,
        )

    def listen(self, events):
        if self.trigger():
            self.show()
            messagebox.showinfo(self.title, self.text)

    def draw(self):
        pass

    def show(self):
        super().show()
        match self.popup_type:
            case PopupType.INFO:
                messagebox.showinfo(self.title, self.text)
            case PopupType.ERROR:
                messagebox.showerror(self.title, self.text)
            case PopupType.WARNING:
                messagebox.showwarning(self.title, self.text)
            case PopupType.QUESTION:
                self.result = messagebox.askquestion(self.title, self.text)
            case PopupType.OK_CANCEL:
                self.result = messagebox.askokcancel(self.title, self.text)
            case PopupType.YES_NO:
                self.result = messagebox.askyesno(self.title, self.text)
            case PopupType.YES_NO_CANCEL:
                self.result = messagebox.askyesnocancel(self.title, self.text)
            case PopupType.RETRY_CANCEL:
                self.result = messagebox.askretrycancel(self.title, self.text)

    def get_result(self):
        return self.result


if __name__ == "__main__":
    import sys

    from pygame_widgets.button import Button

    def set_button_color():
        if popup.get_result():
            button.set_inactive_color("green")
        elif popup.get_result() == False:
            button.set_inactive_color("red")

    pygame.init()
    win = pygame.display.set_mode((600, 600))

    popup = Popup(
        win,
        100,
        100,
        400,
        400,
        PopupType.YES_NO,
        "Popup",
        "This is the text in the popup. Would you like to continue? The buttons below can be customised.",
        radius=20,
        text_size=20,
    )

    button = Button(win, 100, 100, 400, 400, text="Popup", on_click=popup.show)

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
        set_button_color()
