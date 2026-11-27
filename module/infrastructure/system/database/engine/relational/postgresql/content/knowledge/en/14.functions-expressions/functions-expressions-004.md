# Arithmetic Functions, Rounding, and Error Handling in PostgreSQL

In a database management system, calculations are not merely addition, subtraction, multiplication, and division. Whether a column has type `INTEGER`, `NUMERIC`, or `DOUBLE PRECISION` can make the exact same expression yield different results in **data type, decimal places, precision, and rounding behavior**.

For example, dividing `7 / 2` between two integers in PostgreSQL produces `3`, whereas `7::NUMERIC / 2` produces `3.5`. The value `12.345` cast into `NUMERIC(8,2)` is typically rounded to `12.35`. A calculation using `DOUBLE PRECISION` can introduce binary representation error even when two decimal numbers look completely simple to the user. Division by zero can cause an entire SQL statement to fail; casting after multiplying two `INTEGER` values cannot rescue a multiplication that has already overflowed.

Therefore, when writing analytical queries, processing orders, computing taxes, aggregating metrics, or calculating percentages, PostgreSQL developers need to understand simultaneously:

1. **What do arithmetic operators and functions do?**
2. **How do data types determine the result?**
3. **At which step does rounding/truncation happen?**
4. **When do we need to handle errors and unknown values?**
5. **How do we ensure results match business semantics?**

This lesson covers the operators `+`, `-`, `*`, `/`, `%`, the functions `ABS`, `SIGN`, `ROUND`, `TRUNC`, `FLOOR`, `CEIL`, `MOD`, `POWER`, `SQRT`, distinguishes exact decimal arithmetic from binary floating point, and presents techniques for handling division by zero, overflow, `NULL`, and accumulated rounding errors.

---

## 1. Learning Objectives

After this lesson, you will be able to:

- Use arithmetic operators and control **precedence** with parentheses.
- Distinguish integer division from decimal division; know when to **cast before computing**.
- Choose `NUMERIC/DECIMAL`, `INTEGER/BIGINT`, or `REAL/DOUBLE PRECISION` based on precision requirements.
- Use functions for absolute value, sign, rounding, truncation, floor, ceiling, modulo, exponentiation, and square root.
- Distinguish **round**, **trunc**, **floor**, and **ceil**, especially with negative numbers.
- Explain midpoint rounding behavior and differences between `NUMERIC` and floating point.
- Understand how `NUMERIC(p,s)` constrains digits and can round when assigning to a column.
- Identify binary floating-point error, compare floating-point numbers for near-equality, and understand epsilon limitations.
- Handle `division_by_zero`, overflow, invalid inputs, `NULL`, and special values explicitly.
- Calculate percentages, unit prices, quantities, taxes, and totals without rounding prematurely.
- Use `SUM`, `AVG`, and aggregates appropriately for the input types.
- Write and verify practical queries on PostgreSQL.

Examples use modern PostgreSQL syntax. Table creation/deletion sections are strictly for a **practice database**; never run them directly on an environment containing data you need to keep.

## 2. The Big Picture: Numeric Types Are Part of the Calculation

PostgreSQL provides several numeric types with distinct characteristics:

| Type | Characteristics | Suitable Scenarios | Things to Watch |
| --- | --- | --- | --- |
| `SMALLINT` | 2-byte integer | Small counters, numeric status codes | Narrow range |
| `INTEGER` / `INT` | 4-byte integer | Quantities, IDs, medium counters | Integer division; overflow |
| `BIGINT` | 8-byte integer | Large quantities, smallest currency units | Still has limits |
| `NUMERIC(p,s)` / `DECIMAL(p,s)` | Decimal with controlled precision | Money, decimal measurements, rates | Compute overhead, scale, rounding |
| `NUMERIC` | Decimal unconstrained by column-level `p,s` | Intermediate calculations needing many digits | Does not replace range validation |
| `REAL` | 4-byte binary floating point | Measurements/estimates tolerating small error | Roughly 6 significant decimal digits |
| `DOUBLE PRECISION` | 8-byte binary floating point | Statistics, science, approximate arithmetic | Roughly 15 significant decimal digits |
| `MONEY` | Specialized currency type, locale-dependent formatting | Certain legacy/specialized systems | Does not store currency code; less flexible than `numeric` in many cases |

Precision/accuracy has **two meanings to distinguish**:

- **Data type precision:** how many digits and what rules represent a value.
- **Business correctness of the result:** whether the formula, units, rounding, and input data match requirements.

A calculation using `NUMERIC` can be exact in decimal arithmetic yet **still be business-wrong** if it uses the wrong exchange rate, adds two different currencies, or rounds a unit price before multiplying by quantity.

### 2.1. Exact vs. Approximate

`NUMERIC` represents many finite decimal values such as `0.1`, `0.01`, and `12.345` accurately within type limits, whereas binary floating point cannot represent all such decimal fractions exactly.

Example:

```sql
SELECT
    0.1::NUMERIC + 0.2::NUMERIC AS decimal_sum,
    0.1::DOUBLE PRECISION + 0.2::DOUBLE PRECISION
        AS floating_sum;
```

Both display near `0.3`, yet in binary floating point, representation error can cause exact equality checks to fail.

This does not mean `NUMERIC` has infinite precision in every operation. Dividing `1/3` has a non-terminating decimal expansion; PostgreSQL must still produce a finite result under its decimal arithmetic rules.

---

## 3. Preparing the Practice Database

To run examples without affecting real data, create a separate schema:

> **Warning:** The `DROP TABLE IF EXISTS` statements in the practice section delete existing data in the matching tables under schema `arithmetic_lab`. Run only in a test database that may be reset.

```sql
CREATE SCHEMA IF NOT EXISTS arithmetic_lab;

DROP TABLE IF EXISTS arithmetic_lab.order_lines;
DROP TABLE IF EXISTS arithmetic_lab.sensor_readings;

CREATE TABLE arithmetic_lab.order_lines (
    line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL,
    quantity NUMERIC(12,3) NOT NULL
        CHECK (quantity > 0),
    unit_price NUMERIC(16,4) NOT NULL
        CHECK (unit_price >= 0),
    discount_rate NUMERIC(7,5) NOT NULL DEFAULT 0
        CHECK (discount_rate BETWEEN 0 AND 1),
    line_gross NUMERIC(20,4)
        GENERATED ALWAYS AS (
            quantity * unit_price
        ) STORED
);

CREATE TABLE arithmetic_lab.sensor_readings (
    reading_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sensor_code TEXT NOT NULL,
    reading_value DOUBLE PRECISION,
    expected_value DOUBLE PRECISION,
    measured_at TIMESTAMPTZ NOT NULL
);
```

We use `NUMERIC` for monetary calculations and `DOUBLE PRECISION` for illustrative measurement data.

Insert data:

```sql
INSERT INTO arithmetic_lab.order_lines (
    sku, quantity, unit_price, discount_rate
)
VALUES
    ('ITEM-A',   2.000,  19.9900, 0.00000),
    ('ITEM-B',   1.500,   4.2000, 0.10000),
    ('ITEM-C', 100.000,   0.0150, 0.00000),
    ('ITEM-D',   3.000,  12.3450, 0.07500),
    ('ITEM-E',   1.000, 100.0000, 0.15000);

INSERT INTO arithmetic_lab.sensor_readings (
    sensor_code, reading_value, expected_value, measured_at
)
VALUES
    ('TEMP-A', 23.5,     23.5, '2026-11-01 09:00:00+00'),
    ('TEMP-A', 23.50001, 23.5, '2026-11-01 09:01:00+00'),
    ('TEMP-B',  0.1,      0.1, '2026-11-01 09:02:00+00'),
    ('TEMP-B', NULL,     10.0, '2026-11-01 09:03:00+00');
```

Inspect the data:

```sql
SELECT
    line_id, sku, quantity, unit_price,
    discount_rate, line_gross
FROM arithmetic_lab.order_lines
ORDER BY line_id;

SELECT *
FROM arithmetic_lab.sensor_readings
ORDER BY reading_id;
```

The `line_gross` value is computed by the database as `quantity * unit_price`. It is the amount **before discount**, keeping four fractional digits per the column definition. This is illustrative data, not a complete invoicing system.

---

## 4. Basic Arithmetic Operators

Common operators:

| Operator | Meaning | Example |
| --- | --- | --- |
| `+` | Addition | `5 + 3` |
| `-` | Subtraction | `5 - 3` |
| `*` | Multiplication | `5 * 3` |
| `/` | Division | `10 / 4` |
| `%` | Modulo | `10 % 4` |
| `^` | Exponentiation in PostgreSQL | `2 ^ 3` |
| `+x` | Unary plus | `+5` |
| `-x` | Sign negation | `-5` |

Try a SQL query:

```sql
SELECT
    12 + 5 AS added,
    12 - 5 AS subtracted,
    12 * 5 AS multiplied,
    12 / 5 AS integer_quotient,
    12 % 5 AS remainder,
    2 ^ 3 AS power_result;
```

For the two integers `12` and `5`, the quotient `12 / 5` is **2**, not 2.4. The remainder `12 % 5` is **2**.

### 4.1. Parentheses and Operator Precedence

Unclear style:

```sql
SELECT 10 + 2 * 3 AS result;
```

The result is **16**, because multiplication has higher precedence than addition.

Parentheses change the calculation:

```sql
SELECT (10 + 2) * 3 AS result;
```

Result: **36**.

When a formula includes percentages, fees, taxes, or multiple terms, always use parentheses to express intent:

```sql
SELECT
    (100::NUMERIC - 15::NUMERIC)
      * (1::NUMERIC + 0.08::NUMERIC)
        AS net_plus_tax;
```

In this example, the discounted price is 85, and after an assumed 8% tax it is 91.8.

Do not rely on guessing operator precedence in formulas with critical business value.

### 4.2. Subtraction and Negative Numbers

```sql
SELECT
    -7 + 2 AS a,
    -7 - 2 AS b,
    -7 * 2 AS c;
```

