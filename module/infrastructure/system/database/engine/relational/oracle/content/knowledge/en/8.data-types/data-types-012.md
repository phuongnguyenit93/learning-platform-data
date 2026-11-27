# Explicit Conversion, Implicit Conversion, and Data Loss Errors in Oracle

In Oracle Database, every value has a **data type**: numeric (`NUMBER`), character (`VARCHAR2`), temporal (`DATE`, `TIMESTAMP`), binary data, and so on. When a Java application reads or writes data, when SQL compares two expressions of different types, or when loading data from CSV, Oracle may need to convert a value from one type to another. Some conversions are performed **explicitly** by developer intent; others occur **implicitly** under Oracle's rules.

Without noticing a conversion step, an apparently valid SQL statement can hit `ORA-01722` (*invalid number*), misread day/month order under session settings, prevent an index from being used, or store a **rounded** number silently. Worse still, not every alteration raises an error: losing fractional seconds, losing numeric precision, or shifting how an instant is represented can happen while the SQL operation succeeds.

This lesson builds a consistent model to **recognize**, **explicitly convert**, **validate before storing**, and **prevent unintended data loss** in Oracle SQL/PLSQL and JDBC applications.

## 1. Map of the Two Conversion Kinds

**Explicit conversion** occurs when the SQL statement specifies the conversion, such as `TO_NUMBER`, `TO_DATE`, `TO_TIMESTAMP`, `TO_CHAR`, or `CAST`:

~~~sql
SELECT TO_NUMBER('125.50',
                 '999D99',
                 'NLS_NUMERIC_CHARACTERS = ''.,''') AS amount
FROM dual;
~~~

**Implicit conversion** occurs when two expressions have different types and Oracle automatically picks a conversion to evaluate an expression, comparison, or assignment:

~~~sql
-- If ORDER_ID is NUMBER, literal '101' is VARCHAR2.
-- Oracle may convert '101' to NUMBER during comparison.
SELECT order_id
FROM lab_order
WHERE order_id = '101';
~~~

| Criterion | Explicit | Implicit |
|---|---|---|
| Who specifies the conversion? | The SQL/PLSQL author or application API | Oracle based on expression types/context |
| Readability of intent | Clear in the statement: `TO_DATE(..., 'YYYY-MM-DD')` | Hidden: `date_col = '2026-11-14'` |
| Format/NLS control | Can specify format model and NLS parameters | Easily depends on session settings |
| Risk when schema/data changes | Easier to control with validation | Can error, alter semantics, or hurt execution plans |
| Preferred usage | At input/output boundaries between types | Should not be relied upon for critical data or app SQL |

**Guideline:** Data should enter the system with the **right type from the start**. Use explicit conversion at ingestion boundaries, then keep values in their proper types across tables, PL/SQL variables, and JDBC parameters.

## 2. What Does Oracle Store in Common Data Types?

Before converting, understand what is *actually* stored:

| Oracle Type | Contents | What to Watch |
|---|---|---|
| `NUMBER` | Decimal number, optionally with precision/scale | Digit limits and rounding when reducing scale |
| `BINARY_FLOAT` / `BINARY_DOUBLE` | Binary floating-point number | Many decimal numbers cannot be represented with exact precision |
| `CHAR` / `VARCHAR2` | Character string | Distinguish BYTE vs. CHAR length; numeric/date values stored as text have no automatic numeric/date semantics |
| `DATE` | Year, month, day, hour, minute, second | **Includes time component**, yet has no fractional seconds and no timezone |
| `TIMESTAMP` | Date-time with fractional seconds per precision | Carries no timezone info |
| `TIMESTAMP WITH TIME ZONE` | Point in time with timezone/offset info | Requires consistent display/zone-conversion rules on integration |
| `TIMESTAMP WITH LOCAL TIME ZONE` | Normalized under Oracle mechanics and displayed in session timezone | Does not preserve the original offset verbatim as an independent string |
| `RAW`, `BLOB` | Binary bytes | Should not be converted arbitrarily into character strings |

For example, `'125.50'` is a **string**, distinct from the number `125.50`. The string `'2026-11-14'` differs from the date value `DATE '2026-11-14'`. Both strings look like valid data, yet Oracle knows their semantics only after explicit conversion under clear rules.

## 3. Essential Explicit Conversion Functions

