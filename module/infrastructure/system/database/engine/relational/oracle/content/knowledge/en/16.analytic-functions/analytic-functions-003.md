# ROW_NUMBER, RANK, and DENSE_RANK

In Oracle Database, the analytic functions **ROW_NUMBER**, **RANK**, and **DENSE_RANK** are used to number or rank rows according to a defined order within an analytic window. They commonly appear in leaderboard reports, selecting the top N rows, finding the latest record per group, pagination, and deduplicating records based on business rules.

The three functions look similar, but they handle rows with equal sort values very differently:

- **ROW_NUMBER** assigns a unique sequential number to each row within every partition.
- **RANK** gives tied rows the same rank and leaves a gap before the next rank.
- **DENSE_RANK** also gives tied rows the same rank, but does not skip numbers for the next rank.

To choose the right function, first determine whether the business requirement wants **to count each row**, **competition-style ranking**, or **ranking of distinct value tiers**. Then determine the PARTITION BY scope, ORDER BY key, NULL placement, and how ties should be handled.

## 1. Analytic Functions and the OVER Clause

General syntax:

~~~sql
function_name(expression)
OVER (
    [PARTITION BY partition_expression, ...]
    ORDER BY sort_expression [ASC | DESC]
             [NULLS FIRST | NULLS LAST]
)
~~~

For the three ranking functions:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC, employee_id
)
~~~

~~~sql
RANK() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC
)
~~~

~~~sql
DENSE_RANK() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC
)
~~~

Meaning of the components:

- **function_name** selects the numbering/ranking rule.
- **PARTITION BY** divides the row set into independent groups. Each group restarts numbering or ranking from 1.
- **ORDER BY** determines the order used to assign numbers or ranks within each group.
- **ASC/DESC** specifies the sort direction.
- **NULLS FIRST/LAST** specifies the placement of NULL values in the sort key.

If PARTITION BY is omitted, the entire row set after steps prior to the analytic function is treated as a single partition.

If ORDER BY is omitted, these three functions have no basis for determining ranking order; when using ranking functions, declare the ordering explicitly.

### 1.1. Simple Example Without Partitioning

