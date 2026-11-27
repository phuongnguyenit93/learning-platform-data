# Cutover Plans, Go/No-Go Gates, and Limitations of Rollback or Downgrade

An Oracle Database upgrade or migration is complete only when the application runs cleanly on the target, data is reconciled, dependent systems connect properly, and operations can handle post-cutover incidents. A cutover plan must clearly specify when traffic shifts, conditions permitting continuation, decision authorities, verification evidence, and how to fall back if criteria are not met.

A common source of confusion is that the word **rollback** gets used for very different actions:

- **Application rollback:** reverting traffic to an older application version.
- **Traffic rollback:** switching DNS, services, connection pools, or load balancers back to the old endpoint.
- **Database recovery/restore:** restoring the database from backups or flashback logs to an earlier point in time.
- **Data rollback/reconciliation:** handling transactions written to the new database after cutover.
- **Database downgrade:** reverting a database from a newer Oracle release to an older release via a supported downgrade procedure.
- **Forward fix:** keeping the new database and resolving errors with follow-up changes.

These actions are not equivalent. Reverting traffic to the old application does not automatically revert the database to the old schema; restoring a database can discard recent transactions; downgrading releases may no longer be supported after using new features or raising `COMPATIBLE`. Therefore, fallback options must be designed per change milestone and rehearsed before production execution.

## 1. Cutover Goals and Scope

### 1.1. What Is Cutover?

Cutover is the moment a system switches from the source environment to the target environment or from an older database release to a newer release. Cutover typically involves:

1. Stopping or throttling writes on the source system.
2. Synchronizing final data deltas.
3. Switching roles, services, or connection endpoints.
4. Starting or opening traffic on the target application.
5. Verifying transactions and data.
6. Monitoring stability post-switchover.

Cutover is more than swapping a connection string. It is a synchronized change across databases, applications, batch jobs, integrations, credentials, network routes, and operations.

### 1.2. Go/No-Go

- **GO:** proceed to the next step because all mandatory criteria pass and the authorized decision-maker approves.
- **NO-GO:** stop before crossing an unsafe point of no return, hold the system in a defined state, and trigger the fallback or remediation plan.
- **HOLD:** pause to gather further evidence or resolve an unclear condition. `HOLD` must never stretch indefinitely; assign an owner and a decision deadline.

Go/no-go is an evidence-based decision, never a gut feeling that the system "looks okay."

### 1.3. Defining Success

Before the change window, explicitly define:

- Which applications must operate.
- Which database is the single authoritative writer post-cutover.
- Which business flows must pass.
- Which row counts and control totals must match.
- Acceptable latency, error rate, and throughput thresholds.
- Which background jobs are allowed to run.
- Practical RPO and RTO.
- Observation duration before closing the rollback window.
- Technical and business sign-off authorities.

### 1.4. Scope of Change

Distinguish change types:

| Change Type | Example | Key Controls |
|---|---|---|
| Application release | Deploying new Spring Boot version | Schema compatibility and binary rollback |
| Schema change | Adding/altering columns, indexes, constraints | Compatibility with both old and new apps |
| Database upgrade | Upgrading Oracle release | Dictionary, `COMPATIBLE`, components, features |
| Migration | Moving to new database/host | Data consistency, endpoints, delta sync |
| Platform change | OS, storage, RAC, cloud | Drivers, networking, performance, recovery |
| Security change | TDE, wallets, credentials | Database openability and app connectivity |

A single cutover may combine multiple change types. The more variables changing simultaneously, the harder root-cause isolation becomes when errors occur. Separate independent changes into distinct windows when schedule and architecture allow.

## 2. Distinguishing Rollback, Restore, Downgrade, and Forward Fix

### 2.1. Application Rollback

Application rollback reverts binaries/configuration to the prior version. It is safe only if the older version remains compatible with the existing schema and data.

Examples:

- The new application only added a nullable column; the old application still runs.
- The new application writes to a new column the old application ignores.
- A migration dropped or renamed an old column the old application still requires.

The first two cases differ in compatibility nuances; the third causes application rollback to fail. Therefore, schema changes should follow the expand-and-contract model.

### 2.2. Traffic Rollback

Traffic rollback switches clients back to the old endpoint. It can be fast, yet is valid only if the old database remains authoritative and holds all required changes.

If the new database already accepted post-cutover transactions, merely flipping DNS or connection strings back to the old database loses new transactions or splits data into two diverging branches.

### 2.3. Database Restore/Recovery

Restore/recovery returns a database to a recoverable state using backups, archived redo, flashback logs, or valid snapshots. This is a database recovery operation, not a simple undo for a single DDL statement.

Restoring may:

- Recover the entire database or a subset via supported methods.
- Require downtime and redo apply duration.
- Discard changes after the recovery point unless captured/replayed separately.
- Require synchronized recovery of TDE wallets, control files, parameter files, and dependencies.

### 2.4. Flashback Database

Flashback Database uses flashback logs to rewind the database to an earlier timestamp or restore point within supported limits. It can serve as a useful fallback for certain upgrades, provided prerequisites, Fast Recovery Area (FRA) capacity, flashback log retention, and Oracle release guidelines are verified.

Flashback Database is not an independent backup. It does not replace RMAN backups, undo outbound emails/payments/APIs, restore external files, or automatically resynchronize downstream systems.

### 2.5. Database Downgrade

Downgrade reverts a database from a newer release to an older release using an Oracle-supported path. It differs from restoring an old backup and from application rollback.

