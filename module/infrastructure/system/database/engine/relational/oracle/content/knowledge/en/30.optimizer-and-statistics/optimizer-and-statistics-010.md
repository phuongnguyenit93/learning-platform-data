# Query Transformation: View Merging, Unnesting, and Predicate Pushing

The Oracle Cost-Based Optimizer (CBO) does not merely select indexes or join methods for a SQL statement strictly as written. Before generating an execution plan, the optimizer can transform the query structure into a semantically equivalent form that is easier to optimize. This family of operations is called **query transformation**.

Three key techniques are view merging, subquery unnesting, and predicate pushing. View merging pulls an inline view's query block into the outer query block so the optimizer sees multiple tables and join conditions together. Unnesting converts certain subqueries into joins or semi/anti joins. Predicate pushing moves filter conditions closer to the data source to reduce the number of rows processed in later steps.

Transformations are not always valid or beneficial. The optimizer must preserve SQL semantics—accounting for NULLs, aggregation, outer joins, DISTINCT, set operators, analytic functions, and other constraints—and then evaluate the cost of the alternatives. Understanding query transformations therefore helps you read execution plans, explain why a plan differs from how the SQL was written, and know when to test hints or rewrites.

After this lesson, you will be able to:

- Identify query blocks, inline views, subqueries, and views in execution plans.
- Explain simple view merging and complex view merging.
- Understand the conditions, benefits, and limitations of view merging.
- Distinguish view merging from materialization of a WITH clause.
- Understand subquery unnesting for IN, EXISTS, NOT IN, and NOT EXISTS.
- Recognize semi joins, anti joins, and null-aware anti joins.
- Explain predicate pushing, predicate pushdown, and join predicate pushdown.
- Distinguish predicates pushed into WHERE, HAVING, individual UNION ALL branches, or correlated views.
- Read plans to identify whether a transformation occurred.
- Use QB_NAME, MERGE, NO_MERGE, UNNEST, NO_UNNEST, PUSH_PRED, and related hints in a controlled manner.
- Diagnose cases where a transformation is invalid, not chosen, or makes a plan slower.

> Query transformations vary by release, optimizer_features_enable, statistics, constraints, bind values, and system configuration. Examples in this lesson illustrate principles; verify actual execution plans on your exact Oracle version and data.

## 1. Query Blocks and the Optimizer's Role

### 1.1. What Is a Query Block?

A query block is a SELECT unit within a SQL statement. A single SQL statement can contain multiple query blocks produced by inline views, subqueries, CTEs, or set operations.

Example:

```sql
SELECT e.employee_id, e.last_name
FROM employees e
WHERE e.department_id IN (
    SELECT d.department_id
    FROM departments d
    WHERE d.location_id = 1700
);
```

This SQL statement has an outer query block reading EMPLOYEES and a child query block reading DEPARTMENTS. The optimizer may keep the subquery separate, unnest it into a semi join, or apply other transformations if valid and beneficial.

Inline view example:

```sql
SELECT v.department_id, v.employee_count
FROM (
    SELECT department_id, COUNT(*) AS employee_count
    FROM employees
    GROUP BY department_id
) v
WHERE v.department_id = 50;
```

The SELECT inside parentheses is a separate query block, commonly called a view query block or inline view. The optimizer may keep it as a distinct block, push predicates inside, or apply complex view merging depending on conditions.

### 1.2. Where Does Query Transformation Happen?

At a high level, the CBO performs the following tasks:

1. Parses the SQL and builds an expression/query-block tree.
2. Checks semantics, object metadata, constraints, and privileges.
3. Considers valid transformations.
4. Generates access path, join order, join method, and other operation alternatives.
5. Estimates costs based on statistics, cardinality, and the cost model.
6. Selects the lowest-cost plan within the search space considered by the optimizer.

Internal ordering and the exact set of transformations can differ across releases. Do not treat this list as a rigid pipeline that every SQL statement traverses identically.

### 1.3. Transformations Must Preserve Semantics

Two SQL statements that appear equivalent in intent are not necessarily semantically equivalent. For example:

- NOT IN uses three-valued logic (TRUE/FALSE/UNKNOWN) when NULLs are present.
- Outer joins produce null-extended rows.
- GROUP BY changes the grain of the data.
- DISTINCT eliminates duplicates.
- ROWNUM and FETCH FIRST can depend on row order/boundaries.
- Analytic functions depend on row sets and window ordering.

The optimizer may only apply a transformation if it preserves results under SQL semantics. When rewriting manually, the developer is responsible for preserving these rules.

## 2. View Merging

### 2.1. Concept

View merging is a transformation that brings the query block of a view (inline view or referenced view) into the outer query block. After merging, the optimizer can optimize tables and conditions from both blocks as a single larger query block.

Before transformation:

```sql
SELECT e.employee_id, v.department_name
FROM employees e
JOIN (
    SELECT department_id, department_name
    FROM departments
    WHERE status = 'ACTIVE'
) v
  ON v.department_id = e.department_id
WHERE e.salary > 10000;
```

View V is simply a projection/filter on DEPARTMENTS. The optimizer can merge the view to see EMPLOYEES and DEPARTMENTS together with their conditions directly:

```sql
SELECT e.employee_id, d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE d.status = 'ACTIVE'
  AND e.salary > 10000;
```

This is a conceptual equivalent in a simple example. Not every inline view can be rewritten this way.

### 2.2. Why Is View Merging Useful?

If a view is not merged, the optimizer may have to optimize the view as a separate block and only then combine its results with the outer query. Once merged, the optimizer can:

- Consider join orders across tables inside the view and tables outside.
- Choose access paths using predicates from both sides.
- Push filters and join conditions deeper.
- Eliminate unnecessary projections or query layers.
- Exploit transitive predicates and other transformations.

The main benefit is expanding the plan search space. View merging does not automatically mean a faster query; the optimizer still must choose a good plan based on cost.

### 2.3. Simple View Merging

Simple view merging typically applies to views with a straightforward SELECT-PROJECT-JOIN (SPJ) structure—meaning primarily FROM, WHERE, and a SELECT expression list, without constructs that alter grain/results such as GROUP BY or DISTINCT.

Example:

```sql
SELECT *
FROM (
    SELECT employee_id, department_id, salary
    FROM employees
    WHERE salary > 5000
) v
WHERE v.department_id = 20;
```

The view only filters and projects columns. The optimizer can combine the predicates into:

```sql
SELECT employee_id, department_id, salary
FROM employees
WHERE salary > 5000
  AND department_id = 20;
```

Simple view merging is usually easy to apply because it does not have to handle aggregation boundaries or duplicate elimination.

### 2.4. Complex View Merging

Complex view merging handles certain views with more complex constructs, such as GROUP BY or DISTINCT. Merging must preserve aggregation/duplicate semantics and is evaluated by the optimizer for both validity and cost.

Aggregation view example:

```sql
SELECT d.department_name, v.total_salary
FROM departments d
JOIN (
    SELECT department_id, SUM(salary) AS total_salary
    FROM employees
    GROUP BY department_id
) v
  ON v.department_id = d.department_id
WHERE d.location_id = 1700;
```