~~~sql
SELECT employee_id,
       full_name,
       salary,
       ROW_NUMBER() OVER (
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS row_no
FROM employees
ORDER BY row_no;
~~~

All employees are in the same partition. Employees with higher salaries receive lower sequence numbers. If salaries are equal, EMPLOYEE_ID is used as a secondary key to determine which row receives a number first.

### 1.2. Example Partitioned by Department

~~~sql
SELECT employee_id,
       full_name,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS row_no
FROM employees
ORDER BY department_id NULLS LAST, row_no;
~~~

Each department has its own ROW_NUMBER sequence starting from 1. Both the top employee in department 10 and the top employee in department 20 can have ROW_NO = 1.

PARTITION BY does not reduce the number of rows like GROUP BY. It only divides rows into groups so the analytic function computes independently.

## 2. ROW_NUMBER: A Unique Sequential Number for Each Row

**ROW_NUMBER()** assigns 1, 2, 3, ... to rows in the order specified by the analytic ORDER BY. Each row within a partition receives a distinct number, even when sort key values are equal.

Example:

~~~sql
SELECT employee_id,
       full_name,
       salary,
       ROW_NUMBER() OVER (
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS row_no
FROM employees
ORDER BY row_no;
~~~

If three employees share a salary of 20 million, they still receive three different numbers, such as 2, 3, and 4. The ordering among them must be determined by a secondary key if the application requires repeatable, stable results.

### 2.1. ROW_NUMBER Requires Deterministic Ordering

If you write only:

~~~sql
ROW_NUMBER() OVER (ORDER BY salary DESC)
~~~

and multiple rows have the same SALARY, Oracle does not guarantee which row gets the smaller number within the tied salary group. The order can change depending on the execution plan, index, data, or system processing.

To assign numbers stably, add one or more secondary keys so the ORDER BY combination uniquely distinguishes each row:

~~~sql
ROW_NUMBER() OVER (
    ORDER BY salary DESC NULLS LAST,
             employee_id ASC
)
~~~

If EMPLOYEE_ID is a primary key, this key combination establishes a unique order across the employee set.

**ROW_NUMBER always assigns unique numbers, but if ORDER BY does not distinguish tied rows, which row gets which number within the tie group is nondeterministic.** This is the difference between "assigned numbers are unique" and "which row gets which number is deterministic."

### 2.2. Selecting the Top N Rows

To retrieve at most the top 10 highest-paid employees:

~~~sql
SELECT employee_id, full_name, salary
FROM (
    SELECT employee_id,
           full_name,
           salary,
           ROW_NUMBER() OVER (
               ORDER BY salary DESC NULLS LAST,
                        employee_id
           ) AS rn
    FROM employees
)
WHERE rn <= 10
ORDER BY rn;
~~~

ROW_NUMBER is appropriate when business rules require **at most N rows**, without needing to keep all tied rows at the cutoff. If there are fewer than N rows, fewer than N rows are returned.

If the data has 20 employees tied at the 10th-position salary boundary, the query still selects exactly 10 rows according to the defined secondary key.

### 2.3. Selecting the Top N Rows Within Each Group

Example retrieving the top three highest-paid employees in each department:

~~~sql
SELECT department_id,
       employee_id,
       full_name,
       salary
FROM (
    SELECT e.department_id,
           e.employee_id,
           e.full_name,
           e.salary,
           ROW_NUMBER() OVER (
               PARTITION BY e.department_id
               ORDER BY e.salary DESC NULLS LAST,
                        e.employee_id
           ) AS rn
    FROM employees e
)
WHERE rn <= 3
ORDER BY department_id NULLS LAST, rn;
~~~

Each department has its own numbering sequence. The condition RN <= 3 is applied in the outer query block because analytic functions are evaluated after the WHERE clause of the query block containing them.

This is a very common **top-N per group** pattern.

### 2.4. Selecting the Latest Record per Business Key

A history table may hold multiple versions of the same entity. To retrieve the latest version for each CUSTOMER_ID:

~~~sql
SELECT customer_id,
       address_id,
       address_text,
       updated_at
FROM (
    SELECT a.customer_id,
           a.address_id,
           a.address_text,
           a.updated_at,
           ROW_NUMBER() OVER (
               PARTITION BY a.customer_id
               ORDER BY a.updated_at DESC NULLS LAST,
                        a.address_id DESC
           ) AS rn
    FROM customer_address_history a
)
WHERE rn = 1
ORDER BY customer_id;
~~~

ROW_NUMBER = 1 selects the single latest record per customer. ADDRESS_ID acts as a secondary key to ensure a deterministic choice when two versions share the same UPDATED_AT.

If the business needs to keep **all simultaneously latest versions** when timestamps match, ROW_NUMBER is not suitable; consider RANK or DENSE_RANK on the appropriate time key.

### 2.5. Deduplicating by Priority Rules

Suppose imported data has multiple rows for the same customer ID and you want to keep the newest row, preferring a higher-priority source when timestamps are equal:

~~~sql
SELECT customer_id,
       source_code,
       imported_at,
       payload
FROM (
    SELECT s.*,
           ROW_NUMBER() OVER (
               PARTITION BY s.customer_id
               ORDER BY s.imported_at DESC NULLS LAST,
                        CASE s.source_code
                            WHEN 'MASTER' THEN 1
                            WHEN 'CRM' THEN 2
                            ELSE 3
                        END,
                        s.import_id DESC
           ) AS rn
    FROM staging_customer s
)
WHERE rn = 1;
~~~

ORDER BY inside ROW_NUMBER expresses the record-selection policy:
1. More recent import timestamp comes first.
2. If timestamps are equal, the MASTER source is preferred.
3. If still tied, IMPORT_ID breaks the tie.

This is not merely a SQL technique; it is the business rule deciding which record wins. Document the policy clearly so results do not depend on physical data layout.

## 3. RANK: Ranking with Gaps

**RANK()** assigns the same rank to rows with identical values across all sort keys. The next rank increments by the number of preceding rows, so gaps can appear.

Example with descending scores:

| Score | Row count | RANK |
| ---: | ---: | --- |
| 100 | 2 | 1, 1 |
| 90 | 1 | 3 |
| 80 | 1 | 4 |
| 70 | 2 | 5, 5 |

Two people with a score of 100 tie for 1st place. Because two rows already occupy the top rank, the score of 90 receives rank 3 rather than 2.

Syntax:

~~~sql
RANK() OVER (
    [PARTITION BY ...]
    ORDER BY score DESC
)
~~~

### 3.1. RANK by Score in a Competition

~~~sql
SELECT candidate_id,
       candidate_name,
       score,
       RANK() OVER (
           ORDER BY score DESC NULLS LAST
       ) AS competition_rank
FROM exam_result
ORDER BY score DESC NULLS LAST, candidate_id;
~~~

If two candidates have the same score, they share the same COMPETITION_RANK. CANDIDATE_ID is used only in the outermost ORDER BY for stable display; it does not participate in determining ties.

This is how competition-style leaderboards are represented: if two people tie for first place, the next person is in third place.

### 3.2. RANK per Partition

~~~sql
SELECT department_id,
       employee_id,
       full_name,
       salary,
       RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST
       ) AS salary_rank
FROM employees
ORDER BY department_id NULLS LAST,
         salary_rank,
         employee_id;
~~~

Ranking restarts from 1 in each department. Employees with the same salary within a department share the same SALARY_RANK.

### 3.3. RANK <= N to Keep Tied Rows at the Boundary

~~~sql
SELECT employee_id, full_name, salary, salary_rank
FROM (
    SELECT e.employee_id,
           e.full_name,
           e.salary,
           RANK() OVER (
               ORDER BY e.salary DESC NULLS LAST
           ) AS salary_rank
    FROM employees e
)
WHERE salary_rank <= 3
ORDER BY salary_rank, salary DESC NULLS LAST, employee_id;
~~~

The condition RANK <= 3 keeps every row with rank 1, 2, or 3. If multiple rows tie at third place, all of them are kept.

However, if two rows tie for rank 1, the next row has rank 3. The condition RANK <= 2 returns only the rank 1 group, not the rank 3 group. This is the expected behavior of competition ranking, not a bug.

### 3.4. Do Not Add a Unique Key to Analytic ORDER BY When Preserving Ties

Suppose you want two employees with the same salary to be ranked as tied:

~~~sql
RANK() OVER (
    ORDER BY salary DESC
)
~~~

If you write:

~~~sql
RANK() OVER (
    ORDER BY salary DESC, employee_id
)
~~~

and EMPLOYEE_ID is unique, every row will have a distinct combination of sort keys; no rows will tie. RANK then behaves almost like ROW_NUMBER in its ranking output.

Therefore:
- **Keys used to define ties** must be inside the analytic ORDER BY.
- **Keys used only to order the display of tied rows** should be placed in the outermost ORDER BY.

Example:

~~~sql
SELECT employee_id,
       full_name,
       salary,
       RANK() OVER (ORDER BY salary DESC NULLS LAST) AS salary_rank
FROM employees
ORDER BY salary_rank, employee_id;
~~~

Two people with the same salary still receive the same SALARY_RANK, while the output displays rows in ascending EMPLOYEE_ID order within each tie group.

## 4. DENSE_RANK: Ranking Without Gaps

**DENSE_RANK()** also assigns the same rank to rows with matching sort keys, but the next rank increments by exactly one. No rank numbers are skipped after a tie group.

Example:

| Score | Row count | DENSE_RANK |
| ---: | ---: | --- |
| 100 | 2 | 1, 1 |
| 90 | 1 | 2 |
| 80 | 1 | 3 |
| 70 | 2 | 4, 4 |

Syntax:

~~~sql
DENSE_RANK() OVER (
    [PARTITION BY ...]
    ORDER BY score DESC
)
~~~

### 4.1. Ranking Distinct Salary Levels

~~~sql
SELECT employee_id,
       full_name,
       salary,
       DENSE_RANK() OVER (
           ORDER BY salary DESC NULLS LAST
       ) AS salary_level
FROM employees
ORDER BY salary_level, employee_id;
~~~

If salaries are 30 million, 30 million, 20 million, 15 million:
- Both people earning 30 million receive DENSE_RANK = 1.
- The person earning 20 million receives 2.
- The person earning 15 million receives 3.

DENSE_RANK is suitable when you want to rank **distinct value levels**, rather than the position of individual rows in a list.

### 4.2. Retrieving the Top N Highest Salary Levels

~~~sql
SELECT employee_id,
       full_name,
       salary,
       salary_level
FROM (
    SELECT e.employee_id,
           e.full_name,
           e.salary,
           DENSE_RANK() OVER (
               ORDER BY e.salary DESC NULLS LAST
           ) AS salary_level
    FROM employees e
)
WHERE salary_level <= 3
ORDER BY salary_level, employee_id;
~~~

The query returns all employees belonging to the top three distinct salary levels. If 20 people share the highest salary, all 20 are returned; the second and third levels are also kept.

This is where it differs from ROW_NUMBER <= 3, which returns at most three rows.

### 4.3. DENSE_RANK per Group

~~~sql
SELECT department_id,
       employee_id,
       full_name,
       salary,
       DENSE_RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST
       ) AS salary_level
