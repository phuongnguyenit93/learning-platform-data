# COUNT(*), COUNT(column), SUM, AVG, MIN, and MAX in Oracle Database

Aggregate functions transform multiple rows of data into one or more summary results. In Oracle Database, six commonly used calculations are:

- **`COUNT(*)`**: counts the number of rows.
- **`COUNT(expression)`**: counts the number of rows where the expression is not `NULL`.
- **`SUM(expression)`**: calculates the sum of non-NULL numeric values.
- **`AVG(expression)`**: calculates the average of non-NULL numeric values.
- **`MIN(expression)`**: retrieves the minimum value according to the data type's comparison rules.
- **`MAX(expression)`**: retrieves the maximum value according to the data type's comparison rules.

The most important aspect when using these functions is understanding **how NULL is handled**. For example, `COUNT(*)` still counts a row even if some columns in that row are NULL; `COUNT(amount)` ignores rows where `AMOUNT=NULL`; and `AVG(amount)` divides only by the number of amount values actually present. Without understanding this clearly, count, total amount, and average reports may diverge from business semantics.

This lesson explains how to use each function, combine them with `GROUP BY` and `HAVING`, perform conditional counting, handle empty result sets, avoid row-duplication scenarios caused by joins, and interpret results in Oracle reports.

## 1. What is an aggregate function?

### 1.1. From multiple rows to one result

Suppose a sales table has the following values:

```text
SALE_ID    AMOUNT
-------    ------
1          1000
2          1500
3          1000
4          NULL
5          3000
```

Aggregate functions return summary information:

| Expression | Result | Meaning |
| --- | ---: | --- |
| `COUNT(*)` | 5 | There are 5 rows |
| `COUNT(amount)` | 4 | There are 4 rows with a non-NULL amount |
| `SUM(amount)` | 6500 | Sum of 1000 + 1500 + 1000 + 3000 |
| `AVG(amount)` | 1625 | Sum of 6500 divided by the 4 present values |
| `MIN(amount)` | 1000 | Minimum value |
| `MAX(amount)` | 3000 | Maximum value |

`COUNT(*)` returns the number of rows in the input set. The remaining functions in the example ignore `NULL` in the evaluated expression.

### 1.2. Aggregate functions do not necessarily return one row per input row

Without `GROUP BY`, an aggregate query typically returns **one result row** for the entire input set:

```sql
SELECT COUNT(*) AS row_count,
       SUM(amount) AS total_amount,
       AVG(amount) AS average_amount
FROM   sales;
```

If `GROUP BY` is added, Oracle computes the result separately for each group:

```sql
SELECT region,
       COUNT(*) AS sale_count,
       SUM(amount) AS total_amount
FROM   sales
GROUP  BY region;
```

The following example returns one row for each region that has at least one row in the input set. `NULL` values in the `REGION` column also form their own separate group if such data exists.

### 1.3. Distinguishing aggregate functions from row-level functions

A row-level function (scalar function) takes input from a single row and returns a result for that row, such as `UPPER(name)` or `ROUND(amount, 2)`. An aggregate function takes multiple rows and returns a single result for the entire set or for each group.

You can use a scalar function inside an aggregate:

```sql
SELECT SUM(ROUND(amount, 2)) AS total_rounded
FROM   sales;
```

Here `ROUND` is applied to each amount value before `SUM` aggregates them. The order in which functions are applied can change the result; choose it according to the business meaning.

## 2. Sample data for practice

The following examples use the `DEMO_SALES` table. Create the table in a test schema:

```sql
CREATE TABLE demo_sales (
    sale_id     NUMBER(10) PRIMARY KEY,
    region      VARCHAR2(30),
    salesperson VARCHAR2(50),
    amount      NUMBER(12,2),
    status      VARCHAR2(20) NOT NULL,
    sold_at     DATE NOT NULL
);
```

Insert data:

```sql
INSERT INTO demo_sales VALUES (
    1, 'NORTH', 'An', 1000,
    'PAID', DATE '2026-11-01'
);

INSERT INTO demo_sales VALUES (
    2, 'NORTH', 'An', 1500,
    'PAID', DATE '2026-11-02'
);

INSERT INTO demo_sales VALUES (
    3, 'NORTH', 'Binh', 1000,
    'PENDING', DATE '2026-11-03'
);

INSERT INTO demo_sales VALUES (
    4, 'SOUTH', 'Chi', 2000,
    'PAID', DATE '2026-11-04'
);

INSERT INTO demo_sales VALUES (
    5, 'SOUTH', 'Chi', NULL,
    'PENDING', DATE '2026-11-05'
);

INSERT INTO demo_sales VALUES (
    6, 'SOUTH', 'Dung', 3000,
    'PAID', DATE '2026-11-06'
);

INSERT INTO demo_sales VALUES (
    7, 'EAST', 'An', NULL,
    'CANCELLED', DATE '2026-11-07'
);

INSERT INTO demo_sales VALUES (
    8, 'EAST', 'Binh', 500,
    'PAID', DATE '2026-11-08'
);

INSERT INTO demo_sales VALUES (
    9, 'EAST', 'Binh', 500,
    'PAID', DATE '2026-11-09'
);

INSERT INTO demo_sales VALUES (
    10, NULL, 'Ema', 700,
    'PAID', DATE '2026-11-10'
);

COMMIT;
```

The table has 10 rows; two rows have `AMOUNT=NULL`; the value 500 appears twice. This dataset is intentionally structured to show the difference between counting rows, counting non-NULL values, and counting distinct values.

| SALE_ID | REGION | SALESPERSON | AMOUNT | STATUS |
| ---: | --- | --- | ---: | --- |
| 1 | NORTH | An | 1,000 | PAID |
| 2 | NORTH | An | 1,500 | PAID |
| 3 | NORTH | Binh | 1,000 | PENDING |
| 4 | SOUTH | Chi | 2,000 | PAID |
| 5 | SOUTH | Chi | NULL | PENDING |
| 6 | SOUTH | Dung | 3,000 | PAID |
| 7 | EAST | An | NULL | CANCELLED |
| 8 | EAST | Binh | 500 | PAID |
| 9 | EAST | Binh | 500 | PAID |
| 10 | NULL | Ema | 700 | PAID |

