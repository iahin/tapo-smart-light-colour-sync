from __future__ import annotations

import asyncio
from dataclasses import dataclass
import ipaddress
import re
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from .config import AudioSettings, Credentials, EnvDefaults, ScreenSettings, ENV_PATH
from .sync_manager import SyncCoordinator, SyncMode


BG_TOP = "#F7F3EE"
BG_BOTTOM = "#E6EEF4"
CARD_BG = "#FFFFFF"
ACCENT = "#2A5C8A"
ACCENT_HOVER = "#244E75"
TEXT = "#1A1F2B"
TEXT_MUTED = "#5A6576"
ERROR = "#B00020"

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _is_valid_email(value: str) -> bool:
    return bool(EMAIL_PATTERN.match(value))


def _is_valid_ipv4(value: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(value), ipaddress.IPv4Address)
    except ValueError:
        return False


@dataclass(frozen=True)
class AudioDevice:
    index: int
    name: str
    channels: int


class AsyncRunner:
    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run(self, coro: asyncio.Future) -> asyncio.Future:
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def call_soon(self, func: Callable, *args) -> None:
        self._loop.call_soon_threadsafe(func, *args)

    def stop(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)


class BasePage(ttk.Frame):
    def __init__(self, parent: tk.Widget, app: "TapoSyncApp") -> None:
        super().__init__(parent, style="Card.TFrame", padding=(28, 24))
        self.app = app


class LoginPage(BasePage):
    def __init__(self, parent: tk.Widget, app: "TapoSyncApp") -> None:
        super().__init__(parent, app)

        self.columnconfigure(0, weight=1)

        title = ttk.Label(self, text="Tapo Sync", style="Title.TLabel")
        subtitle = ttk.Label(
            self,
            text="Sign in to your Tapo account to continue.",
            style="Subtitle.TLabel",
        )

        form = ttk.Frame(self, style="Card.TFrame")
        form.columnconfigure(0, weight=1)

        self.email_var = tk.StringVar(value=app.env_defaults.email or "")
        self.password_var = tk.StringVar(value=app.env_defaults.password or "")
        self.ip_var = tk.StringVar(value=app.env_defaults.device_ip or "")

        email_label = ttk.Label(form, text="Email", style="Field.TLabel")
        email_entry = ttk.Entry(form, textvariable=self.email_var, style="Field.TEntry")

        password_label = ttk.Label(form, text="Password", style="Field.TLabel")
        password_entry = ttk.Entry(
            form, textvariable=self.password_var, show="*", style="Field.TEntry"
        )

        ip_label = ttk.Label(form, text="Device IP (optional)", style="Field.TLabel")
        ip_entry = ttk.Entry(form, textvariable=self.ip_var, style="Field.TEntry")

        helper = ttk.Label(
            form,
            text="IP is required for audio sync. Screen sync can auto-discover.",
            style="Help.TLabel",
            wraplength=360,
        )

        self.save_var = tk.BooleanVar(value=False)
        save_check = ttk.Checkbutton(
            form,
            text="Save credentials to .env",
            variable=self.save_var,
            style="Field.TCheckbutton",
        )

        submit = ttk.Button(
            self, text="Log In", style="Primary.TButton", command=self._on_submit
        )

        title.grid(row=0, column=0, sticky="w", pady=(0, 6))
        subtitle.grid(row=1, column=0, sticky="w", pady=(0, 18))

        form.grid(row=2, column=0, sticky="ew")
        email_label.grid(row=0, column=0, sticky="w")
        email_entry.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        password_label.grid(row=2, column=0, sticky="w")
        password_entry.grid(row=3, column=0, sticky="ew", pady=(4, 12))
        ip_label.grid(row=4, column=0, sticky="w")
        ip_entry.grid(row=5, column=0, sticky="ew", pady=(4, 10))
        helper.grid(row=6, column=0, sticky="w")
        save_check.grid(row=7, column=0, sticky="w", pady=(10, 0))

        self.status_label = ttk.Label(self, text="", style="StatusError.TLabel")

        self.status_label.grid(row=3, column=0, sticky="w", pady=(18, 0))
        submit.grid(row=4, column=0, sticky="ew", pady=(12, 0))

    def set_status(self, message: str) -> None:
        self.status_label.configure(text=message)

    def _validate_inputs(
        self, email: str, password: str, device_ip: Optional[str]
    ) -> Optional[str]:
        if not email:
            return "Email is required."
        if not _is_valid_email(email):
            return "Enter a valid email address."
        if not password:
            return "Password is required."
        if device_ip and not _is_valid_ipv4(device_ip):
            return "Enter a valid IPv4 address, like 192.168.1.20."
        return None

    def _on_submit(self) -> None:
        email = self.email_var.get().strip()
        password = self.password_var.get().strip()
        device_ip = self.ip_var.get().strip() or None

        error = self._validate_inputs(email, password, device_ip)
        if error:
            self.set_status(error)
            return

        self.set_status("")
        credentials = Credentials(email=email, password=password)
        if self.save_var.get():
            save_error = self.app.save_credentials_to_env(credentials, device_ip)
            if save_error:
                self.set_status(save_error)
                return
        self.app.set_credentials(credentials, device_ip)
        self.app.show_page("main")