FROM employees
ORDER BY department_id NULLS LAST,
         salary_level,
         employee_id;
~~~

Each department has its own distinct salary levels. Two employees with the same salary in the same department receive the same DENSE_RANK.

## 5. Comparison Using a Small Dataset

Suppose there are six rows in descending score order:

| ID | Name | Score |
| ---: | --- | ---: |
| 101 | An | 100 |
| 102 | Binh | 100 |
| 103 | Chi | 90 |
| 104 | Dung | 80 |
| 105 | Giang | 80 |
| 106 | Hanh | 70 |

Query:

~~~sql
SELECT candidate_id,
       candidate_name,
       score,
       ROW_NUMBER() OVER (
           ORDER BY score DESC, candidate_id
       ) AS rn,
       RANK() OVER (
           ORDER BY score DESC
       ) AS rnk,
       DENSE_RANK() OVER (
           ORDER BY score DESC
       ) AS drnk
FROM exam_result
ORDER BY score DESC, candidate_id;
~~~

Result:

| ID | Score | ROW_NUMBER | RANK | DENSE_RANK |
| ---: | ---: | ---: | ---: | ---: |
| 101 | 100 | 1 | 1 | 1 |
| 102 | 100 | 2 | 1 | 1 |
| 103 | 90 | 3 | 3 | 2 |
| 104 | 80 | 4 | 4 | 3 |
| 105 | 80 | 5 | 4 | 3 |
| 106 | 70 | 6 | 6 | 4 |

Observations:
- ROW_NUMBER distinguishes every row: 1 through 6.
- RANK ties 100 and 80, skipping 2 and 5.
- DENSE_RANK ties like RANK, but score tier ranks are consecutive: 1, 2, 3, 4.

### 5.1. Top 3 Rows vs. Top 3 Score Tiers

With the data above:

| Condition | Selected rows | Row count |
| --- | --- | ---: |
| ROW_NUMBER <= 3 | 100, 100, 90 | 3 |
| RANK <= 3 | 100, 100, 90 | 3 |
| DENSE_RANK <= 3 | 100, 100, 90, 80, 80 | 5 |

In this example, ROW_NUMBER <= 3 and RANK <= 3 happen to return the same three rows. However, if multiple people tie at third place, RANK <= 3 will retain that entire tie group; ROW_NUMBER still cuts off at exactly three rows.

DENSE_RANK <= 3 retrieves the three highest distinct score levels, so it includes both rows with score 80.

## 6. PARTITION BY: Independent Ranking per Group

PARTITION BY splits the dataset into partitions. Each partition is numbered or ranked separately without collapsing partitions.

~~~sql
SELECT department_id,
       employee_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees;
~~~

If departments 10, 20, and 30 exist, each department restarts at RN = 1.

### 6.1. Partitioning by Multiple Columns

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY region, product
    ORDER BY sale_date DESC, sale_id DESC
)
~~~

Each REGION/PRODUCT pair is an independent partition. Within that pair, the most recent transaction comes first; SALE_ID breaks ties.

### 6.2. Partition Does Not Need to Be a Unique Key

PARTITION BY defines logical groups and does not require partition columns to be unique. Multiple rows sharing the same partition value are processed in the same window.

If a partition column is NULL, rows with the same NULL partition key value are grouped into the same partition under analytic semantics. This differs from treating NULL as a value comparable with equals in a WHERE clause.

### 6.3. No PARTITION BY Means One Partition

~~~sql
RANK() OVER (ORDER BY score DESC)
~~~

ranks the entire result set. If you add:

~~~sql
RANK() OVER (PARTITION BY class_id ORDER BY score DESC)
~~~

then ranking restarts per class. Simply adding PARTITION BY changes the meaning of the leaderboard.

## 7. ORDER BY Inside OVER and Final SELECT ORDER BY

A SQL statement can contain two ORDER BY clauses with two different purposes:

1. **ORDER BY inside OVER** determines the order for assigning ROW_NUMBER/RANK/DENSE_RANK.
2. **Outermost ORDER BY** determines the order in which rows are returned to the client.

Example:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees
ORDER BY salary ASC NULLS LAST;
~~~

ROW_NUMBER is still assigned by descending salary within each department, whereas the final displayed output is ordered by ascending salary across the entire dataset.

Without an outermost ORDER BY, display order is not guaranteed, even if the analytic function includes an ORDER BY.

### 7.1. Tie-Breaker in Analytic Order vs. Tie-Breaker in Output Order

Example where you want equal salaries tied in rank, but displayed sorted by ID:

~~~sql
SELECT employee_id,
       salary,
       RANK() OVER (
           ORDER BY salary DESC NULLS LAST
       ) AS salary_rank
FROM employees
ORDER BY salary_rank, employee_id;
~~~

EMPLOYEE_ID only orders rows in the final output; it does not alter the tie groups.

If using ROW_NUMBER, the secondary key must be inside the analytic ORDER BY so number assignment is deterministic:

~~~sql
ROW_NUMBER() OVER (
    ORDER BY salary DESC NULLS LAST, employee_id
)
~~~

Do not mistakenly place a unique key inside RANK/DENSE_RANK if the goal is to preserve ties.

## 8. NULLs in Ranking Keys

Oracle has default NULL ordering:
- ASC defaults to NULLS LAST.
- DESC defaults to NULLS FIRST.

For score/salary leaderboards, you usually want NULLs at the end:

~~~sql
RANK() OVER (
    ORDER BY score DESC NULLS LAST
)
~~~