The optimizer may consider complex view merging in supported cases. However, do not infer that every GROUP BY view can or should always be merged. Keeping the view separate to aggregate first and then join may have a lower cost or be required to preserve semantics.

### 2.5. GROUP BY and Semantic Boundaries

Suppose a view computes total salary by department. After GROUP BY, each department has at most one row. Merging or pushing predicates improperly could alter the input row set to aggregation or how sums are computed.

A predicate on the grouping key can often be pushed before GROUP BY because it selects groups by key. A predicate on an aggregate such as SUM(salary) > 100000 belongs to HAVING semantics; it cannot arbitrarily be turned into a WHERE filter on individual employees.

Example:

```sql
SELECT department_id, SUM(salary) AS total_salary
FROM employees
WHERE department_id = 50
GROUP BY department_id
HAVING SUM(salary) > 100000;
```

WHERE department_id = 50 filters rows before aggregation. HAVING filters groups after aggregation. These two positions cannot be swapped arbitrarily.

## 3. Conditions and Limitations of View Merging

### 3.1. Not Every View Can Be Merged

Transformations can be restricted by:

- GROUP BY, DISTINCT, and aggregates.
- Set operators such as UNION, UNION ALL, INTERSECT, and MINUS.
- CONNECT BY / hierarchical queries.
- The MODEL clause.
- Certain cases of ROWNUM, row limiting, and analytic functions.
- Outer joins and null-preserving relationships.
- Expressions or constructs where merging would alter semantics.
- Query blocks with special properties, such as certain remote objects or security barriers.

This list is not an absolute “keyword forbids merging” rule across all releases. Oracle can support certain complex transformations under specific conditions. Inspect plans and version documentation rather than relying on a rigid blacklist.

### 3.2. Views with DISTINCT

DISTINCT removes duplicates. If a view is merged into the outer query, the optimizer must preserve duplicate-elimination semantics. In some cases, complex view merging can do this; in others, the view is kept separate or another transformation is used.

Example:

```sql
SELECT c.customer_id
FROM customers c
JOIN (
    SELECT DISTINCT customer_id
    FROM orders
) o
  ON o.customer_id = c.customer_id;
```

The view produces a set of unique customer_ids. Removing DISTINCT without preserving semantics could multiply result rows because one customer can have many orders.

### 3.3. Views with Set Operators

Views using UNION ALL or UNION create a set-operation boundary. The optimizer may apply transformations such as pushing predicates into each branch, but that does not mean the entire view merges into a standard single query block.

```sql
SELECT *
FROM (
    SELECT customer_id, status FROM current_customers
    UNION ALL
    SELECT customer_id, status FROM archived_customers
) all_customers
WHERE status = 'ACTIVE';
```

The predicate status = 'ACTIVE' can be pushed into both branches if valid. This is predicate pushing across UNION ALL; distinguish it from view merging.

### 3.4. Outer Joins and Null-Preserving Semantics

An outer join retains rows from the preserved side even when the other side has no match. Moving a predicate from WHERE into ON or into a view can change whether unmatched rows are kept or discarded.

Example:

```sql
SELECT d.department_id, e.employee_id
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE';
```

The predicate e.status = 'ACTIVE' in WHERE eliminates rows where e is NULL, giving the query semantics close to an inner join for that predicate. Moving the predicate to ON:

```sql
SELECT d.department_id, e.employee_id
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
 AND e.status = 'ACTIVE';
```

keeps departments with no ACTIVE employees with NULL employee columns. The two queries are not equivalent. The optimizer must preserve this distinction when transforming.

### 3.5. ROWNUM, Row Limiting, and Analytic Functions

Row-limiting and ordering constructs can create semantic boundaries. For example, filtering outside an inline view containing ROWNUM is not necessarily equivalent to placing the predicate before ROWNUM is assigned.

Similarly, analytic functions compute over row sets and windows. Predicate pushdown/merging only applies when it does not alter the row set seen by the analytic function or when the optimizer has a semantics-preserving transformation.

Do not rewrite queries containing ROWNUM, FETCH FIRST, or analytic functions based solely on surface appearance. Check processing order and actual results.

## 4. MERGE and NO_MERGE Hints

### 4.1. MERGE Hint

The MERGE hint instructs the optimizer to consider merging a view:

```sql
SELECT /*+ MERGE(v) */
       e.employee_id, v.department_name
FROM employees e
JOIN (
    SELECT department_id, department_name
    FROM departments
    WHERE status = 'ACTIVE'
) v
  ON v.department_id = e.department_id;
```

The hint can be placed in the outer query block referencing the view alias or use query-block syntax depending on context. Verify exact hint syntax and applicability for your release.

### 4.2. NO_MERGE Hint

NO_MERGE instructs the optimizer to keep the view as a separate query block:

```sql
SELECT /*+ NO_MERGE(v) */
       e.employee_id, v.department_name
FROM employees e
JOIN (
    SELECT department_id, department_name
    FROM departments
    WHERE status = 'ACTIVE'
) v
  ON v.department_id = e.department_id;
```

This can be useful when preserving a view boundary to avoid a transformation that causes a poor plan, or when controlling query-block structure during testing. Do not use NO_MERGE as a default habit for optimizing queries.

### 4.3. Hints Do Not Replace Evidence

A hint can be ignored if the alias/query block is wrong, invalid for the SQL structure, conflicts with another hint, or the transformation cannot be performed. After adding a hint, inspect the execution plan and hint report (if supported by your release) to see whether the hint was used.

### 4.4. Query Block Naming

QB_NAME assigns a name to a query block for precise referencing:

```sql
SELECT /*+ QB_NAME(main_qb) */
       e.employee_id, v.department_name
FROM employees e
JOIN (
    SELECT /*+ QB_NAME(dept_v) */
           department_id, department_name
    FROM departments
    WHERE status = 'ACTIVE'
) v
  ON v.department_id = e.department_id;
```

Query block names reduce reliance on auto-generated aliases and make complex SQL with multiple subqueries/inline views easier to read. Syntax for referencing query blocks in hints depends on hint type and release.

## 5. Subquery Unnesting

### 5.1. Concept

Subquery unnesting is a transformation that converts a subquery into a join or equivalent relational structure inside the outer query block. The goal is to let the optimizer consider a broader range of join orders, join methods, and access paths.

IN subquery example:

```sql
SELECT e.employee_id, e.last_name
FROM employees e
WHERE e.department_id IN (
    SELECT d.department_id
    FROM departments d
    WHERE d.location_id = 1700
);
```

The optimizer can unnest this into a semi join between EMPLOYEES and DEPARTMENTS, instead of executing the subquery as a separate unit for each outer row.

### 5.2. Correlated Subqueries

A correlated subquery references columns from the outer query block:

```sql
SELECT e.employee_id, e.last_name
FROM employees e
WHERE EXISTS (
    SELECT 1
    FROM departments d
    WHERE d.department_id = e.department_id
      AND d.location_id = 1700
);
```

The subquery uses e.department_id from the outer query. Without unnesting, the subquery may be evaluated per outer row or handled via another mechanism. If unnested, the optimizer can convert it into a semi join.

### 5.3. Uncorrelated Subqueries

