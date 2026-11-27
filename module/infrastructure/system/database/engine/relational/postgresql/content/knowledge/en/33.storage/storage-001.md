# Heap, Data Pages, and Tuple Structure in PostgreSQL

## 1. How Does PostgreSQL Store a Row in a Table?

When running:

```sql
INSERT INTO inventory.products(product_code, product_name, quantity)
VALUES ('BOOK-01', 'Practical PostgreSQL', 12);
```

we see a logical row consisting of three columns. However, PostgreSQL does not store a table as a list of Java objects or a CSV file. For a regular table, data is organized as a **heap relation**: a collection of data pages (*pages/blocks*), where each page has slots referencing the tuples (row versions) that currently exist or previously existed on the page.

Conceptual model:

```text
Database
  |
  +-- Schema
       |
       +-- Table (heap relation)
            |
            +-- Main fork
            |     +-- Block 0 / Page 0
            |     +-- Block 1 / Page 1
            |     +-- Block 2 / Page 2
            |     +-- ...
            |
            +-- FSM fork
            +-- VM fork
            +-- TOAST relation (if needed)
```

Each physical tuple contains information about the row version, the creating/deleting/updating transaction, data offsets, and column values. An index typically stores a **TID** pointing to the tuple's location in the heap, rather than storing the entire row itself as a full copy.

Key point: **a heap is not a structure automatically sorted by primary key**. If you want ordered results, the query still needs **ORDER BY**.

### Learning Objectives

After this lesson, you will be able to:

1. Explain a heap relation and why a heap does not guarantee row ordering.
2. Distinguish between relation, fork, segment, block/page, line pointer, and tuple.
3. Read the structure of a heap page at a conceptual level.
4. Describe the page header, line pointers area, free space, and tuple area.
5. Explain the tuple header, xmin, xmax, ctid, null bitmap, and alignment.
6. Understand why a logical row can have multiple tuple versions due to MVCC.
7. Distinguish ctid from a primary key and understand the limitations of system columns.
8. Describe TOAST and how PostgreSQL stores oversized values.
9. Understand HOT updates, fillfactor, and the role of free space.
10. Distinguish the Free Space Map (FSM) from the Visibility Map (VM).
11. Explain VACUUM, pruning, freezing, and bloat.
12. Understand the relationship between heap TID, index scan, and index-only scan.
13. Use appropriate functions/catalogs and extensions to inspect sizes, pages, and tuples.
14. Identify common misconceptions when reasoning from physical storage structure.

---

## 2. Terminology and Storage Hierarchy

| Term | Meaning |
|---|---|
| Database | A PostgreSQL database |
| Relation | A relational object such as a table, index, sequence, or view that has relation metadata |
| Heap relation | A relation that stores tuples as a heap-organized table |
| Fork | A physical file branch of a relation, e.g., main/FSM/VM |
| Segment | A file belonging to a relation; a large relation can be split into multiple segments |
| Block/Page | The unit of data page that PostgreSQL reads/writes at the storage level |
| Tuple | A row version stored in the heap |
| Line pointer / ItemId | An element in a page pointing to a tuple or indicating the slot state on the page |
| TID / ItemPointer | A heap location identifier consisting of a block number and an offset number |
| TOAST | Mechanism for storing/reducing the size of large varlena values |
| FSM | Free Space Map, tracking approximate available free space across pages |
| VM | Visibility Map, tracking whether a page is all-visible/all-frozen |

### 2.1. A Relation Does Not Mean a Single File

A small table may occupy only one main fork file. However, a large relation can have multiple segments; in addition, there are auxiliary forks and potentially a separate TOAST relation.

### 2.2. A Heap Is Not a Linked List in Insert Order

A page can hold multiple tuples, and new tuples may be placed on any page with sufficient free space. After an UPDATE, the new tuple version may reside on a different page or on the same page in the case of a HOT update. Never rely on physical order to represent business ordering.

### 2.3. Heap and Index Have Different Roles

- The heap holds tuples and tuple versions.
- An index provides a search path, typically leading to a heap TID to check/read the tuple.
- Some index-only scans can return results without a heap fetch when the Visibility Map allows it, yet indexes still have their own semantics.

## 3. Heap Pages and Block Size

PostgreSQL organizes data in pages/blocks. In most common installations, the page size is **8 KiB (8192 bytes)**.

Check with:

```sql
SHOW block_size;
```

Common output:

```text
 block_size
------------
 8192
```

### 3.1. Block Size Is a PostgreSQL Build Property

Block size is determined when PostgreSQL is built, not a property customizable per table via ALTER TABLE.

Do not assume every PostgreSQL build on every platform must be 8 KiB. Always read SHOW block_size on the actual server.

### 3.2. Page as the Unit of Physical Management

A heap page can contain:

- A header describing the page state.
- An array of line pointers.
- Free space for new or updated tuples.
- Heap tuples stored starting from the end of the page.

The number of rows per page is not fixed. It depends on tuple size, null bitmap, alignment, line pointers, TOAST pointers, and free space.

### 3.3. Calculating Approximate Block Count

For the main fork:

```sql
SELECT
    pg_relation_size('public.some_table'::regclass) AS main_bytes,
    current_setting('block_size')::integer AS block_bytes,
    pg_relation_size('public.some_table'::regclass)
        / current_setting('block_size')::integer AS main_blocks;
```

This is a division to estimate the number of blocks in the main fork. Do not mistakenly add index/TOAST sizes here.

## 4. Layout Diagram of a Heap Page

A typical page has the following conceptual layout:

```text
Page start / offset 0
+---------------------------------------------------+
| PageHeaderData                                    |
+---------------------------------------------------+
| ItemIdData #1                                     |
| ItemIdData #2                                     |
| ItemIdData #3                                     |
| ...                                               |
| (line pointer array grows from header)            |
+---------------------------------------------------+
|                                                   |
|             Free space                            |
|                                                   |
+---------------------------------------------------+
| Tuple C                                            |
|                                                   |
| Tuple B                                            |
|                                                   |
| Tuple A                                            |
+---------------------------------------------------+
Page end / BLCKSZ
```

Two opposing growth directions:

- The page header and line pointer array grow forward from the start of the page.
- Tuple data is placed backward from the end of the page toward the beginning.
- The region between the two is the usable free space.

### 4.1. Why Are Line Pointers Needed?

Indexes and TIDs reference a **line pointer slot**, not directly the byte offset of a tuple. If PostgreSQL needs to compact data within a page, the byte location of a tuple can change while the line pointer remains the reference point.

This allows the TID to continue identifying the slot on the page during appropriate page management operations.

### 4.2. Heap Pages Normally Do Not Use Special Space

The generic page structure may reserve a special space for the access method. A regular heap page does not need a separate special region like some index access methods do, so pd_special usually points to the end of the page.

Do not apply the detailed layout of a B-tree index page to a heap page: they are two page types with different purposes and structures.

## 5. PageHeaderData: Metadata at the Start of a Page

The page header holds information for managing the page. Important fields include:

| Field | General Role |
|---|---|
| pd_lsn | LSN of the most recent related WAL record applied to the page |
| pd_checksum | Page checksum field when checksums are enabled/used |
| pd_flags | Page status flags |
| pd_lower | Lower boundary of the line pointer array region (offset to start of free space) |
| pd_upper | Upper boundary of the tuple/free space region (offset to end of free space) |
| pd_special | Start of special space |
| pd_pagesize_version | Page size and format version information |
| pd_prune_xid | Metadata assisting in determining whether the page may need pruning |

In the common PostgreSQL layout, PageHeaderData occupies about **24 bytes**. This is an implementation detail; consult the source/documentation of your specific version if performing forensic analysis or writing byte-level tools.

### 5.1. pd_lower and pd_upper

For a normal heap page:

- pd_lower marks the end of the line pointer array.
- pd_upper marks the start of the tuple area from the end of the page.
- pd_upper - pd_lower is the contiguous free space between the two regions, which does not necessarily equal total reclaimable free space if the page has fragmentation or dead tuples needing pruning.

### 5.2. pd_lsn and WAL

WAL (Write-Ahead Logging) allows PostgreSQL to recover changes after a crash. The page LSN helps determine the WAL state reflected by the page according to recovery rules.

pd_lsn is neither a transaction ID nor a timestamp of the latest INSERT.

### 5.3. Checksum Is Not Encryption

Page checksums, if enabled, help detect certain forms of page corruption. They do not hide data from someone reading the file, do not encrypt the page, and do not replace backup/restore.

### 5.4. pd_prune_xid Is Not an Exact Dead Row Count

This is metadata supporting management/pruning and should not be used as a direct count of dead tuples on the page.

## 6. Line Pointers / ItemIdData

