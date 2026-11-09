"""
End-to-end STT + translation test using a real speech WAV file.
Generates nothing by itself: expects ./sample.wav (16 kHz mono 16-bit PCM),
created by the companion PowerShell TTS command.

Run:  python e2e_test.py [path-to-wav]
Writes detected subtitles to e2e_result.txt (UTF-8).
"""
import sys
import wave

import numpy as np

from translator_engine import LocalTranslatorEngine


def read_wav_mono16k(path):
    with wave.open(path, "rb") as w:
        assert w.getnchannels() == 1, "expected mono wav"
        assert w.getsampwidth() == 2, "expected 16-bit wav"
        sr = w.getframerate()
        raw = w.readframes(w.getnframes())
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if sr != 16000:
        # simple linear resample (adequate for this smoke test)
        n = int(len(data) * 16000 / sr)
        data = np.interp(np.linspace(0, len(data), n, endpoint=False),
                         np.arange(len(data)), data).astype(np.float32)
    return data


def main():
    wav_path = sys.argv[1] if len(sys.argv) > 1 else "sample.wav"
    model_size = sys.argv[2] if len(sys.argv) > 2 else "tiny.en"
    audio = read_wav_mono16k(wav_path)
    print(f"Loaded {len(audio)/16000:.1f}s of audio from {wav_path}")

    results = []
    engine = LocalTranslatorEngine(model_size=model_size, device="cpu", compute_type="int8")
    engine.callback = lambda en, ru: results.append((en, ru))
    engine.load_models()

    # Feed the audio in the same 0.5 s chunks the live capturer produces.
    chunk = int(16000 * 0.5)
    for i in range(0, len(audio), chunk):
        engine.process_audio_chunk(audio[i:i + chunk])
    engine.flush()

    lines = [f"EN: {en}\nRU: {ru}" for en, ru in results]
    text = "\n\n".join(lines) if lines else "(no subtitles produced)"
    with open("e2e_result.txt", "w", encoding="utf-8") as f:
        f.write(text + "\n")
    print(text)

    if not results:
        print("\nE2E FAILED: no subtitles produced")
        return 1
    print("\nE2E OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