A subquery that does not reference the outer query:

```sql
SELECT employee_id, last_name
FROM employees
WHERE department_id IN (
    SELECT department_id
    FROM departments
    WHERE location_id = 1700
);
```

The subquery can be evaluated as an independent set of values, or the optimizer can transform it into a join. Correlation is not required for unnesting to occur.

### 5.4. Benefits

Unnesting can:

- Allow the optimizer to choose join order between outer and subquery tables.
- Use an appropriate hash join, nested loops, or merge join/semi join.
- Avoid repeated subquery evaluation for every outer row in certain cases.
- Combine predicates across multiple query blocks.
- Leverage indexes and statistics on the participating tables.

Unnesting is not always faster. If the subquery is very selective and the outer query has only a few rows, keeping the subquery or using nested loops may be cheaper.

## 6. Semi Joins and EXISTS/IN

### 6.1. Semi Join

A semi join returns a row from the outer side if at least one matching row exists on the inner side. It does not duplicate outer rows when the inner side has multiple matches.

Example:

```sql
SELECT c.customer_id, c.customer_name
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
```

Meaning: return every customer with at least one order. Even if a customer has 20 orders, the query still returns one customer row (unless the outer source itself has duplicates).

If written directly as an INNER JOIN:

```sql
SELECT c.customer_id, c.customer_name
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id;
```

A customer with multiple orders will appear multiple times. The two queries are not equivalent in cardinality without adding DISTINCT or aggregation. A semi join is the operation that matches EXISTS semantics.

### 6.2. IN Subqueries

IN checks whether an outer value belongs to the subquery's set of values:

```sql
SELECT employee_id
FROM employees
WHERE department_id IN (
    SELECT department_id
    FROM departments
    WHERE location_id = 1700
);
```

The optimizer can convert this into a semi join. Duplicate department_ids in the subquery do not cause outer rows to repeat, because IN only tests set membership.

### 6.3. EXISTS Subqueries

EXISTS only cares whether at least one row satisfies the condition:

```sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
);
```

SELECT 1 is just a placeholder expression; EXISTS does not need specific column values. The optimizer can stop searching once a match is found, depending on the plan.

### 6.4. Semi Joins in Execution Plans

In plans, you may see operations such as:

- NESTED LOOPS SEMI
- HASH JOIN SEMI
- MERGE JOIN SEMI

The operation name indicates the plan implements semi-join semantics. Not every EXISTS/IN appears as one of these exact operations; a plan may retain FILTER or use another structure depending on the query and release.

### 6.5. When Are Semi Joins Advantageous?

Semi joins fit when only checking existence and no columns from the inner table are needed. They avoid duplicating outer rows and generally allow the optimizer to pick access paths based on join conditions.

If columns from the inner table are needed, EXISTS cannot provide them; use a join or scalar subquery according to the desired semantics.

## 7. Anti Joins and NOT EXISTS/NOT IN

### 7.1. Anti Join

An anti join returns outer rows that have no matching row on the inner side. For example, customers who have never placed an order:

```sql
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
```

The optimizer can transform this into an anti join.

### 7.2. NOT EXISTS

NOT EXISTS checks that no row satisfies the correlated condition. If the subquery finds no rows, the predicate evaluates to TRUE.

Example:

```sql
SELECT p.product_id
FROM products p
WHERE NOT EXISTS (
    SELECT 1
    FROM order_items i
    WHERE i.product_id = p.product_id
);
```

If PRODUCT_ID in ORDER_ITEMS contains NULLs, equality does not match NULL with normal product_ids; a NULL on the inner side does not make NOT EXISTS evaluate to UNKNOWN the way NOT IN does. Therefore, NOT EXISTS is usually easier to reason about semantically when inner keys can be NULL.

### 7.3. NOT IN and NULLs

NOT IN follows three-valued logic. Example:

```sql
SELECT 10
FROM dual
WHERE 10 NOT IN (20, 30, NULL);
```

No rows are returned. Because the right-hand set includes NULL, the comparison is equivalent to:

```text
10 <> 20 AND 10 <> 30 AND 10 <> NULL
TRUE AND TRUE AND UNKNOWN = UNKNOWN
```

WHERE only keeps rows where the predicate is TRUE; UNKNOWN is discarded. This is why NOT IN can unexpectedly return zero rows if the subquery returns a NULL.

### 7.4. Comparing NOT IN and NOT EXISTS

```sql
-- May be affected by NULLs in the subquery:
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
);

-- Checks that no row matches by equality:
SELECT c.customer_id
FROM customers c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
```

If ORDERS.CUSTOMER_ID contains NULLs, the two queries can return different results. If c.customer_id is also NULL, NOT EXISTS with equality does not match NULL and can return the outer NULL row; decide from business requirements whether to keep that row.

### 7.5. Writing Safe NOT IN When the Inner Key Is Nullable

If business logic calls for NOT IN semantics while excluding NULLs from the inner set, filter explicitly:

```sql
SELECT c.customer_id
FROM customers c
WHERE c.customer_id NOT IN (
    SELECT o.customer_id
    FROM orders o
    WHERE o.customer_id IS NOT NULL
);
```

If the outer key can be NULL, explicitly decide whether to exclude it:

```sql
WHERE c.customer_id IS NOT NULL
  AND c.customer_id NOT IN (...)
```

Do not add IS NOT NULL out of habit if NULL carries distinct business meaning.

### 7.6. Null-Aware Anti Join

Oracle can use a null-aware anti join for certain NOT IN queries to preserve semantics when the inner expression may contain NULLs. In the execution plan, you may see operations such as HASH JOIN ANTI NA or HASH JOIN ANTI SNA (depending on release/plan notation).

A null-aware anti join is not a bug or a bad plan sign on its own. It reflects that the optimizer must handle NULLs accurately for NOT IN. If a NOT NULL constraint proves the inner expression cannot be NULL, the optimizer may gain additional transformation options.

## 8. Conditions and Limitations of Subquery Unnesting

### 8.1. Subqueries Cannot Always Be Unnested

Unnesting can be restricted by:

- Aggregates or GROUP BY inside the subquery.
- ROWNUM and certain row-limiting constructs.
- Set operators or complex query structures.
- Hierarchical queries.
- Analytic functions in contexts where semantics cannot be preserved.
- Certain subqueries containing outer joins or special expressions.
- Complex correlation, multiple query blocks, or references that cannot be decorrelated.
- Conditions that could alter results if converted into a join.

Oracle supports many conditional unnesting cases, including some aggregate/complex subqueries. Treat this as a set of factors to verify rather than an absolute prohibition list.

### 8.2. Aggregates in Correlated Subqueries

Example:

```sql
SELECT e.employee_id
FROM employees e
WHERE e.salary > (
    SELECT AVG(e2.salary)
    FROM employees e2
    WHERE e2.department_id = e.department_id
);
```

The subquery computes the department average for each employee. The optimizer may apply complex transformations such as aggregate decorrelation or keep the subquery depending on conditions/cost. You cannot directly replace it with a raw join on EMPLOYEES without risking row multiplication or wrong averages.

A manual rewrite can aggregate first and then join:

```sql
SELECT e.employee_id
FROM employees e
JOIN (
    SELECT department_id, AVG(salary) AS avg_salary
    FROM employees
    GROUP BY department_id
) a
  ON a.department_id = e.department_id
WHERE e.salary > a.avg_salary;
```

This rewrite must consider NULL department_id cases: an equality join does not match NULLs, just as the correlated predicate does not match NULLs; if the subquery finds no rows, AVG returns NULL and salary > NULL is UNKNOWN, so the outer row is eliminated. Even so, verify semantics whenever other conditions, aggregates/filters, and NULLs are involved.

### 8.3. Scalar Subqueries

A scalar subquery returns one scalar value per outer row:

```sql
SELECT
    e.employee_id,
    (
        SELECT d.department_name
        FROM departments d
        WHERE d.department_id = e.department_id
    ) AS department_name
FROM employees e;
```

Scalar subqueries have strict semantics: 0 rows returns NULL; 1 row returns the value; more than 1 row raises ORA-01427. You cannot rewrite one into a regular join without preserving this behavior, especially uniqueness and duplicates. Oracle may perform scalar subquery caching or other transformations; do not assume every outer row always triggers a physical lookup.

### 8.4. Correlation and Execution Count

A plan showing a FILTER or SUBQUERY operation does not by itself prove the subquery executes once per outer row. Oracle can cache scalar results, use nested loops, unnest, or choose another approach. Check Starts, A-Rows, and buffers in the actual plan to evaluate real execution behavior.

## 9. UNNEST and NO_UNNEST Hints

### 9.1. UNNEST Hint

UNNEST asks the optimizer to consider unnesting a subquery:

```sql
SELECT e.employee_id
FROM employees e
WHERE e.department_id IN (
    SELECT /*+ UNNEST */
           d.department_id
    FROM departments d
    WHERE d.location_id = 1700
);
```

The hint is normally placed inside the subquery to be unnested. Exact syntax and applicability depend on query and release.

### 9.2. NO_UNNEST Hint

NO_UNNEST asks Oracle to keep the subquery as a nested subquery instead of unnesting:

```sql
SELECT e.employee_id
FROM employees e
WHERE e.department_id IN (
    SELECT /*+ NO_UNNEST */
           d.department_id
    FROM departments d
    WHERE d.location_id = 1700
);
```

This can be used to test an alternative plan or prevent a specific transformation when there is evidence it increases cost. Do not use NO_UNNEST merely to keep SQL executing literally as written.

### 9.3. Hints and Query Blocks

In deeply nested queries, assign QB_NAME to query blocks and target hints to the proper block. Misplaced hints or wrong query-block references may be ignored.

### 9.4. Comparing via Plans

Run the query without hints, with UNNEST, and with NO_UNNEST in a test environment. Compare:

- Join operations and join order.
- Estimated rows and actual rows.
- Subquery Starts.
- Buffer gets, reads, elapsed time, and CPU.
- Impact of bind values and statistics.

Do not pick a hint merely because the resulting plan looks simpler.

## 10. Predicate Pushing

### 10.1. Concept

Predicate pushing (predicate pushdown) is a transformation that moves a filter condition down to a lower query block or row source to eliminate rows earlier. This can reduce the number of rows materialized, joined, sorted, aggregated, or passed through later steps.

Example:

```sql
SELECT *
FROM (
    SELECT employee_id, department_id, salary
    FROM employees
) v
WHERE v.department_id = 50;
```

The predicate department_id = 50 can be pushed into the view's query block:

```sql
SELECT employee_id, department_id, salary
FROM employees
WHERE department_id = 50;
```

Even if the view cannot be merged, predicate pushing can still filter rows inside the view before results are combined with the outer query.

### 10.2. Predicate Pushing Differs from View Merging

- View merging combines query blocks.
- Predicate pushing keeps the query-block boundary intact while moving filter conditions inside when valid.

The two transformations can complement each other. An unmergeable view can still receive pushed predicates from the outer query. Conversely, after merging, predicates become conditions within the same query block.

### 10.3. Early Filtering Can Reduce Work

If a table has 10 million rows but a predicate retains only 100 rows, pushing the predicate down to table access reduces the data flowing through joins/sorts. However, a predicate will not necessarily be pushed if:

- It cannot be evaluated in the lower query block.
- Pushing it down alters semantics.
- The expression is unsafe or cannot be moved.
- The cost model favors another alternative.

### 10.4. Predicate Pushdown Across UNION ALL

Example:

```sql
SELECT customer_id, status
FROM (
    SELECT customer_id, status
    FROM current_customers
    UNION ALL
    SELECT customer_id, status
    FROM archived_customers
) all_customers
WHERE status = 'ACTIVE';
```

The predicate status = 'ACTIVE' can be pushed into each branch:

```sql
SELECT customer_id, status
FROM current_customers
WHERE status = 'ACTIVE'
UNION ALL
SELECT customer_id, status
FROM archived_customers
WHERE status = 'ACTIVE';
```

Because UNION ALL retains all rows from both branches, distributing a predicate applied to the combined output down into each branch is valid if expressions/data types are compatible. With UNION (distinct), the transformation can still be considered while preserving duplicate elimination.

### 10.5. Predicates on Grouping Keys

View:

```sql
SELECT department_id, SUM(salary) AS total_salary
FROM employees
GROUP BY department_id;
```

Outer query:

```sql
SELECT *
FROM (
    SELECT department_id, SUM(salary) AS total_salary
    FROM employees
    GROUP BY department_id
) v
WHERE v.department_id = 50;
```

The predicate on department_id is on a grouping key and can be pushed into WHERE department_id = 50 before aggregation in this case. That allows Oracle to read/aggregate only data for department 50.

### 10.6. Predicates on Aggregates

If the outer query filters:

```sql
WHERE v.total_salary > 100000
```

The equivalent condition is HAVING SUM(salary) > 100000 after aggregation; it cannot become WHERE salary > 100000. Pushing an aggregate predicate before GROUP BY would change which rows contribute to the sum.

### 10.7. Predicates on Outer Joins

With outer joins, a predicate from the null-generated side can alter preserved rows if moved incorrectly between WHERE and ON. The optimizer only pushes when null-preserving semantics are maintained.

Examples to distinguish:

```sql
-- Eliminates departments without an ACTIVE employee:
SELECT d.department_id, e.employee_id
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
WHERE e.status = 'ACTIVE';

-- Keeps all departments, matching only ACTIVE employees:
SELECT d.department_id, e.employee_id
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
 AND e.status = 'ACTIVE';
```

Do not move predicates across an outer join just to make a query look tidier.

## 11. Join Predicate Pushdown (JPPD)

### 11.1. Concept

Join predicate pushdown is a transformation that pushes a join predicate from an outer query block into an unmerged view. The view can become correlated with rows from the outer query; Oracle can execute the view per join key value using nested loops or another suitable plan.

Example:

```sql
SELECT d.department_id, v.max_salary
FROM departments d
JOIN (
    SELECT department_id, MAX(salary) AS max_salary
    FROM employees
    GROUP BY department_id
) v
  ON v.department_id = d.department_id
WHERE d.location_id = 1700;
```

