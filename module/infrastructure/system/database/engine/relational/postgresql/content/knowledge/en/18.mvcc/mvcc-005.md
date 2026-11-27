# UPDATE, DELETE, Old Row Versions, and Dead Rows in PostgreSQL

One of PostgreSQL's most important characteristics is **MVCC — Multi-Version Concurrency Control**, a mechanism for controlling concurrency using multiple versions of data.

When an application executes:

```sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 1001;
```

PostgreSQL does not simply overwrite `status` at the old row's location in a way that forces every transaction to immediately see a single new version. Instead, for standard heap tables, PostgreSQL creates a **new row version** and marks the previous version as superseded. A transaction reading under an older snapshot can still need to see the previous version, while a transaction starting after the `UPDATE` commits will see the new version.

Similarly:

```sql
DELETE FROM orders WHERE order_id = 1001;
```

does not necessarily make the row's data bytes vanish from the file immediately. PostgreSQL marks the row version as logically deleted, after which **pruning** and **VACUUM** reclaim the space once no transaction needs the old version anymore.

This explains commonly observed behaviors:

- Frequent `UPDATE`s cause a table or index to grow even though the number of logical business rows stays nearly constant.
- Deleting millions of records does not immediately shrink file sizes.
- A `SELECT` in an older transaction still sees data that another transaction just `UPDATE`d or `DELETE`d.
- `VACUUM` runs yet cannot clean up all dead tuples because an old snapshot is still active.
- Updating an unindexed column is sometimes faster than updating an indexed column thanks to **HOT updates**.
- The `n_dead_tup` metric can grow after many writes, though it is not an exact count at every instant.
- Running `VACUUM` properly enables space reuse, which does not mean every file automatically shrinks.

This lesson focuses on explaining **`UPDATE`, `DELETE`, old row versions, and dead rows** in the context of PostgreSQL MVCC: from snapshot principles, tuple metadata, and HOT/non-HOT updates to garbage collection, monitoring, bloat investigation, and safe hands-on practice.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Explain why PostgreSQL retains multiple versions of a row when `UPDATE`s occur.
2. Distinguish **current row**, **old row version**, **no-longer-visible version**, and **reclaimable dead tuple**, rather than calling everything "deleted rows."
3. Explain how `DELETE` marks a row version and why another transaction's `SELECT` may still see that row.
4. Use the snapshot model to predict results under `READ COMMITTED` and `REPEATABLE READ`.
5. Understand the general roles of system columns `xmin`, `xmax`, and `ctid`, as well as the limitations when reading them.
6. Distinguish HOT from non-HOT `UPDATE`s and see why indexed columns, `fillfactor`, and free space on heap pages matter.
7. Explain why `UPDATE`/`DELETE` bring along dead tuples, index maintenance, WAL, and `VACUUM`.
8. Understand **heap page pruning**, **VACUUM**, **autovacuum**, **VACUUM FULL**, and the difference between reusing space internally and returning disk space to the operating system.
9. Recognize that long-running transactions, replication slots, and standby feedback can hold back old versions.
10. Inspect `pg_stat_user_tables`, relation sizes, `EXPLAIN (ANALYZE, BUFFERS, WAL)`, and related metrics.
11. Analyze scenarios involving repeated `UPDATE`s, bulk `DELETE`s, table bloat, and transaction ID wraparound.
12. Write queries, simulate two sessions, verify results, and propose solutions aligned with business requirements.

> **Scope:** Examples apply to regular heap tables in modern PostgreSQL. Some internal details, statistics field names, and optimization behaviors can vary across versions. Data-modifying statements must only be run on a **practice database that is safe to reset**.

---

## 2. Why Are Multiple Row Versions Needed?

Suppose the system has a row:

```text
order_id=101 | status=NEW | amount=100
```

Two sessions run concurrently:

```text
Time        Session A (reader)           Session B (writer)
----------------------------------------------------------------
T1          Begin transaction
T2          Read order 101 = NEW
T3                                       UPDATE status='PAID'
T4                                       COMMIT
T5          Re-read order 101
T6          COMMIT
```

Question: at T5, does Session A see `NEW` or `PAID`?

**The answer depends on the isolation level and snapshot**:

- With standard `READ COMMITTED`, each statement receives an appropriate snapshot at statement start. The new `SELECT` after B's `COMMIT` can see `PAID`.
- With `REPEATABLE READ`, A holds its transaction snapshot once established, so the subsequent `SELECT` still sees `NEW`, even though B committed.

To support both behaviors without forcing every `SELECT` to wait on `UPDATE`s, PostgreSQL must manage **data versions**.

### 2.1. Conceptual Model

```text
Before UPDATE:
    Tuple V1: (id=101, status=NEW)

Session B UPDATE:
    Tuple V1: (id=101, status=NEW)   <- old version
          |
          +----> Tuple V2: (id=101, status=PAID) <- new version

Session A with old snapshot:
    sees V1

Other session with post-COMMIT snapshot:
    sees V2

When no snapshot needs V1 anymore:
    V1 can be reclaimed/reused by PostgreSQL mechanisms
```

This is a logical model, not a guarantee that V1 and V2 always live on the same physical page. They may be on the same heap page or different pages depending on conditions.

### 2.2. Difference Between Logical Value and Physical Tuples

One **business row** with key `order_id=101` can go through many **tuple versions**:

```text
V1 NEW
   |
   v
V2 PAID
   |
   v
V3 PAID, note='confirmed'
   |
   v
V4 CANCELED
```

An application usually only cares about the **current version** visible to its snapshot; PostgreSQL must manage any versions still needed by other transactions.

That is why "one row was `UPDATE`d 1,000 times" is not equivalent to "writing to the exact same bytes on disk."

---

## 3. Terminology to Distinguish

| Term | Meaning |
| --- | --- |
| **Logical row** | A record from the business perspective, e.g., order #101 |
| **Heap tuple** | A row version stored in the table's heap structure |
| **Tuple version** | A version of the row produced by `INSERT`/`UPDATE` |
| **Snapshot** | Metadata determining which transactions/tuples are visible to a read query |
| **Visible tuple** | A version satisfying visibility rules for a given snapshot |
| **Old tuple version** | An older version after `UPDATE` or `DELETE`; may still be needed by another snapshot |
| **Dead tuple** | A tuple no longer needed by any eligible snapshot and eligible for cleanup/reuse per system rules |
| **Pruning** | Cleaning/collapsing tuple chains on a heap page when safe |
| **VACUUM** | Maintenance that reclaims reusable space and assists with transaction age management |
| **Autovacuum** | Background mechanism triggering `VACUUM`/`ANALYZE` based on conditions and thresholds |
| **HOT update** | An optimized `UPDATE` that can avoid adding new index tuples when conditions are met |
| **Bloat** | A state where a table/index uses much more space than necessary for its current useful data |
| **Freeze** | Processing transaction metadata of old versions to prevent XID wraparound risk |
| **WAL** | Write-ahead log used for recovery and replication of logged changes |

**Important note:** "Old version" **does not equal** "allowed to delete immediately." A tuple may no longer be visible to new snapshots yet still be required by a long-running transaction holding an old snapshot.

### 3.1. Four Conceptual States

```text
INSERT/UPDATE creates a new version
           |
           v
Version COMMITs and can be visible to some snapshots
           |
           v
New UPDATE/DELETE makes the version old
           |
           v
Does any snapshot still need the old version?
    |                      |
   Yes                     No
    |                      |
    v                      v
Retain                 Eligible for cleanup/prune/VACUUM
    |
    +----> When snapshot ends, re-evaluate cleanup eligibility
```

In reality, visibility also depends on commit/abort status, tuple metadata, locks, and other MVCC details. This diagram is for learning the concepts, not a complete state machine of heap tuples.

---

## 4. Setup Experiment: Creating a Dedicated MVCC Table

Let us create a table with a primary key, an indexed column, and an unindexed column so we can observe both kinds of `UPDATE`s.

> **Warning:** `DROP TABLE IF EXISTS` deletes existing data in that practice table. Only run these statements on a test database or resettable schema. Never run them in production.

### 4.1. Creating the Schema and Table

```sql
CREATE SCHEMA IF NOT EXISTS mvcc_versions_lab;

DROP TABLE IF EXISTS mvcc_versions_lab.orders;

CREATE TABLE mvcc_versions_lab.orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELED')),
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    note TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
) WITH (fillfactor = 80);
```

Key points:

- `order_id` is the `PRIMARY KEY` and has a unique index.
- `customer_id` will be indexed to illustrate updating an indexed column.
- `note` is not in any index, giving it an opportunity for HOT `UPDATE`s.
- `status` participates in the predicate of a partial index.
- `fillfactor = 80` encourages PostgreSQL to leave free space on pages, helping in-page updates when conditions allow. It does not guarantee every `UPDATE` becomes HOT.

### 4.2. Inserting Data

```sql
INSERT INTO mvcc_versions_lab.orders (
    order_id, customer_id, status, amount, note
)
VALUES
    (101, 1, 'NEW',      100.00, 'created'),
    (102, 1, 'NEW',       80.00, 'created'),
    (103, 2, 'PAID',     150.00, 'paid'),
    (104, 2, 'CANCELED',  50.00, 'cancelled'),
    (105, 3, 'NEW',      200.00, 'created'),
    (106, 4, 'NEW',       25.00, 'created');

CREATE INDEX idx_mvcc_orders_customer
ON mvcc_versions_lab.orders(customer_id);

CREATE INDEX idx_mvcc_orders_paid
ON mvcc_versions_lab.orders(order_id)
WHERE status = 'PAID';

ANALYZE mvcc_versions_lab.orders;
```

### 4.3. Inspecting the Data

```sql
SELECT
    order_id, customer_id, status, amount, note
FROM mvcc_versions_lab.orders
ORDER BY order_id;
```

Six initial orders:

| order_id | customer_id | status | amount | note |
| ---: | ---: | --- | ---: | --- |
| 101 | 1 | NEW | 100 | created |
| 102 | 1 | NEW | 80 | created |
| 103 | 2 | PAID | 150 | paid |
| 104 | 2 | CANCELED | 50 | cancelled |
| 105 | 3 | NEW | 200 | created |
| 106 | 4 | NEW | 25 | created |

