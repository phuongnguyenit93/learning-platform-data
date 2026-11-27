# Separating Analytic Result Filtering and Checking Version-Specific Syntax

In Oracle Database, *analytic functions* such as ROW_NUMBER, RANK, DENSE_RANK, SUM OVER, LAG, and LEAD are evaluated over a query block's row set after FROM, WHERE, GROUP BY, and HAVING have been processed. Consequently, results produced by analytic functions generally cannot be filtered directly using WHERE in the same query block.

To filter rows based on analytic results, understand two ways to write the query:

- **Compatible with older Oracle versions:** compute the analytic function inside an inline view or common table expression (CTE), then filter the result column in the outer query block.
- **Concise syntax in Oracle AI Database 26ai:** use the **QUALIFY** clause, which is processed after analytic functions and before ORDER BY/FETCH FIRST.

The key point of this lesson is separating SQL processing stages accurately, choosing syntax compatible with the target database, and verifying the release/RU before introducing QUALIFY into an application. Syntax support cannot be inferred solely from the version of SQL Developer, the JDBC driver, or the IDE in use; the SQL statement is parsed by the database server that the connection actually points to.

## 1. Why Can't Analytic Results Be Filtered by WHERE at the Same Level?

Suppose you want the highest-paid employee in each department:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees
WHERE rn = 1;
~~~

The SQL statement above is invalid because RN is an alias created from an analytic expression in the SELECT list. The WHERE clause of the same query block is processed before the analytic function produces RN. At the moment WHERE runs, RN does not yet exist in that query block's scope.

Logical processing order model:

~~~text
FROM / JOIN
     |
WHERE                  -- filter source rows
     |
GROUP BY               -- form groups if present
     |
HAVING                 -- filter groups
     |
Analytic functions     -- compute ROW_NUMBER, RANK, SUM OVER...
     |
QUALIFY                -- if supported by version
     |
DISTINCT
     |
ORDER BY
     |
FETCH FIRST            -- limit final rows
~~~

This is a logical model for understanding semantics. The optimizer may transform the physical execution plan, yet the query result must still conform to the semantic order of the clauses.

### 1.1. WHERE and Analytic Functions Have Two Different Roles

WHERE selects the **input** row set for the analytic function:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees
WHERE active_flag = 'Y';
~~~

Only active employees participate in numbering. If a department's highest-paid employee has left the company, the top active employee receives RN = 1.

If you want to rank all employees first and then display only active ones, compute the ranking first and filter ACTIVE in the outer query block. These two business requirements are different; placing WHERE in the wrong position changes the result.

### 1.2. You Cannot Arbitrarily Replace WHERE with HAVING

HAVING filters groups produced by GROUP BY. It is not a general clause for filtering analytic results in the same query block.

Valid example:

~~~sql
SELECT department_id,
       AVG(salary) AS avg_salary
FROM employees
GROUP BY department_id
HAVING AVG(salary) > 20000000;
~~~

HAVING filters by each group's aggregate. If you want to rank groups by AVG(SALARY) and then take only the top three groups, you must use an outer query block or QUALIFY on a supported version.

## 2. Broadly Compatible Approach: Inline View

An inline view is a subquery in the FROM clause. The inner query block computes the analytic function; the outer query block treats the analytic result as a regular column and filters it with WHERE.

~~~sql
SELECT employee_id,
       department_id,
       salary,
       rn
FROM (
    SELECT e.employee_id,
           e.department_id,
           e.salary,
           ROW_NUMBER() OVER (
               PARTITION BY e.department_id
               ORDER BY e.salary DESC NULLS LAST,
                        e.employee_id
           ) AS rn
    FROM employees e
)
WHERE rn = 1
ORDER BY department_id NULLS LAST;
~~~

The structure has two stages:

1. The inner query block computes RN for each employee.
2. The outer query block keeps rows where RN = 1.

This approach works across many Oracle generations, including 19c and 21c systems, and continues to work on newer releases. When building applications that must run across multiple database versions, an inline view is a strong compatibility choice.

### 2.1. An Inline View Can Filter Top-N Within Each Partition

~~~sql
SELECT department_id,
       employee_id,
       full_name,
       salary,
       rn
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

Each department returns at most three employees. Because ROW_NUMBER is computed in the inner query block, the RN <= 3 condition is applied in the outer query block.

If you need to keep all tied employees at the boundary, replace ROW_NUMBER with RANK. If you want the top N distinct salary levels, use DENSE_RANK. Splitting query blocks does not change the meaning of the ranking function.

### 2.2. Filtering Analytic Results by Alias in the Outer Query Block

The RN alias is scoped only to the inner query block's SELECT list. The outer query block can reference it as a column of the inline view:

~~~sql
SELECT ranked.employee_id,
       ranked.salary,
       ranked.rn
FROM (
    SELECT employee_id,
           salary,
           ROW_NUMBER() OVER (
               ORDER BY salary DESC NULLS LAST, employee_id
           ) AS rn
    FROM employees
) ranked
WHERE ranked.rn <= 10;
~~~

Alias the inline view and qualify column names when a query has multiple data sources. This avoids confusion over RN or duplicate column names.

## 3. Using a CTE to Separate Steps Clearly

A CTE is declared in a WITH clause, letting you name intermediate query blocks. In terms of analytic filtering semantics, a CTE plays the same role as an inline view.

