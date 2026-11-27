# Formatting, Type Conversion, and Data Analysis Functions in PostgreSQL

An order-management system typically performs three consecutive tasks: **reading data in the right types**, **computing/aggregating over meaningful values**, and **formatting results for display or report export**. For example, money should be stored as `numeric` for accurate summation, order timestamps should use `timestamptz` when representing real instants, while the UI may need formatted strings like `125,000.50` and dates like `10/02/2026`.

PostgreSQL offers a wide array of functions and expressions for these needs:

- **Formatting:** `to_char`, `format`, `concat_ws`, `lpad`, and string functions.
- **Type conversion:** `CAST(... AS ...)`, the `::` operator, `to_date`, `to_timestamp`, `to_number`, `pg_typeof`.
- **Temporal and JSON handling:** `date_trunc`, `extract`, `AT TIME ZONE`, `jsonb_build_object`, `->`, and `->>`.
- **Data analysis:** `COUNT`, `SUM`, `AVG`, `FILTER`, `PERCENTILE_CONT`, `STDDEV_SAMP`, and window functions such as `ROW_NUMBER`, `LAG`, and `LEAD`.

These tools work closely together, yet **they are not interchangeable**. `to_char` produces **strings for display**, not a way to store money; `CAST` changes a **value's data type**; and window functions compute analytics while keeping every input row.

This lesson uses modern PostgreSQL with self-contained SQL examples, highlighting common pitfalls around `NULL`, time zones, locale-dependent number formatting, malformed input, and numeric precision. The end includes practice exercises, solutions, and a function-selection guide.

## 1. Distinguishing Value, Data Type, and Representation

Consider three expressions:

~~~sql
SELECT
    125000.50::numeric(12, 2) AS money_value,
    '125000.50'::text AS money_text,
    to_char(125000.50::numeric, 'FM999,999,990.00')
        AS formatted_money;
~~~

They may look similar in a SQL client, yet they differ fundamentally:

| Expression | Type / Meaning | Best Suited For |
| --- | --- | --- |
| `125000.50::numeric(12,2)` | Exact decimal with precision/scale | Storing, comparing, arithmetic, pricing |
| `'125000.50'::text` | Character string | Raw input, labels, documents |
| `to_char(..., 'FM999,999,990.00')` | Formatted string | Displaying grouped numbers, exporting reports |

Sorting formatted money strings alphabetically can differ from numeric sorting. For instance, `'900'` sorts after `'1000'` lexicographically, even though 900 is smaller than 1000.

**Rule:** store values in types matching business semantics, compute with type-appropriate operations, and format only at the display or export boundary.

### 1.1. Functions and Operators Do Not Always Return the Input Type

~~~sql
SELECT
    pg_typeof(125000.50::numeric) AS input_type,
    pg_typeof(to_char(125000.50::numeric, 'FM999999.00'))
        AS output_type,
    pg_typeof('2026-02-10'::date) AS date_type;
~~~

`pg_typeof(expression)` tells you **which type PostgreSQL assigns to an expression**. Use it whenever you are unsure whether the result of an operation, cast, or function is `text`, `numeric`, `date`, or `timestamptz`.

## 2. Preparing the Practice Dataset

The examples below are for a **practice PostgreSQL database**; do not run this DDL on a system holding data you need to preserve.

### 2.1. Creating Schema and Tables

~~~sql
CREATE SCHEMA expr_lab;

CREATE TABLE expr_lab.customers (
    customer_id integer PRIMARY KEY,
    full_name text NOT NULL,
    email text NOT NULL UNIQUE,
    signup_at timestamptz NOT NULL
);

CREATE TABLE expr_lab.orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES expr_lab.customers(customer_id),
    ordered_at timestamptz NOT NULL,
    status text NOT NULL CHECK (
        status IN ('paid', 'pending', 'cancelled', 'refunded')
    ),
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0),
    channel text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
~~~

Type choices:

- `integer` for small lab IDs; high-growth systems may require `bigint` or another ID strategy.
- `timestamptz` stores **absolute instants**; choose the corresponding time zone on display.
- `numeric(12,2)` for decimal money calculations, avoiding `float` when binary floating-point error must be avoided in basic financial math.
- `metadata jsonb` holds extra fields that vary per order; frequently queried attributes such as `status` and `channel` remain explicit columns.

### 2.2. Inserting Customers

~~~sql
INSERT INTO expr_lab.customers (
    customer_id, full_name, email, signup_at
) VALUES
    (1, 'Lan Nguyen', 'Lan@Example.test',
        '2026-01-05 08:00:00+07'),
    (2, 'Minh Tran', 'minh@example.test',
        '2026-01-08 10:00:00+07'),
    (3, 'An Le', 'an@example.test',
        '2026-01-10 09:00:00+07'),
    (4, 'Chi Pham', 'chi@example.test',
        '2026-02-01 14:00:00+07');
~~~

Customer Chi has no orders yet, illustrating empty groups in analytics.

### 2.3. Inserting Nine Orders

~~~sql
INSERT INTO expr_lab.orders (
    order_id, customer_id, ordered_at, status,
    amount, channel, metadata
) VALUES
    (1001, 1, '2026-01-10 10:15:00+07', 'paid',
        125000.50, 'web',
        '{"promo":"TET","risk_score":4,"labels":["gift","new"]}'),
    (1002, 1, '2026-01-12 14:00:00+07', 'pending',
        80000.00, 'web',
        '{"risk_score":2,"labels":["review"]}'),
    (1003, 2, '2026-01-13 09:00:00+07', 'paid',
        90000.00, 'store',
        '{"promo":"NONE","risk_score":1,"labels":[]}'),
    (1004, 3, '2026-01-14 11:20:00+07', 'paid',
        250000.00, 'partner',
        '{"promo":"TET","risk_score":5,"labels":["vip"]}'),
    (1005, 2, '2026-02-02 16:40:00+07', 'cancelled',
        50000.00, 'web',
        '{"labels":["cancel_request"]}'),
    (1006, 1, '2026-02-04 08:05:00+07', 'paid',
        140000.00, 'web',
        '{"risk_score":2,"labels":["vip"]}'),
    (1007, 3, '2026-02-08 19:00:00+07', 'refunded',
        100000.00, 'partner',
        '{"promo":"NONE","labels":["refund"]}'),
    (1008, 2, '2026-02-10 12:10:00+07', 'paid',
        65000.00, 'store',
        '{"risk_score":3,"labels":[]}'),
    (1009, 3, '2026-02-11 17:30:00+07', 'paid',
        200000.00, 'web',
        '{"risk_score":4,"labels":["gift","vip"]}');
~~~

Quick check:

~~~sql
SELECT status, COUNT(*) AS order_count
FROM expr_lab.orders
GROUP BY status
ORDER BY status;
~~~

Expected result: **6 paid, 1 pending, 1 cancelled, 1 refunded**; 9 orders total. The total `amount` of **orders currently in paid status** is **870000.50**. This figure in the lab is simply the sum of order amounts by status, not how a real accounting system defines net revenue.

## 3. Type Conversion with CAST and ::

PostgreSQL supports two common casting syntaxes:

~~~sql
CAST(expression AS target_type)
~~~

and:

~~~sql
expression::target_type
~~~

Example:

~~~sql
SELECT
    CAST('123' AS integer) AS a,
    '123'::integer AS b,
    '2026-02-10'::date AS d,
    'true'::boolean AS flag,
    '125000.50'::numeric(12, 2) AS amount;
~~~

`CAST` is standard SQL syntax, while `::` is idiomatic PostgreSQL shorthand. Both require a **valid conversion** between source and target types.

### 3.1. String Literals vs. Typed Expressions

~~~sql
SELECT '42'::integer;
~~~

Here `'42'` is an untyped string literal until PostgreSQL resolves the expression, making the cast to integer straightforward.

In prepared statements or already-typed `text` expressions, casting rules can differ; not every conversion from `text` to enum, number, or date happens implicitly.

### 3.2. Casts Can Fail

~~~sql
-- Intentionally triggers an error:
SELECT '12x'::integer;

-- Intentionally triggers an error:
SELECT 'not-a-date'::date;

-- Intentionally triggers an error because value exceeds integer range:
SELECT '9999999999999999999'::integer;
~~~

If run inside a transaction, a PostgreSQL error puts the transaction into an *aborted* state. Use `ROLLBACK` or roll back to an appropriate savepoint before continuing.

### 3.3. Casting Does Not Always Mean Truncating Fractions

~~~sql
SELECT
    123.456::numeric(10, 2) AS rounded_to_scale,
    trunc(123.456::numeric, 2) AS truncated_to_scale,
    round(123.456::numeric, 2) AS explicit_round;
