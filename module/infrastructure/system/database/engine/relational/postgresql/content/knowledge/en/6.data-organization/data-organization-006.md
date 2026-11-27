# Permanent, temporary, and UNLOGGED tables in PostgreSQL

## 1. Three table types serving three data organization needs

In PostgreSQL, most business data is stored in **permanent tables**. However, when processing reports, bulk data imports, or multi-step computations, not every dataset needs long-term persistence. PostgreSQL also provides **temporary tables** and **UNLOGGED tables** to choose the right level of persistence and write overhead.

Three ways to create tables:

```sql
-- Permanent table: default when TEMP or UNLOGGED is omitted.
CREATE TABLE app_orders (
    order_id bigint PRIMARY KEY,
    amount numeric(12,2) NOT NULL
);

-- Temporary table: exists within the scope of the connection session.
CREATE TEMP TABLE session_work (
    order_id bigint PRIMARY KEY
);

-- UNLOGGED table: persists across sessions, yet its data
-- is not WAL-protected like a permanent table.
CREATE UNLOGGED TABLE import_stage (
    batch_id bigint NOT NULL,
    raw_line text NOT NULL
);
```

All three use `CREATE TABLE`, yet they do not share the same lifecycle.

| Criterion | Permanent table | Temporary (`TEMP`) table | `UNLOGGED` table |
| --- | --- | --- | --- |
| Basic syntax | `CREATE TABLE` | `CREATE TEMP TABLE` | `CREATE UNLOGGED TABLE` |
| Object lifecycle | Until dropped/altered or administrative action | Usually until session ends; can be shorter | Until dropped/altered or administrative action |
| Readable from another session? | Yes, subject to privileges and MVCC | Cannot directly read another session's temp table | Yes, subject to privileges and MVCC |
| Remains after creating client disconnects? | Yes | No | Yes |
| Remains after clean restart? | Yes | No | Usually yes |
| Crash-protected via standard WAL? | Yes, depending on durability settings | No; session terminates | **No**; data can be truncated |
| Replicated to physical standby via WAL like permanent tables? | Yes per replication configuration | No | **No** for data contents |
| Supports transactions, `COMMIT`, and `ROLLBACK`? | Yes | Yes | Yes |
| Typical use case | Orders, accounts, payments | Intermediate results for a single session | Shared staging that can be reloaded |

**Do not think of "UNLOGGED" as "TEMP but faster".** An UNLOGGED table is a shared, long-lived object, whereas TEMP is bound to one connection session. Their commonality is that neither provides the same WAL protection for data contents as a permanent table.

Lesson goal: upon completion, you will be able to choose table types matching retention requirements, understand transaction and crash impacts, select appropriate staging approaches, and inspect actual table types via SQL.

## 2. Separate four questions before choosing a table type

When designing, ask four independent questions:

1. **How long must the data survive?** Only for a single calculation, a single transaction, a connection, an import run, or many years?
2. **Who needs to read or write the data?** Only one session, multiple application connections, different batch workers, or replicas?
3. **Does the data need to survive a crash?** If staging data is lost, can it be re-ingested from original files, object storage, or another trusted source?
4. **How important are operational costs?** WAL, indexes, disk capacity, autovacuum, replication, backups, and churn from creating/dropping temp tables.

Example in a retail system:

```text
Data sources
   |
   +-- Payment transactions ------------> permanent table
   |                                      (data loss is unacceptable)
   |
   +-- Temp ID set during reporting ----> TEMP table
   |                                      (used only on the same connection)
   |
   +-- Re-readable import file ---------> UNLOGGED staging table
                                          (multiple workers read, reload acceptable)
```

Base your selection on **data requirements**, not merely an intuition that "TEMP is fast" or "WAL is expensive".

## 3. Permanent tables: storing long-lived data

### 3.1. Creating and using

Permanent tables are the default:

```sql
CREATE SCHEMA IF NOT EXISTS table_kinds_lab;

CREATE TABLE table_kinds_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Insert an order:

```sql
INSERT INTO table_kinds_lab.orders
    (order_id, customer_name, amount)
VALUES
    (101, 'Nguyễn An', 250000.00);
```

If the connection is in **autocommit** mode, a successful `INSERT` normally commits as its own transaction. Inside `BEGIN`, the change waits for `COMMIT` before becoming committed data.

Read from another connection:

```sql
SELECT
    order_id,
    customer_name,
    amount
FROM table_kinds_lab.orders
WHERE order_id = 101;
```

Another session can read committed rows if privileges and snapshots permit.

### 3.2. `COMMIT`, `ROLLBACK`, and visibility

An operation inside a transaction:

```sql
BEGIN;

INSERT INTO table_kinds_lab.orders
    (order_id, customer_name, amount)
VALUES
    (102, 'Trần Bình', 175000.00);

-- Within this transaction, the session sees its own changes.
SELECT * FROM table_kinds_lab.orders WHERE order_id = 102;

ROLLBACK;
```

After `ROLLBACK`, order 102 does not become committed data.

Conversely:

```sql
BEGIN;

INSERT INTO table_kinds_lab.orders
    (order_id, customer_name, amount)
VALUES
    (103, 'Lê Chi', 300000.00);

COMMIT;
```

Committed data for order 103 continues to exist after the session that created it closes.

**Distinguish two properties:**

- **Cross-session visibility:** depends on commit, privileges, and snapshot per isolation level.
- **Crash durability:** depends on WAL mechanisms and data-safety configuration.

A committed row may temporarily be invisible to another transaction holding an older snapshot; that does not turn a permanent table into a temporary table.

### 3.3. Role of WAL

PostgreSQL uses the **Write-Ahead Log (WAL)** to record necessary change information before the corresponding data is considered durable. In normal operation, WAL contributes to **crash recovery** and supports replication/backups via related mechanisms.

```text
UPDATE/INSERT into permanent table
             |
             v
  Modify data / generate required WAL records
             |
             v
  COMMIT per durability policy
             |
             v
  As needed: flush/write data pages
             |
             v
  If crash occurs: use WAL for recovery
