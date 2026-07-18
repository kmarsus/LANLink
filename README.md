# LANLink

![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)
![Platform: Windows](https://img.shields.io/badge/platform-Windows-blue.svg)
![Status](https://img.shields.io/badge/status-MVP-orange.svg)
![LAN](https://img.shields.io/badge/network-LAN-success.svg)

**LANLink** is a free, open-source, Windows-first LAN file sharing and remote support application.

It enables computers on the same local network to discover each other automatically without requiring Windows SMB sharing configuration. Each computer runs its own LANLink service, discovers nearby devices using UDP broadcast, and exposes only folders explicitly selected by the local user.

LANLink is designed for offices, schools, businesses, and home networks where fast and secure local file sharing is required.

## Releases

The latest version is available from the GitHub Releases page:

https://github.com/kmarsus/LANLink/releases

Open the latest release and download the appropriate package from the **Assets** section.

## Features

- Automatic LAN device discovery
- Windows-first desktop application
- No Windows SMB configuration required
- Folder-based sharing
- User-controlled shared folders
- Local dashboard
- Built-in remote support
- Automatic Windows startup
- Automatic firewall configuration
- Private-network operation
- Offline LAN communication
- No cloud dependency
- No advertisements
- No tracking
- Open-source
- MIT License

## How It Works

Each computer runs the LANLink service.

LANLink automatically discovers nearby computers on the same LAN using UDP broadcast.

Only folders explicitly selected by the local user are shared.

No Windows network sharing configuration is required.

## Installation

1. Open the GitHub Releases page.
2. Open the latest release.
3. Download the Windows package from the **Assets** section.
4. Extract the downloaded archive to a permanent location.
5. Run the installer included in the package.
6. Approve the Windows permission prompt if requested.
7. LANLink automatically starts after installation.
8. The dashboard opens at:

```
http://127.0.0.1:8764
```

No separate Python installation is required when using the packaged Windows release.

## Startup

LANLink can automatically start when you sign in to Windows.

The installer configures startup automatically.

## Dashboard

The local dashboard is available at:

```
http://127.0.0.1:8764
```

The dashboard allows users to:

- View discovered devices
- Manage shared folders
- Configure application settings
- Monitor transfer status
- Start remote support sessions

## Shared Folders

LANLink never shares files automatically.

Users must explicitly choose which folders will be shared.

Folders can be added or removed at any time from the dashboard.

## Security

LANLink is designed for trusted local-area networks.

The application:

- Shares only user-selected folders
- Does not upload files to cloud services
- Does not require SMB sharing
- Does not expose files to the public internet
- Does not collect analytics
- Does not display advertisements

Users should operate LANLink only on trusted private networks.

## Privacy

LANLink operates primarily within the local network.

No online account is required.

No personal data is collected for analytics or advertising.

## Running from Source

Requirements:

- Windows 10 or Windows 11
- Python 3.10 or newer

Clone the repository:

```powershell
git clone https://github.com/kmarsus/LANLink.git
cd LANLink
```

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Run the application:

```powershell
python main.py
```

If your project uses another entry point, run the appropriate application file.

## Building

Install PyInstaller:

```powershell
python -m pip install pyinstaller
```

Build:

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

or

```powershell
pyinstaller --noconfirm --clean --windowed --name LANLink main.py
```

The generated application will normally be available inside the `dist` directory.

## Verify a Release

A release may include a SHA-256 checksum.

You can verify the downloaded application with:

```powershell
Get-FileHash .\LANLink.exe -Algorithm SHA256
```

Compare the result with the checksum published in the corresponding GitHub Release.

## SmartScreen

Windows Defender SmartScreen may initially display an **Unknown Publisher** warning if the application has not yet established sufficient reputation or is not digitally signed.

Users may:

- Review the source code
- Build the application from source
- Verify published checksums
- Download only from the official GitHub Releases page

## Contributing

Contributions are welcome.

You may:

- Report bugs
- Suggest features
- Improve documentation
- Submit pull requests

Please avoid committing secrets, passwords, certificates, or private information.

## Bug Reports

Please include:

- Windows version
- LANLink version
- Steps to reproduce
- Expected behavior
- Actual behavior
- Error messages
- Screenshots if applicable

## Roadmap

Future improvements may include:

- Encrypted transfers
- Multi-user authentication
- File version history
- Automatic updates
- Microsoft Store distribution
- Digitally signed releases
- Cross-platform support
- Better remote support tools
- Performance improvements
- Large-file optimization

## Search Keywords

LAN file sharing software, Windows LAN file sharing, local network file transfer, SMB alternative, peer discovery, office file sharing, LAN collaboration, Windows remote support, local file server, offline file sharing, Python LAN application, open-source LAN software.

## License

Copyright © 2026 Khandaker Marsus.

LANLink is free and open-source software released under the [MIT License](LICENSE).
