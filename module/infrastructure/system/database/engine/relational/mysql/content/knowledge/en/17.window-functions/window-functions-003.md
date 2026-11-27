# ROW_NUMBER, RANK, and DENSE_RANK

MySQL provides three commonly used window functions for numbering and ranking rows: `ROW_NUMBER()`, `RANK()`, and `DENSE_RANK()`. All three use the `OVER()` clause to define the row scope and comparison order. They frequently appear in leaderboards, top-N per group, selecting the latest record per customer, and handling data with tied scores.

The key difference lies in how they handle tied rows (peer rows): `ROW_NUMBER()` always assigns a distinct number to every row; `RANK()` assigns the same rank to equal rows and skips the subsequent rank numbers; `DENSE_RANK()` also assigns the same rank without leaving gaps. To pick the right function, first determine whether the business logic requires a per-row sequence number or a value-based rank.

Window functions are supported in MySQL starting in version 8.0. MySQL 5.7 and earlier do not support window function syntax. This lesson assumes MySQL 8.0 or higher.

## 1. Window functions and OVER() syntax

A window function computes a value for each row based on a group of related rows while preserving individual rows in the result. Unlike `GROUP BY`, it does not collapse multiple rows into a single summary row.

General syntax:

```sql
window_function() OVER (
    [PARTITION BY expression [, expression ...]]
    [ORDER BY expression [ASC | DESC] [, expression ...]]
)
```

- `PARTITION BY` divides the result into independent groups; the function restarts from the beginning in each group.
- `ORDER BY` defines the row order used for numbering or ranking within each group.
- If `PARTITION BY` is omitted, the entire result set belongs to a single partition.
- For ranking functions, rows that share identical values across all `ORDER BY` expressions are called peer rows (tied rows).

The three functions in this lesson take no arguments:

```sql
ROW_NUMBER() OVER (...)
RANK() OVER (...)
DENSE_RANK() OVER (...)
```

## 2. Preparing practice data

Suppose a system stores employee evaluation scores by department:

```sql
CREATE TABLE employee_scores (
    employee_id BIGINT UNSIGNED NOT NULL,
    employee_name VARCHAR(100) NOT NULL,
    department VARCHAR(50) NOT NULL,
    score DECIMAL(5, 2) NULL,
    PRIMARY KEY (employee_id),
    KEY idx_employee_scores_department_score (department, score)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;

INSERT INTO employee_scores
    (employee_id, employee_name, department, score)
VALUES
    (1, 'An',   'Sales',       95.00),
    (2, 'Bình', 'Sales',       90.00),
    (3, 'Chi',  'Sales',       90.00),
    (4, 'Dũng', 'Sales',       80.00),
    (5, 'Hoa',  'Engineering', 99.00),
    (6, 'Khoa', 'Engineering', 99.00),
    (7, 'Lan',  'Engineering', 92.00),
    (8, 'Minh', 'Engineering', 85.00);
```

In each department, several employees have identical scores. This dataset is ideal for seeing the differences among the three functions.

## 3. ROW_NUMBER(): numbering each row individually

`ROW_NUMBER()` assigns a consecutive integer starting at 1 to each row in a partition according to the declared order. Every row always receives a distinct number, even when rows share the same score.

```sql
SELECT
    employee_id,
    employee_name,
    department,
    score,
    ROW_NUMBER() OVER (
        PARTITION BY department
        ORDER BY score DESC, employee_id ASC
    ) AS row_num
FROM employee_scores
ORDER BY department, row_num;
```

Sample output:

| Department | Employee | Score | row_num |
| --- | --- | ---: | ---: |
| Engineering | Hoa | 99.00 | 1 |
| Engineering | Khoa | 99.00 | 2 |
| Engineering | Lan | 92.00 | 3 |
| Engineering | Minh | 85.00 | 4 |
| Sales | An | 95.00 | 1 |
| Sales | Bình | 90.00 | 2 |
| Sales | Chi | 90.00 | 3 |
| Sales | Dũng | 80.00 | 4 |

