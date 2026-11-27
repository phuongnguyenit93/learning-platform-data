# Writing a Revenue Report with Subtotals, Rankings, and Period-over-Period Comparisons

A revenue report often needs to answer multiple questions in a single result set: what is the revenue per region or sales rep, what is the total for each month, which unit ranks highest, and how do results change compared to the previous month or the same period last year. Oracle SQL can perform these aggregations using `GROUP BY`, `ROLLUP`, `GROUPING SETS`, and analytic functions such as `RANK`, `DENSE_RANK`, `ROW_NUMBER`, and `LAG`.

The key when combining these techniques is determining the right data grain. Aggregate revenue at the reporting grain first, and only then rank or compare across time. Subtotals must be clearly identified so they are not ranked alongside business units. When comparing month over month, generate all periods including months with zero transactions so that the preceding row is genuinely the preceding calendar month.

## 1. Defining Revenue Calculation Rules

Before writing SQL, agree on the definition of revenue. The same transaction tables can yield different numbers depending on recognition rules.

The lab example uses a simple model:

| Table | Key Columns | Role |
|---|---|---|
| `SALES_ORDER` | `ORDER_ID`, `ORDER_DATE`, `STATUS`, `REGION_ID`, `CURRENCY_CODE` | Order header and recognition timestamp |
| `SALES_ORDER_LINE` | `ORDER_ID`, `LINE_NO`, `PRODUCT_ID`, `QUANTITY`, `UNIT_PRICE`, `DISCOUNT_AMOUNT` | Value of each line item |
| `SALES_REGION` | `REGION_ID`, `REGION_NAME` | Sales region lookup |

Assumptions for the examples:

- Only include orders with `STATUS = 'COMPLETED'`.
- `ORDER_DATE` is the revenue recognition date in the report.
- `DISCOUNT_AMOUNT` is the monetary discount for the entire line item, not a percentage.
- Line revenue = quantity × unit price − discount amount.
- The examples exclude tax, shipping fees, refunds, or post-sale adjustments.
- Each report aggregates a single currency; if multiple currencies exist, group by currency or convert using an approved exchange rate.

Formula:

[
\text{Revenue} = \sum (\text{QUANTITY} \times \text{UNIT\_PRICE} - \text{DISCOUNT\_AMOUNT})
\]

Do not simply take `SUM(UNIT_PRICE)` because each line can have a quantity greater than one and a discount. Likewise, do not calculate revenue on the header table and then join directly to the line table if the header amount already holds the order total: joining can multiply the header value by the number of detail lines.

### 1.1. Checking Data Grain and Join Relationships

Common relationships:

```text
SALES_ORDER 1 ----- n SALES_ORDER_LINE
      |
      +----- 1 SALES_REGION
```

One order has many line items, but belongs to only one region in this model. If you join additional tables such as promotions, payments, or status history that have multiple rows per order, aggregate those tables first or select the exact row needed. Otherwise, revenue may be double-counted.

### 1.2. Choosing the Recognition Date

`ORDER_DATE` in the example is the revenue recognition date. Real-world systems may need to use invoice date, shipment date, service completion date, or accounting posting date. Choose the right date column according to financial policy.

If the column is `TIMESTAMP WITH TIME ZONE`, standardize the reporting time zone before grouping by day or month. A transaction near midnight can fall into a different month when converted from UTC to local time. Do not strip time zone information before confirming business rules.

## 2. Calculating Basic Revenue with GROUP BY

First, calculate revenue by region:

```sql
SELECT r.region_id,
       r.region_name,
       SUM(
         l.quantity * l.unit_price
         - NVL(l.discount_amount, 0)
       ) AS revenue
FROM sales_order o
JOIN sales_order_line l
  ON l.order_id = o.order_id
JOIN sales_region r
  ON r.region_id = o.region_id
WHERE o.status = 'COMPLETED'
GROUP BY r.region_id, r.region_name
ORDER BY revenue DESC, r.region_id;
```

`NVL(l.discount_amount, 0)` treats a null discount as 0. If `DISCOUNT_AMOUNT` can be negative or data can be invalid, enforce business constraints instead of letting the formula silently mask bad data.

To calculate by month and region, add the month expression to both the select list and `GROUP BY`:

```sql
SELECT TRUNC(o.order_date, 'MM') AS month_start,
       r.region_id,
       r.region_name,
       SUM(
         l.quantity * l.unit_price
         - NVL(l.discount_amount, 0)
       ) AS revenue
FROM sales_order o
JOIN sales_order_line l
  ON l.order_id = o.order_id
JOIN sales_region r
  ON r.region_id = o.region_id
WHERE o.status = 'COMPLETED'
  AND o.order_date >= DATE '2026-01-01'
  AND o.order_date <  DATE '2027-01-01'
GROUP BY TRUNC(o.order_date, 'MM'),
         r.region_id,
         r.region_name
ORDER BY month_start, revenue DESC, r.region_id;
```

`TRUNC(date_value, 'MM')` truncates a date to the first day of the month. Use a half-open date range `>= start` and `< end` to include every timestamp on the final day, even when the column stores a time component. Filtering directly on the date column is also generally friendlier to indexes and partition pruning than predicates like `TRUNC(order_date) = ...`.

## 3. Creating Subtotals with ROLLUP and GROUPING SETS

### 3.1. ROLLUP by Month and Region

`ROLLUP` produces aggregation levels from detail up to subtotals and the grand total. With `ROLLUP(month_start, (region_id, region_name))`, Oracle generates groups equivalent to:

1. Each month and region pair.
2. The total across all regions within each month.
3. The grand total across all months.

Example:

```sql
WITH sales_by_region AS (
  SELECT TRUNC(o.order_date, 'MM') AS month_start,
         r.region_id,
         r.region_name,
         SUM(
           l.quantity * l.unit_price
           - NVL(l.discount_amount, 0)
         ) AS revenue
  FROM sales_order o
  JOIN sales_order_line l
    ON l.order_id = o.order_id
  JOIN sales_region r
    ON r.region_id = o.region_id
  WHERE o.status = 'COMPLETED'
    AND o.order_date >= DATE '2026-01-01'
    AND o.order_date <  DATE '2027-01-01'
  GROUP BY TRUNC(o.order_date, 'MM'),
           r.region_id,
           r.region_name
)
SELECT CASE
         WHEN GROUPING(month_start) = 1 THEN 'GRAND TOTAL'
         WHEN GROUPING(region_name) = 1 THEN 'MONTHLY TOTAL'
         ELSE 'REGION DETAIL'
       END AS row_type,
       month_start,
       region_name,
       SUM(revenue) AS revenue,
       GROUPING_ID(month_start, region_id, region_name) AS grouping_level
FROM sales_by_region
GROUP BY ROLLUP(month_start, (region_id, region_name))
ORDER BY month_start NULLS LAST,
         GROUPING(region_name),
         region_id;
```

The `GROUPING(column)` function returns 1 when the column has been rolled up out of the current grouping level to form a subtotal, and 0 when the column is part of a detail group. This is how you distinguish a subtotal row from a real data row that happens to contain `NULL`.

`GROUPING_ID(month_start, region_id, region_name)` encodes the grouping state of the passed columns. It is useful when a report has multiple aggregation levels or when the application needs to identify each row type.

Column order in `ROLLUP` matters. The syntax `ROLLUP(month_start, (region_id, region_name))` treats region ID and region name as a composite column group, producing month-region detail, monthly totals, and the grand total without producing an extra subtotal level for `region_id` alone. Reversing the order changes the generated grouping sets.

### 3.2. Using GROUPING SETS for Exact Aggregation Levels

`GROUPING SETS` lets you specify the exact groups to compute without having to take the entire `ROLLUP` hierarchy:

```sql
SELECT TRUNC(o.order_date, 'MM') AS month_start,
       r.region_name,
       SUM(
         l.quantity * l.unit_price
         - NVL(l.discount_amount, 0)
       ) AS revenue,
       GROUPING_ID(
         TRUNC(o.order_date, 'MM'),
         r.region_name
       ) AS grouping_level
FROM sales_order o
JOIN sales_order_line l
  ON l.order_id = o.order_id
JOIN sales_region r
  ON r.region_id = o.region_id
WHERE o.status = 'COMPLETED'
GROUP BY GROUPING SETS (
  (TRUNC(o.order_date, 'MM'), r.region_name),
  (TRUNC(o.order_date, 'MM')),
  ()
);
```

The groups in this example are month-region detail, monthly total, and grand total. If you need a separate total per region without a grand total, declare the corresponding grouping sets. `CUBE` generates every combination of groups and can produce more rows than the report needs; use it only when you genuinely need multi-dimensional cross-tab analysis across all combinations.

