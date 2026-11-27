# NTILE, CUME_DIST, PERCENT_RANK, and Data Distribution

In the **DATABASE_MYSQL** module, learners master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, concurrency control, reading execution plans, query tuning, privilege management, backups, and operations. Three window functions—NTILE(), CUME_DIST(), and PERCENT_RANK()—help analyze a row's relative position within a dataset. They are commonly used for quantile bucketing, measuring cumulative proportions, and expressing rankings as normalized ratios.

All three functions require OVER() and operate within a partition scope. Although they all serve distribution analysis, they answer different questions: NTILE divides rows into roughly equal-sized groups; CUME_DIST reports the proportion of rows preceding or tied with the current row; PERCENT_RANK normalizes rank onto the range from 0 to 1. Results also depend on sort order, tied values, and NULL handling.

These window functions are supported in MySQL 8.0+; MySQL 5.7 does not support OVER() syntax for window functions. For plan inspection, EXPLAIN FORMAT=TREE is available starting in MySQL 8.0.16 and EXPLAIN ANALYZE starting in MySQL 8.0.18. Check the server version with SELECT VERSION() before running the corresponding examples.

## 1. Overview of the three distribution functions

| Function | Output | Question answered |
|---|---|---|
| NTILE(N) | Bucket number from 1 to N | Which group does this row belong to when splitting the set into N roughly equal groups? |
| CUME_DIST() | Decimal from 0 to 1 | What fraction of the partition has values preceding or tied with the current row? |
| PERCENT_RANK() | Decimal from 0 to 1 | Where does the current row's rank sit relatively between the first and last rank? |

All three are window functions and do not collapse multiple rows into one like GROUP BY does. Each input row produces one output row, augmented with a bucket number or distribution value.

Example:

~~~sql
SELECT employee_id,
       salary,
       NTILE(4) OVER (ORDER BY salary) AS salary_quartile,
       CUME_DIST() OVER (ORDER BY salary) AS salary_cume_dist,
       PERCENT_RANK() OVER (ORDER BY salary) AS salary_percent_rank
FROM employees;
~~~

The example above computes salary distribution across all employees. If you want to compute separately per department, add PARTITION BY department_id to each window specification.

## 2. Window specification and calculation scope

A window specification typically includes:

- PARTITION BY: splits data into independent groups.
- ORDER BY: defines row ordering within each group.
- Frame clause: defines the row frame for window functions that use frames.

Example:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       CUME_DIST() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS salary_distribution
FROM employees;
~~~

Each department is an independent partition. CUME_DIST() resets in each department; employees are compared against peers in the same department.

### 2.1. Without PARTITION BY

If PARTITION BY is omitted, the entire query row set forms a single partition:

~~~sql
SELECT product_id,
       revenue,
       NTILE(10) OVER (ORDER BY revenue DESC) AS revenue_decile
FROM products;
~~~

All products are divided into 10 groups by revenue. Bucket 1 contains the highest-revenue group because the ordering is DESC.

### 2.2. Window ORDER BY does not guarantee final output order

ORDER BY inside OVER() only defines the order used to compute the window function. It does not guarantee that rows are returned in that order. If you need output displayed by bucket or value, include ORDER BY at the end of the SELECT statement:

~~~sql
SELECT product_id,
       revenue,
       NTILE(10) OVER (ORDER BY revenue DESC, product_id) AS revenue_decile
FROM products
ORDER BY revenue_decile, revenue DESC, product_id;
~~~

The final ORDER BY controls result set ordering. The two ORDER BY clauses serve distinct purposes and may differ.

## 3. NTILE(N): dividing rows into roughly equal buckets

NTILE(N) divides the rows in each partition into N groups, balancing row counts as evenly as possible. The function returns a 1-based bucket number.

Syntax:

~~~sql
NTILE(N) OVER (
    [PARTITION BY expression, ...]
    [ORDER BY expression [ASC | DESC], ...]
)
~~~

N must be a positive integer. Buckets are numbered according to ORDER BY; without ORDER BY, there is no deterministic ordering basis for interpreting groups.

### 3.1. Bucketing rules

If the row count is divisible by N, every bucket gets the same number of rows. If there is a remainder, the first few buckets get one extra row compared to the rest.

Examples:

| Row count | NTILE(N) | Rows per bucket |
|---:|---:|---|
| 12 | 4 | 3, 3, 3, 3 |
| 10 | 4 | 3, 3, 2, 2 |
| 7 | 3 | 3, 2, 2 |
| 5 | 4 | 2, 1, 1, 1 |