~~~

Expected result:

| Expression | Value |
| --- | ---: |
| `123.456::numeric(10,2)` | 123.46 |
| `trunc(123.456::numeric,2)` | 123.45 |
| `round(123.456::numeric,2)` | 123.46 |

`numeric(precision, scale)` constrains **precision and fractional digits**; when casting to a smaller scale, PostgreSQL rounds. If business rules require **truncation**, call `trunc` explicitly. Never assume casting to `integer` always behaves like `trunc`; understand conversion and rounding rules for each source/target pair.

## 4. Safely Converting Raw Input Strings

In CSV imports or legacy API feeds, inputs can contain spaces, empty strings, or invalid values:

~~~text
'1250.50'
' 900.00 '
''
'N/A'
'15x'
NULL
~~~

Running `raw_value::numeric` directly on all rows causes the **entire query to fail** upon hitting a single invalid value.

### 4.1. Using BTRIM, NULLIF, and CASE

~~~sql
WITH raw_input(raw_value) AS (
    VALUES
        ('1250.50'::text),
        (' 900.00 '::text),
        (''::text),
        ('N/A'::text),
        ('15x'::text),
        (NULL::text)
),
normalized AS (
    SELECT raw_value, NULLIF(btrim(raw_value), '') AS cleaned
    FROM raw_input
)
SELECT
    raw_value,
    cleaned,
    CASE
        WHEN cleaned ~ '^[0-9]+([.][0-9]{1,2})?$'
        THEN cleaned::numeric(12, 2)
        ELSE NULL
    END AS parsed_amount
FROM normalized;
~~~

How to read it:

1. `btrim` strips leading/trailing spaces under default rules.
2. `NULLIF(cleaned, '')` converts empty strings to SQL `NULL`.
3. The regular expression checks a **simple non-negative decimal format** with at most two digits after the dot.
4. Only values matching the pattern are cast to `numeric`; invalid ones yield `NULL` for separate handling.

### Important Limitation

The regex above describes **format only**; it does not guarantee the value fits within `numeric(12,2)`. A very long digit string can still overflow when cast. For a resilient import pipeline, also check length/range, define error policies, and retain source values for traceability.

In production systems, never silently convert every bad input to null and drop it: you may need a `parse_error` column, an import-errors table, or a rejection step.

### 4.2. NULLIF Is Not COALESCE

~~~sql
SELECT
    NULLIF('', '') AS empty_to_null,
    COALESCE(NULL::text, 'unknown') AS null_to_default;
~~~

- `NULLIF(a,b)` returns null when `a=b`; handy for turning placeholders like empty strings into null.
- `COALESCE(a,b,...)` returns the **first non-null** argument; handy for substituting defaults.

For financial data, "unknown amount" differs from "amount equals 0." `COALESCE(parsed_amount, 0)` is only valid if business rules explicitly allow treating missing values as 0.

## 5. Number Formatting Function: TO_CHAR

`to_char` converts a number or temporal value into **text formatted by a template**.

Numeric example:

~~~sql
SELECT
    amount,
    to_char(amount, 'FM999,999,990.00') AS amount_display
FROM expr_lab.orders
WHERE order_id = 1001;
~~~

The numeric value `125000.50` is rendered with grouping commas and two decimal places, e.g., `125,000.50`, per the chosen format mask.

### 5.1. Common Numeric Format Patterns

| Symbol | Meaning | Notes |
| --- | --- | --- |
| `9` | Digit position, padded with space if unused | Depends on template width |
| `0` | Digit position forcing leading/trailing 0s | Useful to keep fixed decimal digits |
| `.` | Literal decimal point in template | Can differ from locale `D` |
| `,` | Literal grouping comma in template | Can differ from locale `G` |
| `D` | Locale-specific decimal separator | Depends on `lc_numeric` |
| `G` | Locale-specific group separator | Depends on `lc_numeric` |
| `FM` | Fill mode, suppresses padding spaces/leading zeroes per pattern rules | Prefix before template |
| `S` | Sign indicator per pattern | Not all currency formats match |

Example:

~~~sql
SELECT
    to_char(125000.50::numeric, 'FM999,999,990.00')
        AS fixed_separator,
    to_char(125000.50::numeric, 'FM999G999G990D00')
        AS locale_separator,
    to_char(-1250.50::numeric, 'FM999,990.00')
        AS negative_number;
~~~

`D` and `G` use locale decimal/grouping characters; output depends on PostgreSQL's locale settings. When exporting across countries, standardize **locale and formatting contracts**, rather than picking patterns by habit.

### 5.2. Do Not Store TO_CHAR Output in Place of Numeric Columns

Avoid designing money tables with:

~~~sql
amount_display text
~~~

as the **sole source of monetary amounts** if the application needs arithmetic. Strings with grouping separators are hard to parse, locale-sensitive, and sort poorly.

Store `amount numeric`, and generate `amount_display` in queries or the presentation layer.

### 5.3. To_char Discards Type Information

~~~sql
SELECT
    pg_typeof(amount) AS stored_type,
    pg_typeof(to_char(amount, 'FM9999990.00')) AS display_type
FROM expr_lab.orders
WHERE order_id = 1001;
~~~

The formatted expression has type `text`. For further summing or price comparisons, use the underlying `amount`, not the formatted string.

## 6. TO_NUMBER: Parsing Formatted Numeric Strings

PostgreSQL provides `to_number(text, template)` to parse formatted text into `numeric`:

~~~sql
SELECT
    to_number('1,250.50', '9,999.99') AS parsed_amount;
~~~

When using `to_number`, the template must match **how the input string is formatted**. Patterns with grouping separators, decimal marks, negative signs, or different locales require matching conventions.

### Difference Between ::numeric and to_number

~~~sql
SELECT '1250.50'::numeric AS simple_cast;
~~~

fits standard decimal strings without extra formatting characters.

Meanwhile:

~~~sql
SELECT to_number('1,250.50', '9,999.99') AS formatted_input;
~~~

parses strings containing grouping commas per the template.

**Warning:** `to_number` is a template parser, not a universal business validator for arbitrary input. In CSVs across locales, a comma can be a thousands separator in one country and a decimal separator in another. Confirm and validate the source format before parsing; never guess locale from a single value.

## 7. Formatting Date/Time with TO_CHAR

A `timestamptz` instant should be stored as a timestamp, not a `dd/mm/yyyy` string. When reporting in local time, format explicitly:

~~~sql
SELECT
    order_id,
    ordered_at,
    to_char(
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh',
        'DD/MM/YYYY HH24:MI:SS'
    ) AS order_time_vietnam
FROM expr_lab.orders
WHERE order_id = 1001;
~~~

For instance, order 1001 renders as `10/01/2026 10:15:00` in `Asia/Ho_Chi_Minh`.

### 7.1. Common Date/Time Patterns

| Pattern | Meaning |
| --- | --- |
| `YYYY` | Four-digit year |
| `MM` | Numeric month |
| `DD` | Day of month |
| `HH24` | 24-hour clock hour |
| `MI` | Minute |
| `SS` | Second |
| `MS` | Millisecond per template |
| `Mon` / `Month` | Abbreviated / full month name |
| `Dy` / `Day` | Day-of-week name |
| `FM` | Suppresses pattern padding |

Example:

~~~sql
SELECT
    to_char(
        DATE '2026-02-10',
        'YYYY-MM-DD'
    ) AS iso_like_date,
    to_char(
        DATE '2026-02-10',
        'DD/MM/YYYY'
    ) AS vietnam_date,
    to_char(
        TIMESTAMP '2026-02-10 12:10:05',
        'HH24:MI:SS'
    ) AS time_only;
~~~

### 7.2. Month Names and lc_time

Month and day names can vary with locale/`lc_time` settings. If building APIs that must behave consistently across environments, return typed temporal values or ISO 8601 strings with explicit offsets/contracts rather than relying on PostgreSQL's localized month names.

### 7.3. TO_CHAR Does Not Mutate the Column Value

~~~sql
SELECT
    pg_typeof(ordered_at),
    pg_typeof(
        to_char(ordered_at, 'YYYY-MM-DD HH24:MI')
    )
FROM expr_lab.orders
WHERE order_id = 1001;
~~~

`to_char` returns `text`. It does not convert the stored `ordered_at` column into `timestamp` or alter stored time zones.

## 8. TO_DATE, TO_TIMESTAMP, and Parsing Temporal Strings

PostgreSQL offers several ways to parse temporal strings:

