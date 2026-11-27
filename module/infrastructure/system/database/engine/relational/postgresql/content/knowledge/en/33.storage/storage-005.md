# Relationship Between Table Size, Indexes, and TOAST Data in PostgreSQL

A PostgreSQL table with 2 million rows is not necessarily twice as large as a table with 1 million rows. Two tables with the exact same row count can also differ in size by tens of times. A table holding only a few integer columns can be far smaller than a table storing long text, JSONB, arrays, or bytea. Once you factor in indexes, TOAST data, free space, dead tuples, and auxiliary structures, the reported "table size" can differ dramatically from the logical business data size the application thinks it is storing.

PostgreSQL stores tables, indexes, and oversized data as separate physical **relations**. Common size-measurement functions include:

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('public.orders')) AS heap_main,
    pg_size_pretty(pg_table_size('public.orders')) AS table_storage,
    pg_size_pretty(pg_indexes_size('public.orders')) AS indexes,
    pg_size_pretty(pg_total_relation_size('public.orders')) AS total;
~~~

To interpret the output accurately, distinguish:

- **Heap/table relation:** pages storing the table's tuples.
- **Index relations:** B-tree, GIN, GiST, BRIN, or other index structures.
- **TOAST relation:** where PostgreSQL stores variable-length values too large to place directly inside heap tuples.
- **TOAST index:** internal index used to locate chunks of a TOASTed value.
- **Auxiliary forks:** Free Space Map (FSM), Visibility Map (VM), and init fork where applicable.

~~~text
                 A PostgreSQL Table
                        |
         +--------------+---------------+
         |              |               |
         v              v               v
    Heap relation   Index relations   TOAST relation
    - tuples/pages  - B-tree           - large value chunks
    - MVCC versions - GIN/GiST...      - TOAST index
         |              |               |
         +--------------+---------------+
                        |
                   Total storage
             heap + forks + indexes + TOAST
~~~

**Core point:** **pg_relation_size()** defaults to measuring a relation's main fork; **pg_table_size()** measures table storage including TOAST and auxiliary forks; **pg_indexes_size()** measures indexes attached to the table; **pg_total_relation_size()** sums table storage and indexes. To diagnose storage growth, inspect each component rather than looking at only a single total number.

This lesson belongs to the **Storage** chapter of the *Database Engine Relational PostgreSQL* module, focusing on the relationship among heap, index, and TOAST sizes, how PostgreSQL organizes pages/tuples, how to measure via SQL, how to read catalogs, and the effects of updates, vacuum, index maintenance, partitioning, and large data types.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish logical data size from physical on-disk storage size.
2. Explain why row count alone does not directly determine relation size.
3. Describe the relationship among heap, indexes, TOAST table, TOAST index, and auxiliary forks.
4. Use pg_relation_size, pg_table_size, pg_indexes_size, and pg_total_relation_size properly.
5. Measure the size of each individual index and each TOAST relation.
6. Understand how pages, tuple headers, line pointers, alignment, MVCC, and dead tuples affect size.
7. Explain why text, bytea, jsonb, arrays, or other varlena types can be compressed or pushed to TOAST.
8. Distinguish the storage strategies PLAIN, MAIN, EXTERNAL, and EXTENDED.
9. Check column TOAST storage and compression settings via system catalogs.
10. Inspect heap/index/TOAST sizes in a lab with realistic data.
11. Understand why indexes can grow larger than the heap and why many indexes increase write costs.
12. Understand how VACUUM, VACUUM FULL, REINDEX, and ANALYZE affect storage differently.
13. Analyze table bloat, index bloat, TOAST growth, and dead tuples without confusing them with live data.
14. Measure total partition sizes and avoid miscounting partitioned parent tables.
15. Use pg_stat_user_tables, pg_statio_user_tables, pg_indexes, pg_class, and appropriate statistics extensions.
16. Make storage decisions based on measurement rather than extrapolating from row counts.

## 2. Logical Data and Physical Storage

Suppose a table is defined as:

~~~sql
CREATE TABLE app.documents (
    document_id bigint PRIMARY KEY,
    title text NOT NULL,
    body text,
    metadata jsonb,
    attachment bytea
);
~~~

A logical row has five fields, yet PostgreSQL does not necessarily store every byte of body, metadata, and attachment directly inside the table's heap pages.

### 2.1. Logical Size

Logical size describes the content the application cares about, such as:

- Character count of a string.
- Byte count of UTF-8 text content.
- Byte size of a file payload.
- Number of elements in JSON/arrays.
- Row and column counts.

Metrics such as length(text), octet_length(text), or source file size exclude PostgreSQL's full physical storage overhead.

### 2.2. Physical Size

Physical size is the space occupied by relations/forks PostgreSQL uses to store:

- Heap pages and tuple metadata.
- Index pages.
- TOAST chunks and TOAST index.
- Free Space Map and Visibility Map.
- Remaining free space within pages.
- Unreclaimed/unreused dead tuples.

### 2.3. WAL Is Not Included in Relation Size

The Write-Ahead Log (WAL) is a separate log stream in the pg_wal directory, not part of pg_total_relation_size('table'). Replication slots, archived WAL, temporary files, and backup storage are also separate items.

### 2.4. Database Size Differs from One Table's Total Size

pg_database_size() measures database size as calculated by PostgreSQL, encompassing many relations in the database. A single table report excludes other schemas, catalogs, temporary files, and WAL.

### 2.5. Same Row Count, Very Different Sizes

| Table | Data per Row | Index Count | Possible Outcome |
| --- | --- | ---: | --- |
| events_small | a few integers and timestamp | 1 | Small heap, small index |
| articles | title and long body | 2 | TOAST present, larger heap/index |
| files | metadata and bytea | 1 | TOAST can dominate total space |
| search_documents | text/JSONB, multiple GIN indexes | 4 | Indexes can exceed heap size |

## 3. Relations and Physical Components

In PostgreSQL, both tables and indexes are **relations**. A relation is typically stored as one or more file segments inside the data directory.

### 3.1. Heap Relation

The heap stores tuples of an ordinary table. The term "heap" reflects that tuples are not physically kept sorted in a fixed index key order.

### 3.2. Index Relation

Each index is a separate relation. A table can have multiple indexes, each maintaining its own lookup structure.

### 3.3. TOAST Relation

When a row is too large to fit comfortably on a heap page, PostgreSQL can compress or store varlena values out-of-line in an auxiliary TOAST relation.

### 3.4. TOAST Index

A TOAST relation has an internal index to locate chunks of a large value. This index serves TOAST storage internally and is not a business index created by the application.

### 3.5. Auxiliary Forks

A relation can have forks besides main:

- **fsm:** Free Space Map, tracking estimated available space per page.
- **vm:** Visibility Map, tracking whether pages qualify as all-visible/all-frozen.
- **init:** init fork used with unlogged relations to restore initial empty contents after a crash.

Not every relation has all forks at all times.

## 4. Pages, Blocks, and Tuples

PostgreSQL organizes a heap into fixed-size **pages**. The common block size is 8 KiB, though this is a build parameter (BLCKSZ) and should not be hard-coded across all tools.

~~~text
A heap page (simplified model)
+------------------------------------------------+
| PageHeaderData                                 |
+------------------------------------------------+
| ItemId / line pointer array                    |
|   -> tuple offset and length                   |
+------------------------------------------------+
|                                                |
| Tuple data                                     |
|   tuple header + null bitmap + column values   |
|                                                |
|                 free space                     |
|                                                |
+------------------------------------------------+
| Special space (depends on relation type)       |
+------------------------------------------------+
~~~

### 4.1. Page Header

Each page holds metadata allowing PostgreSQL to manage tuple positions, page status, and internal structures. This is not application payload.

### 4.2. Line Pointers

Each tuple is referenced via an item identifier/line pointer on the page. Even when a tuple is logically deleted, its line pointer and physical space may persist until cleanup/reuse occurs.

### 4.3. Tuple Header

The tuple header contains MVCC metadata such as transaction IDs, flags, and null information. Tables with nullable columns may require a null bitmap; every row also incurs alignment overhead.

### 4.4. Alignment and Padding

Data types have different alignment requirements. PostgreSQL may insert padding bytes between fields; therefore, the sum of logical value lengths does not equal exact tuple byte length.

### 4.5. Free Space Within a Page

A page need not be packed completely full of tuples. Free space supports INSERT/UPDATE operations and is tracked via FSM/heap page metadata.

### 4.6. Fillfactor

A table's fillfactor adjusts the target fill level when creating/writing pages. For example, a lower fillfactor leaves room for HOT updates, at the cost of requiring more initial heap pages.

~~~sql
CREATE TABLE app.events (
    event_id bigint,
    payload text
) WITH (fillfactor = 80);
~~~

Fillfactor is a workload tuning knob, not an automatic space-reduction mechanism.

## 5. How MVCC Changes Size

PostgreSQL uses Multi-Version Concurrency Control (MVCC). UPDATE generally creates a new tuple version; DELETE marks the current version no longer live for future snapshots.

### 5.1. UPDATE Does Not Always Overwrite In Place

~~~sql
UPDATE app.documents
SET title = 'New title'
WHERE document_id = 100;
~~~

PostgreSQL creates a new version per MVCC. The old tuple may remain visible to other active transactions/snapshots until no longer needed.

### 5.2. Dead Tuples

An old tuple no longer visible to any snapshot becomes a dead tuple eligible for VACUUM reclamation/reuse. Prior to cleanup, it still consumes heap space.

### 5.3. DELETE Does Not Shrink the File Immediately

