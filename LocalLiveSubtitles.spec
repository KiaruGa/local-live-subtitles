# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build definition for Local Live Subtitles (one-folder build)."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH)
NAME = "LocalLiveSubtitles"


def add_tree(source: Path, destination: str) -> list[tuple[str, str]]:
    """Adds every file of a directory, preserving its structure.

    PyInstaller treats the second tuple item as a destination *directory*, so
    the file name is appended automatically.
    """
    entries: list[tuple[str, str]] = []
    if not source.is_dir():
        return entries
    for path in source.rglob("*"):
        if path.is_file():
            entries.append(
                (str(path), str(Path(destination) / path.parent.relative_to(source)))
            )
    return entries


datas: list[tuple[str, str]] = [
    (str(ROOT / "assets" / "app.ico"), "assets"),
    (str(ROOT / "LICENSE"), "."),
]
datas += add_tree(ROOT / "models" / "opus-mt-en-ru-ct2", "models/opus-mt-en-ru-ct2")
datas += add_tree(ROOT / "models" / "whisper" / "base.en", "models/whisper/base.en")
datas += collect_data_files("faster_whisper")

binaries = collect_dynamic_libs("ctranslate2")

hiddenimports = [
    "ctranslate2",
    "sentencepiece",
    "sacremoses",
    "soundcard.mediafoundation",
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch",
        "transformers",
        "tensorflow",
        "scipy",
        "pandas",
        "matplotlib",
        "IPython",
        "tkinter",
        "pytest",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "app.ico"),
    version=str(ROOT / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=NAME,
)
