# PRAGMA UDF, SQL-Invoked Functions, and Oracle Version Support

In Oracle Database, a PL/SQL function can be called directly from a SQL statement. For example, a reporting query might call a function that calculates the post-tax amount for each sales row. This approach encapsulates logic and promotes reuse, but every call from the SQL engine to the PL/SQL engine incurs context-switching overhead. If the function is invoked for hundreds of thousands or millions of rows, that overhead can become a significant share of query execution time.

Oracle provides **PRAGMA UDF** to inform the PL/SQL compiler that a function is primarily used from SQL. The compiler can generate a more suitable execution path and reduce part of the overhead when crossing the SQL/PLSQL boundary. This is a call-path optimization; it does not change business results, does not turn a function into a SQL expression, does not cache results, and does not remove the restrictions on SQL-invoked functions.

This lesson belongs to the **Advanced PL/SQL** module of Database Engine Relational Oracle. It covers context switching, declaring PRAGMA UDF, invoking functions from SELECT and DML, compatibility requirements for datatypes/privileges/side effects, version differences, performance measurement, and alternative design choices.

After this lesson, you can:

- Explain why SQL calling a PL/SQL function can incur context-switch overhead.
- Recognize cases where a function is called once versus repeatedly per row.
- Declare PRAGMA UDF in the right place inside a function.
- Use UDF with standalone functions or package functions.
- Distinguish PRAGMA UDF from DETERMINISTIC, RESULT_CACHE, and PRAGMA INLINE.
- Identify suitable datatypes and parameter modes for SQL-invoked functions.
- Understand restrictions regarding DML, transaction control, DDL, and side effects.
- Understand why you must not assume SQL invokes a function exactly once per row.
- Determine which Oracle versions support PRAGMA UDF.
- Measure and compare before/after performance using an equivalent workload.
- Decide when to rewrite in pure SQL or use an alternative mechanism.

> **Example scope:** Statements follow Oracle Database 19c. PRAGMA UDF was introduced in Oracle Database 12c Release 1 (12.1). Examples use familiar SQL types such as NUMBER/VARCHAR2/DATE; direct SQL support for BOOLEAN or other PL/SQL types depends on the release, especially before versus starting in Oracle Database 23c/23ai.

## 1. The SQL Engine and the PL/SQL Engine

Oracle SQL and PL/SQL work closely together but are not the same execution engine.

- **SQL engine** parses and executes SELECT, INSERT, UPDATE, DELETE, MERGE, and SQL expressions.
- **PL/SQL engine** executes blocks, procedures, functions, packages, and control statements such as IF, LOOP, and EXCEPTION.

When SQL calls a PL/SQL function, control must transfer from the SQL engine to the PL/SQL engine, execute the function, and return to the SQL engine. This back-and-forth transition is commonly called a *context switch*.

### 1.1. A Function Invoked from SELECT

Example:

~~~sql
SELECT
    order_id,
    order_total,
    calculate_net_amount(order_total, 0.10) AS net_amount
FROM orders_lab;
~~~

If the result has 10 rows, the function may be called several times for the rows being computed. If the result has 1 million rows, the SQL engine may have to invoke the PL/SQL function very many times. The actual call count also depends on how the optimizer executes the SQL query, whether expressions are eliminated or re-evaluated, and the query structure.

### 1.2. Illustrating the Call Boundary

~~~text
                 SQL ENGINE
       SELECT ... calculate_net_amount(...)
                      |
                      | call function
                      v
                 PL/SQL ENGINE
       calculate input -> compute -> return
                      |
                      | return value
                      v
                 SQL ENGINE
       continue row processing / fetch result
~~~

If SQL calls the function repeatedly, context-switching overhead repeats as well. For very small functions, the overhead can exceed the computation itself.

### 1.3. Smaller Functions Show Overhead More Clearly

Suppose a function only performs:

~~~sql
RETURN p_amount * (1 - p_tax_rate);
~~~

Multiplication and subtraction are very cheap. If each function call adds communication overhead between the two engines, the total cost can become significant when invoked row by row.

Conversely, if the function performs a heavy, long-running algorithm, context-switching cost may be only a small fraction. PRAGMA UDF is not a substitute for optimizing algorithms, SQL plans, indexes, or I/O.

## 2. What Is PRAGMA UDF?

PRAGMA UDF is a compiler directive in PL/SQL. It tells the compiler that the function is designed primarily to be called from SQL. Oracle can optimize the function call path and reduce switching overhead between the SQL engine and the PL/SQL engine.

### 2.1. Key Implications

- Optimizes the SQL-to-function call path in appropriate cases.
- Can improve queries that invoke a function repeatedly per row.
- Does not change the public signature of the function.
- Does not change return values when the function is written properly.
- Does not guarantee every workload will run faster.

### 2.2. PRAGMA UDF Does Not Create a New Kind of Function

The function remains a normal PL/SQL function. It still has parameters, a return type, exception handling, and dependencies as before. PRAGMA UDF is strictly a compiler hint/directive.

### 2.3. Not Every Function Needs UDF

Consider UDF when:

- The function is invoked from SQL.
- The function may be called many times over a large result set.
- The logic should remain encapsulated in PL/SQL.
- Benchmarks show function-call overhead is significant.

Do not add UDF to every function just because the database supports the pragma. Functions called once from PL/SQL typically do not benefit meaningfully from this optimization target.

