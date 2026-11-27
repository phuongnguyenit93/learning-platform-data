# DATE_FORMAT, STR_TO_DATE, and Explicit Input Formatting

Dates and times often pass through many formats: a user enters `19/11/2026`, an API sends `2026-11-19`, MySQL stores a `DATE` or `DATETIME` value, and a report needs to display `19 November 2026`. Without an explicit format at every boundary, date strings can suffer swapped day and month values, lost fractional seconds, or time zone shifts.

MySQL provides two common functions for this task. `DATE_FORMAT()` formats a date/time value into a string for display or export. `STR_TO_DATE()` parses a string according to a specified format and returns a temporal value. They operate in opposite directions, though neither replaces proper temporal column design and input validation.

This lesson belongs to the `DATABASE_MYSQL` module, focusing on designing and processing date and time data in queries, applications, reports, and operations. The goal is to use explicit formats, avoid relying on default session or server language formats, and preserve range filtering and index usage.

After this lesson, you can:

- Distinguish output formatting with `DATE_FORMAT()` from input parsing with `STR_TO_DATE()`.
- Choose the right format string for year, month, day, hour, minute, second, and microsecond.
- Handle ambiguous date strings using explicit input formats.
- Understand the impact of locale, two-digit years, and week formats.
- Detect malformed data, invalid dates, and trailing characters.
- Handle time zones properly with `TIMESTAMP`, `DATETIME`, and `CONVERT_TZ()`.
- Write date/time filter predicates that preserve index usage.
- Choose the right layer for conversion between MySQL, JDBC, and Java.

## 1. Two Functions with Different Purposes

| Function | Conversion Direction | Return Type | Use When |
| --- | --- | --- | --- |
| `DATE_FORMAT(date, format)` | Date/time value → string | String | Display, reporting, CSV export, or label generation |
| `STR_TO_DATE(str, format)` | String → date/time value | `DATE`, `TIME`, or `DATETIME` depending on format | Importing text data in a known format |

Example:

```sql
SELECT DATE_FORMAT(DATE '2026-11-19', '%d/%m/%Y') AS display_date;
-- Result: 19/11/2026

SELECT STR_TO_DATE('19/11/2026', '%d/%m/%Y') AS parsed_date;
-- Result: 2026-11-19
```

`DATE_FORMAT()` returns a string, so after formatting you are no longer operating on a pure `DATE` value in that expression. `STR_TO_DATE()` produces a temporal value so MySQL can compare, sort, and perform date/time arithmetic.

In applications, if data already uses a Java type such as `LocalDate`, `LocalDateTime`, or `Instant`, pass it via JDBC with its corresponding type. Only use `STR_TO_DATE()` when the input is genuinely a text string that needs parsing.

## 2. Basic Syntax

### 2.1. DATE_FORMAT()

Syntax:

```sql
DATE_FORMAT(date_value, format_string)
```

Example with `DATETIME`:

```sql
SELECT DATE_FORMAT(
    '2026-11-19 14:35:08',
    '%Y-%m-%d %H:%i:%s'
) AS formatted_value;
```

The result is the string `2026-11-19 14:35:08`. Format specifiers are replaced with the corresponding components of the date/time value.

### 2.2. STR_TO_DATE()

Syntax:

```sql
STR_TO_DATE(date_string, format_string)
```

Example with Vietnamese day/month/year date format:

```sql
SELECT STR_TO_DATE('19/11/2026', '%d/%m/%Y') AS parsed_value;
```

The result is the date value `2026-11-19`. The format must accurately describe the order and formatting of the input string. The string `05/09/2026` does not itself state whether `05` is the day or month; only the format specified by the data contract resolves that.

### 2.3. Return Type of STR_TO_DATE()

MySQL determines the result type based on the components present in the format:

- Date components only, no time components: returns `DATE`.
- Time components only, no date components: returns `TIME`.
- Both date and time components: returns `DATETIME`.

Parts not specified in the format may default to 0. Therefore, do not use a format with only `%m/%d` to construct a complete business date if year is mandatory. Explicitly specify all required components and validate inputs.

## 3. Common Format Specifiers

MySQL format strings use a `%` symbol followed by a character. These specifiers have specific meanings; they do not match Java's `DateTimeFormatter` patterns.

### 3.1. Year, Month, and Day