Results respectively: -5, -9, -14.

A formula producing a negative result does not mean PostgreSQL is wrong. Whether negative values are allowed is a **constraint on each data field**: profit can be negative, list price is normally non-negative, and adjustment entries can carry a negative sign.

---

## 5. Integer Division: A Classic Trap

In PostgreSQL, dividing two integer operands returns an integer quotient, **truncating the fractional part toward zero**.

```sql
SELECT
    7 / 2 AS int_division,
    -7 / 2 AS negative_int_division,
    7::NUMERIC / 2 AS decimal_division,
    7 / 2::NUMERIC AS cast_right_operand;
```

Meaningful results:

| Expression | Result |
| --- | ---: |
| `7 / 2` | 3 |
| `-7 / 2` | -3 |
| `7::NUMERIC / 2` | 3.5 |
| `7 / 2::NUMERIC` | 3.5 |

**-7 / 2 = -3**, not -4, because integer division truncates toward zero. That differs from `FLOOR(-3.5)`, which gives -4.

### 5.1. Cast Before, Not After

Two very different expressions:

```sql
SELECT
    (7 / 2)::NUMERIC AS cast_after_division,
    7::NUMERIC / 2 AS cast_before_division;
```

Results:

- `(7 / 2)::NUMERIC` -> **3**; the fraction was already lost before casting.
- `7::NUMERIC / 2` -> **3.5**; one operand was converted to a decimal type before division.

Similarly:

```sql
SELECT
    100 * (3 / 4) AS wrong_fraction,
    100::NUMERIC * 3 / 4 AS correct_fraction;
```

The results are 0 vs. 75, because `3 / 4` evaluates to 0 in integer division.

### 5.2. Percentages Can Become 0 Due to Integer Division

For example, a rate of 3 successful orders out of 10:

```sql
SELECT
    3 / 10 * 100 AS wrong_percent,
    3::NUMERIC / 10 * 100 AS correct_percent;
```

Results:

- First approach: **0**.
- Second approach: **30**.

A common analytics mistake is computing:

```sql
COUNT(*) / total_count
```

when both operands are integers. When you need a ratio with a fractional part, cast to `NUMERIC` or an appropriate type before dividing.

### 5.3. Decimal Literals Also Affect Types

```sql
SELECT
    7 / 2 AS integer_case,
    7.0 / 2 AS decimal_literal_case,
    7::DOUBLE PRECISION / 2 AS float_case;
```

In PostgreSQL, a literal with a decimal point like `7.0` is generally interpreted as `numeric` absent another casting context; it is not necessarily `double precision`. To choose the type deliberately, cast explicitly with `::NUMERIC` or `::DOUBLE PRECISION`.

Do not rely on parser-inferred types as an uncontrolled part of an important formula.

---

## 6. Remainder and Integer Quotient: %, MOD, and DIV

**Remainders** are useful for parity checks, cyclic grouping, or finding positions in a cycle.

```sql
SELECT
    10 % 3 AS remainder_operator,
    MOD(10, 3) AS remainder_function,
    10 / 3 AS integer_quotient;
```

Results: remainder 1, integer quotient 3.

### 6.1. Remainders with Negative Numbers

```sql
SELECT
    MOD(7, 3) AS positive_case,
    MOD(-7, 3) AS negative_dividend,
    MOD(7, -3) AS negative_divisor;
```

Under PostgreSQL's integer remainder rule paired with truncation-toward-zero division:

- `MOD(7,3)` -> 1.
- `MOD(-7,3)` -> -1.
- `MOD(7,-3)` -> 1.

Do not assume `MOD` always returns a value in `0..m-1` when negative values appear. If an algorithm requires a non-negative remainder for a positive divisor `m`, define an explicit normalization such as:

```sql
SELECT
    MOD(MOD(-7, 3) + 3, 3) AS nonnegative_modulo;
```

The result is 2. That formula only illustrates **positive m = 3**; validate `m > 0` in the general case.

### 6.2. The DIV Function

PostgreSQL also provides `DIV(y, x)` for obtaining an integer quotient in numeric contexts:

```sql
SELECT
    DIV(7::NUMERIC, 2::NUMERIC) AS quotient_positive,
    DIV((-7)::NUMERIC, 2::NUMERIC) AS quotient_negative;
```

Results represent truncated quotients: 3 and -3.

`DIV` is not a substitute for decimal division; if you need 3.5, use `7::NUMERIC / 2`.

### 6.3. Do Not Call MOD with a Divisor of 0

```sql
-- This statement is for observing the error; do not run inside a transaction you want to keep.
SELECT MOD(10, 0);
```

PostgreSQL raises a division-by-zero error. Techniques for handling division by zero are covered separately later.

---

## 7. ABS and SIGN: Absolute Value and Sign

### 7.1. ABS

`ABS(x)` returns the absolute value, i.e., the non-negative magnitude of a number:

```sql
SELECT
    ABS(-12) AS abs_negative,
    ABS(12) AS abs_positive,
    ABS(0) AS abs_zero,
    ABS(-12.345::NUMERIC) AS abs_decimal;
```

Results respectively: 12, 12, 0, 12.345.

Applications:

- Measuring absolute deviation between an actual value and an expected value.
- Counting or summing discrepancy magnitudes regardless of sign.
- Checking whether a value falls within a tolerance band.

Example:

```sql
SELECT
    ABS(100.12::NUMERIC - 100.00::NUMERIC)
        AS absolute_difference;
```

Result: 0.12.

**Note:** if using a signed integer type at its minimum boundary, the absolute value may not fit in the same integer type. For example, the absolute value of the minimum `BIGINT` exceeds the maximum positive `BIGINT`.

Therefore, for cases that might touch boundaries, cast to `NUMERIC` before taking the absolute value:

```sql
SELECT ABS((-9223372036854775808)::NUMERIC)
    AS safe_big_abs;
```

### 7.2. SIGN

`SIGN(x)` returns the sign of a number:

- -1 if `x < 0`.
- 0 if `x = 0`.
- 1 if `x > 0`.

```sql
SELECT
    SIGN(-15::NUMERIC) AS negative_sign,
    SIGN(0::NUMERIC) AS zero_sign,
    SIGN(15::NUMERIC) AS positive_sign;
```

In business logic, `SIGN` can classify upward/downward movement:

```sql
SELECT
    SIGN(95::NUMERIC - 100::NUMERIC) AS movement_direction;
```

Result: -1. However, do not use `SIGN` in place of storing the actual delta when the **magnitude** of change matters.

### 7.3. ABS Is Not a Universal Near-Equality Check

With floating point, a check like:

```sql
ABS(a - b) < 0.000001
```

only makes sense if you chose an appropriate tolerance for the **units and scale**. An error of 0.000001 can be tiny for data measured in millions of units, yet huge for microscopic measurements.

A later section covers comparing floating-point numbers using both absolute and relative tolerances.

---

## 8. ROUND, TRUNC, FLOOR, CEIL: Four Different Operations

This group of functions is essential because they are frequently used in money, reporting, scores, ratios, and measurements.

| Function | Behavior | Positive Example | Negative Example |
| --- | --- | --- | --- |
| `ROUND(x)` | Rounds to nearest integer per data type rules | `ROUND(2.7::NUMERIC) = 3` | `ROUND(-2.7::NUMERIC) = -3` |
| `TRUNC(x)` | Truncates fractional part toward 0 | `TRUNC(2.7::NUMERIC) = 2` | `TRUNC(-2.7::NUMERIC) = -2` |
| `FLOOR(x)` | Largest integer not exceeding x | `FLOOR(2.7) = 2` | `FLOOR(-2.7) = -3` |
| `CEIL(x)` / `CEILING(x)` | Smallest integer not less than x | `CEIL(2.7) = 3` | `CEIL(-2.7) = -2` |

### 8.1. Practicing Positive and Negative Numbers

```sql
SELECT
    ROUND( 3.7::NUMERIC) AS round_positive,
    TRUNC( 3.7::NUMERIC) AS trunc_positive,
    FLOOR( 3.7::NUMERIC) AS floor_positive,
    CEIL(  3.7::NUMERIC) AS ceil_positive,

    ROUND(-3.7::NUMERIC) AS round_negative,
    TRUNC(-3.7::NUMERIC) AS trunc_negative,
    FLOOR(-3.7::NUMERIC) AS floor_negative,
    CEIL( -3.7::NUMERIC) AS ceil_negative;
```

Results:

| Value | ROUND | TRUNC | FLOOR | CEIL |
| ---: | ---: | ---: | ---: | ---: |
| 3.7 | 4 | 3 | 3 | 4 |
| -3.7 | -4 | -3 | -4 | -3 |

**Key distinction:** `TRUNC(-3.7)` is -3, whereas `FLOOR(-3.7)` is -4.

### 8.2. When to Use FLOOR/CEIL?

Suppose a warehouse has a total weight of 25.1 kg and ships only in **10 kg boxes**. If the business rule requires rounding up the number of boxes:

```sql
SELECT
    CEIL(25.1::NUMERIC / 10::NUMERIC)
        AS required_box_count;
```

Result: 3.

If counting only full boxes:

```sql
SELECT
    FLOOR(25.1::NUMERIC / 10::NUMERIC)
        AS full_box_count;
```

Result: 2.

Both functions are right for **two different questions**. You cannot simply ask "which rounding function should I use?" without first defining the business rule.

### 8.3. TRUNC Does Not Mean Data Has Been Validated

```sql
SELECT
    TRUNC(19.999::NUMERIC, 2) AS truncated_money,
    ROUND(19.999::NUMERIC, 2) AS rounded_money;
```

Results are 19.99 and 20.00, respectively.

If an API requires clients to send at most two decimal places, both transformations can **hide input errors**. In that case, the proper workflow is validating input upfront and rejecting `19.999`, rather than silently turning it into another value.

---

## 9. ROUND with a Second Parameter: Rounding Width

PostgreSQL supports:

```sql
ROUND(value::NUMERIC, decimal_places)
```

