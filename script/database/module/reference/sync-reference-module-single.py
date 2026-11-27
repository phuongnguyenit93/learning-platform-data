#!/usr/bin/env python3
"""Sync references.yml for one repository module already present in Oracle.

    python script/database/module/reference/sync-reference-module-single.py \
        --module module/infrastructure/cloud/architecture --lang vi
    python script/database/module/reference/sync-reference-module-single.py \
        --module module/infrastructure/cloud/architecture --apply
"""

from _reference_sync import entrypoint


if __name__ == "__main__":
    raise SystemExit(entrypoint(single=True))
