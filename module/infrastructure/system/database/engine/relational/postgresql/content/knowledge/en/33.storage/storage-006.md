# Fillfactor, HOT Updates, and Free Space on Pages in PostgreSQL

A PostgreSQL table can handle millions of updates per day yet still incur substantial unnecessary overhead if every UPDATE has to insert new index entries. A crucial part of storage optimization is understanding **where a row lives on a heap page, how PostgreSQL creates a new row version, and when an UPDATE can become a HOT update**.

Consider a device state table:

- Each device has a stable identifier key.
- The application frequently updates `last_seen`, `status`, and `heartbeat_at`.
- Queries primarily look up devices by `device_id`.
- Some reports filter by `status`.

If an UPDATE only modifies columns not referenced by indexes and the page holding the row still has enough room, PostgreSQL can store the new version on the **same heap page** without adding entries to indexes. This is a **Heap-Only Tuple update (HOT update)**.

Two key factors:

- **Fillfactor**: sets the target fill percentage of heap pages when PostgreSQL writes new tuples, leaving room for future updates.
- **HOT update**: an MVCC optimization allowing a new tuple version to be placed on the same page and avoiding new index entries when necessary conditions are satisfied.

Conceptual diagram:

```text
Heap page
+--------------------------------------------------+
| Page header | line pointers | tuple data         |
|              ^                                    |
|              |                                    |
|         free space                                |
|                                                  |
+--------------------------------------------------+
        |
        +-- UPDATE does not alter indexed columns
        |      + enough space on the same page
        |              |
        |              v
        |          HOT update
        |          - new tuple version on same page
        |          - no new index entries added
        |
        +-- insufficient space or alters indexed column
                       |
                       v
                   Non-HOT update
                   - new tuple version
                   - index maintenance required
```

This lesson belongs to the **Database Engine Relational PostgreSQL** module, **Storage** chapter, focusing on **"Fillfactor, HOT Updates, and Free Space on Pages"**. It progresses from heap page layout and MVCC to choosing fillfactor, monitoring HOT ratio, using the free space map, VACUUM/autovacuum, and verifying behavior with a lab runnable in a practice database.

---

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain heap pages, tuples, line pointers, the page header, and the free space area.
2. Distinguish in-page free space from filesystem free disk space.
3. Explain why an UPDATE in PostgreSQL generally creates a new tuple version under MVCC.
4. Define a HOT update and state the two fundamental conditions for HOT to occur.
5. Explain why HOT updates reduce index maintenance and limit index bloat.
6. Understand HOT chains, root tuples, heap-only tuples, and page pruning.
7. Distinguish a HOT update from an ordinary (non-HOT) UPDATE.
8. Understand the role of table `fillfactor` in reserving free space on heap pages.
9. Distinguish table fillfactor from B-tree index fillfactor.
10. Know why lowering fillfactor does not automatically turn every UPDATE into HOT.
11. Understand the impact of index keys, `INCLUDE` columns, expression indexes, and partial-index predicates on HOT eligibility.
12. Recognize exceptions related to summarizing indexes such as BRIN depending on PostgreSQL version.
13. Use `ALTER TABLE ... SET (fillfactor=...)` and understand its effect on existing data.
14. Distinguish regular VACUUM, VACUUM FULL, CLUSTER, and table rewrite operations.
15. Understand the Free Space Map (FSM) and how it helps find pages with available space.
16. Read `n_tup_upd`, `n_tup_hot_upd`, and compute the HOT update ratio.
17. Use `pg_freespacemap`, `pgstattuple`, and `pageinspect` when diagnostics are needed.
18. Understand why HOT still creates tuple versions, WAL, and vacuum demand.
19. Evaluate trade-offs among page density, table size, read performance, and update performance.
20. Design update-heavy tables keeping frequently updated columns unindexed when appropriate.
21. Tune fillfactor by workload instead of applying one fixed number to every table.
22. Apply fillfactor and HOT considerations to partitioned tables.
23. Verify effectiveness using statistics and realistic workloads rather than observing a single successful UPDATE.

**Scope:** Modern PostgreSQL. Page size is typically 8 KB in standard builds, though it can vary depending on build configuration. Certain HOT optimizations involving summarizing indexes and stats/inspection tools depend on version; verify documentation against your running cluster.

---

## 2. What Is a Heap Page?

PostgreSQL stores rows of an ordinary table in **heap pages**. A relation is divided into fixed-size blocks/pages determined for a given PostgreSQL build.

In common configurations, a page is 8 KB, yet never hard-code this assumption across all tools or environments.

### 2.1. Conceptual Page Structure

A heap page contains:

- **Page header**: page management metadata, LSN, checksum/flags, and boundary offsets.
- **Line pointer array**: items referencing tuples residing on the page.
- **Tuple data area**: bytes of the tuples.
- **Free space**: unused area between the line pointer array and tuple data.

Diagram:

```text
Page start
+------------------------------------------------+
| PageHeaderData                                 |
+------------------------------------------------+
| ItemIdData / line pointer 1                    |
| ItemIdData / line pointer 2                    |
| ItemIdData / line pointer 3                    |
| ...                                            |
+------------------------------------------------+
|                                                |
|              FREE SPACE                        |
|                                                |
+------------------------------------------------+
| Tuple C                                        |
| Tuple B                                        |
| Tuple A                                        |
+------------------------------------------------+
Page end
```

A line pointer is not the row itself. It is a small item helping PostgreSQL locate a tuple inside the page.

### 2.2. What Does a Tuple Contain?

A heap tuple can contain:

- Tuple header.
- Transaction IDs and MVCC metadata.
- Null bitmap when needed.
- Column data.
- Padding/alignment per storage rules.
- Metadata/pointers for large values that may be TOASTed.

Therefore, the actual bytes occupied by a row are not simply the sum of string lengths visible to the application.

### 2.3. What Is Page Free Space Used For?

Free space can be used for:

- INSERTing new tuples.
- Placing a new tuple version on the same page during certain UPDATEs.
- Tuple management operations needing room as appropriate.

For HOT, the critical requirement is that **the new version must fit on the exact same page as the old version**.

### 2.4. Page Free Space Is Not Filesystem Free Space

A table may consume 10 GB on the filesystem while holding hundreds of MB of free space inside its heap pages. PostgreSQL can reuse part of this internal space without shrinking the file.

Conversely, an empty page does not mean the filesystem has reclaimed space for the OS.

### 2.5. `ctid` Is a Tuple Location, Not a Business Key

`ctid` represents a tuple's location within a relation, typically consisting of a block number and an offset number. UPDATE can create a new version at a different location, causing `ctid` to change.

Never use `ctid` as a primary key, business key, or stable identifier across updates.

---

## 3. MVCC: Why Does UPDATE Create a New Tuple Version?

PostgreSQL uses **Multi-Version Concurrency Control (MVCC)**. Rather than overwriting every value of an existing row directly in place, an ordinary UPDATE creates a new version and marks the old version invisible to future snapshots according to transaction visibility rules.

Example:

```sql
CREATE TABLE storage_lab.accounts (
    account_id BIGINT PRIMARY KEY,
    balance NUMERIC(12,2) NOT NULL
);

INSERT INTO storage_lab.accounts
VALUES (1, 1000.00);

UPDATE storage_lab.accounts
SET balance = 900.00
WHERE account_id = 1;
```

Conceptually:

```text
Before UPDATE:
  Tuple version A: balance = 1000

After UPDATE:
  Tuple version A: old version
  Tuple version B: balance = 900

Qualifying older transactions/snapshots may still see A;
newer transactions see B.
```

### 3.1. Not Every Session Sees the Same Version

MVCC lets transactions read consistent snapshots without blocking all readers merely to write a row. Visibility depends on transaction IDs, snapshots, and commit states.

### 3.2. Old Versions Cannot Be Removed Immediately

If an active transaction might still need to read an old version, PostgreSQL must retain it. The old tuple can only be reclaimed once no snapshot needs it under MVCC rules.

### 3.3. Dead Tuples

Tuple versions no longer visible to any transaction become dead tuples. VACUUM can reclaim their space for reuse.

### 3.4. Why Can Continuous UPDATEs Cause Table Bloat?

If a table is updated frequently:

- Many tuple versions are created.
- Some old versions must wait for long-running snapshots to finish.
- Dead tuples must be cleaned by VACUUM/pruning.
- If indexes must insert new entries, indexes can grow as well.

This is a primary reason HOT and fillfactor matter.

### 3.5. HOT Does Not Eliminate MVCC