## 3. Syntax and Placement

### 3.1. Syntax

~~~sql
PRAGMA UDF;
~~~

Place the pragma in the declaration section of the function, before the executable BEGIN section. Example:

~~~sql
CREATE OR REPLACE FUNCTION net_amount_udf (
    p_amount   IN NUMBER,
    p_tax_rate IN NUMBER
)
RETURN NUMBER
IS
    PRAGMA UDF;
BEGIN
    RETURN p_amount * (1 - p_tax_rate);
END net_amount_udf;
/
~~~

The function can be called from SQL:

~~~sql
SELECT
    order_id,
    net_amount_udf(order_total, 0.10) AS net_amount
FROM orders_lab;
~~~

### 3.2. Pragma Placement

The pragma belongs in the declarative section of the function:

~~~text
CREATE FUNCTION ...
RETURN ...
IS
    declarations
    PRAGMA UDF;
BEGIN
    executable statements
END;
~~~

Do not place PRAGMA UDF inside an IF statement, a LOOP, or after BEGIN as an executable statement. It is a compiler directive, not a runtime call.

### 3.3. Function Without UDF

~~~sql
CREATE OR REPLACE FUNCTION net_amount_plain (
    p_amount   IN NUMBER,
    p_tax_rate IN NUMBER
)
RETURN NUMBER
IS
BEGIN
    RETURN p_amount * (1 - p_tax_rate);
END net_amount_plain;
/
~~~

Both functions share identical logic. The difference is that `net_amount_udf` includes the pragma. This is a suitable pair to benchmark when invoked from SQL under an identical workload.

### 3.4. Functions Inside Packages

PRAGMA UDF can also be used with functions implemented in a package body:

~~~sql
CREATE OR REPLACE PACKAGE pricing_api_lab AS
    FUNCTION net_amount (
        p_amount   IN NUMBER,
        p_tax_rate IN NUMBER
    ) RETURN NUMBER;
END pricing_api_lab;
/

CREATE OR REPLACE PACKAGE BODY pricing_api_lab AS
    FUNCTION net_amount (
        p_amount   IN NUMBER,
        p_tax_rate IN NUMBER
    ) RETURN NUMBER
    IS
        PRAGMA UDF;
    BEGIN
        RETURN p_amount * (1 - p_tax_rate);
    END net_amount;
END pricing_api_lab;
/
~~~

Called from SQL:

~~~sql
SELECT
    order_id,
    pricing_api_lab.net_amount(order_total, 0.10) AS net_amount
FROM orders_lab;
~~~

The public signature is in the package specification; the pragma goes in the function implementation. Callers continue invoking the same name and signature as usual.

### 3.5. UDF Does Not Apply to Procedures

PRAGMA UDF is designed for functions. A SQL expression requires a return value, so you cannot substitute a procedure with UDF to call it as a SQL expression. Procedures perform procedural/business operations; functions return a value.

## 4. Where Can Functions Be Invoked from SQL?

A function can appear in many SQL positions provided it meets rules on datatypes, privileges, and side effects.

### 4.1. In the SELECT List

~~~sql
SELECT
    employee_id,
    monthly_salary,
    pricing_api_lab.net_amount(monthly_salary, 0.08) AS salary_after_tax
FROM employee_data_lab;
~~~

This is the classic example: the function computes a value for each row.

### 4.2. In WHERE

~~~sql
SELECT employee_id, full_name
FROM employee_data_lab
WHERE pricing_api_lab.is_high_salary(monthly_salary) = 1;
~~~

If a function is called to filter each row, call overhead can have a large impact. Consider expressing the condition directly in SQL:

~~~sql
SELECT employee_id, full_name
FROM employee_data_lab
WHERE monthly_salary >= 5000;
~~~

Pure SQL usually exposes the predicate clearly to the optimizer and can take advantage of indexes.

### 4.3. In ORDER BY

~~~sql
SELECT employee_id, full_name
FROM employee_data_lab
ORDER BY pricing_api_lab.normalized_name(full_name);
~~~

The function can be invoked during sorting. Do not assume Oracle computes it only once per row or reuses a value from the SELECT list; the optimizer determines execution behavior.

### 4.4. In GROUP BY

~~~sql
SELECT
    pricing_api_lab.salary_band(monthly_salary) AS salary_band,
    COUNT(*) AS employee_count
FROM employee_data_lab
GROUP BY pricing_api_lab.salary_band(monthly_salary);
~~~

The function participates in the grouping expression. If the same expression appears in multiple places, do not rely on Oracle always calling the function only once. Inspect the execution plan and benchmark.

### 4.5. In DML Expressions

~~~sql
UPDATE employee_data_lab
SET monthly_salary =
    pricing_api_lab.apply_raise(monthly_salary, 0.05)
WHERE department_id = 10;
~~~

The function's return value is used as an update expression. Restrictions on side effects and table access still apply. Do not use UDF to secretly execute another chain of DML inside the function.

### 4.6. A Function in SQL Does Not Guarantee One Call per Row

A function expression may appear in SELECT, WHERE, and ORDER BY. The optimizer may transform queries, evaluate expressions at different stages, or eliminate redundant expressions. Therefore:

- Do not rely on how many times the function is called.
- Do not use a SQL-invoked function to increment sequences or write call-count-dependent logs.
- Do not rely on evaluation order between two function expressions.
- Do not assume a column alias in SELECT guarantees the expression is evaluated only once.

SQL-invoked functions should avoid side effects and return results derived strictly from defined inputs/context.

## 5. Requirements for Calling a Function from SQL

PRAGMA UDF does not remove SQL-callable function rules. The function must satisfy the SQL engine's baseline requirements.

### 5.1. Parameter Mode

Parameters of a SQL-invoked function must be appropriate input parameters; do not use OUT or IN OUT to return extra values to a SQL statement.

Do not design:

~~~sql
FUNCTION calculate_value (
    p_input IN NUMBER,
    p_detail OUT VARCHAR2
) RETURN NUMBER;
~~~

to be called directly in SELECT. If multiple values are needed, consider returning an appropriate SQL object type/collection, using separate scalar functions where sensible, or returning a result set via REF CURSOR in a PL/SQL API.

### 5.2. Datatypes Must Be Recognized by SQL

A function used in SQL requires parameter/return types supported by the SQL engine in the target release. Common types include NUMBER, VARCHAR2, DATE, TIMESTAMP, and appropriate SQL object/collection types.

In Oracle 19c, PL/SQL BOOLEAN is not a SQL datatype usable directly in SQL expressions. Therefore, SQL-callable examples should use NUMBER/CHAR to represent flags:

~~~sql
FUNCTION is_active (
    p_status IN VARCHAR2
) RETURN NUMBER;
~~~

A convention can be 1 = active, 0 = inactive. Starting with Oracle Database 23c/23ai, SQL includes a BOOLEAN datatype, expanding PL/SQL/SQL interoperability. When code must run across multiple releases, choose a contract compatible with the lowest supported release.

### 5.3. Do Not Return Local PL/SQL RECORDs as SQL Values

A RECORD declared in a PL/SQL block/package does not automatically become a SQL datatype. A function called in SELECT cannot arbitrarily return a local PL/SQL record as a SQL column.

If multiple fields must be returned as a single SQL value, consider:

- A SQL object type created via CREATE TYPE.
- Separate scalar columns.
- An appropriate SQL collection type.
- A REF CURSOR if the API is a PL/SQL procedure returning a result set.
- JSON/XML if that is the chosen contract.

### 5.4. The Function Must Have Privileges on Required Objects

A function querying tables/views requires appropriate privileges according to AUTHID:

- By default, stored PL/SQL units use definer rights.
- A definer-rights function runs with the owner's privileges per Oracle rules.
- Static SQL in stored code requires direct object grants; privileges granted only through roles do not substitute for direct grants when compiling/using definer-rights code.
- AUTHID CURRENT_USER switches to the invoker-rights model and must be tested with actual callers.

PRAGMA UDF grants no extra privileges, does not bypass object privileges, and does not alter AUTHID.

### 5.5. The Function Must Compile Validly

Check:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_type IN ('FUNCTION', 'PACKAGE', 'PACKAGE BODY')
ORDER BY object_type, object_name;

SELECT name, type, line, position, text
FROM user_errors
ORDER BY name, type, sequence;
~~~

An INVALID function or a package body with errors cannot be invoked reliably from SQL.

## 6. Side-Effect and Transaction Restrictions

Functions called from SQL should be designed as pure value-returning computations. Side effects can violate SQL optimizer expectations and face strict restrictions.

### 6.1. Do Not Use a SELECT Function to Modify Tables

Avoid patterns like:

~~~sql
CREATE OR REPLACE FUNCTION read_and_log_lab (
    p_employee_id IN NUMBER
) RETURN NUMBER
IS
BEGIN
    INSERT INTO function_log_lab(employee_id, logged_at)
    VALUES (p_employee_id, SYSTIMESTAMP);

    RETURN p_employee_id;
END;
/
~~~

When a function is called from SELECT, ordinary DML is restricted and can raise `ORA-14551: cannot perform a DML operation inside a query`. Technical exceptions exist using autonomous transactions, but that should not be treated as a default pattern for turning SQL functions into logging mechanisms.

### 6.2. DML in Functions and Autonomous Transactions

Oracle permits functions using PRAGMA AUTONOMOUS_TRANSACTION to run an independent transaction in certain cases. However, this changes semantics:

- Log data can commit even if the outer SELECT fails.
- The function may be invoked more times than expected.
- The query is no longer a pure computation.
- Independent transactions can cause contention or deadlocks if accessing related resources.

Use autonomous transactions only when auditing requirements genuinely demand independence and transaction boundaries are well understood. For ordinary SELECT-invoked functions, prefer zero DML side effects.

### 6.3. No COMMIT/ROLLBACK Inside SQL Functions

A function invoked from SQL cannot arbitrarily control the calling statement's transaction. COMMIT, ROLLBACK, and transaction control statements in ordinary functions are prohibited in a SQL context and can raise errors such as ORA-14552. Never use a function to decide whether to commit the caller's transaction.

### 6.4. DDL and Session Control Are Inappropriate

Do not execute DDL, ALTER SESSION, transaction control, or system control from a SQL-invoked function. If schema/session changes are needed, perform them through procedures or a dedicated administration layer with explicit transaction boundaries.

### 6.5. Functions Invoked from DML Have Specific Restrictions

