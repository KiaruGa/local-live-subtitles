"""
Quick setup diagnostics for Local AI Live Subtitles.
Run:  python doctor.py

Checks Python packages, audio devices, ffmpeg/yt-dlp availability and
whether the local model folders exist. Does not download any models.
"""
import importlib
import shutil
import sys

OK = "[OK]"
FAIL = "[FAIL]"
WARN = "[WARN]"


def check_import(name, label=None):
    label = label or name
    try:
        mod = importlib.import_module(name)
        version = getattr(mod, "__version__", "")
        print(f"{OK} {label} {version}".rstrip())
        return True
    except Exception as e:  # noqa: BLE001
        print(f"{FAIL} {label}: {e}")
        return False


def main():
    failures = 0
    print(f"Python {sys.version.split()[0]}\n")

    print("--- Packages ---")
    for name, label in (
        ("numpy", None),
        ("PyQt6", None),
        ("soundcard", None),
        ("faster_whisper", "faster-whisper"),
        ("ctranslate2", None),
        ("sentencepiece", None),
        ("sacremoses", None),
    ):
        if not check_import(name, label):
            failures += 1

    print("\n--- External tools ---")
    for tool in ("ffmpeg", "yt-dlp", "streamlink"):
        path = shutil.which(tool)
        if path:
            print(f"{OK} {tool}: {path}")
        else:
            print(f"{WARN} {tool} not found (optional; only needed for URL mode)")

    print("\n--- Audio devices (WASAPI loopback) ---")
    try:
        import soundcard as sc

        speaker = sc.default_speaker()
        print(f"{OK} Default speaker: {speaker.name}")
        try:
            mic = sc.get_microphone(id=speaker.name, include_loopback=True)
            print(f"{OK} Loopback capture device: {mic.name}")
        except Exception as e:  # noqa: BLE001
            print(f"{FAIL} Loopback device: {e}")
            failures += 1
    except Exception as e:  # noqa: BLE001
        print(f"{FAIL} soundcard init: {e}")
        failures += 1

    print("\n--- Local models ---")
    from translator_engine import (
        find_translation_model,
        find_whisper_model,
        app_models_root,
    )

    resolved = find_translation_model()
    if resolved:
        print(f"{OK} Translation model: {resolved}")
    else:
        print(
            f"{WARN} Translation model not found - run 'python scripts/prepare_models.py'"
        )

    whisper = find_whisper_model("base.en")
    if whisper:
        print(f"{OK} Whisper base.en: {whisper}")
    else:
        print(f"{WARN} Whisper base.en not prepared (will download on first run)")
    print(f"     Model directory: {app_models_root()}")

    print()
    if failures:
        print(f"Result: {failures} problem(s) found.")
        return 1
    print("Result: all critical checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
