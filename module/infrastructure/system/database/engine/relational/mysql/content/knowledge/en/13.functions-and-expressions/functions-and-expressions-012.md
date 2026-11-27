# LEAST, GREATEST, and Handling NULL or Mixed Data Types

Within the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query optimization, privilege management, backup, and operations. The two functions **LEAST()** and **GREATEST()** select the smallest or largest value from a list of expressions within the same row. They are useful for clamping values to a range, comparing multiple timestamps, or picking a threshold dynamically from row data.

Results can be surprising if the argument list contains **NULL**, mixes numbers with strings, or uses strings with incompatible collations. You must understand how MySQL compares arguments before using these two functions in business queries.

## 1. What Do LEAST() and GREATEST() Do?

**LEAST(value1, value2, ...)** returns the argument with the smallest value; **GREATEST(value1, value2, ...)** returns the argument with the largest value. Each function requires at least two arguments.

~~~sql
SELECT
    LEAST(12, 5, 20, 8) AS smallest_value,
    GREATEST(12, 5, 20, 8) AS largest_value;
~~~

Results:

| smallest_value | largest_value |
|---:|---:|
| 5 | 20 |

Both are scalar functions: they compare arguments within a single expression evaluation, typically per row. They do not scan across multiple rows of a table to find min/max like the aggregate functions `MIN()` and `MAX()`.

Example where each product has two price tiers:

~~~sql
SELECT product_id,
       LEAST(list_price, sale_price) AS lower_price,
       GREATEST(list_price, sale_price) AS higher_price
FROM products;
~~~

For each row, MySQL compares `list_price` and `sale_price` and returns one of the two values. Define the business meaning of both columns clearly; the function does not inherently know which price is the list price or promotional price.

## 2. Syntax and Usage Contexts

~~~sql
LEAST(value1, value2, ...)
GREATEST(value1, value2, ...)
~~~

These functions can be used in `SELECT`, `WHERE`, `ORDER BY`, `UPDATE`, and other SQL expressions:

~~~sql
SELECT order_id,
       LEAST(requested_quantity, available_quantity) AS fulfillable_quantity
FROM order_requests;
~~~

This caps the shippable quantity by what the customer requested and what is in stock. If either argument is NULL, `LEAST()` also returns NULL; missing-data handling must be decided separately.

Example clamping exam scores between 0 and 100:

~~~sql
SELECT student_id,
       LEAST(GREATEST(raw_score, 0), 100) AS normalized_score
FROM exam_results;
~~~

The expression evaluates in order:

1. `GREATEST(raw_score, 0)` ensures the result is no less than 0.
2. `LEAST(..., 100)` caps the result at 100.

If `raw_score` is NULL, the entire expression remains NULL. Never substitute missing scores with 0 if business logic distinguishes "no score yet" from "score equals zero."

## 3. Distinguishing from MIN() and MAX()

`LEAST()`/`GREATEST()` and `MIN()`/`MAX()` have similar names, yet their evaluation scopes differ:

| Function | Kind | Scope |
|---|---|---|
| LEAST(a, b, c) | Scalar | Compares multiple expressions within one evaluation |
| GREATEST(a, b, c) | Scalar | Compares multiple expressions within one evaluation |
| MIN(column) | Aggregate | Finds the smallest value of one column across a set or group of rows |
| MAX(column) | Aggregate | Finds the largest value of one column across a set or group of rows |

Example picking the lower of two columns for each product:

~~~sql
SELECT product_id, LEAST(price_a, price_b) AS lower_price
FROM product_prices;
~~~

Example finding the lowest price across all products:

~~~sql
SELECT MIN(price_a) AS minimum_price_a
FROM product_prices;
~~~

`MIN()` and `MAX()` are aggregates, so they skip NULL values; if no non-NULL values exist in the input set, the result is NULL. Conversely, `LEAST()` and `GREATEST()` return NULL if any single argument is NULL. This is a critical difference when dealing with missing data.

## 4. NULL Makes LEAST and GREATEST Return NULL

In MySQL, if any argument to `LEAST()` or `GREATEST()` is NULL, the function returns NULL:

~~~sql
SELECT
    LEAST(10, NULL, 20) AS least_result,
    GREATEST(10, NULL, 20) AS greatest_result;
~~~

Both result columns evaluate to NULL, even though the remaining arguments have known values.

### 4.1. NULL Propagates Through Expressions

Suppose `start_price` is 100 and `discount_price` has not been set:

~~~sql
SELECT LEAST(start_price, discount_price) AS effective_price
FROM product_prices;
~~~

The result is NULL, not 100. The function does not assume a missing argument should be skipped.

Similarly, `GREATEST()` does not automatically pick a non-NULL argument. This follows NULL propagation rules: when a required input is unknown, the comparison outcome may be unknown.

### 4.2. Distinguishing NULL from 0 and Empty Strings

~~~sql
SELECT
    LEAST(0, 5) AS zero_and_five,
    LEAST('', 'A') AS empty_and_text,
    LEAST(NULL, 5) AS null_and_five;
~~~

The number 0 is a numeric value; an empty string is a string value; NULL represents the absence of a value. Never replace NULL with 0 or an empty string just to force the function to return a result if doing so alters data semantics.

### 4.3. NULL Originating from LEFT JOIN

A column coming from the right side of a `LEFT JOIN` can be NULL due to no matching row:

~~~sql
SELECT c.customer_id,
       LEAST(c.credit_limit, p.requested_limit) AS allowed_limit
FROM customers AS c
LEFT JOIN pending_limits AS p
  ON p.customer_id = c.customer_id;
~~~

If a customer has no row in `pending_limits`, `p.requested_limit` is NULL in the join output and `allowed_limit` becomes NULL as well. Determine whether "no pending request" means using `credit_limit`, applying no limit, or remaining undetermined. Never let `LEAST()` decide business policy implicitly.

## 5. When You Want to Ignore NULL Arguments

Sometimes business logic wants the smallest/largest among populated arguments, ignoring NULL arguments. `LEAST()` and `GREATEST()` do not perform this automatically.

### 5.1. Two Arguments: Using CASE

For two values `a` and `b`, write it explicitly:

~~~sql
SELECT
    CASE
        WHEN a IS NULL THEN b
        WHEN b IS NULL THEN a
        ELSE LEAST(a, b)
    END AS least_non_null,
    CASE
        WHEN a IS NULL THEN b
        WHEN b IS NULL THEN a
        ELSE GREATEST(a, b)
    END AS greatest_non_null
FROM measurements;
~~~

If both are NULL, the first branch returns `b` (also NULL). If only one value is present, that value is returned. If both are present, the function compares normally.

### 5.2. Multiple Columns Within the Same Row

For three columns, write a `CASE` covering each NULL combination:

~~~sql
SELECT measurement_id,
       CASE
           WHEN value_a IS NULL AND value_b IS NULL THEN value_c
           WHEN value_a IS NULL AND value_c IS NULL THEN value_b
           WHEN value_b IS NULL AND value_c IS NULL THEN value_a
           WHEN value_a IS NULL THEN LEAST(value_b, value_c)
           WHEN value_b IS NULL THEN LEAST(value_a, value_c)
           WHEN value_c IS NULL THEN LEAST(value_a, value_b)
           ELSE LEAST(value_a, value_b, value_c)
       END AS smallest_non_null
FROM measurements;
~~~

If all three columns are NULL, the first condition matches and `value_c` is also NULL, so the result stays NULL. A parallel `CASE` with `GREATEST()` finds the largest non-NULL value. As the column count grows, this becomes verbose; consider normalizing columns into rows or using an appropriate unpivot pattern.

### 5.3. Multiple Columns Across the Whole Table: Using MIN/MAX

To find the min/max across all columns and rows, collapse the columns into one value set with `UNION ALL`:

~~~sql
SELECT MIN(value) AS overall_minimum,
       MAX(value) AS overall_maximum
FROM (
    SELECT value_a AS value FROM measurements
    UNION ALL
    SELECT value_b FROM measurements
    UNION ALL
    SELECT value_c FROM measurements
) AS all_values;
~~~

`MIN()` and `MAX()` ignore NULLs; if all values are NULL, the result remains NULL. This example computes across the entire table rather than per row. Use `UNION ALL` to retain all values and avoid unnecessary deduplication overhead.

### 5.4. Using COALESCE with Sentinel Values Can Be Risky

A common shortcut replaces NULL with an arbitrarily huge or tiny sentinel before calling `LEAST()`/`GREATEST()`. This works only if the sentinel is strictly outside the valid domain and can never occur in real data.

~~~sql
-- Illustrative only; sentinel must be chosen based on the data domain
SELECT LEAST(
    COALESCE(value_a, 999999999),
    COALESCE(value_b, 999999999)
) AS smallest_value
FROM measurements;
~~~

