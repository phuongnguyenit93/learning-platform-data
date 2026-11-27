# Division Rules, Overflow, and Invalid Date/Time Data

MySQL does not only check data types when creating tables. While executing statements, the server also has to handle arithmetic, type conversions, and verify whether values fall within valid ranges. A division by zero, an addition overflowing BIGINT, or a nonexistent date can return NULL, emit a warning, be rejected with an error, or be adjusted depending on the context and SQL mode.

SQL mode is a set of modes that alter how MySQL parses and handles SQL. They can affect division by zero, out-of-range numeric values, invalid dates/times, missing data, or malformed data. Consequently, the same statement can produce different results between two environments if their SQL mode configurations differ.

This article focuses on MySQL 8.x and the InnoDB storage engine. When operating real systems, verify the server version, the SQL mode of the exact session, and the target data types before drawing conclusions about behavior.

## 1. SQL Mode Governs Execution Semantics

SQL mode is a list of modes enabled for the server or for a session. Some modes affect syntax, while others affect data validation and error handling.

Two common scopes:

- **GLOBAL**: the default value new connections receive when creating a session.
- **SESSION**: the value currently applied to the current connection.

Check configuration:

~~~sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;
~~~

Or:

~~~sql
SHOW SESSION VARIABLES LIKE 'sql_mode';
~~~

When GLOBAL changes, already open connections do not automatically switch their session mode. This is especially important with connection pools: a connection may keep the SQL mode it received when created or one modified by the application.

You can set it for a test session:

~~~sql
SET SESSION sql_mode =
    'STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO';
~~~

The command above replaces the session's entire mode list with just the two modes listed. In production applications, do not copy this example mechanically because it could accidentally drop other needed modes. Read the current value, define the desired policy, and manage configuration consistently across development, testing, and production environments.

## 2. Division by Zero

### 2.1. Standard Division

MySQL supports division `/`, integer division `DIV`, and remainder `MOD()`. When the denominator is 0, the operation cannot produce a finite numeric result under ordinary rules.

Example:

~~~sql
SELECT 10 / 0;
SELECT 10 DIV 0;
SELECT MOD(10, 0);
~~~

In MySQL, division by zero generally evaluates to NULL and may emit a warning. Whether a warning or an error occurs depends on SQL mode and statement context. For a SELECT query, the result is typically NULL with a warning when ERROR_FOR_DIVISION_BY_ZERO is enabled; if this mode is off, the operation may return NULL without a warning.

ERROR_FOR_DIVISION_BY_ZERO has been marked deprecated in modern MySQL releases. Although it may still appear in compatibility configurations and defaults of some releases, check the documentation for your exact version and rely on strict mode alongside explicit data checks for new policies.

Inspect immediately after the statement:

~~~sql
SHOW WARNINGS;
SELECT @@warning_count;
~~~

Run SHOW WARNINGS immediately after the statement being checked, because any subsequent statement can alter the current warning list.

### 2.2. When Division Appears in INSERT or UPDATE

Division by zero inside write statements must be evaluated alongside SQL mode:

- When ERROR_FOR_DIVISION_BY_ZERO is enabled, MySQL may emit a warning for division by zero.
- When combined with strict mode, division by zero in INSERT or UPDATE can cause the statement to fail.
- With INSERT IGNORE or UPDATE IGNORE, certain errors are downgraded to warnings and the statement may continue with a fallback value or NULL depending on the expression, target column, and constraints.

Example on a test table:

~~~sql
CREATE TEMPORARY TABLE division_demo (
    numerator   DECIMAL(12, 2) NOT NULL,
    denominator DECIMAL(12, 2) NOT NULL,
    result      DECIMAL(12, 4) NULL
);

INSERT INTO division_demo (numerator, denominator, result)
VALUES (10, 0, 10 / 0);
~~~

The outcome of the INSERT depends on the current SQL mode. If the statement fails, examine the returned error and the session's SQL mode. If the statement succeeds with warnings, check the actual stored values in the table and the warnings immediately afterward.

Do not rely on MySQL's implicit behavior to decide business outcomes when the denominator is 0. The application should explicitly define whether it is invalid data, an undefined result, or a case to skip.

### 2.3. Preventing Zero Denominators with NULLIF

A safe way to avoid division by zero is using NULLIF:

~~~sql
SELECT numerator / NULLIF(denominator, 0) AS ratio
FROM division_demo;
~~~

NULLIF(a, b) returns NULL if both values are equal; otherwise, it returns a. Thus, when denominator is 0, the divisor becomes NULL and the division evaluates to NULL instead of performing division by zero.

