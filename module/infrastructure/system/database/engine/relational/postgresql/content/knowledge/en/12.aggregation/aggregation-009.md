# Ratios, Weighted Averages, and Division by Zero in PostgreSQL

In business reporting, analysis rarely stops at counting rows or summing totals. We need to know **conversion rates**, **successful delivery rates**, **average selling price per unit**, **advertising efficiency**, or **a group's share of total revenue**. All of these metrics involve division, yet picking the wrong denominator, letting integer division truncate decimals, or taking a simple average of rates across different-sized groups will produce wrong answers even when the SQL runs cleanly.

PostgreSQL provides all the primitives required to compute these metrics accurately: the `numeric` type, `::numeric` casts, aggregate functions `SUM()`, `COUNT()`, and `AVG()`, the `FILTER` clause, `NULLIF()` for zero denominators, `CASE` for business rules, `COALESCE()` when defaults are warranted, and grouped/window percentage calculations.

This lesson belongs to PostgreSQL's **Data Aggregation** chapter. The goal is not just writing SQL that avoids runtime errors, but **choosing the mathematically and semantically right calculation**.

## 1. Distinguishing Ratios, Arithmetic Averages, and Weighted Averages

Three commonly confused calculations:

- **Ratio (rate):** the count or amount of one subset relative to a denominator set, e.g., 20 signups out of 100 visits.
- **Arithmetic average (mean):** the sum of values divided by the count of valid observations, e.g., the average list price across three catalog items.
- **Weighted average:** each value carries a different weight or observation count, e.g., average selling price per unit sold.

### 1.1. Ratio

Given numerator \(a\) and denominator \(b\):

\[
r = \frac{a}{b}, \qquad b \ne 0
\]

For example, 20 signups out of 100 visits:

\[
r = \frac{20}{100}=0.2=20\%
\]

Here you must ensure **the numerator comes from the same observation set as the denominator**. If the 20 signups are from this week while the 100 visits are from last week, SQL happily computes 20%, yet the metric is meaningless.

### 1.2. Arithmetic Average

Given three prices 100,000, 160,000, and 50,000:

\[
\bar{x}=\frac{100000+160000+50000}{3}
\approx 103333.33
\]

This assumes **every price carries equal weight**, regardless of how many units sold.

### 1.3. Weighted Average

Suppose sales are:

| Unit Price | Quantity |
|---:|---:|
| 100,000 | 2 |
| 160,000 | 1 |
| 50,000 | 7 |

The average price **per unit sold** is:

\[
\bar{x}_w=\frac{\sum_i w_i x_i}{\sum_i w_i}
=\frac{2\times100000+1\times160000+7\times50000}{2+1+7}
=71000
\]

The result 71,000 differs from the arithmetic mean 103,333.33 because 7 out of 10 units were sold at 50,000.

**Which average to choose depends on the business question.** If asking "what is the average catalog price of these three items?", an arithmetic average fits. If asking "what average price did we realize per unit sold?", the weights must be quantities sold.

## 2. The Integer Division Trap in PostgreSQL

This SQL pitfall is easy to overlook:

~~~sql
SELECT
    1 / 2 AS integer_division,
    1::numeric / 2 AS numeric_division,
    1.0 / 2 AS decimal_division;
~~~

Conceptual results:

| Expression | Result |
|---|---:|
| `1 / 2` | `0` |
| `1::numeric / 2` | `0.5` |
| `1.0 / 2` | `0.5` |

When both operands are integers, integer division in PostgreSQL **truncates the fractional part**. For negative division, the fraction is truncated toward zero per integer-division semantics.

### 2.1. Why Do COUNT and SUM Trigger This Trap So Often?

`COUNT(*)` returns `bigint`. `SUM(integer)` also typically returns `bigint`. Therefore:

~~~sql
SELECT
    COUNT(*) FILTER (WHERE status = 'success')
    / COUNT(*) AS success_rate
FROM some_events;
~~~

when `some_events` exists, divides two integers; any rate below 100% truncates to 0.

Correct approach:

~~~sql
SELECT
    COUNT(*) FILTER (WHERE status = 'success')::numeric
    / NULLIF(COUNT(*), 0) AS success_rate
FROM some_events;
~~~

Apply `::numeric` to the **numerator before dividing**, rather than casting the result after integer division has already happened.

### 2.2. Casting After Division Is Too Late

Wrong if trying to keep decimals:

~~~sql
SELECT (1 / 2)::numeric AS wrong_rate;
~~~

The result is still 0, because integer division executed first.

Right:

~~~sql
SELECT
    1::numeric / 2 AS correct_rate,
    CAST(1 AS numeric) / 2 AS also_correct;
~~~

You can also multiply by a decimal literal:

~~~sql
SELECT 100.0 * 1 / 2 AS percentage;
~~~

In PostgreSQL, `100.0` is a numeric literal with a fractional point, causing the expression to use `numeric` arithmetic instead of integer division.

### 2.3. Percentage Is Ratio Times 100

For a ratio of 0.125:

~~~sql
SELECT
    25::numeric / 200 AS ratio,
    100.0 * 25 / 200 AS percentage;
~~~

The results are ratio `0.125` and percentage `12.5`.

**Do not multiply by 100 in SQL and then multiply by 100 again in the UI.** Agree on whether the API contract returns `ratio = 0.125` or `percentage = 12.5`.

## 3. Division by Zero: Mathematical Rules and SQL Behavior

A ratio \(a/b\) is undefined when \(b=0\). PostgreSQL does not invent a "business-friendly" fallback value for it.

~~~sql
-- Intentional error example; no need to run in the lab flow:
-- SELECT 10 / 0;
~~~

PostgreSQL raises a **division by zero** error, typically with SQLSTATE `22012`.

### 3.1. Distinguishing Three Cases

| Numerator | Denominator | Meaning |
|---:|---:|---|
| 0 | 10 | Rate equals 0 |
| 5 | 10 | Rate equals 0.5 |
| 0 | 0 | Rate is undefined |
| 5 | 0 | Rate is undefined |

**Never default 0/0 to 0.** Suppose a campaign had zero visitors and zero signups: there is no sample to compute a conversion rate, unlike a campaign with 100 visitors and zero signups (0%).

### 3.2. NULL Is Not Zero

In SQL, `NULL` represents an absent or unknown value. If the denominator is NULL, division returns NULL:

~~~sql
SELECT
    5::numeric / NULL::numeric AS unknown_rate;
~~~

This differs from a literal 0 denominator, and `NULLIF` converts a 0 denominator into NULL to prevent an invalid division error.

## 4. NULLIF: The Safe Pattern for Denominators

Syntax:

~~~sql
NULLIF(expression_1, expression_2)
~~~

`NULLIF(a,b)` returns `NULL` if both expressions are equal; otherwise, it returns the first expression.

Example:

~~~sql
SELECT
    NULLIF(10, 0) AS ten,
    NULLIF(0, 0) AS null_instead_of_zero;
~~~

Result: the first is 10, and the second is NULL.

### 4.1. Common Safe Division Pattern

~~~sql
SELECT
    25::numeric / NULLIF(150, 0) AS rate;
~~~

When the denominator is 0, it turns into NULL and the division evaluates to NULL instead of throwing an error.

General SQL formula:

~~~sql
numerator::numeric / NULLIF(denominator, 0)
~~~

Or as a percentage:

~~~sql
100.0 * numerator / NULLIF(denominator, 0)
~~~

`numerator` and `denominator` in these two patterns are **conceptual placeholders**; run them only against actual table/query columns.

### 4.2. NULLIF Does Not Turn the Rate Into 0

~~~sql
SELECT
    0::numeric / NULLIF(0, 0) AS undefined_rate;
~~~

The result is NULL. That is usually the right choice when reports must distinguish **no data to compute** from a **0 rate**.

### 4.3. NULLIF Guards Only Its Own Denominator

If a formula has multiple divisions, guard each denominator. For example:

~~~sql
SELECT
    (10::numeric / NULLIF(0, 0))
    / NULLIF(2, 0) AS result;
~~~

The result is NULL because the first denominator is 0.

`NULLIF` does not prevent integer overflow in numerator multiplications or type-cast errors elsewhere. Set appropriate data types before evaluating expressions.

## 5. CASE: When a Zero Denominator Needs a Business Decision

Use `CASE` when you want explicit branching rules:

~~~sql
SELECT
    CASE
        WHEN 0 = 0 THEN NULL
        ELSE 5::numeric / 0
    END AS rate;
~~~

In practice, avoid expressions with constant division by zero:

~~~sql
WITH metric AS (
    SELECT 5::numeric AS numerator, 0::numeric AS denominator
)
SELECT
    CASE
        WHEN denominator = 0 THEN NULL
        ELSE numerator / NULLIF(denominator, 0)
    END AS rate
FROM metric;
~~~

Note that PostgreSQL may evaluate certain **constant expressions** during planning, so never rely on `CASE WHEN FALSE THEN 1/0 ...` to guarantee safety in every context. `NULLIF` is cleaner and clearer for division.

### 5.1. Three Policies for a Missing Denominator

| Policy | Result When Denominator Is 0 | When to Consider |
|---|---|---|
| Return NULL | "Undefined / insufficient data" | Conversion rates, empty-sample performance |
| Return 0 | Shows 0 per explicit contract | Dashboards with an explicit zero convention |
| Omit row | Excludes group from the report | Reports listing only active groups |

No single policy fits every KPI. **Clarify the semantics before wrapping with COALESCE.**

### 5.2. Returning a Status Alongside the Rate

Instead of returning only a number, return status context too:

~~~sql
WITH metric AS (
    SELECT 0::numeric AS successes, 0::numeric AS attempts
)
SELECT
    CASE
        WHEN attempts = 0 THEN 'NO_SAMPLE'
        ELSE 'COMPUTED'
    END AS rate_status,
    successes / NULLIF(attempts, 0) AS rate
FROM metric;
~~~

With zero attempts, `rate_status = 'NO_SAMPLE'` and `rate = NULL`. Clients can display "Insufficient data" instead of "0%".

