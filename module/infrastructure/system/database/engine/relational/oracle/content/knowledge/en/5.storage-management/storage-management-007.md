# Extent Allocation, High Water Mark, and Impact on Scan Operations

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Storage  
> **Objective:** Understand how Oracle allocates space from data blocks to extents and segments, why the **High Water Mark (HWM)** affects the blocks examined during table scans, and distinguish the impacts of `INSERT`, `DELETE`, `TRUNCATE`, `SHRINK`, and `MOVE` on storage space.

## 1. Problem Statement: Few Rows Left Yet Scans Are Still Slow

Suppose an Oracle table once held 2 million records. After a data cleanup, the table has only 2,000 records remaining. A learner might expect every query to run roughly 1,000 times faster.

In reality, if the application performs a **full table scan**, Oracle may still have to traverse a very large region of segment blocks that had previously been used. The reason is that a `DELETE` operation removing rows **does not mean** the segment immediately shrinks or the **High Water Mark (HWM)** lowers automatically.

Three questions must be kept separate:

1. **How many rows still exist?** Relates to logical data.
2. **How many blocks/extents have been allocated?** Relates to the segment's physical space.
3. **Which block range falls inside the scan scope per the HWM?** Relates to how Oracle accesses data during a full scan.

These three numbers do not necessarily rise and fall together. This lesson focuses on the relationships among them and how to verify them in an Oracle environment.

## 2. Storage Structure: Tablespace → Segment → Extent → Block

Oracle manages space across key levels:

| Level | Concept | Role |
|---|---|---|
| **Tablespace** | Logical storage space backed by one or more datafiles | Organizes segments and allocates space for them |
| **Segment** | Set of extents belonging to a storage object | Stores data of a table, index, undo, a partition... |
| **Extent** | A group of contiguous Oracle blocks allocated within **one datafile** | Unit of space allocation/deallocation for a segment |
| **Oracle data block** | Fundamental logical storage and I/O unit of Oracle Database | Holds data rows, index entries, and block metadata |
| **Row** | A logical record; may span multiple row pieces/blocks depending on the case | Data manipulated by SQL |

Illustrative diagram:

```text
TABLESPACE USERS
│
├─ DATAFILE users01.dbf
│    ├─ Extent 0 of segment LAB_HWM
│    │    ├─ Block 0
│    │    ├─ Block 1
│    │    └─ ...
│    └─ Extent 2 of segment LAB_HWM
│         └─ ...
│
└─ DATAFILE users02.dbf
     └─ Extent 1 of segment LAB_HWM
          └─ ...

Segment LAB_HWM
  = Extent 0 + Extent 1 + Extent 2 + ...
```

A segment can consist of multiple extents, and extents of a segment can reside in different datafiles of the same tablespace. **Each extent** is a contiguous block region within **one** datafile; **the entire segment** does not need to be physically contiguous on disk.

### 2.1. Data Blocks Differ from Operating System Blocks

For example, an Oracle database might have `DB_BLOCK_SIZE = 8192` bytes, corresponding to a standard **8 KiB** block. However, this size depends on configuration, and a database can contain tablespaces with nondefault block sizes where supported.

Check the database setting:

```sql
SELECT name, value
FROM v$parameter
WHERE name = 'db_block_size';
```

The `V$PARAMETER` view requires appropriate privileges; only query it when your account has permission. Do not equate an Oracle data block with a physical disk sector, filesystem page, or network packet.

### 2.2. When Are Extents Allocated?

When a table/index needs more space and already-available blocks cannot accommodate it, Oracle can allocate a **new extent** from the tablespace to the segment. Each extent adds more blocks to the segment's allocated space.

In common **locally managed** tablespaces, the two extent allocation strategies are:

- **AUTOALLOCATE:** Oracle decides extent sizes via its space management mechanism.
- **UNIFORM:** every extent has a uniform size specified by the tablespace configuration.

Extents do not have to be equal in size when using AUTOALLOCATE. Illustrative example for a UNIFORM tablespace with 1 MiB extents and 8 KiB Oracle blocks:

```text
1 extent = 1 MiB = 1,048,576 bytes
1 block  = 8 KiB =     8,192 bytes

Blocks per extent = 1,048,576 / 8,192 = 128
```

This is an example calculation. Some blocks in a segment also serve metadata/space management, so you cannot conclude every allocated block holds exactly 8 KiB of user data.

### 2.3. Segment Creation Can Be Deferred

In many modern Oracle releases, a newly `CREATE TABLE`d table may **not have a physical segment yet** if **deferred segment creation** is active. The first segment/extent is created when data is inserted or an operation requires space.

For example:

```sql
CREATE TABLE lab_empty (
    id NUMBER
);
```

Not seeing a row in `USER_SEGMENTS` right after `CREATE TABLE` is not necessarily an error. When you want to force immediate segment creation in a lab, you can specify:

```sql
CREATE TABLE lab_with_segment (
    id NUMBER
)
SEGMENT CREATION IMMEDIATE;
```

Syntax and privileges must align with version, tablespace, and environment policies.

## 3. Extent Allocation and Free Space Management Inside a Segment

### 3.1. Space Regions Are Not All Alike