Downgrades can be blocked by:

- Source/target releases lacking a supported downgrade path.
- Raising `COMPATIBLE` to a newer level.
- Using features or data types absent from the older release.
- Irreversible dictionary/component changes.
- Specific rules for PDB/CDB, RAC, Data Guard, or options.
- Post-upgrade operations violating downgrade preconditions.

Never assume every Oracle upgrade can be downgraded simply because downgrade scripts exist in Oracle Home.

### 2.6. Forward Fix

Forward fix keeps the target database and resolves defects via application patches, follow-up schema changes, config updates, or data repairs. It is often less risky than restoring when the new database has already accepted substantial valid business transactions and the defect scope is narrow.

Forward fixes still require data assessment, testing, and approval. Never use forward fixes to stall decisions during active corruption or data inconsistency.

## 3. Schema Compatibility Strategy: Expand-and-Contract

### 3.1. Why Bidirectional Compatibility Matters

During rolling deployments, old and new application versions can coexist. If the schema changes abruptly in a way only the new version understands, old applications break during rollout or when rolling back.

Expand-and-contract splits schema changes into stages:

1. **Expand:** add new columns/tables/indexes compatibly with the old application.
2. **Deploy:** deploy the new application able to read/write the new schema while maintaining backward compatibility if needed.
3. **Migrate data:** backfill data and verify.
4. **Switch:** route all traffic to the new logic.
5. **Observe:** monitor long enough to confirm zero old consumers remain.
6. **Contract:** drop old columns/logic in a separate release after rolling back to the old app is no longer needed.

### 3.2. Column Addition Example

Suppose the application needs to replace `CUSTOMER_NAME` with `DISPLAY_NAME`.

Expand phase:

```sql
ALTER TABLE APP.CUSTOMER
    ADD DISPLAY_NAME VARCHAR2(200 CHAR);
```

The new application can write both old and new columns during transition. Backfill:

```sql
UPDATE APP.CUSTOMER
SET DISPLAY_NAME = CUSTOMER_NAME
WHERE DISPLAY_NAME IS NULL;
COMMIT;
```

Only after confirming every consumer uses `DISPLAY_NAME` and the rollback window ends should you schedule contract in a separate release. Never drop `CUSTOMER_NAME` in the same change window if reverting to old binaries remains possible.

### 3.3. Dual-Write and Consistency

Dual-writing two columns keeps old and new apps working but risks values drifting out of sync. Define:

- Which column is the source of truth.
- Write ordering and transaction boundaries.
- Error handling if one write fails.
- Backfill and delta capture.
- How mismatches are detected.
- When writes to the old column stop.

Never enable dual-writes merely by adding two `UPDATE`s without reconciliation mechanisms.

### 3.4. Destructive Schema Changes

Operations such as `DROP COLUMN`, incompatible data type changes, changing column semantics, dropping tables, renaming objects, or adding constraints incompatible with old applications can render application rollback impossible.

Defer destructive changes to the contract phase after:

- All app instances are upgraded.
- Legacy batch/integrations are stopped.
- Zero consumers reference the old object.
- The rollback window is formally closed per approval.
- Backups/recovery points and migration evidence exist.

## 4. Choosing a Cutover Strategy

### 4.1. Big-Bang Cutover

All traffic switches in one window:

- Freeze source writes.
- Export/sync final delta.
- Import/validate on target.
- Switch endpoints.
- Open traffic.

Pros: simpler architecture and data synchronization. Cons: concentrated downtime, intense change-window pressure, and harder rollback once target accepts writes.

### 4.2. Blue-Green

Blue is the current environment; green is the target environment. Green is prepared and tested ahead of time; traffic shifts progressively or all at once.

Blue-green keeps the old environment ready early on, but does not automatically solve data divergence. Explicitly define which database accepts writes and how reverse syncing works if switching back.

### 4.3. Canary or Traffic Splitting

A fraction of traffic shifts to the target for live validation. Suitable when application and data models allow safe traffic splitting. If two databases write to the same entities concurrently without consistency guarantees, canary splitting creates diverging datasets.

### 4.4. Data Guard Switchover

In Data Guard architectures, switchover performs a planned role transition to a synchronized standby. This is a role transition, not a release downgrade or application rollback.

Before switchover, check:

- Transport/apply lag.
- Protection mode/level.
- Broker status and validation.
- Standby redo logs.
- Service relocation and client reconnection.
- Database roles post-transition.

If primary and standby run different releases or upgrade states, use only the role transition workflow explicitly supported for that topology.

### 4.5. Rolling Upgrade

Some Oracle topologies support rolling upgrades via Oracle-documented methods, such as Data Guard/Transient Logical Standby workflows or AutoUpgrade in supported releases. Never invent a custom rolling upgrade by letting two independent database versions accept writes concurrently without a supported sync mechanism.

### 4.6. Comparison

| Strategy | Downtime | Data Complexity | Key Notes |
|---|---|---|---|
| Big-bang | Typically concentrated | Lower with full write freeze | Longer window; harder fallback after writes |
| Blue-green | Can be brief | High if writes occur post-cutover | Requires single-writer discipline and data sync |
| Canary | Can be very low | High if write traffic splits | Needs data-aware routing and consistency |
| Data Guard switchover | Usually brief if well prepared | Redo apply preserves sync | Validate role transition and services |
| Rolling upgrade | Reduces downtime | Depends on Oracle-supported method | Subject to specific version/feature limits |

## 5. Planning Recovery Before the Change Window

