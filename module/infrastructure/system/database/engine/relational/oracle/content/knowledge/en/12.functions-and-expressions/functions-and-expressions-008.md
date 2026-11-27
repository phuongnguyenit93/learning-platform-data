# CAST, Format Models, and Controlling Data Conversion in Oracle

## 1. Why control data conversion?

An application might receive a price from a CSV as the string `'1.250,50'`, receive a date from a UI as `'14/11/2026'`, and write them into `NUMBER` and `DATE` columns in Oracle Database. A SQL statement that runs on a developer's machine might fail in testing or production because how Oracle converts text into numbers or dates can depend on session NLS settings.

Example:

```sql
-- Source data is a string, not yet a NUMBER.
SELECT '123.45' AS amount_text FROM dual;

-- Explicit conversion to NUMBER.
SELECT TO_NUMBER(
           '123.45',
           '999D99',
           'NLS_NUMERIC_CHARACTERS=''.,'''
       ) AS amount_value
FROM dual;
```

When you need to convert an expression from one data type to another, Oracle provides `CAST`. When you need to parse a string according to a specific format, `TO_NUMBER`, `TO_DATE`, `TO_TIMESTAMP`, and `TO_TIMESTAMP_TZ` allow you to specify a **format model**. When you need to format a value for display, use `TO_CHAR`.

Distinguish three concepts:

1. **Type conversion:** transforming an expression from a source data type to a target data type, such as `NUMBER` to `VARCHAR2`.
2. **Format model:** describes how to parse or display components of a number or datetime, such as `YYYY-MM-DD` or `9G999D99`.
3. **NLS parameters:** define language and territory conventions such as decimal markers, group separators, month names, and default display formats.

The goal of this lesson in the **Functions and Expressions** chapter is to write conversion expressions with explicit target types, accurately parse input data, control NLS effects, catch conversion errors, and safely pass typed values from Java/JDBC applications.

## 2. Source types, target types, and conversions

Every SQL expression has a data type. For example:

| Expression | Typical Data Type |
|---|---|
| `123.45` | `NUMBER` |
| `'123.45'` | `VARCHAR2` literal |
| `DATE '2026-11-14'` | `DATE` |
| `TIMESTAMP '2026-11-14 10:30:00'` | `TIMESTAMP` |
| `CAST(NULL AS NUMBER)` | `NUMBER` with value NULL |
| `TO_CHAR(SYSDATE, 'YYYY-MM-DD')` | `VARCHAR2` |
| `TO_NUMBER('123.45', '999D99')` | `NUMBER` |

Data conversion is the process where Oracle interprets a source value and produces a value of the target data type. Not every conversion is safe:

- `'123'` can convert to `NUMBER`.
- `'12A'` is not a valid numeric representation under standard format models.
- `'14/11/2026'` can convert to `DATE` with format `DD/MM/YYYY`.
- `'31/02/2026'` is not a valid calendar date.
- A number may exceed the precision or length of the target type.
- Converting `TIMESTAMP` to `DATE` discards fractional seconds.

### 2.1. Explicit conversion vs. implicit conversion

**Explicit conversion** appears directly in SQL:

```sql
SELECT TO_NUMBER('2500') AS amount FROM dual;
```

**Implicit conversion** is performed automatically by Oracle so two operands or expressions can work together:

```sql
SELECT 2500 + '100' AS total FROM dual;
```

In this specific case Oracle can convert `'100'` to a number. But if the string is `'100A'`, the expression fails. Relying on implicit conversion also makes SQL dependent on session formatting, reduces readability, and can affect execution plans.

Practical rule: **whenever data crosses a type boundary or system boundary, convert explicitly and document the data's semantics**.

## 3. `CAST`: converting an expression to a target data type

### 3.1. Basic syntax

```sql
CAST(expression AS datatype)
```

Example:

```sql
SELECT CAST('12345' AS NUMBER) AS numeric_value,
       CAST(12345 AS VARCHAR2(20)) AS text_value
FROM dual;
```

The first expression has type `NUMBER`; the second has a character type. `CAST` explicitly states the target type right inside the SQL query.

### 3.2. Converting numeric strings to NUMBER

```sql
SELECT CAST('2500' AS NUMBER) AS amount
FROM dual;
```

This example uses a simple numeric string that can be parsed under default session numeric conversion rules. For data containing locale-dependent decimal markers or group separators, do not rely solely on `CAST`; use `TO_NUMBER` with an explicit format model and NLS parameters.

### 3.3. Specifying precision and scale

`CAST` can convert to `NUMBER` with a declared precision and scale:

```sql
SELECT CAST(123.456 AS NUMBER(8, 2)) AS rounded_value,
       CAST(12 AS NUMBER(8, 2)) AS integer_value
FROM dual;
```

`NUMBER(8,2)` allows up to eight significant digits total, with two digits after the decimal point. When casting a number with more fractional digits than the scale permits, Oracle rounds according to numeric conversion rules. If the value exceeds the target precision, the conversion raises an error.

Do not confuse `NUMBER(8,2)` with a display format. The data type controls numeric precision; `TO_CHAR` with a format model controls string formatting.

### 3.4. Converting DATE and TIMESTAMP

```sql
SELECT CAST(DATE '2026-11-14' AS TIMESTAMP) AS timestamp_value
FROM dual;
```

The `DATE` value is widened to `TIMESTAMP`; fractional seconds are filled with zeros.

In the reverse direction:

```sql
SELECT CAST(
           TIMESTAMP '2026-11-14 16:30:45.123456'
           AS DATE
       ) AS date_value
FROM dual;
```

`DATE` retains precision only to the second; `.123456` is not stored in the target type.

**Never use `CAST` to parse a date string in an arbitrary format.** `CAST` does not take a date format model parameter. When the source is a string, use `TO_DATE` or `TO_TIMESTAMP` with a format model:

```sql
SELECT TO_DATE('14/11/2026', 'FXDD/MM/YYYY') AS parsed_date
FROM dual;
```

### 3.5. CAST(NULL AS datatype): typing NULL values

In `UNION`, `CASE`, or queries generating rows with missing columns, you may need to give NULL an explicit type:

```sql
SELECT CAST(NULL AS NUMBER(12, 2)) AS amount
FROM dual;
```

This represents a NULL value of **type NUMBER(12,2)** in the expression. It helps Oracle resolve column types in set operations:

```sql
SELECT CAST(NULL AS NUMBER(12, 2)) AS amount
FROM dual
UNION ALL
SELECT CAST(125.50 AS NUMBER(12, 2)) AS amount
FROM dual;
```

`CAST(NULL AS ...)` does not turn NULL into 0; it only attaches a data type to the NULL expression.

### 3.6. CAST in CASE and UNION

`CASE` branches and set-combined queries require compatible data types:

```sql
SELECT CASE
           WHEN 1 = 1 THEN CAST(100 AS NUMBER(10, 2))
           ELSE CAST(NULL AS NUMBER(10, 2))
       END AS amount
FROM dual;
```

When branches have incompatible types, Oracle can raise a data type mismatch error. Using `CAST` makes the common return type explicit.

### 3.7. CAST and character strings

```sql
SELECT CAST(12345 AS VARCHAR2(20)) AS code_text,
       CAST('AB' AS CHAR(5)) AS fixed_text
FROM dual;
```

`CHAR` is fixed-length with blank-padding rules; `VARCHAR2` is variable-length. When converting numbers to strings for UI display or file exports, `CAST(number AS VARCHAR2(...))` does not give you full control over decimal markers, grouping separators, or digit counts like `TO_CHAR` does.

For example, to display two decimal places:

```sql
SELECT TO_CHAR(
           1234.5,
           'FM9G999D00',
           'NLS_NUMERIC_CHARACTERS=''.,'''
       ) AS formatted_amount
FROM dual;
```

Here `TO_CHAR` is better suited because it accepts an explicit format model.

## 4. How `CAST` differs from `TO_CHAR`, `TO_NUMBER`, and `TO_DATE`

| Function | Conversion Direction | When to Use |
|---|---|---|
| `CAST(expr AS type)` | Expression → target type | Need an explicit output type without a custom parse/display mask |
| `TO_CHAR(number, fmt, nlsparam)` | NUMBER → text | Need control over digits, decimal markers, grouping, or currency |
| `TO_CHAR(datetime, fmt, nlsparam)` | DATE/TIMESTAMP → text | Need control over date/time ordering and timezone display |
| `TO_NUMBER(text, fmt, nlsparam)` | Text → NUMBER | Input follows a specific numeric format |
| `TO_DATE(text, fmt, nlsparam)` | Text → DATE | Input is a date/time down to seconds |
| `TO_TIMESTAMP(text, fmt, nlsparam)` | Text → TIMESTAMP | Input includes fractional seconds |
| `TO_TIMESTAMP_TZ(text, fmt, nlsparam)` | Text → TIMESTAMP WITH TIME ZONE | Input includes timezone offset or region per format model |

Comparison example:

```sql
-- Type conversion:
SELECT CAST(1234.5 AS VARCHAR2(30)) AS cast_text
FROM dual;

-- Conversion and formatting:
SELECT TO_CHAR(
           1234.5,
           'FM9G999D00',
           'NLS_NUMERIC_CHARACTERS=''.,'''
       ) AS formatted_text
FROM dual;
```

Both queries return strings, but the second explicitly formats `1,234.50` according to the specified convention. `CAST` is not a substitute for a format model.

## 5. Implicit conversion: convenient yet error-prone

Oracle can automatically convert types in expressions, comparisons, concatenation, and DML. Implicit conversion shortens statements, yet it can introduce NLS dependencies or force Oracle to evaluate functions over column values.

### 5.1. Strings and numbers

Suppose `orders.order_id` is `NUMBER`.

```sql
-- May force Oracle to convert the string '1001' to NUMBER:
SELECT *
FROM orders
WHERE order_id = '1001';
```

Write the exact type:

```sql
SELECT *
FROM orders
WHERE order_id = 1001;
```

If input comes from an application, bind a numeric type instead of formatting SQL strings. Never force the database to guess how to parse `'1,000'`, `'1.000'`, or `'1,000.00'`.

### 5.2. Datetimes and strings

```sql
-- Depends on session date format:
SELECT *
FROM orders
WHERE created_at >= '14/11/2026';
```

Write explicitly:

```sql
SELECT *
FROM orders
WHERE created_at >= DATE '2026-11-14';
```

Or if input follows day/month/year order:

```sql
SELECT *
FROM orders
WHERE created_at >= TO_DATE('14/11/2026', 'FXDD/MM/YYYY');
```

### 5.3. Converting a column can prevent index usage

Suppose column `created_at` is indexed. The predicate:

```sql
WHERE TO_CHAR(created_at, 'YYYY-MM-DD') = '2026-11-14'
```

applies a function to the column before comparing. Oracle may be unable to use the standard index on `created_at` as expected, because the predicate is no longer a direct range on the column.

Use a half-open interval instead:

```sql
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15'
```

This avoids string formatting and produces a range predicate that can leverage a suitable index. The actual execution plan still depends on statistics, selectivity, and schema structure; no single syntax guarantees index selection.

### 5.4. Conversion direction in comparisons matters

If a column is `NUMBER` while a bind or literal is a string, Oracle converts the string to a number. However, if a column is `VARCHAR2` and compared against a numeric expression, Oracle may convert the **column** to a number in certain contexts. If even one row holds `'A12'`, the query can fail with an invalid number error.

