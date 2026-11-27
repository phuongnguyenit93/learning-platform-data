# TOAST and Large Value Storage in PostgreSQL

A PostgreSQL row can contain very large values: long text, JSON, arrays, or binary data. If the entire value always remained inside the main table's tuple, the system would hit tuple size limits and suffer degraded storage efficiency. PostgreSQL solves this problem with **TOAST — The Oversized-Attribute Storage Technique**.

TOAST allows PostgreSQL to automatically:

- Compress values that are compressible.
- Move oversized values out to an auxiliary storage relation.
- Split values into multiple chunks.
- Keep a small reference inside the main tuple.
- Fetch and reconstruct the value when an SQL query needs it.

Applications still query the column as usual:

~~~sql
SELECT document_body
FROM documents
WHERE document_id = 10;
~~~

Even though most of the content may reside outside the main heap table, PostgreSQL returns the full SQL value. TOAST is an internal mechanism, not a file upload API or message store.

The lesson **"TOAST and Large Value Storage"**, belonging to the **Storage** chapter of the **Database Engine Relational PostgreSQL** module, covers tuple/page limits, inline and out-of-line storage, compression, storage strategies, catalog and size inspection, MVCC/vacuum/WAL, indexes, comparisons with Large Objects and object storage, along with SQL and Java examples.

---

## 1. Why Does PostgreSQL Need TOAST?

PostgreSQL stores heap rows in data pages of a fixed build-time size, typically **8 KB**. A tuple cannot grow arbitrarily beyond what a page can store.

Example:

~~~sql
CREATE TABLE articles (
    article_id BIGINT PRIMARY KEY,
    title TEXT,
    body TEXT
);
~~~

A 200 KB body cannot always be kept inline in the main tuple if it pushes the tuple past the storage threshold.

If every column had to reside on the same page, large values would reduce the number of rows per page, cause queries needing only id/title to suffer from tuple width, and increase update costs.

TOAST lets PostgreSQL **keep oversized data separate from the main tuple**, so tuples in the heap stay compact.

## 2. Tuple Size and the TOAST Threshold

With the common 8 KB page configuration, TOAST typically triggers when a tuple exceeds roughly **2 KB**. This is a typical default threshold/target, not a maximum size limit for TEXT or BYTEA.

What PostgreSQL aims to achieve is:

- The main tuple is small enough to fit on a heap page.
- Large values are compressed when beneficial.
- Eligible values are moved out-of-line.
- Remaining inline data fits within the storage target.

### 2.1. 2 KB Is Not a Single-Column Limit

A text value can be much larger. TOAST handles storage when the data type and storage strategy allow. Conversely, a 2 KB value is not necessarily moved out-of-line every time; the decision also depends on total tuple size and other columns.

## 3. Data Types Eligible for TOAST

TOAST primarily applies to variable-length types, commonly called varlena in PostgreSQL's implementation.

Examples:

- `text` and `varchar`.
- `bytea`.
- `json` and `jsonb`.
- Arrays.
- Certain composite types with a varlena representation.

Fixed-length types such as `integer`, `bigint`, and `boolean` are not TOASTed in the way varlena values are.

### 3.1. TOAST Operates Per Attribute

A tuple can consist of:

~~~text
id           -> inline
created_at   -> inline
title        -> inline
body         -> external TOAST value
thumbnail    -> inline or compressed
metadata     -> inline/compressed/external
~~~

The entire row is not moved out-of-line all at once. PostgreSQL selects toastable attributes to reduce tuple size.

## 4. Inline, Compressed, and Out-of-Line

**Inline:** the value sits directly inside the heap tuple.

~~~text
Heap tuple
+----------------------------------+
| id | title | body value          |
+----------------------------------+
~~~

**Compressed inline:** the value is compressed yet remains inside the tuple.

~~~text
Heap tuple
+----------------------------------+
| id | title | compressed body    |
+----------------------------------+
~~~

**Out-of-line:** the main tuple holds an internal reference to the value stored in an auxiliary relation.

~~~text
Main heap tuple
+----------------------------------+
| id | title | TOAST pointer       |
+----------------------------------+
                 |
                 v
TOAST relation
+-------------------------------+
| chunk 0                       |
| chunk 1                       |
| chunk 2                       |
| ...                           |
+-------------------------------+
~~~

When a query needs the full value, PostgreSQL fetches the necessary chunks and reconstructs the datum.

## 5. TOAST Relation and Chunks

A table with toastable columns can have a PostgreSQL-managed **TOAST table**. This auxiliary relation stores data slices that have been moved out-of-line.

The internal structure typically includes fields such as:

- `chunk_id`: identifier for the TOASTed value.
- `chunk_seq`: sequence number of the chunk.
- `chunk_data`: bytes of the chunk.

An internal index supports looking up chunks by value ID and sequence. The relation name is derived from the main table's OID and normally resides in the system schema `pg_toast`.

### 5.1. Do Not Modify the TOAST Table Directly

Never INSERT, UPDATE, or DELETE chunk rows using application SQL. Never fabricate pointers or hard-code internal relation names. PostgreSQL manages creating, reading, updating, and reclaiming TOAST values alongside the main table.

## 6. TOAST Pointer

When a value is stored out-of-line, the main tuple contains a small representation called an external TOAST pointer. The pointer carries the metadata PostgreSQL needs to locate the value in the associated relation.

Applications do not need to know the binary format of the pointer. When running:

~~~sql
SELECT body
FROM articles;
~~~

PostgreSQL transparently retrieves and returns the normal SQL value.

A pointer is not a business ID, not a file path, and should never be serialized as application data.

