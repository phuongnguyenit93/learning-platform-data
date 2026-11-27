# Hints, Query Blocks, and Verifying That Hints Are Used

The Oracle SQL Optimizer selects an execution plan automatically based on the SQL statement, statistics, bind values, optimizer settings, and many other factors. In certain tuning situations, developers or DBAs want to steer the optimizer toward a specific choice—such as using an index, picking a join method, changing join order, or controlling a query transformation. Oracle provides **optimizer hints** to pass these directives directly inside SQL.

A hint is only useful when placed in the right position, referencing the exact alias and query block, applicable to the SQL structure, and producing a better plan in the real workload. Seeing a hint in source code does not prove Oracle actually used it. You must inspect the executed cursor and its hint report.

This lesson focuses on four tasks:

1. Writing hints with valid syntax in the right query block.
2. Using aliases and `QB_NAME` to target objects precisely.
3. Understanding hints for access paths, join order, join methods, and query transformations.
4. Verifying whether hints were used, ignored, or inapplicable via `DBMS_XPLAN`.

## 1. What is an optimizer hint?

An optimizer hint is a directive placed inside a special SQL comment. Hints can guide the optimizer toward an access path, join method, join order, degree of parallelism, or transformation behavior.

Example:

~~~sql
SELECT /*+ FULL(e) */
       e.employee_id,
       e.employee_name
FROM employees e
WHERE e.department_id = 10;
~~~

`FULL(e)` instructs the optimizer to consider a full table scan for the row source aliased `E` in the corresponding query block.

Another example:

~~~sql
SELECT /*+ USE_HASH(d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

`USE_HASH(d)` steers the optimizer to use a hash join with row source `D` if the hint is valid and applicable.

Hints do not change the business meaning of a SQL statement. Query output must still obey SQL semantics. Hints guide or constrain how the optimizer searches for an execution plan.

### 1.1 Hints are special comments

Regular comment:

~~~sql
SELECT /* query employee */ employee_id
FROM employees;
~~~

Hint comment:

~~~sql
SELECT /*+ FULL(e) */ e.employee_id
FROM employees e;
~~~

The plus sign must follow the comment opener immediately with no space: `/*+`.

The following are not valid hint comments:

~~~sql
SELECT /* + FULL(e) */ e.employee_id FROM employees e;
SELECT --+ FULL(e)
       e.employee_id
FROM employees e;
~~~

The first example has a space between `/*` and `+`. The second uses a line comment rather than the standard block hint comment. Always use `/*+ ... */`.

### 1.2 Hint placement in SQL statements

Hints are placed immediately after the opening keyword of a query block or DML statement:

~~~sql
SELECT /*+ FULL(e) */ ...
INSERT /*+ APPEND */ INTO ...
UPDATE /*+ ... */ ...
DELETE /*+ ... */ ...
MERGE /*+ ... */ INTO ...
~~~

For nested `SELECT`s, each query block can have its own hint comment right after that block's `SELECT`.

### 1.3 Combine hints for one query block into a single comment

Write:

~~~sql
SELECT /*+ LEADING(e d) USE_NL(d) INDEX(d pk_departments) */
       ...
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

Do not split hints for the same query block across separate comments after the same `SELECT`. Oracle only recognizes hint comments in the designated position; comments elsewhere may be ignored.

## 2. Hints are not absolute plan guarantees

A hint can be:

- Recognized and applied.
- Recognized yet inapplicable in the current context.
- Invalidated due to conflict with another hint.
- Unable to resolve the referenced alias or query block.
- Rendered inapplicable after the optimizer transforms the query block.
- Syntactically malformed or given invalid arguments.

Therefore, distinguish carefully:

| Observation | What can be concluded? |
|---|---|
| Hint appears in SQL source | Only that the author requested the hint |
| Execution plan contains the matching operation | Plan has that operation, though not necessarily because of the hint |
| Hint report marks hint Used | Oracle recorded that the hint was used |
| Hint report marks hint Unused/Unresolved | Investigate the reason and scope |
| Plan hash changed | Plan differs, not yet proof the new plan is faster |

An `INDEX RANGE SCAN` in the plan does not by itself prove an `INDEX` hint took effect; the optimizer might have chosen that index anyway without the hint. Conversely, a hint may be recognized yet still fail to produce what the author expected due to other applicability rules.

## 3. Common hint groups

### 3.1 Optimizer goal hints

`ALL_ROWS`:

~~~sql
SELECT /*+ ALL_ROWS */ ...
FROM orders o;
~~~

Steers the optimizer toward throughput / minimum total cost for processing the entire result set.

`FIRST_ROWS(n)`:

~~~sql
SELECT /*+ FIRST_ROWS(20) */ ...
FROM orders o;
~~~

Steers the optimizer to prioritize returning the first N rows quickly in interactive workloads. It does not guarantee reading only N rows or stopping every operation after N rows.

### 3.2 Access path hints

`FULL(alias)`:

~~~sql
SELECT /*+ FULL(e) */
       e.employee_id
FROM employees e
WHERE e.department_id = 10;
~~~

`INDEX(alias index_name)`:

~~~sql
SELECT /*+ INDEX(e ix_employees_department) */
       e.employee_id
FROM employees e
WHERE e.department_id = 10;
~~~

`INDEX_FFS(alias index_name)`:

~~~sql
SELECT /*+ INDEX_FFS(e ix_employees_department) */
       e.department_id
FROM employees e;
~~~

An `INDEX` hint steers the optimizer toward the named index. It does not mean the index is always cheaper than a full scan; if the hint increases I/O or forces many rowid table visits, the query can run slower.

### 3.3 Join method hints

`USE_NL(alias)`:

~~~sql
SELECT /*+ USE_NL(d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

`USE_HASH(alias)`:

~~~sql
SELECT /*+ USE_HASH(d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

`USE_MERGE(alias)`:

~~~sql
SELECT /*+ USE_MERGE(d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

These hints direct the join method used for the specified inner row source. They do not independently dictate the overall join order.

### 3.4 Join order hints

`LEADING`:

~~~sql
SELECT /*+ LEADING(e d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

`LEADING(e d)` guides the optimizer to join starting with the row sources in the specified order within the query block. For multi-table queries, the alias list must reflect the intended join sequence.

`ORDERED`:

~~~sql
SELECT /*+ ORDERED */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;
~~~

`ORDERED` tells the optimizer to follow the table order in the `FROM` clause. When `ORDERED` is specified, `LEADING` is ignored per Oracle rules; do not include both expecting them to jointly control join order.

### 3.5 Query transformation hints

Common hints:

- `MERGE(view_alias)`: enables/steers view merging where applicable.
- `NO_MERGE(view_alias)`: prevents view merging for the named inline view.
- `UNNEST`: directs the optimizer to unnest a subquery.
- `NO_UNNEST`: prevents unnesting where applicable.
- `PUSH_PRED`: directs predicate pushing into a view.
- `NO_PUSH_PRED`: prevents predicate pushing.

Query transformations can reshape query blocks before access paths/joins are selected. When a hint does not take effect as expected, check whether the query block was merged, unnested, or transformed.

### 3.6 Parallel hints

Example:

~~~sql
SELECT /*+ PARALLEL(e, 4) */
       COUNT(*)
FROM employees e;
~~~

`PARALLEL` steers the optimizer toward parallel execution with the specified degree if the environment and objects support it. Parallelism can boost throughput but also consumes CPU, PGA, I/O, and parallel server resources. Never apply parallel hints just because a query is slow without diagnosing the bottleneck first.

### 3.7 Diagnostic hints

`GATHER_PLAN_STATISTICS`:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       e.employee_id
FROM employees e
WHERE e.department_id = 10;
~~~

This hint requests runtime plan statistics collection for the cursor so `E-Rows`/`A-Rows` and related metrics can be inspected via `DBMS_XPLAN`. It is a measurement/diagnostic hint, not an access path or join method directive.

## 4. Aliases are a critical part of hints

If a SQL statement declares an alias:

~~~sql
SELECT /*+ INDEX(e ix_employees_department) */
       e.employee_id
FROM employees e
WHERE e.department_id = 10;
~~~

the hint must reference alias `E`. Do not use the table name `EMPLOYEES` instead of `E` here:

~~~sql
SELECT /*+ INDEX(employees ix_employees_department) */
       e.employee_id
FROM employees e
WHERE e.department_id = 10;
~~~

The second example can prevent the hint from resolving its target because the query declared an alias.

Practical rules:

- Use the exact alias declared in `FROM`.
- Do not include schema owners on aliases inside hints.
- If an alias is double-quoted with mixed/special casing, respect exact identifier semantics.
- Do not confuse an outer query block's inline-view alias with a table alias inside the inline view.

### 4.1 Same table appearing twice

Self-join example:

~~~sql
SELECT /*+ USE_NL(m) */
       e.employee_id,
       m.employee_name AS manager_name
FROM employees e
JOIN employees m
  ON m.employee_id = e.manager_id;
~~~

`EMPLOYEES` appears twice with aliases `E` and `M`. The hint must identify which occurrence to target. Using the bare table name `EMPLOYEES` cannot distinguish the two row sources.

### 4.2 Inline view aliases

~~~sql
SELECT /*+ NO_MERGE(q) */
       q.order_id,
       q.customer_id
FROM (
    SELECT o.order_id,
           o.customer_id
    FROM orders o
    WHERE o.status = 'OPEN'
) q;
~~~

In the outer query block, the inline view has alias `Q`. `NO_MERGE(q)` references `Q` in the outer block. Inside the inline view, `ORDERS` has alias `O` and belongs to a different query block.

## 5. What is a query block?

A query block is a unit of a query analyzed and transformed independently by the optimizer. A single SQL statement can contain multiple query blocks from:

- The main `SELECT`.
- Inline views in `FROM`.
- Scalar subqueries.
- `EXISTS`/`IN` subqueries.
- Set queries such as `UNION`/`UNION ALL`.
- Subqueries inside expressions.

Example:

~~~sql
SELECT c.customer_id,
       (
           SELECT MAX(o.order_date)
           FROM orders o
           WHERE o.customer_id = c.customer_id
       ) AS last_order_date
FROM customers c;
~~~

There is an outer query block reading `CUSTOMERS` and an inner query block computing `MAX(ORDER_DATE)` from `ORDERS`.

Hints placed in the outer `SELECT` apply by default to the outer query block. Hints placed immediately after a subquery's `SELECT` apply to that inner query block.

### 5.1 Each query block has its own scope

