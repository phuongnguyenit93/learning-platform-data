# Large Objects vs. BYTEA and Data Lifecycle in PostgreSQL

An application storing profile photos, contract PDFs, scanned files, or videos in PostgreSQL has two common ways to store binary data:

- **`bytea`:** stores bytes as a column value inside a relational row.
- **Large Object (LO):** stores content in PostgreSQL's dedicated Large Object facility, while the business table keeps a **referencing OID** to that object.

Both can be managed transactionally and backed up alongside the database when using appropriate tools. Yet they differ substantially in access patterns, size limits, security, data linking, and especially **deletion lifecycle**.

Example:

```sql
-- Binary is part of the row:
CREATE TABLE documents_bytea (
    document_id bigint PRIMARY KEY,
    file_name text NOT NULL,
    content bytea NOT NULL
);

-- Row stores only an OID pointing to a separate Large Object:
CREATE TABLE documents_lo (
    document_id bigint PRIMARY KEY,
    file_name text NOT NULL,
    content_oid oid NOT NULL
);
```

With `bytea`, when a row is deleted, its binary value is managed by PostgreSQL under MVCC/TOAST and reclaimed through normal storage cleanup. With Large Objects, **deleting the referencing row does not automatically delete the object**. The application must call `lo_unlink`/corresponding APIs, use triggers aligned with the reference model, or run orphan cleanup processes.

Making the right choice depends on more than file size. Consider whether the application needs range reads/writes, sharing one object across multiple rows, who is authorized to read the object, how row deletion works, backup/restore, and whether clients use JDBC/ORMs.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish the `bytea` data type from OID-referenced Large Objects.
2. Explain how TOAST automatically compresses and stores oversized values of TOAST-capable types out-of-line.
3. State the logical size limit of a TOASTed field/`bytea` (1 GB) and the Large Object advantage for content up to 4 TB.
4. Understand how Large Objects are split into chunks supporting streaming and random access.
5. Create, open, read, write, seek, truncate, and unlink Large Objects via SQL/libpq/pgJDBC.
6. Use JDBC `setBytes`/`getBytes`/`setBinaryStream`/`getBinaryStream` for `bytea`.
7. Access Large Objects inside JDBC transactions and release resources properly.
8. Design metadata–binary relationships, object permissions, and business constraints.
9. Handle lifecycle states: creation, file replacement, row deletion, object sharing, rollback, and orphan cleanup.
10. Understand the `lo` module, the `lo` domain type, the `lo_manage` trigger, and the `vacuumlo` utility.
11. Recognize security risks when OIDs leak, since RLS only protects referencing rows while LO ACLs are separate.
12. Plan backups/restores, `bytea` ↔ LO migrations, retention, and testing to prevent leaks or data loss.

## 2. Two Storage Models

### 2.1. BYTEA: Binary as a Row Attribute

```sql
CREATE TABLE app.attachments (
    attachment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id bigint NOT NULL,
    file_name text NOT NULL,
    media_type text NOT NULL,
    content bytea NOT NULL,
    content_length bigint NOT NULL
        CHECK (content_length >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);
```

A row owns its binary content directly. Metadata and bytes live together in the relational model; foreign keys, transactions, RLS, and column privileges apply under standard table rules.

### 2.2. Large Object: Row Holds OID, Object Exists Separately

```sql
CREATE TABLE app.attachments_lo (
    attachment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id bigint NOT NULL,
    file_name text NOT NULL,
    media_type text NOT NULL,
    content_oid oid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

`content_oid` is a **Large Object identifier**, not the bytes themselves and not a filesystem path. The payload resides in PostgreSQL's Large Object subsystem; applications must open the LO by OID to read or write.

### 2.3. Quick Comparison

| Criterion | `bytea` | Large Object |
| --- | --- | --- |
| Model | Column value inside a row. | Separate object; row holds OID. |
| Max logical size | 1 GB for a TOAST-able datum. | Up to 4 TB per PostgreSQL docs. |
| Physical storage | TOAST can compress and/or split chunks into a TOAST table. | Split into chunks in `pg_largeobject`, metadata in `pg_largeobject_metadata`. |
| Streaming | JDBC offers stream APIs; the value itself remains a `bytea` datum. | LO API reads/writes by slice and seeks directly. |
| Partial read/write | Most operations handle the value as one unit; substring optimizations exist in some TOAST modes. | Explicit random access/partial read-write supported. |
| Lifecycle | Tied to row/column, automatically managed by PostgreSQL. | Must unlink or run cleanup; deleting referencing row does not delete the LO. |
| Sharing one payload | Copy bytes or extract a dedicated content table. | Multiple rows can reference one OID, requiring careful refcount/ownership tracking. |
| Access permissions | Table/column privileges and row-level security (RLS). | Separate LO ACL/owner independent of the referencing row's permissions. |
| Relational integrity | Easy constraints, FKs, and standard DML. | OID does not automatically create an FK to the object catalog. |
| Backup | Follows table data. | Separate LO data; ensure dump tools include Large Objects. |
| JDBC | `getBytes`, `setBytes`, binary streams. | pgJDBC LargeObject API or Blob mapping; requires a transaction. |
| Operational complexity | Generally lower. | Higher due to lifecycle, ACLs, and orphan cleanup. |

### 2.4. Initial Selection Rules

- Small/medium files, usually read in full and tightly bound to a business row: prefer `bytea`.
- Very large files requiring seek/range reads or partial updates: consider Large Objects.
- Files served via CDN/object storage with independent lifecycle/versioning: consider storing externally and keeping metadata/references in PostgreSQL.

Do not pick LO merely because "Large Object" sounds more suitable. Unless you need random-access APIs or sizes exceed the `bytea` limit, OID/orphan management overhead may not be worthwhile.

## 3. How Do BYTEA and TOAST Work?

PostgreSQL uses fixed-size pages (normally 8 kB), and a tuple cannot span arbitrarily across multiple pages. TOAST (The Oversized-Attribute Storage Technique) handles large values of supported types by compressing and/or moving data out to a TOAST table linked to the main table.

**Applications never need to build manual chunk tables for `bytea`.** PostgreSQL handles that transparently when needed while SQL continues seeing a single `bytea` value.

### 3.1. TOAST Does Not Mean Every Value Over 2 kB Is Moved Out

TOAST normally activates when total row width exceeds the threshold (default around 2 kB). PostgreSQL attempts to compress compressible attributes, then moves attributes out-of-line if tuple size still needs reduction. Exact behavior depends on type, storage settings, and actual data.

### 3.2. Storage Strategies

| Strategy | Behavior |
| --- | --- |
| `PLAIN` | Neither compression nor out-of-line storage; mandatory for non-TOASTable types. |
| `EXTENDED` | Permits compression and out-of-line storage; default for most TOASTable types. |
| `EXTERNAL` | Permits out-of-line storage without compression; can speed up substrings on large text/bytea at the cost of higher storage. |
| `MAIN` | Permits compression while preferring inline storage; falls back to out-of-line only if the tuple cannot otherwise fit on a page. |

Example changing storage strategy:

```sql
ALTER TABLE app.attachments
ALTER COLUMN content SET STORAGE EXTERNAL;
```

This only sets the policy for **subsequent writes/updates**; `ALTER TABLE ... SET STORAGE` itself does not rewrite all existing data. Never switch to EXTERNAL merely assuming "streaming will be faster"; benchmark workload and disk usage.

### 3.3. BYTEA Size Limits

A TOAST-able datum has a 1 GB logical size limit (specifically per varlena representation). Thus `bytea` cannot hold a single 3 GB file as one datum, even though PostgreSQL splits TOAST chunks underneath.

Beyond server limits, applications often hit lower bounds:

- Java `byte[]` requires a contiguous array in heap.
- ORMs may materialize the entire value.
- Drivers may buffer data in ways that inflate heap usage.
- HTTP uploads/downloads may hit request timeouts.
- A SELECT returning large binary columns consumes substantial memory/network.

**TOAST relieves tuple/page pressure; it does not make binary access automatically streaming or free.**

### 3.4. TOAST Table and Index

Each table with TOAST-able columns can have its own TOAST table whose OID is stored in `pg_class.reltoastrelid`. Out-of-line values are chunked in the TOAST table with an index to locate chunks.

Never directly read or modify `pg_toast_*` system tables. They are implementation details; run SQL against the parent table and let PostgreSQL manage them.

### 3.5. Updating Other Columns Does Not Necessarily Rewrite BYTEA

When updating a row without modifying its out-of-line binary column, PostgreSQL generally preserves the existing TOAST value rather than rewriting the large payload. Do not assume "every UPDATE to a row with BYTEA rewrites the entire file."

However, if `bytea` content itself changes, PostgreSQL creates a new MVCC version and updates TOAST storage accordingly; vacuum reclaims the old version once no snapshot needs it.

## 4. Large Objects: Separate Objects, OIDs, and Chunks

Large Objects are a separate storage subsystem within each PostgreSQL database.

### 4.1. Two Primary Catalogs

- `pg_largeobject` stores LO content in chunks.
- `pg_largeobject_metadata` stores the OID, owner, and ACL of each LO.

Applications generally do not query these catalogs directly; use the Large Object API or server-side functions.

### 4.2. OID Is a Reference Handle

An OID value in a business table is merely the object's numeric identifier:

```sql
SELECT content_oid
FROM app.attachments_lo
WHERE attachment_id = 10;
```

To read bytes, call the API or LO functions such as `lo_get(content_oid)`. Selecting the OID does not fetch content.

### 4.3. Objects Are Split into Chunks

PostgreSQL stores an LO as chunks indexed by a B-tree for offset lookups. Chunks need not be contiguous; LOs support seeking to an offset and writing a region without allocating intervening gaps. Unwritten gaps read back as zero bytes under sparse allocation semantics.

### 4.4. Size Limits

PostgreSQL documentation states Large Objects can reach up to **4 TB**. When working with objects exceeding 2 GB, use 64-bit offset/size APIs (e.g., libpq `lo_lseek64`/`lo_tell64`/`lo_truncate64`; pgJDBC `seek64`/`size64`/`truncate64`). Legacy 32-bit APIs cannot address offsets beyond 2 GB.

### 4.5. OIDs Are Not Foreign Keys

PostgreSQL does not automatically create an FK from `content_oid` to the object catalog. If a row is deleted, the LO stays behind; if the LO is unlinked, rows may retain OIDs pointing to a missing object.

Therefore, applications must establish clear rules:

- Who owns the object?
- How many rows reference it?
- Does deleting a row delete the object?
- When replacing a file, when is the old object unlinked?
- Is sharing an OID permitted?
- What cleans up unreferenced objects?

### 4.6. Never Reuse OIDs as Business Codes

OIDs are database-allocated and scoped to a specific database. Never use OIDs as guessable public IDs, never assume they survive export/import or match across databases, and never expose OIDs to clients as security capabilities.

## 5. SQL API for Large Objects

PostgreSQL provides server-side functions to create/delete and read/write LOs. They are handy for small actions or labs, yet functions returning `bytea` materialize the full content and do not replace streaming APIs for huge files.

### 5.1. Creating an LO

```sql
SELECT lo_create(0) AS new_loid;
```

`0` tells PostgreSQL to allocate an available OID and return it, creating an empty object.

Another option when you already have `bytea`:

```sql
SELECT lo_from_bytea(0, decode('48656c6c6f', 'hex')) AS new_loid;
```

This returns the OID of an LO holding the bytes for UTF-8 "Hello". Use small payloads for this; never pass a multi-GB file through `bytea` to call `lo_from_bytea`.

### 5.2. Reading All or a Slice with lo_get

```sql
-- Read entire content, returning bytea:
SELECT lo_get(12345);