## 7. Chunking

An out-of-line value is divided into multiple chunks:

~~~text
value_id = 5001

chunk_seq 0 -> first part
chunk_seq 1 -> next part
chunk_seq 2 -> next part
...
chunk_seq N -> final part
~~~

Chunk size is an implementation detail depending on page size and internal structure. Applications should never hard-code chunk size.

Internal chunking does not mean a SELECT automatically streams piece by piece. If the application SELECTs the entire column, the value may have to be reconstructed and transmitted over the protocol.

## 8. Compression and Out-of-Line Storage

TOAST combines two techniques:

1. **Compression:** reduces the byte count of a value.
2. **Out-of-line storage:** moves the value to an auxiliary relation.

Repetitive text usually compresses well:

~~~sql
SELECT repeat('PostgreSQL storage ', 10000);
~~~

Already-compressed data such as JPEG, MP4, ZIP, or ciphertext usually does not shrink appreciably when compressed further.

### 8.1. Not Every TOAST Value Is Compressed

PostgreSQL may attempt compression per the storage strategy, yet if compression yields insufficient savings, the value may be stored external uncompressed. Never assume every out-of-line value is compressed.

## 9. The Four Storage Strategies

PostgreSQL allows configuring the storage strategy per toastable column:

| Strategy | Compression | Out-of-line | Characteristics |
|---|---|---|---|
| `PLAIN` | No | No | Always inline; unsuitable for large values |
| `EXTENDED` | Yes | Yes | Common default; compresses then moves out-of-line if needed |
| `EXTERNAL` | No | Yes | Stores out-of-line without compression |
| `MAIN` | Yes | Yes, when more necessary | Prefers keeping inline after compression; out-of-line as last resort |

### 9.1. PLAIN

`PLAIN` disallows both compression and out-of-line storage. With large values, INSERT/UPDATE can fail because the tuple cannot fit on a page.

Never set PLAIN arbitrarily on large TEXT/BYTEA columns.

### 9.2. EXTENDED

This is the common choice for toastable types. PostgreSQL can compress and/or move the value out-of-line as needed to keep the tuple within size targets.

Usually the sensible default for text, JSONB, arrays, and bytea.

### 9.3. EXTERNAL

`EXTERNAL` allows out-of-line storage without compression. Certain substring/slice reads on text/bytea can avoid decompressing the entire compressed value, at the trade-off of higher storage usage.

EXTERNAL still stores inside PostgreSQL, not S3 or an external filesystem.

### 9.4. MAIN

`MAIN` permits compression yet prioritizes keeping data inline. PostgreSQL only moves the value out-of-line when strictly necessary for the tuple to fit.

This is a less common strategy in typical application design.

## 10. Changing the Storage Strategy

You can alter a column's storage strategy:

~~~sql
ALTER TABLE articles
ALTER COLUMN body
SET STORAGE EXTENDED;
~~~

Or:

~~~sql
ALTER TABLE articles
ALTER COLUMN body
SET STORAGE EXTERNAL;
~~~

The setting applies to future storage writes as applicable; **it does not automatically rewrite all existing values**.

If the table already holds millions of values compressed under the old strategy, ALTER COLUMN SET STORAGE does not automatically convert all existing data.

## 11. Compression Methods

Common TOAST compression methods:

- `pglz`: traditional method, always available in PostgreSQL.
- `lz4`: available if PostgreSQL was built with LZ4 support.

Starting in PostgreSQL 14, you can choose a compression method per column:

~~~sql
ALTER TABLE articles
ALTER COLUMN body
SET COMPRESSION lz4;
~~~

Only use LZ4 if the server supports it; otherwise, the command returns an error.

### 11.1. Storage Strategy Differs from Compression Method

- `SET STORAGE EXTENDED` governs whether a column can be compressed and/or stored out-of-line.
- `SET COMPRESSION lz4` selects the compression algorithm when a value is compressed.

A column can use EXTENDED with either pglz or LZ4.

### 11.2. default_toast_compression

~~~sql
SHOW default_toast_compression;
~~~

This GUC selects the default method for columns without a specific override. The default is typically `pglz`; LZ4 depends on the build.

Do not confuse TOAST compression with WAL compression.

## 12. Changing Compression Does Not Rewrite Old Data

~~~sql
ALTER TABLE articles
ALTER COLUMN body
SET COMPRESSION lz4;
~~~

changes the method for values stored in the future. Existing values do not automatically decompress and recompress merely because of ALTER COLUMN.

To convert existing representations, you need a controlled rewrite/UPDATE or an appropriate table rewrite operation.

Bulk rewrites can generate many tuple versions, increase WAL, I/O, replication lag, temporary disk usage, and vacuum pressure. Never UPDATE an entire production table just to test a compression method.

## 13. toast_tuple_target

The table storage parameter `toast_tuple_target` controls the target tuple size after TOAST processing.

~~~sql
ALTER TABLE articles
SET (toast_tuple_target = 4096);
~~~

The default is typically around 2 KB on standard configurations. Valid ranges depend on internal limits and server page size.

- A lower target can push more data out-of-line sooner.
- A higher target can keep more data inline.
- Actual impact depends on the number of toastable columns, compressibility, and workload.

This is not a parameter to "increase to hold bigger files"; it controls the inline tuple target.

### 13.1. Difference from fillfactor

| Parameter | Purpose |
|---|---|
| `toast_tuple_target` | Target tuple size after TOAST |
| `fillfactor` | Page fill percentage and space reserved for UPDATEs |

These two parameters address completely different storage concerns.

## 14. Creating the Lab Table

