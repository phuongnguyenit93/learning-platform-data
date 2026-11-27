# Choosing Data Types by Value Domain, Precision, and Query Needs

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Data Types  
> **Objective:** Choose the right data type for each Oracle column based on **business meaning**, **value domain**, **precision**, **storage volume**, and **how the application queries it**; know how to avoid design mistakes that cause rounding errors, loss of time information, implicit conversions, or difficulty using indexes.

## 1. Why is choosing a data type a design decision?

Suppose a sales application has three values:

```text
"001234"          Order code
1234              Quantity
1234.00           Price
```

The three values look similar in characters, but they have **different semantics**:

- The order code `"001234"` needs to preserve leading zeros, is usually compared for equality, and does not participate in addition → store as a string.
- The quantity `1234` is a whole count used in inventory/aggregation calculations → store as an exact integer type.
- The price `1234.00` must preserve units and decimal rounding rules → store as an exact decimal type.

If you put all of them in `VARCHAR2`, the application has to convert strings to numbers for calculations and easily runs into data errors. If you put all of them in `NUMBER`, the order code can lose its leading zeros. **A data type is how business rules are expressed in the database structure**, not just picking a column with enough space to store a value.

### Five questions before choosing

1. **What does the value represent?** Money, quantity, code, name, timestamped event, duration, document, image, or logical flag?
2. **What is the valid domain?** Are negative numbers, fractional parts, `+` signs, leading zeros, Unicode strings, empty values, or `NULL` allowed?
3. **How precise must it be?** Exact to the currency unit, down to milliseconds, or is floating-point approximation acceptable?
4. **What will queries do?** Sum, range filter, sort, join on keys, search strings, search JSON, or read LOBs?
5. **Which systems read/write the data?** Java/JDBC, JSON APIs, BI reports, the Oracle version in use, and timezone/encoding rules?

An appropriate choice must address all of these questions together. Choosing a type based solely on how it looks when displayed can cause errors that are difficult to fix once data grows.

## 2. Overview of Oracle Data Type Groups

| Data Group | Common Oracle Types | Typical Use Cases | Key Considerations |
|---|---|---|---|
| Exact decimal numbers | `NUMBER(p,s)` | Prices, tax rates, scores, quantities with fractional parts | Control precision/scale and rounding |
| Integers | `NUMBER(p,0)`, `NUMBER`; identity/sequence for keys | Quantities, sequence numbers, numeric IDs | Choose sufficient range and do not turn codes with leading zeros into numbers |
| Approximate numbers | `BINARY_FLOAT`, `BINARY_DOUBLE` | Measurements, statistics, scientific computing | Binary floating-point has representation error |
| Variable-length strings | `VARCHAR2(n BYTE/CHAR)` | Names, emails, business codes | Choose BYTE/CHAR semantics; watch collation and Unicode |
| Fixed-length strings | `CHAR(n BYTE/CHAR)` | Truly fixed standard codes | Has padding; not better than VARCHAR2 by default |
| National charset strings | `NCHAR`, `NVARCHAR2` | Specific needs with national character set | When the database uses AL32UTF8, VARCHAR2 is sufficient in many cases |
| Date/time to the second | `DATE` | Birth dates, document dates, datetimes to the second | Oracle DATE **includes hour/minute/second**, no timezone/fractional seconds |
| Sub-second timestamps | `TIMESTAMP(p)` | Internal operation times, events with fractional seconds | Does not carry a timezone |
| Timezone-aware timestamps | `TIMESTAMP WITH TIME ZONE`, `TIMESTAMP WITH LOCAL TIME ZONE` | Global events, auditing, cross-timezone schedules | The two types have different semantics for preserving/displaying timezone |
| Time intervals | `INTERVAL YEAR TO MONTH`, `INTERVAL DAY TO SECOND` | Processing durations, cycles | Do not replace with DATE when the meaning is a duration |
| Large text | `CLOB`, `NCLOB` | Articles, long descriptions, documents | Querying/indexing differs from regular strings |
| Large binary data | `BLOB` | Images, PDFs, binary files | Do not store binary data as VARCHAR2 |
| Small binary / identifiers | `RAW(n)` | 16-byte UUIDs, binary digests | Can be displayed as hex via RAWTOHEX |
| JSON | `JSON` on supported versions; `CLOB`/`VARCHAR2` with `IS JSON` on older versions | Flexible payloads | Frequently queried attributes should be designed intentionally |
| Boolean | `BOOLEAN` in SQL on supported Oracle versions; encoded with CHECK on older versions | On/off flags | Must consider version and NULL semantics |
| Specialized formats | `XMLTYPE`, spatial/`VECTOR` types on appropriate versions | XML, GIS, vector search | Only choose when functionality and Oracle features support it |

**Principle:** Prefer the type whose meaning matches the data most closely. Do not store everything as `VARCHAR2(4000)` just because it makes initial string inserts easy.

## 3. Value Domain Comes First

A **domain** is the set of values that are valid from a business perspective, not merely the set of values a data type can represent.

Examples:

| Field | Business Domain | Choice | Constraints to Consider |
|---|---|---|---|
| `quantity` | Non-negative integer, expected maximum by design | `NUMBER(10,0)` | `NOT NULL`, `CHECK (quantity >= 0)` |
| `unit_price` | Non-negative monetary amount, exact to 2 decimal places | `NUMBER(15,2)` | `NOT NULL`, `CHECK (unit_price >= 0)` |
| `phone_number` | Character string that may contain `+`, leading `0`, and separators | `VARCHAR2(32 CHAR)` | Format validation in application/appropriate constraint |
| `postal_code` | Code that may contain letters and leading zeros | `VARCHAR2(20 CHAR)` | No arithmetic operations |
| `country_code` | Standard fixed-length alphabetic ISO code | `CHAR(2 CHAR)` | Can add FK to a country code table |
| `status` | A defined set of statuses | `VARCHAR2(20 CHAR)` | `CHECK (... IN (...))` or FK to a lookup table |
| `created_at` | Record creation time as an absolute instant | `TIMESTAMP WITH TIME ZONE` | Default `SYSTIMESTAMP`, timezone policy |
| `birth_date` | Calendar date with no time meaning | `DATE` | Normalize time component to 00:00:00 on write |
| `attachment` | Binary content | `BLOB` or object storage with metadata in DB | Storage policy, streaming, security |
| `is_active` | True/false, sometimes with "unknown" | `BOOLEAN` on supported versions or `CHAR(1)` | Three-valued logic rules and `NOT NULL` if required |

**Data types and constraints work together** to protect the value domain. For example, `NUMBER(10,0)` allows negative values, so an integer type alone does not express the rule "non-negative quantity".

Different constraint layers:

- `NOT NULL`: the column must have a value.
- `CHECK`: simple conditions on values, such as non-negative or belonging to a set of statuses.
- `UNIQUE` / `PRIMARY KEY`: uniqueness and row identification.
- `FOREIGN KEY`: the value must exist in a referenced table.
- Application-level validation: complex rules that depend on external data or require detailed error messages.

Do not rely solely on UI validation: data can also enter through ETL, batch jobs, APIs, and other SQL scripts.

## 4. NUMBER: Decimal Precision, Precision, and Scale

### 4.1. What does NUMBER(p,s) mean?

The `NUMBER(p,s)` type in Oracle lets you design **exact decimal** numbers:

- `p` (**precision**): total number of significant digits allowed by the declaration.
- `s` (**scale**): number of digits to the right of the decimal point declared when `s` is positive.
- `NUMBER(p,0)`: an integer in the sense that column values are stored with no fractional part.
- `NUMBER` without specifying `p,s`: a more flexible NUMBER type, suitable when the precision range genuinely needs to be wide; however, for specific business data it is usually better to declare it explicitly.

Examples:

| Type | Valid Example | Illustrative Limit/Meaning |
|---|---|---|
| `NUMBER(5,0)` | `12345` | Up to 5 integer digits, ignoring sign |
| `NUMBER(5,2)` | `999.99` | 3 digits before the decimal point, 2 digits after |
| `NUMBER(12,2)` | `9999999999.99` | 10 integer digits, 2 decimal places |
| `NUMBER(8,4)` | `12.3456` | 8 digits total, 4 digits after the decimal point |
| `NUMBER(10,0)` | `450000` | Integer data with a constrained range |
| `NUMBER` | Exact decimal value within NUMBER limits | Does not enforce currency scale rules by itself |

