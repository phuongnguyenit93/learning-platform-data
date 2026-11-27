# Cutover Plans, Incremental Delta Data, and Rollback When Validation Fails

Migrating an Oracle Database to a new server, PDB, data center, or environment does not end when export/import finishes. During preparation, source data can still change: users place orders, update customer records, payments are recorded, background jobs update statuses, and applications generate new transactions. If you only move a snapshot from one point in time and switch connections, changes occurring after the extraction point can be lost.

A cutover plan must define how to create a consistent initial dataset, how to capture and apply incremental data (delta), when to stop writes on the source, conditions permitting the application to switch to the target, and a rollback plan if validation fails. Specifically, once the application begins writing to the target database, returning to the source is no longer as simple as changing a connection string: new transactions on the target must be preserved or handled according to an explicit business decision.

## 1. Cutover Goals and Terminology

### 1.1. Data milestones

During a migration, distinguish the following milestones:

- **Source:** the database serving the application before migration.
- **Target:** the new database that will receive the application and transactions after cutover.
- **Baseline / initial load:** the initial dataset extracted from the source at a consistent point and loaded into the target.
- **Delta / change data:** changes occurring after the baseline point, including inserts, updates, and deletes.
- **Catch-up:** the process of applying outstanding deltas to the target so it approaches the source state.
- **Write freeze:** the point when new write transactions are stopped on the source to establish the final cutover boundary.
- **Cutover point:** the authorized moment to switch the application to the target.
- **Rollback window:** the post-cutover period during which operations keeps preparations ready and can fall back to the source per an established plan.

Baseline and delta must have a clear boundary. If the baseline includes a transaction and the delta applies that transaction again, data can be duplicated. If the baseline misses a transaction and the delta starts after that transaction, data will be lost. Defining the synchronization point is a vital part of the design.

### 1.2. Objectives to align on

Before selecting tools, the project team must agree on:

| Objective | Question to answer |
|---|---|
| Downtime | How long can the application stop writes or stop service? |
| RPO | What maximum time window of data loss is acceptable? |
| RTO | How long can it take from deciding to switch or roll back until service is ready? |
| Consistency | Which common data point must related tables and transactions reflect? |
| Delta mechanism | Use redo-based CDC, GoldenGate, application-level mechanisms, or custom extraction? |
| Rollback | If the target has already accepted new transactions, how will those transactions be preserved? |
| Acceptance | Which checks must pass before opening writes on the target? |

No single tool or cutover schedule fits every system. A small database may tolerate downtime for export/import and verification. A large transactional system requiring short downtime typically pre-loads a baseline and continuously syncs deltas while the source remains active.

## 2. Choosing a Migration Strategy

### 2.1. Offline migration (with downtime)

The simplest offline workflow is stopping writes on the source, exporting data, importing to the target, validating, and switching the application. Because the source stays frozen throughout, no continuous delta mechanism is needed.

Suitable when:

- Data volume and object count are small enough to export/import within the downtime window.
- Business operations can pause transactions temporarily.
- Target structure has planned migration changes.
- The organization prefers a workflow with fewer moving parts and accepts the agreed downtime.

The drawback is that downtime encompasses export, file transfer, import, object compilation, validation, and error handling. Rehearse with production-scale data to estimate realistic durations.

### 2.2. Pre-loading baseline, syncing deltas while source stays active

For systems needing short downtime, create a baseline at a consistent SCN, load it into the target while the source continues serving transactions, and continuously apply subsequent changes. Once delta lag approaches zero, the project team freezes writes on the source, waits for apply to finish, validates, and switches the application.

Commonly considered tools/mechanisms:

- Oracle GoldenGate or a redo-based CDC solution to capture and apply changes.
- Replication mechanisms already designed and supported in the current architecture.
- Application-layer outbox/event logs if the application is built to emit complete transaction events that can be replayed safely.
- Watermark-based delta extraction where data, schemas, and consistency requirements permit.

Data Pump can produce a consistent logical baseline using `FLASHBACK_SCN` or `FLASHBACK_TIME` under suitable conditions. However, Data Pump does not natively provide a continuous CDC stream tracking every post-baseline insert, update, and delete. Design a dedicated delta mechanism and define how deltas are applied to the target.

### 2.3. Comparing options

