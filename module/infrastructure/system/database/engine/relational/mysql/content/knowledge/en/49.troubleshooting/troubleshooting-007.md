# Data Too Long, Out of Range, Truncated Values, and Strict Mode

## Objectives

MySQL can reject a statement when data exceeds a column's domain, or convert and truncate values with warnings depending on SQL mode and execution method. Situations like `Data too long`, `Out of range value`, and `Data truncated` often appear during data imports, schema changes, or connecting applications to data sources with different types. If warnings are ignored, the system may store altered data while the application still reports success.

This lesson belongs to the **DATABASE_MYSQL** module, covering table design, data types, keys, SQL, indexes, transactions, concurrency control, reading execution plans, query optimization, and relational database operations. It guides you through reading conversion errors, understanding strict SQL mode, validating value domains before writing, and safely handling imports or column type changes.

After this lesson, you will be able to:

- Distinguish numeric out-of-range errors, overlong strings, and converted/truncated values.
- Inspect `sql_mode` at global and session levels, and understand `STRICT_TRANS_TABLES` alongside `STRICT_ALL_TABLES`.
- Use `SHOW WARNINGS`, error codes, and data validation queries to pinpoint causes.
- Identify the impact of `INSERT IGNORE`, `UPDATE IGNORE`, `LOAD DATA`, and strict mode.
- Clean data in staging, change column types in a controlled way, and protect data with constraints.

## 1. Three Error Categories to Distinguish

| Category | Example | Typical Behavior |
|---|---|---|
| Data too long | Writing a 20-character string into `VARCHAR(8)` | Strict mode usually reports error 1406; non-strict may truncate the string and emit a warning |
| Out of range | Writing `256` into `TINYINT UNSIGNED` or `1000.00` into `DECIMAL(5,2)` | Strict mode usually reports error 1264; non-strict may clamp to the boundary value and emit a warning |
| Data truncated / conversion | Converting an invalid string to a number, date, or another type | May report an error or warning 1265/1366/1292 depending on value, context, and SQL mode |

It is crucial to distinguish a **failed statement** from a **completed statement with warnings**. A statement with warnings may have written values after MySQL truncated, rounded, or replaced them with boundary values. Therefore, checking affected row counts alone is insufficient; check warnings and actual stored data after writing.

## 2. Checking SQL Mode

SQL mode controls how MySQL handles many compatibility and data conversion scenarios. Strict mode is enabled when `sql_mode` includes `STRICT_TRANS_TABLES` or `STRICT_ALL_TABLES`.

Check server and current session configuration:

```sql
SELECT @@GLOBAL.sql_mode AS global_sql_mode,
       @@SESSION.sql_mode AS session_sql_mode;
```

`GLOBAL` is the default value applied to new sessions. `SESSION` is the value active for the current connection. A connection pool may retain sessions created before the global configuration changed; therefore, changing `GLOBAL` does not necessarily update existing connections.

In many MySQL 8.0 releases, default SQL mode includes `STRICT_TRANS_TABLES`, `ONLY_FULL_GROUP_BY`, `NO_ZERO_IN_DATE`, `NO_ZERO_DATE`, `ERROR_FOR_DIVISION_BY_ZERO`, and `NO_ENGINE_SUBSTITUTION`. Some zero-date modes have been deprecated in newer versions; defaults and valid modes depend on the version. Always inspect the instance's actual value and documentation.

### `STRICT_TRANS_TABLES` and `STRICT_ALL_TABLES`

- `STRICT_TRANS_TABLES`: for transactional tables like InnoDB, invalid data causes the statement to error and roll back. For nontransactional tables, behavior may depend on which row in a multi-row statement failed; rows already written cannot be rolled back.
- `STRICT_ALL_TABLES`: enforces strict behavior even for nontransactional storage engines. However, storage engines without rollback support still retain rows written before the error occurred.

