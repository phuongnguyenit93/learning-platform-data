# COMPACT, DYNAMIC, COMPRESSED, and Row Format Conditions

The row format determines how InnoDB lays out a row's data inside a data page, stores variable-length column metadata, and handles long columns moved off-page. This choice affects record size in the clustered index, index key length limits, storage consumption, and CPU/I/O overhead.

The three row formats most important to understand when designing tables are COMPACT, DYNAMIC, and COMPRESSED. In modern MySQL, DYNAMIC is typically the default choice. COMPACT matters primarily for legacy compatibility; COMPRESSED can reduce storage usage, though compression benefits and costs must be measured on real data.

This article explains how long columns are stored, support conditions by version and tablespace, row/index limits, how to declare or convert row formats, and how to verify the results in MySQL.

## 1. What Does the Row Format Determine?

InnoDB stores tables in pages. For tables with a clustered index, row data is stored in the leaf pages of the clustered index. Each record contains management information, column data, and information supporting MVCC.

The row format determines how records are encoded and how InnoDB handles large values when a row cannot fit completely inside a data page.

Affected aspects:

- Record structure and per-row overhead.
- How variable-length columns are stored.
- How many bytes of a long column are kept in the record versus stored off-page.
- How many rows can fit on a single page.
- Index key length limits in certain versions/page sizes.
- Whether and how data is compressed.

The row format does not alter the SQL semantics of a column. A VARCHAR column remains a VARCHAR; changing the row format changes how InnoDB physically organizes the table's data.

## 2. InnoDB's Four Row Formats

InnoDB has four row formats: REDUNDANT, COMPACT, DYNAMIC, and COMPRESSED.

| Row format | Key characteristics | Common use cases |
|---|---|---|
| REDUNDANT | Older record format; higher column metadata storage overhead | Compatibility with very old systems |
| COMPACT | More compact records than REDUNDANT; keeps an initial prefix of a long column in the record when moving the rest off-page | Legacy application compatibility or preserving Antelope-style storage behavior |
| DYNAMIC | Can store the entire long column value off-page, with the record keeping a 20-byte pointer when moved off-page | Common default choice on modern MySQL |
| COMPRESSED | Builds on DYNAMIC's long-column storage and stores pages in compressed form | Tables with highly compressible data needing storage savings |

Most new systems should start with DYNAMIC. Only choose COMPRESSED after measuring storage savings, compression/decompression CPU, I/O, and latency. Do not switch to COMPACT simply because of its name or by assuming records are always smaller in every scenario.

## 3. How Does COMPACT Store Long Columns?

COMPACT reduces record overhead compared to REDUNDANT. For long columns such as BLOB, TEXT, or large variable-length columns, when InnoDB decides to move data outside the clustered index page, COMPACT retains up to the first 768 bytes of the value inside the record. The remainder is stored on overflow pages, and the record holds a 20-byte pointer to the off-page data.

This means a large TEXT column can still occupy significant space inside the clustered index page even when most of its content has been moved off-page.

Example:

~~~sql
CREATE TABLE articles_compact (
    article_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(200) NOT NULL,
    body LONGTEXT,
    PRIMARY KEY (article_id)
) ENGINE = InnoDB
  ROW_FORMAT = COMPACT;
~~~

When body is very long and chosen for off-page storage, the leading portion of its value can still reside in the record. This increases record size compared to storing the entire long column off-page.

COMPACT can still be appropriate if legacy compatibility must be maintained or for specific measured reasons. However, for tables containing many large text columns, retaining inline prefixes can reduce the number of records per page.

## 4. How DYNAMIC Handles Long Columns

DYNAMIC is designed to reduce the amount of long data kept in clustered index records. When InnoDB selects a long column for off-page storage, the entire column value can be stored in overflow pages; the record in the clustered index holds a 20-byte pointer.

Key differences:

| Scenario | COMPACT | DYNAMIC |
|---|---|---|
| Long column stored off-page | Keeps up to the first 768 bytes in the record, the rest off-page | Can move the entire column value off-page |
| Inline data of long columns | Can be larger | Typically smaller when columns are moved off-page |
| Record in clustered index | May contain leading prefixes of multiple long columns | May contain only pointers for off-page long columns |
| Consequence | Can reduce oversized rows via overflow while still keeping inline prefixes | Can increase records per page and ease record-size pressure |

Example:

~~~sql
CREATE TABLE articles_dynamic (
    article_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(200) NOT NULL,
    body LONGTEXT,
    metadata JSON,
    PRIMARY KEY (article_id)
) ENGINE = InnoDB
  ROW_FORMAT = DYNAMIC;
~~~

DYNAMIC is helpful for tables with BLOB, TEXT, JSON, or long VARCHAR columns. However, not every value in a long column is always placed off-page. InnoDB decides based on row size and whether the record fits in the page; short values can still be stored inline.

Do not interpret DYNAMIC as "every VARCHAR/TEXT column is always stored off-page." The off-page decision depends on row size and the need to fit the record into the page.

## 5. COMPRESSED: Row Format with Page Compression

COMPRESSED uses long-column organization similar to DYNAMIC and adds page compression. When a page is written to the tablespace, InnoDB attempts to compress the data so the page occupies less space.

The target compressed page size is controlled by KEY_BLOCK_SIZE. Example with the default 16 KB page size:

~~~sql
CREATE TABLE archived_articles (
    article_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(200) NOT NULL,
    body LONGTEXT,
    PRIMARY KEY (article_id)
) ENGINE = InnoDB
  ROW_FORMAT = COMPRESSED
  KEY_BLOCK_SIZE = 8;
~~~

KEY_BLOCK_SIZE = 8 specifies a target compressed page size of 8 KB. It does not mean each row or column is limited to 8 KB. The original page is still processed by InnoDB at the instance's page size; the compressed page is stored at the target size.

If KEY_BLOCK_SIZE is omitted, InnoDB uses a default value equal to half of innodb_page_size. With a 16 KB page size, the default is typically 8 KB.

### 5.1. When Is Compression Beneficial?

Compression can be suitable when:

- Data contains many repeated strings, text, JSON, or highly compressible content.
- The table is large and storage space or I/O is a bottleneck.
- The read/write workload can tolerate additional CPU cost.
- It has been benchmarked with production-representative data distributions and page sizes.

Compression may not be beneficial when:

- Data is already compressed, such as JPEG images, video, or encrypted payloads.
- The workload is CPU-bound.
- Pages change frequently and recompression introduces excessive overhead.
- Space savings are small relative to operational cost.

You cannot conclude COMPRESSED is always faster than DYNAMIC. Smaller sizes can reduce I/O, but compression and decompression increase CPU work and can affect latency.

### 5.2. KEY_BLOCK_SIZE

KEY_BLOCK_SIZE is the compressed page size in KB. Common values are 1, 2, 4, 8, and 16 KB, within the limits supported by innodb_page_size and the MySQL version.

Examples with a 16 KB page size:

| Configuration | Meaning |
|---|---|
| KEY_BLOCK_SIZE = 8 | Target compressed page size 8 KB |
| KEY_BLOCK_SIZE = 4 | Target compressed page size 4 KB |
| KEY_BLOCK_SIZE = 2 | Target compressed page size 2 KB |

The smaller the compressed page, the higher the required compression ratio. If data cannot compress down to the target size, InnoDB may need recompression handling, padding, or encounter compression failures to meet the target. Choosing too small a value can increase CPU and write costs.

On instances using an innodb_page_size of 32 KB or 64 KB, the COMPRESSED row format is not supported. Verify @@innodb_page_size before designing compressed tables.

## 6. Compatibility Conditions by MySQL Version

Row format limits have evolved across versions.

### 6.1. Antelope and Barracuda in Older Versions

In older MySQL versions, InnoDB used the file format concept:

- **Antelope** supported REDUNDANT and COMPACT.
- **Barracuda** added DYNAMIC and COMPRESSED.

In older versions, using DYNAMIC or COMPRESSED could require enabling the Barracuda file format and related settings such as innodb_file_per_table. Index prefix length limits could also depend on innodb_large_prefix.

### 6.2. MySQL 5.7 and MySQL 8.0

In newer MySQL 5.7 releases and MySQL 8.0, older file format mechanisms were simplified. MySQL 8.0 removed innodb_file_format and innodb_large_prefix; there is no need to manually enable Barracuda or large prefix as described in guides written for MySQL 5.6.

innodb_default_row_format controls the default row format when creating a table without specifying one explicitly. On modern MySQL, the default is typically DYNAMIC.

Do not mechanically apply MySQL 5.6 configuration guides to MySQL 8.0. Before changing production settings, check your actual version and the documentation for that release.

## 7. Tablespace and Page Size Conditions for COMPRESSED

The COMPRESSED row format is not supported in the system tablespace. In modern versions, compressed tables can be placed in file-per-table tablespaces or general tablespaces if other compatibility conditions are met.