Oracle NUMBER can represent up to **38 significant digits** when declared with appropriate precision. With `NUMBER(p,s)`, if the fractional part has more digits than the scale, Oracle may **round** on store; if the result exceeds precision, it can raise an error such as `ORA-01438`.

Example:

```sql
CREATE TABLE lab_precision (
    amount NUMBER(5,2)
);

INSERT INTO lab_precision VALUES (12.345);
-- Stored with scale 2: may become 12.35.

INSERT INTO lab_precision VALUES (9999.99);
-- Exceeds NUMBER(5,2) domain: precision error.

ROLLBACK;
```

Because scale can cause Oracle to round, do not use the data type as a substitute for a validation rule like "reject more than 2 decimal places" if the business requires rejecting input rather than rounding it. The application or an appropriate constraint must define the policy clearly.

### 4.2. Choosing NUMBER for Money

Suppose the system needs to store values up to nearly `10^10` currency units with two fractional digits:

```sql
amount NUMBER(12,2) NOT NULL
```

If transactions can reach trillions, increase precision appropriately based on the **projected range over the data lifecycle**, avoiding looking only at current values.

A monetary column also usually needs a **currency unit**:

```sql
amount        NUMBER(18,2) NOT NULL,
currency_code CHAR(3 CHAR) NOT NULL
```

The same number `100.00` means very different things in `VND` versus `USD`. In multi-currency systems, the number of fractional digits also depends on each currency's rules and accounting system; `NUMBER(18,2)` is a design example, **not a universal rule for every currency**.

When Java works with Oracle NUMBER monetary values, use `java.math.BigDecimal` for exact decimal values, and do not use `double` for monetary addition/subtraction in ways that can introduce representation errors.

### 4.3. Integer Values and Surrogate Keys

For quantities:

```sql
quantity NUMBER(10,0) DEFAULT 0 NOT NULL
         CHECK (quantity >= 0)
```

For auto-generated IDs:

```sql
id NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY
   PRIMARY KEY
```

Identity helps generate key values in the database. It solves **ID generation**; it does not automatically validate that an ID is a business code or solve all distributed system requirements.

If a distributed system needs globally unique identifiers, you can consider UUIDs stored as `RAW(16)` or standardized strings; the choice depends on the ID generation mechanism, join characteristics, and APIs.

### 4.4. NUMBER Should Not Be Used for Every Digit String

The following values are usually **codes**, not numbers:

- Phone numbers `+84901234567`.
- Postal codes `00123`.
- Employee codes `000057`.
- Product codes `0123456789012` that have a check digit and must preserve every character exactly.
- Long account numbers that may exceed NUMBER precision or contain leading zeros.

Because they do not require arithmetic, store them as `VARCHAR2`, plus constraints/validation if needed. Storing them as NUMBER can drop leading zeros and turn identifying data into numeric quantities.

## 5. NUMBER vs. BINARY_FLOAT/BINARY_DOUBLE: Exact vs. Approximate

### 5.1. Differences in Representation

`NUMBER` is Oracle's exact decimal numeric type; whereas:

- `BINARY_FLOAT`: binary floating-point number, close to IEEE 754 single precision.
- `BINARY_DOUBLE`: binary floating-point number, close to IEEE 754 double precision.

Decimal values such as `0.1` cannot be represented exactly with a finite number of binary bits in many cases. Therefore, floating-point arithmetic can produce approximate results.

Selection table:

| Need | Prefer | Why |
|---|---|---|
| Money, balances, invoices | `NUMBER(p,s)` | Requires decimal exactness |
| Countable integers | `NUMBER(p,0)` | Avoids fractional parts; use CHECK for range |
| Tax rates needing deterministic rounding rules | `NUMBER(p,s)` with appropriate scale | Controls unit and rounding |
| Physical sensor readings with measurement error | `BINARY_DOUBLE` or `NUMBER` depending on requirements | Floating-point can fit speed and measurement range |
| Scientific algorithms needing approximate numbers | `BINARY_DOUBLE` | Suitable for floating-point calculations |
| Product codes made of digits | `VARCHAR2` | Not a quantity for arithmetic |

Example:

```sql
CREATE TABLE lab_numeric_types (
    id NUMBER PRIMARY KEY,
    exact_value NUMBER(12,4),
    approximate_value BINARY_DOUBLE
);
```

One thing to understand is that floating-point types can represent special values such as NaN or infinity depending on Oracle's capabilities. If the problem requires finite, measurement-valid values, you must actively enforce that in the design.

### 5.2. Comparing Approximate Numbers

Do not expect every `BINARY_DOUBLE` operation to return an exact decimal suitable for strict equality comparison. In floating-point processing, comparing whether the **difference is within an acceptable tolerance** is usually more useful than `=` on computed results.

However, the `epsilon` threshold must not be chosen arbitrarily: it must be based on measurement error, transformations, and scientific/business requirements. For money, it is better **not to introduce floating-point error in the first place**.

### 5.3. NUMBER Types in Java

With JDBC, a NUMBER column can be retrieved as `BigDecimal` when decimal precision must be preserved:

```java
BigDecimal amount = rs.getBigDecimal("AMOUNT");
```

For integer columns whose domain is known to fit within the corresponding Java type, you can retrieve `int` or `long`; for nullable columns, you must handle `NULL` so `NULL` is not mistaken for `0`.

**Do not assume `NUMBER(10)` is always safe with Java `int`:** the range of `NUMBER(10,0)` is larger than a signed 32-bit integer. Combine actual precision, constraints, and application requirements to choose the Java type.

## 6. CHAR, VARCHAR2, and NVARCHAR2: What Do Strings Mean?

### 6.1. VARCHAR2 Is the Common Choice for Variable-Length Text

`VARCHAR2(n)` fits names, emails, status codes, order codes, and many short text fields.

Example:

```sql
customer_name VARCHAR2(150 CHAR) NOT NULL,
email         VARCHAR2(254 CHAR),
order_code    VARCHAR2(40 CHAR)
```

Strings are stored at their actual length within the declared limit and Oracle's byte limit.

**Why not set VARCHAR2(4000) for everything?** Overly broad limits weaken domain expression, allow malformed data to slip in easily, and affect index/application design. Base limits on business constraints: email maximums per system rules, order code formats, or person name display requirements.

### 6.2. BYTE and CHAR Semantics

In a database using AL32UTF8, a Unicode character can occupy from one to multiple bytes. Oracle lets you declare string length using:

- `VARCHAR2(30 BYTE)`: at most **30 bytes**; the actual number of characters may be fewer.
- `VARCHAR2(30 CHAR)`: at most **30 characters** under character length semantics, while still subject to the **maximum byte limit** of the data type in the database configuration.

Example:

```sql
CREATE TABLE lab_text_length (
    code      VARCHAR2(30 BYTE),
    full_name VARCHAR2(30 CHAR)
);
```

If a column contains Vietnamese or multilingual data, using `CHAR semantics` for limits that express character counts is usually more sensible than `BYTE semantics`.

Checking length in characters and bytes:

```sql
SELECT LENGTH('Tiếng Việt')  AS char_length,
       LENGTHB('Tiếng Việt') AS byte_length
FROM dual;
```

On the AL32UTF8 charset, many accented characters occupy multiple bytes, so the two measurements can differ. `LENGTH`/`LENGTHB` are useful when diagnosing length-limit errors.

> **Practical limit:** Under `MAX_STRING_SIZE=STANDARD`, `VARCHAR2` values in SQL have the common limit of **4,000 bytes**; under `EXTENDED`, they can reach **32,767 bytes** in supported cases. `VARCHAR2(4000 CHAR)` does not guarantee storing 4,000 four-byte characters. `MAX_STRING_SIZE` should not be changed just to fix a single column without evaluating database-wide impact.

### 6.3. CHAR: Fixed Length and Padding

