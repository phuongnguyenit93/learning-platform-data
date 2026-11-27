# Reclaiming Space with Shrink, Move, and Segment Reorganization

In Oracle Database, **deleting rows does not immediately release space allocated to a table**. A table can shrink from millions of rows down to a few thousand rows yet still retain many blocks and extents for reuse. If the table is frequently scanned in full, blocks below the high-water mark (HWM) can continue affecting data-read work. If a tablespace is running low on space, a DBA may want to reclaim extents no longer serving current data.

Oracle provides **segment shrink**, **table move**, **index coalesce/rebuild**, and dedicated operations for partitions or LOBs. Each approach has distinct prerequisites, resource demands, and impacts on ROWIDs, indexes, transactions, and availability. This lesson explains how to choose between them and practice on a dedicated Oracle schema.

> Before reorganizing a segment, identify **at which level space is free** and whether you want to reclaim it back to the **segment, tablespace, or datafile**. Never run SHRINK or MOVE solely because many rows were deleted.

## 1. Understanding Space in Oracle

### 1.1. Block, Extent, Segment, Tablespace, and Datafile

~~~text
Oracle Database
  |
  +-- Tablespace APP_DATA
       |
       +-- Datafile 01, Datafile 02...
       |
       +-- TABLE segment DON_HANG
       |     +-- Extent A: multiple data blocks
       |     +-- Extent B: multiple data blocks
       |     +-- Extent C: multiple data blocks
       |
       +-- INDEX segment IDX_DON_HANG_NGAY
       |
       +-- LOB segment (if LOB data is stored separately)
~~~

| Unit | Meaning | Relation to Space Reclamation |
|---|---|---|
| **Data block** | Oracle's unit of data storage and access | Deleting rows can leave empty space inside blocks |
| **Extent** | Group of blocks allocated to one segment | Extents can stay with the segment after many rows are deleted |
| **Segment** | Set of extents dedicated to a table, index, LOB, or partition | SHRINK and MOVE reorganize how a segment uses space |
| **Tablespace** | Logical storage space containing segments | Returned extents can be allocated to other objects |
| **Datafile** | Physical file storing tablespace data | Returning extents to the tablespace does not automatically shrink the file on disk |

A single table can involve **multiple distinct segments**: the table segment, indexes, LOBs, and partition segments. Shrinking the table segment does not mean dependent segments have been shrunk as well.

### 1.2. High-Water Mark (HWM)

The high-water mark indicates the block region Oracle considers to have been used at the segment level. For heap tables, the HWM plays a role in access patterns such as full table scans.

~~~text
Before deleting many rows:
| row  | row  | row  | row  | row  | empty |
                                   ^ HWM

After DELETE:
| empty | empty | row  | empty | row  | empty |
                                      ^ HWM may remain unchanged

After compacting rows and lowering HWM (illustrative):
| row  | row  | empty | empty | empty | empty |
              ^ new HWM
~~~

**DELETE** marks/removes rows, creating space inside blocks for reuse when new data is inserted. However, regular DELETE **does not lower the HWM or return allocated extents to the tablespace**. Thus, row counts can drop sharply while segment size stays nearly constant.

Empty space is not always waste. If an application deletes and re-inserts a comparable volume of data every day, keeping blocks for reuse can be better than reclaiming and reallocating them.

### 1.3. Three Different Reclamation Goals

1. **Space inside a segment:** blocks with free space for the segment to reuse. DELETE can create this kind of space.
2. **Free space in the tablespace:** extents no longer belonging to a segment, available to serve other segments. Certain SHRINK/MOVE operations help achieve this.
3. **Physical datafile size:** file size at the storage layer. Reclaiming extents does not automatically shrink datafiles; a DBA must inspect extent locations and separate resize feasibility.

For example, reducing a table segment from 4 GB to 1 GB can return 3 GB to the tablespace, while a 10 GB datafile still stays 10 GB in size.

## 2. Measuring Current State Before Reorganizing