In applications using InnoDB, `STRICT_TRANS_TABLES` is usually the right default. Strict mode catches bad data at write time instead of silently altering it. Never disable strict mode server-wide just to get a single import to finish.

## 3. Numeric Type Domains

Numeric types have specific representation ranges. Values outside the range can cause errors or be clamped to boundaries depending on SQL mode.

| Type | Range |
|---|---:|
| `TINYINT` signed | -128 to 127 |
| `TINYINT UNSIGNED` | 0 to 255 |
| `SMALLINT` signed | -32,768 to 32,767 |
| `SMALLINT UNSIGNED` | 0 to 65,535 |
| `INT` signed | -2,147,483,648 to 2,147,483,647 |
| `INT UNSIGNED` | 0 to 4,294,967,295 |
| `BIGINT` signed | -2^63 to 2^63 - 1 |
| `BIGINT UNSIGNED` | 0 to 2^64 - 1 |

`UNSIGNED` expands the positive range while eliminating negative numbers. Do not change a column to `UNSIGNED` solely to raise the upper bound if data or business rules can ever include negative numbers.

### `DECIMAL(M,D)`

`DECIMAL(M,D)` stores exact decimal numbers, where `M` is total digits and `D` is digits after the decimal point. For example, `DECIMAL(5,2)` ranges from `-999.99` to `999.99`.

- `999.99` is within range.
- `1000.00` is out of range because it needs four integer digits.
- `12.345` has more decimal digits than scale 2; MySQL converts according to the target type's rounding rules, so verify the result rather than assuming simple truncation.

For monetary amounts, choose precision/scale per business limits and rounding rules. Never use `FLOAT` or `DOUBLE` in place of exact decimals when financial reconciliation is required.

## 4. Strings Too Long: `VARCHAR`, `CHAR`, and `TEXT`

`VARCHAR(n)` limits by character count, not byte count. With `utf8mb4`, a single character can occupy up to four bytes. Even so, row length and index limits remain governed by byte count, row format, and InnoDB configuration.

Example:

```sql
CREATE TABLE import_probe (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  code VARCHAR(8) CHARACTER SET utf8mb4 NOT NULL
) ENGINE = InnoDB;

INSERT INTO import_probe (code) VALUES ('ABC12345');
```

An 8-character string fits. The string `ABCDEFGHI` has 9 characters and exceeds the limit.

Check data length:

```sql
SELECT code,
       CHAR_LENGTH(code) AS character_count,
       LENGTH(code) AS byte_count
FROM import_probe;
```

`CHAR_LENGTH()` counts characters; `LENGTH()` counts bytes. With Unicode data, the two values can differ substantially. When validating source data before loading into `VARCHAR(n)`, use `CHAR_LENGTH()` to check character limits; use `LENGTH()`/`OCTET_LENGTH()` to evaluate byte size and related storage limits.

If data genuinely needs to be longer, consider widening `VARCHAR(n)` or using an appropriate `TEXT` type. `TEXT` has different capacity tiers (`TINYTEXT`, `TEXT`, `MEDIUMTEXT`, `LONGTEXT`), though practical sizes remain subject to packet, memory, row format, and query constraints. Do not convert every column to `LONGTEXT` to dodge errors, as that weakens the data model and can affect indexing, sorting, memory, and performance.

## 5. Reproducing Errors in Strict Mode

Create a lab table:

```sql
CREATE DATABASE IF NOT EXISTS strict_mode_lab;
USE strict_mode_lab;

CREATE TABLE values_probe (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  qty TINYINT UNSIGNED NOT NULL,
  amount DECIMAL(5,2) NOT NULL,
  code VARCHAR(4) CHARACTER SET utf8mb4 NOT NULL
) ENGINE = InnoDB;
```

Check active mode:

```sql
SELECT @@SESSION.sql_mode;
```

With strict mode enabled, try inserting an out-of-range number:

```sql
INSERT INTO values_probe (qty, amount, code)
VALUES (256, 12.34, 'ABCD');
```

MySQL typically returns error `1264` (`Out of range value`) for `qty`. With InnoDB, the statement fails and adds no row.

Try an overlong string:

```sql
INSERT INTO values_probe (qty, amount, code)
VALUES (10, 12.34, 'ABCDE');
```

MySQL typically returns error `1406` (`Data too long for column 'code'`). No new row is added because the statement failed.

Verify data:

```sql
SELECT * FROM values_probe;
```

## 6. Observing Non-Strict Mode Behavior in a Lab

To understand why warnings are dangerous, you can temporarily change SQL mode in a **dedicated test session**. Save the original mode:

```sql
SET @saved_sql_mode = @@SESSION.sql_mode;
SET SESSION sql_mode = '';
```

Try writing an out-of-range value:

```sql
INSERT INTO values_probe (qty, amount, code)
VALUES (256, 12.34, 'ABCD');

SHOW WARNINGS;
```

In non-strict mode, MySQL clamps `qty` to the boundary value `255` and emits a warning. Inspect the saved value:

```sql
SELECT *
FROM values_probe
ORDER BY id DESC
LIMIT 1;
```

Try an overlong string:

```sql
INSERT INTO values_probe (qty, amount, code)
VALUES (10, 12.34, 'ABCDE');

SHOW WARNINGS;
```

In non-strict mode, MySQL stores the portion of the string that fits the column and emits a warning. The stored value becomes `ABCD` rather than the source string `ABCDE`.

Restore the session mode:

```sql
SET SESSION sql_mode = @saved_sql_mode;
```

This is strictly an experiment to observe conversion behavior. Never use `sql_mode = ''` in production or real data ingestion pipelines.

## 7. `INSERT IGNORE` and `UPDATE IGNORE`

`IGNORE` can downgrade certain data conversion errors into warnings and let the statement continue. Example:

```sql
INSERT IGNORE INTO values_probe (qty, amount, code)
VALUES (300, 10.00, 'TOOLONG');

SHOW WARNINGS;
```

Even with strict mode enabled, `IGNORE` can cause invalid values to be converted to the closest storable value while the statement continues. Understand this behavior thoroughly before using it in imports.

`INSERT IGNORE` can also skip rows violating unique keys or turn other errors into warnings. `UPDATE IGNORE` behaves similarly for convertible errors. Never use `IGNORE` as a way to "skip bad data" without reporting and remediation workflows.

If business rules allow skipping invalid records, save every rejected row, its reason, and source data into a reject/quarantine table so it can be fixed and reprocessed. Never let warnings disappear into application logs.

## 8. Warnings Must Be Read Immediately After the Statement

MySQL provides `SHOW WARNINGS` to view warnings and errors from the most recently executed statement in the current session:

```sql
INSERT INTO values_probe (qty, amount, code)
VALUES (10, 10.00, 'ABCDE');

SHOW COUNT(*) WARNINGS;
SHOW WARNINGS;
```

Run `SHOW WARNINGS` immediately after the statement being inspected, before running any other SQL that might alter the diagnostics list. `SHOW COUNT(*) WARNINGS` shows the recorded warning count; `SHOW WARNINGS` displays level, code, and message. Displayed rows are capped by `max_error_count`, so do not assume every warning appears if a batch produces many errors.

Common error codes:

| Code | Common Meaning | Investigation Path |
|---:|---|---|
| `1406` | Data too long for column | Source length, target type/length, encoding |
| `1264` | Out of range value | Numeric range, signedness, precision/scale |
| `1265` | Data truncated for column | Data conversion or truncation |
| `1366` | Incorrect value for column | String unconvertible to target type or invalid characters |
| `1292` | Incorrect date/time value or conversion | Date/time format, timezone, SQL mode |

Exact codes may vary by context and version; read the full message alongside `SQLSTATE` and column location rather than relying on the code alone.

