import asyncio

from tapo_sync.config import Credentials, ScreenSettings, load_env_defaults
from tapo_sync.screen_sync import ScreenSyncEngine
from tapo_sync.tapo_controller import TapoController, discover_device_ip


async def main() -> None:
    defaults = load_env_defaults()
    if not defaults.email or not defaults.password:
        raise RuntimeError("TAPO_EMAIL and TAPO_PASSWORD must be set in .env")

    credentials = Credentials(defaults.email, defaults.password)
    controller = TapoController(credentials.email, credentials.password)

    device_ip = defaults.device_ip
    if not device_ip:
        device_ip = await discover_device_ip(credentials.email, credentials.password)
    if not device_ip:
        raise RuntimeError("Device not found. Set TAPO_IP in .env.")

    await controller.connect(device_ip)
    await controller.ensure_on()

    engine = ScreenSyncEngine(controller, ScreenSettings())
    await engine.start()

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await engine.stop()
        await controller.ensure_off()


if __name__ == "__main__":
    asyncio.run(main())