| Function / Syntax | Typical Use | Example |
|---|---|---|
| `TO_NUMBER(text, format, nlsparam)` | String to number | `TO_NUMBER('1,234.50', '9G999D99', ...)` |
| `TO_CHAR(number, format, nlsparam)` | Number to display string | `TO_CHAR(1234.5, 'FM9G999D00', ...)` |
| `TO_DATE(text, format, nlsparam)` | String to `DATE` | `TO_DATE('2026-11-14', 'YYYY-MM-DD')` |
| `TO_TIMESTAMP(text, format)` | String to `TIMESTAMP` | `TO_TIMESTAMP('2026-11-14 08:30:12.123456', 'YYYY-MM-DD HH24:MI:SS.FF6')` |
| `TO_TIMESTAMP_TZ(text, format)` | String to timezone-aware timestamp | `TO_TIMESTAMP_TZ('2026-11-14 08:30 +07:00', 'YYYY-MM-DD HH24:MI TZH:TZM')` |
| `TO_CHAR(date_or_timestamp, format)` | Datetime to display string | `TO_CHAR(SYSDATE, 'YYYY-MM-DD HH24:MI:SS')` |
| `CAST(expr AS type)` | Casts an expression to another SQL type | `CAST(123.456 AS NUMBER(6,2))` |
| `DATE 'YYYY-MM-DD'` | ANSI DATE literal syntax | `DATE '2026-11-14'` |
| `TIMESTAMP 'YYYY-MM-DD HH24:MI:SS...'` | TIMESTAMP literal | `TIMESTAMP '2026-11-14 08:30:12.123'` |

Oracle format models matter greatly: `YYYY` is four-digit year, `MM` is numeric month, `DD` is day; `HH24` is 24-hour hour, `MI` is minute, and `SS` is second. For numbers, `D` marks the decimal separator and `G` marks the grouping separator according to NLS settings.

### 3.1. Converting Strings to Numbers

~~~sql
SELECT TO_NUMBER(
         '1,234.50',
         '9G999D99',
         'NLS_NUMERIC_CHARACTERS = ''.,'''
       ) AS amount
FROM dual;
~~~

In this example, the NLS argument specifies period as decimal point and comma as grouping separator, so `'1,234.50'` means **one thousand two hundred thirty-four point five zero**. Never use a formatless `TO_NUMBER('1,234.50')` on external input assuming every session interprets it the same way.

Converting back for **display**:

~~~sql
SELECT TO_CHAR(
         1234.5,
         'FM9G999D00',
         'NLS_NUMERIC_CHARACTERS = ''.,'''
       ) AS formatted_amount
FROM dual;
~~~

`FM` suppresses leading padding spaces common in numeric format models; `D00` displays two decimal digits per the format. The result is a **display string**; never use formatted strings with grouping separators in place of `NUMBER` for calculations or numeric sorting.

### 3.2. Converting Strings to Dates and Times

~~~sql
SELECT TO_DATE('2026-11-14', 'YYYY-MM-DD') AS order_date
FROM dual;

SELECT TO_TIMESTAMP(
         '2026-11-14 08:30:12.123456',
         'YYYY-MM-DD HH24:MI:SS.FF6'
       ) AS event_time
FROM dual;

SELECT TO_TIMESTAMP_TZ(
         '2026-11-14 08:30:12.123456 +07:00',
         'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM'
       ) AS event_time_tz
FROM dual;
~~~

These three conversions yield **three distinct types**: `DATE` (to the second), `TIMESTAMP` (fractional seconds), and `TIMESTAMP WITH TIME ZONE` (with offset/timezone). Source data from an API that includes an offset should be kept in a type and contract that preserves that information, rather than stripping `+07:00` and storing it as contextless local time.

If only a calendar date without time is needed, you can use a literal:

~~~sql
INSERT INTO lab_event (event_date)
VALUES (DATE '2026-11-14');
~~~

The literal `DATE '2026-11-14'` is independent of `NLS_DATE_FORMAT` and sets time to **00:00:00**. It fits when the field is genuinely date-only; if the event has hour/minute/second precision, store and convert using the right type.

### 3.3. Converting Numbers/DATE to Strings for Display

~~~sql
SELECT
  TO_CHAR(DATE '2026-11-14', 'DD/MM/YYYY') AS date_vi,
  TO_CHAR(
    TIMESTAMP '2026-11-14 08:30:12.123',
    'YYYY-MM-DD"T"HH24:MI:SS.FF3'
  ) AS event_text
FROM dual;
~~~

Do not convert `DATE` or `TIMESTAMP` to strings just to store them in a `VARCHAR2` column when the schema can store real temporal types. Strings are only for **data export**, reporting, or protocols requiring text.

### 3.4. Using CAST When the Target Type Is Known

~~~sql
SELECT
  CAST(123.456 AS NUMBER(6,2)) AS rounded_amount,
  CAST(TIMESTAMP '2026-11-14 08:30:12.987'
       AS DATE) AS date_without_fraction
FROM dual;
~~~

`CAST` clearly states the target type, yet **it does not replace format models** when parsing external datetime strings. For string inputs formatted as `YYYY-MM-DD`, `TO_DATE(text, 'YYYY-MM-DD')` is far cleaner than an NLS-dependent cast.

## 4. Implicit Conversion: Convenient but Unpredictable

Oracle permits implicit conversion in certain comparisons, expressions, and assignments. For example, comparing a `NUMBER` column `ORDER_ID` to a string:

~~~sql
SELECT order_id
FROM lab_order
WHERE order_id = '101';
~~~

Because the left side is numeric, Oracle can convert the string `'101'` to the number `101`. The query succeeding does not prove it is good practice; once an application sends `'101A'`, the conversion fails.

The reverse case is even more dangerous:

~~~sql
-- CUSTOMER_CODE is VARCHAR2, whereas literal 1001 is NUMBER.
SELECT customer_code
FROM lab_customer
WHERE customer_code = 1001;
~~~