Each line pointer is a small entry on the page, typically **4 bytes**. It describes the tuple's offset and length along with the slot state.

Common states include:

- LP_UNUSED: unused slot.
- LP_NORMAL: slot pointing to a normal tuple.
- LP_REDIRECT: redirecting slot, usually related to a HOT chain/pruning.
- LP_DEAD: slot marked dead according to heap page state.

Flag names are internal details; exact display varies by inspection tool.

### 6.1. What Is an Offset Number?

A heap TID usually has the form:

```text
(block_number, offset_number)
```

offset_number identifies an entry in that block's line pointer array. It is **not an absolute byte offset** of the tuple in the file.

### 6.2. Why Are Line Pointers Important When Compacting a Page?

Tuple bytes can be moved inside the page to coalesce free space. PostgreSQL can update lp_off in the corresponding line pointer without having to change the slot's TID.

### 6.3. A Slot Does Not Mean a Permanent Logical Row

A row has multiple tuple versions under MVCC; a HOT chain may involve different line pointers/redirects. Never store ctid as a long-term business key.

## 7. What Is a Tuple?

A tuple is a **physical version of a row**. A logical row can go through:

```text
INSERT -> tuple version V1
UPDATE -> tuple version V2
UPDATE -> tuple version V3
DELETE -> V3 becomes a deleted version
```

With MVCC, PostgreSQL retains the versions needed so different transactions see data according to their snapshots. Therefore, a table with 1,000 current logical rows can still contain more than 1,000 physical tuples due to old versions, dead tuples, or data not yet VACUUMed/pruned.

### 7.1. Tuple Header and Tuple Data

A physical tuple conceptually consists of two parts:

```text
Heap tuple
+----------------------------------+
| Tuple header                     |
|  - xmin / xmax / command info    |
|  - ctid                          |
|  - infomask flags                |
|  - header offset                 |
|  - optional null bitmap          |
+----------------------------------+
| Attribute data                   |
|  - column 1                      |
|  - column 2                      |
|  - padding/alignment             |
|  - column 3                      |
|  - varlena / TOAST pointer       |
+----------------------------------+
```

Tuple size is not simply the sum of the displayed value lengths. You must include the header, optional null bitmap, alignment/padding, and other physical data structures.

### 7.2. Fixed Header and Extension

HeapTupleHeaderData has fixed-size fields; followed optionally by a null bitmap, with attribute data starting at the offset recorded in t_hoff. The header requires appropriate alignment.

The minimum header size is commonly described as around 23 bytes before padding/optional bitmap; do not use this figure as an absolute size formula for every tuple.

## 8. MVCC Fields in the Tuple Header

Important fields include:

| Field | Role |
|---|---|
| xmin | Transaction ID that created the tuple version |
| xmax | Transaction ID/metadata related to deletion, replacement, or tuple locking |
| cmin / cmax | Command ID related to operations within a transaction |
| ctid | TID of the current tuple or location of the next tuple version depending on context |
| infomask | Status flag bits of the tuple |
| infomask2 | Additional status flag bits, including information related to attribute count |
| t_hoff | Offset to the attribute data section within the tuple |

### 8.1. xmin

xmin identifies the transaction that created the tuple version. A transaction only sees the tuple when snapshot/transaction visibility rules permit.

### 8.2. xmax Does Not Always Mean "Deleted"

xmax can represent a transaction that deleted or replaced the tuple, but it can also represent tuple locking or MultiXact metadata. Do not read xmax <> 0 and conclude for certain that the row is deleted for all transactions.

### 8.3. cmin/cmax

Command IDs distinguish commands within the same transaction. They are part of the MVCC/visibility mechanism, not an application audit timestamp column.

### 8.4. Infomask

Flags in infomask indicate tuple properties, such as presence of a null bitmap, transaction confirmation status via hint bits, external/varlena attributes, or other states. These are implementation details; use standard tools rather than hard-coding bit masks in application code.

## 9. System Columns: xmin, xmax, ctid, tableoid

PostgreSQL exposes several queryable system columns:

```sql
SELECT
    tableoid::regclass AS physical_relation,
    ctid,
    xmin,
    xmax,
    customer_id,
    full_name
FROM public.customers;
```

These columns are not declared in DDL as ordinary business columns.

### 9.1. ctid

ctid represents the physical location of the tuple version in the relation, typically in the form (block, offset).

It is useful for:

- Page/tuple debugging.
- Observing tuple versions.
- Labs on UPDATE/HOT/VACUUM.
- Certain internal operations with tight transaction scope and strict control.

It is unsuitable as a primary key or external identifier.

### 9.2. UPDATE Can Change ctid

UPDATE typically creates a new tuple version. The old tuple's ctid can point to the new tuple version. Thus, a row's ctid can change after an UPDATE.

VACUUM FULL, CLUSTER, or relation rewrite operations can change physical locations much more broadly.

### 9.3. xmin Is Not created_at

xmin is a transaction ID, not the row creation timestamp. Transaction IDs have lifecycles, wraparound/freeze behavior, and internal semantics; do not use it in place of created_at.

### 9.4. xmax Is Not deleted_at

xmax is not a deletion timestamp. If you need to audit change times or actors, create dedicated columns or history/audit tables.

### 9.5. tableoid in Partitioned Tables

When querying through a partitioned table, tableoid helps identify the physical relation/partition containing the tuple. This is useful metadata when investigating partitioning, not tenant authorization.

## 10. Tuple Visibility: Why Can the Same Page Hold Old and New Versions?

MVCC allows multiple transactions to read different snapshots without locking every row for reading. An example:

```text
Initially: quantity = 5 (tuple V1)

T1: BEGIN
T1: UPDATE quantity = 4
    -> creates tuple version V2

T2: using an older snapshot
    -> can still see V1

T1: COMMIT

New transaction
    -> sees V2

V1 can only be reclaimed when no snapshot still needs to see it
```

Visibility depends on transaction status, snapshot, and tuple metadata; never inspect a single xmin or xmax field in isolation and infer visibility on your own.

### 10.1. UPDATE Usually Creates a New Version

In a PostgreSQL heap, UPDATE usually does not overwrite every byte of the old tuple directly as in a simple in-place model. It creates a new version and marks the old version under MVCC rules.

### 10.2. DELETE Does Not Immediately Erase Bytes

DELETE marks the tuple as invalid for future snapshots once the deleting transaction commits, while the physical bytes may remain until pruning/VACUUM can reclaim them.

### 10.3. Dead Tuples Depend on the Snapshot Horizon

A tuple version can only be removed when no active transaction/snapshot needs it. Long-running transactions or replication slots holding an old horizon can delay reclamation.

## 11. UPDATE, DELETE, and Bloat

Suppose a row is UPDATED 100 times. The table does not necessarily keep just one single tuple. It may go through many versions:

```text
Page 0:
  old tuple version (dead when no longer needed)
  new tuple version

Page 1:
  several other versions

FSM:
  tracks usable free space

VACUUM/pruning:
  reclaims dead tuples when safe
```

### 11.1. What Is Bloat?

Bloat is physical space that no longer holds useful live data or is inefficiently utilized due to update/delete churn, page fragmentation, stale index entries, and other factors.

There is no single bloat figure that is universally exact across all measurement methods; understand the tool and methodology.

### 11.2. A Table with Few Rows Can Still Be Large

If a table once held millions of records and most were deleted, the file may still retain many pages for reuse. A small COUNT(*) does not prove a small file.

### 11.3. Heap Bloat and Index Bloat Are Different

- Heap bloat: page/tuple storage has underutilized space.
- Index bloat: index structures contain dead/underused pages or inefficient distribution.

VACUUM and REINDEX solve different problems; do not treat them as interchangeable.

## 12. TOAST: Storing Large Values

PostgreSQL uses **TOAST** (*The Oversized-Attribute Storage Technique*) for large varlena values such as text, bytea, jsonb, and types with suitable representations.

When a tuple has attributes too large relative to the inline storage target, PostgreSQL can:

1. Compress the value.
2. Move the value out to a TOAST relation.
3. Store a pointer/descriptor in the main tuple.
4. Split the out-of-line value into chunks in the TOAST table.

Diagram:

```text
Main heap tuple
+-----------------------------+
| id = 10                     |
| title = 'Document'          |
| body = TOAST pointer ------+-----------------+
+-----------------------------+                 |
                                                v
                                   TOAST relation
                                   +------------------+
                                   | value chunks     |
                                   | chunk sequence   |
                                   | chunk data       |
                                   +------------------+
```

### 12.1. A TOAST Relation Is a Separate Relation

A table with TOASTed values can have its own TOAST table and index. pg_total_relation_size includes the associated components per function semantics; pg_relation_size of the main table does not account for the full footprint.

### 12.2. Not Every Text Value Goes to TOAST

