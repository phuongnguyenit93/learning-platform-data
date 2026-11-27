# ALTER TABLE: Adding, Modifying, and Dropping Columns and Constraints

An application's schema evolves alongside business requirements. A table might need a new status column, a data type change, a default value, an added foreign key, or the removal of a legacy constraint. In MySQL, `ALTER TABLE` performs these structural modifications and can affect existing data, indexes, locks, table lock duration, and storage capacity.

Schema changes must therefore be treated as controlled migrations. Before running them, you must understand the current definition, existing data, dependent objects, and online DDL capabilities of your MySQL version. Afterward, verify the actual structure and data.

This article focuses on MySQL 8.x with InnoDB. Some `ALTER TABLE` algorithms and online DDL capabilities vary by version, storage engine, column type, and table structure; always consult documentation for your exact deployment version.

## 1. ALTER TABLE Modifies Table Structure

`ALTER TABLE` is a DDL statement used to add, modify, rename, or remove table components. One statement can contain one or more operations:

~~~sql
ALTER TABLE table_name
    alter_option,
    alter_option,
    ...;
~~~

Common operation categories:

| Category | Purpose | Example |
|---|---|---|
| Add column | Add a new attribute | ADD COLUMN |
| Modify column | Change type, NULL, DEFAULT, or attributes | MODIFY COLUMN |
| Rename column | Keep data while changing column name | RENAME COLUMN or CHANGE COLUMN |
| Drop column | Remove column definition and data | DROP COLUMN |
| Add constraint | Enforce data rules | ADD CONSTRAINT |
| Drop constraint | Remove a rule | DROP FOREIGN KEY, DROP CHECK, DROP PRIMARY KEY |
| Manage indexes | Add, drop, or rename indexes | ADD INDEX, DROP INDEX, RENAME INDEX |
| Change default | Change DEFAULT without modifying column type | ALTER COLUMN SET/DROP DEFAULT |

Before altering, inspect the current structure:

~~~sql
SHOW CREATE TABLE shop.customers\G
SHOW INDEX FROM shop.customers;
~~~

`SHOW CREATE TABLE` shows the DDL currently active on the server. `SHOW INDEX` inspects existing indexes and key part order. Together, these two commands are a great starting point to avoid duplicate additions or dropping the wrong object.

## 2. Adding Columns with ADD COLUMN

### 2.1. Adding a New Column

Basic syntax:

~~~sql
ALTER TABLE customers
ADD COLUMN phone_number VARCHAR(30);
~~~

The new column is appended at the end of the column list if no position is specified. On tables with existing data, existing rows receive `NULL` for the new column if it allows `NULL` and has no other default value.

You can specify full data type, NULL, DEFAULT, and comment:

~~~sql
ALTER TABLE customers
ADD COLUMN marketing_opt_in BOOLEAN NOT NULL DEFAULT FALSE
    COMMENT 'Customer consents to receive marketing communications';
~~~

In MySQL, `BOOLEAN` is an alias for `TINYINT(1)`. Common values are 0 and 1; if only those two values should be accepted, consider a `CHECK` constraint on versions that enforce it.

### 2.2. Choosing Column Position

You can place a column first or after another column:

~~~sql
ALTER TABLE customers
ADD COLUMN loyalty_code VARCHAR(40) AFTER email;

ALTER TABLE customers
ADD COLUMN external_ref VARCHAR(80) FIRST;
~~~

`FIRST` and `AFTER` primarily affect display order in metadata and `SELECT *` results. They do not replace listing columns explicitly in queries, nor do they automatically make queries faster. Applications should address columns by name instead of relying on physical order or `SELECT *` order.

### 2.3. Adding a NOT NULL Column to a Table with Existing Data

When adding a `NOT NULL` column, you must determine values for existing rows. Without an appropriate `DEFAULT`, the operation may fail or behave differently depending on SQL mode and DDL capabilities of your version.

An easier-to-control rollout starts by adding the column as nullable:

~~~sql
ALTER TABLE customers
ADD COLUMN preferred_language VARCHAR(10) NULL;
~~~

Then backfill data according to business rules:

~~~sql
UPDATE customers
SET preferred_language = 'vi'
WHERE preferred_language IS NULL;
~~~