If `999999999` is ever a valid input, the output will be wrong. For dates and times, inventing dummy sentinel dates is even more error-prone. Prefer `CASE` or row-level aggregation with `MIN`/`MAX` when skipping NULLs.

## 6. Numeric Comparison Rules

MySQL selects comparison rules based on argument types. Key rules for `LEAST()` and `GREATEST()`:

- If all arguments are integers, they are compared as integers.
- If at least one argument is `DOUBLE`, all arguments are compared as `DOUBLE`.
- If no argument is `DOUBLE` but at least one is `DECIMAL`, they are compared as `DECIMAL`.
- If the list mixes numbers and strings, arguments are compared as strings.

Therefore, never mix numbers and strings merely because a string looks numeric. `'100'` is a string and does not automatically carry the same semantics as the integer `100` in every expression.

### 6.1. Integer Arguments

~~~sql
SELECT
    LEAST(8, 12, 3) AS min_integer,
    GREATEST(8, 12, 3) AS max_integer;
~~~

All arguments are integers, so they are compared numerically.

### 6.2. DECIMAL and Financial Data

For monetary amounts, use `DECIMAL` with suitable precision and scale:

~~~sql
SELECT LEAST(
           CAST('125.50' AS DECIMAL(12,2)),
           CAST('99.90' AS DECIMAL(12,2))
       ) AS lower_amount;
~~~

`DECIMAL` represents exact decimal numbers according to declared precision/scale. If any argument is `DOUBLE`, MySQL switches to `DOUBLE` comparison, which uses approximate floating-point arithmetic. Avoid letting a stray `DOUBLE` column or literal alter how monetary values are compared.

### 6.3. DOUBLE and Approximate Numbers

~~~sql
SELECT GREATEST(1.25E0, 1.20, 1.30) AS greatest_value;
~~~

Scientific notation like `1.25E0` creates an approximate floating-point literal. Once one argument is `DOUBLE`, comparison switches to `DOUBLE`. If business rules demand exact decimal comparison, convert values to an appropriate `DECIMAL` before calling the function.

### 6.4. Avoid Mixing Numbers with Numeric Strings

A surprising example:

~~~sql
SELECT GREATEST(2, '10') AS result;
~~~

Because the argument list mixes a number and a string, MySQL compares them as strings. Lexicographically, `'2'` is greater than `'10'`, so the chosen result is `2`, even though numerically 10 is greater than 2.

If numeric comparison is intended, cast explicitly:

~~~sql
SELECT GREATEST(
           CAST(2 AS DECIMAL(10,0)),
           CAST('10' AS DECIMAL(10,0))
       ) AS numeric_result;
~~~

The numeric result is 10. Before casting strings to numbers, validate inputs. Non-numeric strings can yield unexpected converted values, warnings, or errors depending on context and SQL mode.

## 7. String Comparison and Collation Rules

When arguments are compared as strings, collation governs ordering. Collations may be case-sensitive or case-insensitive, accent-sensitive or accent-insensitive, and apply specific Unicode rules.

~~~sql
SELECT
    LEAST('apple', 'Banana') AS first_value,
    GREATEST('apple', 'Banana') AS last_value;
~~~

The result depends on the collation applied to the expression. Under a case-insensitive collation, strings differing only in case may be considered equivalent; under a case-sensitive collation, the ordering can change.

### 7.1. Specifying Collation Explicitly

If a specific comparison rule is needed, declare the collation explicitly:

~~~sql
SELECT LEAST(
           _utf8mb4'An' COLLATE utf8mb4_0900_as_cs,
           _utf8mb4'an' COLLATE utf8mb4_0900_as_cs
       ) AS case_sensitive_min;
~~~

`utf8mb4_0900_as_cs` is a MySQL 8.0 collation that is both accent-sensitive and case-sensitive. On other versions, check available collations with `SHOW COLLATION` and select a suitable rule.

### 7.2. Incompatible Collations

If string expressions come from columns or literals with incompatible collations, MySQL may raise a collation-mix error. Inspect them:

~~~sql
SELECT
    CHARSET(column_a) AS charset_a,
    COLLATION(column_a) AS collation_a,
    CHARSET(column_b) AS charset_b,
    COLLATION(column_b) AS collation_b
FROM sample_table
LIMIT 10;
~~~

You can unify charsets/collations before comparing:

~~~sql
SELECT LEAST(
           CONVERT(column_a USING utf8mb4) COLLATE utf8mb4_0900_ai_ci,
           CONVERT(column_b USING utf8mb4) COLLATE utf8mb4_0900_ai_ci
       ) AS least_text