If business logic needs a default value, you can use COALESCE, but choose a meaningful default:

~~~sql
SELECT COALESCE(
    numerator / NULLIF(denominator, 0),
    0
) AS ratio_or_zero
FROM division_demo;
~~~

Use 0 only if business logic genuinely defines a zero denominator as equivalent to a ratio of 0. In many cases, NULL means "undefined" and is completely different from the number 0.

Another option is CASE:

~~~sql
SELECT
    CASE
        WHEN denominator = 0 THEN NULL
        ELSE numerator / denominator
    END AS ratio
FROM division_demo;
~~~

### 2.4. Distinguishing /, DIV, and MOD

| Expression | Meaning | Example with 10 and 3 |
|---|---|---|
| 10 / 3 | Arithmetic division, with fractional part | 3.3333... |
| 10 DIV 3 | Integer division | 3 |
| MOD(10, 3) | Remainder | 1 |

The scale of the `/` division result is also affected by the `div_precision_increment` variable:

~~~sql
SHOW SESSION VARIABLES LIKE 'div_precision_increment';
~~~

The default value is typically 4. It controls the number of decimal digits added to the scale of a division result; if business logic requires specific precision, explicitly cast or round instead of relying on the default.

Example:

~~~sql
SELECT
    10 / 3 AS default_division,
    CAST(10 / 3 AS DECIMAL(12, 4)) AS fixed_scale,
    ROUND(10 / 3, 2) AS rounded_value;
~~~

ROUND() rounds the result to the specified number of digits. Do not confuse displaying fewer digits with storing exact decimal precision.

## 3. Overflow and Out-of-Range Values

### 3.1. Ranges of Integer Types

Integer types have specific limits. The UNSIGNED attribute shifts the range to non-negative values and increases the positive upper bound.

| Type | Minimum Signed | Maximum Signed | Maximum Unsigned |
|---|---:|---:|---:|
| TINYINT | -128 | 127 | 255 |
| SMALLINT | -32,768 | 32,767 | 65,535 |
| MEDIUMINT | -8,388,608 | 8,388,607 | 16,777,215 |
| INT | -2,147,483,648 | 2,147,483,647 | 4,294,967,295 |
| BIGINT | -9,223,372,036,854,775,808 | 9,223,372,036,854,775,807 | 18,446,744,073,709,551,615 |

If an assigned value exceeds the target column's range, MySQL handles it differently depending on strict mode, IGNORE, and conversion context.

### 3.2. Strict Mode and Numeric Columns

With InnoDB tables, strict mode generally causes an INSERT or UPDATE with out-of-range values to be rejected rather than silently adjusted. When strict mode is disabled, MySQL may clamp the value to the nearest boundary and emit a warning.

Example:

~~~sql
CREATE TEMPORARY TABLE tinyint_demo (
    value TINYINT NOT NULL
);

INSERT INTO tinyint_demo (value) VALUES (200);
~~~

200 exceeds the signed TINYINT limit of 127. In strict mode, the INSERT usually fails with an out-of-range error. In non-strict mode, the server may store the boundary value 127 and emit a warning. Inspect the actual stored value rather than assuming data was stored intact.

With multi-row statements, strict mode and the storage engine also affect rollback scope. InnoDB is a transactional engine, so when one row causes a statement to fail, the entire statement can be rolled back. With non-transactional storage engines, some rows may already have been written before the error occurs, depending on strict mode and processing order.

### 3.3. IGNORE Changes Error Reporting

INSERT IGNORE and UPDATE IGNORE can downgrade certain data errors into warnings so the statement continues. This does not mean out-of-range values are stored intact. MySQL may adjust the value or use NULL/default depending on the situation.

Example:

~~~sql
INSERT IGNORE INTO tinyint_demo (value)
VALUES (200);

SHOW WARNINGS;

SELECT value FROM tinyint_demo;
~~~

Only use IGNORE when business logic accepts a policy of skipping or adjusting data. Do not use it to mask input validation errors or make a migration "pass" without verifying results.

## 4. Overflow in Arithmetic Expressions

Overflow can occur directly inside a SELECT expression, before the result is even assigned to a column. For instance, arithmetic on UNSIGNED values can produce a negative result or exceed the representable range.

~~~sql
SELECT CAST(0 AS UNSIGNED) - 1;
~~~

By default, subtraction involving UNSIGNED operands can be evaluated using unsigned arithmetic. If the result is negative, MySQL may raise an unsigned out-of-range error.

The NO_UNSIGNED_SUBTRACTION SQL mode changes subtraction behavior: results of subtraction with unsigned operands are handled in signed fashion so negative numbers can be represented when appropriate.

