from __future__ import annotations

import ctypes
import io
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from PIL import ImageGrab


@dataclass
class RemoteRequest:
    request_id: str
    device_id: str
    device_name: str
    control: bool
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    session_token: str = ""


class RemoteManager:
    def __init__(self):
        self._lock = threading.RLock()
        self.requests: dict[str, RemoteRequest] = {}
        self.sessions: dict[str, dict[str, Any]] = {}

    def request(self, device_id: str, device_name: str, control: bool) -> RemoteRequest:
        with self._lock:
            request = RemoteRequest(secrets.token_urlsafe(18), device_id, device_name, control)
            self.requests[request.request_id] = request
            return request

    def approve(self, request_id: str) -> RemoteRequest | None:
        with self._lock:
            request = self.requests.get(request_id)
            if not request or request.status != "pending":
                return None
            request.status = "approved"
            request.session_token = secrets.token_urlsafe(32)
            self.sessions[request.session_token] = {
                "device_id": request.device_id,
                "control": request.control,
                "last_seen": time.time(),
            }
            return request

    def reject(self, request_id: str) -> bool:
        with self._lock:
            request = self.requests.get(request_id)
            if not request or request.status != "pending":
                return False
            request.status = "rejected"
            return True

    def pending(self) -> list[dict[str, Any]]:
        with self._lock:
            return [vars(item).copy() for item in self.requests.values()
                    if item.status == "pending" and time.time() - item.created_at < 300]

    def request_status(self, request_id: str, device_id: str) -> dict[str, Any] | None:
        with self._lock:
            request = self.requests.get(request_id)
            if not request or request.device_id != device_id:
                return None
            return {"status": request.status, "session_token": request.session_token if request.status == "approved" else ""}

    def session(self, token: str, device_id: str, require_control: bool = False) -> dict[str, Any] | None:
        with self._lock:
            session = self.sessions.get(token)
            if not session or session["device_id"] != device_id:
                return None
            if time.time() - session["last_seen"] > 3600 or (require_control and not session["control"]):
                self.sessions.pop(token, None)
                return None
            session["last_seen"] = time.time()
            return dict(session)

    def disconnect(self, token: str) -> None:
        with self._lock:
            self.sessions.pop(token, None)


def capture_screen(quality: int = 70, max_width: int = 1920) -> bytes:
    image = ImageGrab.grab(all_screens=True)
    if image.width > max_width:
        ratio = max_width / image.width
        image = image.resize((max_width, max(1, int(image.height * ratio))))
    stream = io.BytesIO()
    image.convert("RGB").save(stream, "JPEG", quality=max(25, min(90, quality)), optimize=True)
    return stream.getvalue()


KEYS = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "shift": 0x10,
    "ctrl": 0x11, "control": 0x11, "alt": 0x12, "escape": 0x1B, "space": 0x20,
    "pageup": 0x21, "pagedown": 0x22, "end": 0x23, "home": 0x24,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "delete": 0x2E, "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78,
    "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "arrowleft": 0x25, "arrowup": 0x26, "arrowright": 0x27, "arrowdown": 0x28,
}


def inject_input(event: dict[str, Any]) -> None:
    if os.name != "nt":
        raise RuntimeError("Remote input is supported on Windows only")
    user32 = ctypes.windll.user32
    kind = event.get("type")
    if kind == "move":
        screen_w, screen_h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        x = max(0, min(screen_w - 1, int(float(event.get("x", 0)) * screen_w)))
        y = max(0, min(screen_h - 1, int(float(event.get("y", 0)) * screen_h)))
        user32.SetCursorPos(x, y)
    elif kind in ("mousedown", "mouseup"):
        button = event.get("button", 0)
        flags = {("mousedown", 0): 0x0002, ("mouseup", 0): 0x0004,
                 ("mousedown", 2): 0x0008, ("mouseup", 2): 0x0010}.get((kind, button))
        if flags:
            user32.mouse_event(flags, 0, 0, 0, 0)
    elif kind == "wheel":
        user32.mouse_event(0x0800, 0, 0, int(event.get("delta", 0)), 0)
    elif kind in ("keydown", "keyup"):
        key = str(event.get("key", "")).lower()
        vk = KEYS.get(key)
        if vk is None and len(key) == 1 and key.isascii():
            vk = user32.VkKeyScanW(ord(key)) & 0xFF
        if vk is not None:
            user32.keybd_event(vk, 0, 0 if kind == "keydown" else 0x0002, 0)


def get_clipboard_text() -> str:
    import tkinter
    root = tkinter.Tk()
    root.withdraw()
    try:
        return root.clipboard_get()
    except tkinter.TclError:
        return ""
    finally:
        root.destroy()


def set_clipboard_text(text: str) -> None:
    import tkinter
    root = tkinter.Tk()
    root.withdraw()
    root.clipboard_clear()
    root.clipboard_append(text[:1_000_000])
    root.update()
    root.destroy()