```

Permanent tables are designed to protect committed changes under proper durability configurations, though this does not mean **data loss is impossible in every circumstance**. For example:

- `synchronous_commit = off` allows some transactions to report commit before their corresponding WAL is durably flushed; a crash right around then can lose them.
- Disabling `fsync` or using storage hardware that fails to honor flush guarantees weakens durability.
- Hardware failure or accidentally dropping a table still requires backups, recovery procedures, and operational safeguards.

**WAL does not replace backups.** Critical long-lived data still needs backup policies, tested restores, and proper access controls.

### 3.4. When must you use a permanent table?

Data normally belongs in a permanent table when:

- It is the business **source of truth**.
- It cannot be fully reconstructed if the server crashes.
- It must be shared across many connections, services, and long time spans.
- It must appear on standbys/replicas via supported replication strategies.
- It requires backups, auditing, privilege protection, and stable relational constraints.

Examples: purchase orders, balances, payment history, account details, multi-day report outputs, and task states the system must recover after a restart.

## 4. TEMP tables: intermediate data private to one session

### 4.1. Creating a temporary table

PostgreSQL allows:

```sql
CREATE TEMP TABLE temp_order_ids (
    order_id bigint PRIMARY KEY
);
```

Or written in full:

```sql
CREATE TEMPORARY TABLE temp_order_ids (
    order_id bigint PRIMARY KEY
);
```

This table has a name and columns like a normal SQL table; you can `INSERT`, `SELECT`, `UPDATE`, `DELETE`, create indexes, and join with other tables. However, **ownership is scoped to the session that created it**.

Example using a temporary table:

```sql
INSERT INTO temp_order_ids (order_id)
SELECT order_id
FROM table_kinds_lab.orders
WHERE amount >= 200000;

SELECT
    o.order_id,
    o.customer_name,
    o.amount
FROM table_kinds_lab.orders AS o
JOIN temp_order_ids AS t
    ON t.order_id = o.order_id
ORDER BY o.order_id;
```

The data in `temp_order_ids` holds only the list of order IDs selected in the current session. Subsequent inserts/updates to `orders` **do not automatically update** rows already copied to the temp table.

### 4.2. Creating a TEMP table with `CREATE TABLE AS`

If you want to persist a query's result into a temporary table:

```sql
CREATE TEMP TABLE temp_large_orders AS
SELECT
    order_id,
    customer_name,
    amount
FROM table_kinds_lab.orders
WHERE amount >= 200000;

SELECT * FROM temp_large_orders ORDER BY order_id;
```

`CREATE TEMP TABLE ... AS SELECT` creates a table holding the query's current result set. Unlike a **view**, these are materialized rows, not a query definition recomputed on each read.

In a multi-step workflow:

```text
Source query
   |
   v
TEMP table
   |
   +-- Step 1: add computed columns
   +-- Step 2: create indexes
   +-- Step 3: JOIN and aggregate
   +-- Step 4: export report
   |
   v
Close session -> table is dropped
```

If an intermediate result is used within **a single SQL statement**, a CTE or subquery is often simpler and carries less overhead than creating a temporary table.

### 4.3. Temporary tables are not shared across sessions

Open two separate PostgreSQL connections, such as two `psql` windows.

**Session A:**

```sql
SELECT pg_backend_pid() AS session_a_pid;

CREATE TEMP TABLE session_notes (
    note_id integer PRIMARY KEY,
    content text NOT NULL
);

INSERT INTO session_notes (note_id, content)
VALUES (1, 'Session A data');

SELECT * FROM session_notes;
```

**Session B:**

```sql
SELECT pg_backend_pid() AS session_b_pid;

SELECT * FROM session_notes;
```

Session B normally receives `relation "session_notes" does not exist` unless B has another object with that name. Session B **cannot use Session A's temporary table as a shared table**.

Session B can create its own temporary table with the same name:

```sql
CREATE TEMP TABLE session_notes (
    note_id integer PRIMARY KEY,
    content text NOT NULL
);

INSERT INTO session_notes (note_id, content)
VALUES (2, 'Session B data');
```

The two tables are **two distinct objects**. They share a name yet belong to separate sessions. One session can execute multiple transactions across its lifetime while keeping the temp table intact, depending on the `ON COMMIT` policy.

### 4.4. How long does a temporary table live?

By default, a temp table usually exists **until the session ends** or `DROP TABLE` runs, provided it was not created inside a transaction that later rolled back.

```text
Session A opens
   |
   +-- CREATE TEMP TABLE temp_order_ids
   +-- INSERT ...
   +-- COMMIT
   +-- SELECT ... from temp_order_ids
   +-- BEGIN / UPDATE / COMMIT
   +-- SELECT ... from temp_order_ids
   |
Session A closes
   |
   +-- PostgreSQL drops temp_order_ids

New Session B opens
   |
   +-- Cannot see Session A's temp_order_ids
```

**Common trap:** an application creates a temp table on one connection, returns the connection to the pool, and then queries it using another connection. The result is `relation does not exist` even though logs show the table creation succeeded.

## 5. `ON COMMIT`: three ways TEMP data ends at transaction boundaries

PostgreSQL supports three policies for temporary tables:

| Option | After `COMMIT` | Can the table still be used in the same session? |
| --- | --- | --- |
| **`ON COMMIT PRESERVE ROWS`** | Preserves committed rows | Yes |
| **`ON COMMIT DELETE ROWS`** | Deletes all rows in the temp table | Yes, though the table is empty |
| **`ON COMMIT DROP`** | Drops the temp table itself | No, must be recreated |

`ON COMMIT PRESERVE ROWS` is **PostgreSQL's default**. Do not assume behavior from another DBMS.

### 5.1. `ON COMMIT PRESERVE ROWS`

```sql
CREATE TEMP TABLE t_preserve (
    id integer PRIMARY KEY
) ON COMMIT PRESERVE ROWS;

BEGIN;

INSERT INTO t_preserve (id) VALUES (10);

COMMIT;

SELECT * FROM t_preserve;
```

The result still retains row `id = 10` within the same session. When the session closes, however, `t_preserve` is removed.

### 5.2. `ON COMMIT DELETE ROWS`

```sql
CREATE TEMP TABLE t_delete (
    id integer PRIMARY KEY
) ON COMMIT DELETE ROWS;

BEGIN;

INSERT INTO t_delete (id) VALUES (20), (21);

SELECT COUNT(*) AS before_commit
FROM t_delete;

COMMIT;

SELECT COUNT(*) AS after_commit
FROM t_delete;
```

Inside the transaction, `before_commit = 2`. After commit, the table still exists, yet `after_commit = 0`.

**Note on autocommit:** without `BEGIN`, each standalone `INSERT` may commit immediately; with `ON COMMIT DELETE ROWS`, rows may be cleared before the next `SELECT` executes. To keep them across multiple SQL statements in the same transaction, open an explicit transaction.

### 5.3. `ON COMMIT DROP`

```sql
BEGIN;

CREATE TEMP TABLE t_drop (
    id integer PRIMARY KEY
) ON COMMIT DROP;

INSERT INTO t_drop (id) VALUES (30);

SELECT * FROM t_drop;