If N exceeds the number of rows in a partition, only the buckets that receive rows appear in the output; the remaining buckets are empty.

### 3.2. Splitting into quartiles

Quartiles divide data into four groups with roughly equal row counts:

~~~sql
SELECT employee_id,
       salary,
       NTILE(4) OVER (
           ORDER BY salary ASC, employee_id
       ) AS salary_quartile
FROM employees
ORDER BY salary ASC, employee_id;
~~~

Bucket 1 holds the lowest salaries; bucket 4 holds the highest salaries. If you want bucket 1 to hold the highest salaries, change the sort order to salary DESC.

### 3.3. Splitting into deciles

Deciles divide data into 10 groups:

~~~sql
SELECT customer_id,
       annual_spend,
       NTILE(10) OVER (
           ORDER BY annual_spend DESC, customer_id
       ) AS spend_decile
FROM customer_metrics;
~~~

Decile 1 is the group of customers with the highest annual_spend; decile 10 is the lowest. This numbering depends on ORDER BY DESC.

### 3.4. Buckets are split by row count, not value range

NTILE does not guarantee that buckets span equal value intervals. If most products earn between 0 and 100 while a few products earn millions, the buckets will still have nearly equal row counts; their revenue ranges can vary wildly.

NTILE also does not guarantee keeping tied values in the same bucket. If a group of multiple rows sharing the same score straddles a bucket boundary, tied rows can be split across two buckets. This is an important difference from CUME_DIST and PERCENT_RANK.

### 3.5. Deterministic ordering when bucketing

If ORDER BY cannot resolve the order between tied rows, bucket assignment for individual rows in a tied group can vary across runs or execution plans.

Add a unique key as a secondary sort criterion:

~~~sql
NTILE(4) OVER (
    PARTITION BY department_id
    ORDER BY salary ASC, employee_id ASC
)
~~~

`employee_id` makes per-row ordering unambiguous. However, because `employee_id` is part of ORDER BY, rows with the same salary but different `employee_id` are no longer peers across the full window ordering. This is appropriate for NTILE when stable bucket assignment is needed; for CUME_DIST or PERCENT_RANK, consider whether equal salary values should remain peers.

## 4. CUME_DIST(): cumulative distribution within a partition

CUME_DIST() returns the cumulative distribution of the current row within its partition. Formula:

\[
\operatorname{CUME\_DIST} =
\frac{\text{number of rows preceding or tied with the current row}}
{\text{total number of rows in the partition}}
\]

The numerator includes all rows belonging to the current row's peer group. Values lie in the range greater than 0 and less than or equal to 1.

Syntax:

~~~sql
CUME_DIST() OVER (
    [PARTITION BY expression, ...]
    [ORDER BY expression [ASC | DESC], ...]
)
~~~

### 4.1. Example calculating cumulative distribution

Suppose there are five scores in ascending order:

| Row | Score | Rows preceding or tied | CUME_DIST |
|---:|---:|---:|---:|
| 1 | 10 | 1 | 1/5 = 0.20 |
| 2 | 20 | 3 | 3/5 = 0.60 |
| 3 | 20 | 3 | 3/5 = 0.60 |
| 4 | 40 | 4 | 4/5 = 0.80 |
| 5 | 50 | 5 | 5/5 = 1.00 |

The two rows with score 20 are peers. Both have a CUME_DIST of 0.60 because the numerator counts through the end of the peer group, not just each row's individual position.

### 4.2. Interpreting with ORDER BY ASC

With ORDER BY score ASC, CUME_DIST indicates the proportion of rows whose score is less than or equal to the current value (including all peers equal to that value).

If a product has CUME_DIST = 0.90, roughly 90% of rows in the partition have values less than or equal to that product's value. This can be used to identify the upper tail of a distribution.

### 4.3. Interpreting with ORDER BY DESC

When switched to ORDER BY score DESC, the order is reversed. CUME_DIST then measures the proportion of rows preceding or tied in descending order, corresponding to rows whose score is greater than or equal to the current value.

~~~sql
SELECT product_id,
       revenue,
       CUME_DIST() OVER (
           ORDER BY revenue DESC
       ) AS high_to_low_cume_dist
FROM products;
~~~

Do not interpret CUME_DIST as "less than or equal to" when the window uses DESC. Always read it in the direction of ORDER BY.

### 4.4. How peer groups cause step jumps

CUME_DIST can jump across values rather than rising uniformly per row. If a single value appears in multiple rows, all peers share the same CUME_DIST and the proportion jumps to the end of that group.