The lab allows you to reset the table with the statements in this section before moving to another experiment. Avoid running all `UPDATE`/`DELETE`s back-to-back and still expecting outputs to match the initial data.

---

## 5. System Columns: xmin, xmax, and ctid

PostgreSQL provides several **system columns** on heap tables, letting you inspect tuple-level traces:

- `xmin`: transaction ID associated with creating the tuple version.
- `xmax`: metadata related to deleting/replacing or **locking** the tuple; never read it naively as "the transaction that DELETEd it."
- `ctid`: physical location of the tuple version in the heap (block, offset).

Try:

```sql
SELECT
    order_id,
    status,
    xmin::TEXT AS xmin_text,
    xmax::TEXT AS xmax_text,
    ctid::TEXT AS tuple_location
FROM mvcc_versions_lab.orders
ORDER BY order_id;
```

The values of `xmin`, `xmax`, and `ctid` in the output **depend entirely on the run, transaction history, VACUUM, and how PostgreSQL placed the tuples**. There is no fixed set of numbers that matches across all machines.

### 5.1. What Does xmin Tell Us?

A tuple version is created by a specific transaction. `xmin` usually identifies the transaction ID that created the version currently being read.

Conceptual example:

```text
V1: xmin=500
UPDATE by transaction 501
V2: xmin=501
```

Do not deduce business chronological order or absolute `COMMIT` timing merely by comparing two `xmin` numbers. Transaction IDs have allocation rules, wraparound, and age-based freezing.

### 5.2. Why Isn't xmax Just a DELETE Marker?

A common but inaccurate explanation is "`xmax=0` means the row is not deleted; `xmax!=0` means the row is deleted."

In reality, `xmax` is also used in **row locking**, can hold an uncommitted transaction or a MultiXact, and visibility also depends on transaction status and internal flags.

Therefore:

- Never use `xmax <> 0` to conclude a row **was successfully DELETEd**.
- Never write business logic using `xmin`/`xmax` instead of application-managed status, audit, or timestamp columns.
- Never use `xmax` as an API to confirm `INSERT ... ON CONFLICT` outcomes without understanding internal semantics and cross-version stability.

### 5.3. ctid Is Not a Durable Key

`ctid` represents a tuple version's physical location in the heap. After an `UPDATE`, the new version can live at a different location; `VACUUM FULL` or table rewrites also change locations.

Therefore:

- `ctid` is useful when **studying physical placement** or internals within careful bounds.
- `ctid` is **not a primary key** and must never be stored as a long-term ID in applications.
- Never assume `ctid` increases monotonically or always stays in the same block across `UPDATE`s.

### 5.4. One Snapshot Does Not Show Every Version

A normal `SELECT` only returns tuples **visible to its snapshot**; you cannot expect `SELECT xmin, xmax, ctid` to list all old uncleaned versions sitting on a page.

To inspect deeper physical states, specialized extensions and tools such as `pageinspect` may be needed, and only in a lab with proper privileges. Reading raw pages and decoding status flags goes beyond regular SQL queries.

---

## 6. How Does UPDATE Create a New Row Version?

In the initial state:

```sql
SELECT
    order_id, status, amount, note,
    xmin::TEXT AS xmin_text,
    ctid::TEXT AS ctid_text
FROM mvcc_versions_lab.orders
WHERE order_id = 101;
```

Then inside a controlled transaction:

```sql
BEGIN;

UPDATE mvcc_versions_lab.orders
SET status = 'PAID',
    updated_at = clock_timestamp()
WHERE order_id = 101
RETURNING
    order_id, status, amount, note,
    xmin::TEXT AS new_xmin,
    ctid::TEXT AS new_ctid;

COMMIT;
```

The new version has `status='PAID'`. If you query again:

```sql
SELECT
    order_id, status,
    xmin::TEXT AS xmin_text,
    ctid::TEXT AS ctid_text
FROM mvcc_versions_lab.orders
WHERE order_id = 101;
```

you are reading the version considered valid by the current snapshot.

### 6.1. What Happens to the Old NEW Version?

Logically:

```text
V1: (id=101, status=NEW)
     xmin=T_insert
     UPDATEd by T_update
         |
         v
V2: (id=101, status=PAID)
     xmin=T_update
```

When `T_update` commits:

- Sufficiently new snapshots normally see V2 and not V1.
- Older snapshots may still see V1.
- Once nobody needs V1, its space can be reclaimed/reused by PostgreSQL.

### 6.2. UPDATE Writes More Than Just the New Row

Beyond the new heap version, there may be:

- Required WAL records.
- Index maintenance work.
- Triggers and constraints.
- Dead tuples and future cleanup work.
- Dirty buffers that must be flushed to data files.
- Replay on physical standbys or apply on logical subscribers if configured.

In the lab, changing `status` can affect the partial index `WHERE status='PAID'`. That is one reason why this `UPDATE` can be more expensive than an `UPDATE` modifying only the `note` column.

### 6.3. Multi-Row UPDATE Does Not Create "One Shared Old Version"

```sql
BEGIN;

UPDATE mvcc_versions_lab.orders
SET amount = amount + 10
WHERE customer_id = 1
RETURNING order_id, amount;

ROLLBACK;
```

Both rows `101` and `102` may be matched (if initial customer data was unchanged), each getting its own new version inside the transaction. `ROLLBACK` prevents the changes from committing, yet it does not mean zero heap/WAL work happened during execution.

---

## 7. Transaction Rollback: Created Versions Never Become Valid Data

An `UPDATE` can fail or a transaction can roll back:

```sql
BEGIN;

UPDATE mvcc_versions_lab.orders
SET note = 'temporary note'
WHERE order_id = 102;

SELECT order_id, note
FROM mvcc_versions_lab.orders
WHERE order_id = 102;

ROLLBACK;

SELECT order_id, note
FROM mvcc_versions_lab.orders
WHERE order_id = 102;
```

Inside the transaction, it can see `temporary note` because it wrote it itself. After rollback, new transactions see the version from before that `UPDATE`.

However, tuples created inside an aborted transaction can still leave behind traces needing cleanup in the heap. The system distinguishes **tuples from committed transactions** from **tuples from aborted transactions** via metadata and transaction status.

**`ROLLBACK` restores the logical outcome; it does not necessarily revert every physical byte instantaneously.** That is also why benchmarking `UPDATE` inside a transaction followed by `ROLLBACK` still generates WAL, dirty buffers, and cleanup work.

---

## 8. Two Sessions: What Does READ COMMITTED See After UPDATE?

This is the most important lab for understanding snapshots.

Use **two independent PostgreSQL connections**, such as two `psql` windows or two SQL editor tabs with separate sessions. Run the commands in the exact order below. To match the described output, first reset the table and reload the initial data from section 4.

### 8.1. Session A: Open READ COMMITTED

```sql
-- SESSION A
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT order_id, status
FROM mvcc_versions_lab.orders
WHERE order_id = 101;
```

Initially sees `NEW`.

### 8.2. Session B: Update and Commit

```sql
-- SESSION B (separate connection)
BEGIN;

UPDATE mvcc_versions_lab.orders
SET status = 'PAID'
WHERE order_id = 101;

COMMIT;
```

Since A only ran a normal `SELECT`, it does not block B; B can commit its `UPDATE`.

### 8.3. Session A: Read Again After B's Commit

```sql
-- SESSION A (still in the same transaction)
SELECT order_id, status
FROM mvcc_versions_lab.orders
WHERE order_id = 101;

COMMIT;
```

Under `READ COMMITTED`, A's second statement receives a new snapshot per isolation rules, so it can see `PAID` committed by B.

### 8.4. Why Isn't A "Reading Dirty Data"?

A did not read B's uncommitted `UPDATE`. It only saw `PAID` **after B COMMITted**, in a statement permitted to use a new snapshot.

PostgreSQL does not allow dirty reads in the usual sense even when an application requests isolation level `READ UNCOMMITTED`; that level behaves equivalently to `READ COMMITTED`.

### 8.5. Snapshot at Statement Start, Not Row Start

A long-running `SELECT` gets one consistent view of data under the snapshot assigned to that statement. Do not imagine individual rows in the same `SELECT`'s output dynamically "flipping" to a new state as another transaction commits mid-query.

Specific lock/recheck rules for `UPDATE`/`DELETE` under `READ COMMITTED` have additional details, so this phrasing mainly describes normal `SELECT` behavior.

---

## 9. Two Sessions: REPEATABLE READ Still Sees the Old Version

Reset the initial data before this example, or pick a row that is still `NEW` to test.

### 9.1. Session A: Start Transaction and Acquire Snapshot

```sql
-- SESSION A
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT order_id, status
FROM mvcc_versions_lab.orders
WHERE order_id = 101;
```

On this read, A sees `NEW`.

### 9.2. Session B: UPDATE and COMMIT

```sql
-- SESSION B
BEGIN;

UPDATE mvcc_versions_lab.orders
SET status = 'PAID'
WHERE order_id = 101;

COMMIT;
```

### 9.3. Session A: Read Again

```sql
-- SESSION A
SELECT order_id, status
FROM mvcc_versions_lab.orders
WHERE order_id = 101;
```

A **still sees NEW** under the `REPEATABLE READ` transaction snapshot, even though B committed.

Then:

```sql
-- SESSION A
COMMIT;

-- New statement/transaction:
SELECT order_id, status
FROM mvcc_versions_lab.orders
WHERE order_id = 101;
```

Now, with a fresh snapshot, A can see `PAID`.

### 9.4. Key Distinction: Reading vs. Updating

If A does not merely `SELECT`, but **attempts to UPDATE the same row already changed by B after the snapshot**, PostgreSQL `REPEATABLE READ` can raise a concurrency error like:

```text
ERROR: could not serialize access due to concurrent update
SQLSTATE: 40001
```

This situation may require rolling back and retrying the entire transaction. Never assume that because A read the old version, it is allowed to overwrite the new version without concurrency checks.

### 9.5. How Long Are Old Versions Retained?

In this lab, while A holds a snapshot from before B's `UPDATE`, PostgreSQL may have to keep the OLD version so A can still read it.

