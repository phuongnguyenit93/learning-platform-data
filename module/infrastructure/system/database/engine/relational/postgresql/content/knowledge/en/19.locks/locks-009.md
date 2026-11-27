# Locks in ALTER TABLE, Index Creation, and Maintenance in PostgreSQL

## 1. Why Can DDL and Maintenance Stall a System?

A PostgreSQL table may serve thousands of `SELECT`, `INSERT`, `UPDATE`, and `DELETE` statements every minute. When engineers need to add a column, create an index, validate a constraint, clean up dead row versions, or reorganize data, the database must ensure that **the table structure and data cannot change incompatibly while the operation is running**.

PostgreSQL uses multiple types of **locks** to safeguard that consistency. DDL and maintenance are often labeled "administrative tasks," yet they directly impact live application traffic:

- `ALTER TABLE` can require `ACCESS EXCLUSIVE` even when the metadata change itself takes milliseconds.
- Regular `CREATE INDEX` allows reads, yet **blocks writes** on the target table while building the index.
- `CREATE INDEX CONCURRENTLY` avoids blocking writes, yet takes longer, consumes more work, and enforces operational constraints.
- Plain `VACUUM` is designed to run concurrently with most reads and writes, yet still conflicts with certain DDL and maintenance tasks.
- `VACUUM FULL` rewrites the table, requires the strongest lock, and **blocks both reads and writes**.
- Even a strong lock request **waiting in the queue** can cause incoming queries to queue behind it, even before DDL starts modifying the table.

### 1.1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **table-level locks**, **row-level locks**, and **transaction/virtual transaction locks** at an operational level.
2. Understand modes such as `ACCESS SHARE`, `ROW EXCLUSIVE`, `SHARE UPDATE EXCLUSIVE`, `SHARE`, `SHARE ROW EXCLUSIVE`, and `ACCESS EXCLUSIVE`.
3. Explain when `ALTER TABLE` blocks reads/writes and why a near-instant metadata change can still cause an outage.
4. Choose `CREATE INDEX` vs. `CREATE INDEX CONCURRENTLY` based on concurrency requirements.
5. Distinguish `REINDEX`, `REINDEX CONCURRENTLY`, `VACUUM`, `VACUUM FULL`, `ANALYZE`, and `CLUSTER`.
6. Observe blockers and waiters via `pg_stat_activity`, `pg_locks`, `pg_blocking_pids()`, and progress views.
7. Use `lock_timeout`, `statement_timeout`, and phased migrations to contain risk.
8. Test with two connections to observe lock waits in a practice database.
9. Build a schema/index maintenance deployment checklist with rollback and verification steps.

> **Practice safety:** run lock/DDL examples only in a lab database you are authorized to use. Never hold blocking locks on production tables "just to see what happens." Operations like `VACUUM FULL`, `CLUSTER`, or large index builds generate heavy load, consume extra disk space, and directly impact users.

---

## 2. Locks in PostgreSQL: Three Common Levels

"Lock" is not a single monolithic concept. When reading docs or handling incidents, identify which layer is involved.

| Lock layer | Role | Typical operations |
|---|---|---|
| **Table-level / relation locks** | Protects relation operations and coordinates DDL, DML, and maintenance | `ALTER TABLE`, `CREATE INDEX`, `VACUUM`, `SELECT` |
| **Row-level locks** | Coordinates updates or explicit locking on individual rows | `UPDATE`, `DELETE`, `SELECT ... FOR UPDATE` |
| **Transaction ID / virtual transaction locks** | Coordinates waiting for another transaction to end | A writer waiting on a transaction that modified a row |

There are also page-level locks, predicate locks (under `SERIALIZABLE`), advisory locks, and internal synchronization primitives. This lesson focuses on **relation locks** during `ALTER TABLE`, indexing, and maintenance, while keeping in mind that row and transaction locks also appear in lock-wait reports.

### 2.1. Lock Mode Names Do Not Mean "Absolute Full-Table Lock"

`ROW EXCLUSIVE` includes the word "EXCLUSIVE," yet **does not** block plain `SELECT`s. Conversely, `ACCESS EXCLUSIVE` is the strongest relation lock mode, conflicting with every other relation mode—including `ACCESS SHARE` used by plain `SELECT`s.

Likewise, the word **ROW** in `ROW SHARE` or `ROW EXCLUSIVE` does not make them **row-level locks**: they are still **table-level lock modes**.

### 2.2. Relation Locks and MVCC Data Visibility

A plain `SELECT` acquires `ACCESS SHARE` on accessed relations, while MVCC decides which row versions are visible to its snapshot. MVCC keeps readers from waiting on row-by-row writers, yet **does not eliminate** DDL conflicts such as `ACCESS EXCLUSIVE`.

### 2.3. How Long Are Locks Held?

Many relation locks are acquired by a statement inside a transaction and held **until the transaction ends**, not released as soon as the `ALTER` statement finishes executing. For example:

~~~sql
BEGIN;
ALTER TABLE demo.some_table ADD COLUMN note TEXT;
-- ALTER TABLE has returned, yet the transaction remains open.
-- The acquired lock stays held until COMMIT/ROLLBACK.
COMMIT;
~~~

The snippet above is **illustrative**; `demo.some_table` does not exist yet in the lab. Do not run it before setting up the practice tables later.

Consequence: **never open a transaction, run `ALTER TABLE`, and spend minutes manually inspecting before `COMMIT`ting.** Even a millisecond DDL keeps its strong lock held throughout the entire wait.

---

## 3. Relation Lock Modes to Remember

PostgreSQL defines eight relation-level lock modes:

| Lock mode | Key characteristics / common operations |
|---|---|
| `ACCESS SHARE` | Acquired by plain `SELECT`; conflicts only with `ACCESS EXCLUSIVE` |
| `ROW SHARE` | Acquired on the relation by `SELECT ... FOR UPDATE/SHARE` and row-locking variants alongside row locks |
| `ROW EXCLUSIVE` | Acquired by `INSERT`, `UPDATE`, `DELETE`, `MERGE`, and write operations |
| `SHARE UPDATE EXCLUSIVE` | Acquired by plain `VACUUM`, `ANALYZE`, `CREATE INDEX CONCURRENTLY`, and some `ALTER`/maintenance commands |
| `SHARE` | Typical for regular `CREATE INDEX`; allows reads but conflicts with data writes |
| `SHARE ROW EXCLUSIVE` | Certain constraint changes like `ALTER TABLE ... ADD FOREIGN KEY`; conflicts with normal writes |
| `EXCLUSIVE` | Strong mode; still compatible with `ACCESS SHARE` while blocking many other modes |
| `ACCESS EXCLUSIVE` | Strongest mode; conflicts with all other modes, including plain `SELECT` reads |

**Important:** the right column lists common examples, not a rule that one SQL statement takes only one lock. A single statement can lock **multiple relations** (tables, indexes, referenced tables) with different lock types across objects.

### 3.1. Core Conflict Pairs

| Lock mode pair | Conflicts? | Meaning |
|---|---|---|
| `ACCESS SHARE` – `ACCESS EXCLUSIVE` | **Yes** | `SELECT` is blocked by strong `ALTER TABLE` locks |
| `ACCESS SHARE` – `SHARE` | **No** | Regular `CREATE INDEX` still allows `SELECT` |
| `ROW EXCLUSIVE` – `SHARE` | **Yes** | `INSERT/UPDATE/DELETE` are blocked by regular `CREATE INDEX` |
| `ROW EXCLUSIVE` – `SHARE UPDATE EXCLUSIVE` | **No** | Plain `VACUUM` and `CREATE INDEX CONCURRENTLY` coexist with normal DML |
| `SHARE UPDATE EXCLUSIVE` – itself | **Yes** | Two maintenance tasks taking this mode on the same table wait on each other |
| `ROW EXCLUSIVE` – `ACCESS EXCLUSIVE` | **Yes** | Strong `ALTER TABLE` blocks writes |
| `ACCESS SHARE` – `SHARE UPDATE EXCLUSIVE` | **No** | Plain `VACUUM` does not block `SELECT` under this mode pair |
| `ROW SHARE` – `EXCLUSIVE` | **Yes** | `EXCLUSIVE` blocks queries that take row locks |

This table covers **representative pairs**, not PostgreSQL's full lock compatibility matrix. Beyond relation locks, operations can still wait on row locks, I/O, CPU, or other transactions.

### 3.2. Which Operations Block Reads vs. Writes?

| Operation on target table | Typical mode | Plain `SELECT` | `INSERT/UPDATE/DELETE` |
|---|---|---|---|
| `ALTER TABLE ADD COLUMN` | `ACCESS EXCLUSIVE` | Waits | Waits |
| `CREATE INDEX` | `SHARE` | Usually runs | Waits |
| `CREATE INDEX CONCURRENTLY` | `SHARE UPDATE EXCLUSIVE` | Usually runs | Usually runs |
| Plain `VACUUM` | `SHARE UPDATE EXCLUSIVE` | Usually runs | Usually runs |
| `ANALYZE` | `SHARE UPDATE EXCLUSIVE` | Usually runs | Usually runs |
| `VACUUM FULL` | `ACCESS EXCLUSIVE` | Waits | Waits |
| `CLUSTER` | `ACCESS EXCLUSIVE` | Waits | Waits |

The last two columns reflect **basic relation-lock conflicts**. "Usually runs" does not mean guaranteed fast, immune to other blocks, or free of CPU/I/O pressure.

---

## 4. Setting Up a Dedicated Lab Schema

Create a schema and sample orders table. Run only in a database authorized for practice:

~~~sql
CREATE SCHEMA IF NOT EXISTS lock_lab;

CREATE TABLE lock_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new',
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes TEXT
);

INSERT INTO lock_lab.orders (customer_id, status, amount)
VALUES
    (101, 'new', 150),
    (102, 'paid', 250),
    (101, 'paid', 90),
    (103, 'new', 300),
    (104, 'paid', 420);

SELECT order_id, customer_id, status, amount, created_at
FROM lock_lab.orders
ORDER BY order_id;
~~~

The table holds five sample orders. Do not re-run `INSERT` on the same table when expecting exactly five rows, as the `order_id` identity keeps incrementing and adding duplicate rows.

A customers table for foreign-key practice:

~~~sql
CREATE TABLE lock_lab.customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL
);

INSERT INTO lock_lab.customers (customer_id, customer_name)
VALUES
    (101, 'An'),
    (102, 'Bình'),
    (103, 'Chi'),
    (104, 'Dũng');
~~~

### 4.1. Two Connection Sessions

Open **two independent connections** to the same lab database, called **Session A** and **Session B**. Use two `psql` windows or two distinct connections—never run two-session examples sequentially on a single connection.

To check PIDs for monitoring:

~~~sql
SELECT pg_backend_pid() AS current_pid;
~~~

### 4.2. Lab Purpose

The examples below use `ROLLBACK` so **test `ALTER`s or updates are not persisted**. Examples like `CREATE INDEX CONCURRENTLY` and special maintenance commands cannot run inside a transaction block, so they are demonstrated separately rather than wrapped in a rollback transaction.

---

## 5. ALTER TABLE: Assume Strong Locks by Default

### 5.1. Why Does ALTER TABLE Need Locks?

`ALTER TABLE` alters the structure or rules of a relation, such as:

- Adding, dropping, or changing column types.
- Renaming columns or tables.
- Adding or dropping constraints.
- Setting or dropping `NOT NULL`.
- Modifying partitions, triggers, and metadata.
- Changing defaults, storage, generated expressions, or other attributes.

So other transactions never read or write against a half-updated structure, PostgreSQL acquires appropriate locks on the relation and sometimes dependent relations.

**Safe rule:** many `ALTER TABLE` forms acquire `ACCESS EXCLUSIVE` **except subcommands explicitly documented to take a weaker lock**. Exact lock level depends on the **subcommand** and sometimes PostgreSQL version.

### 5.2. Adding a Nullable Column: Fast Metadata Still Takes ACCESS EXCLUSIVE

Lab example:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

ALTER TABLE lock_lab.orders
    ADD COLUMN shipping_note TEXT;

-- Pause here only in the lab to observe; do not hold long.
ROLLBACK;
~~~

