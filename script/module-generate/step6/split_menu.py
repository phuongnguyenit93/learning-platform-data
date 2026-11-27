#!/usr/bin/env python3
"""STEP 6: split one module's menu-detail-status.yml into per-chapter work files.

No existing module file is modified. Staging is isolated under
temp/step6/<SERVICE_NAME>/<lang>/ and can be resumed without overwriting work.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

import yaml

from readme_related import (
    KINDS, FINAL_BEFORE_RELATED, RelatedError, chapter_catalog,
    read_assessments, load_yaml, semantic_fingerprint,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "script" / "module-generate" / "step3"))
sys.path.insert(0, str(REPO_ROOT / "script" / "module-generate" / "step4"))

from generate_menu_detail import StrictLoader, Step3Error, CHILD_FIELDS, windows_long_path  # noqa: E402
from _knowledge_local import load_layout, markdown_has_content  # noqa: E402

SERVICE_RE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*\Z")
LANG_RE = re.compile(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*\Z")
STEP6_FIELDS = frozenset(CHILD_FIELDS)
CHILD_KEYS = frozenset(("slug", "title", "status")) | STEP6_FIELDS
STAGING_VERSION = 1


class Step6Error(Exception):
    """Preflight, staging, or merge validation failure."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def regular_file(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise Step6Error(f"Required regular file missing or symlinked: {path}")
    return path.read_bytes()


