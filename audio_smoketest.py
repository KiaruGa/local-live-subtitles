"""
Audio loopback smoke test: captures ~3 seconds of system sound and reports
whether PCM chunks arrive from the WASAPI loopback device.
Run:  python audio_smoketest.py
"""
import time

import numpy as np

from audio_capture import AudioStreamCapturer


def main():
    capturer = AudioStreamCapturer()
    print("Starting system loopback for 3 seconds...")
    capturer.start_system_loopback()

    chunks = []
    t0 = time.time()
    while time.time() - t0 < 3.0:
        chunk = capturer.get_audio_chunk()
        if chunk is not None:
            chunks.append(chunk)
        else:
            time.sleep(0.02)

    capturer.stop()

    if not chunks:
        print("AUDIO SMOKETEST FAILED: no audio chunks received")
        return 1

    total = sum(len(c) for c in chunks)
    peak = max(float(np.max(np.abs(c))) for c in chunks)
    print(f"AUDIO SMOKETEST OK: {len(chunks)} chunks, {total} samples, peak={peak:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
