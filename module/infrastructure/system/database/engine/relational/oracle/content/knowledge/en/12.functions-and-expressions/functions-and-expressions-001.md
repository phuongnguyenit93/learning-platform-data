# Arithmetic Expressions, Operator Precedence, and Division Handling

In Oracle Database, arithmetic expressions appear in almost every SQL statement: calculating gross amounts, discounts, completion rates, average scores, day differences, or cost allocations. An expression such as `quantity * unit_price - discount / 100` can produce unintended results if the author does not understand **operator precedence**, **operation grouping**, **the numeric data types of operands**, and **how to handle zero or NULL denominators**.

This lesson explains how Oracle evaluates `+`, `-`, `*`, and `/`; how to use parentheses to express the exact intent; the difference between numeric division and integer division in business logic; rounding methods; and safe SQL patterns when the denominator might be zero. The examples can be executed using SQL*Plus, SQLcl, or any compatible SQL tool.

## 1. What is an arithmetic expression?

An arithmetic expression is a combination of **constants**, **columns**, **bind variables**, **functions**, and **operators** that produces a numeric value. For example:

~~~sql
SELECT quantity * unit_price AS gross_amount,
       quantity * unit_price - discount_amount AS net_amount
FROM order_items;
~~~

In the query above:

- `quantity` and `unit_price` are numeric columns.
- `*` is the multiplication operator.
- `discount_amount` is subtracted from the pre-discount gross amount.
- `AS gross_amount` and `AS net_amount` assign column aliases to the results.

An expression can appear in multiple clauses:

~~~sql
SELECT order_id,
       quantity * unit_price AS line_total
FROM order_items
WHERE quantity * unit_price > 100000
ORDER BY quantity * unit_price DESC;
~~~

Oracle evaluates expressions according to SQL rules and the data types of the operands. Whether an expression appears in `SELECT`, `WHERE`, or `ORDER BY` does not change the mathematical meaning of the operators; however, the optimizer may choose different execution plans for the query.

### 1.1 The four basic arithmetic operators

| Operator | Name | Example | Result |
|---|---|---|---:|
| `+` | Addition | `12 + 5` | 17 |
| `-` | Subtraction | `12 - 5` | 7 |
| `*` | Multiplication | `12 * 5` | 60 |
| `/` | Division | `12 / 5` | 2.4 |

Oracle SQL does not have a dedicated integer division operator like some programming languages. The `/` operator performs numeric division and can produce a fractional part. If business logic requires an integer part, you must explicitly choose `TRUNC`, `FLOOR`, or another appropriate function.

## 2. Operator precedence

Basic rules for arithmetic expressions:

1. Unary operators such as unary plus `+x` and unary minus `-x`.
2. Multiplication `*` and division `/`.
3. Addition `+` and subtraction `-`.
4. Operators with the same precedence are evaluated from left to right in standard arithmetic expressions.
5. Parentheses `(...)` are evaluated before expressions outside them and allow the author to explicitly specify operation grouping.

Example:

~~~sql
SELECT 100 + 20 * 3 AS result
FROM dual;
~~~

The result is `160`, because Oracle evaluates `20 * 3` first and then adds 100:

~~~text
100 + 20 * 3
= 100 + 60
= 160
~~~

If the intent is to add first and then multiply:

~~~sql
SELECT (100 + 20) * 3 AS result
FROM dual;
~~~

The result is `360`:

~~~text
(100 + 20) * 3
= 120 * 3
= 360
~~~

### 2.1 Multiplication and division share the same precedence

`*` and `/` have equal precedence. Without parentheses, they are evaluated from left to right:

~~~sql
SELECT 20 / 5 * 2 AS left_to_right,
       20 / (5 * 2) AS grouped_denominator
FROM dual;
~~~

| Expression | Grouping | Result |
|---|---|---:|
| `20 / 5 * 2` | `(20 / 5) * 2` | 8 |
| `20 / (5 * 2)` | `20 / 10` | 2 |

This is a common mistake when calculating ratios or unit prices. If you want to divide by the **product of two values**, you must enclose the entire product in parentheses.

### 2.2 Addition and subtraction share the same precedence

`+` and `-` also have equal precedence, evaluated from left to right:

~~~sql
SELECT 100 - 20 + 5 AS left_to_right,
       100 - (20 + 5) AS subtract_group
FROM dual;
~~~

The results are `85` and `75`, respectively. The two expressions are not equivalent because the parentheses change the grouping of operations.

### 2.3 Unary minus and subtraction

~~~sql
SELECT -5 * 2 AS negative_product,
       5 * -2 AS product_negative,
       5 - -2 AS subtract_negative
FROM dual;
~~~

The results are `-10`, `-10`, and `7`. A minus sign placed before an operand is a sign-negation operator; a `-` between two expressions is subtraction. When expressions become complex, use parentheses to make the intent clear to readers:

~~~sql
SELECT 100 - (-20) AS add_twenty,
       -(100 - 20) AS negate_difference
FROM dual;
~~~

### 2.4 Parentheses clarify business intent

Consider the formula for calculating the payable amount:

~~~text
Gross amount = quantity × unit price
Discount = gross amount × discount rate / 100
Payable amount = gross amount - discount
~~~