HOT still creates a new tuple version. It only optimizes how indexes reference those versions. HOT does not turn UPDATE into an in-place overwrite and does not eliminate the need for VACUUM.

---

## 4. What Is a HOT Update?

**HOT** stands for **Heap-Only Tuple**.

An UPDATE can be HOT when fundamental conditions hold:

1. The UPDATE does not modify columns referenced by relevant indexes, per PostgreSQL's HOT rules.
2. The page holding the old tuple has enough free space to store the new tuple version on the **same page**.

When HOT succeeds:

- PostgreSQL places the new tuple version on the same heap page.
- Existing index entries can continue pointing to the root tuple of the HOT chain.
- No new index entry needs to be added for the new version.
- Old and new versions are linked in a HOT chain and can be pruned when safe.

### 4.1. Illustrative Example

Table:

```sql
CREATE TABLE storage_lab.device_state (
    device_id BIGINT PRIMARY KEY,
    status TEXT NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL
);
```

Suppose there is only a primary key index on `device_id`.

UPDATE statement:

```sql
UPDATE storage_lab.device_state
SET last_seen = clock_timestamp()
WHERE device_id = 1001;
```

`last_seen` is not referenced by any index. If the page holding the row has enough room, PostgreSQL can perform a HOT update.

### 4.2. Example Unlikely to Be HOT

If we create an index:

```sql
CREATE INDEX device_state_last_seen_idx
ON storage_lab.device_state(last_seen);
```

and then run:

```sql
UPDATE storage_lab.device_state
SET last_seen = clock_timestamp()
WHERE device_id = 1001;
```

The UPDATE modifies `last_seen`, which is referenced by an index. Under normal HOT rules, this update is ineligible for HOT.

### 4.3. What Does HOT Reduce?

A non-HOT UPDATE generally requires index maintenance for the new tuple version. HOT avoids adding new index entries, reducing:

- Index tuples created.
- WAL generated for index maintenance.
- Index bloat caused by frequent row versions.
- Cost of cleaning up dead index entries.
- Portion of I/O and CPU spent on index updates.

### 4.4. HOT Does Not Mean "No Index Needed"

Indexes are still used to find the root tuple. HOT merely avoids inserting extra index entries for every version in the chain when conditions allow.

### 4.5. HOT Does Not Guarantee Fast UPDATEs in Every Case

An UPDATE must still locate the row, evaluate predicates, lock the tuple, write the new version, emit WAL, and maintain transactional semantics. If the bottleneck is lock contention, network latency, or WAL sync, HOT may not be the dominant factor.

---

## 5. HOT Eligibility: Which Columns Do Indexes Reference?

The condition "does not modify columns referenced by indexes" covers more than just simple key column lists.

### 5.1. Direct Column B-Tree Index

```sql
CREATE INDEX idx_device_status
ON storage_lab.device_state(status);
```

An UPDATE changing `status` is normally non-HOT because `status` is an index key.

### 5.2. INCLUDE Columns

```sql
CREATE INDEX idx_device_status_cover
ON storage_lab.device_state(device_id)
INCLUDE (status);
```

`status` is stored inside the index as an included payload column. An UPDATE changing `status` can disqualify HOT.

Never assume INCLUDE columns are "unrelated to index maintenance."

### 5.3. Expression Indexes

```sql
CREATE INDEX idx_customer_lower_email
ON storage_lab.customers (lower(email));
```

Even though the index definition does not list `email` as a bare column key, the expression depends on that column. Updating `email` requires updating the index entry.

### 5.4. Partial Index Predicates

```sql
CREATE INDEX idx_active_devices
ON storage_lab.device_state(device_id)
WHERE status = 'ACTIVE';
```

`status` appears in the predicate. Changing status can cause the row to enter or leave the index, requiring index maintenance and disqualifying HOT.

### 5.5. One Column Referenced Across Multiple Indexes

If a table has 5 indexes, HOT eligibility checks all applicable indexes. A single index depending on the modified column prevents HOT for that UPDATE.

### 5.6. Summarizing Indexes and BRIN

Certain PostgreSQL versions include exceptions for **summarizing indexes**, notably BRIN, because such indexes summarize block ranges rather than storing one TID entry per row like B-trees do.

Do not apply a blanket rule that "any column appearing in any index strictly forbids HOT" without checking documentation for your version and index type. For B-trees and standard per-tuple indexes, assume any referenced column prevents HOT.

### 5.7. Checking Actual Index Definitions

```sql
SELECT
    indexrelid::regclass AS index_name,
    pg_catalog.pg_get_indexdef(indexrelid) AS index_definition
FROM pg_catalog.pg_index
WHERE indrelid = 'storage_lab.device_state'::regclass
ORDER BY indexrelid::regclass::TEXT;
```

Before tuning HOT, read all index definitions rather than checking only the primary key.

---

## 6. HOT Chains and Root Tuples

When a HOT update occurs, index entries do not point directly to each new version. Instead, PostgreSQL uses a **HOT chain** within the same heap page.

Conceptual model:

```text
Index entry
    |
    v
Root tuple A (old version)
    |
    | HOT link
    v
Tuple B (next version)
    |
    | HOT link
    v
Tuple C (newer version)
```

### 6.1. Why Is It Called a Heap-Only Tuple?

Versions after the root reside solely on the heap page without their own index entries. They are heap-only tuples within the chain.

### 6.2. Index Entries Still Work

An index scan lands on the root tuple. PostgreSQL follows the chain and checks visibility to return the version matching the snapshot.

### 6.3. HOT Chains Can Grow Long

If the same row is UPDATED repeatedly before older versions are pruned, the chain accumulates multiple versions.

A long chain increases visibility-checking work when accessing the row. Page pruning and VACUUM remove unneeded versions.

### 6.4. Page Pruning

When safe under MVCC, PostgreSQL can prune dead tuple versions within a page. This can happen during page access or during VACUUM, depending on circumstances.

### 6.5. HOT Does Not Break Primary Keys

The index entry continues leading to the chain root. The primary key still identifies the logical row by key value, while HOT optimizes how tuple versions are chained on the heap side.

### 6.6. Do Not Store ctid in Applications

Because HOT chains and UPDATEs change tuple positions, `ctid` is not a durable identifier. Use a primary key or business key.

---

## 7. Heap Table Fillfactor

**Table fillfactor** is a storage parameter specifying the target percentage of page space to fill with tuple data during initial writes.

Valid values typically range from **10 to 100**; the default is **100**.

### 7.1. Fillfactor = 100

By default, PostgreSQL packs page space tightly. This is usually sensible for append-only or rarely updated tables.

### 7.2. Fillfactor = 80

```sql
CREATE TABLE storage_lab.device_state (
    device_id BIGINT PRIMARY KEY,
    status TEXT NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL
) WITH (fillfactor = 80);
```

The goal is reserving free room on heap pages when writing new tuples, creating opportunities for future UPDATEs to store new versions on the same page.

### 7.3. Fillfactor Does Not Guarantee Exactly 20% Free on Every Page

Page headers, line pointers, tuple headers, alignment, variable row sizes, and UPDATE/DELETE activity alter page fullness.

A setting of 80 does not guarantee every page always has exactly 20% free bytes or that every row can grow 20%.

### 7.4. Fillfactor Affects INSERT Placement

Fillfactor primarily governs how PostgreSQL fills pages when writing new tuples. As fresh pages are filled, the engine stops adding new inserts once occupancy reaches the configured target.

### 7.5. Fillfactor Creates Opportunity, Not a Guarantee of HOT

An UPDATE still fails to be HOT if:

- An indexed column changes.
- The new tuple version does not fit on the old page.
- The page lacks room due to variable-width growth or other updates.
- Other HOT requirements are not satisfied.

### 7.6. Fillfactor 100 Can Still Have HOT Updates

If VACUUM/pruning freed space, or a page has leftover room because tuples did not completely fill it, an UPDATE to non-indexed columns can still be HOT.

Never think of fillfactor 100 as "HOT disabled."

---

## 8. Why Can a Lower Fillfactor Help Update-Heavy Tables?

Suppose each row has `device_id`, `status`, `last_seen`, and `heartbeat_at`.

- `device_id` is used for lookups and has a primary key index.
- `last_seen` and `heartbeat_at` change frequently.
- Queries do not require indexes on those two timestamp columns.

If frequently changing columns are unindexed and pages retain room, HOT updates can occur.

### 8.1. Keeping Space Near the Old Tuple

HOT requires the new tuple version on the same page. Leaving free space on pages during INSERT increases the probability that the new version fits there.

