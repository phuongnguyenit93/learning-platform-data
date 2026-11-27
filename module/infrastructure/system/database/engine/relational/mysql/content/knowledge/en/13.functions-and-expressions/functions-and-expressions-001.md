# Arithmetic Expressions, Precedence, and Division / or DIV

Arithmetic expressions appear in almost every MySQL query: calculating line amounts, discounts, taxes, ratios, remaining quantities, durations, or remainders during allocation. Expressions such as `quantity * unit_price`, `total / item_count`, or `balance - amount` look simple, yet can produce wrong results without understanding data types, operator precedence, integer division, `NULL`, overflow, and division by zero.

This lesson belongs to the **DATABASE_MYSQL** module. The module aims at mastering MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control, while practicing reading execution plans, query optimization, privilege management, backup, and handling relational database operational issues. Within the **Functions and Expressions** chapter, this lesson focuses on arithmetic expressions, operator evaluation order, and how to choose `/`, `DIV`, `%`, or `MOD()` according to the exact business semantics.

## 1. Arithmetic Expressions in SQL

An arithmetic expression combines operands, operators, and parentheses to produce a numeric value. Operands can be literals, columns, variables, functions, or subexpressions.

```sql
SELECT
    10 + 5 AS addition_result,
    10 - 5 AS subtraction_result,
    10 * 5 AS multiplication_result,
    10 / 5 AS division_result,
    10 DIV 3 AS integer_division_result,
    10 % 3 AS remainder_result;
```

Expressions can appear in:

- `SELECT` to compute returned values.
- `WHERE` or `HAVING` to filter rows and groups.
- `ORDER BY` to sort by a computed value.
- `UPDATE` to calculate a column's new value.
- `INSERT ... SELECT` to transform data during loading.
- Generated columns or functional indexes when an expression is used frequently and complies with MySQL's rules.

Business example:

```sql
SELECT
    order_item_id,
    quantity,
    unit_price,
    quantity * unit_price AS line_amount
FROM order_items;
```

Here `quantity` and `unit_price` are operands; `*` is the multiplication operator; `line_amount` is the alias for the result.

## 2. Basic Arithmetic Operators

| Operator | Meaning | Example | Result |
|---|---|---|---:|
| `+` | Addition | `8 + 3` | `11` |
| `-` | Subtraction | `8 - 3` | `5` |
| `*` | Multiplication | `8 * 3` | `24` |
| `/` | Ordinary division | `8 / 3` | Result with fractional part |
| `DIV` | Integer division truncated toward 0 | `8 DIV 3` | `2` |
| `%` | Remainder | `8 % 3` | `2` |
| `MOD` | Remainder, equivalent to `%` | `MOD(8, 3)` | `2` |

MySQL also supports unary `+` and `-`:

```sql
SELECT
    +12 AS positive_value,
    -12 AS negative_value,
    -(-12) AS double_negative;
```

`MOD(N, M)` is a function with the same meaning as the `N % M` operator. You can use the function form when it makes the expression easier to read or when passing arguments through a SQL-generating API.

Exponentiation is not the `^` operator in MySQL. `^` is bitwise XOR. If you need exponentiation, use `POW()` or `POWER()`:

```sql
SELECT POW(2, 3) AS eight;
```

## 3. Precedence Order of Arithmetic Operators

When an expression contains multiple operators, MySQL relies on precedence rules to determine which part is evaluated first. Among common arithmetic operators:

1. Unary `+` and `-`.
2. Multiplication `*`, division `/`, integer division `DIV`, remainder `%` and `MOD`.
3. Addition `+` and subtraction `-`.

Operations at the same precedence level associate from left to right in ordinary arithmetic expressions. Parentheses `()` allow you to specify the exact evaluation order and should be used whenever an expression might be misread.

### 3.1. Multiplication and Division Execute Before Addition and Subtraction

```sql
SELECT 10 + 6 * 2 AS result;
```

