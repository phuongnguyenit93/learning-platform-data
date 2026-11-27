# Integers, Numeric, and Floating-Point Numbers in PostgreSQL

## 1. They Are All Numbers—Why Does PostgreSQL Need Multiple Data Types?

In PostgreSQL, values that look similar in SQL can carry very different meanings:

- `25` can be a **product quantity** and should be stored as an integer.
- `125000.50` can be a **unit price** and requires exact decimal arithmetic.
- `23.687491` can be a **temperature measured by a sensor** and accepts approximate error.
- `9000000000000000000` is a very large integer, exceeding the limit of the standard `integer` type.

PostgreSQL provides three important groups:

1. **Integers**: `smallint`, `integer`, `bigint`, storing exact whole numbers within defined ranges.
2. **Exact decimal numbers**: `numeric`, also known by its equivalent name `decimal`, suitable for monetary values and rules requiring decimal precision.
3. **Binary floating-point numbers**: `real` and `double precision`, optimized for many scientific calculations, measurements, and approximate data, but **not guaranteed to represent every decimal number exactly**.

Example of two columns:

```sql
CREATE TABLE product_metrics (
    price numeric(12,2) NOT NULL,
    measured_temperature double precision NOT NULL
);
```

A unit price must ensure that `0.10 + 0.20` in decimal arithmetic yields a result corresponding to 0.30. Sensor temperatures inherently involve device and measurement tolerances; using a floating-point type can be more suitable in terms of speed and value range.

**Choosing a numeric type is not just about saving memory.** It determines accuracy, value range, rounding behavior, overflow errors, division results, aggregation capabilities, and business consistency.

## 2. Overview Table of Numeric Types

| PostgreSQL Type | Typical Storage Size | Range / Precision | Best Suited For |
| --- | --- | --- | --- |
| `smallint` | 2 bytes | Signed integer, from −32,768 to 32,767 | Small counts when the range is truly guaranteed |
| `integer` / `int` / `int4` | 4 bytes | From −2,147,483,648 to 2,147,483,647 | Quantities, indices, many kinds of IDs |
| `bigint` / `int8` | 8 bytes | From −9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 | Large counters, long-term growing IDs |
| `numeric(p,s)` / `decimal(p,s)` | Variable | Exact decimal according to declared precision and scale | Prices, money, exact ratios |
| `numeric` without declared p/s | Variable | Exact decimal within PostgreSQL implementation limits | Calculations requiring many digits |
| `real` / `float4` | 4 bytes | Around 6 significant decimal digits | Approximate measurement data when error is acceptable |
| `double precision` / `float8` | 8 bytes | Around 15 significant decimal digits | Arithmetic calculations and measurements needing higher precision than `real` |

Two important notes:

- `smallint`, `integer`, and `bigint` are **signed integers**. PostgreSQL does not have a direct equivalent of `UNSIGNED INT` found in some other database management systems.
- `real` and `double precision` can represent very large/small value ranges, but **a wide range does not mean absolute exactness**. A value like `0.1` generally does not have an exact finite representation in base 2.

### 2.1. Type Aliases

PostgreSQL accepts multiple type names:

```sql
SELECT
    15::smallint AS small_value,
    15::integer AS integer_value,
    15::int AS int_alias,
    15::bigint AS bigint_value,
    15.25::numeric AS numeric_value,
    15.25::decimal AS decimal_alias,
    15.25::real AS real_value,
    15.25::double precision AS double_value;
```

`decimal` is essentially an equivalent spelling of `numeric` in PostgreSQL. For floating-point numbers, `float4` is an alias for `real` and `float8` is an alias for `double precision`. These aliases are convenient when reading catalogs or legacy code, but when designing lessons or schemas, prefer clear names such as `integer` and `double precision`.

## 3. Integer Types: `smallint`, `integer`, `bigint`

### 3.1. When to Use Integers?

Integers are suitable for values that inherently have no fractional part in the business domain:

- Inventory quantities.
- Number of items purchased in an order line.
- Identifiers or incrementing counters.
- Number of visits/accesses.
- Whole seconds or whole milliseconds when the unit is explicitly designed.

Example:

```sql
CREATE TABLE inventory_counts (
    product_id bigint PRIMARY KEY,
    on_hand integer NOT NULL CHECK (on_hand >= 0),
    reserved integer NOT NULL DEFAULT 0 CHECK (reserved >= 0)
);
```

`on_hand` and `reserved` are **whole unit quantities**. The `CHECK` constraint enforces the non-negative rule; the `integer` type alone still permits negative numbers.

### 3.2. Limits of Each Type

```text
smallint
  -32768 .............................. 32767

integer
  -2147483648 ......................... 2147483647

bigint
  -9223372036854775808 ... 9223372036854775807
```

Valid input example:

```sql
SELECT
    32767::smallint AS max_smallint,
    2147483647::integer AS max_integer,
    9223372036854775807::bigint AS max_bigint;
```

If you try to cast an out-of-range value:

```sql
-- Intentionally causes an error:
SELECT 32768::smallint;

-- Intentionally causes an error:
SELECT 2147483648::integer;
```

PostgreSQL raises an error stating that the number is out of range for the requested type; it does not allow an `integer` to hold arbitrary digits simply because the input source is large.

### 3.3. `integer` or `bigint` for IDs?

`integer` uses 4 bytes, while `bigint` uses 8 bytes. If IDs may grow over many years or the expected row count is very large, `bigint` is generally a sensible choice for an incrementing key.

```sql
CREATE TABLE customer_accounts (
    account_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    display_name text NOT NULL
);
```

`GENERATED ... AS IDENTITY` provides identifier values via a sequence. You may encounter `serial`/`bigserial` in legacy systems:

```sql
-- Relatively common legacy declaration style:
CREATE TABLE legacy_example (
    id bigserial PRIMARY KEY
);
```

`serial` and `bigserial` are convenience notations associated with sequences, **not completely independent numeric types** like `integer` and `bigint`.

**Identity/sequence columns do not guarantee gapless consecutive IDs.** A sequence can consume values through transaction rollbacks or collisions, and PostgreSQL does not undo sequence value allocations the same way it rolls back table rows. Do not use incrementing IDs as proof of record counts or for legally required consecutive invoice numbers without dedicated design.

### 3.4. Watch Out for Intermediate Calculation Overflow

Suppose you multiply two `integer` values:

```sql
-- Intentionally risks integer out of range because multiplication
-- occurs in integer before casting to bigint:
SELECT (50000::integer * 50000::integer)::bigint;
```

The mathematical result is `2,500,000,000`, which exceeds the `integer` limit. Casting **after** the multiplication does not rescue an operation that has already overflowed.

Better:

```sql
SELECT 50000::bigint * 50000::integer AS product;
```

When one operand is already `bigint`, PostgreSQL can select the multiplication operator and result type suited for the larger range.

However, `bigint` also has limits. If a calculation might exceed the 64-bit limit, consider `numeric` before multiplying:

```sql
SELECT
    9000000000000000000::numeric
    * 1000000000000000000::numeric AS huge_product;
```

**Rule:** promote to a sufficiently large type **before** executing an operation that could overflow.

### 3.5. Conditional Value Updates

```sql
UPDATE inventory_counts
SET on_hand = on_hand - 2
WHERE product_id = 101
  AND on_hand >= 2
RETURNING product_id, on_hand;
```