### 5.1. Backups Must Be Restorable

Before making changes, confirm:

- Complete RMAN backups with readable backup pieces.
- Sufficient archived redo logs to recover to the target point.
- Control files and SPFILE protected.
- Password files and TDE wallets/keystores safely backed up.
- Backups stored on independent storage/sites per design.
- Sufficient space and permissions to restore.
- Restore tests executed or recent valid recovery evidence on record.

An RMAN job marked `COMPLETED` does not guarantee recovery meets RTO. Verify actual backups, metadata, and recovery procedures.

### 5.2. Capture Backup Baseline

Record DBID, `DB_UNIQUE_NAME`, database role, Oracle release, `COMPATIBLE`, character sets, timezone file version, control file locations, datafiles, redo logs, FRA, and TDE configuration.

Example:

```sql
SELECT dbid,
       name,
       db_unique_name,
       database_role,
       open_mode,
       protection_mode,
       protection_level
FROM v$database;

SELECT name, value
FROM v$parameter
WHERE name IN (
    'compatible',
    'db_recovery_file_dest',
    'db_recovery_file_dest_size',
    'db_flashback_retention_target'
);

SELECT * FROM v$timezone_file;
```

### 5.3. RMAN Backup

Illustrative commands:

```text
RMAN> BACKUP DATABASE PLUS ARCHIVELOG;
RMAN> BACKUP CURRENT CONTROLFILE;
RMAN> BACKUP SPFILE;
```

Exact commands and strategies must match database mode, retention policies, catalogs, and environment. If using TDE, safeguard keystores/wallets and confirm keys open on the recovery host.

### 5.4. Restore Rehearsal

Rehearse restores on an isolated host/environment:

1. Identify target backups.
2. Restore control file/SPFILE per runbook.
3. Restore datafiles.
4. Recover using appropriate archived redo logs.
5. Open the database per supported procedure.
6. Verify objects, data, and application connectivity.
7. Measure actual elapsed time.

Never run a restore rehearsal over an active production source.

### 5.5. Guaranteed Restore Points

For certain database upgrades, a guaranteed restore point (GRP) establishes a Flashback Database marker to revert to pre-upgrade state when supported prerequisites are met.

Before relying on a GRP:

- Verify Flashback Database and `ARCHIVELOG` prerequisites per release.
- Ensure FRA has enough space for all change-window activity.
- Confirm the restore point exists and is guaranteed.
- Know the exact flashback/reopen steps for your release.
- Rehearse or confirm procedures with the responsible DBA.
- Monitor FRA continuously while the GRP remains active.

GRPs can cause FRA to fill rapidly; if FRA runs out of space, database operations can halt. Never create a GRP and forget to drop it once the rollback window closes with approval.

### 5.6. Restore Points Are Not Downgrades

Flashing back to a GRP restores the database to an earlier point in time. Downgrading converts the dictionary/database back to an older release via downgrade scripts. These are different mechanisms with distinct preconditions. Nor does a GRP undo external side effects outside the database.

### 5.7. Storage Snapshots

SAN/VM/cloud snapshots can speed up recovery, yet require verifying consistency across database, control/data/redo files, and all ASM disk groups. Crash-consistent snapshots are not automatically equivalent to Oracle-supported backups. Coordinate with storage vendors and Oracle recovery procedures.

## 6. Limitations of Oracle Database Downgrades

### 6.1. Downgrade Paths Depend on Release

Oracle supports downgrades only between specific release/source-target combinations under documented rules. Never assume upgrading from release A to B automatically permits downgrading from B to A. Consult the downgrade guide for the exact release, patch level, architecture, and installed components.

### 6.2. COMPATIBLE

`COMPATIBLE` governs database feature compatibility. Raising `COMPATIBLE` to a newer level can permanently eliminate standard downgrade paths back to older releases.

Do not raise `COMPATIBLE` immediately post-upgrade just to "match versions." Raise it only when:

- The upgrade is complete.
- Applications and database are verified.
- Standard-path downgrades are no longer needed.
- Change owners accept closing the downgrade path.
- Post-`COMPATIBLE` backup/recovery strategies are verified.

### 6.3. Using New Features

If the upgraded database created or used data types, dictionary metadata, SQL features, index types, or components absent in the older release, downgrading may be blocked or lose data/behavior.

Even without raising `COMPATIBLE`, using certain new features can render objects or data non-downgradable. Check downgrade restrictions and feature usage before enabling new features.

### 6.4. Database Components

Components such as JVM, XML DB, Spatial, Text, OLAP, or options carry their own upgrade/downgrade workflows. `INVALID` component statuses or incompatible component versions can block downgrades.

Check:

```sql
SELECT comp_id,
       comp_name,
       version,
       status
FROM dba_registry
ORDER BY comp_id;
```

### 6.5. CDB/PDB

Multitenant setups impose separate rules for CDB root, seed, and PDBs. Never assume a single PDB can be downgraded independently in every scenario. Check release guides and container states.

### 6.6. RAC, Data Guard, and Options

RAC, ASM, Data Guard, GoldenGate, TDE, and integrations may require specific operational sequences. Downgrading the database does not automatically downgrade Oracle Grid Infrastructure, clients, JDBC drivers, applications, or agents.

### 6.7. Time Zone Files

Timezone file upgrades are separate changes affecting `TSTZ` data. Check timezone downgrade support and converted data. Never manually downgrade timezone files by copying old `.dat` files or changing `DBTIMEZONE`.