-- Read 100 bytes starting at offset 500 (0-based offset):
SELECT lo_get(12345, 500, 100);
```

`lo_get` returns `bytea`. The offset/length form is great for small slices, yet **never use it to pull a 4 TB LO into a single bytea result**.

### 5.3. Writing a Slice with lo_put

```sql
SELECT lo_put(
    12345,
    0,
    convert_to('Hello PostgreSQL', 'UTF8')
);
```

`lo_put` writes bytes starting at the specified offset, extending the object if needed. Offset is a 0-based bigint.

### 5.4. Deleting an LO with lo_unlink

```sql
SELECT lo_unlink(12345);
```

Returns 1 on successful deletion, or 0 if no matching object exists per function semantics. Only the LO owner or a superuser can unlink. **Never call unlink before verifying no remaining rows still reference the object.**

### 5.5. Import/Export: Server-Side vs. Client-Side Differ

Server-side functions:

```sql
SELECT lo_import('/server/path/report.pdf');
SELECT lo_export(12345, '/server/path/report-copy.pdf');
```

These access the **PostgreSQL server's filesystem** under the OS user running the server; by default they are restricted to superusers due to server file read/write risks.

In `psql`, `\lo_import` and `\lo_export` are meta-commands using the **client machine's filesystem running psql**. Never confuse the two despite their similar names.

### 5.6. Do Not Grant Server-Side lo_import/lo_export Casually

Granting untrusted users permission to invoke server-side import/export opens paths to read/write server files, including sensitive files. Grant only to audited operational roles treated as high-privilege administration.

## 6. BYTEA in SQL: Creating, Writing, Reading, and Checking

### 6.1. Lab Table

```sql
CREATE SCHEMA IF NOT EXISTS storage_lab;

CREATE TABLE storage_lab.attachments_bytea (
    attachment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_name text NOT NULL,
    media_type text NOT NULL,
    content bytea NOT NULL,
    content_length bigint NOT NULL
        CHECK (content_length >= 0),
    sha256_hex text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (content_length = octet_length(content))
);
```

`octet_length` counts bytes, making it proper for binary data. Never use text `length` to measure file byte size when multi-byte encodings may exist.

### 6.2. Inserting Small Binary from Hex

```sql
INSERT INTO storage_lab.attachments_bytea (
    file_name,
    media_type,
    content,
    content_length
)
VALUES (
    'hello.txt',
    'text/plain',
    decode('48656c6c6f', 'hex'),
    5
)
RETURNING attachment_id, file_name, octet_length(content);
```

`decode(...,'hex')` converts a hex string into bytes. The 5-byte result is "Hello".

### 6.3. Reading Content as Hex/Base64

```sql
SELECT
    file_name,
    encode(content, 'hex') AS hex_value,
    encode(content, 'base64') AS base64_value,
    octet_length(content) AS bytes
FROM storage_lab.attachments_bytea;
```

Hex/base64 are handy for debugging tiny payloads, yet never SELECT/encode hundreds of MB to logs or consoles.

### 6.4. Slicing Binary Data

```sql
SELECT substring(content FROM 1 FOR 3)
FROM storage_lab.attachments_bytea
WHERE file_name = 'hello.txt';
```

For `bytea`, substring positions are **1-based**, unlike Large Object API offsets which are **0-based**. Watch out for this off-by-one difference when porting code.

### 6.5. Updating Binary

```sql
UPDATE storage_lab.attachments_bytea
SET
    content = decode('576f726c64', 'hex'),
    content_length = 5
WHERE file_name = 'hello.txt';
```

The new content is "World". `CHECK(content_length=octet_length(content))` prevents metadata length drift.

### 6.6. Deleting a BYTEA Row

```sql
DELETE FROM storage_lab.attachments_bytea
WHERE file_name = 'hello.txt';
```

Deleting the row removes the link to the `bytea` datum at the same time. PostgreSQL handles reclaiming old physical versions under MVCC/autovacuum; no `lo_unlink` or `vacuumlo` is ever needed for `bytea`.

## 7. Large Objects in SQL: Reference Table and Operations

### 7.1. Creating an LO Reference Metadata Table

```sql
CREATE TABLE storage_lab.attachments_lo (
    attachment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_name text NOT NULL,
    media_type text NOT NULL,
    content_oid oid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

In this basic example, `oid` clearly represents the reference type. You can install the `lo` module and use the `lo` domain to clarify the column holds an LO reference; the domain alone does not manage lifecycle.

### 7.2. Creating Object and Referencing Row in the Same Transaction

```sql
BEGIN;

WITH new_object AS (
    SELECT lo_from_bytea(
        0,
        convert_to('Large Object demo', 'UTF8')
    ) AS object_oid
)
INSERT INTO storage_lab.attachments_lo (
    file_name,
    media_type,
    content_oid
)
SELECT
    'demo.txt',
    'text/plain',
    object_oid
FROM new_object
RETURNING attachment_id, content_oid;

COMMIT;
```

The object and referencing row are created inside the same transaction. If the row INSERT fails and the transaction rolls back, LO creation rolls back too. This avoids orphans from the outset in simple workflows.

### 7.3. Reading a Small LO with lo_get

```sql
SELECT
    attachment_id,
    file_name,
    convert_from(lo_get(content_oid), 'UTF8') AS content_text
FROM storage_lab.attachments_lo
WHERE file_name = 'demo.txt';
```

This example assumes the LO holds small UTF-8 text. For general binary files, keep data as bytea/streams; never call `convert_from` unless bytes are valid encoded text.

### 7.4. Reading an LO Slice

```sql
SELECT lo_get(content_oid, 0, 6)
FROM storage_lab.attachments_lo
WHERE file_name = 'demo.txt';
```

Offset 0 reads the first six bytes. Use this for small previews/chunks, never to read an entire large LO into memory.

### 7.5. Replacing LO Content with lo_put

```sql
UPDATE storage_lab.attachments_lo
SET content_oid = lo_from_bytea(
    0,
    convert_to('Replacement content', 'UTF8')
)
WHERE file_name = 'demo.txt'
RETURNING attachment_id, content_oid;
```

**Warning:** this UPDATE creates a new LO without deleting the old LO. It demonstrates why lifecycle must be managed explicitly; do not use it as a complete replacement pattern. Section 14 covers handling old objects safely.

### 7.6. Deleting an Object

```sql
-- Replace 12345 with an actual OID:
SELECT lo_unlink(12345);
```

After unlinking, any rows still holding that OID become broken references. Remove/replace references beforehand or inside the same transaction per your designed order and policy.

## 8. JDBC with BYTEA

pgJDBC supports `bytea` via standard JDBC APIs. For small payloads already in memory, use `setBytes`/`getBytes`. For larger files, stream APIs avoid allocating huge `byte[]` arrays in the application.

### 8.1. Uploading BYTEA via InputStream

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;

Path file = Path.of("upload/report.pdf");
long fileSize = Files.size(file);

String sql = """
    INSERT INTO storage_lab.attachments_bytea
        (file_name, media_type, content, content_length)
    VALUES (?, ?, ?, ?)
    """;

try (Connection conn = dataSource.getConnection();
     InputStream in = Files.newInputStream(file);
     PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setString(1, file.getFileName().toString());
    ps.setString(2, "application/pdf");
    ps.setBinaryStream(3, in, fileSize);
    ps.setLong(4, fileSize);
    ps.executeUpdate();
}
```

This example uses Java 15+ text blocks and the `setBinaryStream(index, stream, long length)` overload. Ensure length is accurate. pgJDBC documents the length-taking stream overload; the driver has no general way to know the length of an unbounded InputStream beforehand. If input length is unknown, spool to a temp file/staging object first to measure size, or use a chunked upload protocol.

### 8.2. Downloading BYTEA via InputStream

```java
String sql = """
    SELECT content
    FROM storage_lab.attachments_bytea
    WHERE attachment_id = ?
    """;

try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setLong(1, attachmentId);

    try (var rs = ps.executeQuery()) {
        if (rs.next()) {
            try (InputStream in = rs.getBinaryStream("content")) {
                // Stream to HTTP response/file/consumer.
                // No need to allocate byte[] for the whole file.
                in.transferTo(outputStream);
            }
        }
    }
}
```

This assumes `outputStream` is owned and kept open by the caller. Do not close caller-owned streams inside the method unless your contract says so. Also ensure ResultSet/Statement/Connection stay open while reading the stream.

### 8.3. getBytes Fits Small Payloads

```java
byte[] content = rs.getBytes("content");
```

`getBytes` materializes the full value on the heap. Use it for small images or tightly size-capped data; avoid it on unbounded large payloads.

### 8.4. An InputStream Does Not Mean Unlimited Size

Stream APIs avoid forcing the application to hold all bytes in one array, yet constraints still exist:

- 1 GB limit of a single `bytea` datum.
- Buffering inside drivers, frameworks, servlets, and reverse proxies.
- Request/statement timeouts, network bandwidth, and memory pressure.
- Requirement to hold ResultSet/Connection open while consuming the stream.

Enforce upload limits at the API layer, validate content length, and use end-to-end streaming with backpressure.

### 8.5. Verifying Size and Checksum

Store `octet_length(content)` or SHA-256 metadata. If computing the hash in the application while streaming the upload, avoid re-reading the file a second time just to hash it. Hashes verify integrity; they do not replace authorization or malware scanning.

## 9. JDBC with Large Objects

pgJDBC's Large Object API centers on two classes:

- `LargeObjectManager`: create, open, delete objects.
- `LargeObject`: read/write, stream, seek, truncate, and close descriptors.

### 9.1. Large Objects Always Require a Transaction

**Every Large Object API operation must occur inside an SQL transaction block.** An open LO descriptor is only valid within the active transaction; never use LOs on an autocommit connection as if they were standalone file handles.

```java
conn.setAutoCommit(false);
```

Upon completion, `commit` or `rollback` the transaction. With connection pools, the transaction manager must restore connections to a clean state.

### 9.2. Uploading via pgJDBC LargeObjectManager

Example using the lower-level API to stream a file in chunks:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;

import org.postgresql.PGConnection;
import org.postgresql.largeobject.LargeObject;
import org.postgresql.largeobject.LargeObjectManager;

Path file = Path.of("upload/archive.bin");

try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);

    try {
        PGConnection pg = conn.unwrap(PGConnection.class);
        LargeObjectManager manager = pg.getLargeObjectAPI();
        long oid = manager.createLO(
            LargeObjectManager.READWRITE
        );

        try (LargeObject lo = manager.open(
                oid, LargeObjectManager.WRITE);
             InputStream in = Files.newInputStream(file);
             var out = lo.getOutputStream()) {
            in.transferTo(out);
        }

        String sql = """
            INSERT INTO storage_lab.attachments_lo
                (file_name, media_type, content_oid)
            VALUES (?, ?, ?::oid)
            """;
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setString(1, file.getFileName().toString());
            ps.setString(2, "application/octet-stream");
            // Send OID as decimal string so PostgreSQL
            // parses it properly as oid (unsigned 32-bit).
            ps.setString(3, Long.toString(oid));
            ps.executeUpdate();
        }

        conn.commit();
    } catch (Exception ex) {
        try {
            conn.rollback();
        } catch (Exception rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
```

