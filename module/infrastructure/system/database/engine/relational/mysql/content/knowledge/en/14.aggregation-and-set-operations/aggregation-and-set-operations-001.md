# COUNT(*), COUNT(column), SUM, AVG, MIN, and MAX

Aggregate functions turn multiple rows into a single value or one value per group. They are commonly used in revenue reporting, order statistics, inventory checks, data analytics, and business queries. Using aggregate functions correctly requires understanding which rows are counted, how `NULL` is handled, and how results change when the input set is empty.

MySQL provides the core functions `COUNT()`, `SUM()`, `AVG()`, `MIN()`, and `MAX()`. `COUNT(*)` counts rows, `COUNT(column)` counts non-`NULL` values, `SUM()` computes totals, `AVG()` computes averages, and `MIN()` and `MAX()` find the minimum/maximum value. These functions are often paired with `GROUP BY` to produce results by customer, product, status, or time period.

This lesson belongs to the `DATABASE_MYSQL` module, where you practice table design, data types, keys, SQL queries, indexes, transactions, concurrency control, reading execution plans, and query optimization. The goal is to write aggregations with accurate semantics, handle missing data properly, and avoid miscounting or double-summing caused by joins or duplicate data.

After this lesson, you will be able to:

- Distinguish between `COUNT(*)`, `COUNT(column)`, and `COUNT(DISTINCT column)`.
- Use `SUM`, `AVG`, `MIN`, and `MAX` on numeric data and understand their behavior with `NULL`.
- Predict results when there are no rows or when all input values are `NULL`.
- Group data with `GROUP BY` and filter groups with `HAVING`.
- Write conditional aggregation to compute multiple metrics in a single scan.
- Avoid row multiplication bugs when aggregating across multiple one-to-many relationships.
- Understand result data types, collation effects, and limitations when aggregating temporal values.
- Verify aggregate queries using sample data and `EXPLAIN`.

## 1. How Do Aggregate Functions Work?

An aggregate function takes a set of values and computes a single result. Without `GROUP BY`, MySQL aggregates the entire row set matching `FROM`/`WHERE` into one result. With `GROUP BY`, MySQL divides rows into groups and computes the aggregate separately for each group.

```sql
SELECT
    COUNT(*) AS row_count,
    SUM(amount) AS total_amount,
    AVG(amount) AS average_amount,
    MIN(amount) AS minimum_amount,
    MAX(amount) AS maximum_amount
FROM sales
WHERE status = 'PAID';
```

This query returns one aggregated row for all `PAID` transactions. When `GROUP BY customer_id` is added, it returns one row for each customer that has at least one input row after the `WHERE` condition.

The logical processing order can be pictured as follows:

```text
FROM / JOIN
     |
     v
WHERE (filter input rows)
     |
     v
GROUP BY (create groups, if any)
     |
     v
Aggregate functions
     |
     v
HAVING (filter groups)
     |
     v
SELECT (project results)
     |
     v
ORDER BY / LIMIT
```

This is a mental model for query semantics. The optimizer may execute a different plan, but the result must obey SQL rules.

## 2. Creating Sample Data to Observe

The examples use two temporary tables: customers and sales transactions. The fixture includes normal values, `NULL`, a zero amount, two transactions with the same amount, and one customer with no transactions yet.

Run all examples in the same MySQL session:

```sql
DROP TEMPORARY TABLE IF EXISTS sales;
DROP TEMPORARY TABLE IF EXISTS customers;

CREATE TEMPORARY TABLE customers (
    customer_id INT UNSIGNED NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE TEMPORARY TABLE sales (
    sale_id BIGINT UNSIGNED NOT NULL,
    customer_id INT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    amount DECIMAL(10, 2) NULL,
    quantity INT UNSIGNED NULL,
    PRIMARY KEY (sale_id),
    KEY idx_sales_customer_status (customer_id, status)
) ENGINE = InnoDB;

INSERT INTO customers (customer_id, customer_name) VALUES
(1, 'An'),
(2, 'Bình'),
(3, 'Chi'),
(4, 'Dũng');

INSERT INTO sales (sale_id, customer_id, status, amount, quantity) VALUES
(101, 1, 'PAID',    100.00, 2),
(102, 1, 'PAID',      NULL, 1),
(103, 1, 'PENDING',  50.00, 1),
(104, 2, 'PAID',    200.00, 3),
(105, 2, 'PAID',    200.00, 2),
(106, 3, 'PAID',      0.00, 0);
```