### 6.8. Data Pump VERSION Is Not a Downgrade

Data Pump `VERSION` only controls metadata compatibility during export within supported bounds. It does not downgrade the database dictionary, `COMPATIBLE`, timezone files, or used features. Exporting a dump with a lower `VERSION` does not turn a new database into an old release.

### 6.9. Backup/Restore Is Not a Downgrade

Restoring a backup from the old release returns the system to pre-upgrade state, which is backup recovery rather than downgrading the upgraded database. It requires valid backups, archived logs, TDE keys, time, and a compatible environment.

## 7. Rollback Limits After the Target Accepts Writes

### 7.1. Before Opening Traffic

If the target has not received business transactions, rollback is usually simpler:

- Point endpoints back to source.
- Keep target for investigation.
- Cancel or repeat imports per plan.
- No need to reconcile new production transactions on the target.

### 7.2. After the Target Accepts Writes

The moment the target processes new transactions, source and target diverge unless bidirectional replication or delta capture is active. Reverting traffic to source without migrating those new transactions loses data or leaves systems out of sync.

### 7.3. Dual Active Writers

Never allow source and target to write to the same data domain simultaneously without explicit conflict resolution, key allocation, and transaction consistency design. Two databases can generate colliding business transactions or update the same entity in conflicting orders.

### 7.4. Reverse Replication

Some architectures maintain reverse replication/capture to propagate changes from target back to source during the rollback window. Design upfront for:

- Data type and schema support on both sides.
- Capture/apply latency.
- Conflict detection and resolution.
- Sequence/key generation.
- DDL synchronization.
- Transaction ordering.
- Failover handling if replication breaks.

Never spin up reverse replication ad hoc after writes have already occurred; it will not automatically resolve prior conflicts.

### 7.5. Restoring to Pre-Cutover Discards Data

If the target runs for 30 minutes and then gets restored to a pre-cutover GRP, those 30 minutes of transactions disappear from the recovered database. Have a plan to capture and replay/reconcile them if business rules require it.

### 7.6. External Side Effects

Database rollbacks cannot undo:

- Sent emails or SMS messages.
- Payments submitted to payment gateways.
- Messages published to Kafka/queues.
- Files written to object storage.
- Outbound partner API requests.
- Jobs triggered on external systems.

Applications need idempotency keys, outbox/inbox patterns, compensation workflows, or reconciliation to handle external side effects. Never assume database transactions encompass external systems.

## 8. Fallback Selection Matrix

| When Failure Is Detected | Common Candidate Options | Risks / Conditions |
|---|---|---|
| Before import | Abort change, stay on source | Usually easy to revert |
| Import done, traffic not yet open | Fix/re-import or discard target | Verify target received zero external writes |
| New app buggy, schema still compatible | Application rollback | Old binaries must run cleanly on current schema |
| Traffic switched, target has zero writes | Switch endpoints back to source | Confirm no background writers touched target |
| Target received writes, source still intact | Reverse sync/reconcile or forward fix | Never just flip connection strings |
| Destructive DDL already ran | Restore, forward fix, or recreate objects | Old app may be incompatible with schema |
| Upgrade failed before opening database | GRP, restore, or downgrade per guide | Check prerequisites and release path |
| Upgrade finished, `COMPATIBLE` unchanged | Downgrade if Oracle-supported, or restore | Check feature usage and downgrade guide |
| `COMPATIBLE` already raised | Usually forward fix or restore backup/GRP if supported | Standard downgrade may no longer work |
| Target already processed heavy writes | Forward fix or reverse data migration | Check RPO, conflicts, and side effects |

This matrix is a decision framework. Each change plan must fill in exact releases, database roles, recovery points, owners, and time budgets per branch.

## 9. Go/No-Go Gates

### Gate 1 — Pre-Change Readiness

GO when:

- Change scope and owners are approved.
- Upgrade/migration path is Oracle-supported.
- Source/target compatibility is verified.
- Backup/recovery plans have verified evidence.
- Restore rehearsal meets RTO.
- Application compatibility and schema changes are reviewed.
- Cutover and fallback runbooks are rehearsed.
- Monitoring, access, and escalation paths are ready.

NO-GO if backups are unreadable, downgrade/restore assumptions are unclear, or critical dependencies remain unmapped.

### Gate 2 — Pre-Cutover

GO when:

- Target database is open in the right role/mode.
- Components and invalid objects are in acceptable state.
- Data Pump/upgrade logs contain zero unexplained errors.
- Data reconciliation meets acceptance criteria.
- Constraints, indexes, sequences, and grants match expectations.
- Networking, listeners, services, and credentials work.
- Batch jobs are controlled.
- Business owners are ready to verify.

NO-GO if material mismatches, unexplained data loss, or missing target recovery paths exist.

### Gate 3 — Opening Traffic

GO when:

- Source writes are frozen or final deltas applied.
- Exactly one database is designated as writer.
- Connection endpoints point to the target.
- Smoke tests pass.
- Critical business flows pass.
- Error rates and latency fall within thresholds.
- Authorized decision-maker declares GO.

NO-GO if applications write to the wrong database, duplicate keys appear, transactions fail, or control totals mismatch.

### Gate 4 — Post-Cutover

GO to close the rollback window when:

- Traffic remains stable throughout the observation window.
- Zero new discrepancies appear.
- Batches and integrations run normally.
- Monitoring and alerting operate properly.
- Business sign-off is recorded.
- Recovery artifacts are secured.

Drop GRPs, temporary backups, or reverse replication only after change-owner approval and retention policy checks.