The result is `22`, because `6 * 2` is evaluated first and then 10 is added.

If you want addition first:

```sql
SELECT (10 + 6) * 2 AS result;
```

The result is `32`.

### 3.2. DIV, MOD, and Multiplication Share the Same Precedence

```sql
SELECT 20 / 5 * 2 AS result;
```

Division and multiplication share the same precedence, so the expression associates left to right: `(20 / 5) * 2`.

Similarly:

```sql
SELECT 20 DIV 3 * 2 AS result;
SELECT 20 % 6 + 1 AS result;
```

To avoid relying on readers memorizing precedence rules, you can write it explicitly:

```sql
SELECT (20 DIV 3) * 2 AS result;
SELECT (20 % 6) + 1 AS result;
```

### 3.3. Parentheses Clarify Business Intent

The following two expressions are not identical:

```sql
SELECT amount * tax_rate / 100 AS tax_amount
FROM invoices;

SELECT amount * (tax_rate / 100) AS tax_amount
FROM invoices;
```

Mathematically they represent the same ratio, but expression grouping can affect intermediate types and arithmetic precision. With `DECIMAL`, MySQL applies precision/scale rules at each operation; when a result requires a specific scale, use `CAST()` or `ROUND()` at the exact business step.

Do not rely on an expression "looking like math" and ignore data types. Write parentheses so reviewers clearly understand the formula, especially when division, ratios, or monetary calculations are involved.

## 4. Ordinary Division `/`

The `/` operator performs division and can return a fractional part. For exact-value operands such as integers and `DECIMAL`, MySQL performs exact arithmetic according to numeric type precision/scale rules. For approximate-value operands such as `FLOAT` or `DOUBLE`, the result is an approximate floating-point number.

```sql
SELECT
    5 / 2 AS exact_division,
    1 / 3 AS one_third,
    1.0E0 / 3 AS approximate_division;
```

With exact-value division, the number of decimal digits in the result is influenced by `div_precision_increment` (default is 4) along with the precision/scale of the operands. Check the current value:

```sql
SELECT @@SESSION.div_precision_increment;
```

Do not depend on the default number of decimal digits when the result represents business data. If a specific scale is needed, cast explicitly:

```sql
SELECT CAST(1 AS DECIMAL(12, 4)) /
       CAST(3 AS DECIMAL(12, 4)) AS ratio;
```

### 4.1. Dividing Integers with `/` Can Still Produce a Fractional Part

```sql
SELECT 7 / 2 AS ordinary_division;
```

The result has a fractional part, according to the precision/scale applied by MySQL. Do not use `/` if the goal is to discard the fractional part.

### 4.2. Dividing Decimal Numbers

```sql
SELECT
    CAST(125000 AS DECIMAL(14, 2)) /
    CAST(3 AS DECIMAL(14, 2)) AS average_amount;
```

For monetary values, use `DECIMAL` instead of `FLOAT`/`DOUBLE`. Floating-point types store approximate binary values, so some decimal numbers cannot be represented exactly. Repeatedly summing money can accumulate subtle errors if approximate types are used.

### 4.3. Controlling Scale with CAST and ROUND

`CAST()` converts a result to a type with the specified precision/scale; `ROUND()` rounds to the requested number of decimal places.

```sql
SELECT
    CAST(10 / 3 AS DECIMAL(12, 4)) AS cast_result,
    ROUND(10 / 3, 2) AS rounded_result;
```

The two operations serve different purposes:

- `CAST(... AS DECIMAL(p, s))` defines the data type and scale of the converted value.
- `ROUND(value, d)` applies rounding rules to `d` decimal places.

Do not use `ROUND()` merely to mask a calculation with the wrong scale. First determine the business rounding rule: rounding per line or rounding only the final total can yield different results.

## 5. Integer Division `DIV`

`DIV` performs division and returns the integer part. The fractional part is discarded toward zero (truncate toward zero), rather than always rounding down.