where `decimal_places` specifies how many digits after the decimal point to keep.

```sql
SELECT
    ROUND(12.34567::NUMERIC, 0) AS zero_places,
    ROUND(12.34567::NUMERIC, 1) AS one_place,
    ROUND(12.34567::NUMERIC, 2) AS two_places,
    ROUND(12.34567::NUMERIC, 4) AS four_places;
```

Arithmetic results:

| Requested Scale | Result |
| ---: | ---: |
| 0 | 12 |
| 1 | 12.3 |
| 2 | 12.35 |
| 4 | 12.3457 |

### 9.1. Negative Scale: Rounding the Integer Part

The second parameter can be negative, rounding to the nearest ten, hundred, or thousand.

```sql
SELECT
    ROUND(12345.678::NUMERIC, -1) AS nearest_ten,
    ROUND(12345.678::NUMERIC, -2) AS nearest_hundred,
    ROUND(12345.678::NUMERIC, -3) AS nearest_thousand;
```

Results:

- Nearest ten: 12350.
- Nearest hundred: 12300.
- Nearest thousand: 12000.

A negative scale parameter in the **ROUND function** is distinct from declaring scale in a `NUMERIC(p,s)` column, although modern PostgreSQL also supports extended scale capabilities in type definitions.

### 9.2. TRUNC Can Also Accept Digit Count

```sql
SELECT
    TRUNC(123.4567::NUMERIC, 2) AS trunc_two,
    TRUNC(123.4567::NUMERIC, 0) AS trunc_zero,
    TRUNC(123.4567::NUMERIC, -1) AS trunc_tens;
```

Results respectively: 123.45, 123, 120.

With negative numbers:

```sql
SELECT
    TRUNC(-123.4567::NUMERIC, 2) AS neg_trunc,
    ROUND(-123.4567::NUMERIC, 2) AS neg_round;
```

Results: -123.45 and -123.46.

### 9.3. When a Value Is Exactly Halfway Between Two Rounding Levels

For `NUMERIC`, PostgreSQL rounds ties **away from zero** (*ties away from zero*) under its default rounding rule.

```sql
SELECT
    ROUND( 2.5::NUMERIC) AS plus_two_point_five,
    ROUND(-2.5::NUMERIC) AS minus_two_point_five,
    ROUND( 1.235::NUMERIC, 2) AS plus_three_digits,
    ROUND(-1.235::NUMERIC, 2) AS minus_three_digits;
```

Results:

| Numeric Input | After ROUND |
| --- | ---: |
| 2.5 | 3 |
| -2.5 | -3 |
| 1.235 to 2 digits | 1.24 |
| -1.235 to 2 digits | -1.24 |

**Do not assume the same rule applies to `DOUBLE PRECISION`.** Tie handling in `round(double precision)` depends on the floating-point/platform mechanism, typically round-to-nearest-even in common environments.

Example:

```sql
SELECT
    ROUND(2.5::NUMERIC) AS decimal_round,
    ROUND(2.5::DOUBLE PRECISION) AS float_round;
```

In common IEEE environments, the `numeric` result is 3, while the `double` result may be 2 under round-to-nearest-even. Never build monetary logic on assumptions about cross-platform floating-point rounding.

### 9.4. Two-Argument ROUND Requires Compatible NUMERIC Type

An important API difference:

```sql
-- Valid:
SELECT ROUND(12.345::NUMERIC, 2);
```

However, in PostgreSQL, the form:

```sql
-- EXPECTED ERROR: no round(double precision, integer)
-- under standard function signatures.
SELECT ROUND(12.345::DOUBLE PRECISION, 2);
```

normally reports that no matching function exists for those argument types.

The fix is converting to `NUMERIC` **if that cast matches your requirements**, then calling the function:

```sql
SELECT ROUND((12.345::DOUBLE PRECISION)::NUMERIC, 2);
```

Still, casting a value that has already passed through floating point to `NUMERIC` **does not restore lost input precision**. If exact decimals are needed, parse and store as `NUMERIC` from the start.

---

## 10. NUMERIC(p,s): Precision, Scale, and Rounding on Storage

The declaration:

```sql
amount NUMERIC(12,2)
```

commonly means:

- A total of **12 significant decimal digits** in the declared range.
- Keeping **2 digits after the decimal point**.
- Allowing up to **10 integer digits** in the standard `0 <= scale <= precision` form.

Example:

```sql
SELECT
    123.456::NUMERIC(8,2) AS rounded_on_cast;
```

The result is **123.46**.

This is crucial: when a value is cast into `NUMERIC(p,s)`, PostgreSQL can **round it to the column's scale** rather than always raising an error when an input has extra decimal digits.

### 10.1. Scale Is Not an Input Format Validator

If a user enters `19.999` while business rules allow at most two decimal places:

```sql
SELECT 19.999::NUMERIC(8,2) AS stored_value;
```

the result can be **20.00**.

Therefore:

- If **rounding is permitted**, document the rule and perform it deliberately.
- If inputs with more than two decimal digits **must be rejected**, validate the **raw input before casting**.
- Do not write a constraint like `CHECK(amount = ROUND(amount,2))` on a column already typed as `NUMERIC(...,2)` expecting to prove the input had at most 2 decimal places; the value may already have been rounded before `CHECK` runs.

### 10.2. Precision Can Overflow After Rounding

```sql
SELECT 999.99::NUMERIC(5,2) AS valid_amount;
```

This is valid because the integer part has three digits.

However:

```sql
-- EXPECTED ERROR: integer part exceeds NUMERIC(5,2) capacity.
SELECT 1000.00::NUMERIC(5,2);
```

is rejected.

Even a boundary-adjacent value like `999.995` can round up to `1000.00` and **then exceed the column's precision limit**.

### 10.3. Do Not Use Scale 2 for Every Value

| Quantity | Example Type | Why |
| --- | --- | --- |
| Final USD amount | `NUMERIC(18,2)` | Stored to the cent per business contract |
| Unit price for small items | `NUMERIC(18,4)` | Can be less than one cent |
| Exchange rate | `NUMERIC(24,10)` | Needs extra digits to reduce drift when multiplying |
| Quantity / weight | `NUMERIC(12,3)` | Quantities with fractional units of measure |
| Tax rate as 0..1 ratio | `NUMERIC(9,6)` | Needs ratio precision |
| Intermediate value | `NUMERIC` | Avoid constraining scale prematurely |

These are examples, not mandatory rules. Choose precision and scale based on **possible value ranges and operations**.

---

## 11. Floating-Point Error: Why Does 0.1 + 0.2 Hardly Equal 0.3?

`REAL` and `DOUBLE PRECISION` use **binary floating-point** representation. The decimal fraction `0.1` has no finite binary expansion, so the stored value is an approximation.

Try:

```sql
SELECT
    (0.1::DOUBLE PRECISION + 0.2::DOUBLE PRECISION)
        AS calculated,
    0.3::DOUBLE PRECISION
        AS expected,
    (
        0.1::DOUBLE PRECISION
        + 0.2::DOUBLE PRECISION
        = 0.3::DOUBLE PRECISION
    ) AS equal_as_floats;
```

In most common binary floating-point environments, the exact equality comparison in this example can return **FALSE**, because the two sides hold binary approximations near 0.3 that are not bit-identical.

Compare with:

```sql
SELECT
    (0.1::NUMERIC + 0.2::NUMERIC)
      = 0.3::NUMERIC AS equal_as_decimal;
```

Result: TRUE.

### 11.1. Display Precision Differs from Internal Precision

PostgreSQL may format a floating-point number as a short readable string depending on output rules and `extra_float_digits`:

```sql
SHOW extra_float_digits;
```

Seeing `0.3` on screen **does not prove** that the floating-point number is stored as the exact decimal fraction 3/10.

Do not cast to text or rely on displayed digits to decide whether two floating-point calculations are truly equal.

### 11.2. Addition Order Can Affect Floating-Point Sums

Floating-point addition rounds at each step to finite significant bits. Computationally, a sum can therefore depend on addition order when numbers differ widely in magnitude.

Conceptual example:

```text
1e16 + 1 - 1e16

If adding 1e16 and 1 loses the 1
due to finite precision:
    the final result can be 0

Whereas grouping 1 + (-1e16) and then adding 1e16
also undergoes different rounding steps.
```

An example showing ordering clearly on many IEEE systems:

```sql
SELECT
    (
        (1e16::DOUBLE PRECISION + 1::DOUBLE PRECISION)
        - 1e16::DOUBLE PRECISION
    ) AS first_order,

    (
        1e16::DOUBLE PRECISION
        + (1::DOUBLE PRECISION - 1e16::DOUBLE PRECISION)
    ) AS second_order;
```

Both orderings in this specific example **can lose the 1**; the key point is the non-associativity of floating-point arithmetic. To see a sharper difference, compare:

```sql
SELECT
    (
        (1e16::DOUBLE PRECISION
          + (-1e16)::DOUBLE PRECISION)
        + 1::DOUBLE PRECISION
    ) AS cancel_first,

    (
        1e16::DOUBLE PRECISION
        + ((-1e16)::DOUBLE PRECISION
          + 1::DOUBLE PRECISION)
    ) AS add_small_to_large_first;
```

In common IEEE environments, `cancel_first` is 1, whereas `add_small_to_large_first` can be 0.

With `SUM(double precision)` over large datasets, parallel query plans and differing evaluation orders can also produce tiny variations in the least significant digits. Never assume floating-point sums produce identical bit patterns across every execution plan.

### 11.3. Does NUMERIC Eliminate All Errors?

`NUMERIC` is well suited when you need **exact finite decimals** or decimal arithmetic with controlled precision. Yet it does not magically turn every operation into infinite-precision math:

- `1 / 3` has no finite decimal representation.
- Exponentiation, roots, and logarithms can require approximations.
- Casting to `NUMERIC(p,s)` can round.
- Operations performed in the wrong order still yield wrong business results.
- Precision already lost in a `double` cannot be recovered to its original intent merely by casting.

