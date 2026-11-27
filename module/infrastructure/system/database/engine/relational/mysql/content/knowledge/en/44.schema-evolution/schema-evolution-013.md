# Renaming Tables/Columns, Dependencies, and Application Contracts

In the **DATABASE_MYSQL** module, changing a schema is more than editing a single DDL statement. A table or column may be used concurrently by multiple application versions, views, triggers, stored routines, background jobs, reports, CDC pipelines, and integration systems. Renaming directly while those components are still active can cause queries to fail immediately once the DDL finishes.

This lesson covers how to inventory dependencies, rename tables and columns in MySQL, preserve compatibility across multi-version application rollouts, control metadata locks, and decide when to remove legacy names. The focus is managing the contract between schema and application across the **expand, migrate, contract** phases.

Within DATABASE_MYSQL, this topic connects to table design, data types, keys, SQL queries, indexes, transactions, and concurrency control; it also ties into reading execution plans, query tuning, privilege management, backups, and relational database incident operations.

## 1. Objectives and concepts

After this lesson, you will be able to:

- Identify components that depend on table and column names.
- Distinguish direct renames from schema changes with a compatibility phase.
- Use `RENAME TABLE` and `RENAME COLUMN` properly.
- Recognize risks when using `CHANGE COLUMN` and altering columns with dependencies.
- Design rollouts so old and new application versions operate side by side during transition.
- Check metadata locks, replication, and queries still referencing old schemas.
- Determine safe conditions for dropping legacy columns/tables and prepare rollbacks.

An **application contract** is the set of assumptions applications and related systems rely on when accessing the database: schema names, tables, columns, data types, nullability, defaults, indexes, constraints, privileges, and data semantics. A rename might leave underlying data unchanged yet still break the contract if clients continue sending SQL using the old name.

A schema may be consumed by many components:

- APIs, workers, cron jobs, batch jobs, and application versions rolling out gradually.
- ORM mappings, prepared statements, query builders, and raw SQL.
- Views, triggers, stored procedures, functions, and events.
- Foreign keys, indexes, generated columns, and partitions.
- BI reports, ETL jobs, CDC consumers, data warehouses, and operational scripts.
- Dashboards, customer support tools, and ad-hoc queries.
- Backups, restores, migration tools, and data validation workflows.

Therefore, before renaming, know who uses the object, how they use it, and when they can switch to the new name.

## 2. Inventorying dependencies before changing

### 2.1. Finding dependencies inside MySQL

Information Schema reveals many references stored in metadata. For example, listing columns of a table:

~~~sql
SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME,
       COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT,
       EXTRA, GENERATION_EXPRESSION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'appdb'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
~~~

Find foreign keys referencing the table or column:

~~~sql
SELECT CONSTRAINT_SCHEMA, TABLE_NAME, COLUMN_NAME,
       CONSTRAINT_NAME, REFERENCED_TABLE_SCHEMA,
       REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE REFERENCED_TABLE_SCHEMA = 'appdb'
  AND REFERENCED_TABLE_NAME = 'orders';
~~~

Find views referencing the table:

~~~sql
SELECT VIEW_SCHEMA, VIEW_NAME, TABLE_SCHEMA, TABLE_NAME
FROM INFORMATION_SCHEMA.VIEW_TABLE_USAGE
WHERE TABLE_SCHEMA = 'appdb'
  AND TABLE_NAME = 'orders';
~~~

Find triggers attached to the table:

~~~sql
SELECT TRIGGER_SCHEMA, TRIGGER_NAME, EVENT_OBJECT_SCHEMA,
       EVENT_OBJECT_TABLE, ACTION_TIMING, EVENT_MANIPULATION,
       ACTION_STATEMENT
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE EVENT_OBJECT_SCHEMA = 'appdb'
  AND EVENT_OBJECT_TABLE = 'orders';
~~~

Find indexes using a column:

~~~sql
SELECT TABLE_SCHEMA, TABLE_NAME, INDEX_NAME,
       COLUMN_NAME, SEQ_IN_INDEX, NON_UNIQUE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = 'appdb'
  AND TABLE_NAME = 'orders'
  AND COLUMN_NAME = 'customer'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

