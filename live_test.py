"""
Live loopback diagnostic: captures 20 s of system audio, prints chunk RMS
statistics and any subtitles produced by the engine.

Run while an English stream is playing:
    python live_test.py [seconds] [model]
"""
import sys
import time

import numpy as np

from audio_capture import AudioStreamCapturer
from translator_engine import LocalTranslatorEngine


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 20.0
    model = sys.argv[2] if len(sys.argv) > 2 else "base.en"

    capturer = AudioStreamCapturer()
    engine = LocalTranslatorEngine(model_size=model)

    results = []
    engine.callback = lambda en, ru: (
        results.append((en, ru)),
        print(f"[SUB] {en}  ->  {ru}"),
    )

    print(f"Loading {model}...")
    engine.load_models()
    print(f"Capturing {seconds:.0f}s from system loopback...")
    capturer.start_system_loopback()

    t0 = time.time()
    chunks = 0
    rms_values = []
    last_report = t0
    while time.time() - t0 < seconds:
        chunk = capturer.get_audio_chunk()
        if chunk is not None:
            chunks += 1
            rms_values.append(float(np.sqrt(np.mean(chunk ** 2))))
            engine.process_audio_chunk(chunk)
        else:
            time.sleep(0.01)
        if time.time() - last_report >= 5.0:
            recent = rms_values[-500:] or [0.0]
            print(f"  ... {time.time()-t0:4.1f}s | chunks={chunks} | "
                  f"rms(avg)={np.mean(recent):.5f} rms(max)={np.max(recent):.5f}")
            last_report = time.time()

    engine.flush()
    capturer.stop()

    print(f"\nTotal chunks: {chunks}")
    if rms_values:
        print(f"Chunk RMS: avg={np.mean(rms_values):.5f} max={np.max(rms_values):.5f}")
    print(f"Subtitles produced: {len(results)}")
    for en, ru in results:
        print(f"  EN: {en}\n  RU: {ru}")
    return 0 if results else 2


if __name__ == "__main__":
    raise SystemExit(main())