Choosing `NUMERIC` is a **representation decision**, not a substitute for rounding design and validation.

---

## 12. Comparing Two Nearly Equal Floating-Point Numbers

When computing with floating point for measurements or simulations, comparing:

```sql
actual_value = expected_value
```

can be overly strict when two values differ solely by computational rounding noise.

A common approach is checking **absolute difference**:

```sql
SELECT
    ABS(
        (0.1::DOUBLE PRECISION + 0.2::DOUBLE PRECISION)
        - 0.3::DOUBLE PRECISION
    ) < 1e-12::DOUBLE PRECISION AS nearly_equal;
```

In common IEEE environments, the result is TRUE.

### 12.1. Choose Epsilon by Units

`epsilon = 0.000001` has very different meanings across:

- Temperature error in degrees Celsius.
- Distance error in meters.
- Timing error in microseconds.
- Converted currency amounts.

There is no single epsilon right for every domain. If you need accuracy to 0.01 USD, use an exact currency representation rather than comparing `double` values with an arbitrary epsilon.

### 12.2. Combining Absolute and Relative Tolerance

When values can be very large or very small, you can use:

```sql
SELECT
    ABS(actual_value - expected_value)
        <= GREATEST(
            0.000001::DOUBLE PRECISION,
            0.000001::DOUBLE PRECISION
                * GREATEST(
                    ABS(actual_value),
                    ABS(expected_value)
                )
        ) AS approximately_equal
FROM arithmetic_lab.sensor_readings
WHERE actual_value IS NOT NULL
  AND expected_value IS NOT NULL;
```

Here:

- The left side is the absolute difference.
- The first `0.000001` is an illustrative absolute tolerance.
- The term multiplied by the larger magnitude is a relative tolerance.
- `GREATEST` picks the larger of the two tolerance thresholds.

**This is an illustrative formula**, not a universal error standard. Thresholds must be engineered for your measurement requirements, hardware, value range, and business sensitivity.

### 12.3. Avoid Epsilon When Comparing Settled Monetary Amounts

If a transaction must pay exactly **19.99 USD**, using:

```sql
ABS(amount_float - 19.99) < 0.01
```

can treat values differing by nearly a cent as "equal." In a payment system, that can be unacceptable.

For settled amounts, store `NUMERIC` with an appropriate scale or integers in minor units, and test equality under the currency contract.

### 12.4. NULL and NaN in Near-Equality Checks

A comparison involving `NULL` normally yields UNKNOWN and is filtered out in `WHERE`. Special values like `NaN` or infinity may require separate handling per data policy; do not assume epsilon formulas automatically check finiteness.

---

## 13. Special Values: NaN and Infinity

PostgreSQL floating-point types can represent special values such as:

- `NaN` — Not a Number.
- `Infinity` — positive infinity.
- `-Infinity` — negative infinity.

These can be demonstrated with explicitly cast literals:

```sql
SELECT
    'NaN'::DOUBLE PRECISION AS float_nan,
    'Infinity'::DOUBLE PRECISION AS float_positive_inf,
    '-Infinity'::DOUBLE PRECISION AS float_negative_inf;
```

Modern PostgreSQL's `NUMERIC` type also supports these special values under appropriate conditions/declarations, although precision/scale limits may prevent storing certain special values.

### 13.1. PostgreSQL Has Its Own NaN Comparison Rules

Do not assume every SQL DBMS uses identical IEEE semantics for comparing `NaN`. PostgreSQL defines ordering rules to support sorting and indexing, in which `NaN` values can compare equal to each other and greater than all non-`NaN` numeric values when comparing/sorting.

Try in the lab:

```sql
SELECT
    'NaN'::DOUBLE PRECISION = 'NaN'::DOUBLE PRECISION
        AS pg_nan_equals_nan,
    'NaN'::DOUBLE PRECISION > 1000::DOUBLE PRECISION
        AS pg_nan_greater_than_number;
```

Therefore, a `CHECK (value >= 0)` **does not automatically prove a value is a valid finite number** if the data type allows `NaN` or infinity.

If the application accepts only finite measurements, validate in the application or add constraints designed specifically for your data type and PostgreSQL version. Never treat `NaN` as a valid sensor reading merely because it has type `DOUBLE PRECISION`.

### 13.2. Infinity Is Not the Default Handling for Division by Zero

In many programming languages, floating-point division by zero produces Infinity. In PostgreSQL SQL, however:

```sql
-- EXPECTED ERROR division_by_zero.
SELECT 1.0::DOUBLE PRECISION / 0.0::DOUBLE PRECISION;
```

Do not expect this expression to return infinity to handle later; PostgreSQL raises a division-by-zero error. Check the denominator explicitly before dividing.

---

## 14. Division by Zero: Errors and Handling

Pattern:

```sql
SELECT 100 / 0;
```

raises the error:

```text
ERROR: division by zero
SQLSTATE: 22012
```

Inside an explicit transaction, an error places the transaction into an aborted state; the application must `ROLLBACK` or roll back to a savepoint appropriately rather than continuing as if no error occurred.

### 14.1. Using NULLIF to Avoid Division by Zero

`NULLIF(a,b)` returns `NULL` if both values are equal; otherwise, it returns `a`.

Example:

```sql
SELECT
    100::NUMERIC / NULLIF(0::NUMERIC, 0::NUMERIC)
        AS safe_ratio;
```

`NULLIF(0,0)` returns NULL, turning the division into `100 / NULL`, which returns NULL instead of raising a division-by-zero error.

With a non-zero denominator:

```sql
SELECT
    100::NUMERIC / NULLIF(4::NUMERIC, 0::NUMERIC)
        AS ratio;
```

Result: 25.

### 14.2. Example Computing Averages for Potentially Empty Groups

Suppose there are columns `success_count` and `total_count`:

```sql
SELECT
    success_count::NUMERIC
       / NULLIF(total_count, 0) AS success_ratio
FROM some_daily_metrics;
```

This is a SQL snippet for a hypothetical `some_daily_metrics` table not created in the lab.

If `total_count = 0`, the ratio returns NULL. This is usually the right representation: **insufficient denominator to define a ratio**.

### 14.3. Should You COALESCE a NULL Result to 0?

```sql
SELECT COALESCE(
    100::NUMERIC / NULLIF(0::NUMERIC, 0::NUMERIC),
    0::NUMERIC
) AS ratio_or_zero;
```

This returns 0.

Think carefully: does **an undefined ratio** genuinely mean **a ratio of 0**?

| Scenario | Meaning |
| --- | --- |
| 0 successes out of 10 attempts | 0% success rate |
| 0 successes out of 0 attempts | No observations, undefined rate |
| 5 successes out of 0 attempts | Inconsistent data or different definition |
| `total_count` is NULL | Denominator information unavailable |

If a report should show a dash or "N/A" when there is no denominator, keeping NULL is often better. Use `COALESCE` only when business rules explicitly define it.

### 14.4. Using CASE for Explicit Branching

```sql
SELECT CASE
    WHEN 0 = 0 THEN NULL::NUMERIC
    ELSE 100::NUMERIC / 0::NUMERIC
END AS guarded_result;
```

This illustrates the branching idea, though PostgreSQL carries a **planner caveat**: constant expressions like `1/0` can sometimes be pre-evaluated during planning even inside a `CASE` branch you expect not to run.

Therefore, do not rely on a `CASE` containing a constant division by zero to guarantee every error is avoided. In real queries with column denominators, `numerator / NULLIF(denominator, 0)` is usually shorter and easier to verify.

### 14.5. NULLIF Does Not Fix Bad Data

Using `NULLIF` prevents an error at the division operation, but if `total_count = 0` occurs in a situation where business rules say it **must never be 0**, you should still detect and fix the source data rather than hiding the anomaly behind a silent NULL.

---

## 15. NULL in Arithmetic Operations

Most common PostgreSQL arithmetic operators and functions behave this way: when an input is NULL, the result is NULL.

```sql
SELECT
    10 + NULL::INTEGER AS add_null,
    10 * NULL::INTEGER AS multiply_null,
    ABS(NULL::NUMERIC) AS abs_null,
    ROUND(NULL::NUMERIC, 2) AS round_null;
```

All these expressions return NULL.

### 15.1. NULL Is Not 0

Suppose a table has a nullable `discount_rate` column:

- `discount_rate = 0`: explicitly known to have no discount.
- `discount_rate IS NULL`: discount rate unknown or not applicable in the model.
- The two states can carry different meanings.

If you write:

```sql
COALESCE(discount_rate, 0)
```

you are **deciding** to treat missing values as 0. That can be right as a business default, but should not be applied blindly to every dataset.

### 15.2. NULLIF and COALESCE

```sql
SELECT
    NULLIF(5, 5) AS equal_to_null,
    NULLIF(5, 3) AS different_remains,
    COALESCE(NULL::INTEGER, 8) AS first_nonnull,
    COALESCE(NULL::NUMERIC, NULL::NUMERIC, 2.5::NUMERIC)
        AS third_value;
```

Meaning:

- `NULLIF(5,5)` -> NULL.
- `NULLIF(5,3)` -> 5.
- `COALESCE(NULL,8)` -> 8.
- `COALESCE(NULL,NULL,2.5)` -> 2.5.

Do not apply `COALESCE` unconditionally to turn corrupted data, missing data, or division-by-zero results into artificially valid numbers.

### 15.3. SUM and AVG Ignore NULL Inputs

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(reading_value) AS known_readings,
    SUM(reading_value) AS sum_readings,
    AVG(reading_value) AS average_reading
