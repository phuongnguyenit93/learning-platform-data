# RENAME TABLE, Atomic Renames, and Dependencies to Verify

## Lesson Objectives

After this lesson, you will be able to:

- Use `RENAME TABLE` and `ALTER TABLE ... RENAME` to rename tables.
- Rename multiple tables in a single statement and understand left-to-right execution order.
- Distinguish atomic rename, atomic DDL on server crash, and rollbackable transactions.
- Swap old and new tables using a blue/green pattern.
- Understand metadata locks and why a rename statement may wait on other transactions.
- Inspect impacts on foreign keys, views, triggers, stored programs, privileges, and applications.
- Plan ahead, verify afterward, and prepare recovery procedures.

Renaming a table looks like changing a single identifier. In a running system, table names also appear in foreign keys, views, triggers, stored procedures, access privileges, application code, reports, scheduled jobs, and operational scripts. A `RENAME TABLE` statement can finish in milliseconds yet still break applications if dependencies were not audited.

This lesson focuses on MySQL with InnoDB while highlighting key limitations when using other storage engines or moving tables across databases.

## 1. What Is RENAME TABLE Used For?

`RENAME TABLE` changes the name of one or more tables. Data and table structure stay with the same table object; this is not a statement that copies rows one by one into a new table.

Basic syntax:

~~~sql
RENAME TABLE old_table TO new_table;
~~~

You can qualify the database:

~~~sql
RENAME TABLE shop.orders TO shop.sales_orders;
~~~

The single-table form is equivalent to:

~~~sql
ALTER TABLE shop.orders RENAME TO sales_orders;
~~~

`RENAME TABLE` has the advantage of renaming multiple tables in one statement. `ALTER TABLE ... RENAME` is handy when renaming a single table or combining the rename with other `ALTER TABLE` changes supported by your MySQL version.

Distinguish different rename needs:

| Need | Statement / Approach |
|---|---|
| Rename a table | `RENAME TABLE` or `ALTER TABLE ... RENAME` |
| Rename a column | `ALTER TABLE ... RENAME COLUMN` |
| Rename an index | `ALTER TABLE ... RENAME INDEX` |
| Move a table to another database | `RENAME TABLE db_old.t TO db_new.t` |
| Rename a database | MySQL has no general `RENAME DATABASE` command |
| Rename a `TEMPORARY` table | Use `ALTER TABLE`; `RENAME TABLE` does not apply to `TEMPORARY` tables |

Renaming a table does not automatically rewrite every SQL query in your application. MySQL updates certain relational metadata, but table names hardcoded inside views, stored programs, events, trigger bodies, or application code still need to be audited.

## 2. Renaming a Single Table

Suppose the current table is `shop.customer_old` and you want to rename it to `shop.customer`:

~~~sql
RENAME TABLE shop.customer_old TO shop.customer;
~~~

If the right database is selected via `USE`, you can omit the database prefix:

~~~sql
USE shop;

RENAME TABLE customer_old TO customer;
~~~

Database and table names should follow consistent naming conventions. If a name contains reserved words or special characters, quote the identifier with backticks. In practice, prefer non-keyword identifiers to avoid confusion.

Before running, confirm the source table exists and the target name is free:

~~~sql
SHOW TABLES FROM shop LIKE 'customer_old';
SHOW TABLES FROM shop LIKE 'customer';
~~~

You can inspect metadata:

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    TABLE_TYPE,
    ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME IN ('customer_old', 'customer');
~~~

If the target name already exists, a standard rename fails. Never drop an existing target table just to free up its name without verifying what table it is and whether its data must be kept.

## 3. Renaming Multiple Tables in One Statement

`RENAME TABLE` accepts multiple rename pairs in a single statement:

~~~sql
RENAME TABLE
    shop.customer_old TO shop.customer,
    shop.order_old TO shop.sales_order,
    shop.order_item_old TO shop.sales_order_item;
~~~

Operations execute from left to right. If the statement encounters an error, MySQL does not leave a partial subset of that rename statement applied.

This is useful when a release must atomically rename a group of tables together. For example, a new application release runs only once both the orders table and line-items table carry their new names.