~~~sql
DELETE FROM app.documents
WHERE document_id < 1000;
~~~

The visible row count drops, yet the heap file size usually does not drop immediately. Freed space can be reused for future writes.

### 5.4. HOT Update

A Heap-Only Tuple (HOT) update can avoid creating new index entries when conditions hold, such as not modifying indexed columns and having sufficient space on the same page. HOT reduces index churn, yet does not eliminate all MVCC overhead.

### 5.5. A Table Grows Even When Row Count Is Stable

A heavy UPDATE workload can create many tuple versions, index page splits, dead tuples, and fragmented free space. Consequently, storage can grow even while count(*) remains nearly constant.

## 6. What Is TOAST?

**TOAST** stands for *The Oversized-Attribute Storage Technique*. It is PostgreSQL's mechanism for handling variable-length (varlena) values when they become too large to place efficiently in a heap tuple.

Common types eligible for TOAST:

- text, varchar, bytea.
- json, jsonb.
- Array types.
- Certain extension-defined types based on varlena.

### 6.1. Why Is TOAST Needed?

A heap tuple must fit on a page and leave room for other tuples. If a row carries a 2 MB JSON payload, storing the entire value inline would fit very few rows per page, increasing I/O and hurting efficiency.

### 6.2. Compress First, Externalize When Needed

PostgreSQL can:

1. Compress large varlena values if the storage strategy permits.
2. If the tuple is still too large, move selected values out to a TOAST table.
3. Replace the inline value with a small external TOAST pointer inside the heap tuple.

### 6.3. Not Every Large Value Gets TOASTed

TOAST applies to eligible data types and storage strategies. Small values remain inline. Fixed-length types do not use the varlena TOAST mechanism in the same way.

### 6.4. Do Not Hard-Code Thresholds

In default 8 KiB block builds, the tuple processing threshold is around a quarter of a page (roughly 2 KiB), yet actual behavior depends on page size, tuple overhead, and build/config. PostgreSQL aims to bring the tuple down to a target size rather than guaranteeing every column over a fixed byte count is externalized.

### 6.5. TOAST Is Not a Separate Database

A TOAST table is an internal relation belonging to its parent table. PostgreSQL manages its name, dependency relationship, and TOAST index; users must never write/delete chunks directly.

## 7. How Does a TOAST Relation Store Data?

Each table needing TOAST gets an auxiliary relation. Large values can be split into chunks; a TOAST index retrieves chunks by value ID and chunk sequence.

~~~text
Heap table: app.documents
  row document_id=10
  body = external pointer
              |
              v
TOAST table: pg_toast.pg_toast_<oid>
  value_id | chunk_seq | chunk_data
  ---------+-----------+-----------
  ...      | 0         | bytes ...
  ...      | 1         | bytes ...
  ...      | 2         | bytes ...
              |
              v
TOAST index
  (value_id, chunk_seq)
~~~

### 7.1. External Pointer in the Heap

The heap tuple holds metadata referencing the TOAST value instead of the entire payload. When a query reads that value, PostgreSQL fetches the associated chunks.

### 7.2. Chunking

A large value is split into multiple chunks stored in the TOAST table. Each chunk has a sequence number and is reassembled on read.

### 7.3. TOAST Index

The TOAST index is essential for locating chunks. It also consumes storage, has pages, and incurs maintenance cost.

### 7.4. Updating a TOAST Value

If an application modifies a large JSONB/text field, PostgreSQL may have to write a new TOAST value and update the external pointer. Never assume a tiny edit inside JSONB writes only a few physical bytes.

### 7.5. Reading a Small Column Does Not Always Read the TOAST Payload

A query selecting only document_id and title can avoid fetching large body/attachment values. Designing queries to fetch only needed columns reduces I/O and network payload.

## 8. Varlena and TOAST-Eligible Data Types

PostgreSQL uses a varlena representation for many variable-length types. Varlena allows values to carry length/representation metadata and supports compression/external storage.

### 8.1. Text

~~~sql
CREATE TABLE app.notes (
    note_id bigint PRIMARY KEY,
    content text
);
~~~

A text column can be very short or very long; PostgreSQL does not preallocate a fixed maximum buffer for every row.

### 8.2. Bytea

~~~sql
CREATE TABLE app.attachments (
    attachment_id bigint PRIMARY KEY,
    payload bytea
);
~~~

Bytea works well for storing binary bytes, though large files require evaluating TOAST, backups, replication, streaming, and fetch overhead. Storing files in object storage while keeping metadata/references in PostgreSQL is also a common architectural choice.

### 8.3. JSONB

~~~sql
CREATE TABLE app.events (
    event_id bigint PRIMARY KEY,
    payload jsonb NOT NULL
);
~~~

JSONB has its own binary representation and can be TOASTed when large. Beyond heap/TOAST, a GIN index on JSONB can consume considerable space.

### 8.4. Arrays

~~~sql
CREATE TABLE app.measurements (
    measurement_id bigint PRIMARY KEY,
    samples numeric[]
);
~~~

Large arrays can also trigger TOAST. If queries frequently target individual elements, a child-table design may be more efficient than a massive array depending on workload.

### 8.5. Composite and Extension Types

A composite type may rely on varlena, though exact TOAST capability depends on type definition and storage support.

## 9. The Four TOAST Storage Strategies

PostgreSQL stores a storage attribute per column:

| Storage | Compress? | Out-of-line to TOAST? | Meaning |
| --- | --- | --- | --- |
| PLAIN | No | No | Keep inline; no TOAST compression or out-of-line storage |
| MAIN | Yes | Only if needed to fit tuple | Prefer keeping inline after compression |
| EXTERNAL | No | Yes | Can store out-of-line without compression |
| EXTENDED | Yes | Yes | Allows compression and external storage; common default for varlena |

### 9.1. PLAIN

Suitable for types/representations requiring inline storage or when TOAST must be prevented. For large columns forced inline, rows may fail to fit on a page and writes may fail.

### 9.2. MAIN

PostgreSQL can compress the value while preferring to keep it inline; it pushes out-of-line only when necessary for the tuple to meet target size.

### 9.3. EXTERNAL

PostgreSQL can store the value out-of-line uncompressed. For workloads reading substrings/slices, avoiding full-value decompression can help, at the cost of higher storage usage.

### 9.4. EXTENDED

Allows both compression and out-of-line storage. This is the standard default for varlena types like text, bytea, and jsonb.

### 9.5. Changing Storage Strategy

~~~sql
ALTER TABLE app.documents
ALTER COLUMN body SET STORAGE EXTERNAL;
~~~

This adjusts how PostgreSQL stores **values written or updated in the future**. It does not automatically rewrite all existing stored values into the new strategy.

### 9.6. Do Not Pick EXTERNAL Just Because TOAST Looks Large

Skipping compression can cause TOAST to grow sharply if data is highly compressible. Pick a strategy only after measuring compression ratios, read patterns, and total footprint.

## 10. TOAST Compression

PostgreSQL can compress varlena values before externalizing or keeping them inline depending on strategy. Compression saves disk and I/O at the expense of CPU.

### 10.1. PGLZ

PGLZ is PostgreSQL's traditional default compression method. It requires no additional external library.

### 10.2. LZ4

PostgreSQL builds compiled with LZ4 support allow choosing the LZ4 compression method. Exact feature availability and configuration depend on server version and build options.

### 10.3. Choosing Compression Per Column

On supported versions, you can specify:

~~~sql
ALTER TABLE app.documents
ALTER COLUMN body SET COMPRESSION lz4;
~~~

or another supported method such as pglz. Verify server build and version before relying on this syntax.

### 10.4. Compression Does Not Always Save Space

For already-compressed data (JPEG, ZIP, PDF, video, encrypted blobs), compressing again yields minimal savings while burning CPU. Repetitive text usually achieves far better compression ratios.

### 10.5. Compression Ratio

A logical check:

~~~sql
SELECT
    document_id,
    octet_length(body) AS logical_bytes,
    pg_column_size(body) AS datum_bytes
FROM app.documents
ORDER BY document_id;
~~~

octet_length() returns text content bytes in its encoding; pg_column_size() returns the datum representation size as measured by PostgreSQL. For TOAST/external values, do not interpret pg_column_size() as the sum of all chunks plus TOAST index overhead for the row; use relation size functions to measure total storage.

### 10.6. Changing Compression Method Does Not Rewrite Old Data

After changing the compression method, previously stored values are not automatically recompressed. Converting existing data requires a controlled rewrite/update plan accounting for WAL, locks, and temporary disk space.

## 11. Heap Size, Table Size, Index Size, and Total Size

The four primary size functions:

~~~sql
SELECT
    pg_size_pretty(pg_relation_size('public.orders')) AS relation_main,
    pg_size_pretty(pg_table_size('public.orders')) AS table_bytes,
    pg_size_pretty(pg_indexes_size('public.orders')) AS index_bytes,
    pg_size_pretty(pg_total_relation_size('public.orders')) AS total_bytes;
~~~

### 11.1. pg_relation_size

pg_relation_size(relation [, fork]) returns the bytes of a single relation/fork. When fork is omitted, it defaults to the main fork.

Example:

~~~sql
SELECT
    pg_size_pretty(
        pg_relation_size('public.orders', 'main')
    ) AS main_fork,
    pg_size_pretty(
        pg_relation_size('public.orders', 'fsm')
    ) AS free_space_map,
    pg_size_pretty(
        pg_relation_size('public.orders', 'vm')
    ) AS visibility_map;
~~~

### 11.2. pg_table_size

