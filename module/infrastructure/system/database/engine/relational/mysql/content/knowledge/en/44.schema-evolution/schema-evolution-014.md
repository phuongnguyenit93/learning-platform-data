# Data Verification, Access Privileges, and Rollback Planning After Migration

A schema migration is complete only when the new structure is accurate, data preserves its meaning, the application accesses objects with the proper privileges, and operations has a recovery path if errors are found. An `ALTER TABLE` statement succeeding only proves MySQL executed the structural change; it does not prove data converted accurately, application queries remain compatible, or access privileges remain valid.

In MySQL, many DDL statements implicitly commit the active transaction. Therefore, you cannot treat a series of `ALTER TABLE`s, backfills, and application updates as one single transaction to `ROLLBACK` on failure. A rollback plan must be designed before the migration, covering checkpoints, backups, reverting the application to the previous version, and handling records created after cutover.

This lesson uses MySQL 8.4, InnoDB, and a phased migration rollout workflow. Adapt the examples to your actual table sizes, workloads, replication topology, and business requirements.

## Objectives

After this lesson, you will be able to:

- Define structural, data, and application behavior verification criteria before and after migration.
- Check row counts, `NULL` values, duplicate keys, orphaned records, and backfill outcomes.
- Verify migration and application account privileges under least-privilege principles.
- Explain why DDL cannot be rolled back like DML and distinguish atomic DDL from transaction rollback.
- Design migrations using expand-contract to preserve compatibility across old and new application versions.
- Plan rollbacks, backups/PITR, replica checks, and go/no-go rollout gates.

## 1. Define the migration contract before running

Every migration needs a concise, verifiable specification. This specification acts as a contract across the migration author, deployer, tester, and on-call operator.

| Item | Questions to answer |
|---|---|
| Objective | Which schema or data behavior will change? Why is the change needed? |
| Scope | Which databases, tables, columns, indexes, constraints, views, triggers, or routines are affected? |
| Compatibility | Can current and new application versions coexist during the transition window? |
| Data | Under what business rules is legacy data transformed? Which values are kept, transformed, or dropped? |
| Privileges | What privileges does the deployment account need? What privileges does the runtime account need post-migration? |
| Load and locks | Could DDL rebuild tables, hold metadata locks, or generate heavy load, and for how long? |
| Verification | Which queries, metrics, and application flows prove the migration succeeded? |
| Rollback | Can a reverse migration run? If not, how will backup/PITR or forward-fix be used? |

Record schema version before and after, migration ID, migration file checksum, deployment timestamp, operator, and verification results. If using a migration tool with a history table, ensure the status recorded there accurately reflects reality. Never mark a migration complete merely because the tool submitted the statement; verify both database and application afterward.

## 2. Pre-migration checks

### 2.1. Capture current schema state

Save table definitions and dependent objects before changing anything:

```sql
SHOW CREATE TABLE app_db.customers\G
SHOW CREATE VIEW app_db.customer_summary\G
SHOW TRIGGERS FROM app_db;
```

You can also query structured metadata in `INFORMATION_SCHEMA`:

```sql
SELECT TABLE_NAME, ENGINE, TABLE_COLLATION
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'app_db';

SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE,
       IS_NULLABLE, COLUMN_DEFAULT, EXTRA
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'app_db'
ORDER BY TABLE_NAME, ORDINAL_POSITION;

SELECT TABLE_NAME, INDEX_NAME, NON_UNIQUE,
       SEQ_IN_INDEX, COLUMN_NAME
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = 'app_db'
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
```

Reconcile all relevant indexes, foreign keys, check constraints, triggers, views, stored procedures, functions, and events. A migration renaming or dropping a column can break views or routines even though `ALTER TABLE` succeeds. Save `SHOW CREATE` outputs or schema dumps in version control for later comparison.

### 2.2. Measure baseline data and workload

Collect baseline metrics before changing:

```sql
SELECT COUNT(*) AS total_rows,
       SUM(email IS NULL) AS email_nulls,
       COUNT(DISTINCT customer_id) AS distinct_ids
FROM app_db.customers;

SELECT status, COUNT(*) AS row_count
FROM app_db.customers
GROUP BY status
ORDER BY status;
```

On large tables, `COUNT(*)`, `COUNT(DISTINCT ...)`, or full-table checksums read massive data and create load. Run them on a suitable replica, across primary-key ranges, or during a low-load window. Never fire multiple concurrent full-table scans on production just to check off a checklist.

Also record critical queries, p95/p99 latency, error rates, connection counts, replication lag, and CPU/I/O utilization. Compare against baseline post-migration to spot performance regressions or query errors.

### 2.3. Validate legacy data preconditions

Before adding `NOT NULL`, `UNIQUE`, `CHECK`, or foreign keys, verify whether existing data satisfies the new rules.

Find missing values:

```sql
SELECT COUNT(*) AS missing_email
FROM app_db.customers
WHERE email IS NULL OR TRIM(email) = '';
```

Find duplicates before adding a unique index:

```sql
SELECT normalized_email, COUNT(*) AS occurrences
FROM app_db.customers
GROUP BY normalized_email
HAVING COUNT(*) > 1;
```

Find orphaned child records before adding a foreign key:

```sql
SELECT o.customer_id, COUNT(*) AS orphan_orders
FROM app_db.orders AS o
LEFT JOIN app_db.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.customer_id IS NULL
GROUP BY o.customer_id;
```

If violations exist, agree on cleanup rules with the business owner. Never arbitrarily pick rows to delete or merge just to force a migration through. Record affected records and remediation outcomes for reconciliation.

## 3. Post-migration verification

Verification should span three layers: structure, data, and behavior. Each layer requires concrete expected outcomes.

### 3.1. Confirm the new structure

After DDL, re-read the table definition:

```sql
SHOW CREATE TABLE app_db.customers\G

SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE,
       COLUMN_DEFAULT, EXTRA
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'app_db'
  AND TABLE_NAME = 'customers'
ORDER BY ORDINAL_POSITION;

SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = 'app_db'
  AND TABLE_NAME = 'customers'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

Verify names, types, lengths, charset, collation, nullability, defaults, generated columns, indexes, and constraints. Do not check only that the new column appeared; confirm indexes and constraints have exact column ordering, names, and attributes.

### 3.2. Verify row counts and completeness

Compare row counts before and after under identical filters and data cutoffs. If the application writes continuously during verification, counts change naturally; use a consistent snapshot/cutoff, planned write pause, or reconciliation over a fixed key set. If the migration should neither add nor delete rows, counts at the same cutoff must match. If transformations alter row counts, document exact rules and expected counts.

Example checking a backfilled new column:

```sql
SELECT COUNT(*) AS total_rows,
       SUM(status_v2 IS NULL) AS status_v2_nulls
FROM app_db.customers;
```

Check distribution of new values:

```sql
SELECT status_v2, COUNT(*) AS row_count
FROM app_db.customers
GROUP BY status_v2
ORDER BY status_v2;
```

Reconciling across primary-key buckets helps isolate discrepancies:

```sql
SELECT
  FLOOR(customer_id / 10000) AS id_bucket,
  COUNT(*) AS row_count,
  SUM(status_v2 IS NULL) AS missing_count
