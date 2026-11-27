# ORA-01722, ORA-01843, ORA-01861, and Data/NLS-Dependent Conversion Errors

Oracle conversion errors typically occur when a character value is interpreted as `NUMBER`, `DATE`, or `TIMESTAMP`, yet the actual data does not match the format Oracle expects. Errors can come from SQL calling `TO_NUMBER`/`TO_DATE` explicitly, or from implicit conversion when comparing two different data types, assigning values, calling procedures, or binding parameters from a Java application.

Three errors to recognize:

- **ORA-01722: invalid number** — Oracle cannot convert a string to `NUMBER` under the active rules or format model.
- **ORA-01843: not a valid month** — the month component of a date value is invalid or cannot be interpreted under the active month language/format.
- **ORA-01861: literal does not match format string** — the input string does not match the format model required by the conversion.

A frequent cause is reliance on NLS session settings such as `NLS_NUMERIC_CHARACTERS`, `NLS_DATE_FORMAT`, `NLS_DATE_LANGUAGE`, and `NLS_TERRITORY`. The same SQL statement can succeed in one session and fail in another because decimal points, group separators, day/month/year order, or month-name languages differ.

The sustainable fix is to inspect the data types on both sides, locate sources of implicit conversion, inspect offending data, use properly typed bind variables, and specify explicit formats/NLS parameters whenever text must be parsed. Do not fix these by changing database-wide NLS settings or stripping characters from data without confirming business meaning.

## 1. How Oracle Converts Data

Oracle supports explicit conversion and implicit conversion.

### 1.1. Explicit Conversion

SQL invokes a conversion function directly:

~~~sql
SELECT TO_NUMBER('1250.75') FROM dual;

SELECT TO_DATE(
         '2026-11-14',
         'YYYY-MM-DD'
       )
FROM dual;
~~~

The SQL author explicitly specifies the conversion and can supply a format model/NLS parameter. This is the preferred approach when input data is text that must be parsed into an Oracle data type.

### 1.2. Implicit Conversion

Oracle automatically converts one operand so both sides can be compared or evaluated.

Example:

~~~sql
SELECT *
FROM app.orders
WHERE order_id = '10025';
~~~

If `ORDER_ID` is `NUMBER` while the literal is a character string, Oracle converts `'10025'` to `NUMBER`. With valid numeric strings, the statement runs. If a comparison uses a `VARCHAR2` column containing non-numeric values, the same conversion raises ORA-01722.

Another example:

~~~sql
SELECT *
FROM app.orders
WHERE created_at >= '14/11/2026';
~~~

If `CREATED_AT` is `DATE`, Oracle must interpret the string as a `DATE` via implicit conversion, usually governed by `NLS_DATE_FORMAT`. Another session with a different format can hit ORA-01861 or misinterpret the date.

### 1.3. Why Implicit Conversion Is Dangerous

- SQL behavior depends on session configuration.
- Dirty data only fails when an execution path touches that value.
- Execution plan changes can make errors appear or disappear.
- Oracle may convert the indexed column in the predicate, preventing index usage.
- A JDBC application may bind `VARCHAR2` instead of `NUMBER`/`DATE`.
- Reused connection pool sessions can carry over NLS state from a prior request if the application alters session settings without resetting them.

### 1.4. Data Types Must Be Verified from the Schema

Check column definitions:

~~~sql
SELECT owner,
       table_name,
       column_name,
       data_type,
       data_length,
       data_precision,
       data_scale,
       nullable
FROM all_tab_columns
WHERE owner = 'APP'
  AND table_name = 'ORDERS'
ORDER BY column_id;
~~~

If a monetary column is stored as `VARCHAR2`, determine why the schema uses text—raw imported data, local formatting, identifiers, or legacy design—before adding `TO_NUMBER` everywhere. Not every string of digits represents a numeric quantity.

## 2. ORA-01722 — invalid number

ORA-01722 occurs when Oracle must interpret a character value as `NUMBER`, but the value is invalid under the conversion rules or format model.

### 2.1. Simple Example

~~~sql
SELECT TO_NUMBER('ABC') FROM dual;
~~~

Oracle cannot convert `ABC` into a `NUMBER`.

Common offending data:
- Letters inside a column expected to be numeric.
- Empty strings or strings containing only separators.
- Currency symbols incompatible with the format model.
- Decimal/group separators mismatched with NLS.
- Plus or minus signs in positions disallowed by the format.
- Whitespace or Unicode characters handled unexpectedly.
- Numeric strings with suffixes, units, or descriptive notes.
- Truncated or misaligned fields from ETL.

### 2.2. Implicit Conversion in Predicates

Suppose the schema has:

~~~sql
CREATE TABLE app.external_orders (
    external_order_id VARCHAR2(40),
    amount_text       VARCHAR2(40)
);
~~~

Data:

~~~sql
INSERT INTO app.external_orders VALUES ('1001', '250.50');
INSERT INTO app.external_orders VALUES ('1002', 'UNKNOWN');
~~~

Query:

~~~sql
SELECT *
FROM app.external_orders
WHERE amount_text > 100;
~~~

Because one side is `VARCHAR2` and the other is `NUMBER`, Oracle converts `amount_text` to `NUMBER` for comparison. Upon hitting `UNKNOWN`, the query raises ORA-01722.

Do not rely on predicate order in `WHERE` to pre-filter dirty rows:

~~~sql
SELECT *
FROM app.external_orders
WHERE REGEXP_LIKE(amount_text, '^[0-9]+([.][0-9]+)?$')
  AND TO_NUMBER(amount_text) > 100;
~~~

The SQL optimizer may reorder predicate evaluation; never assume `REGEXP_LIKE` runs before `TO_NUMBER`. Use a guarded `CASE` expression or `DEFAULT ON CONVERSION ERROR` on supported versions, and better yet, normalize data at ingestion time.