### 3.1. Swapping Two Table Names

Suppose there are two tables:

- `shop.current_data`: the table currently used by the application.
- `shop.next_data`: the newly prepared table.

To swap names so `current_data` holds the contents of `next_data`, you must free the target name first. Use a non-existent intermediate name:

~~~sql
RENAME TABLE
    shop.current_data TO shop.swap_temp,
    shop.next_data TO shop.current_data,
    shop.swap_temp TO shop.next_data;
~~~

Because steps execute left to right:

1. `current_data` is renamed to `swap_temp`.
2. `next_data` is renamed to `current_data`.
3. `swap_temp` is renamed to `next_data`.

After the statement completes, the name `current_data` points to the table object formerly named `next_data`. The name `next_data` points to the old table.

The intermediate name must not already exist. Follow a clear naming convention to avoid colliding with a temporary name created concurrently by another job or migration.

### 3.2. Replacing a Production Table with a Prepared Table

A common pattern is renaming the live table to a backup name and immediately moving the candidate table into the live name:

~~~sql
RENAME TABLE
    shop.orders TO shop.orders_before_release,
    shop.orders_candidate TO shop.orders;
~~~

Both changes execute in one statement. Applications never observe an intermediate state where `orders` does not exist between two separate statements.

However, this is still just a rename operation. Before executing, confirm:

- `orders_candidate` has the right structure, indexes, constraints, and data.
- Recent data has been synchronized up to the cutover moment.
- In-flight write transactions are handled per plan.
- Foreign keys referencing `orders` have been analyzed.
- Views, triggers, privileges, and applications are compatible with the new table.
- A plan exists for handling data written after cutover if reverting to the old table becomes necessary.

`orders_before_release` still lives on the same MySQL instance and storage failure domain. It does not replace an independent backup.

## 4. Understanding the Atomicity of RENAME TABLE

The word "atomic" is used for several distinct guarantees. Separate three concepts clearly.

### 4.1. Statement-Level Rename Atomicity

In a multi-pair `RENAME TABLE` statement, MySQL processes the rename sequence in order. If one step fails, the entire statement fails without leaving partial renames applied.

With proper table locking, the rename executes atomically: other sessions cannot access the tables while the rename is underway. Clients observe either the pre-statement state or the post-statement state, never intermediate steps within that same statement.

This helps when renaming groups of tables or executing old/new cutovers. It does not mean all running queries automatically succeed; queries may wait on metadata locks or fail if the application queries the old name after the rename finishes.

### 4.2. Atomic DDL on Server Crash

MySQL 8.x supports atomic DDL for supported operations and storage engines. For `RENAME TABLE`, atomicity across an unexpected server crash is guaranteed only when every table in the statement uses a storage engine supporting atomic DDL. In MySQL 8.4, InnoDB is the storage engine supporting atomic DDL for tables.

For example, a statement renaming multiple InnoDB tables recovers as either fully applied or fully rolled back during crash recovery. If the statement includes a table using an engine without atomic DDL support, do not assume the same crash-safe guarantee across the whole operation.

Check the engines of all involved tables before relying on atomic DDL:

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME IN (
      'orders',
      'orders_candidate',
      'orders_before_release'
  );
~~~

Atomic DDL is a property of DDL operations and storage engines, not a guarantee that every engine, MySQL version, and storage layer behaves identically. Verify your exact server version.

### 4.3. Atomic DDL Is Not Transactional DDL

`RENAME TABLE` triggers an implicit commit. If a session has an open transaction, MySQL commits that transaction before executing the DDL statement. You cannot wrap `RENAME TABLE` inside a transaction and use `ROLLBACK` to restore the old name.

Example:

~~~sql
START TRANSACTION;

UPDATE shop.orders
SET order_status = 'review'
WHERE order_id = 1001;

RENAME TABLE shop.orders TO shop.orders_old;

ROLLBACK;
~~~

Never expect `ROLLBACK` to undo a table rename. The preceding transaction was also implicitly committed before `RENAME TABLE` ran.

To revert the name, you must execute a new `RENAME TABLE` statement after verifying state:

~~~sql
RENAME TABLE shop.orders_old TO shop.orders;
~~~

The reverse rename only restores the name. It does not undo data written to the table, application changes, or business effects occurring after the initial cutover.

## 5. Metadata Locks and Wait Times

MySQL uses metadata locking (MDL) to protect table definitions and database objects when multiple sessions run concurrently.

A transaction that has accessed a table holds a metadata lock until that transaction ends. Consequently, `RENAME TABLE` may wait for another transaction to `COMMIT` or `ROLLBACK` before acquiring the required lock.

Example Session A:

~~~sql
START TRANSACTION;

SELECT *
FROM shop.orders
WHERE order_id = 1001;

-- Transaction remains open, not yet committed or rolled back.
~~~

Meanwhile, Session B runs:

~~~sql
RENAME TABLE shop.orders TO shop.orders_old;
~~~

Session B can block waiting on the metadata lock held by Session A. Even a read-only transaction holds MDL; not only `UPDATE` transactions block DDL.

### 5.1. Peak-Hour Impact

If a rename waits for a long time:

- Migration or release pipelines can hang.
- New queries needing metadata locks queue up behind the waiting DDL request.
- Connection pools can exhaust threads due to queued requests.
- Application latency can spike even though the rename itself is only a metadata change.

Thus, a tiny rename command can still cause downtime if long-running transactions are open beforehand.

Before deploying:

- Inspect open transactions and their ages.
- Clear hung transactions or sessions holding forgotten open transactions.
- Schedule during low-traffic windows when business requirements call for it.
- Set appropriate lock wait timeouts and prepare a way to cancel the migration if locks cannot be acquired.
- Never run multiple dependent rename migrations concurrently.

### 5.2. Inspecting Metadata Locks

MySQL 8.x lets you observe metadata locks via Performance Schema:

~~~sql
SELECT
    ml.OBJECT_SCHEMA,
    ml.OBJECT_NAME,
    ml.LOCK_TYPE,
    ml.LOCK_DURATION,
    ml.LOCK_STATUS,
    th.PROCESSLIST_ID,
    th.PROCESSLIST_USER,
    th.PROCESSLIST_TIME,
    th.PROCESSLIST_STATE,
    th.PROCESSLIST_INFO
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS th
    ON th.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.OBJECT_TYPE = 'TABLE'
  AND ml.OBJECT_SCHEMA = 'shop'
ORDER BY
    ml.LOCK_STATUS,
    ml.OBJECT_NAME;
~~~

Focus on `LOCK_STATUS = 'PENDING'` to spot waiting requests. `GRANTED` rows show locks currently held. Appropriate Performance Schema privileges are required.

You can also inspect active sessions:

~~~sql
SHOW FULL PROCESSLIST;
~~~

Never rush to `KILL` a session merely because it appears in the list. First identify which application owns the transaction, whether it is processing critical business work, and the impact of aborting it.

### 5.3. Metadata Lock Acquisition Order

In a multi-pair `RENAME TABLE`, MySQL acquires metadata locks in table-name order. When multiple sessions run concurrent operations, lock acquisition order can affect wait behavior or operation ordering.

That is why multiple deployments must never independently rename the same group of tables. Coordinate migrations through a single pipeline and control transactions holding locks on related tables.

## 6. Foreign Keys and Constraint Names After Renaming a Table

Foreign keys are the most critical dependency to check when renaming tables.

InnoDB tracks referential relationships in metadata. When a table is renamed, foreign keys referencing that table update to reflect the new name, unless a constraint name conflict occurs. If a conflict arises, `RENAME TABLE` fails.

Example `order_item` table referencing `sales_order`:

~~~sql
CREATE TABLE shop.sales_order (
    order_id BIGINT UNSIGNED NOT NULL,
    order_no VARCHAR(40) NOT NULL,
    PRIMARY KEY (order_id),
    UNIQUE KEY uq_sales_order_no (order_no)
) ENGINE = InnoDB;

CREATE TABLE shop.order_item (
    order_item_id BIGINT UNSIGNED NOT NULL,
    order_id BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (order_item_id),
    KEY idx_order_item_order (order_id),
    CONSTRAINT fk_order_item_sales_order
        FOREIGN KEY (order_id)
        REFERENCES shop.sales_order (order_id)
) ENGINE = InnoDB;
~~~