`CHAR(n)` is intended for fixed-length strings. Oracle pads with spaces up to the declared length, leading to comparison/display behaviors that require attention.

Example:

```sql
country_code CHAR(2 CHAR)
```

For standard country codes that are always exactly 2 characters long, `CHAR(2 CHAR)` can make sense. However, `CHAR(100)` is not better than `VARCHAR2(100 CHAR)` just because "fixed allocation is faster"; it can introduce padding and confusion over trailing spaces.

For statuses like `'NEW'`, `'PAID'`, `'CANCELLED'` that have different lengths, prefer `VARCHAR2` with a domain constraint.

### 6.4. NCHAR and NVARCHAR2

`NCHAR` and `NVARCHAR2` use Oracle's separately configured **national character set**. They suit certain compatibility/language problems with specific requirements.

If the database is already designed with **AL32UTF8**, `VARCHAR2` can store Unicode for most application data. Do not switch every person-name column to `NVARCHAR2` by default; evaluate source-target charsets, JDBC, and actual requirements. Choosing a national charset does not replace collation design or data normalization.

### 6.5. Empty Strings and NULL in Oracle

In Oracle SQL, a zero-length character string (`''`) is currently treated as equivalent to `NULL` for standard character types like `VARCHAR2`. This is a notable difference compared to many other database management systems.

Consequences:

- You cannot use `''` as a state distinct from NULL in a VARCHAR2 column under current behavior.
- `' '` (a single space) is **different** from an empty string/NULL.
- Use `IS NULL` instead of `= NULL`.
- If the business needs three states ("not entered", "intentionally empty", and "has content"), you must design an extra status column or another convention.

Example:

```sql
SELECT
    CASE WHEN CAST('' AS VARCHAR2(10)) IS NULL
         THEN 'NULL'
         ELSE 'NOT NULL'
    END AS empty_string_result
FROM dual;
```

### 6.6. Collation, Case Sensitivity, and Searching

`VARCHAR2` stores characters, but **comparison/sorting rules** are also affected by collation, `NLS_SORT`, `NLS_COMP`, and version-dependent collation features.

Business rules must clarify:

- Are emails and usernames case-sensitive or case-insensitive?
- Are business codes normalized to uppercase and are they accent-sensitive?
- Does searching Vietnamese names require accent stripping, prefix search, or full-text search?
- Which language's alphabet governs sorting?

Do not solve everything automatically with `UPPER(column)` in queries because an expression on a column can affect whether a regular index can be used. If real queries consistently use a normalization function, consider a **function-based index** or an explicit collation design, after checking the query plan.

For example, email normalization can be applied in the application before writing, or supported by an index/constraint aligned with system rules. There is no single collation rule that fits every business domain.

## 7. DATE, TIMESTAMP, and Timezones: Storing Time Meaning Accurately

### 7.1. What Does Oracle DATE Contain?

In Oracle, `DATE` stores **year, month, day, hour, minute, second**. It:

- Does not store fractional seconds.
- Does not contain a timezone.
- Is not synonymous with a date-only `LocalDate` type in every programming ecosystem.

Example creating a date value with a session-format-independent literal:

```sql
SELECT DATE '2026-11-14' AS day_value
FROM dual;
```

The literal `DATE 'YYYY-MM-DD'` creates the point in time at 00:00:00 on that date, **without attaching a timezone**.

For birth dates or due dates that only have calendar-date meaning, `DATE` is a common choice, but the application must standardize **time component = 00:00:00** or enforce a constraint if only dates are accepted.

### 7.2. TIMESTAMP(p) Stores Fractional Seconds Without a Timezone

`TIMESTAMP(p)` has fractional-second precision according to parameter `p`, for example:

```sql
processed_at TIMESTAMP(6)
```

Literal example:

```sql
SELECT TIMESTAMP '2026-11-14 09:30:45.123456'
FROM dual;
```

This fits timestamps in a context where timezone conventions are already managed by the application, or where fractional seconds are needed without storing a timezone in the value itself.

**Risk:** If a client in Vietnam writes `2026-11-14 09:30:45` and a client in the US writes the same string, the two `TIMESTAMP` values can represent **two different actual instants**, because this type does not indicate timezone.

### 7.3. TIMESTAMP WITH TIME ZONE

`TIMESTAMP WITH TIME ZONE` expresses time together with the appropriate timezone or offset information. It is suitable when you need to know the **absolute instant** an event occurred and work with systems across multiple timezones.

Example:

```sql
CREATE TABLE lab_event_log (
    event_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_name VARCHAR2(100 CHAR) NOT NULL,
    occurred_at TIMESTAMP(6) WITH TIME ZONE
        DEFAULT SYSTIMESTAMP NOT NULL
);
```

Inserting a timestamp with an offset:

```sql
INSERT INTO lab_event_log (event_name, occurred_at)
VALUES (
    'PAYMENT_CONFIRMED',
    TO_TIMESTAMP_TZ(
        '2026-11-14 09:30:45 +07:00',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    )
);

COMMIT;
```

Offset-aware values define the instant more clearly. If the application requires daylight saving time rules or geographic region names, supported timezone regions can be used instead of offsets alone, along with managing the appropriate timezone file version.

### 7.4. TIMESTAMP WITH LOCAL TIME ZONE

`TIMESTAMP WITH LOCAL TIME ZONE` normalizes values to the database timezone on storage and converts them to the session timezone on retrieval. It is useful when users in different locations want to see the same instant in **their session's timezone**, without needing to preserve the input's original timezone metadata.

Comparison:

| Type | Fractional Seconds | Timezone Info | Choose When |
|---|---|---|---|
| `DATE` | No | No | Calendar dates, or points in time to the second in a well-defined context |
| `TIMESTAMP(p)` | Yes | No | Local timestamps where the application manages timezone by convention |
| `TIMESTAMP(p) WITH TIME ZONE` | Yes | Has offset/region info | Global events, timezone reconciliation, and absolute instants |
| `TIMESTAMP(p) WITH LOCAL TIME ZONE` | Yes | Does not preserve original timezone the same way; displayed per session | Multi-timezone timestamp data that should render in the session timezone |

If the requirement is to **preserve the input's source timezone** as a business fact, do not choose `WITH LOCAL TIME ZONE` just because its name contains "TIME ZONE".

### 7.5. DATE / SYSDATE / SYSTIMESTAMP / CURRENT_TIMESTAMP

Some commonly confused functions:

- `SYSDATE`: current time from the database server's operating system as an Oracle `DATE`, accurate to the second.
- `SYSTIMESTAMP`: current timestamp on the database server with timezone information.
- `CURRENT_TIMESTAMP`: current timestamp in the session's timezone, of a timezone-aware type.
- `LOCALTIMESTAMP`: current timestamp in the session's timezone, **without** a timezone.

Example:

```sql
SELECT SYSDATE,
       SYSTIMESTAMP,
       CURRENT_TIMESTAMP,
       LOCALTIMESTAMP
FROM dual;
```

In distributed applications, clearly establish the authoritative time source, session timezone, and user-facing display rules.

### 7.6. Querying by Date: Use Half-Open Intervals

Suppose the `order_date` column is an Oracle `DATE` and is indexed. To find all orders on November 14, 2026:

**Avoid** equality comparison against a date if the column has a time component:

```sql
WHERE order_date = DATE '2026-11-14'
```

That condition only matches values at exactly `00:00:00` on that date.

**Prefer** a half-open interval:

```sql
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15'
```

This approach:

- Includes all points in time within the day, regardless of hour/minute/second.
- Avoids calling `TRUNC(order_date)` on the column for every row.
- Typically gives the optimizer better conditions for an **index range scan** or **partition pruning**, given appropriate design and statistics.

Depending on timezone semantics, for a `TIMESTAMP WITH TIME ZONE` column you must convert the **day boundaries in the right business timezone** into the corresponding point-in-time range. A calendar day in one timezone does not by default match the same day in another timezone.

### 7.7. INTERVAL for Durations

A **duration** is not a **point in time**. Oracle provides:

- `INTERVAL YEAR TO MONTH`: duration in years/months.
- `INTERVAL DAY TO SECOND`: duration in days/hours/minutes/seconds, optionally with fractional seconds.

Example:

```sql
SELECT TIMESTAMP '2026-11-14 09:30:00'
       + INTERVAL '45' MINUTE AS end_time
FROM dual;
```

If you need to store response times measured in milliseconds, sometimes `NUMBER(12,0)` (milliseconds) is also more suitable than `INTERVAL`, especially when computing statistics and exposing values via APIs. Choose based on semantics and actual operations, and document the **unit** clearly to avoid confusing seconds with milliseconds.

## 8. LOB, RAW, and Unstructured Data

### 8.1. VARCHAR2 or CLOB?

`VARCHAR2` suits short or medium text within configuration limits. `CLOB` is for long text, such as article bodies, large product descriptions, or documents.

| Characteristic | VARCHAR2 | CLOB |
|---|---|---|
| Capacity | Has a configured byte limit | Can hold very large amounts of text |
| Querying with `=` / `ORDER BY` | Direct standard SQL operations | Has specific limitations/overhead and dedicated LOB functions |
| B-tree index on column | Possible when length/index type fits | Cannot build a B-tree directly over an entire CLOB like VARCHAR2 |
| Full-text search | Can use suitable options | Typically consider Oracle Text for content search |
| Read/write from JDBC | String for appropriate sizes | Reader/stream or LOB APIs |
| Purpose | Names, codes, short notes | Articles, documents, long content |

Do not choose `CLOB` for every column just to "avoid worrying about size". Columns that need full-value comparisons/joins/indexes should still use data types that can be appropriately declared and indexed.

### 8.2. BLOB and Binary Files

`BLOB` stores binary data such as images, PDFs, or compressed content. Do not turn bytes into a text string and put them in `VARCHAR2` if the data is not genuinely text.

Example:

```sql
CREATE TABLE lab_attachments (
    attachment_id RAW(16) DEFAULT SYS_GUID() NOT NULL,
    original_name VARCHAR2(255 CHAR) NOT NULL,
    mime_type VARCHAR2(120 CHAR) NOT NULL,
    content BLOB,
    created_at TIMESTAMP(6) WITH TIME ZONE
        DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT pk_lab_attachments PRIMARY KEY (attachment_id)
);
```

Choosing whether to store BLOBs in the database or put files in object storage and store only URLs/keys and metadata in Oracle also depends on volume, backup, latency, transactions, access control, and infrastructure. `BFILE` is a reference to an external file managed by the server with different limitations from BLOB; do not treat it like a regular transactional BLOB.

### 8.3. RAW(16) for 128-Bit Identifiers

`RAW(n)` stores bytes without character set conversion. A 128-bit UUID/GUID can be stored in `RAW(16)` to be more compact than a hyphenated hex string.

Example:

```sql
CREATE TABLE lab_uuid_entity (
    entity_id RAW(16) DEFAULT SYS_GUID() PRIMARY KEY,
    title VARCHAR2(120 CHAR) NOT NULL
);

INSERT INTO lab_uuid_entity (title)
VALUES ('Test record');

SELECT RAWTOHEX(entity_id) AS entity_id_hex, title
FROM lab_uuid_entity;
```

`SYS_GUID()` generates a 16-byte RAW identifier in Oracle. If the application requires a specific UUID standard/version, you must align the system's ID generation mechanism; do not assume all GUIDs follow the same UUID version.

### 8.4. Avoid LONG for New Designs

Some legacy systems have `LONG` or `LONG RAW` columns. For new schemas, prefer `CLOB` or `BLOB` depending on the data type, because `LONG` types have major limitations in SQL operations and have been superseded by design.

## 9. JSON, XML, and Specialized Types

### 9.1. JSON: Choose Type by Version and Query Pattern

Oracle provides JSON querying features such as `JSON_VALUE`, `JSON_EXISTS`, and `JSON_TABLE`.

In Oracle 19c, JSON is commonly stored in `VARCHAR2`, `CLOB`, or `BLOB` with an `IS JSON` constraint:

```sql
CREATE TABLE lab_json_legacy (
    id NUMBER PRIMARY KEY,
    payload CLOB
        CONSTRAINT ck_lab_json_valid CHECK (payload IS JSON)
);
```

Example:

```sql
INSERT INTO lab_json_legacy (id, payload)
VALUES (
    1,
    '{"channel":"WEB","priority":2,"paid":true}'
);

SELECT id,
       JSON_VALUE(payload, '$.channel' RETURNING VARCHAR2(20)) AS channel
FROM lab_json_legacy
WHERE JSON_VALUE(payload, '$.priority' RETURNING NUMBER) >= 2;
```

In newer versions that support the **native JSON data type** (for example Oracle Database 21c and subsequent supported releases), you can use the `JSON` type so Oracle stores and operates on JSON data using that version's native mechanisms.

**When should fields be extracted into relational columns?** If `channel`, `status`, `customer_id`, or `created_at` are always core attributes and are frequently filtered/joined/indexed, making them strongly typed columns makes domain constraints and optimization easier.

JSON is useful for flexible parts of the structure, not a reason to replace every relational column with a single payload.

### 9.2. Querying JSON and Indexing

If you frequently filter on:

```sql
WHERE JSON_VALUE(payload, '$.priority' RETURNING NUMBER) >= 2
```

A DBA can consider function-based indexes, JSON search indexes, or specialized index structures supported by the version. The decision should be based on queries and execution plans; a large JSON payload can slow queries down if every record has to be parsed/evaluated without an appropriate access path.

### 9.3. XMLTYPE and Specialized Data

If the business uses XML documents and needs to manipulate them by XML structure, `XMLTYPE` together with XML functions may be more appropriate than storing XML as an unconstrained string.

Some Oracle features also provide specialized types for spatial data, vectors, and other search problems. Only use them when the version/edition supports them and **both the data domain and query needs** genuinely require them; do not replace coordinates or vector representations with comma-separated text just to avoid learning specialized types.

## 10. BOOLEAN: Choose by Oracle Version and Three-Valued Logic

### 10.1. SQL BOOLEAN in Newer Oracle Releases

Oracle Database **23c/23ai and appropriate newer releases** support the `BOOLEAN` type in SQL. A boolean column clearly expresses the domain **TRUE, FALSE**, and `NULL` (when nullable).

Syntax example on an Oracle version supporting SQL BOOLEAN:

```sql
CREATE TABLE lab_flags_new (
    id NUMBER PRIMARY KEY,
    is_active BOOLEAN DEFAULT TRUE NOT NULL
);
```

`BOOLEAN` expresses intent more clearly than using strings `'Y'`/`'N'` for a logical flag, but you must check compatibility if the application/database also needs to support 19c or 21c.

### 10.2. Before SQL BOOLEAN: Constrained Flag Encoding

In Oracle 19c and many systems in production, **SQL column BOOLEAN** is not supported as a regular column type, even though **PL/SQL BOOLEAN** exists in the PL/SQL language.

Common pattern:

```sql
CREATE TABLE lab_flags_legacy (
    id NUMBER PRIMARY KEY,
    is_active CHAR(1 CHAR) DEFAULT 'Y' NOT NULL,
    CONSTRAINT ck_lab_is_active
        CHECK (is_active IN ('Y', 'N'))
);
```

Or:

```sql
is_active NUMBER(1,0) DEFAULT 1 NOT NULL
          CHECK (is_active IN (0,1))
```

`NULL` should only be allowed if the business truly has an "unknown/undecided" state. If the column represents a mandatory flag, use `NOT NULL`.

**Important:** `CHECK (is_active IN (...))` does not by itself forbid NULL because an UNKNOWN result still satisfies SQL CHECK rules; add `NOT NULL` if NULL must be disallowed.

## 11. Type Selection Table by Business Scenario

| Data | Recommended Type | Why | Avoid |
|---|---|---|---|
| Internal record ID | `NUMBER`/`NUMBER(p,0)` with identity/sequence or `RAW(16)` if using GUID | Key with an appropriate generation strategy | Using person name/email as the primary key by default |
| Order code `0000123` | `VARCHAR2(30 CHAR)` | Preserves leading zeros and formatting | `NUMBER` |
| Inventory quantity | `NUMBER(10,0)` + CHECK | Whole-number count, non-negative | `VARCHAR2` |
| Selling price | `NUMBER(18,2)` or appropriate scale | Decimal exactness | `BINARY_DOUBLE` for money |
| Rate with four decimal places | `NUMBER(p,4)` with sufficiently wide p | Clearly defined precision | `FLOAT` without defined rounding rules |
| Sensor measurement | `BINARY_DOUBLE` or `NUMBER(p,s)` | Depends on error tolerance/calculations | Defaulting to currency-style scale when unsuitable |
| Phone number | `VARCHAR2(32 CHAR)` | Has `+`, leading zero, formatting characters | `NUMBER` |
| Postal code | `VARCHAR2(20 CHAR)` | May contain letters and leading zeros | `NUMBER` |
| Vietnamese customer name | `VARCHAR2(150 CHAR)` | Character-based length and Unicode | `CHAR(150)` |
| ISO currency code | `CHAR(3 CHAR)` + FK/CHECK | Standard fixed length | `NUMBER` |
| Birth date | `DATE`, convention to strip time | Calendar date | `VARCHAR2('dd/mm/yyyy')` |
| Global audit event | `TIMESTAMP(6) WITH TIME ZONE` | Unambiguous instant and timezone | `VARCHAR2` or TIMESTAMP without timezone convention |
| Processing duration | `INTERVAL DAY TO SECOND` or `NUMBER` with unit | Duration differs from timestamp | `DATE` |
| Short notes | `VARCHAR2(1000 CHAR)` when byte limit fits | Short text access | Unnecessary `CLOB` |
| Long article body | `CLOB` | Large text | `VARCHAR2` exceeding limits |
| Image/PDF file | `BLOB` or external storage + metadata | Binary data | `VARCHAR2` |
| 128-bit UUID | `RAW(16)` or standard string if compatibility needed | Exact bytes, compact | `NUMBER` without considering representation |
| Flexible payload | `JSON` or JSON-storing type with `IS JSON` per version | Structured document | Unvalidated text |
| On/off flag | `BOOLEAN` when supported or `CHAR(1)` + CHECK | Clear logical domain | Unconstrained `VARCHAR2(100)` |

The `p,s,n` values in the table are **design illustrations**. Real projects must determine limits based on business analysis, existing data, and projected growth.

## 12. Example of Designing an Order Schema with Consistent Data Types

Suppose the system needs to store:

- An internal ID generated by Oracle.
- A display order code that may contain leading zeros and letters.
- A numeric customer ID.
- Total amount and currency.
- Creation time with timezone.
- Sales channel from a finite set of values.
- Optional long text notes.

DDL:

```sql
CREATE TABLE app_orders (
    order_id NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY,
    order_code VARCHAR2(40 CHAR) NOT NULL,
    customer_id NUMBER(19,0) NOT NULL,
    total_amount NUMBER(18,2) NOT NULL,
    currency_code CHAR(3 CHAR) NOT NULL,
    created_at TIMESTAMP(6) WITH TIME ZONE
        DEFAULT SYSTIMESTAMP NOT NULL,
    sales_channel VARCHAR2(12 CHAR) NOT NULL,
    note_text CLOB,

    CONSTRAINT pk_app_orders PRIMARY KEY (order_id),
    CONSTRAINT uq_app_orders_code UNIQUE (order_code),
    CONSTRAINT ck_app_orders_total CHECK (total_amount >= 0),
    CONSTRAINT ck_app_orders_channel
        CHECK (sales_channel IN ('WEB', 'APP', 'STORE'))
);
```

In a real application, `CUSTOMER_ID` usually has a **foreign key** to the customers table, `CURRENCY_CODE` may have an FK to a currency lookup table, and other constraints related to transaction rules. This example focuses on choosing data types.

Insert two orders:

```sql
INSERT INTO app_orders (
    order_code, customer_id, total_amount, currency_code,
    created_at, sales_channel, note_text
) VALUES (
    '00001582', 1001, 125000.00, 'VND',
    TO_TIMESTAMP_TZ(
        '2026-11-14 09:30:00 +07:00',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    ),
    'WEB', 'Deliver during business hours'
);

INSERT INTO app_orders (
    order_code, customer_id, total_amount, currency_code,
    created_at, sales_channel
) VALUES (
    '00001583', 1002, 89000.00, 'VND',
    TO_TIMESTAMP_TZ(
        '2026-11-14 10:00:00 +07:00',
        'YYYY-MM-DD HH24:MI:SS TZH:TZM'
    ),
    'APP'
);

COMMIT;
```

Notable characteristics:

- `order_code` preserves the string `00001582`.
- `total_amount` is an exact decimal, suitable for aggregating amounts with the same currency.
- `created_at` preserves the offset information at write time; timezone-based queries need proper boundaries.
- `sales_channel` is constrained to `WEB`, `APP`, `STORE`.
- `note_text` allows NULL when there is no note.
- `order_id` is a surrogate key, separated from the business order code.

### 12.1. Aggregating Money in the Right Unit

```sql
SELECT currency_code,
       SUM(total_amount) AS total_amount
FROM app_orders
GROUP BY currency_code;
```

Do not add `100 USD` and `100 VND` to get `200` without converting by exchange rate and business rules. `NUMBER` ensures proper decimal addition; understanding the **unit** remains part of the business model.

### 12.2. Querying Order Code Using Its String Type

```sql
SELECT order_id, order_code, total_amount
FROM app_orders
WHERE order_code = '00001582';
```

The `ORDER_CODE` column is a string. Do not write `WHERE order_code = 1582` because implicit conversion can break leading-zero semantics, fail on alphanumeric codes, and affect how the optimizer uses an index.

### 12.3. Querying Time in the Right Timezone

For example, to request data for **14/11/2026 in UTC+07:00**, use two boundary points with explicit offsets:

```sql
SELECT order_code, created_at
FROM app_orders
WHERE created_at >= TO_TIMESTAMP_TZ(
          '2026-11-14 00:00:00 +07:00',
          'YYYY-MM-DD HH24:MI:SS TZH:TZM'
      )
  AND created_at < TO_TIMESTAMP_TZ(
          '2026-11-15 00:00:00 +07:00',
          'YYYY-MM-DD HH24:MI:SS TZH:TZM'
      );
```

Using boundary points matches the day semantics at the chosen offset. For regions with DST, use a **timezone region** and appropriate conversion rules, because a local day is not necessarily always 24 hours long.

## 13. How Data Types Affect the Optimizer, Indexes, and Queries

### 13.1. Comparisons Must Be Type-Consistent

SQL:

```sql
SELECT *
FROM app_orders
WHERE customer_id = 1001;
```

is appropriate because `CUSTOMER_ID` is a NUMBER.

Conversely:

```sql
WHERE customer_id = '1001'
```

can cause Oracle to perform an **implicit conversion** from string to number, depending on context. Even if it sometimes returns the expected result, the application should use a properly typed numeric bind variable to avoid NLS/implicit-cast issues and data errors.

For string columns:

```sql
WHERE order_code = '00001582'
```

do not pass an integer value just because the order code looks numeric. Oracle converting the **column** with `TO_NUMBER(order_code)` can fail when non-numeric codes exist and make a regular index hard to use.

### 13.2. Keep Queried Columns Unwrapped in Range Filters

With `DATE`:

```sql
-- Less favorable for a regular index if there is no function-based index:
WHERE TRUNC(order_date) = DATE '2026-11-14'

-- Usually better for range filtering:
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15'
```

There is no rule that "a function on a column is always slow"; Oracle has function-based indexes and optimizer transformations. However, direct predicates on the column with properly typed binds are usually easier to optimize.

### 13.3. Numeric and String Sorting Differ

Suppose you have the values:

```text
"2", "10", "100"
```

Stored in `VARCHAR2` and sorted lexicographically, they can come out as `"10", "100", "2"`; stored in `NUMBER` and ordered numerically, they come out as `2, 10, 100`.

