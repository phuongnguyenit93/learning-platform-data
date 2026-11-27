# ROUND, TRUNCATE, MOD, CEIL, FLOOR, and Negative Number Rules

MySQL provides mathematical functions to round, truncate fractional parts, compute remainders, and obtain the integer above or below a value. `ROUND()`, `TRUNCATE()`, `MOD()`, `CEIL()`, and `FLOOR()` frequently appear in reporting queries, monetary calculations, data bucketing, bucket-based pagination, and metric processing.

A common source of bugs is that these functions do not handle negative numbers in the same way. `TRUNCATE()` cuts toward 0; `CEIL()` moves toward positive infinity; `FLOOR()` moves toward negative infinity; `MOD()` retains the dividend's sign; and `ROUND()` follows distinct rules for exact values versus approximate floating-point values. Understanding these rules accurately helps prevent errors in business calculations.

## 1. Overview of the Functions

| Function | Effect | Positive Example | Negative Example |
| --- | --- | --- | --- |
| `ROUND(x, d)` | Rounds to `d` decimal places; negative `d` rounds left of the decimal point | `ROUND(2.56, 1) = 2.6` | `ROUND(-2.56, 1) = -2.6` |
| `TRUNCATE(x, d)` | Discards digits beyond `d` places without rounding | `TRUNCATE(2.59, 1) = 2.5` | `TRUNCATE(-2.59, 1) = -2.5` |
| `MOD(n, m)` | Returns the remainder of dividing `n` by `m` | `MOD(11, 4) = 3` | `MOD(-11, 4) = -3` |
| `CEIL(x)` | Returns the smallest integer greater than or equal to `x` | `CEIL(2.1) = 3` | `CEIL(-2.1) = -2` |
| `FLOOR(x)` | Returns the largest integer less than or equal to `x` | `FLOOR(2.9) = 2` | `FLOOR(-2.1) = -3` |

`CEIL()` is a synonym for `CEILING()`. Both names have the exact same meaning. These functions return a computed value inside an expression; they do not modify data stored in a table by themselves. To persist results, you must use `UPDATE`, `INSERT`, or another write operation.

## 2. ROUND(): Rounding Numbers

Syntax:

```sql
ROUND(number [, decimals])
```

- `number` is the value to round.
- `decimals` is the number of digits to keep after the decimal point.
- If `decimals` is omitted, MySQL defaults to rounding to the nearest integer.
- If `decimals` is positive, it rounds to that many decimal places.
- If `decimals` equals 0, it rounds to an integer.
- If `decimals` is negative, it rounds digits to the left of the decimal point.

Example:

```sql
SELECT
    ROUND(12.3456) AS integer_value,
    ROUND(12.3456, 2) AS two_decimals,
    ROUND(12.3456, 1) AS one_decimal,
    ROUND(12.3456, 0) AS zero_decimals,
    ROUND(12345.67, -1) AS nearest_ten,
    ROUND(12345.67, -2) AS nearest_hundred;
```

The results are `12`, `12.35`, `12.3`, `12`, `12350`, and `12300`, respectively.

### 2.1. ROUND with Negative Numbers

For exact-value arguments such as integers or `DECIMAL`, MySQL rounds exact half-way cases away from 0. Thus, `2.5` becomes `3`, while `-2.5` becomes `-3`.

```sql
SELECT
    ROUND(2.5) AS positive_half,
    ROUND(-2.5) AS negative_half,
    ROUND(2.45, 1) AS positive_tie,
    ROUND(-2.45, 1) AS negative_tie,
    ROUND(149, -1) AS positive_tens,
    ROUND(-149, -1) AS negative_tens;
```

With the exact values in the example, the results are `3`, `-3`, `2.5`, `-2.5`, `150`, and `-150`, respectively.

Note the case of `-2.45` rounded to one decimal place: the result is `-2.5`, meaning the magnitude increases when rounding at a midpoint. Do not describe this rule simply as "always rounding up," because for negative numbers moving away from 0 produces a numerically smaller value.

