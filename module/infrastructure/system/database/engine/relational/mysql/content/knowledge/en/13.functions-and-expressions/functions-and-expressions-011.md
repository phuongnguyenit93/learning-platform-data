# CAST, CONVERT, and Explicit Conversion Control

In MySQL, an expression can combine multiple data types: numbers, strings, dates/times, and `NULL`. When types do not match, MySQL sometimes performs implicit conversion to evaluate arithmetic or comparisons. Implicit conversion is convenient in short SQL statements, yet it can alter comparison semantics, trigger warnings, or prevent queries from using indexes.

`CAST()` and `CONVERT()` let authors specify the exact target data type or character set to use. Within the **DATABASE_MYSQL** module, you need to know when to cast types, when to convert character encodings, how to inspect warnings, and how to keep filter predicates index-friendly.

## 1. What Is Data Type Conversion?

Data type conversion transforms a value from one type to another so it fits a calculation, comparison, storage column, or output format.

Examples:

- Converting string `'125.50'` to `DECIMAL` for monetary calculations.
- Converting ISO date string `'2026-11-19'` to `DATE`.
- Converting number `123` to string `'123'` for concatenation with text.
- Converting a string to the `utf8mb4` character set for uniform Unicode handling.

MySQL can convert types automatically in many expressions. For instance, comparing a numeric column to a string literal can cause the server to convert the string to a number. Without understanding these rules, a query can run cleanly while returning surprising results.

Explicit conversion means specifying the conversion directly in SQL:

```sql
SELECT CAST('125.50' AS DECIMAL(10,2)) AS amount;
SELECT CONVERT('2026-11-19', DATE) AS order_date;
```

Casting clarifies intent, yet it does not validate source data by itself. If inputs are invalid or exceed the target range, outputs may still be truncated, rounded, turned into fallback values, or raise warnings depending on type and context.

## 2. What Forms Do CAST and CONVERT Have?

MySQL provides two equivalent type-conversion forms:

```sql
CAST(expression AS target_type)
CONVERT(expression, target_type)
```

For example, both statements below serve the exact same purpose:

```sql
SELECT CAST('42' AS UNSIGNED) AS quantity;
SELECT CONVERT('42', UNSIGNED) AS quantity;
```

`CAST()` is commonly used when emphasizing a standard type cast. `CONVERT(expr, type)` is an equivalent syntax and handy if you are already familiar with the `CONVERT` function name.

`CONVERT()` also has a separate form for character set transcoding:

```sql
CONVERT(expression USING target_character_set)
```

Example:

```sql
SELECT CONVERT('Tiếng Việt' USING utf8mb4);
```

The two forms of `CONVERT()` serve different purposes:

| Syntax | Purpose |
|---|---|
| `CONVERT(expr, type)` | Converts a value to a target SQL data type |
| `CAST(expr AS type)` | Converts a value to a target SQL data type |
| `CONVERT(expr USING charset)` | Transcodes a string to a target character set |

Do not write `CONVERT(expr, utf8mb4)` to convert character sets; always use the `USING` keyword.

## 3. Commonly Used Target Types

In practice exercises, common target types include:

| Target Type | Purpose | Example |
|---|---|---|
| `SIGNED` / `UNSIGNED` | Converts to signed/unsigned integer | `CAST('120' AS UNSIGNED)` |
| `DECIMAL(M,D)` | Converts to exact decimal with specified precision/scale | `CAST('123.45' AS DECIMAL(10,2))` |
| `CHAR` | Converts to character string | `CAST(123 AS CHAR)` |
| `BINARY` | Converts to byte string for binary processing | `CAST('ABC' AS BINARY)` |
| `DATE` | Converts to calendar date | `CAST('2026-11-19' AS DATE)` |
| `TIME` | Converts to time of day or duration | `CAST('14:30:00' AS TIME)` |
| `DATETIME` | Converts to timezone-naive date and time | `CAST('2026-11-19 14:30:00' AS DATETIME)` |
| `JSON` | Converts valid JSON text into a JSON value | `CAST('{"active": true}' AS JSON)` |

You can specify a character set when casting to `CHAR`:

```sql
CAST(expression AS CHAR CHARACTER SET utf8mb4)
```

If the result requires a specific collation, you can also attach `COLLATE`:

```sql
SELECT
    CAST('Nguyen' AS CHAR CHARACTER SET utf8mb4)
        COLLATE utf8mb4_0900_ai_ci AS normalized_name;
```

