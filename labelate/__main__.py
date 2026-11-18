"""Launch the PySide6 desktop app with python -m labelate or python labelate."""
import sys

if not __package__ and not getattr(sys, 'frozen', False):
    # `python labelate` puts this directory first on sys.path, where labelate/platform.py
    # would shadow the standard library `platform` (imported by bleak, pyniim, ...).
    # Import labelate as a package from its parent directory instead. PyInstaller builds
    # run this file as their entry script too, but their sys.path must stay untouched.
    from pathlib import Path
    here = Path(__file__).resolve().parent
    sys.path[:] = [entry for entry in sys.path if Path(entry or '.').resolve() != here]
    sys.path.insert(0, str(here.parent))

from labelate.app import main

if __name__ == '__main__':
    main()
