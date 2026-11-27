# Designing Character Sets and Collations for Storing and Searching Vietnamese Text

Applications that store Vietnamese personal names, addresses, products, and content must handle diacritics, letter case, sorting, and searching accurately. Choosing the wrong character set or collation can lead to garbled display, comparisons treating distinct strings as equivalent (or vice versa), or queries failing to use indexes as expected.

Design requires distinguishing two concepts: the **character set** determines how characters are encoded into bytes; the **collation** determines how strings in that character set are compared and sorted. For modern Vietnamese data, the baseline choice should be `utf8mb4`, followed by selecting a collation aligned with business rules for search, uniqueness, and sort order. Within the `DATABASE_MYSQL` module, this lesson brings together table design, data types, indexing, querying, and relational data operations.

After this lesson, you will be able to:

- Distinguish between character sets and collations.
- Choose `utf8mb4` to store Vietnamese and other Unicode characters.
- Understand `ai`, `as`, `ci`, `cs` suffixes and binary collations.
- Select comparison rules for searching names, emails, identifiers, and content.
- Verify how collation affects `=`, `LIKE`, `ORDER BY`, and unique indexes.
- Design schemas, indexes, and Java/Connector/J connections consistently.
- Normalize Unicode and migrate legacy data safely.
- Test with accented Vietnamese words, unaccented words, and letter-case variations.

## 1. How Do Character Sets and Collations Differ?

A character set is a collection of characters and the rules for encoding those characters into bytes. A collation is a set of rules determining whether two strings are considered equal and which string comes first when sorting.

For example, `utf8mb4` can store Vietnamese characters such as `ă`, `â`, `đ`, `ê`, `ô`, `ơ`, `ư`, tone marks, and even emojis. An accent-insensitive collation may treat certain accented and unaccented forms as equivalent during comparison; an accent-sensitive collation distinguishes them.

| Property | Question Answered | Example |
|---|---|---|
| Character set | How are characters encoded into bytes? | `utf8mb4` |
| Collation | What rules govern string comparison and sorting? | `utf8mb4_0900_ai_ci` |

Two columns that both use `utf8mb4` but have different collations can still yield different outcomes for `=`, `LIKE`, `ORDER BY`, `GROUP BY`, and uniqueness.

## 2. Why Use `utf8mb4`?

MySQL provides different UTF-8 character sets. `utf8mb3` uses at most three bytes per character and cannot represent all of Unicode. The name `utf8` in MySQL is a legacy alias for `utf8mb3` in modern versions and has been deprecated. For new schemas, always use `utf8mb4`.

`utf8mb4` supports up to four bytes per character, covering the entirety of Unicode, including Vietnamese and supplementary characters outside the Basic Multilingual Plane.

Check the server character set and collation:

```sql
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
```

Check the current database:

```sql
SELECT
    SCHEMA_NAME,
    DEFAULT_CHARACTER_SET_NAME,
    DEFAULT_COLLATION_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
WHERE SCHEMA_NAME = DATABASE();
```

Do not rely solely on server defaults. Explicitly declare the character set and collation at the database, table, or column level so schema behavior stays consistent across environments.

## 3. Reading Collation Names

MySQL collation names typically encode the character set and comparison rules. For the common UCA 9.0 collations in MySQL 8.0:

| Component | Meaning |
|---|---|
| `utf8mb4` | Character set |
| `0900` | Unicode Collation Algorithm version 9.0 rule set |
| `ai` | Accent-insensitive: ignores accent differences in collation comparisons |
| `as` | Accent-sensitive: distinguishes accent differences |
| `ci` | Case-insensitive: ignores uppercase/lowercase differences |
| `cs` | Case-sensitive: distinguishes uppercase/lowercase differences |
| `bin` | Compares by encoded binary values/code units of the character set |

Examples:

- `utf8mb4_0900_ai_ci`: accent-insensitive and case-insensitive.
- `utf8mb4_0900_as_ci`: accent-sensitive and case-insensitive.
- `utf8mb4_0900_as_cs`: accent-sensitive and case-sensitive.
- `utf8mb4_bin`: binary collation belonging to the `utf8mb4` character set.

Not every collation exists in every MySQL version or distribution. Check the actual available list:

```sql
SHOW COLLATION LIKE 'utf8mb4%';
```

MySQL 8.0 includes the `utf8mb4_0900_*` collations. On MySQL 5.7 or older environments, you may need to use collations such as `utf8mb4_unicode_ci`; verify the version and `SHOW COLLATION` output before writing DDL.

## 4. Choosing Collations for Vietnamese Business Rules

No single collation is optimal for every column. Display names, emails, product SKUs, and identifiers each have different comparison requirements.

### 4.1. Accent-insensitive name search

An application may want users typing `nguyen` to find `Nguyễn`. An accent-insensitive/case-insensitive collation like `utf8mb4_0900_ai_ci` can support this behavior for characters the collation treats as equivalent.

Example:

```sql
CREATE TABLE customer_search_demo (
    customer_id BIGINT NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(200) NOT NULL,
    PRIMARY KEY (customer_id),
    KEY idx_customer_full_name (full_name)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

INSERT INTO customer_search_demo (full_name)
VALUES ('Nguyễn Văn An'), ('Trần Thị Bình'), ('Đặng Minh Châu');

SELECT customer_id, full_name
FROM customer_search_demo
WHERE full_name LIKE '%nguyen%';
```

The example above demonstrates accent-insensitive matching; because the pattern `'%nguyen%'` has a leading wildcard, a standard B-tree index cannot perform a prefix range scan. Collation alone does not make substring-contains searches indexable.

### 4.2. Accent-sensitive search

For codes or keywords where diacritics alter meaning, choose an accent-sensitive collation. Example:

```sql
CREATE TABLE dictionary_entry (
    entry_id BIGINT NOT NULL AUTO_INCREMENT,
    term VARCHAR(150) NOT NULL,
    PRIMARY KEY (entry_id),
    KEY idx_dictionary_term (term)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_as_ci;
```

In this collation, `ci` ignores case while `as` distinguishes accents. If case sensitivity is also needed, consider `utf8mb4_0900_as_cs`.

### 4.3. Language-specific collations and dictionary order

General UCA collations follow generic Unicode rules; language-tailored collations can sort certain letters according to that language's specific rules. For Vietnamese, `ORDER BY` display ordering can be an important product requirement, especially in directories, dictionaries, or name lists.

Do not assume the server's default collation provides the Vietnamese dictionary order your business expects. Inspect available locale-specific collations with `SHOW COLLATION`, then test representative letters and words such as `a`, `ă`, `â`, `b`, `d`, `đ`, `e`, `ê`, `o`, `ô`, `ơ`, `u`, `ư` along with tone marks. Choose a collation after verifying its actual sort order on the exact target MySQL version.

### 4.4. Accent-insensitive does not mean all strings match equally

Unicode-based collations rely on specific weights and rules. Do not assume every accented letter automatically equals its unaccented counterpart, or that `đ` is always treated the same as `d`. Run comparisons on the target server version using the application's actual test word set.

## 5. Testing Comparison Behavior with SQL

Test two strings directly under the target collation:

```sql
SELECT
    _utf8mb4'Nguyễn' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'Nguyen' COLLATE utf8mb4_0900_ai_ci AS accent_insensitive,

    _utf8mb4'Nguyễn' COLLATE utf8mb4_0900_as_ci =
    _utf8mb4'Nguyen' COLLATE utf8mb4_0900_as_ci AS accent_sensitive,

    _utf8mb4'NGUYEN' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'nguyen' COLLATE utf8mb4_0900_ai_ci AS case_insensitive;
```

Conceptual expected results:

- The first comparison may treat the two strings as equivalent under the accent-insensitive collation.
- The second comparison distinguishes the accents.
- The third comparison ignores letter case.

The literal introducer `_utf8mb4` specifies the string's character set; `COLLATE` specifies the comparison rule. Run this test on the actual target server because collations and versions can differ.

Test behavior with real Vietnamese words:

```sql
SELECT
    _utf8mb4'ma' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'má' COLLATE utf8mb4_0900_ai_ci AS ma_vs_ma_tone,

    _utf8mb4'd' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'đ' COLLATE utf8mb4_0900_ai_ci AS d_vs_d_stroke,

    _utf8mb4'hoa' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'HÒA' COLLATE utf8mb4_0900_ai_ci AS case_and_accent;
```

