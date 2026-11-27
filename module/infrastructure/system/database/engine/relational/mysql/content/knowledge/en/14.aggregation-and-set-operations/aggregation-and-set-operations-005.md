# Conditional Aggregation Using CASE or Boolean Expressions

In reporting, you often need multiple metrics over the same dataset: total orders, paid orders, pending orders, collected revenue, cancelled revenue, or the number of customers who made a purchase. Running a separate query for each metric forces the application to issue multiple SQL queries and risks each query observing a different data state. **Conditional aggregation** solves this by placing conditions inside aggregate functions, allowing multiple metrics to be computed in a single grouping pass.

In MySQL, the most common approach combines `CASE` with `SUM()`, `COUNT()`, `AVG()`, `MIN()`, `MAX()`, or `COUNT(DISTINCT ...)`. For simple conditions, MySQL boolean expressions can also be summed via `SUM(condition)`, since a condition typically evaluates to `1`, `0`, or `NULL`. However, you must understand SQL three-valued logic and handle `NULL` deliberately so you do not miscount.

## Learning Objectives

After this lesson, you will be able to:

- Explain conditional aggregation and why it is used to compute multiple metrics in a single query.
- Use `SUM(CASE WHEN ... THEN ... ELSE ... END)` for conditional totals.
- Use `COUNT(CASE WHEN ... THEN ... END)` and `COUNT(DISTINCT CASE ... END)` for conditional counting.
- Use boolean expressions inside `SUM()` according to MySQL boolean rules.
- Distinguish `ELSE 0` from `ELSE NULL`, as well as how `NULL` affects aggregate functions.
- Build pivot-style reports using multiple conditional aggregate expressions.
- Distinguish whole-source filtering in `WHERE` from metric-specific conditions.
- Combine conditional aggregation with `GROUP BY`, `HAVING`, `LEFT JOIN`, and percentages.

## 1. Practice Data

The examples use an order table grouped by region. Run this in a sandbox database:

```sql
CREATE TABLE sales_region (
    region_id INT NOT NULL,
    region_name VARCHAR(40) NOT NULL,
    PRIMARY KEY (region_id),
    UNIQUE KEY uq_sales_region_name (region_name)
) ENGINE = InnoDB;

CREATE TABLE sales_order_agg (
    order_id BIGINT UNSIGNED NOT NULL,
    region_id INT NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    sales_rep VARCHAR(80) NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    order_date DATE NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_sales_order_agg_region_date (region_id, order_date),
    KEY idx_sales_order_agg_customer (customer_id),
    CONSTRAINT fk_sales_order_agg_region
        FOREIGN KEY (region_id)
        REFERENCES sales_region (region_id)
) ENGINE = InnoDB;

INSERT INTO sales_region (region_id, region_name)
VALUES
    (1, 'North'),
    (2, 'South'),
    (3, 'West'),
    (4, 'East');

INSERT INTO sales_order_agg
    (order_id, region_id, customer_id, sales_rep,
     order_status, order_date, amount)
VALUES
    (101, 1, 1001, 'An',   'PAID',      '2025-01-02', 120.00),
    (102, 1, 1002, 'Binh', 'PENDING',   '2025-01-03',  80.00),
    (103, 1, 1001, 'An',   'CANCELLED', '2025-01-04',  50.00),
    (104, 2, 1003, 'Chi',  'PAID',      '2025-01-02', 200.00),
    (105, 2, 1004, 'Dung', 'PAID',      '2025-01-05', 150.00),
    (106, 2, 1003, 'Chi',  'REFUNDED',  '2025-01-06', 200.00),
    (107, 1, 1005, 'An',   'PAID',      '2025-02-01', 300.00),
    (108, 3, 1006, 'Hoa',  'PENDING',   '2025-02-02',  60.00),
    (109, 3, 1006, 'Hoa',  'PAID',      '2025-02-03',  90.00),
    (110, 3, 1007, 'Lam',  'CANCELLED', '2025-02-04',  40.00);
```

The `East` region has no orders yet. This scenario will be used to illustrate retaining empty groups when reporting through a `LEFT JOIN`. The `amount` column uses `DECIMAL` so monetary examples do not rely on floating-point numbers.

Inspect the data:

```sql
SELECT
    order_id,
    region_id,
    customer_id,
    order_status,
    order_date,
    amount
FROM sales_order_agg
ORDER BY order_id;
```

