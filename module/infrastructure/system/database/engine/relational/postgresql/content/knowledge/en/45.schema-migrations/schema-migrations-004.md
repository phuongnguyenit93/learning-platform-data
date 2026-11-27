# Adding Columns, Default Values, and Version-Specific Behavior Checks

Adding a column to a PostgreSQL table can be a very lightweight operation, or it can force the database to read and rewrite the entire table. The outcome depends on the PostgreSQL version, the DEFAULT expression, NOT NULL requirements, column type, and table state. The most critical boundary is PostgreSQL 11: adding a column with a non-volatile default expression can use **fast default**, storing the default value in metadata so existing rows read the new value without rewriting the entire heap.

Fast default does not mean ALTER TABLE needs no lock, that every default is fast, or that the schema change has no impact on the application. Safe migrations require checking server version, volatility, table size, lock behavior, constraints, replication, and how the application deploys code.

## 1. Learning Objectives

After this lesson, you will be able to:

- Add columns using ALTER TABLE ... ADD COLUMN.
- Distinguish defaults for existing rows from defaults applied to future INSERTs.
- Explain the critical difference between PostgreSQL 10 and PostgreSQL 11+.
- Distinguish volatile and non-volatile default expressions.
- Identify when ADD COLUMN can avoid a table rewrite.
- Understand the impact of NOT NULL, CHECK, and DEFAULT.
- Evaluate locks, wait times, and application impact.
- Roll out schema changes in multiple steps to reduce risk.
- Inspect catalog metadata and verify results on old and new data.
- Design migrations compatible across multiple PostgreSQL versions.

## 2. ADD COLUMN Syntax

### 2.1. Basic Syntax

ALTER TABLE is used to add a column:

```sql
ALTER TABLE customers
ADD COLUMN loyalty_level text;
```

If DEFAULT is omitted, the new column's value on existing rows is NULL. Subsequent INSERTs also receive NULL if the application does not provide a value and the column has no default or other constraint.

### 2.2. Adding a Column With a Default

```sql
ALTER TABLE customers
ADD COLUMN is_active boolean DEFAULT true;
```

For existing rows, PostgreSQL ensures queries see true for the new column. For future INSERTs, if the statement omits is_active, the default true is applied.

### 2.3. Adding a NOT NULL Column

```sql
ALTER TABLE customers
ADD COLUMN status text NOT NULL DEFAULT 'active';
```

Every row must have a non-NULL value. The non-NULL default supplies values for existing rows and new INSERTs. Without a default, adding a NOT NULL column to a populated table typically fails because existing rows would receive NULL.

### 2.4. Adding a Column With a Specific Type

```sql
ALTER TABLE orders
ADD COLUMN submitted_at timestamptz;
```

Data types affect storage, operators, casts, index design, and client mapping. Choose types based on semantics; do not use text for everything if the application needs date/time, numeric, or enum semantics.

### 2.5. Adding Multiple Columns in One ALTER TABLE

```sql
ALTER TABLE orders
    ADD COLUMN source text,
    ADD COLUMN priority smallint DEFAULT 0,
    ADD COLUMN reviewed_at timestamptz;
```

A single ALTER TABLE can perform multiple subcommands. Grouping changes can reduce the number of lock acquisitions, though if any subcommand is heavy, the entire command can still run long.

### 2.6. IF NOT EXISTS

```sql
ALTER TABLE customers
ADD COLUMN IF NOT EXISTS loyalty_level text;
```

IF NOT EXISTS prevents errors if a column with the same name already exists. It does not verify that the existing column has the right type, default, nullability, or collation. Idempotent migrations still require checking for schema drift.

### 2.7. Specifying the Schema Explicitly

```sql
ALTER TABLE public.customers
ADD COLUMN external_reference text;
```

Use schema-qualified table names in migrations to prevent search_path from targeting the wrong table.

### 2.8. Verifying After Adding a Column

```sql
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'customers'
ORDER BY ordinal_position;
```

This is a readable way to inspect schema. For PostgreSQL-specific details such as missing-value metadata, inspect the pg_attribute catalog covered later.

## 3. What Does DEFAULT Mean?

### 3.1. Default Applies When INSERT Omits the Column

```sql
ALTER TABLE invoices
ADD COLUMN currency text DEFAULT 'VND';

INSERT INTO invoices (invoice_number, total_amount)
VALUES ('INV-1001', 250000);
```

The new row receives currency = 'VND' because the INSERT omits this column.

### 3.2. DEFAULT Does Not Override Application-Provided Values

```sql
INSERT INTO invoices (invoice_number, total_amount, currency)
VALUES ('INV-1002', 90000, 'USD');
```

The explicit value USD is used. Default only applies when the column is omitted or the DEFAULT keyword is specified.

### 3.3. Explicit DEFAULT in INSERT

```sql
INSERT INTO invoices (invoice_number, total_amount, currency)
VALUES ('INV-1003', 120000, DEFAULT);
```

DEFAULT instructs PostgreSQL to use the column's current default expression. If the column has no default, the result is NULL (except for identity/generated cases with specific semantics).

### 3.4. DEFAULT Does Not Automatically Update Existing Rows After SET DEFAULT

```sql
ALTER TABLE invoices
ALTER COLUMN currency SET DEFAULT 'VND';
```

The command above changes the default for future INSERT/UPDATE statements that omit a value. It does not run an UPDATE across all existing rows. To backfill existing rows, run separate DML.

### 3.5. DROP DEFAULT Does Not Erase Stored Values

```sql
ALTER TABLE invoices
ALTER COLUMN currency DROP DEFAULT;
```

This removes the default for future operations. Existing values in rows are neither deleted nor changed to NULL.

### 3.6. NULL vs. Omitting the Column

These two statements differ:

```sql
INSERT INTO invoices (invoice_number, currency)
VALUES ('INV-2001', DEFAULT);

INSERT INTO invoices (invoice_number, currency)
VALUES ('INV-2002', NULL);
```

DEFAULT requests using the default expression; NULL requests storing NULL without triggering the default. If the column is NOT NULL, the second statement is rejected.

### 3.7. When Is the Default Expression Evaluated?

The default expression is evaluated when a value is needed for a new row. For ADD COLUMN on a populated table, the PostgreSQL version and expression volatility determine whether existing row values are materialized via a table rewrite or stored as missing-value metadata.

### 3.8. One Default for All Existing Rows

When ADD COLUMN uses a non-volatile default, PostgreSQL 11+ can evaluate the expression once at ALTER TABLE time and use that same result as the logical default for existing rows. This differs from evaluating a volatile expression separately for every row.

### 3.9. Defaults Can Depend on Session/Transaction

Expressions such as CURRENT_USER, CURRENT_TIMESTAMP, or current_setting(...) have transaction/session-dependent semantics. Understand the volatility classification and the value present in the migration session before using them as defaults.

### 3.10. Do Not Confuse Default With Generated Columns

A default only supplies a value when INSERT/UPDATE omits the column. A generated column is computed from an expression based on other columns per PostgreSQL rules. The two mechanisms have different semantics and limitations.

## 4. Volatility of DEFAULT Expressions

### 4.1. Three Volatility Levels

PostgreSQL classifies functions into:

| Volatility | General meaning | Examples |
| --- | --- | --- |
| IMMUTABLE | Same arguments always produce the same result; independent of database/session/time. | lower(text), pure arithmetic operations. |
| STABLE | Result is stable within a single statement per function contract, but may differ between statements. | CURRENT_TIMESTAMP, now(). |
| VOLATILE | Can change between calls, has side effects, or depends on mutable state. | clock_timestamp(), random(), nextval(). |

This is a contract relied upon by the planner and executor. Never declare a function with the wrong volatility just to speed up a migration.

### 4.2. Non-Volatile Defaults

PostgreSQL 11+ can use fast default if the default expression is non-volatile. This includes immutable and stable expressions per catalog semantics. PostgreSQL evaluates the expression during ALTER TABLE and stores a missing value for existing rows.

For example:

```sql
ALTER TABLE events
ADD COLUMN imported_at timestamptz DEFAULT now();
```

now() returns the transaction timestamp and is stable. When ALTER TABLE runs, existing rows see one shared timestamp evaluated for the migration transaction; subsequent INSERTs receive the default timestamp of their own transactions.

### 4.3. Volatile Defaults

A volatile expression may require a different value for each existing row. PostgreSQL must compute and store a value for every row via a table rewrite when adding a column with a volatile default.

For example:

```sql
ALTER TABLE sample_data
ADD COLUMN random_key double precision DEFAULT random();
```

Each existing row needs its own result. On a large table, the operation can read/write the entire table, generate heavy I/O, and hold a strong lock for a long time.

### 4.4. clock_timestamp vs. now