A segment can contain:

1. **Allocated blocks currently holding data.**
2. **Allocated blocks below the HWM that have free space to accept more rows.**
3. **Allocated blocks above the HWM that have not yet been brought into the used data region.**
4. **Extents not yet allocated to any segment, still free in the tablespace.**

These regions produce different behaviors. Oracle can reuse free space inside blocks in the second region during **conventional inserts**; if more usable space is needed, the segment can advance into blocks above the HWM or request a new extent.

**Do not misunderstand:** "Many free bytes remain in the tablespace" does not mean "the table can shrink immediately" or "full scans will read only a few blocks." Tablespace free space, in-segment free space, and HWM position are three distinct concepts.

### 3.2. ASSM and MSSM

There are two in-segment free-space management mechanisms learners commonly encounter:

- **ASSM (Automatic Segment Space Management):** Oracle uses bitmaps to track relative block fullness and pick blocks with free space. This is the common choice for new tablespaces.
- **MSSM (Manual Segment Space Management):** uses freelists and related parameters; may be encountered in legacy systems.

ASSM concerns **free-space management inside a segment**, whereas AUTOALLOCATE/UNIFORM concerns **allocated extent sizes**. These two choices are not synonymous:

```text
TABLESPACE
  ├─ Extent allocation: AUTOALLOCATE / UNIFORM
  └─ Segment space management: AUTO / MANUAL
                               (ASSM / MSSM)
```

Depending on release/segment type, ASSM may use low HWM and high HWM mechanisms to distinguish fully formatted blocks from newly allocated regions; thus Oracle's actual block scanning/formatting implementation is more sophisticated than a single HWM line diagram. At a foundational level, the HWM remains the key boundary separating used segment space from unused allocated space.

### 3.3. Inspecting a Table's Extents and Segment

Assume table `LAB_HWM` has been created and has a segment:

```sql
SELECT segment_name, segment_type, tablespace_name,
       extents, blocks, bytes
FROM user_segments
WHERE segment_name = 'LAB_HWM'
  AND segment_type = 'TABLE';
```

Meaning:

- `EXTENTS`: number of extents in the segment.
- `BLOCKS`: **total blocks allocated** to the segment.
- `BYTES`: total allocated size; not the actual data size of rows.
- `TABLESPACE_NAME`: tablespace holding the segment.

View each extent:

```sql
SELECT extent_id, file_id, block_id, blocks, bytes
FROM user_extents
WHERE segment_name = 'LAB_HWM'
  AND segment_type = 'TABLE'
ORDER BY extent_id;
```

Illustrative example:

| EXTENT_ID | FILE_ID | BLOCK_ID | BLOCKS |
|---:|---:|---:|---:|
| 0 | 7 | 128 | 8 |
| 1 | 7 | 136 | 8 |
| 2 | 7 | 256 | 128 |

The three extents can differ in size under the allocation policy; the table is simulated and does not represent every installation.

> **Scope:** Each partition of a partitioned table typically has its own segment; indexes also have separate segments. When inspecting an object with partitions/LOBs, check the exact `SEGMENT_TYPE` and corresponding segments rather than searching only by table name.

## 4. What Is the High Water Mark (HWM)?

The **High Water Mark** is a logical boundary inside a segment indicating the block range that has been brought into active use starting from the beginning of the segment. For a **standard full table scan**, Oracle examines blocks in the region below the relevant segment's HWM; blocks that are allocated yet have never entered the region below the HWM do not need to be scanned as table data.

Imagine 12 blocks of a table:

```text
Segment LAB_HWM, allocated blocks:

[0][1][2][3][4][5][6][7][8][9][10][11]
 |  |  |  |  |  |  |  |  |   |  |  |
 D  D  F  F  F  F  F  .  .  .   .  .
                     ^
                    HWM

D = contains data
F = previously used, now has no rows (e.g., after DELETE)
. = allocated but unused, above the HWM

Full table scan: region [0..6] must be examined.
Does not blindly scan [7..11] merely because they are allocated.
```

This is a **logical** diagram; metadata blocks, bitmaps, and Oracle's I/O read paths are omitted. In modern ASSM, there are also low/high HWM details as mentioned, and the SQL engine can apply other optimizations. The diagram focuses on the essence: **the HWM is a critical scan boundary, not a counter of currently existing rows**.

### 4.1. When Does the HWM Rise?

When insert operations require new blocks beyond the previously used region, Oracle can **advance the HWM**. A segment may be allocated a new extent before or while expanding its used region.

Example:

```text
Step A: 5 used blocks        [D][D][D][D][D][.][.][.]
                                 HWM ^ (after block 4)

Step B: insert more rows     [D][D][D][D][D][D][D][.]
                                       HWM ^ (after block 6)
```

Blocks below the HWM are not necessarily full. After many inserts/deletes, the segment can have scattered gaps throughout the used region.

### 4.2. The HWM Does Not Automatically Drop on DELETE

Suppose 8 blocks were used and then almost all rows were deleted:

```text
Before DELETE:
[D][D][D][D][D][D][D][D][.][.]
                         ^
                        HWM

After DELETE:
[D][F][F][F][F][F][F][F][.][.]
                         ^
                        HWM stays nearly unchanged
```

