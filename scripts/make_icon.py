"""Генерирует логотип MemeMic: docs/logo.png, assets/mememic.ico, mememic/icon.py.

Рисуем без внешних библиотек: numpy + zlib. Формы сглаживаются
суперсэмплингом x4, поэтому на 16x16 иконка остаётся читаемой.
"""

from __future__ import annotations

import base64
import struct
import zlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SS = 4  # суперсэмплинг


def hex_rgb(value: str) -> np.ndarray:
    value = value.lstrip("#")
    return np.array([int(value[i : i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


BG_TOP = hex_rgb("#7C3AED")     # фиолетовый
BG_BOTTOM = hex_rgb("#06B6D4")  # циан
WHITE = np.array([255, 255, 255], dtype=np.float32)
YELLOW = hex_rgb("#FDE047")


def rounded_rect_mask(size: int, x0: float, y0: float, x1: float, y1: float, r: float) -> np.ndarray:
    ys, xs = np.mgrid[0:size, 0:size]
    x = xs / size
    y = ys / size
    cx = np.clip(x, x0 + r, x1 - r)
    cy = np.clip(y, y0 + r, y1 - r)
    dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    return (
        (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1) & (dist <= r + 1e-9)
    )


def render(size: int = 1024) -> np.ndarray:
    n = size * SS
    ys, xs = np.mgrid[0:n, 0:n]
    x = xs / n
    y = ys / n

    # --- фон: скруглённый квадрат с диагональным градиентом -----------
    bg_mask = rounded_rect_mask(n, 0.02, 0.02, 0.98, 0.98, 0.23)
    t = np.clip((x + y) / 2.0, 0, 1)[..., None]
    color = BG_TOP * (1 - t) + BG_BOTTOM * t

    # мягкий блик в левом верхнем углу
    glow = np.exp(-(((x - 0.22) ** 2 + (y - 0.18) ** 2) / 0.045))[..., None]
    color = color + (WHITE - color) * glow * 0.18

    img = np.zeros((n, n, 4), dtype=np.float32)
    img[..., :3] = color
    img[..., 3] = bg_mask * 255.0

    def paint(mask: np.ndarray, rgb: np.ndarray, alpha: float = 1.0) -> None:
        a = mask.astype(np.float32) * alpha * bg_mask
        if not a.any():
            return
        img[..., :3] = img[..., :3] * (1 - a[..., None]) + rgb * a[..., None]
        img[..., 3] = np.maximum(img[..., 3], a * 255.0)

    # --- микрофон ------------------------------------------------------
    paint(rounded_rect_mask(n, 0.385, 0.185, 0.615, 0.545, 0.115), WHITE)

    # решётка капсули: три тёмные полоски
    for gy in (0.275, 0.35, 0.425):
        paint(rounded_rect_mask(n, 0.425, gy - 0.012, 0.575, gy + 0.012, 0.012), BG_TOP, 0.55)

    # U-образная скоба: кольцо ниже центра капсули
    rr = np.sqrt((x - 0.5) ** 2 + (y - 0.545) ** 2)
    paint((rr >= 0.185) & (rr <= 0.235) & (y > 0.545), WHITE)

    # ножка и основание
    paint(rounded_rect_mask(n, 0.483, 0.775, 0.517, 0.845, 0.014), WHITE)
    paint(rounded_rect_mask(n, 0.395, 0.84, 0.605, 0.895, 0.027), WHITE)

    # --- звуковые волны по бокам --------------------------------------
    for side in (-1, 1):
        for radius in (0.335, 0.415):
            rr = np.sqrt((x - 0.5) ** 2 + (y - 0.43) ** 2)
            sector = (x - 0.5) * side > 0.16
            paint((rr >= radius) & (rr <= radius + 0.038) & sector, YELLOW, 0.95)

    # --- даунсэмплинг --------------------------------------------------
    img = np.clip(img, 0, 255).astype(np.uint8)
    img = img.reshape(size, SS, size, SS, 4).mean(axis=(1, 3))
    return np.clip(img, 0, 255).astype(np.uint8)


def downscale(rgba: np.ndarray, size: int) -> np.ndarray:
    """Усреднение по областям (box filter) для произвольного размера."""
    h = rgba.shape[0]
    bounds = np.linspace(0, h, size + 1).astype(int)
    data = rgba.astype(np.float64)
    sums = np.add.reduceat(np.add.reduceat(data, bounds[:-1], axis=0), bounds[:-1], axis=1)
    counts = np.diff(bounds).astype(np.float64)
    out = sums / counts[:, None, None] / counts[None, :, None]
    return np.clip(out, 0, 255).astype(np.uint8)


def png_bytes(rgba: np.ndarray) -> bytes:
    h, w = rgba.shape[:2]
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def ico_bytes(images: list[tuple[int, bytes]]) -> bytes:
    count = len(images)
    out = struct.pack("<HHH", 0, 1, count)
    offset = 6 + 16 * count
    payload = b""
    for size, data in images:
        out += struct.pack(
            "<BBBBHHII",
            size if size < 256 else 0,
            size if size < 256 else 0,
            0,
            0,
            1,
            32,
            len(data),
            offset,
        )
        offset += len(data)
        payload += data
    return out + payload


def main() -> None:
    print("rendering 1024px master...")
    master = render(1024)

    docs = ROOT / "docs"
    assets = ROOT / "assets"
    docs.mkdir(exist_ok=True)
    assets.mkdir(exist_ok=True)

    png_path = docs / "logo.png"
    png_path.write_bytes(png_bytes(master))
    print("wrote", png_path)

    icons = []
    for size in (16, 32, 48, 64, 128, 256):
        small = master if size == 1024 else downscale(master, size)
        icons.append((size, png_bytes(small)))

    ico_path = assets / "mememic.ico"
    ico_path.write_bytes(ico_bytes(icons))
    print("wrote", ico_path)

    preview = downscale(master, 64)
    b64 = base64.b64encode(png_bytes(preview)).decode("ascii")
    icon_py = ROOT / "mememic" / "icon.py"
    icon_py.write_text(
        '"""Иконка окна MemeMic (PNG 64x64 в base64). Сгенерировано scripts/make_icon.py."""\n\n'
        f'ICON_PNG_BASE64 = "{b64}"\n',
        encoding="utf-8",
    )
    print("wrote", icon_py)


if __name__ == "__main__":
    main()