## 9. Strict Mode with Transactional and Nontransactional Tables

InnoDB supports rollback. When strict mode detects an invalid value in an InnoDB write statement, the statement fails and its changes roll back.

With nontransactional storage engines, already-written data cannot roll back. In a multi-row statement, an error can occur after some rows have already been written. `STRICT_TRANS_TABLES` behaves differently depending on whether the error occurs on the first row or a later row; `STRICT_ALL_TABLES` applies strict behavior across all engines but cannot undo nontransactional data written before the failure.

Therefore:

- Prefer InnoDB for business tables requiring atomicity.
- Do not rely on a single bulk insert statement as an atomic transaction if the table uses a nontransactional engine.
- After an import error, check written row counts and data state; do not look only at the exception.
- Use InnoDB staging tables to validate, normalize, and move data to target tables.

## 10. Invalid Dates/Times and SQL Mode

Dates and times can also be rejected or converted depending on SQL mode and version. Modes historically used to control this include `NO_ZERO_DATE`, `NO_ZERO_IN_DATE`, and `ALLOW_INVALID_DATES`; both zero-date modes have been deprecated in newer MySQL releases. Strict mode also affects how invalid date values are handled.

Values such as `0000-00-00`, dates with zero month/day, or nonexistent calendar dates may produce warnings or rejections depending on mode and version. Never rely on zero dates to represent "unknown"; use `NULL` or an explicit status model.

Before converting date/time data, determine:

- Whether the column is a calendar date (`DATE`), timezone-naive timestamp (`DATETIME`), or timezone-aware instant (`TIMESTAMP`).
- Whether source format and timezone are known.
- Whether zero dates, out-of-calendar dates, or unparseable strings exist.
- Required fractional seconds precision (0 to 6 digits).

Example mode and data check:

```sql
SELECT @@SESSION.sql_mode;

SELECT COUNT(*) AS zero_date_rows
FROM source_stage
WHERE date_text IN ('0000-00-00', '0000-00-00 00:00:00');
```

In ETL, parse dates/times during the staging step using explicit rules, log parse errors to a reject table, and load only valid values into the target column.

## 11. Validating Data Before Writing

Do not wait for `INSERT` to fail to discover out-of-range data. Before loading, run validation queries matching target column types.

Example for source data destined for `TINYINT UNSIGNED`:

```sql
SELECT source_id, qty
FROM source_stage
WHERE qty IS NULL
   OR qty < 0
   OR qty > 255;
```

Check values for `DECIMAL(5,2)`:

```sql
SELECT source_id, amount
FROM source_stage
WHERE amount < -999.99
   OR amount > 999.99;
```

Check string length for target `VARCHAR(4)`:

```sql
SELECT source_id, code, CHAR_LENGTH(code) AS char_count
FROM source_stage
WHERE CHAR_LENGTH(code) > 4;
```

Also check `NULL`s, empty strings, and whitespace per business rules. If the target column is `NOT NULL`, find all source rows missing values before loading. Never replace `NULL` with `0`, an empty string, or a default date unless explicitly defined by business rules.

## 12. Using Staging and Quarantine for Imports

A safe pipeline typically has three zones:

1. **Raw/staging:** preserves source values in sufficiently wide types, usually strings or lossless types during extraction.
2. **Validated/normalized:** converts using explicit rules, recording valid values and validation errors.
3. **Target:** business tables with official data types, constraints, and indexes.

Example staging table:

```sql
CREATE TABLE stg_measurements (
  source_id VARCHAR(64) NOT NULL,
  qty_text VARCHAR(100),
  amount_text VARCHAR(100),
  code_text TEXT,
  source_row_number BIGINT
) ENGINE = InnoDB;
```

Preserving source data before casting enables investigation and replay. During normalization, split valid and invalid rows into separate sets. The quarantine table should store source ID, raw value, column name, error code, message, and processing timestamp.

