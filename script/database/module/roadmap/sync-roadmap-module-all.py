#!/usr/bin/env python3
"""Sync roadmap.yml for every repository module that already exists in Oracle.

    python script/database/module/roadmap/sync-roadmap-module-all.py --lang vi
    python script/database/module/roadmap/sync-roadmap-module-all.py --lang vi --apply
"""

from _roadmap_sync import entrypoint


if __name__ == "__main__":
    raise SystemExit(entrypoint(single=False))