You can inspect view, routine, and event definitions through the corresponding Information Schema tables (`VIEWS`, `ROUTINES`, and `EVENTS`). However, metadata does not always capture every dependency. Dynamically concatenated SQL strings, table names from config files, or application-generated queries are not recorded as static metadata dependencies.

### 2.2. Finding dependencies outside the database

Combine metadata checks with source code and configuration searches:

- Search for old table/column names across repositories, migrations, query templates, and config files.
- Check ORM entities, mappings, serializers, and API contracts.
- Check job schedulers, indirectly invoked stored procedures, and triggers on other tables.
- Check CDC connectors, schema registries, ETL pipelines, dashboards, and reports.
- Check consumers running older versions during rollouts.
- Check support scripts, notebooks, and operational queries stored outside the main repository.

A search returning zero hits for the old name does not prove zero dependencies remain. For example, an application may construct table names from config variables or dynamic SQL. Trace both data flow and ownership of every consumer.

### 2.3. Building a dependency matrix and migration plan

Before running DDL, document:

| Dependency | Where old name is used | Owner / team | Transition method | Completion criterion |
|---|---|---|---|---|
| Old API version | Read/write SQL | App team | Deploy compatible version | Zero old instances left |
| Background worker | Status update query | Ops team | Upgrade workers and drain old jobs | Zero jobs using old name |
| Reporting view | `SELECT` from old table | Data team | Update view definition | Reports verified accurate |
| Trigger | Audit logging | DBA/app team | Inspect and update trigger | Write tests pass |
| CDC/ETL | Old column mapping | Data team | Update schema mapping | Consumers read new schema |
| Support scripts | Manual SQL | Ops team | Update docs and scripts | Zero runbooks calling old name |

Assign an explicit owner to every dependency. If an owner cannot be identified or you do not know whether a consumer is still active, treat that as an unresolved risk before contracting.

## 3. Direct table and column renames

### 3.1. Renaming a table with RENAME TABLE

Basic syntax:

~~~sql
RENAME TABLE appdb.orders TO appdb.customer_orders;
~~~

This statement updates the object name in metadata. Table data is not copied into a new table simply because the name changed. However, the operation still requires metadata locks and may wait on transactions or queries holding metadata locks on the table.

Multiple renames can execute in a single statement:

~~~sql
RENAME TABLE
  appdb.orders TO appdb.orders_archive,
  appdb.orders_next TO appdb.orders;
~~~

This is useful when swapping names between an active table and a prepared table. Confirm all source/target names exist in the expected state with zero name collisions. Atomic/crash-safe behavior depends on supported MySQL version and storage engine; verify against your target version and test in a staging environment before using it for cutover.

Renaming a table does not automatically rewrite SQL outside the database. Applications, scripts, query templates, and CDC configs may still reference the old name. Never assume view definitions, routines, or dynamic SQL are automatically rewritten to the new name. Inspect and redeploy dependent objects in planned order.

### 3.2. Renaming a column with RENAME COLUMN

On MySQL 8.0 and newer, you can use:

~~~sql
ALTER TABLE appdb.customer_orders
  RENAME COLUMN customer TO customer_name;
~~~

`RENAME COLUMN` renames without requiring you to re-specify the column's full data type definition. This is usually the cleanest option when the only goal is renaming.

Before executing, check:

- Views, routines, triggers, and applications still referencing the old name.
- Generated columns or expressions depending on the column.
- Associated indexes, unique keys, and foreign keys.
- CDC mappings and downstream schema consumers.
- MySQL version and supported DDL algorithm for the specific table structure.

Do not assume all dependencies automatically adapt simply because `ALTER TABLE` succeeded. Re-read dependent object definitions and test actual queries.

### 3.3. Distinguishing RENAME COLUMN from CHANGE COLUMN

`CHANGE COLUMN` can rename and modify the column definition simultaneously:

~~~sql
ALTER TABLE appdb.customer_orders
  CHANGE COLUMN customer customer_name
  VARCHAR(150) NOT NULL;