```sql
SELECT
    7 DIV 2 AS positive_result,
    -7 DIV 2 AS negative_result,
    7 DIV -2 AS negative_divisor_result;
```

The results are `3`, `-3`, and `-3`, respectively.

### 5.1. DIV Differs from FLOOR

This is an important distinction for negative numbers:

```sql
SELECT
    -7 DIV 2 AS integer_division,
    FLOOR(-7 / 2) AS floor_result,
    TRUNCATE(-7 / 2, 0) AS truncate_result;
```

Results:

- `-7 DIV 2` is `-3` because the fractional part is discarded toward 0.
- `FLOOR(-7 / 2)` is `-4` because `FLOOR()` returns the greatest integer less than or equal to the value.
- `TRUNCATE(-7 / 2, 0)` is `-3` because it truncates the decimal part toward 0.

Therefore, `DIV` cannot replace `FLOOR()` in every formula. Choose based on the business definition.

### 5.2. Example: Splitting Total Minutes into Hours and Minutes

Assume `duration_minutes` is a non-negative number of minutes:

```sql
SELECT
    duration_minutes DIV 60 AS hours_part,
    MOD(duration_minutes, 60) AS minutes_part
FROM task_durations;
```

For 135 minutes, the result is 2 hours and 15 minutes. `DIV` gets the whole hours, and `MOD()` gets the remaining minutes.

### 5.3. DIV Is Not Rounding

If you want to round 2.7 to 3, use `ROUND(2.7)`. `2.7 DIV 1` returns 2 because it drops the fractional part. If you want the greatest integer less than or equal to the value, use `FLOOR()`; if you want the smallest integer greater than or equal to the value, use `CEIL()` or `CEILING()`.

## 6. Remainder `%` and the MOD() Function

`%` and `MOD()` return the remainder of a division:

```sql
SELECT
    17 % 5 AS remainder_operator,
    MOD(17, 5) AS remainder_function;
```

Both return `2`.

With negative operands, the remainder takes the sign of the left operand (dividend):

```sql
SELECT
    MOD(-17, 5) AS negative_dividend,
    MOD(17, -5) AS negative_divisor,
    MOD(-17, -5) AS both_negative;
```

The results are `-2`, `2`, and `-2`, respectively.

### 6.1. Example: Checking Even/Odd Numbers

```sql
SELECT
    product_id,
    CASE
        WHEN product_id % 2 = 0 THEN 'EVEN'
        ELSE 'ODD'
    END AS id_parity
FROM products;
```

If `product_id` can be negative, the even/odd check still works because even numbers have a remainder of 0.

### 6.2. Allocating the Remainder

Suppose 101 units must be distributed across 4 groups. Integer division shows the minimum each group receives; modulo shows how much remains:

```sql
SELECT
    101 DIV 4 AS base_amount,
    101 MOD 4 AS remainder_amount;
```

The result is 25 units per group with a remainder of 1. The remainder must be allocated according to a deterministic business rule, such as adding one unit sequentially to the first group in key order. Do not discard the remainder if total allocation must preserve the original quantity.

### 6.3. MOD with Decimal Numbers

`MOD()` can work with decimal values:

```sql
SELECT MOD(10.5, 3.2) AS decimal_remainder;
```

The result type and precision depend on the operand types. If an exact result is required, use `DECIMAL` instead of `FLOAT`/`DOUBLE`.

## 7. Comparing `/`, DIV, and MOD

| Expression | Result | Meaning |
|---|---:|---|
| `17 / 5` | `3.4` | Ordinary division, preserves fractional part. |
| `17 DIV 5` | `3` | Integer division, truncates toward 0. |
| `17 % 5` | `2` | Remainder. |
| `MOD(17, 5)` | `2` | Remainder in function form. |
| `-17 DIV 5` | `-3` | Negative integer division, truncates toward 0. |
| `FLOOR(-17 / 5)` | `-4` | Rounds down to the smaller integer. |
| `MOD(-17, 5)` | `-2` | Remainder carries the sign of the dividend. |

