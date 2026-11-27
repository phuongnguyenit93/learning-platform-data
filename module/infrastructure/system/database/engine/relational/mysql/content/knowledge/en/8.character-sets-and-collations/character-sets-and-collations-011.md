# Converting Character Sets/Collations and Evaluating Duplicate Data After Conversion

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries through indexes, transactions, concurrency control, execution plan reading, query tuning, privileges, backups, and operations. When changing a character set or collation, you must understand which encoding currently stores the data, how the new comparison rules behave, and whether values previously treated as distinct will become equivalent.

A conversion can affect data, indexes, unique constraints, foreign keys, and application search behavior. In particular, switching to a case-insensitive or accent-insensitive collation can introduce uniqueness conflicts. Therefore, a proper workflow must check data under the exact target character set and collation before altering the schema.

## 1. Distinguishing character set conversion from collation conversion

A character set defines how characters are encoded into bytes and which characters can be represented. A collation defines how strings are compared, sorted, and whether two strings are considered equivalent in comparisons.

| Change | What changes | Example |
|---|---|---|
| Character set | Encoding used to store characters | latin1 to utf8mb4 |
| Collation | Rules for comparing and sorting strings | utf8mb4_bin to utf8mb4_0900_ai_ci |
| Both | Encoding and comparison rules | latin1/latin1_swedish_ci to utf8mb4/utf8mb4_0900_ai_ci |

Changing a collation within the same character set generally does not require altering the meaning of stored characters, yet alters comparisons, sort order, GROUP BY results, JOINs, and UNIQUE constraints. Changing a character set requires MySQL to convert characters from the source encoding to the target encoding; if the source encoding was declared inaccurately or data was already corrupted, converting may preserve or worsen the broken text.

Do not treat changing charset/collation as a simple attribute rename. Define the exact goal: standardizing encoding, changing comparison rules, or repairing improperly encoded data.

## 2. Understanding data before converting

### 2.1. Character data consists of bytes and metadata

MySQL interprets string data based on the column's declared character set and the connection's charset. When a client sends a string, the server converts the data from the client's character set to the column's target character set. When reading data, the server converts results according to the connection charset.

Consequently, garbled displayed text can originate in several places:

- Bytes were written incorrectly into the column because the client declared the wrong charset when sending data.
- The column declares a charset that does not match the actual encoding of the stored bytes.
- Data was stored accurately, yet the client reads results using an incompatible charset.
- An export/import process used a different charset than the source or target.

Looking solely at strings displayed in a terminal or UI is insufficient to determine whether bytes in the database are wrong. Before fixing data, inspect column metadata, connection charsets, and the byte representation of known samples.

### 2.2. Checking current charset and collation

View charset/collation at the server and session levels:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'character_set_server';
SHOW GLOBAL VARIABLES LIKE 'collation_server';

SHOW SESSION VARIABLES LIKE 'character_set%';
SHOW SESSION VARIABLES LIKE 'collation%';
~~~

Connection variables to pay attention to include:

- character_set_client: charset the server uses to interpret data sent by the client.
- character_set_connection: charset used while evaluating string expressions on the connection.
- character_set_results: charset used when the server sends results back to the client.
- collation_connection: default collation for string expressions associated with the connection.

View the database's charset/collation:

~~~sql
SELECT SCHEMA_NAME,
       DEFAULT_CHARACTER_SET_NAME,
       DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = 'sales';
~~~

View attributes of string columns in a table:

~~~sql
SELECT COLUMN_NAME,
       COLUMN_TYPE,
       IS_NULLABLE,
       CHARACTER_SET_NAME,
       COLLATION_NAME,
       CHARACTER_MAXIMUM_LENGTH,
       CHARACTER_OCTET_LENGTH
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'customers'
ORDER BY ORDINAL_POSITION;
~~~

CHARACTER_MAXIMUM_LENGTH shows the limit in characters; CHARACTER_OCTET_LENGTH shows the limit in bytes. These two values help assess the impact of converting to a charset with a higher maximum byte count per character.

View the actual table definition:

~~~sql
SHOW CREATE TABLE sales.customers;
~~~

SHOW CREATE TABLE helps inspect full column types, NULL/NOT NULL, DEFAULT, indexes, foreign keys, generated columns, comments, and other attributes that must be preserved when modifying definitions.

