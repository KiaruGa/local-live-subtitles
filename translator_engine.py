"""Local speech recognition and English -> Russian translation.

STT:      faster-whisper (CTranslate2 Whisper).
Translation: OPUS-MT en-ru converted to CTranslate2 (int8 on CPU).
No PyTorch or Transformers are required at runtime.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

TRANSLATION_MODEL_DIR = "opus-mt-en-ru-ct2"


def app_models_root() -> Path:
    """Writable directory for downloaded/cached models."""
    override = os.environ.get("LOCAL_SUBTITLES_MODELS")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "LocalLiveSubtitles" / "models"
    return Path(__file__).resolve().parent / "models"


def bundled_models_root() -> Path | None:
    """Models shipped inside the PyInstaller bundle (read-only)."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidate = base / "models"
        if candidate.exists():
            return candidate
    return None


def _model_candidates(*relative: str) -> list[Path]:
    candidates = [app_models_root().joinpath(*relative)]
    bundled = bundled_models_root()
    if bundled is not None:
        candidates.append(bundled.joinpath(*relative))
    return candidates


def find_translation_model() -> Path | None:
    """Looks for the converted OPUS-MT model in all known locations."""
    for candidate in _model_candidates(TRANSLATION_MODEL_DIR):
        if (candidate / "model.bin").exists():
            return candidate
    return None


def find_whisper_model(model_size: str) -> Path | None:
    """Looks for a ready-to-use flat CTranslate2 Whisper model."""
    for candidate in _model_candidates("whisper", model_size):
        if (candidate / "model.bin").exists():
            return candidate
    return None


def _ct2_device() -> str:
    """Resolves the CTranslate2 device.

    The distributed build ships CPU libraries only, so "auto" means CPU.
    Set LOCAL_SUBTITLES_DEVICE=cuda when running from source with CUDA-enabled
    CTranslate2 libraries installed.
    """
    requested = os.environ.get("LOCAL_SUBTITLES_DEVICE", "auto").strip().lower()
    if requested in ("cpu", "cuda"):
        return requested
    return "cpu"


