# NULL, Empty Sets, and Aggregate Results

Aggregate functions in MySQL such as `COUNT()`, `SUM()`, `AVG()`, `MIN()`, and `MAX()` do not handle `NULL` the same way. Most aggregate functions ignore `NULL` values; `COUNT(*)` counts rows regardless of whether columns contain `NULL`, whereas `COUNT(expression)` counts only non-`NULL` expressions. When the input has no rows or no non-`NULL` values, `COUNT()` returns 0, while `SUM()`, `AVG()`, `MIN()`, and `MAX()` return `NULL`.

The distinction between an empty set, a group with no valid values, and an aggregated value of zero is critical in reporting, revenue statistics, data analytics, and missing-data handling. In the `DATABASE_MYSQL` module, understanding these rules is essential for writing `GROUP BY`, `HAVING`, conditional aggregation, and safe aggregate queries.

## Objectives

After this lesson, you will be able to:

- Distinguish an empty result set from a set that has rows where all aggregated values are `NULL`.
- Explain the differences between `COUNT(*)`, `COUNT(expression)`, and `COUNT(DISTINCT expression)`.
- Predict the results of `SUM()`, `AVG()`, `MIN()`, and `MAX()` when the input is empty or contains `NULL`.
- Understand why an aggregate without `GROUP BY` still returns one row on an empty set, whereas `GROUP BY` may return no groups.
- Use `COALESCE()`/`IFNULL()` with accurate semantics instead of turning every missing-data case into 0.
- Write conditional aggregation, `HAVING`, and aggregations over `LEFT JOIN` without miscounting rows.
- Distinguish `DISTINCT` from `COUNT(DISTINCT ...)` when `NULL` is present.

## 1. Sample Data

The examples use the `payment_sample` table. The `amount` column is nullable to represent an undetermined amount or missing recorded data.

```sql
CREATE TABLE payment_sample (
    payment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    category VARCHAR(20) NULL,
    amount DECIMAL(12, 2) NULL,
    note VARCHAR(100) NULL,
    PRIMARY KEY (payment_id),
    KEY idx_payment_category (category)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;

INSERT INTO payment_sample (category, amount, note)
VALUES
    ('A', 10.00, 'cash'),
    ('A', NULL, 'amount pending'),
    ('A', 30.00, 'card'),
    ('B', NULL, 'not recorded'),
    ('B', NULL, NULL),
    (NULL, 5.00, 'unclassified'),
    (NULL, NULL, 'unknown amount');
```

Three data groups are present: `A`, `B`, and `NULL`. Group `A` has two known amount values; group `B` has two rows with no non-`NULL` amount values; group `NULL` has one amount value and one missing value.

## 2. NULL in Aggregate Functions

Most aggregate functions ignore `NULL` arguments. This means they compute over present values rather than treating `NULL` as 0.

| Function | How `NULL` is handled | Result when there are no non-`NULL` values |
|---|---|---|
| `COUNT(*)` | Counts every row, including rows with `NULL` columns | `0` if the input has no rows |
| `COUNT(expr)` | Counts only rows where `expr` is not `NULL` | `0` |
| `COUNT(DISTINCT expr)` | Counts unique non-`NULL` values | `0` |
| `SUM(expr)` | Ignores `NULL`, sums remaining values | `NULL` |
| `AVG(expr)` | Ignores `NULL`, averages remaining values | `NULL` |
| `MIN(expr)` | Ignores `NULL`, finds the minimum value | `NULL` |
| `MAX(expr)` | Ignores `NULL`, finds the maximum value | `NULL` |
| `GROUP_CONCAT(expr)` | Ignores `NULL` arguments | `NULL` if there are no non-`NULL` values |

### 2.1. COUNT(*) and COUNT(expression)

Run the query on group `A`:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    COUNT(note) AS note_count
FROM payment_sample
WHERE category = 'A';
```

Result:

| row_count | amount_count | note_count |
|---:|---:|---:|
| 3 | 2 | 3 |

`COUNT(*)` counts three rows. `COUNT(amount)` counts only the two rows with non-`NULL` `amount`. `COUNT(note)` counts three rows because all three `note` values in group A contain data.

Run on group `B`:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    COUNT(note) AS note_count
FROM payment_sample
WHERE category = 'B';
```

Result:

| row_count | amount_count | note_count |
|---:|---:|---:|
| 2 | 0 | 1 |

Group B has two rows, but no non-`NULL` `amount` values. This is not an empty set: rows still exist, only the monetary data is missing.

### 2.2. COUNT(DISTINCT expression)

`COUNT(DISTINCT expression)` counts non-`NULL` values after deduplication:

```sql
SELECT
    COUNT(category) AS non_null_categories,
    COUNT(DISTINCT category) AS distinct_non_null_categories
FROM payment_sample;
```

The result is `5` for `COUNT(category)` and `2` for `COUNT(DISTINCT category)`: five rows have a non-`NULL` category, but there are only two distinct values, `A` and `B`.

`COUNT(DISTINCT category)` does not count `NULL`. By contrast, `SELECT DISTINCT category` can return a single `NULL` row:

```sql
SELECT DISTINCT category
FROM payment_sample;
```

Therefore, "counting distinct values" with `COUNT(DISTINCT ...)` is not equivalent to counting the rows returned by `SELECT DISTINCT` when the column contains `NULL`.

## 3. SUM, AVG, MIN, and MAX with NULL

For group `A`:

```sql
SELECT
    SUM(amount) AS total_amount,
    AVG(amount) AS average_amount,
    MIN(amount) AS minimum_amount,
    MAX(amount) AS maximum_amount
FROM payment_sample
WHERE category = 'A';
```

Result:

| total_amount | average_amount | minimum_amount | maximum_amount |
|---:|---:|---:|---:|
| 40.00 | 20.00 | 10.00 | 30.00 |

Aggregate functions skip the row where `amount IS NULL`. `AVG(amount)` computes the average `(10 + 30) / 2 = 20`, rather than dividing by all three rows.

For group `B`:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(amount) AS known_amount_count,
    SUM(amount) AS total_amount,
    AVG(amount) AS average_amount,
    MIN(amount) AS minimum_amount,
    MAX(amount) AS maximum_amount
FROM payment_sample
WHERE category = 'B';
```

Result:

| row_count | known_amount_count | total_amount | average_amount | minimum_amount | maximum_amount |
|---:|---:|---:|---:|---:|---:|
| 2 | 0 | `NULL` | `NULL` | `NULL` | `NULL` |

Rows exist, but there are no amounts to compute over. Returning `0` for the sum or average in this case could mislead a report into assuming the actual total is 0.

## 4. Empty Sets and Aggregates Without GROUP BY

An aggregate query without `GROUP BY` returns one result row even when there are no input rows. `COUNT()` returns `0`; functions such as `SUM()`, `AVG()`, `MIN()`, and `MAX()` return `NULL`.

Example filtering for a non-existent category:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    SUM(amount) AS total_amount,
    AVG(amount) AS average_amount,
    MIN(amount) AS minimum_amount,
    MAX(amount) AS maximum_amount
FROM payment_sample
WHERE category = 'C';
```

Result:

| row_count | amount_count | total_amount | average_amount | minimum_amount | maximum_amount |
|---:|---:|---:|---:|---:|---:|
| 0 | 0 | `NULL` | `NULL` | `NULL` | `NULL` |

Note: the query still returns one row. That row is the result of aggregating over an empty input set, not a data row from `payment_sample`.

### 4.1. An Empty Set Differs from an All-NULL Set

Compare the two queries:

```sql
-- Input set has two rows, but both amounts are NULL.
SELECT COUNT(*) AS row_count, COUNT(amount) AS value_count, SUM(amount) AS total
FROM payment_sample
WHERE category = 'B';

-- No input rows.
SELECT COUNT(*) AS row_count, COUNT(amount) AS value_count, SUM(amount) AS total
FROM payment_sample
WHERE category = 'C';
```

| Case | `COUNT(*)` | `COUNT(amount)` | `SUM(amount)` |
|---|---:|---:|---:|
| Category B: two rows, all amounts NULL | 2 | 0 | `NULL` |
| Category C: no rows | 0 | 0 | `NULL` |

Looking only at `SUM(amount)` cannot distinguish the two cases. Combine `COUNT(*)` and `COUNT(amount)` to tell whether there are no rows or rows exist with no valid values.

### 4.2. Deleting All Data Still Does Not Eliminate the Aggregate Result Row

In an empty table, the query:

```sql
SELECT COUNT(*) AS row_count, SUM(amount) AS total_amount
FROM payment_sample;
```

still returns one row: `row_count = 0`, `total_amount = NULL`. You can observe this in a temporary table or an empty derived table without deleting any data:

```sql
SELECT COUNT(*) AS row_count, SUM(amount) AS total_amount
FROM (
    SELECT CAST(NULL AS DECIMAL(12, 2)) AS amount
    WHERE 1 = 0
) AS empty_input;
```

The input to the aggregate has zero rows. Therefore `COUNT(*)` is 0 and `SUM(amount)` is `NULL`.

## 5. GROUP BY on an Empty Set and NULL-Only Groups

With `GROUP BY`, MySQL produces results only for groups that actually appear in the set after `WHERE`. If the input set is empty, there are no groups and the query returns no rows.

```sql
SELECT
    category,
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    SUM(amount) AS total_amount
FROM payment_sample
WHERE category = 'C'
GROUP BY category;
```

The result has zero rows. This differs from an aggregate without `GROUP BY`, which returns one row with `COUNT(*) = 0`.

### 5.1. Groups with NULL Values

`GROUP BY` groups together `NULL` values of the same expression into one group:

```sql
SELECT
    category,
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    SUM(amount) AS total_amount
FROM payment_sample
GROUP BY category;
```

The result has three groups: `A`, `B`, and `NULL`. The `NULL` group has two rows, one amount of 5.00 and one amount of `NULL`, so `COUNT(*) = 2`, `COUNT(amount) = 1`, and `SUM(amount) = 5.00`.

Grouping `NULL` together does not mean rows are considered equal in every comparison. `GROUP BY` grouping rules place `NULL` values into the same group, whereas `category = NULL` still evaluates to `UNKNOWN`. To filter for the null group, use `WHERE category IS NULL`.

## 6. COALESCE and IFNULL: When Should NULL Be Converted to 0?

`COALESCE()` returns the first non-`NULL` argument; `IFNULL()` takes two arguments and returns the second argument when the first is `NULL`.

```sql
SELECT
    SUM(amount) AS raw_total,
    COALESCE(SUM(amount), 0) AS displayed_total,
    IFNULL(AVG(amount), 0) AS displayed_average
FROM payment_sample
WHERE category = 'C';
```

`raw_total` and `AVG` evaluate to `NULL`; the two wrapped expressions return `0` for display. This is a presentation decision or business rule, not an inherent property of aggregation.

### 6.1. Do Not Lose Information About Data State

If you return only `COALESCE(SUM(amount), 0)`, the reader cannot tell whether the total is 0 because:

- There are no matching rows.
- There are rows, but every amount is `NULL`.
- There are valid amount values whose actual sum is 0.

You can return additional counters to preserve context:

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(amount) AS known_amount_count,
    SUM(amount) AS raw_total,
    COALESCE(SUM(amount), 0) AS total_for_display,
    CASE
        WHEN COUNT(*) = 0 THEN 'NO_ROWS'
        WHEN COUNT(amount) = 0 THEN 'ALL_VALUES_NULL'
        ELSE 'HAS_VALUES'
    END AS data_state