When comparing a number to a string, Oracle may convert the **character column value to a number**. Rows with `'1001'` match, yet rows with `'A1001'` or `'001001X'` cannot be converted to numbers. The result can be **`ORA-01722: invalid number`**; furthermore, applying a function to the column can prevent normal index usage. Other filter conditions in the same SQL statement **are not guaranteed** to run first to exclude bad rows, because the optimizer is free to reorder predicate evaluation.

If `CUSTOMER_CODE` is a **business code**, compare against a **string**:

~~~sql
SELECT customer_code
FROM lab_customer
WHERE customer_code = '1001';
~~~

Here `'01001'` and `'1001'` are **two distinct codes**, even though their numeric values would match. Converting code strings to numbers drops leading zeros and breaks code identity.

### 4.1. Contexts Prone to Implicit Conversion

| Context | Risky Example | Proactive Pattern |
|---|---|---|
| Comparing `NUMBER` with text | `amount = '100.50'` | Bind numeric parameter or `TO_NUMBER` with format/NLS |
| Comparing `VARCHAR2` with number | `customer_code = 1001` | `customer_code = '1001'` or bind `VARCHAR2` |
| Comparing `DATE` with text | `order_date = '14/11/2026'` | `order_date = DATE '2026-11-14'` or `TO_DATE` with format |
| Assigning text to numeric column | `INSERT ... VALUES ('1,25')` | Parse/validate value first, then bind `NUMBER` |
| Mixing expression types | `CASE` or `NVL` with differing branch types | Normalize branches/arguments to the same target type |
| JDBC binding | `setString` for a `NUMBER` column | `setBigDecimal`, `setLong` per semantics |

**Note:** Oracle defines conversion rules across types and operators; not every pair converts automatically, and conversion direction depends on context. Never code on the assumption that "Oracle always converts the right side to match the left side."

### 4.2. Impact on Indexes and Execution Plans

Suppose the table has an index on `CUSTOMER_CODE VARCHAR2(32)`:

~~~sql
CREATE INDEX ix_lab_customer_code
ON lab_customer (customer_code);
~~~

Type-consistent comparison:

~~~sql
SELECT customer_id
FROM lab_customer
WHERE customer_code = :customer_code;
-- Bind :customer_code as VARCHAR2.
~~~

If the application passes a numeric parameter, the predicate can effectively become `TO_NUMBER(customer_code) = :number_value`. Converting the column to a number not only risks `ORA-01722` but can also prevent direct use of the regular index on the string column. Oracle has specialized optimizer transformations, yet **fixing the parameter type** is usually the first step.

When diagnosing, inspect predicates in the execution plan via `DBMS_XPLAN.DISPLAY_CURSOR` (when authorized and after execution), looking for conversion wrappers like `TO_NUMBER(column_name)` or `INTERNAL_FUNCTION(...)`. You cannot diagnose implicit conversion from runtime alone; read the plan and bind datatypes.

## 5. NLS: Different Sessions Can Interpret the Same String Differently

Oracle's **National Language Support (NLS)** parameters affect how numbers and dates are parsed and displayed when full format models are omitted:

~~~sql
SELECT parameter, value
FROM nls_session_parameters
WHERE parameter IN (
  'NLS_DATE_FORMAT',
  'NLS_TIMESTAMP_FORMAT',
  'NLS_DATE_LANGUAGE',
  'NLS_NUMERIC_CHARACTERS'
)
ORDER BY parameter;
~~~

### 5.1. NLS_DATE_FORMAT

A session might configure:

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY';
~~~

Then `'14/11/2026'` may parse as expected during an implicit date conversion. Yet in a session with `NLS_DATE_FORMAT = 'YYYY-MM-DD'`, the same string fails to match and errors out. Viewing `DATE` in a SQL tool may also print only the calendar date while **hiding the time component**, even though the stored value still has hour/minute/second.

Specify formats explicitly when parsing and displaying:

~~~sql
SELECT
  TO_DATE('14/11/2026', 'DD/MM/YYYY') AS parsed_date,
  TO_CHAR(
    TO_DATE('14/11/2026', 'DD/MM/YYYY'),
    'YYYY-MM-DD HH24:MI:SS'
  ) AS shown_date
FROM dual;
~~~

For strict text parsing, use the `FX` format modifier to require exact format matching:

~~~sql
SELECT TO_DATE('2026-11-14', 'FXYYYY-MM-DD')
FROM dual;
~~~

Even a strict format will not make `'2026-02-30'` valid. Date components must still represent a real calendar date.

### 5.2. NLS_DATE_LANGUAGE

If a date string contains month names:

~~~sql
SELECT TO_DATE(
         '15-MAR-2026',
         'DD-MON-YYYY',
         'NLS_DATE_LANGUAGE = American'
       ) AS parsed_date
FROM dual;
~~~

Specifying the language avoids session dependence on alphabetic month abbreviations. Whenever possible, pass numeric dates under a strict protocol or typed date/timestamp binds instead of natural-language month names.