Using a single `UPDATE ... WHERE` statement ensures checking and writing are based on data at update time, avoiding the anti-pattern where an application reads a quantity, computes locally, and writes back without considering concurrency. For multi-step reservation workflows, proper transaction and locking design is still required.

## 4. Integer Division: Fractional Parts Are Truncated

An error-prone difference among numeric types:

```sql
SELECT
    5 / 2 AS integer_division,
    5.0 / 2 AS decimal_division,
    5::numeric / 2 AS explicit_numeric_division;
```

Typical results:

| Expression | Result | Reason |
| --- | ---: | --- |
| `5 / 2` | `2` | Both operands are integers: integer division |
| `5.0 / 2` | `2.500000...` | The literal 5.0 is a numeric decimal in typical contexts |
| `5::numeric / 2` | `2.500000...` | Cast to numeric before dividing |

For integer division, PostgreSQL discards the fractional part by **truncation toward zero**, not always taking the floor:

```sql
SELECT
    -5::integer / 2::integer AS negative_integer_division,
    floor(-5::numeric / 2) AS numeric_floor;
```

Results:

- `-5 / 2` in integer division is `-2`.
- `floor(-2.5)` is `-3`.

This matters if you use division to calculate ratios:

```sql
-- Unsuitable if you want a percentage result with decimals:
SELECT 3 / 4 * 100 AS percentage_wrong;

-- Cast before division:
SELECT 3::numeric / 4 * 100 AS percentage_correct;
```

The results are `0` and `75.000...`, respectively. On a table with two columns `success_count integer` and `total_count integer`, the expression `success_count / total_count` suffers from the same issue if not cast.

### 4.1. Avoiding Division by Zero

```sql
-- Intentionally causes an error:
SELECT 10 / 0;
```

You can use `NULLIF` to avoid a zero denominator:

```sql
SELECT
    10::numeric / NULLIF(0, 0) AS safe_ratio;
```

`NULLIF(0, 0)` returns `NULL`, so the division returns `NULL` instead of a division-by-zero error. However, `NULL` must be handled explicitly at the reporting layer: it may represent "undefined", not 0%.

### 4.2. Ratios from Aggregated Data

```sql
SELECT
    7::numeric / NULLIF(20, 0) AS ratio,
    round(100 * 7::numeric / NULLIF(20, 0), 2) AS percent;
```

Result: ratio `0.35` and percentage `35.00`. You can choose to multiply by 100 at the presentation layer for percentage display, but you must stay consistent between the API and the database: storing `0.35` under `rate` is different from storing `35` under `percentage_points`.

## 5. `numeric` / `decimal`: Exact Decimal Numbers

### 5.1. When to Choose numeric?

Use `numeric` when the business requires decimal-system calculations without accepting the binary representation errors of floating point, for example:

- Unit prices, line totals, tax amounts.
- Accounting balances.
- Fees, discount rates, and interest rates requiring prescribed precision.
- Computation results requiring many exact digits.

```sql
CREATE TABLE prices (
    product_code text PRIMARY KEY,
    price numeric(12,2) NOT NULL CHECK (price >= 0),
    tax_rate numeric(7,6) NOT NULL CHECK (tax_rate >= 0 AND tax_rate <= 1)
);
```

`numeric(12,2)` is suitable for prices with up to 12 total digits and 2 digits after the decimal point, within the limits of the declaration. `numeric(7,6)` keeps 6 digits after the decimal point for rates like `0.080000`.

### 5.2. What Do Precision and Scale Mean?

General declaration:

```sql
numeric(precision, scale)
```

- **Precision (`p`):** the total number of significant digits allowed in the number per the declaration.
- **Scale (`s`):** the number of digits after the decimal point to which the type is designed to store/coerce values.

Some common examples when `0 <= s <= p`:

| Type | Max Digits Left of Decimal Point | Digits After Decimal Point | Valid Example |
| --- | ---: | ---: | --- |
| `numeric(5,2)` | 3 | 2 | `999.99` |
| `numeric(8,3)` | 5 | 3 | `12345.678` |
| `numeric(12,2)` | 10 | 2 | `1234567890.12` |
| `numeric(7,6)` | 1 | 6 | `0.123456` |
| `numeric(18,8)` | 10 | 8 | `1234567890.12345678` |

Example:

```sql
SELECT
    123.45::numeric(5,2) AS accepted,
    12.345::numeric(5,2) AS rounded;
```

The value `12.345` is rounded to scale 2, becoming `12.35`.

If the integer-part digit limit is exceeded:

```sql
-- Intentionally causes numeric field overflow:
SELECT 1000.00::numeric(5,2);
```

`numeric(5,2)` only allows 3 digits to the left of the decimal point and cannot hold `1000.00`.

### 5.3. Order of Operations: Rounding First, Then Range Check

When casting a value to `numeric(p,s)`, PostgreSQL rounds to the declared scale, and then the value must fit within the allowed digit limits.

```sql
SELECT 999.994::numeric(5,2) AS still_fits;
```

The result is `999.99`, which fits within the range. However:

```sql
-- After rounding to 1000.00, it exceeds numeric(5,2) range:
SELECT 999.995::numeric(5,2);
```

The expected result is an out-of-range error. Therefore, some inputs near the boundary can be rejected **after rounding**.

### 5.4. Scale Does Not Mean Validating Exact Decimal Places on Input

Suppose you have a column:

```sql
amount numeric(12,2)
```

If the application sends `12.345`, PostgreSQL may **round it to `12.35`** when coercing to the column type. If the business rule states "must reject values with more than two decimal places", then `numeric(12,2)` **alone is not enough to reject that input**. You need to validate before the value gets rounded—in the application or in an ingestion/staging step that preserves the original input.

This is especially important when distinguishing between:

- **Normalizing monetary amounts by rounding**: accepting inputs with extra decimal digits and storing them according to policy.
- **Rejecting malformed currency-unit data**: not accepting numbers with more fractional digits than permitted.

### 5.5. `numeric` Without Declared Precision and Scale

PostgreSQL allows:

```sql
CREATE TABLE exact_measurements (
    measure_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    exact_value numeric NOT NULL
);
```

`numeric` without `(p,s)` uses the precision and scale of each value within implementation limits, without automatically forcing all inputs to two decimal places.

```sql
INSERT INTO exact_measurements (exact_value)
VALUES
    (0.123456789012345678901234567890),
    (12345678901234567890.123456789);
```

This form is useful when handling very long decimal numbers, though it generally consumes more resources than fixed-size numeric types. For prices/money with clear scale rules, declare an appropriate `numeric(p,s)` to document the value domain.

### 5.6. Negative Scale and Scale Greater Than Precision

In **PostgreSQL 15 and later**, `numeric` syntax allows extended configurations such as **negative scale**, used to round to the left of the decimal point.

```sql
-- PostgreSQL 15+:
SELECT 12345::numeric(5,-2) AS rounded_to_hundreds;
```

The value is rounded to the nearest hundred, e.g., `12300`.

This is a different feature from changing the number of digits after the decimal point when storing money. Do not use negative scale for monetary values that must be stored down to the smallest unit. Always check the PostgreSQL version when using this feature in older environments.

## 6. Rounding with `numeric`

### 6.1. `round`: Rounding to a Number of Digits

