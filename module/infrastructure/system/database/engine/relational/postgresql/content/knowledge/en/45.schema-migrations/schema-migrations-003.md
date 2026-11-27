# ALTER TABLE, Lock Levels, and Table Rewrite Operations in PostgreSQL

`ALTER TABLE` is one of the most frequently used DDL commands for modifying a PostgreSQL schema. It can add or drop columns, change data types, set defaults, add constraints, change ownership, move tablespaces, and alter partition structures. These changes have vastly different costs: some only update catalog metadata, some must scan the entire table, some must rebuild indexes, and some must rewrite the entire physical table data.

When running in production, the critical question is not just whether the statement is syntactically valid. You must know **which lock the command acquires, how long the lock is held, whether it blocks reads/writes, whether it scans or rewrites the table, how much extra disk/WAL it requires, how it affects replicas, and whether it can be rolled out in phases**.

This lesson belongs to the **Schema Migrations** chapter and focuses on:

- The structure and common forms of `ALTER TABLE`.
- PostgreSQL table lock modes and the lock level of each operation group.
- Differences between metadata-only, table scan, index build, and table rewrite.
- The impact of defaults, data type changes, constraints, and column removal.
- How to safely add constraints using `NOT VALID` and `VALIDATE CONSTRAINT`.
- How to build indexes concurrently and attach an index as a primary/unique constraint.
- Partition attach/detach and their impact on parent/child tables.
- Lock queues, blocking sessions, timeouts, and transaction duration.
- Disk space, WAL, replication lag, and MVCC caveats during rewrites.
- Expand-contract migrations, batched backfills, and rollback-capable rollouts.
- Monitoring, migration runbook, and hands-on exercises.

> **Operational principle:** a metadata-only operation can still require a strong lock. "No table rewrite" does not mean "non-blocking." Conversely, an operation that scans the table does not necessarily rewrite data. Separate lock behavior, scan cost, rewrite cost, and transaction duration when evaluating a migration.

## 1. How Does ALTER TABLE Work?

`ALTER TABLE` changes the definition of a table or a partitioned table. PostgreSQL stores schema definitions in system catalogs, while table data and indexes reside in separate storage relations.

A statement may perform one or more tasks:

1. Validate the object, privileges, and validity of the change.
2. Acquire locks on the table and potentially on related relations.
3. Update catalog metadata.
4. Scan existing data to verify constraints or convert values.
5. Create, drop, or rebuild indexes.
6. Rewrite table storage if the physical layout or data representation needs to change.
7. Update dependencies and related metadata.
8. Hold locks until the transaction ends.

### 1.1. Basic Syntax

```sql
ALTER TABLE [ ONLY ] table_name
    action [, ... ];
```

`table_name` should be schema-qualified in migrations:

```sql
ALTER TABLE app.orders
    ADD COLUMN source_code text;
```

Actions can be combined in a single command. However, combining multiple changes does not automatically make a migration faster or safer. A single command containing multiple subcommands may have to acquire the strongest lock required by any subcommand and perform multiple pieces of work within the same transaction.

### 1.2. ONLY and Inheritance/Partitioning

PostgreSQL supports table inheritance and declarative partitioning. For a parent table, an ALTER TABLE operation usually applies recursively to descendants when syntax permits.

- `ALTER TABLE parent ...` usually modifies the parent and related child tables/partitions.
- `ALTER TABLE ONLY parent ...` restricts the change to the parent itself.
- Some actions cannot be applied to the parent alone if doing so would make the schema incompatible with children.
- Some operations have specific restrictions on partitioned tables.

Before running DDL on a large parent table, determine the partition count, child table states, and lock behavior across the entire hierarchy. A command that looks like it touches a single relation may require locks on many relations.

### 1.3. A Single ALTER TABLE Statement Can Contain Multiple Actions

For example:

```sql
ALTER TABLE app.orders
    ADD COLUMN source_code text,
    ALTER COLUMN status SET DEFAULT 'pending';
```

Neither action may require a table rewrite, yet the statement's lock level must still satisfy the requirements of all actions. If one action requires `ACCESS EXCLUSIVE`, do not assume the other action weakens the overall lock.

### 1.4. DDL Is Usually Transactional

Many forms of `ALTER TABLE` can run inside a transaction and roll back if the transaction fails. However, locks are held until COMMIT/ROLLBACK. A migration running inside a long transaction may continue holding locks after the DDL statement itself has completed.

Some related commands, especially `CREATE INDEX CONCURRENTLY` and `DROP INDEX CONCURRENTLY`, cannot run inside a transaction block. The migration tool must support non-transactional migrations for those operations.

## 2. Table Lock Modes

PostgreSQL uses table-level locks to coordinate concurrent operations. The lock mode determines whether an operation can run concurrently with reads, writes, or other DDL.

### 2.1. Main Lock Modes

| Lock mode | General meaning |
| --- | --- |
| `ACCESS SHARE` | Weakest lock; typically acquired by SELECT |
| `ROW SHARE` | Typically used by SELECT ... FOR UPDATE/SHARE |
| `ROW EXCLUSIVE` | Typically acquired by INSERT, UPDATE, DELETE, and MERGE |
| `SHARE UPDATE EXCLUSIVE` | Used by certain maintenance/DDL operations; compatible with ROW EXCLUSIVE |
| `SHARE` | Allows reads but blocks ordinary writers |
| `SHARE ROW EXCLUSIVE` | Strong lock, self-conflicting, and blocks writers |
| `EXCLUSIVE` | Blocks many concurrent activities, still allows ACCESS SHARE |
| `ACCESS EXCLUSIVE` | Strongest; conflicts with every other table lock mode |

A lock name containing "ROW" does not mean it is a row-level lock. These are **table-level lock modes**. PostgreSQL also has separate row-level locks for individual tuples.

### 2.2. ACCESS SHARE

A normal SELECT acquires `ACCESS SHARE`. This lock allows many readers and writers to operate concurrently, but it is blocked by `ACCESS EXCLUSIVE`.

Therefore, an ALTER TABLE acquiring ACCESS EXCLUSIVE may wait for running SELECTs and can also cause new SELECTs to queue behind the pending DDL.

### 2.3. ROW EXCLUSIVE

Data-modifying statements such as INSERT, UPDATE, DELETE, and MERGE typically acquire `ROW EXCLUSIVE` on the modified table.

`ROW EXCLUSIVE` is compatible with several other locks, including `ACCESS SHARE` and `SHARE UPDATE EXCLUSIVE`, but is incompatible with `SHARE`, `SHARE ROW EXCLUSIVE`, `EXCLUSIVE`, and `ACCESS EXCLUSIVE`.

### 2.4. SHARE UPDATE EXCLUSIVE

`SHARE UPDATE EXCLUSIVE` is used by operations such as ordinary VACUUM, ANALYZE, CREATE INDEX CONCURRENTLY, and VALIDATE CONSTRAINT. It allows ordinary DML to continue, while preventing conflicting DDL/maintenance operations from running concurrently.

This lock is self-conflicting: two sessions requesting SHARE UPDATE EXCLUSIVE on the same table may have to wait for each other.

### 2.5. SHARE ROW EXCLUSIVE

`SHARE ROW EXCLUSIVE` blocks ordinary writers and is self-conflicting. An important example is ADD FOREIGN KEY, which may acquire this lock on both the referencing and referenced tables.

This means adding a foreign key can force writes on both tables to wait during the lock phase, even when validating old data is split into a separate VALIDATE CONSTRAINT step.

### 2.6. ACCESS EXCLUSIVE

`ACCESS EXCLUSIVE` is the strongest lock. It conflicts with every other lock mode, including ACCESS SHARE from SELECT.

Many forms of ALTER TABLE acquire ACCESS EXCLUSIVE by default. Consequently, a change that does not rewrite the table can still cause SELECT/INSERT/UPDATE/DELETE to wait for the lock.

### 2.7. Locks Are Held Until the End of the Transaction

PostgreSQL holds table locks until the transaction ends. For example:

```sql
BEGIN;

ALTER TABLE app.orders
    ADD COLUMN source_code text;

-- Other statements run here.

COMMIT;
```

The lock from ALTER TABLE may remain held while subsequent statements execute. If a migration tool opens a transaction and then executes multiple steps or waits for an external process before COMMIT, the blocking duration can be much longer than the actual DDL execution time.