FROM sample_table;
~~~

Only use the target collation if your server supports it and it aligns with business semantics. Never pick an arbitrary collation merely to silence a technical error; a new collation can alter sort order and comparison outcomes.

### 7.3. Binary Strings

If arguments are binary strings, comparison operates on raw bytes rather than linguistic collation rules for text. Never use binary strings in place of proper text collations for comparing names, addresses, or user text unless exact byte ordering is genuinely required.

## 8. Comparing Dates and Times

When comparing timestamps or dates, ensure arguments share the intended `DATE`, `DATETIME`, or `TIMESTAMP` type:

~~~sql
SELECT order_id,
       LEAST(
           CAST(created_at AS DATETIME),
           CAST(deadline_at AS DATETIME)
       ) AS earlier_time,
       GREATEST(
           CAST(created_at AS DATETIME),
           CAST(deadline_at AS DATETIME)
       ) AS later_time
FROM orders;
~~~

If both columns already share the same type and timezone semantics, redundant casting is unnecessary. If one column is a date-time string, convert it explicitly and check for malformed values before comparing.

Example clamping a due date within a year:

~~~sql
SELECT task_id,
       LEAST(
           GREATEST(due_date, DATE '2026-01-01'),
           DATE '2026-12-31'
       ) AS due_date_in_year
FROM tasks;
~~~

Dates before 2026 clamp to `2026-01-01`, dates after 2026 clamp to `2026-12-31`, and dates within range remain unchanged. If `due_date` is NULL, the result remains NULL.

Never mix date/time values with arbitrary string formats or integer epoch timestamps without explicit conversion. When data crosses multiple timezones, normalize timezone conventions prior to comparison.

## 9. Explicit Casting to Control Results

When arguments have different types, use `CAST()` or `CONVERT()` to make intent explicit:

~~~sql
SELECT LEAST(
           CAST(raw_value_a AS DECIMAL(14,3)),
           CAST(raw_value_b AS DECIMAL(14,3))
       ) AS minimum_measurement
FROM sensor_readings;
~~~

Common `CAST` target types:

~~~sql
CAST(value AS SIGNED)
CAST(value AS UNSIGNED)
CAST(value AS DECIMAL(12,2))
CAST(value AS CHAR)
CAST(value AS DATE)
CAST(value AS DATETIME)
~~~

Pick a target type large enough to hold the data. For instance, casting a very large integer to `SIGNED` can overflow or raise an error if it exceeds range; casting currency to `DECIMAL(12,2)` can round or truncate digits beyond scale 2. Verify input ranges and rounding rules.

If the goal is numeric comparison, never cast to `CHAR`. If the goal is collation-based text comparison, never let MySQL infer numeric comparison from one numeric argument.

## 10. Using LEAST and GREATEST to Clamp Values

### 10.1. Clamping Quantities

~~~sql
SELECT request_id,
       GREATEST(requested_quantity, 0) AS nonnegative_quantity
FROM order_requests;
~~~

This clamps negative quantities up to 0. If the column can be NULL, the result remains NULL. If NULL must be treated as 0, write:

~~~sql
SELECT request_id,
       GREATEST(COALESCE(requested_quantity, 0), 0)
           AS nonnegative_quantity
FROM order_requests;
~~~

Only use `COALESCE(..., 0)` if business rules define a missing value as equivalent to quantity zero.

### 10.2. Clamping Durations

~~~sql
SELECT task_id,
       LEAST(
           GREATEST(actual_duration_minutes, 0),
           480
       ) AS capped_duration
FROM task_metrics;
~~~

The output is bounded between 0 and 480 minutes. This is a display or calculation rule; if negative source values or values above 480 indicate anomalies requiring investigation, keep the raw source column for auditing instead of overwriting it with clamped values.

### 10.3. Updating Values with Clamping

You can use these expressions inside `UPDATE`:

~~~sql
UPDATE inventory
SET reserved_quantity =
    LEAST(
        GREATEST(reserved_quantity, 0),
        on_hand_quantity
    )
WHERE product_id = 100;
~~~

This bounds `reserved_quantity` between 0 and available `on_hand_quantity`. Before deploying in concurrent systems, design appropriate transactions and locking so `on_hand_quantity` does not shift unexpectedly between check and update. Scalar functions alone do not enforce concurrency control or cross-row integrity.

## 11. Distinguishing Row-Level Minimums from Table-Level Minimums

Suppose a table stores three readings per device:

~~~sql
CREATE TABLE sensor_readings (
    reading_id BIGINT NOT NULL,
    sensor_id BIGINT NOT NULL,
    value_a DECIMAL(10,2) NULL,
    value_b DECIMAL(10,2) NULL,
    value_c DECIMAL(10,2) NULL,
    PRIMARY KEY (reading_id)
);
~~~

Find the smallest among the three columns for each reading:

~~~sql
SELECT reading_id,
       LEAST(value_a, value_b, value_c) AS row_minimum
FROM sensor_readings;
~~~

If any of the three columns is NULL, `row_minimum` is NULL.

Find the smallest `value_a` across all rows:

~~~sql
SELECT MIN(value_a) AS column_minimum
FROM sensor_readings;
~~~

`MIN(value_a)` skips rows where `value_a` is NULL. This aggregates vertically across table rows rather than comparing columns horizontally within each row.

To find the overall min across all three columns while skipping NULLs:

~~~sql
SELECT MIN(value) AS overall_minimum,
       MAX(value) AS overall_maximum
FROM (
    SELECT value_a AS value FROM sensor_readings
    UNION ALL
    SELECT value_b FROM sensor_readings
    UNION ALL
    SELECT value_c FROM sensor_readings
) AS all_values;
~~~

The query stacks all columns into one value set and applies `MIN()`/`MAX()`; NULLs are skipped by the aggregates. Use `UNION ALL` to retain every value and avoid unnecessary duplicate elimination costs.

## 12. Interaction with WHERE Predicates and Indexes

You can use `LEAST()`/`GREATEST()` inside filter conditions:

~~~sql
SELECT product_id, price_a, price_b
FROM products
WHERE LEAST(price_a, price_b) < 100;
~~~

This expresses intent concisely, yet wrapping columns in a function can prevent MySQL from using regular single-column indexes the way direct comparisons would. On large tables, inspect the plan with `EXPLAIN`.

For two non-NULL columns of identical numeric type, the condition:

~~~sql
WHERE LEAST(price_a, price_b) < 100
~~~

can be rewritten logically as:

~~~sql
WHERE price_a < 100 OR price_b < 100
~~~

However, when NULLs are possible, verify three-valued logic before rewriting. `LEAST()` returns NULL if either column is NULL; conversely, the `OR` condition can evaluate to TRUE when one column is under 100 and the other is NULL. The two expressions are not equivalent in the presence of NULLs.

Never optimize by rewriting expressions without proving equivalence across the entire data domain, including NULLs and data types. Use `EXPLAIN` and representative data to measure actual effectiveness.

## 13. Common Errors and How to Handle Them

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `LEAST(a, b)` returns NULL even when one column has a value | The other argument is NULL | Decide whether NULL should be skipped or yield an undetermined result |
| `GREATEST(2, '10')` picks 2 | Mixing numbers and strings triggers string comparison | Cast all arguments to a matching numeric type |
| Monetary comparisons behave unexpectedly | A `DOUBLE` argument or unintended type coercion is present | Use `DECIMAL` consistently and check precision/scale |
| String ordering differs between environments | Differing or incompatible collations | Check `CHARSET`/`COLLATION` and specify an explicit collation |
| Function does not skip NULL like `MIN` | `LEAST`/`GREATEST` are scalar functions with NULL propagation | Use `CASE` or unpivot values into rows and aggregate with `MIN`/`MAX` |
| Date/time results do not match expectations | Mixed `DATE`/`DATETIME` with strings or numbers | Standardize types with `CAST`/`CONVERT` and timezone conventions |
| Query slows down after putting `LEAST`/`GREATEST` in `WHERE` | Wrapping columns prevents index usage | Read `EXPLAIN`; rewrite predicates only after verifying NULL equivalence |
| Replacing NULL with a sentinel produces wrong answers | The sentinel falls inside the valid value range | Use `CASE` or aggregate functions that naturally ignore NULLs |

## 14. Practice Lab: Comparing Data Types and NULLs

Perform this lab in a sandbox database or development environment where you are permitted to create tables.

**Step 1 — Create the sample table.**

~~~sql
CREATE TABLE lab_measurements (
    measurement_id INT NOT NULL,
    value_a DECIMAL(10,2) NULL,
    value_b DECIMAL(10,2) NULL,
    value_c DECIMAL(10,2) NULL,
    label_a VARCHAR(20) NULL,
    label_b VARCHAR(20) NULL,
    PRIMARY KEY (measurement_id)
) ENGINE=InnoDB;
~~~