```sql
SELECT
    round(12.345::numeric, 2) AS rounded_two_decimals,
    round(12.344::numeric, 2) AS rounded_down,
    round(-12.345::numeric, 2) AS rounded_negative;
```

Results according to PostgreSQL `numeric` rounding rules:

| Expression | Result |
| --- | ---: |
| `round(12.345::numeric, 2)` | `12.35` |
| `round(12.344::numeric, 2)` | `12.34` |
| `round(-12.345::numeric, 2)` | `-12.35` |

For a value lying exactly **halfway between two rounding choices** (*tie*), PostgreSQL `numeric` rounds **away from zero**.

```sql
SELECT
    round(2.5::numeric) AS positive_half,
    round(-2.5::numeric) AS negative_half;
```

The results are `3` and `-3`.

In finance, not every business uses the same rounding rule. If **banker's rounding / ties-to-even** is required, do not assume the default `round(numeric, s)` satisfies that policy. You must design the business rounding policy and implement/verify it consistently across the application and the database.

### 6.2. `trunc`: Truncating the Fractional Part Without Rounding

```sql
SELECT
    trunc(12.349::numeric, 2) AS trunc_positive,
    trunc(-12.349::numeric, 2) AS trunc_negative;
```

Results:

- `12.34`, not `12.35`.
- `-12.34`, because `trunc` truncates toward zero.

Compare:

```sql
SELECT
    round(19.999::numeric, 2) AS rounded,
    trunc(19.999::numeric, 2) AS truncated;
```

`round` gives `20.00`, while `trunc` gives `19.99`.

Do not use `trunc` and `round` interchangeably just because their outputs happen to match on many ordinary examples.

### 6.3. `floor` and `ceil`

```sql
SELECT
    floor(2.8::numeric) AS floor_positive,
    ceil(2.2::numeric) AS ceil_positive,
    floor(-2.2::numeric) AS floor_negative,
    ceil(-2.8::numeric) AS ceil_negative;
```

The results are `2`, `3`, `-3`, and `-2`, in order.

- `floor(x)`: the nearest integer **not greater than x**.
- `ceil(x)`: the nearest integer **not less than x**.
- `trunc(x)`: truncates the fractional part toward zero.

When calculating the number of boxes needed to hold products, `ceil(quantity / capacity)` is only correct if the division result is not truncated **before** `ceil` is called:

```sql
SELECT
    ceil(7::numeric / 3) AS boxes_needed;
```

The result is `3`; whereas `ceil(7 / 3)` already receives the integer result `2` from integer division and can return the wrong answer.

## 7. Floating-Point Types: `real` and `double precision`

### 7.1. What Does "Floating-Point" Mean?

`real` and `double precision` in PostgreSQL are typically implemented according to IEEE 754 binary floating-point numbers, with finite bits for the significand and exponent.

Unlike `numeric` (exact decimal representation), floating point uses **binary approximate** representation. Many decimal numbers such as `0.1` and `0.2` do not have an exact finite representation in binary form.

This is analogous to how `1/3` does not have a finite decimal form:

```text
1 / 3 = 0.333333333333333...
```

Conversely, `0.1` does not have a finite binary form, so `double precision` must store a value very close to it.

### 7.2. How Do `real` and `double precision` Differ?

| Property | `real` | `double precision` |
| --- | --- | --- |
| Size | 4 bytes | 8 bytes |
| Precision approx. | 6 significant decimal digits | 15 significant decimal digits |
| Exponent range | Narrower | Wider |
| Representation error | Relatively larger | Generally smaller than `real` |
| Use cases | Sensors not needing many digits, high-volume scientific data | Measurements, general numerical algorithms |
| Absolute decimal exactness | No | No |

Example:

```sql
SELECT
    12345678.9::real AS measured_real,
    12345678.9::double precision AS measured_double;
```

With `real`, the trailing digits can change significantly because the number has more significant digits than the type's precision capacity. `double precision` preserves more accurate digits, but is still a binary approximation.

**Do not infer that because a number prints cleanly in psql, the internally stored value is absolutely exact.** PostgreSQL has formatting mechanisms when displaying floating-point results; the printed digits and the stored binary value are two different things.

### 7.3. Testing `0.1 + 0.2`

```sql
SELECT
    0.1::numeric + 0.2::numeric AS exact_decimal_sum,
    0.1::double precision + 0.2::double precision AS approximate_sum;
```

With `numeric`, the mathematical value is `0.3` with exact decimal precision. With `double precision`, the result is typically near `0.30000000000000004` on standard IEEE 754 systems.

Exact equality comparison:

```sql
SELECT
    (0.1::numeric + 0.2::numeric = 0.3::numeric)
        AS numeric_equal,
    (0.1::double precision + 0.2::double precision
        = 0.3::double precision)
        AS float_equal;
```

Typically:

- `numeric_equal` is `true`.
- `float_equal` is `false` with standard IEEE 754 arithmetic.

This is not a "PostgreSQL bug"; it is a property of **binary floating-point numbers**.

### 7.4. Comparing Floating-Point Numbers with an Error Threshold

If you need to check whether two measurements are **close within an acceptable tolerance**, express the threshold from the business domain:

```sql
SELECT
    abs(
        (0.1::double precision + 0.2::double precision)
        - 0.3::double precision
    ) < 1e-12::double precision AS approximately_equal;
```

Using an absolute threshold of `1e-12` here is only for illustration. For values spanning widely different magnitudes, you often need to consider both **absolute error** and **relative error**.

A common approximate comparison pattern:

```sql
SELECT
    abs(a - b) <= 1e-9::double precision
        + 1e-6::double precision
          * greatest(abs(a), abs(b)) AS close_enough
FROM (
    SELECT
        0.1::double precision + 0.2::double precision AS a,
        0.3::double precision AS b
) AS values_to_compare;
```

Threshold constants must be derived from sensor tolerances, acceptance rules, or algorithmic requirements—do not copy one epsilon formula blindly across all projects.

**If the number is actually money, the solution is not comparing money with a tiny epsilon; usually you should use `numeric` from the start.**

### 7.5. Do Not Use Floating Point for Business Keys Requiring Exact Equality

For example, you should not use `double precision` to represent "a listed price of exactly 0.30" and then rely on `= 0.3` to look up records. Monetary prices should use `numeric`; IDs should use `bigint` or an appropriate identifier type; approximate measurements are what better fit floating point.

Using floats in an indexed column is not forbidden, but you must understand the semantics of comparison operators and data distribution before designing exact-match queries on a measured value.

## 8. Special Values: `NaN`, `Infinity`, and `-Infinity`

PostgreSQL supports special floating-point values, such as:

```sql
SELECT
    'NaN'::double precision AS not_a_number,
    'Infinity'::double precision AS positive_infinity,
    '-Infinity'::double precision AS negative_infinity;
```

`NaN` (*Not a Number*) often appears in numerical models when a result has no ordinary numeric value. `Infinity` and `-Infinity` represent infinite values according to the supported type's semantics.

PostgreSQL also supports corresponding special values in `numeric` on modern versions, such as:

```sql
SELECT
    'NaN'::numeric AS numeric_nan,
    'Infinity'::numeric AS numeric_infinity;
```

**Important limitation:** `numeric` infinity values cannot be stored in a `numeric(p,s)` type with a declared finite precision; handling and acceptance of these values also depend on the PostgreSQL version, column type, and constraints.

