"""
Headless self-test: verifies local models load and translation/STT pipeline works.
Run:  python selftest.py
Downloads models on first run (MarianMT en->ru + faster-whisper tiny.en).
"""
import numpy as np

from translator_engine import LocalTranslatorEngine


def main():
    print("== Loading models ==")
    engine = LocalTranslatorEngine(model_size="tiny.en", device="cpu", compute_type="int8")
    engine.load_models()

    print("\n== Translation test ==")
    samples = [
        "Hello everyone, welcome back to the stream.",
        "Today we are going to play a new game.",
    ]
    for text in samples:
        ru = engine.translate_text(text)
        print(f"EN: {text}")
        print(f"RU: {ru}\n")

    print("== STT pipeline test (synthetic audio) ==")
    # 2 seconds of a 440 Hz tone: verifies the transcription call path does not crash.
    sr = 16000
    t = np.linspace(0, 2.0, sr * 2, endpoint=False)
    tone = 0.1 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    try:
        segments, info = engine.whisper_model.transcribe(
            tone, beam_size=1, language="en", vad_filter=True
        )
        text = " ".join(s.text.strip() for s in segments)
        print(f"STT ok (lang={info.language}, prob={info.language_probability:.2f}), text='{text}'")
    except Exception as e:  # noqa: BLE001
        print(f"STT FAILED: {e}")
        return 1

    print("\nSELFTEST OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
