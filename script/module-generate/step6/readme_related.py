#!/usr/bin/env python3
"""Shared strict local assessment and chapter-related validation for STEP 6."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import yaml


KINDS = ("quiz", "interview", "casestudy")
ROOTS = {"quiz": "quiz", "interview": "interviewQuestion", "casestudy": "caseStudy"}
FINAL_BEFORE_RELATED = {"quiz": 3, "interview": 4, "casestudy": 4}
SLUG = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")


class RelatedError(Exception):
    """Schema, ownership, preflight, or referential-integrity error."""


class StrictLoader(yaml.SafeLoader):
    pass


def no_duplicate_keys(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict:
    result: dict = {}
    for key, value in node.value:
        name = loader.construct_object(key, deep=True)
        if name in result:
            raise RelatedError(f"Duplicate YAML key: {name}")
        result[name] = loader.construct_object(value, deep=True)
    return result


StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, no_duplicate_keys
)


def read_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise RelatedError(f"Missing or unsafe regular file: {path}")
    return path.read_bytes()


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_yaml(path: Path) -> object:
    try:
        return yaml.load(read_file(path).decode("utf-8-sig"), Loader=StrictLoader)
    except (yaml.YAMLError, UnicodeError, ValueError) as exc:
        raise RelatedError(f"Bad YAML in {path}: {exc}") from exc


def to_yaml(value: dict) -> bytes:
    return yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=110).encode("utf-8")


def semantic_fingerprint(kind: str, data: dict) -> str:
    """Hash all non-Related data, surviving YAML reserialization and Phase 5."""
    import copy

    clone = copy.deepcopy(data)
    collection = "cases" if kind == "casestudy" else "questions"
    for group in clone[ROOTS[kind]]:
        for item in group[collection]:
            item["readmeRelated"]["anchorList"] = []
    return sha(json.dumps(clone, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8"))


def chapter_catalog(module: Path, lang: str) -> list[dict]:
    knowledge = module / "content" / "knowledge" / lang
    levels = load_yaml(knowledge / "menu-level-1-slug.yml")
    detail = load_yaml(knowledge / "menu-detail-status.yml")
    if type(levels) is not dict or set(levels) != {"menu"} or (
        type(levels["menu"]) is not list or not levels["menu"]
    ):
        raise RelatedError("Invalid menu-level-1-slug.yml")
    if type(detail) is not dict or set(detail) != {"menu"} or (
        type(detail["menu"]) is not list or len(detail["menu"]) != len(levels["menu"])
    ):
        raise RelatedError("Chapter count differs from menu-detail-status.yml")
    catalog = []
    seen = set()
    for chapter_index, (level, entry) in enumerate(zip(levels["menu"], detail["menu"])):
        if type(level) is not dict or set(level) != {"index", "slug", "title"} or (
            type(level["index"]) is not int or level["index"] != chapter_index
        ):
            raise RelatedError(f"Invalid chapter catalog index {chapter_index}")
        slug, title = level["slug"], level["title"]
        if type(slug) is not str or not SLUG.fullmatch(slug) or slug in seen:
            raise RelatedError(f"Invalid/duplicate chapter slug: {slug}")
        if type(title) is not str or not title.strip():
            raise RelatedError(f"Invalid chapter title: {slug}")
        if type(entry) is not dict or entry.get("slug") != slug or (
            entry.get("title") != title
        ):
            raise RelatedError(f"Knowledge chapter identity changed: {slug}")
        children = entry.get("childs")
        if type(children) is not list or not children:
            raise RelatedError(f"Empty Knowledge chapter: {slug}")
        valid_slugs = []
        for i, child in enumerate(children, 1):
            expected = f"{slug}-{i:03d}"
            if type(child) is not dict or child.get("slug") != expected:
                raise RelatedError(f"Invalid lesson slug in {slug}: {expected}")
            valid_slugs.append(expected)
        seen.add(slug)
        catalog.append({"slug": slug, "title": title, "index": chapter_index,
                        "lessons": frozenset(valid_slugs)})
    return catalog


def validate_assessment(kind: str, data: object) -> dict[tuple[int, int], dict]:
    root = ROOTS[kind]
    if type(data) is not dict or set(data) != {root} or (
        type(data[root]) is not list or not data[root]
    ):
        raise RelatedError(f"Invalid assessment root: {kind}")
    result = {}
    for groupID, group in enumerate(data[root], 1):
        field = "cases" if kind == "casestudy" else "questions"
        if type(group) is not dict or set(group) != {"groupID", "groupName", field} or (
            type(group["groupID"]) is not int or group["groupID"] != groupID
        ):
            raise RelatedError(f"Invalid {kind} group {groupID}")
        if type(group["groupName"]) is not str or not group["groupName"].strip():
            raise RelatedError(f"Missing groupName: {kind} group {groupID}")
        items = group[field]
        if type(items) is not list or not items:
            raise RelatedError(f"Empty {kind} group {groupID}")
        for idx, item in enumerate(items):
            key = (groupID, idx)
            label = f"{kind}[groupID={groupID},index={idx}]"
            if kind == "quiz":
                required = {"index", "question", "readmeRelated", "answers", "correctAnswerId"}
                name = "question"
            elif kind == "interview":
                required = {"index", "question", "knowledge", "answer", "readmeRelated"}
                name = "question"
            else:
                required = {"index", "situation", "resolve", "knowledge", "answer",
                            "readmeRelated"}
                name = "situation"
            if type(item) is not dict or set(item) != required or (
                type(item["index"]) is not int or item["index"] != idx
            ):
                raise RelatedError(f"Invalid item fields/index: {label}")
            if type(item[name]) is not str or not item[name].strip():
                raise RelatedError(f"Missing question/situation: {label}")
            related = item["readmeRelated"]
            if type(related) is not dict or set(related) != {"anchorList"} or (
                type(related["anchorList"]) is not list
            ):
                raise RelatedError(f"Invalid anchorList: {label}")
            anchors = related["anchorList"]
            if any(type(s) is not str or not s.strip() for s in anchors) or (
                len(set(anchors)) != len(anchors)
            ):
                raise RelatedError(f"Invalid/duplicate anchors: {label}")
            if kind == "quiz":
                answers = item["answers"]
                if type(answers) is not list or len(answers) != 4 or (
                    type(item["correctAnswerId"]) is not str or item["correctAnswerId"] not in "ABCD"
                ):
                    raise RelatedError(f"Invalid Quiz answers/correctAnswerId: {label}")
                for answer_id, answer in zip("ABCD", answers):
                    if type(answer) is not dict or set(answer) != {
                        "id", "answer", "explanation"
                    } or answer["id"] != answer_id:
                        raise RelatedError(f"Invalid Quiz choice: {label}")
                    if any(type(answer[f]) is not str or not answer[f].strip()
                           for f in ("answer", "explanation")):
                        raise RelatedError(f"Incomplete Quiz choice: {label}")
            else:
                fields = ("knowledge", "answer") if kind == "interview" else (
                    "resolve", "knowledge", "answer"
                )
                if any(type(item[f]) is not str or not item[f].strip() for f in fields):
                    raise RelatedError(f"Incomplete STEP 5 answer fields: {label}")
            result[key] = item
    return result


def read_assessments(stage: Path) -> tuple[dict, dict, dict]:
    contents, data, items = {}, {}, {}
    for kind in KINDS:
        path = stage / "format" / f"{kind}.yml"
        contents[kind] = read_file(path)
        data[kind] = load_yaml(path)
        items[kind] = validate_assessment(kind, data[kind])
    return contents, data, items


def related_links(stage: Path, catalog: list[dict], items: dict) -> dict:
    """Validated, deterministic chapter-order union; blank files are not completed."""
    root = stage / "readme-related"
    if root.is_symlink() or not root.is_dir():
        raise RelatedError(f"Related staging missing/unsafe: {root}")
    expected_slugs = {chapter["slug"] for chapter in catalog}
    if {x.name for x in root.iterdir()} != expected_slugs:
        raise RelatedError("Related folder inventory differs from Knowledge menu")
    merged = {kind: {key: [] for key in items[kind]} for kind in KINDS}
    for chapter in catalog:
        folder = root / chapter["slug"]
        if folder.is_symlink() or not folder.is_dir() or (
            {x.name for x in folder.iterdir()} != {kind + ".yml" for kind in KINDS}
        ):
            raise RelatedError(f"Related chapter file inventory invalid: {folder}")
        for kind in KINDS:
            path = folder / f"{kind}.yml"
            data = load_yaml(path)
            if type(data) is not dict or set(data) != {"groups"} or (
                type(data["groups"]) is not list
            ):
                raise RelatedError(f"Related proposals must contain groups list: {path}")
            seen = set()
            for group in data["groups"]:
                if type(group) is not dict or set(group) != {"groupID", "items"} or (
                    type(group["groupID"]) is not int or group["groupID"] < 1
                ) or type(group["items"]) is not list or not group["items"]:
                    raise RelatedError(f"Invalid related group at {path}")
                for item in group["items"]:
                    if type(item) is not dict or set(item) != {"index", "readmeRelated"} or (
                        type(item["index"]) is not int or item["index"] < 0
                    ):
                        raise RelatedError(f"Invalid related item at {path}")
                    key = (group["groupID"], item["index"])
                    links = item["readmeRelated"]
                    if key not in items[kind] or key in seen:
                        raise RelatedError(f"Unknown/duplicate related identity {kind}:{key} in {path}")
                    if type(links) is not list or not links or any(
                        type(slug) is not str or slug not in chapter["lessons"]
                        for slug in links
                    ) or len(set(links)) != len(links):
                        raise RelatedError(f"Invalid/non-chapter lesson IDs in {kind}:{key} at {path}")
                    seen.add(key)
                    merged[kind][key].extend(
                        slug for slug in links if slug not in merged[kind][key]
                    )
    return merged