```sql
SELECT now(), transaction_timestamp(), statement_timestamp(), clock_timestamp();
```

- now() and transaction_timestamp() return the transaction start time.
- statement_timestamp() returns the statement start time.
- clock_timestamp() returns the actual wall-clock time when the function is called and can change even within a single statement.

clock_timestamp() is volatile; now() is stable. Thus two defaults that look similar in meaning ("current time") can have vastly different ADD COLUMN costs.

### 4.5. random and Sequences

random() produces a changing result on each call. nextval() mutates sequence state and is volatile. Using them as defaults during ADD COLUMN on a large table can force a rewrite, and sequence side effects must also be accounted for.

### 4.6. User-Defined Functions

PostgreSQL relies on a function's volatility marker. If a function is marked STABLE but actually depends on state changing per row/call, that declaration is incorrect and can produce wrong results. Never change VOLATILE to STABLE just to avoid a rewrite.

### 4.7. Inspecting Volatility in the Catalog

```sql
SELECT
    p.oid::regprocedure AS function_name,
    p.provolatile,
    CASE p.provolatile
        WHEN 'i' THEN 'IMMUTABLE'
        WHEN 's' THEN 'STABLE'
        WHEN 'v' THEN 'VOLATILE'
    END AS volatility
FROM pg_proc AS p
WHERE p.proname IN ('now', 'clock_timestamp', 'random', 'nextval')
ORDER BY 1;
```

provolatile is the catalog flag: i, s, or v.

### 4.8. Literal Expressions

```sql
ALTER TABLE accounts
ADD COLUMN region_code text DEFAULT 'VN';
```

Literals do not depend on row/session and are the classic case for fast default in PostgreSQL 11 and later.

### 4.9. Cast Expressions

```sql
ALTER TABLE products
ADD COLUMN enabled boolean DEFAULT true;

ALTER TABLE products
ADD COLUMN created_on date DEFAULT DATE '2026-01-01';
```

Constant expressions can be handled via fast default. For casts or operators provided by extensions or user-defined types, verify volatility and actual behavior.

### 4.10. Pre-Migration Checks

Before using a function in a default, determine:

1. Is the function built-in or user-defined?
2. What is pg_proc.provolatile?
3. Must the result differ for each existing row?
4. Should the value for existing rows represent the migration time or each row's creation time?
5. Which version is the migration running on?

Choose the expression based on business semantics first, then evaluate cost.

## 5. Fast Default Starting in PostgreSQL 11

### 5.1. Behavior Before PostgreSQL 11

In PostgreSQL 10 and earlier versions, ADD COLUMN with a non-NULL DEFAULT on a populated table typically had to rewrite the table to write the default into every row. On large tables, this could consume substantial time, I/O, and locks.

For example:

```sql
ALTER TABLE large_orders
ADD COLUMN source text DEFAULT 'legacy';
```

On PostgreSQL 10 and earlier, do not assume this statement is metadata-only; adding the default can rewrite the heap.

### 5.2. PostgreSQL 11: Fast Default

PostgreSQL 11 introduced an optimization for ADD COLUMN with a non-volatile default. Instead of writing the value to all existing rows, the server stores the missing value in catalog metadata. When reading an old tuple lacking this physical attribute, the executor returns the missing value.

On large tables, the statement can complete very quickly compared to rewriting the entire heap.

### 5.3. Key Conditions

Fast default applies when:

- The PostgreSQL version supports it (11 and later).
- The statement is ADD COLUMN with a non-volatile default expression.
- No other factor in the same ALTER TABLE forces a table rewrite.

Do not generalize "PostgreSQL 11+ makes ADD COLUMN always fast" to every DDL. Check all subcommands and column types.

### 5.4. attmissingval and atthasmissing

PostgreSQL stores missing-value information in the pg_attribute catalog:

- atthasmissing: indicates whether the attribute has missing-value metadata.
- attmissingval: the value used when an old tuple lacks the physical attribute.

This is an implementation detail useful for understanding fast default. Applications should not rely directly on catalog internals as a stable API.

### 5.5. Reading Existing Rows

With fast default, an un-rewritten old row still returns the logical default value on SELECT. SQL users see the column as populated, even though the value has not been written as an individual datum in each old tuple.

### 5.6. Inserting New Rows

Rows INSERTed after the column is added receive the default value and store data according to the current tuple layout. Missing-value metadata primarily supports old rows created before the column existed.

### 5.7. Updating Existing Rows

When an old row is UPDATEd and the tuple is rewritten in the new layout, the logical missing value may be materialized into the new tuple. Do not rely on every row retaining atthasmissing after rewrite or maintenance operations.

### 5.8. DROP DEFAULT After Fast Default

```sql
ALTER TABLE large_orders
ALTER COLUMN source DROP DEFAULT;
```

This operation only removes the default for new rows. Existing rows must still read the missing value stored in metadata. DROP DEFAULT does not turn them into NULL.

### 5.9. Subsequent Table Rewrites

Another operation that forces a table rewrite may materialize missing values into new tuples and clear the need for missing metadata on those rows. Thus atthasmissing can change after rewrite operations.

### 5.10. Benefits and Limitations

Fast default drastically reduces data-writing cost for certain ADD COLUMN operations, but:

- ALTER TABLE still requires a lock.
- DDL can wait long for a lock if other transactions hold relation locks.
- Volatile defaults can still rewrite.
- Another subcommand in the same ALTER can make the operation heavy.
- Indexes, constraints, partitioning, and replication still need to be accounted for.

## 6. Version Behavior Matrix

### 6.1. Overview Matrix

| Version | ADD COLUMN without default | ADD COLUMN with constant/non-volatile DEFAULT | ADD COLUMN with volatile DEFAULT |
| --- | --- | --- | --- |
| PostgreSQL 10 and earlier | Usually metadata-only, no heap rewrite solely for adding a nullable column. | On populated tables, usually rewrites to materialize the default. | Rewrites to compute values for each row. |
| PostgreSQL 11 and later | Metadata-only for a simple nullable column addition. | Fast default: stores missing-value metadata, avoids heap rewrite solely for the default. | Requires rewrite to compute volatile values for existing rows. |

This matrix covers the basic ADD COLUMN case. Other factors such as stored generated columns, type conversions, constraints, partitioning, or multiple subcommands can change the outcome.

### 6.2. PostgreSQL 9.6 and 10

In these versions, adding a nullable column without a default is usually a metadata operation. When a non-NULL default is specified on a populated table, the server must rewrite so every tuple holds the new column value.

If a migration must support these versions, consider adding a nullable column without a default first, backfilling in batches, and then setting the default for future INSERTs.

### 6.3. PostgreSQL 11

This is the fast-default milestone. A constant or non-volatile expression can be stored in metadata instead of rewriting the entire table.

### 6.4. PostgreSQL 12–18

Fast default remains the standard behavior for non-volatile defaults. However, other ALTER TABLE features, generated columns, partitioning, and constraint validation have evolved across releases. Read the documentation for the exact major version, especially when migrations use multiple subcommands.

### 6.5. Checking Server Version

```sql
SHOW server_version;
SHOW server_version_num;
```

server_version_num is a convenient integer for migration logic. Never infer server behavior from the psql client version.

### 6.6. Primary and Replica Versions

In physical streaming replication, primary and standby belong to the same PostgreSQL major version in a standard cluster. During major upgrades or migrations, clearly identify which node is serving traffic and which version actually executes DDL.

### 6.7. Version-Specific Migrations

If an application supports multiple major versions, you can:

- Use a shared strategy across all versions: nullable-add + batched backfill + SET DEFAULT.
- Use fast default directly on PostgreSQL 11+ if semantics fit.
- Maintain separate migration branches when the performance benefit is significant and the deployment system manages versions cleanly.

### 6.8. Do Not Rely on the Dev Environment Version String

Migrations run against the actual production server version. Check the version on the pipeline/deployment target and staging. A PostgreSQL 16 dev database does not prove a migration is safe on PostgreSQL 10 in production.

### 6.9. Check Major-Version Documentation

Major-version documentation pages reflect the corresponding behavior. Only use the current documentation when the target version is actually the current supported release.

### 6.10. Compatibility Testing

Create disposable databases for each supported major version, load realistic data volumes, run the migration, and record durations, lock waits, table sizes, WAL volume, and SELECT results. This verifies actual behavior far better than relying on migration assumptions alone.

## 7. Table Rewrites and Physical Costs

### 7.1. What Is a Table Rewrite?

A table rewrite rebuilds the physical representation of a table, typically reading old tuples and writing new tuples with the updated schema/values. On large tables, the operation can:

- Read and write data roughly proportional to heap size.
- Generate heavy WAL depending on the operation and recovery settings.
- Require additional temporary disk space.
- Hold a strong lock and block concurrent DML.
- Increase replication lag or backup workload.

