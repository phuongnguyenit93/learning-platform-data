# TINYTEXT/TEXT/MEDIUMTEXT/LONGTEXT and Corresponding BLOB Types

This lesson belongs to the **Data Types** chapter of the `DATABASE_MYSQL` module. The module aims for mastery of MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, execution plan reading, query tuning, privilege management, backups, and handling relational database operational issues. The `TEXT` and `BLOB` families serve columns with variable-length and potentially very large values, yet they differ in how MySQL interprets content, performs comparisons, indexes values, and transmits data.

After this lesson, you will be able to choose the right tier among `TINYTEXT`, `TEXT`, `MEDIUMTEXT`, `LONGTEXT`, or their corresponding `BLOB` types; explain byte limits; distinguish character data from binary data; create appropriate prefix or `FULLTEXT` indexes; and identify storage, query, packet, and performance limits.

## 1. What Problems Do TEXT and BLOB Solve?

MySQL provides two families of large, variable-length data types:

- **TEXT** stores character strings. Values have a character set and collation, so MySQL can process them according to language rules, comparison rules, sort order, and character conversion.
- **BLOB** stores byte strings. Values are treated as binary data with the `binary` character set and collation; comparisons and sorting operate on raw byte values.

Examples:

| Data | Typically Suitable Type | Reason |
|---|---|---|
| Article bodies, long descriptions, multi-line notes | `TEXT` or `MEDIUMTEXT` | Content is text requiring charset and collation |
| HTML, Markdown, Vietnamese text content | `TEXT` or `MEDIUMTEXT` | Needs to be stored and compared as character strings |
| Images, PDFs, audio, compressed data | Appropriate `BLOB` | Must preserve every byte of the file verbatim |
| Encrypted payloads or binary-serialized data | Appropriate `BLOB` | Bytes should not be interpreted as text |
| Very large log content or text | `MEDIUMTEXT` or `LONGTEXT` | `VARCHAR` limits may not be suitable |

Do not choose `BLOB` merely because data looks long, and do not choose `LONGTEXT` merely to "have plenty of room." Determine whether the content is text or binary bytes, its actual size, query patterns, and data lifecycle before choosing a type.

## 2. Four Capacity Tiers

Each family has four corresponding types. The limits below represent the maximum byte size of the value payload:

| TEXT Type | Corresponding BLOB Type | Maximum Capacity | Length Prefix Bytes |
|---|---|---:|---:|
| `TINYTEXT` | `TINYBLOB` | 255 bytes | 1 byte |
| `TEXT` | `BLOB` | 65,535 bytes (64 KiB - 1) | 2 bytes |
| `MEDIUMTEXT` | `MEDIUMBLOB` | 16,777,215 bytes (16 MiB - 1) | 3 bytes |
| `LONGTEXT` | `LONGBLOB` | 4,294,967,295 bytes (4 GiB - 1) | 4 bytes |

Corresponding types in each row share the same capacity limits and storage requirements. The primary difference is that `TEXT` stores character strings while `BLOB` stores raw bytes.

### Byte Limits Are Not Always Equal to Character Counts

For `TEXT` types, maximum capacity is measured in encoded bytes. Actual character capacity depends on the character set.

For instance, `utf8mb4` can use up to 4 bytes per character. If every character takes all 4 bytes, the approximate theoretical character limits are:

| Type | Max Bytes | Estimated Max Characters at 4 Bytes/Char |
|---|---:|---:|
| `TINYTEXT` | 255 | 63 |
| `TEXT` | 65,535 | 16,383 |
| `MEDIUMTEXT` | 16,777,215 | 4,194,303 |
| `LONGTEXT` | 4,294,967,295 | 1,073,741,823 |

This estimate assumes every character consumes 4 bytes. Many ASCII characters use only 1 byte, while Vietnamese characters can take varying byte counts. Thus, exact character counts cannot be deduced from the `TEXT` type name alone.

For `BLOB`, limits are always measured in bytes because the content is a byte string. There is no "character count" concept determining `BLOB` capacity.