`PARTITION BY department` resets the numbering to 1 for each department. `employee_id` is added after `score` to break ties between two people with the same score, making `ROW_NUMBER()` deterministic and repeatable as long as data does not change.

If `PARTITION BY department` is omitted, MySQL numbers all employees in a single set. If `ORDER BY` is omitted, the numbering order is nondeterministic; do not rely on that for business cases requiring stable ordering.

## 4. RANK(): ranking with gaps after ties

`RANK()` assigns the same rank to rows that share identical values across all `ORDER BY` expressions. The next rank is based on row position, creating a gap after a tied group.

```sql
SELECT
    employee_id,
    employee_name,
    department,
    score,
    RANK() OVER (
        PARTITION BY department
        ORDER BY score DESC
    ) AS score_rank
FROM employee_scores
ORDER BY department, score_rank, employee_id;
```

Sample output:

| Department | Employee | Score | score_rank |
| --- | --- | ---: | ---: |
| Engineering | Hoa | 99.00 | 1 |
| Engineering | Khoa | 99.00 | 1 |
| Engineering | Lan | 92.00 | 3 |
| Engineering | Minh | 85.00 | 4 |
| Sales | An | 95.00 | 1 |
| Sales | Bình | 90.00 | 2 |
| Sales | Chi | 90.00 | 2 |
| Sales | Dũng | 80.00 | 4 |

Both Engineering employees with a score of 99 receive rank 1. The next person receives rank 3 because two rows precede them. Similarly, two Sales employees with a score of 90 receive rank 2, and the next receives rank 4.

This is the standard ranking style used in competitions or scoreboards, where tied participants share a position and the subsequent position number is skipped.

## 5. DENSE_RANK(): consecutive ranking without gaps

`DENSE_RANK()` also assigns the same rank to tied rows, but the next rank increases by only 1 regardless of how many rows were in the preceding group.

```sql
SELECT
    employee_id,
    employee_name,
    department,
    score,
    DENSE_RANK() OVER (
        PARTITION BY department
        ORDER BY score DESC
    ) AS dense_score_rank
FROM employee_scores
ORDER BY department, dense_score_rank, employee_id;
```

Sample output:

| Department | Employee | Score | dense_score_rank |
| --- | --- | ---: | ---: |
| Engineering | Hoa | 99.00 | 1 |
| Engineering | Khoa | 99.00 | 1 |
| Engineering | Lan | 92.00 | 2 |
| Engineering | Minh | 85.00 | 3 |
| Sales | An | 95.00 | 1 |
| Sales | Bình | 90.00 | 2 |
| Sales | Chi | 90.00 | 2 |
| Sales | Dũng | 80.00 | 3 |

If the goal is to rank distinct score tiers, `DENSE_RANK()` is typically appropriate: the highest score tier is rank 1, and the second highest tier is rank 2, even if multiple people achieved the top tier.

## 6. Comparing the three functions on the same group

With Sales scores of `95, 90, 90, 80`, the results are:

| Score | ROW_NUMBER* | RANK | DENSE_RANK |
| ---: | ---: | ---: | ---: |
| 95 | 1 | 1 | 1 |
| 90 | 2 | 2 | 2 |
| 90 | 3 | 2 | 2 |
| 80 | 4 | 4 | 3 |

`ROW_NUMBER*` in the table assumes an additional tie-breaker key, such as `employee_id`, to decide which row receives 2 and which receives 3. If you only sort by score, the two rows with score 90 still receive distinct `ROW_NUMBER()` values, but their relative order is not guaranteed.

| Function | Tied rows | Rank after a tied group | Common use cases |
| --- | --- | --- | --- |
| `ROW_NUMBER()` | Each row gets a distinct number | Always consecutive | Picking exact N rows, pagination, taking one record in deterministic order |
| `RANK()` | Same rank | Has gaps | Competition standings or position-based scoreboards |
| `DENSE_RANK()` | Same rank | No gaps | Ranking distinct value tiers or score levels |

## 7. Peer rows are determined by the entire ORDER BY in OVER