### 8.2. Reducing Index Churn

When most UPDATEs are HOT, indexes avoid receiving new entries on every status change, limiting index growth.

### 8.3. Improving Page Locality

Versions of a row stay on the same page, allowing index lookup and visibility checking to remain within one page instead of bouncing across multiple heap pages.

### 8.4. Not Every Update-Heavy Table Needs Low Fillfactor

If the application regularly updates indexed columns, lowering fillfactor enlarges the table without enabling HOT for those UPDATEs.

### 8.5. Row Size Growth Matters

If `description` grows from 100 bytes to 2 KB, reserved free space may not accommodate the new tuple version. HOT eligibility depends on actual version size.

### 8.6. Choose Fillfactor by Pattern, Not Table Name

A table named `events` might be insert-only; a table named `sessions` might be continuously updated. Tune based on actual data behavior, not domain labels.

---

## 9. Trade-Offs of Lowering Fillfactor

Lower fillfactor can benefit update-heavy workloads, yet comes with costs.

| Potential Benefit | Cost / Risk |
| --- | --- |
| More HOT opportunities | More heap pages |
| Fewer new index entries | Table consumes more disk space |
| Reduced index churn/bloat | Full table scans read more pages |
| Room for tuple versions | Buffer cache holds fewer rows |
| Potentially less WAL/index maintenance | Backups and physical replication may ship more bytes |
| Improved performance for certain update patterns | INSERTs may allocate more pages |

### 9.1. Read-Heavy Tables

If a table rarely receives UPDATEs and queries scan many rows, fillfactor 100 is usually better due to higher density.

### 9.2. Update-Heavy Tables

If a table updates non-indexed columns heavily and HOT ratio is low due to lack of page space, test lower fillfactor in staging/benchmarks.

### 9.3. Tables with Very Large Rows

A percentage of page free space is insufficient if the new tuple version exceeds actual leftover bytes. Inspect row width, TOAST behavior, and update growth.

### 9.4. Tables with Many Partitions

Each leaf partition has its own physical pages and storage parameters. Do not assume altering fillfactor on a partitioned parent automatically rewrites or tunes existing partitions.

### 9.5. Do Not Pick 70 or 80 by Intuition

Those are common test starting points, not universal optima. Test 100, 90, 80, or lower depending on your data, measuring throughput, storage, read latency, and HOT ratio.

---

## 10. Changing Fillfactor on an Existing Table

You can change the storage parameter:

```sql
ALTER TABLE storage_lab.device_state
SET (fillfactor = 80);
```

### 10.1. Does It Rewrite the Whole Table Immediately?

No. `ALTER TABLE ... SET (fillfactor=80)` updates the storage parameter for subsequent writes; it does not automatically relocate existing tuples to carve out 20% free space on every existing page.

### 10.2. Old Data Stays on Old Pages

Already-full pages remain short of space for HOT. Simply changing the setting does not make the HOT ratio jump immediately.

### 10.3. When Does Free Space Appear?

- Earlier UPDATEs/DELETEs create dead tuples.
- VACUUM/pruning reclaims space for reuse.
- Pages that were never completely filled.
- Rewrite/repack operations reorganize tuples under the new storage settings.

### 10.4. Table Rewrites

Rewrite methods such as VACUUM FULL, CLUSTER, or tools like pg_repack reorganize data and produce fresh page layouts. Each has distinct locking, disk space, duration, and operational risks.

### 10.5. Regular VACUUM Does Not Compact All Live Tuples

Regular VACUUM reclaims dead tuple space for reuse, updates the FSM, and maintains visibility/freezing. It usually does not pack live tuples together to shrink the file to minimum size.

### 10.6. VACUUM FULL

VACUUM FULL rewrites the relation under a strong lock (ACCESS EXCLUSIVE) and needs extra disk space to build the new copy during execution. Never run it on large production tables without thorough planning.

### 10.7. CLUSTER

CLUSTER rewrites a table in the order of a chosen index and can improve locality along that order. It takes a strong lock and carries operational cost. Do not run it routinely as a substitute for proper index/fillfactor design.

### 10.8. pg_repack

`pg_repack` is an external extension/tool outside PostgreSQL core that can reorganize tables with different locking behavior from VACUUM FULL under specific conditions. Verify compatibility, privileges, disk space, and operational procedures before use.

---

## 11. Table Fillfactor Differs from B-Tree Index Fillfactor

A common mistake is thinking `fillfactor=80` on a table also controls how indexes are filled.

They are two independent storage parameters.

| Property | Table fillfactor | B-tree index fillfactor |
| --- | --- | --- |
| Applies to | Heap table | B-tree index |
| Common default | 100 | 90 |
| Goal | Reserve room for tuple versions/updates | Control fullness of index pages |
| Impact on HOT | Can increase HOT chances via heap free space | Does not directly make updates HOT-eligible |
| Trade-off | Table size, scan density, update locality | Index size, page splits, cache |
| Configuration | `CREATE TABLE ... WITH (fillfactor=...)` | `CREATE INDEX ... WITH (fillfactor=...)` |

### 11.1. Creating a B-Tree Index with Fillfactor

```sql
CREATE INDEX device_state_status_idx
ON hot_lab.device_state(status)
WITH (fillfactor = 85);
```

### 11.2. Changing Index Fillfactor

```sql
ALTER INDEX storage_lab.device_state_status_idx
SET (fillfactor = 80);
```

The new setting affects how the index is maintained in applicable operations; existing pages are not automatically reorganized merely by ALTER INDEX.

### 11.3. REINDEX When Rebuilding Page Layout

```sql
REINDEX INDEX storage_lab.device_state_status_idx;
```

REINDEX rebuilds the index and must be planned around locking/concurrency/version rules. Never run on large production systems without assessing impact.

### 11.4. Why Do B-Trees Need Free Space?

B-trees split pages when inserting entries into a full page. Lower fillfactor reserves room for certain insert patterns and can reduce splits in some workloads.

### 11.5. Index Fillfactor Does Not Fix HOT Eligibility

If an UPDATE modifies an indexed column, a lower B-tree fillfactor does not make that UPDATE HOT. HOT eligibility depends on whether indexes must update entries for modified columns plus space on the heap page.

---

## 12. Free Space Map (FSM)

PostgreSQL maintains the **Free Space Map** to track approximate available free space across pages of a relation.

### 12.1. What Is the FSM Used For?

When inserting a new tuple, PostgreSQL consults the FSM to locate a page likely able to hold the tuple instead of scanning every page sequentially.

### 12.2. FSM Is Approximate Information

The FSM is not an exact real-time byte-by-byte map. Concurrent writes and page modifications can cause actual free space to differ from recorded values.

### 12.3. FSM and HOT Are Related, Yet Different

The FSM helps locate any page with free room for writes. HOT requires the new version to reside **on the exact same page as the old tuple**. Plenty of free space on other pages cannot make an UPDATE HOT if the old page lacks space.

### 12.4. VACUUM Updates Free Space Information

VACUUM updates the FSM as it reclaims dead tuple space so subsequent writes can reuse it.

### 12.5. Free Space Does Not Mean Bloat

A table with a lower fillfactor intentionally reserves free space to support UPDATEs. Do not treat every free byte as waste or bloat.

---

## 13. Inspecting Free Space with pg_freespacemap

The `pg_freespacemap` extension provides functions to read free space map information.

### 13.1. Creating the Extension If Permitted

```sql
CREATE EXTENSION IF NOT EXISTS pg_freespacemap;
```

Installing extensions requires appropriate privileges and administrator approval in managed environments.

### 13.2. Inspecting Free Space Per Page

```sql
SELECT
    blkno,
    avail AS available_bytes
FROM pg_freespace(
    'storage_lab.device_state'::regclass
)
ORDER BY blkno
LIMIT 30;
```

The schema of the function depends on where the extension was installed; if your search_path excludes that schema, qualify it explicitly.

### 13.3. Output Meaning

- `blkno`: block/page number in the relation.
- `avail`: estimated free space recorded by the FSM for that page.

### 13.4. This Is Not an Exact Byte Measurement

For deep analysis, cross-check with `pgstattuple`, `pageinspect`, or real workload testing. Never use a single FSM row to conclude for certain that the next UPDATE will be HOT.

### 13.5. Summarizing Free Space Distribution

```sql
SELECT
    COUNT(*) AS pages,
    MIN(avail) AS min_free_bytes,
    AVG(avail)::NUMERIC(12,2) AS avg_free_bytes,
    MAX(avail) AS max_free_bytes
FROM pg_freespace(
    'storage_lab.device_state'::regclass
);
```

