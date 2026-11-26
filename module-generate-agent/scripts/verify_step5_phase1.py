#!/usr/bin/env python3
"""Read-only structural QA for STEP 5 NEW Phase 1 in a selected module subtree.

Usage:
  python module-generate-agent/scripts/verify_step5_phase1.py --module module/integration/api/graphql --type quiz
  python module-generate-agent/scripts/verify_step5_phase1.py --all --json

The script does not claim semantic/expert QA. It never writes any file.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
TYPES = ('quiz', 'interview', 'casestudy')
ANSWER = re.compile(r'^Đáp án đúng:\s*([ABCD])$')
OPTION = [re.compile(rf'^{letter}\.\s*(\S.*)$') for letter in 'ABCD']


def assess(module: Path, kind: str) -> dict:
    result = {'module': module.relative_to(ROOT).as_posix(), 'type': kind, 'status': '',
              'count': 0, 'errors': [], 'flags': [], 'pass': False}
    stage = module / 'content/temp/step5'
    raw_file, status_file = stage/'raw'/f'{kind}.md', stage/'status'/f'{kind}.yml'
    if not raw_file.is_file():
        result['errors'].append('MISSING_RAW')
        return result
    if raw_file.is_symlink():
        result['errors'].append('RAW_SYMLINK')
        return result
    try:
        raw = raw_file.read_text(encoding='utf-8-sig')
        result['status'] = status_file.read_text(encoding='utf-8-sig').strip()
    except (UnicodeError, OSError) as exc:
        result['errors'].append('READ_ERROR:' + str(exc))
        return result
    if not raw.strip():
        result['errors'].append('EMPTY_RAW')
        return result
    if result['status'] != 'status: Phase 1':
        result['errors'].append('NOT_PHASE_1')
    if kind == 'quiz':
        blocks = re.split(r'\r?\n\s*\r?\n+', raw.strip())
        result['count'] = len(blocks)
        questions, corrects = [], []
        longest_right = 0
        for i, block in enumerate(blocks, start=1):
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if len(lines) != 6:
                result['errors'].append(f'QUIZ_{i}_LINES_{len(lines)}')
                continue
            question = lines[0]
            if '?' not in question:
                result['errors'].append(f'QUIZ_{i}_NOT_QUESTION')
            questions.append(question.casefold())
            options = []
            for k in range(4):
                match = OPTION[k].fullmatch(lines[k+1])
                if match is None:
                    result['errors'].append(f'QUIZ_{i}_BAD_OPTION_{k}')
                options.append(match.group(1) if match else '')
            ans = ANSWER.fullmatch(lines[-1])
            if not ans:
                result['errors'].append(f'QUIZ_{i}_BAD_ANSWER')
                continue
            right = ans.group(1)
            corrects.append(right)
            sizes = [len(opt) for opt in options]
            if len(set(opt.casefold().strip() for opt in options)) != 4:
                result['errors'].append(f'QUIZ_{i}_DUPLICATE_OPTIONS')
            if min(sizes) and max(sizes)/min(sizes) > 1.5:
                result['flags'].append(f'QUIZ_{i}_OPTION_LENGTH_1_5')
            if sizes[ord(right)-65] == max(sizes):
                longest_right += 1
        if len(set(questions)) != len(questions):
            result['errors'].append('QUIZ_DUPLICATE_QUESTIONS')
        if len(corrects) >= 4:
            counts = Counter(corrects)
            result['answer_counts'] = {x: counts[x] for x in 'ABCD'}
            if max(counts[x] for x in 'ABCD')-min(counts[x] for x in 'ABCD')>1:
                result['errors'].append('QUIZ_UNBALANCED_ANSWERS')
            if any(corrects[i] == corrects[i+1] == corrects[i+2]
                   for i in range(len(corrects)-2)):
                result['errors'].append('QUIZ_TRIPLE_REPEAT')
            if len(corrects) >= 12 and all(corrects[i] == corrects[i%4]
                                          for i in range(len(corrects))):
                result['flags'].append('QUIZ_PERIODIC_4_PATTERN')
            # A deceptively subtle answer leak: each consecutive block of
            # four questions has A/B/C/D exactly once, even though the order
            # within each block varies and global letter counts look ideal.
            # The final item of a block can be guessed by elimination.
            quartets = [corrects[i:i+4] for i in range(0, len(corrects)-3, 4)]
            if len(quartets) >= 4:
                balanced_quartets = sum(set(block) == set('ABCD') for block in quartets)
                if balanced_quartets / len(quartets) >= 0.75:
                    result['flags'].append(
                        f'QUIZ_PREDICTABLE_QUARTETS_{balanced_quartets}_OF_{len(quartets)}'
                    )
        if len(corrects) >= 10 and longest_right/len(corrects) > 0.4:
            result['flags'].append('QUIZ_RIGHT_OPTION_LONGEST_OVER_40_PERCENT')
    else:
        lines = [line.strip() for line in raw.splitlines()]
        result['count'] = len(lines)
        if any(not line for line in lines):
            result['errors'].append('BLANK_LINE')
        if len(set(line.casefold() for line in lines)) != len(lines):
            result['errors'].append('DUPLICATE_LINE')
        if kind == 'interview' and any(not line.endswith('?') for line in lines):
            result['errors'].append('INTERVIEW_NOT_QUESTION')
        if any(line.startswith(('```', '### ', '# ')) for line in lines):
            result['errors'].append('RAW_HAS_GROUP_OR_CODE_HEADER')
    result['pass'] = not result['errors']
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--module')
    choice.add_argument('--all', action='store_true')
    parser.add_argument('--scope', default='module/integration',
                        help='Repository-relative subtree for --all, default module/integration')
    parser.add_argument('--type', choices=TYPES)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if args.module:
        target = ROOT / args.module
        if not target.is_dir() or not target.resolve().is_relative_to((ROOT/'module').resolve()):
            parser.error('Module must belong to module tree')
        modules = [target]
    else:
        scope = (ROOT / args.scope).resolve()
        if not scope.is_dir() or not scope.is_relative_to((ROOT/'module').resolve()):
            parser.error('Scope must belong to module tree')
        modules = []
        for activation in sorted(scope.rglob('module_activate.json')):
            module_root = activation.parent
            enabled = json.loads(activation.read_text(encoding='utf-8-sig')).get('isModule')
            if enabled is not True:
                continue
            metadata = json.loads((module_root / 'module-info.json').read_text(encoding='utf-8-sig'))
            if metadata['CURRENT_STEP']['VALUE'] == 'FINAL':
                continue
            modules.append(module_root)
        if not modules:
            parser.error('No active modules found in scope')
    results = [assess(module, kind) for module in modules for kind in (args.type,) if args.type] if args.type else [assess(module, kind) for module in modules for kind in TYPES]
    if args.json:
        print(json.dumps(results, ensure_ascii=True, separators=(',', ':')))
    else:
        for entry in results:
            print(f"{entry['module']}/{entry['type']}: count={entry['count']} status={entry['status']} errors={entry['errors']} flags={entry['flags']}")
    return 0 if all(entry['pass'] for entry in results) else 2


if __name__ == '__main__':
    sys.exit(main())