## 3. COUNT(*): counting rows

### 3.1. Syntax and examples

```sql
SELECT COUNT(*) AS total_sales
FROM   demo_sales;
```

Result:

```text
TOTAL_SALES
-----------
10
```

`COUNT(*)` counts **every row** in the result set after applying `FROM`, `JOIN`, and `WHERE` conditions. It does not check whether individual columns are NULL.

Example:

```sql
SELECT COUNT(*) AS north_sales
FROM   demo_sales
WHERE  region = 'NORTH';
```

The result is **3** because there are three rows belonging to NORTH.

### 3.2. COUNT(*) still counts rows with NULL columns

```sql
SELECT COUNT(*) AS total_rows,
       COUNT(amount) AS rows_with_amount
FROM   demo_sales;
```

Result:

| TOTAL_ROWS | ROWS_WITH_AMOUNT |
| ---: | ---: |
| 10 | 8 |

The two rows with ID 5 and 7 have a NULL amount, but they are still existing rows, so `COUNT(*)` includes both.

Here is the question distinction to make:

- "How many transactions are there?" → usually use `COUNT(*)`.
- "How many transactions have an amount value?" → use `COUNT(amount)`.

### 3.3. COUNT(1) and COUNT(*)

In Oracle, `COUNT(1)` counts rows because the constant expression 1 is never NULL. In terms of result semantics, it is equivalent to `COUNT(*)` in ordinary queries:

```sql
SELECT COUNT(*) AS count_star,
       COUNT(1) AS count_one
FROM   demo_sales;
```

Both results equal 10. `COUNT(1)` is not a reliable performance optimization trick compared to `COUNT(*)`. When you want to count rows, use `COUNT(*)` because it expresses the intent clearly and does not mislead readers into thinking a specific column is being counted.

### 3.4. COUNT(*) after JOIN counts rows of the JOIN result

If a customer has three orders, when you join the customers table with the orders table, that customer appears in three rows in the result set. `COUNT(*)` then counts **three joined rows**, not a single unique customer.

General example:

```sql
SELECT COUNT(*) AS joined_rows
FROM   customers c
JOIN   orders o
       ON o.customer_id = c.customer_id;
```

If the goal is to count customers who have at least one order, you can use:

```sql
SELECT COUNT(DISTINCT c.customer_id) AS customers_with_orders
FROM   customers c
JOIN   orders o
       ON o.customer_id = c.customer_id;
```

Or use `EXISTS` to express the intent of checking existence. Always identify **the unit to count**: result rows, orders, customers, or another business entity.

## 4. COUNT(expression): counting non-NULL expressions

### 4.1. Syntax

```sql
COUNT(expression)
```

This function counts the number of rows where `expression` evaluates to a **non-NULL** value. The expression can be a column, a calculation, or `CASE`.

Example:

```sql
SELECT COUNT(amount) AS known_amount_count,
       COUNT(region) AS known_region_count,
       COUNT(salesperson) AS known_salesperson_count
FROM   demo_sales;
```

Based on the sample data:

| Expression | Result | Why |
| --- | ---: | --- |
| `COUNT(amount)` | 8 | Two rows have a NULL amount |
| `COUNT(region)` | 9 | One row has a NULL region |
| `COUNT(salesperson)` | 10 | All ten rows have a salesperson |

### 4.2. COUNT(expression) does not count non-zero numbers only

Suppose the `AMOUNT` column has the values 0, 100, and NULL:

- `COUNT(amount)` counts both 0 and 100, returning 2.
- `COUNT(amount)` skips NULL, not 0.

If the business requirement is to count amounts greater than 0, you must add a condition:

```sql
SELECT COUNT(*) AS positive_amount_count
FROM   demo_sales
WHERE  amount > 0;
```

Do not use `COUNT(amount)` as a substitute for checking positive/negative/zero values.

### 4.3. COUNT on an expression

```sql
SELECT COUNT(amount * 2) AS count_calculated_amount
FROM   demo_sales;
```

If `AMOUNT` is NULL, the multiplication also returns NULL, so that row is not counted. If the expression is non-NULL for every row, `COUNT(expression)` can equal `COUNT(*)`.

A conditional example:

```sql
SELECT COUNT(
         CASE
           WHEN status = 'PAID' THEN 1
         END
       ) AS paid_sales
FROM   demo_sales;
```

`CASE` returns 1 for PAID transactions and defaults to NULL for the remaining statuses. `COUNT` only counts the non-NULL 1 values.

**Do not write `ELSE 0` in this conditional COUNT pattern if the goal is to count PAID rows.** Zero is also not NULL, so `COUNT(CASE ... ELSE 0 END)` will count non-PAID rows as well.

### 4.4. COUNT(DISTINCT expression)

`DISTINCT` instructs Oracle to count only distinct values:

```sql
SELECT COUNT(amount) AS non_null_amount_rows,
       COUNT(DISTINCT amount) AS distinct_amounts
FROM   demo_sales;
```

Result:

| NON_NULL_AMOUNT_ROWS | DISTINCT_AMOUNTS |
| ---: | ---: |
| 8 | 6 |

There are eight rows with an amount, but only six distinct amount values: 500, 700, 1000, 1500, 2000, and 3000. The two 500 values at IDs 8 and 9 are counted only once in `COUNT(DISTINCT amount)`.

`COUNT(DISTINCT expression)` also ignores NULL. In the sample table, the two NULL amounts do not form a distinct value to be counted.

### 4.5. COUNT(DISTINCT) differs from counting unique rows

`COUNT(DISTINCT amount)` counts **distinct amount values**, not unique transactions. Two different transactions that both have an amount of 500 still contribute one value to the distinct result.

If you want to count transactions, use an appropriate primary key or `COUNT(*)` over the filtered transaction set. Do not substitute `COUNT(DISTINCT amount)` just because the data contains repeated values.

## 5. SUM: calculating the sum of numeric values

### 5.1. Syntax and example

```sql
SELECT SUM(amount) AS total_amount
FROM   demo_sales;
```

Based on the sample table, the total is:

```text
TOTAL_AMOUNT
------------
10200
```

Oracle adds the non-NULL values. The two rows with `AMOUNT=NULL` do not participate in the sum; they are not automatically treated as 0 in the calculation.

