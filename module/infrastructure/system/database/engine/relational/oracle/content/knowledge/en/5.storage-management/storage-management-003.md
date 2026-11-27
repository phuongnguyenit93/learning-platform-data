# Locally Managed Tablespaces and Automatic Segment Space Management in Oracle

When an application writes additional data to an Oracle table, the database must decide **where to get space from** and **which block to write into**. Both questions sound similar, yet they belong to two different management layers:

1. **Locally managed tablespace (LMT)** manages the **allocation and deallocation of extents** between the tablespace and segments. Oracle uses **bitmaps** to track whether extents are allocated or free.
2. **Automatic Segment Space Management (ASSM)** manages **available free space inside a segment's data blocks**, allowing Oracle to find a suitable block when inserting rows. Oracle also uses bitmaps here, but these bitmaps serve the **segment/block** level rather than marking free extents in the tablespace.

These are foundational mechanisms of modern Oracle storage. Understanding the boundary between LMT and ASSM helps you read tablespace configurations, explain why tables keep their allocated size even after deleting data, identify concurrency issues during simultaneous inserts, and avoid confusing `AUTOALLOCATE`, `AUTOEXTEND`, and `SEGMENT SPACE MANAGEMENT AUTO`.

## 1. From Tablespace to Block: Knowing Exactly What Oracle Manages

Oracle organizes relational data storage across logical and physical layers:

```text
Oracle Database / PDB
  |
  +-- TABLESPACE app_data       [logical storage space]
        |
        +-- DATAFILE 01.dbf     [physical/storage-managed file]
        +-- DATAFILE 02.dbf
        |
        +-- SEGMENT of table ORDERS
        |     +-- EXTENT 1: multiple contiguous Oracle data blocks
        |     +-- EXTENT 2: multiple contiguous Oracle data blocks
        |     +-- ...
        |
        +-- SEGMENT of index IDX_ORDERS_CUSTOMER
              +-- EXTENT 1
              +-- EXTENT 2

        LMT tracks allocated / unallocated extents in the tablespace.
        ASSM tracks blocks with space to write in each segment.
```

| Component | Role | Common Question |
|---|---|---|
| **Tablespace** | Logical space collection containing segments; usually backed by one or more datafiles | Does the tablespace still have free extents to allocate? |
| **Datafile** | File holding Oracle blocks for a tablespace | Can the file grow in size or can a new file be added? |
| **Segment** | Storage unit for an object/data structure such as a table, index, or LOB | How many bytes/extents have been allocated to the segment? |
| **Extent** | Set of contiguous blocks in a datafile, allocated to a segment | When a segment grows, how does Oracle acquire additional extents? |
| **Data block** | Smaller logical storage and I/O unit inside an extent | Which block still has room to insert or update a row? |

A table can have its own data segment and multiple distinct index/LOB segments. A newly created object **might not have a segment yet** if configuration enables *deferred segment creation*: Oracle allocates the segment only when data needs to be written. Therefore, not seeing a new table's name in `USER_SEGMENTS` is not necessarily an error.

**Rule to remember:** *LMT determines which extent belongs to which segment; ASSM helps determine which block inside a segment has enough space to write.* Both mechanisms are typically used together, yet they solve two different problems.

## 2. What Is a Locally Managed Tablespace (LMT)?

A **locally managed tablespace** is a tablespace in which extent allocation state is managed by **bitmaps within the tablespace's own storage structures**, rather than relying on data dictionary tables to record every extent allocation as in the older **dictionary-managed tablespace (DMT)** model.

Each bitmap represents the state of a set of space units: which ones are available for allocation and which have been assigned to segments. When a segment needs to grow, Oracle consults the free-space info, finds a suitable extent, allocates it, and updates the corresponding metadata.

```text
TABLESPACE (LMT)
  Extent-management bitmap:
  [USED][USED][FREE][FREE][USED][FREE][...]
            |                   |
      extent already       extent available
      belongs to a         for future
      segment              allocation

  TABLE ORDERS       -> extent A + extent B
  INDEX ORDERS_IDX   -> extent E
```

This diagram only illustrates the concept; actual bitmap layout and management units may vary by extent policy and Oracle version.

### 2.1. What Problem Does LMT Solve Compared to DMT?

In the older dictionary-managed model, extent metadata was managed through dictionary structures; frequent allocations/deallocations increased update contention on shared dictionary metadata. LMT moves space metadata into the tablespace itself as bitmaps, enabling efficient extent management and reducing dictionary contention when multiple objects grow simultaneously.

Practical advantages of LMT:

- **Reduced reliance on dictionary updates** for frequent extent allocation operations.
- **Centralized space management per tablespace**, fitting the modern Oracle storage model.
- **Simplified extent administration**: you can let Oracle choose extent sizes via `AUTOALLOCATE` or enforce a fixed size via `UNIFORM`.
- **More convenient capacity tracking** through views reflecting datafiles, segments, extents, and free space.

Do not assume LMT means zero contention of any kind, never running out of space, or no need to monitor datafiles. LMT only changes **how Oracle manages extent allocation**.

### 2.2. `AUTOALLOCATE`: Oracle Chooses Extent Sizes

An LMT can use automatic extent allocation mode:

```sql
EXTENT MANAGEMENT LOCAL AUTOALLOCATE
```

In this mode, Oracle determines extent sizes as a segment grows based on internal policies and the segment's size/needs. Extents within the same segment **do not have to be the same size**. This mode is convenient when you have many tables/indexes growing at different rates.

Points to note:

- `AUTOALLOCATE` refers to **the size of extents allocated to segments**; it does not mean datafiles will auto-grow.
- The exact algorithm, size tiers, and transition points are implementation details; do not plan capacity assuming a table will always receive one fixed extent size.
- Even with automatic extent sizing, a segment still needs **eligible free extents** in the tablespace and sufficient underlying physical storage.

### 2.3. `UNIFORM SIZE`: Fixed-Size Extents

An LMT can also use:

```sql
EXTENT MANAGEMENT LOCAL UNIFORM SIZE 1M
```

Here, all extents allocated in the tablespace share the specified uniform size—`1M` in this example. This mode makes allocation more predictable, which can help specific workloads or administrative needs, but it can reserve significant space for small objects; for instance, a small segment allocated a 1 MB extent might still contain only a few blocks of actual data.

**There is no rule saying "UNIFORM is always faster than AUTOALLOCATE."** The choice should be based on object types, growth patterns, segment counts, capacity management, and measured results. For many standard applications, letting Oracle manage extents via `AUTOALLOCATE` is a reasonable starting point.

### 2.4. Comparing LMT Policies

| Attribute | `AUTOALLOCATE` | `UNIFORM SIZE` |
|---|---|---|
| Extent size | Oracle chooses automatically based on policy and segment growth | Fixed to the specified size |
| Flexibility | Well-suited when objects have varying sizes and growth rates | Well-suited when controlling the allocation unit is desired |
| Predictability | Extent size can vary over the segment's lifecycle | Every extent is the same size; easy to estimate incremental allocation |
| Risk to consider | Do not predict extent sizes solely from row counts | May over-allocate space for many small objects |
| Automatic datafile growth | **No**; that is a separate feature | **No**; that is a separate feature |

In modern Oracle systems, LMT is the standard mechanism; DMT is mainly encountered in historical documentation or when studying legacy systems. Do not design new tablespaces as DMT.

## 3. What Is Automatic Segment Space Management (ASSM)?

**Automatic Segment Space Management** automatically manages **blocks with suitable free space for write operations inside a segment**. When inserting a new row, Oracle must find a block with enough space, or format/use additional blocks from extents already belonging to the segment. ASSM maintains block fullness/free-space status via **bitmaps inside the segment**.

```text
SEGMENT of table ORDERS
  |
  +-- Bitmap indicating block free-space levels
  |       Block A: nearly full
  |       Block B: has room
  |       Block C: mostly free
  |
  +-- Extent 1
  |     [Block A][Block B][Block C][...]
  +-- Extent 2
        [Block D][Block E][Block F][...]

On INSERT -> Oracle checks free-space info -> selects a suitable block.
```

ASSM bitmaps are **not** LMT extent-management bitmaps: they operate at different levels and answer different questions.

### 3.1. Why Choose ASSM Over Manual Freelist Management?

Before ASSM, the **manual segment space management (MSSM)** model used *freelists* to track blocks capable of accepting more rows. DBAs often had to tune `FREELISTS`, `FREELIST GROUPS`, and related parameters to balance concurrent writes across sessions.

ASSM uses bitmaps so Oracle maintains free-block info automatically, reducing the need for manual freelist tuning and typically supporting workloads with many concurrent inserting sessions well. That **does not guarantee all applications are free of contention**: index hot blocks, transaction locks, ITLs, I/O, redo, sequences, and data design can still become bottlenecks.

| Criterion | MSSM (Manual) | ASSM (Automatic) |
|---|---|---|
| Tracking blocks with space | Freelists and manual management mechanisms | Segment bitmaps |
| Freelist parameters | Meaningful under manual management | Traditional freelist mechanism not used for ASSM segments |
| `PCTUSED` | Participates in deciding when a block returns to the insertable list | Does not control block selection the way MSSM does |
| `PCTFREE` | Meaningful | **Still meaningful**, especially to reserve space for row-enlarging updates |
| Extent allocation | Handled by tablespace mechanism, e.g., LMT | **Does not replace LMT**; ASSM manages blocks inside segments |
| Operations | Requires understanding and sometimes tuning freelists | Oracle automatically manages block free-space levels |

### 3.2. ASSM Categorizes Blocks by Free-Space Level

Bitmaps help Oracle identify groups of blocks with different amounts of free space without maintaining manual free-block lists like MSSM. When deeper inspection is needed, the `DBMS_SPACE.SPACE_USAGE` package can report block counts across free-space bands, typically represented as `FS1` through `FS4` and `FULL`:

| Category | Approximate Free-Space Level |
|---|---|
| `FS1` | 0–25% free space |
| `FS2` | 25–50% free space |
| `FS3` | 50–75% free space |
| `FS4` | 75–100% free space |
| `FULL` | Block considered full per management criteria |

These categories are a **way to observe status**, not a substitute for measuring the exact usable bytes for every row type. Block metadata and overhead also consume space. `DBMS_SPACE.SPACE_USAGE` requires appropriate privileges and invocation matching the segment type; never assume an application account can query every segment in the database.

### 3.3. `PCTFREE` Still Matters in ASSM

`PCTFREE` specifies the proportion of space on a data block reserved to support **updates to existing rows** (especially when row data grows in length). For example:

```sql
CREATE TABLE lab_customer (
    customer_id NUMBER PRIMARY KEY,
    full_name   VARCHAR2(200 CHAR),
    address     VARCHAR2(500 CHAR)
)
PCTFREE 20;
```

With `PCTFREE 20`, Oracle aims to leave part of the block's capacity for updates, though the value should not be interpreted as a guarantee that 20% of bytes always remain unused at all times. If `address` frequently changes from `NULL` to a long string, extra space may be needed to limit row migration; conversely, setting it too high can increase the number of blocks that must be read.

**`PCTUSED` differs from `PCTFREE`.** In MSSM, `PCTUSED` determines when a block becomes eligible for inserts again via the freelist after deletes/updates. In ASSM, Oracle uses bitmaps to track free space, so `PCTUSED` is no longer the corresponding tuning knob. When tuning, observe actual data and workload rather than copying freelist settings from legacy Oracle guides.

## 4. How Do LMT and ASSM Work Together During Data Inserts?

Suppose an application executes an `INSERT` into table `ORDERS` in a tablespace configured with `EXTENT MANAGEMENT LOCAL AUTOALLOCATE` and `SEGMENT SPACE MANAGEMENT AUTO`.

1. Oracle needs to find a block in the table segment with enough room to write the row; **ASSM** assists by checking fullness/free-space bitmaps.
2. If additional blocks are needed and the segment still has usable space in already-allocated extents, Oracle uses that space and updates corresponding metadata.
3. If the segment must expand with a new extent, **LMT** locates and allocates a free extent in the tablespace; under `AUTOALLOCATE`, Oracle selects the extent size per its policy.
4. ASSM continues managing the blocks brought into use within the segment for subsequent inserts.
5. If the tablespace lacks eligible extents, the datafile cannot extend, or another limit/quota applies, the operation can fail even though ASSM itself is working normally.

```text
INSERT data
      |
      v
ASSM: does segment have a suitable block? -- Yes --> write to block, update bitmap
      |
     No
      v
Does segment have unused blocks in extents? -- Yes --> bring block into use
      |
     No
      v
LMT: allocate new extent from tablespace -- Success --> ASSM manages new blocks
      |
     No
      v
Check tablespace/datafile/quota/limits -> out-of-space ORA error may occur
```

This diagram explains responsibility layers, not every internal step of the optimizer or buffer manager. Besides data segments, Oracle also has index/LOB/undo/temporary segments with their own characteristics and policies.

## 5. Do Not Confuse `AUTOALLOCATE`, `AUTOEXTEND`, ASSM, and Oracle ASM

The names sound alike, yet their jobs are completely different:

| Mechanism | Management Layer | Meaning |
|---|---|---|
| `EXTENT MANAGEMENT LOCAL` | Tablespace | Tracks extent state using local tablespace bitmaps |
| `AUTOALLOCATE` | Extent | Oracle chooses extent sizes when a segment needs more space |
| `UNIFORM SIZE` | Extent | Uses a fixed extent size throughout the tablespace |
| `SEGMENT SPACE MANAGEMENT AUTO` (ASSM) | Segment/block | Oracle uses bitmaps to manage blocks with room for writes |
| `AUTOEXTEND ON` | Datafile | Allows the file to grow incrementally, within configured limits and actual capacity |
| **ASM – Automatic Storage Management** | Physical storage | Oracle manages disk groups and distributes database files across storage infrastructure; **not ASSM** |
| Automatic Undo Management | Undo | Manages undo automatically; not the mechanism for locating user table blocks |

For example, a datafile with `AUTOEXTEND OFF` can still serve many inserts as long as free extents remain. Conversely, a file with `AUTOEXTEND ON` does not guarantee unlimited growth: `MAXSIZE`, actual storage capacity, user quotas, or other limits can still block allocation.

LMT is called "locally managed" because **extent metadata lives inside the tablespace**; the word "local" does not mean the database must run on directly attached disks or cannot use SAN, NFS, or Oracle ASM.

## 6. Creating an LMT Tablespace Combined with ASSM

The examples below are intended for **DEV/TEST lab environments** and users granted appropriate DBA privileges. Creating tablespaces may require the `CREATE TABLESPACE` privilege, underlying disk space, directory access, or Oracle Managed Files (OMF) configuration. Do not execute these on production just to run a practice exercise.

### 6.1. Example: `AUTOALLOCATE` + ASSM

```sql
-- Example for a lab Oracle database/PDB with a valid datafile path.
CREATE TABLESPACE lmt_assm_lab
DATAFILE '/u02/oradata/DEV_PDB/lmt_assm_lab01.dbf' SIZE 256M
    AUTOEXTEND ON NEXT 64M MAXSIZE 2G
EXTENT MANAGEMENT LOCAL AUTOALLOCATE
SEGMENT SPACE MANAGEMENT AUTO;
```

Reading each clause:

- `CREATE TABLESPACE lmt_assm_lab`: creates a tablespace to store application data.
- `DATAFILE ... SIZE 256M`: provisions an initial 256 MB datafile. The path above is a **placeholder path** and must be replaced with a real DBA-managed path.
- `AUTOEXTEND ON NEXT 64M MAXSIZE 2G`: allows the datafile to grow in 64 MB increments when needed up to the configured limit; still depends on underlying infrastructure.
- `EXTENT MANAGEMENT LOCAL AUTOALLOCATE`: LMT manages extents with bitmaps, and Oracle chooses extent sizes.
- `SEGMENT SPACE MANAGEMENT AUTO`: ASSM manages block space inside segments.

If the database uses **Oracle Managed Files**, a DBA can omit explicit paths when target file-creation parameters are configured; if using **Oracle ASM**, the file path may point to a disk group. Choose the file-creation syntax matching the running Oracle configuration rather than copying example paths verbatim.

### 6.2. Example: `UNIFORM` + ASSM

```sql
CREATE TABLESPACE lmt_uniform_lab
DATAFILE '/u02/oradata/DEV_PDB/lmt_uniform_lab01.dbf' SIZE 256M
    AUTOEXTEND OFF
EXTENT MANAGEMENT LOCAL UNIFORM SIZE 1M
SEGMENT SPACE MANAGEMENT AUTO;
```

Here, every extent allocated in the tablespace uses a 1 MB size, while ASSM still automatically locates blocks with room for writes. `AUTOEXTEND OFF` means the datafile does not grow automatically; it **does not disable ASSM**, nor does it stop Oracle from allocating additional extents from remaining free space inside the file.

### 6.3. Granting Quota to an Authorized Practice Schema

A user needs object creation privileges and a tablespace quota to store segments. Example for a DBA or authorized administrator:

```sql
ALTER USER lab_app QUOTA 128M ON lmt_assm_lab;
```

`CREATE TABLE` or other object-creation privileges should be granted according to purpose. Quota is separate from tablespace free space: a tablespace may still have free capacity while a user hits their quota. Never grant `UNLIMITED TABLESPACE` or high administrative privileges to an application account merely to make a lab exercise run.

**Multitenant context:** in a CDB/PDB architecture, create and inspect tablespaces in the **right PDB**. Verify `CON_NAME`/service of your session before running DDL; logging into the CDB root or the wrong PDB puts operations out of scope.

## 7. Checking Whether a Tablespace Uses LMT and ASSM

A DBA or user with appropriate dictionary query privileges can inspect `DBA_TABLESPACES`:

```sql
SELECT
    tablespace_name,
    contents,
    extent_management,
    allocation_type,
    segment_space_management
FROM dba_tablespaces
WHERE tablespace_name IN ('LMT_ASSM_LAB', 'LMT_UNIFORM_LAB');
```

Columns to understand:

| Column | Meaning When Reading |
|---|---|
| `EXTENT_MANAGEMENT` | Value `LOCAL` indicates the tablespace uses LMT extent management |
| `ALLOCATION_TYPE` | Shows the extent allocation strategy, e.g., `SYSTEM` for autoallocate or `UNIFORM` for fixed size |
| `SEGMENT_SPACE_MANAGEMENT` | Value `AUTO` indicates ASSM; for certain tablespace types this mechanism does not carry the same meaning as for regular permanent tablespaces |
| `CONTENTS` | Identifies `PERMANENT`, `TEMPORARY`, or other tablespace types before interpreting parameters |

Do not infer settings from the name `LMT_ASSM_LAB` alone: names are human-chosen, whereas **dictionary values reflect actual configuration**. `DBA_*` views are not exposed to application users by default. If your account lacks privileges, ask a DBA for the output; never grant the `DBA` role just to run a check query.

### 7.1. Inspecting Datafiles and Expansion Capability

```sql
SELECT
    tablespace_name,
    file_name,
    bytes / 1024 / 1024 AS allocated_mb,
    autoextensible,
    maxbytes / 1024 / 1024 AS max_mb
FROM dba_data_files
WHERE tablespace_name = 'LMT_ASSM_LAB';
```

`BYTES` is the current datafile size; `MAXBYTES` relates to the configured growth ceiling, not a guarantee that storage actually has that much space available. Capacity monitoring must cross-check multiple sources: free space inside the tablespace, segment growth, datafile configuration, and OS/ASM storage capacity.

### 7.2. Distinguishing Segment Allocated Space from Free Extents

```sql
-- Free extents in the tablespace (tablespace level).
SELECT tablespace_name,
       SUM(bytes) / 1024 / 1024 AS free_extent_mb
FROM dba_free_space
WHERE tablespace_name = 'LMT_ASSM_LAB'
GROUP BY tablespace_name;

-- Space and extent count allocated per segment (segment level).
SELECT owner, segment_name, segment_type,
       extents, bytes / 1024 / 1024 AS allocated_mb
FROM dba_segments
WHERE tablespace_name = 'LMT_ASSM_LAB'
ORDER BY bytes DESC;
```

**`DBA_FREE_SPACE` reflects unallocated extents in the tablespace**, not the sum of unused bytes inside blocks belonging to all tables. Conversely, `DBA_SEGMENTS.BYTES` is the space allocated to the segment, **not equal to the useful data size of all rows**. A table with many deleted rows can still hold onto its allocated extents.

For regular schema users, `USER_SEGMENTS` and `USER_EXTENTS` let you inspect segments/extents you own when you have appropriate object access; for example:

```sql
SELECT segment_name, segment_type, tablespace_name,
       extents, bytes / 1024 / 1024 AS allocated_mb
FROM user_segments
WHERE tablespace_name = 'LMT_ASSM_LAB';
```

Seeing no rows in `DBA_FREE_SPACE` for a tablespace does not automatically mean the query failed; check the overall context, including whether there are no free extents left to list, view privileges, or related file states.

## 8. Hands-On Lab: Observing Extent Allocation as a Table Grows

The following lab demonstrates how **LMT and ASSM operate together**. It assumes account `LAB_APP` has been granted table creation privileges and quota on `LMT_ASSM_LAB`, and you are connected to the right DEV/TEST PDB.

### Step 1 – Verify the Environment Before Writing Data

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME') AS pdb_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER') AS login_user
FROM dual;
```

Confirm the values match your assigned lab environment. All data in the following steps is synthetic.

### Step 2 – Create a Table in an ASSM Tablespace

```sql
CREATE TABLE lab_orders_space (
    order_id NUMBER PRIMARY KEY,
    status   VARCHAR2(20 CHAR) NOT NULL,
    payload  VARCHAR2(400 CHAR)
)
TABLESPACE lmt_assm_lab
PCTFREE 15;
```

The primary key can create a separate index segment; to avoid confusion when measuring size, inspect `SEGMENT_TYPE` clearly for each object. In configurations allowing *deferred segment creation*, the newly created table might not appear in `USER_SEGMENTS` until data is inserted.

### Step 3 – Insert Controlled Synthetic Data

```sql
INSERT INTO lab_orders_space (order_id, status, payload)
SELECT LEVEL,
       'NEW',
       RPAD('LAB', 300, 'x')
FROM dual
CONNECT BY LEVEL <= 5000;

COMMIT;

SELECT COUNT(*) AS total_rows
FROM lab_orders_space;
```

This uses Oracle's `CONNECT BY LEVEL` syntax to generate 5,000 synthetic rows. Actual space and extent counts vary by block size, metadata, edition/version, allocation policy, and tablespace state. Do not expect a fixed extent count as an invariant answer.

### Step 4 – Inspect Segments and Extents After Insert

```sql
SELECT segment_name, segment_type, extents,
       bytes / 1024 AS allocated_kb
FROM user_segments
WHERE segment_name = 'LAB_ORDERS_SPACE';

SELECT extent_id, file_id, block_id,
       blocks, bytes / 1024 AS extent_kb
FROM user_extents
WHERE segment_name = 'LAB_ORDERS_SPACE'
ORDER BY extent_id;
```

`USER_SEGMENTS` shows how many extents/bytes have been allocated to the segment; `USER_EXTENTS` lists each extent. With `AUTOALLOCATE`, the number of blocks per extent **can differ**. If you test a similar table in a `UNIFORM SIZE 1M` tablespace, its extents will have a fixed size per the tablespace policy.

### Step 5 – Delete Data and Observe Again

```sql
DELETE FROM lab_orders_space
WHERE MOD(order_id, 2) = 0;

COMMIT;

SELECT COUNT(*) AS remaining_rows
FROM lab_orders_space;

SELECT segment_name, extents, bytes / 1024 AS allocated_kb
FROM user_segments
WHERE segment_name = 'LAB_ORDERS_SPACE';
```

The row count decreases, yet **`USER_SEGMENTS.BYTES` usually does not drop proportionally**. `DELETE` frees space for reuse **inside the segment** per block management rules, rather than automatically returning extents to the tablespace or shrinking the datafile. ASSM updates its info on blocks available for new data; LMT still views those extents as belonging to that segment.

### Step 6 – Discuss and Clean Up in the Lab

Try inserting additional rows with new keys and watch `USER_SEGMENTS`: Oracle may reuse space in existing blocks before needing another extent, depending on row size and block state.

Only after confirming this is the table you created in **DEV/TEST**, clean up if permitted:

```sql
DROP TABLE lab_orders_space PURGE;
```

`DROP TABLE ... PURGE` removes the object without placing it in the recycle bin; this is a destructive operation on lab data and DDL with an implicit commit. Never run it against real data or similarly named production tables. If your organization requires retaining practice data, skip cleanup.

## 9. Why Does a Tablespace Stay "Full" Even After Deleting Many Rows?

A common misconception is: "I `DELETE`d 80% of the rows, so 80% of the space must be returned to the tablespace." In reality, there are **at least three capacity levels**:

1. **Used datafile space on storage:** a file that has grown will not shrink on its own simply because many rows were deleted.
2. **Extents allocated to the segment:** Oracle keeps extents in the segment until an eligible release operation/condition occurs; `DBA_SEGMENTS.BYTES` reflects this allocated space.
3. **Space inside allocated blocks:** ASSM manages free space inside blocks so subsequent inserts/updates can reuse it.

```text
DATAFILE allocated 1024 MB
  |
  +-- 800 MB extents already belonging to segments
  |      |
  |      +-- Current data rows and block metadata
  |      +-- Free space inside blocks from DELETE/UPDATE
  |          (managed by ASSM, not yet FREE tablespace extents)
  |
  +-- 224 MB extents not yet allocated to any segment
         (LMT can allocate these when needed)
```

These numbers are illustrative only and omit overhead. LMT and ASSM **are not tools that automatically compact data, purge old records, return every extent to the tablespace, or shrink physical files**.

### 9.1. High Water Mark and Full Table Scans

The **High Water Mark (HWM)** is the boundary associated with used blocks in a segment. When many rows are deleted, the HWM might not move down, so some table scan operations still have to examine blocks below the HWM even with fewer rows remaining. ASSM knows which blocks have room for inserts, yet that does not mean the HWM automatically lowers or full scans always read less.

If space needs to be reclaimed or reorganized, DBAs/developers can evaluate techniques such as **segment shrink**, `MOVE`, object rebuilds, or partitioning/data retention policies. For example, on a supported heap table in ASSM when preconditions are met:

```sql
-- Example maintenance operation only, for an authorized table.
ALTER TABLE lab_orders_space ENABLE ROW MOVEMENT;
ALTER TABLE lab_orders_space SHRINK SPACE;
```

Not every table/LOB/index can be shrunk the same way; the operation has limitations and impacts on rowids, indexes, locks, rowid-dependent applications, load, and online availability. Before applying to production, consult documentation for your Oracle release, test, plan, and monitor afterward. **Never assume shrink will reduce the datafile size on the operating system.**

### 9.2. What Determines Whether a Row Fits in a Current Block?

Beyond the ASSM bitmap, Oracle also considers row size, block metadata/transaction entries, `PCTFREE`, data types, length-increasing updates, block size, and other conditions. An update that enlarges a row can cause **row migration** if the current block lacks space; this can increase I/O on queries accessing via ROWID/index. ASSM helps select blocks, but does not completely eliminate row migration or all forms of data fragmentation.

## 10. Oracle Space Errors and How to Classify Them

Tablespace/segment errors typically appear when applications write data or run DDL. Read both the error code and the segment/tablespace name in the message to assign troubleshooting:

| Example Error Code | Indicative Meaning | What to Check |
|---|---|---|
| `ORA-01653` | Unable to extend table segment with required extent | Free extents, datafile/maxsize, quota, table growth |
| `ORA-01654` | Unable to extend index segment | Tablespace holding the index, capacity, and index workload |
| `ORA-01652` | Unable to extend temporary segment | Temporary tablespace, temp usage, SQL/sort/hash workload |
| `ORA-01536` | Exceeded tablespace quota granted to user | Schema quota, object allocation, and privilege policy |
| `ORA-01658` | Unable to create initial extent for segment in tablespace | Eligible free extents and extent size/file limits |

`ORA-01653` **does not automatically mean the disk is full**. The tablespace may lack space to allocate an extent, the datafile may have hit `MAXSIZE`, autoextend may be off, underlying storage may be out of capacity, or the user may be restricted by quota. With `UNIFORM SIZE`, enough space for the chosen extent unit is needed; with `AUTOALLOCATE`, the next extent size depends on Oracle's policy.

### Scenario A – LMT + ASSM Tablespace Yet Insert Raises `ORA-01653`

1. **Developer** identifies which table/index is growing rapidly, which SQL generates load, what migration or batch job just ran, row counts, and projected capacity needs.
2. **DBA** checks `DBA_SEGMENTS`, `DBA_FREE_SPACE`, datafile/autoextend, quotas, PDB status, and ability to allocate new extents.
3. **Operations** checks storage/disk groups, alerts, growth, and capacity to add infrastructure resources per procedure.
4. The team picks an evidence-based resolution: adding files/raising approved limits, adjusting quotas appropriately, handling data per retention policy, or fixing application bugs generating abnormal data.

Enabling ASSM does not add extra disk capacity. `AUTOEXTEND ON` also does not guarantee the disk always has free space.

### Scenario B – Concurrent Inserts from Multiple Sessions Remain Slow

A system moves to LMT + ASSM yet inserts still suffer rising latency. Check wait events, contention on monotonically increasing indexes/hot blocks, transaction locks, redo logs, CPU, I/O, connection count, batch size, and commit behavior. ASSM reduces manual freelist tuning in some workloads, but **does not single-handedly solve bottlenecks across the entire transaction pipeline**.

### Scenario C – Data Deleted Yet Table Size Does Not Shrink

A developer deletes test data; `COUNT(*)` drops, while `DBA_SEGMENTS.BYTES` barely changes. This may be expected behavior: the segment retains extents for reuse. If reducing footprint is required, evaluate HWM, shrink eligibility, indexes/LOBs/partitions, and reclamation policies; never issue `DROP`, `TRUNCATE`, or `SHRINK` in production without assessing impact.

## 11. Operating LMT and ASSM: Which Metrics Are Truly Useful?

### 11.1. Tracking Space at Each Layer

| What You Want to Know | Common Observation Source | Caution When Interpreting |
|---|---|---|
| How many free extents does the tablespace have? | `DBA_FREE_SPACE` | Does not count free space inside blocks already assigned to segments |
| How big is the datafile, and is autoextend enabled? | `DBA_DATA_FILES` | `MAXBYTES` is a configured cap, not a guarantee of available storage |
| How many bytes and extents are allocated to a segment? | `DBA_SEGMENTS`, `USER_SEGMENTS` | Allocated size does not equal useful data bytes |
| How big are a segment's extents? | `DBA_EXTENTS`, `USER_EXTENTS` | Extent size depends on allocation strategy, not ASSM |
| How full/free are blocks in an ASSM segment? | `DBMS_SPACE.SPACE_USAGE` with right privileges and segment type | Must understand fullness bands and API limitations |
| Overall capacity and usage trends? | Tablespace/storage metrics, `DBA_TABLESPACE_USAGE_METRICS`, and deployed monitoring | Must cross-check autoextend, quotas, reserved space, tablespace type, and infrastructure reality |

Setting alerts based on growth trends and time remaining before reaching limits is usually more helpful than watching a point-in-time free-MB number. For critical application tablespaces, also factor in backups, recovery capacity, batch spikes, and major-release growth.

### 11.2. Do Not Ignore Account Limits and Tablespace Types

- **Quotas:** a schema can exhaust its quota even when the tablespace still has room; review quota policies before raising limits.
- **Indexes and LOBs:** a table may reside in one tablespace while its indexes/LOBs reside in others; errors can originate from auxiliary segments.
- **Temporary tablespaces:** sorts/hashes and temporary operations use separate temp management; do not apply permanent table block ASSM semantics verbatim to temp.
- **Undo tablespaces:** serve MVCC/transaction recovery with separate undo policies; do not confuse with business-table ASSM.
- **CDB/PDB:** query the right container when inspecting the catalog; identically named tablespaces in different PDBs are independent objects.
- **Access privileges:** querying dictionary views or running `ALTER TABLESPACE` requires appropriate privileges; developers provide business metrics while DBAs execute storage changes per process.

## 12. Choosing `AUTOALLOCATE` vs. `UNIFORM`, and When to Think About ASSM

A sound decision starts from the workload, not a parameter name:

**Case 1 – Many tables and indexes of varying sizes.** LMT `AUTOALLOCATE` is typically a straightforward choice because Oracle chooses extent sizes automatically; ASSM handles block management for common write workloads. Monitor actual extent counts and space usage instead of over-tuning every parameter upfront.

**Case 2 – Workload requiring a fixed extent unit.** Consider `UNIFORM SIZE` when predictable allocation behavior is needed and you understand the reserved-space overhead for small segments. ASSM still works normally for block management; the two options are not mutually exclusive.

**Case 3 – Concurrent writes across many sessions.** ASSM is suitable in many systems because it manages free blocks automatically; however, performance also depends on indexes, SQL statements, commits, latches/waits, and infrastructure setup. Validate with representative benchmarks and AWR/ASH or licensed diagnostic tools if available in your environment.

**Case 4 – Fast-growing tables or frequent deletions.** Evaluate retention/partitioning management, HWM, free extents, growth, and maintenance costs. ASSM does not replace a data lifecycle strategy, and LMT does not automatically shrink OS files.

For modern Oracle environments, **LMT + ASSM** is the standard combination for permanent application tablespaces. Choose another mechanism only when documented technical requirements and testing on your target Oracle version and segment types justify it.

## 13. Common Misconceptions

| Incorrect or Incomplete Statement | Accurate Understanding |
|---|---|
| "LMT and ASSM both use bitmaps, so they are the same feature." | LMT manages **tablespace extents**; ASSM manages **blocks with free space inside a segment**. |
| "Locally managed means using local disks only." | "Local" means extent metadata is stored/managed inside the tablespace; storage can still be ASM or other platforms. |
| "AUTOALLOCATE automatically grows datafiles." | AUTOALLOCATE selects extent sizes; AUTOEXTEND controls whether datafiles are permitted to grow. |
| "ASSM means every INSERT is fast and contention-free." | ASSM removes manual freelist tuning; hot indexes, transactions, I/O, redo, and resource limits still apply. |
| "With ASSM enabled, you don't need to care about PCTFREE." | `PCTFREE` still controls space reserved for updates and row density per block. |
| "PCTUSED must be tuned so ASSM finds free blocks." | ASSM uses bitmaps; traditional `PCTUSED`/freelist mechanics belong to MSSM. |
| "Deleting 90% of rows returns 90% of space to the tablespace." | Space is typically reused inside the segment; extent counts and datafile sizes do not necessarily drop. |
| "DBA_FREE_SPACE is the total free space across all tables." | That view reflects unallocated extents at the tablespace level, not unused bytes inside blocks already allocated to segments. |
| "ORA-01653 means ASSM is broken." | Check extent allocation capacity, datafiles, quotas, infrastructure, and which segment is growing. |
| "ASM and ASSM are two spellings of the same feature." | ASM manages storage/disk groups; ASSM manages blocks inside segments. |

## 14. Self-Check Knowledge Exercises

### Question 1 – Two Tables Sharing a Tablespace

In `APP_DATA`, table A uses 20 extents and table B uses 3 extents. Which mechanism records which extents are allocated to segments? If B needs one more extent, which mechanism plays a role in allocating it? **Answer:** LMT and the tablespace extent-management bitmap.

### Question 2 – Table Already Has Extents; Insert Needs a Block with Room

An application inserts a new row while the segment still has blocks with available space. Which mechanism helps Oracle locate a suitable block? **Answer:** ASSM; it tracks block free-space info using the segment's bitmap.

### Question 3 – `AUTOEXTEND OFF` Yet INSERT Still Succeeds

Why can the table still accept writes even though the datafile is not allowed to extend? **Answer:** The tablespace may still have free extents inside the datafile, or the segment may have usable blocks within already-allocated extents. `AUTOEXTEND` only governs **physical file** growth, not every individual insert.

### Question 4 – `DELETE` One Million Rows Yet `DBA_SEGMENTS.BYTES` Does Not Drop

Does that necessarily mean `DELETE` failed? **Answer:** No. Check remaining row counts, committed transactions, and delete scope. Extents can stay with the segment; ASSM can reuse free blocks without returning extents to the tablespace.

### Question 5 – Choosing Settings for an Application Tablespace

Suppose you have many small and large tables, moderate concurrent writes, and no fixed-extent requirement. A reasonable starting point is `EXTENT MANAGEMENT LOCAL AUTOALLOCATE` and `SEGMENT SPACE MANAGEMENT AUTO`. Decisions around `AUTOEXTEND`, `MAXSIZE`, quotas, backups, and capacity alerts must be designed **separately** based on storage budget and operational requirements.

## Conclusion

**LMT manages extents at the tablespace level; ASSM manages free space inside blocks at the segment level.** `AUTOALLOCATE` or `UNIFORM` determines extent sizing within LMT; `PCTFREE` still shapes block organization under ASSM; `AUTOEXTEND` and Oracle ASM are distinct functional layers. Observing the right layer through `DBA_TABLESPACES`, `DBA_SEGMENTS`, `DBA_EXTENTS`, `DBA_FREE_SPACE`, and datafile metrics explains storage growth, `ORA-01653` errors, post-`DELETE` space reuse, and the impact of storage changes. In real Oracle operations, combine automated mechanisms with capacity monitoring, least-privilege access, and controlled maintenance plans.
