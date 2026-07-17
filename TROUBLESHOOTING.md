# Troubleshooting LANLink from another PC or Codex

The public repository includes all source files and the bundled Windows executable. Clone it on any PC with Codex:

```powershell
git clone https://github.com/kmarsus/LANLink.git
cd LANLink
```

For a normal installation, copy the complete folder, run `install.bat`, then inspect these files on the affected computer:

- `%LOCALAPPDATA%\LANLink\lanlink.log` — startup and runtime diagnostics (rotated automatically)
- `%LOCALAPPDATA%\LANLink\settings.json` — local configuration; **never share this file publicly** because it contains device secrets and pairing tokens

The local-only diagnostic summary is available while LANLink is running:

`http://127.0.0.1:8764/api/diagnostics`

Useful checks:

1. Confirm `LANLink.exe` is still running in Task Manager.
2. Open `http://127.0.0.1:8764` on the affected PC.
3. Confirm the Windows network profile is **Private**; LANLink's installer intentionally scopes firewall rules to Private networks.
4. Ensure TCP `8765` and UDP `53421` are not blocked by third-party security software.
5. For source-level investigation, install Python 3.11+ only on the developer/Codex PC, then run `python -m pip install -e . pytest` and `python -m pytest`.

When requesting help, share the relevant `lanlink.log` lines and the error you see, but do not share `settings.json`, pairing PINs, or unattended-access PINs.
