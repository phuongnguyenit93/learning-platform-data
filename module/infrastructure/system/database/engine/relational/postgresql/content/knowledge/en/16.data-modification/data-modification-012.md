# Evaluating the Impact of Data Modification on Indexes, WAL, and Replication in PostgreSQL

From an application's perspective, an `INSERT`, `UPDATE`, or `DELETE` statement often looks very short. For example:

```sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 1001;
```

However, PostgreSQL does not simply "edit a cell in a table." Depending on the table structure, indexes, and system configuration, an operation can create a new tuple version under **MVCC**, write or update entries in **indexes**, generate **Write-Ahead Log (WAL)** records, dirty buffer pool pages, create work for **VACUUM**, and transmit and apply changes to **replicas**.

When a service grows from a few thousand to millions of writes per day, these indirect costs can drive up latency, disk I/O, WAL volume, replica lag, or fill up the `pg_wal` disk. An `UPDATE` that "changes just one column" can sometimes generate more I/O than an `INSERT`; a new index speeds up `SELECT` queries while making write workloads more expensive; and a transaction that commits successfully on the primary does not automatically mean every standby has already applied the data.

This lesson shows how to **trace the entire write path**, **measure it with PostgreSQL tools**, and **make evidence-based trade-offs** among write speed, read speed, durability, and replication lag.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe the path from `INSERT`/`UPDATE`/`DELETE` to heap pages, indexes, WAL, and standbys.
2. Explain why MVCC causes `UPDATE` to create new row versions and `DELETE` to leave tuples that must be cleaned up.
3. Distinguish **HOT updates** from non-HOT updates and understand the impact of indexed columns, expression indexes, partial indexes, and `fillfactor`.
4. Analyze write costs for B-tree and other index types, and recognize **write amplification**.
5. Explain WAL's role in crash recovery, durability, backup/PITR, and physical/logical replication.
6. Recognize how **full-page images (FPI)**, checkpoints, `wal_compression`, and large transactions affect WAL volume.
7. Distinguish **physical streaming replication** from **logical replication**, and understand the scope of replica identity and publication/subscription.
8. Monitor metrics such as `n_tup_upd`, `n_tup_hot_upd`, `n_dead_tup`, index size, `pg_stat_wal`, WAL LSNs, and replication lag.
9. Use `EXPLAIN (ANALYZE, BUFFERS, WAL)` in a **test database** to gather evidence of a write operation's cost.
10. Choose appropriate batch, index, schema, `VACUUM`, and replication strategies without recklessly disabling data-safety mechanisms.
11. Explain why minimizing WAL or reducing index count is not always the right optimization.
12. Build a risk-assessment checklist before running a large data-modification campaign.

**Scope:** Focuses on modern PostgreSQL regular logged tables with WAL and MVCC. Certain statistics views may vary by PostgreSQL version or account privileges. Run lab exercises only in a test database; never run benchmarks or alter production settings by copying illustrative SQL verbatim.

---

## 2. Mental Model: Which Layers Does a Write Operation Traverse?

Consider an application executing a data-modifying transaction:

```text
Application
   |
   v
BEGIN / INSERT / UPDATE / DELETE / COMMIT
   |
   +----> Permission, constraint, trigger, FK, and lock checks
   |
   +----> Heap/table pages: new tuple, new version, or marked deleted
   |           |
   |           +----> Dead tuples, page pruning, future VACUUM work
   |
   +----> Indexes: insert/update required index tuples
   |           |
   |           +----> Possible page splits, bloat, write I/O
   |
   +----> WAL: write records describing recoverable changes
   |           |
   |           +----> Flush WAL to satisfy durability level
   |           +----> Archive WAL / PITR
   |           +----> Physical streaming replication
   |           +----> Logical decoding / logical replication
   |
   +----> Dirty buffers flushed to data files later
   |
   +----> COMMIT acknowledged per synchronous_commit
                 and applicable standby settings
```

Key point: **WAL is not a literal copy of SQL statements**, and writing WAL does not mean heap/index data pages have been flushed to data files immediately.

PostgreSQL follows the **write-ahead** rule: before a data page modification is considered durable in the data files, the WAL needed to recover that change must be written/flushed as required. Writing data pages is orchestrated later by shared buffers, the background writer, the checkpointer, and other processes; after a crash, PostgreSQL replays WAL to restore a consistent state.

### 2.1. Three Distinct Cost Layers

| Layer | Typical costs | What to measure |
| --- | --- | --- |
| Heap/MVCC | New tuple versions, dirty buffers, dead tuples, VACUUM | Rows changed, HOT updates, dead/live tuples, table size |
| Index | New index tuples, page reads/writes, page splits, bloat | Index count/selection, index size, query plans, write overhead |
| WAL/Replication | WAL records, FPI, flushes, network send, standby replay/apply | WAL bytes/FPI, commit latency, slot retention, LSN lag |

A single transaction can put different kinds of pressure on all three layers. For instance, adding an index can speed up reads while increasing WAL and update cost; batching tiny transactions reduces per-commit overhead, whereas oversized transactions create WAL bursts and long lag spikes.

### 2.2. What Is Write Amplification?

**Write amplification** occurs when a small logical change in the application triggers multiple physical write operations or ongoing maintenance work.

Conceptual example:

```text
One logical UPDATE
  -> writes a new tuple version in the heap
  -> may create new index entries across multiple indexes
  -> writes WAL for heap/index/pages
  -> retains the old tuple for MVCC
  -> requires later VACUUM/pruning cleanup
  -> ships and applies WAL on standbys
```

There is no fixed multiplier like "one UPDATE = five writes." Actual cost depends on the operation type, index count, tuple width, data distribution, free space on heap pages, checkpoints, transaction boundaries, replicas, and WAL settings.

---

## 3. Self-Contained Test Dataset

We use an `orders` table containing columns that change frequently:

- `status`: order status.
- `amount`: monetary amount.
- `note`: notes that may be edited repeatedly.
- `customer_id`: lookup key.
- `updated_at`: modification timestamp.

The table lives in a dedicated schema to avoid colliding with application data.

> **Run only in a disposable test database.** `DROP TABLE IF EXISTS` deletes any lab table of the same name. Never run these commands in production.

### 3.1. Creating the Table

```sql
CREATE SCHEMA IF NOT EXISTS dml_impact_lab;

DROP TABLE IF EXISTS dml_impact_lab.orders;

CREATE TABLE dml_impact_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELED')),
    amount NUMERIC(14,2) NOT NULL
        CHECK (amount >= 0),
    note TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
) WITH (fillfactor = 80);
```

`fillfactor = 80` tells PostgreSQL to reserve part of each heap page during inserts so new `UPDATE` tuple versions have room to be placed **on the same page**. This is a trade-off: it can improve HOT update eligibility where appropriate, at the cost of the table initially occupying more pages. Do not treat 80 as a universal optimum for every workload.

### 3.2. Loading an Observable Dataset

```sql
INSERT INTO dml_impact_lab.orders (
    customer_id, status, amount, note,
    updated_at
)
SELECT
    (g.n % 500) + 1,
    CASE
        WHEN g.n % 10 = 0 THEN 'PAID'
        WHEN g.n % 10 = 1 THEN 'CANCELED'
        ELSE 'NEW'
    END,
    (g.n % 100000)::NUMERIC / 100,
    'initial-' || g.n::TEXT,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
FROM generate_series(1, 12000) AS g(n);

ANALYZE dml_impact_lab.orders;
```

The dataset contains 12,000 orders, 500 customer IDs, and three statuses. Resetting and rerunning the lab produces a structurally equivalent dataset.

```sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'NEW') AS new_orders
FROM dml_impact_lab.orders;
```

### 3.3. Creating Two Illustrative Indexes

```sql
CREATE INDEX idx_orders_customer
ON dml_impact_lab.orders (customer_id);

CREATE INDEX idx_orders_paid_customer
ON dml_impact_lab.orders (customer_id)
WHERE status = 'PAID';

ANALYZE dml_impact_lab.orders;
```

The table now has:

1. A unique index backing the `order_id` primary key.
2. A standard B-tree index on `customer_id`.
3. A B-tree **partial index** on `customer_id` covering only rows where `status = 'PAID'`.

Both new indexes serve different read patterns while adding maintenance work on writes. Next we compare updating `note` versus updating `status`.

### 3.4. Representative SELECT Queries

```sql
-- Look up one order by primary key.
SELECT *
FROM dml_impact_lab.orders
WHERE order_id = 500;

-- Order history for a customer.
SELECT order_id, status, amount
FROM dml_impact_lab.orders
WHERE customer_id = 25
ORDER BY order_id DESC;

-- PAID orders for a customer.
SELECT order_id, amount
FROM dml_impact_lab.orders
WHERE customer_id = 25
  AND status = 'PAID';
```

Indexes are usually worth keeping when they accelerate **important real queries** and their read benefits outweigh maintenance and storage costs. Never drop an index solely because it shows up on the write path.

---

## 4. How Does INSERT Affect Heap, Indexes, and WAL?

When inserting a row into a regular logged table, PostgreSQL must:

1. Validate data types, `NOT NULL`, `CHECK`, constraints, and relevant triggers.
2. Locate space in a heap page (or allocate a new page).
3. Write the new heap tuple.
4. Create index tuples in every applicable index. For unique indexes and primary keys, enforce uniqueness.
5. Write sufficient WAL to recover the logged changes.
6. At `COMMIT`, perform flush/wait steps per the configured durability and replication mode.

### 4.1. A Single INSERT Can Touch Multiple Pages

If a row qualifies for the partial index `idx_orders_paid_customer`, the `INSERT` can create index entries in:

- The primary key index.
- `idx_orders_customer`.
- `idx_orders_paid_customer`.

If the row has `status = 'NEW'`, it **is not a member** of the `PAID` partial index, so no entry is added to that index.

Still, the engine must evaluate the index predicate and maintain the remaining structures. Exact cost varies with indexes, cache state, and dataset layout.

### 4.2. Single-Row vs. Multi-Row Writes

Comparing:

```sql
INSERT INTO dml_impact_lab.orders (
    customer_id, status, amount
)
VALUES (901, 'NEW', 10.00);

INSERT INTO dml_impact_lab.orders (
    customer_id, status, amount
)
VALUES (902, 'NEW', 20.00);
```

