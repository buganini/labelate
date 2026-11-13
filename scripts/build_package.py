"""Build a standalone desktop package with PyInstaller."""
import platform
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

# macOS
## brew install create-dmg
## xcrun notarytool store-credentials notarytool-creds  --apple-id your@apple.id --team-id "XXXXXXXXXX" --password "xxxx-xxxx-xxxx-xxxx"

create_dmg = False
codesign_identity = None

pyinstaller_args = []
create_dmg_args = []
if platform.system() == "Darwin":
    pyinstaller_args.extend(["-i", "resources/icon.icns"])
    subprocess.run(["security", "find-identity", "-v", "-p", "codesigning"])
    codesign_identity = input('Enter the codesign identity "Developer ID Application: XXXXXX (XXXXXXXXXX)" (leave empty for no signing): ').strip()
    if codesign_identity:
        create_dmg_args.extend(["--codesign", codesign_identity])
        create_dmg_args.extend(["--notarize", "notarytool-creds"])
    create_dmg = True
else:
    pyinstaller_args.extend(["-i", "resources/icon.ico"])

PyInstaller.__main__.run([
    os.path.join(PKG_BASE, "labelate", "__main__.py"),
    "--name", "Labelate",
    "--onedir",
    "--noconfirm",
    "--windowed",
    *pyinstaller_args,
])

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
        ])

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
