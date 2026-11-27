#!/usr/bin/env python3
"""Sync all base.md Overviews for modules already present in Oracle.

    python script/database/module/overview/sync-overview-module-all.py --lang vi
    python script/database/module/overview/sync-overview-module-all.py --lang vi --apply
"""

from _overview_sync import entrypoint


if __name__ == "__main__":
    raise SystemExit(entrypoint(single=False))