| Approach | Downtime | Advantages | Risks/conditions |
|---|---|---|---|
| Offline Data Pump | Higher; includes full export/import and validation. | Easy to organize, fewer sync components. | Needs a sufficient service outage window; must benchmark real timings. |
| Data Pump baseline + CDC | Usually short at cutover. | Loads most data ahead of time, waiting only for final deltas. | Requires SCN alignment, CDC management, transaction ordering, and apply error handling. |
| Transportable tablespaces + delta | Can be short for large datasets. | Moves datafiles quickly when conditions are met. | Requires self-containment, endianness, version, read-only, and specialized procedures. |
| Network migration/replication | Depends on technology and volume. | Can eliminate intermediate dump files. | Depends on network, privileges, compatibility, and load on both databases. |
| Application-level delta | Can be short if already built. | Can preserve business logic and event control. | Must fully handle updates/deletes, retries, ordering, and idempotency. |

Choose based on RPO/RTO, volume, change rate, Oracle version, schema structure, downtime tolerance, and operational capability. Do not pick CDC solely to reduce downtime if the team cannot monitor lag, resolve apply errors, and rehearse rollback.

## 3. Planning a Consistent Baseline

### 3.1. Why is a consistent point needed?

Suppose table `ORDERS` is exported at 10:00, yet table `PAYMENTS` is exported at 10:15 while transactions continue. An order created and paid between those two times can leave the two tables reflecting different states if the export did not use a consistent snapshot. On import, data may mismatch even though each table individually looks valid.

The baseline should reflect a unified logical point across related tables. With Data Pump, you can specify an SCN so objects export from the same snapshot when flashback and undo conditions allow.

### 3.2. Capturing the SCN for the baseline

You can obtain the current SCN with:

```sql
SELECT current_scn
FROM v$database;
```

Or using the package:

```sql
SELECT dbms_flashback.get_system_change_number AS baseline_scn
FROM dual;
```

Record the SCN, timestamp, database identity, PDB/container, and export start time. An SCN is a logical database marker, not a wall-clock timestamp. Never convert SCNs to wall-clock time via linear arithmetic.

### 3.3. Exporting with FLASHBACK_SCN

Example Data Pump parfile:

```text
DIRECTORY=DP_DIR
DUMPFILE=app_baseline_%U.dmp
LOGFILE=app_baseline.log
JOB_NAME=APP_BASELINE_EXPORT
SCHEMAS=APP
FLASHBACK_SCN=123456789012
PARALLEL=4
LOGTIME=ALL
METRICS=YES
```

Run:

```bash
expdp app_migration@SOURCEPDB PARFILE=app_baseline.par
```

Replace the example SCN with the actual recorded value. `FLASHBACK_SCN` tells Oracle to read consistent data as of that SCN. The job can fail with snapshot/undo errors if it needs block versions whose undo was overwritten or is no longer available. Assess export duration, change rate, and undo configuration before picking the baseline SCN.

`FLASHBACK_TIME` can also specify a timestamp; Oracle maps that time to an appropriate SCN. For runbooks requiring an exact boundary between baseline and CDC, recording the actual SCN used is clearer.

### 3.4. Aligning baseline with CDC

For redo-based CDC, the team must pinpoint exactly where capture starts relative to the baseline SCN. The goal is:

- Every transaction already reflected in the baseline is not re-applied in a way that causes duplicates.
- Every transaction committed after the baseline boundary is captured and applied.
- Transactions open at baseline time are handled properly according to the tool's snapshot/commit rules.
- No log gaps exist between capture initialization and continuous tracking.

GoldenGate and CDC tools have dedicated instantiation/initial-load procedures. Use the exact SCN synchronization or checkpoint process supported by the tool; never guess an approximate SCN from wall-clock time. Test on a clone to prove zero lost or duplicated transactions at the boundary.

## 4. Designing and Applying Incremental Data (Delta)

### 4.1. What changes must delta include?

A complete delta must account for:

- **INSERT:** new records created after the baseline.
- **UPDATE:** changes to existing record values.
- **DELETE:** records deleted from the source.
- **DDL:** structural changes such as adding columns, changing types, creating indexes, or altering constraints.
- **Sequences/identities:** key-generation values advancing while the application stays active.
- **Dependent data:** child tables, audit tables, workflow states, LOBs, and data updated by background jobs.

Extracting only newly created rows misses updates and deletes. Relying solely on `updated_at` misses hard deletes unless tombstones or dedicated capture exist. Multi-table migrations must also preserve proper transaction ordering and boundaries.