### 3.3. Labeling and Sorting Subtotals

Total rows normally contain `NULL` in rolled-up dimension columns. Do not rely solely on `NVL(region_name, 'TOTAL')` to identify totals because real data might contain a region with an unassigned name. Use `GROUPING` to distinguish them.

When rendering the report, you can use `CASE` to assign labels:

```sql
CASE
  WHEN GROUPING(region_name) = 1 THEN 'MONTHLY TOTAL'
  ELSE region_name
END
```

If the report includes a grand total, check `GROUPING(month_start)` before `GROUPING(region_name)` so the grand total row is identified accurately.

## 4. Ranking with Analytic Functions

Analytic functions perform calculations across a group of rows while preserving each individual row. For revenue reports, aggregate by month and region first, then rank regions within each month.

### 4.1. Distinguishing RANK, DENSE_RANK, and ROW_NUMBER

Suppose regional revenue in a given month is:

| Region | Revenue | RANK | DENSE_RANK | ROW_NUMBER |
|---|---:|---:|---:|---:|
| North | 500 | 1 | 1 | 1 |
| South | 420 | 2 | 2 | 2 |
| Central | 420 | 2 | 2 | 3 |
| West | 300 | 4 | 3 | 4 |

- `RANK()` assigns the same rank to ties and leaves gaps in subsequent ranks.
- `DENSE_RANK()` assigns the same rank to ties without leaving gaps.
- `ROW_NUMBER()` assigns a unique number to each row, even when revenue values are equal.

Example:

```sql
WITH region_month AS (
  SELECT TRUNC(o.order_date, 'MM') AS month_start,
         r.region_id,
         r.region_name,
         SUM(
           l.quantity * l.unit_price
           - NVL(l.discount_amount, 0)
         ) AS revenue
  FROM sales_order o
  JOIN sales_order_line l
    ON l.order_id = o.order_id
  JOIN sales_region r
    ON r.region_id = o.region_id
  WHERE o.status = 'COMPLETED'
  GROUP BY TRUNC(o.order_date, 'MM'),
           r.region_id,
           r.region_name
)
SELECT month_start,
       region_name,
       revenue,
       RANK() OVER (
         PARTITION BY month_start
         ORDER BY revenue DESC
       ) AS revenue_rank,
       DENSE_RANK() OVER (
         PARTITION BY month_start
         ORDER BY revenue DESC
       ) AS dense_revenue_rank,
       ROW_NUMBER() OVER (
         PARTITION BY month_start
         ORDER BY revenue DESC, region_id
       ) AS display_order
FROM region_month
ORDER BY month_start, display_order;
```

`PARTITION BY month_start` restarts the ranking for each month. `ORDER BY revenue DESC` places the highest revenue first. For `ROW_NUMBER`, add a deterministic tie-breaker such as `region_id` so the output order does not vary arbitrarily when revenues are tied.

For `RANK` and `DENSE_RANK`, only include tie-breaking criteria in `ORDER BY` if you intend to break ties. Adding `region_id` to the same `ORDER BY` clause means two regions with equal revenue will no longer be considered tied.

### 4.2. Getting Top N per Month

Oracle does not allow filtering directly on an analytic function alias in the same query block. Wrap the result in a CTE or subquery:

```sql
WITH ranked_region AS (
  SELECT month_start,
         region_id,
         region_name,
         revenue,
         ROW_NUMBER() OVER (
           PARTITION BY month_start
           ORDER BY revenue DESC, region_id
         ) AS rn
  FROM (
    SELECT TRUNC(o.order_date, 'MM') AS month_start,
           r.region_id,
           r.region_name,
           SUM(
             l.quantity * l.unit_price
             - NVL(l.discount_amount, 0)
           ) AS revenue
    FROM sales_order o
    JOIN sales_order_line l
      ON l.order_id = o.order_id
    JOIN sales_region r
      ON r.region_id = o.region_id
    WHERE o.status = 'COMPLETED'
    GROUP BY TRUNC(o.order_date, 'MM'),
             r.region_id,
             r.region_name
  )
)
SELECT month_start, region_name, revenue
FROM ranked_region
WHERE rn <= 3
ORDER BY month_start, rn;
```

`ROW_NUMBER() <= 3` always returns at most three regions per month. If the requirement is to include all regions tied for third place, use `RANK() <= 3` or `DENSE_RANK() <= 3` depending on the ranking rule.