Points to confirm:

- Whether innodb_file_per_table is enabled if the design relies on file-per-table.
- Whether the table currently resides in the system tablespace.
- Whether innodb_page_size is among those supported for COMPRESSED; 32 KB and 64 KB page sizes do not support COMPRESSED.
- Whether KEY_BLOCK_SIZE is valid for the page size and server version.
- Whether tablespace options are compatible with the chosen row format.

Not every page size setting can be changed after initializing an instance. innodb_page_size is a fixed attribute of an initialized data directory; changing page size typically requires creating a new instance and migrating data.

## 8. Row Format and Index Length Limits

The row format affects InnoDB's maximum index key length limit in relevant configurations.

With a 16 KB page size:

| Row format | Typical maximum index key limit |
|---|---:|
| REDUNDANT | 767 bytes |
| COMPACT | 767 bytes |
| DYNAMIC | 3072 bytes |
| COMPRESSED | 3072 bytes |

Actual limits also depend on innodb_page_size, MySQL version, and compatibility configuration. With an 8 KB page size, the maximum limit is correspondingly lower (typically 1536 bytes for row formats supporting large prefixes); with a 4 KB page size, it is 768 bytes.

### 8.1. Impact with utf8mb4

utf8mb4 can require up to 4 bytes per character. Therefore, index prefix length in characters does not equal length in bytes.

Example:

~~~sql
CREATE TABLE customer_names (
    customer_id BIGINT UNSIGNED NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    PRIMARY KEY (customer_id),
    KEY idx_display_name (display_name)
) ENGINE = InnoDB
  ROW_FORMAT = DYNAMIC
  DEFAULT CHARSET = utf8mb4;
~~~

With DYNAMIC and a 16 KB page size, the 3072-byte limit is usually enough for an index on VARCHAR(255) utf8mb4 (up to 1020 bytes for character data, excluding overhead). With COMPACT, the 767-byte limit can make a full-column index too long.

If compatibility with a row format having a 767-byte limit is required, a prefix index can be used where appropriate:

~~~sql
CREATE INDEX idx_display_name_prefix
ON customer_names (display_name(191));
~~~

A prefix index only stores and compares the leading portion of the string in the index; it may not distinguish values sharing the same prefix and does not fully replace a full-column index. Choose prefix lengths based on data distribution and query predicates.

### 8.2. Key Limit Is Not Row Size Limit

Do not confuse the 3072-byte index key limit with the row size limit. These are two separate limits:

- Index key limit restricts the total length of columns in an index key.
- Row size limit restricts the inline data of a row in a clustered index page as well as limits at the SQL layer.

Switching to DYNAMIC can solve certain long-column storage issues and allow longer index keys in supported configurations, but it does not allow arbitrary index designs or arbitrarily sized rows.

## 9. Row Size Limits and Off-Page Columns

MySQL has an SQL-layer row size limit of approximately 65,535 bytes, excluding the full content of BLOB/TEXT columns handled separately. InnoDB also enforces an inline record size limit within a page: record data must fit within the portion of a page available to a single row, roughly half a page after overhead.

When a row has many large variable-length columns, InnoDB can move some columns off-page so the inline record fits on the page. DYNAMIC and COMPRESSED have an advantage because they can move the entire long column value off-page when that column is selected for overflow.

If there are still too many fixed-size or short columns that must be stored inline, CREATE TABLE or INSERT/UPDATE can fail with a row size too large error.

Table design should:

- Avoid creating excessive very large VARCHAR columns if the business does not need them.
- Separate large, infrequently accessed data from frequently read tables where sensible.
- Choose DYNAMIC for tables with many long columns.
- Measure actual sizes and test INSERTing boundary values.
- Never rely on changing row formats as a substitute for proper schema design.

## 10. Declaring Row Format at Table Creation

You can specify the row format in CREATE TABLE:

~~~sql
CREATE TABLE documents (
    document_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    content LONGTEXT,
    PRIMARY KEY (document_id)
) ENGINE = InnoDB
  ROW_FORMAT = DYNAMIC;
~~~

Creating a table using COMPACT:

~~~sql
CREATE TABLE legacy_documents (
    document_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    content LONGTEXT,
    PRIMARY KEY (document_id)
) ENGINE = InnoDB
  ROW_FORMAT = COMPACT;
~~~

Creating a table using COMPRESSED:

~~~sql
CREATE TABLE cold_documents (
    document_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(255) NOT NULL,
    content LONGTEXT,
    PRIMARY KEY (document_id)
) ENGINE = InnoDB
  ROW_FORMAT = COMPRESSED
  KEY_BLOCK_SIZE = 8;
~~~

If ROW_FORMAT is omitted, InnoDB uses innodb_default_row_format at table creation time. Specifying the row format explicitly makes schema intent clearer, especially when applications require cross-environment consistency.

## 11. Changing the Row Format of an Existing Table

You can instruct InnoDB to convert a table to another row format with ALTER TABLE:

~~~sql
ALTER TABLE documents
ROW_FORMAT = DYNAMIC;
~~~

Converting to COMPRESSED:

~~~sql
ALTER TABLE cold_documents
ROW_FORMAT = COMPRESSED,
KEY_BLOCK_SIZE = 8;
~~~

Changing the row format typically requires rebuilding the physical structure of the table. For large tables, the operation can consume time, I/O, CPU, and temporary disk space; it can also require metadata locks. Online execution support and the DDL algorithm depend on the version, specific operation, and table structure.

Before running in production:

1. Check table size and free disk space.
2. Check the MySQL version and online DDL capabilities for that operation.
3. Test on a data copy close to production size.
4. Determine metadata lock duration and application impact.
5. Prepare backups and rollback/restore procedures.
6. Run inside a maintenance window if acceptable impact cannot be guaranteed.

Do not assume ALTER TABLE ... ROW_FORMAT is always INSTANT or always non-locking. If specifying ALGORITHM/LOCK, verify version support beforehand; requesting an unsupported algorithm will cause the statement to fail rather than automatically becoming safe.

## 12. Checking the Active Row Format

### 12.1. SHOW CREATE TABLE

~~~sql
SHOW CREATE TABLE documents;
~~~

This displays the DDL stored by the server for the table, including engine, charset, collation, and row format options if specified.

### 12.2. SHOW TABLE STATUS

~~~sql
SHOW TABLE STATUS LIKE 'documents';
~~~

The Row_format column reports the current row format, such as Dynamic, Compact, or Compressed.

### 12.3. INFORMATION_SCHEMA.TABLES

~~~sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE,
    ROW_FORMAT,
    CREATE_OPTIONS,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH
FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'documents';
~~~

InnoDB's TABLE_ROWS is typically an estimate and not always an exact row count. DATA_LENGTH and INDEX_LENGTH reflect estimated sizes according to engine metadata.

### 12.4. Checking Instance Configuration

~~~sql
SELECT
    @@version AS mysql_version,
    @@innodb_default_row_format AS default_row_format,
    @@innodb_page_size AS innodb_page_size,
    @@innodb_file_per_table AS file_per_table;
~~~

Variables and values may differ by version, distribution, or configuration. If a variable does not exist in the older/newer version you are using, check the corresponding documentation instead of assuming every instance shares the same variable list.

## 13. Distinguishing Row Compression from Page Compression

ROW_FORMAT=COMPRESSED is InnoDB's traditional table compression format, typically paired with KEY_BLOCK_SIZE to specify the compressed page size.

MySQL also offers InnoDB page compression configured via the COMPRESSION table option, such as COMPRESSION='zlib' or another algorithm supported by the version. Page compression relies on sparse file support and filesystem/storage punch-hole capabilities. This mechanism differs from the COMPRESSED row format.

Do not use the two concepts interchangeably:

| Feature | ROW_FORMAT=COMPRESSED | Page compression |
|---|---|---|
| Primary configuration | ROW_FORMAT and KEY_BLOCK_SIZE | COMPRESSION option |
| Mechanism | Compresses pages to a target block size | Compresses pages and punches holes to free unused space in the file if storage supports it |
| Depends on sparse/punch-hole filesystem | Not a core requirement of the traditional mechanism | Yes |
| Goal | Reduce stored page size via compressed page format | Reduce file footprint on storage |

Algorithm support and filesystem requirements depend on version, operating system, and storage hardware. Verify in your deployment environment before choosing page compression.

## 14. Measuring Before Choosing a Row Format

Do not compare file sizes right after table creation alone. Measure storage size, CPU, I/O, and latency together.

An experiment can be performed on three tables with identical schemas and data:

~~~sql
CREATE TABLE docs_compact (
    id BIGINT UNSIGNED NOT NULL,
    body LONGTEXT,
    PRIMARY KEY (id)
) ENGINE = InnoDB ROW_FORMAT = COMPACT;

