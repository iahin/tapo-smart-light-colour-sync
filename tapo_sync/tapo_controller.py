from __future__ import annotations

from typing import Optional

from tapo import ApiClient


class TapoController:
    def __init__(self, email: str, password: str) -> None:
        self._email = email
        self._password = password
        self._client: Optional[ApiClient] = None
        self._device = None
        self._device_ip: Optional[str] = None

    @property
    def device_ip(self) -> Optional[str]:
        return self._device_ip

    async def connect(self, device_ip: str) -> None:
        if self._device and self._device_ip == device_ip:
            return

        self._client = ApiClient(self._email, self._password)
        self._device = await self._client.l530(device_ip)
        self._device_ip = device_ip

    async def ensure_on(self) -> None:
        if not self._device:
            raise RuntimeError("Device not connected.")
        await self._device.on()

    async def ensure_off(self) -> None:
        if not self._device:
            return
        await self._device.off()

    async def set_color(self, hue: int, saturation: int, brightness: int) -> None:
        if not self._device:
            raise RuntimeError("Device not connected.")
        await self._device.set_hue_saturation(hue, saturation)
        await self._device.set_brightness(brightness)


async def discover_device_ip(
    email: str,
    password: str,
    scan_base: str = "192.168.1",
    start: int = 1,
    end: int = 254,
) -> Optional[str]:
    for i in range(start, end + 1):
        ip = f"{scan_base}.{i}"
        try:
            client = ApiClient(email, password)
            device = await client.l530(ip)
            await device.get_device_info()
            return ip
        except Exception:
            continue

    return None
