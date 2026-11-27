# Converting engines and re-verifying data, constraints, and indexes

## Objectives

After this lesson, you will be able to:

- Convert a MySQL table from one storage engine to another using appropriate DDL.
- Evaluate the impact of engine conversion on data, transactions, locking, indexes, and constraints.
- Pre-check data that could cause errors when adding `NOT NULL`, `UNIQUE`, or foreign keys.
- Reconcile table definitions, row counts, and data contents before and after conversion.
- Plan a conversion with backups, concurrent-write controls, a maintenance window, and a recovery plan.

## 1. Why must you verify after converting an engine?

The storage engine governs how MySQL stores and handles a table's data. Converting from MyISAM to InnoDB, for example, can introduce transactions, row-level locking, and foreign keys. However, the conversion operation can rebuild the table's physical structure, recreate indexes, and alter locking, recovery, or concurrent update behavior.

A successful `ALTER TABLE` statement only indicates that the server completed the DDL operation. It does not prove that:

- Every value was preserved without unintended truncation, rounding, or type coercion.
- Necessary indexes and unique constraints still exist with the exact column order.
- Referential relationships are established and no orphan records remain.
- Applications continue working properly under the new transaction, isolation level, and locking behavior.
- Query performance still meets requirements.

Therefore, engine conversion must be treated as a data and operational change. Record the initial baseline state, execute the conversion under control, and then verify both structure and data.

## 2. Inspecting the table before conversion

### 2.1. Identify the current engine and definition

Select the right database and inspect the engine:

```sql
SELECT DATABASE();

SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH,
    TABLE_COLLATION
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders';
```

`TABLE_ROWS` can be an estimate, especially for InnoDB. Use `COUNT(*)` when an exact record count is needed. Size metrics in `information_schema.TABLES` are also reported in engine-specific ways.

Retrieve the full DDL:

```sql
SHOW CREATE TABLE orders\G
```

This definition is the baseline for verifying columns, data types, defaults, `AUTO_INCREMENT`, primary keys, unique keys, indexes, foreign keys, charset, collation, comments, and engine. Save the output in your change record for post-conversion comparison.

### 2.2. Inspect columns and data types

```sql
SELECT
    COLUMN_NAME,
    ORDINAL_POSITION,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    EXTRA,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY ORDINAL_POSITION;
```

Pay attention to columns that could be affected when switching engines or normalizing schemas:

- String columns near length limits, or with differing charsets or collations.
- Numeric columns with `UNSIGNED`, or `DECIMAL` precision and scale that must remain intact.
- Date/time columns with default values, default expressions, or zero-date handling dependent on `sql_mode`.
- `BLOB`/`TEXT`, JSON, generated columns, and specialized data types.
- `AUTO_INCREMENT` columns and the next counter value.
- Nullable columns or columns with implicit defaults.

Engine conversion is not the time to arbitrarily change data types. If schema adjustments are also needed, separate them into deliberate changes so root causes are clear if data or applications fail.

### 2.3. Inspect indexes and constraints

List indexes:

```sql
SHOW INDEX FROM orders;
```

Or read metadata:

```sql
SELECT
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    SUB_PART,
    INDEX_TYPE,
    COLLATION
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
```

`SEQ_IN_INDEX` shows column order within a composite index; `SUB_PART` shows prefix length if present. When comparing, preserve exact column order, unique/non-unique status, prefix lengths, and index type. Comparing index names alone is insufficient.

Inspect constraints and foreign keys:

```sql
SELECT
    tc.CONSTRAINT_NAME,
    tc.CONSTRAINT_TYPE,
    kcu.COLUMN_NAME,
    kcu.ORDINAL_POSITION,
    kcu.REFERENCED_TABLE_SCHEMA,
    kcu.REFERENCED_TABLE_NAME,
    kcu.REFERENCED_COLUMN_NAME
FROM information_schema.TABLE_CONSTRAINTS AS tc
LEFT JOIN information_schema.KEY_COLUMN_USAGE AS kcu
  ON tc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
 AND tc.TABLE_NAME = kcu.TABLE_NAME
 AND tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
WHERE tc.TABLE_SCHEMA = DATABASE()
  AND tc.TABLE_NAME = 'orders'
ORDER BY tc.CONSTRAINT_NAME, kcu.ORDINAL_POSITION;
```

