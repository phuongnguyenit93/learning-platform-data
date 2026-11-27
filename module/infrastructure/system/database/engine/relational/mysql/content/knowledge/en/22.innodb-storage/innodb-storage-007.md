# Off-Page TEXT/BLOB Data and Record Size Limits

InnoDB stores data rows inside tablespace pages. A row can have many columns, yet not every byte of a large value must reside in the page holding the record. For columns with long values such as `TEXT`, `BLOB`, or large `VARCHAR`, InnoDB can move the long data portion to overflow pages (off-page storage) and keep a pointer in the clustered index record.

Off-page storage behavior depends on the row format. `COMPACT` and `REDUNDANT` keep a prefix of up to 768 bytes inside the record and store the remainder off-page; `DYNAMIC` and `COMPRESSED` can store the entire value off-page when InnoDB decides to externalize a column. Even with off-page storage, a table remains subject to the SQL-layer row-size limit and the internal record limit dictated by the InnoDB page size.

Understanding these two limits helps diagnose `Row size too large` errors, choose a row format, design tables with LOB columns, and avoid reading large payloads when queries only need metadata.

## 1. Records, Pages, and Off-Page Storage

InnoDB organizes data into pages. With the common default configuration, `innodb_page_size` is 16 KiB. An InnoDB table has a clustered index; each row's record resides in a leaf page of the clustered index. If a row has very large variable-length values, keeping all bytes in the same page reduces how many records fit and can exceed the internal record size limit.

InnoDB solves this by storing part of a large value in the record and moving the remainder to separate pages. These pages are commonly called overflow pages or BLOB pages. The record in the clustered index keeps the information needed to locate the data stored off-page.

**Off-page does not mean data is stored on another server or in a file outside MySQL.** The data still belongs to the InnoDB tablespace; it simply resides on pages separate from the main record's page. With file-per-table, these pages typically reside in the corresponding table's tablespace.

Externalizing can make the primary record more compact, but when a query needs to read the entire value, InnoDB must access the additional pages holding that data. Thus, off-page storage resolves record-size limits rather than making LOB reads free.

## 2. Two Row-Size Limits to Distinguish

MySQL enforces a row-size limit at the SQL layer, and InnoDB enforces an internal record limit tied to the page size. These two limits are distinct:

| Limit | Scope | Value / Characteristics |
| --- | --- | --- |
| SQL row-size limit | Total row size according to how MySQL represents columns | Maximum 65,535 bytes; actual content of `TEXT`/`BLOB` is stored separately and contributes only about 9–12 bytes of metadata to this calculation |
| InnoDB maximum row size | Record residing inside an InnoDB page, excluding full externalized LOB content | Slightly less than half the page size |

With a 16 KiB page size, the maximum internal record size is typically slightly under ~8 KiB. The exact number can be lower due to record headers, transaction metadata, directory slots, and other overhead. When an error reports `Row size too large (> 8126)`, this is usually the InnoDB record limit on a 16 KiB page, not the 65,535-byte SQL-layer limit.

### 2.1. The 65,535-Byte Limit at the SQL Layer

MySQL limits total row size to 65,535 bytes. When calculating this limit, the contents of `TEXT` and `BLOB` are not counted in full like `VARCHAR` columns; they contribute only length metadata, typically about 9–12 bytes depending on type. However, `VARCHAR`, `CHAR`, numeric, datetime, and metadata of other columns all count toward the row size.

For example, a table with several `VARCHAR(10000)` columns using the `utf8mb4` charset can exceed the SQL row-size limit even if actual stored data is short. `utf8mb4` can require up to 4 bytes per character, so a declared character length does not mean the maximum byte count equals the character count.

Changing some large columns from `VARCHAR` to `TEXT` can reduce their contribution to the SQL row-size limit, though it is not a cure-all. You must also consider internal record limits, row format, column count, and actual data.

### 2.2. InnoDB Record Limit by Page Size

InnoDB needs to keep the main record small enough to fit on a page. The general rule is that the maximum row size is slightly less than half the page size:

| `innodb_page_size` | Approximate record limit before overhead |
| ---: | ---: |
| 4 KiB | Slightly less than ~2 KiB |
| 8 KiB | Slightly less than ~4 KiB |
| 16 KiB | Slightly less than ~8 KiB |
| 32 KiB | Slightly less than ~16 KiB |
| 64 KiB | Slightly less than ~32 KiB |

