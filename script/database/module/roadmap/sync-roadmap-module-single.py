#!/usr/bin/env python3
"""Sync one module's roadmap.yml, matched by SERVICE_NAME to Oracle MODULE.

    python script/database/module/roadmap/sync-roadmap-module-single.py \
        --module module/infrastructure/cloud/architecture --lang vi
    python script/database/module/roadmap/sync-roadmap-module-single.py \
        --module module/infrastructure/cloud/architecture --apply
"""

from _roadmap_sync import entrypoint


if __name__ == "__main__":
    raise SystemExit(entrypoint(single=True))