### 4.3. Ranking Sales Reps Within Each Region

To rank sales reps by region and month, aggregate at the month-region-rep level and then partition by month and region:

```sql
RANK() OVER (
  PARTITION BY month_start, region_id
  ORDER BY revenue DESC
)
```

Do not rank individual order line items if the goal is to rank by total revenue. Doing so causes Oracle to rank each line item rather than each sales rep or region total.

## 5. Comparing Revenue Over Time with LAG

`LAG(expression, offset, default)` retrieves a value from a preceding row in the analytic window without needing a self join. With contiguous monthly data, `LAG(revenue, 1)` fetches the previous month's revenue; `LAG(revenue, 12)` fetches revenue from the same month in the prior year.

### 5.1. Computing Monthly and Prior-Month Revenue

```sql
WITH monthly_sales AS (
  SELECT TRUNC(o.order_date, 'MM') AS month_start,
         SUM(
           l.quantity * l.unit_price
           - NVL(l.discount_amount, 0)
         ) AS revenue
  FROM sales_order o
  JOIN sales_order_line l
    ON l.order_id = o.order_id
  WHERE o.status = 'COMPLETED'
  GROUP BY TRUNC(o.order_date, 'MM')
),
comparison AS (
  SELECT month_start,
         revenue,
         LAG(revenue) OVER (
           ORDER BY month_start
         ) AS previous_month_revenue
  FROM monthly_sales
)
SELECT month_start,
       revenue,
       previous_month_revenue,
       revenue - previous_month_revenue AS change_amount,
       CASE
         WHEN previous_month_revenue IS NULL
           OR previous_month_revenue = 0
         THEN NULL
         ELSE ROUND(
           (revenue - previous_month_revenue)
           / previous_month_revenue * 100,
           2
         )
       END AS change_percent
FROM comparison
ORDER BY month_start;
```

Percentage change formula:

[
\text{Change \%} =
\frac{\text{Current} - \text{Previous}}{\text{Previous}} \times 100
\]

If the prior period had no revenue or was 0, the growth percentage is undefined under this formula. Return `NULL` or display a dedicated label such as “N/A”; never substitute 1 for a 0 denominator, as that produces misleading percentages.

### 5.2. Why You Must Generate All Months

The query above only includes months that had transactions. If February had no revenue, the data may contain only January and March. Then `LAG(revenue)` for March will return January, even though the report labels it as the previous month. That compares against the most recent active period rather than the immediately preceding calendar month.

To compare strictly against the preceding calendar month, build a calendar spine containing every month in the reporting range, left join revenue, and replace missing periods with 0.

```sql
WITH params AS (
  SELECT DATE '2026-01-01' AS from_month,
         DATE '2026-12-01' AS to_month
  FROM dual
),
months AS (
  SELECT ADD_MONTHS(p.from_month, LEVEL - 1) AS month_start
  FROM params p
  CONNECT BY LEVEL <= MONTHS_BETWEEN(
    p.to_month, p.from_month
  ) + 1
),
monthly_sales AS (
  SELECT TRUNC(o.order_date, 'MM') AS month_start,
         SUM(
           l.quantity * l.unit_price
           - NVL(l.discount_amount, 0)
         ) AS revenue
  FROM sales_order o
  JOIN sales_order_line l
    ON l.order_id = o.order_id
  CROSS JOIN params p
  WHERE o.status = 'COMPLETED'
    AND o.order_date >= p.from_month
    AND o.order_date < ADD_MONTHS(p.to_month, 1)
  GROUP BY TRUNC(o.order_date, 'MM')
),
filled_months AS (
  SELECT m.month_start,
         NVL(s.revenue, 0) AS revenue
  FROM months m
  LEFT JOIN monthly_sales s
    ON s.month_start = m.month_start
),
comparison AS (
  SELECT month_start,
         revenue,
         LAG(revenue) OVER (
           ORDER BY month_start
         ) AS previous_month_revenue
  FROM filled_months
)
SELECT month_start,
       revenue,
       previous_month_revenue,
       revenue - previous_month_revenue AS change_amount,
       CASE
         WHEN previous_month_revenue IS NULL
           OR previous_month_revenue = 0
         THEN NULL
         ELSE ROUND(
           (revenue - previous_month_revenue)
           / previous_month_revenue * 100,
           2
         )
       END AS change_percent
FROM comparison
ORDER BY month_start;
```