FROM arithmetic_lab.sensor_readings;
```

The lab table has four rows, one of which has a NULL `reading_value`.

- `COUNT(*)` counts 4 rows.
- `COUNT(reading_value)` counts 3 non-NULL values.
- `SUM` and `AVG` ignore NULL `reading_value` entries per aggregate rules.

If all readings are NULL, `AVG` and `SUM` return NULL, not 0.

---

## 16. Overflow, Underflow, and Numeric Range Limits

An operation can have a **correct formula** yet produce a result that cannot be represented by the chosen data type.

### 16.1. Integer Overflow

`INTEGER` has the signed integer range:

```text
-2147483648 ... 2147483647
```

Example:

```sql
-- EXPECTED ERROR: INTEGER overflow.
SELECT 2147483647::INTEGER + 1::INTEGER;
```

If an addition may exceed the `INTEGER` range, cast **before adding**:

```sql
SELECT
    2147483647::BIGINT + 1::BIGINT
        AS safe_bigint_sum;
```

Result: 2147483648, valid within `BIGINT`.

### 16.2. BIGINT Also Has Limits

`BIGINT` has the range:

```text
-9223372036854775808 ... 9223372036854775807
```

For numbers that may exceed this range, use `NUMERIC` for calculation steps or redesign the data model.

```sql
SELECT
    9000000000000000000::NUMERIC
      + 9000000000000000000::NUMERIC
        AS decimal_large_sum;
```

Result: 18000000000000000000, exceeding `BIGINT` while fitting comfortably in `NUMERIC` in this example.

### 16.3. Casting After Multiplication Can Be Too Late

Wrong example:

```sql
-- EXPECTED ERROR: INTEGER * INTEGER can overflow before casting.
SELECT (2000000000::INTEGER * 2::INTEGER)::BIGINT;
```

The `INTEGER` multiplication must complete before the result is cast to `BIGINT`. If it overflows, the trailing cast cannot save it.

Correct approach:

```sql
SELECT 2000000000::BIGINT * 2::BIGINT AS safe_product;
```

Similarly, dividing integers and then casting to `NUMERIC` loses the fraction. **When you cast matters just as much as the target type you choose.**

### 16.4. Check Ranges When Designing the Schema

If quantity can never be negative:

```sql
quantity BIGINT NOT NULL CHECK (quantity >= 0)
```

If a rate is a value between 0 and 1:

```sql
rate NUMERIC(9,6) NOT NULL
    CHECK (rate BETWEEN 0 AND 1)
```

If a strictly positive integer is required:

```sql
units INTEGER NOT NULL CHECK (units > 0)
```

Constraints prevent values outside business domains, yet **they do not guarantee subsequent formulas will not overflow**. You must still estimate growth and intermediate results.

### 16.5. Numeric Field Overflow

A statement:

```sql
-- EXPECTED ERROR: precision too small.
SELECT 100000::NUMERIC(5,2);
```

exceeds the capacity of `NUMERIC(5,2)`. PostgreSQL typically uses SQLSTATE **22003** for numeric value out of range or related errors.

Applications should distinguish out-of-range errors from unparseable input errors, division by zero, and `CHECK`/`NOT NULL` violations.

### 16.6. Underflow with Floating Point

With floating point, a non-zero number that is **too small** may not be representable at the required magnitude, or may be rounded to 0 in certain situations.

Conceptual example:

```text
A multiplication produces 10^-400
but the floating-point type has a finite exponent range.
The result can fall below the representable threshold.
```

Do not assume every underflow silently returns 0. Specific behavior can depend on the operation, type, version, and PostgreSQL error rules. If extremely small quantities are needed, check numeric ranges and representations during design.

---

## 17. POWER, SQRT, CBRT, and Other Math Functions

Beyond basic arithmetic, PostgreSQL provides mathematical functions for statistics, engineering, and analytics.

### 17.1. POWER and the ^ Operator

```sql
SELECT
    POWER(2::NUMERIC, 3::NUMERIC) AS two_cubed,
    2 ^ 3 AS two_cubed_operator,
    POWER(10::NUMERIC, 2::NUMERIC) AS ten_squared;
```

Results: 8, 8, 100.

When writing nested exponentiations or combining with negative numbers, **use parentheses to specify grouping explicitly**, rather than assuming notation habits from outside SQL.

### 17.2. SQRT and CBRT

```sql
SELECT
    SQRT(81::NUMERIC) AS square_root_81,
    CBRT(27::DOUBLE PRECISION) AS cube_root_27;
```

Meaningful results: 9 and approximately 3.

Roots, powers, and logarithms have **defined domains**. For example, the real square root of a negative number is undefined in real numbers; PostgreSQL will not turn it into a valid real number simply because `SQRT` exists.

```sql
-- EXPECTED DOMAIN ERROR for negative real input.
SELECT SQRT((-1)::NUMERIC);
```

Handling must follow business rules:

- If a negative number is bad input: reject or flag an error.
- If complex arithmetic is needed: use a dedicated representation/tool; do not expect real `SQRT` to return complex numbers.
- If a tiny negative value arises from floating-point error: define a controlled tolerance/clamping policy instead of blindly hiding all negative values.

### 17.3. LOG, LN, and Input Domains

Logarithm functions require inputs within their mathematical domain; for instance, logarithms of non-positive numbers have no ordinary finite real value.

```sql
SELECT
    LN(1::NUMERIC) AS ln_one,
    LN(10::NUMERIC) AS ln_ten,
    LOG(100::NUMERIC) AS log_base_ten_of_100;
```

Meaningful results: 0, approximately 2.302585..., and 2.

Do not run `LN(0)` or `LOG(-1)` expecting NULL by default; out-of-domain inputs raise errors.

### 17.4. PI and Trigonometric Functions

PostgreSQL includes `PI()` and trigonometric functions for engineering workloads:

```sql
SELECT
    PI() AS pi_approx,
    RADIANS(180::DOUBLE PRECISION) AS radians_of_180,
    DEGREES(PI() / 2) AS degrees_of_half_pi,
    SIN(PI() / 2) AS sine_of_half_pi;
```

These calculations typically use approximate floating point; do not compare results directly against 0 or 1 with `=` in general. When threshold checks are required, use a domain-appropriate tolerance.

---

## 18. RANDOM and Pseudo-Random Numbers

PostgreSQL provides `RANDOM()`, returning a pseudo-random `DOUBLE PRECISION` value typically in the interval **[0,1)**.

```sql
SELECT RANDOM() AS random_fraction;
```

Example simulating an integer 1..6 in the lab:

```sql
SELECT
    FLOOR(RANDOM() * 6)::INTEGER + 1
        AS simulated_die_roll;
```

The result can be an integer from 1 to 6.

### 18.1. RANDOM Is Not Suitable for Security Tokens

`RANDOM()` is intended for ordinary statistics, simulation, and testing. Never use it to generate password reset tokens, API secrets, or values requiring cryptographic secrecy.

Applications needing secure randomness must use an appropriate cryptographic entropy/random API and dedicated security mechanisms.

### 18.2. Reproducibility

PostgreSQL supports `SETSEED` to seed the session pseudo-random generator in certain contexts:

```sql
SELECT SETSEED(0.25);
SELECT RANDOM();
```

This can help in experiments, yet **is not a guarantee** that every version, environment, execution plan, and call count will produce identical sequences. Never build business correctness on the default `RANDOM` sequence.

---

## 19. SUM, AVG, MIN, MAX, and Result Types

Aggregate functions are also a key part of arithmetic processing in queries.

```sql
SELECT
    COUNT(*) AS line_count,
    SUM(line_gross) AS total_gross,
    AVG(line_gross) AS average_gross,
    MIN(line_gross) AS minimum_gross,
    MAX(line_gross) AS maximum_gross
FROM arithmetic_lab.order_lines;
```

With the lab data:

- `ITEM-A`: 2 × 19.99 = 39.98.
- `ITEM-B`: 1.5 × 4.20 = 6.30.
- `ITEM-C`: 100 × 0.0150 = 1.50.
- `ITEM-D`: 3 × 12.3450 = 37.0350.
- `ITEM-E`: 1 × 100 = 100.00.

The initial gross total is **184.8150** before any currency-specific rounding rules.

### 19.1. Input Type Determines Aggregate Return Type

Common PostgreSQL rules:

| Input | `SUM(...)` Usually Returns | `AVG(...)` Usually Returns |
| --- | --- | --- |
| `SMALLINT` | `BIGINT` | `NUMERIC` |
| `INTEGER` | `BIGINT` | `NUMERIC` |
| `BIGINT` | `NUMERIC` | `NUMERIC` |
| `NUMERIC` | `NUMERIC` | `NUMERIC` |
| `REAL` | `REAL` | `DOUBLE PRECISION` |
| `DOUBLE PRECISION` | `DOUBLE PRECISION` | `DOUBLE PRECISION` |

These are behaviors of common PostgreSQL aggregates, not a promise that other arithmetic operations widen types by the same rule.

For example, `SUM(integer)` can avoid overflow on moderate totals by returning `BIGINT`, yet an **integer × integer** expression inside `SUM` can still overflow **before the aggregate receives the value**.

### 19.2. Cast Before Aggregating When a Wider Range Is Needed

Suppose a hypothetical table has `quantity INTEGER` and `unit_price_cents INTEGER`.

Risky pattern:

```sql
-- Illustrative pattern; table sale_items is not created in the lab.
SELECT SUM(quantity * unit_price_cents)
FROM sale_items;
```

The `INTEGER * INTEGER` multiplication can overflow before `SUM`.

Casting upfront:

```sql
SELECT SUM(
    quantity::NUMERIC * unit_price_cents::NUMERIC
)
FROM sale_items;
```

Or cast to `BIGINT` if products and totals are guaranteed to fit within `BIGINT`.

### 19.3. SUM Over an Empty Set Is Not 0

```sql
SELECT
    COUNT(*) AS rows_count,
    SUM(line_gross) AS total
FROM arithmetic_lab.order_lines
WHERE sku = 'SKU-NOT-FOUND';
```

Results: `rows_count = 0` and `total = NULL`.

If a report should show 0:

```sql
SELECT
    COALESCE(SUM(line_gross), 0::NUMERIC) AS total
