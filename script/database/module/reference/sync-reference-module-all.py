#!/usr/bin/env python3
"""Sync references.yml for all modules already present in Oracle.

    python script/database/module/reference/sync-reference-module-all.py --lang vi
    python script/database/module/reference/sync-reference-module-all.py --lang vi --apply
"""

from _reference_sync import entrypoint


if __name__ == "__main__":
    raise SystemExit(entrypoint(single=False))
