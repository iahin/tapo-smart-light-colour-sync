from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


@dataclass(frozen=True)
class Credentials:
    email: str
    password: str


@dataclass(frozen=True)
class AudioSettings:
    device_id: int = 14
    chunk: int = 1024
    num_bands: int = 10
    update_interval: float = 0.05
    history_len: int = 300


@dataclass(frozen=True)
class ScreenSettings:
    refresh_rate: int = 60
    smoothing_factor: float = 0.4
    gamma_correction: float = 1.2
    saturation_boost: float = 1.5
    min_brightness: int = 10
    max_brightness: int = 80
    power_factor: float = 1.8
    monitor_index: int = 1


@dataclass(frozen=True)
class EnvDefaults:
    email: Optional[str] = None
    password: Optional[str] = None
    device_ip: Optional[str] = None
    audio_device_id: int = 14


def load_env_defaults() -> EnvDefaults:
    load_dotenv(ENV_PATH)

    email = os.getenv("TAPO_EMAIL")
    password = os.getenv("TAPO_PASSWORD")
    device_ip = os.getenv("TAPO_IP")
    audio_device_id = int(os.getenv("AUDIO_DEVICE_ID", "14"))

    return EnvDefaults(
        email=email,
        password=password,
        device_ip=device_ip,
        audio_device_id=audio_device_id,
    )