Once verified that no `NULL`s remain, change the column to `NOT NULL`:

~~~sql
ALTER TABLE customers
MODIFY COLUMN preferred_language VARCHAR(10) NOT NULL;
~~~

On large tables, do not backfill everything in a single long transaction. Batch updates by primary key ranges while monitoring locks, undo/redo logs, replication lag, and system load.

### 2.4. DEFAULT Does Not Automatically Rewrite Legacy Data

`DEFAULT` is used when an `INSERT` omits a value for the column (or explicitly requests `DEFAULT`). Changing `DEFAULT` does not mean existing rows are updated to the new value.

Example:

~~~sql
ALTER TABLE customers
ADD COLUMN account_status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE';
~~~

Existing rows are handled according to DDL rules and MySQL version. In many cases, the default value is materialized on read without rewriting every row, though cost and `INSTANT` eligibility depend on version and table conditions. Never assume every column addition avoids rebuilding the table.

## 3. Changing Types and Attributes with MODIFY COLUMN

`MODIFY COLUMN` changes a column's definition while preserving its name:

~~~sql
ALTER TABLE customers
MODIFY COLUMN full_name VARCHAR(200) NOT NULL;
~~~

Crucial detail: `MODIFY COLUMN` requires re-declaring all attributes you want to keep—such as data type, `NULL`/`NOT NULL`, `DEFAULT`, `COMMENT`, charset, collation, and `AUTO_INCREMENT` if present. Do not assume omitted attributes are preserved automatically as expected.

For example, if the current column is:

~~~sql
phone_number VARCHAR(30) NULL DEFAULT NULL
~~~

and you want to make it mandatory, write explicitly:

~~~sql
ALTER TABLE customers
MODIFY COLUMN phone_number VARCHAR(30) NOT NULL;
~~~

This succeeds only if existing data satisfies the new definition. If `NULL`s remain, resolve them first.

### 3.1. Increasing or Decreasing String Length

Increasing `VARCHAR` length is generally less risky than shrinking it:

~~~sql
ALTER TABLE customers
MODIFY COLUMN full_name VARCHAR(200) NOT NULL;
~~~

Shrinking length:

~~~sql
ALTER TABLE customers
MODIFY COLUMN full_name VARCHAR(80) NOT NULL;
~~~

Before shrinking, check the longest existing data:

~~~sql
SELECT
    MAX(CHAR_LENGTH(full_name)) AS max_characters,
    MAX(OCTET_LENGTH(full_name)) AS max_bytes
FROM customers;
~~~

`CHAR_LENGTH` counts characters; `OCTET_LENGTH` counts bytes. With `utf8mb4`, byte count can exceed character count. Data exceeding the new length can cause DDL to fail in strict mode or be truncated with warnings in certain non-strict contexts. Never rely on MySQL truncating data as a migration strategy.

### 3.2. Changing Numeric Types

Example widening `INT` to `BIGINT`:

~~~sql
ALTER TABLE orders
MODIFY COLUMN order_number BIGINT UNSIGNED NOT NULL;
~~~

Before changing, verify:

- Do existing values fit within the target type's range?
- Is signed/unsigned compatible with foreign keys and related columns?
- Do indexes, generated columns, views, triggers, routines, or applications depend on the old type?
- Does the connector map the new data type properly?

Changing `BIGINT UNSIGNED` to signed `INT` can lose the ability to represent large values or negative numbers. When altering the type of a column referenced by a foreign key, carefully manage relationships and migration ordering.

### 3.3. Changing NULL and NOT NULL

Changing from nullable to `NOT NULL` requires zero remaining `NULL` rows:

~~~sql
SELECT COUNT(*) AS null_count
FROM customers
WHERE phone_number IS NULL;
~~~

If the count is greater than 0, decide how to handle each data group before altering. Never assign empty strings or 0 automatically if they do not mean the same thing as `NULL` in the business domain.

Changing from `NOT NULL` to `NULL`:

~~~sql
ALTER TABLE customers
MODIFY COLUMN phone_number VARCHAR(30) NULL;
~~~

This relaxes the data constraint, yet applications may need updates to handle `NULL` cases. Update validation and mappings in the application layer.