### 2.3. Comparing a NUMBER Column with a VARCHAR2 Column

Example:

~~~sql
SELECT *
FROM app.orders o
JOIN app.imported_orders i
  ON o.order_id = i.order_id_text;
~~~

If `ORDER_ID` is `NUMBER` and `ORDER_ID_TEXT` is `VARCHAR2`, the join requires conversion. A single dirty value in the import table causes the entire join to fail.

Resolution:
- Inspect data in the import table.
- Parse into a staging numeric column using explicit rules.
- Route invalid rows to a quarantine/error table.
- Join `NUMBER` to `NUMBER` after validating data.
- Never wrap an indexed `NUMBER` column in `TO_CHAR(number_column)` merely to mask the error when the bind/source can be properly typed.

### 2.4. Decimal Separators and Group Separators

The strings `1,234.56` and `1.234,56` represent the same numeric value under two different locale conventions.

Oracle uses `NLS_NUMERIC_CHARACTERS`:
- First character: decimal separator.
- Second character: group separator.

Check the session:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_NUMERIC_CHARACTERS',
    'NLS_TERRITORY'
);
~~~

Example parsing a string with a dot decimal and comma grouping:

~~~sql
SELECT TO_NUMBER(
         '1,234.56',
         '9G999D99',
         'NLS_NUMERIC_CHARACTERS = ''.,'''
       ) AS amount
FROM dual;
~~~

Example parsing a string with a comma decimal and dot grouping:

~~~sql
SELECT TO_NUMBER(
         '1.234,56',
         '9G999D99',
         'NLS_NUMERIC_CHARACTERS = '',.'''
       ) AS amount
FROM dual;
~~~

In the format model:
- `D` represents the NLS decimal character.
- `G` represents the NLS group separator.

If the format model lacks `G`/`D`, or the NLS parameter differs from source data, parsing fails or yields unintended values. Never blindly replace commas with dots; `'1,234'` could mean one thousand two hundred thirty-four or one point two three four depending on the source.

### 2.5. Currency Symbols and Format Models

If data contains currency symbols, supply an appropriate format model and `NLS_CURRENCY`/`NLS_ISO_CURRENCY`. Example:

~~~sql
SELECT TO_NUMBER(
         '$1,250.00',
         'L9G999D99',
         'NLS_NUMERIC_CHARACTERS = ''.,'' NLS_CURRENCY = ''$'''
       )
FROM dual;
~~~

The format model must match length, symbol placement, and source conventions. If data involves multiple currencies, it is far better to store `amount` as `NUMBER` and the currency code in a separate column.

## 3. ORA-01843 — not a valid month

ORA-01843 typically occurs when Oracle cannot recognize the month portion of a date string under the active format model and `NLS_DATE_LANGUAGE`.

### 3.1. Language-Dependent Month Names

Example:

~~~sql
SELECT TO_DATE(
         '14-NOV-2026',
         'DD-MON-YYYY'
       )
FROM dual;
~~~

If the session uses a different month language and does not recognize `NOV`, parsing fails. Specify the language explicitly:

~~~sql
SELECT TO_DATE(
         '14-NOV-2026',
         'DD-MON-YYYY',
         'NLS_DATE_LANGUAGE = ENGLISH'
       )
FROM dual;
~~~

If a source sends Vietnamese or other localized month names, the format language must match the source and be verified against Oracle release support.

### 3.2. Invalid Month Number

Example with month 13:

~~~sql
SELECT TO_DATE(
         '2026-13-14',
         'YYYY-MM-DD'
       )
FROM dual;
~~~

The month is outside 01–12. Depending on the case, Oracle raises ORA-01843 or a related date error.

### 3.3. NLS_DATE_LANGUAGE

Check the session language:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_DATE_LANGUAGE',
    'NLS_DATE_FORMAT',
    'NLS_TERRITORY'
);
~~~

Parse month names with an explicit NLS setting:

~~~sql
SELECT TO_DATE(
         '14-NOV-2026',
         'DD-MON-YYYY',
         'NLS_DATE_LANGUAGE=ENGLISH'
       )
FROM dual;
~~~

Never rely on a developer workstation's default month language and promote that string format to production without specifying NLS.

### 3.4. YY and RR

`YY` and `RR` handle two-digit years differently. Use four-digit years (`YYYY`) whenever data formats allow. Avoid relying on `RR`'s century window for long-lived data or cross-system integrations.

## 4. ORA-01861 — literal does not match format string

ORA-01861 occurs when a literal fails to match the format model. Causes include day/month/year order, separators, time components, fractional seconds, or timezones.

### 4.1. Swapped Day and Month Order

~~~sql
SELECT TO_DATE(
         '14/11/2026',
         'YYYY-MM-DD'
       )
FROM dual;
~~~

The input uses `DD/MM/YYYY`, whereas the format model expects `YYYY-MM-DD`.

Correct form:

~~~sql
SELECT TO_DATE(
         '14/11/2026',
         'DD/MM/YYYY'
       )
FROM dual;
~~~

### 4.2. Mismatched Separators

`2026-11-14` and `2026/11/14` are different strings. When a format model specifies hyphens, do not assume Oracle automatically accepts slashes.

~~~sql
SELECT TO_DATE(
         '2026/11/14',
         'YYYY-MM-DD'
       )
FROM dual;
~~~

### 4.3. Time Component Present but Omitted from Format

~~~sql
SELECT TO_DATE(
         '2026-11-14 15:30:00',
         'YYYY-MM-DD'
       )
FROM dual;
~~~

The string includes a time component. The format model must include the time elements if the goal is to parse both date and time:

~~~sql
SELECT TO_DATE(
         '2026-11-14 15:30:00',
         'YYYY-MM-DD HH24:MI:SS'
       )
FROM dual;
~~~

### 4.4. Format Models Are Parsing Instructions, Not Labels

The format model dictates how input is parsed, not merely a display hint. Verify:
- `YYYY` vs. `RR`/`YY`.
- `MM` vs. `MON`/`MONTH`.
- `DD`.
- `HH24`, `MI`, `SS`.
- `FF` for fractional seconds.
- `TZH`/`TZM` or `TZR`/`TZD` for timezones.
- Literal separators.
- `NLS_DATE_LANGUAGE` when using month names.

## 5. Distinguishing Common Date Conversion Errors

Date/time errors look similar yet point to distinct causes.

| Error Code | Common Meaning | Investigation Focus |
| --- | --- | --- |
| ORA-01843 | Invalid or unrecognized month | `MM`/`MONTH`/`MON`, `NLS_DATE_LANGUAGE`, month data |
| ORA-01861 | Literal does not match format model | Field order, separators, time components |
| ORA-01858 | Non-numeric character found where numeric was expected | Day/month/year/time fields and format model |
| ORA-01847 | Day of month invalid for the month | Day value and month/year |
| ORA-01830 | Date format picture ends before converting entire input string | Trailing time or text in string |
| ORA-01821 | Date format not recognized | Format model tokens |
| ORA-01841 | Year invalid or out of range | Year value and calendar |

Do not treat all date errors by changing `NLS_DATE_FORMAT`. Compare the actual input string, format model, NLS language, and target data type.

## 6. How NLS Settings Affect Conversions

NLS (National Language Support) governs language and regional conventions inside a database session.

### 6.1. Common Parameters

| Parameter | Effect |
| --- | --- |
| `NLS_NUMERIC_CHARACTERS` | Decimal point and group separator |
| `NLS_DATE_FORMAT` | Default format when converting/displaying `DATE` in many contexts |
| `NLS_DATE_LANGUAGE` | Language of month/day names and certain date text |
| `NLS_TERRITORY` | Regional conventions, affecting default date/numeric formats |
| `NLS_TIMESTAMP_FORMAT` | Default format for `TIMESTAMP` |
| `NLS_TIMESTAMP_TZ_FORMAT` | Default format for `TIMESTAMP WITH TIME ZONE` |
| `NLS_CALENDAR` | Calendar system used in date interpretation |
| `NLS_CURRENCY` | Local currency symbol |
| `NLS_ISO_CURRENCY` | ISO currency symbol by territory |

### 6.2. Inspecting NLS Session Parameters

~~~sql
SELECT parameter,
       value
FROM nls_session_parameters
ORDER BY parameter;
~~~

Filter to relevant parameters:

~~~sql
SELECT parameter,
       value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_NUMERIC_CHARACTERS',
    'NLS_DATE_FORMAT',
    'NLS_DATE_LANGUAGE',
    'NLS_TERRITORY',
    'NLS_TIMESTAMP_FORMAT',
    'NLS_TIMESTAMP_TZ_FORMAT',
    'NLS_CALENDAR'
)
ORDER BY parameter;
~~~

### 6.3. Comparing Session and Database Scope

~~~sql
SELECT 'SESSION' AS scope, parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_NUMERIC_CHARACTERS',
    'NLS_DATE_FORMAT',
    'NLS_DATE_LANGUAGE'
)
UNION ALL
SELECT 'DATABASE', parameter, value
FROM nls_database_parameters
WHERE parameter IN (
    'NLS_NUMERIC_CHARACTERS',
    'NLS_DATE_FORMAT',
    'NLS_DATE_LANGUAGE'
)
ORDER BY parameter, scope;
~~~

`NLS_DATABASE_PARAMETERS` shows database-level configuration; session parameters are what actually govern SQL execution. Clients, drivers, and logon environments can override session defaults.

### 6.4. NLS_LANG and JDBC Thin

`NLS_LANG` is an environment variable common in Oracle Client/OCI describing client language, territory, and character set. It is not a universal mechanism for controlling every session's NLS.

JDBC Thin runs in Java and handles Unicode through its own mechanisms; do not assume changing `NLS_LANG` on the host alters parsing in a Thin session. Always inspect `NLS_SESSION_PARAMETERS` on the actual connection.

### 6.5. Using ALTER SESSION Intentionally

You can set session NLS parameters:

~~~sql
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';
ALTER SESSION SET NLS_DATE_LANGUAGE = 'ENGLISH';
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD';
~~~

This configures the session; it does not fix dirty data or replace explicit format models. With connection pools, `ALTER SESSION` persists after the connection returns to the pool and gets reused by subsequent requests.

If an application modifies session NLS settings:
- Establish a baseline when creating/borrowing connections.
- Reset session state upon returning connections.
- Never rely on request ordering.
- Audit all datasources and pools.
- Better yet, use explicit conversions and properly typed binds to eliminate session dependence.

## 7. Format Models and Safe Conversions

### 7.1. Converting Text to NUMBER

~~~sql
SELECT TO_NUMBER(
         :amount_text,
         'FM999G999G999D9999',
         'NLS_NUMERIC_CHARACTERS = ''.,'''
       )
FROM dual;
~~~

Bind `:amount_text` as a string matching the defined contract. The format model must accommodate business range, precision, scale, and signs.

### 7.2. Converting Text to DATE

~~~sql
SELECT TO_DATE(
         :date_text,
         'YYYY-MM-DD'
       )
FROM dual;
~~~

When using month names:

~~~sql
SELECT TO_DATE(
         :date_text,
         'DD-MON-YYYY',
         'NLS_DATE_LANGUAGE=ENGLISH'
       )
FROM dual;
~~~