~~~sql
CREATE SCHEMA toast_lab;

CREATE TABLE toast_lab.documents (
    document_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT,
    raw_data BYTEA,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);
~~~

The table includes common toastable types: TEXT, BYTEA, and JSONB.

### 14.1. Inserting Large Data

~~~sql
INSERT INTO toast_lab.documents (
    title, body, raw_data, metadata
)
VALUES (
    'TOAST demonstration',
    repeat('PostgreSQL TOAST storage technique. ', 5000),
    convert_to(repeat('ABCD', 20000), 'UTF8'),
    jsonb_build_object(
        'category', 'database',
        'description', repeat('large json value ', 2000),
        'tags', jsonb_build_array('postgresql', 'storage')
    )
);
~~~

Repetitive data typically compresses well. Exact stored sizes depend on build and internal representation.

## 15. Measuring Logical Bytes and Storage Size

~~~sql
SELECT
    document_id,
    octet_length(body) AS body_logical_bytes,
    pg_column_size(body) AS body_storage_bytes,
    octet_length(raw_data) AS raw_logical_bytes,
    pg_column_size(raw_data) AS raw_storage_bytes,
    pg_column_size(metadata) AS metadata_storage_bytes
FROM toast_lab.documents;
~~~

- `octet_length`: byte count of the text/bytea value in SQL representation.
- `pg_column_size`: storage size of the datum, which can reflect compression.

`pg_column_size` is not the total size of the entire TOAST relation; it excludes all chunks, indexes, and overhead across other rows.

## 16. Inspecting the Compression Method

On PostgreSQL 14+:

~~~sql
SELECT
    document_id,
    pg_column_compression(body) AS body_compression,
    pg_column_compression(raw_data) AS raw_compression,
    pg_column_compression(metadata) AS metadata_compression
FROM toast_lab.documents;
~~~

`pg_column_compression` returns the compression method name of a compressed datum; it returns NULL if the datum is not compressed in its stored representation.

NULL does not mean data is missing. The value may be small, inline, or external uncompressed.

If an older server lacks this function, omit it from the query.

## 17. Inspecting the TOAST Relation via pg_class

Catalog field `pg_class.reltoastrelid` links the main table to its TOAST relation.

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    CASE
        WHEN c.reltoastrelid = 0 THEN NULL
        ELSE c.reltoastrelid::regclass::TEXT
    END AS toast_relation,
    CASE
        WHEN c.reltoastrelid = 0 THEN 0
        ELSE pg_relation_size(c.reltoastrelid::regclass)
    END AS toast_relation_bytes
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'toast_lab'
  AND c.relname = 'documents';
~~~

Use the OID association rather than hard-coding TOAST relation names.

A table with toastable columns can have an auxiliary relation even when it currently holds no out-of-line values. The existence of a TOAST relation does not prove all large values are stored out-of-line.

## 18. Functions for Measuring Relation Size

| Function | Scope |
|---|---|
| `pg_relation_size(table)` | Size of a specific relation/fork, usually the main heap |
| `pg_table_size(table)` | Table and auxiliary components such as TOAST/FSM/VM, excluding indexes |
| `pg_indexes_size(table)` | Total size of indexes |
| `pg_total_relation_size(table)` | Total of table, TOAST, and indexes |
| `pg_size_pretty(bytes)` | Human-readable byte formatting |

Example:

~~~sql
SELECT
    pg_size_pretty(
        pg_relation_size('toast_lab.documents'::regclass)
    ) AS heap_size,
    pg_size_pretty(
        pg_table_size('toast_lab.documents'::regclass)
    ) AS table_size,
    pg_size_pretty(
        pg_indexes_size('toast_lab.documents'::regclass)
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size('toast_lab.documents'::regclass)
    ) AS total_size;
~~~

Looking only at pg_relation_size of the main heap can miss a substantial footprint residing in the TOAST relation.

## 19. Detoasting on Read

When an expression needs the full value, PostgreSQL performs **detoasting**: fetching the compressed/out-of-line value, decompressing it, and reconstructing the datum.

~~~sql
SELECT body
FROM toast_lab.documents
WHERE document_id = 1;
~~~

The client receives body as ordinary text.

A query reading only ID/title may avoid loading body. Therefore, specify explicit projections:

~~~sql
SELECT document_id, title, created_at
FROM toast_lab.documents
ORDER BY document_id;
~~~

Avoid SELECT * in list endpoints if the UI does not need large content.

### 19.1. ORMs May Load Blobs Unintentionally

A JPA/Hibernate entity with a body/bytea field can be fetched alongside metadata if mapping or queries are poorly structured. Inspect the actual SQL generated by the ORM, especially on list endpoints.

## 20. TOAST and MVCC

PostgreSQL uses MVCC: UPDATE creates a new row version rather than overwriting every byte of the old version directly.

For a row containing a TOAST value:

- The new version can continue referencing an unchanged large value.
- If the large value changes, PostgreSQL creates a new TOAST value/chunks.
- The old version must be retained as long as an active snapshot might still read it.
- Vacuum reclaims unreferenced data when safe.

This explains why repeatedly updating a large TEXT/BYTEA column can inflate storage and WAL.

### 20.1. Updating Metadata Does Not Necessarily Rewrite the Blob

If body is unchanged, PostgreSQL can reuse the existing TOAST representation. Do not rely on this implementation detail as a substitute for measuring workload behavior.

## 21. VACUUM and TOAST

A TOAST relation has its own data/versions and is managed by PostgreSQL alongside appropriate vacuum/autovacuum mechanisms.

After many UPDATEs/DELETEs of large values:

- Old tuple versions become dead tuples once no snapshot needs them.
- Unreferenced TOAST chunks can be reclaimed.
- VACUUM makes space reusable.

~~~sql
VACUUM (VERBOSE) toast_lab.documents;
~~~

### 21.1. VACUUM Does Not Mean the File Shrinks Immediately

Regular VACUUM makes space reusable within the relation; it does not necessarily return file space to the filesystem.

`VACUUM FULL` rewrites the table and can shrink the file, but requires a strong lock, temporary disk space, and time. Never run it casually just to "clean TOAST."

## 22. Autovacuum and Long Transactions

If a transaction holds an old snapshot, PostgreSQL cannot yet clean up row versions and TOAST values still needed by that snapshot.

Inspect transactions:

~~~sql
SELECT
    pid,
    usename,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

If a workload updates large blobs frequently, monitor dead tuples, vacuum activity, TOAST relation growth, long-running snapshots, and replication slots/WAL retention.

## 23. TOAST and WAL

INSERTing/UPDATing a large value can write many TOAST chunks and generate corresponding WAL. Consequences:

- WAL volume increases.
- Replication must ship more bytes.
- Backup/archive volume increases.
- Logical decoding workloads can consume significant resources.
- Frequent blob updates generate substantial I/O.

### 23.1. TOAST Compression Differs from wal_compression

TOAST compression stores the datum using the column's compression method. `wal_compression` is a separate setting governing full-page images in WAL per PostgreSQL support. Do not confuse the two mechanisms.

## 24. TOAST and Indexes

TOAST handles storage of values inside heap rows. Indexes have their own tuple/index-entry size limits and **are not automatically TOASTed** like heap columns.

A B-tree index on very large text can hit index tuple size limits. Never assume that because a column is toastable, the entire value can be indexed without limit.

Choose by query pattern:

- Metadata/ID: B-tree on small keys.
- Full-text search: GIN with tsvector.
- JSONB operators: GIN with the appropriate jsonb operator class.
- Fuzzy string search: consider pg_trgm.
- Large BYTEA: index a checksum/metadata rather than the entire payload.

Indexing large content increases storage, WAL, and write cost; create such indexes only when the workload requires them.

## 25. BYTEA with TOAST

~~~sql
CREATE TABLE toast_lab.attachments (
    attachment_id BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    content BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);
~~~

BYTEA is SQL's binary type, suited for data that belongs with the row. Large values can be TOASTed automatically.

Advantages:

- INSERT/UPDATE happens in the same transaction as metadata.
- GRANT and RLS apply at the row/table level.
- Simple SQL.
- Table backups include the values.

Disadvantages:

- SELECTing the whole BYTEA transfers the full payload.
- Updating large payloads increases TOAST/WAL churn.
- No offset-based random access API like Large Objects.
- Does not inherently provide CDN or object lifecycle features.

## 26. What Are Large Objects?

PostgreSQL has a separate subsystem called **Large Objects (LO)**. An object is identified by an OID; applications typically store the OID in a reference table.

~~~sql
CREATE TABLE toast_lab.file_refs (
    file_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    filename TEXT NOT NULL,
    object_oid OID NOT NULL
);
~~~

Large Objects are managed in separate catalog relations, normally:

- `pg_largeobject_metadata`: metadata, ownership, and privileges.
- `pg_largeobject`: content split into pages/chunks.

### 26.1. RLS on the Reference Table Does Not Replace LO Privileges

A file_refs row hidden by RLS does not automatically revoke access to the Large Object via other paths. Large Objects have their own ACLs. Protect both the reference table and object permissions/lifecycle.

## 27. How TOAST and Large Objects Differ

| Criterion | TOAST | Large Objects |
|---|---|---|
| Goal | Large column values | Separate binary objects |
| Access | SQL as TEXT/BYTEA/JSONB | OID and LO API |
| Relationship to row | Value belongs to the row | Row usually holds the OID |
| Chunking | Automatic internal handling | Managed by the LO subsystem |
| Partial read/write | Depends on type/operators | Offset access supported via API |
| Permissions | Table/column and RLS | Separate large object privileges |
| Lifecycle | Tied to row version/MVCC | Must manage unlink/references |
| Backup | Travels with table data | Must ensure dumps include LOs |

TOAST generally fits best when data is a column value belonging to a row with simple SQL access. Large Objects fit when partial read/write or streaming of large objects is needed.

## 28. Creating a Large Object in the Lab

PostgreSQL provides functions such as `lo_create`, `lo_put`, `lo_get`, and `lo_unlink`.

~~~sql
DO $$
DECLARE
    v_oid OID;
BEGIN
    v_oid := lo_create(0);

    PERFORM lo_put(
        v_oid,
        0,
        convert_to('Large object payload', 'UTF8')
    );

    INSERT INTO toast_lab.file_refs (
        filename,
        object_oid
    )
    VALUES ('example.txt', v_oid);
END;
$$;
~~~

This is a lab database example. LO operations require an appropriate transaction.

### 28.1. Reading Content

~~~sql
SELECT
    filename,
    convert_from(lo_get(object_oid), 'UTF8') AS content
FROM toast_lab.file_refs;
~~~

Only use convert_from when the content is genuinely UTF-8 text. Never cast arbitrary binary files to text.

### 28.2. Partial Read

~~~sql
SELECT lo_get(object_oid, 0, 8)
FROM toast_lab.file_refs;
~~~

The result is a byte slice; it may not be a valid UTF-8 string if sliced in the middle of a multi-byte character.

## 29. Deleting a Large Object Properly