Choose the operator based on the question:

- Need a ratio or average with a fractional part: `/`.
- Need the number of full groups or whole units: `DIV`.
- Need what is left over after division: `%` or `MOD()`.
- Need rounding: `ROUND()`, `FLOOR()`, or `CEIL()` depending on the rule.

## 8. How Data Types Affect Calculations

MySQL has the following main numeric type groups:

| Group | Typical Types | Characteristics |
|---|---|---|
| Exact integers | `TINYINT`, `SMALLINT`, `MEDIUMINT`, `INT`, `BIGINT` | Store whole numbers; can be declared `UNSIGNED`. |
| Exact decimals | `DECIMAL(p, s)` | Store decimal values by precision and scale; suitable for money and figures requiring decimal exactness. |
| Approximate numbers | `FLOAT`, `DOUBLE` | Store binary floating-point numbers; may incur representation error. |

### 8.1. Exact-Value and Approximate-Value

Example using `DECIMAL`:

```sql
SELECT
    CAST(0.1 AS DECIMAL(10, 2)) +
    CAST(0.2 AS DECIMAL(10, 2)) AS exact_sum;
```

With `DECIMAL`, calculations are performed using exact decimal arithmetic within the supported precision range.

With floating-point numbers:

```sql
SELECT CAST(0.1 AS DOUBLE) + CAST(0.2 AS DOUBLE) AS approximate_sum;
```

The result may display close to `0.3`, yet the underlying binary value is not necessarily equal to exact 0.3. Do not use strict equality comparisons on `FLOAT`/`DOUBLE` results if the business logic requires a tolerance.

### 8.2. Monetary Values Should Use DECIMAL

Schema example:

```sql
CREATE TABLE invoice_lines (
    invoice_line_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    quantity        DECIMAL(12, 3) NOT NULL,
    unit_price      DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (invoice_line_id)
);
```

Computing line amount:

```sql
SELECT
    invoice_line_id,
    quantity,
    unit_price,
    CAST(quantity * unit_price AS DECIMAL(18, 2)) AS line_amount
FROM invoice_lines;
```

Choosing precision/scale should be based on the maximum expected quantity, unit price, and total amount. `DECIMAL(18,2)` is only an example; do not copy these parameters blindly for every business domain.

### 8.3. Integers and UNSIGNED

`UNSIGNED` extends the positive range of values but cannot represent negative numbers. It suits quantities, counts, or IDs when the business domain is non-negative. However, subtraction can produce negative numbers even when every operand is non-negative.

For example, stock quantity is `BIGINT UNSIGNED`:

```sql
SELECT quantity - 5 AS remaining_quantity
FROM inventory;
```

If `quantity` is less than 5, subtraction can yield a negative value outside the unsigned operation's range, and MySQL may raise an out-of-range error. Do not assume an unsigned column automatically converts to signed when a calculation requires a negative number.

If a negative number is a valid outcome, cast explicitly:

```sql
SELECT CAST(quantity AS SIGNED) - 5 AS signed_difference
FROM inventory;
```

If the business logic prohibits negative inventory, guard the condition directly in the update statement instead of casting to mask the error:

```sql
UPDATE inventory
SET quantity = quantity - 5
WHERE product_id = 1001
  AND quantity >= 5;
```

The application must check the affected row count to determine whether the inventory deduction succeeded.

### 8.4. NO_UNSIGNED_SUBTRACTION

The `NO_UNSIGNED_SUBTRACTION` SQL mode changes how MySQL handles subtraction results involving unsigned operands: the result is treated as signed in applicable cases. This can allow expressions to represent negative numbers, yet it also changes the result type and range of existing SQL.

Check the mode:

```sql
SELECT @@SESSION.sql_mode;
```

Do not enable this mode just to silence an error on one negative inventory subtraction. First determine whether negative numbers are valid in the business domain, pick appropriate data types, and test queries that depend on the result type.