### 2.8. Common Lock Levels

The table below is a practical guide for common forms; locks can vary by subcommand, version, partition hierarchy, and related objects. Always check the documentation for the running major version.

| Operation | Typical lock on table |
| --- | --- |
| Most ALTER TABLE forms | ACCESS EXCLUSIVE |
| ADD FOREIGN KEY | SHARE ROW EXCLUSIVE on involved tables |
| VALIDATE CONSTRAINT | SHARE UPDATE EXCLUSIVE |
| SET STATISTICS | SHARE UPDATE EXCLUSIVE |
| SET/RESET certain table storage parameters | SHARE UPDATE EXCLUSIVE |
| ATTACH PARTITION | SHARE UPDATE EXCLUSIVE on parent; stronger lock on attached table |
| Regular DETACH PARTITION | ACCESS EXCLUSIVE on parent and partition |
| DETACH PARTITION CONCURRENTLY | SHARE UPDATE EXCLUSIVE on parent in supported versions |
| CREATE INDEX CONCURRENTLY | SHARE UPDATE EXCLUSIVE |
| Regular VACUUM | SHARE UPDATE EXCLUSIVE |

This is not an exhaustive list. For example, a regular CREATE INDEX and many other ALTER TABLE forms have different lock behavior than a concurrent index build.

## 3. Lock Compatibility and Traffic Impact

A lock mode only makes sense when placed alongside running activities.

### 3.1. Key Interactions to Remember

| Running activity | ACCESS EXCLUSIVE DDL | SHARE UPDATE EXCLUSIVE DDL |
| --- | --- | --- |
| Regular SELECT | Blocked | Can continue |
| INSERT/UPDATE/DELETE | Blocked | Usually can continue |
| Regular VACUUM | Blocked | May conflict with same-mode operation |
| CREATE INDEX CONCURRENTLY | Blocked | Conflicts if on same table |
| Other DDL | Blocked | Depends on the DDL's lock mode |
| Another ACCESS EXCLUSIVE lock | Blocked | Blocked |

This table illustrates common cases and does not replace the official lock matrix. A single statement may touch multiple tables, so check each relation individually.

### 3.2. Metadata-Only Operations Can Still Block

For example, adding a nullable column with no default usually does not rewrite the table. However, it still requires a strong lock. If the table has a long-running transaction holding a lock, ALTER TABLE may wait.

This is why you must distinguish:

- **Rewrite cost:** whether physical table data is recreated.
- **Scan cost:** whether existing rows are read for verification.
- **Lock cost:** which lock is needed and whom it may wait on.
- **Transaction cost:** how long the lock is held.
- **Resource cost:** CPU, I/O, WAL, and disk space.

### 3.3. Lock Queue and Blocking Convoy

Suppose a long-running transaction is holding ACCESS SHARE on a table. An ALTER TABLE requesting ACCESS EXCLUSIVE enters the wait queue. Subsequent incoming SELECTs may also have to wait behind the pending strong lock request, depending on lock queue and conflict rules.

The result can be:

1. An old query holds a lock for a long time.
2. ALTER TABLE waits for ACCESS EXCLUSIVE.
3. New requests queue behind it.
4. The application connection pool fills up with waiting requests.
5. Latency spikes even on endpoints not directly related to the migration.

A DDL waiting for a lock can cause major impact before it even alters the schema.

### 3.4. DDL Should Have a Lock Timeout

Use a short timeout so the migration fails fast if it cannot acquire the lock within the allowed window:

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '5min';

ALTER TABLE app.orders
    ADD COLUMN source_code text;

COMMIT;
```

`lock_timeout` limits the wait time for each lock acquisition attempt. `statement_timeout` limits the total statement execution time. Example values must be tuned to your SLOs and deployment policy.

If a lock timeout occurs, the current transaction enters an aborted state until ROLLBACK. The migration runner must handle the error and retry the entire transaction in a controlled manner.

### 3.5. Do Not Retry Continuously Without Backoff

If DDL retries every few milliseconds, it can continuously create lock pressure. Use bounded retries with backoff and jitter; before each attempt, check blockers and workload conditions.

## 4. Metadata-Only Changes

Metadata-only changes primarily update the catalog without rewriting the entire table data. They are usually much faster on large tables, though lock acquisition remains critical.

### 4.1. ADD COLUMN Without Default

For example:

```sql
ALTER TABLE app.orders
    ADD COLUMN source_code text;
```

On modern PostgreSQL versions, adding a nullable column with no default usually only updates metadata. PostgreSQL does not have to rewrite every row to store NULL for the new column.

Characteristics:

- No full table scan needed to compute values.
- No rewrite of all table data.
- Storage for new values is written when rows are subsequently inserted or updated.
- Still requires the ALTER TABLE lock.
- Schema changes can affect application code and ORM mappings.

This is usually the least expensive way to add a column, but requires rolling out application code compatible with the new schema.

### 4.2. ADD COLUMN With a Constant Default

For example:

```sql
ALTER TABLE app.orders
    ADD COLUMN source_code text DEFAULT 'legacy';
```

Starting in PostgreSQL 11, a non-volatile default expression can be evaluated once during ALTER TABLE and stored as missing-value metadata for existing rows. In this case, PostgreSQL does not need to rewrite the entire table just to populate the default in every row.

This can make the operation vastly faster on large tables.

Keep in mind:

- The default is used for new rows.
- Existing rows read the column as the value stored in metadata.
- When a row is later rewritten, the value is materialized according to storage behavior.
- The operation still requires a lock.
- Prior to PostgreSQL 11, ADD COLUMN with a non-NULL default usually rewrote the table.

### 4.3. ADD COLUMN With a Volatile Default

For example:

```sql
ALTER TABLE app.orders
    ADD COLUMN created_token uuid DEFAULT gen_random_uuid();
```

A volatile expression can return a different value for each row. PostgreSQL must compute the value for existing rows, so a table rewrite may be required.

Functions such as `random()` or `clock_timestamp()` are examples of volatile expressions. Check the volatility classification of any function used in a default.

### 4.4. SET DEFAULT and DROP DEFAULT

```sql
ALTER TABLE app.orders
    ALTER COLUMN source_code SET DEFAULT 'unknown';

ALTER TABLE app.orders
    ALTER COLUMN source_code DROP DEFAULT;
```

Changing a default does not update existing row values and does not require a table rewrite. It changes the behavior of INSERT or UPDATE statements that omit the column according to statement semantics.

Do not confuse SET DEFAULT with running an UPDATE across all rows to assign a default value to existing data.

### 4.5. RENAME COLUMN and RENAME TABLE

```sql
ALTER TABLE app.orders
    RENAME COLUMN source_code TO origin_code;

ALTER TABLE app.orders
    RENAME TO customer_orders;
```

Renaming primarily updates catalog metadata without rewriting data. However, locks must still be acquired and the application can break immediately upon deployment if older code still references the previous name.

Renames in production should follow expand-contract: add the new structure, migrate callers, and only drop the old name once confirmed.

### 4.6. DROP COLUMN

```sql
ALTER TABLE app.orders
    DROP COLUMN legacy_code RESTRICT;
```

DROP COLUMN usually does not rewrite the table immediately. PostgreSQL marks the attribute as dropped in the catalog and stops exposing that column in normal queries.

However:

- Old physical tuple data is not immediately compacted.
- The table file size may not shrink after DROP COLUMN.
- Space may only be reused when rows are rewritten/updated or the table is rewritten by another operation.
- Dependencies can cause DROP RESTRICT to fail.
- DROP CASCADE can drop dependent objects.

Do not use DROP COLUMN expecting immediate disk usage reduction. If space reclamation is required, evaluate rewrite/repack options and downtime/lock costs separately.

### 4.7. ALTER COLUMN SET STATISTICS

For example:

```sql
ALTER TABLE app.orders
    ALTER COLUMN customer_id SET STATISTICS 500;
```

Changing the statistics target controls the level of detail the planner collects for the column. It does not rewrite the table, though ANALYZE is required for the new statistics to take effect. The lock is typically weaker than default ALTER TABLE forms on current versions.

Higher statistics targets can increase ANALYZE duration and statistics size. Only increase them for columns with clear query planning issues.

### 4.8. Storage Parameters

For example:

```sql
ALTER TABLE app.orders
    SET (fillfactor = 85);