If the view is not merged, the optimizer can still push the department_id join condition from DEPARTMENTS into the view so it computes/reads only what is needed for each department instead of computing the entire aggregate result first and then joining. Feasibility and benefit depend on query structure, cardinality, indexes, and cost.

### 11.2. The View Becomes Correlated

After JPPD, the view can reference values from the outer row. This can create a correlated view. The execution plan often shows nested loops or repeated view access driven by outer rows, though plan details vary by release.

JPPD can be beneficial when the outer row source is small and the join predicate is selective. If the outer side has millions of rows, executing the inner view repeatedly can be more expensive than a hash join against a view computed once.

### 11.3. PUSH_PRED and NO_PUSH_PRED

PUSH_PRED asks the optimizer to consider pushing join predicates into a view:

```sql
SELECT /*+ PUSH_PRED(v) */
       d.department_id, v.max_salary
FROM departments d
JOIN (
    SELECT department_id, MAX(salary) AS max_salary
    FROM employees
    GROUP BY department_id
) v
  ON v.department_id = d.department_id
WHERE d.location_id = 1700;
```

NO_PUSH_PRED prevents join predicate pushdown into the specified view:

```sql
SELECT /*+ NO_PUSH_PRED(v) */
       d.department_id, v.max_salary
FROM departments d
JOIN (
    SELECT department_id, MAX(salary) AS max_salary
    FROM employees
    GROUP BY department_id
) v
  ON v.department_id = d.department_id
WHERE d.location_id = 1700;
```

Hints do not guarantee a faster plan. Verify aliases, query blocks, hint reports, and actual runtime.

### 11.4. Distinguishing Predicate Pushing from JPPD

| Technique | Pushed Predicate | Goal |
| --- | --- | --- |
| Predicate pushing | Filter from outer query into view/subquery | Filter data early |
| Join predicate pushdown | Join condition from outer block into view | Create a correlated view, leverage outer keys |
| View merging | Entire view query block is merged | Expand join order/access path search space |

The three techniques are related but not synonymous. A view that cannot be merged may still accept predicate pushdown or JPPD.

## 12. Predicate Pushdown and Special Boundaries

### 12.1. DISTINCT

A predicate on a column projected through DISTINCT can be pushed when it preserves the distinct set. For instance, filtering region_code after distinct can be equivalent to filtering before distinct if the predicate only references the same column expression:

```sql
SELECT *
FROM (
    SELECT DISTINCT region_code
    FROM customers
) v
WHERE v.region_code = 'VN';
```

However, DISTINCT must not be dropped if joins or duplicates in the outer query alter cardinality. Transformations must preserve full-statement semantics.

### 12.2. Analytic Functions

Analytic functions evaluate over the query block's row set. Pushing a predicate before an analytic function runs can change the window and results.

Example:

```sql
SELECT *
FROM (
    SELECT employee_id,
           department_id,
           salary,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY salary DESC
           ) AS rn
    FROM employees
) v
WHERE v.department_id = 50
  AND v.rn <= 3;
```

The predicate department_id = 50 can often be processed early because it isolates an independent partition; the predicate rn <= 3 depends on the analytic function's output and cannot be pushed as an ordinary filter before ROW_NUMBER is computed. Oracle has specialized transformations for certain top-N patterns, yet they must preserve semantics.

### 12.3. ROWNUM and Row Limiting

ROWNUM is assigned in the order rows are emitted by the query block; pushing a predicate across a ROWNUM boundary can change which rows are selected. Example:

```sql
SELECT *
FROM (
    SELECT *
    FROM employees
    WHERE department_id = 10
    ORDER BY salary DESC
)
WHERE ROWNUM <= 5;
```

This is the classic top-N pattern: sort inside the view and limit outside. Do not move ROWNUM into the inner query block before ORDER BY, as that would grab 5 rows before sorting and produce a different result.

### 12.4. CONNECT BY

Hierarchical queries have parent/child and traversal-order semantics. Predicates can apply before or after tree construction; pushing to the wrong place can prune necessary ancestors or change result branches. Do not rewrite CONNECT BY based solely on predicate placement without checking the resulting tree.

### 12.5. Functions in Predicates

Predicates containing user-defined functions, session-dependent functions, or non-deterministic functions can restrict predicate movement and add evaluation cost. Do not use side-effecting functions in predicates. If an expression can be written with built-in SQL or backed by a function-based index, consider those options.

### 12.6. Remote Tables and Database Links

In distributed queries, predicate pushdown can send filters to the remote database to reduce data transferred over a database link. Pushdown feasibility depends on expression type, data types, remote version, and compatibility. Inspect plans for REMOTE operations and check the actual remote SQL; do not assume every predicate is sent to the remote site.

## 13. How View Merging, Unnesting, and Predicate Pushing Interact

### 13.1. One Query Can Use Multiple Transformations

Example:

```sql
SELECT e.employee_id, e.last_name
FROM employees e
JOIN (
    SELECT department_id
    FROM departments
    WHERE location_id = 1700
) d
  ON d.department_id = e.department_id
WHERE EXISTS (
    SELECT 1
    FROM job_history h
    WHERE h.employee_id = e.employee_id
);
```

The optimizer can:

- Merge the DEPARTMENTS inline view if it is simple enough.
- Unnest EXISTS into a semi join.
- Push the location_id predicate down to DEPARTMENTS.
- Choose the optimal join order and join method for the post-transformation table set.

The final plan does not necessarily retain the aliases or SELECT layers from the original text.

### 13.2. One Transformation Can Unlock Another

Merging a view can expose additional join predicates and enable join elimination, predicate transitivity, or join reordering. Unnesting a subquery can bring inner tables into the same query block so the optimizer can push predicates or pick different join methods.

This is why a single transformation should not be judged in isolation from the full plan. A transformation may pay off because it unlocks downstream options.

### 13.3. Transformations Can Also Expand the Search Space

Adding query blocks, merging views, or unnesting multiple subqueries increases the number of alternatives the optimizer can consider. Oracle has search limits and heuristics to control parse/optimization time. For very complex queries, the optimizer will not necessarily evaluate every possible permutation.

### 13.4. Hints Can Create Unexpected Interactions

MERGE, NO_MERGE, UNNEST, NO_UNNEST, and PUSH_PRED can affect query blocks and opportunities for other transformations. A hint forcing a view to stay separate can block a better join order; a hint forcing unnesting can inflate intermediate row-source cardinality if query structure/semantics do not fit.

If multiple hints are required, document each hint's goal, query block name, and plan/runtime evidence. Avoid stacking conflicting hints.

## 14. Reading Execution Plans to Identify Transformations

### 14.1. DBMS_XPLAN

To view a plan:

```sql
EXPLAIN PLAN FOR
SELECT e.employee_id
FROM employees e
WHERE EXISTS (
    SELECT 1
    FROM departments d
    WHERE d.department_id = e.department_id
      AND d.location_id = 1700
);

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

EXPLAIN PLAN produces an estimated plan and does not necessarily reflect bind values, runtime row counts, or the child cursor actually executing in the application.

### 14.2. Actual Plan

For a query that has executed with appropriate statistics, view:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS +OUTLINE'
    )
);
```