### 4.2. Redo-based CDC

Redo-based CDC reads change information from redo/archive logs and translates it into apply operations on the target. Oracle GoldenGate is a common solution for this architecture. Depending on version and configuration, CDC can capture inserts/updates/deletes, preserve commit order, track checkpoints, and apply transactions.

Prerequisites to prepare:

- Enable appropriate supplemental logging to capture necessary keys and data.
- Confirm archive logs are retained long enough for Extract to read through lag or outages.
- Grant capture/apply privileges per tool and version guides.
- Confirm tables have suitable identifying keys; tables lacking primary keys may need unique keys or extra configuration.
- Define handling for DDL, LOBs, sequences, partitions, and special data types.
- Monitor checkpoints, trails/staging data, apply lag, errors, and conflicts.
- Ensure the target is initialized from the baseline at the exact SCN using the tool's instantiation workflow.

Never treat CDC as a flawless automatic mirror. Missing logging, missing archive logs, unsupported tables, or apply process errors can stall deltas. Establish alerts and lag-remediation runbooks before cutover day.

### 4.3. Data-layer watermark deltas

For small systems or table sets with strict update rules, deltas can be extracted using a timestamp or change-sequence column. Example:

```sql
SELECT order_id, customer_id, status, total_amount, updated_at
FROM app.orders
WHERE updated_at > :last_successful_watermark
  AND updated_at <= :high_watermark;
```

Where:

- `last_successful_watermark` is the last marker successfully applied.
- `high_watermark` is the fixed cutoff for the current extraction batch.
- Only advance the watermark after loading and verifying the delta successfully.

Do not fetch a fresh `SYSTIMESTAMP` per table within the same batch if a unified snapshot is needed. Choose one shared high watermark, record it, and apply it across all related tables.

Timestamp approaches carry major limitations:

- `updated_at` must be updated on every write path, including batch jobs and admin tasks.
- Timezone and timestamp precision must be standardized.
- Transactions starting before the watermark yet committing afterward can be missed if update timestamps do not reflect commit time.
- Hard deletes do not appear in standard delta queries.
- Late-arriving records or backdated timestamps can break watermarks.
- Extracting multiple tables at different snapshots can yield inconsistent states.

If watermarks are still used, employ an overlap window and idempotent upsert logic, recognizing that overlap only mitigates certain risks and does not solve deletes, late commits, or transaction ordering. Use audit/tombstone tracking for deletes and reconcile after every apply.

### 4.4. Why ORA_ROWSCN should not be treated as complete CDC

`ORA_ROWSCN` can expose SCN information associated with row changes, yet it is not always an exact per-row timestamp. Unless a table uses `ROWDEPENDENCIES`, the value may reflect block-level changes. Nor does it preserve deleted records or historical versions.

Therefore, never rely solely on `ORA_ROWSCN` to capture all deltas for a critical migration. Use checkpointed/redo-based CDC or an explicitly designed change log.

### 4.5. Applying deltas idempotently

An idempotent delta operation can be rerun without producing unintended side effects. For upserts, use `MERGE` on a stable key:

```sql
MERGE INTO target_orders t
USING staging_orders_delta s
   ON (t.order_id = s.order_id)
WHEN MATCHED THEN
    UPDATE SET
        t.status       = s.status,
        t.total_amount = s.total_amount,
        t.updated_at   = s.updated_at
WHEN NOT MATCHED THEN
    INSERT (order_id, status, total_amount, updated_at)
    VALUES (s.order_id, s.status, s.total_amount, s.updated_at);
```

This example illustrates upsert only; add real columns and business rules. For deletes, record tombstones or delete events and apply deletes by exact key. You cannot reconstruct deletes merely by comparing surviving rows without a complete baseline or log.

When deltas are re-applied multiple times, include duplicate guards such as unique event IDs, sequence/checkpoints, unique constraints, or controlled merge logic. Never assume every `INSERT` is safe to retry.

### 4.6. Preserving transaction order and table dependencies

A single business transaction can update multiple tables. If deltas are split across files or batches and applied out of order, foreign keys may temporarily fail or invalid business states may emerge.

- Prefer CDC tools that preserve commit order and transaction boundaries.
- If processing in batches, map parent/child relationships and load order.
- Avoid running parallel delta streams over the same keys when update order matters.
- Check for deadlocks, conflicts, and apply errors before declaring delta complete.
- Never discard failed transactions just to force lag to zero; define a handling and logging workflow.

