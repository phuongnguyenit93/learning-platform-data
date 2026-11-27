# ANSI JOIN and Legacy Oracle (+) Syntax

In Oracle Database, a query can combine data from multiple tables using JOIN syntax. Modern SQL code typically uses **ANSI JOIN** with the keywords `INNER JOIN`, `LEFT OUTER JOIN`, `RIGHT OUTER JOIN`, and `FULL OUTER JOIN`. In many long-standing Oracle systems, you will still encounter Oracle's proprietary syntax using `(+)` in the `WHERE` clause to express outer joins.

Both styles can express many of the same joins, but you should not read `(+)` as an arithmetic operator or an arbitrary symbol. It indicates **which table is the optional side** in a legacy outer join. When maintaining or migrating legacy code, you must preserve the right kept side, place filter predicates in the right clause, and check post-JOIN row counts.

This lesson moves from basic ANSI syntax to reading and converting `(+)`, distinguishing `ON` from `WHERE`, handling multiple conditions, self joins, anti-joins, full outer joins, and pitfalls that drop rows or duplicate data.

## 1. What Problem Does JOIN Solve?

A relational database typically splits information across multiple tables. For example:

- `DEPARTMENTS` stores departments.
- `EMPLOYEES` stores employees and their department IDs.
- `LOCATIONS` stores department locations.

To display department names alongside employee names, pair rows from both tables using the linking key:

~~~sql
SELECT d.department_name,
       e.employee_name
FROM departments d
JOIN employees e
  ON e.department_id = d.department_id;
~~~

`ON` specifies the matching condition. Each result row represents one pair of rows satisfying the condition. If a department has multiple employees, the department name appears multiple times — that is the correct outcome of a one-to-many relationship.