You need to know which segments are large, how many rows exist, how much data was deleted, whether the segment is likely to reuse free space soon, and whether the main goal is saving space or improving queries.

### 2.1. Checking Allocated Segment Space

~~~sql
SELECT segment_name,
       segment_type,
       tablespace_name,
       ROUND(bytes / 1024 / 1024, 2) AS allocated_mb,
       blocks,
       extents
FROM user_segments
WHERE segment_name IN (
    'LAB_REORG',
    'PK_LAB_REORG',
    'IX_LAB_REORG_NHOM'
)
ORDER BY segment_type, segment_name;
~~~

**USER_SEGMENTS.BYTES** is the number of bytes Oracle allocated to the segment—**not** total live business data size, and not the guaranteed reclaimable byte count. Part of that space accounts for block metadata, in-block free space, write headroom, and extent allocation policy.

### 2.2. Checking Table and Index Information

~~~sql
SELECT table_name,
       tablespace_name,
       num_rows,
       blocks,
       avg_row_len,
       last_analyzed
FROM user_tables
WHERE table_name = 'LAB_REORG';

SELECT index_name,
       index_type,
       status,
       tablespace_name
FROM user_indexes
WHERE table_name = 'LAB_REORG';
~~~

**NUM_ROWS**, **BLOCKS**, and **AVG_ROW_LEN** are optimizer statistics; they may be stale after a data purge. **COUNT(*)** gives the current row count, though on large tables it still carries a cost. Do not use a simple `NUM_ROWS × AVG_ROW_LEN` calculation to predict exact reclaimable extent space.

When deeper analysis of reclaimable space is needed, a DBA can use the **Segment Advisor** or suitable capabilities of **DBMS_SPACE**, depending on version, segment type, and access privileges.

### 2.3. ASSM Affects Shrink Capability

Segment shrink normally requires eligible objects to reside in a tablespace using **Automatic Segment Space Management (ASSM)**. Check with:

~~~sql
SELECT tablespace_name,
       contents,
       segment_space_management
FROM user_tablespaces
WHERE tablespace_name = 'APP_DATA';
~~~

`APP_DATA` is an illustrative name. For tablespaces using manual segment space management (MSSM), or object types that do not support shrink, choose a different method. Never retry repeatedly and assume errors are caused by missing privileges.

## 3. SHRINK SPACE: Compacting Rows and Lowering HWM

**Segment shrink** reorganizes space inside an eligible segment. Oracle can move live rows to pack them into fewer blocks, lower the HWM, and return unneeded extents to the tablespace.

For regular heap tables, because rows can change physical location, you must enable **row movement**:

~~~sql
ALTER TABLE lab_reorg ENABLE ROW MOVEMENT;
~~~

ROWIDs can change during shrink. Java applications should never store ROWID as a long-lived business key; use the primary key instead.

### 3.1. SHRINK SPACE COMPACT and SHRINK SPACE

~~~sql
-- Table must be shrink-eligible and reside in an ASSM tablespace.
ALTER TABLE lab_reorg ENABLE ROW MOVEMENT;

-- Compact rows, deferring the HWM-lowering step.
ALTER TABLE lab_reorg SHRINK SPACE COMPACT;

-- Finish lowering HWM and reclaim eligible extents.
ALTER TABLE lab_reorg SHRINK SPACE;
~~~

**SHRINK SPACE COMPACT** compacts data without performing the HWM adjustment step yet. **SHRINK SPACE** completes HWM reduction and extent reclamation where possible; it can also be run directly without having to run COMPACT first.

Splitting into two phases lets you schedule row movement and HWM adjustment at different times. The compaction phase can permit DML per Oracle's supported mechanism; lowering the HWM can require a brief lock. SHRINK still consumes CPU, I/O, undo, and redo, and can wait on locks; it does not mean completely zero-impact execution.

### 3.2. SHRINK SPACE CASCADE

~~~sql
ALTER TABLE lab_reorg SHRINK SPACE CASCADE;
~~~