### 7.2. Metadata-Only Changes

A metadata-only change updates the catalog without rewriting the entire heap. Fast default is one example. However, metadata-only does not mean zero-cost: there are still catalog updates, lock acquisition, WAL/catalog work, and cache invalidation.

### 7.3. Estimating Disk Headroom

Before a rewrite, inspect:

- Heap size and TOAST size.
- Index sizes.
- Available disk on the tablespace/filesystem.
- WAL filesystem capacity and archive throughput.
- Whether replication slots are retaining WAL long term.
- Backup/replica lag.

Do not assume you need exactly double the disk size; demand depends on the operation, index handling, tablespace, and concurrent writes.

### 7.4. WAL and Replicas

DDL rewrites can generate substantial WAL. Physical replicas must replay that WAL; logical subscribers have distinct behavior governed by DDL management. Monitor WAL generation, archive backlog, and replay lag during migrations.

### 7.5. Lock Duration

A large rewrite usually holds a lock blocking DML for its execution time. A metadata-only ALTER TABLE can execute very fast once the lock is acquired, yet if another transaction holds a lock for a long time, the ALTER still waits.

### 7.6. Table Rewrites Within the Same Transaction

DDL inside a transaction holds locks until the transaction ends. Avoid letting an application migration transaction continue running slow steps after ALTER TABLE; that extends the lock hold duration.

### 7.7. VACUUM and Rewrites Are Not the Same

Normal VACUUM reclaims/reuses dead tuple space within a relation; it is not equivalent to a table rewrite that materializes a new column. VACUUM FULL, CLUSTER, or certain ALTER TYPE operations can rewrite. Use the right terminology rather than calling every cleanup "vacuum."

### 7.8. TOAST

Rows with large values may store data out-of-line in a TOAST relation. Rewrites or data transformations can affect both heap and TOAST storage. Base estimates on the entire relation set, not just the heap file.

### 7.9. Indexes

A nullable ADD COLUMN or fast default does not automatically require rebuilding existing indexes because those indexes do not contain the new column. If the migration creates an index on the new column, that is a separate operation with its own scan/build cost and locks.

### 7.10. Measure Before Production

Test the migration on a staging copy with size and data distribution close to production. Record duration, lock wait, WAL bytes, replica lag, and disk usage. Small dev tables do not simulate the cost of tables hundreds of GB in size.

## 8. Locks During Schema Changes

### 8.1. ADD COLUMN Typically Requires ACCESS EXCLUSIVE

Standard ALTER TABLE ADD COLUMN acquires an ACCESS EXCLUSIVE lock on the table. This is a strong lock that conflicts with nearly all other table-level locks, including locks used by ordinary SELECTs.

Even when fast default makes the catalog update instantaneous, the statement must still wait to acquire the lock. If a long transaction holds a lock on the table, the migration can wait and form a queue for other sessions.

### 8.2. Lock Waits Are More Dangerous Than Execution Time

An ALTER TABLE may take only milliseconds after acquiring the lock, yet wait for minutes because another transaction has not committed. While ALTER TABLE waits for ACCESS EXCLUSIVE, incoming requests may also queue behind it depending on the lock queue and workload.

Therefore, monitor both lock acquisition wait time and command execution time.

### 8.3. Long Transactions

A session might open a transaction, read the table, and sit idle before committing. The relation lock held by that transaction can prevent DDL from acquiring ACCESS EXCLUSIVE.

Check for idle-in-transaction sessions and long-running transactions before a migration. Do not look only at active queries.

### 8.4. lock_timeout

Set a limit on lock wait time so the migration fails fast if it cannot acquire the lock:

```sql
SET lock_timeout = '3s';
SET statement_timeout = '2min';

ALTER TABLE public.customers
ADD COLUMN preferred_language text;
```

If the lock is not acquired within 3 seconds, the statement is canceled and the transaction enters an aborted state if inside a transaction block. The migration client must handle rollback and retry with backoff.

### 8.5. statement_timeout

statement_timeout limits total statement execution time, including lock wait time. Set a value appropriate for the migration. For large table rewrites, too short a timeout aborts the operation mid-way; too long a timeout can hold locks too long.

### 8.6. Inspecting Lock Waits

```sql
SELECT
    a.pid,
    a.usename,
    a.state,
    a.wait_event_type,
    a.wait_event,
    now() - a.query_start AS query_age,
    pg_blocking_pids(a.pid) AS blocking_pids,
    left(a.query, 160) AS query_text
FROM pg_stat_activity AS a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.query_start;
```

This query finds blocked sessions and lists the PIDs that may be blocking them. Inspect the blocker before canceling or terminating; never kill transactions arbitrarily.

### 8.7. Viewing Relation Locks

```sql
SELECT
    a.pid,
    a.state,
    l.mode,
    l.granted,
    c.relname,
    a.query
FROM pg_locks AS l
JOIN pg_class AS c ON c.oid = l.relation
LEFT JOIN pg_stat_activity AS a ON a.pid = l.pid
WHERE c.relname = 'customers'
ORDER BY l.granted, a.pid;
```

A table name can exist across multiple schemas; add a schema filter when needed. Catalog queries are point-in-time snapshots and require privileges to view the relevant sessions.

### 8.8. Keep Migration Transactions Short

Keep DDL transactions short. Do not run a multi-million-row data backfill inside the same transaction as ADD COLUMN if they can be separated. Commit immediately after the metadata change to release the lock.

### 8.9. Controlled Retries

If a migration fails due to a lock timeout:

1. Confirm the transaction rolled back.
2. Identify the blocker and a lower-workload window.
3. Retry with backoff and jitter.
4. Set a bounded retry count.
5. Log and alert if it fails to complete.

Do not retry in a tight loop that worsens the lock queue.

### 8.10. DDL Still Requires a Change Plan

Fast default reduces rewrites, not lock risk. For critical tables, migrations need a maintenance/change window, short lock timeouts, observability, and a rollback/forward-fix plan.

## 9. NOT NULL and CHECK Constraints

### 9.1. Adding NOT NULL When the Table Already Has Rows

The following command usually fails if the table has data and no non-NULL default:

```sql
ALTER TABLE customers
ADD COLUMN customer_tier text NOT NULL;
```

Existing rows have no value for the new column and would receive NULL. You must provide an appropriate default or use a multi-step migration to backfill before setting NOT NULL.

### 9.2. ADD COLUMN NOT NULL DEFAULT on PostgreSQL 11+

On PostgreSQL 11+, if the default is non-volatile, fast default can supply values for existing rows without rewriting the heap solely for the default. The column can be added with NOT NULL because the missing value is non-NULL.

```sql
ALTER TABLE customers
ADD COLUMN customer_tier text NOT NULL DEFAULT 'standard';
```

This does not remove the lock requirement. On PostgreSQL 10 and earlier, the same operation on a populated table can rewrite the table.

### 9.3. SET NOT NULL After Backfilling

If the column already exists as nullable, ensure no NULLs remain before setting NOT NULL:

```sql
SELECT count(*)
FROM customers
WHERE customer_tier IS NULL;

ALTER TABLE customers
ALTER COLUMN customer_tier SET NOT NULL;
```

If NULLs remain, SET NOT NULL fails. On large tables, the validation scan can take significant time; there is a pattern using a validated CHECK constraint to avoid redundant scans.

### 9.4. CHECK Constraints

A CHECK constraint ensures every INSERTed/UPDATEd row satisfies an expression:

```sql
ALTER TABLE orders
ADD CONSTRAINT orders_total_nonnegative
CHECK (total_amount >= 0);
```

By default, PostgreSQL verifies existing rows when adding a CHECK constraint. On large tables, the validation scan can run long.

### 9.5. NOT VALID

You can add a CHECK constraint with NOT VALID:

```sql
ALTER TABLE customers
ADD CONSTRAINT customers_tier_present
CHECK (customer_tier IS NOT NULL) NOT VALID;
```

NOT VALID skips scanning and validating all existing rows at ADD CONSTRAINT time. The constraint is still enforced for new rows and rows UPDATEd after the constraint is added.

### 9.6. VALIDATE CONSTRAINT

After backfilling and ensuring existing data satisfies the condition:

```sql
ALTER TABLE customers
VALIDATE CONSTRAINT customers_tier_present;
```

VALIDATE CONSTRAINT scans existing data to confirm the constraint. It uses a weaker lock than a normal ADD CONSTRAINT and allows ordinary DML to proceed during validation per PostgreSQL lock semantics.

### 9.7. Using CHECK to Support SET NOT NULL

PostgreSQL can skip a full table scan on SET NOT NULL if a valid CHECK constraint already proves the column cannot contain NULL and that constraint is not dropped in the same command:

```sql
ALTER TABLE customers
ADD CONSTRAINT customers_tier_not_null_check
CHECK (customer_tier IS NOT NULL) NOT VALID;

ALTER TABLE customers
VALIDATE CONSTRAINT customers_tier_not_null_check;

ALTER TABLE customers
ALTER COLUMN customer_tier SET NOT NULL;

ALTER TABLE customers
DROP CONSTRAINT customers_tier_not_null_check;
```

This technique avoids repeated scans. SET NOT NULL still requires a lock; verify your PostgreSQL version and specific constraint behavior before production.

### 9.8. Backfill Before Validation

If existing rows still contain NULLs, VALIDATE CONSTRAINT will fail. Perform batched backfills, verify the NULL count reaches 0, and then validate.

### 9.9. CHECK Can Evaluate to NULL

A CHECK constraint passes if the expression evaluates to TRUE or NULL; it only rejects FALSE. Therefore CHECK (amount > 0) does not replace NOT NULL if amount can be NULL. To forbid NULL, use NOT NULL or an explicit check condition.

### 9.10. Foreign Keys Also Support NOT VALID

A foreign key can be added NOT VALID to avoid checking all historical rows immediately at ADD CONSTRAINT time; new and updated rows are still enforced. Later, VALIDATE CONSTRAINT checks existing data. Foreign keys have distinct lock behavior and costs on both referencing and referenced tables; read the documentation for your version.

## 10. Batched Data Backfills

### 10.1. Why Not UPDATE the Whole Table at Once?

A single massive UPDATE can:

- Generate massive WAL volume.
- Create many dead tuples and increase autovacuum work.
- Hold row locks and transaction snapshots for a long time.
- Increase replication lag.
- Bloat the table and indexes.
- Cause application latency spikes.

For large tables, splitting the backfill into independently committed batches keeps load controlled and allows pausing/resuming.

### 10.2. Add a Nullable Column First

```sql
ALTER TABLE customers
ADD COLUMN customer_tier text;
```

This is typically a metadata change on PostgreSQL versions supporting basic ADD COLUMN without a default. DDL still requires a brief ACCESS EXCLUSIVE lock.

### 10.3. Set Default for New INSERTs

```sql
ALTER TABLE customers
ALTER COLUMN customer_tier SET DEFAULT 'standard';
```

After this step, INSERTs omitting customer_tier receive standard. Existing rows remain NULL until backfilled.

### 10.4. Batched Backfill by Primary Key

Example using an ascending id and a bounded batch size:

```sql
WITH batch AS (
    SELECT id
    FROM customers
    WHERE customer_tier IS NULL
    ORDER BY id
    LIMIT 5000
    FOR UPDATE SKIP LOCKED
)
UPDATE customers AS c
SET customer_tier = 'standard'
FROM batch
WHERE c.id = batch.id;
```

Run the statement in its own transaction and loop until no matching rows remain. SKIP LOCKED is useful when multiple backfill workers run in parallel or to avoid waiting on rows locked by the application; design the loop so skipped rows are not missed.

### 10.5. Commit Each Batch

Do not wrap the entire loop in one giant transaction. Commit each batch to release row locks, shorten snapshot hold time, and let vacuum clean up dead tuples incrementally.

### 10.6. Choosing Batch Size

A batch of 5,000 rows is just an example. Tune based on row width, index count, WAL rate, storage throughput, replication lag, and application latency. Start small and scale up when headroom permits.

### 10.7. Batching by Key Range

If you have an ascending primary key, you can partition by ranges:

```sql
UPDATE customers
SET customer_tier = 'standard'
WHERE id > 100000
  AND id <= 105000
  AND customer_tier IS NULL;
```

Save checkpoints of completed ranges. This makes resuming easy, though you must account for new rows or rows with IDs outside the scanned range.

### 10.8. Backfilling From Business Data

Not every row gets the same value. You can backfill via a join or mapping:

```sql
UPDATE orders AS o
SET fulfillment_region = c.region_code
FROM customers AS c
WHERE c.id = o.customer_id
  AND o.fulfillment_region IS NULL;
```

For large tables, chunk by the orders primary key and verify join cardinality/uniqueness to avoid non-deterministic results.

### 10.9. Reducing Replica Impact

Monitor replay lag and WAL archiving. Pause or shrink batch sizes if replica lag exceeds operational thresholds. Never let replication slots retain WAL until disk fills up.

### 10.10. Completing the Backfill

```sql
SELECT count(*) AS remaining_nulls
FROM customers
WHERE customer_tier IS NULL;
```

Proceed to validation/NOT NULL only when the result is 0 and the application writes valid values for every new row.

## 11. Expand-Contract Migrations for Applications

### 11.1. Why Is Expand-Contract Needed?

During a rolling deployment, old and new application versions may run simultaneously for a period. If DDL immediately requires a new NOT NULL column or drops an old column, older instances can error out.

Expand-contract adds a compatible schema first, deploys code capable of using the new schema, backfills and verifies, and only then tightens constraints or drops old schema elements.

### 11.2. Expand Phase

1. ADD COLUMN nullable, usually without a default if supporting multiple server versions.
2. Set a default for new INSERTs if appropriate.
3. Deploy code that reads/writes the new column while staying compatible with unbackfilled rows.
4. Monitor errors and ensure all app instances have upgraded.

### 11.3. Backfill Phase

Backfill historical rows in batches. Verify data, null counts, uniqueness/business rules, and replica lag. Do not enforce NOT NULL before all writers send valid values.

### 11.4. Validate Phase

Add CHECK NOT VALID, validate after backfilling, and then SET NOT NULL if required by the schema. Keep a temporary CHECK if needed to prove conditions during the transition.

### 11.5. Contract Phase

Once all application versions use the new schema and no longer read or write the legacy column, remove compatibility code or drop the old column in a separate migration.

### 11.6. Backward Compatibility

New code should tolerate:

- The column not yet existing in some environments during rollout.
- Historical rows remaining NULL during the backfill phase.
- Defaults not yet deployed on every database.
- Some older app instances still INSERTing without providing the new column.

Define the exact contract between code and schema at each step.

### 11.7. Do Not Use DEFAULT to Mask Bad Data

A default should only be a valid default under business semantics. Do not set a placeholder like unknown or 0 just to get a migration past NOT NULL if the application treats it as real data.

### 11.8. Feature Flags

Reading/writing the new column can be gated by a feature flag after the schema is expanded and sufficiently backfilled. Keep a rollback flag to revert to old behavior if validation catches issues.

### 11.9. Independent Migrations

Separate fast DDL, long backfills, and constraint validation into distinct migrations or jobs. This simplifies retries, observability, and rollbacks.

### 11.10. Contract Only After Observation

Do not drop a legacy column immediately after deploying new code. Wait long enough to confirm no old binaries, scheduled jobs, reports, integrations, or ad hoc SQL depend on the old schema.

## 12. Special Column Cases and Table Structures

### 12.1. Generated Stored Columns

A stored generated column stores the result of a generated expression inside the row. When adding a stored generated column to a populated table, PostgreSQL must compute values for existing data; this operation can require a table rewrite and carry high cost.

```sql
ALTER TABLE products
ADD COLUMN normalized_sku text
GENERATED ALWAYS AS (upper(trim(sku))) STORED;
```

Generated columns were introduced in PostgreSQL 12 as stored. Newer versions may introduce additional generated-column modes; check the documentation for your exact major version. Do not apply fast-default assumptions to stored generated columns.

### 12.2. Identity Columns

An identity column uses an internal sequence to auto-generate values on INSERT:

```sql
CREATE TABLE shipment_items (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    description text
);
```

Adding identity to an existing column has different semantics than adding a normal constant default. If the table already has rows that need identity values assigned, design an explicit backfill and sequence alignment, check your version, and test on a data copy beforehand.

Do not assume adding identity automatically resolves all historical NULLs or sequence collisions.

### 12.3. Serial-Style Sequence Defaults

A column with a default calling nextval is volatile:

```sql
ALTER TABLE legacy_events
ADD COLUMN generated_id bigint DEFAULT nextval('legacy_events_id_seq');
```

On a large table, a volatile default can force a rewrite to generate distinct values for every old row. Additionally, ensure the sequence exists, ownership/permissions are correct, and the sequence is positioned past the highest backfilled value.

### 12.4. Defaults Depending on Extensions or User-Defined Types

A default may invoke a function, operator, or cast provided by an extension. Volatility and behavior of the function/type affect fast-default eligibility. Verify extension versions across all environments and do not assume identical cast semantics across major versions.

### 12.5. Partitioned Tables