~~~sql
WITH ranked_employees AS (
    SELECT e.employee_id,
           e.department_id,
           e.full_name,
           e.salary,
           ROW_NUMBER() OVER (
               PARTITION BY e.department_id
               ORDER BY e.salary DESC NULLS LAST,
                        e.employee_id
           ) AS rn
    FROM employees e
)
SELECT employee_id,
       department_id,
       full_name,
       salary,
       rn
FROM ranked_employees
WHERE rn <= 3
ORDER BY department_id NULLS LAST, rn;
~~~

CTEs are useful when:
- A query has multiple transformation steps.
- The same intermediate dataset is referenced multiple times.
- You want a meaningful name for the ranked result.
- Source filtering must be separated from analytic result filtering.
- A long SQL statement needs to be readable and maintainable.

### 3.1. A CTE Does Not Guarantee Creating a Temporary Table

A CTE is a way of organizing query blocks. The Oracle optimizer may inline/merge or materialize it depending on the query, hints, and cost. Do not assume every CTE is written to TEMP as a physical table.

When performance matters, inspect the execution plan and runtime statistics rather than inferring behavior from the WITH syntax.

### 3.2. Multiple Analytic Stages Can Use Multiple CTEs

For example, first compute rankings within each department, then count the selected people per department:

~~~sql
WITH ranked AS (
    SELECT e.department_id,
           e.employee_id,
           e.salary,
           ROW_NUMBER() OVER (
               PARTITION BY e.department_id
               ORDER BY e.salary DESC NULLS LAST, e.employee_id
           ) AS rn
    FROM employees e
),
top_people AS (
    SELECT department_id,
           employee_id,
           salary
    FROM ranked
    WHERE rn <= 3
)
SELECT department_id,
       COUNT(*) AS selected_count,
       AVG(salary) AS selected_avg_salary
FROM top_people
GROUP BY department_id
ORDER BY department_id;
~~~

The first query block computes rankings; the second query block filters the top three; the final query block aggregates the filtered results. This style makes the boundary between analytic calculation and aggregate calculation explicit.

## 4. QUALIFY in Oracle AI Database 26ai

Oracle AI Database 26ai supports the **QUALIFY** clause to filter analytic function results within the same SELECT query block. In role, QUALIFY is to analytic functions what HAVING is to GROUP BY.

Example for the top employee per department:

~~~sql
SELECT employee_id,
       department_id,
       full_name,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees
QUALIFY rn = 1
ORDER BY department_id NULLS LAST;
~~~

QUALIFY is processed after analytic functions. Therefore RN has already been calculated when the condition RN = 1 is evaluated.

You can also write the analytic function directly inside the predicate:

~~~sql
SELECT employee_id,
       department_id,
       salary
FROM employees
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC NULLS LAST, employee_id
) <= 3
ORDER BY department_id NULLS LAST, salary DESC NULLS LAST;
~~~

This syntax avoids needing an inline view solely to filter ROW_NUMBER results.

### 4.1. Position of QUALIFY in SELECT

In Oracle AI Database 26ai, QUALIFY appears after WINDOW (if present) and before ORDER BY and FETCH FIRST.

Ordering model:

~~~text
SELECT
FROM / JOIN
WHERE
GROUP BY
HAVING
WINDOW
QUALIFY
DISTINCT
ORDER BY
FETCH FIRST
~~~

If no named WINDOW clause is used, QUALIFY still comes after HAVING and before ORDER BY.

Example:

~~~sql
SELECT employee_id,
       salary,
       RANK() OVER (ORDER BY salary DESC NULLS LAST) AS salary_rank
FROM employees
QUALIFY salary_rank <= 5
ORDER BY salary_rank, employee_id
FETCH FIRST 20 ROWS ONLY;
~~~

The query:
1. Computes SALARY_RANK.
2. Retains rows with rank no greater than 5.
3. Sorts the results.
4. Limits the final output to at most 20 rows.

FETCH FIRST at the end may cut off some of the tied rows that QUALIFY retained. If the requirement is to keep all tied rows, reconsider the final row-limiting clause.

### 4.2. QUALIFY Can Reference Analytic Aliases

Example:

~~~sql
SELECT employee_id,
       salary,
       ROW_NUMBER() OVER (
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees
QUALIFY rn <= 10;
~~~

In Oracle AI Database 26ai, QUALIFY can filter on an analytic expression alias from the SELECT list or use an analytic expression directly inside the predicate.

Using an alias avoids repeating the analytic expression. If an alias matches a source column name or is a quoted/case-sensitive identifier, choose a clear, unambiguous alias.

### 4.3. QUALIFY Does Not Replace WHERE

WHERE filters source rows before the analytic function runs. QUALIFY filters rows after the analytic function runs.

Example ranking only ACTIVE employees:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees
WHERE active_flag = 'Y'
QUALIFY rn = 1;
~~~

Inactive employees do not participate in ranking.

If you want to rank all employees and then display only ACTIVE employees who ranked first, the ACTIVE condition must be applied in an outer query block:

~~~sql
WITH ranked AS (
    SELECT e.employee_id,
           e.department_id,
           e.salary,
           e.active_flag,
           ROW_NUMBER() OVER (
               PARTITION BY e.department_id
               ORDER BY e.salary DESC NULLS LAST, e.employee_id
           ) AS rn
    FROM employees e
)
SELECT employee_id, department_id, salary
FROM ranked
WHERE active_flag = 'Y'
  AND rn = 1;
~~~

In the second query, RN is computed across all employees before filtering ACTIVE. If the highest-paid employee has left the company, that department may return zero rows. This is a critical business-logic distinction.

### 4.4. QUALIFY Does Not Replace HAVING

HAVING filters aggregated groups; QUALIFY filters analytic results after GROUP BY/HAVING have been processed.

Example ranking departments by total salary:

~~~sql
SELECT department_id,
       SUM(salary) AS total_salary,
       DENSE_RANK() OVER (
           ORDER BY SUM(salary) DESC NULLS LAST
       ) AS salary_level
FROM employees
GROUP BY department_id
HAVING COUNT(*) >= 5
QUALIFY salary_level <= 3
ORDER BY salary_level, department_id;
~~~

Steps:
- GROUP BY produces one row per department.
- HAVING retains departments with at least five employees.
- DENSE_RANK ranks the remaining departments by total salary.
- QUALIFY retains the top three distinct total salary tiers.

On versions that do not support QUALIFY, wrap the GROUP BY query block, compute DENSE_RANK in an inline view, and filter SALARY_LEVEL outside.

## 5. Oracle Version Compatibility Table

Key milestone to remember: **QUALIFY was introduced by Oracle in Oracle AI Database 26ai**, and is not syntax you can assume works on every database branded 23ai.

| Database release | Filter analytic results in same query block with QUALIFY | Recommended approach |
| --- | --- | --- |
| Oracle Database 19c | Not supported | Inline view or CTE |
| Oracle Database 21c | Not supported | Inline view or CTE |
| Oracle Database 23ai prior to RU 23.26.0 | Not supported | Inline view or CTE |
| Oracle AI Database 26ai, RU 23.26.0 branch and later | Supported | QUALIFY or inline view/CTE |

Oracle announced QUALIFY in the Oracle AI Database 26ai New Features documentation. The Oracle Database 21c SQL Language Reference describes filtering analytic results by nesting the query in a subquery and filtering in the parent query. Therefore, do not take a QUALIFY example from 26ai documentation and run it verbatim on 19c, 21c, or a pre-support 23ai database.

### 5.1. Release Names and RU Numbers Can Be Confusing

Oracle renamed the 23ai branch to Oracle AI Database 26ai starting with RU 23.26.0. You may encounter:
- Product name displayed as 26ai.
- Version/RU number formatted as 23.26.0...
- Older docs referencing 23ai while newer docs reference 26ai.

When verifying syntax support, read both the release name and the actual version/RU. Do not infer support solely from a major number shown in an administration UI.

### 5.2. Client Version Does Not Determine Server Syntax

An application may use:
- A newer SQL Developer version.
- JDBC driver 23.x or 26.x.
- An IDE with modern syntax highlighting.
- A modern ORM framework.

Yet if it connects to a 19c database, the 19c database parser still rejects QUALIFY. Conversely, an older client may fail to highlight new syntax supported by a newer database, even though the server can parse the SQL statement.

Verify the database service/instance that the application actually connects to, not just the tooling version.

## 6. Checking Version and Release Update

Before using new syntax, inspect the target database.

### 6.1. Check the Version Banner

~~~sql
SELECT banner
FROM v$version
WHERE banner LIKE 'Oracle Database%';
~~~

V$VERSION typically provides product name and release info. Privileges to query dynamic performance views depend on configuration and grants assigned to the user.

Another query:

~~~sql
SELECT product,
       version,
       status
FROM product_component_version
WHERE product LIKE 'Oracle Database%';
~~~

PRODUCT_COMPONENT_VERSION can be used in environments where the application account has privileges to read this view.

### 6.2. Check Instance Version and RU When Corresponding Columns Exist

On versions supporting VERSION_FULL:

~~~sql
SELECT version,
       version_full
FROM v$instance;
~~~

VERSION generally shows the base release; VERSION_FULL provides fuller detail useful for identifying the RU. If an older version lacks the VERSION_FULL column, that SELECT may raise an invalid identifier error; in that case use V$VERSION or a view appropriate for the running release.

### 6.3. Check COMPATIBLE

~~~sql
SELECT value
FROM v$parameter
WHERE name = 'compatible';
~~~

COMPATIBLE is a parameter governing database format/behavior compatibility under Oracle rules. Do not use COMPATIBLE instead of release/RU information to conclude whether new syntax exists. Identify the actual database binary/RU and check the corresponding documentation.

### 6.4. Check Against the Exact Service the Application Uses

In environments with multiple databases, PDBs, or services:
- Connect to the exact service that the production application will use.
- Run the version query inside that same session.
- In RAC or rolling-update environments, confirm target instances/services are uniform per operational plans.
- If development, test, and production are on different RUs, test the SQL on each environment.

A QUALIFY query running on local 26ai does not prove that production 19c can run it.

## 7. Safely Testing QUALIFY Syntax

Once you know the server is Oracle AI Database 26ai, you can test a non-mutating SELECT:

~~~sql
SELECT dummy,
       ROW_NUMBER() OVER (ORDER BY dummy) AS rn
FROM dual
QUALIFY rn = 1;
~~~

This query reads DUAL and filters the analytic result. If the parser accepts QUALIFY, that signals syntax support in the current database session.

If an older server does not support it, the parser raises a syntax error, usually SQL syntax/ORA-00933 or the version's equivalent error message. Do not catch an error and automatically assume every error means QUALIFY is missing; the SQL might have another error.

### 7.1. Do Not Use UPDATE/DELETE to Test Syntax

Test syntax support using SELECT on DUAL or a sandbox table. Never run a DML statement capable of modifying data just to see if the parser recognizes a keyword.

### 7.2. A Syntax Test Does Not Replace Functional Testing

A successful test SELECT with QUALIFY only confirms the parser accepts basic syntax. You still must test:
- Aliases inside QUALIFY.
- Complex analytic expressions.
- Combined GROUP BY/HAVING.
- DISTINCT and FETCH FIRST.
- NULL semantics.
- Tie/ranking results.
- Query plans and performance.
- ORM/JDBC behavior when sending the SQL.

## 8. Writing Queries That Run Across Multiple Versions

If a single application supports Oracle 19c, 21c, 23ai, and 26ai, there are two strategies.

### 8.1. Use Inline View/CTE as the Common Syntax

~~~sql
WITH ranked_orders AS (
    SELECT o.order_id,
           o.customer_id,
           o.created_at,
           o.status,
           ROW_NUMBER() OVER (
               PARTITION BY o.customer_id
               ORDER BY o.created_at DESC NULLS LAST,
                        o.order_id DESC
           ) AS rn
    FROM orders o
    WHERE o.created_at >= :from_date
)
SELECT order_id,
       customer_id,
       created_at,
       status
FROM ranked_orders
WHERE rn = 1
ORDER BY customer_id;
~~~

This avoids depending on QUALIFY. It is appropriate when:
- The application deploys across multiple releases.
- SQL is packaged in a shared library.
- You do not want to maintain two query variants.
- Older databases require long-term support.

### 8.2. Use QUALIFY When the Target Environment Is Known

~~~sql
SELECT o.order_id,
       o.customer_id,
       o.created_at,
       o.status,
       ROW_NUMBER() OVER (
           PARTITION BY o.customer_id
           ORDER BY o.created_at DESC NULLS LAST,
                    o.order_id DESC
       ) AS rn
FROM orders o
WHERE o.created_at >= :from_date
QUALIFY rn = 1
ORDER BY customer_id;
~~~

This is shorter in Oracle AI Database 26ai. It is not automatically compatible with 19c, 21c, or 23ai RUs prior to support.

### 8.3. Select SQL by Configuration, Not by Guessing Version Strings per Request

If an application truly needs both SQL variants:
- Check database version/RU at connection pool initialization or environment configuration time.
- Map to a capability flag such as SUPPORTS_QUALIFY.
- Select the corresponding SQL from a controlled query registry.
- Never concatenate keywords or column names from user input.
- Log the release/capability for deployment diagnostics.

If the database version is managed by deployment configuration, configure the capability explicitly per environment. Avoid parsing banner strings arbitrarily on every request.

## 9. Distinguishing WHERE, HAVING, QUALIFY, and Outer WHERE

These four filter locations have distinct purposes:

| Clause | Filters on | Logical timing | Example |
| --- | --- | --- | --- |
| WHERE | Source rows | Before GROUP BY and analytics | STATUS = 'ACTIVE' |
| HAVING | Aggregated groups | After GROUP BY | COUNT(*) >= 5 |
| QUALIFY | Analytic results | After analytic functions, on 26ai | RN = 1 |
| Outer query block WHERE | Result columns of inner query block | After inner query block completes | ranked.rn = 1 |

Example including all steps on Oracle AI Database 26ai:

~~~sql
SELECT department_id,
       employee_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees
WHERE active_flag = 'Y'
QUALIFY rn <= 3
ORDER BY department_id, rn;
~~~

WHERE filters ACTIVE first; the analytic function ranks ACTIVE employees; QUALIFY keeps the top three; ORDER BY determines display order.

On Oracle 19c/21c/23ai prior to support, express the same logic with an inline view:

~~~sql
SELECT department_id, employee_id, salary, rn
FROM (
    SELECT department_id,
           employee_id,
           salary,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY salary DESC NULLS LAST, employee_id
           ) AS rn
    FROM employees
    WHERE active_flag = 'Y'
)
WHERE rn <= 3
ORDER BY department_id, rn;
~~~