Some pages may not appear as expected if the relation is tiny or FSM entries have not yet been refreshed to the latest state.

---

## 14. Viewing Live Tuples, Dead Tuples, and Free Space with pgstattuple

The `pgstattuple` extension provides detailed relation-level statistics.

### 14.1. Installing the Extension

```sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;
```

Requires appropriate privileges and awareness of scan cost.

### 14.2. Table Statistics

```sql
SELECT *
FROM pgstattuple(
    'storage_lab.device_state'::regclass
);
```

Output columns can include:

- `table_len`: relation size in bytes.
- `tuple_count`: count of live tuples.
- `tuple_len`: total bytes of live tuple data.
- `tuple_percent`: percentage of live tuple data.
- `dead_tuple_count`: count of dead tuples.
- `dead_tuple_len`: bytes of dead tuples.
- `dead_tuple_percent`: percentage of dead tuple data.
- `free_space`: observed free space.
- `free_percent`: percentage of free space.

### 14.3. pgstattuple Has a Cost

Exact functions scan the relation to gather statistics; on very large tables, this consumes significant I/O and time. Schedule carefully.

### 14.4. pgstattuple_approx

Some versions include `pgstattuple_approx`, which uses the free space map and visibility map to estimate faster under certain conditions. It is an approximation, not a replacement for an exact scan when precision is required.

### 14.5. Interpreting Results in Context

- High free space may reflect fillfactor design or recent deletes/updates.
- High dead tuple percent may indicate vacuum is falling behind.
- Low tuple percent may indicate low page density or bloat.
- Never judge from a single percentage alone; examine workload, table/index sizes, and trends.

---

## 15. Monitoring HOT Updates with pg_stat_user_tables

PostgreSQL exposes table-level update statistics.

```sql
SELECT
    schemaname,
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    n_dead_tup
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'storage_lab'
ORDER BY relname;
```

### 15.1. n_tup_upd

Number of tuple updates recorded for the table.

### 15.2. n_tup_hot_upd

Number of HOT updates recorded for the table.

### 15.3. HOT Update Ratio

You can compute:

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    ROUND(
        100.0 * n_tup_hot_upd / NULLIF(n_tup_upd, 0),
        2
    ) AS hot_update_percent
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'storage_lab'
ORDER BY relname;
```

### 15.4. There Is No Universal HOT Ratio Target

- For an append-only table with almost no UPDATEs, HOT ratio means very little.
- A table frequently updating an indexed column will naturally have a low HOT ratio by design.
- An update-heavy table modifying non-indexed columns should achieve a higher HOT ratio if pages have enough room.
- A 90% ratio does not by itself prove query latency is healthy or indexes are bloat-free.

### 15.5. Statistics Are Cumulative

Counters can reset based on stats mechanisms and operational events. Compare deltas over a defined time window rather than reading an isolated cumulative number without history.

### 15.6. Statistics Updates Have Latency

Stats may not immediately reflect a transaction that just committed. Re-query after commit inside a fresh snapshot/transaction. Do not treat instantaneous reads as synchronous per-statement counters.

---

## 16. Why Is the HOT Ratio Low?

Common causes include:

### 16.1. UPDATEs Modify Indexed Columns

For example, an index exists on `last_seen` while every heartbeat updates `last_seen`.

Potential fixes: drop the index if queries do not genuinely need it, or adjust the data/index model. Never drop an essential index solely to inflate the HOT ratio.

### 16.2. Pages Lack Free Space

Fillfactor 100 and packed pages leave no room for new tuple versions.

Solution: test a lower fillfactor for new data or plan a rewrite/repack to apply it to existing data.

### 16.3. New Tuple Versions Grow Larger

Growing TEXT/JSONB columns can prevent the new version from fitting on the page even if initial free space was reserved.

### 16.4. Multiple Indexes Depend on Modified Columns

Expression indexes, partial indexes, or INCLUDE columns can block HOT eligibility.

### 16.5. Fillfactor Not Applied to Actual Partitions

For partitioned tables, data resides in leaf partitions. Setting fillfactor on the parent does not retro-fit existing child partitions still using earlier settings.

### 16.6. Updating Many Unstable Columns Together

If every UPDATE changes status, indexed timestamps, keys, and other fields at once, achieving HOT is difficult.

### 16.7. No Free Space Despite Low Configured Fillfactor

Altering the storage parameter does not create free space on pre-existing pages. Vacuuming, rewriting, or waiting for new writes under the updated setting may be needed.

### 16.8. HOT Is Not the Sole Objective

If an UPDATE must change an index key because queries filter by the updated value, non-HOT is an expected cost. Never optimize HOT by breaking business query capabilities.

---

## 17. Designing Tables to Support HOT

Key design principles:

### 17.1. Separate Stable Columns from Frequently Updated Columns

Example:

```sql
CREATE TABLE storage_lab.device_state (
    device_id BIGINT PRIMARY KEY,
    hardware_serial TEXT NOT NULL,
    status TEXT NOT NULL,
    last_seen TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    metadata JSONB
);
```

- `device_id`, `hardware_serial`: relatively stable.
- `last_seen`, `heartbeat_at`: updated frequently.
- `metadata`: may vary widely in size.

If the workload primarily updates timestamps, avoid indexing timestamps without strong query justification.

### 17.2. Do Not Index Every Column "Just in Case"

Every index adds write overhead and storage cost. Only create indexes justified by actual query patterns and measurable benefits.

### 17.3. Evaluate INCLUDE Columns

Covering indexes assist index-only scans in some scenarios, yet including a constantly changing column disqualifies UPDATEs from HOT.

### 17.4. Evaluate Partial Indexes

Partial indexes reduce size by indexing only a subset of rows, yet predicate columns affect HOT too. A frequently updated status column in a predicate can force non-HOT updates.

### 17.5. Split Tables When Update Frequencies Differ Sharply

A table combining many static profile columns with fast-changing heartbeat columns can be split into a separate status table sharing the primary key when workload and consistency models align.

Example:

```sql
CREATE TABLE storage_lab.devices (
    device_id BIGINT PRIMARY KEY,
    serial_number TEXT NOT NULL,
    model TEXT NOT NULL
);

CREATE TABLE storage_lab.device_heartbeats (
    device_id BIGINT PRIMARY KEY
        REFERENCES storage_lab.devices(device_id),
    last_seen TIMESTAMPTZ NOT NULL,
    heartbeat_state TEXT NOT NULL
) WITH (fillfactor = 80);
```

Splitting introduces trade-offs in JOINs, transactions, and schema complexity; only adopt it when workload evidence supports it.

### 17.6. Avoid No-Op Value UPDATEs

An UPDATE that leaves values unchanged still creates a new tuple version. When application logic permits skipping redundant updates:

```sql
UPDATE storage_lab.device_state
SET status = $1
WHERE device_id = $2
  AND status IS DISTINCT FROM $1;