## 2. What Is Conditional Aggregation?

Normally, an aggregate function processes every row in a group:

```sql
SELECT
    region_id,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM sales_order_agg
GROUP BY region_id;
```

If you need to calculate metrics only for paid orders, you can place a condition inside the aggregate function's expression:

```sql
SELECT
    region_id,
    COUNT(CASE WHEN order_status = 'PAID' THEN 1 END) AS paid_order_count,
    SUM(CASE
            WHEN order_status = 'PAID' THEN amount
            ELSE 0
        END) AS paid_amount
FROM sales_order_agg
GROUP BY region_id;
```

Every row still participates in grouping by `region_id`, but only rows satisfying the condition contribute to the paid metrics. Other rows contribute `NULL` for counting or `0` for summing.

The strength of this approach is computing multiple metrics side by side:

```sql
SELECT
    region_id,
    COUNT(*) AS all_orders,
    COUNT(CASE WHEN order_status = 'PAID' THEN 1 END) AS paid_orders,
    COUNT(CASE WHEN order_status = 'PENDING' THEN 1 END) AS pending_orders,
    COUNT(CASE WHEN order_status = 'CANCELLED' THEN 1 END) AS cancelled_orders,
    SUM(CASE WHEN order_status = 'PAID' THEN amount ELSE 0 END) AS paid_amount,
    SUM(CASE WHEN order_status = 'PENDING' THEN amount ELSE 0 END) AS pending_amount
FROM sales_order_agg
GROUP BY region_id
ORDER BY region_id;
```

The query only needs to read the source row set once under the chosen execution plan, then evaluate the aggregate expressions per group. The optimizer still decides how to read the data and perform grouping; this should not be interpreted as a guarantee that every expression is always evaluated in a single physical scan.

## 3. CASE Inside Aggregate Functions

MySQL supports two forms of `CASE`:

**Searched CASE** evaluates conditions sequentially:

```sql
CASE
    WHEN condition_1 THEN result_1
    WHEN condition_2 THEN result_2
    ELSE default_result
END
```

**Simple CASE** compares one expression against values:

```sql
CASE expression
    WHEN value_1 THEN result_1
    WHEN value_2 THEN result_2
    ELSE default_result
END
```

In conditional aggregation, searched CASE is usually more flexible because conditions can combine multiple columns and logical operators.

### 3.1. CASE Inside SUM

General pattern:

```sql
SUM(
    CASE
        WHEN condition THEN numeric_value
        ELSE 0
    END
)
```

Example: calculate revenue from paid orders:

```sql
SELECT
    region_id,
    SUM(
        CASE
            WHEN order_status = 'PAID' THEN amount
            ELSE 0
        END
    ) AS paid_revenue
FROM sales_order_agg
GROUP BY region_id;
```

For each row, CASE returns `amount` if the order is paid and `0` otherwise. `SUM()` adds those values within each group.

If you need sums for multiple conditions, each metric uses its own CASE:

```sql
SELECT
    region_id,
    SUM(CASE WHEN order_status = 'PAID' THEN amount ELSE 0 END) AS paid_revenue,
    SUM(CASE WHEN order_status = 'REFUNDED' THEN amount ELSE 0 END) AS refunded_amount,
    SUM(CASE WHEN order_status = 'CANCELLED' THEN amount ELSE 0 END) AS cancelled_amount
FROM sales_order_agg
GROUP BY region_id;
```

### 3.2. CASE Inside COUNT

`COUNT(expression)` counts only non-`NULL` values. Therefore, the conditional counting pattern typically returns a non-null value when the condition is true and ignores the rest:

```sql
COUNT(CASE WHEN condition THEN 1 END)
```

Example:

```sql
SELECT
    region_id,
    COUNT(CASE WHEN order_status = 'PAID' THEN order_id END) AS paid_orders,
    COUNT(CASE WHEN order_status = 'PENDING' THEN order_id END) AS pending_orders
FROM sales_order_agg
GROUP BY region_id;
```

Do not write `ELSE 0` in this counting expression. If you add `ELSE 0`, every row produces a non-null value and `COUNT()` will count rows that do not satisfy the condition:

```sql
-- Wrong if the goal is to count only PAID orders:
COUNT(CASE WHEN order_status = 'PAID' THEN 1 ELSE 0 END)
```