Two rows are considered tied when all expressions in the window's `ORDER BY` evaluate to equal values under their comparison rules. For example:

```sql
RANK() OVER (
    PARTITION BY department
    ORDER BY score DESC
)
```

Employees with the same `score` within the same `department` are peer rows.

However, if you add the primary key to the same window:

```sql
RANK() OVER (
    PARTITION BY department
    ORDER BY score DESC, employee_id ASC
)
```

Each row has a different `employee_id`, so employees with the same score are no longer peer rows. The `RANK()` output becomes distinct consecutive numbers, defeating the purpose of tying by score.

Therefore:

- For `RANK()` and `DENSE_RANK()`, include in `ORDER BY` only the criteria that actually define the business ranking.
- For `ROW_NUMBER()`, add a unique key as a tie-breaker when stable sequential numbering is needed.
- If you need both score-based ranking and a deterministic per-row sequence number, compute both functions in the same query using two different window specifications.

Example:

```sql
SELECT
    employee_id,
    employee_name,
    department,
    score,
    RANK() OVER (
        PARTITION BY department
        ORDER BY score DESC
    ) AS score_rank,
    ROW_NUMBER() OVER (
        PARTITION BY department
        ORDER BY score DESC, employee_id ASC
    ) AS row_num
FROM employee_scores;
```

This query preserves score ties while also providing a unique, deterministic sequence number for each employee.

## 8. PARTITION BY: ranking within each group

`PARTITION BY` splits the result set into independent partitions. Each function resets its calculation in every partition.

Example ranking employees within each department:

```sql
SELECT
    department,
    employee_name,
    score,
    RANK() OVER (
        PARTITION BY department
        ORDER BY score DESC
    ) AS department_rank
FROM employee_scores;
```

If `PARTITION BY` is omitted, rankings are computed company-wide:

```sql
SELECT
    department,
    employee_name,
    score,
    RANK() OVER (
        ORDER BY score DESC
    ) AS company_rank
FROM employee_scores;
```

You can partition by multiple columns:

```sql
RANK() OVER (
    PARTITION BY department, review_period
    ORDER BY score DESC
)
```

In this case, each `(department, review_period)` pair forms its own partition. Choose partitioning columns matching the business ranking scope: system-wide, per department, per review period, or per region.

## 9. ORDER BY in OVER vs. query ORDER BY

`ORDER BY` inside `OVER()` defines the ordering used to compute sequence numbers or ranks. It **does not guarantee the final order of rows returned to the client**.

Example:

```sql
SELECT
    employee_id,
    employee_name,
    score,
    ROW_NUMBER() OVER (ORDER BY score DESC, employee_id) AS row_num
FROM employee_scores;
```

The function computes `row_num` in descending score order, yet the final display order is still not guaranteed if the outer query lacks `ORDER BY`.

To display results in ranked order:

```sql
SELECT
    employee_id,
    employee_name,
    score,
    ROW_NUMBER() OVER (ORDER BY score DESC, employee_id) AS row_num
FROM employee_scores
ORDER BY score DESC, employee_id;
```

With partitions, you can display by group and then by rank:

```sql
SELECT
    employee_id,
    employee_name,
    department,
    score,
    DENSE_RANK() OVER (
        PARTITION BY department
        ORDER BY score DESC
    ) AS score_rank
FROM employee_scores
ORDER BY department, score_rank, employee_id;
```

Do not rely on physical table order or accidental index scan order in place of an outer `ORDER BY`.

## 10. Ranking after data aggregation

Window functions can be applied on top of `GROUP BY` results. For example, ranking departments by total revenue:

Suppose an orders table records the department associated with each order's revenue:

```sql
CREATE TABLE department_orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    department VARCHAR(50) NOT NULL,
    total_amount DECIMAL(13, 2) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_department_orders_department (department)
) ENGINE=InnoDB;
```