Example:

~~~sql
SELECT /*+ QB_NAME(q_main) */
       c.customer_id,
       q.order_count
FROM customers c
JOIN (
    SELECT /*+ QB_NAME(q_orders) */
           o.customer_id,
           COUNT(*) AS order_count
    FROM orders o
    GROUP BY o.customer_id
) q
  ON q.customer_id = c.customer_id;
~~~

Here:

- `q_main` is the outer query block name.
- `q_orders` is the query block name inside the inline view.
- Aliases `C` and `Q` belong to the outer block.
- Alias `O` belongs to block `q_orders`.

Do not reference alias `O` in the outer block when `O` exists only inside the inner query block.

## 6. QB_NAME: naming query blocks

`QB_NAME` assigns a name to a query block so other hints can target it precisely.

Example:

~~~sql
SELECT /*+ QB_NAME(q_main) */
       c.customer_id,
       q.order_count
FROM customers c
JOIN (
    SELECT /*+ QB_NAME(q_orders) */
           o.customer_id,
           COUNT(*) AS order_count
    FROM orders o
    GROUP BY o.customer_id
) q
  ON q.customer_id = c.customer_id;
~~~

Names `q_main` and `q_orders` make scopes clear to readers. In complex SQL statements, explicit names are far easier to maintain than auto-generated names like `SEL$1` or `SEL$2`.

### 6.1 Why shouldn't you rely long-term on SEL$1?

The optimizer generates internal names for query blocks. Auto-generated names can shift whenever the SQL changes, query transformations fire, or subquery structures change.

If a hint references `SEL$1` and a later edit reorders query blocks, the hint may point to the wrong block or fail to resolve altogether.

Explicit `QB_NAME` labels keep hints readable and decoupled from internal numbering.

### 6.2 Query block names must be unique within the SQL statement

Pick short, meaningful, unique names:

- `q_main`
- `q_orders`
- `q_customer_filter`
- `q_item_aggregation`

Keep names consistent when referencing them in query-block-qualified hints.

### 6.3 QB_NAME is not a table alias

`QB_NAME` names a query block, whereas an alias names a row source/table occurrence. The two identifiers have distinct roles:

| Identifier | Example | Used to |
|---|---|---|
| Query block name | `q_orders` | Identify query scope |
| Table alias | `o` | Identify row source inside query block |
| Index name | `ix_orders_status` | Identify index |

A hint targeting both a query block and an alias usually needs both pieces of information.

## 7. Hints targeting another query block

Oracle supports query-block-qualified hint syntax by prefixing the query block name with `@` inside the hint's target argument.

Example:

~~~sql
SELECT /*+
          QB_NAME(q_main)
          NO_MERGE(q)
          INDEX(@q_orders o ix_orders_status)
       */
       q.order_id,
       c.customer_name
FROM (
    SELECT /*+ QB_NAME(q_orders) */
           o.order_id,
           o.customer_id
    FROM orders o
    WHERE o.status = :status
) q
JOIN customers c
  ON c.customer_id = q.customer_id;
~~~

Explanation:

- `QB_NAME(q_main)` names the outer block.
- `QB_NAME(q_orders)` names the inline view's block.
- `NO_MERGE(q)` tells the optimizer not to merge inline view `Q` into the outer block.
- `INDEX(@q_orders o ix_orders_status)` targets alias `O` inside block `q_orders` to guide its access path.

This is advanced syntax. When using it, verify that the query block name and alias match the parsed query and inspect the Hint Report. If views merge or transformations alter block structure, re-verify hint scope.

### 7.1 Do not overuse cross-query-block hints

Cross-block hints help when controlling a deeply nested row source. However, they make SQL harder to read and brittle when query structure changes.

Preferences:

1. Place hints directly inside the query block owning the row source whenever possible.
2. Use `QB_NAME` when cross-block targeting is necessary.
3. Keep query block names stable and descriptive.
4. Re-check the hint report after every SQL structural change.

## 8. Example of hints per query block

~~~sql
SELECT /*+ QB_NAME(q_main) LEADING(c q) USE_NL(q) */
       c.customer_id,
       q.order_id
FROM customers c
JOIN (
    SELECT /*+ QB_NAME(q_orders) INDEX(o ix_orders_status) */
           o.order_id,
           o.customer_id
    FROM orders o
    WHERE o.status = :status
) q
  ON q.customer_id = c.customer_id;
~~~

In this example:

- Block `q_main` carries `LEADING` and `USE_NL`.
- Block `q_orders` carries `INDEX` on `O`.
- Outer alias `Q` is distinct from inner alias `O`.
- Both hint groups reside in their respective query block's hint comment.

The optimizer may still transform the query under other rules. Check the plan and hint report to confirm how hints were applied.

## 9. How do LEADING, ORDERED, and USE_NL work together?

A common mistake is adding only `USE_NL` and expecting Oracle to pick the right driving table.

Example:

~~~sql
SELECT /*+ USE_NL(d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.employee_id BETWEEN 1000 AND 1010;
~~~

`USE_NL(d)` guides `D` to be the inner row source of a nested loops join, yet join order remains an independent decision. To specify order as well, combine them:

~~~sql
SELECT /*+ LEADING(e d) USE_NL(d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.employee_id BETWEEN 1000 AND 1010;
~~~

`LEADING(e d)` guides join order starting with `E` then `D`; `USE_NL(d)` guides the join method with `D` as the inner side. You still must verify the optimizer accepted both hints.

### 9.1 LEADING versus ORDERED

`LEADING` specifies order by aliases. `ORDERED` takes order from the `FROM` clause. Do not use both simultaneously to control the same decision; `ORDERED` causes `LEADING` to be ignored.

`LEADING` is usually clearer when you want to keep the `FROM` clause logically structured while specifying join order.

### 9.2 USE_NL does not create an index

If the inner row source lacks a suitable access path, nested loops may scan lots of data for every outer row. The `USE_NL` hint does not build an index or make inner lookups cheaper.

## 10. Controlling access paths

### 10.1 FULL

~~~sql
SELECT /*+ FULL(o) */
       o.order_id,
       o.order_date
FROM orders o
WHERE o.status = 'OPEN';
~~~

`FULL` directs the optimizer to read the table via a full table scan for alias `O`. This makes sense when reading most of the table or when available indexes are inefficient.

### 10.2 INDEX

~~~sql
SELECT /*+ INDEX(o ix_orders_status) */
       o.order_id
FROM orders o
WHERE o.status = 'CANCELLED';
~~~

`INDEX` directs the optimizer to use the specified index if possible. If the predicate matches most rows and requires many non-indexed columns, table access by rowid can be costly.

### 10.3 INDEX_DESC

~~~sql
SELECT /*+ INDEX_DESC(o ix_orders_date) */
       o.order_id,
       o.order_date
FROM orders o
WHERE o.customer_id = :customer_id;
~~~

`INDEX_DESC` steers toward scanning an index in descending order where applicable. Verify index key order and predicates; the hint does not guarantee ordered SQL output if the query lacks `ORDER BY`.

### 10.4 NO_INDEX

`NO_INDEX` directs the optimizer not to use the specified index for applicable access paths. Use with caution as it can eliminate a helpful access path for other values or workloads.

### 10.5 Hints do not replace index design

If a query filters on `CUSTOMER_ID` and `ORDER_DATE`, a composite index may fit far better than a single-column index. An `INDEX` hint cannot fix poor index column order, bad clustering factor, or non-sargable predicates.

## 11. Controlling query transformations

The optimizer can transform SQL to produce better plans. Common transformations include:

- View merging.
- Predicate pushing.
- Subquery unnesting.
- OR expansion.
- Query rewrite.
- Join elimination where eligible.

Hints can influence several of these transformations.

### 11.1 MERGE and NO_MERGE

Inline view:

~~~sql
SELECT q.customer_id,
       q.order_count
FROM (
    SELECT o.customer_id,
           COUNT(*) AS order_count
    FROM orders o
    GROUP BY o.customer_id
) q;
~~~

`NO_MERGE`:

~~~sql
SELECT /*+ NO_MERGE(q) */
       q.customer_id,
       q.order_count
FROM (
    SELECT o.customer_id,
           COUNT(*) AS order_count
    FROM orders o
    GROUP BY o.customer_id
) q;
~~~

`NO_MERGE` steers the optimizer to keep the inline view as a separate query block where applicable. This can preserve aggregation boundaries or aid targeted tuning, yet can also prevent predicate pushing or more efficient operator combinations.

### 11.2 UNNEST and NO_UNNEST

`EXISTS` subquery:

~~~sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

The optimizer can unnest the subquery into a semijoin. `UNNEST` or `NO_UNNEST` can influence this transformation where applicable.

Do not assume unnesting is always good or always bad. Inspect query blocks, cardinality, and join methods after transformation.

### 11.3 Predicate pushing

Predicate pushing moves conditions from an outer query block into a view/subquery to reduce rows earlier. `PUSH_PRED`/`NO_PUSH_PRED` hints can influence this in certain cases.

Do not block predicate pushing without measuring. Keeping an inline view unpushed may force far more rows to be processed.

## 12. Hints for DML

Hints can appear in `INSERT`, `UPDATE`, `DELETE`, and `MERGE`.

Direct-path insert example:

~~~sql
INSERT /*+ APPEND */
INTO order_archive
SELECT *
FROM orders
WHERE order_date < DATE '2025-01-01';
~~~

`APPEND` requests direct-path insert where supported. Direct-path insert has segment, locking, and transaction rules different from conventional inserts; evaluate impacts on concurrent access and commits.

You can also place hints on the `SELECT` query block of an `INSERT`:

~~~sql
INSERT INTO order_archive
SELECT /*+ FULL(o) */
       o.*
FROM orders o
WHERE o.order_date < DATE '2025-01-01';
~~~

Hints after `SELECT` affect the reading query block. Hints after `INSERT` affect the `INSERT` target. Do not confuse the two scopes.

## 13. Hints in subqueries and correlated subqueries

Example:

~~~sql
SELECT /*+ QB_NAME(q_main) */
       c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT /*+ QB_NAME(q_exists) INDEX(o ix_orders_customer) */
           1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
~~~

The `INDEX` hint sits in query block `q_exists` and references that block's alias `O`. The optimizer may unnest the subquery; inspect transformations and the hint report to confirm whether the hint still applies as intended.

To test keeping the subquery separate, try `NO_UNNEST` inside the inner block, but benchmark because preventing transformations can yield a worse plan.