COMMIT;
```

After commit, the table `t_drop` no longer exists in the session:

```sql
-- Expected to error after commit:
SELECT * FROM t_drop;
```

**Creating `ON COMMIT DROP` outside an explicit transaction** in an autocommit session causes the table to be dropped as soon as the `CREATE TEMP TABLE` statement completes. Therefore, when you only want a temp table for one transaction, run `BEGIN` before creating it.

### 5.4. Which policy should you choose?

- **PRESERVE ROWS:** multiple SQL statements across consecutive transactions on **the same session** need to reuse the data.
- **DELETE ROWS:** you want to reuse the table structure, starting each transaction with an empty table.
- **DROP:** the table is needed only for a single transaction and should clean up automatically at commit.

Do not use `ON COMMIT` on permanent or UNLOGGED tables as you do on TEMP tables: this is a lifecycle-management feature for **temporary tables**.

## 6. TEMP tables still support transactions and rollback

The name "temporary" does not mean DML on the table falls outside transactional rules.

```sql
CREATE TEMP TABLE t_tx (
    id integer PRIMARY KEY
);

INSERT INTO t_tx (id) VALUES (1);

BEGIN;

INSERT INTO t_tx (id) VALUES (2);

ROLLBACK;

SELECT id FROM t_tx ORDER BY id;
```

Assuming row 1 was inserted in autocommit prior to `BEGIN`, the result retains **id = 1** without row 2. The temp table remains in the session because it was created before the rolled-back transaction.

If `CREATE TEMP TABLE` itself occurs inside a transaction that rolls back:

```sql
BEGIN;

CREATE TEMP TABLE t_new (
    id integer PRIMARY KEY
);

INSERT INTO t_new VALUES (1);

ROLLBACK;
```

then **table creation itself** is rolled back as well. Afterward, `SELECT * FROM t_new` no longer finds the table unless another same-named object exists.

Similarly, savepoints work:

```sql
CREATE TEMP TABLE t_save (
    id integer PRIMARY KEY
);

BEGIN;

INSERT INTO t_save VALUES (1);

SAVEPOINT before_optional_insert;

INSERT INTO t_save VALUES (2);

ROLLBACK TO SAVEPOINT before_optional_insert;

COMMIT;

SELECT * FROM t_save ORDER BY id;
```

Only id 1 remains. TEMP transaction behavior does not make it "data-unsafe" within a session: PostgreSQL still provides atomicity and undo semantics for eligible operations.

## 7. UNLOGGED: shared tables whose data is not crash-safe

### 7.1. Creating an UNLOGGED table

```sql
CREATE UNLOGGED TABLE table_kinds_lab.import_lines (
    batch_id bigint NOT NULL,
    line_no integer NOT NULL,
    raw_product_code text NOT NULL,
    raw_quantity text NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (batch_id, line_no)
);
```

Table `import_lines` is created in schema `table_kinds_lab`, identical to a permanent table in naming scope and cross-session accessibility. Sessions with appropriate privileges can `SELECT`, `INSERT`, and `UPDATE` on the same table.

However, the **`UNLOGGED`** keyword changes a crucial storage property: PostgreSQL **does not write WAL for the data of unlogged relations the way it does for permanent tables**.

Example:

```sql
INSERT INTO table_kinds_lab.import_lines
    (batch_id, line_no, raw_product_code, raw_quantity)
VALUES
    (5001, 1, 'P001', '2'),
    (5001, 2, 'P002', '3'),
    (5001, 3, 'INVALID', 'not-a-number');
```

After commit, another session can read:

```sql
SELECT *
FROM table_kinds_lab.import_lines
WHERE batch_id = 5001
ORDER BY line_no;
```

UNLOGGED does not confine data to the creating session like TEMP does.

### 7.2. Why can reducing WAL be helpful?

When loading large volumes of reproducible data, omitting WAL for table contents and associated indexes can **reduce WAL write volume**, potentially speeding up certain workloads or relieving pressure on WAL storage/archiving.

However:

- `UNLOGGED` **does not mean operations require zero I/O**.
- PostgreSQL still writes data/index pages, enforces constraints, consumes CPU, acquires locks, and manages memory.
- Certain metadata changes and other activities still interact with logging mechanisms.
- Unlogged tables still incur index and vacuum costs.
- Actual gains depend on the dataset, configuration, hardware, and queries; **benchmark it** rather than assuming a fixed speedup factor.

### 7.3. Consequences after a crash or unclean shutdown

One mandatory characteristic to remember: **UNLOGGED provides no crash-recovery guarantee for data like permanent tables do**.

When PostgreSQL restarts after a crash or unclean shutdown, unlogged table contents are **truncated** during recovery. The table structure persists, yet the data can be wiped clean.

```text
Before crash:
    table_kinds_lab.import_lines
    batch 5001: 100,000 rows
              |
              v
Server crash / unclean shutdown
              |
              v
PostgreSQL recovery
              |
              v
UNLOGGED table exists, but data is truncated
              |
              v
Application must reload from a trusted source
```

UNLOGGED tables **usually retain data across a clean restart**. Do not equate every restart with a crash: data truncation specifically applies to crashes or unclean shutdowns.

More importantly, **`COMMIT` still functions in transactional semantics**, yet it does not convert UNLOGGED data into WAL-protected data across crashes. An `INSERT` into an UNLOGGED table can commit validly and still be lost after a crash.

### 7.4. UNLOGGED and replication

UNLOGGED data contents **are not streamed via WAL-based physical streaming replication like permanent table data**. Therefore:

- Never design an application expecting a standby to hold a copy of UNLOGGED staging contents.
- Never rely on a PostgreSQL physical replica as a recovery strategy for UNLOGGED table data.
- After failover, staging workflows may need to reload data or adjust deployment strategies.

If you need a table for reporting on a read replica, that table's data must travel via an appropriate replication mechanism; permanent tables are the clearer default choice.

### 7.5. Choose UNLOGGED only when data is reproducible

A shared staging table may fit UNLOGGED when:

1. Original data is already safely persisted in files, object storage, a replayable messaging system, or another permanent table.
2. If staging is lost after a crash, the job can restart or reload deterministically.
3. The workflow does not depend on reading unlogged table contents from a physical standby.
4. Multiple sessions genuinely need to share intermediate data.
5. Operational gains have been measured and justify the trade-off.

**Never choose UNLOGGED for orders, invoices, payments, mandatory audit logs, or unique data lacking a trusted recovery source.**

## 8. Detailed comparison of durability, transactions, and scope

Misconceptions often arise from conflating three independent properties: **persistence**, **transaction semantics**, and **visibility**.

### 8.1. Persistence: does the object survive?

- Permanent: persists until `DROP` or an appropriate administrative action.
- TEMP: defaults to session lifetime; `ON COMMIT DROP` can remove it sooner.
- UNLOGGED: the object persists long-term, even after its data is truncated by a crash.

### 8.2. Transaction semantics: can changes roll back?

All three table types support transactional DML operations. Example:

```sql
BEGIN;

INSERT INTO table_kinds_lab.import_lines
    (batch_id, line_no, raw_product_code, raw_quantity)
VALUES
    (5002, 1, 'P003', '10');