against:

```sql
INSERT INTO dml_impact_lab.orders (
    customer_id, status, amount
)
VALUES
    (901, 'NEW', 10.00),
    (902, 'NEW', 20.00);
```

both still write the rows and maintain indexes, but the multi-row form can reduce network round-trips, parse/plan overhead, and transaction/commit overhead if the app was sending separate `INSERT`s. Actual gains depend on the driver, prepared statements, and transaction management.

**Note:** These sample `INSERT`s modify the lab table; only run them when testing row additions. To preserve the baseline dataset, wrap them in a transaction and `ROLLBACK`.

### 4.3. COPY Is Often Useful for Large Bulk Loads

For initial bulk data loads, `COPY` is typically much more efficient than issuing individual `INSERT`s:

```sql
-- Illustrative syntax; do not run without a valid COPY stream.
COPY dml_impact_lab.orders (
    customer_id, status, amount, note
)
FROM STDIN WITH (FORMAT csv, HEADER true);
```

`COPY FROM STDIN` requires client support for streaming data over the COPY protocol. Running it alone in a plain SQL editor does not automatically read a CSV file from the application host.

When bulk-loading a brand-new table, you may consider **loading data first and building indexes afterward** if downtime, constraints, safety, and workload permit. However, never drop unique/foreign key constraints or active indexes on a live production table serving traffic just to speed up an import.

### 4.4. Sequences and Gaps Are Not WAL Errors

`GENERATED ALWAYS AS IDENTITY` columns typically rely on sequences. Allocated sequence values are **not guaranteed to be gapless** across transaction rollbacks, sequence caching, or concurrency.

Never infer committed row counts from `MAX(order_id) - MIN(order_id) + 1`. Skipped IDs do not mean WAL corruption or missing rows on a replica.

---

## 5. UPDATE Under MVCC: Why Does One Row Have Multiple Versions?

In PostgreSQL, a normal `UPDATE` does not simply overwrite the old tuple in place. PostgreSQL creates a **new tuple version** so concurrent transactions with different snapshots can observe consistent data under MVCC.

Concept:

```text
Before UPDATE:
Heap page -> [tuple V1: amount=100]

UPDATE amount=120:
Heap page -> [tuple V1: old version]
             [tuple V2: amount=120]

Newer transactions see V2
Older transactions may still need V1
V1 can only be reclaimed once no longer needed for MVCC
```

Exact commit/rollback visibility depends on transaction IDs, snapshots, locks, and internal tuple headers. The diagram illustrates the principle rather than exact on-disk byte layout.

### 5.1. Updating a Single Column Can Still Generate Substantial I/O

```sql
UPDATE dml_impact_lab.orders
SET amount = amount + 1
WHERE order_id = 500;
```

This is not just adding 1 in memory: PostgreSQL must locate the row, acquire locks, create a new tuple version, emit WAL, and decide whether new index tuples are needed.

Cost varies dramatically among:

- Updating a column **not referenced by any index**.
- Updating an **index key column**.
- Updating a column used in a **partial index predicate**.
- Updating a column referenced in an **index expression** or stored via `INCLUDE`.
- Updating a text value so it grows large enough to spill to **TOAST**.
- Updating a table with **triggers** that write into other tables.

### 5.2. Even a No-Op UPDATE That Leaves Values Unchanged Has a Cost

Example:

```sql
UPDATE dml_impact_lab.orders
SET amount = amount
WHERE order_id = 500;
```

Never assume PostgreSQL automatically skips an `UPDATE` just because the new value equals the old value. Along the normal execution path, an `UPDATE` can still create a new tuple version and write WAL.

When the application only intends to write if the value actually changes:

```sql
UPDATE dml_impact_lab.orders
SET amount = 100.00
WHERE order_id = 500
  AND amount IS DISTINCT FROM 100.00;
```

`IS DISTINCT FROM` handles nullable columns cleanly and avoids writing a new version if the column already holds the desired value.

If audit triggers must fire on every update request even when data is unchanged, skipping the `UPDATE` changes business behavior—align on policy first.

---

## 6. HOT Updates: An Opportunity to Reduce Index Overhead

**HOT — Heap-Only Tuple update** — is a PostgreSQL optimization that allows eligible `UPDATE`s to create a new heap version **without inserting new index entries**.

Key eligibility conditions typically include:

1. The `UPDATE` does not modify any columns depended upon by ordinary indexes—including columns in expressions, predicates, or `INCLUDE` lists where applicable. Detailed rules can differ for summarizing indexes such as BRIN depending on PostgreSQL version.
2. The new tuple version fits **on the same heap page** as the previous version.
3. Other internal system conditions permit the HOT optimization.

When ineligible, PostgreSQL performs a non-HOT update. Creating the new version then requires inserting **new index tuples across the table's indexes**, even in indexes whose key values did not change, because those indexes must point to the new tuple location.

### 6.1. Why Does HOT Matter?

Suppose a table has 6 indexes, and an `UPDATE` modifies only a note field:

```sql
UPDATE dml_impact_lab.orders
SET note = 'customer confirmed'
WHERE order_id = 500;
```

When PostgreSQL achieves a HOT update:

- A new heap version and corresponding WAL are still written.
- However, no new entries need to be added to every ordinary index for that version.
- This can significantly reduce write amplification and slow down index bloat.

**HOT does not mean "zero WAL," "zero dead tuples," or "zero cost."** It primarily reduces index-maintenance overhead on eligible `UPDATE`s.

### 6.2. Why Does fillfactor Matter?

A HOT update requires placing the new version **on the same heap page**. If the page is completely full, HOT cannot happen even when no indexed column changed.

Setting `fillfactor = 80` at table creation reserves room on heap pages, improving HOT eligibility for update-heavy workloads.

Trade-offs:

- Lower `fillfactor` can enable more HOT updates.
- However, the table spans more heap pages, increasing read and cache footprint.
- Updates that expand rows to TOAST or pages with unfavorable layout may still miss HOT.
- No single `fillfactor` is optimal for every table.

### 6.3. Example of a Likely HOT Candidate UPDATE

Since `note` in the lab is not part of any index:

```sql
UPDATE dml_impact_lab.orders
SET note = note || '-reviewed'
WHERE order_id BETWEEN 200 AND 300;
```

This is a **HOT candidate**, not a guarantee that all 101 rows will be HOT-updated. Actual eligibility depends on free page space, tuple size, and current table state.

### 6.4. Example of an UPDATE Unlikely to Be HOT

```sql
UPDATE dml_impact_lab.orders
SET customer_id = customer_id + 500
WHERE order_id BETWEEN 200 AND 300;
```

`customer_id` participates in both the standard index and the partial index, so modifying it requires index updates. Do not expect HOT under standard rules.

Another example:

```sql
UPDATE dml_impact_lab.orders
SET status = 'PAID'
WHERE order_id BETWEEN 201 AND 210
  AND status = 'NEW';
```

`status` appears in the partial index predicate `WHERE status='PAID'`. Changing status causes rows to **enter the index**, requiring index maintenance.

### 6.5. Monitoring HOT Updates

```sql
SELECT
    schemaname,
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    n_dead_tup,
    last_autovacuum
FROM pg_stat_user_tables
WHERE schemaname = 'dml_impact_lab'
  AND relname = 'orders';
```

- `n_tup_upd`: cumulative `UPDATE` count recorded in statistics.
- `n_tup_hot_upd`: count of HOT `UPDATE`s recorded.
- `n_dead_tup`: estimated dead tuples.
- `last_autovacuum`: timestamp of the most recent autovacuum, if any.

Conceptual ratio:

```text
HOT ratio = n_tup_hot_upd / n_tup_upd
```

Only compute when the denominator is non-zero, and remember that **statistics are cumulative, slightly delayed, and resettable**. A point-in-time ratio does not cleanly isolate a single recent batch, especially with concurrent writers.

### 6.6. Indexed Columns Are Not Just Leading Index Keys

An index can depend on a column in several ways:

```sql
-- Expression index: modifying amount can impact the index.
CREATE INDEX idx_orders_amount_bucket
ON dml_impact_lab.orders ((ROUND(amount, 0)));

-- INCLUDE index: amount is also stored inside the index.
CREATE INDEX idx_orders_customer_cover
ON dml_impact_lab.orders (customer_id)
INCLUDE (amount);

-- Partial index: status is evaluated in the membership predicate.
CREATE INDEX idx_orders_paid_example
ON dml_impact_lab.orders (amount)
WHERE status = 'PAID';
```

These indexes are **illustrative only**; do not create all of them in the lab unless testing a specific read pattern. They alter HOT eligibility and `UPDATE` cost.

To judge "which columns are HOT-friendly," inspect **every index definition** on the table—including expressions, predicates, and `INCLUDE` columns—not just the leftmost B-tree key columns.

---

## 7. Do More Indexes Always Make Writes More Expensive?

Indexes exist primarily to accelerate queries and enforce constraints. At the same time, every index is an additional physical structure that must be maintained.

### 7.1. Impact by Operation

| Operation | Typical index impact |
| --- | --- |
| `INSERT` | Inserts an entry into each applicable index; checks uniqueness where required |
| `UPDATE` (HOT) | Can avoid inserting new index entries for the new heap version |
| `UPDATE` (non-HOT) | Can create new index entries across indexes, increasing cost and bloat |
| `DELETE` | Marks the old heap tuple dead under MVCC; index entries are not necessarily removed immediately |
| `VACUUM` | Reclaims dead tuples and obsolete index entries |
| `CREATE INDEX` | Scans the table and builds the index, consuming I/O and CPU; generates WAL |
| `REINDEX` | Rebuilds index structures, consuming I/O/CPU with lock/availability trade-offs by mode |

Not all index types carry the same write cost. B-tree, GIN, GiST, SP-GiST, BRIN, and extension indexes each behave differently.

### 7.2. B-tree

B-trees handle equality, range predicates, and ordering well. Writes add entries, modify leaf/internal pages, and occasionally trigger page splits as the tree grows.

If a table carries many overlapping B-tree indexes across different column combinations, `INSERT`s and non-HOT `UPDATE`s touch many more structures. B-trees are not "free" merely because reads are fast.

### 7.3. GIN and Search Indexes