SQL clearly expresses each step:

~~~sql
SELECT quantity * unit_price AS gross_amount,
       quantity * unit_price * discount_percent / 100 AS discount_amount,
       quantity * unit_price
         - (quantity * unit_price * discount_percent / 100)
           AS payable_amount
FROM order_items;
~~~

This can be simplified:

~~~sql
SELECT quantity * unit_price
       * (1 - discount_percent / 100) AS payable_amount
FROM order_items;
~~~

Both approaches are conceptually equivalent when the columns are numeric and the discount rate represents a percentage. The first approach is easier to cross-check step by step; the second is more concise. In business SQL, **parentheses can make a statement easier to read even when operator precedence is already unambiguous**.

## 3. Practicing operator precedence in Oracle

You do not need to create a table to test operators. You can use the single-row dummy table `DUAL`:

~~~sql
SELECT 2 + 3 * 4 AS case_1,
       (2 + 3) * 4 AS case_2,
       20 / 5 * 2 AS case_3,
       20 / (5 * 2) AS case_4,
       100 - 20 - 5 AS case_5,
       100 - (20 - 5) AS case_6
FROM dual;
~~~

Expected results:

| Column | Expression | Result |
|---|---|---:|
| `CASE_1` | `2 + (3 * 4)` | 14 |
| `CASE_2` | `(2 + 3) * 4` | 20 |
| `CASE_3` | `(20 / 5) * 2` | 8 |
| `CASE_4` | `20 / (5 * 2)` | 2 |
| `CASE_5` | `(100 - 20) - 5` | 75 |
| `CASE_6` | `100 - (20 - 5)` | 85 |

You can replace literals with columns to verify the same rules on actual data:

~~~sql
SELECT order_id,
       quantity,
       unit_price,
       quantity * unit_price AS gross_amount,
       (quantity * unit_price) - discount_amount AS net_amount
FROM order_items;
~~~

### 3.1 Avoid hard-to-read shorthand expressions

Example:

~~~sql
SELECT base_amount * 1 - discount / 100 AS total
FROM invoices;
~~~

Readers have to guess whether `discount` is a monetary amount or a percentage. If it is a percentage rate, the formula likely needs:

~~~sql
SELECT base_amount * (1 - discount_percent / 100) AS total
FROM invoices;
~~~

If `discount` is a monetary amount:

~~~sql
SELECT base_amount - discount_amount AS total
FROM invoices;
~~~

Column names and parentheses should clearly reflect units and meaning. A syntactically valid expression can still be logically wrong in business terms if it mixes **percentages** with **monetary amounts**.

## 4. Division in Oracle: not automatically integer division

In Oracle, the `/` operator returns a numeric result. For example:

~~~sql
SELECT 5 / 2 AS quotient,
       10 / 4 AS another_quotient,
       1 / 3 AS repeating_fraction
FROM dual;
~~~

| Expression | Mathematical Result |
|---|---:|
| `5 / 2` | 2.5 |
| `10 / 4` | 2.5 |
| `1 / 3` | Approximately 0.333333... up to Oracle numeric precision |

Oracle does not automatically truncate the fractional part just because both operands look like integers. If you need an integer part, you must explicitly specify whether to **truncate toward zero** or **round down**.

### 4.1 TRUNC: truncate fractional digits toward zero

~~~sql
SELECT TRUNC(5 / 2) AS positive_trunc,
       TRUNC(-5 / 2) AS negative_trunc,
       TRUNC(10 / 3, 2) AS two_decimals
FROM dual;
~~~

The results are `2`, `-2`, and `3.33`, respectively. `TRUNC(n, 2)` truncates after two decimal places; it does not round the third digit. `TRUNC(-2.89)` yields `-2` because it truncates toward zero.

### 4.2 FLOOR: round down along the number line

~~~sql
SELECT FLOOR(5 / 2) AS positive_floor,
       FLOOR(-5 / 2) AS negative_floor
FROM dual;
~~~

The results are `2` and `-3`. For negative numbers, `FLOOR` moves to the greatest integer less than or equal to the value, which differs from `TRUNC`.

| Value | `TRUNC(value)` | `FLOOR(value)` | Explanation |
|---:|---:|---:|---|
| 2.9 | 2 | 2 | Same result for positive numbers |
| -2.9 | -2 | -3 | `TRUNC` moves toward 0; `FLOOR` moves toward negative infinity |
| 2.0 | 2 | 2 | Already an integer |

### 4.3 ROUND: round to the specified decimal place

~~~sql
SELECT ROUND(10 / 3, 2) AS rounded_2,
       ROUND(10 / 3, 0) AS rounded_integer,
       ROUND(125.456, 1) AS rounded_1
FROM dual;
~~~

The results are `3.33`, `3`, and `125.5`, respectively. `ROUND` rounds according to Oracle's rounding rules, unlike `TRUNC` which simply discards digits after the specified position.

| Function | Purpose | Example |
|---|---|---|
| `TRUNC(n, 2)` | Truncate to two decimal places | `3.333... → 3.33` |
| `ROUND(n, 2)` | Round to two decimal places | `3.335 → 3.34` |
| `FLOOR(n)` | Largest integer not exceeding n | `-2.1 → -3` |
| `CEIL(n)` | Smallest integer not less than n | `2.1 → 3` |