`DELETE` removes rows and generates undo/redo per transaction mechanics, yet does not automatically reclaim segment blocks or push the HWM downward. Free space below the HWM can be reused by subsequent **conventional INSERTs**.

**Consequence:** A table with very few remaining rows may still force a full table scan to inspect many blocks that once held data.

### 4.3. HWM Differs from Allocated Block Count

There can be:

- **Allocated blocks:** all blocks belonging to extents assigned to the segment.
- **Blocks below HWM:** blocks already within the segment's used/scan range.
- **Blocks actually containing rows:** blocks currently holding live rows.

These three numbers do not have to match. `USER_SEGMENTS.BLOCKS` reflects allocated blocks, so never use it directly as a metric for "blocks below HWM" or "blocks currently containing data".

## 5. How Does the HWM Affect Full Table Scans?

### 5.1. Nature of a Full Table Scan

A **full table scan** reads the table's data block range rather than using an index to locate a small subset of rows. Oracle usually reads via multiblock I/O; depending on the situation it may use the buffer cache or direct path reads, serial or parallel scans.

In principle, the range to inspect is heavily governed by the span **below the HWM**. Suppose two tables both have **1,000 existing rows**, yet:

- Table **A** freshly inserted 1,000 rows into a small set of blocks.
- Table **B** once held 1,000,000 rows and then `DELETE`d down to 1,000.

If B has not compacted its segment/HWM, a full table scan on B may have to process significantly more blocks. Filtering down to return few rows does not shrink the full scan's block range.

### 5.2. "Scanning up to the HWM" Does Not Mean Every Block Causes One Physical I/O

Do not conclude the number of blocks below the HWM equals the exact count of disk reads:

- Blocks already in the **buffer cache** may not require another physical read.
- Multiblock I/O can read multiple blocks in a single request.
- Direct path reads, parallel query, partition pruning, and storage optimizations can alter execution.
- Oracle may skip or handle certain block regions specially via internal metadata/bitmaps.
- A query using a suitable **index** may avoid a full table scan altogether.

The HWM governs scan scope, while execution time also depends on cache, I/O, CPU, predicates, execution plan, and workload.

### 5.3. Which Statements Actually Perform a Full Scan?

Example:

```sql
SELECT COUNT(*)
FROM lab_hwm;
```

This statement is **not guaranteed** to always use a full table scan. If a suitable index exists and the optimizer chooses an index fast full scan, the access path differs. You must inspect the execution plan.

Example checking the estimated plan:

```sql
EXPLAIN PLAN FOR
SELECT COUNT(*)
FROM lab_hwm;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

In a lab table with no index on `LAB_HWM`, the optimizer normally chooses `TABLE ACCESS FULL`. If partitioned, the plan may apply partition pruning; each partition has its own segment/HWM.

### 5.4. Reducing Row Count Differs from Reducing Scan Range

Suppose before cleanup:

```text
Row count:                  500,000
Blocks below HWM:            10,000 (illustrative)
Allocated extents:               80
```

After `DELETE`ing 99%:

```text
Row count:                    5,000
Blocks below HWM:           ~10,000 (may stay nearly unchanged)
Allocated extents:               80 (usually unchanged)
```

A full scan does not automatically become 100× cheaper. However, a selective **index range scan** for a matching predicate may touch very few blocks; that does not negate the HWM's impact on full table scans.

### 5.5. Why Do Optimizer Statistics Not Fix the HWM?

`DBMS_STATS.GATHER_TABLE_STATS` refreshes statistics used by the optimizer, such as row count and used blocks per stats. It does **not** automatically compact rows or lower the HWM just because the table now has less data.

If the row count dropped, the optimizer may switch execution plans based on new statistics. That changes the **access path**, which is not equivalent to **reclaiming physical space**.

## 6. DML/DDL Operations Affecting HWM and Extents

| Operation | Typical Impact on HWM | Impact on Allocated Extents | Meaning for Full Scans |
|---|---|---|---|
| **Conventional INSERT** | Can reuse free space below HWM; HWM rises when new block regions are needed | Can request new extents when space runs out | Scan scope can grow as HWM rises |
| **Direct-path INSERT** (e.g., `APPEND`, if Oracle actually uses direct path) | Typically writes above HWM and advances HWM upon appropriate completion | Can extend segment / allocate extents | Can raise HWM even when empty space exists below |
| **UPDATE** | Usually modifies rows in used blocks; may need extra room, row migration/chaining, or expansion in some cases | Does not necessarily change; can grow depending on row size and remaining space | Depends on block distribution changes and HWM |
| **DELETE** | Usually **does not lower HWM** | Usually retains extents | Many empty blocks below HWM may remain inside scan range |
| **TRUNCATE TABLE ... DROP STORAGE** | Resets the segment's HWM | Can release unneeded extents per segment rules | Full scan on empty table touches very few blocks |
| **TRUNCATE TABLE ... REUSE STORAGE** | Resets the HWM | Keeps most/allocated extents for reuse | Low HWM even though `USER_SEGMENTS.BLOCKS` may stay large |
| **ALTER TABLE ... SHRINK SPACE** | Can lower HWM after compact and shrink steps | Can return excess space to the tablespace | Can shrink full scan scope |
| **ALTER TABLE ... MOVE** | Rebuilds table storage into a new segment; HWM matches new segment | Can move/reallocate extents depending on options | Can eliminate large empty regions; watch ROWIDs/indexes |
| **DROP TABLE ... PURGE** | No table segment remains to scan | Returns space per object/tablespace management | No object left to full-scan |

This table describes typical behavior for **heap tables**. Index-organized tables, LOBs, partitioned objects, and compression/storage options follow their own rules.

### 6.1. DELETE: Rollbackable, Does Not Reclaim Extents Automatically

`DELETE` is DML that can be rolled back before commit:

```sql
DELETE FROM lab_hwm
WHERE id > 100;

