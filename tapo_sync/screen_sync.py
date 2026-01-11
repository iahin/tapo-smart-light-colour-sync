from __future__ import annotations

import asyncio
import colorsys
from typing import Optional

import mss
from PIL import Image
import numpy as np

from .config import ScreenSettings
from .tapo_controller import TapoController


def lerp(start: float, end: float, factor: float) -> float:
    return start + (end - start) * factor


def lerp_hue(start: float, end: float, factor: float) -> float:
    diff = end - start
    if abs(diff) > 180:
        if end > start:
            start += 360
        else:
            end += 360
    result = lerp(start, end, factor)
    return result % 360


def apply_gamma_correction(color: tuple[int, int, int], gamma: float) -> tuple[int, int, int]:
    return tuple(int(255 * ((c / 255) ** gamma)) for c in color)


class ScreenSyncEngine:
    def __init__(self, controller: TapoController, settings: ScreenSettings) -> None:
        self._controller = controller
        self._settings = settings
        self._stop_event: Optional[asyncio.Event] = None
        self._task: Optional[asyncio.Task] = None
        self._user_brightness = 80
        self._current_hue = 0.0
        self._current_sat = 50.0
        self._current_brightness = 60.0

    def set_user_brightness(self, value: int) -> None:
        self._user_brightness = max(1, min(100, int(value)))

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

    def _get_average_screen_color(self) -> tuple[int, int, int]:
        with mss.mss() as sct:
            monitor_index = self._settings.monitor_index
            if monitor_index >= len(sct.monitors):
                monitor_index = 1
            monitor = sct.monitors[monitor_index]
            screenshot = sct.grab(monitor)

            img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
            try:
                resample = Image.Resampling.LANCZOS
            except AttributeError:
                resample = Image.LANCZOS
            img = img.resize((150, 150), resample)

            pixels = np.array(img)
            weights = np.mean(pixels, axis=2) ** self._settings.power_factor
            weight_sum = np.sum(weights)
            if weight_sum <= 0:
                weights = np.full_like(weights, 1.0 / weights.size)
            else:
                weights = weights / weight_sum

            avg_color = np.array(
                [
                    np.sum(pixels[:, :, 0] * weights),
                    np.sum(pixels[:, :, 1] * weights),
                    np.sum(pixels[:, :, 2] * weights),
                ],
                dtype=int,
            )

            return tuple(avg_color)

    def _get_weighted_avg_color(self) -> tuple[int, int, int]:
        avg_color = self._get_average_screen_color()
        corrected_color = apply_gamma_correction(avg_color, self._settings.gamma_correction)

        r, g, b = [c / 255.0 for c in corrected_color]
        h, s, v = colorsys.rgb_to_hsv(r, g, b)

        s = min(s * self._settings.saturation_boost, 1.0)

        brightness = int(self._user_brightness * v)
        brightness = max(self._settings.min_brightness, min(brightness, self._settings.max_brightness))

        hue = int(h * 360)
        saturation = max(10, int(s * 100))

        return hue, saturation, brightness

    def _update_colors(self) -> tuple[int, int, int]:
        target_hue, target_sat, target_brightness = self._get_weighted_avg_color()

        self._current_hue = lerp_hue(self._current_hue, target_hue, self._settings.smoothing_factor)
        self._current_sat = lerp(self._current_sat, target_sat, self._settings.smoothing_factor)
        self._current_brightness = lerp(
            self._current_brightness, target_brightness, self._settings.smoothing_factor
        )

        return int(self._current_hue), int(self._current_sat), int(self._current_brightness)

    async def _run(self) -> None:
        interval = 1.0 / self._settings.refresh_rate

        while self._stop_event and not self._stop_event.is_set():
            hue, sat, brightness = self._update_colors()
            await self._controller.set_color(hue, sat, brightness)
            await asyncio.sleep(interval)
