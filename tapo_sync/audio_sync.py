from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Optional, Tuple

import numpy as np

from .config import AudioSettings
from .tapo_controller import TapoController


try:
    import pyaudiowpatch as pyaudio
except ImportError:
    try:
        import pyaudio
    except ImportError:
        pyaudio = None


FORMAT = pyaudio.paFloat32 if pyaudio else None
CHANNELS = 1

DEFAULT_BANDS = [50, 100, 250, 500, 1000, 2000, 4000, 6000, 10000, 20000]


class AdaptiveEnergy:
    def __init__(self, num_bands: int, maxlen: int = 300) -> None:
        self._band_hist = [deque(maxlen=maxlen) for _ in range(num_bands)]

    def update_and_normalize(self, band_energies: list[float]) -> list[float]:
        normalized = []
        for i, energy in enumerate(band_energies):
            self._band_hist[i].append(energy)

            if len(self._band_hist[i]) < 20:
                normalized.append(0.0)
                continue

            arr = np.array(self._band_hist[i], dtype=np.float32)
            med = float(np.median(arr))
            p90 = float(np.percentile(arr, 90))

            if p90 <= med:
                norm_val = 0.0
            else:
                norm_val = float(
                    np.clip((energy - med) / (p90 - med + 1e-9), 0, 2.0)
                )

            normalized.append(float(np.tanh(norm_val)))

        return normalized


class AudioSyncEngine:
    def __init__(self, controller: TapoController, settings: AudioSettings) -> None:
        self._controller = controller
        self._settings = settings
        self._stop_event: Optional[asyncio.Event] = None
        self._task: Optional[asyncio.Task] = None
        self._energy_norm = AdaptiveEnergy(settings.num_bands, settings.history_len)
        self._stream = None
        self._pyaudio = None

        if pyaudio is None:
            raise RuntimeError(
                "PyAudio is required for audio sync. Install pyaudio or pyaudiowpatch."
            )

        if settings.num_bands != len(DEFAULT_BANDS):
            raise ValueError("Only 10-band audio analysis is supported.")

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if not self._task:
            return
        if self._stop_event:
            self._stop_event.set()
        await self._task
        self._task = None

    def _open_audio_stream(self) -> Tuple[pyaudio.PyAudio, pyaudio.Stream, int]:
        p = pyaudio.PyAudio()
        info = p.get_device_info_by_index(self._settings.device_id)
        rate = int(info["defaultSampleRate"])

        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=rate,
            input=True,
            input_device_index=self._settings.device_id,
            frames_per_buffer=self._settings.chunk,
            stream_callback=None,
        )
        stream.start_stream()
        return p, stream, rate

    def _analyze_frame(self, frame: np.ndarray, rate: int) -> list[float]:
        n = frame.size
        if n == 0:
            return [0.0] * self._settings.num_bands

        freqs = np.fft.fft(frame)
        mag = np.abs(freqs[: n // 2]) / n

        band_energies = []
        for i, freq_max in enumerate(DEFAULT_BANDS):
            freq_min = DEFAULT_BANDS[i - 1] if i > 0 else 0

            bin_max = int(freq_max * n / rate)
            bin_min = int(freq_min * n / rate)

            bin_max = min(bin_max, len(mag) - 1)
            bin_min = max(bin_min, 0)

            if bin_max > bin_min:
                energy = float(np.mean(mag[bin_min:bin_max]))
            else:
                energy = 0.0

            band_energies.append(energy)

        return self._energy_norm.update_and_normalize(band_energies)

    async def _run(self) -> None:
        self._pyaudio, self._stream, rate = self._open_audio_stream()
        last_send = time.time()

        try:
            while self._stop_event and not self._stop_event.is_set():
                try:
                    data = self._stream.read(self._settings.chunk, exception_on_overflow=False)
                except OSError:
                    await asyncio.sleep(0.05)
                    continue

                frame = np.frombuffer(data, dtype=np.float32)
                band_norms = self._analyze_frame(frame, rate)

                overall_energy = float(np.mean(band_norms))
                bass_energy = float(np.mean(band_norms[0:3]))
                mid_energy = float(np.mean(band_norms[3:6]))
                treble_energy = float(np.mean(band_norms[6:10]))

                hue = int((bass_energy * 0 + treble_energy * 240) % 360)
                saturation = int(50 + mid_energy * 50)
                saturation = max(30, min(saturation, 100))

                brightness = int(20 + overall_energy * 80)
                brightness = max(10, min(brightness, 100))

                now = time.time()
                if now - last_send > self._settings.update_interval:
                    await self._controller.set_color(hue, saturation, brightness)
                    last_send = now

                await asyncio.sleep(0)
        finally:
            if self._stream:
                try:
                    self._stream.stop_stream()
                    self._stream.close()
                except Exception:
                    pass
            if self._pyaudio:
                try:
                    self._pyaudio.terminate()
                except Exception:
                    pass
