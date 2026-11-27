# Distinguishing DELETE, TRUNCATE, DROP, and Transaction Impacts

When removing data from MySQL, three commands are commonly mentioned: `DELETE`, `TRUNCATE TABLE`, and `DROP TABLE`. All three can make data inaccessible, yet their scope of impact and transactional behavior are fundamentally different. Choosing the wrong command can wipe out a table's structure, bypass triggers, reset the `AUTO_INCREMENT` counter, or unintentionally commit an active transaction.

In the **DATABASE_MYSQL** module, you need to understand these commands from both perspectives: data manipulation and structural operations. This lesson focuses on MySQL with InnoDB, explaining rollback capability, implicit commits, foreign keys, triggers, required privileges, and how to pick the right command.

## 1. Quick Comparison of the Three Commands

| Criterion | `DELETE` | `TRUNCATE TABLE` | `DROP TABLE` |
|---|---|---|---|
| Command group | DML | DDL | DDL |
| Goal | Delete specific or all rows | Remove all rows, keeping the empty table | Completely remove the table and its definition |
| Supports `WHERE`? | Yes | No | No |
| Keeps table structure, indexes, and constraints? | Yes | Yes | No |
| Can roll back with InnoDB? | Yes, if not yet committed | No | No |
| Triggers implicit commit? | No | Yes | Yes |
| Fires `DELETE` triggers? | Yes, for each deleted row | No | Does not fire row-level `DELETE` triggers |
| `AUTO_INCREMENT` impact | Does not reset counter merely by deleting all rows | Resets to the table's starting value | Table and counter are dropped together |
| Primary privilege required | `DELETE` | `DROP` | `DROP` |
| When to use | Conditional deletion or when transactions are needed | Intentionally emptying an entire table | Removing an obsolete table |

Key takeaway: `DELETE` operates on rows; `TRUNCATE` empties a table via a DDL operation; `DROP` removes the table object itself.

## 2. `DELETE` — Deleting Rows in a Table

`DELETE` removes rows matching a `WHERE` condition. The table, columns, indexes, and constraints remain intact after the statement completes.

```sql
-- Delete a specific order
DELETE FROM orders
WHERE order_id = 105;

-- Delete orders cancelled before a cutoff date
DELETE FROM orders
WHERE status = 'CANCELLED'
  AND created_at < '2025-01-01';
```

If `WHERE` is omitted, MySQL deletes every row in the table:

```sql
DELETE FROM orders;
```

The command above preserves the `orders` table and its definitions. However, it can delete a huge volume of data, take a long time, generate heavy undo/redo logs, and impact other transactions. Verify your filter with `SELECT` before running a delete on live data.

### DELETE Can Be Rolled Back with InnoDB

For InnoDB tables, `DELETE` is transactional. As long as the transaction has not committed, it can be undone:

```sql
START TRANSACTION;

DELETE FROM orders
WHERE order_id = 105;

-- Inspect within the current transaction
SELECT *
FROM orders
WHERE order_id = 105;

ROLLBACK;

-- Row is restored after rollback
SELECT *
FROM orders
WHERE order_id = 105;
```

If you issue `COMMIT` instead of `ROLLBACK`, the deletion is persisted. Rollback capability depends on the storage engine: with non-transactional engines like MyISAM, `ROLLBACK` does not restore deleted rows.

### DELETE Fires Triggers and Foreign Keys

`BEFORE DELETE` and `AFTER DELETE` triggers fire for deleted rows. If the table participates in foreign keys, `ON DELETE` actions execute according to the relationship definition:

- `RESTRICT`/`NO ACTION`: rejects deleting the parent row if referencing child rows exist.
- `CASCADE`: deletes related child rows.
- `SET NULL`: sets child foreign key columns to `NULL`, provided those columns allow `NULL`.

For instance, if `orders.customer_id` references `customers.customer_id` with `ON DELETE RESTRICT`, deleting a customer with orders is rejected. If the foreign key uses `ON DELETE CASCADE`, deleting a customer deletes their orders as well. Inspect all relationships before executing.

### DELETE Does Not Automatically Reset AUTO_INCREMENT

Deleting all rows with `DELETE` does not reset InnoDB's `AUTO_INCREMENT` counter:

```sql
DELETE FROM import_queue;
```