When a function is called inside an UPDATE/DELETE/MERGE statement, avoid reading or modifying the table currently being modified in ways that violate mutating/SQL-invoked function rules. Specific cases can trigger ORA-04091 or other side-effect errors. Put the update logic directly in the DML statement, use an appropriate trigger, or separate steps cleanly across transactions.

### 6.6. Do Not Rely on Function Evaluation Order

Example:

~~~sql
SELECT
    function_a(col),
    function_b(col)
FROM source_table;
~~~

There is no guarantee `function_a` always runs before `function_b`. Nor is there any guarantee a function runs once per row or only once when an expression is repeated. Side effects relying on evaluation order or call count can introduce logic bugs.

## 7. What PRAGMA UDF Does and Does Not Do

| Capability | PRAGMA UDF |
| --- | --- |
| Tells compiler function is primarily called from SQL | Yes |
| Can reduce SQL-to-PL/SQL call overhead | Yes, workload-dependent |
| Changes function output | No |
| Caches results by input | No |
| Guarantees function runs exactly once per row | No |
| Makes function deterministic | No |
| Allows OUT/IN OUT parameters in SQL | No |
| Allows DML/COMMIT/DDL in SQL functions | No |
| Automatically turns PL/SQL RECORD into a SQL datatype | No |
| Replaces SQL rewrite/index/plan tuning | No |

PRAGMA UDF is a call-path optimization; correctness, SQL compatibility, security, and side-effect constraints remain unchanged.

## 8. Distinguishing PRAGMA UDF from Other Pragmas/Features

Several features can appear on the same function while solving different problems.

### 8.1. UDF vs. DETERMINISTIC

DETERMINISTIC declares that a function returns the same result given the same inputs under its promised semantics:

~~~sql
CREATE OR REPLACE FUNCTION normalize_code_lab (
    p_code IN VARCHAR2
) RETURN VARCHAR2
DETERMINISTIC
IS
BEGIN
    RETURN UPPER(TRIM(p_code));
END;
/
~~~

Differences:

- PRAGMA UDF: optimizes the cost of calling the function from SQL.
- DETERMINISTIC: promises output stability for identical inputs; relevant to function-based indexes and certain optimizations.

Do not declare DETERMINISTIC if results depend on mutable tables, SYSDATE/SYSTIMESTAMP, NLS settings, application context, package state, or session data. Incorrect declarations can lead to wrong results or stale/invalid indexes.

DETERMINISTIC is not an automatic time-bounded cache and does not guarantee the function executes only once.

### 8.2. UDF vs. RESULT_CACHE

RESULT_CACHE tells Oracle to store function results in the result cache when supported:

- PRAGMA UDF focuses on reducing call overhead.
- RESULT_CACHE focuses on reusing previously computed results while the cache remains valid.
- A function can be designed to use both if semantics and release allow, though neither replaces the other.

Result caching carries invalidation/dependency rules and consumes memory. Do not cache results that depend on session state or unmanaged mutable data.

### 8.3. UDF vs. PRAGMA INLINE

PRAGMA INLINE is a compiler directive concerning inlining PL/SQL subprogram calls within PL/SQL code:

- PRAGMA UDF targets functions invoked by SQL.
- PRAGMA INLINE targets subprogram call optimization during PL/SQL compilation.

Do not use PRAGMA INLINE as a replacement for PRAGMA UDF across the SQL-to-PL/SQL boundary.

### 8.4. UDF vs. PARALLEL_ENABLE

PARALLEL_ENABLE relates to whether a function can participate in parallel execution under Oracle's conditions. PRAGMA UDF does not make a function parallel-safe. If parallel query execution is needed, evaluate safety, state, and dependencies separately.

### 8.5. UDF vs. SQL Macros

SQL macros are a different mechanism: a macro expands into a SQL expression or query so the optimizer sees pure SQL logic rather than calling a PL/SQL function per row. SQL macro availability depends on Oracle version and Release Update. Scalar SQL macros and table SQL macros have different support milestones; check documentation for your target release before adopting them.

When logic can be expressed as a SQL expression or a supported SQL macro, that approach can let the optimizer optimize the entire expression better than a PL/SQL function. PRAGMA UDF remains useful when logic must stay in PL/SQL and the function is genuinely invoked from SQL.

## 9. Oracle Version Support

PRAGMA UDF was introduced in Oracle Database 12c Release 1 (12.1). PL/SQL functions could still be called from SQL in earlier releases; what was missing was the UDF pragma instructing the compiler to optimize the call path via this feature.

| Version | PRAGMA UDF | Notes |
| --- | --- | --- |
| Oracle 11g and earlier | Not supported | Stored functions can still be called from SQL if rules are met; do not declare PRAGMA UDF |
| Oracle 12c Release 1 (12.1) | Introduced | PRAGMA UDF can be used in functions |
| Oracle 12c Release 2 (12.2) | Supported | SQL-callable function restrictions still apply |
| Oracle 18c | Supported | Verify compatibility when deploying across environments |
| Oracle 19c | Supported | Version used in this lesson's examples |
| Oracle 21c | Supported | Other SQL features such as SQL macros may offer alternatives depending on macro type |
| Oracle 23c/23ai | Supported | SQL/PLSQL interoperability expanded, including SQL BOOLEAN; still verify per datatype/API |

### 9.1. Database Version Is Not the Only Compatibility Setting

When deploying across multi-database environments, check:

- Exact database version.
- Release Update (RU) and patch level.
- COMPATIBLE initialization parameter.
- Client/driver version if functions are invoked through applications.
- Compilation settings and schema privileges.

A feature existing in a newer release does not mean every database in an environment has been upgraded or had compatibility raised accordingly.

### 9.2. Do Not Assume PRAGMA UDF Is Ignored on Older Versions

If source code contains PRAGMA UDF and is compiled on an unsupported database, the compiler can raise syntax/invalid-pragma errors. Do not ship identical source across releases without a migration or versioning strategy.

### 9.3. Keeping Source Compatible Across Versions

If you must support both 11g and 12c+:

- Use function source without PRAGMA UDF as the compatibility baseline.
- Maintain a separate source variant or deployment script for 12c+ if benchmarks prove a benefit.
- Do not add the pragma to shared functions if the lowest supported environment lacks support.
- Test compilation in a database running the lowest committed version.

### 9.4. BOOLEAN and SQL Interoperability

In Oracle 19c, BOOLEAN is a PL/SQL type and cannot be used directly as a SQL datatype in a standard SELECT. You can return NUMBER or CHAR to represent true/false.

Oracle Database 23c/23ai adds BOOLEAN in SQL, expanding interoperability. Still, if a package API must run on both 19c and 23ai, keep a shared compatible return type or versioned APIs. UDF does not resolve SQL datatype differences across releases.

## 10. Designing SQL-Friendly Functions

### 10.1. Prefer Side-Effect-Free Functions

Good SQL-callable functions typically:

- Accept clear inputs.
- Compute and return a single value.
- Perform no INSERT/UPDATE/DELETE.
- Perform no COMMIT/ROLLBACK.
- Do not mutate package state.
- Do not depend on invocation order.
- Do not rely on how many times the optimizer evaluates an expression.

Example:

~~~sql
CREATE OR REPLACE FUNCTION normalize_email_udf (
    p_email IN VARCHAR2
) RETURN VARCHAR2
IS
    PRAGMA UDF;
BEGIN
    IF p_email IS NULL THEN
        RETURN NULL;
    END IF;

    RETURN LOWER(TRIM(p_email));
END normalize_email_udf;
/
~~~

### 10.2. Avoid Reading Mutable Data When Possible

A function looking up a configuration table can be convenient:

~~~sql
FUNCTION get_tax_rate(p_region_code VARCHAR2) RETURN NUMBER;
~~~

However, when called for many rows, it can generate numerous nested SQL calls. Results also depend on configuration data, privileges, and transaction visibility. When possible, JOINing the configuration table directly in SQL is usually clearer and easier to optimize.

### 10.3. Avoid Deeply Nested Function Calls

~~~text
SQL query
  -> function A
       -> function B
            -> function C
                 -> SELECT config table
~~~

Each layer adds call overhead and obscures execution behavior. If the logic is a data transformation, consider consolidating into one small function or a SQL expression.

### 10.4. Handle NULL Explicitly

SQL uses three-valued logic: TRUE/FALSE/UNKNOWN. A function should clearly define what NULL inputs return:

~~~sql
CREATE OR REPLACE FUNCTION safe_discount_udf (
    p_amount IN NUMBER,
    p_rate IN NUMBER
) RETURN NUMBER
IS
    PRAGMA UDF;
BEGIN
    IF p_amount IS NULL OR p_rate IS NULL THEN
        RETURN NULL;
    END IF;

    RETURN p_amount * p_rate;
END;
/
~~~

Do not leave callers guessing NULL semantics. If NULL must be treated as 0, make that consistent inside the function or SQL expression.

### 10.5. Control NLS and Session Dependencies

Function output can vary with:

- NLS_DATE_FORMAT/NLS_NUMERIC_CHARACTERS.
- Session time zone.
- Current schema.
- Application context.
- Current user.
- Package state.
- SYSDATE/SYSTIMESTAMP.

If a function depends on these factors, do not mark it DETERMINISTIC just to create a function-based index or hope for caching. Passing inputs explicitly and normalizing formats is usually safer.

## 11. Measuring Performance Before and After PRAGMA UDF

Do not conclude UDF is faster merely because the compiler supports it. Benchmark on representative data and queries.

### 11.1. Create the Lab Table

~~~sql
CREATE TABLE udf_sales_lab AS
SELECT
    LEVEL AS sale_id,
    MOD(LEVEL, 10000) + 1 AS gross_amount
FROM dual
CONNECT BY LEVEL <= 100000;
~~~

### 11.2. Create a Function Without UDF

~~~sql
CREATE OR REPLACE FUNCTION tax_net_plain_lab (
    p_amount IN NUMBER,
    p_rate IN NUMBER
) RETURN NUMBER
IS
BEGIN
    RETURN p_amount * (1 - p_rate);
END tax_net_plain_lab;
/
~~~

### 11.3. Create a Function with UDF

~~~sql
CREATE OR REPLACE FUNCTION tax_net_udf_lab (
    p_amount IN NUMBER,
    p_rate IN NUMBER
) RETURN NUMBER
IS
    PRAGMA UDF;
BEGIN
    RETURN p_amount * (1 - p_rate);
END tax_net_udf_lab;
/
~~~

### 11.4. Run Two Equivalent Queries