~~~sql
SELECT
    '2026-02-10'::date AS cast_date,
    to_date('10/02/2026', 'DD/MM/YYYY') AS parsed_date,
    to_timestamp(
        '2026-02-10 12:10:05',
        'YYYY-MM-DD HH24:MI:SS'
    ) AS parsed_timestamp;
~~~

### 8.1. Distinguishing the Three Return Types

| Expression | Return Type |
| --- | --- |
| `'2026-02-10'::date` | `date` |
| `to_date(text, template)` | `date` |
| `to_timestamp(text, template)` | `timestamp with time zone` / `timestamptz` |

With `to_timestamp(text, template)`, if the input string lacks explicit time zone info, PostgreSQL interprets it using the session environment. **Align the source time zone**, especially when services in multiple regions send timestamps.

### 8.2. TO_TIMESTAMP with Epoch Seconds Is a Different Overload

~~~sql
SELECT to_timestamp(1700000000::double precision)
       AS timestamp_from_epoch_seconds;
~~~

This overload takes **Unix epoch seconds**, not text+template. Do not confuse:

~~~sql
to_timestamp(double precision)
~~~

with:

~~~sql
to_timestamp(text, text)
~~~

When epoch inputs arrive in **milliseconds**, convert them to seconds per input contract; never pass milliseconds directly expecting the right timestamp.

### 8.3. Template Parsers Can Be More Lenient Than Strict Source Formats

`to_date`/`to_timestamp` follow template parsing rules that can accept looser input than you might expect; do not treat them as a **complete validation system** for user-entered dates. If input must strictly follow `DD/MM/YYYY`, validate length, characters, and calendar bounds separately.

When input is already ISO 8601 and the target type is clear, a direct cast:

~~~sql
SELECT '2026-02-10'::date;
~~~

is usually simpler than a complex template parser.

## 9. TIMESTAMP, TIMESTAMPTZ, and AT TIME ZONE

A major mistake in data analysis is treating all temporal expressions alike.

- `timestamp without time zone` represents **calendar date and time**, carrying no time zone or offset.
- `timestamptz` represents an **absolute instant**; PostgreSQL displays it according to the session time zone or explicit conversion.
- `AT TIME ZONE` works in two ways with **different return types** depending on input.

### 9.1. From Absolute Instant to Local Time

