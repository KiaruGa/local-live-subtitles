#!/usr/bin/env python3
"""Prepare the local models used by Local Live Subtitles.

Creates:
  models/whisper/base.en/      flat CTranslate2 Whisper model (STT)
  models/opus-mt-en-ru-ct2/    OPUS-MT en->ru converted to CTranslate2 int8

The translation conversion needs PyTorch and Transformers, which are only
build-time dependencies (see requirements-dev.txt). The application itself
runs on CTranslate2 alone.

Usage:
  python scripts/prepare_models.py
  python scripts/prepare_models.py --force
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
WHISPER_SIZE = "base.en"
OPUS_REPO = "Helsinki-NLP/opus-mt-en-ru"
OPUS_DIR = MODELS_DIR / "opus-mt-en-ru-ct2"
HF_CACHE = MODELS_DIR / "marian"

COPY_FILES = [
    "source.spm",
    "target.spm",
    "vocab.json",
    "tokenizer_config.json",
    "generation_config.json",
]


def _human_size(path: Path) -> str:
    total = sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    return f"{total / (1024 ** 3):.2f} GB" if total > 1024 ** 3 else f"{total / 1024 ** 2:.1f} MB"


def _copy_cached_whisper(size: str, target: Path) -> bool:
    """Reuses an existing Hugging Face cache instead of downloading again."""
    cache_root = MODELS_DIR / "whisper" / f"models--Systran--faster-whisper-{size}"
    for snapshot in sorted((cache_root / "snapshots").glob("*/model.bin"), reverse=True):
        source = snapshot.parent
        for item in source.iterdir():
            if item.is_file():
                shutil.copy2(item, target / item.name)
        return (target / "model.bin").exists()
    return False


def prepare_whisper(force: bool) -> Path:
    from faster_whisper.utils import download_model

    target = MODELS_DIR / "whisper" / WHISPER_SIZE
    if (target / "model.bin").exists() and not force:
        print(f"[models] Whisper {WHISPER_SIZE} already prepared ({_human_size(target)}).")
        return target

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    if not force and _copy_cached_whisper(WHISPER_SIZE, target):
        print(f"[models] Reused cached Whisper {WHISPER_SIZE}: {target}")
        return target

    print(f"[models] Downloading Whisper {WHISPER_SIZE}...")
    download_model(WHISPER_SIZE, output_dir=str(target))
    print(f"[models] Whisper ready: {target} ({_human_size(target)})")
    return target


def prepare_translation(force: bool) -> Path:
    if (OPUS_DIR / "model.bin").exists() and not force:
        print(f"[models] Translation model already prepared ({_human_size(OPUS_DIR)}).")
        return OPUS_DIR

    try:
        import torch  # noqa: F401
        from ctranslate2.converters import TransformersConverter
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        sys.exit(
            f"[models] Missing build dependency: {exc}\n"
            "Install build requirements first: pip install -r requirements-dev.txt"
        )

    HF_CACHE.mkdir(parents=True, exist_ok=True)
    print(f"[models] Downloading {OPUS_REPO} from Hugging Face...")
    snapshot = Path(
        snapshot_download(
            OPUS_REPO,
            cache_dir=str(HF_CACHE),
            allow_patterns=["pytorch_model.bin", "*.spm", "*.json"],
        )
    )

    if OPUS_DIR.exists():
        shutil.rmtree(OPUS_DIR)
    print("[models] Converting OPUS-MT to CTranslate2 int8...")
    converter = TransformersConverter(str(snapshot))
    converter.convert(
        str(OPUS_DIR),
        quantization="int8",
        force=True,
        copy_files=COPY_FILES,
    )
    print(f"[models] Translation model ready: {OPUS_DIR} ({_human_size(OPUS_DIR)})")
    return OPUS_DIR


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="rebuild models even if present")
    parser.add_argument(
        "--translation-only", action="store_true", help="skip the Whisper download"
    )
    parser.add_argument("--whisper-only", action="store_true", help="skip translation model")
    args = parser.parse_args()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    if not args.whisper_only:
        prepare_whisper(args.force)
    if not args.translation_only:
        prepare_translation(args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