GIN indexes are commonly used for arrays, `jsonb`, or full-text search. Depending on operator class and configuration, a single row can contribute many index keys/entries.

Mechanisms like the pending list (when `fastupdate` is enabled) defer part of the update work until cleanup/merge phases, creating periodic expensive bursts. Read latency, `VACUUM`, and workload behavior are all affected.

Do not equate GIN write cost with B-tree write cost solely by counting index objects.

### 7.4. BRIN

BRIN summarizes value ranges per block range and stays very compact when a column correlates with physical table order. It can fit large, append-heavy time-series tables well.

However:

- BRIN does not replace B-tree for arbitrary selective lookups.
- Filtering effectiveness depends on physical data correlation and `pages_per_range`.
- Summary data still requires maintenance.
- Whether updating a BRIN-indexed column blocks HOT depends on PostgreSQL version; test on your target version before relying on it.

### 7.5. Partial Indexes: Fewer Entries, Still Watch the Predicate

In the lab:

```sql
CREATE INDEX idx_orders_paid_customer
ON dml_impact_lab.orders (customer_id)
WHERE status = 'PAID';
```

This index only stores `PAID` rows, making it smaller than a full-table index when `PAID` is a small fraction.

Yet when running:

```sql
UPDATE dml_impact_lab.orders
SET status = 'PAID'
WHERE status = 'NEW'
  AND order_id BETWEEN 100 AND 200;
```

rows transitioning state must be inserted into the partial index. The predicate also affects HOT eligibility.

**Practical takeaway:** partial indexes shrink index footprint and speed up targeted reads, but they are not free for `UPDATE`s that flip predicate membership.

### 7.6. Unique Indexes and Primary Keys Cannot Be Dropped Lightly

Indexes created for `PRIMARY KEY` or `UNIQUE` constraints also enforce data integrity under concurrency. Removing one for write throughput risks duplicates or breaking foreign key references.

When optimizing, distinguish:

- Indexes backing **mandatory constraints**.
- Indexes serving **critical queries**.
- **Proven** redundant, unused, or duplicate indexes.

Never judge an index solely by `idx_scan`; a unique index scanned rarely may still be essential to protect data integrity.

---

## 8. DELETE Is Not Immediate Physical Removal

Consider:

```sql
DELETE FROM dml_impact_lab.orders
WHERE order_id = 500;
```

Logically, the row disappears from eligible snapshots after `COMMIT`. Physically on disk, PostgreSQL usually retains the old tuple temporarily for MVCC; associated index entries also wait until they can be cleaned safely.

Therefore, a large `DELETE` campaign can:

- Generate substantial WAL.
- Create large volumes of dead tuples.
- Force `VACUUM` to do heavy cleanup work.
- Leave table and index files large even after live row counts drop.
- Put pressure on I/O and replication.
- Hold locks/transactions open too long if executed in one giant transaction.

### 8.1. What Does VACUUM Do?

`VACUUM` processes tuples no longer visible to any MVCC snapshot, makes space reusable inside heap/index pages, and updates internal metadata (visibility map, free space map, etc.).

In the lab:

```sql
VACUUM (ANALYZE) dml_impact_lab.orders;
```

This is a maintenance command for the practice database. In production, rely on tuned autovacuum and an operational plan rather than ad-hoc manual intervention.

**`VACUUM` usually does not immediately return all disk space to the OS.** It primarily makes space reusable inside the relation; reclaiming large physical file sizes typically requires table/index rewrite or repack techniques with their own locks and trade-offs.

### 8.2. Autovacuum and Long-Running Transactions

Autovacuum automatically cleans dead tuples and guards against transaction ID wraparound. However, if a long-running transaction holds onto an old snapshot, PostgreSQL cannot reclaim tuple versions still needed by that snapshot.

This creates a vicious feedback loop:

```text
Heavy UPDATE/DELETE
    -> dead tuples accumulate
    -> long transaction/snapshot
    -> VACUUM cleanup is blocked
    -> table/indexes bloat, increasing read/write I/O
    -> replication/recovery also suffer pressure
```

Never disable autovacuum just to "save CPU" without a complete replacement plan. Future bloat and wraparound risk are far worse than normal autovacuum overhead.

### 8.3. Batched DELETEs

Instead of deleting millions of rows in one transaction, many systems delete in bounded batches to limit lock duration, WAL spikes, and standby lag.

Lab pattern:

```sql
WITH batch AS (
    SELECT order_id
    FROM dml_impact_lab.orders
    WHERE status = 'CANCELED'
    ORDER BY order_id
    LIMIT 200
)
DELETE FROM dml_impact_lab.orders AS o
USING batch AS b
WHERE o.order_id = b.order_id
RETURNING o.order_id;
```

Loop batch by batch **across separate transactions**, tracking deleted counts and stopping when none remain. Never loop inside a single giant transaction and call that "batching" for transaction-size reduction.

Keep in mind:

- Concurrent writers may create new matching rows.
- Individual batches can encounter lock contention.
- `ORDER BY` ordering should be deterministic.
- Deletion campaigns need auditing, backups, and idempotency plans.
- Total WAL does not necessarily decrease just from batching; some per-transaction overhead can rise, though peak load and lock hold times become easier to control.

### 8.4. TRUNCATE Is Not the Same as DELETE

`TRUNCATE` clears an entire table faster than row-by-row `DELETE` without leaving dead tuples in the same way, but it has different semantics:

- Acquires a strong lock, typically `ACCESS EXCLUSIVE`.
- Has consequences for foreign keys and referencing tables.
- Does not fire row-level `DELETE` triggers the way `DELETE` does.
- Is transactional DDL in PostgreSQL and can be rolled back when appropriate.
- Has its own WAL/replication semantics; it is not "zero-WAL" on regular logged tables.

Choose `TRUNCATE` only when the **true requirement is removing all rows** and all stakeholders approve.

---

## 9. What Is WAL and What Roles Does It Serve?

**WAL (Write-Ahead Log)** is the change log that enables PostgreSQL to recover data after crashes and supplies the change stream for backups and replication.

Model:

```text
Transaction writes heap/index changes
           |
           v
WAL records generated
           |
           v
WAL buffers / WAL files
           |
           +----> fsync/flush per durability configuration
           |
           +----> Crash recovery / redo
           |
           +----> WAL archive + base backup -> PITR
           |
           +----> WAL sender -> Physical standby
           |
           +----> Logical decoding -> Subscriber
```

Common misconception: WAL **does not contain only application-level INSERT/UPDATE/DELETE statements**. It records everything needed for recovery: index page updates, maintenance/metadata operations, full-page images, and commit records.

### 9.1. WAL Before Data Pages Hit Disk Permanently

PostgreSQL can acknowledge `COMMIT` to the client as soon as WAL is flushed per the configured synchronization mode, while modified heap/index pages in shared buffers may not yet be written to data files.

After a crash, recovery replays WAL to bring data files into a consistent state.

This explains why **WAL flush latency** directly affects `COMMIT` latency even when table write throughput looks modest.

### 9.2. WAL Alone Is Not a Complete Backup

WAL archives enable Point-in-Time Recovery (PITR), yet recovery still requires a **valid base backup** plus the continuous WAL sequence.

Never assume "we have WAL on disk so we don't need backups." Likewise, never treat a replica alone as a backup strategy: accidental deletes or logical bugs replicate straight to standbys.

### 9.3. WAL and Transaction Rollbacks

A transaction that performs writes and then executes `ROLLBACK` has still generated WAL for the attempted modifications. Logical rollback does not erase already-written WAL bytes.

Therefore, running:

```sql
BEGIN;

UPDATE dml_impact_lab.orders
SET note = note || '-temporary'
WHERE order_id BETWEEN 1 AND 1000;

ROLLBACK;
```

reverts the logical table state in the lab, **not the WAL or I/O generated during execution**. Keep this in mind when measuring with `EXPLAIN (ANALYZE, BUFFERS, WAL)`.

---

## 10. Why Can a Small UPDATE Generate So Much WAL?

WAL volume is shaped by many factors:

| Factor | Mechanism |
| --- | --- |
| Rows modified | More tuple versions and WAL records |
| Tuple width | Wider rows can require more logged data |
| Index count and types | Index updates also generate WAL |
| HOT vs. non-HOT | Non-HOT updates typically emit extra index WAL |
| Full-page images | Whole pages logged after checkpoints for crash safety |
| Page splits | Can trigger additional WAL and page writes |
| TOAST | Large values generate TOAST data and TOAST index WAL |
| Triggers / FKs / cascades | One logical write triggers downstream writes |
| Transaction batching | Commit overhead and WAL patterns shift |
| `wal_level` and replication | `logical` level logs additional decoding metadata |
| Checkpoints/config | Shapes FPI frequency and write pressure |
| Unlogged/temporary tables | Different WAL and durability semantics than logged tables |

There is no simple formula like "WAL bytes = new row size," because PostgreSQL must log page-level and recovery metadata.

### 10.1. Full-Page Images (FPI)

When `full_page_writes` is enabled—the standard safe setting—the first modification to a given data page after a checkpoint can cause PostgreSQL to write a **full-page image** into WAL to guard against torn pages.

This can make WAL grow in bursts:

```text
Checkpoint
    |
    +--> first edit on page A -> may include FPI
    +--> next edit on page A  -> no FPI by default
    +--> first edit on page B -> may include FPI
```

Do not assume an FPI happens once per table; the unit is the **page**, and exact behavior has specific rules and exceptions.

### 10.2. Overly Frequent Checkpoints

Frequent checkpoints force pages back into the "first modification after checkpoint" state more often, increasing FPI volume on eligible workloads and concentrating write pressure.

Key settings include:

- `checkpoint_timeout`.
- `max_wal_size` (a soft target influencing checkpoint scheduling, **not an absolute hard cap on `pg_wal` directory size**).
- `checkpoint_completion_target` on supported versions.
- Write rate and buffer pool sizing.

Tuning checkpoint parameters must be guided by I/O metrics, recovery-time objectives (RTO), WAL archiving, and hardware capacity—never copy a magic number blindly.

### 10.3. wal_compression

`wal_compression` can shrink WAL size from **full-page images** in many workloads by compressing page images, trading extra CPU time for compression/decompression.

Do not assume `wal_compression=on` compresses every WAL record at a constant ratio. Actual savings depend on FPI proportion, page contents, data types, CPU headroom, and the compression algorithm supported by your PostgreSQL version.