COMMIT;
```

Oracle marks/deletes rows transactionally and generates undo/redo. Even after commit, `USER_SEGMENTS.BYTES` and the HWM generally do not shrink proportionally to deleted rows. If the application is about to insert new data, that space can be usefully reused.

### 6.2. TRUNCATE: Clears All Rows and Resets HWM

`TRUNCATE TABLE` is DDL, typically much faster than deleting row by row when removing all data. It performs an implicit commit per DDL semantics and cannot be rolled back like an uncommitted `DELETE`.

```sql
TRUNCATE TABLE lab_hwm DROP STORAGE;
```

or:

```sql
TRUNCATE TABLE lab_hwm REUSE STORAGE;
```

Both remove all rows and reset the HWM; the big difference is **releasing extents** versus **retaining extents for reuse**. `DROP STORAGE` normally retains minimum initial space per segment properties rather than guaranteeing `0 bytes`. `REUSE STORAGE` can avoid re-allocating extents when the application plans to reload large amounts of data.

Apply `TRUNCATE` only when **deleting all data is permitted**. On systems with foreign keys, materialized view logs, flashback, or other operational constraints, truncating also requires checking object prerequisites, syntax, and side effects.

### 6.3. SHRINK SPACE: Compacts and Lowers HWM

For **heap tables** in tablespaces using **ASSM**, `ALTER TABLE ... SHRINK SPACE` can move rows to fill gaps, lower the HWM, and return unneeded space.

Typical workflow:

```sql
ALTER TABLE lab_hwm ENABLE ROW MOVEMENT;

ALTER TABLE lab_hwm SHRINK SPACE COMPACT;

ALTER TABLE lab_hwm SHRINK SPACE;
```

- `ENABLE ROW MOVEMENT` permits Oracle to move rows to other blocks, which can **change ROWIDs**. Applications must not assume ROWIDs are immutable.
- `SHRINK SPACE COMPACT` compacts data without **yet executing the final HWM-lowering/space-release step**; useful when separating row-rearrangement from HWM adjustment.
- `SHRINK SPACE` completes the appropriate shrink operation, including lowering the HWM and returning space.

If phasing is unnecessary, eligible tables can run `SHRINK SPACE` directly. These commands can generate redo/undo, consume I/O, change ROWIDs, and hold locks during phases; not every segment type or configuration supports shrink.

### 6.4. MOVE: Rebuilding the Segment

`ALTER TABLE ... MOVE` essentially reorganizes the table's storage into a rebuilt segment. If a table has many empty blocks from `DELETE`s, rebuilding can pack the data region much more tightly.

General form example:

```sql
ALTER TABLE lab_hwm MOVE;
```

Considerations:

- Rows can change **ROWID**.
- Related indexes may need maintenance/rebuilding depending on release, index type, and online/offline options; never assume indexes stay usable across every MOVE variant.
- May require extra temporary space or room for the new segment; can impact DML/concurrent sessions.
- `MOVE ONLINE` behavior and support depend on release, edition, and table characteristics.

This is a physical reorganization with operational impact, not a default cure for every large table.

## 7. Why Can APPEND Cause the HWM to Rise Quickly?

**Conventional** inserts generally prioritize blocks with available room, including free space below the HWM. **Direct-path INSERTs** typically insert into new regions above the HWM to optimize bulk data loading.

Syntax example asking the optimizer to consider direct path:

```sql
INSERT /*+ APPEND */ INTO lab_hwm (id, payload)
SELECT level, RPAD('A', 80, 'A')
FROM dual
CONNECT BY level <= 10000;

COMMIT;
```

Runtime conditions decide whether Oracle uses direct path or falls back to conventional insert; hints do not guarantee identical execution in every environment. Direct-path inserts also impose specific concurrency/transaction restrictions and effects.

Typical scenario:

1. A table once held huge row counts, then nearly everything was `DELETE`d → many empty blocks below the HWM.
2. Conventional inserts can reuse those blocks.
3. Direct-path inserts can append above the HWM, growing the segment even though space remains empty below.

Thus, choosing a data loading method must match throughput, concurrency, and storage capacity goals.

## 8. Experiment: INSERT → DELETE → Observe Scan → SHRINK

Run the following experiment **only in a lab schema** on a self-created table `LAB_HWM`. Never run it on production tables. The account needs table creation privilege and appropriate tablespace quota. If lacking privileges for `DBMS_STATS`, `DBMS_XPLAN`, or `DBMS_SPACE`, use authorized queries or ask a DBA for assistance.

### 8.1. Create a Table Without Indexes

```sql
CREATE TABLE lab_hwm (
    id      NUMBER NOT NULL,
    payload VARCHAR2(200 CHAR) NOT NULL
)
SEGMENT CREATION IMMEDIATE;
```

Leaving out indexes keeps the example simple: `COUNT(*)` will typically read the table segment directly.

### 8.2. Insert Many Rows to Expand Storage

```sql
INSERT INTO lab_hwm (id, payload)
SELECT level, RPAD('X', 120, 'X')
FROM dual
CONNECT BY level <= 30000;

