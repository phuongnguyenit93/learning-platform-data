# Managing DDL, Stored Programs, and Reference Data with Version Control

The MySQL schema is part of the application's source code. Tables, indexes, constraints, stored procedures, functions, triggers, events, and reference data all determine how the application reads and writes data. If you change them manually in each environment, databases easily drift apart and it becomes difficult to determine which version is running. Managing them with version control and ordered migrations ensures every change is reviewed, deployable repeatably, testable, and traceable.

This lesson belongs to the **Schema Evolution** chapter of the **DATABASE_MYSQL** module. On the path to mastering MySQL—from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, privilege management, backups, and operations—schema evolution connects structural changes to the application release lifecycle. The scope of this lesson covers DDL, stored programs, and reference data stored in the repository and then deployed through controlled migrations.

## 1. Why version control database changes?

An application may release a new version while the database still retains the old schema. If you deploy code without a required column, index, routine, or reference data, the application can fail immediately at runtime. Conversely, changing the database before compatible code is ready can break the currently running application version.

Version control for databases helps answer the following questions:

- How do schemas differ across development, staging, and production environments?
- Which changes were deployed, at what time, and by whom?
- Does a running stored procedure match the exact version in the repository?
- Which reference data was added, modified, or deprecated in each release?
- When a migration fails, how can it be resumed, recovered, or fixed forward?

At least four asset groups need to be managed:

| Group | Examples | How to version |
|---|---|---|
| Schema structure | Database, table, column, index, constraint | Ordered DDL migrations |
| Stored programs | Procedure, function, trigger, event | Controlled create/update scripts |
| Reference data | Order statuses, customer types, country codes | Idempotent DML migrations |
| Related privileges and configuration | GRANT, role, SQL mode, event scheduler | Environment-specific deployment scripts aligned with security policy |

Not all data is reference data. Operational business data such as orders, transactions, customer history, and personal data must be managed through backups, data migrations, or data synchronization workflows. Do not commit production dumps into the repository just to version the schema.

## 2. Organizing the repository for the database

Migrations and stored program definitions can be separated into distinct directories. For example:

~~~text
database/
  migrations/
    V20261119_01__create_customer_status.sql
    V20261119_02__seed_customer_status.sql
    V20261119_03__add_status_to_customers.sql
    V20261119_04__create_customer_summary_procedure.sql
  reference/
    README.md
  routines/
    procedures/
    functions/
    triggers/
    events/
  tests/
    schema/
    data-integrity/
~~~

This structure is only one way to organize files. If your migration tool requires a specific directory, follow the tool's configuration and maintain consistent conventions.

A migration should have a descriptive action name and a unique version. For example, using Flyway conventions:

- `V20261119_01__create_customer_status.sql`
- `V20261119_02__seed_customer_status.sql`
- `V20261119_03__add_status_to_customers.sql`

Flyway records executed migrations in a schema history table, including version, checksum, timestamp, and status. Applied versioned migration files must be treated as immutable. If you need to fix logic, create a new migration; modifying an old file changes its checksum and causes the deployment state to no longer match history.

Other tools use similar concepts, though table names, file naming rules, and checksum mechanisms may differ. Read your tool's documentation before choosing a convention. Never allow two migrations to share the same version after merging branches.

## 3. DDL migrations: changing the schema step by step

Suppose you need to add a customer status table. The first step creates the reference table:

~~~sql
CREATE TABLE customer_status (
  status_code VARCHAR(24) NOT NULL,
  label VARCHAR(80) NOT NULL,
  sort_order SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  PRIMARY KEY (status_code)
) ENGINE=InnoDB;
~~~

Next, add the new column to the customers table. While the application is running, start with a nullable column or a compatible default so the old code version continues to work:

~~~sql
ALTER TABLE customers
  ADD COLUMN status_code VARCHAR(24) NULL,
  ADD INDEX idx_customers_status_code (status_code);
~~~

Once both the reference table and the new column exist, add the foreign key:

~~~sql
ALTER TABLE customers
  ADD CONSTRAINT fk_customers_status
  FOREIGN KEY (status_code)
  REFERENCES customer_status (status_code)
  ON UPDATE RESTRICT
  ON DELETE RESTRICT;
~~~

At this stage, the column allows `NULL`, so existing rows without a status remain valid. Afterward, backfill the data and switch the code to read/write the new column. Once all rows have valid values, a separate migration can alter the column to `NOT NULL` if business rules require it.