ALTER TABLE app.orders
    RESET (fillfactor);
```

Storage parameters generally affect how rows/index pages are created or maintained in the future. Changing metadata does not automatically rewrite all existing pages to apply the new setting. Altering the layout of existing data may require a separate rewrite operation.

## 5. Operations That Must Scan the Table

A table scan reads existing rows to verify a condition. Scans can take a long time on large tables, though they do not necessarily create a new physical copy.

### 5.1. ADD CHECK Constraint

For example:

```sql
ALTER TABLE app.orders
    ADD CONSTRAINT orders_amount_nonnegative
    CHECK (total_amount >= 0);
```

When adding a constraint in the default validated state, PostgreSQL must check existing rows to confirm every row satisfies the condition. On a large table, this scan can take a long time.

### 5.2. ADD CHECK NOT VALID

You can split the work:

```sql
ALTER TABLE app.orders
    ADD CONSTRAINT orders_amount_nonnegative
    CHECK (total_amount >= 0)
    NOT VALID;
```

`NOT VALID` skips the verification scan across existing rows at ADD time. The constraint is still enforced for new rows or rows inserted/updated according to constraint semantics. Existing data remains unverified.

Afterward:

```sql
ALTER TABLE app.orders
    VALIDATE CONSTRAINT orders_amount_nonnegative;
```

VALIDATE CONSTRAINT scans existing data under a weaker lock than ACCESS EXCLUSIVE, typically SHARE UPDATE EXCLUSIVE. Ordinary DML can continue during validation, though you still need to monitor I/O, CPU, and contention.

### 5.3. SET NOT NULL

For example:

```sql
ALTER TABLE app.orders
    ALTER COLUMN customer_id SET NOT NULL;
```

PostgreSQL must verify there are no NULLs in the column. Without proof from a valid constraint, the operation may scan the table.

You can use a CHECK constraint as a preparatory step:

```sql
ALTER TABLE app.orders
    ADD CONSTRAINT orders_customer_id_not_null_check
    CHECK (customer_id IS NOT NULL)
    NOT VALID;

ALTER TABLE app.orders
    VALIDATE CONSTRAINT orders_customer_id_not_null_check;

ALTER TABLE app.orders
    ALTER COLUMN customer_id SET NOT NULL;

ALTER TABLE app.orders
    DROP CONSTRAINT orders_customer_id_not_null_check;
```

When PostgreSQL recognizes a validated CHECK constraint proving the column contains no NULLs, it can skip the full scan when setting NOT NULL. Verify this behavior on your exact major version and keep the steps in a controlled migration.

### 5.4. ADD FOREIGN KEY

For example:

```sql
ALTER TABLE app.order_items
    ADD CONSTRAINT order_items_order_fk
    FOREIGN KEY (order_id)
    REFERENCES app.orders(id);
```

A foreign key must check existing rows in the referencing table and ensure referenced keys are valid. The operation acquires SHARE ROW EXCLUSIVE locks on the involved tables per PostgreSQL behavior.

### 5.5. Foreign Key NOT VALID

```sql
ALTER TABLE app.order_items
    ADD CONSTRAINT order_items_order_fk
    FOREIGN KEY (order_id)
    REFERENCES app.orders(id)
    NOT VALID;
```

Then validate:

```sql
ALTER TABLE app.order_items
    VALIDATE CONSTRAINT order_items_order_fk;
```

This separates the lock/setup phase from the scan of existing data. The constraint is still enforced for new data according to foreign key semantics. Ensure the application does not continue creating orphan rows during rollout.

### 5.6. Adding NOT NULL via CHECK NOT VALID

PostgreSQL does not have the same `NOT VALID` syntax directly on a NOT NULL constraint. The CHECK constraint pattern enables a safer rollout:

1. Add CHECK (column IS NOT NULL) NOT VALID.
2. Deploy code ensuring all new writes include a value.
3. Backfill existing NULLs in batches.
4. VALIDATE CONSTRAINT.
5. ALTER COLUMN SET NOT NULL.
6. DROP the auxiliary CHECK constraint.

The order may need adjustment depending on how the application writes data and its transaction model. Do not skip handling existing rows.

## 6. Operations That Must Rewrite the Table

A table rewrite creates new physical storage for the table or converts the representation of rows. This is usually the most expensive category of operation on large tables.

### 6.1. ALTER COLUMN TYPE

For example:

```sql
ALTER TABLE app.orders
    ALTER COLUMN external_id TYPE bigint
    USING external_id::bigint;
```

Changing a data type usually requires a table rewrite if the representations of the old and new types are not binary-coercible. The USING expression is evaluated for every row to produce the new value.

Impacts may include:

- Reading the entire table.
- Evaluating the expression for each row.
- Rewriting table storage.
- Rebuilding related indexes as needed.
- Generating WAL and replication traffic.
- Requiring disk space for old and new storage to coexist during the rewrite.
- Holding a strong lock for the duration of the operation.

### 6.2. When Can a TYPE Change Avoid a Rewrite?

If the old type and new type are binary-coercible and require no change in physical representation, PostgreSQL may only update metadata. For example, certain conversions between compatible types may not require a rewrite.

Do not infer this solely from whether two types can cast to each other. Cast compatibility does not equate to binary coercibility. Check the type conversion documentation and test on a data clone of comparable size.

### 6.3. USING Expression

`USING` allows transforming data:

```sql
ALTER TABLE app.events
    ALTER COLUMN event_time TYPE timestamptz
    USING event_time AT TIME ZONE 'UTC';
```

The expression must be valid for every row. A single unconvertible row can fail the entire ALTER TABLE. Preflight with a SELECT of the expression over the data, identify invalid values, and verify timezone semantics before running DDL.

`USING` does not automatically convert a column's default expression. If the old default cannot cast to the new type, you may need to DROP DEFAULT first, change the type, and then SET DEFAULT to the new value.

### 6.4. SET LOGGED and SET UNLOGGED

```sql
ALTER TABLE app.stage_data SET UNLOGGED;
ALTER TABLE app.stage_data SET LOGGED;
```

Changing persistence mode can require a table rewrite. UNLOGGED tables are not protected by WAL in the way logged tables are and are truncated after crash/recovery per PostgreSQL semantics. Do not use UNLOGGED for data requiring durability/replication such as core business tables.

### 6.5. SET TABLESPACE

```sql
ALTER TABLE app.orders
    SET TABLESPACE fast_storage;
```

Moving a table to another tablespace requires copying physical data and may move associated indexes per command semantics. It requires disk capacity at the destination, I/O bandwidth, and lock hold time. Tablespaces are not a substitute for partitioning or workload isolation.

### 6.6. SET ACCESS METHOD

On supported PostgreSQL versions:

```sql
ALTER TABLE app.events
    SET ACCESS METHOD heap;
```

Changing the table access method requires rewriting storage. This operation requires careful evaluation of compatibility, extension support, index methods, and operational impact.

### 6.7. CLUSTER and VACUUM FULL

These are not standard ALTER TABLE forms, but belong to the rewrite category:

- `CLUSTER` reorders the table according to a chosen index and rewrites the table.
- `VACUUM FULL` creates a compacted copy and requires an ACCESS EXCLUSIVE lock.
- Some repacking tools use a shadow table or swap strategy to reduce downtime, though they still require disk, WAL, and lock phases.

Do not run these operations simply because a table is large. Assess bloat, free space reuse, workload, and maintenance windows first.

### 6.8. A Rewrite Is Not Just "UPDATE All Rows"

A rewrite alters the physical relation storage. It can create a new relfilenode and update catalog references. A full-table UPDATE also creates new row versions, but has different semantics, WAL, vacuum, and lock behavior. Do not treat the two operations as equivalent.

## 7. Estimating Table Rewrite Cost

Before changing a type or moving a tablespace, estimate the resources required.

### 7.1. Disk Space

Suppose:

- Current table is 80 GiB.
- Indexes are 35 GiB.
- Rewrite must create a new table.
- Indexes must be rebuilt.

During the operation, old and new files can coexist. Peak disk demand can exceed the final total size because temporary headroom, WAL, and concurrent activities are also needed.

A conservative envelope:

```text
peak_free_space_needed ≈
    new_table_copy
  + rebuilt_indexes
  + WAL_growth
  + temporary_working_space
  + safety_headroom