### 10.4. Should You Disable full_page_writes or fsync?

**Never disable `full_page_writes` or `fsync` as a routine production optimization.** Those settings are fundamental to data integrity and crash/power-loss recovery.

Benchmarking faster by sacrificing durability produces misleading numbers that do not meet production safety requirements. When comparing configurations, keep **identical durability guarantees** or state explicitly that two different durability contracts are being compared.

---

## 11. COMMIT, synchronous_commit, and Acknowledgment Latency

A practical question: when PostgreSQL returns `COMMIT` success, what is actually guaranteed?

It depends on `synchronous_commit`, synchronous standby configuration, and how the storage layer handles flushes.

### 11.1. Synchronization Modes

Common modes:

| Mode | Intuition | Trade-off |
| --- | --- | --- |
| `on` | Waits for local WAL flush and, if configured, acknowledgment from synchronous standby | Stronger durability per config; higher latency |
| `local` | Waits for local WAL flush, does not wait for standbys | Skips remote sync wait |
| `remote_write` | With a synchronous standby, waits until standby writes WAL to OS cache (not necessarily flushed to disk) | Lower latency than flush, weaker remote guarantee |
| `remote_apply` | With a synchronous standby, waits until WAL is replayed and visible to standby queries per policy | Highest latency |
| `off` | Does not wait for local WAL flush before confirming commit | Recent confirmed transactions may be lost on crash; unsuitable for many workloads |

Standby-related modes only wait remotely when **synchronous replication is actively configured**, such as via `synchronous_standby_names`.

### 11.2. Does synchronous_commit=off Break ACID?

PostgreSQL still maintains WAL consistency for crash recovery, so the database remains consistent on restart, yet asynchronous commits can lose a small window of recently acknowledged transactions if a crash occurs before WAL is flushed. That is an intentional durability trade-off.

Never switch to `off` to mask latency in financial, order, or critical-record systems without explicit approval and tolerance for potential commit loss.

### 11.3. Remote Apply Differs from Remote Flush

A standby having **received** WAL does not mean it has **flushed** it; having flushed WAL does not mean it has finished **replaying** it; and finishing replay does not mean an already-open query snapshot on the standby immediately sees the changes.

Thus, "primary committed" and "the app can immediately read the new value from a replica" are not always equivalent statements.

---

## 12. Physical Streaming Replication: Copying Physical WAL

Physical replication ships and replays WAL so standbys stay exact replicas at the **cluster physical storage level**.

Conceptual flow:

```text
Primary
  WAL sender
      |
      v
Network -> WAL receiver on standby
                    |
                    v
             WAL written/flushed
                    |
                    v
             Recovery / WAL replay
                    |
                    v
             Heap, indexes, catalog updated
```

Consequently, physical changes to indexes, heap pages, tables, and schemas on the primary are reflected via WAL replay on physical standbys within PostgreSQL's logging rules.

### 12.1. New Indexes Make Replicas Work Too

If you run on the primary:

```sql
CREATE INDEX idx_orders_amount
ON dml_impact_lab.orders(amount);
```

building the index consumes CPU/I/O on the primary and produces WAL that physical standbys must replay. A physical standby does not "receive a SQL string and build the index independently"; it replays the physical WAL changes.

Therefore, large index builds or rebuilds can trigger a **WAL burst** and replication lag even when application `INSERT`/`UPDATE` rates are steady.

### 12.2. Replica Lag Has Multiple Stages

Distinct checkpoints along the pipeline:

- **Sent LSN**: how far the primary has transmitted WAL.
- **Write LSN**: how far the standby has written WAL to OS cache.
- **Flush LSN**: how far the standby has flushed WAL to disk.
- **Replay LSN**: how far the standby has applied WAL into data pages.

Depending on the workload, the bottleneck may be:

- Network bandwidth/latency.
- Standby disk WAL flush throughput.
- Standby CPU/I/O during replay.
- Replay conflicts with long-running read queries on the standby.
- WAL spikes from bulk DML, index builds, `REINDEX`, or backfills.

Never glance at a single "lag seconds" chart and immediately blame the network.

### 12.3. Physical Replication and UNLOGGED Tables

`UNLOGGED` tables have different logging and durability semantics from regular tables and **do not replicate row contents over physical streaming replication like normal logged tables**. Unlogged tables are truncated after an unclean crash to maintain consistency.

Use `UNLOGGED` only for **recreatable or expendable data** such as staging tables—never for accounts, payments, or authoritative data requiring durability and replication.

---

## 13. Logical Replication: Replicating Data-Level Changes

Logical replication uses WAL and logical decoding to stream table changes via publications and subscriptions.

Concept:

```text
Publisher PostgreSQL
   |
   +--> WAL with logical decoding metadata
   |
   +--> Logical decoding / replication slot
                |
                v
         Decoded INSERT/UPDATE/DELETE changes ...
                |
                v
           Subscriber / Apply worker
                |
                v
         Rows applied to target tables
```

Logical replication differs from physical replication in scope and semantics:

| Aspect | Physical | Logical |
| --- | --- | --- |
| Replication level | Physical WAL / cluster storage | Logical row changes per publication |
| Scope | Whole WAL-logged cluster | Selectable tables and DML operations |
| Source indexes | Physical index changes are replayed | Subscriber indexes/schemas managed independently |
| DDL | Logged schema changes replay physically | Built-in logical replication **does not replicate DDL automatically** |
| Sequences | Physical state logged/replayed via WAL | Sequence progression is not replicated as normal row changes |
| Typical uses | Standby, HA, read replicas, PITR | Selective data sharing, major upgrades/migrations, integration |
| Write cost | WAL generation, network, replay | Additional WAL detail, decode, send, apply, subscriber indexes |

### 13.1. wal_level and Logical Decoding Requirements

Logical replication requires an appropriate WAL level, typically `wal_level = logical`. This logs extra information to support decoding and can increase resource usage.

Do not change `wal_level` impulsively in production; changing it may require a restart and must be coordinated with backup and replication plans.

### 13.2. Publications Do Not Auto-Create Subscriber Schemas

**Illustrative** syntax (no need to run in the lab):

```sql
CREATE PUBLICATION orders_publication
FOR TABLE dml_impact_lab.orders
WITH (publish = 'insert,update,delete');
```

Running a real subscriber also requires network connectivity, privileges, publication/subscription setup, matching target table schemas, and initial synchronization planning. A lone `CREATE PUBLICATION` command does not stand up an entire pipeline.

With built-in logical replication, DDL changes like adding columns or indexes are not automatically propagated like DML rows. Coordinate DDL across publisher and subscriber carefully to avoid apply failures.

### 13.3. REPLICA IDENTITY for UPDATE and DELETE

To apply `UPDATE` or `DELETE` on a subscriber, logical replication must identify **which target row** to modify or remove.

By default, PostgreSQL uses the primary key as replica identity when present. Without a suitable key, publishing `UPDATE`/`DELETE` is restricted or requires an explicit replica identity setting.

One option:

```sql
-- Illustrative only; DO NOT run blindly on production tables.
ALTER TABLE dml_impact_lab.orders
REPLICA IDENTITY FULL;
```

`REPLICA IDENTITY FULL` logs entire old row values to identify rows, which can increase WAL volume and subscriber apply/lookup cost. It is not a better default than a primary key.

Because our lab table has `PRIMARY KEY` `order_id`, you **do not need `REPLICA IDENTITY FULL`** under normal circumstances.

### 13.4. Logical Subscribers Have Their Own Write Costs

If a subscriber defines 5 indexes while the publisher has only 2, every replicated change applied on the subscriber must maintain **all 5 subscriber indexes** according to the subscriber's schema.

The bottleneck is not always the network: apply workers, lock contention, constraints, indexes, huge transactions, and subscriber host capacity can all limit replication speed.

### 13.5. Logical Replication Does Not Automatically Resolve Arbitrary Conflicts

Built-in logical replication is not a general multi-master system where both sides write freely and business conflicts vanish automatically. Out-of-order overwrites, incompatible schemas, or missing identity keys can stall or error out apply workers.

Plan data ownership, DDL rollouts, slot recovery, conflict handling, and apply-worker monitoring explicitly.

---

## 14. Replication Slots and the Risk of Filling pg_wal

Replication slots retain information/WAL needed so consumers can resume reading WAL from their last position, depending on slot type and configuration.

Scenario:

```text
Primary generates 20 GB of WAL
    |
    +--> standby/logical consumer stops or falls far behind
                |
                v
           Slot pins an old LSN
                |
                v
        Old WAL segments cannot be recycled
                |
                v
             pg_wal grows
                |
                v
           Risk of disk exhaustion
```

**Replication slots do not automatically cap WAL usage.** If a consumer stalls, a slot can hold WAL until disk fills; retention caps like `max_slot_wal_keep_size` trade off disk safety against invalidating lagging slots.

### 14.1. Inspecting Replication Slots

On a server where you hold appropriate monitoring privileges:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

Columns:

- `slot_name`: slot identifier.
- `slot_type`: `physical` or `logical`.
- `active`: whether a consumer is currently connected to the slot.
- `restart_lsn`: earliest WAL position still potentially required by the slot.
- `confirmed_flush_lsn`: confirmed flush checkpoint for a logical slot.

Never assume an `inactive` slot is harmless. A long-inactive slot is often the root cause of growing `pg_wal`.

### 14.2. Never Drop a Slot Solely to Free Disk Space

Dropping an active replication consumer's slot can break its ability to resume cleanly, forcing a full resync or rebuild. That carries major recovery and availability consequences.

When you suspect a slot is pinning WAL:

1. Identify which system or consumer owns the slot.
2. Check whether the consumer is running and lagging.
3. Evaluate consumer recovery options.
4. Check disk headroom, retention settings, and WAL archiver health.
5. Execute an approved plan rather than dropping slots impulsively.

### 14.3. WAL Archiving Can Also Cause Accumulation

When archiving is enabled, WAL segments must be retained until archived successfully. If `archive_command` or archive storage stalls or fails, unarchived WAL piles up in `pg_wal`.

Systems using both replicas and PITR must monitor **slots, standbys, and the archiver** together—not just `pg_stat_replication`.

---