Meaning of the test data:

| Data | Test purpose |
| --- | --- |
| Sale 101 | Normal numeric value |
| Sale 102 | `amount` is `NULL`, but the row still exists |
| Sale 103 | Status is not `PAID` |
| Sale 104 and 105 | Two distinct rows with the same `amount = 200.00` |
| Sale 106 | Zero value, distinct from `NULL` |
| Customer 4 | No rows in the `sales` table |

This fixture clearly demonstrates that aggregates ignore `NULL`, counting rows differs from counting values, and `DISTINCT` can change the meaning of a calculation.

## 3. COUNT(*) — Counting Rows

`COUNT(*)` counts the number of rows in the input set, regardless of whether the columns in a row contain `NULL` values.

```sql
SELECT COUNT(*) AS total_sales
FROM sales;
```

The expected result is `6`, because the table has six rows.

Count paid transactions:

```sql
SELECT COUNT(*) AS paid_sales
FROM sales
WHERE status = 'PAID';
```

The expected result is `5`. The row with `amount = NULL` is still counted because `COUNT(*)` only cares about the number of rows, not the values of individual columns.

`COUNT(*)` also counts rows after a join. This is an important point: if one parent row matches three child rows, the parent row appears three times in the joined result set and `COUNT(*)` may count it three times. To count parent entities, choose the appropriate key or query structure.

## 4. COUNT(column) — Counting Non-NULL Values

`COUNT(expr)` counts the number of rows where the expression `expr` evaluates to a non-`NULL` value. It does not count `NULL` values.

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    COUNT(quantity) AS quantity_count
FROM sales
WHERE status = 'PAID';
```

Expected result:

| row_count | amount_count | quantity_count |
| ---: | ---: | ---: |
| 5 | 4 | 5 |

There are five `PAID` transactions, but only four transactions have a non-`NULL` `amount`. `quantity` has a value in all five transactions, including zero.

Key points to remember:

- `COUNT(amount)` still counts `0`, empty strings, or `FALSE` if the expression is not `NULL`.
- `COUNT(*)` counts rows even if every column is `NULL`.
- `COUNT(1)` also usually counts all rows just like `COUNT(*)` because the literal expression `1` is not `NULL`; to express intent clearly, prefer `COUNT(*)` when the goal is counting rows.
- `COUNT(nullable_column)` is appropriate when you want to know how many rows actually have a value in that column.

## 5. COUNT(DISTINCT ...) — Counting Distinct Values

`COUNT(DISTINCT expr)` counts the number of distinct values and ignores `NULL`.

```sql
SELECT
    COUNT(*) AS paid_rows,
    COUNT(amount) AS non_null_amounts,
    COUNT(DISTINCT amount) AS distinct_amounts
FROM sales
WHERE status = 'PAID';
```

The expected result is `5`, `4`, `3`:

- There are five `PAID` rows.
- There are four non-`NULL` amount values.
- The distinct amounts are `100.00`, `200.00`, and `0.00`.

MySQL also supports counting combinations of multiple expressions:

```sql
SELECT COUNT(DISTINCT customer_id, status) AS distinct_customer_status_pairs
FROM sales;
```

With the multi-expression form, MySQL counts distinct combinations of values where every expression in the combination is non-`NULL`.

For string expressions, what counts as "distinct" is also affected by collation. If a collation is case-insensitive or accent-insensitive, certain strings may be treated as equivalent when `COUNT(DISTINCT text_column)` runs. If the business logic requires byte-level or case-sensitive distinction, choose an appropriate collation and test with representative data.

### 5.1. DISTINCT Does Not Mean Deduplicating Rows

Transactions 104 and 105 are two separate transactions even though they share the same amount. When computing a sum:

```sql
SELECT
    SUM(amount) AS total_amount,
    SUM(DISTINCT amount) AS distinct_amount_total