Ask: is this a **code** or a **numeric magnitude**? Do not choose NUMBER just so "ORDER BY comes out right" if the data is actually a code with its own rules. When a code needs to be sorted by its numeric part, design a dedicated sort column or an appropriate splitting/normalization rule.

### 13.4. Key Size and Indexes

Columns used as a **primary key**, **foreign key**, or join column commonly appear in indexes. Overly large types can increase index size and memory/I/O cost.

Examples:

- Short IDs with `NUMBER`/`RAW(16)` are usually more compact than an ID string several hundred characters long.
- If a key is a business code of moderate length, `VARCHAR2` can still be appropriate.
- A `CLOB` column is not suitable for direct use as a B-tree primary key.
- Strings with case-insensitive comparisons need a corresponding normalization/collation/index strategy.

Do not force every key to be a NUMBER; evaluate stability, uniqueness, data domain, and integration patterns.

### 13.5. Data Type Choice and Partitioning

Partitioning by date usually requires a column carrying a meaningful time value. If `created_at` is stored as a string `'14/11/2026 09:30'`, filtering by month/quarter, sorting, and partition management become harder and easily NLS-dependent.

With a properly typed time column, you can design **range partitioning** by time or other Oracle-supported strategies; whether it is optimal still depends on workload and version.

### 13.6. Statistics and Cardinality

The optimizer uses statistics, histograms, data density, and column type information to estimate the number of matching rows. A status column with only a few values is very different from a nearly unique UUID column.

The right data type together with appropriate **constraints**, **statistics**, and indexes helps Oracle optimize more accurately. However, you cannot conclude that changing the type alone will make every query fast: you must inspect execution plans and actual I/O metrics.

## 14. NULL, Default Values, and the Meaning of Missing Data

`NULL` represents **no known/provided value**, distinct from `0`, `FALSE`, a space string, or a sentinel date.

Examples:

- `discount_amount = 0`: confirmed no discount.
- `discount_amount IS NULL`: discount information is not yet available, or not applicable per system rules.
- `birth_date IS NULL`: birth date unknown.
- `is_active = FALSE`: confirmed inactive.
- `is_active IS NULL`: status unknown, if the design permits.

Do not set sentinel dates like `DATE '1900-01-01'` or numbers like `-1` as "unknown" codes when they could be interpreted as valid values. If "not applicable" must be distinguished from "unknown", you can add an explicit status column.

### DEFAULT Does Not Replace NOT NULL

Example:

```sql
quantity NUMBER(10,0) DEFAULT 0 NOT NULL
```

`DEFAULT 0` provides a value when the application omits the column in an INSERT (depending on syntax/configuration), while `NOT NULL` forbids NULL values. If an explicit NULL needs to be replaced by a default in certain situations, Oracle versions provide the `DEFAULT ON NULL` syntax where appropriate.

For audit timestamp columns:

```sql
created_at TIMESTAMP(6) WITH TIME ZONE
    DEFAULT SYSTIMESTAMP NOT NULL
```

Determine whether the application is allowed to override this timestamp or whether the database/triggers should manage it entirely. Lessons about data types and write rules should not be conflated.

### SQL Three-Valued Logic

Example:

```sql
SELECT *
FROM app_orders
WHERE sales_channel <> 'WEB';
```

If `sales_channel` is nullable, `NULL` rows are not automatically selected by the `<>` comparison, because the condition evaluates to UNKNOWN. To include NULL rows, state it explicitly, for example:

```sql
WHERE sales_channel <> 'WEB'
   OR sales_channel IS NULL
```

Designing `NOT NULL` appropriately can simplify queries; do not blindly forbid NULL on every column when the business domain genuinely has valid unknown information.

## 15. Designing Data Types with Java/JDBC

Java applications need to map Oracle values to appropriate Java types. The table below is common guidance; exact mapping details also depend on the JDBC driver, Oracle version, and application timezone conventions.

| Oracle | Common Java Type | What to Watch |
|---|---|---|
| `NUMBER(p,s)` with fractional part | `BigDecimal` | Preserves exact decimal and scale policy |
| `NUMBER(p,0)` | `Integer`, `Long`, or `BigDecimal` depending on range | NULL and overflow; large NUMBER can exceed long |
| `BINARY_DOUBLE` | `Double` | Accepts floating-point error |
| `VARCHAR2` / `CHAR` | `String` | Unicode, CHAR padding, nullability |
| `DATE` | `java.sql.Timestamp`/`Date` or suitable java.time mapping | Oracle DATE has time to the second; do not accidentally drop the time component |
| `TIMESTAMP` | `LocalDateTime` or corresponding JDBC object | No timezone |
| `TIMESTAMP WITH TIME ZONE` | `OffsetDateTime` or appropriate Oracle JDBC timezone API | Check driver support, offset/region semantics |
| `CLOB` | `Clob`, `Reader`, or `String` for small sizes | Streaming, memory, connection lifetime |
| `BLOB` | `Blob`/`InputStream` | Streaming and size limits |
| `RAW(16)` | `byte[]`/application ID encoding | Watch byte order and UUID format |
| SQL `BOOLEAN` on supported versions | `Boolean` depending on JDBC driver | SQL BOOLEAN and PL/SQL BOOLEAN vary by version |

Example using bind variables instead of string concatenation:

```java
String sql = """
    INSERT INTO app_orders (
        order_code, customer_id, total_amount,
        currency_code, sales_channel
    ) VALUES (?, ?, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, "00001584");
    ps.setLong(2, 1003L);
    ps.setBigDecimal(3, new BigDecimal("153000.00"));
    ps.setString(4, "VND");
    ps.setString(5, "WEB");
    ps.executeUpdate();
}
```

**Why use `PreparedStatement`?**

- Bind values are passed with the appropriate type/format instead of concatenating SQL.
- Prevents SQL injection when passing input.
- Reduces dependence on how Oracle interprets date/number strings under NLS.
- Improves SQL cursor reuse when queries differ only in parameter values.

The sample code uses a Java text block, which requires a Java version that supports that feature; replace with regular string literals in older environments. `setBigDecimal` with `new BigDecimal("153000.00")` preserves the decimal value from a string.

### Datetimes in JDBC

A real-world bug is writing local time into a timezone-less `TIMESTAMP`, and then having an application on another machine interpret it in a different timezone. Define the **contract** for each column:

- Does this column store a **calendar date** or an **instant**?
- Does the value come from the database or the client?
- Is the value normalized to UTC, or does it store an offset/timezone?
- Which session timezone do the driver and Oracle session use?
- Does the API return ISO-8601 with an offset or only a datetime string?

Answering these questions matters more than "using TIMESTAMP because the name sounds more modern than DATE".

## 16. Explicit Conversion and Avoiding NLS Dependence

### 16.1. Date Literals and TO_DATE

Avoid writing:

```sql
WHERE order_date = '14/11/2026'
```

This string may be implicitly converted by Oracle based on the session's `NLS_DATE_FORMAT`; running it in another environment can fail or misinterpret the date.

Prefer:

```sql
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15'
```

Or if the input is a string with an explicit format:

```sql
TO_DATE('14/11/2026', 'DD/MM/YYYY')
```

For timezone-aware timestamps, use `TO_TIMESTAMP_TZ` with a format mask representing the offset or region. In JDBC applications, prefer binding datetime values using typed APIs rather than converting everything to strings.

### 16.2. TO_CHAR for Display

`TO_CHAR` is useful for formatting output:

```sql
SELECT TO_CHAR(
           DATE '2026-11-14',
           'DD/MM/YYYY'
       ) AS formatted_date
FROM dual;
```

However, `'14/11/2026'` is a **display** format, not a date storage type. Dates stored in a `DATE` column should be filtered, calculated, and sorted as temporal values.

### 16.3. Numeric Strings and Decimal Separators

In environments with different NLS settings, a string value `'1,23'` can be interpreted differently regarding decimal and grouping separators. To store into a NUMBER column, the application should use numeric binds or convert explicitly with the appropriate format/NLS as required.

General example:

```sql
SELECT TO_NUMBER(
           '1234.56',
           '9999D99',
           'NLS_NUMERIC_CHARACTERS = ''.,'''
       ) AS parsed_amount
FROM dual;
```