Small values are normally stored inline. The decision depends on tuple size, column storage strategy, and page conditions.

### 12.3. TOAST Is Not the Large Objects API

PostgreSQL Large Objects (lo_*) are a separate mechanism with their own API/metadata. Do not equate every large bytea or large text column with Large Objects.

## 13. TOAST Storage Strategies

Common storage strategies:

| Strategy | Compression | Out-of-line | Purpose |
|---|---|---|---|
| PLAIN | No | No | Keep inline, no compression |
| EXTENDED | Possible | Possible | Compress first, move out-of-line if needed |
| EXTERNAL | No | Possible | Move out-of-line without compression |
| MAIN | Possible | Restricted/prefer inline | Try to keep inline, only move out-of-line if necessary |

Example of changing a storage strategy:

```sql
ALTER TABLE documents
ALTER COLUMN body SET STORAGE EXTERNAL;
```

This changes the policy for storing values processed in the future according to PostgreSQL semantics; do not assume it immediately rewrites all existing data.

### 13.1. Compression Algorithm Depends on Version/Build

PGLZ is the traditional choice; some versions/builds support LZ4. Verify actual server capabilities and COMPRESSION syntax before relying on a specific algorithm.

### 13.2. Compression Does Not Always Reduce Total Cost

Compression has a CPU cost. If a workload frequently reads full large JSON/text values, decompression can affect latency. If a workload mainly reads metadata, TOAST keeps the main tuple compact.

### 13.3. A TOAST Pointer Is Still Metadata

Even when the value lives out-of-line, the main tuple retains the metadata needed to locate that value. Reading a TOASTed column can incur extra I/O and detoasting.

## 14. Null Bitmap and NULL Representation

A tuple can contain a null bitmap to indicate which attributes are NULL.

Example table:

```sql
CREATE TABLE sample_nulls (
    id integer NOT NULL,
    nickname text,
    age integer,
    note text
);
```

A tuple:

```text
id       = 1
nickname = NULL
age      = 20
note     = NULL
```

The null bitmap records the null status of attributes. A NULL value is not stored as an ordinary zero-length byte sequence.

### 14.1. NULL Differs from Empty String

- SQL NULL: absence of value / unknown per SQL semantics.
- '': zero-length string.
- 0: the number zero.
- false: boolean value false.

These states have different representations and query behaviors.

### 14.2. The Null Bitmap Is Only Part of the Overhead

A tuple containing NULLs still requires a header and line pointer. Bitmap size depends on attribute count and alignment. You cannot calculate tuple size solely from the octet_length of text columns.

## 15. Alignment and Padding

PostgreSQL stores attributes in the column order defined in the tuple descriptor, applying alignment requirements by data type.

Common alignment classes:

| Alignment code | General requirement |
|---|---|
| c | 1 byte |
| s | 2 bytes |
| i | 4 bytes |
| d | 8 bytes |

For example, fixed-length types int2, int4, and int8 have corresponding alignment requirements. Certain varlena and other types follow specific rules.

### 15.1. Padding Can Make a Tuple Larger Than Total Payload

Padding bytes may appear between two attributes so the next field starts on an appropriate boundary.

### 15.2. Column Order Can Affect Physical Size

Certain column orderings can produce different padding, especially with many alternating fixed-width columns of large and small alignments. This is a physical-level optimization that should be measured; do not alter schemas based purely on folklore rules.

### 15.3. Do Not Hard-Code Column Offsets

Tuple data does not store a fixed offset per column like an application-defined C struct. PostgreSQL uses the tuple descriptor, null bitmap, alignment, and type metadata to decode attributes.

## 16. TID, Heap Tuple, and Index

A B-tree index typically stores the index key together with a TID pointing to the heap tuple:

```text
B-tree index entry
+----------------------------+
| key = customer_id 101      |
| TID = (block 8, offset 3)  |
+----------------------------+
             |
             v
Heap block 8
+----------------------------+
| line pointer #3            |
|       |                    |
|       v                    |
| heap tuple version         |
+----------------------------+
```

### 16.1. Indexes Do Not Necessarily Store the Full Row

An index stores keys and the information needed to locate the tuple. When columns missing from the index are required or visibility must be verified, the executor may visit the heap.

### 16.2. Index Scans May Require Heap Fetches

The index entry points to a TID; PostgreSQL must verify that the tuple version matches the snapshot and retrieve any required attributes.

### 16.3. Index-Only Scan and Visibility Map

An index-only scan can avoid heap visits when the index contains all needed columns and the Visibility Map indicates the page is all-visible. If the page is not all-visible, PostgreSQL may still have to check heap visibility.

### 16.4. Index-Only Does Not Mean "Never Reads Heap"

If the VM bit is not set or gets cleared by an UPDATE, heap fetches can occur. Inspect EXPLAIN (ANALYZE, BUFFERS) to observe Heap Fetches.

## 17. HOT Update (Heap-Only Tuple)

HOT is an optimization for UPDATE when conditions are favorable:

- Indexed columns do not change according to the relevant rules.
- Sufficient free space exists on the same heap page for the new tuple version.
- Other implementation conditions are satisfied.

When a HOT update occurs, PostgreSQL can create the new tuple version on the same page without adding new entries to every index, and line pointers/chains support traversing from the old version to the new version.

### 17.1. Why Is HOT Beneficial?

Updating a non-indexed column can avoid many index writes, reducing WAL and index bloat in suitable cases.

### 17.2. When Does HOT Not Occur?

- An indexed column changes.
- A column referenced by an expression/partial index changes.
- Not enough space remains on the same page.
- Other HOT conditions are not met.

### 17.3. HOT Is Not an UPDATE Type Called Directly by Applications

There is no UPDATE HOT syntax. PostgreSQL decides whether the optimization applies based on page/index conditions.

### 17.4. Observing HOT Statistics

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY relname;
```

These statistics are cumulative/estimates managed by the stats system; understand resets and update timing. n_tup_hot_upd shows the recorded number of HOT updates.

## 18. Fillfactor: Reserving Space for UPDATEs

A heap table's fillfactor controls the page fill target when writing/loading data. The default is typically 100, meaning PostgreSQL tries to pack pages nearly full per storage rules.

Example:

```sql
CREATE TABLE hot_demo (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    stable_key text NOT NULL,
    counter integer NOT NULL DEFAULT 0,
    description text
) WITH (fillfactor = 80);
```

### 18.1. Why Reserve 20%?

The free space creates an opportunity for a new tuple version after an UPDATE to fit on the same page, increasing the likelihood of HOT updates.

### 18.2. Low Fillfactor Has Trade-Offs

- The table occupies more pages.
- Sequential scans may read more blocks.
- Cache footprint increases.
- INSERTs may use storage less efficiently.
- HOT/update performance may improve for suitable workloads.

### 18.3. Fillfactor Is Not a Tuple Size Limit

A large tuple can still fail to fit on a page; fillfactor does not guarantee HOT updates.

### 18.4. Changing Fillfactor Does Not Rewrite the Whole Table Automatically

ALTER TABLE ... SET (fillfactor = 80) changes the storage parameter for future applicable operations; it does not automatically compact/rewrite all existing pages to 80%.

## 19. Free Space Map (FSM)

The FSM is an auxiliary fork recording estimated free space on heap pages (and related structures). When PostgreSQL needs to place a new tuple, the FSM helps find a page likely to have enough room.

### 19.1. FSM Is Not a Real-Time Exact Byte Map

A page can change after the FSM records an estimate; this is metadata to assist page selection, not a guarantee of exact free bytes at every instant.

### 19.2. FSM Supports Space Reuse

After DELETE/UPDATE and VACUUM, space can be marked usable for new tuples instead of immediately shrinking the file.

### 19.3. Checking FSM Size

```sql
SELECT
    pg_relation_size('public.some_table'::regclass, 'main') AS main_bytes,
    pg_relation_size('public.some_table'::regclass, 'fsm') AS fsm_bytes;
```

If the fork has not been created or has no data, its size may be 0.

### 19.4. pg_freespacemap

The pg_freespacemap extension lets you inspect per-block free-space estimates. Installing the extension and execution privileges depend on the environment.

## 20. Visibility Map (VM)

The VM records the visibility status of heap pages. Two key states:

- **All-visible:** every tuple on the page is visible to all transactions under applicable visibility conditions.
- **All-frozen:** tuples on the page have been frozen under the transaction ID mechanism.

### 20.1. Why Is the VM Important for Index-Only Scans?

If a page is all-visible, PostgreSQL can skip heap visibility checks for index entries pointing to that page under appropriate conditions. This helps index-only scans reduce heap I/O.

### 20.2. UPDATE Can Clear All-Visible

When a page is modified, the visibility bit can be cleared because the page is no longer guaranteed to be all-visible.

### 20.3. VM Is Not a Data Cache

The VM does not store row values; it stores page-level visibility/frozen status bits.

### 20.4. Checking VM Size

```sql
SELECT
    pg_relation_size('public.some_table'::regclass, 'vm') AS vm_bytes;