FROM sales
WHERE customer_id = 2
  AND status = 'PAID';
```

The result is:

| total_amount | distinct_amount_total |
| ---: | ---: |
| 400.00 | 200.00 |

`SUM(DISTINCT amount)` adds each amount value only once. It is not a fix for a join that duplicates rows when each row has its own business meaning. Be clear about whether you want the sum of transactions or the sum of unique price levels.

## 6. SUM() — Computing Totals

`SUM(expr)` adds the non-`NULL` values in the input set. If there are no values to add (the input set is empty or all values are `NULL`), the result is `NULL`.

```sql
SELECT
    SUM(amount) AS paid_revenue,
    SUM(quantity) AS paid_quantity
FROM sales
WHERE status = 'PAID';
```

Expected result:

| paid_revenue | paid_quantity |
| ---: | ---: |
| 500.00 | 8 |

The total amount is `100 + 200 + 200 + 0 = 500`. The `NULL` value in sale 102 is ignored. Quantity is `2 + 1 + 3 + 2 + 0 = 8`.

### 6.1. SUM and NULL

The following three cases produce different results:

```sql
-- No matching rows
SELECT SUM(amount) AS result
FROM sales
WHERE customer_id = 999;

-- Rows exist, but every amount is NULL
SELECT SUM(amount) AS result
FROM sales
WHERE customer_id = 1
  AND sale_id = 102;

-- Row with amount equal to 0
SELECT SUM(amount) AS result
FROM sales
WHERE customer_id = 3;
```

The results are `NULL`, `NULL`, and `0.00`, respectively. The first two cases have an undefined sum because there are no numeric values to add; the last case has an actual numeric value of 0.

If a report should display 0 instead of `NULL`, use `COALESCE()`:

```sql
SELECT COALESCE(SUM(amount), 0.00) AS paid_revenue
FROM sales
WHERE customer_id = 999;
```

This is a display/business rule. Do not mechanically replace every `NULL` with 0 if the system needs to distinguish "no data" from "an actual sum of 0".

## 7. AVG() — Computing Averages

`AVG(expr)` computes the sum of non-`NULL` values divided by the count of non-`NULL` values. It does not divide by the total number of rows if there are `NULL` values.

```sql
SELECT AVG(amount) AS average_paid_amount
FROM sales
WHERE status = 'PAID';
```

There are four non-`NULL` amounts: 100, 200, 200, and 0. The result is `500 / 4 = 125.00`.

Compare:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    SUM(amount) AS amount_sum,
    AVG(amount) AS amount_avg,
    SUM(amount) / COUNT(*) AS wrong_average_if_null_means_missing
FROM sales
WHERE status = 'PAID';
```

`AVG(amount)` divides by 4, whereas `SUM(amount) / COUNT(*)` divides by 5 and yields 100.00. If `NULL` means missing data, dividing by `COUNT(*)` produces an incorrect average. Define the denominator according to the business definition.

`AVG(DISTINCT amount)` computes the average over distinct values. For customer 2, `AVG(amount)` is 200.00 and `AVG(DISTINCT amount)` is also 200.00; on data with many price levels, the two results can differ significantly.

## 8. MIN() and MAX() — Finding Minimum and Maximum Values

`MIN(expr)` returns the smallest value and `MAX(expr)` returns the largest value in the set of non-`NULL` values. If there are no non-`NULL` values, both return `NULL`.

```sql
SELECT
    MIN(amount) AS minimum_amount,
    MAX(amount) AS maximum_amount
FROM sales
WHERE status = 'PAID';
```

The expected result is `0.00` and `200.00`. `NULL` does not participate in comparisons; `0` is still a valid value.

MIN/MAX are not limited to numbers:

```sql
SELECT
    MIN(customer_name) AS first_name_by_collation,
    MAX(customer_name) AS last_name_by_collation
FROM customers;
```

For strings, comparison order depends on data type and collation. A case-insensitive or accent-insensitive collation may treat certain strings as equivalent under comparison rules. Do not assume `MIN(text_column)` means "the first string chronologically" or "the first name in Vietnamese dictionary order" without verifying the collation.

For `ENUM` and `SET`, `MIN()`/`MAX()` compare the string values rather than internal declaration positions. If you need a specific business ordering, write a `CASE` expression or use an explicit ordering column.

## 9. Results When the Input Set Is Empty or NULL

The following table summarizes key behavior:

| Function | Input set has no rows | Rows exist, but all expr values are NULL |
| --- | --- | --- |
| `COUNT(*)` | `0` | Counts number of rows |
| `COUNT(expr)` | `0` | `0` |
| `COUNT(DISTINCT expr)` | `0` | `0` |
| `SUM(expr)` | `NULL` | `NULL` |
| `AVG(expr)` | `NULL` | `NULL` |
| `MIN(expr)` | `NULL` | `NULL` |
| `MAX(expr)` | `NULL` | `NULL` |

Empty set example:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    SUM(amount) AS amount_sum,
    AVG(amount) AS amount_avg,
    MIN(amount) AS min_amount,
    MAX(amount) AS max_amount
FROM sales
WHERE customer_id = 999;
```

An aggregate query without `GROUP BY` still returns exactly one result row. COUNT functions return 0, and the remaining aggregate functions return `NULL`.

If you add `GROUP BY customer_id` to the same query, an empty input set produces 0 groups, so the result has no rows. This is an important difference when an API expects either an empty summary row or an empty list of groups.

## 10. GROUP BY — Aggregating by Groups

`GROUP BY` partitions rows into groups that share the same values in the grouping expressions. Aggregate functions are evaluated independently for each group.

```sql
SELECT
    customer_id,
    COUNT(*) AS paid_sale_count,
    COUNT(amount) AS amount_count,
    SUM(amount) AS paid_total,
    AVG(amount) AS average_amount,
    MIN(amount) AS min_amount,
    MAX(amount) AS max_amount
FROM sales
WHERE status = 'PAID'
GROUP BY customer_id
ORDER BY customer_id;
```

Expected result:

| customer_id | paid_sale_count | amount_count | paid_total | average_amount | min_amount | max_amount |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 2 | 1 | 100.00 | 100.00 | 100.00 | 100.00 |
| 2 | 2 | 2 | 400.00 | 200.00 | 200.00 | 200.00 |
| 3 | 1 | 1 | 0.00 | 0.00 | 0.00 | 0.00 |

Customer 4 does not appear because they have no rows in `sales` to form a group. To include customers with no transactions, start from the `customers` table and use `LEFT JOIN`.

### 10.1. GROUP BY with LEFT JOIN

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(s.sale_id) AS paid_sale_count,
    COUNT(s.amount) AS amount_count,
    SUM(s.amount) AS paid_total,
    AVG(s.amount) AS average_amount
FROM customers AS c
LEFT JOIN sales AS s
    ON s.customer_id = c.customer_id
   AND s.status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

The result includes customer 4. For this customer, `COUNT(s.sale_id) = 0`, `COUNT(s.amount) = 0`, while `SUM` and `AVG` are `NULL`.

With the current fixture, expected result:

| customer_id | customer_name | paid_sale_count | amount_count | paid_total | average_amount |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | An | 2 | 1 | 100.00 | 100.00 |
| 2 | Bình | 2 | 2 | 400.00 | 200.00 |
| 3 | Chi | 1 | 1 | 0.00 | 0.00 |
| 4 | Dũng | 0 | 0 | `NULL` | `NULL` |

The condition `s.status = 'PAID'` is placed inside `ON` so it does not filter out customers with no paid orders. Moving that condition into `WHERE` would filter out the `LEFT JOIN`-generated row where `s.status = NULL`, dropping customer 4.

### 10.2. COUNT(*) vs COUNT on Child Table Key After LEFT JOIN

For a customer with no transactions, `LEFT JOIN` still produces one output row containing the left-side columns and `NULL` for the right-side columns:

```sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_rows,
    COUNT(s.sale_id) AS sale_rows
