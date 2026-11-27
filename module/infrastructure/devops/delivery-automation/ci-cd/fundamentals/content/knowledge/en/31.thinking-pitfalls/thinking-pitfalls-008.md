# Assuming Rolling Back the Application Safely Rolls Back Data Too

## 1. How Does This Misconception Arise?

When a new release causes failures, the common reflex is to revert the application to its previous version. The team selects the old image, runs the deploy or rollback command, sees pods running, and assumes the system has returned to a safe state.

That assumption ignores one critical reality: **applications and data have different change lifecycles**. Moving a binary from version `N+1` back to `N` only changes the running code. The database may have been migrated, data may have been written in a new format, queues may hold new events, and external systems may already have executed side effects.

For example, version `N+1` adds a `REFUNDED` status for orders. After several orders are refunded, the team redeploys `N` because a bug is found on a reporting screen. Binary `N` only understands `PENDING`, `PAID`, and `CANCELLED`. The application might start normally yet throw errors when reading refunded orders, or worse, mis-map the status and display wrong financial numbers.

A successful rollback at the deployment layer does not prove data remains compatible with old code. You must separately verify read paths, write paths, and preservation of business semantics.

In the **DEVOPS_CI_CD_FUNDAMENTALS** module, rollback is part of a traceable release flow covering artifact management, environments, quality gates, and post-deployment verification. The right mindset must include the data state that the new release produced.

## 2. Separating Actions Commonly Lumped Together as "Rollback"

The word rollback is often used for very different operations:

| Operation | What Actually Changes | What Is Not Automatically Restored |
|---|---|---|
| Application rollback | Running image, binary, or code version | Schema and already-written data |
| Configuration rollback | Config or feature flags | Side effects already triggered |
| Infrastructure rollback | Manifest, chart, or resource version | Persistent data and external state |
| Down migration | Schema reverted to prior structure | Deleted data or lost information |
| Database restore | Database reverted to a recovery point | Transactions after that point and external system state |
| Compensation | Creating compensating transactions to fix business impact | Does not necessarily erase the original action history |
| Roll-forward | Releasing a fix forward to a valid state | Does not restore old code |

These operations can be coordinated in a recovery plan, but they cannot be treated as a single command. Runbooks must specify each state to change, execution order, and verification evidence.

## 3. Why Might Old Code Fail to Read New Data?

Applications routinely encode assumptions about schema and data:

- Which columns exist and whether they can be NULL.
- Valid enum values or status sets.
- Data types, measurement units, and timezones.
- Field names and JSON structure.
- Table relationships, keys, and uniqueness rules.
- Event versions that consumers can decode.
- Serialized session or cache structures.
- Allowed sequences of business state transitions.

A new version can alter any of these assumptions. The database stays up and health checks stay green, yet old code may misread values or write data that violates invariants.

Distinguish three failure modes:

1. **Structural errors:** queries reference a dropped column or new constraints block writes.
2. **Representation errors:** new enums, JSON, serialization, or data types cause old parsers to fail.
3. **Semantic errors:** old code reads the value without error yet misinterprets its meaning, such as mixing up currency units or payment statuses.

Semantic errors are harder to catch because they do not necessarily throw exceptions. A system can return HTTP 200 while miscalculating totals or displaying wrong order statuses.

## 4. One Release Changes Multiple States Simultaneously

Consider a release consisting of these steps:

~~~mermaid
flowchart TD
    A["N running with schema S"] --> B["Migration expands schema"]
    B --> C["Deploy N+1"]
    C --> D["N+1 writes data in new format"]
    D --> E["Backfill and shift traffic"]
    E --> F["Drop old structure"]
    F --> G["Incident: request to revert to N"]
~~~

If an incident happens right after step C, the schema may still be compatible and no new data exists yet. Rolling back to `N` may be straightforward.

If an incident happens after step D or E, new data may already exist. If step F has completed, the old schema may be gone. The exact same command to deploy version `N` carries vastly different safety levels depending on where in the release lifecycle it runs.

Therefore, rollback decisions must rely on the actual state of migrations, writers, data, and consumers, not just the application version number.

## 5. Compatibility Matrix Between Application Versions and Schemas

Before releasing, know which version can run against which schema state.

| Application | Old Schema | Expanded Schema | Contracted Schema |
|---|---|---|---|
| `N` | Compatible | May be compatible if purely additive and `N` ignores additions | Usually incompatible if `N` requires removed structures |
| `N+1` | May be compatible if supporting both | Target compatible | Compatible once code drops dependency on old structures |