Once A ends its transaction, the old version may no longer be needed by A; however, cleanup eligibility also depends on **other transactions/snapshots** and visibility management factors.

A long transaction can therefore cause dead tuples to persist for a long time, even when newer transactions no longer see those old rows.

---

## 10. DELETE in MVCC: Logical Deletion First, Physical Cleanup Later

First, when a `DELETE` statement runs:

```sql
BEGIN;

DELETE FROM mvcc_versions_lab.orders
WHERE order_id = 102
RETURNING order_id, status, amount;

COMMIT;
```

In a new snapshot after `COMMIT`:

```sql
SELECT *
FROM mvcc_versions_lab.orders
WHERE order_id = 102;
```

the row is gone.

However, this does not mean the heap page immediately wiped every trace of tuple 102.

### 10.1. State Before and After DELETE

```text
Before DELETE:
    V1 (id=102) -> visible to eligible snapshots

DELETE in transaction B:
    V1 gets deletion metadata recorded by B

B has not COMMITted yet:
    Other sessions normally still see V1 per snapshot
    B sees the row as deleted per its own change

B COMMITs:
    New snapshots do not see V1
    Old snapshots can still see V1

When no snapshot needs V1 anymore:
    VACUUM/pruning can reclaim the space
```

No "V2 deleted row" is created the way `UPDATE` creates a new version holding new values. `DELETE` marks the existing version as logically deleted via MVCC metadata.

### 10.2. Is an Uncommitted DELETE Immediately Visible?

If B ran `DELETE` without **COMMITting yet**, A running a normal `SELECT` in another transaction still sees the row per its snapshot.

This is the foundation for preventing dirty reads. However, if A attempts `UPDATE`/`DELETE`/`SELECT FOR UPDATE` on the same row, **row-level locks** can make A wait; MVCC does not mean every kind of access is lock-free.

### 10.3. ROLLBACK DELETE

```sql
BEGIN;

DELETE FROM mvcc_versions_lab.orders
WHERE order_id = 103;

ROLLBACK;
```

After rollback, row 103 remains valid in its pre-transaction state because the `DELETE` was not committed.

**Do not call this "VACUUM restoring rows."** `VACUUM` never restores committed `DELETE`s; rollback is what cancels the effects of an uncommitted transaction.

---

## 11. Concurrent DELETE and Old Snapshots

This is a parallel demonstration for `DELETE`; reset initial data before running.

### Session A

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT order_id, status
FROM mvcc_versions_lab.orders
WHERE order_id = 102;
-- Sees row 102.
```

### Session B

```sql
BEGIN;

DELETE FROM mvcc_versions_lab.orders
WHERE order_id = 102;

COMMIT;
```

### Session A, Still in the Same Transaction

```sql
SELECT order_id, status
FROM mvcc_versions_lab.orders
WHERE order_id = 102;
-- Can still see the old version of row 102.

COMMIT;
```

After A commits:

```sql
SELECT order_id, status
FROM mvcc_versions_lab.orders
WHERE order_id = 102;
-- New snapshot does not see row 102.
```

Retaining the old version protects **read consistency**—it is not a "stuck DELETE" bug.

### 11.1. Why Shouldn't You Run VACUUM to Try to Erase the Row From A's Snapshot?

`VACUUM` must respect versions still needed by valid snapshots. If A holds an old snapshot, a regular `VACUUM` **is not allowed to delete data that A still needs**.

If an operator sees dead tuples aren't dropping, inspect old transactions/snapshots rather than repeatedly running `VACUUM FULL` or concluding `VACUUM` is broken.

---

## 12. What Exactly Is a "Dead Row"?

The term "dead tuple" is often used loosely for any old version left by `UPDATE`/`DELETE`. In technical analysis, distinguish:

1. **A version that is no longer the current version:** after `UPDATE`, V1 was replaced by V2.
2. **A version still needed by a snapshot:** though old, V1 cannot yet be reclaimed.
3. **A version no longer needed by relevant snapshots:** eligible for cleanup by PostgreSQL mechanisms.
4. **Space cleaned/reused:** the page now has free slots available for future `INSERT`/`UPDATE`s.

Simplified lifecycle:

```text
V1 is INSERTed and COMMITted
     |
     +--> New UPDATE/DELETE
                 |
                 v
         V1 becomes an old version
                 |
                 v
          Any snapshot still need V1?
            |             |
           Yes            No
            |             |
            v             v
          Keep        Eligible for cleanup
                           |
                           v
                 Page pruning / VACUUM
                           |
                           v
                 Space is reused
```

**Not every old tuple can be cleaned immediately; nor has every dead tuple counted in stats been physically cleaned yet.**

### 12.1. Estimated Dead Tuples Is Not the Number of DELETEd Rows

An `UPDATE` can create an old version; a committed `DELETE` creates a version that will become unneeded. However:

- Some transactions roll back.
- Page pruning may already have cleaned some versions.
- HOT chains can hold multiple versions.
- `VACUUM` may have run and reused space.
- Statistics are accumulated/estimated values with lag.

Therefore, never take `n_dead_tup` and claim it equals `COUNT(*)` of `DELETE`s or the exact count of physical heap versions currently on disk.

---

## 13. HOT UPDATE: Reducing Index Cost While Still Creating a Tuple Version

**HOT — Heap-Only Tuple** is an important PostgreSQL optimization.

When an `UPDATE` meets the criteria, the new version can reside **on the same heap page** without creating new index entries in regular indexes.

Common conditions:

- The `UPDATE` does not modify any column indexed directly or indirectly per PostgreSQL rules.
- Sufficient free space exists on **the same heap page** for the new version.
- Other internal conditions permit creating a HOT chain.

Lab example:

```sql
BEGIN;

UPDATE mvcc_versions_lab.orders
SET note = 'checked by support'
WHERE order_id = 105;

ROLLBACK;
```

`note` is not indexed in the lab schema, so this is a **HOT candidate**.

Still, there remain:

- A new heap version.
- MVCC metadata.
- Corresponding WAL and dirty buffers for logged tables.
- Future pruning/`VACUUM` work as needed.

**HOT is not an in-place update and does not mean "zero dead tuples."** The main savings comes from avoiding new index tuple insertions.

### 13.1. Visualizing a HOT Chain

```text
B-tree index entry
       |
       v
Heap tuple root (V1)
       |
       v
HOT-updated V2 (same heap page)
       |
       v
HOT-updated V3 (same heap page)
```

When PostgreSQL looks up the row via the index, it can follow the chain within the heap page to find the version visible to the snapshot.

Because the index entry still points to the root of the chain, PostgreSQL avoids adding extra index entries on qualifying `UPDATE`s. When old versions are no longer needed, the chain can be pruned/collapsed under safe rules.

### 13.2. Fillfactor Helps, but Does Not Guarantee HOT

With:

```sql
CREATE TABLE ... WITH (fillfactor = 80);
```

PostgreSQL leaves free space on pages during `INSERT` according to `fillfactor`. That increases the chance an `UPDATE` can place the new version **on the same page**.

However:

- A page can fill up after several `UPDATE`s.
- The new tuple may be wider than the old tuple.
- Large data types / TOAST change space behavior.
- An `UPDATE` might touch an indexed column and thus not be HOT.
- Summarizing indexes such as BRIN have version-specific HOT rules.

Do not pick `fillfactor` by guesswork. Decide based on table size, `UPDATE` frequency, and observed HOT ratios.

---

## 14. Non-HOT UPDATE and Why Indexes Grow

In the lab, `customer_id` is indexed:

```sql
CREATE INDEX idx_mvcc_orders_customer
ON mvcc_versions_lab.orders(customer_id);
```

If you `UPDATE`:

```sql
BEGIN;

UPDATE mvcc_versions_lab.orders
SET customer_id = customer_id + 1000
WHERE order_id = 105;

ROLLBACK;
```

the new row has a different indexed key value, so the `UPDATE` cannot be HOT under normal rules.

Similarly, `status` appears in the predicate of a partial index:

```sql
CREATE INDEX idx_mvcc_orders_paid
ON mvcc_versions_lab.orders(order_id)
WHERE status = 'PAID';
```

When `status` transitions `NEW → PAID`:

- The new row enters the partial index.
- Related indexes must be maintained.
- HOT eligibility is affected by index dependencies.

### 14.1. Why Can an Index Whose Key Didn't Change Still Need Maintenance?

In a non-HOT update, the new heap version may have a different physical location. Index entries must map to tuples discoverable under MVCC rules.

Thus, a non-HOT `UPDATE` typically creates **new index entries across the table's other indexes too**, even when the key values of some of those indexes did not change.

In other words, PostgreSQL does not index just key values; indexes must point to the appropriate tuple versions. This is a source of **write amplification** in non-HOT `UPDATE`s.

### 14.2. Expressions and INCLUDE Also Matter

The following indexes are **illustrative**; you do not have to create them in the lab:

```sql
-- Expression index depending on amount.
CREATE INDEX idx_amount_rounded
ON mvcc_versions_lab.orders ((ROUND(amount, 0)));

-- Covering index also storing the note column.
CREATE INDEX idx_customer_covering
ON mvcc_versions_lab.orders (customer_id)
INCLUDE (note);

-- Partial index depending on status.
CREATE INDEX idx_paid_amount
ON mvcc_versions_lab.orders(amount)
WHERE status = 'PAID';
```

When evaluating HOT eligibility, inspect all of:

- Index keys.
- `INCLUDE` columns.
- Index expressions.
- Partial index predicates.

A column absent from an index's **leading key list** can still be an index dependency that prevents HOT updates.

### 14.3. Why Not Drop All Indexes to Make UPDATE Faster?

Indexes also serve:

- Critical lookups, `ORDER BY`, and filters.
- Unique constraints and `PRIMARY KEY`s.
- Reporting queries.
- Efficient execution plans.

Dropping indexes solely to reduce write cost can severely degrade read workloads or break data constraints. Optimization must weigh **read and write** metrics together.

---

## 15. An UPDATE That Doesn't Change Values Can Still Create a New Version

Example:

```sql
UPDATE mvcc_versions_lab.orders
SET note = note
WHERE order_id = 106;
```

Beginners might assume this statement is free because the old and new `note` values are identical. Yet a normally executed `UPDATE` still creates a new heap version, generates WAL, fires triggers, and creates `VACUUM` work unless something skips or avoids the update.

If you only want to `UPDATE` when the value actually differs:

```sql
UPDATE mvcc_versions_lab.orders
SET note = 'verified'
WHERE order_id = 106
  AND note IS DISTINCT FROM 'verified';