COMMIT;

SELECT COUNT(*) AS row_count
FROM lab_hwm;
```

Expected result `ROW_COUNT = 30000`. Depending on block size and available space, actual extent and block counts vary across systems.

Inspect allocation:

```sql
SELECT segment_name, extents, blocks, bytes
FROM user_segments
WHERE segment_name = 'LAB_HWM'
  AND segment_type = 'TABLE';

SELECT extent_id, file_id, block_id, blocks
FROM user_extents
WHERE segment_name = 'LAB_HWM'
  AND segment_type = 'TABLE'
ORDER BY extent_id;
```

Gather optimizer statistics:

```sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname => USER,
    tabname => 'LAB_HWM'
  );
END;
/
```

Then:

```sql
SELECT table_name, num_rows, blocks, empty_blocks, last_analyzed
FROM user_tables
WHERE table_name = 'LAB_HWM';
```

`USER_TABLES.NUM_ROWS`, `BLOCKS`, and `EMPTY_BLOCKS` are **statistics** as of gather time, not instant live counters across transactions. In typical interpretation, `USER_TABLES.BLOCKS` reflects used blocks below the HWM per stats; it differs from **total allocated blocks** in `USER_SEGMENTS.BLOCKS`.

### 8.3. Record the Execution Plan Before Deleting

```sql
EXPLAIN PLAN FOR
SELECT COUNT(*)
FROM lab_hwm;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

For an unindexed table like this, the plan usually contains:

```text
TABLE ACCESS FULL  LAB_HWM
```

`EXPLAIN PLAN` shows an **estimated plan**; it does not report actual blocks read or actual runtime. When authorized to view cursor statistics, you can run:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS FULL(t) */ COUNT(*)
FROM lab_hwm t;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR(
    NULL, NULL, 'ALLSTATS LAST'
));
```

`GATHER_PLAN_STATISTICS` collects runtime execution stats for the query when supported by Oracle; `ALLSTATS LAST` displays stats from the latest execution such as rows, buffer gets, and I/O info. Dynamic performance view access and selecting the right cursor depend on environment permissions; if unauthorized, stick to `EXPLAIN PLAN`.

For reliable comparisons, use the same client/session when possible and remember subsequent runs benefit from warmer cache.

### 8.4. DELETE Almost All Rows and Measure Again

```sql
DELETE FROM lab_hwm
WHERE id > 100;

COMMIT;

SELECT COUNT(*) AS row_count
FROM lab_hwm;
```

Result leaves `100` rows. Check allocated blocks/extents:

```sql
SELECT extents, blocks, bytes
FROM user_segments
WHERE segment_name = 'LAB_HWM'
  AND segment_type = 'TABLE';
```

In the typical case, segment `EXTENTS`, `BLOCKS`, and `BYTES` **do not drop significantly solely from DELETE**.

Re-gather stats after delete:

```sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname => USER,
    tabname => 'LAB_HWM'
  );
END;
/

SELECT num_rows, blocks, empty_blocks
FROM user_tables
WHERE table_name = 'LAB_HWM';
```

Observations:

- `NUM_ROWS` is close to the new row count (100), if gather succeeded properly.
- `BLOCKS` per stats may still look large relative to 100 rows because the region below the HWM has not been compacted.
- `USER_SEGMENTS.BLOCKS` still reflects allocated space, which may exceed `USER_TABLES.BLOCKS`.

Check the plan/scan again:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS FULL(t) */ COUNT(*)
FROM lab_hwm t;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR(
    NULL, NULL, 'ALLSTATS LAST'
));
```

Even with only 100 rows left, a full table scan may still examine a large block region below the HWM. Never use a single elapsed-time measurement to prove exact HWM impact: cache, background I/O, and query stats also affect results.

### 8.5. Shrink the Segment and Observe Again

If the environment uses **ASSM** and the table is eligible for shrink:

```sql
ALTER TABLE lab_hwm ENABLE ROW MOVEMENT;

ALTER TABLE lab_hwm SHRINK SPACE COMPACT;

ALTER TABLE lab_hwm SHRINK SPACE;
```

Inspect:

```sql
SELECT COUNT(*) AS row_count
FROM lab_hwm;

SELECT extents, blocks, bytes
FROM user_segments
WHERE segment_name = 'LAB_HWM'
  AND segment_type = 'TABLE';
```

Re-gather statistics:

```sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname => USER,
    tabname => 'LAB_HWM'
  );
END;
/

SELECT num_rows, blocks, empty_blocks
FROM user_tables
WHERE table_name = 'LAB_HWM';
```