```sql
SELECT
    department,
    total_revenue,
    RANK() OVER (ORDER BY total_revenue DESC) AS revenue_rank
FROM (
    SELECT
        department,
        SUM(total_amount) AS total_revenue
    FROM department_orders
    GROUP BY department
) AS department_totals
ORDER BY revenue_rank, department;
```

The derived table first creates one row per department; `RANK()` then ranks the total revenues. You can use a CTE to express the same logic more clearly:

```sql
WITH department_totals AS (
    SELECT
        department,
        SUM(total_amount) AS total_revenue
    FROM department_orders
    GROUP BY department
)
SELECT
    department,
    total_revenue,
    DENSE_RANK() OVER (ORDER BY total_revenue DESC) AS revenue_rank
FROM department_totals
ORDER BY revenue_rank, department;
```

In this query, two departments with equal total revenue receive the same rank. If you use `ROW_NUMBER()` with `department` as a tie-breaker, each department gets a distinct number, but ties are no longer represented.

## 11. Top-N rows per group

A common use case is retrieving the top three employees in each department. You cannot filter directly on a window function alias in `WHERE` within the same query block, because `WHERE` is evaluated before window values are computed. Wrap the query in a CTE or derived table.

### 11.1. Exactly up to N rows per group

Use `ROW_NUMBER()` when you want at most three rows per department:

```sql
WITH ranked_employees AS (
    SELECT
        employee_id,
        employee_name,
        department,
        score,
        ROW_NUMBER() OVER (
            PARTITION BY department
            ORDER BY score DESC, employee_id ASC
        ) AS row_num
    FROM employee_scores
)
SELECT
    employee_id,
    employee_name,
    department,
    score,
    row_num
FROM ranked_employees
WHERE row_num <= 3
ORDER BY department, row_num;
```

Each department returns at most three rows. If there is a tie for third place, `employee_id` decides which person is included in the three selected rows.

### 11.2. Retrieving everyone ranked within the top N

Use `RANK()` when you want to keep all tied rows in the top positions:

```sql
WITH ranked_employees AS (
    SELECT
        employee_id,
        employee_name,
        department,
        score,
        RANK() OVER (
            PARTITION BY department
            ORDER BY score DESC
        ) AS score_rank
    FROM employee_scores
)
SELECT *
FROM ranked_employees
WHERE score_rank <= 3
ORDER BY department, score_rank, employee_id;
```

If multiple employees tie for rank 3, all of them are returned. The result may have more than three rows per department.

### 11.3. Retrieving the top N distinct value tiers

Use `DENSE_RANK()` when you want the top three highest score levels in each department:

```sql
WITH ranked_employees AS (
    SELECT
        employee_id,
        employee_name,
        department,
        score,
        DENSE_RANK() OVER (
            PARTITION BY department
            ORDER BY score DESC
        ) AS score_level
    FROM employee_scores
)
SELECT *
FROM ranked_employees
WHERE score_level <= 3
ORDER BY department, score_level, employee_id;
```

This query keeps all employees belonging to the top three highest score tiers, regardless of how many employees are at each tier.

## 12. Retrieving the latest record per group

Another pattern is picking the latest order for each customer. Use `ROW_NUMBER()` to number orders per customer:

```sql
WITH numbered_orders AS (
    SELECT
        id,
        customer_id,
        status,
        created_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC, id DESC
        ) AS row_num
    FROM orders
)
SELECT
    id,
    customer_id,
    status,
    created_at
FROM numbered_orders
WHERE row_num = 1
ORDER BY customer_id;
```

`id DESC` breaks ties between orders sharing the same `created_at`. Without a tie-breaker, which order is picked among same-timestamp orders can vary across executions.

If you want to return all orders tied at the latest timestamp for each customer, use `RANK()` and sort only by `created_at DESC`:

```sql
WITH ranked_orders AS (
    SELECT
        id,
        customer_id,
        status,
        created_at,
        RANK() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC
        ) AS time_rank
    FROM orders
)
SELECT *
FROM ranked_orders
WHERE time_rank = 1;
```

The two queries solve two different requirements: picking a single latest record versus keeping all records tied at the latest timestamp.