~~~sql
SELECT
    ordered_at,
    ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS local_wall_clock,
    pg_typeof(
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS local_type
FROM expr_lab.orders
WHERE order_id = 1001;
~~~

When `ordered_at` is `timestamptz`, `AT TIME ZONE 'Asia/Ho_Chi_Minh'` yields a **`timestamp without time zone`** representing local wall-clock time.

### 9.2. From Local Wall Clock to an Instant

~~~sql
SELECT
    TIMESTAMP '2026-02-10 12:10:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS exact_instant;
~~~

In this direction, PostgreSQL interprets "12:10 in Vietnam" and returns **`timestamptz`**.

| Input | `AT TIME ZONE 'Asia/Ho_Chi_Minh'` Returns |
| --- | --- |
| `timestamptz` | `timestamp without time zone` |
| `timestamp without time zone` | `timestamptz` |

In regions with daylight saving time, local times can be **ambiguous or nonexistent** on transition days. Vietnam currently observes no DST, yet global systems must still handle named time zones and historical DST policies.

### 9.3. DATE_TRUNC by Month in Business Time Zone

~~~sql
SELECT
    date_trunc(
        'month',
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS vietnam_month,
    COUNT(*) AS n_orders
FROM expr_lab.orders
GROUP BY vietnam_month
ORDER BY vietnam_month;
~~~

Note that the month in Vietnam can differ from the UTC month for events near midnight. When reports must align with a business calendar, convert time zones **before grouping**.

## 10. EXTRACT, DATE_TRUNC, and Temporal Arithmetic

Three temporal operations with distinct goals:

~~~sql
SELECT
    order_id,
    EXTRACT(YEAR FROM ordered_at) AS order_year,
    EXTRACT(MONTH FROM ordered_at) AS order_month,
    date_trunc('day', ordered_at) AS day_boundary,
    ordered_at::date AS session_date
FROM expr_lab.orders
ORDER BY order_id;
~~~

**Warning:** on `timestamptz`, `EXTRACT(MONTH ...)`, `date_trunc('day', ...)`, and `::date` can depend on the session time zone. For region-specific reports, apply `AT TIME ZONE` before extracting year/month/day.

### 10.1. Grouping by Local Day

~~~sql
SELECT
    (ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS order_day,
    COUNT(*) AS order_count
FROM expr_lab.orders
GROUP BY order_day
ORDER BY order_day;
~~~

### 10.2. Computing Real Elapsed Time

~~~sql
SELECT
    o.order_id,
    o.ordered_at,
    c.signup_at,
    o.ordered_at - c.signup_at AS time_since_signup,
    EXTRACT(EPOCH FROM (o.ordered_at - c.signup_at))
        AS seconds_since_signup
FROM expr_lab.orders AS o
JOIN expr_lab.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
~~~

Subtracting two `timestamptz` values produces an **interval**. `EXTRACT(EPOCH FROM interval)` converts that interval into seconds.

### 10.3. AGE Is Not Always Seconds Divided by 86400

~~~sql
SELECT age(
    TIMESTAMP '2026-03-01',
    TIMESTAMP '2026-01-31'
) AS symbolic_age;
~~~

`age` returns an interval with **calendar year/month/day components**, helpful for age calculations. When you need exact elapsed duration between two instants, subtract `timestamp`/`timestamptz` values directly and convert the `interval` to the needed unit.

### 10.4. Generating a Date Axis for Reporting

~~~sql
SELECT day_value::date AS report_day
FROM generate_series(
    DATE '2026-02-01'::timestamp,
    DATE '2026-02-07'::timestamp,
    INTERVAL '1 day'
) AS g(day_value)
ORDER BY report_day;
~~~

`generate_series` emits seven dates. Combining it via `LEFT JOIN` with aggregates lets reports **display zero-order days** rather than skipping days absent from the data.

## 11. String Functions for Cleaning and Display

Input strings can vary in letter case, whitespace, and naming formats.

~~~sql
SELECT
    full_name,
    upper(full_name) AS upper_name,
    lower(email) AS lowercase_email,
    initcap(lower(full_name)) AS title_like_name,
    length(full_name) AS chars_in_name,
    octet_length(full_name) AS bytes_in_name
FROM expr_lab.customers
ORDER BY customer_id;
~~~

### 11.1. LOWER and UPPER

`lower`/`upper` transform case according to the active collation/locale. They are great for search or display normalization, yet **do not by themselves solve all** Unicode, email address, or international personal-name rules.

If business logic treats emails case-insensitively, align policies across:

- how input is accepted and normalized;
- how comparisons are written;
- unique constraints/indexes;
- APIs and data migrations.

### 11.2. BTRIM, LTRIM, RTRIM

~~~sql
SELECT
    btrim('  AB  ') AS trim_both,
    ltrim('  AB  ') AS trim_left,
    rtrim('  AB  ') AS trim_right,
    btrim('---AB---', '-') AS trim_specific_chars;
~~~

`btrim(text, characters)` removes characters from the specified set at **both ends of the string**, leaving middle characters untouched.

### 11.3. REPLACE and REGEXP_REPLACE

~~~sql
SELECT
    replace('ORD_2026_001', '_', '-') AS replaced,
    regexp_replace(
        '  hello   world  ',
        '[[:space:]]+',
        ' ',
        'g'
    ) AS condensed_whitespace;
~~~

`replace` substitutes literal substrings, while `regexp_replace` matches regular expression patterns. The `'g'` flag replaces all matches; without it, only the first match is replaced.

### 11.4. SPLIT_PART and SUBSTRING

~~~sql
SELECT
    split_part('region/store/123', '/', 2) AS part_two,
    substring('ABC-2026-001' FROM 5 FOR 4) AS year_part,
    left('ABC-2026-001', 3) AS prefix,
    right('ABC-2026-001', 3) AS suffix;
~~~

`split_part` extracts a delimited segment using **1-based indexing**. Check for missing delimiters or variable formats before treating extracted substrings as business keys.

### 11.5. LENGTH and OCTET_LENGTH

`length(text)` counts characters as PostgreSQL interprets text, whereas `octet_length(text)` counts bytes. For multi-byte UTF-8 Unicode characters, these two counts can differ.

This matters when external APIs or protocols enforce limits in **bytes** rather than characters.

## 12. String Concatenation: ||, CONCAT, CONCAT_WS, and FORMAT

Concatenation methods differ in **`NULL` semantics**.

~~~sql
SELECT
    'A' || 'B' AS operator_concat,
    concat('A', NULL, 'B') AS function_concat,
    concat_ws(' - ', 'A', NULL, 'B') AS with_separator;
~~~

Results:

| Expression | Result |
| --- | --- |
| `'A' || 'B'` | `AB` |
| `concat('A', NULL, 'B')` | `AB` |
| `concat_ws(' - ', 'A', NULL, 'B')` | `A - B` |

The `||` operator with a `NULL` operand normally returns `NULL`:

~~~sql
SELECT 'A' || NULL::text AS concatenated;
~~~

By contrast, `concat` ignores null arguments. `concat_ws(separator,...)` ignores null values and places separators only between remaining components.

### Example Formatting Customer Labels

~~~sql
SELECT
    customer_id,
    concat_ws(
        ' | ',
        full_name,
        lower(email)
    ) AS customer_label
FROM expr_lab.customers
ORDER BY customer_id;
~~~

If you need a fixed-width code string:

~~~sql
SELECT
    customer_id,
    'CUST-' || lpad(customer_id::text, 6, '0')
        AS customer_code
FROM expr_lab.customers
ORDER BY customer_id;
~~~

For `customer_id = 1`, `lpad` yields `000001`, producing `CUST-000001`. **This is merely a display representation of the ID**, not a surrogate key guaranteed unique or stable unless business rules define it.

## 13. FORMAT: Building Strings with Placeholders

PostgreSQL's `format(formatstr, ...)` accepts placeholders:

- `%s`: inserts argument as string (null formats as empty string per function rules).
- `%I`: quotes argument as a **SQL identifier**.
- `%L`: quotes argument as a **SQL literal**; null renders as the `NULL` keyword.
- `%%`: literal `%` character.

Example:

~~~sql
SELECT
    format('Hello %s!', 'Lan') AS greeting,
    format('%s - %s', 'ORD-1001', 'paid') AS order_label,
    format('%I', 'Order Items') AS quoted_identifier,
    format('%L', 'O''Reilly') AS quoted_literal;
~~~

### 13.1. FORMAT with Dynamic SQL: Distinguishing Identifiers from Values

~~~sql
SELECT format(
    'SELECT %I FROM %I.%I WHERE %I = %L',
    'status',
    'expr_lab',
    'orders',
    'order_id',
    1001
) AS generated_sql;
~~~

The result is a **string containing SQL**, not executed automatically. Use `%I` for schema/table/column names and `%L` for literals.

**Never use `format('... %s ...', raw_user_input)` to splice user data directly into executable SQL.** In Java/JDBC, prefer **prepared statements** and bind parameters for values. When dynamic SQL truly requires variable object names, quote identifiers properly and whitelist allowed names.

### 13.2. FORMAT Differs from TO_CHAR

| Function | Role |
| --- | --- |
| `to_char(numeric, template)` | Formats numbers by mask |
| `to_char(date/timestamp, template)` | Formats temporal values by mask |
| `format(text, ...)` | Combines multiple arguments into a string using placeholders |
| `concat_ws(separator,...)` | Joins parts with a separator |

When you need `DD/MM/YYYY`, use `to_char`. When you need `"Order 1001: paid"`, `format` or `concat_ws` is convenient.

## 14. Converting JSONB to Typed Values

`jsonb` lets a column store JSON structures. Distinguish:

~~~sql
metadata -> 'risk_score'
~~~

which returns **JSONB**, from:

~~~sql
metadata ->> 'risk_score'
~~~

which returns **text** for the extracted JSON value.

Example:

~~~sql
SELECT
    order_id,
    metadata -> 'risk_score' AS score_as_jsonb,
    metadata ->> 'risk_score' AS score_as_text,
    (metadata ->> 'risk_score')::integer AS score_as_integer,
    pg_typeof(metadata -> 'risk_score') AS json_type,
    pg_typeof(metadata ->> 'risk_score') AS text_type
FROM expr_lab.orders
ORDER BY order_id;
~~~

In the sample data, `risk_score` is present on some orders and absent on others. When a key does not exist, key lookup returns SQL `NULL`; casting `NULL` to integer still returns null. However, if a key holds `"not-a-number"`, casting to integer raises an error.

### 14.1. When to Use -> vs. ->>?

| Need | Operator / Function |
| --- | --- |
| Keep JSONB for further JSON processing | `->` |
| Read field as text | `->>` |
| Access nested key as JSONB | `#>` |
| Access nested key as text | `#>>` |
| Build JSONB from a SQL value | `to_jsonb` |
| Build JSON object from key/value pairs | `jsonb_build_object` |

Example:

~~~sql
SELECT
    order_id,
    metadata ->> 'promo' AS promo_code,
    metadata #>> '{labels,0}' AS first_label
FROM expr_lab.orders
ORDER BY order_id;
~~~

`#>> '{labels,0}'` follows the path: key `labels`, array element at index **0**. JSON arrays are 0-based in this path syntax, unlike `WITH ORDINALITY` on set-returning functions (which is 1-based).

### 14.2. Building JSONB for APIs

~~~sql
SELECT
    jsonb_build_object(
        'order_id', order_id,
        'status', status,
        'amount', amount,
        'placed_at', to_char(
            ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh',
            'YYYY-MM-DD HH24:MI:SS'
        )
    ) AS order_json
FROM expr_lab.orders
WHERE order_id = 1001;
~~~

This builds a JSON object. `amount` enters JSON as a numeric value per PostgreSQL's conversion rules; `placed_at` is a **formatted string** we constructed intentionally.

If an API needs an instant with an offset for multi-timezone consumers, define a clear temporal contract rather than sending zone-less strings.

## 15. Expanding JSONB Arrays into Rows for Analysis

Example listing each order's labels:

~~~sql
SELECT
    o.order_id,
    tag.value AS label
FROM expr_lab.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements_text(
        o.metadata -> 'labels'
    ) AS tag(value)
ORDER BY o.order_id, tag.value;
~~~

`jsonb_array_elements_text` expands elements of a JSON array into multiple text rows.

### 15.1. LEFT JOIN LATERAL Preserves Orders with Empty Arrays

~~~sql
SELECT
    o.order_id,
    tag.value AS label
FROM expr_lab.orders AS o
LEFT JOIN LATERAL
    jsonb_array_elements_text(
        o.metadata -> 'labels'
    ) AS tag(value) ON TRUE
ORDER BY o.order_id, tag.value NULLS LAST;
~~~

When `labels` is empty, `CROSS JOIN LATERAL` omits that order, whereas `LEFT JOIN LATERAL` retains one row with `label = NULL`.

### 15.2. WITH ORDINALITY Preserves Element Position

~~~sql
SELECT
    o.order_id,
    tag.position,
    tag.value AS label
FROM expr_lab.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements_text(
        o.metadata -> 'labels'
    ) WITH ORDINALITY AS tag(value, position)
ORDER BY o.order_id, tag.position;
~~~

`position` starts at 1. This is a reliable way to keep the order of labels inside the array.

**Caution:** after expanding two labels on one order into two rows, running `SUM(o.amount)` directly over the expanded rows **double-counts that order's amount**. When summing order totals, keep the **one-row-per-order grain** or aggregate before expanding labels.

## 16. Aggregates: Analyzing Counts, Sums, and Averages

Common aggregate functions:

~~~sql
SELECT
    COUNT(*) AS total_orders,
    SUM(amount) AS total_order_amount,
    AVG(amount) AS avg_order_amount,
    MIN(amount) AS minimum_amount,
    MAX(amount) AS maximum_amount
FROM expr_lab.orders;
~~~

Each returns a metric across the selected rows. `COUNT(*)` counts all rows; `COUNT(amount)` counts non-null `amount` values. Because the lab table defines `amount NOT NULL`, both counts match, though in nullable real-world tables they often differ.

### 16.1. GROUP BY Splits Rows into Groups

~~~sql
SELECT
    channel,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM expr_lab.orders
GROUP BY channel
ORDER BY channel;
~~~

The result has one row per `channel` value present in the orders table, not every possible business channel.

### 16.2. FILTER: Multiple Conditional Aggregates

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    COUNT(*) FILTER (
        WHERE status = 'refunded'
    ) AS refunded_orders,
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) AS paid_amount
FROM expr_lab.orders;
~~~

Result:

| all_orders | paid_orders | refunded_orders | paid_amount |
| ---: | ---: | ---: | ---: |
| 9 | 6 | 1 | 870000.50 |

`FILTER (WHERE ...)` filters rows only for **that specific aggregate function**. A query-level `WHERE` removes rows from the **entire** input set of all aggregates.

### 16.3. SUM and AVG on Empty Sets

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE status = 'not_a_real_status'
    ) AS n,
    SUM(amount) FILTER (
        WHERE status = 'not_a_real_status'
    ) AS s,
    AVG(amount) FILTER (
        WHERE status = 'not_a_real_status'
    ) AS a
FROM expr_lab.orders;
~~~

`COUNT` returns **0**, whereas `SUM` and `AVG` return **NULL** when given zero inputs. Use `COALESCE(SUM(...), 0)` when business rules want a 0 sum; for an average with no observations, `NULL` is usually more accurate than 0.

## 17. Computing Ratios: Avoiding Integer Division and Zero Denominators

Paid order rate:

~~~sql
SELECT
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    COUNT(*) AS all_orders,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE status = 'paid')
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_rate_pct
FROM expr_lab.orders;
~~~