Retry the full scan to observe metrics:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS FULL(t) */ COUNT(*)
FROM lab_hwm t;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR(
    NULL, NULL, 'ALLSTATS LAST'
));
```

If shrink succeeded, the HWM and full table scan range **can drop markedly**. Depending on remaining rows, row size, metadata, and allocation mechanisms, post-shrink segment size will not necessarily shrink down to the theoretical minimum block count.

When row movement is no longer needed for the lab, you can restore it:

```sql
ALTER TABLE lab_hwm DISABLE ROW MOVEMENT;
```

This is an operational choice per needs; disabling row movement again does not revert already-changed ROWIDs back to old values.

### 8.6. Alternative Experiment with TRUNCATE

If you want to observe the HWM reset while keeping extents, after finishing the earlier test branch on the lab table:

```sql
TRUNCATE TABLE lab_hwm REUSE STORAGE;

SELECT COUNT(*) FROM lab_hwm;

SELECT extents, blocks, bytes
FROM user_segments
WHERE segment_name = 'LAB_HWM'
  AND segment_type = 'TABLE';
```

Now the table has no rows and the HWM has been reset, while allocated extents may remain substantial because `REUSE STORAGE` was chosen. This directly illustrates that **allocated space** and **HWM scan range** are two different quantities.

To drop the lab table when finished:

```sql
DROP TABLE lab_hwm PURGE;
```

`DROP TABLE ... PURGE` removes the object from the schema without placing it into the recycle bin; run only on **your self-created lab table** after confirming the data is no longer needed.

## 9. Measuring HWM and Unused Space with DBMS_SPACE

`USER_SEGMENTS` shows total allocated extents/blocks; to estimate unused space above the HWM, you can use the **`DBMS_SPACE`** package in authorized environments.

### 9.1. DBMS_SPACE.UNUSED_SPACE

Example for a non-partitioned heap table:

```sql
SET SERVEROUTPUT ON

DECLARE
  l_total_blocks          NUMBER;
  l_total_bytes           NUMBER;
  l_unused_blocks         NUMBER;
  l_unused_bytes          NUMBER;
  l_last_used_extent_file NUMBER;
  l_last_used_extent_blk  NUMBER;
  l_last_used_block       NUMBER;
BEGIN
  DBMS_SPACE.UNUSED_SPACE(
    segment_owner              => USER,
    segment_name               => 'LAB_HWM',
    segment_type               => 'TABLE',
    total_blocks               => l_total_blocks,
    total_bytes                => l_total_bytes,
    unused_blocks              => l_unused_blocks,
    unused_bytes               => l_unused_bytes,
    last_used_extent_file_id   => l_last_used_extent_file,
    last_used_extent_block_id  => l_last_used_extent_blk,
    last_used_block            => l_last_used_block
  );

  DBMS_OUTPUT.PUT_LINE(
    'Total allocated blocks: ' || l_total_blocks
  );
  DBMS_OUTPUT.PUT_LINE(
    'Unused blocks above HWM: ' || l_unused_blocks
  );
  DBMS_OUTPUT.PUT_LINE(
    'Last used block in extent: ' || l_last_used_block
  );
END;
/
```

The total and unused fields reflect allocated/unused space as documented by the package; never treat their difference as the exact **count of blocks holding rows**.

**Case after DELETE:** Most blocks become empty yet remain **below the HWM**; therefore `UNUSED_BLOCKS` (unused space above the HWM) might **not increase proportionally** to the deleted rows. This is crucial when interpreting output.

`LAST_USED_BLOCK` indicates the last used block offset within the last extent reported by the package interface; it does not substitute for an "absolute HWM block_id" shared across all datafiles.

### 9.2. DBMS_SPACE.SPACE_USAGE and ASSM

With ASSM, `DBMS_SPACE.SPACE_USAGE` provides block distribution across space-usage levels (such as percentage free-space bands). High-free-space block buckets can increase after `DELETE`, even while the HWM stays unchanged.

Conceptually:

```text
UNUSED_SPACE:
    Focuses on unused blocks above the HWM.

SPACE_USAGE in ASSM:
    Focuses on fullness/emptiness of managed blocks
    across different free-space bands.

USER_SEGMENTS:
    Total allocated extents/blocks.

USER_TABLES statistics:
    Optimizer information, fresh only when gathered.