class MainPage(BasePage):
    def __init__(self, parent: tk.Widget, app: "TapoSyncApp") -> None:
        super().__init__(parent, app)
        self._running = False

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)

        header = ttk.Frame(self, style="Card.TFrame")
        header.columnconfigure(0, weight=1)
        title = ttk.Label(header, text="Sync Mode", style="Title.TLabel")
        sign_out = ttk.Button(
            header, text="Sign Out", style="Link.TButton", command=self.app.sign_out
        )
        title.grid(row=0, column=0, sticky="w")
        sign_out.grid(row=0, column=1, sticky="e")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        subtitle = ttk.Label(
            self,
            text="Choose a mode and start syncing your lights.",
            style="Subtitle.TLabel",
        )
        subtitle.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 18))

        self.mode_var = tk.StringVar(value=SyncMode.AUDIO.value)
        mode_frame = ttk.Frame(self, style="Card.TFrame")
        mode_frame.columnconfigure(0, weight=1)
        mode_frame.columnconfigure(1, weight=1)

        audio_radio = ttk.Radiobutton(
            mode_frame,
            text="Audio Sync",
            value=SyncMode.AUDIO.value,
            variable=self.mode_var,
            style="Mode.TRadiobutton",
            command=self._on_mode_change,
        )
        audio_desc = ttk.Label(
            mode_frame,
            text="Reactive color from music and audio bands.",
            style="Help.TLabel",
            wraplength=240,
        )

        screen_radio = ttk.Radiobutton(
            mode_frame,
            text="Screen Sync",
            value=SyncMode.SCREEN.value,
            variable=self.mode_var,
            style="Mode.TRadiobutton",
            command=self._on_mode_change,
        )
        screen_desc = ttk.Label(
            mode_frame,
            text="Ambient lighting based on your display.",
            style="Help.TLabel",
            wraplength=240,
        )

        audio_radio.grid(row=0, column=0, sticky="w")
        audio_desc.grid(row=1, column=0, sticky="w", pady=(6, 0))
        screen_radio.grid(row=0, column=1, sticky="w")
        screen_desc.grid(row=1, column=1, sticky="w", pady=(6, 0))

        mode_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 18))

        settings_frame = ttk.Frame(self, style="Card.TFrame")
        settings_frame.columnconfigure(0, weight=1)
        settings_frame.columnconfigure(1, weight=1)

        ip_label = ttk.Label(settings_frame, text="Device IP", style="Field.TLabel")
        self.ip_var = tk.StringVar(value=self.app.device_ip or "")
        ip_entry = ttk.Entry(settings_frame, textvariable=self.ip_var, style="Field.TEntry")

        audio_label = ttk.Label(settings_frame, text="Audio Device ID", style="Field.TLabel")
        self.audio_device_var = tk.StringVar(value=str(self.app.env_defaults.audio_device_id))
        audio_entry = ttk.Entry(
            settings_frame, textvariable=self.audio_device_var, style="Field.TEntry"
        )
        self._audio_devices = self.app.get_audio_devices()
        self._audio_device_map = {device.index: device for device in self._audio_devices}
        devices_label = ttk.Label(
            settings_frame, text="Available Audio Devices", style="Field.TLabel"
        )
        device_list_frame = ttk.Frame(settings_frame, style="Card.TFrame")
        device_list_frame.columnconfigure(0, weight=1)
        self.audio_device_list = tk.Listbox(
            device_list_frame,
            height=4,
            selectmode=tk.BROWSE,
            background="#F9FAFB",
            foreground=TEXT,
            selectbackground=ACCENT,
            selectforeground="white",
            highlightthickness=1,
            relief="solid",
        )
        device_scroll = ttk.Scrollbar(
            device_list_frame, orient="vertical", command=self.audio_device_list.yview
        )
        self.audio_device_list.configure(yscrollcommand=device_scroll.set)
        self.audio_device_list.bind("<<ListboxSelect>>", self._on_audio_device_select)
        self.audio_device_hint = ttk.Label(
            settings_frame,
            text="",
            style="Help.TLabel",
            wraplength=360,
        )

        refresh_label = ttk.Label(settings_frame, text="Screen Refresh Rate", style="Field.TLabel")
        self.refresh_var = tk.StringVar(value="60")
        self.refresh_menu = ttk.Combobox(
            settings_frame,
            textvariable=self.refresh_var,
            values=["30", "60", "120"],
            state="readonly",
            style="Field.TCombobox",
        )

        ip_label.grid(row=0, column=0, sticky="w")
        ip_entry.grid(row=1, column=0, sticky="ew", pady=(4, 12), padx=(0, 10))
        audio_label.grid(row=0, column=1, sticky="w")
        audio_entry.grid(row=1, column=1, sticky="ew", pady=(4, 12))
        refresh_label.grid(row=2, column=0, sticky="w")
        self.refresh_menu.grid(row=3, column=0, sticky="ew", pady=(4, 0), padx=(0, 10))
        devices_label.grid(row=4, column=0, columnspan=2, sticky="w")
        device_list_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self.audio_device_list.grid(row=0, column=0, sticky="ew")
        device_scroll.grid(row=0, column=1, sticky="ns")
        self.audio_device_hint.grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))

        settings_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 18))

        brightness_frame = ttk.Frame(self, style="Card.TFrame")
        brightness_frame.columnconfigure(0, weight=1)
        brightness_label = ttk.Label(
            brightness_frame,
            text="Screen Brightness (screen mode)",
            style="Field.TLabel",
        )
        self.brightness_var = tk.IntVar(value=80)
        self.brightness_slider = ttk.Scale(
            brightness_frame,
            from_=1,
            to=100,
            orient=tk.HORIZONTAL,
            value=80,
            command=self._on_brightness_change,
            style="Accent.Horizontal.TScale",
        )
        self.brightness_value = ttk.Label(
            brightness_frame, text="80%", style="Help.TLabel"
        )

        brightness_label.grid(row=0, column=0, sticky="w")
        self.brightness_slider.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.brightness_value.grid(row=1, column=1, sticky="e", padx=(8, 0))

        brightness_frame.grid(row=4, column=0, columnspan=2, sticky="ew")

        control_frame = ttk.Frame(self, style="Card.TFrame")
        control_frame.columnconfigure(0, weight=1)
        self.toggle_btn = ttk.Button(
            control_frame,
            text="Start Sync",
            style="Primary.TButton",
            command=self._on_toggle,
        )
        self.status_label = ttk.Label(
            control_frame, text="Idle.", style="Status.TLabel"
        )

        self.toggle_btn.grid(row=0, column=0, sticky="ew")
        self.status_label.grid(row=1, column=0, sticky="w", pady=(8, 0))
        control_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(18, 0))

        self._on_mode_change()
        self._populate_audio_devices()

    def _on_mode_change(self) -> None:
        is_screen = self.mode_var.get() == SyncMode.SCREEN.value
        self.refresh_menu.configure(state="readonly" if is_screen else "disabled")
        self.brightness_slider.configure(state="normal" if is_screen else "disabled")
        self.app.set_status("")

    def _on_brightness_change(self, value: str) -> None:
        value_int = int(float(value))
        self.brightness_var.set(value_int)
        self.brightness_value.configure(text=f"{value_int}%")
        self.app.update_screen_brightness(value_int)

    def set_running(self, running: bool) -> None:
        self._running = running
        self.toggle_btn.configure(text="Stop Sync" if running else "Start Sync")

    def set_status(self, message: str, is_error: bool = False) -> None:
        style = "StatusError.TLabel" if is_error else "Status.TLabel"
        self.status_label.configure(text=message, style=style)

    def set_device_ip(self, device_ip: Optional[str]) -> None:
        self.ip_var.set(device_ip or "")

    def _parse_int(self, value: str, fallback: int) -> int:
        try:
            return int(value)
        except ValueError:
            return fallback

    def _get_audio_device_id(self) -> Optional[int]:
        value = self.audio_device_var.get().strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def _format_audio_device(self, device: AudioDevice) -> str:
        return f"{device.index}: {device.name} ({device.channels} ch)"

    def _populate_audio_devices(self) -> None:
        self.audio_device_list.delete(0, tk.END)
        if not self._audio_devices:
            self.audio_device_hint.configure(
                text="No audio input devices found. Install PyAudio or check audio settings."
            )
            return

        for device in self._audio_devices:
            self.audio_device_list.insert(tk.END, self._format_audio_device(device))

        self.audio_device_hint.configure(text="Select a device to auto-fill the ID.")
        current_id = self._get_audio_device_id()
        if current_id is None or current_id not in self._audio_device_map:
            current_id = self._audio_devices[0].index
            self.audio_device_var.set(str(current_id))
        self._select_audio_device(current_id)

    def _select_audio_device(self, device_id: int) -> None:
        for idx, device in enumerate(self._audio_devices):
            if device.index == device_id:
                self.audio_device_list.selection_clear(0, tk.END)
                self.audio_device_list.selection_set(idx)
                self.audio_device_list.see(idx)
                break

    def _on_audio_device_select(self, _: tk.Event) -> None:
        selection = self.audio_device_list.curselection()
        if not selection:
            return
        device = self._audio_devices[selection[0]]
        self.audio_device_var.set(str(device.index))

    def _validate_audio_device(self, device_id: int) -> Optional[str]:
        if not self._audio_devices:
            return "No audio input devices detected."
        device = self._audio_device_map.get(device_id)
        if not device:
            return "Select an audio device from the list."
        if device.channels <= 0:
            return "Selected audio device has no input channels."
        return None

    def _on_toggle(self) -> None:
        if self._running:
            self.app.stop_sync()
            return

        mode = SyncMode(self.mode_var.get())
        device_ip = self.ip_var.get().strip() or None

        if device_ip and not _is_valid_ipv4(device_ip):
            self.set_status("Enter a valid IPv4 address, like 192.168.1.20.", is_error=True)
            return
        if mode == SyncMode.AUDIO and not device_ip:
            self.set_status("Device IP is required for audio sync.", is_error=True)
            return

        audio_device_id = self._get_audio_device_id()
        if mode == SyncMode.AUDIO:
            if audio_device_id is None:
                self.set_status("Audio device ID is required.", is_error=True)
                return
            audio_error = self._validate_audio_device(audio_device_id)
            if audio_error:
                self.set_status(audio_error, is_error=True)
                return
        if audio_device_id is None:
            audio_device_id = self.app.env_defaults.audio_device_id
        refresh_rate = self._parse_int(self.refresh_var.get(), 60)

        audio_settings = AudioSettings(device_id=audio_device_id)
        screen_settings = ScreenSettings(refresh_rate=refresh_rate)
        self.app.start_sync(
            mode,
            device_ip,
            audio_settings,
            screen_settings,
            self.brightness_var.get(),
        )


