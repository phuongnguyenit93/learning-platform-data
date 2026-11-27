#!/usr/bin/env python3
"""List modules whose SERVICE_NAME_DESCRIBE is empty in module-info.json.

Read-only with respect to module data. Scans all module-info.json files under
java-learning/module and writes a deterministic YAML report.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = Path("script/module-generate/status-report/missing-service-name-describe.yml")


def read_value(metadata: dict, key: str, path: Path) -> object:
    """Read the VALUE member of a module-info.json metadata field."""
    field = metadata.get(key)
    if field is None:
        return None
    if not isinstance(field, dict):
        raise ValueError(f"{path}: {key} must be an object containing VALUE")
    return field.get("VALUE")


def find_missing_descriptions(root: Path) -> list[dict[str, str]]:
    modules_root = root / "learning-platform-data" / "module"
    if not modules_root.is_dir():
        raise FileNotFoundError(f"Module directory not found: {modules_root}")

    missing: list[dict[str, str]] = []
    for info_path in sorted(modules_root.rglob("module-info.json")):
        metadata = json.loads(info_path.read_text(encoding="utf-8-sig"))
        if not isinstance(metadata, dict):
            raise ValueError(f"{info_path}: expected a JSON object")

        service = read_value(metadata, "SERVICE_NAME", info_path)
        if not isinstance(service, str) or not service.strip():
            raise ValueError(f"{info_path}: SERVICE_NAME.VALUE is missing or empty")

        description = read_value(metadata, "SERVICE_NAME_DESCRIBE", info_path)
        if description is not None and not isinstance(description, str):
            raise ValueError(
                f"{info_path}: SERVICE_NAME_DESCRIBE.VALUE must be a string or null"
            )
        if description is None or not description.strip():
            missing.append({
                "location": info_path.parent.relative_to(root).as_posix(),
                "SERVICE_NAME": service,
            })

    return missing


def write_report(output: Path, modules: list[dict[str, str]]) -> None:
    """Write via an adjacent temporary file so interrupted runs don't truncate YAML."""
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=".missing-service-name-describe-", suffix=".tmp", dir=output.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
            yaml.safe_dump(
                {"missingServiceNameDescribe": modules},
                file,
                allow_unicode=True,
                sort_keys=False,
                width=120,
            )
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, output)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=REPO_ROOT,
        help="java-learning root (default: determined from this script)",
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help="YAML output, relative to the java-learning root by default",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output

    missing = find_missing_descriptions(root)
    write_report(output, missing)
    print(f"REPORT_WRITTEN {output}")
    print(f"MODULES_MISSING_SERVICE_NAME_DESCRIBE {len(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