If the table previously allocated IDs up to 500, newly inserted rows continue receiving IDs above 500. This is usually desirable so previously issued IDs are not reused simply because old rows were deleted.

MySQL also supports `DELETE` combined with `ORDER BY` and `LIMIT` in single-table syntax, useful for batched deletions:

```sql
DELETE FROM event_logs
WHERE created_at < '2024-01-01'
ORDER BY created_at
LIMIT 1000;
```

You can loop in batches to reduce lock hold times and undo log size per transaction. Ensure stable filter criteria, an appropriate index, and iteration controls to avoid deleting beyond the intended scope.

## 3. `TRUNCATE TABLE` — Emptying an Entire Table

`TRUNCATE TABLE` removes all rows while preserving the table definition:

```sql
TRUNCATE TABLE import_queue;
```

After this command, the `import_queue` table still exists with its columns, indexes, constraints, and triggers. All row data is gone. `TRUNCATE` does not accept `WHERE`, so it cannot delete partial data.

### Why Is TRUNCATE Usually Faster Than a Full-Table DELETE?

In InnoDB, `TRUNCATE TABLE` executes as a DDL operation that resets the table—essentially dropping and recreating the tablespace/table under MySQL's internal mechanism. It avoids row-by-row deletion like `DELETE`, making it much more efficient for emptying large tables completely.

Actual performance still depends on metadata locks, table size, storage engine, filesystem, and concurrent activity. `TRUNCATE` does not guarantee instant completion or zero impact on applications using the table.

### TRUNCATE Resets AUTO_INCREMENT

For tables with `AUTO_INCREMENT`, `TRUNCATE TABLE` resets the counter to the table's starting value:

```sql
TRUNCATE TABLE import_queue;

INSERT INTO import_queue (payload)
VALUES ('next message');
```

New IDs restart from the table's initial configuration. If you need to preserve the sequence of previously issued IDs, do not use `TRUNCATE` solely to clear data.

### TRUNCATE Does Not Fire DELETE Triggers

`TRUNCATE TABLE` does not delete rows via individual `DELETE` operations, so `BEFORE DELETE`/`AFTER DELETE` triggers do not fire. If a system relies on triggers to write audit logs, update summary tables, or sync data, `TRUNCATE` bypasses those side effects.

For example, if `orders` has a trigger logging deletions to `order_audit`, `DELETE FROM orders` fires the trigger for each row; `TRUNCATE TABLE orders` creates no audit records.

### TRUNCATE and Foreign Keys

In MySQL, you cannot `TRUNCATE` an InnoDB table currently referenced by another table via a foreign key. For example, if `orders.customer_id` references `customers.customer_id`, `TRUNCATE TABLE customers` is rejected while that relationship exists, even if the child table currently has zero referencing rows. Handle relationships according to design or use an appropriate deletion approach in test schemas.

Do not disable `foreign_key_checks` just to force a truncate. Disabling checks is no substitute for controlled data deletion; re-enabling it does not verify data written while checks were disabled.

## 4. `DROP TABLE` — Dropping the Table Entirely

`DROP TABLE` removes the table from the database:

```sql
DROP TABLE import_queue;
```

After this command, the table no longer exists. Column definitions, data, indexes, attached triggers, and table constraints are all removed together. Subsequent `SELECT`, `INSERT`, `UPDATE`, or `DELETE` statements referencing the table fail because the table is gone.

Inspect before dropping:

```sql
SHOW CREATE TABLE import_queue;
SELECT COUNT(*) FROM import_queue;
```

Only run `DROP TABLE` once you confirm the table is genuinely no longer needed. To drop a table only if it exists, use:

```sql
DROP TABLE IF EXISTS import_queue;
```

`IF EXISTS` suppresses the error when the table is missing; it does not make the operation safe or rollbackable.

### DROP TABLE and Foreign Keys

If a table is referenced by another table via a foreign key, MySQL normally rejects `DROP TABLE` while foreign key checks are enabled. Dropping the child table removes constraints owned by that child table along with it. If you need to drop a group of related tables, order drops by dependency and back up first; do not casually disable `foreign_key_checks` to bypass constraints.