### 8.1. Comparing `NaN` in PostgreSQL

Unlike some direct expectations from IEEE 754, PostgreSQL defines ordering/comparison rules for `NaN` in order to support indexes and `ORDER BY`. For supporting numeric types, PostgreSQL treats `NaN` as **equal to itself** and greater than non-`NaN` values under the appropriate comparison operators.

```sql
SELECT
    ('NaN'::double precision = 'NaN'::double precision)
        AS pg_nan_equals_nan,
    ('NaN'::numeric > 1000000::numeric)
        AS pg_nan_sorts_high;
```

This is a **PostgreSQL-specific** rule and should not be assumed across all numerical libraries in applications.

### 8.2. Risks for Financial Constraints

A column:

```sql
amount numeric NOT NULL CHECK (amount >= 0)
```

does not automatically express "every value is a valid finite number". Because `NaN` has special comparison semantics, it can pass comparison conditions that appear obvious at first glance.

If the business does not accept `NaN`, include that rule in appropriate validation/constraints, for instance on an unconstrained numeric column:

```sql
CREATE TABLE checked_amounts (
    amount numeric NOT NULL,
    CONSTRAINT chk_nonnegative_finite
        CHECK (
            amount >= 0
            AND amount <> 'NaN'::numeric
            AND amount <> 'Infinity'::numeric
        )
);
```

The purpose of this example is to **intentionally reject NaN and positive infinity**; negative infinity already fails `amount >= 0`. With `numeric(p,s)`, precision itself also restricts accepting infinity. In production systems, validation must ensure data consists only of required finite values and aligns with the PostgreSQL version in use.

Do not assume `NaN` or `Infinity` has the same meaning as SQL `NULL`:

- `NULL` indicates a missing/unknown value under SQL logic.
- `NaN` is a special value **within the numeric type**.
- `Infinity` is a value representing infinity for an applicable type.

## 9. Numeric Type Casting and Expression Type Inference

PostgreSQL determines types for literals and expressions based on context. This alters mathematical outcomes if you do not pay attention.

### 9.1. Inspecting Types with `pg_typeof`

```sql
SELECT
    pg_typeof(42) AS literal_integer_type,
    pg_typeof(42::bigint) AS bigint_type,
    pg_typeof(42.0) AS decimal_literal_type,
    pg_typeof(42.0::real) AS real_type,
    pg_typeof(42.0::double precision) AS double_type;
```

Typically:

- A small integer literal like `42` is interpreted as `integer`.
- A literal with a decimal point like `42.0` has type `numeric` in the appropriate context.
- An explicit cast produces the requested type.

For an integer literal too large for `integer` but still within `bigint`, PostgreSQL can choose `bigint`; even larger literals may be inferred as `numeric`. However, do not rely on inference rules when the result type is part of the system's correctness requirements: **cast explicitly**.

### 9.2. Two Forms of Casting

PostgreSQL supports:

```sql
SELECT
    CAST('123.45' AS numeric(8,2)) AS standard_cast,
    '123.45'::numeric(8,2) AS postgres_cast;
```

`CAST(x AS type)` is the standard SQL syntax. `x::type` is concise and widely used in PostgreSQL.

### 9.3. Casting Does Not Always Preserve the Exact Value

Example:

```sql
SELECT
    12.345::numeric(5,2) AS rounded_to_scale,
    2.7::numeric::integer AS converted_to_integer;
```

- `numeric(5,2)` rounds to 2 decimal places.
- When casting a `numeric` with a fractional part to a PostgreSQL integer type, the value is **rounded to an integer** per type conversion rules; it is not the same as integer division truncating the fraction.

Do not confuse:

```sql
SELECT
    5::integer / 2::integer AS integer_division,
    (5::numeric / 2)::integer AS rounded_numeric_result;
```

The first expression yields `2`; the second first evaluates to `2.5` and then casts to `integer`, so the result can be `3` under numeric cast rounding rules.

When truncating the fractional part is required, use `trunc` before casting:

```sql
SELECT trunc(5::numeric / 2)::integer AS explicitly_truncated;
```

### 9.4. Casting After an Operation Does Not Restore Lost Precision

Mistake:

```sql
SELECT
    (0.1::double precision + 0.2::double precision)::numeric
        AS cast_after_approximate_math;
```

Casting a result from float to numeric **cannot recover exact decimal information already lost** during rounding and approximate arithmetic in the float type.

Better, if exact decimal values are required:

```sql
SELECT
    0.1::numeric + 0.2::numeric AS exact_math;
```

To maintain precision, you must choose the appropriate type **right from the source data and throughout all computation steps**.

## 10. Arithmetic Operations and Result Types

Common operations:

| Operator / Function | Meaning | Example |
| --- | --- | --- |
| `+` | Addition | `7 + 2` |
| `-` | Subtraction | `7 - 2` |
| `*` | Multiplication | `7 * 2` |
| `/` | Division | `7 / 2` |
| `%` | Modulo (remainder) for supported types | `7 % 2` |
| `^` | Exponentiation per PostgreSQL function/operator types | `2.0::numeric ^ 3` |
| `abs(x)` | Absolute value | `abs(-5)` |
| `sqrt(x)` | Square root with appropriate type | `sqrt(9::numeric)` |

Key point: PostgreSQL has **multiple overloads** of the same operator/function for different types. Operand types affect which function/operator and result type PostgreSQL chooses.

### 10.1. Querying to Observe Operation Result Types

```sql
SELECT
    pg_typeof(1::integer + 2::integer) AS sum_int_type,
    pg_typeof(1::bigint + 2::bigint) AS sum_bigint_type,
    pg_typeof(1::numeric + 2::numeric) AS sum_numeric_type,
    pg_typeof(1::double precision + 2::double precision)
        AS sum_double_type;
```

Even for the same addition operator, the resulting data types differ. This is why applications must check driver mappings and where overflow or rounding will happen.

### 10.2. A Wider Type Does Not Mean Immune to Overflow

`bigint` can hold more integers than `integer`, yet:

```sql
-- Can cause an overflow error:
SELECT 9223372036854775807::bigint + 1::bigint;
```

You need to convert to numeric **before** adding:

```sql
SELECT 9223372036854775807::numeric + 1::numeric
    AS exact_sum;
```

With floating-point numbers, exceeding the range involves special behaviors such as overflow/underflow or infinity values, depending on the operation and version. Do not use floating point in place of bigint just to "avoid overflow" when you actually need to preserve **exactness down to every single whole unit**.

## 11. Aggregations: `SUM`, `AVG`, `COUNT` and Return Types

A common reporting mistake is assuming the input type always equals the aggregate function's result type.

In PostgreSQL:

| Input Expression | Typical Result Type |
| --- | --- |
| `sum(smallint)` | `bigint` |
| `sum(integer)` | `bigint` |
| `sum(bigint)` | `numeric` |
| `sum(numeric)` | `numeric` |
| `sum(real)` | `real` |
| `sum(double precision)` | `double precision` |
| `avg(integer)` | `numeric` |
| `avg(bigint)` | `numeric` |
| `avg(numeric)` | `numeric` |
| `avg(real)` | `double precision` |
| `avg(double precision)` | `double precision` |
| `count(*)` | `bigint` |

These choices help prevent sums of many integers from immediately overflowing their original type. However, you must never blindly assume every aggregate result is `integer`.