With six paid orders out of nine, the rate is **66.67%** (rounded to two decimal places).

Two key details:

1. Multiply by `100.0` to compute in decimal rather than risking integer division elsewhere in the expression.
2. `NULLIF(COUNT(*), 0)` returns null when the denominator is 0, preventing division-by-zero errors.

### Rate by Channel

~~~sql
SELECT
    channel,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE status = 'paid')
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_rate_pct
FROM expr_lab.orders
GROUP BY channel
ORDER BY channel;
~~~

Never compute an overall system rate as an unweighted average of per-channel rates when channels have different order volumes. The denominator for the **overall rate** must be the overall total orders.

## 18. DATE_TRUNC Combined with Aggregates: Monthly Reporting

~~~sql
WITH monthly_orders AS (
    SELECT
        date_trunc(
            'month',
            ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        status,
        amount
    FROM expr_lab.orders
)
SELECT
    month_start,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    COALESCE(
        SUM(amount) FILTER (
            WHERE status = 'paid'
        ),
        0::numeric
    ) AS paid_amount
FROM monthly_orders
GROUP BY month_start
ORDER BY month_start;
~~~

Expected result:

| month_start | all_orders | paid_orders | paid_amount |
| --- | ---: | ---: | ---: |
| 2026-01-01 | 4 | 3 | 465000.50 |
| 2026-02-01 | 5 | 3 | 405000.00 |

Monthly summaries combine **local time conversion**, **temporal truncation**, and **conditional aggregation**. Each step has a clear purpose; omitting `AT TIME ZONE` ties month boundaries to the session's `TimeZone`.

### WHERE Range Predicates Instead of TO_CHAR on Columns

To select February orders in Vietnam time, write explicit timestamp bounds:

~~~sql
SELECT COUNT(*)
FROM expr_lab.orders
WHERE ordered_at >= (
    TIMESTAMP '2026-02-01 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
AND ordered_at < (
    TIMESTAMP '2026-03-01 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
);
~~~

This cleanly expresses a **half-open interval [start, end)** and lets the planner use a B-tree index on `ordered_at`.

By contrast, writing:

~~~sql
WHERE to_char(ordered_at, 'YYYY-MM') = '2026-02'
~~~

both depends on time zone/formatting and wraps the column in a function, preventing direct use of an ordinary index on `ordered_at`. When filtering by time periods, prefer typed instant boundaries.

## 19. Window Functions: Analyzing Without Collapsing Rows

Aggregates with `GROUP BY` emit one row per group. Window functions let you **keep every individual row** while attaching group-level metrics.

### 19.1. ROW_NUMBER Ordering Each Customer's Orders

~~~sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at DESC, order_id DESC
    ) AS newest_first
FROM expr_lab.orders
ORDER BY customer_id, newest_first;
~~~

`PARTITION BY customer_id` groups rows by customer, `ORDER BY` sorts orders within each customer, and `ROW_NUMBER` assigns 1, 2, 3...

To fetch **each customer's latest order**, use a CTE:

~~~sql
WITH ranked AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM expr_lab.orders AS o
)
SELECT customer_id, order_id, ordered_at, amount
FROM ranked
WHERE rn = 1
ORDER BY customer_id;
~~~

PostgreSQL does not allow `WHERE ROW_NUMBER() ... = 1` directly at the same query level, because window functions are evaluated after `WHERE`. Using a CTE or subquery is the standard clean pattern.

### 19.2. RANK and DENSE_RANK Differ from ROW_NUMBER

~~~sql
WITH scores(name, points) AS (
    VALUES
        ('A', 95),
        ('B', 90),
        ('C', 90),
        ('D', 80)
)
SELECT
    name,
    points,
    ROW_NUMBER() OVER (
        ORDER BY points DESC, name
    ) AS row_no,
    RANK() OVER (
        ORDER BY points DESC
    ) AS rank_no,
    DENSE_RANK() OVER (
        ORDER BY points DESC
    ) AS dense_rank_no
FROM scores
ORDER BY points DESC, name;
~~~

Result:

| name | points | row_no | rank_no | dense_rank_no |
| --- | ---: | ---: | ---: | ---: |
| A | 95 | 1 | 1 | 1 |
| B | 90 | 2 | 2 | 2 |
| C | 90 | 3 | 2 | 2 |
| D | 80 | 4 | 4 | 3 |

`RANK` leaves gaps after ties, whereas `DENSE_RANK` does not. `ROW_NUMBER` numbers **every individual row**, so include a tie-breaker like `name` in its `ORDER BY` for deterministic results on tied scores.

## 20. LAG and LEAD: Comparing Against Previous or Next Rows

`LAG` and `LEAD` read values from preceding or following rows in the window order.

