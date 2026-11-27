#!/usr/bin/env python3
"""Create Oracle missing Roadmap reports (read-only).

    python script/database/module/roadmap/check_missing_roadmap.py

Reports: module/database/roadmap/report/missing-roadmap-*.yml
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _missing_data_report import entrypoint  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(entrypoint("roadmap"))
