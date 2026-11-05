"""Аудио-движок: микрофон -> эффекты -> виртуальный микрофон (кабель).

Вход и выход открываются как два независимых потока. Это позволяет выбирать
устройства из разных host API (например, микрофон в WASAPI, а VB-Cable в MME)
и не зависеть от того, умеет ли PortAudio duplex на этой паре устройств.
"""

from __future__ import annotations

import queue

import numpy as np
import sounddevice as sd

from .dsp import DEFAULT_PARAMS, EffectChain, LinearResampler
from .devices import DeviceInfo

CHUNK = 512          # сэмплов на блок (~10.7 мс при 48 кГц)
QUEUE_BLOCKS = 14    # максимум блоков в очереди (~150 мс страховки)

LATENCY_MODES = {
    # block — сэмплов на колбэк, queue — сколько блоков держим в запасе.
    "low": {"block": 256, "queue": 4, "latency": "low"},
    "balanced": {"block": 512, "queue": 8, "latency": "high"},
    "safe": {"block": 1024, "queue": 16, "latency": "high"},
}


class AudioEngine:
    def __init__(self, latency_mode: str = "low") -> None:
        self.params: dict = dict(DEFAULT_PARAMS)
        self.chain: EffectChain | None = None
        self.block = CHUNK
        self.queue_blocks = QUEUE_BLOCKS
        self.portaudio_latency = "high"
        self.latency_mode = "balanced"
        self.set_latency(latency_mode)

        self._queue: queue.Queue[np.ndarray] = queue.Queue(
            maxsize=self.queue_blocks
        )
        self._carry = np.zeros(0, dtype=np.float32)
        self._last_out: np.ndarray | None = None
        self._resampler: LinearResampler | None = None
        self._in_stream: sd.InputStream | None = None
        self._out_stream: sd.OutputStream | None = None

        self.running = False
        self.in_sr = 0
        self.out_sr = 0
        self.in_level = 0.0
        self.out_level = 0.0
        self.underruns = 0
        self.last_error = ""

        self.in_name = ""
        self.out_name = ""

    def set_latency(self, mode: str) -> None:
        """Выбрать режим задержки. Применяется при следующем старте."""
        cfg = LATENCY_MODES.get(mode, LATENCY_MODES["balanced"])
        self.latency_mode = mode if mode in LATENCY_MODES else "balanced"
        self.block = int(cfg["block"])
        self.queue_blocks = int(cfg["queue"])
        self.portaudio_latency = str(cfg["latency"])

    # ------------------------------------------------------------------
    # Колбэки
    # ------------------------------------------------------------------
    def _input_cb(self, indata, frames, time_info, status) -> None:
        try:
            x = indata[:, 0].copy()
            self.in_level = float(np.sqrt(np.mean(x * x) + 1e-12))

            chain = self.chain
            y = chain.process(x, self.params) if chain is not None else x

            try:
                self._queue.put_nowait(y)
            except queue.Full:
                # Отстаём — выбрасываем самый старый блок, чтобы не копить
                # задержку. Небольшой щелчок лучше, чем растущий лаг.
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self._queue.put_nowait(y)
                except queue.Full:
                    pass
        except Exception as exc:  # чтобы не убить аудио-поток
            self.last_error = f"input: {exc!r}"

    def _output_cb(self, outdata, frames, time_info, status) -> None:
        try:
            while len(self._carry) < frames:
                try:
                    chunk = self._queue.get_nowait()
                except queue.Empty:
                    break
                if self._resampler is not None:
                    chunk = self._resampler.process(chunk)
                if len(chunk):
                    self._carry = np.concatenate((self._carry, chunk))

            if len(self._carry) >= frames:
                out = self._carry[:frames]
                self._carry = self._carry[frames:]
            else:
                n = len(self._carry)
                out = np.zeros(frames, dtype=np.float32)
                if n:
                    out[:n] = self._carry
                # Не оставляем слышимую «дыру»: добиваем нехватку
                # затухающим повтором последнего блока (как PLC в кодеках).
                if n < frames and self._last_out is not None:
                    tail = frames - n
                    ramp = np.linspace(0.8, 0.25, tail, dtype=np.float32)
                    out[n:] = self._last_out[:tail] * ramp
                self._carry = np.zeros(0, dtype=np.float32)
                self.underruns += 1

            if len(out) == frames:
                self._last_out = out.copy()

            outdata[:, 0] = out
            if outdata.shape[1] > 1:
                outdata[:, 1:] = out[:, None]

            self.out_level = float(np.sqrt(np.mean(out * out) + 1e-12))
        except Exception as exc:
            self.last_error = f"output: {exc!r}"
            outdata.fill(0.0)

    # ------------------------------------------------------------------
    # Открытие устройств
    # ------------------------------------------------------------------
    @staticmethod
    def _rate_candidates(index: int, prefer: int | None = None) -> list[int]:
        try:
            default = int(round(float(sd.query_devices(index)["default_samplerate"])))
        except Exception:
            default = 48000
        rates = []
        for rate in (prefer, 48000, default, 44100, 32000):
            if rate and rate > 0 and rate not in rates:
                rates.append(int(rate))
        return rates

    def _open_input(self, device: DeviceInfo) -> tuple[sd.InputStream | None, int, list[str]]:
        errors: list[str] = []
        for index in device.indices:
            for sr in self._rate_candidates(index):
                for channels in (1, 2):
                    try:
                        stream = sd.InputStream(
                            device=index,
                            channels=channels,
                            samplerate=sr,
                            blocksize=self.block,
                            latency=self.portaudio_latency,
                            dtype="float32",
                            callback=self._input_cb,
                        )
                        return stream, sr, errors
                    except Exception as exc:
                        errors.append(f"in #{index} @ {sr}/{channels}ch: {exc}")
        return None, 0, errors

    def _open_output(
        self,
        device: DeviceInfo,
        prefer_sr: int,
    ) -> tuple[sd.OutputStream | None, int, list[str]]:
        errors: list[str] = []
        for index in device.indices:
            for sr in self._rate_candidates(index, prefer=prefer_sr):
                for channels in (1, 2):
                    try:
                        stream = sd.OutputStream(
                            device=index,
                            channels=channels,
                            samplerate=sr,
                            blocksize=self.block,
                            latency=self.portaudio_latency,
                            dtype="float32",
                            callback=self._output_cb,
                        )
                        return stream, sr, errors
                    except Exception as exc:
                        errors.append(f"out #{index} @ {sr}/{channels}ch: {exc}")
        return None, 0, errors

    # ------------------------------------------------------------------
    # Публичное API
    # ------------------------------------------------------------------
    def start(
        self,
        input_device: DeviceInfo,
        output_device: DeviceInfo,
        params: dict | None = None,
    ) -> tuple[bool, str]:
        self.stop()
        if params is not None:
            self.params = params

        self.last_error = ""
        self.underruns = 0
        self._queue = queue.Queue(maxsize=self.queue_blocks)
        self._carry = np.zeros(0, dtype=np.float32)

        in_stream, in_sr, in_errors = self._open_input(input_device)
        if in_stream is None:
            detail = in_errors[-1] if in_errors else "нет доступных устройств"
            return False, f"Не удалось открыть микрофон «{input_device.name}».\n{detail}"

        self.chain = EffectChain(in_sr)

        out_stream, out_sr, out_errors = self._open_output(output_device, in_sr)
        if out_stream is None:
            _close_quietly(in_stream)
            self.chain = None
            detail = out_errors[-1] if out_errors else "нет доступных устройств"
            return False, f"Не удалось открыть выход «{output_device.name}».\n{detail}"

        self._resampler = (
            LinearResampler(in_sr, out_sr) if in_sr != out_sr else None
        )

        try:
            out_stream.start()
            in_stream.start()
        except Exception as exc:
            _close_quietly(out_stream)
            _close_quietly(in_stream)
            self.chain = None
            self._resampler = None
            return False, f"Не удалось запустить потоки: {exc}"

        self._in_stream = in_stream
        self._out_stream = out_stream
        self.in_sr = in_sr
        self.out_sr = out_sr
        self.in_name = input_device.name
        self.out_name = output_device.name
        self.running = True

        if in_sr == out_sr:
            fmt = f"{in_sr} Гц"
        else:
            fmt = f"{in_sr} Гц → {out_sr} Гц"
        return True, f"Работает · {fmt}"

    def stop(self) -> None:
        self.running = False
        if self._in_stream is not None:
            _close_quietly(self._in_stream)
            self._in_stream = None
        if self._out_stream is not None:
            _close_quietly(self._out_stream)
            self._out_stream = None

        self.chain = None
        self._resampler = None
        self._last_out = None
        self._queue = queue.Queue(maxsize=self.queue_blocks)
        self._carry = np.zeros(0, dtype=np.float32)
        self.in_level = 0.0
        self.out_level = 0.0

    def set_params(self, params: dict) -> None:
        self.params = params


def _close_quietly(stream) -> None:
    try:
        stream.stop()
    except Exception:
        pass
    try:
        stream.close()
    except Exception:
        pass