Supported target types and syntax variants can depend on the MySQL version. Check the documentation for your exact version before using less common types in migrations.

## 4. Converting Strings to Numbers

When importing CSV files or receiving API payloads, numeric values sometimes arrive as strings. Convert them explicitly before performing calculations:

```sql
SELECT
    CAST('125.50' AS DECIMAL(10,2)) AS unit_price,
    CAST('3' AS UNSIGNED) AS quantity,
    CAST('125.50' AS DECIMAL(10,2)) *
        CAST('3' AS UNSIGNED) AS line_total;
```

`line_total` evaluates to `376.50`. For monetary figures, use `DECIMAL` rather than `FLOAT`/`DOUBLE` to avoid binary floating-point representation errors.

### Conversion Is Not Validation

Example input with non-numeric characters:

```sql
SELECT CAST('12abc' AS UNSIGNED) AS parsed_value;
SHOW WARNINGS;
```

MySQL may parse the leading numeric prefix and emit a warning about the invalid trailing data. For completely non-numeric strings, conversion may return 0 with a warning. Exact behavior depends on the expression, target type, and server version.

Therefore, never use `CAST()` as an input validation mechanism. Before writing data, the application should validate strings against business formats; after SQL statements, inspect warnings if your pipeline needs to detect unclean conversions.

### Rounding and Loss of Precision

When converting a value to `DECIMAL(M,D)`, MySQL applies scale `D`. Fractional digits beyond scale `D` may be rounded:

```sql
SELECT CAST('12.345' AS DECIMAL(5,2)) AS rounded_value;
```

The typical result is `12.35`. If the value exceeds the target precision or type range, MySQL may raise an error or warning depending on context and SQL mode. Always size `M` and `D` based on business limits rather than just a few sample values.

## 5. Converting Numbers to Strings

When concatenating numbers with text or formatting outputs, cast numbers to strings explicitly:

```sql
SELECT CONCAT(
    'Order #',
    CAST(order_id AS CHAR)
) AS order_label
FROM orders;
```

`CAST(order_id AS CHAR)` makes it explicit that `order_id` is converted to a string before concatenation. For presentation formatting, apply dedicated formatting functions or handle formatting in Java.

Do not convert numbers to strings in stored columns merely to keep leading zeros if the value is genuinely a numeric quantity. Conversely, if `00125` is an identifier code rather than an arithmetic number, store it as `CHAR`/`VARCHAR` from the start.

## 6. Converting Dates and Times

`CAST()` can parse strings formatted in MySQL-recognized date/time formats:

```sql
SELECT
    CAST('2026-11-19' AS DATE) AS order_date,
    CAST('14:30:00' AS TIME) AS opening_time,
    CAST('2026-11-19 14:30:00' AS DATETIME) AS scheduled_at;
```

If source strings use a custom format like `19/11/2026`, use `STR_TO_DATE()` to specify the parsing mask:

```sql
SELECT STR_TO_DATE('19/11/2026', '%d/%m/%Y') AS order_date;
```

Do not assume `CAST('19/11/2026' AS DATE)` will understand the day/month order properly. Use ISO format `YYYY-MM-DD` for data interchange whenever possible; for other formats, specify the pattern via `STR_TO_DATE()`.

`CAST(... AS DATETIME)` does not attach a timezone to the value. If the source represents an instant with an offset, the application must parse the offset properly and convert to the system's storage convention. Never strip the offset and treat the remaining date-time string as UTC by default.

## 7. CONVERT and Character Set Conversion

Character set conversion transcodes text representation between character sets. Example:

```sql
SELECT CONVERT('Tiếng Việt 😀' USING utf8mb4) AS unicode_text;
```

`CONVERT(... USING utf8mb4)` converts the string to `utf8mb4`. The resulting collation follows the target character set's default unless a collation is explicitly specified afterward.

Inspect the expression's character set and collation:

```sql
SELECT
    CHARSET(CONVERT('Tiếng Việt' USING utf8mb4)) AS result_charset,
    COLLATION(CONVERT('Tiếng Việt' USING utf8mb4)) AS result_collation;
```

Or cast to character type and specify the charset directly inside `CAST`:

```sql
SELECT CAST('Tiếng Việt' AS CHAR CHARACTER SET utf8mb4);
```