## 10. Measurable Go/No-Go Criteria

Avoid vague criteria like "good performance" or "no major errors." Set concrete thresholds upfront:

| Category | Example Criteria | Evidence |
|---|---|---|
| Availability | Listeners/services open, health checks pass | Connection tests, monitoring |
| Data | Row counts and control totals match | Reconciliation report |
| Integrity | Zero duplicates/orphans beyond accepted exceptions | Constraint/query reports |
| Application | Login, transaction creation, and reporting flows pass | Test evidence |
| Error rate | Below agreed SLA threshold | APM/log metrics |
| Latency | P95/P99 below business thresholds | APM/load tests |
| Capacity | CPU, memory, I/O, FRA, tablespaces have headroom | Monitoring snapshots |
| Batch | Critical jobs finish on schedule | Scheduler/job logs |
| Security | TDE wallets, grants, secrets, and audits intact | Security checklist |
| Recovery | Verified recovery procedure and duration | Restore rehearsal |

Exact numbers must be defined by system and business owners; never apply one generic latency threshold across all databases.

## 11. Detailed Cutover Runbook

### 11.1. T-7 Days to T-1 Day

1. Confirm change ticket, owners, escalation tree, and maintenance window.
2. Freeze out-of-scope schema changes.
3. Verify release/patch/`COMPATIBLE`/timezone/components.
4. Run appropriate preupgrade checks or migration assessments.
5. Verify backups, archive logs, wallets, and restore rehearsals.
6. Verify target capacity, tablespaces, FRA, TEMP, undo, and network.
7. Rehearse export/import or upgrade on representative data.
8. Time every step and refine the runbook.
9. Prepare application configs, endpoints, secrets, firewalls, and services.
10. Prepare dashboards and reconciliation queries.
11. Lock down go/no-go thresholds and decision authorities.
12. Send change-window notifications per organizational policy.

### 11.2. T-60 Minutes

- Open the war room/bridge per plan.
- Confirm step owners are online.
- Verify monitoring and alert channels.
- Verify backup/recovery artifacts are accessible.
- Check source/target status, listeners, services, and sessions.
- Confirm no unplanned deployments or jobs are running.
- Record change window start timestamp.

### 11.3. T-30 Minutes

- Stop or drain batch writers in order.
- Block new user/application transactions per freeze plan.
- Check active transactions and writer sessions.
- Record final SCN/watermark or replication state.
- Confirm source is ready for cutover.

### 11.4. T0 — Data Freeze and Final Sync

- Run final export or apply final delta.
- Wait for Data Guard/replication lag to reach target levels if used.
- Check redo gaps and CDC backlogs.
- Record SCN, timestamp, and logs.
- Never open target writers before the data barrier is confirmed.

### 11.5. T+ — Open Target

- Perform role transition or switch endpoints per runbook.
- Update services, DNS, and connection configurations.
- Start application instances in sequence.
- Verify runtime user, schema, and database identity.
- Run read-only smoke tests first, then controlled write tests.
- Ramp traffic progressively where architecture permits.

### 11.6. Post-Cutover Observation

Monitor:

- Connection failures and `ORA` errors.
- Transaction commits and rollbacks.
- P95/P99 latency.
- Connection pool saturation.
- CPU, memory, I/O, and redo generation.
- Tablespaces, TEMP, UNDO, and FRA.
- Scheduler jobs and batch queues.
- Data Guard transport/apply if standbys remain.
- Business control totals and duplicate keys.

### 11.7. Closing the Change Window

- Record final GO/NO-GO decision.
- Archive logs, SCNs, metric snapshots, and reconciliation reports.
- Document exceptions, owners, and remediation deadlines.
- Confirm the source database is in its intended state (read-only, stopped, or retained for fallback).
- Retain recovery artifacts per retention policy.
- Never drop restore points or reverse sync before explicit approval.

## 12. Rollback Decision Runbook

### 12.1. Classifying Incidents

When errors occur, triage quickly:

1. **Application-only:** binary/config bug while database data and schema remain sound.
2. **Connectivity:** service, listener, DNS, or credentials.
3. **Data mismatch:** missing, duplicate, or incorrect values.
4. **Schema/object:** `INVALID` objects, missing grants, unusable indexes.
5. **Performance/capacity:** latency, I/O, memory, FRA, tablespace limits.
6. **Database integrity:** corruption or recovery issues.
7. **External integration:** message, payment, or API side effects.

### 12.2. When to Choose Application Rollback

Choose when the bug lies in application code and the schema remains backward-compatible. Verify:

- Are old binaries compatible with the new schema?
- Are new background jobs writing data in a new format?
- Can feature flags disable the new behavior?
- Have external side effects already occurred?

### 12.3. When to Choose Traffic Rollback

Before switching back to source:

- Confirm source has the latest data or delta replay is ready.
- Confirm target stopped accepting writes.
- Confirm no jobs or consumers still write to target.
- Check idempotency and transaction duplication risks.
- Establish unambiguously which database is the authoritative writer.

### 12.4. When to Choose Restore/Flashback

Choose only when:

- The recovery point is clearly defined.
- Adequate backups or flashback logs exist.
- Losing post-marker transactions fits RPO or a replay plan exists.
- Recovery finishes within RTO.
- External side effects have compensation/reconciliation plans.
- Authorized leadership approves.

### 12.5. When to Choose Downgrade