```

this cuts unnecessary tuple versions and WAL.

### 17.7. Use Controlled Conditional Updates

Do not blindly UPDATE every row just to refresh timestamps if business rules do not require it. Periodic sweeps can generate huge version churn and vacuum load.

---

## 18. HOT, VACUUM, and Autovacuum

HOT reduces index maintenance yet does not eliminate dead tuple versions. VACUUM remains essential.

### 18.1. What Does Regular VACUUM Do?

- Reclaims dead tuple space for reuse.
- Updates the Free Space Map.
- Supports page pruning/cleanup.
- Updates the Visibility Map when eligible.
- Performs freezing per needs and transaction age rules.

### 18.2. Regular VACUUM Usually Does Not Shrink Relation Files

Reclaimed space is normally kept inside the relation for future writes. Filesystem size may remain large.

### 18.3. Autovacuum

Autovacuum runs VACUUM/ANALYZE automatically based on thresholds and policies. On update-heavy tables, monitor:

- `n_dead_tup`.
- `last_autovacuum`.
- `autovacuum_count`.
- Transaction age and vacuum progress.
- Replication slots or long-running transactions that can block required cleanup.

### 18.4. Tune Per Table When Justified

Illustrative example:

```sql
ALTER TABLE storage_lab.device_state
SET (
    autovacuum_vacuum_threshold = 1000,
    autovacuum_vacuum_scale_factor = 0.05
);
```

Choose settings based on row count, update rate, vacuum duration, and resources. Never copy one magic number across every table.

### 18.5. HOT Chains Need Cleanup

Page pruning and VACUUM reclaim unneeded tuple versions. Long-running transactions/snapshots or replication slots pinning xmin delay cleanup.

### 18.6. HOT Is Not a Complete Anti-Bloat Solution

If a table sees heavy DELETEs, non-HOT updates, long transactions, or lagging autovacuum, bloat can still occur. Measure heap and indexes separately.

---

## 19. Table Bloat vs. Intentional Free Space

**Bloat** refers to relation space growing due to dead tuples, page splits, or inefficient distribution relative to live data. However, free space on a page is not automatically bloat.

### 19.1. Intentional Free Space

With fillfactor 80, space is purposefully reserved to absorb UPDATEs. That is intentional design.

### 19.2. Dead Tuple Space

Unreclaimed old tuple versions occupy space. VACUUM marks that space for reuse.

### 19.3. Index Bloat

Non-HOT updates insert new index entries; older entries become dead and require cleanup. Indexes can grow over time.

### 19.4. Table Size vs. Live Data Size

Do not look solely at `pg_relation_size`. Inspect tuple count, tuple length, dead tuple length, free space, and indexes.

### 19.5. Do Not Try to Force free_percent to 0

An update-heavy table with a tuned lower fillfactor deliberately retains free space. Packing every page full destroys HOT headroom and increases index churn.

---

## 20. Lab: Creating an Update-Heavy Table with Fillfactor

The examples below use the `hot_lab` schema.

> **Warning:** `DROP SCHEMA ... CASCADE` deletes all objects in the named schema. Run only in a disposable lab database. Never run in production or on schemas holding data you need to keep.

### 20.1. Creating the Schema

```sql
DROP SCHEMA IF EXISTS hot_lab CASCADE;
CREATE SCHEMA hot_lab;
```

### 20.2. Creating a Table with Fillfactor 70

```sql
CREATE TABLE hot_lab.device_state (
    device_id BIGINT PRIMARY KEY,
    status TEXT NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    description TEXT
) WITH (fillfactor = 70);
```

### 20.3. Inserting Sample Rows

```sql
INSERT INTO hot_lab.device_state (
    device_id,
    status,
    last_seen,
    description
)
SELECT
    g,
    'ONLINE',
    clock_timestamp(),
    'device-' || g::TEXT
FROM generate_series(1, 20000) AS g;
```

The table has a primary key index on `device_id` and no index on `last_seen` yet.

### 20.4. Checking reloptions

```sql
SELECT
    c.relname,
    c.reloptions
FROM pg_catalog.pg_class AS c
WHERE c.oid = 'hot_lab.device_state'::regclass;
```

Expect to see `fillfactor=70`.

### 20.5. Checking Sizes

```sql
SELECT
    pg_catalog.pg_relation_size(
        'hot_lab.device_state'::regclass
    ) AS heap_bytes,
    pg_catalog.pg_indexes_size(
        'hot_lab.device_state'::regclass
    ) AS index_bytes,
    pg_catalog.pg_total_relation_size(
        'hot_lab.device_state'::regclass
    ) AS total_bytes;
```

### 20.6. Listing Indexes

```sql
SELECT
    indexrelid::regclass AS index_name,
    pg_catalog.pg_get_indexdef(indexrelid) AS definition
FROM pg_catalog.pg_index
WHERE indrelid = 'hot_lab.device_state'::regclass;
```

Initially, the only index is the primary key on `device_id`.

---

## 21. Lab: Generating HOT Updates on a Non-Indexed Column

Try updating `last_seen`:

```sql
UPDATE hot_lab.device_state
SET last_seen = last_seen + INTERVAL '1 second'
WHERE device_id % 10 = 0;
```

### 21.1. Why Is There a HOT Opportunity?

- `last_seen` is unindexed.
- Pages retain free space thanks to fillfactor 70.
- New tuple versions are similar in size to old versions.
- When pages have enough space, updates can be HOT.

### 21.2. Checking Statistics

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    ROUND(
        100.0 * n_tup_hot_upd / NULLIF(n_tup_upd, 0),
        2
    ) AS hot_update_percent,
    n_dead_tup
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'hot_lab'
  AND relname = 'device_state';
```

### 21.3. Expected Outcome

Under normal lab conditions, `n_tup_hot_upd` should rise because the UPDATE only changes an unindexed column and the table reserved space on pages.

Do not expect 100% of row updates to be HOT. Page layout, tuple sizes, free-space state, and execution conditions can cause variations.

### 21.4. Statistics Can Lag Slightly

Run after the statement/transaction commits. If querying inside an older stats snapshot, re-query in a new transaction.

### 21.5. Do Not Reset Cluster-Wide Stats Just for a Lab

`pg_stat_reset()` affects system-wide monitoring metrics. When measuring deltas, record before/after counters and subtract; only reset single-table counters when you understand privileges and impact.

---

## 22. Lab: Creating an Index on the Frequently Updated Column

Now create an index:

```sql
CREATE INDEX device_state_last_seen_idx
ON hot_lab.device_state(last_seen);
```

Then update `last_seen` again:

```sql
UPDATE hot_lab.device_state
SET last_seen = last_seen + INTERVAL '2 seconds'
WHERE device_id % 10 = 0;
```

### 22.1. What Changed?

`last_seen` is now referenced by a B-tree index. When UPDATE modifies it, normal HOT rules no longer qualify.

### 22.2. Re-Reading Statistics

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    ROUND(
        100.0 * n_tup_hot_upd / NULLIF(n_tup_upd, 0),
        2
    ) AS hot_update_percent
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'hot_lab'
  AND relname = 'device_state';
```

Counters are cumulative; to compare two phases accurately, capture before/after values for each phase and compute deltas.

### 22.3. Expected Outcome

UPDATEs after indexing `last_seen` generally stop incrementing the HOT counter as in the first phase; PostgreSQL must maintain the index for the updated values.

### 22.4. Design Lesson

An index speeding up `last_seen` queries makes heartbeat UPDATEs costlier. Measure the trade-off between read performance and write amplification.

### 22.5. Never Drop an Index Just to Improve the HOT Ratio

If production queries depend on that index, dropping it can spike read latency severely. HOT ratio is a diagnostic metric, not an end goal in itself.

---

## 23. Lab: Inspecting the Free Space Map

Install the extension if privileges permit:

```sql
CREATE EXTENSION IF NOT EXISTS pg_freespacemap;
```

### 23.1. Viewing Sample Pages

```sql
SELECT
    blkno,
    avail AS free_bytes
FROM pg_freespace(
    'hot_lab.device_state'::regclass
)
ORDER BY blkno
LIMIT 30;
```

### 23.2. Summarizing Distribution

```sql
SELECT
    COUNT(*) AS page_count,
    MIN(avail) AS minimum_free_bytes,
    ROUND(AVG(avail)::NUMERIC, 2) AS average_free_bytes,
    MAX(avail) AS maximum_free_bytes