```

`IS DISTINCT FROM` handles `NULL` cleanly, unlike `<>` on nullable columns.

### 15.1. Do Not Skip UPDATE If Business Logic Needs the Side Effect

An audit system might intentionally run an `UPDATE` on every confirmation request even if values match. Adding `IS DISTINCT FROM` could cause:

- Audit triggers not to fire.
- `updated_at` not to change.
- Outbound system events to be skipped.

Therefore, skipping redundant `UPDATE`s is a **business decision**, not merely a performance trick.

### 15.2. Repeatedly Updating the Same Row

If the same row is `UPDATE`d hundreds of times in a short window, many tuple versions may exist or have existed:

```text
V1 -> V2 -> V3 -> V4 -> ... -> Vn
```

Pruning/HOT can quickly clean versions no longer needed; however, if a long transaction holds an old snapshot, reclamation is restricted. The outcome depends on page space, indexes, and cleanup speed.

---

## 16. How Does DELETE Affect Indexes?

When deleting a tuple, PostgreSQL does not necessarily remove every entry across all indexes immediately when `DELETE` executes.

Intuition:

```text
DELETE row id=102
   |
   +--> Heap tuple marked per MVCC
   |
   +--> New snapshots stop seeing row after commit
   |
   +--> Old index entries may remain for some time
   |
   +--> VACUUM/index cleanup runs when safe
```

If an index scan visits an old index entry, heap visibility checks determine whether the tuple belongs to the current snapshot, depending on index mechanics and visibility map usage.

### 16.1. Heavy DELETEs Do Not Automatically Shrink Indexes Immediately

After a large `DELETE`:

- The table retains free areas / uncleaned tuples.
- Indexes can retain entries awaiting cleanup.
- `VACUUM` frees space **for reuse**.
- Files on the filesystem do not automatically shrink after every `DELETE`.

Thus, "I deleted 90% of rows yet `du -h` is almost unchanged" does not mean the `DELETE` failed.

### 16.2. DROP/TRUNCATE Are Not Synonyms for DELETE

`TRUNCATE` usually removes all table contents much more efficiently than row-by-row `DELETE`, but behaves differently regarding locks, triggers, foreign keys, transactions, and replication. It is unsuitable when deleting **a subset of rows** or when row-level `DELETE` triggers must run.

`DROP TABLE` removes the table structure itself—completely different from `DELETE`.

Never replace a `DELETE` process with `TRUNCATE`/`DROP` just to reclaim disk space if business requirements forbid it.

---

## 17. Pruning: Cleaning Old Versions Directly on Heap Pages

PostgreSQL can perform **page pruning** to clean/collapse unneeded tuple versions on heap pages, especially HOT chains.

Contrary to the idea that "only `VACUUM` cleans old data," some heap access operations can also trigger pruning when conditions allow.

Example:

```text
Initially:
    Page P: [V1 -> V2 -> V3]

After relevant transactions and snapshots finish:
    V1, V2 no longer needed

Page pruning:
    Can free/collapse the chain and slots as needed
    to reach V3 efficiently and reuse space
```

### 17.1. Pruning Does Not Replace VACUUM

Pruning focuses on page-level tuple chains and in-place space reuse. `VACUUM` also handles broader responsibilities:

- Cleaning up dead tuples.
- Cleaning up index entries when appropriate.
- Updating free space / visibility maps.
- Performing necessary freezing.
- Maintaining relation-wide metadata.

Therefore, never disable autovacuum thinking "pruning takes care of it."

### 17.2. Pruning Makes n_dead_tup Hard to Match Directly

A page can be pruned before a full-table `VACUUM`. Combined with statistics lag, this means the dead tuple counter is not an exact, real-time count of physical dead tuples sitting on pages.

---

## 18. VACUUM: Reclaiming Reusable Space

Regular `VACUUM`'s primary goal is to clean up unneeded versions, make space reusable, support query efficiency, and manage transaction age.

In the lab database:

```sql
VACUUM (ANALYZE) mvcc_versions_lab.orders;
```

**Note:** regular `VACUUM` **cannot run inside an explicit transaction block** (`BEGIN ... VACUUM ... COMMIT`). Run it in an autocommit session or via your client's corresponding mode.

### 18.1. What Does Regular VACUUM Do?

Conceptually:

1. Determines which row versions can be safely cleaned under MVCC.
2. Cleans heap and index entries as needed.
3. Makes space inside the relation reusable.
4. Updates free space and visibility maps.
5. Freezes old transaction metadata where appropriate.
6. With `ANALYZE`, updates planner statistics.

The goal of ordinary `VACUUM` is **continuous maintenance**, not rewriting the entire table to minimal disk size.

### 18.2. VACUUM Usually Does Not Return All Disk Space to the OS

Suppose a table once held 100 million rows, and 90 million were deleted.

Even after `VACUUM` cleans successfully:

- Empty pages in the **middle of the file** are typically kept for future `INSERT`/`UPDATE` reuse.
- PostgreSQL can truncate trailing empty pages at the end of the file under suitable conditions, but do not expect every empty page to shrink the file immediately.
- Indexes also follow their own reuse/cleanup strategies.

If reclaiming most filesystem space is mandatory, evaluate planned rewrite/rebuild approaches rather than assuming ordinary `VACUUM` will suffice.

### 18.3. How Does VACUUM FULL Differ?

`VACUUM FULL` **rewrites** the table to compact physical space and normally requires an **`ACCESS EXCLUSIVE` lock** on the table; it can disrupt concurrent access, generate heavy I/O and WAL, and require extra temporary disk space during the rewrite.

Use it only when:

- There is clear evidence of severe table bloat and real space reclamation is needed.
- An appropriate maintenance window exists.
- Locks, free disk space, replication, and backups have been evaluated.
- Alternative approaches have been weighed.

Never run `VACUUM FULL` after every large `DELETE` as default maintenance.

### 18.4. ANALYZE Is Not Garbage Collection

`ANALYZE` updates data distribution statistics for the planner. It does **not replace** `VACUUM`'s dead-tuple cleanup.

```sql
ANALYZE mvcc_versions_lab.orders;
```

helps the planner after major data changes, but running `ANALYZE` does not make dead tuples disappear.

---

## 19. Autovacuum: Background Maintenance

PostgreSQL includes **autovacuum** to run `VACUUM` and `ANALYZE` automatically based on write activity, estimated tuple counts, and configuration parameters.

It is essential for write-active tables—never treat it as an optional job you can safely turn off.

### 19.1. Why Is Autovacuum Necessary?

Without proper maintenance:

- Dead tuples accumulate.
- Heap and indexes risk bloat.
- `SELECT`s must inspect many useless tuples.
- New writes work against inefficient pages/indexes.
- Transaction IDs age, risking wraparound.
- Tables can be forced into protective modes if XID age grows too large.

Autovacuum keeps these risks under control in normal operations.

### 19.2. What Do Trigger Thresholds Roughly Look Like?

Simplified idea for certain vacuum triggers:

```text
Estimated dead tuples threshold
  ~ autovacuum_vacuum_threshold
    + autovacuum_vacuum_scale_factor * estimated_row_count
```

On very large tables, even a small scale percentage can correspond to millions of dead tuples.

Note that this formula is an **introductory model**. Modern PostgreSQL includes additional thresholds/conditions for `INSERT`s, freezing, and caps like maximum thresholds; do not treat it as the complete scheduler algorithm across all versions.

### 19.3. Per-Table Configuration

Illustrative example of per-table autovacuum options:

```sql
ALTER TABLE mvcc_versions_lab.orders SET (
    autovacuum_vacuum_scale_factor = 0.05,
    autovacuum_analyze_scale_factor = 0.03
);
```

These values are **lab examples**, not a universal production recommendation.

Setting thresholds too low increases background vacuum activity; setting them too high lets dead tuples pile up. Always evaluate table scale, `UPDATE`/`DELETE` rate, free space, I/O, replication, and real statistics.

### 19.4. Autovacuum Can Fall Behind

An `UPDATE` job generating dead tuples very rapidly can outpace autovacuum. That does not mean autovacuum is broken:

- Worker slots are limited.
- The table may be locked or busy with conflicting operations.
- The system may lack I/O or CPU capacity.
- Long transactions may be holding snapshots.
- Threshold/cost settings may be poorly tuned.

Investigate the cause instead of reflexively running `VACUUM FULL` or disabling autovacuum.

---

## 20. Why Do Long Transactions Retain Old Rows?

MVCC can only clean versions **no longer needed by relevant snapshots**. A long-running transaction can hold a very old snapshot, preventing PostgreSQL from reclaiming tuples that transaction might still need to read.

Example:

```text
10:00  Session A starts REPEATABLE READ
10:01  Session A takes snapshot, sees V1
10:02  Session B UPDATE -> V2, COMMIT
10:03  Session C UPDATE -> V3, COMMIT
10:04  Session D UPDATE -> V4, COMMIT
...
11:00  Session A is still open and still needs old snapshot
```

If A must be able to see V1, the system cannot simply discard all old versions and keep only V4.

### 20.1. Idle in Transaction Can Be Dangerous

An application sometimes:

1. Opens a transaction.
2. Runs a `SELECT`.
3. Waits for another HTTP request, user input, or an external API call.
4. Forgets to `COMMIT`/`ROLLBACK`.

The session sits in `idle in transaction`, holding transactions, snapshots, or locks depending on context and obstructing `VACUUM`.

### 20.2. Viewing Long Transactions With pg_stat_activity

With appropriate monitoring privileges:

```sql
SELECT
    pid,
    application_name,
    state,
    xact_start,
    backend_xmin,
    wait_event_type,
    wait_event,
    now() - xact_start AS transaction_age,
    left(query, 120) AS query_preview
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

