# Distinguishing Application Code Rollback from Data Recovery

## Learning Objectives

After this lesson, learners will be able to:

- Distinguish between application code rollback, schema migration rollback, and data recovery.
- Explain why redeploying an older application version does not automatically reverse modified data.
- Choose between application rollback, forward fix, backup restore, point-in-time recovery, and selective recovery.
- Assess the impact of data writes occurring after a new version is deployed.
- Design compatible migrations so old and new versions can coexist during transition.
- Define RPO, RTO, recovery scope, and how to verify consistency after recovery.
- Organize recovery decisions in CI/CD pipelines with proper permissions, evidence, auditing, and drill plans.

## 1. Why distinguish code rollback from data recovery?

When a release introduces a bug, the common instinct is rolling the application back to the previous version. This is a useful action, yet it only restores application code and configuration to the prior state. It does not automatically reverse changes already persisted in databases, message queues, object storage, or external systems.

Example:

1. Application version V2 is deployed.
2. V2 writes order data using the new schema and transitions several records' statuses.
3. A bug is discovered.
4. The team redeploys V1.
5. V1 cannot interpret the data written by V2.

The application has reverted to the old version, yet the data remains in the new state. If V1 misreads, overwrites, or drops new fields, rolling back code can make the incident worse.

The reverse scenario also happens: the application has a bug while the data remains valid. In that case, code rollback alone suffices to restore service; restoring the database would risk losing valid transactions generated after the backup timestamp.

Therefore, distinguish three separate activities:

| Activity | Target being changed | Goal |
|---|---|---|
| Application rollback | Binary, container image, package, or application revision | Revert the application to a known-good version |
| Schema migration rollback | Database structure or schema version | Reverse structural changes if safe and feasible |
| Data recovery | Records, databases, volumes, objects, or event state | Restore lost, corrupted, or erroneously modified data |

These three activities may need coordination, yet they do not substitute for one another.

Core principle:

> Code rollback changes only which program runs. Data recovery alters already-written data state. Before choosing an action, pinpoint exactly what failed and what state changes occurred.

## 2. Which states can change during a release?

A production application rarely consists of a single artifact. Its behavior depends on multiple classes of state:

- **Application code:** packaged JARs, binaries, container images, packages, and libraries.
- **Database schema:** tables, columns, indexes, constraints, stored procedures, and migration versions.
- **Business data:** customers, orders, payments, inventory, permissions, and business states.
- **Events and messages:** messages in brokers, event logs, consumer offsets, and processing state.
- **Object/file storage:** uploaded files, documents, images, and blobs.
- **Runtime configuration:** feature flags, endpoints, limits, and business parameters.
- **External state:** payment transactions, sent emails, webhooks, or mutations on partner systems.

A single release can mutate several state classes simultaneously. For instance, a migration adds a column, the app starts writing the new column, consumers process new events, and a background job transforms legacy data.

When an incident occurs, construct a timeline:

1. Which artifacts and configs were deployed?
2. Which migrations executed?
3. When did the new version start writing data?
4. How many records or events were modified?
5. Which external systems received side effects?
6. When did the bug begin and how long did it persist?
7. Which backups, transaction logs, or event logs cover that timeframe?

Without a timeline, teams easily pick an overly broad recovery action or destroy valid data.

## 3. What can and cannot application rollback do?

Application rollback typically replaces the running version with a previously released artifact.

Example:

~~~text
Before release:
  application = V1
  database schema = S1

After release:
  application = V2
  database schema = S2
  business data = D2

Application rollback:
  application = V1
  database schema = S2
  business data = D2
~~~

The resulting state is not the original V1 + S1 + D1 state. Only the application reverted to V1; schema and business data remain in their altered states.

Application rollback is appropriate when:

- The bug resides in the new code.
- Data remains valid and compatible with the old version.
- The new schema remains backward compatible.
- Already-emitted side effects do not corrupt data when the old version resumes running.
- A verified old artifact exists and remains deployable.

Application rollback is insufficient when:

- Data has been deleted or written erroneously.
- A migration dropped a column required by the old version.
- New values cannot be parsed by the old version.
- Consumers have already processed events under new semantics.
- An external operation already occurred and requires compensation.
- The failure stems from configuration or data state rather than code.

