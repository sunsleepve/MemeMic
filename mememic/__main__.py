"""Точка входа: python -m mememic [--list-devices]."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        prog="mememic",
        description="Войс-ченджер: микрофон -> эффекты -> виртуальный микрофон.",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="показать доступные аудио-устройства и выйти",
    )
    args = parser.parse_args(argv)

    try:
        from . import devices as dev_mod
    except Exception as exc:  # обычно отсутствует sounddevice или PortAudio
        print("Не удалось загрузить аудио-библиотеки:", exc)
        print("Запусти install.bat или: pip install -r requirements.txt")
        return 1

    if args.list_devices:
        try:
            ins, outs = dev_mod.list_devices()
        except Exception as exc:
            print("Ошибка при получении списка устройств:", exc)
            return 1

        print("Входные устройства (микрофоны):")
        for info in ins:
            print("  -", info)
        print()
        print("Выходные устройства (для виртуального кабеля нужен CABLE Input):")
        for info in outs:
            print("  -", info)
        if dev_mod.find_virtual_output(outs) is None:
            print()
            print("Виртуальный кабель не найден. Установи VB-Cable: https://vb-audio.com/Cable/")
        return 0

    try:
        from .gui import run
    except Exception as exc:
        print("Не удалось запустить интерфейс:", exc)
        print("Проверь установку зависимостей: install.bat")
        return 1

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