**Do not force Oracle to convert an entire column just because a parameter has the wrong type.** Match the parameter type to the column type and convert input data at the ingestion boundary.

## 6. What is a format model?

A **format model** is a symbol string describing how Oracle parses or formats a number or datetime value. It is not a data type, does not alter a column's type, and is not a universal format mask shared across all types.

Example:

```sql
TO_CHAR(1234.5, 'FM9G999D00')
```

The format model specifies digit slots `9`, group separator `G`, decimal marker `D`, two decimal digits `00`, and fill mode `FM`.

For datetimes:

```sql
TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS')
```

`YYYY`, `MM`, `DD`, `HH24`, `MI`, and `SS` identify each component. For input conversion functions, the format model also dictates how Oracle interprets each portion of the text.

## 7. Number format models

### 7.1. Common elements

| Element | Meaning | Example |
|---|---|---|
| `9` | Digit slot; left blank if no corresponding digit exists | `9999` |
| `0` | Digit slot; displays 0 if no digit exists at that position | `0000` |
| `D` | Decimal character per NLS | `999D99` |
| `G` | Thousands group separator per NLS | `9G999` |
| `L` | Local currency symbol | `L999D00` |
| `C` | ISO currency symbol per territory | `C999D00` |
| `$` | Dollar sign | `$999D00` |
| `S` | Plus/minus sign | `S9999` |
| `MI` | Trailing minus sign if negative | `9999MI` |
| `PR` | Angle brackets for negative numbers per format model | `9999PR` |
| `FM` | Fill mode, suppresses blank padding where applicable | `FM999G999D00` |
| `EEEE` | Scientific notation | `9.999EEEE` |

`D` and `G` are format elements, not literal commas or periods. The actual characters depend on `NLS_NUMERIC_CHARACTERS` or the NLS parameter passed directly to the function.

### 7.2. Difference between `9` and `0`

```sql
SELECT TO_CHAR(7, '9999') AS optional_digits,
       TO_CHAR(7, '0000') AS forced_zeroes
FROM dual;
```

`9` allows empty leading positions to remain blank, whereas `0` forces zeros at those positions. `TO_CHAR` can also pad with spaces to preserve format model width; `FM` is commonly used when compact output is desired.

```sql
SELECT TO_CHAR(7, 'FM9999') AS compact_number,
       TO_CHAR(7, 'FM0000') AS padded_number
FROM dual;
```

Expected values: `7` and `0007`.

### 7.3. Decimal markers and group separators

```sql
SELECT TO_CHAR(
           1234567.5,
           'FM9G999G999D00',
           'NLS_NUMERIC_CHARACTERS=''.,'''
       ) AS us_style
FROM dual;
```

The NLS parameter sets `.` as the decimal marker and `,` as the group separator; the display output is `1,234,567.50`.

To display in the style commonly used in Vietnam, swap the two characters:

```sql
SELECT TO_CHAR(
           1234567.5,
           'FM9G999G999D00',
           'NLS_NUMERIC_CHARACTERS='',.'''
       ) AS comma_decimal
FROM dual;
```

Illustrative result: `1.234.567,50`.

In `NLS_NUMERIC_CHARACTERS`, **the first character is the decimal marker**, and the second is the group separator. Passing it directly to the function isolates the convention to that expression without changing the entire session's NLS settings.

### 7.4. Parsing numeric strings with TO_NUMBER

When a source sends `1.234,56` under the convention of `.` grouping and `,` decimal, declare both the format model and NLS parameter:

```sql
SELECT TO_NUMBER(
           '1.234,56',
           '9G999D99',
           'NLS_NUMERIC_CHARACTERS='',.'''
       ) AS amount
FROM dual;
```

The result is the number `1234.56`, not the string `1.234,56`.

If data uses `,` grouping and `.` decimal, use:

```sql
SELECT TO_NUMBER(
           '1,234.56',
           '9G999D99',
           'NLS_NUMERIC_CHARACTERS=''.,'''
       ) AS amount
FROM dual;
```

Do not reuse the same format/NLS across sources with conflicting conventions. Identify formats at the ingestion boundary (CSVs, APIs, partner feeds) and parse according to that contract.

### 7.5. Controlling signs and currency

```sql
SELECT TO_CHAR(
           -1250.5,
           'FMS999G999D00',
           'NLS_NUMERIC_CHARACTERS=''.,'''
       ) AS signed_amount
FROM dual;
```

`S` controls sign placement per the format model. If a currency symbol is needed:

```sql
SELECT TO_CHAR(
           1250.5,
           'FML999G999D00',
           'NLS_NUMERIC_CHARACTERS='',.'' NLS_CURRENCY=''VND'''
       ) AS money_text
FROM dual;
```

This illustrates passing `NLS_CURRENCY`; actual currency formatting should follow your application's display policy. Never use currency-formatted strings for numeric calculations or store them in `NUMBER` columns.

### 7.6. Format models are not complete business validation

`TO_NUMBER` checks whether a string can be parsed under a format model, which does not ensure the value satisfies business rules. For example, `'0005'` parses to 5; if a product code must preserve leading zeros, it must be stored as a **character code**, not a NUMBER.

Similarly, a price parsing cleanly does not guarantee it is positive or within allowed bounds. Separate syntax checks, type conversion, and business rule validation.

## 8. Datetime format models

### 8.1. Core elements

