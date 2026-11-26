#!/usr/bin/env python3
"""Read-only deterministic Prime dispatch snapshot for STEP 5 Phase 1.

Nine workers are partitioned by type and by every third module. Only Prime
executes this helper; Worker receives explicit literal metadata and module root.
The helper never assigns a file with existing unverified content or a FINAL
module. Prime must still check worker ownership and perform independent QA.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCOPE = ROOT / 'module/platform/development/programming'
TYPES = ('quiz', 'interview', 'casestudy')


def load_assess():
    script = Path(__file__).with_name('verify_step5_phase1.py')
    spec = importlib.util.spec_from_file_location('step5_verify', script)
    if spec is None or spec.loader is None:
        raise RuntimeError('Unable to load Phase 1 verifier')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.assess


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', default=DEFAULT_SCOPE.relative_to(ROOT).as_posix())
    parser.add_argument('--worker-ids', default=','.join(f'worker-{i}' for i in range(1, 10)),
                        help='Nine comma-separated worker IDs in their original assignment slots')
    parser.add_argument('--assignment-mode', choices=('cohort', 'balanced'), default='cohort',
                        help='cohort preserves existing ownership; balanced hashes each module/type job into one of nine stable shards (switch only at a quiescent checkpoint)')
    args = parser.parse_args()
    worker_ids = [entry.strip() for entry in args.worker_ids.split(',')]
    if len(worker_ids) != 9 or len(set(worker_ids)) != 9 or any(not x.startswith('worker-') for x in worker_ids):
        parser.error('--worker-ids must specify nine unique worker IDs')
    scope = (ROOT / args.scope).resolve()
    if not scope.is_dir() or not scope.is_relative_to((ROOT / 'module').resolve()):
        parser.error('Scope must be an existing subtree of module/')

    assess = load_assess()
    modules = []
    skipped = []
    for file in sorted(scope.rglob('module-info.json')):
        module = file.parent
        activation = json.loads((module / 'module_activate.json').read_text(encoding='utf-8-sig'))
        if activation.get('isModule') is not True:
            continue
        info = json.loads(file.read_text(encoding='utf-8-sig'))
        location = module.relative_to(ROOT).as_posix()
        if info['CURRENT_STEP']['VALUE'] == 'FINAL':
            skipped.append(location)
            continue
        modules.append({
            'path': module,
            'location': location,
            'name': info['SERVICE_NAME']['VALUE'],
            'description': info['SERVICE_NAME_DESCRIBE']['VALUE'],
            'note': info['SPECIAL_NOTE']['VALUE'],
        })
    jobs = {}
    for module in modules:
        for kind in TYPES:
            jobs[(module['location'], kind)] = assess(module['path'], kind)

    next_jobs = []
    blockers = []
    for number in range(1, 10):
        worker_id = worker_ids[number - 1]
        if args.assignment_mode == 'cohort':
            kind = TYPES[(number - 1) % 3]
            cohort = (number - 1) // 3
            own_jobs = [(module, kind) for i, module in enumerate(modules) if i % 3 == cohort]
        else:
            own_jobs = [
                (module, kind)
                for module in modules
                for kind in TYPES
                if int.from_bytes(hashlib.sha256(
                    (module['location'] + ':' + kind).encode('utf-8')).digest()[:8], 'big') % 9 == number - 1
            ]
        for module, kind in own_jobs:
            record = jobs[(module['location'], kind)]
            if record['pass'] and not record['flags']:
                continue
            issue = {'worker': worker_id, 'location': module['location'],
                     'type': kind, 'count': record['count'], 'status': record['status'],
                     'errors': record['errors'], 'flags': record['flags']}
            if record['count'] or record['status'] not in ('status: Phase 0', ''):
                blockers.append(issue)
            else:
                next_jobs.append({'worker': worker_id, 'type': kind,
                                  'location': module['location'], 'name': module['name'],
                                  'description': module['description'], 'note': module['note']})
            break

    all_records = list(jobs.values())
    result = {
        'scope': scope.relative_to(ROOT).as_posix(),
        'active_modules': len(modules),
        'skipped_final': skipped,
        'total_jobs': len(all_records),
        'qa_pass': sum(bool(r['pass'] and not r['flags']) for r in all_records),
        'qa_by_type': {
            kind: sum(bool(record['pass'] and not record['flags'])
                      for (location, assessment), record in jobs.items() if assessment == kind)
            for kind in TYPES
        },
        'fully_complete_modules': sum(
            all(jobs[(module['location'], kind)]['pass']
                and not jobs[(module['location'], kind)]['flags'] for kind in TYPES)
            for module in modules
        ),
        'items_verified': sum(record['count'] for record in all_records
                              if record['pass'] and not record['flags']),
        'content_nonempty': sum(r['count'] > 0 for r in all_records),
        'phase1_status': sum(r['status'] == 'status: Phase 1' for r in all_records),
        'next_jobs': next_jobs,
        'blockers': blockers,
    }
    print(json.dumps(result, ensure_ascii=True, separators=(',', ':')))


if __name__ == '__main__':
    main()
