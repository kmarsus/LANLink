# LANLink

LANLink is an open-source, Windows-first LAN file-sharing and remote-support MVP, released under the [MIT License](LICENSE). It avoids Windows SMB configuration: each PC runs the service, discovers peers with UDP broadcast, and exposes only folders explicitly selected in the local dashboard.

## Install on Windows

1. Download the LANLink release ZIP and extract the complete `LANLink` folder to a permanent location on each office PC.
2. Double-click `install.bat` and approve the Windows permission prompt. No Python installation is required; `LANLink.exe` contains the runtime and application libraries.
3. The installer adds only LANLink's Private-network firewall rules, starts LANLink, and configures automatic start at sign-in.
4. The dashboard opens at `http://127.0.0.1:8764`.

Run `run.bat` to open it later. Run `uninstall.ps1` from PowerShell to remove startup shortcuts and firewall rules; personal settings and shared files are retained.

## Typical workflow

1. Click **Share a folder**, select a folder or drive, and choose **Read only** or **Full access**.
2. On another LANLink PC, select the discovered computer and click **Pair computer**.
3. Approve the request on the sharing PC, or use its configured pairing PIN.
4. Browse and download files. Full-access shares also allow uploads, folders, copies, renames, and deletion.
5. For remote help, click **Remote support**. The other PC must approve screen/control access. Unattended access remains off until its owner enables it and creates a separate PIN.

## Security model

- The management dashboard accepts requests only from the local PC.
- Random 256-bit capability tokens are issued after approval/PIN pairing; only token hashes are stored by the sharing PC.
- Computer-to-computer traffic is encrypted with a per-device, automatically generated HTTPS certificate. The management dashboard is a separate loopback-only HTTP listener.
- Every path is resolved and confined to its selected share, including copy, upload, rename, and deletion operations.
- Read-only mode is enforced by the server, not just hidden in the UI.
- Remote sessions use separate, expiring random tokens and require a new approval. Blocking a computer disconnects its sessions.
- Unattended access is opt-in and requires a separate 6–12 digit PIN.
- Firewall rules are restricted to Windows **Private** network profiles.

LANLink 0.1 is intended for a trusted office LAN. Its self-signed TLS encrypts traffic but does not provide public-CA identity validation, so do not expose port 8765 to the public internet or an untrusted Wi-Fi network. Production hardening should add certificate-fingerprint confirmation or a private CA, signed updates, audit logging, rate limiting, and Windows Credential Manager/DPAPI secret storage.

## Remote support scope

The working remote-support MVP provides JPEG screen streaming, adjustable quality, full-screen viewing, mouse/keyboard injection after approval, text clipboard exchange, disconnect, block, and file transfer through the normal share browser.

It is not yet a kernel/service-level AnyDesk replacement. It cannot control Windows secure desktop/UAC prompts or the lock screen, capture a logged-out session, traverse the internet without a VPN, relay through NAT, stream audio, or deliver hardware-accelerated low-latency video. Those require a signed Windows service, a production transport such as WebRTC/QUIC, and a relay/signaling service.

## Development

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e . pytest pyinstaller
.venv\Scripts\python -m pytest
.venv\Scripts\python -m PyInstaller --noconsole --onefile --name LANLink launcher.py
```

Default ports: HTTPS LAN service `8765`, local dashboard `8764`, UDP discovery `53421`.

## Troubleshooting from another Codex PC

All source code and the standalone `LANLink.exe` are stored in this repository. See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for clone, diagnostic-log, and safe-support instructions.