Deleting the referencing row does not automatically unlink the object. Verify no other valid references remain:

~~~sql
BEGIN;

SELECT lo_unlink(object_oid)
FROM toast_lab.file_refs
WHERE filename = 'example.txt';

DELETE FROM toast_lab.file_refs
WHERE filename = 'example.txt';

COMMIT;
~~~

If multiple rows reference the same OID, unlinking will break remaining references.

### 29.1. Orphaned Large Objects

An object created whose reference is rolled back or improperly deleted can become an orphan. The `vacuumlo` (contrib) utility helps find/remove unreferenced Large Objects within its check scope. In production, back up and review schema references before cleanup.

## 30. Large Object Privileges

Large Objects have their own privileges. Example:

~~~sql
GRANT SELECT
ON LARGE OBJECT 12345
TO app_reader;
~~~

The OID must belong to an existing object and roles must be properly managed. Do not grant broad access without considering who can discover OIDs and how applications access them.

RLS on the reference table does not replace the Large Object ACL.

## 31. Large Objects and JDBC Streaming

pgJDBC provides a Large Object API via:

- `PGConnection`.
- `LargeObjectManager`.
- `LargeObject`.

LO operations require a transaction. Example shape:

~~~java
import java.io.InputStream;
import java.sql.Connection;

import org.postgresql.PGConnection;
import org.postgresql.largeobject.LargeObject;
import org.postgresql.largeobject.LargeObjectManager;

public long store(Connection connection, InputStream input)
        throws Exception {

    boolean oldAutoCommit = connection.getAutoCommit();

    try {
        connection.setAutoCommit(false);

        PGConnection pg =
            connection.unwrap(PGConnection.class);

        LargeObjectManager manager =
            pg.getLargeObjectAPI();

        long oid = manager.createLO(
            LargeObjectManager.READWRITE
        );

        LargeObject object = manager.open(
            oid,
            LargeObjectManager.WRITE
        );

        try (object) {
            byte[] buffer = new byte[8192];
            int count;

            while ((count = input.read(buffer)) != -1) {
                object.write(buffer, 0, count);
            }
        }

        connection.commit();
        return oid;

    } catch (Exception e) {
        connection.rollback();
        throw e;
    } finally {
        connection.setAutoCommit(oldAutoCommit);
    }
}
~~~

This sample code assumes the method owns the connection. Inside a Spring/JPA transaction, do not manually modify autoCommit/commit/rollback when the transaction manager owns the connection.

### 31.1. Streaming Avoids Materializing the Whole File

The application reads buffer-by-buffer from an InputStream and writes via the LO API, instead of loading all bytes into one huge array. Verify actual pgJDBC version, resource cleanup, and exception handling.

## 32. Large Objects and Backups

A TOAST relation is attached to its main table; backing up table data with standard PostgreSQL tools automatically includes TOAST values. You do not need to dump chunks manually.

Large Objects are a separate subsystem. With `pg_dump`, check options to include Large Objects, such as `-b/--blobs`, and pay attention to table/schema filtering modes. Never assume a filtered dump automatically includes every LO your application relies on.

After restore, verify:

- Reference tables.
- Large Object contents.
- OID references.
- Ownership/privileges.
- Application ability to read/write objects.

## 33. lo_import and lo_export

PostgreSQL provides functions to import/export Large Objects on the **server filesystem**, not the Java client's filesystem.

These functions are privilege-restricted because they expose server file access surfaces. Never use them to read arbitrary user-supplied files.

Applications typically use JDBC streaming or object storage uploads rather than granting database server filesystem access to user requests.

## 34. Object Storage for Large Files

For images/videos/files needing a CDN or shared across multiple services, object storage is often better suited than storing all bytes inside PostgreSQL.

The database stores metadata:

~~~sql
CREATE TABLE toast_lab.object_metadata (
    object_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    object_key TEXT NOT NULL UNIQUE,
    content_type TEXT NOT NULL,
    content_size BIGINT NOT NULL,
    checksum TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Object bytes reside in the storage service; the database keeps key, size, checksum, and metadata.

### 34.1. DB Transactions Do Not Roll Back Object Storage

If the application uploads an object and then INSERTs metadata, the two actions are not within the same PostgreSQL transaction. You need upload intents, statuses, checksums, outbox/retry logic, and orphan-object cleanup jobs.

On deletion, coordinate DB record removal and object deletion with retry/idempotency.

## 35. Choosing TOAST, Large Objects, or Object Storage?

| Option | Best When | Trade-Offs |
|---|---|---|
| TOAST-backed TEXT/BYTEA | Value belongs to the row, simple SQL access | Detoasting, network, and WAL on read/write |
| Large Objects | Need offset/partial read-write and in-DB streaming | Separate ACLs, unlinking, orphans, and backups |
| Object storage | Large files, CDN, multiple consumers, independent lifecycle | Consistency between DB and object store |

There is no single fixed size threshold across all systems. Evaluate payload size, read/write frequency, concurrency, network, and backup requirements.

## 36. TOAST and Java Memory

When JDBC executes:

~~~sql
SELECT raw_data
FROM toast_lab.documents
WHERE document_id = ?;
~~~

and calls:

~~~java
byte[] content = resultSet.getBytes("raw_data");
~~~

the driver typically materializes the BYTEA value as a single byte array on the JVM heap.

This can cause:

- Increased heap usage.
- Large allocations and GC pressure.
- Extra copies/encoding inflating memory.
- Network transfer overhead and latency.
- OutOfMemoryError when concurrent requests download large blobs.

### 36.1. Query Only Required Columns

If a list endpoint only needs titles:

~~~sql
SELECT document_id, title
FROM toast_lab.documents;
~~~

Do not SELECT body/raw_data if the UI does not need them. For large files requiring random access/partial reads, consider the LO API or object storage.

## 37. Compression Trades CPU for Storage/I/O

| Heavy Compression | No or Minimal Compression |
|---|---|
| Reduces stored bytes when compressible | Consumes more storage |
| Can reduce I/O | Less compression/decompression CPU |
| Costs CPU on read/write | Can be faster for some access patterns |
| Depends on content | More predictable for incompressible data |

JPEG/MP4/ZIP or ciphertext rarely shrinks meaningfully. Benchmark with realistic sample data.

## 38. EXTERNAL and Partial Access

`EXTERNAL` can be beneficial for certain text/bytea slice operations because it avoids decompressing the entire compressed datum. However, performance still depends on functions, data types, chunks, and I/O.

~~~sql
ALTER TABLE toast_lab.documents
ALTER COLUMN body
SET STORAGE EXTERNAL;
~~~

Do not pick EXTERNAL solely because of its name; measure your workload before switching strategies.

## 39. Metadata Updates and HOT

PostgreSQL performs Heap-Only Tuple (HOT) updates under certain conditions, such as when indexed columns do not change and the page retains enough free space.

TOAST does not by itself guarantee an UPDATE will be HOT. Outcome still depends on indexes, fillfactor, page free space, and modified columns.

Do not treat "the large column is TOASTed" as proof that metadata updates are always cheap.

## 40. TOAST and Logical Replication

Modifying large values can increase WAL and replication traffic. Logical decoding/replication has specific semantics regarding TOASTed columns and columns unchanged across versions.

If downstream consumers require the full row image, verify replica identity, output plugin, PostgreSQL version, unchanged TOAST column handling, and replication lag. Never assume every CDC event always carries the full value.

## 41. Monitoring Storage After UPDATE/DELETE

After updating many blobs, monitor:

- Heap size.
- TOAST relation size.
- Index size.
- Dead tuples.
- Autovacuum activity.
- Long-running snapshots.
- WAL/replication lag.

A small heap table can still have huge TOAST/index storage. Use multiple size functions to understand the full scope, not just a single metric.

## 42. Troubleshooting: Row Too Big

If INSERT/UPDATE reports the tuple is too big, check:

1. Is the column a toastable type?
2. Was the storage strategy set to PLAIN?
3. Does the tuple contain too many inline values?
4. Is toast_tuple_target configured unusually?
5. Do triggers/functions add extra data?
6. Does the data type/extension support TOAST?

Do not rush to change block size or split databases before understanding the schema.

## 43. Troubleshooting: Disk Usage Larger Than Heap

Possible reasons:

- Large TOAST relation.
- Large indexes.
- Dead tuples/old versions.
- Free space map/visibility map.
- Long transactions blocking cleanup.
- Separate Large Objects.
- WAL/archives/backups outside relation size.

Compare pg_relation_size, pg_table_size, pg_indexes_size, and pg_total_relation_size. Check relation associations when suspecting TOAST.

## 44. Common Misconceptions

### 44.1. TOAST Is an Extension That Must Be Installed

False. It is a built-in PostgreSQL mechanism.

### 44.2. 2 KB Is the Maximum Size of TEXT

False. It is a typical threshold/target.

### 44.3. Every Large Value Gets Compressed

False. Compression depends on strategy and compressibility.

### 44.4. EXTERNAL Means S3

False. EXTERNAL is still a TOAST relation inside the database.

### 44.5. SET COMPRESSION Rewrites Old Data

False. A separate rewrite is needed if you want to convert old representations.

### 44.6. pg_column_size Equals the Total TOAST Table Size

False. It measures a single datum, not all chunks/indexes/overhead.

### 44.7. pg_relation_size Includes All TOAST and Indexes

False. Use pg_table_size/pg_total_relation_size.

### 44.8. VACUUM Always Shrinks the File

False. Regular VACUUM makes space reusable; VACUUM FULL rewrites with strong locks.

### 44.9. TOAST Provides a Streaming API for Java

False. TOAST is internal; JDBC often materializes BYTEA. LO API/object storage provide clearer streaming semantics.

### 44.10. BYTEA and Large Objects Are Identical

False. BYTEA is a column value; an LO is a separate object with its own OID/ACL/lifecycle.

### 44.11. RLS on the Reference Table Protects Every Large Object

False. LOs have separate privileges.

### 44.12. Deleting the Referencing Row Automatically Unlinks the LO

Do not assume so. Manage unlinking/lifecycle explicitly.

### 44.13. A Table Backup Always Includes All Large Objects

Not by default; verify dump and restore options.

### 44.14. Indexes Are Automatically TOASTed

False. Index tuples have their own size limits.

### 44.15. TOAST Compression Is the Same as WAL Compression

False. They are two different mechanisms.

## 45. Storage Selection Checklist

**Data:**

1. Is the value text, JSON, bytea, or a file?
2. What are average/p95/p99 sizes?
3. Is it compressible?
4. Do reads need the whole value or slices?
5. Are payloads updated frequently?
6. Are CDN/versioning/retention features needed?

**PostgreSQL:**

7. Which storage strategy applies?
8. Which compression methods are supported?
9. What are TOAST/table/index sizes?
10. What is the WAL and replication impact?
11. Can vacuum/autovacuum keep up?
12. Do queries accidentally SELECT blobs?
13. Is the index strategy appropriate?

**Application / Operations:**

14. Does JDBC materialize the entire byte[]?
15. Is there a suitable streaming API?
16. Are LO ACLs/unlinking/backups clearly handled?
17. Are object storage consistency and lifecycle clearly handled?
18. Are upload/download limits enforced?
19. Are checksums/retries implemented?
20. Has backup/restore been tested with large data?

## 46. Practice Exercises

### Exercise 1 — What is TOAST?

Write out the full meaning of the acronym TOAST.

**Hint:** The Oversized-Attribute Storage Technique.

### Exercise 2 — Tuple size

Why can a tuple not grow arbitrarily large on a single page?

**Hint:** pages have a fixed size.

### Exercise 3 — Threshold

Is roughly 2 KB the maximum size of TEXT?

**Hint:** no, it is a typical threshold/target.

### Exercise 4 — Varlena

Name three data types commonly TOASTed.

**Hint:** TEXT, BYTEA, JSONB.

### Exercise 5 — Inline

Explain inline storage.

**Hint:** the value resides inside the heap tuple.

### Exercise 6 — Out-of-line

What does a TOAST pointer do?

**Hint:** references a value in an auxiliary relation.

### Exercise 7 — Chunk

Why are large values split into chunks?

**Hint:** to store in pieces fitting page/storage limits.

### Exercise 8 — Catalog

Which catalog field links a table to its TOAST relation?

**Hint:** pg_class.reltoastrelid.

### Exercise 9 — Internal relation

Why should chunk rows not be modified directly?

**Hint:** PostgreSQL manages pointers/MVCC/storage internally.

### Exercise 10 — PLAIN

Does PLAIN allow compression or out-of-line storage?

**Hint:** no.

### Exercise 11 — EXTENDED

What are the characteristics of the common default strategy?

**Hint:** compression and out-of-line storage.

### Exercise 12 — EXTERNAL

How does it differ from EXTENDED?

**Hint:** out-of-line without compression.

### Exercise 13 — MAIN

What does MAIN prioritize?

**Hint:** keeping inline after compression, moving out-of-line only when necessary.

### Exercise 14 — Compression

Name two compression methods.

**Hint:** pglz and LZ4 if supported by the build.

### Exercise 15 — Version

Since which version is per-column SET COMPRESSION supported?

**Hint:** PostgreSQL 14.

### Exercise 16 — Existing data

Does SET COMPRESSION rewrite existing values?

**Hint:** no.

### Exercise 17 — toast_tuple_target

What does this parameter control?

**Hint:** target tuple size after TOAST.

### Exercise 18 — fillfactor

Distinguish toast_tuple_target from fillfactor.

**Hint:** inline tuple target vs page free space.

### Exercise 19 — pg_column_size

Write a query measuring the storage size of body.

**Hint:** pg_column_size(body).

### Exercise 20 — octet_length

How does it differ from pg_column_size?

**Hint:** logical bytes vs storage representation.

### Exercise 21 — Compression inspection

Which function inspects a compressed datum's method on PostgreSQL 14+?

**Hint:** pg_column_compression.

### Exercise 22 — Relation size

Distinguish pg_relation_size, pg_table_size, and pg_total_relation_size.

**Hint:** heap, table with auxiliary components, table plus indexes.

### Exercise 23 — Detoast

What might SELECTing the full body require?

**Hint:** fetching/decompressing/reconstructing the datum.

### Exercise 24 — Projection

Why avoid SELECT * when body is large?

**Hint:** reduces detoasting, network transfer, and JVM memory usage.

### Exercise 25 — MVCC

What extra storage might updating a large body create?

**Hint:** new row versions and new TOAST chunks.

### Exercise 26 — Vacuum

Why is old TOAST data not deleted immediately?

**Hint:** older snapshots may still need it.

### Exercise 27 — VACUUM FULL

How does it differ from regular VACUUM?

**Hint:** full rewrite and strong locks.

### Exercise 28 — WAL

Why can updating a large BYTEA increase WAL?

**Hint:** many TOAST chunks/row versions written.

### Exercise 29 — Index

Can a TOASTed column be B-tree indexed over arbitrarily huge values?

**Hint:** no, index tuples have size limits.

### Exercise 30 — BYTEA

List pros and cons of storing files in BYTEA.

**Hint:** simple transactions vs materialization/WAL/storage overhead.

### Exercise 31 — Large Object

How is an LO referenced?

**Hint:** by OID.

### Exercise 32 — LO catalogs

Name the two catalog relations for Large Objects.

**Hint:** pg_largeobject and pg_largeobject_metadata.

### Exercise 33 — LO functions

Name functions to create, read, write, and delete an LO.

**Hint:** lo_create, lo_get, lo_put, lo_unlink.

### Exercise 34 — LO ACL

Does RLS on the file_refs table replace LO privileges?

**Hint:** no.

### Exercise 35 — Orphan LO

Why are lo_unlink and vacuumlo needed?

**Hint:** to clean up unreferenced objects.

### Exercise 36 — JDBC LO

Why does the Large Object API require a transaction?

**Hint:** operations run within a transaction context.

### Exercise 37 — Backup

Why verify --blobs in pg_dump?

**Hint:** Large Objects are a separate subsystem.

### Exercise 38 — Object storage

Why are uploading an object and INSERTing metadata not atomic with PostgreSQL?

**Hint:** an external service does not participate in the DB transaction.

### Exercise 39 — Java memory

What risk does getBytes() carry on a large BYTEA?

**Hint:** materializing byte[] and increasing heap/GC pressure.

### Exercise 40 — Storage choice

Choose storage for large videos needing a CDN.

**Hint:** typically object storage, with the database keeping metadata/keys.

## 47. Frequently Asked Questions

### Is TOAST an extension?

No. It is an internal PostgreSQL storage mechanism.

### Is 2 KB the maximum size of TEXT?

No. It is a typical default threshold/target on standard configurations.

### Is every large value compressed?

No. Compression depends on strategy and whether size can actually be reduced.

### Does EXTERNAL mean storing on an external filesystem outside the database?

No. It is TOAST's uncompressed out-of-line strategy.

### Does SET STORAGE/SET COMPRESSION alter old data?

Not automatically. A controlled rewrite/update is needed to convert existing representations.

### How can I check the compression method?

On PostgreSQL 14+, use pg_column_compression(column).

### Is pg_column_size equal to the TOAST relation size?

No. It measures a single datum, excluding all chunks/indexes/overhead across the relation.

### Does pg_relation_size include TOAST?

Not necessarily. Use pg_table_size or pg_total_relation_size to see broader scope.

### Does TOAST replace Large Objects?

No. TOAST stores column values; Large Objects have OIDs and an offset read/write API.

### Is BYTEA subject to RLS?

BYTEA is a row column, so table access obeys corresponding GRANT/RLS rules. Large Objects have their own ACLs.

### Does deleting a row containing an OID delete the LO?

Do not assume so. Explicitly manage lo_unlink and lifecycle.

### Does TOAST automatically stream files to Java?

No. TOAST is internal. JDBC may materialize BYTEA; the LO API/object storage fit better for certain large files.

### Does VACUUM shrink files immediately?

Usually no. Regular VACUUM makes space reusable; VACUUM FULL rewrites with strong locks.

### Is compression always faster?

No. Compression trades CPU for storage/I/O; net effect depends on data and workload.

### Should images/videos be stored in PostgreSQL?

Possible in some systems, yet you must evaluate size, frequency, streaming, backups, WAL, replication, and CDN needs. Object storage is usually better suited for widely distributed large media.

## 48. Summary

Commands/tools worth remembering:

~~~sql
-- Storage size of a datum.
SELECT pg_column_size(body)
FROM toast_lab.documents;

-- Logical bytes.
SELECT octet_length(body)
FROM toast_lab.documents;

-- Compression method (PostgreSQL 14+).
SELECT pg_column_compression(body)
FROM toast_lab.documents;

-- TOAST relation associated with the table.
SELECT reltoastrelid::regclass
FROM pg_class
WHERE oid = 'toast_lab.documents'::regclass;

-- Heap/table/index/total size.
SELECT
    pg_relation_size('toast_lab.documents'::regclass),
    pg_table_size('toast_lab.documents'::regclass),
    pg_indexes_size('toast_lab.documents'::regclass),
    pg_total_relation_size('toast_lab.documents'::regclass);

-- Storage strategy applied to future writes.
ALTER TABLE toast_lab.documents
ALTER COLUMN body SET STORAGE EXTENDED;

-- Compression for future writes if supported by the server.
ALTER TABLE toast_lab.documents
ALTER COLUMN body SET COMPRESSION pglz;

SHOW default_toast_compression;
~~~

Principles to remember:

1. TOAST handles oversized attributes so main tuples fit on heap pages.
2. It applies primarily to supported variable-length types.
3. Values can be inline, compressed, or out-of-line.
4. TOAST relations, chunks, and pointers are internal; never modify them directly.
5. EXTENDED is the common strategy; PLAIN disables compression/out-of-line, EXTERNAL stores out-of-line uncompressed, MAIN prefers inline.
6. pglz is always available; LZ4 depends on build support and per-column compression was added in PostgreSQL 14.
7. SET STORAGE and SET COMPRESSION do not automatically rewrite old data.
8. toast_tuple_target controls tuple target size, distinct from fillfactor.
9. pg_column_size measures a datum; pg_table_size/pg_total_relation_size inspect broader storage scope.
10. Reading the full value can require detoasting and large byte transfers; query only needed columns.
11. Updating large values can generate new row versions/chunks, WAL, and vacuum pressure.
12. Index tuples have their own size limits; do not assume any TOAST column can be B-tree indexed across its entire value.
13. BYTEA/TOAST integrates with row transactions and RLS; Large Objects have separate OID/ACL/lifecycle management.
14. Object storage fits when streaming, CDN, and independent lifecycle are needed, though it is not atomic with DB transactions.
15. For large files in Java, avoid unnecessary byte[] materialization; consider the LO API or object storage.
16. Backups/restores must explicitly include Large Objects per options and be tested; TOAST travels with table storage.
17. Compression, vacuum, WAL, replication, and JVM memory must be evaluated against real workloads.

Decision flowchart:

~~~text
Large data to store
       |
       v
Is it a value belonging to a row?
       |
   +---+---+
   |       |
  Yes     No / separate file object
   |              |
   v              v
TOAST-backed     Need random/partial
TEXT/BYTEA?      read/write inside DB?
   |              |
   |           +--+--+
   |           |     |
   |          Yes    No
   |           |      |
   |           v      v
   |       Large     Object
   |       Object    storage
   |
   v
Query metadata only or full payload?
   |
   +--> Metadata: do not SELECT blob
   |
   +--> Payload: evaluate detoasting, memory,
                 network, WAL, and compression
~~~

**Conclusion:** TOAST enables PostgreSQL to store large values transparently to SQL, yet **being able to store them does not mean every read/write pattern is cheap**. Choose storage strategies and compression by data type, measure actual TOAST sizes, avoid fetching oversized columns unnecessarily, and compare TOAST against Large Objects or object storage when applications need streaming, partial access, or large-scale file distribution.