ALLSTATS LAST requires runtime row-source statistics to be collected, such as via the GATHER_PLAN_STATISTICS hint or appropriate configuration. DISPLAY_CURSOR reads cursors from the shared pool and requires privileges on fixed views.

### 14.3. Signs of Semi/Anti Joins

The plan may show:

- HASH JOIN SEMI
- NESTED LOOPS SEMI
- HASH JOIN ANTI
- HASH JOIN ANTI NA / ANTI SNA

These operations are strong evidence that existence/non-existence predicates were transformed into semi/anti joins.

### 14.4. Signs a View Remained Separate

The plan may contain a VIEW operation, though seeing VIEW alone is insufficient to conclude which transformation did or did not occur. A view may have been preserved, received pushed predicates, or executed as a separate row source. Inspect ALIAS, Predicate Information, Outline Data, and query block mappings.

### 14.5. Predicate Information

Predicate Information shows which predicates act as access predicates or filter predicates at each operation. This helps reveal whether a predicate was pushed down to table access or remained at a higher filter step.

Example:

```text
access("E"."DEPARTMENT_ID"=50)
filter("E"."SALARY">5000)
```

ACCESS predicates typically help locate rows/index lookups; FILTER predicates filter rows after retrieval. Exact meaning depends on the operation; not every higher-level filter is bad.

### 14.6. Query Block Names and Outlines

With +ALIAS and +OUTLINE formats, the plan displays query block/alias names and the hint outline Oracle uses to describe the plan. Use this information to understand which views/subqueries were merged or unnested and which hints reproduce the plan.

Do not blindly copy outline hints into production; outlines can depend on objects, release, and statistics.

### 14.7. Comparing Estimated and Actual Rows

If E-Rows diverges widely from A-Rows, the optimizer may pick transformations/join methods based on wrong cardinalities. Check:

- Are table and index statistics current?
- Does data skew require histograms?
- Does column correlation require extended statistics?
- Do predicates have bind variables and bind peeking/adaptive cursor sharing?
- Is cardinality after view merging/unnesting estimated accurately?

A semantically valid transformation whose cost relies on bad estimates can still lead to a poor plan.

## 15. WITH Clauses, Inline Views, and Materialization

### 15.1. CTEs Are Not Temporary Tables by Default

A WITH clause (subquery factoring) names a query block:

```sql
WITH active_employees AS (
    SELECT employee_id, department_id, salary
    FROM employees
    WHERE status = 'ACTIVE'
)
SELECT department_id, COUNT(*)
FROM active_employees
GROUP BY department_id;
```

CTEs help organize SQL and reuse logic. They do not automatically mean Oracle must create a physical temporary table. The optimizer can inline/merge a CTE into the consuming query block, or choose TEMP TABLE TRANSFORMATION / materialization when appropriate.

### 15.2. Inlining/Merging a CTE

If a CTE is simple and referenced only once, the optimizer can inline it to optimize the entire query. The CTE then behaves like a merged inline view; the named boundary in SQL does not necessarily remain a physical boundary in the plan.

### 15.3. Materializing a CTE

In some queries, materializing a CTE can help when intermediate results are referenced multiple times or recomputation is expensive. The plan may show TEMP TABLE TRANSFORMATION, LOAD AS SELECT, and reads from an internal temporary table.

Materialization has costs:

- Writing and reading intermediate data.
- Using TEMP space.
- Potentially losing opportunities for deeper predicate pushing or join reordering.
- Potentially paying off when avoiding recomputing an expensive, reused result.

Do not assume materializing is always faster than inlining.

### 15.4. NO_MERGE Does Not Mean Materialize

NO_MERGE keeps a query block separate with respect to merging; it does not promise Oracle will write the view's output to a temporary table. The view can execute as a distinct row source, predicates may still be pushed, and the optimizer can still choose different execution strategies.

Distinction:

| Concept | Meaning |
| --- | --- |
| View merging | Combines query blocks |
| NO_MERGE | Prevents merging the specified view when the hint applies |
| CTE inline | Expands the CTE into the consuming query |
| Materialization | Generates and reads intermediate results per the plan |
| TEMP TABLE TRANSFORMATION | Operation indicating a materialization strategy in the plan |

### 15.5. MATERIALIZE and INLINE Hints

In some Oracle releases, users encounter MATERIALIZE and INLINE hints to influence CTE handling. Their documentation/support level and behavior can vary across releases. Do not rely on hints not guaranteed by your release documentation as a stable API; prefer inspecting plans, checking supported features, and using SQL Plan Management if plan stability is needed in production.

## 16. Related Hints and Disciplined Usage

### 16.1. Transformation Hint Group

| Hint | General Purpose |
| --- | --- |
| MERGE | Requests considering view merging |
| NO_MERGE | Prevents merging the specified view |
| UNNEST | Requests considering subquery unnesting |
| NO_UNNEST | Prevents unnesting the specified subquery |
| PUSH_PRED | Requests considering join predicate pushdown |
| NO_PUSH_PRED | Prevents join predicate pushdown |
| PUSH_SUBQ | Requests pushing a subquery earlier in the plan when applicable |
| NO_PUSH_SUBQ | Prevents subquery pushing per the specified hint |
| QB_NAME | Names a query block for targeting |

Hints only take effect when context, syntax, and transformation validity align. Do not treat them as global on/off switches for every transformation in a statement.

### 16.2. Placing Hints on the Right Query Block

Naming example:

```sql
SELECT /*+ QB_NAME(main) */
       e.employee_id
FROM employees e
WHERE EXISTS (
    SELECT /*+ QB_NAME(dept_exists) UNNEST */
           1
    FROM departments d
    WHERE d.department_id = e.department_id
      AND d.location_id = 1700
);
```

In large SQL statements, meaningful QB_NAME labels make hint tracing easier. Query block names and aliases must be consistent; verify via plan alias/outline sections.

### 16.3. Hint Conflicts and Ignored Hints

For example, placing both MERGE and NO_MERGE on the same view, or UNNEST and NO_UNNEST on the same subquery, creates a conflict. Oracle applies precedence/interpretation rules depending on placement and release; do not rely on ambiguous outcomes.