FROM arithmetic_lab.order_lines
WHERE sku = 'SKU-NOT-FOUND';
```

Do not mechanically replace `AVG(...) NULL` with 0 when the set has no observations.

---

## 20. Round Per Line or Round at the Total?

This is a frequent monetary calculation error, even when all operands are `NUMERIC`.

Suppose there are two lines, each valued at 0.05 USD, with an **assumed** 10% tax rate.

### 20.1. Rounding Tax Per Line

```sql
SELECT
    ROUND(0.05::NUMERIC * 0.10::NUMERIC, 2)
    + ROUND(0.05::NUMERIC * 0.10::NUMERIC, 2)
        AS tax_per_line_then_sum;
```

Each line has an unrounded tax of 0.005, which rounds in `NUMERIC` to 2 decimal places as 0.01, summing to **0.02 USD**.

### 20.2. Summing the Base First, Rounding Tax on the Total

```sql
SELECT
    ROUND(
        (0.05::NUMERIC + 0.05::NUMERIC)
        * 0.10::NUMERIC,
        2
    ) AS tax_on_total;
```

The total base is 0.10 × 10% = 0.01, giving **0.01 USD**.

| Method | Tax Result |
| --- | ---: |
| Round each line then SUM | 0.02 USD |
| SUM base then round tax | 0.01 USD |

**Both calculations use exact decimals yet produce different results.** That comes from the **rounding point**, not a PostgreSQL storage bug.

Actual tax policy must follow applicable regulations and business contracts; this lesson does not assume one method is universally right for every system.

### 20.3. Avoid Rounding Unit Prices Prematurely

Unit price 0.0150 USD/unit, quantity 100:

```sql
SELECT
    ROUND(0.0150::NUMERIC, 2) * 100
        AS wrong_early_round,
    ROUND(0.0150::NUMERIC * 100, 2)
        AS line_total_rounded_at_end;
```

Results:

- Rounding unit price first: 0.02 × 100 = **2.00**.
- Multiplying first, rounding line total afterward: 1.50 = **1.50**.

A 0.50 USD discrepancy arises solely from placing `ROUND` at the wrong step.

**Design rule:** keep full precision in prices and intermediate calculations; round at **defined business checkpoints**, not "the earlier the safer."

---

## 21. Lab: Computing Net Amounts After Discount

The `arithmetic_lab.order_lines` table already has:

- `quantity NUMERIC(12,3)`.
- `unit_price NUMERIC(16,4)`.
- `discount_rate NUMERIC(7,5)`, a ratio from 0 to 1.
- `line_gross NUMERIC(20,4)`, computed as `quantity * unit_price`.

Compute discount and net line amount to two decimal places:

```sql
SELECT
    sku,
    quantity,
    unit_price,
    line_gross,
    discount_rate,
    ROUND(
        line_gross * discount_rate,
        2
    ) AS discount_amount,
    ROUND(
        line_gross * (1::NUMERIC - discount_rate),
        2
    ) AS line_net
FROM arithmetic_lab.order_lines
ORDER BY line_id;
```

Note that there are **two competing formulas** here:

1. `ROUND(gross × (1 - rate), 2)`.
2. `ROUND(gross,2) - ROUND(gross × rate,2)`.

They are not guaranteed to be equal for all inputs. If business rules require rounding the line gross first and subtracting a rounded discount, implement that exact sequence rather than assuming algebraic equivalence.

### 21.1. Summing from Per-Line Rounded Results

If the confirmed rule is **rounding each line's net amount** before totaling the invoice:

```sql
WITH line_amounts AS (
    SELECT
        sku,
        ROUND(
            line_gross * (1::NUMERIC - discount_rate),
            2
        ) AS net_amount
    FROM arithmetic_lab.order_lines
)
SELECT
    COUNT(*) AS line_count,
    SUM(net_amount) AS invoice_net_total
FROM line_amounts;
```

This makes explicit that each line's amount is quantized to two decimal digits prior to aggregation. If the rule requires summing unrounded net values and applying `ROUND` once at the end, the query differs:

```sql
SELECT
    ROUND(
        SUM(line_gross * (1::NUMERIC - discount_rate)),
        2
    ) AS invoice_net_round_once
FROM arithmetic_lab.order_lines;
```

Do not assume the two queries always yield the same total.

### 21.2. Distinguishing Monetary Decimals and Percentages

If `discount_rate = 0.10`, that represents 10%, not 0.10%.

An API integration bug:

```text
Frontend: sends "10" meaning 10%
Backend: multiplies amount * 10 directly
Result: 10x the value, not a 10% discount
```

Specify whether the API accepts **percent 10** or **fraction 0.10**, and when using fractions, a `BETWEEN 0 AND 1` constraint catches many out-of-range inputs.

### 21.3. Exchange Rates Differ from Money

Exchange rates may require more decimal places than final payment amounts:

```sql
SELECT
    123.45::NUMERIC AS source_amount,
    25000.123456::NUMERIC AS example_rate,
    ROUND(
        123.45::NUMERIC * 25000.123456::NUMERIC,
        0
    ) AS rounded_target_amount;
```

The rate above is **hypothetical for study**, not a market quote. Using `NUMERIC(12,2)` for such a rate would round the rate prematurely and skew the converted amount.

---

## 22. Separating Value, Unit, and Rounding Policy

A bare number like `100` does not specify whether it means:

- 100 USD.
- 100 cents.
- 100 VND.
- 100 items.
- 100%.
- An exchange rate of 100 target units per 1 source unit.

Calculations must operate on **quantities in consistent units**.

### 22.1. Amounts in Minor Units

Many payment systems store settled amounts as `BIGINT` minor units:

```text
USD 19.99 -> 1999 cents
VND 125000 -> 125000 dong (if contract uses scale 0)
KWD 1.234 -> 1234 minor units (if scale 3)
```

In this design, all services must agree on:

- Currency code.
- Scale (number of minor-unit digits).
- Value bounds.
- When conversion/rounding happens from unit prices or exchange rates.
- Types and limits when exchanging via JSON/JavaScript.

**Never add two minor-unit amounts of different currencies directly**, even though both are `BIGINT`.

### 22.2. Converting Decimals to Minor Units

Example for USD with scale 2:

```sql
SELECT
    19.99::NUMERIC * 100 AS cents_decimal,
    ROUND(19.99::NUMERIC * 100, 0)::BIGINT
        AS cents_integer;
```

Result: 1999.

If the input is `19.999`, the cent count is not an integer. Depending on the contract, you must either:

- Reject the input for having too many decimal places.
- Or round according to an explicit policy before casting.

Do not cast blindly and hope the value is interpreted properly.

### 22.3. Minor Units Vary by Currency

Never multiply every currency by 100:

- USD typically has 2 minor-unit digits.
- JPY and VND in many data contracts have scale 0.
- Certain currencies such as KWD use scale 3.

Multi-currency systems need a managed reference table/rule, never a hardcoded multiplier of `100` for all transactions.

---

## 23. Display Functions Are Not Calculation Functions

When exporting reports, you may want to format `12345.6` as `12,345.60` or with a currency symbol. PostgreSQL provides `TO_CHAR` for output formatting.

Example:

```sql
SELECT
    TO_CHAR(12345.6::NUMERIC, 'FM999,999,990.00')
        AS formatted_amount;
```

The result is a **formatted text string**, no longer a numeric value for ordinary arithmetic.

### 23.1. Do Not Store Formatted Strings as Money

Avoid storing:

```text
'12,345.60'
'12.345,60'
'$12,345.60'
```

as primary monetary data when a column can store `NUMERIC` or minor units.

Because:

- Commas and dots mean different things across locales.
- Strings may contain inconsistent currency symbols.
- Lexicographical sorting differs from numeric sorting.
- `SUM`/`AVG` and numeric `CHECK` constraints become awkward.
- Re-importing can misparse values.

Compute using numeric types; format at the **presentation layer** or report export stage.

### 23.2. Notes on ROUND and Formatting

`TO_CHAR` can apply pattern-based formatting/rounding rules. When an application needs a **settled** business number, calculate and persist the numeric result per policy first, and format only for display.

Never treat formatted text as primary proof that the underlying source value was stored accurately.

---

## 24. Importing Numbers from Text, CSV, and APIs

A precision bug often happens **before a value ever enters PostgreSQL**.

Example of a bad pipeline:

```text
Client sends "19.99"
    -> Parser converts to double
    -> App runs multiple double calculations
    -> Casts to NUMERIC(18,2)
    -> Stores value tainted by intermediate error/rounding
```

The final `NUMERIC` column **cannot reconstruct the original intent** if the application already distorted the value.

### 24.1. Validate Text Before Casting

If an API accepts only non-negative USD with at most two decimal places, you can define valid inputs:

```text
"0"
"0.01"
"19.99"
"1000.00"
```

And reject:

```text
"-1.00"
"12.345"
"abc"
"1,000.00"    (if the API disallows thousand separators)
```

An illustrative regex for a **non-negative decimal string with a dot and at most two fractional digits**:

```sql
SELECT
    input_text,
    input_text ~ '^[0-9]+(\.[0-9]{1,2})?$'
        AS format_ok
FROM (
    VALUES
        ('19.99'),
        ('12.345'),
        ('-1.00'),
        ('0'),
        ('abc')
) AS x(input_text);
```

**Regex checks format only**; it does not check whether the number exceeds precision, matches the currency, matches the payment provider's scale, or fits the storage type.

Converting text values to `NUMERIC` requires handling parse errors, out-of-range values, and business validation.

### 24.2. Invalid Input Errors

Example:

```sql
-- EXPECTED cast error.
SELECT 'abc'::NUMERIC;
```

PostgreSQL raises SQLSTATE **22P02** (*invalid_text_representation*).

A validly formatted number that is out of range raises a different error, such as **22003** (*numeric_value_out_of_range*). Applications should classify errors by SQLSTATE and return appropriate messages rather than matching error text substrings.

### 24.3. Use Staging When Importing Untrusted Data

A safe pipeline:

```text
CSV file / external API
          |
          v
Staging stores raw strings
          |
          v
Validate format + range + unit
          |
          v
Cast to NUMERIC/BIGINT
          |
          v