`backend_xmin` can reveal the snapshot/visibility horizon held by that backend. Not every long transaction holds the same kind of horizon or has a non-NULL `backend_xmin`.

**Never terminate backends automatically** just because `xact_start` looks old: identify the owner, workload, rollback impact, and operational authorization first. Distinguish legitimate long queries, backup jobs, migrations, and hung clients.

### 20.3. Settings Protecting Against Idle Transactions

PostgreSQL has settings such as `idle_in_transaction_session_timeout` to limit sessions sitting idle inside a transaction.

Depending on the application, this timeout can be helpful, but it can also roll back transactions not designed to handle unexpected disconnects. Never enable it without checking the application, connection pool, and retry logic.

---

## 21. Replication Can Also Hold Back Old Versions

It is not only client transactions on the primary that can restrict cleanup.

Replication mechanisms, logical decoding, or feedback from standbys can retain transaction/tuple horizons needed to keep data readable or decodable.

### 21.1. Replication Slots

On the primary, inspect:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    catalog_xmin,
    restart_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

Columns like `xmin` and `catalog_xmin` reflect transaction horizons the slot must retain for certain data types depending on slot type and version.

Distinguish two effects:

- A slot can retain **WAL** via `restart_lsn`, causing `pg_wal` to grow.
- Certain slot/decoding retention horizons can restrict heap tuple or catalog tuple cleanup.

**Not every slot retains every dead tuple of every table.** Check slot type, horizon values, and the actual consumer's state.

### 21.2. hot_standby_feedback

When a physical standby uses `hot_standby_feedback`, it reports its oldest snapshot needs back to the primary to prevent the primary from removing versions standby queries still need.

Trade-off:

- Can reduce recovery conflicts/cancellations for long queries on the standby.
- Can cause the primary to retain dead tuples longer, increasing bloat.

Do not toggle `hot_standby_feedback` based on a single KPI, because it affects both standby read workloads and primary cleanup.

### 21.3. Why Can Replica Lag and Dead Tuples Be Related?

A slow consumer can:

- Retain WAL.
- Retain horizons needed for logical decoding.
- Exert indirect pressure via feedback/snapshots.
- Lead to storage and `VACUUM` pressure under specific conditions.

However, **replication lag does not directly equal growing dead tuples**. Measure transaction horizons, vacuum stats, slots, and index/table status to pinpoint root causes.

---

## 22. Transaction ID Wraparound and Freezing

PostgreSQL uses transaction IDs with a finite ID space and age-comparison logic. If a system fails to freeze tuples carrying very old transaction info, future transaction ID reuse could corrupt visibility.

That is why **`VACUUM` also has the job of preventing XID wraparound**, not just cleaning dead tuples.

### 22.1. What Is Freezing?

For sufficiently old committed versions meeting criteria, PostgreSQL updates metadata via freezing so they continue being recognized as validly committed even as transaction IDs wrap around.

You do not need to memorize internal bit layouts; understand that:

- Even long-lived live tuples need periodic metadata maintenance.
- A table with few `UPDATE`/`DELETE`s still needs `VACUUM` for freezing.
- Disabling autovacuum or leaving very old transactions open creates serious risk.

### 22.2. Operational Signals

Relevant columns/functions:

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    age(c.relfrozenxid) AS xid_age
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname = 'mvcc_versions_lab'
ORDER BY xid_age DESC;
```

`age(relfrozenxid)` is an indicator of transaction ID age related to a table's freeze state. It is not calendar age in days or hours.

Parameters such as `autovacuum_freeze_max_age` govern anti-wraparound maintenance, though there is no single universal "safe" threshold outside version, resource, and workload context.

### 22.3. Never Disable Anti-Wraparound Autovacuum

Some PostgreSQL versions trigger anti-wraparound autovacuum even when normal autovacuum is disabled on a table. Never rely on that as an operational strategy.

Letting a system approach wraparound triggers strict protective modes and write outages. Prevention via monitoring and routine `VACUUM` is always far easier than emergency recovery when it is too late.

---

## 23. Measuring UPDATE, DELETE, and HOT With pg_stat_user_tables

In PostgreSQL, `pg_stat_user_tables` is the practical starting point.

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
WHERE schemaname = 'mvcc_versions_lab'
  AND relname = 'orders';
```

### 23.1. Explaining the Columns

| Column | How to Read It |
| --- | --- |
| `n_tup_ins` | Count of `INSERT`ed tuples recorded in stats |
| `n_tup_upd` | Count of `UPDATE`d tuples recorded in stats |
| `n_tup_del` | Count of `DELETE`d tuples recorded in stats |
| `n_tup_hot_upd` | Number of `UPDATE`s that used HOT |
| `n_live_tup` | Estimated number of live tuples |
| `n_dead_tup` | Estimated number of dead tuples |
| `last_vacuum` | Most recent manual `VACUUM`, if any |
| `last_autovacuum` | Most recent autovacuum, if any |
| `vacuum_count` | Total manual `VACUUM` counter |
| `autovacuum_count` | Total autovacuum counter |

These are **system statistics**, not an exact transactional audit log. They can lag, be reset, and reflect concurrent writes from multiple sessions.

### 23.2. Calculating the HOT Ratio

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    ROUND(
        100::NUMERIC * n_tup_hot_upd
          / NULLIF(n_tup_upd, 0),
        2
    ) AS hot_percent
FROM pg_stat_user_tables
WHERE schemaname = 'mvcc_versions_lab'
  AND relname = 'orders';
```

`NULLIF(n_tup_upd, 0)` avoids division by zero when no `UPDATE`s have occurred yet.

A low HOT ratio is not automatically a bug: if the workload intentionally changes indexed columns, HOT cannot apply to those `UPDATE`s. Conversely, a high HOT ratio does not guarantee zero dead tuples or zero WAL.

### 23.3. Checking Live Data With COUNT

```sql
SELECT COUNT(*) AS visible_orders
FROM mvcc_versions_lab.orders;
```

`COUNT(*)` depends on the `SELECT`'s snapshot. It does not count invisible old versions as separate business rows.

Do not compare `COUNT(*)` directly with `n_live_tup + n_dead_tup` expecting an exact arithmetic match: one is a snapshot-consistent visible row count, while the other comes from statistical estimates.

### 23.4. Statistics Refresh on Their Own Mechanism

If stats right after DML do not change as expected, it may be due to:

- Stats reporting/flushing intervals.
- Cached session statistics snapshots.
- Uncommitted statements/transactions.
- `VACUUM` having already cleaned up.
- Other concurrent writers modifying the table.
- Stats having been reset.

```sql
SELECT pg_stat_clear_snapshot();
```

clears the session's cached stats snapshot per that function's behavior. It does not turn `n_dead_tup` into an exact real-time count.

---

## 24. Observing Table and Index Sizes

Use size functions:

```sql
SELECT
    pg_size_pretty(
        pg_relation_size('mvcc_versions_lab.orders'::REGCLASS)
    ) AS heap_main_size,

    pg_size_pretty(
        pg_table_size('mvcc_versions_lab.orders'::REGCLASS)
    ) AS table_size,

    pg_size_pretty(
        pg_indexes_size('mvcc_versions_lab.orders'::REGCLASS)
    ) AS all_indexes_size,

    pg_size_pretty(
        pg_total_relation_size('mvcc_versions_lab.orders'::REGCLASS)
    ) AS total_relation_size;
```

Distinguish:

- `pg_relation_size` measures the main fork of the relation by default.
- `pg_table_size` measures table storage plus associated forks as defined.
- `pg_indexes_size` is the total size of associated indexes.
- `pg_total_relation_size` is table plus indexes.

### 24.1. Understanding Bloat

**Bloat** is a mismatch between physical space used and actual useful data. A large file **is not automatically bloat**, since it may hold many live rows or free space intended for imminent reuse.

Signals to inspect together:

- Table/index size growing while live row count stays flat.
- High `UPDATE`/`DELETE` rates.
- Persistently high dead tuple estimates.
- Index scans / table scans getting slower.
- `VACUUM` falling behind.
- Long transactions holding snapshots.
- Workload heavy on non-HOT `UPDATE`s.

Diagnosing bloat accurately may require specialized tools/extensions and page density / free-space analysis, not `pg_total_relation_size` alone.

### 24.2. pgstattuple Is an Optional Advanced Tool

The `pgstattuple` extension provides detailed measurements of live tuples, dead tuples, and free space via scanning. Installing it requires privileges and incurs scan overhead.

Example **only to run if the extension is already permitted/installed and operationally needed**:

```sql
SELECT *
FROM pgstattuple('mvcc_versions_lab.orders');
```

Do not run it continuously on huge tables during peak hours. It is an advanced measurement tool, not required for this lab.

---

## 25. EXPLAIN ANALYZE on UPDATE/DELETE: A Mandatory Safety Check

`EXPLAIN (ANALYZE, BUFFERS, WAL)` shows rows processed, page buffers, WAL records, and execution time of a DML statement.

**Critical warning:** When `ANALYZE` is included, PostgreSQL **actually executes the `UPDATE`/`DELETE`/`INSERT`**.

In the lab, wrap it in a transaction and roll back:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE mvcc_versions_lab.orders
SET note = note || '-test'
WHERE order_id BETWEEN 101 AND 106;

ROLLBACK;
```

Or:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
DELETE FROM mvcc_versions_lab.orders
WHERE status = 'CANCELED';

ROLLBACK;
```

### 25.1. What to Look For?

A plan can include lines like:

```text
Update on orders ...
  Buffers: shared hit=..., dirtied=..., written=...
  WAL: records=..., fpi=..., bytes=...
  -> ...