### 2.2. ROUND with Exact vs. Approximate Numbers

MySQL distinguishes two groups of values:

- **Exact-value:** integers and `DECIMAL`/`NUMERIC`. Midpoints are rounded away from 0.
- **Approximate-value:** `FLOAT`, `DOUBLE`, and floating-point expressions. `ROUND()` results depend on the underlying system math library; on many platforms, midpoints follow round-to-nearest-even.

You can observe the difference by comparing an exact literal with an exponential-notation literal:

```sql
SELECT
    ROUND(2.5) AS exact_value_round,
    ROUND(2.5E0) AS approximate_value_round;
```

`2.5` is an exact-value literal; `2.5E0` is an approximate-value literal. Results for approximate expressions can vary across C libraries and platforms, so do not rely on that behavior as a portable financial rule.

For currency or decimal figures requiring reproducible results, prefer `DECIMAL` and exact literals. Avoid converting values to `DOUBLE` before rounding if business logic dictates explicit decimal rules.

## 3. TRUNCATE(): Truncating Decimals Without Rounding

Syntax:

```sql
TRUNCATE(number, decimals)
```

`TRUNCATE()` keeps the specified number of digits and discards the rest. Unlike `ROUND()`, it does not inspect the next digit to decide whether to round up or down. For negative numbers, truncation moves toward 0.

```sql
SELECT
    TRUNCATE(12.349, 2) AS positive_value,
    TRUNCATE(-12.349, 2) AS negative_value,
    TRUNCATE(149, -1) AS positive_tens,
    TRUNCATE(-149, -1) AS negative_tens;
```

The results are `12.34`, `-12.34`, `140`, and `-140`, respectively.

### 3.1. Positive and Negative: TRUNCATE Always Moves Toward 0

Compare `TRUNCATE()` with `FLOOR()` on negative numbers:

```sql
SELECT
    TRUNCATE(-2.9, 0) AS truncated_value,
    FLOOR(-2.9) AS floored_value,
    CEIL(-2.9) AS ceiled_value;
```

The results are `-2`, `-3`, and `-2`. `TRUNCATE(-2.9, 0)` drops the fractional part to move toward 0; `FLOOR(-2.9)` must move down to the smaller integer, `-3`.

### 3.2. Negative D in TRUNCATE

A negative `decimals` parameter makes the function drop digits to the right of the corresponding place value:

```sql
SELECT
    TRUNCATE(9876.543, -1) AS tens,
    TRUNCATE(9876.543, -2) AS hundreds,
    TRUNCATE(9876.543, -3) AS thousands,
    TRUNCATE(-9876.543, -2) AS negative_hundreds;
```

The results are `9870`, `9800`, `9000`, and `-9800`. Discarded digits never trigger a rounding step.

Do not use `TRUNCATE()` in place of `ROUND()` in monetary calculations merely because you want two decimal places. Dropping remainders can introduce systematic bias, especially across millions of transactions. Only use it when business rules or accounting regulations explicitly require truncation.

## 4. How Do ROUND and TRUNCATE Differ?

The two functions may return the same result for certain inputs, yet their semantics differ:

| Expression | ROUND | TRUNCATE | Explanation |
| --- | ---: | ---: | --- |
| `12.346`, 2 digits | `12.35` | `12.34` | ROUND inspects the next digit; TRUNCATE drops excess digits |
| `12.341`, 2 digits | `12.34` | `12.34` | Next digit does not cause ROUND to round up |
| `-12.346`, 2 digits | `-12.35` | `-12.34` | TRUNCATE still moves toward 0 |
| `149`, `decimals = -1` | `150` | `140` | ROUND to nearest ten; TRUNCATE drops the ones digit |
| `-149`, `decimals = -1` | `-150` | `-140` | Same rule, noting negative direction |

Choose the function according to business requirements:

- Need arithmetic rounding: use `ROUND()`.
- Need to discard excess digits without rounding: use `TRUNCATE()`.
- Need an upper or lower integer bound: use `CEIL()` or `FLOOR()`.

## 5. CEIL() and CEILING(): Rounding Up to an Integer

Syntax:

```sql
CEIL(number)
CEILING(number)
```

Both functions return the smallest integer greater than or equal to the argument. Think of this as rounding toward positive infinity.

```sql
SELECT
    CEIL(2.1) AS positive_fraction,
    CEIL(2.0) AS positive_integer,
    CEIL(-2.1) AS negative_fraction,
    CEIL(-2.0) AS negative_integer;
```

The results are `3`, `2`, `-2`, and `-2`, respectively.

Application example: calculating the number of pages or boxes needed when each page/box holds up to a fixed capacity. If there are 21 items and each box holds 10 items, you need `CEIL(21 / 10) = 3` boxes.

To avoid unintended integer division, you can use a decimal literal or cast explicitly:

```sql
SELECT CEIL(21 / 10.0) AS box_count;
```

## 6. FLOOR(): Rounding Down to an Integer

Syntax:

```sql
FLOOR(number)
```

`FLOOR()` returns the largest integer less than or equal to the argument. This is rounding toward negative infinity.

```sql
SELECT
    FLOOR(2.9) AS positive_fraction,
    FLOOR(2.0) AS positive_integer,
    FLOOR(-2.1) AS negative_fraction,
    FLOOR(-2.0) AS negative_integer;
```

The results are `2`, `2`, `-3`, and `-2`, respectively.

For positive numbers, `FLOOR(x)` often looks like dropping the fractional part. For negative numbers, the result differs from `TRUNCATE(x, 0)`:

```sql
SELECT
    FLOOR(-8.7) AS floor_result,
    TRUNCATE(-8.7, 0) AS truncate_result;
```

The results are `-9` and `-8`. This is an important distinction when computing ranges, buckets, or classifying negative values.

## 7. Distinguishing ROUND, TRUNCATE, CEIL, and FLOOR on Negative Numbers

Use the same value to clearly see the direction of each operation:

```sql
SELECT
    -2.7 AS original_value,
    ROUND(-2.7) AS rounded,
    TRUNCATE(-2.7, 0) AS truncated,
    CEIL(-2.7) AS ceiling_value,
    FLOOR(-2.7) AS floor_value;
```

| Function | Result | Direction |
| --- | ---: | --- |
| `ROUND(-2.7)` | `-3` | Nearest integer |
| `TRUNCATE(-2.7, 0)` | `-2` | Toward 0 |
| `CEIL(-2.7)` | `-2` | Toward positive infinity |
| `FLOOR(-2.7)` | `-3` | Toward negative infinity |

A way to remember:

- `TRUNCATE`: drops remainder, moves toward 0.
- `CEIL`: moves up along the number line.
- `FLOOR`: moves down along the number line.
- `ROUND`: picks the nearest value according to the numeric type's rounding rule.

Do not interpret "up" and "down" in terms of absolute magnitude. On the number line, `-2` is greater than `-3`, so `CEIL(-2.7)` is `-2` and `FLOOR(-2.7)` is `-3`.

## 8. MOD(): Getting the Remainder of Division

Syntax:

```sql
MOD(dividend, divisor)
```

`MOD(n, m)` returns the remainder when dividing `n` by `m`. The `%` operator is an equivalent shorthand:

```sql
SELECT
    MOD(11, 4) AS function_result,
    11 % 4 AS operator_result;
```

Both expressions return `3`.

`MOD()` is commonly used to:

- Check even/odd numbers: `MOD(id, 2) = 0`.
- Partition data into cyclic groups.
- Determine position within a cycle.
- Calculate leftover units or quantities after division.

Example retrieving records with even IDs:

```sql
SELECT id, name
FROM products
WHERE MOD(id, 2) = 0;
```

If both arguments are integers, the result is an integer remainder. `MOD()` also supports decimal numbers:

```sql
SELECT MOD(34.5, 3) AS remainder;
```

The result is `1.5`.

## 9. Sign of MOD with Negative Numbers

In MySQL, the remainder of `MOD(n, m)` takes the sign of the dividend `n` (the first argument), if the remainder is non-zero. Therefore, the result can be negative:

```sql
SELECT
    MOD(11, 4) AS positive_positive,
    MOD(-11, 4) AS negative_positive,
    MOD(11, -4) AS positive_negative,
    MOD(-11, -4) AS negative_negative;
```

The results are `3`, `-3`, `3`, and `-3`, respectively.

This differs from some mathematical definitions or programming languages that always normalize the result into a non-negative range when the modulus is positive. If business logic requires buckets from `0` to `m - 1` and `m` is always positive, you can normalize:

```sql
SELECT MOD(MOD(-11, 4) + 4, 4) AS normalized_remainder;
```

The result is `1`. This normalization formula assumes a positive, non-zero divisor. If the divisor can be negative or zero, define explicit business rules and validate inputs before computing.

### 9.1. MOD with a Zero Divisor

If the second argument is 0, `MOD()` returns `NULL`:

```sql
SELECT MOD(10, 0) AS result;
```

The result is `NULL`. When data may contain a zero divisor, validate beforehand or handle the `NULL` result explicitly. Never assume modulo division always returns a number.

## 10. ROUND and TRUNCATE with Negative Decimal Places

A negative `decimals` argument lets you operate on tens, hundreds, thousands, etc., rather than just fractional places.

```sql
SELECT
    ROUND(1234.56, -1) AS round_tens,
    ROUND(1234.56, -2) AS round_hundreds,
    ROUND(1234.56, -3) AS round_thousands,
    TRUNCATE(1234.56, -1) AS truncate_tens,
    TRUNCATE(1234.56, -2) AS truncate_hundreds,
    TRUNCATE(1234.56, -3) AS truncate_thousands;
```

Results:

| Expression | Result |
| --- | ---: |
| `ROUND(1234.56, -1)` | `1230` |
| `ROUND(1234.56, -2)` | `1200` |
| `ROUND(1234.56, -3)` | `1000` |
| `TRUNCATE(1234.56, -1)` | `1230` |
| `TRUNCATE(1234.56, -2)` | `1200` |
| `TRUNCATE(1234.56, -3)` | `1000` |

In this example the results happen to match because the dropped digits do not cause `ROUND()` to round up. For `149`, the two functions differ: `ROUND(149, -1) = 150`, whereas `TRUNCATE(149, -1) = 140`.

For negative numbers, `TRUNCATE()`'s rule of moving toward 0 still holds:

```sql
SELECT
    ROUND(-149, -1) AS rounded_negative,
    TRUNCATE(-149, -1) AS truncated_negative;
```

The results are `-150` and `-140`, respectively.

## 11. Applications in Billing and Reporting

For monetary data, store values using `DECIMAL(p,s)` instead of `FLOAT`/`DOUBLE` when exact decimals are required. Example:

```sql
CREATE TABLE invoice_lines (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    quantity DECIMAL(10, 3) NOT NULL,
    unit_price DECIMAL(13, 2) NOT NULL,
    tax_rate DECIMAL(5, 4) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Calculate line totals and round to two decimal places:

```sql
SELECT
    id,
    quantity * unit_price AS raw_subtotal,
    ROUND(quantity * unit_price, 2) AS rounded_subtotal,
    ROUND(quantity * unit_price * tax_rate, 2) AS rounded_tax
FROM invoice_lines;
```

### 11.1. Round Per Line or Round the Total?

The two approaches can yield different results:

```sql
-- Round each line before summing
SELECT SUM(ROUND(quantity * unit_price * tax_rate, 2)) AS sum_of_rounded_tax
FROM invoice_lines;