Example:

```sql
SELECT
    pg_typeof(sum(v)) AS sum_type,
    pg_typeof(avg(v)) AS avg_type,
    sum(v) AS sum_value,
    avg(v) AS average_value
FROM (VALUES (1::integer), (2::integer), (3::integer)) AS t(v);
```

`sum(v)` has type `bigint`; `avg(v)` is `numeric` with an average value of `2`.

### 11.1. `AVG` Does Not Perform Integer Division Like `sum/count` When Types Differ

```sql
SELECT
    avg(v) AS average_by_avg,
    sum(v) / count(*) AS ratio_by_sum_count,
    sum(v)::numeric / count(*) AS precise_ratio
FROM (VALUES (1::integer), (2::integer)) AS t(v);
```

- `avg(v)` returns the exact average as numeric, i.e., `1.5`.
- `sum(v)` is bigint and `count(*)` is also bigint; `sum(v) / count(*)` is **integer division**, which yields `1`.
- Casting `sum(v)::numeric` before dividing yields `1.5`.

Therefore, when manually computing ratios, averages, or percentages via `SUM/COUNT`, pay attention to the types of both operands.

### 11.2. `SUM`, `AVG` on Empty Sets and `NULL`

```sql
SELECT
    count(*) AS row_count,
    sum(amount) AS total_amount,
    avg(amount) AS avg_amount
FROM numeric_lab.sales
WHERE false;
```

On an empty set:

- `COUNT(*)` is `0`.
- `SUM(...)` typically returns `NULL`.
- `AVG(...)` returns `NULL`.

When you want to display a total of 0 in a report, you can use:

```sql
SELECT
    COALESCE(SUM(amount), 0::numeric) AS total_amount
FROM numeric_lab.sales
WHERE false;
```

`COALESCE` serves a **reporting presentation convention**, not proof that real data exists. Distinguish "no orders" from "orders exist with a total amount of 0" whenever the business requires it.

## 12. Building a Hands-On Example: Quantities, Unit Prices, and Sensors

The following SQL statements use a **sandbox** database with permissions to create schemas/tables. Do not run table-altering commands in a production environment just for learning. If practicing multiple times, use a fresh schema or actively manage existing data.

### 12.1. Creating the Schema and Table

```sql
CREATE SCHEMA IF NOT EXISTS numeric_lab;

CREATE TABLE numeric_lab.sales (
    sale_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_code text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12,2) NOT NULL CHECK (
        unit_price >= 0
        AND unit_price <> 'NaN'::numeric
    ),
    tax_rate numeric(7,6) NOT NULL CHECK (
        tax_rate >= 0
        AND tax_rate <= 1
        AND tax_rate <> 'NaN'::numeric
    ),
    measured_weight real,
    measured_temperature double precision,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Meaning:

- `sale_id bigint`: ID for a potentially large number of records, allocated via identity.
- `quantity integer`: quantity of units sold, with no fractional part.
- `unit_price numeric(12,2)`: exact decimal unit price at scale 2.
- `tax_rate numeric(7,6)`: tax rate expressed as 0–1, retaining 6 decimal places.
- `measured_weight real`: approximate weighing data.
- `measured_temperature double precision`: measurement data needing more digits than `real`.

The example `CHECK` clauses proactively reject `NaN` in monetary/rate columns. Production values still require business validation and applicable tax rules.

### 12.2. Loading Sample Data

```sql
INSERT INTO numeric_lab.sales
    (
        product_code,
        quantity,
        unit_price,
        tax_rate,
        measured_weight,
        measured_temperature
    )
VALUES
    ('BOOK-001', 2, 125000.00, 0.080000, 1.25, 25.1254),
    ('PEN-002', 5, 15000.50, 0.080000, 0.08, 24.8132),
    ('NOTE-003', 3, 32000.75, 0.050000, 0.35, 23.9971);
```

This is synthetic data for learning numeric types. The `tax_rate` values are purely illustrative and not an assertion of actual tax rates.

### 12.3. Calculating Line Amounts with numeric

```sql
SELECT
    sale_id,
    product_code,
    quantity,
    unit_price,
    quantity::numeric * unit_price AS line_subtotal,
    round(
        quantity::numeric * unit_price * tax_rate,
        2
    ) AS line_tax,
    round(
        quantity::numeric * unit_price * (1 + tax_rate),
        2
    ) AS line_total
FROM numeric_lab.sales
ORDER BY sale_id;
```

Example for row `BOOK-001`:

- `quantity = 2`.
- `unit_price = 125000.00`.
- `tax_rate = 0.080000`.
- `line_subtotal = 2 × 125000.00 = 250000.00`.
- `line_tax = 250000.00 × 0.08 = 20000.00`.
- `line_total = 270000.00`.

The calculations are executed within the appropriate numeric domain, without introducing `double precision` binary errors into unit prices and taxes.

### 12.4. Rounding Per Line or at Invoice Total?

These two calculation methods can produce different results:

**Method A: round tax per line, then sum.**

```sql
SELECT
    SUM(
        round(quantity::numeric * unit_price * tax_rate, 2)
    ) AS tax_rounded_per_line
FROM numeric_lab.sales;
```

**Method B: sum unrounded tax amounts, then round at the end.**

```sql
SELECT
    round(
        SUM(quantity::numeric * unit_price * tax_rate),
        2
    ) AS tax_rounded_after_sum
FROM numeric_lab.sales;
```

Results can differ in the last digit when multiple lines have very small fractional amounts. PostgreSQL does not decide for the business which method is correct: the **tax/rounding policy** must be defined by business rules and applicable regulations.

Once a policy is chosen, apply it consistently across PostgreSQL, Java, and reconciliation systems.

### 12.5. Reporting Total Quantities and Revenue

```sql
SELECT
    product_code,
    SUM(quantity) AS total_quantity,
    SUM(quantity::numeric * unit_price) AS total_before_tax,
    round(
        SUM(quantity::numeric * unit_price * (1 + tax_rate)),
        2
    ) AS total_with_tax
FROM numeric_lab.sales
GROUP BY product_code
ORDER BY product_code;
```

`SUM(quantity)` takes integer quantities and returns `bigint`; total monetary amounts use `numeric`. When a Java application reads these columns, it must choose corresponding mapping types (e.g., `Long` for total quantity, `BigDecimal` for money), rather than assuming every numeric column returns `Integer`.

### 12.6. Querying Measurements

```sql
SELECT
    product_code,
    measured_weight,
    measured_temperature
FROM numeric_lab.sales
WHERE measured_temperature >= 24.0::double precision
ORDER BY measured_temperature DESC;
```

This is appropriate when using approximate measurements and threshold comparisons. If you need to check whether two readings are "nearly equal", define an acceptable tolerance rather than expecting `=` to match exact binary representations.

### 12.7. Checking the Actual Column Types

```sql
SELECT
    pg_typeof(quantity) AS quantity_type,
    pg_typeof(unit_price) AS price_type,
    pg_typeof(measured_weight) AS weight_type,
    pg_typeof(measured_temperature) AS temperature_type