Verify compatibility before rolling back. Seeing an old image still sitting in the registry only proves the image can be pulled, not that the old application can run safely against the current schema and data.

## 4. What is data recovery?

Data recovery is the process of bringing data back to a consistent, usable state after loss, corruption, or unintended changes.

Recovery sources can include:

- Full database backups.
- Incremental or differential backups.
- Transaction logs, write-ahead logs, or binary logs.
- Point-in-time recovery (PITR).
- Volume or storage snapshots.
- Event logs or message archives.
- Verified data replicas.
- Audit records or other authoritative data sources.

Data recovery can operate at multiple scopes:

- A single record or group of records.
- A table or partition.
- A single database.
- A cluster or storage system.
- A related dataset spanning multiple services.

The broader the scope, the harder synchronized recovery becomes and the higher the risk of overwriting valid data.

Restoring from a backup typically rewinds data to a past timestamp. Valid changes occurring after that point may be lost unless replayed or reconciled. Therefore, never restore an entire database for a small subset of bad records if selective recovery is possible.

## 5. Distinguishing schema rollback from data restore

Schema migrations alter structure or storage rules. Data migrations alter data contents or representation. A single migration may do both.

Example:

- Schema migration: adding column `phone_number`.
- Data migration: copying data from `phone` to `phone_number`.
- Destructive schema migration: dropping the old `phone` column.
- Data transformation: normalizing phone number formats and overwriting old values.

Different operations vary in reversibility:

| Operation | Reversibility | Risk |
|---|---|---|
| Add nullable column | Usually easy to keep or drop if nothing depends on it | Lower if unused yet |
| Add index | Index can be dropped if no dependencies exist | May impact performance during creation/removal |
| Add constraint | Can be dropped, though data was validated against it | Removing it may expose invalid data |
| Rename column | Can rename back if no clients depend on it | Old/new apps may be incompatible |
| Drop column | Contents cannot be restored merely by recreating the column | Data loss |
| Merge or normalize values | Original detail may be lost | Requires backup or mapping to restore |
| Delete records | Recoverable from logs/backups if retained | May lose transactions after backup timestamp |

A down migration script does not automatically prove a migration is reversible. If the migration deleted data or collapsed multiple values into one, recreating the old structure will not bring back lost information.

Distinguish clearly:

- **Schema rollback:** changing database structure back to an earlier shape.
- **Data rollback:** reversing written contents.
- **Restore:** recovering from a stored backup or log.
- **Forward migration:** advancing to a new compatible schema to fix the issue without reverting to the old schema.

Not every release requires a down migration. For lossy data changes, a forward fix or selective restore is usually safer.

## 6. Backward compatibility makes application rollback safer

One way to lower risk is designing migrations so old and new versions work together during transition.

The common pattern is expand-and-contract:

1. **Expand:** add new structures without deleting or breaking old structures.
2. **Deploy compatible code:** ship code capable of working with both old and new structures.
3. **Backfill:** copy legacy data to the new structure in controlled batches.
4. **Switch reads/writes:** move the application to read/write the new structure once data is ready.
5. **Observe:** verify zero remaining dependencies on the old structure.
6. **Contract:** remove the old structure only in a subsequent release when rolling back to old code is no longer required.

Example of renaming a column:

Do not execute a single migration dropping `old_name` and creating `new_name` followed immediately by deploying new code.

Instead, split into:

- Release A: add `new_name`, retain `old_name`.
- Release B: code writes simultaneously or syncs both columns cleanly; reads from the old column or uses fallback.
- Backfill legacy data to `new_name`.
- Release C: switch reads to `new_name` and verify data.
- Release D: after an observation window and once no old versions remain, drop `old_name`.

Dual-writing also carries risk: the two writes may not both succeed. If used, employ proper transactions, an outbox, or reconciliation to catch data drift. Never simply add two `UPDATE` statements in code and assume consistency.

Expand-and-contract creates a window where old and new code interact safely with the schema. This is vital for rolling updates, canary rollouts, and application rollbacks.

## 7. What happens to data written after deployment?

This is the deciding question when choosing between rollback and restore.