Planning Time: ...
Execution Time: ...
```

The `...` placeholders here illustrate structure only; they are not measurements from a real system.

Check:

- Actual rows affected.
- Scan method used to locate rows.
- `Buffers`: buffer hits, dirtied, and written pages.
- `WAL`: record count, full-page images, and bytes generated by the statement.
- Execution time.
- Correlate with `pg_stat_user_tables` during extended analysis.

### 25.2. ROLLBACK Does Not Erase the Cost of the Test

Even though logical data reverts, the test `UPDATE`/`DELETE` still generates:

- WAL.
- Dirty buffers.
- Tuple versions/metadata needing cleanup.
- External side effects if triggers are non-transactional.
- Consumed sequence values.

Therefore, practice on a **test database**; never run rolled-back DML experiments in production thinking "it changes nothing."

### 25.3. Never Conclude From a Single Run

`EXPLAIN` results are affected by:

- Table size and cache warmth.
- Number of indexes.
- Full-page images right after a checkpoint.
- HOT vs. non-HOT behavior.
- Tuple width.
- Concurrent transactions.
- Lock waits, CPU, disk, WAL flush, and replication.
- Whether `VACUUM`/pruning has occurred yet.

To compare two designs, use equivalent test conditions and multiple runs; this lesson teaches the tools rather than prescribing fixed benchmark numbers.

---

## 26. A Clear Experiment: Updating note Multiple Times

If you reset the lab and run several `UPDATE`s on one row:

```sql
BEGIN;

UPDATE mvcc_versions_lab.orders
SET note = 'v2'
WHERE order_id = 105;

UPDATE mvcc_versions_lab.orders
SET note = 'v3'
WHERE order_id = 105;

UPDATE mvcc_versions_lab.orders
SET note = 'v4'
WHERE order_id = 105;

SELECT order_id, note
FROM mvcc_versions_lab.orders
WHERE order_id = 105;

COMMIT;
```

Inside the transaction, the `SELECT` result is `v4`.

Intermediate versions created inside the same transaction may not need to stay long once visibility and cleanup run, but that does not mean the earlier `UPDATE`s were free.

### 26.1. What If More Indexes Are Added?

If you add an index depending on `note`, every `note` change affects that index and HOT eligibility. That can increase write amplification and bloat under continuous note-update workloads.

However, indexing `note` can be essential if APIs genuinely query by `note`; the trade-off must balance read workloads and search requirements.

### 26.2. Collapsing Three UPDATEs in One Transaction Into One UPDATE

Three `UPDATE`s incur triple the heap/WAL/trigger work. If the application can **coalesce intended changes** to write only the final state, it is often worth considering:

```sql
UPDATE mvcc_versions_lab.orders
SET note = 'v4'
WHERE order_id = 105;
```

However, if `v2`/`v3`/`v4` are meaningful business states requiring separate auditing or events, you cannot skip them merely to reduce write volume.

---

## 27. Bulk DELETEs and Transaction Limits

A statement like:

```sql
DELETE FROM mvcc_versions_lab.orders
WHERE status = 'CANCELED';
```

affects only a few rows in the lab table. On a multi-million-row table, deleting a massive batch in one transaction can:

- Create huge numbers of dead tuples.
- Generate substantial WAL.
- Increase `VACUUM`/index cleanup work.
- Hold locks and transactions open for a long time.
- Cause logical/physical replication lag.
- Pressure storage / `pg_wal`.
- Disrupt live application workloads.

### 27.1. Batched DELETE

A PostgreSQL pattern using a CTE:

```sql
WITH batch AS (
    SELECT order_id
    FROM mvcc_versions_lab.orders
    WHERE status = 'CANCELED'
    ORDER BY order_id
    LIMIT 100
)
DELETE FROM mvcc_versions_lab.orders AS o
USING batch AS b
WHERE o.order_id = b.order_id
RETURNING o.order_id;
```

In an application, run each batch in its **own transaction**, stopping when zero rows remain; record job progress and monitor metrics.

**Do not assume batching automatically reduces total WAL bytes or dead tuples.** Batching helps control load spikes, lock duration, pause/resume capability, and application impact.

### 27.2. Do Not Assume Direct LIMIT in DELETE

Syntax such as:

```sql
-- Not standard direct DELETE ... LIMIT syntax in PostgreSQL.
DELETE FROM mvcc_versions_lab.orders
WHERE status = 'CANCELED'
LIMIT 100;
```

is not supported in standard PostgreSQL. Use a CTE/subquery selecting keys and then delete by key as shown.

### 27.3. Concurrency and Batching

When multiple workers delete concurrently:

- Two workers could pick the same rows before locking.
- Lock waits occur.
- Rows could change status between the batch `SELECT` and `DELETE`.
- Deletion authorization and idempotency must be ensured.
- `FOR UPDATE SKIP LOCKED` may be needed for multi-worker architectures.

If using `SKIP LOCKED`, remember it intentionally skips locked rows and is not suitable for every consistency/reconciliation goal.

### 27.4. How Does Partitioning Help?

For time-aged data, **partitioning** allows dropping or detaching old partitions under a retention policy without row-by-row `DELETE`s.

However, detaching/dropping partitions involves locking, schema, foreign keys, replication, backups, and application rules. It is a long-term design choice, not an instant `DELETE` drop-in for every table.

---

## 28. VACUUM Does Not Fix Application Concurrency Bugs

MVCC enables concurrent reads and writes, yet does not automatically make every business transaction correct.

### 28.1. Lost Updates and Write Conditions

Suppose two services read `amount=100` and compute new values in the application:

```text
A reads 100, decides to write 120
B reads 100, decides to write 130

A UPDATE SET amount=120
B UPDATE SET amount=130
```

Depending on ordering/locking/isolation, the final result can fail to reflect both updates. Solutions include:

- Atomic relative `UPDATE`s: `SET amount = amount + 10`, when business logic is a delta addition.
- Optimistic concurrency with a version column: `WHERE version = expected_version`.
- Row locks and transactions.
- Appropriate isolation such as `SERIALIZABLE` with retries.
- Constraints preventing out-of-range values.

`VACUUM` plays zero role in detecting or fixing lost updates.

### 28.2. UPDATE ... RETURNING

A useful pattern:

```sql
UPDATE mvcc_versions_lab.orders
SET amount = amount + 10
WHERE order_id = 101
RETURNING order_id, amount, status;
```

It returns the **post-UPDATE values** of the rows actually modified, informing the application of the exact affected count and resulting values in that transaction.

However, `RETURNING` does not replace checking transaction outcomes, constraints, and concurrency. Never use `ctid` as a durable version token across multiple requests.

### 28.3. Optimistic Locking With Application-Managed Version

A business table with `row_version BIGINT NOT NULL` can use:

```sql
-- Illustrative example for a table with a row_version column.
UPDATE application_orders
SET status = 'PAID',
    row_version = row_version + 1
WHERE order_id = 101
  AND row_version = 7
RETURNING order_id, row_version;
```

If 0 rows are returned, one possibility is that the version changed due to a concurrent update. The application must distinguish missing rows, insufficient permissions, and version conflicts per contract.

Never use `xmin` as a default application version; system columns are internal with a different lifecycle than a business version column.

---

## 29. How Do Index-Only Scans and the Visibility Map Relate?

Some queries can use an **index-only scan**, reading needed columns from the index when the index covers them. Under PostgreSQL MVCC, however, an index entry alone usually does not confirm whether a heap tuple is visible to a snapshot.

PostgreSQL maintains a **visibility map** marking heap pages known to be all-visible to relevant snapshots, letting index-only scans skip many heap fetches.

### 29.1. UPDATE/DELETE Affects All-Visible

When an all-visible page is modified, its visibility status must be cleared. That forces index-only scans to revisit the heap for visibility checks until `VACUUM`/relevant mechanisms mark it all-visible again.

Consequently, a heavy `UPDATE` workload can slow down read queries even when a covering index exists.

### 29.2. Using EXPLAIN on SELECT

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM mvcc_versions_lab.orders
WHERE order_id BETWEEN 101 AND 106;
```

If the planner chooses an Index Only Scan, you can observe the `Heap Fetches` metric. On a 6-row lab table, however, a sequential scan is cheaper, so not seeing an Index Only Scan is completely normal.

### 29.3. All-Visible Does Not Mean "Zero Physical Old Versions Remain"

The visibility map is metadata letting the planner/executor optimize visibility checks and vacuuming under PostgreSQL rules. Never interpret an all-visible bit as "the disk contains zero bytes from any old version."

---

## 30. WAL and Replicas: What Else Do Row Versions Affect?

On normal logged tables, `UPDATE`/`DELETE` also generate **WAL** for crash recovery. Physical standbys must replay WAL changes for heap and indexes. Logical replication decodes row changes per publication and replica identity.

### 30.1. Physical Replicas

Physical streaming replication receives and replays WAL. If the primary runs heavy `UPDATE`s:

- WAL generation rate rises.
- Standbys need more CPU/I/O to replay.
- Asynchronous standbys can read older state until replay reaches the corresponding LSN.

Replica lag is not measured by dead tuple counts, though both pressures can arise together during a heavy write burst.

### 30.2. Logical Replicas

In logical replication, `UPDATE`/`DELETE` typically need target-row identification to apply changes. A primary key is usually the best choice for **replica identity**; lacking a suitable key may require alternative settings with extra WAL/apply cost.

Never set `REPLICA IDENTITY FULL` to "fix VACUUM." That setting serves logical replication, not dead-tuple cleanup.

### 30.3. Deleted on Primary, Yet Replica Still Sees the Row?

This can happen under asynchronous replication if the standby has not replayed the `DELETE` yet. That is **replication lag**, distinct from Session A on the primary holding an old `REPEATABLE READ` snapshot.

When investigating, distinguish:

1. Reading an old snapshot on the same primary.
2. Reading a replica that hasn't caught up.
3. A `DELETE` transaction that hasn't `COMMIT`ted yet.
4. A `DELETE` that matched zero rows.
5. Application caching.
6. Soft delete rather than physical `DELETE`.

Diagnose at the right layer rather than blaming everything on "PostgreSQL hasn't cleaned dead tuples."

---

## 31. Soft Delete Differs From Physical DELETE Under MVCC

Many systems use:

```sql
UPDATE orders
SET deleted_at = clock_timestamp()
WHERE order_id = 101;
```

This is an application-level **soft delete**. The record still exists logically in the table, merely marked inactive.

From PostgreSQL's standpoint, that statement is an **`UPDATE`**, not a `DELETE`:

- Creates a new tuple version under MVCC.
- Generates an old version requiring cleanup.
- If `deleted_at` is in a partial or expression index, it can affect HOT eligibility.
- Queries must filter `deleted_at IS NULL` when business logic requires only active rows.