## 15. Measuring Write Cost with EXPLAIN (ANALYZE, BUFFERS, WAL)

This is the most direct tool for observing **an individual statement** in the lab.

> **Warning:** `EXPLAIN ANALYZE` **actually executes the SQL statement**. For `INSERT`, `UPDATE`, and `DELETE`, it truly writes data. Run it only in a test database, and wrap with `BEGIN ... ROLLBACK` to undo logical changes. Remember that rollback **does not undo generated WAL or I/O**.

### 15.1. Observing an Unindexed-Column UPDATE

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE dml_impact_lab.orders
SET note = note || '-a'
WHERE order_id BETWEEN 200 AND 500;

ROLLBACK;
```

Look for output lines such as:

```text
Update on orders ...
  Buffers: shared hit=..., dirtied=..., written=...
  WAL: records=..., fpi=..., bytes=...
  -> Index Scan ...
Planning Time: ...
Execution Time: ...
```

This is an **output format illustration**, not measured numbers from your environment.

Meaning:

- `Buffers shared hit/read/dirtied/written`: buffer cache activity recorded for the statement.
- `WAL records`: count of WAL records attributed to the statement.
- `WAL fpi`: count of full-page images generated.
- `WAL bytes`: total WAL bytes attributed to the statement.
- `Execution Time`: measured statement execution duration.

Plans and metrics vary across versions, privileges, node types, and settings. Do not treat illustrative examples as fixed KPI targets.

### 15.2. Comparing Against an Indexed-Column UPDATE

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE dml_impact_lab.orders
SET customer_id = customer_id + 1000
WHERE order_id BETWEEN 200 AND 500;

ROLLBACK;
```

This statement modifies `customer_id`, which belongs to the B-tree indexes. Under comparable conditions, index work and WAL are often higher than updating an unindexed column.

Still, **never compare a single run and jump to conclusions**: checkpoint timing, warm vs. cold caches, FPIs, tuple width, page fullness, and concurrent activity all affect the numbers.

### 15.3. Comparing a Status Change That Alters Partial-Index Membership

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE dml_impact_lab.orders
SET status = 'PAID'
WHERE order_id BETWEEN 201 AND 500
  AND status = 'NEW';

ROLLBACK;
```

For rows transitioning from `NEW` to `PAID`, the `PAID` partial index needs new entries. The write profile differs from updating `note`, even when identical row counts are updated.

### 15.4. Conditions for a Fairer Benchmark

For a rigorous cost comparison:

- Use datasets of comparable scale and distribution.
- Verify the **actual** number of updated rows, not just expected `WHERE` matches.
- Keep durability and replication settings identical.
- Control or record checkpoint/FPI state and cache warmth.
- Run multiple iterations in an isolated test environment free of competing writers.
- Compare latency, WAL bytes, buffers, CPU, and index growth together.
- Account for the fact that rolled-back trials still generate WAL.
- Never extrapolate a 12,000-row lab table linearly to a 100-million-row production table.

This describes experimental methodology, not a mandatory benchmark step during reading.

---

## 16. Monitoring Table Statistics: UPDATEs, HOT, and Dead Tuples

PostgreSQL exposes cumulative per-table stats in `pg_stat_user_tables`.

```sql
SELECT
    schemaname,
    relname,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname = 'dml_impact_lab'
  AND relname = 'orders';
```

Basic column meanings:

| Column | Meaning |
| --- | --- |
| `n_tup_ins` | Cumulative inserted tuple count |
| `n_tup_upd` | Cumulative updated tuple count |
| `n_tup_del` | Cumulative deleted tuple count |
| `n_tup_hot_upd` | Cumulative HOT `UPDATE` count |
| `n_live_tup` | Estimated live tuples |
| `n_dead_tup` | Estimated dead tuples |
| `last_autovacuum` | Timestamp of most recent autovacuum, if recorded |
| `vacuum_count` | Cumulative manual `VACUUM` runs |

**Never read these counters or estimates as transactionally exact numbers.** Statistics update asynchronously, accumulate over time, can be reset, and reflect concurrent writers.

### 16.1. Calculating the HOT Ratio

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    ROUND(
        100::NUMERIC * n_tup_hot_upd
          / NULLIF(n_tup_upd, 0),
        2
    ) AS hot_update_percent
FROM pg_stat_user_tables
WHERE schemaname = 'dml_impact_lab'
  AND relname = 'orders';
```

When `n_tup_upd = 0`, `NULLIF` safely returns `NULL` instead of dividing by zero.

A low HOT ratio is a signal **worth investigating**, not automatic proof of a bug. The workload may legitimately update indexed columns frequently, or row sizes, `fillfactor`, index definitions, and page layout may constrain HOT placement.

### 16.2. Statistics Can Lag Behind Short Batches

When checking stats immediately after a short test batch, cached session stats snapshots may not yet reflect the newest counts. You can run:

```sql
SELECT pg_stat_clear_snapshot();
```

to discard your session's cached statistics snapshot, though this **does not turn cumulative counters into exact per-statement telemetry**.

Never run global statistics reset functions (`pg_stat_reset`) on monitored shared servers—it wipes baseline history for other operators.

---

## 17. Measuring Heap, Table, and Index Sizes

PostgreSQL offers relation sizing functions:

```sql
SELECT
    pg_size_pretty(
        pg_relation_size('dml_impact_lab.orders'::REGCLASS)
    ) AS heap_main_size,

    pg_size_pretty(
        pg_table_size('dml_impact_lab.orders'::REGCLASS)
    ) AS table_storage_size,

    pg_size_pretty(
        pg_indexes_size('dml_impact_lab.orders'::REGCLASS)
    ) AS all_indexes_size,

    pg_size_pretty(
        pg_total_relation_size('dml_impact_lab.orders'::REGCLASS)
    ) AS total_relation_size;
```

Distinctions:

- `pg_relation_size` measures the relation's **main fork** by default.
- `pg_table_size` includes table storage plus auxiliary structures such as TOAST, FSM, and VM.
- `pg_indexes_size` sums all indexes attached to the table.
- `pg_total_relation_size` combines table and index sizes.

These numbers reflect **current allocated disk size**, not how much space contains live tuples versus bloat needing `VACUUM`.

### 17.1. Inspecting Individual Indexes

```sql
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'dml_impact_lab'
  AND tablename = 'orders'
ORDER BY indexname;
```

Querying per-index sizes from catalogs:

```sql
SELECT
    i.relname AS index_name,
    pg_size_pretty(pg_relation_size(i.oid)) AS index_size
FROM pg_class AS t
JOIN pg_namespace AS n
  ON n.oid = t.relnamespace
JOIN pg_index AS ix
  ON ix.indrelid = t.oid
JOIN pg_class AS i
  ON i.oid = ix.indexrelid
WHERE n.nspname = 'dml_impact_lab'
  AND t.relname = 'orders'
ORDER BY pg_relation_size(i.oid) DESC;
```

Track index sizes **over time** relative to live rows and write volume. Index growth after new `INSERT`s is normal; monotonic growth during steady `UPDATE`/`DELETE` churn without space reuse can signal index bloat.

### 17.2. Index Usage Stats Are Not Index Write Stats

```sql
SELECT
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'dml_impact_lab'
  AND relname = 'orders'
ORDER BY indexrelname;
```

These columns track **read scans using the index**. They do not count "how many index tuples were written by `UPDATE`s."

Never assume an index has zero write overhead just because `idx_scan` is zero—and never drop a `UNIQUE` index solely because `idx_scan` is low.

---

## 18. Measuring Cluster-Wide WAL with pg_stat_wal

PostgreSQL exposes server-wide WAL statistics via `pg_stat_wal` on supported versions.

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    stats_reset
FROM pg_stat_wal;
```

| Field | Meaning |
| --- | --- |
| `wal_records` | Cumulative count of WAL records |
| `wal_fpi` | Cumulative count of full-page images |
| `wal_bytes` | Cumulative WAL bytes written |
| `stats_reset` | Timestamp of last stats reset |

**Important:** `pg_stat_wal` is **cluster-wide**, not isolated to the lab table or your current transaction.

On a busy server, the delta in `wal_bytes` between two timestamps includes activity from all concurrent sessions.

### 18.1. Measuring by LSN

PostgreSQL uses `pg_lsn` log sequence numbers. Useful functions:

```sql
SELECT
    pg_current_wal_insert_lsn() AS current_insert_lsn,
    pg_current_wal_lsn() AS current_write_lsn,
    pg_current_wal_flush_lsn() AS current_flush_lsn;
```

Definitions:

- **Insert LSN**: WAL position inserted into WAL buffers.
- **Write LSN**: WAL position written to WAL files.
- **Flush LSN**: WAL position flushed to disk.

Compute distance between two recorded LSNs:

```sql
-- Syntax illustration only; these LSN literals are not live measurements.
SELECT pg_wal_lsn_diff(
    '0/16B7C90'::PG_LSN,
    '0/16B6C10'::PG_LSN
) AS wal_distance_bytes;
```

When measuring in practice, capture **both LSN samples from the same server at the target boundaries**; since WAL is shared cluster-wide, the LSN delta also includes concurrent activity and does not isolate a single DML statement automatically.

### 18.2. Choosing the Right Measurement Tool

| Goal | Appropriate tool |
| --- | --- |
| One DML statement in a lab | `EXPLAIN (ANALYZE, BUFFERS, WAL)` |
| Server-wide WAL rate over time | `pg_stat_wal`, LSNs, time-series monitoring |
| Per-table `INSERT`/`UPDATE`/`DELETE` and HOT counts | `pg_stat_user_tables` |
| Table and index storage size | `pg_table_size`, `pg_indexes_size` |
| WAL pinned by replication slots | `pg_replication_slots` |
| Standby send/write/flush/replay progress | `pg_stat_replication` and standby WAL functions |
| WAL archiving progress | `pg_stat_archiver` |

Never rely on a single metric to diagnose every kind of write slowdown.

---

## 19. Observing Replication Lag on the Primary

On a **primary with streaming replication** and sufficient privileges:

```sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS primary_to_replay_bytes
FROM pg_stat_replication
ORDER BY application_name;
```

This view returns zero rows if no standbys are connected or visible at query time.

**Interpret carefully:** `primary_to_replay_bytes` is the WAL byte distance between the primary's current WAL position and the standby's latest reported replay position. It is neither pure "bytes currently in flight on the wire" nor a time delay in seconds.

Columns can also be `NULL` or lag behind if the standby has not sent a recent status update.

### 19.1. Pinpointing Bottlenecks Using LSN Checkpoints

Directional diagnostic view:

```text
Primary current WAL LSN
        |
        v
      sent_lsn
        |
        v
      write_lsn
        |
        v
      flush_lsn
        |
        v
      replay_lsn