If NULLS LAST is omitted with DESC, rows with NULL scores may appear first under Oracle's default.

### 8.1. Do Multiple NULL Rows Tie?

If the analytic ORDER BY uses only SCORE and multiple rows have SCORE NULL, they share the same NULL sort key and can receive the same RANK or DENSE_RANK. With ROW_NUMBER, each row still gets a distinct number; ordering among NULL rows requires a secondary key to be deterministic.

~~~sql
SELECT employee_id,
       score,
       ROW_NUMBER() OVER (
           ORDER BY score DESC NULLS LAST, employee_id
       ) AS rn,
       RANK() OVER (
           ORDER BY score DESC NULLS LAST
       ) AS rnk,
       DENSE_RANK() OVER (
           ORDER BY score DESC NULLS LAST
       ) AS drnk
FROM exam_result
ORDER BY rn;
~~~

If NULL means "not graded", business rules might want to exclude those rows from the leaderboard:

~~~sql
SELECT employee_id,
       score,
       RANK() OVER (ORDER BY score DESC) AS score_rank
FROM exam_result
WHERE score IS NOT NULL;
~~~

WHERE is applied before the analytic function in the query block, so rows with NULL SCORE do not participate in ranking. If you still need to display ungraded candidates with a separate status, you can compute the ranking in an inline view over rows with scores and then LEFT JOIN or use CASE in the outer query.

### 8.2. NULL and Replacement Values

Do not use NVL(score, 0) just to push NULLs to the bottom if a score of 0 is a valid value or if "not graded" must be distinguished from "score 0". The cleaner approach is:

~~~sql
ORDER BY score DESC NULLS LAST
~~~

If policy genuinely treats NULL as 0, you can use NVL, but then NULL rows and score-0 rows can tie because they share the same sort key.

## 9. Filtering Ranking Results Using an Inline View or CTE

Analytic functions are computed after WHERE, GROUP BY, and HAVING in the same query block. Therefore, you cannot reference the alias RN in a WHERE clause at the same level:

~~~sql
-- Invalid in the same query block.
SELECT employee_id,
       ROW_NUMBER() OVER (ORDER BY salary DESC) AS rn
FROM employees
WHERE rn <= 5;
~~~

Use an inline view:

~~~sql
SELECT employee_id, salary, rn
FROM (
    SELECT employee_id,
           salary,
           ROW_NUMBER() OVER (
               ORDER BY salary DESC NULLS LAST, employee_id
           ) AS rn
    FROM employees
)
WHERE rn <= 5
ORDER BY rn;
~~~

Or a CTE:

~~~sql
WITH ranked_employees AS (
    SELECT employee_id,
           salary,
           ROW_NUMBER() OVER (
               ORDER BY salary DESC NULLS LAST, employee_id
           ) AS rn
    FROM employees
)
SELECT employee_id, salary, rn
FROM ranked_employees
WHERE rn <= 5
ORDER BY rn;
~~~

An inline view or CTE separates two steps:
1. Compute the rank over the row set.
2. Filter by rank in the outer query block.

The alias RN is scoped only to the query block where it is declared; an outer query block can reference it as a column of the inline view/CTE.

## 10. Ranking GROUP BY Results

Analytic functions can rank already aggregated results. Example ranking departments by total payroll:

~~~sql
SELECT department_id,
       SUM(salary) AS total_salary,
       RANK() OVER (
           ORDER BY SUM(salary) DESC NULLS LAST
       ) AS department_rank
FROM employees
GROUP BY department_id
ORDER BY department_rank, department_id NULLS LAST;
~~~

GROUP BY produces one row per department; RANK then ranks those grouped rows. SUM(salary) can be used directly inside the analytic ORDER BY because it is an aggregate of the query block.

### 10.1. Ranking Revenue by Region

~~~sql
SELECT region,
       SUM(amount) AS revenue,
       DENSE_RANK() OVER (
           ORDER BY SUM(amount) DESC
       ) AS revenue_level
FROM sales
GROUP BY region
ORDER BY revenue_level, region;
~~~

Two regions with the same revenue receive the same DENSE_RANK. If there are three distinct revenue levels, the ranks are 1, 2, 3 with no gaps.

### 10.2. Ranking Within Each Region After Aggregation

~~~sql
SELECT region,
       product,
       SUM(amount) AS revenue,
       RANK() OVER (
           PARTITION BY region
           ORDER BY SUM(amount) DESC
       ) AS product_rank
FROM sales
GROUP BY region, product
ORDER BY region, product_rank, product;
~~~

Each REGION has its own product leaderboard. Products with tied revenue receive the same rank. PRODUCT in the final ORDER BY only stabilizes display order within tied groups.

## 11. Which Function Should You Choose for Top-N?

The three functions are commonly used for top-N filtering, but N can carry three different meanings.

| Business need | Function | Filter condition |
| --- | --- | --- |
| Get at most N exact rows in a deterministic order | ROW_NUMBER | rn <= N |
| Get rows with competition-style rank no greater than N | RANK | rnk <= N |
| Get rows belonging to the top N distinct value levels | DENSE_RANK | drnk <= N |

### 11.1. Get Exactly 5 Rows

~~~sql
SELECT *
FROM (
    SELECT e.employee_id,
           e.full_name,
           e.salary,
           ROW_NUMBER() OVER (
               ORDER BY e.salary DESC NULLS LAST,
                        e.employee_id
           ) AS rn
    FROM employees e
)
WHERE rn <= 5;
~~~

At most five rows are returned. If salaries are tied, EMPLOYEE_ID determines selection order.

### 11.2. Get Everyone in the Top 5 Ranks

~~~sql
SELECT *
FROM (
    SELECT e.employee_id,
           e.full_name,
           e.salary,
           RANK() OVER (
               ORDER BY e.salary DESC NULLS LAST
           ) AS rnk
    FROM employees e
)
WHERE rnk <= 5
ORDER BY rnk, employee_id;
~~~

If multiple people tie at rank 5, all are kept. However, if a tie group at rank 1 has three people, the next rank is 4; the condition RANK <= 5 keeps the rank 1 and rank 4 groups, along with any rank 5 group if present.

### 11.3. Get the Top 5 Distinct Salary Levels