## 5. Managing DDL and Non-Table Objects

During baseline and CDC, schema changes can cause the target to diverge from the source structure. For example, if the source adds a column after baseline export, CDC may not create that column on the target unless DDL replication is configured.

Before and during migration:

- Enforce a **DDL freeze** or synchronized schema release process between source and target.
- Inventory sequences, identities, triggers, procedures, packages, views, synonyms, materialized views, and scheduler jobs.
- Define how grants, roles, database links, directories, network ACLs, credentials, wallets, and external tables are synchronized.
- Clarify which objects are deployed by migration scripts versus created by Data Pump.
- Check invalid objects and dependencies after each import.

Sequences and identities require dedicated handling. If the source application keeps generating keys during baseline/delta, target sequences may lag behind source-issued values. Before opening writes on the target, verify next values are safe and will not collide with loaded data. Never edit dictionary tables directly; use version-appropriate DDL/APIs and application procedures.

Scheduler jobs or triggers that send emails, call APIs, issue payments, publish messages, or create external transactions must be controlled. While testing the target, never let production jobs run concurrently and cause duplicate side effects. Enable them only in the approved cutover sequence.

## 6. Preparation Before Cutover Day

### 6.1. Surveying source and target

Record at minimum:

- Oracle version, patch level, edition, character set, timezone file, and compatibility.
- DBID, DB_NAME, DB_UNIQUE_NAME, CDB/PDB, service names, and RAC/Data Guard topology if present.
- Schemas, tablespaces, datafiles, LOBs, partitions, object dependencies, and storage sizes.
- Database links, directories, external tables, ACLs, wallets, credentials, and background jobs.
- Users, roles, system privileges, object privileges, quotas, and profiles.
- Application configurations, connection pools, secrets, DNS/service discovery, and firewalls.
- Backups, recovery, CDC, archive log retention, and recoverability.

Do not focus solely on table counts. External dependencies outside the database—filesystem files, message queues, schedulers, APIs, certificates, and secrets—can also break the application after cutover.

### 6.2. Full rehearsal

Run at least one migration rehearsal with production-like data volume and change rates. Measure baseline export/import duration, delta apply time, CDC lag, validation, cutover, and rollback. Convert manual steps into a repeatable runbook.

Testing only on a tiny database yields unrealistic timings. Test peak-load periods, large LOB tables, partitions, long-running transactions, and background jobs.

### 6.3. Establishing go/no-go criteria

Criteria must be measurable and have accountable sign-off owners. Example:

| Category | Condition permitting cutover |
|---|---|
| Baseline | Export/import complete; no missing dump pieces; logs reviewed. |
| Delta | CDC/apply has zero unresolved errors; lag below agreed threshold. |
| Data integrity | Primary keys, foreign keys, row counts, and business reconciliations meet thresholds. |
| Schema | Critical objects exist and compile; grants and quotas are accurate. |
| Application | Smoke tests, login, test read/write transactions, and integration flows pass. |
| Performance | Critical queries and flows stay within accepted bounds. |
| Operations | Target backups, monitoring, alerting, secrets, and operational access are ready. |
| Rollback | Runbook, rollback window, and post-cutover transaction preservation plan are approved. |

Never let a single lag metric replace all checks. For instance, lag = 0 with unresolved apply errors is still a failure. Conversely, slight lag with zero errors within agreed thresholds may be handled per plan depending on RPO and business rules.

## 7. Controlled Cutover Procedure

### 7.1. Preparation phase

Before the cutover window:

1. Complete baseline import on the target.
2. Start CDC/delta apply and monitor until steady.
3. Finalize schemas, grants, sequences, services, wallets, database links, and application configs.
4. Run preliminary validation and read-only smoke tests on the target.
5. Verify source and target backups; guarantee a pre-cutover recovery point.
6. Notify users, support teams, and integration partners of the maintenance window.
7. Prepare scripts/commands for write freeze, connection draining, final delta apply, service switch, and rollback.

### 7.2. Starting the write freeze on source

At the agreed time:

- Put the application into maintenance mode or block data creation/update functions.
- Stop or temporarily disable batches/jobs that can write to target schemas.
- Drain connection pools and active write sessions per application procedure.
- Confirm zero open business transactions remain.
- If multiple write producers exist, lock all producers; stopping only one web app may be insufficient.

Never shut down the database abruptly while transactions are active. Allow transactions to finish or handle per business policy, then verify writes are closed.