Inspect foreign key update/delete rules:

```sql
SELECT
    CONSTRAINT_NAME,
    UNIQUE_CONSTRAINT_SCHEMA,
    REFERENCED_TABLE_NAME,
    UPDATE_RULE,
    DELETE_RULE
FROM information_schema.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders';
```

In addition to constraints, record triggers and views depending on the table if they relate to business logic:

```sql
SHOW TRIGGERS FROM app_db LIKE 'orders';
```

Replace `app_db` with the actual database. Triggers do not replace constraints and should not be used to assume all data relationships are enforced.

## 3. Checking data before conversion

### 3.1. Record row counts and data ranges

Capture exact row counts and key data boundaries:

```sql
SELECT
    COUNT(*) AS row_count,
    MIN(order_id) AS min_order_id,
    MAX(order_id) AS max_order_id,
    MIN(created_at) AS first_created_at,
    MAX(created_at) AS last_created_at
FROM orders;
```

For large tables, `COUNT(*)` can take time. Schedule metric collection in an appropriate window and consider system load. If data continues changing during checks, measurements taken at different timestamps may not be directly comparable.

### 3.2. Find NULL values before adding NOT NULL

If you plan to change `customer_id` to `NOT NULL`, check for violating rows first:

```sql
SELECT COUNT(*) AS null_customer_ids
FROM orders
WHERE customer_id IS NULL;
```

If the result exceeds 0, decide how to handle each case: backfill accurate values from business sources, move records to quarantine, or keep `NULL` allowed if that is a valid state. Never inject dummy values just to make DDL succeed.

### 3.3. Find duplicate values before adding UNIQUE

For example, if you plan to create a unique index on `external_ref`:

```sql
SELECT external_ref, COUNT(*) AS duplicate_count
FROM orders
WHERE external_ref IS NOT NULL
GROUP BY external_ref
HAVING COUNT(*) > 1;
```

If the unique key spans multiple columns, group by all columns of the key:

```sql
SELECT tenant_id, external_ref, COUNT(*) AS duplicate_count
FROM orders
GROUP BY tenant_id, external_ref
HAVING COUNT(*) > 1;
```

MySQL allows multiple `NULL` values in a unique index according to its rules. If business rules require every record to have a unique, non-empty value, check for both `NULL` and duplicates.

### 3.4. Check for orphan records before adding foreign keys

Suppose `orders.customer_id` will reference `customers.customer_id`. Find orders without a matching customer:

```sql
SELECT o.order_id, o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.customer_id IS NULL;
```

If the query returns rows, you cannot add the foreign key while enforcing referential integrity. Determine whether these are corrupt records, deleted customers, or a business rule permitting missing references. Fix the data per business decision, then re-run the check.

### 3.5. Check values that may undergo conversion

If changing data types at the same time, find out-of-range or unconvertible values before running DDL. For example, when converting a string column to numeric:

```sql
SELECT order_id, legacy_amount
FROM orders
WHERE legacy_amount IS NOT NULL
  AND TRIM(legacy_amount) NOT REGEXP '^-?[0-9]+([.][0-9]+)?$';
```

This is only a basic decimal format check; monetary data also requires defining precision and scale. Do not rely on one generic regex instead of column-specific business validation rules.

For strings, check lengths before shrinking a column size:

```sql
SELECT MAX(CHAR_LENGTH(external_ref)) AS max_char_length,
       MAX(OCTET_LENGTH(external_ref)) AS max_byte_length
FROM orders;
```

`CHAR_LENGTH` counts characters; `OCTET_LENGTH` counts bytes. With multi-byte charsets like `utf8mb4`, the two values can differ significantly.

## 4. Converting the engine with ALTER TABLE

### 4.1. Verify the target engine

First, confirm the target engine is supported:

```sql
SHOW ENGINES;
```