FROM app_db.customers
GROUP BY FLOOR(customer_id / 10000)
ORDER BY id_bucket;
```

Choose bucket sizes suited to key distribution and table size. When keys have gaps, arithmetic buckets become uneven; use explicit `customer_id >= ... AND customer_id < ...` ranges when inspecting exact intervals.

### 3.3. Verify values with null-safe comparisons

In MySQL, `<=>` compares two values safely with respect to `NULL`: `NULL <=> NULL` evaluates to true. This is helpful when comparing old and new values after backfilling.

Suppose `status_v2` must match a mapping from `status`:

```sql
SELECT customer_id, status, status_v2
FROM app_db.customers
WHERE NOT (
  status_v2 <=> CASE status
    WHEN 'A' THEN 'ACTIVE'
    WHEN 'I' THEN 'INACTIVE'
    WHEN 'P' THEN 'PENDING'
    ELSE 'UNKNOWN'
  END
)
LIMIT 100;
```

The expected result is zero rows, aside from explicitly documented exceptions. If the mapping handles `NULL`, empty strings, or invalid codes specially, reflect that explicitly in both the `CASE` expression and verification criteria.

For numeric or date/time conversions, verify both unconvertible counts and conversion accuracy. For example, when converting `amount_text` to `DECIMAL`, do not check only for empty strings; verify precision, decimal places, rounding, and business bounds.

### 3.4. Verify constraints and reference data

After adding constraints, confirm they exist:

```sql
SELECT CONSTRAINT_NAME, CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = 'app_db'
  AND TABLE_NAME = 'orders';

SELECT CONSTRAINT_NAME, COLUMN_NAME,
       REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = 'app_db'
  AND TABLE_NAME = 'orders';
```

Test both valid and invalid operations in a test environment to confirm constraints enforce as intended. For check constraints, MySQL enforces them starting in MySQL 8.0.16; verify the exact server version and constraint definition on the target host.

Never use `SET foreign_key_checks = 0` as a substitute for verification. When disabling foreign key checks, MySQL does not re-validate rows loaded while disabled once you turn the variable back on. If data was loaded with checks disabled, run explicit queries for orphaned rows before treating data as valid.

### 3.5. Verify replicas and performance

With asynchronous replication, confirm DDL and data have applied on all required replicas before routing read traffic or running the next contract step. Check:

```sql
SHOW REPLICA STATUS\G
```

For Group Replication, inspect member state and recovery/applier Performance Schema tables; `SHOW REPLICA STATUS` is not a general check for internal Group Replication channels. Never judge a replica by a single lag number alone; verify read queries on replicas return schemas and data matching the source.

Re-run critical queries and inspect `EXPLAIN`/`EXPLAIN ANALYZE` in an appropriate environment. Compare duration, estimated/actual row counts, and chosen indexes. Because `EXPLAIN ANALYZE` executes the real query, use it only on bounded read queries in load-assessed environments.

## 4. Verifying access privileges after migration

Schema changes often entail privilege changes. For example, the application needs to read a new column, reporting accounts need access to a new view, or a routine is created with a different `DEFINER`. A migration can succeed while the application fails with `Access denied` because the runtime account lacks privileges on the new object.

### 4.1. Separate migration and runtime accounts

Use role-separated accounts:

| Account | Typical privileges |
|---|---|
| Migration/deployment | Only the DDL privileges needed for the change (`ALTER`, `CREATE`, `INDEX`); DML privileges only if backfilling. Exact privileges depend on operations and created objects. |
| Application runtime | Only DML privileges on required tables/views (`SELECT`, `INSERT`, `UPDATE`, `DELETE`). |
| Reporting/analytics | Typically `SELECT` only on permitted views or tables. |
| Backup/restore | Privileges required for backup, export, or restore tools; never used as an application account. |

Never grant `ALL PRIVILEGES ON *.*` to migration or runtime accounts merely to bypass permission errors. Scope least privileges to the exact statements and objects the migration uses. If creating triggers, routines, views, or foreign keys, verify corresponding special privileges in your MySQL version's docs.

### 4.2. Verify the exact account and granted privileges

MySQL identifies accounts by `user`/`host` pairs. The same username from a different host can carry a completely different privilege set. Inside the application connection, check:

```sql
SELECT USER() AS connection_identity,
       CURRENT_USER() AS privilege_account,
       CURRENT_ROLE() AS active_roles;