### 3.4. Changing DEFAULT Independently

If you only need to change the default value, use `ALTER COLUMN`:

~~~sql
ALTER TABLE customers
ALTER COLUMN account_status SET DEFAULT 'PENDING';

ALTER TABLE customers
ALTER COLUMN account_status DROP DEFAULT;
~~~

Changing `DEFAULT` does not update existing rows. If legacy data needs updating, run a separate `UPDATE` and evaluate transaction impact.

## 4. Renaming Columns with RENAME COLUMN or CHANGE COLUMN

### 4.1. RENAME COLUMN

MySQL 8.0 supports `RENAME COLUMN`:

~~~sql
ALTER TABLE customers
RENAME COLUMN phone_number TO mobile_number;
~~~

This syntax only renames the column without requiring you to re-declare the data type.

### 4.2. CHANGE COLUMN

`CHANGE COLUMN` can change both the name and the definition:

~~~sql
ALTER TABLE customers
CHANGE COLUMN phone_number mobile_number VARCHAR(30) NULL;
~~~

`CHANGE COLUMN` requires declaring the new name and full column definition. Include every attribute you want to keep. Omitting `DEFAULT`, `NULL`, `COMMENT`, or charset/collation can leave the post-migration definition different from what you intended.

### 4.3. Impact on Applications and Dependent Objects

Renaming a column can break:

- SQL in applications and reports.
- Views, triggers, stored procedures, or stored functions.
- ETL jobs, dashboards, and operational scripts.
- ORM mappings, native queries, and subsequent migrations.

MySQL may update certain dependent metadata in specific situations, but never assume all dynamic SQL, application code, or external tools are updated automatically. For live systems, adding a new column, syncing data, switching applications over, and dropping the old column is usually safer than a single-step direct rename.

## 5. Dropping Columns with DROP COLUMN

Syntax:

~~~sql
ALTER TABLE customers
DROP COLUMN legacy_code;
~~~

`DROP COLUMN` removes both the column definition and the data stored in that column. Once completed, you cannot recover the data merely by re-adding a column with the same name. Recovery requires backups, snapshots, or another data source.

Before dropping, check:

1. Does the application still read or write the column?
2. Do any indexes, unique keys, foreign keys, `CHECK` constraints, generated columns, or expressions depend on the column?
3. Do views, triggers, routines, reports, or ETL jobs use the column?
4. Must the data be retained for auditing or backward compatibility?
5. Have backups and recovery plans been verified?

If the column participates in a composite index, dropping it may require handling that index. If the column participates in a foreign key, resolve the constraint beforehand or within an appropriate DDL plan.

Do not drop a column immediately after releasing a new application version. Wait until old instances, background jobs, and reports have stopped using the column before executing the contract migration.

## 6. Adding and Dropping Constraints