~~~sql
SELECT *
FROM (
    SELECT e.employee_id,
           e.full_name,
           e.salary,
           DENSE_RANK() OVER (
               ORDER BY e.salary DESC NULLS LAST
           ) AS salary_level
    FROM employees e
)
WHERE salary_level <= 5
ORDER BY salary_level, employee_id;
~~~

If there are 100 employees but only 3 distinct salaries, the query only has three salary_level tiers; all employees across those three tiers are returned.

### 11.4. Comparison with FETCH FIRST ... WITH TIES

Oracle supports the row-limiting clause in modern versions:

~~~sql
SELECT employee_id, full_name, salary
FROM employees
ORDER BY salary DESC NULLS LAST
FETCH FIRST 5 ROWS WITH TIES;
~~~

WITH TIES retains rows that share the same values across the entire ORDER BY key as the row at the boundary. If you add a unique EMPLOYEE_ID to ORDER BY, rows usually no longer share the entire sort key, so the effect of preserving ties on SALARY may be lost.

You can use:
- ROW_NUMBER when an exact row count with a tie-breaker is needed.
- RANK when competition-style ranking is desired.
- DENSE_RANK when N distinct values are desired.
- FETCH FIRST ... WITH TIES when row limiting by the ORDER BY key while keeping boundary ties is desired.

## 12. Finding the First Row, Last Row, and Latest Record

ROW_NUMBER is frequently used to pick one representative row per group. However, you must define how ties and NULLs are handled.

### 12.1. Latest Record per Customer

~~~sql
WITH ranked_history AS (
    SELECT h.customer_id,
           h.history_id,
           h.changed_at,
           h.status,
           ROW_NUMBER() OVER (
               PARTITION BY h.customer_id
               ORDER BY h.changed_at DESC NULLS LAST,
                        h.history_id DESC
           ) AS rn
    FROM customer_status_history h
)
SELECT customer_id, history_id, changed_at, status
FROM ranked_history
WHERE rn = 1
ORDER BY customer_id;
~~~

This is a single-record selection pattern. If a CUSTOMER_ID has history rows where all CHANGED_AT values are NULL, the row with the largest HISTORY_ID is selected due to the secondary key; verify whether this policy is appropriate.

### 12.2. Keeping All Records at the Latest Timestamp

If you need to keep all rows tied at the latest timestamp:

~~~sql
WITH ranked_history AS (
    SELECT h.customer_id,
           h.history_id,
           h.changed_at,
           h.status,
           RANK() OVER (
               PARTITION BY h.customer_id
               ORDER BY h.changed_at DESC NULLS LAST
           ) AS rnk
    FROM customer_status_history h
)
SELECT customer_id, history_id, changed_at, status
FROM ranked_history
WHERE rnk = 1
ORDER BY customer_id, history_id;
~~~

Do not include HISTORY_ID in the analytic ORDER BY if you want rows with the same CHANGED_AT to tie. HISTORY_ID belongs only in the outer ORDER BY for stable display.

### 12.3. Getting the Latest Distinct Value Levels

DENSE_RANK = 1 also retrieves the latest group; DENSE_RANK is more useful when you want the latest N distinct timestamp levels:

~~~sql
DENSE_RANK() OVER (
    PARTITION BY customer_id
    ORDER BY changed_at DESC NULLS LAST
)
~~~

The condition DRNK <= 3 retrieves the three most recent distinct CHANGED_AT points for each customer, keeping all rows sharing the same timestamp.

## 13. Deduplication with ROW_NUMBER

A common scenario is staging data containing multiple records for the same business key. ROW_NUMBER can mark the preferred record to select one row.

~~~sql
WITH marked_rows AS (
    SELECT s.*,
           ROW_NUMBER() OVER (
               PARTITION BY s.external_key
               ORDER BY s.received_at DESC NULLS LAST,
                        s.source_priority ASC,
                        s.staging_id DESC
           ) AS rn
    FROM staging_data s
)
SELECT *
FROM marked_rows
WHERE rn = 1;
~~~

Rules:
- Partition by EXTERNAL_KEY.
- Most recently received record comes first.
- If timestamps match, smaller SOURCE_PRIORITY comes first.
- If still tied, larger STAGING_ID comes first.

### 13.1. Do Not Delete Data Using ROW_NUMBER Without Defining Keys

If EXTERNAL_KEY can be NULL, all NULL rows fall into the same partition. ROW_NUMBER = 1 keeps a single row from the entire NULL-key group and removes the rest if used for deletion. This may violate business expectations.

You need to decide:
- Is NULL a single shared key?
- Should each NULL row be preserved separately?
- Is an additional source key needed to distinguish them?

### 13.2. Deleting Duplicates in a Table

You can use ROWID to identify physical rows in a controlled cleanup operation:

~~~sql
DELETE FROM staging_data
WHERE ROWID IN (
    SELECT rid
    FROM (
        SELECT ROWID AS rid,
               ROW_NUMBER() OVER (
                   PARTITION BY external_key
                   ORDER BY received_at DESC NULLS LAST,
                            staging_id DESC
               ) AS rn
        FROM staging_data
    )
    WHERE rn > 1
);
~~~

This example retains one preferred row per EXTERNAL_KEY and deletes the remaining rows. **Do not run this on a production business table without thoroughly defining keys, NULL rules, tie-breakers, backups, and a transaction/rollback plan.** ROWID is a physical row identifier in the current context, not a long-term business key to persist externally.

## 14. ROW_NUMBER, RANK, DENSE_RANK, and GROUP BY

GROUP BY reduces row count by producing one row per group; ranking analytics preserve the input row count of the query block and add an analytic column.

Example:

~~~sql
SELECT department_id,
       salary,
       RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS salary_rank
FROM employees;
~~~

Each employee still appears individually.

Meanwhile:

~~~sql
SELECT department_id,
       MAX(salary) AS max_salary
FROM employees
GROUP BY department_id;
~~~

returns one row per department. GROUP BY does not preserve individual employees to produce per-row ranks.

You can combine GROUP BY and analytic functions:
- GROUP BY produces metrics by department or product.
- RANK or DENSE_RANK ranks those groups.

If you want to keep all employees and add the department total, consider SUM(...) OVER (PARTITION BY ...), though that is a different analytic aggregate function rather than ROW_NUMBER/RANK/DENSE_RANK.