class TapoSyncApp(tk.Tk):
    def __init__(self, env_defaults: EnvDefaults) -> None:
        super().__init__()

        self.env_defaults = env_defaults
        self.device_ip: Optional[str] = env_defaults.device_ip

        self._runner = AsyncRunner()
        self._coordinator: Optional[SyncCoordinator] = None
        self._closing = False

        self.title("Tapo Sync")
        self.geometry("900x600")
        self.minsize(720, 520)

        self._apply_style()

        self._bg = tk.Canvas(self, highlightthickness=0, bd=0)
        self._bg.place(x=0, y=0, relwidth=1, relheight=1)
        self._bg.bind("<Configure>", self._draw_background)

        self._pages: dict[str, BasePage] = {}
        self._pages["login"] = LoginPage(self, self)
        self._pages["main"] = MainPage(self, self)

        for page in self._pages.values():
            page.place(relx=0.5, rely=0.5, anchor="center", relwidth=0.78, relheight=0.82)
            page.lower()

        self.show_page("login")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("Card.TFrame", background=CARD_BG)
        style.configure("Title.TLabel", background=CARD_BG, foreground=TEXT, font=("Bahnschrift", 20, "bold"))
        style.configure("Subtitle.TLabel", background=CARD_BG, foreground=TEXT_MUTED, font=("Bahnschrift", 11))
        style.configure("Field.TLabel", background=CARD_BG, foreground=TEXT, font=("Bahnschrift", 10, "bold"))
        style.configure("Help.TLabel", background=CARD_BG, foreground=TEXT_MUTED, font=("Bahnschrift", 9))
        style.configure("Status.TLabel", background=CARD_BG, foreground=TEXT_MUTED, font=("Bahnschrift", 9))
        style.configure("StatusError.TLabel", background=CARD_BG, foreground=ERROR, font=("Bahnschrift", 9))
        style.configure(
            "Field.TCheckbutton", background=CARD_BG, foreground=TEXT, font=("Bahnschrift", 9)
        )
        style.map("Field.TCheckbutton", foreground=[("active", ACCENT)])

        style.configure(
            "Primary.TButton",
            background=ACCENT,
            foreground="white",
            font=("Bahnschrift", 11, "bold"),
            padding=(10, 8),
        )
        style.map(
            "Primary.TButton",
            background=[("active", ACCENT_HOVER), ("disabled", "#A6B7C8")],
        )

        style.configure("Field.TEntry", fieldbackground="#F9FAFB", foreground=TEXT, padding=6)
        style.configure("Field.TCombobox", fieldbackground="#F9FAFB", foreground=TEXT, padding=4)
        style.map("Field.TCombobox", fieldbackground=[("readonly", "#F9FAFB")])

        style.configure(
            "Mode.TRadiobutton",
            background=CARD_BG,
            foreground=TEXT,
            font=("Bahnschrift", 11, "bold"),
            padding=(6, 4),
        )
        style.map("Mode.TRadiobutton", foreground=[("active", ACCENT)])

        style.configure(
            "Link.TButton",
            background=CARD_BG,
            foreground=ACCENT,
            font=("Bahnschrift", 10, "bold"),
            padding=(6, 2),
            borderwidth=0,
        )
        style.map("Link.TButton", foreground=[("active", ACCENT_HOVER)])

        style.configure(
            "Accent.Horizontal.TScale",
            troughcolor="#E3E8EF",
            background=ACCENT,
        )

    def _draw_background(self, event: tk.Event) -> None:
        self._bg.delete("all")
        width = event.width
        height = event.height

        r1, g1, b1 = self._hex_to_rgb(BG_TOP)
        r2, g2, b2 = self._hex_to_rgb(BG_BOTTOM)

        for i in range(height):
            ratio = i / max(height - 1, 1)
            r = int(r1 + (r2 - r1) * ratio)
            g = int(g1 + (g2 - g1) * ratio)
            b = int(b1 + (b2 - b1) * ratio)
            color = f"#{r:02x}{g:02x}{b:02x}"
            self._bg.create_line(0, i, width, i, fill=color)

        self._bg.create_oval(
            width * 0.55,
            -height * 0.2,
            width * 1.1,
            height * 0.4,
            fill="#DCE6F1",
            outline="",
        )
        self._bg.create_oval(
            -width * 0.2,
            height * 0.55,
            width * 0.4,
            height * 1.1,
            fill="#EADFD3",
            outline="",
        )

    @staticmethod
    def _hex_to_rgb(value: str) -> tuple[int, int, int]:
        value = value.lstrip("#")
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))

    def show_page(self, name: str) -> None:
        for page_name, page in self._pages.items():
            if page_name == name:
                page.lift()
            else:
                page.lower()

    def save_credentials_to_env(
        self, credentials: Credentials, device_ip: Optional[str]
    ) -> Optional[str]:
        updates = {
            "TAPO_EMAIL": credentials.email,
            "TAPO_PASSWORD": credentials.password,
            "TAPO_IP": device_ip or "",
        }
        return self._write_env_file(updates)

    def set_credentials(self, credentials: Credentials, device_ip: Optional[str]) -> None:
        self._coordinator = SyncCoordinator(credentials)
        self.device_ip = device_ip
        page = self._pages.get("main")
        if isinstance(page, MainPage):
            page.set_device_ip(device_ip)

    def set_status(self, message: str, is_error: bool = False) -> None:
        page = self._pages.get("main")
        if isinstance(page, MainPage):
            page.set_status(message, is_error)

    def set_login_status(self, message: str) -> None:
        page = self._pages.get("login")
        if isinstance(page, LoginPage):
            page.set_status(message)

    def sign_out(self) -> None:
        if self._closing:
            return
        page = self._pages.get("main")
        if isinstance(page, MainPage):
            page.set_status("Signing out...")
            page.set_running(False)

        if not self._coordinator:
            self._finish_sign_out(None)
            return

        future = self._runner.run(self._coordinator.stop())
        self._attach_future(
            future,
            success_message="Signed out.",
            running=False,
            on_complete=self._finish_sign_out,
        )

    def start_sync(
        self,
        mode: SyncMode,
        device_ip: Optional[str],
        audio_settings: AudioSettings,
        screen_settings: ScreenSettings,
        brightness: int,
    ) -> None:
        if not self._coordinator:
            self.set_status("Please sign in first.", is_error=True)
            return

        self._set_running(True)
        page = self._pages.get("main")
        if isinstance(page, MainPage):
            page.set_status("Starting sync...")

        future = self._runner.run(
            self._coordinator.start(
                mode,
                device_ip,
                audio_settings,
                screen_settings,
                screen_brightness=brightness,
            )
        )
        self._attach_future(future, success_message="Sync running.", running=True)

    def stop_sync(self) -> None:
        if not self._coordinator:
            return
        self._set_running(False)
        page = self._pages.get("main")
        if isinstance(page, MainPage):
            page.set_status("Stopping...")

        future = self._runner.run(self._coordinator.stop())
        self._attach_future(future, success_message="Stopped.", running=False)

    def update_screen_brightness(self, value: int) -> None:
        if not self._coordinator:
            return
        self._runner.call_soon(self._coordinator.set_screen_brightness, value)

    def get_audio_devices(self) -> list[AudioDevice]:
        try:
            try:
                import pyaudiowpatch as pyaudio
            except ImportError:
                import pyaudio
        except ImportError:
            return []

        devices: list[AudioDevice] = []
        p = pyaudio.PyAudio()
        try:
            count = p.get_device_count()
            for idx in range(count):
                info = p.get_device_info_by_index(idx)
                channels = int(info.get("maxInputChannels", 0))
                if channels <= 0:
                    continue
                name = str(info.get("name", f"Device {idx}"))
                devices.append(AudioDevice(index=idx, name=name, channels=channels))
        except Exception:
            return []
        finally:
            try:
                p.terminate()
            except Exception:
                pass

        return devices

    def _write_env_file(self, updates: dict[str, str]) -> Optional[str]:
        try:
            if ENV_PATH.exists():
                lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
            else:
                lines = []
            new_lines = self._merge_env_lines(lines, updates)
            ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        except OSError as exc:
            return f"Could not save .env: {exc}"
        return None

    def _merge_env_lines(self, lines: list[str], updates: dict[str, str]) -> list[str]:
        remaining = dict(updates)
        new_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                new_lines.append(line)
                continue
            key, _value = line.split("=", 1)
            key = key.strip()
            if key in remaining:
                new_lines.append(f"{key}={self._format_env_value(remaining.pop(key))}")
            else:
                new_lines.append(line)
        for key, value in remaining.items():
            new_lines.append(f"{key}={self._format_env_value(value)}")
        return new_lines

    @staticmethod
    def _format_env_value(value: str) -> str:
        if value == "":
            return ""
        if re.search(r"\s|#|\"", value):
            escaped = value.replace("\\", "\\\\").replace("\"", "\\\"")
            return f"\"{escaped}\""
        return value

    def _attach_future(
        self,
        future: asyncio.Future,
        success_message: str,
        running: bool,
        on_complete: Optional[Callable[[Optional[Exception]], None]] = None,
    ) -> None:
        def _done(fut: asyncio.Future) -> None:
            exc: Optional[Exception] = None
            try:
                fut.result()
            except Exception as err:
                exc = err
                if not self._closing:
                    self.after(0, lambda: self.set_status(self._format_error(err), is_error=True))
                    self.after(0, lambda: self._set_running(False))
            else:
                if not self._closing:
                    self.after(0, lambda: self.set_status(success_message))
                    self.after(0, lambda: self._set_running(running))
            if on_complete:
                self.after(0, lambda: on_complete(exc))

        future.add_done_callback(_done)

    def _format_error(self, exc: Exception) -> str:
        message = str(exc).strip()
        if isinstance(exc, ValueError) and "Device IP is required" in message:
            return "Enter the device IP to start audio sync."
        if "PyAudio is required" in message:
            return "Audio sync needs PyAudio. Install pyaudio or pyaudiowpatch."
        if "Device not connected" in message:
            return "Couldn't connect to the device. Check the IP and credentials."
        if not message:
            return "Something went wrong. Please try again."
        return message

    def _set_running(self, running: bool) -> None:
        page = self._pages.get("main")
        if isinstance(page, MainPage):
            page.set_running(running)

    def _on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self._coordinator:
            future = self._runner.run(self._coordinator.stop())

            def _done(fut: asyncio.Future) -> None:
                try:
                    fut.result()
                except Exception:
                    pass
                self.after(0, self._shutdown)

            future.add_done_callback(_done)
            return
        self._shutdown()

    def _shutdown(self) -> None:
        self._runner.stop()
        self.destroy()

    def _finish_sign_out(self, exc: Optional[Exception]) -> None:
        if exc:
            self.set_login_status(self._format_error(exc))
        else:
            self.set_login_status("")
        self._coordinator = None
        page = self._pages.get("main")
        if isinstance(page, MainPage):
            page.set_status("Idle.")
            page.set_running(False)
        self.show_page("login")