### 5.2. SUM skips NULL, but does not skip 0

Suppose a dataset has `AMOUNT` values of 10, 0, and NULL:

- The sum is 10.
- The number of values counted by `COUNT(amount)` is 2.
- The number of rows counted by `COUNT(*)` is 3.

NULL represents no provided/known value; 0 is an actual numeric value. Do not blindly replace every NULL with 0 if doing so changes the meaning of the data.

### 5.3. SUM(DISTINCT expression)

Oracle supports:

```sql
SELECT SUM(amount) AS sum_all_rows,
       SUM(DISTINCT amount) AS sum_distinct_values
FROM   demo_sales;
```

With the sample table:

- `SUM(amount)` = **10200**.
- `SUM(DISTINCT amount)` = **8700** (500 + 700 + 1000 + 1500 + 2000 + 3000 = 8700).

These are two different questions. Total revenue typically must sum every transaction, including two transactions with the same amount. `SUM(DISTINCT amount)` drops one occurrence of the repeated 500 value and therefore is no longer the total revenue across rows.

Only use `DISTINCT` when the business truly requires summing **unique value levels**, not to patch row duplication caused by a JOIN.

### 5.4. Conditional sum

You can use `CASE` inside `SUM`:

```sql
SELECT SUM(
         CASE
           WHEN status = 'PAID' THEN amount
           ELSE 0
         END
       ) AS paid_amount
FROM   demo_sales;
```

The result is **9200**. Only PAID rows contribute their amount; other statuses contribute 0. If a PAID row has a NULL amount, that value is still ignored by SUM.

Another approach is filtering beforehand:

```sql
SELECT SUM(amount) AS paid_amount
FROM   demo_sales
WHERE  status = 'PAID';
```

The result is the same when you only need a single total for PAID rows. `CASE` inside an aggregate is especially useful when you want to compute **multiple conditional metrics in a single grouping pass**.

### 5.5. SUM with negative numbers and decimals

`SUM` does not require all values to be positive. If the data contains refunds or adjustment entries, negative numbers can reduce the total:

```sql
SELECT SUM(amount) AS net_amount
FROM   account_transactions;
```

For currency, `NUMBER(p,s)` with appropriate precision/scale is commonly used to preserve decimal arithmetic rules. You should not convert currency to `BINARY_FLOAT`/`BINARY_DOUBLE` just to save bytes if the business requires exact decimal results.

### 5.6. SUM and return data type

`SUM` accepts a numeric expression. The return data type depends on the argument type according to Oracle rules. When using `NUMBER`, pay attention to precision and potential range overflow in large calculations; when using binary floating-point types, results may be subject to representation rounding errors.

If totals are passed to an application, preserve appropriate numeric type mapping and avoid automatically converting to a programming language's floating-point type when monetary precision is required.

## 6. AVG: calculating the arithmetic mean

### 6.1. Syntax and example

```sql
SELECT AVG(amount) AS average_amount
FROM   demo_sales;
```

With the sample data:

- Sum of non-NULL amounts: 10200.
- Number of non-NULL amount values: 8.
- Average: 10200 / 8 = **1275**.

`AVG(amount)` performs the calculation over non-NULL values. The denominator is not the total row count when NULLs exist.

### 6.2. AVG differs from SUM divided by COUNT(*) when NULLs are present

The calculation matching aggregate semantics:

```sql
SELECT AVG(amount) AS average_amount,
       SUM(amount) / COUNT(*) AS wrong_if_nulls
FROM   demo_sales;
```

With the sample table:

- `AVG(amount)` = 1275.
- `SUM(amount) / COUNT(*)` = 1020.

The second division uses 10 rows as the denominator, even though only 8 rows have an amount value. If you want to compute the average of present values manually, the corresponding denominator is `COUNT(amount)`:

```sql
SELECT SUM(amount) / COUNT(amount) AS calculated_average,
       AVG(amount) AS built_in_average
FROM   demo_sales;
```

Both results are equal for the same expression and row set, provided the denominator is non-zero. Generally, prefer `AVG` because it directly expresses intent and avoids writing the wrong denominator.

### 6.3. AVG(DISTINCT expression)

```sql
SELECT AVG(amount) AS average_all_rows,
       AVG(DISTINCT amount) AS average_distinct_amounts
FROM   demo_sales;
```

With the sample data:

- `AVG(amount)` = **1275**.
- `AVG(DISTINCT amount)` = **1450** (8700 / 6).

The distinct average answers "the average of the different amount levels," not "the average amount per transaction." The two 500 transactions have a weight of two in `AVG(amount)`, but only one in `AVG(DISTINCT amount)`.

### 6.4. Rounding AVG results

`AVG` can return many decimal places:

```sql
SELECT ROUND(AVG(amount), 2) AS average_amount_2dp
FROM   demo_sales;
```

`ROUND` only rounds the result for display purposes or defined calculation rules. You should not round each row before computing the average if the business requires the average of the original values; the two approaches can differ.

### 6.5. Conditional AVG

```sql
SELECT AVG(
         CASE
           WHEN status = 'PAID' THEN amount
         END
       ) AS average_paid_amount
FROM   demo_sales;
```

Non-PAID rows produce NULL from CASE and do not participate in AVG. PAID rows with a NULL amount are also excluded. This is a useful way to compute multiple averages by status in a single grouped query.

### 6.6. Weighted average

`AVG(amount)` computes a simple arithmetic mean where every non-NULL value has equal weight. If each observation has a weight, the general formula is:

\[
\text{Weighted average} =
\frac{\sum(value \times weight)}{\sum(weight)}
\]

Example when both `VALUE` and `WEIGHT` must be present:

```sql
SELECT SUM(value * weight) / NULLIF(SUM(weight), 0)
         AS weighted_average
FROM   demo_measurements
WHERE  value IS NOT NULL
AND    weight IS NOT NULL;
```

`NULLIF(SUM(weight), 0)` returns NULL if the sum of weights is 0, preventing division by zero. You also need to define rules for negative weights, zero weights, and missing data; do not apply this formula without agreeing on the business semantics.

## 7. MIN and MAX: minimum and maximum values

### 7.1. Syntax

```sql
SELECT MIN(amount) AS minimum_amount,
       MAX(amount) AS maximum_amount
FROM   demo_sales;
```