~~~

`CHANGE COLUMN` requires restating the entire column definition. Omitting `UNSIGNED`, `NULL`/`NOT NULL`, `DEFAULT`, `COMMENT`, charset, collation, generated attributes, or other properties silently alters the schema unexpectedly.

When only renaming, prefer `RENAME COLUMN` on supported versions. If forced to use `CHANGE COLUMN` due to an older version or simultaneous definition changes, pull the current definition from `SHOW CREATE TABLE`, preserve all required attributes, and diff before/after DDL.

~~~sql
SHOW CREATE TABLE appdb.customer_orders;
~~~

Never use `CHANGE COLUMN` as a casual rename without inspecting the complete column definition first.

## 4. Why can a direct rename break the application?

Suppose application version A executes:

~~~sql
SELECT order_id, customer
FROM appdb.orders
WHERE order_id = ?;
~~~

A DBA executes:

~~~sql
RENAME TABLE appdb.orders TO appdb.customer_orders;
~~~

After the DDL, version A queries still ask for `appdb.orders` and fail because the old name no longer exists. Likewise, renaming `customer` to `customer_name` breaks old queries resolving that column.

In continuous deployment environments, not every application instance flips versions at the exact same instant. You may have:

- Old instances serving active requests.
- New instances already receiving traffic.
- Old workers executing long-running jobs.
- CDC consumers reading the old schema.
- Batch scripts running only at night.
- Connection pools caching prepared statements created before DDL occurred.

Therefore, compatible DDL must be coordinated with the deployment schedule and lifecycle of every client.

## 5. The expand, migrate, contract strategy

For systems requiring continuous uptime, split changes into phases so old and new versions coexist safely during a transition period.

### 5.1. Expand: add new structures

Suppose `customer` must become `customer_name`. Instead of renaming immediately, add a new column:

~~~sql
ALTER TABLE appdb.orders
  ADD COLUMN customer_name VARCHAR(150) NULL;
~~~

At this stage:

- The old column remains intact so old applications keep running.
- The new column is created with the agreed data type and nullability.
- New indexes or constraints are added per plan.
- Evaluate DDL cost, metadata locks, and disk space before deploying.

If renaming a table, consider creating a new table with the target schema and preparing data synchronization. Copying an entire table can consume heavy resources; pick a suitable online schema change tool when minimal downtime is required.

### 5.2. Migrate: transition application and data

Deploy application changes in a way that stays compatible with the existing schema:

1. An intermediate application release can read both old and new columns or write both following clear rules.
2. Backfill historical data into the new column in small batches.
3. Ensure ongoing changes during the backfill are also synchronized.
4. Compare row counts, `NULL`s, checksums, or business values between both columns.
5. Switch application reads to the new column once data is complete.
6. Monitor error rates and old-column accesses before stopping writes to the old column.

Example batched backfill using an ascending key:

~~~sql
UPDATE appdb.orders
SET customer_name = customer
WHERE order_id > 0
  AND order_id <= 10000
  AND customer_name IS NULL;
~~~

Repeat across chosen key ranges while monitoring transaction time, locks, redo logs, and replication lag. Tune batch size against live load. Avoid running a single massive `UPDATE` that inflates undo/redo, holds locks long, or pushes replicas far behind.

If new writes still target `customer` during backfill, ensure `customer_name` updates accordingly. You can use application-level dual-writes or temporary triggers, provided you designate one authoritative source and define update order to avoid loops or overwriting newer values with stale data. Test inserts, updates, `NULL`s, retries, and transaction rollbacks.

Example application-layer dual-write:

~~~sql
UPDATE appdb.orders
SET customer = ?,
    customer_name = ?
WHERE order_id = ?;
~~~

Both values must derive from the same input and commit in the same transaction. Never deploy two independent write paths without conflict-resolution rules.

### 5.3. Contract: remove legacy structures

Drop the old column only after confirming:

- All applications and workers have switched to the new column.
- Zero queries, views, routines, triggers, or jobs need the old column.
- CDC, reports, ETL, and consumers use the new schema.
- Backfill is finished and data verification passed.
- Verified backups/restores or recovery procedures exist.
- The agreed rollback window with system owners has elapsed.