### Character Set Conversion Cannot Repair Corrupted Bytes

`CONVERT(... USING charset)` assumes MySQL knows the expression's current character set and transcodes characters to the target charset. If source data was originally written using wrong bytes while metadata declared a mismatched charset, converting may preserve corrupted content or corrupt it further. Before fixing mojibake data, identify the raw bytes, true source charset, and target charset.

If the target character set cannot represent certain source characters, conversion can lose information or generate warnings. `utf8mb4` is the right choice for full Unicode support in most new applications; never downgrade to a narrower charset without an explicit compatibility requirement.

## 8. Distinguishing CAST from COLLATE

`CAST()` changes the data type. `COLLATE` selects the comparison rules for a string expression. The two operations can be combined, yet they do not replace each other.

```sql
SELECT
    CAST('café' AS CHAR CHARACTER SET utf8mb4)
        COLLATE utf8mb4_0900_ai_ci =
    CAST('cafe' AS CHAR CHARACTER SET utf8mb4)
        COLLATE utf8mb4_0900_ai_ci AS equal_ignoring_accent;
```

Under `utf8mb4_0900_ai_ci`, both strings compare equal regardless of accents or letter case. Using an accent-sensitive collation yields a different result.

`COLLATE` applies only to expressions with compatible character sets. If two expressions use different charsets, align their character sets first and then pick the matching collation. Never use `COLLATE` to transcode bytes from one charset to another.

## 9. NULL in Conversions

Conversion does not turn `NULL` into a default value. Example:

```sql
SELECT
    CAST(NULL AS DECIMAL(10,2)) AS amount,
    CONVERT(NULL, CHAR) AS label;
```

Both expressions return `NULL`. If missing values should be replaced with another value, express that rule separately using `COALESCE()` or `IFNULL()`:

```sql
SELECT COALESCE(CAST(NULL AS DECIMAL(10,2)), 0.00) AS amount;
```

The result is `0.00`, which comes from `COALESCE()`, not `CAST()`. In comparisons, `NULL = NULL` does not evaluate to true; use `IS NULL` or `IS NOT NULL` to check for null values.

## 10. Implicit Conversion and Unexpected Results

MySQL automatically converts types in certain comparisons and expressions. Example:

```sql
SELECT
    '00123' = 123 AS numeric_comparison,
    '00123' = '123' AS string_comparison;
```

When comparing a string to a number, MySQL can convert the string to a number; therefore `'00123' = 123` evaluates to true. In a string-to-string comparison, characters are compared under collation rules and `'00123'` differs from `'123'`.

This is especially dangerous for identifier codes. Customer codes `'00123'` and `'123'` may be two distinct business identifiers, yet comparing them in a numeric context causes them to be treated as equal.

### Avoid Unintended Type Mixing

Do not write:

```sql
SELECT *
FROM external_codes
WHERE code = 123;
```

If `code` is `VARCHAR` holding identifier codes, compare against a string:

```sql
SELECT *
FROM external_codes
WHERE code = '00123';
```

If the input is a bound parameter requiring a cast, cast the parameter rather than wrapping the indexed column:

```sql
SELECT *
FROM external_codes
WHERE code = CAST(? AS CHAR);
```

Keeping the column type and comparison value type aligned preserves clear semantics and allows MySQL to use indexes.

## 11. CAST/CONVERT and Index Usage

A key optimization principle is to avoid applying functions or casts to indexed columns inside filter predicates, unless an appropriate functional index exists and its plan has been verified.

Suppose `orders.order_id` is indexed:

```sql
-- May reduce the ability to use an index range scan on order_id
SELECT *
FROM orders
WHERE CAST(order_id AS CHAR) = '105';
```

Instead, cast the input value to match the column's type:

```sql
SELECT *
FROM orders
WHERE order_id = CAST('105' AS UNSIGNED);
```

In real queries, bind parameters with the proper type from JDBC; no `CAST` is needed when the driver sends the right type.

Example filtering by time while keeping `created_at` bare:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= CAST(? AS DATETIME)
  AND created_at <  CAST(? AS DATETIME);
