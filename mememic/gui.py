"""Tkinter-интерфейс войс-ченджера."""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from . import config, devices as dev_mod, dsp
from .engine import AudioEngine
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

BG = "#16171f"
PANEL = "#21232f"
PANEL_ALT = "#2a2d3d"
FG = "#eceef6"
MUTED = "#9ba1b7"
ACCENT = "#8b5cf6"
ACCENT_HOVER = "#7c3aed"
GREEN = "#34d399"
YELLOW = "#fbbf24"
RED = "#f87171"

FILTER_CHOICES = {
    "Нет": "none",
    "Телефон": "phone",
    "Глухой": "muffled",
    "Тонкий": "thin",
}
FILTER_TO_LABEL = {v: k for k, v in FILTER_CHOICES.items()}


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
    "volume": {
        "label": "Громкость",
        "lo": 0,
        "hi": 200,
        "step": 5,
        "scale": 0.01,
        "fmt": lambda v: f"{v:.0f}%",
    },
    "gate_db": {
        "label": "Порог шум-гейта",
        "lo": -80,
        "hi": -20,
        "step": 1,
        "scale": 1.0,
        "fmt": lambda v: "выкл" if v <= -79 else f"{v:.0f} дБ",
    },
}


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.engine = AudioEngine()
        self.settings = config.load_settings()
        self.params: dict = dict(dsp.DEFAULT_PARAMS)
        saved_params = self.settings.get("params")
        if isinstance(saved_params, dict):
            for key in self.params:
                if key in saved_params:
                    self.params[key] = saved_params[key]
        if self.params.get("filter") not in dsp.FILTER_MODES:
            self.params["filter"] = "none"

        self.devices_in: list[dev_mod.DeviceInfo] = []
        self.devices_out: list[dev_mod.DeviceInfo] = []
        self.vars: dict[str, tk.DoubleVar] = {}
        self.value_labels: dict[str, ttk.Label] = {}
        self.running = False
        self._logged_underruns = 0
        self._updating = False

        self.root.title("MemeMic")
        try:
            self._icon = tk.PhotoImage(data=ICON_PNG_BASE64)
            self.root.iconphoto(True, self._icon)
        except tk.TclError:
            self._icon = None
        self.root.configure(bg=BG)
        self.root.geometry("680x680")
        self.root.minsize(600, 640)

        self._build_style()
        self._build_ui()
        self._refresh_devices()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
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

        style.configure(".", background=BG, foreground=FG, font=("Segoe UI", 9))
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Panel.TLabel", background=PANEL, foreground=FG)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED)
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 18), background=BG)
        style.configure("Sub.TLabel", font=("Segoe UI", 9), foreground=MUTED, background=BG)
        style.configure("Value.TLabel", font=("Consolas", 9), foreground=ACCENT, background=BG)

        style.configure(
            "TButton",
            background=PANEL_ALT,
            foreground=FG,
            borderwidth=0,
            focusthickness=0,
            padding=(12, 6),
        )
        style.map(
            "TButton",
            background=[("active", "#3a3e52"), ("disabled", "#262835")],
            foreground=[("disabled", "#6c7188")],
        )
        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#ffffff",
            font=("Segoe UI Semibold", 10),
            padding=(16, 9),
        )
        style.map(
            "Accent.TButton",
            background=[("active", ACCENT_HOVER), ("disabled", "#4b3b7a")],
        )
        style.configure(
            "TLabelframe",
            background=BG,
            bordercolor="#2c2f3f",
            borderwidth=1,
            relief="solid",
        )
        style.configure(
            "TLabelframe.Label",
            background=BG,
            foreground=MUTED,
            font=("Segoe UI Semibold", 9),
            padding=(2, 0, 6, 4),
        )
        style.configure(
            "TCombobox",
            fieldbackground=PANEL,
            background=PANEL,
            foreground=FG,
            arrowcolor=FG,
            bordercolor="#2c2f3f",
            lightcolor="#2c2f3f",
            darkcolor="#2c2f3f",
            padding=4,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", PANEL), ("disabled", "#1c1d26")],
            foreground=[("readonly", FG), ("disabled", "#6c7188")],
            arrowcolor=[("disabled", "#6c7188")],
        )
        style.configure("TScale", background=BG, troughcolor="#2c2f3f", borderwidth=0)
        style.configure(
            "TCheckbutton",
            background=BG,
            foreground=FG,
            focuscolor=BG,
        )
        style.map(
            "TCheckbutton",
            background=[("active", BG)],
            indicatorcolor=[("selected", ACCENT), ("!selected", PANEL_ALT)],
        )
        style.configure(
            "Horizontal.TProgressbar",
            background=ACCENT,
            troughcolor="#2c2f3f",
            bordercolor=BG,
            borderwidth=0,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
        )
        style.configure(
            "Out.Horizontal.TProgressbar",
            background=GREEN,
            troughcolor="#2c2f3f",
            bordercolor=BG,
            borderwidth=0,
            lightcolor=GREEN,
            darkcolor=GREEN,
        )

        self.root.option_add("*TCombobox*Listbox.background", PANEL)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    # ------------------------------------------------------------------
    # Интерфейс
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=(18, 12, 18, 12))
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x")
        ttk.Label(header, text="MemeMic", style="Title.TLabel").pack(side="left")
        ttk.Label(
            header,
            text="голосовые эффекты для Discord, GMod и всего остального",
            style="Sub.TLabel",
        ).pack(side="left", padx=(10, 0), pady=(6, 0))

        # --- устройства -------------------------------------------------
        devices_box = ttk.Labelframe(outer, text=" 1. Устройства ", padding=(12, 10))
        devices_box.pack(fill="x", pady=(12, 10))
        devices_box.columnconfigure(1, weight=1)

        ttk.Label(devices_box, text="Микрофон", style="PanelMuted.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 10), pady=3
        )
        self.in_var = tk.StringVar()
        self.in_combo = ttk.Combobox(
            devices_box, textvariable=self.in_var, state="readonly", width=44
        )
        self.in_combo.grid(row=0, column=1, sticky="ew", pady=3)

        ttk.Label(devices_box, text="Выход", style="PanelMuted.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 10), pady=3
        )
        self.out_var = tk.StringVar()
        self.out_combo = ttk.Combobox(
            devices_box, textvariable=self.out_var, state="readonly", width=44
        )
        self.out_combo.grid(row=1, column=1, sticky="ew", pady=3)

        self.refresh_btn = ttk.Button(
            devices_box, text="Обновить", command=self._refresh_devices, width=12
        )
        self.refresh_btn.grid(row=0, column=2, rowspan=2, padx=(10, 0), sticky="ns")

        # --- эффекты ----------------------------------------------------
        fx_box = ttk.Labelframe(outer, text=" 2. Голос ", padding=(12, 10))
        fx_box.pack(fill="both", expand=True)
        fx_box.columnconfigure(0, weight=1, uniform="fx")
        fx_box.columnconfigure(1, weight=1, uniform="fx")

        preset_row = ttk.Frame(fx_box)
        preset_row.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ttk.Label(preset_row, text="Пресет", style="PanelMuted.TLabel").pack(
            side="left", padx=(0, 10)
        )
        self.preset_var = tk.StringVar(value="Без эффектов")
        self.user_presets = config.load_user_presets()
        self.preset_combo = ttk.Combobox(
            preset_row,
            textvariable=self.preset_var,
            values=self._preset_names(),
            state="readonly",
            width=24,
        )
        if self.settings.get("preset") in self._preset_names():
            self.preset_var.set(self.settings["preset"])
        self.preset_combo.pack(side="left")
        self.apply_btn = ttk.Button(
            preset_row, text="Применить", command=self._apply_preset
        )
        self.apply_btn.pack(side="left", padx=(8, 0))
        self.save_preset_btn = ttk.Button(
            preset_row, text="Сохранить…", command=self._save_preset
        )
        self.save_preset_btn.pack(side="left", padx=(8, 0))

        left = ttk.Frame(fx_box)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        right = ttk.Frame(fx_box)
        right.grid(row=1, column=1, sticky="nsew", padx=(12, 0))

        for key in ("pitch", "robot_mix", "robot_freq", "gate_db"):
            self._make_slider(left, key)
        self._make_filter_row(left)
        for key in (
            "echo_mix",
            "echo_delay_ms",
            "echo_feedback",
            "drive",
            "volume",
        ):
            self._make_slider(right, key)

        bottom_opts = ttk.Frame(fx_box)
        bottom_opts.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.bypass_var = tk.BooleanVar(value=bool(self.params.get("bypass", False)))
        ttk.Checkbutton(
            bottom_opts,
            text="Пропускать звук без обработки (bypass)",
            variable=self.bypass_var,
            command=self._on_bypass,
        ).pack(side="left")

        # --- уровни и запуск -------------------------------------------
        levels = ttk.Frame(outer)
        levels.pack(fill="x", pady=(12, 0))
        levels.columnconfigure(1, weight=1)

        ttk.Label(levels, text="Вход", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        self.in_bar = ttk.Progressbar(levels, maximum=100, value=0)
        self.in_bar.grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(levels, text="Выход", style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 10)
        )
        self.out_bar = ttk.Progressbar(
            levels, maximum=100, value=0, style="Out.Horizontal.TProgressbar"
        )
        self.out_bar.grid(row=1, column=1, sticky="ew", pady=2)

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(14, 0))
        self.start_btn = ttk.Button(
            controls,
            text="▶  Старт",
            style="Accent.TButton",
            command=self._toggle,
            width=16,
        )
        self.start_btn.pack(side="left")
        self.status_label = ttk.Label(
            controls,
            text="Готово к запуску",
            style="Muted.TLabel",
            wraplength=430,
            justify="left",
        )
        self.status_label.pack(side="left", padx=(12, 0), fill="x", expand=True)

        self._sync_widgets_from_params()

    def _make_slider(self, parent: ttk.Frame, key: str) -> None:
        spec = SLIDERS[key]
        block = ttk.Frame(parent)
        block.pack(fill="x", pady=(0, 4))

        top = ttk.Frame(block)
        top.pack(fill="x")
        ttk.Label(top, text=spec["label"], style="Muted.TLabel").pack(side="left")
        value_label = ttk.Label(top, text="", style="Value.TLabel")
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
        scale.pack(fill="x", pady=(2, 0))

    def _make_filter_row(self, parent: ttk.Frame) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(4, 0))
        ttk.Label(row, text="Фильтр", style="Muted.TLabel").pack(side="left")
        self.filter_combo = ttk.Combobox(
            row,
            values=list(FILTER_CHOICES),
            state="readonly",
            width=14,
        )
        self.filter_combo.pack(side="right")
        self.filter_combo.bind("<<ComboboxSelected>>", self._on_filter)

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
            self._set_slider(key, float(self.params.get(key, dsp.DEFAULT_PARAMS[key])))
        mode = self.params.get("filter", "none")
        self.filter_combo.set(FILTER_TO_LABEL.get(mode, "Нет"))
        self.bypass_var.set(bool(self.params.get("bypass", False)))

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

    def _on_filter(self, _event=None) -> None:
        self.params["filter"] = FILTER_CHOICES.get(self.filter_combo.get(), "none")

    def _on_bypass(self) -> None:
        self.params["bypass"] = bool(self.bypass_var.get())

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

    def _apply_preset(self) -> None:
        name = self.preset_var.get()
        fresh = self._lookup_preset(name)
        bypass = bool(self.params.get("bypass", False))
        self.params.update(fresh)
        self.params["bypass"] = bypass
        self._sync_widgets_from_params()

    def _save_preset(self) -> None:
        name = simpledialog.askstring(
            "MemeMic",
            "Название пресета:",
            initialvalue=self.preset_var.get(),
            parent=self.root,
        )
        if not name:
            return
        name = name.strip()
        if not name:
            return
        # Сохраняем только отличия от значений по умолчанию — так файл компактный.
        diff = {
            k: v
            for k, v in self.params.items()
            if k != "bypass" and dsp.DEFAULT_PARAMS.get(k) != v
        }
        self.user_presets[name] = diff
        config.save_user_presets(self.user_presets)
        self.preset_combo.configure(values=self._preset_names())
        self.preset_var.set(name)
        self._set_status(
            f"Пресет «{name}» сохранён · {config.presets_path()}", GREEN
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

        if chosen_out is not None and not chosen_out.is_cable:
            self._set_status(
                "Виртуальный кабель не найден — для стрима/Discord установи VB-Cable.",
                YELLOW,
            )

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

        ok, message = self.engine.start(in_dev, out_dev, self.params)
        log(
            f"start: in='{in_dev.name}' out='{out_dev.name}' "
            f"ok={ok} msg='{message.replace(chr(10), ' | ')}'"
            f" in_sr={getattr(self.engine, 'in_sr', None)}"
            f" out_sr={getattr(self.engine, 'out_sr', None)}"
        )
        if not ok:
            messagebox.showerror("MemeMic", message)
            self._set_status("Не удалось запустить", RED)
            return

        self.running = True
        self._logged_underruns = 0
        self.start_btn.configure(text="■  Стоп")
        self._set_controls_enabled(False)

        if not out_dev.is_cable:
            message = (
                message + "\nВыход не похож на виртуальный кабель: "
                "приложения тебя не услышат."
            )
            self._set_status(message, YELLOW)
        else:
            self._set_status(message, GREEN)

    def _stop(self) -> None:
        self.engine.stop()
        log("stop")
        self.running = False
        self.start_btn.configure(text="▶  Старт")
        self._set_controls_enabled(True)
        self.in_bar["value"] = 0
        self.out_bar["value"] = 0
        self._set_status("Остановлено", MUTED)

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "readonly" if enabled else "disabled"
        self.in_combo.configure(state=state)
        self.out_combo.configure(state=state)
        self.refresh_btn.configure(state="normal" if enabled else "disabled")
        self.preset_combo.configure(state=state)
        self.apply_btn.configure(state="normal" if enabled else "disabled")
        self.save_preset_btn.configure(state="normal" if enabled else "disabled")

    def _set_status(self, text: str, color: str) -> None:
        self.status_label.configure(text=text, foreground=color)

    # ------------------------------------------------------------------
    # Цикл обновления
    # ------------------------------------------------------------------
    def _tick(self) -> None:
        if self.running:
            self.in_bar["value"] = min(100.0, self.engine.in_level * 320.0)
            self.out_bar["value"] = min(100.0, self.engine.out_level * 320.0)
            if self.engine.underruns != self._logged_underruns:
                self._logged_underruns = self.engine.underruns
                log(f"underruns={self.engine.underruns}")
            if self.engine.last_error:
                self._set_status(f"Ошибка аудио: {self.engine.last_error}", RED)
        else:
            self.in_bar["value"] = float(self.in_bar["value"]) * 0.8
            self.out_bar["value"] = float(self.out_bar["value"]) * 0.8
        self.root.after(60, self._tick)

    # ------------------------------------------------------------------
    # Выход
    # ------------------------------------------------------------------
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
                }
            )
            self.root.destroy()


def run() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()
