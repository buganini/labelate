"""Launch the PySide6 desktop app with python -m labelate or python labelate."""
if not __package__:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from labelate.app import main

if __name__ == '__main__':
    main()