This matrix only covers schema. You also need a data matrix:

| Existing Data | Can `N` Read It? | Can `N+1` Read It? | What to Verify |
|---|---|---|---|
| Old values | Yes, per old contract | Must be readable | Migration and mapping |
| New values | Possibly not | Must be readable | Enums, parsers, semantics |
| Backfilled records | May only read old representation | Must be readable | Reconcile both representations |
| New events in queue | Possibly not | Must be readable | Consumer compatibility |
| New sessions/cache | Possibly not | Must be readable | Serializers and cache versions |

Do not mark a release rollback-safe merely because the schema still contains old columns. You need proof that data written by `N+1` can still be read and written correctly by `N`.

## 6. Changes That Easily Break Rollbacks

### 6.1. Dropping or Renaming Columns

If `N` queries `status_text` and `N+1`'s migration already ran `DROP` on that column, `N` can fail immediately on query execution. Adding new columns first and keeping old columns across a compatibility window prevents this situation.

### 6.2. Adding New Enums or Statuses

`N` might use a closed enum parsed straight from the database. A new value like `REFUNDED` can throw an exception. If there is a default branch, verify whether it preserves business correctness or silently masks errors.

### 6.3. Changing Types or Units

Switching currency from minor units to major units, changing timezones, altering precision, or changing ID encoding can cause old code to miscalculate even when queries execute fine.

### 6.4. Changing JSON or Serialized Objects

`N` may reject new fields, fail on new types, or require removed fields. Java native serialization can also break on class names and `serialVersionUID`.

### 6.5. Changing Relationships and Constraints

If `N+1` moves data to a new table and stops updating the old table, `N` can read stale data. New constraints can also cause `N`'s `INSERT`/`UPDATE` statements to fail.

### 6.6. New Events and Messages

Rolling back a producer does not delete already-published messages. Consumer `N` can receive new-version events from the queue and fail deserialization. Account for backlogs, retry queues, and dead-letter queues.

### 6.7. Caches and Sessions

Caches can hold new payloads that `N` cannot parse. Active user sessions may break when `N` deserializes them. Flushing a cache is only safe if it holds regenerable derived data and user impact is understood.

## 7. Expand-Contract Preserves the Ability to Run Old Versions

A common strategy is expand-contract:

1. **Expand:** add new columns, tables, or fields without removing old structures.
2. **Deploy compatible code:** deploy a version that understands both old and new states.
3. **Backfill:** migrate data in batches with checkpoints and reconciliation.
4. **Switch:** move readers/writers to the new structure.
5. **Compatibility window:** retain old structures and data long enough to permit rollback.
6. **Contract:** remove old structures only after confirming no consumer still depends on them.

~~~mermaid
flowchart TD
    A["Old schema"] --> B["Expand: add new structure"]
    B --> C["Deploy compatible code"]
    C --> D["Backfill and reconcile"]
    D --> E["Switch to new structure"]
    E --> F["Maintain rollback window"]
    F --> G{"Still need to run N?"}
    G -- "Yes" --> H["Keep schema and data compatible"]
    G -- "No" --> I["Contract in a separate release"]
~~~

Expand-contract does not automatically guarantee rollback. New code can still write values old code does not understand. Schema strategy must be combined with data, event, and feature-flag strategies.

## 8. Safer Migration Example

Suppose the `orders` table has a `legacy_status` column and we want to move to `normalized_status`.

The expand step can add a nullable column:

~~~sql
ALTER TABLE orders
ADD COLUMN normalized_status VARCHAR(40);
~~~

A compatible version can read `normalized_status` when populated and fall back to `legacy_status` during the transition. Writers must update both representations under a consistent rule.

Then backfill in batches:

~~~sql
UPDATE orders
SET normalized_status = map_legacy_status(legacy_status)
WHERE normalized_status IS NULL;
~~~

This is illustrative SQL; the mapping function must be defined, tested, and explicitly handle unmappable values. Never run one massive `UPDATE` on a large table if it can cause locks, long transactions, or excessive database load.

After reconciling row counts and semantics, the new version can switch to reading the new column. The old column is only dropped in a separate release after the rollback window closes and no consumers depend on it.

## 9. Dual-Write Is Not an Automatic Guarantee