```

## 21. VACUUM and Heap Pages

VACUUM helps PostgreSQL manage tuple versions that are no longer needed.

At a high level, VACUUM can:

- Identify dead tuples no longer needed by any valid snapshot.
- Reclaim/mark slots and tuple space for reuse.
- Update the Free Space Map.
- Update the Visibility Map.
- Perform index cleanup where applicable.
- Support freezing old transaction IDs.

### 21.1. Regular VACUUM Does Not Rewrite the Whole Table

```sql
VACUUM (ANALYZE) public.some_table;
```

Regular VACUUM primarily makes space within the relation reusable and updates metadata/statistics. It usually **does not immediately shrink the heap file accordingly**.

### 21.2. VACUUM FULL Differs from VACUUM

```sql
VACUUM FULL public.some_table;
```

VACUUM FULL rewrites the relation to return space to the filesystem, but requires a strong lock (typically ACCESS EXCLUSIVE), creates a rewritten copy, and incurs I/O and temporary disk space costs. Do not run it casually on large production tables.

### 21.3. Pruning Can Happen During Normal Operations

PostgreSQL can prune unneeded tuple versions on a page at opportune times, such as when the page is accessed. Not all cleanup waits for a manual VACUUM.

### 21.4. Long-Running Transactions Delay Reclamation

A transaction holding an old snapshot can keep tuple versions necessary. Replication slots or other horizons can also delay cleanup. Monitor transaction age and replication state when dead tuples grow abnormally.

## 22. Autovacuum

Autovacuum is the background mechanism that maintains vacuum/analyze based on thresholds and statistics.

Parameters that can influence it:

- autovacuum.
- autovacuum_vacuum_threshold.
- autovacuum_vacuum_scale_factor.
- autovacuum_analyze_threshold.
- autovacuum_analyze_scale_factor.
- Per-table storage parameters.
- Cost delay/limit and worker capacity.

### 22.1. Why Do Small and Large Tables Need Different Policies?

A fixed scale factor can produce a very large dead-tuple threshold on a multi-million-row table or trigger too frequently on a small table. Per-table adjustments can be made after measuring the workload.

### 22.2. Autovacuum Is Not a Magic Switch That Eliminates Bloat

It can fall behind due to:

- Long-running transactions/snapshots.
- Replication slots holding back xmin.
- I/O/CPU load.
- Worker capacity.
- Table-specific thresholds.
- Tables with high update/delete churn.

### 22.3. Monitoring Statistics

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;
```

n_live_tup and n_dead_tup are estimates, not exact physical tuple counts.

## 23. Freezing and Transaction ID Wraparound

PostgreSQL uses transaction IDs from a finite space. If old tuples are not properly frozen/maintained, wraparound issues can threaten visibility correctness.

VACUUM plays a critical role in:

- Advancing sufficiently old tuples to an appropriate frozen state.
- Maintaining visibility across transaction ID lifecycles.
- Updating all-frozen bits in the VM when conditions are met.

### 23.1. Frozen Does Not Mean Row Immutability

Freezing relates to how PostgreSQL interprets old transaction IDs for visibility. It does not forbid updating or deleting the row and is not a business flag.

### 23.2. Do Not Disable Autovacuum Arbitrarily

Disabling autovacuum on tables/databases without an alternative vacuum/freeze process can cause dead tuple accumulation, stale statistics, and wraparound risk.

### 23.3. Monitor Operational Warnings

Track database/table frozen XID age, autovacuum progress, and wraparound warnings according to your PostgreSQL version. Do not wait until the server refuses writes to act.

## 24. Heap Page, Index, and MVCC Visibility

An index scan cannot simply match a key and blindly return the tuple. It must respect the snapshot:

```text
B-tree lookup
    |
    v
Index entry (key, TID)
    |
    v
Heap page / line pointer
    |
    v
Tuple version
    |
    v
MVCC visibility check
    |
    +-- visible -> return row
    |
    +-- not visible -> skip / evaluate appropriate version
```

### 24.1. Why Can an Index Contain Entries Pointing to Dead Tuples?

UPDATE/DELETE and VACUUM have separate lifecycles. Old index entries can persist until index cleanup; visibility checks still ensure the wrong version is never returned to a query.

### 24.2. HOT and Index Entries

A HOT update can avoid creating new index entries for the new tuple version under appropriate conditions. The old index entry leads to the chain on the same page, allowing the appropriate version to be found.

### 24.3. Index-Only Scan

If the index contains all required columns, the executor can use the index to return values. However, visibility checks may still require a heap visit unless the VM marks the page all-visible.

## 25. TOAST, Heap, and Size Functions

Useful functions:

| Function | Purpose |
|---|---|
| pg_relation_size(regclass) | Size of the default main fork of the relation |
| pg_relation_size(regclass, fork) | Size of the specified fork |
| pg_table_size(regclass) | Size of the table and associated components such as TOAST/forks, excluding indexes unlike pg_total_relation_size |
| pg_indexes_size(regclass) | Size of the table's indexes |
| pg_total_relation_size(regclass) | Total size of the table + indexes and related TOAST components |
| pg_relation_filepath(regclass) | Physical path of the relation per current storage mapping |
| pg_column_size(value) | Size of the stored representation of a value in context |
| pg_size_pretty(bytes) | Human-readable size formatting |

Example:

```sql
SELECT
    pg_size_pretty(pg_relation_size('orm420.heap_demo')) AS main_fork,
    pg_size_pretty(pg_table_size('orm420.heap_demo')) AS table_with_toast,
    pg_size_pretty(pg_indexes_size('orm420.heap_demo')) AS indexes,
    pg_size_pretty(pg_total_relation_size('orm420.heap_demo')) AS total;
```

### 25.1. Do Not Double-Count Components

pg_total_relation_size already includes the parts measured by pg_table_size plus indexes. Never add table_size + total_relation_size and call that the total.

### 25.2. Logical and Physical Sizes Differ

octet_length(text_value) measures the byte length of the extracted value per data type semantics. pg_column_size measures the stored representation in PostgreSQL context and can be affected by compression/TOAST. They are not always equal.

### 25.3. pg_relation_filepath

The file path can change after relation rewrites, tablespace moves, or storage management operations. Never store file paths as durable table identifiers in applications.

## 26. Lab: Creating a Heap Table with Multiple Data Types

Create the lab schema:

```sql
CREATE SCHEMA IF NOT EXISTS orm420;

CREATE TABLE orm420.heap_demo (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code integer NOT NULL,
    small_value smallint,
    label text,
    amount numeric(12, 2),
    active boolean NOT NULL DEFAULT true,
    payload text,
    created_at timestamptz NOT NULL DEFAULT now()
) WITH (fillfactor = 85);
```

Insert sample rows:

```sql
INSERT INTO orm420.heap_demo(
    code, small_value, label, amount, active, payload
)
SELECT
    g,
    CASE WHEN g % 3 = 0 THEN NULL ELSE (g % 100)::smallint END,
    CASE WHEN g % 4 = 0 THEN NULL ELSE 'item-' || g::text END,
    (g * 10.25)::numeric(12,2),
    (g % 2 = 0),
    repeat('training-data-', 20)
FROM generate_series(1, 300) AS g;
```

Inspect:

```sql
SELECT
    id,
    code,
    small_value,
    label,
    amount,
    active,
    octet_length(payload) AS payload_bytes,
    ctid,
    xmin,
    xmax
FROM orm420.heap_demo
ORDER BY id
LIMIT 10;
```

### 26.1. Observing Relation Sizes

```sql
SELECT
    pg_relation_size('orm420.heap_demo'::regclass) AS main_bytes,
    pg_table_size('orm420.heap_demo'::regclass) AS table_bytes,
    pg_indexes_size('orm420.heap_demo'::regclass) AS index_bytes,
    pg_total_relation_size('orm420.heap_demo'::regclass) AS total_bytes,
    pg_relation_filepath('orm420.heap_demo'::regclass) AS relation_path;
```

### 26.2. Estimating Page Count

```sql
SELECT
    pg_relation_size('orm420.heap_demo'::regclass)
        / current_setting('block_size')::integer AS main_page_count;
```

The main fork page count excludes the TOAST relation and indexes. Do not compare this number against total bytes and draw wrong conclusions.

## 27. Lab: Observing ctid Before and After UPDATE

Fetch a tuple:

```sql
SELECT id, ctid, xmin, xmax, code
FROM orm420.heap_demo
WHERE id = 10;
```

