"""Startskript für PyInstaller (wird zu Briefpapier.exe)."""

import sys

from briefpapier.agent import main

if __name__ == "__main__":
    sys.exit(main())