FROM numeric_lab.sales
LIMIT 1;
```

This query lets you observe the types PostgreSQL stores/reads for the values. It does not measure the physical accuracy of the sensor; sensor accuracy is a property of the measurement source, not just of the database numeric type.

## 13. Monetary Values: `numeric` or Minor-Unit Integers?

There are two common strategies for money:

### 13.1. Storing with `numeric(p,s)`

```sql
CREATE TABLE wallet_balances_numeric (
    wallet_id bigint PRIMARY KEY,
    balance numeric(18,2) NOT NULL
);
```

Advantages:

- Directly expresses monetary amounts with two decimal places.
- Readable SQL.
- Exact decimal arithmetic.
- Can use different scales for rates, currencies, or operations needing more fractional digits.

Rounding policies and limits must be controlled through constraints/business logic.

### 13.2. Storing with `bigint` in Minor Units

```sql
CREATE TABLE wallet_balances_minor_units (
    wallet_id bigint PRIMARY KEY,
    balance_cents bigint NOT NULL
);
```

If the smallest unit is well-defined and fixed, you can store the **count of minor units** as an integer:

```text
12.34 major currency units
= 1234 minor units (if 1 major unit = 100 minor units)
```

Advantages:

- Exact integer arithmetic within `bigint` limits.
- Prevents invalid fractional parts at the storage layer if all systems share the same unit.

Disadvantages:

- Requires conversion and rounding rules at boundaries.
- Requires care across multiple currencies with different decimal places.
- Risk of `bigint` overflow when summing/multiplying large amounts.
- Rate/tax calculations still require decimal numbers or appropriate rounding logic.

**There is no single right choice for every financial system.** What matters is clearly defining **units**, **scale**, **rounding rules**, **value ranges**, **application mapping types**, and reconciliation rules.

### 13.3. The `money` Type in PostgreSQL

PostgreSQL also has a `money` type, but its display formatting and certain locale/configuration-dependent behaviors make it unsuitable as a default for every application.

For problems requiring strict control over precision, scale, JSON/API serialization, and calculations, `numeric(p,s)` is generally easier to explain and more consistent. Only use `money` when you fully understand its behavior, locale requirements, and application compatibility.

## 14. Measurement Data and Scientific Computing

With sensor data, many input digits may not reflect true physical accuracy:

```text
Thermometer reports 24.123456 °C
Device tolerance ±0.1 °C
```

Even if you store `numeric(20,10)`, you **do not make the sensor more accurate**. Conversely, `double precision` can suffice to perform arithmetic operations on measured values.

### 14.1. When Is `real` Suitable?

If billions of measured values can accept around 6 significant digits, `real` reduces storage compared to double. However, you must estimate acceptable error:

- How many reliable digits does the original value have?
- Will subsequent calculations sum millions of values?
- Could cumulative error alter safety thresholds or decisions?
- Is it necessary to guarantee identical results across different CPUs/architectures/software?

`real` can save storage but does not always deliver reliable precision for all computations.

### 14.2. When to Use `double precision`?

`double precision` is generally better suited than `real` for general calculations and numerical algorithms requiring higher approximate precision, such as:

- Scientific data.
- Coordinates/measurements with defined error tolerances.
- Multi-step statistical computations.
- Approximate machine learning data when the schema and processing pipeline accept floats.

You still must watch out for **cumulative error**.

### 14.3. Floating-Point Addition Can Depend on Order

Because each floating-point addition may round, the sum of a set of numbers can vary slightly when the addition order changes.

Conceptual example:

```text
Very large number + very small number + very small number + ...
versus
very small number + ... + very small number + very large number
```

Small numbers can lose their contribution when added to a large number due to significant-digit limits. Parallel query plans may sum in different orders, introducing small float discrepancies.

If a financial report demands an exact monetary sum, use `SUM(numeric)` instead of `SUM(double precision)`. If it is measurement statistics, define tolerances and test algorithmic stability.

## 15. Data Types in Java, JDBC, and Applications

PostgreSQL handles storage, but the application must also preserve the right precision during data transfer.

| PostgreSQL | Typical Java/JDBC Match | Notes |
| --- | --- | --- |
| `smallint` | `Short`/`short` | Must understand the small range limit |
| `integer` | `Integer`/`int` | Suitable for counts within range |
| `bigint` | `Long`/`long` | Larger than integer but still finite |
| `numeric` / `decimal` | `java.math.BigDecimal` | Preserves decimal representation with precision |
| `real` | `Float`/`float` | 32-bit approximate measurement |
| `double precision` | `Double`/`double` | 64-bit approximate measurement |

### 15.1. Avoid `double` for Monetary Prices in Java

Avoid:

```java
double unitPrice = 0.10;
double fee = 0.20;
double total = unitPrice + fee;
```

This is still binary floating-point addition in Java, even if you later send `total` into a `numeric` column in PostgreSQL.

Use `BigDecimal` constructed from decimal strings when exact values are needed:

```java
import java.math.BigDecimal;

BigDecimal unitPrice = new BigDecimal("0.10");
BigDecimal fee = new BigDecimal("0.20");
BigDecimal total = unitPrice.add(fee);

System.out.println(total); // 0.30
```

Do not initialize `BigDecimal` from an already-approximated `double` without understanding the implication; for instance, `new BigDecimal(0.1)` carries the approximate binary value expanded into decimal. When the input is a business decimal number, use a decimal string source or an appropriate exact parsing mechanism.

### 15.2. Reading/Writing numeric via JDBC

Java example:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class PriceReader {
    public static BigDecimal findPrice(Connection conn, long saleId)
            throws Exception {
        String sql =
                "SELECT unit_price FROM numeric_lab.sales WHERE sale_id = ?";

        try (PreparedStatement stmt = conn.prepareStatement(sql)) {
            stmt.setLong(1, saleId);

            try (ResultSet rs = stmt.executeQuery()) {
                if (rs.next()) {
                    return rs.getBigDecimal("unit_price");
                }
                return null;
            }
        }
    }
}
```

`getBigDecimal` is appropriate for reading a numeric column without coercing to double. When writing, use `PreparedStatement.setBigDecimal` to maintain the expected type.

### 15.3. Watch Out for Scale in Java and PostgreSQL

In Java, two `BigDecimal` instances with the same mathematical value but different scales can behave differently in certain object-level comparisons; keep conventions aligned during mapping and reconciliation.

Example:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false (different scale)
```

In PostgreSQL, `numeric` compares by numerical value. Do not treat Java's `BigDecimal.equals` behavior as the SQL rule for comparing `numeric`.

### 15.4. JSON and API Formats

When transferring monetary amounts from PostgreSQL over an API:

- Do not automatically convert prices to a JavaScript Number and assume all digits stay exact across all ranges.
- For very large `bigint` integers, some JavaScript environments cannot accurately represent every 64-bit integer in the `Number` type.
- Consider decimal string representations or data contracts with explicit parsing rules for money and large IDs.

**Precision must be preserved from the database across every layer**: JDBC, service, JSON serialization, frontend, and external accounting systems.

## 16. Indexes and Performance: How Do Numeric Types Affect Them?

### 16.1. Size and Computational Cost

In principle:

- `smallint`/`integer`/`bigint` have fixed sizes and integer operations are generally efficient.
- `real`/`double precision` have fixed sizes and align well with floating-point hardware units.
- `numeric` has variable-length storage and high-precision arithmetic can consume more CPU/memory.

However, query execution time also depends on indexing, row count, selectivity, I/O, memory, JOINs, and query plans. Do not choose `real` for money simply expecting faster speed; data correctness always comes first.

### 16.2. B-tree Indexes on numeric and integer

```sql
CREATE INDEX idx_sales_unit_price
    ON numeric_lab.sales (unit_price);