### 5.3. NLS_NUMERIC_CHARACTERS

The same string `1,234` can mean **one thousand two hundred thirty-four** (comma grouping) or **one point two three four** (comma decimal). Never guess.

~~~sql
-- 1,234 is one thousand two hundred thirty-four.
SELECT TO_NUMBER(
  '1,234',
  '9G999',
  'NLS_NUMERIC_CHARACTERS = ''.,'''
) AS number_value
FROM dual;

-- 1,234 is one point two three four.
SELECT TO_NUMBER(
  '1,234',
  '9D999',
  'NLS_NUMERIC_CHARACTERS = '',.'''
) AS number_value
FROM dual;
~~~

In CSV imports or APIs, the **input format** must be part of the data contract. Session NLS settings cannot substitute for that contract.

## 6. Data Loss Does Not Always Raise an Error

When talking about "data loss bugs", distinguish three phenomena:

1. **Conversion fails with an error:** value cannot be stored, e.g., `ORA-01438` or `ORA-12899`.
2. **Conversion succeeds, yet the value changes:** numeric rounding or loss of fractional seconds.
3. **Conversion yields a value, yet the semantics are wrong:** swapped day/month, wrong currency scale, wrong timezone, or dropped leading zeros on a code.

Not all of these are caught automatically by SQL type checks. Many require explicit business rules.

### 6.1. Precision and Scale of NUMBER

With `NUMBER(p,s)`:

- **p (precision):** total significant digits allowed.
- **s (scale):** decimal digits retained per declaration; Oracle rounds when assigning a value with finer scale.

Example:

~~~sql
CREATE TABLE lab_amount (
  amount_id NUMBER PRIMARY KEY,
  amount    NUMBER(5,2) NOT NULL
);

INSERT INTO lab_amount (amount_id, amount)
VALUES (1, 123.456);

SELECT amount
FROM lab_amount
WHERE amount_id = 1;
~~~

The stored value becomes **123.46** because scale is 2, even though the source was **123.456**. The `INSERT` succeeds: this is **silent precision alteration without an error**. If business rules prohibit automatic rounding, the application must detect/validate scale before writing.

Conversely:

~~~sql
-- NUMBER(5,2) allows at most three digits before the decimal point.
-- 1234.56 cannot fit in NUMBER(5,2).
INSERT INTO lab_amount (amount_id, amount)
VALUES (2, 1234.56);
~~~

This statement fails because the value exceeds the column's precision/scale (typically **`ORA-01438`**). Values near the ceiling that **round up** can also increase the integer digit count and overflow the limit.

**Design decision:** For money, quantities, and rates, size `NUMBER(p,s)` from value ranges, required precision, and rounding rules. Never pick `NUMBER(5,2)` on a hunch that "it should be enough."

### 6.2. BINARY_FLOAT / BINARY_DOUBLE and Binary Error

`BINARY_FLOAT` and `BINARY_DOUBLE` use binary floating-point representation. Decimals such as `0.1` usually have no exact binary representation, so calculations can introduce rounding drift. Converting between `NUMBER` and these types can alter precision.

~~~sql
SELECT
  CAST(0.1 AS BINARY_DOUBLE) AS binary_value,
  CAST(0.1 AS NUMBER) AS decimal_value
FROM dual;
~~~

Never assume two calculations store identical values just from short display formatting. When exact decimal arithmetic such as money is required, use `NUMBER(p,s)` in Oracle and `BigDecimal` in Java, with consistent rounding rules in the business layer.

### 6.3. DATE and TIMESTAMP: Losing Fractional Seconds

Oracle `DATE` stores hour/minute/second, **but drops fractional seconds**. Casting a timestamp with fractional seconds to DATE discards sub-second precision:

~~~sql
SELECT
  TO_CHAR(
    TIMESTAMP '2026-11-14 08:30:12.987654',
    'YYYY-MM-DD HH24:MI:SS.FF6'
  ) AS original_timestamp,
  TO_CHAR(
    CAST(TIMESTAMP '2026-11-14 08:30:12.987654' AS DATE),
    'YYYY-MM-DD HH24:MI:SS'
  ) AS cast_as_date
FROM dual;
~~~

`CAST_AS_DATE` no longer has `.987654`. If event ordering requires millisecond or microsecond granularity, keep the appropriate `TIMESTAMP(p)` precision instead of converting to DATE just for prettier display.

Another pitfall is **stripping time during formatting**:

~~~sql
SELECT TO_DATE(
         TO_CHAR(
           TIMESTAMP '2026-11-14 08:30:12.987654',
           'YYYY-MM-DD'
         ),
         'YYYY-MM-DD'
       ) AS lost_time
FROM dual;
~~~

The result retains only `2026-11-14` at `00:00:00`. That is useful when intentionally extracting a calendar date, yet destructive when the original timestamp is needed.

### 6.4. Risk of Shifting Timezones or Losing Offsets

Suppose an API sends:

~~~text
2026-11-14T08:30:12.123456+07:00
~~~