CREATE TABLE docs_dynamic (
    id BIGINT UNSIGNED NOT NULL,
    body LONGTEXT,
    PRIMARY KEY (id)
) ENGINE = InnoDB ROW_FORMAT = DYNAMIC;

CREATE TABLE docs_compressed (
    id BIGINT UNSIGNED NOT NULL,
    body LONGTEXT,
    PRIMARY KEY (id)
) ENGINE = InnoDB
  ROW_FORMAT = COMPRESSED
  KEY_BLOCK_SIZE = 8;
~~~

Load the same dataset into each table. Test data should include:

- Text content with many repeated segments to test compressibility.
- Pre-compressed or near-random content to observe hard-to-compress cases.
- Both short and long values.
- Some rows with multiple large columns if the production schema has that shape.

Measure these metrics:

| Metric | Meaning |
|---|---|
| DATA_LENGTH | Data size per InnoDB metadata |
| INDEX_LENGTH | Index size |
| Tablespace size on filesystem | Actual storage footprint |
| INSERT/UPDATE duration | Write and compression cost |
| CPU | Compression/decompression overhead |
| SELECT throughput | Read workload serving capacity |
| p95/p99 latency | Impact on real-world tail latency |
| Buffer pool and I/O | Memory and storage device utilization |

Run benchmarks with both warm and cold caches if the workload experiences both states. Repeat multiple times while holding server version, buffer pool configuration, data, and concurrency constant so results are comparable.

## 15. Common Mistakes

**"DYNAMIC always moves every VARCHAR/TEXT off-page."** False. InnoDB only moves columns off-page when needed to make the record fit in the page; short values can remain inline.

**"COMPACT stores all BLOB/TEXT inline."** False. When a long column is chosen for off-page storage, COMPACT keeps up to the first 768 bytes in the record and the rest off-page.

**"DYNAMIC is always faster than COMPACT."** There is no guarantee. DYNAMIC can reduce inline record size for long columns, but actual performance depends on queries, data, and cache behavior.

**"COMPRESSED always reduces total query time."** False. It can reduce I/O and storage size while increasing compression/decompression CPU.

**"KEY_BLOCK_SIZE is the size limit of a single row."** False. It is the target compressed page size in KB.

**"COMPRESSED can be used with any innodb_page_size."** False. 32 KB and 64 KB page sizes do not support the COMPRESSED row format.

**"MySQL 8.0 still requires enabling Barracuda and innodb_large_prefix."** False. Legacy file format settings were removed; do not apply MySQL 5.6 configuration instructions to MySQL 8.0.

**"Changing ROW_FORMAT only updates metadata."** False. The operation usually rebuilds the physical structure and can consume resources, time, temporary space, and metadata locks.

**"3072 bytes is the size limit of an entire row."** False. That is the index key limit in supported configurations; row size has its own separate limits.

**"COMPRESSED row format and page compression are the same feature."** False. They are two distinct mechanisms with different options and deployment requirements.

## 16. Row Format Selection Checklist

- [ ] Identified the actual MySQL version and storage engine.
- [ ] Checked innodb_default_row_format and innodb_page_size.
- [ ] Determined whether the table has many long columns.
- [ ] Understood that COMPACT retains a 768-byte prefix when long columns are moved off-page.
- [ ] Understood that DYNAMIC can store entire long columns off-page.
- [ ] Confirmed tablespace and page size requirements if using COMPRESSED.
- [ ] Checked index key limits by row format, charset, and page size.
- [ ] Tested boundary data to catch row size too large errors.
- [ ] Benchmarked storage size, CPU, I/O, throughput, and p95/p99 latency.
- [ ] Evaluated duration, metadata locks, and disk space needed for ALTER TABLE.
- [ ] Distinguished COMPRESSED row format from page compression.
- [ ] Verified actual row format using SHOW CREATE TABLE or INFORMATION_SCHEMA.

## Conclusion

COMPACT retains up to the first 768 bytes of a long column in the clustered index record when stored off-page; DYNAMIC can move the entire long column value off-page and leave a pointer in the record. COMPRESSED uses similar long-column storage to DYNAMIC and adds page compression with KEY_BLOCK_SIZE.

On modern MySQL, DYNAMIC is usually the sensible default. COMPRESSED should only be chosen after confirming page size, tablespace, and version support, and then measuring effectiveness on a real workload. Verify row format, index limits, row sizes, and DDL impact before rolling out changes in production.