Based on the sample table:

| MINIMUM_AMOUNT | MAXIMUM_AMOUNT |
| ---: | ---: |
| 500 | 3000 |

`MIN` retrieves the smallest value; `MAX` retrieves the largest value according to the data type's comparison rules. Both ignore NULL.

### 7.2. MIN/MAX apply to more than just numbers

Oracle can use `MIN`/`MAX` on data types with appropriate comparison ordering, such as:

- `NUMBER`: smallest/largest number.
- `DATE`: earliest/latest point in time.
- `TIMESTAMP`: earliest/latest point in time.
- Character types: smallest/largest value according to comparison/collation rules.

Example finding the first and last transaction dates:

```sql
SELECT MIN(sold_at) AS first_sale_date,
       MAX(sold_at) AS last_sale_date
FROM   demo_sales;
```

If the column is `DATE`, values can contain hours, minutes, and seconds. Do not rely solely on a date-only display format and conclude that two records occurred at the exact same time.

### 7.3. MIN/MAX on strings does not mean "shortest/longest"

Example:

```sql
SELECT MIN(region) AS first_region,
       MAX(region) AS last_region
FROM   demo_sales;
```

The result is based on string comparison order, not character length or application-defined business order. Collation, data type, and comparison settings can affect the result.

If you want the name with the shortest length, that is a different problem that can combine `LENGTH` with an appropriate query; `MIN(name)` does not automatically pick the shortest string.

### 7.4. MIN/MAX and NULL

With a column containing NULL:

```sql
SELECT MIN(amount),
       MAX(amount),
       COUNT(amount)
FROM   demo_sales;
```

Both MIN and MAX ignore NULL values and return results based on the remaining non-NULL values. If all input expression values are NULL or the input set has no rows, MIN/MAX return NULL.

If a report needs to distinguish "no rows" from "rows exist but every amount is NULL," combine `COUNT(*)` and `COUNT(amount)`.

### 7.5. MIN/MAX do not return the entire corresponding row

The query:

```sql
SELECT MAX(amount)
FROM   demo_sales;
```

only returns **the largest amount value**, not automatically the `SALE_ID` or `SALESPERSON` of the transaction with that value.

To retrieve the row with the largest amount, you can use a subquery:

```sql
SELECT sale_id, salesperson, amount
FROM   demo_sales
WHERE  amount = (
         SELECT MAX(amount)
         FROM   demo_sales
       );
```

If multiple rows tie for the maximum amount, the query returns all tied rows. If exactly one row is needed, you must define a tie-breaking rule, such as ordering by amount descending then sale_id ascending and using an appropriate top-N/row-limiting mechanism.

## 8. NULL and empty result sets

### 8.1. General rules

For basic aggregates:

- `COUNT(*)` counts rows and does not exclude a row because a column is NULL.
- `COUNT(expression)` excludes rows where expression is NULL.
- `SUM`, `AVG`, `MIN`, `MAX` ignore NULL in expression.

Example:

```sql
SELECT COUNT(*) AS row_count,
       COUNT(amount) AS known_amount_count,
       SUM(amount) AS total_amount,
       AVG(amount) AS average_amount,
       MIN(amount) AS min_amount,
       MAX(amount) AS max_amount
FROM   demo_sales;
```

Sample result:

| ROW_COUNT | KNOWN_AMOUNT_COUNT | TOTAL_AMOUNT | AVERAGE_AMOUNT | MIN_AMOUNT | MAX_AMOUNT |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 8 | 10200 | 1275 | 500 | 3000 |

### 8.2. Input set with no rows

Run:

```sql
SELECT COUNT(*) AS row_count,
       COUNT(amount) AS amount_count,
       SUM(amount) AS total_amount,
       AVG(amount) AS average_amount,
       MIN(amount) AS min_amount,
       MAX(amount) AS max_amount
FROM   demo_sales
WHERE  1 = 0;
```

The result is still **one summary row**:

| ROW_COUNT | AMOUNT_COUNT | TOTAL_AMOUNT | AVERAGE_AMOUNT | MIN_AMOUNT | MAX_AMOUNT |
| ---: | ---: | --- | --- | --- | --- |
| 0 | 0 | NULL | NULL | NULL | NULL |

`COUNT` returns 0; the remaining aggregates return NULL because there are no values to compute. This is a distinction that needs handling in APIs/reports.

### 8.3. Rows exist, but all values are NULL

Suppose there are two transactions, both with NULL amounts. Result:

- `COUNT(*)` = 2.
- `COUNT(amount)` = 0.
- `SUM(amount)` = NULL.
- `AVG(amount)` = NULL.
- `MIN(amount)` = NULL.
- `MAX(amount)` = NULL.

Therefore, a `SUM=NULL` result can mean either that the input set is empty **or** that rows exist but none have a non-NULL amount value. Combining the counts helps distinguish these two situations.

### 8.4. Should a NULL SUM be replaced with 0?

You can use:

```sql
SELECT NVL(SUM(amount), 0) AS total_amount
FROM   demo_sales
WHERE  status = 'UNKNOWN_STATUS';
```

The result displays 0 instead of NULL. However, this changes how the result is represented: "no values to aggregate" is turned into "total equals 0."

Only use `NVL(SUM(...), 0)` if reporting rules treat those two states as equivalent. If you need to distinguish them, keep NULL and display an appropriate message at the application layer.

### 8.5. NULL in GROUP BY

Oracle groups rows with `REGION=NULL` into a single group:

```sql
SELECT region,
       COUNT(*) AS sale_count,
       COUNT(amount) AS amount_count,
       SUM(amount) AS total_amount
FROM   demo_sales
GROUP  BY region
ORDER  BY region NULLS LAST;
```

The result includes a NULL region group containing sale ID 10. In that group, `COUNT(*)` is 1 and `COUNT(amount)` is also 1.

If multiple rows have a NULL region, they belong to the same group. `GROUP BY` does not eliminate NULL like a `WHERE region = NULL` condition would; to filter the NULL group, use `HAVING region IS NULL` or filter in WHERE before grouping.

## 9. GROUP BY: computing aggregates per group

### 9.1. Basic syntax