Measures the table's storage, including the heap relation, auxiliary forks, and associated TOAST storage as calculated by PostgreSQL; **it excludes the business indexes directly attached to the table**.

### 11.3. pg_indexes_size

Measures the size of indexes attached to the table. A table can have multiple indexes, each being an independent relation.

### 11.4. pg_total_relation_size

Measures the combined size of the table, its indexes, and its TOAST storage. This is usually the right metric when asking how much overall space a table consumes.

### 11.5. Sizes in Bytes

Size functions return byte counts (bigint). Use pg_size_pretty() for readable KB/MB/GB display, while keeping raw byte values when computing accurate ratios or deltas.

### 11.6. Comparison Summary

| Function | Scope |
| --- | --- |
| pg_relation_size(table) | Main fork of the specified relation |
| pg_table_size(table) | Heap, auxiliary forks, and TOAST storage |
| pg_indexes_size(table) | Indexes attached to the table |
| pg_total_relation_size(table) | Total of table + indexes + TOAST |

## 12. Measuring Each Index of a Table

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(
        pg_relation_size(
            quote_ident(schemaname) || '.' || quote_ident(indexname)
        )
    ) AS index_size
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename = 'orders'
ORDER BY pg_relation_size(
    quote_ident(schemaname) || '.' || quote_ident(indexname)
) DESC;
~~~

A cleaner catalog-based approach:

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    pg_size_pretty(pg_relation_size(i.indexrelid)) AS index_size
FROM pg_index AS i
WHERE i.indrelid = 'public.orders'::regclass
ORDER BY pg_relation_size(i.indexrelid) DESC;
~~~

### 12.1. Why Can an Index Be Large?

- Multi-column indexes or indexes on wide values.
- GIN indexes on JSONB/arrays/full-text.
- Many indexes serving diverse queries.
- Page splits and fragmentation.
- Dead index tuples/unreused space.

### 12.2. Indexes Are Not Free

Every INSERT may need to add index entries. Updating an indexed column typically adds extra index write overhead. Having many indexes increases storage, WAL, CPU, and write latency.

### 12.3. Never Drop an Index Just Because It Is Large

A large index may be essential for query latency and uniqueness constraints. Evaluate usage stats, query plans, uniqueness, and workload before changing indexes.

## 13. Measuring the TOAST Relation

Every table with TOAST references its TOAST table via pg_class.reltoastrelid.

~~~sql
SELECT
    c.oid::regclass AS table_name,
    CASE
        WHEN c.reltoastrelid = 0 THEN NULL
        ELSE c.reltoastrelid::regclass::text
    END AS toast_table,
    CASE
        WHEN c.reltoastrelid = 0 THEN NULL
        ELSE pg_size_pretty(
            pg_total_relation_size(c.reltoastrelid)
        )
    END AS toast_total_size
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname = 'documents';
~~~

### 13.1. reltoastrelid Equal to 0

A value of 0 means the relation has no attached TOAST relation in the catalog at inspection time. Not every table requires TOAST.

### 13.2. TOAST Tables Live in a System Schema

Physical names typically belong to the pg_toast schema; users should access data through the parent table and catalogs, never manipulating TOAST chunks directly.

### 13.3. Measuring TOAST Alone Is Not the Whole Table

The TOAST result covers only the auxiliary relation. To get the table's full footprint, run pg_total_relation_size() on the parent table.

### 13.4. TOAST Index

A TOAST table has an internal index. Calling pg_total_relation_size() on the TOAST relation's OID measures the TOAST table plus its internal index; avoid adding it again if you already used pg_total_relation_size() on the main table.

### 13.5. Avoid Double Counting

If a report includes table_size, toast_size, index_size, and total_size, clarify whether table_size already includes TOAST. Since pg_table_size() already includes TOAST, adding toast_size on top double-counts it.

## 14. Measuring All Tables in a Schema

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    pg_size_pretty(pg_relation_size(
        quote_ident(schemaname) || '.' || quote_ident(relname)
    )) AS heap_main,
    pg_size_pretty(pg_table_size(
        quote_ident(schemaname) || '.' || quote_ident(relname)
    )) AS table_storage,
    pg_size_pretty(pg_indexes_size(
        quote_ident(schemaname) || '.' || quote_ident(relname)
    )) AS indexes,
    pg_size_pretty(pg_total_relation_size(
        quote_ident(schemaname) || '.' || quote_ident(relname)
    )) AS total
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(
    quote_ident(schemaname) || '.' || quote_ident(relname)
) DESC;
~~~

### 14.1. Measures User Tables Only

pg_stat_user_tables is convenient for listing user tables in monitored schemas.

### 14.2. Change Schema Name

Replace public with the schema you are investigating. Never assume all applications live in public.

### 14.3. Safe Identifiers

In the example, identifiers are quoted so table/schema names with special characters are handled safely. For automated tooling, prefer OID-based catalog joins over string concatenation.

### 14.4. Partitioned Parents

A partitioned parent table does not store heap tuples like an ordinary table. To report accurately per partition, enumerate leaf partitions and measure each relation.

## 15. Catalogs pg_class and pg_attribute

pg_class stores relation metadata:

- relkind: relation type.
- reltoastrelid: OID of the TOAST relation.
- relpages, reltuples: page and tuple estimates.
- relfilenode: current file node within the tablespace.
- relpersistence: permanent/unlogged/temporary.
- reloptions: storage parameters such as fillfactor.

pg_attribute describes columns, including storage strategy and compression attributes depending on version.

### 15.1. Inspecting Table and TOAST

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    c.relkind,
    c.reltoastrelid,
    CASE
        WHEN c.reltoastrelid = 0 THEN NULL
        ELSE c.reltoastrelid::regclass
    END AS toast_relation,
    c.relpages,
    c.reltuples,
    c.reloptions
FROM pg_class AS c
WHERE c.oid = 'public.documents'::regclass;
~~~

### 15.2. Inspecting Column Storage Strategy

~~~sql
SELECT
    a.attname AS column_name,
    a.atttypid::regtype AS data_type,
    a.attstorage,
    a.attcompression
FROM pg_attribute AS a
WHERE a.attrelid = 'public.documents'::regclass
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY a.attnum;
~~~

attcompression exists on PostgreSQL versions supporting per-column compression selection (e.g., PostgreSQL 14+). On older servers, querying this column will error; omit attcompression when compatibility is needed.

### 15.3. relkind

Common types:

| relkind | Type |
| --- | --- |
| r | Ordinary table |
| p | Partitioned table |
| i | Index |
| I | Partitioned index |
| t | TOAST table |
| m | Materialized view |
| v | View |

### 15.4. relpages and reltuples Are Estimates

These columns are statistics/catalog estimates, not always exact immediately after fresh workloads. ANALYZE updates planner statistics; size functions measure physical bytes separately.

## 16. Lab: Creating a Table with Inline and TOAST Data

Create the schema:

~~~sql
CREATE SCHEMA storage_lab;
~~~

Create the table:

~~~sql
CREATE TABLE storage_lab.documents (
    document_id bigint PRIMARY KEY,
    title text NOT NULL,
    body text,
    payload bytea,
    metadata jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

### 16.1. Adding Business Indexes

~~~sql
CREATE INDEX idx_documents_created_at
ON storage_lab.documents (created_at);

CREATE INDEX idx_documents_metadata_gin
ON storage_lab.documents
USING gin (metadata);
~~~

### 16.2. Inserting Data with Large Bodies

~~~sql
INSERT INTO storage_lab.documents (
    document_id, title, body, metadata
)
SELECT
    g,
    'Document ' || g,
    (
        SELECT string_agg(
            md5(g::text || ':' || s::text),
            ''
        )
        FROM generate_series(1, 250) AS s
    ),
    jsonb_build_object(
        'category', 'lab',
        'sequence', g,
        'tags', jsonb_build_array('postgres', 'storage', 'toast')
    )
FROM generate_series(1, 30) AS g;
~~~

Body contains many distinct hash strings, making it large and resistant to strong compression compared to a simple repeated string.

### 16.3. Adding Bytea Payloads

~~~sql
UPDATE storage_lab.documents
SET payload = decode(
    repeat(md5(document_id::text), 300),
    'hex'
);
~~~

This simulates a binary payload. Each md5() returns 32 hex characters; decode(..., 'hex') converts it to bytes.

### 16.4. Adding Large JSONB

~~~sql
UPDATE storage_lab.documents
SET metadata = metadata ||
    jsonb_build_object(
        'attributes',
        (
            SELECT jsonb_agg(
                jsonb_build_object(
                    'key', 'field-' || s,
                    'value', md5(document_id::text || ':' || s::text)
                )
            )
            FROM generate_series(1, 100) AS s
        )
    );
~~~

### 16.5. Millions of Records Are Not Needed to Trigger TOAST

Even a few dozen rows with large fields can trigger a TOAST relation. Exact sizes depend on version, compression, and generated data.

## 17. Measuring the Lab Table

~~~sql
SELECT
    pg_size_pretty(pg_relation_size(
        'storage_lab.documents'
    )) AS heap_main,
    pg_size_pretty(pg_table_size(
        'storage_lab.documents'
    )) AS table_including_toast,
    pg_size_pretty(pg_indexes_size(
        'storage_lab.documents'
    )) AS indexes,
    pg_size_pretty(pg_total_relation_size(
        'storage_lab.documents'
    )) AS total;
~~~

### 17.1. Reading the Results

- heap_main: main fork of the heap relation.
- table_including_toast: table storage plus auxiliary/TOAST components per function semantics.
- indexes: indexes attached to the table.
- total: combined storage of the table and indexes.

### 17.2. Why Is heap_main Smaller Than table_including_toast?

When body, payload, or metadata are TOASTed, their payloads reside in the auxiliary relation. Thus the heap holds only pointers and inline fields, while TOAST storage increases table size.

### 17.3. Why Is total Larger Than table?

The table has a primary key index, a created_at index, and a metadata GIN index. Each index is an independent relation increasing total space.

### 17.4. Index Ratio

~~~sql
SELECT
    pg_total_relation_size('storage_lab.documents') AS total_bytes,
    pg_indexes_size('storage_lab.documents') AS index_bytes,
    round(
        100.0 * pg_indexes_size('storage_lab.documents')
        / NULLIF(
            pg_total_relation_size('storage_lab.documents'), 0
        ),
        2
    ) AS index_percent;
~~~

A high ratio is not automatically bad; a search-heavy table can legitimately have a GIN index larger than its heap.

## 18. Measuring Individual Indexes in the Lab

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    pg_size_pretty(pg_relation_size(i.indexrelid)) AS index_size,
    am.amname AS access_method,
    pg_get_indexdef(i.indexrelid) AS index_definition
FROM pg_index AS i
JOIN pg_class AS ic
  ON ic.oid = i.indexrelid
JOIN pg_am AS am
  ON am.oid = ic.relam
WHERE i.indrelid = 'storage_lab.documents'::regclass
ORDER BY pg_relation_size(i.indexrelid) DESC;
~~~

### 18.1. B-tree and GIN

Primary key and created_at indexes typically use B-tree; the lab JSONB index uses GIN. GIN has a different structure and fan-out from B-tree, so size and write cost cannot be deduced simply from row count.

### 18.2. Indexes Can Store Substantial Metadata

An index stores keys and tuple locators plus page overhead. A GIN index expands with the number of tokens/keys inside JSONB.

### 18.3. Indexes Do Not Store the Full Row Like the Heap

An index only stores data required by its access method and tuple references; however, with expression indexes or INCLUDE columns, data stored inside the index can grow substantial.

### 18.4. A Primary Key Is Also an Index

Declaring a PRIMARY KEY automatically creates a unique B-tree index. Do not create a redundant duplicate index on the exact same key without a specific purpose.

## 19. Measuring the Lab's TOAST Relation

~~~sql
SELECT
    c.oid::regclass AS table_name,
    t.oid::regclass AS toast_table,
    pg_size_pretty(pg_relation_size(t.oid)) AS toast_heap_main,
    pg_size_pretty(pg_total_relation_size(t.oid)) AS toast_total
FROM pg_class AS c
JOIN pg_class AS t
  ON t.oid = c.reltoastrelid
WHERE c.oid = 'storage_lab.documents'::regclass;
~~~

### 19.1. If No Rows Are Returned

The table does not have a TOAST relation yet or catalog relations did not match. In our lab with long fields, PostgreSQL normally creates a TOAST relation, though this still depends on actual data and storage behavior.

### 19.2. Inspecting Chunk Counts (Internal Investigation Only)

You can inspect TOAST relation metadata via catalogs or read the system relation with appropriately privileged admin tools. Never build application queries directly against pg_toast tables, as names/OIDs and storage layout are implementation details.

### 19.3. Never Update TOAST Chunks Directly

Editing or deleting internal chunks breaks external pointers and corrupts data. Always update columns on the parent table through normal SQL.

## 20. pg_column_size, octet_length, and pg_column_compression

These three functions answer different questions.

### 20.1. octet_length

For text, returns the byte count of the content in the string's encoding:

~~~sql
SELECT
    title,
    length(body) AS characters,
    octet_length(body) AS logical_bytes
FROM storage_lab.documents
LIMIT 5;
~~~

### 20.2. pg_column_size

Returns the bytes used to store a single datum in PostgreSQL's representation, which may reflect compression. It is not the total size of the entire TOAST relation or indexes.

~~~sql
SELECT
    document_id,
    octet_length(body) AS body_logical_bytes,
    pg_column_size(body) AS body_datum_bytes,
    octet_length(payload) AS payload_bytes,
    pg_column_size(payload) AS payload_datum_bytes
FROM storage_lab.documents
ORDER BY document_id
LIMIT 10;
~~~

### 20.3. pg_column_compression

On supported versions, pg_column_compression(any) returns the compression method name used for the datum, or NULL if uncompressed.

~~~sql
SELECT
    document_id,
    pg_column_compression(body) AS body_compression,
    pg_column_compression(metadata) AS metadata_compression
FROM storage_lab.documents
ORDER BY document_id
LIMIT 10;
~~~

### 20.4. Why Do the Three Numbers Differ?

- octet_length: logical content in bytes.
- pg_column_size: datum representation size per function rules.
- pg_total_relation_size: physical storage of relation/table/indexes across multiple structures.

Never sum pg_column_size() across all rows expecting it to equal pg_total_relation_size(): doing so ignores page headers, tuple headers, line pointers, free space, indexes, TOAST chunks, forks, and dead tuples.

### 20.5. Version Limits

pg_column_compression() and compression metadata depend on PostgreSQL version. If the function does not exist, check server version and omit that column from measurement queries.

## 21. Index Size vs. Heap Size

A table may look like:

~~~sql
CREATE TABLE app.search_docs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text,
    body text,
    attributes jsonb
);

CREATE INDEX search_docs_title_idx
ON app.search_docs (title);

CREATE INDEX search_docs_attributes_gin
ON app.search_docs
USING gin (attributes);
~~~

### 21.1. GIN Indexes on JSONB

GIN can index numerous keys/tokens inside JSONB. A single JSONB row with many attributes can generate dozens or hundreds of index entries; the index can grow huge.

### 21.2. Full-Text Search

A tsvector or expression index for full-text search stores lexemes and metadata. Index entry count does not equal row count.

### 21.3. INCLUDE Columns

~~~sql
CREATE INDEX orders_customer_cover_idx
ON app.orders (customer_id)
INCLUDE (created_at, total_amount);
~~~

An index carrying extra payload columns grows larger, yet supports index-only scans under appropriate visibility conditions.

### 21.4. Partial Indexes

~~~sql
CREATE INDEX orders_open_idx
ON app.orders (created_at)
WHERE status = 'open';
~~~

A partial index can be much smaller than a full-table index if it covers only a subset of rows. Align query predicates so the planner can use it.

### 21.5. Overlapping Indexes

Two indexes sharing prefix columns yet differing in column order, collation, predicate, or INCLUDE columns may serve different queries. Never drop indexes based solely on name; inspect query plans and usage stats.

## 22. Why Can a Table Be Larger Than Its Logical Data?

Physical storage carries multiple layers of overhead:

1. Page headers and line pointers.
2. Tuple headers, null bitmaps, and alignment.
3. Free space within pages.
4. Dead tuples and older MVCC versions.
5. Index entries and index page overhead.
6. TOAST chunks and TOAST indexes.
7. FSM/VM/init forks.
8. Fragmentation and page splits.

### 22.1. Not Every File Byte Is Payload

A table storing 1 GB of application content can occupy well over 1 GB of relation storage due to overhead and indexes. The ratio depends on data types, index count, fillfactor, update rate, and compression.

### 22.2. Compression Can Make Storage Smaller Than Logical Payload

Long repetitive strings compress heavily. Consequently, PostgreSQL's physical file size can sometimes be smaller than the sum of octet_length() values.

### 22.3. Many Indexes Can Multiply Total Size Beyond Payload

A table with multiple GIN indexes or wide-key indexes can have a total size many times larger than heap + TOAST.

### 22.4. Size Cannot Be Inferred from Column Count

One 5 MB jsonb column differs completely from one integer column; column count does not reflect storage footprint.

## 23. VACUUM and Heap Size

Regular VACUUM cleans eligible dead tuples and marks space for reuse. It **does not routinely shrink relation files back to the OS**.

### 23.1. Regular VACUUM

~~~sql
VACUUM (ANALYZE) storage_lab.documents;
~~~

Can:

- Clean up unneeded dead tuples.
- Make page space ready for future writes.
- Update the visibility map.
- Update statistics when combined with ANALYZE.

### 23.2. File Size Usually Does Not Shrink Much

Free space inside the middle of a relation is retained for reuse. Hence pg_total_relation_size() may stay nearly unchanged after VACUUM even as n_dead_tup drops.

### 23.3. VACUUM FULL

~~~sql
VACUUM FULL storage_lab.documents;
~~~

VACUUM FULL rewrites the table into a new file to reclaim physical disk space, typically requiring an ACCESS EXCLUSIVE lock and sufficient temporary disk space. This is not a lightweight command to run casually during peak traffic.

### 23.4. Autovacuum

Autovacuum automates cleanup and analyze based on thresholds/scale factors and workload. It does not automatically run VACUUM FULL to shrink every file.

### 23.5. Long-Running Transactions and Replication Slots

Long snapshots or replication slots pinning xmin can prevent VACUUM from removing certain dead tuples. Heap and indexes may keep growing even while autovacuum runs.

## 24. REINDEX and Index Size

REINDEX rebuilds an index:

~~~sql
REINDEX INDEX storage_lab.idx_documents_created_at;
~~~

### 24.1. REINDEX Targets Indexes, Not the Heap

It does not directly shrink the heap table or TOAST data. To measure effectiveness, compare index size before/after and evaluate query plans.

### 24.2. REINDEX TABLE

~~~sql
REINDEX TABLE storage_lab.documents;
~~~

Rebuilds all indexes of the table under the applicable locking mode.