The **CASCADE** option requests shrinking dependent objects supported by the object type and Oracle version, such as certain indexes. Do not assume CASCADE handles every LOB, domain index, partition, or special object.

After shrink finishes, if row movement is no longer required for other features:

~~~sql
ALTER TABLE lab_reorg DISABLE ROW MOVEMENT;
~~~

Do not disable row movement if the table has other requirements needing it, such as certain partition-key update scenarios.

### 3.3. Conditions to Evaluate

- Is the table a heap table or segment type supporting shrink?
- Does the tablespace use ASSM?
- Do any applications, triggers, or external processes rely on old ROWIDs?
- Are there LOBs, partitions, materialized views, or special index types needing separate handling?
- Can the current workload tolerate the I/O, undo, redo, and HWM-adjustment locks?
- Will new data soon be added back to reuse the free space?

**Not every table can use SHRINK SPACE.** Specialized segment types may have different syntax, limits, or reorganization methods.

## 4. MOVE: Rebuilding the Table Segment

**ALTER TABLE ... MOVE** moves or reorganizes a table segment. Oracle builds a target segment structure and copies live rows into it; upon successful completion, space from the old structure is handled per Oracle's mechanism.

~~~sql
-- Example for an eligible heap table, usually needing a maintenance window.
ALTER TABLE lab_reorg MOVE;
~~~

You can specify a target tablespace if prepared:

~~~sql
ALTER TABLE lab_reorg MOVE TABLESPACE APP_DATA_NEW;
~~~

`APP_DATA_NEW` is an illustrative name. Verify privileges, quotas, capacity, and storage policies of the target tablespace.

### 4.1. Comparing SHRINK and MOVE

| Criterion | SHRINK SPACE | MOVE |
|---|---|---|
| Approach | Compacts rows within the current segment and adjusts HWM | Creates a new segment, copies live rows |
| ASSM requirement | Typically requires ASSM for segment shrink | Does not require shrink's ASSM precondition |
| ROWID | Can change due to row movement | Usually changes due to moving to a new segment |
| Changing tablespace | Not its primary purpose | Can move to another tablespace |
| Resources | Moves/compacts rows inside segment, still generates I/O/undo/redo | Usually needs enough space for the new segment during the move |
| Index impact | Depends on shrink type and CASCADE option | Standard offline MOVE can make indexes UNUSABLE without index maintenance |
| Concurrent DML | May allow DML in certain phases; HWM-lowering phase needs locks | Offline MOVE can block DML; online depends on support |
| Goal | Reclaim free space after deletions | Reorganize or relocate storage |

**MOVE may require significant free space before releasing space**: during the move, both the old and new segments can occupy space simultaneously. If the tablespace is nearly full, MOVE may lack sufficient resources to finish.

### 4.2. Indexes After MOVE

Indexes typically use row locations (ROWIDs) to find data. When a heap table is moved via standard offline move, ROWIDs change, so related indexes can be marked **UNUSABLE** unless an appropriate index-maintenance mechanism is used.

After moving, inspect index status:

~~~sql
SELECT index_name, index_type, status
FROM user_indexes
WHERE table_name = 'LAB_REORG'
ORDER BY index_name;
~~~

For standard indexes in UNUSABLE state, rebuild according to plan:

~~~sql
ALTER INDEX pk_lab_reorg REBUILD;
ALTER INDEX ix_lab_reorg_nhom REBUILD;
~~~

In this example, the index names come from the practice section. If indexes have different names, fetch the actual names from `USER_INDEXES`. For partitioned tables, status at the index partition/subpartition level must also be checked.

### 4.3. MOVE ONLINE

Some Oracle releases support moving tables online when the object qualifies:

~~~sql
-- Execute only when version, edition, and table type support it.
ALTER TABLE lab_reorg MOVE ONLINE;
~~~

