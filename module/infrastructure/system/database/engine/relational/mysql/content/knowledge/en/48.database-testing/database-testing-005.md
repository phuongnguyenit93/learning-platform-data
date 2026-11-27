# Testing

## Testing NULL, Empty Strings, Unicode, Emoji, and Collations

Text data bugs often do not surface in a simple `SELECT` query. A column may receive `NULL`, an empty string, spaces, or a multi-code-point Unicode string; two values that look identical on screen may compare equal in MySQL under a collation while differing in bytes. Emoji can be rejected or turned into replacement characters if a connection layer only supports three-byte UTF-8. A unique index can also reject two names differing in case or accents if the collation ignores those differences.

In the **DATABASE_MYSQL** module, you learn to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control. You also practice reading execution plans, query tuning, privilege management, backups, and handling relational database operational issues. Testing text data is part of these skills: designing schemas properly, understanding comparison rules, protecting unique constraints, and verifying data travels end-to-end from the application to MySQL without corruption.

This lesson builds a test suite for `NULL`, empty strings, whitespace, accented Vietnamese text, combining Unicode characters, emoji, and collations. Examples target MySQL 8.0/8.4 with InnoDB and `utf8mb4`; specific collations can vary by version, so verify supported collation names on the target server.

### 1. Distinguishing NULL, Empty Strings, and Whitespace

The following three cases are not the same:

- `NULL`: no value or unknown value according to the data model.
- `''`: a string of length zero.
- `'   '`: a string containing one or more space characters; it is still a value.

Tabs, newlines, non-breaking spaces (NBSP), and zero-width spaces are also real characters. They may look like blank space, yet they are not equivalent to an empty string.

#### 1.1. SQL NULL Requires Dedicated Comparisons

Never use `= NULL` or `<> NULL`. Regular comparisons with `NULL` evaluate to `UNKNOWN`, not `TRUE`/`FALSE`. Use `IS NULL` and `IS NOT NULL`:

~~~sql
SELECT
  customer_id,
  display_name,
  display_name IS NULL AS is_missing,
  display_name = '' AS is_empty
FROM appdb.customers;

SELECT COUNT(*) AS missing_count
FROM appdb.customers
WHERE display_name IS NULL;

SELECT COUNT(*) AS empty_count
FROM appdb.customers
WHERE display_name = '';
~~~

If reports must group `NULL` and empty strings together, write an explicit rule:

~~~sql
SELECT
  CASE
    WHEN display_name IS NULL THEN 'MISSING'
    WHEN display_name = '' THEN 'EMPTY'
    ELSE 'PRESENT'
  END AS value_state,
  COUNT(*) AS row_count
FROM appdb.customers
GROUP BY value_state;
~~~

Do not blindly use `COALESCE(display_name, '')` everywhere just to simplify queries. Doing so can erase the semantic distinction between "unknown" and "known to be empty," affecting validation, reporting, and business logic.

#### 1.2. Checking Whitespace-Only Strings

`TRIM()` by default removes ASCII space characters from both ends, not every character a user perceives as whitespace:

~~~sql
SELECT
  display_name,
  display_name = '' AS equals_empty,
  TRIM(display_name) = '' AS blank_after_trim,
  CHAR_LENGTH(display_name) AS char_count,
  LENGTH(display_name) AS byte_count,
  HEX(display_name) AS raw_hex
FROM appdb.customers;
~~~

With Unicode data, `TRIM()` does not automatically strip every NBSP, tab, newline, or zero-width character. If the domain requires whitespace normalization, define the exact allowed set of characters to strip at the application layer or use an SQL expression tested against that character set. Never silently delete all invisible characters because they can carry meaning in certain identifiers or languages.

#### 1.3. CHAR and VARCHAR

`CHAR(n)` is a fixed-length type with space-padding rules; how trailing spaces are stored and returned also depends on data type, SQL mode, and version. `VARCHAR(n)` stores variable-length strings. For user names, emails, external codes, and arbitrary text, `VARCHAR` is usually a better fit than `CHAR`, though the final choice must depend on the data domain.

Do not test empty strings only on a `CHAR` column. Test against the actual production column type, because padding and trailing-space comparison rules can alter results.