Do not bundle a large change into a single hard-to-recover file. Split migrations by purpose: create objects, seed reference data, backfill, add final constraints, or drop legacy structures. Steps must be ordered so every running application version remains compatible with the schema at deploy time.

## 4. MySQL DDL and transaction boundaries

DDL includes statements such as `CREATE TABLE`, `ALTER TABLE`, `CREATE INDEX`, `DROP TABLE`, `CREATE PROCEDURE`, and `CREATE TRIGGER`. Most MySQL DDL statements cause an implicit commit. Therefore, you cannot rely on `START TRANSACTION` followed by `ROLLBACK` to undo an entire migration that contains DDL.

For example:

~~~sql
START TRANSACTION;

UPDATE customers
SET display_name = TRIM(display_name)
WHERE display_name <> TRIM(display_name);

ALTER TABLE customers
  ADD COLUMN migrated_at TIMESTAMP NULL;

ROLLBACK;
~~~

The `ALTER TABLE` statement may commit the open transaction before executing; the subsequent `ROLLBACK` neither undoes the DDL nor restores the DML that was implicitly committed earlier.

MySQL 8.0 supports **atomic DDL** for many operations on supported objects. Atomic DDL ensures that a single DDL operation either completes entirely or is rolled back if the server crashes during execution. This does not make DDL rollbackable within a user transaction, nor does it combine multiple DDL statements into a single shared transaction.

Therefore:

- Separate DDL from backfill DML when clear transaction boundaries are required.
- Do not write migrations assuming a `ROLLBACK` statement will reverse an `ALTER TABLE`.
- Plan for intermediate states if a migration stops between files.
- For destructive changes, prepare a backup or recoverable copy before running.
- Verify behavior on the exact MySQL version and storage engine in use.

Standard DML can still be grouped inside an InnoDB transaction as long as no DDL causing an implicit commit is interleaved:

~~~sql
START TRANSACTION;

UPDATE customers
SET status_code = 'ACTIVE'
WHERE status_code IS NULL
  AND id >= 1
  AND id < 1001;

COMMIT;
~~~

For large tables, split backfills into primary-key batches and commit each batch to limit undo log growth, lock hold times, and impact on replicas.

## 5. Managing migration history and repeatability

A migration runner typically stores history in a dedicated table. Flyway uses `flyway_schema_history` by default; other tools may use different names and schemas. The history table helps determine which files have run, which version is currently applied, and whether checksums match the current files.

Key rules:

1. **Unique versions:** each migration version appears only once across the entire history.
2. **Applied migrations are immutable:** do not edit the contents of a versioned file that has already run on any shared environment.
3. **New changes create new migrations:** use a new file to fix bugs or adjust the schema.
4. **Verify checksums:** if a checksum differs, investigate the root cause. Do not manually delete history or edit checksums just to make a pipeline green.
5. **Do not run migrations concurrently:** only one process may orchestrate schema changes on a given database at a time.
6. **Log deployments:** record the application version, migration version, timestamp, outcome, and executing user/process.

If two development branches both create a migration, resolve the version conflict before merging. Never reorder migrations that have already run in production by renaming files; create a subsequent migration to bring the schema to the desired state.

An idempotent migration can be re-run without unintended side effects, though not all DDL is automatically idempotent. For instance, `CREATE TABLE IF NOT EXISTS` does not verify whether an existing table's structure matches the expected definition. The migration runner should be the source of truth for which files have executed; do not use `IF NOT EXISTS` to mask schema drift.

## 6. Managing stored procedures and functions

Stored procedures and functions are database source code. Store their complete definitions in the repository, review them alongside the application, and deploy them via versioned migrations.

Example of a procedure reporting order count per customer:

~~~sql
DELIMITER //

DROP PROCEDURE IF EXISTS get_customer_order_count//

CREATE PROCEDURE get_customer_order_count(
  IN p_customer_id BIGINT UNSIGNED
)
SQL SECURITY INVOKER
READS SQL DATA
BEGIN
  SELECT
    customer_id,
    COUNT(*) AS order_count
  FROM orders
  WHERE customer_id = p_customer_id
  GROUP BY customer_id;
END//

DELIMITER ;
~~~

In this example:

- `DROP PROCEDURE IF EXISTS` allows recreating a procedure with the same name.
- `SQL SECURITY INVOKER` executes the routine with the caller's privileges. The default for routines is `DEFINER`, so choose the privilege model explicitly based on your requirements.
- `READS SQL DATA` declares the routine's characteristic; this declaration does not replace checking logic and access permissions.
- `DELIMITER` is a MySQL command-line client directive to change the statement terminator when the routine body contains semicolons; in MySQL Shell, use `\delimiter`. This is a client-side command, not an SQL statement sent to the server. Your migration runner must also support statement splitting appropriate for routine bodies.

The drop-then-create pattern leaves a brief window where the procedure does not exist; if `CREATE` fails, the old procedure has already been deleted. For high-availability systems, you can create the new procedure under a new versioned name, switch the application to call the new name, verify it, and drop the old name in a later migration. If reusing the same name, choose an appropriate deployment window and test beforehand.

MySQL does not support `CREATE OR REPLACE PROCEDURE` in the way some other DBMSs do. Do not assume `CREATE PROCEDURE` will overwrite an existing routine.

### Routine definitions and privileges

Routines have either `SQL SECURITY DEFINER` or `SQL SECURITY INVOKER`:

- **DEFINER:** the routine executes with the privileges of the definer account. Manage that account and its privileges carefully.
- **INVOKER:** the routine executes with the privileges of the caller. The caller must have privileges on the accessed objects.

Do not hardcode a personal account or an environment-specific account as the definer. When `DEFINER` is needed, use a centrally managed service account with controlled privileges and ensure the account exists in every target environment. After drop/create, re-verify `EXECUTE` privileges and related `GRANT`s; recreating a routine may require reapplying privileges previously granted on that routine.

Functions have additional requirements regarding determinism, privileges, and declared characteristics. Do not declare `DETERMINISTIC` just to bypass binary logging configuration if the function actually depends on changing data or state. Declarations must accurately reflect behavior.

## 7. Managing triggers and events

A trigger is attached to a table and timing event such as `BEFORE INSERT`, `AFTER UPDATE`, or `BEFORE DELETE`. Store each trigger as a separate script or group them per table in a clear order.

Example:

~~~sql
DELIMITER //

DROP TRIGGER IF EXISTS customers_before_insert//

CREATE TRIGGER customers_before_insert
BEFORE INSERT ON customers
FOR EACH ROW
BEGIN
  SET NEW.display_name = TRIM(NEW.display_name);
END//

DELIMITER ;
~~~

Triggers do not have a universal `CREATE OR REPLACE TRIGGER` syntax in MySQL. When modifying a trigger, plan for drop/create or creating a new trigger with a different name, then verify the definition and firing order. Modern MySQL versions support multiple triggers for the same timing and event, but ordering must be explicitly declared and verified if logic is order-dependent.

Triggers can create hidden side effects for the application, so keep logic short, predictable, and easy to test. Avoid putting complex end-to-end business workflows into triggers if operators will struggle to trace side effects.

The Event Scheduler executes scheduled events. Example:

~~~sql
CREATE EVENT ev_archive_old_audit
ON SCHEDULE EVERY 1 DAY
DO
  INSERT INTO audit_archive
    (event_id, action_name, created_at)
  SELECT event_id, action_name, created_at
  FROM audit_log
  WHERE created_at < CURRENT_DATE - INTERVAL 90 DAY;
~~~

This example only illustrates the syntax structure. A production event requires mechanisms to prevent duplicate copying, delete source rows after successful archiving, enforce batch sizes, handle errors, and provide monitoring. Do not run sample events against real data without adding those safeguards.

Inspect the event scheduler and created events:

~~~sql
SHOW VARIABLES LIKE 'event_scheduler';
SHOW EVENTS FROM appdb;
SHOW CREATE EVENT ev_archive_old_audit;
~~~

The Event Scheduler must be enabled for events to execute. Enabling the scheduler is a separate operational configuration; do not assume a `CREATE EVENT` script turns it on automatically. Triggers, events, and routines also have definers and privileges that must be managed like any executable code object.

## 8. Versioning reference data

Reference data is a small, stable set of values shared across multiple parts of the application—such as order statuses, customer types, units of measure, currency codes, or country codes. These values should be versioned alongside the schema because application code often depends on them.