class LocalTranslatorEngine:
    """Real-time English speech-to-text with Russian translation."""

    def __init__(self, model_size="base.en", device="auto", compute_type=None, target_lang="ru"):
        self.model_size = model_size
        self.device = _ct2_device() if device in (None, "auto") else device
        # int8 is fast and accurate enough on CPU; float16 only makes sense on GPU.
        if compute_type is None:
            compute_type = "float16" if self.device == "cuda" else "int8"
        self.compute_type = compute_type
        self.target_lang = target_lang

        self.whisper_model = None
        self.translator = None
        self.spm_source = None
        self.spm_target = None
        self._normalize = None
        self.is_loaded = False
        self.is_running = False

        self.audio_buffer = np.array([], dtype=np.float32)
        # Flush a segment when there is speech followed by a short pause,
        # or when the segment reaches the maximum length.
        self.min_buffer_size = int(16000 * 1.0)   # min speech before a flush
        self.max_buffer_size = int(16000 * 5.0)   # hard cap on segment length
        self.silence_threshold = 0.0025           # RMS below this = silence
        self.silence_samples = 0                  # trailing silence in buffer
        self.pause_samples = int(16000 * 0.30)    # pause that ends a phrase

        self.callback = None
        self._worker_thread = None

    # ------------------------------------------------------------- loading
    def load_models(self):
        """Loads faster-whisper and the CTranslate2 translation model."""
        print(f"[Engine] Loading faster-whisper model: {self.model_size} ({self.device})...")
        local_whisper = find_whisper_model(self.model_size)
        model_ref = str(local_whisper) if local_whisper is not None else self.model_size
        whisper_cache = None
        if local_whisper is None:
            whisper_cache = app_models_root() / "whisper"
            whisper_cache.mkdir(parents=True, exist_ok=True)

        def create(device: str, compute_type: str):
            kwargs = {"device": device, "compute_type": compute_type}
            if whisper_cache is not None:
                kwargs["download_root"] = str(whisper_cache)
            return WhisperModel(model_ref, **kwargs)

        try:
            self.whisper_model = create(self.device, self.compute_type)
        except Exception as exc:  # noqa: BLE001
            if self.device == "cpu":
                raise
            print(f"[Engine] Whisper could not start on {self.device} ({exc}). Falling back to CPU...")
            self.device = "cpu"
            self.compute_type = "int8"
            self.whisper_model = create("cpu", "int8")

        self._load_translation_model()
        self.is_loaded = True

    def _load_translation_model(self):
        model_dir = find_translation_model()
        if model_dir is None:
            print(
                "[Engine Warning] Translation model not found. "
                "Run 'python scripts/prepare_models.py' once, or reinstall the app. "
                "Falling back to the English transcript."
            )
            return

        print(f"[Engine] Loading local OPUS-MT (en-ru, CTranslate2) from {model_dir}...")
        try:
            import ctranslate2
            import sentencepiece as spm

            device = self.device if self.device in ("cpu", "cuda") else "cpu"

            def make(dev: str):
                return ctranslate2.Translator(
                    str(model_dir),
                    device=dev,
                    compute_type="float16" if dev == "cuda" else "int8",
                    inter_threads=1,
                    intra_threads=max(1, min(4, (os.cpu_count() or 2) // 2)),
                )

            try:
                self.translator = make(device)
            except Exception as exc:  # noqa: BLE001
                if device == "cpu":
                    raise
                print(f"[Engine] Translation on {device} failed ({exc}). Falling back to CPU...")
                self.translator = make("cpu")
            self.spm_source = spm.SentencePieceProcessor(
                model_file=str(model_dir / "source.spm")
            )
            self.spm_target = spm.SentencePieceProcessor(
                model_file=str(model_dir / "target.spm")
            )
            try:
                from sacremoses import MosesPunctNormalizer

                self._normalize = MosesPunctNormalizer("en").normalize
            except Exception:  # noqa: BLE001
                self._normalize = None
            print("[Engine] Local translation model successfully loaded!")
        except Exception as exc:  # noqa: BLE001
            print(f"[Engine Warning] Could not load the translation model: {exc}. Fallback to EN.")
            self.translator = None

    # ----------------------------------------------------------- inference
    def translate_text(self, text: str) -> str:
        """Translates English text to Russian using the local OPUS-MT model."""
        if not text or not text.strip():
            return ""
        if self.translator is None or self.spm_source is None or self.spm_target is None:
            return text
        try:
            normalized = self._normalize(text) if self._normalize else text
            tokens = self.spm_source.encode(normalized, out_type=str)
            tokens.append("</s>")
            result = self.translator.translate_batch(
                [tokens], beam_size=4, max_decoding_length=256
            )[0]
            hypothesis = [
                token
                for token in result.hypotheses[0]
                if token not in ("</s>", "<s>", "<pad>", "<unk>")
            ]
            return self.spm_target.decode(hypothesis).strip()
        except Exception as exc:  # noqa: BLE001
            print(f"[Translation Error] {exc}")
            return text

    def process_audio_chunk(self, audio_chunk: np.ndarray):
        """Accumulates audio and transcribes whole phrases, cutting on pauses."""
        if audio_chunk is None or len(audio_chunk) == 0:
            return

        self.audio_buffer = np.append(self.audio_buffer, audio_chunk)

        # Track trailing silence so we can cut on a natural pause instead of
        # slicing a word in half every couple of seconds.
        chunk_rms = float(np.sqrt(np.mean(audio_chunk ** 2)))
        if chunk_rms < self.silence_threshold:
            self.silence_samples += len(audio_chunk)
        else:
            self.silence_samples = 0

        speech_samples = len(self.audio_buffer) - self.silence_samples
        enough_speech = speech_samples >= self.min_buffer_size
        has_pause = self.silence_samples >= self.pause_samples
        too_long = len(self.audio_buffer) >= self.max_buffer_size

        # Long silence with no speech: drop the buffer to avoid unbounded growth.
        if not enough_speech and too_long:
            self.audio_buffer = np.array([], dtype=np.float32)
            self.silence_samples = 0
            return

        if enough_speech and (has_pause or too_long):
            if has_pause:
                # Trim the trailing silence from the segment.
                segment = self.audio_buffer[: len(self.audio_buffer) - self.silence_samples]
            else:
                segment = self.audio_buffer

            self.audio_buffer = np.array([], dtype=np.float32)
            self.silence_samples = 0

            if len(segment) and float(np.sqrt(np.mean(segment ** 2))) >= self.silence_threshold:
                self._run_transcription(segment)

    def _run_transcription(self, audio_data: np.ndarray):
        """Executes STT and translation on an audio segment."""
        if not self.is_loaded or self.whisper_model is None:
            return

        en_text = self._transcribe_with_fallback(audio_data)
        print(f"[STT] processed {len(audio_data)/16000:.1f}s segment")
        if en_text:
            ru_text = self.translate_text(en_text)
            print(f"[STT EN]: {en_text}")
            print(f"[TR RU]: {ru_text}")

            if self.callback:
                self.callback(en_text, ru_text)

    def _transcribe(self, audio_data: np.ndarray) -> str:
        segments, _info = self.whisper_model.transcribe(
            audio_data,
            beam_size=1,
            language="en",
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=300),
        )
        return " ".join(seg.text.strip() for seg in segments if seg.text.strip())

    def _transcribe_with_fallback(self, audio_data: np.ndarray) -> str:
        """Transcribes, falling back to CPU if a CUDA library is missing."""
        try:
            return self._transcribe(audio_data)
        except Exception as exc:  # noqa: BLE001
            message = str(exc).lower()
            cuda_problem = any(
                key in message for key in ("cublas", "cudnn", "cuda", "cudart")
            )
            if self.device != "cpu" and cuda_problem:
                print(f"[Engine] CUDA unavailable ({exc}). Switching to CPU...")
                self.device = "cpu"
                self.compute_type = "int8"
                self.whisper_model = None
                self.translator = None
                self.is_loaded = False
                self.load_models()
                try:
                    return self._transcribe(audio_data)
                except Exception as exc2:  # noqa: BLE001
                    print(f"[Transcription Error] {exc2}")
                    return ""
            print(f"[Transcription Error] {exc}")
            return ""

    def flush(self):
        """Transcribes any buffered audio that has not been flushed yet."""
        segment = self.audio_buffer
        self.audio_buffer = np.array([], dtype=np.float32)
        self.silence_samples = 0
        if len(segment) and float(np.sqrt(np.mean(segment ** 2))) >= self.silence_threshold:
            self._run_transcription(segment)

    # ------------------------------------------------------------ lifecycle
    def start(self, audio_capturer, on_subtitle_callback):
        """Starts processing thread reading from AudioStreamCapturer."""
        self.callback = on_subtitle_callback
        self.is_running = True

        if not self.is_loaded:
            self.load_models()

        def _loop():
            while self.is_running:
                chunk = audio_capturer.get_audio_chunk()
                if chunk is not None:
                    self.process_audio_chunk(chunk)
                else:
                    time.sleep(0.05)

        self._worker_thread = threading.Thread(target=_loop, daemon=True)
        self._worker_thread.start()

    def stop(self):
        self.is_running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=1.0)