MOVE ONLINE aims to minimize DML disruption and includes appropriate index maintenance, yet still requires I/O, redo/undo, space for the new segment, and can acquire locks at certain stages. Tables with partitions, LOBs, or special indexes may carry specific limits. Never infer that "online" means no operational planning is needed.

## 5. INDEX Segments: COALESCE, SHRINK, and REBUILD

An index is a separate segment. Deleting many rows in a table can leave free space in B-tree index blocks, yet not every index needs rebuilding after a purge.

### 5.1. COALESCE

~~~sql
ALTER INDEX ix_lab_reorg_nhom COALESCE;
~~~

COALESCE reorganizes usable space across eligible B-tree leaf blocks so internal space can be reused. It **does not guarantee lowering the HWM or returning extents to the tablespace**.

### 5.2. Index SHRINK

For supported index types in an eligible environment:

~~~sql
ALTER INDEX ix_lab_reorg_nhom SHRINK SPACE;
~~~

Confirm ASSM preconditions and index type. Do not run this on bitmap, domain, partitioned, or specialized indexes without checking support first.

### 5.3. REBUILD

~~~sql
ALTER INDEX ix_lab_reorg_nhom REBUILD;
~~~

REBUILD recreates the index structure and can be suitable when an index is UNUSABLE after MOVE, when moving an index to another tablespace, or when evidence shows reorganization is needed. It consumes CPU, I/O, build space, and time.

| Current State | Option to Consider |
|---|---|
| Index UNUSABLE after offline MOVE | REBUILD or corresponding recovery mechanism |
| B-tree index still valid with lots of empty space | COALESCE or SHRINK if beneficial and supported |
| Need to move index to another tablespace | REBUILD variant with target destination |
| Index performing well, many INSERTs expected soon | Can leave as-is and reuse empty blocks |

Never apply a rigid rule of thumb like "deleting 20% of rows requires rebuilding every index." Base decisions on workload, space reuse, and measurable benefit.

## 6. Partitions, LOBs, and Special Objects

### 6.1. Partitioned Tables

Each partition/subpartition can have its own segment. If purging only an old partition, operating on that specific partition typically has less impact than reorganizing the entire table.

Illustrative example:

~~~sql
-- Assumes table, partition, and target tablespace exist.
ALTER TABLE don_hang_partitioned
    MOVE PARTITION p_2023 TABLESPACE APP_ARCHIVE;
~~~

When moving a partition, consider **local indexes**, **global indexes**, index maintenance options, and version-specific Oracle restrictions. For a partition past its retention period, `TRUNCATE PARTITION` or `DROP PARTITION` is sometimes preferable, though those are policy-driven data removal operations rather than mere space reclamation.

### 6.2. CLOB, BLOB, and LOB Segments

A table with CLOB/BLOB columns can consume most of its space in a separate LOB segment rather than the table segment. Check with:

~~~sql
SELECT table_name,
       column_name,
       segment_name,
       index_name,
       tablespace_name
FROM user_lobs
WHERE table_name = 'TEN_BANG_CO_LOB';
~~~

LOB shrink/move capability depends on **BasicFile/SecureFile**, Oracle version, segment type, and storage attributes. Some options use `MOVE LOB` variants; others have dedicated reclamation steps. Never arbitrarily apply heap-table commands to LOB segments.

### 6.3. IOTs, Clusters, and Other Structures

Index-organized tables (IOTs), clusters, materialized views, or domain indexes have distinct layouts and maintenance rules. Before choosing an operation, identify the **actual object type** and what your running Oracle release supports.

### 6.4. TRUNCATE Differs from SHRINK/MOVE

If all data in a **sandbox table** is no longer needed, you can run:

~~~sql
-- Run only when deleting all test data is permitted.
TRUNCATE TABLE lab_reorg DROP STORAGE;
~~~

TRUNCATE is DDL, follows implicit commit rules, and cannot be rolled back like an uncommitted DELETE. It is subject to foreign key, partition, and storage-attribute restrictions. **Table-wide TRUNCATE is unsuitable when some rows must be kept.**