### 7.3. Converting Text to TIMESTAMP

~~~sql
SELECT TO_TIMESTAMP(
         :timestamp_text,
         'YYYY-MM-DD HH24:MI:SS.FF'
       )
FROM dual;
~~~

With timezone:

~~~sql
SELECT TO_TIMESTAMP_TZ(
         :timestamp_text,
         'YYYY-MM-DD HH24:MI:SS TZH:TZM'
       )
FROM dual;
~~~

Do not strip timezones from data when business logic needs exact instants in time. `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE`, and `TIMESTAMP WITH LOCAL TIME ZONE` have distinct semantics.

### 7.4. Using ANSI Date/Timestamp Literals

For fixed literals in SQL, ANSI literals avoid NLS dependencies:

~~~sql
SELECT *
FROM app.orders
WHERE created_at >= DATE '2026-11-01'
  AND created_at <  DATE '2026-12-01';
~~~

Timestamp literal:

~~~sql
SELECT TIMESTAMP '2026-11-14 15:30:00'
FROM dual;
~~~

Date literals use `YYYY-MM-DD`. For dynamic values from an application, bind `DATE`/`TIMESTAMP` variables instead of concatenating string literals.

### 7.5. Never Call TO_DATE on a DATE Column

Incorrect or unnecessary:

~~~sql
SELECT TO_DATE(created_at, 'YYYY-MM-DD')
FROM app.orders;
~~~

`CREATED_AT` is already a `DATE`. Oracle implicitly converts the `DATE` to text using `NLS_DATE_FORMAT` and then parses it back to `DATE`, introducing NLS dependence and losing time components.

Correct:

~~~sql
SELECT created_at
FROM app.orders;
~~~

If formatting for display:

~~~sql
SELECT TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS')
FROM app.orders;
~~~

Use `TO_CHAR` for presentation; keep `DATE`/`TIMESTAMP` types in filtering and join logic.

## 8. Inspecting Dirty Data Before Conversion

Before editing SQL, pinpoint exactly which values are invalid and where they originate.

### 8.1. Finding Non-Numeric Values

On Oracle releases supporting `REGEXP_LIKE`:

~~~sql
SELECT rowid,
       amount_text
FROM app.external_orders
WHERE amount_text IS NOT NULL
  AND NOT REGEXP_LIKE(
        TRIM(amount_text),
        '^[+-]?[0-9]+([.][0-9]+)?$'
      );
~~~

This pattern accepts only dot decimals and rejects group separators, exponents, currency symbols, and other locales. Adjust it to match your source contract. Do not treat this regex as a universal definition for all numeric strings.

### 8.2. VALIDATE_CONVERSION

Starting in Oracle Database 12.2 on supported releases, `VALIDATE_CONVERSION` can be used:

~~~sql
SELECT rowid,
       amount_text
FROM app.external_orders
WHERE amount_text IS NOT NULL
  AND VALIDATE_CONVERSION(
        amount_text AS NUMBER,
        'FM999G999G999D9999',
        'NLS_NUMERIC_CHARACTERS = ''.,'''
      ) = 0;
~~~

`VALIDATE_CONVERSION` returns `1` if the expression can be converted under the specified rules, and `0` otherwise. `NULL` is considered convertible and returns `1`; check `IS NOT NULL` separately when needed.

### 8.3. VALIDATE_CONVERSION for DATE

~~~sql
SELECT rowid,
       order_date_text
FROM app.external_orders
WHERE order_date_text IS NOT NULL
  AND VALIDATE_CONVERSION(
        order_date_text AS DATE,
        'YYYY-MM-DD'
      ) = 0;
~~~

With month names, include the matching `NLS_DATE_LANGUAGE`.

### 8.4. DEFAULT ON CONVERSION ERROR

Starting in Oracle Database 12.2 on supported releases, `TO_NUMBER`/`TO_DATE`/`TO_TIMESTAMP` support `DEFAULT ON CONVERSION ERROR`:

~~~sql
SELECT TO_NUMBER(
         amount_text DEFAULT NULL ON CONVERSION ERROR,
         'FM999G999G999D9999',
         'NLS_NUMERIC_CHARACTERS = ''.,'''
       ) AS amount
FROM app.external_orders;
~~~

And:

~~~sql
SELECT TO_DATE(
         order_date_text DEFAULT NULL ON CONVERSION ERROR,
         'YYYY-MM-DD'
       ) AS order_date
FROM app.external_orders;
~~~

This prevents a query from aborting on a single unparseable value, though returning `NULL` blurs the distinction between genuinely `NULL` source data and malformed data. In ETL, log errors to a quarantine table instead of silently converting malformed values to `NULL`.

### 8.5. Using CASE to Guard Conversions

~~~sql
SELECT CASE
         WHEN amount_text IS NOT NULL
          AND VALIDATE_CONVERSION(
                amount_text AS NUMBER,
                'FM999G999G999D9999',
                'NLS_NUMERIC_CHARACTERS = ''.,'''
              ) = 1
         THEN TO_NUMBER(
                amount_text,
                'FM999G999G999D9999',
                'NLS_NUMERIC_CHARACTERS = ''.,'''
              )
         ELSE NULL
       END AS amount
FROM app.external_orders;
~~~

`CASE` expressions follow short-circuit evaluation rules. Use the exact same format/NLS parameters in both validation and conversion. On versions supporting `DEFAULT ON CONVERSION ERROR`, that syntax is usually more concise.

## 9. Diagnosing Abnormal Character Data

Values that look identical on screen can contain different bytes or characters.

### 9.1. Whitespace and Control Characters

Check:

~~~sql
SELECT rowid,
       '[' || amount_text || ']' AS visible_value,
       LENGTH(amount_text) AS char_length,
       LENGTHB(amount_text) AS byte_length,
       DUMP(amount_text, 1016) AS hex_dump