Suppose V2 deploys at 10:00. Between 10:00 and 10:30, users place 500 orders. At 10:20, a bug in V2 causes 20 orders to be recorded with the wrong status.

Restoring the database to 09:59 could wipe out all 500 valid orders. Merely rolling the application back to V1 leaves the 20 corrupted orders broken.

The two actions address two different problems:

- Application rollback restores request-handling logic for future requests.
- Data recovery repairs or restores records already impacted.

You may need to combine steps:

1. Halt or throttle the faulty write flow.
2. Revert the application to a compatible version or ship a forward fix.
3. Identify the affected record set by timestamp, release ID, or correlation ID.
4. Restore affected records from backups/logs or reconstruct from an authoritative source.
5. Replay missed valid transactions if feasible.
6. Verify relationships and business invariants.
7. Re-enable write traffic after verification.

Never restore an entire database just to repair a small batch of records if other valid data arrived afterward.

## 8. Data recovery options

### 8.1. Restoring from a full backup

A full backup captures a copy of data at creation time. Restoring returns the system to that backup's state.

Appropriate when:

- The entire database or volume is corrupted.
- An environment must be rebuilt from a known baseline.
- Finer-grained recovery options are infeasible.

Limitations:

- Changes after the backup timestamp may be lost.
- Restoring large databases can take significant time.
- Transaction log replay may be needed to minimize data loss.
- Consistency between the database and related systems must be verified.

### 8.2. Point-in-time recovery

PITR combines a base backup with transaction logs or equivalent logs to recover to a chosen timestamp.

Example:

- Base backup taken at 00:00.
- Transaction logs archived continuously.
- Erroneous deletion occurs at 14:32.
- The database can be restored to just before the bad operation if logs and platform support it.

PITR helps when needing a finer recovery point than scheduled backups. Still, restoring to before an error can drop valid transactions occurring after that point.

A common workflow is restoring to an ephemeral instance or database, extracting needed rows, reconciling, and applying verified data back to the primary system. You do not always need to replace the entire production database with the PITR clone.

### 8.3. Selective recovery

Selective recovery restores only affected records or scopes.

Example:

- Recovering a subset of customers assigned an incorrect status.
- Restoring a single partition or table.
- Diffing production records against a temporary restore.
- Generating a remediation script scoped to an explicit list of IDs.

This minimizes loss of valid data, yet requires understanding data relationships and invariants. Restoring one table alone can break foreign keys, summary balances, or state in another service.

### 8.4. Replaying from an event log or authoritative source

If the system maintains an event log, audit log, or authoritative data source, state can be rebuilt by replaying valid events.

Check:

- Are events complete and properly ordered?
- Are there duplicate events?
- Are consumers idempotent?
- Are event schemas compatible with replay code?
- Are external side effects suppressed or handled separately?
- Can safe offsets or checkpoints be established?

Replaying is not simply re-running every message. If a consumer charges payments or sends emails, blind replay duplicates side effects. Require idempotency keys, deduplication, or a dry/replay mode that avoids unintended external actions.

### 8.5. Forward fix or compensating transactions

Sometimes data cannot be restored verbatim safely. Current state may need fixing via a forward-moving change.

- **Forward fix:** patch code or run a migration to handle existing data properly.
- **Compensating transaction:** issue a new transaction offsetting the prior transaction's effect—for example, issuing a refund instead of erasing payment history.

Compensation does not erase event history. It records a new action that brings business state to the desired outcome while preserving the audit trail.

## 9. How RPO and RTO shape recovery decisions

Two critical objectives:

- **RPO (Recovery Point Objective):** maximum acceptable data loss, typically expressed as a time interval.
- **RTO (Recovery Time Objective):** target duration to restore service or processing capability after an incident.

For example, a service with a 5-minute RPO needs backup/log mechanisms capable of bounding data loss within that window. A 30-minute RTO requires restore, verification, and traffic cutover procedures to complete within that timeframe.

RPO/RTO are not automatically met just because backups exist. Measure:

- Backup frequency and lag.
- Completeness of transaction logs.
- Actual restore duration for real data sizes.
- Consistency checking duration.
- DNS/routing or failover time.
- Data replay and backlog drain time.
- Business verification time before reopening traffic.

