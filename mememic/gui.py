"""Tkinter-интерфейс войс-ченджера MemeMic."""

from __future__ import annotations

import math
import os
import sys
import time
import tkinter as tk
import traceback
import webbrowser
from tkinter import font as tkfont
from tkinter import messagebox, simpledialog, ttk

from . import __version__, config, devices as dev_mod, dsp
from .engine import AudioEngine, LATENCY_MODES
from .icon import ICON_PNG_BASE64


def log(msg: str) -> None:
    """Пишем диагностику в %APPDATA%\\MemeMic\\log.txt."""
    try:
        path = config.settings_path().with_name("log.txt")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except OSError:
        pass


def crash_path():
    """Файл с подробностями падения — рядом с log.txt."""
    return config.settings_path().with_name("crash.txt")


def write_crash(title: str, text: str) -> None:
    """Сохраняем traceback, чтобы ошибку было видно даже у windowed-exe."""
    try:
        path = crash_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"===== {time.strftime('%Y-%m-%d %H:%M:%S')} {title} =====\n")
            fh.write(text.rstrip() + "\n\n")
    except OSError:
        pass
    try:
        print(f"MemeMic: {title}\n{text}", file=sys.stderr)
    except Exception:
        pass


def show_startup_error(title: str, text: str) -> None:
    """Диалог с ошибкой запуска; если messagebox недоступен — молчим."""
    try:
        messagebox.showerror(
            "MemeMic — ошибка запуска",
            f"{title}\n\n{text.strip().splitlines()[-1]}\n\n"
            f"Подробности: {crash_path()}",
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Палитра
# ---------------------------------------------------------------------------

BG = "#0F1118"
BG_SOFT = "#141722"
CARD = "#1B1E2B"
CARD_HOVER = "#232738"
CARD_ACTIVE = "#262B3E"
CARD_ALT = "#2A2F42"
BORDER = "#30364A"
FG = "#F4F6FC"
MUTED = "#9AA1B8"
MUTED_DARK = "#6F768C"
ACCENT = "#7C5CFF"
ACCENT_HOVER = "#6A4BF0"
ACCENT_SOFT = "#2A2350"
GREEN = "#3DDC97"
YELLOW = "#F5C451"
RED = "#FF6B7A"

FILTER_CHOICES = {
    "Нет": "none",
    "Телефон": "phone",
    "Глухой": "muffled",
    "Тонкий": "thin",
}
FILTER_TO_LABEL = {v: k for k, v in FILTER_CHOICES.items()}

HUM_CHOICES = {
    "Выкл": "off",
    "50 Гц": "50",
    "60 Гц": "60",
}
HUM_TO_LABEL = {v: k for k, v in HUM_CHOICES.items()}

LATENCY_LABELS = {
    "low": "Низкая",
    "balanced": "Сбалансированная",
    "safe": "Надёжная",
}
LATENCY_KEYS = {v: k for k, v in LATENCY_LABELS.items()}

HUM_FILTER_MODES = dsp.HumFilter.MODES

PRESET_META = {
    "Без эффектов": {
        "glyph": "○",
        "desc": "Чистый голос без обработки",
        "color": "#5B8DEF",
    },
    "Робот": {
        "glyph": "⚙",
        "desc": "Металлический голос из космоса",
        "color": "#7C5CFF",
    },
    "Демон": {
        "glyph": "☠",
        "desc": "Низкий, хриплый и зловещий",
        "color": "#E05252",
    },
    "Бурундук": {
        "glyph": "♪",
        "desc": "Высокий и суетливый",
        "color": "#F0A64A",
    },
    "Телефон": {
        "glyph": "☎",
        "desc": "Звонок из прошлого века",
        "color": "#4FC3A1",
    },
    "Пещера": {
        "glyph": "☾",
        "desc": "Гулкое эхо в темноте",
        "color": "#5C7CFA",
    },
    "Инопланетянин": {
        "glyph": "☄",
        "desc": "Странный сигнал с орбиты",
        "color": "#9B6BFF",
    },
    "Монстр": {
        "glyph": "☣",
        "desc": "Рычащий и агрессивный",
        "color": "#D95C5C",
    },
    "Мистер, вы потеряли кошелёк": {
        "glyph": "₽",
        "desc": "Тот самый голос из мема",
        "color": "#E8B44A",
    },
}
USER_PRESET_META = {
    "glyph": "★",
    "desc": "Мой пресет",
    "color": "#58C7C7",
}


def _fmt_pitch(v: float) -> str:
    return "0 пт" if abs(v) < 0.05 else f"{v:+.1f} пт"


SLIDERS: dict[str, dict] = {
    "pitch": {
        "label": "Тон голоса",
        "lo": -12,
        "hi": 12,
        "step": 0.5,
        "scale": 1.0,
        "fmt": _fmt_pitch,
    },
    "robot_mix": {
        "label": "Робот",
        "lo": 0,
        "hi": 100,
        "step": 1,
        "scale": 0.01,
        "fmt": lambda v: f"{v:.0f}%",
    },
    "robot_freq": {
        "label": "Частота робота",
        "lo": 5,
        "hi": 120,
        "step": 1,
        "scale": 1.0,
        "fmt": lambda v: f"{v:.0f} Гц",
    },
    "echo_mix": {
        "label": "Эхо",
        "lo": 0,
        "hi": 100,
        "step": 1,
        "scale": 0.01,
        "fmt": lambda v: f"{v:.0f}%",
    },
    "echo_delay_ms": {
        "label": "Задержка эха",
        "lo": 40,
        "hi": 600,
        "step": 10,
        "scale": 1.0,
        "fmt": lambda v: f"{v:.0f} мс",
    },
    "echo_feedback": {
        "label": "Повторы эха",
        "lo": 0,
        "hi": 80,
        "step": 1,
        "scale": 0.01,
        "fmt": lambda v: f"{v:.0f}%",
    },
    "drive": {
        "label": "Драйв / хрип",
        "lo": 0,
        "hi": 100,
        "step": 1,
        "scale": 1.0,
        "fmt": lambda v: f"{v:.0f}%",
    },
    "gate_db": {
        "label": "Шум-гейт",
        "lo": -80,
        "hi": -20,
        "step": 1,
        "scale": 1.0,
        "fmt": lambda v: "выкл" if v <= -79 else f"{v:.0f} дБ",
    },
    "noise_reduction": {
        "label": "Шумоподавление",
        "lo": 0,
        "hi": 100,
        "step": 1,
        "scale": 0.01,
        "fmt": lambda v: "выкл" if v <= 0 else f"{v:.0f}%",
    },
    "highpass": {
        "label": "Срез низа",
        "lo": 0,
        "hi": 200,
        "step": 5,
        "scale": 1.0,
        "fmt": lambda v: "выкл" if v <= 0 else f"{v:.0f} Гц",
    },
    "volume": {
        "label": "Громкость",
        "lo": 0,
        "hi": 200,
        "step": 5,
        "scale": 0.01,
        "fmt": lambda v: f"{v:.0f}%",
    },
}


# ---------------------------------------------------------------------------
# Мелкие графические помощники
# ---------------------------------------------------------------------------


def _round_rect(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float,
    *,
    fill: str,
    outline: str = "",
    width: int = 1,
    tags: tuple[str, ...] = (),
) -> int:
    """Сглаженный прямоугольник на Canvas."""
    radius = max(0.0, min(radius, (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2,
        x1 + radius, y2,
        x1 + radius, y2, x1, y2, x1, y2 - radius,
        x1, y1 + radius,
        x1, y1 + radius, x1, y1, x1 + radius, y1,
    ]
    return canvas.create_polygon(
        points,
        smooth=True,
        splinesteps=28,
        fill=fill,
        outline=outline or fill,
        width=width,
        tags=tags,
    )


def _db_text(level: float) -> str:
    if level < 1e-5:
        return "—"
    db = 20.0 * math.log10(max(level, 1e-6))
    return f"{db:.0f}"


def _level_norm(level: float) -> float:
    if level <= 1e-6:
        return 0.0
    db = 20.0 * math.log10(level)
    return max(0.0, min(1.0, (db + 60.0) / 60.0))


# ---------------------------------------------------------------------------
# Виджеты
# ---------------------------------------------------------------------------


class RoundedCard(tk.Canvas):
    """Карточка со скруглёнными углами и внутренним Frame."""

    def __init__(
        self,
        parent,
        *,
        fill: str = CARD,
        outline: str = BORDER,
        radius: int = 18,
        padding: int = 16,
        expand: bool = False,
        bg: str = BG,
        **kwargs,
    ) -> None:
        super().__init__(
            parent, bg=bg, highlightthickness=0, bd=0, **kwargs
        )
        self.fill = fill
        self.outline = outline
        self.radius = radius
        self.padding = padding
        self.expand = expand
        self.body = tk.Frame(self, bg=fill)
        self._window = self.create_window(
            padding, padding, anchor="nw", window=self.body
        )
        self.bind("<Configure>", self._on_configure)
        self.body.bind("<Configure>", self._on_body)

    def _draw(self, width: int, height: int) -> None:
        self.delete("card")
        if width <= 2 or height <= 2:
            return
        if self.outline:
            _round_rect(
                self, 0, 0, width, height, self.radius,
                fill=self.outline, tags=("card",),
            )
            _round_rect(
                self, 1, 1, width - 1, height - 1, max(1, self.radius - 1),
                fill=self.fill, tags=("card",),
            )
        else:
            _round_rect(
                self, 0, 0, width, height, self.radius,
                fill=self.fill, tags=("card",),
            )
        self.tag_lower("card")

    def _on_configure(self, event: tk.Event) -> None:
        self._draw(event.width, event.height)
        inner_w = max(1, event.width - 2 * self.padding)
        if self.expand:
            inner_h = max(1, event.height - 2 * self.padding)
            self.itemconfigure(
                self._window, width=inner_w, height=inner_h
            )
        else:
            self.itemconfigure(self._window, width=inner_w)

    def _on_body(self, event: tk.Event) -> None:
        if self.expand:
            return
        height = event.height + 2 * self.padding
        if abs(int(self["height"]) - height) > 1:
            self.configure(height=height)
            self._draw(self.winfo_width(), height)


class PillButton(tk.Canvas):
    """Скруглённая кнопка с текстом."""

    def __init__(
        self,
        parent,
        text: str,
        command,
        *,
        width: int = 160,
        height: int = 40,
        fill: str = ACCENT,
        hover: str = ACCENT_HOVER,
        fg: str = "#FFFFFF",
        outline: str = "",
        font: tuple = ("Segoe UI Semibold", 10),
        bg: str = BG,
    ) -> None:
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.text = text
        self.command = command
        self.fill = fill
        self.hover = hover
        self.fg = fg
        self.outline = outline
        self.font = font
        self.enabled = True
        self._hovered = False
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Configure>", lambda _e: self._draw())
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width = int(self["width"])
        height = int(self["height"])
        fill = self.fill
        if not self.enabled:
            fill = "#2A2E3E"
        elif self._hovered:
            fill = self.hover
        _round_rect(
            self, 0.5, 0.5, width - 0.5, height - 0.5, height / 2.0,
            fill=fill, outline=self.outline or fill,
        )
        self.create_text(
            width / 2.0,
            height / 2.0,
            text=self.text,
            fill=self.fg if self.enabled else MUTED_DARK,
            font=self.font,
        )

    def _on_click(self, _event: tk.Event) -> None:
        if self.enabled and self.command is not None:
            self.command()

    def _on_enter(self, _event: tk.Event) -> None:
        self._hovered = True
        self._draw()

    def _on_leave(self, _event: tk.Event) -> None:
        self._hovered = False
        self._draw()

    def set_text(self, text: str) -> None:
        self.text = text
        self._draw()

    def set_colors(self, fill: str, hover: str) -> None:
        self.fill = fill
        self.hover = hover
        self._draw()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()


class StatusPill(tk.Canvas):
    """Маленький статус-индикатор в шапке."""

    def __init__(self, parent, *, bg: str = BG, height: int = 30) -> None:
        super().__init__(
            parent,
            height=height,
            width=150,
            bg=bg,
            highlightthickness=0,
            bd=0,
        )
        self.font = tkfont.Font(family="Segoe UI", size=9)
        self.text = ""
        self.color = MUTED
        self.set("Готово", MUTED)

    def set(self, text: str, color: str) -> None:
        self.text = text
        self.color = color
        width = self.font.measure(text) + 46
        self.configure(width=width)
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width = int(self["width"])
        height = int(self["height"])
        _round_rect(
            self, 0, 0, width, height, height / 2.0,
            fill=CARD_ALT, outline=BORDER,
        )
        self.create_oval(
            13, height / 2.0 - 4, 21, height / 2.0 + 4,
            fill=self.color, outline="",
        )
        self.create_text(
            29, height / 2.0,
            text=self.text,
            anchor="w",
            fill=FG,
            font=self.font,
        )


class LevelMeter(tk.Canvas):
    """Сегментированный индикатор уровня."""

    def __init__(
        self,
        parent,
        *,
        width: int = 180,
        height: int = 8,
        bg: str = CARD,
        segments: int = 28,
    ) -> None:
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=bg,
            highlightthickness=0,
            bd=0,
        )
        self.segments = segments
        self.display = 0.0
        self.bind("<Configure>", lambda _e: self._draw())

    def set_level(self, value: float) -> None:
        value = max(0.0, min(1.0, float(value)))
        if value >= self.display:
            self.display = value
        else:
            self.display = max(value, self.display - 0.07)
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width = self.winfo_width() or int(self["width"])
        height = self.winfo_height() or int(self["height"])
        gap = 2.0
        seg_w = max(2.0, (width - gap * (self.segments - 1)) / self.segments)
        for i in range(self.segments):
            x = i * (seg_w + gap)
            frac = (i + 1) / self.segments
            if frac <= self.display:
                if frac < 0.70:
                    color = GREEN
                elif frac < 0.90:
                    color = YELLOW
                else:
                    color = RED
            else:
                color = "#2B3042"
            _round_rect(
                self, x, 0, x + seg_w, height, height / 2.0,
                fill=color,
            )


class ScrollFrame(tk.Frame):
    """Прокручиваемая область."""

    def __init__(self, parent, *, bg: str = CARD) -> None:
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(
            self, bg=bg, highlightthickness=0, bd=0
        )
        self.scrollbar = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self.canvas.yview,
            style="Vertical.TScrollbar",
        )
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw"
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind("<Enter>", lambda _e: self.bind_wheel())
        self.canvas.bind("<Leave>", lambda _e: self.unbind_wheel())

    def _on_inner(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def bind_wheel(self) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def unbind_wheel(self) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120) * 3, "units")


