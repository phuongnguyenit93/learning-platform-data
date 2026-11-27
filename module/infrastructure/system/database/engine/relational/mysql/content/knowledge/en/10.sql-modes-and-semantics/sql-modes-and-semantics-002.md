# Strict Mode, Conversion Errors, and the Risk of Truncated Data

MySQL can handle data that does not match a column's type in two ways: reject the statement with an error, or adjust the value and continue with a warning. This behavior depends on `sql_mode`, the statement type, the storage engine, and the use of keywords such as `IGNORE`. If strict mode is not enabled or the application ignores warnings, invalid data can be stored in truncated form, coerced, or replaced with boundary values.

**Strict mode** helps MySQL reject many invalid values rather than silently modifying them. The two primary modes are `STRICT_TRANS_TABLES` and `STRICT_ALL_TABLES`. For most transactional applications using InnoDB, strict mode is an essential foundation for catching data errors early. However, it does not replace application-level validation, business checks, or reconciled data import workflows.

## 1. How SQL Mode Affects MySQL Data Handling

`sql_mode` is a system variable containing a list of modes that control SQL syntax and several data-handling rules. Besides strict mode, the list can include modes such as `ONLY_FULL_GROUP_BY`, `NO_ZERO_DATE`, `NO_ZERO_IN_DATE`, `ERROR_FOR_DIVISION_BY_ZERO`, and `NO_ENGINE_SUBSTITUTION`.

Strict mode focuses on invalid or missing values when writing data. For example:

- Strings longer than the limit of `VARCHAR(n)`.
- Numeric values outside the range of the column type.
- Strings that cannot be converted into the numeric type required by the column.
- Invalid date/time values or missing required values.
- Omitting a value for a `NOT NULL` column with no default.

When strict mode applies, MySQL typically returns an error and rejects the value. When strict mode does not apply, MySQL may adjust the value to the closest permitted form, store that value, and emit a warning. Exact behavior also depends on the error type and statement context.

## 2. Checking the Current SQL Mode

SQL mode has global and session scopes. Check both:

```sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;
```

Or:

```sql
SHOW GLOBAL VARIABLES LIKE 'sql_mode';
SHOW SESSION VARIABLES LIKE 'sql_mode';
```

- `GLOBAL` is the default value applied to new connections.
- `SESSION` is the mode list of the current connection; it affects statements executed within that session.

An application using a connection pool may hold multiple connections created at different times. If the global configuration changes, existing connections do not automatically pick up the full new session state. Therefore, check `@@SESSION.sql_mode` from the exact connection the application is using.

The default value of `sql_mode` varies across MySQL versions and distributions. Do not assume development, staging, and production share the same mode list; inspect and manage configurations explicitly.

## 3. STRICT_TRANS_TABLES and STRICT_ALL_TABLES

The two strict modes differ mainly in how they handle non-transactional tables:

| Scenario | `STRICT_TRANS_TABLES` | `STRICT_ALL_TABLES` |
| --- | --- | --- |
| A transactional table like InnoDB encounters an invalid value | The statement errors; changes from the statement are rolled back | The statement errors; changes from the statement are rolled back |
| A non-transactional table encounters an error on the first row | The statement errors | The statement errors |
| A non-transactional table encounters an error on a subsequent row in a multi-row statement | MySQL may adjust the invalid value and continue with a warning | The statement stops at the error; previously written rows may remain |

`STRICT_TRANS_TABLES` is suitable for systems primarily using InnoDB. `STRICT_ALL_TABLES` enforces stricter rules on non-transactional tables, though it cannot roll back rows already written by a non-transactional engine before the error occurred.

For InnoDB, a strict error in a multi-row statement rolls back the changes made by that statement; this does not necessarily mean the entire transaction containing the statement is rolled back. The application must handle the error and decide whether to continue or roll back the transaction based on business logic.

## 4. Example: String Longer Than Column Limit

Create a test table:

```sql
CREATE TABLE strict_text_demo (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code VARCHAR(5) NOT NULL,
    note VARCHAR(100) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Insert a value longer than 5 characters:

```sql
INSERT INTO strict_text_demo (code, note)
VALUES ('MYSQL2026', 'Value exceeds code column limit');
```

When the session has strict mode enabled, MySQL returns an error like `Data too long for column 'code'` and does not insert the row. If strict mode does not apply, MySQL may truncate the string to what fits the column and emit a warning. A truncated value can lose information and even collide with another record's code.

Inspect immediately after the operation:

```sql
SHOW WARNINGS;
SELECT * FROM strict_text_demo;
```

If the statement failed, the table has no new row. If MySQL accepted the value after adjustment, `SHOW WARNINGS` helps detect the warning and `SELECT` shows the actual stored data.

## 5. Example: Out-of-Range or Unconvertible Numeric Values

Consider a table with an unsigned integer column:

```sql
CREATE TABLE strict_number_demo (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    quantity INT UNSIGNED NOT NULL,
    amount DECIMAL(8, 2) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Some problematic inputs:

```sql
-- Negative number is outside the range of INT UNSIGNED
INSERT INTO strict_number_demo (quantity, amount)
VALUES (-3, 10.00);

-- String is not a valid numeric representation
INSERT INTO strict_number_demo (quantity, amount)
VALUES ('many', 10.00);
```

In strict mode, invalid values typically cause the statement to fail. When strict mode does not apply, MySQL may adjust the value to a valid boundary or substitute value while emitting a warning. Do not rely on implicit type coercion to interpret data from files or APIs.

For `DECIMAL(p,s)`, distinguish between an out-of-range value and a value with more decimal digits than the scale. Out-of-range values may be rejected in strict mode or adjusted with a warning in permissive mode. Values whose fractional part exceeds the scale may be rounded according to MySQL's conversion rules; verify the result and warnings on your target version rather than assuming every case is truncated the same way.

## 6. Example: Invalid Dates and Times

Dates and times have their own validation rules. For example:

```sql
CREATE TABLE strict_date_demo (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_date DATE NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

INSERT INTO strict_date_demo (event_date)
VALUES ('2026-02-31');
```

February 31 is not a valid calendar date. With strict configuration and the corresponding date modes, MySQL rejects the value. In a permissive configuration or with a relaxed mode such as `ALLOW_INVALID_DATES`, some date values may be accepted or adjusted. `ALLOW_INVALID_DATES` only performs basic range checks on the month and day, without verifying whether the day exists in that specific month.

The `NO_ZERO_DATE` and `NO_ZERO_IN_DATE` modes control acceptance of all-zero dates or zero day/month components. They interact with strict mode, and their deprecation/recommendation status may vary by version. For business data, use valid dates, `NULL` when the date is unknown if the schema allows, or a separate status value; avoid using `0000-00-00` to represent "no date".

## 7. How Do Warnings and Errors Differ?

When a write statement finishes, MySQL can return both an affected row count and a warning count. Read both instead of only checking whether the statement returned success.

```sql
INSERT IGNORE INTO strict_text_demo (code, note)
VALUES ('TOO-LONG-CODE', 'Testing warnings during data write');

SHOW COUNT(*) WARNINGS;
SHOW WARNINGS;
```

In this example, `IGNORE` can cause a length error to be downgraded to a warning and the `code` value to be truncated to fit `VARCHAR(5)`. This is why you should read diagnostics immediately after the write statement and inspect the actual values in the table.

`SHOW WARNINGS` must be executed immediately after the statement being checked, before running another statement that alters the diagnostics area. The output contains the columns `Level`, `Code`, and `Message`; `Level` can be `Warning`, `Note`, or `Error`.

Some common error/warning codes:

| Code | Common Meaning | What to Do |
| ---: | --- | --- |
| `1264` | Numeric value out of range | Check the type, value range, and source data |
| `1265` | Data adjusted/truncated during conversion | Check length, type, and warnings |
| `1366` | Value has incorrect format for column type | Check input data and conversion |
| `1406` | Data too long for column | Adjust data or justify schema limit changes |
| `1292` | Incorrect value format during conversion, common with numbers/dates | Check format and parsing logic |

Specific codes and messages can depend on the statement, version, and column type. Read both `Code` and `Message`; do not write handling logic relying solely on a fixed message string.

## 8. IGNORE Can Make Strict Mode Less Strict

`INSERT IGNORE` and `UPDATE IGNORE` can downgrade certain errors into warnings so that the statement continues. For invalid values, MySQL may adjust to the closest accepted value or skip the row depending on the error type.

Example:

```sql
INSERT IGNORE INTO strict_text_demo (code, note)
VALUES ('TOO-LONG-CODE', 'Testing IGNORE');

SHOW WARNINGS;
SELECT * FROM strict_text_demo;
```

Even when the session has strict mode enabled, `IGNORE` can downgrade a length error to a warning and truncate the string to fit the column. Thus, `IGNORE` is not a safe way to "ignore unimportant errors". It can allow corrupted data to be saved while the pipeline still reports success.

Only use `IGNORE` when handling for each error type is clearly defined, warnings and inserted/updated/skipped row counts are inspected, and reconciliation with source data is possible. If the goal is solely to avoid duplicate key errors, consider explicit conflict handling such as `ON DUPLICATE KEY UPDATE` instead of masking all error types with `IGNORE`.

## 9. STRICT Mode and LOAD DATA

When loading CSV or text files, `LOAD DATA` is also affected by SQL mode and `IGNORE`/`REPLACE` options. Malformed, oversized, or unconvertible data can trigger errors or warnings depending on the mode and statement.

Example of loading a file into a target table:

```sql
LOAD DATA LOCAL INFILE '/path/to/customers.csv'
INTO TABLE strict_text_demo
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
(code, note);
```

File paths, `LOCAL INFILE` permissions, client/server configuration, and file formats must be adjusted for the environment. After loading, check the row count, warnings, and actual data:

```sql
SHOW COUNT(*) WARNINGS;
SHOW WARNINGS LIMIT 50;
SELECT COUNT(*) FROM strict_text_demo;
```

Do not load untrusted data directly into business tables just because `LOAD DATA` is fast. For external files, a safe workflow typically loads into a staging table, validates formats and value ranges, isolates failing rows, and only then moves valid rows into the main table.

## 10. Scope of SQL Mode Changes

### 10.1. Changing in the Session

You can set modes for the current connection:

```sql
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';

SELECT @@SESSION.sql_mode;
```

The command above replaces the session's entire mode list with the specified list. It is a minimal illustrative example and should not be copied into an application if the project needs other modes such as `ONLY_FULL_GROUP_BY`. Before changing, read the current list and construct the complete target list.

Session changes only persist for that connection. When a connection pool creates a new connection, the session receives the global value at creation time or the session configuration initialized by the application.

### 10.2. Changing Globally

An administrator can change the default value for new connections:

```sql
SET GLOBAL sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';

SELECT @@GLOBAL.sql_mode;
```

This command also replaces the entire global mode list. Existing sessions do not automatically update. Required privileges depend on the MySQL version; modern versions use system variable administration privileges such as `SYSTEM_VARIABLES_ADMIN` for this operation.

`SET GLOBAL` does not guarantee that the configuration survives a restart. To persist long-term, use an option file or the persist mechanism of a supported version.

### 10.3. Persist or Option File

On MySQL 8.0 supporting `SET PERSIST`, you can save the global value to apply after restarts:

```sql
SET PERSIST sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
```

Or configure it in the server option file:

```ini
[mysqld]
sql-mode=STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION
```

The examples above intentionally list only two modes for readability; in production systems, merge with all modes required by the version and application. When using a managed database, configuration may reside in a parameter group or the provider's management tool.

After changing, check `@@GLOBAL.sql_mode`, create a new connection, and verify `@@SESSION.sql_mode` from that connection. With connection pools, recycle or reinitialize connections according to your deployment procedure to ensure sessions receive the desired configuration.

## 11. Practical Example of Testing STRICT_TRANS_TABLES

In a lab environment, record the current mode before testing:

```sql
SELECT @@SESSION.sql_mode;
```

Set minimal strict mode for the lab session:

```sql
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
```

Attempt to insert an overly long string:

```sql
INSERT INTO strict_text_demo (code, note)
VALUES ('LONGER-THAN-FIVE', 'Testing strict mode');
```

Observe the error and inspect the table:

```sql
SELECT * FROM strict_text_demo;
```

Then try `INSERT IGNORE` and read the warnings right after the statement. Compare the result with a normal insert. Finally, restore the original SQL mode in the session using the value recorded in the first step, or close the lab connection.

Do not run commands that change global SQL mode in shared environments just for experimentation. The lab only needs session-level changes.

## 12. Safe Data Ingestion Workflow

When receiving data from APIs, CSVs, legacy systems, or users, follow these steps:

1. **Define the data contract:** types, lengths, value ranges, timezones, date/time formats, and `NULL` semantics.
2. **Validate at the boundary:** validate data against the contract before writing to the database.
3. **Use strict mode:** so MySQL rejects any remaining invalid conversions.
4. **Prefer explicit conversions:** use `CAST`, `CONVERT`, `STR_TO_DATE`, or validated normalization logic; do not rely on implicit casting.
5. **Separate raw data:** load untrusted files into a staging table with sufficiently wide columns or appropriate text types.
6. **Quarantine invalid rows:** record the reason, source line, and offending value; do not silently drop data.
7. **Transfer valid rows:** insert into business tables using controlled statements and transactions when appropriate.
8. **Reconcile:** compare input, valid, rejected, inserted, and updated row counts.
9. **Keep an audit trail:** record the schema version, SQL mode, source file, and import timestamp.

Example of a simple staging table:

```sql
CREATE TABLE customer_import_stage (
    source_row BIGINT UNSIGNED NOT NULL,
    raw_email TEXT,
    raw_age TEXT,
    raw_created_at TEXT,
    PRIMARY KEY (source_row)
) ENGINE=InnoDB;
```

After loading data, you can find age values that do not convert to valid numbers:

```sql
SELECT source_row, raw_age
FROM customer_import_stage
WHERE raw_age IS NOT NULL
  AND TRIM(raw_age) <> ''
  AND TRIM(raw_age) NOT REGEXP '^[0-9]+$';
```

With MySQL 8.0, you can use `REGEXP_LIKE` instead of the `REGEXP` operator to express the condition more clearly. Checking the format before `CAST` helps prevent an invalid string from turning into 0 or another unintended value.

## 13. Handling Invalid Data with Explicit Conversion

Do not write raw data directly into strictly typed columns without confirming the format. For example, if dates in a file are formatted as `DD/MM/YYYY`, parse them with `STR_TO_DATE` using an explicit format:

```sql
SELECT
    source_row,
    raw_created_at,
    STR_TO_DATE(raw_created_at, '%d/%m/%Y') AS parsed_date
FROM customer_import_stage;
```

Then check for `NULL` results, warnings, and valid date rules before inserting. Do not rely solely on `STR_TO_DATE` returning a value; verify that the input data matches the expected format and is not normalized in an unintended business way.

For decimal numbers, you can use `CAST` after validating separators and value ranges. CSV files may use commas as decimal points or thousands separators; normalize the format before parsing. Do not blindly use `REPLACE()` because a comma could be a decimal separator in one source and a column delimiter in another.

## 14. Checking Warnings and Reconciling in the Application

Applications should treat warnings as signals requiring inspection for critical write flows. Depending on the driver, warnings can be retrieved via SQL statements or corresponding API diagnostics.

A minimal post-import check:

```sql
SHOW COUNT(*) WARNINGS;
SHOW WARNINGS LIMIT 100;
```

Run this immediately after the write statement being checked. For multi-batch imports, collect warnings and row counts per batch; do not only check the warnings of the final batch.

Reconcile at least the following metrics:

| Metric | Meaning |
| --- | --- |
| Rows received | Number of source rows received |
| Rows validated | Number of rows passing format and business validation |
| Rows rejected | Number of rows rejected, with reasons |
| Rows inserted | Number of newly inserted rows |
| Rows updated | Number of updated rows |
| Warnings | Count and types of warnings emitted by MySQL |

If the system only records that a statement succeeded without checking warnings or row counts, truncated data can slip through the pipeline undetected.

## 15. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| Enabling strict mode rejects all invalid data in every case | `IGNORE`, certain statements, and storage engine differences can alter behavior |
| `STRICT_TRANS_TABLES` and `STRICT_ALL_TABLES` are identical | Important differences arise with non-transactional tables and multi-row statements |
| Warnings do not matter if the statement succeeds | Warnings can indicate that data was truncated, coerced, or adjusted |
| InnoDB rolls back the entire transaction when a statement hits a strict error | Typically the statement is rolled back; the application decides how to handle the transaction next |
| `INSERT IGNORE` only skips duplicate keys | It can also downgrade many data errors to warnings and adjust values |
| No errors means the data is valid per business rules | MySQL only checks types, constraints, and modes; business rules still require validation |
| Changing global configuration updates all connections immediately | Existing sessions keep their own session state |

## 16. Practice Exercises

1. Create an InnoDB table with `VARCHAR(5)`, `INT UNSIGNED`, and `DATE`; try inserting a long string, a negative number, and an invalid date in strict mode.
2. Run `SHOW WARNINGS` after an accepted statement that produces warnings; record `Level`, `Code`, and `Message`.
3. Try changing session `sql_mode` to remove strict mode in a lab environment; observe the stored values and warnings. Then restore the original mode.
4. Try `INSERT IGNORE` while strict mode is enabled and explain why the result differs from a normal insert.
5. Compare `STRICT_TRANS_TABLES` and `STRICT_ALL_TABLES` on a non-transactional table in an isolated test environment; inspect the rows written prior to the error.
6. Load a CSV file with valid and invalid rows into a staging table; isolate invalid rows before moving data into the main table.
7. Write queries to validate numeric and date data using explicit expressions/formats before `CAST` or `STR_TO_DATE`.
8. Design an import report covering rows received, validated, rejected, inserted, updated, and warnings.

## 17. Key Takeaways

Strict mode causes MySQL to reject many invalid values rather than automatically adjusting them and emitting warnings. `STRICT_TRANS_TABLES` applies strictly to transactional tables and has specific handling for errors on later rows of multi-row statements on non-transactional tables; `STRICT_ALL_TABLES` stops on error but cannot undo rows already written by a non-transactional engine.

`SHOW WARNINGS` must be read immediately after the write statement. `INSERT IGNORE`, `UPDATE IGNORE`, and some import workflows can downgrade errors to warnings or adjust values, so they should not be used to mask data errors. Manage `sql_mode` intentionally at session/global scope, validate in the application, use explicit conversions, stage raw data, and reconcile both row counts and warnings before considering a write or import successful.