Do not use `FLOOR` instead of `TRUNC` when business data includes negative numbers, or `ROUND` when the requirement is truncation. Choose the function based on the business rule.

## 5. Division by zero: common errors and how to handle them

With standard `NUMBER` types, a denominator of 0 in division raises an error:

~~~sql
SELECT 10 / 0 AS result
FROM dual;
~~~

Oracle reports:

~~~text
ORA-01476: divisor is equal to zero
~~~

In a multi-row query, even a single row with a zero denominator can cause the entire SQL statement to fail if the division expression is evaluated for that row. Do not wait for the error to occur before handling it; determine the business meaning of a zero denominator up front.

### 5.1 NULLIF: turn a zero denominator into NULL

Common pattern:

~~~sql
SELECT numerator / NULLIF(denominator, 0) AS ratio
FROM metrics;
~~~

`NULLIF(a, b)` returns `NULL` if `a = b`; otherwise, it returns `a`. Therefore:

- If `denominator = 0`, the denominator becomes `NULL`.
- If `denominator` is non-zero, the division executes normally.
- If `denominator` is already `NULL`, the result remains `NULL`.

In SQL, arithmetic operations involving `NULL` evaluate to `NULL`. Thus, a row with a zero denominator no longer triggers a division-by-zero error:

~~~sql
SELECT 10 / NULLIF(0, 0) AS safe_result
FROM dual;
~~~

`SAFE_RESULT` is `NULL`. This is appropriate when an undefined ratio should be represented as an unavailable/undefined value.

### 5.2 CASE: explicitly define the result when the denominator is zero

If business rules require returning a label or another value:

~~~sql
SELECT CASE
         WHEN denominator = 0 THEN NULL
         ELSE numerator / denominator
       END AS ratio
FROM metrics;
~~~

Or if the convention sets the ratio to 0 when the denominator is 0:

~~~sql
SELECT CASE
         WHEN denominator = 0 THEN 0
         ELSE numerator / denominator
       END AS ratio
FROM metrics;
~~~

Oracle supports short-circuit evaluation for `CASE` expressions: the selected condition branch determines which result expression is evaluated. However, returning `0` is a **business decision**, not a universal mathematical rule. An undefined ratio and a ratio that is genuinely zero are two distinct states.

### 5.3 NVL/COALESCE do not prevent division by zero on their own

The following remains dangerous:

~~~sql
SELECT numerator / NVL(denominator, 0) AS ratio
FROM metrics;
~~~

If `denominator` is `NULL`, `NVL` replaces it with 0 and the division can raise `ORA-01476`. Similarly:

~~~sql
SELECT numerator / COALESCE(denominator, 0) AS ratio
FROM metrics;
~~~

is not safe. `NVL` and `COALESCE` handle `NULL`; they do not ensure the denominator is non-zero. If the goal is to avoid division by zero, use `NULLIF(denominator, 0)` or a `CASE` check for zero.

### 5.4 Do not rely on WHERE clause evaluation order to guard division

A misleading pattern:

~~~sql
SELECT numerator / denominator AS ratio
FROM metrics
WHERE denominator <> 0;
~~~

The author might assume Oracle always filters out rows with a zero denominator before evaluating the division. However, the optimizer can rewrite and reorder expression evaluation; you must not rely on `WHERE` evaluation order to guarantee an expression will not error.

Write self-protecting expressions:

~~~sql
SELECT numerator / NULLIF(denominator, 0) AS ratio
FROM metrics;
~~~

Or use `CASE`:

~~~sql
SELECT CASE
         WHEN denominator <> 0
         THEN numerator / denominator
       END AS ratio
FROM metrics;
~~~

Key takeaway: **the safety guard must reside inside the division expression itself**, not merely in a separate filter predicate.

## 6. Choosing business semantics for zero and NULL denominators

Not every case should be turned into 0. Determine what the denominator represents:

| Case | Possible Meaning | Representation to Consider |
|---|---|---|
| Denominator is 0 | No basis to compute a ratio | `NULL` or an "undefined" status |
| Denominator is `NULL` | Missing input data | `NULL`, or handle separately per business rule |
| Numerator is 0, denominator is positive | Ratio is genuinely zero | Return 0 |
| Both numerator and denominator are positive | Normal ratio | Divide and round according to rules |
| Negative denominator | Could be an adjustment/refund or invalid data | Clarify business rules before calculating |

For example, if `completed_count = 0` and `total_count = 0`, the completion rate cannot automatically be concluded as 0% or 100%. The system needs to define a status such as "no items to evaluate yet", or return `NULL` along with an explanatory label.

### 6.1 Returning both the ratio and its status

A reporting query can separate the numeric value and the status:

~~~sql
SELECT metric_id,
       numerator / NULLIF(denominator, 0) AS ratio,
       CASE
         WHEN denominator IS NULL THEN 'MISSING_DENOMINATOR'
         WHEN denominator = 0 THEN 'ZERO_DENOMINATOR'
         ELSE 'CALCULATED'
       END AS ratio_status