ROLLBACK;
```

The row inserted into UNLOGGED does not become a committed change after rollback, matching permanent table rollback semantics.

**Conceptual trap:** "not WAL-logged like permanent tables" **does not mean** "non-transactional". Transaction rollback while the server is running and crash recovery after failure are two separate requirements.

### 8.3. Visibility: which sessions can see it?

- Permanent and UNLOGGED: multiple sessions can access the same object, though other sessions only see changes per commit/snapshot/privileges.
- TEMP: Session A and Session B have separate objects; B cannot directly read rows in A's temp table.
- A session can create a TEMP table sharing the name of a permanent table, triggering special name-resolution precedence rules.

## 9. Event-by-event comparison table

Assume all three table types have been created and data has been inserted and committed.

| Event | Permanent | Default TEMP | UNLOGGED |
| --- | --- | --- | --- |
| Creating session runs `COMMIT` | Retains committed rows | Retains rows (`PRESERVE ROWS`) | Retains committed rows |
| Creating session disconnects | Table and data remain | Table is dropped | Table and data remain |
| Another session opens with privileges | Can read | Cannot directly read previous session's TEMP | Can read |
| Clean PostgreSQL shutdown and restart | Remains | Session ends, TEMP gone | Usually remains |
| PostgreSQL crash/unclean shutdown | WAL recovery per durability | Session ends, TEMP gone | Data can be truncated |
| Transaction with `INSERT` then `ROLLBACK` | Insert is undone | Insert is undone | Insert is undone |
| Supports `ON COMMIT DELETE ROWS` | Not via temp mechanism | Yes | Not via temp mechanism |
| Creating standard indexes | Yes | Yes | Yes |
| Using in `JOIN`/`GROUP BY` queries | Yes | Yes | Yes |

Notable point: a temporary table is not "limited to a single transaction"; by default it can span **multiple transactions** on the same connection.

## 10. Indexes, statistics, and constraints across the three table types

### 10.1. Indexing TEMP and UNLOGGED tables

Temp example:

```sql
CREATE TEMP TABLE t_index_demo (
    order_id bigint NOT NULL,
    customer_id bigint NOT NULL,
    amount numeric(12,2) NOT NULL
);

CREATE INDEX idx_t_index_customer
    ON t_index_demo (customer_id);
```

The index belongs to the session's temporary table data; it does not become a database-wide index shared across other sessions.

Unlogged example:

```sql
CREATE INDEX idx_import_lines_product
    ON table_kinds_lab.import_lines (raw_product_code);
```

Indexes accelerate access to UNLOGGED tables, while also consuming disk space and write overhead just like any index design. Indexes on unlogged tables are managed with matching unlogged characteristics.

**Creating an index does not automatically speed up every query:** on small tables, a sequential scan can be cheaper. Always use `EXPLAIN` and measure in practice.

### 10.2. TEMP tables and planner statistics

Standard autovacuum **does not vacuum or analyze other sessions' temporary tables**, because only the owning backend can process that data in its proper context. For large TEMP tables, consider running:

```sql
ANALYZE t_index_demo;
```

After loading many rows, `ANALYZE` gives PostgreSQL statistics so the optimizer selects appropriate JOINs, scans, and indexes.

For permanent and UNLOGGED tables, autovacuum/analyze runs according to configuration and workload. Unlogged tables should not be treated as exempt from maintenance merely because they reduce WAL.

### 10.3. Constraints still matter

All three table types can have `PRIMARY KEY`, `UNIQUE`, `NOT NULL`, and `CHECK` constraints as applicable. Example:

```sql
CREATE TEMP TABLE t_validated_lines (
    product_code text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (product_code)
);
```

These constraints enforce validity of intermediate data right inside the session. However, storing multi-table relational data requiring foreign keys can encounter relation-type restrictions; never blindly convert an entire complex relational schema to temp/unlogged without checking compatibility.

## 11. TEMP tables shadowing same-named permanent tables

PostgreSQL creates an internal temporary schema for a session, typically named `pg_temp_N`. A temporary table **can shadow** a same-named permanent table when you reference an unqualified name.

Permanent table example:

```sql
CREATE TABLE table_kinds_lab.daily_totals (
    report_date date PRIMARY KEY,
    total_amount numeric(12,2) NOT NULL
);

INSERT INTO table_kinds_lab.daily_totals
    (report_date, total_amount)
VALUES (DATE '2026-11-14', 750000.00);
```

In Session A, create a temporary table named `daily_totals`:

```sql
CREATE TEMP TABLE daily_totals (
    report_date date PRIMARY KEY,
    total_amount numeric(12,2) NOT NULL
);

INSERT INTO daily_totals
    (report_date, total_amount)
VALUES (DATE '2026-11-14', 123.00);
```

If you use an unqualified name:

```sql
SELECT * FROM daily_totals;
```

the result can come from **Session A's TEMP table**, not `table_kinds_lab.daily_totals`.

To access unambiguously:

```sql
-- Permanent table:
SELECT * FROM table_kinds_lab.daily_totals;

-- Current session's temporary table:
SELECT * FROM pg_temp.daily_totals;
```

**Consequence:** for critical writes or deletes, omitting the schema name can operate on the wrong object. Especially in `SECURITY DEFINER` functions or complex `search_path` setups, design name resolution safely.

## 12. Distinguishing TEMP tables from executor temporary files

Temporary tables are created intentionally with `CREATE TEMP TABLE`. However, PostgreSQL can also create **temporary disk files** to execute a query when intermediate processing exceeds available memory.

Examples of operations that can generate temp files:

- `ORDER BY` on large row sets.
- Certain `GROUP BY`, hash join, or materialization steps.
- Sorting data in memory-intensive operations.

```text
SELECT ... ORDER BY ...
          |
          +-- Sufficient memory for the sort
          |       |
          |       +-- Processed in RAM
          |
          +-- Insufficient
                  |
                  +-- Spills to temporary disk files
                  +-- Managed automatically by query execution
```

| Characteristic | TEMP table | Internal temporary file |
| --- | --- | --- |
| Created via SQL? | Yes, `CREATE TEMP TABLE` | Usually created automatically by executor |
| Has a table name for `SELECT`? | Yes | No |
| Reused across multiple statements? | Possible | Generally no |
| Can create SQL indexes? | Yes | Not in the manner of a SQL table |
| Purpose | Intentional intermediate results | Sort/hash/spill when a query needs it |

You can observe database temp-file activity:

```sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_bytes_pretty
FROM pg_stat_database
WHERE datname = current_database();
```

`pg_stat_database.temp_files` and `temp_bytes` are not counters of temporary tables. They reflect internal temporary files recorded by PostgreSQL statistics.

The `work_mem` parameter governs memory used by certain sort/hash operations; raising it indiscriminately can exhaust RAM when many concurrent queries each run multiple execution nodes.

## 13. Using `pg_class.relpersistence` to inspect table type

PostgreSQL stores metadata in system catalogs. The `pg_class.relpersistence` column indicates a relation's persistence mode.

| Value | Persistence type |
| --- | --- |
| `p` | Permanent |
| `u` | Unlogged |
| `t` | Temporary |

Example:

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    c.relpersistence
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relname IN (
    'orders',
    'temp_order_ids',
    'import_lines'
)
  AND c.relkind IN ('r', 'p')
ORDER BY n.nspname, c.relname;
```