Do not rely on `CAST()` as the sole safety filter. Some casts emit warnings or substitute values; validate format and range before casting, and inspect diagnostics from the conversion step.

## 13. Loading Data with `LOAD DATA`

`LOAD DATA [LOCAL] INFILE` can speed up CSV loading, but it remains subject to type conversion rules, SQL mode, and import settings.

```sql
LOAD DATA LOCAL INFILE 'measurements.csv'
INTO TABLE stg_measurements
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(source_id, qty_text, amount_text, code_text);

SHOW COUNT(*) WARNINGS;
SHOW WARNINGS;
```

`LOCAL` reads files from the client side and must be permitted by both client and server configuration. Enable it only when security policy allows. CSV files must clearly specify delimiter, quote, escape, newline, encoding, and `NULL`/empty-string representation.

For production imports, load into staging first, inspect warnings and row counts, and only then move data into target tables. `LOAD DATA` can handle errors and continue under options like `IGNORE` or `REPLACE`; understand their impact before use because they can skip or overwrite rows.

## 14. Altering the Schema When Data Genuinely Needs a Larger Domain

If data is valid per business rules yet does not fit the column type, altering the schema may be the right fix. Before running `ALTER TABLE`, determine:

- Actual min/max range and projected future range.
- Applications, APIs, ORMs, ETL jobs, and reports relying on the old type.
- Indexes, foreign keys, generated columns, and views depending on the column.
- Storage, lock/DDL duration, and replication impact.
- Rollback plan if the type change cannot be reversed safely.

Example widening a column's length:

```sql
ALTER TABLE customers
  MODIFY external_code VARCHAR(32)
  CHARACTER SET utf8mb4
  NOT NULL;
```

Example changing a numeric type requires evaluating existing data first:

```sql
ALTER TABLE inventory
  MODIFY quantity INT UNSIGNED NOT NULL;
```

Never run `ALTER TABLE` before confirming there are no negative values, `NULL`s, or values outside the new domain. Type changes may require a table rebuild, generate heavy I/O, or impact availability depending on version and alteration type.

## 15. Data Constraints to Prevent Recurrence

Application validation provides early feedback, while the database needs constraints to guard data against all writers.

Example:

```sql
CREATE TABLE inventory_safe (
  sku VARCHAR(32) NOT NULL PRIMARY KEY,
  quantity INT UNSIGNED NOT NULL,
  unit_price DECIMAL(10,2) NOT NULL,
  code VARCHAR(12) NOT NULL,
  CONSTRAINT chk_quantity_nonnegative CHECK (quantity >= 0),
  CONSTRAINT chk_unit_price_nonnegative CHECK (unit_price >= 0)
) ENGINE = InnoDB;
```

MySQL enforces `CHECK` constraints starting in version 8.0.16. Older versions parse them without enforcing constraints in the modern sense. Check your version before relying on `CHECK` for data protection.

Data types and column lengths provide baseline bounds; `CHECK` adds business rules such as non-negativity, percentage ranges, or allowed domain values. Constraints do not replace import error-handling pipelines.

## 16. Error Handling in JDBC Applications

Java applications must distinguish exceptions from warnings. For `SQLException`, record error code, `SQLState`, and sanitized message. For completed statements with warnings, read `SQLWarning` when provided by the driver:

```java
try (PreparedStatement statement = connection.prepareStatement(
        "INSERT INTO values_probe(qty, amount, code) VALUES (?, ?, ?)")) {
    statement.setInt(1, qty);
    statement.setBigDecimal(2, amount);
    statement.setString(3, code);

    int affectedRows = statement.executeUpdate();
    for (SQLWarning warning = statement.getWarnings();
         warning != null;
         warning = warning.getNextWarning()) {
        // Record each warning code/message and flag the record for review.
    }
} catch (SQLException exception) {
    int errorCode = exception.getErrorCode();
    String sqlState = exception.getSQLState();
    // Classify data error; do not retry as a transient network error.
}
```