-- Sum exact values first, then round the total
SELECT ROUND(SUM(quantity * unit_price * tax_rate), 2) AS rounded_total_tax
FROM invoice_lines;
```

This is not merely a technical detail. Accounting rules, tax regulations, or contracts may mandate rounding at the line level, invoice level, or reporting period level. Align on the rule with business stakeholders before writing SQL; never pick an approach just because the numbers look "cleaner."

`TRUNCATE()` can be useful when a rule specifies dropping fractions smaller than the billing unit, though always truncating toward 0 can introduce bias. Do not substitute `TRUNCATE()` for `ROUND()` when standard rounding is required.

### 11.2. Persisting Rounded Values

A `SELECT ROUND(...)` expression only changes the returned result. If you want to persist the rounded value into a column, you need DML:

```sql
UPDATE invoice_lines
SET unit_price = ROUND(unit_price, 2)
WHERE id = 100;
```

Before running a bulk `UPDATE`, inspect the scope with `SELECT`, back up if needed, and confirm that altering source values matches business intent. If rounding is only needed for display, perform it in the read query or presentation layer instead of overwriting source data.

## 12. Applications in Bucketing and Distribution

`MOD()` can partition IDs into cyclic groups:

```sql
SELECT
    id,
    MOD(id, 4) AS bucket_no
FROM events
ORDER BY id;
```

For non-negative IDs, `bucket_no` cycles through `0`, `1`, `2`, `3`. This technique works in exercises for simple sharding or work distribution, though it is not a complete sharding strategy: you must evaluate ID distribution, scalability, changing shard counts, and routing requirements.

`CEIL()` and `FLOOR()` are also helpful when computing fixed-size groups. For example, calculating the number of pages required when each page holds 25 rows:

```sql
SELECT CEIL(COUNT(*) / 25.0) AS page_count
FROM products;
```

To determine a 0-based group index for a positive number `x` with bucket size `k`, you can use `FLOOR(x / k)`. For negative numbers, clarify whether buckets should follow `FLOOR` or truncate toward 0 because boundaries differ.

## 13. How Data Types and Casting Affect Results

Math functions accept many argument types, yet input types affect precision and results. A `DECIMAL` column suits exact decimal calculations; `FLOAT` and `DOUBLE` are approximate numbers that may represent decimal fractions with binary approximations.

If data comes from strings, cast explicitly and validate beforehand:

```sql
SELECT ROUND(CAST('123.456' AS DECIMAL(10, 3)), 2) AS rounded_value;
```

Do not rely on implicit conversion from arbitrary strings. Empty strings, non-numeric characters, or differing decimal separators can trigger warnings, errors, or unexpected results depending on SQL mode.

In calculations with multiple nested functions, inspect types and precision at every step. For example, `ROUND(SUM(...), 2)` differs from `SUM(ROUND(..., 2))` both in outcome and in where rounding takes effect.

## 14. NULL and Mathematical Functions

If any required argument is `NULL`, the result of these math functions is typically `NULL`:

```sql
SELECT
    ROUND(NULL, 2) AS rounded_null,
    TRUNCATE(NULL, 2) AS truncated_null,
    MOD(NULL, 3) AS modulo_null,
    CEIL(NULL) AS ceiling_null,
    FLOOR(NULL) AS floor_null;