How to interpret:

- `relkind = 'r'` is normally an ordinary table.
- `relkind = 'p'` is a partitioned table in modern PostgreSQL releases.
- `relpersistence = 'p'`, `'u'`, or `'t'` distinguishes the three persistence modes.

**Do not confuse `relkind` with `relpersistence`.** The two columns describe different aspects of a relation. Querying `pg_class` may also display some metadata about temp relations in other sessions, yet **grants no permission to query another session's TEMP data**.

### 13.1. Identifying the session's TEMP schema

Inside a session that has created a temp table:

```sql
SELECT pg_backend_pid() AS backend_pid,
       pg_my_temp_schema() AS temp_schema_oid;
```

`pg_my_temp_schema()` returns the OID of the current session's temporary schema (or 0 if no temp schema exists yet). You can view the schema name:

```sql
SELECT nspname
FROM pg_namespace
WHERE oid = pg_my_temp_schema();
```

In application code, avoid guessing `pg_temp_N`; use the `pg_temp` alias or appropriate table names within the same session.

### 13.2. Size inspection does not replace durability

```sql
SELECT
    pg_size_pretty(
        pg_total_relation_size('table_kinds_lab.orders')
    ) AS orders_total_size;
```

This function shows the total size of the relation and its associated components in its current state. However, a tiny table can still hold critical business data, while a huge UNLOGGED table remains unsafe against crashes. **Size does not determine which persistence type to pick**.

## 14. Data import workflow: TEMP or UNLOGGED staging?

Suppose every night the system receives a file containing millions of product codes and quantities. Final data must be stored durably, while the parsing step can be regenerated from the source file.

A workflow might look like:

```text
Durable source file / object storage
           |
           v
Import raw lines
           |
           +-- If single session only: TEMP staging
           |
           +-- If multiple workers must read: UNLOGGED staging
           |
           v
Validate / transform / deduplicate
           |
           v
Commit to PERMANENT tables
           |
           v
Mark batch successful in durable system
           |
           v
Clean up staging per policy
```

**Decision question:** does staging need to be shared across connections?

- If **no**, TEMP may be simpler because it cleans up automatically with the session.
- If **yes** and data is reproducible, UNLOGGED may fit.
- If **yes** and losing staging would lose business data or hinder recovery, permanent staging remains safer.

### 14.1. Loading data into UNLOGGED staging

Table `table_kinds_lab.import_lines` was created above. Load sample rows:

```sql
INSERT INTO table_kinds_lab.import_lines
    (batch_id, line_no, raw_product_code, raw_quantity)
VALUES
    (6001, 1, 'P001', '2'),
    (6001, 2, 'P002', '5'),
    (6001, 3, 'P003', 'invalid-number');
```

The `raw_quantity text` column intentionally preserves raw values so validation can detect malformed rows without failing the entire import command on an immediate cast error.

To process a batch:

```sql
SELECT
    batch_id,
    line_no,
    raw_product_code,
    raw_quantity
FROM table_kinds_lab.import_lines
WHERE batch_id = 6001
ORDER BY line_no;
```

Two sessions can both read the committed batch.

### 14.2. Selecting valid data into a TEMP table

Inside a processing session:

```sql
BEGIN;

CREATE TEMP TABLE valid_import_lines (
    batch_id bigint NOT NULL,
    line_no integer NOT NULL,
    product_code text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (batch_id, line_no)
) ON COMMIT DROP;

INSERT INTO valid_import_lines
    (batch_id, line_no, product_code, quantity)
SELECT
    batch_id,
    line_no,
    raw_product_code,
    raw_quantity::integer
FROM table_kinds_lab.import_lines
WHERE batch_id = 6001
  AND raw_quantity ~ '^[1-9][0-9]*$';

SELECT *
FROM valid_import_lines
ORDER BY line_no;

COMMIT;
```

The example uses regex to filter positive integer strings before casting. On real data, you must also check whether values fit within `integer` range, whether product codes are valid, duplicate/missing lines, and error-handling policies. Even a digit-only string can **overflow** when cast to `integer` if it is too long.

With `ON COMMIT DROP`, `valid_import_lines` disappears automatically after commit. If you need to continue processing across another transaction in the same session, use `PRESERVE ROWS` instead of `DROP`.

### 14.3. Writing final results into a permanent table

Example durable target table:

```sql
CREATE TABLE table_kinds_lab.accepted_import_lines (
    batch_id bigint NOT NULL,
    line_no integer NOT NULL,
    product_code text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (batch_id, line_no)
);
```

In a new transaction, you can create and use a temp table to determine what gets written into the real table:

```sql
BEGIN;

CREATE TEMP TABLE to_accept
ON COMMIT DROP
AS
SELECT
    batch_id,
    line_no,
    raw_product_code AS product_code,
    raw_quantity::integer AS quantity
FROM table_kinds_lab.import_lines
WHERE batch_id = 6001
  AND raw_quantity ~ '^[1-9][0-9]*$';

INSERT INTO table_kinds_lab.accepted_import_lines
    (batch_id, line_no, product_code, quantity)
SELECT
    batch_id,
    line_no,
    product_code,
    quantity
FROM to_accept
WHERE true
ON CONFLICT (batch_id, line_no) DO NOTHING;

COMMIT;
```

`ON CONFLICT DO NOTHING` is an **illustrative policy** to avoid inserting duplicate `batch_id + line_no` pairs. In real projects, clearly decide whether duplicates are an error to report or a valid retry.

For large batches, design completeness checks, invalid-row handling, idempotency, transaction sizing, and resource limits before deploying.

### 14.4. What if a crash occurs mid-import?

- If UNLOGGED data is truncated, **re-read from the safely stored source**.
- If an uncommitted transaction writing to a permanent table was interrupted, PostgreSQL rolls back the uncommitted portion per recovery rules.
- Rows already committed to permanent tables remain durable per database configuration.
- Open TEMP tables in the processing session vanish when the connection terminates.

Therefore, state tracking "which files have been successfully processed"—if not reproducible—should be recorded in a **permanent table or durable state store**, not solely inside UNLOGGED staging.

## 15. `COPY` and `\copy` when loading staging data

PostgreSQL provides `COPY` for bulk data import/export. `psql` provides the `\copy` meta-command to process files on the client side.

Example loading a CSV file from the machine running `psql`:

```text
\copy table_kinds_lab.import_lines (batch_id, line_no, raw_product_code, raw_quantity) FROM 'batch_6002.csv' WITH (FORMAT csv, HEADER true)
```

The line above is a **`psql` meta-command** and assumes the CSV file columns match the specified order. `\copy` reads files from the client environment, whereas variants like `COPY ... FROM '/server/path.csv'` have the PostgreSQL server read files on the server host and require appropriate privileges.

Choosing TEMP or UNLOGGED **does not dictate** using `COPY` vs. `\copy`. Two independent questions apply:

- What lifecycle/scope/durability does the target table need?
- Does the source file live on the client or server machine, and where are read permissions granted?

Never use `COPY` from server files in unprivileged environments, and never treat WAL reduction as an excuse to skip input data validation.

## 16. Switching a permanent table to UNLOGGED or vice versa

PostgreSQL provides commands to switch persistence on eligible tables:

```sql
-- Switch table from logged to unlogged:
ALTER TABLE table_kinds_lab.some_staging
    SET UNLOGGED;

-- Switch back to logged:
ALTER TABLE table_kinds_lab.some_staging
    SET LOGGED;
```

**These commands illustrate syntax only**; `some_staging` was not created in this lesson. Do not run them verbatim without an intentionally selected table.

These changes are not free performance switches:

- They can require **rewriting** table data and associated indexes.
- They can acquire strong locks on the table during conversion.
- They affect replication and durability.
- Restrictions may apply depending on relation kind and dependency relationships.
- You must evaluate table size, PostgreSQL version, maintenance window, privileges, and recovery plans.

**Never switch a live business table to UNLOGGED just to test a speedup**, believing that switching back via `SET LOGGED` will recover data lost in an earlier crash.

For TEMP tables, converting them directly to permanent tables via the same persistence syntax above makes no sense. To keep the data, the clearer approach is to **create a permanent table and insert rows from TEMP while the session is still alive**.

Example:

```sql
-- Assumes temp_large_orders currently exists in the session.
CREATE TABLE table_kinds_lab.saved_large_orders AS
SELECT * FROM temp_large_orders;
```

The new table is permanent by default. However, `CREATE TABLE AS` **does not automatically copy all constraints, indexes, and privileges** a production table needs; apply proper schema design afterward.

## 17. When is TEMP better than a CTE or materialized view?

These three tools are often confused because all three can hold "intermediate results".

### 17.1. CTE for logic within a single SQL statement

```sql
WITH high_value AS (
    SELECT order_id, amount
    FROM table_kinds_lab.orders
    WHERE amount >= 200000
)
SELECT COUNT(*) AS order_count,
       COALESCE(SUM(amount), 0) AS total_amount
FROM high_value;
```

A CTE does not create a standalone TEMP table reusable across subsequent statements. PostgreSQL may inline or materialize a CTE depending on query structure, version, and optimizer choices; **do not assume a CTE is always equivalent to a physical temp table**.

### 17.2. TEMP when multiple statements need the same intermediate set

Use TEMP when you need to:

- Load a large set of IDs, build an index, and JOIN multiple times.
- Run several distinct processing steps inside the same backend/session.
- Explicitly hold intermediate data within a session and clean up afterward.

However, creating and dropping temp tables incurs metadata and catalog overhead. When many connections continuously create thousands of temp tables, measure the cost rather than assuming TEMP always beats CTEs.

### 17.3. Materialized views have a different lifecycle

A materialized view persists query results as of creation/refresh time as a long-lived object:

```sql
CREATE MATERIALIZED VIEW table_kinds_lab.order_summary AS
SELECT
    COUNT(*) AS order_count,
    COALESCE(SUM(amount), 0) AS total_amount
FROM table_kinds_lab.orders;
```

When source tables change, the materialized view does not update continuously; it requires:

```sql
REFRESH MATERIALIZED VIEW table_kinds_lab.order_summary;
```

Materialized views fit scenarios where you want to store repeatedly read results across many sessions and manage refreshes explicitly. It is **not a TEMP table** merely because its contents are computed from a query.

## 18. Connection pools and transaction pooling: real-world pitfalls

A Java service typically uses a connection pool. One request queries the database via connection A and returns it to the pool; the next request might receive A or a different connection.

```text
HTTP request 1
    |
    v
Connection A: CREATE TEMP TABLE report_rows
    |
    v
Return Connection A to pool

HTTP request 2
    |
    +-- If assigned Connection A: report_rows may still exist
    |
    +-- If assigned Connection B: report_rows does not exist
```

Therefore, **never design a multi-request workflow relying on a TEMP table remaining available** without an explicit guarantee of the exact same backend/session.

### 18.1. Session pooling vs. transaction pooling

With a pooler like PgBouncer:

- **Session pooling:** a server connection can be held for a client session for the duration of that session.
- **Transaction pooling:** a server connection can be returned to the pool and assigned to another client after every transaction.

Under transaction pooling, you cannot assume **TEMP tables with `PRESERVE ROWS`**, session-level prepared statements, persistent `SET` commands, or session-level advisory locks remain present on the client's next transaction.

Compatibility features may depend on pooler version and configuration. A safe design principle is to **use only state guaranteed to be supported by the actual pooling mode**.

### 18.2. Keeping TEMP within a single transaction

If using a pooler that reassigns backends per transaction, a sound strategy for short tasks is creating, using, and dropping the temp table **within the same transaction**:

```sql
BEGIN;

CREATE TEMP TABLE selected_ids (
    order_id bigint PRIMARY KEY
) ON COMMIT DROP;

INSERT INTO selected_ids (order_id)
SELECT order_id
FROM table_kinds_lab.orders
WHERE amount >= 200000;

SELECT o.order_id, o.amount
FROM table_kinds_lab.orders AS o
JOIN selected_ids AS s USING (order_id);

COMMIT;
```

All SQL statements must execute over **the exact same connection** within the transaction; drivers/frameworks must not silently swap connections between steps. Nor does this mean the temp table is shared with another request.

### 18.3. Cleaning up state properly

Inside the same session, you can explicitly drop the temp table:

```sql
DROP TABLE IF EXISTS pg_temp.selected_ids;
```

`DISCARD TEMP` can clean up eligible temporary objects in a session you control:

```sql
DISCARD TEMP;
```

`DISCARD ALL` clears more types of session state, yet cannot run inside a transaction block and carries overhead. Do not run it blindly on every request without checking connection pool requirements.

If a real workflow must span multiple connections, store state in a **permanent table** or a shared storage mechanism with an appropriate lifecycle.

## 19. Operational questions on crashes, backups, and replication

### 19.1. Clean restart differs from crash