## 7. Hands-On Practice in a Dedicated Oracle Schema

Example creating a table, loading data, deleting 80% of rows, and observing allocation before and after SHRINK or MOVE. Run **only in a practice schema** with privileges to create/drop tables and indexes. Exact sizes vary by block size, extent allocation, and how Oracle lays out data.

### 7.1. Create Table and Index

~~~sql
CREATE TABLE lab_reorg (
    id       NUMBER(8) CONSTRAINT pk_lab_reorg PRIMARY KEY,
    nhom     NUMBER(3) NOT NULL,
    payload  VARCHAR2(500 CHAR)
);

CREATE INDEX ix_lab_reorg_nhom
    ON lab_reorg (nhom);
~~~

Constraint `PK_LAB_REORG` normally creates a supporting index with that name when no other suitable index is already used. Always confirm actual names in `USER_INDEXES` before rebuilding.

### 7.2. Load Repeatable Data

~~~sql
INSERT INTO lab_reorg (id, nhom, payload)
SELECT LEVEL,
       MOD(LEVEL, 10),
       RPAD('X', 400, 'X')
FROM dual
CONNECT BY LEVEL <= 20000;

COMMIT;

SELECT COUNT(*) AS so_hang
FROM lab_reorg;
~~~

Expected row count is **20,000**. A 400-character payload makes segment changes easier to observe than storing just two integers. Record the baseline:

~~~sql
SELECT segment_name,
       segment_type,
       ROUND(bytes / 1024 / 1024, 2) AS allocated_mb,
       blocks,
       extents
FROM user_segments
WHERE segment_name IN (
    'LAB_REORG', 'PK_LAB_REORG', 'IX_LAB_REORG_NHOM'
)
ORDER BY segment_name;
~~~

### 7.3. Delete 80% of the Data

~~~sql
DELETE FROM lab_reorg
WHERE id <= 16000;

COMMIT;

SELECT COUNT(*) AS so_hang_con_lai
FROM lab_reorg;
~~~

Remaining row count is **4,000**, with IDs from 16001 to 20000. Query `USER_SEGMENTS` again: even though rows dropped sharply, the segment generally has not returned extents to the tablespace from `DELETE` alone.

### 7.4. Run SHRINK

If the heap table sits in an ASSM tablespace and meets prerequisites:

~~~sql
ALTER TABLE lab_reorg ENABLE ROW MOVEMENT;
ALTER TABLE lab_reorg SHRINK SPACE COMPACT;
ALTER TABLE lab_reorg SHRINK SPACE;

SELECT COUNT(*) AS so_hang_sau_shrink
FROM lab_reorg;
~~~

Row count must still equal **4,000**. Re-inspect `LAB_REORG` size via `USER_SEGMENTS` and index status via `USER_INDEXES`. Exact space reclaimed depends on row compaction and extent allocation; do not expect an exact 80% reduction.

~~~sql
SELECT index_name, status
FROM user_indexes
WHERE table_name = 'LAB_REORG'
ORDER BY index_name;
~~~

You can test `CASCADE` in a separate experiment if dependent segments support it and truly need reclamation.

### 7.5. MOVE as an Alternative Practice Method

**MOVE is not a mandatory step after SHRINK.** For a fair comparison, use a sandbox copy in the post-DELETE, pre-SHRINK state, then execute:

~~~sql
ALTER TABLE lab_reorg MOVE;

SELECT index_name, status
FROM user_indexes
WHERE table_name = 'LAB_REORG'
ORDER BY index_name;
~~~

If indexes are marked UNUSABLE, rebuild them:

~~~sql
ALTER INDEX pk_lab_reorg REBUILD;
ALTER INDEX ix_lab_reorg_nhom REBUILD;

SELECT COUNT(*) AS so_hang_sau_move
FROM lab_reorg;
~~~

Row count must still be **4,000**. Check index status, critical queries, and space after the operation. Even when using `MOVE ONLINE` or another index maintenance option, always verify actual metadata afterward.