| Specifier | Meaning | Example |
| --- | --- | --- |
| `%Y` | 4-digit year | `2026` |
| `%y` | 2-digit year | `26` |
| `%m` | 2-digit month (`00`–`12`) | `11` |
| `%c` | Numeric month without leading zero | `11` |
| `%M` | Full month name per locale | `November` |
| `%b` | Abbreviated month name per locale | `Nov` |
| `%d` | 2-digit day of month (`00`–`31`) | `09` |
| `%e` | Day of month without leading zero | `9` |
| `%D` | Day of month with English suffix | `9th` |
| `%j` | Day of year (`001`–`366`) | `323` |

### 3.2. Hour, Minute, Second, and Fractional Parts

| Specifier | Meaning | Example |
| --- | --- | --- |
| `%H` | 24-hour, 2 digits (`00`–`23`) | `14` |
| `%k` | 24-hour, without leading zero | `14` |
| `%h`, `%I` | 12-hour (`01`–`12`) | `02` |
| `%l` | 12-hour, without leading zero | `2` |
| `%i` | Minutes (`00`–`59`) | `35` |
| `%s`, `%S` | Seconds (`00`–`59`) | `08` |
| `%f` | Microseconds, 6 digits | `123456` |
| `%p` | AM or PM indicator | `PM` |
| `%r` | 12-hour time as `hh:mm:ss AM/PM` | `02:35:08 PM` |
| `%T` | 24-hour time as `hh:mm:ss` | `14:35:08` |

Example with microseconds:

```sql
SELECT DATE_FORMAT(
    '2026-11-19 14:35:08.123456',
    '%Y-%m-%d %H:%i:%s.%f'
) AS value_with_microseconds;
```

For `DATETIME(3)` or `TIMESTAMP(3)` columns, fractional precision is millisecond. `%f` represents microseconds with 6 digits; values with lower precision appear zero-padded in the trailing digits.

### 3.3. Weekday and Week of Year

| Specifier | Meaning |
| --- | --- |
| `%a` | Abbreviated weekday name per locale |
| `%W` | Full weekday name per locale |
| `%w` | Weekday number: Sunday = 0 through Saturday = 6 |
| `%U` | Week of year (`00`–`53`), Sunday as first day of week |
| `%u` | Week of year (`00`–`53`), Monday as first day of week |
| `%V` | Week (`01`–`53`), Sunday as first day of week; used with `%X` |
| `%X` | Year for the week starting on Sunday; used with `%V` |
| `%v` | Week (`01`–`53`), Monday as first day of week; used with `%x` |
| `%x` | Year for the week starting on Monday; used with `%v` |

Do not confuse the calendar year `%Y` with the week-based year `%X` or `%x`. A date in early January may belong to the last week of the previous week-year; a date in late December may belong to the first week of the next week-year. When reporting by ISO week or business week conventions, choose the matching specifier pair and test at year boundaries.

### 3.4. Literal Characters and Percent Sign

Non-specifier characters in the format are normally preserved as delimiters:

```sql
SELECT DATE_FORMAT(NOW(), '%d/%m/%Y at %H:%i:%s');
```

To display a literal percent sign `%`, use `%%`:

```sql
SELECT DATE_FORMAT(NOW(), 'Processed 100%% on %d/%m/%Y');
```

Do not copy Java format strings directly into MySQL without translating specifiers. For example, Java uses `yyyy-MM-dd`, whereas MySQL uses `%Y-%m-%d`.

## 4. Locale and Month/Weekday Names

The `%M`, `%b`, `%W`, and `%a` specifiers depend on the session's `lc_time_names` locale. Check the current value:

```sql
SELECT @@session.lc_time_names;
```

You can change the session locale if supported by the server:

```sql
SET lc_time_names = 'en_US';
SELECT DATE_FORMAT('2026-11-19', '%W, %d %M %Y');
```

Different locales return different month and weekday names. Supported locales depend on the MySQL installation; check documentation and valid values in your deployment environment. Never assume the server default locale is Vietnamese or matches the application's locale.

For input data containing month names, `STR_TO_DATE()` also requires a matching format and locale. For instance, `19 November 2026` requires `%d %M %Y` and a locale matching `lc_time_names`. If a system accepts data from multiple sources or languages, prefer numeric ISO inputs to avoid locale dependencies.

## 5. Explicit Input Formats

### 5.1. Never Rely on Implicit Day/Month Order

The following strings are all ambiguous without an explicit format:

| String | Possible Misinterpretation |
| --- | --- |
| `05/09/2026` | September 5 or May 9 |
| `03-04-26` | Day/month/year or month/day/year; 2-digit year also follows mapping rules |
| `11/12/2026` | December 11 or November 12 |