Check the hint report if your release supports it:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALL +HINT_REPORT'
    )
);
```

The hint report shows whether hints were used, ignored, or had syntax/object errors. If that format is unsupported in your release, use outlines and corresponding diagnostics.

### 16.4. Do Not Alter Hidden Optimizer Parameters to Force Transformations

Parameters prefixed with underscores such as _optimizer_* are hidden parameters, not normal tuning interfaces. Do not alter them arbitrarily at session or system level. Interfering with them can cause unsupported behavior and affect many queries. If an optimizer bug is suspected, gather the SQL, plan, version, and traces and work with Oracle Support.

### 16.5. OPTIMIZER_FEATURES_ENABLE

OPTIMIZER_FEATURES_ENABLE can be used in testing to simulate the optimizer behavior set of an earlier release. It is not a default fix for a single slow query and can alter many other optimizer decisions simultaneously. Use it only under control, measure workloads, and follow migration/upgrade guidance.

## 17. Workflow for Investigating Transformations in Slow Queries

### 17.1. Start from Actual SQL and Data

Collect:

- Actual SQL text and query binds.
- Oracle version, optimizer_features_enable, and relevant session settings.
- Object definitions, constraints, indexes, and partitioning.
- Relevant statistics and histograms.
- SQL_ID, child cursors, and actual execution plan.
- Runtime rows, elapsed time, CPU, buffer gets, physical reads, and waits.

Do not draw conclusions from a simplified SQL snippet if production uses different bind values or dynamic predicates.

### 17.2. Identify Which Transformation Is Suspected

Ask specific questions:

- Was an inline view kept separate, preventing a better join order?
- Was EXISTS/IN kept as a FILTER subquery causing many Starts?
- Did a filter predicate remain in an upper query block after a view generated many rows?
- Did JPPD cause an inner view to execute too many times?
- Did complex view merging inflate intermediate cardinality or alter aggregation strategy?

Avoid saying “the optimizer didn't optimize” without pinpointing the operation and evidence.

### 17.3. Controlled Plan Comparisons

Build variants:

1. Original SQL, no hints.
2. Original SQL with the suspected transformation hint.
3. Manual SQL rewrite with equivalent semantics.
4. Variants with/without predicates or CTEs per hypothesis.

Run with identical data/bind values, identical environment, and controlled warm/cold cache. Measure multiple times and inspect actual plans.

### 17.4. Check Cardinality Before Forcing Transformations

If estimated rows are far off, fixing statistics or providing appropriate correlation info can enable the optimizer to select a better transformation on its own. Options include gathering statistics, adding histograms when skew is significant, creating extended statistics for column groups, and checking dynamic sampling.

Do not add histograms or extended statistics broadly without evidence; they can shift plans across many queries.

### 17.5. Check Bind Peeking and Adaptive Cursor Sharing

A query can run with bind values having vastly different selectivities. A plan optimal for a popular location_id may be poor for a rare location_id. Check child cursors, bind peeking, and adaptive cursor sharing before concluding transformation is the sole cause.

### 17.6. Use SQL Monitor/Trace When Necessary

SQL Monitor, SQL Trace/TKPROF, and optimizer traces can provide runtime details or optimizer decisions. Usage rights, licensing, and overhead depend on your environment. Collect narrowly scoped traces on specific queries and disable tracing once finished.

## 18. 10053 Optimizer Trace

### 18.1. Purpose

Event 10053 is an in-depth optimizer trace recording many decisions made during SQL optimization, including transformations considered, rejection reasons, cardinality/cost estimates, and plan alternatives.

It is an advanced diagnostic tool, not a trace to leave enabled routinely in production.

### 18.2. Controlled Collection

In a test environment or under DBA/Oracle Support guidance, you can enable the trace for a specific session/query. Example showing one way to use the event in a session:

```sql
ALTER SESSION SET EVENTS '10053 trace name context forever, level 1';

-- Parse/execute the SQL statement under investigation.
SELECT ...

ALTER SESSION SET EVENTS '10053 trace name context off';
```

Exact event syntax and appropriate levels depend on release; follow official documentation/support recommendations. The trace focuses on hard parse/optimization, not measuring execution elapsed time.

### 18.3. Reading the Trace

The trace can contain:

- Query block transformations attempted.
- View merging/unnesting decisions.
- Predicate move-around.
- Join order alternatives.
- Estimated cardinalities and costs.
- Reasons a transformation was not applied.

Traces are large and complex. Read only the sections relevant to the query block/transformation under investigation; do not share trace files publicly if they contain SQL text, object names, bind values, or sensitive data.

## 19. Lab: View Merging and Predicate Pushing

Examples use a sample schema with EMPLOYEES and DEPARTMENTS. If your schema lacks them, create separate lab tables or substitute equivalent tables; never run DDL in a production schema.

### 19.1. Simple Inline View Query

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       v.employee_id, v.department_id
FROM (
    SELECT employee_id, department_id
    FROM employees
    WHERE salary > 5000
) v
WHERE v.department_id = 50;
```

After running, view the actual plan with DBMS_XPLAN.DISPLAY_CURSOR. Observe whether the view remains a separate operation or predicates appear directly at table access.

### 19.2. Comparing MERGE and NO_MERGE

```sql
SELECT /*+ GATHER_PLAN_STATISTICS MERGE(v) */
       v.employee_id, d.department_name
FROM (
    SELECT employee_id, department_id
    FROM employees
    WHERE salary > 5000
) v
JOIN departments d
  ON d.department_id = v.department_id
WHERE d.location_id = 1700;
```

Run the variant:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS NO_MERGE(v) */
       v.employee_id, d.department_name
FROM (
    SELECT employee_id, department_id
    FROM employees
    WHERE salary > 5000
) v
JOIN departments d
  ON d.department_id = v.department_id
WHERE d.location_id = 1700;
```

Compare join order, view operations, E-Rows/A-Rows, buffer gets, and elapsed time. Hints may not apply if the view merged automatically or is ineligible; verify via the plan/hint report.

### 19.3. Predicate Pushing into a UNION ALL View

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       x.customer_id
FROM (
    SELECT customer_id, status FROM current_customers
    UNION ALL
    SELECT customer_id, status FROM archived_customers
) x
WHERE x.status = 'ACTIVE';
```

Inspect Predicate Information and table access for each branch. The predicate may appear in both branches. This example demonstrates predicate pushdown without full view merging across a set operator.

### 19.4. Predicates on Grouping Keys

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       v.department_id, v.total_salary
FROM (
    SELECT department_id, SUM(salary) AS total_salary
    FROM employees
    GROUP BY department_id
) v
WHERE v.department_id = 50;
```

Observe where the department_id predicate is applied. Then test a predicate on total_salary and compare, because aggregate conditions must be evaluated after GROUP BY.

## 20. Lab: Subquery Unnesting and NULL Semantics

### 20.1. EXISTS

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
);
```

Check whether the plan shows a SEMI join or FILTER. Compare Starts, A-Rows, and buffer gets.

### 20.2. Testing UNNEST and NO_UNNEST

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT /*+ UNNEST */ 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
);
```

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT /*+ NO_UNNEST */ 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
      AND o.order_status = 'OPEN'
);
```

Do not merely count operations; run with the same binds/data and inspect actual statistics.

### 20.3. NOT IN with NULL

Create a small dataset:

```sql
WITH candidates (id) AS (
    SELECT 1 FROM dual
    UNION ALL
    SELECT 2 FROM dual
    UNION ALL
    SELECT 3 FROM dual
),
blocked_ids (id) AS (
    SELECT 2 FROM dual
    UNION ALL
    SELECT CAST(NULL AS NUMBER) FROM dual
)
SELECT id
FROM candidates
WHERE id NOT IN (SELECT id FROM blocked_ids);
```

The query returns no rows because the inner set contains NULL. Try replacing NOT IN with NOT EXISTS:

```sql
WITH candidates (id) AS (
    SELECT 1 FROM dual
    UNION ALL
    SELECT 2 FROM dual
    UNION ALL
    SELECT 3 FROM dual
),
blocked_ids (id) AS (
    SELECT 2 FROM dual
    UNION ALL
    SELECT CAST(NULL AS NUMBER) FROM dual
)
SELECT c.id
FROM candidates c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_ids b
    WHERE b.id = c.id
);
```