```

If `created_at` is indexed, this keeps the column bare inside range predicates. Even so, verify with `EXPLAIN`, as index usage depends on query structure, parameter types, and statistics.

## 12. SQL Mode, Warnings, and Invalid Data

Explicit conversion does not bypass MySQL's data validation rules. SQL mode can govern how the server handles invalid data in `INSERT`, `UPDATE`, and certain expressions.

Inspect the session's mode:

```sql
SELECT @@SESSION.sql_mode;
```

Strict modes such as `STRICT_TRANS_TABLES` and `STRICT_ALL_TABLES` cause many invalid values to be rejected on write rather than silently adjusted. However, do not assume every `CAST()` inside a `SELECT` turns warnings into errors merely because strict mode is enabled. Verify the actual outputs and warnings of expressions on your target server version.

Inspect warnings immediately after a conversion:

```sql
SELECT CAST('12abc' AS UNSIGNED);
SHOW WARNINGS;
```

`SHOW WARNINGS` reports warnings/errors from the most recent statements in the session. Running another statement beforehand can replace the list you wanted to inspect.

Never treat the return value from a failed conversion as valid data. Validate inputs in Java, bind matching parameter types, enforce database constraints, and log conversion errors in import pipelines.

## 13. Using CAST/CONVERT in Java and JDBC

In Java applications, prefer binding parameters with matching Java types instead of concatenating SQL strings or casting every value on the database side.

Example binding a monetary amount with `BigDecimal`:

```java
String sql = "INSERT INTO payments (amount) VALUES (?)";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setBigDecimal(1, new BigDecimal("125.50"));
    statement.executeUpdate();
}
```

Example binding a date:

```java
String sql = "SELECT order_id FROM orders WHERE order_date = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setObject(1, LocalDate.of(2026, 11, 19));
    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
        }
    }
}
```

These examples assume JDBC classes along with `java.math.BigDecimal` and `java.time.LocalDate` are imported, and `connection` is an open JDBC connection. When binding matching types, SQL queries typically do not need `CAST()`.

If source data arrives strictly as a string, you can cast the parameter in SQL:

```sql
SELECT order_id
FROM orders
WHERE order_id = CAST(? AS UNSIGNED);
```

Never use `CAST()` as a substitute for `PreparedStatement`. Parameter binding remains essential to separate data from SQL syntax and prevent SQL injection.

## 14. Checklist for Choosing CAST vs. CONVERT

| Requirement | Approach |
|---|---|
| Convert string to number/date/time | `CAST(expr AS type)` or `CONVERT(expr, type)` |
| Convert number to string | `CAST(expr AS CHAR)` |
| Transcode string to another character set | `CONVERT(expr USING charset)` |
| Specify string comparison rules | `expr COLLATE collation_name` once charsets are compatible |
| Parse custom date string format | `STR_TO_DATE(expr, format)` |
| Use application values in queries | Bind parameters with matching Java types; cast parameters only when needed |

Before adding a conversion to a query, ask yourself:

1. What is the source type and what is the required target type?
2. Could conversion discard decimals, characters, leading zeros, or timezone information?
3. Will invalid values trigger warnings, errors, or truncated outputs?
4. Can the parameter be bound with the right type instead of converting in SQL?
5. Is the conversion wrapping an indexed column inside `WHERE`?
6. For character set conversion, are source bytes genuinely encoded in the declared charset?
7. Does the result carry the right collation for business rules?

## 15. Practice Exercises

1. Convert `'125.50'` to `DECIMAL(10,2)` and calculate the total for quantity `3`.
2. Convert the number `123` to `CHAR` and concatenate it into an order label.
3. Convert an ISO string to `DATE` and a `dd/mm/yyyy` string using `STR_TO_DATE()`.
4. Run `CAST('12abc' AS UNSIGNED)` and check `SHOW WARNINGS`; explain why casting does not replace validation.
5. Compare `CONVERT(expr, type)` with `CONVERT(expr USING utf8mb4)` and inspect `CHARSET()`/`COLLATION()` of the results.
6. Compare `'00123' = 123` against `'00123' = '123'`; explain the risk of comparing identifier codes numerically.
7. Use `EXPLAIN` to compare `CAST(order_id AS CHAR) = ...` against casting the parameter while leaving the `order_id` column bare.
8. Write a JDBC query using `PreparedStatement` with `setBigDecimal()` or `setObject()` to pass properly typed values.

You have completed the lesson when you can distinguish type casting from character set transcoding, spot implicit conversions, read warnings, and place `CAST` appropriately to preserve both semantics and index usability. Define proper data types from the start, and apply explicit conversions at data boundaries only when truly needed.