```

Use the right measurement for the right question. Some Oracle versions/segment types add parameters or restrictions in `DBMS_SPACE`, so check the API for your running Oracle version.

## 10. Three Easily Confused Operational Phenomena

### 10.1. "The Tablespace Has Free Space—Why Are Full Scans Still Slow?"

Tablespace free space indicates space **not yet allocated** to segments. It does not immediately alter blocks below the HWM of a table allocated earlier.

Example:

```text
TABLESPACE USERS: 50 GiB free
SEGMENT HISTORY_LOG: 10 GiB allocated
Remaining rows:      10,000
HWM remains high from previously holding tens of millions of rows
```

Having many free GiB in the tablespace does not make a scan on `HISTORY_LOG` automatically skip empty blocks below the HWM. To diagnose, examine the plan, segment stats, and how the table is accessed.

### 10.2. "After DELETE, the Table Is Small Yet USER_SEGMENTS.BYTES Didn't Shrink"

This is normal behavior: `DELETE` removes rows and leaves space for reuse; retaining extents is beneficial if the table will receive inserts again. If the table will soon grow back, shrinking only to reallocate can cause unnecessary I/O and administrative work.

### 10.3. "After TRUNCATE REUSE STORAGE, the Segment Is Still Big Yet Full Scans Do Very Little Work"

`TRUNCATE REUSE STORAGE` resets the HWM while keeping extents for reuse. Therefore:

- `USER_SEGMENTS.BYTES` can remain large.
- The table currently has zero rows.
- Full table scan scope on the empty table is reduced per the HWM, without having to scan all allocated extents.

This is the clearest illustration distinguishing **allocated space** from **scan range**.

## 11. How Does Partitioning Change Scan Scope?

A partitioned table usually has a **separate segment per partition**, each with its own extents and HWM. When query predicates allow **partition pruning**, Oracle only needs to scan relevant partitions instead of the entire table.

Conceptual example:

```text
TABLE SALES
├─ PARTITION P2024: separate segment + HWM
├─ PARTITION P2025: separate segment + HWM
└─ PARTITION P2026: separate segment + HWM
```

Query:

```sql
SELECT COUNT(*)
FROM sales
WHERE sale_date >= DATE '2026-01-01'
  AND sale_date <  DATE '2027-01-01';
```

If partitioning and predicate patterns align, the optimizer may scan only `P2026`. In that case, **the HWMs of P2024/P2025 lie outside the query's scan scope**.

Conversely, with predicates that prevent pruning, Oracle may have to scan multiple segments. When purging data over time, an appropriate partition management strategy can be far more efficient than `DELETE`ing millions of rows, though `TRUNCATE PARTITION`/`DROP PARTITION` is DDL with impacts on data, indexes, and applications that must be carefully designed.

## 12. Does the HWM Relate to Index Scans?

An index is also a segment with its own blocks and extents, yet the common access structure of a **B-tree index** differs from a heap table.

- An **index range scan** traverses branch/leaf blocks by key, generally avoiding scanning the table up to the HWM just to find a small group of rows.
- An **index fast full scan** reads the entire index via an appropriate method; it can serve as an alternative to a table full scan when the index contains enough columns to answer the query.
- The table may still be accessed by ROWID from the index, making actual table blocks read depend on row distribution, clustering factor, cache, etc.
- Deleting rows can leave empty space inside indexes; index space reuse/maintenance does not behave identically to lowering a heap table's HWM.

Therefore, **"high HWM" does not mean every SQL query against the table is slow**. Inspect whether SQL uses `TABLE ACCESS FULL`, `INDEX RANGE SCAN`, `INDEX FAST FULL SCAN`, or another access path before choosing a remediation.

## 13. Considerations When Wanting to Reduce Scan Time

If a table has a high HWM and full scans become a bottleneck, do not run `SHRINK` or `MOVE` immediately. Answer several technical questions first:

| Question | Why Must It Be Answered? |
|---|---|
| Do real queries actually use `TABLE ACCESS FULL`? | If plans use indexes/partition pruning, table-wide HWM may not be the main bottleneck |
| Does the table regularly grow back with new data? | Shrinking may trigger unnecessary re-allocation |
| Is the amount of empty space below HWM truly large? | With few empty blocks, shrink benefits may be minimal |
| Are queries mainly waiting on I/O, CPU, or contention? | Solutions must target the actual root cause |
| Does the tablespace use ASSM and is the table eligible for `SHRINK`? | Not all segment types/configurations support shrink |
| Do apps store ROWIDs or rely on unchanging ROWIDs? | `SHRINK`/`MOVE` can change ROWIDs |
| Are there indexes, FKs, LOBs, partitions, compression, or special settings? | Maintenance/recovery impact and DDL restrictions can differ |
| Can the operation run during a maintenance window? | Shrinking/reorganizing segments generates I/O, redo/undo, and locks |

Options can include: keeping free space for reuse; improving indexes/predicates/partitioning; updating statistics; shrinking/moving during a maintenance window; or changing data retention policies via partitioning.

Do not rely solely on `USER_SEGMENTS.BYTES`: a table with fewer rows yet large extents is not necessarily a problem if critical queries already use selective access paths.

## 14. Notes on Statistics and Performance Measurement

### 14.1. Choose the Right Metric

| What to Evaluate | Appropriate Tool / Metric | What Not to Infer |
|---|---|---|
| Total allocated blocks | `USER_SEGMENTS.BLOCKS/BYTES/EXTENTS` | Do not directly infer blocks with rows or blocks below HWM |
| Extent list | `USER_EXTENTS` | Do not infer how many rows reside in each extent |
| Row and block counts per optimizer stats | `USER_TABLES.NUM_ROWS/BLOCKS` after `DBMS_STATS` | Do not assume live values after every DML |
| Unused region above HWM | `DBMS_SPACE.UNUSED_SPACE` | Does not measure empty pockets inside the region below HWM |
| Fullness of ASSM blocks | `DBMS_SPACE.SPACE_USAGE` | Does not prove a query will use a full scan |
| Estimated access path | `EXPLAIN PLAN` and `DBMS_XPLAN.DISPLAY` | Not actual runtime execution metrics |
| Access path and stats from one run | `DBMS_XPLAN.DISPLAY_CURSOR(..., 'ALLSTATS LAST')` when authorized and instrumented | Do not treat a single run's duration as a complete benchmark |

### 14.2. Avoid Comparing Single-Run Timings

If you run the same query twice, the second run can be faster because **the cache is warm**, not because the HWM changed. For rigorous performance investigation, measure multiple runs under comparable conditions and examine physical reads, buffer gets, rows processed, and execution plans. Wait events and I/O statistics help pinpoint causes.

### 14.3. Do Not Alter Live Environments with High-Impact Tests

Commands like `TRUNCATE`, `SHRINK`, `MOVE`, `APPEND` loads, and tricks that "force scans" can modify data or affect system stability. Only use tables in a lab schema. On systems with other users, gather evidence first, propose a plan, and execute changes under an approved change process.

## 15. Review Questions

### Question 1. How Does an Extent Differ from a Segment?

**Answer:** An extent is a unit of contiguous Oracle blocks allocated within one datafile. A segment is the set of extents storing data for an object such as a table or index. A segment can comprise multiple extents across multiple locations/datafiles in a tablespace.

### Question 2. Why Might Deleting 99% of Rows Not Proportionally Reduce Full Table Scan Work?

**Answer:** Because `DELETE` typically does not lower the HWM or return extents. Many empty blocks below the HWM remain inside the range a full table scan must examine.

### Question 3. Is `USER_SEGMENTS.BLOCKS` Equal to the Number of Blocks Below the HWM?

**Answer:** No. `USER_SEGMENTS.BLOCKS` reflects **allocated** blocks. The number of blocks below the HWM may be smaller, and the number of blocks actually holding rows may be smaller still.

### Question 4. What Differs Between `TRUNCATE DROP STORAGE` and `REUSE STORAGE`?

**Answer:** Both remove all rows and reset the HWM. `DROP STORAGE` can release unneeded extents, while `REUSE STORAGE` retains most allocated space for reloading data.

### Question 5. Why Is `SHRINK SPACE COMPACT` Not Equivalent to a Full `SHRINK SPACE`?

**Answer:** The `COMPACT` phase mainly rearranges rows to consolidate free space; only a full `SHRINK SPACE` adjusts the HWM and releases eligible space. You must check ASSM, row movement, and segment-type support.

### Question 6. Can Optimizer Statistics Be Used to "Lower the HWM"?

**Answer:** No. `DBMS_STATS` updates statistics so the optimizer can choose plans; it does not compact/lower the HWM or release extents.

### Question 7. Does `APPEND` Always Reuse Empty Blocks Below the HWM?

**Answer:** No. Direct-path insert typically writes above the HWM; conventional insert is what typically reuses blocks below the HWM. Oracle uses direct path only when execution conditions allow.

### Question 8. A Table Has a High HWM Yet SQL Uses an Index Range Scan. Must the Table Be Shrunk?

**Answer:** No. Identify the real bottleneck, accessed blocks, and workload. The HWM mainly matters for full scan scope; deciding to shrink/move requires measurements and weighing operational impact.

---

## 16. Summary of Key Relationships

```text
TABLESPACE has free space
    |
    v