This is a rule of thumb for understanding the limit, not a guarantee that a record can use exactly half a page. Record headers, the page directory, metadata, and column storage layout reduce usable capacity.

Check the page size:

```sql
SELECT @@innodb_page_size AS innodb_page_size_bytes;
```

`innodb_page_size` is chosen when initializing the instance and cannot be changed with a `SET` command on a running instance. Choosing a different page size usually requires creating a new instance and migrating data according to a plan.

## 3. TEXT and BLOB Types

MySQL has four sizes for each of the `TEXT` and `BLOB` groups:

| Type | Maximum data capacity by type | Notes |
| --- | ---: | --- |
| `TINYTEXT` / `TINYBLOB` | 255 bytes | Small values |
| `TEXT` / `BLOB` | 65,535 bytes | Corresponds to 16-bit length limit |
| `MEDIUMTEXT` / `MEDIUMBLOB` | 16,777,215 bytes | Nearly 16 MiB |
| `LONGTEXT` / `LONGBLOB` | 4,294,967,295 bytes | Nearly 4 GiB per type limit |

These are theoretical limits by data type. Practical values are also constrained by `max_allowed_packet`, client/driver capabilities, memory, protocol, server configuration, and storage resources. Do not assume `LONGBLOB` means every application can send a nearly 4 GiB value in a single statement.

### 3.1. TEXT Is Character Data

`TEXT` stores content according to the column's character set and collation. Length is defined by the byte capacity of the TEXT variant, not a fixed character count. A single UTF-8 character can occupy multiple bytes.

```sql
CREATE TABLE articles (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(300) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    PRIMARY KEY (article_id)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

With `utf8mb4`, a 10,000-character string can require more than 10,000 bytes. Actual space depends on the characters stored.

### 3.2. BLOB Is Binary Data

`BLOB` stores raw binary bytes and does not apply character set conversions like `TEXT`. It is suitable for images, attachments, compressed content, or binary payloads.

```sql
CREATE TABLE document_attachments (
    attachment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    file_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    file_data LONGBLOB NOT NULL,
    PRIMARY KEY (attachment_id)
) ENGINE=InnoDB;
```

When comparing `TEXT`, collation rules can cause two strings to be treated as equal despite case or accent differences. With `BLOB`, comparisons are byte-based. Do not use BLOB to store text solely to avoid thinking about charsets; doing so loses text semantics and makes queries harder to read.

## 4. Measuring Bytes and Characters

When diagnosing sizes, distinguish bytes from characters:

- `CHAR_LENGTH(value)` returns the number of characters.
- `OCTET_LENGTH(value)` returns the number of bytes.
- `LENGTH(value)` in MySQL also returns the number of bytes.

Example:

```sql
SELECT
    'Cơ sở dữ liệu' AS sample_text,
    CHAR_LENGTH('Cơ sở dữ liệu') AS character_count,
    OCTET_LENGTH('Cơ sở dữ liệu') AS byte_count;
```

With strings containing non-ASCII characters, `byte_count` can be larger than `character_count`. This is why checking byte lengths is necessary when estimating record size, `VARCHAR`, and payloads.

Measure actual data in a table:

```sql
SELECT
    article_id,
    CHAR_LENGTH(body) AS body_characters,
    OCTET_LENGTH(body) AS body_bytes
FROM articles
ORDER BY body_bytes DESC
LIMIT 20;
```

For BLOBs:

```sql
SELECT
    attachment_id,
    OCTET_LENGTH(file_data) AS file_bytes