### 24.3. REINDEX CONCURRENTLY

~~~sql
REINDEX INDEX CONCURRENTLY storage_lab.idx_documents_created_at;
~~~

Reduces blocking of concurrent writes compared to standard REINDEX in supported conditions, yet performs more phases, consumes temporary resources, and has usage constraints. Check version and lock behavior before production use.

### 24.4. Do Not Reindex Everything on a Rigid Schedule

Large index size alone does not prove index bloat. Inspect workload, statistics, index health, and dedicated measurement tools before deciding.

## 25. Bloat: Heap, Index, and TOAST

**Bloat** is poorly utilized space caused by dead tuples, excess free space, page splits, or storage patterns mismatched to the workload. There is no single definition of bloat applicable to every report.

### 25.1. Heap Bloat

The heap has many pages holding few live tuples or many unreclaimed dead tuples. File size grows while visible row count does not.

### 25.2. Index Bloat

An index has many sparsely populated pages, fragmentation, or dead entries/space. Different index access methods reclaim and reuse pages differently.

### 25.3. TOAST Bloat

Old TOAST values from updates/deletes create dead chunks; the TOAST table also needs VACUUM cleanup. If large fields are updated frequently, the TOAST relation can expand.

### 25.4. Do Not Confuse Useful Free Space with Wasted Bloat

Free space on pages can be highly beneficial for upcoming INSERT/UPDATE workloads. Shrinking via rewrite removes that headroom and may cause the table to grow right back afterward.

### 25.5. Size Alone Is Insufficient

Evaluating bloat requires knowing live/dead tuple counts, page density, index-specific stats, and workload history.

## 26. Observing with pg_stat_user_tables

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'storage_lab'
ORDER BY n_dead_tup DESC;
~~~

### 26.1. n_live_tup/n_dead_tup Are Estimates

These counters/stats are not exact instantaneous full-table row counts. They are useful for monitoring and trends.

### 26.2. Update Churn

Rapidly climbing n_tup_upd alongside steady n_live_tup suggests heavy update churn, warranting checks on vacuum, HOT updates, and dead tuples.

### 26.3. Vacuum Timestamps

last_autovacuum/last_vacuum indicate when vacuum last completed per stats; they do not by themselves prove everything was reclaimed.

### 26.4. Stats Can Reset

Counters can reset via administrative commands, restarts, or version-specific stats behavior. When calculating rates, check reset timestamps.

## 27. Viewing I/O with pg_statio_user_tables

~~~sql
SELECT
    schemaname,
    relname,
    heap_blks_read,
    heap_blks_hit,
    idx_blks_read,
    idx_blks_hit,
    toast_blks_read,
    toast_blks_hit,
    tidx_blks_read,
    tidx_blks_hit
FROM pg_statio_user_tables
WHERE schemaname = 'storage_lab';
~~~

### 27.1. Heap Blocks

Reports heap blocks read from storage or hit in shared buffers per stats.

### 27.2. Index Blocks

Helps observe index I/O activity at the table level.

### 27.3. TOAST Blocks

Shows whether the workload is reading TOAST data. If queries frequently fetch large payloads, toast block reads/hits climb.

### 27.4. TOAST Index Blocks

tidx_blks_* relate to the TOAST index. This is a useful signal when queries locate external chunks.

### 27.5. Cache Hits Are Not Free

A cache hit avoids physical disk I/O at that layer, yet still consumes CPU, memory bandwidth, and tuple reconstruction/decompression work.

## 28. Using pgstattuple for Deep Measurements

The pgstattuple extension reports live/dead tuple and free-space statistics for a relation:

~~~sql
CREATE EXTENSION IF NOT EXISTS pgstattuple;

SELECT *
FROM pgstattuple('storage_lab.documents');
~~~

### 28.1. Output

The extension can report:

- table_len.
- tuple_count, tuple_len.
- dead_tuple_count, dead_tuple_len.
- free_space and corresponding percentages.

### 28.2. Scanning Relations Has a Cost

pgstattuple can scan the entire relation. On large tables, weigh I/O cost and run during appropriate windows.

### 28.3. pgstattuple_approx

An approximation function can use the visibility map to reduce scan work under appropriate conditions. Results are approximations, not a substitute for a full scan when exact numbers are required.

### 28.4. Privileges and Extensions

Installing extensions requires administrative privileges and server-installed packages/modules. Never assume every managed PostgreSQL service permits every extension.

### 28.5. Do Not Turn Bloat Reports into Automatic Rewrite Triggers

Measurements are only inputs to a decision. Rewrites/reindexes require plans for locks, disk space, replication, backups, and rollback.

## 29. How Do FSM and VM Affect Size?

### 29.1. Free Space Map

The FSM stores estimates of free space per page so PostgreSQL can locate pages for new tuples. It occupies a portion of relation storage and updates through writes/vacuuming.

### 29.2. Visibility Map

The VM stores page-level all-visible/all-frozen flags per PostgreSQL semantics. It supports VACUUM and index-only scans.

### 29.3. Index-Only Scans

If a query needs only columns present in an index and the visibility map indicates qualifying pages, PostgreSQL can skip heap fetches for those rows. A healthy VM improves performance without shrinking index size.

### 29.4. Init Fork

Unlogged relations have an init fork to restore initial empty state after a crash. The init fork is a separate physical file; not every table has one.

### 29.5. Measuring Each Fork

~~~sql
SELECT
    pg_size_pretty(pg_relation_size(
        'storage_lab.documents', 'main'
    )) AS main,
    pg_size_pretty(pg_relation_size(
        'storage_lab.documents', 'fsm'
    )) AS fsm,
    pg_size_pretty(pg_relation_size(
        'storage_lab.documents', 'vm'
    )) AS vm,
    pg_size_pretty(pg_relation_size(
        'storage_lab.documents', 'init'
    )) AS init;
~~~

If a fork does not exist or does not apply, the result can be 0.

## 30. Relation File Paths and Tablespaces

Administrative functions reveal relation file locations:

~~~sql
SELECT
    pg_relation_filenode('storage_lab.documents'::regclass)
        AS filenode,
    pg_relation_filepath('storage_lab.documents'::regclass)
        AS relative_path;
~~~

### 30.1. relfilenode

The current physical file identifier for the relation in storage. Certain rewrite/reindex operations change the filenode.

### 30.2. Files Can Split into Segments

A relation exceeding the segment limit spans multiple segment files. Never look at only one file named after the filenode and assume it represents the entire relation.

### 30.3. Tablespaces

A relation may reside in a custom tablespace. Physical paths may differ from the default tablespace; OS permissions and disk management must account for this.

### 30.4. Never Edit or Delete Relation Files Directly

Never move, truncate, rename, or delete files inside base/ or pg_tblspc/ while the server manages the relation. Use SQL/DDL and PostgreSQL tools.

## 31. Partitioning and Total Size

A partitioned table (relkind = 'p') is a logical parent relation and does not hold heap rows like an ordinary table. Data resides in child partitions.

### 31.1. Measuring Each Leaf Partition

On versions supporting pg_partition_tree():

~~~sql
SELECT
    relid::regclass AS partition_name,
    isleaf,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_partition_tree('app.events'::regclass)
WHERE isleaf
ORDER BY pg_total_relation_size(relid) DESC;
~~~

### 31.2. Sum Across Partitions

~~~sql
SELECT
    sum(pg_total_relation_size(relid)) AS total_bytes,
    pg_size_pretty(sum(pg_total_relation_size(relid))) AS total_pretty
FROM pg_partition_tree('app.events'::regclass)
WHERE isleaf;
~~~

### 31.3. Do Not Sum Both Parent and Leaves

If a report already sums leaf partitions, never add the parent again if the reporting tool already aggregates descendants. Document aggregation rules clearly to prevent double counting.

### 31.4. Partitions Can Differ Widely

Monthly partitions can vary dramatically in size due to retention, seasonality, and skew. Reporting top partitions helps spot hot data or anomalous batch loads.

### 31.5. Index Partitions

A partitioned index on the parent is backed by indexes on individual partitions. When measuring indexes, distinguish parent index metadata from leaf index relations.

## 32. Materialized Views and TOAST

A materialized view stores query results as a physical relation. It can have a heap, indexes, and TOAST just like a table.

~~~sql
SELECT
    pg_size_pretty(pg_total_relation_size(
        'app.monthly_report'::regclass
    ));
~~~

### 32.1. Regular Views Have No Heap Storage

A view (relkind = 'v') is merely a query definition and holds no physical copy of data like a materialized view.

### 32.2. Materialized Views Can Have Indexes

Indexes on a materialized view add to total size and increase REFRESH MATERIALIZED VIEW cost.

### 32.3. Measure the Right Relation Type

When reporting sizes, filter by relkind so logical views are never compared with physical heap tables.

## 33. Unlogged and Temporary Tables

### 33.1. Unlogged Tables

Unlogged tables reduce WAL for table data per PostgreSQL semantics, yet lack crash durability like logged tables and are not replicated via physical WAL like normal tables. They still occupy relation disk space.

### 33.2. Init Fork

Unlogged relations use an init fork to reset to an initial empty state upon server crash/restart per PostgreSQL rules.

### 33.3. Temporary Tables

Temporary tables belong to session/transaction scope and can use separate temporary storage. They should not be confused with durable application data.

### 33.4. Measuring Temp Data

Temporary files created by sort/hash spills differ from temporary table relations. They have separate lifecycles and monitoring, and are excluded from pg_total_relation_size() of business tables.

## 34. TOAST and Query Performance