This illustrates explicit transaction handling. In production code, handle checked exceptions per method signatures and never close or alter autoCommit on connections managed externally by a transaction manager. If an error occurs after creating the LO but before commit, rollback undoes both the new object and the metadata row.

### 9.3. Why Bind OID as a Decimal String?

PostgreSQL `oid` is an unsigned 32-bit integer type. Java `int` is signed; calling `setInt` can misbehave when OID values exceed `Integer.MAX_VALUE`. Binding `Long.toString(oid)` and casting `?::oid` lets PostgreSQL parse it cleanly as OID. Always verify against your project's exact pgJDBC and server versions.

### 9.4. Downloading via InputStream

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.PreparedStatement;

import org.postgresql.PGConnection;
import org.postgresql.largeobject.LargeObject;
import org.postgresql.largeobject.LargeObjectManager;

Path destination = Path.of("download/archive.bin");

try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);

    try {
        long oid;
        try (PreparedStatement ps = conn.prepareStatement("""
                SELECT content_oid
                FROM storage_lab.attachments_lo
                WHERE attachment_id = ?
                """)) {
            ps.setLong(1, attachmentId);
            try (var rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new IllegalArgumentException(
                        "Attachment not found"
                    );
                }
                oid = rs.getLong(1);
            }
        }

        PGConnection pg = conn.unwrap(PGConnection.class);
        LargeObjectManager manager = pg.getLargeObjectAPI();

        try (LargeObject lo = manager.open(
                oid, LargeObjectManager.READ);
             InputStream in = lo.getInputStream();
             var out = Files.newOutputStream(destination)) {
            in.transferTo(out);
        }

        conn.commit();
    } catch (Exception ex) {
        try {
            conn.rollback();
        } catch (Exception rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
```

Only open the OID after verifying the user is authorized to download that attachment. Row metadata permissions and LO read permissions are separate layers; see the security section below.

### 9.5. Seeking and Reading a Range

```java
try (LargeObject lo = manager.open(
        oid, LargeObjectManager.READ)) {
    lo.seek64(1024L * 1024L, LargeObject.SEEK_SET);
    byte[] chunk = lo.read(64 * 1024);
    // Process chunk; continue reading until EOF if needed.
}
```

This seeks to 1 MiB and reads up to 64 KiB. `read(int len)` returns a byte array for the slice read; when processing huge files, read chunk-by-chunk and avoid accumulating all chunks into one array.

### 9.6. Truncate

```java
try (LargeObject lo = manager.open(
        oid, LargeObjectManager.WRITE)) {
    lo.truncate64(newLength);
}
```

If the new length exceeds the current size, the extension is zero-filled per LO semantics. This requires a transaction and UPDATE privilege on the LO.

### 9.7. Closing Descriptors and Streams

`LargeObject` implements `AutoCloseable`. Use try-with-resources to close descriptors and streams. Descriptors left open when a transaction ends are closed automatically by PostgreSQL, yet closing explicitly ensures clear resource management and error reporting.

### 9.8. pgJDBC Blob Mapping

pgJDBC also supports `Blob`/`setBlob`/`getBlob` for Large Object mapping. Driver docs show uploading via `PreparedStatement.setBlob(index, inputStream, length)` and reading via `Blob.getBinaryStream()`. Always check driver version, transaction mode, and `oid` column type; these APIs have different semantics from `bytea`.

### 9.9. Never Use One Connection Concurrently from Multiple Threads

A `Connection`/LargeObject descriptor is tied to a specific session/transaction. Never share the same connection/descriptor across two threads seeking/reading/writing simultaneously; synchronize or use dedicated connections by design. A descriptor is not a thread-safe standalone file handle.

## 10. Comparing Application Access Patterns

| Task | BYTEA | Large Object |
| --- | --- | --- |
| Upload small file already in byte[] | `setBytes` | Possible to create LO, yet more complex. |
| Upload file via stream | `setBinaryStream` with exact length | `LargeObject.getOutputStream` or Blob API inside transaction. |
| Download small file | `getBytes` | `lo_get`/Blob, yet requires an LO transaction. |
| Download large file | `getBinaryStream` if datum fits limit and driver streaming works | LO streams by chunks; suited to huge files. |
| Read bytes at offset | `substring(bytea...)`/stream logic; depends on TOAST strategy | `seek64` then `read`. |
| Modify a slice at offset | Usually replaces the `bytea` datum with a new value | `seek64` + write. |
| Delete data | DELETE/UPDATE row; PostgreSQL manages datum | Must manage references and `lo_unlink`/cleanup. |
| Share same binary | Extract an asset table + FK or duplicate bytes | Multiple rows can share OID; requires reference lifecycle. |

### 10.1. BYTEA Can Stream Without Large Objects

A common misconception: calling `getBinaryStream`/`setBinaryStream` on `bytea` is still a JDBC streaming API. You do not need to switch to LOs just to avoid `getBytes`/`byte[]`. The key differences are the 1 GB datum limit and LO's random access/partial write support.

### 10.2. LOs Are Not Automatically Faster

LOs incur OID lookup, ACL, descriptor, chunk operations, and lifecycle overhead. If an application always reads whole 20 KB files, `bytea` is simpler and often faster. Benchmark with realistic sizes and access patterns before choosing.

## 11. Large Object Lifecycle: Create, Reference, Replace, and Delete

This is the biggest operational difference between `bytea` and LOs.

### 11.1. Creating Object and Reference Must Be Atomic

One transaction should perform:

1. Create the LO.
2. Write LO content.
3. Insert metadata row referencing the OID.
4. Commit both.

If step 2 or 3 fails, rollback deletes both the new object and incomplete row. Never commit the LO first and insert the metadata row in a separate transaction without an orphan recovery workflow.

### 11.2. Deleting the Referencing Row Does Not Unlink the Object

Example:

```sql
DELETE FROM storage_lab.attachments_lo
WHERE attachment_id = 10;
```

This only deletes the row. The Large Object whose OID was stored in that row **remains** in the database, consuming disk until unlinked or swept by orphan cleanup tools.

This contrasts with `bytea`, where bytes belong to the row datum and PostgreSQL handles physical reclamation under MVCC/TOAST.

### 11.3. Replacing a File Must Clean Up the Old OID

Safe sequence when one row exclusively owns an LO:

1. Create the new LO and finish writing it.
2. Within the same transaction, UPDATE the row to the new OID.
3. Unlink the old OID once confirmed no other rows reference it.
4. Commit.

If the transaction rolls back, both the OID update and LO creation/deletion roll back together. If multiple rows can share an OID, **never unlink the old OID simply because one row changed its reference**.

### 11.4. One Object with Multiple References

PostgreSQL allows multiple rows to store the same OID. However, Large Objects have no automatic reference counting across business tables:

```text
attachments row A ─┐
                  ├── OID 70001 ── Large Object
attachments row B ─┘

DELETE row A
    must NOT unlink OID 70001
because row B still uses the object.
```

If a trigger or application unlinks upon deleting row A, row B is left with a dangling OID.

### 11.5. Intermediate Metadata Registry When Sharing Is Needed

A cleaner design gives each LO a dedicated asset row, with attachments referencing that asset via FK:

```sql
CREATE TABLE storage_lab.large_object_assets (
    asset_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content_oid oid NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE storage_lab.asset_attachments (
    attachment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    asset_id bigint NOT NULL
        REFERENCES storage_lab.large_object_assets(asset_id)
        ON DELETE RESTRICT,
    owner_id bigint NOT NULL,
    file_name text NOT NULL
);
```

Each LO has one row in `large_object_assets`. Business tables reference `asset_id`; deleting an attachment keeps the object alive if other attachments still reference the asset. Only delete the asset when zero attachments reference it, and let a trigger on the asset table unlink the LO.

### 11.6. Checking Reference Count Before Deleting an Asset

```sql
BEGIN;

DELETE FROM storage_lab.asset_attachments
WHERE attachment_id = 10;

DELETE FROM storage_lab.large_object_assets AS a
WHERE a.asset_id = 7
  AND NOT EXISTS (
      SELECT 1
      FROM storage_lab.asset_attachments AS x
      WHERE x.asset_id = a.asset_id
  );

COMMIT;
```

This is a conceptual pattern; lock the asset row or design transaction locking so concurrent attachment insertions synchronize properly. The `ON DELETE RESTRICT` FK prevents deleting an asset still referenced. Asset deletion succeeds only when zero references remain.

### 11.7. Race Condition When Two Transactions Manage References Concurrently

If one transaction checks "zero references remain" and unlinks while a second transaction concurrently inserts a new reference, a dangling OID can result without synchronization. Locking the asset row serializes updates, and workflows must ensure **all code paths creating references go through the same registry/locking protocol**. Never allow direct OID writes bypassing the asset registry.

### 11.8. Sharing Files and Permissions

If multiple tenants or users share an LO, object ACLs must reflect the sharing policy. Never check only attachment row permissions and assume LO permissions are automatically safe; see Section 15.

## 12. The lo Extension: lo Domain and lo_manage Trigger

PostgreSQL provides the `lo` module to assist managing LO references in tables.

### 12.1. Installing the Extension

```sql
CREATE EXTENSION IF NOT EXISTS lo;
```

The module provides:

- Domain `lo` over `oid` to clearly distinguish columns holding Large Object references.
- Trigger function `lo_manage` to invoke `lo_unlink` when a row is deleted or its LO reference changes.

### 12.2. Example Table with a Unique LO Reference

```sql
CREATE TABLE storage_lab.images (
    image_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    raster lo NOT NULL
);

CREATE TRIGGER images_raster_lo_cleanup
BEFORE UPDATE OF raster OR DELETE
ON storage_lab.images
FOR EACH ROW
EXECUTE FUNCTION lo_manage(raster);
```

The trigger assumes each LO is referenced **exclusively in the trigger-managed column**. When a row is DELETED or `raster` is updated, the trigger unlinks the old LO.

### 12.3. Critical Limitation of lo_manage

`lo_manage` **is not a global garbage collector aware of every OID reference**. It assumes each LO has only one reference in the trigger-managed column. If an OID is shared across two rows, deleting the first row triggers unlinking and breaks the second row.

Never attach `lo_manage` mechanically to every OID table. Use it only when single-owner exclusivity is enforced by design.

### 12.4. UPDATE Not Changing the LO Column

You can restrict the trigger to `BEFORE UPDATE OF raster`. The trigger fires only on UPDATEs listing that column in the SET clause; still verify application logic and exact extension version behavior. To avoid unlinking when the new value equals the old value, design replacement flows clearly and test OLD/NEW handling.

### 12.5. Multiple LO Columns

If a table has multiple independent LO reference columns, create a separate trigger per column with a distinct name and pass the corresponding column name as the trigger argument. Each column needs clear ownership/lifecycle.

### 12.6. DROP TABLE and TRUNCATE Do Not Fire Row Triggers

`lo_manage` is a row-level trigger:

- `DROP TABLE` does not invoke triggers per row.
- `TRUNCATE` does not invoke row-level DELETE triggers.

Both operations can leave behind orphaned LOs. If deleting rows before dropping, run `DELETE FROM table` so triggers fire, or run dedicated LO cleanup before/after DDL.

### 12.7. Do Not Confuse the lo Domain with Automatic Cleanup

`lo` is merely a domain over OID marking column intent. It does not create an FK to the LO catalog, does not delete objects on row deletion, and does not maintain reference counts.

## 13. Cleaning Orphaned Large Objects with vacuumlo

An orphaned Large Object is an LO with no remaining OID reference in columns recognized by cleanup tooling. Orphans waste disk even though no application uses them.

### 13.1. What Does vacuumlo Do?

`vacuumlo` is a client utility shipped with PostgreSQL. It:

1. Builds a set of all Large Object OIDs in the database.
2. Scans columns of type `oid` or `lo`.
3. Removes referenced OIDs from the candidate set.
4. Unlinks the remaining OIDs deemed orphaned.

This is a **real data-deletion tool**, not ordinary `VACUUM`.

### 13.2. Dry-Run Before Deleting

```bash
vacuumlo -n -v my_database
```

`-n`/`--dry-run` only prints which objects would be deleted without unlinking them. Review the list and verify schema/application references before running for real.

### 13.3. Running Bounded Cleanup

```bash
vacuumlo -v -l 1000 my_database
```

`-l` caps how many LOs are deleted per transaction; default is 1000. PostgreSQL acquires a lock per unlinked object, so batching too many in one transaction can exceed `max_locks_per_transaction`. Choose batch sizes matching capacity and schedules.

### 13.4. References Invisible to vacuumlo

`vacuumlo` scans `oid` and `lo` columns as documented. It cannot detect an OID serialized inside:

- `bigint` or `text` columns.
- JSON/JSONB.
- Arrays or custom encodings.
- Custom domains over OID unrecognized by the tool.
- External systems outside the database.

If applications store LO OIDs inside such structures, `vacuumlo` can mistake active objects for orphans and delete live data. Conversely, unrelated `oid` columns can falsely keep unused LOs alive because the tool sees matching OID values.

### 13.5. Safe Operational Workflow

1. Inventory every column and application holding LO OIDs.
2. Standardize references into `oid`/`lo` columns or an auditable registry table.
3. Run `vacuumlo -n -v` first.
4. Review candidate OIDs with data owners.
5. Take backups and verify restore readiness.
6. Run `vacuumlo` for real with an appropriate limit.
7. Monitor disk usage, runtime, locks, and application errors afterward.

### 13.6. vacuumlo Is a Backstop, Not Primary Lifecycle

Proper design unlinks LOs right inside the final delete/replace transaction. `vacuumlo` serves as periodic maintenance to catch orphans from legacy code, failed imports, or DDL operations—never as a substitute for reference management.

## 14. Safe Deletion and Replacement Workflows: Sample Patterns

### 14.1. One Row Exclusively Owning One LO (Unshared)

With exclusive ownership, you can create the new LO, update the row, and unlink the old LO inside one transaction:

```sql
BEGIN;

-- Fetch old OID and lock the row to prevent concurrent replacements.
SELECT content_oid
FROM storage_lab.attachments_lo
WHERE attachment_id = 10
FOR UPDATE;

-- Application creates new LO and streams bytes via LO API inside the transaction.
-- Let :new_oid be the newly written OID.

UPDATE storage_lab.attachments_lo
SET content_oid = :new_oid
WHERE attachment_id = 10;

-- Only after confirming old LO is not shared:
SELECT lo_unlink(:old_oid);

COMMIT;
```

This SQL uses `:new_oid`/`:old_oid` placeholders representing driver-bound values. If an error occurs, rollback restores the old row and old LO while undoing the newly created LO.

### 14.2. Deleting a Row Exclusively Owning an LO

```sql
BEGIN;

SELECT content_oid
FROM storage_lab.attachments_lo
WHERE attachment_id = 10
FOR UPDATE;

DELETE FROM storage_lab.attachments_lo
WHERE attachment_id = 10;

-- Application invokes only after verifying exclusive OID ownership:
SELECT lo_unlink(:old_oid);

COMMIT;
```

Deleting the row then unlinking ensures no dangling reference remains after commit. Within the transaction, both actions are atomic. When foreign keys, cascades, or multiple tables reference OIDs, check every referencing table before unlinking.

### 14.3. Never Unlink When Replacing Only One of Multiple References

If multiple rows share an OID, updating one row must change only that row's reference. Unlink only when the final reference is removed, serialized via a registry table, foreign keys, or refcount locking.

### 14.4. Soft Deletes

If the application sets `deleted_at` instead of running DELETE, DELETE triggers do not fire and the LO must stay intact for recovery/retention. Define retention windows; unlink only in a controlled purge job after expiration.

### 14.5. Retention and Legal Holds

Hiding a document from the UI does not permit physical deletion. Model `active`, `soft_deleted`, `retained`/legal hold states, and explicit purge schedules. Never let `vacuumlo` delete objects tracked outside standard row references if inventory tracking is incomplete.

### 14.6. Auditing and Checksums

Metadata should capture:

- Byte size.
- SHA-256 or suitable checksum.
- Validated/sniffed MIME type, never trusting client filenames blindly.
- Upload timestamp, owner/tenant, and source.
- Version/retention status.
- Object OID or asset ID (if LO).

Checksums detect corruption during upload/restore/migration; they are not encryption.



## 15. Security: Row Permissions Differ from Large Object Permissions

Large Objects have their own owner and ACLs. Since PostgreSQL 9.0, LO privileges are managed with GRANT/REVOKE:

- `SELECT` on LO: allows reading content.
- `UPDATE` on LO: allows writing or truncating content.
- Owner (or superuser): can unlink, change owner, and manage the object per privilege rules.

### 15.1. Granting Privileges on a Large Object

```sql
-- Example assuming OID 70001 exists:
GRANT SELECT
ON LARGE OBJECT 70001
TO app_file_reader;

GRANT UPDATE
ON LARGE OBJECT 70001
TO app_file_writer;
```

Do not grant UPDATE to read-only download roles. Never grant SELECT/UPDATE to `PUBLIC` without explicit justification.

### 15.2. Row Privileges Do Not Automatically Grant LO Privileges

A role may have SELECT on the metadata row yet lack SELECT on the LO, causing open/read calls to fail. Conversely, a role holding SELECT on an LO who knows its OID can read the object via LO ACLs even if RLS hides the referencing row.

**RLS protects rows in tables; Large Object ACLs protect objects separately.** The two layers do not synchronize automatically.

### 15.3. OIDs Are Not Secrets or Capabilities

OIDs can appear in logs, query outputs, backups, or APIs. Never treat hiding an OID as an authorization mechanism. Enforce proper LO ACLs, table privileges, and check user access to the asset metadata before serving reads.

### 15.4. Example Role Separation

One model:

| Role | Privileges |
| --- | --- |
| `storage_owner` | Creates/manages LOs and owns the metadata registry. |
| `app_upload` | Inserts metadata and writes new LOs in authorized transactions. |
| `app_download` | SELECTs eligible metadata and SELECTs granted LOs. |
| `app_reader` | SELECTs LOs only, no UPDATE. |
| `maintenance` | Runs approved orphan/retention cleanup. |

Never share table owner or superuser credentials across every API endpoint.

### 15.5. lo_compat_privileges

PostgreSQL includes `lo_compat_privileges` for legacy backward compatibility with pre-9.0 permission checks. Enabling it alters LO ACL enforcement. Never enable it just to silence permission-denied errors; grant proper SELECT/UPDATE privileges and test under production roles.

### 15.6. RLS on Tables Holding OIDs

Example:

```sql
ALTER TABLE app.attachments_lo
ENABLE ROW LEVEL SECURITY;

CREATE POLICY attachments_tenant_read
ON app.attachments_lo
FOR SELECT
TO app_runtime
USING (tenant_id = app.current_tenant_id());
```

This policy filters rows in the metadata table. It **does not enforce row-level security by tenant_id on `pg_largeobject`**. If an OID leaks via another path and the role holds LO SELECT ACL, a user could read the object. Design ACLs/ownership or service-layer isolation so object scope matches tenant boundaries.

### 15.7. Sharing OIDs Across Tenants Is a Design Risk

If two tenants reference the same LO, granting SELECT on that LO for tenant A also lets tenant A read an object referenced by tenant B. If sharing is required, model shared access explicitly or copy into separate tenant-owned LOs.

### 15.8. Server-Side Import/Export

Server-side `lo_import`/`lo_export` read/write the database server's filesystem. By default only superusers can invoke them; granting EXECUTE to others must be evaluated as a high-risk privilege. Prefer client-side streaming over JDBC/pgJDBC or libpq so files stay within controlled application filesystems.

## 16. Transactions, Concurrency, and Consistency

### 16.1. Create LO and Metadata in One Transaction

When both the LO and metadata row are created in the same transaction, commit publishes both and rollback undoes both. This is the simplest defense against orphaned new LOs.

### 16.2. Delete LO and Metadata in One Transaction

Once business logic verifies zero remaining references, delete the metadata row and call `lo_unlink` in the same transaction. If either fails, rollback keeps state consistent.

### 16.3. Lock Metadata Rows Before Replacing References

When concurrent requests may replace the same attachment, use `SELECT ... FOR UPDATE` on the metadata row to serialize reading the old OID, creating the new OID, and updating the reference. Across multiple referencing tables, enforce a unified locking/registry protocol.

### 16.4. Never Hold Transactions Open During Interactive Uploads

File uploads can take minutes. Never open a transaction, create an LO, hold row locks, and wait for slow client uploads or user input indefinitely. Upload to staging first, verify integrity, then run a short publish/attach transaction; enforce TTLs and cleanup for abandoned staging data.

### 16.5. Snapshots and Descriptors

LO descriptors live only for the current transaction. Ending the transaction closes descriptors; never cache descriptors inside Java/session state across requests. Each request must open LOs inside its own transaction.

### 16.6. Partial Updates and Consistency

LOs support random writes. If an application updates ranges across multiple transactions, readers observe versions per snapshot/transaction semantics. When a file must swap atomically as a complete version, create a new LO and flip the metadata reference upon completion rather than mutating a live served LO in place.

### 16.7. File Versioning

A safe model:

```text
Document
  |
  +-- active_version_id
           |
           v
      File version row
           |
           v
      BYTEA or LO reference

Upload new version -> verify/hash -> commit metadata
                   -> flip active_version_id
                   -> retention cleans old version
```

Versioning prevents readers from seeing half-written files and supports auditing/rollback. Define retention and access controls for historical versions.

## 17. Backup and Restore

Large Objects are separate data, not merely an OID number inside a metadata table. Backups must include **both LO contents and referencing rows**.

### 17.1. Full Database pg_dump

For full-database dumps, `pg_dump` includes Large Objects by default unless excluded or using restricted dump modes. Example:

```bash
pg_dump -Fc -b -f app_backup.dump my_database
```

`-b`/`--large-objects` explicitly requests including LOs in the archive. While default for full dumps, specifying `-b` documents intent clearly in runbooks.

### 17.2. Selective Table/Schema Dumps

When using `--table`, `--schema`, or `--schema-only`, LOs may not be included by default as in full dumps. Restoring a dump containing OID rows without the LOs leaves metadata with broken references.

When selective dumps need LOs, review `pg_dump --large-objects` and verify archive contents; note that this option includes all Large Objects in the database, not necessarily only those referenced by the selected tables.

### 17.3. Excluding LOs from a Dump

```bash
pg_dump -B -Fc -f schema_and_tables.dump my_database
```

`-B`/`--no-large-objects` intentionally omits LOs. Use only when a separate object backup/restore strategy exists and metadata OIDs are not expected to resolve immediately.

### 17.4. Restoring and Verifying

```bash
pg_restore -d restored_database app_backup.dump
```

After restore, verify:

- Metadata rows exist with expected OIDs.
- Large Objects actually open and read under application roles.
- LO owners/ACLs match target-environment roles.
- File bytes match expected sizes and checksums.
- No row references point to missing LOs.

### 17.5. Physical Backups

Physical base backups and WAL-based recovery capture database files/catalogs/WAL at the physical level; Large Objects are included automatically as system relations. Still run verified backup/restore drills and protect WAL/base backups.

### 17.6. Logical Replication Does Not Replicate Large Objects

**PostgreSQL logical replication does not replicate Large Objects.** If a metadata table with an OID column is replicated, the OID number arrives on the subscriber while the LO payload itself is absent. This is a critical trap when using logical replication for failover or read replicas.

`bytea` columns are ordinary table column data and replicate normally with table rows under logical replication (still account for size/version/workload limits, without the "LOs do not replicate" restriction).

When logical replication is required, choose:

- Use `bytea` if sizes and access patterns fit.
- Build a custom sync pipeline with versioning/checksums/idempotency for objects.
- Store files in external object storage and replicate metadata/references independently.

Never assume replicating a table containing OIDs delivers the files to subscribers.

### 17.7. Restoring to Another Database

OIDs are database-scoped identifiers. During restore, pg_dump/pg_restore recreate Large Objects and keep references consistent within the same archive; never copy an OID from database A and assume it points to identical bytes in an independently synced database B.

## 18. Migrating Between BYTEA and Large Objects

Migrations must address both data transfer and lifecycle handling, not merely altering column types.

### 18.1. BYTEA → LO for Payloads Within Limits

Add a new OID column:

```sql
ALTER TABLE storage_lab.attachments_bytea
ADD COLUMN content_oid oid;
```

For small/medium payloads, convert in batches inside transactions:

```sql
UPDATE storage_lab.attachments_bytea
SET content_oid = lo_from_bytea(0, content)
WHERE content_oid IS NULL
RETURNING attachment_id, content_oid;
```

`lo_from_bytea` takes a `bytea` argument, so this works only for datums that can be materialized within `bytea` bounds. Never run one massive UPDATE across millions of files; batch and validate progress.

### 18.2. BYTEA → LO for Very Large Files

A file exceeding 1 GB cannot fit in a `bytea` datum. If the source currently lives in external storage, stream directly from the application into LOs. If the source is `bytea`, it already fits within 1 GB; use JDBC `getBinaryStream` to copy in chunks instead of `getBytes` to avoid full-file heap allocation.

### 18.3. Verify Before Cutover

For every row:

- New OID is non-NULL.
- LO opens and reads cleanly.
- `octet_length`/LO size matches.
- SHA-256 of migrated content matches the source.
- Row metadata still preserves tenant/owner/file name.

Switch application reads to the OID column only after batch verification passes.

### 18.4. Drop Old BYTEA Only After Full Cutover

Retain the old column during canary/rollback windows. Only after applications run stably on LOs and backup/restore has been verified should you drop the `bytea` column in a separate migration. Never drop the old column before verifying all references and consumers.

### 18.5. LO → BYTEA

Only migrate LOs that fit within the `bytea` datum limit. Objects over 1 GB cannot be stored intact in a single `bytea` column.

Example for small LOs:

```sql
ALTER TABLE storage_lab.attachments_lo
ADD COLUMN content_bytea bytea;

UPDATE storage_lab.attachments_lo
SET content_bytea = lo_get(content_oid)
WHERE content_bytea IS NULL;
```

`lo_get` materializes content into `bytea`. Use only for small/medium objects with controlled memory; for larger data, stream via the application and enforce size limits beforehand.

### 18.6. Unlinking LOs After Migration

Only unlink old OIDs after:

1. New `bytea` values are written and checksum-verified.
2. All consumers have switched to the new column.
3. No other rows still reference the old OID.
4. Rollback/backup retention windows have elapsed per policy.

If LOs are shared across multiple references, consult the reference registry/refcount rather than checking only the current row.

### 18.7. Batch Migrations and Restartability

Across millions of rows, migrations need primary-key checkpointing, bounded batch sizes, metrics, and retries. Commit each batch independently; ensure idempotency so restarts never create duplicate LOs for already-migrated rows or leave orphans if an object is created before a failed metadata update. Transaction rollback or cleanup jobs must handle partial batch failures.

## 19. Performance and Operations

### 19.1. When BYTEA Shines

- Relatively small/medium payloads.
- Applications usually fetch the entire payload alongside metadata.
- Desire TOAST compression on compressible files/text.
- Need transactions, FKs, RLS, and standard DML without OID lifecycle overhead.
- No need to seek/write partial byte ranges inside objects.

### 19.2. When Large Objects Shine

- Huge payloads spanning multiple GBs or up to TBs.
- Applications read/write in chunks.
- Random access/seek is required.
- Must avoid materializing the entire datum at once.
- System accepts separate lifecycle, ACL, cleanup, and backup complexity.

### 19.3. TOAST Compression

`bytea` defaults to the `EXTENDED` strategy; PostgreSQL may compress before moving out-of-line. Already-compressed files (JPEG, MP4, ZIP, compressed PDFs) rarely shrink further. Compression consumes CPU and forces decompression on random substrings; choose compression strategies to match the workload.

### 19.4. Large Object Random Access

LOs split data into chunks and index them with a B-tree by position. This excels when clients read slices at arbitrary offsets without fetching the entire object. However, many tiny chunk reads over the network add round-trip latency; pick sensible application chunk and buffer sizes.

### 19.5. I/O and WAL

Both BYTEA and LO store data inside PostgreSQL and incur WAL, backups, physical replication, and disk pressure. Uploading huge files emits substantial WAL. Measure:

- Upload/download throughput.
- WAL volume and replication lag.
- Database disk growth.
- Shared buffers/cache hit ratios and I/O.
- Application heap/GC behavior.
- Transaction durations and lock waits.
- Backup/restore size and duration.

### 19.6. Inspecting Table Sizes

```sql
SELECT
    pg_size_pretty(
        pg_relation_size('storage_lab.attachments_bytea')
    ) AS heap_size,
    pg_size_pretty(
        pg_total_relation_size('storage_lab.attachments_bytea')
    ) AS total_with_toast_indexes;

SELECT
    pg_size_pretty(pg_total_relation_size('pg_largeobject'))
        AS large_object_storage,
    pg_size_pretty(
        pg_total_relation_size('pg_largeobject_metadata')
    ) AS large_object_metadata;
```

These are relation-level metrics, not an exact breakdown "per tenant or per file." Access to system catalogs/relations depends on role privileges. Use appropriate monitoring roles in production.

### 19.7. VACUUM and LOs

`lo_unlink` deletes an object via the API, deleting its chunks and metadata transactionally; it does not immediately shrink OS disk files. MVCC and VACUUM handle dead tuples and space reuse internally. `vacuumlo` sweeps orphaned LOs and differs from ordinary `VACUUM`.

### 19.8. Total Footprint Is More Than Raw File Bytes

Account for:

- Metadata rows, indexes, and TOAST/LO catalogs.
- Multiple versions if history is retained.
- Uncleaned orphan objects.
- WAL/archives and backup copies.
- Replica/standby storage.
- Temporary staging and failed uploads.

## 20. When Should Files Be Stored Outside PostgreSQL?

PostgreSQL works great when files participate directly in transactions at reasonable scale. Yet for large videos, CDN-delivered images, or data needing tiered lifecycle policies, object storage is often a better fit.

### 20.1. Storing Metadata and Object Keys

```sql
CREATE TABLE app.file_assets (
    asset_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id bigint NOT NULL,
    storage_provider text NOT NULL,
    object_key text NOT NULL,
    media_type text NOT NULL,
    byte_size bigint NOT NULL CHECK (byte_size >= 0),
    sha256_hex text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (storage_provider, object_key)
);
```

The DB manages metadata and authorization while the object store holds raw bytes. The backend checks authorization and issues signed URLs or streams appropriately.

### 20.2. DB Transactions and Object Storage Are Not Naturally Atomic

An upload can succeed in object storage while metadata INSERT fails, or metadata can commit while upload fails. Use a staging workflow:

1. Upload to a temporary key.
2. Verify size and checksum.
3. Inside a DB transaction, write metadata in ready state.
4. Promote/copy object or transition status per provider capabilities.
5. Run cleanup jobs for orphaned staging objects.

### 20.3. Requirements Comparison

| Requirement | PostgreSQL BYTEA/LO | Object Storage |
| --- | --- | --- |
| Same transaction as metadata | Yes, inside DB transaction. | No shared atomic transaction with DB. |
| Public/CDN file delivery | Needs app/proxy or gateway. | Usually far more convenient. |
| SQL constraints/joins with metadata | Direct. | Metadata in DB; bytes external. |
| Very large volume and heavy downloads | Strains DB, WAL, and backups. | Usually better optimized for object delivery. |
| Backup consistency | Bundled in DB backups when LO/bytea included. | Must coordinate object and metadata backups separately. |
| Lifecycle | Transactions/triggers/cleanup. | Bucket lifecycle, versioning, retention; still requires metadata sync. |

No single option fits every system. Decide based on workload, RPO/RTO, compliance, network/storage cost, and operational maturity.

## 21. Case Studies

### 21.1. Case A: 100–500 KB Profile Avatars

**Requirements:** user-owned images loaded alongside profiles, upload size-capped, transactional with metadata.

**Best initial fit:** `bytea`.

Reasons:

- Easy row and FK management.
- Deleting user/avatar aligns cleanly with transactions and FK rules.
- No OIDs, LO ACLs, or orphan cleanup needed.
- TOAST handles wide rows transparently.

If avatars serve millions of CDN requests, object storage may win operationally; still, there is no reason to pick Large Objects simply because avatars are binary.

### 21.2. Case B: 8 GB Video Requiring Offset Reads

**Requirements:** file exceeds the `bytea` datum limit and APIs serve byte ranges by offset.

Large Objects fit better than `bytea` inside PostgreSQL due to the 4 TB limit and chunked seek/read support. Design for:

- Chunked upload/download streaming.
- OID metadata, ownership, and ACLs.
- Delete/replace lifecycle and orphan cleanup.
- Full LO backup/restore.
- Awareness that logical replication skips LOs.

If streaming heavily to the public Internet/CDN, object storage is usually a stronger operational choice.

### 21.3. Case C: 15 MB PDF Documents with Rich Metadata and Auditing

If PDFs are always read in full and require atomicity with metadata rows, `bytea` is straightforward. If range/seek reads are needed or files grow into multi-GB territory, evaluate LOs or object storage. Never choose purely by megabyte count; benchmark access patterns and download rates.

### 21.4. Case D: Many Records Pointing to One Template File

**Requirements:** many invoices share one identical terms-and-conditions PDF.

Use a single asset row with invoices FK-linked to that asset. If the asset stores an LO, unlink the LO only when zero references remain. A registry table simplifies permissions, retention, and lifecycle far better than scattering duplicate OIDs across tables.

### 21.5. Case E: Logical Replication Where Subscribers Read Files

If the metadata table replicates yet LOs do not, subscribers receive OIDs they cannot read. Switch binary payloads to `bytea` on replicated tables, use synced external object storage, or build a dedicated LO sync pipeline. Never treat a replicated OID row as proof the file exists on subscribers.

### 21.6. Case F: JDBC Application Deleting Attachments

A DAO that only runs DELETE on `attachments_lo` leaves orphaned LOs behind. Fix by:

- Calling unlink in the same transaction when LOs are exclusively owned.
- Or deleting the final asset registry row so its trigger unlinks.
- Or running scheduled cleanup verified with dry-runs.

Test deletion, replacement, rollback, and concurrent shared references.

## 22. Common Mistakes

### Mistake 1. Thinking BYTEA Always Lives Inline in the Heap

BYTEA is a SQL column value, yet TOAST compresses and moves oversized values out-of-line automatically. Never build manual chunk tables for large files.

### Mistake 2. Thinking TOAST Makes BYTEA Unlimited

A TOAST-able datum still has a 1 GB logical limit. Physical chunking does not allow a single datum to exceed 1 GB.

### Mistake 3. Using getBytes for Very Large Files

`getBytes` materializes the full payload into a Java byte array, risking heap exhaustion and OutOfMemoryError. Stream where appropriate and enforce size caps.

### Mistake 4. Assuming BYTEA Streams Remove All Size Limits

JDBC streaming APIs do not lift the 1 GB `bytea` datum limit or driver/application buffer constraints.

### Mistake 5. Deleting an LO Row and Assuming the File Deletes Automatically

An OID is only a reference. Unlinking or cleanup must be handled explicitly.

### Mistake 6. Unlinking an LO Before Checking Shared References

If another row still holds that OID, it suffers a dangling reference. Enforce exclusive ownership or a registry/refcount.

### Mistake 7. Attaching lo_manage to a Shared LO Column

The `lo_manage` trigger assumes exclusive single-row ownership in its managed column. On shared OIDs, deleting one row breaks others.

### Mistake 8. Expecting lo_manage to Handle DROP TABLE / TRUNCATE

Row-level triggers do not fire for those statements. Run DELETE first or execute dedicated cleanup.

### Mistake 9. Running vacuumlo Without a Dry-Run

References stored in unrecognized custom types/domains or external systems can cause `vacuumlo` to treat active LOs as orphans and delete them. Always run `-n` first and maintain a reference inventory.

### Mistake 10. Using OIDs as Authorization Tokens

OIDs are not secrets or capabilities. LO ACLs, metadata permissions, and application authorization must all be enforced properly.

### Mistake 11. Thinking Row-Level RLS Protects LO Contents Directly

RLS filters rows holding OIDs; LOs carry independent ACLs. Leaked OIDs paired with permissive LO ACLs expose data unexpectedly.

### Mistake 12. Only Granting SELECT on the Metadata Table

Reading an OID from a row does not grant SELECT on the Large Object. Grant appropriate LO privileges while avoiding overly broad grants.

### Mistake 13. Using Server-Side lo_import for Web Uploads

Server-side functions read/write the PostgreSQL host's filesystem and carry severe security risks. Stream from clients/applications via JDBC/LO APIs instead.

### Mistake 14. Using lo_get to Download Multi-GB Files

`lo_get` returns `bytea`. Use it for small objects/slices; stream large files via the LO API.

### Mistake 15. Using 32-Bit APIs for LOs Larger Than 2 GB

`lo_lseek`/`lo_tell`/`lo_truncate` cap at 2 GB. Use 64-bit variants and matching driver APIs.

### Mistake 16. Opening Large Objects in Autocommit Mode

LO descriptors are valid only inside a transaction. Disable autocommit or use an explicit transaction manager.

### Mistake 17. Holding Descriptors Across Requests

Descriptors are scoped to a transaction/session. Store only the OID in metadata, opening a fresh descriptor per transaction and closing it afterward.

### Mistake 18. Updating an OID While Forgetting to Unlink the Old LO

The row points to the new file while the old file keeps consuming disk forever. Implement proper replace-and-cleanup workflows.

### Mistake 19. Dropping a Table with Cleanup Triggers Expecting Them to Fire

DROP TABLE does not fire row DELETE triggers. DELETE rows first or run independent cleanup.

### Mistake 20. Assuming Table-Only pg_dump Automatically Includes LOs

Selective dumps may exclude LOs by default. Check `-b` options and inspect the archive.

### Mistake 21. Expecting Logical Replication to Copy LOs to Subscribers

Large Objects are excluded from logical replication. Pick another storage model or build an explicit sync pipeline.

### Mistake 22. Treating Hashes as Absolute Security Proof

Hashes verify byte integrity, not file safety, malware absence, or uploader authorization. Enforce separate validation and access controls.

### Mistake 23. Trusting Client-Supplied Filenames and Content Types Blindly

Client filenames and MIME types are easily spoofed. Validate extensions, sniff content, cap sizes, and store sanitized metadata.

### Mistake 24. Ignoring WAL, Backup, and Replica Storage

In-DB binaries inflate WAL, backups, restores, and replica disk usage. Measure full-system impact, not only upload speed.

### Mistake 25. Converting LOs Back to BYTEA When Larger Than 1 GB

A 4 GB LO cannot fit inside a single `bytea` datum. Move to object storage or keep LOs; never attempt materializing via `lo_get`.

## 23. Practice Exercises

Exercises use the `storage_lab` schema from Sections 6–7. Run in a lab database; never run unlink or `vacuumlo` in production. Replace placeholder OIDs or file paths with valid values in your environment.

### Exercise 1. Data Model

Explain the difference between `content bytea` and `content_oid oid`. Which column actually holds bytes?

### Exercise 2. Limits

State the logical size limit of a `bytea` datum and the maximum Large Object size per PostgreSQL documentation.

### Exercise 3. TOAST

Does TOAST automatically split a large `bytea` into chunks? Does the application need to know the TOAST table name to read the file?

### Exercise 4. Storage Strategy

Distinguish `EXTENDED` from `EXTERNAL`. When can `EXTERNAL` help substrings?

### Exercise 5. BYTEA Insert

Write an INSERT using `decode(hex,'hex')` to store the bytes "Hi" and set `content_length` accurately.

### Exercise 6. BYTEA Size

Write a SELECT returning the byte count of `content` in the lab table using the proper function.

### Exercise 7. JDBC BYTEA Upload

Write Java code using `setBinaryStream` to upload a file into a `bytea` column; why must length be known?

### Exercise 8. JDBC BYTEA Download

Compare `getBytes` and `getBinaryStream` in terms of memory usage.

### Exercise 9. Creating an LO

Write SQL to create an empty LO and return its assigned OID.

### Exercise 10. Creating an LO from BYTEA

Write a `lo_from_bytea` statement creating an object holding the bytes "Hello".

### Exercise 11. Reading an LO

Write a `lo_get` statement reading the first 20 bytes from OID 12345.

### Exercise 12. Writing an LO

Write a `lo_put` statement writing the UTF-8 string "PG" at offset 0 of OID 12345.

### Exercise 13. Unlink

Write SQL to delete Large Object OID 12345 and state who is permitted to unlink it.

### Exercise 14. Row Delete

After `DELETE FROM attachments_lo WHERE attachment_id=10`, is the referenced Large Object automatically deleted?

### Exercise 15. JDBC LO Transaction

Why does pgJDBC require Large Object API calls to run inside a transaction? How must autocommit be configured?

### Exercise 16. LargeObjectManager

Write Java code obtaining `LargeObjectManager` from `PGConnection` and creating a new LO.

### Exercise 17. Seek64

Why do LOs larger than 2 GB require 64-bit seek/tell/truncate APIs?

### Exercise 18. lo_manage

Write SQL creating the `lo` extension and a cleanup trigger for column `raster lo` on UPDATE/DELETE.

### Exercise 19. Shared OID

Two rows reference the same OID. Why can attaching `lo_manage` directly on both rows delete a file still in use?

### Exercise 20. vacuumlo

Write the dry-run command listing orphaned LOs; explain why inspecting output before real deletion is critical.

### Exercise 21. TRUNCATE

Why can `TRUNCATE` on a table holding LO OIDs leave orphans even with a `lo_manage` trigger attached?

### Exercise 22. ACL

Write a GRANT allowing role `app_file_reader` to read LO OID 12345. What privilege does a role need to write?

### Exercise 23. RLS

A metadata table uses RLS to isolate tenants. Why does that not automatically isolate Large Object ACLs by tenant?

### Exercise 24. Backup

When running `pg_dump` selectively for one metadata table containing OIDs, which option must you check to include Large Objects?

### Exercise 25. Logical Replication

Does logical replication replicate Large Objects? If subscribers must download files, propose two solutions.

### Exercise 26. BYTEA → LO

Write SQL migrating a small `bytea` column to a new LO OID and state the size constraint.

### Exercise 27. LO → BYTEA

Why can a 2 GB LO not be converted into a single `bytea` column? Write an illustrative statement for a small LO.

### Exercise 28. Replace File

Outline the safe sequence for replacing an attachment's exclusively owned LO, including rollback behavior.

### Exercise 29. Reference Registry

Design an asset table and FK so multiple attachments share one LO, unlinking only when the final asset reference is deleted.

### Exercise 30. Choosing Storage Technology

A system stores 200 KB photos and 6 GB videos, needs a CDN, and uses logical replication for metadata. Choose BYTEA, LO, or object storage for each and explain why.

## 24. Exercise Reference Solutions

### Answer 1. Model

`content bytea` stores the row's binary datum directly. `content_oid oid` stores only an OID referencing a separate Large Object; bytes reside in the LO subsystem.

### Answer 2. Limits

A TOAST-able datum like `bytea` has a **1 GB** logical limit. Large Objects scale up to **4 TB** per PostgreSQL docs; objects beyond 2 GB require 64-bit offset/size APIs.

### Answer 3. TOAST

Yes. PostgreSQL automatically compresses and/or splits large values into chunks in a TOAST table when needed. Applications still read/write through the `bytea` column normally without accessing TOAST tables directly.

### Answer 4. EXTENDED and EXTERNAL

`EXTENDED` allows compression and out-of-line storage (common default). `EXTERNAL` stores out-of-line uncompressed; it can let substring reads on large bytea/text fetch only needed ranges at higher disk cost. Always benchmark.

### Answer 5. BYTEA Insert

```sql
INSERT INTO storage_lab.attachments_bytea (
    file_name, media_type, content, content_length
)
VALUES (
    'hi.txt',
    'text/plain',
    decode('4869', 'hex'),
    2
);
```

### Answer 6. Size

```sql
SELECT
    attachment_id,
    octet_length(content) AS byte_count
FROM storage_lab.attachments_bytea;
```

### Answer 7. JDBC BYTEA Upload

```java
long length = Files.size(path);
try (InputStream in = Files.newInputStream(path);
     PreparedStatement ps = conn.prepareStatement(
         "INSERT INTO storage_lab.attachments_bytea " +
         "(file_name,media_type,content,content_length) " +
         "VALUES (?,?,?,?)")) {
    ps.setString(1, path.getFileName().toString());
    ps.setString(2, "application/octet-stream");
    ps.setBinaryStream(3, in, length);
    ps.setLong(4, length);
    ps.executeUpdate();
}
```

The driver needs to know how many bytes to read from the stream; not all overloads support unknown lengths. With BYTEA, payloads must still stay within the 1 GB datum limit.

### Answer 8. getBytes vs. getBinaryStream

`getBytes` allocates a `byte[]` holding the entire value on the heap. `getBinaryStream` lets consumers read incrementally without holding one huge contiguous array, while remaining bound by BYTEA limits, buffering, and ResultSet/Connection lifetime.

### Answer 9. Creating an LO

```sql
SELECT lo_create(0) AS new_oid;
```

`0` lets PostgreSQL assign an available OID.

### Answer 10. lo_from_bytea

```sql
SELECT lo_from_bytea(
    0,
    convert_to('Hello', 'UTF8')
) AS new_oid;
```

This is for small payloads; never use `bytea` as an intermediate buffer for huge files.

### Answer 11. Reading an LO

```sql
SELECT lo_get(12345, 0, 20);
```

Large Object offsets are 0-based; returns `bytea` for the requested slice.

### Answer 12. Writing an LO

```sql
SELECT lo_put(
    12345,
    0,
    convert_to('PG', 'UTF8')
);
```

Must run inside a transaction, and caller needs UPDATE privilege on the LO.

### Answer 13. Unlink

```sql
SELECT lo_unlink(12345);
```

Only the LO owner or a superuser can unlink. Ensure zero valid references remain before deleting.

### Answer 14. Row Delete

No. DELETE removes the referencing row without deleting the Large Object. Call `lo_unlink`, use an appropriate trigger, or run a cleanup job.

### Answer 15. JDBC Transaction

LO descriptors are valid only inside a transaction; LO APIs require a transaction block. Set `conn.setAutoCommit(false)`, close descriptors/streams, and commit or roll back.

### Answer 16. LargeObjectManager

```java
conn.setAutoCommit(false);
PGConnection pg = conn.unwrap(PGConnection.class);
LargeObjectManager manager = pg.getLargeObjectAPI();
long oid = manager.createLO(
    LargeObjectManager.READWRITE
);
```

Then open the object, write bytes, store the OID in metadata, and commit inside the same transaction.

### Answer 17. Seek64

32-bit offset APIs cannot address offsets above 2 GB. Use `seek64`/`size64`/`truncate64` (pgJDBC) or 64-bit libpq functions for oversized objects.

### Answer 18. lo_manage

```sql
CREATE EXTENSION IF NOT EXISTS lo;

CREATE TABLE storage_lab.image_files (
    image_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title text NOT NULL,
    raster lo NOT NULL
);

CREATE TRIGGER image_files_raster_cleanup
BEFORE UPDATE OF raster OR DELETE
ON storage_lab.image_files
FOR EACH ROW
EXECUTE FUNCTION lo_manage(raster);
```

Use only if each LO is exclusively referenced via the trigger-managed column.

### Answer 19. Shared OID

Deleting row A triggers `lo_unlink` even though row B still stores the same OID, turning row B into a dangling reference. `lo_manage` assumes unique references; use an asset registry/refcount when sharing.

### Answer 20. vacuumlo

```bash
vacuumlo -n -v my_database
```

Dry-run lists candidate objects for deletion. Always inspect first because the tool scans only recognized `oid`/`lo` columns and misses OIDs inside text/JSON/custom types or external systems.

### Answer 21. TRUNCATE

`TRUNCATE` does not fire row-level DELETE triggers, so `lo_manage` never runs per row and LOs stay orphaned. Use DELETE instead or run dedicated cleanup; avoid TRUNCATE without handling LO lifecycle.

### Answer 22. ACL

```sql
GRANT SELECT
ON LARGE OBJECT 12345
TO app_file_reader;
```

To write or truncate, a role needs `UPDATE` privilege on the LO. Unlinking requires ownership or superuser.

### Answer 23. RLS

RLS filters metadata rows only. Large Objects have independent ACLs; anyone knowing an OID with SELECT ACL can read the LO even when RLS hides the metadata row. Enforce object ACLs/ownership and avoid leaking OIDs.

### Answer 24. Backup

When dumping selected tables/schemas, check `pg_dump --large-objects` or `-b` because selective dumps may omit LOs by default. Full-database dumps normally include LOs unless excluded; verify archives and restores.

### Answer 25. Logical Replication

No. Large Objects are not replicated by logical replication. Solutions:

1. Store qualifying payloads in `bytea` as a column of the published table (if sizes fit).
2. Use object storage or a custom LO sync pipeline with checksums, versioning, metadata, and error handling.

### Answer 26. BYTEA to LO

```sql
ALTER TABLE storage_lab.attachments_bytea
ADD COLUMN content_oid oid;

UPDATE storage_lab.attachments_bytea
SET content_oid = lo_from_bytea(0, content)
WHERE content_oid IS NULL;
```

Works only when each BYTEA datum stays within 1 GB and can be materialized. In production with large datasets, batch, verify checksums, and use streaming APIs if needed.

### Answer 27. LO to BYTEA

A `bytea` datum cannot exceed 1 GB. For small LOs:

```sql
UPDATE storage_lab.attachments_lo
SET content_bytea = lo_get(content_oid)
WHERE attachment_id = 10;
```

Use only when objects are small enough for memory; never call `lo_get` to materialize a 2 GB object as `bytea`.

### Answer 28. Replace File

Lock the metadata row; create the new LO and stream bytes inside the transaction; verify size/checksum; UPDATE the reference to the new OID; if the old OID was exclusively owned, unlink it in the same transaction; commit. On failure, rollback keeps the old row/OID intact and removes the new LO.

### Answer 29. Reference Registry

Create `assets(asset_id PK, content_oid UNIQUE)` and give attachments FK `asset_id REFERENCES assets ON DELETE RESTRICT`. Delete the asset only when zero attachments reference it; `lo_manage` on the asset table can safely unlink because each OID appears once in the registry. Forbid any other table from storing OIDs outside the registry.

### Answer 30. Technology Choice

- 200 KB photos: `bytea` is simplest if fetched with metadata; object storage also makes sense if heavily served via CDN.
- 6 GB videos: cannot fit in a single `bytea` datum. LOs support the size and seek, yet logical replication skips LOs and CDN traffic would overload the DB; object storage fits best.
- Metadata: keep in PostgreSQL with normal logical replication; sync object bytes via object storage versioning/checksum mechanisms.

## 25. BYTEA/LO Design Checklist

### 25.1. Choosing Storage Type

1. What are the maximum and real percentile file sizes?
2. Do applications read in full or seek/partial read-write?
3. Can `bytea` and TOAST fit comfortably within the 1 GB limit?
4. Are LOs genuinely needed over object storage?
5. Do logical replication or failover subscribers require binary data?

### 25.2. Metadata and Lifecycle

6. Does each LO have one unique owner/reference or is it shared?
7. Is there a registry/refcount if shared?
8. On upload failure, does transaction rollback delete the newly created LO?
9. On replace/delete, when is the old OID unlinked?
10. Are soft delete, retention, legal hold, and purge policies defined?
11. Is `lo_manage` used only where unique-reference assumptions hold?
12. Are TRUNCATE/DROP avoided when they would orphan LOs?
13. Are `vacuumlo` dry-runs and reference inventories maintained?

### 25.3. Security

14. Do table permissions/RLS enforce tenant isolation?
15. Are LO SELECT/UPDATE ACLs granted under least privilege?
16. Are OIDs kept out of client exposure and logs?
17. Are metadata row permissions distinguished from LO permissions?
18. Are server-side `lo_import`/`lo_export` blocked for application roles?
19. Are content size, type sniffing, checksums, and malware scans enforced?

### 25.4. JDBC and Transactions

20. Do BYTEA uploads use streams with exact lengths?
21. Do downloads use `InputStream` instead of `byte[]` for large files?
22. Do LO API calls run inside transactions with descriptors/streams closed cleanly?
23. Are connections/transactions kept out of interactive user waits or slow network stalls?
24. Do connection pools/transaction managers restore connection state cleanly?

### 25.5. Backups and Operations

25. Do selective `pg_dump` runs include LOs?
26. Do restore tests verify metadata, OIDs, bytes, and ACLs together?
27. Is logical replication free of hidden subscriber LO dependencies?
28. Are WAL, backup, and replica storage included in capacity planning?
29. Are checksums and metrics tracked for uploads, downloads, orphans, and cleanup?
30. Are migration and rollback plans tested on realistic data clones?

## 26. Summary

**Both `bytea` and Large Objects store binary data in PostgreSQL, yet they carry very different models and operational responsibilities.**

Core takeaways:

- `bytea` is a column value capped at 1 GB logically. TOAST compresses and/or moves oversized values out-of-line automatically; applications never manage chunks.
- Large Objects store content separately by OID in chunks, supporting streaming and random access up to 4 TB.
- In JDBC, `bytea` uses `setBytes`/`getBytes` or binary streams; LOs use the LargeObject API/Blob mapping and **must run inside a transaction**.
- Deleting a row holding an OID **does not automatically delete the LO**. You must manage `lo_unlink`, reference ownership, or cleanup.
- `lo_manage` helps with exclusive references, yet assumes each LO has only one reference in the managed column and does not handle DROP TABLE/TRUNCATE.
- `vacuumlo` is an orphan-cleanup backstop; always dry-run first and ensure all OID references reside in recognized column types.
- LO ACLs are separate from table privileges and RLS; OIDs are not secrets. Protect objects and metadata together.
- Full-database `pg_dump` normally includes LOs, whereas selective dumps need `-b` checks; logical replication **does not** replicate Large Objects.
- When CDNs, multi-TB media, or logical replication are required, object storage often fits better, paired with synchronized metadata and lifecycle controls.

Practical guiding principle:

> **Choose BYTEA for row-owned binary data that is easy to manage; choose Large Objects only when huge size or random access is genuinely required, and design ownership, ACLs, and cleanup from day one.**

## 27. References

Official documentation; consult the exact PostgreSQL major version and pgJDBC version you run:

- [PostgreSQL — Large Objects: Introduction](https://www.postgresql.org/docs/current/lo-intro.html): LO model, catalogs, and TOAST comparison.
- [PostgreSQL — Large Object Implementation Features](https://www.postgresql.org/docs/current/lo-implementation.html): chunks, random access, sparse allocation, and ACLs.
- [PostgreSQL — Large Object Client Interfaces](https://www.postgresql.org/docs/current/lo-interfaces.html): create/open/read/write/seek/truncate/unlink within transactions.
- [PostgreSQL — Large Object Server-Side Functions](https://www.postgresql.org/docs/current/lo-funcs.html): `lo_create`, `lo_get`, `lo_put`, `lo_unlink`, `lo_import`, and `lo_export`.
- [PostgreSQL — TOAST](https://www.postgresql.org/docs/current/storage-toast.html): datum limits, storage strategies, compression, and out-of-line storage.
- [PostgreSQL — lo module](https://www.postgresql.org/docs/current/lo.html): `lo` domain, `lo_manage` trigger, and limitations.
- [PostgreSQL — vacuumlo](https://www.postgresql.org/docs/current/vacuumlo.html): orphan LO cleanup and dry-run/limit flags.
- [PostgreSQL — pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html): `--large-objects`/`--no-large-objects` options and selective dumps.
- [PostgreSQL — Logical Replication Restrictions](https://www.postgresql.org/docs/current/logical-replication-restrictions.html): Large Objects are not replicated by logical replication.
- [PostgreSQL — Privileges](https://www.postgresql.org/docs/current/ddl-priv.html): SELECT/UPDATE privileges on Large Objects.
- [pgJDBC — Storing Binary Data](https://jdbc.postgresql.org/documentation/binary-data/): BYTEA streams, Blob mapping, and LO transaction requirements.
- [pgJDBC — LargeObject API](https://jdbc.postgresql.org/documentation/publicapi/org/postgresql/largeobject/LargeObject.html): streaming, seek, read/write, truncate, and close.
- [pgJDBC — LargeObjectManager](https://jdbc.postgresql.org/documentation/publicapi/org/postgresql/largeobject/LargeObjectManager.html): creating/opening/deleting Large Objects from JDBC.



