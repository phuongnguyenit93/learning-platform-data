# Explicit Casting, Type Inference, and Implicit Conversion in PostgreSQL

PostgreSQL is a database management system with a **strictly typed system**. Every column, function result, operator, and SQL expression has a definite data type. When components with different types appear within the same expression, PostgreSQL must determine the result type, resolve a matching operator or function, or convert values to the type required by the context.

For example, the expression `5 / 2` yields a different result from `5::numeric / 2`; the string `'2026-11-14'` may be interpreted as a date, text, or another type depending on context; a Java parameter sent as `text` is not necessarily converted implicitly to `uuid`. Failing to understand these mechanics can cause query errors, incorrect rounding, altered time semantics, and prevent PostgreSQL from selecting the intended operator.

This lesson distinguishes three mechanisms:

1. **Explicit casting:** the developer specifies the target type using `CAST(... AS ...)` or `::`.
2. **Type inference and type resolution:** PostgreSQL determines the type of literals, parameters, operators, functions, or multi-branch expressions from context.
3. **Implicit conversion (implicit cast):** PostgreSQL automatically applies a **permitted** type conversion to make an expression or assignment valid.

Not every pair of types can be converted, and not every conversion is safe or preserves data intact.

## 1. Distinguishing Data Type from Textual Representation

Suppose you see three `42` values in a SQL query:

```sql
SELECT
    42 AS number_value,
    '42' AS string_literal,
    '42'::integer AS explicitly_typed_integer;
```

Although a client tool may render them similarly, their type semantics differ:

- `42` is a numeric literal without a decimal point; PostgreSQL generally selects `integer` when the value fits in range, and `bigint` or `numeric` if larger.
- `'42'` is an **untyped string literal** (`unknown` during parsing). PostgreSQL can adopt the type dictated by context, or resolve it to `text` when no other context applies.
- `'42'::integer` forces PostgreSQL to parse the string contents using the input syntax of the `integer` type.

You can observe resolved types using the `pg_typeof` function:

```sql
SELECT
    pg_typeof(42) AS type_a,
    pg_typeof(42.0) AS type_b,
    pg_typeof('42'::integer) AS type_c,
    pg_typeof('42'::text) AS type_d;
```

The expected results are `integer`, `numeric`, `integer`, and `text` respectively. When a literal does not yet have an assigned type, PostgreSQL performs an extra resolution step in the query context; therefore, do not look at single quotes in SQL and assume the result is always `text`.

### Type Categories That Frequently Require Conversion

| Category | PostgreSQL Examples | Key Considerations |
| --- | --- | --- |
| Integers | `smallint`, `integer`, `bigint` | Value range limits, integer division |
| Exact numeric | `numeric`, `decimal` | Preserves decimal precision, can enforce precision and scale |
| Floating-point | `real`, `double precision` | Subject to binary representation error |
| Character strings | `text`, `varchar`, `char` | Distinguish input data from identifiers and literals |
| Boolean | `boolean` | `TRUE`, `FALSE`, `NULL`; do not treat arbitrary numbers as Boolean |
| Date/time | `date`, `time`, `timestamp`, `timestamptz` | Time zones and instants carry distinct meanings |
| Identifiers | `uuid` | Strict input syntax and dedicated binary representation |
| Structured types | `json`, `jsonb`, array, composite | Not every cast is equivalent to parsing internal structure |
| User-defined types | enum, domain, user-defined types | Custom conversion rules and constraints |

Two expressions that look identical in text may not be equivalent as data. For example, `'false'::text` is still a string, whereas `'false'::boolean` is the Boolean false value.

## 2. Explicit Casting: CAST and the :: Operator

Two common syntaxes:

```sql
CAST(expression AS target_type)

expression::target_type
```

`CAST` is standard SQL syntax and offers better portability across database engines. `::` is PostgreSQL's concise shorthand, widely used in PostgreSQL queries and `psql` examples.

Examples:

```sql
SELECT CAST('42' AS integer) AS via_cast;
SELECT '42'::integer AS via_colon;

SELECT CAST('129.75' AS numeric(10, 2));
SELECT '2026-11-14'::date;
SELECT 'true'::boolean;
```

Both forms require a valid conversion path to the target type. Casting **is not guaranteed to always succeed**:

```sql
-- Error: invalid input syntax for type integer.
SELECT 'forty two'::integer;

-- Error: exceeds integer range.
SELECT '999999999999999999999'::integer;
```

In real queries, if a column holds unvalidated input strings, inspect or sanitize the data before casting. A conversion error on any single row can abort the entire statement.

### 2.1. CAST Is Not Only for Strings

```sql
SELECT
    12::numeric(10, 2) AS amount,
    1::double precision / 4 AS fraction,
    123::text AS number_as_text;
```

Meaning:

- `12::numeric(10, 2)` produces a decimal value with scale 2.
- `1::double precision / 4` performs division in a floating-point context.
- `123::text` converts a number to its text representation.

Avoid overusing casts to `text` merely to make two values comparable. Turning numeric identifiers into text can change sort order, comparison behavior, and index usability.

### 2.2. Casting Inside Complex Expressions

```sql
SELECT
    (15 + 5)::numeric / 3 AS average_value,
    ('250.00'::numeric(12, 2) * 0.08)::numeric(12, 2) AS tax,
    CAST((3 + 2) AS text) || ' items' AS label;
```

Use parentheses to make clear which subexpression is being cast. With `::`, distinguish casting an entire expression from casting individual operands, especially when combining arithmetic operators, functions, and extension-defined operators.