Hypothetical table example:

```sql
SELECT *
FROM orders_with_soft_delete
WHERE deleted_at IS NULL;
```

This is illustrative; `orders_with_soft_delete` was not created in the lab.

### 31.1. Why Doesn't Soft Delete Reduce Size Automatically?

Soft delete intentionally **keeps the active record** for auditing/recovery; it does not remove data from the active dataset. In fact, it adds an extra old version from the `UPDATE`.

If retention requires permanent removal after 90 days, build a separate purge job and evaluate MVCC/`VACUUM`, backups, replicas, and legal requirements.

---

## 32. Distinguishing VACUUM, REINDEX, and VACUUM FULL

| Tool | Primary Goal | Impact and Notes |
| --- | --- | --- |
| `VACUUM` | Clean dead tuples, maintain space reuse/visibility/freezing | Generally compatible with concurrent workloads; does not shrink the whole file by default |
| `VACUUM (ANALYZE)` | `VACUUM` plus update planner stats | Helpful after major changes, though still has cost |
| `ANALYZE` | Update planner statistics | Does not replace dead tuple cleanup |
| `VACUUM FULL` | Rewrite to compact the table | Strong lock, high resource cost, requires maintenance planning |
| `REINDEX` | Rebuild indexes | Targets index structure, has its own cost/locks |
| `REINDEX CONCURRENTLY` | Rebuild indexes aiming to reduce blocking locks when supported | Has specific operational rules and limits |
| `CLUSTER` | Rewrite/physically reorder table by chosen index | Heavy locks/cost, not a `VACUUM` substitute |
| `pg_repack` (external extension) | Can assist online-style rewrite/repack under conditions | Needs extension, privileges, disk space, and planning |

**There is no "single best garbage-collection button for every table."** The right tool depends on the goal: cleaning tuples, reclaiming disk space, fixing index bloat, or refreshing planner stats.

### 32.1. Start With Less Invasive Methods

If a table slows down after heavy `UPDATE`/`DELETE`s:

1. Identify the true cause via stats, plans, and sizes.
2. Check for long transactions or replication slots.
3. Verify autovacuum is actually running.
4. Evaluate HOT ratios and index dependencies.
5. Only then consider rewrites/`REINDEX`/`VACUUM FULL` as needed.

Skipping investigation and jumping straight to `VACUUM FULL` can cause downtime without fixing root causes such as an application running needless `UPDATE`s continuously.

---

## 33. Investigating: 80% of Rows Deleted, Yet Size Did Not Shrink

Suppose a table was 200 GB, and after a `DELETE` campaign only 20% of logical rows remain, yet the file is still nearly 200 GB.

Analysis steps:

### 33.1. Confirm the DELETE Actually COMMITted

```sql
SELECT COUNT(*) FROM mvcc_versions_lab.orders;
```

In a real environment, verify the `DELETE` predicate, transaction outcome, and connection source. A client with an uncommitted transaction does not count as completed deletion.

### 33.2. Check Estimated Dead Tuples

```sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum
FROM pg_stat_user_tables
WHERE schemaname = 'mvcc_versions_lab';
```

If dead tuples are high, inspect whether autovacuum/`VACUUM` is cleaning them.

### 33.3. Check Long-Lived Snapshots

```sql
SELECT
    pid, state, xact_start, backend_xmin,
    now() - xact_start AS age
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Check whether any old transaction, slot, or standby feedback is pinning the horizon.

### 33.4. Check Table and Index Sizes

```sql
SELECT
    pg_size_pretty(
        pg_table_size('mvcc_versions_lab.orders'::REGCLASS)
    ) AS table_size,
    pg_size_pretty(
        pg_indexes_size('mvcc_versions_lab.orders'::REGCLASS)
    ) AS index_size;
```

If `VACUUM` cleaned tuples yet the file stays large, space has likely been **marked reusable** inside the file without being returned to the filesystem.

### 33.5. Make a Decision

- If heavy `INSERT`s are coming soon, internal reuse can be very beneficial.
- If disk is nearly full and data volume will remain small, a planned rewrite/repack may be needed.
- If bloat is concentrated in indexes, evaluate index maintenance/rebuilds.
- If old snapshots block cleanup, fix transaction lifecycles.
- If logical retention/backups hold data by policy, never try to bypass policy with `VACUUM`.

---

## 34. Investigating: Continuous UPDATEs and Rising CPU/I/O

A table has 5 million rows, and the application updates `last_seen_at` multiple times per minute for many users.

If `last_seen_at` is indexed, every update affects indexes and HOT. Even if unindexed, full pages still yield low HOT ratios.

### 34.1. Questions to Ask

- Does the application truly need to persist every event, or can updates be coalesced/debounced?
- Is `last_seen_at` used for searching/sorting or only display?
- Do expression indexes or partial indexes depend on it?
- What is the HOT ratio?
- What is the current `fillfactor`?
- Are long transactions or logical slots pinning horizons?
- Is autovacuum keeping up?
- Are table/index sizes growing abnormally?

### 34.2. Design Options

Consider:

- Updating only when the new timestamp differs from the stored one by a business threshold.
- Batching/coalescing multiple events into one update if exact per-event timestamps aren't required.
- Moving high-churn columns into a separate table to isolate write workloads.
- Reviewing indexes touching frequently updated columns.
- Tuning `fillfactor` and vacuum thresholds after benchmarking.
- Switching to an append-only event model if full history is needed.

There is no single answer: if auditing requires recording every single event, coalescing `UPDATE`s would lose required data; in that case use an append-only log/event design instead of dropping writes.

---

## 35. Investigating: Slow UPDATE When Dead Tuples Are Not High

A slow `UPDATE` is not necessarily caused by bloat.

Possible causes include:

- Waiting on row locks from another transaction.
- Expensive constraints, foreign keys, or triggers.
- Missing index on `WHERE`, causing large scans.
- Slow WAL writes or commit flushes.
- Slow synchronous standbys.
- Saturated disk I/O.
- Non-HOT index maintenance.
- Large columns / TOAST overhead.
- Frequent transaction retries.
- Resource contention in the application.

### 35.1. Observing Lock Waits

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 150) AS query_preview
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start NULLS LAST;
```

This is a starting point, not the full diagnosis. If `wait_event_type = 'Lock'`, trace the blocker under appropriate privileges—never treat `VACUUM` as a cure for lock waits.

### 35.2. Separating Statement Time From Commit Time

An `UPDATE` with low `Execution Time` in `EXPLAIN` can still have slow API latency due to:

- Waiting on `COMMIT` flush.
- Synchronous replication acknowledgment.
- Network latency.
- Client transaction management.
- Lock acquisition in an earlier/later step.

Measure the entire path before changing indexes, HOT settings, or autovacuum.

---

## 36. Common Mistakes and Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| "UPDATE overwrites the old tuple directly." | PostgreSQL normally creates a new tuple version under MVCC |
| "DELETE erases all bytes from disk immediately." | `DELETE` marks the tuple per MVCC; cleanup happens later |
| "After DELETE, no transaction can see the row." | Valid older snapshots can still see the prior version |
| "Every old row is immediately a cleanable dead tuple." | It may still be needed by an older snapshot |
| "Dead tuples mean DELETE failed." | Dead tuples are a normal consequence of MVCC |
| "xmin is row creation timestamp." | `xmin` is transaction ID metadata, not a timestamp |
| "Non-zero xmax definitely means a committed DELETE." | `xmax` also tracks row locks and transaction states |
| "ctid is a stable ID." | `ctid` is a tuple version's physical location and can change |
| "Selecting system columns shows all versions." | `SELECT` normally returns only versions visible to its snapshot |
| "HOT UPDATE creates no new version." | HOT still creates a new heap tuple version |
| "HOT means zero WAL." | HOT still generates WAL and heap work |
| "Unindexed columns are guaranteed to be HOT." | Same-page free space and index dependencies also apply |
| "Only index keys affect HOT." | `INCLUDE`, expressions, and partial predicates also affect HOT |
| "Changing one indexed column updates only one index." | Non-HOT updates may insert entries across multiple indexes |
| "UPDATE SET x = x is free." | It can still create tuples, WAL, and trigger work |
| "VACUUM removes deleted data from every snapshot." | `VACUUM` must respect snapshots that still need it |
| "VACUUM must run inside BEGIN/COMMIT." | Regular `VACUUM` cannot run inside an explicit transaction block |
| "VACUUM always shrinks files back to the OS." | It primarily frees space for internal reuse within the relation |
| "VACUUM FULL is just a faster VACUUM." | `FULL` rewrites the table with strong locks and heavy resources |
| "ANALYZE cleans dead tuples." | `ANALYZE` updates planner statistics |
| "With pruning, autovacuum isn't needed." | `VACUUM` also handles index cleanup, freezing, and relation maintenance |
| "n_dead_tup is an exact tuple count." | It is a lagging statistical estimate |
| "n_tup_upd equals live row count." | It is a cumulative update counter, not live rows |
| "Leaving a transaction open a long time hurts nobody." | It can hold snapshots/locks and block cleanup |
| "Replica lag always increases dead tuples." | Mechanisms vary; inspect slots, feedback, and horizons |
| "An inactive replication slot is harmless." | It can retain WAL and required horizons depending on slot type |
| "No DELETEs means no freezing needed." | Long-lived tuples still require XID age maintenance |
| "ROLLBACK causes zero writes or garbage." | Executed DML still produces tuples, WAL, and cleanup work |
| "EXPLAIN ANALYZE UPDATE does not modify data." | It executes the DML; test safely in a lab |
| "Small row count with huge file is definitely a bug." | It may hold reusable free space or real bloat |
| "Soft delete removes physical rows." | Soft delete is an application-level `UPDATE` |
| "VACUUM fixes lost updates." | Correct concurrency requires transactions, locks/versioning, and constraints |
| "COUNT(*) exactly equals n_live_tup." | `COUNT(*)` reflects a snapshot; `n_live_tup` is an estimate |
| "Fast DML means fast COMMIT." | WAL flush, sync replication, and network can add latency |

---

## 37. Practice Exercises

### Exercise 1 — Sketching the Version Lifecycle