class PresetCard(tk.Canvas):
    """Карточка пресета в левой колонке."""

    HEIGHT = 68

    def __init__(
        self,
        parent,
        name: str,
        meta: dict,
        command,
        *,
        is_user: bool = False,
        delete_command=None,
    ) -> None:
        super().__init__(
            parent,
            height=self.HEIGHT,
            bg=CARD,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.name = name
        self.meta = meta
        self.command = command
        self.is_user = is_user
        self.delete_command = delete_command
        self.active = False
        self.hovered = False
        self.fill = CARD

        self.avatar = tk.Canvas(
            self, width=44, height=44, bg=CARD,
            highlightthickness=0, bd=0,
        )
        self.avatar.place(x=12, y=12)

        self.name_label = tk.Label(
            self,
            text=name,
            bg=CARD,
            fg=FG,
            anchor="w",
            font=("Segoe UI Semibold", 9),
        )
        self.name_label.place(x=68, y=12, relwidth=1.0, width=-80)

        self.desc_label = tk.Label(
            self,
            text=meta["desc"],
            bg=CARD,
            fg=MUTED,
            anchor="w",
            font=("Segoe UI", 8),
        )
        self.desc_label.place(x=68, y=32, relwidth=1.0, width=-80)

        self.bind("<Configure>", lambda _e: self._draw())
        for widget in (
            self, self.avatar, self.name_label, self.desc_label
        ):
            widget.bind("<Button-1>", self._click)
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)
        if is_user:
            for widget in (
                self, self.avatar, self.name_label, self.desc_label
            ):
                widget.bind("<Button-3>", self._context_menu)

    def _draw(self) -> None:
        self.delete("bg")
        width = self.winfo_width() or 260
        height = self.HEIGHT
        if self.active:
            fill = CARD_ACTIVE
            outline = ACCENT
        elif self.hovered:
            fill = CARD_HOVER
            outline = BORDER
        else:
            fill = CARD
            outline = ""
        self.fill = fill
        if outline:
            _round_rect(
                self, 0, 0, width, height, 13,
                fill=outline, tags=("bg",),
            )
            _round_rect(
                self, 1, 1, width - 1, height - 1, 12,
                fill=fill, tags=("bg",),
            )
        else:
            _round_rect(
                self, 0, 0, width, height, 13,
                fill=fill, tags=("bg",),
            )
        if self.active:
            _round_rect(
                self, 1, 16, 4, height - 16, 2,
                fill=ACCENT, tags=("bg",),
            )
        self.tag_lower("bg")
        for widget in (
            self, self.avatar, self.name_label, self.desc_label
        ):
            try:
                widget.configure(bg=fill)
            except tk.TclError:
                pass
        self._draw_avatar()

    def _draw_avatar(self) -> None:
        self.avatar.delete("all")
        self.avatar.create_oval(
            2, 2, 42, 42, fill=self.meta["color"], outline=""
        )
        self.avatar.create_text(
            22, 21,
            text=self.meta["glyph"],
            fill="#FFFFFF",
            font=("Segoe UI Symbol", 16, "bold"),
        )
        if self.is_user:
            self.avatar.create_text(
                35, 34, text="★", fill="#FFFFFF",
                font=("Segoe UI Symbol", 7),
            )

    def _click(self, _event: tk.Event) -> None:
        if self.command:
            self.command(self.name)

    def _enter(self, _event: tk.Event) -> None:
        self.hovered = True
        self._draw()

    def _leave(self, _event: tk.Event) -> None:
        self.hovered = False
        self._draw()

    def set_active(self, active: bool) -> None:
        self.active = bool(active)
        self._draw()

    def _context_menu(self, event: tk.Event) -> None:
        if not self.delete_command:
            return
        menu = tk.Menu(
            self,
            tearoff=0,
            bg=CARD_ALT,
            fg=FG,
            activebackground=ACCENT,
            activeforeground="#FFFFFF",
            bd=0,
        )
        menu.add_command(
            label="Удалить пресет",
            command=lambda: self.delete_command(self.name),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()


# ---------------------------------------------------------------------------
# Приложение
# ---------------------------------------------------------------------------


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.settings = config.load_settings()
        self.engine = AudioEngine(str(self.settings.get("latency", "low")))
        self.params: dict = dict(dsp.DEFAULT_PARAMS)
        saved_params = self.settings.get("params")
        if isinstance(saved_params, dict):
            for key in self.params:
                if key in saved_params:
                    self.params[key] = saved_params[key]
        if self.params.get("filter") not in dsp.FILTER_MODES:
            self.params["filter"] = "none"
        if self.params.get("hum") not in HUM_FILTER_MODES:
            self.params["hum"] = "off"

        self.devices_in: list[dev_mod.DeviceInfo] = []
        self.devices_out: list[dev_mod.DeviceInfo] = []
        self.user_presets = config.load_user_presets()
        self.preset_var = tk.StringVar(value="Без эффектов")
        if self.settings.get("preset") in self._preset_names():
            self.preset_var.set(self.settings["preset"])

        self.vars: dict[str, tk.DoubleVar] = {}
        self.value_labels: dict[str, tk.Label] = {}
        self.preset_cards: dict[str, PresetCard] = {}
        self.running = False
        self._logged_underruns = 0
        self._updating = False
        self._search_placeholder = "Поиск голоса…"
        self._virtual_usb_note = ""

        self.root.title("MemeMic")
        try:
            self._icon = tk.PhotoImage(data=ICON_PNG_BASE64)
            self.root.iconphoto(True, self._icon)
            factor = max(1, self._icon.width() // 38)
            self._logo = (
                self._icon.subsample(factor) if factor > 1 else self._icon
            )
        except tk.TclError:
            self._icon = None
            self._logo = None
        self.root.configure(bg=BG)
        self.root.geometry("1200x820")
        self.root.minsize(1060, 780)

        self._build_style()
        self._build_ui()
        self._render_presets()
        self._refresh_devices()
        self._sync_widgets_from_params()
        self._set_active_preset(self.preset_var.get())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.report_callback_exception = self._on_callback_error
        self.root.after(60, self._tick)

    # ------------------------------------------------------------------
    # Оформление
    # ------------------------------------------------------------------
    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            ".", background=BG, foreground=FG, font=("Segoe UI", 9)
        )
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Card.TLabel", background=CARD, foreground=FG)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure(
            "CardMuted.TLabel", background=CARD, foreground=MUTED
        )

        style.configure(
            "TCombobox",
            fieldbackground=CARD_ALT,
            background=CARD_ALT,
            foreground=FG,
            arrowcolor=MUTED,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=6,
        )
        style.map(
            "TCombobox",
            fieldbackground=[
                ("readonly", CARD_ALT),
                ("disabled", "#202434"),
            ],
            foreground=[
                ("readonly", FG),
                ("disabled", MUTED_DARK),
            ],
            arrowcolor=[
                ("disabled", MUTED_DARK),
                ("active", FG),
            ],
            bordercolor=[("focus", ACCENT)],
        )

        style.configure(
            "TScale",
            background=CARD,
            troughcolor="#2E3448",
            bordercolor=CARD,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            sliderlength=14,
            sliderthickness=10,
            borderwidth=0,
        )
        style.map(
            "TScale",
            background=[("active", CARD)],
            troughcolor=[("active", "#353B52")],
        )

        style.configure(
            "TCheckbutton",
            background=CARD,
            foreground=FG,
            focuscolor=CARD,
            padding=2,
        )
        style.map(
            "TCheckbutton",
            background=[("active", CARD)],
            indicatorcolor=[
                ("selected", ACCENT),
                ("!selected", CARD_ALT),
            ],
        )

        style.configure(
            "Vertical.TScrollbar",
            background=CARD_ALT,
            troughcolor=CARD,
            bordercolor=CARD,
            arrowcolor=MUTED,
            width=9,
            arrowsize=9,
        )
        style.map(
            "Vertical.TScrollbar",
            background=[("active", ACCENT)],
        )

        self.root.option_add("*TCombobox*Listbox.background", CARD_ALT)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add(
            "*TCombobox*Listbox.selectBackground", ACCENT
        )
        self.root.option_add(
            "*TCombobox*Listbox.selectForeground", "#FFFFFF"
        )

    # ------------------------------------------------------------------
    # Интерфейс
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg=BG, padx=22, pady=18)
        outer.pack(fill="both", expand=True)

        self._build_header(outer)

        content = tk.Frame(outer, bg=BG)
        content.pack(fill="both", expand=True, pady=(14, 10))
        content.columnconfigure(0, weight=0, minsize=320)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        self._build_sidebar(content)
        self._build_main(content)
        self._build_footer(outer)

    def _build_header(self, parent: tk.Frame) -> None:
        header = tk.Frame(parent, bg=BG)
        header.pack(fill="x")

        if self._logo is not None:
            tk.Label(
                header, image=self._logo, bg=BG, bd=0
            ).pack(side="left", pady=(2, 0))
        else:
            tk.Label(
                header, text="M", bg=ACCENT, fg="#FFFFFF",
                font=("Segoe UI Bold", 18), width=2,
            ).pack(side="left")

        title = tk.Frame(header, bg=BG)
        title.pack(side="left", padx=(12, 0))
        tk.Label(
            title,
            text="MemeMic",
            bg=BG,
            fg=FG,
            font=("Segoe UI Semibold", 20),
        ).pack(anchor="w")
        tk.Label(
            title,
            text="VOICE CHANGER  ·  REAL-TIME",
            bg=BG,
            fg=MUTED_DARK,
            font=("Segoe UI", 7),
        ).pack(anchor="w")

        right = tk.Frame(header, bg=BG)
        right.pack(side="right")
        self.state_pill = StatusPill(right, bg=BG)
        self.state_pill.pack(side="right", pady=(4, 0))
        self.about_btn = PillButton(
            right,
            "?",
            self._about,
            width=34,
            height=34,
            fill=CARD_ALT,
            hover=CARD_HOVER,
            fg=FG,
            outline=BORDER,
            font=("Segoe UI Semibold", 11),
            bg=BG,
        )
        self.about_btn.pack(side="right", padx=(0, 8), pady=(2, 0))

    def _build_sidebar(self, parent: tk.Frame) -> None:
        card = RoundedCard(
            parent, fill=CARD, outline=BORDER, expand=True, padding=16
        )
        card.grid(
            row=0, column=0, sticky="nsew", padx=(0, 14)
        )
        body = card.body
        body.columnconfigure(0, weight=1)
        body.rowconfigure(4, weight=1)

        head = tk.Frame(body, bg=CARD)
        head.grid(row=0, column=0, sticky="ew")
        tk.Label(
            head,
            text="Голоса",
            bg=CARD,
            fg=FG,
            font=("Segoe UI Semibold", 14),
        ).pack(side="left")
        self.preset_count = tk.Label(
            head,
            text="0",
            bg=CARD_ALT,
            fg=MUTED,
            padx=8,
            pady=2,
            font=("Segoe UI", 8),
        )
        self.preset_count.pack(side="right")

        tk.Label(
            body,
            text="Нажми на карточку — голос применится сразу",
            bg=CARD,
            fg=MUTED_DARK,
            font=("Segoe UI", 8),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", pady=(2, 0))

        search = tk.Frame(
            body,
            bg=CARD_ALT,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
        )
        search.grid(row=2, column=0, sticky="ew", pady=(12, 10))
        tk.Label(
            search,
            text="⌕",
            bg=CARD_ALT,
            fg=MUTED,
            font=("Segoe UI Symbol", 13),
        ).pack(side="left", padx=(10, 0))
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            search,
            textvariable=self.search_var,
            bg=CARD_ALT,
            fg=MUTED,
            insertbackground=FG,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Segoe UI", 9),
        )
        self.search_entry.pack(
            side="left", fill="x", expand=True, padx=(6, 10), pady=7
        )
        self.search_entry.bind("<FocusIn>", self._search_focus_in)
        self.search_entry.bind("<FocusOut>", self._search_focus_out)
        self.search_var.set(self._search_placeholder)
        self.search_entry.configure(fg=MUTED)

        self.preset_scroll = ScrollFrame(body, bg=CARD)
        self.preset_scroll.grid(row=4, column=0, sticky="nsew")
        self.preset_list = self.preset_scroll.inner
        self.search_var.trace_add("write", lambda *_a: self._on_search())

        self.save_preset_btn = PillButton(
            body,
            "＋  Сохранить текущий голос",
            self._save_preset,
            width=288,
            height=38,
            fill=CARD_ALT,
            hover=CARD_HOVER,
            fg=FG,
            outline=BORDER,
            font=("Segoe UI Semibold", 9),
            bg=CARD,
        )
        self.save_preset_btn.grid(row=5, column=0, sticky="ew", pady=(10, 0))

    def _build_main(self, parent: tk.Frame) -> None:
        main = tk.Frame(parent, bg=BG)
        main.grid(row=0, column=1, sticky="nsew")

        self.hero_card = RoundedCard(
            main, fill=CARD, outline=BORDER, padding=20
        )
        self.hero_card.pack(fill="x")
        self._build_hero(self.hero_card.body)

        self.devices_card = RoundedCard(
            main, fill=CARD, outline=BORDER, padding=16
        )
        self.devices_card.pack(fill="x", pady=(12, 0))
        self._build_devices(self.devices_card.body)

        self.tune_card = RoundedCard(
            main, fill=CARD, outline=BORDER, padding=16, expand=True
        )
        self.tune_card.pack(fill="both", expand=True, pady=(12, 0))
        self._build_tuning(self.tune_card.body)

    def _build_hero(self, body: tk.Frame) -> None:
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=0)

        self.hero_avatar = tk.Canvas(
            body, width=88, height=88, bg=CARD,
            highlightthickness=0, bd=0,
        )
        self.hero_avatar.grid(
            row=0, column=0, rowspan=4, sticky="nw", padx=(0, 18)
        )

        tk.Label(
            body,
            text="ТЕКУЩИЙ ГОЛОС",
            bg=CARD,
            fg=MUTED_DARK,
            font=("Segoe UI", 7),
            anchor="w",
        ).grid(row=0, column=1, sticky="ew")

        self.hero_name = tk.Label(
            body,
            text="Без эффектов",
            bg=CARD,
            fg=FG,
            font=("Segoe UI Semibold", 20),
            anchor="w",
        )
        self.hero_name.grid(row=1, column=1, sticky="ew", pady=(1, 1))

        self.hero_desc = tk.Label(
            body,
            text="",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=380,
        )
        self.hero_desc.grid(row=2, column=1, sticky="ew")

        self.hero_tags = tk.Frame(body, bg=CARD)
        self.hero_tags.grid(
            row=3, column=1, sticky="w", pady=(9, 0)
        )

        controls = tk.Frame(body, bg=CARD)
        controls.grid(
            row=0, column=2, rowspan=4, sticky="e", padx=(20, 0)
        )
        self.start_btn = PillButton(
            controls,
            "▶   Старт",
            self._toggle,
            width=190,
            height=50,
            fill=ACCENT,
            hover=ACCENT_HOVER,
            fg="#FFFFFF",
            font=("Segoe UI Semibold", 11),
            bg=CARD,
        )
        self.start_btn.pack(anchor="e")
        self.hero_status = tk.Label(
            controls,
            text="Готово к запуску",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 8),
            anchor="e",
        )
        self.hero_status.pack(anchor="e", pady=(6, 0))

        meters = tk.Frame(controls, bg=CARD)
        meters.pack(anchor="e", pady=(10, 0))
        meters.columnconfigure(1, weight=1)
        self.in_meter = LevelMeter(
            meters, width=180, height=8, bg=CARD
        )
        self.out_meter = LevelMeter(
            meters, width=180, height=8, bg=CARD
        )
        self.in_db = tk.Label(
            meters, text="—", bg=CARD, fg=MUTED_DARK,
            font=("Consolas", 7), width=3, anchor="e",
        )
        self.out_db = tk.Label(
            meters, text="—", bg=CARD, fg=MUTED_DARK,
            font=("Consolas", 7), width=3, anchor="e",
        )
        for row, (text, meter, db_label) in enumerate(
            (
                ("Вход", self.in_meter, self.in_db),
                ("Выход", self.out_meter, self.out_db),
            )
        ):
            tk.Label(
                meters,
                text=text,
                bg=CARD,
                fg=MUTED_DARK,
                font=("Segoe UI", 7),
                width=5,
                anchor="w",
            ).grid(row=row, column=0, sticky="w", pady=1)
            meter.grid(row=row, column=1, sticky="ew", pady=1)
            db_label.grid(
                row=row, column=2, sticky="e", padx=(6, 0), pady=1
            )

    def _build_devices(self, body: tk.Frame) -> None:
        body.columnconfigure(1, weight=1)

        tk.Label(
            body,
            text="Устройства",
            bg=CARD,
            fg=FG,
            font=("Segoe UI Semibold", 11),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        tk.Label(
            body,
            text="Микрофон",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9),
            width=18,
            anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=3)
        self.in_var = tk.StringVar()
        self.in_combo = ttk.Combobox(
            body, textvariable=self.in_var, state="readonly"
        )
        self.in_combo.grid(
            row=1, column=1, sticky="ew", pady=3, padx=(0, 10)
        )

        self.refresh_btn = PillButton(
            body,
            "Обновить",
            self._refresh_devices,
            width=104,
            height=31,
            fill=CARD_ALT,
            hover=CARD_HOVER,
            fg=FG,
            outline=BORDER,
            font=("Segoe UI", 8),
            bg=CARD,
        )
        self.refresh_btn.grid(
            row=1, column=2, rowspan=2, sticky="ne", pady=3
        )

        tk.Label(
            body,
            text="Виртуальный выход",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9),
            width=18,
            anchor="w",
        ).grid(row=2, column=0, sticky="w", pady=3)
        self.out_var = tk.StringVar()
        self.out_combo = ttk.Combobox(
            body, textvariable=self.out_var, state="readonly"
        )
        self.out_combo.grid(
            row=2, column=1, sticky="ew", pady=3, padx=(0, 10)
        )

        bottom = tk.Frame(body, bg=CARD)
        bottom.grid(
            row=3, column=0, columnspan=3, sticky="ew", pady=(6, 0)
        )
        tk.Label(
            bottom,
            text="Задержка",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(side="left")
        self.latency_var = tk.StringVar(
            value=LATENCY_LABELS.get(self.engine.latency_mode, "Низкая")
        )
        self.latency_combo = ttk.Combobox(
            bottom,
            textvariable=self.latency_var,
            values=list(LATENCY_LABELS.values()),
            state="readonly",
            width=19,
        )
        self.latency_combo.pack(side="left", padx=(8, 12))
        self.latency_combo.bind(
            "<<ComboboxSelected>>", self._on_latency_change
        )

        self.virtual_badge = tk.Label(
            bottom,
            text="проверка…",
            bg=CARD_ALT,
            fg=MUTED,
            padx=8,
            pady=3,
            font=("Segoe UI", 8),
        )
        self.virtual_badge.pack(side="left")

        self.virtual_help_btn = tk.Button(
            bottom,
            text="Как включить",
            command=self._virtual_help,
            bg=CARD,
            fg=ACCENT,
            activebackground=CARD,
            activeforeground=FG,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 8, "underline"),
        )
        self.virtual_help_btn.pack(side="left", padx=(8, 0))

        self.mic_hint = tk.Label(
            bottom,
            text="",
            bg=CARD,
            fg=MUTED_DARK,
            font=("Segoe UI", 8),
            anchor="e",
        )
        self.mic_hint.pack(side="right")

    def _build_tuning(self, body: tk.Frame) -> None:
        head = tk.Frame(body, bg=CARD)
        head.pack(fill="x")
        tk.Label(
            head,
            text="Тонкая настройка",
            bg=CARD,
            fg=FG,
            font=("Segoe UI Semibold", 11),
        ).pack(side="left")
        self.reset_btn = PillButton(
            head,
            "Сбросить",
            self._reset_params,
            width=92,
            height=29,
            fill=CARD_ALT,
            hover=CARD_HOVER,
            fg=MUTED,
            outline=BORDER,
            font=("Segoe UI", 8),
            bg=CARD,
        )
        self.reset_btn.pack(side="right", padx=(8, 0))
        self.save_top_btn = PillButton(
            head,
            "Сохранить пресет",
            self._save_preset,
            width=140,
            height=29,
            fill=ACCENT_SOFT,
            hover="#352C63",
            fg=ACCENT,
            outline="#453A7A",
            font=("Segoe UI Semibold", 8),
            bg=CARD,
        )
        self.save_top_btn.pack(side="right")

        filters = tk.Frame(body, bg=CARD)
        filters.pack(fill="x", pady=(10, 8))
        tk.Label(
            filters,
            text="Фильтр",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 8),
        ).pack(side="left", padx=(0, 8))
        self.filter_buttons: dict[str, tk.Button] = {}
        for label, mode in FILTER_CHOICES.items():
            button = tk.Button(
                filters,
                text=label,
                command=lambda m=mode: self._on_filter(m),
                bg=CARD_ALT,
                fg=MUTED,
                activebackground=CARD_HOVER,
                activeforeground=FG,
                relief="flat",
                bd=0,
                padx=11,
                pady=5,
                cursor="hand2",
                font=("Segoe UI", 8),
            )
            button.pack(side="left", padx=(0, 5))
            self.filter_buttons[mode] = button

        grid = tk.Frame(body, bg=CARD)
        grid.pack(fill="both", expand=True)
        for column in range(3):
            grid.columnconfigure(column, weight=1, uniform="slider")

        rows = [
            ("pitch", "robot_mix", "robot_freq"),
            ("echo_mix", "echo_delay_ms", "echo_feedback"),
            ("drive", "gate_db", "volume"),
            ("noise_reduction", "highpass", "hum"),
        ]
        for row_index, keys in enumerate(rows):
            for column, key in enumerate(keys):
                if key == "hum":
                    block = self._make_hum_block(grid)
                else:
                    block = self._make_slider(grid, key)
                block.grid(
                    row=row_index,
                    column=column,
                    sticky="ew",
                    padx=(0, 14) if column < 2 else 0,
                    pady=(0, 7),
                )

        options = tk.Frame(body, bg=CARD)
        options.pack(fill="x", pady=(2, 0))
        self.bypass_var = tk.BooleanVar(
            value=bool(self.params.get("bypass", False))
        )
        ttk.Checkbutton(
            options,
            text="Пропускать звук без обработки (bypass)",
            variable=self.bypass_var,
            command=self._on_bypass,
        ).pack(side="left")

    def _make_slider(self, parent: tk.Frame, key: str) -> tk.Frame:
        spec = SLIDERS[key]
        block = tk.Frame(parent, bg=CARD)
        top = tk.Frame(block, bg=CARD)
        top.pack(fill="x")
        tk.Label(
            top,
            text=spec["label"],
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 8),
            anchor="w",
        ).pack(side="left")
        value_label = tk.Label(
            top,
            text="",
            bg=CARD,
            fg=ACCENT,
            font=("Consolas", 8),
            anchor="e",
        )
        value_label.pack(side="right")
        self.value_labels[key] = value_label

        var = tk.DoubleVar(value=0.0)
        self.vars[key] = var
        scale = ttk.Scale(
            block,
            from_=spec["lo"],
            to=spec["hi"],
            variable=var,
            orient="horizontal",
            command=lambda raw, k=key: self._on_slider(k, raw),
        )
        scale.pack(fill="x", pady=(1, 0))
        return block

    def _make_hum_block(self, parent: tk.Frame) -> tk.Frame:
        block = tk.Frame(parent, bg=CARD)
        tk.Label(
            block,
            text="Наводки сети",
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 8),
            anchor="w",
        ).pack(anchor="w")
        self.hum_var = tk.StringVar(
            value=HUM_TO_LABEL.get(
                str(self.params.get("hum", "off")), "Выкл"
            )
        )
        self.hum_combo = ttk.Combobox(
            block,
            textvariable=self.hum_var,
            values=list(HUM_CHOICES),
            state="readonly",
        )
        self.hum_combo.pack(fill="x", pady=(4, 0))
        self.hum_combo.bind(
            "<<ComboboxSelected>>", self._on_hum_change
        )
        return block

    def _build_footer(self, parent: tk.Frame) -> None:
        footer = tk.Frame(parent, bg=BG)
        footer.pack(fill="x")
        self.status_label = tk.Label(
            footer,
            text="Готово к запуску",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 8),
            anchor="w",
        )
        self.status_label.pack(side="left", fill="x", expand=True)
        tk.Label(
            footer,
            text=f"v{__version__}",
            bg=BG,
            fg=MUTED_DARK,
            font=("Segoe UI", 8),
        ).pack(side="right")
        tk.Button(
            footer,
            text="Папка настроек",
            command=self._open_settings_folder,
            bg=BG,
            fg=MUTED,
            activebackground=BG,
            activeforeground=FG,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 8, "underline"),
        ).pack(side="right", padx=(0, 12))

    # ------------------------------------------------------------------
    # Пресеты
    # ------------------------------------------------------------------
    def _preset_names(self) -> list[str]:
        names = list(dsp.PRESETS)
        names += [n for n in self.user_presets if n not in dsp.PRESETS]
        return names

    def _lookup_preset(self, name: str) -> dict:
        if name in dsp.PRESETS:
            return dsp.preset_params(name)
        params = dict(dsp.DEFAULT_PARAMS)
        params.update(self.user_presets.get(name, {}))
        return params

    def _preset_meta(self, name: str) -> dict:
        if name in PRESET_META:
            return PRESET_META[name]
        return USER_PRESET_META

    def _render_presets(self, query: str = "") -> None:
        for child in self.preset_list.winfo_children():
            child.destroy()
        self.preset_cards.clear()
        query = query.strip().lower()
        names = [
            name
            for name in self._preset_names()
            if not query or query in name.lower()
        ]
        self.preset_count.configure(text=str(len(self._preset_names())))
        if not names:
            tk.Label(
                self.preset_list,
                text="Ничего не найдено",
                bg=CARD,
                fg=MUTED_DARK,
                font=("Segoe UI", 9),
                pady=18,
            ).pack(fill="x")
        for name in names:
            card = PresetCard(
                self.preset_list,
                name,
                self._preset_meta(name),
                self._apply_preset_name,
                is_user=name in self.user_presets
                and name not in dsp.PRESETS,
                delete_command=self._delete_preset,
            )
            card.pack(fill="x", pady=(0, 7))
            card.set_active(name == self.preset_var.get())
            self.preset_cards[name] = card
            self._bind_wheel_recursive(card)
        self.preset_scroll.inner.update_idletasks()
        self.preset_scroll.canvas.configure(
            scrollregion=self.preset_scroll.canvas.bbox("all")
        )

    def _bind_wheel_recursive(self, widget) -> None:
        widget.bind("<MouseWheel>", self.preset_scroll._on_wheel)
        for child in widget.winfo_children():
            self._bind_wheel_recursive(child)

    def _on_search(self) -> None:
        text = self.search_var.get()
        if text == self._search_placeholder:
            text = ""
        self._render_presets(text)

    def _search_focus_in(self, _event: tk.Event) -> None:
        if self.search_var.get() == self._search_placeholder:
            self.search_var.set("")
            self.search_entry.configure(fg=FG)

    def _search_focus_out(self, _event: tk.Event) -> None:
        if not self.search_var.get().strip():
            self.search_var.set(self._search_placeholder)
            self.search_entry.configure(fg=MUTED)

    def _apply_preset_name(self, name: str) -> None:
        fresh = self._lookup_preset(name)
        bypass = bool(self.params.get("bypass", False))
        self.params.update(fresh)
        self.params["bypass"] = bypass
        self.engine.set_params(self.params)
        self.preset_var.set(name)
        self._sync_widgets_from_params()
        self._set_active_preset(name)
        self._set_status(f"Пресет «{name}» применён", GREEN)

    def _apply_preset(self) -> None:
        self._apply_preset_name(self.preset_var.get())

    def _set_active_preset(self, name: str) -> None:
        self.preset_var.set(name)
        for card_name, card in self.preset_cards.items():
            card.set_active(card_name == name)
        self._update_hero()

    def _update_hero(self) -> None:
        name = self.preset_var.get()
        meta = self._preset_meta(name)
        self.hero_name.configure(text=name)
        self.hero_desc.configure(text=str(meta["desc"]))
        self.hero_avatar.delete("all")
        self.hero_avatar.create_oval(
            4, 4, 84, 84, fill=meta["color"], outline=""
        )
        self.hero_avatar.create_text(
            44, 43,
            text=meta["glyph"],
            fill="#FFFFFF",
            font=("Segoe UI Symbol", 34, "bold"),
        )
        self._update_tags()

    def _update_tags(self) -> None:
        for child in self.hero_tags.winfo_children():
            child.destroy()
        tags: list[str] = []
        params = self.params
        if bool(params.get("bypass", False)):
            tags.append("Bypass")
        pitch = float(params.get("pitch", 0.0))
        if abs(pitch) >= 0.05:
            tags.append(f"Тон {pitch:+.1f}")
        if float(params.get("robot_mix", 0.0)) > 0:
            tags.append(f"Робот {params['robot_mix'] * 100:.0f}%")
        if float(params.get("echo_mix", 0.0)) > 0:
            tags.append(f"Эхо {params['echo_mix'] * 100:.0f}%")
        if float(params.get("drive", 0.0)) > 0:
            tags.append(f"Драйв {params['drive']:.0f}%")
        mode = str(params.get("filter", "none"))
        if mode != "none":
            tags.append(f"Фильтр: {FILTER_TO_LABEL.get(mode, mode)}")
        if float(params.get("noise_reduction", 0.0)) > 0:
            tags.append(
                f"Шум -{params['noise_reduction'] * 100:.0f}%"
            )
        if float(params.get("highpass", 0.0)) > 0:
            tags.append(f"Низ {params['highpass']:.0f} Гц")
        if str(params.get("hum", "off")) != "off":
            tags.append(f"Наводки {params['hum']} Гц")
        gate = float(params.get("gate_db", -80.0))
        if gate > -79:
            tags.append(f"Гейт {gate:.0f} дБ")
        if not tags:
            tags.append("Чистый голос")
        for text in tags[:6]:
            tk.Label(
                self.hero_tags,
                text=text,
                bg=CARD_ALT,
                fg=MUTED,
                padx=8,
                pady=3,
                font=("Segoe UI", 8),
            ).pack(side="left", padx=(0, 5))

    def _save_preset(self) -> None:
        current = self.preset_var.get()
        initial = (
            f"{current} (мой)" if current in dsp.PRESETS else current
        )
        name = simpledialog.askstring(
            "MemeMic",
            "Название пресета:",
            initialvalue=initial,
            parent=self.root,
        )
        if not name:
            return
        name = name.strip()
        if not name:
            return
        if name in dsp.PRESETS:
            messagebox.showwarning(
                "MemeMic",
                "Это имя занято встроенным пресетом.\n"
                "Добавь к названию что-нибудь своё.",
            )
            return
        if name in self.user_presets:
            if not messagebox.askyesno(
                "MemeMic", f"Пресет «{name}» уже есть. Заменить?"
            ):
                return
        diff = {
            k: v
            for k, v in self.params.items()
            if k != "bypass" and dsp.DEFAULT_PARAMS.get(k) != v
        }
        self.user_presets[name] = diff
        config.save_user_presets(self.user_presets)
        self.preset_var.set(name)
        self._render_presets(self._current_query())
        self._set_active_preset(name)
        self._set_status(
            f"Пресет «{name}» сохранён · {config.presets_path()}", GREEN
        )

    def _delete_preset(self, name: str) -> None:
        if name not in self.user_presets:
            return
        if not messagebox.askyesno(
            "MemeMic", f"Удалить пресет «{name}»?"
        ):
            return
        self.user_presets.pop(name, None)
        config.save_user_presets(self.user_presets)
        if self.preset_var.get() == name:
            self.preset_var.set("Без эффектов")
            self._apply_preset_name("Без эффектов")
        self._render_presets(self._current_query())
        self._set_status(f"Пресет «{name}» удалён", MUTED)

    def _current_query(self) -> str:
        text = self.search_var.get()
        return "" if text == self._search_placeholder else text

    # ------------------------------------------------------------------
    # Синхронизация значений
    # ------------------------------------------------------------------
    def _set_slider(self, key: str, value: float) -> None:
        spec = SLIDERS[key]
        raw = float(value) / float(spec["scale"])
        raw = max(spec["lo"], min(spec["hi"], raw))
        self._updating = True
        try:
            self.vars[key].set(raw)
        finally:
            self._updating = False
        self.value_labels[key].configure(text=spec["fmt"](raw))

    def _sync_widgets_from_params(self) -> None:
        for key in SLIDERS:
            self._set_slider(
                key,
                float(self.params.get(key, dsp.DEFAULT_PARAMS[key])),
            )
        mode = self.params.get("filter", "none")
        self._set_filter_buttons(mode)
        self.hum_var.set(HUM_TO_LABEL.get(self.params.get("hum"), "Выкл"))
        self.bypass_var.set(bool(self.params.get("bypass", False)))
        self._update_tags()

    def _set_filter_buttons(self, mode: str) -> None:
        for button_mode, button in self.filter_buttons.items():
            if button_mode == mode:
                button.configure(
                    bg=ACCENT, fg="#FFFFFF",
                    activebackground=ACCENT_HOVER,
                    activeforeground="#FFFFFF",
                )
            else:
                button.configure(
                    bg=CARD_ALT, fg=MUTED,
                    activebackground=CARD_HOVER,
                    activeforeground=FG,
                )

    def _on_slider(self, key: str, raw) -> None:
        if self._updating:
            return
        spec = SLIDERS[key]
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return
        step = float(spec["step"])
        value = round(value / step) * step
        value = max(spec["lo"], min(spec["hi"], value))
        self.value_labels[key].configure(text=spec["fmt"](value))
        self.params[key] = value * float(spec["scale"])
        self.engine.set_params(self.params)
        self._update_tags()

    def _on_filter(self, mode: str) -> None:
        self.params["filter"] = mode
        self.engine.set_params(self.params)
        self._set_filter_buttons(mode)
        self._update_tags()

    def _on_hum_change(self, _event=None) -> None:
        self.params["hum"] = HUM_CHOICES.get(self.hum_var.get(), "off")
        self.engine.set_params(self.params)
        self._update_tags()

    def _on_bypass(self) -> None:
        self.params["bypass"] = bool(self.bypass_var.get())
        self.engine.set_params(self.params)
        self._update_tags()

    def _reset_params(self) -> None:
        bypass = bool(self.params.get("bypass", False))
        self.params = dict(dsp.DEFAULT_PARAMS)
        self.params["bypass"] = bypass
        self.engine.set_params(self.params)
        self._sync_widgets_from_params()
        self._set_status("Настройки сброшены", MUTED)

    def _on_latency_change(self, _event=None) -> None:
        if self.running:
            self.latency_combo.set(
                LATENCY_LABELS.get(self.engine.latency_mode, "Низкая")
            )
            self._set_status(
                "Задержку можно менять только после остановки", YELLOW
            )
            return
        mode = LATENCY_KEYS.get(self.latency_var.get(), "low")
        self.engine.set_latency(mode)
        self.settings["latency"] = mode
        self._set_status(
            f"Задержка: {LATENCY_LABELS[mode]} · блок {self.engine.block} "
            f"сэмплов",
            MUTED,
        )

    # ------------------------------------------------------------------
    # Устройства
    # ------------------------------------------------------------------
    def _refresh_devices(self) -> None:
        if self.running:
            return
        try:
            ins, outs = dev_mod.list_devices()
        except Exception as exc:
            messagebox.showerror(
                "MemeMic",
                "Не удалось получить список аудио-устройств.\n"
                f"{exc}\n\nПроверь, что sounddevice установлен корректно.",
            )
            return

        self.devices_in, self.devices_out = ins, outs
        self.in_combo["values"] = [d.label for d in ins]
        self.out_combo["values"] = [d.label for d in outs]

        default_in, default_out = dev_mod.default_names()
        saved_in = self.settings.get("input") or ""
        saved_out = self.settings.get("output") or ""

        chosen_in = (
            dev_mod.find_by_name(ins, saved_in)
            or dev_mod.find_by_name(ins, default_in)
            or (ins[0] if ins else None)
        )
        chosen_out = (
            dev_mod.find_by_name(outs, saved_out)
            or dev_mod.find_virtual_output(outs)
            or dev_mod.find_by_name(outs, default_out)
            or (outs[0] if outs else None)
        )

        if chosen_in is not None:
            self.in_var.set(chosen_in.label)
            if not saved_in:
                self.settings["input"] = chosen_in.name
        if chosen_out is not None:
            self.out_var.set(chosen_out.label)
            if not saved_out:
                self.settings["output"] = chosen_out.name

        self._update_virtual_status(chosen_out)

    def _update_virtual_status(self, out_dev) -> None:
        if out_dev is not None and out_dev.is_cable:
            name = out_dev.name
            if "virtual audio driver" in name.lower():
                badge = "Virtual Audio Driver"
                note = "в приложениях — Virtual Mic Driver by MTT"
            elif "voicemeeter" in name.lower():
                badge = "VoiceMeeter"
                note = "в приложениях — VoiceMeeter Output"
            else:
                badge = "VB-Cable"
                note = (
                    "в приложениях — CABLE Output "
                    "(VB-Audio Virtual Cable)"
                )
            self.virtual_badge.configure(text=f"✓ {badge}", fg=GREEN)
            self.mic_hint.configure(text=note)
            self.virtual_help_btn.pack_forget()
            if not self.running:
                self.state_pill.set("Готово", GREEN)
        else:
            self.virtual_badge.configure(
                text="виртуальный микрофон не найден", fg=YELLOW
            )
            self.mic_hint.configure(text="")
            self.virtual_help_btn.pack(side="left", padx=(8, 0))
            if not self.running:
                self.state_pill.set("Нет виртуального микрофона", YELLOW)
            self._set_status(
                "Установи виртуальный аудиодрайвер — иначе приложения "
                "тебя не услышат.",
                YELLOW,
            )

    def _virtual_help(self) -> None:
        answer = messagebox.askyesno(
            "Виртуальный микрофон",
            "MemeMic передаёт обработанный голос в виртуальное "
            "устройство, а приложения читают его как обычный микрофон.\n\n"
            "Сейчас для этого используется бесплатный VB-Cable:\n"
            "1. Скачай драйвер с vb-audio.com/Cable\n"
            "2. Распакуй и запусти VBCABLE_Setup_x64.exe от администратора\n"
            "3. Перезагрузи ПК и нажми «Обновить» в MemeMic\n\n"
            "MemeMic не устанавливает собственный аудиодрайвер: для "
            "отдельного микрофона, как в Voicemod, нужен подписанный "
            "драйвер уровня ядра Windows.\n\n"
            "Открыть сайт VB-Cable?",
            parent=self.root,
        )
        if answer:
            webbrowser.open("https://vb-audio.com/Cable/")

    # ------------------------------------------------------------------
    # Запуск / остановка
    # ------------------------------------------------------------------
    def _toggle(self) -> None:
        if self.running:
            self._stop()
        else:
            self._start()

    def _start(self) -> None:
        in_dev = dev_mod.find_by_name(self.devices_in, self.in_var.get())
        out_dev = dev_mod.find_by_name(self.devices_out, self.out_var.get())
        if in_dev is None or out_dev is None:
            messagebox.showwarning(
                "MemeMic", "Сначала выбери микрофон и устройство вывода."
            )
            return

        self.engine.set_latency(
            LATENCY_KEYS.get(self.latency_var.get(), "low")
        )
        ok, message = self.engine.start(in_dev, out_dev, self.params)
        log(
            f"start: in='{in_dev.name}' out='{out_dev.name}' "
            f"ok={ok} msg='{message.replace(chr(10), ' | ')}'"
            f" in_sr={getattr(self.engine, 'in_sr', None)}"
            f" out_sr={getattr(self.engine, 'out_sr', None)}"
            f" block={self.engine.block}"
        )
        if not ok:
            messagebox.showerror("MemeMic", message)
            self._set_status("Не удалось запустить", RED)
            self.state_pill.set("Ошибка", RED)
            return

        self.running = True
        self._logged_underruns = 0
        self.start_btn.set_text("■   Стоп")
        self.start_btn.set_colors(RED, "#E85B6A")
        self._set_controls_enabled(False)
        self.state_pill.set("Работает", GREEN)

        if not out_dev.is_cable:
            message = (
                message + "\nВыход не похож на виртуальный микрофон: "
                "приложения тебя не услышат."
            )
            self._set_status(message, YELLOW)
            self.state_pill.set("Выход не виртуальный", YELLOW)
        else:
            self._set_status(message, GREEN)
        self.hero_status.configure(text=message.split("\n")[0], fg=GREEN)

    def _stop(self) -> None:
        self.engine.stop()
        log("stop")
        self.running = False
        self.start_btn.set_text("▶   Старт")
        self.start_btn.set_colors(ACCENT, ACCENT_HOVER)
        self._set_controls_enabled(True)
        self.in_meter.set_level(0)
        self.out_meter.set_level(0)
        self.in_db.configure(text="—")
        self.out_db.configure(text="—")
        self.hero_status.configure(
            text="Готово к запуску", fg=MUTED
        )
        self.state_pill.set("Готово", MUTED)
        self._set_status("Остановлено", MUTED)

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "readonly" if enabled else "disabled"
        self.in_combo.configure(state=state)
        self.out_combo.configure(state=state)
        self.refresh_btn.set_enabled(enabled)
        self.latency_combo.configure(state=state)
        self.save_preset_btn.set_enabled(enabled)
        self.save_top_btn.set_enabled(enabled)
        self.reset_btn.set_enabled(enabled)

    def _set_status(self, text: str, color: str = MUTED) -> None:
        self.status_label.configure(text=text, foreground=color)

    # ------------------------------------------------------------------
    # Цикл обновления
    # ------------------------------------------------------------------
    def _tick(self) -> None:
        if self.running:
            in_level = self.engine.in_level
            out_level = self.engine.out_level
            self.in_meter.set_level(_level_norm(in_level))
            self.out_meter.set_level(_level_norm(out_level))
            self.in_db.configure(text=_db_text(in_level))
            self.out_db.configure(text=_db_text(out_level))
            if self.engine.underruns != self._logged_underruns:
                self._logged_underruns = self.engine.underruns
                log(f"underruns={self.engine.underruns}")
            if self.engine.last_error:
                self._set_status(
                    f"Ошибка аудио: {self.engine.last_error}", RED
                )
                self.state_pill.set("Ошибка", RED)
        else:
            self.in_meter.set_level(0)
            self.out_meter.set_level(0)
        self.root.after(60, self._tick)

    # ------------------------------------------------------------------
    # Прочее
    # ------------------------------------------------------------------
    def _on_callback_error(self, exc_type, exc_value, exc_tb) -> None:
        """Ошибки обработчиков Tk не должны молча теряться."""
        text = "".join(
            traceback.format_exception(exc_type, exc_value, exc_tb)
        )
        log("callback error: " + text.strip().replace("\n", " | "))
        write_crash("Ошибка обработчика интерфейса", text)
        try:
            messagebox.showerror(
                "MemeMic — ошибка",
                f"{exc_value}\n\nПодробности: {crash_path()}",
                parent=self.root,
            )
        except Exception:
            pass

    def _open_settings_folder(self) -> None:
        path = config.settings_path().parent
        try:
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(str(path))
        except OSError:
            self._set_status(f"Папка настроек: {path}", MUTED)

    def _about(self) -> None:
        messagebox.showinfo(
            "MemeMic",
            f"MemeMic {__version__}\n\n"
            "Войс-ченджер в реальном времени: микрофон → эффекты → "
            "виртуальный микрофон.\n\n"
            "Лицензия MIT · https://github.com/sunsleepve/MemeMic\n\n"
            "Поддерживаются VB-Cable, VoiceMeeter и другие виртуальные "
            "аудиодрайверы — MemeMic находит их автоматически.",
            parent=self.root,
        )

    def _on_close(self) -> None:
        try:
            self.engine.stop()
        finally:
            config.save_settings(
                {
                    "input": self.in_var.get(),
                    "output": self.out_var.get(),
                    "preset": self.preset_var.get(),
                    "params": self.params,
                    "latency": LATENCY_KEYS.get(
                        self.latency_var.get(), "low"
                    ),
                }
            )
            self.root.destroy()


def run() -> None:
    log(f"gui start: version={__version__}")
    try:
        root = tk.Tk()
    except Exception:
        text = traceback.format_exc()
        write_crash("Не удалось создать окно Tk", text)
        show_startup_error("Не удалось создать окно Tk.", text)
        return

    try:
        App(root)
    except Exception:
        text = traceback.format_exc()
        write_crash("Ошибка при создании интерфейса", text)
        try:
            root.destroy()
        except Exception:
            pass
        show_startup_error("Не удалось создать интерфейс.", text)
        return

    log("gui ready")
    root.mainloop()