## 3. Same Numbers, Different Results: Integer Division vs. Decimal Division

A classic example:

```sql
SELECT
    5 / 2 AS integer_division,
    5::numeric / 2 AS numeric_division,
    5 / 2.0 AS numeric_literal_division;
```

Results:

| Expression | Result | Explanation |
| --- | --- | --- |
| `5 / 2` | `2` | Both operands are integers; fractional part is discarded by integer division |
| `5::numeric / 2` | `2.5` | One operand is `numeric`, so the operation resolves accordingly |
| `5 / 2.0` | `2.5` | The literal `2.0` is normally parsed as `numeric` |

For negative numbers, PostgreSQL integer division truncates the remainder **toward zero**; for example, `-5 / 2` yields `-2`.

A common mistake when computing percentages:

```sql
-- Ratio loses its fractional part before multiplying by 100.
SELECT 3 / 10 * 100 AS wrong_percentage;

-- Cast before dividing to preserve the fractional part.
SELECT 3::numeric / 10 * 100 AS correct_percentage;
```

The first expression yields `0`; the second yields `30` using exact arithmetic. If you want two decimal places:

```sql
SELECT round(3::numeric / 10 * 100, 2) AS percentage;
```

### 3.1. Rounding and Overflow Are Consequences of Casting

```sql
SELECT
    12.7::integer AS rounded_integer,
    12.345::numeric(6, 2) AS rounded_decimal;
```

Casting from a `numeric` with fractional digits to an integer type in PostgreSQL rounds according to cast rules rather than truncating like integer division. Thus `12.7::integer` yields `13`, and `12.345::numeric(6,2)` yields `12.35`.

If you want a specific business rounding strategy, express it explicitly with functions such as `round`, `trunc`, `floor`, or `ceil` before casting. Choose `numeric` for monetary amounts requiring decimal exactness; do not default to `double precision` for money.

Casting to a smaller type can also cause **overflow**:

```sql
-- 40000 exceeds smallint bounds.
SELECT 40000::smallint;
```

This error signals that data violated the target type's contract. Do not blindly replace every overflow with `0` or `NULL` without an explicit business decision.

## 4. Unknown Literals: Why Can a String Become a Number or Date?

In PostgreSQL, a literal written in single quotes without an explicit cast initially has the placeholder type `unknown`. The SQL parser uses surrounding context to decide how that literal should be interpreted.

Examples:

```sql
SELECT 1 = '1' AS numbers_match;

SELECT DATE '2026-11-14' + INTERVAL '1 day' AS next_day;

SELECT '2026-11-14'::date AS explicit_date;
```

In `1 = '1'`, PostgreSQL selects the integer equality operator and interprets the literal `'1'` as an integer. That **does not mean** a column declared as `text` will automatically cast implicitly to integer in every comparison.

Distinguish two situations:

```sql
-- Untyped literal: context can resolve it to integer.
SELECT 10 = '10';

-- Value already typed as text: does not rely on unknown-literal resolution.
SELECT 10 = '10'::text;
```

The second expression fails because there is no matching `integer = text` operator. To compare meaningfully, specify the intended conversion explicitly:

```sql
SELECT 10 = ('10'::text)::integer;

-- Or if the actual intent is string comparison:
SELECT 10::text = '10'::text;
```

Both comparisons above may return the same result on sample inputs, yet their semantics differ: numeric comparison treats `'010'` and `'10'` as equal, whereas text comparison distinguishes them.

### 4.1. Typed Literals

PostgreSQL also supports prefixing a type name before a string literal:

```sql
SELECT DATE '2026-11-14';
SELECT TIMESTAMP '2026-11-14 09:30:00';
SELECT TIMESTAMPTZ '2026-11-14 09:30:00+07';
SELECT INTERVAL '2 days';
```

This constructs a literal with an explicit type, very helpful for date/time comparisons and avoiding reliance on type inference.

An invalid date format literal still fails:

```sql
SELECT 'not-a-date'::date;
```

Ambiguous date formats can be affected by `DateStyle`. Use ISO format `YYYY-MM-DD` or ISO timestamps with explicit offsets to reduce environment dependency.

## 5. Implicit Conversion: What Is PostgreSQL Allowed to Do Automatically?

There are cases where PostgreSQL converts one type to another without requiring `CAST` in SQL. For instance, in an arithmetic expression combining an integer and a `numeric`, the system selects the appropriate operator and widens the integer so fractional precision is preserved.

```sql
SELECT
    2 + 0.5 AS result,
    pg_typeof(2 + 0.5) AS result_type;
```

The result has type `numeric`. However, you must not infer that every `text` converts automatically to `integer` or every `jsonb` converts automatically to `text`.

PostgreSQL distinguishes cast contexts:

| Context | Meaning | Illustrative Example |
| --- | --- | --- |
| **Implicit** | Can be applied automatically during expression, function, and operator resolution | Certain promotions among numeric types |
| **Assignment** | Permitted when assigning/writing to a target column, in addition to explicit contexts | Converting compatible values to a column's type in `INSERT`/`UPDATE` |
| **Explicit only** | Permitted only when the SQL author explicitly requests a cast | Conversions that may lose semantics or require deliberate intent |

These are **permission levels for conversions**, not a guarantee that PostgreSQL will always pick a given cast in every expression. The resolver also weighs candidate functions/operators, preferred types, parameter types, and specific selection rules.

### 5.1. Why Are Implicit Conversions Restricted?

If the database automatically coerced every text value to a number, expressions like `'001' = 1` could conflate string codes with numeric quantities. If it automatically coerced text to dates, malformed strings or ambiguous formats would trigger unpredictable failures. Limiting implicit casts prevents wrong operator choices and silent data loss.