Update it:

```sql
UPDATE orm420.heap_demo
SET label = 'updated-label'
WHERE id = 10;
```

Read it again:

```sql
SELECT id, ctid, xmin, xmax, code, label
FROM orm420.heap_demo
WHERE id = 10;
```

ctid may change due to the new tuple version. xmin typically reflects the transaction that created the new version. Exact observed values depend on page free space, HOT eligibility, and transaction context.

### 27.1. Viewing Multiple Versions at the Raw Page Level

A normal SELECT only returns the version visible to your snapshot. To view physical tuples and line pointers, you can use the pageinspect extension on the lab page (next section).

### 27.2. Do Not Use ctid as an API Identifier

If an application stores ctid and uses it in a later request, UPDATE/VACUUM FULL/CLUSTER can shift the physical location. Use a stable primary key instead.

## 28. Lab: DELETE and VACUUM

Delete a set of sample rows:

```sql
DELETE FROM orm420.heap_demo
WHERE id BETWEEN 20 AND 60;
```

Check statistics:

```sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum
FROM pg_stat_user_tables
WHERE schemaname = 'orm420'
  AND relname = 'heap_demo';
```

Statistics may not update instantaneously and are estimates.

Run vacuum in the lab:

```sql
VACUUM (VERBOSE, ANALYZE) orm420.heap_demo;
```

### 28.1. Why Might the File Not Shrink?

Regular VACUUM makes space reusable within the relation. It does not promise to compact the entire relation and return all pages to the filesystem.

### 28.2. Observing After Vacuum

Re-read n_dead_tup, relation sizes, and page inspection output. Results depend on lingering snapshots, pruning, autovacuum, page layout, and workload.

### 28.3. Do Not Run VACUUM FULL Just for Prettier Byte Counts

VACUUM FULL incurs heavy cost and strong locks. Only consider it when there is a clear goal to reclaim storage and an operational plan.

## 29. Lab: Viewing TOAST with Large Payloads

Create the table:

```sql
CREATE TABLE orm420.toast_demo (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    body text
);
```

Insert large sample data:

```sql
INSERT INTO orm420.toast_demo(title, body)
VALUES (
    'Large training document',
    repeat('TOAST-training-', 20000)
);
```

Inspect logical and representation sizes:

```sql
SELECT
    id,
    octet_length(body) AS logical_bytes,
    pg_column_size(body) AS stored_datum_bytes,
    pg_table_size('orm420.toast_demo'::regclass) AS table_bytes,
    pg_total_relation_size('orm420.toast_demo'::regclass) AS total_bytes
FROM orm420.toast_demo;
```

### 29.1. Why Might body Not Fit Entirely in the Main Tuple?

A large value can be compressed or stored out-of-line in the TOAST relation. The main tuple holds the necessary pointer/metadata.

### 29.2. Checking the TOAST Relation

You can find the TOAST relation via the catalog:

```sql
SELECT
    c.relname AS table_name,
    c.reltoastrelid::regclass AS toast_relation
FROM pg_class AS c
WHERE c.oid = 'orm420.toast_demo'::regclass;
```

If reltoastrelid is 0 or there is no TOAST relation, the table does not currently need a TOAST relation.

### 29.3. TOAST Is Not a Text Search Engine

TOAST chunks/stores large values; it does not provide full-text search. If you need content search, design tsvector, GIN, or a dedicated search service based on workload.

## 30. pageinspect: Reading Pages at a Low Level

pageinspect is a PostgreSQL extension providing functions to inspect pages. It is useful for learning, investigation, and understanding layout, but is not a normal application API.

Install the extension if supported by the server and permitted for your role:

```sql
CREATE EXTENSION IF NOT EXISTS pageinspect;
```

Read block 0 header:

```sql
SELECT *
FROM page_header(
    get_raw_page('orm420.heap_demo', 'main', 0)
);
```

### 30.1. Reading Line Pointers and Tuple Metadata

```sql
SELECT
    lp,
    lp_off,
    lp_flags,
    lp_len,
    t_xmin,
    t_xmax,
    t_ctid,
    t_hoff,
    t_infomask,
    t_infomask2
FROM heap_page_items(
    get_raw_page('orm420.heap_demo', 'main', 0)
)
ORDER BY lp;
```

### 30.2. Reading Tuple Attributes

Some versions of pageinspect support:

```sql
SELECT *
FROM heap_page_item_attrs(
    get_raw_page('orm420.heap_demo', 'main', 0),
    'orm420.heap_demo'::regclass,
    true
);
```

This function returns attribute representations as a bytea array and includes an option to detoast. Check the pageinspect documentation for your exact server version regarding output structure and support scope.

### 30.3. Block 0 Must Exist

get_raw_page requires a valid block. If the relation is empty or has no block 0, the call will error. In the lab we inserted 300 rows, so there should be pages to inspect.

### 30.4. Privileges and Safety

Raw page inspection reads physical bytes, including tuple versions invisible to ordinary SELECTs. Grant access only to authorized operators/investigators, never broadly to application roles.

### 30.5. Never Modify Raw Pages

pageinspect is for observation. Never manually edit page bytes to "fix data"; modifying raw pages outside PostgreSQL mechanisms can corrupt structures, indexes, WAL consistency, and ruin the database.

## 31. pg_freespacemap: Viewing Free-Space Estimates

If the extension is available:

```sql
CREATE EXTENSION IF NOT EXISTS pg_freespacemap;
```

Inspect some pages:

```sql
SELECT
    blkno,
    avail
FROM pg_freespace('orm420.heap_demo'::regclass)
ORDER BY blkno
LIMIT 20;
```

avail is the free-byte estimate recorded by the FSM. This is not an exact forensic byte measurement at the instant of the SELECT.

### 31.1. FSM Does Not Equal Free Space in the Page Header

The FSM is an auxiliary structure maintaining estimates. Page header pd_lower/pd_upper reflect page layout state; fragmentation and pruning can complicate free space interpretation.

## 32. pgstattuple: Estimating Live/Dead/Free Space

The pgstattuple extension can provide statistics on live tuples, dead tuples, and free space.

```sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;

SELECT *
FROM pgstattuple('orm420.heap_demo');
```

This function may scan many pages and incur I/O cost; do not run it frequently on large production tables without evaluation.

### 32.1. pgstattuple_approx

In supported versions, pgstattuple_approx provides a lighter-weight estimate using existing metadata and sampling a subset of pages.

```sql
SELECT *
FROM pgstattuple_approx('orm420.heap_demo');
```

Verify column names, output details, and availability against your version.

### 32.2. There Is No Single Bloat Number

A high free_percent statistic does not automatically prove VACUUM FULL is needed. Consider whether the free space will be reused, how future INSERT/UPDATE workloads behave, whether indexes are bloated, and the cost of rewriting.

## 33. HOT Update and Fillfactor in the Lab

Create a test table:

```sql
CREATE TABLE orm420.hot_lab (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    indexed_code integer NOT NULL,
    counter integer NOT NULL DEFAULT 0,
    description text
) WITH (fillfactor = 70);

CREATE INDEX idx_orm420_hot_code
ON orm420.hot_lab(indexed_code);

INSERT INTO orm420.hot_lab(indexed_code, description)
SELECT g, repeat('x', 100)
FROM generate_series(1, 1000) AS g;
```

Update a non-indexed column:

```sql
UPDATE orm420.hot_lab
SET counter = counter + 1
WHERE id BETWEEN 1 AND 500;
```

View statistics:

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'orm420'
  AND relname = 'hot_lab';
