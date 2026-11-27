# utf8mb4, Historical utf8 Names, and Emoji Storage

When a MySQL application stores usernames, message content, or product descriptions in multiple languages, the character set determines which characters can be represented and how they are encoded into bytes. The collation determines how strings belonging to that character set are compared and sorted. Choosing the right character set at both the schema and connection levels is essential so that Vietnamese text, non-Latin script characters, and emojis are stored, read, and searched accurately.

In MySQL, `utf8mb4` is the right choice for modern Unicode data because it supports up to four bytes per code point. By contrast, the historical `utf8` name in MySQL is an alias for `utf8mb3`, an encoding that supports at most three bytes. Therefore, a column declared with `CHARACTER SET utf8` can store Vietnamese with diacritics and many common characters, but cannot store emoji code points outside the BMP, such as `😀` (U+1F600).

This lesson explains that difference, how to inspect charset/collation at each level, how to test storing emojis, and what to review when migrating an older schema to `utf8mb4`.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish a character set from a collation and understand the role of each.
- Explain that `utf8` in MySQL is a historical name for `utf8mb3`, not the full name for 4-byte UTF-8.
- Choose `utf8mb4` to store extended Unicode and emojis.
- Inspect charset/collation at the server, database, table, column, and connection levels.
- Use `CHAR_LENGTH()`, `LENGTH()`, and `HEX()` to inspect string contents.
- Diagnose errors when storing emojis, characters replaced with `?`, and mojibake.
- Plan a migration of legacy data to `utf8mb4` without corrupting content or altering comparison rules unexpectedly.

## 1. How do character sets and collations differ?

A **character set** is a collection of characters and the rules for encoding each character into bytes. For example, `utf8mb4` represents Unicode using one to four bytes per code point. A **collation** is a set of rules used to compare and sort strings within a character set, including how uppercase/lowercase letters, accents, and linguistic ordering are handled.

For example:

| Component | Example | Role |
|---|---|---|
| Character set | `utf8mb4` | Defines which characters can be represented and how they are encoded |
| Collation | `utf8mb4_unicode_ci` | Defines how strings are compared/sorted |
| Collation suffix `_ci` | case-insensitive | Does not distinguish uppercase and lowercase letters in comparisons |
| Collation suffix `_ai` | accent-insensitive | Does not distinguish accents in comparisons according to that collation's rules |

A character set can have many collations. Choosing `utf8mb4` alone does not decide whether strings are case-sensitive or accent-sensitive; you also need to choose a collation that matches your search, uniqueness, and sorting requirements.

For example, with a case-insensitive collation, the two strings `An` and `AN` can be treated as equal in comparisons and `UNIQUE` constraints. If business logic requires distinguishing them, you must choose the appropriate collation rather than only changing how queries are written.

## 2. `utf8`, `utf8mb3`, and `utf8mb4` in MySQL

In MySQL, the name `utf8` is a historical alias for `utf8mb3`. `utf8mb3` uses at most three bytes per Unicode code point. `utf8mb4` extends the encoding up to four bytes, allowing it to represent code points outside the Basic Multilingual Plane (BMP).

| Name in MySQL | Max bytes per code point | Representation capability |
|---|---:|---|
| `utf8` (historical alias of `utf8mb3`) | 3 | Unicode within the range supported by 3-byte UTF-8; cannot represent non-BMP code points |
| `utf8mb3` | 3 | Same as the historical `utf8` name |
| `utf8mb4` | 4 | Full Unicode, including non-BMP code points and many modern emojis |

The name `utf8` in MySQL is misleading because standard UTF-8 can use up to four bytes. In MySQL, when you want to store full Unicode, explicitly declare `utf8mb4` instead of relying on the name `utf8`.

MySQL has marked `utf8mb3` and its `utf8` alias as legacy/deprecated in recent MySQL 8.0 releases. The exact deprecation warning milestone depends on the minor release. When creating new schemas, use `utf8mb4`; when maintaining legacy systems, check your server version and corresponding documentation before planning to phase out the old name.

### 2.1. Why does Vietnamese with diacritics still work with utf8mb3?

