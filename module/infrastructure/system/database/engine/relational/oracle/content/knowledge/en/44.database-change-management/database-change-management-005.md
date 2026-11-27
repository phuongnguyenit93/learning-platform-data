# Expand-and-Contract Pattern for Application-Compatible Schema Changes

## 1. Why Is the Expand-and-Contract Pattern Needed?

In continuously running systems, database schemas and applications often cannot be deployed at the exact same instant. A rolling deployment can leave multiple application versions active simultaneously: old instances have not yet been replaced, new instances are already serving requests, background workers are still running, and batch jobs have not yet restarted. If the schema changes abruptly in a way only one version understands, part of the application may fail immediately during deployment.

The **expand-and-contract** pattern solves this by splitting a schema change into backward-compatible and forward-compatible steps:

1. **Expand:** add new structures while old application versions continue working.
2. **Migrate:** migrate data and deploy application versions capable of working with both old and new structures.
3. **Switch:** switch reads and writes to the new structures once data is synchronized.
4. **Contract:** drop old structures only when no application version or process still depends on them.

The goal is maintaining availability during rolling deployments while providing checkpoints to pause or roll back to an earlier version if issues arise.

```text
Old schema
   |
   v
EXPAND: add new columns/tables/APIs, keep old structures
   |
   v
MIGRATE: backfill data, keep both forms synchronized
   |
   v
SWITCH: application reads new structure, remains compatible with old writers
   |
   v
CONTRACT: remove bridge, drop old structures once dependencies are gone
   |
   v
New schema
```

This is a multi-release schema deployment strategy. It is especially valuable in Oracle Database, where DDL can trigger implicit commits and lock/metadata operations must be managed separately from business transactions.

## 2. Multi-Version Application Compatibility Principles

### 2.1. The Schema Must Support Both Old and New Versions During Transition

Suppose table `CUSTOMERS` currently has column `CUSTOMER_NAME`, while the new design wants to use `DISPLAY_NAME`.

Old application version:

- Reads `CUSTOMER_NAME`.
- Writes `CUSTOMER_NAME`.
- Has no knowledge that `DISPLAY_NAME` exists.

Transitional version:

- Reads `DISPLAY_NAME` once data has been backfilled.
- Dual-writes both `DISPLAY_NAME` and `CUSTOMER_NAME` so old versions can still read.

Final version:

- Reads and writes only `DISPLAY_NAME`.
- No longer references `CUSTOMER_NAME`.

During rolling deployments, the database must allow these versions to coexist according to the defined compatibility matrix. Adding a new `NOT NULL` column without a compatible default/value causes `INSERT`s from old applications to fail immediately. Therefore, the expand step usually adds the column as nullable first.

### 2.2. Compatibility Matrix

| Application Version | Reads | Writes | Compatible with Expanded Schema? |
|---|---|---|---|
| Old V1 | `CUSTOMER_NAME` | `CUSTOMER_NAME` | Yes, as long as the old column remains |
| Transitional V2 | `DISPLAY_NAME` | Both columns | Yes, once the new column and data are prepared |
| Final V3 | `DISPLAY_NAME` | `DISPLAY_NAME` | Yes, once all old writers are retired |

Do not check only web/API instances. Inventory every component that reads or writes the schema: batch jobs, schedulers, ETL pipelines, reports, stored procedures, triggers, integration services, CDC pipelines, operational scripts, and ad-hoc tools.

### 2.3. Decouple Application Deployment from Schema Changes

A safe release typically consists of independent steps:

- Database migration expanding the schema.
- Batched data backfill.
- Deploying the transitional application.
- Switching the read path and observing.
- Deploying the final version.
- Cleaning up the old schema.

Never bundle everything into a single migration expecting a one-command rollback to restore the prior state. DDL steps, DML backfills, and application deployments have different lifecycles, transaction semantics, and rollback capabilities.

## 3. Example: Renaming Column CUSTOMER_NAME to DISPLAY_NAME

### 3.1. Initial Schema

```sql
CREATE TABLE customers (
    customer_id   NUMBER(19) PRIMARY KEY,
    customer_name VARCHAR2(200) NOT NULL,
    created_at    TIMESTAMP(6) DEFAULT SYSTIMESTAMP NOT NULL
);
```

Application V1 uses `CUSTOMER_NAME` in SQL statements, entity mappings, stored procedures, and reports.

### 3.2. Expand Step: Add the New Column

Add the new column as nullable:

```sql
ALTER TABLE customers
ADD (display_name VARCHAR2(200));
```

