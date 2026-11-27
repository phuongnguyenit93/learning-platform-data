#!/usr/bin/env python3
"""Read-only Google Sheets client using Application Default Credentials (ADC).

Used by convert-google-sheet-to-knowledge.py and callable on its own:
    python script/temp/reading-google-sheet.py --file-url "https://docs.google.com/spreadsheets/d/.../edit#gid=123" --range "A1:C5"

Google Sheets API must be enabled for the credential's Google Cloud project.
The authenticated account/service account needs access to the spreadsheet.
Dependencies: google-auth and google-api-python-client.
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
from urllib.parse import parse_qs, urlparse


READONLY_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
_SPREADSHEET_ID = re.compile(r"[A-Za-z0-9_-]{15,}\Z")
_GID = re.compile(r"[0-9]+\Z")


class SheetsReaderError(ValueError):
    """Invalid Sheet identity, configuration, or read-only access."""


def parse_sheet_url(url: str) -> tuple[str, str | None]:
    """Return (spreadsheet ID, optional gid) from an official Sheets URL."""
    if not isinstance(url, str):
        raise SheetsReaderError("Google Sheets URL must be a string")
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or (parsed.hostname or "").lower() != "docs.google.com":
        raise SheetsReaderError("Expected an HTTPS docs.google.com/spreadsheets URL")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise SheetsReaderError("Unexpected credentials or port in Sheets URL")
    segments = parsed.path.strip("/").split("/")
    if len(segments) < 3 or segments[:2] != ["spreadsheets", "d"] or (
        not _SPREADSHEET_ID.fullmatch(segments[2])
    ) or (len(segments) > 3 and segments[3] not in ("edit", "view", "preview", "copy")):
        raise SheetsReaderError("Invalid Google Sheets spreadsheet ID or URL path")
    if len(segments) > 4:
        raise SheetsReaderError("Unexpected Google Sheets URL path")

    query = parse_qs(parsed.query, keep_blank_values=True)
    fragment = parse_qs(parsed.fragment.lstrip("#"), keep_blank_values=True)
    candidates = query.get("gid", []) + fragment.get("gid", [])
    if any(not _GID.fullmatch(str(value)) for value in candidates):
        raise SheetsReaderError("Invalid gid in Google Sheets URL")
    if len(set(candidates)) > 1:
        raise SheetsReaderError("Conflicting gids in Google Sheets URL")
    return segments[2], candidates[0] if candidates else None


def resolve_gid(explicit_gid: str | int | None, url_gid: str | None) -> str:
    """Require exactly one well-formed tab ID, allowing matching duplicates."""
    value = str(explicit_gid).strip() if explicit_gid is not None else ""
    if value and not _GID.fullmatch(value):
        raise SheetsReaderError("--sheet-id must be a non-negative numeric gid")
    if value and url_gid and int(value) != int(url_gid):
        raise SheetsReaderError("--sheet-id differs from gid in the URL")
    gid = value or url_gid
    if gid is None or gid == "":
        raise SheetsReaderError("No tab gid specified: supply --sheet-id or URL #gid=...")
    return str(int(gid))


def prefer_ipv4() -> None:
    """Prefer IPv4 DNS results for environments where IPv6 is unreliable."""
    original = socket.getaddrinfo
    if getattr(original, "_sheets_ipv4_preference", False):
        return

    def ipv4_first(*args, **kwargs):
        addresses = original(*args, **kwargs)
        return sorted(addresses, key=lambda item: item[0] != socket.AF_INET)

    ipv4_first._sheets_ipv4_preference = True
    socket.getaddrinfo = ipv4_first


def build_sheets_client():
    """Create a Sheets v4 client; ADC may be user or service-account credentials."""
    try:
        import google.auth
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise SheetsReaderError(
            "Missing Python packages: pip install google-auth google-api-python-client"
        ) from exc

    try:
        credentials, _project_id = google.auth.default(scopes=[READONLY_SCOPE])
        return build("sheets", "v4", credentials=credentials, cache_discovery=False)
    except Exception as exc:
        raise SheetsReaderError(
            "Cannot initialize Google Sheets API with ADC. Configure "
            "GOOGLE_APPLICATION_CREDENTIALS or gcloud auth application-default login, "
            "enable Sheets API and grant spreadsheet access."
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file-url", required=True, help="Google Sheets URL")
    parser.add_argument("--sheet-id", help="Numeric gid, or leave out when URL has gid")
    parser.add_argument("--range", dest="cell_range", default="A1:C5",
                        help="Read-only A1 notation within the selected tab")
    parser.add_argument("--ipv4", action="store_true", help="Prefer IPv4 DNS entries")
    args = parser.parse_args()
    try:
        spreadsheet_id, url_gid = parse_sheet_url(args.file_url)
        gid = resolve_gid(args.sheet_id, url_gid)
        if not re.fullmatch(r"[A-Za-z]{1,3}[1-9][0-9]*(?::[A-Za-z]{1,3}[1-9][0-9]*)?", args.cell_range):
            raise SheetsReaderError("Invalid --range; use an A1 range such as A1:C5")
        if args.ipv4:
            prefer_ipv4()
        client = build_sheets_client()
        metadata = client.spreadsheets().get(
            spreadsheetId=spreadsheet_id,
            fields="sheets(properties(sheetId,title))",
        ).execute()
        tab = next(
            (item["properties"]["title"] for item in metadata.get("sheets", [])
             if str(item.get("properties", {}).get("sheetId")) == gid),
            None,
        )
        if tab is None:
            raise SheetsReaderError(f"Tab gid={gid} not found")
        safe_title = "'" + tab.replace("'", "''") + "'"
        response = client.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{safe_title}!{args.cell_range}",
            valueRenderOption="FORMULA",
        ).execute()
        print(json.dumps({
            "tab": tab, "gid": gid, "range": args.cell_range,
            "values": response.get("values", []),
        }, ensure_ascii=False, indent=2))
        return 0
    except (SheetsReaderError, OSError, ValueError) as exc:
        print(f"BLOCKER: SHEETS_READ: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