FROM customers AS c
LEFT JOIN sales AS s
    ON s.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Customer 4 has `joined_rows = 1`, but `sale_rows = 0`. When counting records on the right side of an outer join, use a non-nullable key column such as `sale_id`.

### 10.3. NULL in GROUP BY

Rows with `NULL` in a grouping expression are placed into the same `NULL` group. This differs from the comparison `NULL = NULL`, which does not return `TRUE`; grouping rules treat NULL values as belonging to the same group for aggregation.

```sql
SELECT
    region,
    COUNT(*) AS row_count
FROM some_table
GROUP BY region;
```

If `region` has multiple NULL rows, the result includes one group with `region = NULL`. For display, you can use `COALESCE(region, 'Uncategorized')`, while making sure the fallback label cannot be confused with an actual region value.

## 11. WHERE and HAVING

`WHERE` filters rows before grouping and computing aggregates. `HAVING` filters group results after aggregates are computed.

Example: calculate the total of `PAID` transactions for each customer, showing only customers whose total is greater than 100:

```sql
SELECT
    customer_id,
    SUM(amount) AS paid_total
FROM sales
WHERE status = 'PAID'
GROUP BY customer_id
HAVING SUM(amount) > 100
ORDER BY paid_total DESC;
```

`WHERE status = 'PAID'` filters input transactions; `HAVING SUM(amount) > 100` filters groups after the total is calculated. MySQL allows referencing a select-list alias in `HAVING`:

```sql
HAVING paid_total > 100
```

However, for query clarity and portability across database systems, you can repeat the aggregate expression in `HAVING`. Never use an aggregate directly in `WHERE`:

```sql
-- Wrong: WHERE is processed before grouping
SELECT customer_id, SUM(amount)
FROM sales
WHERE SUM(amount) > 100
GROUP BY customer_id;
```

Move the group condition to `HAVING`.

## 12. Conditional Aggregation — Multiple Metrics in One Query

Conditional aggregation uses `CASE` inside an aggregate to compute multiple metric breakdowns over the same set of rows.

Example: count and sum transactions by status:

```sql
SELECT
    customer_id,
    COUNT(*) AS all_sales,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid_sales,
    SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) AS pending_sales,
    SUM(CASE WHEN status = 'PAID' THEN amount END) AS paid_amount,
    SUM(CASE WHEN status = 'PENDING' THEN amount END) AS pending_amount
FROM sales
GROUP BY customer_id
ORDER BY customer_id;
```

A `CASE` without `ELSE` in the amount sum expression returns `NULL` for rows not matching that status. `SUM()` ignores NULL values, so a group with no transactions of that status gets a `NULL` total. If you want the total to display 0 when there are no matching transactions, wrap it in `COALESCE()` at the outer level:

```sql
COALESCE(SUM(CASE WHEN status = 'REFUNDED' THEN amount END), 0.00)
    AS refunded_amount
```

Conditional counting can also be written with `COUNT(CASE ...)`:

```sql
SELECT
    customer_id,
    COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_count,
    COUNT(CASE WHEN status = 'PENDING' THEN 1 END) AS pending_count
FROM sales
GROUP BY customer_id;
```

`COUNT()` counts only non-NULL expressions; non-matching branches have no `ELSE`, so they return NULL and are not counted.

## 13. Data Types of Aggregate Results

Result types affect JDBC, DTOs, and subsequent arithmetic in SQL.

| Function | Result type characteristics in MySQL |
| --- | --- |
| `COUNT()` | Returns a `BIGINT` integer |
| `SUM()` with exact-value arguments (integer/DECIMAL) | Returns `DECIMAL` |
| `SUM()` with approximate-value arguments (`FLOAT`/`DOUBLE`) | Returns `DOUBLE` |
| `AVG()` with exact-value arguments | Returns `DECIMAL` |
| `AVG()` with approximate-value arguments | Returns `DOUBLE` |
| `MIN()` / `MAX()` | Returns a value of the same type as the input expression |