### 34.1. SELECT Only Needed Columns

~~~sql
SELECT document_id, title
FROM storage_lab.documents
WHERE document_id = 10;
~~~

Omit body, payload, and metadata if the request does not need them. This cuts down TOAST fetches/decompression and bytes sent to clients.

### 34.2. SELECT *

~~~sql
SELECT *
FROM storage_lab.documents
WHERE document_id = 10;
~~~

Can force PostgreSQL to retrieve oversized values, increasing I/O, decompression CPU, and network payload.

### 34.3. Functions Can Trigger Detoasting

Many text/JSONB functions read the full value and trigger detoasting. When writing expressions, do not assume a JSONB operation touches only a few bytes.

### 34.4. JSONB Path Updates

jsonb_set() builds a new resulting JSONB value per data semantics. On a very large document, changing a single key can still incur processing and write costs far larger than a few bytes.

### 34.5. Separating Metadata and Blobs

If applications mostly read metadata and rarely fetch attachments, moving file payloads to a dedicated table or object storage can reduce metadata query footprints. Balance this against transaction consistency, backups, authorization, and file lifecycle.

## 35. Storage Strategy and Read Workloads

### 35.1. EXTENDED

Usually well suited for compressible text/jsonb data that is not predominantly accessed by small slices.

### 35.2. EXTERNAL

Can help for incompressible data or substring/slice access patterns where avoiding full-datum decompression helps in certain cases. The trade-off is larger storage usage.

### 35.3. MAIN

Can keep compressed values inline if they fit on a page, though it is not a general-purpose way to shrink TOAST relations in all scenarios.

### 35.4. PLAIN

Use only when required by type/semantics; never force large text columns to PLAIN to "eliminate TOAST."

### 35.5. Measure Before/After

Test on representative data, measuring pg_total_relation_size, TOAST size, read latency, and CPU. Never select a storage strategy from an unrepresentative microbenchmark.

## 36. ALTER STORAGE and Existing Data

Example:

~~~sql
ALTER TABLE storage_lab.documents
ALTER COLUMN body SET STORAGE EXTERNAL;
~~~

### 36.1. It Is a Column Metadata Attribute

Storage strategy lives in column metadata; it is not a command that rewrites the entire relation.

### 36.2. Old Rows Do Not Change Automatically

Already-stored datums retain their prior representation. Values inserted or updated afterward use the new strategy.

### 36.3. Rewriting Requires a Separate Plan

You can purposefully update rows or use an appropriate rewrite operation, yet doing so generates WAL, locks, temporary disk usage, and system load.

### 36.4. Do Not Blindly Run Self-Assignment UPDATEs

~~~sql
UPDATE storage_lab.documents
SET body = body;
~~~

This can rewrite many rows and fire triggers/index maintenance even though logical content did not change. If converting storage or compression, evaluate rewrite options carefully and test first.

## 37. TOAST, Compression, and Backups

### 37.1. Logical Dumps

pg_dump reads logical table values, including TOASTed values, and exports them in dump format. Users never need to manually copy pg_toast files.

### 37.2. Physical Backups

Physical backups preserve the storage layout per PostgreSQL backup/restore procedures. Never copy a TOAST relation file by itself expecting to restore it independently.

### 37.3. CSV Exports

COPY TO/\copy TO exports logical values of selected columns. When exporting body, PostgreSQL decodes TOAST representations to output the requested format.

### 37.4. Compression Layers

If payloads are already ZIP/JPEG, compressing them again in TOAST yields minimal benefit. Backups often add their own compression layer; avoid estimating backup sizes directly from pg_total_relation_size.

## 38. Measuring Database Size and Top Tables

### 38.1. Database Size

~~~sql
SELECT
    current_database() AS database_name,
    pg_size_pretty(
        pg_database_size(current_database())
    ) AS database_size;
~~~

### 38.2. Top User Tables by Total Size

~~~sql
SELECT
    schemaname,
    relname AS table_name,
    pg_size_pretty(
        pg_total_relation_size(
            quote_ident(schemaname) || '.' || quote_ident(relname)
        )
    ) AS total_size,
    pg_total_relation_size(
        quote_ident(schemaname) || '.' || quote_ident(relname)
    ) AS total_bytes
FROM pg_stat_user_tables
ORDER BY total_bytes DESC
LIMIT 20;
~~~

### 38.3. Top Index Sizes

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    pg_size_pretty(
        pg_relation_size(
            quote_ident(schemaname) || '.' || quote_ident(indexname)
        )
    ) AS index_size
FROM pg_indexes
ORDER BY pg_relation_size(
    quote_ident(schemaname) || '.' || quote_ident(indexname)
) DESC
LIMIT 20;
~~~

### 38.4. Distinguish Database / Schema / Table Scopes

When reporting, explicitly state the scope:

- Database total.
- Schema total (carefully summing relations).
- Table total.
- Heap only.
- Indexes.
- TOAST.

Never add numbers that already include one another.

## 39. Tracking Growth Over Time

A single size snapshot only shows the present state. Understanding growth requires periodic snapshots.

### 39.1. Example Snapshot Table

~~~sql
CREATE TABLE storage_lab.size_snapshots (
    sampled_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    relation_name text NOT NULL,
    heap_bytes bigint NOT NULL,
    table_bytes bigint NOT NULL,
    index_bytes bigint NOT NULL,
    total_bytes bigint NOT NULL
);
~~~

### 39.2. Recording a Snapshot

~~~sql
INSERT INTO storage_lab.size_snapshots (
    relation_name, heap_bytes, table_bytes,
    index_bytes, total_bytes
)
SELECT
    'storage_lab.documents',
    pg_relation_size('storage_lab.documents'),
    pg_table_size('storage_lab.documents'),
    pg_indexes_size('storage_lab.documents'),
    pg_total_relation_size('storage_lab.documents');
~~~

### 39.3. Delta Between Two Snapshots

~~~sql
SELECT
    sampled_at,
    total_bytes,
    total_bytes - lag(total_bytes) OVER (
        ORDER BY sampled_at
    ) AS growth_bytes
FROM storage_lab.size_snapshots
WHERE relation_name = 'storage_lab.documents'
ORDER BY sampled_at;
~~~

### 39.4. Correlating with Workload

To explain growth, also record:

- Insert/update/delete rates.
- Dead tuple estimates.
- Vacuum/analyze timestamps.
- Index sizes.
- Batch import volumes.
- DDL/partition changes.
- Retention and data lifecycle.

### 39.5. Snapshots Have Overhead

Snapshot tables grow too; configure retention, partitioning, or daily/weekly rollups for long-term monitoring.

## 40. Diagnosing Growth Patterns

| Observation | Likely Cause | Investigation Direction |
| --- | --- | --- |
| Heap grows, row count steady | Update churn, dead tuples, free space | pg_stat_user_tables, vacuum, pgstattuple |
| Indexes grow rapidly | Many index entries, GIN growth, bloat | Measure each index, usage stats, query workload |
| TOAST grows rapidly | Large or frequently updated JSON/text/bytea | reltoastrelid, pg_column_size, data profile |
| Total grows while table size steady | Index growth | pg_indexes_size |
| Table size grows while heap main steady | TOAST or auxiliary forks growing | Measure TOAST relation and forks |
| Database grows while top tables flat | Catalogs, other schemas, temp/other relations | Database/schema inventory |
| File does not shrink after DELETE | Space retained for reuse | Regular VACUUM vs rewrite |
| Export smaller than table total | CSV omits index/page overhead | Distinguish logical data from physical storage |

### 40.1. Do Not Infer TOAST Just from a Small Heap

A small heap may simply mean few rows. Always check reltoastrelid and TOAST size before concluding.

### 40.2. Do Not Infer Bloat Just from Total Size

A large index may be actively used and packed with live data. Bloat requires evidence of live/dead density or index structure issues.

### 40.3. Do Not Infer a Disk Leak Just Because Size Does Not Shrink

PostgreSQL retains free pages for reuse. Steady file size after regular VACUUM is normal behavior.

## 41. Storage Parameter Notes

Several parameters affect how PostgreSQL uses storage:

- fillfactor: target page fill level for heaps/indexes.
- toast_tuple_target: target tuple size after TOAST processing on supported versions.
- Column storage strategy: PLAIN, MAIN, EXTERNAL, EXTENDED.
- Compression method: pglz, lz4 if supported by build/server.

### 41.1. Inspecting reloptions

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    c.reloptions
FROM pg_class AS c
WHERE c.oid = 'storage_lab.documents'::regclass;
~~~

### 41.2. Inspecting Column Storage

~~~sql
SELECT
    attname,
    attstorage
FROM pg_attribute
WHERE attrelid = 'storage_lab.documents'::regclass
  AND attnum > 0
  AND NOT attisdropped;
~~~

### 41.3. Storage Strategy Does Not Change Type

ALTER COLUMN ... SET STORAGE does not turn text into varchar or bytea; it adjusts how PostgreSQL stores TOAST-capable values.

### 41.4. Lower Fillfactor Does Not Always Save Disk

Fillfactor 70 can help UPDATEs yet allocates more pages on initial load. Evaluate the actual write/read ratio and page utilization.

## 42. Index Fillfactor and Page Splits

Indexes have their own fillfactor for certain access methods, such as B-tree:

~~~sql
CREATE INDEX documents_title_idx
ON storage_lab.documents (title)
WITH (fillfactor = 80);
~~~

### 42.1. Page Splits

When a B-tree leaf page runs out of space for a new key, PostgreSQL splits the page. Random insert/update patterns produce different page occupancy profiles than append-only workloads.