Oracle allocates EXTENTS to SEGMENT when needed
    |
    v
SEGMENT has allocated blocks
    |
    +-- Region below HWM: brought into active use;
    |                     may hold many empty blocks after DELETE
    |
    +-- Region above HWM: allocated but not yet used
                          within current data scan scope

Conventional INSERT  -> can reuse free space below HWM
Direct-path INSERT   -> usually uses new region above HWM
DELETE               -> removes rows, HWM usually does not drop
TRUNCATE             -> resets HWM; DROP/REUSE differ on extents
SHRINK / MOVE        -> can compact or reorganize segment
DBMS_STATS           -> updates optimizer stats, does not lower HWM

FULL TABLE SCAN      -> HWM affects the block range to examine
INDEX / PARTITION    -> can let queries access a smaller scope
```

When analyzing a slow Oracle query after a large data deletion, separate **row count**, **extent allocation**, **HWM**, **execution plan**, and **actual I/O**. Only when evidence shows a wide scan region below the HWM is a significant factor are segment compaction/reorganization measures justified.

### Recommended Oracle Documentation

- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — Data Blocks, Extents, Segments, tablespaces, and storage space management.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — `TRUNCATE TABLE`, `ALTER TABLE ... SHRINK SPACE`, `ALTER TABLE ... MOVE`, and applicable constraints.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — `DBMS_SPACE.UNUSED_SPACE`, `DBMS_SPACE.SPACE_USAGE`, `DBMS_STATS`.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — Full table scans, execution plans, optimizer statistics, and reading I/O metrics.

Views, privileges, shrink eligibility, and block allocation details depend on Oracle version/edition and segment type. Always verify against the exact documentation for the database in use when applying to a live environment.