## 10. Combining Multiple Analytic Conditions

QUALIFY can contain multiple logical conditions:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn,
       AVG(salary) OVER (
           PARTITION BY department_id
       ) AS department_avg
FROM employees
QUALIFY rn <= 3
    AND salary > department_avg
ORDER BY department_id, rn;
~~~

The query keeps the top three employees in each department and requires their salary to exceed the department average.

On versions without QUALIFY support, compute RN and DEPARTMENT_AVG in an inline view and place both conditions in the outer WHERE:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       rn,
       department_avg
FROM (
    SELECT e.employee_id,
           e.department_id,
           e.salary,
           ROW_NUMBER() OVER (
               PARTITION BY e.department_id
               ORDER BY e.salary DESC NULLS LAST, e.employee_id
           ) AS rn,
           AVG(e.salary) OVER (
               PARTITION BY e.department_id
           ) AS department_avg
    FROM employees e
)
WHERE rn <= 3
  AND salary > department_avg
ORDER BY department_id, rn;
~~~

You cannot use a not-yet-created analytic alias in WHERE of the same query block. An inline view exposes those results as valid input columns for the outer WHERE.

### 10.1. QUALIFY with RANK to Preserve Ties

~~~sql
SELECT employee_id,
       department_id,
       salary,
       RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST
       ) AS salary_rank