Calculate under explicit policy
          |
          v
Target table constraints + reconciliation
```

Never turn every parse error into 0 or NULL and ignore it. Doing so produces clean-looking reports with wrong monetary totals and lost audit trails.

---

## 25. Java BigDecimal and JDBC with NUMERIC

For Java applications connecting to PostgreSQL, `java.math.BigDecimal` is the standard choice for working with `NUMERIC/DECIMAL`.

### 25.1. Do Not Construct BigDecimal from double Unintentionally

Pattern to avoid for decimal money literals:

```java
import java.math.BigDecimal;

// Can bring double's binary representation into BigDecimal.
BigDecimal bad = new BigDecimal(0.1);
```

Use instead:

```java
BigDecimal exact = new BigDecimal("0.1");
BigDecimal alsoUseful = BigDecimal.valueOf(0.1);
```

The string constructor preserves the exact decimal meaning written. `BigDecimal.valueOf(double)` uses the double's canonical string representation safely, yet **cannot recover digits already lost across prior double calculations**.

### 25.2. Specify a Rounding Mode

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal unitPrice = new BigDecimal("0.0150");
BigDecimal quantity = new BigDecimal("100");

BigDecimal gross = unitPrice.multiply(quantity);
BigDecimal payable = gross.setScale(2, RoundingMode.HALF_UP);

System.out.println(payable);  // 1.50
```

In Java, you can choose `HALF_UP`, `HALF_EVEN`, `DOWN`, or other modes. **Do not assume PostgreSQL `ROUND(numeric,scale)` matches every Java rounding mode.**

If the business requires half-even, design matching logic and test consistently across database, backend, and reconciliation systems.

### 25.3. BigDecimal Division Requires Explicit Precision

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

BigDecimal result = one.divide(
    three,
    8,
    RoundingMode.HALF_UP
);
```

Here the result is rounded to 8 decimal places. Do not call `divide` casually expecting every division to terminate; in Java, a non-terminating division without rounding specified throws `ArithmeticException`.

### 25.4. Passing and Reading NUMERIC via JDBC

Sample snippet (the `payments` table is not created in the lab):

```java
BigDecimal amount = new BigDecimal("19.99");

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO payments (amount) VALUES (?)")) {
    ps.setBigDecimal(1, amount);
    ps.executeUpdate();
}
```

When reading:

```java
BigDecimal stored = resultSet.getBigDecimal("amount");
```

For minor-unit amounts stored as `BIGINT`, you can use `setLong/getLong`, while still tracking currency and scale. If JavaScript/JSON is involved, remember that JavaScript `Number`'s safe integer range is smaller than PostgreSQL's `BIGINT` range.

---

## 26. Using EXPLAIN and Observing Performance

`NUMERIC` arithmetic provides necessary decimal accuracy, yet can use more CPU than `INTEGER/BIGINT` arithmetic in many workloads. Arithmetic functions in `WHERE` can also affect index usage.

### 26.1. Queries with Calculations on Columns

Example:

```sql
SELECT sku, line_gross
FROM arithmetic_lab.order_lines
WHERE ROUND(line_gross, 2) >= 20::NUMERIC;
```

If there is a plain B-tree index on `line_gross`, wrapping the column in `ROUND(line_gross,2)` can prevent the query from using the index as straightforwardly as `WHERE line_gross >= 20`.

Do not rewrite those two predicates as equivalent if they **differ at rounding boundaries**. Establish business logic first, then evaluate indexes or precomputed columns.

### 26.2. Expression Indexes When Needed

If an important query frequently filters by the same expression:

```sql
CREATE INDEX idx_order_lines_rounded_gross
ON arithmetic_lab.order_lines (
    (ROUND(line_gross, 2))
);
```

PostgreSQL can consider the expression index for matching predicates when the function volatility, data types, statistics, and query align.

However:

- Indexes add storage and write overhead.
- The query expression must match the indexed expression.
- A 5-row lab table will normally use a sequential scan.
- Do not create indexes before knowing the real workload.

### 26.3. Inspecting Plans

```sql
EXPLAIN
SELECT sku
FROM arithmetic_lab.order_lines
WHERE ROUND(line_gross, 2) >= 20::NUMERIC;
```

To measure actual execution on a `SELECT`:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sku
FROM arithmetic_lab.order_lines
WHERE ROUND(line_gross, 2) >= 20::NUMERIC;
```

`EXPLAIN ANALYZE` **actually runs the statement**, so never run it carelessly on `UPDATE/DELETE/INSERT` in production. For illustrative `SELECT` queries, you can observe the scan plan, actual timing, and buffer usage.

### 26.4. Avoid Repeating Formulas When Standardization Helps

A complex SQL query might compute:

```sql
ROUND(quantity * unit_price * (1 - discount_rate), 2)
```

across `SELECT`, `WHERE`, and `ORDER BY`. You can consider a derived table or CTE to name the expression:

```sql
WITH calculated AS (
    SELECT
        line_id,
        sku,
        ROUND(
            quantity * unit_price
            * (1::NUMERIC - discount_rate),
            2
        ) AS net_amount
    FROM arithmetic_lab.order_lines
)
SELECT sku, net_amount
FROM calculated
WHERE net_amount >= 20::NUMERIC
ORDER BY net_amount DESC, sku;
```

A CTE improves readability and formula consistency, though **do not assume** PostgreSQL always materializes it or evaluates the expression strictly once. For slow queries, inspect the plan and actual data.

---

## 27. SQLSTATE Error Codes and Handling

When doing math in SQL, key errors include:

| Situation | Common SQLSTATE | Meaning |
| --- | --- | --- |
| Division by zero | `22012` | `division_by_zero` |
| Numeric value out of type range | `22003` | `numeric_value_out_of_range` |
| Text cannot be cast to numeric | `22P02` | `invalid_text_representation` |
| Table `CHECK` violation | `23514` | `check_violation` |
| `NOT NULL` column receives `NULL` | `23502` | `not_null_violation` |

Backend handling examples:

- Malformed input -> clear validation message without leaking internal SQL.
- Zero denominator in ratio -> return "undefined" if business rules allow; do not assume 0.
- Overflow -> review data types/limits and intermediate formulas.
- `CHECK` violation -> fix data or input flow rather than disabling constraints to bypass errors.
- Transaction error -> roll back or use savepoints per workflow.

### 27.1. Errors Inside a Transaction

```sql
BEGIN;

-- EXPECTED ERROR:
SELECT 1 / 0;

-- In a PostgreSQL transaction, subsequent statements
-- will not proceed normally until ROLLBACK.
ROLLBACK;
```

When studying, run each **expected-error** example separately, in autocommit mode, or using planned transactions/savepoints. Never place an error-inducing query inside a primary data-loading script expecting later statements to execute.

### 27.2. Do Not Rely on Error Message Text

Drivers typically expose SQLSTATE directly. Structured error codes are far more stable than parsing `"division by zero"` or `"numeric field overflow"` strings, which can vary by version, language, or wrapper.

At the same time, never return raw PostgreSQL error messages directly to end users if they expose table structures or sensitive data.

---

## 28. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "`7 / 2` must be 3.5." | Integer division in PostgreSQL yields integer quotient 3. |
| "Casting the result to `NUMERIC` recovers the fraction." | Once truncated in integer division, trailing casts cannot restore it. |
| "`NUMERIC` is infinitely accurate for every calculation." | Exact for finite decimals, yet repeating divisions/roots and scale casts still have bounds. |
| "`DOUBLE PRECISION` works for all money because it has many digits." | It is binary floating point and can introduce decimal error. |
| "`ROUND` and `TRUNC` are the same." | `ROUND` rounds; `TRUNC` truncates toward 0. |
| "`FLOOR(-3.7)` is -3." | `FLOOR` rounds down, so it is -4. |
| "`CEIL(-3.7)` is -4." | `CEIL` rounds up, so it is -3. |
| "`ROUND` always rounds `.5` to even." | `ROUND` on `NUMERIC` uses ties away from zero. |
| "`ROUND(double,2)` is always available." | PostgreSQL normally provides the two-argument signature for `NUMERIC` only. |
| "`NUMERIC(10,2)` rejects prices with 3 decimal places." | PostgreSQL can round the input to scale 2. |
| "`CAST` after multiplication fixes overflow." | Multiplication already failed before the cast; cast operands first. |
| "`MOD(-7,3)` is always 2." | Remainders can be negative per divisor/type rules; normalize if a non-negative range is needed. |
| "`SUM` over an empty set equals 0." | `SUM` returns NULL; `COUNT(*)` returns 0. |
| "A zero denominator should automatically make a ratio 0." | No denominator can mean the ratio is undefined. |
| "`COALESCE` always improves data." | It can mask missing data or business bugs. |
| "If a `FLOAT` displays `0.3`, it stores `0.3` exactly." | Its binary representation can still be an approximation. |
| "Comparing `FLOAT` with `=` is always safe." | Representation/rounding error can cause mismatches. |
| "Picking a tiny epsilon is always accurate." | Epsilon must fit units and scale; near 0 and large magnitudes differ. |
| "`NaN` never satisfies comparisons in PostgreSQL." | PostgreSQL has specific `NaN` ordering rules for sorting/indexing. |
| "Per-line `ROUND` and total `ROUND` are equivalent." | Different rounding points can produce different totals. |
| "Unit prices always have 2 decimal places." | Unit prices, exchange rates, and quantities may require different scales. |
| "`Random()` is fine for security tokens." | Use a dedicated cryptographic RNG. |
| "Using `NUMERIC` means all financial math is right." | You still need proper units, rounding policies, transactions, and validation. |

---

## 29. Practice Exercises

### Exercise 1 — Operators and Precedence

Predict the results:

```sql
SELECT
    8 + 3 * 4 AS a,
    (8 + 3) * 4 AS b,
    17 / 5 AS c,
    17 % 5 AS d;
```

Explain the difference between `a` and `b`, as well as integer quotient and remainder.

### Exercise 2 — Integer Division and Casts