FROM app.external_orders
WHERE amount_text IS NOT NULL;
~~~

`DUMP` reveals internal representation and byte/character codes in the selected format. `LENGTH` and `LENGTHB` help spot strings where byte length differs from character count.

### 9.2. Unicode Characters

An ASCII hyphen-minus differs from a Unicode minus sign. A regular space differs from a non-breaking space. Inspect the Unicode representation:

~~~sql
SELECT amount_text,
       ASCIISTR(amount_text)
FROM app.external_orders
WHERE amount_text IS NOT NULL;
~~~

`ASCIISTR` renders non-ASCII characters as Unicode escapes, which is invaluable for data imported from Excel, CSV, web forms, or external systems.

### 9.3. Do Not Blindly TRIM/REPLACE Everything

`TRIM` removes leading/trailing spaces according to its rules, but does not strip all Unicode whitespace characters. Using `REPLACE` on commas/dots can corrupt values across different locales.

Before normalizing:
1. Identify the encoding and source system.
2. Inspect raw bytes/Unicode.
3. Confirm separators per the data contract.
4. Define rules for signs, currency symbols, and whitespace.
5. Retain raw input for auditing.
6. Store the normalized value alongside parse status.
7. Route invalid rows to quarantine.

## 10. NLS and Date/Time in Queries

### 10.1. Never Compare a DATE with a String

Avoid:

~~~sql
SELECT *
FROM app.orders
WHERE created_at = '14/11/2026';
~~~

Prefer:

~~~sql
SELECT *
FROM app.orders
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15';
~~~

Or bind `java.sql.Date`/`Timestamp` as appropriate.

### 10.2. Filtering Full Days When Times Are Stored

Oracle `DATE` stores both date and time down to the second. An equality check against a `DATE` literal matches only midnight.

To capture an entire day, use a half-open range:

~~~sql
WHERE created_at >= DATE '2026-11-14'
  AND created_at <  DATE '2026-11-15'
~~~

This also avoids wrapping the column in `TRUNC()`, preserving index range scans. If `TRUNC(created_at)` is used, consider function-based indexes and timezone semantics.

### 10.3. NLS_TIMESTAMP_FORMAT

`TIMESTAMP` has its own default format. Never use unformatted timestamp strings in `INSERT`/`UPDATE`:

~~~sql
INSERT INTO app.events(event_time)
VALUES ('14-NOV-2026 15:30:00');
~~~

Use `TO_TIMESTAMP` with an explicit format or bind a `TIMESTAMP`:

~~~sql
INSERT INTO app.events(event_time)
VALUES (
    TO_TIMESTAMP(
        :event_time_text,
        'DD-MON-YYYY HH24:MI:SS',
        'NLS_DATE_LANGUAGE=ENGLISH'
    )
);
~~~

### 10.4. Timezones and Sessions

`TIMESTAMP WITH TIME ZONE` preserves the timezone/offset per its data type semantics. `TIMESTAMP WITH LOCAL TIME ZONE` normalizes on storage and displays in the session time zone. When reconciling timestamps across systems:
- Record the source's timezone explicitly.
- Normalize to UTC if the contract specifies.
- Bind timezone-aware types appropriately.
- Never parse a local time and assume it is UTC.
- Check DST transitions if the source uses a local region.

## 11. Impact of Bind Variables and JDBC

An application can raise ORA-01722 or ORA-01861 even when the SQL runs in SQL Developer, because the driver binds parameters with different types or session NLS differs.

### 11.1. Binding NUMBER with setBigDecimal

Example:

~~~java
String sql =
    "select order_id from app.orders where total_amount > ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, new BigDecimal("1250.50"));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("order_id"));
        }
    }
}
~~~

When the column is `NUMBER`, bind `BigDecimal`/`long`/`int` matching the domain instead of sending a string and forcing Oracle to parse it via NLS.

### 11.2. Binding DATE/TIMESTAMP with Temporal Types

~~~java
String sql =
    "select order_id from app.orders where created_at >= ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setTimestamp(
        1,
        Timestamp.valueOf(LocalDateTime.of(2026, 11, 14, 0, 0))
    );

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            System.out.println(rs.getLong("order_id"));
        }
    }
}
~~~

If the application uses `LocalDate`, use `java.sql.Date.valueOf(localDate)` or JDBC 4.2 `setObject` where supported by the driver. Choose type mappings consistent with the Oracle column.

### 11.3. When to Bind Strings

Bind `String` only when the value is genuinely text or must be parsed under an explicit contract. When a source supplies date strings:
- Validate the format.
- Use `TO_DATE`/`TO_TIMESTAMP` with an explicit format model.
- Specify `NLS_DATE_LANGUAGE` if month names are used.
- Validate before writing to primary tables.

Never use `setString` for every parameter simply because inputs arrive over HTTP.

### 11.4. PreparedStatement Does Not Automatically Fix Bad Data

Bind variables separate SQL from values, prevent SQL injection, and stabilize cursor sharing. They do not automatically turn dirty strings into valid `NUMBER`/`DATE` values. Bind types must match column types or go through explicit conversions.

### 11.5. Checking Connection Pool Sessions

Query NLS settings directly on a connection borrowed from the pool:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
    'NLS_NUMERIC_CHARACTERS',
    'NLS_DATE_FORMAT',
    'NLS_DATE_LANGUAGE',
    'NLS_TERRITORY'
);
~~~

Run this across multiple connections and after multiple requests to catch altered session state. If the application uses `ALTER SESSION`, ensure state is reset or initialized to a baseline for every connection.

## 12. Data Ingestion, ETL, and Staging

CSV/Excel/API feeds typically deliver text. Never parse all values directly into business tables without validation.

### 12.1. Preserving Raw Input

A staging table can store raw amount/date text, source file and row number, source system, ingest timestamp, parse status, error code/message, and normalized `NUMBER`/`DATE` values once parsed.

Example:

~~~sql
CREATE TABLE app.order_stage (
    source_file       VARCHAR2(255),
    source_row        NUMBER,
    raw_amount        VARCHAR2(100),
    raw_order_date    VARCHAR2(100),
    amount_value      NUMBER,
    order_date        DATE,
    parse_status      VARCHAR2(20),
    parse_error       VARCHAR2(4000)
);
~~~

This table is a simplified example; production designs also need batch IDs, source keys, deduplication, and retention.

### 12.2. Validating Before Insert

~~~sql
SELECT source_file,
       source_row,
       raw_amount,
       CASE
         WHEN raw_amount IS NULL THEN 'MISSING'
         WHEN VALIDATE_CONVERSION(
                raw_amount AS NUMBER,
                'FM999G999G999D9999',
                'NLS_NUMERIC_CHARACTERS = ''.,'''
              ) = 1 THEN 'VALID'
         ELSE 'INVALID_NUMBER'
       END AS amount_status
FROM app.order_stage;
~~~

Similarly for dates:

~~~sql
SELECT source_file,
       source_row,
       raw_order_date,
       CASE
         WHEN raw_order_date IS NULL THEN 'MISSING'
         WHEN VALIDATE_CONVERSION(
                raw_order_date AS DATE,
                'YYYY-MM-DD'
              ) = 1 THEN 'VALID'
         ELSE 'INVALID_DATE'
       END AS date_status
FROM app.order_stage;
~~~

### 12.3. Quarantining Bad Records

Route malformed rows to an error table with source keys and specific reasons. Never silently skip them or convert everything to `0`/`NULL` if the value affects monetary amounts, effective dates, or business keys.

### 12.4. Normalizing by Source

Every feed needs a contract specifying:
- Encoding.
- Decimal/group separators.
- Date/time format.
- Timezone.
- Null representation.
- Currency.
- Sign convention.
- Trimming/whitespace policy.
- Allowed precision/scale.
- Error handling and retry behavior.

Never infer locale from the server host or session NLS.

## 13. Diagnosing Errors in Production

When ORA-01722/01843/01861 occurs, collect enough context to reproduce it.

### 13.1. Capture SQL and Bind Metadata

Log safely under policy:
- `SQL_ID` or statement identifier.
- Bind position/name.
- Bind data type.
- Masked values if sensitive.
- JDK/JDBC driver version.
- Database service/PDB.
- Session NLS parameters.
- Request/batch ID.
- Timestamp and timezone.

Never log passwords, tokens, full payment details, or sensitive personal data.

### 13.2. Find SQL_ID and Execution Plan

DBAs can inspect `V$SQL`/`V$SQL_BIND_CAPTURE` when authorized and capture data exists. Bind capture is not guaranteed to record every bind value or every execution. For critical SQL, save the SQL text, bind data types, and application traces.

Inspect the execution plan:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        sql_id => :sql_id,
        format => 'ALLSTATS LAST +PREDICATE'
    )
);
~~~

The plan can reveal implicit conversions such as `TO_NUMBER(column)` or `TO_CHAR(date_column)` in predicates. Predicate conversions can also disable index access and cause poor cardinality estimates.

### 13.3. Locate Where Conversion Happens

Search SQL for:
- Comparing `NUMBER` with `VARCHAR2`.
- Comparing `DATE`/`TIMESTAMP` with text.
- `NVL`/`COALESCE`/`CASE` mixing data types.
- `UNION`/`UNION ALL` with mismatched column data types.
- `JOIN` between keys of different data types.
- Function arguments receiving text when `NUMBER`/`DATE` is expected.
- Dynamic SQL concatenating strings.
- PL/SQL assignments between mismatched types.

### 13.4. NLS Snapshot at Failure Time

Record:

~~~sql
SELECT parameter,
       value
FROM nls_session_parameters
WHERE parameter LIKE 'NLS_%'
ORDER BY parameter;
~~~

A single application pool can hold sessions with differing state. Inspecting NLS in a SQL Developer session does not prove the failing connection had the same NLS settings.

### 13.5. Error Message Details

Some Oracle releases provide additional diagnostic details for ORA-01722, including the offending value or expression. Where supported, use those details to narrow down the source; do not rely on them as a substitute for inspecting data and SQL.

## 14. Step-by-Step Safe Remediation

An actionable workflow:

1. Record the verbatim ORA code, `SQL_ID`, bind data type, and timestamp.
2. Identify the statement and the failing conversion.
3. Check data types of columns, literals, and binds.
4. Capture `NLS_SESSION_PARAMETERS` from the failing connection.
5. Extract a minimal reproducible dataset while preserving raw values.
6. Find unparseable values using `VALIDATE_CONVERSION`/regex matching the contract.
7. Classify the bad data: separator, month language, whitespace, Unicode character, format, null, or corruption.
8. Fix SQL, bind types, source normalization, or clean data as appropriate.
9. Test against both valid and invalid data.
10. Verify execution plans/indexes and performance.
11. Deploy with monitoring, tracking quarantine counts and remaining errors.
12. Enforce data contracts/validation to prevent recurrence.

### 14.1. Never Change Database-Wide NLS as a First Reflex

Altering `NLS_DATABASE_PARAMETERS` or initialization parameters affects numerous applications and sessions, and will not fix values already formatted under conflicting conventions. First determine the source contract and fix it at the right boundary.

### 14.2. Do Not Apply TO_NUMBER to Every Text Column Without Validation

A `VARCHAR2` column may hold codes like `00123`, `A123`, `N/A`, or currency strings. Converting everything to `NUMBER` breaks semantics or strips leading zeros.

### 14.3. Do Not Replace Bad Data with 0

If `amount_text` fails to parse, substituting `0` produces wrong reports, wrong invoices, or hides upstream errors. Keep raw values and quarantine records.

### 14.4. Do Not Rely on a Single Execution Plan

The optimizer can change plans after stats refreshes, bind value changes, RUs, or data shifts. SQL must remain safe across all valid and dirty data per contract, never relying on accidental predicate evaluation order.

## 15. SQL Patterns to Use and Avoid

| Scenario | Avoid | Prefer |
| --- | --- | --- |
| Comparing `NUMBER` with text input | `number_col = :text` | Bind `NUMBER` or explicitly parse text |
| Comparing `DATE` with string | `date_col = '14/11/2026'` | `DATE`/`TIMESTAMP` bind or ANSI literal |
| Parsing localized numbers | `TO_NUMBER(text_col)` without NLS | `TO_NUMBER` with explicit format and NLS |
| Parsing month names | `TO_DATE` with default NLS | `TO_DATE` with `NLS_DATE_LANGUAGE` |
| Column is already `DATE` | `TO_DATE(date_col, ...)` | Use `date_col` directly |
| Untrusted imported data | Converting directly inside joins | Stage, validate, quarantine, then join |
| Whole-day date range | `TRUNC(date_col) = ...` everywhere | Half-open range `[start, next_day)` |
| Conversions that can fail | Relying on `WHERE` predicate order | `VALIDATE_CONVERSION`/`CASE` or `DEFAULT ON CONVERSION ERROR` |
| Dynamic values | Concatenating SQL strings | `PreparedStatement` with matching bind types |

## 16. Example Handling a Feed with Numeric and Date Errors

Suppose a feed sends these rows:

| source_row | raw_amount | raw_date |
| --- | --- | --- |
| 1 | `1,250.50` | `2026-11-14` |
| 2 | `1.250,50` | `14-NOV-2026` |
| 3 | `UNKNOWN` | `2026-13-14` |
| 4 | `500.00` | `2026/11/15` |

You cannot parse all rows with a single default format if the source lacks a unified contract.

### 16.1. Identify Source Locale

If a file mixes two numeric formats, determine whether the feed aggregates multiple sources. You cannot tell from the string alone whether `1,250` means `1250` or `1.250` without a locale/contract.

### 16.2. Separate by Feed/Format

If Source A uses decimal dot and group comma:

~~~sql
TO_NUMBER(
  raw_amount,
  'FM999G999G999D9999',
  'NLS_NUMERIC_CHARACTERS = ''.,'''
)
~~~

If Source B uses decimal comma and group dot:

~~~sql
TO_NUMBER(
  raw_amount,
  'FM999G999G999D9999',
  'NLS_NUMERIC_CHARACTERS = '',.'''
)
~~~

Source A ISO date:

~~~sql
TO_DATE(raw_date, 'YYYY-MM-DD')
~~~

Source B English month name:

~~~sql
TO_DATE(
  raw_date,
  'DD-MON-YYYY',
  'NLS_DATE_LANGUAGE=ENGLISH'
)
~~~

### 16.3. Quarantine Invalid Rows

Row 3 has amount `UNKNOWN` and month `13`, so it must not enter business tables. Row 4 uses a different date separator than the ISO contract; verify the source before adding a second format.

Never blindly try multiple formats and take the first match when two formats could interpret the same string as different dates. Format must be determined from metadata/source system.

## 17. Impact on Indexes and Performance

Implicit conversion does not just cause errors; it can severely slow down queries.

### 17.1. Conversion on an Indexed Column

Example:

~~~sql
SELECT *
FROM app.orders
WHERE TO_CHAR(order_id) = :order_id_text;
~~~

If an index exists on `ORDER_ID`, wrapping the column in `TO_CHAR` can prevent the regular index from being used as expected. A function-based index might work, but the real fix is binding a `NUMBER`.

### 17.2. Conversion Due to Data Type Mismatch

If a predicate generates `TO_NUMBER(varchar_column)`, Oracle may evaluate the conversion across many rows and fail on dirty values. Depending on the expression and optimizer, the plan may skip usable indexes.

### 17.3. Verify the Execution Plan After Fixing

Use `DBMS_XPLAN.DISPLAY_CURSOR` with predicate information. Check:
- Are there implicit conversions on indexed columns?
- Are predicates SARGable?
- Estimated vs. actual rows.
- Is a full table scan justified?
- Do bind data types match column types?
- Are any function-based indexes actually needed?

Never create an index to paper over a data error or data-type mismatch.

## 18. PL/SQL and Conversion Errors

PL/SQL can also raise these errors during variable assignments or function calls.

~~~sql
DECLARE
    v_amount NUMBER;
BEGIN
    v_amount := '12A.50';
END;
/
~~~

Assigning `VARCHAR2` to `NUMBER` triggers implicit conversion; an invalid string raises ORA-01722.

Better:

~~~sql
DECLARE
    v_amount NUMBER;
BEGIN
    v_amount := TO_NUMBER(
        '1250.50',
        '9999990D99',
        'NLS_NUMERIC_CHARACTERS = ''.,'''
    );
END;
/
~~~

Catching exceptions helps log failures:

~~~sql
BEGIN
    -- conversion or DML
    NULL;
EXCEPTION
    WHEN INVALID_NUMBER THEN
        -- log/quarantine per transaction policy
        RAISE;
    WHEN OTHERS THEN
        RAISE;
END;
/
~~~