```

With `MOD()`, a zero divisor also returns `NULL`. When used in reporting expressions, decide whether to preserve `NULL` to denote missing data or replace it with another value:

```sql
SELECT COALESCE(ROUND(amount, 2), 0.00) AS display_amount
FROM payments;
```

Only use `COALESCE(..., 0)` if business rules treat missing values as equivalent to 0. If `NULL` means uncalculated, unentered, or not applicable, replacing it with 0 can distort reports.

## 15. Common Pitfalls and Misconceptions

| Misconception / Error | Reality | How to Handle |
| --- | --- | --- |
| `ROUND()` always rounds midpoints the same way | Exact-value and approximate-value types can behave differently | Use `DECIMAL` for decimal numbers requiring exactness |
| `TRUNCATE()` is rounding down | It truncates toward 0, not `FLOOR()` | Test specifically with negative numbers |
| `FLOOR(-2.7)` returns `-2` | `FLOOR()` moves down the number line and returns `-3` | Distinguish number-line direction from direction toward 0 |
| `CEIL(-2.7)` returns `-3` | `CEIL()` moves up the number line and returns `-2` | Apply the definition: smallest integer >= value |
| `MOD(-11, 4)` returns `1` | MySQL returns `-3`, sharing the dividend's sign | Normalize if a non-negative remainder is needed with a positive divisor |
| `MOD(n, 0)` returns 0 | The result is `NULL` | Validate divisors and handle NULL |
| `ROUND()` in SELECT alters the column | The function only produces a computed result | Use DML if processed values truly need to be saved |
| Truncating money with `TRUNCATE()` equals rounding | Truncation can introduce bias | Follow exact accounting/business rules |

## 16. Workflow for Choosing the Right Function

Before using a mathematical function, answer these questions:

1. **Is the data exact or approximate?** For money and critical decimal figures, prefer `DECIMAL`.
2. **Do you need rounding or truncation?** Use `ROUND()` for rounding, `TRUNCATE()` for truncating toward 0.
3. **Do you need an upper or lower bound?** Use `CEIL()` for upper, `FLOOR()` for lower.
4. **Are negative numbers possible?** Test outputs on negative numbers instead of extrapolating from positive examples.
5. **What sign does MOD need?** MySQL retains the dividend's sign; normalize if your algorithm requires a non-negative range.
6. **Can NULL or division by zero occur?** Define handling behavior and the semantics of missing values.
7. **At what level is rounding applied?** Per line, invoice total, or report; agree on the rule first.
8. **Display only or persist results?** Avoid overwriting source data if formatting is only needed on read.

## 17. Practice Exercises

1. Run `ROUND(2.5)`, `ROUND(-2.5)`, `ROUND(2.45, 1)`, and `ROUND(-2.45, 1)`; explain the midpoint rule for exact-value types.
2. Compare `ROUND(2.5)` and `ROUND(2.5E0)` on your server; note the effect of approximate-value types.
3. Run `TRUNCATE(149, -1)`, `TRUNCATE(-149, -1)`, `ROUND(149, -1)`, and `ROUND(-149, -1)`.
4. Compare `TRUNCATE(-2.9, 0)`, `CEIL(-2.9)`, and `FLOOR(-2.9)`.
5. Run `MOD(11, 4)`, `MOD(-11, 4)`, `MOD(11, -4)`, `MOD(-11, -4)`, and explain the result signs.
6. Write an expression normalizing the remainder into a non-negative range when the divisor is positive; test with a negative dividend.
7. Create an invoice line table using `DECIMAL`, and compare `SUM(ROUND(...))` with `ROUND(SUM(...))`.
8. Write a query using `CEIL()` to compute the number of boxes required if each box holds 12 items.
9. Test the outputs of these functions with `NULL`, and `MOD()` with a divisor of 0.
10. Pick a problem involving negative numbers (account balance, temperature, inventory variance) and explain whether to use ROUND, TRUNCATE, CEIL, or FLOOR.

## 18. Takeaways

`ROUND(x, d)` rounds to the specified number of digits; negative `d` rounds to tens, hundreds, or thousands. For exact-value types such as `DECIMAL`, midpoints round away from 0; for approximate-value types such as `DOUBLE`, results may depend on the system math library. `TRUNCATE(x, d)` drops excess digits and always moves toward 0, even for negative numbers.

`CEIL()`/`CEILING()` returns the smallest integer greater than or equal to the value, whereas `FLOOR()` returns the largest integer less than or equal to the value. `MOD(n, m)` returns the remainder carrying the sign of `n`; if `m = 0`, the result is `NULL`. When handling currency, use `DECIMAL` and agree on line-level versus total-level rounding. Always test with negative numbers, `NULL`, zero divisors, and actual data types before deploying expressions into an application.