### 2. Creating Purposeful Test Fixtures

Create a lab table with `utf8mb4` and a text column with an explicitly specified collation:

~~~sql
CREATE DATABASE IF NOT EXISTS text_test
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE text_test.text_cases (
  case_id BIGINT NOT NULL PRIMARY KEY,
  label VARCHAR(80) CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci NULL,
  notes VARCHAR(255) CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci NULL
) ENGINE=InnoDB;
~~~

The collation `utf8mb4_0900_ai_ci` is an example for MySQL 8.0 and later. If your version or environment does not support it, pick a collation listed by the server and record that choice in the test output.

Insert representative cases:

~~~sql
INSERT INTO text_test.text_cases (case_id, label, notes) VALUES
  (1, NULL, 'SQL NULL'),
  (2, '', 'empty string'),
  (3, '   ', 'three ASCII spaces'),
  (4, 'A', 'uppercase A'),
  (5, 'a', 'lowercase a'),
  (6, 'cafe', 'without accent'),
  (7, 'café', 'with accent'),
  (8, 'Tieng Viet', 'ASCII approximation'),
  (9, 'Tiếng Việt có dấu', 'Vietnamese text'),
  (10, '😊', 'supplementary-plane emoji'),
  (11, '👨‍👩‍👧‍👦', 'emoji sequence with joiners'),
  (12, 'é', 'e plus combining acute accent'),
  (13, 'é', 'precomposed e acute');
~~~

The two values in cases 12 and 13 may look identical, yet their Unicode encodings differ: one string uses `e` plus a combining acute accent; the other uses the precomposed `é` character. They are useful for testing normalization and collation behavior.

For fixtures containing emoji or non-BMP characters, make sure the SQL file, terminal, and client sending the queries also use UTF-8. If characters are replaced before reaching MySQL, database checks cannot recover the original data.

### 3. utf8mb4 and the Character Path

MySQL's `utf8mb4` charset supports up to four bytes per Unicode code point. The `utf8` charset in MySQL is a historical alias for `utf8mb3`, supporting at most three bytes and unable to store many non-BMP characters, including most modern emoji.

For new data, choose `utf8mb4` for databases/tables/columns and verify the client connection too. Changing only the column's charset without checking `character_set_client`, `character_set_connection`, and `character_set_results` can still leave bugs in the transport layer.

Inspect charsets and collations:

~~~sql
SHOW VARIABLES LIKE 'character_set%';
SHOW VARIABLES LIKE 'collation%';

SELECT
  @@character_set_client,
  @@character_set_connection,
  @@character_set_results,
  @@character_set_server,
  @@character_set_database,
  @@collation_connection,
  @@collation_server,
  @@collation_database;
~~~

Inspect database, table, and column definitions:

~~~sql
SHOW CREATE DATABASE text_test;
SHOW CREATE TABLE text_test.text_cases;

SELECT
  COLUMN_NAME,
  CHARACTER_SET_NAME,
  COLLATION_NAME,
  COLUMN_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'text_test'
  AND TABLE_NAME = 'text_cases';
~~~

A `utf8mb4` column is not enough if the client sends bytes in a different charset. When using a command-line client, connect with an explicit charset or configure the session properly. In applications, verify the driver negotiated the right charset instead of relying solely on defaults.

#### 3.1. Round-Trip Test

A round-trip test verifies characters travel from client to server, are stored, read back, and returned to the client unchanged:

~~~sql
SELECT
  case_id,
  label,
  HEX(label) AS stored_bytes,
  CHAR_LENGTH(label) AS character_count,
  LENGTH(label) AS byte_count
FROM text_test.text_cases
ORDER BY case_id;
~~~

`CHAR_LENGTH()` counts characters according to MySQL string semantics; `LENGTH()` returns the byte count. With UTF-8, those two numbers often differ. For instance, an emoji can be one code point while occupying four bytes. A string with combining marks can contain multiple code points even though a user sees a single character.

To inspect every code point in the data, `HEX()` lets you examine UTF-8 bytes. Compare results between source, target, and the value sent by the application. If bytes differ, determine whether the alteration happened in the serializer, driver, connection charset, or schema conversion.

### 4. Code Points, Graphemes, and Emoji

The notion of "one character" can refer to three distinct things:

- **Byte:** storage unit; UTF-8 uses one to four bytes per code point.
- **Unicode code point:** a Unicode scalar value. `CHAR_LENGTH()` corresponds closely to the number of code points in the string, not bytes.
- **Grapheme cluster:** the unit perceived by a user as a single visible character. One grapheme can consist of multiple code points.

For example, the family emoji `👨‍👩‍👧‍👦` is formed from multiple emoji joined by zero-width joiners (ZWJ). It may render as a single glyph while containing multiple code points and many bytes. Do not use `CHAR_LENGTH()` to count visible UI characters.

Emoji test data should include:

- A simple emoji like `😊`.
- An emoji with a skin-tone modifier like `👍🏽`.
- A country flag formed from regional indicators.
- A ZWJ sequence like `👨‍👩‍👧‍👦`.
- Non-emoji non-BMP characters.
- Vietnamese accented sequences or combining-mark sequences.

Inspect bytes and lengths:

~~~sql
SELECT
  label,
  CHAR_LENGTH(label) AS code_point_count,
  OCTET_LENGTH(label) AS utf8_byte_count,
  HEX(label) AS utf8_hex
FROM text_test.text_cases
WHERE case_id IN (9, 10, 11, 12, 13);
~~~

`OCTET_LENGTH()` is equivalent to `LENGTH()` for byte length. The result for a ZWJ sequence depends on the actual number of code points; measure real data rather than hard-coding an assumption that a visible emoji equals one code point.

### 5. Unicode Normalization

Unicode allows some visually identical characters to be represented by different sequences of code points. For instance, an accented character can be represented in precomposed form or as a base letter plus a combining mark.

MySQL should not be treated as a layer that automatically normalizes all input strings to NFC/NFD. UCA collation comparisons may treat certain canonically equivalent forms as equal according to collation rules, but that does not mean stored bytes are normalized identically.

Therefore, clarify the requirement:

1. **Byte preservation:** two strings with different bytes are still considered distinct.
2. **Linguistic text comparison:** certain Unicode/case/accent variants are treated as equivalent.
3. **Canonical storage:** the application normalizes input to one form, such as NFC, before storing.

If the system needs canonical storage, normalize at the application layer using your chosen Unicode library, then test round-trips and legacy data migrations. Do not replace characters using a small manual mapping table because Unicode spans many combinations and languages.

Compare both forms in MySQL:

~~~sql
SELECT
  HEX('é') AS decomposed_hex,
  HEX('é') AS precomposed_hex,
  'é' = 'é' COLLATE utf8mb4_0900_ai_ci
    AS equal_under_ai_ci,
  BINARY 'é' = BINARY 'é'
    AS equal_as_bytes;
~~~

Comparison results depend on the specific collation. The `BINARY` comparison reveals the byte difference between the two strings in the example. Run this query as a test on the exact server version and record the system's expected behavior.

### 6. Collations Govern Comparison and Sorting

Charset defines character encoding; collation defines how strings are compared and sorted. Two columns both using `utf8mb4` with different collations can produce different results for `=`, `ORDER BY`, `GROUP BY`, `DISTINCT`, `LIKE`, and unique indexes.

Common suffixes in collation names:

| Suffix | General meaning |
|---|---|
| `_ai` | Accent-insensitive: ignores accent differences under collation rules |
| `_as` | Accent-sensitive: distinguishes accents |
| `_ci` | Case-insensitive: ignores uppercase/lowercase differences |
| `_cs` | Case-sensitive: distinguishes uppercase/lowercase |
| `_bin` | Binary collation comparing character/byte values of the charset |
| `_0900` | UCA 9.0 collation family in MySQL 8.0 and later |

Not every suffix combination exists on every version. Inspect the actual collation list:

~~~sql
SHOW COLLATION LIKE 'utf8mb4%';

SELECT
  COLLATION_NAME,
  CHARACTER_SET_NAME,
  IS_DEFAULT,
  PAD_ATTRIBUTE
FROM INFORMATION_SCHEMA.COLLATIONS
WHERE CHARACTER_SET_NAME = 'utf8mb4'
ORDER BY COLLATION_NAME;
~~~

`PAD_ATTRIBUTE` helps identify trailing-space handling rules (`PAD SPACE` or `NO PAD`) in versions that include this column. Do not infer padding solely from the collation name; check metadata and run tests.

#### 6.1. Testing Case and Accent Sensitivity

Force collations directly in a query to compare:

~~~sql
SELECT
  'A' COLLATE utf8mb4_0900_ai_ci =
    'a' COLLATE utf8mb4_0900_ai_ci AS case_equal_ai_ci,
  'cafe' COLLATE utf8mb4_0900_ai_ci =
    'café' COLLATE utf8mb4_0900_ai_ci AS accent_equal_ai_ci,
  'A' COLLATE utf8mb4_0900_as_cs =
    'a' COLLATE utf8mb4_0900_as_cs AS case_equal_as_cs,
  'cafe' COLLATE utf8mb4_0900_as_cs =
    'café' COLLATE utf8mb4_0900_as_cs AS accent_equal_as_cs;
~~~

Under `_ai_ci` collations, case and accents are typically ignored based on collation weights. Under `_as_cs`, both accents and case are distinguished. Verify on the exact collation and real data.

#### 6.2. Testing Trailing Spaces

Two strings differing only by trailing spaces may compare equal under a `PAD SPACE` collation, whereas `NO PAD` distinguishes them. This matters for emails, usernames, identifiers, and unique indexes:

~~~sql
SELECT
  'abc' COLLATE utf8mb4_general_ci =
    'abc ' COLLATE utf8mb4_general_ci AS equal_under_pad_space,
  'abc' COLLATE utf8mb4_0900_ai_ci =
    'abc ' COLLATE utf8mb4_0900_ai_ci AS equal_with_trailing_space,
  HEX('abc') AS first_hex,
  HEX('abc ') AS second_hex;
~~~

In common releases, `utf8mb4_general_ci` is an example of a `PAD SPACE` collation while `utf8mb4_0900_ai_ci` is `NO PAD`; verify `PAD_ATTRIBUTE` on your server before using the result as a criterion. Run tests with the collation used in production. For `CHAR` columns, the data type's own padding rules must also be accounted for; use `VARCHAR` in tests when isolating collation behavior.

#### 6.3. LIKE, ORDER BY, and GROUP BY

It is not just `=` that is affected. Test the operations the application actually uses:

~~~sql
SELECT label, COUNT(*)
FROM text_test.text_cases
GROUP BY label
ORDER BY label;

SELECT DISTINCT label
FROM text_test.text_cases
ORDER BY label;

SELECT case_id, label
FROM text_test.text_cases
WHERE label LIKE 'cafe%';
~~~

If business logic requires accent- or case-sensitive search, use an appropriate collation or design a dedicated column/search key. Do not arbitrarily override collation per query because it can prevent optimal index usage; inspect `EXPLAIN` after adding `COLLATE` to a predicate.

### 7. Collations and Unique Indexes

A unique index checks uniqueness using the comparison rules of the string column's collation. If the collation is case- or accent-insensitive, strings with different bytes can still collide.

Example:

~~~sql
CREATE TABLE text_test.user_names (
  user_id BIGINT NOT NULL PRIMARY KEY,
  username VARCHAR(100)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci NOT NULL,
  UNIQUE KEY uq_user_names_username (username)
) ENGINE=InnoDB;

INSERT INTO text_test.user_names VALUES (1, 'Cafe');
-- The next value can violate the unique key under this collation:
INSERT INTO text_test.user_names VALUES (2, 'café');
~~~

In an accent-insensitive and case-insensitive collation, `Cafe` and `café` can be treated as the same value. Do not assume a unique index enforces byte-level uniqueness if the collation does not.

Before changing the collation of a column with a unique index:

1. Check for duplicates under the target collation.
2. Define business rules for case, accents, whitespace, and Unicode normalization.
3. Clean or resolve conflicting values.
4. Test creating the unique index on a copy of the data.
5. Evaluate locking, DDL duration, and replication impact.
6. Deploy only after conflict-resolution rules are approved.

