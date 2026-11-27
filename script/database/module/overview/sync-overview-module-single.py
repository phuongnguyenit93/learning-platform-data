#!/usr/bin/env python3
"""Sync base.md for one repository module already present in Oracle.

    python script/database/module/overview/sync-overview-module-single.py \
        --module module/infrastructure/cloud/architecture --lang vi
    python script/database/module/overview/sync-overview-module-single.py \
        --module module/infrastructure/cloud/architecture --apply
"""

from _overview_sync import entrypoint


if __name__ == "__main__":
    raise SystemExit(entrypoint(single=True))
