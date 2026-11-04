"""Сохранение настроек между запусками."""

from __future__ import annotations

import json
import os
from pathlib import Path

APP_DIR_NAME = "MemeMic"


def settings_path() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_DIR_NAME / "settings.json"
    return Path.home() / ".mememic" / "settings.json"


def presets_path() -> Path:
    """Пользовательские пресеты — рядом с настройками, чтобы их можно было шарить."""
    return settings_path().with_name("presets.json")


def load_settings() -> dict:
    path = settings_path()
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data: dict) -> None:
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def load_user_presets() -> dict[str, dict]:
    """Пресеты, которые пользователь добавил сам (presets.json)."""
    path = presets_path()
    try:
        with path.open("r", encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(name): params for name, params in data.items() if isinstance(params, dict)}


def save_user_presets(presets: dict[str, dict]) -> None:
    path = presets_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(presets, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass
