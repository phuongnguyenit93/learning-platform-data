# Calling functions in SQL, purity, and side-effect restrictions

Oracle allows calling stored functions in many SQL expressions, such as the SELECT list, WHERE, ORDER BY, GROUP BY, or expressions in INSERT/UPDATE/MERGE. This capability helps encapsulate calculation rules and reuse logic across SQL statements. However, a function called from SQL executes in a context with specific restrictions on data types, DML, transaction control, package state, and parallel execution.

A function suitable for calling from SQL should have clear inputs, return a result based on those inputs, not modify data, not depend on mutable state outside its parameters, and not perform side effects such as sending emails, writing files, or calling external services. That is the mindset of **purity**. The closer a function is to pure, the more predictable its results, the more opportunities the optimizer has to optimize, and the safer it is to reuse across many SQL statements.

After this lesson, you will be able to:

- Create standalone functions and package functions that can be called from SQL.
- Call functions in SELECT, WHERE, and DML expressions.
- Distinguish PL/SQL-only functions from SQL-callable functions.
- Explain purity, determinism, and side effects.
- Understand restrictions on DML, COMMIT/ROLLBACK, DDL, and accessing mutating tables.
- Recognize errors such as ORA-14551, ORA-14552, and ORA-04091.
- Understand why a function may be called more times, fewer times than expected, or in a different order.
- Distinguish DETERMINISTIC from RESULT_CACHE.
- Recognize SQL/PLSQL context-switching overhead and row-by-row function invocation issues.
- Design safe functions, test them, and manage dependencies in packages.

> Some restrictions on data types and calling functions from SQL vary by Oracle release. Examples prioritize common SQL types such as NUMBER, VARCHAR2, and DATE. Verify exact syntax/capabilities for your target release.

## 1. PL/SQL functions and SQL-callable functions

### 1.1. What is a function?

A function is a PL/SQL subprogram that returns a value via the RETURN clause. A function can accept IN parameters, perform calculations or query data, and return the result to the caller.

Example of a function calculating price after tax:

```sql
CREATE OR REPLACE FUNCTION lab_price_with_tax (
    p_net_amount IN NUMBER,
    p_tax_rate   IN NUMBER
)
RETURN NUMBER
IS
BEGIN
    RETURN p_net_amount * (1 + p_tax_rate);
END;
/
```

It can be called from PL/SQL:

```sql
DECLARE
    l_total NUMBER;
BEGIN
    l_total := lab_price_with_tax(100, 0.10);
    DBMS_OUTPUT.PUT_LINE(l_total);
END;
/
```

Because the function is stored in the database and uses SQL-compatible data types, it can also be called in a SQL statement:

```sql
SELECT lab_price_with_tax(100, 0.10) AS gross_amount
FROM dual;
```

The result is 110.

### 1.2. Functions used in PL/SQL are not automatically usable in SQL

A function can be valid in PL/SQL yet not callable directly from SQL if its signature uses PL/SQL-only data types or constructs not supported by the SQL engine in that release.

For example, PL/SQL BOOLEAN has traditionally been a PL/SQL-only type; in Oracle releases prior to SQL BOOLEAN support, a function returning BOOLEAN cannot be used as a regular SQL expression. Oracle Database 23ai adds SQL BOOLEAN support, so consider the version when designing signatures.

Similarly, PL/SQL records, associative arrays, or collection types declared only inside a block do not automatically become SQL data types that can cross into the SQL engine. When collections/objects are needed in SQL, choose schema-level SQL types or package/type constructs supported by the version.

### 1.3. Standalone function

A standalone function is created independently in a schema:

```sql
CREATE OR REPLACE FUNCTION lab_normalize_code (
    p_code IN VARCHAR2
)
RETURN VARCHAR2
IS
BEGIN
    RETURN UPPER(TRIM(p_code));
END;
/
```

Calling from SQL:

```sql
SELECT lab_normalize_code('  ab-123  ') AS normalized_code
FROM dual;
```

The result is AB-123.

### 1.4. Package function

A function can also be a public subprogram in a package. The function must appear in the package specification for code outside the package to call it:

```sql
CREATE OR REPLACE PACKAGE lab_pricing_pkg AS
    FUNCTION price_with_tax (
        p_net_amount IN NUMBER,
        p_tax_rate   IN NUMBER
    ) RETURN NUMBER;
END lab_pricing_pkg;
/

CREATE OR REPLACE PACKAGE BODY lab_pricing_pkg AS
    FUNCTION price_with_tax (
        p_net_amount IN NUMBER,
        p_tax_rate   IN NUMBER
    ) RETURN NUMBER
    IS
    BEGIN
        RETURN p_net_amount * (1 + p_tax_rate);
    END price_with_tax;
END lab_pricing_pkg;
/
```

Calling from SQL using the package name:

```sql
SELECT lab_pricing_pkg.price_with_tax(100, 0.08)
       AS gross_amount
FROM dual;
```

A function declared only in the package body (a private function) cannot be called directly from SQL outside the package.

## 2. Calling functions in SQL expressions

### 2.1. In the SELECT list

```sql
SELECT
    product_id,
    unit_price,
    lab_price_with_tax(unit_price, 0.08) AS price_after_tax
FROM lab_products;
```

The function is called to compute the expression for the result rows. If the query returns many rows, the function may be evaluated many times. Do not assume a single invocation for the entire statement.

### 2.2. In WHERE

```sql
SELECT employee_id, employee_name
FROM lab_employees
WHERE lab_normalize_code(employee_code) = 'EMP-001';
```

A function in WHERE can be evaluated when Oracle checks the predicate for candidate rows. This can incur high cost if the function contains complex logic or internal SQL queries.

### 2.3. In ORDER BY

```sql
SELECT product_id, product_name
FROM lab_products
ORDER BY lab_normalize_code(product_name);
```

Oracle may need to compute the expression for sorting. If the function is expensive and the query returns many rows, consider storing the normalized value, using a direct SQL expression, or using a function-based index if appropriate.

### 2.4. In GROUP BY

```sql
SELECT
    lab_normalize_code(region_code) AS normalized_region,
    COUNT(*) AS customer_count
FROM lab_customers
GROUP BY lab_normalize_code(region_code);
```

The function is used to form the grouping key. The GROUP BY expression must match the SELECT expression per SQL rules; SELECT aliases cannot always be used in GROUP BY across all versions/syntaxes.

### 2.5. In DML

