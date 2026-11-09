import time
import queue
import threading
import warnings

import numpy as np
import soundcard as sc

def list_loopback_speakers():
    """Returns names of all audio outputs usable for WASAPI loopback capture."""
    try:
        return [s.name for s in sc.all_speakers()]
    except Exception:  # noqa: BLE001
        return []


def pick_active_speaker(duration=0.3):
    """Samples every output and returns the one currently carrying the most audio."""
    best_name = None
    best_rms = -1.0
    for speaker in sc.all_speakers():
        try:
            mic = sc.get_microphone(id=speaker.name, include_loopback=True)
            channels = min(2, getattr(speaker, "channels", 2) or 2)
            with mic.recorder(samplerate=16000, channels=channels) as recorder:
                data = recorder.record(numframes=int(16000 * duration))
            rms = float(np.sqrt(np.mean(data ** 2)))
            print(f"[Audio] probe {speaker.name}: rms={rms:.5f}")
            if rms > best_rms:
                best_rms = rms
                best_name = speaker.name
        except Exception as e:  # noqa: BLE001
            print(f"[Audio] probe {speaker.name} failed: {e}")
    if best_name and best_rms > 0.0005:
        return best_name
    return None


# soundcard emits this benign warning when the WASAPI scheduler drifts; it does
# not stop capture and floods the console. Hide just this one.
try:
    from soundcard.mediafoundation import SoundcardRuntimeWarning
    warnings.filterwarnings("ignore", category=SoundcardRuntimeWarning)
except Exception:  # noqa: BLE001
    pass

import subprocess
import shutil

class AudioStreamCapturer:
    """
    Captures audio either from System Loopback (speakers) or a Stream URL (Twitch/YouTube)
    and delivers float32 16kHz mono PCM chunks into a thread-safe queue.
    """
    def __init__(self, sample_rate=16000, chunk_duration=0.1, speaker_name=None):
        self.sample_rate = sample_rate
        self.chunk_size = int(sample_rate * chunk_duration)
        self.audio_queue = queue.Queue()
        self.is_running = False
        self._thread = None
        self.mode = "system"  # "system" or "url"
        self.stream_url = ""
        self.speaker_name = speaker_name

    def start_system_loopback(self, speaker_name=None):
        """Starts capturing system sound from the given output (default speaker)."""
        self.mode = "system"
        self.speaker_name = speaker_name
        self.is_running = True
        self._thread = threading.Thread(target=self._system_loopback_loop, daemon=True)
        self._thread.start()

    def start_url_stream(self, url: str):
        """Starts capturing audio directly from a Twitch or YouTube URL."""
        self.mode = "url"
        self.stream_url = url
        self.is_running = True
        self._thread = threading.Thread(target=self._url_stream_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stops audio capture."""
        self.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _system_loopback_loop(self):
        try:
            speaker = None
            if self.speaker_name and self.speaker_name.lower() != "auto":
                speaker = next(
                    (s for s in sc.all_speakers() if s.name == self.speaker_name),
                    None,
                )
            if speaker is None:
                # No explicit device: pick whichever output is actually playing audio.
                active = pick_active_speaker()
                if active:
                    speaker = next((s for s in sc.all_speakers() if s.name == active), None)
                    print(f"[Audio] Auto-selected active device: {active}")
            if speaker is None:
                speaker = sc.default_speaker()
            mic = sc.get_microphone(id=speaker.name, include_loopback=True)
            print(f"[Audio] Recording system loopback from: {speaker.name}")

            # Record using the speaker's native channel count, then downmix to mono.
            # Requesting channels=1 directly for a loopback device can fail on some
            # WASAPI drivers.
            channels = getattr(speaker, "channels", 2) or 2
            with mic.recorder(samplerate=self.sample_rate, channels=channels) as recorder:
                while self.is_running:
                    data = recorder.record(numframes=self.chunk_size)
                    if data.ndim > 1:
                        data = data.mean(axis=1)
                    audio_data = data.astype(np.float32)
                    self.audio_queue.put(audio_data)
        except Exception as e:
            print(f"[Audio Error] System loopback failed: {e}")
            self.is_running = False

    def _url_stream_loop(self):
        print(f"[Audio] Connecting to stream URL: {self.stream_url}")

        # ffmpeg reads the stream URL and decodes it to raw 16-bit mono PCM on stdout.
        # Twitch/YouTube URLs may require yt-dlp/streamlink; if ffmpeg returns no data,
        # try resolving the page URL with yt-dlp and pipe the result into ffmpeg.
        if not shutil.which("ffmpeg"):
            print("[Audio Error] ffmpeg not found. Install ffmpeg and add it to PATH.")
            self.is_running = False
            return

        process = None
        producer = None
        try:
            source = ["-i", self.stream_url]

            # If yt-dlp is available, prefer it to resolve page URLs reliably.
            if shutil.which("yt-dlp"):
                producer = subprocess.Popen(
                    [ "yt-dlp", "-f", "bestaudio", "-o", "-", "-q", self.stream_url ],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                )
                ffmpeg_cmd = [
                    "ffmpeg", "-loglevel", "quiet", "-i", "pipe:0",
                    "-vn", "-acodec", "pcm_s16le", "-ac", "1",
                    "-ar", str(self.sample_rate), "-f", "s16le", "pipe:1",
                ]
                process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdin=producer.stdout,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                producer.stdout.close()  # allow producer to receive SIGPIPE
            else:
                ffmpeg_cmd = [
                    "ffmpeg", "-loglevel", "quiet", *source,
                    "-vn", "-acodec", "pcm_s16le", "-ac", "1",
                    "-ar", str(self.sample_rate), "-f", "s16le", "pipe:1",
                ]
                process = subprocess.Popen(
                    ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
                )

            bytes_per_sample = 2  # 16-bit PCM
            chunk_bytes = self.chunk_size * bytes_per_sample

            while self.is_running:
                raw_data = process.stdout.read(chunk_bytes)
                if not raw_data:
                    break
                audio_data = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
                self.audio_queue.put(audio_data)
        except Exception as e:
            print(f"[Audio Error] Stream URL capture failed: {e}")
            self.is_running = False
        finally:
            for p in (process, producer):
                if p and p.poll() is None:
                    p.terminate()

    def get_audio_chunk(self):
        """Retrieves next audio chunk if available, otherwise returns None."""
        try:
            return self.audio_queue.get_nowait()
        except queue.Empty:
            return None
