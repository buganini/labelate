"""Build a standalone desktop package with PyInstaller.

    python scripts/build_package.py [--codesign-identity "Developer ID Application: …"] [--no-dmg]

On macOS the identity is asked interactively when omitted; an empty answer builds
an ad-hoc signed app. Printer drivers are bundled when installed, e.g. via
`pip install -e '.[printers]'`.
"""
import argparse
import importlib.util
import platform
import plistlib
import subprocess
import os
import itertools
import glob
import sys
from pathlib import Path

PKG_BASE = os.fspath(Path(__file__).resolve().parents[1])
sys.path.insert(0, PKG_BASE)
os.chdir(PKG_BASE)

import PyInstaller.__main__
from scripts.third_party_licenses import installed_closure, render
from scripts import fetch_fonts

from labelate.version import __version__

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("--codesign-identity", help="macOS Developer ID identity; empty for ad-hoc signing")
parser.add_argument("--no-dmg", action="store_true", help="skip create-dmg on macOS")
args = parser.parse_args()

notices = Path(PKG_BASE, ".build/THIRD_PARTY_LICENSES.txt")
notices.parent.mkdir(parents=True, exist_ok=True)
fonts = fetch_fonts.fetch()


def libusb_entry():
    """pyusb loads libusb from the build machine and PyInstaller bundles it (LGPL-2.1)."""
    try:
        import usb.backend.libusb1
        backend = usb.backend.libusb1.get_backend()
    except ImportError:
        return None
    if backend is None:
        return None
    library = Path(backend.lib._name).resolve()
    root = next((parent for parent in library.parents if (parent / "COPYING").is_file()), None)
    return {"name": "libusb-1.0", "version": root.name if root else library.name, "license": "LGPL-2.1-or-later",
            "homepage": "https://github.com/libusb/libusb",
            "files": [("COPYING", (root / "COPYING").read_text(encoding="utf-8"))] if root else []}


libusb = libusb_entry()
notices.write_text(render([*installed_closure("labelate"), *fetch_fonts.notices(), *([libusb] if libusb else [])]),
                   encoding="utf-8")

BUNDLE_ID = "io.github.buganini.labelate"
# printing.module() imports drivers by name at runtime, which PyInstaller cannot see.
# Collect each installed driver whole (submodules, data, metadata for the window title).
DRIVERS = [name for name in ("brother_ql", "pyniim", "pytsc") if importlib.util.find_spec(name)]
print("Bundling printer drivers:", ", ".join(DRIVERS) or "none")
driver_args = [arg for name in DRIVERS for arg in ("--collect-all", name)]
if "pyniim" in DRIVERS:
    # bleak picks its platform backend inside functions; collect them explicitly.
    driver_args += ["--collect-submodules", "bleak", "--copy-metadata", "bleak"]

# macOS
## brew install create-dmg
## xcrun notarytool store-credentials notarytool-creds  --apple-id your@apple.id --team-id "XXXXXXXXXX" --password "xxxx-xxxx-xxxx-xxxx"

create_dmg = False
codesign_identity = None

pyinstaller_args = []
create_dmg_args = []
if platform.system() == "Darwin":
    pyinstaller_args.extend(["-i", "resources/icon.icns", "--osx-bundle-identifier", BUNDLE_ID])
    codesign_identity = args.codesign_identity
    if codesign_identity is None and sys.stdin.isatty():
        subprocess.run(["security", "find-identity", "-v", "-p", "codesigning"])
        codesign_identity = input('Enter the codesign identity "Developer ID Application: XXXXXX (XXXXXXXXXX)" (leave empty for no signing): ')
    codesign_identity = (codesign_identity or "").strip()
    if codesign_identity:
        create_dmg_args.extend(["--codesign", codesign_identity])
        create_dmg_args.extend(["--notarize", "notarytool-creds"])
    create_dmg = not args.no_dmg
else:
    pyinstaller_args.extend(["-i", "resources/icon.ico"])

PyInstaller.__main__.run([
    os.path.join(PKG_BASE, "labelate", "__main__.py"),
    "--name", "Labelate",
    "--onedir",
    "--noconfirm",
    "--windowed",
    "--add-data", f"{os.path.join(PKG_BASE, 'LICENSE')}{os.pathsep}.",
    "--add-data", f"{notices}{os.pathsep}.",
    "--add-data", f"{os.path.join(PKG_BASE, 'labelate', 'icon.svg')}{os.pathsep}labelate",
    *(arg for font in fonts for arg in ("--add-data", f"{font}{os.pathsep}labelate/fonts")),
    *driver_args,
    *pyinstaller_args,
])

if platform.system() == "Darwin":
    # macOS terminates apps that touch Bluetooth without a usage description (Niim over BLE).
    info_path = Path("dist/Labelate.app/Contents/Info.plist")
    info = plistlib.loads(info_path.read_bytes())
    info.update(
        CFBundleShortVersionString=__version__,
        CFBundleVersion=__version__,
        NSBluetoothAlwaysUsageDescription="Labelate uses Bluetooth to find and print to Niimbot label printers.",
        NSHumanReadableCopyright="Labelate is MIT licensed; this app bundles GPL and LGPL components, see THIRD_PARTY_LICENSES.txt.",
    )
    info_path.write_bytes(plistlib.dumps(info))
    if not codesign_identity:
        # Editing Info.plist invalidates PyInstaller's ad-hoc signature; re-seal the bundle.
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", "dist/Labelate.app"], check=True)

if codesign_identity:
    for path in itertools.chain(
        glob.glob("dist/Labelate.app/**/*.so", recursive=True),
        glob.glob("dist/Labelate.app/**/*.dylib", recursive=True),
        ["dist/Labelate.app"],
    ):
        print("codesign", path)
        subprocess.run(["codesign",
            "--sign", codesign_identity,
            "--entitlements", "resources/entitlements.plist",
            "--timestamp",
            "--deep",
            str(path),
            "--force",
            "--options", "runtime",
        ], check=True)

if create_dmg:
    if os.path.exists("Labelate.dmg"):
        os.unlink("Labelate.dmg")
    subprocess.run([
        "create-dmg",
        "--volname", "Labelate",
        "--volicon", "resources/icon.icns",
        "--app-drop-link", "0", "0",
        *create_dmg_args,
        "Labelate.dmg", "dist/Labelate.app",
    ])
    if codesign_identity:
        subprocess.run(["spctl", "-a", "-t", "open", "--context", "context:primary-signature", "-v", "Labelate.dmg"])