def load_json(path: Path) -> dict:
    try:
        value = json.loads(regular_file(path).decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise Step6Error(f"Invalid JSON: {path}: {exc}") from exc
    if type(value) is not dict:
        raise Step6Error(f"Expected JSON object: {path}")
    return value


def module_context(module_arg: str, lang: str) -> tuple[Path, str, Path]:
    if lang != "vi":
        raise Step6Error("STEP 6 NEW currently supports only lang=vi for the shared STEP 5 staging")
    if not LANG_RE.fullmatch(lang):
        raise Step6Error(f"Invalid language code: {lang!r}")
    repo = REPO_ROOT.resolve()
    modules = repo / "learning-platform-data" / "module"
    if not modules.is_dir():
        modules = repo / "module"
    requested = Path(module_arg).expanduser()
    if not requested.is_absolute() and requested.parts and requested.parts[0] == "module":
        requested = modules.joinpath(*requested.parts[1:])
    try:
        module = requested.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise Step6Error(f"Module does not exist: {module_arg}") from exc
    modules = modules.resolve()
    if not module.is_dir() or module == modules or not module.is_relative_to(modules):
        raise Step6Error(f"Module must be inside {modules}: {module}")
    activation = load_json(module / "module_activate.json")
    if activation.get("isModule") is not True:
        raise Step6Error(f"Inactive module: {module}")
    metadata = load_json(module / "module-info.json")
    item = metadata.get("SERVICE_NAME")
    service = item.get("VALUE") if type(item) is dict else None
    if type(service) is not str or not SERVICE_RE.fullmatch(service):
        raise Step6Error(f"Invalid SERVICE_NAME.VALUE: {module}")
    languages = metadata.get("MODULE_LANGUAGE")
    enabled = languages.get("VALUE") if type(languages) is dict else None
    if type(enabled) is not list or lang not in enabled:
        raise Step6Error(f"Language {lang} not enabled in module-info.json: {module}")
    stage = repo / "temp" / "step6" / service / lang
    for path in (repo / "temp", stage.parent.parent, stage.parent, stage):
        if path.is_symlink():
            raise Step6Error(f"Symlink is not permitted in staging path: {path}")
    return module, service, stage


def parse_menu(raw: str, *, location: str) -> tuple[list[dict], list[str], str]:
    """Parse strict YAML and return chapters, original raw chapter slices, prefix.

    Split uses raw slices rather than dumping YAML so that comments, quoted
    strings and multiline Summary in each chapter remain byte-for-byte intact.
    """
    try:
        data = yaml.load(raw, Loader=StrictLoader)
        node = yaml.compose(raw, Loader=StrictLoader)
    except (yaml.YAMLError, Step3Error, ValueError) as exc:
        raise Step6Error(f"Invalid YAML at {location}: {exc}") from exc
    if type(data) is not dict or set(data) != {"menu"}:
        raise Step6Error(f"Expected only menu at {location}")
    chapters = data["menu"]
    if type(chapters) is not list or not chapters:
        raise Step6Error(f"Nonempty menu list required at {location}")
    if not isinstance(node, yaml.MappingNode):
        raise Step6Error(f"Invalid menu root at {location}")
    menu_nodes = [
        v for k, v in node.value if isinstance(k, yaml.ScalarNode) and k.value == "menu"
    ]
    if len(menu_nodes) != 1 or not isinstance(menu_nodes[0], yaml.SequenceNode):
        raise Step6Error(f"Expected block list menu at {location}")
    nodes = menu_nodes[0].value
    if len(nodes) != len(chapters):
        raise Step6Error(f"Menu syntax disagrees with chapter count: {location}")
    lines = raw.splitlines(keepends=True)
    starts = [n.start_mark.line for n in nodes]
    if not starts or starts != sorted(set(starts)):
        raise Step6Error(f"Chapters must occupy separate lines: {location}")
    # A child item's dash must appear at column zero, not as an inline list.
    for line in starts:
        if not lines[line].startswith("- "):
            raise Step6Error(f"Expected block-style chapter at {location}:{line + 1}")
    prefix = "".join(lines[:starts[0]])
    if "menu:" not in prefix:
        raise Step6Error(f"Missing menu header: {location}")
    slices = [
        "".join(lines[start:starts[i + 1] if i + 1 < len(starts) else len(lines)])
        for i, start in enumerate(starts)
    ]
    return chapters, slices, prefix


def validate_chapter(chapter: dict, *, number: int) -> None:
    if type(chapter) is not dict or set(chapter) != {"slug", "title", "childs"}:
        raise Step6Error(f"Chapter {number} must contain slug, title, childs only")
    slug, title, children = chapter["slug"], chapter["title"], chapter["childs"]
    if type(slug) is not str or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", slug):
        raise Step6Error(f"Invalid chapter slug at {number}: {slug!r}")
    if type(title) is not str or not title.strip():
        raise Step6Error(f"Invalid chapter title at {number}")
    if type(children) is not list or not children:
        raise Step6Error(f"Chapter {number} has no lessons")
    for i, child in enumerate(children, 1):
        if type(child) is not dict or set(child) != CHILD_KEYS:
            raise Step6Error(
                f"STEP 6 schema invalid in {slug} child {i}: "
                f"expected exactly {sorted(CHILD_KEYS)}"
            )
        if child["slug"] != f"{slug}-{i:03d}":
            raise Step6Error(f"Lesson slug/order mismatch in {slug} child {i}")
        for key in CHILD_KEYS - {"slug"}:
            if type(child[key]) is not str:
                raise Step6Error(f"Expected string for {slug}-{i:03d}.{key}")
        if not child["title"].strip():
            raise Step6Error(f"Empty lesson title in {slug} child {i}")
        if child["difficult"] not in ("", "BASIC", "INTERMEDIATE", "ADVANCED"):
            raise Step6Error(f"Invalid difficulty in {slug} child {i}")


def load_manifest(stage: Path) -> dict:
    return load_json(stage / "manifest.json")


def expected_files(manifest: dict) -> set[str]:
    chapters = manifest.get("chapters")
    if type(chapters) is not list or not chapters:
        raise Step6Error("Invalid staging manifest: chapters")
    return {"manifest.json", *(name for ch in chapters
                               for name in (ch["file"], ch["status_file"]))}


def verify_stage_inventory(stage: Path, manifest: dict, *, merged: bool = False) -> None:
    if stage.is_symlink() or not stage.is_dir():
        raise Step6Error(f"Staging folder missing or unsafe: {stage}")
    expected = expected_files(manifest) | ({"merged.json"} if merged else set())
    actual = {item.name for item in stage.iterdir()}
    if actual != expected:
        raise Step6Error(f"Unexpected/missing staging files in {stage}: "
                         f"missing={sorted(expected - actual)} extra={sorted(actual - expected)}")
    if any(item.is_symlink() or not item.is_file() for item in stage.iterdir()):
        raise Step6Error(f"Staging must contain only regular files: {stage}")


def read_status(path: Path) -> str:
    raw = regular_file(path)
    try:
        value = yaml.load(raw.decode("utf-8-sig"), Loader=StrictLoader)
    except (UnicodeError, ValueError, yaml.YAMLError, Step3Error) as exc:
        raise Step6Error(f"Invalid status YAML at {path}: {exc}") from exc
    if type(value) is not dict or set(value) != {"status"} or (
            type(value["status"]) is not str or value["status"] not in ("", "WRITTEN")):
        raise Step6Error(f"Status must be exactly empty or WRITTEN at {path}")
    return value["status"]


def check_manifest(manifest: dict, module: Path, service: str, lang: str) -> None:
    repo = REPO_ROOT.resolve()
    if manifest.get("version") != STAGING_VERSION or (
        manifest.get("service") != service or manifest.get("lang") != lang or
        manifest.get("module") != module.relative_to(repo).as_posix() or
        manifest.get("source") != (
            module / "content" / "knowledge" / lang / "menu-detail-status.yml"
        ).relative_to(repo).as_posix()
    ):
        raise Step6Error("Staging manifest does not match selected module/language")
    if not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("source_sha256", ""))):
        raise Step6Error("Invalid source checksum in manifest")
    if not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("chapter_menu_sha256", ""))):
        raise Step6Error("Invalid chapter menu checksum")
    hashes = manifest.get("assessments_sha256")
    if type(hashes) is not dict or set(hashes) != set(KINDS) or any(
        not re.fullmatch(r"[0-9a-f]{64}", str(v)) for v in hashes.values()
    ):
        raise Step6Error("Missing/invalid assessment baseline fingerprints")
    fingerprints = manifest.get("assessment_semantic_sha256")
    if type(fingerprints) is not dict or set(fingerprints) != set(KINDS) or any(
        not re.fullmatch(r"[0-9a-f]{64}", str(v)) for v in fingerprints.values()
    ):
        raise Step6Error("Missing assessment semantic fingerprints")
    if not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("source_prefix_sha256", ""))):
        raise Step6Error("Invalid source header checksum in manifest")
    hashes = manifest.get("lesson_info_sha256")
    if type(hashes) is not dict or not hashes or any(
        type(path) is not str or not path.endswith(".yml") or
        not re.fullmatch(r"[0-9a-f]{64}", str(sha))
        for path, sha in hashes.items()
    ):
        raise Step6Error("Invalid lesson YAML checksums in manifest")
    chapters = manifest.get("chapters")
    if type(chapters) is not list or not chapters:
        raise Step6Error("Staging manifest has no chapters")
    for i, info in enumerate(chapters, 1):
        if type(info) is not dict or set(info) != {
            "index", "slug", "title", "child_slugs", "file", "status_file"
        }:
            raise Step6Error(f"Invalid chapter manifest entry #{i}")
        slug = info["slug"]
        if info["index"] != i or type(slug) is not str or not re.fullmatch(
                r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", slug):
            raise Step6Error(f"Invalid chapter manifest index/slug #{i}")
        if (info["file"] != f"{i}-{slug}.yml" or
                info["status_file"] != f"{i}-{slug}-status.yml" or
                type(info["title"]) is not str or type(info["child_slugs"]) is not list):
            raise Step6Error(f"Invalid chapter manifest filenames #{i}")


def split(module_arg: str, *, lang: str = "vi", dry_run: bool = False) -> str:
    module, service, stage = module_context(module_arg, lang)
    repo = REPO_ROOT.resolve()
    # After merge_menu has run, the original menu baseline intentionally differs
    # from the current source. Do not try to re-split/overwrite authored work.
    if stage.is_dir() and (stage / "merged.json").is_file():
        prior = load_manifest(stage)
        check_manifest(prior, module, service, lang)
        verify_stage_inventory(stage, prior, merged=True)
        marker = load_json(stage / "merged.json")
        current_menu = module / "content" / "knowledge" / lang / "menu-detail-status.yml"
        if marker.get("source_sha256") != prior["source_sha256"] or (
            digest(regular_file(current_menu)) != marker.get("merged_sha256")
        ):
            raise Step6Error("Finished STEP 6 staging/source changed unexpectedly")
        if any(read_status(stage / item["status_file"]) != "WRITTEN"
               for item in prior["chapters"]):
            raise Step6Error("Chapter status changed after merge")
        if digest(regular_file(module / "content" / "knowledge" / lang /
                               "menu-level-1-slug.yml")) != prior["chapter_menu_sha256"]:
            raise Step6Error("Chapter catalog changed after merge")
        try:
            _, current_data, _ = read_assessments(module / "content" / "temp" / "step5")
            if any(semantic_fingerprint(kind, current_data[kind]) !=
                   prior["assessment_semantic_sha256"][kind] for kind in KINDS):
                raise Step6Error("Assessments changed after chapter review")
        except RelatedError as exc:
            raise Step6Error(f"Assessment preflight failed: {exc}") from exc
        return f"RESUMED_MERGED stage={stage} chapters={len(prior['chapters'])}"
    assessment_stage = module / "content" / "temp" / "step5"
    try:
        current_assessment_bytes, _assessment_yaml, _items = read_assessments(assessment_stage)
        catalog = chapter_catalog(module, lang)
        menu_source = regular_file(module / "content" / "knowledge" / lang / "menu-level-1-slug.yml")
        for kind in KINDS:
            status = load_yaml(assessment_stage / "status" / f"{kind}.yml")
            if type(status) is not dict or set(status) != {"status"} or (
                status["status"] != f"Phase {FINAL_BEFORE_RELATED[kind]}"
            ):
                raise Step6Error(f"STEP 5 {kind} not completed before STEP 6")
        related_dir = assessment_stage / "readme-related"
        if related_dir.is_symlink() or not related_dir.is_dir() or (
            {p.name for p in related_dir.iterdir()} != {chapter["slug"] for chapter in catalog}
        ):
            raise Step6Error("STEP 5 related chapter inventory missing/changed")
        for chapter in catalog:
            folder = related_dir / chapter["slug"]
            if folder.is_symlink() or not folder.is_dir() or (
                {p.name for p in folder.iterdir()} != {kind + ".yml" for kind in KINDS}
            ):
                raise Step6Error(f"Missing three related files for {chapter['slug']}")
            for kind in KINDS:
                regular_file(folder / f"{kind}.yml")
    except (RelatedError, OSError) as exc:
        raise Step6Error(f"STEP 5 preflight failed: {exc}") from exc
    try:
        layout = load_layout(module, lang=lang)
    except (Step3Error, OSError, UnicodeError) as exc:
        raise Step6Error(f"Knowledge layout invalid: {exc}") from exc
    for lesson in layout.lessons:
        if lesson.info["status"] != "WRITTEN" or not markdown_has_content(lesson.markdown_path):
            raise Step6Error(f"STEP 4 must finish every lesson before splitting: {lesson.slug}")
        child = layout.detail["menu"][lesson.chapter_index]["childs"][lesson.lesson_index]
        if child["status"] != "WRITTEN":
            raise Step6Error(f"Consolidated status differs from STEP 4: {lesson.slug}")

    source_bytes = regular_file(layout.detail_path)
    try:
        raw = source_bytes.decode("utf-8-sig")
    except UnicodeError as exc:
        raise Step6Error(f"Invalid UTF-8 source: {layout.detail_path}") from exc
    chapters, chapter_slices, prefix = parse_menu(raw, location=str(layout.detail_path))
    entries = []
    for i, chapter in enumerate(chapters, 1):
        validate_chapter(chapter, number=i)
        slug = chapter["slug"]
        if catalog[i - 1]["slug"] != slug or catalog[i - 1]["title"] != chapter["title"]:
            raise Step6Error(f"Chapter/menu mismatch #{i}: {slug}")
        entries.append({
            "index": i, "slug": slug, "title": chapter["title"],
            "child_slugs": [child["slug"] for child in chapter["childs"]],
            "file": f"{i}-{slug}.yml", "status_file": f"{i}-{slug}-status.yml",
        })
    manifest = {
        "version": STAGING_VERSION, "service": service, "lang": lang,
        "module": module.relative_to(repo).as_posix(),
        "source": layout.detail_path.relative_to(windows_long_path(repo)).as_posix(),
        "source_sha256": digest(source_bytes), "chapters": entries,
        "chapter_menu_sha256": digest(menu_source),
        "assessments_sha256": {
            kind: digest(current_assessment_bytes[kind]) for kind in KINDS
        },
        "assessment_semantic_sha256": {
            kind: semantic_fingerprint(kind, _assessment_yaml[kind]) for kind in KINDS
        },
        "source_prefix_sha256": digest(prefix.encode("utf-8")),
        "lesson_info_sha256": {
            lesson.info_path.relative_to(windows_long_path(repo)).as_posix(): digest(regular_file(lesson.info_path))
            for lesson in layout.lessons
        },
    }

    if stage.exists() or stage.is_symlink():
        previous = load_manifest(stage)
        check_manifest(previous, module, service, lang)
        if previous != manifest:
            raise Step6Error(f"Staging already exists for a different source: {stage}")
        verify_stage_inventory(stage, manifest, merged=(stage / "merged.json").exists())
        counts = {"WRITTEN": 0, "PENDING": 0}
        for info in entries:
            data = regular_file(stage / info["file"]).decode("utf-8-sig")
            staged, _, _ = parse_menu(data, location=info["file"])
            if len(staged) != 1 or staged[0]["slug"] != info["slug"]:
                raise Step6Error(f"Incorrect staged chapter: {info['file']}")
            counts["WRITTEN" if read_status(stage / info["status_file"]) else "PENDING"] += 1
        return f"RESUMED stage={stage} chapters={len(entries)} " + " ".join(
            f"{key}={count}" for key, count in counts.items()
        )

    if dry_run:
        return f"DRY_RUN stage={stage} chapters={len(entries)} lessons={len(layout.lessons)}"

    parent = stage.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{lang}-split-", dir=parent))
    try:
        for entry, content in zip(entries, chapter_slices):
            (temporary / entry["file"]).write_text("menu:\n" + content, encoding="utf-8", newline="")
            (temporary / entry["status_file"]).write_text('status: ""\n', encoding="utf-8", newline="")
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if regular_file(layout.detail_path) != source_bytes:
            raise Step6Error("Source changed during split; staging not published")
        temporary.rename(stage)  # Never overwrite another staging directory.
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return f"SPLIT_OK stage={stage} chapters={len(entries)} lessons={len(layout.lessons)}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", required=True, help="Module folder under java-learning/module")
    parser.add_argument("--lang", default="vi", help="Knowledge language (default: vi)")
    parser.add_argument("--dry-run", action="store_true", help="Validate only; do not create staging")
    args = parser.parse_args()
    try:
        print(split(args.module, lang=args.lang, dry_run=args.dry_run))
        return 0
    except (Step6Error, OSError, ValueError) as exc:
        print(f"BLOCKER: STEP6_SPLIT: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