Functions can be called in DML expressions:

```sql
UPDATE lab_products
SET gross_price = lab_price_with_tax(net_price, tax_rate)
WHERE product_status = 'ACTIVE';
```

Here, the function only calculates and returns a value. The DML itself is the outer UPDATE statement. The function does not need to run its own UPDATE or COMMIT to produce the result.

### 2.6. In INSERT ... SELECT

```sql
INSERT INTO lab_price_snapshot (
    product_id,
    gross_price,
    captured_at
)
SELECT
    product_id,
    lab_price_with_tax(net_price, tax_rate),
    SYSTIMESTAMP
FROM lab_products
WHERE product_status = 'ACTIVE';
```

The function is used as an expression computing a value for the inserted row. If the source query returns many rows, the function may be called per row according to the execution strategy chosen by Oracle.

### 2.7. In MERGE

```sql
MERGE INTO lab_products t
USING lab_product_stage s
ON (t.product_id = s.product_id)
WHEN MATCHED THEN
    UPDATE SET
        t.gross_price =
            lab_price_with_tax(s.net_price, s.tax_rate)
WHEN NOT MATCHED THEN
    INSERT (
        product_id, gross_price
    )
    VALUES (
        s.product_id,
        lab_price_with_tax(s.net_price, s.tax_rate)
    );
```

The function is called in the UPDATE/INSERT expressions. Keep the function free of side effects so that optimizer changes to evaluation order or call count do not alter business behavior.

## 3. What is a pure function?

### 3.1. Practical definition

A pure function can be understood as a function where:

- The result depends solely on the input parameters.
- The same inputs under the same conventions yield the same output.
- It does not modify database data.
- It does not modify package/global state.
- It does not depend on time, current user, NLS settings, session context, or external state unless those values are passed as parameters.
- It does not send emails, make HTTP calls, write files, write out-of-band logs, or cause other side effects.

Pure example:

```sql
CREATE OR REPLACE FUNCTION lab_net_to_gross (
    p_net   IN NUMBER,
    p_rate  IN NUMBER
)
RETURN NUMBER
IS
BEGIN
    RETURN p_net + (p_net * p_rate);
END;
/
```

The function only performs arithmetic on the two parameters. The same p_net and p_rate always produce the same result.

### 3.2. Is a function that reads a table still pure?

Function reading a configuration table:

```sql
CREATE OR REPLACE FUNCTION lab_get_tax_rate (
    p_region IN VARCHAR2
)
RETURN NUMBER
IS
    l_rate NUMBER;
BEGIN
    SELECT tax_rate
    INTO l_rate
    FROM lab_tax_rates
    WHERE region_code = p_region;

    RETURN l_rate;
END;
/
```

This function does not write data, but its result depends on the state of the LAB_TAX_RATES table. If the table changes, the same p_region parameter can return a different result. Therefore, it is not pure in the strict sense of "depending only on parameters" and should not be marked DETERMINISTIC without additional guarantees.

Reading data is not a write side effect, yet it is still an external dependency that causes the result to vary over time.

### 3.3. What is a side effect?

A side effect is an action that alters observable state beyond the returned value. Examples:

- INSERT/UPDATE/DELETE on a table.
- Modifying package variables or global state.
- Writing audit/log rows to a table.
- Calling sequence NEXTVAL.
- Sending an email or calling a REST API.
- Writing a file or performing filesystem operations.
- COMMIT/ROLLBACK on a transaction.
- Altering session settings.

A function that returns the right value while also sending an email still has a side effect. It should not be called as a pure SQL expression.

### 3.4. Purity is more than just the absence of DML

A function that does not UPDATE a table but reads SYSDATE, SYS_CONTEXT, package variables, or NLS settings can still return different results for the same parameters. If such a function is declared deterministic or used in an index/cache without accounting for these dependencies, results can be stale or wrong.

Example of a time-dependent function:

```sql
CREATE OR REPLACE FUNCTION lab_is_expired (
    p_expiry_date IN DATE
)
RETURN NUMBER
IS
BEGIN
    IF p_expiry_date < SYSDATE THEN
        RETURN 1;
    END IF;
    RETURN 0;
END;
/
```

The same p_expiry_date can return 0 today and 1 tomorrow. Do not declare this function DETERMINISTIC.

## 4. Side-effect restrictions when calling functions from SQL

Oracle enforces restrictions on functions running inside SQL because the SQL engine needs an expression that can be evaluated during statement optimization and execution. A function must not silently mutate the database or control transactions while Oracle is computing query results.

### 4.1. Functions called from SELECT cannot perform regular DML

Example of a function attempting to INSERT a log row:

```sql
CREATE OR REPLACE FUNCTION lab_log_and_return (
    p_value IN NUMBER
)
RETURN NUMBER
IS
BEGIN
    INSERT INTO lab_function_log (
        value_logged,
        logged_at
    )
    VALUES (
        p_value,
        SYSTIMESTAMP
    );

    RETURN p_value;
END;
/
```

When called:

```sql
SELECT lab_log_and_return(10)
FROM dual;
```

Oracle typically reports:

```text
ORA-14551: cannot perform a DML operation inside a query
```

Reason: SELECT is expected to read data; having a SELECT expression silently write logs would create unpredictable side effects. Oracle disallows regular DML inside functions called from queries.

### 4.2. Autonomous transactions are a technical exception, not a default design

PL/SQL provides PRAGMA AUTONOMOUS_TRANSACTION. An autonomous function/procedure runs in an independent transaction and can COMMIT on its own; this can allow logging from a function called inside SELECT.

Illustrative example:

```sql
CREATE OR REPLACE FUNCTION lab_autonomous_log (
    p_value IN NUMBER
)
RETURN NUMBER
IS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO lab_function_log (
        value_logged,
        logged_at
    )
    VALUES (
        p_value,
        SYSTIMESTAMP
    );

    COMMIT;
    RETURN p_value;
END;
/
```

This is a special-purpose technique, not a way to turn a function with side effects into a safe SQL function. If a query reads 1 million rows, the function could write logs a huge number of times; the optimizer can alter invocation counts; logs commit independently even if the outer query fails or the caller's transaction rolls back.

Only consider autonomous transactions for narrow goals such as writing diagnostic logs that must persist independently, with bounded invocation counts and clearly understood semantics. Never use them to update business data from a function inside SELECT.

### 4.3. Functions called from DML cannot modify the table being modified by that DML

Suppose an UPDATE modifies LAB_ORDERS while a function called in the expression tries to query or update LAB_ORDERS itself:

```sql
UPDATE lab_orders
SET status = lab_change_order_status(order_id)
WHERE order_date < DATE '2025-01-01';
```

If LAB_CHANGE_ORDER_STATUS performs an invalid query or DML against the very table being modified by the UPDATE statement, Oracle may raise a mutating-table error:

```text
ORA-04091: table is mutating, trigger/function may not see it
```

Do not design functions called from DML to read from or write back to the table being modified by the statement. Convert the logic to set-based SQL, use a staging table, or reorganize the transaction so data is read/written in an appropriate separate step.

### 4.4. Do not COMMIT or ROLLBACK inside functions called from SQL

A function called from a query or DML statement must not terminate the calling SQL statement's transaction. Attempting transaction control or DDL can result in:

```text
ORA-14552: cannot perform a DDL, commit or rollback inside a query or DML
```

DDL typically triggers an implicit commit, so never run DDL from a function used in a SQL expression. The transaction belongs under the caller's control; an orchestrating procedure is usually the appropriate place to decide COMMIT/ROLLBACK.

### 4.5. DML on another table inside a function called from DML

Restrictions on the table being modified by the statement must be distinguished from a function performing DML on a different table. Some contexts may allow affecting another table, yet it remains a side effect and can cause transaction errors, unpredictable results, or unstable write counts.

The safe design remains having SQL-callable functions only calculate and return values. If auditing or updating a related table is required, perform it via explicit DML in the orchestrating procedure/transaction rather than hiding it inside an expression.

### 4.6. Restrictions apply across the entire call chain

If function A calls function B, which calls procedure C that performs DML, the side effect still occurs in the call chain. You cannot bypass the restriction by moving DML into a helper procedure or another package.

When investigating ORA-14551/ORA-14552/ORA-04091, trace the full call stack and check whether the function invokes any helpers, triggers, dynamic SQL, or package procedures.

## 5. SQL engine and PL/SQL engine: context-switching cost

Oracle has a SQL engine that executes SQL statements and a PL/SQL engine that executes blocks/procedures/functions. When SQL calls a PL/SQL function, switching control between the two engines incurs overhead. If the function is invoked for many rows, this cost can accumulate significantly.

### 5.1. Row-by-row function calls

Example:

```sql
SELECT
    order_id,
    lab_price_with_tax(net_amount, tax_rate)
FROM lab_orders;
```

If the table has 5 million rows, the function may be called repeatedly for the rows being calculated. Even a simple function that just multiplies two numbers can introduce much higher overhead than a pure SQL expression:

```sql
SELECT
    order_id,
    net_amount * (1 + tax_rate) AS gross_amount
FROM lab_orders;
```

If a calculation can be expressed directly in SQL, prefer set-based SQL to avoid unnecessary engine switches.

### 5.2. Functions executing internal SELECT statements

The following function queries a configuration table:

```sql
SELECT
    order_id,
    lab_get_tax_rate(region_code)
FROM lab_orders;
```

If there are millions of orders, the function may execute millions of SELECTs against LAB_TAX_RATES. This is the N+1 query pattern: one outer query plus many small queries inside the function.

Replace with a JOIN:

```sql
SELECT
    o.order_id,
    r.tax_rate
FROM lab_orders o
JOIN lab_tax_rates r
  ON r.region_code = o.region_code;
```

A JOIN lets the optimizer see the full data relationship in a single SQL statement, opening up opportunities for choosing join methods, access paths, and join order.

### 5.3. Do not repeat the same calculation in multiple places

Example:

```sql
SELECT
    lab_expensive_calc(amount) AS calculated_value
FROM lab_orders
WHERE lab_expensive_calc(amount) > 100;
```

Do not rely on the assumption that Oracle calculates the function once and reuses it for both the SELECT list and WHERE. The optimizer may evaluate expressions at different steps, transform the query, or invoke the function a different number of times.

If an intermediate calculated result needs reuse, consider a SQL expression, inline view/CTE, storing a normalized column, a function-based index, or an appropriate result cache mechanism. Even a CTE/inline view is not an absolute guarantee that the function runs only once; the optimizer may inline or transform the query.

### 5.4. Functions are not a replacement for JOIN

If a function takes an ID and SELECTs a description from another table, such as GET_CUSTOMER_NAME(customer_id), calling the function row by row is usually less clear than a JOIN:

```sql
-- Row-by-row lookup function:
SELECT
    order_id,
    lab_customer_name(customer_id)
FROM lab_orders;

-- Express the data relationship directly:
SELECT
    o.order_id,
    c.customer_name
FROM lab_orders o
JOIN lab_customers c
  ON c.customer_id = o.customer_id;
```

Functions remain useful for small, reusable calculation rules that are awkward to express in SQL. However, when related data already resides in tables, JOIN is usually the better choice.

## 6. Oracle does not guarantee invocation count or order

A function expression in SQL is not a callback whose execution order is controlled by the programmer. The optimizer can:

- Evaluate a predicate before or after another condition.
- Push a predicate into a view or subquery.
- Eliminate unnecessary expressions.
- Evaluate an expression at a different plan step.
- Execute in parallel or otherwise depending on the plan.
- Call a function multiple times for different rows or expressions.

Therefore, a function in SQL must not depend on how many times it is called, the order in which it is called, or that every row will definitely be evaluated.

### 6.1. Do not use functions to produce sequence side effects

Do not write a function called from SELECT that invokes NEXTVAL and rely on the sequence values reflecting row order:

```sql
SELECT
    order_id,
    lab_next_business_number()
FROM lab_orders
ORDER BY order_date;
```

The optimizer does not guarantee function invocation order matching the final ORDER BY. Result ordering and expression evaluation order are two separate things.

If rows need numbering, use sequences in intentional DML or an explicitly designed INSERT/UPDATE process. Never hide side-effect ID generation inside a function used as a SELECT expression.

### 6.2. Do not send emails or make HTTP calls from a function in SELECT

A function calling an SMTP/REST API may be evaluated multiple times or out of expected order. If the query is re-executed, parallelized, or its plan changes, the number of side effects can change.

Separate reading/computing data from sending notifications. Have a procedure/job/queue worker perform side effects by event ID or deduplication mechanism, rather than calling external services inside SELECT.

### 6.3. Do not rely on predicate evaluation order to avoid errors

Example:

```sql
SELECT *
FROM lab_values
WHERE is_numeric(value_text) = 1
  AND TO_NUMBER(value_text) > 100;
```

Do not assume Oracle always evaluates IS_NUMERIC before TO_NUMBER. The optimizer can reorder predicates; rows with non-numeric data can still trigger conversion errors.

Write a safer expression using CASE:

```sql
SELECT *
FROM lab_values
WHERE CASE
          WHEN VALIDATE_CONVERSION(value_text AS NUMBER) = 1
          THEN TO_NUMBER(value_text)
      END > 100;
```

VALIDATE_CONVERSION is available in modern Oracle releases; if your release does not support it, use an appropriate CASE/safe conversion expression. Do not use a function predicate as an evaluation-order guard.

## 7. DETERMINISTIC: declaring determinism

### 7.1. Syntax

A function can be declared DETERMINISTIC:

```sql
CREATE OR REPLACE FUNCTION lab_normalize_code (
    p_code IN VARCHAR2
)
RETURN VARCHAR2
DETERMINISTIC
IS
BEGIN
    RETURN UPPER(TRIM(p_code));
END;
/
```

DETERMINISTIC is a programmer's promise that the function returns the same result for the same set of input parameters within the function's semantics. Oracle does not analyze all logic to prove this promise is true.

### 7.2. DETERMINISTIC does not mean "runs only once"

DETERMINISTIC does not guarantee:

- That the function is called only once per statement.
- That Oracle always caches the result.
- That the function is called in a specific order.
- That every execution of a query reuses old results.
- That the function automatically becomes faster.

It is metadata that Oracle can use in certain optimizations/structures that depend on functions; do not use it as a mechanism to control invocation counts.

### 7.3. Do not declare DETERMINISTIC for functions depending on state outside parameters

Do not declare DETERMINISTIC if the function depends on:

- SYSDATE, SYSTIMESTAMP, or current time.
- Sequence NEXTVAL.
- Table data that can change.
- Mutable package global variables.
- SYS_CONTEXT, SESSION_USER, or current tenant.
- NLS settings, time zone, or session configuration.
- Files, HTTP services, or external state outside the database.

For example, a function reading a tax rate from a config table can return different results after the table changes; it should not be declared DETERMINISTIC merely because a region usually has the same rate during the day.

### 7.4. DETERMINISTIC and function-based indexes

A function-based index stores the result of an expression for each row. Example:

```sql
CREATE INDEX ix_lab_customer_code_norm
ON lab_customers (lab_normalize_code(customer_code));
```

Functions used in function-based indexes must meet Oracle's requirements, including declaring user-defined functions DETERMINISTIC. More importantly, the function must genuinely be stable with respect to inputs and data rules.

If you change the function's implementation, the index may still hold values computed under the old logic. Consider rebuilding the index and testing queries after modifying the function. DETERMINISTIC does not automatically update stored entries.

### 7.5. DETERMINISTIC is a contract

If a function declares DETERMINISTIC while actually reading tables, time, or package state, Oracle may reuse results based on a false assumption. The consequence can be wrong query results or indexes/materialized structures becoming inconsistent with intended logic.

Only declare it when you can prove the same parameters always yield the same result and the function has no side effects. When in doubt, omit DETERMINISTIC.

## 8. RESULT_CACHE and how it differs from DETERMINISTIC

### 8.1. RESULT_CACHE is a result-caching mechanism

A PL/SQL function can be declared RESULT_CACHE so Oracle caches results by parameter values in the instance's result cache. When called again with the same parameters and all dependencies remain valid, Oracle can return the cached result instead of re-executing the function body.

Example of a function reading an exchange rate table:

```sql
CREATE OR REPLACE FUNCTION lab_get_exchange_rate (
    p_currency_code IN VARCHAR2
)
RETURN NUMBER
RESULT_CACHE
IS
    l_rate NUMBER;
BEGIN
    SELECT exchange_rate
    INTO l_rate
    FROM lab_exchange_rates
    WHERE currency_code = p_currency_code;

    RETURN l_rate;
END;
/
```

Oracle tracks dependencies of a result-cached function on the tables it reads and can invalidate cached results when dependent data changes. Invalidation mechanisms and cache eligibility depend on object types, version, and environment.

### 8.2. RESULT_CACHE differs from DETERMINISTIC

| Criterion | DETERMINISTIC | RESULT_CACHE |
| --- | --- | --- |
| Meaning | Author promises the same input gives the same output | Oracle has a mechanism to cache function results |
| Does Oracle store results? | Not a guarantee to cache results | Caches results via the result cache mechanism |
| Table dependencies | Does not automatically track table changes to validate the declaration | Oracle tracks supported dependencies and invalidates |
| Side effects | Function must truly be stable; side effects are inappropriate | Result-cached functions also need to be safe and side-effect-free |
| Purpose | Declares determinism, enabling certain optimizations/indexes | Reduces re-execution of functions with reusable results |

Do not treat DETERMINISTIC as a synonym for RESULT_CACHE. A function can be deterministic without Oracle caching its results; a result-cached function can read dependent tables and have its cache invalidated when those tables change.

### 8.3. When to consider RESULT_CACHE?

- The function performs a relatively expensive lookup or computation.
- The same parameter sets are called repeatedly and frequently.
- Source data changes infrequently or invalidations are acceptable.
- Results do not depend on session-specific state.
- Results are small enough to benefit from storage in the shared result cache.

### 8.4. Unsuitable cases

Do not use RESULT_CACHE if the function depends on:

- SYSDATE/SYSTIMESTAMP or time-varying data not passed as a parameter.
- Package global state.
- Session context, current user/tenant, or NLS settings not handled properly.
- Sequences, random numbers, or external services whose results vary.
- Side effects that must occur on every call.

For instance, a function that sends an email cannot be "optimized" with result cache; caching could prevent the function from running again and suppress emails or cause unintended behavior.

### 8.5. Caching is not a business guarantee

Do not rely on whether a function definitely runs or does not run to produce a side effect. Oracle can invalidate or evict the cache, an instance can restart, and results can be recomputed. Function result caching is strictly a performance optimization; it is not a message queue, ledger, or exactly-once mechanism.

## 9. PRAGMA RESTRICT_REFERENCES and purity levels

In PL/SQL, RESTRICT_REFERENCES is a pragma used to assert the degree to which a function reads/writes database state and package state. This mechanism is common in legacy packages or contexts requiring compiler verification/evaluation of purity. For new functions, do not add the pragma purely out of habit; check the requirements of your Oracle release and usage context.

### 9.1. Four common levels

| Level | Meaning |
| --- | --- |
| WNDS | Writes No Database State: does not write database state |
| RNDS | Reads No Database State: does not read database state |
| WNPS | Writes No Package State: does not write package state |
| RNPS | Reads No Package State: does not read package state |

For example, a function computing solely from parameters can declare appropriate levels in the package specification:

```sql
CREATE OR REPLACE PACKAGE lab_math_pkg AS
    FUNCTION add_tax (
        p_amount IN NUMBER,
        p_rate   IN NUMBER
    ) RETURN NUMBER;

    PRAGMA RESTRICT_REFERENCES (
        add_tax,
        WNDS,
        RNDS,
        WNPS,
        RNPS
    );
END lab_math_pkg;
/
```

This pragma snippet is an example of declaring purity; exact placement and enforcement rules depend on package syntax and the Oracle version in use.

### 9.2. Reading/writing database state

A function containing a SELECT that reads a table does not satisfy RNDS because it reads database state. A function containing INSERT/UPDATE/DELETE does not satisfy WNDS because it writes database state.

A function computing strictly from parameters can satisfy both RNDS and WNDS, provided there is no hidden database access inside helper functions.

### 9.3. Reading/writing package state

A function that reads or modifies a global variable declared in a package can violate RNPS or WNPS respectively. Example:

```sql
CREATE OR REPLACE PACKAGE lab_state_pkg AS
    g_call_count PLS_INTEGER := 0;

    FUNCTION next_call_count RETURN PLS_INTEGER;
END lab_state_pkg;
/

CREATE OR REPLACE PACKAGE BODY lab_state_pkg AS
    FUNCTION next_call_count RETURN PLS_INTEGER
    IS
    BEGIN
        g_call_count := g_call_count + 1;
        RETURN g_call_count;
    END;
END lab_state_pkg;
/
```

NEXT_CALL_COUNT modifies package state and its result depends on call history in the session. Do not consider this function pure or deterministic; do not use it as a SQL expression to generate business sequence numbers.

### 9.4. Pragmas do not replace pure design

RESTRICT_REFERENCES is a purity assertion/check in contexts where Oracle applies it. It does not make a side-effecting function safe, does not protect against effects through external calls not fully analyzed by the compiler, and does not replace reviewing code and helper dependencies. Design side-effect-free functions first; use pragmas only when explicitly required.

## 10. Functions and parallel SQL

Oracle can execute some SQL statements using parallel execution. If SQL calls a user-defined function, whether the function can run inside parallel workers depends on how the function is declared, its characteristics, query type, and version.

### 10.1. PARALLEL_ENABLE

A function can declare PARALLEL_ENABLE when designed to execute safely in parallel execution servers:

```sql
CREATE OR REPLACE FUNCTION lab_parallel_net_amount (
    p_amount IN NUMBER,
    p_discount IN NUMBER
)
RETURN NUMBER
PARALLEL_ENABLE
IS
BEGIN
    RETURN p_amount * (1 - p_discount);
END;
/
```

This function computes solely from parameters without reading/writing session or package state. PARALLEL_ENABLE is an assertion that the function can be called in an appropriate parallel environment; it does not force Oracle to run the query in parallel and does not make an unsafe side-effecting function safe.

### 10.2. Why are side effects dangerous in parallel queries?

If a function sends emails, writes logs, or increments a package variable during a parallel query, workers can execute in separate sessions. There is no single shared package variable updated in row order as an author might imagine. Invocation counts and execution order are also non-deterministic.

Do not place side effects inside functions used in parallel SQL. Separate reading/computation from writing data or sending messages.

### 10.3. Package state and parallel execution

Package state belongs to a session. Parallel execution workers can have their own sessions/state; do not rely on package variables to share counters or state across workers. If aggregation is required, return data via SQL results, aggregates, or a purpose-built synchronization mechanism.

## 11. Privileges and dependencies of SQL-callable functions

### 11.1. EXECUTE privilege

A user calling a function in SQL needs EXECUTE privilege on the standalone function or the package containing it:

```sql
GRANT EXECUTE ON lab_pricing_pkg TO app;
GRANT EXECUTE ON lab_price_with_tax TO app;
```

The function name may require schema qualification if there is no synonym or the name does not resolve in the current schema:

```sql
SELECT data_owner.lab_price_with_tax(100, 0.08)
FROM dual;
```

### 11.2. Definer's rights and invoker's rights

Stored PL/SQL defaults to running with the owner's privileges (AUTHID DEFINER), unless AUTHID CURRENT_USER is declared. A function's rights model affects how Oracle checks access to objects used by the function.

With a definer-rights function, the owner needs direct object privileges for static SQL per PL/SQL rules; privileges received only via roles are generally insufficient to compile/execute static SQL in a definer-rights unit. When a function reads a config table, verify direct grants to the owner.

### 11.3. Function dependencies and invalidation

A function can depend on tables, views, packages, types, or other functions. Changes to dependent objects can make the function INVALID or cause SQL calling the function to fail until recompiled.

Inspect objects:

```sql
SELECT
    object_name,
    object_type,
    status
FROM user_objects
WHERE object_name IN (
    'LAB_PRICE_WITH_TAX',
    'LAB_PRICING_PKG'
);
```

Inspect dependencies:

```sql
SELECT
    name,
    type,
    referenced_owner,
    referenced_name,
    referenced_type
FROM user_dependencies
WHERE name IN (
    'LAB_PRICE_WITH_TAX',
    'LAB_PRICING_PKG'
)
ORDER BY name, referenced_owner, referenced_name;
```

Dynamic SQL may not generate complete dependency metadata like static SQL. Search source code/configuration if the function builds SQL text at runtime.

## 12. Functions in SQL and function-based indexes

A function-based index stores the result of an expression for each row to accelerate lookups by that expression.

### 12.1. Code normalization example

Function:

```sql
CREATE OR REPLACE FUNCTION lab_normalize_email (
    p_email IN VARCHAR2
)
RETURN VARCHAR2
DETERMINISTIC
IS
BEGIN
    RETURN LOWER(TRIM(p_email));
END;
/
```

Index:

```sql
CREATE INDEX ix_lab_email_norm
ON lab_customers (lab_normalize_email(email));
```

Query using the same expression:

```sql
SELECT customer_id, email
FROM lab_customers
WHERE lab_normalize_email(email) = LOWER(TRIM(:email));
```

Oracle can use the function-based index if the expression, statistics, and cost estimate align.

### 12.2. Functions must be stable

Functions used in function-based indexes must meet DETERMINISTIC requirements and be genuinely stable. Do not use functions that read exchange-rate tables, SYSDATE, session context, or package variables as index keys if values can change without the index being recomputed accordingly.

If you modify the function's logic, consider rebuilding the index so expression values are recomputed. Recompiling a function does not automatically guarantee all stored index entries reflect the new implementation.

### 12.3. Wrapping a column in a function can disable regular index access

If there is a B-tree index on EMAIL but the query writes:

```sql
WHERE LOWER(TRIM(email)) = :normalized_email
```

the regular index on EMAIL may not be usable for a direct equality lookup on the transformed expression. A function-based index on the same expression can help, or the application can store a separate normalized column and ensure normalization on write.

### 12.4. Checking the execution plan

```sql
EXPLAIN PLAN FOR
SELECT customer_id
FROM lab_customers
WHERE lab_normalize_email(email) = LOWER(TRIM('A@EXAMPLE.COM'));

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Do not conclude an index was ignored solely because the plan has no INDEX RANGE SCAN; a full scan may be cheaper if the table is small or the predicate selects most rows.

## 13. Functions declared directly inside a SQL statement

Starting in Oracle Database 12c, SQL can declare local PL/SQL functions in the WITH clause of a query. This function is scoped strictly to that statement, not stored long-term as a standalone or package function.

Example:

```sql
WITH
    FUNCTION local_gross_price (
        p_net_amount NUMBER,
        p_tax_rate   NUMBER
    ) RETURN NUMBER
    IS
    BEGIN
        RETURN p_net_amount * (1 + p_tax_rate);
    END;
SELECT local_gross_price(100, 0.08) AS gross_amount
FROM dual;
```

Local functions are useful when logic is only needed in one query without creating a schema object. However:

- It is still PL/SQL called in SQL, so appropriate side-effect restrictions must be respected.
- It cannot be called from other SQL statements outside the declaring statement.
- It does not replace shared package functions.
- Syntax and client/tool requirements may vary by release.

If the function needs reuse across multiple SQL statements or separate EXECUTE privileges, create a standalone/package function.

## 14. Safe design patterns

### 14.1. Functions that compute strictly from parameters

This is the preferred choice for SQL-callable functions:

```sql
CREATE OR REPLACE FUNCTION lab_discounted_price (
    p_price    IN NUMBER,
    p_discount IN NUMBER
)
RETURN NUMBER
IS
BEGIN
    RETURN p_price * (1 - p_discount);
END;
/
```

Call:

```sql
SELECT
    product_id,
    lab_discounted_price(unit_price, discount_rate) AS final_price
FROM lab_products;
```

The function does not need to access tables, write logs, or change state. If the calculation is short and expressible directly in SQL, compare against an inline expression to reduce overhead.

### 14.2. Use JOIN for lookup data

If a function merely looks up an attribute from another table, prefer JOIN:

```sql
-- Can cause one lookup per row:
SELECT
    o.order_id,
    lab_customer_segment(o.customer_id)
FROM lab_orders o;

-- Express data relationship directly:
SELECT
    o.order_id,
    c.segment_code
FROM lab_orders o
JOIN lab_customers c
  ON c.customer_id = o.customer_id;
```

JOIN lets the optimizer see the relationship between the two tables and is generally easier to extend when additional filters or aggregations are needed.

### 14.3. Separate computation from writing data

If a value needs to be computed and then written, let the function only compute and let a procedure/SQL orchestrate DML:

```sql
CREATE OR REPLACE PROCEDURE recalculate_product_prices
AS
BEGIN
    UPDATE lab_products
    SET gross_price =
        lab_discounted_price(unit_price, discount_rate);
END;
/
```

Here the procedure performs the explicit UPDATE; the function only returns a value. The caller decides COMMIT/ROLLBACK.

### 14.4. Write audits via explicit DML

Do not write a function inside SELECT to both return a value and write audit rows. If business rules require auditing an update command, execute the main DML, capture the row count, and write the audit inside the procedure:

```sql
CREATE OR REPLACE PROCEDURE deactivate_old_customers (
    p_cutoff_date IN DATE,
    p_rows_updated OUT PLS_INTEGER
)
AS
BEGIN
    UPDATE lab_customers
    SET status = 'INACTIVE'
    WHERE last_order_date < p_cutoff_date
      AND status = 'ACTIVE';

    p_rows_updated := SQL%ROWCOUNT;

    INSERT INTO lab_audit_log (
        action_name, affected_rows, created_at
    )
    VALUES (
        'DEACTIVATE_OLD_CUSTOMERS',
        p_rows_updated,
        SYSTIMESTAMP
    );
END;
/
```

The business update and audit row belong to the same transaction; the caller can commit both or roll back both.

### 14.5. Return business status using SQL types

If a function needs to return a status, use a SQL data type compatible with your version and application contract, such as NUMBER or VARCHAR2:

```sql
CREATE OR REPLACE FUNCTION lab_is_valid_amount (
    p_amount IN NUMBER
)
RETURN NUMBER
IS
BEGIN
    RETURN CASE
        WHEN p_amount IS NOT NULL AND p_amount >= 0 THEN 1
        ELSE 0
    END;