## 6. COALESCE: Helpful, Yet Easy to Hide Missing Data

`COALESCE(a,b)` returns the first non-NULL expression.

~~~sql
SELECT
    COALESCE(NULL::numeric, 0) AS replaced_null;
~~~

A frequent idiom:

~~~sql
COALESCE(numerator::numeric / NULLIF(denominator, 0), 0)
~~~

This converts every NULL result into 0—covering both zero denominators and missing numerator values.

### 6.1. When Is 0 Meaningful?

For a daily order-count dashboard, having zero transactions on a fully reconciled day can reasonably display **0 orders**. Here `COALESCE(COUNT...)` is unnecessary since `COUNT` returns 0, while `COALESCE(SUM(...),0)` may be reasonable.

Yet for conversion rate on a day with zero visits, **0%** can mislead readers into thinking "we had traffic, and nobody signed up."

### 6.2. Better Pattern: Preserve a Semantically Meaningful NULL Column

~~~sql
SELECT
    numerator::numeric / NULLIF(denominator, 0)
        AS rate_or_null,
    COALESCE(
        numerator::numeric / NULLIF(denominator, 0),
        0::numeric
    ) AS display_zero_if_undefined
FROM metrics;
~~~

This is a structural example requiring a `metrics` table if run verbatim. In production, return 0 only if the reporting contract explicitly agrees on it.

## 7. Aggregates and NULL in PostgreSQL

Before computing aggregated ratios, understand how `COUNT`, `SUM`, and `AVG` treat NULL.

### 7.1. COUNT(*) Differs from COUNT(column)

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(value) AS nonnull_values
FROM (
    VALUES (1), (NULL), (3)
) AS t(value);
~~~

Result:

| total_rows | nonnull_values |
|---:|---:|
| 3 | 2 |

`COUNT(*)` counts every row. `COUNT(column)` counts only rows where the expression is non-NULL.

### 7.2. AVG Ignores NULL

~~~sql
SELECT AVG(value) AS avg_nonnull
FROM (
    VALUES (10::numeric), (NULL::numeric), (20::numeric)
) AS t(value);
~~~

The result is 15, not 10. The denominator of `AVG(value)` is the **number of non-NULL values**.

### 7.3. SUM on an Empty Set Returns NULL

~~~sql
SELECT
    COUNT(*) AS rows_count,
    SUM(x) AS sum_value,
    AVG(x) AS avg_value
FROM (
    SELECT 1::numeric AS x
    WHERE FALSE
) AS t;
~~~

The result is one row:

| rows_count | sum_value | avg_value |
|---:|---|---|
| 0 | NULL | NULL |

This difference matters when a summary table has no rows yet: `COUNT(*)` returns 0 while `SUM`/`AVG` return NULL when there are no valid inputs.

### 7.4. SUM of All NULLs Is Also NULL

~~~sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(x) AS known_values,
    SUM(x) AS sum_value
FROM (VALUES (NULL::numeric), (NULL::numeric)) AS t(x);
~~~

Two rows exist yet there are no numbers to sum, so `SUM(x)` is NULL. Never treat this as a true sum of 0 unless business rules explicitly define it so.

## 8. Lab: Campaign Dataset for Computing Ratios

From here on, we use a small dataset intentionally containing **positive denominators**, **zero denominators**, and **a group with zero rows**.

Run these commands in a **test PostgreSQL database** where you have schema-creation privileges. Do not run in production. If `ratio_lab` already exists, use another database or schema name; do not wipe real data to repeat examples.

### 8.1. Creating the Schema and Campaigns Table

~~~sql
CREATE SCHEMA ratio_lab;

CREATE TABLE ratio_lab.campaigns (
    campaign_id INTEGER PRIMARY KEY,
    campaign_name TEXT NOT NULL UNIQUE
);

INSERT INTO ratio_lab.campaigns (campaign_id, campaign_name)
VALUES
    (1, 'Alpha'),
    (2, 'Beta'),
    (3, 'Gamma'),
    (4, 'Delta');
~~~

### 8.2. Creating the Daily Metrics Table

~~~sql
CREATE TABLE ratio_lab.campaign_daily (
    campaign_id INTEGER NOT NULL
        REFERENCES ratio_lab.campaigns(campaign_id),
    metric_day DATE NOT NULL,
    visitors INTEGER NOT NULL CHECK (visitors >= 0),
    signups INTEGER NOT NULL CHECK (signups >= 0),
    revenue NUMERIC(14, 2) NOT NULL CHECK (revenue >= 0),
    spend NUMERIC(14, 2) NOT NULL CHECK (spend >= 0),

    CONSTRAINT pk_campaign_daily
        PRIMARY KEY (campaign_id, metric_day),

    CONSTRAINT chk_signups_within_visitors
        CHECK (signups <= visitors)
);
~~~

Each row represents **one campaign on one day**. `signups <= visitors` makes sense only when signups and visitors follow the **same visit/person definition**. In real products, one person might sign up multiple times or visitors might be anonymous; confirm definitions before adding such constraints.

### 8.3. Inserting Targeted Sample Data

~~~sql
INSERT INTO ratio_lab.campaign_daily (
    campaign_id,
    metric_day,
    visitors,
    signups,
    revenue,
    spend
)
VALUES
    (1, DATE '2026-11-10', 100, 20, 1200000.00, 400000.00),
    (1, DATE '2026-11-11',  50,  5,  300000.00, 200000.00),
    (2, DATE '2026-11-10',   0,  0,       0.00,      0.00),
    (2, DATE '2026-11-11',  20,  4,  160000.00,  80000.00),
    (3, DATE '2026-11-10',   0,  0,       0.00,      0.00);
~~~

Overview:

| Campaign | Date | Visitors | Signups | Revenue | Spend |
|---|---|---:|---:|---:|---:|
| Alpha | 11/10 | 100 | 20 | 1,200,000 | 400,000 |
| Alpha | 11/11 | 50 | 5 | 300,000 | 200,000 |
| Beta | 11/10 | 0 | 0 | 0 | 0 |
| Beta | 11/11 | 20 | 4 | 160,000 | 80,000 |
| Gamma | 11/10 | 0 | 0 | 0 | 0 |
| Delta | No rows | — | — | — | — |

This data distinguishes:

- Alpha: 25 signups total across 150 visitors.
- Beta: one day with zero visitors, one day with 4/20.
- Gamma: has a daily record, yet denominator is 0.
- Delta: exists in the campaigns catalog, yet **has no daily metric rows**.

## 9. Computing Daily Rates with NULLIF

~~~sql
SELECT
    campaign_id,
    metric_day,
    visitors,
    signups,
    ROUND(
        100.0 * signups / NULLIF(visitors, 0),
        2
    ) AS signup_rate_pct
FROM ratio_lab.campaign_daily
ORDER BY campaign_id, metric_day;
~~~

Expected output:

| Campaign ID | Date | Visitors | Signups | signup_rate_pct |
|---:|---|---:|---:|---:|
| 1 | 11/10 | 100 | 20 | 20.00 |
| 1 | 11/11 | 50 | 5 | 10.00 |
| 2 | 11/10 | 0 | 0 | NULL |
| 2 | 11/11 | 20 | 4 | 20.00 |
| 3 | 11/10 | 0 | 0 | NULL |

The metric returns NULL on zero-visitor days instead of failing with division by zero.

### 9.1. Why Can't We Average Daily Rates to Get the Campaign Rate?

Alpha had 100 visitors on Nov 10 and 50 visitors on Nov 11. Averaging 20% and 10% gives 15%. Across both days combined, however, Alpha had **25 signups / 150 visitors ≈ 16.67%**.

The discrepancy arises because **each day has a different denominator**.

### 9.2. A Day with Zero Visitors Does Not Have a Rate of 0

Beta on Nov 10: `0/0` is undefined. Replacing NULL with 0 before running `AVG` over both days would yield 10% instead of the true 20% across days with visitors.

## 10. Aggregating Campaign Rates Properly

The right formula for conversion rate across the whole observation set:

\[
\text{Conversion rate} =
\frac{\sum \text{signups}}{\sum \text{visitors}}
\]

In PostgreSQL:

~~~sql
SELECT
    campaign_id,
    SUM(visitors) AS total_visitors,
    SUM(signups) AS total_signups,
    ROUND(
        100.0 * SUM(signups)
        / NULLIF(SUM(visitors), 0),
        2
    ) AS signup_rate_pct
FROM ratio_lab.campaign_daily
GROUP BY campaign_id
ORDER BY campaign_id;
~~~

Expected output:

| campaign_id | total_visitors | total_signups | signup_rate_pct |
|---:|---:|---:|---:|
| 1 | 150 | 25 | 16.67 |
| 2 | 20 | 4 | 20.00 |
| 3 | 0 | 0 | NULL |

Delta does not appear because it has no rows in `campaign_daily`. We will handle that with `LEFT JOIN` later.

### 10.1. Do Not Take AVG of Daily Rates When You Want Period Rate

A simple averaging query:

~~~sql
SELECT
    campaign_id,
    ROUND(
        AVG(
            100.0 * signups / NULLIF(visitors, 0)
        ),
        2
    ) AS average_daily_rate_pct
FROM ratio_lab.campaign_daily
GROUP BY campaign_id
ORDER BY campaign_id;
~~~

returns **15.00** for Alpha, whereas the period rate is **16.67**.

That query is not always "wrong": it computes the **unweighted mean of daily rates across days with valid denominators**, which answers "what is the typical day's rate if every day has equal weight?" It is **not** the conversion rate across total visits.

### 10.2. Combining Two Groups

If group A has 10/100 and group B has 5/50:

\[
\frac{10+5}{100+50}=\frac{15}{150}=10\%
\]

If group A has 20/100 and group B has 5/50:

\[
\frac{20+5}{100+50}=\frac{25}{150}\approx16.67\%
\]

That is why multi-period summary tables should store or pass **numerators and denominators**, not just pre-rounded rates.