**Step 2 — Load sample rows.**

~~~sql
INSERT INTO lab_measurements
    (measurement_id, value_a, value_b, value_c, label_a, label_b)
VALUES
    (1, 10.00, 20.00, 5.00, 'apple', 'Banana'),
    (2, 0.00, 8.00, 12.00, 'A', 'a'),
    (3, NULL, 7.00, 9.00, 'pear', 'orange'),
    (4, NULL, NULL, NULL, NULL, 'kiwi');
~~~

**Step 3 — Compute row-level min/max.**

~~~sql
SELECT measurement_id,
       LEAST(value_a, value_b, value_c) AS row_min,
       GREATEST(value_a, value_b, value_c) AS row_max
FROM lab_measurements
ORDER BY measurement_id;
~~~

Observe rows 3 and 4. Explain why even a single NULL argument turns `LEAST`/`GREATEST` into NULL.

**Step 4 — Compare with aggregates.**

~~~sql
SELECT MIN(value_a) AS min_value_a,
       MAX(value_a) AS max_value_a,
       COUNT(value_a) AS known_value_count
FROM lab_measurements;
~~~

Compare the output with `LEAST(value_a, value_b, value_c)` from the previous step. Explain why aggregate `MIN`/`MAX` skip NULLs while scalar `LEAST`/`GREATEST` do not.

**Step 5 — Test mixed data types.**

~~~sql
SELECT GREATEST(2, '10') AS mixed_result,
       GREATEST(
           CAST(2 AS DECIMAL(10,0)),
           CAST('10' AS DECIMAL(10,0))
       ) AS numeric_result;
~~~

Explain the difference between string comparison and numeric comparison. Try adding `'100'` and `'20'` to observe lexicographical ordering.

**Step 6 — Test collation-sensitive string comparisons.**

~~~sql
SELECT
    LEAST(
        _utf8mb4'An' COLLATE utf8mb4_0900_as_cs,
        _utf8mb4'an' COLLATE utf8mb4_0900_as_cs
    ) AS case_sensitive_result;
~~~

If your server version does not support this collation, use `SHOW COLLATION` to pick an equivalent one and note its case/accent rules.

**Step 7 — Practice skipping NULLs.**

~~~sql
SELECT measurement_id,
       CASE
           WHEN value_a IS NULL THEN value_b
           WHEN value_b IS NULL THEN value_a
           ELSE LEAST(value_a, value_b)
       END AS least_non_null
FROM lab_measurements
ORDER BY measurement_id;
~~~

Verify the row where both `value_a` and `value_b` are NULL. The result must remain NULL.

**Step 8 — Clean up the lab table.**

~~~sql
DROP TABLE lab_measurements;
~~~

Only drop the lab table you created once you finish observing results.

**Expected outcomes:** be able to use `LEAST`/`GREATEST` to compare multiple values within a row; explain NULL propagation; distinguish scalar from aggregate functions; recognize risks of mixing numbers and strings; and apply explicit type casting and collations.

## 15. Principles to Remember

- `LEAST()` returns the smallest argument and `GREATEST()` returns the largest argument in a single evaluation; each needs at least two arguments.
- Both are scalar functions, distinct from aggregate `MIN()`/`MAX()` which scan values across multiple rows.
- Even a single NULL argument causes `LEAST`/`GREATEST` to return NULL.
- `MIN()`/`MAX()` ignore NULLs; never assume `LEAST`/`GREATEST` behave the same way.
- Integer arguments compare as integers; `DOUBLE` switches comparisons to `DOUBLE`; `DECIMAL` is used when `DECIMAL` is present without `DOUBLE`.
- When numbers and strings are mixed, MySQL compares them as strings; cast explicitly if numeric comparison is required.
- Collation governs string comparison ordering; unify charsets/collations if arguments are incompatible.
- Use `CASE` or row-level `MIN`/`MAX` aggregation when NULL arguments must be skipped.
- Never substitute NULL with a sentinel or 0 if that value carries business meaning.
- Verify NULL logic before rewriting `LEAST`/`GREATEST` predicates for index optimization.
- Use `DECIMAL` for financial figures requiring exact decimal comparisons; avoid letting `DOUBLE` alter calculation rules.

Once you understand NULL rules, data types, and collations, you can use `LEAST`/`GREATEST` to clamp and compare values without triggering bugs from implicit type conversions. Clarify the semantics of missing data and standardize argument types directly within your SQL expressions.