Run duplicate-detection queries on source or staging data before creating the unique index. Example staging table without a unique constraint yet:

~~~sql
CREATE TABLE text_test.user_names_staging (
  user_id BIGINT NOT NULL PRIMARY KEY,
  username VARCHAR(100)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci NOT NULL
) ENGINE=InnoDB;

INSERT INTO text_test.user_names_staging VALUES
  (1, 'Cafe'),
  (2, 'café'),
  (3, 'CAFE');
~~~

Query to detect duplicate groups under the target collation:

~~~sql
SELECT
  username COLLATE utf8mb4_0900_ai_ci AS comparison_key,
  COUNT(*) AS duplicate_count,
  GROUP_CONCAT(user_id ORDER BY user_id) AS user_ids
FROM text_test.user_names_staging
GROUP BY username COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
~~~

`GROUP_CONCAT()` has a length limit; for large datasets, fetch keys per group with a separate query instead of relying solely on the concatenated string.

A unique index on a nullable column in MySQL allows multiple `NULL` rows because `NULL` values are not considered equal during uniqueness checks. If business rules allow only one "unknown" value, use a different model or constraint; do not assume a unique index restricts `NULL` to a single row.

### 8. Minimum Test Case Matrix

A text-data test suite should include these groups:

| Group | Sample data | What to verify |
|---|---|---|
| Missing | `NULL` | `IS NULL`, counts, defaults, and constraints |
| Empty | `''` | Zero length, not converted to `NULL` |
| ASCII whitespace | space, tab, CR/LF | Trim and validation rules |
| Unicode whitespace | NBSP, zero-width space | Not mishandled as ASCII space |
| Case | `A`, `a` | Equality, `LIKE`, `GROUP BY`, and uniqueness |
| Accent | `cafe`, `café` | Accent sensitivity |
| Vietnamese | `Tiếng Việt`, `Đặng`, `ắ`, `ộ` | Round-trip and collation |
| Normalization | Visually equivalent NFC/NFD | Bytes, comparison, and normalization |
| Emoji | `😊`, `👍🏽`, flags, ZWJ family | `utf8mb4`, byte count, and round-trip |
| Boundary | empty string, max-length string, trailing characters | Column length and index limits |
| Duplicate | different bytes yet equivalent under collation | Unique constraints |
| Invalid encoding | invalid byte sequence | Errors, warnings, or rejection per driver/SQL mode |

For each case, record:

- Original input at the application layer.
- Expected bytes/Unicode code points when verifying encoding.
- Charset/collation of column and connection.
- Value stored in the database via `HEX()`.
- Value read back in the application.
- Results for equality, `LIKE`, `ORDER BY`, `GROUP BY`, and unique constraints.
- Expected and actual outcomes on each supported MySQL version.

### 9. Testing from Java with Connector/J

Testing SQL directly with a command-line client is insufficient if the application uses Connector/J. Verify both values passed via JDBC and values read back.

JUnit-style test example using `PreparedStatement`:

~~~java
String value = "Tiếng Việt 😊 👨‍👩‍👧‍👦";

try (Connection conn = dataSource.getConnection()) {
    try (PreparedStatement ps = conn.prepareStatement(
            "INSERT INTO text_test.text_cases(case_id, label, notes) VALUES (?, ?, ?)")) {
        ps.setLong(1, 100L);
        ps.setString(2, value);
        ps.setString(3, "round-trip");
        assertEquals(1, ps.executeUpdate());
    }

    try (PreparedStatement ps = conn.prepareStatement(
            "SELECT label FROM text_test.text_cases WHERE case_id = ?")) {
        ps.setLong(1, 100L);
        try (ResultSet rs = ps.executeQuery()) {
            assertTrue(rs.next());
            assertEquals(value, rs.getString("label"));
            assertFalse(rs.next());
        }
    }
}
~~~

Run tests through the exact Connector/J version, JDK, and connection pool used in production. Also inspect session charset:

~~~java
try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(
         "SELECT @@character_set_client, " +
         "@@character_set_connection, " +
         "@@character_set_results, @@collation_connection");
     ResultSet rs = ps.executeQuery()) {
    assertTrue(rs.next());
    // Assert against the charset/collation designed for the application.
}
~~~

