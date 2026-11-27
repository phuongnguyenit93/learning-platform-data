# ALGORITHM INSTANT/INPLACE/COPY and Conditions for Each Change Type

When altering a MySQL table structure with `ALTER TABLE`, the execution algorithm directly impacts DDL runtime, disk usage, locking level, and whether the application can continue reading and writing. The three common algorithms are `INSTANT`, `INPLACE`, and `COPY`. They describe how MySQL performs the change at the storage layer; an algorithm's name alone does not guarantee the operation is completely lock-free or zero-impact on workload.

`INSTANT` primarily modifies metadata without rebuilding the entire table's data. `INPLACE` executes changes within the existing storage structure and may permit concurrent DML, though some operations still rebuild the table or indexes. `COPY` creates a temporary table with the new structure and copies data across; this generally consumes more time, I/O, and disk space while restricting concurrent writes.

Support conditions depend on MySQL version, storage engine, table type, current structure, and the exact DDL operation. This lesson focuses on InnoDB in modern MySQL while emphasizing verification on the exact target version before changing production.

## 1. How do the three DDL algorithms work?

### 1.1. ALGORITHM=INSTANT

`INSTANT` updates metadata so MySQL interprets the table structure according to the new definition. For supported operations, MySQL does not need to read and rewrite all rows in the table. Consequently, execution time is usually very short, I/O usage is low, and DML can continue for most of the operation.

Example adding a nullable column to an InnoDB table when version and table structure support it:

~~~sql
ALTER TABLE customers
  ADD COLUMN nickname VARCHAR(80) NULL,
  ALGORITHM=INSTANT;
~~~

Where supported, the new column's value is resolved via metadata for existing rows; MySQL does not need to rewrite every row just to add the column. When the application begins writing new values, rows are updated normally.

`INSTANT` does not mean no metadata lock is needed. MySQL still must acquire a metadata lock to protect the table definition at the start and end of DDL. A long transaction using the table can force the DDL to wait; a DDL waiting on a metadata lock can also cause new queries to queue behind it. Therefore, an instant change can still cause disruption if long transactions or lock queues exist.

`INSTANT` also has limits on operation types and table structures. You cannot assume every `ADD COLUMN`, `DROP COLUMN`, data type change, or index change executes instantly. In InnoDB, instant support has expanded across releases. For example, adding columns at arbitrary positions and instant `DROP COLUMN` were expanded in MySQL 8.0.29; earlier versions have different limits. Tables with special structures, indexes, or incompatible attributes may not be supported.

### 1.2. ALGORITHM=INPLACE

`INPLACE` performs changes without using the `COPY` workflow of creating a temporary table and copying all rows. However, the name `INPLACE` can be misleading: an `INPLACE` operation can still rebuild the table or indexes internally inside InnoDB. What matters is checking whether the specific operation performs a rebuild and what level of concurrency it allows.

Example adding a secondary index:

~~~sql
ALTER TABLE orders
  ADD INDEX idx_orders_created_at (created_at),
  ALGORITHM=INPLACE,
  LOCK=NONE;
~~~

For supported operations and table structures, InnoDB can build the index while the application continues reading and writing. MySQL captures concurrent changes so the new structure is updated before completion. This process still consumes CPU, I/O, temporary disk space, and can increase query latency.

Some `INPLACE` operations rebuild the table. For instance, adding a primary key may require sorting and reorganizing data according to the new clustered index. Thus, `INPLACE` does not mean metadata-only, nor does it guarantee short execution time.

`LOCK=NONE` explicitly requests concurrent DML during DDL. If the operation does not support this lock level, the statement fails rather than silently degrading to a stricter lock. However, even when `LOCK=NONE` is supported, DDL still needs metadata locks during certain phases, particularly at the start and end.

### 1.3. ALGORITHM=COPY

`COPY` creates a new table with the target structure, copies data from the old table into the new table, and swaps them. This is the more general approach and can support changes that `INSTANT` or `INPLACE` cannot perform.