Dual-write is often used to maintain two representations during transition. However, if updating both places does not happen inside one transaction or if multiple writers exist, the two copies can diverge.

Examples of commonly missed writers:

- Main API.
- Queue workers.
- Nightly batch jobs.
- Admin tools.
- Integrations from other systems.
- Manual operational scripts.

If one writer only updates `normalized_status`, version `N` may read stale `legacy_status`. Inventory every writer, test all write paths, measure mismatches, and run reconciliation.

Across two independent storage systems, never assume two writes will always succeed together. Consider transactional outbox, CDC, idempotent retries, and designating a single authoritative source of truth for each phase.

## 10. Feature Flags Only Control New Data

Feature flags can prevent `N+1` from generating new values while the team needs to preserve rollback capability. For instance, new code is deployed with the `REFUNDED` status turned off.

However, disabling the flag does not delete existing `REFUNDED` records. Nor does it automatically convert data back to old formats, purge events from queues, or reverse completed payments.

Distinguish between:

- **Disable future writes:** stop generating additional new data.
- **Compatibility conversion:** transform or provide an adapter so old code understands existing data.
- **Compensation:** remediate business impact in external systems.
- **Rollback application:** bring back old code once compatibility criteria are met.

A feature flag is a rollout control tool, not a data undo button.

## 11. Down Migrations Do Not Equal Data Recovery

A down migration can recreate column names or table structures, yet it cannot necessarily restore lost data.

Examples:

- Two new statuses were merged into one old status.
- An old column was dropped after data migrated.
- Precision was rounded away.
- A JSON field was stripped.
- Records were consolidated.
- Keys or relationships changed.

If a transformation is lossy, a down migration cannot reconstruct original data. Running a reverse migration can fabricate synthetic values or corrupt business records.

Only use down migrations when the transformation is proven reversible and data generated under the new version still falls within valid constraints of the old schema. For destructive or irreversible changes, keeping the expanded schema and rolling forward is usually safer.

## 12. Database Restore Is Not a Routine Rollback Button

A restore or point-in-time recovery (PITR) rewinds the database to a past timestamp. That can wipe out valid transactions recorded after the recovery point.

Before restoring, determine:

- The exact timestamp or recovery point.
- Which post-point transactions could be lost.
- Which external systems already received side effects from data after that point.
- Whether queues and consumers must be paused or replayed.
- Whether valid transactions can be reconciled and reconstructed.
- RPO/RTO targets and the authorized approver.

Never restore a production database merely to make old code run without a plan to preserve newer transactions. You may need to restore into a temporary environment to extract data or verify state, then choose roll-forward/compensation for production.

Backups are a disaster-recovery capability, not a substitute for application rollback.

## 13. External Side Effects Do Not Vanish on Their Own

A new version may already have:

- Captured or refunded payments.
- Sent emails/SMS.
- Dispatched webhooks or messages.
- Provisioned cloud resources.
- Exported files to partners.
- Triggered accounting or fulfillment workflows.

Reverting the old binary does not undo those actions. You need business-appropriate compensation workflows, idempotency keys, and state reconciliation with providers.

For instance, if a payment provider has already captured funds, do not delete the transaction record just to stop old code from erroring. Invoke the refund API via business workflow, record the outcome, and retain correlation IDs for traceability.

## 14. Choosing Rollback or Roll-Forward?

Rollback is not always the safest option. Evaluate failure type, data state, and compatibility.

| Scenario | Typically Suitable Action |
|---|---|
| Bug is purely in code; schema and data remain compatible | Binary rollback |
| Schema only expanded; no incompatible new values written | Rollback after compatibility check |
| New data already written and old code cannot understand it | Stop new writes, apply adapter, or roll-forward |
| Old schema already contracted | Controlled recreate/restore or roll-forward; never swap binary alone |
| Lossy data transformation | Roll-forward or compensation |
| External side effects already occurred | Compensation and reconciliation |
| Unknown how migrations or data changed | Halt automated actions; gather evidence first |

Decisions must weigh user impact, data correctness, recovery time, and risk of making things worse. A forward patch can restore service faster and safer than forcing an old version to process new data.

## 15. Pre-Rollback Decision Workflow

Before redeploying an older version:

1. Identify the old artifact by version and digest; never rebuild an approximate binary.
2. Record the current release ID, commit, schema version, and executed migrations.
3. Determine when `N+1` started writing new data.
4. Check enums, JSON, data types, semantics, and relationships.
5. List APIs, workers, batch jobs, and consumers that might continue writing.
6. Inspect queue backlogs, caches, sessions, and external side effects.
7. Run binary `N` against a schema and fixtures representing data created by `N+1`.
8. Verify both read paths and write paths along with business invariants.
9. Choose rollback, adapter, compensation, or roll-forward.
10. Document approver, rationale, scope, evidence, and verification plan.

Never test old binaries directly on production data without isolating side effects. Use a protected data copy or a production-like rehearsal environment.

## 16. Executing a Controlled Rollback

Once compatibility evidence is in place:

1. Stop or throttle writers producing incompatible new data.
2. Pause workers/consumers if they might process new messages with old code.
3. Snapshot current database and release state.
4. Deploy the verified old artifact.
5. Keep the expanded schema if old code can safely ignore new structures.
6. Run health checks and smoke tests on critical business flows.
7. Inspect message backlogs, caches, sessions, and external side effects.
8. Reconcile data invariants.
9. Re-open traffic and workers step-by-step.
10. Monitor error rates, latency, mismatches, and retries post-switch.

Never automatically run down migrations alongside swapping binaries. Schema migration is a separate decision requiring evaluation of reversibility and data impact.

## 17. Post-Rollback Verification

A healthy deployment status does not mean data is right.

Verify at minimum:

- Running artifact digest matches the selected version.
- Old version's queries do not reference missing structures.
- No spike in enum parse or deserialization errors.
- New records created by `N+1` still read accurately.
- Old writers do not drop fields or violate invariants.
- Business counts and aggregates match expectations.
- Workers and consumers drain the backlog cleanly.
- No duplicate side effects are emitted.
- Caches/sessions are read or rebuilt safely.
- SLIs/SLOs and error budgets return to acceptable levels.

Compare before/after rollback and save evidence by release ID. If HTTP errors drop while bad transactions or mismatches climb, the system has not recovered.

## 18. Testing Rollback Compatibility Before Release

Do not wait for a production incident to discover whether the old binary still works.

A useful test matrix:

| Test | Input | Expected Result |
|---|---|---|
| `N` + expanded schema | Schema with only new structures added | `N` still functions |
| `N` + data written by `N+1` | Fixtures with new enums/JSON/formats | `N` reads accurately or rejects safely per policy |
| `N` write path | `N` writes to expanded schema | Does not corrupt new data |
| Old consumer + new event | Messages emitted by `N+1` | Consumer decodes or isolates cleanly |
| Partial backfill | Only subset of records converted | No data loss |
| Retry/replay | Re-delivered messages | Does not duplicate side effects |
| Rollback rehearsal | Old binary, schema, and target config | Runbook completes within RTO |

Run the actual old binary against the target database engine/version. Unit tests mocking enum parsers do not substitute for integration tests using realistic schemas and data.

## 19. Put Rollback Compatibility into CI/CD Gates

Pipelines can test running the previous version against data states the new release might create.

~~~mermaid
flowchart TD
    A["Pull request and migration"] --> B["Schema compatibility test"]
    A --> C["Data mapping/semantics test"]
    A --> D["Event contract test"]
    B --> E["Build artifact N+1"]
    C --> E
    D --> E
    E --> F["Generate fixtures from N+1 format"]
    F --> G["Run binary N on new schema and fixtures"]
    G --> H{"Does N read/write safely?"}
    H -- "No" --> I["Block rollback claim or require forward recovery plan"]
    H -- "Yes" --> J["Save compatibility evidence"]
    J --> K["Allow release per policy"]
~~~

A compatibility report can record:

- Artifact digests of `N` and `N+1`.
- Database migration versions.
- Schema fingerprint.
- Fixture/data format version.
- Read/write test results for `N`.
- Event schemas and consumer versions.
- Known rollback limitations.
- Roll-forward plan if incompatible.

If tests fail, the release may still be considered under a different policy, but it must explicitly declare that rollback to `N` is not guaranteed and provide a reviewed alternative recovery plan.

## 20. Managing Rollback Windows and Old Artifacts

A rollback window is the duration an organization commits to being able to restore the previous version via a verified process.

This duration should reflect:

- Defect detection cycles.
- Queue message retention lifetimes.
- Infrequent batch or reporting schedules.
- Canary/production observation periods.
- Artifact support lifecycles.
- Time needed to investigate security findings.