FROM metrics;
~~~

This preserves the distinction between missing data and a zero denominator. Simply using `NVL(ratio, 0)` in a report can collapse different conditions into the same number 0 and mislead readers.

### 6.2 COALESCE at the presentation layer

If the UI requires displaying a string when the ratio is undefined:

~~~sql
SELECT CASE
         WHEN denominator IS NULL THEN 'No data available'
         WHEN denominator = 0 THEN 'Undefined'
         ELSE TO_CHAR(
                ROUND(numerator / denominator * 100, 2),
                'FM999999990D00',
                'NLS_NUMERIC_CHARACTERS=.,'
              ) || '%'
       END AS ratio_display
FROM metrics;
~~~

This is an example of returning a string for presentation. In APIs with structured data contracts, it is usually better to return the **numeric/null value and a separate status**, letting the frontend format according to the user's locale. Avoid forcing everything into strings if downstream consumers still need to compare, sort, or perform further calculations.

## 7. NUMBER, BINARY_FLOAT, and BINARY_DOUBLE

Oracle supports multiple numeric data types. Choosing the right type affects precision, conversions, and division results.

| Type | Characteristics | Typical Use Cases |
|---|---|---|
| `NUMBER` | Decimal number with Oracle precision/scale; supports up to 38 significant digits | Money, quantities, business ratios requiring decimal control |
| `BINARY_FLOAT` | Single-precision binary floating-point number per IEEE 754 | Scientific/graphics calculations needing 32-bit floating point |
| `BINARY_DOUBLE` | Double-precision binary floating-point number per IEEE 754 | Floating-point computations needing 64-bit binary range/precision |

### 7.1 NUMBER division

~~~sql
SELECT 1 / 3 AS number_quotient,
       ROUND(1 / 3, 4) AS rounded_quotient
FROM dual;
~~~

The first result is a numeric value represented by Oracle with finite precision; the second is `0.3333`. For currency, values are typically stored and computed as `NUMBER(p,s)`, then rounded according to business rules at the designated step.

### 7.2 Floating-point types can yield different results from NUMBER

~~~sql
SELECT CAST(0.1 AS BINARY_DOUBLE)
       + CAST(0.2 AS BINARY_DOUBLE) AS binary_sum,
       CAST(0.1 AS NUMBER) + CAST(0.2 AS NUMBER) AS number_sum
FROM dual;
~~~

Binary floating-point numbers cannot exactly represent every finite decimal fraction. Consequently, adding `0.1 + 0.2` using binary floating-point types may display a value close to `0.3` without necessarily equaling the exact ideal decimal value. `NUMBER` is better suited for most monetary calculations.

### 7.3 Numeric precedence and implicit conversion

When an expression mixes numeric types, Oracle applies numeric precedence rules and necessary conversions. Numeric precedence order is generally:

`BINARY_DOUBLE` is higher than `BINARY_FLOAT`, and `BINARY_FLOAT` is higher than `NUMBER`.

If an expression includes a `BINARY_DOUBLE` operand, the result can be evaluated in that floating-point type. Thus, a single literal or column of a different type can change the result type of the entire expression.

Do not mix `NUMBER` with `BINARY_DOUBLE` just to "increase precision" in financial calculations; they are two different numeric representation models. Keep data types consistent, cast explicitly when needed, and verify the result type when troubleshooting.

### 7.4 Division by zero with NUMBER vs. floating-point types

With standard `NUMBER` expressions, dividing by 0 raises `ORA-01476`. `BINARY_FLOAT` and `BINARY_DOUBLE` follow IEEE 754 floating-point rules and can produce special values such as infinity or NaN in certain operations. Therefore, do not mix types and assume every division by zero behaves identically with an error.

In business SQL, zero denominators should still be handled explicitly using `NULLIF` or `CASE`, regardless of numeric type. Never use infinity/NaN values as an implicit way to encode business errors.

## 8. Precision, scale, and rounding in expressions

The `NUMBER(p,s)` type has:

- `p`: precision, the maximum number of significant digits.
- `s`: scale, the number of digits retained after the decimal point (a negative scale rounds to the left of the decimal point).

Example:

~~~sql
CREATE TABLE lab_numeric_values (
    amount        NUMBER(12,2),
    exchange_rate NUMBER(10,6)
);
~~~

`AMOUNT` has up to 12 significant digits with scale 2; `EXCHANGE_RATE` has scale 6. When assigning a value with more fractional digits than the scale allows, Oracle rounds according to the type definition; if the integer part causes precision to be exceeded, an error such as `ORA-01438: value larger than specified precision allowed for this column` can occur.

### 8.1 Round per line or after summing?

The two approaches can produce different results:

~~~sql
SELECT SUM(ROUND(line_amount * tax_rate, 2)) AS sum_rounded_lines,
       ROUND(SUM(line_amount * tax_rate), 2) AS rounded_total
FROM invoice_lines;
~~~

- `SUM(ROUND(..., 2))` rounds each line first and then sums.
- `ROUND(SUM(...), 2)` sums the unrounded values first and then rounds the total.

As a simple example, three tax lines of `0.005` each:

~~~sql
SELECT SUM(ROUND(0.005, 2)) AS round_each,
       ROUND(SUM(0.005), 2) AS round_after_sum
FROM (
    SELECT 1 AS n FROM dual
    UNION ALL SELECT 2 FROM dual
    UNION ALL SELECT 3 FROM dual
);
~~~

Under Oracle rounding rules, the illustrative results are `0.03` when rounding each line and `0.02` when rounding the total. Tax/accounting policies must specify the **unit of rounding**; do not arbitrarily place `ROUND` just because an expression looks cleaner.

### 8.2 Intentional result casting

~~~sql
SELECT CAST(
           ROUND(quantity * unit_price, 2)
           AS NUMBER(14,2)
       ) AS line_total
FROM order_items;
~~~

`ROUND` determines the rounding rule, while `CAST` specifies the desired result data type. Casting does not replace overflow checks; if a value exceeds the target precision, Oracle can still raise an error when storing or converting it.

## 9. Division in reporting: row-level ratios vs. aggregate ratios

A common business logic mistake is misplacing `SUM` relative to division.

Suppose table `sales_by_team` has `team_id`, `revenue`, and `target`:

~~~sql
SELECT team_id,
       revenue / NULLIF(target, 0) AS achievement_ratio
FROM sales_by_team;
~~~

This is the target achievement ratio for **each team**.

If you want the overall ratio across all teams:

~~~sql
SELECT SUM(revenue) / NULLIF(SUM(target), 0) AS total_achievement_ratio
FROM sales_by_team;
~~~

Do not assume that:

~~~sql
SELECT AVG(revenue / NULLIF(target, 0)) AS average_team_ratio
FROM sales_by_team;
~~~

equals `SUM(revenue) / SUM(target)`. The two metrics have different meanings:

| Formula | Meaning |
|---|---|
| `AVG(revenue / target)` | Average of individual team ratios, where each team carries equal weight in AVG (NULL rows are ignored) |
| `SUM(revenue) / SUM(target)` | Ratio of total revenue to total target; teams with larger targets contribute greater weight |
| `SUM(revenue / target)` | Sum of individual ratios; usually not a valid overall achievement metric |

Example:

| Team | Revenue | Target | Ratio |
|---|---:|---:|---:|
| A | 90 | 100 | 90% |
| B | 180 | 300 | 60% |

`AVG(90%, 60%) = 75%`, whereas the overall ratio is `270 / 400 = 67.5%`. Choose the formula based on the reporting question you want to answer.

### 9.1 NULL in aggregations

Oracle ignores `NULL` in many aggregate functions such as `SUM` and `AVG`. If `NULLIF` is used to turn a zero denominator into `NULL`:

~~~sql
SELECT AVG(numerator / NULLIF(denominator, 0)) AS avg_ratio,
       COUNT(*) AS input_rows,
       COUNT(numerator / NULLIF(denominator, 0)) AS calculated_rows
FROM metrics;
~~~

`INPUT_ROWS` counts all rows; `CALCULATED_ROWS` counts how many ratio expressions are non-`NULL`. Together, these two numbers tell readers how many rows actually participated in the average. Without reporting the skipped rows, an average metric might look valid even if many rows could not be computed.

## 10. Arithmetic expressions with NULL

In Oracle SQL, `NULL` represents an unknown or missing value. Arithmetic operations with `NULL` generally return `NULL`:

~~~sql
SELECT 10 + NULL AS add_null,
       10 - NULL AS subtract_null,
       10 * NULL AS multiply_null,
       10 / NULL AS divide_null
FROM dual;
~~~

All results are `NULL`. This does not mean Oracle treats `NULL` as 0.

### 10.1 NVL and COALESCE change calculation semantics

~~~sql
SELECT amount + NVL(discount, 0) AS amount_with_default_discount
FROM invoices;
~~~

Here, `NVL(discount, 0)` carries business meaning: a missing discount value is treated as zero discount. If the business rule treats `NULL` as "discount not yet determined", replacing it with 0 may be wrong.

`COALESCE` lets you pick the first non-`NULL` value:

~~~sql
SELECT amount
       - COALESCE(discount_amount, promotional_discount, 0)
           AS net_amount
FROM invoices;
~~~

This expression prioritizes `discount_amount`; if it is `NULL`, it falls back to `promotional_discount`; if both are `NULL`, it uses 0. You must confirm this priority order matches business rules; the function cannot know on its own which field is primary.

### 10.2 NULLIF differs from NVL

| Function | Behavior | Example |
|---|---|---|
| `NVL(x, 0)` | Replaces `NULL` with 0 | `NVL(NULL,0) = 0` |
| `COALESCE(x, y, 0)` | Returns the first non-`NULL` expression | `COALESCE(NULL,5,0) = 5` |
| `NULLIF(x, 0)` | Returns `NULL` when x equals 0; otherwise returns x | `NULLIF(0,0) = NULL` |

When guarding a denominator, `NULLIF(denominator, 0)` is the right pattern rather than `NVL(denominator, 0)`.

## 11. Data type conversion and NLS in division

Division should use **numeric operands**. If one side is a string, Oracle may perform an implicit conversion:

~~~sql
SELECT 10 / '2' AS result
FROM dual;
~~~

Oracle can convert the string `'2'` to the number 2. However, relying on implicit conversion makes the SQL statement dependent on input data and NLS conversion settings. For example:

~~~sql
SELECT 10 / '2,5' AS result
FROM dual;
~~~

The string `'2,5'` can be interpreted differently depending on `NLS_NUMERIC_CHARACTERS`; some environments raise `ORA-01722: invalid number`. Never use a string with ambiguous separators as a numeric operand.

### 11.1 Use numeric literals in SQL

Numeric literals in SQL are written with a decimal point:

~~~sql
SELECT 10 / 2.5 AS result
FROM dual;
~~~

This is a numeric literal, not a text string subject to the same parsing behavior as `'2,5'`. Display formatting of the result may be affected by NLS, but the numeric value of the literal itself is not a string parsed according to the user's locale.

### 11.2 If you must convert a string to a number

Specify the appropriate format model and NLS parameters explicitly:

~~~sql
SELECT TO_NUMBER(
           '1.234,50',
           '9G999D99',
           'NLS_NUMERIC_CHARACTERS='',.'''
       ) AS parsed_number
FROM dual;
~~~

This example specifies the period as the group separator and the comma as the decimal separator. Make sure to use the proper format model and SQL string quoting rules; in applications, binding a numeric value directly is usually safer than parsing a formatted string.

### 11.3 Java/JDBC: bind numbers using numeric types

Example:

~~~java
String sql = """
    SELECT amount / NULLIF(quantity, 0) AS unit_amount
    FROM order_totals
    WHERE order_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, orderId);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            java.math.BigDecimal unitAmount = rs.getBigDecimal("UNIT_AMOUNT");
        }
    }
}
~~~

This snippet assumes an existing `Connection connection` and variable `orderId`; `AMOUNT` and `QUANTITY` are numeric columns. Bind the ID with `setLong` and read the numeric result with `getBigDecimal` to preserve the decimal model appropriate for monetary operations. Do not use `setString` to pass a locale-formatted number and expect Oracle to always parse it the same way.

## 12. Arithmetic with datetimes and intervals

Beyond numbers, Oracle supports arithmetic operations involving dates and times:

- `DATE + NUMBER`: adds a number of days; the fractional part represents a fraction of a day.
- `DATE - DATE`: returns the difference in days, which can include a fractional part.
- For `TIMESTAMP`, adding or subtracting durations typically uses the appropriate `INTERVAL` type.

Example:

~~~sql
SELECT DATE '2026-11-14' + 1 AS next_day,
       DATE '2026-11-14' + 0.5 AS twelve_hours_later,
       DATE '2026-11-15' - DATE '2026-11-14' AS days_between
FROM dual;
~~~

The results represent the next day, 12 hours later, and a difference of 1 day, respectively. How the time portion of a `DATE` result displays still depends on session/client formatting; if clarity is needed, use `TO_CHAR` with an explicit format.

With timestamps:

~~~sql
SELECT TIMESTAMP '2026-11-14 09:00:00'
       + INTERVAL '90' MINUTE AS after_ninety_minutes
FROM dual;
~~~

Do not convert every timestamp to fractional days for addition or subtraction if business logic involves time zones, daylight saving time, or month-based intervals. Choose the `INTERVAL` and timestamp types that match the temporal semantics.

## 13. Arithmetic expressions in WHERE, UPDATE, and INSERT

### 13.1 WHERE: comparing by expression

~~~sql
SELECT order_id, quantity, unit_price
FROM order_items
WHERE quantity * unit_price > 500000;
~~~

Oracle evaluates the product to compare against the threshold. If a column contains `NULL`, the product expression can be `NULL`; the condition does not evaluate to TRUE, so that row is excluded. If missing quantities or prices should be treated as 0, make it explicit:

~~~sql
SELECT order_id
FROM order_items
WHERE NVL(quantity, 0) * NVL(unit_price, 0) > 500000;
~~~

This changes the logic: missing quantity or price is treated as 0. If missing data is an error that needs detection, check for it separately rather than silently substituting 0.

### 13.2 UPDATE: computing a new value

~~~sql
UPDATE inventory
SET available_qty = available_qty - :sold_qty
WHERE product_id = :product_id
  AND available_qty >= :sold_qty;
~~~

In this example, bind variables pass the sold quantity and product ID. Checking inventory right inside the DML statement prevents updating when stock is insufficient. The application should check the updated row count and handle the transaction accordingly. The subtraction expression does not replace constraints such as `CHECK (available_qty >= 0)`.

### 13.3 INSERT: expressions in VALUES

~~~sql
INSERT INTO order_totals (order_id, amount, tax_amount, total_amount)
VALUES (
    :order_id,
    :amount,
    :amount * :tax_rate,
    :amount + (:amount * :tax_rate)
);
~~~

Oracle computes the expressions based on the bind values and data types. If `tax_rate` is sent as a percentage 8 instead of a ratio 0.08, the result will be off by a factor of 100; bind names and data contracts must make units unambiguous.

## 14. Division in aggregate and analytic queries

### 14.1 Calculating ratios by group

~~~sql
SELECT department_id,
       SUM(completed_count) /
         NULLIF(SUM(total_count), 0) AS completion_ratio
FROM department_metrics
GROUP BY department_id
ORDER BY department_id;
~~~

Here, the denominator is calculated after aggregating by department. `NULLIF` handles the case where the sum of `total_count` is zero.

### 14.2 Calculating percentage share of total

~~~sql
SELECT department_id,
       revenue,
       revenue / NULLIF(SUM(revenue) OVER (), 0) * 100
           AS revenue_share_percent
FROM department_revenue;
~~~

`SUM(revenue) OVER ()` computes total revenue across the entire result set processed by the query; the division expression produces each row's share. If you need totals per region, add `PARTITION BY region_id`:

~~~sql
SELECT region_id,
       department_id,
       revenue,
       revenue /
         NULLIF(SUM(revenue) OVER (PARTITION BY region_id), 0)
         * 100 AS region_share_percent
FROM department_revenue;
~~~

Parentheses or clear formatting in the expression show that the ratio is `revenue / total` multiplied by 100. Without `NULLIF`, a region with zero total revenue could trigger a division-by-zero error.

## 15. Performance and readability of expressions

### 15.1 Repeated expressions can make SQL hard to maintain

~~~sql
SELECT quantity * unit_price AS gross_amount,
       quantity * unit_price - discount_amount AS net_amount,
       (quantity * unit_price - discount_amount) / NULLIF(quantity, 0)
           AS net_per_quantity
FROM order_items;
~~~

When an expression repeats multiple times, you can place it in a CTE:

~~~sql
WITH item_values AS (
    SELECT order_id,
           quantity,
           quantity * unit_price AS gross_amount,
           discount_amount
    FROM order_items
)
SELECT order_id,
       gross_amount,
       gross_amount - discount_amount AS net_amount,
       (gross_amount - discount_amount) / NULLIF(quantity, 0)
           AS net_per_quantity
FROM item_values;
~~~

A CTE separates calculation steps to improve readability. Do not assume a CTE is always materialized into a temporary table; the Oracle optimizer may inline or transform the query according to the execution plan.

### 15.2 Expressions on columns and indexes

The condition:

~~~sql
WHERE quantity * unit_price > 500000
~~~

can prevent straightforward use of standard single-column indexes on `QUANTITY` or `UNIT_PRICE` compared to filtering directly on a single column. If a workload repeatedly queries on a specific expression and performance evidence justifies it, you can evaluate a **function-based index**:

~~~sql
-- Design example, only create after evaluating the workload:
CREATE INDEX ix_order_items_line_value
ON order_items (quantity * unit_price);
~~~

This is not a recommendation to index every expression. Indexes add storage and DML overhead; the optimizer also weighs statistics, selectivity, and query predicates. Inspect the actual execution plan before deciding.

### 15.3 Keep data types clear at the application boundary

If data volumes are large and expressions are needed for filtering or aggregation in the database, let Oracle perform the calculations close to the data. If you are only formatting a fetched value for display, the application can handle formatting in the UI layer. Divide responsibilities based on:

- Does SQL need to filter, sort, or aggregate by the expression?
- Must the calculation rule be shared across multiple applications?
- Are data types and rounding consistent across systems?
- Do you need to preserve the exact number for further calculation, or only a display string?

## 16. Common errors and misconceptions

| Symptom / Error | Common Cause | Resolution |
|---|---|---|
| Calculation result differs from expectation | Wrong operator precedence or missing parentheses | Rewrite the expression step by step and add parentheses |
| `ORA-01476: divisor is equal to zero` | NUMBER denominator is 0 | Use `NULLIF` or `CASE` according to business semantics |
| Division returns decimals when integers were expected | Oracle `/` is numeric division, not integer division | Use `TRUNC` or `FLOOR` as intended |
| Negative numbers yield different results with FLOOR/TRUNC | The two functions handle negative numbers differently | Decide whether to truncate toward 0 or round down |
| `ORA-01722: invalid number` | Invalid string-to-number conversion or NLS mismatch | Bind numeric types or use `TO_NUMBER` with explicit format/NLS |
| Monetary results off by a few minor units | Inconsistent per-line vs. post-sum rounding; floating-point types | Use `NUMBER` and standardize the `ROUND` policy |
| Ratio is 0 even with no data | Using `NVL(ratio,0)` obscures NULL meaning | Return NULL ratio and a separate status when undefined |
| One row with a zero denominator fails the entire report | Unprotected direct division | Use `numerator / NULLIF(denominator,0)` |
| Filtering denominator != 0 still triggers division error | Relying on WHERE evaluation order | Place the safety guard inside the division expression itself |
| Average ratio does not match total ratio | Using `AVG(row_ratio)` instead of `SUM(num)/SUM(den)` | Choose the correct metric definition |
| Binary numbers show tiny precision errors | Binary floating point cannot represent all decimal fractions exactly | Use NUMBER for money and values requiring exact decimal representation |

## 17. Self-check exercises

The statements below can be run in SQL*Plus, SQLcl, or a compatible SQL tool. Use `DUAL` to test expressions first; you do not need to create tables when practicing operators.

### Exercise 1 — Predict operator precedence

Before running, calculate manually:

~~~sql
SELECT 8 + 4 * 3 AS a,
       (8 + 4) * 3 AS b,
       60 / 5 * 2 AS c,
       60 / (5 * 2) AS d,
       50 - 8 + 3 AS e,
       50 - (8 + 3) AS f
FROM dual;
~~~

Explain why `C` and `D` differ, and why `E` does not equal `F`.

### Exercise 2 — Distinguish division, truncation, and rounding

~~~sql
SELECT 17 / 4 AS exact_division,
       TRUNC(17 / 4) AS trunc_result,
       FLOOR(17 / 4) AS floor_result,
       ROUND(17 / 4, 2) AS round_result
FROM dual;
~~~

Next, change the numerator to `-17`. Write down the difference between `TRUNC` and `FLOOR` when the result is negative.

### Exercise 3 — Guarding division

~~~sql
SELECT 100 / NULLIF(5, 0) AS normal_ratio,
       100 / NULLIF(0, 0) AS zero_denominator_ratio,
       100 / NULLIF(NULL, 0) AS null_denominator_ratio
FROM dual;
~~~

Explain why the last two results are `NULL` and why they are not equivalent to a ratio that is genuinely zero.

### Exercise 4 — Choosing the result when the denominator is zero

~~~sql
SELECT CASE
         WHEN 0 = 0 THEN 'NOT_DEFINED'
         ELSE TO_CHAR(100 / 0)
       END AS ratio_status
FROM dual;
~~~

The goal is to recognize how `CASE` selects a branch; afterward, rewrite the example using real columns and `NULLIF`. Do not run unprotected division on data containing zero denominators.

### Exercise 5 — Average of ratios or ratio of totals?

~~~sql
WITH teams AS (
    SELECT 90 AS revenue, 100 AS target FROM dual
    UNION ALL
    SELECT 180, 300 FROM dual
)
SELECT AVG(revenue / target) AS average_team_ratio,
       SUM(revenue) / SUM(target) AS total_ratio
FROM teams;
~~~

Predict both results and explain which formula fits reporting "what percentage does the average team achieve" versus "what percentage of the total target does total revenue achieve".

### Exercise 6 — NULL in expressions

~~~sql
SELECT 10 + NULL AS direct_result,
       10 + NVL(NULL, 0) AS with_nvl,
       10 + COALESCE(NULL, 2, 0) AS with_coalesce
FROM dual;
~~~

Explain why `NVL` and `COALESCE` change the result, and under what business conditions replacing `NULL` with 0 is valid.

### Exercise 7 — NUMBER vs. floating-point types

~~~sql
SELECT CAST(0.1 AS NUMBER) + CAST(0.2 AS NUMBER) AS decimal_sum,
       CAST(0.1 AS BINARY_DOUBLE)
         + CAST(0.2 AS BINARY_DOUBLE) AS binary_sum
FROM dual;
~~~

Compare the numeric types, explain why binary floating-point numbers may not exactly match a decimal fraction, and state why `NUMBER` should be used for money.

### Exercise 8 — Write a line-amount formula

An order line has:

~~~text
quantity = 3
unit_price = 125000
discount_percent = 10
~~~

Write SQL to calculate:

1. Gross amount before discount.
2. Discount amount.
3. Net amount after discount.
4. Net amount after discount rounded to two decimal places.

Use parentheses so readers can clearly see the order of operations, and explain the unit of `discount_percent`.

### Exercise 9 — Design a ratio with status

A table has `completed_count` and `total_count`. Write a query that returns:

- `completion_ratio` using `NULLIF` to avoid division by zero.
- `ratio_status` with three states: `MISSING_TOTAL`, `NO_TARGET`, `CALCULATED`.

Explain how to distinguish `total_count IS NULL` from `total_count = 0`.

## 18. Key takeaways for writing arithmetic expressions

| Topic | Practical Rule |
|---|---|
| Precedence | Multiplication/division before addition/subtraction; equal-precedence operators evaluate left to right |
| Grouping | Use parentheses when business meaning requires explicit grouping |
| Division | `/` returns a numeric result and does not automatically truncate to an integer |
| Division by zero | For NUMBER, use `NULLIF` or `CASE` to guard the denominator |
| NULL | Do not assume `NULL` is 0; only replace via NVL/COALESCE when a business rule dictates it |
| Rounding | Choose `ROUND`, `TRUNC`, `FLOOR`, or `CEIL` according to the goal, especially with negative numbers |
| Numeric types | Prefer `NUMBER` for currency and decimal calculations needing control |
| Conversions | Bind proper types; avoid parsing numeric strings dependent on NLS |
| Reporting ratios | Distinguish average of row-level ratios from ratio of totals |
| Performance | Inspect the execution plan and workload before creating expression-based indexes |

A good arithmetic expression is **mathematically accurate**, **aligned with business semantics**, and **safe against edge-case data**. Clearly express operation grouping, decide beforehand how to handle zero or NULL denominators, pick the appropriate numeric data type, and apply rounding rules at the right step. Doing so ensures SQL produces consistent results across different sessions, tools, and applications.