For instance, if 40% of rows share the same value at the start of a partition, that peer group's CUME_DIST is 0.40. The function does not assign 0.10, 0.20, 0.30, 0.40 separately to tied rows.

## 5. PERCENT_RANK(): normalizing rank to 0–1

PERCENT_RANK() returns the relative rank of a row based on RANK(). Formula:

\[
\operatorname{PERCENT\_RANK} =
\frac{\operatorname{RANK} - 1}
{\text{total rows in partition} - 1}
\]

If the partition has only one row, PERCENT_RANK returns 0 to avoid division by zero. Values fall in the range from 0 to 1.

Syntax:

~~~sql
PERCENT_RANK() OVER (
    [PARTITION BY expression, ...]
    [ORDER BY expression [ASC | DESC], ...]
)
~~~

### 5.1. Example with tied values

With scores 10, 20, 20, 40, 50:

| Score | RANK | Total rows | PERCENT_RANK |
|---:|---:|---:|---:|
| 10 | 1 | 5 | (1 - 1)/(5 - 1) = 0.00 |
| 20 | 2 | 5 | (2 - 1)/(5 - 1) = 0.25 |
| 20 | 2 | 5 | (2 - 1)/(5 - 1) = 0.25 |
| 40 | 4 | 5 | (4 - 1)/(5 - 1) = 0.75 |
| 50 | 5 | 5 | (5 - 1)/(5 - 1) = 1.00 |

The two rows with score 20 share rank 2, so both have PERCENT_RANK 0.25. RANK leaves a gap after the peer group: score 40 has rank 4.

### 5.2. Meaning of 0 and 1

In a partition with at least two rows and an ORDER BY:

- Rows in the first peer group have rank 1, so PERCENT_RANK = 0.
- Rows in the last peer group have rank equal to the starting position of the last group; if the last group contains only one final row, PERCENT_RANK = 1.
- Intermediate values are normalized by rank and total row count.

If the last group has multiple tied rows, all peers share the rank of the first row in that group; therefore the last group's PERCENT_RANK can be less than 1. CUME_DIST for the last group is always 1 because it counts through the end of the peer group.

### 5.3. PERCENT_RANK is not the percentage of rows less than or equal

PERCENT_RANK is based on the rank of the start of the peer group, not on the count of rows preceding or tied like CUME_DIST. Consequently, the two functions can yield noticeably different numbers when many duplicate values exist.

Do not read PERCENT_RANK = 0.25 as claiming that 25% of rows are less than or equal to the current row. When you want the cumulative proportion including peers, use CUME_DIST with the appropriate ORDER BY direction.

## 6. Comparing NTILE, CUME_DIST, and PERCENT_RANK

Placed side by side, the three functions show how each represents the same dataset:

| Characteristic | NTILE(N) | CUME_DIST() | PERCENT_RANK() |
|---|---|---|---|
| Result | Integer bucket number | Ratio from 0 to 1 | Ratio from 0 to 1 |
| Basis | Row count and sort position | End position of peer group | RANK at start of peer group |
| Ties | Can be split across buckets | Same output value | Same output value |
| Even row split | Yes, roughly equal | No | No |
| Single-row set | Bucket 1 | 1 | 0 |
| Best suited for | Quartiles, deciles, customer bucketing | Cumulative proportion, distribution position | Normalized rank, relative rank position |

### 6.1. Sample results on the same dataset

With five rows having scores 10, 20, 20, 40, 50, suppose NTILE(4) sorts by score then student_id for deterministic per-row order:

| student_id | score | NTILE(4) | CUME_DIST by score | PERCENT_RANK by score |
|---:|---:|---:|---:|---:|
| 1 | 10 | 1 | 0.20 | 0.00 |
| 2 | 20 | 1 | 0.60 | 0.25 |
| 3 | 20 | 2 | 0.60 | 0.25 |
| 4 | 40 | 3 | 0.80 | 0.75 |
| 5 | 50 | 4 | 1.00 | 1.00 |

In this table, NTILE uses ORDER BY score, student_id, so the two score-20 rows have distinct positions and are split across buckets 1 and 2. CUME_DIST and PERCENT_RANK only ORDER BY score, so the two score-20 rows remain peers and receive identical results.

This is why you should not blindly share one window ordering across all three functions when tie-handling requirements differ.

## 7. Using multiple distribution functions in one query

Example segmenting customers by spend within each region:

~~~sql
SELECT
    customer_id,
    region_id,
    annual_spend,
    NTILE(4) OVER (
        PARTITION BY region_id
        ORDER BY annual_spend DESC, customer_id
    ) AS spend_quartile,
    CUME_DIST() OVER (
        PARTITION BY region_id
        ORDER BY annual_spend DESC
    ) AS spend_cume_dist,
    PERCENT_RANK() OVER (
        PARTITION BY region_id
        ORDER BY annual_spend DESC
    ) AS spend_percent_rank
FROM customer_metrics
ORDER BY region_id, annual_spend DESC, customer_id;
~~~

Interpretation:

- spend_quartile = 1 is the highest-spending group in each region.
- spend_cume_dist measures the proportion of customers preceding or tied in descending order—i.e., the proportion spending at least as much as the current value.
- spend_percent_rank normalizes the peer group's rank by the number of rows in the region.

NTILE includes `customer_id` for deterministic bucketing. The other two functions sort only by `annual_spend` to keep equal spend levels in the same peer group.

### 7.1. Using named windows when definitions match

If multiple functions share the same partition and order:

~~~sql
SELECT
    employee_id,
    department_id,
    salary,
    CUME_DIST() OVER w AS cume_dist_value,
    PERCENT_RANK() OVER w AS percent_rank_value
FROM employees
WINDOW w AS (
    PARTITION BY department_id
    ORDER BY salary
);
~~~

Named windows avoid repeating definitions and reduce the risk of functions accidentally using mismatched partitions or orderings. Share a window only when peer-group semantics are truly identical.

### 7.2. Adding buckets while preserving peer semantics

If NTILE needs a tie-breaker for stability while CUME_DIST/PERCENT_RANK must preserve ties, declare separate OVER clauses as shown earlier. Do not add a tie-breaker to the distribution functions' window just to sort the output; put display sorting in the query's final ORDER BY.

## 8. Filtering data using window function results

MySQL permits window functions only in the SELECT list and ORDER BY of the corresponding query block; they cannot be placed directly in WHERE, GROUP BY, or HAVING of the same query block.

Do not write:

~~~sql
SELECT employee_id, salary
FROM employees
WHERE NTILE(4) OVER (ORDER BY salary) = 1;
~~~

Compute the window function in a CTE or derived table and filter in the outer query block:

~~~sql
WITH ranked_employees AS (
    SELECT employee_id,
           department_id,
           salary,
           NTILE(4) OVER (
               PARTITION BY department_id
               ORDER BY salary DESC, employee_id
           ) AS salary_quartile
    FROM employees
)
SELECT employee_id, department_id, salary
FROM ranked_employees
WHERE salary_quartile = 1;
~~~

This query fetches the top 25% of employees by row count within each department, assuming the bucket division and row count produce the desired group. Because bucket sizes can differ by one row when not evenly divisible, this is an approximately equal-count grouping rather than a fixed salary threshold condition.

### 8.1. Filtering by CUME_DIST

To select the group with cumulative proportion at least 0.90 in ascending order:

~~~sql
WITH distribution AS (
    SELECT product_id,
           price,
           CUME_DIST() OVER (ORDER BY price ASC) AS price_cume_dist
    FROM products
    WHERE price IS NOT NULL
)
SELECT product_id, price, price_cume_dist
FROM distribution
WHERE price_cume_dist >= 0.90
ORDER BY price, product_id;
~~~

This selects the high-price tail under ascending cumulative distribution. Because peer groups stay intact, the selected row count may differ from exactly 10% if multiple rows share the same price at the cutoff.

### 8.2. Filtering by PERCENT_RANK

~~~sql
WITH distribution AS (
    SELECT product_id,
           revenue,
           PERCENT_RANK() OVER (ORDER BY revenue DESC) AS revenue_percent_rank
    FROM products
    WHERE revenue IS NOT NULL
)
SELECT product_id, revenue, revenue_percent_rank
FROM distribution
WHERE revenue_percent_rank <= 0.10
ORDER BY revenue DESC, product_id;
~~~

With DESC, rank 1 belongs to the highest-revenue group. The filter selects rows whose percent_rank does not exceed 0.10. Due to rank gaps and ties, the returned row count does not necessarily equal exactly 10% of total rows.

## 9. Handling ties and NULL data

### 9.1. Peer groups are defined by the full ORDER BY

Two rows are peers if all expressions in the window's ORDER BY evaluate as equal under comparison rules. With ORDER BY score, rows with equal scores are peers. With ORDER BY score, student_id, rows with different student_ids are no longer peers even if their scores match.

This directly impacts CUME_DIST and PERCENT_RANK. When equal scores should share the same distribution value, include only the columns defining the ranking value in their ORDER BY.

