import sys
import numpy as np
import sounddevice as sd

SR = 48000
DUR = 1.0

out_idx = in_idx = None
for i, d in enumerate(sd.query_devices()):
    name = d["name"]
    host = sd.query_hostapis(d["hostapi"])["name"]
    if "CABLE Input" in name and "WASAPI" in host and d["max_output_channels"] >= 1:
        out_idx = i
    if "CABLE Output" in name and "WASAPI" in host and d["max_input_channels"] >= 1:
        in_idx = i

print("out:", out_idx, sd.query_devices(out_idx)["name"] if out_idx is not None else None)
print("in :", in_idx, sd.query_devices(in_idx)["name"] if in_idx is not None else None)
if out_idx is None or in_idx is None:
    print("FAIL: cable endpoints not found")
    sys.exit(1)

t = np.arange(int(SR * DUR)) / SR
tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

rec = np.zeros((int(SR * DUR), 1), dtype=np.float32)

def cb(indata, frames, time_info, status):
    global rec
    if status:
        print("  status:", status)
    n = min(len(indata), len(rec))
    rec[:n] = indata[:n]

try:
    with sd.InputStream(device=in_idx, channels=1, samplerate=SR, dtype="float32", callback=cb):
        sd.play(tone, samplerate=SR, device=out_idx, blocking=True)
        sd.wait()
except Exception as e:
    print("FAIL:", e)
    sys.exit(1)

rms = float(np.sqrt(np.mean(rec ** 2)))
peak = float(np.max(np.abs(rec)))
print(f"recorded rms={rms:.5f} peak={peak:.5f}")
if rms < 0.01:
    print("FAIL: no signal through cable")
    sys.exit(1)
print("PASS: signal loops through CABLE Input -> CABLE Output")