END;
/
```

SQL:

```sql
SELECT order_id
FROM lab_orders
WHERE lab_is_valid_amount(total_amount) = 1;
```

Inside internal PL/SQL, BOOLEAN may be more natural; when a function must be called from SQL, choose a return type supported by SQL in your release.

## 15. Anti-patterns to avoid

### 15.1. Hidden DML inside a function called in SELECT

A SELECT appears read-only, yet the function silently inserts/updates logs or business tables. The result is ORA-14551 or needing autonomous transactions to bypass restrictions. Extract side effects into a separate step.

### 15.2. Function querying the same table being modified by DML

A function called from UPDATE/DELETE that reads from or writes back to the table being modified by the statement can trigger ORA-04091. Move logic to set-based SQL, staging, or a separate processing step.

### 15.3. Marking DETERMINISTIC on functions depending on mutable data

Reading tables, SYSDATE, sequences, or package state while declaring DETERMINISTIC can cause Oracle to rely on a false promise. Only declare it when results genuinely depend solely on parameters.

### 15.4. Using a function in WHERE for every row when a JOIN works

A function looking up data in another table row-by-row causes excessive PL/SQL/SQL calls. Use a JOIN or set-based SQL expression.

### 15.5. Relying on predicate evaluation order

Do not assume a data-validation condition will always be evaluated before TO_NUMBER. The optimizer can reorder predicates; write CASE or safe conversion expressions.

### 15.6. Using package variables as counters inside SQL

Package state belongs to the session and is not a row-ordered counter. In parallel execution, workers have separate state. If you need a sequence, use an explicit sequence; if you need aggregation, use aggregates or tables/sequences with matching semantics.

### 15.7. Calling external services from functions

Sending emails, making HTTP calls, or writing files inside SQL functions causes the number of side effects to depend on how the statement is executed. Use jobs, queues, outboxes, or procedures invoked once at a business boundary.

### 15.8. Oversized functions in SELECT

Functions containing multiple SELECTs, complex PL/SQL branches, and numerous helper calls are hard to optimize and hide costs from execution plans. Move data transformations into set-based SQL whenever possible; keep functions for well-bounded calculation rules.

## 16. Hands-on practice: pure functions and functions with side effects

The following steps run in a lab schema. Create tables once; change the prefix if names already exist.

### 16.1. Create the products table

```sql
CREATE TABLE lab_sql_products (
    product_id NUMBER(10) PRIMARY KEY,
    product_name VARCHAR2(100) NOT NULL,
    net_price NUMBER(12, 2) NOT NULL,
    tax_rate NUMBER(5, 4) NOT NULL,
    gross_price NUMBER(12, 2)
);

INSERT INTO lab_sql_products VALUES
(1, 'Keyboard', 500000, 0.08, NULL);
INSERT INTO lab_sql_products VALUES
(2, 'Monitor', 3000000, 0.10, NULL);
INSERT INTO lab_sql_products VALUES
(3, 'Mouse', 250000, 0.08, NULL);
COMMIT;
```

### 16.2. Create a pure function

```sql
CREATE OR REPLACE FUNCTION lab_sql_gross_price (
    p_net_price IN NUMBER,
    p_tax_rate  IN NUMBER
)
RETURN NUMBER
IS
BEGIN
    RETURN p_net_price * (1 + p_tax_rate);
END;
/
```

Call from SQL:

```sql
SELECT
    product_id,
    product_name,
    lab_sql_gross_price(net_price, tax_rate) AS gross_price
FROM lab_sql_products
ORDER BY product_id;
```

The result must be the tax-included prices for the three products.

### 16.3. Use the function in UPDATE

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE lab_sql_products
    SET gross_price =
        lab_sql_gross_price(net_price, tax_rate);

    l_rows := SQL%ROWCOUNT;
    DBMS_OUTPUT.PUT_LINE('Updated rows = ' || l_rows);
END;
/
```

Expected result with sample data: 3 rows updated. If you do not want to keep the changes, ROLLBACK in the caller; if you want to keep them, COMMIT per lab procedures.

### 16.4. Create a function attempting to write logs

```sql
CREATE TABLE lab_sql_function_log (
    log_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    input_value NUMBER,
    logged_at TIMESTAMP
);

CREATE OR REPLACE FUNCTION lab_sql_impure_value (
    p_value IN NUMBER
)
RETURN NUMBER
IS
BEGIN
    INSERT INTO lab_sql_function_log (
        input_value, logged_at
    )
    VALUES (
        p_value, SYSTIMESTAMP
    );

    RETURN p_value;
END;
/
```

Try calling it:

```sql
SELECT lab_sql_impure_value(10)
FROM dual;
```

In a regular query, expect ORA-14551 because the function performs DML. This illustrates side-effect restrictions.

### 16.5. Test a controlled autonomous transaction

In the lab schema, you can create an autonomous version to observe the technical exception:

```sql
CREATE OR REPLACE FUNCTION lab_sql_autonomous_log (
    p_value IN NUMBER
)
RETURN NUMBER
IS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO lab_sql_function_log (
        input_value, logged_at
    )
    VALUES (
        p_value, SYSTIMESTAMP
    );

    COMMIT;
    RETURN p_value;
END;
/
```

Run SELECT on the function and check the log table. Then roll back the caller transaction (if any) and observe that the autonomous log remains because it committed independently. This lab demonstrates why autonomous transactions should not be used to silently write business data inside SELECT.

### 16.6. Test a time-dependent function

```sql
CREATE OR REPLACE FUNCTION lab_sql_is_past (
    p_date IN DATE
)
RETURN NUMBER
IS
BEGIN
    RETURN CASE
        WHEN p_date < SYSDATE THEN 1
        ELSE 0
    END;
END;
/
```

Calling with the same date at different times can return different results. Do not declare this function DETERMINISTIC and do not use it in a function-based index assuming invariant results.

### 16.7. Clean up lab data

Drop test objects only when no longer needed:

```sql
DROP FUNCTION lab_sql_is_past;
DROP FUNCTION lab_sql_autonomous_log;
DROP FUNCTION lab_sql_impure_value;
DROP FUNCTION lab_sql_gross_price;
DROP TABLE lab_sql_function_log PURGE;
DROP TABLE lab_sql_products PURGE;
```

If an object has not been created or was already dropped, the corresponding DROP statement will report an error. Run only in the lab schema.

## 17. Common errors and resolution

| Error/symptom | Possible cause | Resolution |
| --- | --- | --- |
| ORA-14551 | Function called from query performs regular DML | Remove DML from function; move to procedure/transaction |
| ORA-14552 | Function called from query/DML performs DDL, COMMIT, or ROLLBACK | Let caller control transactions and DDL |
| ORA-04091 | Function/trigger reads or modifies table currently being modified by DML | Move logic to set-based statement or separate step |
| ORA-06575 | Function is invalid or has compile errors | Check USER_ERRORS, recompile, and check dependencies |
| ORA-00904 / function not recognized | Wrong name/schema/package or signature | Check owner, package spec, synonym, and EXECUTE privilege |
| ORA-06553 / PLS-... when calling from SQL | Parameter/return type incompatible with SQL or wrong signature | Use SQL types supported in the release |
| ORA-01031 | Missing EXECUTE or direct object privilege for definer-rights unit | Grant appropriate privileges and check AUTHID |
| DETERMINISTIC results are stale/wrong | Function depends on tables, time, session, or package state | Remove DETERMINISTIC; use proper caching/dependency tracking |
| Function called too many times | SQL calls function across many rows/expressions | Use set-based SQL, JOIN, reduce rows before calling |
| Query skips regular index | Function wraps column in predicate | Consider function-based index or normalized column |
| Function with side effects runs unexpected times | Optimizer alters plan/evaluation | Remove side effects from SQL functions |
| Parallel query gives inconsistent state results | Function relies on package/session state or side effects | Use stateless functions, check PARALLEL_ENABLE |