Only then execute:

~~~sql
ALTER TABLE appdb.orders
  DROP COLUMN customer;
~~~

`DROP COLUMN` should never be rushed. Once dropped, reverting to old application code will fail unless the old column is restored and backfilled.

## 6. Renaming tables during a compatibility phase

Renaming a table is more complex than renaming a column because many components and foreign keys may reference the table.

One approach to evaluate is creating the new table alongside a compatibility object under the old name during transition. For example, a simple view can expose the old name for read queries:

~~~sql
CREATE VIEW appdb.orders AS
SELECT order_id, customer_name, created_at
FROM appdb.customer_orders;
~~~

This is only an illustrative example. Not every view is updatable; views containing `JOIN`, aggregates, `DISTINCT`, `GROUP BY`, or other constructs cannot accept writes like a base table. Views also cannot act as targets of foreign key constraints. Before using a compatibility view, check privileges, triggers, updatability, performance, and all consumers.

If older applications must write to the old table name, pick a controlled synchronization approach:

- Upgrade all writers before renaming.
- Use a tested compatibility layer with explicit write semantics.
- Build the new table, sync via CDC/triggers or an online schema change tool, then switch endpoints in a short window.

Never maintain two independent tables where old apps write one and new apps write the other without transactional synchronization. That causes split-brain data.

For tables with foreign keys, triggers, or many dependent views, plan each object individually. Inspect metadata after renaming and verify constraints still point to the intended target table. Never assume all dependencies rename automatically.

## 7. Metadata locks and operational impact

### 7.1. DDL requires metadata locks

MySQL uses metadata locks to protect object definitions while queries and DDL execute. A transaction using a table can hold metadata locks until the transaction ends. Thus, `ALTER TABLE` or `RENAME TABLE` can end up waiting behind a long-running query or transaction.

Even when a DDL operation supports `INSTANT` or `INPLACE`, it still needs metadata locks during certain phases. "Online DDL" does not mean zero blocking or zero performance impact.

Check waiting metadata locks:

~~~sql
SELECT OBJECT_TYPE, OBJECT_SCHEMA, OBJECT_NAME,
       LOCK_TYPE, LOCK_DURATION, LOCK_STATUS,
       OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = 'appdb'
  AND OBJECT_NAME = 'orders';
~~~

Find long transactions:

~~~sql
SELECT trx_id, trx_started, trx_state,
       trx_mysql_thread_id, trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Cross-reference with `PROCESSLIST` and application logs to identify the client holding the transaction. Never kill connections arbitrarily; assess whether the transaction can safely roll back and its business impact first.

### 7.2. Controlling wait times

Set a lock wait timeout on the DDL session to avoid waiting indefinitely:

~~~sql
SET SESSION lock_wait_timeout = 10;
~~~

If DDL fails to acquire the metadata lock within this period, it aborts cleanly and can be retried in a suitable window. Pick the timeout based on operational policy. Never hammer retries while the blocker remains unresolved, as repeated waits can queue new queries behind the metadata lock wait.

### 7.3. Choosing DDL algorithms

MySQL provides DDL algorithms such as `INSTANT`, `INPLACE`, and `COPY`; support depends on change type, version, storage engine, and table layout.

- `INSTANT` typically alters metadata only and avoids full table rebuilds for supported operations.
- `INPLACE` can avoid copying the whole table yet may still read/write data or rebuild indexes.
- `COPY` builds a new table and copies data; generally demands more I/O, disk space, and time.

Do not blindly tack `ALGORITHM=INSTANT` or `LOCK=NONE` onto every `ALTER TABLE`. If unsupported, the statement errors out; if omitted, MySQL may pick a heavier algorithm than expected. Verify version docs, test on an equivalent clone, and measure runtime and locks before production.

## 8. Replication, CDC, and deployment ordering

DDL is generally logged to the binary log as statement events and applied on replicas. When renaming a table or column on the primary, replicas must receive the corresponding structure before queries or new application versions hit replicas with the new name.