Adding a nullable column with no default does not rewrite table data, so execution itself is near-instant. Still, acquiring **`ACCESS EXCLUSIVE`** must wait for active transactions holding `ACCESS SHARE`, `ROW EXCLUSIVE`, or conflicting locks; and once acquired, it blocks queries until the transaction ends.

**Never infer:** "no table rewrite" ⇒ "no table lock."

### 5.3. Adding a Constant DEFAULT Column: Rewrite Optimization vs. Lock Mode

In modern PostgreSQL versions, adding a column with a **non-volatile `DEFAULT`** avoids rewriting every existing row at `ALTER` time. Example:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

ALTER TABLE lock_lab.orders
    ADD COLUMN channel TEXT DEFAULT 'web';

ROLLBACK;
~~~

This dramatically cuts **execution time**, yet it still requires the strong relation lock. Conversely, a default using a **volatile expression** forces PostgreSQL to compute and rewrite row data depending on the expression.

### 5.4. ALTER TYPE: Risks of Scans/Rewrites, Indexes, and Long Locks

Illustrative example:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

ALTER TABLE lock_lab.orders
    ALTER COLUMN status TYPE VARCHAR(40);

ROLLBACK;
~~~

Not every type change rewrites the heap; it depends on source/target types, casts, and internal representation. However, many type changes can:

- Read and rewrite massive volumes of data.
- Rebuild affected indexes.
- Generate heavy WAL and I/O pressure.
- Hold a strong lock for a long duration.

Never deploy a type change on a huge table solely because it finished instantly on a five-row lab table.

### 5.5. Dropping a Column: Fast Completion Does Not Mean Zero Downstream Cost

~~~sql
BEGIN;
ALTER TABLE lock_lab.orders DROP COLUMN notes;
ROLLBACK;
~~~

In many cases, dropping a column is a metadata change (old physical values are not immediately stripped from tuples). Still, it requires `ACCESS EXCLUSIVE` and does not immediately reclaim disk space.

### 5.6. Single ALTER TABLE with Multiple Subcommands

~~~sql
BEGIN;
ALTER TABLE lock_lab.orders
    ADD COLUMN source_system TEXT,
    ALTER COLUMN status SET DEFAULT 'new';
ROLLBACK;
~~~

When combining subcommands, the lock level taken covers the **strongest subcommand** in that `ALTER TABLE` statement. Never assume a weaker subcommand's lock mode applies to the whole multi-action statement.

---

## 6. Adding and Validating Constraints with ALTER TABLE

### 6.1. Constraints Enforce Data Integrity Yet May Require Heavy Scans

Example adding a `CHECK` on a large table:

~~~sql
ALTER TABLE lock_lab.orders
    ADD CONSTRAINT chk_order_status
    CHECK (status IN ('new', 'paid', 'canceled'));
~~~

This is not a zero-downtime default. PostgreSQL must scan existing rows to verify all satisfy `CHECK` while holding a strong lock. On large tables, scanning plus lock waiting can cause major disruption.

In the lab, avoid running this repeatedly once the constraint exists; treat it as a schema-change pattern.

### 6.2. Two-Step Pattern: ADD CHECK NOT VALID → VALIDATE

To decouple installing the rule from scanning historical rows:

~~~sql
ALTER TABLE lock_lab.orders
    ADD CONSTRAINT chk_order_status
    CHECK (status IN ('new', 'paid', 'canceled'))
    NOT VALID;
~~~

Then, at a suitable time:

~~~sql
ALTER TABLE lock_lab.orders
    VALIDATE CONSTRAINT chk_order_status;
~~~

How this works:

1. `ADD ... NOT VALID` installs the constraint **without scanning existing rows during the add step**.
2. New writes or row updates must obey the constraint per constraint semantics; `NOT VALID` **does not let new data bypass the `CHECK`**.
3. `VALIDATE CONSTRAINT` scans historical rows to transition the constraint to validated status.
4. `VALIDATE CONSTRAINT` takes **`SHARE UPDATE EXCLUSIVE`** on the validated table—weaker than `ACCESS EXCLUSIVE`, allowing normal DML concurrently.

Key takeaway: **`ADD ... NOT VALID` is still an `ALTER TABLE` requiring a strong lock**, just held far more briefly because it skips the table scan. It does not eliminate the need to plan constraint rollouts carefully.

### 6.3. FOREIGN KEY: Two Tables Involved

Example on the lab schema:

~~~sql
ALTER TABLE lock_lab.orders
    ADD CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id)
    REFERENCES lock_lab.customers(customer_id)
    NOT VALID;
~~~

`ADD FOREIGN KEY` is a case where PostgreSQL acquires **`SHARE ROW EXCLUSIVE`** on both the referencing and referenced tables, rather than `ACCESS EXCLUSIVE`. That mode **conflicts with normal writes** on both relations, so consider traffic on both `orders` and `customers`.

Validate afterward:

~~~sql
ALTER TABLE lock_lab.orders
    VALIDATE CONSTRAINT fk_orders_customer;
~~~

Validation scans rows while using a lighter lock so normal writes continue on the validated table, subject to other system locks.

### 6.4. CHECK NOT VALID Does Not Fix Existing Bad Data

If historical rows violate the constraint, `ADD ... NOT VALID` succeeds, yet `VALIDATE CONSTRAINT` will **fail** until bad data is cleaned up. Thus two-step migrations often have three phases:

~~~text
ADD CONSTRAINT ... NOT VALID
          |
          v
Inspect and clean legacy data in batches
          |
          v
VALIDATE CONSTRAINT
~~~

Never treat `NOT VALID` status as a completed migration.

### 6.5. SET NOT NULL May Require a Table Scan

~~~sql
ALTER TABLE lock_lab.orders
    ALTER COLUMN status SET NOT NULL;
~~~

Unless PostgreSQL already has valid proof that no `NULL`s exist, `SET NOT NULL` scans the table to verify. In supported versions, a **validated `CHECK` constraint proving the column is not `NULL`** allows skipping that verification scan. Even then, the `ALTER` subcommand still acquires its own lock; never confuse "skip scan" with "no lock."

---

## 7. Why Can a Waiting ALTER TABLE Cause a Queueing Cascade?

A classic deployment outage:

1. An old query holds `ACCESS SHARE` or a write transaction holds `ROW EXCLUSIVE` on the table.
2. A migration requests `ACCESS EXCLUSIVE` and **must wait**.
3. **New** `SELECT`/`INSERT`/`UPDATE` statements arriving afterward queue behind the waiting request to prevent starving it.
4. Even before `ALTER` executes a single change, application latency and timeouts spike sharply.

~~~text
T=0    Long SELECT/report holds ACCESS SHARE
T=1    ALTER TABLE requests ACCESS EXCLUSIVE → WAITING
T=2    New SELECT requests ACCESS SHARE      → WAITING behind ALTER
T=3    Incoming API requests keep piling up
T=...  Old report finishes → ALTER acquires lock
       ALTER finishes and COMMITs → queued requests resume
~~~

### 7.1. Execution Time Alone Does Not Determine Risk

Even an `ADD COLUMN` nullable operation that runs in milliseconds alone can **wait a long time** for its lock if a long transaction is open. Once acquired, if the migration transaction does not `COMMIT` immediately, the strong lock stays held.

### 7.2. Time Out Early to Avoid Long Queues

A cautious pattern:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE lock_lab.orders
    ADD COLUMN external_ref TEXT;

COMMIT;
~~~

In production, pick timeouts based on deployment policy, traffic load, and retry budgets. When `lock_timeout` fires, the transaction enters an aborted state; you must **`ROLLBACK`** instead of sending more statements. Never retry continuously without backoff, or you will create repeated DDL queue spikes.

### 7.3. Keep the DDL Transaction Tiny

Better:

~~~text
Prepare migration, verify data, agree on rollback
        |
        v
BEGIN → SET LOCAL lock_timeout → ALTER → COMMIT
        |
        v
Verify results in a new transaction
~~~

Avoid:

~~~text
BEGIN → ALTER → wait 10 minutes for manual engineer review
      → call another API → take screenshots → COMMIT
~~~

The lock stays held across all unnecessary steps, causing an outage on the entire table.

---

## 8. Regular CREATE INDEX

### 8.1. Adding an Index Also Protects the Relation

Example:

~~~sql
CREATE INDEX ix_orders_customer_created
ON lock_lab.orders (customer_id, created_at);
~~~

Regular `CREATE INDEX` scans table data to build the index. On normal tables it acquires a `SHARE` lock on the table, with these properties:

- Allows plain `SELECT`s (`ACCESS SHARE` is compatible).
- **Blocks `INSERT`, `UPDATE`, and `DELETE`** because writes require `ROW EXCLUSIVE`.
- Delayed by existing transactions/DDL/maintenance holding conflicting locks.
- On huge tables, build duration is long → write outage duration is long.

### 8.2. Being Readable Does Not Mean Zero Impact

While building an index, the table can still serve `SELECT`s, yet scan/sort I/O and CPU can slow queries down. Lock blocking of writes and hardware resource pressure are **two distinct sources of impact**.

### 8.3. CREATE INDEX Inside a Transaction

Regular `CREATE INDEX` can run inside an explicit transaction, e.g. in the lab:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

CREATE INDEX ix_orders_status_lab
ON lock_lab.orders (status);

ROLLBACK;
~~~

After `ROLLBACK`, the new index is discarded. However, **the `SHARE` lock stays held until the transaction ends**, so never run it in a transaction and pause to inspect in a GUI before committing or rolling back.

### 8.4. Does Indexing Lock Multiple Relations?

An index command touches the table, new index, and system catalogs. When inspecting `pg_locks`, never assume only one lock row exists for one statement.

### 8.5. Relation Locks vs. Row Locks

If plain `SELECT`s are not table-blocked by `CREATE INDEX` yet run slowly, the cause may be CPU/I/O contention or other operations' locks. Inspect `wait_event_type` and execution plans instead of blaming every slowdown on relation locks.

---

## 9. CREATE INDEX CONCURRENTLY: Less Write Blocking, Not Free

When an application must keep writing while building an index on a large table, PostgreSQL offers:

~~~sql
CREATE INDEX CONCURRENTLY ix_orders_customer_created_c
ON lock_lab.orders (customer_id, created_at);
~~~

**Note:** run this only if the index name does not already exist; note the distinct name from Section 8. Key characteristics:

1. Does not block normal `INSERT`, `UPDATE`, `DELETE` via `SHARE` relation-lock conflicts like regular `CREATE INDEX`.
2. Must **scan the table multiple times** and **wait for concurrent transactions/snapshots**, taking longer overall.
3. Acquires `SHARE UPDATE EXCLUSIVE` on the table across phases; it is **not** "lock-free."
4. Can conflict with other DDL/maintenance, including commands also requiring `SHARE UPDATE EXCLUSIVE`.
5. **Cannot execute inside an explicit transaction block.**
6. Can leave behind an **`INVALID`** index if the build fails or is canceled.
7. Consumes extra disk space and significant I/O and CPU.

### 9.1. Wrong Example: Running Inside BEGIN

~~~sql
-- Wrong: PostgreSQL rejects CREATE INDEX CONCURRENTLY
-- inside an explicit transaction block.
BEGIN;
CREATE INDEX CONCURRENTLY ix_orders_status_c
ON lock_lab.orders (status);
ROLLBACK;
~~~

Because of this transaction-block restriction, any migration tool that wraps every migration in `BEGIN` must **disable transactional wrapping for that migration** using the tool's supported directive.

### 9.2. Do Not Use IF NOT EXISTS to Replace Definition Checks

~~~sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_status_c
ON lock_lab.orders (status);
~~~

`IF NOT EXISTS` only skips erroring if a relation with that name exists per DDL rules; **it does not prove the existing index has the right definition or is `VALID`**.

An index with the same name but wrong columns/predicate or `INVALID` state must still be verified in system catalogs.

### 9.3. Two Table Scans and Transaction Waits

High-level flow:

~~~text
CREATE INDEX CONCURRENTLY
        |
        v
Create initial index metadata (not yet usable)
        |
        v
Table scan pass 1
        |
        v
Wait for relevant writers / index updates
        |
        v
Table scan pass 2 to catch concurrent changes
        |
        v