## 9. Type Conversion and Explicit Casting

MySQL can perform implicit type conversion when expressions mix numbers, strings, or other types. While convenient in short queries, this can produce unexpected results when input data is inconsistent.

```sql
SELECT
    '12' + 3 AS numeric_string,
    CAST('12.50' AS DECIMAL(10, 2)) + 1 AS decimal_value;
```

Numeric strings can be converted to numbers in an arithmetic context. Non-numeric strings may generate warnings or be converted according to MySQL rules and SQL mode. Do not rely on implicit conversion for user-supplied data.

Use `CAST()` or `CONVERT()` when you want to make the type explicit:

```sql
SELECT
    CAST(raw_quantity AS DECIMAL(12, 3)) *
    CAST(raw_price AS DECIMAL(14, 2)) AS calculated_amount
FROM imported_order_lines;
```

Before casting imported data, validate that the input strings are well-formed. `CAST()` does not replace validation; malformed values can still generate warnings or unintended conversions.

## 10. NULL in Arithmetic Expressions

If any operand is `NULL`, the result of a normal arithmetic operation is also `NULL`:

```sql
SELECT
    10 + NULL AS add_result,
    10 - NULL AS subtract_result,
    10 * NULL AS multiply_result,
    10 / NULL AS divide_result;
```

`NULL` means a missing or unknown value, not the number 0. Therefore, you should not automatically replace every `NULL` with 0 unless business rules specify so.

If business rules define that `NULL` must be treated as 0, use `COALESCE()` explicitly:

```sql
SELECT COALESCE(shipping_fee, 0) + item_total AS payable_amount
FROM orders;
```

If `NULL` means "shipping fee not yet calculated", replacing it with 0 can produce inaccurate reports. Distinguish between "no value", "value equals 0", and "not yet determined".

### 10.1. NULLIF to Guard the Denominator

`NULLIF(a, b)` returns `NULL` if `a = b`; otherwise it returns `a`. Combine it with division to guard against a zero denominator:

```sql
SELECT
    revenue / NULLIF(order_count, 0) AS average_order_value
FROM customer_statistics;
```

When `order_count = 0`, `NULLIF()` returns `NULL`, so the division result is `NULL`. This is a concise approach when an "undefined" result matches business semantics.

### 10.2. CASE When a Specific Result Rule Is Needed

If you want to explicitly express the zero-denominator case:

```sql
SELECT
    CASE
        WHEN order_count = 0 THEN 0
        ELSE revenue / order_count
    END AS average_order_value
FROM customer_statistics;
```

Return 0 only if business logic defines the average when there are no orders as 0. If having no orders means there is no basis to compute an average, `NULL` usually reflects reality more accurately.

## 11. Division by Zero and Error Handling

Division with a zero denominator does not produce a valid numeric value. In a `SELECT` query, an expression like `1 / 0` normally returns `NULL` along with a warning. In data-modifying statements such as `INSERT` or `UPDATE`, behavior can be stricter and the statement may be rejected depending on SQL mode, especially when strict mode is enabled.

Check behavior on the current session:

```sql
SELECT 1 / 0 AS division_result;
SHOW WARNINGS;
```

`SHOW WARNINGS` must be executed immediately after the statement being inspected because a subsequent statement may overwrite the current warning list.

### 11.1. Safe Pattern with NULLIF

```sql
SELECT numerator / NULLIF(denominator, 0) AS ratio
FROM metrics;
```

### 11.2. Safe Pattern with CASE

```sql
SELECT
    CASE
        WHEN denominator IS NULL OR denominator = 0 THEN NULL
        ELSE numerator / denominator
    END AS ratio
FROM metrics;
```

### 11.3. Do Not Use IFNULL Arbitrarily to Mask a Zero Denominator

The following example avoids errors but alters the mathematical meaning:

```sql
-- Avoid using this without an explicit business rule:
SELECT numerator / IFNULL(denominator, 1)
FROM metrics;
```

When the denominator is `NULL`, the statement silently substitutes 1. The result then no longer reflects the original ratio. Use `NULLIF(denominator, 0)` to handle zero denominators specifically and decide explicitly how `NULL` should be treated.

## 12. Functions Commonly Combined with Arithmetic Expressions

| Function | Purpose | Example |
|---|---|---|
| `ABS(x)` | Absolute value | `ABS(-12)` → `12` |
| `SIGN(x)` | Sign of a number: -1, 0, or 1 | `SIGN(-8)` → `-1` |
| `ROUND(x, d)` | Round to `d` decimal places | `ROUND(12.345, 2)` |
| `TRUNCATE(x, d)` | Truncate decimal part after `d` digits | `TRUNCATE(12.349, 2)` → `12.34` |
| `FLOOR(x)` | Greatest integer not exceeding x | `FLOOR(3.8)` → `3` |
| `CEIL(x)` / `CEILING(x)` | Smallest integer not less than x | `CEIL(3.2)` → `4` |
| `MOD(a, b)` | Remainder | `MOD(17, 5)` → `2` |
| `POW(a, b)` / `POWER(a, b)` | Exponentiation | `POW(2, 3)` → `8` |
| `SQRT(x)` | Square root | `SQRT(81)` → `9` |

Example distinguishing rounding, truncating, and floor with negative numbers:

```sql
SELECT
    ROUND(-3.7) AS rounded_value,
    TRUNCATE(-3.7, 0) AS truncated_value,
    FLOOR(-3.7) AS floor_value,
    CEIL(-3.7) AS ceil_value;
```

`TRUNCATE()` drops the fractional part toward 0; `FLOOR()` moves toward the smaller integer; `CEIL()` moves toward the larger integer. The three functions are not interchangeable.

## 13. Business Example: Line Amount, Discount, and Tax

Suppose an invoice line has quantity, unit price, discount rate, and tax rate. The formula should clearly express the sequence:

1. Gross amount = quantity × unit price.
2. Discount amount = gross amount × discount rate / 100.
3. Net amount = gross amount − discount amount.
4. Tax amount = net amount × tax rate / 100.
5. Total payable = net amount + tax amount.

Query example:

```sql
SELECT
    order_item_id,
    quantity,
    unit_price,
    discount_rate,
    tax_rate,
    ROUND(quantity * unit_price, 2) AS gross_amount,
    ROUND(quantity * unit_price * discount_rate / 100, 2) AS discount_amount,
    ROUND(
        quantity * unit_price * (1 - discount_rate / 100),
        2
    ) AS net_amount,
    ROUND(
        quantity * unit_price * (1 - discount_rate / 100)
        * tax_rate / 100,
        2
    ) AS tax_amount
FROM order_items;
```

This is an illustrative formula. In real financial systems, you must clearly establish:

- Whether rates are stored as percentages (e.g., 10.00) or decimal fractions (0.10).
- Whether rounding occurs per line, per tax type, or only on the invoice total.
- Whether tax is calculated before or after discounts.
- Whether specific rules exist for individual currencies.
- Whether computed values must be persisted for auditing or recomputed from source data.

Never let the same column store `10` (10%) in some rows and `0.10` (10%) in others. Use naming and constraints to enforce the unit, such as `discount_percent` or `discount_rate` following one fixed convention.

## 14. Expressions in WHERE and Index Usage

An arithmetic expression in `WHERE` can prevent a condition from using an index on the underlying column if MySQL has to evaluate the expression for every row.

For example, table `products` has an index on `unit_price`:

```sql
-- An expression on the column can prevent an index range scan:
SELECT product_id, unit_price
FROM products
WHERE unit_price * 1.1 > 100000;
```

Since the factor 1.1 is a positive constant, the condition can be rewritten into a mathematically equivalent form:

```sql
SELECT product_id, unit_price
FROM products
WHERE unit_price > 100000 / 1.1;
```

Verify equivalence regarding numeric type, precision, and rounding before rewriting. For complex expressions or expressions depending on multiple columns, it is not always possible to rewrite into a condition on a single column.

Check the execution plan:

```sql
EXPLAIN
SELECT product_id, unit_price
FROM products
WHERE unit_price > 100000 / 1.1;
```

Do not assume a rewritten expression is guaranteed to use an index; the optimizer also weighs selectivity, statistics, and access cost.

### 14.1. Generated Columns for Frequently Used Expressions

If the system frequently filters or sorts by a line item's amount, consider a generated column:

```sql
CREATE TABLE order_items (
    order_item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    quantity      DECIMAL(12, 3) NOT NULL,
    unit_price    DECIMAL(14, 2) NOT NULL,
    line_amount   DECIMAL(18, 2)
        GENERATED ALWAYS AS (ROUND(quantity * unit_price, 2)) STORED,
    PRIMARY KEY (order_item_id),
    KEY idx_order_items_line_amount (line_amount)
);
```

A generated column stores or computes its value based on the expression definition. `STORED` saves the calculated value on write; `VIRTUAL` computes it on read according to MySQL's mechanism. Indexes can be created on generated columns when the type and expression meet MySQL's requirements.

If using MySQL 8.0.13 or later, functional indexes are also an option for certain expressions:

```sql
CREATE INDEX idx_items_amount_expression
ON order_items ((quantity * unit_price));
```

Functional indexes have syntax, type, and expression validity requirements; verify them on the target server version. Do not create indexes just because an expression appears in a rare query; indexes increase storage footprint and write overhead.

## 15. Updating Data Using Arithmetic Expressions

`UPDATE` can use a column's current value to compute its new value:

```sql
UPDATE products
SET stock_quantity = stock_quantity - 1
WHERE product_id = 1001
  AND stock_quantity >= 1;
```

The `stock_quantity >= 1` condition ensures stock does not go below 0 if multiple concurrent requests update the row simultaneously. The application should check the update count:

- One row updated: the inventory deduction succeeded.
- Zero rows updated: the product does not exist or stock is insufficient (separate query/logic is needed if you must distinguish between the two).

For monetary operations, perform calculations in a conditional statement within an appropriate transaction instead of reading the value to the application, computing on the client, and overwriting the old value. Atomic updates reduce the risk of lost updates.

Example balance deduction:

```sql
UPDATE accounts
SET balance = balance - 50000.00
WHERE account_id = 101
  AND balance >= 50000.00;
```

This is only one step in a funds transfer workflow; a real system needs a transaction encompassing debit, credit, affected row checks, and rollback if any step fails.

## 16. Overflow, Precision, and Warnings

Every numeric type has a finite value range and precision. Calculation results can exceed the target type's range or fail to fit within the declared precision/scale.

For instance, a `DECIMAL(8,2)` column holds at most eight digits in total, two of which are after the decimal point. If a calculation produces an out-of-range value, MySQL may raise an error or warning depending on the statement, SQL mode, and conversion context.

Inspect values and warnings after test operations:

```sql
SELECT CAST(99999999.99 AS DECIMAL(8, 2)) AS boundary_value;
SHOW WARNINGS;
```

Test boundaries using representative data and expected maximum values, rather than testing only average cases.

Safe design steps:

1. Identify the minimum/maximum possible values for each operand.
2. Compute the result range for addition, multiplication, division, or aggregation.
3. Choose a data type with sufficient precision and scale.
4. Define rounding rules and when rounding takes place.
5. Verify SQL mode and warnings in the corresponding environment.
6. Use `CAST()` when you need to lock down the result type at storage or interface boundaries.

## 17. Practice Exercises

### Exercise 1: Precedence Order

Run the following expressions:

```sql
SELECT 10 + 6 * 2;
SELECT (10 + 6) * 2;
SELECT 20 / 5 * 2;
SELECT 20 DIV 3 * 2;
```