## 11. Connection Between Overall Rate and Weighted Average

Suppose each day \(i\) has:

\[
r_i = \frac{a_i}{b_i}
\]

When \(b_i > 0\), the overall rate is:

\[
R=\frac{\sum_i a_i}{\sum_i b_i}
=\frac{\sum_i b_i r_i}{\sum_i b_i}
\]

This means the **overall rate** is mathematically the **weighted average of sub-rates**, weighted by **their respective denominators**, when groups are valid and data rules are consistent.

For Alpha:

| Date | Rate | Visitor Weight |
|---|---:|---:|
| 11/10 | 20% | 100 |
| 11/11 | 10% | 50 |

\[
R = \frac{100\times20\%+50\times10\%}{100+50}
=\frac{25}{150}\approx16.67\%
\]

### 11.1. Expressing via Sub-Rates for Illustration

~~~sql
SELECT
    campaign_id,
    ROUND(
        100.0 *
        SUM(
            visitors * (signups::numeric / NULLIF(visitors, 0))
        )
        / NULLIF(SUM(visitors), 0),
        2
    ) AS weighted_rate_pct
FROM ratio_lab.campaign_daily
GROUP BY campaign_id
ORDER BY campaign_id;
~~~

This yields the same result as the overall rate on the lab data. However, **never use this verbose, NULL-prone form for real KPIs** when you already have total numerator and total denominator.

Simpler and easier to verify:

~~~sql
SUM(signups)::numeric / NULLIF(SUM(visitors), 0)
~~~

### 11.2. Why Can Complicated Expressions Drift When Data Is Missing?

If a day has `visitors=0` and another metric violates the same observation set, `visitors * (signups / NULLIF(visitors,0))` returns NULL for that day. `SUM` skips NULLs, whereas other totals might include other rows in the numerator or denominator.

Therefore, before rewriting a "rate of sums" as a "weighted average of sub-rates," verify every sub-rate is well-defined, denominators are valid, and observation sets match.

## 12. Defining the Right Numerator and Denominator

Before writing SQL, verify the **measurement unit** and **scope**.

Examples:

| KPI | Numerator | Denominator |
|---|---|---|
| Signup rate | Valid signups (users/events) | Qualifying visits (users/events) |
| Delivery success rate | Delivered orders | Shipped orders or defined order set |
| API error rate | Requests failing per definition | Total processed requests |
| Click-through rate | Valid clicks | Valid impressions |
| Group revenue share | Group revenue | Total revenue across entire set |
| ROAS | Ad-attributed revenue | Ad spend |
| Average selling price per unit | Total line revenue | Total units sold |

### 12.1. Do Not Mix "Users" and "Events"

Suppose one user visits a site 5 times and signs up once:

- Event-level conversion: 1 signup / 5 visits = 20%.
- User-level conversion: 1 signed-up user / 1 unique visitor = 100%.

Both are valid, yet **they measure two different concepts**. If a report says "percentage of users who signed up," the denominator should be unique users in the qualifying population, not page views.

### 12.2. Numerator Must Be a Proper Subset of Denominator

For a probability or 0–100% conversion rate, verify:

\[
0 \le a \le b
\]

If the numerator exceeds the denominator, either there is a data bug or you are mixing two different units. Never slap `LEAST(ratio,1)` on to cap rates at 100% before finding the root cause.

### 12.3. Not All Ratios Are Capped at 100%

ROAS can be 2.5, meaning revenue is 2.5 times ad spend. Units per customer can also exceed 1. Only KPIs defined as a **subset out of a whole** are bounded between 0 and 1.

## 13. Weighted Average: General Formula

Given values \(x_i\) and weights \(w_i\):

\[
\bar{x}_w=\frac{\sum_i x_i w_i}{\sum_i w_i}
\]

Standard conditions for a meaningful weighted average:

- All weights measure the same quantity, such as units, duration, or contribution.
- Weights are defined consistently.
- For ordinary weights, $w_i \ge 0$.
- Total weight is **greater than 0**.
- Rows missing a value or weight are handled consistently in both numerator and denominator.

Sample SQL:

~~~sql
SELECT
    SUM(value * weight)
    / NULLIF(SUM(weight), 0) AS weighted_average
FROM measurements;
~~~

This is a structural example; running it verbatim requires a `measurements` table or CTE with those two columns.

### 13.1. Why Not Use AVG(value * weight)?

`AVG(value * weight)` divides the sum of products by the **number of valid rows**, not by total weight. With weights 2, 1, and 7, the row count is 3 whereas total weight is 10. Those are two different calculations.

### 13.2. Why Not Use AVG(value) When Weights Differ?

`AVG(value)` implicitly gives every row equal weight. If one row represents 10,000 visits and another represents 5 visits, a plain average badly misrepresents the overall population.

## 14. Lab: Quantity-Weighted Average Selling Price

Create a sales lines table:

~~~sql
CREATE TABLE ratio_lab.sales_lines (
    sale_line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category TEXT NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    sold_at TIMESTAMPTZ NOT NULL
);

INSERT INTO ratio_lab.sales_lines (
    category, product_id, quantity, unit_price, sold_at
)
VALUES
    ('Book', 101, 2, 100000.00, TIMESTAMPTZ '2026-11-10 09:00:00+07'),
    ('Book', 102, 1, 160000.00, TIMESTAMPTZ '2026-11-10 10:00:00+07'),
    ('Book', 103, 7,  50000.00, TIMESTAMPTZ '2026-11-11 14:00:00+07'),
    ('Toy',  201, 4,  25000.00, TIMESTAMPTZ '2026-11-11 15:00:00+07');
~~~

### 14.1. Unweighted Average Unit Price per Line

~~~sql
SELECT
    category,
    ROUND(AVG(unit_price), 2) AS simple_avg_price
FROM ratio_lab.sales_lines
GROUP BY category
ORDER BY category;
~~~

For Book: `(100000+160000+50000)/3 = 103333.33`.

This is the average **per line**, not per unit sold.

### 14.2. Quantity-Weighted Average

~~~sql
SELECT
    category,
    SUM(quantity) AS total_units,
    SUM(quantity * unit_price) AS total_revenue,
    ROUND(
        SUM(quantity * unit_price)
        / NULLIF(SUM(quantity), 0),
        2
    ) AS weighted_avg_unit_price
FROM ratio_lab.sales_lines
GROUP BY category
ORDER BY category;
~~~

Expected output:

| category | total_units | total_revenue | weighted_avg_unit_price |
|---|---:|---:|---:|
| Book | 10 | 710,000 | 71,000.00 |
| Toy | 4 | 100,000 | 25,000.00 |

Calculation for Book:

~~~text
2 × 100,000 = 200,000
1 × 160,000 = 160,000
7 ×  50,000 = 350,000

Total revenue = 710,000
Total units   = 10
Unit-weighted average price = 71,000
~~~

### 14.3. Why Does quantity * unit_price Have Enough Precision?

In the lab, `unit_price` is `numeric(12,2)`, so multiplying by quantity uses exact `numeric` decimal arithmetic instead of floating point.

If both operands are large integers, multiplying them can **overflow before aggregation**. Cast before multiplying when needed:

~~~sql
SELECT
    SUM(quantity::numeric * unit_price) AS precise_amount
FROM ratio_lab.sales_lines;
~~~

In the lab `unit_price` is already numeric, yet casting operands upfront is a good habit when values are large integers.

### 14.4. Average Price Does Not Replace Total Revenue

`weighted_avg_unit_price` is a descriptive metric. Never round it and multiply back by quantity for invoicing or reconciliation when exact prices and quantities are stored.

## 15. When Weights Are Zero

If all weights are 0, the weighted average denominator is 0. Example:

~~~sql
WITH measurements(value, weight) AS (
    VALUES
        (10::numeric, 0::numeric),
        (20::numeric, 0::numeric)
)
SELECT
    SUM(value * weight) AS weighted_sum,
    SUM(weight) AS total_weight,
    SUM(value * weight)
        / NULLIF(SUM(weight), 0) AS weighted_avg
FROM measurements;
~~~

Result:

| weighted_sum | total_weight | weighted_avg |
|---:|---:|---|
| 0 | 0 | NULL |

**There is zero observed weight to define an average.** The average is not automatically 0.

### 15.1. Some Zero Weights Can Still Be Valid

~~~sql
WITH measurements(value, weight) AS (
    VALUES
        (10::numeric, 2::numeric),
        (99::numeric, 0::numeric),
        (20::numeric, 3::numeric)
)
SELECT
    SUM(value * weight)
    / NULLIF(SUM(weight), 0) AS weighted_avg
FROM measurements;
~~~

Numerator `10×2 + 99×0 + 20×3 = 80`, denominator `2+0+3=5`, result `16`. The zero-weight row contributes nothing to the result.

### 15.2. Negative Weights Require Explicit Business Rules

In many weighted-average problems, weights must be non-negative. If negative weights are allowed and total weight approaches 0, the result can blow up or fall outside the minimum–maximum range of values.

In sales data, returns or refunds might be recorded with negative quantities in some schemas, in which case `SUM(quantity * price)/SUM(quantity)` carries **net sales** semantics rather than a plain average selling price of sold units.

**Never strip minus signs or apply ABS(weight) before clarifying business rules.**

## 16. NULL in Values and Weights: The Mismatched Denominator Trap

A subtle bug: numerator and denominator aggregate **different row sets** due to NULLs.

~~~sql
WITH measurements(value, weight) AS (
    VALUES
        (10::numeric, 2::numeric),
        (20::numeric, NULL::numeric),
        (NULL::numeric, 5::numeric)
)
SELECT
    SUM(value * weight) AS weighted_sum,
    SUM(weight) AS total_weight,
    SUM(value * weight)
        / NULLIF(SUM(weight), 0) AS naive_weighted_avg
FROM measurements;
~~~

Numerator:

- Row `(10,2)` contributes 20.
- Row `(20,NULL)` produces a NULL product, skipped by SUM.
- Row `(NULL,5)` produces a NULL product, skipped by SUM.