Do not hard-code session expectations if the pool or connection configuration might set different values. What matters is that actual values match the agreed-upon configuration.

In Connector/J, use the charset/collation properties supported by the documentation for that exact version. After connecting, read `character_set_client`, `character_set_connection`, `character_set_results`, and `collation_connection` to verify. Avoid issuing ad-hoc `SET NAMES` on every request because session changes can leak across a connection pool if not reset.

### 10. SQL Mode, Warnings, and Invalid Data

SQL mode governs how MySQL handles out-of-range data, type conversions, and errors. In strict mode, certain invalid values are rejected rather than silently converted. Record the mode used in tests:

~~~sql
SELECT @@SESSION.sql_mode, @@GLOBAL.sql_mode;
-- Execute the INSERT/UPDATE under test immediately before the next statement.
SHOW WARNINGS;
~~~

Do not check exceptions alone. After an `INSERT`/`UPDATE`, read `SHOW WARNINGS` immediately in the same session to detect truncation or conversion warnings. Warnings can be cleared by the next statement.

Test strings exceeding column length, characters unrepresentable in the target charset, and invalid byte sequences. Expect explicit rejection or an approved conversion behavior; never accept silent truncation or replacement with `?`/replacement characters without warnings.

### 11. Checking Schemas and Collation Migrations

When migrating a column from a legacy charset/collation to `utf8mb4` or a new collation, the migration can affect:

- Stored bytes and transcoding.
- Comparison and sort results.
- `DISTINCT`/`GROUP BY` groupings.
- Uniqueness in unique indexes.
- Whether queries can use indexes.
- Index size due to increased maximum bytes per character.

Before running `ALTER`:

~~~sql
SHOW CREATE TABLE appdb.customers;

SELECT
  COUNT(*) AS total_rows,
  SUM(display_name IS NULL) AS null_rows,
  SUM(display_name = '') AS empty_rows,
  MAX(CHAR_LENGTH(display_name)) AS max_char_length,
  MAX(OCTET_LENGTH(display_name)) AS max_byte_length
FROM appdb.customers;
~~~

Check for duplicates under the target collation before building a unique index. Check index sizes and key-length limits based on row format, page size, and version. Use a staging clone to rehearse the `ALTER` and measure duration and replication lag.

Never run `ALTER TABLE ... CONVERT TO CHARACTER SET` without a backup and checking that the data can convert cleanly. When existing byte sequences already had the wrong charset, converting charsets can corrupt the data further. Identify the true source charset before converting.

### 12. Layered Test Matrix

| Layer | What to test | Evidence |
|---|---|---|
| Input/UI | User enters `NULL`, empty, whitespace, Vietnamese, emoji | Pre-serialization value |
| Application | Validation, normalization, Java `String` handling | Unit tests and safe logs |
| JDBC/Driver | Negotiated charset, `setString`/`getString`, reconnect | Connector/J integration test |
| MySQL session | `character_set_*`, `collation_connection`, `sql_mode` | Session metadata query |
| Schema | Column charset/collation, type, length, indexes | `SHOW CREATE TABLE`, `INFORMATION_SCHEMA` |
| SQL semantics | `NULL`, equality, `LIKE`, `GROUP BY`, `ORDER BY` | Query outputs per test case |
| Constraints | Unique keys and nullable columns | Controlled `INSERT` tests |
| Persistence | Stored bytes and read-back values | `HEX()`, `CHAR_LENGTH()`, `LENGTH()` |
| Upgrade/migration | Charset/collation migration on real data | Restore rehearsal, duplicate report, post-migration tests |

Separate unit tests from integration tests. Unit tests verify application validation and normalization; integration tests verify real MySQL and Connector/J behavior. A mocked JDBC test cannot prove whether server collations distinguish or fold two strings as required.

### 13. Troubleshooting

