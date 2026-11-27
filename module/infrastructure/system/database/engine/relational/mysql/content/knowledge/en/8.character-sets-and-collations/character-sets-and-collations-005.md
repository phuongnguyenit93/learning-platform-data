# Character Length, Byte Length, and Index Limits

When designing text columns and indexes in MySQL, you must distinguish **character count** from **byte count**. A string may contain few characters yet occupy many bytes because character sets encode each character using varying numbers of bytes. Length limits for `CHAR`/`VARCHAR` are declared in characters, whereas row size limits and index key limits are calculated in bytes.

This distinction is especially important with `utf8mb4`: a single character can require up to 4 bytes. For example, an index over 200 `utf8mb4` characters can require up to 800 bytes for the string value portion alone. For composite indexes across multiple columns, the total byte length of all key parts together determines whether the index exceeds the limit.

This lesson shows how to measure lengths in SQL, read charset/column/index metadata, calculate maximum string sizes, and evaluate InnoDB index limits. The examples target MySQL 8.x with InnoDB; actual limits also depend on the version, `innodb_page_size`, row format, and storage engine type.

## 1. Characters and bytes are two different units

A character is the unit a user sees or enters in text. A byte is the unit of data encoded and stored. A character set maps characters to one or more bytes.

Common examples:

| Character set | Max bytes per character | Notes |
| --- | ---: | --- |
| `ascii` | 1 | Represents only the ASCII character set |
| `latin1` | 1 | Each character uses one byte in this character set |
| `utf8mb3` | 3 | MySQL's legacy UTF-8 charset; does not fully represent all Unicode code points |
| `utf8mb4` | 4 | Full Unicode support, including many supplementary characters and emojis |

You cannot deduce byte count solely from character count without knowing the charset and specific content. With `utf8mb4`, ASCII strings may still use only one byte per character; Vietnamese with diacritics or emojis can require more bytes.

## 2. Measuring length with CHAR_LENGTH, LENGTH, and OCTET_LENGTH

MySQL provides the following functions:

- `CHAR_LENGTH(str)` returns the number of characters in the string.
- `CHARACTER_LENGTH(str)` is a synonym for `CHAR_LENGTH`.
- `LENGTH(str)` returns the number of bytes in the string according to the value's character set.
- `OCTET_LENGTH(str)` is a synonym for `LENGTH`.

Example with an ASCII character, an accented character, and an emoji:

```sql
SET NAMES utf8mb4;

SELECT
    _utf8mb4'Aé😊' AS sample_text,
    CHAR_LENGTH(_utf8mb4'Aé😊') AS character_count,
    LENGTH(_utf8mb4'Aé😊') AS byte_count,
    OCTET_LENGTH(_utf8mb4'Aé😊') AS octet_count;
```

For this sample string, the character count is 3: `A`, `é`, and `😊`. The byte count in `utf8mb4` is 7: `A` uses 1 byte, `é` uses 2 bytes, and the emoji uses 4 bytes. `LENGTH()` and `OCTET_LENGTH()` return the same result.

Note that MySQL's character-counting functions count character units per the character set/code points, not visual grapheme clusters as perceived by the human eye. An accented letter may be represented as a precomposed code point or as a base character plus a combining mark; two visually identical strings can therefore have different code point counts and byte counts.

Do not use `LENGTH()` to validate business limits defined in terms of character count. Conversely, do not rely solely on `CHAR_LENGTH()` when evaluating storage footprint or index limits.

## 3. Character sets indicate the maximum byte count

You can inspect the character sets supported by MySQL and their `MAXLEN`:

```sql
SELECT
    CHARACTER_SET_NAME,
    DEFAULT_COLLATE_NAME,
    MAXLEN
FROM INFORMATION_SCHEMA.CHARACTER_SETS
WHERE CHARACTER_SET_NAME IN ('ascii', 'latin1', 'utf8mb3', 'utf8mb4')
ORDER BY CHARACTER_SET_NAME;
```

For `utf8mb4`, `MAXLEN` is 4. This is the maximum number of bytes per character; it does not mean every character in the column always occupies 4 bytes.

In MySQL, the name `utf8` was historically an alias for `utf8mb3`. For new schemas, explicitly declare `utf8mb4` to avoid confusion and ensure full Unicode support.

You can view the default charset and collation of the current database:

```sql
SELECT
    SCHEMA_NAME,
    DEFAULT_CHARACTER_SET_NAME,
    DEFAULT_COLLATION_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
WHERE SCHEMA_NAME = DATABASE();
```

Charset/collation can be configured at the server, database, table, or column level. The actual setting of each individual column is what must be used when calculating index byte limits.

## 4. Declared length of CHAR and VARCHAR