| Scenario | Permanent | UNLOGGED | TEMP |
| --- | --- | --- | --- |
| Clean PostgreSQL stop and restart | Committed data remains | Data usually remains | Old session ends, temp table gone |
| Crash/unclean shutdown and recovery | Recovered via WAL/durability | Data truncated per recovery rules | Old session ends, temp table gone |
| Client disconnects | Committed data not lost | Committed data not lost merely from disconnect | That session's temp tables are dropped |

This is why you should never say "restart" vaguely when discussing UNLOGGED incidents. Always determine whether PostgreSQL shut down **cleanly** or **uncleanly**.

### 19.2. Backups of UNLOGGED tables

WAL-based recovery/physical replication **does not provide full protection for UNLOGGED contents**. Some logical backup workflows can export unlogged data depending on tools and options, yet this must not be taken as proof that every backup/replica holds that data.

For example, `pg_dump` has `--no-unlogged-table-data` to exclude UNLOGGED table data. Accordingly, when planning backup/restore:

- Identify the backup type (logical dump, physical backup, provider-managed backup).
- Verify whether options export unlogged contents.
- Test restoring into an isolated environment to see what data actually survives.
- Treat the original import source as the authoritative place to reload staging.

### 19.3. Replication is not backup

A primary and standby do not replace historical backups for recovering from accidental deletes, application bugs, or mistaken administrative actions. With UNLOGGED, contents are not physically streamed via replication like permanent tables, making a staging replay strategy even more essential.

### 19.4. Monitoring

When using UNLOGGED tables for staging, monitor:

- Number of batches in flight.
- Input, valid, and rejected row counts.
- Staging and index disk usage.
- Which source data is reloaded from after a crash.
- Incomplete jobs requiring retry.
- Impact on CPU/I/O and SQL query performance.

For TEMP tables, also monitor concurrent connections, temp create/drop frequency, temp disk usage, and bloat/statistics if workloads are complex.

## 20. Performance: should every table be converted to UNLOGGED or TEMP?

**No.** Choosing a table type is only one decision in data optimization.

### 20.1. Total cost must be measured

A query or batch spends time on:

```text
Total time
  ≈ reading source
   + constraint checks
   + writing data and indexes
   + WAL/flush (if applicable)
   + JOIN/sort/aggregate processing
   + lock waits, I/O, CPU
   + network data transfer
```

Using UNLOGGED can reduce part of the WAL cost; it does not eliminate the rest.

### 20.2. Properly comparing the three variants

If the goal is loading 2 million staging rows, test in the same environment:

| Variant | Target table | What to record |
| --- | --- | --- |
| A | Permanent | Import duration, WAL generated, CPU/I/O, index cost |
| B | UNLOGGED | Import duration, I/O, other impacts, reload plan |
| C | TEMP | Single-session import duration, overhead, multi-session limits |

Keep datasets, indexes, schema constraints, worker counts, and loading methods identical where possible. Remember that TEMP and UNLOGGED have **different semantics**, so a variant with fast runtime that fails sharing or durability requirements is not a valid choice.

### 20.3. Index before or after loading?

For large reproducible staging, loading into a lightly indexed table and creating processing indexes afterward can sometimes outperform maintaining multiple indexes across every insert. However:

- Index creation has its own cost and I/O consumption.
- Constraint and consistency checks may still be needed.
- Concurrent permanent/UNLOGGED usage requires evaluating lock/DDL timing.
- For single-session TEMP tables, index creation must pay off over the remaining JOINs/queries.

There is no universal "always create indexes after import" rule for every workload.

## 21. Choosing table types: concrete scenarios

| Scenario | Typically suitable table type | Reason |
| --- | --- | --- |
| Paid orders | **Permanent** | Cannot accept data loss after crash |
| Mandatory audit logs | **Permanent** | Requires durability and backup procedures |
| Result cache used only in one reporting session | **TEMP** | Auto-cleans when session ends |
| Intermediate ID set reused across three SELECTs in one transaction | **TEMP ON COMMIT DROP** | Data needed only until commit |
| Scratch table cleared after each transaction | **TEMP ON COMMIT DELETE ROWS** | Keeps schema, clears rows on commit |
| Re-loadable import file read concurrently by multiple workers | **UNLOGGED**, if risk accepted | Shared across sessions, reduces some WAL |
| Unique import file not stored elsewhere | **Permanent** | Losing staging would lose the source data |
| Report output opened by another app the next day | **Permanent** or other durable storage | TEMP does not survive across sessions |
| Intermediate data used inside one SQL statement | CTE/subquery | No need to create a separate table |
| Data needed on physical standby | **Permanent** | UNLOGGED does not replicate data like permanent tables |
| Aggregated stats refreshed on a schedule | Permanent/materialized view per design | Data has its own lifecycle and refresh policy |
| Request whose connection isn't pinned across steps | Do not rely on TEMP across connections | TEMP belongs to a single specific session |

These choices are design guidelines, not substitutes for evaluating privileges, constraints, workloads, and operational plans.

## 22. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "TEMP holds data for one transaction." | TEMP defaults to **session** lifetime, spanning multiple transactions |
| "`COMMIT` always clears TEMP." | PostgreSQL defaults to `ON COMMIT PRESERVE ROWS` |
| "`ON COMMIT DROP` can be created outside a transaction and used later." | Under autocommit, the table can be dropped right after the create statement |
| "TEMP doesn't support transactions." | Eligible DML/DDL on TEMP still supports `COMMIT`/`ROLLBACK` |
| "UNLOGGED is TEMP that doesn't auto-delete." | UNLOGGED is a shared table with persistence semantics distinct from TEMP |
| "UNLOGGED loses data after every restart." | Data usually survives clean restarts, but is truncated after crashes/unclean shutdowns |
| "UNLOGGED is fast so it's great for balances." | Lacks crash durability and permanent-table replication; unsuitable for critical data |
| "Committed UNLOGGED data survives crashes." | Commit does not turn unlogged data into WAL-protected data |
| "TEMP cannot have indexes or PKs." | Can have indexes and many applicable constraints |
| "Autovacuum always updates stats on all TEMP tables." | Large TEMP tables generally need explicit `ANALYZE` |
| "Sort temp files are TEMP tables." | Internal temporary disk files are not named SQL tables |
| "If one session creates TEMP, another can read it via `pg_temp_N`." | TEMP data belongs to its session and is not directly shared |
| "Returning a connection to a pool ends the session." | Pools can keep backends alive and reuse session state |
| "`CREATE TABLE AS SELECT` preserves all source constraints/indexes." | Creates a result table without copying full schema attributes |
| "WAL protects UNLOGGED data on replicas too." | UNLOGGED data is not physically replicated via WAL like permanent tables |
| "Missing TEMP after restart proves a crash wiped permanent data." | TEMP disappears when sessions end; it says nothing about permanent durability |

## 23. Practice exercises and answers

### Exercise 1. Choosing a table for payment results

A payment transaction is confirmed; the data must survive after the application disconnects and PostgreSQL recovers from a crash. Which table type should you choose?