```

This is an estimation model, not a fixed formula. Measure on a clone with similar data volume and index layout.

### 7.2. WAL Generation

Logged table rewrites generate WAL. WAL can increase:

- pg_wal disk usage.
- Archive volume.
- Replication traffic.
- Replica replay lag.
- Backup/archive storage costs.

If replicas fall behind, queries on replicas may observe stale data for an extended period.

### 7.3. CPU and I/O

A rewrite can read the entire old table, evaluate expressions, write the new table, and rebuild indexes. It competes with OLTP workloads for the same CPU, storage, and memory.

### 7.4. Replica Impact

Monitor:

- WAL bytes generated.
- Replication lag by time/bytes.
- Replica replay rate.
- Disk usage on primary and replicas.
- Query latency on replicas.
- Replication slot retained WAL.

A replication slot retains WAL not yet acknowledged by its consumer; if a replica or consumer lags for a long time, the primary can accumulate WAL and disk usage will climb.

### 7.5. Backup and Archive Impact

WAL archives and base backups can grow significantly after a rewrite. If using incremental backups or storage snapshots, assess the volume of changed blocks and backup duration.

### 7.6. Lock Duration Is Part of the Cost

If an operation holds ACCESS EXCLUSIVE throughout the rewrite, application traffic may be blocked. For major changes, consider expand-contract or shadow-table migration to transfer data outside a long lock window, then swap during a brief, controlled window.

## 8. MVCC and Table Rewrites

PostgreSQL uses MVCC so transactions see a consistent snapshot. Certain rewrite operations carry an important caveat: table rewrites are not MVCC-safe with respect to transactions holding older snapshots.

### 8.1. Old Snapshots

When a table is rewritten, the new physical storage may not retain row versions according to the visibility rules of a snapshot taken before the rewrite. A long-running transaction that took a snapshot before the DDL may observe the table as empty after the rewrite, per documented behavior.

This is especially important for long-running transactions, repeatable read/serializable sessions, or application workflows that hold transactions open while a migration runs.

### 8.2. Reducing Risk

- Avoid table rewrites when long-running transactions are active.
- Check transaction age before the migration.
- Use lock_timeout to fail fast if blockers exist.
- Choose a maintenance window with an appropriate workload.
- Coordinate with the application regarding transaction boundaries.
- Use staged migrations when you need to avoid a direct rewrite.

### 8.3. Finding Long-Running Transactions

```sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    xact_start,
    now() - xact_start AS transaction_age,
    state,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Do not terminate a transaction solely because it is old. Identify the owner, business operation, and rollback impact before taking action.

## 9. Safer ADD UNIQUE / PRIMARY KEY

Unique and primary key constraints generally require a unique index. Creating the index directly inside ADD CONSTRAINT can scan the table and hold a strong lock.

### 9.1. Adding the Constraint Directly

```sql
ALTER TABLE app.customers
    ADD CONSTRAINT customers_email_key
    UNIQUE (email);
```

PostgreSQL creates the required unique index and validates the data. If the table is large, the lock duration can impact reads and writes.

### 9.2. Creating the Unique Index Concurrently

You can create the index separately:

```sql
CREATE UNIQUE INDEX CONCURRENTLY customers_email_uidx
    ON app.customers (email);
```

A concurrent build allows ordinary INSERT/UPDATE/DELETE operations to continue for most of the build, but:

- Requires multiple scans and phases waiting for transactions.
- Consumes CPU, I/O, and disk.
- Can take longer when old transactions or snapshots are held open.
- Cannot run inside a transaction block.
- Can fail and leave behind an invalid index requiring cleanup.

### 9.3. Attaching the Index as a Constraint

Once the index is valid and meets requirements, it can be attached as a unique constraint:

```sql
ALTER TABLE app.customers
    ADD CONSTRAINT customers_email_key
    UNIQUE USING INDEX customers_email_uidx;
```

The attach command generally only updates metadata and holds the required lock for much less time than building the index. The index must meet PostgreSQL's requirements: suitable for a unique constraint, not a partial or expression index, and using an appropriate index method/order. If adding a PRIMARY KEY, the columns must already be confirmed NOT NULL.

### 9.4. Primary Keys and NOT NULL

A unique index permits multiple NULLs per unique constraint semantics. A primary key requires NOT NULL. If the column is currently nullable, handle NULLs and set NOT NULL before or during primary key creation.

You can use CHECK NOT VALID + VALIDATE + SET NOT NULL to separate the scan from the strong lock step, then create the unique index concurrently and attach it.

### 9.5. Failed Concurrent Builds

If CREATE INDEX CONCURRENTLY fails, an index with `indisvalid = false` may remain. An invalid index is not normally used by the planner, but may still incur write overhead depending on its state.

Check:

```sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    i.relname AS index_name,
    x.indisvalid,
    x.indisready,
    pg_get_indexdef(x.indexrelid) AS definition
FROM pg_index AS x
JOIN pg_class AS i
    ON i.oid = x.indexrelid
JOIN pg_class AS t
    ON t.oid = x.indrelid
JOIN pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE NOT x.indisvalid
   OR NOT x.indisready;
```

If you need to remove an invalid index, confirm the build has stopped and check dependencies first. DROP INDEX CONCURRENTLY may be appropriate, but must run outside a transaction block and cannot drop an index currently backing a constraint.

## 10. ADD FOREIGN KEY and Indexes on the Referencing Table

A foreign key does not automatically create an index on the referencing table's columns. An index may be needed for query joins or so PostgreSQL can efficiently check deletes/updates on referenced rows.

### 10.1. Adding the Foreign Key

```sql
ALTER TABLE app.order_items
    ADD CONSTRAINT order_items_order_fk
    FOREIGN KEY (order_id)
    REFERENCES app.orders(id)
    NOT VALID;
```

After cleaning up old data and verifying writes:

```sql
ALTER TABLE app.order_items
    VALIDATE CONSTRAINT order_items_order_fk;
```

### 10.2. Index on Referencing Columns

For example:

```sql
CREATE INDEX CONCURRENTLY order_items_order_id_idx
    ON app.order_items (order_id);
```

This index is not syntactically required by the foreign key, but can reduce the cost of deleting/updating referenced rows and joining from child to parent.

### 10.3. Choosing Column Order

If a foreign key spans multiple columns, index column order should be based on query patterns. A composite index can support prefix predicates; do not create an index strictly in constraint column order without reviewing the workload.

## 11. Partition Operations

Partitioned tables have a parent relation and multiple child partitions. Certain schema changes must be applied consistently across the entire hierarchy.

### 11.1. ATTACH PARTITION

For example:

```sql
ALTER TABLE app.events
    ATTACH PARTITION app.events_2026_11
    FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
```

ATTACH PARTITION must verify that data in the attached table conforms to the partition bounds. If PostgreSQL must scan the table to verify this, the operation can run long and acquire significant locks.

### 11.2. CHECK Constraint to Avoid Validation Scans

You can create a matching CHECK constraint on the candidate table beforehand:

```sql
ALTER TABLE app.events_2026_11
    ADD CONSTRAINT events_2026_11_bounds_check
    CHECK (
        created_at >= timestamp '2026-11-01'
        AND created_at < timestamp '2026-12-01'
    );
```

If PostgreSQL recognizes the constraint as proving the partition bounds, ATTACH can avoid scanning the table. The constraint must match the partition key/bounds accurately; do not assume an arbitrary expression will be recognized.

### 11.3. DETACH PARTITION

Standard:

```sql
ALTER TABLE app.events
    DETACH PARTITION app.events_2026_01;
```

Detaching typically requires strong locks on both the parent and the partition. Supported versions provide `DETACH PARTITION CONCURRENTLY` to reduce locking on the parent, subject to restrictions and a pending-detach phase.

### 11.4. DETACH PARTITION CONCURRENTLY

```sql
ALTER TABLE app.events
    DETACH PARTITION app.events_2026_01 CONCURRENTLY;
```

This command cannot run inside a transaction block and has restrictions regarding default partitions and detach state. After detaching concurrently, a pending-detach phase must be finalized with the appropriate command if the operation is interrupted. Check the documentation for your exact version before automating.

### 11.5. ALTER Parent and Child Locks

Changing a column or constraint on a partitioned parent may require updating child partitions. The greater the number of partitions, the more locks and catalog operations are needed.