~~~sql
SELECT SUM(tax_net_plain_lab(gross_amount, 0.10))
FROM udf_sales_lab;

SELECT SUM(tax_net_udf_lab(gross_amount, 0.10))
FROM udf_sales_lab;
~~~

Both SQL statements perform the exact same calculation over the same dataset. Record elapsed time, CPU, logical reads, and execution plans.

### 11.5. Measure with a PL/SQL Timer

You can use DBMS_UTILITY.GET_TIME in a lab block:

~~~sql
SET SERVEROUTPUT ON

DECLARE
    l_start PLS_INTEGER;
    l_elapsed PLS_INTEGER;
    l_total NUMBER;
BEGIN
    l_start := DBMS_UTILITY.GET_TIME;

    SELECT SUM(tax_net_plain_lab(gross_amount, 0.10))
    INTO l_total
    FROM udf_sales_lab;

    l_elapsed := DBMS_UTILITY.GET_TIME - l_start;
    DBMS_OUTPUT.PUT_LINE('Plain ticks=' || l_elapsed);
    DBMS_OUTPUT.PUT_LINE('Total=' || l_total);

    l_start := DBMS_UTILITY.GET_TIME;

    SELECT SUM(tax_net_udf_lab(gross_amount, 0.10))
    INTO l_total
    FROM udf_sales_lab;

    l_elapsed := DBMS_UTILITY.GET_TIME - l_start;
    DBMS_OUTPUT.PUT_LINE('UDF ticks=' || l_elapsed);
    DBMS_OUTPUT.PUT_LINE('Total=' || l_total);
END;
/
~~~

GET_TIME returns values in centiseconds according to Oracle documentation; this is a coarse lab measurement. For production workloads, use SQL trace, SQL Monitor, AWR/ASH where permitted and licensed, or approved benchmarking tools.

### 11.6. Benchmarking Rules

- Run warm-ups before recording measurements.
- Run multiple iterations and compare medians/percentiles rather than picking one favorable run.
- Use identical data, bind values, session settings, and execution plan conditions.
- Alternate execution order across iterations to reduce cache bias.
- Do not enable DBMS_OUTPUT per row.
- Do not let uncontrolled concurrent workloads skew measurements.
- Compare returned results to confirm both functions have identical semantics.
- Inspect execution plans and SQL Monitor when available.

### 11.7. UDF Does Not Guarantee a Speedup

If the function is called infrequently, does heavy work itself, or the query is primarily I/O-bound, the difference may be small. The optimizer might already eliminate part of the work, or nested SQL inside the function body may dominate costs. Keep the pragma only when real-workload benchmarks demonstrate a benefit or there is a clear technical reason.

## 12. Comparing Against Rewriting in Pure SQL

Before adding UDF, ask whether the logic can be expressed directly in SQL.

### 12.1. Tax Calculation Function

Function:

~~~sql
net_amount_udf(order_total, 0.10)
~~~

Pure SQL:

~~~sql
order_total * (1 - 0.10)
~~~

When logic is simple, a SQL expression avoids calling PL/SQL altogether.

### 12.2. Banding Function

Function:

~~~sql
salary_band(monthly_salary)
~~~

SQL:

~~~sql
CASE
    WHEN monthly_salary < 3000 THEN 'LOW'
    WHEN monthly_salary < 7000 THEN 'MID'
    ELSE 'HIGH'
END
~~~

CASE exposes the entire condition to the optimizer and avoids boundary calls.

### 12.3. Name Lookup Function

Function:

~~~sql
department_name(employee.department_id)
~~~

SQL JOIN:

~~~sql
SELECT e.employee_id, d.department_name
FROM employee_data_lab e
JOIN department_lab d
  ON d.department_id = e.department_id;
~~~

A JOIN is typically far easier to optimize than calling a function to SELECT one department row per employee.

### 12.4. Complex Reusable Functions

If the logic is complex or shared across many applications, a PL/SQL function can still be a sensible choice. In that case:

- Keep the function stateless/pure if possible.
- Add PRAGMA UDF if the version supports it and the workload fits.
- Consider SQL macros if you want to expand logic into SQL and the release supports them.
- Benchmark both the function approach and a SQL rewrite.

## 13. PRAGMA UDF, Function-Based Indexes, and the Optimizer

PRAGMA UDF does not create indexes and does not make predicates sargable.

### 13.1. Functions in WHERE Can Hinder Index Usage

~~~sql
SELECT *
FROM employee_data_lab
WHERE normalize_email_udf(work_email) = 'user@example.test';
~~~

If an index exists only on `WORK_EMAIL`, wrapping the column in a function expression can prevent normal index usage. UDF only lowers function-call cost; it does not turn a base-column index into an expression index.

### 13.2. Function-Based Indexes

If an expression is queried frequently and the function meets requirements, consider a function-based index:

~~~sql
CREATE INDEX ix_employee_email_norm_lab
ON employee_data_lab(LOWER(TRIM(work_email)));
~~~

When queries use the matching expression, the optimizer can consider the index under suitable conditions. Using a user-defined function in an index requires meeting DETERMINISTIC and Oracle's function-based index rules.

### 13.3. UDF Does Not Replace DETERMINISTIC

Do not add PRAGMA UDF and assume Oracle can reuse previous function results. If a function-based index or caching requires determinism, those requirements must be satisfied independently.

### 13.4. Inspecting the Execution Plan

