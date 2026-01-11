# Tapo Smart Light Colour Sync

Real-time color sync for Tapo L900/L925/L930 smart lighting using either:
- Audio spectrum analysis (music reactive)
- Screen color sampling (ambient bias lighting)

Tested with Tapo L930-5/L925-5 style LED strips and the TP-Link Tapo app login.

Product ref: https://www.tapo.com/sg/product/smart-light-bulb/tapo-l930-5/

## Features
- Audio-driven hue/saturation/brightness with adaptive normalization.
- Screen-driven ambient color with gamma correction and saturation boost.
- Smooth transitions and configurable update rate.
- GUI with login and mode selection.
- `.env`-based defaults (optional).

## Requirements
- Windows (tested) with Python 3.9+.
- A Tapo L900-series device on the same network.
- Tapo app email/password.
- For audio mode: a capture device (e.g., WASAPI loopback).

## Setup
1) Create and activate a virtual environment (optional but recommended).
2) Install dependencies:

```bash
pip install numpy python-dotenv tapo mss pillow pyaudio
# Optional (Windows loopback support):
pip install pyaudiowpatch
```

3) Create a `.env` file in the repo root:

```bash
TAPO_EMAIL=your_email@example.com
TAPO_PASSWORD=your_password_here
TAPO_IP=192.168.x.x
AUDIO_DEVICE_ID=14
```

Notes:
- `TAPO_IP` is required for audio sync unless you enter it in the GUI.
- `AUDIO_DEVICE_ID` is optional; the audio script defaults to `14`.

## Quick Start (GUI)
Run the combined app with a modern Tkinter GUI:

```bash
python tapo_sync_app.py
```

On launch, sign in with your Tapo email/password, then choose Audio Sync or Screen Sync.

## Audio Sync (music reactive, CLI)
Runs `tapo_audio.py` and maps 10 FFT bands to color/brightness.

```bash
python tapo_audio.py
```

Tips:
- Use `AUDIO_DEVICE_ID` to select your input device.
- If you see audio buffer errors, lower system audio load or reduce sample rate.

## Screen Sync (ambient bias, CLI)
Runs `tapo_screen_sync.py` and samples your display for ambient color.

```bash
python tapo_screen_sync.py
```

Notes:
- The default monitor index is `1` (primary). Change `monitor_index` in
  `tapo_sync/config.py` if needed.
- Auto-discovery scans `192.168.1.x`. If your network differs, set `TAPO_IP` in `.env`.

## Configuration
Audio settings:
- `tapo_sync/config.py` -> `AudioSettings` and defaults.

Screen settings:
- `tapo_sync/config.py` -> `ScreenSettings` and defaults.

## Troubleshooting
- Login errors: confirm `TAPO_EMAIL`/`TAPO_PASSWORD` match the Tapo app.
- Device not found: verify IP, network, and that the device is reachable.
- Lag or stutter: lower `REFRESH_RATE` or increase `SMOOTHING_FACTOR`.

## Safety
Do not commit `.env` with real credentials. Keep your Tapo account secure.