### 7.6. Gather Statistics When Appropriate

After a major purge or segment reorganization, optimizer statistics may no longer reflect the new data. In a schema with appropriate privileges:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_REORG',
        cascade => TRUE
    );
END;
/
~~~

The trailing `/` is the SQL*Plus/SQLcl command to execute the PL/SQL block, not part of PL/SQL syntax. In production, follow your statistics gathering policy because updating stats can change execution plans.

### 7.7. Clean Up the Test Table

Once certain the sandbox data is no longer needed:

~~~sql
DROP TABLE lab_reorg PURGE;
~~~

`PURGE` avoids keeping the object in the recycle bin per normal behavior; use only on practice tables authorized for deletion. Never treat `DROP TABLE` as a way to undo a business table reorganization.

## 8. Impacts on ROWID, Indexes, Locks, and Transactions

### 8.1. ROWID Is a Location, Not a Persistent Key

A heap table's ROWID generally represents a row's physical location. SHRINK/MOVE can change ROWIDs. A Java application storing old ROWIDs and reusing them after maintenance may fail to find rows or point to the wrong locations.

Use a **primary key** or stable business key to identify rows in the application layer.

### 8.2. DDL and Implicit Commit

ALTER TABLE, ALTER INDEX, and TRUNCATE are DDL; Oracle enforces **implicit commit** rules. Do not treat them like an UPDATE that can be rolled back within a normal transaction. Avoid running maintenance DDL in the middle of incomplete business workflows.

Prepare a recovery plan, proper backups, and a maintenance window. Never assume `ROLLBACK` can reverse a completed `MOVE`.

### 8.3. Load and Concurrency

- `SHRINK SPACE COMPACT` supports separating row compaction from HWM adjustment, yet still consumes CPU/I/O/redo/undo.
- Finalizing `SHRINK` may require locks related to lowering the HWM.
- Offline `MOVE` can disrupt DML; `MOVE ONLINE`, where supported, reduces this restriction but can still take locks at certain points.
- Index rebuilds and statistics gathering can also impact resources and execution plans.
- Systems with standby/replication must account for redo volume and the impact of physical changes.

Neither SHRINK nor MOVE guarantees faster queries. If SQL is slow due to missing indexes, poor JOINs, bad plans, or returning too much data, reorganization does not replace SQL tuning. Measure key queries before and after the operation.

## 9. Why Might the Datafile Still Not Shrink?

Suppose SHRINK returns several GB of extents to the tablespace. Those extents might sit **in the middle of the datafile**, while other active extents still sit near the end:

~~~text
Datafile:
| in use | free | in use | free | in use | free |
                                      ^
                        Extent still present near end
~~~

To reduce physical file size, the DBA must assess **whether the tail end of the datafile is truly empty and reclaimable**. A tablespace with large total free space does not mean every datafile can be resized smaller proportionally.

With ASM, filesystems, cloud storage, or thin provisioning, physical space reclamation and billing also depend on the underlying storage layer. Therefore, measure goals at the appropriate layer, not solely in `USER_SEGMENTS`.

## 10. Choosing a Method by Scenario

| Context | Option to Consider | Reason |
|---|---|---|
| Frequent deletes followed by inserts of similar scale | **May leave as-is** | Reuses free blocks instead of releasing and reallocating |
| Heap table on ASSM, many rows deleted, need to return extents | **SHRINK SPACE** if eligible | Compacts rows, lowers HWM |
| Want to separate row compaction from HWM-lowering phase | **COMPACT then SHRINK** | Easier operational scheduling |
| Need to move table to another tablespace | **MOVE** | Rebuilds segment at target destination |
| Table ineligible for SHRINK yet supports MOVE | **MOVE** per object type | Different preconditions than shrink |
| Only one partition holds old data | **Partition maintenance** | Targets the exact data subset |
| Index UNUSABLE after MOVE | **REBUILD or corresponding mechanism** | Restores usability |
| Valid B-tree index with lots of empty space | **COALESCE/SHRINK** when suitable | Reuses or reclaims space |
| LOB accounts for most space | **Maintain LOB segment separately** | Table segment does not reflect the whole footprint |
| Want to shrink datafile size | **Manage datafile separately** | Does not follow automatically from segment shrink |