In this example, `from_month` and `to_month` must be the first day of their respective months. `CONNECT BY LEVEL` generates one row per month. The filter on `ORDER_DATE` still uses a half-open range to include the entire final month.

### 5.3. Comparing Year-over-Year (Same Period Last Year)

Once the calendar spine contains every month, you can use an offset of 12:

```sql
LAG(revenue, 12) OVER (ORDER BY month_start) AS same_month_last_year
```

Then compute the difference and percentage just as for the prior month. Offset 12 only means the same month last year when the input series has exactly one row per month, no missing months, and contiguous ordering. Without a calendar spine, offset 12 merely fetches the twelfth preceding row.

Another approach is a self join on the first day of the month:

```sql
SELECT current_month.month_start,
       current_month.revenue,
       prior_year.revenue AS same_month_last_year
FROM monthly_sales current_month
LEFT JOIN monthly_sales prior_year
  ON prior_year.month_start =
     ADD_MONTHS(current_month.month_start, -12);
```

A self join clearly expresses the year-over-year relationship when data is non-contiguous, though you still need a calendar spine if the report must display months without transactions.

### 5.4. Comparing by Quarter or Year

You can change the period truncation expression:

- Month: `TRUNC(order_date, 'MM')`
- Quarter: `TRUNC(order_date, 'Q')`
- Year: `TRUNC(order_date, 'YYYY')`

When comparing quarters, build a complete quarterly calendar and use `LAG(revenue, 1)` for the prior quarter or `LAG(revenue, 4)` for the same quarter last year. Similarly, for years, an offset of 1 gives the previous year.

## 6. Combined Report: Detail, Monthly Totals, Rankings, and Growth

This section combines all techniques into a single query. The report returns:

- Detail rows by month and region, showing revenue, rank, prior-month revenue, and percentage change.
- Monthly total rows, showing total revenue across all regions compared against the previous month.
- A grand total row for the entire reporting period.
- Months with no transactions still appearing with zero revenue.

The example uses the `SALES_REGION` lookup table to generate every month-region combination. Regions with no revenue in a month are assigned 0 so ranking and comparisons remain consistent.