Test the migration on staging with a partition count comparable to production, not just on a single small table.

## 12. Lock Monitoring Before and During Migration

Migrations must be observed like any production workload.

### 12.1. Running or Waiting Sessions

```sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    now() - query_start AS query_age,
    left(query, 500) AS query_sample
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start NULLS LAST;
```

`wait_event_type = 'Lock'` indicates the backend is waiting on a lock. An active session is not necessarily consuming CPU; it may be waiting on a resource.

### 12.2. Finding Blocking PIDs

```sql
SELECT
    a.pid AS blocked_pid,
    a.application_name AS blocked_app,
    a.usename AS blocked_user,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    now() - a.query_start AS blocked_duration,
    left(a.query, 400) AS blocked_query
FROM pg_stat_activity AS a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.query_start;
```

Then look up the blocking PIDs in pg_stat_activity to find the transaction owner, age, and query. A blocker may be idle in transaction, meaning its current query text is not the statement that acquired the lock.

### 12.3. Reading pg_locks

```sql
SELECT
    l.pid,
    l.locktype,
    l.relation::regclass AS relation,
    l.mode,
    l.granted,
    a.application_name,
    a.state,
    a.xact_start,
    left(a.query, 300) AS query_sample
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE l.relation IS NOT NULL
ORDER BY l.granted, l.pid, l.relation;
```

`granted = false` indicates a waiting lock. The lock relation displays the relation OID; for some lock types, relation may be NULL or not applicable.

### 12.4. Checking Long-Running Transactions

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 300) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Long-running transactions can prevent DDL from acquiring locks and hold snapshots that affect vacuum/rewrites. Coordinate with the application owner before canceling or terminating.

### 12.5. pg_blocking_pids

`pg_blocking_pids(pid)` is a convenient helper for finding direct blockers. For long lock chains, traverse from blocked sessions to blocker sessions to identify the root blocker.

## 13. Timeouts and Migration Transaction Design

Timeouts limit how long a migration waits and prevent request queues from growing unboundedly.

### 13.1. lock_timeout

`lock_timeout` limits how long a statement waits on each lock acquisition attempt. For example:

```sql
SET lock_timeout = '2s';
```

If the lock is not acquired within this time, the statement fails. It can be set at the session level or using SET LOCAL inside a transaction.

### 13.2. statement_timeout

`statement_timeout` limits total statement execution time. For large validations or index builds, choose a timeout based on expected duration and rollback behavior.

### 13.3. idle_in_transaction_session_timeout

A migration runner should not open a transaction and leave the session idle for long. This timeout can terminate sessions idle in transaction, though it must be coordinated with the migration framework and workload.

### 13.4. Where Does NOWAIT Apply?

Not every ALTER TABLE form supports NOWAIT. If you need to test lock acquisition without waiting, you can use LOCK TABLE with NOWAIT inside a transaction to preflight lock availability:

```sql
BEGIN;
LOCK TABLE app.orders IN ACCESS EXCLUSIVE MODE NOWAIT;
ROLLBACK;
```

A preflight only checks at a single point in time; another session could acquire a lock immediately after the rollback. Therefore, it does not replace lock_timeout in the actual migration.

### 13.5. One DDL Statement in a Short Transaction

Keep DDL transactions short:

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10min';

ALTER TABLE app.orders
    ADD COLUMN source_code text;

COMMIT;
```

Avoid inserting network calls, manual waits, or unrelated steps before COMMIT.

### 13.6. Do Not Mix Concurrent Indexing into a Transaction

A migration containing CREATE INDEX CONCURRENTLY must run in non-transactional mode:

```sql
CREATE INDEX CONCURRENTLY orders_created_at_idx
    ON app.orders (created_at);
```

The migration framework must mark this migration as non-transactional. If the framework wraps all scripts in BEGIN/COMMIT automatically, the command will fail.

## 14. Expand-Contract Migrations

For applications requiring high uptime, large schema changes should be split across multiple backward-compatible releases.

### 14.1. Expand

Add the new structure so old code continues working:

```sql
ALTER TABLE app.customers
    ADD COLUMN display_name_v2 text;
```

If the column is nullable with no default, the operation is usually metadata-only on modern PostgreSQL.

### 14.2. Deploy Dual-Write or Compatibility Code

The application can write to both old and new columns during a transition phase. If data must stay synchronized, have a strategy for race conditions and transaction consistency.

### 14.3. Batched Backfill

Do not update tens of millions of rows in a single transaction if it can be broken down. For example, using primary key ranges:

```sql
UPDATE app.customers
SET display_name_v2 = display_name
WHERE id >= 1
  AND id < 10001
  AND display_name_v2 IS NULL;