In this example, `D` is the decimal separator under the specified NLS configuration. Do not store monetary amounts as `'1.234,56'` and expect every client to interpret them the same way.

## 17. Inspecting Existing Data Types in an Oracle Schema

You can inspect column metadata via `USER_TAB_COLUMNS`:

```sql
SELECT column_id,
       column_name,
       data_type,
       data_length,
       char_used,
       char_length,
       data_precision,
       data_scale,
       nullable
FROM user_tab_columns
WHERE table_name = 'APP_ORDERS'
ORDER BY column_id;
```

Metadata columns to know:

- `DATA_TYPE`: Oracle data type, such as NUMBER, VARCHAR2, TIMESTAMP WITH TIME ZONE.
- `DATA_LENGTH`: length in bytes in metadata.
- `CHAR_USED`: for applicable character columns, `B` for byte semantics, `C` for char semantics.
- `CHAR_LENGTH`: declared character length for columns supporting character semantics.
- `DATA_PRECISION` and `DATA_SCALE`: precision/scale details for numbers.
- `NULLABLE`: whether NULL is allowed according to metadata.

To read metadata from another schema when authorized:

```sql
SELECT owner, table_name, column_name, data_type
FROM all_tab_columns
WHERE owner = 'APP_SCHEMA'
  AND table_name = 'APP_ORDERS'
ORDER BY column_id;
```

`USER_TAB_COLUMNS` typically shows objects in the current schema; `ALL_TAB_COLUMNS` displays the scope of objects the user has privileges to see. Unquoted object names are usually normalized to uppercase by Oracle in the data dictionary.

### Checking Constraints

```sql
SELECT constraint_name, constraint_type, status
FROM user_constraints
WHERE table_name = 'APP_ORDERS'
ORDER BY constraint_name;
```

Examples of constraint types: `P` = primary key, `U` = unique, `C` = check (including many NOT NULL constraints reflected structurally), `R` = foreign key. To view detailed CHECK expressions, query metadata according to the capabilities and column types of the version in use.

### Understanding Statistics

After `DBMS_STATS`, statistics such as `NUM_DISTINCT`, `NUM_NULLS`, and histograms can help analyze how the optimizer views a column. They do not replace the business domain: "the column currently has only three statuses" does not mean the design may arbitrarily add a fourth status, and "prices are currently under one million" does not mean the NUMBER domain must be capped at one million.

## 18. Design Anti-Patterns and Alternatives

### 18.1. Using VARCHAR2 for Datetimes

**Problem:** Strings like `'31/12/2026'` are hard to compute intervals on, depend heavily on format, and sort lexicographically rather than chronologically.

**Alternative:** `DATE`, `TIMESTAMP`, or `TIMESTAMP WITH TIME ZONE` according to semantics; apply formatting in the presentation layer.

### 18.2. Using BINARY_DOUBLE for Money

**Problem:** Binary approximate representation can introduce errors during calculations.

**Alternative:** `NUMBER(p,s)` and `BigDecimal` in Java; clearly specify scale and rounding.

### 18.3. Using NUMBER for Codes with Leading Zeros

**Problem:** `001234` becomes `1234`, losing identifying information.

**Alternative:** `VARCHAR2` with format/uniqueness constraints.

### 18.4. Using Overly Long CHAR for Names or Descriptions

**Problem:** Padding and fixed size cause friction in comparisons and display.

**Alternative:** `VARCHAR2(n CHAR)` for variable-length text.

### 18.5. Using CLOB for Frequently Joined/Sorted Fields

**Problem:** CLOB lacks regular B-tree indexing and standard comparison behavior like small string columns.

**Alternative:** Separate short lookup keys/columns into `VARCHAR2`/NUMBER; reserve CLOB for large content.

### 18.6. Using Magic Values Instead of NULL

**Problem:** `-1`, `1900-01-01`, or `'UNKNOWN'` can be mistaken for real data and skew statistics/calculations.

**Alternative:** NULL when data is genuinely unknown; a dedicated status or lookup table when the business needs to distinguish multiple conditions.

### 18.7. Omitting CHECK for Narrow-Domain Columns

**Problem:** `status VARCHAR2(100)` allows invalid values like `'PADI'` without the database blocking them.

**Alternative:**

```sql
status VARCHAR2(20 CHAR) NOT NULL
       CHECK (status IN ('NEW', 'PAID', 'CANCELLED'))
```

For statuses that change frequently or carry their own metadata, use a reference table and foreign key instead of a long hard-coded list.

### 18.8. Storing Everything in JSON

**Problem:** Core relational attributes are hard to constrain with FKs and hard to optimize for joins/range queries if they live only inside a payload.

**Alternative:** Relational columns for frequently queried fields and JSON for flexible information.

### 18.9. Implicit Conversion in WHERE Clauses

**Problem:** Wrong NLS assumptions, conversion errors on invalid data, and unintended index usage.

**Alternative:** Bind the right type and convert explicitly once at the data entry boundary.

## 19. Workflow for Choosing a Data Type for a New Column

When designing a new column, you can follow this process:

### Step 1 — Write a one-sentence business description

Example: "`discount_rate` is a discount ratio from 0 to 1, requiring up to four decimal places."

This sentence is better than "discount_rate is a number" because it specifies the domain and precision.

### Step 2 — Pick the type family by nature

- Exact numbers → `NUMBER`.
- Approximate numbers → `BINARY_DOUBLE` when appropriate.
- Strings → `VARCHAR2`, or `CHAR` when truly fixed.
- Dates/timestamps/durations → one of the temporal types.
- Long content, bytes, JSON → a type suited to the nature of the data.

### Step 3 — Define exact limits

Example ratio from 0 to 1 with four fractional digits:

```sql
discount_rate NUMBER(5,4) DEFAULT 0 NOT NULL
              CHECK (discount_rate BETWEEN 0 AND 1)
```

`NUMBER(5,4)` has one digit before the decimal point and four fractional digits, enough for `1.0000`. If the business defines a 0–100 percentage instead of a 0–1 ratio, a different domain and precision are required; name and document the unit clearly.

### Step 4 — Choose NULL and default rules

Ask whether the value is mandatory, and whether missing data differs from `0`/`FALSE`. Add `NOT NULL`, `DEFAULT`, or a status column based on business meaning, not habit.

### Step 5 — Review query and indexing patterns

- Frequently filtered by `customer_id` → ID type consistent with the referenced table and properly indexed.
- Frequently searched by date → semantically right DATE/TIMESTAMP, range predicates, and partitioning if appropriate.
- Frequently searched accent-/case-insensitively → collation/index strategy.
- Frequently searched inside large text bodies → consider Oracle Text.
- Frequently filtering JSON keys → consider dedicated columns or JSON indexes.

### Step 6 — Verify integration compatibility

Check Java/JDBC mapping, JSON serialization, byte/Unicode limits, timezones, compatibility of the target Oracle version, and schema migration strategy when data already exists.

## 20. Comprehensive Practice Exercises

### Exercise 1 — Choose Types for a Users Table

Design the fields:

1. `user_id`: auto-generated internal ID.
2. `display_name`: Unicode name up to 120 characters.
3. `phone`: phone number that may start with `+84`.
4. `birth_date`: birth date with no business time component.
5. `registered_at`: registration time, storing exact timezone.
6. `active_flag`: Y/N only, supporting Oracle 19c.
7. `profile_description`: description that may be tens of thousands of characters long.

Suggested DDL:

```sql
CREATE TABLE lab_users (
    user_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name VARCHAR2(120 CHAR) NOT NULL,
    phone VARCHAR2(32 CHAR),
    birth_date DATE,
    registered_at TIMESTAMP(6) WITH TIME ZONE
        DEFAULT SYSTIMESTAMP NOT NULL,
    active_flag CHAR(1 CHAR) DEFAULT 'Y' NOT NULL,
    profile_description CLOB,
    CONSTRAINT ck_lab_users_active CHECK (active_flag IN ('Y', 'N'))
);
```

Discussion: should `phone` be `UNIQUE`? The answer depends on phone number reuse policies, family accounts, international normalization, and NULL data—it **cannot** be decided from the `VARCHAR2` type alone.

