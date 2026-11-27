# Row Size Limits, Key Length Limits, and Off-Page Storage

When designing InnoDB tables, you must simultaneously account for three limits: the row size limit, index key length limits, and how columns with large values are stored. A table may declare many `VARCHAR`, `TEXT`, or `BLOB` columns, yet that does not mean every byte of every column lives directly inside a single data page. InnoDB can move portions of large data to overflow (off-page) pages while keeping a pointer inside the main-page record.

These limits impact schema design, indexes, primary keys, query performance, and storage footprint. In the `DATABASE_MYSQL` module, understanding them helps you prevent `Row size too large` errors and index key length errors while choosing proper data types for applications storing large content.

## Objectives

After this lesson, you will be able to:

- Distinguish the SQL-layer row size limit from InnoDB's physical inline record limit.
- Explain the relationship between page size, row format, and off-page storage.
- Compare `COMPACT`, `DYNAMIC`, and `COMPRESSED` when storing long columns.
- Estimate index key lengths based on charset and column length.
- Design compact primary keys, composite indexes, and appropriate prefix indexes.
- Diagnose row size and index key errors and inspect table structures via MySQL metadata.

## 1. Three Concepts to Distinguish

| Concept | Meaning | Related Limit or Mechanism |
|---|---|---|
| SQL-layer row size | Maximum total size of columns in the row definition under MySQL rules | MySQL enforces a 65,535-byte row size limit; `BLOB`/`TEXT` count primarily via metadata/pointers rather than full payload |
| InnoDB record on a page | Inline data and record metadata residing inside an InnoDB page | Inline record size is bounded by page size; with 16KB pages, the limit is typically described as slightly under half a page, roughly 8KB |
| Index key length | Maximum bytes of columns/prefixes participating in an index key | Depends on page size, row format, charset, and total length of key parts |

These three limits do not substitute for one another. A table can exceed the 65,535-byte SQL-layer limit even though InnoDB can store some columns off-page. Conversely, a table definition can pass the SQL limit yet hit InnoDB's inline record limit at creation or write time. Indexes also carry their own limits even when column data is stored off-page.

## 2. SQL-Layer Row Size Limit

MySQL enforces a maximum SQL-layer row size of 65,535 bytes. When calculating this limit, MySQL considers the maximum byte size of columns and required overhead. For `VARCHAR`, the declared length is in characters, while maximum byte storage depends on the character set.

For example, `VARCHAR(255)` with `utf8mb4` can require up to 1,020 bytes of character data because one character can occupy up to 4 bytes. A `VARCHAR` column also includes length-prefix bytes and other metadata. Therefore, you cannot simply add declared character counts to verify a table fits within the limit.