Choose only when the Oracle downgrade guide confirms the source-target path, database state, and feature usage permit it. Verify `COMPATIBLE`, components, PDB/CDB, timezone files, Data Guard, and other constraints. If any prerequisite is uncertain, never run a downgrade in production "to see if it works."

### 12.6. When to Choose Forward Fix

Choose when the new database remains consistent and the bug can be safely patched. Identify:

- Root cause.
- Scope of affected rows/objects.
- Required DDL/DML.
- Locks and downtime.
- Roll-forward validation.
- Prevention of recurrence.

## 13. Example: Post-Cutover Decision Scenario

Suppose traffic switched to target and processed transactions for 20 minutes. End-of-day reports then appear wrong because the new application handles timezones differently.

Do not simply point endpoints back to source, because the target already accepted 20 minutes of transactions. Steps:

1. Halt or throttle the affected write flow.
2. Identify transactions from that 20-minute window and the timezone conversions applied.
3. Check whether source received those transactions via reverse replication.
4. If source did not receive them, determine how to export/replay or reconcile by business key.
5. If syncing back safely is not feasible, evaluate staying on target with a forward fix.
6. If target must be restored, quantify lost transactions and define replay/compensation workflows.
7. Business owner approves the decision balancing RPO and data integrity.

This scenario shows that rolling back traffic does not equal rolling back data.

## 14. Pre-Upgrade Oracle Checks

### 14.1. Identify Release and Database Identity

```sql
SELECT banner
FROM v$version
ORDER BY banner;

SELECT dbid,
       name,
       db_unique_name,
       database_role,
       open_mode
FROM v$database;

SELECT name, value
FROM v$parameter
WHERE name IN ('compatible', 'cluster_database');
```

### 14.2. Check Components

```sql
SELECT comp_id,
       comp_name,
       version,
       status
FROM dba_registry
ORDER BY comp_id;
```

Resolve failing components prior to upgrading per Oracle guidance. Never proceed while application-critical components are `INVALID` without knowing why.

### 14.3. Capture Invalid Objects Baseline

```sql
SELECT owner,
       object_type,
       COUNT(*) AS invalid_count
FROM dba_objects
WHERE status = 'INVALID'
GROUP BY owner, object_type
ORDER BY owner, object_type;
```

Save the baseline to separate pre-existing invalid objects from newly invalidated ones post-upgrade. Do not blindly demand zero invalid objects if Oracle or applications intentionally maintain specific invalid objects; classify them clearly.

### 14.4. Check Timezone File

```sql
SELECT * FROM v$timezone_file;
```

Plan `DBMS_DST` separately if a timezone file upgrade is in scope.

### 14.5. Check Data Guard

```sql
SELECT database_role,
       protection_mode,
       protection_level,
       switchover_status
FROM v$database;

SELECT name, value, unit, time_computed, datum_time
FROM v$dataguard_stats
WHERE name IN ('transport lag', 'apply lag');
```

On primary/standby, check destination statuses, broker configuration, and redo gaps using release-appropriate views and commands.

## 15. Upgrade Tools and Preupgrade Checks

### 15.1. Preupgrade Assessment

Before upgrading Oracle Database, run preupgrade checks with the release-matching tool, such as AutoUpgrade or `preupgrade.jar`/scripts per version guidance. Reports may surface:

- Parameters needing adjustment.
- Deprecated/obsolete parameters.
- Component issues.
- Invalid objects.
- Tablespace/capacity concerns.
- Time zone file requirements.
- Feature usage affecting upgrade or downgrade.

Never ignore warnings merely because the tool permits continuing.

### 15.2. AutoUpgrade

AutoUpgrade supports analysis, fixups, upgrading, and post-upgrade tasks in supported Oracle releases. Configs, modes, and fallback options vary by version. Follow release-specific docs and retain configs, logs, and outputs for audit.

### 15.3. Manual Upgrade

When running manual upgrades, strictly follow that release's Upgrade Guide. Never mix scripts from different Oracle Home versions. Check `ORACLE_HOME`, `PATH`, listeners, environment variables, and startup parameters beforehand.

### 15.4. Post-Upgrade Tasks

Post-upgrade, perform required tasks such as compiling invalid objects, validating components, timezone steps, optimizer statistics, and application tests per Oracle guidance. Never run arbitrary scripts without understanding their order and impact.

## 16. Data Guard and Fallback

### 16.1. Standbys as Part of Recovery Design

Standbys help cut RTO and enable role transitions, yet do not automatically serve as an upgrade rollback. Once both primary and standby are upgraded or receive new schema/data changes, never assume the standby remains on the old release ready to take over.

### 16.2. Switchover and Failover

- Switchover is a planned role swap between primary and standby.
- Failover promotes a standby to primary when the primary fails.
- Reinstatement depends on configuration and database state.

None of these equals a downgrade. Verify exact roles and versions on every database after each step.

### 16.3. Rolling Upgrades with Data Guard

Oracle documents supported rolling upgrade workflows for specific releases and topologies. They reduce downtime yet impose strict preconditions on release, redo transport, logical/transient logical standby, and feature compatibility. Follow only Oracle-published procedures.

### 16.4. Post-Role-Transition Checks

Verify:

- New database roles.
- Services registered on the right instances.
- Transport destinations pointing properly.
- Apply processes running actively.
- Application connection pools reconnected.
- Target protection mode/level achieved.
- Zero unresolved redo gaps or data divergence.

## 17. Data Pump Migrations and Rollback

### 17.1. Dump Files Are Not Rollback Points

