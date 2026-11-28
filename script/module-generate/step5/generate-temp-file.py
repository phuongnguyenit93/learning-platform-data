#!/usr/bin/env python3
"""Prepare local STEP 5 working files for exactly one activated module.

This script creates no assessment content and never advances a Phase status.
Existing worker data is never overwritten, truncated, reset, or deleted.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
KINDS = ("quiz", "interview", "casestudy")
STATUS_INITIAL = "status: Phase 0\n"
SUBFOLDERS = ("raw", "format", "status", "readme-related")
SERVICE_RE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*\Z")
PHASES = {
    "quiz": frozenset((0, 1, 2, 3, 5)),
    "interview": frozenset((0, 1, 2, 3, 4, 5)),
    "casestudy": frozenset((0, 1, 2, 3, 4, 5)),
}
YAML_ROOTS = {
    "quiz": "quiz",
    "interview": "interviewQuestion",
    "casestudy": "caseStudy",
}


class Step5Error(Exception):
    """An unsafe module, path, or existing staging state."""


def _read_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise Step5Error(f"Expected regular JSON file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError, OSError) as exc:
        raise Step5Error(f"Invalid JSON at {path}: {exc}") from exc
    if type(value) is not dict:
        raise Step5Error(f"Expected JSON object: {path}")
    return value


def _value(data: dict, name: str) -> object:
    node = data.get(name)
    return node.get("VALUE") if type(node) is dict else None


def module_context(module_arg: str, lang: str = "vi") -> tuple[Path, Path]:
    if lang != "vi":
        raise Step5Error("STEP 5 NEW currently supports only lang=vi; staging is module-scoped")
    modules = REPO_ROOT.resolve() / "module"
    requested = Path(module_arg).expanduser()
    if not requested.is_absolute() and requested.parts and requested.parts[0] == "module":
        requested = modules.joinpath(*requested.parts[1:])
    try:
        module = requested.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise Step5Error(f"Module does not exist: {module_arg}") from exc
    modules = modules.resolve()
    if module == modules or not module.is_relative_to(modules) or not module.is_dir():
        raise Step5Error(f"Module must be below {modules}: {module}")
    if _read_json(module / "module_activate.json").get("isModule") is not True:
        raise Step5Error(f"Module is not active: {module}")
    info = _read_json(module / "module-info.json")
    service = _value(info, "SERVICE_NAME")
    describe = _value(info, "SERVICE_NAME_DESCRIBE")
    note = _value(info, "SPECIAL_NOTE")
    languages = _value(info, "MODULE_LANGUAGE")
    if type(service) is not str or not SERVICE_RE.fullmatch(service):
        raise Step5Error("Invalid SERVICE_NAME.VALUE")
    if type(describe) is not str or not describe.strip() or type(note) is not str:
        raise Step5Error("SERVICE_NAME_DESCRIBE and SPECIAL_NOTE must be strings")
    if type(languages) is not list or lang not in languages:
        raise Step5Error(f"Language {lang} is not enabled in the module")
    content = module / "content"
    stage = content / "temp" / "step5"
    if content.is_symlink() or not content.is_dir():
        raise Step5Error(f"Content directory missing or unsafe: {content}")
    for directory in (content / "temp", stage, *(stage / s for s in SUBFOLDERS)):
        if directory.is_symlink():
            raise Step5Error(f"Symlinked staging directory is not permitted: {directory}")
        if directory.exists() and not directory.is_dir():
            raise Step5Error(f"Expected directory, found another file type: {directory}")
    return module, stage


def chapter_slugs(module: Path, lang: str) -> list[str]:
    menu_path = module / "content" / "knowledge" / lang / "menu-level-1-slug.yml"
    value = _yaml(menu_path)
    chapters = value.get("menu") if type(value) is dict and set(value) == {"menu"} else None
    if type(chapters) is not list or not chapters:
        raise Step5Error(f"Missing chapter menu in {menu_path}")
    names: list[str] = []
    for position, item in enumerate(chapters):
        if type(item) is not dict or set(item) != {"title", "slug", "index"}:
            raise Step5Error(f"Invalid chapter entry at index {position}")
        slug = item["slug"]
        if type(item["index"]) is not int or item["index"] != position:
            raise Step5Error(f"Noncontiguous chapter index at {position}")
        if type(slug) is not str or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", slug):
            raise Step5Error(f"Invalid chapter slug at {position}: {slug!r}")
        if type(item["title"]) is not str or not item["title"].strip() or slug in names:
            raise Step5Error(f"Invalid or duplicate chapter at {position}: {slug}")
        names.append(slug)
    return names


def expected_paths(stage: Path, slugs: list[str]) -> dict[Path, bytes]:
    files: dict[Path, bytes] = {}
    for kind in KINDS:
        files[stage / "raw" / f"{kind}.md"] = b""
        files[stage / "format" / f"{kind}.yml"] = b""
        files[stage / "status" / f"{kind}.yml"] = STATUS_INITIAL.encode("utf-8")
    for slug in slugs:
        for kind in KINDS:
            files[stage / "readme-related" / slug / f"{kind}.yml"] = b""
    return files


def _no_duplicate_keys(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict:
    result: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in result:
            raise Step5Error(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


class StrictLoader(yaml.SafeLoader):
    pass


StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys
)


def _yaml(path: Path) -> object:
    if path.is_symlink() or not path.is_file():
        raise Step5Error(f"Expected regular YAML file: {path}")
    try:
        return yaml.load(path.read_text(encoding="utf-8-sig"), Loader=StrictLoader)
    except (yaml.YAMLError, UnicodeError, ValueError, OSError) as exc:
        raise Step5Error(f"Invalid YAML at {path}: {exc}") from exc


def _phase(path: Path, kind: str) -> int:
    value = _yaml(path)
    if type(value) is not dict or set(value) != {"status"}:
        raise Step5Error(f"Expected only 'status' at {path}")
    status = value["status"]
    if type(status) is not str or not re.fullmatch(r"Phase [0-5]", status):
        raise Step5Error(f"Invalid STEP 5 status at {path}: {status!r}")
    phase = int(status[-1])
    if phase not in PHASES[kind]:
        raise Step5Error(f"Unexpected terminal status for {kind}: {status}")
    return phase


def _required_text(item: dict, field: str, where: str, *, filled: bool) -> None:
    value = item.get(field)
    if type(value) is not str:
        raise Step5Error(f"Expected string for {where}.{field}")
    if filled and not value.strip():
        raise Step5Error(f"Missing Phase data at {where}.{field}")
    if not filled and value != "":
        raise Step5Error(f"Field was filled before its Phase: {where}.{field}")


def _verify_format(kind: str, data: object, phase: int, path: Path) -> None:
    root = YAML_ROOTS[kind]
    if type(data) is not dict or set(data) != {root}:
        raise Step5Error(f"Malformed assessment root at {path}")
    groups = data[root]
    if type(groups) is not list or not groups:
        raise Step5Error(f"Expected nonempty group list at {path}")
    collection = "cases" if kind == "casestudy" else "questions"
    for group_index, group in enumerate(groups, 1):
        if type(group) is not dict or set(group) != {"groupID", "groupName", collection}:
            raise Step5Error(f"Invalid group shape at {path} group {group_index}")
        if type(group["groupID"]) is not int or group["groupID"] != group_index:
            raise Step5Error(f"Invalid groupID at {path} group {group_index}")
        if type(group["groupName"]) is not str or not group["groupName"].strip():
            raise Step5Error(f"Missing group name at {path} group {group_index}")
        items = group[collection]
        if type(items) is not list or not items:
            raise Step5Error(f"Empty group at {path} group {group_index}")
        for index, item in enumerate(items, 1):
            where = f"{path} group {group_index} item {index}"
            if type(item) is not dict:
                raise Step5Error(f"Expected mapping at {where}")
            if kind == "quiz":
                expected = {"index", "question", "answers", "correctAnswerId", "readmeRelated"}
                statement = "question"
            elif kind == "interview":
                expected = {"index", "question", "knowledge", "answer", "readmeRelated"}
                statement = "question"
            else:
                expected = {"index", "situation", "resolve", "knowledge", "answer", "readmeRelated"}
                statement = "situation"
            if set(item) != expected:
                raise Step5Error(f"Wrong STEP 5 fields at {where}")
            if type(item["index"]) is not int or item["index"] != index - 1:
                raise Step5Error(f"Invalid zero-based index at {where}")
            if type(item[statement]) is not str or not item[statement].strip():
                raise Step5Error(f"Missing {statement} at {where}")
            related = item["readmeRelated"]
            if type(related) is not dict or set(related) != {"anchorList"}:
                raise Step5Error(f"Invalid readmeRelated at {where}")
            anchors = related["anchorList"]
            if type(anchors) is not list or (phase < 5 and anchors != []):
                raise Step5Error(f"Expected empty anchorList before Phase 5 at {where}")
            if any(type(anchor) is not str or not anchor.strip() for anchor in anchors) or (
                len(set(anchors)) != len(anchors)
            ):
                raise Step5Error(f"Invalid merged anchorList at {where}")
            if kind == "quiz":
                answers = item["answers"]
                if type(answers) is not list or len(answers) != 4:
                    raise Step5Error(f"Quiz requires four answers at {where}")
                for answer_id, answer in zip("ABCD", answers):
                    if type(answer) is not dict or set(answer) != {
                        "id", "answer", "explanation"
                    } or answer["id"] != answer_id:
                        raise Step5Error(f"Invalid answer identity at {where}")
                    if type(answer["answer"]) is not str or not answer["answer"].strip():
                        raise Step5Error(f"Empty Quiz choice at {where}")
                    _required_text(
                        answer, "explanation", f"{where}.{answer_id}", filled=phase >= 3
                    )
                if type(item["correctAnswerId"]) is not str or (
                    item["correctAnswerId"] not in "ABCD"
                ):
                    raise Step5Error(f"Invalid correctAnswerId at {where}")
            else:
                _required_text(item, "knowledge", where, filled=phase >= 3)
                if kind == "casestudy":
                    _required_text(item, "resolve", where, filled=phase >= 3)
                _required_text(item, "answer", where, filled=phase >= 4)


def inspect_existing(stage: Path, files: dict[Path, bytes]) -> None:
    """Refuse foreign entries or ambiguous partial progress before creating any file."""
    if not stage.exists():
        return
    actual_folders = {entry.name for entry in stage.iterdir()}
    if actual_folders - set(SUBFOLDERS):
        raise Step5Error(f"Unexpected entries in {stage}: {sorted(actual_folders - set(SUBFOLDERS))}")
    for folder in SUBFOLDERS:
        target = stage / folder
        if not target.exists():
            continue
        if target.is_symlink() or not target.is_dir():
            raise Step5Error(f"Unsafe staging folder: {target}")
        if folder == "readme-related":
            actual_slugs = {entry.name for entry in target.iterdir()}
            expected_slugs = {p.parent.name for p in files if p.parent.parent == target}
            if actual_slugs - expected_slugs:
                raise Step5Error(f"Unexpected chapter folders in {target}: {sorted(actual_slugs - expected_slugs)}")
            if actual_slugs != expected_slugs:
                statuses = [
                    stage / "status" / f"{kind}.yml" for kind in KINDS
                ]
                if any(path.exists() and _phase(path, kind) > 0
                       for kind, path in zip(KINDS, statuses)) or any(
                    file.is_file() and file.stat().st_size
                    for chapter_folder in target.iterdir() if chapter_folder.is_dir()
                    for file in chapter_folder.iterdir()
                ):
                    raise Step5Error("Knowledge chapter menu changed after STEP 5 work began")
            for slug in actual_slugs:
                chapter_folder = target / slug
                if chapter_folder.is_symlink() or not chapter_folder.is_dir():
                    raise Step5Error(f"Unsafe related chapter folder: {chapter_folder}")
                entries = {entry.name for entry in chapter_folder.iterdir()}
                if entries - {f"{kind}.yml" for kind in KINDS}:
                    raise Step5Error(f"Unexpected related files in {chapter_folder}")
                if any(item.is_symlink() or not item.is_file() for item in chapter_folder.iterdir()):
                    raise Step5Error(f"Unsafe related file in {chapter_folder}")
            continue
        actual = {entry.name for entry in target.iterdir()}
        expected = {p.name for p in files if p.parent == target}
        if actual - expected:
            raise Step5Error(f"Unexpected files in {target}: {sorted(actual - expected)}")
        for entry in target.iterdir():
            if entry.is_symlink() or not entry.is_file():
                raise Step5Error(f"Unsafe staging entry: {entry}")
    for kind in KINDS:
        status = stage / "status" / f"{kind}.yml"
        raw = stage / "raw" / f"{kind}.md"
        formatted = stage / "format" / f"{kind}.yml"
        if not status.exists():
            if (raw.exists() and raw.stat().st_size) or (
                formatted.exists() and formatted.stat().st_size
            ):
                raise Step5Error(f"Missing status for existing {kind} work; refusing reset")
            continue
        phase = _phase(status, kind)
        if phase >= 1 and (not raw.is_file() or not raw.read_bytes().strip()):
            raise Step5Error(f"Phase {phase} requires populated raw/{kind}.md")
        if phase >= 2:
            if not formatted.is_file() or not formatted.read_bytes().strip():
                raise Step5Error(f"Phase {phase} requires populated format/{kind}.yml")
            _verify_format(kind, _yaml(formatted), phase, formatted)


def prepare(module_arg: str, *, lang: str = "vi", dry_run: bool = False) -> tuple[str, tuple[str, ...]]:
    module, stage = module_context(module_arg, lang)
    files = expected_paths(stage, chapter_slugs(module, lang))
    inspect_existing(stage, files)
    missing = tuple(
        str(path.relative_to(stage)).replace("\\", "/")
        for path in files if not path.exists()
    )
    if dry_run:
        return ("WOULD_CREATE" if not stage.exists() else "WOULD_RESUME", missing)
    if not stage.exists():
        parent = stage.parent
        parent.mkdir(parents=True, exist_ok=True)
        scratch = Path(tempfile.mkdtemp(prefix=".step5-init-", dir=parent))
        try:
            for path, data in files.items():
                dest = scratch / path.relative_to(stage)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
            if stage.exists():
                raise Step5Error(f"Another process created staging: {stage}")
            os.rename(scratch, stage)
        finally:
            if scratch.exists():
                shutil.rmtree(scratch)
        return "CREATED", missing
    for directory in {path.parent for path in files}:
        directory.mkdir(parents=True, exist_ok=True)
    for path, data in files.items():
        if not path.exists():
            try:
                with path.open("xb") as handle:
                    handle.write(data)
            except FileExistsError as exc:
                raise Step5Error(f"Staging modified concurrently: {path}") from exc
    inspect_existing(stage, files)
    return "RESUMED", missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True, help="Path inside java-learning/module")
    parser.add_argument("--lang", default="vi", help="Assessment language (default: vi)")
    parser.add_argument("--dry-run", action="store_true", help="Inspect without writing")
    args = parser.parse_args(argv)
    try:
        result, created = prepare(args.module, lang=args.lang, dry_run=args.dry_run)
    except (Step5Error, OSError) as exc:
        print(f"BLOCKER: STEP5_TEMP_INVALID: {exc}", file=sys.stderr)
        return 2
    print(f"{result}: {len(created)} files ({', '.join(created) or 'nothing missing'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