Wait for older snapshots to finish
        |
        v
Mark index VALID upon successful completion
~~~

Exact phases depend on index type and PostgreSQL version. Monitor using `pg_stat_progress_create_index` and catalogs rather than guessing from a slow query.

### 9.4. Only One Concurrent Index Build per Table at a Time

`CREATE INDEX CONCURRENTLY` is not meant for launching dozens of parallel index builds on **the same table** at once. PostgreSQL restricts concurrent index builds on the same relation and their lock modes conflict. Schedule builds sequentially and watch total load.

### 9.5. Building a UNIQUE Index Concurrently: Clean Data First

~~~sql
-- Illustrative example; fails if duplicates exist:
CREATE UNIQUE INDEX CONCURRENTLY ux_orders_external_ref
ON lock_lab.orders (external_ref);
~~~

This assumes column `external_ref` exists (not present by default in the lab). A `UNIQUE` index fails if duplicates exist (subject to version/definition `NULL` rules). Notably, when building a **`UNIQUE INDEX CONCURRENTLY`**, uniqueness enforcement can begin affecting concurrent transactions **before the build finishes**, and a failed build leaves an invalid index that may still incur overhead or affect uniqueness depending on phase.

Therefore:

- Clean up duplicate data beforehand.
- Know the index's `NULL`/duplicate semantics.
- Monitor the build phases and catalog outcome.
- Prepare a plan to clean up an invalid index.
- Never auto-retry with the same name without checking catalog state first.

### 9.6. CONCURRENTLY on Partitioned Tables

PostgreSQL has restrictions on building a **partitioned index** concurrently directly on the parent. A common rollout strategy on large partitioned tables is creating indexes concurrently on each child partition where supported, then creating/attaching the parent index metadata per documented steps. Check your exact PostgreSQL version and partition layout—never copy non-partitioned SQL blindly onto a partitioned parent expecting it to behave identically.

### 9.7. Choosing CREATE INDEX vs. CREATE INDEX CONCURRENTLY

| Criterion | `CREATE INDEX` | `CREATE INDEX CONCURRENTLY` |
|---|---|---|
| Blocks table writes | Yes | Avoids normal DML blocking from build lock |
| Allows `SELECT` | Yes | Yes |
| Cost / duration | Usually less work | Multiple scans and longer duration |
| Runs inside `BEGIN` | Yes | **No** |
| Needs invalid-state monitoring | Simpler | Especially critical |
| Large table with continuous writes | Needs maintenance window | Usually preferred candidate |
| Zero production impact | **No** | **No** |

**Decision mindset:** decide based on availability requirements, table size, write traffic, time budget, and failure recovery—not shorter syntax.

---

## 10. Inspecting and Recovering INVALID Indexes

### 10.1. Concurrent Builds Can Fail After Creating Metadata

If `CREATE INDEX CONCURRENTLY` is canceled, runs out of resources, hits duplicates on a `UNIQUE` index, or errors, PostgreSQL can leave an index registered in catalogs that is **not valid for the query planner**.

Never check only that the index name exists and declare deployment successful.

### 10.2. Querying pg_index

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisvalid AS is_valid,
    i.indisready AS is_ready_for_inserts,
    i.indislive AS is_live,
    pg_get_indexdef(i.indexrelid) AS index_definition
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
JOIN pg_class AS tbl ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns ON ns.oid = tbl.relnamespace
WHERE ns.nspname = 'lock_lab'
  AND tbl.relname = 'orders'
ORDER BY index_name;
~~~

Key flags:

- `indisvalid`: index is valid for planner query usage.
- `indisready`: index is ready to receive updates from write operations.
- `indislive`: whether the index is still considered live internally.

These flags supplement—never replace—reading command errors and checking the actual index definition.

### 10.3. Common Recovery Paths

When you find an invalid index:

1. Verify the previous build command has **truly ended**, not still running.
2. Read the original error to distinguish duplicate data, resource exhaustion, deadlock, or timeout.
3. Check whether the index backs a constraint/uniqueness or has dependencies.
4. Per supported procedure, run **`DROP INDEX CONCURRENTLY`** to clean up and recreate, or use **`REINDEX CONCURRENTLY`** where appropriate.
5. Re-verify `indisvalid` and query usage.

Example for a **confirmed invalid test index not backing any constraint**, never run blindly:

~~~sql
DROP INDEX CONCURRENTLY IF EXISTS lock_lab.ix_orders_status_c;
~~~

`DROP INDEX CONCURRENTLY` has restrictions: cannot run inside a transaction block, cannot drop indexes enforcing constraints arbitrarily, and does not support `CASCADE` like regular `DROP INDEX`. Check dependencies before dropping.

### 10.4. Never Drop Indexes Recklessly as a Quick Fix

Indexes may enforce:

- Primary keys / unique constraints.
- Critical production query paths.
- Foreign key join paths.
- Uniqueness under concurrent writers.

Dropping an index without a recovery plan can turn **DDL contention into severe query slowdowns or broken invariants**. Check state and plans before acting.

---

## 11. REINDEX and REINDEX CONCURRENTLY

### 11.1. What Does REINDEX Solve?

`REINDEX` rebuilds an index from table data, useful when an index is corrupted, heavily bloated, requires storage/collation updates under operational procedures, or needs recommended maintenance.

Example:

~~~sql
REINDEX INDEX lock_lab.ix_orders_customer_created;
~~~

Run only when the index exists and with an approved plan. Regular `REINDEX` blocks writes on the source table during rebuild and can lock the index in ways that affect queries relying on it.

### 11.2. REINDEX CONCURRENTLY

~~~sql
REINDEX INDEX CONCURRENTLY lock_lab.ix_orders_customer_created;
~~~

Aims to rebuild the index with lighter DML blocking, similar in spirit to concurrent index builds. Keep in mind:

- Multi-phase and waits for concurrent transactions/snapshots.
- Consumes **extra disk space** because old and new index versions coexist during swap.
- **Cannot run inside an explicit transaction block.**
- Has restrictions on supported object types and system/shared catalogs.
- Can leave temporary/invalid index remnants if it fails in certain phases; inspect catalogs before retrying.

### 11.3. Do Not Confuse REINDEX with ANALYZE

`ANALYZE` updates statistics for the query planner; `REINDEX` rebuilds physical index structures. When a query suddenly picks a poor plan due to stale statistics, do not jump straight to `REINDEX` as a knee-jerk fix.

### 11.4. Do Not Confuse REINDEX with VACUUM

`VACUUM` handles dead tuples, visibility/freezing, and reusable space. `REINDEX` rebuilds indexes. They address related yet distinct problems with different costs and lock behavior.

---

## 12. Plain VACUUM and AUTOVACUUM

### 12.1. Why Is VACUUM Needed?

PostgreSQL uses MVCC: `UPDATE` creates new versions and `DELETE` marks old versions. Once no active snapshot needs old versions, they become dead tuples. `VACUUM` helps:

- Reclaim space inside pages for tuple reuse.
- Clean index/heap structures per engine rules.
- Update the visibility map and maintenance metadata.
- Freeze transaction IDs to prevent XID wraparound.

### 12.2. Plain VACUUM Uses a Lighter Lock

~~~sql
VACUUM lock_lab.orders;
~~~

Plain `VACUUM` acquires `SHARE UPDATE EXCLUSIVE` on the vacuumed table, which by lock compatibility **does not block plain `SELECT`/`INSERT`/`UPDATE`/`DELETE`**.

However:

- It can contend with DDL or maintenance taking the same or stronger mode.
- It consumes I/O and CPU and can impact latency.
- It may wait on other operations, or yield to conflicting lock requests per maintenance rules.
- Not all dead tuples can be removed if old snapshots, replication slots, or open transactions still need them.

### 12.3. VACUUM Cannot Run Inside a Transaction Block

**Wrong** example:

~~~sql
BEGIN;
VACUUM lock_lab.orders;
COMMIT;
~~~

PostgreSQL rejects plain `VACUUM` inside an explicit transaction block. Remember this when using migration frameworks that wrap every SQL file in a transaction.

### 12.4. Autovacuum

Autovacuum is PostgreSQL's background worker subsystem running `VACUUM`/`ANALYZE` automatically per thresholds. It is vital for:

- Periodically cleaning old row versions.
- Keeping planner statistics fresh.
- Keeping XID/MultiXact ages within safe limits.

Autovacuum also needs relation locks; it is not "conflict-free" with DDL. Normal autovacuum workers automatically yield to conflicting DDL lock requests, whereas anti-wraparound vacuums have special protection. **Never disable autovacuum just to let DDL run smoothly** without an alternative maintenance and XID-age plan.

### 12.5. VACUUM Does Not Always Shrink Files Immediately

Regular `VACUUM` marks space inside table files **reusable** rather than immediately shrinking OS file size for all dead tuples. Returning space to the OS typically requires trailing empty pages or a rewrite operation like `VACUUM FULL` with its heavy lock cost.

### 12.6. Long Transactions Block Dead Tuple Cleanup

~~~text
REPEATABLE READ reader holds an old snapshot
           |
           v
Writer UPDATE creates many versions → COMMIT
           |
           v
VACUUM sees versions may still be needed by reader
           |
           v
Cannot reclaim those versions prematurely
~~~

A bloated table is not always because "VACUUM didn't run"—often **VACUUM cannot reclaim** tuples because an old snapshot/horizon is pinned open.

---

## 13. ANALYZE: Collecting Statistics with Maintenance Locks

### 13.1. What Does ANALYZE Do?

~~~sql
ANALYZE lock_lab.orders;
~~~

`ANALYZE` gathers statistics for the planner, such as value distributions, row counts, selectivity, and histograms. It **does not** build indexes and **does not** rewrite the table to compact files.

### 13.2. Why Does It Need a Lock?

Because `ANALYZE` reads the relation and updates statistics metadata consistently, it acquires `SHARE UPDATE EXCLUSIVE`. This is compatible with normal reads/writes, yet conflicts with:

- `VACUUM` and maintenance taking the same mode.
- `CREATE INDEX CONCURRENTLY` on the same table.
- Stronger `ALTER TABLE` locks.
- Commands requiring `SHARE`/`ACCESS EXCLUSIVE`.

### 13.3. When to Run ANALYZE Proactively?

- After a large bulk load.
- After major data distribution shifts while statistics are still stale.
- When a query switches to a poor plan and `EXPLAIN` shows wildly inaccurate row estimates.
- After special maintenance/migrations where the planner needs fresh stats.

Avoid running `ANALYZE` blindly and repeatedly on huge tables during peak hours; autovacuum often handles normal workloads.

### 13.4. ALTER and ANALYZE: Rollout Order

When adding columns or backfilling bulk data then indexing:

~~~text
Valid schema migration
       |
       v
Batch backfill / bulk load (if needed)
       |
       v
Create index / verify VALID status
       |
       v
ANALYZE when appropriate
       |
       v
EXPLAIN critical queries
~~~

Depending on workload, `ANALYZE` may fit at a different step. Just never treat `ANALYZE` as a magic cure for every slow query without inspecting the plan.

---

## 14. VACUUM FULL and CLUSTER: Rewriting Tables Under ACCESS EXCLUSIVE

### 14.1. VACUUM FULL Differs from Regular VACUUM

~~~sql
-- Illustrative only; never run in production without a
-- maintenance window and disk/lock calculations.
VACUUM FULL lock_lab.orders;
~~~

`VACUUM FULL` rewrites the table into a compact copy to reclaim physical disk space. It acquires `ACCESS EXCLUSIVE` on the table and **blocks both `SELECT` and DML** for its entire duration.

Consequences:

- Large tables experience long outages.
- Requires **extra free disk space** for the rewrite copy and rebuilt indexes.
- Generates massive WAL and can cause replication lag.
- Changes tuple `ctid`s.
- Cannot run inside an explicit transaction block.

### 14.2. CLUSTER

~~~sql
-- Practice only in a lab database once costs and locks are understood.
CLUSTER lock_lab.orders USING ix_orders_customer_created;
~~~

`CLUSTER` physically reorders table data to match a chosen index. In its standard form, it requires `ACCESS EXCLUSIVE` and blocks reads and writes during the rewrite.

