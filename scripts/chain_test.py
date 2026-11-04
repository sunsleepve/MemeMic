"""Сквозная проверка: микрофон -> ченджер -> CABLE Input -> запись с CABLE Output."""

import pathlib
import sys
import time

import numpy as np
import sounddevice as sd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from mememic import devices as dev_mod
from mememic.dsp import PRESETS
from mememic.engine import AudioEngine

SR = 48000
DUR = 4.0

ins, outs = dev_mod.list_devices()
mic = next((d for d in ins if "USB Condenser" in d.name), None)
cable_out = dev_mod.find_virtual_output(outs)
cable_in = next((d for d in ins if "CABLE Output" in d.name), None)
if mic is None or cable_out is None or cable_in is None:
    print("FAIL: не найдены нужные устройства")
    sys.exit(1)

print("микрофон :", mic.name)
print("выход    :", cable_out.name)

rec = np.zeros((int(SR * DUR), 1), dtype=np.float32)
pos = {"n": 0}


def cb(indata, frames, time_info, status):
    n = min(len(indata), len(rec) - pos["n"])
    if n > 0:
        rec[pos["n"]:pos["n"] + n] = indata[:n]
        pos["n"] += n


params = dict(PRESETS["Робот"]) if "Робот" in PRESETS else dict(list(PRESETS.values())[0])
engine = AudioEngine()
ok, msg = engine.start(mic, cable_out, params)
print("engine:", ok, msg)
if not ok:
    sys.exit(1)

try:
    with sd.InputStream(device=cable_in.indices[0], channels=1, samplerate=SR,
                        dtype="float32", callback=cb):
        time.sleep(DUR)
finally:
    engine.stop()

peak_in = float(getattr(engine, "in_level", 0.0))
rms = float(np.sqrt(np.mean(rec[:pos["n"]] ** 2))) if pos["n"] else 0.0
peak = float(np.max(np.abs(rec[:pos["n"]]))) if pos["n"] else 0.0
print(f"записано с кабеля: {pos['n'] / SR:.2f} c, rms={rms:.5f}, peak={peak:.5f}")
print(f"underruns={engine.underruns}")
if pos["n"] == 0:
    print("FAIL: кабель ничего не получил")
    sys.exit(1)
print("PASS: ченджер пишет в кабель" + (" (была тишина — микрофон молчал)" if rms < 0.002 else ""))