This carries both time and **offset +07:00**. Taking only `'2026-11-14 08:30:12'` and assigning it to a zoneless `DATE` or `TIMESTAMP` discards the offset. Another system may interpret it as 08:30 UTC instead of 08:30 at +07:00—a **seven-hour** shift.

When zone info must be preserved, parse explicitly:

~~~sql
SELECT TO_TIMESTAMP_TZ(
  '2026-11-14 08:30:12.123456 +07:00',
  'YYYY-MM-DD HH24:MI:SS.FF6 TZH:TZM'
) AS event_instant
FROM dual;
~~~

When converting to UTC or another timezone, use Oracle-supported datetime/timezone features and consistent conventions. `TIMESTAMP WITH LOCAL TIME ZONE` normalizes and displays per session timezone; it does not preserve the original input offset string verbatim.

### 6.5. VARCHAR2: BYTE Differs from CHAR

Unicode character count and **byte** count are not always equal. Under database character set `AL32UTF8`, the three characters `'ááá'` occupy **six bytes**:

~~~sql
SELECT
  LENGTH('ááá')  AS char_count,
  LENGTHB('ááá') AS byte_count
FROM dual;
~~~

If a column uses `VARCHAR2(5 BYTE)`, this string exceeds the byte limit despite having only three characters, raising **`ORA-12899`** on insert. With `VARCHAR2(5 CHAR)`, the three-character string fits within Oracle's character limit and maximum byte ceiling.

~~~sql
CREATE TABLE lab_text_limit (
  id        NUMBER PRIMARY KEY,
  text_byte VARCHAR2(5 BYTE),
  text_char VARCHAR2(5 CHAR)
);

-- In AL32UTF8, this 3-character value can occupy 6 bytes,
-- exceeding TEXT_BYTE's limit.
INSERT INTO lab_text_limit (id, text_byte)
VALUES (1, 'ááá');

-- TEXT_CHAR allows up to 5 characters, provided
-- it does not exceed Oracle's maximum byte limit.
INSERT INTO lab_text_limit (id, text_char)
VALUES (2, 'ááá');
~~~

For Vietnamese names, descriptions, or multilingual text, align character set and length semantics when designing schemas. Never slice strings by byte count when the requirement specifies visible character limits.

### 6.6. Identifiers Are Not Arithmetic Numbers

Codes like `'000123'`, postal codes, or account numbers may consist solely of digits yet are **character identifiers** by business meaning. Converting `'000123'` to `NUMBER` strips leading zeros. Converting back with `TO_CHAR(123)` cannot know how long the original code was unless an explicit formatting rule is stored.

Choose types by **semantics**: do you perform addition/subtraction/multiplication/division, or only equality matching and identification? Many digit strings belong in `VARCHAR2`.

## 7. Common Conversion Errors and Their Meanings

| Error Code / Symptom | Common Cause | Example / Resolution |
|---|---|---|
| **`ORA-01722: invalid number`** | String cannot convert to a number during comparison/assignment/cast | Do not compare `VARCHAR2` code columns to NUMBER; validate text before `TO_NUMBER` |
| **`ORA-01861: literal does not match format string`** | Datetime string does not match format model | Use `TO_DATE(text, 'YYYY-MM-DD')` matching input's actual format |
| **`ORA-01843: not a valid month`** | Invalid month token or wrong format order | Check day/month order and NLS date language |
| **`ORA-01830: date format picture ends before converting entire input string`** | Format model does not cover the entire input string | Add matching hour/second/offset elements |
| **`ORA-01438: value larger than specified precision`** | Numeric value exceeds `NUMBER(p,s)` column precision | Choose adequate precision and validate inputs |
| **`ORA-12899: value too large for column`** | String exceeds column BYTE/CHAR size | Check `LENGTH`/`LENGTHB` and length semantics |
| **`ORA-06502: PL/SQL numeric or value error`** | Assigning/converting into an undersized PL/SQL variable or value error | Inspect target variable, record type, and conversion |
| **No error, yet data changed** | Rounding, dropped fractional seconds, lost offset, stripped leading zeros | Compare types and values before/after at ingestion boundaries |

Not every Oracle version or SQL statement raises the exact same error code for bad data: errors depend on the statement, where conversion happens, and the target type. What matters is identifying **which value is converting, from which type to which type, and under which format/NLS settings**.

### Why Can Adding a Filter Still Raise ORA-01722?

Suppose `RAW_AMOUNT` is a string column containing both `'100.00'` and `'UNKNOWN'`:

~~~sql
-- Unsafe to assume the first condition
-- is always evaluated before the second.
SELECT raw_amount
FROM lab_raw_payment
WHERE REGEXP_LIKE(raw_amount, '^[0-9]+(\.[0-9]+)?$')
  AND TO_NUMBER(raw_amount) > 50;
~~~

The optimizer can rewrite and reorder predicate evaluation; never rely on `AND` order to guarantee casting runs only after filtering. Moreover, that regex does not cover precision limits, negative signs, grouping separators, or NLS formats. Use Oracle's **safe validation/conversion** features or clean data during ingestion.

## 8. Validating Data Before Conversion with VALIDATE_CONVERSION