### 42.2. Index Fillfactor

Leaving free space on pages during index creation can reduce subsequent page splits under update-heavy workloads, though initial index size is larger.

### 42.3. REINDEX Can Change Size

Rebuilding an index from current data creates a fresh page layout, so size after REINDEX may shrink or grow depending on data and fillfactor.

### 42.4. Do Not Apply One Bloat Threshold to Every Access Method

B-tree, GIN, GiST, and BRIN have very different internal structures and maintenance behavior. Measurement tools must account for index type.

## 43. TOAST Data and GIN Indexes

A JSONB column can simultaneously be TOASTed and indexed with GIN:

~~~sql
CREATE INDEX documents_metadata_gin
ON storage_lab.documents
USING gin (metadata);
~~~

### 43.1. Two Independent Structures

- TOAST stores representations of oversized values.
- GIN stores inverted lookup structures for keys/tokens inside JSONB.

### 43.2. GIN Does Not Replace TOAST

The index helps locate matching rows, yet PostgreSQL must still retrieve the JSONB value when queries return the payload or evaluate remaining conditions.

### 43.3. Large Columns Can Inflate Both

A JSONB document with many keys can grow TOAST data and GIN entries simultaneously. Looking only at pg_table_size misses index growth; looking only at pg_indexes_size misses TOAST.

### 43.4. Choosing Operator Classes

GIN for JSONB provides operator classes such as jsonb_ops and jsonb_path_ops with trade-offs in supported operators and index size. Choose based on real workload rather than assuming one is always smaller or better.

## 44. Common Misconceptions

### Mistake 1. pg_relation_size Is the Entire Table Size

By default it measures the relation's main fork; it excludes indexes, TOAST, and other forks included in total size.

### Mistake 2. pg_table_size Includes All Indexes

No. It measures table storage/TOAST/forks; use pg_indexes_size() to view attached indexes.

### Mistake 3. pg_total_relation_size Is Only Heap + Regular Indexes

It also includes associated TOAST storage and related components per function definition.

### Mistake 4. TOAST Equals Compression

TOAST is the oversized-attribute storage mechanism; compression is one technique that may be used inside it.

### Mistake 5. Every Text Column Lives in TOAST

Small values are normally stored inline. Only oversized values/tuples trigger compression or out-of-line storage.

### Mistake 6. TOAST Stores the Entire Row

TOAST stores oversized column values, not the entire heap row.

### Mistake 7. A TOAST Index Is a Business Index

It is an internal structure to locate chunks, distinct from application-defined indexes.

### Mistake 8. More Rows Always Means Proportionally Larger Relations

Row width, compression, indexes, and dead tuples make ratios vary widely.

### Mistake 9. DELETE Shrinks Files Immediately

DELETE creates dead tuples; regular VACUUM makes space reusable without necessarily returning files to the OS.

### Mistake 10. Regular VACUUM Equals VACUUM FULL

Regular VACUUM cleans/reuses space; VACUUM FULL rewrites the relation and takes a strong lock.

### Mistake 11. REINDEX Shrinks the Heap

REINDEX only rebuilds indexes; it does not directly rewrite the table's heap or TOAST.

### Mistake 12. ANALYZE Shrinks Files

ANALYZE updates planner statistics, not relation disk footprint.

### Mistake 13. pg_column_size Equals TOAST Size

It measures datum representation, not the entire TOAST relation/index.

### Mistake 14. pg_class.reltuples Is an Exact Count

It is a statistical estimate, not equivalent to COUNT(*) at a specific snapshot.

### Mistake 15. A Large Index Means Index Bloat

An index can be large simply because of the entries/keys it stores. Measure density, usage, and workload.

### Mistake 16. More Indexes Always Make a Table Faster

Indexes accelerate reads at the cost of higher write overhead, storage, and maintenance.

### Mistake 17. A Small JSONB Update Writes Only a Few Bytes

Operations producing a new JSONB result can incur heavy costs, including TOAST rewrites and GIN index maintenance.

### Mistake 18. EXTERNAL Always Saves CPU and Disk

Since it skips compression, it can avoid decompression CPU while increasing disk footprint.

### Mistake 19. Changing SET STORAGE Rewrites All Data

No; strategy changes primarily apply to values written or updated afterward.

### Mistake 20. Changing COMPRESSION Recompresses Every Row Immediately

No. A controlled rewrite/update plan is required to convert existing representations.

### Mistake 21. pg_total_relation_size(parent partition) Is the Only Way to Measure Partitions

A partitioned parent table has no heap like an ordinary table. Measure leaf partitions and sum explicitly to avoid omissions or double counting.

### Mistake 22. WAL Is Inside pg_total_relation_size

WAL is separate storage, not part of a table relation's size.

### Mistake 23. A CSV Export Equals Table Total Size

A CSV holds selected logical data, lacking physical page/tuple/index/TOAST overhead.

### Mistake 24. Deleting Relation Files via the OS Reclaims Disk Safely

That corrupts the database. Always use controlled PostgreSQL commands.

## 45. Practice Exercises

Exercises are based on the storage_lab schema or SQL examples in this lesson. Operations such as VACUUM FULL, REINDEX, and storage strategy changes should be tested in a lab database, never in production solely for observation.

### Exercise 1. Four Size Functions

Distinguish pg_relation_size, pg_table_size, pg_indexes_size, and pg_total_relation_size.

### Exercise 2. Main Fork

If you call pg_relation_size('app.orders') without specifying a fork, what does PostgreSQL measure?

### Exercise 3. Heap and Indexes

Why can pg_table_size be smaller than pg_total_relation_size?

### Exercise 4. TOAST

What does TOAST stand for and what storage problem does it solve?

### Exercise 5. Varlena

Name four PostgreSQL data types commonly eligible for TOAST.

### Exercise 6. External Storage

What does it mean when a heap tuple holds an external TOAST pointer?

### Exercise 7. Chunks

Why can a large TOAST value be split into multiple chunks?

### Exercise 8. TOAST Index

What purpose does the TOAST index serve?

### Exercise 9. PLAIN

Does the PLAIN storage strategy allow compression or externalization?

### Exercise 10. EXTENDED

Which two behaviors does EXTENDED support?

### Exercise 11. MAIN

How does MAIN differ from EXTENDED when deciding to externalize?

### Exercise 12. EXTERNAL

Does EXTERNAL compress values?

### Exercise 13. Compression

Why can a long repetitive string occupy less storage than octet_length()?

### Exercise 14. pg_column_size

Why should you not sum pg_column_size() across all rows and treat that as total relation size?

### Exercise 15. TOAST Relation

Write SQL to look up reltoastrelid of storage_lab.documents and measure its pg_total_relation_size.

### Exercise 16. Index List

Write SQL to list every index on storage_lab.documents along with its byte size.

### Exercise 17. Forks

Name the main, fsm, vm, and init forks; what does each serve?

### Exercise 18. MVCC

Why can UPDATEs cause a heap to grow even when visible row count stays constant?

### Exercise 19. DELETE

Why does deleting many rows not necessarily shrink the relation file immediately?

### Exercise 20. VACUUM

How does regular VACUUM differ from VACUUM FULL?

### Exercise 21. REINDEX

Does REINDEX shrink the heap table?

### Exercise 22. ANALYZE

Does ANALYZE modify relation data or planner statistics?

### Exercise 23. Index Size

Give three reasons why a JSONB GIN index can be larger than a primary key B-tree index.

### Exercise 24. HOT

What are two key conditions enabling an UPDATE to become a HOT update?

### Exercise 25. Fillfactor

Why can a lower fillfactor assist HOT updates while increasing initial disk usage?

### Exercise 26. Catalog

What does pg_class.reltoastrelid tell you?

### Exercise 27. attstorage

What property does pg_attribute.attstorage record?

### Exercise 28. Partitioning

Why measure leaf partitions rather than treating a relkind='p' parent like a regular heap table?

### Exercise 29. WAL

Is WAL included in pg_total_relation_size('table')?

### Exercise 30. pg_stat_user_tables

Write a query viewing n_live_tup, n_dead_tup, and last_autovacuum for the storage_lab schema.

### Exercise 31. pg_statio

Which two columns report TOAST block reads/hits?

### Exercise 32. pgstattuple

What useful information can the pgstattuple extension provide when investigating bloat?

### Exercise 33. JSONB

Why can a small change inside JSONB generate significant TOAST and GIN index overhead?

### Exercise 34. SET STORAGE

After ALTER COLUMN body SET STORAGE EXTERNAL, are existing values automatically rewritten?

### Exercise 35. Compression

Why does changing the compression method not automatically recompress every row?

### Exercise 36. Measuring Sizes

Write a query displaying heap main, table storage, indexes, and total for storage_lab.documents.

### Exercise 37. Index Ratio

Write an expression computing index size as a percentage of total size.

### Exercise 38. Growth

Name at least four types of context to record alongside size snapshots to explain growth.

### Exercise 39. Query Projection

Why is SELECT document_id, title usually much lighter than SELECT * on tables with large TOASTed body/payload columns?

### Exercise 40. Choosing an Investigation Path

A table's total size grows rapidly while its heap main fork stays steady. Outline the order of components to investigate.

## 46. Reference Solutions

### Exercises 1–3. Size Functions

- pg_relation_size: size of the specified relation/fork, defaulting to main.
- pg_table_size: table storage, including TOAST and auxiliary forks per PostgreSQL calculation.
- pg_indexes_size: indexes attached to the table.
- pg_total_relation_size: table storage plus indexes.

Total is larger than table when the table has indexes.