FROM payment_sample
WHERE category = 'B';
```

`COALESCE()` is appropriate when the report defines "no figures" as displaying 0. If users need to distinguish "no data" from "zero activity", keep `NULL` or return an explicit status.

### 6.2. AVG(amount) Differs from AVG(COALESCE(amount, 0))

The following two expressions have different denominators:

```sql
SELECT
    AVG(amount) AS average_known_values,
    AVG(COALESCE(amount, 0)) AS average_null_as_zero
FROM payment_sample
WHERE category = 'A';
```

For group A, `AVG(amount)` averages the known values (10 and 30), yielding 20. `AVG(COALESCE(amount, 0))` replaces the missing value with 0 before computing and divides by all three rows, yielding approximately 13.3333.

Only use the second form if business rules confirm that `NULL` truly means 0. If `NULL` means unrecorded, unknown, or not applicable, replacing it with 0 skews the statistics.

## 7. Conditional Aggregation

Conditional aggregation uses `CASE` inside an aggregate function to compute multiple metrics in a single grouping pass.

Example: count transactions by status/category:

```sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(CASE WHEN category = 'A' THEN 1 END) AS category_a_rows,
    COUNT(CASE WHEN category = 'B' THEN 1 END) AS category_b_rows,
    COUNT(CASE WHEN category IS NULL THEN 1 END) AS unclassified_rows
FROM payment_sample;
```

A `CASE` without an `ELSE` branch returns `NULL` when the condition does not match. `COUNT()` ignores `NULL` values, so each expression counts exactly the rows matching its condition.

### 7.1. Conditional Counting and Summing

```sql
SELECT
    COUNT(CASE WHEN category = 'A' THEN 1 END) AS a_row_count,
    COUNT(CASE WHEN category = 'B' THEN 1 END) AS b_row_count,
    SUM(CASE WHEN category = 'A' THEN amount ELSE 0 END) AS a_total_with_zero_else,
    COALESCE(SUM(CASE WHEN category = 'B' THEN amount END), 0) AS b_total_for_display
FROM payment_sample;
```

`COUNT(CASE ...)` returns 0 if no rows match. With `SUM(CASE WHEN ... THEN amount ELSE 0 END)`, non-matching rows contribute 0; if there are no input rows at all, `SUM()` still returns `NULL` because no expressions are summed. For group B, matching rows all have `NULL` amounts; `COALESCE()` converts the `NULL` sum to 0 for display.

If you need to distinguish "no category B transactions" from "category B transactions exist with unrecorded amounts", also compute `COUNT(CASE WHEN category = 'B' THEN 1 END)` and `COUNT(CASE WHEN category = 'B' THEN amount END)`.

### 7.2. Conditional Aggregation per Group

```sql
SELECT
    category,
    COUNT(*) AS row_count,
    COUNT(CASE WHEN amount >= 20 THEN 1 END) AS amount_at_least_20,
    SUM(CASE WHEN amount >= 20 THEN amount ELSE 0 END) AS sum_at_least_20
FROM payment_sample
GROUP BY category;
```

The condition `amount >= 20` evaluates to `UNKNOWN` when `amount` is `NULL`, so the `WHEN` branch is not taken and the `ELSE 0` branch is used. Without `ELSE`, `CASE` returns `NULL` for rows not meeting the condition; the choice depends on whether you want to ignore them or contribute 0.

## 8. HAVING and Groups with No Values

`WHERE` filters rows before grouping and aggregation; `HAVING` filters group results after aggregates are computed.

Example: keep only groups that have at least one recorded amount:

```sql
SELECT
    category,
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count,
    SUM(amount) AS total_amount
FROM payment_sample
GROUP BY category
HAVING COUNT(amount) > 0;
```

Group B is excluded because `COUNT(amount) = 0`, even though the group has two rows. Group A and the `NULL` group are retained.

If you want to find groups that have rows but all amount values are `NULL`:

```sql
SELECT
    category,
    COUNT(*) AS row_count,
    COUNT(amount) AS amount_count