```sql
WITH
params AS (
  SELECT DATE '2026-01-01' AS from_month,
         DATE '2026-12-01' AS to_month
  FROM dual
),
months AS (
  SELECT ADD_MONTHS(p.from_month, LEVEL - 1) AS month_start
  FROM params p
  CONNECT BY LEVEL <= MONTHS_BETWEEN(
    p.to_month, p.from_month
  ) + 1
),
sales_by_region AS (
  SELECT TRUNC(o.order_date, 'MM') AS month_start,
         o.region_id,
         SUM(
           l.quantity * l.unit_price
           - NVL(l.discount_amount, 0)
         ) AS revenue
  FROM sales_order o
  JOIN sales_order_line l
    ON l.order_id = o.order_id
  CROSS JOIN params p
  WHERE o.status = 'COMPLETED'
    AND o.order_date >= p.from_month
    AND o.order_date < ADD_MONTHS(p.to_month, 1)
  GROUP BY TRUNC(o.order_date, 'MM'),
           o.region_id
),
region_month_grid AS (
  SELECT m.month_start,
         r.region_id,
         r.region_name,
         NVL(s.revenue, 0) AS revenue
  FROM months m
  CROSS JOIN sales_region r
  LEFT JOIN sales_by_region s
    ON s.month_start = m.month_start
   AND s.region_id = r.region_id
),
region_trend AS (
  SELECT g.*,
         LAG(g.revenue) OVER (
           PARTITION BY g.region_id
           ORDER BY g.month_start
         ) AS previous_region_revenue
  FROM region_month_grid g
),
ranked_region AS (
  SELECT t.*,
         RANK() OVER (
           PARTITION BY t.month_start
           ORDER BY t.revenue DESC
         ) AS revenue_rank,
         ROW_NUMBER() OVER (
           PARTITION BY t.month_start
           ORDER BY t.revenue DESC, t.region_id
         ) AS display_order,
         CASE
           WHEN t.previous_region_revenue IS NULL
             OR t.previous_region_revenue = 0
           THEN NULL
           ELSE ROUND(
             (t.revenue - t.previous_region_revenue)
             / t.previous_region_revenue * 100,
             2
           )
         END AS change_percent
  FROM region_trend t
),
monthly_totals AS (
  SELECT month_start,
         SUM(revenue) AS total_revenue
  FROM region_month_grid
  GROUP BY month_start
),
monthly_trend AS (
  SELECT month_start,
         total_revenue,
         LAG(total_revenue) OVER (
           ORDER BY month_start
         ) AS previous_month_revenue
  FROM monthly_totals
),
report_rows AS (
  SELECT month_start,
         1 AS sort_group,
         CAST('REGION DETAIL' AS VARCHAR2(20)) AS row_type,
         region_id,
         region_name,
         revenue,
         revenue_rank,
         previous_region_revenue AS previous_revenue,
         change_percent,
         display_order
  FROM ranked_region
  WHERE revenue <> 0

  UNION ALL

  SELECT month_start,
         2 AS sort_group,
         CAST('MONTHLY TOTAL' AS VARCHAR2(20)) AS row_type,
         CAST(NULL AS NUMBER) AS region_id,
         CAST(NULL AS VARCHAR2(100)) AS region_name,
         total_revenue AS revenue,
         CAST(NULL AS NUMBER) AS revenue_rank,
         previous_month_revenue AS previous_revenue,
         CASE
           WHEN previous_month_revenue IS NULL
             OR previous_month_revenue = 0
           THEN NULL
           ELSE ROUND(
             (total_revenue - previous_month_revenue)
             / previous_month_revenue * 100,
             2
           )
         END AS change_percent,
         0 AS display_order
  FROM monthly_trend

  UNION ALL

  SELECT CAST(NULL AS DATE) AS month_start,
         3 AS sort_group,
         CAST('GRAND TOTAL' AS VARCHAR2(20)) AS row_type,
         CAST(NULL AS NUMBER) AS region_id,
         CAST(NULL AS VARCHAR2(100)) AS region_name,
         SUM(total_revenue) AS revenue,
         CAST(NULL AS NUMBER) AS revenue_rank,
         CAST(NULL AS NUMBER) AS previous_revenue,
         CAST(NULL AS NUMBER) AS change_percent,
         0 AS display_order
  FROM monthly_trend
)
SELECT TO_CHAR(month_start, 'YYYY-MM') AS report_month,
       row_type,
       region_id,
       region_name,
       ROUND(revenue, 2) AS revenue,
       revenue_rank,
       ROUND(previous_revenue, 2) AS previous_revenue,
       change_percent
FROM report_rows
ORDER BY month_start NULLS LAST,
         sort_group,
         display_order;
```

### 6.1. Reading the Output

| Row Type | Data Grain | Comparison Column |
|---|---|---|
| `REGION DETAIL` | One region in one month | Compares the region's revenue with the same region in the previous month |
| `MONTHLY TOTAL` | Total of all regions in one month | Compares the monthly total with the previous month's total |
| `GRAND TOTAL` | Total across the entire reporting range | No prior period in this query |

`region_month_grid` creates one row per month-region pair. Therefore, `LAG` partitioned by region always sees the immediately preceding month, even when that region had zero revenue. `ranked_region` computes rankings on aggregated data, while `monthly_trend` computes the monthly total trend.

The condition `WHERE revenue <> 0` only hides zero-revenue detail rows from the final presentation; those zero rows still participate in the earlier ranking and `LAG` calculations. If you need to display every region including zero-revenue ones, remove this filter. If the business allows negative revenue due to refunds, this filter keeps negative rows.

The sample query assumes `REGION_ID` is `NUMBER` and `REGION_NAME` is at most 100 characters; adjust the types in `CAST(NULL AS ...)` to match your actual schema. If the region catalog is empty, the cross join produces no region details and the monthly total will not reflect unassigned-region revenue. Decide how to handle transactions missing a region before releasing the report.

## 7. Working with ROLLUP and Analytic Functions Together

`ROLLUP` and analytic functions can appear in the same query, but you must be clear on which rows the analytic function operates over. If you apply `RANK` directly after `GROUP BY ROLLUP`, monthly total and grand total rows are present in the analytic function's input set. Those rows can receive ranks and corrupt the report.

An easy-to-control pattern is:

1. Create an aggregated detail CTE.
2. Compute ranks on the detail rows.
3. Compute monthly totals and the grand total in separate CTEs or a separate `ROLLUP`.
4. Combine row types with `UNION ALL`.

If you use `ROLLUP` to generate subtotals and need rankings, wrap the rollup output in a CTE and filter `GROUPING(region_name) = 0` before ranking, or compute ranks in a detail CTE before adding total rows. Never rank subtotals as if they were regions.