**Requirement:** Explain the evaluation order and rewrite them with parentheses to show the intent clearly.

### Exercise 2: Comparing `/` and DIV

Run:

```sql
SELECT
    17 / 5,
    17 DIV 5,
    -17 / 5,
    -17 DIV 5,
    FLOOR(-17 / 5);
```

**Requirement:** Explain why `DIV` differs from `FLOOR()` when the result is negative.

### Exercise 3: Remainder and Allocation

Divide 103 products among 6 groups. Calculate the minimum number of products each group receives and the remainder using `DIV` and `MOD`.

**Requirement:** Propose a remainder allocation rule so that the total allocated products still equals 103.

### Exercise 4: DECIMAL and DOUBLE Types

Compare the addition result of `0.1 + 0.2` when using `DECIMAL` and `DOUBLE`.

**Requirement:** Explain which type is appropriate for money and why approximate results should not be compared with strict equality.

### Exercise 5: Division by Zero and NULLIF

Create a statistics table with `revenue` and `order_count`, including a row where `order_count = 0`. Calculate the average value using `/`, then using `NULLIF()`.

**Requirement:** Record the results and warnings; decide whether the business result should be `NULL` or 0.

### Exercise 6: Subtraction with UNSIGNED

Create an `INT UNSIGNED` column `quantity` and try subtracting a number larger than the current value in a test environment.

**Requirement:** Observe the error or result under the active SQL mode; write a conditional `UPDATE` statement to prevent negative inventory.

### Exercise 7: Calculating Amounts and Rounding

Create an invoice line table with `quantity`, `unit_price`, `discount_percent`, and `tax_percent`. Write a query to compute gross amount, discount, net amount, and tax.

**Requirement:** State the rounding rule at each step and compare it with rounding only the final total.

### Exercise 8: Checking Index Usage with Expressions

Create an index on `unit_price`. Compare the `EXPLAIN` output of `unit_price * 1.1 > ...` against the equivalently rewritten condition.

**Requirement:** Record the access type, key, and estimated row count; explain when to consider a generated column or functional index.

## 18. Arithmetic Expression Review Checklist

- [ ] The operator matches the intended semantics: `/`, `DIV`, `%`, or `MOD()`.
- [ ] Precedence order is explicitly clarified using parentheses when needed.
- [ ] Operand data types (exact vs. approximate) have been evaluated.
- [ ] Money and values needing decimal precision use an appropriate `DECIMAL`.
- [ ] Result precision/scale accommodates the largest expected value.
- [ ] Division handles zero denominators and `NULL` per business rules.
- [ ] Operations on `UNSIGNED` do not cause unintended underflow.
- [ ] Rounding/truncation rules are clearly defined.
- [ ] Implicit type conversions are replaced with `CAST()` when determinism is required.
- [ ] `WHERE` predicates do not wrap indexed columns in expressions when an equivalent form is better.
- [ ] Balance/inventory updates use atomic conditions and check affected rows.
- [ ] Boundary cases, warnings, and SQL mode have been tested.

## 19. Takeaways

In MySQL, multiplication, division, `DIV`, and modulo are evaluated before addition and subtraction; parentheses make formulas unambiguous. `/` retains the fractional part, `DIV` truncates toward 0, and `%`/`MOD()` returns the remainder. `DIV` differs from `FLOOR()` for negative numbers. `DECIMAL` is suited for money and exact decimal arithmetic; `FLOAT`/`DOUBLE` are approximate numbers.

Arithmetic expressions are also shaped by `NULL`, division by zero, `UNSIGNED`, precision/scale, and SQL mode. Guard denominators with `NULLIF()` or `CASE`, use `CAST()` when explicit types are needed, align rounding rules with business requirements, and inspect execution plans whenever expressions appear in filter predicates. A sound SQL formula does not merely execute—it preserves data integrity across edge cases.