An example contrasting literals and columns:

```sql
CREATE SCHEMA IF NOT EXISTS cast_lab;

CREATE TABLE cast_lab.imported_values (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    raw_code text NOT NULL
);

INSERT INTO cast_lab.imported_values(raw_code)
VALUES ('10'), ('010'), ('not_a_number');

-- Valid text comparison:
SELECT * FROM cast_lab.imported_values
WHERE raw_code = '10';
```

If you try to interpret all of `raw_code` as numbers, `raw_code::integer` fails on the `'not_a_number'` row. That is a **data quality** issue, not just missing cast syntax.

### 5.2. Inspecting Registered Casts via pg_cast

PostgreSQL provides the `pg_cast` catalog storing registered type conversions. Example:

```sql
SELECT
    c.castsource::regtype AS source_type,
    c.casttarget::regtype AS target_type,
    CASE c.castcontext
        WHEN 'i' THEN 'implicit'
        WHEN 'a' THEN 'assignment'
        WHEN 'e' THEN 'explicit'
    END AS cast_context,
    CASE c.castmethod
        WHEN 'f' THEN 'function'
        WHEN 'i' THEN 'input/output'
        WHEN 'b' THEN 'binary-compatible'
    END AS cast_method
FROM pg_cast AS c
WHERE c.castsource = 'integer'::regtype
   OR c.casttarget = 'integer'::regtype
ORDER BY source_type::text, target_type::text;
```

The `castcontext` column uses codes `i`, `a`, `e`. The `castmethod` column indicates how the conversion works: function call, I/O conversion, or binary-compatible cast.

**Important caveat:** `pg_cast` does not list every possible conversion PostgreSQL can perform. For instance, certain conversions to/from string types, domains, and composite types are handled via special rules. Therefore, finding no row in `pg_cast` does not automatically prove no conversion path exists.

### 5.3. A Valid Cast Path Does Not Mean Every Value Is Valid

```sql
SELECT '123'::integer;      -- Succeeds
SELECT '12.3'::integer;     -- Integer syntax error
SELECT 'true'::boolean;     -- Succeeds
SELECT 'perhaps'::boolean;  -- Boolean syntax error
```

Input conversions depend on the actual runtime data. A query that parses cleanly does not guarantee every value in a table will cast without error.

## 6. Type Inference in Operators and Function Calls

PostgreSQL supports **overloaded** operators and functions: the same name accepting different parameter type combinations.

```sql
SELECT 7 + 5;
SELECT 7::numeric + 5;
SELECT 7::double precision + 5::double precision;
```

The `+` operator is chosen based on operand types and applicable conversions. The same mechanism applies to functions.

### 6.1. The round Function and numeric vs. double precision

```sql
SELECT round(12.345::numeric, 2) AS rounded_amount;

-- Single-argument form for double precision is available:
SELECT round(12.345::double precision);
```

PostgreSQL provides `round(numeric, integer)` to specify decimal places, but does not provide an identical two-argument `round(double precision, integer)` signature in its standard built-in set.

```sql
-- Cannot resolve round(double precision, integer).
SELECT round(12.345::double precision, 2);

-- Explicitly convert to numeric if scale rounding is genuinely intended:
SELECT round(12.345::double precision::numeric, 2);
```

Converting from floating-point to `numeric` converts only the value already approximated at double precision; it cannot "recover" lost decimal digits if prior floating-point rounding already occurred.

### 6.2. Querying pg_typeof to Observe Resolution Results

```sql
SELECT
    pg_typeof(7 + 5) AS integer_math,
    pg_typeof(7 + 0.5) AS numeric_math,
    pg_typeof(7::double precision + 0.5::double precision)
        AS floating_math;
```

This is a direct hands-on way to observe type resolution outcomes. Whenever a function returns an unexpected type, inspect each argument's type before adding arbitrary casts.

### 6.3. Ambiguous Function/Operator Errors

If multiple function or operator overloads appear equally plausible and the system cannot pick a unique candidate under resolution rules, PostgreSQL raises an error such as **function ... is not unique** or **operator is not unique**.

The fix is usually to cast one or more arguments to the exact type you intend. Choose based on business semantics and the function signature rather than guessing casts at random until the error disappears.

For example, if an application function has overloads for `integer`, `numeric`, and `text`, passing an untyped parameter can make selection ambiguous. Write `my_function($1::numeric)` when the input is truly a decimal number.

## 7. Type Inference for CASE, COALESCE, UNION, and VALUES

Expressions that can return values from multiple branches must choose **one unified result type**. PostgreSQL applies type compatibility and selection rules; simply having `text` somewhere does not automatically convert every other branch to text.

### 7.1. CASE

```sql
SELECT
    CASE
        WHEN TRUE THEN 10
        ELSE 12.5
    END AS chosen_value;
```

The result has type `numeric` because the numeric branches unify under that type.

```sql
SELECT pg_typeof(
    CASE WHEN TRUE THEN 10 ELSE 12.5 END
);
```

If branches return incompatible types, resolution fails:

```sql
-- Do not assume integer and explicitly typed text
-- will automatically unify based on display formatting.
SELECT CASE WHEN TRUE THEN 1 ELSE 'abc'::text END;
```

When you want the expression to return text, cast explicitly:

```sql
SELECT
    CASE
        WHEN TRUE THEN 1::text
        ELSE 'abc'::text
    END AS display_value;
```