`CLUSTER` does not preserve physical order across subsequent `INSERT`/`UPDATE`s. If you need sorted `SELECT` output, **always use `ORDER BY`**, never rely on a prior `CLUSTER`.

### 14.3. Comparison

| Feature | Plain `VACUUM` | `VACUUM FULL` | `CLUSTER` |
|---|---|---|---|
| Purpose | Clean dead tuples / visibility / freeze | Compact table rewrite | Rewrite physically ordered by index |
| Typical lock | `SHARE UPDATE EXCLUSIVE` | `ACCESS EXCLUSIVE` | `ACCESS EXCLUSIVE` |
| Plain `SELECT` | Not blocked by relation lock | Blocked | Blocked |
| Normal DML | Not blocked by relation lock | Blocked | Blocked |
| Disk / WAL | Depends on cleanup; no full rewrite | Can be huge | Can be huge |
| Transaction block | No | No | Depends on command/version rules; schedule separately |
| Reclaiming OS disk space | Not guaranteed | Suited when true compaction is needed | Reordering rewrite, not primarily a bloat tool |

### 14.4. Caution with Replicas

Rewrite maintenance generates massive WAL, replication load, and I/O; standbys may hit query conflicts depending on settings. Maintenance plans must evaluate not only the primary, but also:

- Replica count and acceptable lag.
- WAL volume generated and retention capacity.
- Free disk space on both primary and replicas.
- Read/write outage duration on the primary.
- Failover strategy if maintenance runs into trouble.

---

## 15. Other Maintenance Commands and Lock Scope

### 15.1. TRUNCATE

~~~sql
-- Illustrative only; NEVER run on tables with data you want to keep.
TRUNCATE TABLE lock_lab.orders;
~~~

`TRUNCATE` acquires `ACCESS EXCLUSIVE` on the target table and is unsuitable when concurrent `SELECT` transactions must keep running. It also has different semantics from `DELETE` (triggers, identity sequences, locks, MVCC snapshots), so **never swap `DELETE` for `TRUNCATE` just for speed**.

### 15.2. REFRESH MATERIALIZED VIEW

When using materialized views, PostgreSQL supports:

~~~sql
REFRESH MATERIALIZED VIEW some_schema.sales_summary;
~~~

and:

~~~sql
REFRESH MATERIALIZED VIEW CONCURRENTLY some_schema.sales_summary;
~~~

The view name here is **illustrative** and does not exist in the lab. Standard refresh takes a strong lock on **the materialized view**, blocking readers during refresh; `CONCURRENTLY` avoids blocking readers, subject to prerequisites such as **an appropriate `UNIQUE` index covering all rows without expressions/`WHERE` predicates** and other restrictions.

Do not confuse `REFRESH ... CONCURRENTLY` with `CREATE INDEX CONCURRENTLY`: they solve different problems with different prerequisites.

### 15.3. ATTACH PARTITION

On partitioned tables, `ALTER TABLE ... ATTACH PARTITION` has specialized locking: the parent partitioned table often takes `SHARE UPDATE EXCLUSIVE` instead of `ACCESS EXCLUSIVE`, whereas the attached partition and related tables may require **stronger locks** or a validation scan of partition bounds.

A pre-validated `CHECK` constraint matching the partition bounds on the child table lets PostgreSQL skip that validation scan. Never assign a single lock mode to the whole `ATTACH` operation since **multiple relations** are involved.

### 15.4. Adding PRIMARY KEY/UNIQUE Constraints Using a Pre-Built Index

On large tables, a strategy to minimize write blocking:

1. Build a **matching unique index** using `CREATE UNIQUE INDEX CONCURRENTLY`.
2. Verify the index is `VALID` and matches constraint requirements.
3. Run `ALTER TABLE ... ADD CONSTRAINT ... USING INDEX` to attach the existing index instead of building an index under a strong `ALTER` lock.

Illustrative example (not an existing index name):

~~~sql
-- Step 1, run outside a transaction block:
CREATE UNIQUE INDEX CONCURRENTLY ux_orders_external_code
ON lock_lab.orders (external_code);

-- Step 2, after verifying VALID, in a separate migration:
ALTER TABLE lock_lab.orders
ADD CONSTRAINT uq_orders_external_code
UNIQUE USING INDEX ux_orders_external_code;
~~~

**Conditions:** `external_code` must already exist; the unique index must be valid, non-partial, non-expression, and match constraint rules. The `ALTER` step still takes a DDL lock, just briefly since index building is already done. For `PRIMARY KEY`, `NOT NULL` enforcement and checks may add time/locks; read the exact rules for your target PostgreSQL version.

---

## 16. How Index Build and VACUUM Locks Conflict

Common scenarios:

### 16.1. CREATE INDEX CONCURRENTLY vs. VACUUM

Both use `SHARE UPDATE EXCLUSIVE` on the same table during relevant phases. That mode **conflicts with itself**.

~~~text
VACUUM orders: holds SHARE UPDATE EXCLUSIVE
        |
        v
CREATE INDEX CONCURRENTLY orders: waits for lock
~~~

Or vice versa. This is why you should check active maintenance before starting an index build, even though neither blocks normal DML.

### 16.2. Regular CREATE INDEX vs. Writers

~~~text
Writer (INSERT/UPDATE): ROW EXCLUSIVE
             ↕  conflict
Regular CREATE INDEX: SHARE
~~~

If writers hold open transactions, `CREATE INDEX` waits. Once `CREATE INDEX` acquires `SHARE`, incoming writes wait until the index build and its transaction finish.

### 16.3. ALTER TABLE vs. SELECT

~~~text
SELECT: ACCESS SHARE
           ↕  conflict
ALTER TABLE ADD COLUMN: ACCESS EXCLUSIVE
~~~

A long `SELECT` or a transaction holding `ACCESS SHARE` delays `ALTER`; while `ALTER` waits, incoming `SELECT`s also queue up.

### 16.4. Do Not Equate Lock Waits with I/O Waits

From an application perspective, a "slow" SQL statement may be:

- Waiting on a relation lock.
- Waiting on a transaction ID / row lock.
- Waiting on I/O reading tables or indexes.
- Burning CPU sorting/hashing or writing WAL.
- Hit by throttling, checkpoints, replication, or network delays.

Only wait events, query plans, and metrics distinguish them. Never raise `lock_timeout` to cure CPU/I/O saturation.

---

## 17. Lock Duration and Transaction Boundaries

### 17.1. A Brief DDL Statement Can Still Hold Locks Long

Lab-only example:

~~~sql
BEGIN;

ALTER TABLE lock_lab.orders
    ADD COLUMN migration_flag BOOLEAN DEFAULT false;

-- DDL already finished executing, yet transaction has not COMMITted.
-- Do not pause here to do other work.
ROLLBACK;
~~~

If you keep the transaction open for minutes after `ALTER`, competing transactions wait even though adding the column finished long ago.

### 17.2. Failed Statements Inside a Transaction

When `ALTER TABLE` hits `lock_timeout` inside a transaction, the transaction enters an **aborted** state. Subsequent normal SQL statements fail with `25P02`.

Recovery:

~~~sql
ROLLBACK;
~~~

Never send a second DDL statement inside the same aborted transaction, and never try `COMMIT` expecting to push past the error. Migration tools must close the failed unit of work and perform bounded retries later.

### 17.3. lock_timeout Is Not statement_timeout

| Option | Limits what? | Example |
|---|---|---|
| `lock_timeout` | Time waiting **to acquire a lock** | DDL does not queue 60s behind a long `SELECT` |
| `statement_timeout` | Time spent **executing the statement** | `ALTER`/`CREATE INDEX` does not run past a 30-minute policy |
| `idle_in_transaction_session_timeout` | Time a session sits idle inside a transaction | Prevents abandoned `BEGIN` after DDL |
| `deadlock_timeout` | Wait time before deadlock check / lock-wait logging | Do not tweak arbitrarily as a tuning trick |
| Application/job timeout | Total request/migration budget | Deploy job fails cleanly if budget is exceeded |

`SET LOCAL` inside a transaction isolates parameter changes to that transaction scope:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE lock_lab.orders
    ADD COLUMN app_tag TEXT;

ROLLBACK;
~~~

For `CREATE INDEX CONCURRENTLY` (which cannot run inside `BEGIN`), set timeouts **at the session or client level** carefully, and reset/restore the session afterward—never put `SET LOCAL` outside a transaction expecting it to stick for the next command.

---

## 18. Monitoring Lock Waits with pg_stat_activity

When the app reports "every `SELECT` suddenly slowed down during deploy," first find **which backends are waiting** and **what they are waiting on**, rather than blindly killing processes.

### 18.1. Inspecting Active Sessions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    LEFT(query, 180) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST, query_start NULLS LAST;
~~~

Fields:

| Field | How to read |
|---|---|
| `pid` | Backend process ID |
| `application_name` | Identifies service/migration job when configured by client |
| `state` | `active`, `idle`, `idle in transaction`, etc. |
| `xact_start` | Start time of current open transaction, if any |
| `query_start` | Start time of current/last statement |
| `wait_event_type` | Wait category, e.g. `Lock` or `IO` |
| `wait_event` | Specific wait event |
| `query` | Running/last SQL; may contain sensitive data and is privilege-restricted |

**Warning:** when `state` is `idle in transaction`, `query` shows the **most recently executed** statement, not "currently running SQL." A backend can block others even while appearing idle.

### 18.2. Filtering Sessions Waiting on Locks

~~~sql
SELECT
    pid,
    application_name,
    state,
    wait_event,
    now() - query_start AS waiting_duration,
    LEFT(query, 180) AS statement
FROM pg_stat_activity
WHERE datname = current_database()
  AND wait_event_type = 'Lock'
ORDER BY query_start;
~~~

`wait_event_type='Lock'` reports waiting on a lock, where `wait_event` may be `relation`, `transactionid`, `virtualxid`, or another lock type. Do not assume every lock wait is an `ALTER TABLE` table lock.

### 18.3. xact_start Differs from query_start

- `xact_start` exposes long-lived open transactions.
- `query_start` shows when the current/last statement started.
- `state_change` (if selected) shows when the backend entered its current state.

A session whose statement already finished while its transaction stays open **has not released its locks**.

---

## 19. Identifying Blockers with pg_blocking_pids()

### 19.1. Quick Query for Blocked Sessions

~~~sql
SELECT
    a.pid AS waiting_pid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    LEFT(a.query, 180) AS waiting_query
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.pid;
~~~

`pg_blocking_pids(pid)` returns an array of PIDs blocking the target backend per PostgreSQL's lock analysis. It is far more reliable than manually joining `pg_locks` by relation, since waits also involve **lock queues** and multiple lock types.

### 19.2. Showing Each Blocker Alongside Its Query

~~~sql
SELECT
    waiting.pid AS waiting_pid,
    waiting.application_name AS waiting_app,
    waiting.wait_event_type,
    waiting.wait_event,
    blocking.pid AS blocking_pid,
    blocking.application_name AS blocking_app,
    blocking.state AS blocking_state,
    blocking.xact_start AS blocking_xact_start,
    LEFT(waiting.query, 160) AS waiting_sql,
    LEFT(blocking.query, 160) AS blocking_sql
FROM pg_stat_activity AS waiting
CROSS JOIN LATERAL unnest(
    pg_blocking_pids(waiting.pid)
) AS blocker(blocking_pid)
JOIN pg_stat_activity AS blocking
  ON blocking.pid = blocker.blocking_pid
WHERE waiting.datname = current_database()
ORDER BY waiting.pid, blocking.pid;
~~~

This reveals `idle in transaction` backends holding locks even when their last SQL looks like a `SELECT` or a finished `ALTER`.

Never automatically terminate a blocker without knowing:

- Who owns the transaction?
- Is it processing a payment or a half-finished migration?
- Will interrupting roll back minutes of work or corrupt application state?
- Is there a safer option, such as asking the service to commit/roll back, shedding load, or shortening timeouts?

### 19.3. Blocking PID Is Not the Entire Story

A backend can wait on a granted lock holder **or** a waiter ahead of it in the queue. Always interpret "A blocks B" in the context of the full wait chain and live workload.

If the blocker is a DDL transaction itself, verify who owns the session and whether commit/rollback ran rather than guessing from the last query string.

