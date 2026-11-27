# Illegal Mix of Collations and Wrong Character Set Data

**Illegal mix of collations** occurs when MySQL must compare or combine string expressions but cannot resolve a valid collation according to its precedence rules. The common error code is **1267**; operations combining multiple strings can return error **1271**. A closely related issue is Vietnamese text turning into question marks, replacement characters, or **Incorrect string value** errors (typically code **1366**). The two problem groups are related yet distinct: a collation defines how strings are compared and sorted, whereas a character set defines how characters are encoded into bytes.

This lesson belongs to the **DATABASE_MYSQL** module, **Troubleshooting** chapter. The goal is to accurately diagnose the error source across tables, columns, SQL literals, connections, or stored data; choose the right fix; and convert character sets/collations without corrupting data or causing key conflicts.

## 1. Distinguishing Character Set and Collation

These two concepts always go together yet solve different problems:

- **Character set** defines the repertoire of characters and how characters map to bytes. For example, **utf8mb4** can store any Unicode character, including Vietnamese, emoji, and characters outside the Basic Multilingual Plane.
- **Collation** defines rules for comparing and sorting strings within a character set. It decides whether strings differing in letter case or accents are considered equal.

For example, the same `utf8mb4` character set can use different collations:

| Collation | Primary Rules | Example Behavior |
|---|---|---|
| `utf8mb4_0900_ai_ci` | Accent-insensitive, case-insensitive per Unicode Collation Algorithm 9.0 | Typically treats `a`, `A`, and `á` as equal in comparisons |
| `utf8mb4_0900_as_cs` | Accent-sensitive, case-sensitive | Distinguishes accents and letter case |
| `utf8mb4_bin` | Compares by binary string value | Distinguishes bytes/characters by binary rules |
| `utf8mb4_general_ci` | Older general-purpose rules | Not strictly equivalent to newer UCA collations |

Collation names typically carry suffixes:

- **_ai:** accent-insensitive, ignores diacritics.
- **_as:** accent-sensitive, distinguishes diacritics.
- **_ci:** case-insensitive, ignores letter case.
- **_cs:** case-sensitive, distinguishes letter case.
- **_bin:** compares by binary value.

You cannot look solely at `utf8mb4` to conclude two columns compare identically. Two columns with the same character set but different collations can still collide in `JOIN`, `UNION`, `CONCAT`, or expression comparisons.

### Why Are Charset Errors and Collation Errors Different?

| Symptom | Common Cause |
|---|---|
| Illegal mix of collations | String expressions have incompatible collations or equal precedence that cannot be reconciled |
| `COLLATION ... is not valid for CHARACTER SET ...` | Selected collation does not belong to the expression's character set |
| Incorrect string value | Bytes sent to the server are invalid for the target character set, or the character cannot be represented in the target charset |
| Data displays `?` or `` | Wrong client charset, display issue, or data already suffered replacement/byte loss earlier |
| Vietnamese becomes mojibake, e.g., `Tiáº¿ng Viá»‡t` | UTF-8 bytes were interpreted as another charset or converted multiple times |

Changing a collation cannot restore characters already replaced with question marks. Conversely, changing a character set does not automatically resolve every collation conflict inside queries.

## 2. Where MySQL Gets Charset and Collation Settings

MySQL configures these at multiple levels. A string in an SQL statement may carry a different charset/collation than the column it is compared against.

### Server Level

Server-wide default variables include:

- **character_set_server:** default character set for new databases if unspecified.
- **collation_server:** default collation for new databases if unspecified.

Check:

~~~sql
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
~~~

### Database Level

A database has its own default character set and collation. They act as defaults when creating new tables or objects without explicit declarations:

~~~sql
SELECT
  SCHEMA_NAME,
  DEFAULT_CHARACTER_SET_NAME,
  DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = 'app';
~~~

Changing the database default does not automatically convert existing tables or columns. It only affects defaults for objects created afterward.

### Table and Column Level

Each table has a default charset/collation; individual string columns can override it with their own settings.

~~~sql
SHOW CREATE TABLE app.customers\G
~~~

Inspect column details:

~~~sql
SELECT
  TABLE_SCHEMA,
  TABLE_NAME,
  COLUMN_NAME,
  DATA_TYPE,
  CHARACTER_SET_NAME,
  COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'app'
  AND TABLE_NAME = 'customers'
ORDER BY ORDINAL_POSITION;
~~~

Only character-type columns have a character set and collation. Numeric, datetime, or binary columns typically show `NULL` for both fields.

### Connection/Session Level

These variables control how client and server exchange strings:

| Variable | Role |
|---|---|
| `character_set_client` | Character set the server assumes for statements sent by the client |
| `character_set_connection` | Character set used after converting from client when the server processes string literals |
| `character_set_results` | Character set used to send string results back to the client |
| `collation_connection` | Default collation of string literals and certain expressions on the connection |

Check inside the exact failing session:

~~~sql
SHOW VARIABLES LIKE 'character_set%';
SHOW VARIABLES LIKE 'collation%';

SELECT
  @@character_set_client,
  @@character_set_connection,
  @@character_set_results,
  @@collation_connection;
~~~

Output in a separate SQL client window does not prove the application's connection shares the same configuration. Each connection in a pool may be created or initialized differently.

## 3. Reproducing Illegal Mix of Collations

Suppose a system has an old table and a new table. The customer name column in the old table uses `utf8mb4_general_ci`, while the new table uses `utf8mb4_0900_ai_ci`.

~~~sql
CREATE TABLE app.customer_legacy (
  customer_id BIGINT PRIMARY KEY,
  customer_name VARCHAR(100)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_general_ci
) ENGINE=InnoDB;

CREATE TABLE app.customer_new (
  customer_id BIGINT PRIMARY KEY,
  customer_name VARCHAR(100)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci
) ENGINE=InnoDB;
~~~

A `JOIN` can trigger a collation conflict:

~~~sql
SELECT
  old.customer_id,
  new.customer_id
FROM app.customer_legacy AS old
JOIN app.customer_new AS new
  ON old.customer_name = new.customer_name;
~~~

Depending on coercibility rules and MySQL version, this expression can return error 1267. Inspect the exact collation of each expression in the active session:

~~~sql
SELECT
  COLLATION(old.customer_name) AS old_collation,
  COLLATION(new.customer_name) AS new_collation,
  COERCIBILITY(old.customer_name) AS old_coercibility,
  COERCIBILITY(new.customer_name) AS new_coercibility
FROM app.customer_legacy AS old
CROSS JOIN app.customer_new AS new
LIMIT 1;
~~~

Do not fix this by changing the collation of the entire database before knowing which column is causing the error. A query can combine multiple sources: table columns, literals, prepared statement parameters, `CASE` expressions, `CONCAT`, views, or temporary tables.

## 4. Coercibility Rules: Which Collation Does MySQL Choose?

When combining string expressions, MySQL uses a precedence ranking called **coercibility** to determine the resulting collation. A smaller number means higher precedence.

| Coercibility | Common Expression Source | Meaning |
|---:|---|---|
| 0 | Expression with explicit `COLLATE` | Explicit |
| 1 | Result of combining strings with different collations | No collation |
| 2 | Column, routine parameter, or local variable with declared collation | Implicit |
| 3 | Certain system constants such as `USER()` or `DATABASE()` | System constant |
| 4 | String literal | Coercible |
| 5 | Numeric or temporal value converted to string | Numeric |
| 6 | `NULL` | Ignorable |

You can inspect with:

~~~sql
SELECT
  COLLATION('Hello') AS literal_collation,
  COERCIBILITY('Hello') AS literal_coercibility,
  COLLATION('Hello' COLLATE utf8mb4_0900_ai_ci) AS explicit_collation,
  COERCIBILITY('Hello' COLLATE utf8mb4_0900_ai_ci)
    AS explicit_coercibility;
~~~

A column typically has coercibility 2; a literal typically has coercibility 4. Therefore, a literal can be coerced to the column's collation in a comparison. However, if two columns share the same precedence and have irreconcilable collations, MySQL reports `Illegal mix of collations`.

Rules include additional edge cases for binary/nonbinary strings, different character sets, and specific operators. Use `COLLATION()` and `COERCIBILITY()` on the exact query expressions to verify rather than guessing from table names.

## 5. Expressions That Commonly Trigger Conflicts

Errors do not happen only in `WHERE =` predicates. Review these string-combining operations:

- **JOIN / WHERE:** comparing columns from two tables with different collations.
- **UNION / UNION ALL:** corresponding columns across two `SELECT`s have incompatible charsets/collations.
- **CONCAT / CONCAT_WS:** concatenating string expressions from multiple sources.
- **CASE / IF / COALESCE:** branches returning strings with different collations.
- **GROUP BY / DISTINCT:** determining whether two strings are equal per collation.
- **ORDER BY:** sorting according to the expression's collation rules.
- **LIKE / IN:** comparing a string with a pattern or a list of literals/columns of different collations.
- **Views, stored routines, temporary tables:** objects created at a time or in a session with different defaults.

Example with `UNION`:

~~~sql
SELECT customer_name
FROM app.customer_legacy
UNION ALL
SELECT customer_name
FROM app.customer_new;
~~~

Example with `CASE`:

~~~sql
SELECT
  CASE
    WHEN status_code = 1 THEN 'Active'
    ELSE description
  END AS status_label
FROM app.customer_new;
~~~

When a query errors, progressively simplify the expression and use `COLLATION(expr)` to pinpoint the source. For views or routines, inspect their definitions and creation timestamps; the database default charset may have changed after the object was created.

## 6. Step-by-Step Diagnostic Procedure

Do not start by changing collations. First reproduce the error on the exact connection and gather evidence.

### Step 1 — Capture the Full Error

Collect:

- Error number and `SQLState`.
- Complete executed SQL statement, scrubbed of sensitive data.
- Involved database, table, column, and alias names.
- MySQL Server and Connector/J/client versions.
- Whether the error occurs in `JOIN`, `UNION`, `WHERE`, `INSERT`, `UPDATE`, or when reading results.
- Whether the error occurs for all data or only specific values.

Common error codes:

| Code | Message / Error Group | Meaning |
|---:|---|---|
| 1267 | Illegal mix of collations | Collation conflict in a comparison |
| 1271 | Illegal mix of collations for operation | Conflict when combining multiple string expressions |
| 1253 | `COLLATION is not valid for CHARACTER SET` | Chosen collation does not belong to the expression's charset |
| 1366 | Incorrect string value | Value cannot be validly converted to target charset |
| 1300 | Invalid ... character string | Byte sequence is invalid for the interpreted character set |

### Step 2 — Check Session Charset/Collation

Run on the exact failing connection:

~~~sql
SELECT
  VERSION() AS mysql_version,
  @@character_set_client AS client_charset,
  @@character_set_connection AS connection_charset,
  @@character_set_results AS results_charset,
  @@collation_connection AS connection_collation;
~~~

If the error happens only in the application, run the statement through the actual `DataSource` or log session variables from the app. Do not compare MySQL Workbench output against a connection pool session and assume they match.

### Step 3 — Check Database, Tables, and Columns

~~~sql
SELECT
  SCHEMA_NAME,
  DEFAULT_CHARACTER_SET_NAME,
  DEFAULT_COLLATION_NAME
FROM information_schema.SCHEMATA
WHERE SCHEMA_NAME = 'app';

SELECT
  TABLE_NAME,
  TABLE_COLLATION
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'app'
  AND TABLE_TYPE = 'BASE TABLE';

SELECT
  TABLE_NAME,
  COLUMN_NAME,
  COLUMN_TYPE,
  CHARACTER_SET_NAME,
  COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'app'
  AND CHARACTER_SET_NAME IS NOT NULL
ORDER BY TABLE_NAME, ORDINAL_POSITION;
~~~

Multiple collations in the output are not necessarily a bug: a schema may intentionally use different collations for specific columns. Focus on the columns appearing together in the failing expression.

### Step 4 — Inspect Specific Expressions

For each expression:

~~~sql
SELECT
  COLLATION(column_a),
  COERCIBILITY(column_a),
  COLLATION(column_b),
  COERCIBILITY(column_b);
~~~

If the expression contains a literal, check the literal too:

~~~sql
SELECT
  CHARSET('Đặng'),
  COLLATION('Đặng'),
  COERCIBILITY('Đặng');
~~~

Reduce the query by removing `JOIN`, `CASE`, `CONCAT`, or `UNION` branches one by one until you isolate the expression triggering the error. Then decide whether to convert the charset, apply explicit collation, or standardize the schema.

### Step 5 — Distinguish Comparison Errors from Corrupted Encoding

If the query runs but Vietnamese text renders incorrectly, inspect stored bytes:

~~~sql
SELECT
  customer_id,
  customer_name,
  HEX(customer_name) AS stored_hex,
  LENGTH(customer_name) AS byte_length,
  CHAR_LENGTH(customer_name) AS character_length
FROM app.customers
WHERE customer_id = 1001;
~~~

For Unicode strings, `LENGTH()` counts bytes whereas `CHAR_LENGTH()` counts characters in the column's charset. A difference between them is normal for UTF-8; it does not prove data is corrupted. Compare `HEX()` against the expected UTF-8 bytes of a known value and inspect the same data through another client.

## 7. Resolving Collation Conflicts Inside a Query

If two columns share the same character set but differ in collation, you can specify a common collation to permit comparison.

~~~sql
SELECT old.customer_id, new.customer_id
FROM app.customer_legacy AS old
JOIN app.customer_new AS new
  ON old.customer_name COLLATE utf8mb4_0900_ai_ci
   = new.customer_name COLLATE utf8mb4_0900_ai_ci;
~~~

This example is valid only if both expressions have character set `utf8mb4` and the chosen collation exists on the running MySQL version. It applies the comparison rule for this `JOIN` without altering column definitions or stored data.

### When Two Expressions Have Different Character Sets

If one column is `latin1` and the other is `utf8mb4`, first convert the expression to the same character set, then specify a valid collation:

~~~sql
SELECT old.customer_id, new.customer_id
FROM app.customer_legacy AS old
JOIN app.customer_new AS new
  ON CONVERT(old.customer_name USING utf8mb4)
       COLLATE utf8mb4_0900_ai_ci
   = new.customer_name COLLATE utf8mb4_0900_ai_ci;
~~~

`CONVERT(... USING utf8mb4)` instructs MySQL to transcode characters from the source charset into `utf8mb4`. This is only valid if the declared charset of the source data accurately reflects the stored bytes. If UTF-8 bytes were mistakenly stored in a `latin1` column, `CONVERT` can produce mojibake instead of fixing the data.

### Normalizing Literals

For literals, you can use a character set introducer and `COLLATE`:

~~~sql
SELECT customer_id
FROM app.customers
WHERE customer_name =
  _utf8mb4'Đặng' COLLATE utf8mb4_0900_ai_ci;
~~~

The introducer tells the server which character set the literal belongs to; `COLLATE` selects the comparison rule. It does not replace configuring the proper client charset when sending SQL. If the client already sent mangled bytes, an introducer cannot restore the original text.

### Performance Considerations

Applying `COLLATE` or `CONVERT` directly to a column in `JOIN`/`WHERE` can prevent MySQL from using an index optimally, depending on the expression and execution plan. After making the query run correctly:

~~~sql
EXPLAIN
SELECT old.customer_id, new.customer_id
FROM app.customer_legacy AS old
JOIN app.customer_new AS new
  ON old.customer_name COLLATE utf8mb4_0900_ai_ci
   = new.customer_name COLLATE utf8mb4_0900_ai_ci;
~~~

Inspect access type, `key`, `rows`, and actual execution time. If this is a hot query, the sustainable fix is usually standardizing charset/collation in the schema or maintaining a properly indexed normalized column rather than forcing conversions on every query.

Do not use `BINARY` or `CAST AS BINARY` as a default workaround. Binary comparison changes semantics: letter case, diacritics, and byte differences become significant, which can alter business results.

## 8. Fixing Connection Charset Configuration

If the problem lies in how the client sends or receives data, fix the connection configuration. This does not alter existing columns' charset/collation.

### In an SQL Client or Admin Session

In an interactive SQL client, you can set:

~~~sql
SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
~~~

`SET NAMES` sets `character_set_client`, `character_set_connection`, `character_set_results`, and `collation_connection` for the session. Use only a collation available and compatible with `utf8mb4` on the server. Verify afterward with `SHOW VARIABLES`.

### In a Java Application with Connector/J

With JDBC, let Connector/J manage charset negotiation per its driver version and configuration. Do not arbitrarily run `SET NAMES` every time a connection is borrowed if the driver also manages charset; the two mechanisms can fall out of sync.

Items to verify:

- Actual Connector/J version.
- Session charset/collation via `SELECT @@character_set_client, @@character_set_connection, @@character_set_results, @@collation_connection`.
- Character encoding or connection collation settings per documentation for that exact Connector/J version.
- Charset of data sent from the application and how the framework binds `PreparedStatement` parameters.
- How result character sets are decoded by the client/driver.