After this step:

- V1 continues reading/writing `CUSTOMER_NAME` as before.
- `DISPLAY_NAME` exists but has no values yet for older rows.
- Do not rename or drop the old column.
- Do not enable required constraints on the new column before backfilling and confirming writers are ready.

Adding a column is DDL. Oracle performs implicit commits around DDL; do not treat `ALTER TABLE` as something that can roll back with a preceding DML transaction. Run migrations in a dedicated process and verify before/after states.

### 3.3. Keep Data Synchronized While V1 Still Writes the Old Column

While V1 remains active, its `INSERT`/`UPDATE` statements only know about `CUSTOMER_NAME`. If V2 reads `DISPLAY_NAME`, new data written by V1 must be mirrored to the new column.

A one-way compatibility trigger can be used during transition:

```sql
CREATE OR REPLACE TRIGGER customers_name_bridge_trg
BEFORE INSERT OR UPDATE OF customer_name ON customers
FOR EACH ROW
BEGIN
    :NEW.display_name := :NEW.customer_name;
END;
/
```

This trigger uses `CUSTOMER_NAME` as the source for `DISPLAY_NAME` on insert or when a statement updates the old column. The operational condition in this example is that the transitional version writes the exact same value to both columns; the trigger keeps the new value consistent with the old column.

The trigger is a temporary bridge. Verify ownership, valid status, compilation errors, existing trigger ordering, and performance impact. If the application has other triggers updating either column, clearly define ordering and canonical data source to avoid mutual overwrites.

Another option is implementing the bridge at the application/service layer, though that is only safe if every writer is upgraded before the new version reads the new column. While V1 can still write the old column, a trigger or reliable database-level sync prevents missed writers.

### 3.4. Batched Backfill of Historical Data

Once the bridge is installed, copy existing data:

```sql
UPDATE customers
SET display_name = customer_name
WHERE display_name IS NULL
  AND customer_name IS NOT NULL;

COMMIT;
```

For small tables, a single statement may suffice. For large tables, backfill in batches to reduce lock duration, per-transaction undo/redo volume, archive log pressure, and impact on active workloads.

Example batched loop by `ROWID`:

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    LOOP
        UPDATE customers c
        SET c.display_name = c.customer_name
        WHERE c.display_name IS NULL
          AND c.customer_name IS NOT NULL
          AND c.ROWID IN (
              SELECT x.ROWID
              FROM customers x
              WHERE x.display_name IS NULL
                AND x.customer_name IS NOT NULL
                AND ROWNUM <= 1000
          );

        l_rows := SQL%ROWCOUNT;
        COMMIT;

        EXIT WHEN l_rows = 0;
    END LOOP;
END;
/
```

`1000` is an illustrative batch size. Choose batch size based on row width, redo/undo rate, I/O, lock duration, load levels, and RTO. You can commit per batch, record progress, and resume after failures.

Backfills must be idempotent: re-running them must not corrupt already-migrated data. The condition `DISPLAY_NAME IS NULL` ensures only unpopulated rows are updated, though consider cases where `CUSTOMER_NAME` can validly be `NULL` or business logic allows `DISPLAY_NAME` to differ from `CUSTOMER_NAME`. In such cases, use an explicit migration flag or exact conversion rules rather than relying solely on nulls.

The trigger is installed before backfilling so new changes from legacy writers continuously populate the new column while batches run. Even so, perform a catch-up pass and data check after backfilling to confirm no gaps remain.

### 3.5. Verifying Data After Backfill

Count rows not yet migrated:

```sql
SELECT COUNT(*) AS missing_display_name
FROM customers
WHERE customer_name IS NOT NULL
  AND display_name IS NULL;
```

Compare values:

```sql
SELECT COUNT(*) AS mismatch_count
FROM customers
WHERE customer_name <> display_name
   OR (customer_name IS NULL AND display_name IS NOT NULL)
   OR (customer_name IS NOT NULL AND display_name IS NULL);