Note: types are resolved at **SQL parse/analysis time**, not deferred until a branch executes at runtime. You cannot use `CASE` to hide a branch with an incompatible type and hope PostgreSQL skips resolving it.

### 7.2. COALESCE

`COALESCE` returns the first non-`NULL` argument, yet all arguments must still share a **unified result type**:

```sql
SELECT
    COALESCE(NULL, 10, 12.5) AS value,
    pg_typeof(COALESCE(NULL, 10, 12.5)) AS value_type;
```

`value_type` is `numeric` in the example above. An untyped `NULL` adopts the type resolved from the remaining arguments.

If extracting a numeric value from text, cast deliberately:

```sql
SELECT COALESCE(NULLIF('42', '')::integer, 0);
```

`NULLIF('42', '')` returns text `'42'`; casting to `integer` aligns it with the fallback `0`. If the string is non-empty and non-numeric, the cast still fails.

### 7.3. UNION and UNION ALL

Corresponding columns across `UNION` branches must have compatible types:

```sql
SELECT 10 AS amount
UNION ALL
SELECT 20.5 AS amount;
```

The result type is `numeric`. With untyped string literals:

```sql
SELECT 'alpha' AS code
UNION ALL
SELECT 'beta' AS code;
```

The result column resolves to `text` when all branches supply unknown string literals.

When chaining multiple `UNION` clauses, PostgreSQL resolves types pairwise across the expression tree. An intermediate branch containing only `NULL`/unknown may resolve to `text` before reaching an `integer` branch later, causing a mismatch error. Use explicit casts in the earlier branches when all rows share a specific type:

```sql
SELECT NULL::integer AS score
UNION ALL
SELECT NULL::integer
UNION ALL
SELECT 5;
```

### 7.4. VALUES and INSERT

A multi-row `VALUES` clause must also unify types per column position:

```sql
SELECT *
FROM (VALUES (1), (2.5), (3)) AS v(amount);
```

In `INSERT`, the **target column types** provide assignment context:

```sql
CREATE TABLE cast_lab.payments (
    payment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    amount numeric(12, 2) NOT NULL,
    paid boolean NOT NULL DEFAULT FALSE,
    paid_on date
);

INSERT INTO cast_lab.payments (amount, paid, paid_on)
VALUES ('150.75', 'true', '2026-11-14');
```

The untyped string literals are interpreted according to the target column types: `numeric`, `boolean`, and `date`. Do not assume that replacing those literals with **JDBC parameters explicitly typed as text** will undergo the same implicit conversion on assignment.

### 7.5. ARRAY

A PostgreSQL array has a definite element type:

```sql
SELECT ARRAY[1, 2, 3]::integer[] AS integer_array;
SELECT ARRAY['a', 'b', 'c']::text[] AS text_array;
```

Elements of incompatible types cause the array expression to fail. When you need an array of identifiers, specify the exact type such as `uuid[]` or `bigint[]` instead of converting everything to text.

## 8. NULL and Unknown Types

`NULL` represents the absence of a SQL value. An uncast `NULL` normally infers its type from context, for example:

```sql
SELECT COALESCE(NULL, 100::bigint);
SELECT NULL::date;
SELECT NULL::uuid;
```

`NULL::date` and `NULL::uuid` are both `NULL`, yet they belong to **different types**. That distinction matters in overloaded functions, `UNION`, and nullable parameters.

Example:

```sql
SELECT
    pg_typeof(NULL::integer) AS integer_null,
    pg_typeof(NULL::text) AS text_null,
    pg_typeof(NULL::boolean) AS boolean_null;
```

Remember that `NULL` is never treated as `0`, `FALSE`, or an empty string. Casting `NULL` to a target type only gives a type to the missing value; it never creates data.

### 8.1. Do Not Assume NULL Skips Broken Casts

```sql
SELECT COALESCE(NULLIF('', '')::integer, 0); -- 0
```

However:

```sql
SELECT COALESCE(NULLIF('bad', '')::integer, 0);
```

fails because `'bad'::integer` is invalid. `COALESCE` only handles `NULL` after the cast expression succeeds; it is not an error-catching mechanism for failed conversions.

For unvalidated input, enforce acceptance checks, sanitize at the ingestion boundary, or handle errors in the application/ETL pipeline. Even a regex checking digits alone does not guarantee the value fits inside the target integer range.

## 9. Converting Between date, timestamp, and timestamptz

This is the area where explicit, deliberate casting matters most in many applications.

PostgreSQL distinguishes:

- `date`: calendar date, with no time of day or time zone.
- `time without time zone`: time of day with no time zone.
- `timestamp without time zone`: "local" date and time without identifying a time zone or a unique UTC instant.
- `timestamp with time zone` (`timestamptz`): represents an **instant in time**, interpreted using the session time zone when input lacks an offset and displayed in the session time zone.

Examples:

```sql
SELECT
    '2026-11-14'::date AS calendar_day,
    '2026-11-14 09:00:00'::timestamp AS local_datetime,
    '2026-11-14 09:00:00+07'::timestamptz AS instant;
```

A `timestamptz` value is stored and compared as an absolute point in time; only its formatted display changes when a session alters `TimeZone`.

```sql
BEGIN;
    SET LOCAL TIME ZONE 'UTC';

    SELECT '2026-11-14 09:00:00+07'::timestamptz AS utc_display;
COMMIT;
```

Displayed in UTC, that instant corresponds to `2026-11-14 02:00:00+00`.

### 9.1. Timezone-Naive Data Does Not Automatically Become an Accurate Instant

```sql
SELECT '2026-11-14 09:00:00'::timestamp;
```