FROM document_attachments
ORDER BY file_bytes DESC
LIMIT 20;
```

These queries measure the logical length of values, not the exact physical bytes on disk after InnoDB organizes pages, compression, metadata, and off-page storage.

## 5. Row Format Determines How Long Values Are Stored

InnoDB supports the main row formats: `REDUNDANT`, `COMPACT`, `DYNAMIC`, and `COMPRESSED`. The row format defines record layout and how variable-length columns are stored.

| Row format | Inline prefix when value is stored off-page | Remainder |
| --- | --- | --- |
| `REDUNDANT` | Up to 768 bytes | Stored off-page |
| `COMPACT` | Up to 768 bytes | Stored off-page |
| `DYNAMIC` | Does not keep a 768-byte prefix; record keeps a 20-byte pointer when externalized | Entire value stored off-page |
| `COMPRESSED` | LOB handling similar to `DYNAMIC` | Entire value stored off-page |

Short values can still remain completely inline inside the record. InnoDB only externalizes columns when needed for the record to fit on a page and according to the row format's strategy. Therefore, declaring a `TEXT` column does not mean every value in that column always lives off-page.

### 5.1. REDUNDANT and COMPACT: Keeping a 768-Byte Prefix

With these two older row formats, when a variable-length value is stored off-page, InnoDB retains up to the first 768 bytes inside the clustered index record and stores the rest on overflow pages. The record also holds a 20-byte pointer to the off-page data.

This allows accessing the prefix without necessarily reading the rest in some cases, yet 768 inline bytes still consume space in the record. If a row has many long LOB columns, their inline prefixes can add up and push the record past the page limit.

Therefore, simply changing `VARCHAR` columns to `TEXT` may not fix a `Row size too large` error if the table still uses `COMPACT` and multiple 768-byte prefixes remain stored in the record.

### 5.2. DYNAMIC and COMPRESSED: Storing the Entire Value Off-Page

With `DYNAMIC` and `COMPRESSED`, when a long column is externalized, InnoDB can store the entire value on overflow pages and retain only a 20-byte pointer in the clustered index record. This significantly reduces inline LOB data compared to a 768-byte prefix.

`DYNAMIC` fits tables with many long columns or large LOB values where most queries read only metadata. It is InnoDB's common default row format in modern MySQL; still, verify the table's actual row format rather than relying on assumptions about defaults.

`COMPRESSED` also supports off-page storage like `DYNAMIC`, while adding page compression. Compression incurs extra CPU overhead and page-size/algorithm constraints; do not pick it solely to reduce record size without measuring the workload.

## 6. Checking the Current Row Format

You can view the row format in `INFORMATION_SCHEMA.TABLES`:

```sql
SELECT
    TABLE_NAME,
    ENGINE,
    ROW_FORMAT
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'articles';
```

Or use:

```sql
SHOW TABLE STATUS LIKE 'articles'\G
SHOW CREATE TABLE articles\G
```

If a table does not specify `ROW_FORMAT`, the row format is chosen according to InnoDB's default setting at table creation time. You can inspect that setting:

```sql
SHOW VARIABLES LIKE 'innodb_default_row_format';
```

To create a new table with DYNAMIC:

```sql
CREATE TABLE article_contents (
    article_id BIGINT UNSIGNED NOT NULL,
    body LONGTEXT NOT NULL,
    PRIMARY KEY (article_id)
) ENGINE=InnoDB
  ROW_FORMAT=DYNAMIC;
```

To alter an existing table:

```sql
ALTER TABLE articles ROW_FORMAT=DYNAMIC;
```

Changing row format may require rebuilding the table and consume I/O, temporary space, time, or metadata locks. Before running on a large table, test on staging with representative data, check supported DDL algorithms for your current version, execution time, and spare disk space.

## 7. Why Does Row Size Too Large Still Happen with TEXT/BLOB?

Common error message:

```text
ERROR 1118 (42000): Row size too large (> 8126).
Changing some columns to TEXT or BLOB may help.
In current row format, BLOB prefix of 768 bytes is stored inline.
```

This error usually indicates that the internal record exceeds the page limit. Common causes include:

- The table has too many `VARCHAR` columns with large declared lengths.
- Many columns use `utf8mb4`, increasing the maximum byte size of each column.
- The table uses `COMPACT`/`REDUNDANT`, keeping 768-byte inline prefixes for multiple long columns.
- There are many fixed-length columns whose data cannot be moved off-page entirely.
- The current row format or page size leaves less usable inline capacity than expected.

Do not solve this by mechanically converting every column to `TEXT`. Identify which columns truly hold long content, choose `DYNAMIC` where suitable, reduce inline column counts/lengths, or split data into related tables.

## 8. Workflow for Diagnosing and Resolving Record Size Errors

When encountering error 1118 or suspecting oversized rows:

1. **Read the DDL:** use `SHOW CREATE TABLE` to inspect column types, charsets, nullability, indexes, and row format.
2. **Check page size:** inspect `@@innodb_page_size`; remember InnoDB's record limit depends on page size.
3. **Check row format:** inspect `INFORMATION_SCHEMA.TABLES.ROW_FORMAT` and `innodb_default_row_format`.
4. **Estimate bytes:** use `OCTET_LENGTH()` on real data; for empty columns, estimate using charset and declared length.
5. **Identify long columns:** check large `VARCHAR`s, `TEXT`/`BLOB`s, nullable columns, and total column count in the table.
6. **Evaluate external storage:** if using `COMPACT`, consider `DYNAMIC` to eliminate the 768-byte inline prefix on externalized columns.
7. **Reduce inline data:** shorten `VARCHAR`s, choose appropriate types, or move rarely accessed content to a separate table.
8. **Check the SQL row-size limit:** if declared totals still exceed 65,535 bytes at the SQL layer, changing row format is insufficient; schema changes are required.
9. **Test DDL on staging:** verify the table can be created, large data inserts succeed, and queries work properly.
10. **Assess migration cost:** rebuilds, locks, disk space, replication lag, and deployment window before applying to production.

## 9. Splitting Metadata and LOB Content into Two Tables

If most queries only need title, status, author, and update timestamp, while large content is only read when a user opens a document, you can split metadata and content:

```sql
CREATE TABLE documents (
    document_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(300) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (document_id),
    KEY idx_documents_status_created (status, created_at)
) ENGINE=InnoDB;