```

If both columns must be identical, `MISMATCH_COUNT` should equal `0` at verification time. If transformation involves normalization rules (such as trimming, reformatting, or concatenating fields), compare against the transformation expression instead of direct equality.

On large tables, full-table verification queries also carry cost. You can run them by partition or key range, monitor progress, and use a consistent snapshot if exact comparison is needed while writes continue.

## 4. Migrate Step: Deploying the Transitional Application

### 4.1. V2 Reads the New Column and Writes Both Columns

After historical data is backfilled and verified, deploy V2:

- Read `DISPLAY_NAME`.
- On insert/update, write the same value to both `CUSTOMER_NAME` and `DISPLAY_NAME`.
- Do not assume V1 disappears the instant rolling deployment begins.

Example V2 SQL:

```sql
INSERT INTO customers (
    customer_id,
    customer_name,
    display_name
)
VALUES (
    :customer_id,
    :display_name,
    :display_name
);
```

Update:

```sql
UPDATE customers
SET customer_name = :display_name,
    display_name  = :display_name
WHERE customer_id = :customer_id;
```

The bridge trigger continues ensuring V1 writers updating only `CUSTOMER_NAME` also refresh `DISPLAY_NAME`. V2 writes both so legacy consumers can keep reading the old column.

Do not let V2 read the new column before backfilling completes or without safe fallback logic. If code must deploy prior to backfill for operational reasons, a feature flag can keep the old read path active until validation passes.

### 4.2. Separate the Read Switch from the Write Switch

A feature flag can flip the read path once new data is ready:

```text
V2 deployed, read_old=true, write_both=true
        |
        v
Backfill + validation complete
        |
        v
read_new=true, write_both=true
        |
        v
Observe metrics and data consistency
```

Separating these two decisions simplifies rollback. If V2 reads `DISPLAY_NAME` and hits discrepancies, you can revert the read path to `CUSTOMER_NAME` while continuing to dual-write and fix the data.

Feature flags do not replace schema compatibility. V1 must still run on the expanded schema; V2 may enable reading the new column only after data conditions are met.

### 4.3. Monitoring During the Mixed-Version Phase

During rolling deployment, monitor:

- Count of instances/workers still running V1.
- Write volume through V1 vs. V2.
- Trigger executions/errors and invalid statuses.
- Rows still missing or mismatched in `DISPLAY_NAME`.
- SQL errors such as `ORA-00904` (invalid identifier), `ORA-01400` (cannot insert NULL), and constraint errors.
- Latency, lock waits, redo/undo generation, and connection pools.

Do not declare V2 deployment finished just because web instances are updated. Batch jobs, schedulers, consumers, and infrequently invoked services may keep running old binaries for extended periods.

## 5. Switch Step: Moving All Consumers to the New Schema

### 5.1. Confirm No Consumers Still Read the Old Column

Before removing `CUSTOMER_NAME`, inventory all dependencies:

- SQL in source code and binaries across all services.
- JPA/Hibernate mappings, native queries, stored procedures, packages, and views.
- Triggers, materialized views, database links, and synonyms.
- ETL, BI/reporting, data warehouse, CDC/replication, and data exports.
- Schedulers, batch jobs, deployment scripts, and operational utilities.
- External consumers or other teams accessing the schema directly.

Oracle data dictionary views such as `DBA_DEPENDENCIES` help locate database object dependencies, but cannot detect dynamic SQL, application-side SQL, or queries sent by external tools. Combine source searches, application inventories, SQL monitoring, and explicit sign-off from each integration owner.

### 5.2. Deploy V3 Using Only the New Column

Once V1 is completely decommissioned, deploy V3:

- Read only `DISPLAY_NAME`.
- Write only `DISPLAY_NAME`.
- Remove all references to `CUSTOMER_NAME`.

While rolling from V2 to V3, both versions read `DISPLAY_NAME`. V2 still writes both; V3 writes only the new column. The bridge trigger only syncs from the old column to the new column, so it does not interfere with new values written by V3.

Wait for all V2 instances/workers to finish and confirm no writer still needs `CUSTOMER_NAME`. Only then should you plan the contract step.

### 5.3. Enforcing New Constraints

If `DISPLAY_NAME` requires `NOT NULL`, first confirm zero null rows remain:

```sql
SELECT COUNT(*)
FROM customers
WHERE display_name IS NULL;
```

Once data is valid, add the check constraint following procedures suited to your Oracle release and table size. Oracle supports constraint states such as `ENABLE NOVALIDATE` and `ENABLE VALIDATE` for certain constraint types:

```sql
ALTER TABLE customers
  ADD CONSTRAINT customers_display_name_nn
  CHECK (display_name IS NOT NULL)
  ENABLE NOVALIDATE;

ALTER TABLE customers
  ENABLE VALIDATE CONSTRAINT customers_display_name_nn;