| Element | Meaning |
|---|---|
| `YYYY` | Four-digit year |
| `YY` | Two-digit year under Oracle rules |
| `RR` | Two-digit year with special century-inference rules |
| `MM` | Numeric month |
| `MON` | Abbreviated month name per NLS language |
| `MONTH` | Full month name per NLS language |
| `DD` | Day of month |
| `DDD` | Day of year |
| `DY`, `DAY` | Short/full day-of-week name per NLS |
| `HH24` | Hour on 24-hour clock |
| `HH12` or `HH` | Hour on 12-hour clock |
| `MI` | Minute |
| `SS` | Second |
| `FF`, `FF1`…`FF9` | Fractional seconds for TIMESTAMP |
| `TZH` | Time zone offset hours |
| `TZM` | Time zone offset minutes |
| `TZR` | Time zone region |
| `TZD` | Daylight saving abbreviation for the region where applicable |

**Critical pitfall:** `MM` is month; `MI` is minute. `HH24:MM:SS` is almost always a bug when you mean hour-minute-second; use `HH24:MI:SS`.

### 8.2. Parsing dates with TO_DATE

```sql
SELECT TO_DATE('14/11/2026', 'DD/MM/YYYY') AS parsed_date
FROM dual;
```

To require an exact structural match:

```sql
SELECT TO_DATE('14/11/2026', 'FXDD/MM/YYYY') AS parsed_date
FROM dual;
```

`FX` (*format exact*) enforces stricter matching between the input string and format model, including separators and element widths per Oracle rules. This is useful for strict external contracts—such as partner files guaranteed to send `DD/MM/YYYY`.

### 8.3. Dates with month names and NLS_DATE_LANGUAGE

```sql
SELECT TO_DATE(
           '14-NOV-2026',
           'DD-MON-YYYY',
           'NLS_DATE_LANGUAGE=ENGLISH'
       ) AS parsed_date
FROM dual;
```

`MON` interprets month names using the active date language. If the session uses another language, omitting NLS causes parsing to fail or misinterpret values. If you control the input protocol, numeric ISO format `YYYY-MM-DD` exchanges far more reliably than natural-language month names.

### 8.4. Parsing 12-hour and 24-hour times

Input:

```text
14/11/2026 04:30:15 PM
```

Format:

```sql
SELECT TO_DATE(
           '14/11/2026 04:30:15 PM',
           'DD/MM/YYYY HH12:MI:SS AM'
       ) AS parsed_datetime
FROM dual;
```

If the source sends `16:30:15`, use `HH24`:

```sql
SELECT TO_DATE(
           '14/11/2026 16:30:15',
           'DD/MM/YYYY HH24:MI:SS'
       ) AS parsed_datetime
FROM dual;
```

Never use `HH12` without AM/PM if the source can be ambiguous between morning and afternoon.

### 8.5. Parsing fractional seconds with TO_TIMESTAMP

```sql
SELECT TO_TIMESTAMP(
           '2026-11-14 16:30:15.123456',
           'YYYY-MM-DD HH24:MI:SS.FF6'
       ) AS precise_timestamp
FROM dual;
```

`DATE` does not retain fractional seconds; use `TIMESTAMP` when needed. `FF6` represents six fractional-second digits. If the string contains a literal `T`:

```sql
SELECT TO_TIMESTAMP(
           '2026-11-14T16:30:15.123',
           'YYYY-MM-DD"T"HH24:MI:SS.FF3'
       ) AS precise_timestamp
FROM dual;
```

`"T"` is enclosed in double quotes in the format model so Oracle treats it as a literal character rather than a format element.

### 8.6. Parsing timezones with TO_TIMESTAMP_TZ

```sql
SELECT TO_TIMESTAMP_TZ(
           '2026-11-14 16:30:15 +07:00',
           'YYYY-MM-DD HH24:MI:SS TZH:TZM'
       ) AS event_time
FROM dual;
```

`TZH:TZM` parses the hour/minute offset. If data uses region names like `Europe/Paris`, the format model can use `TZR` and in some cases `TZD`; exact behavior depends on Oracle's timezone file and DST rules. A fixed numeric offset does not capture a region's full historical DST rules.

### 8.7. Formatting output with TO_CHAR

```sql
SELECT TO_CHAR(
           DATE '2026-11-14',
           'YYYY-MM-DD'
       ) AS iso_date,
       TO_CHAR(
           TIMESTAMP '2026-11-14 16:30:15.123456',
           'YYYY-MM-DD"T"HH24:MI:SS.FF6'
       ) AS iso_timestamp
FROM dual;
```

`TO_CHAR` returns text. It does not change the source column's type and should not replace datetime types in filter predicates or date arithmetic.

## 9. Standard literals vs. format models: which to choose?

When datetime constants are hardcoded directly in SQL, use standard ANSI literals:

```sql
SELECT DATE '2026-11-14',
       TIMESTAMP '2026-11-14 16:30:15.123456',
       TIMESTAMP '2026-11-14 16:30:15 +07:00'
FROM dual;
```

Literals create typed values without relying on default NLS parsing. For dynamic inputs, use conversion functions with format models:

```sql
SELECT TO_DATE(:p_day, 'FXYYYY-MM-DD')
FROM dual;
```

In applications, an even better approach is to parse strings at the API boundary per published contract and **bind typed datetime values**. There is no need to send strings to Oracle just to parse them if Java already holds a valid temporal object and the driver supports binding it.

| Source | Approach to Consider |
|---|---|
| Fixed constant in SQL | ANSI `DATE`/`TIMESTAMP` literal |
| Date string from file/API | `TO_DATE` with explicit format model and NLS |
| Timestamp string with fractional seconds | `TO_TIMESTAMP` |
| String with timezone offset | `TO_TIMESTAMP_TZ` |
| Java already holds `LocalDate`/`LocalDateTime`/`OffsetDateTime` | Bind typed value via JDBC |
| Generating text reports | `TO_CHAR` with explicit format model |
| Only specifying result type in an expression | `CAST` |

## 10. Controlling NLS in numeric and datetime conversions

NLS (*National Language Support*) in Oracle encompasses settings governing language, territory, and data formatting/conversion conventions.

### 10.1. Common NLS parameters