A Data Pump dump is a logical export scoped to specific objects and a point in time. It does not replace RMAN backups, omits physical database state, and cannot automatically revert the source.

### 17.2. Retaining the Source

After Data Pump migration, retain the source database in a well-defined state until:

- Target reconciliation passes.
- Applications stabilize.
- Final deltas are applied.
- Business sign-off completes.
- The rollback window closes.

Never drop the source immediately after import finishes.

### 17.3. Post-Export Deltas

If source kept accepting writes after the export snapshot, capture and apply deltas. If target accepted writes, account for bidirectional deltas in fallback plans. Never rely on final row counts without knowing the snapshot boundary.

### 17.4. Data Pump VERSION

`VERSION` generates export metadata compatible with an older release within supported bounds; it does not provide a downgrade path for an upgraded database and does not guarantee all source features can import into target.

## 18. RPO, RTO, and Rollback Window Duration

### 18.1. RPO

Recovery Point Objective is the maximum data loss acceptable to the business. When picking a restore point or backup, decide whether post-marker transactions can be replayed.

### 18.2. RTO

Recovery Time Objective is the target time to restore service. Measure end-to-end:

- Detection and NO-GO decision.
- Stopping traffic and draining sessions.
- Restore/flashback/downgrade or endpoint switch.
- Data reconciliation/replay.
- Application startup and smoke tests.
- Business validation.

### 18.3. Rollback Window

The rollback window is how long fallback paths remain viable after cutover. Base it on:

- Change risk level.
- Batch and business cycles.
- Reconciliation time.
- Feasibility of keeping source and reverse sync.
- GRP/FRA capacity.
- Expected restore duration.

Never close the rollback window simply because the home page loads.

### 18.4. Closing the Rollback Window

After closing the rollback window, destructive actions—dropping source, dropping GRPs, contracting schemas, or raising `COMPATIBLE`—require separate change approval. Log the timestamp and rationale for closing the window.

## 19. Roles, Responsibilities, and Decision Authority

| Role | Responsibility |
|---|---|
| Change owner | Coordinates change, maintains timeline and decision log |
| DBA lead | Database upgrade, backups, recovery, data consistency |
| Application lead | Binaries/configs, compatibility, smoke tests |
| Infrastructure/network | Hosts, storage, networking, DNS, load balancers |
| Security | TDE, wallets, credentials, access control |
| Business owner | Approves business outcomes and data risk |
| Operations/NOC | Monitoring, alerting, incident response |
| Release manager | Approves deployments and change gates |

Designate one authority for final GO/NO-GO calls. Every gate needs a proposer, a verifier, and a recorder.

## 20. Decision Logs and Evidence

Every decision record should capture:

- Timestamp and timezone.
- Gate under evaluation.
- `GO`/`NO-GO`/`HOLD`.
- Supporting metrics and evidence.
- Proposer and approver.
- Residual risks.
- Next actions.
- Deadline or reassessment time.

Preserve artifacts:

- Change plan/runbook version.
- Preupgrade reports.
- RMAN backup logs and restore test evidence.
- GRP identifiers and FRA metrics.
- Export/import/upgrade logs.
- SCN/watermarks and data reconciliation reports.
- Invalid object and component reports.
- Application/APM metrics.
- Test results and business sign-offs.
- Rollback/forward-fix decision logs.

## 21. Sample Decision Matrix for an Oracle Upgrade

Suppose the database upgrades from an older release to a newer release while the Spring Boot application remains unchanged in phase one.

| Gate | Condition | Example Decision |
|---|---|---|
| Readiness | Preupgrade checks show component error | NO-GO until resolved |
| Backup | RMAN backup finished, restore untested | HOLD |
| Pre-cutover | Upgrade complete, newly invalid objects untriaged | HOLD |
| Data | Control totals match, constraints pass | Candidate for GO |
| Application | Smoke tests pass, P99 latency within bounds | Candidate for GO |
| `COMPATIBLE` | Still at prior compatibility level | Preserve downgrade path if Oracle-supported |
| Observation | One batch cycle still pending | Keep rollback window open |
| Final | Business owner signed off, monitoring stable | GO to close window per policy |

This illustrates decision-making structure; actual releases will define tailored conditions.

## 22. Lab Exercise: Rehearsing Cutover and Rollback

Run this in a lab/staging environment with representative data. Never test restores, flashbacks, or downgrades directly in production.

### Step 1 — Write Change Scope

Document database releases, schema changes, application versions, hosts/services, targets, and dependencies.

### Step 2 — Define Fallbacks

Specify application rollback, traffic rollback, GRP, RMAN restore, supported downgrade, or forward fix. Document conditions and timings for each.

### Step 3 — Capture Baseline

Record DB identity, `COMPATIBLE`, timezone file, components, invalid objects, row counts, and business totals.

### Step 4 — Backup and Recovery Rehearsal

Take appropriate backups, verify backup pieces, and rehearse restore/flashback in an isolated environment. Measure RTO.

### Step 5 — Simulate Cutover

Freeze source, record SCN, apply deltas, switch endpoints, and open traffic on target.

### Step 6 — Test Application Rollback

Deploy old application binaries against the new schema. Confirm whether the schema stays backward-compatible; if not, document the breaking DDL.

### Step 7 — Simulate Post-Cutover Writes

Generate transactions on target, then walk through a traffic rollback plan. Define replay/reverse sync steps so zero data is lost.

### Step 8 — Simulate NO-GO

