"""DSP-часть войс-ченджера.

Все эффекты работают с моно-блоками float32 и хранят своё состояние между
вызовами, поэтому их можно дёргать из аудио-колбэка кусками любого размера.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, iirnotch, sosfilt, tf2sos

# ---------------------------------------------------------------------------
# Параметры по умолчанию и пресеты
# ---------------------------------------------------------------------------

DEFAULT_PARAMS: dict = {
    "pitch": 0.0,          # полутона, -12..+12
    "robot_mix": 0.0,      # 0..1
    "robot_freq": 40.0,    # Гц, 5..120
    "echo_mix": 0.0,       # 0..1
    "echo_delay_ms": 180.0,
    "echo_feedback": 0.35,
    "drive": 0.0,          # 0..100, «грязь»/перегруз
    "filter": "none",      # none | phone | muffled | thin
    "volume": 1.0,         # 0..2
    "gate_db": -50.0,      # порог шум-гейта, -80 = выключен
    "noise_reduction": 0.35,  # 0..1, лёгкое подавление шипения
    "highpass": 80.0,      # Гц, срез инфраниза/гула, 0 = выключен
    "hum": "off",          # off | 50 | 60 — подавление наводок сети
    "bypass": False,
}

# Пресет — это набор отличий от DEFAULT_PARAMS.
PRESETS: dict[str, dict] = {
    "Без эффектов": {},
    "Робот": {"robot_mix": 0.85, "robot_freq": 45.0},
    "Демон": {
        "pitch": -6.0,
        "drive": 55.0,
        "filter": "muffled",
        "echo_mix": 0.18,
        "echo_delay_ms": 140.0,
    },
    "Бурундук": {"pitch": 7.0, "drive": 25.0},
    "Телефон": {"filter": "phone", "drive": 40.0},
    "Пещера": {
        "pitch": -1.0,
        "echo_mix": 0.5,
        "echo_delay_ms": 220.0,
        "echo_feedback": 0.5,
    },
    "Инопланетянин": {
        "pitch": 4.0,
        "robot_mix": 0.55,
        "robot_freq": 14.0,
        "echo_mix": 0.25,
    },
    "Монстр": {"pitch": -9.0, "drive": 70.0, "echo_mix": 0.12},
    "Мистер, вы потеряли кошелёк": {
        "pitch": -1.5,
        "robot_mix": 0.85,
        "robot_freq": 48.0,
        "filter": "phone",
        "drive": 30.0,
        "echo_mix": 0.1,
        "echo_delay_ms": 90.0,
        "echo_feedback": 0.2,
        "volume": 1.6,
    },
}

FILTER_MODES = ("none", "phone", "muffled", "thin")


def preset_params(name: str) -> dict:
    """Полный набор параметров для пресета."""
    params = dict(DEFAULT_PARAMS)
    params.update(PRESETS.get(name, {}))
    return params


# ---------------------------------------------------------------------------
# Питч-шифтер
# ---------------------------------------------------------------------------


class PitchShifter:
    """Питч-шифтер на фазовом вокодере (STFT).

    Сначала сигнал растягивается по времени в ``r`` раз (фазовая
    реконструкция), затем проигрывается в ``r`` раз быстрее. Длительность
    остаётся прежней, высота тона умножается на ``r``.

    Такой метод даёт точную высоту тона (в отличие от гранулярного шифтера)
    и предсказуемые артефакты — лёгкую «фазовость» на больших сдвигах.
    """

    def __init__(self, samplerate: int, window: int = 1024):
        self.sr = samplerate
        self.n = int(window)
        self.ha = max(1, self.n // 4)  # анализ: 75 % перекрытия
        self.window = np.hanning(self.n + 1)[:-1].astype(np.float64)  # periodic
        self.bins = self.n // 2 + 1
        self.freqs = 2.0 * np.pi * np.arange(self.bins) / self.n

        self.inbuf = np.zeros(0, dtype=np.float32)
        self.prev_phase = np.zeros(self.bins, dtype=np.float64)
        self.sum_phase = np.zeros(self.bins, dtype=np.float64)
        self.ola = np.zeros(self.n, dtype=np.float64)
        self.norm = np.zeros(self.n, dtype=np.float64)

        self.resampler = LinearResampler(step=1.0)
        self.hs = self.ha
        self.active = False
        self._warm_left = 0

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self.inbuf = np.zeros(0, dtype=np.float32)
        self.prev_phase = np.zeros(self.bins, dtype=np.float64)
        self.sum_phase = np.zeros(self.bins, dtype=np.float64)
        self.ola = np.zeros(self.n, dtype=np.float64)
        self.norm = np.zeros(self.n, dtype=np.float64)
        self.resampler.reset()
        self.active = False
        # Пока окна не перекрылись полностью, делить на сумму окон нельзя.
        self._warm_left = max(0, self.n // self.ha - 1)

    def _process_frame(self, frame: np.ndarray, hs: int) -> np.ndarray:
        spectrum = np.fft.rfft(frame * self.window)
        mag = np.abs(spectrum)
        phase = np.angle(spectrum)

        expected = self.freqs * self.ha
        delta = phase - self.prev_phase - expected
        delta = (delta + np.pi) % (2.0 * np.pi) - np.pi
        omega = self.freqs + delta / self.ha

        # Identity phase locking (Laroche & Dolson): фазу двигаем только у
        # спектральных пиков, а соседние бины держим в той же относительной
        # фазе, что и на анализе. Без этого при больших сдвигах бины
        # «разъезжаются», и перекрытие окон гасит сигнал на 10–15 дБ.
        if self.bins >= 3:
            middle = mag[1:-1]
            peaks = np.nonzero((middle > mag[:-2]) & (middle >= mag[2:]))[0] + 1
        else:
            peaks = np.zeros(0, dtype=np.int64)

        if len(peaks) == 0:
            self.sum_phase += omega * hs
        else:
            peak_phase = self.sum_phase[peaks] + omega[peaks] * hs
            mids = (peaks[:-1] + peaks[1:]) // 2
            owner = np.searchsorted(mids, np.arange(self.bins), side="left")
            owner = np.clip(owner, 0, len(peaks) - 1)
            self.sum_phase = peak_phase[owner] + (phase - phase[peaks][owner])

        out_frame = np.fft.irfft(mag * np.exp(1j * self.sum_phase), n=self.n)
        self.ola += out_frame * self.window
        self.norm += self.window * self.window

        if self._warm_left > 0:
            self._warm_left -= 1
            out = np.zeros(0, dtype=np.float64)
        else:
            out = self.ola[:hs] / np.maximum(self.norm[:hs], 1e-3)

        if hs >= self.n:
            self.ola[:] = 0.0
            self.norm[:] = 0.0
        else:
            self.ola[:-hs] = self.ola[hs:]
            self.ola[-hs:] = 0.0
            self.norm[:-hs] = self.norm[hs:]
            self.norm[-hs:] = 0.0

        self.prev_phase = phase
        return out

    # ------------------------------------------------------------------
    def process(self, x: np.ndarray, semitones: float) -> np.ndarray:
        if len(x) == 0:
            return x

        # Сдвиг меньше 0.05 полутона слышать невозможно — не тратим CPU.
        if abs(semitones) < 0.05:
            if self.active:
                self.reset()
            return x.copy()

        if not self.active:
            self.reset()
            self.active = True

        ratio = float(2.0 ** (semitones / 12.0))
        # Целый шаг синтеза: погрешность < 4 центов, зато без интерполяции.
        hs = max(1, min(int(round(self.ha * ratio)), self.n // 2))
        self.hs = hs
        self.resampler.step = float(hs) / float(self.ha)

        self.inbuf = np.concatenate(
            (self.inbuf, np.asarray(x, dtype=np.float32))
        )

        chunks = []
        while len(self.inbuf) >= self.n:
            frame = self.inbuf[: self.n]
            chunks.append(self._process_frame(frame, hs))
            self.inbuf = self.inbuf[self.ha:]

        if not chunks:
            return np.zeros(0, dtype=np.float32)

        stretched = np.concatenate(chunks)
        return self.resampler.process(stretched).astype(np.float32)


# ---------------------------------------------------------------------------
# Шум-гейт
# ---------------------------------------------------------------------------


class NoiseGate:
    """Простой гейт: считает RMS блока и плавно открывает/закрывает его."""

    def __init__(self, samplerate: int):
        self.sr = float(samplerate)
        self.gain = 0.0

    def process(self, x: np.ndarray, threshold_db: float) -> np.ndarray:
        if threshold_db is None or threshold_db <= -79.0 or len(x) == 0:
            self.gain = 1.0
            return x

        threshold = 10.0 ** (threshold_db / 20.0)
        rms = float(np.sqrt(np.mean(x * x) + 1e-12))
        target = 1.0 if rms >= threshold else 0.0

        # 5 мс на открытие, 150 мс на закрытие (чтобы не рубить хвосты слов).
        tau = 0.005 if target > self.gain else 0.150
        coef = 1.0 - np.exp(-len(x) / (tau * self.sr))
        prev = self.gain
        self.gain += (target - self.gain) * coef

        ramp = np.linspace(prev, self.gain, len(x), dtype=np.float32)
        return (x * ramp).astype(np.float32)


# ---------------------------------------------------------------------------
# Чистка низа и сетевых наводок
# ---------------------------------------------------------------------------


class HighPass:
    """Мягкий срез инфраниза: убирает гул стола, ветер и DC-смещение."""

    def __init__(self, samplerate: int):
        self.sr = float(samplerate)
        self.cutoff = 0.0
        self.sos = None
        self.zi = None

    def process(self, x: np.ndarray, cutoff: float) -> np.ndarray:
        cutoff = float(cutoff or 0.0)
        cutoff = min(max(cutoff, 0.0), self.sr * 0.45)
        if cutoff <= 10.0 or len(x) == 0:
            self.cutoff = cutoff
            self.sos = None
            self.zi = None
            return x

        if self.sos is None or abs(cutoff - self.cutoff) > 0.5:
            self.cutoff = cutoff
            self.sos = butter(
                2, cutoff, btype="highpass", fs=self.sr, output="sos"
            )
            self.zi = np.zeros((self.sos.shape[0], 2), dtype=np.float64)

        y, self.zi = sosfilt(self.sos, x, zi=self.zi)
        return y.astype(np.float32)


class HumFilter:
    """Узкие режекторы на 50/60 Гц и первые гармоники."""

    MODES = ("off", "50", "60")

    def __init__(self, samplerate: int):
        self.sr = float(samplerate)
        self.mode = "off"
        self.sos = None
        self.zi = None

    def _build(self, mode: str):
        if mode not in ("50", "60"):
            return None
        base = float(mode)
        parts = []
        for freq in (base, base * 2.0, base * 3.0):
            if freq >= self.sr * 0.45:
                continue
            b, a = iirnotch(freq, Q=30.0, fs=self.sr)
            parts.append(tf2sos(b, a))
        return np.vstack(parts) if parts else None

    def process(self, x: np.ndarray, mode: str) -> np.ndarray:
        if mode not in self.MODES:
            mode = "off"
        if mode != self.mode:
            self.mode = mode
            self.sos = self._build(mode)
            self.zi = (
                None
                if self.sos is None
                else np.zeros((self.sos.shape[0], 2), dtype=np.float64)
            )
        if self.sos is None or len(x) == 0:
            return x
        y, self.zi = sosfilt(self.sos, x, zi=self.zi)
        return y.astype(np.float32)


class NoiseSuppressor:
    """Лёгкий подавитель шипения без FFT-задержки.

    Оценивает «шумность» блока по спектральной плоскостности: у шипения
    спектр ровный, у голоса и тонов — пиковый. Поэтому устойчивые ноты и
    гласные не глушатся, а постоянный фон между словами становится тише.
    """

    def __init__(self, samplerate: int):
        self.sr = float(samplerate)
        self.gain = 1.0
        self._window: np.ndarray | None = None

    def process(self, x: np.ndarray, amount: float) -> np.ndarray:
        amount = float(amount or 0.0)
        if amount <= 0.001 or len(x) < 32:
            self.gain = 1.0
            return x

        n = len(x)
        if self._window is None or len(self._window) != n:
            self._window = np.hanning(n).astype(np.float32)

        spectrum = np.abs(np.fft.rfft(x * self._window)) + 1e-9
        flatness = float(
            np.exp(np.mean(np.log(spectrum))) / max(np.mean(spectrum), 1e-12)
        )
        rms = float(np.sqrt(np.mean(x * x) + 1e-12))

        # 0.3 — граница «ровный шум / гармонический звук». Значение подобрано
        # так, чтобы синус и голос оставались нетронутыми.
        if flatness > 0.30:
            target = 1.0 - (0.85 if rms < 0.03 else 0.35) * min(1.0, amount)
        else:
            target = 1.0

        tau = 0.012 if target < self.gain else 0.150
        coef = 1.0 - np.exp(-n / (tau * self.sr))
        self.gain += (target - self.gain) * coef
        return (x * self.gain).astype(np.float32)


def soft_limit(x: np.ndarray) -> np.ndarray:
    """Плавный лимитер вместо жёсткого клипа — меньше щелчков и хрипа."""
    threshold = 0.92
    absx = np.abs(x)
    mask = absx > threshold
    if not np.any(mask):
        return x.astype(np.float32, copy=False)

    y = x.astype(np.float32, copy=True)
    over = (absx[mask] - threshold) / (1.0 - threshold)
    y[mask] = np.sign(x[mask]) * (
        threshold + (1.0 - threshold) * np.tanh(over)
    )
    return y


# ---------------------------------------------------------------------------
# Кольцевая модуляция («робот»)
# ---------------------------------------------------------------------------


class RingMod:
    def __init__(self, samplerate: int):
        self.sr = float(samplerate)
        self.phase = 0.0

    def process(self, x: np.ndarray, freq: float, mix: float) -> np.ndarray:
        if mix <= 0.0 or len(x) == 0:
            return x
        phase = self.phase + np.arange(len(x), dtype=np.float64) * (freq / self.sr)
        mod = np.cos(2.0 * np.pi * phase).astype(np.float32)
        self.phase = float((self.phase + len(x) * freq / self.sr) % 1.0)
        wet = x * mod
        return (x * (1.0 - mix) + wet * mix).astype(np.float32)


# ---------------------------------------------------------------------------
# Перегруз / дисторшн
# ---------------------------------------------------------------------------


def apply_drive(x: np.ndarray, amount: float) -> np.ndarray:
    """amount 0..100. 0 — выключено."""
    if amount <= 0.0 or len(x) == 0:
        return x
    drive = 1.0 + 0.25 * amount
    mix = min(1.0, amount / 100.0)
    wet = np.tanh(drive * x) / np.tanh(drive)
    return (x * (1.0 - mix) + wet * mix).astype(np.float32)


# ---------------------------------------------------------------------------
# Фильтры
# ---------------------------------------------------------------------------


class VoiceFilter:
    """Телефонный / глухой / тонкий фильтр (биквады scipy)."""

    def __init__(self, samplerate: int):
        self.sr = float(samplerate)
        self.mode = "none"
        self.sos = None
        self.zi = None

    def _build(self, mode: str):
        if mode == "phone":
            return butter(4, [300.0, 3400.0], btype="bandpass", fs=self.sr, output="sos")
        if mode == "muffled":
            return butter(2, 900.0, btype="lowpass", fs=self.sr, output="sos")
        if mode == "thin":
            return butter(2, 350.0, btype="highpass", fs=self.sr, output="sos")
        return None

    def process(self, x: np.ndarray, mode: str) -> np.ndarray:
        if mode not in FILTER_MODES:
            mode = "none"
        if mode != self.mode:
            self.mode = mode
            self.sos = self._build(mode)
            self.zi = None if self.sos is None else np.zeros((self.sos.shape[0], 2))

        if self.sos is None or len(x) == 0:
            return x

        y, self.zi = sosfilt(self.sos, x, zi=self.zi)
        return y.astype(np.float32)


# ---------------------------------------------------------------------------
# Эхо
# ---------------------------------------------------------------------------


class Echo:
    """Эхо с обратной связью. Читает/пишет блоками, без по-сэмплового цикла."""

    def __init__(self, samplerate: int, max_delay_s: float = 1.0):
        self.sr = float(samplerate)
        self.size = int(self.sr * max_delay_s) + 1
        self.buf = np.zeros(self.size, dtype=np.float32)
        self.w = 0

    def _write(self, x: np.ndarray) -> None:
        n = len(x)
        end = self.w + n
        if end <= self.size:
            self.buf[self.w:end] = x
        else:
            k = self.size - self.w
            self.buf[self.w:] = x[:k]
            self.buf[: end - self.size] = x[k:]
        self.w = end % self.size

    def process(
        self,
        x: np.ndarray,
        delay_ms: float,
        feedback: float,
        mix: float,
    ) -> np.ndarray:
        if len(x) == 0:
            return x

        delay = int(max(1.0, delay_ms) * self.sr / 1000.0)
        delay = min(delay, self.size - 2)
        n = len(x)

        start = self.w
        self._write(x)

        if mix <= 0.0:
            return x

        # Позиция каждого сэмпла минус задержка. Задержка всегда больше
        # размера блока, поэтому чтение не задевает только что записанный x.
        indices = (start + np.arange(n) - delay) % self.size
        wet = self.buf[indices].copy()

        y = x + float(feedback) * wet
        np.clip(y, -1.5, 1.5, out=y)
        self._write(y)  # перезаписываем текущий блок с учётом обратной связи

        return (x * (1.0 - mix) + wet * mix).astype(np.float32)


# ---------------------------------------------------------------------------
# Вся цепочка
# ---------------------------------------------------------------------------


class EffectChain:
    """Цепочка: низ -> наводки -> гейт -> шум -> питч -> робот -> фильтр -> драйв -> эхо."""

    def __init__(self, samplerate: int):
        self.sr = samplerate
        self.highpass = HighPass(samplerate)
        self.hum = HumFilter(samplerate)
        self.gate = NoiseGate(samplerate)
        self.denoise = NoiseSuppressor(samplerate)
        self.pitch = PitchShifter(samplerate)
        self.ring = RingMod(samplerate)
        self.vfilter = VoiceFilter(samplerate)
        self.echo = Echo(samplerate)

    def process(self, x: np.ndarray, p: dict) -> np.ndarray:
        x = np.asarray(x, dtype=np.float32)
        if len(x) == 0 or p.get("bypass", False):
            return x

        x = self.highpass.process(x, float(p.get("highpass", 80.0)))
        x = self.hum.process(x, str(p.get("hum", "off")))
        x = self.gate.process(x, p.get("gate_db", -50.0))
        x = self.denoise.process(x, float(p.get("noise_reduction", 0.0)))
        x = self.pitch.process(x, float(p.get("pitch", 0.0)))
        x = self.ring.process(
            x,
            float(p.get("robot_freq", 40.0)),
            float(p.get("robot_mix", 0.0)),
        )
        x = self.vfilter.process(x, str(p.get("filter", "none")))
        x = apply_drive(x, float(p.get("drive", 0.0)))
        x = self.echo.process(
            x,
            float(p.get("echo_delay_ms", 180.0)),
            float(p.get("echo_feedback", 0.35)),
            float(p.get("echo_mix", 0.0)),
        )

        volume = float(p.get("volume", 1.0))
        if volume != 1.0:
            x = x * volume

        return soft_limit(x)


# ---------------------------------------------------------------------------
# Ресемплер (на случай, если вход и выход работают на разных частотах)
# ---------------------------------------------------------------------------


class LinearResampler:
    """Линейная интерполяция. Для прототипа достаточно."""

    def __init__(
        self,
        sr_in: int = 48000,
        sr_out: int = 48000,
        step: float | None = None,
    ):
        # step — сколько входных сэмплов приходится на один выходной.
        self.step = float(step) if step else float(sr_in) / float(sr_out)
        self.buf = np.zeros(0, dtype=np.float32)
        self.pos = 0.0

    def reset(self) -> None:
        self.buf = np.zeros(0, dtype=np.float32)
        self.pos = 0.0

    def process(self, x: np.ndarray) -> np.ndarray:
        if abs(self.step - 1.0) < 1e-9:
            return x
        if len(x) == 0:
            return x

        self.buf = np.concatenate([self.buf, np.asarray(x, dtype=np.float32)])
        last = len(self.buf) - 1
        if self.pos >= last:
            return np.zeros(0, dtype=np.float32)

        count = int(np.floor((last - 1e-9 - self.pos) / self.step)) + 1
        positions = self.pos + self.step * np.arange(count, dtype=np.float64)
        i0 = np.floor(positions).astype(np.int64)
        frac = (positions - i0).astype(np.float32)
        i1 = np.minimum(i0 + 1, last)
        out = self.buf[i0] * (1.0 - frac) + self.buf[i1] * frac

        consumed = int(np.floor(positions[-1]))
        self.buf = self.buf[consumed:].copy()
        self.pos = float(positions[-1] - consumed)
        return out.astype(np.float32)