| Parameter | Effect |
|---|---|
| `NLS_NUMERIC_CHARACTERS` | Decimal marker and group separator |
| `NLS_CURRENCY` | Local currency symbol |
| `NLS_ISO_CURRENCY` | ISO currency rules/symbol per territory |
| `NLS_DATE_FORMAT` | Default mask for DATE display and implicit conversions |
| `NLS_TIMESTAMP_FORMAT` | Default mask for TIMESTAMP |
| `NLS_TIMESTAMP_TZ_FORMAT` | Default mask for TIMESTAMP WITH TIME ZONE |
| `NLS_DATE_LANGUAGE` | Month names, day names, and datetime language |
| `NLS_TERRITORY` | Territory conventions and numeric/datetime defaults |

### 10.2. Checking session NLS settings

```sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_NUMERIC_CHARACTERS',
    'NLS_CURRENCY',
    'NLS_DATE_FORMAT',
    'NLS_TIMESTAMP_FORMAT',
    'NLS_TIMESTAMP_TZ_FORMAT',
    'NLS_DATE_LANGUAGE',
    'NLS_TERRITORY'
)
ORDER BY parameter;
```

Actual values can differ across SQL*Plus, SQL Developer, SQLcl, and Java applications. Drivers, connection properties, or `ALTER SESSION` calls in a connection pool can produce sessions with differing NLS configurations.

### 10.3. Passing NLS parameters directly inside functions

For numbers:

```sql
SELECT TO_NUMBER(
           '1.234,56',
           '9G999D99',
           'NLS_NUMERIC_CHARACTERS='',.'''
       )
FROM dual;
```

For month names:

```sql
SELECT TO_DATE(
           '14-NOV-2026',
           'DD-MON-YYYY',
           'NLS_DATE_LANGUAGE=ENGLISH'
       )
FROM dual;
```

This scopes the convention to **a single expression**, making SQL self-documenting without mutating state for the entire session.

### 10.4. ALTER SESSION is not a substitute for explicit format models

You can adjust session settings in test environments:

```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY';
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';
```

Yet SQL relying on implicit conversion still behaves differently when executed on another session. Especially in connection pools, reusing sessions means NLS changes made by a previous request can leak into subsequent requests if not reset.

`ALTER SESSION` is useful for testing dependencies or meeting controlled operational conventions. For application logic, prefer **explicit format models and typed binds**.

## 11. Handling conversion errors

Explicit conversions control how values are parsed, but they do not turn invalid data into valid data. A string can match a structural format yet contain an impossible value or exceed the target type's limits.

### 11.1. Invalid number errors

```sql
SELECT TO_NUMBER('12A', '999')
FROM dual;
```

A string with invalid characters can raise:

```text
ORA-01722: invalid number
```

Causes include unexpected characters, mismatched decimal/group separators, an incorrect format model, or corrupted input data.

### 11.2. Datetime mismatch errors

```sql
SELECT TO_DATE('14/11/2026', 'FXYYYY-MM-DD')
FROM dual;
```

The string uses day/month/year order while the format requires year-month-day, causing a mismatch. Related errors include:

- `ORA-01861`: literal does not match format string.
- `ORA-01843`: not a valid month.
- `ORA-01830`: date format picture ends before converting entire input string.
- `ORA-01847`: day of month must be between 1 and last day of month.

Exact error messages depend on input data and format models.

### 11.3. Target precision/length errors

```sql
SELECT CAST(123456 AS NUMBER(4))
FROM dual;
```

Values exceeding declared precision raise numeric overflow errors, commonly `ORA-01438` in precision-bounded columns/types.

When writing character data into a column that is too short, you can encounter `ORA-12899: value too large for column`. Do not check only character length with `LENGTH` if the column uses byte semantics and the database character set includes multi-byte characters; check `LENGTHB` and column metadata too.

### 11.4. Separate format validation, parsing, and business validation

An ingestion pipeline should follow clear stages:

```text
Input text
      |
      v
Validate format contract
      |
      v
Parse with explicit format model / NLS
      |
      v
Validate target type, precision, range
      |
      v
Validate business rules
      |
      v
Bind typed value and write to database
```

For example, with monetary amounts:

1. Does `'1.234,56'` match the partner's published format?
2. Does `TO_NUMBER` parse it cleanly under that format/NLS?
3. Is the value within the permitted monetary range?
4. Does it have the allowed number of decimal places for that currency?
5. Will it fit into the target `NUMBER(12,2)` column?

Do not lump everything into a single `CAST` and only catch a generic exception at the end.

### 11.5. VALIDATE_CONVERSION on supported versions

Recent Oracle versions support `VALIDATE_CONVERSION` to test whether an expression can be converted to a target type:

```sql
SELECT VALIDATE_CONVERSION('123.45' AS NUMBER) AS can_convert_number,
       VALIDATE_CONVERSION('12A' AS NUMBER) AS cannot_convert_number
FROM dual;
```

It typically returns `1` when convertible and `0` when not convertible. This function is available in Oracle versions supporting the feature (commonly 12.2 and later); verify your database version before using it.

NULL input is treated as convertible to the target type per function rules, so `VALIDATE_CONVERSION(NULL AS NUMBER)` does not replace `IS NULL`. Always check for missing data separately.

## 12. Common safe conversion patterns

### 12.1. Parsing numbers from CSV with decimal commas

```sql
SELECT TO_NUMBER(
           amount_text,
           'FM9G999G999D99',
           'NLS_NUMERIC_CHARACTERS='',.'''
       ) AS amount_value
FROM import_rows;
```

This assumes `AMOUNT_TEXT` uses periods for grouping and commas for decimals. If a source follows another convention, adjust format/NLS to match the contract. Never guess based on the job server's OS locale.

### 12.2. Parsing date strings by API format