SHOW GRANTS;
```

`USER()` reports the identity the client presented; `CURRENT_USER()` reports the MySQL account used for privilege checks. `CURRENT_ROLE()` shows roles active in the session. When checking specific accounts from an admin session:

```sql
SHOW GRANTS FOR 'app_runtime'@'10.20.30.%';
SHOW GRANTS FOR 'report_reader'@'10.20.40.%';
```

If privileges are granted via roles, verify the role is granted and activated via default roles or `SET ROLE`. A granted role that is not active contributes zero privileges in the current session. Never check only role names in `SHOW GRANTS`; inspect `CURRENT_ROLE()` on an actual application connection.

### 4.3. Verify privileges on new objects

After creating a new table or view, grant exact privileges to the exact accounts:

```sql
GRANT SELECT ON app_db.customer_summary
TO 'report_reader'@'10.20.40.%';

GRANT SELECT, INSERT, UPDATE ON app_db.customer_preferences
TO 'app_runtime'@'10.20.30.%';
```

These examples illustrate privilege scoping only. Never grant `INSERT` or `UPDATE` if an application only needs read access. For views, check `SQL SECURITY DEFINER` versus `SQL SECURITY INVOKER`, whether the `DEFINER` account exists, and whether it holds needed privileges. A view executing under definer security behaves differently from one executing under invoker security.

If a migration renames tables/columns or replaces views, check dependent objects: triggers, stored routines, events, other views, and reporting accounts. Privileges on an old table do not automatically grant access to a newly created object.

### 4.4. Test using the actual runtime account

Never validate permissions using only a DBA account. Connect with the actual application account or a test account carrying identical grants/roles, and execute critical operations:

```sql
-- Verify read query required by the application.
SELECT customer_id, status_v2
FROM app_db.customers
WHERE customer_id = 1001;

-- Verify write privilege if the application performs updates.
UPDATE app_db.customer_preferences
SET preference_value = 'email'
WHERE customer_id = 1001;
```

In test environments, wrap test DML in a transaction and roll it back whenever possible. Never run test writes in production without dedicated test data and clear cleanup procedures. Also test intentionally denied paths—for example, confirming a reporting account cannot write to operational tables.

## 5. Understanding DDL rollback limits in MySQL

### 5.1. DDL usually causes implicit commits

Many DDL statements such as `ALTER TABLE`, `CREATE TABLE`, `DROP TABLE`, `CREATE INDEX`, and `DROP INDEX` trigger an implicit commit. This means any open transaction commits before the DDL runs; afterward, `ROLLBACK` cannot undo the schema change the way it undoes DML.

Example:

```sql
START TRANSACTION;

UPDATE app_db.customers
SET status = 'I'
WHERE customer_id = 1001;

ALTER TABLE app_db.customers
  ADD COLUMN migrated_at DATETIME NULL;

ROLLBACK;
```

Never assume the trailing `ROLLBACK` will undo both `ALTER TABLE` and the preceding `UPDATE`. Because DDL causes an implicit commit, the transaction was committed prior to DDL execution. Separate schema migrations and data transactions into explicitly planned steps.

### 5.2. Atomic DDL is not transaction rollback

MySQL supports atomic DDL for many operations on supported storage engines. Atomic DDL makes DDL crash-safe: if the server crashes mid-DDL, MySQL recovers state so the operation either finishes completely or is internally rolled back.

This does not mean a user can issue `ROLLBACK` after `ALTER TABLE` succeeds to revert to the old schema. Atomic DDL protects execution integrity; it does not turn DDL into an arbitrarily rollbackable business transaction unit.

### 5.3. Online DDL can still impact production

Some `ALTER TABLE` operations support `ALGORITHM=INSTANT`, `ALGORITHM=INPLACE`, or `LOCK=NONE`; exact support depends on change type, MySQL version, and storage engine. `INSTANT` avoids table rebuilds for supported operations, though not every change qualifies. `INPLACE` does not necessarily mean no rebuild or zero I/O cost.

Example instructing MySQL to use instant execution if supported:

```sql
ALTER TABLE app_db.customers
  ADD COLUMN migrated_at DATETIME NULL,
  ALGORITHM=INSTANT;