With modern Connector/J, UTF-8/`utf8mb4` is usually supported automatically; do not copy legacy properties just because you found them in an old app's configuration. If connection collation must be pinned, use properties supported by your driver version and inspect the session after the pool creates a connection.

### With Connection Pools

Connection pools reuse sessions. Initialization settings must apply consistently to every new connection. If you change charset via `SET NAMES` on a connection and return it to the pool, the next request may receive a session in an unexpected state. Avoid mutating session settings mid-request; if needed, standardize via tested `DataSource` or connection initialization configuration.

## 9. Standardizing Schema Default Charset/Collation

Once columns and data are confirmed properly encoded, you can standardize defaults for new objects and convert existing tables according to a plan.

### Changing the Database Default

~~~sql
ALTER DATABASE app
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

This changes the database default for subsequently created objects. It **does not automatically convert** data or collations of existing tables or columns.

### Changing the Table Default

~~~sql
ALTER TABLE app.customers
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

This changes the table's default charset/collation, affecting newly added string columns if not explicitly specified. It **does not convert** the collation of existing string columns.

### Converting Existing String Columns

~~~sql
ALTER TABLE app.customers
  CONVERT TO CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
~~~

`CONVERT TO CHARACTER SET` instructs MySQL to convert the table's character columns to the target charset/collation. This is both a data and metadata change that may rebuild the table, generate I/O load, hold metadata locks, and require extra disk space. Read your version's documentation for supported DDL algorithms; never assume this command is always `INSTANT` or lock-free.

In some cases, MySQL may widen column types to preserve character capacity when converting to a charset with larger max bytes per character—for example, changing `VARCHAR` to `TEXT`. Always inspect `SHOW CREATE TABLE` after migration and check whether applications, ORMs, indexes, or length limits depend on the old column type.

If you only want to change one column:

~~~sql
ALTER TABLE app.customers
  MODIFY customer_name VARCHAR(150)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci
    NOT NULL;
~~~

When using `MODIFY`, you must restate all existing column attributes such as data type, length, `NULL`/`NOT NULL`, `DEFAULT`, `COMMENT`, generated expressions, and other attributes. Omitting an attribute can unintentionally alter the schema. Use `SHOW CREATE TABLE` as the baseline when authoring DDL.

### Checking Whether a Collation Exists on the Server

~~~sql
SHOW COLLATION LIKE 'utf8mb4_0900_ai_ci';
SHOW CHARACTER SET LIKE 'utf8mb4';
~~~

`utf8mb4_0900_*` collations belong to the MySQL 8.0 family; MySQL 5.7 lacks these UCA 9.0 collations. MariaDB has its own collation list and names by version. Do not use a collation name from a newer MySQL on an older server or MariaDB without verifying first.

## 10. Data Stored Under the Wrong Character Set

This scenario is more dangerous than an ordinary collation mismatch. For example, a column is declared `latin1`, yet the actual bytes stored inside are UTF-8 bytes. MySQL interprets each byte as `latin1`, displaying mojibake. Running `CONVERT TO CHARACTER SET utf8mb4` directly tells MySQL to transcode characters from the declared `latin1`, leaving the result still corrupted.

### Distinguishing Three Cases

1. **Correct declaration, wrong connection:** table data is valid, but the client sends or reads with the wrong charset. Fix connection configuration; do not alter stored data.
2. **Wrong column declaration, bytes intact:** bytes are valid UTF-8 stored in a column declared `latin1` or another charset. Recover the raw bytes and reinterpret them under the true charset.
3. **Bytes already replaced or lost:** data turned into question marks or replacement characters prior to storage. Changing charsets cannot recover lost information; restore from backups or original source data.

### Checking Bytes Before Converting

~~~sql
SELECT
  customer_id,
  customer_name,
  HEX(customer_name) AS raw_hex,
  LENGTH(customer_name) AS byte_length,
  CHAR_LENGTH(customer_name) AS character_length
FROM app.customers
WHERE customer_id IN (1001, 1002, 1003);
~~~

Pick known accurate values and compare `HEX` against expected bytes. Check multiple data groups, including ASCII text, accented Vietnamese, emoji if stored, and records imported from different sources. A single table can contain data written across multiple eras with different encodings.

Never rely solely on a GUI screenshot to conclude bytes are valid. GUIs may silently transcode charsets during display.

### Recovery Procedure When UTF-8 Bytes Were Misdeclared