A backup strategy might meet RPO yet miss RTO if restores take too long. Conversely, snapshots might restore quickly yet wide intervals between snapshots lose too many transactions.

## 10. Ensuring cross-system consistency

An application may write data to multiple stores:

- Primary database.
- Read replicas.
- Message brokers.
- Search indexes.
- Caches.
- Object storage.
- External payment or CRM services.

Restoring only the primary database can leave other systems holding newer or desynchronized state.

Example:

1. Database marks an order as `PAID`.
2. An `OrderPaid` event is published to the broker.
3. Consumers update inventory and send notifications.
4. Later, the database is restored to before the order became `PAID`.
5. The broker and inventory system still retain the processed event.

At that point, systems no longer agree on state. Recovery requires a proper reconciliation or replay plan.

Supporting mechanisms:

- Transactional outbox linking database writes to event emission.
- Idempotent consumers handling duplicate messages safely.
- Correlation IDs and event IDs for tracing.
- Reconciliation jobs comparing state across systems.
- Sagas or compensating actions for multi-service workflows.
- Recorded checkpoints and offsets during replays.

No single database transaction covers all external systems. Design recovery workflows per bounded context and business relationship.

## 11. Decision workflow: code rollback, forward fix, or data recovery?

When a release causes an incident, do not jump straight to restoring the database or rolling back the application. Evaluate sequentially:

1. **Containment:** stop error propagation; halt rollout, disable feature flags, or restrict writes if needed.
2. **Classify:** determine whether the fault lies in code, schema, data, config, dependencies, or external systems.
3. **Assess compatibility:** is the previous application version compatible with the current schema and data?
4. **Measure impact:** determine timeframe, affected record scope, impacted users, and side effects.
5. **Choose recovery path:** application rollback, forward fix, migration correction, selective restore, PITR, or compensation.
6. **Preserve evidence:** retain logs, audits, snapshots, and data copies for investigation.
7. **Execute with controls:** follow runbooks, enforce proper permissions, back up before destructive steps, and confirm scope.
8. **Verify:** validate schema, data, relationships, and business invariants.
9. **Resume traffic:** reopen write flows only once safety criteria pass.
10. **Record:** document decision, actor, timestamps, recovered data, and any residual drift.

~~~mermaid
flowchart TD
    A["Release causes incident"] --> B["Contain: halt rollout / restrict writes"]
    B --> C["Classify code, schema, data, config, external state"]
    C --> D{"Is data corrupted or lost?"}
    D -- "No" --> E{"Is old code compatible with current state?"}
    E -- "Yes" --> F["Rollback application"]
    E -- "No" --> G["Forward fix / compatible migration"]
    D -- "Yes" --> H["Determine data scope and timeline"]
    H --> I{"Can selective fix or replay resolve it?"}
    I -- "Yes" --> J["Selective recovery / compensation"]
    I -- "No" --> K["Temporary restore from backup / PITR"]
    K --> L["Extract, diff, and reconcile"]
    J --> M["Verify schema, data, and business rules"]
    L --> M
    F --> N["Post-recovery verification"]
    G --> N
    M --> N
    N --> O["Reopen traffic and record audit"]
~~~

The diagram is a decision framework. In real incidents, multiple branches may combine—such as rolling back the application first to stop bad writes, followed by selective recovery for affected records.

## 12. Safe migrations in CI/CD pipelines

Migrations must be governed as release changes affecting data state.

Before running a migration, pipelines should verify:

- Whether the migration version already exists or has run.
- Whether the migration is idempotent or detects partial runs.
- Whether an appropriate backup or recovery point exists.
- Whether the migration locks tables long or degrades performance.
- Whether the running application is compatible with the new schema.
- Whether multiple application versions access the database concurrently.
- Whether the migration performs destructive or lossy transformations.
- Whether a recovery plan and accountable owner exist.

For high-risk migrations, separate them from application deployment steps so they can be reviewed, tested, and observed independently.

Reference sequence:

1. Create a backup or verify a recovery point.
2. Test the migration on a representative data copy.
3. Apply compatible migrations in stages.
4. Verify schema and data.
5. Deploy the application artifact.
6. Monitor behavior and metrics.
7. Run the contract migration only when no old version needs the old structure.