```

If the operation does not support the requested algorithm, MySQL returns an error rather than silently picking another algorithm. This avoids surprise rebuilds, yet must still be tested on the target version and schema first.

Even online DDL needs metadata locks at certain phases. Long transactions or queries holding metadata locks force DDL to wait; a long-waiting DDL also causes incoming queries to queue behind it. Before running migrations, inspect long transactions, the process list, and metadata locks:

```sql
SELECT *
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = 'app_db'
  AND OBJECT_NAME = 'customers';

SHOW FULL PROCESSLIST;
```

Never kill sessions or queries based solely on runtime. Identify the owner, transaction, and application impact before intervening. On large tables, test DDL on a clone near production size and measure duration, I/O, locks, temp space, and replication lag.

## 6. Designing migrations with expand-contract

Expand-contract breaks a large change into small steps, letting old and new application versions operate side by side during transition. This lowers risk when renaming columns, changing data formats, or switching read/write logic.

Suppose `status` currently stores short codes `A`, `I`, `P`; the new application version expects `status_v2` with values `ACTIVE`, `INACTIVE`, `PENDING`.

### Phase 1: Expand

Add the new nullable column so the old application keeps working:

```sql
ALTER TABLE app_db.customers
  ADD COLUMN status_v2 VARCHAR(20) NULL,
  ALGORITHM=INSTANT;
```

Inspect structure and grant privileges to the runtime account if permissions are scoped by column or view. Do not drop the old column yet; the current application continues reading/writing `status`.

### Phase 2: Dual-write and backfill

Deploy an application version that writes both `status` and `status_v2` concurrently, or use a tested temporary sync mechanism. Enable dual-write only after the new column exists on every server capable of serving traffic. During rolling deployments, every instance or job still writing `status` must either be upgraded to dual-write or drained before relying on `status_v2`; if legacy writers update only `status`, newer values drift out of sync with `status_v2`.

Backfill in primary-key batches to bound transactions and locks:

```sql
UPDATE app_db.customers
SET status_v2 = CASE status
  WHEN 'A' THEN 'ACTIVE'
  WHEN 'I' THEN 'INACTIVE'
  WHEN 'P' THEN 'PENDING'
  ELSE 'UNKNOWN'
END
WHERE customer_id > 0
  AND customer_id <= 10000
  AND status_v2 IS NULL;
```

Repeat for successive `customer_id` ranges. Tune batch size to transaction time, I/O load, lock contention, and replication lag. Never run a single full-table `UPDATE` in a huge transaction without measuring impact first.

If the application can still mutate `status` during backfill, deploy dual-writes first or ensure the backfill avoids overwriting newer updates. Persist checkpoints of completed batches so execution can resume if interrupted.

### Phase 3: Validate

Verify row counts and mappings:

```sql
SELECT COUNT(*) AS total_rows,
       SUM(status_v2 IS NULL) AS missing_status
FROM app_db.customers;

SELECT COUNT(*) AS mismatched_rows
FROM app_db.customers
WHERE NOT (
  status_v2 <=> CASE status
    WHEN 'A' THEN 'ACTIVE'
    WHEN 'I' THEN 'INACTIVE'
    WHEN 'P' THEN 'PENDING'
    ELSE 'UNKNOWN'
  END
);
```

Expected results are `missing_status = 0` and `mismatched_rows = 0`, assuming that matches the agreed business rules. Also check per-status distributions, out-of-domain values, and new application queries.

### Phase 4: Switch

Deploy the application version that reads `status_v2`. Maintain dual-writes during an observation period so reads can revert to the old column if issues appear. Monitor errors, latency, null rates, and discrepancies between both columns.

Shift traffic completely only after every application instance is compatible and every read-serving replica has applied the migration. When running mixed application versions during rolling deployments, ensure older versions cannot overwrite newer versions' data.

### Phase 5: Contract

After a sufficient observation period and confirming zero applications depend on the old column, execute the contract step:

```sql
-- Preserve full existing DEFAULT, COMMENT, CHARACTER SET, and COLLATE if present.
ALTER TABLE app_db.customers
  MODIFY COLUMN status_v2 VARCHAR(20) NOT NULL;

-- Execute only in a separate migration after verifying zero consumers remain.
ALTER TABLE app_db.customers
  DROP COLUMN status;