## 14. Hint conflicts and ignored hints

A SQL statement can contain conflicting hints:

~~~sql
SELECT /*+ FULL(e) INDEX(e ix_employees_department) */
       e.employee_id
FROM employees e
WHERE e.department_id = 10;
~~~

`FULL(e)` and `INDEX(e ...)` prescribe opposing access paths for the same row source. Never rely on hint order to guess which one Oracle will pick. Conflicts can cause one or more hints to be ignored.

Common causes:

- Invalid hint syntax.
- Nonexistent alias or wrong scope.
- Wrong query block name.
- Hint incompatible with join or predicate type.
- Conflicting hints.
- Query transformation altered the hinted target.
- Hint inapplicable due to SQL structure or version limits.
- Hint placed in the wrong position.

### 14.1 Do not throw many hints randomly

Adding a pile of hints makes it hard to tell which hint altered the plan. Test systematically:

1. Capture baseline.
2. Add one targeted hint.
3. Inspect the hint report.
4. Compare plans and runtime.
5. Keep or drop the hint based on numbers.

## 15. Verifying hints with DBMS_XPLAN

This is the most critical step of the lesson. Always inspect the executed cursor rather than looking only at SQL source.

### 15.1 Collecting runtime statistics

Attach `GATHER_PLAN_STATISTICS` to the query:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS USE_NL(d) LEADING(e d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.employee_id BETWEEN 1000 AND 1010;
~~~

Fetch all rows so runtime statistics on the cursor are fully recorded.

### 15.2 Viewing the current cursor

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +ALIAS +OUTLINE +HINT_REPORT'
    )
);
~~~

Format meanings:

- `ALLSTATS LAST`: shows runtime statistics for the latest execution when stats are available.
- `ALIAS`: shows alias/query block details associated with operations.
- `OUTLINE`: shows outline hints capable of reproducing the plan.
- `HINT_REPORT`: shows the status of hints Oracle parsed in the cursor, on supported versions.

Support for `HINT_REPORT` depends on Oracle version. If your environment does not support it yet, use available `DBMS_XPLAN` format options and consult your release documentation.

### 15.3 Viewing a specific SQL_ID and child cursor

When a session runs multiple SQL statements, `NULL/NULL` may not point to the cursor you want to inspect. Locate the `SQL_ID`:

~~~sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       sql_text
FROM v$sql
WHERE sql_text LIKE '%ORDERS%'
ORDER BY last_active_time DESC;
~~~

Then:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        sql_id          => :sql_id,
        cursor_child_no => :child_number,
        format          => 'ALLSTATS LAST +ALIAS +OUTLINE +HINT_REPORT'
    )
);
~~~

`V$SQL` holds cursors currently in the shared pool; entries can vanish if aged out or if the shared pool changes. Privileges on performance views are required.

### 15.4 What does Hint Report reveal?

The hint report helps distinguish:

- Used hints.
- Unused hints.
- Unresolved aliases/query blocks.
- Syntax errors or invalid hints.
- Overridden/conflicting hints in a specific context.

Exact wording and status codes vary by version. Read the report section in the output instead of guessing just because the plan contains a similar operation.

### 15.5 Seeing a matching operation in the plan is not enough proof

For example, source contains `INDEX(e ix_emp_dept)` and the plan shows `INDEX RANGE SCAN`. The optimizer might have picked that index on its own even without the hint.

Conversely, if the plan shows `FULL SCAN` while source has an `INDEX` hint, the hint may have failed to resolve, been inapplicable, or had another conflict. Always read the hint report, aliases, query blocks, and outline.

## 16. OUTLINE differs from HINT_REPORT

These two sections are often confused:

**HINT_REPORT** answers: how were the hints supplied in the SQL parsed and used?

**OUTLINE** shows the set of optimizer hints/directives that can reproduce the current execution plan. The outline is not simply a verbatim echo of the hint comments written in source.

A plan generated by the optimizer with zero user hints still has an outline containing internal hints describing the plan decisions.

Therefore:

- Use `HINT_REPORT` to investigate hints written in SQL.
- Use `OUTLINE` to study how to reproduce a plan.
- Use `ALLSTATS LAST` to examine runtime rows and resource usage.
- Use `SQL_ID`/child number to make sure you are viewing the right cursor.

## 17. ALIAS and query blocks in DBMS_XPLAN

The `ALIAS` format shows table aliases and query blocks attached to operations. This is essential when hints span multiple blocks.

When a hint goes unused, verify:

1. Does the alias in source match the alias in the plan?
2. Is the query block name accurate?
3. Was the query block merged or unnested?
4. Was the hint placed in the right query block's comment?
5. Do cross-block hints use the exact `@query_block` syntax?

For complex queries, assigning clear `QB_NAME`s to key blocks makes reading plans and hint reports much easier.

## 18. EXPLAIN PLAN is not final proof

`EXPLAIN PLAN`:

~~~sql
EXPLAIN PLAN FOR
SELECT /*+ USE_HASH(d) */
       e.employee_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` builds an estimated plan in the explain context. It does not show runtime `A-Rows`, actual buffers, or full details of executed production cursors.

Actual plans can differ due to:

- Bind peeking.
- Child cursors.
- Optimizer environment.
- Differing statistics.
- Session settings.
- Adaptive cursor behavior.
- Differing SQL text or schemas.

To confirm a hint applied to live SQL, obtain the `SQL_ID`/child cursor and use `DISPLAY_CURSOR`.

## 19. Bind variables and hints

A hint locking an access path or join method may not suit every bind value.

Example:

~~~sql
SELECT /*+ USE_NL(c) */
       o.order_id,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = :status;
~~~

If `STATUS = 'CANCELLED'` has only 0.1% of rows, nested loops may be great. If `STATUS = 'OPEN'` has 95% of rows, the same hint forces inner lookups to loop massively.

When evaluating hints with binds:

- Test both common and rare values.
- Inspect child cursors.
- Check `IS_BIND_SENSITIVE` and `IS_BIND_AWARE` in `V$SQL` when authorized.
- Inspect peeked binds in the plan if present.
- Measure elapsed time, CPU, buffers, and `A-Rows`.

`PEEKED_BINDS` shows bind values peeked during hard parse for that cursor, not a log of every bind value from every execution.

Do not add permanent hints based on a single bind value if the SQL spans multiple selectivity regimes.

## 20. Hints and adaptive behavior

The optimizer can use adaptive mechanisms depending on release and settings, such as adaptive plans or adaptive cursor sharing. Some decisions can adjust based on runtime feedback or bind selectivity.

When investigating:

- Note the Oracle release.
- Check actual plans and child cursors.
- Check the hint report.
- Inspect adaptive plan details if available.
- Never assume an initially displayed plan represents full runtime behavior.

Hints can restrict the optimizer's search space. If a hint conflicts with adaptive goals or transformations, verify results in the live target environment.

## 21. Targeted hint selection guide

Before adding a hint, identify the problem:

| Observed issue | Hint group to test | What to verify |
|---|---|---|
| Suboptimal access path | `FULL`, `INDEX`, `INDEX_FFS` | Buffers, reads, rows, and timing |
| Suboptimal join method | `USE_NL`, `USE_HASH`, `USE_MERGE` | Cardinality, Starts, TEMP, CPU |
| Suboptimal join order | `LEADING` or `ORDERED` | Intermediate row sources and join order |
| Inline view merged unexpectedly | `NO_MERGE` | Predicate pushdown and cardinality |
| Subquery transformation hurts plan | `UNNEST`/`NO_UNNEST` | Semijoin/antijoin and row counts |
| Need runtime inspection | `GATHER_PLAN_STATISTICS` | A-Rows, Starts, buffers |
| Need to test parallelism | `PARALLEL` | Throughput, CPU, PGA, TEMP, and concurrency |

This table is only a starting guide. Suitable hints still depend on the specific SQL and version.

## 22. End-to-end hint verification workflow

A repeatable tuning process:

### Step 1: Capture baseline

Record:

- Original SQL text.
- `SQL_ID` and child number if executed.
- Representative bind values.
- Current plan.
- `E-Rows`/`A-Rows`.
- Buffers, reads, CPU, and elapsed time.
- Optimizer environment and relevant statistics.

### Step 2: State a hypothesis

Example:

- The outer row source actually has only 20 rows.
- The optimizer picked hash join, yet hash build costs more than indexed lookup.
- An index on the inner join key could make nested loops cheaper.

Hypotheses must be grounded in plan/runtime data.

### Step 3: Add a minimal hint set

Example:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS LEADING(o c) USE_NL(c) */
       o.order_id,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = :status;
~~~

Do not combine `FULL`, `INDEX`, `PARALLEL`, and multiple transformation hints simultaneously without clear cause.

### Step 4: Check the hint report

Use `DISPLAY_CURSOR` with `+HINT_REPORT` and `+ALIAS`. Verify:

- Hints were recognized.
- Aliases match.
- Query blocks match.
- Hints were used or unused.
- No conflicts or unresolved targets exist.

### Step 5: Inspect the actual plan

Check operations:

- `NESTED LOOPS`/`HASH JOIN`/`MERGE JOIN`.
- Access path for each row source.
- Join order.
- `E-Rows`/`A-Rows`.
- `Starts`.
- `Buffers` and `TEMP`.

### Step 6: Measure multiple runs

Run with:

- Common bind values.
- Rare bind values.
- Small/medium/large inputs.
- Representative concurrency.

Compare median/p95 where appropriate; never conclude from a single run.

### Step 7: Regression testing

Verify:

- SQL output is unchanged.
- No dropped or duplicated rows.
- `NULL` semantics unchanged.
- Transactions and locking unchanged.
- Related workloads suffer no regressions.

### Step 8: Decide whether to keep or remove

Keep hints only when gains are measurable, stable, clearly scoped, and owned by someone monitoring after data/statistics shift.

## 23. Complete example: verifying hints on a multi-table query

Suppose an application fetches orders by status and joins customers:

~~~sql
SELECT /*+ QB_NAME(q_main)
           GATHER_PLAN_STATISTICS
           LEADING(o c)
           USE_NL(c)
           INDEX(o ix_orders_status)
           INDEX(c pk_customers)
       */
       o.order_id,
       o.order_date,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = :status;
~~~

The hints:

- `QB_NAME(q_main)`: names the query block.
- `GATHER_PLAN_STATISTICS`: gathers runtime statistics.
- `LEADING(o c)`: guides join order.
- `USE_NL(c)`: guides nested loops with `C` as inner row source.
- `INDEX(o ix_orders_status)`: guides `ORDERS` access path.
- `INDEX(c pk_customers)`: guides `CUSTOMERS` access path.

After executing and fetching all rows:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +ALIAS +OUTLINE +PEEKED_BINDS +HINT_REPORT'
    )
);
~~~

Reading the output:

1. Hint report confirms how each hint was parsed/applied.
2. `ALIAS` confirms query block and aliases.
3. Operation tree confirms join method and access paths.
4. `E-Rows`/`A-Rows` show whether estimates match reality.
5. `Starts` and `Buffers` reveal inner lookup iteration cost.
6. `PEEKED_BINDS` shows binds peeked at hard parse if present.

If a common `STATUS` matches hundreds of thousands of orders, nested loops may perform poorly. Test other values or drop the hints to let the optimizer choose appropriately.

## 24. Complex query blocks: inline views and subqueries

Example query:

~~~sql
SELECT /*+ QB_NAME(q_main) */
       c.customer_id,
       q.total_amount
FROM customers c
JOIN (
    SELECT /*+ QB_NAME(q_order_totals) */
           o.customer_id,
           SUM(o.order_amount) AS total_amount
    FROM orders o
    WHERE o.order_date >= DATE '2026-01-01'
    GROUP BY o.customer_id
) q
  ON q.customer_id = c.customer_id
WHERE c.status = 'ACTIVE';
~~~

When tuning:

- Hints on `C` belong to `q_main`.
- Hints on `O` belong to `q_order_totals`.
- Alias `Q` is the inline view row source in `q_main`.
- Query transformations may merge or reshape the view if allowed.

To test keeping the inline view boundary:

~~~sql
SELECT /*+ QB_NAME(q_main) NO_MERGE(q) */
       c.customer_id,
       q.total_amount
FROM customers c
JOIN (
    SELECT /*+ QB_NAME(q_order_totals) */
           o.customer_id,
           SUM(o.order_amount) AS total_amount
    FROM orders o
    WHERE o.order_date >= DATE '2026-01-01'
    GROUP BY o.customer_id
) q
  ON q.customer_id = c.customer_id
WHERE c.status = 'ACTIVE';
~~~

Compare plans with and without `NO_MERGE`. Preventing merging is not always better; the optimizer may lose predicate-pushdown or operator-reordering opportunities.

## 25. Outline data and SQL Plan Management

Outline data is a set of directives describing how to reproduce the current plan. It helps DBAs understand which optimizer choices the plan relies on.

SQL Plan Management (SPM) is a mechanism for managing SQL plan baselines. It differs from embedding hints directly in SQL:

- Direct hints are written inside the SQL text.
- Outlines in `DBMS_XPLAN` describe how to reproduce a plan.
- SQL plan baselines manage accepted plans for a SQL statement via SPM.

Do not treat outline output as if it were the exact hint list authored in source. For long-term plan stability, evaluate SPM and formal plan-management processes.

## 26. Privileges and verification tools

`DBMS_XPLAN.DISPLAY_CURSOR` and `V$SQL_PLAN`/`V$SQL` may require read privileges on performance views. In application environments, accounts typically do not have broad privileges just for debugging.

You can ask a DBA to:

- Grant appropriate least-privilege read access.
- Extract plans for a `SQL_ID`/child cursor.
- Enable statistics in a session/test environment.
- Provide the Hint Report and runtime metrics.

Never grant `DBA` or `SELECT ANY DICTIONARY` to an application user solely to read execution plans.

## 27. Common mistakes with hints and query blocks

| Mistake | Consequence | Fix |
|---|---|---|
| Writing `/* + HINT */` | Not a valid hint comment | Write `/*+ HINT */` |
| Placing hints after `FROM` | Ignored due to wrong placement | Place right after query/DML block keyword |
| Using table name instead of alias | Hint fails to resolve row source | Use the alias from `FROM` |
| Using another block's alias | Hint cannot find target | Match query block and alias |
| Relying long-term on `SEL$1` | Internal names can shift | Assign explicit `QB_NAME` |
| Using `USE_NL` without join order control | Inner/driving roles may be unexpected | Pair with `LEADING` when justified |
| Using `LEADING` and `ORDERED` together | Join order hints conflict; `ORDERED` overrides `LEADING` | Choose one mechanism |
| Thinking `INDEX` hint guarantees speed | Index lookups can incur heavy rowid I/O | Measure buffers/elapsed time |
| Adding many hints at once | Hard to tell which hint made the difference | Test small incremental groups |
| Checking only plan operations to confirm hints | Optimizer may pick the same plan naturally | Inspect `HINT_REPORT` |
| Looking only at `EXPLAIN PLAN` | Misses full runtime cursor state | Use `DISPLAY_CURSOR` |
| Confusing `OUTLINE` with `HINT_REPORT` | Mixes up source hint status and plan reproduction | Read each section for its own purpose |
| Testing only one bind value | Plan may perform poorly for other values | Test common and rare binds |
| Leaving hints forever after data shifts | Stale hints can cause plan regressions | Monitor and review periodically |
| Blocking all query transformations | Loses optimization opportunities | Only block with hypothesis and metrics |

## 28. Self-check practice exercises

Run exercises in a test schema using the same dataset when comparing.

### Exercise 1 — Hint comments

Write one `SELECT` with a `FULL` hint and one `SELECT` with a normal comment. Inspect plans and explain the special hint comment syntax.

### Exercise 2 — Aliases

Write a self-join on `EMPLOYEES` with aliases `E` and `M`. Use `USE_NL(M)` and check the hint report. Try referencing the table name instead of the alias and record the result.

### Exercise 3 — Access paths

Compare no hint, `FULL(E)`, and `INDEX(E index_name)`. Measure buffers, reads, and elapsed time under high and low selectivity predicates.

### Exercise 4 — Join methods

Compare `USE_NL`, `USE_HASH`, and `USE_MERGE` on the same equijoin. Inspect join operations and the hint report.

### Exercise 5 — Join order

Build a three-table query. Test `LEADING(a b c)` and `LEADING(c a b)`. Inspect the plan tree and intermediate cardinalities.

### Exercise 6 — LEADING and ORDERED

Write a query containing both hints. Inspect the hint report to observe conflict/precedence. Then remove one hint and compare.

### Exercise 7 — QB_NAME

Create a query with an inline view and an `EXISTS` subquery. Name each block with `QB_NAME` and read the `ALIAS` section in `DBMS_XPLAN`.

### Exercise 8 — Cross-query-block hints

Use a query-block-qualified hint to target an alias inside an inline view. Verify the exact query block and alias in the hint report.

### Exercise 9 — NO_MERGE

Compare plans for an inline view without hints and with `NO_MERGE`. Observe predicate pushdown, cardinality, and intermediate rows.

### Exercise 10 — HINT_REPORT and OUTLINE

Run a query containing a valid hint, an invalid-alias hint, and conflicting hints. Compare `HINT_REPORT` with `OUTLINE`.

### Exercise 11 — Bind values

Run the same SQL with rare and common binds. Observe child cursors, peeked binds, join methods, and runtime.

### Exercise 12 — End-to-end verification

Pick a slow SQL, save baseline, state a hypothesis, add one hint, verify the hint report, compare actual plans, and benchmark multiple runs. Document why you keep or drop the hint.

## 29. Pre-production checklist for hints

**Syntax and scope**

- Does the hint comment start with `/*+ ... */` immediately after the keyword?
- Are hints for the same query block grouped properly?
- Do aliases match `FROM` exactly?
- Are `QB_NAME` labels added where needed?
- Do cross-block hints reference the exact query block and alias?

**Applicability**

- Is the hint compatible with query transformations?
- Are there conflicting hints?
- Are `LEADING` and `ORDERED` mixed?
- Do `USE_NL`/`USE_HASH`/`USE_MERGE` name the proper inner row source?
- What status does the hint report show?

**Plan verification**

- Are you inspecting the exact `SQL_ID` and child cursor?
- Did you check the actual plan with `DISPLAY_CURSOR`?
- Is `ALLSTATS LAST` included?
- Did you read `ALIAS`, `OUTLINE`, and `HINT_REPORT`?
- Are `E-Rows`/`A-Rows`, `Starts`, `Buffers`, and `TEMP` reasonable?

**Performance and stability**

- Were both common and rare bind values tested?
- Were multiple benchmark runs measured?
- Was concurrency tested?
- Are SQL results identical?
- Are there regressions on related workloads?
- Is there an owner monitoring when data/statistics evolve?

## 30. Summary takeaways

| Concept | Key takeaway |
|---|---|
| Optimizer hint | Directive in a special comment to influence plan selection |
| Hint comment | Starts with `/*+` and sits right after the query/DML block keyword |
| Alias | Row source name that must be used accurately in hints |
| Query block | `SELECT`/subquery unit analyzed by the optimizer |
| `QB_NAME` | Names a query block for unambiguous targeting |
| `@query_block` | Syntax for targeting another query block in supported hints |
| `FULL`/`INDEX` | Directs access path |
| `USE_NL`/`USE_HASH`/`USE_MERGE` | Directs join method |
| `LEADING` | Directs join order by alias |
| `ORDERED` | Directs join order by `FROM` order; conflicts with `LEADING` |
| `NO_MERGE`/`MERGE` | Controls view merging |
| `UNNEST`/`NO_UNNEST` | Controls subquery unnesting |
| `GATHER_PLAN_STATISTICS` | Collects runtime plan statistics |
| `HINT_REPORT` | Verifies parsed hint status |
| `ALIAS` | Inspects aliases and query blocks in the plan |
| `OUTLINE` | Shows directives to reproduce a plan, distinct from hint report |
| `DISPLAY_CURSOR` | Views the actual executed cursor's plan |
| `EXPLAIN PLAN` | Estimated plan; does not replace runtime cursors |

Hints are targeted tuning tools. Place hints in the right query block, use accurate aliases, and name complex query blocks with `QB_NAME`. `LEADING` guides join order, `USE_NL`/`USE_HASH`/`USE_MERGE` guide join methods, and `FULL`/`INDEX` guide access paths; these groups do not substitute for one another. Most importantly, verify the executed cursor with `DBMS_XPLAN`, inspect `HINT_REPORT`, `ALIAS`, `OUTLINE`, and runtime statistics. Keep a hint only when benchmarks demonstrate measurable gains across representative bind values and workloads, backed by a plan to monitor as data or statistics change.
