# File Organizer GUI Prototype

Prototype GUI for converting `file_organizer_v1.5.py` into a desktop app.

Running (dev):

1. Create and activate a Python 3.11+ venv (recommended).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python gui_app.py
```

Packaging to macOS `.app` (Apple Silicon)

This project uses a PySide6 prototype. To build a .app you can use `py2app` or `PyInstaller`.

Example with `py2app` (suggested, run on macOS on target arch):

```bash
pip install py2app
python setup_py2app.py py2app
```

Notes:
- For a fully native Cocoa UI consider rewriting the UI using PyObjC or a native Swift app and calling the Python core as a helper process.
- Code signing and notarization are required to distribute an unsigned .app on macOS. See Apple's docs.

Building a standalone `.app` with py2app

1. Ensure you run the build on the target architecture (Apple Silicon) Python. The bundled app will include a Python runtime, so the build's architecture matters.
2. Use the provided build script:

```bash
./build_app.sh
```

3. After build, the `.app` will be in `dist/`. You should code sign and notarize for distribution; unsigned apps may be blocked by Gatekeeper.

Notes on fully native binaries
- py2app bundles Python and the PySide6 Qt libraries; the result is a standalone app but still Python-based under the hood.
- If you require a non-Python native binary, consider reimplementing the UI in Swift (Xcode) and invoking the `organizer_core` logic via a helper process or rewriting the core in Swift/Objective-C.

Photos integration

- This project includes optional Photos export functionality using `osxphotos`.
- To enable: install `osxphotos` in the build environment (`pip install osxphotos`) or install from `requirements.txt`.
- The GUI exposes "Export from Photos" which will export originals into a timestamped session folder. There is an option to "Delete from Photos after successful export" but deletion is a best-effort operation and requires explicit user permissions — use with caution.
- Grant Photos access/automation permissions when prompted by macOS. Test on a small album first.

Native macOS UI (PyObjC)

- The project now includes a native Cocoa UI implemented with PyObjC: `pyobjc_app.py`.
- This keeps the app Python-based but provides a native macOS look-and-feel and allows packaging via `py2app`.
- To run the native UI during development:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python pyobjc_app.py
```

- Packaging: use the existing `build_app.sh`/`setup_py2app.py`. Ensure `pyobjc` and `pyobjc-framework-Cocoa` are installed in the build venv.

Code signing and notarization (optional automation)

The `build_app.sh` script supports optional automatic code-signing and notarization when you provide the required environment variables. This is disabled by default.

- To sign the app locally, export a valid Developer ID identity and run the script. Example:

```bash
export SIGN_IDENTITY="Developer ID Application: Example Co (TEAMID)"
./build_app.sh
```

- To submit the app for notarization (Apple ID must have an app-specific password):

```bash
export NOTARIZE_USERNAME="apple.id@example.com"
export NOTARIZE_PASSWORD="<app-specific-password>"
export BUNDLE_ID="com.example.fileorganizer"
./build_app.sh
```

Notes:
- Notarization requires zipping the `.app` and submitting via `xcrun altool`. The script will create a zip and submit it if the variables above are set.
- The script will attempt to codesign embedded libraries too. Depending on your identity and entitlements you may need to adjust `entitlements.plist` produced by the script.
- For distribution on Gatekeeper, a signed and notarized app is recommended. The script provides convenience automation but you must supply valid Apple credentials and a Developer ID.