Rename the parent table:

~~~sql
RENAME TABLE shop.sales_order TO shop.customer_order;
~~~

After renaming, inspect the child table definition:

~~~sql
SHOW CREATE TABLE shop.order_item;
~~~

You can query metadata:

~~~sql
SELECT
    CONSTRAINT_SCHEMA,
    TABLE_NAME,
    CONSTRAINT_NAME,
    REFERENCED_TABLE_SCHEMA,
    REFERENCED_TABLE_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE CONSTRAINT_SCHEMA = 'shop'
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, CONSTRAINT_NAME;
~~~

### 6.1. Auto-Generated Foreign Key Names

MySQL adjusts certain constraint names according to internal rules:

- Internally generated foreign key names or user-named constraints prefixed with the old table name + `'_ibfk_'` may be renamed to reflect the new table name.
- Foreign keys pointing to the renamed table are also updated.
- If a new constraint name collides with an existing constraint, the rename fails. Resolving it requires dropping and recreating the foreign key with an explicit name.

For constraints named under custom conventions, do not guess whether their names will change automatically. Inspect `SHOW CREATE TABLE` before and after migration.

### 6.2. CHECK Constraints

`CHECK` constraints named with the old table name + `'_chk_'` prefix are also adjusted by MySQL to match the new table name when recognized as internally generated or following that convention.

Inspect with:

~~~sql
SHOW CREATE TABLE shop.customer_order;
~~~

Do not write scripts that depend on auto-generated constraint names. Assign meaningful explicit constraint names, keep definitions in migrations, and verify metadata after renaming.

### 6.3. Special Warning When Swapping Tables

This is crucial during blue/green table swaps.

Suppose `order_item` has a foreign key pointing to `orders`. When you run:

~~~sql
RENAME TABLE
    shop.orders TO shop.orders_old,
    shop.orders_candidate TO shop.orders;
~~~

The foreign key pointing to the old `orders` table object updates to reference `orders_old`. MySQL tracks the underlying referenced object and updates metadata when it is renamed. It does not infer that your application wanted to repoint relationships to the brand-new `orders_candidate` object.

Consequently, after the swap, `order_item` may still reference the old table now named `orders_old`. If child rows must reference the new table, design a separate foreign key migration plan, typically including:

1. Identifying all child tables referencing `orders`.
2. Ensuring compatible keys and data in the new table.
3. Planning `DROP`/`ADD` of foreign keys in the proper order.
4. Checking for orphan rows before recreating constraints.
5. Executing cutover and verifying metadata afterward.

Never disable `foreign_key_checks` just to push a swap through. Re-enabling `foreign_key_checks` does not scan or validate data written while checks were off.

## 7. Views, Triggers, and Stored Programs

### 7.1. Views

Views store query definitions referencing tables or other views. If a table is renamed or altered in a way that breaks objects referenced by a view, the view can become invalid.

Inspect the definition:

~~~sql
SHOW CREATE VIEW shop.v_order_summary;
~~~

MySQL provides `CHECK TABLE` to verify whether a view is invalid:

~~~sql
CHECK TABLE shop.v_order_summary;
~~~

Locate views in metadata:

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    VIEW_DEFINITION
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = 'shop';
~~~

Do not rely solely on `RENAME TABLE` succeeding. Re-run queries reading views, including nested views and views used by applications.

If a view definition needs updating, store `CREATE OR REPLACE VIEW` in migrations so deployments stay repeatable and reviewable.

### 7.2. Triggers

Triggers attach to a specific table. When renaming a table within the same schema, verify the trigger remains attached to the right table and its trigger body still references valid tables.

View triggers:

~~~sql
SHOW TRIGGERS FROM shop;
~~~

Or query:

~~~sql
SELECT
    TRIGGER_SCHEMA,
    TRIGGER_NAME,
    EVENT_OBJECT_SCHEMA,
    EVENT_OBJECT_TABLE,
    ACTION_TIMING,
    EVENT_MANIPULATION,
    ACTION_STATEMENT
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE EVENT_OBJECT_SCHEMA = 'shop'
ORDER BY EVENT_OBJECT_TABLE, TRIGGER_NAME;
~~~

