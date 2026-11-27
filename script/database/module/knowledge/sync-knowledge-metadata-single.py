#!/usr/bin/env python3
"""Sync five optional Knowledge metadata fields for one module, dry-run default."""

from _knowledge_metadata_sync import entrypoint


if __name__ == "__main__":
    raise SystemExit(entrypoint(single=True))