When adding a column to a partitioned parent table, PostgreSQL propagates the change to partitions according to version rules. A large partition count can force DDL to acquire locks across many relations and lengthen lock acquisition.

Check:

- Partition count and nesting.
- Detached/attached partitions.
- Partition-specific defaults or constraints.
- Whether any partition has schema drift.
- Lock conflicts on child relations.

### 12.6. Adding a Column to a Single Partition

If a change targets only one partition, consider schema consistency with the parent and sibling partitions. A single partition with a divergent column can complicate queries through the parent and attach/detach operations.

Do not use ALTER TABLE ONLY on parent or child without understanding the command's inheritance/partition semantics.

### 12.7. Inheritance

With traditional table inheritance, ALTER TABLE on a parent typically affects descendants unless ONLY is used on supported operations. Columns can be inherited; adding the same name/type to a child can cause conflicts.

### 12.8. Foreign Tables and Partitioned Foreign Tables

Foreign tables/FDWs have capabilities and DDL behavior dependent on the FDW. Local catalog metadata changes via ALTER TABLE do not necessarily create columns on the remote system. Check remote schemas and FDW support before migrating.

### 12.9. Temporary and Unlogged Tables

Temporary tables are session-scoped and unlogged tables have different WAL/recovery semantics than ordinary logged tables. DDL on them has different costs and persistence; do not benchmark on temp/unlogged tables to predict production logged table behavior.

### 12.10. Type Changes Accompanied by ADD COLUMN

If the same migration both adds a column and alters/casts the type of an existing column, the type change may force a rewrite even when the new ADD COLUMN qualifies for fast default. Separate changes to isolate which operation drives cost and locking.

## 13. Version-Based Migration Recipes

### 13.1. Recipe A: PostgreSQL 11+ With an Appropriate Constant Default

If all existing rows can take the same valid business value:

```sql
ALTER TABLE public.orders
ADD COLUMN source_system text NOT NULL DEFAULT 'legacy';
```

This is the classic fast-default case in PostgreSQL 11+. Even without rewriting the heap solely for the default, the statement still requires an ACCESS EXCLUSIVE lock along with lock timeouts and monitoring.

### 13.2. Recipe B: Supporting PostgreSQL 10 and Earlier

Use nullable-add, set the default separately, backfill in batches, and then set NOT NULL:

```sql
-- Migration 1: quick schema expansion
ALTER TABLE public.orders
ADD COLUMN source_system text;

-- Migration 2: default for future inserts
ALTER TABLE public.orders
ALTER COLUMN source_system SET DEFAULT 'legacy';
```

Next, deploy compatible application code, backfill old rows in batches, validate zero NULLs remain, and then SET NOT NULL. This strategy avoids a massive table rewrite at ADD COLUMN time on older servers.

### 13.3. Recipe C: Distinct Values per Historical Row

If values must be derived from each row's data, add a nullable column first:

```sql
ALTER TABLE public.events
ADD COLUMN event_day date;
```

Backfill in batches from the existing timestamp:

```sql
UPDATE public.events
SET event_day = created_at::date
WHERE id > 100000
  AND id <= 105000
  AND event_day IS NULL;
```

Do not use a constant default if business rules require each row to have its own value derived from historical data.

### 13.4. Recipe D: Default now for Existing Rows

If the requirement is for all historical rows to share the migration timestamp, on PostgreSQL 11+:

```sql
ALTER TABLE audit_events
ADD COLUMN migrated_at timestamptz NOT NULL DEFAULT now();
```

now() is stable, not volatile. Existing rows see the same migration transaction timestamp; subsequent INSERTs receive their own inserting transaction's timestamp. If each historical row needs its own real event time, this is not the right semantics.

### 13.5. Recipe E: Volatile Default Needing Unique/Random per Row

Do not run a volatile ADD COLUMN directly on a very large table unless you accept a rewrite. Instead:

1. Add a nullable column without a default.
2. Deploy writers that generate values for new rows.
3. Backfill historical rows in batches using a function/sequence with the desired semantics.
4. Check uniqueness/distribution.
5. Apply required constraints/defaults.

### 13.6. Recipe F: NOT NULL Column With No Business Default

If the application must supply a real value for every row:

1. Add a nullable column.
2. Deploy new code writing values.
3. Backfill historical rows from business data sources.
4. Validate CHECK NOT VALID.
5. SET NOT NULL.

Do not set placeholder values merely to satisfy a constraint.

### 13.7. Recipe G: Changing Default While Preserving Historical Values

```sql
ALTER TABLE orders
ALTER COLUMN priority SET DEFAULT 10;
```

Existing rows do not change. If you want to raise priority for a subset of historical rows, run an UPDATE with a specific WHERE clause and verify the business rules separately.

### 13.8. Recipe H: Dropping Default While Preserving Historical Values

```sql
ALTER TABLE orders
ALTER COLUMN priority DROP DEFAULT;
```

Rows that already have a priority keep it. New application writes must supply an explicit value or accept NULL if the column is nullable.

### 13.9. Recipe I: Multiple Columns With Different Semantics

You do not need to combine all columns into one ALTER:

- A column with an appropriate constant default can be added directly on PG11+.
- A column needing per-row derivation should be added nullable and backfilled.
- A NOT NULL column requires data validation.
- A stored generated column may require a rewrite.

Splitting migrations makes locking and partial rollbacks easier to manage.

### 13.10. Recipe J: Rerunnable Migrations

IF NOT EXISTS avoids duplicate-column errors, yet the pipeline must still verify schema state after each run. If a migration stops midway through multiple steps, identify which steps committed and resume from a checkpoint; do not assume the entire migration file is atomic if the tool splits transactions.

## 14. Verifying Catalog and Data After Migration

### 14.1. Inspecting Column Metadata

```sql
SELECT
    a.attname,
    format_type(a.atttypid, a.atttypmod) AS data_type,
    a.attnotnull,
    a.atthasdef,
    a.atthasmissing,
    a.attmissingval
FROM pg_attribute AS a
WHERE a.attrelid = 'public.orders'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
```

atthasmissing/attmissingval let you inspect fast-default metadata on versions containing these catalog fields. Catalog internals can change; use this query for diagnosis, not as an application contract.

### 14.2. Inspecting the Default Expression

```sql
SELECT
    column_name,
    column_default,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders'
  AND column_name = 'source_system';
```

column_default describes the expression used for new rows; it does not necessarily display missing-value metadata for historical rows.

### 14.3. Checking Null Counts

```sql
SELECT
    count(*) FILTER (WHERE source_system IS NULL) AS null_rows,
    count(*) AS total_rows
FROM public.orders;
```

On very large tables, COUNT(*) can require a costly scan. Run at an appropriate time or rely on a validated constraint verified by PostgreSQL. Do not use statistics estimates as absolute proof for NOT NULL.

### 14.4. Checking Constraints

```sql
SELECT
    conname,
    contype,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'public.orders'::regclass
ORDER BY conname;
```

convalidated shows whether the constraint has validated historical rows or remains in the NOT VALID state.

### 14.5. Checking Relation Size

```sql
SELECT
    pg_size_pretty(pg_relation_size('public.orders')) AS heap_size,
    pg_size_pretty(pg_table_size('public.orders')) AS table_size,
    pg_size_pretty(pg_total_relation_size('public.orders')) AS total_size;
```

Compare before and after for signs of a rewrite or unexpected growth. Sizes can shift due to concurrent DML, vacuum, and index changes; measure under comparable conditions.

### 14.6. Checking Migrations Waiting on Locks

Inspect pg_stat_activity, pg_locks, wait events, and blocking PIDs. Record the blocker's transaction start time. Never conclude a migration is hung solely from long statement runtime; it may be waiting on a lock.

### 14.7. Checking Replicas

On the primary, check pg_stat_replication; on standbys, check pg_stat_wal_receiver and replay LSN. After a DDL rewrite/backfill, confirm replicas have replayed the WAL and lag is within SLA.

### 14.8. Checking Application Behavior

Test INSERT omitting the column, INSERT specifying DEFAULT, INSERT sending an explicit value, and UPDATE on an old row. Check ORM/schema caches, prepared statements, serializers, and reporting queries.

### 14.9. Checking Permissions

ALTER TABLE requires appropriate privileges on the relation; default expressions may call functions or sequences the migration role must have permission to access. Check ownership and grants on sequence/extension objects.

### 14.10. Recording Migration Evidence

Record server_version_num, migration command, start/end times, lock wait, relation sizes, WAL/archive lag, constraint state, and null count. This provides evidence for comparing staging against production.

## 15. Diagnosing Common Scenarios

### 15.1. ADD COLUMN Runs Slowly

Check:

1. Server major version.
2. Whether the default expression is volatile.
3. Whether there is a stored generated column or type change in the same ALTER.
4. Whether many partitions/descendants need locks.
5. Whether the statement is waiting on a lock or executing a rewrite.