FROM pg_freespace(
    'hot_lab.device_state'::regclass
);
```

### 23.3. Comparing with Fillfactor

Page free space will not necessarily stay at exactly 30% from the initial fillfactor. UPDATEs, VACUUM, tuple sizes, and page occupancy have already changed it.

### 23.4. FSM Does Not Predict HOT with Certainty

It reports estimated free space per page. HOT also depends on indexed columns and whether the new tuple version fits on that exact page.

---

## 24. Lab: Observing Dead Tuples and VACUUM

Install `pgstattuple` if permitted:

```sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;
```

### 24.1. Reading Stats Before VACUUM

```sql
SELECT *
FROM pgstattuple(
    'hot_lab.device_state'::regclass
);
```

### 24.2. Running Regular VACUUM

```sql
VACUUM (VERBOSE, ANALYZE) hot_lab.device_state;
```

Regular VACUUM must run outside a transaction block as required by PostgreSQL.

### 24.3. Re-Reading Stats

```sql
SELECT *
FROM pgstattuple(
    'hot_lab.device_state'::regclass
);
```

### 24.4. What to Observe

- Dead tuple count/length may drop.
- Free space may increase as dead tuples are reclaimed for reuse.
- The relation file generally does not shrink merely from regular VACUUM.
- Stats can differ based on timing and visibility horizons.

### 24.5. HOT Chain Cleanup

VACUUM and page pruning reclaim unneeded HOT tuple versions, shortening chain traversal and letting pages reuse space.

---

## 25. Lab: Changing Fillfactor and Understanding Impact on Existing Data

Change the setting:

```sql
ALTER TABLE hot_lab.device_state
SET (fillfactor = 85);
```

### 25.1. Confirm

```sql
SELECT reloptions
FROM pg_catalog.pg_class
WHERE oid = 'hot_lab.device_state'::regclass;
```

### 25.2. What Does Not Happen?

PostgreSQL does not immediately move existing tuples so every page has 15% free space. Existing pages retain their current layout.

### 25.3. Subsequently Inserted Rows

Pages used for newly written tuples will apply the storage parameter according to PostgreSQL's fillfactor rules.

### 25.4. Applying Broadly to Old Data

Consider a planned table rewrite/repack. For example:

```sql
-- Heavy operation, illustrative for lab environments:
-- VACUUM (FULL) hot_lab.device_state;
```

VACUUM FULL requires an ACCESS EXCLUSIVE lock and extra disk space. Never run it casually on large production tables just to experiment.

### 25.5. New Table Fillfactor Does Not Change Index Fillfactor

Table reloptions and index reloptions are independent. Inspect `pg_class.reloptions` for each relation separately if needed.

---

## 26. B-Tree Index Fillfactor and Page Splits

B-tree indexes also have a fillfactor storage parameter, commonly defaulting to 90.

### 26.1. Example

```sql
CREATE INDEX device_state_status_idx
ON hot_lab.device_state(status)
WITH (fillfactor = 85);
```

### 26.2. Why Leave Room on Index Pages?

When inserting new entries, a B-tree splits a page if it runs out of room. A lower fillfactor leaves room for certain insert patterns and can reduce splits in some workloads.

### 26.3. Index Fillfactor and Table Fillfactor Serve Different Goals

- Heap fillfactor creates room for new tuple versions on the same heap page.
- B-tree fillfactor controls index page occupancy.

### 26.4. Lowering Index Fillfactor Does Not Enable HOT

If an UPDATE modifies an indexed column, the B-tree index still must be updated. Lowering index fillfactor will not turn that update into HOT.

### 26.5. Index Read Density

Lower index fillfactor enlarges the index and reduces entries per page, affecting cache efficiency and pages read. Measure both read and write workloads.

---

## 27. Partitioned Tables and Fillfactor

A partitioned table in PostgreSQL is a coordinating parent relation; actual data resides in leaf partitions.

### 27.1. Parent Storage Parameters Do Not Replace Checking Leaves

```sql
CREATE TABLE hot_lab.events (
    event_id BIGINT,
    tenant_id BIGINT,
    event_type TEXT,
    updated_at TIMESTAMPTZ
) PARTITION BY RANGE (event_id);
```

Create a partition:

```sql
CREATE TABLE hot_lab.events_p1
PARTITION OF hot_lab.events
FOR VALUES FROM (1) TO (100000)
WITH (fillfactor = 80);
```

### 27.2. Each Partition Has Its Own Physical Pages

HOT updates happen within the heap page of the partition holding the tuple. That partition's fillfactor and indexes determine HOT eligibility.

### 27.3. Inspect Each Partition

Do not inspect only the parent's reloptions. Enumerate leaf partitions and check reloptions/ownership/indexes on each physical table.

### 27.4. Partition Pruning Does Not Replace HOT

Partition pruning helps queries skip irrelevant partitions; HOT optimizes tuple updates inside a partition. The two mechanisms solve different problems.

### 27.5. Partition Rotation Can Shift Workload Behavior

New partitions can start with a new fillfactor while older partitions retain older layouts. A partitioned table can exhibit different HOT ratios across time and partitions.

---

## 28. Choosing Fillfactor by Workload Type

| Workload | Direction to Consider |
| --- | --- |
| Append-only, few UPDATEs | Fillfactor near 100 is usually suitable |
| Frequent updates to non-indexed columns | Test 80–90 or lower via benchmarks |
| Continuous heartbeat/timestamp updates | Consider dropping unnecessary timestamp indexes, test lower fillfactor |
| UPDATEs frequently alter index keys | Lower fillfactor will not unlock HOT eligibility |
| Rows grow sharply in size | Measure tuple growth; fixed reserve may be insufficient |
| Read-heavy table with large scans | Higher density is typically beneficial |
| Table with many partitions | Tune leaf partitions by age/workload |
| Deletes/updates causing heavy dead tuples | Examine autovacuum, transaction age, HOT, and bloat together |

### 28.1. Never Optimize a Single Metric in Isolation

A high HOT ratio with a heap twice as large can slow full scans. A lower HOT ratio paired with healthy query latency and compact storage may be the right design.

### 28.2. Use Representative Workloads

Simulate all of the following:

- INSERT/UPDATE/DELETE ratios.
- Fraction of updates touching indexed columns.
- Row width and update size growth.
- Concurrency.
- Index count.
- Transaction duration.
- Autovacuum and replication behavior.

### 28.3. Benchmark Multiple Levels

For example, test 100, 90, 80, and 70 in staging clones. Compare identical datasets and workloads rather than comparing differently sized tables and attributing differences solely to fillfactor.

### 28.4. Measure Reads Too

If a table sees far more sequential scans than UPDATEs, increasing page count can hurt significantly. Use `EXPLAIN (ANALYZE, BUFFERS)` alongside workload metrics.

---

## 29. Other Factors Affecting HOT

### 29.1. Tuple Size

The new tuple version must fit on the same page. VARCHAR/TEXT/JSONB columns can change tuple size; TOAST can affect how large values are stored.

### 29.2. Number of Indexes

More indexes raise the odds that a frequently updated column is referenced by an index. Also, non-HOT UPDATEs must maintain more indexes.

### 29.3. Partial Index Predicates

Columns referenced in predicates can cause UPDATEs to alter row membership in the index.

### 29.4. Expression Indexes

A source column used inside an expression index still counts as a column the index depends on.

### 29.5. INCLUDE Columns

A covering index can disqualify UPDATEs to included columns from HOT, even though those columns are not key columns.

### 29.6. Actual Page Occupancy

Fillfactor is a target when writing new tuples, yet pages can fill up or end up unevenly populated after many operations.

### 29.7. Concurrent Workloads

Other sessions may INSERT/UPDATE on the same page; HOT still requires enough room at execution time. Do not assume a single-threaded benchmark gives the same HOT ratio as concurrent production.

### 29.8. Long Transaction Snapshots

A long-running transaction can pin old versions, delaying cleanup and preventing free space from being reclaimed in time.

---

## 30. HOT, WAL, and Replication

HOT reduces part of index maintenance, yet it is still a write operation.

### 30.1. HOT Still Produces Tuple Versions

UPDATE creates a new version and must log data/metadata under durability rules. Never treat HOT as "zero WAL."

### 30.2. Reducing Index WAL Can Still Help

When a table has many indexes and most UPDATEs are HOT, avoiding new index entries reduces write amplification.

### 30.3. Heap WAL Is Still Generated

Heap tuple changes still must be WAL-logged per PostgreSQL policy. HOT does not disable WAL for table updates.

### 30.4. Replication Can Still Receive Heavy WAL

A heartbeat table updated millions of times per day still generates substantial write volume. HOT cuts index maintenance WAL, yet replication workload remains.

### 30.5. Monitor Replica Lag

If tuning fillfactor boosts update throughput, actual write volume may climb with it. Monitor replication lag and disk/WAL capacity.

---

## 31. Do Not Confuse HOT with No-Op UPDATEs

A statement like:

```sql
UPDATE hot_lab.device_state
SET status = status
WHERE device_id = 100;
```

must not be assumed to do "nothing" just because column values match. PostgreSQL still executes UPDATE tuple-versioning semantics, even if HOT applies when eligible.

If application logic does not need to rewrite rows when values are unchanged, add a guard condition:

```sql
UPDATE hot_lab.device_state
SET status = $1
WHERE device_id = $2
  AND status IS DISTINCT FROM $1;