`DROP TABLE` differs from `DELETE` because it destroys the schema as well. To use the table again after `DROP`, you must recreate it with DDL or restore from a backup/migration. Data cannot be recovered with `ROLLBACK`.

## 5. Impact on Transactions and Implicit Commits

This is the most critical distinction when choosing a command:

| Command | Can Run Inside an InnoDB Transaction? | Impact on an Open Transaction |
|---|---|---|
| `DELETE` | Yes | Does not auto-commit; can `COMMIT` or `ROLLBACK` with the transaction |
| `TRUNCATE TABLE` | Not in a rollbackable DML sense | Triggers an implicit commit; truncate cannot be undone with `ROLLBACK` |
| `DROP TABLE` | Not in a rollbackable DML sense | Triggers an implicit commit; drop cannot be undone with `ROLLBACK` |

`TRUNCATE` and `DROP` are DDL. MySQL executes an implicit commit on any open transaction before running these commands; these DDL commands also finish in their own committed state. Consequently, a subsequent `ROLLBACK` cannot restore a truncated/dropped table or undo DML changes already committed by the implicit commit.

### Demonstrating Rollbackable DELETE

Run in a test schema with an InnoDB table:

```sql
START TRANSACTION;

DELETE FROM transaction_probe
WHERE id = 10;

ROLLBACK;
```

The row `id = 10` is restored provided the transaction was not committed and no implicit-commit operation intervened.

### Demonstrating TRUNCATE's Implicit Commit

Suppose there are two independent InnoDB test tables: `transaction_probe` and `truncate_probe`. Run:

```sql
START TRANSACTION;

INSERT INTO transaction_probe (id, note)
VALUES (9001, 'insert before truncate');

TRUNCATE TABLE truncate_probe;

ROLLBACK;
```

When `TRUNCATE TABLE` runs, MySQL implicitly commits the open transaction beforehand. Therefore, row `9001` in `transaction_probe` has already been committed and remains after `ROLLBACK`. Meanwhile `truncate_probe` is emptied and cannot be rolled back either.

`DROP TABLE` carries the exact same implicit commit risk:

```sql
START TRANSACTION;

UPDATE transaction_probe
SET note = 'updated before drop'
WHERE id = 9001;

DROP TABLE drop_probe;

ROLLBACK;
```

The `DROP TABLE` command commits the preceding `UPDATE`; `ROLLBACK` neither undoes the update nor restores `drop_probe`. Run this example only in a disposable test schema.

## 6. Atomic DDL Does Not Mean Rollbackable

MySQL 8.0 supports atomic DDL for many DDL operations on supporting storage engines, including InnoDB. Atomic DDL ensures a DDL operation either completes entirely or recovers cleanly if the server crashes mid-execution.

However, **atomic DDL does not make DDL a rollbackable part of a user transaction**. `TRUNCATE TABLE` and `DROP TABLE` still trigger an implicit commit and cannot be undone with `ROLLBACK` the way InnoDB `DELETE` can.

Distinguish clearly:

- *Crash atomicity*: MySQL protects the integrity of the DDL operation itself against server crashes.
- *Transactional rollback*: the application can request undoing uncommitted work via `ROLLBACK`.

These two concepts solve different problems. Do not rely on atomic DDL as a substitute for backups or data recovery plans.

## 7. Required Privileges

The commands require different privileges:

| Command | Primary Privilege |
|---|---|
| `DELETE FROM table ...` | `DELETE` on the table or matching scope |
| `TRUNCATE TABLE table` | `DROP` on the table |
| `DROP TABLE table` | `DROP` on the table |

An account with only `DELETE` can delete rows without being permitted to truncate or drop tables. This aligns with the principle of least privilege: routine application accounts generally need only DML privileges; DDL privileges belong to controlled migration or administrative accounts.

Check privileges:

```sql
SHOW GRANTS;
```

Do not grant broad `DROP` privileges to an application account simply because one job needs to clear a table. If a business workflow must delete data, use `DELETE` with proper conditions and privileges.

## 8. Which Command Should You Choose?