FROM payment_sample
GROUP BY category
HAVING COUNT(*) > 0
   AND COUNT(amount) = 0;
```

You cannot use `WHERE SUM(amount) ...` to filter groups because aggregates are computed after the row-filtering step. Use `HAVING` for conditions that depend on aggregate results.

## 9. Aggregating Over LEFT JOIN and the COUNT(*) Trap

When using `LEFT JOIN`, a row in the left table without matching records still appears with `NULL` in all right-side columns. As a result, `COUNT(*)` counts the null-extended row, whereas `COUNT(child.primary_key)` counts only actual matching child rows.

```sql
CREATE TABLE customer_sample (
    customer_id BIGINT UNSIGNED NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

CREATE TABLE order_sample (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    amount DECIMAL(12, 2) NULL,
    PRIMARY KEY (order_id),
    KEY idx_order_sample_customer (customer_id)
) ENGINE=InnoDB;

INSERT INTO customer_sample VALUES
    (1, 'An'), (2, 'Binh'), (3, 'Chi');

INSERT INTO order_sample VALUES
    (101, 1, 100.00),
    (102, 1, NULL),
    (103, 2, 0.00);
```

Count orders per customer:

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(*) AS joined_rows,
    COUNT(o.order_id) AS order_count,
    COUNT(o.amount) AS known_amount_count,
    SUM(o.amount) AS total_amount
FROM customer_sample AS c
LEFT JOIN order_sample AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Notable results:

- Customer An has two orders: `COUNT(*) = 2`, `COUNT(o.order_id) = 2`, `COUNT(o.amount) = 1`, `SUM(o.amount) = 100.00`.
- Customer Binh has one order with amount 0: both row and order counts are 1, `COUNT(o.amount) = 1`, `SUM = 0.00`.
- Customer Chi has no orders: `LEFT JOIN` produces one null-extended row with `o.*` columns set to `NULL`; hence `COUNT(*) = 1`, whereas `COUNT(o.order_id) = 0`, `COUNT(o.amount) = 0`, and `SUM(o.amount) = NULL`.

If the report needs the order count, use `COUNT(o.order_id)` or a guaranteed `NOT NULL` child column—never `COUNT(*)` in a `LEFT JOIN` query like this.

### 9.1. When to COALESCE a LEFT JOIN Sum to 0?

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(o.amount), 0) AS total_for_display
FROM customer_sample AS c
LEFT JOIN order_sample AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id;
```

Customer Chi will have `order_count = 0` and `total_for_display = 0`. However, if a customer has orders where every `amount` is `NULL`, the total will also be displayed as 0. If you need to distinguish the two states, keep both `COUNT(o.order_id)` and `COUNT(o.amount)`.

## 10. GROUP_CONCAT and NULL Values

`GROUP_CONCAT()` concatenates non-`NULL` values within a group. It ignores `NULL` arguments; if a group has no non-`NULL` values, the result is `NULL`.

```sql
SELECT
    category,
    GROUP_CONCAT(note ORDER BY note SEPARATOR ', ') AS notes
FROM payment_sample
GROUP BY category;
```

Group B has one note `'not recorded'` and one `NULL` note, so the string contains only `'not recorded'`. If every note in a group is `NULL`, `notes` is `NULL`.

Result length is capped by `group_concat_max_len` (default is typically 1024 bytes). Check the current value:

```sql
SELECT @@SESSION.group_concat_max_len;
```

If the result is truncated, check warnings and consider adjusting the limit as needed while accounting for `max_allowed_packet` and memory. Do not assume `GROUP_CONCAT()` always returns unbounded full content.

## 11. NULL in Aggregate Expressions and Arithmetic

### 11.1. Division by Zero and Missing Denominators

To compute a ratio, choose a meaningful denominator and handle the case where the denominator is 0:

```sql
SELECT
    SUM(amount) / NULLIF(COUNT(amount), 0) AS average_amount
FROM payment_sample
WHERE category = 'B';
```

`NULLIF(COUNT(amount), 0)` returns `NULL` when there are no amount values. The division then returns `NULL` instead of dividing by zero. For a simple average, `AVG(amount)` is usually clearer; this example illustrates protecting the denominator in ratio expressions.

### 11.2. NULL in Addition Before Aggregation

```sql
SELECT SUM(amount + shipping_fee) AS total_with_shipping
FROM order_with_shipping;
```

If either operand is `NULL`, addition yields `NULL`; `SUM()` skips that row. If business rules treat an absent fee as 0, write it explicitly:

```sql
SELECT SUM(amount + COALESCE(shipping_fee, 0)) AS total_with_shipping
FROM order_with_shipping;
```

Use `COALESCE(shipping_fee, 0)` only if `NULL` genuinely means no shipping fee was incurred. If `NULL` means the fee has not been calculated yet, substituting 0 can make the report inaccurate.

## 12. Empty Sets in Subqueries and Existence Checks

A subquery returning zero rows has different semantics from an aggregate subquery:

- A scalar subquery returning no rows evaluates to `NULL`.
- A scalar subquery with an aggregate and no `GROUP BY` still returns one row; `COUNT(*)` may be 0 and `SUM()` may be `NULL`.
- `EXISTS (subquery)` returns FALSE if the subquery has no rows; `NOT EXISTS` returns TRUE.

Example:

```sql
SELECT
    (SELECT amount
     FROM payment_sample
     WHERE category = 'C'
     LIMIT 1) AS scalar_no_row,
    (SELECT COUNT(*)
     FROM payment_sample
     WHERE category = 'C') AS aggregate_count,
    EXISTS (
        SELECT 1
        FROM payment_sample
        WHERE category = 'C'
    ) AS has_category_c;
```

The results are `NULL`, `0`, and `0`, respectively. Use `EXISTS`/`NOT EXISTS` when the business question is "whether any row exists" instead of counting all rows when you do not need the count.

## 13. Common Pitfalls

| Symptom | Cause | Solution |
|---|---|---|
| `SUM()` returns `NULL` even though the query has rows | All values of the aggregated expression are `NULL` | Check `COUNT(*)` and `COUNT(expr)` to distinguish |
| `COUNT(*)` and `COUNT(column)` differ | `COUNT(*)` counts rows, `COUNT(column)` skips `NULL` | Choose the counter that matches the business question |
| Report shows 0 when there is no data | `COALESCE(SUM(...), 0)` conflates empty set and all-NULL | Return row count/value count or state as well |
| Unexpectedly low average | `AVG(COALESCE(value, 0))` treats missing rows as 0 | Only replace NULL with 0 when business rules require it |
| GROUP BY returns no rows when filtering an empty set | There are no groups to form | If one summary row is needed, omit GROUP BY or use a scalar aggregate |
| LEFT JOIN counts customers with no orders as 1 | Using `COUNT(*)` on the null-extended row of LEFT JOIN | Use `COUNT(child.primary_key)` |
| COUNT(DISTINCT col) is lower than visible DISTINCT values | `COUNT(DISTINCT)` ignores NULL, while `SELECT DISTINCT` can return one NULL | Decide whether NULL should be counted as a distinct value |
| GROUP_CONCAT is truncated | Exceeded `group_concat_max_len` | Check session settings and warnings; increase carefully if needed |

## 14. Process for Reading Aggregate Results

When an aggregate returns `NULL` or 0, inspect in order:

1. Check how many rows remain after `WHERE` using `COUNT(*)`.
2. Check how many non-`NULL` values the aggregate expression has using `COUNT(expr)`.
3. Check whether values are genuinely 0 or merely missing.
4. If `GROUP BY` is used, verify whether the group appears in the input set.
5. If `LEFT JOIN` is used, count the child table's primary key instead of counting all joined rows.
6. Check whether `CASE`, `COALESCE`, `IFNULL`, or arithmetic inside the aggregate changes `NULL` semantics.
7. Replace `NULL` with 0 at the reporting layer only when the business definition allows it.

A useful diagnostic query:

```sql
SELECT
    COUNT(*) AS input_rows,
    COUNT(amount) AS non_null_amounts,
    SUM(amount) AS raw_sum,
    AVG(amount) AS raw_average,
    MIN(amount) AS minimum_amount,
    MAX(amount) AS maximum_amount
FROM payment_sample
WHERE category = 'B';
```

The output shows that two input rows exist, yet there are no valid amounts to aggregate. This is a better diagnostic approach than wrapping `SUM()` in `COALESCE()` and ignoring the underlying cause.

## 15. Hands-on Exercises

Practice in your own lab database with `payment_sample`, `customer_sample`, and `order_sample`:

1. Compute `COUNT(*)`, `COUNT(amount)`, `SUM(amount)`, and `AVG(amount)` for categories A and B; explain the differences.
2. Filter for non-existent category C and observe that an aggregate without `GROUP BY` still returns one row.
3. Add `GROUP BY category` to the query above and confirm the result has no rows.
4. Run `SELECT DISTINCT category` and `COUNT(DISTINCT category)` to observe how each handles `NULL`.
5. Create a group that has rows where every amount is `NULL`; use `HAVING COUNT(*) > 0 AND COUNT(amount) = 0` to find that group.
6. Compare `AVG(amount)` with `AVG(COALESCE(amount, 0))`; explain the effect of the denominator.
7. Write conditional aggregation to count rows per category and conditionally sum amounts.
8. Use `LEFT JOIN` to count orders per customer; compare `COUNT(*)` with `COUNT(order_id)` for a customer with no orders.
9. Test `GROUP_CONCAT(note)` on a group with some `NULL` notes and a group with only `NULL` notes; check `group_concat_max_len`.
10. Compare an empty scalar subquery, an aggregate scalar subquery, and `EXISTS` on the same condition with no matching rows.
11. Design a report with three states: `NO_ROWS`, `ALL_VALUES_NULL`, and `HAS_VALUES`; return both row count and valid value count.
12. Write a brief business explanation of when a missing total amount must be shown as `NULL` and when it may be shown as 0.

You have completed this lesson when you can distinguish an empty set, an all-`NULL` group, and a true zero sum, and choose the right counting function and missing-value handling in reports.

## 16. Key Principles to Remember

- `COUNT(*)` counts rows; `COUNT(expr)` counts non-`NULL` values; `COUNT(DISTINCT expr)` counts unique non-`NULL` values.
- `SUM()`, `AVG()`, `MIN()`, and `MAX()` ignore `NULL`, returning `NULL` if there are no valid values.
- An aggregate without `GROUP BY` returns one row on an empty set; `COUNT()` is 0 while value aggregates are typically `NULL`.
- `GROUP BY` on an empty set forms no groups and returns no rows.
- `GROUP BY` puts `NULL` values into the same group; `WHERE col = NULL` is still incorrect—use `IS NULL`.
- Having rows where all aggregated values are `NULL` is different from having no rows; use both `COUNT(*)` and `COUNT(expr)` to tell them apart.
- `COALESCE(SUM(expr), 0)` is a display/business rule, not proof that the actual sum is 0.
- `AVG(COALESCE(expr, 0))` changes the denominator; use it only if NULL is defined as 0.
- `LEFT JOIN` produces null-extended rows; use `COUNT(child.primary_key)` to count child records that actually exist.
- `HAVING` filters groups after aggregation; `WHERE` filters rows before aggregation.
- `GROUP_CONCAT()` ignores NULL and can be truncated according to `group_concat_max_len`.