## 8. Handling NULLs, Missing Months, and Invalid Data

### 8.1. NULLs in Revenue Calculations

If `DISCOUNT_AMOUNT` is `NULL`, direct subtraction produces `NULL` and `SUM` ignores that value. Use `NVL(discount_amount, 0)` when `NULL` means no discount. If `NULL` means missing or undetermined data, fix the source data rather than defaulting it to 0.

If `QUANTITY` or `UNIT_PRICE` can be `NULL`, define explicit data quality rules. A line missing its unit price should not silently disappear from total revenue without warning. You can check separately:

```sql
SELECT COUNT(*) AS invalid_line_count
FROM sales_order_line
WHERE quantity IS NULL
   OR unit_price IS NULL
   OR quantity < 0;
```

Negative quantities may be valid in a system representing adjustments or returns; apply rules matching your accounting model.

### 8.2. Orders Without a Region

An inner join with `SALES_REGION` drops transactions whose `REGION_ID` does not match the lookup table. If the report must preserve those transactions, use a left join and label them “Unassigned” in the output. Also report unallocated order counts and revenue so the report total does not silently fall below source totals.

### 8.3. Currencies and Rounding

Never add VND, USD, EUR, or other currencies directly into a single arithmetic sum. There are two approaches:

- Group the report by `CURRENCY_CODE`, producing separate totals per currency.
- Convert to a single reporting currency using an exchange rate table with well-defined effective dates, rate types, and rate selection rules.

Keep full precision during intermediate calculations and round at the presentation layer per accounting policy. Rounding each line before summing can yield a different result than summing everything and rounding at the end.

## 9. Performance and Scalability

### 9.1. Filtering Dates on the Native Column

Prefer:

```sql
WHERE order_date >= :from_date
  AND order_date <  :to_date_exclusive
```

Avoid:

```sql
WHERE TRUNC(order_date, 'MM') = DATE '2026-01-01'
```

unless a suitable function-based index or design is in place. Half-open range predicates typically make better use of indexes and date/month partitioning.

### 9.2. Aggregating Before Joining Large Dimensions

If a dimension has a one-to-many relationship, check cardinality and avoid multiplying fact rows. You can aggregate revenue by foreign key first and then join region names, product names, or sales rep names. Dimension tables should have a unique key on the join column.

### 9.3. Indexes and Partitioning

Appropriate indexes depend on filter predicates and workload. An index starting with `STATUS` followed by `ORDER_DATE` may or may not be optimal depending on selectivity; no single index order fits every report. For large fact tables, partitioning by recognition date can enable partition pruning by period, though you should verify the execution plan and storage strategy.

### 9.4. Inspecting the Execution Plan

Inspect the report query's plan using `DBMS_XPLAN.DISPLAY_CURSOR` when you have privileges and cursor data:

```sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    sql_id => :sql_id,
    format => 'TYPICAL'
  )
);
```

Evaluate cardinality estimates, join methods, access paths, sorts, hash aggregations, and intermediate data volume. Reports using `ROLLUP`, `RANK`, and `LAG` may require sorting or window operations; monitor memory and temp tablespace usage on large datasets.

Do not automatically collect AWR/ASH or use Diagnostics/Tuning Pack features unless corresponding licensing is confirmed. You can inspect cursor execution plans and runtime metrics permitted by organizational policy.

### 9.5. Materializing Results for Frequently Run Reports

If a report runs repeatedly over large datasets, consider daily/monthly summary tables or materialized views. Define:

- Refresh frequency and acceptable data latency.
- Handling of late-arriving transactions, cancellations, and refunds.
- Re-synchronization procedures when source data changes.
- Reconciliation checks against the source transaction tables.
- Access permissions and retention period for summary data.

Materialized views or summary tables do not replace defining revenue rules. They only persist results computed under the chosen rules.

## 10. Verification and Reconciliation

A report can execute without errors yet still be wrong due to multiplying joins, missing status filters, skipped months, or mixed currencies. Reconcile at multiple levels:

1. Total revenue from line items versus sum of regional totals.
2. Sum of regional totals versus monthly totals.
3. Sum of monthly totals versus the full-period grand total.
4. Count of orders included versus count of completed orders under the same filters.
5. Verify that months with no transactions appear with zero revenue.
6. Verify that tied regions receive ranks matching the ranking rule.
7. Verify that the first month of the period has no prior month if dates outside the reporting range are not queried.
8. Verify percentage calculation when prior-period revenue is 0.
9. Verify transactions near day/month boundaries and time zones.