The expression above counts all rows because both `1` and `0` are non-`NULL`. Use `COUNT(CASE WHEN ... THEN 1 END)` or `SUM(CASE WHEN ... THEN 1 ELSE 0 END)`.

### 3.3. CASE Inside AVG

To compute an average over rows satisfying a condition, return the value to average when true and `NULL` when false:

```sql
SELECT
    region_id,
    AVG(CASE
            WHEN order_status = 'PAID' THEN amount
        END) AS average_paid_order
FROM sales_order_agg
GROUP BY region_id;
```

`AVG()` ignores `NULL`, so only paid orders enter both the numerator and the denominator. If you write `ELSE 0`, non-matching rows enter the denominator with a value of 0 and pull the average down; that result carries a different meaning.

## 4. CASE Combined with Logical Expressions

CASE conditions can use `AND`, `OR`, `NOT`, numeric comparisons, value ranges, or null checks. For example, count paid orders with amount at least 150:

```sql
SELECT
    region_id,
    COUNT(
        CASE
            WHEN order_status = 'PAID' AND amount >= 150
            THEN order_id
        END
    ) AS large_paid_orders
FROM sales_order_agg
GROUP BY region_id;
```

To calculate the amount of orders in paid or refunded status:

```sql
SELECT
    region_id,
    SUM(
        CASE
            WHEN order_status IN ('PAID', 'REFUNDED')
            THEN amount
            ELSE 0
        END
    ) AS settled_or_refunded_amount
FROM sales_order_agg
GROUP BY region_id;
```

When combining `AND` and `OR`, add parentheses to make the intended logic explicit:

```sql
CASE
    WHEN order_status = 'PAID'
         AND (amount >= 200 OR region_id = 1)
    THEN amount
    ELSE 0
END
```

Do not rely on readers remembering operator precedence. Parentheses make conditions easy to review and less likely to break when new criteria are added.

## 5. Using Boolean Expressions Directly Inside SUM

In MySQL, conditional expressions can be converted to numeric values in numeric context:

- A true condition returns `1`.
- A false condition returns `0`.
- An unknown condition due to `NULL` returns `NULL`.

Therefore, with `order_status` declared `NOT NULL`, you can write:

```sql
SELECT
    region_id,
    SUM(order_status = 'PAID') AS paid_orders,
    SUM(order_status = 'PENDING') AS pending_orders,
    SUM(order_status = 'CANCELLED') AS cancelled_orders
FROM sales_order_agg
GROUP BY region_id;
```

This is a concise MySQL-specific shorthand. It produces the same counts as:

```sql
SUM(CASE WHEN order_status = 'PAID' THEN 1 ELSE 0 END)
```

### 5.1. When to Use CASE Instead of SUM(condition)?

Boolean expressions are concise for counting simple conditions on non-nullable columns. CASE expresses intent more clearly when:

- You need to sum a different value per row.
- You need multiple classification branches.
- The condition can evaluate to `UNKNOWN` due to nullable columns.
- You want to state an explicit default value for non-matching rows.
- You want SQL that is easily portable across database systems.

Example with a nullable status column:

```sql
SELECT
    SUM(order_status = 'PAID') AS paid_count_using_boolean,
    SUM(CASE
            WHEN order_status = 'PAID' THEN 1
            ELSE 0
        END) AS paid_count_explicit
FROM some_legacy_orders;
```

If `order_status` is `NULL`, `order_status = 'PAID'` evaluates to `NULL`. `SUM()` skips that null value. CASE enters the WHEN branch only when the condition is TRUE; both FALSE and UNKNOWN go to ELSE and return 0. Both forms yield the same count in this example, but CASE makes explicit that every non-matching row contributes 0.

### 5.2. Do Not Confuse SUM(condition) with COUNT(condition)

`COUNT(expression)` counts every non-null value. A false condition usually evaluates to 0, and 0 is not null:

```sql
SELECT
    COUNT(order_status = 'PAID') AS count_of_non_null_predicates,
    SUM(order_status = 'PAID') AS number_of_paid_orders
FROM sales_order_agg;
```

Because `order_status` is `NOT NULL`, `COUNT(order_status = 'PAID')` counts all orders, not just paid orders. Use `SUM(condition)` or `COUNT(CASE WHEN condition THEN 1 END)` to count rows matching the condition.

