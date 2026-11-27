#!/usr/bin/env python3
"""Preview or import Menu/Knowledge for all modules (default dry-run)."""

from _knowledge_menu_sync import entrypoint


if __name__ == "__main__":
    raise SystemExit(entrypoint(single=False))
