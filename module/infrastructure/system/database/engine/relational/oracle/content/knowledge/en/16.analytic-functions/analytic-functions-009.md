# NTILE, CUME_DIST, PERCENT_RANK, and Data Distribution in Oracle Database

In data analysis, beyond sorting or numbering individual rows, you often need to know where a record falls within the distribution of an entire group. For example:

- Dividing employees into four salary groups of roughly equal size.
- Determining where a store's revenue sits within the revenue distribution across all stores.
- Finding products in the top 10% highest-sales tier.
- Comparing one student's exam score against the whole class.
- Ranking customers by spending within each region.

Oracle provides three analytic functions commonly used for these requirements:

- **NTILE(n)** divides ordered rows into n buckets of nearly equal row counts and returns each row's bucket number.
- **CUME_DIST()** computes the cumulative distribution of a row within its partition, i.e., the proportion of rows with a sort value less than or equal to the current row's value in the declared order.
- **PERCENT_RANK()** computes the relative rank position of a row based on RANK, normalized to the range 0 to 1.

All three functions require a defined ordering in the OVER clause, yet they answer different questions. NTILE divides the row count into groups; CUME_DIST and PERCENT_RANK describe relative position within a distribution. Understanding ties, NULLs, PARTITION BY, and how to read percentages helps prevent misinterpreting reports.

## 1. Three Concepts and the Questions They Answer

Suppose we have a list of five students' scores sorted ascending:

| Student | Score |
|---|---:|
| An | 10 |
| Binh | 20 |
| Chi | 20 |
| Dung | 30 |
| Ha | 40 |

There are three different questions:

1. **NTILE(4):** if we divide five students into four groups of nearly equal headcount, which group does each student belong to?
2. **CUME_DIST():** what fraction of students have a score less than or equal to the current student's score?
3. **PERCENT_RANK():** where does the current student's rank sit on a 0–1 scale, based on the lowest rank of the tied group?

Do not lump all three together as "percentile rank" and use them interchangeably. They follow different rules, especially when multiple rows share the same value.

## 2. NTILE: Dividing Rows into Nearly Equal Buckets

### 2.1 Syntax

~~~sql
NTILE(expr)
OVER (
    [PARTITION BY expr [, expr] ...]
    ORDER BY expr [ASC | DESC] [NULLS FIRST | NULLS LAST]
             [, expr ...]
)
~~~

Where:

- expr is the number of buckets to divide into, and must be a valid positive integer.
- ORDER BY determines the order of rows before partitioning into buckets.
- PARTITION BY splits data into independent groups; each partition is bucketed separately.
- NTILE returns a 1-based bucket number.

Example:

~~~sql
SELECT employee_id,
       salary,
       NTILE(4) OVER (
           ORDER BY salary, employee_id
       ) AS salary_quartile
FROM employees
ORDER BY salary, employee_id;
~~~

The query divides all employees into four groups by ascending salary. Bucket 1 holds lower-salary rows, and bucket 4 holds higher-salary rows according to the declared order.

### 2.2 How Row Counts Are Distributed

NTILE attempts to create buckets with nearly equal row counts. If the total row count is not evenly divisible by the number of buckets, the remainder rows are distributed one by one to the lower-numbered buckets.

For example, with 10 rows and NTILE(4):

| Bucket | Row count |
|---:|---:|
| 1 | 3 |
| 2 | 3 |
| 3 | 2 |
| 4 | 2 |

The first six rows are assigned to the first two buckets, three rows each; the remaining two buckets receive two rows each.

With 7 rows and NTILE(3):

| Bucket | Row count |
|---:|---:|
| 1 | 3 |
| 2 | 2 |
| 3 | 2 |

Not every bucket has the exact same row count in all cases. The goal is that bucket row counts differ by at most one.

### 2.3 NTILE Example with DUAL

To observe how bucketing works, you can build a small dataset using UNION ALL:

~~~sql
WITH scores AS (
    SELECT 1 AS student_id, 10 AS score FROM dual
    UNION ALL SELECT 2, 20 FROM dual
    UNION ALL SELECT 3, 20 FROM dual
    UNION ALL SELECT 4, 30 FROM dual
    UNION ALL SELECT 5, 40 FROM dual
)
SELECT student_id,
       score,
       NTILE(4) OVER (
           ORDER BY score, student_id
       ) AS bucket_no
FROM scores
ORDER BY score, student_id;
~~~

With five rows and four buckets, the first bucket receives the extra row when distributing the remainder. Thus the result is:

| STUDENT_ID | SCORE | BUCKET_NO |
|---:|---:|---:|
| 1 | 10 | 1 |
| 2 | 20 | 1 |
| 3 | 20 | 2 |
| 4 | 30 | 3 |
| 5 | 40 | 4 |

Two students with the same score of 20 can be placed into two different buckets. NTILE splits **rows by position**; it does not guarantee that equal values stay in the same bucket.

### 2.4 Why Is a Tie-Breaker Needed?

If you write:

~~~sql
NTILE(4) OVER (ORDER BY score)
~~~

and multiple students tie at a bucket boundary, Oracle has no further criterion to determine which row comes first in the tied group. Bucket assignment among tied rows can be unstable.

If a unique key STUDENT_ID exists, write:

~~~sql
NTILE(4) OVER (
    ORDER BY score, student_id
)
~~~