If you confirm the column actually holds UTF-8 bytes despite another declared charset, you may need to preserve the raw bytes in a temporary binary column and then reinterpret them as `utf8mb4` into the target column. Illustrative pattern:

~~~sql
-- 1. Create a copy or staging column large enough to preserve raw bytes.
ALTER TABLE app.customers
  ADD COLUMN customer_name_raw VARBINARY(1024) NULL;

-- 2. Copy current bytes without collation conversion.
UPDATE app.customers
SET customer_name_raw = CAST(customer_name AS BINARY);

-- 3. Create target column with the proper charset.
ALTER TABLE app.customers
  ADD COLUMN customer_name_fixed VARCHAR(255)
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci NULL;

-- 4. Reinterpret staging bytes as UTF-8 after verifying data.
UPDATE app.customers
SET customer_name_fixed =
    CONVERT(customer_name_raw USING utf8mb4);
~~~

This is strictly an illustrative pattern explaining the workflow, not a script to run directly in production. Size the staging column for maximum byte length, verify valid byte sequences, handle `NULL`s, verify lengths, reconcile data, and test on a copy first. If source bytes are not valid UTF-8, the `CONVERT` step can fail or produce unwanted output.

Only after full reconciliation should you plan switching applications to the fixed column, updating indexes/constraints, renaming columns, or dropping the old column. Keep originals until backups and recovery verification are complete.

### Lost Characters Cannot Be Recovered

If a client sent a character unrepresentable in the column's charset and the server saved a question mark, the original bytes no longer exist in the database. Changing the column to `utf8mb4` only enables storing Unicode going forward; it cannot turn question marks back into original characters. You must restore from backups, source logs, or original records retained in another system.

## 11. Risks When Changing Collations

Changing collations can alter comparison results and data uniqueness even when underlying bytes do not change.

### Unique Keys Can Trigger Duplicates

Suppose an earlier collation was case-sensitive, so these values coexisted:

~~~text
Admin
admin
~~~

If switched to a case-insensitive collation, both values become equal. If the column has a `UNIQUE` index, `ALTER` can fail with duplicate key errors.

Pre-check using the target collation:

~~~sql
SELECT
  customer_name COLLATE utf8mb4_0900_ai_ci AS normalized_name,
  COUNT(*) AS duplicate_count
FROM app.customers
WHERE customer_name IS NOT NULL
GROUP BY customer_name COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
~~~

This query applies only when the source column uses `utf8mb4` and is a non-`NULL` single-column key. If the column uses another charset, convert the expression to `utf8mb4` first and then apply the target collation. For multi-column unique indexes, group by all key columns and handle `NULL`s per index semantics. Review duplicate groups with business stakeholders before altering unique constraints.

### Indexes and Length Limits

`utf8mb4` can take up to four bytes per character. Converting a column from a single-byte charset to `utf8mb4` increases index size. Check:

- Total byte length of columns in composite indexes.
- Index prefix lengths.
- InnoDB row format and page size.
- MySQL version and corresponding index limits.
- Index rebuild capacity and temporary disk space.

Never assume every `VARCHAR(255)` can have a full index across all versions/configurations. Older systems may have tighter index limits than modern InnoDB configurations.

### Application Semantics Changes

A new collation can change:

- Search and `LIKE` results.
- Group counts in `GROUP BY` and `DISTINCT`.
- `ORDER BY` sort order.
- `JOIN` matches and key comparisons.
- Unique key and upsert behavior.

Beyond accents and letter case, collations also carry `PAD SPACE` or `NO PAD` properties. Some older collations ignore trailing spaces in comparisons, whereas `0900` UCA 9.0 collations use `NO PAD`. Switching to an `0900` collation can change comparisons on strings with trailing spaces and alter unique key behavior. Test strings with trailing whitespace before switching.

For example, an application that previously allowed two usernames differing only in letter case can no longer create both after switching to a case-insensitive collation. That is a business rule change, not just a technical change.

## 12. Safe Migration Plan

Converting charsets/collations on production tables requires a dedicated plan, especially for large tables or tables with unique keys.

### Before the Change

1. Record `SHOW CREATE TABLE`, indexes, foreign keys, triggers, and column collations.
2. Confirm existing data bytes match their declared charsets.
3. Choose target charsets/collations compatible with every server in the topology.
4. Check for unique collisions under the target collation.
5. Estimate disk space, rebuild duration, I/O, and replica lag.
6. Back up and test restoration; test the migration on a production-like data copy.
7. Test application behavior against the new comparison rules.