FROM employees
QUALIFY salary_rank <= 3
ORDER BY department_id, salary_rank, employee_id;
~~~

If multiple people tie at rank 3, everyone at rank 3 is kept. Do not add EMPLOYEE_ID to the analytic ORDER BY if you want to preserve salary ties; ID belongs only in the outer ORDER BY for stable display.

### 10.2. QUALIFY After Aggregates and Analytics

~~~sql
SELECT department_id,
       SUM(salary) AS total_salary,
       RANK() OVER (
           ORDER BY SUM(salary) DESC NULLS LAST
       ) AS dept_rank
FROM employees
GROUP BY department_id
HAVING COUNT(*) > 1
QUALIFY dept_rank <= 5
ORDER BY dept_rank;
~~~

HAVING removes groups with one or fewer employees before RANK ranks them. QUALIFY retains the top five ranks among the remaining groups.

If you want to rank all departments first and then display only departments with more than one employee, move the group filter to an outer query block; placing HAVING here changes the set participating in ranking.

## 11. Filtering Analytic Results and DISTINCT

In Oracle AI Database 26ai, the documented logical processing order places QUALIFY before DISTINCT. This can affect results when DISTINCT deduplicates rows after analytic functions have been computed and QUALIFY has filtered them.

Example:

~~~sql
SELECT DISTINCT department_id,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY employee_id
       ) AS rn
FROM employees
QUALIFY rn <= 2
ORDER BY department_id, rn;
~~~

Because RN differs across rows within the same department, DISTINCT typically does not eliminate those rows. If you omit RN from the select list, check carefully which analytic expression is used in QUALIFY and which columns DISTINCT retains.

When using an inline view on older versions, DISTINCT in the outer query block occurs after the inner query block computes the analytic function; preserve the same logical order when converting queries between the two syntax styles.

## 12. QUALIFY and FETCH FIRST

QUALIFY filters analytic results; FETCH FIRST limits the row count of the final result after ORDER BY.

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees
QUALIFY rn <= 3
ORDER BY department_id, rn
FETCH FIRST 20 ROWS ONLY;
~~~

The query selects up to three people per department, then caps the total output at most 20 rows. If there are many departments and total rows after QUALIFY exceed 20, FETCH FIRST truncates trailing rows according to ORDER BY.

If the goal is at most 20 rows **per department**, put RN <= 20 inside QUALIFY, not a query-wide FETCH FIRST 20 ROWS ONLY.

## 13. Verifying Results and Semantics Before Optimizing

When converting a query from inline view to QUALIFY, compare both on the same dataset:

~~~sql
-- Inline view approach.
SELECT employee_id, department_id, salary
FROM (
    SELECT employee_id,
           department_id,
           salary,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY salary DESC NULLS LAST, employee_id
           ) AS rn
    FROM employees
)
WHERE rn <= 3
ORDER BY department_id, rn;
~~~

~~~sql
-- QUALIFY approach on Oracle AI Database 26ai.
SELECT employee_id, department_id, salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees
QUALIFY rn <= 3
ORDER BY department_id, rn;
~~~

These two queries are written to preserve identical semantics. When comparing, verify:
- Same source row set and WHERE conditions.
- Same PARTITION BY.
- Same analytic ORDER BY, including NULLS FIRST/LAST.
- Same tie-breaker.
- Same ranking filter condition.
- Same final ORDER BY.
- Same NULL and duplicate handling.
- Same FETCH FIRST limit if present.

Do not conclude two queries are equivalent just because a small dataset happens to return matching output.

### 13.1. Testing Ties at Boundaries

Create test data with at least:
- Two rows sharing the highest value.
- Multiple rows sharing the same value at the top-N boundary.
- A row with a NULL sort key.
- Multiple partitions.
- A partition with zero rows after WHERE.

Then compare ROW_NUMBER, RANK, and DENSE_RANK. If you replace the analytic ORDER BY with a different combination, tie results may change even though the SQL still runs.

### 13.2. Testing Partitions with No Rows

If WHERE filters out all employees of a department, the analytic function produces no RN for that department. QUALIFY cannot restore rows already filtered out by WHERE.

If a report needs every department including departments with no matching employees, start from the DEPARTMENTS table and LEFT JOIN the ranked employee set, or use an appropriate query block to retain parent rows.

## 14. Performance: QUALIFY Is Not Automatically Faster Than an Inline View

QUALIFY makes SQL shorter and expresses the intent to filter analytic results cleanly. However, you should not assume QUALIFY is always faster than an inline view or CTE.

The optimizer can transform equivalent query structures. Performance depends on:
- Number of source rows after WHERE.
- Number of partitions and cardinality per partition.
- Whether analytic ORDER BY requires a large sort.
- Indexes and access paths.
- Whether filter predicates can be pushed before analytic evaluation while preserving semantics.
- PGA/TEMP and degree of sort spill.
- Optimizer statistics and version/RU.