```sql
SELECT group_column,
       aggregate_function(...)
FROM   table_name
WHERE  row_condition
GROUP  BY group_column
ORDER  BY group_column;
```

Example totaling revenue by region:

```sql
SELECT region,
       COUNT(*) AS sale_count,
       COUNT(amount) AS amount_count,
       SUM(amount) AS total_amount,
       AVG(amount) AS average_amount,
       MIN(amount) AS min_amount,
       MAX(amount) AS max_amount
FROM   demo_sales
GROUP  BY region
ORDER  BY region NULLS LAST;
```

Result based on the sample data:

| REGION | SALE_COUNT | AMOUNT_COUNT | TOTAL_AMOUNT | AVERAGE_AMOUNT | MIN_AMOUNT | MAX_AMOUNT |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
In the sample table, there are **three** EAST transactions (IDs 7, 8, 9). Two rows have non-NULL amounts of 500 and 500; sum is 1000, average is 500, min is 500, max is 500.

| REGION | SALE_COUNT | AMOUNT_COUNT | TOTAL_AMOUNT | AVERAGE_AMOUNT | MIN_AMOUNT | MAX_AMOUNT |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| EAST | 3 | 2 | 1000 | 500 | 500 | 500 |
| NORTH | 3 | 3 | 3500 | 1166.67 | 1000 | 1500 |
| SOUTH | 3 | 2 | 5000 | 2500 | 2000 | 3000 |
| NULL | 1 | 1 | 700 | 700 | 700 | 700 |

Each row represents a region group, and the aggregate functions are evaluated independently within that group.

### 9.2. Multiple GROUP BY columns

You can group by multiple dimensions:

```sql
SELECT region,
       status,
       COUNT(*) AS sale_count,
       SUM(amount) AS total_amount
FROM   demo_sales
GROUP  BY region, status
ORDER  BY region NULLS LAST, status;
```

A group is defined by the **combination of values** across all columns in `GROUP BY`. For example, `(NORTH, PAID)` is distinct from `(NORTH, PENDING)`.

If you want statistics by region and salesperson, replace `status` with `salesperson` or add columns matching the business question. More grouping columns generally produce more, smaller groups.

### 9.3. SELECT with GROUP BY

In a query with `GROUP BY`, expressions in `SELECT` normally must be:

- An expression used in `GROUP BY`; or
- An aggregate function applied to data in the group; or
- An expression validly constructed from grouping/aggregate expressions according to Oracle rules.

Incorrect example:

```sql
SELECT region,
       salesperson,
       SUM(amount)
FROM   demo_sales
GROUP  BY region;
```

`SALESPERSON` is neither grouped nor aggregated, so Oracle does not know which salesperson's name to pick for a region group that has multiple salespeople.

How to fix depends on the goal:

```sql
SELECT region,
       salesperson,
       SUM(amount)
FROM   demo_sales
GROUP  BY region, salesperson;
```

or if you only need totals by region, remove `SALESPERSON` from SELECT.

### 9.4. GROUP BY does not automatically sort results

Even if you observe results often coming back in some order, **never rely on a default order from GROUP BY**. For a deterministic order, use `ORDER BY`:

```sql
SELECT region, SUM(amount) AS total_amount
FROM   demo_sales
GROUP  BY region
ORDER  BY total_amount DESC NULLS LAST;
```

Presentation order is a separate requirement, not a guaranteed property of grouping.

## 10. HAVING: filtering groups after aggregation

### 10.1. WHERE and HAVING are different

- **`WHERE`** filters input rows **before grouping**.
- **`HAVING`** filters groups **after GROUP BY and aggregation**.

Example retrieving regions with a total amount of at least 3000:

```sql
SELECT region,
       SUM(amount) AS total_amount
FROM   demo_sales
GROUP  BY region
HAVING SUM(amount) >= 3000
ORDER  BY total_amount DESC;
```

Based on the sample table, NORTH has 3500 and SOUTH has 5000; both satisfy the condition. EAST (1000) and the NULL group (700) are excluded.

### 10.2. Filter rows first, filter groups second

Requirement: count only PAID transactions, then keep only regions with a total PAID amount over 3000:

```sql
SELECT region,
       COUNT(*) AS paid_count,
       SUM(amount) AS paid_total
FROM   demo_sales
WHERE  status = 'PAID'
GROUP  BY region
HAVING SUM(amount) > 3000
ORDER  BY paid_total DESC;
```

`WHERE status='PAID'` removes non-PAID transactions before computation. `HAVING SUM(amount)>3000` retains only groups whose total meets the threshold.

### 10.3. Do not use aggregates directly in WHERE at the same level

Do not write:

```sql
SELECT region, SUM(amount)
FROM   demo_sales
WHERE  SUM(amount) > 3000
GROUP  BY region;
```

Because `WHERE` is applied before group aggregates are computed. Move the group condition to `HAVING`:

```sql
SELECT region, SUM(amount)
FROM   demo_sales
GROUP  BY region
HAVING SUM(amount) > 3000;
```

If you want to filter based on the aggregate of a subquery, you can aggregate in the subquery and then filter in the outer query.

### 10.4. HAVING does not strictly require an explicit GROUP BY

You can use an aggregate in `HAVING` without `GROUP BY` to filter the entire set as a single group:

```sql
SELECT SUM(amount) AS total_amount
FROM   demo_sales
HAVING SUM(amount) > 10000;
```

If the total is greater than 10000, the query returns one row; otherwise, no rows are returned. This pattern is less common, but it helps clarify that HAVING is a condition on aggregate results.

## 11. Conditional counting and summing

Conditional aggregation is a technique for computing multiple metrics in a single query, typically using `CASE` inside aggregate functions.

### 11.1. Counting by status

```sql
SELECT COUNT(*) AS all_sales,
       COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_sales,
       COUNT(CASE WHEN status = 'PENDING' THEN 1 END) AS pending_sales,
       COUNT(CASE WHEN status = 'CANCELLED' THEN 1 END) AS cancelled_sales
FROM   demo_sales;
```

Based on the sample table:

| ALL_SALES | PAID_SALES | PENDING_SALES | CANCELLED_SALES |
| ---: | ---: | ---: | ---: |
| 10 | 7 | 2 | 1 |

Unmatched CASE branches return NULL, so COUNT counts only the corresponding status.