```

### 31.1. Benefits

- Fewer tuple versions.
- Less WAL.
- Fewer dead tuples.
- Lower vacuum workload.
- Reduced lock/write churn in suitable workloads.

### 31.2. NULL-Safe Comparison

`IS DISTINCT FROM` handles NULLs cleanly compared to standard `<>` when checking whether two values differ.

### 31.3. Respect Business Logic

Some applications intentionally update timestamps or audit columns even when other fields do not change. Never skip meaningful updates merely to boost the HOT ratio.

---

## 32. Diagnostics with pageinspect

`pageinspect` is an extension supporting low-level page structure inspection.

### 32.1. Installing the Extension

```sql
CREATE EXTENSION IF NOT EXISTS pageinspect;
```

Requires appropriate privileges; raw page-reading functions demand elevated permissions and controlled usage.

### 32.2. Viewing the Page Header

```sql
SELECT *
FROM page_header(
    get_raw_page('hot_lab.device_state', 0)
);
```

### 32.3. Viewing Heap Page Items

```sql
SELECT *
FROM heap_page_items(
    get_raw_page('hot_lab.device_state', 0)
);
```

### 32.4. Why Exercise Caution?

- This is an internal structure diagnostic tool.
- Interpreting flags/tuple fields requires version-specific implementation knowledge.
- One specific page does not represent the entire relation.
- Never treat pageinspect output as a stable application API.

### 32.5. Never Modify Raw Pages

`pageinspect` is strictly for inspection; never edit page bytes to fix tuples. Fix data through SQL or official recovery procedures.

---

## 33. Controlled Fillfactor Benchmarking

A meaningful benchmark should compare multiple variants:

### 33.1. Prepare Identical Tables

- Table A: fillfactor 100.
- Table B: fillfactor 90.
- Table C: fillfactor 80.
- Table D: fillfactor 70.

Use identical schemas, data distributions, indexes, and constraints.

### 33.2. Choose Update Patterns

- Update only unindexed columns.
- Update a B-tree indexed column.
- Update a column in a partial-index predicate.
- Update causing significant row-width growth.
- Concurrent updates across many rows.

### 33.3. Metrics

- `n_tup_upd`.
- `n_tup_hot_upd`.
- HOT ratio.
- `n_dead_tup`.
- Heap bytes.
- Index bytes.
- Total relation bytes.
- WAL volume.
- Update throughput.
- p50/p95 latency.
- Read latency/scan buffers.
- Autovacuum frequency/duration.
- Replication lag.

### 33.4. Measurement Tools

- `pg_stat_user_tables`.
- `pg_relation_size`, `pg_indexes_size`, `pg_total_relation_size`.
- `pgstattuple`.
- `pg_freespacemap`.
- `EXPLAIN (ANALYZE, BUFFERS)`.
- `pg_stat_statements` if installed and permitted.
- System WAL/replication monitoring.

### 33.5. Do Not Benchmark Only Once

Caches, checkpoints, vacuum, background load, and data distribution influence results. Run multiple iterations under equivalent conditions.

### 33.6. Never Run Destructive Benchmarks in Production

Use staging/benchmark clones or dedicated test datasets. Avoid generating millions of synthetic UPDATEs against user-facing tables just to test fillfactor.

---

## 34. Reading Index Definitions to Spot Columns Blocking HOT

List a table's indexes:

```sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indisprimary,
    i.indisunique,
    i.indisvalid,
    pg_catalog.pg_get_indexdef(i.indexrelid) AS definition