For non-binary strings, `CHAR(n)` and `VARCHAR(n)` declare limits in characters, not bytes.

Example:

```sql
CREATE TABLE text_length_demo (
    ascii_code VARCHAR(100)
        CHARACTER SET ascii,
    vietnamese_text VARCHAR(100)
        CHARACTER SET utf8mb4,
    fixed_country_code CHAR(2)
        CHARACTER SET ascii
) ENGINE=InnoDB;
```

Both `VARCHAR(100)` columns allow up to 100 characters, yet their maximum byte limits differ:

- `ascii_code`: up to about 100 bytes for ASCII character data.
- `vietnamese_text`: up to 400 bytes of character data under the 4-byte/character limit of `utf8mb4`.

`VARCHAR` also has prefix bytes to store the actual length. MySQL typically uses one prefix byte if the column's maximum byte length does not exceed 255; if larger, it uses two bytes. Thus, `VARCHAR(100)` with `ascii` can use a 1-byte length prefix, whereas `VARCHAR(100)` with `utf8mb4` has a maximum potential of 400 bytes and requires a 2-byte length prefix.

This estimates the string portion of a column, not the formula for total InnoDB row size. Records also have metadata, null bitmaps, transaction metadata, indexes, and page-layout overhead. Row format also affects how long data is stored.

## 5. Viewing character and byte limits from INFORMATION_SCHEMA

Column metadata provides both character length and maximum byte length:

```sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    COLUMN_TYPE,
    CHARACTER_SET_NAME,
    COLLATION_NAME,
    CHARACTER_MAXIMUM_LENGTH,
    CHARACTER_OCTET_LENGTH
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND CHARACTER_MAXIMUM_LENGTH IS NOT NULL
ORDER BY TABLE_NAME, ORDINAL_POSITION;
```

Meaning of the two key columns:

- `CHARACTER_MAXIMUM_LENGTH`: maximum length in characters.
- `CHARACTER_OCTET_LENGTH`: maximum length in bytes.

For example, a `VARCHAR(100)` column using `utf8mb4` typically has `CHARACTER_MAXIMUM_LENGTH = 100` and `CHARACTER_OCTET_LENGTH = 400`. If the column uses `ascii`, both values are usually 100.

When evaluating an existing schema, read the metadata rather than inferring charsets from column names or database defaults. A table may have columns using different charsets/collations due to migration history.

## 6. Row size limits are not the same as index limits

MySQL has a maximum defined row size limit of 65,535 bytes, shared across columns and affected by overhead. For `VARCHAR` columns, the maximum data portion is calculated based on the bytes the charset might require, plus length storage. Therefore, multiple large `VARCHAR` columns can cause a `CREATE TABLE` statement to exceed the row limit even if each individual column has a valid length.

With InnoDB, certain long data such as `TEXT`/`BLOB` or variable-length values may be stored off-page outside the main data page depending on row format and record size. Off-page storage does not eliminate all MySQL definition limits; metadata or storage pointers still carry overhead.

Row limits and index limits are two separate checks:

- Row limits determine whether a record's definition and data can be validly organized.
- Index limits determine whether the total size of an index's key parts exceeds the engine's limit.

A table can succeed in creation while an index on a long text column still fails. Conversely, a short index does not guarantee the entire row definition is valid.

## 7. Why are indexes measured in bytes?

B-tree indexes must store key values for sorting and searching. For string columns, key values are represented using the column's character set and collation; the maximum size depends on the bytes potentially required for the characters.

With `utf8mb4`, you can estimate the maximum string data portion as follows:

\[
\text{Max bytes} = \text{Indexed characters} \times 4
\]

Examples:

| Index length in characters | Charset | Max bytes for string portion |
| ---: | --- | ---: |
| 100 | `ascii` | 100 |
| 100 | `utf8mb4` | 400 |
| 191 | `utf8mb4` | 764 |
| 255 | `utf8mb4` | 1,020 |
| 500 | `utf8mb4` | 2,000 |

This calculation covers the string data portion of a key part. An actual index may also include other columns, numeric types, nullable flags, and internal metadata. For composite indexes, you must sum the byte limits of all key parts rather than looking only at the longest column.

## 8. InnoDB key length limits

With InnoDB using the default 16 KB page size and `DYNAMIC` or `COMPRESSED` row format, the common key length limit is 3,072 bytes. This limit scales down with smaller page sizes: 1,536 bytes for 8 KB pages and 768 bytes for 4 KB pages.

With legacy `COMPACT` or `REDUNDANT` row formats, the prefix/key length limit on a 16 KB page configuration is 767 bytes. This is why many older guides recommended `VARCHAR(191)` for `utf8mb4` indexes: 191 × 4 = 764 bytes, fitting within the 767-byte limit. On modern MySQL 8.x setups with InnoDB `DYNAMIC` and 16 KB pages, you do not need to mechanically apply the number 191 to every column.

