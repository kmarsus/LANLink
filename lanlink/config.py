from __future__ import annotations

import hashlib
import json
import os
import platform
import secrets
import socket
import threading
import uuid
from datetime import datetime, timedelta, timezone
from copy import deepcopy
from pathlib import Path
from typing import Any


def _data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / "LANLink"


def pin_hash(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), salt.encode(), 180_000).hex()


def ensure_certificate(data_dir: Path) -> tuple[Path, Path]:
    """Create a per-device self-signed certificate used to encrypt LAN traffic."""
    cert_path, key_path = data_dir / "lanlink.crt", data_dir / "lanlink.key"
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import ipaddress

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, socket.gethostname())])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=1825))
            .add_extension(x509.SubjectAlternativeName([
                x509.DNSName(socket.gethostname()), x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
            ]), critical=False).sign(key, hashes.SHA256()))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


class Settings:
    """Thread-safe JSON settings with atomic replacement."""

    def __init__(self, path: Path | None = None):
        self.path = path or (_data_dir() / "settings.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.data = self._load()

    def _defaults(self) -> dict[str, Any]:
        device_id = str(uuid.uuid4())
        salt = secrets.token_hex(16)
        return {
            "device_id": device_id,
            "device_name": socket.gethostname(),
            "platform": platform.platform(),
            "port": 8765,
            "device_secret": secrets.token_hex(32),
            "pin_salt": salt,
            "pairing_mode": "approval",
            "pairing_pin_hash": "",
            "shares": [],
            "trusted_devices": {},
            "outgoing_tokens": {},
            "blocked_devices": [],
            "unattended_enabled": False,
            "unattended_pin_hash": "",
            "remote_quality": 70,
        }

    def _load(self) -> dict[str, Any]:
        default = self._defaults()
        if not self.path.exists():
            self.data = default
            self.save()
            return default
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            default.update(loaded)
            return default
        except (OSError, json.JSONDecodeError):
            backup = self.path.with_suffix(".broken.json")
            try:
                self.path.replace(backup)
            except OSError:
                pass
            self.data = default
            self.save()
            return default

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self.data)

    def save(self) -> None:
        with self._lock:
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            temporary.replace(self.path)

    def update(self, **values: Any) -> None:
        with self._lock:
            self.data.update(values)
            self.save()

    def set_pairing_pin(self, pin: str) -> None:
        if pin and (not pin.isdigit() or not 4 <= len(pin) <= 10):
            raise ValueError("PIN must be 4-10 digits")
        self.update(pairing_pin_hash=pin_hash(pin, self.data["pin_salt"]) if pin else "")

    def check_pairing_pin(self, pin: str) -> bool:
        expected = self.data.get("pairing_pin_hash", "")
        return bool(expected) and secrets.compare_digest(expected, pin_hash(pin, self.data["pin_salt"]))

    def set_unattended_pin(self, pin: str) -> None:
        if pin and (not pin.isdigit() or not 6 <= len(pin) <= 12):
            raise ValueError("Unattended PIN must be 6-12 digits")
        self.update(unattended_pin_hash=pin_hash(pin, self.data["pin_salt"]) if pin else "")

    def check_unattended_pin(self, pin: str) -> bool:
        expected = self.data.get("unattended_pin_hash", "")
        return bool(expected) and secrets.compare_digest(expected, pin_hash(pin, self.data["pin_salt"]))

    def issue_token(self, device_id: str, device_name: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self.data["trusted_devices"][device_id] = {
                "name": device_name,
                "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            }
            self.save()
        return token

    def verify_token(self, device_id: str, token: str) -> bool:
        record = self.data.get("trusted_devices", {}).get(device_id)
        if not record or device_id in self.data.get("blocked_devices", []):
            return False
        actual = hashlib.sha256(token.encode()).hexdigest()
        return secrets.compare_digest(record["token_hash"], actual)

    def certificate_paths(self) -> tuple[Path, Path]:
        return ensure_certificate(self.path.parent)