`INVALID_NUMBER` is the predefined PL/SQL exception for ORA-01722. Date errors can be handled via `SQLCODE`/named exceptions or controlled `WHEN OTHERS`. Never swallow an exception after logging if the transaction is supposed to fail.

## 19. Regression Testing for NLS and Conversions

A solid test suite never runs under only one NLS session configuration.

### 19.1. Numeric Test Matrix

- Decimal dot / group comma.
- Decimal comma / group dot.
- Negative and positive values.
- Zero and leading zeros.
- Precision/scale boundaries.
- Null/empty.
- Currency symbols if permitted by contract.
- ASCII spaces and Unicode spaces.
- Alphabetic/invalid characters.
- Scientific/exponent notation if supported.

### 19.2. Date Test Matrix

- ISO `YYYY-MM-DD`.
- `DD/MM/YYYY` and `MM/DD/YYYY`.
- Month names in supported languages.
- Leap day.
- End-of-month dates.
- Month 13 / day 32.
- With and without time components.
- Fractional seconds.
- Timezone offset/region.
- DST boundaries.
- Null/empty and whitespace.

### 19.3. Running Across Multiple NLS Sessions

In a test database, open sessions with varied NLS values and execute the same test cases. SQL using explicit formats/NLS or properly typed binds must yield deterministic results regardless of session defaults.

### 19.4. Testing Connection Pools

Borrow a connection, alter NLS settings, return it to the pool, and borrow again. Verify that session state is reset per policy. This catches bugs that only manifest when an earlier request ran `ALTER SESSION`.

### 19.5. Testing Optimizer Plans

With datasets containing both valid and invalid rows:
- Gather statistics.
- Exercise queries across differing plans if possible.
- Verify no reliance on predicate order.
- Test varied bind values and bind data types.
- Confirm no unintended implicit conversions occur.

## 20. Incident Handling Checklist

- [ ] Record verbatim ORA-01722/01843/01861 message and stack.
- [ ] Identify `SQL_ID`, module, action, and request/batch ID.
- [ ] Identify column/literal/bind data types on both sides.
- [ ] Determine whether the conversion is explicit or implicit.
- [ ] Capture `NLS_SESSION_PARAMETERS` from the failing connection.
- [ ] Preserve raw input and confirm source locale/format.
- [ ] Locate unparseable values.
- [ ] Inspect Unicode characters, whitespace, and separators.
- [ ] Check date language, format model, and timezone.
- [ ] Inspect `JOIN`, `UNION`, `NVL`/`CASE`, and dynamic SQL.
- [ ] Check bind data types in JDBC.
- [ ] Inspect the execution plan for implicit conversions.
- [ ] Fix at the source contract, staging, SQL, or bind boundary.
- [ ] Avoid changing database-wide NLS without impact assessment.
- [ ] Never silently convert bad data to `0`/`NULL`.
- [ ] Test across multiple NLS sessions and pooled connections.
- [ ] Reconcile data after remediation.
- [ ] Add monitoring/quarantine to prevent recurrence.

## 21. Self-Practice Exercises

1. Distinguish explicit conversion from implicit conversion.
2. Explain the root causes of ORA-01722.
3. List scenarios that can trigger ORA-01843.
4. Explain ORA-01861 using a format mismatch example.
5. Why can the same SQL succeed in SQL Developer but fail in an application?
6. What do the two characters in `NLS_NUMERIC_CHARACTERS` represent?
7. Parse `1,234.56` using `TO_NUMBER` with explicit format and NLS parameters.
8. Parse `1.234,56` under a decimal-comma locale.
9. Why can't you blindly replace all commas with dots?
10. How does `NLS_DATE_LANGUAGE` affect month names?
11. Distinguish `NLS_DATE_FORMAT` from `NLS_DATE_LANGUAGE`.
12. Why is `TO_DATE(date_column, ...)` an anti-pattern?
13. Write an ANSI `DATE` literal for November 14, 2026.
14. Write a whole-day filter condition without calling `TRUNC` on the column.
15. Distinguish `DATE`, `TIMESTAMP`, and `TIMESTAMP WITH TIME ZONE`.
16. Explain the role of `VALIDATE_CONVERSION`.
17. How does `VALIDATE_CONVERSION` handle `NULL`?
18. Write a query to find rows where `amount_text` cannot be converted to `NUMBER`.
19. What can `DEFAULT NULL ON CONVERSION ERROR` mask?
20. Why shouldn't you rely on predicate evaluation order in `WHERE`?
21. Write a `CASE` expression guarding `TO_NUMBER`.
22. How do `DUMP` and `ASCIISTR` help locate abnormal characters?
23. Distinguish `NLS_LANG` from `NLS_SESSION_PARAMETERS` in JDBC Thin.
24. Why can a connection pool leak NLS session state across requests?
25. Write a JDBC `PreparedStatement` binding a `NUMBER` with `BigDecimal`.
26. Write a JDBC bind for a timestamp instead of sending a date string.
27. Why doesn't `PreparedStatement` automatically fix malformed input data?
28. Analyze the impact of implicit conversion on indexes and execution plans.
29. Design staging/quarantine tables for a feed containing multi-locale numbers and dates.
30. Build a test matrix for ORA-01722, ORA-01843, and ORA-01861 across multiple JDK/JDBC/NLS sessions.

**ORA-01722, ORA-01843, and ORA-01861 usually stem from Oracle interpreting text using a data type or NLS setting that mismatches the source data.** Inspect data types, SQL expressions, bind types, and session NLS on the exact connection; preserve raw input, validate against format contracts, and quarantine invalid records. Use `TO_NUMBER`/`TO_DATE`/`TO_TIMESTAMP` with explicit format models and NLS settings when parsing text, bind `NUMBER`/`DATE`/`TIMESTAMP` for typed values, and avoid relying on default NLS or predicate order.