### 2.3. Verifying the target charset is supported

Do not assume every MySQL version shares the exact same collation list:

~~~sql
SHOW CHARACTER SET LIKE 'utf8mb4';
SHOW COLLATION WHERE Charset = 'utf8mb4';
~~~

For example, utf8mb4_0900_ai_ci belongs to the MySQL 8.0 line; it is not available on MySQL 5.7. Choose a collation present in your exact version and check both production and recovery environments.

In MySQL, the name utf8 was historically used as an alias for utf8mb3. When full Unicode support is needed, including non-BMP characters such as many emojis, use utf8mb4 and verify compatibility across applications, drivers, and schemas.

## 3. Choosing the conversion goal

### 3.1. Converting to utf8mb4

utf8mb4 is the standard choice for modern Unicode data. Each character can take 1 to 4 bytes. When converting from a charset with smaller limits such as latin1 or utf8mb3 to utf8mb4, MySQL converts characters according to the declared source encoding.

Target example:

~~~sql
ALTER DATABASE sales
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

This command only changes the database's default charset/collation for objects created afterward. It does not automatically convert existing tables and columns. To convert existing data, operate at the table or column level.

### 3.2. Changing only the collation

If columns already use utf8mb4 and the goal is only to alter comparison rules, keep the character set and select the new collation. For example, converting from a binary collation to an accent- and case-insensitive collation:

~~~sql
ALTER TABLE customers
  CONVERT TO CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

The command above applies to character columns in the table and sets the target collation. Even though the charset remains the same, string comparison behavior changes. Check for duplicates beforehand if UNIQUE indexes exist on the affected columns.

### 3.3. Converting a single column

If only one column needs changing, use MODIFY COLUMN with its complete definition:

~~~sql
ALTER TABLE customers
  MODIFY COLUMN email VARCHAR(255)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci
    NOT NULL;
~~~

When using MODIFY COLUMN, redeclare all attributes to retain, such as data type, length, NULL/NOT NULL, DEFAULT, COMMENT, generated expressions, and other properties. Omitting an attribute can cause the column definition afterward to differ from the original definition. Always inspect SHOW CREATE TABLE before and after migration.

### 3.4. Changing table default without converting existing columns

The following statement changes the table's default:

~~~sql
ALTER TABLE customers
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

It adjusts the table default for character columns created afterward. It does not convert the charset/collation of existing columns. Distinguish clearly:

| Statement | Scope of effect |
|---|---|
| ALTER DATABASE ... CHARACTER SET ... | Database default |
| ALTER TABLE ... DEFAULT CHARACTER SET ... | Table default |
| ALTER TABLE ... CONVERT TO CHARACTER SET ... | Converts existing character columns in the table |
| ALTER TABLE ... MODIFY COLUMN ... CHARACTER SET ... | Converts and sets attributes for the specified column |

## 4. Converting existing data

### 4.1. CONVERT TO CHARACTER SET

To convert character columns in a table to the target charset/collation:

~~~sql
ALTER TABLE customers
  CONVERT TO CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

MySQL converts string data from the currently declared character set to the target charset and applies the target collation to character columns. Binary columns such as BINARY, VARBINARY, and BLOB are not treated as text columns in the same way.

During conversion, MySQL may adjust text data types such as TEXT to a larger TEXT type to preserve maximum character capacity when the target charset needs more bytes. Therefore, re-inspect SHOW CREATE TABLE after conversion rather than assuming column types and storage sizes remain unchanged.

### 4.2. MODIFY COLUMN for a single column

Example of a notes column needing individual conversion:

~~~sql
ALTER TABLE support_tickets
  MODIFY COLUMN note TEXT
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci
    NULL;
~~~

If the original column had DEFAULT, COMMENT, or other attributes, preserve them in the MODIFY definition. For columns with indexes, generated columns, or related constraints, check dependencies before editing.

### 4.3. Converting strings with CONVERT and CAST for testing

You can inspect post-conversion representations without altering the column:

~~~sql
SELECT
    username,
    CONVERT(username USING utf8mb4) AS username_utf8mb4,
    CHARSET(CONVERT(username USING utf8mb4)) AS target_charset,
    COLLATION(CONVERT(username USING utf8mb4)) AS expression_collation
