#!/usr/bin/env python3
"""Shared Oracle connection helper for database scripts.

Running this file performs a connection-only health check:
open a connection, then close it. No SQL, queries, commits, or imports.

    python script/database/connect-oracle-db.py
    python script/database/connect-oracle-db.py --env-file .env.oracle-overview
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = REPO_ROOT / ".env.oracle-overview"
SCHEMA_RE = re.compile(r"[A-Za-z][A-Za-z0-9_$#]*\Z")


class OracleConnectionError(Exception):
    """An expected connection configuration problem safe to display."""


def load_env_file(path: Path, *, required: bool = False) -> None:
    """Load simple KEY=VALUE variables; the process environment wins."""
    if not path.is_file():
        if required:
            raise OracleConnectionError(f"Environment file not found: {path}")
        return
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise OracleConnectionError(f"Invalid KEY=VALUE at {path}:{line_number}")
        key, value = (part.strip() for part in line.split("=", 1))
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise OracleConnectionError(f"Invalid variable name at {path}:{line_number}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def config_from_env() -> dict[str, str]:
    """Validate required Oracle settings without exposing their values."""
    required = ("ORACLE_USER", "ORACLE_PASSWORD", "ORACLE_DSN")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise OracleConnectionError(
            "Missing " + ", ".join(missing)
            + f". Configure environment variables or {DEFAULT_ENV_FILE.name}."
        )
    schema = os.environ.get("ORACLE_SCHEMA", "").strip()
    if schema and not SCHEMA_RE.fullmatch(schema):
        raise OracleConnectionError("ORACLE_SCHEMA must be a simple Oracle identifier")
    return {
        "user": os.environ["ORACLE_USER"],
        "password": os.environ["ORACLE_PASSWORD"],
        "dsn": os.environ["ORACLE_DSN"],
        "schema": schema.upper(),
    }


def connect(config: dict[str, str]):
    """Return (oracledb driver, open connection); caller must close it."""
    try:
        import oracledb
    except ImportError as exc:
        raise OracleConnectionError(
            "Python driver missing. Install with: python -m pip install oracledb"
        ) from exc
    # Thin mode supports Oracle Autonomous Database TLS connections.
    connection = oracledb.connect(
        user=config["user"], password=config["password"], dsn=config["dsn"]
    )
    return oracledb, connection


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    args = parser.parse_args(argv)
    if argv is None:
        import sys
        raw_args = sys.argv[1:]
    else:
        raw_args = argv
    explicitly_provided = any(
        item == "--env-file" or item.startswith("--env-file=")
        for item in raw_args
    )
    try:
        load_env_file(args.env_file, required=explicitly_provided)
        config = config_from_env()
        _, connection = connect(config)
    except OracleConnectionError as exc:
        print(f"CONNECT_FAILED: {exc}")
        return 1
    except Exception as exc:
        # Never print DSN, credentials, SQL bind values, or raw driver messages.
        print(f"CONNECT_FAILED: {type(exc).__name__}")
        return 1

    try:
        print("CONNECT_OK: Oracle connection established; no SQL executed.")
    finally:
        connection.close()
    print("DISCONNECT_OK: Oracle connection closed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