```sql
CREATE TABLE profile_text (
    id BIGINT UNSIGNED NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    biography VARCHAR(1000),
    PRIMARY KEY (id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

`VARCHAR(1000)` permits up to 1,000 characters; it does not mean every row consumes 4,000 bytes for that column. On write, `VARCHAR` typically stores actual length plus length overhead; when validating table definition capacity, MySQL checks the theoretical maximum.

### 2.1. Why Do `TEXT` and `BLOB` Differ from `VARCHAR`?

`TEXT` and `BLOB` are designed for long content. In MySQL's row size calculation, their full payloads do not count like an inline `VARCHAR`; only a small metadata/pointer portion (typically around 9–12 bytes depending on type) counts toward the SQL row size. Large payloads are managed separately by the storage engine.

This lets a table define multiple large content columns without immediately hitting the SQL row size limit upon declaration. However, it does not make storage free: content still consumes tablespace capacity and may require overflow pages, extra I/O, and memory during queries.

Do not convert every large `VARCHAR` into `TEXT` merely to bypass errors. Consider semantics, length constraints, indexing requirements, default value rules per MySQL version, application validation, and read/write workloads.

### 2.2. Example Table Exceeding the SQL Row Size Limit

A table with many `VARCHAR(255)` columns using `utf8mb4` can exceed 65,535 bytes even though each column looks modest:

```sql
-- Example illustrating a definition that can exceed MySQL's row size limit.
CREATE TABLE wide_profile (
    id BIGINT UNSIGNED NOT NULL,
    field_01 VARCHAR(255),
    field_02 VARCHAR(255),
    field_03 VARCHAR(255),
    field_04 VARCHAR(255),
    field_05 VARCHAR(255),
    field_06 VARCHAR(255),
    field_07 VARCHAR(255),
    field_08 VARCHAR(255),
    field_09 VARCHAR(255),
    field_10 VARCHAR(255),
    -- In a real schema, repeating many similar columns can exceed 65,535 bytes.
    PRIMARY KEY (id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

Ten columns in this example may not cross the limit yet; the exact column count depends on types, charset, and overhead. The key point is calculating by maximum bytes, not character count. If many independent fields are needed, consider splitting the table in a one-to-one relationship or attribute groups, or using `TEXT` for long content where semantics fit.

## 3. InnoDB Inline Record Limit

InnoDB stores data in pages. With the common `innodb_page_size=16384` (16KB), the inline size of a single record on a page is capped slightly below half a page, roughly 8KB. The remaining space covers page structures, page directory, record headers, and internal metadata. The exact limit is not strictly `page_size / 2` for every schema.

InnoDB also stores per-record metadata, such as:

- Record headers and management fields.
- A bitmap for nullable columns.
- Length/offset information for variable-length columns.
- InnoDB system columns such as transaction ID and rollback pointer; tables without an explicit primary key also carry a hidden row ID.

Thus, space available for user data is always less than the page size and depends on row structure.

### 3.1. How Does Page Size Affect Limits?

Inspect the instance's page size:

```sql
SELECT @@innodb_page_size;
```

MySQL/InnoDB supports several page sizes chosen at instance initialization—commonly 4KB, 8KB, 16KB, 32KB, or 64KB depending on platform and build. The standard default is 16KB. `innodb_page_size` cannot be changed arbitrarily on an existing data directory; changing page size generally requires initializing a new instance and migrating data cleanly.

Never increase page size merely to silence a single row size error. Page size also affects index key limits, I/O behavior, page footprint, and compatibility with storage features. Evaluate the full workload and version constraints before choosing a page size.

### 3.2. The `Row size too large` Error

When an inline record can exceed the limit, MySQL may raise an error such as:

```text
ERROR 1118 (42000): Row size too large (...).
```

The message typically indicates the threshold of the current page/row format. Do not work around it by disabling strict mode or forcing the server to accept a fragile schema. Inspect column types, charsets, row format, and opportunities to move long columns to off-page storage.

## 4. Row Formats and Off-Page Storage

InnoDB supports row formats including `REDUNDANT`, `COMPACT`, `DYNAMIC`, and `COMPRESSED`. In standard MySQL 8.0 releases, `DYNAMIC` is the default row format. The row format dictates how records are encoded and whether long columns are stored inline or off-page.

| Row Format | Characteristics Regarding Long Columns |
|---|---|
| `REDUNDANT` | Legacy row format using older record layout; avoid for new tables unless specifically required for compatibility |
| `COMPACT` | Keeps up to the first 768 bytes of `BLOB`/`TEXT` values inline in the clustered index record and stores the remainder on overflow pages; record holds a 20-byte pointer |
| `DYNAMIC` | Can store the entire long column value off-page and keep a 20-byte pointer in the record when needed; minimizes inline bloat |
| `COMPRESSED` | Built on `COMPACT`/`DYNAMIC`-style record layout with page compression; compression and off-page behavior depend on configuration, page size, and version |

### 4.1. COMPACT: Keeping an Inline Prefix

With `COMPACT`, InnoDB stores the first 768 bytes of `BLOB`/`TEXT` values inline inside the clustered index record; the remainder moves to overflow pages. The record contains a 20-byte pointer referencing the off-page data.

This means a long `TEXT` column can still bloat the inline record substantially if many columns each retain a 768-byte prefix. When a table has numerous long columns, the sum of inline prefixes can push the record past the limit.

### 4.2. DYNAMIC: Moving the Entire Long Value Off-Page

With `DYNAMIC`, when InnoDB moves a long column off-page, the entire value can reside on overflow pages while the clustered index record keeps just a 20-byte pointer. This reduces inline data size and is generally far better suited for tables with multiple large `VARCHAR`, `TEXT`, or `BLOB` columns.

InnoDB does not automatically push every long column off-page when creating a table. The engine decides based on actual record size and storage conditions. Short values can remain inline; when a record grows too large, InnoDB selects suitable variable-length columns to move off-page until the record fits within the inline threshold.

### 4.3. COMPRESSED

`COMPRESSED` stores pages in compressed form with its own long-column/off-page behavior. Compression can reduce disk usage and I/O, yet adds CPU cost, can trigger page reorganization, and faces compatibility limits across page sizes, filesystems, and versions. Do not select `COMPRESSED` solely to bypass a row-size limit; benchmark and verify deployment documentation.

### 4.4. Inspecting and Changing Row Formats

Inspect the current row format:

```sql
SHOW TABLE STATUS LIKE 'profile_text'\G
SHOW CREATE TABLE profile_text\G
```

Or query metadata:

```sql
SELECT TABLE_NAME, ROW_FORMAT
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'profile_text';
```

Create a new table using `DYNAMIC`:

```sql
CREATE TABLE document_store (
    document_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    body LONGTEXT,
    attachment LONGBLOB,
    PRIMARY KEY (document_id)
) ENGINE=InnoDB
  ROW_FORMAT=DYNAMIC
  DEFAULT CHARSET=utf8mb4;
```

Change the row format of an existing table:

```sql
ALTER TABLE profile_text ROW_FORMAT=DYNAMIC;
```

Changing row format can rebuild the table, generate heavy I/O, and require temporary disk space. Test on a replica, verify supported DDL algorithms, locking duration, and free disk space before executing in production.

## 5. Index Key Length Limits

InnoDB caps maximum index key length based on page size and row format. With a 16KB page size, the standard limit for `DYNAMIC`/`COMPRESSED` is 3,072 bytes; with 8KB pages, 1,536 bytes; with 4KB pages, 768 bytes. `REDUNDANT` and `COMPACT` row formats carry a legacy 767-byte index key limit in corresponding configurations.

These limits are measured in bytes, not characters. With `utf8mb4`, a single character can take up to 4 bytes. Therefore, an index on `VARCHAR(1000)` using `utf8mb4` can require up to 4,000 bytes for character data alone, exceeding the 3,072-byte limit on a 16KB page.

### 5.1. Example of an Oversized Index Key

```sql
CREATE TABLE customer_directory (
    customer_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(1000) NOT NULL,
    PRIMARY KEY (customer_id),
    KEY idx_customer_email (email)
) ENGINE=InnoDB
  ROW_FORMAT=DYNAMIC
  DEFAULT CHARSET=utf8mb4;
```

Indexing the entire `email` column can exceed the key limit because `VARCHAR(1000)` in `utf8mb4` can require up to 4,000 bytes before length overhead. The server may report:

```text
ERROR 1071 (42000): Specified key was too long; max key length is ... bytes
```

### 5.2. Prefix Indexes

For `VARCHAR`, `TEXT`, or `BLOB` columns, you can index a leading prefix when business rules and query patterns permit:

```sql
CREATE TABLE customer_directory (
    customer_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(1000) NOT NULL,
    PRIMARY KEY (customer_id),
    KEY idx_customer_email_prefix (email(191))
) ENGINE=InnoDB
  ROW_FORMAT=DYNAMIC
  DEFAULT CHARSET=utf8mb4;
```

Prefix `191` specifies characters for non-binary string columns; with `utf8mb4`, the character portion requires up to 764 bytes. The number 191 frequently appears in older schemas because 191 × 4 = 764, sitting just under the legacy 767-byte limit. On modern configurations with a 3,072-byte limit, you can choose a longer prefix if needed, while summing total key bytes and evaluating selectivity.

A prefix index does not store the full column value. If a query must distinguish two emails sharing the same first 191 characters, MySQL may have to read the record and inspect the remaining characters. The index can still accelerate searches, though effectiveness depends on data distribution and real queries.

For `TEXT` and `BLOB`, MySQL requires specifying a prefix length when creating an index. For `VARCHAR`, prefix length is optional. Avoid overly short prefixes if many rows share the same prefix, as low selectivity makes the index ineffective.

### 5.3. Composite Indexes Sum Component Lengths

The key length of a composite index is the sum of maximum bytes of all participating key parts plus related overhead. You cannot assume each column gets its own 3,072-byte allowance.

Example:

```sql
CREATE TABLE tenant_contact (
    contact_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    email VARCHAR(800) NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    PRIMARY KEY (contact_id),
    KEY idx_tenant_email (tenant_id, email(150)),
    KEY idx_tenant_name (tenant_id, display_name(150))
) ENGINE=InnoDB
  ROW_FORMAT=DYNAMIC
  DEFAULT CHARSET=utf8mb4;
```

In `idx_tenant_name`, `tenant_id` takes 8 bytes and the `display_name(150)` prefix can take up to 600 bytes for `utf8mb4` characters, plus overhead. When designing composite indexes, sum all columns/prefixes, order columns according to query access patterns, and keep total key length below configuration limits.

## 6. Wide Primary Keys Inflate Secondary Indexes

InnoDB uses a clustered index to store rows ordered by the primary key. Every secondary index also stores the corresponding primary key value to locate the row in the clustered index. Consequently, the primary key affects not only the primary index; it inflates the size of every secondary index as well.

For example, a table with a `BIGINT` primary key and five secondary indexes stores that 8-byte primary key in every entry of each secondary index. If the primary key is a wide string, the repeated cost across secondary indexes grows substantially. At millions or billions of rows, this difference impacts disk usage, buffer pool efficiency, and page reads.

Design principles:

- Prefer compact, stable, immutable primary keys.
- Avoid using a long string as a primary key when a more compact surrogate key works.
- If using a composite primary key, include only the essential columns.
- Inspect existing secondary indexes before widening a primary key's type.
- Keep foreign key types and signedness compatible with the referenced primary key.

This does not mean every table must use an auto-incrementing integer. Natural keys can make sense when they are short, stable, and uniquely identify business entities. Weigh storage cost, join ergonomics, stability, and distributed ID requirements.

## 7. Calculating Bytes by Charset and Column Metadata

For string types, `CHARACTER_MAXIMUM_LENGTH` reports maximum character count, whereas `CHARACTER_OCTET_LENGTH` reports maximum byte length under the charset. Query metadata to estimate sizes:

```sql
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    COLUMN_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    CHARACTER_OCTET_LENGTH,
    CHARACTER_SET_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customer_directory';
```

`CHARACTER_OCTET_LENGTH` helps spot columns whose maximum byte size exceeds their declared character count. With `utf8mb4`, the maximum byte length is typically four times the character count; with other charsets, the multiplier varies.

Inspect indexes and prefix lengths:

```sql
SHOW INDEX FROM customer_directory;
```

Inspect the index key length used by the optimizer:

```sql
EXPLAIN
SELECT customer_id
FROM customer_directory
WHERE email = 'learner@example.com';
```

The `key_len` column in `EXPLAIN` output indicates the key length in bytes used by the optimizer in the access path, which may include nullability and variable-length overhead. It is not always the full maximum length of the entire index; read it alongside `key`, `ref`, `rows`, and `SHOW INDEX`.

## 8. Diagnostic Workflow for Row Size and Index Key Errors

When encountering a table or index creation error, check in order:

1. Identify accurately whether the error is row size (`1118`) or key length (`1071`). They have different root causes and fixes.
2. Check `@@innodb_page_size`, `@@innodb_default_row_format`, and the table's actual row format.
3. Inspect charset/collation at table and string-column levels; use `CHARACTER_OCTET_LENGTH` instead of reading character length alone.
4. For row size errors, sum approximate maximum bytes of inline columns including overhead, nullability, and variable-length bytes; identify wide columns suitable for splitting or off-page storage.
5. For index key errors, sum maximum bytes of all columns/prefixes in the index; inspect primary and composite indexes.
6. Run `SHOW CREATE TABLE`, `SHOW TABLE STATUS`, and `SHOW INDEX` to verify the actual structure.
7. Test changes in a lab environment or near-production-sized data copy, then measure storage footprint and latency.

Configuration inspection commands:

```sql
SELECT
    @@innodb_page_size AS page_size_bytes,
    @@innodb_default_row_format AS default_row_format,
    @@character_set_server AS server_charset,
    @@collation_server AS server_collation;

SHOW CREATE TABLE customer_directory\G
SHOW TABLE STATUS LIKE 'customer_directory'\G
SHOW INDEX FROM customer_directory;
```

### 8.1. Resolution Strategies by Error Type

| Error | Common Cause | Resolution |
|---|---|---|
| `Row size too large` at SQL layer | Maximum column bytes exceed 65,535 bytes | Reduce declared lengths, split tables, or use `TEXT`/`BLOB` for long content where semantically appropriate |
| `Row size too large` in InnoDB | Inline record exceeds page/row-format threshold | Use `DYNAMIC` if appropriate, reduce inline data, split groups of wide columns, or adjust schema |
| `Specified key was too long` | Total index key bytes exceed page-size/row-format limit | Use a selective prefix index, shorten column length, change charset if appropriate, or redesign composite indexes |
| Oversized secondary indexes | Wide primary key repeated inside every secondary index | Shorten primary key if data model allows; drop redundant indexes |

Converting a column to `TEXT` can reduce its SQL row size contribution and enable off-page storage, yet indexing `TEXT` requires prefixes and reading payloads may incur extra I/O. Splitting tables can require additional joins. Each fix has trade-offs; choose based on access patterns.

## 9. Table Design Example for Large Content

Suppose an application stores documents consisting of frequently queried metadata and large payloads. Avoid cramming all content into a table with many wide `VARCHAR` columns if most queries only read metadata.

A design can separate metadata and payload:

```sql
CREATE TABLE document (
    document_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (document_id),
    KEY idx_document_tenant_created (tenant_id, created_at)
) ENGINE=InnoDB
  ROW_FORMAT=DYNAMIC
  DEFAULT CHARSET=utf8mb4;

CREATE TABLE document_payload (
    document_id BIGINT UNSIGNED NOT NULL,
    body LONGBLOB NOT NULL,
    PRIMARY KEY (document_id),
    CONSTRAINT fk_document_payload_document
        FOREIGN KEY (document_id)
        REFERENCES document (document_id)
        ON DELETE CASCADE
) ENGINE=InnoDB
  ROW_FORMAT=DYNAMIC;
```

Document list queries read only metadata:

```sql
SELECT document_id, title, content_type, created_at
FROM document
WHERE tenant_id = 42
ORDER BY created_at DESC
LIMIT 50;
```

Only when a user opens a document does the application fetch the payload:

```sql
SELECT body
FROM document_payload
WHERE document_id = 9001;
```

This design avoids dragging large payloads into frequent list queries. In return, reading a full document requires querying the payload table as well. If content is almost always accessed together with metadata, keeping one table with `DYNAMIC` may be simpler. Measure your workload to decide.

## 10. Practice Lab

Perform in a dedicated lab database using MySQL 8.x and InnoDB:

1. Create two tables with identical long string columns, one with `ROW_FORMAT=COMPACT` and one with `ROW_FORMAT=DYNAMIC`. Check `SHOW TABLE STATUS` to verify row format.
2. Insert short and long values into `TEXT`/`LONGTEXT` columns. Observe table and index sizes before and after using appropriate statistics tools; explain why short values may remain inline while long values move off-page.
3. Create a table with multiple `VARCHAR(255)` columns in `utf8mb4`. Estimate maximum row size in bytes and observe the limit when adding more columns in the lab.
4. Create an index on `VARCHAR(1000)` `utf8mb4`, noting the key length error if it exceeds limits. Test a prefix index and compare `EXPLAIN` and selectivity.
5. Create a composite index combining one numeric column and two string columns; calculate maximum total key bytes and adjust prefixes to fit within limits.
6. Compare a table with an `INT` vs. `BIGINT` primary key and one with a string primary key; add a few secondary indexes and observe index sizes.
7. Use `information_schema.COLUMNS`, `SHOW CREATE TABLE`, `SHOW INDEX`, and `EXPLAIN` to compile a report on row format, charset, byte length, and key length.
8. Redesign a wide table by separating metadata from payload. Compare the columns and bytes read in list queries before and after the change.

You have completed this lesson when you can explain the two distinct row size limits, predict index key byte sizes by charset, identify when long data moves off-page, and select an appropriate resolution for each error.

## 11. Design Principles

- Calculate sizes by maximum bytes, not merely declared character counts.
- Distinguish the 65,535-byte SQL row size limit from InnoDB's page-size-dependent inline record limit.
- Use `DYNAMIC` for tables with large variable-length columns when appropriate; verify actual row format.
- Remember that off-page storage still consumes space and can incur extra I/O when reading payloads.
- Sum bytes across all components of a composite index; `utf8mb4` can use up to 4 bytes per character.
- Design compact primary keys because InnoDB duplicates them inside every secondary index.
- Use prefix indexes when selectivity and queries fit; never truncate prefixes solely to make DDL succeed.
- Benchmark and test DDL in a production-like environment before changing row formats, page sizes, or table structures.
