from __future__ import annotations

from enum import Enum
from typing import Optional

from .audio_sync import AudioSyncEngine
from .config import AudioSettings, Credentials, ScreenSettings
from .screen_sync import ScreenSyncEngine
from .tapo_controller import TapoController, discover_device_ip


class SyncMode(str, Enum):
    AUDIO = "audio"
    SCREEN = "screen"


class SyncCoordinator:
    def __init__(self, credentials: Credentials) -> None:
        self._credentials = credentials
        self._controller = TapoController(credentials.email, credentials.password)
        self._audio_engine: Optional[AudioSyncEngine] = None
        self._screen_engine: Optional[ScreenSyncEngine] = None
        self._active_mode: Optional[SyncMode] = None

    @property
    def active_mode(self) -> Optional[SyncMode]:
        return self._active_mode

    async def start(
        self,
        mode: SyncMode,
        device_ip: Optional[str],
        audio_settings: AudioSettings,
        screen_settings: ScreenSettings,
        screen_brightness: Optional[int] = None,
    ) -> None:
        await self.stop()

        if mode == SyncMode.AUDIO:
            if not device_ip:
                raise ValueError("Device IP is required for audio sync.")
            await self._controller.connect(device_ip)
            await self._controller.ensure_on()

            self._audio_engine = AudioSyncEngine(self._controller, audio_settings)
            await self._audio_engine.start()
            self._active_mode = SyncMode.AUDIO
            return

        if mode == SyncMode.SCREEN:
            ip = device_ip
            if not ip:
                ip = await discover_device_ip(
                    self._credentials.email, self._credentials.password
                )
            if not ip:
                raise RuntimeError("Device not found. Enter its IP and try again.")

            await self._controller.connect(ip)
            await self._controller.ensure_on()

            self._screen_engine = ScreenSyncEngine(self._controller, screen_settings)
            if screen_brightness is not None:
                self._screen_engine.set_user_brightness(screen_brightness)
            await self._screen_engine.start()
            self._active_mode = SyncMode.SCREEN
            return

        raise ValueError("Unsupported sync mode.")

    async def stop(self) -> None:
        if self._audio_engine:
            await self._audio_engine.stop()
            self._audio_engine = None
        if self._screen_engine:
            await self._screen_engine.stop()
            self._screen_engine = None
        try:
            await self._controller.ensure_off()
        except Exception:
            pass
        self._active_mode = None

    def set_screen_brightness(self, value: int) -> None:
        if self._screen_engine:
            self._screen_engine.set_user_brightness(value)