~~~sql
SET SESSION sql_mode =
    CONCAT_WS(',', @@SESSION.sql_mode, 'NO_UNSIGNED_SUBTRACTION');

SELECT CAST(0 AS UNSIGNED) - 1;
~~~

The SET statement above appends the mode to the session's current list. If the session already has this mode, the string could contain duplicate names; in production configurations, manage the mode list explicitly.

NO_UNSIGNED_SUBTRACTION affects subtraction semantics; it does not allow an UNSIGNED column to store negative numbers. If a negative result is written into an UNSIGNED column, the operation can still fail or be adjusted depending on SQL mode.

### 4.1. Overflow in DECIMAL

DECIMAL uses exact decimal arithmetic and is suited for monetary data. MySQL supports a maximum precision of 65 digits and a maximum scale of 30 digits. When a result or assigned value exceeds the target type's precision/scale, the server may raise an error or emit a warning and adjust depending on strict mode, the operation, and context.

Example:

~~~sql
CREATE TEMPORARY TABLE decimal_demo (
    amount DECIMAL(5, 2) NOT NULL
);

INSERT INTO decimal_demo (amount)
VALUES (12345.67);
~~~

DECIMAL(5,2) has only 5 total digits, including 2 digits after the decimal point; the integer part can have at most 3 digits. The value 12345.67 cannot be represented in this column.

When designing monetary columns, calculate the maximum value range and decimal places according to business requirements. Do not pick DECIMAL(10,2) merely because it is a common example.

### 4.2. FLOAT and DOUBLE

FLOAT and DOUBLE use approximate floating-point representations. They have different value ranges and rounding characteristics than DECIMAL. Arithmetic operations can introduce representation inaccuracies even when no overflow occurs.

Example:

~~~sql
SELECT
    0.1 + 0.2 AS approximate_result,
    CAST(0.1 AS DECIMAL(3, 1))
      + CAST(0.2 AS DECIMAL(3, 1)) AS decimal_result;
~~~

When handling currency, ratios requiring explicit rounding rules, or exact comparisons by decimal places, prefer DECIMAL. FLOAT/DOUBLE are better suited for scientific data or calculations that tolerate approximate precision.

## 5. Arithmetic on UNSIGNED Numbers

UNSIGNED is useful for counters, identifiers, and non-negative quantities. However, arithmetic on UNSIGNED can cause surprises when an intermediate result needs to be negative.

Inventory example:

~~~sql
CREATE TEMPORARY TABLE inventory_demo (
    product_id BIGINT UNSIGNED NOT NULL,
    quantity   INT UNSIGNED NOT NULL,
    PRIMARY KEY (product_id)
);

INSERT INTO inventory_demo VALUES (1, 3);

UPDATE inventory_demo
SET quantity = quantity - 5
WHERE product_id = 1;
~~~

If the subtraction produces a negative result, MySQL may raise an out-of-range error. Do not expect an UNSIGNED column to automatically convert negative numbers to 0.

One business safeguard is placing the condition directly in the UPDATE:

~~~sql
UPDATE inventory_demo
SET quantity = quantity - 5
WHERE product_id = 1
  AND quantity >= 5;
~~~

After the UPDATE, the application checks the affected row count. If it is 0, either the product was not found or inventory was insufficient; distinguish the two cases if business logic requires.

Another approach is locking and checking inventory within a transaction, then updating conditionally. Keeping the condition in the UPDATE remains useful because it performs the check and modification in a single statement, reducing race condition risks compared to reading quantity and updating unconditionally.

## 6. Invalid Date and Time Data

MySQL validates date/time values based on data type, SQL mode, and context. A string that looks like a date is not necessarily a valid calendar date.

Example:

- 2026-02-30: month and day are within numeric bounds, yet the date does not exist on the calendar.
- 2026-13-01: month is out of range.
- 2026-00-15: zero month.
- 0000-00-00: zero date.
- 2026-04-31: April does not have 31 days.

These cases are not all identical. SQL mode may allow certain incomplete or invalid date forms, though applications should not use such values as normal business data.

### 6.1. Strict Mode

Two common strict modes:

- **STRICT_TRANS_TABLES**: enables strict checks for transactional tables like InnoDB; for non-transactional tables, handling of multi-row statements may have limitations.
- **STRICT_ALL_TABLES**: applies strict behavior more broadly across all storage engines; with non-transactional engines, some data may still be written before an error occurs.

In strict mode, invalid date/time values in INSERT or UPDATE typically cause the statement to fail. In non-strict mode, the server may adjust the value and emit a warning. Exact results also depend on date modes and the operation performed.

Check:

~~~sql
SELECT @@SESSION.sql_mode;
~~~

### 6.2. NO_ZERO_DATE and NO_ZERO_IN_DATE

Two modes related to zero dates:

- **NO_ZERO_DATE** controls acceptance of the full value 0000-00-00.
- **NO_ZERO_IN_DATE** controls values with a non-zero year but zero month or day, such as 2026-00-15.

When combined with strict mode, disallowed values typically raise errors during writes. If strict mode is off, the server may only emit a warning and adjust the data.

In MySQL 8.0, NO_ZERO_DATE and NO_ZERO_IN_DATE have been marked deprecated. Exact behavior still depends on the version and active SQL mode. Do not build new designs relying on toggling these two modes individually to permit invalid dates.

### 6.3. ALLOW_INVALID_DATES

ALLOW_INVALID_DATES relaxes full date validity checks for DATE and DATETIME. MySQL still verifies months in 1–12 and days in 1–31, but does not fully check month/day calendar combinations.

For example, with this mode, a value like 2026-02-30 may be accepted for DATE or DATETIME even though that date does not exist on the calendar. This mode does not apply to TIMESTAMP; TIMESTAMP still requires valid dates.

ALLOW_INVALID_DATES is usually unsuitable for business applications. It can be helpful in certain data ingestion pipelines that need to preserve received date components intact, provided there is a separate validation and cleansing step before using the data.

### 6.4. A Zero Date Is Not NULL

A zero date 0000-00-00 is a special value, distinct from NULL:

- NULL indicates no value or unknown according to column semantics.
- A zero date is a special date value that may be forbidden by SQL mode.
- Comparisons, date/time functions, and conversions can treat the two cases differently.

If a date is unknown, use NULL if business rules allow. If you need to distinguish "not entered", "not applicable", and "pending confirmation", use a dedicated business status column.

## 7. Date/Time Values Outside Data Type Range

Beyond non-existent calendar dates, values can also exceed the data type's supported range:

| Type | Typical Range in MySQL 5.7, 8.0, and 8.4 |
|---|---|
| DATE | 1000-01-01 to 9999-12-31 |
| DATETIME | 1000-01-01 00:00:00 to 9999-12-31 23:59:59 |
| TIMESTAMP | 1970-01-01 00:00:01 to 2038-01-19 03:14:07 UTC |

Example:

~~~sql
CREATE TEMPORARY TABLE temporal_demo (
    date_value      DATE,
    datetime_value  DATETIME,
    timestamp_value TIMESTAMP
);

INSERT INTO temporal_demo (date_value)
VALUES ('10000-01-01');
~~~

The year 10000 exceeds the DATE range. Similarly, TIMESTAMP cannot store an instant beyond its upper bound, even though DATETIME can represent that year within its supported range.

When receiving data from APIs, validate date ranges before sending them to the database. Avoid using TIMESTAMP for far-future data such as long-term maintenance schedules, maturity dates, or events that could occur after 2038.

## 8. How SQL Mode Affects Write Outcomes

A useful mental model is distinguishing three outcomes:

1. **Statement succeeds, no warnings:** the value is accepted under current rules.
2. **Statement succeeds, with warnings:** the server adjusted or accepted the value under a permissive mode; read both the warnings and actual stored data.
3. **Statement fails:** the server rejects the operation. With InnoDB, the failing statement is rolled back; the enclosing transaction may remain open and the application must decide whether to roll back the transaction.

Example of checking warnings:

~~~sql
INSERT IGNORE INTO tinyint_demo (value)
VALUES (200);

SHOW WARNINGS;

SELECT value
FROM tinyint_demo
ORDER BY value;
~~~

Do not only check the statement's return code at the application layer and ignore warnings. If the server accepts data after adjusting it, the application could end up storing a value different from the original input.

### 8.1. IGNORE Is Not a Safe Strict Mode

IGNORE changes how certain errors are reported, often converting errors into warnings and allowing the statement to continue. This is useful in import workflows that intentionally skip certain rows, yet dangerous when used for business operations requiring accuracy.

For numeric or date/time data, verify:

- Which value was stored after adjustment?
- Which rows were skipped?
- Which warnings were emitted?
- Was any data lost or business meaning altered?

Without a clear warning-handling policy, avoid IGNORE for critical write operations.

## 9. Observing Errors and Warnings

When inspecting SQL mode behavior, run the following commands directly in the same session:

~~~sql
SELECT @@SESSION.sql_mode;
SELECT @@warning_count;
SHOW WARNINGS;
SHOW ERRORS;
~~~

SHOW WARNINGS lists the most recent warnings, notes, and errors retained for the session. SHOW ERRORS displays errors only. These commands are helpful in SQL clients and manual testing.