Illustrative example changing a column's data type where version/engine requires `COPY`:

~~~sql
ALTER TABLE customers
  MODIFY COLUMN phone_number VARCHAR(40),
  ALGORITHM=COPY;
~~~

The copy process may read the entire table, write all data, and rebuild all indexes. For large tables, provision disk space for the new table, indexes, temporary files, binary logs, and safety headroom. Impacts can include elevated I/O, replication lag, long DDL duration, and write restrictions on the table.

Default locking behavior depends on the operation and engine. `COPY` does not support concurrent DML like `INPLACE` with `LOCK=NONE`. In practice, assume a `COPY` operation may block writes for an extended period and confirm exact read/write behavior for your version before planning production changes.

## 2. Quick comparison of the three algorithms

| Attribute | INSTANT | INPLACE | COPY |
|---|---|---|---|
| Mechanism | Modifies metadata | Modifies structure in place; may rebuild | Creates new table and copies data |
| Reads/rewrites all rows | Usually no | Depends on operation; some rebuild | Yes |
| Duration | Usually very brief if supported | Short to long depending on operation | Can be long on large tables |
| I/O | Usually low | Can be high when building indexes or rebuilding | Usually high |
| Concurrent DML | Usually supported for instant operations | Depends on `LOCK` and operation | Restricted; not usable as online DDL with `LOCK=NONE` |
| Metadata lock | Still required | Still required | Still required |
| Extra space | Usually low | May need space for indexes/rebuild/log | Usually needs space for full copy and indexes |
| Operational risks | Metadata lock waits, version/structure limits | Resource load, online alter log, rebuild, and metadata locks | Duration, disk space, locks, and replication lag |

The usual preference order is choosing `INSTANT` if genuinely supported, evaluating `INPLACE` with an appropriate lock level, and planning an explicit maintenance window if only `COPY` is available. However, do not choose an algorithm by name alone: an `INPLACE` operation rebuilding a huge table can be costlier than a `COPY` operation on a tiny table.

## 3. Distinguishing ALGORITHM and LOCK

`ALGORITHM` determines how MySQL executes the structural change. `LOCK` determines the level of concurrency permitted while DDL runs. These are two related options, not substitutes for each other.

Common `LOCK` levels:

| Lock level | Meaning |
|---|---|
| DEFAULT | MySQL chooses the maximum concurrency level supported by the operation |
| NONE | Permits concurrent reads and writes during online phases supported by the operation |
| SHARED | Permits concurrent reads but blocks writes |
| EXCLUSIVE | Blocks both reads and writes while the lock is in effect |

Example requiring MySQL to build an index `INPLACE` while permitting concurrent DML:

~~~sql
ALTER TABLE orders
  ADD INDEX idx_orders_customer_created (customer_id, created_at),
  ALGORITHM=INPLACE,
  LOCK=NONE;
~~~

If MySQL reports that the operation cannot run with `LOCK=NONE`, treat that as a signal to re-evaluate the design. Do not simply remove `LOCK=NONE` to make the statement succeed without understanding the disruption `DEFAULT` or another lock level will cause.

With `ALGORITHM=INSTANT`, modern MySQL versions restrict locking to default mode; do not try specifying `LOCK=NONE`, `SHARED`, or `EXCLUSIVE` for instant operations. Use simple `INSTANT` syntax and verify behavior against your running version's documentation.

`LOCK=NONE` also does not mean lock-free across the entire statement lifecycle. Metadata locks can still block at the start and end of DDL. The application can experience waits if a transaction holds a metadata lock for a long time or if DDL is waiting on a lock and new queries pile up behind it.

## 4. Common changes and usable algorithms

The table below is a directional guide for InnoDB, not a support matrix valid across every version:

| Change | Typical algorithm | Things to check |
|---|---|---|
| Add nullable column at end of table | `INSTANT` on supported versions | Version, row format, table structure, and instant row version limit |
| Add column at arbitrary position | `INSTANT` on MySQL 8.0.29+ if eligible | Version and table structure constraints |
| Drop column | `INSTANT` on MySQL 8.0.29+ in supported cases; earlier often needs other approaches | Indexes, generated columns, partitions, and row version limit |
| Change column `DEFAULT` value | Often `INSTANT` for supported metadata changes | Column type, default expression, and version |
| Add secondary index | Usually `INPLACE` | Whether `LOCK=NONE` is supported; space and index-build load |
| Drop secondary index | Usually `INPLACE` | Depends on index type and table structure |
| Add primary key | May be `INPLACE` but usually rebuilds data | Table size, clustered index, and disk space |
| Change column data type | May be `INPLACE` or require `COPY` | Physical conversion feasibility, data loss risk, and version |
| Change row format or storage attributes | May require rebuild or `COPY` | Engine, target row format, compression, and data size |

Never use this table as a substitute for testing. For example, adding a seemingly simple column may not be instant if the table has reached the row version limit or has an incompatible structure. Conversely, an operation may run `INPLACE` in one version yet require `COPY` in another.

### 4.1. Adding columns and the instant row version limit

InnoDB can store certain instant changes as row versions rather than rewriting all rows. Each instant column add or drop can increment the table's row version count. MySQL caps the total number of row versions; once the limit is reached, subsequent instant operations cannot execute until the table is rebuilt appropriately.

On MySQL 8.0.29 and newer, you can inspect row version info in InnoDB metadata via columns provided by that version, such as `TOTAL_ROW_VERSIONS` in `INFORMATION_SCHEMA.INNODB_TABLES`. Before relying on this column, verify it exists in the exact running version.

Example query on a version providing that metadata column:

~~~sql
SELECT
  NAME,
  TOTAL_ROW_VERSIONS
FROM INFORMATION_SCHEMA.INNODB_TABLES
WHERE NAME = 'app_db/customers';
~~~

If the row version count approaches the limit, schedule a controlled rebuild to consolidate the physical structure before making further instant changes. Rebuilds can consume substantial resources and time, so factor them into your schema evolution plan instead of waiting for DDL to fail.

### 4.2. Adding indexes

Adding a secondary index typically uses `INPLACE` and may permit `LOCK=NONE`. Even so, MySQL must read data to build the index, sort keys, and write the new index structure. On large tables, this operation can raise I/O and degrade latency for other queries.

Before creating an index, confirm the index does not already exist, column order matches queries, and disk space is sufficient. After creation, verify queries with `EXPLAIN` and monitor response times. Never build multiple huge indexes simultaneously on a production machine without evaluating I/O contention.

## 5. Requesting an algorithm deliberately

If you want MySQL to execute only with `INSTANT` and error out if unsupported:

~~~sql
ALTER TABLE customers
  ADD COLUMN preferred_name VARCHAR(100) NULL,
  ALGORITHM=INSTANT;
~~~

If you want to prevent falling back to `COPY` while accepting `INPLACE`:

~~~sql
ALTER TABLE orders
  ADD INDEX idx_orders_status_created (status, created_at),
  ALGORITHM=INPLACE,
  LOCK=NONE;
~~~

If `ALGORITHM` is omitted, MySQL uses `DEFAULT` and picks whichever method it deems suitable. That is convenient, yet may violate production lock-duration requirements. For sensitive changes, explicitly specifying the desired algorithm and lock level makes the statement fail fast if requirements aren't met rather than unexpectedly running a much costlier operation.

Do not force `ALGORITHM=INPLACE` or `INSTANT` just to avoid `COPY` if the operation does not support it. A MySQL error is a signal to pause and reassess, not a reason to bypass safety checks.

## 6. Metadata locks and long transactions

MySQL uses metadata locks (MDL) to protect object definitions when queries and DDL access a table concurrently. A transaction can hold metadata locks until the transaction ends, even after the query statement itself finishes executing while the transaction remains open.

Example:

1. Session A opens a transaction and queries the `customers` table.
2. Session A has not yet run `COMMIT` or `ROLLBACK`.
3. Session B executes `ALTER TABLE customers ADD COLUMN ...`.
4. The DDL must wait on Session A's metadata lock.
5. Subsequent queries may queue behind the waiting DDL, making the system appear hung.

Thus, even `INSTANT` DDL can be delayed by long-running transactions. Before executing, check open transactions, long queries, lock waits, and the process list.

You can inspect granted or pending metadata locks on versions with appropriate Performance Schema support:

~~~sql
SELECT
  OBJECT_TYPE,
  OBJECT_SCHEMA,
  OBJECT_NAME,
  LOCK_TYPE,
  LOCK_DURATION,
  LOCK_STATUS,
  OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = 'app_db'
  AND OBJECT_NAME = 'customers';
~~~

If locks are waiting, identify the owning session and determine whether the transaction can finish safely. Never kill sessions or transactions indiscriminately; confirm the owner and business impact first.

You can cap metadata lock wait time using `lock_wait_timeout` at the session level:

~~~sql
SET SESSION lock_wait_timeout = 10;
~~~

Setting a timeout makes DDL exit rather than wait indefinitely if it cannot acquire a metadata lock. Choose the exact value based on your deployment window. A low timeout may cause DDL to fail during busy periods; handle the error and retry at an appropriate time.

## 7. Online DDL still has costs

For `INPLACE` operations that permit concurrent DML, InnoDB records concurrent modifications occurring during structure construction in an online alter log. If the volume of changes exceeds `innodb_online_alter_log_max_size`, the DDL fails. Raising the limit is not free: it consumes extra disk space and can prolong the finalization phase.

Impacts to monitor include:

- Increased CPU and I/O from table scans, key sorting, or rebuilds.
- Increased disk usage from new indexes, temporary files, or the online alter log.
- Increased replication lag from the DDL or concurrent changes during execution.
- Increased application latency from resource contention.
- Metadata locks during start and completion phases.
- Prolonged DDL extending maintenance windows and delaying rollback options.

Online DDL does not guarantee zero impact on other queries. Test with production-like data sizes and write rates, monitor metrics, and define abort thresholds.

## 8. Choosing algorithms through practical examples

### Scenario A: Adding an optional description column

Requirement: add nullable column `nickname` to `customers`. If the InnoDB version supports instant for this structure, use `ALGORITHM=INSTANT`. Before running, confirm the table has not hit row version limits and no long transactions hold MDL.

### Scenario B: Adding an index for reporting queries

Requirement: add an index on `(status, created_at)`. Verify column order against `WHERE` and `ORDER BY` clauses. If supported, use `INPLACE, LOCK=NONE` to permit concurrent DML. Measure I/O, disk space, lag, and latency while the index builds.

### Scenario C: Changing data type in a way that alters storage

Requirement: convert a numeric column from `INT` to a wider range or convert a string column to another type. `INPLACE` eligibility depends on the exact conversion and version. If MySQL requires `COPY`, estimate duration and disk space, schedule a maintenance window, or use a well-tested online schema change tool. Check for out-of-range values and data-loss risks before running.

### Scenario D: Adding a primary key to a large table

Adding a primary key may require InnoDB to reorganize the clustered index. Even if the statement accepts `INPLACE`, the operation can rebuild the entire table and incur heavy I/O. Measure duration on a production-like clone, evaluate disk space, and assess replication impact.

## 9. Safe ALTER TABLE deployment workflow

A practical workflow should include these steps:

1. **Define the change:** document the table, column/index, before/after types, application impact, and compatibility requirements.
2. **Check version and engine:** confirm exact MySQL version, InnoDB, table structure, partitions, indexes, and conditions that could restrict algorithms.
3. **Select algorithm and lock:** prefer `INSTANT` when supported; otherwise evaluate `INPLACE` and `LOCK=NONE`; if only `COPY` is possible, plan capacity and downtime.
4. **Test on a clone:** use data matching production size, indexes, and workload; record duration, I/O, locks, and replication lag.
5. **Check metadata locks:** detect long transactions and lock-holding sessions prior to execution.
6. **Prepare backups and recovery:** confirm backups can be restored; prepare reverse DDL if feasible and evaluate whether type conversion loses data.
7. **Run with safeguards:** specify algorithm/lock explicitly when needed, set an appropriate `lock_wait_timeout`, and execute within the agreed window.
8. **Monitor:** observe process list, Performance Schema, CPU, I/O, disk space, replication lag, and application errors.
9. **Verify post-DDL:** run `SHOW CREATE TABLE`, inspect indexes, and run `EXPLAIN` on affected queries.
10. **Close the change:** record results, duration, actual algorithm used, locks, and follow-up items to watch.

Example before-and-after structural checks:

~~~sql
SHOW CREATE TABLE customers\G
SHOW INDEX FROM customers;
~~~

Do not run multiple heavy DDLs concurrently if they compete for resources or metadata locks. In replicated setups, verify DDL has applied on replicas and check lag before routing critical read workloads back.

## 10. Rollback and DDL limits

`ALTER TABLE` typically causes an implicit commit and cannot be undone with a standard SQL transaction `ROLLBACK`. Atomic DDL in MySQL protects the consistency of certain DDL operations against server crashes, but does not allow operators to roll back a schema to a prior definition using `ROLLBACK`.

Before changing anything, prepare one of these options:

- Tested reverse DDL, if the transformation does not lose information.
- Restore from backup or snapshot when schema/data is severely damaged.
- Run a supplemental migration to fix schema and data forward.
- For incompatible or hard-to-reverse changes, use expand-and-contract: add new structures, deploy code compatible with both forms, backfill data, switch reads/writes, and drop legacy structures in a separate release.

Changing data types can lose data if values cannot be represented in the new type. Dropping a column or index can impact applications and queries. A DDL statement completing without SQL error does not prove application compatibility. Verify both currently running code and the application version being deployed.

## 11. Practice scenario

An `orders` table has 80 million rows. The development team requests adding column `delivery_note`, creating an index on `(customer_id, created_at)`, and changing `legacy_code` from `VARCHAR(20)` to `VARCHAR(80)`. The system has continuous write traffic and a reporting replica.

Design a plan:

1. Check MySQL version, engine, table structure, and instant add-column eligibility for `delivery_note`.
2. If supported, add `delivery_note` with `ALGORITHM=INSTANT`; check metadata locks and row versions.
3. Evaluate building the new index with `INPLACE, LOCK=NONE` if supported; measure I/O and replication lag during the build.
4. Check whether changing `legacy_code` requires a rebuild or `COPY`; check existing data and disk space.
5. If changing the data type requires `COPY`, separate it into a maintenance window or use a rehearsed online schema change strategy.
6. After each DDL step, verify schema, indexes, query `EXPLAIN` plans, and replica status before proceeding to the next step.

Do not bundle all three changes into a single `ALTER TABLE` statement just to reduce deployment count if they have different algorithms, locks, and costs. Separating steps isolates which change causes load or errors and limits blast radius if you need to abort.

## 12. Self-check questions

1. How does `INSTANT` differ from `INPLACE` in how metadata and physical data are modified?
2. Why can `ALGORITHM=INPLACE` still rebuild a table?
3. Which two aspects of `ALTER TABLE` do `ALGORITHM` and `LOCK` control?
4. Why might `INSTANT` still have to wait for a metadata lock?
5. When can adding an index use `INPLACE` with `LOCK=NONE`, and what costs still remain?
6. Why must you check the MySQL version before using instant `ADD/DROP COLUMN`?
7. What role does the online alter log play when DML occurs concurrently?
8. Why cannot `ALTER TABLE` be undone with a standard SQL `ROLLBACK`?

Choosing an `ALTER TABLE` algorithm is a decision about execution mechanics, concurrency, resources, and operational risk. Verify support on your exact version, specify algorithms and lock levels explicitly when needed, rehearse on production-equivalent data, and verify both schema and application after DDL completes.