CREATE TABLE document_contents (
    document_id BIGINT UNSIGNED NOT NULL,
    body LONGTEXT NOT NULL,
    PRIMARY KEY (document_id),
    CONSTRAINT fk_document_contents_document
        FOREIGN KEY (document_id) REFERENCES documents (document_id)
) ENGINE=InnoDB
  ROW_FORMAT=DYNAMIC;
```

List queries do not need to read content:

```sql
SELECT document_id, title, status, created_at
FROM documents
WHERE status = 'published'
ORDER BY created_at DESC, document_id DESC
LIMIT 50;
```

Only when a user opens a document is the LOB read:

```sql
SELECT d.document_id, d.title, c.body
FROM documents AS d
JOIN document_contents AS c
  ON c.document_id = d.document_id
WHERE d.document_id = 1001;
```

This separation keeps metadata records compact so list queries avoid reading LOB pages. In exchange, creating, updating, or deleting documents must manage two tables; if they must change atomically, perform them in the same InnoDB transaction.

## 10. Reading LOBs Can Increase I/O

When a query selects a LOB column, InnoDB may need to access overflow pages to fetch the value. If the application only needs metadata, avoid selecting large columns:

```sql
-- Better for lists: fetch only the columns needed for display
SELECT document_id, title, status
FROM documents
WHERE status = 'published';
```

Avoid:

```sql
-- Reads the full content even though the UI only needs the title
SELECT *
FROM documents_with_body
WHERE status = 'published';
```

Key precautions:

- Avoid `SELECT *` on tables with LOBs when full content is not needed.
- Paginate metadata lists before loading detailed content.
- Use driver streaming APIs when handling large BLOB/TEXT values, avoiding loading many large values into application memory at once.
- Enforce upload size limits and validate data types at the application layer.
- Evaluate caching and retrieval latency for LOBs separately from metadata queries.

Off-page storage does not guarantee every read is slow; if pages are already in the buffer pool, data can be served from memory. Cost depends on LOB size, page count, locality, cache hit rate, and workload.

## 11. Indexes on TEXT/BLOB

You cannot create a standard B-tree index over the entire length of an arbitrary-length `TEXT`/`BLOB` column. MySQL requires a prefix length when indexing these types:

```sql
CREATE INDEX idx_articles_body_prefix
ON articles (body(100));
```

For non-binary string columns, prefix length is specified in characters; the actual index limit is still measured in bytes and depends on charset, row format, and page size. With `utf8mb4`, 100 characters can require up to 400 bytes.

A prefix index only indexes the beginning of the value. It can help with certain prefix search conditions, but does not represent the entire content. Two values sharing the same prefix are not distinguished by a prefix index the way a full-column index would.

Example:

```sql
SELECT article_id
FROM articles
WHERE body LIKE 'MySQL InnoDB%';
```

A prefix index can assist queries starting with a matching prefix, but does not help leading-wildcard search patterns such as `LIKE '%InnoDB%'`. Check `EXPLAIN` and consider `FULLTEXT` if the business requirement is full-text search.

For BLOBs, prefix length is measured in bytes. For TEXT, pay attention to character set and collation. InnoDB's key length limit depends on page size and row format; do not pick a long prefix without checking the index limit.

## 12. Index Key Length Limits Related to Row Format

InnoDB's maximum index key size depends on page size and row format. With a 16 KiB page size, the common limit is 3072 bytes for `DYNAMIC`/`COMPRESSED`, whereas `COMPACT`/`REDUNDANT` have a historical 767-byte limit. An 8 KiB or 4 KiB page size lowers the maximum limit accordingly (typically 1536 and 768 bytes for row formats supporting larger limits).

With `utf8mb4`, a 191-character prefix can require up to 764 bytes; this is why the number 191 frequently appears in schemas compatible with the legacy 767-byte limit. However, it is not a mandatory optimal number for every table or version. Choose prefix lengths based on queries and actual key length limits.

A `UNIQUE` prefix only guarantees the prefix portion does not collide under index rules; it does not replace a unique constraint over the full long content. If the business requires uniqueness across the entire content, a computed hash column with controlled verification can be used, provided collision probability is handled and full verification logic is enforced on writes.

## 13. max_allowed_packet and Data Transfer Limits

The maximum capacity of `LONGTEXT`/`LONGBLOB` does not mean applications can transmit values that large in a single packet. `max_allowed_packet` caps the packet/statement size accepted by client and server; drivers, protocols, and memory also impose their own limits.

Check server configuration:

```sql
SHOW VARIABLES LIKE 'max_allowed_packet';
```

When uploading a large file, check limits across reverse proxies, web servers, the application, drivers, and MySQL. Increasing `max_allowed_packet` does not resolve internal record limits, does not replace row format selection, and does not raise data type limits.

When handling large LOBs, consider streaming, application-layer chunking, or object storage while keeping only metadata/URLs/keys in MySQL. If content must be stored directly in the database for unified transactions, backups, and access control, weigh storage costs, replication, backup/restore, and I/O.

## 14. Choosing Between Storing BLOBs in MySQL vs. Object Storage

Storing binary content in MySQL has several benefits:

- Metadata and content can be committed or rolled back in the same transaction.
- Database access permissions and backups apply under the same workflow.
- Eliminates consistency handling between metadata rows and external files.

However, it also carries costs:

- Tablespaces, backups, and binary logs can grow rapidly.
- Replication must transmit large payloads.
- List queries can inadvertently pull LOBs if queries select overly broad columns.
- Restoring a single table or recovering large datasets can take significant time.

Object storage fits when files are large, read/write loads are high, or content needs CDN distribution. With this approach, the database typically stores the object key, checksum, size, content type, and status. You must design for cases where a file upload succeeds while the metadata transaction fails, or vice versa; outbox patterns, pending states, and orphan-object cleanup jobs are common solutions.

There is no single right choice for every system. The decision depends on file sizes, atomicity requirements, access frequency, backup, retention, access control, and operational cost.

## 15. Example: Measuring and Inspecting Tables with LOBs

Create a test table with the DYNAMIC row format:

```sql
CREATE TABLE lob_lab (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    body LONGTEXT NULL,
    binary_payload LONGBLOB NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_lob_lab_created (created_at)
) ENGINE=InnoDB
  ROW_FORMAT=DYNAMIC
  DEFAULT CHARACTER SET utf8mb4;