For row `(order_id=101, status='NEW')`, sketch the versions across two sequential `UPDATE`s: first to `PAID`, then changing `note`. Explain which version is visible to a new snapshot vs. an old snapshot.

### Exercise 2 — Reading System Columns

Run:

```sql
SELECT order_id, xmin, xmax, ctid
FROM mvcc_versions_lab.orders
ORDER BY order_id;
```

Then `UPDATE` `note` on row 105 and read again. Why shouldn't `ctid` be used as an application key? Why doesn't `xmax <> 0` prove a committed `DELETE`?

### Exercise 3 — READ COMMITTED Two Sessions

Run the experiment in section 8 with two connections. What does A see before and after B's `COMMIT`? What changes if B has not `COMMIT`ted yet?

### Exercise 4 — REPEATABLE READ Two Sessions

Run the experiment in section 9. Why does A still see `NEW` after B `UPDATE`s and `COMMIT`s? When does A start seeing `PAID`?

### Exercise 5 — DELETE and Snapshots

Have A hold a `REPEATABLE READ` snapshot before B `DELETE`s row 102. Can A see row 102 after B `COMMIT`s? Why isn't `VACUUM` allowed to remove the version A still needs?

### Exercise 6 — ROLLBACK UPDATE

Run `UPDATE note = 'temporary'` then `ROLLBACK`. Why doesn't the rolled-back version become current data? Why can the test still generate WAL and dirty pages?

### Exercise 7 — ROLLBACK DELETE

`DELETE` row 103 inside a transaction and then `ROLLBACK`. Does the row still exist? Distinguish rollback from `VACUUM`.

### Exercise 8 — HOT Candidate

`UPDATE` `note` on row 105. Why can it be HOT? Which two main conditions must hold? Does `fillfactor=80` guarantee 100% HOT?

### Exercise 9 — Indexed Column

`UPDATE` `customer_id` on row 105. Why does HOT eligibility change? Which indexes may need new entries on a non-HOT update?

### Exercise 10 — Partial Index

A table has a partial index `WHERE status='PAID'`. How does updating `status` from `NEW` to `PAID` affect index membership? Why does this differ from updating `note`?

### Exercise 11 — No-Op Update

Write:

```sql
UPDATE mvcc_versions_lab.orders
SET note = note
WHERE order_id = 106;
```

Explain why this can still create a new version and WAL. Rewrite it using `IS DISTINCT FROM` if you only want to update when `note` differs from the target value.

### Exercise 12 — Visible Row Count vs. Dead Tuple Estimate

Compare `COUNT(*)` with `n_live_tup` and `n_dead_tup` from `pg_stat_user_tables`. Why don't those three numbers have to satisfy an exact arithmetic equation at every instant?

### Exercise 13 — HOT Ratio

Compute:

```sql
ROUND(
  100::NUMERIC * n_tup_hot_upd
  / NULLIF(n_tup_upd, 0),
  2
)
```

from `pg_stat_user_tables`. Does a low HOT ratio mean all `UPDATE`s are wrong?

### Exercise 14 — VACUUM

Run several `UPDATE`/`DELETE` statements in the lab, end your transactions, and then run:

```sql
VACUUM (ANALYZE) mvcc_versions_lab.orders;
```

Explain why transactions must finish before `VACUUM` and why the file does not necessarily shrink noticeably.

### Exercise 15 — Autovacuum and Freezing

Explain the two duties: cleaning dead tuples and preventing XID wraparound. Why does a table with very few `UPDATE`/`DELETE`s still require maintenance?

### Exercise 16 — Long-Running Transaction

A `REPEATABLE READ` session holds an old snapshot for an hour while thousands of other `UPDATE`s commit. What can happen to tuple-version reclamation? Which `pg_stat_activity` query helps investigate?

### Exercise 17 — pg_replication_slots

Inspect `xmin`, `catalog_xmin`, and `restart_lsn` from `pg_replication_slots`. Distinguish tuple/catalog retention horizons from the WAL position retained. Why should you never drop a slot without knowing its consumer?

### Exercise 18 — Comparing VACUUM, VACUUM FULL, and REINDEX

What problem does each tool target? Which tools require rewrites/strong locks? When index bloat is large while the heap is not, which option is worth investigating?

### Exercise 19 — EXPLAIN ANALYZE UPDATE

Inside a lab transaction:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE mvcc_versions_lab.orders
SET note = 'changed'
WHERE order_id BETWEEN 101 AND 106;

ROLLBACK;
```

Describe WAL records, FPI, bytes, and `Buffers`. Why shouldn't you run the same test in production just because it ends in `ROLLBACK`?

### Exercise 20 — Batched DELETE

Write a `DELETE` for up to 100 `CANCELED` rows using a key-selecting CTE. Explain per-batch transactions, idempotency, and stopping when no rows remain.

### Exercise 21 — Bloat After Heavy DELETE

A table stays 200 GB after deleting most rows and running `VACUUM`. Give at least four possible explanations and how to test each hypothesis before proposing `VACUUM FULL`.

### Exercise 22 — Index-Only Scan

Why does an index-only scan still care about the visibility map? How can continuous `UPDATE`/`DELETE`s affect `Heap Fetches`?

### Exercise 23 — Soft Delete

A table uses `deleted_at` instead of physical `DELETE`. In MVCC terms, does a soft delete create an old row version or immediately remove the row from the heap? Why can it affect HOT?

### Exercise 24 — Optimistic Concurrency

Design an `UPDATE` with `WHERE row_version = expected_version`. If the `UPDATE` returns 0 rows, how should the application respond? Should `ctid` be used as a durable version token?

### Exercise 25 — Update-Heavy Workload

A table has `last_seen_at` updated dozens of times per minute. Propose a checklist covering index necessity, HOT ratio, `fillfactor`, autovacuum, write coalescing, and audit requirements.

### Exercise 26 — Distinguishing Four "Row Still Visible After DELETE" Cases

Classify:

1. Another session hasn't `COMMIT`ted its `DELETE`.
2. Session A holds an old `REPEATABLE READ` snapshot.
3. The application reads from an async standby lagging in replay.
4. The application performs soft deletes.

Explain why a single `VACUUM` command cannot solve all four.

---

## 38. Checklist for Evaluating UPDATE/DELETE in Real Systems

| Question | What to Verify |
| --- | --- |
| Is the operation an `UPDATE` or `DELETE`? | Creates a new tuple version vs. marks deleted |
| How many rows are actually affected? | `WHERE`, `RETURNING`, row count |
| Are indexed columns modified? | Keys, `INCLUDE`, expressions, predicates |
| Is HOT possible? | No indexed dependencies changed, same heap page |
| Does `fillfactor` fit the workload? | Page free space vs. `UPDATE` rate |
| Are there no-op `UPDATE`s? | `IS DISTINCT FROM` if business rules allow |
| Are there triggers, FKs, or cascades? | Indirect write amplification |
| Are old snapshots still active? | `xact_start` / `backend_xmin` |
| Are transactions sitting idle too long? | Connection pool, timeouts |
| Are replication slots holding horizons? | `xmin` / `catalog_xmin` / `restart_lsn` |
| Is standby feedback enabled? | Tuple retention rules and bloat risk |
| Is dead tuple estimate growing? | `pg_stat_user_tables` |
| Is the HOT ratio meaningful? | `n_tup_hot_upd` / `n_tup_upd`, stats scope |
| Is autovacuum running properly? | `last_autovacuum`, thresholds, logs |
| Is there wraparound risk? | `age(relfrozenxid)`, freeze policy |
| Are tables or indexes growing abnormally? | `pg_table_size`, `pg_indexes_size` over time |
| Can free space in files be reused? | Do not equate free space with OS disk returned |
| Is `VACUUM FULL` needed? | Rewrite, locks, disk, and HA impact |
| Is `REINDEX` needed? | Check index bloat and lock impact |
| Should `DELETE` be batched? | WAL, locks, transactions, restartability |
| Can partition retention be used? | Long-term schema design |
| Is `EXPLAIN` DML safe? | `ANALYZE` executes; lab only |
| Are comparisons fair? | Cache, checkpoints, row count, concurrent writers |
| Are there data consistency issues? | Locks, optimistic versioning, retries |
| Are replicas stale? | Replication lag vs. old snapshots |
| Using soft delete? | Logical `UPDATE` vs. physical `DELETE` |
| Audit/retention requirements? | Never drop required writes or mis-delete history |
| Backups and recovery ready? | PITR/base backups, tested restores |
| Safe abort thresholds defined? | WAL/disk/lag/latency/lock waits |

## Conclusion

In PostgreSQL, `UPDATE` and `DELETE` are best understood through the **MVCC model — multiple row versions coexisting as needed by snapshots**.

- **`UPDATE`** normally creates a new tuple version and marks the old version superseded. Old snapshots can still see the previous version, while newer snapshots see the new version after commit.
- **`DELETE`** marks the existing version as logically deleted. It does not guarantee physical data or index entries disappear instantaneously.
- **An old tuple version** does not automatically equal a **reclaimable dead tuple**. PostgreSQL must protect versions still required by active transactions, snapshots, or replication horizons.
- **HOT updates** reduce index work when modified columns do not affect index dependencies and the new tuple fits on the same heap page. They still create heap versions and WAL.
- **Pruning, `VACUUM`, and autovacuum** clean up old versions, enable space reuse, and prevent XID wraparound. Ordinary `VACUUM` does not shrink every file back to the operating system by default.
- **Long-running transactions**, certain replication retention horizons, and misconfiguration can keep old versions around longer and increase bloat.
- **System columns and statistics** like `xmin`, `xmax`, `ctid`, and `n_dead_tup` are tools for understanding and investigation—not permanent business APIs or exact real-time counters.
- **`UPDATE`/`DELETE` performance** also depends on indexes, triggers, WAL, locks, I/O, replication, and transaction design. Never optimize from a single metric.

When you clearly separate **"no longer visible"**, **"no longer needed by any snapshot"**, and **"reclaimed for reuse"**, you will accurately explain row lifecycles in PostgreSQL, avoid wrong conclusions after `UPDATE`/`DELETE`, and use `VACUUM` and monitoring tools safely and effectively.