### Length Storage Overhead

MySQL stores `TEXT`/`BLOB` values as variable-length data. In addition to payload bytes, 1, 2, 3, or 4 bytes are required to store the length prefix, depending on the type.

If a `MEDIUMTEXT` value has an actual length of 10,000 bytes, the data plus length prefix needs roughly 10,003 bytes before accounting for row, record, page, off-page pointer, and other storage overhead.

Do not use this calculation as an exact formula for total table size. Actual storage also depends on the storage engine, row format, row size, page size, indexes, and compression.

## 3. Comparing TEXT and BLOB

### TEXT: Character Strings with Charset and Collation

`TEXT` is a non-binary string type. You can declare character set and collation at the column level:

~~~sql
CREATE TABLE articles (
    id BIGINT UNSIGNED PRIMARY KEY,
    title VARCHAR(300) NOT NULL,
    body MEDIUMTEXT
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
);
~~~

In this example:

- `utf8mb4` enables Unicode storage, including Vietnamese and supplementary characters outside the BMP.
- `utf8mb4_0900_ai_ci` is a case-insensitive and accent-insensitive collation according to its rules.
- Comparisons, searches, and sorting on `body` follow the collation.

A specific collation can treat two byte-different strings as equal in comparisons. For instance, a case-insensitive collation treats `'MySQL'` and `'mysql'` as equal. Choose collations based on linguistic and business requirements.

Inspect the actual charset/collation:

~~~sql
SELECT
    CHARSET(body) AS character_set_name,
    COLLATION(body) AS collation_name
FROM articles
LIMIT 1;
~~~

### BLOB: Binary Byte Strings

`BLOB` has the `binary` character set and collation. MySQL does not interpret `BLOB` contents as UTF-8 or any text encoding.

~~~sql
CREATE TABLE attachments (
    id BIGINT UNSIGNED PRIMARY KEY,
    file_name VARCHAR(255) NOT NULL,
    mime_type VARCHAR(127) NOT NULL,
    payload MEDIUMBLOB NOT NULL
);
~~~

For example, two bytes `0x41` and `0x61` are compared byte by byte and are treated as distinct. `BLOB` has no case-insensitive or accent-insensitive rules like `TEXT` collations.

Inspect the string type:

~~~sql
SELECT
    CHARSET(payload) AS character_set_name,
    COLLATION(payload) AS collation_name,
    LENGTH(payload) AS byte_length,
    HEX(payload) AS hex_value
FROM attachments;
~~~

`CHARSET(payload)` and `COLLATION(payload)` both return `binary`.

### Converting Between BLOB and TEXT

Only convert `BLOB` to `TEXT` when you know the character encoding of the bytes. For example, if a `BLOB` genuinely contains UTF-8 text:

~~~sql
SELECT CONVERT(payload USING utf8mb4) AS decoded_text
FROM attachments;
~~~

If the bytes represent JPEG, PDF, compressed data, or ciphertext, converting to `TEXT` will not turn them into valid text. The result may contain invalid characters or become corrupted during processing.

Conversely, if you need the raw bytes of a text string, you can use `CONVERT(... USING BINARY)` or a function matching your encoding goal. Distinguish charset conversion from preserving original bytes verbatim.

## 4. Which Tier Should You Choose?

| Type | When to Use | Examples |
|---|---|---|
| `TINYTEXT` / `TINYBLOB` | Very short content, capped at 255 bytes | Short notes, tiny binary payloads |
| `TEXT` / `BLOB` | Content not exceeding roughly 64 KiB | Long descriptions, small documents |
| `MEDIUMTEXT` / `MEDIUMBLOB` | Content potentially reaching several MiB | Long articles, HTML content, medium attachments |
| `LONGTEXT` / `LONGBLOB` | Genuine requirement for hundreds of MiB or larger | Huge text payloads or large files stored in the database |

Selection guidelines:

- Pick the smallest tier that satisfies known data limits and reasonable projected growth.
- If data is always short and has a clear upper bound, prefer `VARCHAR(N)` or `VARBINARY(N)` over `TEXT`/`BLOB`.
- Pick `TEXT` for content needing charset/collation and `BLOB` for content needing exact byte preservation.
- Do not pick `LONG` merely to avoid estimating size; oversized data impacts packets, memory, backups, replication, I/O, and query latency.
- Check the maximum size your application actually sends and receives, not just the type's theoretical limit.

### How Do TEXT/BLOB Differ from VARCHAR/VARBINARY?

`TEXT` can be viewed as a very large `VARCHAR`-like type, and `BLOB` as a very large `VARBINARY`-like type. However, there are notable differences:

| Characteristic | VARCHAR / VARBINARY | TEXT / BLOB |
|---|---|---|
| Declared length | Requires limit `N` | Limit can be omitted; four fixed tiers |
| Meaning of length | `VARCHAR` in characters; `VARBINARY` in bytes | `TEXT` capped in encoded bytes; `BLOB` in bytes |
| DEFAULT | Supports `DEFAULT` per version rules | Does not support `DEFAULT` |
| B-tree index | Entire column can be indexed if within limits | Must declare a prefix length |
| InnoDB storage | Can store off-page if row is large | Can store off-page if row is large |
| Purpose | Strings with clear bounds | Large, variable-length content |

For example, declaring `body TEXT DEFAULT ''` is invalid because `TEXT`/`BLOB` columns do not support `DEFAULT` values. If an initial value is needed, the application can pass an empty string explicitly on `INSERT` or handle it in application logic.

A subtle but important difference when using `TEXT` as a key: `TEXT` values are not automatically padded or stripped on `INSERT`/`SELECT`. However, comparisons of `TEXT` index entries apply trailing-space padding rules. Consequently, if you create a unique index on `TEXT`, two values differing only in trailing spaces may be treated as duplicate keys. The same rule does not apply to `BLOB`. Avoid using `TEXT` as a unique identifier if the business requires exact distinction of every byte or trailing space.

## 5. How InnoDB Stores TEXT/BLOB

`TEXT` and `BLOB` are variable-length types. In InnoDB, large columns can be stored outside the main data page (off-page) on overflow pages.

Exact storage depends on row format and row size:

- With `ROW_FORMAT=DYNAMIC` or `COMPRESSED`, InnoDB can store the entire long value off-page. The clustered index record holds a 20-byte pointer to the overflow pages.
- With `ROW_FORMAT=COMPACT` or `REDUNDANT`, the first 768 bytes of a `BLOB`/`TEXT`/`VARCHAR` column may remain inline in the clustered index record, with the rest placed on overflow pages plus a pointer.
- With `DYNAMIC`, `TEXT`/`BLOB` values of 40 bytes or less are always stored inline; off-page storage decisions also depend on total row size and page size.

InnoDB's default row format is currently `DYNAMIC` under default configuration. Nevertheless, when analyzing legacy tables or customized environments, inspect the actual row format:

~~~sql
SHOW TABLE STATUS
FROM your_database
LIKE 'articles';
~~~

Or:

~~~sql
SELECT
    NAME,
    ROW_FORMAT
FROM INFORMATION_SCHEMA.INNODB_TABLES
WHERE NAME = 'your_database/articles';
~~~

Off-page storage does not make querying large columns cheap. When selecting large content, MySQL still must read overflow pages, serialize the payload over the wire protocol, and transfer it to the client. If a query only needs ID, title, or status, avoid fetching large content columns unnecessarily.

## 6. Indexing TEXT and BLOB

### B-Tree Indexes Require a Prefix Length

With `CHAR`/`VARCHAR`, prefix length is optional. With `TEXT`/`BLOB`, creating a B-tree index requires specifying how many leading characters or bytes to index.

~~~sql
CREATE TABLE article_search (
    id BIGINT UNSIGNED PRIMARY KEY,
    title VARCHAR(300) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    KEY idx_body_prefix (body(100))
) ENGINE=InnoDB;
~~~

