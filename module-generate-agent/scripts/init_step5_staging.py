#!/usr/bin/env python3
"""Initialize STEP 5 NEW staging for enabled modules in a selected subtree, without overwrite.

This local workflow helper is used because the parent java-learning Python
initializer is not available from this workspace. Only creates missing files
and directories; never edits an existing file or any module metadata.

Usage (from learning-platform-data):
  python module-generate-agent/scripts/init_step5_staging.py --scope module/platform/development/programming --dry-run
  python module-generate-agent/scripts/init_step5_staging.py --scope module/platform/development/programming --apply
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
TYPES = ('quiz', 'interview', 'casestudy')
MENU_SLUG = re.compile(r"""^\s*slug:\s*(?:"([a-z0-9-]+)"|'([a-z0-9-]+)'|([a-z0-9-]+))\s*$""")
MENU_INDEX = re.compile(r'^\s*index:\s*(\d+)\s*$')


def ensure_within_root(path: Path) -> None:
    path.relative_to(ROOT)
    cursor = ROOT
    for segment in path.relative_to(ROOT).parts:
        cursor = cursor / segment
        if cursor.is_symlink():
            raise ValueError(f'Symlink in target path: {cursor}')


def candidates(scope: Path) -> list[tuple[str, list[tuple[Path, bytes]]]]:
    targets: list[tuple[str, list[tuple[Path, bytes]]]] = []
    for activation in sorted(scope.rglob('module_activate.json')):
        module = activation.parent
        location = module.relative_to(ROOT).as_posix()
        ensure_within_root(activation)
        active = json.loads(activation.read_text(encoding='utf-8-sig'))
        if active.get('isModule') is not True:
            continue
        info = json.loads((module / 'module-info.json').read_text(encoding='utf-8-sig'))
        if 'vi' not in info['MODULE_LANGUAGE']['VALUE']:
            raise ValueError(f'VI missing: {location}')
        if info['CURRENT_STEP']['VALUE'] == 'FINAL':
            print(f'SKIP_FINAL {location}')
            continue
        if int(info['CURRENT_STEP']['VALUE']) < 3:
            raise ValueError(f'STEP 3 not done: {location}')
        for field in ('SERVICE_NAME', 'SERVICE_NAME_DESCRIBE', 'SPECIAL_NOTE'):
            if not isinstance(info[field]['VALUE'], str):
                raise ValueError(f'Invalid metadata {field}: {location}')
        menu = module / 'content' / 'knowledge' / 'vi' / 'menu-level-1-slug.yml'
        text = menu.read_text(encoding='utf-8-sig')
        slugs = [next(group for group in m.groups() if group is not None)
                 for line in text.splitlines() if (m := MENU_SLUG.match(line))]
        indices = [int(m.group(1)) for line in text.splitlines() if (m := MENU_INDEX.match(line))]
        if not slugs or len(slugs) != len(indices) or len(set(slugs)) != len(slugs):
            raise ValueError(f'Invalid menu/slug count: {location}')
        if indices != list(range(len(indices))):
            raise ValueError(f'Invalid menu index sequence: {location}')
        stage = module / 'content' / 'temp' / 'step5'
        planned: list[tuple[Path, bytes]] = []
        for kind in TYPES:
            planned.append((stage / 'raw' / (kind + '.md'), b''))
            planned.append((stage / 'format' / (kind + '.yml'), b''))
            planned.append((stage / 'status' / (kind + '.yml'), b'status: Phase 0\n'))
        # A menu chapter may also be named 'overview'. The same empty scaffold
        # path is created only once; future STEP 6 Related identity needs review.
        for chapter in dict.fromkeys(['overview', *slugs]):
            for kind in TYPES:
                planned.append((stage / 'readme-related' / chapter / (kind + '.yml'), b''))
        for path, _ in planned:
            ensure_within_root(path)
        if stage.exists():
            # A prior run may have authored content. Never reset it.
            for path, default in planned:
                if path.exists():
                    if not path.is_file():
                        raise ValueError(f'Expected file: {path}')
                    if '/status/' in path.as_posix():
                        value = path.read_text(encoding='utf-8-sig').strip()
                        if not re.fullmatch(r'status: Phase [0-5]', value):
                            raise ValueError(f'Unexpected status in {path}: {value!r}')
            allowed = {path for path, _ in planned}
            extras = [p for p in stage.rglob('*') if p.is_file() and p not in allowed]
            if extras:
                raise ValueError(f'Unexpected file under STEP 5 staging: {extras[0]}')
        targets.append((location, planned))
    return targets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true')
    group.add_argument('--apply', action='store_true')
    parser.add_argument('--scope', default='module/integration',
                        help='Repository-relative module subtree; default module/integration')
    options = parser.parse_args()
    try:
        scope = (ROOT / options.scope).resolve()
        if not scope.is_dir() or not scope.is_relative_to(ROOT / 'module'):
            raise ValueError(f'Invalid module subtree: {scope}')
        if (ROOT / options.scope).is_symlink():
            raise ValueError(f'Symlink module subtree: {scope}')
        modules = candidates(scope)  # Validate *all* modules before creating files.
        if not modules:
            raise ValueError(f'No active modules found: {scope}')
        total = 0
        for location, planned in modules:
            missing = [p for p, _ in planned if not p.exists()]
            total += len(missing)
            if options.apply:
                for path, content in planned:
                    if path.exists():
                        continue
                    path.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        with path.open('xb') as stream:
                            stream.write(content)
                    except FileExistsError:
                        # Another initializer/worker may be racing; stop safely.
                        raise ValueError(f'File appeared during initialization: {path}')
            print(f'{location}: missing={len(missing)}, total={len(planned)}')
        print(f'{"APPLY" if options.apply else "DRY_RUN"}_PASS modules={len(modules)} newly_created={total}')
        return 0
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        print(f'BLOCKER: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
