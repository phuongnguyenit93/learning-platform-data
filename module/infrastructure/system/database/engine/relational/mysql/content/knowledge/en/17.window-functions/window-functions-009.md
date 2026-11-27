# WINDOW Clause and Reusing Window Definitions

When a query needs multiple window functions sharing the same partitioning and ordering, repeating the entire `PARTITION BY` and `ORDER BY` inside every `OVER (...)` makes the SQL verbose and prone to logic drift. MySQL lets you assign a name to a window definition in a `WINDOW` clause and then reference that name across multiple functions via `OVER window_name`.

Named windows gather partitioning, ordering, and sometimes frame rules into one shared definition, making queries more consistent and maintainable. A window name is scoped strictly to the query block containing `WINDOW`; it is not a table, session variable, or data cache. Reusing a definition also does not guarantee the optimizer will sort data only once, as the physical execution plan is still decided by MySQL.

This lesson is part of the **DATABASE_MYSQL** module. The module aims to master MySQL from table design, data types, keys, and SQL queries to indexes, transactions, and concurrency control, alongside practicing execution plan reading, query optimization, privilege management, backups, and handling relational database operational issues. Within the **Window Functions** chapter, this lesson focuses on `WINDOW` syntax, name scoping, and reusing window definitions across multiple analytical functions.

## 1. What problem do named windows solve?

Suppose you need to number employees, rank salaries, and calculate running salary totals within each department. The functions share partitioning by department, yet require different orderings: ranking orders only by salary to preserve ties; row numbering and running totals need an added unique key for deterministic per-row order:

```sql
SELECT
    employee_id,
    department_id,
    salary,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    ) AS row_num,
    RANK() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC
    ) AS salary_rank,
    SUM(salary) OVER (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_salary
FROM employees;
```

The two sort rules look similar but serve different purposes. `RANK()` sorts solely by salary so employees with equal salaries tie. `ROW_NUMBER()` and the running total append `employee_id` to establish deterministic per-row ordering. Including `employee_id` in `RANK()`'s window would prevent rows with equal salaries from being peer rows.

Named windows let you name both rules and reuse each in the right place:

```sql
SELECT
    employee_id,
    department_id,
    salary,
    ROW_NUMBER() OVER w_department_salary_row AS row_num,
    RANK() OVER w_department_salary_rank AS salary_rank,
    SUM(salary) OVER (
        w_department_salary_row
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_salary
FROM employees
WINDOW
    w_department_salary_rank AS (
        PARTITION BY department_id
        ORDER BY salary DESC
    ),
    w_department_salary_row AS (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    );
```

`w_department_salary_rank` keeps rows with equal salaries at the same rank. `w_department_salary_row` adds a unique key to determine row order for `ROW_NUMBER()` and the `ROWS` frame of the running total. Share a single named window only when the functions genuinely require identical partition, order, and peer-row semantics.

## 2. Syntax and placement of the WINDOW clause

General syntax in a `SELECT` statement:

```sql
SELECT
    select_list
FROM table_references
WHERE where_condition
GROUP BY group_list
HAVING having_condition
WINDOW
    window_name_1 AS (window_specification_1),
    window_name_2 AS (window_specification_2)
ORDER BY order_list
LIMIT row_count;
```

The `WINDOW` clause sits after `HAVING` and before `ORDER BY`. Unused clauses may be omitted, but the syntactic order must be preserved.

A window definition takes the form:

```sql
WINDOW window_name AS (
    [PARTITION BY partition_expression [, ...]]
    [ORDER BY order_expression [ASC | DESC] [, ...]]
    [frame_clause]
)
```

Example:

```sql
SELECT
    customer_id,
    order_id,
    order_date,
    total_amount,
    ROW_NUMBER() OVER w_customer_date AS order_sequence
FROM orders
WINDOW w_customer_date AS (
    PARTITION BY customer_id
    ORDER BY order_date, order_id
);
```

The name `w_customer_date` is referenced with `OVER w_customer_date`. It is a window definition name, not a table alias from `FROM`.

## 3. Scope of window names

A named window is valid only within the query block that declares `WINDOW`. It can be referenced by window expressions in the select list and other places in that query block where window functions are permitted.

```sql
SELECT
    employee_id,
    ROW_NUMBER() OVER w AS row_num
FROM employees
WINDOW w AS (PARTITION BY department_id ORDER BY employee_id);
```