### 14.1. Do Not Push a QUALIFY Condition Down to WHERE If It Changes the Ranking Set

Example:

~~~sql
SELECT employee_id,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS rn
FROM employees
QUALIFY rn = 1;
~~~

You cannot arbitrarily rewrite this as WHERE RN = 1 in the same query block. Nor can you push an outer row filter down into WHERE if doing so causes the analytic function to rank over a smaller row set.

The optimizer is only allowed to perform transformations that preserve results. When rewriting manually, preserve the semantic order.

### 14.2. Viewing the Execution Plan

You can inspect the estimated plan:

~~~sql
EXPLAIN PLAN FOR
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
       ) AS rn
FROM employees
QUALIFY rn <= 3;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

On a database supporting QUALIFY, the plan may show WINDOW SORT or an analytic-related operation along with filtering steps. On older versions, use the equivalent inline view query to inspect the plan.

EXPLAIN PLAN is an estimated plan. For production, inspect the cursor plan and runtime statistics when authorized, such as DBMS_XPLAN.DISPLAY_CURSOR with appropriate options. Do not claim a specific operation must appear for every query or every RU.

## 15. Java JDBC and Version-Specific SQL

JDBC sends SQL statements to the database server. If an application uses QUALIFY while the server does not support it, the statement will fail during parse/execute even if the driver is a newer version.

### 15.1. Configuring Capability by Environment

An application design can:
- Read database product/version from DatabaseMetaData or query release metadata.
- Determine whether the server supports QUALIFY.
- Select the appropriate SQL template.
- Use PreparedStatement to bind values.
- Test the SQL against the exact database release/RU in CI.

Metadata example:

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;

public final class DatabaseInfo {
    public static void printVersion(Connection connection)
            throws SQLException {
        DatabaseMetaData metadata = connection.getMetaData();

        System.out.println(metadata.getDatabaseProductName());
        System.out.println(metadata.getDatabaseProductVersion());
        System.out.println(metadata.getDriverName());
        System.out.println(metadata.getDriverVersion());
    }
}
~~~

DATABASEPRODUCTVERSION reports the database server version the connection uses; DRIVERVERSION is only the driver version. Do not use DRIVER VERSION instead of DATABASE PRODUCT VERSION when deciding SQL syntax.

### 15.2. Two SQL Templates

SQL for older servers:

~~~java
String legacySql = """
    SELECT employee_id, department_id, salary
    FROM (
        SELECT e.employee_id,
               e.department_id,
               e.salary,
               ROW_NUMBER() OVER (
                   PARTITION BY e.department_id
                   ORDER BY e.salary DESC NULLS LAST,
                            e.employee_id
               ) AS rn
        FROM employees e
        WHERE e.active_flag = ?
    )
    WHERE rn <= ?
    ORDER BY department_id, rn
    """;
~~~

SQL for Oracle AI Database 26ai:

~~~java
String modernSql = """
    SELECT e.employee_id,
           e.department_id,
           e.salary,
           ROW_NUMBER() OVER (
               PARTITION BY e.department_id
               ORDER BY e.salary DESC NULLS LAST,
                        e.employee_id
           ) AS rn
    FROM employees e
    WHERE e.active_flag = ?
    QUALIFY rn <= ?
    ORDER BY department_id, rn
    """;
~~~

Both use bind variables for ACTIVE_FLAG and N. They differ only in where the analytic result filter is placed.

### 15.3. Do Not Probe Support by Running QUALIFY on Every Request

Do not attempt a QUALIFY query on every API call and catch the error to fall back to legacy SQL. That approach:
- Increases round trips and parse overhead.
- Pollutes error logs.
- Can mask real SQL errors.
- Makes execution paths unpredictable.
- Can cause inconsistent behavior across connections in a pool.

Determine capability during datasource initialization or from deployment configuration. If a connection pool can target multiple different databases/services, capability must match the exact connection group.

## 16. Workflow for Verifying Version-Specific Syntax

Before using QUALIFY in a project:

1. Identify the database service the application actually connects to.
2. Read the server's banner/version.
3. Determine the full RU, especially on the 23ai/26ai branch.
4. Consult the SQL Language Reference for that exact release.
5. If 19c, 21c, or 23ai prior to RU 23.26.0, use an inline view/CTE.
6. If Oracle AI Database 26ai, test a small QUALIFY SELECT on that exact database.
7. Run a test suite covering ties, NULLs, multiple partitions, and empty partitions.
8. Compare results against the equivalent inline view version.
9. Inspect execution plans and runtime statistics.
10. Update SQL templates/capability config and re-test in CI.

### 16.1. Checking Syntax in SQL Developer/SQLcl

Client tools may offer syntax highlighting or completion based on their own version. That does not prove the database server supports the syntax. Running the SELECT on the target connection is what confirms the server parser accepts it.

If a tool reports an error, record:
- Database product version.
- Full RU.
- Minimal reproducible SQL text.
- Error code/message.
- Service/PDB the session is connected to.

### 16.2. Do Not Infer Support from COMPATIBLE Alone

COMPATIBLE is not a catalog listing all SQL keywords supported by the parser. A database can have a COMPATIBLE setting different from the latest installed release. Use the actual release/RU and corresponding feature documentation to decide.

