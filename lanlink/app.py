from __future__ import annotations

import argparse
import hashlib
import logging
import os
import secrets
import shutil
import threading
import time
import webbrowser
from functools import wraps
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import requests as requests_module
from flask import Flask, Response, abort, jsonify, render_template, request, send_file
from waitress import serve
from werkzeug.serving import make_server

from .config import Settings
from .discovery import DiscoveryService
from .remote import RemoteManager, capture_screen, get_clipboard_text, inject_input, set_clipboard_text

requests_module.packages.urllib3.disable_warnings(requests_module.packages.urllib3.exceptions.InsecureRequestWarning)
requests = requests_module.Session()
requests.verify = False


def configure_logging(settings: Settings) -> Path:
    """Write diagnostic logs that remain available from a packaged GUI build."""
    log_path = settings.path.parent / "lanlink.log"
    logger = logging.getLogger("lanlink")
    if not any(getattr(handler, "baseFilename", None) == str(log_path) for handler in logger.handlers):
        handler = RotatingFileHandler(log_path, maxBytes=1_500_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return log_path


def safe_path(root: str | Path, relative: str = "", must_exist: bool = True) -> Path:
    base = Path(root).resolve()
    relative = relative.replace("\\", "/").lstrip("/")
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as error:
        raise ValueError("Path leaves the shared folder") from error
    if must_exist and not candidate.exists():
        raise FileNotFoundError(relative)
    return candidate


def share_by_id(settings: Settings, share_id: str) -> dict[str, Any] | None:
    return next((item for item in settings.data["shares"] if item["id"] == share_id), None)


def create_app(settings_path: Path | None = None, start_discovery: bool = True) -> Flask:
    root = Path(__file__).resolve().parent
    app = Flask(__name__, template_folder=str(root / "templates"), static_folder=str(root / "static"))
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024
    settings = Settings(settings_path)
    discovery = DiscoveryService(settings)
    remote = RemoteManager()
    pairing_requests: dict[str, dict[str, Any]] = {}
    pin_attempts: dict[str, list[float]] = {}
    outgoing_pairing: dict[str, str] = {}
    outgoing_remote: dict[str, dict[str, str]] = {}
    app.extensions.update(lan_settings=settings, lan_discovery=discovery, remote_manager=remote)
    if start_discovery:
        discovery.start()

    def is_local() -> bool:
        return request.remote_addr in ("127.0.0.1", "::1")

    def local_only(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            if not is_local():
                abort(403, "The management interface is available only on this PC")
            return function(*args, **kwargs)
        return wrapper

    def paired_only(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            device_id = request.headers.get("X-Device-ID", "")
            token = request.headers.get("Authorization", "").removeprefix("Bearer ")
            if not settings.verify_token(device_id, token):
                return jsonify(error="Pairing required"), 401
            request.paired_device_id = device_id
            return function(*args, **kwargs)
        return wrapper

    def peer(device_id: str) -> tuple[dict[str, Any], str]:
        item = discovery.get(device_id)
        if not item:
            abort(404, "Computer is offline")
        return item, f"{item.get('scheme', 'https')}://{item['host']}:{item['port']}"

    def auth_headers(device_id: str, session_token: str = "") -> dict[str, str]:
        token = settings.data.get("outgoing_tokens", {}).get(device_id, "")
        headers = {"X-Device-ID": settings.data["device_id"], "Authorization": f"Bearer {token}"}
        if session_token:
            headers["X-Session-Token"] = session_token
        return headers

    def relay_error(response: requests.Response):
        try:
            message = response.json().get("error", response.text)
        except ValueError:
            message = response.text
        return jsonify(error=message or f"Remote error {response.status_code}"), response.status_code

    @app.errorhandler(ValueError)
    @app.errorhandler(FileNotFoundError)
    def input_error(error):
        return jsonify(error=str(error) or "Not found"), 400 if isinstance(error, ValueError) else 404

    @app.get("/")
    @local_only
    def index():
        return render_template("index.html")

    @app.get("/remote/<device_id>")
    @local_only
    def remote_page(device_id: str):
        return render_template("remote.html", device_id=device_id)

    @app.get("/api/state")
    @local_only
    def state():
        data = settings.snapshot()
        peers = discovery.online_peers()
        for item in peers:
            item["paired"] = item["device_id"] in data.get("outgoing_tokens", {})
            item["blocked"] = item["device_id"] in data.get("blocked_devices", [])
        public_settings = {key: data[key] for key in (
            "device_id", "device_name", "port", "pairing_mode", "shares",
            "unattended_enabled", "remote_quality"
        )}
        public_settings["pairing_pin_set"] = bool(data.get("pairing_pin_hash"))
        public_settings["unattended_pin_set"] = bool(data.get("unattended_pin_hash"))
        trusted = [{"device_id": key, "name": value["name"], "blocked": key in data["blocked_devices"]}
                   for key, value in data["trusted_devices"].items()]
        return jsonify(settings=public_settings, peers=peers, pairing_requests=list(pairing_requests.values()),
                       remote_requests=remote.pending(), trusted_devices=trusted)

    @app.get("/api/diagnostics")
    @local_only
    def diagnostics():
        return jsonify(version="0.1.0", log_path=str(settings.path.parent / "lanlink.log"),
                       settings_path=str(settings.path), discovery_peers=len(discovery.online_peers()))

    @app.patch("/api/settings")
    @local_only
    def update_settings():
        body = request.get_json(force=True)
        changes = {}
        if "device_name" in body:
            name = str(body["device_name"]).strip()[:64]
            if not name:
                raise ValueError("Computer name is required")
            changes["device_name"] = name
        if "pairing_mode" in body:
            if body["pairing_mode"] not in ("approval", "pin"):
                raise ValueError("Unknown pairing mode")
            changes["pairing_mode"] = body["pairing_mode"]
        if "pairing_pin" in body:
            settings.set_pairing_pin(str(body["pairing_pin"]))
        if "remote_quality" in body:
            changes["remote_quality"] = max(25, min(90, int(body["remote_quality"])))
        if "unattended_enabled" in body:
            enabled = bool(body["unattended_enabled"])
            if enabled and not (body.get("unattended_pin") or settings.data.get("unattended_pin_hash")):
                raise ValueError("Set a 6-12 digit unattended PIN first")
            changes["unattended_enabled"] = enabled
        if "unattended_pin" in body:
            settings.set_unattended_pin(str(body["unattended_pin"]))
        if changes:
            settings.update(**changes)
        return jsonify(ok=True)

    @app.post("/api/shares")
    @local_only
    def add_share():
        body = request.get_json(force=True)
        path = Path(str(body.get("path", ""))).expanduser().resolve()
        if not path.is_dir():
            raise ValueError("Select an existing folder or drive")
        mode = body.get("mode", "read")
        if mode not in ("read", "full"):
            raise ValueError("Mode must be read or full")
        item = {"id": secrets.token_hex(8), "name": str(body.get("name") or path.name or str(path))[:80],
                "path": str(path), "mode": mode}
        with settings._lock:
            if any(Path(existing["path"]).resolve() == path for existing in settings.data["shares"]):
                raise ValueError("That location is already shared")
            settings.data["shares"].append(item)
            settings.save()
        return jsonify(item), 201

    @app.post("/api/pick-folder")
    @local_only
    def pick_folder():
        import tkinter
        from tkinter import filedialog
        root_window = tkinter.Tk()
        root_window.withdraw()
        root_window.attributes("-topmost", True)
        try:
            selected = filedialog.askdirectory(title="Choose a folder or drive to share", mustexist=True)
        finally:
            root_window.destroy()
        return jsonify(path=selected)

    @app.delete("/api/shares/<share_id>")
    @local_only
    def remove_share(share_id: str):
        with settings._lock:
            before = len(settings.data["shares"])
            settings.data["shares"] = [item for item in settings.data["shares"] if item["id"] != share_id]
            settings.save()
        return jsonify(ok=before != len(settings.data["shares"]))

    @app.post("/api/trusted/<device_id>/<action>")
    @local_only
    def trusted_action(device_id: str, action: str):
        with settings._lock:
            if action == "revoke":
                settings.data["trusted_devices"].pop(device_id, None)
            elif action == "block":
                if device_id not in settings.data["blocked_devices"]:
                    settings.data["blocked_devices"].append(device_id)
                for token, session in list(remote.sessions.items()):
                    if session["device_id"] == device_id:
                        remote.disconnect(token)
            elif action == "unblock":
                settings.data["blocked_devices"] = [item for item in settings.data["blocked_devices"] if item != device_id]
            else:
                raise ValueError("Unknown action")
            settings.save()
        return jsonify(ok=True)

    # Pairing endpoints exposed to LAN peers.
    @app.post("/api/public/pair")
    def pair_request():
        if request.content_length and request.content_length > 16_384:
            return jsonify(error="Pairing request is too large"), 413
        body = request.get_json(force=True)
        device_id = str(body.get("device_id", ""))
        name = str(body.get("device_name", "Unknown computer"))[:64]
        if not device_id or device_id in settings.data["blocked_devices"]:
            return jsonify(error="Pairing is blocked"), 403
        now = time.time()
        for key, value in list(pairing_requests.items()):
            if now - value.get("created_at", now) >= 600:
                pairing_requests.pop(key, None)
        if settings.data["pairing_mode"] == "pin":
            address = request.remote_addr or "unknown"
            recent = [stamp for stamp in pin_attempts.get(address, []) if now - stamp < 300]
            if len(recent) >= 8:
                return jsonify(error="Too many pairing attempts; wait five minutes"), 429
            recent.append(now)
            pin_attempts[address] = recent
        request_id = secrets.token_urlsafe(18)
        status = "pending"
        token = ""
        if settings.data["pairing_mode"] == "pin" and settings.check_pairing_pin(str(body.get("pin", ""))):
            token, status = settings.issue_token(device_id, name), "approved"
        pairing_requests[request_id] = {"request_id": request_id, "device_id": device_id, "device_name": name,
                                        "status": status, "token": token, "created_at": now}
        return jsonify(request_id=request_id, status=status)

    @app.get("/api/public/pair/<request_id>")
    def pair_status(request_id: str):
        device_id = request.args.get("device_id", "")
        item = pairing_requests.get(request_id)
        if not item or item["device_id"] != device_id:
            return jsonify(error="Pairing request not found"), 404
        return jsonify(status=item["status"], token=item["token"] if item["status"] == "approved" else "")

    @app.post("/api/pairing/<request_id>/<action>")
    @local_only
    def decide_pairing(request_id: str, action: str):
        item = pairing_requests.get(request_id)
        if not item or item["status"] != "pending":
            return jsonify(error="Pairing request is no longer pending"), 404
        if action == "approve":
            item["token"] = settings.issue_token(item["device_id"], item["device_name"])
            item["status"] = "approved"
        elif action == "reject":
            item["status"] = "rejected"
        else:
            raise ValueError("Unknown action")
        return jsonify(ok=True)

    @app.post("/api/peers/<device_id>/pair")
    @local_only
    def begin_outgoing_pair(device_id: str):
        _, base = peer(device_id)
        body = request.get_json(silent=True) or {}
        response = requests.post(base + "/api/public/pair", json={"device_id": settings.data["device_id"],
            "device_name": settings.data["device_name"], "pin": str(body.get("pin", ""))}, timeout=5)
        if not response.ok:
            return relay_error(response)
        result = response.json()
        outgoing_pairing[device_id] = result["request_id"]
        return jsonify(result)

    @app.get("/api/peers/<device_id>/pair")
    @local_only
    def poll_outgoing_pair(device_id: str):
        _, base = peer(device_id)
        request_id = outgoing_pairing.get(device_id)
        if not request_id:
            return jsonify(error="No pending pairing request"), 404
        response = requests.get(base + f"/api/public/pair/{request_id}", params={"device_id": settings.data["device_id"]}, timeout=5)
        if not response.ok:
            return relay_error(response)
        result = response.json()
        if result.get("status") == "approved" and result.get("token"):
            with settings._lock:
                settings.data["outgoing_tokens"][device_id] = result["token"]
                settings.save()
        return jsonify(result)

    # Permissioned file server endpoints.
    @app.get("/api/public/shares")
    @paired_only
    def public_shares():
        return jsonify([{key: item[key] for key in ("id", "name", "mode")} for item in settings.data["shares"]])

    def require_share(share_id: str, write: bool = False) -> dict[str, Any]:
        item = share_by_id(settings, share_id)
        if not item:
            abort(404, "Share not found")
        if write and item["mode"] != "full":
            abort(403, "This share is read-only")
        return item

    @app.get("/api/public/files/<share_id>")
    @paired_only
    def list_files(share_id: str):
        share = require_share(share_id)
        folder = safe_path(share["path"], request.args.get("path", ""))
        if not folder.is_dir():
            raise ValueError("Path is not a folder")
        items = []
        for child in folder.iterdir():
            try:
                stat = child.stat()
                items.append({"name": child.name, "directory": child.is_dir(), "size": stat.st_size,
                              "modified": stat.st_mtime})
            except OSError:
                continue
        return jsonify(sorted(items, key=lambda item: (not item["directory"], item["name"].lower())))

    @app.get("/api/public/download/<share_id>")
    @paired_only
    def download_file(share_id: str):
        share = require_share(share_id)
        target = safe_path(share["path"], request.args.get("path", ""))
        if not target.is_file():
            raise ValueError("Only files can be downloaded")
        return send_file(target, as_attachment=True, download_name=target.name)

    @app.post("/api/public/upload/<share_id>")
    @paired_only
    def upload_file(share_id: str):
        share = require_share(share_id, write=True)
        folder = safe_path(share["path"], request.form.get("path", ""))
        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename:
            raise ValueError("Choose a file to upload")
        name = Path(uploaded.filename).name
        target = safe_path(folder, name, must_exist=False)
        uploaded.save(target)
        return jsonify(ok=True, name=name), 201

    @app.post("/api/public/operation/<share_id>")
    @paired_only
    def file_operation(share_id: str):
        share = require_share(share_id, write=True)
        body = request.get_json(force=True)
        operation = body.get("operation")
        target = safe_path(share["path"], str(body.get("path", "")), must_exist=(operation != "mkdir"))
        if target == Path(share["path"]).resolve():
            raise ValueError("The share root cannot be changed")
        if operation == "delete":
            shutil.rmtree(target) if target.is_dir() else target.unlink()
        elif operation == "rename":
            name = str(body.get("name", "")).strip()
            if not name or Path(name).name != name:
                raise ValueError("Enter a simple file name")
            destination = safe_path(target.parent, name, must_exist=False)
            target.rename(destination)
        elif operation == "mkdir":
            target.mkdir()
        elif operation == "copy":
            destination = safe_path(share["path"], str(body.get("destination", "")), must_exist=False)
            if target.is_dir():
                shutil.copytree(target, destination)
            else:
                shutil.copy2(target, destination)
        else:
            raise ValueError("Unknown operation")
        return jsonify(ok=True)

    # Local proxy keeps capability tokens out of the browser.
    @app.get("/api/peers/<device_id>/shares")
    @local_only
    def peer_shares(device_id: str):
        _, base = peer(device_id)
        response = requests.get(base + "/api/public/shares", headers=auth_headers(device_id), timeout=8)
        return jsonify(response.json()) if response.ok else relay_error(response)

    @app.get("/api/peers/<device_id>/files/<share_id>")
    @local_only
    def peer_files(device_id: str, share_id: str):
        _, base = peer(device_id)
        response = requests.get(base + f"/api/public/files/{share_id}", params={"path": request.args.get("path", "")},
                                headers=auth_headers(device_id), timeout=15)
        return jsonify(response.json()) if response.ok else relay_error(response)

    @app.get("/api/peers/<device_id>/download/<share_id>")
    @local_only
    def peer_download(device_id: str, share_id: str):
        _, base = peer(device_id)
        response = requests.get(base + f"/api/public/download/{share_id}", params={"path": request.args.get("path", "")},
                                headers=auth_headers(device_id), timeout=60, stream=True)
        if not response.ok:
            return relay_error(response)
        headers = {"Content-Disposition": response.headers.get("Content-Disposition", "attachment")}
        return Response(response.iter_content(65536), headers=headers, content_type=response.headers.get("Content-Type"))

    @app.post("/api/peers/<device_id>/upload/<share_id>")
    @local_only
    def peer_upload(device_id: str, share_id: str):
        _, base = peer(device_id)
        uploaded = request.files.get("file")
        if not uploaded:
            raise ValueError("Choose a file")
        response = requests.post(base + f"/api/public/upload/{share_id}", headers=auth_headers(device_id),
                                 data={"path": request.form.get("path", "")},
                                 files={"file": (uploaded.filename, uploaded.stream, uploaded.mimetype)}, timeout=300)
        return jsonify(response.json()) if response.ok else relay_error(response)

    @app.post("/api/peers/<device_id>/operation/<share_id>")
    @local_only
    def peer_operation(device_id: str, share_id: str):
        _, base = peer(device_id)
        response = requests.post(base + f"/api/public/operation/{share_id}", headers=auth_headers(device_id),
                                 json=request.get_json(force=True), timeout=30)
        return jsonify(response.json()) if response.ok else relay_error(response)

    # Approval-gated remote desktop server.
    def remote_session(require_control: bool = False):
        device_id = request.headers.get("X-Device-ID", "")
        pair_token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        session_token = request.headers.get("X-Session-Token", "")
        if not settings.verify_token(device_id, pair_token) or not remote.session(session_token, device_id, require_control):
            abort(401, "Remote session is not authorized")
        return session_token

    @app.post("/api/public/remote/request")
    @paired_only
    def request_remote():
        body = request.get_json(force=True)
        item = remote.request(request.paired_device_id, str(body.get("device_name", "Remote computer"))[:64],
                              bool(body.get("control", True)))
        if settings.data["unattended_enabled"] and settings.check_unattended_pin(str(body.get("pin", ""))):
            remote.approve(item.request_id)
        return jsonify(request_id=item.request_id, status=item.status)

    @app.get("/api/public/remote/request/<request_id>")
    @paired_only
    def poll_remote(request_id: str):
        result = remote.request_status(request_id, request.paired_device_id)
        return jsonify(result) if result else (jsonify(error="Request not found"), 404)

    @app.post("/api/remote/<request_id>/<action>")
    @local_only
    def decide_remote(request_id: str, action: str):
        if action == "approve":
            return jsonify(ok=bool(remote.approve(request_id)))
        if action == "reject":
            return jsonify(ok=remote.reject(request_id))
        raise ValueError("Unknown action")

    @app.get("/api/public/remote/screen")
    def remote_screen():
        remote_session()
        quality = int(request.args.get("quality", settings.data["remote_quality"]))
        return Response(capture_screen(quality), content_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.post("/api/public/remote/input")
    def remote_input():
        remote_session(require_control=True)
        inject_input(request.get_json(force=True))
        return jsonify(ok=True)

    @app.route("/api/public/remote/clipboard", methods=["GET", "POST"])
    def remote_clipboard():
        remote_session(require_control=request.method == "POST")
        if request.method == "POST":
            set_clipboard_text(str(request.get_json(force=True).get("text", "")))
            return jsonify(ok=True)
        return jsonify(text=get_clipboard_text())

    @app.post("/api/public/remote/disconnect")
    def remote_disconnect():
        token = remote_session()
        remote.disconnect(token)
        return jsonify(ok=True)

    @app.post("/api/peers/<device_id>/remote/request")
    @local_only
    def begin_peer_remote(device_id: str):
        _, base = peer(device_id)
        body = request.get_json(silent=True) or {}
        response = requests.post(base + "/api/public/remote/request", headers=auth_headers(device_id), json={
            "device_name": settings.data["device_name"], "control": body.get("control", True), "pin": body.get("pin", "")
        }, timeout=8)
        if not response.ok:
            return relay_error(response)
        result = response.json()
        outgoing_remote[device_id] = {"request_id": result["request_id"], "session_token": ""}
        return jsonify(result)

    @app.get("/api/peers/<device_id>/remote/request")
    @local_only
    def poll_peer_remote(device_id: str):
        _, base = peer(device_id)
        state = outgoing_remote.get(device_id)
        if not state:
            return jsonify(error="No remote request"), 404
        response = requests.get(base + f"/api/public/remote/request/{state['request_id']}",
                                headers=auth_headers(device_id), timeout=8)
        if not response.ok:
            return relay_error(response)
        result = response.json()
        if result.get("session_token"):
            state["session_token"] = result["session_token"]
        return jsonify(result)

    def peer_remote_call(device_id: str, method: str, endpoint: str, **kwargs):
        _, base = peer(device_id)
        state = outgoing_remote.get(device_id, {})
        session_token = state.get("session_token", "")
        if not session_token:
            abort(401, "Remote session has not been approved")
        return requests.request(method, base + endpoint, headers=auth_headers(device_id, session_token), timeout=20, **kwargs)

    @app.get("/api/peers/<device_id>/remote/screen")
    @local_only
    def peer_remote_screen(device_id: str):
        response = peer_remote_call(device_id, "GET", "/api/public/remote/screen",
                                    params={"quality": request.args.get("quality", "70")})
        return Response(response.content, status=response.status_code, content_type=response.headers.get("Content-Type"))

    @app.post("/api/peers/<device_id>/remote/input")
    @local_only
    def peer_remote_input(device_id: str):
        response = peer_remote_call(device_id, "POST", "/api/public/remote/input", json=request.get_json(force=True))
        return jsonify(response.json()), response.status_code

    @app.route("/api/peers/<device_id>/remote/clipboard", methods=["GET", "POST"])
    @local_only
    def peer_remote_clipboard(device_id: str):
        kwargs = {"json": request.get_json(force=True)} if request.method == "POST" else {}
        response = peer_remote_call(device_id, request.method, "/api/public/remote/clipboard", **kwargs)
        return jsonify(response.json()), response.status_code

    @app.post("/api/peers/<device_id>/remote/disconnect")
    @local_only
    def peer_remote_disconnect(device_id: str):
        response = peer_remote_call(device_id, "POST", "/api/public/remote/disconnect")
        outgoing_remote.pop(device_id, None)
        return jsonify(ok=response.ok)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="LANLink")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--dashboard-port", type=int, default=8764)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    app = create_app()
    settings: Settings = app.extensions["lan_settings"]
    log_path = configure_logging(settings)
    logger = logging.getLogger("lanlink")
    if args.port != settings.data["port"]:
        settings.update(port=args.port)
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{args.dashboard_port}")).start()
    cert_path, key_path = settings.certificate_paths()
    secure_server = make_server("0.0.0.0", args.port, app, threaded=True,
                                ssl_context=(str(cert_path), str(key_path)))
    threading.Thread(target=secure_server.serve_forever, name="lanlink-https", daemon=True).start()
    logger.info("LANLink started: dashboard=http://127.0.0.1:%s, LAN HTTPS port=%s, log=%s",
                args.dashboard_port, args.port, log_path)
    serve(app, host="127.0.0.1", port=args.dashboard_port, threads=12)


if __name__ == "__main__":
    main()