### 7.3. Capturing the final delta

Once source writes have stopped:

1. Record the final SCN or checkpoint per the CDC mechanism.
2. Wait for Extract/transport/apply to process all changes committed before the write freeze.
3. Confirm zero unresolved lag and zero transaction apply errors.
4. If using watermarks, fix the final high watermark and extract all changes in scope, including deletes per the designed mechanism.
5. Record the timestamp, final SCN/checkpoint, and event count.

Never open target writes while source deltas remain unapplied. If transactions errored, explicitly resolve and rerun; never skip errors just to display a fake zero lag.

### 7.4. Reconciling and verifying target

Run the checks defined in the validation plan. Data reconciliation should use the same snapshot point and filter rules on both databases. Freezing the source makes comparison deterministic.

Also check:

- Sequences/identities can issue keys without collisions.
- Non-business scheduler jobs and triggers are not enabled prematurely.
- Services, connection strings, wallets, and credentials point to the target.
- Network routes and integration permissions are ready.
- Target monitoring, alerting, backups, and support operations are active.

### 7.5. Switching the application to target

Once gates pass and authorized approvers sign off:

1. Switch service names, connection strings, DNS, or service discovery configurations to the target per the rehearsed plan.
2. Start applications and fresh connection pools.
3. Run designated smoke tests: login, read data, create a controlled test transaction, update, and query back.
4. Confirm test transactions do not trigger unintended external side effects.
5. Open user writes in waves or by percentage if supported by the architecture.
6. Monitor error rates, latency, sessions, locks, jobs, CDC, and business data.

At this point the target becomes the authoritative data source. Record the exact cutover timestamp and the first target transaction.

### 7.6. Holding the source during the rollback window

During the post-cutover observation window:

- Keep the source unable to receive application writes.
- Do not drop schemas, datafiles, database links, or backups needed for rollback.
- Retain backups and logs sufficient to recover either side.
- Prevent both databases from accepting business transactions for the same dataset concurrently.
- Monitor approved health metrics and rollback triggers.

If the source keeps accepting writes alongside the target without a designed multi-master architecture, data diverges and merging becomes extremely hard. Exactly one write authority must exist at all times.

## 8. Data Reconciliation and Application Verification

### 8.1. Row counts by table or partition

Comparing row counts is the foundational check. Count per table:

```sql
SELECT COUNT(*) AS row_count
FROM app.orders;
```

For large tables, compare by partition, key range, or time bucket to isolate discrepancies quickly. Optimizer statistics are not always exact counts; when exact proof is required, run appropriate count queries or an agreed reconciliation method.

### 8.2. Reconciling business aggregates

Example comparing order counts and totals by status:

```sql
SELECT status,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM app.orders
GROUP BY status
ORDER BY status;
```

Run the exact same query on source and target at the same recovery point. Supplement with min/max dates, unique customer counts, balance totals, daily transaction counts, and other critical metrics.

### 8.3. Checking relationships and anomalous data

Useful checks:

- Child records lacking matching parent records.
- Duplicate primary or business keys.
- Unexpected `NULL`s in mandatory columns.
- Status values outside allowed domains.
- Sequences/identities risking key collisions.
- Mismatched amounts, balances, or payment statuses.
- Incomplete LOBs, referenced files, or external data.

Example finding orders referencing non-existent customers:

```sql
SELECT COUNT(*) AS orphan_orders
FROM app.orders o
WHERE NOT EXISTS (
    SELECT 1
    FROM app.customers c
    WHERE c.customer_id = o.customer_id
);
```

If tables have enabled and validated foreign keys, some anomalies are already prevented; still, verify constraints are actually enabled and validated after import. Never assume every constraint was created or enabled.

### 8.4. Hashes/checksums and limits

Keyed checksums or hashes can help spot differences across large datasets. However, standardize data representation, `NULL` handling, timezones, decimals, CLOB/BLOBs, and row order. Hashing does not prove every business nuance; it is a supplementary layer.

Avoid concatenating an entire table into a giant string in one SQL query. Split by partition or key range, compute stable fingerprints, and compare segments to locate differences.

### 8.5. Functional and performance verification

Minimum smoke tests must exercise critical business paths:

- Login and authentication.
- Historical data lookups.
- Creating a controlled test transaction.
- Updating status and reading back.
- Verifying reports, batches, and integration APIs.
- Verifying user/role privileges and sensitive data protection.
- Checking critical query latencies, connection pools, and application logs.