### Exercises 4–8. TOAST

TOAST stands for *The Oversized-Attribute Storage Technique*, handling large variable-length values via compression and/or external storage. Chunks reside in the TOAST table; the TOAST index locates them; the heap tuple holds a pointer when externalized.

### Exercises 9–12. Storage Strategies

| Strategy | Compression | External |
| --- | --- | --- |
| PLAIN | No | No |
| MAIN | Yes | Only if needed to fit tuple |
| EXTENDED | Yes | Yes |
| EXTERNAL | No | Yes |

### Exercises 13–14. Logical and Physical Size

Repetitive strings compress heavily, so the datum representation is smaller than logical byte length. Summing datum sizes omits page/tuple/line-pointer overhead, free space, dead tuples, indexes, TOAST indexes, and forks.

### Exercise 15. TOAST

~~~sql
SELECT
    c.reltoastrelid::regclass AS toast_table,
    pg_total_relation_size(c.reltoastrelid) AS toast_bytes
FROM pg_class AS c
WHERE c.oid = 'storage_lab.documents'::regclass
  AND c.reltoastrelid <> 0;
~~~

### Exercise 16. Index List

~~~sql
SELECT
    indexrelid::regclass AS index_name,
    pg_relation_size(indexrelid) AS bytes
FROM pg_index
WHERE indrelid = 'storage_lab.documents'::regclass
ORDER BY bytes DESC;
~~~

### Exercise 17. Forks

main holds primary data; fsm tracks free-space estimates; vm tracks visibility/all-frozen flags; init restores the initial empty state of unlogged relations.

### Exercises 18–19. MVCC

UPDATE normally creates a new tuple version and keeps the old version until no snapshot needs it. DELETE marks tuples invisible; VACUUM cleans/reuses space later without necessarily returning file space to the OS.

### Exercises 20–22. Maintenance

Regular VACUUM cleans/reuses dead tuples; VACUUM FULL rewrites the relation with a strong lock. REINDEX rebuilds indexes without rewriting the heap. ANALYZE updates planner statistics.

### Exercise 23. GIN Size

GIN can index numerous JSON keys/tokens per row, storing posting lists and page metadata; it is not one entry per row like a primary key B-tree.

### Exercises 24–25. HOT and Fillfactor

HOT can apply when no indexed columns change and the page has enough space for the new tuple (among other technical conditions). Lower fillfactor leaves free room on pages, aiding updates while reducing initial tuple density.

### Exercises 26–27. Catalog

reltoastrelid is the OID of the auxiliary TOAST relation; attstorage records the column's storage strategy such as PLAIN/MAIN/EXTERNAL/EXTENDED.

### Exercises 28–29. Partitions and WAL

A partitioned parent is a metadata relation while data lives in leaf partitions. WAL resides in pg_wal and is excluded from a table's total size.

### Exercise 30. Table Stats

~~~sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum
FROM pg_stat_user_tables
WHERE schemaname = 'storage_lab';
~~~

### Exercise 31. TOAST I/O

toast_blks_read and toast_blks_hit in pg_statio_user_tables.

### Exercise 32. pgstattuple

Can report table length, live tuple count/length, dead tuple count/length, and free space; scans have I/O cost and require appropriate privileges/extension.

### Exercise 33. JSONB

JSONB is a single datum with its own representation; modifications can produce a new value, new TOAST value, and new GIN entries, causing heap/TOAST/index write amplification.

### Exercises 34–35. Storage/Compression Change

No. Changing storage strategy or compression affects values written/updated afterward; existing data requires a controlled rewrite/update plan to convert representations.

### Exercise 36. Size Breakdown

~~~sql
SELECT
    pg_relation_size('storage_lab.documents') AS heap_main,
    pg_table_size('storage_lab.documents') AS table_bytes,
    pg_indexes_size('storage_lab.documents') AS index_bytes,
    pg_total_relation_size('storage_lab.documents') AS total_bytes;
~~~

### Exercise 37. Index Ratio

~~~sql
SELECT round(
    100.0 * pg_indexes_size('storage_lab.documents')
    / NULLIF(
        pg_total_relation_size('storage_lab.documents'), 0
    ),
    2
) AS index_percent;
~~~

### Exercise 38. Growth Context

Examples: live/dead tuple estimates, insert/update/delete rates, vacuum/analyze timestamps, index sizes, TOAST size, partition sizes, batch imports, and workload changes.

### Exercise 39. Projection

When oversized columns are omitted from the SELECT list, PostgreSQL generally avoids fetching/detoasting them for the result, cutting I/O, decompression CPU, and bytes returned to clients.

### Exercise 40. Investigation

Measure pg_indexes_size first and list individual indexes; inspect the TOAST relation and auxiliary forks; review update/dead tuple stats, index growth, partition changes, and maintenance history. Only then conclude which component is growing and choose the right action.

## 47. Quick Reference Table

| Need | Tool |
| --- | --- |
| Measure main heap fork | pg_relation_size(table) |
| Measure a specific fork | pg_relation_size(table, 'fsm') or 'vm' |
| Measure table + TOAST | pg_table_size(table) |
| Measure table's indexes | pg_indexes_size(table) |
| Measure total table + indexes | pg_total_relation_size(table) |
| Format bytes | pg_size_pretty(bytes) |
| Measure entire database | pg_database_size(db) |
| Check TOAST OID | pg_class.reltoastrelid |
| Check storage strategy | pg_attribute.attstorage |
| Check compression metadata | pg_attribute.attcompression on supported versions |
| Measure datum representation | pg_column_size(value) |
| Measure text logical bytes | octet_length(text) |
| Check datum compression method | pg_column_compression(value) on supported versions |
| List index relations | pg_index.indexrelid |
| View index definition | pg_get_indexdef() |
| Check dead tuple estimate | pg_stat_user_tables.n_dead_tup |
| Check TOAST I/O | pg_statio_user_tables.toast_blks_* |
| Measure live/dead/free space deeply | pgstattuple extension |
| Clean dead tuples / reuse | VACUUM |
| Rewrite heap to shrink | VACUUM FULL or suitable rewrite tool |
| Rebuild indexes | REINDEX |
| Update planner stats | ANALYZE |
| View relation file path | pg_relation_filepath() |
| View filenode | pg_relation_filenode() |
| Measure leaf partitions | pg_partition_tree() + size functions |

## 48. Checklist for Investigating Unexpected Table Growth

1. **Define the exact scope:** database, schema, table, partition, heap, or total?
2. Record raw byte sizes with PostgreSQL functions, not only pg_size_pretty.
3. Separate pg_relation_size, pg_table_size, pg_indexes_size, and pg_total_relation_size.
4. Check whether the table has a reltoastrelid.
5. Measure the TOAST relation separately and avoid double-counting TOAST in table size.
6. List every index, its access method, and its definition.
7. Check whether indexes use GIN/INCLUDE/expressions or wide keys.
8. Inspect n_live_tup, n_dead_tup, and update/delete churn.
9. Check last vacuum/analyze timestamps and autovacuum behavior.
10. Check for long-running transactions/replication slots retaining dead tuples.
11. Check FSM/VM forks if table size grows while heap main stays flat.
12. Compare logical payload (octet_length) with datum representation (pg_column_size).
13. Check storage strategies/compression on varlena columns.
14. Identify large or frequently updated JSONB/text/bytea payloads.
15. Check TOAST I/O and whether queries accidentally use SELECT *.
16. Inspect partition sizes without double-counting parent and leaves.
17. Review fillfactor and HOT update patterns.
18. Verify index usage and query plans before dropping any index.
19. If bloat is suspected, use appropriate measurement tools such as pgstattuple and evaluate scan cost.
20. Choose VACUUM, REINDEX, or rewrite targeting the specific affected relation.
21. Assess disk headroom and temporary space before VACUUM FULL/rewrites.
22. Assess locks, replication lag, WAL, and backups before maintenance.
23. Never delete or move relation files using OS commands.
24. Capture periodic snapshots to observe trends rather than a single point in time.
25. Re-measure after changes using the exact same scope and methodology.

## 49. Summary

A PostgreSQL table's size is the sum of multiple physical structures:

- **Heap** stores tuples and is shaped by page layout, MVCC versions, dead tuples, free space, and fillfactor.
- **Indexes** are separate relations; index count, access methods, and indexed content can expand total footprint substantially.
- **TOAST** handles oversized varlena values via compression and/or external storage in an auxiliary relation alongside a TOAST index.
- **FSM/VM/init forks** and auxiliary metadata also contribute to table storage.

When measuring, distinguish pg_relation_size() (default main fork), pg_table_size() (table storage with TOAST/forks), pg_indexes_size() (indexes), and pg_total_relation_size() (overall total). For deeper diagnosis, combine pg_class.reltoastrelid, pg_attribute.attstorage, pg_column_size(), pg_stat_user_tables, pg_statio_user_tables, and tools like pgstattuple when needed.

**Never guess root causes from a single total number.** Heap growth, index growth, TOAST growth, and dead tuple buildup are distinct phenomena requiring different remedies. Regular VACUUM enables space reuse; VACUUM FULL rewrites the heap; REINDEX rebuilds indexes; ANALYZE updates statistics. Choose the right tool only after measuring and assessing locks, WAL, disk headroom, replication, and workload.

A reliable workflow is **measure each component → identify the data types/workload driving growth → check MVCC/TOAST/index behavior → apply maintenance to the right relation → re-measure after changes**. That ensures storage decisions are grounded in what PostgreSQL actually stores on disk rather than row counts or CSV export sizes.