Check wait_event, pg_locks, and blocking PIDs to distinguish a lock wait from an I/O-heavy rewrite.

### 15.2. Fast-Default ADD COLUMN Is Still Blocked

Fast default avoids heap rewrites for eligible cases, yet ALTER TABLE still needs ACCESS EXCLUSIVE. Look for transactions holding relation locks, idle-in-transaction sessions, and unfinished prepared transactions.

### 15.3. Fast in Staging but Slow in Production

Staging may have fewer rows, fewer concurrent sessions, and no long transactions. Compare table/TOAST/index sizes, partition count, lock queues, workload, and storage. Do not compare only server CPU/RAM.

### 15.4. Migration on PostgreSQL 10 Takes Hours

If ADD COLUMN has a non-NULL DEFAULT on a large table, a rewrite is the likely explanation. Confirm via server version, I/O, relation size, and lock state. For future rollouts, use nullable-add + batched backfill + SET DEFAULT/NOT NULL.

### 15.5. Default now on Historical Rows Differs From Row Creation Time

now() in fast default provides a single migration-transaction timestamp for historical rows. If the business requires each row's true timestamp, derive it from a historical column or audit source and backfill.

### 15.6. Changing Default Leaves Old Values Unchanged

This is expected behavior. SET DEFAULT only changes the default for rows created or updated later when the column is omitted. UPDATE historical rows separately if business rules require changing existing data.

### 15.7. DROP DEFAULT Causes INSERTs to Fail

After DROP DEFAULT, an INSERT omitting a nullable column receives NULL; if the column is NOT NULL, that INSERT fails. Check application writers and deploy code that sends values before dropping the default.

### 15.8. SET NOT NULL Fails

Check NULL count, concurrent writers, CHECK constraint state, and backfill completeness. A backfill may have finished once while older app code kept inserting NULLs afterward. Set a default or deploy updated writers before validating.

### 15.9. VALIDATE CONSTRAINT Fails

Some historical rows may violate the constraint. Find violating rows with a corresponding query, fix the data per business rules, and re-validate. Do not drop a constraint just to make a migration green if it protects a key invariant.

### 15.10. Backfill Runs Forever

Check indexes for the predicate/range, batch size, rows skipped via SKIP LOCKED, deadlocks, WAL rate, and autovacuum. If every batch scans the full table due to a missing index or inefficient key range, optimize row selection.

### 15.11. Replica Lag Increases

Backfills and rewrites generate WAL and replay load. Shrink batch size, add pauses between batches, and check standby I/O/CPU and archive throughput. Never let slots retain WAL until the filesystem fills.

### 15.12. Disk Grows After Backfill

UPDATEs create dead tuples and index churn. Check autovacuum progress, table bloat, index sizes, and long-running snapshots blocking vacuum cleanup. Regular VACUUM can reuse space; VACUUM FULL requires a rewrite and strong locks.

### 15.13. Application Errors After ADD COLUMN

Some ORMs/drivers cache schemas, use SELECT * with ordinal mapping, or run positional INSERTs without listing columns. Check generated SQL, prepared statements, row decoders, and code assumptions about column count/order.

### 15.14. IF NOT EXISTS Masks Schema Drift

If a column already exists with the wrong type or default, IF NOT EXISTS does not fix it. Compare catalogs against the desired schema and write explicit reconciliation migrations.

### 15.15. Partition Attach Fails After Migration

Check column definitions, constraints, and defaults on the partition. A child table with mismatched schema or data violating partition constraints cannot be attached. Run validation queries on the child beforehand.

### 15.16. Generated Columns Do Not Use Fast Default

Stored generated columns must compute values for historical rows. Separate the operation, estimate rewrite cost, and consider backfilling into an ordinary column if a multi-step online rollout is required.

### 15.17. Sequence Collisions After Backfill

If backfilling IDs with a sequence or assigning IDs manually, advance the sequence safely past the maximum existing ID and test concurrent inserts. Avoid letting the sequence emit existing IDs.

### 15.18. Migration Rollback Is Difficult

ADD COLUMN can sometimes be rolled back with DROP COLUMN, but once the application writes new data, dropping the column loses that data. Plan forward-fixes and backup/recovery before destructive contract changes.

## 16. Common Mistakes

### 16.1. Assuming ADD COLUMN Is Always Metadata-Only

Volatile defaults, stored generated columns, type conversions, or other subcommands can force a rewrite. Verify version and expressions before running.

### 16.2. Assuming PostgreSQL 11+ Makes Every ADD COLUMN Fast

Fast default only applies to non-volatile defaults under qualifying conditions. It neither removes lock requirements nor eliminates rewrites caused by other operations.

### 16.3. Using clock_timestamp for "Current Time"

clock_timestamp is volatile and can force per-row computation on existing rows. If you want a single migration timestamp, consider now() after confirming business semantics.

### 16.4. Marking a User-Defined Function STABLE to Avoid Rewrites

Volatility is a correctness contract. Misdeclaring it can cause PostgreSQL to evaluate expressions incorrectly and produce bad data.

### 16.5. Thinking SET DEFAULT Backfills Historical Rows

SET DEFAULT only affects future INSERT/UPDATEs. Historical rows require a separate UPDATE/backfill.

### 16.6. Thinking DROP DEFAULT Erases Old Values

DROP DEFAULT only removes the expression for future writes; existing data remains untouched.

### 16.7. Sending NULL Instead of DEFAULT

An explicit NULL INSERT does not trigger the default. If the column is NOT NULL, the statement is rejected.

### 16.8. Adding NOT NULL Before Backfilling

Historical NULLs or old writers can fail the migration. Expand the schema, deploy writers, backfill, validate, and then SET NOT NULL.

### 16.9. Updating the Entire Table in One Transaction

This can generate massive WAL/dead tuples, hold locks/snapshots too long, and cause replica lag. Split into independently committed batches.

### 16.10. Forgetting Lock Timeout

Even metadata-only DDL can wait for ACCESS EXCLUSIVE and build a lock queue. Set a reasonable lock_timeout and check blockers.

### 16.11. Combining Fast DDL With Heavy Rewrites

A single heavy subcommand inside a multi-subcommand ALTER TABLE can make the entire command expensive. Split operations to manage locks and rewrites.

### 16.12. Testing Only on Small Tables

Tables with a few thousand rows do not simulate lock contention, rewrite duration, WAL, TOAST, or replica lag in production. Test on realistic datasets.

### 16.13. Relying on psql Version

Client version does not dictate server DDL behavior. Run SHOW server_version / server_version_num on the target.

### 16.14. Ignoring Application Compatibility

The schema can be valid while the app breaks due to SELECT *, ORM metadata caches, positional INSERTs, or old binaries. Use expand-contract rollouts.

### 16.15. Treating IF NOT EXISTS as Complete Migration Idempotency

It only skips duplicate column name errors without verifying type, default, or constraints. Verify schema state after every step.

### 16.16. Using Placeholder Defaults Against Business Semantics

Fake defaults can turn into real data and corrupt reports. Match business semantics or backfill from authoritative sources.

### 16.17. Not Monitoring Replication

DDL rewrites/backfills can create WAL backlogs. Monitor replicas, archiving, and slot retention throughout the migration.

### 16.18. Dropping CHECK Too Early

If CHECK serves as proof for SET NOT NULL to skip a scan or protects writers during rollout, only drop it once the NOT NULL constraint is active and all writers comply.

### 16.19. Not Checking Partitions

Parent/child schema drift can cause attach failures or query errors. Inspect all partitions and inheritance descendants.

### 16.20. Not Recording Evidence

Without recording versions, commands, lock waits, durations, and data checks, it is hard to explain differences between staging and production. Preserve full migration evidence.

## 17. Hands-On Labs

Run these labs on a disposable database. Generate enough data to observe differences; do not run table rewrites or backfill stress tests in production.

### Lab 1. Adding a Column Without a Default

#### Step 1. Create the table

```sql
CREATE TABLE add_column_lab AS
SELECT
    g::bigint AS id,
    md5(g::text) AS payload
FROM generate_series(1, 1000000) AS g;

ALTER TABLE add_column_lab ADD PRIMARY KEY (id);
```

#### Step 2. Record size

```sql
SELECT
    pg_relation_size('add_column_lab') AS heap_bytes,
    pg_total_relation_size('add_column_lab') AS total_bytes;
```

#### Step 3. Add a nullable column

```sql
ALTER TABLE add_column_lab
ADD COLUMN note text;
```

#### Step 4. Verify

```sql
SELECT count(*) AS rows,
       count(note) AS nonnull_notes
FROM add_column_lab;
```

Existing rows are expected to have note as NULL.