Run:

```sql
SELECT
    7 / 2 AS a,
    (7 / 2)::NUMERIC AS b,
    7::NUMERIC / 2 AS c,
    (-7)::INTEGER / 2 AS d;
```

Explain why `a` and `b` equal 3, `c` equals 3.5, and `d` equals -3.

### Exercise 3 — Calculating Success Rate

There are 7 successful orders out of 12. Write a PostgreSQL query computing the percentage to two decimal places.

Hint:

```sql
ROUND(7::NUMERIC / 12::NUMERIC * 100, 2)
```

Why would `7 / 12 * 100` be wrong?

### Exercise 4 — Distinguishing ROUND, TRUNC, FLOOR, and CEIL

For 3.7, -3.7, 2.5, and -2.5, build a table of results for all four functions.

Specifically, explain why `TRUNC(-3.7)` differs from `FLOOR(-3.7)`.

### Exercise 5 — ROUND with Negative Scale

Compute:

```sql
SELECT
    ROUND(12345.678::NUMERIC, -1),
    ROUND(12345.678::NUMERIC, -2),
    TRUNC(12345.678::NUMERIC, -2);
```

Explain why rounding to hundreds differs from truncating to hundreds.

### Exercise 6 — NUMERIC vs. Floating Point

Compare:

```sql
SELECT
    (0.1::NUMERIC + 0.2::NUMERIC) = 0.3::NUMERIC
        AS decimal_equal,
    (0.1::DOUBLE PRECISION + 0.2::DOUBLE PRECISION)
         = 0.3::DOUBLE PRECISION AS float_equal;
```

Then use `ABS(a-b) < epsilon` to check near-equality in a measurement scenario.

Why should you not use an arbitrary epsilon to reconcile settled payment amounts?

### Exercise 7 — Rounding Rules for Negative Numbers

Run:

```sql
SELECT
    ROUND( 1.235::NUMERIC, 2),
    ROUND(-1.235::NUMERIC, 2),
    TRUNC(-1.235::NUMERIC, 2);
```

Explain midpoint rounding of negative numbers in `NUMERIC` and how it differs from truncation.

### Exercise 8 — Numeric Precision and Overflow

Test:

```sql
SELECT
    999.99::NUMERIC(5,2) AS valid;
```

Then run separately:

```sql
-- EXPECTED ERROR.
SELECT 1000.00::NUMERIC(5,2);
```

Why are there not enough integer digits? What happens if you enter `999.995`?

### Exercise 9 — Overflow Before Casting

Compare:

```sql
-- EXPECTED ERROR.
SELECT (2000000000::INTEGER * 2::INTEGER)::BIGINT;
```

and:

```sql
SELECT 2000000000::BIGINT * 2::BIGINT;
```

Explain why you must cast **before the calculation**.

### Exercise 10 — Division by Zero and NULLIF

Write a query computing `sales / visits` for:

- sales = 100, visits = 20;
- sales = 100, visits = 0;
- sales = 0, visits = 0.

Use `NULLIF(visits,0)` to avoid errors and explain why the two zero-denominator cases deserve separate business analysis.

### Exercise 11 — SUM and AVG with NULL

The `arithmetic_lab.sensor_readings` table has one NULL `reading_value`. Compare:

```sql
SELECT
    COUNT(*),
    COUNT(reading_value),
    SUM(reading_value),
    AVG(reading_value)
FROM arithmetic_lab.sensor_readings;
```

Why does `COUNT(*)` differ from `COUNT(column)`? What does `SUM` return if you filter down to an empty set?

### Exercise 12 — Rounding Tax Per Line vs. on the Total

Two line items each cost 0.05 USD, with an assumed 10% tax rate. Compute:

1. Round tax per line to 2 digits, then sum.
2. Sum the base first, multiply by tax, and round at the end.

Compare 0.02 and 0.01, and explain why this is a **business rule** decision rather than a `NUMERIC` bug.

### Exercise 13 — Unit Price Below 0.01

A product has unit price 0.0150 USD and quantity 100. Write SQL two ways:

1. Round the unit price to 2 decimal places before multiplying.
2. Multiply by quantity first, then round the result.

Compare 2.00 and 1.50, then explain how to choose the storage scale for `unit_price`.

### Exercise 14 — Handling NaN and Infinity

Using literals:

```sql
SELECT
    'NaN'::DOUBLE PRECISION,
    'Infinity'::DOUBLE PRECISION,
    '-Infinity'::DOUBLE PRECISION;
```

Explain why measurement and financial systems need explicit policies to accept or reject these special values.

### Exercise 15 — MOD with Negative Numbers

Run:

```sql
SELECT
    MOD(-7,3),
    MOD(7,-3),
    MOD(MOD(-7,3)+3,3);
```

Distinguish standard remainder from a remainder normalized into a non-negative range for a positive divisor.

### Exercise 16 — Computing Invoice Total via CTE

From `arithmetic_lab.order_lines`, create a CTE `line_amounts` containing:

- SKU.
- Gross = quantity × unit_price.
- Discount = gross × discount_rate.
- Net = ROUND(gross × (1 - discount_rate), 2).

Then `SUM(net)` to compute the total. Write another version using `SUM(gross × (1 - discount_rate))` and applying `ROUND` once. Must the two results always match across all datasets?

### Exercise 17 — Choosing Calculations for Measurement Data

A sensor reads an actual value of 23.50001 with an expected value of 23.5. Design a check using:

- Absolute tolerance 0.001.
- Relative tolerance 0.01%.
- Combining both thresholds.

Explain why a single global epsilon cannot fit every measurement unit.

### Exercise 18 — Data Type Design

Choose appropriate types and scales for:

1. Integer product quantities.
2. Weights with three decimal places.
3. Unit prices with four decimal places.
4. Settled USD payment amounts to the cent.
5. Exchange rates with many fractional digits.
6. Monetary amounts in minor units.
7. Sensor temperatures for approximate statistics.

Note the impact of overflow, rounding, and units for each choice.

### Exercise 19 — Parsing Text Before Storing Numeric

API inputs:

```text
19.99
19.999
-1.00
abc
0
```

Policy permits only non-negative numbers with at most two decimal digits. Classify valid vs. invalid inputs and explain why merely defining `NUMERIC(18,2)` is insufficient to reject `19.999`.

### Exercise 20 — Optimizing Expressions

Create an index on:

```sql
CREATE INDEX idx_order_lines_rounded_gross
ON arithmetic_lab.order_lines ((ROUND(line_gross,2)));
```

Use `EXPLAIN` to inspect the query plan for `ROUND(line_gross,2) >= 20`. Why might PostgreSQL still choose a sequential scan on a five-row table?

---

## 30. Safe Calculation Design Checklist

| Question | Action to Define |
| --- | --- |
| Are operands `INTEGER` or `NUMERIC`? | Check integer division and cast timing |
| Can the calculation overflow? | Estimate intermediate bounds; widen types before adding/multiplying |
| Can a denominator be 0? | Check / use `NULLIF` and define policy for undefined values |
| Can inputs be `NULL`? | Distinguish missing data from 0 |
| Are currency or ratios involved? | Define units, currency, and ratio representation |
| Is exact decimal precision required? | Use `NUMERIC` or integer minor units |
| Are floating-point calculations used? | Define acceptable error and finiteness checks |
| Are near-equality checks needed? | Design domain-specific absolute/relative tolerances |
| Is `ROUND` used? | Specify scale, tie-breaking rule, and rounding stage |
| Are negative values possible? | Distinguish `ROUND`/`TRUNC`/`FLOOR`/`CEIL` |
| Are tax or discounts computed? | Decide per-line vs. total-level rounding |
| Are unit prices smaller than a cent? | Keep intermediate precision; avoid early rounding |
| Are exchange rates involved? | Keep sufficient precision and snapshot rates by timestamp |
| Are `NUMERIC(p,s)` bounds tight? | Check overflow even after rounding |
| Are `NaN`/`Infinity` possible? | Validate per data policy |
| Importing from CSV/JSON? | Validate format/range before casting |
| Integrating with Java? | `BigDecimal` from strings and appropriate `RoundingMode` |
| Integrating with JavaScript? | Watch safe integer limits and JSON contracts |
| Using `SUM`/`AVG` aggregates? | Check output types, `NULL`, and accumulated error |
| Query slow due to calculations? | Check `EXPLAIN`, indexes, expressions, and stats |
| Auditability required? | Store formula snapshots, rounding policy, units, and settled values |
| Updating balances? | Use transactions, constraints, concurrency control, and idempotency |

## Conclusion

Arithmetic functions in PostgreSQL are only truly reliable when paired with **the right data types, the right formulas, and clear rounding rules**.

Key principles:

- `+`, `-`, `*`, `/`, `%`, and math functions must be used with awareness of operand types. **Dividing two integers can drop the fraction**, and **casting after an operation cannot rescue a truncated or overflowed result**.
- `ROUND`, `TRUNC`, `FLOOR`, and `CEIL` are distinct transformations; negative numbers and midpoint ties must be checked carefully.
- `NUMERIC` fits exact decimal arithmetic within declared bounds, though `NUMERIC(p,s)` can round on storage and operations like repeating division still require finite precision.
- `REAL/DOUBLE PRECISION` are approximate binary floating-point types; use them for measurements, science, or statistics where approximation is acceptable, never by default for settled financial amounts needing reconciliation.
- `NULLIF` prevents division-by-zero errors, yet an "undefined" value does not automatically mean 0. `COALESCE` must express an intentional business policy.
- Overflow, unparseable inputs, `NaN`, and `Infinity` must be detected and handled properly rather than hidden behind arbitrary casts or rounding.
- **Where you round** matters just as much as **how you round**; money, tax, unit prices, and exchange rates often require different scales and reconciled workflows.

By clearly separating **representation**, **intermediate calculation**, **validation**, **rounding policy**, and **final values**, you can write accurate PostgreSQL queries, explain every result, and prevent small discrepancies from compounding into major business errors.