Check page size:

```sql
SHOW VARIABLES LIKE 'innodb_page_size';
```

Check table row formats:

```sql
SELECT
    TABLE_NAME,
    ENGINE,
    ROW_FORMAT
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
```

Actual limits also depend on the MySQL version, engine, and configuration. `innodb_page_size` is determined at instance initialization; it cannot be changed arbitrarily via a runtime variable on a running instance. If your environment uses a non-default page size or row format, check your version's documentation before designing indexes.

## 9. Index prefixes and how length is declared

For string columns, you can create an index on the full value or on a leading prefix of the value. Example:

```sql
CREATE TABLE articles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(500) NOT NULL,
    body TEXT,
    PRIMARY KEY (id),
    KEY idx_articles_title (title(150)),
    KEY idx_articles_body_prefix (body(100))
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

For non-binary string columns such as `CHAR`, `VARCHAR`, or `TEXT`, the prefix length in DDL is measured in characters. Thus `title(150)` can require up to 600 bytes for the prefix portion in `utf8mb4`. For binary types such as `BINARY`, `VARBINARY`, or `BLOB`, the prefix length is measured in bytes.

Index prefixes help reduce key size, but have limitations:

- The index stores only the leading part of the value, so different values can share the same prefix.
- Queries needing to distinguish the full string may still have to read the row to inspect the remainder.
- Too short a prefix has low selectivity and may not help queries much.
- A prefix index is not semantically equivalent to a full-column index.

In particular, a unique prefix index only guarantees uniqueness of the prefix. If two strings share the same first 100 characters but differ afterward, a unique index on `column(100)` still treats them as a conflict. If business rules require the entire email or identifier to be unique, use a full index or an alternative key design that guarantees the proper semantics.

## 10. Composite index limits

For multi-column indexes, the total maximum length of all key parts must stay within the engine's limit. Example:

```sql
CREATE TABLE tenant_documents (
    tenant_id BIGINT UNSIGNED NOT NULL,
    slug VARCHAR(200) NOT NULL,
    title VARCHAR(300) NOT NULL,
    PRIMARY KEY (tenant_id, slug),
    KEY idx_tenant_title (tenant_id, title(100))
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

Estimate for the primary key:

- `tenant_id`: 8 bytes.
- `slug`: up to 200 × 4 = 800 bytes.
- Total key value portion: roughly 808 bytes before internal overhead.

Estimate for `idx_tenant_title`:

- `tenant_id`: 8 bytes.
- Prefix `title(100)`: up to 100 × 4 = 400 bytes.
- Total key value portion: roughly 408 bytes before internal overhead.

Both indexes fit well below the common 3,072-byte limit of 16 KB InnoDB with modern row formats, yet the primary key index could exceed the 767-byte limit under legacy `COMPACT`/`REDUNDANT` setups. This is why you must sum all key parts and check the row format rather than inspecting each column in isolation.

Composite indexes also follow the leftmost prefix rule for usability. An index `(tenant_id, status, created_at)` generally supports predicates starting from `tenant_id`; it is not automatically equivalent to an index on `status` alone. Column ordering must be designed from actual queries and `EXPLAIN`, not just byte math.

## 11. Inspecting indexes and prefixes from metadata

`SHOW INDEX` or `SHOW KEYS` shows the columns and their order in an index:

```sql
SHOW INDEX FROM tenant_documents;
```

Detailed metadata can be read via `INFORMATION_SCHEMA.STATISTICS`:

```sql
SELECT
    TABLE_NAME,
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    SUB_PART,
    INDEX_TYPE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
```

`SUB_PART` indicates the prefix length if the index uses only part of the column; a `NULL` value generally indicates the index covers the full column. For non-binary strings, `SUB_PART` is in characters; for binary types, it is in bytes.

To check the query execution plan:

```sql
EXPLAIN
SELECT id, title
FROM articles
WHERE title LIKE 'MySQL%';
```

`EXPLAIN` lets you verify whether the optimizer chooses the index. A prefix index does not guarantee every query on the column will be optimized; search conditions, collation, patterns, statistics, and data distribution all influence the plan.

## 12. Example of a key-too-long error and how to handle it

Suppose a table has a column `title VARCHAR(1000) CHARACTER SET utf8mb4` and creates a full index:

```sql
CREATE TABLE long_titles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(1000) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_long_titles_title (title)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

The string value portion of the index can require up to 4,000 bytes. This exceeds the common 3,072-byte InnoDB limit with 16 KB pages, so creating the index can fail with a key length error.

Handling options to consider based on requirements:

1. **Reduce column length** if business rules genuinely cap the string shorter.
2. **Use a prefix index** if queries only need to search by a sufficiently selective prefix and do not rely on that prefix to enforce full-string uniqueness.
3. **Design a better composite index**, dropping unnecessary key parts or reducing prefix length based on queries.
4. **Choose an appropriate data type**, such as `TEXT` for long content and indexing only a required prefix; remember that `TEXT` also requires a prefix for standard indexing.
5. **Check row format/page size** and actual server limits before changing configuration or migrating data.

Do not switch `utf8mb4` to `latin1` just to make an index fit a limit if the data requires Unicode. Doing so removes the ability to store valid characters and creates data conversion errors. Also do not use a prefix index as a unique key if business logic requires full-string uniqueness.

## 13. Measuring actual data before choosing a prefix

Maximum limits help validate the schema, while actual data lengths and distinctness help choose a useful prefix. You can measure the maximum length:

```sql
SELECT
    MAX(CHAR_LENGTH(title)) AS max_characters,
    MAX(OCTET_LENGTH(title)) AS max_bytes,
    AVG(CHAR_LENGTH(title)) AS average_characters
FROM articles;
```

To evaluate prefix selectivity, you can compare the count of distinct prefixes against total rows:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(DISTINCT LEFT(title, 50)) AS distinct_prefix_50,
    COUNT(DISTINCT LEFT(title, 100)) AS distinct_prefix_100
FROM articles;
```

These measurements are only a starting point. Test on representative data, consider distributions by tenant or status, and benchmark real queries. For columns with many values sharing common prefixes, longer prefixes increase selectivity but also increase index size.

## 14. Workflow for designing string columns and indexes

Before creating a column or index, follow this sequence:

1. Determine whether the data is text or binary bytes.
2. Choose a charset matching the business character repertoire; for modern Unicode text, prefer `utf8mb4`.
3. Define business limits in characters and check `CHARACTER_OCTET_LENGTH`.
4. Calculate maximum bytes for each key part based on charset and prefix length.
5. Sum the maximum sizes of all key parts in composite indexes.
6. Check `innodb_page_size`, row format, and version/storage engine limits.
7. Decide between full or prefix indexes; check uniqueness semantics before choosing a prefix.
8. Review real queries, use `EXPLAIN`, and measure performance after creating the index.
9. Verify metadata via `SHOW CREATE TABLE`, `SHOW INDEX`, and `INFORMATION_SCHEMA`.

## 15. Practice exercises

1. Run `CHAR_LENGTH`, `LENGTH`, and `OCTET_LENGTH` on ASCII strings, Vietnamese strings with diacritics, and emojis; explain the differences.
2. Query `INFORMATION_SCHEMA.CHARACTER_SETS` to view `MAXLEN` for `ascii`, `latin1`, and `utf8mb4`.
3. Create two `VARCHAR(100)` columns, one using `ascii` and one using `utf8mb4`; compare `CHARACTER_MAXIMUM_LENGTH` and `CHARACTER_OCTET_LENGTH`.
4. Check `innodb_page_size` and `ROW_FORMAT` of InnoDB tables in your lab environment.
5. Calculate the maximum index size on `VARCHAR(191)`, `VARCHAR(255)`, and `VARCHAR(500)` using `utf8mb4`.
6. Create a prefix index on a `VARCHAR(500)` column and inspect `SUB_PART` via `INFORMATION_SCHEMA.STATISTICS`.
7. Create a unique prefix index in the lab schema, test two strings with identical prefixes but different endings, and observe the result.
8. Create a composite index containing a `BIGINT` column and a `VARCHAR` column using `utf8mb4`; calculate total max bytes and compare against the server limit.
9. Use `EXPLAIN` to check whether a query leverages the prefix index as intended.

## 16. Takeaways

The declared length of `CHAR`/`VARCHAR` is measured in characters; `CHAR_LENGTH()` counts characters while `LENGTH()`/`OCTET_LENGTH()` count bytes. With `utf8mb4`, each character can take up to 4 bytes. `INFORMATION_SCHEMA.COLUMNS` exposes both `CHARACTER_MAXIMUM_LENGTH` and `CHARACTER_OCTET_LENGTH` for metadata inspection.

Index limits are calculated in bytes and apply to the sum of all key parts. Modern InnoDB with 16 KB pages and `DYNAMIC`/`COMPRESSED` row formats commonly supports up to 3,072 bytes for key length; smaller page sizes or legacy row formats have lower limits. Prefix indexes can shrink key size, yet change uniqueness semantics if used on a unique index. Calculate bytes per charset, check page size/row format, verify metadata, and benchmark queries before finalizing index design.