If converting to InnoDB, confirm InnoDB has an appropriate support status. Do not rely on `default_storage_engine`, as that variable only sets the default for new tables that omit an engine specification.

### 4.2. Perform the conversion

Example converting the `orders` table to InnoDB:

```sql
ALTER TABLE orders ENGINE = InnoDB;
```

Immediately inspect the DDL result and warnings:

```sql
SHOW WARNINGS;

SELECT TABLE_NAME, ENGINE
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders';
```

`ALTER TABLE ... ENGINE = ...` can rebuild the table and indexes in the target engine's format. Execution time depends on table size, index count, I/O speed, concurrent activity, and the MySQL version's implementation.

### 4.3. Engine conversion is not a regular rollbackable operation

DDL such as `ALTER TABLE` triggers an implicit commit; you cannot wrap an engine conversion inside an application transaction and call `ROLLBACK` to undo it like a set of InnoDB `UPDATE` statements. Treat it as a structural change requiring backups and an independent recovery plan.

Online DDL capability and lock levels depend on source/target engines, change type, version, and table structure. Do not assume engine conversion always runs with `ALGORITHM=INPLACE` or `LOCK=NONE`. Check version documentation and test on a similarly sized copy first. If you specify an unsupported algorithm or lock mode, the server may reject the change; do not force online options without verification.

During conversion, account for:

- Metadata locks that can force other DDL or DML queries to wait.
- Extra temporary disk space potentially needed to rebuild the table and indexes.
- Increased CPU and I/O that can impact production workloads.
- DDL potentially waiting on long-running transactions holding metadata locks.
- Potentially significant lock durations and completion times on large tables.

### 4.4. Converting multiple related tables

If tables are linked by foreign keys, list all parents and children. InnoDB requires all tables participating in a foreign key relationship to use a compatible supporting engine; in standard MySQL, both sides use InnoDB.

Execute conversions according to plan across the entire group of related tables. After each step, verify constraints and data. Do not assume converting only the child or only the parent table is sufficient to establish a valid referential relationship.

## 5. Re-verifying data after engine conversion

### 5.1. Check row counts and data boundaries

Re-run the counts and aggregations captured prior to conversion:

```sql
SELECT
    COUNT(*) AS row_count,
    MIN(order_id) AS min_order_id,
    MAX(order_id) AS max_order_id,
    MIN(created_at) AS first_created_at,
    MAX(created_at) AS last_created_at
FROM orders;
```

Compare against the baseline. For business tables, also verify sums, row counts by status, by date, or by tenant:

```sql
SELECT
    DATE(created_at) AS order_date,
    status,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM orders
GROUP BY DATE(created_at), status
ORDER BY order_date, status;
```

Aggregations must run over the same data scope or at a consistent point in time. If the application keeps writing during conversion or between measurements, differences may reflect new transactions rather than data loss.

### 5.2. Verify content by key

For critical data, compare by primary key across small ranges. For example, checking a range of `order_id`:

```sql
SELECT
    order_id,
    customer_id,
    status,
    total_amount,
    created_at
FROM orders
WHERE order_id BETWEEN 100000 AND 109999
ORDER BY order_id;
```

In large migrations, data can be exported in batches and deterministically hashed at the application or ETL layer. Normalize representations of `NULL`, charsets, time zones, and numeric formats before hashing. Do not rely solely on `COUNT(*)` or a single sum to conclude two datasets are identical.

### 5.3. Check NULL values, lengths, and value domains

Re-run the data checks from the preflight step. For example:

```sql
SELECT COUNT(*) AS null_customer_ids
FROM orders
WHERE customer_id IS NULL;

SELECT MAX(CHAR_LENGTH(external_ref)) AS max_external_ref_length
FROM orders;

SELECT COUNT(*) AS invalid_amounts
FROM orders
WHERE total_amount < 0;
```

The `total_amount < 0` check only applies if business rules forbid negative numbers; for refunds or adjustments, negative values may be valid. Every check must derive from the system's data rules.

## 6. Re-verifying indexes

### 6.1. Reconcile index definitions

After conversion, run:

```sql
SHOW INDEX FROM orders;
SHOW CREATE TABLE orders\G
```