Yet the denominator `SUM(weight)` still includes weight 5 from the row missing `value`, giving a total of 7. The output "20/7" is **not** the average across complete observation pairs.

### 16.1. Filter to the Same Set of Complete Pairs

~~~sql
WITH measurements(value, weight) AS (
    VALUES
        (10::numeric, 2::numeric),
        (20::numeric, NULL::numeric),
        (NULL::numeric, 5::numeric)
)
SELECT
    SUM(value * weight)
        / NULLIF(SUM(weight), 0) AS weighted_avg
FROM measurements
WHERE value IS NOT NULL
  AND weight IS NOT NULL
  AND weight > 0;
~~~

Only row `(10,2)` enters both sums, yielding an average of 10.

### 16.2. Use FILTER When Computing Multiple Metrics Together

~~~sql
WITH measurements(value, weight) AS (
    VALUES
        (10::numeric, 2::numeric),
        (20::numeric, NULL::numeric),
        (NULL::numeric, 5::numeric)
)
SELECT
    COUNT(*) AS all_rows,
    COUNT(*) FILTER (
        WHERE value IS NOT NULL
          AND weight IS NOT NULL
          AND weight > 0
    ) AS valid_pairs,
    SUM(value * weight) FILTER (
        WHERE value IS NOT NULL
          AND weight IS NOT NULL
          AND weight > 0
    )
    /
    NULLIF(
        SUM(weight) FILTER (
            WHERE value IS NOT NULL
              AND weight IS NOT NULL
              AND weight > 0
        ),
        0
    ) AS weighted_avg
FROM measurements;
~~~

In larger reports, put the valid-pair filter in a CTE to avoid repeating conditions and keep names readable.

### 16.3. Do Not Assume NULL Means 0 Everywhere

`COALESCE(value,0)` turns "unknown value" into "value equals 0." That can distort statistical analysis.

In real data, classify the cause of NULLs:

- Not applicable to this row.
- Measurement not yet available.
- Data lost during ingestion.
- Intentionally uncollected.
- True value is 0 but stored as NULL.

Only after aligning on semantics should you decide whether to filter, substitute 0, or report missing data.

## 17. FILTER: Computing Multiple Conditional Ratios in One GROUP BY

PostgreSQL supports:

~~~sql
aggregate(expression) FILTER (WHERE condition)
~~~

This gives **each aggregate its own row subset** within the same query.

Example on campaign data:

~~~sql
SELECT
    campaign_id,
    SUM(visitors) AS total_visitors,
    SUM(signups) AS total_signups,
    SUM(visitors) FILTER (
        WHERE metric_day = DATE '2026-11-10'
    ) AS visitors_on_day_10,
    SUM(visitors) FILTER (
        WHERE metric_day = DATE '2026-11-11'
    ) AS visitors_on_day_11
FROM ratio_lab.campaign_daily
GROUP BY campaign_id
ORDER BY campaign_id;
~~~

For a campaign with no rows matching a day's FILTER, `SUM(...)` on an empty filtered set returns NULL, not 0.

### 17.1. COUNT(*) FILTER for Status-Based Rates