```

This carries higher risk because `DROP COLUMN` discards legacy data. Never combine the contract step in the same deployment as expand. Keep a backup/schema snapshot and verify the recovery path before dropping columns.

## 7. Phased rollback planning

Rollbacks must answer two questions: how to restore the application to a safe working state, and how to preserve data created after the migration. Reversing DDL alone fails to answer the second question.

### 7.1. Classifying reversibility

| Change type | Reversibility | Action plan |
|---|---|---|
| Adding unused nullable column | Usually easy | Stop new app; leave column or drop after verifying no needed data exists. |
| Adding index | Usually reversible | Drop index if hurting performance or deployment plans; verify dependent queries. |
| Backfilling new column | Reversible if old column intact | Switch app back to old column; keep new column for investigation or drop later. |
| Lossy data type conversion | May be irreversible | Requires original data copy or backup/PITR restore. |
| Dropping column/table | Unrecoverable via reverse DDL | Restore from backup/PITR or recover data from another copy. |
| Merging/deleting duplicate rows | May lose information | Archive mappings and source records before merging; restore per business rules. |

A reverse migration is safe only when post-migration data can still be represented faithfully in the old schema. For instance, if `status_v2` stores new states lacking an equivalent code in legacy `status`, reversing loses data semantics.

### 7.2. Preparing backups and recovery points

Before risky migrations, ensure you have a backup whose restore capability has been tested. Record:

- Backup timestamp and database/table scope.
- Corresponding binary log file/position or GTID metadata.
- Binary log retention sufficient for PITR.
- Backup storage location, access credentials, and decryption capability if encrypted.
- Expected restore and verification duration.

Do not merely verify that a backup file exists. Execute a test restore into an isolated environment and verify data, schema, and required accounts/privileges. An untested backup is never proof the system can recover on time.

With PITR, restore the backup onto a separate instance and replay binary logs up to just before the faulty transaction. Never overwrite production immediately before determining which data must be preserved. If writes continued post-migration, rolling back to an older snapshot loses valid transactions occurring after the snapshot unless replayed or reconciled.

### 7.3. Rolling back application and schema

Inside expand-contract:

1. If the new application fails before contraction, shift traffic back to the old version reading the old column.
2. Retain dual-writes if needed to keep both columns synchronized during rollback.
3. Inspect records inserted/updated post-cutover; confirm the old column still holds equivalent values.
4. If the new column contains data unrepresentable in the old schema, never roll back the application blindly; run a reverse mapping or forward-fix.
5. Drop the new column only after confirming it is no longer needed for investigation or recovery.

If a migration dropped or overwrote data unrecoverably via inverse logic, halt writes per incident runbook, restore into a separate environment, replay logs to a safe point, and reconcile transactions after that point. Any cutover-back decision requires sign-off from the business data owner.

### 7.4. Forward-fix can be safer than rollback

Not every failure warrants reverting to the old schema. If DDL succeeded, new data is written, and the new schema can support the application, a supplemental migration (forward-fix) usually lowers data-loss risk. For instance, adding a missing index, fixing a backfill mapping, or granting missing permissions can be resolved directly without restoring the whole database.

Choose rollback when a verified reverse path exists and post-migration data can be preserved. Choose forward-fix when the current schema remains a sound foundation and defects can be fixed with additive changes. Document the decision, approver, and verification steps before executing.

## 8. Progress gating and migration stop conditions

Production migrations should define explicit checkpoints. Example:

| Checkpoint | Proceed when | Stop / investigate when |
|---|---|---|
| Before DDL | Backup/restore verified; replicas healthy; no long lock-holding transactions | Unusable backup, high replication lag, abnormal metadata locks |
| After DDL | Schema accurate; duration and locks within bounds | DDL failed, application blocked, replica SQL thread stopped |
| After backfill | Row counts and mappings match; data errors within threshold | Mismatches, unexpected nulls, duplicates, or orphaned rows |
| After privilege grants | Runtime account succeeds on valid flows and is blocked on disallowed flows | `Access denied`, inactive role, over-scoped privileges |
| After cutover | Error rate and latency within bounds; replicas caught up | Rising errors, slow queries, reads diverging from source |
| Before contract | Zero legacy consumers left; rollback window elapsed; fresh backup ready | Old app versions or jobs still depend on old column |

Set concrete numeric thresholds for your system, such as max replication lag, error rate, latency, and lock duration. Never copy generic example thresholds across workloads. Once a stop condition triggers, pause the next phase and preserve logs and current state for investigation.

## 9. Recording migrations and verification evidence

A migration can be re-run or resumed after interruption only when you know exactly which steps completed. Record at minimum:

- Migration ID, checksum, and application version.
- Start/finish timestamps for each phase.
- Executed DDL statements and outcomes.
- Before/after row counts, backfilled row counts, error counts, and excluded rows.
- GTIDs or binary log coordinates at key milestones.
- Before/after privileges and tested accounts.
- Replica status, errors, and lag.
- Operator, verifier, and any rollback/forward-fix decisions.

Example simple migration history table:

```sql
CREATE TABLE IF NOT EXISTS ops_schema_migrations (
    migration_id VARCHAR(120) NOT NULL PRIMARY KEY,
    checksum     CHAR(64) NOT NULL,
    started_at   DATETIME NOT NULL,
    finished_at  DATETIME NULL,
    status       ENUM('RUNNING', 'SUCCEEDED', 'FAILED', 'ROLLED_BACK')
                 NOT NULL,
    applied_by   VARCHAR(255) NOT NULL,
    notes        TEXT NULL
) ENGINE = InnoDB;
```

This example table is only an operational log; it does not replace migration tooling or auditing systems. Update status only after verifying the database; never mark `SUCCEEDED` if data or privilege checks failed.

## 10. Practice workflow: a reversible migration

Suppose you need to add `status_v2` to `customers` and migrate the application from `status` to the new column.

### Before deployment

1. Save `SHOW CREATE TABLE`, indexes, constraints, triggers, views, and relevant grants.
2. Record baseline row counts, status distribution, null counts, and critical application queries.
3. Confirm backups have been test-restored; record GTID/binlog metadata and log retention.
4. Inspect long transactions, metadata locks, replication health, and free disk space.
5. Prepare the dual-write application version and a plan to switch reads back to the old column.

### During deployment

1. Add the nullable column using DDL tested on the target MySQL version.
2. Re-read `SHOW CREATE TABLE` and verify metadata.
3. Grant required privileges to the runtime account; verify grants and active roles.
4. Roll out dual-writes, then run checkpointed batched backfills.
5. Verify null counts, mappings, value distributions, duplicate keys, and replica lag.
6. Gradually shift application reads to the new column by traffic slice; watch errors and latency.

### After deployment

1. Run smoke tests using the actual runtime account.
2. Reconcile source/replica data and core business queries.
3. Retain the old column and dual-writes through the agreed rollback window.
4. Once the rollback window ends, confirm zero legacy consumers remain and take an appropriate backup/snapshot.
5. Run the contract step in a separate migration; re-verify schema, privileges, and application.
6. Archive migration outcomes and verification evidence in change management.

## 11. Common errors

| Symptom | Cause | Resolution |
|---|---|---|
| DDL succeeds yet application fails | Runtime account lacks privileges or app is schema-incompatible | Check `CURRENT_USER()`, `CURRENT_ROLE()`, `SHOW GRANTS`, and smoke-test with app account. |
| Unable to `ROLLBACK` `ALTER TABLE` | DDL triggered implicit commit | Use a controlled reverse migration, forward-fix, or backup/PITR. |
| Migration waits a long time | Another transaction holds metadata locks | Identify lock-holding session and handle per owner/workload. |
| Backfill misses or corrupts data | Skipped batches, wrong mapping, or out-of-sync dual-writes | Use checkpoints, null counts, null-safe equality checks, and key-range verification. |
| Adding unique index fails | Existing data has duplicates | Report duplicates, align on business remediation, then create index. |
| Adding foreign key fails | Orphaned rows or incompatible key types/collations | Locate and remediate orphans; compare column types and indexes on both sides. |
| Replica lags after DDL/backfill | Heavy DDL or batch load | Shrink batches, throttle speed, wait for replica catch-up before next phase. |
| App rolled back yet new data unreadable | New column holds values unrepresentable in old schema | Controlled reverse mapping or forward-fix; do not drop the new column. |
| Re-running migration errors out | Non-idempotent script or unclear migration state | Inspect schema and migration journal before retrying; write explicit state checks. |

## 12. Deployment checklist

- [ ] Recorded migration ID, checksum, and objective.
- [ ] Checked schema, indexes, constraints, triggers, views, and dependent routines.
- [ ] Saved baseline data metrics and workload stats.
- [ ] Confirmed legacy data satisfies new constraints or has an approved cleanup plan.
- [ ] Tested backup restore; PITR and binary log retention meet requirements.
- [ ] Tested DDL on target version and schema; evaluated algorithm and locks.
- [ ] Migration and runtime accounts follow least-privilege permissions.
- [ ] Tested privileges with actual runtime account, including active roles.
- [ ] Backfill uses batches, checkpoints, retries, and reconciliation queries.
- [ ] Defined migration stop criteria and decision owners clearly.
- [ ] Old and new apps remain compatible during expand-contract phases.
- [ ] Wrote and rehearsed rollback or forward-fix procedures.
- [ ] Verified schema, data, privileges, replicas, and performance post-migration.
- [ ] Archived migration evidence and completion status.

## 13. Self-check exercises

1. Why cannot `ROLLBACK` undo a succeeded `ALTER TABLE` statement?
2. How does atomic DDL differ from transaction rollback?
3. Before adding a unique index on an email column, what data checks are required?
4. Why must you test privileges with the actual runtime account instead of a DBA account?
5. In expand-contract, why should you not drop the old column immediately after the new app starts reading the new column?
6. If the new column holds values that cannot be represented in the old schema, how must application rollback be handled?
7. Why does re-enabling `foreign_key_checks` not automatically re-validate rows loaded while checks were disabled?
8. When DDL waits on a metadata lock, what must you investigate before killing a session?

**Answer hints:** (1) DDL generally triggers an implicit commit; schema changes commit independently. (2) Atomic DDL makes individual DDL operations crash-safe internally, whereas transaction rollback undoes uncommitted transactional changes. (3) Duplicate groups after normalization, accounting for case differences, whitespace, and collation rules. (4) DBA accounts have broad privileges that hide missing runtime permissions; verify exact `user`/`host` and active roles. (5) Older app versions, jobs, or reports may still depend on the old column; keeping it preserves rollback options. (6) Controlled reverse mapping or forward-fix; never delete new data just to force a rollback. (7) MySQL does not re-scan existing rows when re-enabling the variable; you must explicitly query for orphaned rows. (8) Identify the transaction holding the metadata lock, its owner, running queries, and the data/business impact of killing it.

## References

- [MySQL 8.4 Reference Manual: Implicit Commit](https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html)
- [MySQL 8.4 Reference Manual: Atomic Data Definition Statement Support](https://dev.mysql.com/doc/refman/8.4/en/atomic-ddl.html)
- [MySQL 8.4 Reference Manual: Online DDL](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl.html)
- [MySQL 8.4 Reference Manual: Metadata Locking](https://dev.mysql.com/doc/refman/8.4/en/metadata-locking.html)
- [MySQL 8.4 Reference Manual: The INFORMATION_SCHEMA COLUMNS Table](https://dev.mysql.com/doc/refman/8.4/en/information-schema-columns-table.html)
- [MySQL 8.4 Reference Manual: Privileges Provided by MySQL](https://dev.mysql.com/doc/refman/8.4/en/privileges-provided.html)
- [MySQL 8.4 Reference Manual: Foreign Key Constraints](https://dev.mysql.com/doc/refman/8.4/en/create-table-foreign-keys.html)