Most common Vietnamese letters, including accented letters encoded within the BMP, can be represented by `utf8mb3`. Because of this, an application may have stored names such as `Nguyễn`, `Trường`, and `Đặng` for years without obvious errors.

However, Unicode data does not consist only of Vietnamese letters. An emoji like `😀` has code point U+1F600, which lies outside the BMP and requires four bytes in UTF-8. Various symbols, emojis, or characters from other scripts also reside outside the BMP. Once an application begins receiving these characters, the 3-byte limit of `utf8mb3` surfaces.

### 2.2. An emoji is not always a single code point

A simple emoji like `😀` is a single code point. Yet the visual glyph a user sees can be formed by combining multiple code points: emoji + variation selector, emoji + skin tone modifier, two regional indicators forming a country flag, or multiple emojis joined with a zero-width joiner (ZWJ) to form family/profession icons.

Therefore, a single displayed symbol can consist of multiple code points and many bytes. `utf8mb4` supports the necessary code points; collation, fonts, and the rendering application still affect how the string is compared or displayed.

## 3. Testing emoji storage capability

Let's practice in a sandbox database. First, check the MySQL version and the session's charset/collation:

```sql
SELECT VERSION() AS mysql_version;

SELECT
    @@character_set_server AS server_charset,
    @@collation_server AS server_collation,
    @@character_set_client AS client_charset,
    @@character_set_connection AS connection_charset,
    @@character_set_results AS results_charset,
    @@collation_connection AS connection_collation;
```

Set the current connection to use `utf8mb4`:

```sql
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;
```

`SET NAMES` sets the client, connection, and results charsets for the session, as well as the connection collation if specified. In a real application, configure the charset via the driver/connection string so every connection is initialized consistently; do not rely on manual statements in a SQL window.

Create a test table with an explicitly declared charset:

```sql
CREATE TABLE unicode_message_demo (
    message_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    message_text VARCHAR(200)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci
        NOT NULL,
    PRIMARY KEY (message_id)
) ENGINE = InnoDB;

INSERT INTO unicode_message_demo (message_text)
VALUES
    ('Xin chào Việt Nam'),
    ('Have a great day 😀'),
    ('Symbols: 🚀 🎉 🌱');

SELECT
    message_id,
    message_text,
    CHAR_LENGTH(message_text) AS character_count,
    LENGTH(message_text) AS byte_count,
    HEX(message_text) AS stored_bytes
FROM unicode_message_demo
ORDER BY message_id;
```

Rows containing emojis are stored successfully if both the column and the connection use a compatible charset. For a string containing a single `😀` emoji, `CHAR_LENGTH()` returns `1`, while `LENGTH()` returns `4` when the string is UTF-8 encoded. For sentences containing Vietnamese characters and emojis, the byte count is usually larger than the character count because code points have varying encoding lengths.

`HEX()` reveals the actual bytes of the string returned by MySQL. For the `😀` code point encoded in UTF-8, the byte sequence is `F09F9880`. This is a useful way to verify data when a terminal interface cannot render the character.

## 4. Testing the limits of utf8mb3

To see the difference, you can create a separate table using `utf8mb3` if your MySQL version still supports this name:

```sql
CREATE TABLE utf8mb3_message_demo (
    message_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    message_text VARCHAR(100)
        CHARACTER SET utf8mb3
        COLLATE utf8mb3_unicode_ci
        NOT NULL,
    PRIMARY KEY (message_id)
) ENGINE = InnoDB;
```

Try inserting a Vietnamese string:

```sql
INSERT INTO utf8mb3_message_demo (message_text)
VALUES ('Xin chào Việt Nam');
```

The Vietnamese string above can be stored. Next, try inserting a non-BMP code point:

```sql
INSERT INTO utf8mb3_message_demo (message_text)
VALUES ('Non-BMP character: 😀');
```

Under a connection sending valid UTF-8, the second statement will fail because `utf8mb3` cannot represent code point U+1F600. The error message typically indicates an incorrect string value for the column's character set. If SQL mode or the client performs different conversion behavior, inspect errors and warnings; never accept characters silently turning into `?` or being dropped.