Always mandate the format in API contracts, import files, or UI inputs. Do not guess the format from sample values or the host machine's locale.

### 5.2. Examples of Common Formats

| Input | Explicit Format | Expected Result |
| --- | --- | --- |
| `2026-11-19` | `%Y-%m-%d` | `2026-11-19` |
| `19/11/2026` | `%d/%m/%Y` | `2026-11-19` |
| `11/19/2026` | `%m/%d/%Y` | `2026-11-19` |
| `19-11-2026 14:35` | `%d-%m-%Y %H:%i` | `2026-11-19 14:35:00` |
| `2026-11-19T14:35:08` | `%Y-%m-%dT%H:%i:%s` | `2026-11-19 14:35:08` |
| `2026-11-19 14:35:08.123456` | `%Y-%m-%d %H:%i:%s.%f` | Preserves microseconds |
| `02:35:08 PM` | `%r` | `14:35:08` |

Query example:

```sql
SELECT
    STR_TO_DATE('19/11/2026', '%d/%m/%Y') AS date_vn,
    STR_TO_DATE('11/19/2026', '%m/%d/%Y') AS date_us,
    STR_TO_DATE('2026-11-19T14:35:08', '%Y-%m-%dT%H:%i:%s') AS datetime_iso;
```

The format string must match the component order. The `T` in the ISO string example is an explicit literal separator, not a MySQL time token.

### 5.3. Prefer 4-Digit Years

The `%y` specifier applies a 2-digit year mapping rule: `00`–`69` maps to `2000`–`2069`, while `70`–`99` maps to `1970`–`1999`. This rule can misinterpret historical data if a source sends abbreviated years.

For dates exchanged between systems, require 4-digit years and use `%Y`. Only use `%y` when an external data contract strictly mandates 2-digit years and both sides agree on the century mapping rule.

## 6. String Validation and Handling Invalid Dates

`STR_TO_DATE()` helps parse strings, but it does not completely replace input validation. Strings can have swapped fields, missing parts, trailing garbage characters, or nonexistent calendar dates.

### 6.1. Do Not Only Check for Non-NULL Results

Example input:

```sql
SELECT STR_TO_DATE('2026-11-19xyz', '%Y-%m-%d') AS parsed_value;
```

Scanning may stop once the format ceases to match; trailing characters at the end should not be treated as validated. Thus, simply checking `IS NOT NULL` does not prove the entire input string is valid.

For fixed numeric formats with padding rules, you can validate both string structure and post-parse value. For example, with canonical `YYYY-MM-DD`, validation can include:

1. Verify the string has exactly 10 characters with digits and hyphens at the expected positions.
2. Parse using `STR_TO_DATE(raw_value, '%Y-%m-%d')`.
3. Confirm a temporal value was produced.
4. Format back using `DATE_FORMAT(parsed_value, '%Y-%m-%d')` and compare against the original string to catch trailing characters or non-canonical forms.

Round-tripping is a helpful check for fixed numeric formats, though it does not replace date-range validation and must handle parse errors according to your MySQL version.

Example with a properly structured string:

```sql
SET @raw_date = '2026-11-19';
SET @parsed_date = STR_TO_DATE(@raw_date, '%Y-%m-%d');

SELECT
    @parsed_date AS parsed_date,
    DATE_FORMAT(@parsed_date, '%Y-%m-%d') AS canonical_value,
    BINARY @raw_date = BINARY DATE_FORMAT(@parsed_date, '%Y-%m-%d') AS exact_match;
```

`exact_match = 1` indicates the string matches this canonical representation. This example only illustrates checking the parsed string; on versions that might return out-of-range dates, still validate calendar legality separately.

### 6.2. Nonexistent Dates and Version Differences

For example, `2026-02-30` looks like a valid date shape, yet February 30 does not exist. How MySQL handles this depends on version:

- From MySQL 8.0.35 onward, `STR_TO_DATE()` performs full range checking and raises an error if the resulting date is invalid.
- Prior to MySQL 8.0.35, range checking was incomplete; some invalid dates could be returned without immediate rejection by the function.

Never rely solely on the function returning a value to conclude a date is valid across all versions. Test behavior on your target server version, inspect warnings/errors, and validate dates in the application layer or import pipeline.

Intentional lab test example:

```sql
SELECT STR_TO_DATE('2026-02-30', '%Y-%m-%d');
SHOW WARNINGS;
```

