import asyncio

from tapo_sync.audio_sync import AudioSyncEngine
from tapo_sync.config import AudioSettings, Credentials, load_env_defaults
from tapo_sync.tapo_controller import TapoController


async def main() -> None:
    defaults = load_env_defaults()
    if not defaults.email or not defaults.password or not defaults.device_ip:
        raise RuntimeError("TAPO_EMAIL, TAPO_PASSWORD, TAPO_IP must be set in .env")

    credentials = Credentials(defaults.email, defaults.password)
    controller = TapoController(credentials.email, credentials.password)
    await controller.connect(defaults.device_ip)
    await controller.ensure_on()

    audio_settings = AudioSettings(device_id=defaults.audio_device_id)
    engine = AudioSyncEngine(controller, audio_settings)
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