Do not let pipelines automatically run destructive migrations on merge without proper gates. Automation needs clear preconditions, timeouts, and safe stop controls.

## 13. Example: handling a release that adds a new data field

Suppose V2 adds `normalized_email` to store normalized email addresses. V2 begins reading the new field while writing both the old `email` and normalized email.

An unsafe rollout might:

1. Add the new field.
2. Drop the old `email` field.
3. Deploy V2.
4. Discover a bug in V2.
5. Roll back to V1.
6. V1 fails because the old `email` field is gone.

A safer process:

**Phase 1 — Expand**

- Add `normalized_email`, keep old `email`.
- Verify schema and indexes.
- Do not delete legacy data yet.

**Phase 2 — Compatible release**

- Deploy V2 able to fall back to reading old `email`.
- Write `normalized_email` under verified rules.
- Preserve V1's ability to keep operating.

**Phase 3 — Backfill and verify**

- Migrate legacy rows in batches.
- Save checkpoints to resume after failures.
- Count remaining unmigrated rows.
- Compare values and check duplicates or constraints.

**Phase 4 — Switch**

- Switch reads to `normalized_email`.
- Monitor errors and business outcomes.
- Keep old `email` throughout the supported rollback window.

**Phase 5 — Contract**

- Drop old `email` only after confirming zero dependent versions or consumers remain.
- Ship in a separate release.
- Update the recovery plan since rolling back to old code may no longer be supported afterward.

If V2 fails prior to contract, code can roll back to V1 while keeping the expanded schema. If `normalized_email` data was written wrongly, repair or re-backfill the data; code rollback alone will not fix those values.

## 14. Selective recovery: steps to control

Selective recovery minimizes data loss, yet requires pinpointing exact affected records.

A workflow can include:

1. Stop the faulty job or code to prevent creating more bad records.
2. Identify release ID, time window, and record filter predicates.
3. Take a snapshot or restore a copy into an isolated environment.
4. Compare current production data against the restored copy.
5. Generate explicit lists of records to fix versus records to preserve.
6. Verify foreign keys, balances, aggregates, and invariants.
7. Review the repair script and execute a dry run.
8. Apply in checkpointed batches.
9. Reconcile before/after counts and write audit logs.
10. Reconcile with queues, search indexes, and related services.

Never run broad `UPDATE` or `DELETE` statements directly in production based solely on a quick count query. For critical data, require a copy, explicit scope, result verification, and batched pause/resume capability.

If corrupted records can be identified by event ID or correlation ID, use those identifiers instead of timestamps alone. Clocks across systems drift, and wide time windows may sweep up valid transactions.

## 15. Backups only matter when restores are tested

Having backups does not equal having recovery capability.

Verify:

- Did the backup finish cleanly without corruption?
- Can the backup be read and decrypted?
- Are encryption keys still accessible?
- Does the backup reside in an independent failure domain?
- Is retention long enough to catch delayed bug discoveries?
- Are transaction logs continuous with zero gaps?
- Does restore duration meet RTO?
- Does restored data pass consistency checks?
- Is the application compatible with the restored schema?

Run periodic restore drills in isolated environments. Measure total wall-clock time from start until data is verified—not just backup file download speed.

Backups must also be protected from deletion or encryption by the same account holding production admin rights. Use immutable backups, retention locks, or separated privileges depending on the platform.

## 16. Permissions and auditing during recovery

Data recovery can carry greater impact than routine deployments. Permissions must be scoped by operation type.

Example:

| Role | Recommended permissions |
|---|---|
| Developer | Read logs and request recovery; cannot restore production directly |
| Database operator | Execute database actions per runbook and change control |
| Incident commander | Coordinate recovery decisions and scope |
| Security/compliance | Oversee audits and evidence preservation requirements |
| CI workload | Run only authorized migrations or recovery tasks under a dedicated identity |

A recovery record should capture:

- Incident or change ID.
- Actor and workload identity.
- Start and end timestamps.
- Affected database, table, partition, or resource.
- Backup ID, log position, or PITR timestamp.
- Relevant artifact and schema versions.
- Scope of recovered records.
- Pre- and post-recovery record counts.
- Consistency check results.
- Compensating actions or replays performed.
- Final status and residual risks.