```

### 33.1. Why Can HOT Occur?

indexed_code did not change, and fillfactor reserved space. If the new tuple fits on the same page and other conditions are met, a HOT update can occur.

### 33.2. Trying to Change an Indexed Column

```sql
UPDATE orm420.hot_lab
SET indexed_code = indexed_code + 100000
WHERE id BETWEEN 1 AND 500;
```

Because an indexed column changed, this update is generally ineligible for HOT under the relevant index rules.

### 33.3. Statistics Do Not Necessarily Update Immediately

The statistics collector / cumulative stats system has its own update and reset behavior. When comparing over time, you may need to wait/re-read and control the lab workload.

## 34. Heap Page Allocation Differs from B-tree Page Split

Heap pages have no key ordering like B-trees. When a page runs out of space, PostgreSQL can pick another page via the FSM or extend the relation.

A B-tree index is hierarchical and splits pages when keys are added. Do not use the term "B-tree page split" to describe every block growth in a heap relation.

### 34.1. Heap Does Not Sort by Index

```sql
CREATE INDEX idx_products_code
ON orm420.heap_demo(code);
```

Even after creating an index, the heap table is still not physically ordered by code.

### 34.2. CLUSTER Is an Ordered Rewrite Operation

```sql
CLUSTER orm420.heap_demo
USING idx_products_code;
```

CLUSTER rewrites the table in index order at execution time and requires a strong lock. Subsequent INSERTs/UPDATEs can cause physical order to drift away from the clustered state. It provides no ORDER BY guarantee for SQL queries.

## 35. Relation Forks: main, FSM, VM, and init

A relation can have the following forks:

| Fork | Role |
|---|---|
| main | Main content of the table/index |
| fsm | Free Space Map |
| vm | Visibility Map |
| init | Initial fork for unlogged relations, used to restore initial empty state after a crash |

For a heap table, the main fork holds data pages. FSM/VM hold metadata for storage management and visibility.

### 35.1. Unlogged Tables and the init Fork

Unlogged tables are not WAL-logged in the full manner of logged tables and can be truncated/reset after a crash; the init fork supports restoring the initial empty state per PostgreSQL mechanisms.

Do not use unlogged tables for data requiring durability like a standard logged table.

### 35.2. Temporary Tables

Temporary tables have session/transaction scope as declared and reside in temporary schemas/backend-specific storage. Do not assume their physical files behave identically to a permanent table under base/database_oid.

### 35.3. Partitioned Tables

A partitioned parent is usually a coordinating relation, not a single heap holding all rows. Child partitions are separate physical relations with their own pages/forks. Check tableoid and each partition when measuring storage.

## 36. Segments and Physical File Paths

A large relation can be split into multiple segment files. The common default segment size is around **1 GiB**, though this is a build/implementation detail that can be configured differently.

You can check the current path:

```sql
SELECT
    'orm420.heap_demo'::regclass AS relation,
    pg_relation_filenode('orm420.heap_demo'::regclass) AS relfilenode,
    pg_relation_filepath('orm420.heap_demo'::regclass) AS file_path;
```

### 36.1. Why Can relfilenode Change?

Relation-rewriting operations such as VACUUM FULL, CLUSTER, or certain ALTER TABLE commands can create new relation files and change relfilenode.

### 36.2. Do Not Hard-Code Paths in Applications

Paths depend on database OID, tablespace, relfilenode, fork, and segment. Use SQL/catalog APIs for investigation; do not store file paths as durable identifiers.

### 36.3. Tablespaces

A relation can live in a tablespace other than the default. Therefore, not every relation is found under a single base directory.

## 37. Tuple Width, Row Count, and Page Density

A 100-column table does not necessarily take the same space as a 10-column table; column count and data types alone are not enough to deduce exact size.

Factors include:

- Tuple header.
- Null bitmap.
- Attribute alignment/padding.
- Fixed-length and variable-length values.
- TOAST compression/out-of-line storage.
- Line pointer overhead.
- Fillfactor.
- Dead tuple versions.
- Free space and fragmentation.

### 37.1. Simple Estimation

A conceptual model:

```text
page footprint
  ~= page header
   + line pointer array
   + tuple headers
   + null bitmaps
   + aligned attribute data
   + free space
   + special area (if used by access method)
```

Do not use this calculation as a replacement for pg_relation_size or page inspection.

### 37.2. Comparing Two Data Types

A bigint has a fixed 8-byte value width, yet the tuple also includes header/alignment/line pointer overhead. A short text has a varlena header and may use a short representation. A long text may be TOASTed.

### 37.3. Do Not Split Tables Just Because "Many Columns Must Be Slow"

Vertical partitioning can narrow heap width for common queries, but introduces joins, transaction consistency, and complexity. Base the decision on access patterns and actual measurements.

## 38. Updating a Small Column in a Large Tuple

If a table holds large JSON/text and a small column is updated frequently:

- PostgreSQL creates a new tuple version per MVCC.
- Large attributes may stay TOASTed/compressed or pointers may be preserved depending on semantics.
- HOT eligibility depends on index changes and free space.
- WAL and page churn may increase.
- Indexes may receive new entries if the update is not HOT.

Therefore, table designs combining large fields with frequently updated fields should be evaluated against workload.

### 38.1. Separating Metadata and Payload?

Some systems move large payloads to a separate table so metadata updates cause less churn in the main table. However, splitting introduces join and consistency overhead. There is no universal rule to always separate blobs.

### 38.2. JSONB Can Have Its Own TOAST and Index

Large JSONB values can be TOASTed. A GIN index on JSONB also has its own index storage structure, which can significantly expand total footprint. Measure pg_table_size, pg_indexes_size, and pg_total_relation_size.

## 39. VACUUM, REINDEX, and CLUSTER: Do Not Confuse Their Purposes

| Command | Primary Effect | Impact / Limitations |
|---|---|---|
| VACUUM | Reclaims dead tuples for reuse, updates FSM/VM, freezes | Usually does not rewrite the entire table |
| VACUUM FULL | Rewrites/compacts table, reclaims file space | Strong lock, high I/O and temporary space |
| ANALYZE | Updates planner statistics | Does not compact the table |
| REINDEX | Rebuilds indexes | Does not automatically compact the heap table |
| CLUSTER | Rewrites table in index order | Strong lock; physical order can drift with subsequent DML |

### 39.1. REINDEX Does Not Fix Heap Bloat

If the heap has many dead tuples/free space, REINDEX only rebuilds the index. Identify the exact bloated component first.

### 39.2. ANALYZE Does Not Clean Up Tuples

ANALYZE collects data distribution statistics for the planner; it is not vacuuming.

### 39.3. Do Not Run Every Maintenance Command Reflexively

Each command carries different lock, I/O, WAL, and availability impacts. Verify your objective and system state beforehand.

## 40. WAL, Page LSN, and Durability

PostgreSQL uses Write-Ahead Logging: changes must be recorded in WAL in proper order before the corresponding data pages are flushed durably.

Simplified diagram:

```text
SQL UPDATE
   |
   v
Heap tuple/page change in buffer
   |
   +--> WAL record created
   |        |
   |        v
   |     WAL flushed per commit/durability settings
   |
   v
Data page can be written to storage later
```

### 40.1. pd_lsn

The page LSN helps recovery determine which WAL records are already reflected on the page. It is not a business field and must not be used to order business orders.

### 40.2. Full-Page Writes

Under appropriate conditions, PostgreSQL writes full-page images to WAL to support page recovery after partial page writes. This is part of WAL/recovery design, not a substitute for full backups.

### 40.3. Page Checksums

Checksums help detect certain page corruption when enabled. They do not encrypt data and do not replace backups, replication, or restore testing.

### 40.4. fsync and Durability

Durability settings such as fsync, synchronous_commit, and storage guarantees govern when commits are durable. Never change them solely to lower latency without understanding data-loss risks.

## 41. Heap Pages and Index-Only Scan: EXPLAIN Lab

Create an index on the queried column:

```sql
CREATE INDEX idx_orm420_heap_demo_code
ON orm420.heap_demo(code);
```

Run:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT code
FROM orm420.heap_demo
WHERE code BETWEEN 100 AND 150;
```

### 41.1. Why Might You See an Index Scan?

The planner can use the index to find TIDs and then fetch heap tuples.

### 41.2. Why Might You See an Index Only Scan?

If the index contains all required columns and pages are all-visible per the VM, the executor can avoid heap fetches for many rows.

### 41.3. Heap Fetches

If the plan shows Index Only Scan, check Heap Fetches. A large number indicates the executor still had to visit the heap to check visibility in some cases.

### 41.4. ANALYZE and VACUUM Can Affect Plans

Statistics and the visibility map change with workload/maintenance. Do not force the planner with hints unavailable in core PostgreSQL; inspect schema/indexes/stats first.

## 42. Observing TOAST and Overall Relation Size

Summary query:

```sql
SELECT
    c.oid::regclass AS relation,
    c.reltoastrelid::regclass AS toast_relation,
    pg_size_pretty(pg_relation_size(c.oid, 'main')) AS main_fork,
    pg_size_pretty(pg_relation_size(c.oid, 'fsm')) AS fsm_fork,
    pg_size_pretty(pg_relation_size(c.oid, 'vm')) AS vm_fork,
    pg_size_pretty(pg_table_size(c.oid)) AS table_size,
    pg_size_pretty(pg_indexes_size(c.oid)) AS indexes_size,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class AS c
WHERE c.oid = 'orm420.toast_demo'::regclass;
```

The result reveals components across the different size functions. Auxiliary forks may not exist yet or may have size 0.

### 42.1. TOAST Index

A TOAST relation has its own index to locate chunks by value/chunk sequence. pg_total_relation_size includes the related TOAST storage per function semantics.

### 42.2. Index Size Is Not Tuple Payload Size

An index can consume more space than expected due to key width, tuple overhead, page fill, bloat, and entry count. Measure it directly instead of summing column sizes manually.