## 6. COUNT(IF(...)) and COUNT(DISTINCT CASE ...)

MySQL provides `IF(condition, value_if_true, value_if_false)`. You can use it with `COUNT()`:

```sql
SELECT
    region_id,
    COUNT(IF(order_status = 'PAID', order_id, NULL)) AS paid_order_count
FROM sales_order_agg
GROUP BY region_id;
```

When the condition is true, IF returns `order_id`; when false, it returns `NULL`. COUNT counts only non-null values. This is concise, though `IF()` is MySQL-specific; `CASE` is standard SQL and easier to read and port across engines.

Count the number of distinct customers who have at least one paid order:

```sql
SELECT
    region_id,
    COUNT(
        DISTINCT CASE
            WHEN order_status = 'PAID' THEN customer_id
        END
    ) AS paid_customers
FROM sales_order_agg
GROUP BY region_id;
```

Non-`PAID` rows produce `NULL`; `COUNT(DISTINCT ...)` ignores null and counts each unique customer ID once. This is useful when a customer has multiple orders and you want to count only customers participating in a specific status.

Do not write `COUNT(DISTINCT customer_id)` when the goal is counting only customers with PAID orders: that counts customers across all statuses in the source set.

## 7. Computing Multiple Metrics in a Single GROUP BY

A regional report can simultaneously compute counts, revenue, average order value, and unique customers by status:

```sql
SELECT
    r.region_name,
    COUNT(o.order_id) AS all_orders,
    COUNT(CASE WHEN o.order_status = 'PAID' THEN o.order_id END) AS paid_orders,
    COUNT(CASE WHEN o.order_status = 'PENDING' THEN o.order_id END) AS pending_orders,
    COUNT(CASE WHEN o.order_status = 'CANCELLED' THEN o.order_id END) AS cancelled_orders,
    SUM(CASE WHEN o.order_status = 'PAID' THEN o.amount ELSE 0 END) AS paid_revenue,
    AVG(CASE WHEN o.order_status = 'PAID' THEN o.amount END) AS average_paid_order,
    COUNT(DISTINCT CASE
        WHEN o.order_status = 'PAID' THEN o.customer_id
    END) AS paid_customers
FROM sales_region AS r
LEFT JOIN sales_order_agg AS o
    ON o.region_id = r.region_id
GROUP BY r.region_id, r.region_name
ORDER BY r.region_id;
```

The result has one row per region, including `East`, which has no orders yet. For a region with no orders:

- `COUNT(o.order_id)` returns 0 because the order side is a null-extended row.
- The CASE expressions for counts and revenue return 0 or contribute no values.
- `AVG(...)` returns `NULL` because there are no PAID orders to average.
- `COUNT(DISTINCT ...)` returns 0.

The difference between 0 and `NULL` here is meaningful: cumulative revenue with no orders can be reported as 0, whereas an average with no samples to compute is `NULL`. If the UI needs to show 0 for the average, decide explicitly at the reporting layer with `COALESCE()`, rather than assuming both states mean the same thing.

### 7.1. Placing Date Filters Correctly with LEFT JOIN

If you want to report on a date range while keeping regions that had no orders in that period, place the date condition in the `ON` clause:

```sql
SELECT
    r.region_name,
    COUNT(o.order_id) AS order_count,
    SUM(CASE WHEN o.order_status = 'PAID' THEN o.amount ELSE 0 END) AS paid_revenue
FROM sales_region AS r
LEFT JOIN sales_order_agg AS o
    ON o.region_id = r.region_id
   AND o.order_date >= '2025-01-01'
   AND o.order_date <  '2025-02-01'
GROUP BY r.region_id, r.region_name
ORDER BY r.region_id;
```

If you move the two date conditions on table `o` down into `WHERE`, rows without orders have `o.order_date = NULL` and get filtered out; the result loses regions without orders and defeats the row-preserving behavior of LEFT JOIN.

## 8. WHERE Filters the Source, CASE Filters Each Metric

This is an important design decision when writing reports. `WHERE` removes rows from the entire aggregation; conditions inside CASE only control whether a row contributes to a specific aggregate expression.

For example, a report wants to count PAID, PENDING, and CANCELLED orders in January:

```sql
SELECT
    region_id,
    COUNT(*) AS all_orders,
    SUM(CASE WHEN order_status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders,
    SUM(CASE WHEN order_status = 'PENDING' THEN 1 ELSE 0 END) AS pending_orders,
    SUM(CASE WHEN order_status = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled_orders
FROM sales_order_agg
WHERE order_date >= '2025-01-01'
  AND order_date <  '2025-02-01'
GROUP BY region_id;
```

The date condition goes in WHERE because every metric covers only January. The status conditions go inside each CASE because each metric needs a different subset of the remaining rows.

If you wrote:

```sql
WHERE order_status = 'PAID'
```

then PENDING and CANCELLED orders would be removed from the source before grouping. The PENDING and CANCELLED count columns in the select list would always be 0; the query could no longer report those statuses together.

Rule of thumb:

- Put conditions that restrict the shared source across all metrics in `WHERE`.
- Put conditions that apply to a single metric or subset of metrics inside `CASE`.
- Put group-level filtering conditions based on computed aggregates in `HAVING`.

## 9. Classifying with CASE Before Grouping

CASE is not only for inside SUM/COUNT. It can also classify each row into a business category, and then use that classification in GROUP BY.

Example: split orders into three value tiers:

```sql
WITH classified_orders AS (
    SELECT
        order_id,
        region_id,
        amount,
        CASE
            WHEN amount >= 200 THEN 'HIGH'
            WHEN amount >= 100 THEN 'MEDIUM'
            ELSE 'LOW'
        END AS amount_band
    FROM sales_order_agg
)
SELECT
    region_id,
    amount_band,
    COUNT(*) AS order_count,
    SUM(amount) AS band_amount
FROM classified_orders
GROUP BY region_id, amount_band
ORDER BY region_id, amount_band;
```

CASE is evaluated top to bottom; the first matching WHEN branch determines the result. Thus, condition order matters. If you put `amount >= 100` before `amount >= 200`, rows with amount 200 or more are placed into MEDIUM and never reach the HIGH branch.

The buckets in this example are mutually exclusive because CASE picks the first matching branch. If you write separate conditional aggregates, metrics can intentionally overlap—for instance, counting all PAID orders while also counting the high-value PAID subset. Be clear about whether metrics are mutually exclusive categories or independent filtered sets.

## 10. Creating Pivot-Style Reports with Conditional Aggregation

Pivoting turns categorical values into columns. MySQL does not have a dedicated `PIVOT` syntax like some other database engines, but you can produce report columns using conditional aggregate functions.

For example, one row per region and one column per status:

```sql
SELECT
    r.region_name,
    SUM(CASE WHEN o.order_status = 'PAID' THEN 1 ELSE 0 END) AS paid_count,
    SUM(CASE WHEN o.order_status = 'PENDING' THEN 1 ELSE 0 END) AS pending_count,
    SUM(CASE WHEN o.order_status = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled_count,
    SUM(CASE WHEN o.order_status = 'REFUNDED' THEN 1 ELSE 0 END) AS refunded_count
FROM sales_region AS r
LEFT JOIN sales_order_agg AS o
    ON o.region_id = r.region_id
GROUP BY r.region_id, r.region_name
ORDER BY r.region_id;
```

Each CASE expression produces one column. If a new status is added, the report must be updated to include a corresponding column. When the set of categories changes frequently or is unknown in advance, consider returning row-based results `(region, status, count)` and letting the application layer pivot dynamically.

## 11. Computing Conditional Ratios and Percentages

Conditional aggregation is frequently used to compute conversion rates, paid order rates, or revenue shares.

Example: ratio of PAID orders to total orders by region:

```sql
SELECT
    region_id,
    COUNT(*) AS all_orders,
    SUM(CASE WHEN order_status = 'PAID' THEN 1 ELSE 0 END) AS paid_orders,
    ROUND(
        100.0 * SUM(CASE WHEN order_status = 'PAID' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_rate_percent
FROM sales_order_agg
GROUP BY region_id;
```

`NULLIF(denominator, 0)` returns `NULL` when the denominator is 0, avoiding division-by-zero errors. In a grouped query with at least one row per group, `COUNT(*)` is not 0, but this pattern is helpful when formulas are reused in complex queries or combined with dimension tables that may have no matching data.

Always confirm the denominator matches the business definition. The ratio of PAID over all orders differs from PAID over processed orders (excluding PENDING), and differs from PAID per customer. Do not change the denominator without clearly stating the metric definition.