Do not log personal data or unnecessary secrets in recovery logs. Audits need sufficient traceability without creating extra sensitive data stores.

## 17. Common anti-patterns

| Anti-pattern | Risk | Improvement |
|---|---|---|
| Assuming rolling back an image rolls back the database | New data persists and may be incompatible | Assess code, schema, and data separately |
| Running down migrations immediately on deploy failure | May delete data or corrupt current state | Verify reversibility and impact first |
| Restoring an entire database for a small batch of bad rows | Loses valid transactions after backup | Use selective recovery where feasible |
| Skipping backups before destructive migrations | Lacks a reliable recovery point | Create and verify a recovery point |
| Rebuilding artifacts during rollback | May fail to restore the exact prior binary | Redeploy previous artifact by digest |
| Failing to test old-code compatibility | Old version may fail reading new schema | Use expand-and-contract and compatibility tests |
| Replaying messages non-idempotently | Duplicates payments, emails, or side effects | Deduplication, idempotency, and replay mode |
| Restoring only the database, ignoring queues/caches/storage | Cross-system state becomes inconsistent | Plan full-state reconciliation |
| Never rehearsing restores | Real RTO may overrun targets | Run restore drills and time them |
| Omitting recovery scope records | Cannot prove which data changed | Maintain recovery audits and reconciliation reports |

## 18. Checklist for distinguishing rollback and data recovery

When a release hits an incident, check:

- [ ] Identified whether the fault is in code, schema, business data, config, or external state.
- [ ] Stopped or restricted operations continuing to cause errors.
- [ ] Built a timeline of release, migrations, and data writes.
- [ ] Verified whether the previous application version is compatible with current schema.
- [ ] Identified valid data created after the backup timestamp.
- [ ] Selected proper scope: records, table, database, or full system.
- [ ] Identified suitable backup, transaction logs, or replay sources.
- [ ] Assessed realistic RPO and RTO.
- [ ] Accounted for side effects across queues, caches, storage, and external systems.
- [ ] Secured a snapshot or recovery point before destructive actions.
- [ ] Recovery scripts support dry-runs, bounded scope, and checkpoints.
- [ ] Proper permissions and approvals exist for production actions.
- [ ] Verified consistency and business invariants post-recovery.
- [ ] Reconciled or replayed cross-system data.
- [ ] Verified actual artifact/config/schema before reopening traffic.
- [ ] Recorded audit logs, evidence, and residual risks.

## 19. Self-assessment exercise

Release V3 of the order service deployed at 09:00. A migration moved `order_status` to a new state model. Between 09:00 and 09:30, the system received 1,200 orders. At 09:20, V3 was found assigning wrong statuses to 40 orders. The team has an 08:00 backup and continuous transaction logs up to the present. Version V2 remains in the registry, yet V2 only understands the old schema. Several `OrderPaid` events were sent to the message broker and processed by the inventory consumer.

Propose a plan:

1. What is the first action to stop new errors from occurring?
2. Can you roll back straight to V2? What conditions must be checked?
3. Why would restoring the whole database to 08:00 lose valid data?
4. Can PITR create a temporary database to extract those 40 broken orders?
5. What must be reconciled before modifying production records?
6. How should already-processed `OrderPaid` events be reconciled or compensated?
7. Should all messages be replayed from backup? Why or why not?
8. Which schema rules and invariants must pass before reopening traffic?
9. What evidence must the audit record capture?

A sound plan typically halts the faulty flow, evaluates app and schema compatibility, executes selective recovery from a temporary PITR restore, reconciles broker and consumer side effects, and verifies all business state. Final decisions must rest on actual data and verified recovery capabilities.

## Conclusion

Application code rollback and data recovery address two distinct layers of state. Code rollback restores the program to an earlier version; data recovery restores or repairs mutations written to databases, queues, storage, and connected systems. Schema migration rollback is a separate operation and may be irreversible once data has been deleted or lossily transformed.

In CI/CD, design staged compatible migrations, retain old artifacts by digest, maintain appropriate backups and transaction logs, define RPO/RTO, and rehearse restores. During an incident, contain impact, build a timeline, pick the smallest valid recovery scope, reconcile data and side effects, and verify everything before reopening traffic. This approach restores service while preserving as many valid transactions as possible.