### 9.2. NULL is still a row in the partition

Window functions do not automatically exclude rows with NULL sort values. In MySQL, when sorting ASC, NULLs sort before non-NULL values; when sorting DESC, NULLs sort after.

If NULL means missing data that should not participate in the distribution, filter it out in the input query before computing:

~~~sql
WITH valid_scores AS (
    SELECT student_id, class_id, score
    FROM exam_results
    WHERE score IS NOT NULL
)
SELECT student_id,
       class_id,
       score,
       CUME_DIST() OVER (
           PARTITION BY class_id
           ORDER BY score
       ) AS score_cume_dist
FROM valid_scores;
~~~

If NULL rows must be retained but placed last in ascending order:

~~~sql
CUME_DIST() OVER (
    PARTITION BY class_id
    ORDER BY (score IS NULL), score
)
~~~

The expression `score IS NULL` evaluates to 0 for non-NULL scores and 1 for NULL scores. NULL rows still count toward the total rows in the partition; they are simply placed after non-NULL values.

### 9.3. When every value in a partition is NULL

If all score values are NULL and the window orders solely by score, every row is a peer. CUME_DIST is 1 for all rows because the entire partition precedes or ties with each row. PERCENT_RANK is 0 because the peer group's rank is 1. NTILE still divides rows by count and row order; without a tie-breaker, individual bucket assignments are nondeterministic.

Decide upfront whether all-NULL groups should be excluded from analysis, kept as a separate group, or surfaced as undetermined data.

## 10. Does the window frame affect these three functions?

NTILE, CUME_DIST, and PERCENT_RANK are ranking/distribution functions. They evaluate over the partition and window ordering, not over a sliding frame like SUM() OVER (ROWS ...). In MySQL, a frame clause does not restrict the calculation scope of these functions.

Example:

~~~sql
SELECT score,
       CUME_DIST() OVER (
           ORDER BY score
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS cume_dist_value
FROM exam_results;
~~~

Do not interpret the ROWS frame here as limiting CUME_DIST to rows up to the current physical row. CUME_DIST still uses its cumulative distribution definition across the full partition and peer group. To avoid misleading readers, omit frame clauses from these distribution functions.

## 11. Distinguishing from RANK, DENSE_RANK, and ROW_NUMBER

Ranking functions are related but not directly interchangeable:

| Function | Numbering behavior | Tie handling |
|---|---|---|
| ROW_NUMBER() | 1, 2, 3, 4, ... | Every row gets a distinct number |
| RANK() | 1, 2, 2, 4, ... | Tied rows share rank, leaving gaps |
| DENSE_RANK() | 1, 2, 2, 3, ... | Tied rows share rank, no gaps |
| NTILE(N) | 1 to N | Splits by row count, may split peers |
| CUME_DIST() | Ratio 0 to 1 | Same peer group gets same cumulative proportion |
| PERCENT_RANK() | Ratio 0 to 1 | Same peer group gets same normalized rank |

Example:

~~~sql
SELECT student_id,
       score,
       ROW_NUMBER() OVER (ORDER BY score) AS row_num,
       RANK() OVER (ORDER BY score) AS rank_value,
       DENSE_RANK() OVER (ORDER BY score) AS dense_rank_value,
       CUME_DIST() OVER (ORDER BY score) AS cume_dist_value,
       PERCENT_RANK() OVER (ORDER BY score) AS percent_rank_value
FROM exam_results;
~~~

ROW_NUMBER fits when unique sequence numbers are required; RANK and DENSE_RANK represent rankings with ties; CUME_DIST and PERCENT_RANK normalize position within a distribution; NTILE forms equal-count groups.

## 12. Data analytics applications

### 12.1. Customer segmentation

Divide customers into 5 groups by total spend within each region:

~~~sql
WITH customer_spend AS (
    SELECT customer_id,
           region_id,
           SUM(total_amount) AS total_spend
    FROM orders
    WHERE status = 'PAID'
    GROUP BY customer_id, region_id
),
segmented AS (
    SELECT customer_id,
           region_id,
           total_spend,
           NTILE(5) OVER (
               PARTITION BY region_id
               ORDER BY total_spend DESC, customer_id
           ) AS spend_group
    FROM customer_spend
)
SELECT *
FROM segmented
ORDER BY region_id, spend_group, total_spend DESC;
~~~

Group 1 contains the highest-spending customers in each region. Aggregating before the window function ensures each customer enters NTILE as a single row.

### 12.2. Identifying revenue distribution thresholds

~~~sql
SELECT product_id,
       revenue,
       CUME_DIST() OVER (
           PARTITION BY category_id
           ORDER BY revenue
       ) AS revenue_distribution
FROM product_metrics;
~~~

With ascending ORDER BY, `revenue_distribution` indicates the fraction of products in the category with revenue less than or equal to the current level. This helps spot top or bottom performers while watching for ties at cutoffs.

### 12.3. Comparing relative standing across departments

~~~sql
SELECT employee_id,
       department_id,
       salary,
       PERCENT_RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS salary_percent_rank
FROM employees;
~~~

A percent rank of 0.8 indicates the employee's rank lies in the upper region of the department's salary distribution. This is relative rank position, not strictly earning more than exactly 80% of employees when ties exist.

### 12.4. Building bucket summary reports

~~~sql
WITH bucketed AS (
    SELECT order_id,
           customer_id,
           total_amount,
           NTILE(4) OVER (
               ORDER BY total_amount DESC, order_id
           ) AS amount_quartile
    FROM orders
    WHERE status = 'PAID'
)
SELECT amount_quartile,
       COUNT(*) AS order_count,
       MIN(total_amount) AS min_amount,
       MAX(total_amount) AS max_amount,
       AVG(total_amount) AS average_amount
FROM bucketed
GROUP BY amount_quartile
ORDER BY amount_quartile;
~~~

The inner query splits orders into four buckets by row count; the outer query summarizes each bucket's characteristics. MIN/MAX here aggregate across rows already assigned to buckets, distinct from the inner distribution window function.

## 13. Performance and EXPLAIN

Window functions may require sorting rows by PARTITION BY and ORDER BY. On large datasets, sorting, buffering, and internal temporary tables can consume significant CPU, memory, and I/O.

### 13.1. Indexes supporting partitions and ordering

Example:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       PERCENT_RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS salary_percent_rank
FROM employees;
~~~

An index starting with `department_id` followed by `salary` can aid ordered access:

~~~sql
CREATE INDEX ix_employees_department_salary
ON employees (department_id, salary);
~~~

This index does not guarantee MySQL will completely eliminate sorting for the window function. Index usage depends on the query plan, selected columns, filter predicates, index order, and server version. Inspect existing indexes before adding new ones.

### 13.2. Multiple window orderings may require multiple sort passes

If NTILE uses `ORDER BY score, student_id` while CUME_DIST uses `ORDER BY score`, MySQL may need to process distinct window orderings. Even when definitions share PARTITION BY, adding a column to ORDER BY creates a different window ordering.

Combine window definitions only when semantics match. When CUME_DIST needs ties preserved and NTILE needs deterministic ordering, keep separate windows and measure the actual plan.

### 13.3. Reading EXPLAIN

~~~sql
EXPLAIN FORMAT=TREE
SELECT employee_id,
       department_id,
       salary,
       NTILE(4) OVER (
           PARTITION BY department_id
           ORDER BY salary, employee_id
       ) AS salary_quartile,
       CUME_DIST() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS salary_cume_dist
FROM employees;
~~~

Observe:

- Sort and window aggregate/evaluation steps.
- Input row counts per partition.
- Index chosen for the source table.
- Temporary tables or materialization steps if any.
- Estimated row counts and costs across query blocks.

### 13.4. EXPLAIN ANALYZE

MySQL 8.0.18+ supports EXPLAIN ANALYZE for compatible SELECT statements. It executes the query and reports actual timings, row counts, and iterator loops:

~~~sql
EXPLAIN ANALYZE
SELECT employee_id,
       department_id,
       salary,
       CUME_DIST() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS salary_cume_dist
FROM employees;
~~~

Run this only after assessing load; EXPLAIN ANALYZE executes the real query. Use lab or staging environments with representative data to compare plans and metrics.

### 13.5. Reducing data before window evaluation

When analyzing only a specific period, filter data in the input query block if doing so matches requirements:

~~~sql
WITH monthly_sales AS (
    SELECT customer_id,
           SUM(total_amount) AS total_amount
    FROM orders
    WHERE status = 'PAID'
      AND created_at >= '2026-01-01'
      AND created_at < '2027-01-01'
    GROUP BY customer_id
)
SELECT customer_id,
       total_amount,
       NTILE(10) OVER (ORDER BY total_amount DESC, customer_id) AS spend_decile
FROM monthly_sales;
~~~

The window function processes only the output of `monthly_sales`. Do not push filters before or after aggregation if doing so alters the target dataset under analysis.

## 14. Common mistakes and troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| NTILE produces buckets with very uneven value ranges | NTILE balances row counts, not value widths | Use a function matching your goal; inspect data skew |
| Two rows with equal scores land in different buckets | NTILE splits row-by-row and can split peers | Accept this behavior or group by distinct values first |
| Buckets change between runs | ORDER BY lacks a tie-breaker for tied rows | Add a unique key to NTILE's ORDER BY |
| CUME_DIST jumps by a large step | Multiple rows belong to the same peer group | Expected behavior; it counts through the end of the peer group |
| PERCENT_RANK differs from expected cumulative proportion | Based on RANK, not count of rows <= current value | Use CUME_DIST when cumulative proportion is needed |
| PERCENT_RANK of a single-row partition is 0 | Formula handles single-row partitions to avoid division by zero | Expected result |
| CUME_DIST returns 1 for all rows | Window may lack ORDER BY making all rows peers, or partition has one peer group | Verify whether ORDER BY reflects business ordering |
| NULL rows shift buckets or distributions | NULLs stay in the partition and sort per MySQL rules | Filter NULLs out or position them explicitly |
| Cannot filter directly by window alias in WHERE | Window functions run after the query block's WHERE phase | Use a CTE or derived table and filter in the outer query block |
| Window query is slow on large tables | Sorting, large partitions, or multiple window orderings | Inspect EXPLAIN, check indexes, and filter input data appropriately |

## 15. Practice lab: bucketing and measuring score distribution

Run this in a MySQL 8.0 lab database. The lab creates a dedicated table with a small score set so results are easy to verify by hand.

### 15.1. Create the table and load data

~~~sql
CREATE TABLE lab_scores (
    student_id INT NOT NULL,
    class_id INT NOT NULL,
    score DECIMAL(5,2) NULL,
    PRIMARY KEY (student_id),
    KEY ix_lab_scores_class_score (class_id, score)
) ENGINE=InnoDB;

INSERT INTO lab_scores (student_id, class_id, score)
VALUES
    (1, 1, 10.00),
    (2, 1, 20.00),
    (3, 1, 20.00),
    (4, 1, 40.00),
    (5, 1, 50.00),
    (6, 2, 30.00),
    (7, 2, 60.00),
    (8, 2, 90.00),
    (9, 2, NULL);
~~~

Class 1 has five rows, with two students tied at 20. Class 2 has three valid scores and one NULL row.

### 15.2. Step 1 — Compute all three functions on the same partition

~~~sql
SELECT
    student_id,
    score,
    NTILE(4) OVER (
        PARTITION BY class_id
        ORDER BY score, student_id
    ) AS score_bucket,
    CUME_DIST() OVER (
        PARTITION BY class_id
        ORDER BY score
    ) AS score_cume_dist,
    PERCENT_RANK() OVER (
        PARTITION BY class_id
        ORDER BY score
    ) AS score_percent_rank
FROM lab_scores
WHERE class_id = 1
ORDER BY score, student_id;
~~~

Expected output for class 1:

| student_id | score | score_bucket | score_cume_dist | score_percent_rank |
|---:|---:|---:|---:|---:|
| 1 | 10.00 | 1 | 0.20 | 0.00 |
| 2 | 20.00 | 1 | 0.60 | 0.25 |
| 3 | 20.00 | 2 | 0.60 | 0.25 |
| 4 | 40.00 | 3 | 0.80 | 0.75 |
| 5 | 50.00 | 4 | 1.00 | 1.00 |

Explain why the two rows with score 20 share the same CUME_DIST and PERCENT_RANK yet land in two different NTILE buckets.

### 15.3. Step 2 — Reverse sort direction

~~~sql
SELECT student_id,
       score,
       NTILE(4) OVER (
           PARTITION BY class_id
           ORDER BY score DESC, student_id
       ) AS highest_first_bucket,
       CUME_DIST() OVER (
           PARTITION BY class_id
           ORDER BY score DESC
       ) AS high_to_low_cume_dist,
       PERCENT_RANK() OVER (
           PARTITION BY class_id
           ORDER BY score DESC
       ) AS high_to_low_percent_rank
FROM lab_scores
WHERE class_id = 1
ORDER BY score DESC, student_id;
~~~

Observe bucket 1 and the distribution values when high scores come first. Restate the meaning of CUME_DIST under descending order.

### 15.4. Step 3 — Compare with and without a tie-breaker

~~~sql
SELECT student_id,
       score,
       NTILE(4) OVER (
           ORDER BY score
       ) AS bucket_without_tiebreaker,
       NTILE(4) OVER (
           ORDER BY score, student_id
       ) AS bucket_with_tiebreaker,
       CUME_DIST() OVER (
           ORDER BY score
       ) AS cume_dist_by_score
FROM lab_scores
WHERE class_id = 1
ORDER BY score, student_id;
~~~

Compare NTILE stability when adding a tie-breaker. In the sample data, `student_id` determines the order of the two score-20 rows; CUME_DIST still treats them as peers because its window orders only by `score`.

### 15.5. Step 4 — Observe NULL behavior

~~~sql
SELECT student_id,
       score,
       CUME_DIST() OVER (
           PARTITION BY class_id
           ORDER BY score
       ) AS cume_dist_with_null,
       PERCENT_RANK() OVER (
           PARTITION BY class_id
           ORDER BY score
       ) AS percent_rank_with_null
FROM lab_scores
WHERE class_id = 2
ORDER BY score, student_id;
~~~

Observe that NULL comes first under ORDER BY ASC and still counts in the partition's total row count. Next, filter out NULLs in the input query block:

~~~sql
SELECT student_id,
       score,
       CUME_DIST() OVER (
           PARTITION BY class_id
           ORDER BY score
       ) AS cume_dist_without_null
FROM lab_scores
WHERE class_id = 2
  AND score IS NOT NULL
ORDER BY score, student_id;
~~~

Compare the denominators and outputs of the two queries.

### 15.6. Step 5 — Filter by quantile

~~~sql
WITH distribution AS (
    SELECT student_id,
           class_id,
           score,
           CUME_DIST() OVER (
               PARTITION BY class_id
               ORDER BY score
           ) AS score_cume_dist
    FROM lab_scores
    WHERE score IS NOT NULL
)
SELECT *
FROM distribution
WHERE score_cume_dist >= 0.75
ORDER BY class_id, score, student_id;
~~~

Explain why a CTE is needed to filter window results and why the tail row count may not equal exactly 25% when peers exist.

### 15.7. Step 6 — Read the execution plan

~~~sql
EXPLAIN FORMAT=TREE
SELECT student_id,
       class_id,
       score,
       NTILE(4) OVER (
           PARTITION BY class_id
           ORDER BY score, student_id
       ) AS score_bucket,
       CUME_DIST() OVER (
           PARTITION BY class_id
           ORDER BY score
       ) AS score_cume_dist
FROM lab_scores;
~~~

Observe the sort, window evaluation, and chosen index steps. Try EXPLAIN ANALYZE on MySQL 8.0.18+ and explain the actual row counts. A tiny lab table is insufficient for drawing performance conclusions at large scale.

### 15.8. Step 7 — Clean up the lab table

~~~sql
DROP TABLE lab_scores;
~~~

Drop the lab table only after recording your results.

**Expected outcome:** compute NTILE, CUME_DIST, and PERCENT_RANK; explain ties and NULLs; reverse ORDER BY direction without misinterpreting results; filter window output via a CTE; read basic execution plans.

## 16. Key principles to remember

- NTILE(N) splits each partition into N roughly equal buckets by row count; earlier buckets take extra rows when there is a remainder.
- NTILE does not split by value intervals and can separate tied rows across bucket boundaries.
- Add a unique key to NTILE's ORDER BY for deterministic bucket assignment.
- CUME_DIST equals the number of rows preceding or tied divided by total rows in the partition.
- With ORDER BY ASC, CUME_DIST represents the proportion of values less than or equal to current; with DESC, interpret it in descending order.
- PERCENT_RANK equals (RANK - 1)/(row count - 1); single-row partitions return 0.
- CUME_DIST counts through the end of the peer group; PERCENT_RANK uses the rank at the start of the peer group.
- Peer groups are defined by the full window ORDER BY expression list; adding a tie-breaker can break ties.
- NULLs remain in the partition and sort first under ASC or last under DESC in MySQL; filter or position them explicitly if business logic requires it.
- Window ORDER BY does not dictate result set order; use an outer ORDER BY when needed.
- Never filter directly on window functions in WHERE within the same query block; use a CTE or derived table.
- These functions do not use frames to constrain scope the way aggregate window functions do.
- Use EXPLAIN to inspect sorts, indexes, and window evaluation; EXPLAIN ANALYZE executes the real query.

NTILE, CUME_DIST, and PERCENT_RANK all describe distributions yet serve distinct analytical views. Choose NTILE for roughly equal-count groups, CUME_DIST for cumulative proportions including peers, and PERCENT_RANK for normalized rankings. Always verify partition, sort direction, ties, and NULLs before interpreting results.