~~~mermaid
erDiagram
    DEPARTMENTS ||--o{ EMPLOYEES : "department_id"
    DEPARTMENTS ||--o{ LOCATIONS : "location_id"
    DEPARTMENTS {
        number department_id PK
        varchar department_name
        number location_id FK
    }
    EMPLOYEES {
        number employee_id PK
        varchar employee_name
        number department_id FK
    }
    LOCATIONS {
        number location_id PK
        varchar city
    }
~~~

JOIN does not automatically know the business relationship between two tables. The author must specify the proper keys and conditions. Joining on the wrong columns or omitting a condition can produce a Cartesian product, explode row counts, or multiply monetary totals.

## 2. JOIN Types in ANSI SQL

| JOIN Type | Rows Preserved | When No Match Exists on the Other Side |
|---|---|---|
| `INNER JOIN` | Only pairs of rows satisfying the condition | Unmatched rows are excluded |
| `LEFT OUTER JOIN` | All rows from the left table, plus matching right rows | Right-table columns are filled with `NULL` |
| `RIGHT OUTER JOIN` | All rows from the right table, plus matching left rows | Left-table columns are filled with `NULL` |
| `FULL OUTER JOIN` | All rows from both sides | The side without a partner is filled with `NULL` |
| `CROSS JOIN` | Every combination of left rows × right rows | No matching condition needed |

"Left" and "right" are based on table position in `FROM ... JOIN ...`, not on schema names or which table is more important.

### 2.1 INNER JOIN

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_id,
       e.employee_name
FROM departments d
INNER JOIN employees e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
~~~

`INNER` can be shortened to `JOIN`. Only departments with matching employees appear; employees with a NULL `DEPARTMENT_ID` or a non-matching code do not appear in this result either.

### 2.2 LEFT OUTER JOIN

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_id,
       e.employee_name
FROM departments d
LEFT OUTER JOIN employees e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
~~~

The result keeps **every department**. If a department has no employees yet, the `E.*` columns return `NULL`. The `OUTER` keyword is optional; `LEFT JOIN` has the exact same meaning.

### 2.3 RIGHT OUTER JOIN

~~~sql
SELECT d.department_name,
       e.employee_id,
       e.employee_name
FROM departments d
RIGHT OUTER JOIN employees e
    ON e.department_id = d.department_id;
~~~

This query keeps all employees, including those not assigned to a department or having an unmatched department code. It can be rewritten using `LEFT JOIN` by swapping the two tables' positions:

~~~sql
SELECT d.department_name,
       e.employee_id,
       e.employee_name
FROM employees e
LEFT JOIN departments d
    ON d.department_id = e.department_id;
~~~

Both queries are equivalent in row set if conditions and projections are preserved. In new code, many teams consistently choose `LEFT JOIN` because reading the preserved table on the left is easier.

### 2.4 FULL OUTER JOIN

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_id,
       e.employee_name
FROM departments d
FULL OUTER JOIN employees e
    ON e.department_id = d.department_id;
~~~

The result keeps:

- Departments with employees.
- Departments without employees.
- Employees with a matching department.
- Employees without a matching department.

In employee-only rows, department columns are `NULL`; in department-only rows, employee columns are `NULL`. If you need a single unified department ID from both sides for display, you can use `COALESCE(d.department_id, e.department_id)`.

### 2.5 CROSS JOIN

~~~sql
SELECT c.color_name,
       s.size_name
FROM colors c
CROSS JOIN sizes s;
~~~

If `COLORS` has 4 rows and `SIZES` has 3 rows, the result has 12 combinations. This is an intentional Cartesian product, often used to build combination matrices or reference sets. Do not add `CROSS JOIN` merely because you forgot the `ON` condition of a regular join.

## 3. ANSI JOIN: Placing Join Conditions in ON

ANSI JOIN cleanly separates three parts:

~~~sql
SELECT select_list
FROM main_table a
JOIN secondary_table b
  ON join_condition
WHERE filter_condition;
~~~

- `FROM`/`JOIN` expresses the tables and relationship type.
- `ON` describes how the two data sources pair up.
- `WHERE` filters the result according to query criteria.

Example:

~~~sql
SELECT d.department_name,
       e.employee_name
FROM departments d
JOIN employees e
  ON e.department_id = d.department_id
WHERE d.active_flag = 'Y';
~~~

Here the join condition is the department ID; the condition keeping only active departments is placed in `WHERE`.

### 3.1 Multi-table JOIN

~~~sql
SELECT d.department_name,
       e.employee_name,
       l.city
FROM departments d
JOIN employees e
  ON e.department_id = d.department_id
LEFT JOIN locations l
  ON l.location_id = d.location_id;
~~~

The query specifies:

1. Keep only employees with a matching department.
2. For each matched department, fetch the location if present; if absent, still keep the employee and return `NULL` for `CITY`.

Reading left to right reveals each combination step. For complex queries, use consistent aliases and put `ON` conditions on clear lines so maintainers can identify each column's table.

### 3.2 Join conditions with multiple columns

~~~sql
SELECT o.order_id,
       s.shipment_id
FROM orders o
JOIN shipments s
  ON s.order_id = o.order_id
 AND s.source_system = o.source_system;
~~~

If the logical key has two columns, join on both. Joining only on `ORDER_ID` can wrongly link data from another source system. An `ON` condition can include multiple expressions combined with `AND`/`OR`; use parentheses when controlling logical precedence.

### 3.3 JOIN on identically named columns using USING

When two tables share join column names, ANSI supports:

~~~sql
SELECT department_id,
       d.department_name,
       e.employee_name
FROM departments d
JOIN employees e
USING (department_id);
~~~

`USING` is concise when join column names match. The column named in `USING` is treated as a single coalesced join column in the output list; in some contexts, it cannot be referenced with an alias prefix. When you need multi-expression conditions, differing column names, or clearer control, use `ON`.

Avoid `NATURAL JOIN` in long-lived business code: Oracle automatically joins on **every identically named column** between the two tables. When the schema adds a column sharing a name, the query's meaning can silently change without the SQL changing. Explicit `ON` is easier to review and more stable.

## 4. Legacy Oracle Syntax: (+) in WHERE

Before ANSI JOIN became standard in Oracle, outer joins were commonly written using the proprietary `(+)` operator in the `WHERE` clause.

ANSI example:

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_id,
       e.employee_name
FROM departments d
LEFT OUTER JOIN employees e
    ON e.department_id = d.department_id;
~~~

Written in legacy Oracle syntax:

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_id,
       e.employee_name
FROM departments d,
     employees e
WHERE e.department_id(+) = d.department_id;
~~~

In this example:

- `DEPARTMENTS d` is the preserved side.
- `EMPLOYEES e` is the optional side, which may lack matching rows.
- `(+)` is placed next to the column of the optional table `e`.
- If a department has no employees, Oracle produces a result row with `e` columns set to `NULL`.

**Quick reading rule:** in `A.col = B.col(+)`, table `A` is preserved, while `B`'s rows are optional. This corresponds to `A LEFT OUTER JOIN B`.

### 4.1 (+) is not a "plus" sign

Do not read:

~~~sql
e.department_id(+) = d.department_id
~~~

as addition or a function. `(+)` is Oracle's legacy outer join notation appearing in `WHERE` comparison predicates. It marks the side that may lack data.

### 4.2 To preserve the right table, put (+) on the opposite side

ANSI:

~~~sql
SELECT d.department_name,
       e.employee_name
FROM departments d
RIGHT JOIN employees e
  ON e.department_id = d.department_id;
~~~

Legacy Oracle:

~~~sql
SELECT d.department_name,
       e.employee_name
FROM departments d,
     employees e
WHERE d.department_id(+) = e.department_id;
~~~

This time `EMPLOYEES` is preserved, while `DEPARTMENTS` is optional. The `(+)` marker is placed on the `d` column.

### 4.3 Legacy INNER JOIN needs no (+)

ANSI:

~~~sql
SELECT d.department_name,
       e.employee_name
FROM departments d
JOIN employees e
  ON e.department_id = d.department_id;
~~~

Legacy comma-join syntax:

~~~sql
SELECT d.department_name,
       e.employee_name
FROM departments d,
     employees e
WHERE e.department_id = d.department_id;
~~~

Without `(+)`, the equality condition is an inner join. The legacy style puts both join conditions and filter conditions together in `WHERE`; when queries have many tables, telling them apart is harder than in ANSI.

## 5. Crucial Rule: Conditions on the Optional Table Must Stay on the Right Side

This is the single biggest source of bugs when reading or migrating `(+)` syntax.

Suppose you want to keep all departments while matching only employees whose status is `ACTIVE`.

### 5.1 ANSI: optional-table condition placed in ON

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_name,
       e.status
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
 AND e.status = 'ACTIVE';
~~~

Meaning: for each department, find employees matching the ID **and** currently ACTIVE. If there are no ACTIVE employees, the department still appears with `e.*` columns equal to NULL.

### 5.2 Oracle (+): mark the optional side's condition too

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_name,
       e.status
FROM departments d,
     employees e
WHERE e.department_id(+) = d.department_id
  AND e.status(+) = 'ACTIVE';
~~~

The condition `e.status(+) = 'ACTIVE'` belongs to the outer join logic. It specifies that only ACTIVE employees match, while still preserving the department if no such employee is found.

### 5.3 What happens if (+) is omitted from the status condition?

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_name,
       e.status
FROM departments d,
     employees e
WHERE e.department_id(+) = d.department_id
  AND e.status = 'ACTIVE';
~~~

The condition `e.status = 'ACTIVE'` lacks `(+)`. For departments with no matching employee, `e.status` is NULL; the comparison does not evaluate to TRUE, so the department row is excluded. The result behaves like an inner join with respect to the status condition and **defeats the goal of keeping all departments**.

ANSI has the equivalent mistake if you place the condition in `WHERE`:

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_name
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE';
~~~

This is one of the most important takeaways:

| Condition | Meaning |
|---|---|
| `LEFT JOIN ... ON key AND e.status = 'ACTIVE'` | Keep all departments; match only ACTIVE employees |
| `LEFT JOIN ... ON key WHERE e.status = 'ACTIVE'` | Drop rows lacking an ACTIVE employee; usually produces an inner-join-like result for that condition |
| Legacy `e.key(+) = d.key AND e.status(+) = 'ACTIVE'` | Keep all departments; filter employees inside the outer join condition |
| Legacy `e.key(+) = d.key AND e.status = 'ACTIVE'` | Null-rejecting status condition drops departments with no matching employee |

**Clarify the business question:** do you want to filter source rows before pairing, or filter the result after pairing? With outer joins, these two are not equivalent.

## 6. Multiple Join Conditions Between the Same Two Tables

If an outer join relies on multiple conditions, `(+)` syntax must be applied consistently to all predicates involving the optional side.

ANSI:

~~~sql
SELECT o.order_id,
       s.shipment_id
FROM orders o
LEFT JOIN shipments s
  ON s.order_id = o.order_id
 AND s.source_system = o.source_system;
~~~

Legacy Oracle:

~~~sql
SELECT o.order_id,
       s.shipment_id
FROM orders o,
     shipments s
WHERE s.order_id(+) = o.order_id
  AND s.source_system(+) = o.source_system;
~~~

If you put `(+)` on one condition and forget it on the other, Oracle may not execute the outer join as intended and instead return only matched pairs. This is a subtle bug because the SQL still runs with no syntax error.

When migrating to ANSI, place all pairing conditions together in `ON`:

~~~sql
LEFT JOIN shipments s
  ON s.order_id = o.order_id
 AND s.source_system = o.source_system
 AND s.is_current = 'Y'
~~~

If `IS_CURRENT` is a criterion for the matched shipment row, it belongs in `ON`; if it filters the final result and accepting the loss of orders without a current shipment is intended, only then place it in `WHERE`.

## 7. Self Join: One Table Playing Two Roles

A self join joins a table to itself, commonly used for employee–manager hierarchies, parent–child categories, or replacement records.

ANSI:

~~~sql
SELECT e.employee_id,
       e.employee_name,
       m.employee_name AS manager_name
FROM employees e
LEFT JOIN employees m
  ON m.employee_id = e.manager_id;
~~~

Each alias represents one role:

- `e` is the employee.
- `m` is the manager.
- `LEFT JOIN` also preserves employees who have no manager yet.

Legacy Oracle syntax must also use separate aliases:

~~~sql
SELECT e.employee_id,
       e.employee_name,
       m.employee_name AS manager_name
FROM employees e,
     employees m
WHERE e.manager_id = m.employee_id(+);
~~~

You cannot omit aliases and use the same table name to distinguish two roles. In new code, ANSI is easier to read because each alias attaches directly to its `ON` condition.

## 8. FULL OUTER JOIN and Limitations of (+)

ANSI supports it directly:

~~~sql
SELECT COALESCE(a.business_key, b.business_key) AS business_key,
       a.value_a,
       b.value_b
FROM source_a a
FULL OUTER JOIN source_b b
  ON b.business_key = a.business_key;
~~~

The result keeps:

- Keys present in both sources.
- Keys present only in `SOURCE_A`.
- Keys present only in `SOURCE_B`.

Legacy Oracle `(+)` syntax **has no direct equivalent for a general FULL OUTER JOIN**. You cannot put `(+)` on both sides of the same condition to form a full outer join.

When maintaining legacy code, the cleanest solution is ANSI `FULL OUTER JOIN` on any Oracle version that supports it. In environments or cases requiring emulation, you can combine two directional outer joins with `UNION ALL` while excluding the overlap, though you must design carefully to avoid duplicating rows:

~~~sql
-- Illustrates full outer join via two branches; prefer ANSI FULL OUTER JOIN.
SELECT a.business_key,
       a.value_a,
       b.value_b
FROM source_a a
LEFT JOIN source_b b
  ON b.business_key = a.business_key

UNION ALL

SELECT b.business_key,
       a.value_a,
       b.value_b
FROM source_b b
LEFT JOIN source_a a
  ON a.business_key = b.business_key
WHERE a.business_key IS NULL;
~~~

The condition `a.business_key IS NULL` in the second branch is safe for detecting "no row in A" only if `BUSINESS_KEY` in table A is **non-NULL whenever a row exists** (typically a primary key or NOT NULL unique key). If the key is composite or nullable, test another non-null identifying column for absence. Additionally, `UNION ALL` retains valid duplicate rows; if business logic requires deduplication, define specific keys and deduplication rules.

## 9. Anti-Join: Finding Rows Without a Partner

A common requirement is finding departments without employees. There are two ways to write this.

### 9.1 LEFT JOIN ... IS NULL

~~~sql
SELECT d.department_id,
       d.department_name
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
WHERE e.employee_id IS NULL;
~~~

`EMPLOYEE_ID` must be a non-NULL identifying column of an employee row (such as the primary key). With no matching employee, the `e` columns are NULL-extended and the department row is selected.

Do not check `e.some_nullable_column IS NULL` if that column can be NULL on an actually matched employee; otherwise you cannot distinguish "no matched row" from "matched row with a NULL data column."

### 9.2 NOT EXISTS

~~~sql
SELECT d.department_id,
       d.department_name
FROM departments d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

`NOT EXISTS` directly expresses "no matching employee exists." It is often easier to read when only an existence check is needed and no columns from the secondary table are required. The Oracle optimizer can transform it into an anti-join in the execution plan.

### 9.3 Using (+) syntax to find unmatched rows

Legacy Oracle code may write:

~~~sql
SELECT d.department_id,
       d.department_name
FROM departments d,
     employees e
WHERE e.department_id(+) = d.department_id
  AND e.employee_id IS NULL;
~~~

In this pattern, `EMPLOYEE_ID` is a non-null key of the employees table, and `IS NULL` identifies unmatched rows. When reading legacy code, verify that the checked column is a mandatory/non-NULL key. For new code, `NOT EXISTS` usually conveys the intent more clearly.

## 10. NULLs in JOIN Conditions

The condition:

~~~sql
ON a.customer_id = b.customer_id
~~~

does not treat `NULL` as equal to `NULL`. If both columns are NULL, the condition is not TRUE, so the two rows do not match. This is standard SQL logic, not an outer join bug.

If business logic wants to pair two NULL values as an "undetermined" group, write an explicit condition, for example:

~~~sql
ON a.customer_id = b.customer_id
OR (a.customer_id IS NULL AND b.customer_id IS NULL)
~~~

However, this can cross-match many NULL rows with each other, producing a huge and usually unwanted row count. It is better to use genuine non-NULL identifying keys or a well-defined surrogate code.

### 10.1 Be cautious with NVL in JOIN keys

Some legacy code writes:

~~~sql
ON NVL(a.customer_id, -1) = NVL(b.customer_id, -1)
~~~

This treats every NULL as the dummy code `-1`. If `-1` can also be a valid value or many rows are NULL, the result can produce many-to-many matches. Wrapping columns in functions can also interfere with standard index usage. Only apply this when the value domain and business rules guarantee the sentinel never collides; prefer non-NULL keys.

## 11. WHERE, ON, and Filtering Order in Outer Joins

With inner joins, table-related filter conditions can often move between `ON` and `WHERE` without changing the result set. With outer joins, condition placement can change the result.

Suppose we need every department and details of active employees:

~~~sql
-- Keep all departments; match only ACTIVE employees.
SELECT d.department_id,
       e.employee_id
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
 AND e.status = 'ACTIVE';
~~~

If written as:

~~~sql
-- Returns only departments with a matching ACTIVE employee.
SELECT d.department_id,
       e.employee_id
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE';
~~~

then rows with no employees have `e.status = NULL` and are dropped by `WHERE`. The result no longer preserves all departments.

A practical rule of thumb:

- `ON` describes **conditions for an optional-side row to be paired**.
- `WHERE` describes **conditions filtering the result after pairing**, including whether NULL-extended rows are intentionally rejected.

Do not mechanically copy every condition from a `(+)` query's `WHERE` clause into ANSI `WHERE`; conditions belonging to the pairing logic must move into `ON`.

## 12. Important Limitations of (+) Syntax

The `(+)` operator is legacy Oracle syntax with many restrictions. When maintaining it, check the Oracle documentation for your exact release; historical restrictions can vary by version.

Common rules to remember:

1. **Used in WHERE conditions**, never place `(+)` inside `FROM ... JOIN ... ON`.
2. **Never mix `(+)` and ANSI JOIN syntax in the same query block.** Oracle may raise `ORA-25156: old style outer join (+) cannot be used with ANSI joins`.
3. If a pair of tables has multiple outer join conditions, mark the optional side consistently across the relevant conditions. Omitting `(+)` on one condition can break the expected outer join behavior.
4. Restrictions apply when combining `(+)` with `OR`, `IN`, subqueries, or complex expressions; many cases must be rewritten with ANSI JOIN/EXISTS.
5. A self join requires distinct aliases for the two roles of the same table.
6. `(+)` cannot directly express `FULL OUTER JOIN`.
7. Multi-table outer join restrictions historically depended on release; do not rely on a complex legacy query without verifying your version.

Example of an invalid/unsupported mixed syntax under legacy rules:

~~~sql
-- Never mix syntax like this within the same query block:
SELECT *
FROM departments d
JOIN locations l
  ON l.location_id = d.location_id,
     employees e
WHERE e.department_id(+) = d.department_id;
~~~

Rewrite completely in ANSI:

~~~sql
SELECT d.department_name,
       l.city,
       e.employee_name
FROM departments d
JOIN locations l
  ON l.location_id = d.location_id
LEFT JOIN employees e
  ON e.department_id = d.department_id;
~~~

### 12.1 Do not arbitrarily put (+) into OR conditions

Queries such as:

~~~sql
-- Problematic legacy pattern under (+) restrictions:
WHERE e.department_id(+) = d.department_id
  AND (e.status(+) = 'ACTIVE' OR d.include_all = 'Y')
~~~

may be rejected or fail to express the intended logic. Migrate the conditions to ANSI, putting pairing criteria in `ON` and result filters in `WHERE` with clear parentheses. For complex existence logic, consider `EXISTS` or a classifying CTE before the JOIN.

### 12.2 Do not arbitrarily compare (+) columns against subqueries

Certain forms of comparing `(+)`-marked columns with subqueries are restricted. When encountering legacy code with subqueries in outer join conditions, do not try sprinkling `(+)` everywhere to force it to compile. Extracting the subquery into an inline view/CTE and using ANSI JOIN is usually much clearer and easier to control.

## 13. Migrating Legacy Code from (+) to ANSI JOIN

When refactoring, do not merely replace `(+)` with `LEFT JOIN`. Determine:

1. Which table is preserved?
2. Which table is the optional side?
3. Which conditions belong to the pairing relationship?
4. Which conditions are result filters?
5. Are any optional-side conditions being used to keep or reject NULL rows?
6. Does the JOIN change the grain/row count due to a one-to-many relationship?

### 13.1 Basic conversion rules

| Legacy Syntax | Equivalent ANSI |
|---|---|
| `FROM A a, B b WHERE a.id = b.id` | `FROM A a JOIN B b ON a.id = b.id` |
| `WHERE b.a_id(+) = a.id` | `FROM A a LEFT JOIN B b ON b.a_id = a.id` |
| `WHERE a.b_id(+) = b.id` | `FROM B b LEFT JOIN A a ON a.b_id = b.id` |
| `WHERE b.a_id(+) = a.id AND b.flag(+) = 'Y'` | `FROM A a LEFT JOIN B b ON b.a_id = a.id AND b.flag = 'Y'` |
| `WHERE b.a_id(+) = a.id AND a.active = 'Y'` | `FROM A a LEFT JOIN B b ON b.a_id = a.id WHERE a.active = 'Y'` |

### 13.2 Complete conversion example

Legacy code:

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_id,
       e.employee_name
FROM departments d,
     employees e
WHERE e.department_id(+) = d.department_id
  AND e.status(+) = 'ACTIVE'
  AND d.region_id = 'NORTH';
~~~

Read the intent:

- Keep departments in the NORTH region.
- For each department, match ACTIVE employees if any.
- Departments without ACTIVE employees still appear.

ANSI:

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_id,
       e.employee_name
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
 AND e.status = 'ACTIVE'
WHERE d.region_id = 'NORTH';
~~~

The optional side's status condition moves into `ON`; the preserved side's region condition stays in `WHERE`.

### 13.3 Avoid conversions that silently alter results

A legacy query:

~~~sql
SELECT d.department_id,
       e.employee_id
FROM departments d,
     employees e
WHERE e.department_id(+) = d.department_id
  AND e.status = 'ACTIVE';
~~~

is NOT equivalent to:

~~~sql
SELECT d.department_id,
       e.employee_id
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
 AND e.status = 'ACTIVE';
~~~

Because the legacy query has `e.status = 'ACTIVE'` without `(+)`, departments without ACTIVE employees were dropped. The second ANSI query preserves those departments. To preserve the exact legacy result, write:

~~~sql
SELECT d.department_id,
       e.employee_id
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE';
~~~

This is why you must translate **semantics**, not characters. If the legacy code's original intent really was to keep every department, the legacy query may have had a bug; fixing that bug must be confirmed against business requirements and verification data.

## 14. JOIN and Aggregates: Beware of Post-Join Row Counts

A JOIN can produce multiple rows for one entity. For example, a department has 5 employees; after joining, the department appears 5 times. Summing department budgets after the JOIN multiplies the total.

~~~sql
SELECT d.department_id,
       SUM(d.annual_budget) AS budget_after_join,
       COUNT(e.employee_id) AS employee_count
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
GROUP BY d.department_id;
~~~

If `ANNUAL_BUDGET` is a department-level figure, `SUM(d.annual_budget)` adds the budget repeatedly once per employee. For department-level data, you can use `MAX(d.annual_budget)`/`MIN` when guaranteed a single value per department, or aggregate the employees table separately before joining:

~~~sql
WITH employee_counts AS (
    SELECT department_id,
           COUNT(*) AS employee_count
    FROM employees
    GROUP BY department_id
)
SELECT d.department_id,
       d.annual_budget,
       NVL(ec.employee_count, 0) AS employee_count
FROM departments d
LEFT JOIN employee_counts ec
  ON ec.department_id = d.department_id;
~~~

### 14.1 COUNT(*) vs COUNT(optional-side column)

~~~sql
SELECT d.department_id,
       COUNT(*) AS joined_row_count,
       COUNT(e.employee_id) AS matched_employee_count
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
GROUP BY d.department_id;
~~~

For a department without employees:

- `COUNT(*)` is 1 because LEFT JOIN still creates a NULL-extended row for the department.
- `COUNT(e.employee_id)` is 0 because the employee key is NULL on the unmatched row.

To count employees, use a non-NULL identifying column on the employee side or `COUNT(CASE WHEN ... THEN 1 END)`.

## 15. Three-Table Example Combining INNER and LEFT JOIN

Requirement: list employees who have a department; display the department's location if available; still keep the employee when the location is not specified.

~~~sql
SELECT e.employee_id,
       e.employee_name,
       d.department_name,
       l.city
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
LEFT JOIN locations l
  ON l.location_id = d.location_id
ORDER BY d.department_id, e.employee_id;
~~~

Step-by-step meaning:

1. `EMPLOYEES JOIN DEPARTMENTS`: keeps only employees with a valid department.
2. `LEFT JOIN LOCATIONS`: fetches the department's location without dropping employees if the location is missing.

Changing the first join to a `LEFT JOIN` from `EMPLOYEES` to `DEPARTMENTS` would also preserve employees without a department. Choose the join type based on row-preservation requirements, not habit.

## 16. Verifying Results During Migration or Maintenance

When migrating legacy code, compare **row sets and values**, not just whether the new SQL runs without error.

A practical verification process:

1. Pick a representative data slice containing both matched and unmatched cases.
2. Run the legacy query and the ANSI query on the same consistent snapshot/transaction.
3. Compare total row counts, unmatched row counts, and rows with NULL values on the optional side.
4. Compare by identifying keys, not merely total row counts.
5. Check aggregate metrics before and after JOIN to catch duplication.
6. Cross-check special `ON`/`WHERE` conditions, especially predicates on optional tables.

Example verification metrics:

~~~sql
-- Count total rows and rows without a matched employee.
SELECT COUNT(*) AS result_rows,
       COUNT(e.employee_id) AS matched_employees,
       COUNT(CASE WHEN e.employee_id IS NULL THEN 1 END)
           AS departments_without_employee
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id;
~~~

This is a quick check; if a department has multiple employees, `RESULT_ROWS` exceeds the number of departments. To count unique departments with/without employees, use `COUNT(DISTINCT d.department_id)` or pre-aggregate by department.

## 17. Common Errors and Misconceptions

| Error / Symptom | Cause | Resolution |
|---|---|---|
| `ORA-25156: old style outer join (+) cannot be used with ANSI joins` | Mixing `(+)` and ANSI syntax in the same query block | Convert the entire query block to ANSI or keep all legacy syntax until refactored |
| Departments without employees disappear | Predicate on `e.*` in `WHERE` is null-rejecting | Move pairing predicate to `ON` if departments must be kept |
| Outer join returns fewer rows than expected | Missing `(+)` on one condition or wrong optional side marked | Identify preserved/optional tables, mark consistently, or convert to ANSI |
| Total revenue increases after JOIN | One-to-many relationship duplicates parent-level rows | Identify grain, pre-aggregate details, or use a correctly leveled source |
| `COUNT(*)` is higher than employee count | LEFT JOIN keeps childless parent rows | Use `COUNT(e.primary_key)` to count child rows |
| Cannot use `(+)` for FULL OUTER JOIN | Legacy syntax cannot express full outer joins directly | Use ANSI `FULL OUTER JOIN` |
| Ambiguous column name in self join | Missing distinct aliases for each role | Use aliases such as `employee e` and `employee m` |
| Two NULL keys do not match | `NULL = NULL` is not TRUE | Check business rules; use non-NULL keys or a controlled explicit condition |
| `NOT IN`/`OR` combined with (+) fails | Limitations of legacy Oracle syntax | Rewrite with ANSI, `EXISTS`, or a CTE |
| LEFT JOIN becomes inner-like | Right-table condition placed in WHERE | Distinguish result filters from pairing conditions |
| Query runs but matches wrong rows | Missing part of a composite key or wrong column joined | Join all key components, verify cardinality and data |

## 18. Self-Check Exercises

Assume three tables:

~~~sql
-- Conceptual structure:
-- DEPARTMENTS(department_id, department_name, location_id)
-- EMPLOYEES(employee_id, employee_name, department_id, status, manager_id)
-- LOCATIONS(location_id, city)
~~~

### Exercise 1 — Converting INNER JOIN

Write an ANSI JOIN listing employees and department names. Rewrite the same query using legacy comma join and `WHERE` condition. Why do both queries return only rows with matching department keys?

### Exercise 2 — Converting LEFT JOIN to (+)

Write ANSI `DEPARTMENTS LEFT JOIN EMPLOYEES`. Then write the legacy syntax using `e.department_id(+) = d.department_id`. State which table is preserved and which columns become NULL when no employee exists.

### Exercise 3 — Predicate on the optional table

Requirement: keep all departments while matching only ACTIVE employees. Write both forms:

- ANSI: status in `ON`.
- Legacy Oracle: status in a condition with `(+)`.

Then move the status condition to `WHERE` and explain which departments disappear.

### Exercise 4 — RIGHT JOIN

Write a query preserving all employees even without a department. Implement one version with `RIGHT JOIN` and one version with `LEFT JOIN` swapping table order. Compare the row sets.

### Exercise 5 — FULL OUTER JOIN

Source A and Source B contain customer code lists from two systems. Write a `FULL OUTER JOIN` keeping codes present in either or both sources. Use `COALESCE` to display the unified key. Explain why `(+)` cannot replace this directly.

### Exercise 6 — Anti-join

Find departments without employees using `LEFT JOIN ... WHERE e.employee_id IS NULL` and `NOT EXISTS`. Why must you pick a non-NULL key column to check?

### Exercise 7 — NULL and JOIN

Two tables have NULL `CUSTOMER_ID`. Predict the result of `a.customer_id = b.customer_id`. If you pair NULL with NULL using a custom rule, what row-multiplication risks can occur?

### Exercise 8 — COUNT

A department has no employees yet. Compare `COUNT(*)` and `COUNT(e.employee_id)` in a LEFT JOIN. Which metric reflects the actual employee count?

### Exercise 9 — Grain and aggregation

A department has an annual budget of 1,000,000 and 4 employees. What does JOIN followed by `SUM(d.annual_budget)` return? Rewrite the query to return the budget once and an employee count of 4.

### Exercise 10 — Refactoring legacy code

Convert the following query to ANSI while preserving its meaning:

~~~sql
SELECT d.department_id,
       e.employee_id
FROM departments d,
     employees e
WHERE e.department_id(+) = d.department_id
  AND e.status(+) = 'ACTIVE'
  AND d.region_id = 'NORTH';
~~~

Then write a variant with `e.status = 'ACTIVE'` in `WHERE`. Explain the difference and pick the query matching the requirement to keep all NORTH departments.

## 19. Workflow for Reading and Migrating a Legacy (+) Query

When encountering a legacy query, follow this sequence:

~~~mermaid
flowchart TD
    A["Read FROM and aliases"] --> B["Find every condition with (+)"]
    B --> C["Identify tables without (+): preserved side"]
    C --> D["Identify all predicates on the optional side"]
    D --> E["Separate pairing predicates from filter predicates"]
    E --> F["Write ANSI JOIN with clear ON/WHERE"]
    F --> G["Verify matched, unmatched, and aggregated rows"]
    G --> H["Check plan and release change"]
~~~

Legacy syntax reading checklist:

- Which column has `(+)`? That table is the optional side in the outer join condition.
- Which table has no `(+)`? That table is preserved.
- Are there multiple pairing conditions? Mark the optional side consistently.
- Is there a predicate on the optional table without `(+)`? That predicate may drop NULL-extended rows.
- Are there `OR`, `IN`, subqueries, self joins, or many tables? Check legacy syntax limits and consider rewriting in ANSI.
- Is a FULL OUTER JOIN needed? Use ANSI.
- Does the JOIN duplicate parent-level rows? Check grain before aggregating.

## 20. Summary Notes

| Question | Rule |
|---|---|
| Where does ANSI JOIN place join conditions? | `ON` |
| Which rows does INNER JOIN keep? | Only matching row pairs |
| Which table does LEFT JOIN preserve? | All rows of the left table |
| Which table does RIGHT JOIN preserve? | All rows of the right table |
| What does FULL OUTER JOIN preserve? | All rows from both sides, paired when possible |
| What does `A.id = B.id(+)` mean? | A is preserved, B is the optional side |
| Where do optional-side predicates go in ANSI? | `ON` if you want to keep left rows lacking a predicate-matching partner |
| What can a predicate in WHERE do? | Drop NULL-extended rows and make an outer join behave inner-like |
| Can (+) and ANSI be mixed in the same query block? | No; may raise `ORA-25156` |
| Can (+) express FULL OUTER JOIN directly? | No |
| Counting child rows after LEFT JOIN? | `COUNT(child_primary_key)`, not always `COUNT(*)` |
| Is migrating legacy code just symbol replacement? | No; you must preserve kept side, predicates, and grain |

ANSI JOIN is the preferred syntax for new code because join types and pairing conditions are stated explicitly. You still need to read `(+)` syntax when maintaining legacy systems: it marks the **optional side**, and predicate placement dictates which rows survive. When refactoring, translate semantics accurately into `ON`/`WHERE`, and verify unmatched rows, NULLs, multi-column conditions, and post-JOIN row counts. That ensures the new query is both readable and faithful to the business result the legacy code truly requires.
