## FBGrabber

Cross‑platform desktop app to download Facebook videos with quality selection, a managed download queue, progress indicators, and a clean modern UI.

### Features
- Quality selector after pasting a URL (lists available formats: resolution, fps, codec, size)
- Download queue with status, progress, speed, ETA
- Concurrent downloads control
- Choose download folder (defaults to your Videos/FBGrabber)
- Optional cookies file support for private videos
- Works on Windows, macOS, and Linux

### Prerequisites
- Python 3.9+

### Setup
```bash
# From the project root
python -m venv .venv

# Windows PowerShell
. .venv/Scripts/Activate.ps1

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### Run
```bash
python app/main.py
```

### Packaging
Packaging is per‑OS. Use PyInstaller; artifacts are placed in `dist/`.

#### Windows (.exe)
```powershell
python -m pip install pyinstaller
pyinstaller --noconfirm `
  --name FBGrabber `
  --windowed `
  --add-data "app/styles.qss;app" `
  --icon app\\assets\\icon.ico `
  app\main.py

# Optional single-file build (slower startup):
# pyinstaller --onefile --windowed --name FBGrabber --add-data "app/styles.qss;app" app\main.py
```

The executable will be at `dist/FBGrabber/FBGrabber.exe` (or `dist/FBGrabber.exe` with `--onefile`).

#### macOS (.app and .dmg)
```bash
python -m pip install pyinstaller
pyinstaller --noconfirm \
  --name FBGrabber \
  --windowed \
  --add-data "app/styles.qss:app" \
  --icon app/assets/icon.icns \
  app/main.py

# Create DMG
hdiutil create -volname "FBGrabber" -srcfolder "dist/FBGrabber.app" -ov -format UDZO "dist/FBGrabber.dmg"
```

Note: For distribution outside your machine, consider codesigning and notarization.

#### Debian/Ubuntu (.deb)
Build the app first:
```bash
python -m pip install pyinstaller
pyinstaller --noconfirm \
  --name fbgrabber \
  --windowed \
  --add-data "app/styles.qss:app" \
  app/main.py
```

Quick .deb using dpkg-deb:
```bash
APP=fbgrabber; VER=0.1.0; ARCH=amd64
mkdir -p pkg/DEBIAN pkg/opt/$APP pkg/usr/bin pkg/usr/share/applications
cat > pkg/DEBIAN/control <<EOF
Package: $APP
Version: $VER
Section: utils
Priority: optional
Architecture: $ARCH
Maintainer: You <you@example.com>
Description: FBGrabber - Facebook video downloader
EOF
cp -r dist/fbgrabber/* pkg/opt/$APP/
printf '#!/bin/sh\nexec /opt/%s/%s "$@"\n' "$APP" "fbgrabber" > pkg/usr/bin/$APP
chmod +x pkg/usr/bin/$APP
cat > pkg/usr/share/applications/$APP.desktop <<EOF
[Desktop Entry]
Type=Application
Name=FBGrabber
Exec=$APP
Categories=AudioVideo;Network;
EOF
dpkg-deb --build pkg "dist/${APP}_${VER}_${ARCH}.deb"
```

Alternative packagers: Nuitka (smaller/faster), Briefcase (native installers), or fpm (simpler multi‑format packaging).

### Notes
- YT‑DLP handles Facebook video extraction. If a video requires login, provide a cookies file via Settings.
- Respect the content provider's Terms of Service and copyright laws in your jurisdiction.