Compare with pre-conversion output:

- Is the primary key still intact?
- Do unique indexes preserve uniqueness and column order?
- Do composite indexes preserve exact column order and prefix lengths?
- Are `FULLTEXT`, `SPATIAL`, functional, or specialized indexes still supported?
- Do indexes have the expected names, types, and attributes?

Index support depends on engine and version. An index valid in the source engine might not be supported by the target engine or may require redefinition. Inspect the actual post-conversion DDL, not just old statements.

### 6.2. Check unique indexes and duplicate data

If a unique index needs to be recreated, check for duplicates first:

```sql
SELECT external_ref, COUNT(*) AS duplicate_count
FROM orders
WHERE external_ref IS NOT NULL
GROUP BY external_ref
HAVING COUNT(*) > 1;
```

After cleaning data and confirming business rules, you can add the unique index:

```sql
ALTER TABLE orders
ADD CONSTRAINT uq_orders_external_ref UNIQUE (external_ref);
```

Do not add a constraint merely because current data happens to have no duplicates. A unique key must reflect business rules and `NULL`-handling expectations.

### 6.3. Update statistics and verify execution plans

After converting the engine and recreating needed indexes, update table statistics:

```sql
ANALYZE TABLE orders;
```

Then inspect critical queries:

```sql
EXPLAIN
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 101
  AND created_at >= '2026-01-01'
ORDER BY created_at DESC;
```

Compare access types, chosen keys, estimated rows, and join order against the baseline. The new engine may use different optimizer mechanics, statistics, and locking. Do not assume performance is better simply because the table moved to InnoDB; benchmark with production-like data and traffic.

## 7. Re-verifying constraints and referential relationships

### 7.1. Confirm constraints exist

```sql
SELECT
    CONSTRAINT_NAME,
    CONSTRAINT_TYPE
FROM information_schema.TABLE_CONSTRAINTS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY CONSTRAINT_TYPE, CONSTRAINT_NAME;
```

Compare the list of primary keys, unique keys, check constraints (if supported by your version), and foreign keys against the saved DDL. Do not assume the target engine automatically creates constraints that the source engine did not enforce.

### 7.2. Add foreign keys after verifying data

Example adding a relationship from `orders.customer_id` to `customers.customer_id`:

```sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customers (customer_id)
ON UPDATE RESTRICT
ON DELETE RESTRICT;
```

Before running, verify:

- Both tables use an engine supporting foreign keys.
- Referencing and referenced columns have compatible data types, including size and signedness for numeric types.
- For string columns, charsets and collations match appropriately.
- The referenced column has a suitable index satisfying MySQL's rules.
- No orphan rows exist in the child table.
- `ON UPDATE` and `ON DELETE` behaviors match business rules.

Re-check for orphans after adding the constraint:

```sql
SELECT o.order_id, o.customer_id
FROM orders AS o
LEFT JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.customer_id IS NULL;
```

An empty result is a good sign for the checked relationship, yet you still must confirm the constraint exists in `information_schema` and that the application properly handles constraint violation errors.

### 7.3. Do not use foreign_key_checks to bypass data validation

MySQL provides the `foreign_key_checks` variable to control foreign key checking during certain operations. Disabling it is not a way to fix orphan data. When re-enabled, MySQL does not automatically scan and validate all data loaded while checks were disabled.

Therefore, never use `SET foreign_key_checks = 0` to make a migration "pass through" and then assume the data is valid. If a special workflow requires disabling checks, include an independent referential validation step before letting applications use the data.

## 8. Verifying application behavior after engine conversion

Moving from a non-transactional engine to InnoDB can change application behavior for the better, yet it can also expose old assumptions about locking or update ordering. Verify:

- **Transactions:** commit, rollback, savepoints, and multi-statement error handling.
- **Isolation:** isolation levels and read outcomes under concurrent transactions.
- **Locking:** row locks, gap/next-key locks, deadlocks, and lock wait times.
- **Constraints:** does the application handle duplicate key, foreign key, and `NOT NULL` errors properly?
- **AUTO_INCREMENT:** does the next value align with existing keys and write workflows?
- **SQL mode, charset, collation:** have string comparisons, type coercions, or date/time values changed?
- **Backup/restore:** do current backup tools support the target engine and successfully restore data?
- **Replication/HA:** do binlogs, replicas, failover, and monitoring continue functioning properly?