Keep old artifacts immutable by digest. Store release manifests, schema/migration versions, required configs, and compatibility test results. Never rely on mutable tags or rebuilding old source months later.

Expiration of the rollback window does not mean the system is unrecoverable. It means reverting to the prior binary is no longer guaranteed safe; recovery then relies on rehearsed roll-forward, backup/PITR, or compensation.

## 21. Real-World Example: The `REFUNDED` Status

Suppose `N` only knows `PENDING`, `PAID`, and `CANCELLED`. `N+1` adds `REFUNDED` after successful refunds.

If `N+1` has a bug and the team rolls back to `N`:

- The database still returns order rows.
- `N`'s enum parser may throw an exception.
- APIs reading refunded orders may return 500.
- Old workers may infinitely retry incompatible messages.
- Dashboards may undercount totals if they only sum the three legacy statuses.

Sound decisions:

**Before enabling the feature:** if rollback to `N` must stay viable, `N` must handle unknown statuses or use a safe adapter. If compatibility is absent, do not enable writing new values during the rollback window.

**After `REFUNDED` is already written:** never arbitrarily map it to `CANCELLED` or `PAID` merely to stop the old parser from crashing. Preserve business truth, halt new generation if needed, and ship a fix capable of reading that data.

**When rapid recovery is needed:** prefer a compatible patch or roll-forward. Deleting refund records might silence UI errors while corrupting payment history.

## 22. Common Anti-Patterns

| Misconception or Behavior | Consequence | Fix |
|---|---|---|
| Binary rollback equals full system rollback | Database and side effects stay in new state | Assess each state layer separately |
| Migrations can always be reversed | Lossy data cannot be reconstructed | Verify reversibility before running |
| Keeping old columns in schema is enough | New values may not be understood by old code | Test data and semantics |
| Disabling feature flag undoes data | New records and events persist | Stop new writes, convert, or roll forward |
| Restoring backup is fast and harmless | Loses transactions after recovery point | Evaluate RPO, replay, and reconciliation |
| Green health check proves data correctness | Business corruption can still exist | Verify invariants and read/write paths |
| Testing only the new version | Unknown whether old version still runs | Test old binary against new schema/fixtures |
| Rolling back immediately on any alert | Can worsen the failure | Run preflight checks and decision matrix |
| Rebuilding old artifact during an incident | Binary may differ from what previously ran | Use immutable artifacts by digest |
| Ignoring queues and external systems | Consumers or side effects keep failing | Pause, reconcile, and compensate |

## 23. Checklist Before Declaring a Rollback Safe

**Application and schema**

- [ ] Old artifact is identified by digest.
- [ ] Executed migrations are completely inventoried.
- [ ] Current schema is compatible with the old binary.
- [ ] Old structures have not been contracted, or a clear restoration plan exists.
- [ ] JDK/runtime, config, secrets, and permissions remain compatible.

**Data and business logic**

- [ ] New data created by the current version is identified.
- [ ] Enums, JSON, data types, and semantics are verified.
- [ ] Read paths and write paths of the old version have been tested.
- [ ] Business invariants and numbers remain accurate.
- [ ] Backfills/dual-writes have been reconciled.

**Dependent systems**

- [ ] Queues, backlogs, and dead-letter queues are assessed.
- [ ] Caches and sessions are compatible or have a handling plan.
- [ ] External side effects have compensation/reconciliation.
- [ ] Writers and consumers are stopped/restarted in sequence.

**Execution and evidence**

- [ ] Explicit rollback vs. roll-forward decision is made.
- [ ] Destructive down migrations are never run automatically.
- [ ] Runbook, approver, and stop conditions are in place.
- [ ] Smoke tests and post-rollback verification exist.
- [ ] Release ID, migration versions, and evidence are recorded.

## 24. Conclusion

Rolling back an application only reverts running code to an earlier version. It does not automatically reverse schemas, data, queued events, caches, sessions, or side effects already committed in external systems. Assuming a binary rollback equals data safety is a thinking pitfall that can deepen an outage.

To preserve reversibility, design with expand-contract, maintain cross-version compatibility, control when new values begin appearing, retain immutable artifacts, and test old binaries against schemas and data produced by new versions. When data has changed irreversibly, roll-forward or compensation is usually the safer recovery path.

A sound rollback decision rests on live state and evidence: which migrations ran, which data was written, which consumers remain active, and which invariants must be verified. Treat rollback as a conditional, multi-layered recovery process, not a button that rewinds the entire system into the past.