If your version has removed or does not provide the `utf8mb3_unicode_ci` collation, skip creating this test table and use version/documentation details to confirm the limitation. Do not change `utf8mb3` to `utf8` expecting 4-byte storage capability: in MySQL, `utf8` is an alias for this 3-byte encoding.

## 5. Character set and collation configuration levels

MySQL allows setting defaults at multiple levels. Higher-level configuration generally supplies default values for objects created afterward; lower-level declarations can override them.

| Level | How to check | Primary effect |
|---|---|---|
| Server | `@@character_set_server`, `@@collation_server` | Default values when creating a new database if unspecified |
| Database | `information_schema.schemata` | Default values for new tables in the database |
| Table | `SHOW CREATE TABLE`, `information_schema.tables` | Default values for new character columns in the table |
| Column | `SHOW FULL COLUMNS`, `information_schema.columns` | Actual charset/collation of each character column |
| Connection | `@@character_set_client`, `@@character_set_connection`, `@@character_set_results` | How MySQL receives, converts, and returns data to the client |

### 5.1. Checking at the server level

```sql
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
```

Or use `SELECT @@GLOBAL.character_set_server, @@GLOBAL.collation_server;`. Global variables indicate server-level defaults; changing them does not automatically convert existing data.

### 5.2. Checking at the database level

```sql
SELECT
    SCHEMA_NAME,
    DEFAULT_CHARACTER_SET_NAME,
    DEFAULT_COLLATION_NAME
FROM information_schema.schemata
WHERE SCHEMA_NAME = DATABASE();
```

Create a new database with explicit defaults:

```sql
CREATE DATABASE app_unicode
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;
```

Change the defaults of an existing database:

```sql
ALTER DATABASE app_unicode
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;
```

`ALTER DATABASE` changes the defaults for objects created afterward. This statement does not automatically convert the charset of existing tables and columns.

### 5.3. Checking at the table and column levels

```sql
SHOW CREATE TABLE unicode_message_demo;

SHOW FULL COLUMNS FROM unicode_message_demo;
```

Or query metadata:

```sql
SELECT
    TABLE_NAME,
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_SET_NAME,
    COLLATION_NAME,
    CHARACTER_MAXIMUM_LENGTH
FROM information_schema.columns
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'unicode_message_demo'
ORDER BY ORDINAL_POSITION;
```

Numeric columns and certain non-string types may have `NULL` for `CHARACTER_SET_NAME` and `COLLATION_NAME`; that is normal. A table's charset serves as the default for new columns, while each individual character column can have its own charset/collation.

### 5.4. Checking at the connection level

```sql
SHOW SESSION VARIABLES LIKE 'character_set%';
SHOW SESSION VARIABLES LIKE 'collation%';
```

Key variables:

- `character_set_client`: the charset MySQL assumes the client uses to send statements.
- `character_set_connection`: the charset MySQL uses when converting received literals and evaluating string expressions.
- `character_set_results`: the charset MySQL uses when returning results to the client.
- `collation_connection`: the default collation for comparing string literals on the connection when no other specific collation applies.

A column that is already `utf8mb4` can still fail if the application connects using a 3-byte charset. Conversely, a `utf8mb4` connection will not allow a `utf8mb3` column to store 4-byte code points. Both sides must be verified.

## 6. Choosing the right collation for utf8mb4

Collation affects comparisons, sorting, `GROUP BY`, `ORDER BY`, string concatenation, and `UNIQUE` constraints. Some common collations:

| Collation | General characteristics | Notes |
|---|---|---|
| `utf8mb4_general_ci` | Legacy collation, case-insensitive comparison | May use simpler rules; not the best choice for all languages |
| `utf8mb4_unicode_ci` | Unicode rules based on an older UCA version | Widely supported across common MySQL versions |
| `utf8mb4_0900_ai_ci` | Unicode 9.0 collation in MySQL 8.0, accent- and case-insensitive | Not available in MySQL 5.7; verify when deploying across versions |
| `utf8mb4_bin` | Compares by the binary value of the string | Useful when strict encoding/case-sensitive byte-level comparison is needed; does not replace all business rules |