Constraints enforce data rules at the database level, even when multiple applications or processes write to the table concurrently. MySQL with InnoDB supports common constraints such as `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, and `CHECK`.

### 6.1. Adding a PRIMARY KEY

If a table has no primary key yet:

~~~sql
ALTER TABLE staging_orders
ADD CONSTRAINT pk_staging_orders PRIMARY KEY (staging_order_id);
~~~

Primary key columns must be `NOT NULL`. An InnoDB table has only one `PRIMARY KEY`, which serves as the clustered index. Without a suitable primary key, InnoDB picks a `NOT NULL` unique index or generates an internal hidden row ID.

Before adding a primary key, check for `NULL`s and duplicates:

~~~sql
SELECT COUNT(*) AS null_keys
FROM staging_orders
WHERE staging_order_id IS NULL;

SELECT staging_order_id, COUNT(*) AS duplicate_count
FROM staging_orders
GROUP BY staging_order_id
HAVING COUNT(*) > 1;
~~~

If duplicates or `NULL`s exist, resolve them per business rules first. Adding a primary key on a large table may also rebuild the clustered index and generate substantial I/O load.

Dropping a primary key:

~~~sql
ALTER TABLE staging_orders
DROP PRIMARY KEY;
~~~

You cannot drop a primary key if a dependent foreign key or another structure requires it. In InnoDB, dropping a primary key can cause the engine to pick a different clustered index or generate a hidden row ID; this is rarely a change you want to make casually.

### 6.2. Adding a UNIQUE Constraint

`UNIQUE` ensures no two rows share duplicate keys per index comparison rules:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT uq_customers_email UNIQUE (email);
~~~

You can create a unique index directly:

~~~sql
ALTER TABLE customers
ADD UNIQUE INDEX uq_customers_email (email);
~~~

In MySQL, a `UNIQUE` constraint is implemented as a unique index. On nullable columns, a unique index can hold multiple `NULL` rows because `NULL` is not considered equal to another `NULL` in standard uniqueness checks. If business rules require every row to have a mandatory unique email, combine `NOT NULL` with `UNIQUE`.

Audit data before adding:

~~~sql
SELECT email, COUNT(*) AS duplicate_count
FROM customers
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
~~~

The column's collation affects comparisons. Under a case-insensitive collation, two emails differing only in letter case are treated as duplicates. Choose a collation matching the application's identity rules.

Dropping a unique index:

~~~sql
ALTER TABLE customers
DROP INDEX uq_customers_email;
~~~

MySQL uses `DROP INDEX` to drop the unique index created by a `UNIQUE` constraint. If dependent objects exist, handle relationships before dropping.

### 6.3. Adding a FOREIGN KEY

A foreign key guarantees child-table values reference an existing row in the parent table, or `NULL` if the column and business rules allow it.

Example:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customers (customer_id)
ON UPDATE RESTRICT
ON DELETE RESTRICT;
~~~

Before adding a foreign key, check:

- Both tables use a storage engine supporting foreign keys, typically InnoDB.
- Child and referenced columns have compatible types; for integers, size and signed/unsigned must match.
- The referenced column has a suitable index, typically `PRIMARY KEY` or `UNIQUE KEY`.
- The child column has the required index; InnoDB may auto-create one if none fits.
- No orphan rows exist in the child table.
- Charset and collation are compatible if the foreign key uses string columns.

Find orphan rows before adding:

~~~sql
SELECT o.order_id, o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
~~~

If orphan rows exist, decide whether to fix keys, insert valid parent records, or remove data through an approved procedure. Never delete rows solely to make a migration succeed.

### 6.4. ON DELETE and ON UPDATE

Referential actions define what happens when the parent key changes:

| Action | Meaning |
|---|---|
| RESTRICT | Reject changes in the parent table if referencing child rows exist |
| NO ACTION | In InnoDB, behaves equivalently to RESTRICT |
| CASCADE | Propagate delete or key update operations to child rows |
| SET NULL | Set child foreign key columns to NULL; child columns must allow NULL |

Example:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customers (customer_id)
ON DELETE CASCADE;
~~~

`ON DELETE CASCADE` can delete numerous order rows when deleting a single customer. Only use it when data lifecycle genuinely requires it; for financial or audit data, dedicated retention and soft-delete policies are usually needed.

### 6.5. Dropping a FOREIGN KEY

~~~sql
ALTER TABLE orders
DROP FOREIGN KEY fk_orders_customer;
~~~

`DROP FOREIGN KEY` removes the referential constraint. The supporting index on `customer_id` may remain after dropping the foreign key because it can still serve other queries. If you also want to drop the index, confirm it is no longer needed or used by another constraint before running `DROP INDEX`.

### 6.6. Adding a CHECK Constraint

`CHECK` evaluates an expression for every row on `INSERT` or `UPDATE`:

~~~sql
ALTER TABLE products
ADD CONSTRAINT chk_products_price
CHECK (price >= 0);
~~~

Another example:

~~~sql
ALTER TABLE bookings
ADD CONSTRAINT chk_booking_period
CHECK (ends_at > starts_at);
~~~

MySQL began enforcing `CHECK` constraints in version 8.0.16. Versions prior to 8.0.16 may accept `CHECK` syntax while silently ignoring enforcement. Therefore, on older versions, do not rely on `CHECK` to protect data.

`CHECK` passes any row where the expression does not evaluate to `FALSE`; an `UNKNOWN` result caused by `NULL` does not fail the constraint. If the column must have a value, combine it with `NOT NULL`.

Dropping `CHECK`:

~~~sql
ALTER TABLE products
DROP CHECK chk_products_price;
~~~

Constraint names should be meaningful and stable so migrations can reference them accurately.

## 7. Modifying Column-Related Indexes

Add an index:

~~~sql
ALTER TABLE orders
ADD INDEX idx_orders_status_created (status, created_at);
~~~

Add a unique index:

~~~sql
ALTER TABLE customers
ADD UNIQUE INDEX uq_customers_external_ref (external_ref);
~~~

Rename an index:

~~~sql
ALTER TABLE orders
RENAME INDEX idx_orders_status_created
TO idx_orders_status_time;
~~~

Drop an index:

~~~sql
ALTER TABLE orders
DROP INDEX idx_orders_status_time;
~~~

Do not drop an index just because you do not see it used in a single query. Consider the overall workload, index usage, query plans, foreign keys, and write overhead. A secondary index unused by the query you are inspecting may still serve background jobs or reports.

## 8. Making Multiple Changes in One ALTER TABLE

MySQL allows combining multiple alter options in a single statement:

~~~sql
ALTER TABLE customers
    ADD COLUMN preferred_language VARCHAR(10) NULL,
    ADD COLUMN marketing_opt_in BOOLEAN NOT NULL DEFAULT FALSE,
    ADD INDEX idx_customers_created_at (created_at);
~~~

Combining operations can avoid scanning or rebuilding the table multiple times, though the DDL algorithm must satisfy all operations in the statement. If one operation requires `COPY`, the entire `ALTER` may fall back to the more expensive algorithm.

When changes carry different risk profiles or require different online algorithms, splitting into separate migrations makes control, impact measurement, and recovery easier. There is no universal rule that one giant `ALTER` is always faster than multiple small ones; evaluate table structure, version, and benchmarks.

## 9. ALGORITHM and LOCK in DDL

### 9.1. Primary Algorithms

`ALTER TABLE` can use these algorithms:

| Algorithm | General Meaning |
|---|---|
| INSTANT | Modifies metadata for supported operations; avoids rebuilding table data |
| INPLACE | Storage engine applies changes without necessarily creating a full table copy; may still rebuild or construct indexes |
| COPY | Creates a new table copy, copies rows, then swaps out the old table; typically requires more I/O and time |

The name `INPLACE` does not mean the operation writes zero data. Some `INPLACE` operations still rebuild the clustered index or recreate secondary indexes. `INSTANT` is likewise supported only for a specific set of operations and conditions.

Example forcing MySQL to execute only if `INSTANT` is supported:

~~~sql
ALTER TABLE customers
ADD COLUMN profile_note VARCHAR(200) NULL,
ALGORITHM=INSTANT;
~~~

If the server cannot execute using `INSTANT`, the statement errors out instead of silently falling back to another algorithm. This is a useful safeguard against accidentally triggering a heavy `COPY` operation on a large table.

### 9.2. LOCK

The `LOCK` option controls concurrency levels permitted during DDL:

| Lock | General Meaning |
|---|---|
| DEFAULT | Let MySQL select the appropriate lock level |
| NONE | Allow concurrent reads and writes during supported online phases |
| SHARED | Allow reads but block writes during the corresponding phase |
| EXCLUSIVE | Block concurrent access with an exclusive lock |

Example:

~~~sql
ALTER TABLE orders
ADD INDEX idx_orders_created_at (created_at),
ALGORITHM=INPLACE,
LOCK=NONE;
~~~

If the operation or engine does not support the requested combination, MySQL returns an error. Do not omit options and blindly assume DDL will not lock application traffic.

### 9.3. Online DDL Still Requires Metadata Locks

Even when DDL supports `LOCK=NONE`, MySQL still requires metadata locks during specific phases, particularly at the start and end of the change. A long-running transaction holding a metadata lock on the table can block `ALTER TABLE`. Once DDL waits on a metadata lock, subsequent queries can queue up behind it.

Before migrating:

- Check for long transactions and sessions holding metadata locks.
- Avoid running DDL during peak traffic hours.
- Set appropriate timeouts and monitor the processlist.
- Prepare a way to abort or cancel the migration if wait times exceed operational thresholds.

Do not interpret "online" as zero impact. DDL still consumes CPU, I/O, redo/undo logs, temporary storage, and can increase replication lag.

## 10. DDL and Transactions

`ALTER TABLE` is DDL and triggers an implicit commit in MySQL. You cannot rely on an application transaction's `ROLLBACK` to undo an executed `ALTER TABLE`.

Example:

~~~sql
START TRANSACTION;

UPDATE customers
SET account_status = 'ACTIVE'
WHERE customer_id = 42;

ALTER TABLE customers
ADD COLUMN source_channel VARCHAR(30) NULL;

ROLLBACK;
~~~

`ALTER TABLE` can commit the open transaction before executing. Therefore, the preceding `UPDATE` may already be committed; `ROLLBACK` after `ALTER` neither undoes the DDL nor reverses what was implicitly committed.

MySQL 8.0 supports atomic DDL for many operations and supported storage engines: if the server crashes mid-execution, the DDL operation recovers consistently as either completed or unapplied. Atomic DDL does not mean DDL can be rolled back with a user `ROLLBACK` statement.

Keep DDL and data backfill changes in separate migration steps. Design rollbacks as compensating migrations or backup/snapshot restores rather than assuming an outer transaction can reverse `ALTER TABLE`.

## 11. Safe Migration Strategy for Live Tables

For small tables and simple changes, a single `ALTER TABLE` may suffice. For large tables or zero-downtime applications, follow the expand-migrate-contract pattern.

### 11.1. Expand: Extend the Schema

Add the new column in a backward-compatible way, usually nullable or with a safe `DEFAULT`:

~~~sql
ALTER TABLE customers
ADD COLUMN display_name VARCHAR(200) NULL;
~~~

Old application versions continue working because the old column is still present and the new column is not yet mandatory.

### 11.2. Migrate: Sync and Backfill Data

Deploy new application code capable of reading both old and new columns, or dual-writing both columns during the transition period. Backfill in batches:

~~~sql
UPDATE customers
SET display_name = full_name
WHERE customer_id > ?
  AND customer_id <= ?
  AND display_name IS NULL;
~~~

After each batch, check updated row counts and errors. Use bounded primary key ranges to avoid oversized transactions. For actively changing data, sync rows updated concurrently during the backfill.

### 11.3. Contract: Remove Legacy Structure

Once every application instance has switched to the new column, verify no remaining queries, jobs, or reports depend on the old column. Only then drop it:

~~~sql
ALTER TABLE customers
DROP COLUMN full_name;
~~~

The contract phase is destructive. Have backups or data reconstruction capability verified before executing it.

## 12. Complete Migration Example: Adding and Enforcing Email

Suppose the `customers` table currently has a nullable `email` column and we want to ensure every customer has a unique email.

**Step 1: Audit existing data**

~~~sql
SELECT COUNT(*) AS null_email_count
FROM customers
WHERE email IS NULL;

SELECT email, COUNT(*) AS duplicate_count
FROM customers
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1;
~~~

**Step 2: Remediate data per business rules**

Do not invent dummy emails to fill missing data unless the system explicitly defines that rule. Request missing data, flag status, or resolve exception records.

**Step 3: Add the unique index**

~~~sql
ALTER TABLE customers
ADD UNIQUE INDEX uq_customers_email (email);
~~~

**Step 4: Change column to NOT NULL**

~~~sql
ALTER TABLE customers
MODIFY COLUMN email VARCHAR(255) NOT NULL;
~~~

Before running, verify the original column definition to preserve the exact charset, collation, comment, and other attributes. Consider operation ordering based on application needs and your version's DDL capabilities.

**Step 5: Verify**

~~~sql
SHOW CREATE TABLE customers\G
SHOW INDEX FROM customers;

SELECT COUNT(*) AS null_email_count
FROM customers
WHERE email IS NULL;
~~~

The migration is complete only when both structure and data satisfy the new rule.

## 13. Monitoring Impact and Verifying After ALTER TABLE

Before and after DDL, record:

- Row counts, table size, and index sizes.
- Engine, charset, collation, and column definitions.
- Execution duration and metadata lock wait time.
- CPU, I/O, free disk space, and temporary disk usage.
- Replication lag and replica health.
- Application errors, timeouts, and queued connections.

Useful verification commands:

~~~sql
SHOW CREATE TABLE shop.orders\G
SHOW INDEX FROM shop.orders;
SHOW TABLE STATUS FROM shop LIKE 'orders'\G

SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'shop'
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
~~~

You can observe active processes:

~~~sql
SHOW FULL PROCESSLIST;
~~~

To investigate metadata locks more deeply, use Performance Schema and appropriate `sys` schema views if enabled. Access privileges and view schemas depend on the MySQL version.

## 14. Common Errors

### 14.1. Data Truncated or Out of Range

Usually caused by a target type narrower than existing data, insufficient precision, mismatched signed/unsigned, or strings exceeding the new length. Audit data before altering, convert in batches if needed, and verify SQL mode.

### 14.2. Cannot Add or Update a Child Row

When adding a foreign key, MySQL detects child rows referencing non-existent parent rows. Find orphan rows, fix data per business rules, and retry.

### 14.3. Duplicate Entry

When adding `PRIMARY KEY` or `UNIQUE`, existing data contains duplicates. Find duplicate groups with `GROUP BY`, decide which records to merge or fix before adding the constraint.

### 14.4. Lock Wait or Metadata Lock

DDL may block waiting on other transactions. Inspect the processlist, long transactions, and metadata locks; choose a suitable deployment window. Never kill sessions arbitrarily without understanding what that transaction is doing.

### 14.5. Long-Running DDL or Disk Full

`COPY` operations or index rebuilds can duplicate table data and require extra temporary space. Check disk space, I/O, table size, replication, and maintenance windows before running. On very large tables, evaluate online schema change tools if native DDL cannot meet downtime constraints.

## 15. Pre-Release Migration Checklist

1. Read `SHOW CREATE TABLE` and confirmed the target schema.
2. Identified columns, indexes, constraints, and dependent objects.
3. Measured row counts, `NULL` values, duplicates, and out-of-range values.
4. Verified SQL mode, MySQL version, and storage engine.
5. Identified which `ALGORITHM`/`LOCK` the operation can use.
6. Tested on a representative-sized data copy.
7. Estimated duration, I/O, temporary space, and replication lag.
8. Prepared a backup or snapshot and recovery plan.
9. Deployed backward-compatible application versions in sequence when needed.
10. Verified DDL, data, and queries after migration.

## 16. Common Misconceptions

**"ALTER TABLE always runs instantaneously."** No. Depending on the operation, MySQL may only update metadata, rebuild indexes, or copy the entire table.

**"ALGORITHM=INPLACE means zero data rebuild."** No. `INPLACE` can still rebuild the clustered index or perform heavy work inside the storage engine.

**"LOCK=NONE means zero locks."** No. Online DDL still needs metadata locks during specific phases and can block behind long transactions.

**"Changing DEFAULT updates all existing rows."** No. `DEFAULT` primarily applies to subsequent `INSERT`s; updating old data is a separate operation.

**"MODIFY COLUMN only needs the new data type."** No. You must re-declare all attributes you want to retain, such as `NULL`, `DEFAULT`, charset, collation, and comment.

**"DROP COLUMN can be undone with ROLLBACK."** No. `ALTER TABLE` triggers an implicit commit; recovering data requires backups or compensating migrations.

**"Adding CHECK is always enforced on every MySQL."** No. MySQL only enforces `CHECK` constraints starting in version 8.0.16.

**"Adding a FOREIGN KEY only requires two columns with the same name."** No. It requires compatible types, suitable indexes, a supporting engine, and existing data free of orphan rows.

## Conclusion

`ALTER TABLE` lets a schema evolve by adding, renaming, modifying, and dropping columns—as well as adding or removing `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, `CHECK`, and indexes. Every change requires evaluating existing data, target types, dependent objects, and the DDL capabilities of your MySQL version.

For active production tables, favor backward-compatible migrations, batch backfills, and dropping legacy structures only after applications have completely switched over. Distinguish `INSTANT`, `INPLACE`, and `COPY`; remember that online DDL still acquires metadata locks and `ALTER TABLE` cannot be rolled back inside an ordinary transaction. Pre- and post-migration verification safeguards data integrity and keeps MySQL systems running reliably.