The value above does not say whether it means 9 AM in Vietnam or UTC. If you cast `timestamp without time zone` to `timestamptz`, PostgreSQL interprets it in the session time zone unless another zone is specified.

If the data represents local wall-clock time in a known city, specify the zone explicitly:

```sql
SELECT
    '2026-11-14 09:00:00'::timestamp
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS instant;
```

That expression converts a local time in a known zone to the corresponding `timestamptz`. Conversely, applying `AT TIME ZONE` to a `timestamptz` yields a `timestamp without time zone` showing local wall-clock time in the chosen zone.

Converting back and forth without clarifying business intent can shift timestamps by hours, especially in time zones observing daylight saving time.

### 9.2. Casting to date Discards the Time Component

```sql
SELECT '2026-11-14 14:30:00'::timestamp::date AS only_date;
```

The `date` result retains only the calendar date. For `timestamptz::date`, **the calendar date depends on the session time zone**, meaning the same instant can appear as two different calendar dates in two time zones.

When a Java application uses `LocalDate`, `LocalDateTime`, or `OffsetDateTime`/`Instant`, map each to the semantically matching PostgreSQL type. `LocalDateTime` carries no offset and should not replace `Instant` when tracking global instants.

## 10. Casting with UUID

PostgreSQL has a dedicated `uuid` type:

```sql
SELECT
    '550e8400-e29b-41d4-a716-446655440000'::uuid AS user_id;
```

Invalid formats fail:

```sql
SELECT 'user-123'::uuid;
```

Suppose we have a table:

```sql
CREATE TABLE cast_lab.users (
    user_id uuid PRIMARY KEY,
    username text NOT NULL UNIQUE
);

INSERT INTO cast_lab.users (user_id, username)
VALUES (
    '550e8400-e29b-41d4-a716-446655440000',
    'learner'
);
```

The string in `INSERT` is an untyped literal taking context from the `uuid` column. For client parameters already typed as `text`, pass a proper UUID value or cast explicitly in the appropriate place:

```sql
SELECT *
FROM cast_lab.users
WHERE user_id = '550e8400-e29b-41d4-a716-446655440000'::uuid;
```

**Do not** cast `user_id::text` in predicates just to compare against a text parameter. That wraps the column in an expression, can prevent direct use of the standard B-tree index on `user_id`, and hides the fact that the application is binding the wrong type. Binding parameters with the proper `uuid` type is far better.

## 11. Casting with JSON and JSONB

`jsonb` holds structured data. The two operations below have different meanings:

```sql
SELECT
    '{"quantity": 3}'::jsonb AS parsed_json,
    '{"quantity": 3}'::text AS plain_text;
```

The first value is parsed by PostgreSQL into valid JSONB; the second is merely a character string. Malformed JSON is rejected when cast to `jsonb`:

```sql
SELECT '{quantity:3}'::jsonb;
```

### 11.1. -> and ->> Differ in Result Type

```sql
SELECT
    pg_typeof(('{"quantity":3}'::jsonb -> 'quantity'))
        AS jsonb_result,
    pg_typeof(('{"quantity":3}'::jsonb ->> 'quantity'))
        AS text_result;
```

`->` returns a `jsonb` value, whereas `->>` extracts the value as `text`. When using extracted values in arithmetic, cast only when you know the format is valid:

```sql
SELECT
    (('{"quantity":3}'::jsonb ->> 'quantity')::integer * 10)
        AS total_units;
```

If a JSONB document contains `{"quantity":"many"}`, casting to integer will fail. Therefore, storing clean types upfront and validating payloads at ingestion boundaries is essential.

### 11.2. JSON null Is Not SQL NULL

```sql
SELECT
    jsonb_typeof('{"flag":null}'::jsonb -> 'flag') AS json_null_type,
    jsonb_typeof('{}'::jsonb -> 'flag') AS missing_type;
```

The first result is the string `'null'`; the second is SQL `NULL` because the key does not exist. Conversions from JSONB to text or Boolean must account for missing keys, JSON `null`, and unexpected value types.

### 11.3. Converting a Number to JSONB Is Not Just Formatting

```sql
SELECT
    to_jsonb(42) AS json_number,
    to_jsonb('42'::text) AS json_string;
```

The first is the JSON number `42`; the second is the JSON string `"42"`. They look similar at a glance, yet differ in JSON type and comparison behavior.

## 12. Casting text, varchar, char, and Length Limits

`text` and `varchar` are broadly interchangeable in text queries. `varchar(n)` enforces a maximum length, while `char(n)` has space-padding semantics.

```sql
SELECT
    'hello'::text AS a,
    'hello'::varchar(10) AS b,
    'AB'::char(5) AS c;
```

Explicitly casting to `varchar(n)` or `char(n)` truncates strings exceeding the limit according to PostgreSQL cast rules. By contrast, when **assigning to a table column** with a declared length, values exceeding the limit are normally rejected, except in special cases involving trailing spaces.

```sql
SELECT 'abcdef'::varchar(3) AS shortened;
```

The explicit cast output is truncated to `abc`. This is an intentional **lossy truncation** on cast and should not be used as a default sanitization strategy.

When limiting user input length, validate before saving and return a clear error instead of relying on silent cast truncation.

### 12.1. The String Concatenation Operator ||

```sql
SELECT 'Order #' || 123::text AS label;
```

PostgreSQL also provides `||` overloads that accept certain non-text operands. However, when expressions involve multiple types or custom types, explicit casts make code clearer and less sensitive to overload resolution.

Another mistake is casting numbers to text before ordering or comparing:

```sql
SELECT '10'::text < '2'::text AS lexical_comparison;
SELECT 10 < 2 AS numeric_comparison;
```

Collation-based text comparison can produce the opposite result of numeric comparison. Never convert numeric columns to text when the intent is mathematical comparison.

## 13. Assignment Casts When Writing to Table Columns

During `INSERT` or `UPDATE`, PostgreSQL ensures assigned expressions match the target column types.

```sql
CREATE TABLE cast_lab.measurements (
    measurement_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reading numeric(10, 2) NOT NULL,
    recorded_on date NOT NULL
);

INSERT INTO cast_lab.measurements (reading, recorded_on)
VALUES ('12.45', '2026-11-14');

UPDATE cast_lab.measurements
SET reading = 15
WHERE measurement_id = 1;
```

Untyped literals or integers convert smoothly in the assignment context of a `numeric(10,2)` column. However, assignment cast rules do not mean invalid values are ignored:

```sql
-- This statement fails because the string is not a valid number.
INSERT INTO cast_lab.measurements (reading, recorded_on)
VALUES ('not-a-number', '2026-11-14');
```

`numeric(10,2)` also enforces total precision and scale rounding. SQL types are part of the data contract between the application and the database, not merely storage hints.

### 13.1. DEFAULT Is Not an Implicit Cast

```sql
CREATE TABLE cast_lab.jobs (
    job_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    enabled boolean NOT NULL DEFAULT TRUE
);
```

`DEFAULT TRUE` applies when the `enabled` column is omitted or the `DEFAULT` keyword is used. Its job is not to convert `NULL`, `''`, or a mismatched value into `TRUE`. Default substitution and type casting are two distinct mechanisms.

### 13.2. CHECK, Domains, and Enums

A column or domain can attach extra constraints after type resolution:

```sql
CREATE DOMAIN cast_lab.positive_amount AS numeric(12, 2)
    CHECK (VALUE >= 0);

CREATE TABLE cast_lab.invoices (
    invoice_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    amount cast_lab.positive_amount NOT NULL
);

INSERT INTO cast_lab.invoices(amount) VALUES (125.00);
```

Casting or writing a value into a domain must also satisfy the domain's constraints (where checked). Do not cast down to the base type to deliberately bypass data integrity rules required by the system.

For enums:

```sql
CREATE TYPE cast_lab.order_status AS ENUM
    ('draft', 'submitted', 'approved');

CREATE TABLE cast_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status cast_lab.order_status NOT NULL DEFAULT 'draft'
);
```

The literal `'submitted'` can be inferred as the enum type when the column provides context, yet a `text` column does not automatically turn into `cast_lab.order_status` in arbitrary expressions. To convert a validated text value to an enum:

```sql
SELECT 'submitted'::text::cast_lab.order_status;
```

If the string does not match an enum label, PostgreSQL raises an error. Casting never creates new enum labels.

## 14. Parameter Types in SQL and Java/JDBC

Many production bugs only surface when SQL literals are replaced with prepared statement parameters from an application.

### 14.1. PREPARE Can Specify Parameter Types

In `psql`:

```sql
PREPARE find_payment(numeric) AS
SELECT payment_id, amount
FROM cast_lab.payments
WHERE amount >= $1;

EXECUTE find_payment(100.00);
DEALLOCATE find_payment;
```

Parameter `$1` is declared as `numeric`, allowing PostgreSQL to pick the matching `numeric` comparison operator.

If parameter types are left unspecified, PostgreSQL attempts to infer them from context; when context is missing or ambiguous, preparing the statement can fail.

```sql
PREPARE echo_integer(integer) AS
SELECT $1 + 1;

EXECUTE echo_integer(41);
DEALLOCATE echo_integer;
```

Here the result is `42`, and the parameter signature is unambiguous.

### 14.2. Passing the Right Types from JDBC to the Database

Given `cast_lab.users(user_id uuid, username text)`, JDBC code should pass a `UUID` object:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;

public String loadUsername(Connection connection, String rawId)
        throws SQLException {
    UUID userId = UUID.fromString(rawId);

    String sql = """
        SELECT username
        FROM cast_lab.users
        WHERE user_id = ?
        """;

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        ps.setObject(1, userId);

        try (ResultSet rs = ps.executeQuery()) {
            return rs.next() ? rs.getString("username") : null;
        }
    }
}
```

`UUID.fromString` validates input syntax before sending it to the database; PostgreSQL still validates the `uuid` type and constraints. If `rawId` is malformed, Java throws `IllegalArgumentException`, which should be translated at the API boundary into an appropriate error response.

A common mistake is binding a `varchar` string and expecting PostgreSQL to coerce it automatically to `uuid` in `WHERE user_id = ?`. Depending on the driver and binding mode, the expression can fail with an operator-not-found error. Choosing the matching Java/SQL type upfront—or casting explicitly when unavoidable—is far clearer.

### 14.3. SQL CAST for Parameters Passed as Strings

In some integrations, the client genuinely only holds a string parameter and SQL needs to dictate how to parse it:

```sql
-- In a JDBC PreparedStatement, ? is a placeholder bound by the driver:
SELECT username
FROM cast_lab.users
WHERE user_id = CAST(? AS uuid);
```

This makes semantics clear, though malformed values still trigger a PostgreSQL error. Never build SQL via string concatenation:

```java
// Avoid constructing SQL from user input like this:
String sql = "SELECT username FROM cast_lab.users WHERE user_id = '"
    + rawId + "'::uuid";