CREATE INDEX idx_sales_quantity
    ON numeric_lab.sales (quantity);
```

Example:

```sql
SELECT sale_id, product_code, unit_price
FROM numeric_lab.sales
WHERE unit_price >= 100000.00::numeric
ORDER BY unit_price, sale_id;
```

An index can be helpful when the table is large and the predicate is selective enough. With just a few practice rows, PostgreSQL may choose a sequential scan because it is cheaper.

Verify:

```sql
EXPLAIN
SELECT sale_id, product_code, unit_price
FROM numeric_lab.sales
WHERE unit_price >= 100000.00::numeric;
```

Do not create many indexes just to speed up a practice exercise on tiny data. Indexes incur storage overhead and write-time maintenance costs.

### 16.3. Watch Parameter Types When Querying

If a column is `numeric(12,2)`, passing the value via JDBC using `BigDecimal` clearly defines the decimal meaning. If a column is `bigint`, pass a proper long/BigInt in the application instead of a floating-point type that could lose precision on very large IDs.

When SQL casts a column or compares differing types, index usage in the query plan can be affected. Do not conclude solely from seeing a cast expression that "the index definitely cannot be used"; verify using `EXPLAIN` and real table statistics.

### 16.4. Floating Point and Equality Queries

```sql
SELECT *
FROM numeric_lab.sales
WHERE measured_temperature = 24.8::double precision;
```

An equality query **compares the stored binary value**, not "temperature near 24.8". If the source is a sensor, you should usually query a range:

```sql
SELECT *
FROM numeric_lab.sales
WHERE measured_temperature >= 24.7::double precision
  AND measured_temperature <  24.9::double precision;
```

This range means "from 24.7 up to below 24.9" in business terms, not a universal default epsilon for all data. If specific measurement rules are needed, define thresholds matching the requirements.

## 17. Value Ranges, Units, and Constraints

Choose a type wide enough, but also protect domain logic.

### 17.1. Non-Negative Quantities

```sql
CREATE TABLE numeric_lab.stock_levels (
    sku text PRIMARY KEY,
    quantity integer NOT NULL
        CHECK (quantity >= 0)
);
```

Mathematically, the `integer` type allows negative numbers; the `CHECK` constraint is what enforces the "non-negative stock" rule.

### 17.2. Percentages Must Establish a Convention: 0 to 1 or 0 to 100

Two designs:

```sql
discount_rate numeric(7,6)
    CHECK (discount_rate >= 0 AND discount_rate <= 1)
```

or:

```sql
discount_percent numeric(5,2)
    CHECK (discount_percent >= 0 AND discount_percent <= 100)
```

Both can make sense, but you must name columns according to **units** and document them clearly in the API contract. If a user enters 15% and the system stores it in `discount_rate`, the value must be `0.15`, not `15`.

### 17.3. Temperatures Do Not Share the Same Domain as Percentages

```sql
temperature_celsius double precision
```

For temperatures that can be negative, do not add `CHECK (temperature_celsius >= 0)` just because many other numeric columns are non-negative. Constraints must derive from reality and business goals.

### 17.4. Choose an Adequate Type While Leaving Room for Growth

An access counter in `integer` may become insufficient as a system grows. If you expect it to exceed roughly 2.1 billion, use `bigint` early on or prepare a controlled migration.

Conversely, replacing every `smallint` column with `numeric` "so it never overflows" is not necessarily sensible: storage cost, computation overhead, and domain clarity all need to be weighed.

## 18. Common Errors and How to Handle Them

| Error or Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `smallint out of range` | Value exceeds ±32 thousand | Choose `integer` or the proper value domain |
| `integer out of range` | Operation/literal exceeds 32-bit limit | Use `bigint` or `numeric` before the operation |
| `bigint out of range` | Value or operation exceeds 64-bit limit | Use `numeric` if the problem truly requires it |
| `numeric field overflow` | Value after rounding exceeds declared precision/scale | Review p/s and business domain |
| `12.345` into `numeric(12,2)` becomes `12.35` | Column automatically rounds to scale 2 | Decide whether policy is round or reject |
| `5 / 2` equals `2` | Integer division | Cast before dividing |
| `SUM(integer)/COUNT(*)` yields an integer | Both aggregate operands have integer types | Cast `SUM(...)::numeric` before dividing |
| Float `0.1 + 0.2` differs from `0.3` | Binary representation error | Use numeric if decimal precision is needed |
| `round(double precision, integer)` has no matching overload | `round(x, s)` has a corresponding numeric version | Cast to numeric when decimal rounding is intended |
| Float values vary by summation order | Accumulated error and evaluation order | Accept/account for tolerance or use numeric when needed |
| `NaN` slips past seemingly valid comparisons | PostgreSQL's special NaN semantics | Add finite-value constraints/validation |
| `numeric` slower than integer in batches | Exact-precision arithmetic carries overhead | Choose only when business requires it; benchmark workload |
| Very large IDs altered in frontend | JavaScript Number does not preserve all int64 values | Use appropriate serialization and receiving types |
| Monetary amounts wrong before writing to PostgreSQL | Application computed using double | Use BigDecimal/decimal end-to-end |
| Float equality query misses measurements | Stored values are approximate with measurement error | Use a range or business-meaningful tolerance |
| Ratio evaluates to `NULL` | Denominator is 0 and `NULLIF` was used | Define how missing/undefined data is represented |

### 18.1. Encountering numeric field overflow

Example:

```sql
-- Intentionally errors:
SELECT 12345.67::numeric(6,2);
```

`numeric(6,2)` only allows 4 digits before the decimal point; `12345.67` has 5 digits before the decimal point, so it cannot be stored.

Do not immediately increase precision indefinitely if the root issue is **invalid input violating business rules**. Check the table of valid business values before altering the schema.

### 18.2. `round` with Two Arguments for double precision

```sql
-- This statement has no matching overload like numeric:
-- SELECT round(1.234::double precision, 2);

-- If you genuinely want decimal rounding at this step:
SELECT round(1.234::double precision::numeric, 2);
```

However, casting double to numeric at the final step does not turn approximate data back into the exact original decimal before it passed through float. You must clarify the goal of the rounding step.

### 18.3. Difference in `round` Between numeric and float at Ties

With numeric:

```sql
SELECT round(2.5::numeric), round(-2.5::numeric);
```

The results are `3` and `-3`.

For floating-point types, when a value lies exactly halfway between two integers, PostgreSQL typically relies on the platform's rounding behavior; on many systems, results tend toward **ties-to-even**. Do not depend on `round(numeric)` and `round(double precision)` matching when the rounding policy is critical to the business.

## 19. Practice Exercises

### Exercise 1. Choosing a Type for Product Quantity

A store sells items individually, with line quantities up to a few million.

**Hint:** `integer` is a reasonable choice; add `CHECK (quantity > 0)` for order lines or `CHECK (stock >= 0)` for inventory. Do not use numeric simply because prices use numeric.

### Exercise 2. Choosing a Type for Monetary Prices

Unit prices require 2 decimal places, and the integer part can reach up to 10 digits.

**Hint:** `numeric(12,2)` (10 integer digits and 2 fractional digits), combined with valid-value constraints and business validation. If limits could be exceeded, pick a more suitable p.

### Exercise 3. What Does `7 / 2` Return?

```sql
SELECT
    7 / 2 AS integer_value,
    7::numeric / 2 AS precise_value;