For CDC consumers:

- Check whether connectors detect schema changes automatically.
- Determine whether consumers accept new column names or need compatibility mappings.
- Check schema registries and downstream event formats.
- Avoid renaming and changing data types simultaneously if unnecessary; separating changes isolates failure causes.
- Ensure consumers can process events from both before and after the schema transition.

An easily controllable rollout sequence:

1. Deploy schema changes in a backward-compatible manner.
2. Update consumers, views, and components that can be prepared ahead of time.
3. Roll out the new application version in batches.
4. Backfill and verify data.
5. Switch reads/writes to the new structure.
6. Monitor long enough to confirm zero legacy consumers remain.
7. Contract by dropping obsolete objects.

For read replicas, wait until DDL has applied and check replication status before routing queries using new column/table names to replicas. With replication lag, a new app hitting a lagging replica immediately fails with "unknown column" if DDL hasn't arrived yet.

## 9. Rollback and recovery

### 9.1. Rollback before contract

During expand/migrate, while the old column still exists and remains accurately synced, you can switch application reads back to the old column. Before rolling back:

- Halt rollout of the new version.
- Identify the authoritative data source and sync direction.
- Check for updates written exclusively to the new column.
- Reverse-sync if the old column stopped receiving updates.
- Confirm the old application can read current data cleanly.

For a direct rename, rollback may use an inverse `RENAME TABLE` or `RENAME COLUMN` if no new dependencies or unexpected data exist. However, renaming back does not automatically revert applications, views, or SQL already deployed with the new name.

### 9.2. After contract

After `DROP COLUMN` or `DROP TABLE`, rollback is no longer a simple rename statement. You must restore structure, recover data from backups/binlogs or reconstruct from an authoritative source, and re-verify dependencies.

Determine beforehand:

- Which backups can restore and how long restoration takes?
- Are binary logs available to replay to the needed point in time?
- Can the column be reconstructed from other data?
- Does recovery require pausing writes?
- Who approves the rollback decision?

Never drop old objects simply because the new application deployed cleanly. Require evidence that every consumer switched and data reconciled.

## 10. Example plan for renaming column customer

Suppose `orders` has column `customer` and needs to move to `customer_name`.

| Phase | Schema | Application | Checks |
|---|---|---|---|
| Initial | `customer` only | Old version reads/writes `customer` | Record row counts and dependencies |
| Expand | Add `customer_name NULL` | Old version continues running | DDL completes, no abnormal locks |
| Migrate 1 | Both columns | Intermediate version writes both | Batched backfill, reconciliation |
| Migrate 2 | Both columns | New version reads `customer_name` | Monitor errors and old-column access |
| Contract | Drop `customer` | Only new version active | Confirm zero legacy consumers left |

Illustrative statements:

~~~sql
-- 1. Expand
ALTER TABLE appdb.orders
  ADD COLUMN customer_name VARCHAR(150) NULL;

-- 2. Backfill in batches; repeat for subsequent key ranges
UPDATE appdb.orders
SET customer_name = customer
WHERE order_id > 0
  AND order_id <= 10000
  AND customer_name IS NULL;

-- 3. Reconcile
SELECT COUNT(*) AS mismatch_count
FROM appdb.orders
WHERE NOT (customer_name <=> customer);

-- 4. Contract only after all consumers have migrated
ALTER TABLE appdb.orders
  DROP COLUMN customer;
~~~

The NULL-safe equality operator **`<=>`** compares two values even when one or both are `NULL`. If business logic allows the two columns to diverge after a cutoff point, define exact sync rules before running this reconciliation query.

This example assumes both columns represent the exact same data and dual-writing is active. Do not run `DROP COLUMN` until all contract preconditions are confirmed.

## 11. Pre-rename checklist

### Discovery and design

- [ ] Identified exact object, schema, and new name.
- [ ] Inventoried foreign keys, indexes, views, triggers, routines, events, and generated columns.
- [ ] Searched for dependencies across applications, workers, reports, CDC, ETL, and ops scripts.
- [ ] Determined how long old and new application versions may coexist.
- [ ] Chose direct rename vs. expand/migrate/contract.
- [ ] Defined data synchronization method and authoritative source.