```

String concatenation invites SQL injection and blurs the boundary between SQL code and data. Always use `PreparedStatement` and placeholders.

### 14.4. NULL Parameters Need a Type

`PreparedStatement.setNull` requires a SQL type code:

```java
import java.sql.Types;

// Example for a nullable integer column:
ps.setNull(1, Types.INTEGER);
```

For `uuid` or PostgreSQL-specific types, binding depends on the JDBC driver; use `setObject` with the matching Java type when non-null, or apply an explicit cast on the placeholder when passing null if needed.

When receiving a `null` without clear surrounding context, the server may be unable to infer the parameter type. Consequently, parameter typing is especially important for overloaded functions, `CASE`, `IS NULL` clauses, and dynamic SQL.

## 15. Impact of CAST on Indexes and Execution Plans

Casting correctly preserves query meaning, yet where a cast is placed changes the expression the planner must evaluate.

Suppose `cast_lab.users.user_id` is `uuid PRIMARY KEY`, so PostgreSQL already maintains a B-tree index on it:

```sql
-- Comparing with a properly typed value: matches the index on user_id.
SELECT *
FROM cast_lab.users
WHERE user_id = '550e8400-e29b-41d4-a716-446655440000'::uuid;
```

If you cast **the column** to text:

```sql
SELECT *
FROM cast_lab.users
WHERE user_id::text = '550e8400-e29b-41d4-a716-446655440000';
```

the predicate becomes an expression on the column. The regular B-tree index on `user_id` is no longer directly usable for `user_id::text` in the same way as equality on `uuid`. Furthermore, text comparison semantics differ from UUID comparison.

On a text column storing numbers:

```sql
CREATE TABLE cast_lab.legacy_prices (
    row_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    raw_amount text NOT NULL
);
```

Query:

```sql
SELECT *
FROM cast_lab.legacy_prices
WHERE raw_amount::numeric > 100;
```

forces PostgreSQL to parse every row's value as a number before comparing, and fails if any row contains a malformed string. A regular B-tree index on `raw_amount` is not equivalent to an index on the expression `raw_amount::numeric`.

**The best fix is usually correcting the column's data type design**—for instance using `numeric` for money, `date` for dates, and `uuid` for UUIDs. Expression indexes can help during transitional migrations, but creating an index on a failing cast over dirty data will also fail, and indexes cannot fix a broken data model.

### 15.1. Checking EXPLAIN on Representative Data

```sql
EXPLAIN
SELECT *
FROM cast_lab.users
WHERE user_id = '550e8400-e29b-41d4-a716-446655440000'::uuid;
```

`EXPLAIN` shows which scan/index the planner expects to use. `EXPLAIN (ANALYZE, BUFFERS)` actually executes the query to gather runtime statistics, so use it only on appropriate queries and environments. On very small tables, PostgreSQL may pick a sequential scan even when an index exists; do not conclude an index is broken from a plan on a handful of rows.

## 16. Why You Should Not Use Casts to Hide a Flawed Data Model

A table with an `amount_text text` column storing every price as a string might seem to "work" by adding `amount_text::numeric` in every report. However:

- Any malformed value can crash queries.
- Every calculation must repeat the cast.
- Sorting or comparing text can produce mathematically wrong results whenever someone forgets to cast.
- Text indexes and planner statistics poorly reflect true numeric distributions.
- Data updates and validation become fragile and complex.

PostgreSQL data types exist for clear purposes: `numeric` for exact quantities, `date` for dates, `timestamptz` for instants, `uuid` for IDs, `boolean` for true/false, `jsonb` for JSON structures. Convert data at the **ingestion boundary** and store the proper type as early as possible.

### 16.1. Migrating from text to the Proper Type

Suppose a legacy table `cast_lab.old_measurements` has a column `raw_reading text`. The migration process should:

1. Profile how many values are missing, blank, malformed, or out of expected bounds.
2. Define business-approved data cleaning rules.
3. Create a recoverable migration/backup and test on representative data.
4. Alter the column using `USING` once all rows are normalized.
5. Update Java/API code and remove redundant casts from queries.

Example syntax when data is already guaranteed to hold only valid numbers or empty strings:

```sql
-- Illustrative example: old_measurements table and data are prepared.
ALTER TABLE cast_lab.old_measurements
    ALTER COLUMN raw_reading TYPE numeric(12, 2)
    USING NULLIF(trim(raw_reading), '')::numeric(12, 2);