In particular, when migrating from MyISAM to InnoDB, locking shifts from table locks to InnoDB's locking mechanisms. Concurrent reads and writes may achieve different parallelism, yet deadlocks and lock waits can still occur. Applications must implement bounded retries for retryable transaction errors.

## 9. Safe conversion plan for production

### 9.1. Preparation

1. Identify MySQL version, source/target engines, and DDL support capabilities.
2. Save `SHOW CREATE TABLE`, column metadata, indexes, constraints, triggers, and critical business queries.
3. Check for `NULL` values, duplicates, orphans, lengths, and value domains.
4. Measure table/index sizes, write rates, query durations, and available disk space.
5. Take a restorable backup and test restoring it in an equivalent environment.
6. Dry-run the conversion on a production-sized data copy.

### 9.2. Execution

1. Choose a maintenance window or migration mechanism suited to downtime constraints.
2. If simple data consistency is required, pause writes to the table during conversion and notify dependent components.
3. Run the engine conversion DDL; monitor duration, metadata locks, CPU, I/O, and disk space.
4. Read warnings/errors and confirm the target engine was applied.
5. Create or restore any indexes and constraints not preserved as planned.

If writes cannot be paused, use an online migration strategy that synchronizes changes during copy, monitors replication lag, and cuts over endpoints safely. Tools like `pt-online-schema-change` or `gh-ost` have specific limitations regarding foreign keys, triggers, DDL types, and versions; test them beforehand rather than assuming they handle every engine conversion.

### 9.3. Verification and bringing the application back

1. Compare row counts, min/max keys, business aggregates, and batch data.
2. Reconcile DDL, indexes, constraints, and triggers against the baseline.
3. Run orphan, duplicate, and critical data-rule checks.
4. Run application smoke tests and integration tests.
5. Benchmark critical queries and monitor locks, deadlocks, CPU, and I/O.
6. Re-open write traffic once mandatory checks pass.
7. Monitor post-conversion and archive results for rollback or investigation if needed.

### 9.4. Recovery plan

If verification fails, halt the rollout and execute the prepared fallback plan. With DDL changes, do not rely on a transaction `ROLLBACK` to revert to the old engine. Options may include restoring a backup, routing traffic back to the prior copy, or running a tested reverse migration. If the application already wrote new data after conversion, determine how to reconcile those changes before reverting.

## 10. Post-conversion checklist

| Item | Verification criterion |
|---|---|
| Engine | `information_schema.TABLES.ENGINE` matches target engine |
| DDL | Columns, data types, defaults, charset/collation, and table options match the plan |
| Row counts | `COUNT(*)` or batch reconciliation matches over the same data scope |
| Data values | Business totals, keys, and batch hashes show no unexplained discrepancies |
| Indexes | Primary, unique, composite, prefix, and specialized indexes are verified |
| Constraints | Primary keys, unique keys, check constraints, and foreign keys exist as required |
| References | No orphan rows exist in checked relationships |
| AUTO_INCREMENT | Next value aligns with existing keys and write workflows |
| Queries | `EXPLAIN` and benchmarks for critical queries meet requirements |
| Application | Transactions, locking, retries, and constraint handling work properly |
| Operations | Backup/restore, replication, monitoring, and recovery plans are confirmed |

## 11. Conclusion

Converting a storage engine via `ALTER TABLE ... ENGINE = ...` can rebuild tables and indexes while changing transaction, locking, and constraint behavior. Therefore, inspect DDL and data beforehand, check target engine limits, and re-verify row counts, values, indexes, constraints, and application behavior afterward.

A conversion should only be considered complete once data is reconciled, table structure meets requirements, critical queries are verified, and backup/restore workflows work. For production, dry-run on an equivalent copy, control concurrent writes, and prepare a recovery plan before starting.