FROM users
LIMIT 20;
~~~

CONVERT(expr USING charset) converts an expression to the specified character set. This is a tool for testing or building query expressions; it does not modify column definitions or stored data.

If you need to apply a collation to the test expression:

~~~sql
SELECT CONVERT(username USING utf8mb4)
         COLLATE utf8mb4_0900_ai_ci AS normalized_username
FROM users;
~~~

Use only collations confirmed to exist on the server. This expression is helpful when simulating comparisons under the target collation before migration.

## 5. Evaluating duplicate data under the target collation

### 5.1. Why can changing collation create conflicts?

Two strings that are distinct under the current collation can be considered equal under the target collation. For instance, collations with the ai_ci suffix are accent-insensitive and case-insensitive. Pairs such as the following can become equivalent in comparisons:

| First value | Second value | Behavior under an ai_ci collation |
|---|---|---|
| Admin | admin | Can be equal due to case-insensitivity |
| resume | résumé | Can be equal due to accent-insensitivity |
| A | a | Can be equal due to case-insensitivity |

Specific outcomes depend on the target collation and the Unicode rules it uses. Do not write custom LOWER or accent-stripping functions to guess outcomes; ask MySQL itself to compare under the exact post-migration collation.

If a column has a UNIQUE index, two previously distinct values may violate uniqueness after conversion. MySQL will refuse to create or maintain the unique index if post-conversion data is no longer unique. There is no automatic mechanism to merge two rows into one; conflicts must be resolved by business rules beforehand.

### 5.2. Listing duplicate groups under the target collation

Suppose users.username currently uses another charset or another collation. Check under the target charset/collation:

~~~sql
SELECT
    CONVERT(username USING utf8mb4)
      COLLATE utf8mb4_0900_ai_ci AS target_username,
    COUNT(*) AS duplicate_count
FROM users
WHERE username IS NOT NULL
GROUP BY target_username
HAVING COUNT(*) > 1;
~~~

This query groups values treated as equal under the target collation and lists only groups with more than one row. The username IS NOT NULL condition fits checking a single-column UNIQUE index, as MySQL permits multiple NULL values in a unique index.

If the column is already utf8mb4, you can omit CONVERT and specify the collation directly:

~~~sql
SELECT username COLLATE utf8mb4_0900_ai_ci AS target_username,
       COUNT(*) AS duplicate_count
FROM users
WHERE username IS NOT NULL
GROUP BY target_username
HAVING COUNT(*) > 1;
~~~

If the target collation belongs to a different charset than the source expression's charset, convert the expression to the target charset before applying COLLATE.

### 5.3. Inspecting rows forming conflicts

To identify the specific records within duplicate groups:

~~~sql
SELECT
    a.user_id AS first_id,
    a.username AS first_username,
    b.user_id AS second_id,
    b.username AS second_username
FROM users AS a
JOIN users AS b
  ON a.user_id < b.user_id
 AND CONVERT(a.username USING utf8mb4) COLLATE utf8mb4_0900_ai_ci
     = CONVERT(b.username USING utf8mb4) COLLATE utf8mb4_0900_ai_ci
WHERE a.username IS NOT NULL
  AND b.username IS NOT NULL
ORDER BY a.user_id, b.user_id;
~~~

The user_id < b.user_id condition avoids returning reversed pairs and self-joins. Replace user_id with the table's actual primary key. If a group has more than two rows, the query returns multiple pairs; aggregate the results before deciding which record to keep.

### 5.4. Checking composite UNIQUE indexes

Suppose there is a unique index on (tenant_id, username). When simulating conflicts, compare all components of the key:

~~~sql
SELECT tenant_id,
       CONVERT(username USING utf8mb4)
         COLLATE utf8mb4_0900_ai_ci AS target_username,
       COUNT(*) AS duplicate_count
FROM users
WHERE tenant_id IS NOT NULL
  AND username IS NOT NULL
GROUP BY tenant_id, target_username
HAVING COUNT(*) > 1;
~~~

In a MySQL composite UNIQUE index, rows with at least one NULL key component can coexist without violating uniqueness. Therefore, when checking conflicts for a unique index, group only rows where all key components are non-NULL. If business rules require uniqueness even when NULL is present, model that rule separately.