```

Verify row format and engine:

```sql
SELECT TABLE_NAME, ENGINE, ROW_FORMAT
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'lob_lab';
```

Measure logical content sizes:

```sql
SELECT
    id,
    CHAR_LENGTH(body) AS body_chars,
    OCTET_LENGTH(body) AS body_bytes,
    OCTET_LENGTH(binary_payload) AS payload_bytes
FROM lob_lab
ORDER BY id;
```

Compare a metadata query against a LOB-reading query:

```sql
EXPLAIN
SELECT id, title, created_at
FROM lob_lab
WHERE created_at >= '2026-01-01';

EXPLAIN
SELECT id, title, body
FROM lob_lab
WHERE created_at >= '2026-01-01';
```

Both queries may use the same filter condition and index, yet the second query must also return large content. Use `EXPLAIN ANALYZE` in a lab environment with representative data to measure actual timing and row counts; `EXPLAIN` alone does not accurately capture LOB read costs across all cache states.

## 16. Common Mistakes and Misconceptions

| Misconception / Error | Reality | How to handle |
| --- | --- | --- |
| TEXT/BLOB is always stored off-page | Short values can reside inline; InnoDB externalizes as needed according to row format | Check row format and data sizes |
| Off-page means files stored outside the database | Overflow pages still belong to the InnoDB tablespace | Understand off-page as pages separate from the main record |
| Changing VARCHAR to TEXT always fixes error 1118 | SQL row limit and InnoDB page limit are separate limits; COMPACT still keeps a 768-byte prefix | Check SQL size, row format, and page size |
| DYNAMIC still keeps a 768-byte inline prefix | When externalized, DYNAMIC stores the entire value off-page and keeps a pointer | Choose the right row format and verify DDL |
| `LONGTEXT` can always hold nearly 4 GiB | Packets, clients, memory, server, and storage have their own limits | Check `max_allowed_packet` and the full pipeline |
| 65,535 bytes is the InnoDB record limit | That is the SQL-layer limit; InnoDB records also face a smaller page-dependent limit | Distinguish the two error types and limits |
| CHAR_LENGTH equals byte count | With multi-byte charsets, byte count can be larger | Use `OCTET_LENGTH()` when measuring size |
| A prefix index represents the entire TEXT/BLOB | The index contains only the declared prefix | Use FULLTEXT or an appropriate search strategy |
| SELECT * is harmless on tables with LOBs | It can read and transmit unnecessarily large values | Select only columns the application truly needs |
| Splitting content tables is always faster | Adds joins and two-table transaction management | Measure workload and choose by access pattern |

## 17. Checklist for Designing Tables with TEXT/BLOB

When designing tables with long content, check:

1. Is the content text or binary bytes? Choose `TEXT` or `BLOB` with accurate semantics.
2. What maximum capacity is needed? Choose TINY/TEXT/MEDIUM/LONG appropriately—do not pick LONG just "to be safe."
3. Which charset is used? Calculate byte size, especially with `utf8mb4`.
4. What is the current row format? With many LOBs, evaluate `DYNAMIC`.
5. What is the page size? The internal record limit varies with page size.
6. Does the table have many large `VARCHAR` or fixed-length columns? Estimate inline record size.
7. Do frequent queries need to read the LOB? If not, consider separating metadata and content.
8. Does the content need indexing? Pick prefix index, FULLTEXT, or a search engine based on query patterns.
9. Could upload sizes exceed `max_allowed_packet` or client limits?
10. Can backups, restores, replication, and retention handle LOB volume?
11. Does changing row format or splitting tables require a rebuild and spare disk space?

## 18. Practice Exercises

1. Create two tables with identical schemas, one using `ROW_FORMAT=COMPACT` and one using `ROW_FORMAT=DYNAMIC`; verify via `INFORMATION_SCHEMA.TABLES`.
2. Insert short and long TEXT values; use `OCTET_LENGTH()` to compare bytes against characters.
3. Create a table with many large `VARCHAR` columns and test table creation/inserts to observe both the SQL row-size limit and the InnoDB record-size limit in a lab environment.
4. Convert a table from COMPACT to DYNAMIC; compare DDL, rebuild duration, and ability to store large data.
5. Investigate error 1118 on a 16 KiB page size; identify which part comes from the record limit under ~8 KiB.
6. Create a prefix index on a TEXT column; use `EXPLAIN` to compare prefix searches against `LIKE '%term%'`.
7. Create separate metadata and LOB content tables; compare list queries against detail queries.
8. Check `max_allowed_packet` and simulate large payloads in a test environment with appropriate limits.
9. Design a schema storing images/attachments in BLOBs; document its impact on backup and replication.
10. Propose an object storage approach for large files, including how to prevent orphan files and keep metadata synchronized with objects.

## 19. Takeaways

InnoDB stores records inside pages and can move large variable-length columns to overflow pages. `REDUNDANT`/`COMPACT` retain up to a 768-byte inline prefix along with a 20-byte pointer; `DYNAMIC`/`COMPRESSED` can store the entire value off-page when externalized and keep only a 20-byte pointer. Off-page data still resides inside the InnoDB tablespace, not automatically outside the database.

Distinguish the 65,535-byte SQL row-size limit from the InnoDB record limit of slightly under half the page size. For 16 KiB pages, maximum records are typically under ~8 KiB. TEXT/BLOB columns contribute only small metadata to the SQL-layer limit, while the row format dictates how many LOB bytes remain inline. When encountering error 1118, check charset, column count, `VARCHAR`, page size, and row format; evaluate DYNAMIC, reduce inline data, or split content tables. Use `OCTET_LENGTH()` to measure bytes, avoid unnecessary LOB reads, verify prefix indexes and `max_allowed_packet`, and factor in I/O, backups, replication, and migrations.