```

`USING` specifies how to compute the new column values from the old ones. If even one string like `'not-a-number'` remains, the migration fails; never arbitrarily coerce dirty strings to `0`. Altering a column's type can rewrite the table and its indexes, acquire heavy locks, and cause downtime; plan carefully for production environments.

## 17. Common Errors and How to Diagnose Them

| Symptom | Typical Cause | Resolution |
| --- | --- | --- |
| `invalid input syntax for type integer` | String is not a valid integer | Validate data, handle blank/sentinel strings, cast after cleaning |
| `integer out of range` | Value exceeds target type bounds | Pick a wider type, verify bounds and input rules |
| `operator does not exist: integer = text` | Two already-typed operands lack a matching operator or implicit cast | Pass the right type or cast explicitly with clear semantics |
| `function ... does not exist` | Function signature does not match input argument types | Check overloads and cast arguments appropriately |
| `function ... is not unique` | Multiple overloads match equally | Explicitly cast the ambiguous arguments |
| `CASE types ... cannot be matched` | Branches do not unify to a single type | Decide on a common result type and cast each branch |
| Division result drops fractional digits | Both operands are integers | Cast to `numeric` before dividing |
| Monetary calculations show rounding drift | Using `real`/`double precision` instead of exact numeric | Consider `numeric` and explicit business rounding rules |
| Timestamps off by several hours | Confusing `timestamp` and `timestamptz`, or wrong `TimeZone` | Clarify instant semantics, offsets, and time zones |
| Queries with casts run slowly | Cast applied on the column, unsuitable index, or wrong column type | Fix column typing, inspect `EXPLAIN`, consider proper indexes |
| JDBC UUID query fails | Sending a `varchar` parameter instead of `uuid` | Use `java.util.UUID` / proper parameter binding or cast placeholder |
| `COALESCE` still fails on malformed strings | The cast fails before returning a value to COALESCE | Validate/clean inputs instead of treating COALESCE as error handling |
| `UNION` with NULL and numbers fails | An intermediate branch already resolved to a different type | Type `NULL`/literals explicitly across `UNION` branches |

Start troubleshooting by inspecting **actual expression types**, column types in catalogs, and the full error message rather than scattering `::text` casts everywhere.

## 18. Combined Practice

Practice in a separate database using the `cast_lab` schema created earlier in this lesson. These examples do not require modifying or deleting production data.

### Exercise 1: Observe Literal and Arithmetic Types

```sql
SELECT
    pg_typeof(1) AS a,
    pg_typeof(1.0) AS b,
    pg_typeof(1::bigint) AS c,
    pg_typeof(1 + 2.5) AS d;

SELECT
    7 / 2 AS wrong_ratio,
    7::numeric / 2 AS correct_ratio;
```

Explain why `wrong_ratio` loses its fractional part and how to decide the desired result type.

### Exercise 2: Distinguish Unknown Literals from Typed Text

```sql
SELECT 1 = '1';

-- Try this to observe the operator resolution error:
SELECT 1 = '1'::text;

-- Use explicit numeric comparison:
SELECT 1 = ('1'::text)::integer;
```

Analyze the difference between the literal `'1'` and an expression already typed as `text`.

### Exercise 3: CAST with Currency

```sql
SELECT
    '120.456'::numeric(10, 2) AS rounded_price,
    round(120.456::numeric, 2) AS rounded_by_function;

SELECT
    3 / 8 * 100 AS integer_percentage,
    round(3::numeric / 8 * 100, 2) AS decimal_percentage;
```

Compare the results, verify how rounding behaves, and explain why you must cast before dividing.

### Exercise 4: CASE, COALESCE, and UNION

```sql
SELECT
    pg_typeof(
        CASE WHEN TRUE THEN 10 ELSE 11.5 END
    ) AS case_type,
    pg_typeof(COALESCE(NULL, 1, 2.5)) AS coalesce_type;

SELECT NULL::numeric AS amount
UNION ALL
SELECT 100::integer
UNION ALL
SELECT 200.5::numeric;
```

Try replacing one branch with `'unknown'::text` and explain why type resolution changes or fails.

### Exercise 5: Instants and Time Zones

```sql
BEGIN;
    SET LOCAL TIME ZONE 'UTC';
    SELECT
        '2026-11-14 09:00:00+07'::timestamptz AS instant_utc,
        '2026-11-14 09:00:00'::timestamp AS local_only,
        ('2026-11-14 09:00:00'::timestamp
           AT TIME ZONE 'Asia/Ho_Chi_Minh') AS local_to_instant;
COMMIT;
```

Explain why two expressions display different clock hours yet can describe the exact same instant in time.

### Exercise 6: JSONB Data and Properly Typed Parameters

```sql
SELECT
    ('{"qty":3}'::jsonb -> 'qty') AS json_value,
    ('{"qty":3}'::jsonb ->> 'qty')::integer AS integer_value;

PREPARE user_by_id(uuid) AS
SELECT username FROM cast_lab.users WHERE user_id = $1;

EXECUTE user_by_id('550e8400-e29b-41d4-a716-446655440000');
DEALLOCATE user_by_id;
```

Try changing `qty` to the string `"three"` in your lab environment to observe the cast failure, and explain how to validate errors at the input boundary.

## 19. Key Principles to Remember

- **Cast explicitly** with `CAST(expr AS type)` or `expr::type` whenever conversion intent needs to be unambiguous, especially for numbers, dates/times, UUIDs, and JSON data.
- **Type inference** happens when PostgreSQL resolves `unknown` literals, operators, functions, `CASE`, `COALESCE`, `UNION`, `VALUES`, and parameters; it is not a blanket mechanism that turns any text into any type.
- **Implicit conversion** is only permitted in specific contexts and for casts PostgreSQL allows. `pg_cast` helps inspect part of those rules, though it does not list every special conversion.
- **Types govern mathematical results**: integer division drops fractional parts; `numeric` and floating-point types have fundamentally different precision guarantees.
- **Casts can lose data or fail** due to rounding, overflow, string truncation, invalid input syntax, or time-zone semantics. Validate data before converting.
- **Store the right types from the start**. If a database stores numbers as text or instants as strings, repeated casts in queries are a signal to revisit the schema and ingestion pipeline.
- **Applications must bind parameters with proper types**. In JDBC/JPA, matching Java types to PostgreSQL types avoids operator lookup errors, avoids column-side casts, and preserves index usage.
- **Never optimize by guessing**: use `pg_typeof` to inspect expression types and `EXPLAIN` to verify execution plans when needed.

Understanding type conversion mechanics helps you write predictable SQL, protect data integrity, and clearly separate data-quality bugs from expression-resolution errors. A well-written SQL statement does more than pass on sample rows—it accurately reflects **the data types the system commits to storing and processing**.
