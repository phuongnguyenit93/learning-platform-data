#!/usr/bin/env python3
"""STEP 2 NEW: import explicitly selected Vietnamese Reference content."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _scoped_import import main as _main


def main(argv=None):
    return _main("reference", argv)

if __name__ == "__main__":
    raise SystemExit(main())