---

## 20. Inspecting Relation Locks in Detail via pg_locks

### 20.1. Viewing Locks on the orders Table

~~~sql
SELECT
    l.pid,
    a.application_name,
    a.state,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name,
    l.waitstart
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a ON a.pid = l.pid
WHERE l.relation = 'lock_lab.orders'::regclass
ORDER BY l.granted, l.pid, l.mode;
~~~

`granted=true`: lock is currently held.

`granted=false`: backend is waiting for that lock. For certain locks, `pid` may be `NULL` (e.g., prepared transactions), so do not assume every lock maps to a live backend in `pg_stat_activity`.

`waitstart` can be `NULL` right as waiting begins or when not applicable; never rely solely on `waitstart` to establish full blocker ordering.

### 20.2. Viewing All Relation Locks in the Lab Schema

~~~sql
SELECT
    l.pid,
    a.application_name,
    l.relation::regclass AS relation_name,
    l.mode,
    l.granted
FROM pg_locks AS l
JOIN pg_class AS c ON c.oid = l.relation
JOIN pg_namespace AS n ON n.oid = c.relnamespace
LEFT JOIN pg_stat_activity AS a ON a.pid = l.pid
WHERE n.nspname = 'lock_lab'
  AND l.locktype = 'relation'
ORDER BY relation_name::text, l.pid, l.mode;
~~~

A single statement can hold locks on tables, indexes, and dependent objects. Never count rows in `pg_locks` assuming it shows how many table rows are locked. **Normal row-level locks do not each appear as separate rows in `pg_locks`**; row-update waits show up via `transactionid`/tuple locks.

### 20.3. Never Look Only at mode and Ignore granted

A row showing:

~~~text
mode = AccessExclusiveLock
granted = false
~~~

means the backend is **waiting for** `ACCESS EXCLUSIVE`, not that it already holds exclusive control of the table. Still, that waiting request can stall incoming requests behind it in the queue.

### 20.4. Never Edit Catalogs / pg_locks

`pg_locks` is a diagnostic view, not a table for `UPDATE` or `DELETE`. Resolve conflicts by **ending transactions, adjusting schedules/timeouts, or handling sessions via operational runbooks**—never by trying to "delete a lock row" in SQL.

---

## 21. Monitoring CREATE INDEX CONCURRENTLY via Progress Views

### 21.1. pg_stat_progress_create_index

On PostgreSQL versions supporting it, while an index build is running:

~~~sql
SELECT
    p.pid,
    p.datname,
    p.relid::regclass AS table_name,
    p.index_relid::regclass AS index_name,
    p.command,
    p.phase,
    p.lockers_total,
    p.lockers_done,
    p.current_locker_pid,
    p.blocks_total,
    p.blocks_done,
    p.tuples_total,
    p.tuples_done
FROM pg_stat_progress_create_index AS p
WHERE p.datname = current_database()
ORDER BY p.pid;
~~~

The `phase` column is key to seeing whether the build is:

- Initializing or waiting for writers.
- Building the index from table data.
- Validating the index.
- Waiting for old snapshots to finish.
- Running other phases per version and index access method.

Exact phase names vary by version. Seeing zero rows means **no index build is currently running**, not that an earlier index is `VALID`.

### 21.2. Diagnosing a "Stalled" Build

When an index build takes a long time:

1. Check `phase`.
2. If waiting on lockers/writers/snapshots, inspect `pg_blocking_pids()` and long transactions.
3. If scanning/building, watch `blocks`/`tuples` progress (not all phases update every counter).
4. Check I/O, disk space, WAL/replica lag, and autovacuum activity.
5. Once finished, verify `pg_index.indisvalid`.

Never divide `blocks_done / blocks_total` as an overall "% complete" for the entire job, since a build has multiple phases with different costs.

### 21.3. Missing Progress Rows Do Not Mean Zero Impact

Fast commands finish before appearing in the view. Large commands can sit in a waiting phase with zero block progress. Combine progress views with `pg_stat_activity` and system metrics.

---

## 22. Monitoring VACUUM, ANALYZE, and CLUSTER

### 22.1. Plain VACUUM Progress

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count
FROM pg_stat_progress_vacuum
WHERE datname = current_database()
ORDER BY pid;
~~~

Fits regular `VACUUM`, showing phases like scanning heap, vacuuming indexes, vacuuming heap, and cleaning up indexes (depending on PostgreSQL version). `VACUUM FULL` uses the rewrite path reported in `pg_stat_progress_cluster`.

### 22.2. VACUUM FULL / CLUSTER Rewrites

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    command,
    phase,
    heap_tuples_scanned,
    heap_tuples_written
FROM pg_stat_progress_cluster
WHERE datname = current_database()
ORDER BY pid;
~~~

`pg_stat_progress_cluster` reports rewrite progress for `CLUSTER` and `VACUUM FULL`. With huge tuple counts, monitor duration and disk headroom; progress visibility does not mean you can pause and resume mid-rewrite.

### 22.3. ANALYZE Progress

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS table_name,
    phase,
    sample_blks_total,
    sample_blks_scanned
FROM pg_stat_progress_analyze
WHERE datname = current_database()
ORDER BY pid;
~~~

Available progress views and columns depend on **PostgreSQL version**. On older versions lacking a view, inspect `pg_stat_activity` and OS monitoring rather than assuming the command is not running.

### 22.4. Post-Maintenance Verification

After maintenance completes:

- Confirm the command returned success.
- Check index states if relevant.
- Verify table statistics/bloat and query plans where needed.
- Check replication health if large WAL was generated.
- Never merely log "VACUUM ran" without verifying no pinned horizon prevented reclaiming dead tuples.

---

## 23. Two-Session Experiment: SELECT Blocking ALTER TABLE

Goal: observe how a finished `SELECT` inside an open transaction makes `ALTER TABLE` wait for `ACCESS EXCLUSIVE`.

### 23.1. Session A — Keep Transaction Open After SELECT

~~~sql
BEGIN;

SELECT COUNT(*) AS order_count
FROM lock_lab.orders;

-- DO NOT COMMIT/ROLLBACK yet.
-- Leave Session A here and switch to B.
~~~

The `SELECT` acquires `ACCESS SHARE` on the table, and inside an explicit transaction that lock stays held until the transaction ends.

### 23.2. Session B — Try ALTER with Short Timeout

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

ALTER TABLE lock_lab.orders
    ADD COLUMN lab_lock_probe TEXT;
~~~

Because A holds `ACCESS SHARE`, B requests `ACCESS EXCLUSIVE`, waits, and fails with:

~~~text
ERROR: canceling statement due to lock timeout
SQLSTATE: 55P03
~~~

Immediately after the error in B:

~~~sql
ROLLBACK;
~~~

### 23.3. Session A — Release Lock

~~~sql
ROLLBACK;
~~~

### 23.4. Session B — Retry Without Blocker

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

ALTER TABLE lock_lab.orders
    ADD COLUMN lab_lock_probe TEXT;

-- ALTER completes quickly on a 5-row table.
-- Use ROLLBACK so lab_lock_probe is not kept.
ROLLBACK;
~~~

**Conclusion:** lock wait time has nothing to do with metadata complexity or table row count.

### 23.5. Incoming SELECT Queued Behind ALTER

If Session C runs a new `SELECT` right while B is **waiting for `ACCESS EXCLUSIVE`**, C queues behind B's DDL request. This is **head-of-line blocking** in the lock queue. Never trigger this in production just to verify the principle.

---

## 24. Two-Session Experiment: Writer Blocking Regular CREATE INDEX

### 24.1. Session A — Hold Lock From UPDATE

~~~sql
BEGIN;

UPDATE lock_lab.orders
SET amount = amount + 1
WHERE order_id = (
    SELECT MIN(order_id) FROM lock_lab.orders
);

-- Do not COMMIT/ROLLBACK yet.
~~~

`UPDATE` acquires `ROW EXCLUSIVE` on the relation along with row/transaction locks.

### 24.2. Session B — Regular Index Creation

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

CREATE INDEX ix_orders_amount_probe
ON lock_lab.orders (amount);
~~~

Regular `CREATE INDEX` needs `SHARE`, conflicting with A's `ROW EXCLUSIVE`, so it waits and times out.

Session B:

~~~sql
ROLLBACK;
~~~

Session A:

~~~sql
ROLLBACK;
~~~

### 24.3. Why Should B Not Wait Forever?

In real workloads with long write transactions, a waiting regular `CREATE INDEX` queues up new writers behind it, causing an outage. A short `lock_timeout` lets the migration fail cleanly and retry on schedule.

### 24.4. Large Tables with Continuous Writes

When an index is required and writes cannot pause, consider `CREATE INDEX CONCURRENTLY` with progress monitoring—accounting for I/O, snapshot waits, timeouts, invalid index cleanup, and deployment timing.

---

## 25. Controlled Practice with CREATE INDEX CONCURRENTLY

Do not place this inside `BEGIN`. On the lab table, run it as a standalone command:

~~~sql
CREATE INDEX CONCURRENTLY ix_orders_status_created_c
ON lock_lab.orders (status, created_at);
~~~

Then verify:

~~~sql
SELECT
    idx.relname AS index_name,
    i.indisvalid,
    i.indisready,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
WHERE i.indrelid = 'lock_lab.orders'::regclass
  AND idx.relname = 'ix_orders_status_created_c';
~~~

Once finished, if the lab index is no longer needed:

~~~sql
DROP INDEX CONCURRENTLY IF EXISTS
    lock_lab.ix_orders_status_created_c;
~~~

Notes:

- `CREATE INDEX CONCURRENTLY` and `DROP INDEX CONCURRENTLY` must run **outside transaction blocks**.
- Never re-run `CREATE` with the same name while an index already exists—even `INVALID`—without inspecting state first.
- On a tiny table of a few rows, the planner may prefer `Seq Scan` over the index; this lab teaches lock/build lifecycle, not forcing planner index selection.

---

## 26. Safe Schema Changes on Large Tables: Expand → Backfill → Enforce → Contract

Business scenario: add an external identifier `external_code` to orders, backfill existing rows, and eventually guarantee every order has a unique non-null code.

**Never cram everything into one giant transaction.** Break it into controlled steps.

### 26.1. Expand: Add Nullable Column with Short DDL

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';

ALTER TABLE lock_lab.orders
    ADD COLUMN external_code TEXT;

COMMIT;
~~~

In real applications, ensure old and new app code are both compatible with the expanded schema before shifting traffic.

### 26.2. Batch Backfill

For the tiny lab table:

~~~sql
UPDATE lock_lab.orders
SET external_code = 'ORD-' || order_id::text
WHERE external_code IS NULL;
~~~

On very large tables, avoid a single full-table `UPDATE` in one transaction because it:

- Holds row locks and transactions open too long.
- Generates massive dead tuples and WAL.
- Spikes replication lag.
- Is painful to retry on failure.
- Overloads `VACUUM`.

A batch pattern when multiple independent workers backfill:

~~~sql
WITH batch AS (
    SELECT order_id
    FROM lock_lab.orders
    WHERE external_code IS NULL
    ORDER BY order_id
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
UPDATE lock_lab.orders AS o
SET external_code = 'ORD-' || o.order_id::text
FROM batch
WHERE o.order_id = batch.order_id;
~~~

`SKIP LOCKED` is used here for **work-queue backfilling**, where workers skip rows currently being backfilled by another worker. Include a termination check / remaining-row count so **every row is eventually backfilled**. Never use `SKIP LOCKED` for business flows that must touch one specific locked row.

### 26.3. Enforce Uniqueness: Build Index Outside Transaction

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY ux_orders_external_code
ON lock_lab.orders (external_code);
~~~

Before building, confirm backfill is complete, no duplicates exist, and `NULL` handling matches rules.

After building, verify:

~~~sql
SELECT i.indisvalid, i.indisready
FROM pg_index AS i
WHERE i.indexrelid = 'lock_lab.ux_orders_external_code'::regclass;
~~~

### 26.4. Enforce NOT NULL in Phases

~~~sql
ALTER TABLE lock_lab.orders
    ADD CONSTRAINT chk_external_code_not_null
    CHECK (external_code IS NOT NULL)
    NOT VALID;
~~~

Once all legacy rows are populated:

~~~sql
ALTER TABLE lock_lab.orders
    VALIDATE CONSTRAINT chk_external_code_not_null;
~~~

Afterward, where supported by your version:

~~~sql
ALTER TABLE lock_lab.orders
    ALTER COLUMN external_code SET NOT NULL;
~~~

A validated `CHECK` constraint lets PostgreSQL skip a separate `NOT NULL` verification scan, yet **does not eliminate the `ALTER` lock needed by `SET NOT NULL`**.

### 26.5. Attach UNIQUE Constraint Using Existing Index

~~~sql
ALTER TABLE lock_lab.orders
    ADD CONSTRAINT uq_orders_external_code
    UNIQUE USING INDEX ux_orders_external_code;
~~~

This is much faster than letting `ALTER` build a huge index under a strong lock, though it still takes an appropriate DDL lock and the index must meet constraint prerequisites.

### 26.6. Contract: Clean Up Old Artifacts Once Traffic Has Switched

Only after every service, worker, and ETL pipeline uses the new schema and rollback plans are settled:

- Drop unused legacy columns, constraints, or indexes.
- Remove dual-writes.
- Update ORM/migration metadata.
- Monitor data integrity and write latency.

**Never drop an old column in the same deploy as new code while old application instances are still running.**

### 26.7. Per-Stage Checklist

| Stage | Key lock behavior | What to verify |
|---|---|---|
| `ADD COLUMN` | `ACCESS EXCLUSIVE`; keep brief | App handles nullable column |
| Backfill | Row locks + `ROW EXCLUSIVE` per batch | All rows updated; WAL under control |
| `UNIQUE INDEX CONCURRENTLY` | `SHARE UPDATE EXCLUSIVE`, snapshot waits | Index `VALID`; no duplicates |
| `ADD CHECK NOT VALID` | Short `ALTER`, still takes lock | New writes enforced properly |
| `VALIDATE CHECK` | `SHARE UPDATE EXCLUSIVE` | Legacy data clean; constraint validated |
| `SET NOT NULL` | Strong `ALTER` lock | Validated `NOT NULL` proof ready; good timing |
| `ADD UNIQUE USING INDEX` | DDL lock, usually short | Index compatible; constraint active |
| Cleanup | DDL lock per subcommand | No remaining service reads/writes old schema |

Not everything can roll back as one unit once `CONCURRENTLY` steps run. Plan **step-by-step recovery** instead of treating the entire rollout as one giant transaction.

---

## 27. Rolling Out Migrations Safely Alongside Live Applications

### 27.1. Lock Timeout Must Fit Within Request Budgets

If your API times out at 3 seconds, an `ALTER` waiting 60 seconds for a lock piles up requests and causes timeouts long before the `ALTER` finishes. Coordinate:

- Acceptable lock wait threshold.
- Statement execution timeout.
- Application and connection-pool budgets.
- Bounded retry strategy.
- Rollback/cancellation criteria when metrics degrade.

The goal is never "run `ALTER` at all costs," but **never turn a schema change into an availability incident**.

### 27.2. Test on Representative Data Volumes First

A 5-row lab table will not reveal:

- How long `ALTER TYPE` takes on 200 million rows.
- How much disk and WAL an index build needs.
- How high replication lag will climb.
- Long-running analytics, cron maintenance, or CDC consumers waiting.
- Dependent indexes, triggers, or constraints in production.

Test in staging with production-like row counts, statistics, and write patterns. Even after staging tests, production concurrency differs—keep timeouts and live monitoring mandatory.

### 27.3. Set application_name for Migration Jobs

Where supported by the driver, set a descriptive name like `schema-migrate-orders` so DBAs can spot it easily:

~~~sql
SELECT
    pid, application_name, state, xact_start,
    wait_event_type, wait_event,
    LEFT(query, 180) AS sql_sample
FROM pg_stat_activity
WHERE datname = current_database()
  AND application_name LIKE 'schema-migrate-%';
~~~

Never reuse another service's name or embed secrets/tokens in `application_name`.

### 27.4. Migration Tools and Non-Transactional Steps

Many migration tools default to **one transaction per migration**. That is great for standard DDL, yet fails on `CREATE INDEX CONCURRENTLY`, `DROP INDEX CONCURRENTLY`, or `REINDEX ... CONCURRENTLY`.

Workflow:

1. Check how your framework enables "non-transactional migration" mode.
2. Isolate `CONCURRENTLY` steps into dedicated migrations/jobs.
3. Never mark a migration "done" just because an index name exists.
4. Verify `indisvalid`, uniqueness, and schema version.
5. If a concurrent step fails, resolve the invalid index before re-running.
6. Ensure multiple app instances cannot run migrations concurrently.

### 27.5. Advisory Locks Only Coordinate Migrators, Not Relation Locks

Some systems use an **advisory lock** so only one migrator runs at a time. That helps, yet:

- It works by **voluntary agreement among cooperating clients**, not blocking `SELECT`/`UPDATE`/`ALTER` from applications unaware of that advisory key.
- It does not replace the relation locks PostgreSQL requires for DDL.
- Transaction-level and session-level advisory locks have distinct lifetimes, especially in connection pools.

Never treat "holding an advisory migration lock" as proof that `ALTER` will not block live traffic.

### 27.6. When Canceling or Terminating a Blocker Is Necessary

PostgreSQL provides query cancellation and backend termination under appropriate privileges. Yet signaling someone else's session is **risky**, potentially rolling back large transactions or disrupting users.

Incident triage order:

1. Identify exact blocker, waiter, and owner.
2. Inspect what the transaction is doing, its age, and criticality.
3. Consider **canceling/rolling back the waiting migration first** to relieve queued traffic.
4. If the blocker must be interrupted, coordinate with the owner and follow approved runbooks.
5. Monitor recovery and verify schema state afterward.

Never embed arbitrary `pg_terminate_backend(pid)` commands in automated learning scripts.

---

## 28. Workload-Aware Index and Maintenance Planning

### 28.1. Three Independent Cost Axes

A maintenance operation can be expensive along three dimensions:

| Axis | Measurement question | Example |
|---|---|---|
| **Locking** | Who does it block/wait on, and for how long? | `ALTER` taking `ACCESS EXCLUSIVE` |
| **Compute / I/O** | How much scanning, sorting, rewriting, and WAL? | `CREATE INDEX CONCURRENTLY` multi-pass scans |
| **Storage / replication** | Extra temp disk, new indexes, replica lag? | `VACUUM FULL`, `REINDEX`, `CLUSTER` |

An operation might not block DML at the lock layer yet still spike application latency by saturating I/O.

### 28.2. Signs Autovacuum Is Falling Behind

Table statistics view:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'lock_lab'
ORDER BY relname;
~~~

`n_live_tup` and `n_dead_tup` are **statistical estimates**, not exact `COUNT(*)`s. High dead tuples may stem from heavy `UPDATE`/`DELETE` churn or long-held snapshots pinning the horizon; never crank up `VACUUM` frequency while ignoring old snapshots.

### 28.3. Table and Index Sizes

~~~sql
SELECT
    pg_size_pretty(
        pg_relation_size('lock_lab.orders'::regclass)
    ) AS heap_size,
    pg_size_pretty(
        pg_indexes_size('lock_lab.orders'::regclass)
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size('lock_lab.orders'::regclass)
    ) AS total_size;
~~~

These sizes estimate scale before index builds or rewrites, though they do not directly reveal **actual internal bloat** or peak temp disk usage. Sizes and concurrency shift over time.

### 28.4. REINDEX After Collation Changes or Bloat

If OS collation versions change or text indexes are affected, reindexing must follow PostgreSQL version guidance and operational policy. Never run `ALTER DATABASE REFRESH COLLATION VERSION` just to silence warnings while skipping rebuilding affected indexes.

### 28.5. Do Not Starve Autovacuum with Continuous Index Builds

Running concurrent index builds, `ANALYZE`, and DDL back-to-back on the same table can stall maintenance behind `SHARE UPDATE EXCLUSIVE` waits and build backlog. Schedule maintenance per table/partition cleanly without stacking uncontrolled jobs.

---

## 29. Checklist: Before, During, and After DDL / Maintenance

### 29.1. Before Deployment

- [ ] Clearly define the schema/index/maintenance goal and technical rationale.
- [ ] Confirm PostgreSQL version and table type (regular, partitioned, materialized).
- [ ] Identify **each subcommand's lock mode** and all affected relations.
- [ ] Measure table/index size, row counts, write rate, and replication lag.
- [ ] Check for long transactions, potential blockers, and active maintenance.
- [ ] Choose `CREATE INDEX` vs. `CREATE INDEX CONCURRENTLY` per availability needs.
- [ ] Audit constraints, duplicates, `NULL`s, and validation prerequisites.
- [ ] Configure `lock_timeout`/`statement_timeout` and retry policy.
- [ ] For `CONCURRENTLY`, verify the migration tool does not wrap it in `BEGIN`.
- [ ] Prepare **per-step rollback/recovery scripts**, especially for `INVALID` indexes.
- [ ] Agree on maintenance windows or online rollout criteria and abort thresholds.

### 29.2. During Execution

- [ ] Watch `pg_stat_activity.wait_event_type` and `pg_blocking_pids`.
- [ ] Watch `pg_stat_progress_create_index`/`vacuum`/`cluster` where available.
- [ ] Monitor waiting connection counts, API latency, and timeouts.
- [ ] Monitor CPU, I/O, free disk headroom, WAL rate, and replica lag.
- [ ] On lock timeout, roll back the failed transaction; never launch duplicate parallel runs.
- [ ] Never hold a transaction open for slow manual inspection.

### 29.3. After Completion

- [ ] Confirm the migration/index command reported success.
- [ ] Verify `indisvalid` and `indisready` on new/rebuilt indexes.
- [ ] Confirm constraints are validated or intentionally `NOT VALID`.
- [ ] Check `EXPLAIN` on key queries without assuming the planner's choice.
- [ ] Confirm no `idle in transaction` migration sessions remain.
- [ ] Verify `VACUUM`/`ANALYZE` backlog and replica lag recovered.
- [ ] Update schema versions, runbooks, and post-rollout cleanup tasks.

---

## 30. Decision Flowchart

~~~mermaid
flowchart TD
    A["Need to alter or maintain a PostgreSQL table"] --> B{"Operation type?"}
    B -- "ALTER TABLE" --> C{"Can it be split into phases?"}
    C -- "Yes" --> D["Expand / batch backfill / validate / contract"]
    C -- "No" --> E["Assess ACCESS EXCLUSIVE, rewrite, maintenance window"]
    B -- "Add index" --> F{"Must table keep accepting writes?"}
    F -- "No, have maintenance window" --> G["Regular CREATE INDEX"]
    F -- "Yes" --> H["CREATE INDEX CONCURRENTLY outside transaction block"]
    B -- "Clean dead tuples / stats" --> I["Plain VACUUM or ANALYZE"]
    B -- "Compact / physical reorder" --> J["VACUUM FULL / CLUSTER, ACCESS EXCLUSIVE"]
    B -- "Rebuild index" --> K{"Need minimal DML blocking?"}
    K -- "Yes" --> L["REINDEX CONCURRENTLY where supported"]
    K -- "No" --> M["Regular REINDEX in maintenance window"]
    D --> N["lock_timeout, pg_stat_activity, blockers"]
    E --> N
    G --> N
    H --> N
    I --> N
    J --> N
    L --> N
    M --> N
    N --> O["Verify catalogs/progress and application health"]
~~~

This diagram is a guide. Final decisions depend on PostgreSQL version, data volume, schema dependencies, write-availability SLAs, and operational constraints.

---

## 31. Common Mistakes and Misconceptions

| Mistake | Consequence | Fix |
|---|---|---|
| "Nullable `ALTER ADD COLUMN` doesn't rewrite so it doesn't lock" | `SELECT`/DML still blocked | Distinguish **execution time** from **lock mode** |
| `BEGIN` → `ALTER` → long GUI check → `COMMIT` | Holds `ACCESS EXCLUSIVE` way too long | Keep DDL transactions tiny |
| No `lock_timeout` for DDL on hot tables | Waiting `ALTER` builds a query queue | Fail fast and retry with control |
| Checking only lock holders, ignoring waiter queue | Fails to explain why new `SELECT`s wait | Inspect `pg_blocking_pids()` and lock queue |
| Using regular `CREATE INDEX` on busy large tables | Writes blocked for entire build | Consider `CREATE INDEX CONCURRENTLY` |
| Thinking `CREATE INDEX CONCURRENTLY` takes zero locks | Surprised by DDL/`VACUUM` conflicts | Understand `SHARE UPDATE EXCLUSIVE` |
| Putting `CREATE INDEX CONCURRENTLY` inside `BEGIN` | Rejected by PostgreSQL | Use non-transactional migration mode |
| Seeing index name exists and assuming deploy succeeded | Index may be `INVALID` or wrong definition | Check `pg_index` + `pg_get_indexdef` |
| Retrying failed concurrent index with same name blindly | Fails again or wastes resources | Diagnose root error and clean invalid index |
| Building `UNIQUE` concurrently with duplicates present | Build fails and errors writers | Deduplicate data and plan uniqueness carefully |
| Relying on `IF NOT EXISTS` to verify index correctness | Ignores wrong columns or invalid state | Compare catalog definitions and flags |
| Running `VACUUM FULL` like regular `VACUUM` | Blocks reads/writes; expensive rewrite | Use only when truly needed in a window |
| Disabling autovacuum so "DDL won't be blocked" | Dead tuples and XID age spike | Coordinate workloads; never disable casually |
| Running `ANALYZE` to fix every slow query | Cannot fix missing indexes, bad SQL, or locks | Inspect `EXPLAIN` and stats |
| Treating `n_dead_tup` as an exact `COUNT(*)` | Misdiagnosis | Treat as an estimate |
| Holding one huge transaction during backfill | Heavy locks, WAL, and bloat | Batch and commit frequently |
| Using `SKIP LOCKED` for rows that must not be skipped | Business data missed | Use only for tracked queues/backfills |
| Thinking `SET NOT NULL` is metadata-only with no scan | `ALTER` may scan entire table | Check validated `CHECK` proof and version |
| Inspecting only the child table during `ADD FOREIGN KEY` | Missed blockers on referenced parent | Monitor both relations |
| Reading block % progress as overall job completion | Build still has wait/validation phases | Track `phase` and catalogs |
| Using `VACUUM FULL` to "fix `xmin`/`xmax`" | Misunderstands MVCC and adds downtime | Never use rewrites to manipulate tuple visibility |
| Terminating blockers without knowing owner | Aborted work and user errors | Investigate/coordinate via runbook |
| Ignoring replication lag and WAL in maintenance plans | Replicas lag behind or fill disks | Monitor both primary and replicas |
| Ignoring app compatibility during schema changes | Old app/worker instances break | Use phased expand/contract |
| Skipping rollback after `lock_timeout` inside `BEGIN` | Session stuck in aborted state | `ROLLBACK` and reset connection cleanly |

---

## 32. Practice Exercises

Exercises use `lock_lab.orders` and `lock_lab.customers` from Section 4 unless stated otherwise. Never run schema-altering exercises in a shared lab while others are working on the same tables. For two-session exercises, follow the exact order and **end every transaction**, leaving no sessions waiting on locks afterward.

### Exercise 1 — Identifying Lock Modes

Which relation lock modes do a plain `SELECT` and an `ALTER TABLE ADD COLUMN` acquire? Are those two modes compatible?

### Exercise 2 — SELECT vs. CREATE INDEX

Why can plain `SELECT`s keep running while a regular `CREATE INDEX` builds on a table, whereas `INSERT`/`UPDATE` must wait?

### Exercise 3 — ROW EXCLUSIVE Is Not a Row-Level Lock

Explain why `ROW EXCLUSIVE` is a table-level lock name and does not mean the whole table is locked against `SELECT`s.

### Exercise 4 — Fast Metadata ALTER, Slow Deploy

A nullable `ADD COLUMN` takes 10 ms in isolation, yet waits 45 seconds for a lock in production. List at least three things to inspect.

### Exercise 5 — Head-of-Line Blocking

Session A holds a `SELECT` inside an open transaction, Session B waits for `ACCESS EXCLUSIVE` to run `ALTER`, and Session C sends a new `SELECT`. Why does Session C also wait even though A and C only `SELECT`?

### Exercise 6 — Two-Session DDL

Write SQL where Session A runs `BEGIN` and `SELECT` on `orders` without committing, and Session B runs `ALTER ADD COLUMN` with `lock_timeout` 2s. After the timeout, what must each session do to return the lab to normal?

### Exercise 7 — ADD CONSTRAINT NOT VALID

A large table needs `CHECK (amount >= 0)` without guaranteeing legacy rows are clean yet. Outline the `NOT VALID`, cleanup, and `VALIDATE CONSTRAINT` path. Does `NOT VALID` allow new `INSERT`s to violate the `CHECK`?

### Exercise 8 — FOREIGN KEY

Which tables and typical lock mode does `ADD FOREIGN KEY` involve? Why must you check blockers on both child and parent tables?

### Exercise 9 — SET NOT NULL

On a table with millions of rows, why can `SET NOT NULL` take a long time? How can a `VALID` `CHECK` constraint help in supported versions?

### Exercise 10 — Regular CREATE INDEX

Write a statement creating an index on `(customer_id, created_at)` and explain why writers block during the build.

### Exercise 11 — CREATE INDEX CONCURRENTLY

Write SQL to create an index on `(status, created_at)` minimizing DML blocking; why cannot it be wrapped in `BEGIN`?

### Exercise 12 — INVALID Index

A concurrent index build failed yet `pg_class` still lists the index name. Write SQL checking `indisvalid` and `indisready`. What should the next step be?

### Exercise 13 — IF NOT EXISTS

Does `CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_name ...` succeeding without error prove the index has the right columns and is `VALID`?

### Exercise 14 — DROP INDEX CONCURRENTLY

Why must `DROP INDEX CONCURRENTLY` also run outside a transaction block? Can you arbitrarily drop an index backing a `PRIMARY KEY`/`UNIQUE` constraint?

### Exercise 15 — REINDEX

Compare regular `REINDEX` and `REINDEX CONCURRENTLY` on locks, cost, transaction blocks, and recovery after a failed build.

### Exercise 16 — Plain VACUUM

Which lock mode does plain `VACUUM` use? Why can it still slow down APIs even without blocking DML at the lock layer?

### Exercise 17 — VACUUM FULL

Why does `VACUUM FULL` block both reads and writes and require extra disk space? Name situations where it should be avoided.

### Exercise 18 — ANALYZE

What problem does `ANALYZE` solve, and does it rebuild indexes? Why shouldn't `REINDEX` be the default fix for stale planner statistics?

### Exercise 19 — CLUSTER

What does `CLUSTER` physically reorder data by? Afterward, is a `SELECT` without `ORDER BY` guaranteed by PostgreSQL to return rows in that index order?

### Exercise 20 — Maintenance Conflicts

Why can `CREATE INDEX CONCURRENTLY` and `VACUUM` on the same table wait on each other, even though both permit `INSERT`/`UPDATE`?

### Exercise 21 — Blocking PIDs

Write SQL listing blocked backends and their blocking PID arrays. Should you automatically terminate the first blocker found?

### Exercise 22 — pg_locks

Write SQL displaying relation locks on `lock_lab.orders` with `mode` and `granted`. What does `granted=false` mean?

### Exercise 23 — CREATE INDEX Progress

Write SQL inspecting `phase` and block progress of an index build. Why isn't `blocks_done / blocks_total` always the overall completion percentage?

### Exercise 24 — VACUUM Progress

Which view reports plain `VACUUM` progress? Which view typically reports `VACUUM FULL`/`CLUSTER` progress?

### Exercise 25 — DDL Transactions

Why should you commit immediately after a short `ALTER` instead of leaving the transaction open for manual review? State risks to connection pools.

### Exercise 26 — Distinguishing Timeouts

What durations do `lock_timeout` and `statement_timeout` limit? If `lock_timeout` errors inside `BEGIN`, how must you handle transaction state?

### Exercise 27 — Partitioned Systems

Why must `ATTACH PARTITION` check locks on both parent and child rather than just one relation? Which constraint can skip the data validation scan?

### Exercise 28 — Expand/Contract Migration

Design a five-step plan to add a unique, `NOT NULL` `external_code` column on a large `orders` table while keeping writes online.

### Exercise 29 — Batch Backfill

Why can updating every row in one giant transaction cause long locks, WAL spikes, and bloat? When can `FOR UPDATE SKIP LOCKED` help?

### Exercise 30 — Applications and Replicas

A `VACUUM FULL` or `CLUSTER` generates huge WAL. Why is monitoring only the primary while ignoring replicas insufficient?

### Exercise 31 — Privileges and Lock Investigation

An `idle in transaction` backend owned by the payments service is blocking an `ALTER`. What should you do before considering cancel or terminate?

### Exercise 32 — Choosing the Right Technique

Pick the primary approach for each requirement:

1. Add an index to a 100M-row table while accepting writes.
2. Refresh statistics after a bulk load.
3. Regularly reclaim dead tuples with minimal DML blocking.
4. Compact a heavily bloated table file within a maintenance window.
5. Change a column's type on a hot table with rewrite risk.
6. Add a `CHECK` constraint on a table with many legacy rows.
7. Rebuild an index while minimizing write blocking.
8. Remove a leftover invalid index without opening `BEGIN`.

Briefly explain each choice and its limitations.

---

## 33. Suggested Solutions

### Exercise 1 — Relation Locks of SELECT and ALTER

Plain `SELECT` acquires `ACCESS SHARE`; `ALTER TABLE ... ADD COLUMN` acquires `ACCESS EXCLUSIVE`. The two modes **conflict**, so a held `SELECT` delays `ALTER`, and a held `ALTER` blocks `SELECT`.

### Exercise 2 — SELECT and Regular CREATE INDEX

Regular `CREATE INDEX` acquires `SHARE`. `SELECT`'s `ACCESS SHARE` is **compatible** with `SHARE`; `INSERT/UPDATE/DELETE`'s `ROW EXCLUSIVE` **conflicts** with `SHARE`, so writers wait until the build and its transaction finish.

### Exercise 3 — ROW EXCLUSIVE

`ROW EXCLUSIVE` is a **table-level mode** acquired by DML, not an exclusive lock blocking `SELECT`s. Plain `SELECT` uses `ACCESS SHARE` and is compatible with `ROW EXCLUSIVE`. Contention between writers on **the same row** involves row-level/transaction locks.

### Exercise 4 — Fast Metadata ALTER, Long Wait

Check:

1. Which backend holds the conflicting lock via `pg_blocking_pids()`?
2. Is there a long/`idle in transaction` session holding `ACCESS SHARE` or `ROW EXCLUSIVE`?
3. Is `ALTER` **waiting** or has it already been granted `ACCESS EXCLUSIVE`?
4. Are there earlier waiters in the lock queue?
5. Are timeouts, other migrations, DDL, or maintenance running?

Never solve this by raising timeouts indefinitely.

### Exercise 5 — Head-of-Line Blocking

Session B entered the queue requesting `ACCESS EXCLUSIVE`, which conflicts with C's `SELECT` even though C's `ACCESS SHARE` is compatible with A. PostgreSQL will not let C keep jumping ahead of B indefinitely, or B would starve. Thus even a **waiting `ALTER`** creates a backlog.

### Exercise 6 — Two-Session DDL

**Session A:**

~~~sql
BEGIN;
SELECT COUNT(*) FROM lock_lab.orders;
-- Leave open and switch to B.
~~~

**Session B:**

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';
ALTER TABLE lock_lab.orders ADD COLUMN lab_test_col TEXT;
-- Upon lock timeout:
ROLLBACK;
~~~

**Session A:**

~~~sql
ROLLBACK;
~~~

To re-test without keeping the lab column:

~~~sql
BEGIN;
ALTER TABLE lock_lab.orders ADD COLUMN lab_test_col TEXT;
ROLLBACK;
~~~

### Exercise 7 — CHECK NOT VALID and VALIDATE

~~~sql
ALTER TABLE lock_lab.orders
ADD CONSTRAINT chk_orders_amount_nn
CHECK (amount >= 0) NOT VALID;
~~~

Then clean invalid rows in controlled batches, and run:

~~~sql
ALTER TABLE lock_lab.orders
VALIDATE CONSTRAINT chk_orders_amount_nn;
~~~

`NOT VALID` skips the full-table scan **during `ADD`**, while still enforcing `CHECK` on new/modified rows. `VALIDATE` checks existing rows using `SHARE UPDATE EXCLUSIVE`. In the lab, `amount` already has an equivalent `CHECK`, so this illustrates the technique without adding redundant production constraints.

### Exercise 8 — FOREIGN KEY

~~~sql
ALTER TABLE lock_lab.orders
ADD CONSTRAINT fk_orders_customers
FOREIGN KEY (customer_id)
REFERENCES lock_lab.customers(customer_id)
NOT VALID;
~~~

`ADD FOREIGN KEY` acquires `SHARE ROW EXCLUSIVE` on both referencing table `orders` and referenced table `customers`; writes on both can be blocked. Running `VALIDATE CONSTRAINT` later decouples scanning legacy rows from `ADD`.

### Exercise 9 — SET NOT NULL

`SET NOT NULL` may scan the whole table to confirm no `NULL`s exist. In PostgreSQL versions supporting this optimization, a validated `CHECK (column IS NOT NULL)` lets it skip that verification scan. Still, the `ALTER` takes its own lock and can wait on conflicts.

### Exercise 10 — Regular CREATE INDEX

~~~sql
CREATE INDEX ix_orders_customer_created
ON lock_lab.orders(customer_id, created_at);
~~~

`SHARE` acquired during the build conflicts with writers' `ROW EXCLUSIVE`. On large tables with continuous writes, use a maintenance window or build concurrently per availability needs.

### Exercise 11 — CREATE INDEX CONCURRENTLY

~~~sql
CREATE INDEX CONCURRENTLY ix_orders_status_created_c
ON lock_lab.orders(status, created_at);
~~~

Never wrap in `BEGIN`: it executes across multiple internal transactions and waits for snapshots/writers. PostgreSQL rejects `CREATE INDEX CONCURRENTLY` inside an explicit transaction block. It avoids blocking normal DML, yet still takes locks and resources.

### Exercise 12 — INVALID Index

~~~sql
SELECT
    idx.relname AS index_name,
    i.indisvalid,
    i.indisready,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
WHERE i.indrelid = 'lock_lab.orders'::regclass;
~~~

If invalid, diagnose the original error, confirm the build job exited, check uniqueness/dependencies, and then drop or reindex per index type and runbook. Never auto-retry with the same name uninvestigated.

### Exercise 13 — IF NOT EXISTS

**No.** It only avoids duplicate-relation errors under DDL rules. It does not verify that the existing index matches the intended columns, predicate, uniqueness, collations, or `VALID` status. Inspect catalogs and index definition.

### Exercise 14 — DROP INDEX CONCURRENTLY

`DROP INDEX CONCURRENTLY` has its own transaction rules and must run outside a transaction block. You cannot drop an index backing a `PRIMARY KEY`/`UNIQUE` constraint directly in a way that breaks dependencies; handle the constraint and data via a proper migration plan.

### Exercise 15 — REINDEX

- Regular `REINDEX`: blocks writes and index-dependent operations during rebuild; schedule for low traffic.
- `REINDEX ... CONCURRENTLY`: avoids normal DML blocking, yet is multi-phase, uses extra disk/WAL, waits on snapshots, and cannot run inside an explicit transaction block.
- On failure: inspect index state and temporary/invalid remnants before retrying; never loop blindly.

### Exercise 16 — Plain VACUUM

Plain `VACUUM` uses `SHARE UPDATE EXCLUSIVE`, compatible with normal `ROW EXCLUSIVE` and `ACCESS SHARE`. Even without blocking DML at the lock layer, it increases latency via I/O, CPU, heap/index work, or maintenance lock conflicts.

### Exercise 17 — VACUUM FULL

`VACUUM FULL` rewrites the table to compact disk usage under `ACCESS EXCLUSIVE`, blocking `SELECT` and DML. Rewrites require extra disk space and generate heavy WAL/replica lag. Avoid during peak traffic on hot tables or without disk headroom and a maintenance window.

### Exercise 18 — ANALYZE

`ANALYZE` updates statistics for the query planner. It does not rebuild indexes. When row-count estimates go stale after bulk loads or skew shifts, check `ANALYZE` first instead of defaulting to `REINDEX`.

### Exercise 19 — CLUSTER

`CLUSTER table USING index` rewrites data physically ordered by that index under `ACCESS EXCLUSIVE`. Subsequent writes break physical order again. A `SELECT` **without `ORDER BY`** still has no guaranteed row order.

### Exercise 20 — Maintenance Conflicts

Both `CREATE INDEX CONCURRENTLY` and plain `VACUUM` acquire `SHARE UPDATE EXCLUSIVE` on the same relation; that mode conflicts **with itself**, even though it is compatible with normal DML. Monitor progress and schedule maintenance cleanly.

### Exercise 21 — Blocking PIDs

~~~sql
SELECT
    pid,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    LEFT(query, 160) AS sql_sample
FROM pg_stat_activity
WHERE datname = current_database()
  AND cardinality(pg_blocking_pids(pid)) > 0;
~~~

**Do not** blindly terminate the first PID. Verify owner, transaction type, business impact, and rollback risk, and coordinate with operators.

### Exercise 22 — pg_locks

~~~sql
SELECT
    pid, locktype, mode, granted,
    relation::regclass AS relation_name
FROM pg_locks
WHERE relation = 'lock_lab.orders'::regclass
ORDER BY granted, pid, mode;
~~~

`granted=false` means the lock has not been granted yet and the backend is waiting for it—not that it already holds exclusive control.

### Exercise 23 — Index Progress

~~~sql
SELECT
    pid,
    relid::regclass AS table_name,
    command,
    phase,
    blocks_total,
    blocks_done,
    lockers_total,
    lockers_done
FROM pg_stat_progress_create_index
WHERE datname = current_database();
~~~

The job still has scan/validation/snapshot-wait phases after the current phase. Block ratio reflects only **that phase**, not total job time or cost.

### Exercise 24 — VACUUM Progress

- `pg_stat_progress_vacuum`: plain `VACUUM`.
- `pg_stat_progress_cluster`: rewrite progress for `VACUUM FULL` and `CLUSTER`.
- `pg_stat_progress_analyze`: `ANALYZE` on supported versions.

### Exercise 25 — DDL Transactions

Relation locks stay held until transaction end. After `ALTER` finishes, if the transaction has not committed, `SELECT`/DML still wait. In pools, sessions left `idle in transaction` or returned uncommitted stall subsequent requests. DDL transactions must be short and closed cleanly on all paths.

### Exercise 26 — Timeouts

`lock_timeout`: time waiting **to acquire a lock**.

`statement_timeout`: total **statement** execution time, including lock waits.

Inside a transaction, a timeout error aborts the transaction; you must `ROLLBACK` the whole transaction or roll back to a valid savepoint rather than sending more SQL as if no error occurred.

### Exercise 27 — ATTACH PARTITION

The operation acquires different locks on the parent, child, and related objects. Unless the child already has a constraint proving all rows fit the partition bounds, PostgreSQL scans to verify. A matching **validated `CHECK`** skips that scan where supported.

### Exercise 28 — Expand/Contract

A clean rollout:

1. **Expand:** add nullable `external_code TEXT` via brief `ALTER`; code supports both schemas.
2. **Backfill:** update in batches; verify uniqueness and complete coverage.
3. **Index:** `CREATE UNIQUE INDEX CONCURRENTLY`; verify `indisvalid` and definition.
4. **Enforce:** `CHECK NOT VALID`/`VALIDATE` and `SET NOT NULL` where applicable; attach `UNIQUE` constraint `USING INDEX` via brief DDL.
5. **Contract:** switch all apps/ETL to the new schema, then drop legacy artifacts with monitoring and per-step recovery plans.

Never force `CREATE INDEX CONCURRENTLY` into the same transaction as `ALTER`.

### Exercise 29 — Batch Backfill

One full-table `UPDATE` creates a massive transaction, extensive row locks/versions, WAL spikes, replica lag, and bloat. Split into small batches and commit frequently. `FOR UPDATE SKIP LOCKED` helps when independent workers pull batches, provided you verify all rows are eventually processed.

### Exercise 30 — Replicas

Large rewrites and index builds generate heavy WAL and I/O, raising replica lag and disk usage. Even once the primary finishes, replica readers may still lag behind. Monitor lag, disk, replay, backups, and infrastructure limits on both primary and replicas.

### Exercise 31 — Idle in Transaction Backend

First identify owning service, job/request, transaction age, and real impact via `pg_stat_activity` and `pg_blocking_pids()`. Consider canceling/rolling back the **waiting migration** to clear the queue, or coordinate with the payments team for a controlled finish—never blindly kill a payments session.

### Exercise 32 — Choosing the Right Tool

| Scenario | Recommended approach | Caveats |
|---|---|---|
| Index large table while taking writes | `CREATE INDEX CONCURRENTLY` | Outside `BEGIN`, scan/snapshot waits, check `INVALID` |
| Gather stats after bulk load | `ANALYZE` | `SHARE UPDATE EXCLUSIVE`, does not rebuild indexes |
| Periodic dead tuple cleanup | Plain `VACUUM` / autovacuum | Does not block normal DML by lock mode; uses I/O |
| Shrink table file in maintenance window | `VACUUM FULL` | `ACCESS EXCLUSIVE`, rewrite, extra disk needed |
| Change column type with rewrite risk | Expand/contract or maintenance window | Analyze cast/rewrite, strong lock, app compatibility |
| `CHECK` on large legacy table | `ADD ... NOT VALID` then `VALIDATE` | `ADD` still locks; `VALIDATE` scans |
| Rebuild index minimizing write blocks | `REINDEX ... CONCURRENTLY` if supported | Outside `BEGIN`, needs extra disk and monitoring |
| Remove leftover invalid index | `DROP INDEX CONCURRENTLY` if eligible | Outside `BEGIN`, check dependencies/constraints |

---

## 34. Summary

**Locks in PostgreSQL are an essential part of keeping DDL, DML, and maintenance consistent; what matters is not merely whether a command feels fast or slow, but its lock mode, hold duration, and how its lock requests interact with live traffic.**

- **`ALTER TABLE`:** many subcommands acquire `ACCESS EXCLUSIVE`. Even a non-rewriting metadata change can wait and block both `SELECT` and DML. Check every subcommand, especially constraint and partition operations.
- **Large constraints:** split into `ADD ... NOT VALID`, backfill/cleanup, then `VALIDATE CONSTRAINT`; cuts scan duration during `ADD` without removing the lock entirely.
- **Regular `CREATE INDEX`:** acquires `SHARE`, permitting `SELECT` while blocking DML.
- **`CREATE INDEX CONCURRENTLY`:** avoids blocking writes, yet performs multiple scans, waits on snapshots, uses `SHARE UPDATE EXCLUSIVE`, cannot run in a transaction block, and can leave `INVALID` indexes.
- **`REINDEX`/`REINDEX CONCURRENTLY`:** rebuild indexes with trade-offs in locking, duration, disk space, and failure recovery.
- **Plain `VACUUM` and `ANALYZE`:** designed to coexist with normal DML, though still consuming resources and potentially conflicting with other maintenance/DDL.
- **`VACUUM FULL`/`CLUSTER`:** rewrite tables under `ACCESS EXCLUSIVE`, requiring maintenance windows and disk/WAL/replication planning.
- **Observability:** `pg_stat_activity`, `pg_blocking_pids()`, `pg_locks`, and `pg_stat_progress_*` views distinguish blockers, waiters, phases, and load.
- **Safe rollouts:** keep DDL transactions short, bound waits with `lock_timeout`, clean up on failure, use expand/backfill/enforce/contract, and verify catalogs and applications afterward.

The right workflow for live systems: **identify change and lock mode → measure concurrency and size → pick the least-blocking technique → prepare timeouts and rollback → deploy in phases → monitor blockers and progress → verify catalogs, performance, data, and replicas upon completion.**