On newer versions, the `SELECT` statement may abort with an error before `SHOW WARNINGS` runs; catch errors in the client or application to record results. Never use invalid-date examples in production write flows.

### 6.3. Staging Tables for Imported Data

When importing CSVs or files from external systems, preserve raw strings in a staging table so invalid data can be investigated:

```sql
CREATE TABLE import_staging_dates (
    row_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_value VARCHAR(100) NOT NULL,
    PRIMARY KEY (row_id)
) ENGINE = InnoDB;

INSERT INTO import_staging_dates (source_value) VALUES
('2026-11-19'),
('2026-02-30'),
('19/11/2026'),
('2026-11-19-extra');
```

Define a dedicated parser for each source format. Do not try multiple ambiguous formats and take whichever succeeds first. In MySQL 8.0.35+, an out-of-range value can cause a query containing `STR_TO_DATE()` to fail with an error; the import pipeline must catch errors per batch or pre-parse in the application so one bad row does not obscure which row failed.

After validation, write clean data into actual `DATE`/`DATETIME` columns. Retain `source_value` in staging or an error table for as long as needed for traceability before cleaning up staging.

## 7. Date/Time, DATETIME, and TIMESTAMP

`DATE_FORMAT()` and `STR_TO_DATE()` operate on temporal values, yet do not carry full time zone metadata by themselves.

### 7.1. DATETIME Does Not Auto-Convert Time Zones

`DATETIME` stores calendar date and time, e.g. `2026-11-19 09:00:00`. When reading or formatting with `DATE_FORMAT()`, MySQL does not automatically shift this value according to the session's `time_zone`. If the application treats the value as local time, store the business time zone convention or an explicit zone ID alongside it.

### 7.2. TIMESTAMP Depends on Session Time Zone

MySQL stores `TIMESTAMP` in UTC and converts to/from the session time zone on write/read. Consequently, the same `TIMESTAMP` column can render differently if sessions use different time zones.

```sql
SELECT
    @@session.time_zone,
    created_at,
    DATE_FORMAT(created_at, '%Y-%m-%d %H:%i:%s') AS formatted_created_at
FROM orders
WHERE order_id = 1001;
```

Set the session time zone explicitly before formatting or exporting data:

```sql
SET time_zone = '+00:00';
SELECT DATE_FORMAT(created_at, '%Y-%m-%d %H:%i:%s')
FROM orders;
```

If a report needs Vietnam time, use an appropriate session timezone or convert explicitly. `CONVERT_TZ()` requires loaded timezone tables to recognize zone names like `Asia/Ho_Chi_Minh`; fixed offsets do not handle a region's DST rules automatically.

```sql
-- Ensure TIMESTAMP is represented in UTC before passing to CONVERT_TZ.
SET time_zone = '+00:00';

SELECT DATE_FORMAT(
    CONVERT_TZ(created_at, '+00:00', 'Asia/Ho_Chi_Minh'),
    '%d/%m/%Y %H:%i:%s'
) AS created_at_vn
FROM orders;
```

If `CONVERT_TZ()` returns `NULL`, check timezone tables and zone names. Do not use a fixed offset string for a region observing DST if data must follow geographic rules.

### 7.3. STR_TO_DATE Does Not Parse Timezone Offsets

`STR_TO_DATE()` formats parse date and time components, not full ISO-8601 timezone offsets. If input strings include `Z` or an offset like `+07:00`, extract and apply the offset explicitly in the application, or parse into `OffsetDateTime`/`Instant` in Java and write to MySQL using UTC convention.

Never strip an offset and store the remaining date/time as if it were UTC. For example, `2026-11-19T09:00:00+07:00` corresponds to `2026-11-19T02:00:00Z`, not `09:00:00Z`.

## 8. Querying by Date/Time While Preserving Index Usage

`DATE_FORMAT()` is handy for presentation, but avoid applying functions to indexed columns inside filter predicates when aiming to use a standard B-tree index.

Avoid:

```sql
SELECT order_id, created_at
FROM orders
WHERE DATE_FORMAT(created_at, '%Y-%m-%d') = '2026-11-19';
```

Applying a function to `created_at` can make the predicate non-sargable for a regular index on that column.

Use a half-open time range instead:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= '2026-11-19 00:00:00'
  AND created_at <  '2026-11-20 00:00:00';