```sql
SELECT TO_DATE(date_text, 'FXYYYY-MM-DD') AS event_date
FROM import_rows;
```

If the source sends day-month-year:

```sql
SELECT TO_DATE(date_text, 'FXDD/MM/YYYY') AS event_date
FROM import_rows;
```

Each source should have one clearly defined format model. Never allow a single source column to mix multiple date formats without a way to distinguish them.

### 12.3. Parsing timestamps with fractional seconds

```sql
SELECT TO_TIMESTAMP(
           timestamp_text,
           'FXYYYY-MM-DD"T"HH24:MI:SS.FF6'
       ) AS event_timestamp
FROM import_rows;
```

If the data includes an offset, convert to `TIMESTAMP WITH TIME ZONE` using `TO_TIMESTAMP_TZ` with a format model covering the timezone component.

### 12.4. Formatting output with fixed conventions

```sql
SELECT TO_CHAR(
           amount,
           'FM9G999G999D00',
           'NLS_NUMERIC_CHARACTERS='',.'''
       ) AS amount_display,
       TO_CHAR(
           created_at,
           'YYYY-MM-DD HH24:MI:SS'
       ) AS created_at_display
FROM orders;
```

This works well for text reports. If the application will process the data further, return native numeric/datetime types via the driver instead of converting everything to strings in the database.

## 13. Conversions in Java/JDBC

In Java, values are already typed in the application layer. For example:

| Java | Meaning | Typical Oracle Mapping |
|---|---|---|
| `BigDecimal` | Exact decimal number | `NUMBER` |
| `Long`/`Integer` | Integer | Appropriate `NUMBER` |
| `String` | Text | `VARCHAR2`/`NVARCHAR2` per schema |
| `LocalDate` | Calendar date | Appropriate mapping to `DATE` |
| `LocalDateTime` | Datetime without timezone | `TIMESTAMP` |
| `OffsetDateTime` | Datetime with offset | `TIMESTAMP WITH TIME ZONE` if driver supports |

### 13.1. Binding numbers with BigDecimal

```java
import java.math.BigDecimal;
import java.sql.PreparedStatement;

String sql = "INSERT INTO payments (payment_id, amount) VALUES (?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, paymentId);
    ps.setBigDecimal(2, new BigDecimal("1234.56"));
    ps.executeUpdate();
}
```

Use `BigDecimal` for decimal numbers requiring exactness, such as money. Avoid constructing `BigDecimal` from a `double` that already carries binary rounding error when you need to preserve exact decimal input; constructing from a String is the clean choice.

### 13.2. Parsing text at the application boundary

If an API receives `'1.234,56'` under a known locale convention, Java can parse it in the ingestion layer per the defined locale/contract and bind a `BigDecimal`. Alternatively, the system can load text into a staging table and use `TO_NUMBER` in SQL with explicit format and NLS parameters. Both approaches require consistent input contracts.

Never send locale-dependent strings and let Oracle guess:

```java
// Unsafe: never concatenate user text into SQL:
String sql = "INSERT INTO payments(amount) VALUES ('" + amountText + "')";
```

Instead, parse and bind:

```java
String sql = "INSERT INTO payments(amount) VALUES (?)";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, parsedAmount);
    ps.executeUpdate();
}
```

### 13.3. Binding typed datetimes

Example for a `TIMESTAMP` column:

```java
import java.sql.PreparedStatement;
import java.sql.Timestamp;
import java.time.LocalDateTime;

LocalDateTime createdAt = LocalDateTime.of(2026, 11, 14, 16, 30, 15);

String sql = "INSERT INTO events (event_id, created_at) VALUES (?, ?)";
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, eventId);
    ps.setTimestamp(2, Timestamp.valueOf(createdAt));
    ps.executeUpdate();
}
```

This snippet assumes the target column is a non-timezone timestamp and the driver is configured accordingly. For `DATE`, `TIMESTAMP WITH TIME ZONE`, or `TIMESTAMP WITH LOCAL TIME ZONE`, select the mapping and API matching the semantics you need to preserve. Never format `LocalDateTime` into `'DD/MM/YYYY HH24:MI:SS'` and concatenate it into SQL.

### 13.4. Reading results into Java types

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT amount FROM payments WHERE payment_id = ?")) {
    ps.setLong(1, paymentId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigDecimal amount = rs.getBigDecimal("amount");
        }
    }
}
```

`getBigDecimal` suits decimal values requiring precision. If a column is nullable, check `wasNull()` when using primitive getters; for object types like `BigDecimal`, JDBC returns `null` for SQL NULL.

## 14. Conversions and query optimization

### 14.1. Convert the parameter, never the column unnecessarily

Suppose `orders.created_at` has an index. Avoid:

```sql
WHERE TO_CHAR(created_at, 'YYYY-MM-DD') = '2026-11-14'
```

Prefer:

```sql
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15'
```

If the source only provides a string:

```sql
WHERE created_at >= TO_DATE(:p_day, 'FXYYYY-MM-DD')
  AND created_at <  TO_DATE(:p_day, 'FXYYYY-MM-DD') + 1