A database may open cleanly yet applications still fail due to missing grants, synonyms, database links, wallets, directories, ACLs, jobs, or service configurations.

## 9. Designing Rollback

### 9.1. Rollback before target receives writes

This is the simplest case. If the target has not received business transactions and the source remains intact:

1. Place the target in maintenance/read-only mode or block writes.
2. Switch services/connection strings back to the source.
3. Re-enable source applications and jobs in sequence.
4. Verify transactions and connections on the source.
5. Document the failed cutover root cause and preserve logs.

Because the source did not change during target testing, no new target data needs merging back, aside from cleaning up or accounting for deliberate test transactions.

### 9.2. Rollback after target has received writes

Once the target accepts real transactions, the source becomes stale. Simply pointing services back to the source loses target-written transactions and can cause duplicate IDs or broken business states.

Before cutover, select one of these strategies:

- **Reverse replication/CDC:** prepare capability to capture changes from the target and apply them back to the source if rollback triggers.
- **Controlled reconciliation:** stop target writes, extract and reconcile all new transactions, and apply them to the source via a tested procedure.
- **No rollback after write gate:** define clearly that past a certain business threshold only forward-fix or recovery to another target is permitted; no falling back to the old source.
- **Business-approved data loss:** only in exceptional cases, authorized decision-makers accept data loss within a clearly bounded and documented scope.

Never assume unidirectional source-to-target CDC can reverse itself automatically. Reverse replication must be configured and tested for conflicts, sequences, DDL, and transactions before cutover. Without a reverse path, define a concrete reconciliation workflow or explicit rollback cutoff.

### 9.3. Rollback decision table

| Situation | Appropriate action |
|---|---|
| Service not yet switched, target received no writes | Abort cutover; continue serving from source. |
| Target opened yet only smoke tests ran with no business data | Account for all test transactions; switch back to source if nothing needs retaining. |
| Target received real transactions, reverse CDC active and verified | Stop target writes, drain apply, sync back to source, reconcile, then switch services. |
| Target received writes with no reverse path | Stop writes, evaluate reconciliation; do not switch back to source before a data-preservation decision. |
| Target suffers severe failure yet data remains accessible | Consider forward-fix or building a new target from backup/CDC based on RTO and integrity. |
| Both source and target unavailable | Activate DR/recovery plan; select recovery point per RPO and approved runbooks. |

### 9.4. Controlled rollback steps

1. Incident commander or authorized lead declares rollback per predefined criteria.
2. Block all new transactions to target and drain write sessions.
3. Record timestamp, final SCN/checkpoint, and list of committed transactions on target.
4. Execute the target-delta preservation strategy: reverse CDC, export/reconcile, or business-approved decision.
5. If using reverse CDC: confirm capture/apply finished with zero conflicts or failed transactions; verify data on source.
6. If reconciling: snapshot/back up target, extract deltas, match keys, and apply in designed transaction order.
7. Confirm source holds expected final data, safe sequences, and healthy objects/jobs.
8. Switch services to source and reopen writes gradually.
9. Run smoke tests, inspect errors, and perform business reconciliation.
10. Keep the target along with logs/backups for investigation; clean up only after the rollback window closes with approval.

Never wipe the target immediately after rolling back. The target holds forensic evidence of the failure and newly created transactions; retain it long enough for investigation and data preservation.

## 10. Scenarios That Commonly Break Rollback

### 10.1. Both databases accepting writes

If both source and target process transactions for the same business domain, they diverge into two conflicting versions. Primary keys collide, balances diverge, and event ordering cannot be restored with a simple export.

Enforce a single write authority at all times. If dual-write or active-active is required, that is a dedicated architecture needing conflict resolution, transaction semantics, and separate testing—not a cutover workaround.

### 10.2. Insufficient archive log or CDC trail retention

If archive logs are deleted before Extract finishes reading, CDC can lose its ability to resume from checkpoint. If trails are purged or storage fills, deltas stall. Before migration, size retention for peak change rates plus incident recovery time, and alert on rising lag.

### 10.3. Schema changes during synchronization

DDL can cause source and target structures to diverge, breaking apply or dropping data. Enforce a DDL freeze or synchronized DDL rollout; verify CDC tool DDL support and handle uncaptured changes manually.

### 10.4. Sequences and external side effects