In applications, drivers typically expose SQLState, vendor error codes, and warning chains. Log that information alongside the statement and MySQL version when investigating incidents. Do not write sensitive data or secrets into logs.

### 9.1. Checking Configuration Across Environments

Run the same query across development, test, and production:

~~~sql
SELECT
    VERSION() AS mysql_version,
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode,
    @@SESSION.time_zone AS session_time_zone;
~~~

If SQL modes differ, identical input data may be rejected in one environment yet adjusted in another. Include SQL mode in deployment configuration and test migrations under production-like settings.

## 10. Comprehensive Testing Example

The following example creates temporary tables to test division, overflow, and invalid dates. Run in a test session:

~~~sql
CREATE TEMPORARY TABLE numeric_check (
    id       INT NOT NULL AUTO_INCREMENT,
    amount   TINYINT NOT NULL,
    ratio    DECIMAL(8, 4) NULL,
    PRIMARY KEY (id)
);

CREATE TEMPORARY TABLE date_check (
    id         INT NOT NULL AUTO_INCREMENT,
    event_date DATE NULL,
    event_time DATETIME NULL,
    PRIMARY KEY (id)
);

-- Test division by zero
SELECT 10 / 0;
SHOW WARNINGS;

-- Test safe division
SELECT 10 / NULLIF(0, 0) AS safe_ratio;

-- Test numeric value exceeding TINYINT range
INSERT INTO numeric_check (amount) VALUES (200);
SHOW WARNINGS;

-- Test nonexistent date
INSERT INTO date_check (event_date) VALUES ('2026-02-30');
SHOW WARNINGS;

-- Inspect actual stored data
SELECT * FROM numeric_check;
SELECT * FROM date_check;
~~~

Results can differ by SQL mode. To compare strict and non-strict modes, run in two separate test sessions, set SQL modes intentionally, and record errors, warnings, and stored data. Never use production tables to test boundary values or invalid data.

## 11. Safe Data Design and Processing Workflow

When building features involving arithmetic or date/time data, follow this workflow:

1. Determine business value ranges before choosing column types.
2. Choose numeric types with sufficient range; use DECIMAL for values requiring decimal precision.
3. Check denominators before division or use NULLIF to handle zero denominators.
4. Check arithmetic on UNSIGNED columns, especially subtractions that could yield negative numbers.
5. Choose DATE, DATETIME, or TIMESTAMP according to calendar date, local wall-clock time, or instant semantics.
6. Enable appropriate strict modes and check the actual SQL mode of each session.
7. Do not use IGNORE to hide data errors without a clear policy.
8. Check warnings immediately after operations and verify actual stored values.
9. Test boundary values near data type limits, invalid dates, and out-of-range inputs.
10. Synchronize SQL mode across environments and test behavior after MySQL upgrades.

## 12. Common Misconceptions

**"Division by zero always rolls back the entire transaction."** Not necessarily. The outcome depends on the statement, SQL mode, IGNORE, and target data type. A SELECT may just return NULL and a warning; an INSERT or UPDATE may fail in strict mode.

**"If INSERT succeeds, the value was stored exactly as provided."** No. In non-strict mode or with IGNORE, MySQL may adjust the data and emit a warning.

**"UNSIGNED is just a way to represent larger positive numbers."** It also affects arithmetic semantics, especially subtractions that could produce negative results.

**"DECIMAL never overflows."** DECIMAL is exact decimal arithmetic within finite precision and scale limits. Values or results exceeding those limits can still be rejected or adjusted.

**"ALLOW_INVALID_DATES makes all date/time types accept any string."** No. This mode only relaxes part of validation for DATE and DATETIME; month and day must still be within numeric bounds, while TIMESTAMP still requires valid dates.

**"A zero date is the same as NULL."** No. NULL indicates absence of a value; a zero date is a special date value and can be forbidden by SQL mode.

**"Changing GLOBAL SQL mode updates all connections immediately."** No. Open sessions keep their own SESSION value until altered.

## Conclusion

Division by zero, overflow, and invalid date/time data are all governed by data types, SQL mode, and statement context. SELECT may return NULL with a warning; write operations in strict mode may be rejected; IGNORE can convert some errors into warnings and cause data adjustments. Arithmetic on UNSIGNED columns warrants special care because intermediate results may be unable to represent negative numbers.

Check SQL mode on the exact session, validate inputs, choose data types with sufficient range, guard division with NULLIF or CASE, and read warnings after operations. Testing results, errors, and actual stored data keeps applications faithful to business semantics across different MySQL environments.