Modern Oracle releases (12.2+, for supported conversions) provide `VALIDATE_CONVERSION`. It returns whether an expression can convert to the target type under a specified format, instead of failing the entire query on the first bad row.

### 8.1. Staging Table Holding Raw Data

When loading from CSV or external feeds, land raw strings in a **staging** table before converting to business types:

~~~sql
CREATE TABLE lab_raw_payment (
  row_id        NUMBER PRIMARY KEY,
  raw_amount    VARCHAR2(60),
  raw_date      VARCHAR2(60)
);

INSERT INTO lab_raw_payment VALUES
  (1, '125.50', '2026-11-14');

INSERT INTO lab_raw_payment VALUES
  (2, 'UNKNOWN', '2026-11-14');

INSERT INTO lab_raw_payment VALUES
  (3, '90.00', '2026-02-30');

INSERT INTO lab_raw_payment VALUES
  (4, '1,200.50', '14/11/2026');

COMMIT;
~~~

This illustrates real-world data: row 1 fits the expected format, row 2 has a bad number, row 3 has an invalid calendar date, and row 4 uses **another format**. Do not call row 4 "garbage"; it may be valid under **a different contract**. Agree on canonical formats before automating conversions.

### 8.2. Detecting Format Mismatches

Suppose the input contract requires numbers like `125.50` (period decimal, no grouping) and dates formatted as `YYYY-MM-DD`:

~~~sql
SELECT
  row_id,
  raw_amount,
  raw_date,
  VALIDATE_CONVERSION(
    raw_amount AS NUMBER,
    '9999999D99',
    'NLS_NUMERIC_CHARACTERS = ''.,'''
  ) AS amount_valid,
  VALIDATE_CONVERSION(
    raw_date AS DATE,
    'FXYYYY-MM-DD'
  ) AS date_valid
FROM lab_raw_payment
ORDER BY row_id;
~~~

`AMOUNT_VALID` and `DATE_VALID` classify which rows Oracle can parse under the chosen format. When `NULL` values appear, enforce business nullability rules separately; passing conversion validation does not guarantee the value satisfies **`NOT NULL`** or business range rules.

### 8.3. DEFAULT ... ON CONVERSION ERROR

In supported releases (Oracle 12.2+), `TO_NUMBER`, `TO_DATE`, and related conversion functions support **`DEFAULT ... ON CONVERSION ERROR`**:

~~~sql
SELECT
  row_id,
  TO_NUMBER(
    raw_amount DEFAULT NULL ON CONVERSION ERROR,
    '9999999D99',
    'NLS_NUMERIC_CHARACTERS = ''.,'''
  ) AS amount_number,
  TO_DATE(
    raw_date DEFAULT NULL ON CONVERSION ERROR,
    'FXYYYY-MM-DD'
  ) AS payment_date
FROM lab_raw_payment
ORDER BY row_id;
~~~

Unparseable values turn into `NULL` **by explicit choice of the SQL author** instead of aborting the query. However, `NULL` can now mean either missing input or **malformed input**; never silently load those `NULL`s into production business tables. Keep raw columns, validation flags, and error reasons in staging to fix data or report back to the source system.

Note: `DEFAULT ... ON CONVERSION ERROR` catches errors only within the **conversion step** supported by the function; errors while evaluating input expressions or subsequent constraint violations can still occur.

### 8.4. Loading Into a Typed Table After Validation

Example properly typed target table:

~~~sql
CREATE TABLE lab_payment (
  payment_id   NUMBER PRIMARY KEY,
  amount       NUMBER(12,2) NOT NULL,
  payment_date DATE NOT NULL
);
~~~

Insert only rows satisfying accepted **formats and values**:

~~~sql
INSERT INTO lab_payment (payment_id, amount, payment_date)
SELECT
  row_id,
  TO_NUMBER(
    raw_amount,
    '9999999D99',
    'NLS_NUMERIC_CHARACTERS = ''.,'''
  ),
  TO_DATE(raw_date, 'FXYYYY-MM-DD')
FROM lab_raw_payment
WHERE raw_amount IS NOT NULL
  AND raw_date IS NOT NULL
  AND VALIDATE_CONVERSION(
        raw_amount AS NUMBER,
        '9999999D99',
        'NLS_NUMERIC_CHARACTERS = ''.,'''
      ) = 1
  AND VALIDATE_CONVERSION(raw_date AS DATE, 'FXYYYY-MM-DD') = 1;
~~~

In production pipelines, an even safer pattern builds **safe** conversion expressions in staging, then selects valid rows with range, business-constraint, and precision checks before inserting. Never rely on predicate evaluation order as a data guard. Here `VALIDATE_CONVERSION` filters by format, yet you must still evaluate the target `NUMBER(12,2)` type: a string parseable as NUMBER can still round or overflow precision on write.

### 8.5. If an Older Oracle Release Lacks VALIDATE_CONVERSION

Never replace `VALIDATE_CONVERSION` with a naive regex and assume all numbers/dates are validated. Alternatives include parsing in the application/ETL layer with strict parsers and routing failures to a reject table, or writing a PL/SQL conversion function with **exception handling** per row returning an error status instead of aborting the batch. Weigh performance and context-switch overhead on large datasets.

