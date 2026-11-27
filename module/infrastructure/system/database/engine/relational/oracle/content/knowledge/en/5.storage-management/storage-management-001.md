# Relationship Between Tablespace, Datafile, Segment, Extent, and Data Block

## 1. Why Must We Distinguish Oracle's Storage Units?

When creating a table in Oracle Database, you usually just write `CREATE TABLE`, followed by `INSERT` and `SELECT`. However, the table's data must be placed into an organized storage structure: the table belongs to a **tablespace**, space is allocated to a **segment** via **extents**, each extent consists of multiple **Oracle data blocks**, and the blocks reside inside the **datafiles** of that tablespace.

If you do not understand this relationship, it is easy to confuse:

- The size of **the data currently stored in the table** with the size of **the space allocated to the segment**.
- The **current datafile size** with the **remaining space that a tablespace can expand into**.
- A **tablespace** (a logical unit) with an **operating system directory** (a physical location).
- **One table** with **a single segment**; indexes, LOBs, and partitions can have their own separate segments.
- A **block** with an **extent**; they differ in both level and purpose.

In the Oracle relational storage model, these concepts help you answer practical questions such as: "Which tablespace does this table reside in?", "How many MB have been allocated to it?", "Which datafile holds its extents?", "Why is there still free disk space yet an error occurs saying a segment cannot be extended?", and "Does deleting rows immediately shrink the datafile?".

The goal of this lesson is to understand the **logical and physical hierarchy**, read information directly through data dictionary views, and visualize what happens when Oracle allocates additional space for a table or index.

## 2. The Big Picture: Logical and Physical

Oracle organizes data from two closely related perspectives:

1. **Logical**: tablespace → segment → extent → data block.
2. **Physical**: a tablespace has one or more datafiles; the blocks allocated to extents reside **inside each datafile**.

A simple diagram:

```text
                              ORACLE DATABASE
                                     |
                           TABLESPACE APP_DATA
                                     |
               +---------------------+-------------------+
               |                                         |
          DATAFILE 01                                DATAFILE 02
          (file_id=5)                                (file_id=6)
               |                                         |
        +------+------+                           +------+------+
        |             |                           |             |
    Extent A      Extent B                    Extent C      Extent D
    TABLE_ORDERS  IDX_ORDERS                  TABLE_ORDERS  IDX_ORDERS
        |             |                           |             |
     [block]       [block]                     [block]       [block]
     [block]       [block]                     [block]       [block]
     [block]       [block]                     [block]       [block]

  Segment TABLE_ORDERS = Extent A + Extent C + ...
  Segment IDX_ORDERS   = Extent B + Extent D + ...
```

The diagram does not show all headers, free space, or the many segments that can coexist in one file. It illustrates one key point: **a segment can consist of extents located across multiple different datafiles**, as long as those datafiles belong to the same tablespace; **each individual extent resides entirely within a single datafile**.

### Core Relationships

| Component | Nature | Direct Relationship | What Not to Confuse |
|---|---|---|---|
| **Tablespace** | High-level logical storage unit of the database | Consists of one or more datafiles, or tempfiles for temporary tablespaces; contains segments | Not a Linux/Windows directory |
| **Datafile** | Physical storage file or ASM-managed file | Belongs to one tablespace; contains blocks and extents of multiple segments | Not necessarily one file per table |
| **Segment** | Space allocated for a storage object/structure | Belongs to one tablespace; consists of extents | Not synonymous with one logical table always having only one segment |
| **Extent** | Group of contiguous Oracle blocks allocated to a segment | Belongs to one segment; resides entirely within one datafile | An extent cannot span across two datafiles |
| **Data block** | Smallest logical storage unit managed by Oracle in this structure | Resides inside a datafile; multiple blocks form an extent | Not equal by default to a sector or OS block |

You can remember this with two statements:

> A **tablespace** organizes logical space; a **datafile** provides physical storage. A **segment** receives space from the tablespace in the form of **extents**, and an extent consists of **data blocks**.

> Oracle identifies where data is stored using **file + block**, whereas SQL applications typically work with **tables, rows, and columns** without needing to know those physical coordinates.

## 3. Tablespace: The Logical Storage Management Boundary

### 3.1. What Is a Tablespace?

A **tablespace** is the logical unit Oracle uses to group storage structures. When creating a table or index, you can specify the tablespace for its segment. Oracle uses the files associated with the tablespace to provide the blocks that store the data.

Example of organization:

```text
DATABASE
  |
  +-- SYSTEM         : core system objects
  +-- SYSAUX         : auxiliary objects for Oracle components
  +-- UNDOTBS1       : stores undo data according to configuration
  +-- TEMP           : temporary space for operations needing work areas
  +-- APP_DATA       : application tables (custom-designed example)
  +-- APP_INDEX      : application indexes (custom-designed example)
```

`APP_DATA` and `APP_INDEX` are just illustrative names. An application can place tables and indexes in the same tablespace or separate them to simplify administration, capacity monitoring, and storage policies.

Some types and roles:

| Tablespace | Characteristics | Usage Examples |
|---|---|---|
| **Permanent** | Stores persistent data segments; uses datafiles | Application tables, indexes, LOBs |
| **Undo** | Contains undo segments for rollback, read consistency, and other tasks | Undo managed by Oracle according to the configured mechanism |
| **Temporary** | Serves temporary data for operations requiring extra space; uses tempfiles | Sorts, hashes, and other temporary operations when needed |
| **SYSTEM/SYSAUX** | Tablespaces with special roles for database operation | System metadata, internal components |