FROM pg_catalog.pg_index AS i
WHERE i.indrelid = 'hot_lab.device_state'::regclass
ORDER BY i.indexrelid::regclass::TEXT;
```

### 34.1. Identify Frequently Updated Columns

Cross-reference application UPDATE statements against:

- Key columns.
- INCLUDE columns.
- Expression dependencies.
- Partial-index predicates.
- Index types.

### 34.2. Do Not Read Only Index Names

An index named `idx_device_lookup` does not reveal which columns are actually indexed. Read `pg_get_indexdef`.

### 34.3. Invalid/Unready Indexes

Indexes in special states or left mid-build during failed migrations have specific semantics. Check `indisvalid`/`indisready` during investigations; do not assume every catalog index entry behaves like a normal valid index.

### 34.4. Evaluate Query Benefits Before Dropping an Index

An index may underpin critical latency SLAs. Any decision to drop an index for HOT must weigh query plans, read frequency, write amplification, and SLAs.

---

## 35. Common Anti-Patterns

| Anti-Pattern | Consequence | Remedy |
| --- | --- | --- |
| Setting fillfactor 50 on every table | Bloats pages/storage/scan I/O | Tune per workload |
| Lowering fillfactor and expecting old data to re-layout automatically | Old pages keep old layout | Plan rewrite/repack |
| Indexing every frequently updated timestamp column | Many UPDATEs lose HOT | Index only when queries need it |
| INCLUDE-ing a constantly changing heartbeat column | UPDATEs require index maintenance | Evaluate covering index trade-offs |
| Treating HOT ratio as the sole KPI | Misaligned optimization | Measure latency, size, WAL, read cost |
| Believing HOT eliminates VACUUM | Dead tuples/chains still accumulate | Monitor autovacuum |
| Confusing FSM with exact page free space | Wrong HOT predictions | Cross-check pages/stats |
| Confusing intentional free space with bloat | Unnecessary table rewrites | Check pgstattuple and workload |
| Running VACUUM FULL routinely | Heavy locks, disk overhead | Rely on autovacuum and suitable tools |
| Changing index fillfactor to fix HOT | Does not affect heap/index-column rules | Fix index design or heap space |
| Updating every row every minute even unchanged | Unnecessary tuple versions/WAL | Use `IS DISTINCT FROM` |
| Checking only primary key for HOT | Misses expression/partial/INCLUDE indexes | Audit all index definitions |
| Dropping indexes without checking query plans | Read latency spikes | Benchmark both reads and writes |
| Assuming parent fillfactor applies to all partitions | Leaf pages differ | Inspect each leaf |
| Using ctid as a row identifier | UPDATE changes physical position | Use a stable key |
| Assuming HOT generates zero WAL | Underestimates replication/write load | Measure actual WAL |
| Raising autovacuum scale factor arbitrarily | Dead tuples pile up | Tune per table and churn rate |
| Running pageinspect in production at peak hours | I/O/privilege/inspection overhead | Run in controlled windows |
| Reading stats before COMMIT | Counters not yet reflected | Read after commit |
| Resetting cluster-wide stats for lab tests | Loses monitoring baselines | Compute deltas or use a dedicated lab |

---

## 36. Practice Exercises

### Exercise 1 — Heap Page

Draw a heap page showing the page header, line pointers, tuple data, and free space. Explain why a line pointer is not the tuple itself.

### Exercise 2 — MVCC UPDATE

A row has balance=100. After an UPDATE to 90, explain why PostgreSQL creates a new version and how an older transaction can still see the old version.

### Exercise 3 — Dead Tuples

Why cannot the old version be erased immediately when UPDATE finishes? What allows VACUUM to reclaim it?

### Exercise 4 — Defining HOT

State the two basic conditions for a HOT update and explain each.

### Exercise 5 — Non-Indexed Update

Create a table with only a primary key index on id. UPDATE an unindexed timestamp column. Which conditions let that update become HOT?

### Exercise 6 — Indexed Update

Create an index on `last_seen`, then UPDATE `last_seen`. Why is normal HOT no longer eligible?

### Exercise 7 — INCLUDE Index

Create a B-tree index with INCLUDE(status). How can updating status affect HOT?

### Exercise 8 — Expression Index

Create an index on `lower(email)`. Why must updating email be evaluated even though email is not listed as a bare key?

### Exercise 9 — Partial Index

Create an index `WHERE status='ACTIVE'`. How does updating status from ACTIVE to INACTIVE affect index membership and HOT?

### Exercise 10 — BRIN

Explain why summarizing indexes such as BRIN can have exceptions to ordinary HOT rules. Check documentation for your PostgreSQL version.

### Exercise 11 — HOT Chain

Draw an index entry pointing to a root tuple and three tuple versions in a HOT chain. Why does the index not need a separate entry for every version?

### Exercise 12 — Page Pruning

Which tuple versions can page pruning reclaim? Why does visibility of other transactions dictate cleanup timing?

### Exercise 13 — ctid

An application stores ctid in an audit table to revisit rows later. Why is this unsafe after an UPDATE?

### Exercise 14 — Default Fillfactor

State the default and valid range of heap table fillfactor. Why does 100 not mean HOT is disabled?

### Exercise 15 — Fillfactor 80

Create a table with fillfactor=80. Explain what the reserved space is used for and why every page does not always have exactly 20% free bytes.

### Exercise 16 — Altering Fillfactor

Run ALTER TABLE SET fillfactor=70 on a populated table. Are existing pages automatically rewritten?

### Exercise 17 — Table Rewrites

Compare regular VACUUM with VACUUM FULL regarding dead tuple reuse, table size, and locking.

### Exercise 18 — B-Tree Fillfactor

Create a B-tree index with fillfactor=80. Why does this not turn UPDATEs on the indexed column into HOT?

### Exercise 19 — Index Splits

Explain how index fillfactor can affect page splits and its trade-offs for index size/cache.

### Exercise 20 — FSM

Install pg_freespacemap, query pg_freespace, and explain why the FSM provides only approximate information.

### Exercise 21 — pgstattuple

Use pgstattuple to inspect live tuples, dead tuples, and free space. Why avoid running exact scans casually on very large tables?

### Exercise 22 — HOT Ratio

Write a query computing n_tup_hot_upd / n_tup_upd. Why is the ratio less meaningful when a table barely sees UPDATEs?

### Exercise 23 — Stats Delay

Right after an UPDATE, querying stats shows unchanged counters. List possible reasons and how to re-observe after commit.

### Exercise 24 — HOT Lab

Create a table with fillfactor=70, insert 20,000 rows, update unindexed last_seen, and read n_tup_hot_upd. Which conditions could still prevent some updates from being HOT?

### Exercise 25 — Non-HOT Lab

Create an index on last_seen and repeat the UPDATE. Compare before/after counters using deltas.

### Exercise 26 — Row Growth

An UPDATE expands description from 100 bytes to 2 KB. Why does fillfactor 80 not guarantee HOT?

### Exercise 27 — Index Audit

Use pg_get_indexdef to list every index on a table. Identify columns referenced in keys, INCLUDE, expressions, and predicates.

### Exercise 28 — Drop an Index?

An index on last_seen lowers the HOT ratio yet serves an important dashboard query. Propose a benchmark and decision criteria for keeping or dropping it.

### Exercise 29 — No-Op UPDATE

Compare `UPDATE SET status=status` with a guarded `status IS DISTINCT FROM $1` UPDATE. What is the impact on tuple versions and WAL?

### Exercise 30 — Autovacuum

A table's n_dead_tup rises fast while last_autovacuum was hours ago. Which metrics should you inspect before changing autovacuum settings?

### Exercise 31 — Long-Running Transactions

Explain how a long-lived transaction snapshot delays cleanup of HOT chains and dead tuples.

### Exercise 32 — Partition Fillfactor

Create a partitioned parent table and two leaf partitions with different fillfactors. Write a query checking reloptions on each leaf.

### Exercise 33 — Append-Only Workload

Why can an insert-only table with almost no UPDATEs usually keep fillfactor 100?

### Exercise 34 — Heartbeat Workload

Design a heartbeat table so frequently updated columns are not referenced by unnecessary indexes.

### Exercise 35 — Splitting Tables

A profile table stores both static info and heartbeats. List pros and cons of splitting heartbeats into a separate table.

### Exercise 36 — WAL

Do HOT updates eliminate all WAL? Distinguish heap changes from index maintenance.

### Exercise 37 — Replication

A table has a high HOT ratio yet still generates heavy WAL. Explain why standbys can still lag.

### Exercise 38 — Fillfactor Benchmark

Design a benchmark comparing 100/90/80/70. Specify the dataset, indexes, update patterns, and metrics to hold steady and measure.

### Exercise 39 — Table Size

Use pg_relation_size, pg_indexes_size, and pg_total_relation_size. Why measure heap and indexes separately?

### Exercise 40 — Bloat vs. Free Space

A table shows free_percent 25% after setting fillfactor 75. Can you conclude the table is bloated? What extra data is needed?

### Exercise 41 — Pageinspect

Use pageinspect to read the page header and heap_page_items. Why is this an internal diagnostic tool rather than a stable API?

### Exercise 42 — Index vs. Table Fillfactor

A DBA lowers a B-tree fillfactor from 90 to 70 expecting HOT updates to rise. Explain the misconception.

### Exercise 43 — Concurrent Updates

Two sessions concurrently UPDATE rows on the same page. Why might HOT results differ from a sequential benchmark?

### Exercise 44 — Large Table Rewrite

A 2 TB table needs its fillfactor changed from 100 to 80. Plan the assessment of disk space, locks, replication, backups, and rollback.

### Exercise 45 — Production Diagnosis

The HOT ratio dropped from 80% to 15% after a release. Build an investigation workflow covering new indexes, update queries, fillfactor, row growth, partitions, and autovacuum.

### Exercise 46 — End-to-End Design

An IoT system receives 100,000 heartbeats/sec, reads state by device_id, filters certain devices by status, and runs a dashboard by last_seen. Design indexes, fillfactor, HOT strategy, partitioning, vacuum policy, and benchmarks to balance write throughput with query latency.

---

## 37. Fillfactor and HOT Tuning Checklist

| Question | What to Verify |
| --- | --- |
| Does the table receive frequent UPDATEs? | Frequency and which columns change |
| Are updated columns indexed? | Audit all indexes |
| Are there expression/partial indexes? | Check dependencies |
| Are there INCLUDE columns? | Check whether included columns change |
| Does index type have a summarizing exception? | Check BRIN/version docs |
| Does the new tuple version fit on the page? | Row width and growth |
| What is the current table fillfactor? | reloptions |
| Does fillfactor apply to newly written pages? | Right physical table/partition |
| Does old data need a rewrite? | Locks/disk/availability |
| What is the HOT ratio? | n_tup_hot_upd/n_tup_upd |
| Do counters have a baseline/time window? | Avoid comparing raw cumulative sums |
| Are dead tuples climbing? | n_dead_tup/pgstattuple |
| What does FSM free space look like? | pg_freespace |
| Is vacuum keeping up? | last_autovacuum/count/duration |
| Are there long transactions? | Snapshots/xmin |
| Is index bloat shrinking? | Index sizes/statistics |
| Is heap size growing excessively? | pg_relation_size |
| Are sequential scans getting slower? | Buffers/read latency |
| What is the WAL volume? | Write amplification |
| Did replica lag change? | HA metrics |
| Are there no-op UPDATEs? | IS DISTINCT FROM |
| Are indexed columns updated unnecessarily? | Query/index review |
| Should hot/cold columns be split? | Model design |
| Are partition settings consistent? | Leaf reloptions |
| Is B-tree fillfactor being confused? | Check separately |
| Were multiple levels benchmarked? | 100/90/80/70 or as suited |
| Was concurrency tested? | Production-like workload |
| Was data correctness verified? | Constraints/transactions |
| Is there a VACUUM FULL/repack plan? | Locks/disk/rollback |
| Is post-deploy monitoring in place? | HOT, bloat, latency, WAL |
| Is there a setting rollback plan? | ALTER TABLE SET/RESET |
| Is tuning rationale documented? | Reasons and workload evidence |

## Conclusion

**Fillfactor, HOT updates, and page free space** are tightly connected concepts at the heap storage and MVCC layers. They help PostgreSQL process UPDATEs more efficiently, especially on tables with frequent changes to unindexed columns.

Key principles:

1. **UPDATEs generally create new tuple versions under MVCC.** Old versions must be kept until no snapshot needs them; VACUUM and pruning handle cleanup.
2. **HOT updates require the new version to fit on the same heap page without modifying index references under HOT rules.** Free space alone is not enough.
3. **HOT avoids new index entries for the new version.** This reduces index churn, index-related WAL, and bloat, while heap versions and heap WAL still occur.
4. **Heap table fillfactor creates HOT opportunities.** Lower values reserve room when writing new tuples, yet do not guarantee every UPDATE is HOT.
5. **Low fillfactor carries costs.** Larger heaps, more pages, sequential scans reading more blocks, and lower cache density.
6. **Index definitions dictate HOT eligibility.** Key columns, INCLUDE columns, expression dependencies, and partial predicates all matter; summarizing indexes have version-specific exceptions.
7. **Table fillfactor differs from B-tree index fillfactor.** Index fillfactor governs index page occupancy/splits and does not directly enable HOT on the heap.
8. **Changing fillfactor does not rewrite existing data.** Evaluate VACUUM FULL, CLUSTER, or repack tools if existing pages must be reorganized, accounting for locks and disk requirements.
9. **FSM, pgstattuple, and pg_stat_user_tables aid diagnosis.** Combine free space, dead tuples, HOT counters, and relation sizes rather than relying on one metric.
10. **VACUUM remains mandatory.** HOT does not remove the need to clean up dead tuples and HOT chains.
11. **Avoid indexing frequently changing columns unless queries require them.** Yet never drop critical indexes solely to boost the HOT ratio; measure both reads and writes.
12. **Tune using real workloads.** Compare fillfactor, HOT ratio, table/index sizes, WAL, autovacuum, replication lag, and latency before and after changes.

Good storage design does not try to pack every page to 100% or maximize HOT at all costs. It arranges data distribution so **UPDATEs run efficiently, indexes avoid unnecessary growth, VACUUM keeps pace, and read queries continue meeting operational SLAs**.