```

Better yet, parse the parameter once in the application and bind two typed endpoints. When a business requirement genuinely calls for a conversion expression on a column, you can evaluate a function-based index, designed and tested separately.

### 14.2. Never use TO_CHAR to compare numbers

```sql
-- Avoid turning NUMBER into text just to filter:
WHERE TO_CHAR(amount, '999D99') = '123,45'
```

Text formatting depends on NLS, and wrapping the column prevents normal index use. Compare numerically:

```sql
WHERE amount = 123.45
```

Or bind a `BigDecimal` from the application.

### 14.3. Conversions in JOINs can be costly or fail

If `customers.customer_id` is NUMBER while `orders.customer_id_text` is VARCHAR2, the join condition:

```sql
ON customers.customer_id = orders.customer_id_text
```

can force Oracle to convert types. If the text column contains even one non-numeric value, conversion fails. For long-term design, join keys should share identical data types. When schema changes cannot happen immediately, clean source data, control conversions, and inspect the execution plan.

## 15. Common conversion errors

| Error | Common Scenario | Resolution |
|---|---|---|
| `ORA-01722: invalid number` | String fails to parse as number or NLS/format mismatch | Inspect raw value, `TO_NUMBER`, format, and `NLS_NUMERIC_CHARACTERS` |
| `ORA-01861: literal does not match format string` | Datetime string mismatches format model | Verify ordering, separators, and use `FX` for strict checks |
| `ORA-01843: not a valid month` | Invalid month number or month name mismatches `NLS_DATE_LANGUAGE` | Check month and language settings |
| `ORA-01830: date format picture ends before converting entire input string` | Format model stops before consuming the entire string | Add time/fractional/offset elements or fix input |
| `ORA-01847: day of month must be between 1 and last day of month` | Day does not exist in that month | Check calendar validity |
| `ORA-01438` | Numeric value exceeds column/type precision | Check precision, scale, and source value |
| `ORA-12899` | String exceeds column length | Check `DATA_LENGTH`, `CHAR_LENGTH`, byte semantics, and encoding |
| `ORA-00932: inconsistent datatypes` | Incompatible types in expressions, UNION, or CASE | Use `CAST` to align types intentionally |

### Troubleshooting checklist when an error occurs

1. **What is the source type?** String, NUMBER, DATE, or TIMESTAMP?
2. **What should the target type be?** Do not go solely by display format.
3. **Is a format model needed?** If the source is a formatted date/number string, specify the format explicitly.
4. **Which NLS settings are active?** Decimal markers, grouping, month language, and session formats.
5. **Is the value valid on the calendar or in the numeric domain?** Matching a format does not guarantee valid data.
6. **Does casting lose data?** For example, TIMESTAMP to DATE drops fractional seconds.
7. **Is conversion applied to the parameter or the column?** Watch for failures on legacy rows and index impact.
8. **Can the app bind the right type directly?** If so, avoid re-parsing strings in the database.

## 16. Comprehensive practice lab

The steps below use `DUAL` to test conversions, then create a dedicated table in a practice schema. Never run DDL/DML against production data.

### Step 1. CAST and target types

```sql
SELECT CAST('12345' AS NUMBER) AS number_value,
       CAST(12345 AS VARCHAR2(20)) AS text_value,
       CAST(NULL AS NUMBER(10, 2)) AS typed_null
FROM dual;
```

Inspect the data type of each expression via your SQL client or result metadata.

### Step 2. Parsing numbers under two conventions

```sql
SELECT TO_NUMBER(
           '1,234.56',
           '9G999D99',
           'NLS_NUMERIC_CHARACTERS=''.,'''
       ) AS decimal_dot,
       TO_NUMBER(
           '1.234,56',
           '9G999D99',
           'NLS_NUMERIC_CHARACTERS='',.'''
       ) AS decimal_comma
FROM dual;
```

Both expressions return the same numeric value `1234.56`, parsed from two different text representations.

### Step 3. Formatting numbers into two display styles

```sql
SELECT TO_CHAR(
           1234.5,
           'FM9G999D00',
           'NLS_NUMERIC_CHARACTERS=''.,'''
       ) AS style_dot,
       TO_CHAR(
           1234.5,
           'FM9G999D00',
           'NLS_NUMERIC_CHARACTERS='',.'''
       ) AS style_comma
FROM dual;
```

Illustrative results are `1,234.50` and `1.234,50`, respectively.

### Step 4. Parsing dates and timestamps

```sql
SELECT TO_DATE('14/11/2026', 'FXDD/MM/YYYY') AS parsed_date,
       TO_TIMESTAMP(
           '2026-11-14T16:30:15.123456',
           'FXYYYY-MM-DD"T"HH24:MI:SS.FF6'
       ) AS parsed_timestamp
FROM dual;
```

Verify result types: the first column is DATE, the second is TIMESTAMP.

### Step 5. Controlling month-name language

```sql
SELECT TO_DATE(
           '14-NOV-2026',
           'FXDD-MON-YYYY',
           'NLS_DATE_LANGUAGE=ENGLISH'
       ) AS parsed_month
FROM dual;
```

Try omitting the language parameter in a session with a different `NLS_DATE_LANGUAGE` to observe the difference if your environment is configured for it.

### Step 6. Create a test table

```sql
CREATE TABLE demo_conversion (
    id           NUMBER PRIMARY KEY,
    amount       NUMBER(12, 2),
    event_date   DATE,
    event_time   TIMESTAMP(6),
    amount_text  VARCHAR2(30),
    date_text    VARCHAR2(30)
);
```

### Step 7. Insert explicitly converted data

```sql
INSERT INTO demo_conversion (
    id, amount, event_date, event_time, amount_text, date_text
) VALUES (
    1,
    TO_NUMBER(
        '1.234,56',
        '9G999D99',
        'NLS_NUMERIC_CHARACTERS='',.'''
    ),
    TO_DATE('14/11/2026', 'FXDD/MM/YYYY'),
    TO_TIMESTAMP(
        '2026-11-14 16:30:15.123456',
        'FXYYYY-MM-DD HH24:MI:SS.FF6'
    ),
    '1.234,56',
    '14/11/2026'
);

COMMIT;
```

The insert parses values with explicit rules; it does not require `NLS_DATE_FORMAT` to be `DD/MM/YYYY`.

### Step 8. Format output using format models

```sql
SELECT id,
       TO_CHAR(
           amount,
           'FM9G999D00',
           'NLS_NUMERIC_CHARACTERS='',.'''
       ) AS amount_display,
       TO_CHAR(event_date, 'YYYY-MM-DD') AS date_display,
       TO_CHAR(event_time, 'YYYY-MM-DD HH24:MI:SS.FF6') AS time_display