```

If the **sent → write** gap is large, inspect network throughput, standby receive, or WAL write paths.

If the **flush → replay** gap is large, inspect standby CPU/I/O during replay or recovery conflicts with long standby read queries.

Treat this as an **investigation guide**, not proof on its own; status messages arrive asynchronously, so correlate with logs, CPU, disk metrics, and wall-clock timestamps.

### 19.2. On the Standby: Checking Receive and Replay

On a **standby**:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn,
    pg_last_xact_replay_timestamp()
        AS last_replayed_commit_time;
```

`pg_last_xact_replay_timestamp()` reports the timestamp of the last replayed commit/abort transaction record; on an **idle system with no new commits**, elapsed time since that timestamp grows even when the standby is completely caught up.

Never conclude replication is lagging solely from `now() - pg_last_xact_replay_timestamp()`. Cross-check LSNs, primary commit activity, connection status, and workload.

### 19.3. Read-After-Write on Replicas

An application writing to the primary and immediately reading from an asynchronous standby may observe **stale data**.

Design options depending on consistency needs:

- Route immediate post-write reads to the primary.
- Wait until the standby reaches at least the write's target LSN where supported.
- Use synchronous replication at an appropriate mode (`remote_apply`) when latency and budget permit.
- Embrace eventual consistency with explicit UX/status design where immediate read-your-writes is unnecessary.

Never assume "COMMIT succeeded on primary" means every replica reflects the change immediately.

---

## 20. WAL Archiving and Backup Health

If you archive WAL for PITR, monitor `pg_stat_archiver`:

```sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
```

During a major backfill or `UPDATE` wave:

- WAL generation rate rises.
- The archiver may fall behind if backup storage throughput is slow.
- Unarchived WAL segments accumulate in `pg_wal`.
- Replication slots may simultaneously retain WAL.
- Recovery-time objective (RTO) and restore duration can worsen.

**Major risk:** treating `max_wal_size` as a hard ceiling on `pg_wal`. Whenever slots, stalled archiving, or other conditions retain WAL, actual disk usage can exceed `max_wal_size`.

Monitor **filesystem free space** and out-of-space alerts directly, not just PostgreSQL config parameters.

---

## 21. Backfilling Millions of Rows: Often-Overlooked Cost Sources

A classic task:

> Populate a new column across 10 million historical orders.

Hypothetical statement:

```sql
UPDATE orders
SET category = 'STANDARD'
WHERE category IS NULL;
```

Running this in a single huge transaction can cause:

- Millions of new tuple versions.
- Heavy WAL across heap and all affected indexes.
- Massive dead-tuple accumulation requiring `VACUUM`.
- Long-held locks and transaction/snapshot duration.
- Spikes in WAL archiving and replication volume.
- Lag on physical standbys and logical subscribers.
- Autovacuum being hindered by the long-running transaction.
- Disk I/O bursts well above normal load.

### 21.1. Pre-Execution Assessment

Check beforehand:

1. How many rows actually need modification?
2. Is the updated column part of an index, expression, `INCLUDE`, or partial-index predicate?
3. Are triggers, generated columns, foreign keys, or cascades involved?
4. Can new tuples be HOT? Do heap pages have free space?
5. How much headroom do WAL, replicas, and the archiver currently have?
6. What write and read latency budgets are acceptable?
7. Can updates be batched cleanly over a deterministic key?
8. Does the backfill coincide with schema or application code deployments?
9. Can the job pause, resume, and rerun safely?
10. Are `VACUUM`, `ANALYZE`, and index-bloat checks planned afterward?

### 21.2. Update Only Rows That Need Changing

Instead of rewriting every row:

```sql
UPDATE orders
SET category = 'STANDARD';
```

add an exact guard:

```sql
UPDATE orders
SET category = 'STANDARD'
WHERE category IS DISTINCT FROM 'STANDARD';
```

This illustrates a **hypothetical** `orders` table with a `category` column (outside the lab schema). It avoids rewriting rows that already have the target value, provided skipping no-op updates is compatible with your audit/trigger requirements.

### 21.3. Key-Ordered Batching

Pattern using an ordered key slice:

```sql
-- Illustrative pattern on a hypothetical table.
WITH batch AS (
    SELECT order_id
    FROM orders
    WHERE category IS DISTINCT FROM 'STANDARD'
    ORDER BY order_id
    LIMIT 1000
)
UPDATE orders AS o
SET category = 'STANDARD'
FROM batch AS b
WHERE o.order_id = b.order_id;
```

Run each batch in its own **separate transaction**, throttle the rate, and monitor replica lag. If multiple workers run concurrently, coordinate key ranges or locks to avoid contention.

**Batching does not magically reduce total WAL or total update work.** It primarily controls **peak load, transaction length, lock hold times, and pause/resume capability**.

### 21.4. Watch Schema Migrations Carefully

When adding a new column, adding certain defaults/constraints behaves very differently depending on PostgreSQL version. Do not assume every `ALTER TABLE ADD COLUMN ... DEFAULT ...` rewrites the whole table, nor assume every `ALTER` is free.

If a default is only needed for **new rows**, you may not need to backfill all historical rows immediately. If `NOT NULL` is required, plan validation and constraint enforcement steps supported by your version.

Evaluate DDL schema changes and data backfills as **two distinct phases** that interact heavily around WAL, locks, and replication.

---

## 22. Initial Bulk Loads and Index Creation Order

When building a brand-new table with hundreds of millions of rows and loading initial data, a common question arises:

> Should indexes be created before or after the import?

Two main approaches:

### Approach A — Indexes Exist Before Load

```text
Create table + indexes
      |
      v
Bulk COPY / INSERT
      |
      v
Every row updates heap and indexes as it arrives
```

Pros: indexes and constraints are active throughout the load. Cons: maintaining indexes per batch can add random I/O and WAL overhead.

### Approach B — Load Into New Table, Then Build Indexes

```text
Create empty table (essential constraints)
      |
      v
Bulk COPY / INSERT into new table
      |
      v
CREATE INDEX / VALIDATE
      |
      v
ANALYZE -> Cutover
```

Building indexes post-load can be faster for some workloads thanks to bulk index-build algorithms. Yet it brings its own concerns:

- CPU, I/O, temp-space, and WAL spikes during index creation.
- Ensuring uniqueness and foreign keys safely.
- Locks and read/write availability while building indexes.
- Replicas replaying large index-build WAL bursts.
- Cutover and rollback planning.

Never apply Approach B blindly to a live production table with active readers and writers. On live tables, `CREATE INDEX CONCURRENTLY` may be required; it has distinct locking/transaction rules and cannot execute inside an ordinary transaction block.

### 22.1. COPY Does Not Always Mean "Zero WAL"

On normal logged tables, `COPY` generates appropriate WAL. Specific load setups and PostgreSQL versions optimize WAL in well-defined cases, so never claim `COPY` skips WAL everywhere or provides identical durability across all modes.

---

## 23. UNLOGGED and TEMP: Intentional Durability Trade-Offs

PostgreSQL supports:

```sql
CREATE UNLOGGED TABLE dml_impact_lab.staging_events (
    source_id BIGINT,
    payload TEXT
);
```

Row modifications in unlogged tables bypass normal WAL logging. That cuts WAL overhead for regenerable staging data, with critical trade-offs:

- Data is not crash-safe; unlogged tables are truncated on crash recovery.
- Row data is not shipped to physical standbys like regular logged tables.
- Unsuitable for authoritative business data needing durability or replication.
- Catalog/DDL operations still emit WAL; never equate `UNLOGGED` with "zero WAL whatsoever."

For single-session scratch data:

```sql
CREATE TEMP TABLE session_stage (
    source_id BIGINT,
    payload TEXT
) ON COMMIT DROP;
```

Temporary tables have session/transaction scope distinct from durable tables. `ON COMMIT DROP` drops the table when the creating transaction commits—do not use it if you expect the table to survive across multiple transactions.

**Choose `UNLOGGED` or `TEMP` only when data is expendable and rebuildable**, never solely to chase speed.

---

## 24. Triggers, Foreign Keys, and Cascades Are Part of Write Cost

An `UPDATE`'s total work is not limited to the target table's heap and indexes.

Additional multipliers include:

- `BEFORE`/`AFTER` `INSERT`/`UPDATE`/`DELETE` triggers.
- Audit triggers writing to history tables.
- Foreign key checks looking up parent/child tables.
- `ON UPDATE CASCADE` / `ON DELETE CASCADE` touching many child rows.
- Generated columns and expression indexes.
- Logical decoding and subscriber apply overhead.
- Constraint checks, unique conflicts, and lock waits.
- Application retries triggered by deadlocks or serialization failures.

### 24.1. One Logical DELETE Can Trigger Millions of Physical DELETEs

Suppose `customers` connects to `orders` via `ON DELETE CASCADE`. Deleting one customer with millions of orders causes heavy heap/index writes and WAL on `orders`, not just one row in `customers`.

Before deleting or updating referenced keys:

1. Inspect foreign keys and cascade rules.
2. Estimate indirect row impact.
3. Monitor locks, transaction time, and replica lag.
4. Verify backup, retention, audit, and recovery plans.

Never gauge cost solely from `DELETE FROM customers WHERE id=...` when child tables are huge.

### 24.2. Audits and CDC Carry Real Business Value

When compliance or traceability demands full change history, extra WAL and audit storage are **necessary costs**. Never remove auditing or CDC mechanisms without knowing which business workflows depend on them.

---

## 25. Large Transactions, Locks, and Retries

A single huge transaction incurs fewer `COMMIT`s than many tiny ones, yet introduces other hazards:

| Oversized transaction | Undersized transaction |
| --- | --- |
| Holds locks and snapshots too long | Many network round-trips and commits |
| Produces large WAL bursts | Higher per-commit flush overhead |
| Rolling back discards huge amounts of work | More resume checkpoints and idempotency work |
| Can block `VACUUM` progress | May lower raw bulk throughput |
| Forces standbys/logical apply to process giant bursts | WAL/traffic spreads out more smoothly |

There is no universal optimal batch size. Tune against system resources and targets:

- Target throughput.
- Application latency budget.
- WAL generation rate.
- Replication lag tolerances.
- Rollback/retry impact.
- Lock footprint.
- RPO/RTO and maintenance windows.

### 25.1. Viewing COMMIT and End-to-End Latency

An `UPDATE` finishing in milliseconds inside `EXPLAIN ANALYZE` may not reflect total client latency once `COMMIT` waits for local WAL flush or synchronous standbys.

When benchmarking writes, measure:

- Individual statement execution time.
- `COMMIT` time.
- Transactions/sec and rows/sec.
- WAL bytes/sec.
- Primary-to-standby lag.
- Lock waits, CPU, and disk I/O.

### 25.2. Retries Can Multiply Write Work

If transactions hit deadlocks (`40P01`) or serialization failures (`40001`) and the application retries whole transactions, one logical request generates multiple database attempts.

Handle `40P01` and `40001` with bounded retries, exponential backoff, jitter, and end-to-end idempotency where external side effects exist.

Do not assume PostgreSQL grew unstable when WAL spikes coincide with heavy retry storms.

---

## 26. WAL and Logical Replication When Updating Identity Keys

Modifying primary keys has broader impact than updating ordinary columns:

```sql
-- ILLUSTRATIVE ONLY; do not run unless intending to mutate identities.
UPDATE dml_impact_lab.orders
SET order_id = order_id + 1000000
WHERE order_id BETWEEN 1 AND 10;
```

Consequences include:

- Touching the primary key B-tree.
- Re-checking uniqueness.
- Checking or cascading foreign keys in referencing tables.
- Emitting heap/index WAL.
- Needing valid replica identity so logical subscribers locate the old row accurately.

In application schemas, keep primary keys **immutable** rather than changing them when display IDs change. If business identifiers can change, keep them in a separate column with its own unique constraint.

### 26.1. Do Not Enable REPLICA IDENTITY FULL Unnecessarily

When a table has a primary key, logical replication identifies `UPDATE`/`DELETE` targets via that key. Switching to `REPLICA IDENTITY FULL` increases WAL payload, decoding work, and subscriber lookup costs.

Only alter replica identity when there is a clear technical requirement, test plan, and impact analysis.

---

## 27. Decision Table: Which Optimizations Help and at What Cost?

| Measure | Potential benefit | Trade-off / condition |
| --- | --- | --- |
| Drop genuinely unneeded indexes | Reduces storage and write maintenance | Can hurt reads; preserve constraint indexes |
| Targeted partial index | Smaller index, faster filtered reads | Updates crossing the predicate still pay maintenance cost |
| Avoid updating indexed columns unnecessarily | Increases HOT eligibility | May require schema adjustments or caching |
| Tuned `fillfactor` | Reserves space for HOT updates | Table uses more pages on disk/cache |
| Skip no-op `UPDATE`s | Fewer tuple versions and WAL | Changes trigger/audit firing semantics |
| Multi-row `INSERT` | Reduces round-trip overhead | Requires batch/error management |
| `COPY` for initial bulk load | Strong bulk throughput | Requires COPY-protocol client and clear constraint strategy |
| Build indexes after bulk load | Faster bulk index creation | Peak CPU/I/O/WAL and locking during build |
| Batched updates/deletes | Caps transaction duration and spikes | Does not guarantee lower total WAL |
| Tune autovacuum | Controls dead tuples and bloat | Consumes background I/O/CPU; tune by metrics |
| `wal_compression` | Shrinks FPI WAL in many workloads | Uses CPU; does not compress non-FPI records uniformly |
| Tune checkpoints | Balances FPI rate, recovery time, I/O spikes | Must honor RTO and disk constraints |
| `UNLOGGED` staging | Avoids row WAL for rebuildable data | Lost on crash; not replicated like logged tables |
| Synchronous replication | Stronger remote commit durability | Adds commit latency and availability impact |
| Asynchronous replication | Avoids remote commit waits | Replicas can lag and lose unshipped data on primary loss |
| Replication slots | Protects consumer WAL continuity | Can pin WAL until disk fills |
| Off-peak scheduling | Reduces peak contention | Extends total window and adds orchestration |

**Never optimize purely for raw throughput.** Weigh recoverability, consistency, read latency, RPO/RTO, and operational complexity together.

---

## 28. Real-World Scenario 1: High-Volume Status Transitions

A service transitions 500,000 orders daily from `NEW → PAID`.

In our lab, the partial index `WHERE status='PAID'` accelerates queries listing paid orders, yet forces index updates on every status transition.

Questions to evaluate:

1. What share of read traffic actually filters `status='PAID'`?
2. Is this partial index truly necessary, or does another index suffice?
3. How many status updates per second occur at peak?
4. How much do WAL bytes/statement and WAL bytes/sec increase?
5. Are replicas replaying fast enough?
6. Are there reconciliation bursts at settlement cutoffs?
7. Do payment/reconciliation jobs contend for row locks?
8. Do audit triggers generate extra downstream writes?

Status transitions are **core business logic**—never skip updates or drop needed indexes recklessly. Sound improvements typically come from eliminating redundant writes, validating query plans, pacing batches, or refining index design.

---

## 29. Real-World Scenario 2: Frequently Updated Notes

A multi-million-row table updates `note` frequently while queries look up by `order_id` and `customer_id`.

This workload can benefit well from HOT updates if:

- `note` is excluded from all indexes, expressions, predicates, and `INCLUDE` lists.
- Updated tuples still fit within the same heap page.
- `fillfactor` is sized sensibly.
- Triggers do not amplify writes elsewhere.

Evaluation steps:

```text
Observe HOT ratio and table/index sizes
          |
          v
Check whether any index references note
          |
          v
Inspect row width / TOAST / fillfactor
          |
          v
Measure note UPDATEs with EXPLAIN (ANALYZE, BUFFERS, WAL)
          |
          v
Watch autovacuum and dead-tuple levels
          |
          v
Test schema/index/fillfactor changes in a staging environment
```

If `note` grows from a few dozen bytes to tens of kilobytes, TOAST storage and tuple size become dominant factors; HOT cannot eliminate the cost of writing large values.

---

## 30. Real-World Scenario 3: Replica Lag After CREATE INDEX

A team creates a new index to accelerate search APIs; shortly afterward, standby lag spikes even though application `INSERT` rates did not change noticeably.

Investigation steps:

1. Check whether `CREATE INDEX` or `REINDEX` ran around the time lag started.
2. Check WAL generation rate and archiver queue.
3. Inspect `pg_stat_replication`: `sent_lsn`, `write_lsn`, `flush_lsn`, `replay_lsn`.
4. Inspect standby CPU, disk I/O, and recovery apply activity.
5. Verify physical vs. logical replication (built-in logical replication does not auto-replicate DDL/indexes the way physical replication replays WAL).
6. Check concurrent workloads, checkpoints, and FPIs.
7. Draw conclusions only from time-correlated metrics.

**Never "fix" lag by deleting a replica or dropping its slot.** The spike may simply be the standby catching up on a legitimate WAL burst; rash intervention can destroy recoverability.

---

## 31. Common Misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "Updating one column modifies it in place." | MVCC normally writes a new tuple version |
| "DELETE frees disk space immediately." | Creates dead tuples requiring `VACUUM`; files rarely shrink automatically |
| "Skipping indexed columns guarantees HOT." | Same-page free space and all index definitions still apply |
| "HOT generates zero WAL." | HOT still writes heap tuples and WAL; it avoids extra index entries |
| "Only leading index keys affect HOT." | Expressions, predicates, and `INCLUDE` columns matter too |
| "More indexes are always good because SELECT gets faster." | Indexes add write/storage overhead and can inhibit HOT |
| "Partial indexes add no cost on status UPDATEs." | Changing predicate membership requires maintaining the partial index |
| "An UPDATE with the same value is free." | Normal execution can still create a new tuple version and WAL |
| "WAL is a plain-text log of SQL queries." | WAL logs physical/recovery changes needed for redo |
| "WAL size equals the tuple's data size." | FPIs, index WAL, TOAST, and page metadata all contribute |
| "ROLLBACK deletes the WAL already written." | Logical rollback does not erase generated WAL or disk I/O |
| "`max_wal_size` is a hard cap on `pg_wal`." | Slots, stalled archiving, and other factors can push WAL past it |
| "Disabling `fsync`/`full_page_writes` is a safe tuning trick." | Compromises crash recovery and data durability |
| "`wal_compression` shrinks every WAL record." | Primarily compresses FPIs under eligible conditions |
| "Primary `COMMIT` means standbys already replayed it." | Depends on `synchronous_commit` and replication state |
| "Once a standby receives WAL, queries see it." | Write, flush, replay, and query snapshots all stand in between |
| "Logical replication syncs DDL and indexes automatically." | Built-in logical replication does not auto-replicate DDL |
| "`REPLICA IDENTITY FULL` is always better than `PRIMARY KEY`." | Increases WAL detail and subscriber lookup/apply cost |
| "Inactive slots are harmless." | Inactive slots can pin WAL until disk fills |
| "`pg_stat_wal` measures just my current table." | It is a cluster-wide WAL counter |
| "Low `idx_scan` proves an index is useless." | Unique constraints and targeted workloads may still rely on it |
| "Batching always reduces total WAL." | Smooths spikes and lock duration, does not guarantee fewer total WAL bytes |
| "`VACUUM` always shrinks physical files." | Reclaims internal space for reuse rather than shrinking files on disk |
| "`UNLOGGED` is just a faster logged table." | Has fundamentally different crash, WAL, and replication behavior |
| "`EXPLAIN ANALYZE UPDATE` only explains, doesn't run." | It actually executes the `UPDATE`; run only in safe test transactions |
| "One benchmark run tells the whole story." | Cache warmth, checkpoints, FPIs, and concurrency skew single runs |
| "Replicas replace backups." | Accidental deletes and logical bugs replicate to standbys |
| "Write tuning just means dropping indexes." | Must balance durability, reads, WAL, vacuum, and replication |