Total reconciliation query:

```sql
SELECT SUM(
         l.quantity * l.unit_price
         - NVL(l.discount_amount, 0)
       ) AS source_revenue
FROM sales_order o
JOIN sales_order_line l
  ON l.order_id = o.order_id
WHERE o.status = 'COMPLETED'
  AND o.order_date >= DATE '2026-01-01'
  AND o.order_date <  DATE '2027-01-01';
```

Compare this figure with the report's grand total using the exact same status definition, date range, currency, and handling of unallocated regions. If the report performs currency conversion, also reconcile the chosen exchange rates and effective dates.

## 11. Presenting the Report to End Users

When surfacing SQL results in an application or BI tool, clearly distinguish row types:

- Detail rows: month, region, revenue, rank, prior-month revenue, percentage change.
- Monthly total rows: highlight the total while retaining period-over-period comparison columns.
- Grand total row: clearly indicate the entire reporting span and omit meaningless comparison percentages.

Format numbers according to currency and viewer locale while preserving raw numeric values for sorting and calculations. Never sort revenue by formatted strings such as `1.200.000`; sort by `NUMBER` first and format afterward.

If the report has filters for region, product, or sales rep, clarify whether subtotals are computed over the filtered scope or over the entire dataset. The same query can produce different totals depending on whether filters are applied before or after aggregation.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Joining header to multiple child tables before aggregating | Revenue is multiplied | Aggregate each one-to-many relationship before joining |
| Ranking individual line items | Ranks do not reflect regional or rep revenue | Aggregate to the target grain first, then apply analytic functions |
| Ranking subtotal rows | Monthly or grand totals appear in the rankings | Rank detail rows separately, then append total rows |
| Using `RANK` when a unique sequence number is needed | Multiple rows share the same rank | Use `ROW_NUMBER` with a stable tie-breaker |
| Using `ROW_NUMBER` when ties should be preserved | A tied unit is pushed to a lower rank | Use `RANK` or `DENSE_RANK` |
| Using `LAG` only on active transaction months | Missing months cause comparisons to skip periods | Build a calendar spine and fill missing months with 0 |
| Dividing by zero prior-period revenue | Runtime error or meaningless percentage | Use `CASE` to return NULL/N/A |
| Filtering with `BETWEEN` on columns containing time | May miss timestamps at the end of the day | Use `>= start` and `< end_exclusive` |
| Summing multiple currencies directly | Total revenue is meaningless | Group by currency or convert using exchange rates |
| Rounding per line without a policy | Totals exhibit rounding discrepancies | Standardize the rounding point |

## 13. Report-Building Workflow

1. Finalize definitions for revenue, transaction status, recognition date, currency, and refund handling.
2. Identify the source data grain and inspect one-to-many relationships to avoid row multiplication.
3. Write the base aggregation query at the reporting dimensions.
4. Add `ROLLUP` or `GROUPING SETS` for subtotals and grand totals.
5. Create a detail CTE and apply `RANK`, `DENSE_RANK`, or `ROW_NUMBER` per ranking rules.
6. Build a calendar spine when strict calendar prior-period or year-over-year comparisons are required.
7. Use `LAG` or a self join to fetch the comparison period and handle zero prior-period revenue.
8. Combine detail rows, monthly totals, and the grand total using `UNION ALL` when explicit control over row levels is needed.
9. Reconcile source totals, regional totals, and period totals.
10. Verify the execution plan, access permissions, data security, and output formatting.

## 14. Practical Guidelines

A reliable revenue report starts with the right revenue definition and data grain. `GROUP BY` computes figures at the analysis grain; `ROLLUP` and `GROUPING SETS` produce subtotals; `RANK`, `DENSE_RANK`, and `ROW_NUMBER` rank aggregated results; and `LAG` compares consecutive periods. A calendar spine ensures months with zero transactions still count as periods, while `GROUPING` distinguishes subtotals from real `NULL` values.

When combining calculations, compute details and trends in separate CTEs before assembling the report row types. Reconcile totals against source data, handle currencies and time zones explicitly, and verify performance at realistic data scale. That way, readers can trace where every number comes from, which criteria determine rankings, and which exact time periods are being compared.