The result can include 1 and 3. The difference is SQL NULL semantics, not an optimizer bug. This lab helps identify which rewrites preserve business logic.

## 21. Common Issues and Troubleshooting

| Symptom | Possible Cause | Investigation Path |
| --- | --- | --- |
| Inline view still shows a VIEW operation | View not merged, intentionally preserved, or plan displays separate row source | Check query blocks, aliases, predicates, and transformation eligibility |
| View merge makes query slower | Post-merge join order/cardinality is suboptimal | Compare actual plans, test NO_MERGE, and inspect statistics |
| EXISTS runs with FILTER and high Starts | Subquery not unnested or plan chose that path | Check Starts/A-Rows; test UNNEST in a controlled way |
| NOT IN returns zero rows | Inner subquery contains NULL | Determine intended semantics; consider NOT EXISTS or filtering NULLs if appropriate |
| NOT EXISTS and NOT IN return different results | Different NULL semantics | Check nullability of both outer and inner keys |
| Predicate remains in an upper operation | Cannot be pushed, invalid, or cost did not select pushdown | Inspect query block boundaries and Predicate Information |
| UNION ALL view reads too many rows | Predicate not pushed into branches or missing access paths | Inspect per-branch plans, indexes, and statistics |
| JPPD generates high Starts | Large outer row source, inner view executed repeatedly | Compare hash join/materialization vs. nested loops; check cardinality |
| GROUP BY view processes too many rows | Grouping-key filter not pushed or stale stats | Check predicate mapping, group cardinality, and cost |
| Outer join loses rows after rewrite | Predicate moved improperly between ON and WHERE | Check null-preserving semantics and unmatched rows |
| Hint has no effect | Wrong alias/query block, hint conflict, or invalid transformation | Use QB_NAME, outlines, and hint reports |
| Plan changes across bind values | Differing selectivities, child cursors/adaptive cursor sharing | Check bind peeking, child cursors, and actual rows |
| EXPLAIN PLAN differs from runtime | Different binds, environment, or child cursor | Use DISPLAY_CURSOR for the actual cursor |
| Query slow despite right transformation | Wrong cardinality/cost estimate or poor access path | Check statistics, E-Rows/A-Rows, waits, and I/O |

## 22. Best Practice Principles

1. **Understand semantics before rewriting.** Pay special attention to NULLs, duplicates, outer joins, aggregation, ROWNUM, and analytic functions.
2. **Read queries by query block.** Name blocks in multi-layered SQL to trace transformations.
3. **Let the optimizer choose first.** Do not add hints without a baseline plan and actual runtime data.
4. **Distinguish view merging from predicate pushing.** An unmerged view can still receive filter/join predicates.
5. **Use EXISTS/IN for existence checks.** Do not replace them with joins unless handling duplicates/cardinality.
6. **Be careful with NOT IN and NULLs.** Verify nullability and semantics before rewriting to NOT EXISTS.
7. **Do not push aggregate predicates down into WHERE.** Distinguish row filters from group filters.
8. **Preserve outer join semantics.** Predicates in ON vs. WHERE can produce different results.
9. **Use hints as evidence-based experiments.** MERGE/NO_MERGE/UNNEST/NO_UNNEST/PUSH_PRED are not universal turbo buttons.
10. **Use QB_NAME and hint reports.** Verify hints target the intended query block.
11. **Compare actual plans.** Rely on A-Rows, Starts, buffers, and runtime—not EXPLAIN PLAN alone.
12. **Fix cardinality estimates before forcing plans.** Inaccurate statistics may be the root cause.
13. **Measure across real bind values.** One plan does not suit every selectivity.
14. **Do not alter hidden optimizer parameters arbitrarily.** Collect evidence and follow Oracle Support guidance if an optimizer bug is suspected.
15. **Verify after upgrades.** Transformations and cost models can change across releases/optimizer_features_enable.
16. **Keep SQL readable.** Query transformation is the optimizer's job; SQL should clearly express business logic.

## 23. Self-Check Questions

1. What is a query block?
2. How does query transformation help the optimizer expand its search space?
3. How does view merging differ from predicate pushing?
4. What kind of views does simple view merging typically apply to?
5. What additional semantic boundaries must complex view merging handle?
6. Why can omitting DISTINCT alter cardinality?
7. Why can a predicate on a grouping key be pushed before GROUP BY while an aggregate predicate cannot?
8. How do outer joins complicate predicate pushdown?
9. What are the MERGE and NO_MERGE hints used for?
10. How does QB_NAME assist when tuning multi-level queries?
11. What is subquery unnesting?
12. How does a semi join differ from an inner join when the inner side has multiple matches?
13. Which operation typically represents EXISTS and IN?
14. How does an anti join relate to NOT EXISTS?
15. Why is NOT IN affected by NULLs?
16. What does a null-aware anti join signify in an execution plan?
17. Which constructs can restrict subquery unnesting?
18. How does a scalar subquery differ from a join in 0/1/many-row semantics?
19. How does join predicate pushdown make a view correlated?
20. When can JPPD be beneficial, and when can it increase Starts?
21. How does predicate pushing across UNION ALL work?
22. Why can a predicate on analytic row_number not be pushed like an ordinary filter?
23. Are CTEs materialized by default?
24. Does NO_MERGE mean materialization?
25. How does DISPLAY_CURSOR differ from EXPLAIN PLAN?
26. How do E-Rows, A-Rows, and Starts help diagnose transformations?
27. When should you inspect a 10053 optimizer trace?
28. Why should you avoid forcing transformations via hidden parameters?

## 24. Mental Model

```text
SQL WITH MULTIPLE QUERY BLOCKS
        |
        v
  VIEW / INLINE VIEW / CTE
        |
        +-- VIEW MERGING
        |      Merge query blocks to expand join search space
        |
        +-- PREDICATE PUSHING
        |      Push filters down toward data sources
        |
        +-- JOIN PREDICATE PUSHING
               Push join keys into a view, possibly creating a correlated view
        |
        v
  SUBQUERY
        |
        +-- IN / EXISTS -> SEMI JOIN
        +-- NOT EXISTS -> ANTI JOIN
        +-- NOT IN -> NULL-aware semantics
        +-- UNNEST or keep subquery
        |
        v
  COST-BASED PLAN SEARCH
        |
        +-- Join order / access path / join method
        +-- Cardinality / statistics / bind values
        +-- Validity first, cost second
        |
        v
  VERIFICATION
        |
        +-- DISPLAY_CURSOR / ALLSTATS LAST
        +-- Predicate Information / Alias / Outline
        +-- A-Rows / E-Rows / Starts / Buffers
        +-- Use hints only with evidence
```

**Key takeaway:** view merging combines query blocks, unnesting converts subqueries into appropriate joins, and predicate pushing moves conditions closer to data sources. The optimizer may only apply transformations that preserve semantics and are judged beneficial by the cost model. When tuning, read actual plans, verify NULL/cardinality/outer join behavior, and use hints as controlled experiments rather than defaults.