This creates deterministic ordering. However, adding a secondary key also means tied-score rows can still be split across different buckets. If the business requirement is that **all rows with the same value must belong to the same group**, NTILE may not be appropriate; consider grouping by value thresholds or using rank/cumulative distribution.

### 2.5 NTILE with PARTITION BY

Divide employees into four separate salary buckets within each department:

~~~sql
SELECT department_id,
       employee_id,
       salary,
       NTILE(4) OVER (
           PARTITION BY department_id
           ORDER BY salary, employee_id
       ) AS salary_quartile
FROM employees
ORDER BY department_id, salary, employee_id;
~~~

Each DEPARTMENT_ID restarts bucket numbering at 1. Employees in department A do not affect the bucket counts or ordering of department B.

If a department has fewer than four employees, some bucket numbers will not appear in that department's result. NTILE does not generate empty rows to fill buckets.

### 2.6 NTILE Does Not Divide by Value Width

Suppose salaries are 5, 6, 7, 100, 200, 300. NTILE(3) divides row counts nearly equally rather than creating equal-width numeric intervals like 0–100, 100–200, 200–300.

Therefore:

- NTILE(4) divides into four groups by row count.
- Dividing into fixed value ranges is a different problem, typically handled with CASE or a threshold table.
- If statistical percentile thresholds are needed, look at PERCENTILE_CONT or PERCENTILE_DISC.

## 3. CUME_DIST: Cumulative Distribution

### 3.1 Syntax

~~~sql
CUME_DIST()
OVER (
    [PARTITION BY expr [, expr] ...]
    ORDER BY expr [ASC | DESC] [NULLS FIRST | NULLS LAST]
             [, expr ...]
)
~~~

CUME_DIST takes no arguments inside its parentheses. The function returns a number strictly greater than 0 and less than or equal to 1.

For a row r in a partition, it can be understood as:

\[
\operatorname{CUME\_DIST}(r)
=
\frac{\text{number of rows with sort value less than or equal to r's value}}
{\text{total number of rows in partition}}
\]

"Less than or equal to" is evaluated according to the order of the entire ORDER BY expression list, not just one column if multiple sort columns are specified.

Rows sharing identical values across all ORDER BY expressions are peers (tied group) and receive the same CUME_DIST. The cumulative value is calculated through the end of that peer group.

### 3.2 Example with Scores 10, 20, 20, 30, 40

~~~sql
WITH scores AS (
    SELECT 1 AS student_id, 10 AS score FROM dual
    UNION ALL SELECT 2, 20 FROM dual
    UNION ALL SELECT 3, 20 FROM dual
    UNION ALL SELECT 4, 30 FROM dual
    UNION ALL SELECT 5, 40 FROM dual
)
SELECT student_id,
       score,
       CUME_DIST() OVER (
           ORDER BY score
       ) AS cumulative_distribution
FROM scores
ORDER BY score, student_id;
~~~

Result:

| STUDENT_ID | SCORE | CUME_DIST |
|---:|---:|---:|
| 1 | 10 | 0.20 |
| 2 | 20 | 0.60 |
| 3 | 20 | 0.60 |
| 4 | 30 | 0.80 |
| 5 | 40 | 1.00 |

Explanation:

- For score 10: 1/5 rows have score less than or equal to 10, so 0.20.
- For score 20: 3/5 rows have score less than or equal to 20, so both score-20 rows receive 0.60.
- For score 30: 4/5 rows have score less than or equal to 30, so 0.80.
- For score 40: 5/5 rows have score less than or equal to 40, so 1.00.

### 3.3 CUME_DIST Represents the Cumulative Proportion up to the Current Group

If an employee's CUME_DIST is 0.80 under ORDER BY salary ASC, it means 80% of rows in the partition have a salary less than or equal to that employee's salary. It does not mean the employee is in the "top 80% highest salaries".

To interpret high/low direction, check the ORDER BY direction:

- ORDER BY salary ASC: accumulates from lowest salary to highest salary.
- ORDER BY salary DESC: accumulates from highest salary to lowest salary.

Changing ASC to DESC reverses the meaning of the cumulative distribution.

### 3.4 CUME_DIST with PARTITION BY

Compute the cumulative position of salary within each department:

~~~sql
SELECT department_id,
       employee_id,
       salary,
       CUME_DIST() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS salary_cume_dist
FROM employees
ORDER BY department_id, salary, employee_id;
~~~

The denominator is the total number of rows in each department's partition. An employee may have a CUME_DIST of 0.90 in a small department, which cannot be compared directly against 0.90 in a department with a different staffing structure if the goal is company-wide comparison.

### 3.5 CUME_DIST and Ties

Tied values receive the same CUME_DIST because the function counts through the end of the peer group. This is useful when you do not want to split equal values into different distribution positions.

If you add a unique key to ORDER BY:

~~~sql
CUME_DIST() OVER (
    ORDER BY score, student_id
)
~~~

then rows with the same SCORE are no longer peers if STUDENT_ID differs. CUME_DIST is then computed over that finer order and can differ from ordering by SCORE alone.

Only add a tie-breaker if distinguishing individual rows is the business intent. If equal values should stay at the same quantile position, sort only by the value expression being analyzed.

## 4. PERCENT_RANK: Relative Rank

### 4.1 Syntax and Formula

~~~sql
PERCENT_RANK()
OVER (
    [PARTITION BY expr [, expr] ...]
    ORDER BY expr [ASC | DESC] [NULLS FIRST | NULLS LAST]
             [, expr ...]
)
~~~

PERCENT_RANK returns a value from 0 to 1. Formula:

\[
\operatorname{PERCENT\_RANK}
=
\frac{\operatorname{RANK}-1}{N-1}
\]

Where:

- RANK is the row's rank according to ORDER BY, using the tie rules of the RANK function.
- N is the total number of rows in the partition.
- If the partition has only one row, PERCENT_RANK returns 0.

For rows sharing the same ORDER BY values, RANK and PERCENT_RANK are identical. After a tie group, RANK skips positions corresponding to the number of tied rows.

### 4.2 Example with Score Data

~~~sql
WITH scores AS (
    SELECT 1 AS student_id, 10 AS score FROM dual
    UNION ALL SELECT 2, 20 FROM dual
    UNION ALL SELECT 3, 20 FROM dual
    UNION ALL SELECT 4, 30 FROM dual
    UNION ALL SELECT 5, 40 FROM dual
)
SELECT student_id,
       score,
       RANK() OVER (ORDER BY score) AS score_rank,
       PERCENT_RANK() OVER (
           ORDER BY score
       ) AS score_percent_rank
FROM scores
ORDER BY score, student_id;
~~~

Result:

| STUDENT_ID | SCORE | SCORE_RANK | PERCENT_RANK |
|---:|---:|---:|---:|
| 1 | 10 | 1 | 0.00 |
| 2 | 20 | 2 | 0.25 |
| 3 | 20 | 2 | 0.25 |
| 4 | 30 | 4 | 0.75 |
| 5 | 40 | 5 | 1.00 |

Explanation:

- Score 10 has rank 1: (1 - 1) / (5 - 1) = 0.
- Score 20 has rank 2: (2 - 1) / 4 = 0.25.
- Score 30 has rank 4 because two score-20 rows share rank 2, skipping rank 3: (4 - 1) / 4 = 0.75.
- Score 40 has rank 5: (5 - 1) / 4 = 1.

PERCENT_RANK is not the fraction of rows less than or equal to the current row. It normalizes the lowest rank of the peer group.

### 4.3 PERCENT_RANK with PARTITION BY

~~~sql
SELECT department_id,
       employee_id,
       salary,
       PERCENT_RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS salary_percent_rank
FROM employees
ORDER BY department_id, salary, employee_id;
~~~

Ranking is computed independently in each department. The lowest-paid employee in each partition has PERCENT_RANK equal to 0; the highest-ranked person usually has 1 if the partition has at least two rows (unless tied at the top). For a single-row partition, the result is 0 by the function's special rule.

## 5. Comparing NTILE, CUME_DIST, and PERCENT_RANK

With data 10, 20, 20, 30, 40 in ascending order:

| SCORE | NTILE(4) with tie-breaker | CUME_DIST | PERCENT_RANK |
|---:|---:|---:|---:|
| 10 | 1 | 0.20 | 0.00 |
| 20 | 1 | 0.60 | 0.25 |
| 20 | 2 | 0.60 | 0.25 |
| 30 | 3 | 0.80 | 0.75 |
| 40 | 4 | 1.00 | 1.00 |

The three functions answer three questions:

| Function | Question | Core calculation |
|---|---|---|
| NTILE(n) | Which bucket does the row belong to if row counts are split nearly evenly? | Row position after sorting and bucket count |
| CUME_DIST() | What fraction of the partition has values less than or equal to the current value? | Row count up to end of peer group / N |
| PERCENT_RANK() | Where does the row's lowest rank fall relatively from 0 to 1? | (RANK - 1) / (N - 1), returning 0 when N=1 |

### 5.1 NTILE Can Split Equal Values

The two score-20 rows in the example land in bucket 1 and bucket 2 because NTILE divides rows by position. CUME_DIST and PERCENT_RANK keep them at the same value because they are peers under ORDER BY SCORE.

### 5.2 CUME_DIST Is Usually Greater Than PERCENT_RANK at Intermediate Points

For score 20:

- CUME_DIST = 0.60 because three out of five rows have score less than or equal to 20.
- PERCENT_RANK = 0.25 because the lowest rank is 2 out of five rows.

There is no contradiction: the two formulas measure two different aspects.

### 5.3 Do Not Confuse NTILE(4) with Statistical Quartiles

NTILE(4) splits the row count into four nearly equal-sized buckets. It does not compute threshold values Q1, median, and Q3 according to a statistical percentile method.

If you need quantile thresholds of a metric, consider:

- PERCENTILE_CONT: computes a continuous percentile, which may interpolate between values.
- PERCENTILE_DISC: selects an actual value from the dataset under discrete percentile rules.

NTILE is useful for roughly equal-count bucketing; PERCENTILE_CONT/DISC are useful when value thresholds are needed. Pick the right tool for the reporting question.

## 6. Ties and Deterministic Ordering

### 6.1 Peer Groups Are Defined by the Entire ORDER BY

In CUME_DIST and PERCENT_RANK, rows are peers when they share identical values across all ORDER BY expressions.

Example:

~~~sql
CUME_DIST() OVER (
    ORDER BY salary
)
~~~

Two employees with the same salary are peers.

However:

~~~sql
CUME_DIST() OVER (
    ORDER BY salary, employee_id
)
~~~

means if EMPLOYEE_ID differs, the two employees are no longer peers.

This can change CUME_DIST and PERCENT_RANK values, not just display order.

### 6.2 When Should You Add a Secondary Key?

With NTILE, if you want deterministic bucket assignment at boundaries, add a unique secondary key. With CUME_DIST/PERCENT_RANK, only add a secondary key if you want each row treated as a separate rank rather than treating equal values as tied.

A single query can use two analytic clauses:

~~~sql
SELECT employee_id,
       salary,
       NTILE(4) OVER (
           ORDER BY salary, employee_id
       ) AS stable_bucket,
       CUME_DIST() OVER (
           ORDER BY salary
       ) AS salary_cume_dist,
       PERCENT_RANK() OVER (
           ORDER BY salary
       ) AS salary_percent_rank
FROM employees;
~~~

NTILE has a tie-breaker for stable row-by-row bucketing; the two distribution functions preserve peer groups by salary. This is a sound choice when the two goals differ.

### 6.3 Final Query ORDER BY Does Not Change Analytic ORDER BY

~~~sql
SELECT employee_id,
       salary,
       PERCENT_RANK() OVER (
           ORDER BY salary
       ) AS salary_percent_rank
FROM employees
ORDER BY employee_id;
~~~

PERCENT_RANK is computed by salary. Results are presented by employee_id. The two orderings serve separate purposes.

## 7. NULLs in Data Distribution

### 7.1 NULLs Are Sorted by NULLS FIRST/LAST

Oracle treats NULL as a value during analytic sorting. Default positions:

- ORDER BY ASC: NULLS LAST.
- ORDER BY DESC: NULLS FIRST.

Declare explicitly when NULLs can appear:

~~~sql
CUME_DIST() OVER (
    ORDER BY score ASC NULLS LAST
)
~~~

~~~sql
PERCENT_RANK() OVER (
    ORDER BY score ASC NULLS LAST
)
~~~

With ASC NULLS LAST, NULL-score rows sit at the end of the ordering and form a peer group. The CUME_DIST of the NULL group can equal 1 because all rows in the partition precede or tie with NULL in that order.

### 7.2 Is NULL Equal to 0?

No. NULL represents missing/unknown data semantically, whereas 0 is a specific number. If you replace it with:

~~~sql
ORDER BY NVL(score, 0)
~~~

you alter the distribution ordering and can merge NULLs into the same group as score 0. Do this only if business rules confirm that unrecorded scores must be treated as 0.

### 7.3 Excluding NULLs Before Computing Distribution

If a report analyzes only records that have scores:

~~~sql
SELECT student_id,
       score,
       CUME_DIST() OVER (
           ORDER BY score
       ) AS score_cume_dist
FROM student_scores
WHERE score IS NOT NULL;
~~~

WHERE removes NULLs from the analytic input set, so the denominator N counts only rows with non-NULL scores.

If you still want to display students without scores while excluding them from the distribution, compute the analytic functions over the scored subset and LEFT JOIN back to the full student list.

### 7.4 NULLs in PARTITION BY

Rows with NULL PARTITION BY keys are grouped into a shared NULL partition under Oracle's grouping/analytic rules. If data has many records missing DEPARTMENT_ID, distribution functions partitioned by DEPARTMENT_ID will evaluate them together as one NULL group.

If NULL should not form a business group, filter or classify explicitly in the source data before computing analytics.

## 8. Reading Distribution Results Under ASC and DESC

### 8.1 Distribution from Low to High

~~~sql
SELECT employee_id,
       salary,
       CUME_DIST() OVER (
           ORDER BY salary ASC
       ) AS cumulative_from_low,
       PERCENT_RANK() OVER (
           ORDER BY salary ASC
       ) AS rank_from_low
FROM employees
ORDER BY salary, employee_id;
~~~

Distribution values increase from lower salaries to higher salaries. CUME_DIST indicates the fraction of employees whose salary does not exceed the current salary.

### 8.2 Distribution from High to Low

~~~sql
SELECT employee_id,
       salary,
       CUME_DIST() OVER (
           ORDER BY salary DESC
       ) AS cumulative_from_high,
       PERCENT_RANK() OVER (
           ORDER BY salary DESC
       ) AS rank_from_high
FROM employees
ORDER BY salary DESC, employee_id;
~~~

Cumulative values are computed from highest salary down to lowest salary. If you need the proportion of employees earning at least the current salary, CUME_DIST with DESC can express that goal, though watch out for ties and NULL ordering.

### 8.3 Do Not Misread 0.9

With CUME_DIST and ORDER BY salary ASC, 0.9 means roughly 90% of rows have salary less than or equal to the current value. With ORDER BY salary DESC, 0.9 is the cumulative proportion from high to low.

PERCENT_RANK equal to 0.9 means the relative rank is near the end of the declared order, not directly that 90% of rows have values less than or equal to it.

State the sort direction clearly in the alias name or report documentation, such as SALARY_CUME_DIST_ASC, so readers do not have to guess.

## 9. Filtering by NTILE, CUME_DIST, and PERCENT_RANK

Analytic functions are evaluated after WHERE in the same query block. Therefore, NTILE/CUME_DIST/PERCENT_RANK cannot be placed directly in the WHERE clause of that same query block. Use a CTE or inline view.

### 9.1 Filtering the Highest Bucket Group

~~~sql
WITH bucketed AS (
    SELECT employee_id,
           department_id,
           salary,
           NTILE(4) OVER (
               PARTITION BY department_id
               ORDER BY salary, employee_id
           ) AS salary_bucket
    FROM employees
)
SELECT employee_id,
       department_id,
       salary,
       salary_bucket
FROM bucketed
WHERE salary_bucket = 4
ORDER BY department_id, salary DESC, employee_id;
~~~

The query retrieves bucket 4 of each department. With ORDER BY salary ASC inside NTILE, bucket 4 contains the highest-salary group by nearly equal row count.

### 9.2 Retrieving Rows with CUME_DIST Above 0.9

~~~sql
WITH distributed AS (
    SELECT employee_id,
           salary,
           CUME_DIST() OVER (
               ORDER BY salary
           ) AS salary_cume_dist
    FROM employees
)
SELECT employee_id,
       salary,
       salary_cume_dist
FROM distributed
WHERE salary_cume_dist > 0.90
ORDER BY salary DESC, employee_id;
~~~

With ORDER BY salary ASC, the condition above retrieves peer groups whose cumulative proportion exceeds 90%. This is not necessarily exactly 10% of employees: ties can push the cumulative proportion past the threshold.

### 9.3 Retrieving Rows with PERCENT_RANK >= 0.9

~~~sql
WITH ranked AS (
    SELECT employee_id,
           salary,
           PERCENT_RANK() OVER (
               ORDER BY salary
           ) AS salary_percent_rank
    FROM employees
)
SELECT employee_id,
       salary,
       salary_percent_rank
FROM ranked
WHERE salary_percent_rank >= 0.90
ORDER BY salary DESC, employee_id;
~~~

The condition selects rows whose relative rank is at least 0.90 in ascending order. Due to the RANK-based formula and ties, the actual row count may not be exactly 10%.

### 9.4 When an Exact Number of Top Rows Is Needed

If the requirement is exactly the top 10 highest-paid employees, use ROW_NUMBER with deterministic ordering:

~~~sql
WITH numbered AS (
    SELECT employee_id,
           salary,
           ROW_NUMBER() OVER (
               ORDER BY salary DESC, employee_id
           ) AS rn
    FROM employees
)
SELECT employee_id,
       salary
FROM numbered
WHERE rn <= 10
ORDER BY salary DESC, employee_id;
~~~

If the requirement is all tied individuals at 10th place, consider RANK or DENSE_RANK instead of ROW_NUMBER. Do not use CUME_DIST or PERCENT_RANK just to get "top 10" if the real requirement is an exact row count.

## 10. NTILE, CUME_DIST, and PERCENT_RANK After Aggregation

These functions can be applied over a dataset already grouped by GROUP BY, for example ranking regional revenue:

~~~sql
WITH regional_sales AS (
    SELECT region,
           SUM(amount) AS total_revenue
    FROM sales
    GROUP BY region
)
SELECT region,
       total_revenue,
       NTILE(4) OVER (
           ORDER BY total_revenue, region
       ) AS revenue_quartile,
       CUME_DIST() OVER (
           ORDER BY total_revenue
       ) AS revenue_cume_dist,
       PERCENT_RANK() OVER (
           ORDER BY total_revenue
       ) AS revenue_percent_rank
FROM regional_sales
ORDER BY total_revenue, region;
~~~

Logical sequence:

1. The `regional_sales` CTE produces one row per REGION.
2. SUM calculates revenue per region.
3. The analytic functions analyze the distribution of those revenue totals.

Here N is the number of regions present in `regional_sales`, not the number of source transactions.

### 10.1 PARTITION BY Along Another Dimension

~~~sql
WITH product_sales AS (
    SELECT region,
           product_id,
           SUM(amount) AS revenue
    FROM sales
    GROUP BY region, product_id
)
SELECT region,
       product_id,
       revenue,
       NTILE(4) OVER (
           PARTITION BY region
           ORDER BY revenue, product_id
       ) AS product_bucket,
       CUME_DIST() OVER (
           PARTITION BY region
           ORDER BY revenue
       ) AS revenue_cume_dist
FROM product_sales
ORDER BY region, revenue, product_id;
~~~

Each region is bucketed and analyzed independently across that region's own products.

### 10.2 Missing Periods Are Not Automatically Filled

If aggregating by month, months with no transactions may not appear. NTILE, CUME_DIST, and PERCENT_RANK only analyze existing rows in the partition. To analyze distribution across every month in a full calendar, create/join a calendar dimension before computing analytics.

## 11. Comparison with RANK and DENSE_RANK

To understand PERCENT_RANK, distinguish RANK and DENSE_RANK:

| Function | Rule on ties | Example ranks for scores 10, 20, 20, 30 |
|---|---|---|
| ROW_NUMBER | Each row gets a distinct sequence number | 1, 2, 3, 4 (needs tie-breaker for stability) |
| RANK | Equal values get same rank; next position skipped | 1, 2, 2, 4 |
| DENSE_RANK | Equal values get same rank; no rank numbers skipped | 1, 2, 2, 3 |
| PERCENT_RANK | Normalizes RANK by N | 0, 1/(N-1), 1/(N-1), 3/(N-1) |

PERCENT_RANK is based on RANK, not DENSE_RANK. Therefore, the spacing between quantile values can jump after a tie group.

Example with N=4:

| SCORE | RANK | DENSE_RANK | PERCENT_RANK |
|---:|---:|---:|---:|
| 10 | 1 | 1 | 0.0000 |
| 20 | 2 | 2 | 0.3333 |
| 20 | 2 | 2 | 0.3333 |
| 30 | 4 | 3 | 1.0000 |

## 12. Row-Count Quantiles vs. Value-Based Percentiles

A common misinterpretation is treating NTILE(4) as the Q1, median, and Q3 value thresholds. In reality:

- NTILE(4) splits rows into four groups of nearly equal size.
- PERCENT_RANK/CUME_DIST describe each row's relative position within the sorted distribution.
- PERCENTILE_CONT/PERCENTILE_DISC return a percentile threshold value according to their respective rules.

Example needing the 90th percentile salary threshold:

~~~sql
SELECT PERCENTILE_CONT(0.90)
       WITHIN GROUP (ORDER BY salary) AS p90_salary
FROM employees;
~~~

PERCENTILE_CONT can interpolate to return a value that does not necessarily exist in the raw data.

~~~sql
SELECT PERCENTILE_DISC(0.90)
       WITHIN GROUP (ORDER BY salary) AS p90_salary
FROM employees;
~~~

PERCENTILE_DISC picks an existing value from the dataset according to discrete percentile definitions.

These two percentile functions use ordered-set aggregate/hypothetical-set syntax in Oracle, and are not direct replacements for NTILE. Choose:

| Need | Appropriate tool |
|---|---|
| Split staff into four groups of nearly equal headcount | NTILE(4) |
| Know cumulative proportion up to current value | CUME_DIST |
| Know relative rank via RANK formula | PERCENT_RANK |
| Compute threshold value at the 90th percentile | PERCENTILE_CONT or PERCENTILE_DISC |
| Get exactly the top 20 rows | ROW_NUMBER |
| Get all rows tied at a rank | RANK or DENSE_RANK depending on semantics |

## 13. NULLs, Ties, and Determinism in Report Design

### 13.1 Define the Row Set Before Computing

WHERE filters input rows before analytic functions run. If employees without salaries are excluded, the denominator N of CUME_DIST and PERCENT_RANK shrinks. If they are kept with NULLS LAST, they participate in the partition and affect the distribution.

Decide clearly whether the report measures:

- All employees, including those without salaries.
- Only employees with defined salaries.
- Employees with salaries, while displaying the NULL group separately.

### 13.2 Ties at NTILE Boundaries

If multiple equal values fall right on a bucket boundary, NTILE can split the tied-value group. This is valid under the definition of nearly equal row-count partitioning. If the report must keep ties together, choose another grouping method.

### 13.3 CUME_DIST/PERCENT_RANK Need Consistent Peer Group Definitions

Do not add unrelated columns to the analytic ORDER BY. If you add EMPLOYEE_ID to PERCENT_RANK, employees with the same salary are split into separate peers, altering the distribution output.

### 13.4 Analytic Results Do Not Guarantee Display Order

Always write an ORDER BY at the end of the query if the report requires a specific display order. ORDER BY inside OVER only serves analytic calculation.

## 14. Performance and Execution Plans

### 14.1 Functions Require Ordering Processing

NTILE, CUME_DIST, and PERCENT_RANK all rely on ordering within partitions. On large datasets, Oracle may need to sort data by PARTITION BY and ORDER BY expressions. Sorting can use PGA or TEMP depending on data size and plan.

### 14.2 Share the Same Analytic Clause When Possible

Example:

~~~sql
SELECT employee_id,
       salary,
       CUME_DIST() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS cume_dist_value,
       PERCENT_RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS percent_rank_value
FROM employees;
~~~

Both functions share the same partition/order definition. The optimizer can reuse the same ordering pass, though this should not be treated as a guaranteed plan contract. Avoid altering ordering just in hopes of sharing a sort if it changes semantics.

### 14.3 Indexes May Help, But Do Not Guarantee Avoiding a Sort

An index on:

~~~sql
(department_id, salary, employee_id)
~~~

can help access by department and salary order, yet Oracle also considers filters, cardinality, clustering factor, joins, partitioning, and read cost. Analytic functions do not automatically force index usage on ORDER BY columns.

Do not create new indexes based solely on an example. Inspect workload, execution plan, and actual runtime first.

### 14.4 Viewing the Execution Plan

~~~sql
EXPLAIN PLAN FOR
SELECT employee_id,
       department_id,
       salary,
       NTILE(4) OVER (
           PARTITION BY department_id
           ORDER BY salary, employee_id
       ) AS salary_bucket,
       CUME_DIST() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS salary_cume_dist,
       PERCENT_RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary
       ) AS salary_percent_rank
FROM employees;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN shows the estimated plan, not runtime measurements. When tuning, inspect the actual cursor plan, actual row counts, sort/window operations, CPU, I/O, and TEMP.

## 15. Lab: Employee Score Distribution

Commands in this section are meant for a dedicated practice schema with table-creation privileges and appropriate quota. Do not run experimental DDL/DML on a production schema. Oracle DDL such as CREATE TABLE causes an implicit commit.

### 15.1 Create the Table

~~~sql
CREATE TABLE lab_employee_scores (
    employee_id   NUMBER PRIMARY KEY,
    department_id NUMBER NOT NULL,
    employee_name VARCHAR2(60) NOT NULL,
    score         NUMBER(6,2)
);
~~~

### 15.2 Load Data

~~~sql
INSERT INTO lab_employee_scores VALUES (1, 10, 'An', 10);
INSERT INTO lab_employee_scores VALUES (2, 10, 'Binh', 20);
INSERT INTO lab_employee_scores VALUES (3, 10, 'Chi', 20);
INSERT INTO lab_employee_scores VALUES (4, 10, 'Dung', 30);
INSERT INTO lab_employee_scores VALUES (5, 10, 'Ha', 40);
INSERT INTO lab_employee_scores VALUES (6, 20, 'Lan', 50);
INSERT INTO lab_employee_scores VALUES (7, 20, 'Minh', 60);
INSERT INTO lab_employee_scores VALUES (8, 20, 'Nam', 60);
INSERT INTO lab_employee_scores VALUES (9, 20, 'Oanh', 80);
INSERT INTO lab_employee_scores VALUES (10, 20, 'Phuc', NULL);
COMMIT;
~~~

Department 10 has five students/employees with two rows tied at score 20. Department 20 has five rows, including two tied at score 60 and one NULL score.

### 15.3 Compare All Three Functions in One Query

~~~sql
SELECT department_id,
       employee_id,
       employee_name,
       score,
       NTILE(4) OVER (
           PARTITION BY department_id
           ORDER BY score ASC NULLS LAST, employee_id
       ) AS score_bucket,
       CUME_DIST() OVER (
           PARTITION BY department_id
           ORDER BY score ASC NULLS LAST
       ) AS score_cume_dist,
       PERCENT_RANK() OVER (
           PARTITION BY department_id
           ORDER BY score ASC NULLS LAST
       ) AS score_percent_rank
FROM lab_employee_scores
ORDER BY department_id, score ASC NULLS LAST, employee_id;
~~~

Observations:

- Buckets restart from 1 in each department.
- Two rows with the same score can be placed in different buckets by NTILE due to the employee_id tie-breaker.
- CUME_DIST and PERCENT_RANK keep identical results for tied-score rows because their analytic ORDER BY uses only SCORE.
- The NULL score sits at the end of the partition per NULLS LAST and participates in the distribution.

### 15.4 Compare With and Without a Tie-Breaker

~~~sql
SELECT employee_id,
       score,
       NTILE(4) OVER (
           PARTITION BY department_id
           ORDER BY score
       ) AS bucket_without_tiebreaker,
       NTILE(4) OVER (
           PARTITION BY department_id
           ORDER BY score, employee_id
       ) AS bucket_with_tiebreaker,
       CUME_DIST() OVER (
           PARTITION BY department_id
           ORDER BY score
       ) AS cume_dist_by_score,
       CUME_DIST() OVER (
           PARTITION BY department_id
           ORDER BY score, employee_id
       ) AS cume_dist_by_score_and_id
FROM lab_employee_scores
WHERE department_id = 10
ORDER BY score, employee_id;
~~~

This query lets you observe how adding EMPLOYEE_ID not only determines which row comes first in NTILE, but also alters peer groups for CUME_DIST.

### 15.5 Analyze Only People with Scores

~~~sql
SELECT department_id,
       employee_id,
       score,
       CUME_DIST() OVER (
           PARTITION BY department_id
           ORDER BY score
       ) AS cume_dist_known_scores,
       PERCENT_RANK() OVER (
           PARTITION BY department_id
           ORDER BY score
       ) AS percent_rank_known_scores
FROM lab_employee_scores
WHERE score IS NOT NULL
ORDER BY department_id, score, employee_id;
~~~

WHERE removes NULL rows before analytic evaluation. Each partition's denominator includes only employees with scores.

### 15.6 Filter the Highest Bucket

~~~sql
WITH bucketed AS (
    SELECT department_id,
           employee_id,
           employee_name,
           score,
           NTILE(4) OVER (
               PARTITION BY department_id
               ORDER BY score, employee_id
           ) AS score_bucket
    FROM lab_employee_scores
    WHERE score IS NOT NULL
)
SELECT department_id,
       employee_id,
       employee_name,
       score
FROM bucketed
WHERE score_bucket = 4
ORDER BY department_id, score DESC, employee_id;
~~~

The query retrieves bucket 4 per department, excluding NULL scores before bucketing.

### 15.7 Clean Up the Lab Table

Only drop tables you created in the practice schema once you have confirmed the data is no longer needed. Do not put DROP TABLE in scripts that could accidentally run on production; DDL performs an implicit commit and you cannot rely on ROLLBACK to recover.

## 16. Common Errors and Misconceptions

| Error / Misconception | Reality | Solution |
|---|---|---|
| NTILE(4) divides into equal value intervals | NTILE divides row counts nearly equally | Use thresholds/percentiles if value intervals are needed |
| NTILE always keeps ties in the same bucket | It can split equal values across a boundary | Choose a value-based grouping method if needed |
| Buckets always have equal row counts | When N is not evenly divisible, earlier buckets receive extra rows | Account for bucket sizes in advance |
| CUME_DIST is rank/(N-1) | That is the form of PERCENT_RANK using RANK | Apply each function's exact formula |
| PERCENT_RANK is the fraction of rows <= value | CUME_DIST is the cumulative fraction up to the peer group | Review the formulas |
| PERCENT_RANK is always > 0 | Rank 1 rows return 0; a single-row partition also returns 0 | Remember the 0 and 1 bounds |
| CUME_DIST can be 0 | Values are always > 0 and <= 1 | Check denominator and peer group |
| Adding a tie-breaker does not affect distribution | It can break peer groups and change CUME_DIST/PERCENT_RANK | Add only when ties must be broken |
| Outer ORDER BY controls analytic evaluation | ORDER BY inside OVER controls calculation | Distinguish the two ORDER BY clauses |
| NULLs are automatically ignored | NULLs are sorted per NULLS FIRST/LAST | Filter explicitly if NULLs must be excluded |
| NTILE/CUME_DIST can be used in WHERE in the same query block | Analytic functions run after WHERE | Use a CTE or inline view |
| NTILE(4) is statistical quartiles | It splits into four nearly equal-count groups | Use PERCENTILE_CONT/DISC when thresholds are needed |
| Adding PARTITION BY does not affect the denominator | Each partition has its own N | Verify the analysis level |

## 17. Checklist for Interpreting Distribution Results

Before publishing a report using these three functions, verify:

1. Which row set enters the analytic functions? Does WHERE filter out NULLs or specific statuses?
2. Is the partition the entire dataset or per department/region/customer?
3. Is ORDER BY ascending or descending? Which end do percentages accumulate from?
4. Are there ties? Should equal-value rows stay in the same peer group?
5. Does NTILE need nearly equal row counts or grouping by value thresholds?
6. If using NTILE, the remainder gives earlier buckets an extra row; is that acceptable?
7. Does CUME_DIST express the proportion of rows through the end of the peer group, or are readers confusing it with percentile rank?
8. PERCENT_RANK is based on RANK; single-row partitions return 0.
9. Are NULLs kept, excluded, or placed first/last?
10. Is a secondary key needed for deterministic ordering, and does adding it alter peer groups?
11. If filtering analytic results, is a CTE/inline view used?
12. If percentile thresholds are needed, were PERCENTILE_CONT/DISC chosen instead of NTILE?

## 18. Self-Practice Exercises

**Question 1 — Bucketing.** There are 11 rows and NTILE(4). How many rows are in each of the four buckets?

Hint: Base division gives 2 rows per bucket, and the remainder of 3 rows is added one each to buckets 1, 2, and 3: 3, 3, 3, 2.

**Question 2 — CUME_DIST.** A partition has values 10, 20, 20, 30, 40. What is the CUME_DIST of 20?

Hint: Three out of five rows have values less than or equal to 20, so 0.60.

**Question 3 — PERCENT_RANK.** With the same data, what is the PERCENT_RANK of the two rows with score 20?

Hint: RANK=2 and N=5, so (2-1)/(5-1)=0.25.

**Question 4 — Ties.** Why can two rows with the same score fall into two different NTILE buckets yet share the same CUME_DIST?

Hint: NTILE splits individual rows by position; CUME_DIST returns the same value for the peer group.

**Question 5 — Tie-breaker.** If STUDENT_ID is added to CUME_DIST's ORDER BY, what can change?

Hint: Rows with equal scores but different IDs are no longer peers; CUME_DIST is computed on the finer order.

**Question 6 — Partition.** How does computing CUME_DIST by DEPARTMENT_ID differ from computing it company-wide?

Hint: The denominator and cumulative row set are computed separately within each department.

**Question 7 — NULL.** Under ORDER BY SCORE ASC NULLS LAST, where does the NULL SCORE group sit in the distribution?

Hint: At the end of the ordering; the NULL group can receive CUME_DIST = 1 because every row precedes or ties with it.

**Question 8 — Filtering analytics.** Write a query retrieving rows with PERCENT_RANK greater than or equal to 0.9.

Hint: Compute PERCENT_RANK inside a CTE and filter in the outer query block.

**Question 9 — Percentile threshold.** To find the P90 salary as a specific monetary amount, should you use NTILE(10) or PERCENTILE_CONT(0.90)?

Hint: PERCENTILE_CONT is appropriate for computing continuous value thresholds; NTILE divides rows into nearly equal-sized groups.

**Question 10 — Exactly 10 rows.** To get the exact 10 highest-paid employees, which function should you use?

Hint: ROW_NUMBER with ORDER BY salary DESC and a unique secondary key.

## 19. Summary

NTILE, CUME_DIST, and PERCENT_RANK are all analytic functions for analyzing a row's relative position in a sorted dataset, but their meanings differ:

- **NTILE(n)** divides rows into n nearly equal buckets. Earlier buckets receive an extra row when the total row count is not evenly divisible by n. Equal-value rows can be split across boundaries.
- **CUME_DIST()** returns the cumulative proportion up to the end of the current row's peer group: count of rows less than or equal in order / total rows in partition. Peers receive the same result.
- **PERCENT_RANK()** normalizes RANK via (RANK - 1) / (N - 1); rank 1 rows receive 0, and single-row partitions also receive 0.

To use them accurately:

- Use PARTITION BY when separate distributions per business group are needed.
- Choose the right ORDER BY direction; ASC and DESC change how the distribution is read.
- Add a tie-breaker only when deterministic row-by-row ordering is needed; for CUME_DIST/PERCENT_RANK, adding a column can break peer groups.
- Decide whether NULLs participate in the distribution and declare NULLS FIRST/LAST explicitly.
- Use a CTE or inline view to filter analytic results.
- Distinguish row-count bucketing from value-based percentile thresholds.

Understanding these distinctions lets reports bucket data, describe distributions, and select high/low tiers without confusing buckets with percentiles or relative ranks.
