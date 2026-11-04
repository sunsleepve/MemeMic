"""Проверки DSP без реального аудио-железа."""

from __future__ import annotations

import unittest

import numpy as np

from mememic import dsp

SR = 48000
BLOCK = 512


def run_chain(signal: np.ndarray, params: dict, sr: int = SR):
    chain = dsp.EffectChain(sr)
    out = []
    for start in range(0, len(signal) - BLOCK + 1, BLOCK):
        out.append(chain.process(signal[start:start + BLOCK], params))
    return np.concatenate(out)


def dominant_freq(signal: np.ndarray, sr: int = SR) -> float:
    window = np.hanning(len(signal))
    spectrum = np.abs(np.fft.rfft(signal * window))
    freqs = np.fft.rfftfreq(len(signal), 1.0 / sr)
    return float(freqs[int(np.argmax(spectrum))])


def sine(freq: float, seconds: float, sr: int = SR) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    return (0.5 * np.sin(2.0 * np.pi * freq * t)).astype(np.float32)


def only_pitch(semitones: float) -> dict:
    params = dict(dsp.DEFAULT_PARAMS)
    params.update({"pitch": semitones, "gate_db": -80.0})
    return params


class PitchShifterTest(unittest.TestCase):
    def test_octave_up(self):
        out = run_chain(sine(440.0, 2.0), only_pitch(12.0))
        measured = dominant_freq(out[SR // 2:])
        self.assertAlmostEqual(measured, 880.0, delta=15.0)

    def test_octave_down(self):
        out = run_chain(sine(440.0, 2.0), only_pitch(-12.0))
        measured = dominant_freq(out[SR // 2:])
        self.assertAlmostEqual(measured, 220.0, delta=15.0)

    def test_fifth_up(self):
        out = run_chain(sine(300.0, 2.0), only_pitch(7.0))
        measured = dominant_freq(out[SR // 2:])
        self.assertAlmostEqual(measured, 300.0 * 2 ** (7 / 12), delta=20.0)

    def test_zero_shift_keeps_signal(self):
        signal = sine(440.0, 1.0)
        out = run_chain(signal, only_pitch(0.0))
        np.testing.assert_allclose(out, signal[: len(out)], atol=1e-6)

    def test_no_nan_and_no_clipping(self):
        out = run_chain(sine(200.0, 2.0), only_pitch(-12.0))
        self.assertTrue(np.all(np.isfinite(out)))
        self.assertLessEqual(float(np.max(np.abs(out))), 1.0)

    def test_level_is_preserved(self):
        signal = sine(440.0, 2.0)
        for semitones in (12.0, 7.0, -7.0, -12.0):
            with self.subTest(semitones=semitones):
                out = run_chain(signal, only_pitch(semitones))[SR // 2:]
                rms = float(np.sqrt(np.mean(out * out)))
                self.assertAlmostEqual(rms / 0.3536, 1.0, delta=0.2)


class GateTest(unittest.TestCase):
    def test_closes_on_silence_and_opens_on_voice(self):
        gate = dsp.NoiseGate(SR)
        noise = (np.random.default_rng(1).normal(0, 0.0005, BLOCK)).astype(np.float32)
        for _ in range(30):
            gate.process(noise, -40.0)
        self.assertLess(gate.gain, 0.15)

        loud = sine(200.0, BLOCK / SR)
        for _ in range(10):
            gate.process(loud, -40.0)
        self.assertGreater(gate.gain, 0.8)

    def test_disabled_gate_is_transparent(self):
        gate = dsp.NoiseGate(SR)
        x = np.zeros(BLOCK, dtype=np.float32)
        np.testing.assert_allclose(gate.process(x, -80.0), x)


class EchoTest(unittest.TestCase):
    def test_impulse_appears_after_delay(self):
        echo = dsp.Echo(SR)
        impulse = np.zeros(SR, dtype=np.float32)
        impulse[0] = 0.5
        out = echo.process(impulse, 100.0, 0.0, 1.0)
        peak = int(np.argmax(np.abs(out[10:]))) + 10
        self.assertAlmostEqual(peak / SR, 0.1, delta=0.01)

    def test_no_echo_when_mix_zero(self):
        echo = dsp.Echo(SR)
        x = sine(300.0, 0.2)
        out = echo.process(x, 100.0, 0.5, 0.0)
        np.testing.assert_allclose(out, x)


class ResamplerTest(unittest.TestCase):
    def test_length_and_frequency(self):
        resampler = dsp.LinearResampler(SR, 44100)
        signal = sine(500.0, 1.0)
        chunks = [
            resampler.process(signal[i:i + BLOCK])
            for i in range(0, len(signal) - BLOCK, BLOCK)
        ]
        out = np.concatenate(chunks)
        self.assertAlmostEqual(len(out) / 44100.0, 1.0, delta=0.05)
        self.assertAlmostEqual(dominant_freq(out, 44100), 500.0, delta=20.0)

    def test_identity_rate(self):
        resampler = dsp.LinearResampler(SR, SR)
        x = sine(200.0, 0.1)
        np.testing.assert_allclose(resampler.process(x), x)


class PresetTest(unittest.TestCase):
    def test_all_presets_are_stable(self):
        rng = np.random.default_rng(42)
        signal = (0.2 * rng.standard_normal(SR)).astype(np.float32)

        for name in dsp.PRESETS:
            with self.subTest(preset=name):
                params = dsp.preset_params(name)
                out = run_chain(signal, params)
                self.assertGreater(len(out), 0)
                expected = len(signal) // BLOCK * BLOCK
                # Пипетка питч-шифтера «съедает» часть сэмплов на старте
                # (это его задержка, а не потеря длительности).
                self.assertLess(abs(len(out) - expected), expected * 0.05)
                self.assertTrue(np.all(np.isfinite(out)))
                self.assertLessEqual(float(np.max(np.abs(out))), 1.0)

    def test_preset_does_not_mutate_defaults(self):
        before = dict(dsp.DEFAULT_PARAMS)
        dsp.preset_params("Демон")
        self.assertEqual(dsp.DEFAULT_PARAMS, before)


if __name__ == "__main__":
    unittest.main()