**Answer:** a permanent table with transactions, appropriate WAL/durability settings, backups, and replication. Neither TEMP nor UNLOGGED satisfies recovery requirements for such critical data.

### Exercise 2. Two sessions both creating `TEMP t`

Session A:

```sql
CREATE TEMP TABLE t (id integer);
INSERT INTO t VALUES (1);
```

Session B:

```sql
CREATE TEMP TABLE t (id integer);
INSERT INTO t VALUES (2);
```

**Question:** What will A see when running `SELECT * FROM t`?

**Answer:** A reads **its own** temp table containing row 1; it does not see row 2 in B's table.

### Exercise 3. Does commit delete a default temp table?

```sql
CREATE TEMP TABLE t_default (id integer);
INSERT INTO t_default VALUES (10);
COMMIT;
SELECT * FROM t_default;
```

**Answer:** PostgreSQL defaults to `ON COMMIT PRESERVE ROWS`. If the insert committed under autocommit, the table and row 10 still exist in the session. An explicit `COMMIT` outside a transaction may emit a warning that no transaction is in progress, without making the temp table vanish.

### Exercise 4. Choosing `ON COMMIT DELETE ROWS`

```sql
CREATE TEMP TABLE t_clean (id integer)
ON COMMIT DELETE ROWS;

BEGIN;
INSERT INTO t_clean VALUES (1), (2);
COMMIT;
SELECT COUNT(*) FROM t_clean;
```

**Answer:** `0`. The table still exists, but its rows are deleted when the transaction commits.

### Exercise 5. Choosing `ON COMMIT DROP`

```sql
BEGIN;
CREATE TEMP TABLE t_once (id integer)
ON COMMIT DROP;
INSERT INTO t_once VALUES (5);
COMMIT;
```

**Question:** After commit, can you run `SELECT * FROM t_once`?

**Answer:** No, the table was dropped according to its policy.

### Exercise 6. Does UNLOGGED lack rollback support?

```sql
BEGIN;
INSERT INTO table_kinds_lab.import_lines
    (batch_id, line_no, raw_product_code, raw_quantity)
VALUES (7001, 1, 'P123', '4');
ROLLBACK;
```

**Answer:** Rollback still undoes the insert. UNLOGGED affects **WAL/crash recovery**, not transaction semantics.

### Exercise 7. Does an UNLOGGED table keep its name after a crash?

**Answer:** Its table structure/definition can still exist, yet the unlogged table's contents are truncated when PostgreSQL recovers from an unclean shutdown. The application must have a reload plan to continue processing.

### Exercise 8. What does `pg_class.relpersistence = 'u'` indicate?

**Answer:** It indicates an **unlogged** relation. `'p'` is permanent and `'t'` is temporary. Do not confuse this column with `relkind`, which describes the relation object kind.

### Exercise 9. A report uses a TEMP table on connection A, the next step runs on connection B and reports table not found

**Cause:** the temp table belongs to A, so B cannot use it. Keep steps on the same backend/session or use shared storage when a workflow must span multiple connections.

### Exercise 10. Why does `pg_stat_database.temp_bytes` rise when nobody creates TEMP tables?

**Answer:** PostgreSQL can create temporary disk files to spill sorts/hashes during query execution. These are not SQL TEMP tables.

### Exercise 11. Choosing a table type for import staging

CSV files are stored in object storage and can be reloaded anytime. Three workers on the same primary need to read the shared staging batch; data is not needed on standbys. Which table can be considered?

**Answer:** UNLOGGED can fit if truncating staging after a crash is acceptable and retry/reload logic is designed. Permanent remains a valid option if simplicity and stronger protection are preferred; TEMP is unsuitable for sharing across workers in different sessions.

### Exercise 12. A TEMP table holds 3 million rows and the planner picks a poor plan

**Hint:** after loading data, run `ANALYZE` on the TEMP table, inspect indexes, and check `EXPLAIN`. Do not wait for autovacuum to update statistics on a session's temp table as it does on permanent tables.

## 24. Decision template before creating a table

A practical checklist:

```text
Dataset name:
    _________________________________________

Dataset survives until:
    [ ] End of a single SQL statement
    [ ] COMMIT / ROLLBACK
    [ ] End of a session
    [ ] End of a batch/job
    [ ] Long-term

Who reads?
    [ ] Single connection
    [ ] Multiple connections
    [ ] Multiple services
    [ ] Read replica

Fully reproducible after a crash?
    [ ] Yes, from a durable source
    [ ] No
    [ ] Unclear

Data protection requirements:
    [ ] Needs crash durability
    [ ] Staging loss acceptable
    [ ] Needs backup/restore
    [ ] Needs replication

Operational processes:
    [ ] Designated owner/worker for cleanup
    [ ] Retry/idempotency implemented
    [ ] Appropriate statistics and indexes
    [ ] Benchmarked, monitoring WAL/I/O/CPU
    [ ] Connection pooling verified

Chosen table type:
    [ ] Permanent
    [ ] TEMP + ON COMMIT policy: _____________
    [ ] UNLOGGED + reload plan: ______________
```

If you are not yet sure whether data **is reproducible after a crash** or **needs sharing across sessions**, do not rush into UNLOGGED or TEMP as an "optimization trick".

## 25. Summary

PostgreSQL provides three ways to organize tables with clear trade-offs:

- **Permanent tables** are the default for durable data: objects and committed data survive across sessions and restarts, with WAL-based crash recovery under proper configuration.
- **TEMP tables** store intermediate results for **a single session**. Tables can span multiple transactions and default to `ON COMMIT PRESERVE ROWS`; `DELETE ROWS` and `DROP` allow clearing data or dropping the table at commit.
- **UNLOGGED tables** persist and are shared like regular tables, yet data **is not WAL-protected across crashes and is not replicated via physical streaming replication like permanent tables**. They fit reloadable staging data best.
- **Transactions and durability are distinct concepts.** TEMP and UNLOGGED still support `COMMIT`, `ROLLBACK`, indexes, and many constraints, without providing the same lifecycle and crash recovery as permanent tables.
- **TEMP tables differ from temporary disk files**, as well as CTEs and materialized views. Create tables only when named intermediate data reused across multiple steps is genuinely required.
- **Inspect table types with `pg_class.relpersistence`** when needed: `p`, `t`, and `u` correspond to permanent, temporary, and unlogged.
- **Connection pooling, duplicate table names, and `search_path`** can cause subtle bugs if session scope is misunderstood.
- **Benchmark performance and assess recovery costs** before choosing UNLOGGED: reducing WAL has no value if data must survive all failures.

The final deciding question is not "which table is fastest?", but rather: **how long must this dataset exist, who needs access, is loss after a crash acceptable, and how will the system recover?** Choosing the right table type from those answers keeps PostgreSQL designs both clear and operationally sound.
