# TO_CHAR, TO_NUMBER, TO_DATE, and TO_TIMESTAMP in Oracle Database

## 1. Data type conversion: value-to-string and string-to-value

An application receives a date as text `2026-11-14`, a CSV file has a price `1.234,50`, or an API sends a timestamp `2026-11-14T09:30:15.123456`. Oracle needs to know the **actual data type** before comparing, calculating, or storing it in a column. The four most common conversion functions are:

- **`TO_CHAR`**: converts `NUMBER`, `DATE`, `TIMESTAMP`, or certain other data types into `VARCHAR2` according to a format model.
- **`TO_NUMBER`**: converts a character string into `NUMBER`, with options to specify decimal markers, grouping separators, and currency symbols.
- **`TO_DATE`**: parses a string into a `DATE` value.
- **`TO_TIMESTAMP`**: parses a string into a `TIMESTAMP` value, optionally preserving fractional seconds.

Distinguish **data type conversion** from **display formatting**. A date in the database is not the string `14-NOV-2026`; `DATE` is a datetime value. `TO_CHAR` merely creates a string for display or transmission. Likewise, the number `1234.5` is not the string `1.234,50`; that is just one locale-specific representation.

| Function | Conversion Direction | Return Type | Example |
| --- | --- | --- | --- |
| `TO_CHAR(number, fmt, nlsparam)` | NUMBER → text | `VARCHAR2` | `TO_CHAR(1234.5, 'FM9G999D00')` |
| `TO_CHAR(datetime, fmt, nlsparam)` | DATE/TIMESTAMP → text | `VARCHAR2` | `TO_CHAR(SYSDATE, 'YYYY-MM-DD')` |
| `TO_NUMBER(char, fmt, nlsparam)` | text → NUMBER | `NUMBER` | `TO_NUMBER('1.234,50', '9G999D99', ...)` |
| `TO_DATE(char, fmt, nlsparam)` | text → DATE | `DATE` | `TO_DATE('2026-11-14', 'YYYY-MM-DD')` |
| `TO_TIMESTAMP(char, fmt, nlsparam)` | text → TIMESTAMP | `TIMESTAMP` | `TO_TIMESTAMP('2026-11-14 09:30:15.123', ...)` |

> Content focuses on Oracle Database 19c syntax. Verify format models and NLS behavior against your actual database and driver version. Table names and data examples are illustrative; run DDL/DML only in authorized lab schemas.

## 2. What is a format model?

A format parameter such as `YYYY-MM-DD` or `9G999D00` is called a **format model**. It describes how Oracle parses or presents a value without altering the underlying column data type.

~~~text
NUMBER value 1234.5
       │
       ├── TO_CHAR(..., 'FM9G999D00') ──► '1,234.50'
       │
       └── TO_CHAR(..., 'FM9990D000') ──► '1234.500'

String '2026-11-14'
       │
       └── TO_DATE(..., 'YYYY-MM-DD') ──► a DATE value
                                          no longer a string
~~~

A format model can include these components:

- **Format elements**: `YYYY`, `MM`, `DD`, `HH24`, `MI`, `SS`, `FF`, `9`, `0`, `G`, `D`, etc.
- **Punctuation/literals**: hyphens, colons, dots, or literal text enclosed in double quotes.
- **Modifiers**: `FM` (fill mode), `FX` (format exact), `TM` (text minimum), and other type-specific modifiers.
- **NLS parameters**: govern how decimal markers, currency symbols, or localized month/day names are interpreted.

Never use a NUMBER format model in place of a DATE/TIMESTAMP format model. For example, `YYYY` denotes year in datetime formats, while `9` denotes a digit position in number formats.

## 3. TO_CHAR with NUMBER: formatting numbers as strings

### 3.1. Syntax and purpose

~~~sql
TO_CHAR(number [, format_model [, nlsparam]])
~~~

Example:

~~~sql
SELECT TO_CHAR(1234.5, 'FM9G999D00') AS formatted_number
FROM   dual;
~~~

The result depends on the session's NLS settings. If the decimal marker is a period and the grouping separator is a comma, the output is `1,234.50`. In another environment, `D` and `G` can produce different characters.

**TO_CHAR returns VARCHAR2**, so once formatted, the result is no longer suitable for arithmetic as a NUMBER without converting back. Keep numeric data as NUMBER in the database; format only at presentation or export boundaries.

### 3.2. Common numeric format elements

| Element | Meaning | Example Format / Interpretation |
| --- | --- | --- |
| `9` | Digit position; unused leading positions may become spaces | `9999` |
| `0` | Digit position; pads with 0 when no digit is present | `0000` |
| `D` | Decimal character per `NLS_NUMERIC_CHARACTERS` | `999D99` |
| `G` | Group separator per `NLS_NUMERIC_CHARACTERS` | `9G999G999` |
| `L` | Local currency symbol per NLS | `L9G999D00` |
| `C` | ISO currency symbol per territory | `C999D00` |
| `$` | Dollar sign | `$999D00` |
| `S` | Leading/trailing plus or minus sign | `S9990` |
| `MI` | Trailing minus sign (for negative numbers) | `9990MI` |
| `PR` | Negative numbers enclosed in angle brackets per format model | `9990PR` |
| `EEEE` | Scientific notation | `9.99EEEE` |
| `V` | Multiplies number by power of 10 for display; no decimal point in model | `999V99` |
| `FM` | Suppresses leading/trailing blank padding | `FM9990D00` |

Examples of `9` and `0`:

~~~sql
SELECT TO_CHAR(7, '999')     AS optional_digits,
       TO_CHAR(7, 'FM999')   AS no_padding,
       TO_CHAR(7, 'FM000')   AS zero_padded,
       TO_CHAR(7.5, 'FM990D00') AS fixed_decimals
FROM   dual;
~~~

Conceptual results:

| Format | String |
| --- | --- |
| `999` | May have leading blank padding before `7` |
| `FM999` | `7` |
| `FM000` | `007` |
| `FM990D00` | `7.50` when NLS decimal is a period |

`FM` strips blank padding generated by the format model. It is not a command to "delete every zero everywhere"; use `0` or `9` to control digit positions and verify the output against requirements.

### 3.3. Decimal and group characters: D and G

`D` and `G` read characters from `NLS_NUMERIC_CHARACTERS`. The character pair is specified in the order **decimal character, group separator**.

For example, to explicitly use a period as the decimal separator and a comma as the group separator:

~~~sql
SELECT TO_CHAR(
         1234.5,
         'FM9G999D00',
         'NLS_NUMERIC_CHARACTERS = ''.,'''
       ) AS amount_text
FROM dual;
~~~

Result: `1,234.50`.

To format with a period as the group separator and a comma as the decimal separator:

~~~sql
SELECT TO_CHAR(
         1234.5,
         'FM9G999D00',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS amount_text
FROM dual;
~~~

Result: `1.234,50`.

**Do not confuse format literals with NLS parameters:** `D` is a placeholder for the decimal marker; `G` is a placeholder for the group separator. If you want fixed output independent of session settings, pass the NLS parameter explicitly or follow an agreed transport convention.

### 3.4. Currency: L, C, and $

~~~sql
SELECT TO_CHAR(
         1250000,
         'FML9G999G999D00',
         'NLS_NUMERIC_CHARACTERS = ''.,'' NLS_CURRENCY = ''VND'''
       ) AS local_currency
FROM dual;
~~~

`L` uses `NLS_CURRENCY`, whereas `C` uses the ISO currency symbol for the territory. Do not hardcode one currency format for every country or assume a currency symbol alone uniquely conveys the **currency code**. In multi-currency systems, store the monetary amount and currency code separately (e.g., `amount NUMBER`, `currency_code CHAR(3)`); use formatting only for presentation.

### 3.5. Rounding, width, and negative signs

A format model can round a value to the requested number of decimal places. Example:

~~~sql
SELECT TO_CHAR(12.3456, 'FM990D00',
               'NLS_NUMERIC_CHARACTERS = ''.,''') AS rounded_value
FROM dual;
~~~

The output displays two decimal places, typically `12.35`. **Never use TO_CHAR as a mechanism for storing rounded values**; if business rules require rounding numeric data, use `ROUND(number, scale)` and store NUMBER with the designed precision/scale.

If a value does not fit the format model, Oracle may return a string of `#` characters instead of the number. When you see `####`, check the format model width rather than assuming the column data was corrupted.

### 3.6. Scientific notation and text minimum

~~~sql
SELECT TO_CHAR(1234567, '9.99EEEE') AS scientific_value
FROM dual;
~~~

`EEEE` formats in exponential notation. `TM` (Text Minimum) follows specific rules to produce the shortest suitable numeric representation; do not combine `TM` arbitrarily with every other element. For financial output or fixed-schema files, explicitly specifying decimal digits is usually easier to control.

## 4. TO_NUMBER: converting strings to NUMBER

### 4.1. Syntax

~~~sql
TO_NUMBER(char [, format_model [, nlsparam]])
~~~

Example parsing `'1.234,50'` with period grouping and comma decimal:

~~~sql
SELECT TO_NUMBER(
         '1.234,50',
         '9G999D99',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS amount_number
FROM dual;
~~~

The result is a NUMBER with value `1234.5`, no longer a string. From here you can perform arithmetic:

~~~sql
SELECT TO_NUMBER(
         '1.234,50',
         '9G999D99',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       ) * 2 AS doubled_amount
FROM dual;
~~~

### 4.2. When is a format model needed?

If the string is a simple number matching current NLS conventions, Oracle can convert it via:

~~~sql
SELECT TO_NUMBER('1234.50') FROM dual;
~~~

However, if data arrives from files or applications using different conventions, never rely on session defaults. Specify the format and `NLS_NUMERIC_CHARACTERS` explicitly:

~~~sql
-- Decimal = comma, group = period.
SELECT TO_NUMBER(
         '1.234,50',
         '9G999D99',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       )
FROM dual;

-- Decimal = period, group = comma.
SELECT TO_NUMBER(
         '1,234.50',
         '9G999D99',
         'NLS_NUMERIC_CHARACTERS = ''.,'''
       )
FROM dual;
~~~

A string `1,234` could mean **one thousand two hundred thirty-four** or **one point two three four**, depending on convention. You cannot infer its meaning from the string alone unless the source provides a locale/format contract.

### 4.3. Never use TO_NUMBER to mask dirty input data

~~~sql
SELECT TO_NUMBER('12A5') FROM dual;
~~~

Values that are not valid numeric strings per the format raise a conversion error, commonly `ORA-01722: invalid number`. When data comes from CSVs or legacy columns:

1. Define valid source formats (decimal marker, grouping, currency, negative sign).
2. Separate valid rows from invalid rows before loading.
3. Convert types explicitly, retaining raw values for auditing when needed.
4. Never replace invalid strings with 0 by default, as that turns bad data into a seemingly valid business value.

Oracle 12.2 and later offer `VALIDATE_CONVERSION` to test convertibility in supported cases:

~~~sql
SELECT raw_amount,
       VALIDATE_CONVERSION(
         raw_amount AS NUMBER,
         '9G999D99',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS can_convert
FROM   import_amounts;
~~~

`1` means convertible under the given rules, `0` means not convertible; `NULL` input returns valid per function semantics. Check exact syntax and data type rules for your release. `VALIDATE_CONVERSION` does not validate that a value is **business-valid**, only that it is parseable.

### 4.4. Non-monetary numbers

Do not convert strings containing `$`, `€`, or `₫` by blindly stripping characters and calling `TO_NUMBER`. Know the exact format model and NLS currency, or separate the currency code from the numeric amount. If source numbers use parentheses for negatives, percent signs, or currency symbols, the format model must accurately reflect that syntax.

## 5. DATE, TIMESTAMP, and display strings are three different things

Before using `TO_DATE` and `TO_TIMESTAMP`, distinguish the data types:

| Type | Stored Information | Has Timezone? | Time Precision |
| --- | --- | --- | --- |
| `DATE` | Year, month, day, hour, minute, second | No | Down to the second |
| `TIMESTAMP(p)` | Datetime and fractional seconds | No | `p` fractional second digits, default 6, max 9 |
| `TIMESTAMP WITH TIME ZONE` | Datetime plus timezone offset or region | Yes | Fractional seconds per precision |
| `TIMESTAMP WITH LOCAL TIME ZONE` | Normalized to database timezone; displayed in session timezone | Does not store original timezone separately like TSTZ | Fractional seconds per precision |

Oracle's `DATE` **includes a time component** down to seconds. It is not a date-only type like `DATE` in some other RDBMSs. Inserting `DATE '2026-11-14'` stores midnight as the time. Comparing against a date literal will not match a row with time 14:00 on the same day.

`TIMESTAMP` preserves fractional seconds, but **does not store a timezone**. If the source carries an offset like `+07:00` or a region like `Asia/Ho_Chi_Minh`, choose the appropriate timezone-aware type and function rather than silently discarding timezone info.

## 6. TO_DATE: converting strings to DATE

### 6.1. Syntax

~~~sql
TO_DATE(char [, format_model [, nlsparam]])
~~~

Example:

~~~sql
SELECT TO_DATE('2026-11-14', 'YYYY-MM-DD') AS order_date
FROM dual;
~~~

The result is a `DATE` value. The format model describes the structure of the source string; it does not dictate how clients render the value afterward. SQL Developer and SQL*Plus may display it differently depending on `NLS_DATE_FORMAT`.

### 6.2. Common datetime format elements

| Element | Meaning | Example |
| --- | --- | --- |
| `YYYY` | 4-digit year | `2026` |
| `RRRR` | 2- or 4-digit year with RR compatibility rules | `26`, `2026` |
| `YY` | 2-digit year, tied to current century | `26` |
| `RR` | 2-digit year with century-inference rules | `26` |
| `MM` | Numeric month | `11` |
| `MON` | Abbreviated month name | `NOV` |
| `MONTH` | Full month name | `NOVEMBER` |
| `DD` | Day of month | `14` |
| `DDD` | Day of year | `318` |
| `DY`, `DAY` | Short/full day-of-week name | `SAT`, `SATURDAY` |
| `HH24` | Hour 00–23 | `17` |
| `HH` / `HH12` | Hour 1–12 | `05` |
| `MI` | Minute | `30` |
| `SS` | Second | `45` |
| `AM` / `PM` | Meridian indicator for 12-hour clock | `PM` |
| `IW` | ISO week | `46` |
| `IYYY` | ISO year corresponding to ISO week | `2026` |

Example with time:

~~~sql
SELECT TO_DATE(
         '2026-11-14 17:30:45',
         'YYYY-MM-DD HH24:MI:SS'
       ) AS created_at
FROM dual;
~~~

`DATE` stores hour, minute, and second, but **no fractional seconds**. Do not use `FF` expecting to store fractional seconds in a DATE. If the source contains `17:30:45.123456`, use `TO_TIMESTAMP`.

### 6.3. Dates with month names: NLS date language

The string `14-NOV-2026` uses a month name. `NOV` is interpreted using the session's date language, which can differ if the session uses another language.

~~~sql
SELECT TO_DATE(
         '14-NOV-2026',
         'DD-MON-YYYY',
         'NLS_DATE_LANGUAGE = American'
       ) AS date_value
FROM dual;
~~~

If a source sends `14-NOV-2026` while the session uses a different language, conversion can fail unless `NLS_DATE_LANGUAGE` is specified. For integrations, **numeric ISO strings such as `YYYY-MM-DD` are far less language-dependent**.

### 6.4. FX: enforcing strict format matching

Oracle allows some flexibility in separators or field widths when parsing unless exact matching is enabled. The **`FX`** modifier enforces stricter format model matching.

~~~sql
-- Flexible parsing per format model (FX not enabled).
SELECT TO_DATE('2026-3-8', 'YYYY-MM-DD')
FROM dual;

-- Exact matching: input must match the specified model format.
SELECT TO_DATE('2026-03-08', 'FXYYYY-MM-DD')
FROM dual;
~~~

With `FX`, `'2026-3-8'` fails the two-digit width requirement for month and day in the exact format. When external systems follow a strict contract, `FX` catches malformed input early instead of silently accepting unintended variants. Punctuation and whitespace must also match the exact format.

### 6.5. YY, RR, YYYY, RRRR: avoiding century bugs

**Avoid two-digit years for new data whenever possible.** `YY` interprets years in the current century. `RR` was introduced to handle two-digit years across century boundaries, but its rule depends on the current year.

`RR` pivot rules:

| Last Two Digits of Current Year | Input `00–49` | Input `50–99` |
| --- | --- | --- |
| Current year ends in `00–49` | Current century | Previous century |
| Current year ends in `50–99` | Next century | Current century |

For example, when the current year ends in `00–49`, input `49` resolves to the current century while `50` resolves to the previous century. When the current year ends in `50–99`, input `00` resolves to the next century. Thus, the exact same two-digit string can be interpreted differently in different decades.

- Use `YYYY` for full 4-digit years.
- `RRRR` accepts 2- or 4-digit years with RR semantics.
- Keep `RR` only when supporting legacy 2-digit data with well-defined conventions.

### 6.6. Use ANSI date literals for SQL constants

When a date is a constant in SQL, you can use a literal independent of `NLS_DATE_FORMAT`:

~~~sql
SELECT *
FROM   orders
WHERE  order_date >= DATE '2026-11-01'
AND    order_date <  DATE '2026-12-01';
~~~

`DATE 'YYYY-MM-DD'` is standard Oracle SQL literal syntax. It represents midnight on the specified date. If a time component is needed, use `TO_DATE` with an explicit format or the corresponding timestamp literal.

### 6.7. TO_DATE returns only DATE, not TIMESTAMP or timezone-aware timestamps

Never use `TO_DATE` to parse fractional seconds or timezones. `DATE` has neither fractional precision nor timezone info. For `'2026-11-14 17:30:45.123456'`, use `TO_TIMESTAMP`; if the string includes `+07:00`, consider `TO_TIMESTAMP_TZ`.

## 7. TO_TIMESTAMP: converting strings to TIMESTAMP

### 7.1. Syntax

~~~sql
TO_TIMESTAMP(char [, format_model [, nlsparam]])
~~~

Example with six fractional-second digits:

~~~sql
SELECT TO_TIMESTAMP(
         '2026-11-14 17:30:45.123456',
         'YYYY-MM-DD HH24:MI:SS.FF6'
       ) AS event_timestamp
FROM dual;
~~~

The result has type `TIMESTAMP(6)`. `FF` is the **fractional seconds** format element:

| Format | Meaning |
| --- | --- |
| `FF` | Fractional seconds; precision inferred from input/model per supported rules |
| `FF1` | One fractional digit |
| `FF3` | Three digits (millisecond precision) |
| `FF6` | Six digits (microsecond precision) |
| `FF9` | Nine digits (nanosecond precision) |

If the target column is `TIMESTAMP(3)` while the source provides 9 digits, stored precision is bounded by the column definition. Align precision consistently across source, bind variable, column, and output format.

### 7.2. TO_TIMESTAMP does not store a timezone

The string:

~~~text
2026-11-14 17:30:45.123456
~~~

does not state whether this instant is in UTC, Vietnam time, or another timezone. `TO_TIMESTAMP` produces a `TIMESTAMP` **without a timezone**. If the system needs to pinpoint a global instant, require an offset or region from the source and use `TIMESTAMP WITH TIME ZONE` with `TO_TIMESTAMP_TZ`.

### 7.3. Month names in TIMESTAMP

~~~sql
SELECT TO_TIMESTAMP(
         '14-NOV-2026 05:30:45.123 PM',
         'DD-MON-YYYY HH:MI:SS.FF3 PM',
         'NLS_DATE_LANGUAGE = American'
       )
FROM dual;
~~~

When the format uses `HH`/`HH12`, include `AM`/`PM` if the source uses a 12-hour clock. If using `HH24`, do not append AM/PM as though they belong to the same convention.

## 8. Timestamps with timezone: TO_TIMESTAMP_TZ

`TO_TIMESTAMP` is not appropriate for strings carrying timezone data. Oracle provides **`TO_TIMESTAMP_TZ`** to convert strings into `TIMESTAMP WITH TIME ZONE`.

### 8.1. Strings with a UTC offset

~~~sql
SELECT TO_TIMESTAMP_TZ(
         '2026-11-14 17:30:45.123456 +07:00',
         'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM'
       ) AS event_time_tz
FROM dual;
~~~

`TZH:TZM` represents hours and minutes offset from UTC. `+07:00` records the offset on the submitted value. If the data represents Vietnam time and the source guarantees a `+07:00` offset, it can be parsed explicitly as shown.

### 8.2. Strings with a time zone region

Oracle supports the region format element `TZR` and daylight abbreviation `TZD`:

~~~sql
SELECT TO_TIMESTAMP_TZ(
         '2026-11-14 17:30:45 Asia/Ho_Chi_Minh',
         'YYYY-MM-DD HH24:MI:SS TZR'
       ) AS event_time_tz
FROM dual;
~~~

A region encodes regional timezone rules over time rather than a single static offset. In regions observing daylight saving time, a local wall-clock time can be ambiguous or nonexistent during clock transitions. When the source provides both region and abbreviation, the format can use `TZR TZD`; input values must conform to Oracle's timezone file rules.

### 8.3. Distinguishing the three timestamp types

| Type | Storage Semantics | Display Behavior |
| --- | --- | --- |
| `TIMESTAMP` | Datetime and fractional seconds, no timezone attached | Does not automatically shift with session timezone |
| `TIMESTAMP WITH TIME ZONE` | Datetime plus offset/region | Preserves the value's timezone information |
| `TIMESTAMP WITH LOCAL TIME ZONE` | Normalized to database timezone; does not retain original timezone separately | Oracle converts to session time zone upon retrieval/display |

For example, calling `TO_CHAR` on a `TIMESTAMP WITH LOCAL TIME ZONE` can produce different output across two sessions with different `TIME_ZONE` settings. This is a display behavior, not a modification of stored data.

## 9. TO_CHAR with DATE/TIMESTAMP: generating display strings

### 9.1. Basic datetime formatting

~~~sql
SELECT TO_CHAR(
         SYSDATE,
         'YYYY-MM-DD HH24:MI:SS'
       ) AS current_date_text
FROM dual;
~~~

`SYSDATE` returns a `DATE` based on the database server's operating system clock. The output is a formatted string, not a `DATE`. For timestamps:

~~~sql
SELECT TO_CHAR(
         SYSTIMESTAMP,
         'YYYY-MM-DD"T"HH24:MI:SS.FF3 TZH:TZM'
       ) AS current_timestamp_text
FROM dual;
~~~

`"T"` is a literal letter T inside the format model, handy for producing ISO 8601-like strings. `SYSTIMESTAMP` returns a timestamp with the server environment's timezone/offset.

### 9.2. Language-dependent month and day names

~~~sql
SELECT TO_CHAR(
         DATE '2026-11-14',
         'DD-MON-YYYY',
         'NLS_DATE_LANGUAGE = American'
       ) AS english_date
FROM dual;
~~~

Omitting `NLS_DATE_LANGUAGE` lets `MON`, `MONTH`, `DY`, and `DAY` vary with session settings. For integration files or APIs, numeric ISO formats like `YYYY-MM-DD` are much easier to control.

### 9.3. FM strips blank padding

`DAY` and `MONTH` format models pad day/month names with spaces to a standard width:

~~~sql
SELECT '[' || TO_CHAR(DATE '2026-11-14', 'DAY',
                      'NLS_DATE_LANGUAGE = American') || ']' AS padded_day,
       '[' || TO_CHAR(DATE '2026-11-14', 'FMDAY',
                      'NLS_DATE_LANGUAGE = American') || ']' AS fill_mode_day
FROM dual;
~~~

`FM` toggles fill mode, stripping blank padding. It can affect subsequent format elements in the model; when toggling on and off across segments, Oracle supports repeated `FM` occurrences. Always test actual output, especially when generating fixed-width files.

### 9.4. ISO weeks and day of week

`D` returns the day-of-week number per `NLS_TERRITORY`, so do not assume Sunday is always 1 in every environment. `IW` and `IYYY` represent the ISO week and ISO year; **always pair them together** to avoid mixing calendar years with ISO week years:

~~~sql
SELECT TO_CHAR(DATE '2026-01-01', 'YYYY-MM-DD') AS calendar_date,
       TO_CHAR(DATE '2026-01-01', 'IYYY-IW') AS iso_week
FROM dual;
~~~

Early January days can belong to the final ISO week of the previous year, and vice versa. When reporting by ISO week, never combine `YYYY` with `IW`, because they belong to two different reference systems.

## 10. NLS: the root of hard-to-reproduce conversion bugs

**NLS (National Language Support)** governs how Oracle interprets and formats language- and territory-dependent elements.

| NLS Parameter | Effect |
| --- | --- |
| `NLS_DATE_FORMAT` | Default format for DATE ↔ character conversions in many contexts |
| `NLS_TIMESTAMP_FORMAT` | Default format for TIMESTAMP |
| `NLS_TIMESTAMP_TZ_FORMAT` | Default format for TIMESTAMP WITH TIME ZONE |
| `NLS_DATE_LANGUAGE` | Month/day names and certain datetime text |
| `NLS_NUMERIC_CHARACTERS` | Decimal and group separators |
| `NLS_CURRENCY` | Local currency symbol |
| `NLS_ISO_CURRENCY` | ISO currency symbol per territory |
| `NLS_TERRITORY` | Regional conventions for dates, weeks, currency, and formatting |

Inspect the current session's NLS settings:

~~~sql
SELECT parameter, value
FROM   nls_session_parameters
WHERE  parameter IN (
         'NLS_DATE_FORMAT',
         'NLS_TIMESTAMP_FORMAT',
         'NLS_TIMESTAMP_TZ_FORMAT',
         'NLS_DATE_LANGUAGE',
         'NLS_NUMERIC_CHARACTERS',
         'NLS_CURRENCY',
         'NLS_TERRITORY'
       )
ORDER BY parameter;
~~~

Database, instance, and session settings can differ. Drivers and clients can also override session NLS parameters on connect. Consequently, a query relying on implicit conversion might work on a developer workstation yet fail on an application server.

### 10.1. Changing session NLS to observe the effect

In a lab session:

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD-MON-YYYY';
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';

SELECT SYSDATE,
       TO_CHAR(1234.5, '9G999D00')
FROM dual;
~~~

`ALTER SESSION` affects only the current session. In a connection pool, sessions are reused; never leave an application relying on random NLS state mutated by a prior request. Reset or configure sessions deterministically.

### 10.2. Pass NLS parameters directly in the function

Instead of relying on session state:

~~~sql
SELECT TO_DATE(
         '14-NOV-2026',
         'DD-MON-YYYY',
         'NLS_DATE_LANGUAGE = American'
       )
FROM dual;

SELECT TO_NUMBER(
         '1.234,50',
         '9G999D99',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       )
FROM dual;
~~~

This embeds the **source data contract** directly in the conversion call. For fixed number/date formats in files, always specify format and locale explicitly rather than leaning on session defaults.

## 11. Implicit conversion: Oracle converts automatically, but do not rely on it

Oracle can automatically convert data types during comparisons, concatenation, or expression evaluation. While convenient in quick queries, it introduces NLS dependencies, runtime errors, and index issues.

### 11.1. Comparing DATE with a string

~~~sql
-- Not recommended: string depends on session NLS_DATE_FORMAT.
SELECT *
FROM   orders
WHERE  order_date = '14-NOV-2026';
~~~

Oracle must convert the string to DATE using default rules. If a session uses a different format, the query can raise `ORA-01861`, `ORA-01843`, or yield unintended results.

Write it explicitly:

~~~sql
SELECT *
FROM   orders
WHERE  order_date = TO_DATE('14-NOV-2026',
                            'DD-MON-YYYY',
                            'NLS_DATE_LANGUAGE = American');
~~~

Or using ISO date literals:

~~~sql
SELECT *
FROM   orders
WHERE  order_date >= DATE '2026-11-14'
AND    order_date <  DATE '2026-11-15';
~~~

### 11.2. Comparing NUMBER with a string

~~~sql
-- Avoid relying on implicit conversion:
SELECT *
FROM   invoice_lines
WHERE  amount = '1,234.50';
~~~

A string with grouping separators may fail to parse as expected under `NLS_NUMERIC_CHARACTERS`. It is better to bind a NUMBER from the application or parse the string with an explicit format:

~~~sql
WHERE amount = TO_NUMBER(
  '1,234.50',
  '9G999D99',
  'NLS_NUMERIC_CHARACTERS = ''.,'''
)
~~~

### 11.3. TO_CHAR in string concatenation

When concatenating DATE or NUMBER values to strings, Oracle implicitly converts them to text using default formats:

~~~sql
-- Text result depends on session NLS:
SELECT 'Created at ' || created_at
FROM orders;
~~~

For logs, APIs, and exports, specify the format explicitly:

~~~sql
SELECT 'Created at ' ||
       TO_CHAR(created_at, 'YYYY-MM-DD"T"HH24:MI:SS')
FROM orders;
~~~

### 11.4. Avoid implicit or explicit conversion on indexed columns

Suppose `orders.order_date` is a DATE column with a standard index. The predicate:

~~~sql
WHERE TO_CHAR(order_date, 'YYYY-MM-DD') = '2026-11-14'
~~~

wraps the **column** in a function. Oracle may be unable to use the standard index on `order_date` as intended, unless a matching function-based index exists and the optimizer selects it.

Use a date range instead:

~~~sql
WHERE order_date >= DATE '2026-11-14'
AND   order_date <  DATE '2026-11-15'
~~~

Range predicates leave the column unwrapped and are generally much friendlier to index range scans. If a query genuinely needs `TRUNC(order_date)` or `TO_CHAR(order_date, ...)`, evaluate a function-based index, statistics, and the execution plan.

**Rule of thumb:** convert the **bind/input value once** to match the column's data type; avoid wrapping the column in a function inside predicates whenever unnecessary.

## 12. Comparing dates that include time: use ranges instead of date equality

Suppose `created_at` is a DATE column storing timestamps with time components:

| Value | Belongs to 2026-11-14? |
| --- | --- |
| `2026-11-14 00:00:00` | Yes |
| `2026-11-14 09:15:00` | Yes |
| `2026-11-14 23:59:59` | Yes |
| `2026-11-15 00:00:00` | No |

The predicate:

~~~sql
-- Matches midnight only; often misses rows from the same day with times other than 00:00.
WHERE created_at = DATE '2026-11-14'
~~~

differs from:

~~~sql
-- Entire day 2026-11-14, without guessing 23:59:59.
WHERE created_at >= DATE '2026-11-14'
AND   created_at <  DATE '2026-11-15'
~~~

For TIMESTAMP, the same range principle applies:

~~~sql
WHERE event_time >= TIMESTAMP '2026-11-14 00:00:00'
AND   event_time <  TIMESTAMP '2026-11-15 00:00:00'
~~~

Never construct an "end of day" using `23:59:59.999999`, because column precision may differ and timestamps can hold finer fractional digits. A **half-open interval (start inclusive, next-day start exclusive)** is cleaner and safer.

## 13. TO_CHAR and TO_DATE are not perfect two-way inverses

Some conversions lose information:

- `DATE` → `TO_CHAR(..., 'YYYY-MM-DD')` → `TO_DATE(...)`: **loses the time component** because the format only includes the date.
- `TIMESTAMP(6)` → format `...FF3` → `TO_TIMESTAMP(...)`: loses fractional digits beyond three places.
- `TIMESTAMP WITH TIME ZONE` → string with only `YYYY-MM-DD HH24:MI:SS` → `TO_TIMESTAMP`: loses timezone/offset.
- NUMBER → `TO_CHAR` with two decimal places → `TO_NUMBER`: can lose precision due to format rounding.

Example:

~~~sql
SELECT TO_CHAR(
         TO_DATE('2026-11-14', 'YYYY-MM-DD'),
         'YYYY-MM-DD HH24:MI:SS'
       ) AS output
FROM dual;
~~~

The time portion becomes `00:00:00`, because the input string only supplied a date. There is no way to recover the original time once omitted.

If round-trip fidelity is required, pick formats carrying complete information and target types capable of storing it. For timezone-aware timestamps, format and parse must preserve either offset or region per the contract.

## 14. ISO formats for integrations and APIs

For cross-system data exchange, prefer language-independent formats:

| Kind | Common Representation | Handling Function / Pattern |
| --- | --- | --- |
| Date | `2026-11-14` | `TO_DATE(text, 'YYYY-MM-DD')` or ANSI `DATE` literal |
| Local timestamp | `2026-11-14T09:30:15.123456` | `TO_TIMESTAMP(text, 'YYYY-MM-DD"T"HH24:MI:SS.FF6')` |
| Timestamp with offset | `2026-11-14T09:30:15.123456+07:00` | `TO_TIMESTAMP_TZ(..., 'YYYY-MM-DD"T"HH24:MI:SS.FF6TZH:TZM')` |
| Machine-readable number | `1234.50` | Bind NUMBER or `TO_NUMBER(..., explicit NLS)` |

Specify ISO format details precisely: whether timezone is included, number of fractional second digits, whether offsets include colons, and whether `Z` denotes UTC. If a source sends `Z`, the format model and parsing logic must handle it accordingly; do not assume `Z` behaves identically to `+00:00` in every format mask.

### 14.1. JDBC: bind by data type instead of string concatenation

In Java/JDBC, prefer binding strongly typed values:

~~~java
PreparedStatement ps = connection.prepareStatement(
    "SELECT order_id, created_at FROM orders WHERE created_at >= ?"
);
ps.setTimestamp(1, timestampValue);
~~~

If the column is DATE, align driver/JDBC mappings and `setDate`/`setTimestamp` usage with the time precision your application intends to keep. For `TIMESTAMP WITH TIME ZONE`, consult the corresponding Oracle JDBC / `java.time` APIs and driver version; avoid forcing values through `String` unnecessarily.

Bind variables help:

- Eliminate NLS dependencies when passing properly typed values.
- Prevent format errors and mitigate SQL injection risks from concatenation.
- Support statement reuse and cursor sharing.
- Keep semantics clear across NUMBER, DATE, TIMESTAMP, and VARCHAR2.

If input arrives as text, parse and validate it in a layer with a clear format contract, or convert explicitly in SQL; never concatenate raw input directly into SQL statements.

## 15. Common ORA conversion errors

| Error | Common Cause | How to Investigate |
| --- | --- | --- |
| `ORA-01722: invalid number` | String cannot be parsed as NUMBER under format/NLS | Check raw value, `NLS_NUMERIC_CHARACTERS`, format model, unexpected characters |
| `ORA-01481: invalid number format model` | Invalid number format model | Check `9`, `0`, `D`, `G`, modifiers, and element placement |
| `ORA-01830: date format picture ends before converting entire input string` | Format ends before the entire input string is consumed | Add time/fractional elements or fix input |
| `ORA-01843: not a valid month` | Month name/number mismatches format or NLS language | Check `MON`/`MONTH`, `MM`, `NLS_DATE_LANGUAGE` |
| `ORA-01847: day of month must be between 1 and last day of month` | Day does not exist in that month | Check invalid dates like 31/02 |
| `ORA-01858: a non-numeric character was found where a numeric was expected` | Input character mismatches numeric format slot | Compare input against format elements |
| `ORA-01861: literal does not match format string` | String mismatches format, often due to separators or widths | Use explicit format, check `FX`, inspect input |
| `ORA-01862: the numeric value does not match the length of the format item` | Numeric component length violates exact format | Check `FX` and digit count |
| `ORA-01821: date format not recognized` | Unrecognized datetime format model | Check whether tokens/formats are supported for that type |

Specific error codes can depend on expression and release. When debugging:

1. Capture the actual **raw string**, preserving spaces and Unicode characters.
2. Record the session NLS parameters of the exact failing connection.
3. Document both the column data type and bind variable data type.
4. Test the conversion standalone with the exact input, format, and NLS settings.
5. Never "fix" bad data by stripping all non-numeric characters; doing so can turn `1.234,50` into an incorrect number.

### 15.1. Month names and Unicode characters

Accented month/day names or non-ASCII characters also depend on character set, NLS language, and source files. A string like `Tháng Mười Một` cannot automatically be parsed with English `MON` or `MONTH`. Integration systems are best served by sending **numeric components** or standardized month names in a declared language.

### 15.2. Inputs with whitespace

Do not assume `TRIM` is always harmless: spaces can be significant in fixed-width formats, currency symbols, or string tokens. If the source specifies padding, trim the exact side and character per the contract before parsing. When `FX` is enabled, whitespace must strictly match the format model.

## 16. Practice exercises: NUMBER and NLS

> These SELECT statements are read-only. No tables are needed to practice conversions. Run them in SQL*Plus, SQLcl, or SQL Developer.

### Exercise A — Formatting a number with two locales

~~~sql
SELECT TO_CHAR(
         1234567.89,
         'FM9G999G999D00',
         'NLS_NUMERIC_CHARACTERS = ''.,'''
       ) AS us_style,
       TO_CHAR(
         1234567.89,
         'FM9G999G999D00',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS comma_decimal
FROM dual;
~~~

Expected results:

| US-style | Decimal comma |
| --- | --- |
| `1,234,567.89` | `1.234.567,89` |

### Exercise B — Parsing the same number under the right convention

~~~sql
SELECT TO_NUMBER(
         '1.234.567,89',
         '9G999G999D99',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS parsed_amount
FROM dual;
~~~

The NUMBER result is `1234567.89`. Try switching the NLS parameter to `''.,''` while keeping the input string unchanged and observe the error or altered meaning; then explain why you cannot reliably infer locale solely from commas and periods.

### Exercise C — Padded numbers

~~~sql
SELECT '[' || TO_CHAR(7, '999') || ']' AS padded,
       '[' || TO_CHAR(7, 'FM999') || ']' AS fill_mode,
       '[' || TO_CHAR(7, 'FM000') || ']' AS zero_fill
FROM dual;
~~~

Explain the difference between format-generated spaces, mandatory leading zeros, and the underlying NUMBER value.

## 17. Practice exercises: DATE and TIMESTAMP

### Exercise D — NLS-independent DATE parsing

~~~sql
SELECT TO_DATE('2026-11-14', 'YYYY-MM-DD') AS d
FROM dual;
~~~

Next:

~~~sql
SELECT TO_CHAR(
         TO_DATE('2026-11-14 17:30:45',
                 'YYYY-MM-DD HH24:MI:SS'),
         'YYYY-MM-DD HH24:MI:SS'
       ) AS formatted_d
FROM dual;
~~~

The output retains the time component `17:30:45`, because Oracle DATE stores down to seconds.

### Exercise E — Parsing TIMESTAMP with fractional seconds

~~~sql
SELECT TO_CHAR(
         TO_TIMESTAMP(
           '2026-11-14 17:30:45.123456',
           'YYYY-MM-DD HH24:MI:SS.FF6'
         ),
         'YYYY-MM-DD HH24:MI:SS.FF6'
       ) AS timestamp_text
FROM dual;
~~~

Try replacing `FF6` with `FF3`, and observe how formatting displays only three fractional digits.

### Exercise F — Timestamps with timezone

~~~sql
SELECT TO_CHAR(
         TO_TIMESTAMP_TZ(
           '2026-11-14 17:30:45.123456 +07:00',
           'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM'
         ),
         'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM'
       ) AS timestamp_with_tz
FROM dual;
~~~

Explain why replacing this with `TO_TIMESTAMP` fails to preserve the timezone offset as a property of the value.

### Exercise G — NLS language for month names

~~~sql
SELECT TO_CHAR(
         DATE '2026-11-14',
         'DD-MON-YYYY',
         'NLS_DATE_LANGUAGE = American'
       ) AS month_english
FROM dual;
~~~

Try changing the language to another Oracle-supported value in your environment and compare outputs; never infer data types from display output.

### Exercise H — Full-day date range

~~~sql
SELECT *
FROM   orders
WHERE  created_at >= DATE '2026-11-14'
AND    created_at <  DATE '2026-11-15';
~~~

This example targets a real `ORDERS` table; adjust table/column names if needed. Explain why `created_at = DATE '2026-11-14'` would miss rows created at 09:30 on that same day.

## 18. Data import processing workflow

Suppose a CSV file contains:

~~~text
order_id,amount,order_date
1001,"1.234,50","14-11-2026"
1002,"250,00","15-11-2026"
1003,"invalid","31-02-2026"
~~~

Never load raw text directly into NUMBER/DATE columns via implicit conversion. A safe workflow:

1. Load raw values into **VARCHAR2 staging columns**.
2. Specify the source format: decimal comma / group period, date `DD-MM-YYYY`.
3. Use `VALIDATE_CONVERSION` if your version supports it to classify parseable vs. unparseable rows.
4. Log errors by row/source file and retain raw values for remediation.
5. Convert valid rows with `TO_NUMBER`/`TO_DATE` using explicit formats and NLS parameters.
6. Insert data into target tables with proper data types and constraints.
7. Report counts of loaded rows, rejected rows, and rejection reasons.

Staging check example:

~~~sql
SELECT order_id,
       raw_amount,
       VALIDATE_CONVERSION(
         raw_amount AS NUMBER,
         '9G999G999D99',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS amount_ok,
       raw_order_date,
       VALIDATE_CONVERSION(
         raw_order_date AS DATE,
         'DD-MM-YYYY'
       ) AS date_ok
FROM   order_import_stage;
~~~

Once validated, perform the conversion:

~~~sql
SELECT order_id,
       TO_NUMBER(
         raw_amount,
         '9G999G999D99',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS amount,
       TO_DATE(raw_order_date, 'DD-MM-YYYY') AS order_date
FROM   order_import_stage
WHERE  VALIDATE_CONVERSION(
         raw_amount AS NUMBER,
         '9G999G999D99',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       ) = 1
AND    VALIDATE_CONVERSION(
         raw_order_date AS DATE,
         'DD-MM-YYYY'
       ) = 1;
~~~

This illustrates reading and converting data, not a complete insert script. In production implementations, handle `NULL`s, duplicate keys, business rule errors, transaction batching, logging, and changes occurring between validation and insertion. For large files, Data Pump, SQL*Loader, or external tables provide better mechanisms; staging gives you control over data before it enters business schemas.

## 19. Design mistakes to avoid

1. **Storing dates as VARCHAR2** even when a fixed format is always used. This breaks date comparisons/sorting and loses date arithmetic.
2. **Storing monetary amounts as strings** to preserve grouping separators. Store NUMBER and format at display time.
3. **Calling `TO_DATE(date_column, ...)`**. The input is already a DATE; this triggers implicit DATE → text → DATE conversion, potentially dropping time components or altering values per NLS.
4. **Omitting format models** when parsing date/time strings from APIs or files.
5. **Using YY/RR for new dates** when sources can supply full four-digit years.
6. **Using TO_DATE to parse fractional seconds** or timezone offsets.
7. **Using TO_TIMESTAMP on timezone-aware input** and silently dropping the offset/region.
8. **Wrapping columns in TO_CHAR inside WHERE** without evaluating indexes or function-based indexes.
9. **Relying on implicit session NLS** in connection pools or multi-client environments.
10. **Replacing unparseable values with 0 or 01-01-1900** without business authorization and auditing.
11. **Formatting monetary amounts without currency codes** in multi-currency systems.
12. **Using BETWEEN with end-of-day 23:59:59** on TIMESTAMP columns with fractional seconds; prefer half-open ranges.

## 20. Official Oracle documentation

1. [Oracle Database 19c SQL Language Reference — TO_CHAR (number)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_CHAR-number.html): syntax, number format models, NLS, and VARCHAR2 return behavior.
2. [Oracle Database 19c SQL Language Reference — TO_CHAR (datetime)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_CHAR-datetime.html): datetime format models, timestamp/time zone formatting, and NLS date language.
3. [Oracle Database 19c SQL Language Reference — TO_NUMBER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_NUMBER.html): character-to-NUMBER conversion, format models, and NLS.
4. [Oracle Database 19c SQL Language Reference — TO_DATE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_DATE.html): string-to-DATE conversion, formats, NLS, and warning against passing DATE into TO_DATE.
5. [Oracle Database 19c SQL Language Reference — TO_TIMESTAMP](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_TIMESTAMP.html): string-to-TIMESTAMP conversion, fractional seconds, and NLS.
6. [Oracle Database 19c SQL Language Reference — TO_TIMESTAMP_TZ](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/TO_TIMESTAMP_TZ.html): parsing timestamps with timezones.
7. [Oracle Database 19c SQL Language Reference — Format Models](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Format-Models.html): number/datetime format elements, `FX`, `FM`, `RR`, `FF`, `TZR`, `TZH`, `TZM`.
8. [Oracle Database 19c SQL Language Reference — Data Type Comparison Rules](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Type-Comparison-Rules.html): implicit conversion and data type comparison rules.
9. [Oracle Database 19c SQL Language Reference — VALIDATE_CONVERSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/VALIDATE_CONVERSION.html): convertibility validation for staging classification in supported releases.
10. [Oracle Database 19c Globalization Support Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/nlspg/): session NLS, territory, language, numeric/date formats, and multilingual integration.
11. [Oracle Database 19c JDBC Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/): binding DATE/TIMESTAMP values and type mapping between Java/JDBC and Oracle.

**Key rule to remember:** Use `TO_CHAR` for **presentation**, `TO_NUMBER` to **parse numbers**, `TO_DATE` to **parse DATEs**, and `TO_TIMESTAMP` to **parse timestamps with fractional seconds**; if timezone data is present, choose `TO_TIMESTAMP_TZ`. Always specify format and NLS explicitly for text inputs, prefer strongly typed bind variables, and keep columns unwrapped in filter predicates to avoid NLS bugs and performance issues.