### 5.5. Indexes using prefixes or expressions

If a unique index covers only a prefix of a string column, the check must simulate the exact prefix and collation of the index. For example, an index on the first 20 characters of username must be checked with the equivalent expression LEFT(..., 20), not merely grouped by the entire username:

~~~sql
SELECT
    LEFT(
      CONVERT(username USING utf8mb4) COLLATE utf8mb4_0900_ai_ci,
      20
    ) AS target_prefix,
    COUNT(*) AS duplicate_count
FROM users
WHERE username IS NOT NULL
GROUP BY target_prefix
HAVING COUNT(*) > 1;
~~~

For functional indexes or generated columns used in a unique key, simulate the exact expression used by the index. Inspect SHOW CREATE TABLE and INFORMATION_SCHEMA.STATISTICS to verify indexes, column order, prefix lengths, and related attributes.

### 5.6. Whitespace and Unicode rules

Collations can also differ in how trailing spaces are handled. Some collations use PAD SPACE, while others use NO PAD. As a result, strings with trailing spaces may compare differently depending on the collation. Inspect collation attributes on supported versions:

~~~sql
SELECT COLLATION_NAME, CHARACTER_SET_NAME, PAD_ATTRIBUTE
FROM information_schema.COLLATIONS
WHERE COLLATION_NAME = 'utf8mb4_0900_ai_ci';
~~~

Some Unicode collations also apply equivalence rules to strings with different Unicode representations. Do not test only uppercase/lowercase and Vietnamese diacritics; test real application data, including combining characters, whitespace, punctuation, and non-BMP characters if present.

## 6. Checking impact on indexes and constraints

### 6.1. Unique indexes

A unique index enforces uniqueness under the comparison rules of the collation attached to the column/index. When changing collation, the set of values considered equal can change. If data introduces conflicts, ALTER TABLE can fail while rebuilding indexes.

Check existing indexes:

~~~sql
SELECT INDEX_NAME,
       NON_UNIQUE,
       SEQ_IN_INDEX,
       COLUMN_NAME,
       SUB_PART,
       COLLATION
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = 'sales'
  AND TABLE_NAME = 'users'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

NON_UNIQUE = 0 indicates a unique index. SUB_PART indicates the prefix length if the index uses only part of the column. Also inspect SHOW CREATE TABLE to see the complete definition.

### 6.2. String primary keys and foreign keys

If a primary key or foreign key includes string columns, changing charset/collation can affect indexes and referential relationships. Corresponding string columns in an InnoDB foreign key must have compatible types and identical character set/collation. Never convert one side of a relationship and leave the other side unchanged.

Before migrating:

- List parent tables, child tables, and string columns in foreign keys.
- Identify indexes supporting foreign keys and related unique constraints.
- Plan the conversion order for both sides.
- If constraints must be temporarily dropped, plan write locks, verify referential integrity, and recreate constraints immediately after conversion.
- Verify types, charsets, and collations on both sides after migration.

Do not use SET FOREIGN_KEY_CHECKS = 0 as a way to skip analysis. Disabling checks does not automatically revalidate all data when re-enabled; integrity checks and controlled constraint recreation are required.

### 6.3. Index length after converting to utf8mb4

utf8mb4 can require up to 4 bytes per character. An index that fit within byte limits under an older charset may exceed limits after conversion. Key limits depend on the MySQL version, InnoDB page size, row format, and index type. Check composite key lengths and prefix indexes against actual server settings.

Do not truncate columns or prefixes merely to make ALTER succeed without evaluating the impact on uniqueness and search. If an index cannot be created because it exceeds limits, review key design, column lengths, prefixes, row format, and version before deciding.

## 7. Data with corrupted encoding: do not convert blindly

Distinguish two scenarios:

1. **Data stored correctly, client displays incorrectly:** bytes and column metadata match, yet the connection or terminal charset is wrong. Adjusting the connection/client charset can resolve this without modifying data.
2. **Data written incorrectly:** bytes were written in one encoding while the server interpreted them under another, turning stored content into corrupted text. Converting the column to utf8mb4 per current metadata may merely re-encode that corrupted text into the new encoding.

Inspect several samples:

~~~sql
SELECT
    id,
    display_name,
    HEX(display_name) AS stored_bytes,
    CHARSET(display_name) AS declared_charset,
    COLLATION(display_name) AS declared_collation
FROM customers
WHERE id IN (101, 102, 103);
~~~

Compare stored_bytes against known original strings and column metadata. Also inspect the connection charset:

~~~sql
SHOW SESSION VARIABLES LIKE 'character_set_client';
SHOW SESSION VARIABLES LIKE 'character_set_connection';
SHOW SESSION VARIABLES LIKE 'character_set_results';
~~~

If mojibake is suspected, copy a sample dataset to a test database and rehearse the recovery procedure on the copy. Do not apply CAST/CONVERT chains through BINARY across all of production without accurately determining the original encoding and how the bytes were written. A wrong conversion can destroy the ability to recover original content.

## 8. Safe migration workflow

Converting charset/collation on large tables can rebuild tables and indexes, consuming CPU, I/O, temporary disk space, and time. The procedure must be tested on representative data before applying in production.

ALTER TABLE is DDL and triggers an implicit commit per MySQL rules. Do not place the migration inside an application transaction expecting ROLLBACK to undo schema changes. Prepare separate backups, a deployment window, and a recovery plan.

### Step 1 — Define scope

List databases, tables, text columns, current charsets/collations, indexes, foreign keys, generated columns, and applications reading/writing data. Distinguish changing defaults from converting existing columns.

### Step 2 — Lock in targets and compatibility

Choose a character set and collation available on the target MySQL version. Verify that drivers, clients, migration tools, replication topology, and recovery environments all support them. Document comparison requirements: accent sensitivity, case sensitivity, and trailing-space handling.

### Step 3 — Back up and test restore

Create a restorable backup and test restoring in an isolated environment. For InnoDB, logical dumps can use a consistent snapshot, yet concurrent DDL and non-transactional objects must be accounted for. Backups must include data along with required objects such as routines, triggers, events, and deployment grants as needed.

Do not treat the mere existence of a backup file as proof. Only begin the migration once you have proven data and configuration can be restored.

### Step 4 — Build a staging copy

Restore the backup into a staging environment closely matching production's version, charset/collation, and settings. Rehearse the migration on a copy with representative scale and data distribution. Record duration, storage usage, locks, warnings, and errors.

### Step 5 — Check duplicates in advance

Run queries simulating the target collation for each unique index, including composite unique keys, prefix indexes, and functional indexes. Save the list of conflicting keys and identify the business owner of each record. Do not automatically delete or merge records just to get the migration past checks.

### Step 6 — Resolve conflicts

Choose resolution strategies based on business rules:

- Normalize one value and update references pointing to that record.
- Rename one of the conflicting values according to an agreed naming convention.
- Keep a case- or accent-sensitive collation if that reflects genuine business requirements.
- Redesign the unique key, such as including tenant or organizational scope in the unique key if uniqueness only applies within that scope.

Before merging two records, check foreign keys, transaction history, related data, and external system references. Charset/collation conversion is not a valid reason to delete data automatically.

### Step 7 — Convert during a deployment window

Choose a conversion method suited to table size and allowable downtime. For small tables, direct ALTER TABLE after backup may suffice. For large tables, evaluate online DDL or shadow-table migration tools; verify support for your exact version, engine, and alteration type.

During conversion, control concurrent writes so new duplicate values are not introduced after the pre-check step. If using a shadow table, ensure change-sync mechanisms, row-count reconciliation, and controlled cutover are in place.

### Step 8 — Verify after conversion

- Read SHOW CREATE TABLE and INFORMATION_SCHEMA to confirm charset/collation on every target column.
- Compare row counts, NULL counts, string lengths, and sample values before and after.
- Re-run duplicate detection queries under the target collation.
- Verify unique indexes, foreign keys, and constraints were recreated properly.
- Test inserts, updates, lookups, sorting, joins, and searches with Vietnamese text, mixed case, diacritics, and non-BMP Unicode characters.
- Monitor error logs, replication lag, query latency, and application errors after cutover.

### Step 9 — Retain a recovery path