## 15. Position of Analytic Functions in SQL Processing Order

Logically, analytic functions are evaluated after the FROM, WHERE, GROUP BY, and HAVING steps of the query block, but before the final ORDER BY.

Simplified model:

~~~text
FROM / JOIN
    |
WHERE
    |
GROUP BY
    |
HAVING
    |
Analytic functions
    |
Final ORDER BY
~~~

Consequences:
- WHERE filters rows before ranking.
- GROUP BY can change the row set that ranking sees.
- HAVING eliminates groups before analytic functions are computed.
- Filtering on RN/RANK/DENSE_RANK requires an outer query block.
- ORDER BY inside OVER and the final ORDER BY serve separate purposes.

Example with WHERE before ranking:

~~~sql
SELECT employee_id,
       salary,
       ROW_NUMBER() OVER (ORDER BY salary DESC) AS rn
FROM employees
WHERE department_id = 10;
~~~

Only employees in department 10 participate in numbering.

If you want to number the entire company first and then display only people in department 10, compute the ranking in an inline view first:

~~~sql
SELECT employee_id, department_id, salary, rn
FROM (
    SELECT employee_id,
           department_id,
           salary,
           ROW_NUMBER() OVER (
               ORDER BY salary DESC NULLS LAST, employee_id
           ) AS rn
    FROM employees
)
WHERE department_id = 10;
~~~

The two queries have different meanings because the placement of WHERE changes the input row set seen by the analytic function.

## 16. ROW_NUMBER and ROWNUM Are Not the Same

Oracle has the **ROWNUM** pseudocolumn, which is not the ROW_NUMBER analytic function.

- ROWNUM is a sequence number assigned as Oracle selects rows in a query block during execution.
- ROW_NUMBER() OVER (ORDER BY ...) is an analytic function that ranks rows according to a declared ordering.
- ROWNUM has no PARTITION BY.
- ROW_NUMBER can rank independently by group.

The traditional ROWNUM top-N pattern requires placing ORDER BY inside an inline view:

~~~sql
SELECT *
FROM (
    SELECT employee_id, salary
    FROM employees
    ORDER BY salary DESC NULLS LAST, employee_id
)
WHERE ROWNUM <= 5;
~~~

If ROWNUM and ORDER BY are placed in the same query block:

~~~sql
SELECT employee_id, salary
FROM employees
WHERE ROWNUM <= 5
ORDER BY salary DESC;
~~~

Oracle may pick five rows first and then sort those five rows; the result is not necessarily the five highest salaries in the table.

In modern code, ROW_NUMBER or FETCH FIRST usually expresses deterministic top-N queries more clearly. For top-N per partition, ROW_NUMBER is a better choice than ROWNUM.

## 17. Performance and Execution Plans

Ranking functions may require Oracle to sort rows by PARTITION BY and ORDER BY. On large datasets, the operation may use PGA memory or spill to TEMP if the workarea is insufficient.

### 17.1. Reduce the Row Set Before Ranking When Semantics Allow

~~~sql
SELECT employee_id,
       salary,
       RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS salary_rank
FROM employees
WHERE active_flag = 'Y';
~~~

Only ACTIVE employees participate in ranking. If business logic requires ranking everyone first and filtering status afterward, the filter must be placed in an outer query block; the two approaches yield different results.

### 17.2. Indexes May Help, But Do Not Guarantee Avoiding a Sort

An index on the partition key and sort key can assist some access paths:

~~~sql
CREATE INDEX ix_emp_dept_salary
ON employees (department_id, salary DESC, employee_id);
~~~

However, the optimizer may still choose a scan and WINDOW SORT/HASH or another plan depending on the data, filter predicates, and estimated cost. Do not create an index solely because a query uses ROW_NUMBER.

Consider:
- Which columns are in PARTITION BY?
- Which columns and directions are in ORDER BY?
- How large is the dataset after WHERE?
- How many partitions are there and how large is each partition?
- Does the query need to return all columns?
- How much write overhead does the index add?

### 17.3. Viewing the Execution Plan

~~~sql
EXPLAIN PLAN FOR
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

The plan may show operations such as WINDOW SORT, WINDOW NOSORT, or other operations related to analytic processing depending on version and access path. Specific operation names are not a fixed contract.

EXPLAIN PLAN provides an estimated plan, not actual runtime measurements. For production, inspect cursor plans and runtime statistics when authorized, such as DBMS_XPLAN.DISPLAY_CURSOR with appropriate options.

### 17.4. Avoid SELECT * in Large Ranking Queries

When computing ROW_NUMBER on tables with large payloads such as CLOB/BLOB, select only the needed columns in the ranking query block whenever possible. A narrower row set can reduce sort and memory overhead. If you need the full payload after selecting IDs, you can rank the keys first and join back for details in an outer step.

Example:

~~~sql
WITH ranked_ids AS (
    SELECT employee_id,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY salary DESC NULLS LAST, employee_id
           ) AS rn
    FROM employees
)
SELECT e.employee_id,
       e.full_name,
       e.salary
FROM ranked_ids r
JOIN employees e
  ON e.employee_id = r.employee_id
WHERE r.rn <= 3
ORDER BY e.department_id, r.rn;
~~~

Apply this only when the plan and cardinality make sense; an extra join can introduce other costs. Measure on real data.

## 18. Pagination with ROW_NUMBER

You can number the entire result set and retrieve a range of sequence numbers:

~~~sql
SELECT employee_id,
       full_name,
       salary,
       rn
FROM (
    SELECT e.employee_id,
           e.full_name,
           e.salary,
           ROW_NUMBER() OVER (
               ORDER BY e.salary DESC NULLS LAST,
                        e.employee_id
           ) AS rn
    FROM employees e
)
WHERE rn BETWEEN 21 AND 30
ORDER BY rn;
~~~

This is the third page if each page has 10 rows. The EMPLOYEE_ID key makes the order unique within the same dataset.

### 18.1. Deterministic Ordering Does Not Automatically Guarantee a Snapshot Across Requests

Even when ORDER BY includes a unique key, if data changes between requests for page 1 and page 2, a new row can be inserted near the top or an old row can be deleted. OFFSET/ROW_NUMBER pagination can cause users to see duplicate or skipped rows across pages.