Example: share of PAID revenue out of total order amount:

```sql
SELECT
    region_id,
    SUM(CASE WHEN order_status = 'PAID' THEN amount ELSE 0 END) AS paid_amount,
    SUM(amount) AS all_amount,
    ROUND(
        100.0 * SUM(CASE WHEN order_status = 'PAID' THEN amount ELSE 0 END)
        / NULLIF(SUM(amount), 0),
        2
    ) AS paid_amount_share_percent
FROM sales_order_agg
GROUP BY region_id;
```

If `amount` can be negative (e.g., adjustment entries) or refunds are stored as negative amounts, redefine how revenue and the denominator are computed. Do not infer accounting semantics solely from column names.

## 12. NULL and ELSE in Conditional Aggregation

SQL uses three-valued logic: TRUE, FALSE, and UNKNOWN. Comparisons with `NULL` usually evaluate to UNKNOWN. In CASE, only a TRUE condition selects a WHEN branch; FALSE and UNKNOWN continue to the next branch or ELSE.

These three expressions have different meanings:

```sql
CASE WHEN condition THEN amount ELSE 0 END

CASE WHEN condition THEN amount ELSE NULL END

CASE WHEN condition THEN amount END
```

The last two expressions are equivalent because a CASE without ELSE defaults to returning `NULL`.

### 12.1. ELSE 0 When Non-Matching Rows Should Contribute Zero to a Sum

```sql
SUM(CASE WHEN order_status = 'PAID' THEN amount ELSE 0 END)
```

Non-PAID rows contribute 0. If a group has rows but no PAID orders, the conditional sum is 0. This is typically appropriate for cumulative revenue metrics that should show 0 when no matching transactions exist.

### 12.2. ELSE NULL When Non-Matching Rows Should Be Excluded from Aggregation

```sql
AVG(CASE WHEN order_status = 'PAID' THEN amount END)
```

Non-PAID rows return NULL and are ignored by AVG. This is appropriate when computing the average solely over PAID orders. Using ELSE 0 instead would include non-PAID rows in the denominator and drag the average down.

### 12.3. Aggregating Over an Empty Source Set

For an aggregate query without GROUP BY, MySQL still returns one result row. `COUNT(*)` returns 0, while `SUM(...)` returns NULL if there are no input rows:

```sql
SELECT
    COUNT(*) AS row_count,
    SUM(CASE WHEN order_status = 'PAID' THEN amount ELSE 0 END) AS paid_amount
FROM sales_order_agg
WHERE order_date >= '2030-01-01'
  AND order_date <  '2030-02-01';
```

If the UI requires the total to always be 0 when the source is empty, wrap the result with `COALESCE()`:

```sql
SELECT
    COUNT(*) AS row_count,
    COALESCE(
        SUM(CASE WHEN order_status = 'PAID' THEN amount ELSE 0 END),
        0
    ) AS paid_amount
FROM sales_order_agg
WHERE order_date >= '2030-01-01'
  AND order_date <  '2030-02-01';
```

Do not apply COALESCE automatically to every metric. The average of an empty set should usually remain NULL because there are no samples to compute; total revenue may be defined by convention to display 0.

## 13. Conditional Aggregation with DISTINCT and Multiple Conditions

Count distinct customers who have a PAID order of at least 100:

```sql
SELECT
    region_id,
    COUNT(DISTINCT CASE
        WHEN order_status = 'PAID' AND amount >= 100
        THEN customer_id
    END) AS high_value_paid_customers
FROM sales_order_agg
GROUP BY region_id;
```

Counting customers who have both PAID and PENDING orders can be done by computing two separate flags and filtering groups in an outer query or using a grouping expression:

```sql
SELECT
    region_id,
    COUNT(DISTINCT CASE WHEN order_status = 'PAID' THEN customer_id END) AS paid_customers,
    COUNT(DISTINCT CASE WHEN order_status = 'PENDING' THEN customer_id END) AS pending_customers
FROM sales_order_agg
GROUP BY region_id;
```

If you need to count customers belonging to both sets, place the intermediate aggregation in a CTE:

```sql
WITH customer_status_by_region AS (
    SELECT
        region_id,
        customer_id,
        MAX(order_status = 'PAID') AS has_paid,
        MAX(order_status = 'PENDING') AS has_pending
    FROM sales_order_agg
    GROUP BY region_id, customer_id
)
SELECT
    region_id,
    COUNT(CASE WHEN has_paid = 1 AND has_pending = 1 THEN customer_id END)
        AS customers_with_both_statuses
FROM customer_status_by_region
GROUP BY region_id;
```

In MySQL, boolean expressions return 1 or 0 in our sample data where status is NOT NULL; MAX over the group indicates whether at least one row satisfies the condition. If the status column is nullable, consider using an explicit CASE to control UNKNOWN.

## 14. Conditional Aggregation and HAVING

`HAVING` filters groups after metrics are computed. For example, retrieve only regions with at least two PAID orders:

```sql
SELECT
    region_id,
    COUNT(CASE WHEN order_status = 'PAID' THEN order_id END) AS paid_orders,
    SUM(CASE WHEN order_status = 'PAID' THEN amount ELSE 0 END) AS paid_revenue
FROM sales_order_agg
GROUP BY region_id
HAVING COUNT(CASE WHEN order_status = 'PAID' THEN order_id END) >= 2
ORDER BY paid_revenue DESC;
```

In MySQL, you can reference aliases in HAVING:

```sql
SELECT
    region_id,
    COUNT(CASE WHEN order_status = 'PAID' THEN order_id END) AS paid_orders
FROM sales_order_agg
GROUP BY region_id
HAVING paid_orders >= 2;
```

For clarity and portability across other database systems, you can also use a derived table or CTE and filter in the outer query. Do not put aggregate conditions into WHERE at the same level because WHERE is applied before groups are formed.

## 15. Common Mistakes When Writing Conditional Aggregation

- Using `COUNT(CASE WHEN condition THEN 1 ELSE 0 END)` and accidentally counting every row.
- Using `COUNT(condition)` with a boolean expression; false conditions return 0 and are still counted.
- Using `SUM(condition)` and forgetting the condition can return NULL when source data is nullable.
- Using `ELSE 0` inside AVG and accidentally pulling non-matching rows into the denominator.
- Using `ELSE NULL` for SUM and being surprised when a group with no matching values produces NULL.
- Putting a status condition in WHERE so other status metrics have no data left to compute.
- Writing multiple CASE expressions with overlapping conditions while assuming they are mutually exclusive.
- Ordering WHEN branches improperly in classification CASE expressions; a broader branch placed first can shadow a narrower branch.
- Using COUNT(DISTINCT customer_id) instead of COUNT(DISTINCT CASE WHEN ... THEN customer_id END), counting customers across all statuses.
- Moving a right-table condition into WHERE after a LEFT JOIN, dropping groups with no matching rows.
- Using SUM(amount) to report revenue without defining which statuses count as revenue.
- Using the wrong denominator for the business definition when computing ratios.
- Using IF() in queries requiring cross-database portability without considering CASE.

## 16. Checklist for Designing Conditional Reports

- Clearly defined each metric: row count, distinct entity count, sum, average, or ratio.
- Identified the shared source set and individual conditions per metric.
- Placed shared conditions in WHERE and metric-specific conditions in CASE.
- Chosen COUNT(CASE...), SUM(CASE...), or SUM(condition) matching the data types and NULL semantics.
- Used ELSE 0 for counts/sums that should return 0 when no rows match; used NULL when rows must be excluded from AVG or other aggregates.
- Checked whether condition columns allow NULL and handled UNKNOWN intentionally.
- Checked whether CASE conditions overlap or must be mutually exclusive.
- Used COUNT(DISTINCT CASE...) when conditionally counting distinct entities.
- Retained empty groups via LEFT JOIN and placed right-table filters in ON when appropriate.
- Defined the correct denominator and division-by-zero rule for ratio metrics.
- Tested results on groups with data, groups with no matching rows, and completely empty sources.
- Used HAVING instead of WHERE to filter groups when conditions depend on aggregate results.

Conditional aggregation lets you compute multiple metrics over the same dataset by placing conditions inside aggregate functions. CASE is clear and flexible; boolean expressions inside SUM offer a concise MySQL-specific shorthand. Choosing appropriately between COUNT and SUM, handling ELSE and NULL deliberately, and separating shared filters in WHERE from per-metric conditions will keep reports accurate, maintainable, and free from sending many separate queries.