### 11.2. Total revenue by status

```sql
SELECT SUM(CASE WHEN status = 'PAID'
                THEN amount ELSE 0 END) AS paid_amount,
       SUM(CASE WHEN status = 'PENDING'
                THEN amount ELSE 0 END) AS pending_amount,
       SUM(CASE WHEN status = 'CANCELLED'
                THEN amount ELSE 0 END) AS cancelled_amount
FROM   demo_sales;
```

Based on the sample data:

- PAID: 9200.
- PENDING: 1000 (row ID 3; ID 5 has a NULL amount).
- CANCELLED: NULL is converted to 0 by the ELSE 0 branch in the CANCELLED row, so the resulting sum is 0.

If you want a group with no values to evaluate to NULL instead of 0, omit `ELSE 0`:

```sql
SUM(CASE WHEN status = 'CANCELLED' THEN amount END)
```

For CANCELLED rows with a NULL amount, the expression above returns NULL because there are no non-NULL numeric values to sum.

### 11.3. Computing multiple KPIs in a single GROUP BY

```sql
SELECT region,
       COUNT(*) AS total_sales,
       COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_count,
       SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END) AS paid_total,
       AVG(CASE WHEN status = 'PAID' THEN amount END) AS paid_average,
       MIN(CASE WHEN status = 'PAID' THEN amount END) AS min_paid_amount,
       MAX(CASE WHEN status = 'PAID' THEN amount END) AS max_paid_amount
FROM   demo_sales
GROUP  BY region
ORDER  BY region NULLS LAST;
```

Each aggregate has its own input expression, yet all are computed over each region group. This approach is useful for dashboard reports and summary tables.

### 11.4. Conditional COUNT and the ELSE 0 bug

Compare:

```sql
SELECT COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS correct_count,
       COUNT(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS counts_every_row
FROM   demo_sales;
```

The first result is 7; the second result is 10 because both 1 and 0 are non-NULL. When using `COUNT(CASE...)` for conditional counting, you normally **do not need ELSE**.

### 11.5. Percentages

You can calculate the percentage of PAID transactions out of total transactions:

```sql
SELECT
    COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_count,
    COUNT(*) AS total_count,
    ROUND(
      100 * COUNT(CASE WHEN status = 'PAID' THEN 1 END)
          / NULLIF(COUNT(*), 0),
      2
    ) AS paid_percent
FROM demo_sales;
```

`NULLIF(COUNT(*), 0)` protects the division when the input set has no rows. For an aggregate query without GROUP BY, COUNT returns 0 on an empty set, and the division is turned into division by NULL instead of division by zero.

## 12. Aggregates combined with JOIN: avoiding duplicate counting and summing

### 12.1. One parent row with multiple child rows

Suppose an order has multiple detail lines. When joining:

```sql
SELECT o.order_id,
       o.total_amount,
       i.item_id
FROM   orders o
JOIN   order_items i
       ON i.order_id = o.order_id;
```

If an order has three items, the order's `TOTAL_AMOUNT` value appears three times in the join result. Therefore:

```sql
SELECT SUM(o.total_amount) AS total_order_amount
FROM   orders o
JOIN   order_items i
       ON i.order_id = o.order_id;
```

can **repeatedly add the order total according to the number of item lines**, no longer giving the true sum of order amounts.

This is a very common fan-out bug in reporting.

### 12.2. Aggregate first, then JOIN

If the goal is total revenue by customer from the orders table, aggregate orders first:

```sql
SELECT c.customer_id,
       c.customer_name,
       NVL(x.order_total, 0) AS order_total
FROM   customers c
LEFT JOIN (
    SELECT customer_id,
           SUM(total_amount) AS order_total
    FROM   orders
    GROUP  BY customer_id
) x
       ON x.customer_id = c.customer_id;
```

The subquery produces one aggregated row per customer_id; when joined to customers, the total is not multiplied by the number of items.

If you need item counts, aggregate the items table separately by order/customer and then join the pre-aggregated results on the proper key.

### 12.3. COUNT(*) and COUNT(child_id) in LEFT JOIN

Example:

```sql
SELECT c.customer_id,
       COUNT(*) AS joined_rows,
       COUNT(o.order_id) AS actual_orders
FROM   customers c
LEFT JOIN orders o
       ON o.customer_id = c.customer_id
GROUP  BY c.customer_id;
```

For a customer with no orders:

- `COUNT(*)` is still 1 because LEFT JOIN produces one result row with the order-side columns set to NULL.
- `COUNT(o.order_id)` is 0 if `ORDER_ID` is non-NULL in real order rows.

To count actual child rows, use `COUNT` on a child table key column guaranteed to be NOT NULL, typically the primary key. This is an important distinction when writing order-count-per-customer reports.

### 12.4. COUNT(DISTINCT) can be valid, but is not a universal fix for every join

If the goal is to count unique customers after a join, `COUNT(DISTINCT customer_id)` can be appropriate. However, if total amounts are multiplied, using `SUM(DISTINCT total_amount)` is not a general solution: two different orders may have the same total amount, in which case one value would be erroneously dropped.

The proper fix is to identify the **grain (level of detail) of the data**, aggregate at the right grain before joining, or use joins/`EXISTS` matching the actual question.

## 13. Empty sets, empty groups, and subqueries

### 13.1. Aggregate without GROUP BY

```sql
SELECT COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM   demo_sales
WHERE  status = 'NOT_A_STATUS';
```

The result has one row: `ROW_COUNT=0`, `TOTAL_AMOUNT=NULL`.

### 13.2. Aggregate with GROUP BY

```sql
SELECT region,
       COUNT(*) AS row_count,
       SUM(amount) AS total_amount
FROM   demo_sales
WHERE  status = 'NOT_A_STATUS'
GROUP  BY region;
```

There are no input rows, so no groups are formed; the result is **0 rows**, not a row with a count of 0.

### 13.3. Aggregating via a subquery

For example, to find regions whose total revenue exceeds the average regional revenue:

```sql
SELECT region,
       SUM(amount) AS region_total
FROM   demo_sales
GROUP  BY region
HAVING SUM(amount) > (
    SELECT AVG(region_total)
    FROM (
        SELECT SUM(amount) AS region_total
        FROM   demo_sales
        GROUP  BY region
    )
)
ORDER BY region_total DESC;
```