## 9. Catching Precision Loss Before Saving

It is not enough that a conversion **throws no exception**. For critical data, compare **values before and after**.

### 9.1. Detecting Numbers That Would Be Rounded

Given a parsed `NUMBER`, if the target column is `NUMBER(12,2)` and business rules **forbid** any digits past the second decimal place:

~~~sql
SELECT
  123.456 AS source_amount,
  ROUND(123.456, 2) AS rounded_amount
FROM dual;

-- 123.456 <> ROUND(123.456, 2) so the source value would be altered.
SELECT CASE
         WHEN 123.456 = ROUND(123.456, 2)
         THEN 'EXACT'
         ELSE 'WOULD_ROUND'
       END AS precision_check
FROM dual;
~~~

In real ingestion pipelines, evaluate this predicate on the safely parsed `NUMBER`. If business rules **allow** rounding, explicitly define the rounding mode and stage. For money, rounding per line before summing often differs from summing first and rounding the total.

### 9.2. Detecting Lost Time Components

Before converting `TIMESTAMP` to `DATE`, confirm requirements:

- If only date or second-level time is needed, dropping fractional seconds may be intentional.
- If transactions must be ordered to microsecond precision, keep `TIMESTAMP(p)`.
- If data arrives across multiple timezones, preserve offset/instant metadata in the matching type or contract.

Do not round-trip through `TO_CHAR` and `TO_DATE` just to "strip the timezone" without justification. A UI display format change **does not require** downgrading the stored data type.

### 9.3. Controlling Character Length

~~~sql
SELECT
  LENGTH('ááá') AS length_chars,
  LENGTHB('ááá') AS length_bytes
FROM dual;
~~~

When the target is `VARCHAR2(n BYTE)`, verify byte length in the database character set; when the target is `VARCHAR2(n CHAR)`, verify character count while still respecting Oracle's byte limits. Never use `SUBSTR`/`SUBSTRB` to truncate person names or key codes unless explicitly permitted by business rules.

## 10. JDBC: Bind the Right Types Instead of Sending Everything as Strings

Java applications often receive text inputs from HTTP/JSON/CSV, yet **should not send every value to Oracle via `PreparedStatement.setString()`** expecting the database to guess types.

Example saving an invoice:

~~~sql
CREATE TABLE lab_invoice (
  invoice_id NUMBER PRIMARY KEY,
  amount     NUMBER(12,2) NOT NULL,
  issued_at  TIMESTAMP(6) NOT NULL
);
~~~

Java parses/validates input per contract and binds proper types:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.Timestamp;
import java.time.LocalDateTime;

String sql = """
    INSERT INTO lab_invoice (invoice_id, amount, issued_at)
    VALUES (?, ?, ?)
    """;

// These values must already be validated against the input contract.
long invoiceId = 1001L;
BigDecimal amount = new BigDecimal("125.50");
LocalDateTime issuedAt =
    LocalDateTime.of(2026, 11, 14, 8, 30, 12, 123456000);

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, invoiceId);                      // NUMBER
    ps.setBigDecimal(2, amount);                   // NUMBER(12,2)
    ps.setTimestamp(3, Timestamp.valueOf(issuedAt)); // TIMESTAMP
    ps.executeUpdate();
}
~~~

This example illustrates mapping a zoneless `TIMESTAMP`. If the API supplies instants with offsets, use a temporal model and driver supporting `TIMESTAMP WITH TIME ZONE` (such as `OffsetDateTime` on supported JDBC/Oracle versions) and define timezone conversion rules explicitly.

### 10.1. Common Mistakes in the Java Layer

| Pattern | Risk | Better Approach |
|---|---|---|
| `setString(1, "125,50")` for NUMBER column | Implicit NLS-dependent parsing | Parse per contract into `BigDecimal`, then `setBigDecimal` |
| `setString(1, "14/11/2026")` for DATE | Session format may not match | Parse in application, then bind appropriate date/timestamp |
| `new BigDecimal(0.1)` | Inherits `double` representation error | `new BigDecimal("0.1")` or `BigDecimal.valueOf` as appropriate |
| `setDouble` for money | Floating-point and precision error | `setBigDecimal` + business precision/scale |
| Storing account numbers via `setLong` | Strips leading zeros, numeric range limits | `VARCHAR2` column and `setString` |
| Using `java.sql.Date` for datetimes with time | Can drop time component via date mapping | `Timestamp` or timezone-aware temporal type |

Typed binds reduce NLS dependence, yet you must still validate **precision/scale**, **date ranges**, **nullability**, and database constraints. Bind variables protect against SQL injection; they do not guarantee business validity.

### 10.2. Reading Data Back Into Java

For `NUMBER(12,2)`, typically read with `ResultSet.getBigDecimal()`; for `TIMESTAMP`, read with `getTimestamp()` and map to the matching `java.time` type. Avoid `getDouble()` when monetary exactness is required. For `DATE`, remember Oracle DATE includes time: reading only into `LocalDate` can discard the time component.

