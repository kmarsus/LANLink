from __future__ import annotations

import json
import socket
import threading
import time
from typing import Any


DISCOVERY_PORT = 53421
MAGIC = "office-lan-share-v1"


class DiscoveryService:
    def __init__(self, settings):
        self.settings = settings
        self.peers: dict[str, dict[str, Any]] = {}
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        if self._threads:
            return
        for target, name in ((self._listen, "lan-discovery-listen"), (self._announce, "lan-discovery-announce")):
            thread = threading.Thread(target=target, name=name, daemon=True)
            self._threads.append(thread)
            thread.start()

    def stop(self) -> None:
        self._stop.set()

    def online_peers(self) -> list[dict[str, Any]]:
        now = time.time()
        result = []
        for peer in list(self.peers.values()):
            item = dict(peer)
            item["online"] = now - item.get("last_seen", 0) < 12
            result.append(item)
        return sorted(result, key=lambda item: (not item["online"], item.get("name", "").lower()))

    def get(self, device_id: str) -> dict[str, Any] | None:
        peer = self.peers.get(device_id)
        if peer and time.time() - peer.get("last_seen", 0) < 12:
            return dict(peer)
        return None

    def _payload(self) -> bytes:
        data = self.settings.snapshot()
        return json.dumps({
            "magic": MAGIC,
            "device_id": data["device_id"],
            "name": data["device_name"],
            "port": data["port"],
            "scheme": "https",
            "share_count": len(data["shares"]),
        }).encode()

    def _announce(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        while not self._stop.is_set():
            try:
                sock.sendto(self._payload(), ("255.255.255.255", DISCOVERY_PORT))
            except OSError:
                pass
            self._stop.wait(3)
        sock.close()

    def _listen(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("", DISCOVERY_PORT))
        except OSError:
            return
        sock.settimeout(1)
        own_id = self.settings.data["device_id"]
        while not self._stop.is_set():
            try:
                raw, address = sock.recvfrom(8192)
                data = json.loads(raw.decode())
                if data.get("magic") != MAGIC or data.get("device_id") == own_id:
                    continue
                data.update({"host": address[0], "last_seen": time.time()})
                self.peers[data["device_id"]] = data
            except (socket.timeout, UnicodeDecodeError, json.JSONDecodeError, KeyError):
                continue
            except OSError:
                break
        sock.close()