Prefer stable business keys such as `status_code` rather than relying on `AUTO_INCREMENT` values that may differ across environments.

~~~sql
CREATE TABLE order_status (
  status_code VARCHAR(24) NOT NULL,
  label VARCHAR(80) NOT NULL,
  sort_order SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  is_terminal BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (status_code)
) ENGINE=InnoDB;
~~~

Load standard values via migration:

~~~sql
INSERT INTO order_status
  (status_code, label, sort_order, is_terminal)
VALUES
  ('PENDING', 'Pending', 10, FALSE),
  ('PAID', 'Paid', 20, FALSE),
  ('SHIPPED', 'Shipped', 30, FALSE),
  ('CANCELLED', 'Cancelled', 90, TRUE)
ON DUPLICATE KEY UPDATE
  label = VALUES(label),
  sort_order = VALUES(sort_order),
  is_terminal = VALUES(is_terminal);
~~~

The `VALUES(column)` syntax in the `ON DUPLICATE KEY UPDATE` clause has been deprecated since MySQL 8.0.20. On MySQL 8.0.19 and later, you can use a row alias:

~~~sql
INSERT INTO order_status
  (status_code, label, sort_order, is_terminal)
VALUES
  ('PENDING', 'Pending', 10, FALSE),
  ('PAID', 'Paid', 20, FALSE)
AS incoming
ON DUPLICATE KEY UPDATE
  label = incoming.label,
  sort_order = incoming.sort_order,
  is_terminal = incoming.is_terminal;
~~~

Choose syntax compatible with your system's MySQL version. The first example works easily on older versions but emits a deprecation warning on newer releases; the alias syntax requires MySQL 8.0.19 or newer.

Upsert allows a migration to be re-applied without creating duplicate primary keys. However, it also updates the specified columns whenever a key already exists. Use it only for canonical data owned by the repository. If users or operations teams are allowed to edit labels or statuses in production, separate user-managed configuration from standard seed data.

### Adding, changing, and deprecating reference codes

- **Adding a code:** insert the row via migration before application code begins writing that code.
- **Renaming a label:** update the label if the code remains stable and only the display text changes.
- **Changing meaning:** create a new code instead of silently changing the meaning of an existing code.
- **Deprecating:** mark `is_active = FALSE` or `is_deprecated = TRUE`; keep the row if historical data still references it.
- **Deleting a code:** delete only when certain no historical data or foreign keys reference it and business rules permit removal.

Never reuse a retired code for a different meaning. Doing so causes historical reports to misinterpret old data.

## 9. Deploying with the expand–migrate–contract pattern

While an application is serving users, schema changes should be divided into three phases:

<text>**Expand** — add new structures in a backward-compatible way.</text>

- Add nullable columns, new tables, indexes, or new routines.
- Keep existing structures so the currently running application version keeps working.
- Deploy code capable of reading/writing the new structure while remaining compatible with the old schema if needed.

<text>**Migrate** — transition data and application traffic.</text>

- Backfill data in batches.
- Check for nulls, duplicates, foreign keys, and row counts.
- Switch the application to read/write the new structure.
- Monitor errors, replication lag, and query latency.

<text>**Contract** — remove old structures once no clients use them.</text>

- Confirm no code or jobs still read the old column or routine.
- Drop the old structure in a separate migration.
- Monitor post-deployment and keep an appropriate recovery plan ready.

For example, when renaming column `full_name` to `display_name`: instead of renaming immediately and breaking old code, add `display_name`, synchronize data from `full_name`, release code using the new column, monitor, and only drop `full_name` in a later release. If multiple application versions run concurrently, dual-writes or a tested synchronization mechanism are needed during the transition period.

For large datasets, backfill by primary-key ranges:

~~~sql
UPDATE customers
SET display_name = full_name
WHERE id >= 1
  AND id < 1001
  AND display_name IS NULL;
~~~

The migration job repeats the statement across ID ranges, records checkpoints, and only advances to the next batch after the previous one succeeds. Do not hold a single transaction over millions of rows if doing so generates massive undo logs or holds locks for too long.

## 10. Online DDL, metadata locks, and production impact

Not all DDL changes have the same cost. Depending on the operation, MySQL version, and table structure, `ALTER TABLE` may:

- Modify metadata without rebuilding data.
- Execute in place while still consuming I/O and CPU resources.
- Rebuild the table and indexes.
- Wait on metadata locks held by active transactions or queries touching the table.