FROM demo_conversion;
```

### Step 9. Inspect column metadata

```sql
SELECT column_name,
       data_type,
       data_length,
       data_precision,
       data_scale
FROM user_tab_columns
WHERE table_name = 'DEMO_CONVERSION'
ORDER BY column_id;
```

Metadata confirms the target column types match the design.

### Step 10. Clean up the practice table

Only when you are certain this is a table you created and no longer need the data:

```sql
DROP TABLE demo_conversion PURGE;
```

`DROP TABLE ... PURGE` permanently drops the object and data, bypassing the recycle bin; it is DDL with an implicit commit. Never run cleanup commands on business tables or shared objects.

## 17. Practical rules when writing CAST and format models

| Scenario | Recommended | Avoid |
|---|---|---|
| Need an explicit NUMBER type on an expression | `CAST(expr AS NUMBER(p,s))` | Relying on unclear inferred types |
| Need to parse a locale-specific numeric string | `TO_NUMBER(text, fmt, nlsparam)` | `CAST(text AS NUMBER)` when input format varies |
| Need to parse a date string | `TO_DATE(text, fmt, nlsparam)` | Comparing DATE to NLS-dependent strings |
| Need to parse a timestamp with fractional seconds | `TO_TIMESTAMP(text, fmt, nlsparam)` | Parsing via DATE and expecting fractions to survive |
| Need to parse a timestamp with offset | `TO_TIMESTAMP_TZ` | Dropping offset and storing timezone-less TIMESTAMP |
| Need to output numbers with specific separators | `TO_CHAR(number, fmt, nlsparam)` | `CAST(number AS VARCHAR2)` assuming formatting |
| Need to output standardized datetimes | `TO_CHAR(datetime, fmt, nlsparam)` | Relying on client default formatting |
| Need to filter a single day on a DATE column | `>=` and `<` bounds with typed values | `TO_CHAR(column, ...) = '...'` |
| Java already holds BigDecimal or temporal types | Bind typed values via JDBC | Concatenating strings into SQL for Oracle to parse |
| Need NULL in UNION/CASE | `CAST(NULL AS target_type)` | Letting Oracle guess incompatible types |

Good SQL tells the reader **where values come from, which rules parse them, what type the result holds, and how errors are handled**.

## 18. Self-check questions

**Question 1.** How do `CAST('123' AS NUMBER)` and `TO_NUMBER('123','999')` differ in purpose?

**Answer:** CAST converts an expression to a target data type; TO_NUMBER parses text according to a specific numeric format model and optionally accepts NLS parameters.

**Question 2.** Can you use `CAST('14/11/2026' AS DATE)` to always parse DD/MM/YYYY?

**Answer:** No. CAST does not accept a separate format model; string-to-date conversion can depend on NLS. Use `TO_DATE('14/11/2026','FXDD/MM/YYYY')`.

**Question 3.** Do `D` and `G` in number formats always mean period and comma?

**Answer:** No. `D` is the decimal marker and `G` is the group separator per NLS; you can control them with `NLS_NUMERIC_CHARACTERS`.

**Question 4.** When parsing `1.234,56` under Vietnamese conventions, how should `NLS_NUMERIC_CHARACTERS` be set?

**Answer:** The first character is the decimal marker `,`, and the second is the group separator `.`, so `',.'`.

**Question 5.** Does `TO_DATE` preserve milliseconds?

**Answer:** No. DATE is only precise to the second. Use `TO_TIMESTAMP` when fractional seconds are needed.

**Question 6.** Why is `TO_CHAR(created_at, 'YYYY-MM-DD')` in a WHERE clause often suboptimal?

**Answer:** Applying a function to the column before comparison can block normal index usage and forces string-based filtering. Use range predicates on DATE/TIMESTAMP values.

**Question 7.** Does `CAST(NULL AS NUMBER)` return 0?

**Answer:** No. It remains NULL, typed as NUMBER.

**Question 8.** What does `FX` do?

**Answer:** It enforces exact matching between the input string and the format model when parsing datetimes.

**Question 9.** In format model `HH24:MM:SS`, which element is wrong?

**Answer:** `MM` is month; minutes must use `MI`.

**Question 10.** Why should a Java application bind `BigDecimal` instead of splicing `'1.234,56'` into SQL?

**Answer:** Binding separates data from SQL syntax, prevents SQL injection, and avoids forcing Oracle to guess formatting from session NLS settings.

**Question 11.** Does converting TIMESTAMP to DATE preserve fractional seconds?

**Answer:** No. DATE retains precision only down to the second.

**Question 12.** Does `VALIDATE_CONVERSION(NULL AS NUMBER)` replace `IS NOT NULL`?

**Answer:** No. That function checks convertibility; NULL is considered convertible under its rules. To check for missing data, use `IS NULL`/`IS NOT NULL`.

## 19. Conclusion

`CAST` **converts an expression to a target data type**; `TO_NUMBER`, `TO_DATE`, `TO_TIMESTAMP`, and `TO_TIMESTAMP_TZ` **parse text using a format model**; and `TO_CHAR` **formats numeric or datetime values into strings**. These tools serve distinct roles and should not be substituted for one another mechanically.

When inputs are text, specify format models explicitly, include NLS parameters whenever decimal markers, group separators, or month names depend on locale, and validate bad data before writing. When inputs are already typed in Java, prefer **binding the proper type via JDBC** instead of converting to strings and re-parsing. Minimize implicit conversions, avoid wrapping indexed columns in formatting functions inside filter predicates unnecessarily, and always account for potential loss of precision, fractional seconds, or timezone metadata when converting to a target type.