## 17. Practice Dataset

Create a sandbox table to compare inline views and QUALIFY. The DDL/DML statements below are strictly for a practice schema.

### 17.1. Create the Table

~~~sql
CREATE TABLE employee_filter_demo (
    employee_id   NUMBER(6)
        CONSTRAINT pk_employee_filter_demo PRIMARY KEY,
    department_id NUMBER(4) NOT NULL,
    full_name     VARCHAR2(80 CHAR) NOT NULL,
    salary        NUMBER(12,2),
    active_flag   CHAR(1) NOT NULL
);
~~~

### 17.2. Load Data

~~~sql
INSERT INTO employee_filter_demo VALUES (101, 10, 'An',    20000000, 'Y');
INSERT INTO employee_filter_demo VALUES (102, 10, 'Binh',  20000000, 'Y');
INSERT INTO employee_filter_demo VALUES (103, 10, 'Chi',   15000000, 'Y');
INSERT INTO employee_filter_demo VALUES (104, 10, 'Dung',  25000000, 'N');

INSERT INTO employee_filter_demo VALUES (201, 20, 'Giang', 30000000, 'Y');
INSERT INTO employee_filter_demo VALUES (202, 20, 'Hanh',  18000000, 'Y');
INSERT INTO employee_filter_demo VALUES (203, 20, 'Khanh', NULL,      'Y');
INSERT INTO employee_filter_demo VALUES (204, 20, 'Lan',   30000000, 'N');

INSERT INTO employee_filter_demo VALUES (301, 30, 'Minh',  12000000, 'Y');

COMMIT;
~~~

The data contains:
- Department 10 has two ACTIVE employees sharing salary 20 million and one ACTIVE employee at 15 million.
- Department 10 also has one INACTIVE employee at 25 million.
- Department 20 has two ACTIVE people with salary 30 million, one ACTIVE person with NULL salary, and one INACTIVE person with salary 30 million.
- Department 30 has one ACTIVE person.

### 17.3. Rank ACTIVE Employees First, Then Take Top Two

Inline view approach:

~~~sql
SELECT employee_id,
       department_id,
       full_name,
       salary,
       rn
FROM (
    SELECT e.employee_id,
           e.department_id,
           e.full_name,
           e.salary,
           ROW_NUMBER() OVER (
               PARTITION BY e.department_id
               ORDER BY e.salary DESC NULLS LAST,
                        e.employee_id
           ) AS rn
    FROM employee_filter_demo e
    WHERE e.active_flag = 'Y'
)
WHERE rn <= 2
ORDER BY department_id, rn;
~~~

On Oracle AI Database 26ai, write the equivalent using QUALIFY:

~~~sql
SELECT e.employee_id,
       e.department_id,
       e.full_name,
       e.salary,
       ROW_NUMBER() OVER (
           PARTITION BY e.department_id
           ORDER BY e.salary DESC NULLS LAST,
                    e.employee_id
       ) AS rn
FROM employee_filter_demo e
WHERE e.active_flag = 'Y'
QUALIFY rn <= 2
ORDER BY department_id, rn;
~~~

Expected result:
- Department 10: An, Binh.
- Department 20: Giang, Hanh.
- Department 30: Minh.

In department 20, two people share a salary of 30 million; EMPLOYEE_ID determines ROW_NUMBER order. The NULL salary row comes last.

### 17.4. Rank Everyone First, Then Display Only ACTIVE

~~~sql
WITH ranked AS (
    SELECT e.employee_id,
           e.department_id,
           e.full_name,
           e.salary,
           e.active_flag,
           ROW_NUMBER() OVER (
               PARTITION BY e.department_id
               ORDER BY e.salary DESC NULLS LAST,
                        e.employee_id
           ) AS rn
    FROM employee_filter_demo e
)
SELECT employee_id, department_id, full_name, salary
FROM ranked
WHERE active_flag = 'Y'
  AND rn = 1
ORDER BY department_id;
~~~

Result:
- Department 10 has no rows because Dung is the highest-paid employee but INACTIVE; after ranking everyone, Dung receives RN = 1 and is then filtered out.
- Department 20 has no missing row because Giang or Lan has salary 30 million; Giang receives RN = 1 due to smaller ID and being ACTIVE, so Giang is kept.
- Department 30 has Minh.

This example shows how WHERE placement can change the meaning of ranking.

### 17.5. Comparing ROW_NUMBER and RANK at the Boundary

~~~sql
SELECT employee_id,
       department_id,
       salary,
       RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST
       ) AS salary_rank
FROM employee_filter_demo
WHERE active_flag = 'Y'
QUALIFY salary_rank <= 1
ORDER BY department_id, employee_id;
~~~

On 26ai, RANK <= 1 retains everyone tied for first place in each department. Department 10 has An and Binh; department 20 has Giang; department 30 has Minh.

If RANK is replaced with ROW_NUMBER and condition RN = 1, each department keeps only one row. If replaced with DENSE_RANK <= 1, the result also keeps every row at the highest distinct salary tier.

### 17.6. Clean Up the Practice Table

~~~sql
DROP TABLE employee_filter_demo PURGE;
~~~

Only drop the sandbox table created for this lesson when certain the data is no longer needed. DROP TABLE is DDL with implicit commit behavior; PURGE bypasses the recycle bin as usual.