## 13. NULLs in ranking function ORDER BY

MySQL treats `NULL` as smaller than non-`NULL` values when sorting. Consequently, `ORDER BY score DESC` places `NULL` scores last; `ORDER BY score ASC` places `NULL`s first.

If multiple rows have `score IS NULL` and the window only sorts by `score`, they are peer rows and receive the same `RANK()`/`DENSE_RANK()`. If business rules dictate not ranking unscored rows, filter them out before computing the function:

```sql
WITH scored AS (
    SELECT
        employee_id,
        employee_name,
        department,
        score,
        RANK() OVER (
            PARTITION BY department
            ORDER BY score DESC
        ) AS score_rank
    FROM employee_scores
    WHERE score IS NOT NULL
)
SELECT *
FROM scored
ORDER BY department, score_rank, employee_id;
```

If you still need to keep unscored employees in the output without ranking them alongside scored ones, separate scored and unscored rows using distinct queries/CTEs or add an explicit ranking status column. Do not replace `NULL` with 0 if 0 is a valid score and the two meanings must remain distinct.

## 14. Collation and data types affecting peer rows

For `ORDER BY` on text columns, collation determines comparison behavior. Two strings may be considered equal under a case-insensitive or accent-insensitive collation; in that case, they become peer rows for `RANK()` and `DENSE_RANK()`.

Example:

```sql
SELECT
    employee_id,
    employee_name,
    RANK() OVER (
        ORDER BY employee_name COLLATE utf8mb4_0900_ai_ci
    ) AS name_rank
FROM employee_scores;
```

The illustrated collation belongs to MySQL 8.0. It is case-insensitive and accent-insensitive. If sensitivity is required, pick a collation matching your requirements and check the collations available on your server.

For numbers and dates/times, store values using proper data types (`DECIMAL`, `DATE`, `DATETIME`, `TIMESTAMP`) rather than inconsistently formatted strings. Sorting string representations of numbers or dates can cause lexicographical order to diverge from numeric/chronological order.

## 15. Window functions cannot be filtered directly in WHERE of the same query block

Logical query processing order means `WHERE` is applied before window functions produce results. Thus, the following statement is invalid:

```sql
-- Invalid: cannot use a window alias in WHERE within the same query block
SELECT
    employee_id,
    score,
    ROW_NUMBER() OVER (ORDER BY score DESC) AS row_num
FROM employee_scores
WHERE row_num <= 3;
```

Use a CTE or derived table:

```sql
WITH numbered AS (
    SELECT
        employee_id,
        score,
        ROW_NUMBER() OVER (ORDER BY score DESC, employee_id) AS row_num
    FROM employee_scores
)
SELECT employee_id, score, row_num
FROM numbered
WHERE row_num <= 3;
```

MySQL does not support a `QUALIFY` clause like some other database engines. A CTE/derived table is the standard way to filter window function results.

## 16. Performance and indexing for ranking

Window functions may require sorting rows by partition and window order. Appropriate indexes can help reduce read or sort work for certain queries, though they do not guarantee MySQL will always eliminate the sort step.

Example ranking query by department and score:

```sql
SELECT
    employee_id,
    department,
    score,
    RANK() OVER (
        PARTITION BY department
        ORDER BY score DESC
    ) AS score_rank
FROM employee_scores;
```

An index starting with `(department, score)` is a candidate worth evaluating. If deterministic ordering for `ROW_NUMBER()` is needed, an index on `(department, score, employee_id)` may align with query order, depending on index key directions and MySQL version.

Inspect the plan:

```sql
EXPLAIN
SELECT
    employee_id,
    department,
    score,
    RANK() OVER (
        PARTITION BY department
        ORDER BY score DESC
    ) AS score_rank
FROM employee_scores;
```

In MySQL 8.0.18 and later, you can use `EXPLAIN ANALYZE` to measure actual row counts and execution time. Check data volume, sorts, temporary tables, and read costs; avoid creating multiple nearly identical indexes unless the workload proves the benefit.

## 17. Common mistakes and misconceptions