The innermost subquery computes each region's total; the outer subquery computes the average of those regional totals, and the main query filters groups exceeding that threshold. This is how to use subqueries when you need an aggregate over another aggregate result.

You should not write `AVG(SUM(amount))` directly at the same SELECT/GROUP BY level without an appropriate nested query structure. When multi-level aggregation is needed, use a subquery or CTE to separate the steps.

### 13.4. CTEs improve readability for multi-step queries

```sql
WITH region_totals AS (
    SELECT region,
           COUNT(*) AS sale_count,
           SUM(amount) AS total_amount
    FROM   demo_sales
    GROUP  BY region
)
SELECT region,
       sale_count,
       total_amount
FROM   region_totals
WHERE  total_amount >= 3000
ORDER  BY total_amount DESC;
```

A CTE names an intermediate result, helping separate aggregation logic from filtering/presentation logic. The Oracle Optimizer may transform execution; a CTE does not automatically imply that data is always materialized into a temporary table.

## 14. Performance and reading execution plans

### 14.1. Aggregates may need to read a lot of data

A query:

```sql
SELECT SUM(amount)
FROM   demo_sales;
```

must examine all values in the input set to compute an exact sum. Oracle may choose a full table scan, index scan, or another strategy depending on structure and statistics. Simply creating an index on `AMOUNT` does not guarantee that `SUM` will be faster.

### 14.2. COUNT(*) and COUNT(column) are not arbitrary optimization choices

Choose the function based on semantics:

- `COUNT(*)` when you need the number of rows.
- `COUNT(column)` when you need the number of non-NULL values.
- `COUNT(DISTINCT column)` when you need the number of distinct values.

Do not change `COUNT(*)` to `COUNT(1)` expecting a speedup. Do not change `COUNT(*)` to `COUNT(column)` if the column can be NULL; the result will change.

### 14.3. Indexes and MIN/MAX

With a suitable index, Oracle can sometimes find MIN/MAX by accessing one end of the index instead of scanning the whole table. This capability depends on filter conditions, index order, NULLs, statistics, and the execution plan.

Do not infer performance merely from the fact that a column is indexed. Check the execution plan and actual runtime metrics.

### 14.4. GROUP BY and memory

Queries with many groups may use hash aggregation or sort/group by mechanisms. The number of groups, data size, value distribution, parallelism, and memory affect cost. If memory is insufficient, some operations may spill to TEMP.

For large reports, you should:

- Filter rows early with appropriate conditions.
- Choose the right grouping columns, avoiding creating finer-grained groups than required.
- Check table and index statistics.
- Measure execution plans/runtimes.
- Avoid fan-out joins before aggregating.

### 14.5. Viewing an execution plan

Example:

```sql
EXPLAIN PLAN FOR
SELECT region,
       COUNT(*) AS sale_count,
       SUM(amount) AS total_amount
FROM   demo_sales
GROUP  BY region;

SELECT *
FROM   TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` displays the estimated plan. When investigating a query that has already run, a DBA can inspect cursor plans and runtime statistics using appropriate privileges/tools. For a very small demo table, a full scan is normal; there is no need to create an index just to avoid it.

## 15. Common errors and misconceptions

### 15.1. Miscounting due to NULL

**Symptom:** `COUNT(*)` is greater than `COUNT(amount)`.

**Cause:** some rows have no amount. This is a semantic difference, not a counting bug.

**Resolution:** determine whether the report needs to count transactions or transactions with a known amount value.

### 15.2. AVG is lower than expected

**Possible causes:** dividing the sum by COUNT(*) instead of COUNT(column), or the dataset contains real 0 values. `AVG` ignores NULL but includes 0.

**Resolution:** check the non-NULL count, distinguish 0 from NULL, and verify filter conditions before calculating.

### 15.3. SUM returns NULL even though the table has rows

Either all values of the summed expression are NULL, or WHERE selects no rows. Combine `COUNT(*)` and `COUNT(expression)` to tell them apart.

### 15.4. COUNT after LEFT JOIN returns 1 even with no child rows

LEFT JOIN produces a parent row with NULL child columns. `COUNT(*)` counts this joined row; use `COUNT(child.primary_key)` to count actual child rows.

### 15.5. SUM is abnormally large after a JOIN

A parent row may repeat for each child row. Check the grain of the join result and aggregate child/parent tables separately before joining.

### 15.6. SUM(DISTINCT) underreports revenue

DISTINCT removes duplicate values, not duplicate rows by transaction key. Two valid transactions with the same amount will only be summed once. Do not use it to fix fan-out.

### 15.7. MIN/MAX on strings yields results unlike natural language expectations

This is a comparison by string/collation order, not by business meaning. If you need min/max by length, custom priority order, or another rule, express that rule explicitly.

### 15.8. Using WHERE to filter aggregate results

Aggregates at the same SELECT level cannot be used directly in WHERE. Use HAVING, or place the aggregate in a subquery/CTE and filter outside.

### 15.9. GROUP BY does not return a row when there is no data

Without GROUP BY: aggregates typically return one result row, and COUNT can be 0. With GROUP BY: an empty set produces no groups, so no result rows are returned.

### 15.10. Failing to distinguish a 0 sum from a NULL sum

0 is a numeric value; NULL means no aggregate value is defined. Only convert NULL to 0 with NVL/COALESCE when the report/business wants both states represented identically.

## 16. Process for designing an aggregate report

Before writing a reporting query, answer the following questions:

1. **What unit is being counted?** Rows, transactions, customers, products, or distinct value groups?
2. **What does NULL mean?** Unknown, not yet entered, not applicable, or should it be treated as 0?
3. **Is deduplication needed?** DISTINCT on which value, and why?
4. **What set should be computed over?** Which WHERE conditions apply before grouping?
5. **Which dimensions to group by?** Region, month, status, salesperson, or a combination?
6. **What criteria filter groups?** HAVING after aggregation.
7. **Does a JOIN duplicate rows?** Check 1:N relationships and grain before SUM/COUNT.
8. **What should an empty set display?** 0, NULL, or no rows?
9. **Do you need unique values or individual transactions?** Avoid misusing SUM(DISTINCT).
10. **Do you need the full row matching MIN/MAX?** Write a query to find the row and define tie-breaking rules.