### During Execution

- Choose a change window suited to workload.
- Monitor metadata locks, long transactions, disk space, and replica lag.
- For large tables, evaluate native MySQL online DDL or online schema change tools per supported conditions.
- Break changes down by table/column if needed for control and rollback.
- Do not mix charset/collation changes with unrelated schema edits simultaneously.

### After the Change

- Compare `SHOW CREATE TABLE` and column metadata against the target design.
- Reconcile row counts, `NULL`s, lengths, and sample values via `HEX`.
- Verify unique keys, foreign keys, indexes, and query plans.
- Run integration tests for search, `JOIN`, `ORDER BY`, `GROUP BY`, and Vietnamese writes.
- Confirm replication and applications produce no new errors.
- Drop staging columns or old copies only after the verification window ends and backups are confirmed.

## 13. Handling Incorrect String Value and Corrupted Vietnamese Data

Error 1366 typically occurs when MySQL cannot convert incoming data to the column's character set or when input bytes are invalid. For Vietnamese applications, the cause usually lies in one of these places:

- Client sends UTF-8, but the session declares a different charset.
- Target column or table uses a charset incapable of storing the input characters.
- Application transcoded the string multiple times before binding parameters.
- Imported CSV file has a different encoding than declared in `LOAD DATA`.
- File was read with the wrong charset before sending to the database.

### Check Column Configuration

~~~sql
SHOW CREATE TABLE app.customers\G

SELECT
  COLUMN_NAME,
  CHARACTER_SET_NAME,
  COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'app'
  AND TABLE_NAME = 'customers'
  AND COLUMN_NAME = 'customer_name';
~~~

### Check Session

~~~sql
SELECT
  @@character_set_client,
  @@character_set_connection,
  @@character_set_results,
  @@collation_connection;
~~~

### Inspect Input Bytes and Stored Bytes

Insert a test record through the exact application path, then read `HEX` from MySQL. Compare bytes against the expected UTF-8 encoding of the test string. If writing via an SQL client succeeds while the application fails, focus on the driver, `DataSource` settings, and how the framework binds parameters.

Never disable strict SQL mode to hide error 1366. Downgrading errors to warnings or substituting characters silently loses data without the application noticing.

### When Importing Files

Declare the file's character set in the import statement:

~~~sql
LOAD DATA INFILE '/var/lib/mysql-files/customers.csv'
INTO TABLE app.customers_import
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
(customer_id, customer_name);
~~~

Ensure the file is genuinely UTF-8. Declaring `CHARACTER SET utf8mb4` does not automatically and accurately convert a Windows-1258 or differently encoded file into UTF-8 if the source bytes do not match.

## 14. Preventing Recurring Charset/Collation Errors

To prevent every table or application from picking different settings, standardize policies at both schema and connection layers.

### Pick One Standard for Text Data

- Prefer **utf8mb4** for new Unicode data.
- Pick a collation matching business rules—for instance, whether case and accents are ignored or distinguished.
- Use the same standard across columns frequently joined or compared together.
- Use binary collations only when binary comparison semantics are truly required.
- Never rely on implicit defaults; declare charset/collation explicitly in important DDL.

### Be Careful with the Name `utf8`

In MySQL, the name **utf8** is an alias for **utf8mb3** on versions still supporting that alias. `utf8mb3` supports at most three bytes per character and cannot store certain Unicode characters such as many emoji. For new schemas, use `utf8mb4`. When auditing legacy systems, never blindly replace `utf8` with `utf8mb4`; inspect data, indexes, unique constraints, and applications first.

`utf8mb3` was deprecated starting in MySQL 8.0.28. MySQL 8.0 commonly uses `utf8mb4_0900_ai_ci` as the default collation for `utf8mb4`, yet systems upgraded from older versions may retain older collations at database, table, and column levels. Never infer actual collations solely from server version.

### Align Environments and Topology

- Use the same MySQL version or a common intersection of collations across primary, replicas, and recovery environments.
- Verify collation availability before running migrations or restores.
- Keep connection charset settings consistent across `DataSource` and all connection pools.
- Standardize CSV/import file reading and application encoding.
- Specify charset/collation explicitly in migration scripts so new environments do not depend on server defaults.

### Test Unicode Data Thoroughly