Here, the index stores only the first 100 characters of `body`. For `BLOB`, prefix length is measured in bytes:

~~~sql
CREATE TABLE binary_objects (
    id BIGINT UNSIGNED PRIMARY KEY,
    payload LONGBLOB NOT NULL,
    KEY idx_payload_prefix (payload(32))
) ENGINE=InnoDB;
~~~

### Prefix Index Limits

Prefix length is bounded by storage engine, row format, and page size. With InnoDB's default 16 KiB page size:

| InnoDB Row Format | Maximum Index Prefix |
|---|---:|
| REDUNDANT or COMPACT | 767 bytes |
| DYNAMIC or COMPRESSED | 3,072 bytes |

MyISAM has a 1,000-byte prefix limit. Practical limits may be lower with smaller page sizes or due to total key length across multi-column indexes.

In MySQL 9.7, B-tree indexes on `TEXT`/`BLOB` are supported by InnoDB, MyISAM, and BLACKHOLE. Indexing capability and exact limits depend on the storage engine; do not generalize InnoDB limits to every engine.

A common point of confusion:

- Prefix length in a `TEXT` index definition is specified in characters.
- Prefix length for `BLOB` is specified in bytes.
- Technical index limits are measured in bytes.

For example, `body(200)` with `utf8mb4` can require up to 800 bytes for the prefix, since one character can take up to 4 bytes. Do not take the 3,072-byte limit and declare 3,072 characters on a `utf8mb4` `TEXT` column.

### Prefix Indexes Do Not Store Full Content

An index `body(100)` only helps MySQL find values whose leading characters match. If a search predicate compares the entire value, the server may still have to read the row and verify the remainder.

~~~sql
SELECT id
FROM article_search
WHERE body = 'A long article body ...';
~~~

The prefix index can eliminate rows with differing prefixes, but full-value verification is still required. Two different documents sharing the same first 100 characters share the same prefix index entry.

Therefore:

- Choose a prefix with sufficiently high selectivity based on real data.
- Use `SHOW INDEX` to inspect the created prefix.
- Use `EXPLAIN` to confirm whether the optimizer uses the index.
- Do not use a unique prefix index if business rules require the entire content to be unique.

If you need to identify large content by its full value, compute a hash such as SHA-256 in the application layer, store it in `BINARY(32)`, and index the hash column. When exact matching is critical, still verify the full content as required by business rules to handle theoretical hash collisions.

~~~sql
CREATE TABLE documents (
    id BIGINT UNSIGNED PRIMARY KEY,
    body MEDIUMTEXT NOT NULL,
    body_sha256 BINARY(32) NOT NULL,
    KEY idx_body_sha256 (body_sha256)
);
~~~

### FULLTEXT Indexes for Text

If the goal is searching for words or phrases inside text, a prefix B-tree index is not a full-text search engine. MySQL supports `FULLTEXT` indexes on `CHAR`, `VARCHAR`, and `TEXT` with InnoDB or MyISAM.

~~~sql
CREATE TABLE knowledge_articles (
    id BIGINT UNSIGNED PRIMARY KEY,
    title VARCHAR(300) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    FULLTEXT KEY ft_title_body (title, body)
) ENGINE=InnoDB;
~~~

Query:

~~~sql
SELECT
    id,
    MATCH(title, body) AGAINST ('transaction index' IN NATURAL LANGUAGE MODE) AS score