Once the statement finishes, the name `w` ceases to exist. A subsequent standalone statement cannot reference it:

```sql
-- Error: w is not declared in this query block.
SELECT employee_id, ROW_NUMBER() OVER w
FROM employees;
```

### 3.1. Each query block has its own WINDOW clause

CTEs, derived tables, and subqueries form their own query blocks. If a window function is evaluated inside a CTE, the window name must be declared inside that CTE's `SELECT`:

```sql
WITH ranked_employees AS (
    SELECT
        employee_id,
        department_id,
        salary,
        ROW_NUMBER() OVER w_dept_salary AS row_num
    FROM employees
    WINDOW w_dept_salary AS (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    )
)
SELECT employee_id, department_id, salary, row_num
FROM ranked_employees
WHERE row_num <= 3;
```

The outer query reads the `row_num` column produced by the CTE. It cannot see `w_dept_salary` inside the CTE and cannot write `OVER w_dept_salary` unless another named window is declared in the outer query block.

Similarly, a subquery can define its own window names. Those names do not automatically propagate out to the enclosing query block.

### 3.2. The same name can be reused independently in another query block

Two different query blocks can both declare a window named `w` without sharing a definition. Each name is resolved within its own query block.

```sql
WITH per_department AS (
    SELECT
        employee_id,
        department_id,
        ROW_NUMBER() OVER w AS department_row
    FROM employees
    WINDOW w AS (
        PARTITION BY department_id
        ORDER BY employee_id
    )
)
SELECT
    employee_id,
    department_id,
    RANK() OVER w AS global_rank
FROM per_department
WINDOW w AS (ORDER BY employee_id);
```

The CTE has its own `w` for numbering within each department. The outer query also defines `w`, sorting the entire result by `employee_id`. The two definitions are completely unrelated.

## 4. Reusing a definition across multiple window functions

Named windows shine when multiple functions reuse one or more partition/order rules:

```sql
SELECT
    order_id,
    customer_id,
    order_date,
    total_amount,
    ROW_NUMBER() OVER w_customer_sequence AS row_num,
    RANK() OVER w_customer_date AS date_rank,
    DENSE_RANK() OVER w_customer_date AS dense_date_rank,
    LAG(total_amount) OVER w_customer_sequence AS previous_amount,
    LEAD(total_amount) OVER w_customer_sequence AS next_amount
FROM orders
WINDOW
    w_customer_date AS (
        PARTITION BY customer_id
        ORDER BY order_date
    ),
    w_customer_sequence AS (
        PARTITION BY customer_id
        ORDER BY order_date, order_id
    );
```

The functions intentionally use two distinct orderings within each customer:

- `RANK()` and `DENSE_RANK()` order only by `order_date`, so same-day orders tie.
- `ROW_NUMBER()` assigns a distinct sequence number to each row by `order_date, order_id`.
- `LAG()` reads the previous row's value and `LEAD()` reads the next row's value along the deterministic order with tie-breaker.

Named windows let functions with matching rules share one definition. When peer-row semantics differ, create separate definitions instead of forcing every function into one ordering.

## 5. Declaring multiple named windows in one WINDOW clause

A query block can define multiple windows separated by commas:

```sql
SELECT
    employee_id,
    department_id,
    salary,
    hired_at,
    ROW_NUMBER() OVER w_department AS department_sequence,
    RANK() OVER w_salary AS salary_rank,
    ROW_NUMBER() OVER w_hire_date AS hire_sequence
FROM employees
WINDOW
    w_department AS (
        PARTITION BY department_id
    ),
    w_salary AS (
        PARTITION BY department_id
        ORDER BY salary DESC
    ),
    w_hire_date AS (
        PARTITION BY department_id
        ORDER BY hired_at, employee_id
    );
```

The three definitions serve three analytical perspectives:

- `w_department`: partitions by department only, with no ordering specified.
- `w_salary`: ranks by descending salary within each department.
- `w_hire_date`: orders by hire date within each department.

Do not force all functions onto a single named window when analytical needs differ. Create distinct names that clearly reflect differences in partition, order, or frame.

## 6. Inheriting window definitions

MySQL allows a named window to reference a previously declared named window. This lets you create a base definition and extend it with the remaining clauses.

For example, create a base window containing only the partition, then add ordering:

```sql
SELECT
    employee_id,
    department_id,
    salary,
    ROW_NUMBER() OVER w_department_salary AS salary_sequence,
    COUNT(*) OVER w_department AS department_size
FROM employees
WINDOW
    w_department AS (
        PARTITION BY department_id
    ),
    w_department_salary AS (
        w_department
        ORDER BY salary DESC, employee_id
    );
```

`w_department_salary` inherits `PARTITION BY department_id` from `w_department` and appends `ORDER BY`. A later window may only reference a named window already defined earlier in the same `WINDOW` clause.

### 6.1. Inheritance rules

When a new definition references another named window:

- The referenced window must be declared earlier in the `WINDOW` clause.
- You cannot redeclare or override a component already present in the base window.
- If the base window already has `PARTITION BY`, the child window cannot add another `PARTITION BY`.
- If the base window already has `ORDER BY`, the child window cannot replace it with another `ORDER BY`.
- A frame should be declared at one appropriate level only; do not specify a frame twice across an inheritance chain.

A clean inheritance pattern is: base window declares `PARTITION BY`; child window adds `ORDER BY`; specific function calls add a frame if needed.

### 6.2. Invalid forward references

The following example is invalid because `w_department` references `w_base`, which is declared afterward:

```sql
SELECT employee_id, ROW_NUMBER() OVER w_department
FROM employees
WINDOW
    w_department AS (w_base ORDER BY employee_id),
    w_base AS (PARTITION BY department_id);
```

Swap the declaration order:

```sql
SELECT employee_id, ROW_NUMBER() OVER w_department
FROM employees
WINDOW
    w_base AS (PARTITION BY department_id),
    w_department AS (w_base ORDER BY employee_id);
```

Treat window definitions in dependency order like a directed list: base definitions first, extended definitions afterward.

## 7. Adding a frame when using a named window

A named window can define `PARTITION BY` and `ORDER BY`, and an aggregate function can append a frame when referencing it:

```sql
SELECT
    employee_id,
    department_id,
    salary,
    SUM(salary) OVER (
        w_department_salary
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_salary
FROM employees
WINDOW w_department_salary AS (
    PARTITION BY department_id
    ORDER BY salary, employee_id
);
```

The frame specifies the subset of rows inside the partition evaluated at the current position. In this example, the sum runs from the department's first row to the current row ordered by salary and employee ID.

### 7.1. ROWS and RANGE

MySQL supports `ROWS` and `RANGE` frames:

- `ROWS` defines scope by physical row count before/after the current position in window order.
- `RANGE` defines scope by the value of the `ORDER BY` expression; equal-value rows can belong to the same frame.

Example of a row-based cumulative frame:

```sql
SUM(total_amount) OVER (
    w_customer_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Example of a value-range cumulative frame with `RANGE`:

```sql
SUM(total_amount) OVER (
    w_customer_date
    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

If multiple rows share the same `ORDER BY` value, `RANGE` includes all peer rows in the current frame, whereas `ROWS` steps row by row in sequence. If deterministic per-row results are needed, use `ROWS` and add a unique tie-breaker to `ORDER BY`.

### 7.2. Default frames can alter results unexpectedly

For aggregate window functions, when `ORDER BY` is present without an explicit frame, MySQL defaults to a frame equivalent to:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

When `ORDER BY` is absent, the default frame spans the entire partition. Consequently, the two expressions below do not necessarily mean the same thing:

```sql
SUM(total_amount) OVER w_customer_date
```

```sql
SUM(total_amount) OVER (
    w_customer_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
```

The first expression is a running total under the default frame with `ORDER BY`; the second expression is the full-partition total on every row. When business rules require a group-wide total, either omit `ORDER BY` in the definition used for the group total or declare the full-partition frame explicitly.

### 7.3. LAST_VALUE and full-partition frames

`LAST_VALUE()` returns the value from the last row of the current frame, not automatically the last row of the entire partition. If you want the final chronological value for each customer, extend the frame to the end of the partition:

```sql
SELECT
    order_id,
    customer_id,
    order_date,
    total_amount,
    LAST_VALUE(total_amount) OVER (
        w_customer_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS final_order_amount
FROM orders
WINDOW w_customer_date AS (
    PARTITION BY customer_id
    ORDER BY order_date, order_id
);
```

Here, `order_id` breaks ties when multiple orders share the same date. The frame extends to `UNBOUNDED FOLLOWING` so the last row is the end of the entire partition.

## 8. ORDER BY inside a named window vs. final query ORDER BY

`ORDER BY` inside a window definition defines the order used to compute window functions. It does not guarantee the order of rows returned to the client.

```sql
SELECT
    employee_id,
    department_id,
    salary,
    ROW_NUMBER() OVER w_salary AS salary_sequence
FROM employees
WINDOW w_salary AS (
    PARTITION BY department_id
    ORDER BY salary DESC, employee_id
)
ORDER BY employee_id;
```

`ROW_NUMBER()` numbers rows by descending salary within each department, while the final output is sorted by `employee_id`. If display order must follow salary order, write `ORDER BY department_id, salary DESC, employee_id` at the end of the statement.

Never omit the final `ORDER BY` when the application requires deterministic ordering, especially for pagination.

## 9. Named windows and GROUP BY

Window functions operate on the rows of the query result after the filtering and grouping stages of the query block. `GROUP BY` collapses rows to one row per group; window functions compute values across those remaining rows without collapsing them further.

Example totaling revenue per customer, then ranking customers:

```sql
WITH customer_totals AS (
    SELECT
        customer_id,
        SUM(total_amount) AS revenue
    FROM orders
    GROUP BY customer_id
)
SELECT
    customer_id,
    revenue,
    RANK() OVER w_revenue AS revenue_rank
FROM customer_totals
WINDOW w_revenue AS (ORDER BY revenue DESC);
```

The `customer_totals` CTE produces one row per customer. The named window `w_revenue` ranks those aggregated rows. These are two steps with different grains: the aggregate produces a per-customer result set, and the window function analyzes rankings over that result set.

## 10. Cannot use a named window directly in WHERE

Window functions are evaluated after the `WHERE` stage of the same query block. Therefore, you cannot filter directly on a window function alias in `WHERE` at the same level:

```sql
-- Invalid: WHERE cannot filter window function results in the same query block.
SELECT
    employee_id,
    ROW_NUMBER() OVER w_salary AS row_num
FROM employees
WHERE row_num <= 3
WINDOW w_salary AS (
    PARTITION BY department_id
    ORDER BY salary DESC, employee_id
);
```

Move the window calculation into a CTE or derived table and filter in the outer query block:

```sql
WITH ranked_employees AS (
    SELECT
        employee_id,
        department_id,
        salary,
        ROW_NUMBER() OVER w_salary AS row_num
    FROM employees
    WINDOW w_salary AS (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    )
)
SELECT employee_id, department_id, salary, row_num
FROM ranked_employees
WHERE row_num <= 3
ORDER BY department_id, row_num;
```

The named window is scoped strictly inside the CTE. The outer query uses the `row_num` column rather than referencing `w_salary` from inside the CTE.

## 11. When to use one window, multiple windows, or inheritance?

| Scenario | Organization approach |
|---|---|
| Multiple functions share partition/order | One shared named window. |
| Same partition but different ordering | Multiple separate named windows. |
| Same partition, some functions ordered and others not | Base window with partition; child windows add ordering. |
| Same partition/order but different frames | Use base named window and append frame at each `OVER (...)`, or declare separate definitions if clearer. |
| Only one simple window function | Writing `OVER (...)` inline may be shorter and easier to read. |
| Need the definition in another statement | Redeclare in the new query block; named windows do not persist across statements. |

Named windows help when they clarify a shared rule. Creating too many names where each name is used only once without improving readability can make the query harder to follow.

## 12. Complete reporting example: employee analysis by department

Requirement: for each employee, display salary, rank within the department, sequence number by hire date, running salary total in salary order, and the highest salary in the department.

```sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    hired_at,
    RANK() OVER w_salary_rank AS salary_rank,
    ROW_NUMBER() OVER w_hire AS hire_sequence,
    SUM(salary) OVER (
        w_salary_sequence
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_salary,
    MAX(salary) OVER w_department AS department_max_salary
FROM employees
WINDOW
    w_department AS (
        PARTITION BY department_id
    ),
    w_salary_rank AS (
        w_department
        ORDER BY salary DESC
    ),
    w_salary_sequence AS (
        w_department
        ORDER BY salary DESC, employee_id
    ),
    w_hire AS (
        w_department
        ORDER BY hired_at, employee_id
    )
ORDER BY department_id, salary DESC, employee_id;
```

The query uses four named windows:

- `w_department` is the base definition, partitioning employees by department.
- `w_salary_rank` inherits the partition and orders by descending salary; employees with equal salaries tie.
- `w_salary_sequence` inherits the partition and appends `employee_id` to establish per-row order for the running total.
- `w_hire` inherits the partition and adds hire date ordering.

Each function uses the definition matching its requirement. `MAX(salary) OVER w_department` has no `ORDER BY`, so every row receives the department's maximum salary. `SUM()` uses a `ROWS` frame from the start of the partition to the current row along `w_salary_sequence`.

If `department_id` can be `NULL`, all unassigned employees will fall into a single `NULL` partition. If business logic should treat that group differently, categorize it explicitly with an expression or filter it earlier in the query block.

## 13. MySQL version and support limits

Window functions and the named `WINDOW` clause are supported in MySQL 8.0+. MySQL 5.7 does not support this syntax; queries targeting MySQL 5.7 must be redesigned using subqueries, self-joins, or techniques compatible with that version.

Before deploying:

```sql
SELECT VERSION() AS mysql_version;
```

Do not check only the version on your development machine. Verify the server version that the application, staging, and production environments actually connect to.

## 14. Performance and EXPLAIN

Named windows provide SQL-level definition reuse, not a performance guarantee. Window functions may require sorting rows by partition and order. On large datasets, sorting or materialization can consume CPU, memory, and temporary storage.

Inspect the execution plan:

```sql
EXPLAIN
SELECT
    employee_id,
    department_id,
    salary,
    RANK() OVER w_salary_rank AS salary_rank,
    SUM(salary) OVER (
        w_salary_sequence
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_salary
FROM employees
WINDOW
    w_salary_rank AS (
        PARTITION BY department_id
        ORDER BY salary DESC
    ),
    w_salary_sequence AS (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    );
```

On MySQL 8.0.18 and later, `EXPLAIN ANALYZE` can report actual row counts and timings when executing a read query:

```sql
EXPLAIN ANALYZE
SELECT
    employee_id,
    department_id,
    salary,
    ROW_NUMBER() OVER w_salary AS row_num
FROM employees
WINDOW w_salary AS (
    PARTITION BY department_id
    ORDER BY salary DESC, employee_id
);
```

Key notes:

- An index whose column order aligns with `PARTITION BY` and `ORDER BY` can assist data access, though the optimizer cannot always eliminate the sort step.
- A composite index `(department_id, salary, employee_id)` is a candidate for the query above; consider sort direction, selectivity, and write workload.
- Multiple named windows with different orderings may require separate sort steps.
- Sharing a single named window does not guarantee MySQL performs only one physical sort.
- Filtering rows in `WHERE` before window evaluation reduces input size, but filter only when business logic permits.
- Do not exclude rows prior to the window if those rows must participate in ranking, running totals, or frames.

## 15. Common mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| `Unknown window 'w'` | Name undeclared or outside the query block | Declare `WINDOW w AS (...)` inside the exact SELECT. |
| CTE/subquery cannot see an outer window name | Named windows do not cross query block boundaries | Redeclare inside the query block that uses it. |
| Child window inherits a name declared later | Forward reference in the WINDOW clause | Place the base window before the child window. |
| Cannot add PARTITION/ORDER to inherited window | That component was already declared in the base window | Pick a suitable base window or create a separate definition. |
| Two functions give different results despite seeming to share order | One function uses a different definition or frame | Share a named window and inspect each function's frame. |
| Running total jumps across tied-value groups | Default RANGE frame groups peer rows | Use `ROWS` with a tie-breaker if row-by-row stepping is needed. |
| LAST_VALUE returns current value instead of partition end | Default frame ends at current row | Extend frame to `UNBOUNDED FOLLOWING`. |
| Display order does not match window order | Confused ORDER BY in OVER with outer ORDER BY | Add ORDER BY at the end of SELECT. |
| WHERE cannot filter by row_number | Window functions do not exist at WHERE stage | Compute in a CTE/derived table, then filter in outer query. |
| Query remains slow despite using a named window | Named windows only reuse logical definitions | Check sorts, row counts, indexes, and EXPLAIN. |

## 16. Workflow for designing a WINDOW clause

1. **Determine input row grain.** Window functions analyze existing rows; confirm whether the query already filters or aggregates beforehand.
2. **Define partitions.** Which rows belong in the same analytical group?
3. **Define ordering.** Which order governs rank, lag/lead, or running totals?
4. **Add a tie-breaker.** When unique ordering is needed, append a unique key such as the primary key.
5. **Define frames.** Does the function need the full partition, a row-by-row running window, or a value range?
6. **Create base named windows.** Name partition/order combinations shared by multiple functions.
7. **Create inherited windows if needed.** Declare base windows first and append only missing components.
8. **Use OVER consistently.** Reference named windows for functions sharing identical rules.
9. **Verify scoping.** If moving calculations into a CTE/subquery, declare the window in that query block.
10. **Sort final output.** Add an outer ORDER BY if the client needs a specific display order.
11. **Inspect performance.** Use EXPLAIN/EXPLAIN ANALYZE and evaluate indexes, sorts, and row counts.

## 17. Practice exercises

### Exercise 1: Reusing a named window

Write a query that numbers and ranks orders per customer; define separate orderings for per-row numbering and date-based ranking.

**Requirement:** use `w_customer_sequence` for `ROW_NUMBER()`, `LAG()`, and `LEAD()` ordered by `order_date, order_id`; use `w_customer_date` for `RANK()` when same-day orders should tie. Explain why the two sets of functions require two different definitions.

### Exercise 2: Declaring multiple named windows

On the employees table, create windows `w_department`, `w_salary`, and `w_hire`.

**Requirement:** use `PARTITION BY department_id` for all three, with distinct orderings on the latter two windows.

### Exercise 3: Inheriting definitions

Create a base window containing only `PARTITION BY`, then declare child windows that add `ORDER BY`.

**Requirement:** try reversing the declaration order to observe the forward-reference error; try overriding an already-declared PARTITION BY and explain why it is invalid.

### Exercise 4: Cumulative frames

Use a named window with partition/order and compute `SUM()` with `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`.

**Requirement:** create two rows sharing the same sort value and compare `ROWS` vs. `RANGE`.

### Exercise 5: LAST_VALUE

Find each customer's final order amount using `LAST_VALUE()`.

**Requirement:** run with the default frame, then extend the frame to `UNBOUNDED FOLLOWING`; explain the difference.

### Exercise 6: Scope inside a CTE

Place `ROW_NUMBER() OVER w` inside a CTE and filter `row_num <= 3` in the outer query.

**Requirement:** try referencing `w` in the outer query without redeclaring it and explain the scoping error.

### Exercise 7: WINDOW and final ORDER BY

Rank employees by salary within each department while sorting final output by employee ID.

**Requirement:** explain why the ordering inside `OVER` does not dictate display order.

### Exercise 8: EXPLAIN

Write a query using two named windows with different orderings and run `EXPLAIN`.

**Requirement:** observe any sort or temporary steps; explain why named windows do not guarantee a single sort pass.

## 18. Review checklist

- [ ] Named windows are declared in the correct query block.
- [ ] `WINDOW` appears after HAVING and before ORDER BY.
- [ ] Window names are meaningful and not confused with table/CTE aliases.
- [ ] Functions sharing partition/order reference the same definition.
- [ ] Multiple named windows are separated by commas.
- [ ] Inherited windows only reference previously declared definitions.
- [ ] Existing PARTITION BY/ORDER BY from base windows are not overridden.
- [ ] Frames are specified explicitly when aggregates require specific semantics.
- [ ] ROWS and RANGE are chosen according to peer-row handling needs.
- [ ] Tie-breakers are present when unique row ordering is required.
- [ ] ORDER BY inside OVER is not confused with final query ORDER BY.
- [ ] Window functions are filtered in an outer query block via CTE/derived table when needed.
- [ ] Named windows are not expected to persist across statements or query blocks.
- [ ] Checked MySQL version and execution plan via EXPLAIN.

## 19. Takeaways

The `WINDOW` clause lets you name a window definition and reuse it with `OVER window_name`. It sits after `HAVING` and before `ORDER BY`; window names are scoped strictly to the query block where they are declared. A query block can define multiple named windows, and one definition can inherit from a window declared earlier.

Use base windows for `PARTITION BY`, child windows to add `ORDER BY`, and append frames where functions require them. Never override components already present in an inherited window. Named windows make SQL consistent, yet they are not a cache and do not guarantee a single physical sort. Always distinguish ordering inside `OVER` from final result ordering, pick the right frame, and verify execution plans on your target MySQL version.