---

## 32. Practice Exercises

### Exercise 1 — Trace an INSERT Path

For a newly inserted order with `status='PAID'`, list every structure that may be written: heap, primary key, `customer_id` index, `PAID` partial index, WAL, standby. Explain why a `NEW` row does not enter the `PAID` partial index.

### Exercise 2 — Updating Only `note`

Run:

```sql
BEGIN;
EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE dml_impact_lab.orders
SET note = note || '-x'
WHERE order_id BETWEEN 200 AND 500;
ROLLBACK;
```

Inspect WAL `records`/`fpi`/`bytes` and actual rows updated. Why does WAL still appear even though `note` is unindexed?

### Exercise 3 — Updating an Indexed Column

Repeat the measurement with `customer_id = customer_id + 1000` over the same range inside a rolled-back transaction. Hypothesize why index maintenance increases. Why should you not rely on a single comparison run?

### Exercise 4 — HOT Ratio

Query `pg_stat_user_tables` for `n_tup_upd` and `n_tup_hot_upd`, then compute the HOT percentage safely using `NULLIF`.

Does this ratio measure the single statement you just ran in a rolled-back transaction directly? Explain its cumulative and delayed nature.

### Exercise 5 — Partial Index

Analyze:

```sql
CREATE INDEX idx_orders_paid_customer
ON dml_impact_lab.orders(customer_id)
WHERE status = 'PAID';
```

If `status` changes `NEW → PAID`, which structures may be updated? If an `UPDATE` modifies only `note`, can it still be HOT?

### Exercise 6 — Adding an Index on `note`

Suppose you create an index `ON orders(note)` to speed up searches. Why could that hurt HOT eligibility when the app updates `note` frequently? When would the read speedup still justify that cost?

### Exercise 7 — Non-HOT Update and Unchanged Index Keys

Explain why a non-HOT `UPDATE` can generate new index entries even in an index whose key column stayed unchanged. What role does the heap tuple location play?

### Exercise 8 — DELETE and VACUUM

Delete a batch of `CANCELED` rows in the lab, observe `n_dead_tup` and table size before/after, and run `VACUUM` if permitted in your lab. Why does the file size not necessarily shrink right away?

### Exercise 9 — Batched DELETE

Design an application loop that executes 200-row batched `DELETE`s, commits each batch, and stops when no matching rows remain. Explain how to handle restarts, errors, concurrency, and WAL bursts.

### Exercise 10 — `pg_stat_wal`

Query `wal_records`, `wal_fpi`, `wal_bytes`, and `stats_reset`. Why can the delta in `wal_bytes` between two timestamps contain activity unrelated to your lab?

### Exercise 11 — EXPLAIN WAL

Compare an `UPDATE` changing only `note` against one changing `status` using `EXPLAIN (ANALYZE, BUFFERS, WAL)` in test transactions. Distinguish WAL `records`, `fpi`, and `bytes`.

### Exercise 12 — Checkpoints and FPIs

Why can repeating the exact same workload over the same pages produce different FPI counts depending on checkpoint timing? When does `wal_compression` help, and at what cost?

### Exercise 13 — Physical vs. Logical Replication

Build a comparison table showing how a primary's actions affect a physical standby versus a logical subscriber for:

1. `UPDATE` on data rows.
2. `CREATE INDEX`.
3. `ALTER TABLE` adding a column.
4. `UNLOGGED` staging tables.
5. Changing `REPLICA IDENTITY`.

Explain why results diverge between physical and logical replication.

### Exercise 14 — Replication Lag

From `pg_stat_replication`, distinguish `sent_lsn`, `write_lsn`, `flush_lsn`, and `replay_lsn`. If replay is far behind while receive keeps up, where do you investigate first?

### Exercise 15 — Stale Reads on a Replica

An API writes `PAID` on the primary and immediately reads `NEW` from an async standby. Is that necessarily a SQL bug? Name three strategies to handle different consistency needs.

### Exercise 16 — Replication Slot Pinning WAL

A logical consumer has been down for hours and `pg_wal` is growing rapidly. How do you inspect `pg_replication_slots`, `pg_stat_wal`, and filesystem usage to confirm? Why shouldn't you immediately drop the slot?

### Exercise 17 — Backfill Plan

An 8-million-row table needs a new column backfilled. Outline an assessment plan covering affected row count, indexes/HOT, WAL headroom, archiver, batch size, replication lag, retries, maintenance window, and reconciliation.

### Exercise 18 — UNLOGGED Staging

What kinds of data belong in an `UNLOGGED` staging table? What happens if the server crashes or fails over to a standby mid-import?

### Exercise 19 — Index Selection

An index is rarely scanned for reads yet enforces a `UNIQUE` constraint. Should you drop it to speed up writes? If another index looks redundant, what evidence must you gather before dropping it?

### Exercise 20 — Transactions and COMMIT Latency

An `UPDATE` reports 8 ms Execution Time, yet the application waits 60 ms for `COMMIT`. List possible contributors (WAL flush, synchronous standby, network, locks, app pauses) and how to isolate them.

### Exercise 21 — Logical REPLICA IDENTITY

If a publisher table lacks a primary key while its publication includes `UPDATE`/`DELETE`, what must you investigate? Why can `REPLICA IDENTITY FULL` increase WAL and apply cost?

### Exercise 22 — Spotting Flawed Benchmarks

A team measures updating `note` before adding indexes, then updates `status` after adding four indexes, and concludes updating `status` is inherently 10× slower. List the uncontrolled variables: row counts, index definitions, FPIs/checkpoints, HOT eligibility, cache warmth, transactions, triggers, WAL, and concurrent writers.

### Exercise 23 — Avoiding No-Op Writes

Write an `UPDATE` changing `status` only when it differs from the target using `IS DISTINCT FROM`. When might skipping the `UPDATE` break audit logs or trigger expectations?

### Exercise 24 — Recovery and Backups

Explain WAL's role in crash recovery and PITR. Why is a WAL archive without a valid base backup insufficient for recovery, and why do replicas not replace backups?

---

## 33. Checklist for Evaluating a Major Data Change

| Question | How to evaluate |
| --- | --- |
| How many rows truly change? | `SELECT COUNT(*)`, `WHERE` selectivity, range checks |
| Is the DML an `INSERT`, `UPDATE`, or `DELETE`? | Assess tuple versions, indexes, dead tuples |
| Are updated columns indexed? | Check keys, `INCLUDE`, expressions, partial predicates |
| Is HOT likely? | Same-page space, `fillfactor`, index dependencies |
| Are triggers/FKs/cascades involved? | Trace indirect writes and lock chains |
| Are large TOAST values updated? | Inspect row width and payload growth |
| How many indexes exist? | Review index definitions, sizes, reads, constraints |
| Are all indexes actually needed? | Audit workload/constraints before dropping any |
| Must the data survive crashes/failover? | Use logged tables; never abuse `UNLOGGED` |
| How much WAL does the write emit? | `EXPLAIN ... WAL`, cluster WAL rates |
| Are FPIs significant? | Watch `wal_fpi`, checkpoints, `wal_compression` |
| Could `pg_wal` fill up? | Monitor disk space, slots, and archiver lag |
| Are physical standbys attached? | Monitor sent/write/flush/replay LSNs |
| Are logical subscribers attached? | Watch apply throughput, replica identity, schema sync |
| Is synchronous replication enabled? | Check commit latency and sync mode |
| Do replica reads expect read-your-writes? | Route critical reads or wait for LSN replay |
| How long will transactions run? | Watch locks, snapshots, `VACUUM`, retries |
| Can the work be batched? | Pick rows per transaction and throttle rate |
| Is the batch safely resumable? | Ensure idempotency, checkpoints, stable ordering |
| Can the campaign be rolled back safely? | Verify backups/PITR and operational rollback plan |
| Are `VACUUM`/`ANALYZE` needed afterward? | Monitor dead tuples, stats freshness, autovacuum |
| Is table/index bloat a risk? | Track size over time, HOT rate, vacuum progress |
| Is an index rebuild warranted? | Act only on hard evidence; account for locks and WAL |
| Will concurrent writers interfere? | Plan retries, contention bounds, isolation level |
| Have real plans been inspected? | Review `EXPLAIN` on production-like data |
| Are before/after baselines captured? | Measure latency, rows/s, WAL/s, lag, CPU, disk |
| Is durability preserved properly? | Never turn off `fsync` or `full_page_writes` |
| Is live monitoring configured? | Alert on WAL, lag, disk space, autovacuum, errors |
| Are stop/abort thresholds defined? | Set clear latency/lag/disk limits and owners |

## Conclusion

Evaluating a write operation in PostgreSQL means looking well beyond the affected row count reported by SQL. An `INSERT` creates both a heap tuple and index entries; an `UPDATE` under MVCC typically produces a new tuple version and only avoids index writes when **HOT** applies; and a `DELETE` does not immediately shrink files on disk, leaving cleanup work to **VACUUM**.

At the durability layer, **WAL** records changes required for crash recovery, backups, and replication. WAL volume exceeds raw user-data size due to index updates, full-page images, checkpoints, TOAST writes, and indirect triggers. Chasing raw write speed by disabling durability features undermines system reliability.

At the replication layer, **physical replication** replays physical WAL changes, whereas **logical replication** decodes and applies row-level changes per publication and requires separate management of schemas, replica identity, and subscriber indexes. Committing on the primary does not guarantee an async standby has caught up; replication slots and stalled WAL archiving can also cause `pg_wal` to grow rapidly.

A reliable workflow is:

1. Identify the logical change and true affected row count.
2. Inspect MVCC effects, HOT eligibility, index definitions, triggers, and foreign keys.
3. Measure `EXPLAIN (ANALYZE, BUFFERS, WAL)` safely in a test environment.
4. Monitor WAL rate, dead tuples, table/index size, autovacuum, and replica lag.
5. Make explicit trade-offs across write speed, read speed, durability, recovery, and consistency.
6. Control batching, live monitoring, stop thresholds, and safe resumability.

Once you understand how **heap/MVCC**, **indexes**, **WAL**, and **replication** interact, you can explain why a small write batch causes heavy I/O, why an index built for fast `SELECT`s slows down `UPDATE`s, and why large backfills must be engineered as measurable, controllable operations rather than one-off SQL scripts.