FROM knowledge_articles
WHERE MATCH(title, body) AGAINST ('transaction index' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC;
~~~

`FULLTEXT` has its own tokenizer, stopwords, minimum token length, and search rules. Results are not equivalent to arbitrary substring matching with `LIKE '%word%'`. Check parser configuration and data language before using it for Vietnamese search.

## 7. Query Limits with TEXT/BLOB

### max_sort_length

When sorting `BLOB`/`TEXT`, MySQL uses only the leading number of bytes specified by `max_sort_length`. The default is 1024 bytes. If the distinguishing data appears past this prefix, sort order or grouping may not reflect the entire content as expected.

Check it:

~~~sql
SHOW VARIABLES LIKE 'max_sort_length';
~~~

If business logic truly needs to compare or sort long content, evaluate the impact of increasing this variable at the session or server level. Sorting large amounts of long text remains resource-intensive; sorting by key, timestamp, title, or compact metadata columns is preferable whenever applicable.

### Temporary Tables and SELECT *

If a query requires a temporary table and includes `TEXT`/`BLOB` columns, MySQL may have to use an on-disk temporary table because the `MEMORY` engine does not support these types. This increases I/O and can hurt performance.

Pattern to avoid when full body content is unnecessary:

~~~sql
-- Fetches all columns, including a very large body
SELECT *
FROM articles
WHERE id = 100;
~~~

Replace with:

~~~sql
-- Fetches only the metadata needed for list views
SELECT id, title, created_at
FROM articles
WHERE id = 100;
~~~

Fetch large content only when the UI or business operation actually needs to read it.

### max_allowed_packet and Memory

A type's capacity limit does not guarantee that a client can transmit a value that large in one request. Packet limits and available memory constrain practical payload sizes.

The `max_allowed_packet` variable controls the message size that client and server can handle. When transferring large `BLOB`/`TEXT` values, check both server and client settings such as `mysql` client or `mysqldump`. If a packet exceeds the limit, you may encounter `Packet too large` errors or dropped connections.

Check on the server:

~~~sql
SHOW VARIABLES LIKE 'max_allowed_packet';
~~~

Do not raise packet size to the maximum arbitrarily. Consider memory consumption, concurrent connections, application/connector limits, and the risk of a single huge request straining the server.

### Strict SQL Mode and Oversized Data

When assigning a value exceeding a column's limit:

- With strict SQL mode enabled, MySQL raises an error and rejects truncated values.
- With strict SQL mode disabled, the value may be truncated to fit the column and emit a warning.
- Trimming excess trailing spaces on `TEXT` values follows its own warning rules.

Check SQL mode:

~~~sql
SELECT @@SESSION.sql_mode;
~~~

Do not rely on silent truncation. Validate input length in the application layer, enable strict mode appropriately, and handle errors explicitly to avoid silent content loss.

## 8. Practical Table Design Examples

### Storing Articles

~~~sql
CREATE TABLE articles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    slug VARCHAR(200) NOT NULL,
    title VARCHAR(300) NOT NULL,
    summary TEXT,
    body MEDIUMTEXT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_articles_slug (slug),
    FULLTEXT KEY ft_articles_content (title, body)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;
~~~

Explanation:

- `slug` has a clear bound and must be unique, so it uses `VARCHAR`.
- `title` is a short string, using `VARCHAR`.
- `summary` is a short paragraph of variable length; `TEXT` is a reasonable choice.
- `body` is long article content; `MEDIUMTEXT` is generally better than `TEXT` if articles can exceed 64 KiB.
- The `FULLTEXT` index supports full-text search across title and body.

When fetching only titles and timestamps for list pages, do not `SELECT body`.

### Storing Attachments

~~~sql
CREATE TABLE attachments (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    owner_id BIGINT UNSIGNED NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    mime_type VARCHAR(127) NOT NULL,
    byte_size BIGINT UNSIGNED NOT NULL,
    sha256 BINARY(32) NOT NULL,
    payload LONGBLOB NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY idx_attachments_owner_created (owner_id, created_at),
    KEY idx_attachments_sha256 (sha256)
) ENGINE=InnoDB;
~~~

Explanation:

- File name and MIME type are bounded character strings, using `VARCHAR`.
- File size is a byte count, using `BIGINT UNSIGNED`.
- SHA-256 is 32 bytes, using `BINARY(32)` rather than `BLOB`.
- File content can use `LONGBLOB` if storing files in MySQL is required.

For large files or high file counts, consider object storage or a dedicated file service. The database can store only metadata, checksums, sizes, storage keys, and access permissions. This keeps database backups smaller and avoids streaming large files through frequent queries. The decision depends on transaction, retention, replication, security, and infrastructure requirements.

## 9. Useful Functions for Inspecting Content

| Function | Meaning |
|---|---|
| `CHAR_LENGTH(expr)` | Number of characters in the string |
| `LENGTH(expr)` | Number of bytes in the string |
| `OCTET_LENGTH(expr)` | Number of bytes, equivalent to `LENGTH` |
| `CHARSET(expr)` | Character set of the expression |
| `COLLATION(expr)` | Collation of the expression |
| `HEX(expr)` | Hexadecimal representation of bytes |
| `CONVERT(expr USING charset)` | Converts a string to the specified character set |

Example with Unicode data:

~~~sql
SELECT
    'Cơ sở dữ liệu' AS sample_text,
    CHAR_LENGTH('Cơ sở dữ liệu') AS character_count,
    LENGTH('Cơ sở dữ liệu') AS byte_count,
    CHARSET('Cơ sở dữ liệu') AS character_set_name,
    COLLATION('Cơ sở dữ liệu') AS collation_name;
~~~

If the connection character set is `utf8mb4`, `byte_count` will exceed `character_count` because non-ASCII Unicode characters take multiple bytes. `CHAR_LENGTH` measures characters; `LENGTH` measures bytes.

## 10. Hands-On Lab: TEXT, BLOB, and Prefix Indexes

Run in a dedicated lab database.

### Step 1: Create Test Tables

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_large_values_lab;
USE mysql_large_values_lab;

CREATE TABLE notes (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    PRIMARY KEY (id),
    KEY idx_body_prefix (body(100))
) ENGINE=InnoDB
  DEFAULT CHARACTER SET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE binary_samples (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    label VARCHAR(100) NOT NULL,
    payload MEDIUMBLOB NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
~~~

### Step 2: Insert Unicode Text

~~~sql
INSERT INTO notes (title, body)
VALUES (
    'Giới thiệu MySQL',
    'Cơ sở dữ liệu quan hệ lưu trữ dữ liệu theo bảng. MySQL hỗ trợ transaction, index và nhiều kiểu dữ liệu văn bản.'
);
~~~

Read the content and check sizes:

~~~sql
SELECT
    id,
    title,
    CHAR_LENGTH(body) AS character_count,
    OCTET_LENGTH(body) AS byte_count,
    CHARSET(body) AS character_set_name,
    COLLATION(body) AS collation_name
FROM notes;
~~~

Observe that `byte_count` is greater than or equal to `character_count`. The difference depends on characters and encoding.

### Step 3: Insert Binary Bytes

~~~sql
INSERT INTO binary_samples (label, payload)
VALUES
    ('sample-bytes', X'0041FF7F');
~~~

Read the data:

~~~sql
SELECT
    id,
    label,
    LENGTH(payload) AS byte_count,
    HEX(payload) AS payload_hex,
    CHARSET(payload) AS character_set_name,
    COLLATION(payload) AS collation_name
FROM binary_samples;
~~~

The `HEX` result should show the exact byte sequence `0041FF7F`. Both `00` and `FF` bytes are valid data inside a `BLOB`.

### Step 4: Inspect the Index

~~~sql
SHOW INDEX FROM notes;

EXPLAIN
SELECT id
FROM notes
WHERE body LIKE 'Cơ sở dữ liệu%';
~~~

Inspect the `Sub_part` column of the index to see the declared prefix length. `EXPLAIN` output depends on row count, statistics, and selectivity; on a very small table, the optimizer may choose a table scan. Do not conclude an index is broken just because the lab table has few rows.

### Step 5: Test Metadata-Only Queries

~~~sql
SELECT id, title
FROM notes
ORDER BY id DESC
LIMIT 20;
~~~

Then compare with:

~~~sql
SELECT *
FROM notes
ORDER BY id DESC
LIMIT 20;
~~~

When `body` is large, the first query reduces data read and network transfer if the screen only needs titles. This is a key habit when designing APIs and list views.

### Step 6: Clean Up

~~~sql
DROP DATABASE mysql_large_values_lab;
~~~

Run this command only against the lab database you just created. It deletes all practice data inside the database.

## 11. Common Issues

| Symptom | Common Cause | Resolution |
|---|---|---|
| `Data too long for column` | Value exceeds type limit or encoded byte limit | Check `TEXT`/`BLOB` tier, charset, actual byte size, and strict mode |
| `Packet too large` | Sent value exceeds client/server packet limit | Check `max_allowed_packet` on both sides and available memory |
| Cannot create index | `TEXT`/`BLOB` missing prefix length or prefix exceeds limit | Specify an appropriate prefix and check row format and page size |
| `BLOB/TEXT column can't have a default value` | Attempting to declare `DEFAULT` on `TEXT`/`BLOB` | Remove `DEFAULT`; pass explicit values from the application |
| Search does not handle accents/case as expected | Unsuitable `TEXT` collation | Choose the right collation or use explicit conversion/collation |
| `BLOB` displays as hex | Client renders binary strings in hexadecimal | Use `HEX` to inspect bytes; decode in the application using the known encoding |
| Slow queries with `SELECT *` | Fetching large content unnecessarily or spilling temporary tables to disk | Select only needed columns, paginate, and fetch large content on detail requests |
| Unexpected sorting of long `TEXT` | `max_sort_length` only considers the configured leading bytes | Inspect this variable and consider sorting by compact metadata instead |

## 12. Schema Design Guidelines for Choosing Types

Before creating a large column, answer these questions:

1. Is the content text or raw binary bytes?
2. Does it need linguistic/collation comparison or exact byte comparison?
3. What is the realistic maximum size in bytes?
4. Do you need full-text search, prefix search, full equality comparison, or ID-based lookup only?
5. Is the data read in list queries or only on detail views?
6. Should the content live in the database or is object storage a better fit?
7. Can connectors, clients, servers, backups, and replication handle the expected data size?

Quick rules of thumb:

- Short text with clear bounds: use `VARCHAR`.
- Long text needing Unicode and collation: use the `TEXT` family.
- Raw binary bytes that must remain intact: use the `BLOB` family.
- Content typically within 64 KiB: consider `TEXT`/`BLOB`.
- Content potentially exceeding 64 KiB but under 16 MiB: consider `MEDIUMTEXT`/`MEDIUMBLOB`.
- Only use `LONGTEXT`/`LONGBLOB` when real capacity requirements demand it.
- Do not fetch large columns in list queries when unneeded.
- Prefix indexes fit leading-prefix queries; evaluate `FULLTEXT` for natural-language search.
- When storing large files, consider keeping metadata in MySQL and file content in object storage.

## Official References

Limits and behaviors in this lesson were verified against the **MySQL 9.7 Reference Manual** as of **19-11-2026**:

1. [The BLOB and TEXT Types](https://dev.mysql.com/doc/refman/9.7/en/blob.html): differences between character strings and byte strings, limits, `DEFAULT`, prefix indexes, `max_sort_length`, and `max_allowed_packet`.
2. [String Data Type Syntax](https://dev.mysql.com/doc/refman/9.7/en/string-type-syntax.html): TINY/TEXT/MEDIUM/LONG tiers and length-prefix bytes.
3. [Data Type Storage Requirements](https://dev.mysql.com/doc/refman/9.7/en/storage-requirements.html): storage calculation and character set impact.
4. [Column Indexes](https://dev.mysql.com/doc/refman/9.7/en/column-indexes.html): prefix indexes and `FULLTEXT` indexes.
5. [CREATE INDEX Statement](https://dev.mysql.com/doc/refman/9.7/en/create-index.html): prefix syntax, storage engine limits, and unique prefix rules.
6. [InnoDB Row Formats](https://dev.mysql.com/doc/refman/9.7/en/innodb-row-format.html): inline/off-page storage of variable-length columns.
7. [Character Sets and Collations](https://dev.mysql.com/doc/refman/9.7/en/charset.html): character sets, collations, and string comparison rules.