Keep backups and old snapshots for a defined retention period. If issues arise, halt writes or revert the application to the previous configuration per the tested plan. Do not assume reversing a collation or charset conversion always restores original bytes; a conversion that lost characters or merged comparison semantics may be irreversible.

## 9. Connection charset and data flowing through applications

Converting columns to utf8mb4 is not enough if the client keeps sending data using an incompatible charset. In the MySQL CLI, you can set the connection charset with:

~~~sql
SET NAMES utf8mb4;
~~~

SET NAMES sets character_set_client, character_set_connection, and character_set_results; collation_connection is set per the specified charset or collation. This is a session setting and does not alter column or database charsets.

For Java applications, configure MySQL Connector/J per your driver version and use Unicode in JDBC. Do not copy outdated connection parameters from guides written for different driver versions. Verify the actual charset using SHOW SESSION VARIABLES and run round-trip tests with representative strings.

A round-trip test should include:

1. The application sends Vietnamese strings with diacritics and several non-BMP Unicode characters.
2. Read the same values back through the application itself and via MySQL CLI configured for utf8mb4.
3. Compare character values and database HEX against known input data.
4. Test collation during comparison and sorting, because accurate display does not prove comparison rules match requirements.

## 10. Complete migration example for a username column

Suppose the users table has a username column with a unique index and needs to convert to utf8mb4_0900_ai_ci.

**First, inspect the definition and indexes:**

~~~sql
SHOW CREATE TABLE users;

SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME, SUB_PART
FROM information_schema.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'users'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

**Check duplicate groups under the target collation:**

~~~sql
SELECT
    CONVERT(username USING utf8mb4)
      COLLATE utf8mb4_0900_ai_ci AS target_username,
    COUNT(*) AS row_count
FROM users
WHERE username IS NOT NULL
GROUP BY target_username
HAVING COUNT(*) > 1;
~~~

If the query returns rows, inspect the affected records and resolve them per business rules. Even if no duplicate groups are returned, still check composite unique keys, prefixes, or functional indexes if the schema uses them.

**After backup, test on a copy before altering the column:**

~~~sql
ALTER TABLE users
  MODIFY COLUMN username VARCHAR(100)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci
    NOT NULL;
~~~

The example assumes username was originally VARCHAR(100) NOT NULL with no extra attributes. If the real definition differs, preserve all existing attributes in the MODIFY statement.

**Verify after conversion:**

~~~sql
SELECT COLUMN_NAME, COLUMN_TYPE, CHARACTER_SET_NAME, COLLATION_NAME,
       IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'users'
  AND COLUMN_NAME = 'username';

SHOW CREATE TABLE users;
~~~

Re-run the duplicate query under the target collation and test login/search using case and accent variants permitted by business rules. The existing unique index must remain valid and enforce uniqueness under the new collation.

## 11. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| ALTER TABLE reports Duplicate entry | Values became equivalent under new collation or composite unique key has conflicts | Simulate with GROUP BY using target collation, resolve groups before migration |
| Incorrect string value | Target charset or column cannot represent character, or input has wrong encoding | Check source charset, sample data, connection charset, and SQL mode |
| Text remains corrupted after switching to utf8mb4 | Bytes were already written wrong previously or client displays incorrectly | Inspect HEX, column charset, and connection; rehearse recovery on a copy |
| Index too long or index creation fails | Max byte size increased after converting to utf8mb4 or exceeded index limit | Check total key length, prefixes, row format, page size, and version |
| Foreign key cannot be altered | String columns on both sides no longer share type/charset/collation or dependent index | Plan converting both columns and constraints in sequence |
| Searches return different results than before | New collation changes comparison, case, accents, or whitespace handling | Verify target collation and align queries/unique rules with business logic |
| ALTER TABLE takes too long or impacts app | Table rebuilds, indexes recreate, or DDL causes locks/I/O | Benchmark on staging, pick deployment window, and evaluate online DDL |
| Ran ALTER DATABASE yet old columns unchanged | Only the database default was updated | Convert existing columns/tables with CONVERT TO or MODIFY COLUMN |

## 12. Practice lab: simulating collation collisions

Perform in a lab database on MySQL 8.0 supporting utf8mb4_0900_ai_ci. Do not use production tables.

**Step 1 — Create a table with a case- and accent-sensitive collation:**