Note: moving a table that has triggers to another database with `RENAME TABLE` is rejected by MySQL with error `ER_TRG_IN_WRONG_SCHEMA`. Handle triggers and schema moves separately.

Trigger names belong to the schema namespace. When building a candidate table with triggers, ensure trigger names do not collide with existing triggers. During a table swap, inspect triggers on both the old and new tables.

### 7.3. Stored Procedures, Functions, and Events

Stored programs or events may contain SQL referencing table names. Never assume MySQL rewrites SQL strings inside procedure, function, or event bodies when renaming a table.

Inspect definitions:

~~~sql
SHOW CREATE PROCEDURE shop.recalculate_order;
SHOW CREATE FUNCTION shop.order_total;
SHOW CREATE EVENT shop.refresh_order_summary;
~~~

You can inspect metadata:

~~~sql
SELECT
    ROUTINE_SCHEMA,
    ROUTINE_NAME,
    ROUTINE_TYPE
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA = 'shop';

SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    STATUS,
    EVENT_DEFINITION
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'shop';
~~~

Viewing full definitions may require appropriate privileges. Search migration sources, repositories, and deployment configs for dynamic SQL, string-concatenated table names, or names stored in config files.

## 8. Access Privileges Do Not Automatically Follow the New Name

`RENAME TABLE` requires privileges:

- `ALTER` and `DROP` on the original table.
- `CREATE` and `INSERT` on the target table name.

When moving across databases, corresponding privileges are needed on both databases.

An easily missed detail: privileges granted directly on an old table or view name do not automatically transfer to the new name. Re-grant privileges on the new name.

Example checking current grants:

~~~sql
SHOW GRANTS FOR 'app_reader'@'10.%';
~~~

Re-grant read privileges on the new table:

~~~sql
GRANT SELECT
ON shop.customer_order
TO 'app_reader'@'10.%';
~~~

Example granting privileges to an application account:

~~~sql
GRANT SELECT, INSERT, UPDATE, DELETE
ON shop.orders
TO 'shop_runtime'@'10.%';
~~~

The accounts, hosts, and privileges above are illustrative. Retrieve the actual accounts from your deployment environment.

If privileges are granted at the database level rather than table level, the scope may still cover the new name. Even so, verify with `SHOW GRANTS` and test connecting as the actual runtime account. Never test solely with an admin account, which can see tables even when the application lacks privileges.

## 9. Moving a Table to Another Database

`RENAME TABLE` can move a table between two databases:

~~~sql
RENAME TABLE
    shop.orders TO shop_archive.orders;
~~~

The target database must exist and the account needs matching privileges.

Limitations to keep in mind:

- If the table has triggers, moving it to another database is rejected with `ER_TRG_IN_WRONG_SCHEMA`.
- Views can be renamed within the same database, but cannot be moved to another database with `RENAME TABLE`.
- If the target database resides on a different filesystem, behavior depends on platform and OS filesystem operations.
- Privileges granted specifically to the old table name do not follow the new name.
- Check foreign keys, views, routines, events, and application code referencing the old schema.

Do not treat moving every table from database A to database B via multiple `RENAME TABLE` statements as a true database rename. The old database still exists, merely empty of the moved tables. Other objects and related configurations still require separate handling.

## 10. Table Name Case Sensitivity

How MySQL compares database and table names depends on the operating system and the `lower_case_table_names` variable.

Check:

~~~sql
SELECT
    @@lower_case_table_names AS lower_case_table_names,
    @@lower_case_file_system AS lower_case_file_system;
~~~

Common values:

| `lower_case_table_names` Value | Behavior |
|---:|---|
| 0 | Stores names using declared casing and compares case-sensitively |
| 1 | Stores names in lowercase and compares case-insensitively |
| 2 | Stores using declared casing but compares in lowercase; only suited to case-insensitive filesystems |