### Lab 2. Comparing Non-Volatile Defaults

#### Step 1. Create a new table

```sql
CREATE TABLE fast_default_lab AS
SELECT g::bigint AS id
FROM generate_series(1, 1000000) AS g;
```

#### Step 2. Record time and size

Record start time, relation size, and server_version_num.

#### Step 3. Add a constant default

```sql
ALTER TABLE fast_default_lab
ADD COLUMN source text DEFAULT 'import';
```

#### Step 4. Read historical rows

```sql
SELECT source, count(*)
FROM fast_default_lab
GROUP BY source;
```

On PostgreSQL 11+, this is a fast-default candidate. Observe duration and atthasmissing if supported by the catalog.

### Lab 3. Volatile Default on a Disposable Table

#### Step 1. Create a separate test table

```sql
CREATE TABLE volatile_default_lab AS
SELECT g::bigint AS id
FROM generate_series(1, 100000) AS g;
```

#### Step 2. Add a random default

```sql
ALTER TABLE volatile_default_lab
ADD COLUMN random_value double precision DEFAULT random();
```

#### Step 3. Check results

```sql
SELECT count(*), count(DISTINCT random_value)
FROM volatile_default_lab;
```

Historical rows are assigned values during the rewrite. Use a disposable table because the operation can read and rewrite the entire heap.

### Lab 4. DEFAULT vs. UPDATE

#### Step 1. Add a column

```sql
ALTER TABLE add_column_lab
ADD COLUMN source_code text;
```

#### Step 2. Set default

```sql
ALTER TABLE add_column_lab
ALTER COLUMN source_code SET DEFAULT 'legacy';
```

#### Step 3. Compare historical and new rows

```sql
INSERT INTO add_column_lab (id, payload)
VALUES (2000001, 'new-row');

SELECT id, source_code
FROM add_column_lab
WHERE id IN (1, 2000001);
```

Historical row remains NULL; new row receives legacy.

### Lab 5. CHECK NOT VALID and Validation

#### Step 1. Add an unvalidated constraint

```sql
ALTER TABLE add_column_lab
ADD CONSTRAINT add_column_lab_note_nonempty
CHECK (note IS NOT NULL) NOT VALID;
```

#### Step 2. Observe enforcement

Try INSERT/UPDATE on a new row with note NULL; the constraint rejects it. The constraint has not yet validated historical rows.

#### Step 3. Backfill

```sql
UPDATE add_column_lab
SET note = 'filled'
WHERE note IS NULL;
```

On real large tables, replace the full-table UPDATE with a batch loop.

#### Step 4. Validate

```sql
ALTER TABLE add_column_lab
VALIDATE CONSTRAINT add_column_lab_note_nonempty;
```

#### Step 5. SET NOT NULL

```sql
ALTER TABLE add_column_lab
ALTER COLUMN note SET NOT NULL;
```

### Lab 6. Inspecting Lock Waits

#### Step 1. Session A

```sql
BEGIN;
SELECT * FROM add_column_lab WHERE id = 1;
-- Keep transaction open for the exercise.
```

#### Step 2. Session B

Attempt ADD COLUMN on the same table with a short lock_timeout. Observe the timeout.

#### Step 3. Observe the blocker

Use pg_stat_activity, pg_locks, and pg_blocking_pids to identify the session holding the lock.

#### Step 4. End Session A

COMMIT or ROLLBACK Session A, then retry the DDL in Session B.

### Lab 7. Cleaning Up Lab Data

```sql
DROP TABLE IF EXISTS add_column_lab;
DROP TABLE IF EXISTS fast_default_lab;
DROP TABLE IF EXISTS volatile_default_lab;
```

Only run cleanup in the lab database and confirm these tables were created by the lab.

## 18. Practice Exercises

### Exercise 1. Basic ADD COLUMN

Write a statement to add a nullable text column named preferred_name without a default to the customers table.

### Exercise 2. Default

Add a boolean column named is_enabled with default true. Explain the values seen by historical rows and new INSERTs.

### Exercise 3. NULL vs. DEFAULT

Distinguish between an INSERT omitting the column, an INSERT using the DEFAULT keyword, and an INSERT sending an explicit NULL.

### Exercise 4. SET DEFAULT

If you run ALTER COLUMN SET DEFAULT 'VN', do historical rows automatically change to VN? Why or why not?

### Exercise 5. Volatility

Classify now(), clock_timestamp(), random(), and nextval() by volatility.

### Exercise 6. Fast Default

In which PostgreSQL major version was fast default introduced? What is the key condition on the default expression?

### Exercise 7. Version Behavior

A table has 500 million rows. How might ADD COLUMN region text DEFAULT 'APAC' behave differently on PostgreSQL 10 versus PostgreSQL 16?

### Exercise 8. Volatile Default

Why can ADD COLUMN random_key double precision DEFAULT random() rewrite the table even on PostgreSQL 16?

### Exercise 9. now vs. clock_timestamp

Why can default now() use fast default while clock_timestamp() cannot?

### Exercise 10. Catalog

What information do atthasmissing and attmissingval provide?

### Exercise 11. Locks

Why can a fast-default ADD COLUMN still wait a long time in production?

### Exercise 12. Lock Timeout

Write an example setting a 2-second lock_timeout and a 1-minute statement_timeout before ALTER TABLE.

### Exercise 13. NOT NULL

Why does adding a NOT NULL column without a default to a populated table usually fail?

### Exercise 14. NOT VALID

Does CHECK NOT VALID check existing rows immediately at ADD CONSTRAINT time? Does it enforce new rows?

### Exercise 15. VALIDATE

After backfilling, which command validates historical rows?

### Exercise 16. CHECK NULL

Why does CHECK (amount > 0) not replace NOT NULL?

### Exercise 17. Backfill

State three reasons for splitting a backfill UPDATE into independently committed batches.

### Exercise 18. Expand-Contract

Describe the order of expand, deploy, backfill, validate, and contract when adding a mandatory column for an application.

### Exercise 19. Generated Columns

Why does the fast-default assumption not apply to stored generated columns?

### Exercise 20. Partitioning

When adding a column to a partitioned parent, what should you check on child partitions?

### Exercise 21. Replication

How can a large table rewrite affect standbys and WAL archiving?

### Exercise 22. Schema Drift

Why is ADD COLUMN IF NOT EXISTS insufficient to guarantee an idempotent migration?

### Exercise 23. Compatibility

Design a way to add a source_system column defaulting to 'legacy' for an application supporting both PostgreSQL 10 and 16.

### Exercise 24. Historical Values

If each row needs a new value derived from created_at, why should you not use a constant default?

### Exercise 25. Production Evidence

List at least eight pieces of information to record when deploying ADD COLUMN on a large table.

## 19. Suggested Answers

### Answer 1

```sql
ALTER TABLE public.customers
ADD COLUMN preferred_name text;
```

### Answer 2

```sql
ALTER TABLE public.customers
ADD COLUMN is_enabled boolean DEFAULT true;
```

Historical rows see `true`. New `INSERT`s omitting `is_enabled` also receive `true`; an explicit `NULL` still stores `NULL` if the column is nullable.

### Answer 3

- Omitting the column: PostgreSQL uses the default if present, otherwise `NULL`.
- Passing `DEFAULT`: requests evaluation of the default expression.
- Passing `NULL`: stores `NULL` without triggering the default.

### Answer 4

No. `SET DEFAULT` only changes the expression for future `INSERT`/`UPDATE` statements when the column is omitted or `DEFAULT` is specified. Historical rows are not updated.

### Answer 5

- `now()`: `STABLE`.
- `clock_timestamp()`: `VOLATILE`.
- `random()`: `VOLATILE`.
- `nextval()`: `VOLATILE`.

### Answer 6

PostgreSQL 11 introduced fast default for `ADD COLUMN` with non-volatile default expressions.

### Answer 7

PostgreSQL 10 normally rewrites the heap to materialize the default on historical rows. PostgreSQL 16 can store missing-value metadata and avoid rewriting the heap solely for the constant default. Both still require locks.

### Answer 8

`random()` is volatile; every historical row needs its own value, so PostgreSQL must compute and store those values during a rewrite.

### Answer 9

`now()` is stable and returns the same transaction timestamp; `clock_timestamp()` is volatile and can change between calls. Fast default only applies to non-volatile expressions.

### Answer 10

`atthasmissing` indicates whether a column has missing-value metadata; `attmissingval` stores the logical value for old tuples lacking the physical attribute.

### Answer 11

`ALTER TABLE` still requires `ACCESS EXCLUSIVE`. Long transactions or other lock holders can block the migration from acquiring the lock even when the catalog update itself is instantaneous.

### Answer 12