| Need | Appropriate Command | Reason |
|---|---|---|
| Delete a customer or subset of orders by condition | `DELETE ... WHERE ...` | Selective deletion; runs inside an InnoDB transaction |
| Delete data in batches to control load | `DELETE ... ORDER BY ... LIMIT ...` | Breaks work into chunks and monitors each batch |
| Empty an entire staging table without row-level delete triggers | `TRUNCATE TABLE` | Keeps structure, usually fast, resets AUTO_INCREMENT; accept implicit commit |
| Permanently remove an obsolete table | `DROP TABLE` | Removes both structure and data; requires DDL/migration to recreate |
| Need ability to undo while verifying results | `DELETE` in an InnoDB transaction | Allows inspecting before committing or running `ROLLBACK` |
| Need DELETE trigger auditing or ON DELETE referential actions | `DELETE` | Triggers and referential actions execute per row |

Before deleting large datasets, verify:

1. Exact server, database, and table.
2. Backups or recovery plans matching the data's criticality.
3. Any foreign keys, triggers, or other applications depending on the table.
4. Any open transaction that DDL would unexpectedly commit.
5. Whether the account's privileges match the intended operation.

## 9. Safe Workflow Before Destructive Operations

For conditional `DELETE`, run a `SELECT` with the exact same filter first to inspect which rows will be affected:

```sql
SELECT order_id, customer_id, status, created_at
FROM orders
WHERE status = 'CANCELLED'
  AND created_at < '2025-01-01'
ORDER BY created_at;
```

If the scope looks right, execute inside an InnoDB transaction:

```sql
START TRANSACTION;

DELETE FROM orders
WHERE status = 'CANCELLED'
  AND created_at < '2025-01-01';

SELECT ROW_COUNT() AS deleted_rows;

-- Inspect related tables and results before confirming.
COMMIT;
-- Or use ROLLBACK if the result is wrong.
```

`ROW_COUNT()` returns the number of rows affected by the most recent statement in the session. Running another statement changes this value; read it immediately after `DELETE`.

With `TRUNCATE` or `DROP`, there is no `ROLLBACK` step to rescue data. Confirm table name, schema, environment, backups, and dependencies beforehand. Even when clearing data in a test environment, verify the connected database:

```sql
SELECT DATABASE(), @@hostname, @@port;
```

This helps avoid accidentally running against production when multiple connection profiles are open.

## 10. End-to-End Example on an InnoDB Table

Create a test table:

```sql
CREATE TABLE cleanup_demo (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    note VARCHAR(100) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

INSERT INTO cleanup_demo (note)
VALUES ('keep'), ('remove'), ('remove');
```

Conditional delete and rollback:

```sql
START TRANSACTION;

DELETE FROM cleanup_demo
WHERE note = 'remove';

SELECT * FROM cleanup_demo;

ROLLBACK;

SELECT * FROM cleanup_demo;
```

Empty the table while keeping its structure:

```sql
TRUNCATE TABLE cleanup_demo;

SHOW CREATE TABLE cleanup_demo;
SELECT COUNT(*) FROM cleanup_demo;
```

Drop the table completely:

```sql
DROP TABLE cleanup_demo;

SHOW TABLES LIKE 'cleanup_demo';
```

After the final command, the table no longer exists in the schema. Run all examples in a lab database, never on operational tables holding data you need to keep.

## 11. Hands-on Exercises

1. Create an InnoDB table with an `AUTO_INCREMENT` key, insert a few rows, and record the allocated IDs.
2. Delete one row with `DELETE` inside a transaction and `ROLLBACK`; verify the row returns.
3. Delete all rows with `DELETE` and insert another row; observe how the `AUTO_INCREMENT` counter continues.
4. Repopulate test data and run `TRUNCATE TABLE`; confirm the structure remains, the table is empty, and the counter resets.
5. Add a `DELETE` trigger for audit logging and compare audit record counts between `DELETE` and `TRUNCATE`.
6. Open a transaction, modify one table, then run `TRUNCATE` on another lab table; after `ROLLBACK`, verify the pre-DDL change was implicitly committed.
7. Create a foreign key relationship between two tables and observe how `TRUNCATE` on the parent table is rejected while referenced by the child table.
8. Run `DROP TABLE` on a lab table and explain why it cannot be recovered via `ROLLBACK`.

You have completed this lesson when you can choose accurately between deleting rows, emptying a table, and dropping a table; explain their effects on transactions, triggers, foreign keys, and `AUTO_INCREMENT`; and verify environments and dependencies before destructive operations.