Defaults are typically 1 on Windows, 0 on Linux/Unix, and 2 on macOS, though always check the actual server setting. This variable is set at MySQL server initialization and cannot be changed arbitrarily afterward.

To avoid cross-platform bugs between Windows and Linux, consistently use lowercase table names. For example, always write `orders` and `order_item` instead of mixing `Orders` and `orders`.

## 11. Safe Rename Deployment Workflow

A table rename migration should be managed like an internal database API change. Table names are referenced by applications and database objects; renaming can break compatibility if older code is still running.

### Step 1: Inventory Dependencies

Record:

- `SHOW CREATE TABLE` of source and target tables.
- Storage engine of every table in the statement.
- Incoming and outgoing foreign keys.
- Related views, triggers, procedures, functions, and events.
- Table-level grants.
- Every repository, service, job, dashboard, ETL, and script referencing the table name.
- Long-running transactions, connection pools, and active prepared statements.

Query to find foreign keys referencing the table:

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    CONSTRAINT_NAME,
    COLUMN_NAME,
    REFERENCED_TABLE_SCHEMA,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE REFERENCED_TABLE_SCHEMA = 'shop'
  AND REFERENCED_TABLE_NAME = 'orders';
~~~

Query to find triggers on the table:

~~~sql
SELECT
    TRIGGER_NAME,
    EVENT_OBJECT_TABLE,
    ACTION_STATEMENT
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE EVENT_OBJECT_SCHEMA = 'shop'
  AND EVENT_OBJECT_TABLE = 'orders';
~~~

### Step 2: Prepare Compatible Application Releases

If multiple application versions run concurrently, deploy code capable of handling the transition. Common strategies:

- Release an application version able to read both new and old names during migration.
- Use a centralized repository/configuration layer for table names.
- Update views or a compatibility layer if appropriate for the architecture.
- Coordinate workers, schedulers, batch jobs, and consumers before cutover.

Never rename a table while an active application version still queries the old name without a compatibility layer.

### Step 3: Check Metadata Locks and Operational State

Identify transactions holding locks. Wait for or resolve those transactions per operational procedures.

Confirm:

- Backups matching the risk level are in place.
- Replicas and replication filters have been checked.
- No concurrent migration is modifying the same table group.
- Maximum wait timeout and on-call owner are defined.
- Post-rename verification queries are ready.

### Step 4: Execute a Single RENAME TABLE Statement

Example:

~~~sql
RENAME TABLE
    shop.orders TO shop.orders_legacy,
    shop.orders_next TO shop.orders;
~~~

Do not split into two independent statements if your goal is avoiding a gap where `orders` does not exist. A multi-pair statement performs the renames together in one operation.

### Step 5: Verify Immediately After Rename

Verify tables:

~~~sql
SHOW TABLES FROM shop LIKE 'orders';
SHOW TABLES FROM shop LIKE 'orders_legacy';

SHOW CREATE TABLE shop.orders;
SHOW INDEX FROM shop.orders;
~~~

Verify row counts and key metrics:

~~~sql
SELECT COUNT(*) AS row_count
FROM shop.orders;

SELECT order_status, COUNT(*) AS row_count
FROM shop.orders
GROUP BY order_status;
~~~

Verify foreign keys:

~~~sql
SELECT
    TABLE_NAME,
    CONSTRAINT_NAME,
    REFERENCED_TABLE_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE CONSTRAINT_SCHEMA = 'shop'
  AND REFERENCED_TABLE_NAME IS NOT NULL;
~~~

Verify views:

~~~sql
CHECK TABLE shop.v_order_summary;
~~~

Verify permissions using the actual application account, not just a DBA account. Run smoke tests on critical read/write flows and monitor application errors, slow queries, replication lag, and MySQL logs.

### Step 6: Finalize Dependencies

Once the table has its new name:

- Update or recreate views.
- Update stored procedures, functions, and events.
- Verify triggers and trigger bodies.
- Re-create table-level grants.
- Deploy code using only the new name.
- Update downstream migrations, operational docs, and dashboards.
- Retain the old table for the planned rollback window before dropping it upon confirmation.

Do not `DROP` the old table immediately after cutover. Wait until you confirm data, relationships, and applications are operating cleanly.