For example, if `amount` is `DECIMAL(10,2)`, read `SUM(amount)` and `AVG(amount)` with Java `BigDecimal` rather than converting to `double` if decimal precision is required. `COUNT()` is typically read as `long`/`Long` in JDBC.

```java
long saleCount = resultSet.getLong("sale_count");
BigDecimal total = resultSet.getBigDecimal("total_amount");
BigDecimal average = resultSet.getBigDecimal("average_amount");
```

If an aggregate result can be NULL—for example, `SUM()` over an empty set—check for null or use a wrapper/reference type. Never read a potentially NULL value into a primitive and treat 0 as a real value.

## 14. Aggregating Temporal Data

`MIN()` and `MAX()` are useful with `DATE`, `DATETIME`, and `TIMESTAMP`, such as finding the earliest or latest transaction:

```sql
SELECT
    MIN(placed_at) AS first_sale_at,
    MAX(placed_at) AS latest_sale_at
FROM sales_history;
```

Do not apply `SUM()` or `AVG()` directly to `TIME`, `DATE`, or `DATETIME` expecting arithmetic in time units. MySQL may convert temporal values to numeric form, truncating after the first non-digit character and yielding unexpected results.

If you need the total of `TIME` durations, convert to seconds first:

```sql
SELECT SEC_TO_TIME(SUM(TIME_TO_SEC(duration))) AS total_duration
FROM task_runs;
```

If you need the average duration:

```sql
SELECT SEC_TO_TIME(AVG(TIME_TO_SEC(duration))) AS average_duration
FROM task_runs;
```

`TIME_TO_SEC()` returns the number of seconds (including fractional seconds if TIME has them). `SEC_TO_TIME()` converts seconds back to TIME. Check the range limits of the TIME type if total durations can be very large or exceed the representable range.

## 15. Avoiding Row Multiplication When Joining Before Aggregating

A common bug is joining two one-to-many child tables and then summing. If an order has 2 line items and 3 payments, a direct join produces 6 rows. `SUM(item_amount)` and `SUM(payment_amount)` are then multiplied.

Illustration:

```text
orders (1)
   |             |
   | 1-to-many   | 1-to-many
   v             v
order_items    payments
   2 rows        3 rows
        \        /
         JOIN result
            6 rows
```

Aggregate each child table down to one row per order before joining:

```sql
SELECT
    o.order_id,
    item_totals.items_total,
    payment_totals.payments_total
FROM orders AS o
LEFT JOIN (
    SELECT order_id, SUM(quantity * unit_price) AS items_total
    FROM order_items
    GROUP BY order_id
) AS item_totals
    ON item_totals.order_id = o.order_id
LEFT JOIN (
    SELECT order_id, SUM(amount) AS payments_total
    FROM payments
    GROUP BY order_id
) AS payment_totals
    ON payment_totals.order_id = o.order_id;
```

Each derived table has at most one row per `order_id`, so the join does not cross-multiply child rows. This is a structural example; the `orders`, `order_items`, and `payments` tables must be created according to your own lab schema.

Do not use `SUM(DISTINCT amount)` as a generic fix for join fan-out. Two legitimate amounts can be identical and still need to be summed twice. Fix the join cardinality or aggregate before joining.

## 16. Indexes and Performance of Aggregate Queries

Aggregates must process their input rows. Appropriate indexes can reduce the number of rows read or provide access in grouping order, though no single index is optimal for every aggregate query.

Example query:

```sql
SELECT customer_id, SUM(amount)
FROM sales
WHERE status = 'PAID'
GROUP BY customer_id;
```

For this query, an index starting with `status` followed by `customer_id` can help filter by status first and then group by customer. A covering index that also includes `amount` can avoid reading rows from the clustered index, at the cost of a larger index and higher write overhead.

Check the execution plan:

```sql
EXPLAIN
SELECT customer_id, SUM(amount)
FROM sales
WHERE status = 'PAID'
GROUP BY customer_id;
```

Inspect `type`, `key`, `rows`, `filtered`, and `Extra`. Depending on the query, MySQL may use an index or create a temporary table/filesort for grouping and sorting. Do not assume a query is slow solely because `Using temporary` appears; measure with representative data.

Guidelines:

- Push irrelevant row filters into `WHERE` before grouping.
- Select only the columns you actually need.
- Choose indexes based on the combination of filters, joins, and grouping.
- Weigh covering index size against the benefit of avoiding table lookups.
- Verify cardinality and statistics; small fixture datasets do not represent production distributions.
- Use `EXPLAIN ANALYZE` when actually executing the query is acceptable.

## 17. Hands-on Exercises

1. Run the fixture in section 2. Compute `COUNT(*)`, `COUNT(amount)`, `SUM(amount)`, `AVG(amount)`, `MIN(amount)`, and `MAX(amount)` for status `PAID`.
2. Compare `COUNT(*)` with `COUNT(amount)` and explain the effect of sale 102.
3. Compare `SUM(amount)` with `SUM(DISTINCT amount)` for customer 2.
4. Run aggregates on an empty set and on a set where all amounts are NULL. Record each function's output.
5. Add `GROUP BY customer_id`, then switch to a `LEFT JOIN` from customers to retain customers with no transactions.
6. Test `COUNT(*)` and `COUNT(s.sale_id)` after `LEFT JOIN`; explain why the results differ for customer 4.
7. Write conditional aggregation to compute the count of `PAID` and `PENDING` transactions and the total amount for each status.
8. Create data with two one-to-many child tables and demonstrate how a direct join multiplies rows and corrupts totals. Fix it by aggregating each child table first.
9. Find the earliest/latest transaction using `MIN()` and `MAX()`. Try aggregating durations via `TIME_TO_SEC()` and `SEC_TO_TIME()`.
10. Run `EXPLAIN` on an aggregate query grouped by status and customer; test a composite index and compare plans on a sufficiently large dataset.

## 18. Checklist Before Deploying Aggregations to Production

- [ ] Clearly defined the counting unit: rows, non-NULL values, entities, or distinct values.
- [ ] Selected `COUNT(*)`, `COUNT(column)`, or `COUNT(DISTINCT ...)` to match the exact requirement.
- [ ] Defined how `NULL`, `0`, and empty input sets should be handled.
- [ ] Verified whether `SUM(DISTINCT)`/`AVG(DISTINCT)` matches the business meaning.
- [ ] `WHERE` filters rows before aggregation and `HAVING` filters groups after aggregation.
- [ ] `GROUP BY` does not depend on non-deterministic values; compatible with `ONLY_FULL_GROUP_BY`.
- [ ] Outer joins count a non-nullable key of the child table rather than `COUNT(*)` when counting child rows.
- [ ] No join fan-out multiplies values before summing.
- [ ] Aggregate result types are compatible with JDBC and the domain model.
- [ ] Temporal values are converted to numeric units before `SUM`/`AVG` of durations.
- [ ] Indexes and execution plans have been verified with representative data.

## 19. Completion Criteria

You have completed this lesson when you can explain the differences between `COUNT(*)`, `COUNT(column)`, and `COUNT(DISTINCT ...)`, accurately predict the behavior of `SUM`, `AVG`, `MIN`, and `MAX` with `NULL` and empty sets, write `GROUP BY`/`HAVING` queries and conditional aggregations, avoid miscounting after `LEFT JOIN` or join fan-out, and choose appropriate index checks and result types for your application.

## References

- [MySQL 8.4 Reference Manual — Aggregate Functions](https://dev.mysql.com/doc/refman/8.4/en/aggregate-functions.html)
- [MySQL 8.4 Reference Manual — GROUP BY Modifiers](https://dev.mysql.com/doc/refman/8.4/en/group-by-modifiers.html)
- [MySQL 8.4 Reference Manual — EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