```

`ENABLE NOVALIDATE` enforces the check on new data without validating all existing data yet; `ENABLE VALIDATE` verifies existing data and may take time or affect DDL locking. Exact syntax, online capabilities, and converting check constraints to `NOT NULL` vary by release. Never treat `NOVALIDATE` as proof that historical data is clean.

If the column truly needs the `NOT NULL` metadata attribute, after validation you can run `ALTER TABLE ... MODIFY (DISPLAY_NAME NOT NULL)` per a tested plan. Check constraints and dictionary status after DDL.

## 6. Contract Step: Removing Old Schema Structures

### 6.1. Preconditions Before Dropping

Contract only after confirming every condition below:

1. No V1 application reads or writes `CUSTOMER_NAME`.
2. No V2 dual-write or job/consumer needs the old column.
3. Stored procedures, views, triggers, reports, ETL, CDC, and integrations have switched to `DISPLAY_NAME`.
4. `DISPLAY_NAME` data is reconciled with zero unexpected mismatches.
5. New constraints/indexes are created and validated if required by business rules.
6. A sufficient observation period has elapsed to catch weekly/monthly scheduled consumers.
7. Backups/recovery capabilities and an incident plan exist if contract causes errors.

### 6.2. Remove the Bridge Trigger

Once no writer updates only the old column:

```sql
DROP TRIGGER customers_name_bridge_trg;
```

Verify the trigger is dropped and no other triggers reference both columns. DDL performs an implicit commit; `ROLLBACK` cannot undo it if a subsequent step fails.

### 6.3. Drop the Old Column

```sql
ALTER TABLE customers
DROP COLUMN customer_name;
```

This contract step is incompatible with V1/V2. Afterward, any binary or SQL still referencing `CUSTOMER_NAME` will fail. For large tables or to minimize lock duration, consider appropriate Oracle features such as `SET UNUSED` first followed by physical dropping in a separate window, or online redefinition techniques. Availability and cost depend on Oracle release, edition, object type, and table structure.

Do not treat `SET UNUSED` as if the column vanished from all physical storage; the column is marked unused and continues occupying space until physically dropped via Oracle's cleanup process.

### 6.4. Verify the Final Schema

```sql
SELECT column_name,
       data_type,
       nullable,
       data_length