## 12. Blue/Green Table Swaps and Rollback Limits

A blue/green table swap prepares a new table in advance, then renames it to assume the production table name. This helps minimize cutover downtime after a long data-preparation phase.

High-level workflow:

~~~mermaid
flowchart TD
    A[Create orders_candidate] --> B[Copy and sync data]
    B --> C[Verify structure, indexes, constraints, and data]
    C --> D[Check FKs, views, triggers, and privileges]
    D --> E[Pause or coordinate writes during cutover]
    E --> F[Run RENAME TABLE in one statement]
    F --> G[Smoke test and verify relationships]
    G --> H{Checks pass?}
    H -->|Yes| I[Monitor then end old table retention window]
    H -->|No| J[Evaluate rollback or roll forward]
~~~

### 12.1. The Candidate Table Must Be Ready Before Cutover

The candidate table must have:

- An application-compatible schema.
- Required indexes and constraints.
- Copied and synchronized data.
- Appropriate triggers.
- Planned foreign key updates.
- Privileges ready to be granted to the production name after swap.

If writes still land on the old table during copying, you need a change synchronization mechanism: pausing writes, controlled dual-writes, change data capture, or another tested strategy. Copying once and renaming later can lose updates made after the copy started.

### 12.2. Rollback Is Not Just Renaming in Reverse

Suppose you executed:

~~~sql
RENAME TABLE
    shop.orders TO shop.orders_old,
    shop.orders_candidate TO shop.orders;
~~~

Then the application continues writing to the new `shop.orders`. If you immediately rename back:

~~~sql
RENAME TABLE
    shop.orders TO shop.orders_failed,
    shop.orders_old TO shop.orders;
~~~

New records written to `orders` after cutover now sit inside `orders_failed`. They do not automatically appear in `orders_old`.

Therefore, rolling back via rename is only safe when you have planned how to preserve or replay post-cutover writes. You may need to:

- Pause writes before rolling back.
- Reconcile and migrate new changes back into the old table.
- Run a compensating migration or roll forward.
- Use change logs/CDC to replay necessary transactions.

Once new data has been written and cannot be safely reversed, rolling forward is often better than mechanically renaming back.

### 12.3. Do Not Use the Old Table as Your Only Backup

`orders_old` still resides on the same instance, disk, or storage cluster. If the instance or storage suffers a failure, both tables can be affected simultaneously.

For risky changes, maintain an independent backup and verify restore capability. Backups must meet RPO/RTO requirements and be restore-tested per operational procedures.

## 13. Common Errors and Troubleshooting

| Scenario | Common Cause | How to Inspect |
|---|---|---|
| Table already exists | Target name is already taken | `SHOW TABLES`, check target object |
| Table doesn't exist | Wrong schema, wrong name, or wrong letter case | `SHOW TABLES`, check `@@lower_case_table_names` |
| Access denied | Missing `ALTER`/`DROP` on source or `CREATE`/`INSERT` on target | `SHOW GRANTS` |
| Lock wait / metadata lock timeout | Another transaction holds MDL | `performance_schema.metadata_locks`, `SHOW FULL PROCESSLIST` |
| Trigger in wrong schema | Moving a table with triggers to another database | `INFORMATION_SCHEMA.TRIGGERS` |
| Foreign key constraint name conflict | Post-rename FK name collides | `SHOW CREATE TABLE` on related tables |
| View stops working | View references old table name or invalidated object | `CHECK TABLE`, `SHOW CREATE VIEW` |
| Application reports table not found | Code, worker, or job still uses old name | Search SQL in repositories and logs |
| Application loses permissions | Table-level grants not re-applied to new name | `SHOW GRANTS` and test with runtime account |
| Replica errors after deploy | Inconsistent schema, replication filters, or migrations | `SHOW REPLICA STATUS`, replica logs |

Do not fix errors by impulsively dropping objects or disabling constraints. Identify which objects applications actively use and which dependencies will be impacted.

## 14. Pre- and Post-Rename Checklist

### Before Running