~~~sql
EXPLAIN PLAN FOR
SELECT SUM(tax_net_udf_lab(gross_amount, 0.10))
FROM udf_sales_lab;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

The execution plan shows how Oracle accesses tables and evaluates SQL at the plan level. It does not always reveal the exact number of function invocations; combine with runtime statistics/tracing when needed.

## 14. SQL-Invoked Functions and Security

### 14.1. Default Definer Rights

Stored functions run by default with the owner's privileges (AUTHID DEFINER). If a function accesses configuration tables or data in another schema, the owner needs appropriate direct privileges for static SQL.

### 14.2. Invoker Rights

You can declare:

~~~sql
CREATE OR REPLACE FUNCTION current_user_region_lab
RETURN VARCHAR2
AUTHID CURRENT_USER
IS
    PRAGMA UDF;
BEGIN
    RETURN SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA');
END;
/
~~~

AUTHID CURRENT_USER switches the function to the invoker-rights model under Oracle rules. This is a security-semantics change, not a performance optimization option. Use it only when your authorization design requires that behavior.

### 14.3. Do Not Use UDF to Bypass Access Checks

PRAGMA UDF does not alter privilege checks, does not grant the function higher privileges than the caller, and does not bypass VPD/RLS or security policies. Test functions using the actual user accounts that will call them.

### 14.4. SQL-Callable Functions and Application Context

A function can read SYS_CONTEXT or session attributes. If output depends on context, identical inputs can return different results across sessions. Do not declare DETERMINISTIC or cache under the assumption that only input parameters determine output unless context is accounted for in the semantics.

## 15. Versions, Compatibility, and Deployment Strategy

### 15.1. Checking Database Version

~~~sql
SELECT banner
FROM v$version;
~~~

Or:

~~~sql
SELECT version
FROM product_component_version
WHERE product LIKE 'Oracle Database%';
~~~

Permissions to query V$VERSION vary by environment; use views authorized by your DBA.

### 15.2. Checking COMPATIBLE

A DBA can check:

~~~sql
SHOW PARAMETER compatible
~~~

Or:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'compatible';
~~~

COMPATIBLE is part of database compatibility policy. Do not raise this parameter merely to try PRAGMA UDF; the pragma is supported based on database release and must be verified in version documentation.

### 15.3. Deploying Across Multiple Environments

A pipeline might have DEV on 23ai, TEST on 19c, and PROD on an older 19c RU. Do not test only on DEV and deploy as-is. Instead:

1. Identify the version/RU of the lowest environment.
2. Confirm pragma and datatype support in that environment.
3. Compile in a representative environment.
4. Run SQL smoke tests.
5. Benchmark under an equivalent workload.
6. Maintain source variants if multiple versions must be supported.

### 15.4. API and Datatype Compatibility

If a public function returns BOOLEAN or a new type available only in newer releases, 19c callers will not compile. Keep a shared contract using NUMBER/CHAR or provide versioned package APIs. UDF does not bridge datatype differences between SQL engines across releases.

## 16. Common Errors

| Error/Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| PLS-00710 or invalid pragma error | Database does not support PRAGMA UDF or pragma misplaced | Check version and place in function declarative section |
| Function cannot be called in SELECT | Incompatible SQL return/parameter type or invalid function | Check signature, datatypes, and USER_ERRORS |
| PLS-00306 when calling function | Argument count/type mismatch | Fix invocation and overloads |
| ORA-14551 | Function performs DML inside a query | Remove side effect or move to separate procedure/transaction |
| ORA-14552 | Function attempts transaction control/DDL in SQL context | No COMMIT/ROLLBACK/DDL inside SQL-called functions |
| ORA-04091 | Accessing a mutating table in DML/trigger context | Redesign SQL/trigger or split processing |
| Different results across two calls | Function depends on time, session, context, or changing data | Make dependencies explicit; do not misdeclare DETERMINISTIC |
| Adding UDF yields no speedup | Few function calls, I/O or nested SQL bottleneck, or already optimized | Benchmark and inspect plan/runtime statistics |
| Function called more times than expected | SQL optimizer evaluates expression across multiple steps | Do not rely on call count; write side-effect-free functions |
| Function-based index not used | Expression mismatch or function/index requirements unmet | Check index definition, DETERMINISTIC, and execution plan |
| Compiles on 23ai but fails on 19c | Uses datatype/feature exclusive to newer release | Pick compatible contract or version-specific source |

## 17. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| PRAGMA UDF turns PL/SQL into SQL | The function remains PL/SQL |
| UDF completely eliminates context switching | It can reduce overhead, not guarantee zero cost |
| UDF automatically caches results | No; RESULT_CACHE is a separate mechanism |
| UDF makes a function deterministic | No |
| SQL always calls a function once per row | The optimizer may evaluate multiple times or eliminate expressions |
| UDF allows OUT/IN OUT in SELECT | No |
| UDF allows a function to modify tables | No; side-effect restrictions still apply |
| UDF automatically enables function-based indexes | No; indexing and determinism requirements are separate |
| UDF applies to procedures | No, the pragma is for functions |
| A SQL function can return any PL/SQL type | Return/parameter types must be supported by SQL in that release |
| BOOLEAN can be used in SQL on Oracle 19c | BOOLEAN is PL/SQL-only in 19c; SQL BOOLEAN arrives in 23c/23ai |
| Every function should get UDF | Add it only when invoked from SQL and justified by design/benchmarks |