```

The predicate `>= start_of_day` and `< start_of_next_day` captures every instant within the day, including microseconds, without guessing an end-of-day literal like `23:59:59.999999`.

For a date passed from the application, compute the next day in Java or via a clear SQL expression. When the column is `TIMESTAMP`, ensure start/end boundaries are computed in the business time zone and converted into instants matching the connection session.

If grouping results by day for display, `DATE_FORMAT()` can be used in `SELECT` or `GROUP BY`, while evaluating the execution plan and number of rows scanned. For large analytical tables, consider a generated date column or summary table if workloads repeatedly aggregate by day.

## 9. Comparing MySQL Formats with Java

MySQL and Java use two different format pattern systems. Never copy a format string verbatim from one layer to the other.

| Meaning | MySQL | Java `DateTimeFormatter` |
| --- | --- | --- |
| 4-digit year | `%Y` | `uuuu` or `yyyy` depending on purpose |
| 2-digit month | `%m` | `MM` |
| 2-digit day | `%d` | `dd` |
| 24-hour | `%H` | `HH` |
| Minutes | `%i` | `mm` |
| Seconds | `%s` | `ss` |
| 6-digit microseconds | `%f` | `SSSSSS` |
| AM/PM | `%p` | `a` |

Java example:

```java
DateTimeFormatter formatter = DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT);
String displayDate = LocalDate.of(2026, 11, 19).format(formatter);
LocalDate parsedDate = LocalDate.parse("19/11/2026", formatter);
```

For ISO inputs, `LocalDate.parse("2026-11-19")` uses the default ISO formatter. For `Instant`, use an offset-aware formatter or `Instant.parse()` for ISO-8601 UTC strings. Java can parse and validate before writing, preventing unvalidated strings from reaching SQL.

When JDBC already receives a `LocalDate` or `LocalDateTime`, use `PreparedStatement.setObject()` and let the driver transmit the typed temporal value. Do not format into a string only to re-parse inside the same application.

## 10. Recommended Date/Time Processing Pipeline

A reliable pipeline typically consists of these steps:

1. **Define the input contract:** format, locale, time zone, fractional-second precision, and required components.
2. **Validate structure:** length, delimiters, digits, trailing characters, and padding rules.
3. **Parse:** use `STR_TO_DATE()` with an explicit format or parse with the Java Time API.
4. **Validate range:** verify calendar date existence, valid hour/minute/second bounds, and valid offsets/zones.
5. **Normalize:** convert to the semantically correct temporal type; for instants, apply an explicit UTC convention.
6. **Store:** persist into `DATE`, `TIME`, `DATETIME`, or `TIMESTAMP`, never storing display strings as primary data.
7. **Format/export:** use `DATE_FORMAT()` or a Java formatter in the presentation layer according to the recipient's locale.
8. **Query:** filter using time ranges on the raw column to preserve index usage.

Import pipelines should retain raw values and report failing rows. APIs should reject non-conforming formats rather than guessing. Reports should clearly document the timezone and locale used so identical outputs can be reproduced consistently.

## 11. Practice Exercises

1. Use `DATE_FORMAT()` to display a date as `dd/mm/yyyy`, a date with month name, and a timestamp with microseconds.
2. Use `STR_TO_DATE()` to parse `19/11/2026`, `11/19/2026`, and `2026-11-19T14:35:08` using three distinct formats.
3. Test a format with swapped day/month order and explain why input formats must come from a data contract.
4. Compare `%Y` vs `%y` using years `69`, `70`, and `26`, and explain the 2-digit year mapping rule.
5. Change `lc_time_names` to a supported locale and observe `%M`, `%b`, `%W`, and `%a`.
6. Test a string with trailing characters and design a validation check that rejects partially parsed inputs.
7. Test a nonexistent date like `2026-02-30` on your lab MySQL version. Note differences before/after MySQL 8.0.35 and how applications handle errors.
8. Store an instant in a `TIMESTAMP` column, query it in a UTC session and a `+07:00` session, and compare displayed values.
9. Compare `EXPLAIN` output for a predicate using `DATE_FORMAT(created_at, ...)` versus a half-open range on `created_at`.
10. Write Java code to parse `LocalDate` with `DateTimeFormatter`, then persist via JDBC `setObject()`, and compare against parsing with `STR_TO_DATE()`.

## 12. Completion Criteria

You have completed this lesson when you can accurately explain the roles of `DATE_FORMAT()` and `STR_TO_DATE()`, write explicit format strings for dates and times, handle locales and 2-digit years, detect malformed inputs or nonexistent dates per MySQL version, perform intentional time zone conversions, and write date/time filters that preserve index usage. You should also know when to parse in MySQL versus when to use the Java Time API before passing typed values over JDBC.