- [ ] Confirmed exact server, database, and source table.
- [ ] Confirmed target and intermediate names are unused.
- [ ] Verified storage engine of every table in the statement.
- [ ] Checked active transactions and metadata locks.
- [ ] Inventoried incoming and outgoing foreign keys.
- [ ] Checked views, triggers, routines, functions, and events.
- [ ] Checked table-level grants.
- [ ] Verified applications and workers are compatible with the new name.
- [ ] Prepared data sync and rollback plan.
- [ ] Verified backups commensurate with risk.

### After Running

- [ ] Old and new names match expected states.
- [ ] `SHOW CREATE TABLE` and indexes are correct.
- [ ] Foreign keys reference the intended objects.
- [ ] `CHECK` constraints remain intact.
- [ ] Views and triggers work properly.
- [ ] Runtime privileges are verified.
- [ ] Read/write smoke tests pass.
- [ ] Replicas stay caught up with zero replication errors.
- [ ] Dashboards, logs, jobs, and scripts use the new name.
- [ ] Old table is dropped only after the rollback retention window expires.

## 15. Hands-on Exercises

### Exercise 1: Renaming a Single Table

Create a `customer_old` table in a practice database. Insert a few rows, then rename it to `customer` using `RENAME TABLE`. Confirm data, indexes, and `AUTO_INCREMENT` remain intact.

### Exercise 2: Renaming Multiple Tables

Create two tables `orders_old` and `order_items_old`. Use a single `RENAME TABLE` statement to rename both. Then induce a target-name conflict in your lab environment and observe that the statement fails without leaving a partial rename.

### Exercise 3: Swapping Tables

Create `orders_live` and `orders_candidate` with distinct datasets. Use an intermediate name to swap them. Verify which name points to which data after the statement.

### Exercise 4: Observing Metadata Locks

Open a transaction in Session A and `SELECT` from a table without ending the transaction. From Session B, attempt `RENAME TABLE`. Observe the wait state in the processlist and Performance Schema. End Transaction A and watch the rename proceed.

### Exercise 5: Checking Foreign Keys

Create a parent and child table with an FK. Rename the parent table, then inspect `SHOW CREATE TABLE` on the child table and `INFORMATION_SCHEMA.KEY_COLUMN_USAGE`. Note the referenced table name after the rename.

### Exercise 6: Checking Views and Privileges

Create a view over a test table and grant direct `SELECT` to an account on that table. Rename the table, run `CHECK TABLE` on the view, then check the account's privileges and re-grant permissions on the new name as needed.

### Exercise 7: Planning a Blue/Green Swap

Write a plan to replace `orders` with `orders_candidate`. List every FK, view, trigger, table-level grant, and application consumer. Define how to sync data during copying and how to preserve post-cutover transactions if a rollback is needed.

## Conclusion

`RENAME TABLE` is a powerful tool for renaming one or more tables in a single operation. Under the right conditions, it avoids intermediate missing-table states and enables blue/green table swaps. However, atomic renames do not replace transaction rollbacks, backups, or coordinated application deployments.

Before renaming, audit metadata locks, storage engines, foreign keys, views, triggers, stored programs, privileges, and every consumer of the table name. Afterward, verify relationships and permissions using metadata and the actual runtime application account. A cutover is only complete when both the database and every component using it operate cleanly under the new name.

## References

- MySQL 8.4 Reference Manual — RENAME TABLE Statement: https://dev.mysql.com/doc/refman/8.4/en/rename-table.html
- MySQL 8.4 Reference Manual — Atomic Data Definition Statement Support: https://dev.mysql.com/doc/refman/8.4/en/atomic-ddl.html
- MySQL 8.4 Reference Manual — Statements That Cause an Implicit Commit: https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html
- MySQL 8.4 Reference Manual — Metadata Locking: https://dev.mysql.com/doc/refman/8.4/en/metadata-locking.html
- MySQL 8.4 Reference Manual — MySQL 8.4 FAQ: Views: https://dev.mysql.com/doc/refman/8.4/en/faqs-views.html
- MySQL 8.4 Reference Manual — Identifier Case Sensitivity: https://dev.mysql.com/doc/refman/8.4/en/identifier-case-sensitivity.html