## 18. Checking functions and compile status

### 18.1. Viewing functions in the schema

```sql
SELECT
    object_name,
    object_type,
    status
FROM user_objects
WHERE object_type IN ('FUNCTION', 'PACKAGE', 'PACKAGE BODY')
ORDER BY object_type, object_name;
```

### 18.2. Viewing compile errors

```sql
SELECT
    name,
    type,
    line,
    position,
    text
FROM user_errors
ORDER BY name, sequence;
```

### 18.3. Recompiling functions

```sql
ALTER FUNCTION lab_sql_gross_price COMPILE;
```

For packages:

```sql
ALTER PACKAGE lab_pricing_pkg COMPILE;
ALTER PACKAGE lab_pricing_pkg COMPILE BODY;
```

Successful compilation does not prove a function is pure or business-correct. Inspect code, dependencies, privileges, and runtime behavior.

### 18.4. Measuring cost

To compare a function against SQL expressions/JOINs:

- Run on the same data and bind values.
- Compare execution plans and actual row counts.
- Observe elapsed time, CPU, buffer gets, and physical reads.
- Run enough iterations to separate parsing, cache warm-up, and execution.
- Measure both function overhead and SQL cost inside the function.
- Never draw conclusions from a single run.

SQL Trace/TKPROF or SQL Monitor (with appropriate privileges and licensing) can help investigate complex queries. Do not enable broad tracing in production without planning for overhead and storage.

## 19. Best-practice principles

1. **Keep SQL-callable functions as pure as possible.** Accept parameters, compute, return a result.
2. **Never hide DML inside SELECT.** Move data modifications to procedures or explicit DML.
3. **Never COMMIT/ROLLBACK/DDL inside SQL functions.** The caller controls the transaction.
4. **Avoid accessing the table being modified by the statement.** Use set-based design or separate steps.
5. **Use JOIN instead of row-by-row lookup functions.** Let the optimizer see data relationships.
6. **Never assume invocation count or order.** The SQL optimizer may transform the plan.
7. **Declare DETERMINISTIC only when genuinely true.** Same inputs must yield same outputs; no dependency on mutable external state.
8. **Distinguish RESULT_CACHE from DETERMINISTIC.** One caches results; the other promises determinism.
9. **Do not use autonomous transactions to mask side effects.** Restrict to narrow independent needs such as evaluated diagnostic logging.
10. **Verify SQL data types.** Function signatures must be compatible with the release's SQL engine.
11. **Be careful with package state.** Session state makes functions unpredictable and unsuitable for parallel execution.
12. **Use PARALLEL_ENABLE responsibly.** Declare only if the function is truly safe in parallel workers.
13. **Evaluate function-based indexes carefully.** Functions must be stable and logic changes may require rebuilding the index.
14. **Manage EXECUTE privileges and direct grants.** Check definer/invoker rights.
15. **Monitor dependencies and compile status.** Table/package changes can make functions INVALID.
16. **Benchmark both queries and DML.** Functions may be convenient to reuse but cause context switches or N+1 SQL.

## 20. Self-check questions

1. How does a PL/SQL function differ from a procedure?
2. Can a function created in a package body without appearing in the package spec be called directly from external SQL?
3. Why might a function using PL/SQL-only types not be callable from SQL?
4. Which places in SQL can commonly call functions?
5. What factors should a pure function depend on to return its result?
6. Is reading a configuration table a write side effect? Why does it still affect purity?
7. Why can a function that writes to a table and is called from SELECT receive ORA-14551?
8. How can autonomous transactions alter that behavior, and why should they not be overused?
9. Which actions typically trigger ORA-14552?
10. Why should a function called from UPDATE not access the table currently being updated?
11. Why does a side effect in a helper function still count as a side effect of the call chain?
12. How can SQL engine/PLSQL engine context switching affect a multi-million-row query?
13. Why is JOIN usually better than a row-by-row SELECT lookup function?
14. Does the optimizer guarantee a function is called once per row or in ORDER BY order?
15. Does DETERMINISTIC automatically cache results?
16. Which dependencies make a function unsuitable for DETERMINISTIC?
17. How does RESULT_CACHE differ from DETERMINISTIC?
18. What do WNDS, RNDS, WNPS, and RNPS describe?
19. Does PARALLEL_ENABLE guarantee that a query runs in parallel?
20. Why must functions used in function-based indexes be stable and considered for index rebuilds when logic changes?
21. When should you use a package function versus WITH FUNCTION?
22. Which privileges must be checked when another user calls a stored function?

## 21. Mental model

```text
SQL CALLS PL/SQL FUNCTION
        |
        v
  SQL-compatible inputs
        |
        v
  COMPUTING FUNCTION
        |
        +-- Pure: output depends on parameters
        +-- No DML/DDL/COMMIT inside queries
        +-- No hidden side effects
        +-- Independent of call order/count
        |
        v
  SQL ENGINE OPTIMIZES AND EXECUTES
        |
        +-- May invoke multiple times
        +-- May reorder evaluation
        +-- May execute in parallel if eligible
        |
        v
  PERFORMANCE MANAGEMENT
        |
        +-- Set-based SQL / JOIN first
        +-- DETERMINISTIC only when accurate
        +-- RESULT_CACHE when beneficial
        +-- Function-based index when needed
        |
        v
  SIDE EFFECTS / TRANSACTIONS
        |
        +-- Explicit procedures/DML
        +-- Caller decides COMMIT/ROLLBACK
        +-- Outbox/job for external services
```

**Key takeaway:** a function called from SQL should primarily be a computational expression that the optimizer can evaluate in a SQL-friendly way. Keep functions pure, avoid hidden DML and transaction control, do not rely on invocation counts/order, and prefer JOINs/set-based SQL when data already lives in tables. DETERMINISTIC is an author's promise; RESULT_CACHE is a caching mechanism; neither turns a side-effecting function into a safe function.