~~~sql
CREATE TABLE lab_accounts (
    account_id INT NOT NULL,
    username VARCHAR(100)
      CHARACTER SET utf8mb4
      COLLATE utf8mb4_0900_as_cs NOT NULL,
    PRIMARY KEY (account_id),
    UNIQUE KEY uq_lab_username (username)
) ENGINE=InnoDB;
~~~

**Step 2 — Insert values that are distinct under the source collation:**

~~~sql
INSERT INTO lab_accounts (account_id, username) VALUES
    (1, 'Admin'),
    (2, 'admin'),
    (3, 'resume'),
    (4, 'résumé');
~~~

**Step 3 — Check under source and target collations:**

~~~sql
SELECT username, COUNT(*)
FROM lab_accounts
GROUP BY username;

SELECT
    username COLLATE utf8mb4_0900_ai_ci AS target_username,
    COUNT(*) AS duplicate_count
FROM lab_accounts
GROUP BY target_username
HAVING COUNT(*) > 1;
~~~

Observe which groups collapse when compared under the accent- and case-insensitive target collation.

**Step 4 — Try converting on the lab copy.** Try running ALTER TABLE to change the collation; the operation will fail if the unique index cannot enforce uniqueness under the new collation. Record the error message and confirm the table still holds data for further inspection.

~~~sql
ALTER TABLE lab_accounts
  CONVERT TO CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

**Step 5 — Resolve duplicate data per lab rules.** Pick a canonical username, rename remaining values to unique names per lab rules, or delete test rows after recording results. Do not apply this approach to real data without evaluating referential relationships.

**Step 6 — Re-run checks and convert.** Confirm the duplicate query returns no conflicting groups, then run ALTER TABLE and inspect SHOW CREATE TABLE.

**Step 7 — Clean up the lab.**

~~~sql
DROP TABLE lab_accounts;
~~~

Drop only the lab table created for this exercise.

**Expected outcome:** be able to explain why a new collation can create duplicates, simulate comparison under the target collation, identify unique index conflicts, and perform the conversion once data satisfies the new rules.

## 13. Pre-production conversion checklist

- Confirmed the MySQL version and target collation are supported across all relevant environments.
- Inventoried charsets/collations at database, table, column, and connection levels.
- Determined whether data was written with corrupted encoding or merely displayed incorrectly.
- Reviewed SHOW CREATE TABLE, indexes, foreign keys, generated columns, and dependent constraints.
- Checked duplicates under the target collation for all unique keys, including composite keys, prefixes, and functional indexes.
- Excluded rows with NULL components from unique-key duplicate checks per actual MySQL semantics.
- Evaluated byte lengths of columns and indexes after converting to the target charset.
- Backed up and tested restoring; rehearsed migration on a representative copy.
- Finalized duplicate-data resolution plans with business owners.
- Planned the deployment window, concurrent write controls, monitoring plan, and rollback plan.
- Post-conversion, verified metadata, row counts, sample values, indexes, foreign keys, replication, and application behavior.

## 14. Key principles to remember

- Character set determines encoding; collation determines comparison and sorting.
- ALTER DATABASE or ALTER TABLE DEFAULT CHARACTER SET only changes defaults, not existing data.
- CONVERT TO CHARACTER SET converts character columns in the table; MODIFY COLUMN fits converting a single column and must redeclare all attributes.
- Data written with corrupted encoding is not automatically fixed by changing charset; inspect bytes, metadata, and connection charset.
- Accent/case-insensitive collations can make distinct values become equivalent and trigger UNIQUE conflicts.
- Duplicate checks must simulate the exact collation, prefix, and all components of the target unique key.
- For unique keys, multiple rows with NULL components can be valid under MySQL rules; do not treat them as duplicates solely because GROUP BY groups NULLs.
- Converting to utf8mb4 can increase byte footprint and impact index limits.
- Foreign keys on string columns must be converted in sync on both sides.
- Backups, restore tests, post-migration verification, and a recovery plan are mandatory parts of production changes.

Safe charset/collation conversion requires controlling both encoding and data equivalence rules. By checking duplicates under the target collation beforehand, understanding index dependencies, and rehearsing migrations on a copy, you can transition to Unicode standards while protecting data integrity and application behavior.