### Before DDL

- [ ] Have verified backups and tested recovery plans.
- [ ] Tested DDL on a clone of equivalent size and configuration.
- [ ] Evaluated DDL algorithm, metadata locks, and disk space.
- [ ] Froze competing DDL changes on the same object.
- [ ] Prepared plans for replication lag and CDC schema changes.

### After DDL and before contract

- [ ] Re-inspected `SHOW CREATE TABLE` and metadata dependencies.
- [ ] Tested read/write queries across active application versions.
- [ ] Verified triggers, views, routines, and background jobs.
- [ ] Reconciled old/new data and checked application errors.
- [ ] Confirmed zero clients still reference the old name.
- [ ] Obtained data owner approval before running `DROP`.

## 12. Self-check

**Scenario 1:** An application has multiple running instances. A DBA renames `orders` to `customer_orders` during peak hours. What can happen?

**Hint:** Old instances and background jobs still querying `orders` immediately fail. The DDL may also stall waiting on metadata locks from active transactions using the table.

**Scenario 2:** You need to rename `customer` to `customer_name` on MySQL 8.0. When only renaming, which syntax should you prefer?

**Hint:** Use `ALTER TABLE ... RENAME COLUMN` so you do not have to restate the entire column definition. Then verify all dependencies and consumers.

**Scenario 3:** A migration uses `CHANGE COLUMN` and accidentally omits `UNSIGNED` and `DEFAULT`. What are the consequences?

**Hint:** The statement silently alters column type and default behavior unintentionally. Diff `SHOW CREATE TABLE` before/after and preserve all required attributes.

**Scenario 4:** Backfill finished, yet old application instances can still update `customer`. Can `customer` be dropped now?

**Hint:** Not yet. Ensure all new updates also synchronize to `customer_name`, migrate all writers, and verify zero legacy consumers remain.

**Scenario 5:** After `DROP COLUMN`, the team wants to roll back by renaming the new column back to the old name. Is that sufficient?

**Hint:** No. The old column and any un-migrated data in it were deleted. Restore structure and data from backup/binlogs or an authoritative source, then re-verify dependencies.

## 13. Key takeaways

- Table and column names are part of the contract between the database and every client.
- Inventory dependencies across Information Schema, source code, jobs, CDC, ETL, and reports before renaming.
- `RENAME TABLE` and `RENAME COLUMN` update metadata; they do not automatically rewrite external SQL.
- `CHANGE COLUMN` requires restating full column definitions and can accidentally alter attributes.
- Expand/migrate/contract lets multiple application versions coexist safely during transition.
- Backfills need appropriate batching and synchronization for incoming updates.
- Online DDL can still require metadata locks; test algorithms and wait times on equivalent environments.
- `DROP` legacy structures only after all consumers have migrated, data is reconciled, and rollback paths are evaluated.
- After contraction, recovery requires backups/binlogs or data reconstruction; renaming back does not restore dropped data.

## References

- [MySQL 8.4 Reference Manual: RENAME TABLE Statement](https://dev.mysql.com/doc/refman/8.4/en/rename-table.html) — syntax and conditions for renaming tables.
- [MySQL 8.4 Reference Manual: ALTER TABLE Statement](https://dev.mysql.com/doc/refman/8.4/en/alter-table.html) — `RENAME COLUMN`, `CHANGE COLUMN`, and DDL algorithms.
- [MySQL 8.4 Reference Manual: Online DDL](https://dev.mysql.com/doc/refman/8.4/en/innodb-online-ddl-operations.html) — algorithms and lock levels for InnoDB operations.
- [MySQL 8.4 Reference Manual: Metadata Locking](https://dev.mysql.com/doc/refman/8.4/en/metadata-locking.html) — how MySQL manages metadata locks.
- [MySQL 8.4 Reference Manual: INFORMATION_SCHEMA](https://dev.mysql.com/doc/refman/8.4/en/information-schema.html) — metadata for dependency inventorying.