**Key distinction:** a regular temporary tablespace uses **tempfiles** instead of datafiles; it still has temporary space/temporary segments, but its management and monitoring views are not identical to those of a permanent tablespace. Do not assume every file inside a tablespace appears in `DBA_DATA_FILES` just because you see the word "tablespace".

### 3.2. Smallfile and Bigfile Tablespaces

Oracle supports different tablespace organization types:

- **Smallfile tablespace**: can contain multiple datafiles; this is the common layout in many systems.
- **Bigfile tablespace**: designed with **a single very large datafile** (or a single large tempfile for a temporary tablespace), accompanied by corresponding limits and administration tools.

Thus, the statement "a tablespace has multiple datafiles" is a **capability**, not a mandatory requirement. A tablespace may have only one datafile. For a bigfile tablespace, growth capacity relies heavily on resizing that single large file.

### 3.3. Tablespace, Schema, and User Are Not the Same

A schema can own tables across multiple tablespaces; conversely, a tablespace can contain segments belonging to multiple schemas:

```text
SCHEMA SALES:
  SALES.ORDERS        -> segment in APP_DATA
  SALES.IDX_ORDERS    -> segment in APP_INDEX

SCHEMA SUPPORT:
  SUPPORT.TICKETS     -> segment in APP_DATA
```

A user's `DEFAULT TABLESPACE` is typically used when creating objects without specifying a tablespace, though a DBA can grant quotas, revoke tablespace privileges, or specify a different tablespace for individual objects. **The user name, schema name, and tablespace name do not have to match.**

## 4. Datafile: The Physical File Providing Blocks for a Tablespace

### 4.1. What Does a Datafile Contain?

A datafile is managed by Oracle. It has an internal structure containing file-administration metadata and blocks that can be allocated to different segments. Oracle reads and writes these blocks through the storage layer.

Examples of paths you might see in a filesystem-based environment:

```text
/u02/oradata/LABDB/app_data01.dbf
/u02/oradata/LABDB/app_data02.dbf
```

In a system using **Oracle Automatic Storage Management (ASM)**, paths may look like:

```text
+DATA/LABDB/DATAFILE/app_data.123.987654321
```

This is a logical filename managed by ASM, not an OS directory path for running `cp`, `mv`, or `rm` like a regular file. With **Oracle Managed Files (OMF)**, Oracle can also automatically generate and manage filenames based on the configured storage location.

For normal datafiles, the relationships are:

- **Each datafile belongs to one tablespace** at a time.
- **One tablespace can have multiple datafiles** (except under specific models/limits like bigfile).
- **One datafile can contain extents of multiple segments**.
- **One segment can receive extents from multiple datafiles within the same tablespace**.
- **A specific extent never crosses datafile boundaries**.

A datafile is not synonymous with a segment, and Oracle does not require creating a separate `.dbf` file for each table.

### 4.2. Size and Growth Capability

When inspecting a datafile, distinguish between:

| Attribute | Meaning |
|---|---|
| Current size (`BYTES`) | File size currently recorded by Oracle |
| `AUTOEXTENSIBLE` | Whether Oracle is allowed to extend the file when needed per configuration |
| `MAXBYTES` | Maximum configured size or limit according to the file mode |
| Free space inside the tablespace | Blocks/extents not yet allocated to segments, per the tablespace management mechanism |
| Free space in the storage system | Remaining space on the filesystem/ASM disk group or storage service |

For example, suppose a datafile is currently 2 GB with autoextend enabled up to 8 GB. That **does not mean** you immediately have 6 GB of physical space available: expansion capability also depends on remaining storage system space, quotas, file limits, configuration, and conditions at the time extension is needed.

Similarly, seeing `du` or `ls -lh` report a large file does not tell you how many rows are stored. Oracle may have allocated blocks to segments while only a portion of those blocks contain application data.

### 4.3. When Do You Need to Add or Extend a Datafile?

This is an administrative operation when a tablespace lacks allocatable space. A DBA can adjust autoextend, resize a file, or add a datafile using the **appropriate Oracle statement**, depending on the tablespace type and storage approach. The following example is for reading syntax only—**do not run it on a lab machine without proper authorization and a capacity plan**:

```sql
-- Illustrates an administrative option for a smallfile tablespace.
-- Path, size, and tablespace name must be replaced with the real configuration.
ALTER TABLESPACE app_data
  ADD DATAFILE '/u02/oradata/LABDB/app_data03.dbf'
  SIZE 256M AUTOEXTEND ON NEXT 64M MAXSIZE 4G;
```

In practice, adding files to a bigfile tablespace does not work the same way; in OMF/ASM environments the syntax may not require specifying a filesystem filename. Expansion is performed only after the DBA confirms storage location, limits, backup policies, and compliance with operational rules.

## 5. Segment: Space Allocated to Tables, Indexes, and Other Structures

### 5.1. What Is a Segment?

A **segment** is the set of extents Oracle has allocated for a storage entity. It is a concept reflecting **allocated space**, distinct from the logical definition of a table.

Common segment types:

| Segment Type | What Does It Contain? | Notes |
|---|---|---|
| `TABLE` | Data of a regular heap table | A non-partitioned table can have one segment |
| `INDEX` | Index structure | Separate from the table segment |
| `LOBSEGMENT` | LOB data stored out-of-line per configuration | May be accompanied by a `LOBINDEX` or auxiliary structure |
| `TABLE PARTITION`, `INDEX PARTITION` | Segment for each partition | A partitioned table/index can have many segments |
| `TABLE SUBPARTITION`, `INDEX SUBPARTITION` | Subpartition-level segment | Depends on partitioning design |
| `UNDO` | Undo data | Managed by the undo mechanism |
| `TEMPORARY` | Temporary space during processing | Distinct lifecycle and monitoring method |

Not every SQL object has its own segment:

- A **standard view** stores a query definition and has no data/segment of its own like a table.
- **Sequences**, synonyms, and metadata have different storage characteristics; you cannot mechanically apply "one object = one segment".
- A table's **index** is usually a separate segment; therefore, creating a `PRIMARY KEY` can result in an index segment alongside the table segment.
- A **partitioned table** can organize data into multiple segments by partition/subpartition.
- Large **LOBs** may use separate segments depending on structure and storage settings.
- **Deferred segment creation**: a newly created table might not have a segment allocated until actually needed; hence its name appears in `USER_TABLES` without a corresponding row in `USER_SEGMENTS`.

### 5.2. Which Tablespace Does a Segment Belong To?

Typically, **each segment belongs to one tablespace** and is allocated extents from the datafiles of that tablespace. A single table can involve multiple segments in different tablespaces: the table segment in `APP_DATA`, the index segment in `APP_INDEX`, and the LOB segment in `APP_LOB`.

Do not state "the ORDERS table resides in one datafile" as a rule: a table can have multiple extents, and extents of the same segment can be spread across multiple datafiles of the tablespace.

### 5.3. Allocated Segment Space and Actual Data Can Differ

Suppose `ORDERS` has 128 MB allocated by Oracle for its table segment, while row payload and metadata account for only about 75 MB:

```text
128 MB segment allocated
|-------------------------------|
| data + metadata | free space  |
|-----------------|-------------|
```

Do not deduce actual figures by simple subtraction because blocks also contain headers, transaction info, reserved free space, and possibly space that previously held deleted rows. `USER_SEGMENTS.BYTES` or `DBA_SEGMENTS.BYTES` primarily shows the **space allocated to the segment**, not the useful row-level data size.

## 6. Extent: The Unit of Additional Space Allocation for a Segment

### 6.1. What Is an Extent?

An **extent** is a group of **contiguous Oracle data blocks within the same datafile** allocated to **one segment**. When a segment needs more space and already-allocated blocks can no longer accommodate it, Oracle can allocate another extent from suitable free space in the tablespace.

Example of an extent consisting of 8 blocks, each 8 KB:

```text
Extent #0 in datafile 5:
  block 120  block 121  block 122  block 123
  block 124  block 125  block 126  block 127

  8 blocks × 8 KB/block = 64 KB
```

A segment can own multiple extents:

```text
Segment APP.ORDERS
  Extent 0  -> file 5, starting block 120, 8 blocks
  Extent 1  -> file 5, starting block 256, 8 blocks
  Extent 2  -> file 6, starting block 640, 16 blocks
```

The numbers above are illustrative only. A segment's extents **do not need to be adjacent**, nor must they be in the same datafile; it is each individual extent that requires a contiguous sequence of blocks **within one file**.

### 6.2. Extent Size and Allocation Mechanisms

Oracle has several extent management mechanisms, most commonly **locally managed tablespaces (LMT)** using bitmaps:

- **`AUTOALLOCATE`**: Oracle selects the extent size based on an appropriate allocation policy/mechanism; extents of one segment may vary in size.
- **`UNIFORM SIZE`**: extents in the tablespace are allocated in a predetermined uniform size (within Oracle's rules for that tablespace type).

This means:

- "An extent is always 64 KB" is **false**; 64 KB is only an example.
- "All extents of a segment are always the same size" is also **incorrect** in setups using autoallocate.
- A high extent count alone is not enough to conclude there is a performance problem; you must examine access patterns, segment structure, allocation strategy, and actual runtime evidence.

Inspecting extents can show you across how many files a segment is allocated, its total size, or the starting block location of each extent.

### 6.3. When Does Oracle Allocate Another Extent?

A simplified cycle for a heap table:

```text
INSERT new rows
       |
       v
Oracle searches for a block with enough space in the segment
       |
       +-- Space found --> writes data into a suitable block
       |
       +-- No suitable space left
               |
               v
       Oracle needs to extend the segment
               |
               +-- Does the tablespace have an allocatable extent?
                      |
                      +-- Yes --> allocates another extent to the segment
                      |
                      +-- No --> may need to extend the datafile,
                                     if permitted and resources exist
                                     |
                                     +-- Cannot extend --> error
```

This diagram only describes the concept of space allocation, not the detailed internal algorithm for every segment type. Oracle does **not** create a new extent on **every `INSERT`**. Many rows share a single data block; many blocks reside together within an existing extent.

### 6.4. Why Does Deleting Rows Not Immediately Release Extents?

`DELETE` logically removes rows and generates the required undo, but it does not automatically return extents from the segment back to the tablespace. The freed space after deletion can typically be **reused within the segment**, depending on block organization and space management mechanisms.

`TRUNCATE` behaves differently from `DELETE`: it typically resets the high water mark to an appropriate state and can release extents depending on storage options (`DROP STORAGE`/`REUSE STORAGE`), though it is DDL and performs an implicit commit. Structural commands such as `ALTER TABLE ... MOVE`, shrink, and reclaim methods require checking preconditions, impact on indexes/ROWIDs, and DBA evaluation before use.

**Never use OS commands to delete individual "extents"**: an extent is a unit managed by Oracle **inside a datafile**, not a separate file listed by `ls`.

## 7. Data Block: The Smallest Logical Storage Unit in the Hierarchy

### 7.1. What Does an Oracle Data Block Contain?

An **Oracle data block** is the smallest logical unit used to manage data storage space in this model. Multiple blocks form an extent; multiple extents form a segment.

A data block can contain:

- **Block header** and block-management metadata.
- **Transaction entries** to support concurrency control.
- **Row directory** so Oracle can locate rows within the block.
- **Row data** for heap table data blocks.
- **Free space** for future writes/updates.

Simplified model:

```text
  +----------------------------------------------------+
  | Block header + transaction information             |
  +----------------------------------------------------+
  | Row directory / locator information                |
  +----------------------------------------------------+
  | Row data (rows or row pieces)                      |
  |                                                    |
  +----------------------------------------------------+
  | Free space                                         |
  +----------------------------------------------------+
```

Header size, block layout, and data organization depend on segment type, block format, and runtime state. Index blocks and undo blocks do not have the exact same layout as heap table blocks.

### 7.2. Block Size Differs from Sector and OS Block Size

The common Oracle data block size in many environments is **8 KB**, though the actual value is determined by the database/tablespace configuration. Most tablespaces use the standard block size `DB_BLOCK_SIZE`, while some configurations support tablespaces with a nonstandard block size when corresponding conditions are met.

Examples:

| Assumption | Calculation |
|---|---|
| 1 Oracle block = 8 KB | 8,192 bytes/block |
| 1 extent = 64 KB | 8 Oracle blocks |
| 1 extent = 1 MB | 128 Oracle blocks |
| Segment with four 1 MB extents | 4 MB of space allocated to the segment |

The calculations above describe **allocated block capacity**, without subtracting internal block management overhead and without reflecting how much actual row data is present. Actual I/O sizes may encompass multiple Oracle blocks; do not confuse an Oracle data block with the filesystem's read unit size.

### 7.3. `PCTFREE`, Row Inserts, and Row Updates

For heap table blocks, Oracle has mechanisms to manage free space. The **`PCTFREE`** attribute indicates the percentage of space in a block reserved for row growth caused by updates, according to block usage policy.

For instance, if a table stores customer information and later updates a description field to be longer, keeping free space in the block can help avoid moving the row to another block. When an updated row no longer fits in its original location, **row migration** can occur; when a row's data requires multiple blocks from the start, **row chaining** can occur.

`PCTFREE` does not mean "10% of the entire tablespace is always empty" or "each extent uses at most 90%". It is an attribute governing **block usability** for applicable segments, not a tablespace capacity metric.

### 7.4. How Does the High Water Mark (HWM) Relate to Blocks?

The **High Water Mark** represents the boundary of blocks that have ever been used/formatted within the segment's management scope per Oracle's mechanism. Some full table scan operations may have to examine blocks below the HWM, even if many rows were later `DELETE`d.

Therefore, after deleting many rows:

1. Row count decreases.
2. `USER_SEGMENTS.BYTES` may remain unchanged.
3. Extent count may remain unchanged.
4. Empty space inside the segment can be reused.
5. The datafile does not automatically shrink by the exact number of deleted data bytes.

This is one reason to distinguish between **logical data**, **used blocks**, **segment allocated space**, and **file size**.

## 8. Storage Hierarchy Through an Arithmetic Example

Suppose a database has a tablespace `APP_DATA` with two datafiles and an 8 KB block size:

```text
APP_DATA
  |
  +-- app_data01.dbf      512 MB
  +-- app_data02.dbf      512 MB
```

Suppose a table segment `ORDERS` is allocated:

```text
Extent 0:  64 KB =   8 blocks, file 1
Extent 1:  64 KB =   8 blocks, file 1
Extent 2: 1 MB   = 128 blocks, file 2
Extent 3: 1 MB   = 128 blocks, file 2
```

Total extent capacity allocated to the segment in this example:

```text
  64 KB + 64 KB + 1024 KB + 1024 KB = 2176 KB
  Total blocks = 8 + 8 + 128 + 128 = 272 blocks
```

From this we can deduce:

- `ORDERS` has **4 extents** and **272 allocated blocks** in the example.
- Total segment space allocated across extents is **2.125 MB** (2,176 KB divided by 1,024).
- The segment uses **two datafiles** yet still **belongs to one tablespace**, `APP_DATA`.
- The two datafiles have a combined current size of **1,024 MB**, which does not mean all of that is free for `ORDERS`: other segments, metadata, and already-allocated space share the tablespace.
- You cannot deduce the number of rows in `ORDERS` from 272 blocks alone because rows per block depend on row size, headers, emptiness, block type, and data state.

This is an arithmetic example illustrating structural relationships, not a guarantee that Oracle will allocate the exact sequence 64 KB, 64 KB, 1 MB, 1 MB in every version/configuration.

## 9. Which Segments Can a Table Involve?

Consider a sales schema:

```text
TABLE: ORDERS
    |-- Table segment (row data)
    |-- Primary key index segment
    |-- Index on CUSTOMER_ID
    |-- LOB segment for ATTACHMENT column (if present)
    |-- Separate partition segments (if partitioned)
```

Example designing a table and index in two separate tablespaces:

```sql
-- DDL illustration only; requires appropriate tablespaces and quotas.
CREATE TABLE orders (
    order_id     NUMBER NOT NULL,
    customer_id  NUMBER NOT NULL,
    total_amount NUMBER(12, 2) NOT NULL,
    CONSTRAINT pk_orders PRIMARY KEY (order_id)
)
TABLESPACE app_data;

CREATE INDEX idx_orders_customer
    ON orders(customer_id)
    TABLESPACE app_index;
```

Note: a `PRIMARY KEY` is typically enforced by Oracle with an index. If you do not specify the index's tablespace for the constraint, that index may be created in a tablespace according to default/configured rules. Therefore, even this example can create **multiple segments** in different locations.

If the table is partitioned by month:

```text
ORDERS (logical table)
   |
   +-- ORDERS_P202601 : table partition segment
   +-- ORDERS_P202602 : table partition segment
   +-- ORDERS_P202603 : table partition segment
```

Each partition can have its own segment and can be placed in a separate tablespace depending on configuration. You cannot conclude that `USER_SEGMENTS` must contain exactly one row with `SEGMENT_NAME = 'ORDERS'` for every partitioned table; you also need to inspect `SEGMENT_TYPE` and `PARTITION_NAME` (when present) to understand the structure.

## 10. Reading the Actual Structure Through Data Dictionary Views

Oracle provides views for inspecting tablespaces, files, segments, and extents. This is a more reliable way to observe storage than guessing from `.dbf` filenames.

### 10.1. Views to Remember

| View | Object | Typical Access Privilege |
|---|---|---|
| `USER_TABLES` | Tables owned by the currently logged-in schema | Regular user |
| `USER_SEGMENTS` | Segments owned by the currently logged-in schema | Regular user |
| `USER_EXTENTS` | Extents of segments owned by the currently logged-in schema | Regular user |
| `USER_INDEXES` | Index information in the schema | Regular user |
| `DBA_TABLESPACES` | Tablespace info in the queried database/container | Requires appropriate dictionary view privileges |
| `DBA_DATA_FILES` | Datafiles and sizes related to permanent/undo tablespaces | Requires appropriate dictionary view privileges |
| `DBA_TEMP_FILES` | Tempfiles of temporary tablespaces | Requires appropriate dictionary view privileges |
| `DBA_SEGMENTS` | Segments across multiple schemas | Requires appropriate dictionary view privileges |
| `DBA_EXTENTS` | Extents across multiple schemas | Requires appropriate dictionary view privileges |
| `DBA_FREE_SPACE` | Free-space extents in permanent tablespaces per the view | Requires appropriate dictionary view privileges |

The following examples are written for Oracle SQL*Plus/SQLcl or any tool capable of running SQL. In a CDB/PDB architecture, results depend on the **connected container/PDB** and privileges; an account in one PDB does not necessarily see the entire database across containers.

### 10.2. Viewing Segments in the Current Schema

```sql
SELECT segment_name,
       segment_type,
       tablespace_name,
       bytes,
       blocks,
       extents
FROM user_segments
ORDER BY tablespace_name, segment_type, segment_name;
```

Meaning of key columns:

- `SEGMENT_NAME`: name of the segment or associated storage object.
- `SEGMENT_TYPE`: TABLE, INDEX, LOBSEGMENT, PARTITION variants...
- `TABLESPACE_NAME`: tablespace containing the segment.
- `BYTES`: total bytes allocated to the segment.
- `BLOCKS`: total blocks allocated to the segment.
- `EXTENTS`: number of extents allocated to the segment.

Do not interpret `BYTES` as "the total data size of all rows". It reflects the **allocated space** for the segment at the time of the query.

### 10.3. Viewing Individual Extents of a Segment

For a non-partitioned table named `DEMO_STORAGE`:

```sql
SELECT segment_name,
       segment_type,
       tablespace_name,
       extent_id,
       file_id,
       block_id,
       blocks,
       bytes
FROM user_extents
WHERE segment_name = 'DEMO_STORAGE'
ORDER BY extent_id;
```

Explanation:

| Column | Meaning |
|---|---|
| `EXTENT_ID` | Sequence number of the extent within the segment |
| `FILE_ID` | Identifier of the datafile Oracle uses for the extent |
| `BLOCK_ID` | Starting block of the extent within that datafile |
| `BLOCKS` | Number of blocks in the extent |
| `BYTES` | Extent size in bytes |

If `FILE_ID` changes across rows, you are seeing a segment's extents allocated across **multiple datafiles**. If `BLOCKS` differs across extents, the tablespace likely uses an allocation mechanism with variable extent sizes.

**Illustrative** sample output (not live executed output):

```text
EXTENT_ID  FILE_ID  BLOCK_ID  BLOCKS  BYTES
---------  -------  --------  ------  -------
        0        7       128       8    65536
        1        7       256       8    65536
        2        8      1024     128  1048576
```

The output above means extent 0 is in file 7, starting at block 128 and consisting of 8 blocks; extent 2 lies entirely in file 8. It does **not** mean Oracle stored "one row per extent".

### 10.4. Mapping `FILE_ID` to Datafile Name

To view the physical/logical filename of the file an extent is using, a DBA can run:

```sql
SELECT e.owner,
       e.segment_name,
       e.segment_type,
       e.extent_id,
       e.file_id,
       f.file_name,
       e.block_id,
       e.blocks,
       e.bytes
FROM dba_extents e
JOIN dba_data_files f
  ON f.file_id = e.file_id
 AND f.tablespace_name = e.tablespace_name
WHERE e.owner = 'APP'
  AND e.segment_name = 'DEMO_STORAGE'
ORDER BY e.extent_id;
```

In the example, `'APP'` is a placeholder schema to replace with the schema being inspected; the statement requires appropriate privileges on `DBA_` views. For partitioned or LOB objects, expand the filter/selected columns to inspect the exact segment and partition. Temporary space is not queried this way because it uses tempfiles and dedicated management views.

### 10.5. Viewing Tablespaces and Datafiles

To check tablespace configuration:

```sql
SELECT tablespace_name,
       contents,
       block_size,
       extent_management,
       allocation_type,
       segment_space_management,
       bigfile
FROM dba_tablespaces
ORDER BY tablespace_name;
```

To list datafiles:

```sql
SELECT tablespace_name,
       file_id,
       file_name,
       bytes,
       autoextensible,
       maxbytes
FROM dba_data_files
ORDER BY tablespace_name, file_id;
```

And for tempfiles:

```sql
SELECT tablespace_name,
       file_id,
       file_name,
       bytes,
       autoextensible,
       maxbytes
FROM dba_temp_files
ORDER BY tablespace_name, file_id;
```

`BLOCK_SIZE` tells you the Oracle block unit of the tablespace; `ALLOCATION_TYPE` relates to how extents are allocated; `SEGMENT_SPACE_MANAGEMENT` indicates the mechanism managing free space inside segments. These are **different concepts**: extent allocation occurs at the tablespace/segment level, whereas free-space management inside blocks occurs at the segment level.

### 10.6. Viewing Free Space in Permanent Tablespaces

```sql
SELECT tablespace_name,
       ROUND(SUM(bytes) / 1024 / 1024, 2) AS free_mb
FROM dba_free_space
GROUP BY tablespace_name
ORDER BY tablespace_name;
```

This query shows the sum of free extents reported by `DBA_FREE_SPACE`, which **is not necessarily the total capacity available for future growth**. It does not include unused autoextend capacity, does not fully reflect filesystem/ASM limits, and differs in how temporary tablespaces are tracked. Tablespaces with no rows in the view may not appear in the aggregate result, so you must also inspect files and space status.

Do not equate:

```text
Existing datafile  ≠  Allocated segment  ≠  Useful stored data

Free extents in tablespace
    ≠ Free space inside blocks allocated to a segment
    ≠ Remaining storage capacity available to extend files
```

## 11. Practice: Seeing the Relationship from a Real Table

This section targets a lab schema with `CREATE TABLE` privilege and sufficient quota on its default tablespace. Perform this only in a schema authorized for object creation. If you only have read access, skip the DDL/DML parts and run `SELECT` queries on existing objects you are permitted to view.

### Step 1. Create a Small Table Requiring Immediate Segment Allocation

```sql
CREATE TABLE demo_storage (
    id      NUMBER NOT NULL,
    payload VARCHAR2(100),
    CONSTRAINT pk_demo_storage PRIMARY KEY (id)
)
SEGMENT CREATION IMMEDIATE;
```

Note that `PRIMARY KEY` may cause Oracle to create an additional **index segment**. `SEGMENT CREATION IMMEDIATE` is used to focus on observing the table segment immediately after creation, rather than depending on when Oracle defers segment allocation. DDL performs an implicit commit; never use a production table to test this operation.

### Step 2. Inspect Table, Index, and Tablespace

```sql
SELECT table_name, tablespace_name
FROM user_tables
WHERE table_name = 'DEMO_STORAGE';

SELECT index_name, index_type, tablespace_name
FROM user_indexes
WHERE table_name = 'DEMO_STORAGE';
```

If `TABLESPACE` is not specified in the DDL, Oracle applies default rules and the user's privileges/quotas to choose the tablespace. An index can be a separate segment, and the index's tablespace is not necessarily what a learner might assume.

### Step 3. Inspect Allocated Segments

```sql
SELECT segment_name,
       segment_type,
       tablespace_name,
       extents,
       blocks,
       bytes
FROM user_segments
WHERE segment_name = 'DEMO_STORAGE'
   OR segment_name IN (
       SELECT index_name
       FROM user_indexes
       WHERE table_name = 'DEMO_STORAGE'
   )
ORDER BY segment_type, segment_name;
```

You can observe at least the structures related to the table and index once the segments have been allocated according to database conditions. If the index segment does not appear immediately, inspect the actual creation/allocation mechanism; do not assume from the object name alone that a dictionary row must exist prior to any operation.

### Step 4. Inspect Extent Details of the Table Segment

```sql
SELECT segment_name,
       extent_id,
       file_id,
       block_id,
       blocks,
       bytes
FROM user_extents
WHERE segment_name = 'DEMO_STORAGE'
  AND segment_type = 'TABLE'
ORDER BY extent_id;
```

Record `EXTENT_ID`, `FILE_ID`, `BLOCK_ID`, and `BLOCKS`. Each row corresponds to an extent and shows which location in which datafile it maps to.

### Step 5. Insert Data and Observe Again

```sql
INSERT INTO demo_storage (id, payload)
SELECT LEVEL, RPAD('x', 100, 'x')
FROM dual
CONNECT BY LEVEL <= 1000;

COMMIT;
```

Then re-run the two `USER_SEGMENTS` and `USER_EXTENTS` queries above. It is **not guaranteed** that you will see additional extents, because the result depends on pre-allocated space, block size, space settings, and segment structure. What you need to recognize is that **increasing the row count does not increase the extent count at a 1:1 ratio**.

You can check the row count using:

```sql
SELECT COUNT(*) AS row_count
FROM demo_storage;
```

At the same time, `USER_SEGMENTS.BYTES` may be significantly larger than the `1000 × 100 bytes` payload: that is normal because of metadata, indexes, free space, and block/extent-level allocation.

### Step 6. Delete Part of the Rows and Inspect Extents

```sql
DELETE FROM demo_storage
WHERE id <= 500;

COMMIT;
```

Run again:

```sql
SELECT COUNT(*) AS row_count FROM demo_storage;

SELECT segment_name, extents, blocks, bytes
FROM user_segments
WHERE segment_name = 'DEMO_STORAGE';
```

If the row count dropped while `EXTENTS` and `BYTES` did not decrease, that illustrates the difference between **existing rows** and **space allocated to the segment**. Do not attempt to manually "shrink" files on the operating system.

### Step 7. Clean Up the Practice Object When No Longer Needed

Only in a lab schema and after confirming it is the exact object you created:

```sql
DROP TABLE demo_storage PURGE;
```

`PURGE` bypasses the recycle bin for this table under the corresponding mechanism, so **do not use it on tables that may need recovery**. Dropping is destructive and DDL performs an implicit commit. If you are not permitted or are unsure of the schema, let the DBA/environment administrator handle it.

### Record Your Lab Results

| Metric | After CREATE | After INSERT | After DELETE |
|---|---|---|---|
| Row count `COUNT(*)` | 0 | ... | ... |
| Table segment extent count | ... | ... | ... |
| Blocks allocated to table segment | ... | ... | ... |
| Bytes allocated to table segment | ... | ... | ... |
| Separate index segment present? | ... | ... | ... |

The objective is to **observe storage relationships**, not to predict a fixed extent count. Actual results vary by Oracle version and configuration.

## 12. Operational Scenarios Directly Related to Storage Relationships

### 12.1. `ORA-01653`: Unable to Extend Table Segment

An error such as:

```text
ORA-01653: unable to extend table ... in tablespace ...
```

usually indicates that Oracle cannot allocate another suitable extent for the table segment in the named tablespace. Causes to check include:

1. Does the tablespace still have suitable free extents?
2. Is the datafile allowed to autoextend, and has it hit its limit?
3. Does the filesystem or ASM disk group have enough space?
4. Are there related quota limits, tablespace/file limits, or administrative policies?
5. Does the specific segment have any notable storage characteristics?

You cannot fix this error merely by increasing `PCTFREE` or creating more indexes; the core issue is **the ability to allocate extents to the segment**.

### 12.2. `ORA-01654`: Unable to Extend Index Segment

An index also has its own segment/extents. If the index is placed in a different tablespace from the table, the index tablespace can run out of space even while the table's tablespace still has room. Therefore, query `USER_INDEXES`, `USER_SEGMENTS`, or `DBA_SEGMENTS` to see which tablespace the index belongs to.

### 12.3. `ORA-01652`: Unable to Extend Temporary Segment

Some sort/join/query operations require temporary space. Errors like `ORA-01652` relate to an inability to allocate sufficient space for a temporary segment. In that case, inspect the **temporary tablespace, tempfiles, sessions using TEMP, and available capacity**, rather than focusing solely on the datafiles of table-storing tablespaces.

### 12.4. Why Does DML Fail Even When the Tablespace Has Free Space?

Overall capacity is only one of several conditions. The exact context also depends on the size of the extent to be allocated, file status, maxsize/autoextend limits, quotas, tablespace policies, and position in the storage model. `DBA_FREE_SPACE` results must be evaluated alongside datafile info and the actual error; do not rely on a single "free MB" number to draw conclusions.

### 12.5. Why Does a Table with a Few Thousand Rows Have a Fairly Large Segment?

This can be due to **stepped extent allocation**, partially used blocks, free space reserved for updates, previously deleted data, separate indexes/LOBs, or table organization features. When measuring size, specify whether you are measuring the **table segment alone**, **all related segments**, or **useful row data**.

### 12.6. Why Does the Tablespace Run Out of Space When the Disk Still Has Plenty of Room?

The disk and the tablespace are two separate layers. A datafile might be at a fixed size, have autoextend disabled, have reached maxsize, or the storage configured for that specific tablespace cannot grow through normal means. Seeing free filesystem space does not guarantee a segment can receive more extents.

## 13. Extent and Block Space Management: Mechanisms to Know

Two names frequently seen in Oracle storage descriptions:

| Mechanism | Scope | Meaning |
|---|---|---|
| **Locally Managed Tablespace (LMT)** | Manages extent allocation in a tablespace | Uses appropriate metadata/bitmaps to track allocated and free extents |
| **Automatic Segment Space Management (ASSM)** | Manages free space inside a segment | Uses bitmaps to manage blocks by available free-space level |

LMT answers the question: "**Which extents in the tablespace** can be allocated to a segment?". ASSM answers the question: "**Which blocks in the segment** have suitable space to write data?". These are two distinct management layers.

Some commonly viewed attributes:

```sql
SELECT tablespace_name,
       extent_management,
       allocation_type,
       segment_space_management
FROM dba_tablespaces
WHERE tablespace_name = 'APP_DATA';
```

`EXTENT_MANAGEMENT`, `ALLOCATION_TYPE`, and `SEGMENT_SPACE_MANAGEMENT` explain many allocation behaviors observed when inspecting extents/blocks. Requires appropriate dictionary view privileges.

## 14. Statements That Easily Cause Confusion

| Statement | True or False? | Explanation |
|---|---|---|
| "Each table in Oracle has its own datafile." | False | Multiple segments can share a datafile; a single segment can also span multiple datafiles via its extents |
| "An extent spans across two datafiles if space runs out." | False | An extent consists of contiguous blocks **within one datafile** |
| "A segment resides in only one tablespace." | True in principle per segment | A segment's extents are allocated within one tablespace; a logical object can have multiple segments across multiple tablespaces |
| "One datafile belongs to multiple tablespaces simultaneously." | False under the standard model | A datafile is associated with a single tablespace |
| "`USER_SEGMENTS.BYTES` is the exact size of currently stored rows." | False | That is the space allocated to the segment |
| "Deleting 90% of rows shrinks the datafile by 90%." | False | Space inside the segment can be reused without shrinking the file |
| "One `INSERT` creates one extent." | False | Multiple rows can share already-allocated blocks/extents |
| "A tablespace is just a directory storing `.dbf` files." | False | A tablespace is a logical object; datafiles/ASM files are storage representations |
| "All tablespaces have datafiles in the same way." | False | Temporary tablespaces typically use tempfiles |
| "Growing a datafile is the only way to fix space issues." | False | You must analyze root cause, reuse/reclaim options, autoextend, limits, and storage design |
| "A block is always 8 KB." | False | 8 KB is a common value, not a rule for all tablespaces |
| "A `CREATE TABLE` must appear immediately in `USER_SEGMENTS`." | Not always true | Deferred segment creation can postpone allocation |

## 15. Self-Check Questions

**Question 1.** Tablespace `APP_DATA` has two datafiles. Can segment `ORDERS` receive extents in both files?

**Answer:** Yes, in an appropriate configuration; the segment still belongs to one tablespace, and each extent is allocated within a specific datafile.

**Question 2.** Extent A contains 16 blocks of size 8 KB. How many KB of allocated space does that extent have?

**Answer:** `16 × 8 KB = 128 KB`. This is the extent size, which does not mean all 128 KB is useful row data.

**Question 3.** Table `CUSTOMERS` has 10 MB of data, while `USER_SEGMENTS.BYTES` reports 16 MB. Is there a contradiction?

**Answer:** No. Segments are allocated by extents/blocks and include metadata, free space, reserved space, or previously used space.

**Question 4.** Why can an index encounter an out-of-space error when the table's tablespace still has free space?

**Answer:** An index is a separate segment and may be placed in a different tablespace. You must check the corresponding index tablespace/segment.

**Question 5.** Datafile 1 has reached its limit, while datafile 2 in the same tablespace still has suitable space. Must the segment stop growing?

**Answer:** Not necessarily. Oracle can allocate extents from another datafile **in the same tablespace** when conditions are met. Actual behavior depends on storage configuration, tablespace type, and allocation availability.

**Question 6.** Why can't you find row-by-row data by opening `app_data01.dbf` in a text editor?

**Answer:** A datafile is an Oracle-managed storage format with blocks, metadata, and internal structures; accessing data must go through SQL and the Oracle engine. Manually modifying the file content can corrupt the database.

**Question 7.** Can you calculate the number of rows in a segment solely from `EXTENTS`, `BLOCKS`, and `BYTES`?

**Answer:** No. Those figures describe allocated space; row counts depend on data characteristics and block organization. Use appropriate SQL, reliable statistics, or dedicated analysis tools to determine it.

## 16. Conclusion

Oracle's storage relationships can be remembered along one axis:

```text
                      [TABLESPACE]
                      /          \
                     /            \
               [SEGMENTS]      [DATAFILES]
                   |               ^
               [EXTENTS] ---------+
                   |
              [DATA BLOCKS]
```

A **tablespace** is logical space, a **datafile** is the physical storage for blocks, a **segment** is space dedicated to a table/index/storage structure, an **extent** is an allocation unit of contiguous blocks in one datafile, and a **data block** is the smallest logical storage unit managed by Oracle in this model. One segment can receive multiple extents across multiple files in the same tablespace; multiple segments share those files.

When evaluating capacity or troubleshooting extension errors, separate **file size**, **free tablespace extents**, **allocated segment space**, **usable blocks**, and **actual row data**. This approach helps you read `USER_SEGMENTS`, `USER_EXTENTS`, `DBA_DATA_FILES`, and `DBA_TABLESPACES` accurately while better understanding Oracle Database's storage decisions.