These approaches must be verified against your Oracle version/edition and exact object type.

## 11. Controlled Maintenance Workflow

1. **Define the goal:** need tablespace free space, lower HWM for table scans, move tablespaces, or shrink datafiles?
2. **Capture baseline:** row count, per-segment allocation, indexes/LOBs, SQL plans, growth trends, and space reuse rate.
3. **Confirm eligibility:** ASSM, row movement, table/index type, partitions, LOBs, and SHRINK/MOVE ONLINE restrictions.
4. **Estimate resources:** MOVE may need space for a new segment; SHRINK incurs row movement, redo/undo, I/O, and locks; index maintenance also needs budget.
5. **Prepare operations:** privileges, low-load window, backups and recovery plan, impact on sessions, jobs, standby, or replication.
6. **Execute the chosen operation:** do not automatically run both SHRINK and MOVE if only one method is needed.
7. **Verify:** row counts and primary keys, index status, extent/byte counts, tablespace free space, application queries, and post-maintenance plans.
8. **Monitor trends:** if the segment quickly grows large again, review retention, batch purges, and partitioning instead of reorganizing repeatedly.

## 12. Common Misconceptions

**"Deleting 80% of rows makes Oracle return 80% of the space."** False. DELETE creates internal free space, without necessarily lowering HWM or returning extents.

**"SHRINK does not move rows."** False. Shrink can move rows and change ROWIDs.

**"SHRINK will shrink the datafile."** Not guaranteed. It can return extents to the tablespace; datafiles are a separate layer.

**"MOVE does not affect indexes."** False across variants. Standard offline MOVE can leave indexes UNUSABLE.

**"Index COALESCE always reclaims extents."** False. COALESCE mainly targets internal block reuse.

**"For a table with CLOB/BLOB, you only need to SHRINK the table."** Insufficient. LOBs can live in separate segments accounting for most of the space.

**"Every table can use SHRINK SPACE."** False. Requires ASSM and a supported object type.

**"ONLINE means no maintenance plan is needed."** False. Online variants still carry operational costs and specific limits.

**"Successful DDL proves optimization succeeded."** False. You must verify data, indexes, space, and query performance.

## 13. Self-Practice Exercises

1. A 40 GB table has only 5% of its rows left, yet tomorrow it is expected to re-insert a large data volume. Why might not shrinking immediately make sense?
2. After `DELETE`, `COUNT(*)` drops sharply while `USER_SEGMENTS.BYTES` barely changes. Explain using blocks, extents, and HWM.
3. A table does not reside in an ASSM tablespace. Why must you consider another option before `SHRINK`?
4. After `ALTER TABLE MOVE`, which columns and views help detect indexes needing rebuild?
5. A table has a 500 MB table segment and a 30 GB LOB segment. Why does `SHRINK` on the table segment barely impact total size?
6. After shrink, tablespace free space rises while the datafile stays the same size. What happened?
7. Why should a Java application use primary keys instead of ROWIDs to store row identifiers?
8. When is index `COALESCE` preferable to `REBUILD`?
9. Why can a `MOVE` command fail with out-of-space even when the goal is to reclaim space?
10. Compare `SHRINK` and `MOVE` across ASSM requirements, row movement mechanics, indexes, locking, changing tablespaces, and extra space required.

In Oracle Database, **free space inside a segment, tablespace free space, and datafile size are three distinct layers**. SHRINK compacts rows and lowers HWM for eligible objects; MOVE rebuilds or relocates segments; indexes, LOBs, and partitions have their own mechanisms. Choosing an approach based on before/after measurements alongside an operational plan lets you reclaim space while preserving data integrity and application availability.