### Exercise 2 — Find Flaws in an Initial Design

Suppose we have the schema:

```sql
CREATE TABLE bad_orders (
    order_code NUMBER,
    price BINARY_DOUBLE,
    created_at VARCHAR2(30),
    customer_phone NUMBER,
    status VARCHAR2(4000)
);
```

Tasks:

- List at least five risks.
- Propose replacement types.
- Add constraints to protect the domain.
- Explain how date-based queries will be affected.
- State which Java type should be used for price.

**Guidance:** Order code and phone should use VARCHAR2, price NUMBER(p,s), created_at a temporal type, status appropriately sized VARCHAR2 with CHECK/FK; Java BigDecimal for price.

### Exercise 3 — Distinguish NUMBER and BINARY_DOUBLE Results

Create the table:

```sql
CREATE TABLE lab_math (
    id NUMBER PRIMARY KEY,
    exact_value NUMBER(12,2),
    float_value BINARY_DOUBLE
);

INSERT INTO lab_math VALUES (1, 0.10, 0.10);
INSERT INTO lab_math VALUES (2, 0.20, 0.20);
COMMIT;

SELECT SUM(exact_value) AS exact_total,
       SUM(float_value) AS approximate_total
FROM lab_math;
```

Explain why one should not conclude that a monetary algorithm can use floating-point just because the displayed result rounds to `0.3`. Distinguish between **approximate internal value** and **display formatting**.

### Exercise 4 — Choose a Time Type and Query a Full Day

Given the table:

```sql
CREATE TABLE lab_visits (
    visit_id NUMBER PRIMARY KEY,
    visited_at DATE NOT NULL
);

INSERT INTO lab_visits VALUES (
    1,
    TO_DATE('14/11/2026 08:15:00', 'DD/MM/YYYY HH24:MI:SS')
);

INSERT INTO lab_visits VALUES (
    2,
    TO_DATE('14/11/2026 23:59:59', 'DD/MM/YYYY HH24:MI:SS')
);

COMMIT;
```

Write a query to retrieve all `VISITED_AT` values on 14/11/2026 without missing rows whose time is not 00:00:00:

```sql
SELECT *
FROM lab_visits
WHERE visited_at >= DATE '2026-11-14'
  AND visited_at <  DATE '2026-11-15';
```

Discussion: if the data is timestamp with timezone and customers are in multiple regions, you need to know which timezone defines the concept of "on that day".

### Exercise 5 — Read Metadata Instead of Guessing

Create a sample table with NUMBER, VARCHAR2 CHAR semantics, and TIMESTAMP. Run:

```sql
SELECT column_name, data_type,
       data_precision, data_scale,
       data_length, char_used, char_length
FROM user_tab_columns
WHERE table_name = 'LAB_USERS'
ORDER BY column_id;
```

Explain why `DATA_LENGTH` and `CHAR_LENGTH` are not always identical, and why `DATA_PRECISION/DATA_SCALE` must be inspected when reading NUMBER types.

### Exercise 6 — Choose Types for Sensor Data

The system receives:

- `sensor_code` in the format `"0008-A"`.
- `measured_at` is the measurement time accurate to milliseconds, with devices located in multiple countries.
- `temperature_c` can be negative and has measurement error.
- `battery_pct` is a number from 0 to 100, requiring one digit after the decimal point.
- `raw_packet` is the device's raw bytes.

Suggested mapping:

| Column | Viable Type |
|---|---|
| `sensor_code` | `VARCHAR2(32 CHAR)` |
| `measured_at` | `TIMESTAMP(3) WITH TIME ZONE` |
| `temperature_c` | `BINARY_DOUBLE` or `NUMBER(p,s)` depending on measurement characteristics |
| `battery_pct` | `NUMBER(4,1) CHECK (battery_pct BETWEEN 0 AND 100)` |
| `raw_packet` | `BLOB` or `RAW(n)` if packets have a small, fixed limit |

Question: why must the measurement domain of `temperature_c` still be validated with appropriate logic/constraints even though the numeric type already represents negative numbers?

## 21. Data Type Selection Decision Tree

```text
What value needs to be stored?
|
+-- Numeric quantity for calculation?
|      |
|      +-- Needs decimal exactness (money, counts)?
|      |      └── NUMBER(p,s), domain constraints
|      |
|      +-- Accepts floating-point approximation?
|             └── BINARY_DOUBLE / BINARY_FLOAT
|
+-- Character string or identifier code?
|      |
|      +-- Variable length, Unicode?
|      |      └── VARCHAR2(n CHAR), appropriate charset/collation
|      |
|      +-- Standard fixed length?
|      |      └── CHAR(n CHAR) when padding fits
|      |
|      +-- Long text?
|             └── CLOB
|
+-- Time?
|      |
|      +-- Calendar date / to the second, no timezone needed?
|      |      └── DATE (clear convention for time component)
|      |
|      +-- Needs fractional seconds, no timezone needed?
|      |      └── TIMESTAMP(p)
|      |
|      +-- Needs explicit instant/timezone?
|      |      └── TIMESTAMP WITH TIME ZONE
|      |
|      +-- Wants display in session timezone?
|      |      └── TIMESTAMP WITH LOCAL TIME ZONE
|      |
|      +-- Is a time duration?
|             └── INTERVAL or NUMBER with unit
|
+-- Binary data?
|      |
|      +-- Small/fixed (UUID)?
|      |      └── RAW(n)
|      |
|      +-- Large files/bytes?
|             └── BLOB
|
+-- Flexibly structured data?
|      |
|      +-- JSON: native JSON or CLOB/VARCHAR2/BLOB + IS JSON
|      +-- XML: XMLTYPE when appropriate
|
+-- True/false value?
       └── SQL BOOLEAN on supported versions,
           or CHAR(1)/NUMBER(1) with CHECK
```

After choosing a type family, you **must still** check: whether `NOT NULL` is needed, whether the domain/precision/scale are sufficient, whether indexes/joins make sense, whether byte/Unicode/timezone rules are interpreted consistently, and whether Java/JDBC passes the right types.

---

## 22. Key Takeaways When Designing Oracle Tables

A good Oracle column expresses the meaning of the data and helps the database enforce business rules:

- **Money, quantities, decimal rates:** use `NUMBER` with precision/scale matching the domain; money requires rounding rules and currency.
- **Approximate measurements:** consider `BINARY_DOUBLE` and the error characteristics of calculations.
- **Identifiers containing letters/leading zeros:** use strings; do not force NUMBER just because digits are present.
- **Unicode text:** design with `VARCHAR2(n CHAR)` and an appropriate charset; distinguish byte limits from character limits.
- **Dates and timestamps:** distinguish calendar dates, timezone-less timestamps, timezone-aware instants, and durations.
- **Large text/bytes:** use `CLOB`/`BLOB` or an appropriate storage solution; do not cram them into small columns.
- **Flags/JSON/specialized types:** verify against the SQL version and how the application queries them.
- **Query performance:** avoid implicit conversions, use properly typed bind variables, and verify indexes/partitions and execution plans on real workloads.

### Oracle References

- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — **Data Types**, **Datetime and Interval Data Types**, **SQL Conditions**, **CREATE TABLE** sections.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — character data, encoding, numeric precision, storage, and schema objects.
- [Oracle Database Globalization Support Guide](https://docs.oracle.com/en/database/) — `AL32UTF8`, byte/character semantics, collation, and NLS.
- [Oracle Database JSON Developer's Guide](https://docs.oracle.com/en/database/) — JSON types by version and `JSON_VALUE`/`JSON_TABLE` queries.
- [Oracle Database JDBC Developer's Guide](https://docs.oracle.com/en/database/) — Oracle/Java type mapping, binding, LOBs, and datetimes.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — predicates, implicit conversion, indexes, and the optimizer.

Type names, limits, SQL `BOOLEAN`/`JSON` capabilities, and temporal conversion behavior can depend on the **Oracle version, database configuration, client driver, and session settings**. When designing a schema that must operate across multiple versions, use the oldest supported version as the compatibility baseline.