FROM user_tab_columns
WHERE table_name = 'CUSTOMERS'
ORDER BY column_id;
```

Check constraints, indexes, triggers, and related dependencies. Run V3 application smoke tests and inspect SQL logs after contract.

## 7. Rollback and Reverting to Previous Versions

### 7.1. Rollback During Expand/Migrate

Before contract, reverting to V1 is usually straightforward because the old column still exists and the bridge keeps updating data. You can:

- Turn off the feature flag reading `DISPLAY_NAME`.
- Roll back the application to V1.
- Keep the new column and bridge trigger to investigate/repair data.
- Stop backfilling if transformation rules are flawed, then adjust and re-run idempotently.

There is no need to immediately drop the new column when rolling back the application. Keeping the expanded schema is usually safer and enables retrying later.

### 7.2. Post-Contract Rollback Is Harder

After dropping `CUSTOMER_NAME`, you cannot simply roll binaries back to V1. You must restore old schema/data or deploy a reverse migration recreating the column and repopulating it from the new column. If the transformation was lossy, exact original state cannot be reconstructed solely from the new column.

Therefore, contract should be treated as a point of no return. Before contracting, confirm application owners, decommission schedules, and rollback expectations are aligned.

### 7.3. Rollback Does Not Mean Database Restore

Application rollback, feature flag rollback, reverse migrations, and RMAN restores are distinct operations. Database restore can discard transactions after the backup/SCN and disrupt many other applications. Never restore an entire database to undo a small schema migration when a safer reverse migration is available.

## 8. Oracle-Specific Considerations

### 8.1. DDL Implicitly Commits

Oracle implicitly commits before and after many DDL statements. Operations like `ALTER TABLE`, `CREATE INDEX`, `CREATE TRIGGER`, and `DROP COLUMN` do not share a single rollback transaction with preceding DML.

Therefore:

- Run DDL migrations as independent steps and record migration state.
- Never rely on `ROLLBACK` to undo succeeded DDL.
- Verify object statuses and data after each migration.
- Design reverse migrations with separate DDL/DML when feasible.

### 8.2. DDL Locks and DML Impact

DDL acquires metadata/table locks depending on the operation. If another transaction is actively using the object or holding related locks, DDL may wait or fail with a lock timeout. Conversely, DDL can block new sessions while acquiring metadata locks.

Before migration:

- Identify long-running transactions touching the table.
- Pick an appropriate deployment window and configure DDL lock timeout where supported.
- Test on a clone with production-like data and size.
- Monitor blocking sessions, wait events, and DDL duration.
- Avoid running large migrations concurrently with heavy batch jobs.

### 8.3. CREATE INDEX ONLINE and Online Operations

Oracle supports `ONLINE` for certain index/DDL operations depending on release, object type, and licensing/edition conditions. Example:

```sql
CREATE INDEX customers_display_name_ix
ON customers(display_name)
ONLINE;
```

`ONLINE` allows DML to proceed during part of index creation, yet still involves locking points and specific restrictions. Never assume every DDL supports online mode or is completely non-blocking. Consult Oracle documentation for your exact version, edition, and table type before use.

### 8.4. Backfills Generate Redo/Undo and Archive Logs

Updating millions of rows generates undo/redo and can spike archive logs, backup volumes, replication lag, or Data Guard impact. Run in controlled batches, commit deliberately, and monitor FRA, archive destinations, undo tablespaces, and standby apply lag.

Never disable logging or archiving just to speed up migrations without evaluating recovery impact and data protection requirements.

### 8.5. Statistics and Execution Plans

Adding columns, backfilling, and creating indexes can shift cardinality and execution plans. After transforming data, check statistics and plans for new queries. Gather statistics per DBA policy; avoid blindly gathering stats or flushing the shared pool during peak hours.

### 8.6. Edition-Based Redefinition and DBMS_REDEFINITION

Oracle provides advanced tools for online changes:

- **Edition-Based Redefinition (EBR):** lets you maintain multiple editions of PL/SQL objects and use editioning views for edition-based application upgrades. EBR fits edition-capable code/database objects; it does not automatically eliminate migrations for table structure changes.
- **DBMS_REDEFINITION:** supports online redefinition for certain table structure changes by syncing data to an interim table and switching objects. Verify eligibility criteria, dependencies, privileges, storage, and release limits.

Expand-and-contract is a coordination strategy between application and schema; EBR/`DBMS_REDEFINITION` are Oracle capabilities usable in specific technical steps. They complement each other rather than replacing one another.

## 9. Schema Changes Beyond Renaming Columns

### 9.1. Adding a Required Column

Never add a `NOT NULL` column that old versions do not populate unless a compatible default is provided. The safe sequence is usually:

1. Add the column as nullable or with a verified default.
2. Deploy application code writing the new value.
3. Backfill older rows.
4. Confirm zero nulls or invalid values remain.
5. Add and validate the constraint.

### 9.2. Changing Data Types

Directly altering a column's type can break old SQL or lose data. For major conversions, consider adding a new column with the target type, backfilling via conversion expressions, inspecting unconvertible rows, dual-writing during transition, and switching consumers. Never use `TO_NUMBER`/`TO_DATE` in backfills without defining formats and handling conversion errors.

### 9.3. Splitting One Column into Multiple Columns

For example, splitting `FULL_NAME` into `FIRST_NAME` and `LAST_NAME`. Expand adds the two columns; backfill applies agreed splitting rules; the transitional application can read the two new columns while still writing `FULL_NAME` so older versions work. If splitting is irreversible, retain the original column until data and the final consumer have migrated.

### 9.4. Merging Tables or Changing Relationships

When modifying relationships, foreign keys, or table layouts, preserve old read/write paths during transition. Compatibility views or package APIs can encapsulate the new schema. Migrate data in batches, validate keys/unique constraints, and drop old structures only after every consumer switches.

### 9.5. Renaming a Table

Instead of renaming directly, create the new table, sync data, transition applications via compatibility views/synonyms or APIs, and retire the old table. Synonyms resolve object names in some cases, but do not guarantee column compatibility, privileges, DML behavior, or all dependencies.

## 10. Testing Migrations Before Production

### 10.1. Testing the Expanded Schema Against Old Versions

After adding columns/triggers/indexes, run V1's full integration test suite against the new schema. The goal is proving V1 can still insert, update, select, batch-process, and invoke stored procedures.

### 10.2. Mixed-Version Testing

Run V1 and V2 concurrently against the same test database:

- V1 inserts/updates the old column.
- V2 reads the new column.
- V2 inserts/updates both columns.
- Verify the bridge trigger and check for data drift.
- Run legacy batch jobs while backfilling is underway.

### 10.3. Testing Backfill and Restartability

Test stopping the backfill midway, restarting it, and verifying idempotency. Test concurrent writers updating rows during backfill; once complete, zero missing or mismatched rows should remain per conversion rules.

### 10.4. Testing Contract

In staging, deploy V3 with zero references to the old column, verify all tests pass, and then drop the column. Intentionally execute a V1 SQL statement to prove legacy dependencies are caught prior to production contract.

### 10.5. Load and Operational Testing

Measure DDL duration, lock waits, redo/undo, archive generation, replication lag, query latency, connection pools, and backfill runtime. Test rolling deployments, worker restarts, application rollbacks, and feature flags.

## 11. Expand-and-Contract Deployment Checklist

| Stage | Conditions to Verify |
|---|---|
| Pre-expand | All readers/writers inventoried; backups, migration plan, owners, and rollback strategy ready |
| Expand | New structures added while V1 stays functional; DDL locks and runtime controlled |
| Bridge | Sync trigger/service tested; source column and write precedence clearly defined |
| Backfill | Batched idempotently; progress, undo/redo monitored without overloading the system |
| Validate | Zero missing/mismatched rows; new constraints/indexes ready; data reconciled |
| Deploy V2 | V2 reads new schema and dual-writes; V1 can still run safely |
| Switch | All readers switched; feature flags and metrics confirm new read path is stable |
| Deploy V3 | No binary/job needs old column; V3 uses only the new schema |
| Contract | Remove bridge, drop old objects in a separate migration; contingency plan ready if a dependency was missed |
| Post-contract | Smoke tests, check dependencies/logs/invalid objects, backup, and update runbooks |

## 12. Common Pitfalls

### 12.1. Renaming/Dropping in a Single Release

Running old applications fail immediately when querying renamed or dropped columns/tables. Rolling deployments cause two versions to coexist; contracting too early breaks compatibility.

### 12.2. Adding a New Column and Switching Reads Immediately

Historical rows may not be backfilled yet and legacy writers keep updating only the old column. V2 reads `NULL` or stale data. Bridge, backfill, and validate before switching.

### 12.3. Dual-Writing Only in the New Application

If V1 still exists, V1 does not know about the new column and will not dual-write. You need a mechanism ensuring legacy writers also populate new data, such as a bridge trigger or upgrading all writers before switching.

### 12.4. Backfilling in One Giant Transaction

Updating an entire table generates massive undo/redo, holds locks long, spikes archive logs, and degrades workloads. Batch work, commit progressively, and support resumability.

### 12.5. Relying Solely on Dependency Views to Confirm No Consumers Remain

Dynamic SQL, Java code, external ETL, and ad-hoc queries do not appear in database dependency views. Combine source scanning, deployment inventories, monitoring, and owner confirmations.

### 12.6. Treating DDL Like a Rollbackable Transaction

Oracle DDL performs implicit commits. Design reverse migrations or preserve old structures through the safe window; `ROLLBACK` will not undo a completed `DROP COLUMN`.

### 12.7. Skipping an Observation Window Before Contract

Weekly jobs may not run on deployment day. Wait through full workload cycles and confirm zero access to the old column before dropping it.

## 13. Key Principles to Remember

- Expand-and-contract splits schema changes into compatible expansion, data/application migration, and final contraction.
- Expanded schemas must allow old and new versions to coexist during rolling deployments.
- Add new columns as nullable first; backfill and verify data before enforcing mandatory constraints.
- While legacy writers remain, maintain a bridge ensuring new data stays updated; application-only dual-writes miss old writers.
- Backfill in idempotent, resumable batches while monitoring redo/undo/locks.
- Separate read switching from write switching for easier observation and pre-contract rollback.
- Never drop old columns/tables until every service, job, report, trigger, stored procedure, and integration has migrated.
- Oracle DDL performs implicit commits; application rollback and DDL rollback are distinct concerns.
- Verify DDL locks, online operations, indexes, statistics, invalid objects, and replication lag per release/edition.
- Contract is the final commitment point; afterward, rolling back to old binaries may be impossible once the old schema is removed.

## Oracle Reference Documentation

- [Oracle Database 19c SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html)
- [Oracle Database 19c SQL Language Reference — CREATE TRIGGER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TRIGGER.html)
- [Oracle Database 19c Administrator's Guide — Managing Schema Objects](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-schema-objects.html)
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_REDEFINITION](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_REDEFINITION.html)
- [Oracle Database 19c Development Guide — Edition-Based Redefinition](https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/editions.html)
- [Oracle Database 19c Reference — DBA_DEPENDENCIES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_DEPENDENCIES.html)