Target transactions may call payment gateways, send emails, or emit messages. Rolling back the database does not undo external side effects. Control jobs and integrations during smoke tests; use sandboxes or side-effect suppression in test runs.

Sequences may also advance on the target even for rolled-back transactions. When returning to source, verify sequence/identity values so duplicates are avoided. For committed transactions, preserve ordering and issued identifiers.

### 10.5. Failing to define rollback expiration

Keeping the old source alive too long raises cost and risk of confusion; deleting it too early destroys rollback capability. Define the rollback window, exit criteria, approvers, and end-of-window actions. Once the window closes, archive or decommission the old source per approved procedure.

## 11. Timeline-Based Sample Runbook

A cutover runbook must specify owners, verifiers, commands/tools, expected outputs, and timeboxes for every step. Example:

| Phase | Tasks | Gate/evidence |
|---|---|---|
| T-14 days | Survey, identify schemas, dependencies, capacity, and delta strategy. | Scope and RPO/RTO approved. |
| T-7 days | Rehearse baseline, delta, validation, and rollback. | Actual timings and defects logged. |
| T-1 day | Verify backups, CDC lag, disk space, privileges, job schedules, and contacts. | Readiness checklist signed off. |
| T-30 minutes | Announce maintenance, prep services, and monitor source/target. | Coordinator confirms start. |
| T0 | Enable write freeze, stop writer jobs, and drain sessions. | Zero active source write transactions. |
| T+ | Lock final SCN/checkpoint and apply final delta. | Tool lag = 0, zero apply errors. |
| T+ | Reconcile data, verify schemas and applications. | All acceptance gates pass. |
| T+ | Go/no-go approval; switch services to target. | Cutover point recorded. |
| Post-cutover | Smoke test, open writes, monitor, and hold source. | Target healthy within thresholds; rollback window starts. |
| End of window | Confirm stability, finalize backups, and handle old source. | System owner approves closing rollback window. |

Timelines are illustrative only. Real runbooks must base durations on rehearsals and organizational change management procedures.

## 12. Cutover and Rollback Reporting Template

Every migration should archive a record containing:

| Field | Details to record |
|---|---|
| Source/target | DB_NAME, DB_UNIQUE_NAME, DBID, service, PDB, and version. |
| Baseline | SCN/time, Data Pump job, dump set, logs, and completion time. |
| Delta | Tool, start/end checkpoints, lag, transaction counts, and apply errors. |
| Write freeze | Start timestamp, verifier, stopped sessions/jobs. |
| Validation | Row counts, aggregates, key/constraint checks, smoke test results. |
| Go/no-go | Decision, approver, and rationale. |
| Cutover | Service switch timestamp, first transaction on target. |
| Rollback | Conditions, timestamp, reverse/reconciliation method, and outcome if triggered. |
| RPO/RTO | Achieved recovery point and service restoration duration. |
| Follow-up | Remaining issues, owner, deadline, and closure evidence. |

Never include passwords, key material, or real personal data in reports. Reference secret IDs and store documents in access-controlled locations.

## 13. Operational Principles to Remember

- Establish a consistent baseline SCN and record it explicitly.
- Data Pump creates a logical baseline; it does not replace CDC for post-baseline changes.
- Deltas must cover inserts, updates, deletes, and relevant structural/identity changes.
- Align CDC checkpoints with the baseline using tool-supported mechanisms; never guess boundaries.
- Retain archive logs/trails long enough for CDC catch-up and outage recovery.
- Maintain a single write authority for any dataset during cutover.
- Freeze writes, drain transactions, and apply final deltas before opening target writes.
- Set measurable acceptance gates with accountable approvers.
- If the target has received writes, never fall back to the old source before preserving target transactions.
- Verify sequences, jobs, triggers, database links, and external side effects.
- Rehearse both cutover and rollback in a production-equivalent environment.
- Retain source, backups, and logs through the rollback window; clean up only after approval.

## Conclusion

A safe migration coordinates a consistent baseline, delta synchronization, write freeze, validation, and gated cutover. SCNs anchor the snapshot; CDC or change logs carry subsequent inserts, updates, and deletes. When switching applications, confirm source writes have stopped, deltas are fully applied, and data/application checks pass. Design rollback beforehand—especially once the target accepts real transactions—using tested reverse replication or reconciliation to preserve data. Rehearsing the entire workflow and measuring RPO/RTO is what proves the plan works when an incident occurs.