## 18. Pre-Use Checklist for PRAGMA UDF

**Feature and Version**

- Is the database Oracle 12.1 or higher?
- Are RU/COMPATIBLE and datatypes compatible?
- Must the source run across multiple versions?

**Function Contract**

- Does the function use appropriate IN parameters?
- Are return/parameter datatypes supported SQL datatypes?
- Does the function compile VALID?
- Does the caller have EXECUTE and the owner have required direct grants?

**Semantics**

- Does the function avoid DML, DDL, and transaction control?
- Are there any side effects or call-count/order dependencies?
- Are NULL, NLS, time zone, and application context defined?
- Are DETERMINISTIC/RESULT_CACHE declared consistently with semantics?

**Performance**

- Is the function invoked many times from SQL?
- Can it be rewritten in pure SQL?
- Have both approaches been benchmarked on identical data?
- Have execution plan, CPU, elapsed time, and nested SQL been inspected?
- Is the pragma retained based on measured gains or clear rationale?

## 19. Comprehensive Lab Exercise

This lab compares a plain function against a function with PRAGMA UDF.

### Step 1 — Create Data

~~~sql
CREATE TABLE udf_sales_lab (
    sale_id NUMBER PRIMARY KEY,
    gross_amount NUMBER(12,2) NOT NULL
);

INSERT INTO udf_sales_lab(sale_id, gross_amount)
SELECT LEVEL, MOD(LEVEL, 10000) + 1
FROM dual
CONNECT BY LEVEL <= 100000;

COMMIT;
~~~

### Step 2 — Plain Function

~~~sql
CREATE OR REPLACE FUNCTION tax_net_plain_lab (
    p_amount IN NUMBER,
    p_rate IN NUMBER
) RETURN NUMBER
IS
BEGIN
    RETURN p_amount * (1 - p_rate);
END;
/
~~~

### Step 3 — Function with UDF

~~~sql
CREATE OR REPLACE FUNCTION tax_net_udf_lab (
    p_amount IN NUMBER,
    p_rate IN NUMBER
) RETURN NUMBER
IS
    PRAGMA UDF;
BEGIN
    RETURN p_amount * (1 - p_rate);
END;
/
~~~

### Step 4 — Compare Results

~~~sql
SELECT SUM(tax_net_plain_lab(gross_amount, 0.10)) AS total_plain
FROM udf_sales_lab;

SELECT SUM(tax_net_udf_lab(gross_amount, 0.10)) AS total_udf
FROM udf_sales_lab;
~~~

Both totals must match.

### Step 5 — Compare Runtime

Run each query multiple times, recording elapsed time and CPU. Use warm-ups and identical session settings. Do not draw conclusions from a single run.

### Step 6 — Compare Pure SQL

~~~sql
SELECT SUM(gross_amount * (1 - 0.10)) AS total_sql
FROM udf_sales_lab;
~~~

Pure SQL is a useful baseline to see whether invoking a PL/SQL function is necessary at all.

### Step 7 — Check Status and Errors

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
    'TAX_NET_PLAIN_LAB',
    'TAX_NET_UDF_LAB'
)
ORDER BY object_name;

SELECT name, type, line, position, text
FROM user_errors
WHERE name IN ('TAX_NET_PLAIN_LAB', 'TAX_NET_UDF_LAB')
ORDER BY name, sequence;
~~~

### Step 8 — Clean Up Lab (Optional)

~~~sql
DROP FUNCTION tax_net_plain_lab;
DROP FUNCTION tax_net_udf_lab;
DROP TABLE udf_sales_lab PURGE;
~~~

Run only if you are sure the objects belong to the lab and the data is no longer needed. DROP is DDL with an implicit commit.

## Oracle Reference Documentation

- [Oracle Database PL/SQL Language Reference — UDF Pragma](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/UDF-pragma.html): syntax and purpose of PRAGMA UDF.
- [Oracle Database PL/SQL Language Reference — PL/SQL Functions Invoked from SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-functions-that-sql-statements-can-invoke.html): conditions and restrictions for SQL-invoked functions.
- [Oracle Database PL/SQL Language Reference — DETERMINISTIC Clause](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/DETERMINISTIC-clause.html): semantics of deterministic functions.
- [Oracle Database PL/SQL Language Reference — RESULT_CACHE Clause](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/RESULT_CACHE-clause.html): PL/SQL function result cache.
- [Oracle Database PL/SQL Language Reference — Function-Based Indexes](https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/indexes.html): indexes on expressions and related requirements.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/): SQL datatypes and SQL expressions.
- [Oracle Database 23ai SQL Language Reference — Data Types](https://docs.oracle.com/en/database/oracle/oracle-database/23/sqlrf/Data-Types.html): SQL datatypes, including BOOLEAN in newer releases.

**Principle to remember:** PRAGMA UDF tells the compiler that a function is primarily invoked from SQL and can reduce context-switching overhead. It is supported from Oracle Database 12.1 onward, yet does not alter contracts, datatype restrictions, privileges, or side-effect limits of SQL-callable functions. Prefer pure SQL when logic can be expressed directly; if a PL/SQL function is still needed, keep it simple and side-effect-free, add UDF when supported by the version, and benchmark on real workloads.