MySQL provides DDL algorithms such as `INSTANT`, `INPLACE`, and `COPY`; support depends on the specific operation and version. For example, if a change supports instant execution, you can explicitly require it:

~~~sql
ALTER TABLE customers
  ADD COLUMN source_system VARCHAR(32) NULL,
  ALGORITHM=INSTANT;
~~~

If the server does not support the requested algorithm for that operation, the statement fails rather than silently falling back to another method. Do not assume every `ADD COLUMN` is instant or every `INPLACE` operation is lock-free.

Some operations allow `LOCK=NONE` to minimize blocking DML during execution:

~~~sql
ALTER TABLE customers
  ADD INDEX idx_customers_created_at (created_at),
  ALGORITHM=INPLACE,
  LOCK=NONE;
~~~

Use this only when supported by the operation and version. Even online DDL can still acquire metadata locks at the start/end, consume significant resources, and increase replication lag.

Before a large migration:

- Check free disk space, I/O throughput, table size, and estimated duration.
- Identify long-running transactions that might hold metadata locks.
- Test on a clone close to production size.
- Run during an appropriate maintenance window with timeouts and an abort plan.
- Monitor the process list, metadata locks, CPU, I/O, and replica lag.
- Consider online schema change tools such as `gh-ost` or `pt-online-schema-change` if native DDL does not meet requirements; carefully verify foreign keys, triggers, replication topology, and tool limitations.

You can inspect waiting metadata locks via Performance Schema:

~~~sql
SELECT
  OBJECT_SCHEMA,
  OBJECT_NAME,
  LOCK_TYPE,
  LOCK_DURATION,
  LOCK_STATUS,
  OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = DATABASE()
  AND LOCK_STATUS IN ('PENDING', 'GRANTED');
~~~

Correlate the results with the process list and the threads holding locks. Do not blindly kill every session holding a metadata lock; identify the transaction, owner, and impact before acting.

## 11. Rollback and recovery when a migration fails

Not every migration can be safely rolled back. Adding a nullable column can usually remain in place without affecting old code; dropping a column or performing lossy data transformations is hard to reverse.

Distinguish three concepts:

- **Database rollback:** using a transaction to undo uncommitted DML; does not apply to most DDL due to implicit commits.
- **Down migration:** a script that reverses a schema change. Only safe if the data and application still permit reversal.
- **Forward fix:** creating a new migration to repair an invalid state or move the system forward to a valid state.

For example, adding a column does not immediately require a down migration. If the new code hits a bug, you can roll back the application while keeping the new column because old code remains compatible. Conversely, if an old column was already dropped and you discover old code still needs it, you must restore data from backup or create a supplemental migration capable of recovering the data.

Before destructive changes:

1. Identify what data will be lost or transformed.
2. Have a backup and verify restore capability.
3. Record row counts, checksums, or business totals before the change.
4. Define the deployment window and accountable owner.
5. Prepare a tested recovery script or forward fix.
6. Never delete migration history to force the runner to re-execute an old file.

If a migration fails partway through multiple DDL statements, inspect the actual schema and migration history before proceeding. Earlier DDL statements may have already completed even though a later statement failed. Do not blindly re-run the entire script; determine exactly which objects were created or altered.

## 12. Reviewing and testing migrations in CI/CD

The pipeline should validate migrations before deploying to shared databases:

- Spin up an empty database on the target MySQL version and run all migrations from scratch.
- Upgrade a database from the previous version to test the real migration path.
- Check that there are no duplicate migration versions, applied files have not been modified, and checksums match.
- Verify tables, columns, indexes, constraints, and stored programs after migration.
- Run tests for routines, triggers, events, and dependent application queries.
- Load reference data and verify mandatory codes exist.
- Test migrations against sample data containing duplicates, `NULL`s, orphaned foreign keys, and realistic data volumes.
- Measure execution duration, metadata locks, and replication lag in staging.

A query to inspect columns can use `information_schema.COLUMNS`:

~~~sql
SELECT
  TABLE_NAME,
  COLUMN_NAME,
  COLUMN_TYPE,
  IS_NULLABLE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customers'
ORDER BY ORDINAL_POSITION;
~~~

Inspect routines:

~~~sql
SHOW CREATE PROCEDURE get_customer_order_count;
SHOW CREATE TRIGGER customers_before_insert;
~~~