~~~sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    amount,
    LAG(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS previous_amount,
    amount - LAG(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS change_from_previous
FROM expr_lab.orders
ORDER BY customer_id, ordered_at, order_id;
~~~

For each customer's first order, there is no prior row, so `LAG(amount)` returns `NULL` and the difference is also null. You can use `COALESCE` if business logic assumes "previous amount was 0," though many reports keep null to indicate **no prior value for comparison**.

### LEAD to Inspect the Next Order Status

~~~sql
SELECT
    customer_id,
    order_id,
    status,
    LEAD(status) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS next_order_status
FROM expr_lab.orders
ORDER BY customer_id, ordered_at, order_id;
~~~

`LEAD` here checks the status of **the customer's next order in history**, not status transitions **within the same order**. To analyze state transitions of one order, you need an order-status-event log table over time.

## 21. Running Totals and Moving Averages

### 21.1. Running Paid Total Per Customer

~~~sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    status,
    amount,
    COALESCE(
        SUM(amount) FILTER (
            WHERE status = 'paid'
        ) OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at, order_id
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        ),
        0::numeric
    ) AS running_paid_amount
FROM expr_lab.orders
ORDER BY customer_id, ordered_at, order_id;
~~~

`FILTER` ensures only **paid orders** contribute to the sum, while pending/cancelled/refunded orders still appear in the output rows.

For Lan, the running paid total after order 1001 is `125000.50`; after order 1002 (pending) it remains the same; after order 1006 (paid) it becomes `265000.50`.

### 21.2. Three-Order Moving Average

~~~sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    amount,
    AVG(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS avg_last_three_orders
FROM expr_lab.orders
ORDER BY customer_id, ordered_at, order_id;
~~~

Meaning: at each order, compute the average of **at most three rows**—the current row and the two preceding rows—within each customer.

This is a **row-count moving average**, not a **three-day** average. For a time-based window, use a `RANGE` frame on time or aggregate by day first, depending on data and PostgreSQL version.

### 21.3. LAST_VALUE and Window Frames

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    LAST_VALUE(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS last_amount_in_customer_history
FROM expr_lab.orders
ORDER BY customer_id, ordered_at, order_id;
~~~

With `LAST_VALUE`, the window **frame** is critical. With `ORDER BY` and no explicit frame, the default frame ends at the **current row (or last peer)** rather than the end of the **entire partition**. To get the final value across the whole group in that order, specify `UNBOUNDED FOLLOWING` as shown above.

## 22. Percentiles, Median, and Dispersion

Beyond averages, reports often need the **median**, standard deviation, or amount quantiles.

### 22.1. Median with PERCENTILE_CONT

~~~sql
SELECT
    PERCENTILE_CONT(0.5)
        WITHIN GROUP (
            ORDER BY amount::double precision
        ) AS median_paid_amount
FROM expr_lab.orders
WHERE status = 'paid';
~~~

The six paid amounts in ascending order:

~~~text
65000.00
90000.00
125000.50
140000.00
200000.00
250000.00
~~~

With six elements, the continuous median is the average of the third and fourth elements:

~~~text
(125000.50 + 140000.00) / 2 = 132500.25
~~~

`PERCENTILE_CONT(0.5)` is an **ordered-set aggregate** that interpolates between values. With `amount::double precision` in the example, the return type is floating point. If strict decimal precision is required for monetary rules, mind interpolation and floating-point conversion semantics.

### 22.2. PERCENTILE_DISC: Value Present in the Dataset

~~~sql
SELECT
    PERCENTILE_DISC(0.5)
        WITHIN GROUP (ORDER BY amount)
        AS discrete_median_paid_amount
FROM expr_lab.orders
WHERE status = 'paid';
~~~

`PERCENTILE_DISC` picks an actual **value present in the dataset** using discrete percentile rules rather than interpolating like `PERCENTILE_CONT`. For those six values at percentile 0.5, the discrete result is `125000.50`.

Do not assume "median" across all reports uses the same formula when the count is even; specify **continuous median** vs. **discrete percentile** per business rules.

### 22.3. Standard Deviation

~~~sql
SELECT
    COUNT(*) AS n_paid,
    ROUND(AVG(amount), 2) AS mean_paid_amount,
    ROUND(STDDEV_SAMP(amount), 2) AS sample_stddev,
    ROUND(STDDEV_POP(amount), 2) AS population_stddev
FROM expr_lab.orders
WHERE status = 'paid';
~~~

- `STDDEV_SAMP` computes the sample standard deviation.
- `STDDEV_POP` computes the population standard deviation.
- With too few observations, sample statistics can return null due to insufficient degrees of freedom.

In analytics, clarify whether **the set is a sample or the entire population**, and whether outliers or status filters skew the numbers.

### 22.4. Simple Z-Score

~~~sql
WITH paid_orders AS (
    SELECT order_id, amount
    FROM expr_lab.orders
    WHERE status = 'paid'
),
stats AS (
    SELECT
        AVG(amount) AS mean_amount,
        STDDEV_POP(amount) AS sd_amount
    FROM paid_orders
)
SELECT
    p.order_id,
    p.amount,
    ROUND(
        (p.amount - s.mean_amount)
        / NULLIF(s.sd_amount, 0),
        3
    ) AS z_score
FROM paid_orders AS p
CROSS JOIN stats AS s
ORDER BY p.order_id;
~~~

A `Z-score` measures deviation from the mean in units of standard deviation within the chosen set. If standard deviation is 0 (all values identical), the denominator is 0; `NULLIF` returns null instead of raising an error. Never flag fraud or financial anomalies solely from an unvalidated z-score threshold.

## 23. Grouping Analytics with ROLLUP and GROUPING

A report may need both per-channel totals and a system-wide summary row.

~~~sql
SELECT
    CASE
        WHEN GROUPING(channel) = 1 THEN 'ALL_CHANNELS'
        ELSE channel
    END AS channel_group,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    COALESCE(
        SUM(amount) FILTER (
            WHERE status = 'paid'
        ),
        0::numeric
    ) AS paid_amount
FROM expr_lab.orders
GROUP BY ROLLUP (channel)
ORDER BY GROUPING(channel), channel_group;
~~~

`ROLLUP(channel)` produces per-channel groups plus the grand total row. `GROUPING(channel)` distinguishes the summary row generated by `ROLLUP` from a real row whose `channel` happens to be `NULL`.

Constructs such as `GROUPING SETS` and `CUBE` produce multi-level summaries; use them only when the output format fits actual needs, as group counts grow rapidly.

### Creating a "Every Day Even Without Orders" Report

~~~sql
WITH days AS (
    SELECT day_value::date AS order_day
    FROM generate_series(
        TIMESTAMP '2026-02-08',
        TIMESTAMP '2026-02-12',
        INTERVAL '1 day'
    ) AS g(day_value)
),
orders_per_day AS (
    SELECT
        (ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS order_day,
        COUNT(*) AS n_orders
    FROM expr_lab.orders
    GROUP BY 1
)
SELECT
    d.order_day,
    COALESCE(o.n_orders, 0) AS order_count
FROM days AS d
LEFT JOIN orders_per_day AS o USING (order_day)
ORDER BY d.order_day;
~~~

Because `generate_series` builds the date axis, days with zero orders appear with `order_count = 0`. Directly running `GROUP BY order_day` on the orders table would omit days with no rows.

## 24. Performance: Column Functions and Index Eligibility

A frequent pattern:

~~~sql
WHERE lower(email) = 'lan@example.test'
~~~

If only a plain index exists on `email`, PostgreSQL will not use it directly to satisfy `lower(email)`.

### 24.1. Expression Index

~~~sql
CREATE INDEX idx_customers_email_lower
ON expr_lab.customers (lower(email));
~~~

Then querying:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, full_name
FROM expr_lab.customers
WHERE lower(email) = 'lan@example.test';
~~~

lets the planner consider the expression index. On a four-row lab table, `Seq Scan` remains cheaper; that does not mean the index is wrong.

**A plain `CREATE INDEX` expression index does not enforce uniqueness.** For case-insensitive uniqueness, design a **unique expression index** or equivalent mechanism after cleaning existing duplicates and aligning normalization/collation policies.

### 24.2. Prefer Timestamp Ranges When Filtering Dates

Compare:

~~~sql
-- Applies a function per row and misses direct use of
-- an ordinary index on ordered_at:
WHERE to_char(ordered_at, 'YYYY-MM') = '2026-02'
~~~

with:

~~~sql
-- Strongly typed time range:
WHERE ordered_at >= (
    TIMESTAMP '2026-02-01'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
AND ordered_at < (
    TIMESTAMP '2026-03-01'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
~~~

With the index:

~~~sql
CREATE INDEX idx_orders_ordered_at
ON expr_lab.orders (ordered_at);
~~~

the planner can perform an index range scan. Filtering with instant bounds also avoids comparing formatted date strings.

### 24.3. Do Not Create Indexes Before Understanding the Workload

Indexes carry costs:

- Consume disk space and buffer cache.
- `INSERT`, `UPDATE`, and `DELETE` must maintain index entries.
- Expression indexes recompute expressions when rows change.
- Some session/locale-dependent functions fail expression index immutability rules.

Compare via `EXPLAIN (ANALYZE, BUFFERS)` on representative data and review overall latency/throughput. Never claim `to_char` in `WHERE` is "always slow"; the real issues are **index eligibility, optimization opportunities, and semantic correctness**.

## 25. Checking Types and Debugging Expressions

In complex SQL, errors often stem from PostgreSQL inferring unexpected types.

### 25.1. PG_TYPEOF

~~~sql
SELECT
    pg_typeof(1) AS integer_literal_type,
    pg_typeof(1.0) AS decimal_literal_type,
    pg_typeof('123'::text) AS cast_text_type,
    pg_typeof('2026-02-10'::date) AS date_type,
    pg_typeof(now()) AS now_type,
    pg_typeof(to_char(now(), 'YYYY-MM-DD')) AS formatted_type;
~~~

Especially with `CASE`, `COALESCE`, or `UNION`, PostgreSQL must resolve **a common result type** across branches.

### 25.2. CASE Branches Must Have Compatible Types

Correct:

~~~sql
SELECT
    CASE
        WHEN status = 'paid' THEN amount
        ELSE 0::numeric
    END AS amount_if_paid
FROM expr_lab.orders;
~~~

Error-prone:

~~~sql
-- Do not mix numeric and text labels in the same CASE result:
SELECT
    CASE
        WHEN status = 'paid' THEN amount
        ELSE 'N/A'
    END
FROM expr_lab.orders;
~~~

In the flawed branch above, PostgreSQL tries to resolve a common type, and `'N/A'` cannot be cast to `numeric`.

If the goal is a **text display column**, explicitly format both branches as text:

~~~sql
SELECT
    CASE
        WHEN status = 'paid'
        THEN to_char(amount, 'FM999,999,990.00')
        ELSE 'N/A'
    END AS amount_display
FROM expr_lab.orders;
~~~

### 25.3. format Does Not Replace Prepared Statements

When communicating from Java/JDBC, bind user values as parameters:

~~~java
String sql = """
    SELECT order_id, amount
    FROM expr_lab.orders
    WHERE customer_id = ?
      AND ordered_at >= ?
      AND ordered_at < ?
    ORDER BY ordered_at
    """;
~~~

This snippet uses Java text blocks (Java 15+) showing parameter placeholders. Use `PreparedStatement` with properly typed values/timestamps rather than splicing formatted text into SQL. Formatting values for display and constructing safe SQL are **two separate concerns**.

## 26. Common Mistakes

### Mistake 1. Sorting Numbers Using Formatted Text

~~~sql
ORDER BY to_char(amount, 'FM999,999,990.00')
~~~

sorts as **text**, not numerically. To sort amounts from lowest to highest, use `ORDER BY amount` and put `to_char` only in `SELECT` for display.

### Mistake 2. Confusing timestamp and timestamptz

A string `'2026-02-10 12:10'` does not state its time zone. In multi-region analytics, verify whether values are local clocks or absolute instants before casting, formatting, or grouping by month.

### Mistake 3. Filtering Time Using Formatted Display Strings

`WHERE to_char(ordered_at, 'YYYY-MM') = ...` depends on time zone and hinders index scans. Prefer `timestamptz` ranges aligned to the business time zone.

### Mistake 4. Casting Untrusted Source Data Directly

`'15x'::numeric` raises an error and can abort an entire import statement. Validate/normalize first, log bad rows, and never drop data silently.

### Mistake 5. Assuming TO_NUMBER Understands All Locales Automatically

`'1,250.50'` and `'1.250,50'` can represent the same number in different locales with opposite separators. Know the source format and matching template/settings.

### Mistake 6. Thinking Format CHECK Equals Business CHECK

A regex accepts `'999999999999999999'` as digits, yet it can overflow the target numeric precision or violate business bounds. Validate range, digit counts, and domain rules too.

### Mistake 7. Conflating NULL with 0

Having no amount or no observations for `AVG` differs from a genuine 0 value. Only apply `COALESCE` according to business semantics.

### Mistake 8. Using AVG(CASE WHEN ... ELSE 0) with the Wrong Denominator

~~~sql
AVG(CASE WHEN status = 'paid' THEN amount ELSE 0 END)
~~~

divides across all rows, not only paid rows. If you want the average of **paid orders**, use:

~~~sql
AVG(amount) FILTER (WHERE status = 'paid')
~~~

### Mistake 9. Forgetting the Window Frame on LAST_VALUE

`LAST_VALUE` does not automatically read the last row of the entire partition when the default frame stops at the current row/peer. Declare the frame explicitly to fit your question.

### Mistake 10. Summing After a One-to-Many Join or JSON Expansion

An order with two labels or two line items appears twice in the joined result, doubling `SUM(amount)`. Confirm the **grain** before aggregating.

### Mistake 11. Treating String Formatting as Stored Rounding

`to_char(amount, '...00')` changes display only. It does not update the `amount` column or truncate stored fractional digits.

### Mistake 12. Creating Expression Indexes Without Checking Plans

Not all functions are immutable enough for expression indexes, and even valid indexes may be skipped by the planner on small datasets. Evaluate query patterns, immutability, and write overhead.

## 27. Practice Exercises

The exercises below use schema `expr_lab` and the nine sample orders. Predict return types and `NULL` cases before running each query.

### Exercise 1. Value vs. Representation

Write a query returning `order_id`, raw `amount`, and `amount_display` with grouping commas and two decimal places. Why should you not `ORDER BY amount_display` when sorting by price?

### Exercise 2. CAST and Precision

Compare the results:

~~~sql
123.456::numeric(10, 2)
trunc(123.456::numeric, 2)
round(123.456::numeric, 2)
~~~

Explain the difference between casting to a scale and truncating fractional digits.

### Exercise 3. Cleaning Numbers from Text

Given `' 1200.50 '`, `''`, `'N/A'`, and `'12x'`, use `btrim`, `nullif`, `CASE`, and regex to cast only valid simple decimal strings.

### Exercise 4. TO_DATE

Write an expression parsing `'10/02/2026'` into `date` and an expression formatting the result as `'2026-02-10'`.

### Exercise 5. Time Zones

For `ordered_at timestamptz`, write an expression formatting `DD/MM/YYYY HH24:MI` in `Asia/Ho_Chi_Minh` and an expression grouping orders by local month.

### Exercise 6. TO_TIMESTAMP

Distinguish `to_timestamp('2026-02-10 12:10:05', 'YYYY-MM-DD HH24:MI:SS')` from `to_timestamp(1700000000::double precision)`.

### Exercise 7. String Functions

Write expressions converting an email to lowercase, stripping whitespace from both ends of a string, and generating customer code `CUST-000001` from `customer_id = 1`.

### Exercise 8. JSONB Type Conversion

Return `risk_score` as an integer from `metadata`. What does the expression return if the key is missing? What happens if the key contains non-numeric text?

### Exercise 9. Paid Summary

Compute total orders, paid orders count, total `amount` of paid orders, and paid percentage of total orders. Predict the numbers from the nine sample orders.

### Exercise 10. Grouping by Month

Return one row per Vietnam calendar month: month, total orders, paid orders, and total paid amount. Verify January and February outputs.

### Exercise 11. ROW_NUMBER

For each customer with orders, fetch their latest order using `ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY ordered_at DESC, order_id DESC)`.

### Exercise 12. LAG

Compute `previous_amount` and the difference between current `amount` and the same customer's previous order. Why is the delta null for each customer's first order?

### Exercise 13. RANK and DENSE_RANK

Given scores `95,90,90,80`, explain the difference between `RANK` and `DENSE_RANK`.

### Exercise 14. Median

Compute the continuous median for paid orders using `PERCENTILE_CONT(0.5) WITHIN GROUP`. What is the median?

### Exercise 15. Standard Deviation

Write a query computing `AVG`, `STDDEV_SAMP`, and `STDDEV_POP` for paid order `amount`. When can sample statistics return null?

### Exercise 16. Window Frame

Compute the running paid total per customer using frame `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. Are unpaid orders kept in the output?

### Exercise 17. JSON Array Data

Expand `metadata.labels` into multiple rows with `order_id`. How do you preserve element position, and how do you preserve orders with empty arrays?

### Exercise 18. FORMAT and Dynamic SQL

Distinguish placeholders `%s`, `%I`, and `%L`. Why should you never interpolate raw user input into dynamic SQL with `%s`?

### Exercise 19. Query Performance

Filter February orders in Vietnam time so PostgreSQL can consider an ordinary B-tree index on `ordered_at`. Why avoid filtering with `to_char(ordered_at, 'YYYY-MM')`?

### Exercise 20. Empty Aggregate Sets

What do `COUNT(*)`, `SUM(amount)`, and `AVG(amount)` return when zero rows match? Should every null be replaced with 0?

## 28. Solutions and Hints

### Exercise 1. Numeric vs. Display String

~~~sql
SELECT
    order_id,
    amount,
    to_char(amount, 'FM999,999,990.00') AS amount_display
FROM expr_lab.orders
ORDER BY amount;
~~~

`ORDER BY amount` sorts using `numeric`; `amount_display` is `text` and does not preserve numeric order.

### Exercise 2. Cast, TRUNC, ROUND

`123.456::numeric(10,2) = 123.46`; `trunc(...,2) = 123.45`; `round(...,2) = 123.46`. Casting to a scale can round, whereas `trunc` chops off fractional digits.

### Exercise 3. Normalizing Input

~~~sql
WITH inputs(raw) AS (
    VALUES
        (' 1200.50 '::text),
        (''::text),
        ('N/A'::text),
        ('12x'::text)
)
SELECT
    raw,
    CASE
        WHEN btrim(raw) ~ '^[0-9]+([.][0-9]{1,2})?$'
        THEN btrim(raw)::numeric(12,2)
        ELSE NULL
    END AS amount
FROM inputs;
~~~

`' 1200.50 '` becomes numeric `1200.50`; the other three yield null in this illustrative formula.

### Exercise 4. Formatted Dates

~~~sql
SELECT
    to_date('10/02/2026', 'DD/MM/YYYY') AS parsed_date,
    to_char(
        to_date('10/02/2026', 'DD/MM/YYYY'),
        'YYYY-MM-DD'
    ) AS formatted_date;
~~~

### Exercise 5. Time Zone Conversion

~~~sql
SELECT
    order_id,
    to_char(
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh',
        'DD/MM/YYYY HH24:MI'
    ) AS local_time,
    date_trunc(
        'month',
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS local_month
FROM expr_lab.orders;
~~~

### Exercise 6. Two Overloads of TO_TIMESTAMP

The `(text, text)` signature parses a timestamp by template; the `(double precision)` signature converts Unix epoch seconds. Watch session `TimeZone` when parsing offset-less strings.

### Exercise 7. String Helpers

~~~sql
SELECT
    lower('Lan@Example.test') AS email_lower,
    btrim('   hello   ') AS trimmed,
    'CUST-' || lpad(1::text, 6, '0') AS customer_code;
~~~

### Exercise 8. JSONB to Integer

~~~sql
SELECT
    order_id,
    (metadata ->> 'risk_score')::integer AS risk_score
FROM expr_lab.orders;
~~~

Missing keys return null. Non-numeric text raises a cast error; validate untrusted source data before casting.

### Exercise 9. Paid Summary

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    SUM(amount) FILTER (WHERE status = 'paid') AS paid_amount,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE status = 'paid')
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_rate_pct
FROM expr_lab.orders;
~~~

Results: **9, 6, 870000.50, 66.67**.

### Exercise 10. Monthly Paid

~~~sql
WITH src AS (
    SELECT
        date_trunc(
            'month',
            ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        status,
        amount
    FROM expr_lab.orders
)
SELECT
    month_start,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    SUM(amount) FILTER (WHERE status = 'paid') AS paid_amount
FROM src
GROUP BY month_start
ORDER BY month_start;
~~~

January: **4 orders, 3 paid, 465000.50**. February: **5 orders, 3 paid, 405000.00**.

### Exercise 11. Latest Order

~~~sql
WITH ranked AS (
    SELECT
        order_id, customer_id, ordered_at, status,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM expr_lab.orders
)
SELECT customer_id, order_id, status
FROM ranked
WHERE rn = 1
ORDER BY customer_id;
~~~

Returns the latest order for Lan, Minh, and An. Customer Chi has no orders so does not appear from `orders`.

### Exercise 12. LAG

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    LAG(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS previous_amount,
    amount - LAG(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS amount_delta
FROM expr_lab.orders
ORDER BY customer_id, ordered_at, order_id;
~~~

The first row in each partition has no prior row to compare against.

### Exercise 13. Ranking

`RANK` returns `1,2,2,4`; `DENSE_RANK` returns `1,2,2,3`. `ROW_NUMBER` numbers each row sequentially and needs a tie-breaker for stable ordering.

### Exercise 14. Median

~~~sql
SELECT
    PERCENTILE_CONT(0.5)
        WITHIN GROUP (ORDER BY amount::double precision)
        AS median_paid
FROM expr_lab.orders
WHERE status = 'paid';
~~~

Result: **132500.25**.

### Exercise 15. Standard Deviation

~~~sql
SELECT
    AVG(amount) AS avg_amount,
    STDDEV_SAMP(amount) AS sample_sd,
    STDDEV_POP(amount) AS population_sd
FROM expr_lab.orders
WHERE status = 'paid';
~~~

Sample statistics like `STDDEV_SAMP` require enough observations to compute sample variance; with a single non-null value, sample standard deviation is undefined and returns null.

### Exercise 16. Running Total

~~~sql
SELECT
    customer_id, order_id, status, amount,
    COALESCE(
        SUM(amount) FILTER (
            WHERE status = 'paid'
        ) OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at, order_id
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        ),
        0::numeric
    ) AS running_paid_amount
FROM expr_lab.orders
ORDER BY customer_id, ordered_at, order_id;
~~~

Unpaid rows **stay in the result**, without adding their `amount` to the running total.

### Exercise 17. JSONB Labels

~~~sql
SELECT
    o.order_id,
    tag.position,
    tag.label
FROM expr_lab.orders AS o
LEFT JOIN LATERAL
    jsonb_array_elements_text(
        o.metadata -> 'labels'
    ) WITH ORDINALITY AS tag(label, position)
    ON TRUE
ORDER BY o.order_id, tag.position NULLS LAST;
~~~

`LEFT JOIN LATERAL` retains rows with empty arrays; `WITH ORDINALITY` records 1-based positions.

### Exercise 18. FORMAT

`%s` formats an argument as a string, `%I` quotes a SQL identifier, `%L` quotes a SQL literal. In applications, bind values via prepared statements; `%s` provides no protection against dangerous input in dynamic SQL.

### Exercise 19. Time Ranges

~~~sql
SELECT order_id, ordered_at
FROM expr_lab.orders
WHERE ordered_at >= (
    TIMESTAMP '2026-02-01'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
AND ordered_at < (
    TIMESTAMP '2026-03-01'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
);
~~~

`timestamptz` bounds reflect exact month boundaries in Vietnam and allow the planner to use an index on the underlying column. `to_char` produces text and complicates comparisons and index usage.

### Exercise 20. Empty Groups

`COUNT(*) = 0`, `SUM(amount) = NULL`, `AVG(amount) = NULL`. `COALESCE` fits when display rules want a 0 total, whereas averages with no data should usually stay null or display "N/A."

## 29. Quick Reference Table

| Goal | Tool |
| --- | --- |
| Standard SQL cast | `CAST(x AS type)` |
| PostgreSQL shorthand cast | `x::type` |
| Inspect expression type | `pg_typeof(x)` |
| Format number by template | `to_char(number, template)` |
| Format date/time | `to_char(timestamp, template)` |
| Parse date | `to_date(text, template)` |
| Parse timestamp by template | `to_timestamp(text, template)` |
| Epoch seconds to instant | `to_timestamp(double precision)` |
| Parse formatted number | `to_number(text, template)` |
| Concatenate text handling nulls | `concat`, `concat_ws` |
| Build string with placeholders | `format('%s %I %L', ...)` |
| Strip whitespace | `btrim`, `ltrim`, `rtrim` |
| Normalize letter case | `lower`, `upper` |
| Regex replacement | `regexp_replace` |
| Split string by delimiter | `split_part` |
| Convert time zone | `AT TIME ZONE` |
| Extract temporal field | `extract` |
| Truncate to day/month boundary | `date_trunc` |
| Generate date axis | `generate_series` |
| JSONB value as text | `->>`, `#>>` |
| Build JSONB | `to_jsonb`, `jsonb_build_object` |
| Expand JSON array | `jsonb_array_elements_text` |
| Grouped summary statistics | `GROUP BY` + `COUNT/SUM/AVG` |
| Conditional aggregation | `FILTER (WHERE condition)` |
| Division-by-zero-safe ratios | `NULLIF(denominator, 0)` |
| Ranking within groups | `ROW_NUMBER`, `RANK`, `DENSE_RANK` |
| Access prior/next rows | `LAG`, `LEAD` |
| Running totals / moving averages | Aggregate `OVER (...) ROWS ...` |
| Median / percentiles | `PERCENTILE_CONT`, `PERCENTILE_DISC` |
| Standard deviation | `STDDEV_SAMP`, `STDDEV_POP` |
| Analyze query execution plan | `EXPLAIN (ANALYZE, BUFFERS)` |

## 30. Checklist Before Deploying Analytical Queries

| Question | Why Answer It? |
| --- | --- |
| What type are the raw values? | Avoid invalid comparisons between text and numeric/date |
| Is formatting used only for display? | Avoid storing formatted numbers/dates as primary sources |
| Can imported data be malformed? | Prevent a single failed cast from breaking the whole pipeline |
| Are locale and decimal separators aligned? | Prevent misparsing money |
| Is the timestamp `timestamp` or `timestamptz`? | Avoid wrong time zones and shifted report dates |
| Are time interval bounds `[start,end)` clear? | Avoid missing or double-counting boundary events |
| What does `NULL` mean? | Distinguish missing data from 0 |
| Does one output row represent an order, customer, or label? | Prevent inflated aggregates after joins |
| What is the denominator of ratios/averages? | Avoid syntactically valid yet business-wrong metrics |
| Does window `ORDER BY` include a tie-breaker? | Keep ranking and `LAG` deterministic |
| Does the window frame match the intent? | Prevent wrong `LAST_VALUE` or running totals |
| Need performance tuning for large tables? | Check indexes, expressions, `EXPLAIN`, and memory |
| Does dynamic SQL use parameter binding? | Prevent quoting bugs and SQL injection |

## 31. Summary

In PostgreSQL, **formatting**, **type conversion**, and **data analysis** are three distinct steps that frequently appear together in one SQL query.

**Formatting** with `to_char`, `format`, or string functions produces human-readable strings. Formatted values are **`text`**, so never use them instead of raw numbers or timestamps in critical calculations or comparisons.

**Type conversion** via `CAST`/`::`, `to_date`, `to_timestamp`, or `to_number` brings data into the proper type for processing. Casts can fail, round, or depend on templates/time zones; untrusted input must be validated with explicit error-handling policies.

**Data analysis** with aggregates, `FILTER`, window functions, percentiles, and temporal functions enables conditional reporting, cross-row comparisons, running totals, and distribution metrics. Results are only right when you define the exact row set, grain, time bounds, denominators, and `NULL` semantics.

Maintain the discipline: **store the right data types — clean and validate before casting — compute on typed values — format at the final step — verify results against business semantics and query plans**. That foundation keeps PostgreSQL queries readable, accurate, and scalable as data grows.