For out-of-range or overlong data, retrying the same payload will continue failing or continue mutating data. Return contextual validation errors, quarantine the record, or request source data correction.

Do not log full payloads if they contain personal data, tokens, or sensitive fields. Log source ID, column name, error code, and masked values when investigating.

## 17. Troubleshooting Checklist

When encountering `Data too long`, `Out of range`, or `Data truncated`, proceed in order:

1. Capture error code, `SQLState`, message, table/column name, and sanitized statement.
2. Check `@@SESSION.sql_mode` on the exact failing connection; do not look only at global mode.
3. Read column data type, signed/unsigned, precision/scale, charset/collation, and length.
4. Check source values using `CHAR_LENGTH`, `LENGTH`, min/max, and range predicates.
5. If the statement produced warnings, run `SHOW WARNINGS` immediately in the same session.
6. Identify whether the engine is transactional or nontransactional and check for partially written rows.
7. Inspect `IGNORE`, `LOAD DATA`, casts, or implicit conversions in the pipeline.
8. Decide whether to fix data, widen the schema, or reject records per business rules.
9. Reload from staging, and reconcile row counts and actual written values.
10. Keep strict mode enabled in production and add validation/monitoring to prevent recurrence.

## 18. Common Mistakes

- **Disabling strict mode so imports run:** data can be truncated or clamped to boundary values. Keep raw data, fix mappings, and reload under strict mode.
- **Checking only inserted row count:** the statement may succeed with warnings and altered values. Check warnings and target data.
- **Confusing characters with bytes:** `VARCHAR(n)` limits characters, while bytes affect row size and index limits. Use `CHAR_LENGTH` and `LENGTH` appropriately.
- **Using `UNSIGNED` without checking:** negative data gets rejected or clamped to 0 depending on mode. Verify business domain before changing types.
- **Using `INSERT IGNORE` to hide errors:** records may be truncated or skipped. Log warnings and quarantine invalid data.
- **Checking only global SQL mode:** connection pools may hold sessions with older modes. Check the active session and recycle pools after config changes.
- **Arbitrarily widening columns:** increases storage, index size, and complexity without fixing bad source data. Pick types matching business domains.
- **Editing data directly without raw copies:** makes it hard to recover original values. Keep staging and source audits.

## 19. Practice Exercises

On a test MySQL instance:

1. Create `values_probe` with `TINYINT UNSIGNED`, `DECIMAL(5,2)`, and `VARCHAR(4)`.
2. Enable strict mode in the session and try inserting `qty=256`, `amount=1000.00`, and a 5-character string; record the errors.
3. Temporarily disable strict mode only in the lab session, repeat the inserts, and read `SHOW WARNINGS`; inspect the values actually stored.
4. Try `INSERT IGNORE` with strict mode enabled and compare warnings against a regular insert.
5. Load multi-byte Unicode strings; compare `CHAR_LENGTH()` and `LENGTH()`.
6. Create a staging table, locate out-of-range rows via validation queries, and isolate them into a quarantine table.
7. Widen a column or adjust a type after proving data validity; verify schema and data after `ALTER TABLE`.
8. Write a JDBC test that reads `SQLWarning` and classifies `SQLException` by error code/`SQLState`.

**Completion criteria:** you can explain the difference between errors and warnings, predict the effect of strict mode, pinpoint truncated/clamped values, and design a data ingestion pipeline that never silently corrupts data.

## Conclusion

`Data too long`, `Out of range`, and `Data truncated` signal mismatches among source data, column types, or conversion rules. Check SQL mode on the exact session, read warnings right after the statement, verify numeric ranges and string lengths, and process data through staging before writing to business tables. Keep strict mode enabled, use InnoDB, and enforce clear constraints and validation to catch bad data at the source instead of silently mutating values.