| Symptom | Possible cause | How to investigate |
|---|---|---|
| Emoji stored as `?` or rejected | Column or connection uses `utf8mb3`/other charset | Inspect column and session charsets; compare input against `HEX()` |
| Vietnamese diacritics corrupted | Bytes interpreted under wrong charset or file/client encoding mismatch | Check charset at every hop and run round-trip tests |
| `NULL` not filtered properly | Used `= NULL` instead of `IS NULL` | Fix predicate and test `UNKNOWN` semantics |
| Empty string treated as missing | Application or SQL conflates `''` with `NULL` | Clarify data contract and use separate conditions |
| Two distinct usernames collide on unique index | Collation ignores case/accents or trailing spaces | Inspect collation, `PAD_ATTRIBUTE`, and duplicate groups under target collation |
| Visually identical strings have different hashes | NFC/NFD or byte encoding differs | Compare `HEX()`, code points, and normalization rules |
| `LIKE` returns unexpected rows | Collation and wildcard semantics | Check collation, escape `%`/`_`, and run boundary cases |
| Duplicates appear after migration | Target collation folds previously distinct values | Analyze duplicates before `ALTER` and resolve per business rules |
| Results differ between CLI and Java | Driver/session charset or collation differs | Query session variables from the application's actual connection |
| Data truncated without `INSERT` failing | Non-strict SQL mode or ignored warnings | Check SQL mode and `SHOW WARNINGS` immediately after the statement |

### 14. Practice Exercise

An account-management application stores usernames in a `VARCHAR(100)` column. The legacy system used a case-insensitive, accent-insensitive collation. After migrating to `utf8mb4_0900_ai_ci`, a migration creating a unique index fails because the values `Cafe`, `café`, and `CAFE` exist. Several users also report that emoji in display names are saved as question marks.

1. Write a query distinguishing `NULL`, empty strings, and strings containing only ASCII spaces.
2. Use `CHAR_LENGTH`, `OCTET_LENGTH`, and `HEX` to inspect Vietnamese text and emoji.
3. How do you verify when a column's charset differs from the connection's charset?
4. Write a query to find duplicate usernames under the target collation.
5. Why can those three usernames violate the unique index?
6. Design an NFC/NFD test and explain why identical bytes are not the only condition for collation equality.
7. Write a Connector/J integration test that writes and reads back strings containing Vietnamese text and emoji.
8. Before changing a production collation, which duplicate groups must be reported and resolved?

### 15. Acceptance Checklist

- [ ] Distinguished `NULL`, `''`, whitespace, and default values in the data contract.
- [ ] Tested `IS NULL`/`IS NOT NULL`; did not use `= NULL`.
- [ ] Tested `CHAR`/`VARCHAR`, trailing spaces, and padding rules.
- [ ] Database, table, column, and connection use the defined charset and collation.
- [ ] Emoji and non-BMP characters round-trip cleanly through the actual Connector/J driver.
- [ ] `HEX`, `CHAR_LENGTH`, and `OCTET_LENGTH` match expected data.
- [ ] Test cases cover Vietnamese text, combining marks, NFC/NFD, emoji modifiers, and ZWJ.
- [ ] Verified case/accent sensitivity, `LIKE`, `ORDER BY`, `GROUP BY`, and `DISTINCT`.
- [ ] Verified `PAD_ATTRIBUTE` or trailing-space behavior of the collation.
- [ ] Detected duplicates under the target collation before creating unique indexes.
- [ ] Verified multiple `NULL`s in unique indexes per business rules.
- [ ] SQL mode and warnings are captured; no unintended truncation or conversion occurs.
- [ ] Charset/collation migration rehearsed on a data copy with a backup.
- [ ] Both unit tests and integration tests exercise the real application layers.

### 16. Operational Principles

Never assume every blank string is empty or every visually similar string is the same value. Distinguish `NULL`, empty, and whitespace with dedicated conditions; use `utf8mb4` for modern Unicode data and verify charsets on both columns and connections. Inspect bytes with `HEX()`, lengths with `CHAR_LENGTH()` and `OCTET_LENGTH()`, and test equality, `LIKE`, grouping, and unique indexes under the real collation. Before changing a collation, identify duplicates under the target rules and resolve them according to business requirements. A trustworthy test suite must run through the exact application, Connector/J, connection pool, and MySQL version slated for deployment.