## 43. Maintenance and Storage Investigation in Production

When a table grows unusually large, investigate in sequence:

1. Read pg_relation_size, pg_table_size, pg_indexes_size, and pg_total_relation_size.
2. Determine whether the table has a TOAST relation or partitions.
3. Inspect row estimates, dead tuples, and vacuum timestamps.
4. Check transaction age, replication slots, and xmin horizons if vacuum cannot reclaim space.
5. Use pgstattuple/pgstattuple_approx if privileges and cost permit.
6. Check indexes separately.
7. Review update/delete churn, HOT ratio, and fillfactor.
8. Inspect actual query plans.
9. Plan maintenance with lock/I/O/storage budgets.
10. Monitor after execution.

### 43.1. Do Not Run pageinspect Indiscriminately on Every Table

Raw page inspection is a specialized tool. For size questions, start with pg_relation_size/catalogs. For tuple/page layout questions, use pageinspect in lab environments or authorized investigations.

### 43.2. Never Copy Raw Pages to Uncontrolled Locations

Raw pages can contain sensitive data, old tuple versions, or bytes not exposed by SELECT. Treat the output as sensitive production data.

### 43.3. Long Transactions Are a Signal to Investigate

A long transaction can pin old required tuple versions, preventing VACUUM from reclaiming them. Check pg_stat_activity, replication slots, and transaction horizons before blindly increasing autovacuum workers.

## 44. Common Misconceptions

### Misconception 1 — The Heap Automatically Sorts by Primary Key

No. A heap does not guarantee order; use ORDER BY.

### Misconception 2 — One Row Always Maps to One Physical Tuple

No. MVCC allows multiple tuple versions for one logical row across INSERT/UPDATE/DELETE.

### Misconception 3 — UPDATE Overwrites the Tuple In Place

Do not assume that. UPDATE generally creates a new tuple version; HOT is a conditional optimization.

### Misconception 4 — DELETE Immediately Frees File Bytes

No. The tuple becomes dead and waits for pruning/VACUUM.

### Misconception 5 — VACUUM Always Shrinks the File

No. Regular VACUUM makes free space reusable; VACUUM FULL rewrites to reclaim space with heavy locks/cost.

### Misconception 6 — ctid Is a Good Primary Key

No. ctid can change after UPDATE/rewrite and only has physical meaning.

### Misconception 7 — xmin Is created_at

No. xmin is a transaction ID, not a timestamp.

### Misconception 8 — Non-Zero xmax Means the Tuple Is Definitely Deleted

No. xmax also represents locking/MultiXact states depending on implementation.

### Misconception 9 — A Page Is 8KB So Any Tuple Can Be 8KB

No. There are also page headers, line pointers, free space, alignment, and tuple/TOAST storage limits.

### Misconception 10 — TOAST Is Only Compression

No. TOAST can compress and/or store out-of-line depending on the storage strategy.

### Misconception 11 — TOAST and Large Objects Are the Same

No. They are two different mechanisms.

### Misconception 12 — FSM Reports Exact Free Bytes

No. FSM is approximate metadata assisting page selection.

### Misconception 13 — VM Stores Row Values

No. VM stores page-level visibility/frozen status bits.

### Misconception 14 — Index-Only Scan Never Reads the Heap

No. If the VM is not all-visible, heap fetches may still be needed.

### Misconception 15 — HOT Happens on Any UPDATE Not Changing the Primary Key

No. All indexed columns/expressions/predicates, free space, and other conditions must be satisfied.

### Misconception 16 — Lower Fillfactor Is Always Faster

No. It increases page count/storage/cache footprint; measure against your workload.

### Misconception 17 — Creating an Index Sorts the Heap

No. An index is a separate structure pointing to heap TIDs.

### Misconception 18 — CLUSTER Preserves Order Forever

No. Subsequent DML can alter physical order.

### Misconception 19 — pg_relation_size Is the Total of Everything

No. By default it measures the relation's main fork; use table/index/total size functions as appropriate.

### Misconception 20 — pg_column_size Equals octet_length

Not always; TOAST, compression, and representation affect it.

### Misconception 21 — A Partitioned Parent Table Holds All Heap Pages

Not necessarily. Child partitions are typically separate physical relations.

### Misconception 22 — Page Checksums Encrypt Pages

No. Checksums help detect corruption, not provide confidentiality.

### Misconception 23 — Enabling Autovacuum Means Zero Dead Tuples

No. Snapshot horizons, replication slots, thresholds, and workload can delay cleanup.

### Misconception 24 — REINDEX Cleans Up Heap Bloat

No. REINDEX rebuilds indexes; it does not compact the heap table.

### Misconception 25 — ANALYZE Reclaims Dead Tuples

No. ANALYZE updates planner statistics.

### Misconception 26 — You Can Store ctid to Reference a Row Across Requests

No. Use a stable primary key or business key.

### Misconception 27 — Raw Page Output Is Not Sensitive Because It Is Not a Normal SELECT

False. It can contain old data and sensitive bytes; protect output like database data.

## 45. Exercises with Answers

### Exercise 1. What is a heap?

**Answer:** A relation structure that stores tuples across pages without guaranteeing row order by primary key or INSERT order.

### Exercise 2. What is the common PostgreSQL block size?

**Answer:** 8 KiB (8192 bytes) in standard builds; check with SHOW block_size.

### Exercise 3. Can block size be changed for a single table via ALTER TABLE?

**Answer:** No. It is a build/server property, not a per-table setting.

### Exercise 4. What are the main regions of a page?

**Answer:** Page header, line pointer array, free space, and tuple area; special space may exist for access methods that use it, whereas regular heap pages do not need it.

### Exercise 5. How many bytes does a line pointer usually take?

**Answer:** 4 bytes in the common layout.

### Exercise 6. What does a TID consist of?

**Answer:** A block number and the offset number of the line pointer within that block.

### Exercise 7. Is the TID offset the byte offset of the tuple?

**Answer:** No. It is the line pointer slot number.

### Exercise 8. Why do pages need line pointers?

**Answer:** They allow referencing a tuple by slot while tuple bytes can be moved/compacted inside the page.

### Exercise 9. What do pd_lower and pd_upper describe?

**Answer:** The boundaries of the line pointer array and the tuple/free-space region in the page layout.

### Exercise 10. What does pd_lsn relate to?

**Answer:** The most recent related WAL LSN applied to the page.

### Exercise 11. Do page checksums encrypt data?

**Answer:** No. They help detect certain corruptions.

### Exercise 12. What is a tuple version?

**Answer:** A physical version of a row in MVCC, containing transaction metadata and attribute data.

### Exercise 13. What does xmin usually represent?

**Answer:** The transaction ID that created the tuple version.

### Exercise 14. Is xmax always the transaction that deleted the row?

**Answer:** No. It can also represent locking/MultiXact metadata depending on tuple state.

### Exercise 15. What format does ctid have?

**Answer:** (block_number, offset_number).

### Exercise 16. Is ctid suitable as a primary key?

**Answer:** No. It can change after UPDATE/rewrite.

### Exercise 17. What does UPDATE typically do with the old tuple?

**Answer:** Creates a new tuple version and marks the old version per MVCC; cleanup occurs later when safe.

### Exercise 18. Does DELETE immediately erase physical bytes?

**Answer:** No. The tuple becomes dead and awaits pruning/VACUUM.

### Exercise 19. What is the null bitmap used for?

**Answer:** Recording the NULL status of attributes; NULL is not an empty string or ordinary zero-byte value.

### Exercise 20. Why is tuple size larger than the sum of column payloads?

**Answer:** Because of the tuple header, line pointer, null bitmap, alignment/padding, and TOAST/varlena structures.

### Exercise 21. What problem does TOAST solve?

**Answer:** Compressing and/or storing large varlena values out-of-line so main tuples/pages remain manageable.

### Exercise 22. Is TOAST the same as Large Objects?

**Answer:** No. Large Objects have their own API and mechanism.

### Exercise 23. What does the PLAIN storage strategy do?

**Answer:** Neither compresses nor stores out-of-line.

### Exercise 24. What does EXTENDED mean?

**Answer:** Can compress and store out-of-line when needed.

### Exercise 25. How do FSM and VM differ?

**Answer:** FSM tracks free-space estimates; VM tracks page-level all-visible/all-frozen status.

### Exercise 26. How does index-only scan use the VM?

**Answer:** If the heap page is all-visible, it can skip heap visibility checks and reduce heap fetches.

### Exercise 27. What important conditions are required for a HOT update?

**Answer:** Indexed columns do not change under relevant rules, sufficient free space exists on the same page, along with other implementation conditions.

### Exercise 28. What does fillfactor 70 mean?