Inspect reference data:

~~~sql
SELECT status_code
FROM order_status
ORDER BY sort_order, status_code;
~~~

CI should verify actual results and expected conditions, not merely confirm that SQL statements ran without error. For events, do not wait for the production schedule to test; verify the definition, privileges, scheduler status, and invoke the business logic via separate routines or tests whenever possible.

## 13. Common schema management mistakes

| Mistake | Consequence | Better practice |
|---|---|---|
| Editing schema directly in production | Repository does not reflect actual state | Route every change through reviewed migrations |
| Editing an applied migration | Checksums and environment histories diverge | Create a new migration |
| Mixing DDL and DML expecting `ROLLBACK` | Data may commit before script fails | Split steps and design intermediate states |
| Dropping a column in the same release as code change | Running older application versions break | Expand–migrate–contract |
| Using `IF NOT EXISTS` to hide drift | Object exists with the wrong definition | Verify schema and migration history |
| Dropping/creating routines without checking privileges | Procedures lose `GRANT`s or get wrong `DEFINER` | Verify security mode, definer, and privileges post-deploy |
| Using seed data to overwrite user-edited data | Operational changes are lost | Separate canonical data from admin-managed data |
| Running large DDL without prior measurement | Metadata locks, high I/O, and replication lag | Test on production-like data and monitor |
| Running two migration runners concurrently | Race conditions and unpredictable schema state | Allow only one process to orchestrate migrations |
| Rolling back by deleting migration history | Loss of visibility into deployed state | Fix forward with a new migration and document clearly |

## 14. Sample schema release workflow

A release involving database changes can follow this sequence:

1. The developer creates DDL, routine, or reference data migrations on a branch.
2. Reviewers check compatibility, affected data, privileges, and DDL duration.
3. CI runs migrations from an empty database and upgrades from the previous schema version.
4. Staging tests with representative data, verifying queries and stored programs.
5. Take a backup or confirm a recovery point before destructive changes.
6. The pipeline deploys migrations in order before releasing code that requires the new schema.
7. Monitor migration history, application errors, locks, I/O, and replica lag.
8. Switch code to use the new structure, backfill, and verify data.
9. In a later release, drop legacy structures once no clients use them.
10. Record the release outcome and schema version alongside the application version.

If multiple services share a database, clearly designate a single service or pipeline that owns the schema. Avoid letting multiple services run competing migrations against the same database without coordination.

## 15. Key takeaways

- DDL, stored programs, and reference data are all assets requiring version control.
- Use versioned migrations with clear ordering and deployment history.
- Do not modify applied migrations; create a new file for subsequent changes.
- Most MySQL DDL causes implicit commits; atomic DDL does not mean DDL can be rolled back by a transaction.
- Manage procedures, functions, triggers, and events as source code; check delimiter, definer, security mode, and `GRANT`s.
- Reference data should use stable keys and idempotent migrations; do not mix it with operational business data.
- Use expand–migrate–contract to preserve compatibility across multi-version application rollouts.
- Online DDL can still consume resources and wait on metadata locks.
- Prepare backups, testing, and forward fixes for destructive changes.
- CI must verify the schema, routines, reference data, and upgrade paths from previous versions.

Database version control establishes a reviewable and reproducible change history. When migrations are ordered, stored programs have explicit execution privileges, reference data uses stable keys, and every release is tested against realistic schemas, MySQL evolution becomes far more predictable across environments.

## References

- [MySQL 8.0 Reference Manual: Statements That Cause an Implicit Commit](https://dev.mysql.com/doc/refman/8.0/en/implicit-commit.html)
- [MySQL 8.0 Reference Manual: Atomic Data Definition Statement Support](https://dev.mysql.com/doc/refman/8.0/en/atomic-ddl.html)
- [MySQL 8.0 Reference Manual: Online DDL](https://dev.mysql.com/doc/refman/8.0/en/innodb-online-ddl.html)
- [MySQL 8.0 Reference Manual: Stored Objects and DEFINER Security](https://dev.mysql.com/doc/refman/8.0/en/stored-objects-security.html)
- [MySQL 8.0 Reference Manual: Event Scheduler](https://dev.mysql.com/doc/refman/8.0/en/events.html)
- [Flyway Documentation: Versioned Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/versioned-migrations)