If consistency across multiple requests is required, consider:
- Maintaining the same snapshot/transaction if the model permits.
- Capturing an appropriate data snapshot or SCN.
- Using keyset pagination based on the last key of the previous page.
- Explicitly accepting that the list reflects current data on each request.

ROW_NUMBER resolves ordering within a single query execution; it does not lock data across multiple requests.

### 18.2. Keyset Pagination with a Unique Sort Key

If the list is sorted by CREATED_AT DESC and ID DESC, the next page can use the last key from the previous page:

~~~sql
SELECT id, created_at, title
FROM articles
WHERE created_at < :last_created_at
   OR (
       created_at = :last_created_at
       AND id < :last_id
   )
ORDER BY created_at DESC, id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

This approach avoids numbering and skipping rows from previous pages. It assumes CREATED_AT is NOT NULL and ID is a unique key. If CREATED_AT allows NULL, predicate logic matching NULLS FIRST/LAST must be added.

## 19. Sample Dataset for Practice

Create a sandbox table with tied scores, multiple partitions, and a NULL value. This data lets you observe the differences among the three functions.

### 19.1. Create the Table

~~~sql
CREATE TABLE exam_rank_demo (
    candidate_id   NUMBER(6)
        CONSTRAINT pk_exam_rank_demo PRIMARY KEY,
    candidate_name VARCHAR2(80 CHAR) NOT NULL,
    class_id       NUMBER(4) NOT NULL,
    score          NUMBER(5,2)
);
~~~

### 19.2. Load Data

~~~sql
INSERT INTO exam_rank_demo VALUES (101, 'An',    10, 100);
INSERT INTO exam_rank_demo VALUES (102, 'Binh',  10, 100);
INSERT INTO exam_rank_demo VALUES (103, 'Chi',   10, 90);
INSERT INTO exam_rank_demo VALUES (104, 'Dung',  10, 80);
INSERT INTO exam_rank_demo VALUES (105, 'Giang', 10, 80);
INSERT INTO exam_rank_demo VALUES (106, 'Hanh',  10, 70);

INSERT INTO exam_rank_demo VALUES (201, 'Khanh', 20, 95);
INSERT INTO exam_rank_demo VALUES (202, 'Lan',   20, 95);
INSERT INTO exam_rank_demo VALUES (203, 'Minh',  20, 70);
INSERT INTO exam_rank_demo VALUES (204, 'Nga',   20, NULL);

COMMIT;
~~~

Class 10 has six people, and class 20 has four people. Scores 100, 95, and 80 have ties; Nga's row has a NULL score.

### 19.3. Compute All Three Ranking Types Within Each Class

~~~sql
SELECT candidate_id,
       candidate_name,
       class_id,
       score,
       ROW_NUMBER() OVER (
           PARTITION BY class_id
           ORDER BY score DESC NULLS LAST, candidate_id
       ) AS rn,
       RANK() OVER (
           PARTITION BY class_id
           ORDER BY score DESC NULLS LAST
       ) AS rnk,
       DENSE_RANK() OVER (
           PARTITION BY class_id
           ORDER BY score DESC NULLS LAST
       ) AS drnk
FROM exam_rank_demo
ORDER BY class_id, rn;
~~~

Expected result:

| Class | ID | Score | ROW_NUMBER | RANK | DENSE_RANK |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 101 | 100 | 1 | 1 | 1 |
| 10 | 102 | 100 | 2 | 1 | 1 |
| 10 | 103 | 90 | 3 | 3 | 2 |
| 10 | 104 | 80 | 4 | 4 | 3 |
| 10 | 105 | 80 | 5 | 4 | 3 |
| 10 | 106 | 70 | 6 | 6 | 4 |
| 20 | 201 | 95 | 1 | 1 | 1 |
| 20 | 202 | 95 | 2 | 1 | 1 |
| 20 | 203 | 70 | 3 | 3 | 2 |
| 20 | 204 | NULL | 4 | 4 | 3 |

In each class, ROW_NUMBER restarts at 1. Two people with the same score receive the same RANK and DENSE_RANK. The NULL score appears last because of DESC NULLS LAST.

### 19.4. Top Two Rows per Class

~~~sql
SELECT candidate_id, candidate_name, class_id, score
FROM (
    SELECT e.*,
           ROW_NUMBER() OVER (
               PARTITION BY class_id
               ORDER BY score DESC NULLS LAST, candidate_id
           ) AS rn
    FROM exam_rank_demo e
)
WHERE rn <= 2
ORDER BY class_id, rn;
~~~

Result has at most two rows per class:
- Class 10: An and Binh.
- Class 20: Khanh and Lan.

Even though two people have the same score, ROW_NUMBER selects exactly two rows thanks to candidate_id as a tie-breaker.

### 19.5. Top Two Ranks per Class

~~~sql
SELECT candidate_id, candidate_name, class_id, score, rnk
FROM (
    SELECT e.*,
           RANK() OVER (
               PARTITION BY class_id
               ORDER BY score DESC NULLS LAST
           ) AS rnk
    FROM exam_rank_demo e
)
WHERE rnk <= 2
ORDER BY class_id, rnk, candidate_id;
~~~

Both An and Binh (rank 1) are kept; the next rank is 3 so there is no row at rank 2. The result for each class contains only the two people tied for first place. This is how RANK handles gaps.

### 19.6. Top Two Distinct Score Tiers per Class

~~~sql
SELECT candidate_id, candidate_name, class_id, score, drnk
FROM (
    SELECT e.*,
           DENSE_RANK() OVER (
               PARTITION BY class_id
               ORDER BY score DESC NULLS LAST
           ) AS drnk
    FROM exam_rank_demo e
)
WHERE drnk <= 2
ORDER BY class_id, drnk, candidate_id;
~~~

Result:
- Class 10: two people with score 100 and one person with score 90.
- Class 20: two people with score 95 and one person with score 70.

DENSE_RANK <= 2 retrieves the two highest distinct score levels, not two rows.

### 19.7. Filtering Out NULL Scores Before Ranking

~~~sql
SELECT candidate_id,
       candidate_name,
       score,
       RANK() OVER (
           ORDER BY score DESC
       ) AS rnk
FROM exam_rank_demo
WHERE score IS NOT NULL
ORDER BY rnk, candidate_id;
~~~