```sql
SET lock_timeout = '2s';
SET statement_timeout = '1min';
ALTER TABLE public.customers ADD COLUMN source text;
```

### Answer 13

Existing rows have no value for the new column and would receive `NULL`. `NOT NULL` forbids `NULL`, so PostgreSQL rejects it without a suitable default or backfill workflow.

### Answer 14

`NOT VALID` skips validating historical rows at `ADD CONSTRAINT` time, but the constraint is still enforced for newly inserted and subsequently updated rows.

### Answer 15

```sql
ALTER TABLE public.customers
VALIDATE CONSTRAINT customers_tier_present;
```

### Answer 16

`CHECK` only rejects expressions evaluating to `FALSE`; if an expression evaluates to `NULL`, the row passes. `NOT NULL` must be added separately to forbid `NULL`.

### Answer 17

Batch commits release row locks, avoid overly long transactions and snapshots, and help control WAL, replica lag, autovacuum, and application latency.

### Answer 18

1. Expand: add a nullable column and compatible default.
2. Deploy: new app reads/writes the column while handling historical `NULL`s.
3. Backfill: update old rows in batches.
4. Validate: `CHECK NOT VALID`, `VALIDATE`, `SET NOT NULL`.
5. Contract: remove compatibility code/legacy columns once all writers have switched.

### Answer 19

A stored generated column must compute its value from each row's data and store the result. Adding one to a populated table can require a rewrite; it is not a single constant missing value.

### Answer 20

Check partition counts, child schemas, defaults/constraints, attached/detached partitions, schema drift, and locks across all children.

### Answer 21

Rewrites/backfills can generate heavy WAL. Standbys must replay that WAL so lag can rise; archive backlogs and replication slot retention can also grow WAL disk usage.

### Answer 22

`IF NOT EXISTS` only ignores duplicate column name errors; it does not check the type, default, nullability, collation, or constraints of an existing column.

### Answer 23

Use a cross-version-compatible strategy: `ADD COLUMN` nullable without a default, `SET DEFAULT 'legacy'` for new `INSERT`s, deploy compatible writers, backfill historical rows in batches, validate, and `SET NOT NULL` if needed. PostgreSQL 16 can use fast default directly if `'legacy'` fits all historical rows, though a shared migration recipe is easier to manage.

### Answer 24

A constant default gives all historical rows the same value; business rules require values derived from each row's `created_at`, so you must backfill with an expression over per-row data.

### Answer 25

Examples: `server_version_num`, migration command, table/TOAST/index sizes, start/end times, lock wait, blocking transactions, WAL bytes, archive lag, replica lag, null count, constraint validation state, and application errors.

## 20. ADD COLUMN Deployment Checklist

### 20.1. Before migration

1. Check `server_version_num` on the target.
2. Check table size, TOAST size, index size, and partition count.
3. Identify the default expression and its volatility.
4. Decide whether historical rows share one value or need per-row values.
5. Determine whether the column requires `NOT NULL`.
6. Check application versions and rolling deployment compatibility.
7. Check for long-running transactions and lock holders.
8. Evaluate disk, WAL, archive, and replica headroom.
9. Test on staging with comparable data.
10. Prepare `lock_timeout`, `statement_timeout`, and rollback/forward-fix plans.

### 20.2. During migration

11. Use schema-qualified table names.
12. Keep DDL transactions short.
13. Separate DDL from long batch backfills.
14. Monitor lock waits and blockers.
15. Monitor WAL, replica lag, and disk.
16. Do not retry in a tight loop on lock timeouts.
17. Record command, duration, and server version.

### 20.3. After migration

18. Verify column type, default, and nullability.
19. Verify both historical and new rows.
20. Verify constraint state and validation.
21. Test application `INSERT`/`UPDATE`/`SELECT`.
22. Check replicas and WAL archiving.
23. Record relation sizes and evidence.
24. Contract/drop legacy schema only when no old consumers remain.

## 21. Runbook: Handling Slow or Failed Migrations

### Step 1. Determine state

Check whether the migration session is still running, waiting on a lock, or has failed. Inspect errors, `wait_event`, query age, and transaction state.

### Step 2. Check version and operation

Confirm server major version, default volatility, and whether any subcommand forces a rewrite. Cross-check against the migration plan.

### Step 3. Find blockers

Use `pg_stat_activity`, `pg_locks`, and `pg_blocking_pids`. Identify the transaction owner, transaction age, and impact of canceling.

### Step 4. Assess resource pressure

If rewriting or backfilling, check CPU, I/O, disk, WAL, archiving, and replication lag. Pause batch jobs if thresholds are exceeded.

### Step 5. Choose action

- Lock wait: cancel migration cleanly, resolve the blocker, retry with backoff.
- Heavy rewrite: abort if the impact is unacceptable; replan by version with staged backfills.
- Backfill lag: shrink batch size or pause, wait for replicas to catch up.
- Constraint validation failure: locate and fix violating rows per business rules.
- Application errors: roll back feature flags/code rollout or apply a forward-fix compatible schema.

### Step 6. Verify

Verify schema/catalogs, null counts, constraints, application behavior, and replicas after retrying.

### Step 7. Record incident

Save the timeline, version, lock blockers, DDL, WAL/replica metrics, backfilled data progress, and corrective actions.

## 22. Summary

Adding columns in PostgreSQL is a schema change whose semantics and costs depend on version. PostgreSQL 11 introduced fast default for `ADD COLUMN` with non-volatile default expressions: historical rows read the missing value from catalog metadata without rewriting the heap solely for the default. PostgreSQL 10 and earlier normally rewrite the table when adding a non-`NULL` default to a populated table.

Key principles to remember:

- `DEFAULT` applies when `INSERT` omits the column or passes `DEFAULT`; explicit `NULL` does not use the default.
- `SET DEFAULT` does not update historical rows; `DROP DEFAULT` does not erase existing values.
- `now()` is stable; `clock_timestamp()`, `random()`, and `nextval()` are volatile.
- Volatile defaults require per-row evaluation for historical rows and can force table rewrites even on PostgreSQL 11+.
- Fast default still requires an `ACCESS EXCLUSIVE` lock; lock waits can pose a greater risk than execution time.
- `NOT NULL` requires all historical and new rows to hold non-`NULL` values.
- `CHECK NOT VALID` defers historical validation; `VALIDATE CONSTRAINT` verifies after backfilling.
- A validated `CHECK` constraint can help `SET NOT NULL` avoid a redundant table scan on supported versions.
- Large table backfills should be batched, committed independently, and monitored for WAL and replica lag.
- Expand-contract keeps rolling deployments compatible between old code and new schemas.
- Stored generated columns, identity columns, partitions, type changes, and extensions require version-specific behavior checks.
- Check `server_version_num` on the target; the `psql` client version does not govern DDL behavior.
- Test on production-like datasets and preserve lock/resource evidence.

Practical rule of thumb:

> **Before adding a column, determine the values required for historical rows, the volatility of the default, the server version, and lock impact; then choose a migration strategy suited to your data and application rollout.**

## 23. References

Prefer documentation matching the running major version:

- [PostgreSQL ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): `ADD COLUMN`, `SET`/`DROP DEFAULT`, `SET NOT NULL`, `CHECK`, and `NOT VALID`.
- [PostgreSQL 11 Release Notes](https://www.postgresql.org/docs/11/release-11.html): fast default optimization for `ADD COLUMN`.
- [PostgreSQL 10 ALTER TABLE](https://www.postgresql.org/docs/10/sql-altertable.html): `ALTER TABLE` behavior before fast default.
- [PostgreSQL 11 ALTER TABLE](https://www.postgresql.org/docs/11/sql-altertable.html): version introducing fast default.
- [PostgreSQL 12 ALTER TABLE](https://www.postgresql.org/docs/12/sql-altertable.html): generated columns and version-specific constraint behavior.
- [Function Volatility Categories](https://www.postgresql.org/docs/current/xfunc-volatility.html): `IMMUTABLE`, `STABLE`, and `VOLATILE`.
- [System Catalogs — pg_attribute](https://www.postgresql.org/docs/current/catalog-pg-attribute.html): column metadata.
- [System Catalogs — pg_constraint](https://www.postgresql.org/docs/current/catalog-pg-constraint.html): constraint validation metadata.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): table-level lock modes and conflicts.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity`, `pg_locks`, and wait events.
- [PostgreSQL Generated Columns](https://www.postgresql.org/docs/current/ddl-generated-columns.html): generated-column semantics and restrictions.
- [PostgreSQL Identity Columns](https://www.postgresql.org/docs/current/ddl-identity-columns.html): identity/sequence behavior.
- [PostgreSQL Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html): partitioned tables and partitions.
- [PostgreSQL Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): dead tuples, autovacuum, and table maintenance.