```

**Answer:** the integer division result is `3`; the numeric result includes the fractional part `3.5`.

### Exercise 4. Why Does `round(-2.5::numeric)` Not Equal −2?

**Answer:** PostgreSQL `round(numeric)` handles ties by rounding **away from zero**, so `-2.5` becomes `-3`.

### Exercise 5. Which Type for a Sensor Recording About 7 Significant Digits?

**Hint:** `double precision` is generally more appropriate than `real` if you need to preserve around 7 significant digits of a measured value. However, consider actual error tolerances and computation needs; if exact decimal values under a specific measurement standard are required, a different model may be needed.

### Exercise 6. Calculating Success Rate

Given 29 successes out of 40 attempts, write SQL returning the exact ratio and the percentage rounded to two decimal places.

```sql
SELECT
    29::numeric / NULLIF(40, 0) AS success_rate,
    round(100 * 29::numeric / NULLIF(40, 0), 2)
        AS success_percent;
```

**Answer:** ratio `0.725` and percentage `72.50`.

### Exercise 7. Can `numeric(5,2)` Store `999.995`?

**Answer:** no. After rounding to two decimal places, the value becomes `1000.00`, exceeding the three integer digits allowed by `numeric(5,2)`.

### Exercise 8. Why Doesn't Casting to `numeric` After `integer` Multiplication Prevent Overflow?

```sql
SELECT (50000::integer * 50000::integer)::numeric;
```

**Answer:** integer multiplication occurs **before** the cast, so it already overflows. Cast an operand beforehand:

```sql
SELECT 50000::numeric * 50000::integer;
```

### Exercise 9. Sum and Average of Two Integers

```sql
SELECT
    sum(v) AS total,
    avg(v) AS average,
    sum(v) / count(*) AS problematic_manual_average,
    sum(v)::numeric / count(*) AS exact_manual_average
FROM (VALUES (1::integer), (2::integer)) AS t(v);
```

**Answer:** `total = 3`; `average = 1.5`; the manual average is wrong because integer division yields `1`; the numeric-cast manual average yields `1.5`.

### Exercise 10. Is Storing Money as double Safe?

**Answer:** unsuitable when decimal exactness is required for billing and reconciliation, because numbers like `0.1` are not represented exactly in binary float. Use `numeric(p,s)` or minor-unit integers with explicit rules.

### Exercise 11. Choosing a Type for Large Totals

You need to store the count of processed events, which may exceed 2.1 billion.

**Answer:** consider `bigint`; when addition results could exceed 64-bit limits, use `numeric` or another suitable data model. Do not rely on `integer` just because current data volume is still small.

### Exercise 12. Aggregating Revenue by Product Code

```sql
SELECT
    product_code,
    SUM(quantity) AS items_sold,
    SUM(quantity::numeric * unit_price) AS revenue
FROM numeric_lab.sales
GROUP BY product_code
ORDER BY product_code;
```

**Answer:** `items_sold` is the total quantity; `revenue` is the pre-tax monetary total in the numeric domain. Check application mappings to receive `SUM(quantity)` in a type with sufficient range.

### Exercise 13. Finding Temperatures Near 25°C

Suppose a sensor has an acceptable tolerance of ±0.2°C. Write a query for this range:

```sql
SELECT sale_id, measured_temperature
FROM numeric_lab.sales
WHERE measured_temperature BETWEEN
    24.8::double precision AND 25.2::double precision;
```

**Explanation:** the ±0.2°C threshold is an example rule; `BETWEEN` is inclusive of both endpoints. For problems needing open bounds or different measurement rules, write the conditions explicitly.

### Exercise 14. Why Is `NaN` Not `NULL`?

**Answer:** `NaN` is a special value within numeric types, with its own sorting/comparison semantics in PostgreSQL. `NULL` represents a missing/unknown value in SQL logic. Proper validation is required to prevent storing `NaN` in monetary columns, not just `NOT NULL`.

### Exercise 15. Choosing a Type for Foreign Exchange Rates

If the business requires many fixed decimal places and exact reconciliation, you can use `numeric(p,s)` with a scale defined by business standards, such as `numeric(20,10)`. Do not pick `double precision` merely because exchange rates have long fractional parts.

## 20. Numeric Type Design Checklist

Before creating a numeric column, answer:

| Question | If the answer is… | Consider |
| --- | --- | --- |
| Can the data ever have a fractional part? | No, counting whole units | `integer` / `bigint` |
| Is absolute decimal exactness required? | Yes | `numeric(p,s)` |
| Is it a naturally approximate measurement? | Yes, with known error tolerance | `real` / `double precision` |
| How many digits can the integer part reach? | Very large | Verify precision/range |
| How many fractional digits are needed? | Per business rules | Define scale |
| What if values exceed limits? | Possible | Wider type, validation |
| What rounding policy applies? | Half-up, ties-even, truncation, per line or total | Design explicit calculations |
| Can intermediate multiplication/addition overflow? | Yes | Cast operands **before** the operation |
| Could data be NaN/infinity? | Not allowed | Finite-value validation/constraints |
| What type does the application read it into? | Java/JSON/other clients | Align types to avoid losing precision |
| Will the numeric column be indexed? | Yes | Benchmark query plans and parameter types |
| Are the data units clear? | Not yet | Name columns and API contracts clearly with units |

Do not pick a numeric type simply because "it can hold all example values". A good schema must reflect the **possible data domain**, **required precision**, and **how the system uses the values**.

## 21. Summary

PostgreSQL has multiple numeric types because numerical problems are not all alike:

1. **`smallint`, `integer`, `bigint`** store exact integers within defined ranges. Use them for quantities and IDs, paired with `CHECK` constraints to restrict business domains.
2. **`numeric`/`decimal`** store and compute exact decimal numbers. `numeric(p,s)` defines precision and scale; values may be rounded on write, then rejected if out of range.
3. **`real`/`double precision`** store approximate binary floating-point numbers. `double precision` has more significant digits than `real`, yet **does not turn 0.1 into an exact binary number**.
4. **Integer division truncates fractional parts**, and casting after the operation may be too late. To divide with fractional results or avoid overflow, convert operand types beforehand.
5. **`round`, `trunc`, `floor`, `ceil` are not equivalent**. Numeric rounds ties away from zero; monetary rounding policies must be explicitly defined.
6. **`SUM` and `AVG` return different types from their input columns**; verify this when manually computing ratios and mapping data to Java.
7. **`NaN`, infinity, and `NULL` are not the same**. Decide whether special values are permitted in a column.
8. **Numeric types must remain accurate end-to-end across the application**: PostgreSQL `numeric` pairs with Java `BigDecimal` and matching API contracts; do not convert to double midway expecting to regain precision later.
9. **Performance is a secondary trade-off after correctness**. Use the simplest type that meets the true value domain and precision needs, then benchmark workloads and design indexes appropriately.

An easy rule to remember: **use integers for counting; use numeric for money and decimals requiring reconciliation; use real or double precision for measurement data and calculations accepting error**. Always verify ranges, units, and rounding rules before adding a numeric type to a PostgreSQL schema.