| Misconception / mistake | Reality | Resolution |
| --- | --- | --- |
| `ROW_NUMBER`, `RANK`, and `DENSE_RANK` give the same result | They differ in how peer rows and rank gaps are handled | Choose according to business requirements |
| Adding the primary key to RANK's ORDER BY is always good | A unique key breaks score-based tie groups | Only add tie-breakers to `ROW_NUMBER` or outer display ORDER BY |
| ORDER BY inside OVER guarantees display order | It only controls window evaluation | Add `ORDER BY` to the outer query |
| PARTITION BY is the same as GROUP BY | PARTITION BY does not collapse rows into one row | Use window functions when row-level detail must be preserved |
| You can filter on a row number alias in WHERE | WHERE executes before window functions | Wrap in a CTE or derived table |
| RANK() <= 3 always returns exactly 3 rows per group | Ties can push the row count past three | Use ROW_NUMBER if at most N rows are strictly required |
| DENSE_RANK() <= 3 means three rows | It selects the top three distinct value tiers/ranks | Distinguish row count from number of rank tiers |
| Omitting ORDER BY in OVER still uses natural order | Numbering order is nondeterministic | Declare explicit ordering and tie-breakers |

## 18. Workflow for choosing a ranking function

Before writing the query, answer:

1. Do we need to number individual rows or rank by value?
2. Should two rows with the same score/value be tied?
3. After a tied group, should the next rank skip numbers?
4. Is the ranking scope the entire dataset or grouped by `PARTITION BY`?
5. Does the window `ORDER BY` include only business criteria, or was a unique key accidentally added that breaks ties?
6. If using `ROW_NUMBER()`, is there a unique tie-breaker for deterministic results?
7. Should rows with `NULL` be ranked; does `NULL` placement match business rules?
8. Should we filter top-N rows, top-N ranks, or top-N value tiers?
9. Is the query wrapped in a CTE/derived table to filter window results?
10. Have execution plans and performance been verified on representative data?

## 19. Practice exercises

1. Create the `employee_scores` table as shown in the example and insert at least two employees with identical scores in each department.
2. Compute `ROW_NUMBER()`, `RANK()`, and `DENSE_RANK()` company-wide; compare the results.
3. Add `PARTITION BY department` and observe rankings restarting in each department.
4. Add `employee_id` to `RANK()`'s `ORDER BY`; explain why rows with equal scores are no longer tied.
5. Compute both `RANK()` by score and `ROW_NUMBER()` by score plus primary key in the same SELECT.
6. Retrieve at most three employees per department using `ROW_NUMBER()`.
7. Retrieve all employees ranked in the top three positions using `RANK()`; create a tie at the third position.
8. Retrieve employees belonging to the top three highest score tiers per department using `DENSE_RANK()`.
9. Use `ROW_NUMBER()` to retrieve the latest order per customer; test with data containing two orders sharing the same `created_at`.
10. Add a row with a `NULL` score, inspect the ordering, and try filtering NULLs out before ranking.
11. Use `EXPLAIN` to inspect the plan for a query with `PARTITION BY` and `ORDER BY`; test an appropriate index in a lab environment.

## 20. Takeaways

`ROW_NUMBER()` assigns consecutive, distinct numbers to every row; `RANK()` assigns the same rank to tied rows and skips subsequent rank numbers; `DENSE_RANK()` assigns the same rank without leaving gaps. `PARTITION BY` splits the calculation scope and resets numbering/ranking in each group. `ORDER BY` inside `OVER()` defines calculation order, not guaranteed final result order.

Peer rows are determined by the complete `ORDER BY` expression list in the window. Do not add a unique key to `RANK()`/`DENSE_RANK()` if business rules require preserving ties; for `ROW_NUMBER()`, add a unique tie-breaker for stable results. To filter top-N, use a CTE or derived table because MySQL does not allow filtering directly on a window alias in `WHERE` within the same query block. Choose the function based on ranking semantics first, then verify indexes and `EXPLAIN` on MySQL 8.0+.