Nga's row does not participate in the leaderboard. If you still want to display Nga with a NOT GRADED status, you can compute the ranking in an inline view over rows with scores and then LEFT JOIN or use CASE in the outer query.

### 19.8. Clean Up the Sandbox Table

~~~sql
DROP TABLE exam_rank_demo PURGE;
~~~

Only drop the sandbox table created for this lesson when you are certain the data is no longer needed. DROP TABLE is DDL with implicit commit behavior; PURGE bypasses the recycle bin as usual.

## 20. Common Pitfalls and Misconceptions

| Symptom | Cause | Resolution |
| --- | --- | --- |
| ROW_NUMBER changes between runs | ORDER BY has tied rows without a tie-breaker | Add a unique secondary key to the analytic ORDER BY |
| RANK skips rank numbers | Multiple rows are tied | This is expected behavior; use DENSE_RANK if you do not want gaps |
| DENSE_RANK <= 3 returns more than 3 rows | Retrieves the top three distinct sort key tiers, keeping all tied rows | Use ROW_NUMBER if at most three rows are needed |
| RANK does not keep all rows in top N as expected | Ranks skipped due to ties in an earlier group | Clarify whether you need N competition ranks or N distinct levels |
| Two people with the same score no longer tie | A unique ID was added to the analytic ORDER BY | Use only score in RANK/DENSE_RANK; put ID in the outer ORDER BY |
| NULLs appear first when using DESC | Oracle's default is NULLS FIRST | Write DESC NULLS LAST if NULLs must appear last |
| Cannot filter RN in WHERE at the same level | Analytic functions are evaluated after WHERE | Wrap the query in an inline view or CTE |
| ORDER BY inside OVER does not sort output | Window order and final order serve two different purposes | Add ORDER BY to the outermost query block |
| Top-N per group returns the wrong count | Missing PARTITION BY or wrong partition key | Redefine the business grouping |
| ROW_NUMBER picks the wrong latest record | Priority order or tie-breaker is incorrect | Specify the full record-selection policy |
| Pagination duplicates/misses rows across requests | Data changes or non-unique ordering | Total order, keyset pagination, or snapshot |
| Large sort consumes TEMP | Large dataset or wide sort key | Filter per semantics, reduce columns, inspect plan and workload |

## 21. Workflow for Choosing a Ranking Function

Before writing a query, determine:

1. **What unit is being ranked?** Individual rows, employees, products, or aggregated groups?
2. **What is the scope?** Company-wide or independent per department/region/class?
3. **Which columns form the ranking key?** How do those columns define ties?
4. **Is a tie-breaker** only used to pick one row, or is it allowed to change the tie definition?
5. **Should NULLs** be placed first, last, or excluded from the ranking set?
6. Does the business need **exactly N rows**, **N competition ranks**, or **N distinct values**?
7. If filtering by rank, is the analytic function placed inside an inline view/CTE?
8. Is there a final ORDER BY to guarantee the returned row order?
9. Can the dataset change between pages/requests?
10. Does the execution plan have a large sort, TEMP usage, or an access path needing optimization?

Selection guide:

| Requirement | Choice |
| --- | --- |
| Number every row sequentially | ROW_NUMBER |
| Pick one best record per key | ROW_NUMBER with PARTITION BY and a tie-breaker |
| Competition-style leaderboard, ties with gaps | RANK |
| Rank distinct value tiers, no gaps | DENSE_RANK |
| Exact top N rows | ROW_NUMBER <= N |
| Top N ranks keeping ties | RANK <= N |
| Top N distinct values | DENSE_RANK <= N |

## 22. Self-Practice Exercises

1. Given scores 100, 100, 90, 80, compute ROW_NUMBER, RANK, and DENSE_RANK in descending order.
2. Explain why the RANK of 90 is 3 while its DENSE_RANK is 2.
3. Write a query to retrieve the top five highest-paid employees, ensuring deterministic results when salaries tie.
4. Write a query to retrieve all employees belonging to the top three distinct salary levels.
5. Write a query to retrieve the top three employees in each department using ROW_NUMBER.
6. Replace ROW_NUMBER with RANK and explain the change in returned row count when there is a tie at third place.
7. Write DENSE_RANK by score for each class and retrieve the top two score levels.
8. Why should you not add EMPLOYEE_ID to the analytic ORDER BY of RANK if you want to keep salary ties?
9. How can you sort the output by EMPLOYEE_ID within tie groups without changing ranks?
10. When SALARY is NULL and ORDER BY SALARY DESC is used, where does Oracle place NULLs by default? Write the syntax to move NULLs to the end.
11. Write a query to select the latest address of each customer, using ID to break ties.
12. If you need to keep all addresses with the exact same latest timestamp, should you use ROW_NUMBER or RANK? Why?
13. A partition has two rows with NULL EXTERNAL_KEY. Under PARTITION BY EXTERNAL_KEY, how are they processed?
14. Why can't the RN alias be used in the WHERE clause of the same query block?
15. Rewrite the query filtering RN = 1 using a CTE.
16. Compare WHERE placed before the analytic function with WHERE filtering RN in an outer query block.
17. Rank departments by SUM(SALARY) after GROUP BY.
18. Distinguish ORDER BY inside OVER from ORDER BY at the end of a SELECT statement.
19. Why does ROWNUM <= 5 in the same query block as ORDER BY not always return the top five rows?
20. Compare ROW_NUMBER <= 5, RANK <= 5, and DENSE_RANK <= 5 using a dataset with a tie at the boundary.
21. A pagination query using ROW_NUMBER has a unique ordering. Why can data changes between two requests still cause users to see duplicate or missing rows?
22. When is keyset pagination more appropriate than OFFSET/ROW_NUMBER pagination?
23. Inspect the execution plan of a ROW_NUMBER query by DEPARTMENT_ID and SALARY. Look for sort/window operations if they appear.
24. A staging table has multiple records with the same business key. Define a priority order and write a query that keeps exactly one record.

**ROW_NUMBER numbers each row, RANK ranks ties with gaps, and DENSE_RANK ranks ties without gaps.** PARTITION BY defines the ranking scope; ORDER BY inside OVER defines ordering and ties; the outermost ORDER BY controls display order. When you choose the right function, handle NULLs explicitly, and add tie-breakers in the right place, top-N queries, leaderboards, and latest-record selections will match business requirements and remain stable over the same dataset.