Do not hardcode assumptions about `d`/`đ` or any character pair in business logic before verifying the actual output. Your test suite should explicitly capture pairs that business rules require to match or differ.

## 6. Declaring Character Sets and Collations at the Right Level

MySQL lets you configure defaults at the server, database, table, and column levels. A lower-level setting overrides higher-level defaults.

### 6.1. Database

```sql
CREATE DATABASE shop
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
```

### 6.2. Table

```sql
CREATE TABLE customers (
    customer_id BIGINT NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(200) NOT NULL,
    email VARCHAR(254) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email),
    KEY idx_customers_full_name (full_name)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

In this example, `email` inherits the table's accent-insensitive/case-insensitive collation. This means the unique index also uses that comparison rule. For emails, this can be a reasonable product policy if the system intentionally treats email addresses as case-insensitive, yet it should not be applied accidentally; normalization and uniqueness rules need to be explicitly defined.

### 6.3. Column

You can set a dedicated collation per column:

```sql
CREATE TABLE customer_profile (
    customer_id BIGINT NOT NULL,
    display_name VARCHAR(200)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci NOT NULL,
    legal_name VARCHAR(200)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_as_cs NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;
```

This example illustrates two distinct policies: display names support accent- and case-insensitive searching, while legal names are compared more strictly. In real systems, clarify storage and search requirements before choosing policies.

## 7. Impact on Unique Indexes and Duplicate Data

Collation determines whether two string values are considered duplicates when enforcing a unique key. If a column uses an accent-insensitive/case-insensitive collation, strings differing in diacritics or case that are equivalent under that collation can collide on the unique index.

For example, under a case-insensitive collation, `An@example.com` and `an@example.com` may be treated as the same value. Under an accent-insensitive collation, names with different accents may be treated as equivalent depending on weight rules.

Before creating or altering a unique index, check for collisions under the target collation:

```sql
SELECT
    email COLLATE utf8mb4_0900_ai_ci AS comparison_value,
    COUNT(*) AS duplicate_count
FROM customers
GROUP BY email COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
```

Do the same for names, codes, or fields receiving a unique constraint. If the query returns duplicate groups, decide the business rule for merging, updating values, or selecting another collation before creating the index.

### 7.1. Separating search policy and uniqueness policy

Sometimes users need accent-insensitive name searching while the system must still preserve two distinct accented names separately. Do not force one column to serve both requirements with the same collation if they conflict.

Options include:

- Keep the original column with a collation suited for storage and uniqueness.
- Add a separate normalized search column maintained by the application and index it.
- Create a generated column or functional index if the normalization expression and MySQL version support it.
- Offload search to a dedicated search service when diacritic stripping, tokenization, or ranking exceed collation capabilities.

If using a search-key column, define a stable normalization algorithm, version it when necessary, and ensure the original data remains untouched.

## 8. Collation and Index Performance

String indexes are ordered according to the column's collation. When a query compares using that same collation, the optimizer can use the index normally. Applying a different collation inline in the expression, or wrapping the column in a function, can change index usability.

Example:

```sql
-- Compare using the collation defined on the column.
SELECT customer_id, full_name
FROM customers
WHERE full_name = 'Nguyen Van An';

-- Forcing a different collation in the query may change index usage.
SELECT customer_id, full_name
FROM customers
WHERE full_name COLLATE utf8mb4_0900_as_cs = 'Nguyen Van An';
```

Run `EXPLAIN` on both queries to verify the access path. If the application frequently needs two different comparison behaviors, consider separate columns/indexes instead of forcing a different collation in every query.

### 8.1. Index length limits with `utf8mb4`

`utf8mb4` can require up to four bytes per character. A `VARCHAR(255)` column may require up to 1,020 bytes for character data alone, excluding overhead and other columns in a composite index. InnoDB key length limits depend on version, page size, row format, and configuration; do not treat the old 191-character rule of thumb as a universal limit.

Before creating an index:

- Check key length limits for your InnoDB version and configuration.
- Check total byte length across composite indexes.
- Consider an index prefix if appropriate for the queries and semantics.
- Do not treat a prefix unique key as equivalent to full-string uniqueness: two values differing only after the prefix will be rejected as duplicates.
- Evaluate selectivity, write overhead, and index storage size.

## 9. Exact, Prefix, and Substring Search

Collation controls character comparison, while pattern shape and indexing still govern performance.

| Query | Meaning | B-tree Index Usability |
|---|---|---|
| `name = 'Nguyen'` | Equality comparison using column collation | Usually able to use the index |
| `name LIKE 'Nguyen%'` | Prefix search | Usually able to use an index range scan |
| `name LIKE '%Nguyen'` | Suffix search | Usually cannot use a B-tree range scan |
| `name LIKE '%Nguyen%'` | Substring search at any position | Usually requires a scan; consider a search index/service |

Example:

```sql
SELECT customer_id, full_name
FROM customers
WHERE full_name LIKE 'nguyen%';
```

With an accent-insensitive/case-insensitive collation, this query can match multiple accent and case forms according to collation rules. However, if the pattern starts with `%`, a standard B-tree index cannot locate a range starting point from a prefix.

For Vietnamese contains-style name search, consider data scale, tokenization, diacritic-stripping rules, and ranking. MySQL FULLTEXT has its own tokenization and stopword behavior; test it against real Vietnamese text. When fuzzy matching, typo tolerance, suggestions, or complex diacritic folding are required, a dedicated search engine may be a better fit.

## 10. Unicode Normalization: NFC and NFD

Unicode allows a visible character to be represented either by a single precomposed code point or by a sequence of a base character plus combining marks. For instance, an accented Vietnamese vowel can have a precomposed representation or a decomposed representation.

Two strings may look identical visually while having different byte sequences. Modern collations handle certain Unicode equivalences, yet you should not rely on the assumption that every system, driver, and search algorithm normalizes identically.

Recommendations:

- Normalize input text to Unicode NFC at the application boundary if data policy permits.
- Preserve user-entered content as required by business rules; if verbatim storage is needed, keep a separate raw field.
- Apply the same normalization algorithm across writes, searches, imports, and data synchronization.
- Test NFC/NFD strings, tone marks, the letter `đ`, combining characters, and emojis.
- Do not use diacritic stripping as the sole normalization step, as it discards meaningful distinctions.

Java example:

```java
import java.text.Normalizer;

String normalizedName = Normalizer.normalize(
    inputName,
    Normalizer.Form.NFC
);
```

NFC standardizes the Unicode representation; it does not strip Vietnamese accents and does not replace database collation.

## 11. Configuring Java/Connector/J Application Connections

Applications must send and receive strings using a consistent character encoding. In modern Connector/J, UTF-8 maps to `utf8mb4` on MySQL; still, verify the driver version and actual session state.

Example JDBC URL:

```text
jdbc:mysql://mysql.example.internal:3306/shop?characterEncoding=UTF-8
```

After connecting, verify:

```sql
SHOW SESSION VARIABLES LIKE 'character_set_client';
SHOW SESSION VARIABLES LIKE 'character_set_connection';
SHOW SESSION VARIABLES LIKE 'character_set_results';
SHOW SESSION VARIABLES LIKE 'collation_connection';
```

Roles of these variables:

- `character_set_client`: encoding the server uses to interpret bytes sent by the client.
- `character_set_connection`: character set used for expressions and literals after receiving input.
- `character_set_results`: encoding used when returning results to the client.
- `collation_connection`: collation for comparisons in certain expressions/literals.

The column's own collation still governs column comparison semantics against compatible literals, though collation coercibility and expression conversions can affect results. If you encounter `Illegal mix of collations`, inspect the collations of involved columns, literals, connection settings, and JOIN/UNION expressions.

### 11.1. Spring Boot

Configuration example:

```properties
spring.datasource.url=jdbc:mysql://mysql.example.internal:3306/shop?characterEncoding=UTF-8
spring.datasource.username=${SHOP_DB_USER}
spring.datasource.password=${SHOP_DB_PASSWORD}
```

Secrets should be injected from a secret manager or secured deployment environment. Never commit passwords to a repository. Declare table/column collations in migrations; do not rely on `collation_connection` as a substitute for schema definitions.

### 11.2. Do not arbitrarily run `SET NAMES` on a connection pool

`SET NAMES` alters session variables. With a connection pool, sessions are reused across different requests. Let Connector/J manage character encoding via driver configuration and verify session state. If you must alter session state, ensure the pool resets it before returning the connection for reuse.

## 12. Migrating Legacy Schemas to `utf8mb4`

Before converting legacy tables, identify both the declared character set and the actual byte encoding. There are two distinct scenarios:

1. **Data was stored properly under the old character set:** `ALTER TABLE ... CONVERT TO CHARACTER SET utf8mb4` lets MySQL convert characters from the old encoding to UTF-8.
2. **Data already suffers from mojibake:** UTF-8 bytes were previously misinterpreted as latin1 or another encoding. Simply converting the schema may preserve corrupted strings or worsen data damage; a dedicated data-repair workflow is required after identifying the byte origin.

Inspect the current definition:

```sql
SHOW CREATE TABLE customers\G

SELECT
    COLUMN_NAME,
    CHARACTER_SET_NAME,
    COLLATION_NAME,
    COLUMN_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customers';
```

### 12.1. Conversion planning

1. Back up and test restoring in an isolated environment.
2. Inspect actual encoding using representative samples, including Vietnamese names, combining marks, and non-BMP characters.
3. Check for unique collisions under the target collation.
4. Check index lengths, composite indexes, foreign keys, and dependent views/routines.
5. Dry-run the conversion on a replica sized close to production.
6. Measure duration, locks, I/O, temporary disk space, and replication lag.
7. Choose an appropriate maintenance window or online schema change strategy.
8. After conversion, verify data, query plans, sort order, uniqueness, and application behavior.

Table conversion example:

```sql
ALTER TABLE customers
    CONVERT TO CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
```

This statement can rebuild the table and indexes, consume significant I/O and disk space, wait on metadata locks, and impact replication. Never run it directly on large tables during peak traffic without testing first.

### 12.2. Checking collisions before changing collation

A new collation may consider two previously distinct values equal. Before altering a column with a unique index, run a grouping query under the target collation:

```sql
SELECT
    email COLLATE utf8mb4_0900_ai_ci AS comparison_value,
    COUNT(*) AS row_count
FROM customers
GROUP BY email COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
```

Repeat for all columns with unique constraints and composite keys. If collisions exist, define a data resolution policy before running `ALTER TABLE`; otherwise, the migration may fail when rebuilding the unique index.

### 12.3. Distinguishing charset conversion from mojibake repair

Do not blindly run byte-reinterpretation casts like `CONVERT(CAST(... AS BINARY) USING ...)` across an entire table simply because characters look wrong. The right repair depends on the original bytes, declared charset, and which step misinterpreted the string. First make a copy, select samples whose data origin is known, inspect bytes with `HEX(column)`, and test recovery on the copy.

If characters were already replaced with `?` or replacement characters during writes, the original information may be permanently lost and cannot be recovered merely by changing collations.

## 13. Common Pitfalls

| Symptom | Possible Cause | How to Investigate |
|---|---|---|
| Vietnamese turns into `?` or garbled characters | Client/server charset mismatch or data written incorrectly | Check session charsets, DDL, and raw bytes via `HEX()` |
| Some emojis fail | Table/column uses `utf8mb3` or unsuitable client encoding | Switch to `utf8mb4` and verify driver settings |
| Searching `nguyen` does not find `Nguyễn` | Column uses an accent-sensitive collation or query forces another collation | Check column collation and comparison expressions |
| `Nguyen` and `Nguyễn` treated as duplicates | Unique index uses an accent-insensitive collation | Review uniqueness requirements and check collisions before migration |
| Vietnamese name sort order is unexpected | Collation lacks suitable language sorting rules | Compare tailored collations with a test word set |
| `Illegal mix of collations` | Expression combines strings from columns/literals with incompatible collations | Check `COLLATION()`, column metadata, and connection settings |
| Query slows down after adding `COLLATE` in WHERE | Expression using a different collation alters index usability | Run `EXPLAIN`; consider column collation or a separate search key |
| Collation migration fails | Unique key collision or index length limit exceeded | Find collisions, calculate byte lengths, and inspect indexes |
| Switched to utf8mb4 but text is still broken | Data already suffered from mojibake beforehand | Identify original bytes and run a dedicated repair procedure |

## 14. Vietnamese Test Suite for Schema and Search

A test suite should cover the following data groups:

| Group | Examples | Purpose |
|---|---|---|
| Accented vowels | `a`, `á`, `à`, `ả`, `ã`, `ạ` | Verify accent sensitivity |
| Variant vowels | `a`, `ă`, `â`; `e`, `ê`; `o`, `ô`, `ơ`; `u`, `ư` | Verify weights and sorting |
| Consonants | `d`, `đ` | Verify collation-specific rules |
| Letter case | `An`, `AN`, `an` | Verify case sensitivity |
| Full names | `Nguyễn Văn An`, `Nguyen Van An` | Verify name search behavior |
| Unicode normalization | NFC and NFD forms of the same text | Verify composed/decomposed input |
| Non-BMP characters | Emojis in display names/content | Confirm end-to-end `utf8mb4` |
| Whitespace | space, non-breaking space, trailing spaces | Verify trimming and comparison rules |

Test at least these operations:

- `=` and `<>`.
- `LIKE 'prefix%'` and `LIKE '%contains%'`.
- `ORDER BY` and `GROUP BY`.
- `DISTINCT`.
- Unique indexes and composite unique keys.
- JOINs between string columns with different collations.
- Inserts/reads through both the MySQL client and the Java application.
- Migrations from legacy character sets/collations.

Do not check only how data looks on screen. Inspect raw bytes, comparison results, and execution plans inside the database.

## 15. Integrated Practice Scenario

An online store holds 5 million customer profiles. Users want to search names without typing accents, yet the system must accurately store legal names and must never automatically merge distinct profiles. Emails are considered case-insensitive by product policy. Name lists need to be sorted according to an agreed Vietnamese ordering rule.

Execute in the lab environment:

1. Create the database and tables with `utf8mb4`; do not use the legacy `utf8`/`utf8mb3` alias in new schemas.
2. Create display name and legal name columns with collations matching search and comparison requirements.
3. Choose the email collation and verify unique semantics using values differing only by case.
4. Inspect `SHOW COLLATION` to find a suitable option for Vietnamese sorting; record the sort order of `a`, `ă`, `â`, `d`, `đ`, `e`, `ê`, `o`, `ô`, `ơ`, `u`, `ư`.
5. Insert pairs `Nguyễn`/`Nguyen`, `ma`/`má`, `d`/`đ`, NFC/NFD forms, and emojis.
6. Run comparisons and searches using `=`, `LIKE`, `ORDER BY`, and `GROUP BY`.
7. Create an index for prefix search and use `EXPLAIN` to confirm the access path.
8. Test `LIKE '%term%'` to observe B-tree limitations; evaluate FULLTEXT or a search service if needed.
9. Check for collisions before creating unique indexes under the chosen collation.
10. Run the Java/Connector/J application, verifying session charsets and data round-trips.
11. Create a copy of a schema using a legacy charset, convert it to `utf8mb4`, and compare data before and after.
12. Document the character set/collation policy for each column category and add regression tests for CI.

**Self-assessment questions:**

- How does a character set differ from a collation?
- Why should new schemas use `utf8mb4` instead of the legacy `utf8` alias?
- What rules do `ai_ci`, `as_ci`, and `as_cs` represent?
- Why should `d` and `đ` be tested explicitly rather than assumed from the `ai` suffix?
- How does collation affect unique indexes?
- Why can't `LIKE '%term%'` leverage a B-tree index the way prefix search does?
- How do NFC and NFD differ in Unicode representation, and what problem does NFC not solve?
- Why must Connector/J session charsets be verified?
- Why can changing a collation cause a unique index migration to fail?
- How do you distinguish proper charset conversion from mojibake data repair?

## Conclusion

Storing Vietnamese safely starts with `utf8mb4`, while accurate searching and sorting depend on collation. Choose `ai`/`as` and `ci`/`cs` according to business rules, verify Vietnamese behavior on the target MySQL version, and evaluate impacts on unique indexes and execution plans. Normalize Unicode consistently, verify Connector/J encoding, and dry-run schema conversions on a replica before rolling out to large datasets.