## 18. Common Errors and Misconceptions

| Symptom | Cause | Resolution |
| --- | --- | --- |
| ORA-00904 with RN alias in WHERE | Analytic alias does not yet exist in the same query block | Use inline view/CTE, or QUALIFY on 26ai |
| Syntax error at keyword QUALIFY | Server release/RU does not support it | Check version/RU, use nested query |
| QUALIFY works locally but fails in production | Local and production run different database releases | Verify production database service |
| SQL Developer highlights QUALIFY but server throws error | Client parser is newer than server | Rely on server version, not syntax highlighting |
| Ranking results change after adding WHERE | WHERE alters the row set entering analytic functions | Clarify whether to filter before or after ranking |
| QUALIFY returns more rows than expected | Used RANK/DENSE_RANK which preserve ties | Use ROW_NUMBER if at most N exact rows are needed |
| QUALIFY keeps only one person despite tied scores | ROW_NUMBER assigns unique numbers | Use RANK/DENSE_RANK if ties should be preserved |
| Inline view and QUALIFY return different results | Differing WHERE, partition, order, NULLs, or tie-breaker | Compare each component carefully |
| QUALIFY and FETCH FIRST return fewer rows than top-N per group | FETCH FIRST limits the entire query output | Use ranking condition per partition |
| CTE mistaken for a temporary table | Confusing query organization with physical execution plan | Inspect execution plan |
| Query drops empty departments | Started from employees or used INNER JOIN | Start from departments table and LEFT JOIN |
| Using COMPATIBLE to infer QUALIFY support | Confusing compatibility parameter with release/RU | Check server version and release-specific docs |

## 19. Syntax Selection Principles

Apply the following guidelines:

- If the target database is 19c or 21c, use an inline view or CTE.
- If 23ai prior to RU 23.26.0, use an inline view or CTE.
- If Oracle AI Database 26ai, QUALIFY can be used for more concise queries.
- If the application supports multiple releases, prefer common syntax or select SQL templates via verified capability flags.
- Regardless of syntax, clarify whether WHERE filters before ranking or outer filter/QUALIFY filters after ranking.
- Always make analytic ORDER BY sufficiently clear; with ROW_NUMBER, add a unique tie-breaker when deterministic selection is needed.
- Include a final ORDER BY if the application requires sorted output.
- Test NULLs, ties, empty partitions, and changing data.
- Measure execution plans on the target database; do not assume QUALIFY is faster than an inline view.

## 20. Self-Practice Exercises

1. Why can't the RN alias be used in the WHERE clause of the same query block?
2. Rewrite the query filtering ROW_NUMBER = 1 using an inline view.
3. Rewrite the same query using a CTE.
4. On Oracle AI Database 26ai, write the equivalent query using QUALIFY.
5. Distinguish the roles of WHERE, HAVING, QUALIFY, and WHERE in an outer query block.
6. A department has ACTIVE and INACTIVE employees. Compare results when filtering ACTIVE before ranking versus after ranking.
7. Write a query retrieving the top three highest-paid employees in each department using QUALIFY.
8. Write a query retaining all tied top-ranked employees using RANK.
9. Why can adding EMPLOYEE_ID to analytic ORDER BY break ties in RANK?
10. Write a query ranking departments by SUM(SALARY), keeping only groups with at least five employees and the top three ranks.
11. Does Oracle 21c support QUALIFY? What is the compatible way to write it?
12. Can Oracle 23ai prior to RU 23.26.0 use QUALIFY?
13. Why can't the JDBC driver version be used to conclude that the database server supports QUALIFY?
14. Write a query checking the database banner using V$VERSION.
15. Can COMPATIBLE replace checking database release/RU? Explain.
16. A QUALIFY query runs on a personal machine but fails in production. List the information you need to check.
17. Why does FETCH FIRST 10 ROWS ONLY after QUALIFY RN <= 3 not mean 10 rows per partition?
18. Compare inline view and QUALIFY in terms of semantics and compatibility.
19. Why is a CTE not a physical temporary table by default?
20. Inspect the execution plan of a filtered analytic query. Identify the operations handling analytic processing and filtering, if any.

## 21. Oracle Reference Documentation

- [Oracle AI Database 26ai SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/SELECT.html): QUALIFY syntax, clause position, processing order, and examples.
- [Oracle AI Database 26ai SQL Language Reference — Analytic Functions](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/Analytic-Functions.html): analytic function evaluation order and relationship with QUALIFY.
- [Oracle Database 21c SQL Language Reference — Analytic Functions](https://docs.oracle.com/en/database/oracle/oracle-database/21/sqlrf/Analytic-Functions.html): filtering analytic results via nested queries on versions without QUALIFY.
- [Oracle AI Database 26ai New Features Guide](https://docs.oracle.com/en/database/oracle/oracle-database/26/nfcoa/all-nfg.html): QUALIFY support in 26ai.

**Filtering analytic results is a step that occurs after analytic functions have finished computing.** On Oracle 19c, 21c, and 23ai prior to RU 23.26.0, use an inline view or CTE to separate the computation step from the filtering step. On Oracle AI Database 26ai, QUALIFY lets you write both steps in the same query block. Whichever syntax you choose, verify the target database's release/RU and preserve the exact filtering order, partitioning, tie-breakers, and NULL rules so results remain unchanged.