Collation names have suffixes describing their properties. `_ci` is generally case-insensitive; `_cs` is case-sensitive; `_ai` is accent-insensitive; `_as` is accent-sensitive; `_bin` is binary comparison. Not every suffix combination exists for every charset and version.

Check available collations on the server:

```sql
SHOW COLLATION LIKE 'utf8mb4%';
```

Or:

```sql
SELECT COLLATION_NAME, CHARACTER_SET_NAME, IS_DEFAULT
FROM information_schema.collations
WHERE CHARACTER_SET_NAME = 'utf8mb4'
ORDER BY COLLATION_NAME;
```

For multilingual applications, choose a collation based on search and uniqueness requirements. For instance, if emails are normalized to lowercase in the application layer, a case-insensitive collation may fit; if identifiers are case-sensitive, consider another collation. Do not change a table's collation just to fix an emoji error: the ability to store characters is determined by the character set.

## 7. Character length vs. byte length

With multibyte data, `CHAR_LENGTH()` and `LENGTH()` return two different measurements:

- `CHAR_LENGTH(string)` counts the number of characters according to the string's character set.
- `LENGTH(string)` counts the number of bytes in the string.

Example with an emoji:

```sql
SET NAMES utf8mb4;

SELECT
    '😀' AS emoji,
    CHAR_LENGTH('😀') AS character_count,
    LENGTH('😀') AS byte_count,
    HEX('😀') AS utf8_hex;
```

The expected result is one character, four bytes, and the hex string `F09F9880`. If the client terminal does not support rendering emojis, `HEX()` still confirms the bytes handled by MySQL.

Note: `CHAR_LENGTH()` does not count "perceived visual characters" as a user sees them. A composite emoji built from multiple code points may render as one symbol yet be counted as multiple characters. Strings with combining marks can also contain multiple code points for a single displayed character.

With `VARCHAR(n)`, `n` is the maximum number of characters in the charset, not a fixed byte count. In `utf8mb4`, a `VARCHAR(100)` column can require up to roughly 400 bytes for content alone, excluding overhead and related row/index limits. This must be accounted for when designing row sizes, indexes, and migrations.

## 8. Why can an application still fail even when the column uses utf8mb4?

For an emoji to travel from a user's device to the database and back accurately, the entire path must be compatible:

```text
Device / browser
        |
        v
Application and request encoding
        |
        v
MySQL driver / connection charset
        |
        v
character_set_client -> character_set_connection
        |
        v
utf8mb4 column and table
        |
        v
character_set_results -> driver -> display UI
```

Common causes:

- The column is still `utf8mb3`, even though the database default was changed to `utf8mb4`.
- The driver opens a connection with a 3-byte charset or a charset that does not match the outgoing data.
- A SQL file or migration script was saved in a different encoding than the client assumes.
- The application transforms the string incorrectly before sending it to MySQL.
- The data was already replaced with `?` or corrupted into mojibake before being saved; changing the charset afterward cannot automatically recover the original content.
- The UI, font, or terminal lacks the glyph to display the emoji, even though the bytes in the database are correct.

When investigating, separate three questions: did MySQL receive the string properly, did the column store the right bytes, and did the client render it properly? Use `CHARACTER_SET_NAME`, `@@character_set_client`, `HEX(column)`, and compare outputs at each layer to pinpoint where the mismatch occurs.

## 9. Diagnosing mojibake and encoding corruption

Mojibake occurs when bytes of one encoding are interpreted as another encoding, causing the string to display incorrectly while still being stored as a valid character string. For example, a UTF-8 string misdecoded as Latin-1/Windows-1252 can appear as garbled characters.

Do not run `ALTER TABLE ... CONVERT TO CHARACTER SET utf8mb4` immediately upon seeing corrupted text. The conversion command assumes the current data is accurately encoded in the column's declared charset. If the bytes were already misinterpreted before saving, converting may preserve that corrupted string or make it worse.

Investigation procedure:

1. Check the actual charset/collation of the database, table, and column.
2. Check the connection charset at the time the data was written if logs or application configurations are available.
3. Use `HEX(column)` to inspect the stored bytes and compare them against the expected UTF-8 bytes from a trusted source.
4. Inspect the data at the application layer before sending and after reading back.
5. Back up the original data and test any repair procedure on a copy; never test conversions directly on production data.

If the bytes in the database have already become question marks (`3F`) instead of the emoji's UTF-8 bytes, the original information is usually lost and cannot be deduced solely by changing charsets. You must restore from the original data source, backups, or an upstream system. If the bytes remain intact but were misinterpreted, a controlled conversion plan may be possible once the true encoding is identified.

## 10. Converting legacy schemas to utf8mb4

Changing the database default does not automatically convert existing tables. To convert a table, MySQL provides the syntax:

```sql
ALTER TABLE ten_bang
    CONVERT TO CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;
```

This statement converts the character columns in the table to the target character set/collation. Verify the outcome using `SHOW CREATE TABLE` and `INFORMATION_SCHEMA.COLUMNS` afterward.

A safe migration plan typically includes:

1. **Inventory:** list all schemas, tables, character columns, and current collations; identify which columns are already `utf8mb4` and which remain `utf8mb3` or another charset.
2. **Data assessment:** inspect content, bytes, values at risk of encoding issues, and unique keys whose comparison behavior may change under a new collation.
3. **Structural assessment:** check column lengths, total row size, indexes, and key length limits of the current MySQL version/row format.
4. **Backup and testing:** test the conversion on a near-production copy of the data; compare row counts, `HEX()` values, query results, and constraints.
5. **Connection standardization:** configure drivers to use `utf8mb4` before deploying new columns or writing new data.
6. **Rollout:** choose a maintenance window or migration tool suited to table size and uptime requirements; monitor duration, locking, temporary space, and replication lag.
7. **Verification:** re-verify each column's charset/collation, test storing emojis, read them back from the application, and check comparison/unique queries.

For example, changing the database default for new tables and converting an existing table are two separate operations:

```sql
-- Default for new objects in the database
ALTER DATABASE app_unicode
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- Convert data and character columns of an existing table
ALTER TABLE customer_message
    CONVERT TO CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;
```

Changing a collation can alter string equality, sort order, and `UNIQUE` outcomes. For example, two strings previously considered distinct may become equal under the new collation, causing unique index creation or maintenance to fail. Check for duplicates under the target collation before converting.

Additionally, `ALTER TABLE ... CONVERT` can rebuild the table, increasing I/O, requiring temporary disk space, and causing locks depending on the version, engine, data size, and DDL algorithm. Do not run large conversion commands in production without benchmarking and preparing a recovery plan.

## 11. Checklist for verifying utf8mb4 and emojis

- Confirmed the MySQL version and did not confuse the historical `utf8` with `utf8mb4`.
- Used `utf8mb4` for databases, tables, and columns that need to store extended Unicode.
- Selected collations according to business rules for case sensitivity, accents, sorting, and uniqueness.
- Verified the actual charset/collation of each column via `SHOW CREATE TABLE` or `INFORMATION_SCHEMA.COLUMNS`.
- Configured the driver/connection to use `utf8mb4` and checked session variables.
- Tested storing and reading back a non-BMP emoji, such as `😀`.
- Compared `CHAR_LENGTH()`, `LENGTH()`, and `HEX()` to distinguish characters from bytes.
- Tested composite emoji sequences, variation selectors, and ZWJ sequences if the product needs to support them.
- Evaluated column sizes, row sizes, indexes, and key length limits during conversion.
- Inspected mojibake data by actual bytes before running a convert statement.
- Backed up data, tested the migration on a copy, and verified the collation's impact on unique keys.

`utf8mb4` enables MySQL to store full Unicode, including emojis requiring four bytes. However, for data to flow safely through an application, the charset must be consistent from client and connection down to the column, and the collation must be chosen according to business comparison rules. Understanding `utf8mb3`'s limitations, inspecting bytes with `HEX()`, and planning conversions carefully will help avoid character loss, mojibake, and unexpected changes in queries or unique indexes.