```

Iterate over ranges and commit each batch. Benchmark batch sizes against WAL, locks, replica lag, and autovacuum.

Another approach uses a CTE and SKIP LOCKED so multiple workers share the row workload:

```sql
WITH batch AS (
    SELECT id
    FROM app.customers
    WHERE display_name_v2 IS NULL
    ORDER BY id
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
UPDATE app.customers AS c
SET display_name_v2 = c.display_name
FROM batch
WHERE c.id = batch.id;
```

The worker must loop until no matching rows remain. If concurrent writers continue creating new rows, dual-write or trigger/compatibility logic must ensure no gaps occur.

### 14.4. Validate

Once the backfill finishes, verify:

```sql
SELECT count(*) AS remaining_rows
FROM app.customers
WHERE display_name IS NOT NULL
  AND display_name_v2 IS NULL;
```

Then add/validate required constraints or indexes.

### 14.5. Switch Reads

Deploy application code reading from the new column. Monitor error rates, data consistency, and query plans. Keep the old column during the rollback window.

### 14.6. Contract

Once no code reads or writes the old column, drop the old structures in a separate release:

```sql
ALTER TABLE app.customers
    DROP COLUMN display_name RESTRICT;
```

Dropping a column does not necessarily reclaim disk space immediately. The goal of contraction is removing the old schema contract; reclaiming storage is a separate decision.

### 14.7. Why Not Change the Type Immediately?

If ALTER COLUMN TYPE requires rewriting a large table, expand-contract lets you create a new column, backfill gradually, and switch the application. This increases complexity and temporarily increases storage, but reduces the duration of strong locks on the main table.

## 15. Phased Data Type Changes

For example, changing `varchar` to `bigint` when numbers are stored as text.

### 15.1. Preflight the Data

```sql
SELECT external_id
FROM app.orders
WHERE external_id IS NOT NULL
  AND external_id !~ '^[0-9]+$'
LIMIT 100;
```

Check for range overflow:

```sql
SELECT external_id
FROM app.orders
WHERE external_id ~ '^[0-9]+$'
  AND external_id::numeric > 9223372036854775807
LIMIT 100;
```

Do not cast all rows directly before verifying format and range. Unexpected data can cause DDL to fail after scanning most of the table.

### 15.2. Direct ALTER TYPE

If the table is small and the maintenance window allows:

```sql
ALTER TABLE app.orders
    ALTER COLUMN external_id TYPE bigint
    USING NULLIF(external_id, '')::bigint;
```

Assess defaults, indexes, constraints, views, function signatures, and application serialization beforehand.

### 15.3. Expand-Contract With a New Column

For large tables:

1. ADD COLUMN external_id_bigint bigint.
2. Deploy dual-write code.
3. Backfill in batches.
4. Validate consistency.
5. Create indexes concurrently.
6. Switch reads to the new column.
7. Stop writes to the old column.
8. Drop the old column after a deprecation window.

### 15.4. Consistency Check

```sql
SELECT count(*) AS mismatched_rows
FROM app.orders
WHERE external_id_bigint IS DISTINCT FROM
      NULLIF(external_id, '')::bigint;
```

Only run the cast in the consistency query once you have ensured the data is convertible; otherwise the query may error out. For dirty data, use guarded conversion or a staging column to record failing rows.

## 16. Online Constraint Addition Patterns

### 16.1. CHECK Constraint

Pattern:

```sql
ALTER TABLE app.orders
    ADD CONSTRAINT orders_amount_check
    CHECK (total_amount >= 0)
    NOT VALID;

ALTER TABLE app.orders
    VALIDATE CONSTRAINT orders_amount_check;
```

Separate adding from validation to minimize strong lock duration. Monitor the validation scan because it still reads data and consumes I/O.

### 16.2. Foreign Key

```sql
ALTER TABLE app.order_items
    ADD CONSTRAINT order_items_order_fk
    FOREIGN KEY (order_id)
    REFERENCES app.orders(id)
    NOT VALID;

ALTER TABLE app.order_items
    VALIDATE CONSTRAINT order_items_order_fk;
```

Ensure the referenced key has a PK/unique constraint and consider an index on the child columns for the workload.

### 16.3. NOT NULL

```sql
ALTER TABLE app.customers
    ADD CONSTRAINT customers_email_nn_check
    CHECK (email IS NOT NULL)
    NOT VALID;

ALTER TABLE app.customers
    VALIDATE CONSTRAINT customers_email_nn_check;

ALTER TABLE app.customers
    ALTER COLUMN email SET NOT NULL;

ALTER TABLE app.customers
    DROP CONSTRAINT customers_email_nn_check;
```

Ensure no writers can insert NULLs while these steps run.

### 16.4. Unique Constraint

```sql
CREATE UNIQUE INDEX CONCURRENTLY customers_external_id_uidx
    ON app.customers (external_id);

ALTER TABLE app.customers
    ADD CONSTRAINT customers_external_id_key
    UNIQUE USING INDEX customers_external_id_uidx;
```

If duplicates exist, the concurrent unique build fails. Preflight duplicates:

```sql
SELECT
    external_id,
    count(*)
FROM app.customers
WHERE external_id IS NOT NULL
GROUP BY external_id
HAVING count(*) > 1
ORDER BY count(*) DESC
LIMIT 100;
```

NULL semantics differ between UNIQUE and PRIMARY KEY. Confirm the business invariant before choosing a constraint.

## 17. Locking and Rewrites on Partitioned Tables

Partitioning increases the number of relations a migration may touch.

### 17.1. Adding a Column on the Parent

```sql
ALTER TABLE app.events
    ADD COLUMN source_system text;
```

PostgreSQL typically propagates column changes to partitions. Lock acquisition can involve the parent and child relations. A large number of partitions increases catalog and lock work.

### 17.2. ALTER TABLE ONLY

```sql
ALTER TABLE ONLY app.events
    ALTER COLUMN source_system SET DEFAULT 'api';
```

ONLY restricts the operation to the parent. However, if child tables must maintain a uniform schema, modifying only the parent can create an inconsistent state or be disallowed for certain actions.

### 17.3. Type Changes on Partitions

Changing a column type on a partitioned parent may require corresponding operations on partitions. Rewriting each partition can create large peak I/O and WAL spikes. For historical partitions, it may be possible to process partition by partition if schema and application compatibility allow.

### 17.4. Partition Maintenance Locks

ATTACH/DETACH has its own lock behavior. If a default partition exists, bound verification may scan the default partition and run long. Create a matching CHECK constraint before attaching to reduce scanning when PostgreSQL can prove the bounds.

## 18. Migration Impact on Replication

DDL and rewrites affect replicas differently depending on the replication mode.

### 18.1. Physical Streaming Replication

Physical replicas replay WAL from the primary. Table rewrites and index builds generate WAL that can cause replica replay lag. DDL arrives on the replica via WAL replay; do not run the migration separately on a physical standby.

### 18.2. Logical Replication

Logical replication does not automatically replicate DDL the way physical WAL replay does. Schema changes must be deployed separately and in the proper order on publisher and subscriber.

If the subscriber lacks the required column or constraint, replication apply may fail when the publisher begins sending rows under the new schema. Expand subscriber and publisher according to the rollout plan.

### 18.3. Replication Lag

Monitor:

```sql
SELECT
    application_name,
    state,
    sync_state,
    write_lag,
    flush_lag,
    replay_lag,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
```

Lag fields may be NULL if there is no recent sample. Combine LSN byte differences with provider metrics for a complete picture.

### 18.4. Logical Replication Slots

Slots retain WAL for subscribers. If a consumer falls behind, retained WAL can increase disk usage. Monitor slot activity and retained bytes during large rewrites.

### 18.5. Multi-Region Rollouts

If applications read from replicas across multiple regions, wait for schema changes/replay to complete before deploying code that depends on a new column. Feature flags or capability checks may be required.

## 19. Migration Tools and Transaction Boundaries

Migration frameworks may automatically manage transactions, lock timeouts, and ordering.

### 19.1. One Migration Does Not Have to Be One Large Transaction

Fast metadata changes can be grouped into short transactions. Concurrent index builds must be kept outside transactions. Large backfills should be batched and committed periodically.

### 19.2. Migration Locks

Many migration tools use an advisory lock to ensure only one migration runner executes at a time. An advisory migration lock does not replace table locks and does not prevent DBAs or applications from executing other DDL.

### 19.3. Idempotency

`IF EXISTS` and `IF NOT EXISTS` can make migrations safer when object state has been verified, but they do not replace schema version tracking. An existing index with the wrong definition can still cause CREATE INDEX IF NOT EXISTS to skip fixing it.

### 19.4. Never Run DDL in an Unknown State

If a deployment loses its connection after sending DDL, the client may not know whether the transaction committed. Before retrying, inspect catalog state and migration history. Never blindly re-run destructive commands.

### 19.5. Migration Observability

Record:

- Migration ID/version.
- Start/end timestamps.
- Database/cluster.
- Statement/phase.
- Lock wait duration.
- Execution duration.
- Rows processed.
- WAL bytes and replica lag.
- Error/retry count.
- Application release version.

## 20. Migration Example: Adding a Column and Backfilling

Suppose we need to add a `normalized_email` column to a large customers table.

### 20.1. Expand Schema

```sql
ALTER TABLE app.customers
    ADD COLUMN normalized_email text;
```

On modern PostgreSQL, this is usually metadata-only if there is no volatile default. A lock must still be acquired.

### 20.2. Deploy Compatibility Code

New code writes both email and normalized_email. Old code still reads email. Do not switch reads immediately.

### 20.3. Batched Backfill

```sql
WITH batch AS (
    SELECT id
    FROM app.customers
    WHERE normalized_email IS NULL
    ORDER BY id
    LIMIT 2000
    FOR UPDATE SKIP LOCKED
)
UPDATE app.customers AS c
SET normalized_email = lower(trim(c.email))
FROM batch
WHERE c.id = batch.id;
```

Run repeatedly, committing each batch. Stop when no matching rows remain. You may need to distinguish legitimate NULL emails from unbackfilled rows using a separate status or appropriate predicate.

### 20.4. Add Index Concurrently

```sql
CREATE INDEX CONCURRENTLY customers_normalized_email_idx
    ON app.customers (normalized_email);
```

Monitor progress:

```sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    phase,
    lockers_total,
    lockers_done,
    blocks_total,
    blocks_done,
    tuples_total,
    tuples_done
FROM pg_stat_progress_create_index;
```

### 20.5. Switch Reads

Deploy code reading normalized_email. Monitor nulls, query plans, errors, and latency. Keep a compatibility window for rollback.

### 20.6. Contract

After old code is no longer running:

```sql
ALTER TABLE app.customers
    DROP COLUMN email RESTRICT;
```

Only do this once the business contract and downstream consumers have migrated. Dropping the column does not guarantee immediate file size reduction.

## 21. Migration Example: Adding a Foreign Key Online

Suppose order_items.order_id needs to reference orders.id on a large table.

### 21.1. Preflight Orphan Rows

```sql
SELECT oi.order_id, count(*)
FROM app.order_items AS oi
LEFT JOIN app.orders AS o
    ON o.id = oi.order_id
WHERE oi.order_id IS NOT NULL
  AND o.id IS NULL
GROUP BY oi.order_id
ORDER BY count(*) DESC
LIMIT 100;
```

Resolve orphan rows before validating.

### 21.2. Add NOT VALID

```sql
ALTER TABLE app.order_items
    ADD CONSTRAINT order_items_order_fk
    FOREIGN KEY (order_id)
    REFERENCES app.orders(id)
    NOT VALID;
```

Assess the lock window on both child and parent. The command may wait on transactions holding conflicting locks.

### 21.3. Validate

```sql
ALTER TABLE app.order_items
    VALIDATE CONSTRAINT order_items_order_fk;
```

Monitor I/O, active transactions, and lock waits. Validation still reads existing rows.

### 21.4. Post-Check

```sql
SELECT
    conname,
    convalidated,
    pg_get_constraintdef(oid, true)
FROM pg_constraint
WHERE conrelid = 'app.order_items'::regclass
  AND conname = 'order_items_order_fk';
```

Verify convalidated is true and application writes no longer create orphan data.

## 22. Operations That Can Run Long Even Without a Rewrite

Not rewriting the table does not mean the operation is instantaneous.

### 22.1. Constraint Validation

A validation scan can read the entire table. The I/O cost approaches a full scan depending on cache, table size, and concurrency.

### 22.2. Index Creation

An index build reads the table, sorts/indexes tuples, and writes index storage. Concurrent builds add extra phases and waits to ensure consistency.

### 22.3. SET NOT NULL

Without a valid CHECK proof, PostgreSQL must verify no NULLs exist. On a large table, the scan is significant.

### 22.4. Partition Attach

PostgreSQL may scan the candidate table or default partition to verify partition constraints if no matching CHECK constraint exists.

### 22.5. DROP COLUMN

The catalog operation is fast but does not immediately reclaim physical space. If a rewrite is needed later to reclaim space, the heavy cost appears in that step.

## 23. Preflight Checklist Before ALTER TABLE

Before running DDL in production, answer:

### 23.1. Object Scope

- How many rows and GB does the table have?
- Are there partitions or inheritance children?
- Are there related indexes, constraints, triggers, views, or foreign keys?
- Are there replication/CDC consumers?

### 23.2. Lock Behavior

- Which lock mode does the subcommand acquire?
- Does it require locks on referenced tables or partitions?
- Are long-running transactions holding conflicting locks?
- Are there pending DDLs or maintenance jobs?
- Are lock timeout and statement timeout configured?

### 23.3. Rewrite/Scan Behavior

- Does the operation rewrite the table?
- Does it scan existing rows?
- Does it rebuild indexes?
- Can NOT VALID/VALIDATE or concurrent index builds be used?
- Can expand-contract be used?

### 23.4. Resource Capacity

- Free disk on tablespaces holding the table/indexes?
- WAL capacity and archive throughput?
- Replica lag headroom?
- CPU/I/O headroom?
- Backup window and retained WAL?
- Is there enough room for old and new files simultaneously?

### 23.5. Application Compatibility

- Can old and new application versions run concurrently?
- Does ORM/schema caching need refreshing?
- Are prepared statements affected by renames or type changes?
- Is there a feature flag to switch reads/writes?
- Is rollback feasible after backfilling?

## 24. Monitoring Migration Progress

### 24.1. CREATE INDEX Progress

`pg_stat_progress_create_index` shows the phase, blocks, and tuples processed for running index builds.

### 24.2. VACUUM Progress

`pg_stat_progress_vacuum` tracks vacuum operations. If maintenance coincides with a migration, use the corresponding progress view to isolate costs.

### 24.3. Table Locks

Use pg_locks joined with pg_stat_activity to detect sessions holding or waiting for locks. Monitor pending DDL before it causes a lock convoy.

### 24.4. WAL and Replication

Monitor WAL generation, archive backlog, replication slot retention, and replica replay lag. For large rewrites, set alerts based on disk headroom and lag budgets.

### 24.5. Application Metrics

Monitor:

- Request p95/p99 latency.
- Connection pool wait times.
- Database timeout/error rates.
- Queue depth.
- Transaction retry counts.
- Endpoint availability.
- Background job backlog.

A migration that succeeds in SQL yet causes API timeouts is still an operational failure.

## 25. Rollback and Recovery

Not every schema migration can be rolled back with a simple command.

### 25.1. Metadata-Only Changes

ADD COLUMN can be rolled back with DROP COLUMN if no new data or dependencies need to be preserved. A rename can be reversed, though application versions may already be using the new name.

### 25.2. Type Changes

Reverting a type change can lose data if the conversion is not reversible. For instance, bigint to integer can overflow, or text normalization can lose original formatting.

### 25.3. Backfills

A backfill usually cannot be rolled back by setting the column to NULL if the application has started writing new values. Determine the source of truth and reconciliation strategy.

### 25.4. Index Creation

An index can be dropped if it does not back a constraint and is unneeded by the workload. Concurrent index cleanup must run outside a transaction block.

### 25.5. DDL After Commit

After COMMIT, rolling back requires a new migration or a restore/recovery strategy. Never assume a transaction rollback can undo a migration committed in a previous release.

### 25.6. Recovery Plan

Before high-risk operations:

- Have an appropriate backup/restore point.
- Verify backups can be restored.
- Save the DDL and current definitions.
- Prepare an inverse migration or forward-fix plan.
- Designate who decides to abort.
- Set thresholds for disk, lag, latency, and lock waits.

## 26. Common Pitfalls

| Symptom | Possible cause | Remediation |
| --- | --- | --- |
| ALTER TABLE waits very long | Conflicting transaction holding lock | Use pg_blocking_pids, locate transaction owner |
| New SELECTs also wait | ACCESS EXCLUSIVE DDL queued | Investigate lock queue, stop retry burst, resolve blocker |
| ADD COLUMN takes long | Volatile default or older version requiring rewrite | Check default volatility and server version |
| ALTER TYPE spikes disk usage | Table/index rewrite and WAL | Estimate disk/WAL, use staged migration |
| ADD CHECK makes writes wait | Validation/lock behavior | Use NOT VALID then VALIDATE |
| SET NOT NULL scans table long | Missing valid CHECK proof | Backfill, validate check, then set not null |
| CREATE INDEX CONCURRENTLY fails | Duplicate values, old snapshots, or cancellation | Check logs, invalid index, and blockers |
| ADD FK fails | Orphan rows | Preflight and fix data beforehand |
| Replica lag increases | WAL burst from rewrite/index build | Throttle batch/concurrency, monitor replay |
| Disk fills mid-rewrite | Insufficient headroom for old/new files/WAL | Abort per runbook, expand capacity |
| DROP COLUMN does not shrink disk | Column only marked dropped | Evaluate rewrite/repack separately |
| Migration tool reports concurrent index in transaction | Script auto-wrapped in BEGIN/COMMIT | Mark migration non-transactional |
| Partition attach scans long | Missing CHECK constraint proving bounds | Add/validate constraint before attach |
| Schema changed but app errors | Old/new code incompatible | Use expand-contract and feature flags |
| Rollback loses data | Irreversible type/backfill conversion | Use forward fix or restore/reconciliation |

## 27. Production Runbook for ALTER TABLE

**Step 1 — Define the change.** Document the table, columns, constraints, indexes, partitions, and application behavior before/after.

**Step 2 — Classify the operation.** Identify whether it is metadata-only, table scan, index build, or rewrite. Note the lock mode and involved relations.

**Step 3 — Check the workload.** Look for long-running transactions, blockers, peak traffic, and running maintenance.

**Step 4 — Check capacity.** Estimate table/index size, disk headroom, WAL/archive throughput, and replica lag budget.

**Step 5 — Prepare the migration.** Choose lock_timeout, statement_timeout, transaction boundaries, batch size, and rollback/forward-fix plan.

**Step 6 — Test on staging.** Use data volume, indexes, partitions, and concurrency close to production; measure lock wait, runtime, WAL, and disk.

**Step 7 — Execute in phases.** Prefer expand, concurrent indexing, NOT VALID/VALIDATE, and batched backfills where appropriate.

**Step 8 — Monitor in real time.** Watch pg_stat_activity, pg_locks, progress views, replication lag, disk, and application metrics.

**Step 9 — Abort if budgets are exceeded.** Stop batches or cancel the operation per runbook if latency, disk, or lag crosses defined thresholds.

**Step 10 — Verify schema and data.** Check catalogs, constraints, index validity, row consistency, and application behavior.

**Step 11 — Switch traffic.** Enable feature flags / new read paths once schema and replicas are ready.

**Step 12 — Contract after deprecation.** Drop old objects in a separate release once no callers or dependencies remain.

## 28. Hands-On Exercises

Perform these on a dedicated PostgreSQL lab. Do not test large rewrites, lock contention, or destructive DDL in production.

### Exercise 1 — ALTER TABLE Metadata

Create a small table and add a nullable column without a default. Observe the catalog changes and explain why the operation does not need to write NULL into every row.

### Exercise 2 — Lock Modes

In one session, open a transaction running SELECT on a table. In another session, run ALTER TABLE ADD COLUMN. Observe the lock wait and explain the ACCESS SHARE/ACCESS EXCLUSIVE conflict.

### Exercise 3 — Lock Queue

Create a transaction holding a lock for a long time, have ALTER TABLE wait on it, and issue another SELECT. Observe the queue behavior and request latency.

### Exercise 4 — lock_timeout

Set a short lock_timeout and attempt ALTER TABLE while a blocker is present. Verify the statement fails fast and the transaction requires rollback.

### Exercise 5 — statement_timeout

Run a long validation or query in the lab with a short statement_timeout. Compare its timeout behavior with lock_timeout.

### Exercise 6 — ADD COLUMN Without Default

Create a table with many rows, add a nullable column, and compare the duration with a small table. Record the lock and file size.

### Exercise 7 — ADD COLUMN Constant Default

On PostgreSQL 11+, add a column with a constant default. Compare this with older version behavior or the corresponding version documentation.

### Exercise 8 — ADD COLUMN Volatile Default

Add a column with a volatile default in the lab. Observe the runtime and explain why existing rows require individual values.

### Exercise 9 — SET/DROP DEFAULT

Change a default and verify that existing rows do not change automatically.

### Exercise 10 — DROP COLUMN

Drop a column in the lab and check pg_attribute.attisdropped. Compare the logical schema with physical relation size.

### Exercise 11 — RENAME COLUMN

Rename a column and test application queries using the old and new names. Write a backward-compatible rollout.

### Exercise 12 — ALTER TYPE Rewrite

Convert a text column to bigint using USING on a lab table with many rows. Measure runtime, disk, and WAL.

### Exercise 13 — Binary-Coercible Conversion

Find a type conversion identified as binary-coercible in the PostgreSQL documentation. Compare its behavior against a conversion that requires a rewrite.

### Exercise 14 — Default Conversion

Create a default that cannot cast to the target type. Test DROP DEFAULT, ALTER TYPE, and re-applying SET DEFAULT.

### Exercise 15 — CHECK Validation

Add a normal CHECK constraint on a populated table. Observe the scan and compare it with ADD CHECK NOT VALID followed by VALIDATE.

### Exercise 16 — NOT NULL Proof

Create rows with NULLs, backfill them, add CHECK NOT VALID, validate, and then SET NOT NULL. Observe behavior and locks.

### Exercise 17 — Foreign Key NOT VALID

Create orphan rows, add FK NOT VALID, and observe new data being checked. Fix the orphans and validate the constraint.

### Exercise 18 — FK Referencing Index

Create a child table with a foreign key. Test deleting parent rows without a child index, then create the index and compare query/lock impact.

### Exercise 19 — Unique Index Concurrently

Create a unique index concurrently on a large lab table. Monitor pg_stat_progress_create_index.

### Exercise 20 — Concurrent Index Failure

Create duplicate data and attempt a unique index concurrently. Inspect the leftover invalid index and perform the cleanup procedure.

### Exercise 21 — Attach Index as Constraint

Create a unique index concurrently and use ADD CONSTRAINT USING INDEX. Inspect the constraint/index catalog relationship.

### Exercise 22 — Transaction Boundary

Run ALTER TABLE inside a long transaction and observe that the lock persists after the statement until COMMIT.

### Exercise 23 — Rewrite Disk Estimate

Measure table/index sizes and estimate peak free space for a rewrite. Compare with actual disk consumption in the lab.

### Exercise 24 — WAL and Replica Lag

On a lab with a physical standby, run a controlled rewrite and observe WAL generation and replay lag.

### Exercise 25 — MVCC Rewrite Caveat

Create a long-running snapshot transaction and test a rewrite in a test environment. Observe the version-specific behavior and explain the MVCC-safety warning.

### Exercise 26 — Partition Attach

Create a partitioned parent and a candidate table. Attach the partition; compare behavior with and without a CHECK constraint proving bounds.

### Exercise 27 — Partition Detach

Test regular DETACH PARTITION and CONCURRENTLY if supported by your version. Observe lock modes and restrictions.

### Exercise 28 — Parent ALTER TABLE

Add a column on a partitioned parent. Observe schemas/locks of child partitions and test ONLY in the lab.

### Exercise 29 — Expand-Contract

Execute a migration to add a new column, dual-write, batch backfill, switch reads, and drop the old column in a lab application.

### Exercise 30 — Batch Backfill

Compare one large UPDATE against multiple batches. Measure WAL, transaction duration, replica lag, and autovacuum impact.

### Exercise 31 — Blocking Diagnosis

Create a blocker and a blocked DDL. Use pg_stat_activity, pg_locks, and pg_blocking_pids to find the root transaction.

### Exercise 32 — Migration Timeout

Design a migration using SET LOCAL lock_timeout and statement_timeout. Verify rollback behavior on timeout.

### Exercise 33 — Migration Framework

Configure a non-transactional migration for CREATE INDEX CONCURRENTLY. Verify the framework does not auto-wrap it in BEGIN/COMMIT.

### Exercise 34 — Preflight Report

Write a read-only report covering table size, index size, partitions, long transactions, locks, replication lag, and disk headroom before DDL.

### Exercise 35 — Production Rollout Plan

Write a runbook for an ALTER COLUMN TYPE on a large table, covering preflight, staged migration, batch size, monitoring, abort thresholds, and recovery plan.

## 29. Summary

Key takeaways when working with **ALTER TABLE, lock levels, and table rewrite operations**:

1. ALTER TABLE has many forms with different lock, scan, and rewrite costs.
2. Most ALTER TABLE forms require ACCESS EXCLUSIVE; ADD FOREIGN KEY and VALIDATE CONSTRAINT are important lock exceptions.
3. Metadata-only does not mean non-blocking: strong locks can still block reads and writes.
4. Locks are held until the end of the transaction, so migration transactions must stay short.
5. ADD COLUMN nullable without default usually does not rewrite; constant defaults have a fast path since PostgreSQL 11, while volatile defaults may rewrite.
6. SET/DROP DEFAULT and RENAME primarily change metadata.
7. DROP COLUMN does not reclaim physical disk immediately.
8. ADD CHECK/FK NOT VALID separates constraint creation from scanning existing data; VALIDATE CONSTRAINT uses a weaker lock.
9. SET NOT NULL can skip a full scan when a suitable validated CHECK proof exists.
10. ALTER COLUMN TYPE usually rewrites the table if the physical representation changes; USING expressions must be preflighted.
11. Concurrent unique indexes and ADD CONSTRAINT USING INDEX reduce strong lock duration.
12. Concurrent index builds consume I/O, have multiple phases, and can leave invalid indexes on failure.
13. Partition attach/detach has specific lock behavior and restrictions.
14. Rewrites require disk, WAL, CPU, I/O, and can cause replica lag; they also carry MVCC caveats.
15. Expand-contract, batched backfills, bounded timeouts, and monitoring reduce production risk.

A safe schema migration begins with understanding the lock mode and the physical work PostgreSQL must perform. By separating metadata changes, validation scans, index builds, and table rewrites, operations teams can select the right rollout pattern, budget resources, and reduce the risk of turning a DDL change into an outage.

## 30. Official PostgreSQL Documentation

- [ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html)
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)
- [Table-Level Lock Modes](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-TABLES)
- [MVCC and Table Rewriting](https://www.postgresql.org/docs/current/mvcc-caveats.html)
- [ALTER TABLE and Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html)
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html)
- [CREATE INDEX Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html#CREATE-INDEX-PROGRESS-REPORTING)
- [Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html)
- [ALTER TABLE Partition Operations](https://www.postgresql.org/docs/current/sql-altertable.html)
- [Runtime Client Connection Defaults](https://www.postgresql.org/docs/current/runtime-config-client.html)
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [pg_locks](https://www.postgresql.org/docs/current/view-pg-locks.html)
- [pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEW)
- [Progress Reporting](https://www.postgresql.org/docs/current/progress-reporting.html)
- [Warm Standby and Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html)
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html)

The `current` links point to the current PostgreSQL documentation. Lock modes, fast defaults, partition operations, catalog fields, and concurrent DDL restrictions may vary by major version. Before deploying, check `SHOW server_version` and the documentation matching your running version.
