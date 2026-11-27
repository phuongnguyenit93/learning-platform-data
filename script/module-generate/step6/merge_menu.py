#!/usr/bin/env python3
"""STEP 6: verify completed chapters and merge them into menu-detail-status.yml.

This script never deletes staging. Cleanup requires delete_temp_split_menu.py.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

import split_menu
from readme_related import (
    KINDS, RelatedError, chapter_catalog, read_assessments, related_links,
    semantic_fingerprint,
)
from split_menu import (
    Step3Error, Step6Error, check_manifest, digest, load_layout, load_manifest,
    markdown_has_content, module_context, parse_menu,
    read_status, regular_file, validate_chapter, verify_stage_inventory,
    STEP6_FIELDS,
)

REQUIRED_SUMMARY_HEADINGS = (
    "# 0. Định hướng học tập",
    "## 1. Mục đích của bài học",
    "## 2. Những câu hỏi người học phải tự trả lời được",
    "## 3. Sau khi học xong, người học phải đạt được điều gì?",
)
COMPARISON_FIELDS = ("focus", "problemSolved", "mechanism", "applicationValue")


def validate_summary(summary: str, title: str, slug: str) -> None:
    if not summary.strip() or "\x00" in summary:
        raise Step6Error(f"Missing/invalid Summary for {slug}")
    lines = summary.splitlines()
    headings = [line.strip() for line in lines
                if re.match(r"^#{1,2} (?:[0-3])\.", line)]
    if headings != list(REQUIRED_SUMMARY_HEADINGS):
        raise Step6Error(f"Summary headings 0→1→2→3 missing/out of order: {slug}")
    locations = [lines.index(heading) for heading in REQUIRED_SUMMARY_HEADINGS]
    if any(line.strip() for line in lines[locations[0] + 1:locations[1]]):
        raise Step6Error(f"Summary section 0 must contain only a heading: {slug}")
    sec1 = lines[locations[1] + 1:locations[2]]
    if not any(line.strip() == f"**{title}**" for line in sec1):
        raise Step6Error(f"Summary must include exact bold lesson title: {slug}")
    sec2 = lines[locations[2] + 1:locations[3]]
    if not any(line.startswith("### ") for line in sec2) or not any(
        re.match(r"^\s*\d+\.\s+.+\?\s*$", line) for line in sec2
    ):
        raise Step6Error(f"Summary needs a question group and open questions: {slug}")
    sec3 = lines[locations[3] + 1:]
    if not any(re.fullmatch(r"\|\s*Năng lực\s*\|\s*Kết quả mong đợi\s*\|", line.strip())
               for line in sec3) or not any(
        re.fullmatch(r"\|\s*:?-{3,}:?\s*\|\s*:?-{3,}:?\s*\|", line.strip())
        for line in sec3
    ):
        raise Step6Error(f"Summary requires a two-column GFM competency table: {slug}")
    if not any(line.startswith("|") and line.count("|") == 3
               and "Năng lực" not in line and not re.match(r"^\|\s*:?-{3,}", line)
               for line in sec3):
        raise Step6Error(f"Summary competency table has no content row: {slug}")
    if re.search(r"\b(?:TODO|TBD)\b|<[^>]+>", summary, flags=re.IGNORECASE):
        raise Step6Error(f"Summary still contains placeholders: {slug}")


def validate_finished_chapter(staged: dict, original: dict, index: int) -> None:
    validate_chapter(staged, number=index)
    if (staged["slug"], staged["title"]) != (original["slug"], original["title"]):
        raise Step6Error(f"Chapter identity changed: #{index}")
    if len(staged["childs"]) != len(original["childs"]):
        raise Step6Error(f"Chapter lesson count changed: #{index}")
    for child, baseline in zip(staged["childs"], original["childs"]):
        slug = baseline["slug"]
        if any(child.get(key) != baseline.get(key)
               for key in set(baseline) - STEP6_FIELDS):
            raise Step6Error(f"Immutable lesson metadata changed: {slug}")
        if child["status"] != "WRITTEN":
            raise Step6Error(f"Lesson status must remain WRITTEN: {slug}")
        if child["difficult"] not in ("BASIC", "INTERMEDIATE", "ADVANCED"):
            raise Step6Error(f"Missing difficulty: {slug}")
        for field in COMPARISON_FIELDS:
            content = child[field]
            if not content.strip() or "\x00" in content or re.search(
                r"\b(?:TODO|TBD)\b|<[^>]+>", content, re.IGNORECASE
            ):
                raise Step6Error(f"Invalid {field}: {slug}")
        validate_summary(child["summary"], child["title"], slug)


def staged_hashes(stage: Path, manifest: dict) -> dict[str, str]:
    names = sorted(
        name for chapter in manifest["chapters"]
        for name in (chapter["file"], chapter["status_file"])
    )
    return {name: digest(regular_file(stage / name)) for name in names}


def stage_marker(stage: Path, manifest: dict, output_bytes: bytes) -> dict:
    return {
        "version": 1,
        "source_sha256": manifest["source_sha256"],
        "merged_sha256": digest(output_bytes),
        "manifest_sha256": digest(regular_file(stage / "manifest.json")),
        "files_sha256": staged_hashes(stage, manifest),
    }


def safe_write(path: Path, before: bytes | None, content: bytes) -> None:
    """Atomic single-file replace after readback of original bytes."""
    if before is not None and regular_file(path) != before:
        raise Step6Error(f"Source changed during merge: {path}")
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=".step6-merge-", suffix=".tmp",
                                        dir=path.parent)
    try:
        if path.exists():
            os.chmod(tmp_name, stat.S_IMODE(path.stat().st_mode))
        with os.fdopen(tmp_fd, "wb") as writer:
            writer.write(content)
            writer.flush()
            os.fsync(writer.fileno())
        if before is not None and regular_file(path) != before:
            raise Step6Error(f"Source changed before merge replace: {path}")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    if regular_file(path) != content:
        raise Step6Error(f"Exact readback failed after writing: {path}")


def merge(module_arg: str, *, lang: str = "vi", dry_run: bool = False) -> str:
    module, service, stage = module_context(module_arg, lang)
    manifest = load_manifest(stage)
    check_manifest(manifest, module, service, lang)
    try:
        layout = load_layout(module, lang=lang)
    except (Step3Error, OSError, UnicodeError) as exc:
        raise Step6Error(f"Knowledge layout invalid at merge: {exc}") from exc
    current_lesson_hashes = {
        lesson.info_path.relative_to(split_menu.windows_long_path(split_menu.REPO_ROOT.resolve())).as_posix():
            digest(regular_file(lesson.info_path))
        for lesson in layout.lessons
    }
    if current_lesson_hashes != manifest["lesson_info_sha256"]:
        raise Step6Error("Lesson YAML changed after split; refusing merge")
    for lesson in layout.lessons:
        if lesson.info["status"] != "WRITTEN" or not markdown_has_content(lesson.markdown_path):
            raise Step6Error(f"Lesson Markdown/status not complete at merge: {lesson.slug}")
    marker_path = stage / "merged.json"
    verify_stage_inventory(stage, manifest, merged=marker_path.exists())
    source = module / "content" / "knowledge" / lang / "menu-detail-status.yml"
    current_bytes = regular_file(source)
    try:
        raw = current_bytes.decode("utf-8-sig")
    except UnicodeError as exc:
        raise Step6Error(f"Invalid source UTF-8: {source}") from exc
    original, _, prefix = parse_menu(raw, location=str(source))
    if digest(prefix.encode("utf-8")) != manifest.get("source_prefix_sha256"):
        raise Step6Error("Source header changed after split")
    if len(original) != len(manifest["chapters"]):
        raise Step6Error("Source chapter count differs from staging manifest")
    for index, chapter in enumerate(original, 1):
        validate_chapter(chapter, number=index)
        entry = manifest["chapters"][index - 1]
        if (chapter["slug"] != entry["slug"] or chapter["title"] != entry["title"] or
                [child["slug"] for child in chapter["childs"]] != entry["child_slugs"]):
            raise Step6Error(f"Source identity changed for chapter #{index}")

    contents = []
    for i, entry in enumerate(manifest["chapters"], 1):
        if read_status(stage / entry["status_file"]) != "WRITTEN":
            raise Step6Error(f"Chapter not marked WRITTEN: {entry['status_file']}")
        try:
            staged_raw = regular_file(stage / entry["file"]).decode("utf-8-sig")
        except UnicodeError as exc:
            raise Step6Error(f"Invalid UTF-8 staged chapter: {entry['file']}") from exc
        staged, portions, header = parse_menu(staged_raw, location=entry["file"])
        if len(staged) != 1 or header not in ("menu:\n", "menu:\r\n"):
            raise Step6Error(f"Staged file must contain exactly one chapter: {entry['file']}")
        # If the source is already merged (idempotent rerun), do not treat
        # the authored field differences as unauthorized. Immutable data
        # is checked using the source, and original checksum gates the write.
        if digest(current_bytes) == manifest["source_sha256"]:
            validate_finished_chapter(staged[0], original[i - 1], i)
        else:
            validate_finished_chapter(staged[0], staged[0], i)
        contents.append(portions[0])

    # Chapter WRITTEN covers Knowledge QA AND three Related proposal files.
    # Refuse to publish Knowledge when Related is blank/inconsistent or when
    # assessment content drifted after the split baseline.
    if digest(regular_file(module / "content" / "knowledge" / lang /
                           "menu-level-1-slug.yml")) != manifest["chapter_menu_sha256"]:
        raise Step6Error("Chapter catalog changed after split")
    try:
        assessment_stage = module / "content" / "temp" / "step5"
        _bytes, assessments, assessment_items = read_assessments(assessment_stage)
        if any(semantic_fingerprint(kind, assessments[kind]) !=
               manifest["assessment_semantic_sha256"][kind] for kind in KINDS):
            raise Step6Error("Assessment content changed since STEP 6 split")
        related_links(assessment_stage, chapter_catalog(module, lang), assessment_items)
    except RelatedError as exc:
        raise Step6Error(f"Related proposals not complete: {exc}") from exc

    assembled = prefix
    for part in contents:
        if assembled and not assembled.endswith(("\n", "\r")):
            assembled += "\n"
        assembled += part
    output = (b"\xef\xbb\xbf" if current_bytes.startswith(b"\xef\xbb\xbf") else b"") + (
        assembled.encode("utf-8")
    )
    current_hash = digest(current_bytes)
    if current_hash not in (manifest["source_sha256"], digest(output)):
        raise Step6Error("Source changed after split: refusing to overwrite external edits")

    # A completed stage is immutable: the marker must still describe exactly
    # the same source, files, and merged output.
    marker = stage_marker(stage, manifest, output)
    if marker_path.exists():
        existing = json.loads(regular_file(marker_path).decode("utf-8"))
        if existing != marker or current_bytes != output:
            raise Step6Error("Merge marker differs from staged/current data")
        return f"ALREADY_MERGED stage={stage} chapters={len(contents)}"
    if dry_run:
        return f"DRY_RUN stage={stage} chapters={len(contents)} output_sha256={digest(output)}"

    # Check for edits to staging during preparation and source race.
    if staged_hashes(stage, manifest) != marker["files_sha256"]:
        raise Step6Error("Staging changed while preparing merge")
    if current_bytes != output:
        safe_write(source, current_bytes, output)
    else:
        if regular_file(source) != output:
            raise Step6Error("Source changed during idempotent merge")
    # Keep the stage until explicit cleanup; marker confirms exact merge.
    payload = (json.dumps(marker, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    safe_write(marker_path, None, payload)
    return f"MERGE_OK source={source} chapters={len(contents)} stage_preserved={stage}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True)
    parser.add_argument("--lang", default="vi")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        print(merge(args.module, lang=args.lang, dry_run=args.dry_run))
        return 0
    except (Step6Error, OSError, UnicodeError, ValueError) as exc:
        print(f"BLOCKER: STEP6_MERGE: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