~~~sql
WITH events(event_id, outcome) AS (
    VALUES
        (1, 'success'),
        (2, 'failure'),
        (3, 'success'),
        (4, 'success')
)
SELECT
    COUNT(*) AS total_events,
    COUNT(*) FILTER (
        WHERE outcome = 'success'
    ) AS success_events,
    ROUND(
        100.0 * COUNT(*) FILTER (
            WHERE outcome = 'success'
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS success_rate_pct
FROM events;
~~~

Result: 3/4 = 75%.

### 17.2. FILTER vs. Query-Level WHERE

If you put:

~~~sql
WHERE outcome = 'success'
~~~

then `COUNT(*)` counts only successes, no longer all events. When both total and success counts are needed in one query, `FILTER` cleanly separates numerator and denominator scopes.

### 17.3. Parentheses Matter

Write explicitly:

~~~sql
100.0 *
COUNT(*) FILTER (WHERE outcome = 'success')
/
NULLIF(COUNT(*), 0)
~~~

Wrap inside `ROUND(...,2)` when using numeric types. Never omit parentheses or accidentally attach FILTER to the wrong expression.

## 18. CASE and FILTER: Two Ways to Conditionally Aggregate

Equivalent in many cases:

~~~sql
COUNT(*) FILTER (WHERE outcome = 'success')
~~~

and:

~~~sql
SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END)
~~~

Yet note the empty-set difference:

- `COUNT(*) FILTER` returns 0 when no rows match.
- `SUM(CASE ... END)` returns NULL if **zero input rows** enter the aggregate.
- `SUM(CASE WHEN ... THEN 1 END)` can return NULL when all rows fail to match because implicit ELSE is NULL.

### 18.1. Example

~~~sql
WITH events(outcome) AS (
    VALUES ('failure'), ('failure')
)
SELECT
    COUNT(*) FILTER (
        WHERE outcome = 'success'
    ) AS success_count,
    SUM(
        CASE
            WHEN outcome = 'success' THEN 1
            ELSE 0
        END
    ) AS success_sum
FROM events;
~~~

Both return 0 because two input rows exist and CASE has `ELSE 0`.

### 18.2. Which One to Choose?

- `FILTER` is clearer when computing multiple conditional metrics.
- `CASE` is helpful when value selection or classification logic is complex.
- Both must operate on **the same unit and observation set**.

## 19. LEFT JOIN and Groups Without Data

`ratio_lab.campaigns` has four campaigns while `campaign_daily` has rows for only three. To show the full catalog, use `LEFT JOIN`:

~~~sql
SELECT
    c.campaign_id,
    c.campaign_name,
    COUNT(d.campaign_id) AS days_with_data,
    SUM(d.visitors) AS total_visitors,
    SUM(d.signups) AS total_signups,
    ROUND(
        100.0 * SUM(d.signups)
        / NULLIF(SUM(d.visitors), 0),
        2
    ) AS signup_rate_pct
FROM ratio_lab.campaigns AS c
LEFT JOIN ratio_lab.campaign_daily AS d
    ON d.campaign_id = c.campaign_id
GROUP BY c.campaign_id, c.campaign_name
ORDER BY c.campaign_id;
~~~

Expected output:

| Campaign | days_with_data | Visitors | Signups | Rate |
|---|---:|---:|---:|---:|
| Alpha | 2 | 150 | 25 | 16.67 |
| Beta | 2 | 20 | 4 | 20.00 |
| Gamma | 1 | 0 | 0 | NULL |
| Delta | 0 | NULL | NULL | NULL |

### 19.1. Gamma and Delta Differ

- **Gamma:** has recorded metrics, yet visitors=0; rate is 0/0 and undefined.
- **Delta:** has zero daily rows; we cannot tell whether it never ran, ETL is lagging, or metrics aren't logged yet.

If you use:

~~~sql
COALESCE(SUM(d.visitors), 0)
~~~

both Gamma and Delta display 0 visitors. To avoid losing that distinction, also expose `days_with_data` or a data-status column.

### 19.2. The COUNT(*) Trap on LEFT JOIN

~~~sql
COUNT(*)
~~~

counts a LEFT JOIN output row even when no right-side row matched. For Delta, `COUNT(*)` returns 1.

To count actual metric records, count a non-NULL column from the right-hand table:

~~~sql
COUNT(d.campaign_id)
~~~

### 19.3. Do Not Carelessly Put Right-Table Filters in WHERE

~~~sql
SELECT c.campaign_name, d.metric_day
FROM ratio_lab.campaigns AS c
LEFT JOIN ratio_lab.campaign_daily AS d
    ON d.campaign_id = c.campaign_id
WHERE d.metric_day >= DATE '2026-11-10';
~~~

The `WHERE` filter drops unmatched rows where `d.metric_day IS NULL`, making Delta vanish.

To keep all campaigns within a date range, move the date predicate into `ON`:

~~~sql
SELECT c.campaign_name, d.metric_day
FROM ratio_lab.campaigns AS c
LEFT JOIN ratio_lab.campaign_daily AS d
    ON d.campaign_id = c.campaign_id
   AND d.metric_day >= DATE '2026-11-10';
~~~

With outer joins, conditions in `ON` and `WHERE` are not always interchangeable.

## 20. "0%", "NULL", and "No Rows" Are Not the Same

These three cases need distinct presentations for users to make sound decisions:

~~~text
100 attempts, 0 successes -> genuine 0%
0 attempts, 0 successes   -> NULL / N/A
No attempt records        -> NULL / NO_DATA
~~~

Make this explicit in SQL:

~~~sql
SELECT
    c.campaign_name,
    COUNT(d.campaign_id) AS row_count,
    SUM(d.visitors) AS visitors,
    SUM(d.signups) AS signups,
    CASE
        WHEN COUNT(d.campaign_id) = 0 THEN 'NO_DATA'
        WHEN SUM(d.visitors) = 0 THEN 'NO_SAMPLE'
        ELSE 'COMPUTED'
    END AS rate_status,
    ROUND(
        100.0 * SUM(d.signups)
        / NULLIF(SUM(d.visitors), 0),
        2
    ) AS signup_rate_pct
FROM ratio_lab.campaigns AS c
LEFT JOIN ratio_lab.campaign_daily AS d
    ON d.campaign_id = c.campaign_id
GROUP BY c.campaign_id, c.campaign_name
ORDER BY c.campaign_id;
~~~

In the lab, statuses are:

- Alpha, Beta: `COMPUTED`.
- Gamma: `NO_SAMPLE`.
- Delta: `NO_DATA`.

For JSON APIs, this is much clearer than squeezing all states into a single numeric field.

## 21. ROAS and ROI: Similar Division, Different Meaning

In marketing:

\[
ROAS = \frac{\text{Revenue attributed to ads}}{\text{Ad spend}}
\]

ROAS is a **multiplier**, not necessarily a percentage, and can exceed 1.

Another metric:

\[
ROI = \frac{\text{Return}-\text{Investment}}{\text{Investment}}
\]

In practice, "return" and "investment" for ROI may involve cost of goods sold, operations, and other components. Never confuse an illustrative arithmetic formula with a full accounting standard.

### 21.1. Computing ROAS on the Lab Data

~~~sql
SELECT
    campaign_id,
    SUM(revenue) AS total_revenue,
    SUM(spend) AS total_spend,
    ROUND(
        SUM(revenue) / NULLIF(SUM(spend), 0),
        3
    ) AS roas
FROM ratio_lab.campaign_daily
GROUP BY campaign_id
ORDER BY campaign_id;
~~~

Expected output:

| campaign_id | total_revenue | total_spend | roas |
|---:|---:|---:|---:|
| 1 | 1,500,000 | 600,000 | 2.500 |
| 2 | 160,000 | 80,000 | 2.000 |
| 3 | 0 | 0 | NULL |

Gamma has zero spend, so ROAS is undefined under this division even though revenue is also 0. Do not turn 0/0 into a ROAS of 0.

### 21.2. Illustrative "Net Return Ratio"

~~~sql
SELECT
    campaign_id,
    ROUND(
        (SUM(revenue) - SUM(spend))
        / NULLIF(SUM(spend), 0),
        3
    ) AS illustrative_net_return_ratio
FROM ratio_lab.campaign_daily
GROUP BY campaign_id
ORDER BY campaign_id;
~~~

This is merely an illustrative `(revenue - ad_spend)/ad_spend` ratio, **not full accounting ROI** if COGS, taxes, fees, or other expenses apply.

### 21.3. Never Average Daily ROAS to Compute Period ROAS

Alpha's ROAS on day 1 is 1,200,000 / 400,000 = 3.0; on day 2 it is 300,000 / 200,000 = 1.5.

The simple average of the two days is 2.25, while period ROAS is:

\[
\frac{1500000}{600000}=2.5
\]

Sum total revenue and total spend across the period instead of averaging ratios without spend weights.

## 22. Each Group's Share of Total

Another question: "What percentage of total revenue does each campaign contribute?"

\[
\text{Share}_i=\frac{\text{Revenue}_i}{\sum_j \text{Revenue}_j}
\]

We can use a window function:

~~~sql
WITH revenue_by_campaign AS (
    SELECT
        c.campaign_id,
        c.campaign_name,
        COALESCE(SUM(d.revenue), 0::numeric) AS revenue
    FROM ratio_lab.campaigns AS c
    LEFT JOIN ratio_lab.campaign_daily AS d
        ON d.campaign_id = c.campaign_id
    GROUP BY c.campaign_id, c.campaign_name
)
SELECT
    campaign_name,
    revenue,
    ROUND(
        100.0 * revenue
        / NULLIF(SUM(revenue) OVER (), 0),
        2
    ) AS revenue_share_pct
FROM revenue_by_campaign
ORDER BY campaign_id;
~~~

In the lab, total revenue is 1,660,000; Alpha accounts for approx. **90.36%**, Beta **9.64%**, and Gamma/Delta **0%**.

### 22.1. Why Compute Overall SUM After GROUP BY?

The CTE yields **one row per campaign**. The window `SUM(revenue) OVER ()` sums those campaign-level totals to form the shared denominator, avoiding a self-join across all groups.

### 22.2. When Total Revenue Is Zero

If every campaign has 0 revenue, `NULLIF(SUM(revenue) OVER (),0)` evaluates to NULL, so shares become NULL. There is no positive total revenue to define a share.

### 22.3. Share Differs from Growth Rate

A group with revenue 100 out of a 1,000 total has a 10% share. If last month's revenue was 80, growth is `(100-80)/80 = 25%`. Both metrics use **different denominators**.

## 23. Growth Rate and Zero Prior-Period Denominators

Growth rate is typically defined as:

\[
g=\frac{current-previous}{previous}
\]

Example:

~~~sql
WITH periods(previous_value, current_value) AS (
    VALUES
        (80::numeric, 100::numeric),
        (0::numeric, 100::numeric),
        (0::numeric, 0::numeric)
)
SELECT
    previous_value,
    current_value,
    ROUND(
        100.0 * (current_value - previous_value)
        / NULLIF(previous_value, 0),
        2
    ) AS growth_pct
FROM periods;
~~~

Result:

| previous | current | growth_pct |
|---:|---:|---:|
| 80 | 100 | 25.00 |
| 0 | 100 | NULL |
| 0 | 0 | NULL |

An increase from 0 to 100 cannot be expressed as a standard percentage with a 0 denominator. Reports may display "New", "From zero", or absolute delta instead of a percentage.

### 23.1. Valid Negative Growth

If previous period is 100 and current is 80:

~~~sql
SELECT
    100.0 * (80::numeric - 100)
    / NULLIF(100, 0) AS growth_pct;
~~~

Result: **-20%**. Negative values are not division errors—they reflect genuine decline.

### 23.2. Negative Previous Values Need Explicit Rules

In accounting, a metric may be negative due to losses or adjustments. Applying the standard growth formula with a negative denominator can yield counterintuitive signs. Never apply growth formulas mechanically without defining semantics for negative values and sign flips.

## 24. Weighted Averages Across Multiple Aggregation Levels

A common BI mistake: having a daily report with `avg_unit_price` and `units_sold`, then rolling up to the month.

Given:

~~~text
Day 1: 10 units, avg_price 100
Day 2: 90 units, avg_price  50
~~~

The simple average of the two daily averages is 75, whereas the true period average is:

\[
\frac{10\times100+90\times50}{10+90}=55
\]

### 24.1. Store Numerators and Weights in Aggregate Tables

Instead of storing only:

~~~text
day, avg_unit_price
~~~

store:

~~~text
day, sales_amount, units_sold
~~~

Then compute:

~~~sql
SELECT
    SUM(sales_amount) / NULLIF(SUM(units_sold), 0)
        AS overall_avg_unit_price
FROM daily_product_stats;
~~~

This is a structural example requiring a `daily_product_stats` table if executed verbatim.

### 24.2. When Is an Average of Averages Still Valid?

If every group has the exact same **count of valid observations** or equal weight by definition, the simple mean of group means equals the overall mean. Never assume that condition holds by default.

### 24.3. Do Not Round Intermediate Averages Before Rolling Up

If you store daily averages rounded to 2 decimals and multiply back by units, rounding errors accumulate. Store exact summed values and weights, and **round only at the final presentation layer**.

## 25. JOIN Fan-Out: Aggregation Can Break Before Division

Suppose `orders` has one row per order and `order_items` has many rows per order.

~~~text
orders
  order_id=1, shipping_fee=20

order_items
  (order=1, product=A)
  (order=1, product=B)
  (order=1, product=C)
~~~

If you JOIN and run `SUM(o.shipping_fee)`, the 20 shipping fee gets summed **three times** because the order repeats across three items.

### 25.1. Error-Prone Structural Example

~~~sql
SELECT
    SUM(o.shipping_fee) AS wrong_shipping_sum
FROM orders AS o
JOIN order_items AS i
    ON i.order_id = o.order_id;
~~~

An aggregate is not guaranteed right merely because it uses `SUM`.

### 25.2. Solution: Aggregate at the Right Granularity

Pre-aggregate order items to order level before joining:

~~~sql
WITH item_totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS item_amount
    FROM order_items
    GROUP BY order_id
)
SELECT
    SUM(o.shipping_fee) AS total_shipping,
    SUM(i.item_amount) AS total_items
FROM orders AS o
JOIN item_totals AS i
    ON i.order_id = o.order_id;
~~~

This pattern aggregates at **order granularity** before joining. Mind the join type: INNER JOIN drops orders without items; if all orders must remain, use LEFT JOIN and explicit NULL handling.

### 25.3. A Ratio Can Break Even When Both Numerator and Denominator Are Multiplied

Sometimes multiplying both numerator and denominator equally happens to yield the original ratio, hiding the bug in simple tests. Once orders have varying numbers of items, multiplication becomes **uneven**, skewing ratios and weighted averages.

Clarify:

- Does one post-JOIN row represent an order, line item, customer, or event?
- Are any measurements duplicated?
- At what level should weights be summed?
- Do you want an average per person, per order, or per item?

## 26. COUNT DISTINCT: Ratios Over Unique Entities

When an event table has multiple events per user, you may need unique user counts.

~~~sql
WITH visits(user_id, did_signup) AS (
    VALUES
        (101, FALSE),
        (101, TRUE),
        (102, FALSE),
        (103, TRUE),
        (103, TRUE)
)
SELECT
    COUNT(DISTINCT user_id) AS distinct_users,
    COUNT(DISTINCT user_id) FILTER (
        WHERE did_signup
    ) AS distinct_signed_up_users,
    ROUND(
        100.0 * COUNT(DISTINCT user_id) FILTER (
            WHERE did_signup
        )
        / NULLIF(COUNT(DISTINCT user_id), 0),
        2
    ) AS user_conversion_pct
FROM visits;
~~~

There are 3 unique users (101, 102, 103), of whom 2 had a TRUE signup event. User-level conversion rate is **66.67%**.

### 26.1. What If COUNT(*) Replaced COUNT DISTINCT?

There are 5 events and 3 with `did_signup=TRUE`, giving an event-level rate of 60%. That measures a different unit.

### 26.2. When Is DISTINCT Not Enough?

- One user may have multiple device IDs.
- Bot events or invalid traffic exist.
- Numerator and denominator cover mismatched observation periods.
- Identity mapping is incomplete or changes over time.

These are data-modeling and product questions that adding `DISTINCT` alone cannot solve.

## 27. FILTER and Measurement Period Conditions Must Match

A KPI can accidentally take its numerator from a filtered subset while taking its denominator from the entire table, silently changing its meaning.

For example, signup rate **in November**:

~~~sql
SELECT
    ROUND(
        100.0 * SUM(signups) FILTER (
            WHERE metric_day >= DATE '2026-11-01'
              AND metric_day < DATE '2026-12-01'
        )
        /
        NULLIF(
            SUM(visitors) FILTER (
                WHERE metric_day >= DATE '2026-11-01'
                  AND metric_day < DATE '2026-12-01'
            ),
            0
        ),
        2
    ) AS november_signup_rate_pct
FROM ratio_lab.campaign_daily;
~~~

For a single target period, filtering once in `WHERE` and summing cleanly is simpler and easier to read:

~~~sql
SELECT
    ROUND(
        100.0 * SUM(signups)
        / NULLIF(SUM(visitors), 0),
        2
    ) AS november_signup_rate_pct
FROM ratio_lab.campaign_daily
WHERE metric_day >= DATE '2026-11-01'
  AND metric_day < DATE '2026-12-01';
~~~

### 27.1. When Does FILTER Make More Sense Than WHERE?

When one report row needs metrics across **multiple periods or multiple distinct conditions**, `FILTER` lets you compute several sums in a single `GROUP BY` pass. When numerator and denominator share the exact same set, `WHERE` is cleaner.

### 27.2. Date and timestamptz Must Follow the Business Time Zone

With an event table storing `occurred_at TIMESTAMPTZ`, filtering "Nov 14 in Vietnam" requires converting both local boundaries to instants:

~~~sql
WHERE occurred_at >= (
    TIMESTAMP '2026-11-14 00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
AND occurred_at < (
    TIMESTAMP '2026-11-15 00:00'
    AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
~~~

Computing the numerator by Vietnam dates and the denominator by UTC dates skews the ratio. Both parts of a KPI must use the **same time-window convention**.

## 28. Computing Shares of Total with Window Functions

Window functions compute shares without collapsing individual output rows.

### 28.1. Each Line's Share of Category Revenue

~~~sql
SELECT
    sale_line_id,
    category,
    quantity * unit_price AS line_revenue,
    ROUND(
        100.0 * quantity * unit_price
        / NULLIF(
            SUM(quantity * unit_price) OVER (
                PARTITION BY category
            ),
            0
        ),
        2
    ) AS category_revenue_share_pct
FROM ratio_lab.sales_lines
ORDER BY category, sale_line_id;
~~~

Each row shows its revenue percentage relative to **that category's total revenue**.

### 28.2. Distinguishing OVER() and OVER(PARTITION BY ...)

- `OVER ()` computes over the entire window input set.
- `OVER (PARTITION BY category)` computes within each category.

Picking the wrong partition can make percentages divide by the grand total instead of the group total.

### 28.3. Avoid Window Calculations Over JOIN-Multiplied Rows

Window functions run over the query's row set at the window stage. If `FROM`/`JOIN` duplicated rows, the window denominator is inflated too. Fix input granularity upstream rather than trying to mask fan-out with windows.

## 29. ROUND: Where Should Rounding Happen?

PostgreSQL supports:

~~~sql
SELECT ROUND(16.666666::numeric, 2) AS rounded_percentage;
~~~

Result: `16.67`.

### 29.1. Rounding at the End vs. Rounding Parts and Summing

Suppose two unrounded shares are 33.333...% and 66.666...%. Rounding parts first and summing across many groups can yield 99.99% or 100.01% due to rounding drift.

Arithmetically, never sum pre-rounded ratios to build a higher-level KPI. Store **summed numerators/denominators** or unrounded numeric values and round only for display.

### 29.2. ROUND Overloads Depend on Type

~~~sql
SELECT ROUND(1.2345::numeric, 2);
~~~

This works for `numeric` with a scale parameter.

For `double precision`, two-argument `ROUND(double precision, integer)` is not supported like `numeric`; if you need two decimal places, cast to numeric where appropriate:

~~~sql
SELECT ROUND(1.2345::double precision::numeric, 2);
~~~

Note that casting an approximate floating-point number to `numeric` cannot recover precision already lost earlier.

### 29.3. Rounding vs. Formatting the % Sign

When SQL returns `16.67` in `signup_rate_pct`, the UI can format it as `16.67%`. Avoid using `TO_CHAR` to bake `%` strings in every layer if APIs need numeric types for sorting or further calculation.

## 30. NUMERIC vs. DOUBLE PRECISION

PostgreSQL has two common numeric families in analytics:

- `NUMERIC` for exact decimal calculations suited to finance/unit counts and explicit rounding control.
- `REAL`/`DOUBLE PRECISION` for approximate binary floating point, often faster and suited to scientific/statistical measurements.

### 30.1. For Money, Prefer NUMERIC When Exact Decimals Are Required

~~~sql
SELECT
    0.1::numeric + 0.2::numeric AS decimal_sum;
~~~

`numeric` fits currency well because it avoids binary representation inaccuracies inherent in floating point.

### 30.2. For Large Measurements, double precision Has Trade-Offs

When source values are `double precision`, sums and products carry floating-point approximation error. That does not mean data is broken, yet reports must account for expected precision.

### 30.3. Cast Before Multiplying to Prevent Integer Overflow

If quantity and price are large integers:

~~~sql
SELECT
    2000000000::numeric * 2000000000::numeric
    AS product_without_integer_overflow;
~~~

If integer multiplication already overflowed, casting afterward is too late. Use a sufficiently wide type **on the operands themselves**.

### 30.4. AVG and SUM Return Different Types Depending on Input

In PostgreSQL, `AVG(integer)` returns `numeric`, whereas `SUM(integer)` returns `bigint`. Never assume `SUM(integer)/COUNT(*)` preserves decimals automatically just because `AVG(integer)` returns numeric.

Use directly:

~~~sql
SELECT AVG(quantity) FROM ratio_lab.sales_lines;
~~~

or cast explicitly when writing the division yourself:

~~~sql
SELECT
    SUM(quantity)::numeric / NULLIF(COUNT(*), 0)
FROM ratio_lab.sales_lines;
~~~

## 31. Rules When Negative Values Exist

A ratio like `revenue/spend` normally expects non-negative spend. If spend goes negative due to credit/adjustment entries, overall ROAS can change meaning.

A weighted average with negative weights also loses the property of lying between the minimum and maximum values.

### 31.1. Scope Data Before Calculating

If analyzing sales only, separate returns/refunds per business rules or model distinct transaction types in the fact table.

### 31.2. Do Not Blindly Use ABS or GREATEST

~~~sql
-- Do not use these by default to "patch" a KPI:
-- SUM(ABS(weight) * value) / SUM(ABS(weight))
-- GREATEST(spend, 1)
~~~

These operations **alter the metric definition**, not merely prevent technical errors. In particular, `GREATEST(denominator,1)` turns zero-attempt groups into fake 1-attempt groups, silently distorting KPIs.

## 32. Assessing Data Quality Before Aggregating

A ratio can turn negative, exceed 100%, return NULL, or hit a zero denominator. Before tweaking formulas, run an audit query.

### 32.1. Checking Campaign Data

~~~sql
SELECT
    campaign_id,
    metric_day,
    visitors,
    signups
FROM ratio_lab.campaign_daily
WHERE visitors < 0
   OR signups < 0
   OR signups > visitors
   OR visitors IS NULL
   OR signups IS NULL;
~~~

In the lab with proper constraints, this returns zero rows. In real pipelines with staging tables lacking constraints or mixed metric feeds, anomalies can appear.

### 32.2. Counting Zero-Denominator Groups

~~~sql
SELECT
    campaign_id,
    COUNT(*) AS days_total,
    COUNT(*) FILTER (
        WHERE visitors = 0
    ) AS days_with_zero_visitors,
    COUNT(*) FILTER (
        WHERE visitors > 0
    ) AS days_with_positive_visitors
FROM ratio_lab.campaign_daily
GROUP BY campaign_id
ORDER BY campaign_id;
~~~

Knowing how many days had zero sample helps analysts judge reliability and coverage.

### 32.3. Reporting Coverage

If a 30-day KPI has data for only 4 days, the 4-day rate may be valid SQL yet fail to represent the full month. Track:

- Days with data.
- Expected total days.
- ETL latency.
- Unprocessed or late-arriving events.
- Whether the denominator covers the full population or only observed rows.

This is part of **data quality**, which `NULLIF` alone cannot fix.

## 33. HAVING: Filtering Groups After Aggregation

Sometimes a report wants only groups with positive denominators.

~~~sql
SELECT
    campaign_id,
    SUM(visitors) AS total_visitors,
    ROUND(
        100.0 * SUM(signups)
        / NULLIF(SUM(visitors), 0),
        2
    ) AS signup_rate_pct
FROM ratio_lab.campaign_daily
GROUP BY campaign_id
HAVING SUM(visitors) > 0
ORDER BY campaign_id;
~~~

Gamma is excluded because its total visitors equal 0.

### 33.1. HAVING vs. WHERE

- `WHERE` filters **source rows** before grouping.
- `HAVING` filters **output groups** after aggregation.

Do not write:

~~~sql
WHERE SUM(visitors) > 0
~~~

because aggregates cannot appear directly in same-level `WHERE` conditions.

### 33.2. Should You Exclude Zero-Sample Groups?

Depends on the report:

- A "top campaigns with traffic" leaderboard may exclude zero-traffic groups.
- A monitoring dashboard needs zero-traffic groups visible to catch campaigns that never launched.
- A data-quality report should keep zero groups and expose their status.

Never add `HAVING` just to dodge division by zero and accidentally hide important groups.

## 34. Multi-Dimensional GROUP BY and Higher-Level Totals

With campaign, date, channel, and geography dimensions, define the grouping grain before computing ratios.

Example using campaign and date in the lab data:

~~~sql
SELECT
    metric_day,
    SUM(visitors) AS total_visitors,
    SUM(signups) AS total_signups,
    ROUND(
        100.0 * SUM(signups)
        / NULLIF(SUM(visitors), 0),
        2
    ) AS signup_rate_pct
FROM ratio_lab.campaign_daily
GROUP BY metric_day
ORDER BY metric_day;
~~~

A daily rate across all campaigns must compute **daily total signups / daily total visitors**, not average per-campaign rates unless each campaign is intentionally treated as an equal-weight observation.

### 34.1. Rolling Up Days to Months

~~~sql
SELECT
    date_trunc('month', metric_day::timestamp)::date
        AS metric_month,
    SUM(visitors) AS visitors,
    SUM(signups) AS signups,
    ROUND(
        100.0 * SUM(signups)
        / NULLIF(SUM(visitors), 0),
        2
    ) AS signup_rate_pct
FROM ratio_lab.campaign_daily
GROUP BY 1
ORDER BY 1;
~~~

The monthly denominator is total visitors across the matching period and scope.

### 34.2. GROUPING SETS / ROLLUP

PostgreSQL supports `ROLLUP` or `GROUPING SETS` for multi-level aggregation.

~~~sql
SELECT
    campaign_id,
    metric_day,
    SUM(visitors) AS visitors,
    SUM(signups) AS signups,
    ROUND(
        100.0 * SUM(signups)
        / NULLIF(SUM(visitors), 0),
        2
    ) AS signup_rate_pct
FROM ratio_lab.campaign_daily
GROUP BY ROLLUP (campaign_id, metric_day)
ORDER BY campaign_id NULLS LAST, metric_day NULLS LAST;
~~~

Subtotal and grand total rows must be distinguished via `GROUPING()` when grouping columns can hold real NULLs. Crucially: **every ROLLUP level recomputes the ratio from summed numerators and summed denominators**, never by averaging rounded lower-level ratios.

## 35. Performance: Reduce Volume Before Dividing

In PostgreSQL, division itself is rarely the bottleneck. In large reports, cost typically comes from:

- Scanning large datasets.
- JOINs multiplying row counts.
- `GROUP BY` across many keys.
- Large sorts or hash aggregates.
- Heavy casts and functions evaluated per row.
- Transferring large results to the application.

### 35.1. Filter Time Range Before Aggregating

~~~sql
SELECT
    campaign_id,
    SUM(signups)::numeric
        / NULLIF(SUM(visitors), 0) AS signup_rate
FROM ratio_lab.campaign_daily
WHERE metric_day >= DATE '2026-11-01'
  AND metric_day < DATE '2026-12-01'
GROUP BY campaign_id;
~~~

If reports routinely filter by date and group by campaign, consider an index:

~~~sql
CREATE INDEX idx_campaign_daily_day_campaign
ON ratio_lab.campaign_daily (metric_day, campaign_id);
~~~

Because the lab table is tiny, PostgreSQL will likely still pick a sequential scan. Never create indexes solely because a column appears in `GROUP BY`; consider workload, selectivity, write overhead, and query plans.

### 35.2. Using EXPLAIN

~~~sql
EXPLAIN
SELECT
    campaign_id,
    SUM(signups)::numeric
        / NULLIF(SUM(visitors), 0) AS signup_rate
FROM ratio_lab.campaign_daily
GROUP BY campaign_id;
~~~

`EXPLAIN` shows the estimated plan. On safe test data:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    campaign_id,
    SUM(signups)::numeric
        / NULLIF(SUM(visitors), 0) AS signup_rate
FROM ratio_lab.campaign_daily
GROUP BY campaign_id;
~~~

`EXPLAIN ANALYZE` **actually runs the SELECT** to measure rows and timing. On DML it also executes modifications unless rolled back appropriately.

### 35.3. Partial Aggregates and Materialized Views

When computing the same daily/monthly metrics across billions of events, consider storing **summed numerators and summed denominators** in an aggregate table or materialized view, then dividing at read time.

Avoid storing only pre-rounded ratios, since rolling them up accurately across periods is difficult.

Example summary table structure:

~~~sql
CREATE TABLE ratio_lab.campaign_month_summary (
    campaign_id INTEGER NOT NULL,
    metric_month DATE NOT NULL,
    total_visitors BIGINT NOT NULL CHECK (total_visitors >= 0),
    total_signups BIGINT NOT NULL CHECK (total_signups >= 0),
    PRIMARY KEY (campaign_id, metric_month),
    CHECK (total_signups <= total_visitors)
);
~~~

The ETL layer must ensure totals update accurately without double-counting on retries and stay synchronized with source data. Merely having a summary table does not guarantee accurate numbers.

## 36. Java Integration: Handling NULL Ratios

When SQL returns `NULL` for an undefined ratio, the application must not silently coerce NULL to 0 just because a primitive `double` field cannot hold null.

With PostgreSQL/JDBC:

~~~java
import java.math.BigDecimal;
import java.sql.ResultSet;

BigDecimal rate = rs.getBigDecimal("signup_rate_pct");

if (rate == null) {
    // Display "Insufficient data" per the API contract.
} else {
    // Format percentage according to the user's locale.
}
~~~

`rs` is assumed to be a `ResultSet` positioned on a valid row.

### 36.1. JSON Representation in APIs

A clear response shape:

~~~json
{
  "campaign": "Gamma",
  "totalVisitors": 0,
  "totalSignups": 0,
  "signupRatePct": null,
  "rateStatus": "NO_SAMPLE"
}
~~~

This is an illustrative JSON literal, not PostgreSQL SQL. The API clearly separates a true 0% from having no sample.

### 36.2. BigDecimal and Monetary Ratios

If Java recomputes average prices, use `BigDecimal` with explicit scale and rounding modes. For financial reporting, never multiply `double` values and hope every decimal digit stays exact.

### 36.3. Do Not Compute the Same KPI Twice Using Different Formulas

If PostgreSQL returns `signup_rate_pct=16.67`, the frontend should not recompute `25/150` with a different rounding rule in the same view without alignment. Either return **raw numerator/denominator** for one layer to compute, or return a single well-defined ratio.

## 37. Testing Results and Edge Cases

Any ratio or weighted-average query should be tested against at least:

1. Zero numerator, positive denominator.
2. Both numerator and denominator equal to 0.
3. Empty input row set.
4. Positive numerator with zero denominator (if permitted by data).
5. Some rows with zero denominator while total denominator is positive.
6. Two groups of vastly different sizes.
7. Zero weights.
8. NULL weights.
9. NULL value `x` with positive weight.
10. Negative weights (if permitted by model).
11. Two joined sources multiplying rows.
12. Report dates differing from the session time zone.
13. Very large amounts or numerators.
14. Rounding at the end vs. rounding per group.
15. Dimension groups with zero actual rows.

### 37.1. Small Arithmetic Sanity Test

~~~sql
WITH example(numerator, denominator) AS (
    VALUES
        (0::numeric, 10::numeric),
        (5::numeric, 10::numeric),
        (0::numeric, 0::numeric),
        (5::numeric, 0::numeric)
)
SELECT
    numerator,
    denominator,
    numerator / NULLIF(denominator, 0) AS ratio
FROM example;
~~~

Results: 0, 0.5, NULL, NULL.

### 37.2. Verifying Weighted Average Against a Known Answer

~~~sql
WITH prices(price, quantity) AS (
    VALUES
        (100000::numeric, 2::numeric),
        (160000::numeric, 1::numeric),
        (50000::numeric, 7::numeric)
)
SELECT
    SUM(price * quantity)
    / NULLIF(SUM(quantity), 0) AS weighted_avg_price
FROM prices;
~~~

Expected result: **71000**.

### 37.3. Verifying Overall Rate

~~~sql
WITH days(visitors, signups) AS (
    VALUES
        (100::numeric, 20::numeric),
        (50::numeric, 5::numeric)
)
SELECT
    ROUND(
        100.0 * SUM(signups)
        / NULLIF(SUM(visitors), 0),
        2
    ) AS total_rate_pct,
    ROUND(
        AVG(
            100.0 * signups / NULLIF(visitors, 0)
        ),
        2
    ) AS avg_daily_rate_pct
FROM days;
~~~

Expected results: **16.67** and **15.00**. This test directly illustrates why you cannot replace an overall rate with an average of sub-rates.

## 38. Common Mistakes

### 38.1. Dividing Two Integers Then Casting

Wrong:

~~~sql
(1 / 2)::numeric
~~~

Right:

~~~sql
1::numeric / 2
~~~

### 38.2. Leaving Zero Denominators Unguarded

Wrong:

~~~sql
SUM(signups)::numeric / SUM(visitors)
~~~

When total visitors equal 0, PostgreSQL raises an error.

Right:

~~~sql
SUM(signups)::numeric / NULLIF(SUM(visitors), 0)
~~~

### 38.3. Turning Every NULL into 0

`COALESCE(ratio,0)` can erase the distinction between **true 0%** and **insufficient sample**.

### 38.4. Averaging Daily Rates to Get Monthly Rate

Wrong when seeking the overall period rate across varying daily visitor counts. Use total numerator / total denominator.

### 38.5. Using AVG(unit_price) for Average Price per Unit Sold

When line quantities differ, you must weight by quantity.

### 38.6. Using AVG(value * weight)

`AVG` divides by valid row count, not total weight; that is not a weighted average.

### 38.7. Numerator and Denominator Using Different Row Sets Due to NULL

`SUM(value*weight)` skips rows missing `value`, while `SUM(weight)` still adds their weight. Keep observation pairs consistent.

### 38.8. Using COUNT(*) After LEFT JOIN to Count Right-Side Rows

An unmatched LEFT JOIN still emits a row, so `COUNT(*)` does not count actual right-side rows. Use `COUNT(right_table.nonnull_key)`.

### 38.9. Filtering Right-Side Columns in WHERE After LEFT JOIN

Can eliminate zero-data groups you intended to keep.

### 38.10. Mixing Users and Events

The SQL still yields a number, yet the metric mixes incompatible definitions.

### 38.11. Rounding Sub-Rates Before Combining

Rounding cannot substitute for aggregating raw numerators and denominators.

### 38.12. Failing to Guard Multiplication Against Overflow

Casting after integers overflow is too late. Widen the operand types beforehand.

### 38.13. Using GREATEST(denominator,1) to Avoid Zero

This silently fabricates a denominator of 1 and corrupts KPIs.

### 38.14. Using ABS(weight) to Strip Negative Signs

Can alter return/adjustment semantics. Clarify with business owners first.

### 38.15. Using DISTINCT to Fix JOIN Fan-Out

`DISTINCT` neither restores the true relationship between orders and items nor preserves valid rows sharing identical values.

### 38.16. Treating ROAS as a 0–100% Conversion Rate

ROAS is a revenue-to-spend multiplier that can exceed 1. Signup rate is a subset-to-whole ratio with different bounds.

### 38.17. Computing a Ratio Across Mismatched Time Windows

Mismatched time boundaries corrupt KPIs even when SQL runs error-free.

### 38.18. Treating NULL and Zero Rows as Identical

A group with rows and a 0 denominator differs from a group with no source records at all.

### 38.19. Assuming Every Rate Needs 2 Decimal Places

Display precision depends on business context. Tiny sample sizes may warrant reliability warnings rather than extra decimal digits.

### 38.20. Mathematically Valid Metric Answering the Wrong Question

Both a 15% daily average and a 16.67% period rate are valid calculations; only one answers "what percentage of period visitors signed up?"

## 39. Practice Exercises

### Exercise 1 — Integer Division

Predict the output:

~~~sql
SELECT 3 / 4, 3::numeric / 4;
~~~

**Hint:** 0 and 0.75.

### Exercise 2 — Division by Zero

Write an expression for 5/0 returning NULL instead of an error.

**Solution:**

~~~sql
SELECT 5::numeric / NULLIF(0, 0);
~~~

### Exercise 3 — Distinguishing 0 from Undefined

Why is 0/100 = 0% while 0/0 should not default to 0%?

**Hint:** The first had 100 observed opportunities with zero successes; the second had no sample to evaluate.

### Exercise 4 — Daily Conversion Rate

Use `ratio_lab.campaign_daily` to compute daily signup percentage, returning NULL when visitors=0.

~~~sql
SELECT
    campaign_id,
    metric_day,
    ROUND(
        100.0 * signups / NULLIF(visitors,0),
        2
    ) AS signup_rate_pct
FROM ratio_lab.campaign_daily;
~~~

### Exercise 5 — Overall Campaign Rate

Alpha has 20/100 and 5/50. Compute the period rate.

**Hint:** `(20+5)/(100+50) = 16.67%` after rounding.

### Exercise 6 — AVG of Rates

Why does `AVG(20%, 10%) = 15%` differ from Alpha's overall period rate?

**Hint:** The two days had 100 and 50 visitors—not equal weights.

### Exercise 7 — Weighted Average Unit Price

Books sold 2 units at 100,000, 1 unit at 160,000, and 7 units at 50,000. What is the average price per unit?

**Hint:** 71,000.

### Exercise 8 — Broken Formula

Why doesn't `AVG(quantity * unit_price)` compute the quantity-weighted average selling price?

**Hint:** `AVG` divides by row count, not total quantity.

### Exercise 9 — Zero Weights

Two observations both have weight 0. What does the weighted average return?

**Hint:** NULL / undefined under the standard formula.

### Exercise 10 — Incomplete Value-Weight Pair

The third value is NULL while its weight is 5. Should weight 5 be added to the denominator when the numerator skips that row?

**Hint:** No, if computing a weighted average across complete observation pairs.

### Exercise 11 — COUNT FILTER

Compute the rate of events with `outcome='success'` using `COUNT(*) FILTER` and denominator `COUNT(*)`.

**Hint:** Cast the numerator to `numeric` and protect the denominator with `NULLIF`.

### Exercise 12 — LEFT JOIN

Campaign Delta has no daily rows. Why can `COUNT(*)` after a `LEFT JOIN` equal 1?

**Hint:** One output row preserves the left-side campaign, even though right-side columns are NULL.

### Exercise 13 — Gamma vs. Delta

Gamma has visitors=0 on one day; Delta has no daily rows at all. What column helps distinguish them?

**Hint:** `COUNT(d.campaign_id)` and a data-status column.

### Exercise 14 — ROAS

Alpha has revenue=1,500,000 and spend=600,000. What is period ROAS?

**Answer:** 2.5.

### Exercise 15 — Average Daily ROAS

Alpha has daily ROAS of 3.0 and 1.5 across two days. Why does AVG=2.25 differ from period ROAS=2.5?

**Hint:** The two days had spend of 400,000 and 200,000; spend weights differ.

### Exercise 16 — Revenue Share

Alpha has revenue 1,500,000 and Beta has 160,000. What percentage of the two campaigns' combined revenue does Alpha represent?

**Hint:** Approx. 90.36%.

### Exercise 17 — Growth from 0

Previous period revenue=0, current=100. Should growth return 100%?

**Hint:** Standard percentage growth is undefined with a 0 denominator; return NULL or a label like "New".

### Exercise 18 — Row-Multiplying JOIN

An order has 3 `order_items` and `shipping_fee=20`. After an INNER JOIN, what can `SUM(shipping_fee)` become?

**Hint:** 60, if the order's fee is multiplied across all 3 items.

### Exercise 19 — User-Level Conversion

There are 5 visit events from 3 unique users; 2 users signed up. What is user-level conversion rate?

**Hint:** 2/3 ≈ 66.67%; do not put event count in the denominator.

### Exercise 20 — Monthly GROUP BY

Write a query computing monthly signup rate from `campaign_daily`, without averaging daily rates.

**Hint:** `GROUP BY` month and `SUM(signups)::numeric / NULLIF(SUM(visitors),0)`.

### Exercise 21 — HAVING

Return only campaigns with total visitors > 0.

**Hint:** `HAVING SUM(visitors) > 0`.

### Exercise 22 — Rounding at the Right Time

Why should percentages be rounded after summing numerators and denominators?

**Hint:** Avoids rounding drift across intermediate groups.

### Exercise 23 — Double Precision

Why can `NUMERIC` suit decimal revenue and spend better than `DOUBLE PRECISION`?

**Hint:** `NUMERIC` provides exact decimal arithmetic; `double precision` uses approximate binary floating point.

### Exercise 24 — Fake Denominator

Why does replacing `NULLIF(spend,0)` with `GREATEST(spend,1)` corrupt ROAS?

**Hint:** It replaces a real denominator of 0 with a fake 1 when `spend=0`.

### Exercise 25 — API Rate Display

If PostgreSQL returns `signup_rate_pct=NULL`, what should the JSON and UI convey?

**Hint:** Return `null` alongside `rateStatus=NO_SAMPLE` and display "Insufficient data," rather than silently converting it to 0%.

## 40. Quick Reference Table

| Need | PostgreSQL Formula |
|---|---|
| Decimal ratio | `numerator::numeric / NULLIF(denominator,0)` |
| Percentage | `100.0 * numerator / NULLIF(denominator,0)` |
| Ratio of sums | `SUM(numerator)::numeric / NULLIF(SUM(denominator),0)` |
| Percentage rounded to 2 decimals | `ROUND(100.0 * SUM(num)/NULLIF(SUM(den),0),2)` |
| Arithmetic mean | `AVG(value)` |
| Weighted average | `SUM(value*weight)/NULLIF(SUM(weight),0)` |
| Average price per unit | `SUM(quantity*unit_price)/NULLIF(SUM(quantity),0)` |
| Event success rate | `COUNT(*) FILTER (WHERE success)::numeric / NULLIF(COUNT(*),0)` |
| Count non-NULL column values | `COUNT(column)` |
| Count all rows | `COUNT(*)` |
| Share of overall total | `value / NULLIF(SUM(value) OVER (),0)` |
| Share within partition | `value / NULLIF(SUM(value) OVER (PARTITION BY group_key),0)` |
| ROAS | `SUM(revenue)/NULLIF(SUM(spend),0)` |
| Growth rate | `(current-previous)/NULLIF(previous,0)` |
| Detect groups with data | `COUNT(right_table.nonnull_key)` |
| Groups with positive denominator | `HAVING SUM(denominator)>0` |
| Round numeric | `ROUND(expression::numeric,2)` |
| NULL on zero denominator | `NULLIF(denominator,0)` |
| Show 0 instead of NULL when contract allows | `COALESCE(expression,0)` |
| Filter groups vs. rows | `GROUP BY`, `HAVING` |
| Multiple conditional sums | `aggregate(...) FILTER (WHERE ...)` |
| Inspect query plan | `EXPLAIN` |
| Measure executed query | `EXPLAIN (ANALYZE, BUFFERS)` |

---

## Conclusion

When computing **ratios**, **weighted averages**, and handling **division by zero** in PostgreSQL, the primary challenge is not syntax—it is **the meaning of the numerator, denominator, and unit of observation**. A division can run cleanly yet return wrong metrics if the two sets have mismatched scopes, if a JOIN multiplies rows, or if sub-rates are averaged instead of computing the ratio of totals.

Three essential SQL patterns to remember:

~~~sql
-- 1. Ratio of sums; preserve decimals and guard against division by zero.
SUM(numerator)::numeric / NULLIF(SUM(denominator), 0)

-- 2. Weighted average; value-weight pairs must come from the same row set.
SUM(value * weight) / NULLIF(SUM(weight), 0)

-- 3. Percentage rounded for display.
ROUND(
    100.0 * SUM(numerator) / NULLIF(SUM(denominator), 0),
    2
)
~~~

These are **conceptual expression patterns**; substitute `numerator`, `denominator`, `value`, and `weight` with real columns or expressions.

Let `NULLIF` guard zero denominators, use `COALESCE` only when 0 carries real meaning, cast operands before divisions or multiplications that risk precision loss or overflow, and round only after aggregating. When storing daily or grouped summary tables, keep **summed numerators and summed denominators** so higher-level periods roll up accurately rather than storing only pre-rounded rates.

Most importantly, a trustworthy metric must be right on **math, data types, time boundaries, granularity, missing data, and business rules**. PostgreSQL gives you every tool to express those calculations clearly; it is the SQL author's job to settle on the right meaning before picking the formula.
