#!/usr/bin/env python3
"""One-way, replace-existing Google Sheet -> module content migration.

Source fields:
  B17: Base Markdown; L3: Reference YAML; F3:H17: Roadmap table (max 9
  contiguous milestones, never read lower Knowledge rows); A18:N..., O, AC:
  Knowledge; Special Note heading in row 2, value in row 3.
Target files:
  content/base/<lang>/base.md
  content/reference/<lang>/references.yml
  content/roadmap/<lang>/roadmap.yml
  content/knowledge/<lang>/ (recreated from the source, including lesson files)
  module-info.json.SPECIAL_NOTE.VALUE (replace even if the new note is empty)

This is a disposable synchronization/migration tool, not a merging importer.
--apply replaces only these targets and removes related legacy Knowledge
artifacts and the old readme/docs/<lang>/BASE.md file. Existing data is
transactionally staged and rolled back if publishing fails. Other languages,
Quiz/Interview/Case Study, Java code and metadata fields are not touched.
No Google Sheet writes, Gradle, Oracle or CURRENT_STEP changes.

Usage:
  python script/temp/convert-google-sheet-to-knowledge.py --file-url URL --lang vi --ipv4
  python script/temp/convert-google-sheet-to-knowledge.py --file-url URL --lang vi --ipv4 --apply

--lang (or --language) defaults to vi and writes inside content/knowledge/<lang>/.
Dry-run is the default and never alters local files.

Dependencies: PyYAML, google-auth, google-api-python-client.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile
import unicodedata
from urllib.parse import urlsplit

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "script" / "module" / "step3"))
sys.path.insert(0, str(REPO / "script" / "module" / "step4"))
from generate_menu_detail import (  # noqa: E402
    RESERVED_STEMS,
    SLUG_RE,
    Step3Error,
    StrictLoader,
    dump_yaml,
    service_name,
    write_new,
)
import generate_menu_detail as menu_detail_generator  # noqa: E402
from generate_menu_detail import (  # noqa: E402
    DIFFICULTIES,
    LiteralText,
)

SHEET_FILENAME_RE = re.compile(r"(?i)[a-z][a-z0-9]*\.md\Z")
OLD_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*-[0-9]{3}\Z")
ROADMAP_MAX = 9  # STEP 2 NEW + Oracle importer both require <10 milestones.
ROADMAP_FIRST_ROW = 3
ROADMAP_LAST_ROW = 17  # Knowledge section starts at row 18; do not read past this.
LEGACY_KNOWLEDGE_FILES = frozenset({
    "note.yml", "menu.yml", "menu-level-1-slug.yml", "menu-detail-status.yml",
})
LEGACY_CHAPTER_DIR = re.compile(r"[1-9][0-9]*\.[a-z][a-z0-9-]*\Z")


def reader_module():
    """Load the read-only Google Sheets helper from the same script directory."""
    source = Path(__file__).with_name("reading-google-sheet.py")
    spec = importlib.util.spec_from_file_location("reading_google_sheet_cli", source)
    if spec is None or spec.loader is None:
        raise Step3Error(f"Cannot load Sheets reader: {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def text_at(row: list, index: int, *, trim: bool = True) -> str:
    value = row[index] if index < len(row) else ""
    if value is None:
        return ""
    value = str(value)
    return value.strip() if trim else value


def old_filename_to_slug(filename: str) -> str:
    stem = filename[:-3]
    # Same camel/Pascal -> kebab mapping used in the old Groovy importer.
    stem = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", stem)
    stem = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", stem)
    return stem.lower()


def module_from_location(repo: Path, raw: str) -> Path:
    if not raw or "\\" in raw or raw.startswith("/") or raw.endswith("/"):
        raise Step3Error(f"Unsafe I3 module location: {raw!r}")
    parts = raw.split("/")
    if parts[0] != "module" or any(part in ("", ".", "..") for part in parts):
        raise Step3Error(f"Unsafe I3 module location: {raw!r}")
    if PurePosixPath(raw).as_posix() != raw:
        raise Step3Error(f"I3 must be a canonical repository-relative path: {raw!r}")
    modules_root = (repo / "learning-platform-data" / "module").resolve(strict=True)
    module = modules_root.joinpath(*parts[1:]).resolve(strict=True)
    if not module.is_dir() or not module.is_relative_to(modules_root):
        raise Step3Error("I3 does not resolve to a module inside this repository.")
    if not (module / "module-info.json").is_file():
        raise Step3Error(f"Missing module-info.json in module: {module}")
    return module


def special_note_update_plan(module: Path, sheet_note: str) -> tuple[Path, bytes, bytes]:
    """Build a full replacement of module-info with only SPECIAL_NOTE.VALUE changed."""
    path = module / "module-info.json"
    if path.is_symlink() or not path.is_file():
        raise Step3Error(f"Unsafe or missing module-info.json: {path}")
    before = path.read_bytes()
    try:
        info = json.loads(before.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise Step3Error(f"Invalid module-info.json: {path}") from exc
    if type(info) is not dict:
        raise Step3Error("module-info.json must be a JSON object")
    service = info.get("SERVICE_NAME")
    if type(service) is not dict or service.get("VALUE") is None:
        raise Step3Error("module-info.json must contain SERVICE_NAME.VALUE")
    note = info.get("SPECIAL_NOTE")
    if note is None:
        note = {
            "DESCRIPTION": "Special Note use when generate content",
            "TYPE": "string",
            "VALUE": "",
        }
        info["SPECIAL_NOTE"] = note
    else:
        if type(note) is not dict or type(note.get("VALUE")) is not str or (
            note.get("TYPE") not in (None, "string")
        ):
            raise Step3Error("module-info.json SPECIAL_NOTE must be a string VALUE object")
    if note["VALUE"] == sheet_note:
        return path, before, before
    note["VALUE"] = sheet_note
    linebreak = "\r\n" if b"\r\n" in before else "\n"
    output = json.dumps(info, indent=2, ensure_ascii=False)
    if before.endswith((b"\n", b"\r")):
        output += "\n"
    prefix = b"\xef\xbb\xbf" if before.startswith(b"\xef\xbb\xbf") else b""
    return path, before, prefix + output.replace("\n", linebreak).encode("utf-8")


def slugify_title(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title.replace("đ", "d").replace("Đ", "D"))
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    if not ascii_text:
        raise Step3Error(f"Cannot generate ASCII roadmap id from title: {title!r}")
    return ascii_text


def parse_roadmap(rows: list[list]) -> dict:
    """Only F3:H17; stop at first fully blank row, reject gaps and >9 milestones."""
    milestones = []
    seen_ids: set[str] = set()
    ended = False
    for row_number in range(ROADMAP_FIRST_ROW, ROADMAP_LAST_ROW + 1):
        row = rows[row_number - ROADMAP_FIRST_ROW] if row_number - ROADMAP_FIRST_ROW < len(rows) else []
        fields = [text_at(row, i, trim=False) for i in range(3)]
        if not any(field.strip() for field in fields):
            ended = True
            continue
        if ended:
            raise Step3Error(f"Roadmap F{row_number}:H{row_number} has data after an empty row")
        title, purpose, objectives_cell = (field.strip() for field in fields)
        if any(not field or field.startswith("=") or "\x00" in field
               for field in (title, purpose, objectives_cell)):
            raise Step3Error(f"Invalid Roadmap milestone fields at F{row_number}:H{row_number}")
        objectives = [line.strip() for line in objectives_cell.splitlines() if line.strip()]
        if not objectives or any(line.startswith("=") for line in objectives):
            raise Step3Error(f"Invalid Roadmap objectives at H{row_number}")
        if (len(title) > 300 or len(purpose) > 1000 or
                len("\n".join(objectives)) > 2000):
            raise Step3Error(f"Roadmap milestone exceeds STEP 2 limits at row {row_number}")
        milestone_id = slugify_title(title)
        if milestone_id in seen_ids:
            raise Step3Error(f"Duplicate Roadmap title/id: {title}")
        seen_ids.add(milestone_id)
        milestones.append({"id": milestone_id, "title": title,
                           "purpose": purpose, "objectives": objectives})
        if len(milestones) > ROADMAP_MAX:
            raise Step3Error(f"Roadmap has more than {ROADMAP_MAX} milestones; STEP 2 NEW requires <10")
    if not milestones:
        raise Step3Error("Roadmap F3:H17 is empty")
    return {"roadmap": milestones}


def parse_references(source: str) -> dict:
    if not source.strip() or source.lstrip().startswith("=") or "\x00" in source:
        raise Step3Error("Missing or formula-valued Reference YAML at L3")
    try:
        document = yaml.load(source, Loader=StrictLoader)
    except (yaml.YAMLError, Step3Error) as exc:
        raise Step3Error(f"Invalid Reference YAML at L3: {exc}") from exc
    if type(document) is not dict or set(document) != {"references"} or (
        type(document["references"]) is not list or not document["references"]
    ):
        raise Step3Error("L3 must contain nonempty references: [] YAML")
    urls = set()
    for n, item in enumerate(document["references"], start=1):
        if type(item) is not dict or not {"title", "url"}.issubset(item) or (
            set(item) - {"title", "url", "description"}
        ):
            raise Step3Error(f"Invalid Reference entry #{n}")
        title, url, desc = item["title"], item["url"], item.get("description")
        if type(title) is not str or not title.strip() or type(url) is not str or (
            not url.startswith("https://") or any(ch.isspace() for ch in url)
        ) or (desc is not None and type(desc) is not str):
            raise Step3Error(f"Invalid Reference fields at entry #{n}")
        try:
            parsed = urlsplit(url)
            valid = bool(parsed.hostname) and parsed.username is None and parsed.password is None
        except ValueError:
            valid = False
        if not valid or url in urls:
            raise Step3Error(f"Invalid/duplicate Reference URL at entry #{n}")
        if (len(title) > 300 or len(url) > 2000 or
                (desc is not None and len(desc) > 1000)):
            raise Step3Error(f"Reference entry #{n} exceeds STEP 2 limits")
        urls.add(url)
    return document


def decode_sheet(tab: dict, repo: Path, lang: str = "vi") -> dict:
    """Validate 1:1 source rows before constructing any output."""
    title = tab["title"]
    front = tab["front"]
    menu_rows = tab["menu_rows"]
    # Optional evidence from a caller that inspected a Sheets cell's
    # userEnteredValue and verified it is literal stringValue, not formulaValue.
    # The normal CLI does not supply this and remains strict.
    verified_literal_equals_cells = tab.get("verified_literal_equals_cells", frozenset())
    # Exact, caller-reviewed legacy filename/slug exceptions. The normal
    # converter remains strict; only callers that verified the original cells
    # may allow a specific (row, filename, slug) triple.
    verified_chapter_slug_exceptions = tab.get(
        "verified_chapter_slug_exceptions", frozenset()
    )

    detail_name = text_at(front[0], 1)
    if not detail_name:
        raise Step3Error("Sheet B1 (detailName) is empty.")
    step = text_at(front[2], 9).upper()
    if step not in ("", "STEP 3", "STEP 4", "STEP 5", "FINAL"):
        raise Step3Error(
            f"Sheet J3 indicates {step!r}. This converter supports STEP 3/4/5/FINAL only."
        )
    location = text_at(front[2], 8)
    module = module_from_location(repo, location)
    if type(lang) is not str or not re.fullmatch(r"[a-z][a-z0-9-]{0,9}\Z", lang):
        raise Step3Error(f"Invalid --lang {lang!r}")
    subject = service_name(module)

    labels = [text_at(front[1], i).casefold() for i in range(29)]
    special_columns = [i for i, label in enumerate(labels) if label == "special note"]
    if len(special_columns) != 1:
        raise Step3Error(
            f"Expected exactly one 'Special Note' heading on row 2, found {len(special_columns)}."
        )
    special_note = text_at(front[2], special_columns[0], trim=False)
    if "\x00" in special_note or special_note.lstrip().startswith("="):
        raise Step3Error("Sheet Special Note is invalid or contains a formula.")
    special_note_update_plan(module, special_note)  # Preflight before any file changes.

    base = tab.get("base_markdown")
    if type(base) is not str or not base.strip() or not base.lstrip().startswith("# "):
        raise Step3Error("B17 Base Markdown must be nonempty and start with an H1")
    if base.lstrip().startswith("=") or "\x00" in base:
        raise Step3Error("B17 Base Markdown contains an invalid value/formula")
    roadmap = parse_roadmap(tab.get("roadmap_rows", []))
    reference_raw = tab.get("reference_yaml", "")
    references = parse_references(reference_raw)

    if text_at(menu_rows[0], 0) != "Khu vực Menu":
        raise Step3Error("Missing 'Khu vực Menu' at A18.")
    if (text_at(menu_rows[1], 0) != "Menu Cấp 1" or
            text_at(menu_rows[1], 1) != "Menu Cấp 2"):
        raise Step3Error("Invalid A19:B19 Menu headers.")

    chapters: list[dict] = []
    imported_child_fields: dict[str, dict[str, str]] = {}
    lesson_rows: set[int] = set()
    chapter_rows: set[int] = set()
    difficulty_cells = tab.get("difficulty_rows", {})
    summary_cells = tab.get("summary_rows", {})
    seen_gap = False
    for row_number, row in enumerate(menu_rows[2:], start=20):
        left = text_at(row, 0)
        middle = text_at(row, 1)
        third = text_at(row, 2, trim=False)
        rest = [text_at(row, i, trim=False) for i in range(3, 14)]

        if not (left or middle or third or any(rest)):
            seen_gap = True
            continue
        if seen_gap:
            raise Step3Error(f"Menu has data after a blank row (row {row_number}).")

        if left and not OLD_ID_RE.fullmatch(left):
            # Parent row: A=chapter title, B=legacy filename, C=base slug.
            slug = third.strip()
            if not SHEET_FILENAME_RE.fullmatch(middle):
                raise Step3Error(f"Missing/invalid chapter filename B{row_number}: {middle!r}")
            if not SLUG_RE.fullmatch(slug) or len(slug) > 80 or slug in RESERVED_STEMS:
                raise Step3Error(f"Invalid chapter slug C{row_number}: {slug!r}")
            canonical = old_filename_to_slug(middle)
            if canonical != slug and (
                row_number, middle, slug
            ) not in verified_chapter_slug_exceptions:
                raise Step3Error(
                    f"B{row_number} filename and C{row_number} slug differ: "
                    f"expected {canonical!r}, found {slug!r}."
                )
            if any(rest):
                raise Step3Error(f"Unexpected authored data on chapter row D{row_number}:N{row_number}.")
            chapters.append({"title": left, "slug": slug, "lessons": [], "bodies": [],
                             "fragments": [], "row": row_number})
            chapter_rows.add(row_number)
        elif middle:
            if not chapters:
                raise Step3Error(f"Lesson B{row_number} appears before the first chapter.")
            if len(chapters[-1]["lessons"]) >= 999:
                raise Step3Error(f"More than 999 lessons in chapter {chapters[-1]['slug']}.")
            expected_id = f"{chapters[-1]['slug']}-{len(chapters[-1]['lessons'])+1:03d}"
            if left and left != expected_id:
                raise Step3Error(
                    f"Existing legacy lesson ID A{row_number}={left!r} differs "
                    f"from STEP_3_NEW ID {expected_id!r}."
                )
            # Preserve every byte of the returned Unicode text: do NOT strip
            # chunks, insert separators, or reserialize Markdown. STEP 4 may
            # span several adjacent cells (C:N) to honor Sheets cell limits.
            fragments = [third, *rest]
            seen_empty = False
            nonempty_fragments = 0
            for index, fragment in enumerate(fragments):
                if not fragment:
                    seen_empty = True
                elif seen_empty:
                    column = "CDEFGHIJKLMN"[index]
                    raise Step3Error(
                        f"Knowledge fragments have a gap before {column}{row_number}."
                    )
                else:
                    nonempty_fragments += 1
            body = "".join(fragments)
            if "\x00" in body:
                raise Step3Error(f"Knowledge contains NUL at row {row_number}.")
            for index, fragment in enumerate(fragments):
                if fragment.startswith("="):
                    column = "CDEFGHIJKLMN"[index]
                    if (row_number, column) not in verified_literal_equals_cells:
                        raise Step3Error(
                            f"Knowledge cell at {column}{row_number} starts with =; "
                            "review possible formulas before migration."
                        )
            chapters[-1]["lessons"].append(middle)
            chapters[-1]["bodies"].append(body)
            chapters[-1]["fragments"].append(nonempty_fragments)
            lesson_rows.add(row_number)
            difficult = str(difficulty_cells.get(row_number, "")).strip()
            summary = str(summary_cells.get(row_number, ""))
            if difficult not in DIFFICULTIES:
                raise Step3Error(
                    f"Invalid Difficulty O{row_number}={difficult!r}; "
                    "expected BASIC/INTERMEDIATE/ADVANCED or blank."
                )
            if not summary.strip():
                summary = ""
            if "\x00" in summary:
                raise Step3Error(f"Summary AC{row_number} contains NUL.")
            imported_child_fields[expected_id] = {
                "difficult": difficult,
                "summary": summary,
            }
        else:
            raise Step3Error(f"Invalid parent/lesson structure at A{row_number}:C{row_number}.")

    # Row-of-chapter AC contains the separate chapter roadmap and is
    # intentionally NOT imported. Other populated orphan cells are blockers.
    for label, value_map in (("O", difficulty_cells), ("AC", summary_cells)):
        for row_number, value in value_map.items():
            if (str(value).strip() and row_number not in lesson_rows and
                    row_number not in chapter_rows):
                raise Step3Error(
                    f"Orphan {label}{row_number} content outside menu lessons."
                )
    if not chapters:
        raise Step3Error("No menu chapters found on the selected tab.")
    for chapter in chapters:
        if not chapter["lessons"]:
            raise Step3Error(f"Chapter {chapter['title']!r} has no lessons.")
    titles = [item["title"].casefold() for item in chapters]
    slugs = [item["slug"].casefold() for item in chapters]
    if len(titles) != len(set(titles)) or len(slugs) != len(set(slugs)):
        raise Step3Error("Duplicate chapter title or slug.")

    menu = {"menu": [
        {"level1": item["title"], "level2": item["lessons"]}
        for item in chapters
    ]}
    slug_menu = {"menu": [
        {"title": item["title"], "slug": item["slug"], "index": i}
        for i, item in enumerate(chapters)
    ]}

    # Extra checks equivalent to STEP_3_NEW finish, before any write.
    markdown: dict[str, str] = {}
    written = 0
    total_characters = 0
    multi_fragment_lessons = 0
    for i, chapter in enumerate(chapters, start=1):
        if len({t.casefold() for t in chapter["lessons"]}) != len(chapter["lessons"]):
            raise Step3Error(f"Duplicate lesson title in chapter {i}.")
        if any(not name.strip() or "\x00" in name for name in chapter["lessons"]):
            raise Step3Error(f"Blank/invalid lesson title in chapter {i}.")
        for j, (body, count) in enumerate(
            zip(chapter["bodies"], chapter["fragments"]), start=1
        ):
            stem = f"{chapter['slug']}-{j:03d}"
            relative_path = f"{i}.{chapter['slug']}/{stem}.md"
            markdown[relative_path] = body
            written += bool(body.strip())
            total_characters += len(body)
            multi_fragment_lessons += count > 1

    return {
        "module": module, "lang": lang, "location": location, "tab_title": title,
        "spreadsheet_id": tab["spreadsheet_id"], "gid": tab["gid"],
        "legacy_step": text_at(front[2], 9),
        "subject": subject, "detail_name": detail_name,
        "special_note": special_note, "menu": menu, "slug_menu": slug_menu,
        "base": base, "roadmap": roadmap, "references": references,
        "reference_raw": reference_raw,
        "markdown": markdown,
        "imported_fields": imported_child_fields,
        "difficult_count": sum(bool(v["difficult"]) for v in imported_child_fields.values()),
        "summary_count": sum(bool(v["summary"]) for v in imported_child_fields.values()),
        "chapters": len(chapters),
        "lessons": sum(len(item["lessons"]) for item in chapters),
        "written": written, "pending": len(markdown) - written,
        "markdown_characters": total_characters,
        "multi_fragment_lessons": multi_fragment_lessons,
    }


def fetch_tab(reader, url: str, gid: str, repo: Path) -> dict:
    client = reader.build_sheets_client()
    spreadsheet_id, _ = reader.parse_sheet_url(url)
    metadata = client.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
        fields="properties(title),sheets(properties(sheetId,title,gridProperties(rowCount,columnCount)))",
    ).execute()
    sheet = next(
        (s["properties"] for s in metadata.get("sheets", [])
         if str(s["properties"].get("sheetId")) == gid),
        None,
    )
    if sheet is None:
        raise Step3Error(f"Tab gid={gid} not found in the spreadsheet.")
    if sheet.get("gridProperties", {}).get("rowCount", 0) < 20:
        raise Step3Error("Tab is too short to contain the STEP 3 Menu.")
    row_count = sheet["gridProperties"]["rowCount"]
    title = sheet["title"]
    quoted = "'" + title.replace("'", "''") + "'"
    # FORMULA mode also exposes non-empty formulas: never drop a hidden source
    # cell merely because its computed/displayed value currently looks blank.
    data = client.spreadsheets().values().batchGet(
        spreadsheetId=spreadsheet_id,
        ranges=[f"{quoted}!A1:AC3", f"{quoted}!A18:N{row_count}",
                f"{quoted}!O20:O{row_count}", f"{quoted}!AC20:AC{row_count}",
                f"{quoted}!B17", f"{quoted}!L3",
                f"{quoted}!F{ROADMAP_FIRST_ROW}:H{ROADMAP_LAST_ROW}"],
        valueRenderOption="FORMULA",
    ).execute()
    ranges = data.get("valueRanges", [])
    if len(ranges) != 7:
        raise Step3Error("Unexpected Google Sheets range response.")
    # O and AC are sparse, aligned by absolute row number. AC parent rows
    # hold legacy chapter roadmaps, not lesson summaries.
    # Only entries belonging to child rows are imported by decode_sheet().
    def indexed_cells(response: dict, column: str) -> dict[int, str]:
        values = {}
        for number, row in enumerate(response.get("values", []), start=20):
            if not row or row[0] is None or not str(row[0]).strip():
                continue
            value = str(row[0])
            if value.startswith("="):
                raise Step3Error(
                    f"Formula at {column}{number} cannot be imported as raw text."
                )
            values[number] = value
        return values

    difficulty_rows = indexed_cells(ranges[2], "O")
    summary_rows = indexed_cells(ranges[3], "AC")
    front = ranges[0].get("values", [])
    menu_rows = ranges[1].get("values", [])
    # Explicitly pad rows when Google omitted empty trailing rows.
    front = front + [[] for _ in range(max(0, 3 - len(front)))]
    menu_rows = menu_rows + [[] for _ in range(max(0, 2 - len(menu_rows)))]
    def single_cell(index: int, label: str) -> str:
        matrix = ranges[index].get("values", [])
        if len(matrix) > 1 or (matrix and len(matrix[0]) > 1):
            raise Step3Error(f"Unexpected {label} value range")
        return text_at(matrix[0], 0, trim=False) if matrix else ""
    return {
        "title": title,
        "gid": gid,
        "spreadsheet_id": spreadsheet_id,
        "front": front,
        "menu_rows": menu_rows,
        "difficulty_rows": difficulty_rows,
        "summary_rows": summary_rows,
        "base_markdown": single_cell(4, "B17 Base"),
        "reference_yaml": single_cell(5, "L3 Reference"),
        "roadmap_rows": ranges[6].get("values", []),
    }


def expected_yaml(plan: dict) -> dict[str, dict]:
    return {
        "menu.yml": plan["menu"],
        "menu-level-1-slug.yml": plan["slug_menu"],
    }


def populate_knowledge(stage: Path, plan: dict) -> None:
    """Overlay STEP 4 text and statuses inside private staging only.

    The shared STEP 3 finish script creates canonical files first. We then
    restore Sheet-authored Markdown exactly, without platform newline changes.
    """
    from _knowledge_local import load_layout, markdown_has_content

    layout = load_layout(stage, lang=plan["lang"])
    if len(layout.lessons) != plan["lessons"]:
        raise Step3Error("STEP 3-generated lesson count differs from Sheet.")

    details = layout.detail
    for lesson in layout.lessons:
        rel = lesson.markdown_path.relative_to(layout.root).as_posix()
        body = plan["markdown"].get(rel)
        if body is None:
            raise Step3Error(f"Missing expected Markdown in Sheet plan: {rel}")
        status = "WRITTEN" if body.strip() else ""
        with lesson.markdown_path.open("w", encoding="utf-8", newline="") as handle:
            handle.write(body)
        if lesson.markdown_path.read_bytes() != body.encode("utf-8"):
            raise Step3Error(f"Markdown readback differs from Google Sheets: {rel}")

        # Use the canonical STEP 3 NEW lesson schema: exactly three fields.
        metadata = {**lesson.info, "status": status}
        with lesson.info_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(dump_yaml(metadata))
        child = details["menu"][lesson.chapter_index]["childs"][lesson.lesson_index]
        child["status"] = status
        imported = plan["imported_fields"][lesson.slug]
        if imported["difficult"]:
            child["difficult"] = imported["difficult"]
        if imported["summary"]:
            child["summary"] = LiteralText(imported["summary"])

    with layout.detail_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(dump_yaml(details))

    # STEP_4_NEW contract readback: titles, file identity, per-lesson status,
    # global status and non-empty Markdown must all match.
    readback = load_layout(stage, lang=plan["lang"])
    for lesson in readback.lessons:
        rel = lesson.markdown_path.relative_to(readback.root).as_posix()
        expected = plan["markdown"][rel]
        status = "WRITTEN" if expected.strip() else ""
        actual_status = readback.detail["menu"][lesson.chapter_index]["childs"][
            lesson.lesson_index]["status"]
        if lesson.info["status"] != status or actual_status != status:
            raise Step3Error(f"STEP 4 status readback mismatch: {rel}")
        child = readback.detail["menu"][lesson.chapter_index]["childs"][
            lesson.lesson_index]
        incoming = plan["imported_fields"][lesson.slug]
        if (child["difficult"] != incoming["difficult"] or
                child["summary"] != incoming["summary"] or
                any(child[field] != "" for field in
                    ("focus", "problemSolved", "mechanism", "applicationValue"))):
            raise Step3Error(f"Imported Knowledge metadata readback mismatch: {rel}")
        if lesson.markdown_path.read_bytes() != expected.encode("utf-8"):
            raise Step3Error(f"STEP 4 Markdown readback mismatch: {rel}")
        if status and not markdown_has_content(lesson.markdown_path):
            raise Step3Error(f"WRITTEN lesson is blank: {rel}")


def targets_for_plan(plan: dict) -> list[tuple[str, Path]]:
    """Only language-scoped targets plus identified flat legacy artifacts."""
    module, lang = plan["module"], plan["lang"]
    content = module / "content"
    result = [
        ("knowledge", content / "knowledge" / lang),
        ("base", content / "base" / lang / "base.md"),
        ("references", content / "reference" / lang / "references.yml"),
        ("roadmap", content / "roadmap" / lang / "roadmap.yml"),
        ("old-base", content / "readme" / "docs" / lang / "BASE.md"),
    ]
    flat = content / "knowledge"
    if flat.is_dir() and not flat.is_symlink():
        for item in sorted(flat.iterdir()):
            if item.name in LEGACY_KNOWLEDGE_FILES or (
                LEGACY_CHAPTER_DIR.fullmatch(item.name) and item.is_dir()
            ):
                result.append(("legacy", item))
    return result


def filesystem_path(path: Path) -> Path:
    """Use extended Windows paths so deep, *regular* files stay visible.

    Path.is_file()/exists() may incorrectly report False for a long Win32 path
    even when a normal on-disk file exists. This caused snapshot to mistake
    long lesson paths for unsafe special filesystem entries after publishing.
    Only ordinary absolute local/UNC paths from the module tree reach here.
    """
    if os.name != "nt":
        return path
    value = str(path)
    if value.startswith("\\\\?\\"):
        return path
    if value.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + value[2:])
    if not Path(value).is_absolute():
        raise Step3Error(f"Expected absolute path before Windows extension: {path}")
    return Path("\\\\?\\" + value)


def snapshot(path: Path):
    """Exact footprint of a file/tree; never traverse/delete a symbolic link."""
    path = filesystem_path(path)
    if path.is_symlink():
        raise Step3Error(f"Refusing symbolic link in Sheet synchronization: {path}")
    if not path.exists():
        return None
    if path.is_file():
        return ("file", hashlib.sha256(path.read_bytes()).hexdigest())
    if not path.is_dir():
        raise Step3Error(f"Unsafe output target: {path}")
    entries = []
    for item in sorted(path.rglob("*")):
        if item.is_symlink():
            raise Step3Error(f"Refusing symbolic link inside Sheet synchronization tree: {item}")
        if item.is_file():
            entries.append((item.relative_to(path).as_posix(), "file",
                            hashlib.sha256(item.read_bytes()).hexdigest()))
        elif item.is_dir():
            entries.append((item.relative_to(path).as_posix(), "dir"))
        else:
            raise Step3Error(f"Unsafe special filesystem entry: {item}")
    return ("dir", tuple(entries))


def preflight_targets(plan: dict) -> list[tuple[str, Path, object]]:
    module = plan["module"]
    targets = []
    for kind, path in [*targets_for_plan(plan), ("module-info", module / "module-info.json")]:
        current = path
        while current != module:
            if current.is_symlink() or (current.exists() and not (
                current.is_dir() if current != path else (current.is_dir() or current.is_file())
            )):
                raise Step3Error(f"Unsafe synchronization path: {current}")
            current = current.parent
        if kind in ("knowledge", "legacy") and path.exists():
            if kind == "knowledge" and not path.is_dir():
                raise Step3Error(f"Expected Knowledge directory: {path}")
        elif kind in ("base", "references", "roadmap", "old-base", "module-info"):
            if path.exists() and not path.is_file():
                raise Step3Error(f"Expected regular file: {path}")
        targets.append((kind, path, snapshot(path)))
    return targets


def build_staging(plan: dict, stage: Path, metadata_bytes: bytes) -> dict[str, Path]:
    """Render all outputs in a disposable module tree; never touch real content."""
    shutil.copy2(plan["module"] / "module-info.json", stage / "module-info.json")
    lang = plan["lang"]
    knowledge = stage / "content" / "knowledge" / lang
    knowledge.mkdir(parents=True)
    for name, doc in expected_yaml(plan).items():
        write_new(knowledge / name, dump_yaml(doc))
    menu_detail_generator.finish(stage, dry_run=False, lang=lang)
    populate_knowledge(stage, plan)
    _, produced, _, chapters, lessons = menu_detail_generator.plan_output(stage, lang=lang)
    if chapters != plan["chapters"] or lessons != plan["lessons"] or any(
        not path.is_file() for path in produced
    ):
        raise Step3Error("Generated Knowledge counts/files do not match Sheet")
    base = stage / "content" / "base" / lang / "base.md"
    ref = stage / "content" / "reference" / lang / "references.yml"
    roadmap = stage / "content" / "roadmap" / lang / "roadmap.yml"
    for path in (base, ref, roadmap):
        path.parent.mkdir(parents=True, exist_ok=True)
    base.write_bytes(plan["base"].encode("utf-8"))
    ref.write_bytes(plan["reference_raw"].encode("utf-8"))
    roadmap.write_bytes(dump_yaml(plan["roadmap"]).encode("utf-8"))
    if base.read_bytes() != plan["base"].encode("utf-8") or (
        yaml.safe_load(ref.read_text(encoding="utf-8")) != plan["references"]
    ) or yaml.safe_load(roadmap.read_text(encoding="utf-8")) != plan["roadmap"]:
        raise Step3Error("Base/Reference/Roadmap staging readback failed")
    info = stage / "module-info.json"
    info.write_bytes(metadata_bytes)
    if json.loads(info.read_text(encoding="utf-8-sig"))["SPECIAL_NOTE"]["VALUE"] != plan["special_note"]:
        raise Step3Error("Staging SPECIAL_NOTE.VALUE differs")
    return {
        "knowledge": knowledge, "base": base, "references": ref,
        "roadmap": roadmap, "module-info": info,
    }


def sync_plan(plan: dict) -> dict:
    """Read-only preflight used by dry-run and immediately before commit."""
    note_path, original_note_bytes, new_note_bytes = special_note_update_plan(
        plan["module"], plan["special_note"]
    )
    targets = preflight_targets(plan)
    if next((record[2] for record in targets if record[1] == note_path), None) != (
        "file", hashlib.sha256(original_note_bytes).hexdigest()
    ):
        raise Step3Error("module-info.json changed during preflight")
    return {
        "targets": targets, "metadata_bytes": new_note_bytes,
        "updates": [kind for kind, path, old in targets if kind != "module-info" or (
            original_note_bytes != new_note_bytes
        )],
        "deletions": [str(path) for kind, path, old in targets
                      if kind in ("old-base", "legacy") and old is not None],
    }


def apply_plan(plan: dict) -> None:
    """Replace scoped targets with a multi-path rollback transaction."""
    module = plan["module"]
    content = module / "content"
    preview = sync_plan(plan)
    if content.is_symlink() or (content.exists() and not content.is_dir()):
        raise Step3Error(f"Unsafe content/ directory: {content}")
    content_created = not content.exists()
    if content_created:
        content.mkdir()
    stage = Path(tempfile.mkdtemp(prefix=".sheet-sync-stage-", dir=content))
    if os.name == "nt":
        # Staging adds content/knowledge/<lang> to the already deep module path.
        # Windows long-path semantics require an extended absolute path; normal
        # Win32 paths may fail at ~260 chars even though the final target is valid.
        stage = Path("\\\\?\\" + str(stage.resolve()))
    published = []
    backup_moves = []
    created_dirs = []
    keep_backups = False
    try:
        generated = build_staging(plan, stage, preview["metadata_bytes"])
        expected = {name: snapshot(src) for name, src in generated.items()}
        current_targets = preflight_targets(plan)
        if current_targets != preview["targets"]:
            raise Step3Error("Target changed during Sheet staging; refusing to overwrite")
        operations = []
        for kind, target, before in current_targets:
            source = generated.get(kind)
            if kind == "module-info" and target.read_bytes() == preview["metadata_bytes"]:
                continue
            if source is not None and expected[kind] == before:
                continue
            if source is None and before is None:
                continue
            operations.append((kind, target, before, source))

        for count, (kind, target, old, source) in enumerate(operations):
            if snapshot(target) != old:
                raise Step3Error(f"Concurrent modification before publish: {target}")
            parent = target.parent
            missing_dirs = []
            while not parent.exists():
                if parent.is_symlink():
                    raise Step3Error(f"Unsafe parent in publish: {parent}")
                missing_dirs.append(parent)
                parent = parent.parent
            if parent.is_symlink():
                raise Step3Error(f"Unsafe parent in publish: {parent}")
            for directory in reversed(missing_dirs):
                directory.mkdir()
                created_dirs.append(directory)
            if old is not None:
                backup = stage / "backups" / str(count)
                backup.parent.mkdir(parents=True, exist_ok=True)
                target.rename(backup)
                backup_moves.append((target, backup))
            if source is not None:
                source.rename(target)
                published.append((target, expected[kind]))
                if snapshot(target) != expected[kind]:
                    raise Step3Error(f"Published output differs from staging: {target}")

        # Verify deletion as well as retained new targets.
        for kind, target, old, source in operations:
            if source is None and target.exists():
                raise Step3Error(f"Legacy file was not removed: {target}")
            if source is not None and snapshot(target) != expected[kind]:
                raise Step3Error(f"Final readback mismatch: {target}")
    except Exception as exc:
        errors = []
        for target, fingerprint in reversed(published):
            try:
                if snapshot(target) != fingerprint:
                    raise Step3Error("File modified concurrently after publish")
                if target.is_dir():
                    shutil.rmtree(filesystem_path(target))
                else:
                    target.unlink()
            except Exception as rollback_error:
                errors.append(str(rollback_error))
        for target, backup in reversed(backup_moves):
            try:
                if target.exists() or target.is_symlink():
                    raise Step3Error(f"Cannot restore over another file: {target}")
                backup.rename(target)
            except Exception as rollback_error:
                errors.append(str(rollback_error))
        for directory in reversed(created_dirs):
            try:
                directory.rmdir()
            except OSError:
                pass
        if errors:
            keep_backups = True
            raise Step3Error(f"Sync failed: {exc}; ROLLBACK INCOMPLETE: {errors}; backup={stage}") from exc
        raise Step3Error(f"Sync failed, previous content restored: {exc}") from exc
    finally:
        if not keep_backups:
            shutil.rmtree(stage)
        if content_created and content.is_dir():
            try:
                content.rmdir()
            except OSError:
                pass
    print(f"SYNC_OK module={module} lang={plan['lang']} "
          f"knowledge_chapters={plan['chapters']} lessons={plan['lessons']} "
          f"roadmap={len(plan['roadmap']['roadmap'])} "
          f"references={len(plan['references']['references'])} "
          f"base_characters={len(plan['base'])} "
          f"replaced={len(published)} removed_legacy={len(preview['deletions'])} "
          f"current_step_unchanged=True")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file-url", required=True, help="Full Google Sheet URL.")
    parser.add_argument("--sheet-id", help="Tab gid; omit if the URL has #gid=.")
    parser.add_argument("--lang", "--language", dest="lang", default="vi",
                        help="Target language under content/knowledge/ (default: vi)")
    parser.add_argument("--ipv4", action="store_true", help="Prefer IPv4 for the Google APIs.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview only (default).")
    mode.add_argument("--apply", action="store_true",
                      help="Replace Sheet-owned Knowledge, Base, Roadmap, Reference, Special Note and remove old artifacts.")
    parser.add_argument("--repo-root", type=Path, default=REPO, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        reader = reader_module()
        spreadsheet_id, url_gid = reader.parse_sheet_url(args.file_url)
        gid = reader.resolve_gid(args.sheet_id, url_gid)
        repo = args.repo_root.resolve(strict=True)
        if args.ipv4:
            reader.prefer_ipv4()
        tab = fetch_tab(reader, args.file_url, gid, repo)
        plan = decode_sheet(tab, repo, lang=args.lang)
        overview = sync_plan(plan)
        if args.apply:
            apply_plan(plan)
        else:
            print(json.dumps({
                "status": "DRY_RUN",
                "spreadsheetId": spreadsheet_id,
                "tabTitle": plan["tab_title"],
                "gid": plan["gid"],
                "moduleLocation": plan["location"],
                "language": plan["lang"],
                "subject": plan["subject"],
                "detailName": plan["detail_name"],
                "chapters": plan["chapters"],
                "lessons": plan["lessons"],
                "legacyStep": plan["legacy_step"],
                "written": plan["written"],
                "pending": plan["pending"],
                "difficultCount": plan["difficult_count"],
                "summaryCount": plan["summary_count"],
                "baseCharacters": len(plan["base"]),
                "roadmapCount": len(plan["roadmap"]["roadmap"]),
                "referenceCount": len(plan["references"]["references"]),
                "legacyPathsToRemove": overview["deletions"],
                "specialNoteDestination": str(plan["module"] / "module-info.json"),
                "specialNoteWillReplace": overview["metadata_bytes"] != (
                    plan["module"] / "module-info.json"
                ).read_bytes(),
                "markdownCharacters": plan["markdown_characters"],
                "multiFragmentLessons": plan["multi_fragment_lessons"],
                "generatedFiles": 3 + plan["lessons"] * 2,
                "destination": str(plan["module"] / "content"),
                "targets": [str(path) for _kind, path, _old in overview["targets"]],
            }, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(f"BLOCKER: SHEET_TO_STEP3_NEW: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