Reporting query template:

```sql
SELECT group_key,
       COUNT(*) AS row_count,
       COUNT(value_column) AS known_value_count,
       SUM(value_column) AS total_value,
       AVG(value_column) AS average_value,
       MIN(value_column) AS minimum_value,
       MAX(value_column) AS maximum_value
FROM   source_table
WHERE  row_level_condition
GROUP  BY group_key
HAVING COUNT(*) >= :minimum_rows
ORDER  BY group_key;
```

This is only an illustrative skeleton; replace table/column names and conditions according to the exact grain and business rules.

## 17. Self-check exercises

Use the `DEMO_SALES` table created in section 2.

### Question 1 — COUNT(*)

Write a query to count the total number of rows in the table.

**Hint:**

```sql
SELECT COUNT(*) FROM demo_sales;
```

The result is 10.

### Question 2 — COUNT(column)

Write a query to count the number of rows with a non-NULL amount. Does the result equal COUNT(*)?

**Hint:** Use `COUNT(amount)`; the result is 8 because two rows have a NULL amount.

### Question 3 — COUNT(DISTINCT)

How many distinct amount levels are there, excluding NULL?

**Hint:** `COUNT(DISTINCT amount)`; the result is 6.

### Question 4 — SUM

Calculate the total amount across all transactions. How do the two NULL rows affect it?

**Hint:** `SUM(amount)` = 10200; NULLs are ignored.

### Question 5 — AVG

Calculate the average amount and explain the denominator.

**Hint:** `AVG(amount)` = 1275; the denominator is the 8 non-NULL values.

### Question 6 — MIN/MAX

Find the lowest and highest amounts.

**Hint:** `MIN(amount)=500` and `MAX(amount)=3000`.

### Question 7 — GROUP BY

Calculate the transaction count and total amount by region, including the NULL group.

**Hint:** `GROUP BY region`; the NULL group has one row with a total of 700.

### Question 8 — HAVING

Display only regions with a total amount of at least 3000.

**Hint:** `GROUP BY region HAVING SUM(amount) >= 3000`. NORTH and SOUTH qualify.

### Question 9 — Conditional counting

Count the number of PAID transactions without using WHERE to exclude other statuses.

**Hint:**

```sql
SELECT COUNT(CASE WHEN status = 'PAID' THEN 1 END)
FROM demo_sales;
```

Result is 7.

### Question 10 — COUNT CASE and ELSE 0

Why does `COUNT(CASE WHEN status='PAID' THEN 1 ELSE 0 END)` return 10 instead of 7?

**Hint:** Both 1 and 0 are non-NULL, so COUNT counts every row.

### Question 11 — Total PAID

Calculate the total amount of PAID transactions.

**Hint:** `SUM(CASE WHEN status='PAID' THEN amount END)` or filter `WHERE status='PAID'`; the result is 9200.

### Question 12 — Empty set

Run an aggregate with `WHERE 1=0`. What do COUNT and SUM return?

**Hint:** COUNT returns 0; SUM returns NULL. Because there is no GROUP BY, one result row is still returned.

### Question 13 — LEFT JOIN

A customer with no orders appears after a LEFT JOIN. Why is `COUNT(*)` equal to 1 while `COUNT(order_id)` is 0?

**Hint:** The row is preserved by LEFT JOIN with NULL order-side columns; COUNT(*) counts the joined row, while COUNT(order_id) skips NULL.

### Question 14 — SUM DISTINCT

Two different transactions both have an amount of 500. Why is `SUM(DISTINCT amount)` unsuitable for calculating actual revenue?

**Hint:** DISTINCT drops one of the two 500 values even though they are two separate transactions.

### Question 15 — JOIN fan-out

An order has four item lines. If you join order with item and then SUM(order.total_amount), how is the order total affected?

**Hint:** The order total appears four times in the joined set and can be summed four times. Aggregate orders before joining, or aggregate at the correct grain.

### Question 16 — MIN/MAX dates/times

Write a query to find the earliest and latest sale times.

**Hint:** `MIN(sold_at)` and `MAX(sold_at)`.

### Question 17 — Conditional AVG

Calculate the average amount of PAID transactions.

**Hint:**

```sql
SELECT AVG(CASE WHEN status = 'PAID' THEN amount END)
FROM demo_sales;
```

### Question 18 — Distinguishing NULL and 0

If a report has no transactions in a period, should SUM always be displayed as 0?

**Hint:** It depends on the business requirement. NULL indicates there are no values to aggregate; only convert to 0 when the report intends that interpretation.

## 18. Cleaning up practice data

Only run this after confirming the tables are demo data you created and do not contain data you need to keep:

```sql
-- DESTRUCTIVE OPERATION: for learning schema only.
DROP TABLE demo_sales PURGE;
```

The DROP statement is DDL and removes both the table and its data. Do not run it on application tables; do not rely on ROLLBACK to undo executed DDL.

## 19. Oracle reference documentation

- [Oracle Database SQL Language Reference — Aggregate Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Aggregate-Functions.html): general rules on aggregate functions and NULL handling.
- [Oracle Database SQL Language Reference — COUNT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/COUNT.html): `COUNT(*)`, `COUNT(expression)`, and `COUNT(DISTINCT ...)`.
- [Oracle Database SQL Language Reference — SUM](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SUM.html): summing values and return data types.
- [Oracle Database SQL Language Reference — AVG](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/AVG.html): averages and NULL handling.
- [Oracle Database SQL Language Reference — MIN](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/MIN.html) and [MAX](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/MAX.html): minimum/maximum values.
- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): `WHERE`, `GROUP BY`, `HAVING`, and `ORDER BY`.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): execution plans, optimizer, and aggregate performance.

When using aggregate functions in Oracle, always clarify **whether you are counting rows or values**, **whether NULLs are ignored**, **whether you need to aggregate per transaction or per unique value**, and **whether a JOIN duplicates data before calculation**. Use `GROUP BY` to form groups, `HAVING` to filter groups, and `CASE` to compute conditional metrics. Once these semantics are clear, COUNT, SUM, AVG, MIN, and MAX reports will accurately reflect business data.