At the JSON API layer, when numeric fields represent money or high-precision values, establish an explicit serialization contract; do not assume JavaScript clients retain every significant digit of an Oracle NUMBER when parsed as floating-point `Number`.

## 11. Practice Exercises by Error Type

Run these examples in a practice PDB schema; use `LAB_` tables to avoid touching business data. Some statements **intentionally fail** to demonstrate Oracle behavior, so run each statement individually and note the message.

### Exercise 1 — DATE Literal vs. String

~~~sql
SELECT
  TO_CHAR(DATE '2026-11-14', 'YYYY-MM-DD HH24:MI:SS')
    AS typed_date,
  TO_CHAR(
    TO_DATE('14/11/2026', 'DD/MM/YYYY'),
    'YYYY-MM-DD'
  ) AS parsed_date
FROM dual;
~~~

**Question:** Why does `DATE '2026-11-14'` depend less on session NLS than comparing a DATE column directly to `'14/11/2026'`?

**Hint:** A DATE literal and formatted `TO_DATE` make type/format explicit, whereas a bare string lacks DATE type and relies on session configuration when Oracle converts implicitly.

### Exercise 2 — Digits That Are Actually Codes

~~~sql
SELECT
  '000123' AS original_code,
  TO_NUMBER('000123') AS converted_number
FROM dual;
~~~

**Question:** Why should a customer code or postal code `000123` never be stored in a NUMBER column if the six-character string must be preserved intact?

**Hint:** Numeric values carry no memory of leading zeros. Only an explicit code format contract could reconstruct the length.

### Exercise 3 — Rounding and Precision Overflow

~~~sql
CREATE TABLE lab_precision (
  id NUMBER PRIMARY KEY,
  amount NUMBER(5,2)
);

INSERT INTO lab_precision VALUES (1, 123.456);
SELECT id, amount FROM lab_precision;

-- The next statement intentionally exceeds NUMBER(5,2) range.
INSERT INTO lab_precision VALUES (2, 1234.56);
~~~

**Question:** Why does row 1 store 123.46 while row 2 errors? If the application must keep 123.456 exact, what design or rule must change?

### Exercise 4 — Mixed-Format Input Data

Create `LAB_RAW_PAYMENT` from Section 8 and use `VALIDATE_CONVERSION` to find rows that do not match numeric format `9999999D99` and date format `FXYYYY-MM-DD`.

**Question:** Is `'1,200.50'` invalid in every context? Why shouldn't the system guess formats row-by-row without explicit source metadata and policy?

**Hint:** It can be valid under a grouping-separator format; inputs need a consistent contract or explicit source/locale metadata.

### Exercise 5 — Losing Fractional Seconds

~~~sql
SELECT
  TO_CHAR(
    TIMESTAMP '2026-11-14 08:30:12.123456',
    'HH24:MI:SS.FF6'
  ) AS source_time,
  TO_CHAR(
    CAST(TIMESTAMP '2026-11-14 08:30:12.123456' AS DATE),
    'HH24:MI:SS'
  ) AS target_time
FROM dual;
~~~

**Question:** If this timestamp belongs to a financial transaction, why does converting `TIMESTAMP → DATE` lose the ability to order two events occurring within the same second?

### Exercise 6 — Bind Type Causing Implicit Conversion

A table has `CUSTOMER_CODE VARCHAR2(12)` containing `'000123'` and `'A123'`. Two Java snippets:

~~~java
ps.setLong(1, 123L);
// Compared with WHERE customer_code = ?

ps.setString(1, "000123");
// Also WHERE customer_code = ?
~~~

**Question:** Which call preserves identifier semantics? Which can cause Oracle to convert the column to a number and fail on `'A123'`?

**Answer key:** `setString` with the original code string is right; `setLong` drops leading zeros and can trigger semantically wrong implicit conversion.

## 12. Decision Flowchart for Conversions

~~~text
Value arrives from Java / JSON / CSV / SQL?
                  |
                  v
Identify true SEMANTICS
  - Identifier code or arithmetic number?
  - Calendar date or datetime with time?
  - Timezone/offset present?
  - Currency unit and precision?
                  |
                  v
Define target type and format convention
  - NUMBER(p,s), VARCHAR2(n CHAR/BYTE)
  - DATE, TIMESTAMP(p), TIMESTAMP WITH TIME ZONE
                  |
                  v
Validate source data
  - Parseable under specified format and NLS?
  - Within valid domain/range?
  - Does conversion round or drop time/characters?
                  |
           +------+------+
           |             |
         Fails         Passes
           |             |
           v             v
   Keep raw + reason  Explicit conversion / typed bind
   report error or    and store in properly typed column
   route to reject       |
                         v
                   Verify constraints and
                   persisted values
~~~

**Practical rule:** Prefer **typed binds** and **explicit conversion with clear format models** at data boundaries; treat implicit conversion as a suspect whenever SQL fails or runs slowly. For precision-loss scenarios, ask not only "can it convert?" but also **"does the converted value still preserve the original meaning and precision?"**. That is the difference between a SQL query that merely runs and a data platform you can trust.