**Answer:** A lower page fill target to reserve space for suitable workloads; it is neither a tuple size limit nor a HOT guarantee.

### Exercise 29. Does regular VACUUM usually shrink the file?

**Answer:** Usually it does not rewrite the entire table; it mainly makes space reusable and updates FSM/VM. Some trailing empty pages may be truncated when conditions allow.

### Exercise 30. How is VACUUM FULL different?

**Answer:** Rewrites/compacts the relation and can return space to the filesystem, but requires a strong lock and incurs I/O/temporary space overhead.

### Exercise 31. How do long transactions affect VACUUM?

**Answer:** They can hold old snapshots, leaving tuple versions ineligible for reclamation.

### Exercise 32. Does autovacuum always delete every dead tuple immediately?

**Answer:** No. It depends on thresholds, worker capacity, transaction horizons, replication, and workload.

### Exercise 33. Does freeze mean the row cannot be UPDATED anymore?

**Answer:** No. Freeze relates to transaction ID visibility, not business immutability.

### Exercise 34. What does pg_relation_size(table) measure by default?

**Answer:** The main fork of the relation.

### Exercise 35. What does pg_total_relation_size include?

**Answer:** Table storage, indexes, and related TOAST components per function semantics.

### Exercise 36. Is pg_column_size always equal to octet_length?

**Answer:** No. Representation, compression, and TOAST can make them differ.

### Exercise 37. Which extension is used to read raw heap pages?

**Answer:** pageinspect, with appropriate privileges and support.

### Exercise 38. What information does heap_page_items return?

**Answer:** Line pointers and tuple metadata such as xmin/xmax/ctid/infomask per extension output.

### Exercise 39. What is pgstattuple used for?

**Answer:** Live/dead tuple and free-space statistics; can be I/O-intensive because it scans the relation.

### Exercise 40. Is heap page allocation like a B-tree page split?

**Answer:** No. A heap has no key-sorted structure like a B-tree; when out of space, it picks another page or extends the relation.

### Exercise 41. Does CLUSTER guarantee future SELECT order?

**Answer:** No. It rewrites in index order at runtime; queries still need ORDER BY.

### Exercise 42. Does REINDEX compact the heap?

**Answer:** No. It rebuilds the index.

### Exercise 43. Where does a partitioned table store rows?

**Answer:** Typically in child partitions, which are separate physical relations; the parent is primarily a coordinating relation.

### Exercise 44. Is a page LSN a timestamp?

**Answer:** No. It is a Log Sequence Number in the WAL.

### Exercise 45. Should you edit bytes directly with pageinspect to fix rows?

**Answer:** No. pageinspect is an observation tool; raw page mutation can corrupt the database.

## 46. Checklist for Investigating Heap/Table Storage

| Question | What to Verify |
|---|---|
| Is this a heap table or another relation? | pg_class.relkind, partitioning |
| What is the server block size? | SHOW block_size |
| How much does the main fork occupy? | pg_relation_size |
| What are the FSM/VM sizes? | pg_relation_size(..., 'fsm'/'vm') |
| Is there a TOAST relation? | pg_class.reltoastrelid |
| How much do indexes occupy? | pg_indexes_size |
| What is the total footprint? | pg_total_relation_size |
| Current file path/relfilenode? | pg_relation_filepath, pg_relation_filenode |
| What are the dead tuple estimates? | pg_stat_user_tables |
| When was the last autovacuum? | last_autovacuum/last_autoanalyze |
| Are there long transactions? | pg_stat_activity |
| Is a replication slot holding back the horizon? | replication slot monitoring |
| What is the HOT ratio? | n_tup_hot_upd / n_tup_upd |
| Current fillfactor? | pg_class.reloptions/table options |
| Do tuples have large TOAST values? | pg_column_size, TOAST relation |
| Is page-level evidence needed? | pageinspect on the relevant page |
| Is there actual bloat? | pgstattuple/estimates and workload |
| Does index-only scan have heap fetches? | EXPLAIN (ANALYZE, BUFFERS) |
| Need VACUUM or VACUUM FULL? | Space reuse vs filesystem reclamation |
| Is there enough disk headroom for a rewrite? | Storage budget |
| Lock impact of maintenance? | Access pattern, lock plan |
| Is sensitive data in raw page output? | Privileges, output handling |

## 47. Official PostgreSQL Documentation

- [Database Physical Storage](https://www.postgresql.org/docs/current/storage.html) — files/forks/segments and overall layout.
- [Database Page Layout](https://www.postgresql.org/docs/current/storage-page-layout.html) — page header, line pointers, and tuple area.
- [Heap-Only Tuples (HOT)](https://www.postgresql.org/docs/current/storage-hot.html) — HOT updates and index maintenance.
- [TOAST](https://www.postgresql.org/docs/current/storage-toast.html) — oversized attributes, compression, and out-of-line storage.
- [MVCC Introduction](https://www.postgresql.org/docs/current/mvcc-intro.html) — multi-version concurrency control.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — VACUUM, ANALYZE, freezing, and autovacuum.
- [Visibility Map](https://www.postgresql.org/docs/current/storage-vm.html) — all-visible/all-frozen and index-only scans.
- [Free Space Map](https://www.postgresql.org/docs/current/storage-fsm.html) — free space management.
- [System Columns](https://www.postgresql.org/docs/current/ddl-system-columns.html) — ctid, xmin, xmax, tableoid.
- [pageinspect](https://www.postgresql.org/docs/current/pageinspect.html) — raw page inspection.
- [pgstattuple](https://www.postgresql.org/docs/current/pgstattuple.html) — tuple/free-space statistics.
- [pg_freespacemap](https://www.postgresql.org/docs/current/pgfreespacemap.html) — FSM inspection.
- [Database File Layout](https://www.postgresql.org/docs/current/storage-file-layout.html) — relation file mapping.
- [WAL Introduction](https://www.postgresql.org/docs/current/wal-intro.html) — Write-Ahead Logging and recovery.

Physical layout details are implementation details and may vary by version/build. When writing page-reading tools or performing forensics, consult the documentation for the exact version and do not assume all releases share identical byte layouts.

## 48. Summary

A PostgreSQL heap relation is a collection of pages containing tuple versions. A page consists of a header, line pointer array, free space, and tuple data. Tuples carry MVCC metadata and attribute values; oversized values can be TOASTed; indexes use TIDs to locate tuples.

```text
Table / Heap relation
   |
   +-- Main fork
   |     |
   |     +-- Page header
   |     +-- Line pointers
   |     +-- Free space
   |     +-- Tuple versions
   |             |
   |             +-- xmin / xmax / ctid
   |             +-- null bitmap / alignment
   |             +-- attribute data / TOAST pointers
   |
   +-- FSM -> free-space estimates
   |
   +-- VM  -> all-visible / all-frozen
   |
   +-- TOAST relation -> large values/chunks
   |
   +-- Indexes -> keys and heap TIDs
```

Key takeaways:

1. **Heaps do not guarantee row order.** Always use ORDER BY when order matters.
2. **Pages are the fundamental unit of storage.** 8 KiB is the common default; verify the server's block_size.
3. **Line pointers are tuple reference slots.** TIDs use block and offset numbers, not byte offsets.
4. **A tuple is a physical row version.** MVCC allows multiple versions to coexist.
5. **xmin, xmax, and ctid are internal metadata.** Do not use them in place of primary keys or audit timestamps.
6. **UPDATE/DELETE do not immediately reclaim bytes.** Pruning/VACUUM reclaims space once snapshots no longer need old versions.
7. **TOAST handles large varlena values.** TOAST is not Large Objects.
8. **FSM and VM serve different purposes.** FSM assists in finding free space; VM tracks visibility/freeze state and supports index-only scans.
9. **HOT updates depend on index changes and free space.** Fillfactor can help, but does not guarantee HOT.
10. **Regular VACUUM makes space reusable.** VACUUM FULL rewrites to reclaim file space with heavy locks and cost.
11. **Indexes point to heap TIDs.** Index-only scans reduce heap fetches only when conditions, especially VM visibility, are met.
12. **Measure the right storage components.** Distinguish main fork, table size, indexes, TOAST, and total size.
13. **Page inspection is a specialized tool.** pageinspect, pgstattuple, and FSM functions require proper privileges, cost awareness, and output handling.
14. **WAL/page LSN/checksums serve durability and integrity.** Checksums are not encryption.
15. **Storage maintenance must be workload-driven.** Evaluate dead tuples, long transactions, HOT ratio, bloat, locks, and disk headroom before rewriting.

**One sentence to remember:** *The heap is where PostgreSQL keeps row versions on pages; line pointers locate tuples, MVCC determines which version is visible, TOAST handles oversized values, and FSM/VM/VACUUM manage space and visibility over time.*