Inject a test failure such as an unregistered service or control total mismatch. Follow the decision tree, stop opening traffic, and write the decision log.

### Step 9 — Evaluate Downgrade Path

Read the release-matching downgrade guide, verify `COMPATIBLE`/feature usage, and note which conditions close the downgrade path. Executing an actual downgrade is optional if no matching test setup exists.

### Step 10 — Finalize the Runbook

Record per-step timings, owners, commands, expected outcomes, stop gates, and recovery paths.

## 23. Pre-Change-Window Checklist

- [ ] Change scope, owners, and maintenance window approved.
- [ ] Oracle release/patches and supported upgrade/downgrade paths verified.
- [ ] Preupgrade assessment executed.
- [ ] Database components and invalid objects baseline saved.
- [ ] `COMPATIBLE` setting and raise timing decided.
- [ ] Timezone file plan confirmed.
- [ ] Application/schema compatibility reviewed.
- [ ] Expand-and-contract plan applied to destructive changes.
- [ ] RMAN backups and archived logs ready.
- [ ] Control files/SPFILE/password file/TDE wallets backed up.
- [ ] Restore rehearsal meets RTO.
- [ ] GRP/FRA prerequisites and capacity checked if used.
- [ ] Data Guard/standby/replication healthy.
- [ ] Data snapshot/SCN/delta plan clear.
- [ ] Row counts and business control totals baseline saved.
- [ ] Endpoint/DNS/service/connection pool switchover rehearsed.
- [ ] Pause/resume plans ready for batches and external integrations.
- [ ] Application rollback and database fallback documented separately.
- [ ] Reverse sync/reconciliation plan ready for post-cutover writes.
- [ ] RPO/RTO and rollback window approved by business owner.
- [ ] Go/no-go thresholds and decision authorities assigned.
- [ ] War room, escalation paths, and monitoring ready.

## 24. Cutover Checklist

- [ ] Readiness gate confirmed GO.
- [ ] Writers drained and batches stopped per runbook.
- [ ] Freeze SCN/watermark and timestamp recorded.
- [ ] Final delta applied and lag/gaps verified.
- [ ] Target role/open mode/services right.
- [ ] No two databases accepting unintended concurrent writes.
- [ ] Connection endpoints and credentials accurate.
- [ ] Smoke tests and controlled write tests pass.
- [ ] Business control totals and key reconciliations pass.
- [ ] Constraints, indexes, sequences, and grants verified.
- [ ] Error rate, latency, and capacity within thresholds.
- [ ] GO/NO-GO decision logged.

## 25. Post-Cutover and Closing Rollback Window Checklist

- [ ] Sufficient observation window and batch cycles elapsed.
- [ ] Zero unexplained application/database errors remain.
- [ ] Monitoring and alerting healthy.
- [ ] Final data reconciliation passes.
- [ ] External side effects and integrations verified.
- [ ] Business owner sign-off obtained.
- [ ] Official writer database confirmed.
- [ ] Old source retained or retired per retention plan.
- [ ] Reverse replication kept or stopped per decision.
- [ ] GRP retained or dropped per approval.
- [ ] Fresh post-cutover backup completed and verified.
- [ ] `COMPATIBLE` raised only when downgrade path is no longer needed and approved.
- [ ] Decision logs, metrics, and evidence archived.

## 26. Self-Check Questions

1. How does cutover differ from an application deployment?
2. How do `GO`, `NO-GO`, and `HOLD` differ?
3. How does application rollback differ from database restore?
4. Why does pointing DNS back to source not guarantee new data is preserved?
5. How does Oracle downgrade differ from restoring a backup?
6. When is a forward fix appropriate?
7. How does expand-and-contract reduce application rollback risk?
8. Why should destructive DDL be separated from the initial deployment phase?
9. Does blue-green automatically resolve data divergence?
10. When can canary traffic create dual writers?
11. How does Data Guard switchover differ from failover and downgrade?
12. Why isn't a standby automatically a rollback for a database upgrade?
13. Which artifacts besides datafiles does an RMAN backup strategy require?
14. Why run a restore rehearsal instead of just checking that backup jobs completed?
15. How do guaranteed restore points support upgrade fallbacks?
16. What FRA and flashback log requirements apply to GRPs?
17. Why isn't a GRP an independent backup?
18. How does `COMPATIBLE` affect downgrade eligibility?
19. How can using new features block downgrades?
20. Why is Data Pump `VERSION` not a database downgrade?
21. What must be checked regarding `TSTZ`/timezone file upgrades before fallback?
22. Why does rolling back after target accepts writes require reverse sync or reconciliation?
23. Which side effects can a database restore not undo automatically?
24. How do RPO and RTO shape fallback choices?
25. Which criteria belong in the pre-cutover gate?
26. Who should hold final GO/NO-GO decision authority?
27. When can the rollback window be closed?
28. Why retain the source database for a period after migration?
29. When should you pick forward fix over restore?
30. What must a rollback rehearsal prove?

**Key principle to remember:** Establish a single authoritative writer, snapshot/delta strategy, RPO/RTO, and fallback per stage upfront. Application rollback swaps binaries only; traffic rollback switches endpoints only; database restore/flashback rewinds data to a recovery point; downgrade is a distinct, bounded Oracle procedure. Raising `COMPATIBLE` or adopting new features can close the downgrade path. Once the target accepts writes, never route traffic back to source without a reverse sync/reconciliation plan. Declare GO only when data, applications, infrastructure, and recovery evidence meet agreed thresholds; close the rollback window only after business sign-off.