Build a test dataset containing:

- Accented and unaccented Vietnamese characters.
- Uppercase and lowercase letters.
- Unicode combining-mark strings if the application accepts input from diverse sources.
- Non-BMP characters like emoji if required by business features.
- Empty strings, `NULL`s, quotes, and special characters.

Test writes, reads, searches, `JOIN`, `GROUP BY`, `ORDER BY`, and unique keys. A single successful `INSERT` does not prove the entire text-handling pipeline is sound.

## 15. Quick Decision Matrix

| Symptom | First Check | Remediation Path |
|---|---|---|
| Error 1267 when joining two tables | `COLLATION()` and `COERCIBILITY()` of both columns | Standardize collation in query or schema |
| Error 1271 in `UNION`/`CONCAT`/`CASE` | Collation of each branch/argument | Coerce branches to the same charset and collation |
| Error 1253 | Expression character set and specified collation | Choose a collation belonging to that character set |
| Error 1366 inserting Vietnamese text | Session charset, column charset, and input bytes | Fix connection/column or import encoding after verification |
| Characters display wrong without query error | `HEX()`, `charset_results`, and client display | Determine whether bytes were corrupted on write or only misdecoded on read/display |
| Mojibake in a `latin1` column | `SHOW CREATE TABLE` and `HEX()` | Verify raw bytes; recover via binary staging if applicable |
| `ALTER` changing collation reports duplicate key | Duplicate values under target collation | Resolve business conflicts before rebuilding `UNIQUE` index |
| App fails while SQL client works | Session variables on the exact `DataSource` | Inspect Connector/J, pool initialization, and parameter binding |

## 16. Pre- and Post-Fix Checklist

**Diagnostics**

- [ ] Recorded error number, `SQLState`, and failing SQL statement.
- [ ] Identified the exact failing session/connection.
- [ ] Checked server, database, table, and column charsets/collations.
- [ ] Used `COLLATION()` and `COERCIBILITY()` on involved expressions.
- [ ] Distinguished collation conflicts from misencoded data bytes.
- [ ] Checked `HEX()` against known sample values.

**Query/Connection Fixes**

- [ ] Target collation exists and is compatible with the character set.
- [ ] Applied `COLLATE`/`CONVERT` only to necessary expressions.
- [ ] Checked `EXPLAIN` after adding conversions to `JOIN`/`WHERE`.
- [ ] Connection pool has consistent charset configuration.
- [ ] Avoided arbitrary `SET NAMES` inside individual JDBC requests.

**Schema/Data Conversion**

- [ ] Backed up and tested restoration.
- [ ] Confirmed stored bytes match declared charsets.
- [ ] Checked unique collisions under the target collation.
- [ ] Assessed index lengths, storage, DDL locks, and replica lag.
- [ ] Tested migration on a representative data copy.
- [ ] Verified Vietnamese text, Unicode data, and query plans after conversion.
- [ ] Preserved original data until reconciliation completed.

## References

- [MySQL Reference Manual — Character Sets and Collations](https://dev.mysql.com/doc/refman/8.0/en/charset.html)
- [MySQL Reference Manual — Connection Character Sets and Collations](https://dev.mysql.com/doc/refman/8.0/en/charset-connection.html)
- [MySQL Reference Manual — Collation Coercibility in Expressions](https://dev.mysql.com/doc/refman/8.0/en/charset-collation-coercibility.html)
- [MySQL Reference Manual — Column Character Set Conversion](https://dev.mysql.com/doc/refman/8.0/en/charset-conversion.html)
- [MySQL Reference Manual — ALTER TABLE](https://dev.mysql.com/doc/refman/8.0/en/alter-table.html)
- [MySQL Reference Manual — Character Set utf8mb4](https://dev.mysql.com/doc/refman/8.0/en/charset-unicode-utf8mb4.html)

## Conclusion

Illegal mix of collations is a string comparison rule issue; corrupted Vietnamese text is usually a byte, character set, or connection issue. Inspect the charset/collation of each expression and session using metadata, `COLLATION()`, and `COERCIBILITY()` before making changes. Use `COLLATE` or `CONVERT` for targeted queries when appropriate; standardize the schema when a long-term solution is needed. If bytes were misdeclared, verify `HEX` and recover safely before running `ALTER`. Finally, verify unique keys, indexes, query plans, and the JDBC pipeline to ensure changes do not break semantics or lose data.
