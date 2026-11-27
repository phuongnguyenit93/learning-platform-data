# Context Switch Cost Between SQL and PL/SQL in Oracle

## 1. SQL Engine and PL/SQL Engine

Oracle Database supports both SQL and PL/SQL, but these two languages are processed by execution components with distinct roles:

- The **SQL engine** parses and executes SQL statements such as `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, JOIN, GROUP BY, and set-based operations.
- The **PL/SQL engine** executes procedural logic such as variables, assignments, IF, LOOP, procedure/function calls, and exception handling.

When a PL/SQL program executes a SQL statement, control transfers from the PL/SQL engine to the SQL engine to execute the SQL statement, and then the result is returned to the PL/SQL engine. This handoff is called a **context switch between SQL and PL/SQL**.

Example:

```sql
DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM employees;

    DBMS_OUTPUT.PUT_LINE('Employees=' || v_count);
END;
/
```

In this example, PL/SQL starts the block, asks the SQL engine to run `SELECT COUNT(*)`, receives the result, and then continues executing `DBMS_OUTPUT.PUT_LINE`.

A single context switch incurs a certain coordination cost. One switch is usually very small, but if a program performs it hundreds of thousands or millions of times, the total cost can become significant. Therefore, when tuning PL/SQL, you must pay attention to the number of round-trips between the two engines, not just the number of lines of code.

This lesson belongs to the **Advanced PL/SQL** chapter, focusing on the causes of context switches, the cost of row-by-row processing, calling PL/SQL functions from SQL, replacing them with set-based processing, using `BULK COLLECT` and `FORALL`, and methods for measuring performance before and after optimization.

## 2. In Which Directions Do Context Switches Occur?

There are two common context switch directions:

1. **PL/SQL calling SQL:** PL/SQL is running a block or loop and executes a SQL statement. Control transfers to the SQL engine and returns when the statement completes or returns a batch of results.
2. **SQL calling PL/SQL:** a SQL statement invokes a stored function or a function in an expression. The SQL engine switches to the PL/SQL engine to run the function and then receives the result.

### 2.1. PL/SQL Calling SQL

```sql
BEGIN
    UPDATE employees
    SET salary = salary * 1.05
    WHERE department_id = 10;
END;
/
```

The PL/SQL block calls a single UPDATE statement. The SQL engine processes the entire set of matching rows in one statement. This is usually more efficient than iterating through each employee and running a separate UPDATE for each row.

### 2.2. SQL Calling PL/SQL

```sql
CREATE OR REPLACE FUNCTION employee_bonus (
    p_salary IN NUMBER
) RETURN NUMBER
AS
BEGIN
    RETURN p_salary * 0.10;
END employee_bonus;
/

SELECT employee_id,
       employee_bonus(salary) AS bonus
FROM employees;
```

The SQL engine processes the query and needs to call the PL/SQL function to calculate the bonus for the result rows. Each time the function is executed, control may need to switch to the PL/SQL engine and back.

Do not assume that a function is always called exactly once per row visible in the result. The optimizer may transform or evaluate expressions differently. The key point is that a PL/SQL function used in SQL can create significant overhead when called repeatedly over large data sets.

### 2.3. Execution Flow Diagram

```text
PL/SQL block
    |
    | Send SQL statement
    v
SQL engine
    |
    | Return result / status
    v
PL/SQL block

SQL statement calling a PL/SQL function:

SQL engine
    |
    | Call function
    v
PL/SQL engine
    |
    | Return value
    v
SQL engine continues processing query
```

The optimization goal is to reduce unnecessary switches, especially in large loops and frequently evaluated function expressions.

## 3. Why Do Many Context Switches Slow Down a Program?

A context switch requires overhead to transfer control, pass parameters, receive results, and resume execution state. A single switch is typically small compared to a complex query, but the iteration count can cause total execution time to rise sharply.

Suppose a block processes 100,000 rows and performs one UPDATE per iteration:

```sql
BEGIN
    FOR r IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = 50
    ) LOOP
        UPDATE employees
        SET salary = salary * 1.05
        WHERE employee_id = r.employee_id;
    END LOOP;
END;
/
```

The flow can be pictured as:

1. The SQL engine returns one row to the PL/SQL loop.
2. PL/SQL extracts the employee ID.
3. PL/SQL sends one UPDATE to the SQL engine.
4. The SQL engine executes the UPDATE and returns the status.
5. PL/SQL proceeds to the next row.

With a set of 100,000 rows, the code can generate a large number of individual DML calls. Each statement also carries parse/execute cost, bind overhead, constraint checks, triggers, index maintenance, redo/undo, and row locking depending on the operation.

Context switches are not the only cost, but they are often a symptom of a row-by-row design that prevents the database from leveraging set-based processing.

## 4. Row-by-Row Processing: A Common Anti-Pattern

Row-by-row processing is the approach of fetching individual rows into PL/SQL and performing a separate operation for each row.

### 4.1. Example: Updating Salary Row by Row

```sql
BEGIN
    FOR r IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = 50
    ) LOOP
        UPDATE employees
        SET salary = salary * 1.05
        WHERE employee_id = r.employee_id;
    END LOOP;
END;
/
```

The code is easy to read for beginners, but if you only need to raise salaries by 5% for all employees in department 50, the loop is unnecessary.

### 4.2. Rewriting with a Single Set-Based SQL Statement

```sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 50;
```

The SQL engine processes the entire set of rows in a single statement. PL/SQL only needs to send the UPDATE once, without coordinating a separate statement for each employee.

### 4.3. Comparison

| Criterion | Row-by-row | Set-based |
|---|---|---|
| Number of DML calls from PL/SQL | Potentially one per row | One statement for the whole set |
| Context switches | Many | Significantly fewer |
| Optimizer visibility into the data set | Small individual operations | All conditions of the statement |
| Ability to optimize JOIN/aggregate | Limited if code is fragmented | SQL engine can optimize holistically |
| Suitability | Logic genuinely requires procedural decisions per row | Transformations expressible in SQL |

### 4.4. Not Every Loop Is Wrong

A loop can be appropriate when:

- Each row must call an API or undergo separate procedural handling.
- Logic depends on the result of the previous row.
- Operations need to be performed that cannot be expressed in a single SQL statement.
- The data set is small and simple.
- Orchestrating multiple different types of work.

Even in those cases, if you can batch data and reduce the number of SQL calls, consider bulk processing.

## 5. Use Set-Based SQL Before Bulk Processing

SQL is inherently designed to operate on data sets. Whenever business logic can be expressed in a single SQL statement, prefer that approach before reaching for `BULK COLLECT` or `FORALL`.

### 5.1. Use UPDATE Instead of a Loop

Row-by-row:

```sql
BEGIN
    FOR r IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = 20
    ) LOOP
        UPDATE employees
        SET commission_pct = 0.10
        WHERE employee_id = r.employee_id;
    END LOOP;
END;
/
```

Set-based:

```sql
UPDATE employees
SET commission_pct = 0.10
WHERE department_id = 20;
```

### 5.2. Use MERGE Instead of Repeated Checks Followed by INSERT/UPDATE

If you need to synchronize a target table from a source table, `MERGE` can process multiple rows in one statement:

```sql
MERGE INTO customer_summary target
USING (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(amount) AS total_amount
    FROM orders
    GROUP BY customer_id
) source
ON (target.customer_id = source.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        target.order_count = source.order_count,
        target.total_amount = source.total_amount
WHEN NOT MATCHED THEN
    INSERT (
        customer_id,
        order_count,
        total_amount
    )
    VALUES (
        source.customer_id,
        source.order_count,
        source.total_amount
    );
```

This example assumes a `CUSTOMER_SUMMARY` table with the corresponding columns. A single MERGE processes the entire source result set instead of PL/SQL looping over each customer and running separate SELECT/UPDATE/INSERT statements.

### 5.3. Use CASE to Express Row-Level Rules

```sql
UPDATE employees
SET salary =
    CASE
        WHEN salary < 5000 THEN salary * 1.10
        WHEN salary < 10000 THEN salary * 1.07
        ELSE salary * 1.03
    END
WHERE department_id = 50;
```

Different branches per row can still be expressed within one SQL statement using `CASE`, avoiding a PL/SQL loop.

### 5.4. Use Analytic Functions Instead of Sequential Calculation

Example: ranking employees by salary within each department:

```sql
SELECT employee_id,
       department_id,
       salary,
       DENSE_RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS salary_rank
FROM employees;
```

If the problem involves ranking, running totals, moving averages, or comparing previous/next rows, analytic functions usually express it better than fetching each row into PL/SQL and computing it manually.

## 6. SQL Calling a PL/SQL Function Row by Row

Another source of context switches is calling a stored function in SELECT, WHERE, ORDER BY, or SQL expressions.

### 6.1. Example: Function Called in SELECT

```sql
CREATE OR REPLACE FUNCTION normalize_email (
    p_email IN VARCHAR2
) RETURN VARCHAR2
AS
BEGIN
    RETURN LOWER(TRIM(p_email));
END normalize_email;
/

SELECT customer_id,
       normalize_email(email) AS normalized_email
FROM customers;
```

The function simply calls `LOWER` and `TRIM`, which are already SQL functions. Wrapping this operation in a PL/SQL function can introduce extra context switches without bringing significant benefit.

Write it directly instead:

```sql
SELECT customer_id,
       LOWER(TRIM(email)) AS normalized_email
FROM customers;
```

### 6.2. Function in WHERE

```sql
SELECT order_id
FROM orders
WHERE calculate_customer_score(customer_id) >= 80;
```

If the function is evaluated for many rows, the SQL engine may have to call the PL/SQL engine repeatedly. In addition to context switches, the function might query other tables, triggering SQL inside SQL and causing an N+1 query cost.

Check whether the function can be replaced with a JOIN, subquery, CASE, analytic function, or pure SQL expression.

### 6.3. N+1 Query Inside a Function

Example: a function that looks up a customer's level:

```sql
CREATE OR REPLACE FUNCTION get_customer_level (
    p_customer_id IN NUMBER
) RETURN VARCHAR2
AS
    v_level VARCHAR2(30);
BEGIN
    SELECT customer_level
    INTO v_level
    FROM customers
    WHERE customer_id = p_customer_id;

    RETURN v_level;
END get_customer_level;
/
```

Query:

```sql
SELECT order_id,
       get_customer_level(customer_id)
FROM orders;
```

If there are 50,000 orders, the function may be called many times; each call executes a SELECT. This is an N+1 pattern: one query retrieves the list, followed by many small queries to fetch related data.

It can be rewritten using a JOIN:

```sql
SELECT o.order_id,
       c.customer_level
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id;
```

A JOIN lets the optimizer see the data relationship and choose an appropriate access path for the entire query.

### 6.4. Do Not Assume How Many Times a Function Is Called

The number of function executions does not necessarily equal the number of final rows returned. The optimizer may:

- Evaluate predicates before or after transformations.
- Re-evaluate expressions in different branches of the plan.
- Eliminate some evaluations through query transformations.
- Vary the call count depending on bind values, statistics, and database version.

Therefore, do not write functions with side effects or depend on invocation counts when the function is used in SQL.

## 7. Avoid PL/SQL Functions When a SQL Expression Suffices

If the logic consists only of SQL operators and functions, write it directly in SQL:

| Logic | Prefer in SQL |
|---|---|
| String normalization | `TRIM`, `LOWER`, `UPPER`, `REPLACE` |
| Conditional checks | `CASE`, `COALESCE`, `NVL`, `NULLIF` |
| Arithmetic calculations | Operators `+`, `-`, `*`, `/` |
| Aggregation | `SUM`, `COUNT`, `MIN`, `MAX`, `AVG` |
| Top/priority row selection | `ROW_NUMBER`, `RANK`, `FETCH FIRST` |
| Related data lookup | JOIN, scalar subquery, or EXISTS |
| Group calculations | GROUP BY and analytic functions |

Example function:

```sql
CREATE OR REPLACE FUNCTION line_total (
    p_quantity IN NUMBER,
    p_unit_price IN NUMBER
) RETURN NUMBER
AS
BEGIN
    RETURN p_quantity * p_unit_price;
END line_total;
/
```

SQL can compute this directly:

```sql
SELECT order_line_id,
       quantity * unit_price AS line_total
FROM order_lines;
```

If the formula is just multiplication, calling a PL/SQL function is unnecessary.

## 8. PRAGMA UDF for Functions Called from SQL

In some cases, a PL/SQL function genuinely needs to be reused and called from SQL. Oracle provides `PRAGMA UDF` to inform the compiler that the function is primarily used from SQL and can have its invocation overhead optimized.

### 8.1. Syntax

```sql
CREATE OR REPLACE FUNCTION normalize_customer_code (
    p_code IN VARCHAR2
) RETURN VARCHAR2
AS
    PRAGMA UDF;
BEGIN
    RETURN UPPER(TRIM(p_code));
END normalize_customer_code;
/
```

`PRAGMA UDF` is placed in the declaration section of the function, before `BEGIN`.

### 8.2. What Does PRAGMA UDF Do?

`PRAGMA UDF` hints to the compiler to optimize the function for the context of being called from SQL. In certain workloads, it can reduce overhead when the SQL engine calls the PL/SQL function.

However, understand its limitations:

- It does not turn a PL/SQL function into a SQL expression.
- It does not guarantee complete elimination of context switches.
- It does not replace rewriting a query in a set-based way.
- It does not make a function with side effects safe to call from SQL.
- The benefit depends on the workload, database version, parameter types, and how the optimizer executes the query.

### 8.3. When to Consider It?

`PRAGMA UDF` is suitable when:

- The function is called frequently from SQL.
- The logic cannot be easily expressed in pure SQL.
- The function does not cause inappropriate side effects.
- You have measured and confirmed that function call overhead is significant.
- The Oracle version supports this pragma.

`PRAGMA UDF` has been available since Oracle Database 12c Release 1. For systems supporting multiple versions, verify the minimum supported version before deploying.

## 9. DETERMINISTIC and RESULT_CACHE Are Not the Same as PRAGMA UDF

Three commonly confused concepts:

| Mechanism | Purpose |
|---|---|
| `PRAGMA UDF` | Helps optimize the overhead of a function called from SQL |
| `DETERMINISTIC` | Declares that the function always returns the same output for the same input, as promised by the developer |
| `RESULT_CACHE` | Allows Oracle to cache function results by parameters and manage data dependencies accordingly |

### 9.1. DETERMINISTIC

```sql
CREATE OR REPLACE FUNCTION normalize_code (
    p_code IN VARCHAR2
) RETURN VARCHAR2
DETERMINISTIC
AS
BEGIN
    RETURN UPPER(TRIM(p_code));
END normalize_code;
/
```

`DETERMINISTIC` is a promise made by the function author. Oracle does not automatically verify that the function is truly deterministic. Do not declare it if the result depends on:

- Current time.
- Sequences or session state.
- Package global variables.
- NLS settings not passed as parameters.
- Mutable data that the function reads without being properly reflected in the contract.

Do not treat DETERMINISTIC as a general-purpose cache or a guarantee that the function runs only once.

### 9.2. RESULT_CACHE

```sql
CREATE OR REPLACE FUNCTION get_tax_rate (
    p_region_code IN VARCHAR2
) RETURN NUMBER
RESULT_CACHE
AS
    v_rate NUMBER;
BEGIN
    SELECT tax_rate
    INTO v_rate
    FROM tax_regions
    WHERE region_code = p_region_code;

    RETURN v_rate;
END get_tax_rate;
/
```

`RESULT_CACHE` allows Oracle to store function results in the result cache and manage validity based on data dependencies tracked by Oracle. It can reduce repeated computation/querying when inputs are identical and the cache remains valid.

Even so, the function still involves a call from SQL to PL/SQL. Result cache can reduce the work inside the function, but you should not assume it completely removes context switch cost.

Use result cache only when the function behaves appropriately, its result does not depend on unmanaged session state, and caching yields a measurable benefit.

## 10. BULK COLLECT: Fetching Multiple Rows in a Single Data Transfer

When you genuinely need to process rows in PL/SQL, `BULK COLLECT` fetches multiple rows from the SQL engine into collections in a single fetch/batch instead of transferring one row at a time.

### 10.1. SELECT BULK COLLECT INTO

```sql
DECLARE
    TYPE employee_id_tab_t IS TABLE OF employees.employee_id%TYPE;
    TYPE salary_tab_t IS TABLE OF employees.salary%TYPE;

    v_employee_ids employee_id_tab_t;
    v_salaries salary_tab_t;
BEGIN
    SELECT employee_id, salary
    BULK COLLECT INTO v_employee_ids, v_salaries
    FROM employees
    WHERE department_id = 50;

    DBMS_OUTPUT.PUT_LINE(
        'Fetched=' || v_employee_ids.COUNT
    );

    FOR i IN 1 .. v_employee_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(
            v_employee_ids(i) || ': ' || v_salaries(i)
        );
    END LOOP;
END;
/
```

The collections receive the columns at matching positions. If the query returns no rows, the collections are empty; `BULK COLLECT` does not raise `NO_DATA_FOUND` simply because no rows were returned.

### 10.2. Why Does BULK COLLECT Reduce Overhead?

With row-by-row fetching, PL/SQL has to receive many small results. With bulk fetching, the SQL engine returns a group of rows into collections. Data transfer is batched, reducing the number of back-and-forth round-trips.

Bulk fetching does not eliminate all costs:

- SQL still has to read and process the data.
- Collections require memory in the PGA.
- PL/SQL still has to iterate over the elements if the logic requires per-row processing.
- Excessively large batches can increase memory usage and affect other sessions.

### 10.3. Limiting Memory Usage with LIMIT

For large data sets, you should not always load the entire result set into collections. Use an explicit cursor and `FETCH BULK COLLECT ... LIMIT`:

```sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = 50
        ORDER BY employee_id;

    TYPE employee_id_tab_t IS TABLE OF employees.employee_id%TYPE;
    TYPE salary_tab_t IS TABLE OF employees.salary%TYPE;

    v_employee_ids employee_id_tab_t;
    v_salaries salary_tab_t;
    c_batch_size CONSTANT PLS_INTEGER := 500;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees
        BULK COLLECT INTO v_employee_ids, v_salaries
        LIMIT c_batch_size;

        EXIT WHEN v_employee_ids.COUNT = 0;

        FOR i IN 1 .. v_employee_ids.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                v_employee_ids(i) || ': ' || v_salaries(i)
            );
        END LOOP;
    END LOOP;

    CLOSE c_employees;
EXCEPTION
    WHEN OTHERS THEN
        IF c_employees%ISOPEN THEN
            CLOSE c_employees;
        END IF;
        RAISE;
END;
/
```

Each fetch retrieves at most 500 rows. The final batch may contain fewer than 500; when the next fetch returns an empty collection, the loop exits.

### 10.4. Choosing a Batch Size

There is no single optimal batch size for every system. The value depends on:

- Number of columns and size of each row.
- Total number of rows.
- Available PGA memory.
- Number of concurrent sessions.
- PL/SQL processing cost per row.
- Driver/application capabilities and limits if data is passed onward.

Test a few sizes such as 100, 500, 1,000, or 5,000 in a representative environment and measure elapsed time and memory. Do not pick a huge batch size just to minimize fetch count.

## 11. FORALL: Sending DML Using Arrays Instead of Row by Row

`FORALL` is a PL/SQL statement for bulk binding. It sends a single DML statement with bind values taken from collections across multiple iterations, reducing context switches compared to executing a separate DML statement in each loop iteration.

### 11.1. Row-by-Row UPDATE

```sql
DECLARE
    TYPE id_tab_t IS TABLE OF employees.employee_id%TYPE;
    v_ids id_tab_t;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO v_ids
    FROM employees
    WHERE department_id = 50;

    FOR i IN 1 .. v_ids.COUNT LOOP
        UPDATE employees
        SET salary = salary * 1.05
        WHERE employee_id = v_ids(i);
    END LOOP;
END;
/
```

DML is executed one iteration at a time from PL/SQL. If you only need to raise salaries for all employees in department 50, a single set-based UPDATE is still better.

### 11.2. Using FORALL

```sql
DECLARE
    TYPE id_tab_t IS TABLE OF employees.employee_id%TYPE;
    v_ids id_tab_t;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO v_ids
    FROM employees
    WHERE department_id = 50;

    IF v_ids.COUNT > 0 THEN
        FORALL i IN 1 .. v_ids.COUNT
            UPDATE employees
            SET salary = salary * 1.05
            WHERE employee_id = v_ids(i);
    END IF;

    DBMS_OUTPUT.PUT_LINE(
        'Rows affected=' || SQL%ROWCOUNT
    );
END;
/
```

`FORALL` bundles bind values from the collection to execute DML in bulk. It reduces PL/SQL-to-SQL overhead compared to a row-by-row DML loop.

### 11.3. FORALL Is Not a Regular FOR Loop

| FOR loop | FORALL |
|---|---|
| Executes PL/SQL statements per iteration | Bulk-binds one DML statement with multiple collection values |
| Can contain many types of PL/SQL statements | Applies only to a single DML statement inside the FORALL body |
| Suitable for arbitrary procedural logic | Used when performing bulk DML from collections |
| Typically causes many SQL calls if doing row-by-row DML | Reduces switches between PL/SQL and SQL |

Do not place `IF`, `DBMS_OUTPUT`, or multiple arbitrary SQL statements inside a FORALL body. Prepare the collections first, then execute one appropriate DML statement.

### 11.4. Collection Index Forms

FORALL can iterate using:

- `1 .. collection.COUNT` when the collection is dense and indices are contiguous.
- `INDICES OF collection` when the collection has sparse indices.
- `VALUES OF index_collection` when another collection holds the list of indices to process.

Example:

```sql
FORALL i IN INDICES OF v_ids
    UPDATE employees
    SET salary = salary * 1.05
    WHERE employee_id = v_ids(i);
```

With sparse collections, do not assume indices are always `1 .. COUNT`. Use `INDICES OF` when you need to iterate over existing indices.

## 12. Combining BULK COLLECT and FORALL

This is a common pattern when business logic needs to read a set of rows, process them in PL/SQL, and then update many rows.

### 12.1. Example: Reading and Updating in Batches

```sql
DECLARE
    CURSOR c_changes IS
        SELECT employee_id, new_salary
        FROM employee_salary_stage
        WHERE batch_id = 1001
        ORDER BY employee_id;

    TYPE id_tab_t IS TABLE OF employees.employee_id%TYPE;
    TYPE salary_tab_t IS TABLE OF employees.salary%TYPE;

    v_ids id_tab_t;
    v_new_salaries salary_tab_t;
    c_limit CONSTANT PLS_INTEGER := 500;
BEGIN
    OPEN c_changes;

    LOOP
        FETCH c_changes
        BULK COLLECT INTO v_ids, v_new_salaries
        LIMIT c_limit;

        EXIT WHEN v_ids.COUNT = 0;

        FORALL i IN 1 .. v_ids.COUNT
            UPDATE employees
            SET salary = v_new_salaries(i)
            WHERE employee_id = v_ids(i);
    END LOOP;

    CLOSE c_changes;
EXCEPTION
    WHEN OTHERS THEN
        IF c_changes%ISOPEN THEN
            CLOSE c_changes;
        END IF;
        RAISE;
END;
/
```

This example assumes a staging table `EMPLOYEE_SALARY_STAGE` with `BATCH_ID`, `EMPLOYEE_ID`, and `NEW_SALARY`. The cursor fetches data in batches; each bulk fetch retrieves up to 500 rows; FORALL performs the UPDATE using the corresponding collections.

### 12.2. Why Use LIMIT?

If the staging table has millions of rows, loading all of them into collections can consume significant PGA memory. LIMIT keeps memory usage predictable and enables batch-by-batch processing.

### 12.3. Do Not COMMIT Arbitrarily After Every Batch

LIMIT controls collection size, not transaction boundaries. If you COMMIT after each batch:

- The entire process is no longer atomic.
- A failure in a later batch cannot roll back already-committed batches.
- Callers may observe partially updated new data states.
- Keeping a cursor open across COMMITs can encounter issues such as `ORA-01555` in some workloads or fetch/transaction-related errors depending on implementation.

Choose transaction boundaries based on business requirements. If multi-batch processing must remain atomic, keep an appropriate transaction scope and manage undo/redo; if independent batch processing is allowed, persist progress state and design clear recovery logic.

## 13. Handling Errors in FORALL with SAVE EXCEPTIONS

When one element causes an error, the application must decide whether to stop immediately or continue processing the remaining elements.

### 13.1. SAVE EXCEPTIONS

`SAVE EXCEPTIONS` instructs Oracle to continue through the remaining FORALL iterations while recording the error for each failed iteration. After completion, Oracle raises exception `ORA-24381` to indicate that at least one iteration failed.

Example:

```sql
DECLARE
    TYPE id_tab_t IS TABLE OF employees.employee_id%TYPE;
    v_ids id_tab_t;

    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    SELECT employee_id
    BULK COLLECT INTO v_ids
    FROM employees
    WHERE department_id = 50;

    IF v_ids.COUNT > 0 THEN
        FORALL i IN 1 .. v_ids.COUNT SAVE EXCEPTIONS
            UPDATE employees
            SET salary = salary * 1.05
            WHERE employee_id = v_ids(i);
    END IF;
EXCEPTION
    WHEN e_bulk_errors THEN
        FOR i IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Iteration=' ||
                SQL%BULK_EXCEPTIONS(i).ERROR_INDEX ||
                ', Oracle code=' ||
                SQL%BULK_EXCEPTIONS(i).ERROR_CODE
            );
        END LOOP;
        RAISE;
END;
/
```

### 13.2. SQL%BULK_EXCEPTIONS

Inside the bulk error handler:

- `SQL%BULK_EXCEPTIONS.COUNT`: number of failed iterations.
- `SQL%BULK_EXCEPTIONS(i).ERROR_INDEX`: index of the iteration that caused the error.
- `SQL%BULK_EXCEPTIONS(i).ERROR_CODE`: Oracle error code, typically returned as a positive number in this attribute.

You can use `SQLERRM(-SQL%BULK_EXCEPTIONS(i).ERROR_CODE)` to retrieve the corresponding message:

```sql
DBMS_OUTPUT.PUT_LINE(
    SQLERRM(-SQL%BULK_EXCEPTIONS(i).ERROR_CODE)
);
```

If using `INDICES OF` or `VALUES OF`, make sure you understand the relationship between ERROR_INDEX and the collection/iteration index; do not assume it is always a business key.

### 13.3. SQL%BULK_ROWCOUNT

`SQL%BULK_ROWCOUNT(i)` indicates the number of rows affected by the i-th iteration of FORALL:

```sql
FOR i IN 1 .. v_ids.COUNT LOOP
    DBMS_OUTPUT.PUT_LINE(
        'Iteration ' || i ||
        ' affected ' || SQL%BULK_ROWCOUNT(i) || ' rows'
    );
END LOOP;
```

This is useful when an ID does not exist or a DML statement can affect 0, 1, or multiple rows.

### 13.4. SAVE EXCEPTIONS Does Not Decide COMMIT Behavior

After a FORALL has some succeeding and some failing iterations, the caller must still decide whether to COMMIT or ROLLBACK according to business policy. Do not assume that catching `ORA-24381` automatically rolls back all successful changes.

If the handler logs and then `RAISE;`, the caller still receives the bulk error. If the handler processes it and does not re-raise, the caller must have a clear contract on succeeded/failed rows and how to proceed.

## 14. Cursor FOR Loops and Automatic Fetch Optimization

Cursor FOR loop syntax:

```sql
BEGIN
    FOR r IN (
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = 50
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(r.employee_id || ' ' || r.last_name);
    END LOOP;
END;
/
```

Oracle applies runtime optimizations for cursor FOR loops, including array fetching in modern releases. Therefore, you should not rewrite them into explicit cursors solely to replace FOR loop syntax without a measured reason.

However, automatic fetch optimization does not turn row-by-row DML inside the loop into a set-based DML statement. If each iteration still runs a separate UPDATE/INSERT, the DML portion can still generate many context switches.

Distinguish clearly:

- A cursor FOR loop automates fetching and cursor management.
- `BULK COLLECT` lets you explicitly gather multiple rows into collections.
- `FORALL` bundles bind values for bulk DML.
- Set-based SQL is usually the first choice if the entire logic can be expressed in one statement.

## 15. Context Switches and Functions in Triggers

Triggers can invoke PL/SQL procedures/functions or execute SQL. If a row-level trigger fires for thousands of rows, the PL/SQL logic and SQL statements inside the trigger may execute repeatedly.

Example:

```sql
CREATE OR REPLACE TRIGGER trg_order_audit
AFTER UPDATE OF status
ON orders
FOR EACH ROW
BEGIN
    INSERT INTO order_status_audit (
        order_id,
        old_status,
        new_status,
        changed_at
    )
    VALUES (
        :OLD.order_id,
        :OLD.status,
        :NEW.status,
        SYSTIMESTAMP
    );
END trg_order_audit;
/
```

If an UPDATE statement affects 100,000 rows, the row-level trigger executes for each row and performs the corresponding audit operations. This may be a business requirement, but the trigger's cost must be factored into total DML execution time.

If auditing can be designed using another mechanism or handled at the statement/batch level while still meeting requirements, evaluate it. Do not remove a trigger merely for speed if it protects data integrity or mandatory auditing.

## 16. Other Optimizations Related to Context Switches

### 16.1. Reducing Function Calls in SQL

If the same function expression is repeated in multiple places in a query, check whether it can be computed once in an inline view or CTE. However, the optimizer may merge or transform query blocks; do not assume a CTE is materialized by default.

Example:

```sql
WITH normalized AS (
    SELECT customer_id,
           LOWER(TRIM(email)) AS normalized_email
    FROM customers
)
SELECT customer_id, normalized_email
FROM normalized
WHERE normalized_email = LOWER(TRIM(:email));
```

Here normalization uses SQL built-ins rather than calling a PL/SQL function.

### 16.2. Using Scalar Subquery Caching Cautiously

Oracle may apply optimizations such as scalar subquery caching in certain queries, helping avoid recomputing repeated results. However, behavior depends on version, query shape, and execution plan. Do not rely on caching as a semantic guarantee or a substitute for set-based design.

### 16.3. Function Result Cache

`RESULT_CACHE` can help functions that read rarely changing reference data and are called repeatedly with the same parameters. It reduces computation/read work on cache hits, though you still need to measure context switch and cache lookup costs.

### 16.4. Native Compilation Is Not a Solution for Every Context Switch

PL/SQL native compilation can speed up compute-heavy PL/SQL code, but it does not eliminate the fundamental transfer of control between the SQL engine and the PL/SQL engine. If the bottleneck is millions of SQL calls inside a loop, reduce the call count or use bulk processing before considering native compilation.

## 17. Measuring Context Switches and Performance

Do not optimize based on guesswork or line counts. Measure using the same data, same bind values, and same environment.

### 17.1. Measuring Time and Row Counts

Record:

- Elapsed time.
- CPU time.
- Rows read and rows updated.
- Logical reads / buffer gets.
- Physical reads if any.
- Redo/undo generated.
- PGA memory when using collections.
- Number of SQL executions.

### 17.2. Checking Session Statistics

If you have privileges to read dynamic performance views, you can inspect session context switch statistics:

```sql
SELECT n.name,
       s.value
FROM v$sesstat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
WHERE s.sid = TO_NUMBER(
    SYS_CONTEXT('USERENV', 'SID')
)
AND LOWER(n.name) LIKE '%context switch%'
ORDER BY n.name;
```

Statistic names may vary by version or environment. You can also inspect statistics matching `PL/SQL` and `SQL`. Values in `V$SESSTAT` are typically cumulative for the session; capture snapshots before and after the test run and compute the delta rather than comparing two sessions that ran different workloads.

Access to `V$` views depends on account privileges and database policy. In environments without access, a DBA can help collect these metrics.

### 17.3. SQL Trace and TKPROF

SQL Trace records parse/execute/fetch counts, CPU/elapsed time, logical/physical reads, and wait details. You can enable trace for a test session:

```sql
ALTER SESSION SET SQL_TRACE = TRUE;

-- Run the exact PL/SQL block to measure.

ALTER SESSION SET SQL_TRACE = FALSE;
```

Then run TKPROF on the trace file to summarize the output. Trace files may record SQL text and bind values depending on configuration; enable it only in appropriate environments and scopes to avoid unintentionally capturing sensitive data.

### 17.4. DBMS_HPROF

`DBMS_HPROF` is the hierarchical profiler for PL/SQL, helping analyze execution time and call relationships between subprograms. It is useful for finding which functions or procedures consume the most time or are called most often.

Conceptual example:

```sql
BEGIN
    DBMS_HPROF.START_PROFILING(
        location => 'PLSQL_PROF_DIR',
        filename => 'context_switch_test.trc'
    );

    -- Call the program to measure here.

    DBMS_HPROF.STOP_PROFILING;
END;
/
```

The directory object, file write permissions, and trace analysis steps must be configured by a DBA or environment administrator. Do not run profiling broadly in production without evaluating its overhead.

### 17.5. DBMS_XPLAN

For the SQL portion, enable runtime statistics in the test session:

```sql
ALTER SESSION SET statistics_level = ALL;
```

Run the query:

```sql
SELECT department_id,
       COUNT(*)
FROM employees
GROUP BY department_id;
```

After running in the same session:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

`DBMS_XPLAN` displays the SQL statement's execution plan, actual row counts, and buffer gets per operation. It does not replace a PL/SQL profiler when you need to see which functions are called frequently or where time is spent inside PL/SQL.

## 18. Designing Meaningful Benchmarks

When comparing row-by-row, set-based, and bulk approaches:

1. Use the same data set and the same filter conditions.
2. Run multiple iterations to reduce the impact of parsing, caching, and system noise.
3. Record the actual number of rows processed.
4. Measure elapsed time and CPU time, not just client-observed duration.
5. Compare buffer gets, physical reads, and redo.
6. Measure total DML throughput, not just fetch time.
7. Verify transaction state and data results after each approach.
8. Test multiple batch sizes when using BULK COLLECT/FORALL.
9. Run at concurrency levels close to the real workload.
10. Do not extrapolate results from a tiny table to millions of rows.

### 18.1. Result Recording Table

| Approach | Elapsed | CPU | Buffer gets | SQL calls | PGA | Rows |
|---|---:|---:|---:|---:|---:|---:|
| Row-by-row | Measure | Measure | Measure | Measure | Measure | Measure |
| Set-based SQL | Measure | Measure | Measure | Measure | Measure | Measure |
| BULK COLLECT + FORALL | Measure | Measure | Measure | Measure | Measure | Measure |

There are no universal numbers across all databases. Choose the approach based on measured results from your actual workload and transaction requirements.

## 19. Workflow for Optimizing a PL/SQL Block

When a procedure runs slowly, follow this order:

1. **Identify the slow area:** use a profiler or trace to see whether time is spent in SQL or PL/SQL.
2. **Find repeated SQL:** check execution counts and SQL statements invoked inside loops or functions.
3. **Check if it can be written set-based:** replace DML loops with UPDATE, MERGE, INSERT SELECT, or analytic SQL.
4. **Reduce function calls in queries:** use SQL built-ins, JOINs, or SQL expressions where possible.
5. **Use PRAGMA UDF when appropriate:** only when the function is necessary and after measuring.
6. **Bulk fetch:** use BULK COLLECT if many rows must be read into PL/SQL.
7. **Bulk DML:** use FORALL if updating/inserting/deleting from collections.
8. **Limit memory:** use LIMIT for large data sets.
9. **Handle batch errors:** consider SAVE EXCEPTIONS and commit policy.
10. **Re-measure:** confirm performance improved while business results remain unchanged.

### 19.1. Decision Questions

- Can the entire change be performed in a single SQL statement?
- Is a PL/SQL function being called for each row in a query?
- Is the function running a SELECT inside each invocation?
- If processing must stay in PL/SQL, can data be fetched in batches?
- Can the DML use FORALL?
- Does the batch size put pressure on PGA memory?
- Does the process need full atomicity, or are per-batch commits acceptable?
- Do you need to capture individual errors or stop at the first error?

## 20. Common Misconceptions

| Misconception | Reality |
|---|---|
| A single context switch is always very expensive | One switch is usually small; high frequency creates significant overhead |
| Every PL/SQL loop is slow | Loops are mainly a concern with repeated SQL calls or large volumes; pure PL/SQL logic can be fine |
| Cursor FOR loops eliminate all context switches | They simplify fetching and use array fetch optimization; per-row DML inside still incurs cost |
| BULK COLLECT is always faster than set-based SQL | Set-based SQL is usually better if the logic can be written in SQL |
| FORALL is a table-wide UPDATE like set-based SQL | FORALL bulk-binds a DML statement across a collection; it does not replace every set-based UPDATE |
| LIMIT automatically splits transactions | LIMIT only caps fetch batch size; it does not COMMIT |
| FORALL cannot have partial errors | SAVE EXCEPTIONS lets it continue and collect errors; the caller must still handle them |
| PRAGMA UDF removes context switches | It can reduce overhead, not guarantee eliminating engine switches |
| DETERMINISTIC automatically caches results | It is a developer promise of determinism, not a general caching mechanism |
| RESULT_CACHE removes all function call overhead | Caching reduces computation on hits; the function call itself still has cost |
| SQL calls a function exactly once per row | Evaluation count depends on the execution plan and Oracle optimizations |
| Adding COMMIT after every batch is always good | It can break atomicity and complicate recovery |
| Triggers do not affect DML performance | Row-level triggers can fire per row and increase total work |
| Native compilation fixes N+1 SQL | It does not eliminate repeated SQL calls or context switches |

## 21. Hands-On Practice Lab

The exercises below use the sample `EMPLOYEES` table and modify data. Run them in a lab schema or test transaction; ROLLBACK when you do not want to keep changes.

### Step 1. Measure Row-by-Row UPDATE

```sql
BEGIN
    FOR r IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = 50
    ) LOOP
        UPDATE employees
        SET salary = salary * 1.01
        WHERE employee_id = r.employee_id;
    END LOOP;
END;
/

ROLLBACK;
```

Record execution time, SQL execution count, and buffer gets.

### Step 2. Measure Set-Based UPDATE

```sql
UPDATE employees
SET salary = salary * 1.01
WHERE department_id = 50;

ROLLBACK;
```

Compare with Step 1 on the same data and same initial state.

### Step 3. Test BULK COLLECT and FORALL

```sql
DECLARE
    TYPE id_tab_t IS TABLE OF employees.employee_id%TYPE;
    v_ids id_tab_t;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO v_ids
    FROM employees
    WHERE department_id = 50;

    IF v_ids.COUNT > 0 THEN
        FORALL i IN 1 .. v_ids.COUNT
            UPDATE employees
            SET salary = salary * 1.01
            WHERE employee_id = v_ids(i);
    END IF;
END;
/

ROLLBACK;
```

Measure and compare against the set-based UPDATE. Bulk processing can be faster than row-by-row, though not necessarily faster than a simple set-based UPDATE.

### Step 4. Create a Function Called from SQL

```sql
CREATE OR REPLACE FUNCTION lab_salary_band (
    p_salary IN NUMBER
) RETURN VARCHAR2
AS
BEGIN
    IF p_salary < 5000 THEN
        RETURN 'LOW';
    ELSIF p_salary < 10000 THEN
        RETURN 'MEDIUM';
    ELSE
        RETURN 'HIGH';
    END IF;
END lab_salary_band;
/
```

### Step 5. Use the Function in SELECT

```sql
SELECT employee_id,
       lab_salary_band(salary) AS salary_band
FROM employees;
```

Observe execution time and call count using a profiler/trace if the environment allows.

### Step 6. Rewrite Using CASE

```sql
SELECT employee_id,
       CASE
           WHEN salary < 5000 THEN 'LOW'
           WHEN salary < 10000 THEN 'MEDIUM'
           ELSE 'HIGH'
       END AS salary_band
FROM employees;
```

Compare results and execution time against the function. The logic in this example can be expressed directly in SQL, so CASE is the simpler option.

### Step 7. Test PRAGMA UDF

```sql
CREATE OR REPLACE FUNCTION lab_salary_band_udf (
    p_salary IN NUMBER
) RETURN VARCHAR2
AS
    PRAGMA UDF;
BEGIN
    IF p_salary < 5000 THEN
        RETURN 'LOW';
    ELSIF p_salary < 10000 THEN
        RETURN 'MEDIUM';
    ELSE
        RETURN 'HIGH';
    END IF;
END lab_salary_band_udf;
/
```

Run the query with this function, measure multiple times, and compare with the function without the pragma. Do not draw conclusions from a single run.

### Step 8. Test Batch Bulk Fetch

```sql
DECLARE
    CURSOR c_emp IS
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = 50;

    TYPE id_tab_t IS TABLE OF employees.employee_id%TYPE;
    TYPE salary_tab_t IS TABLE OF employees.salary%TYPE;
    v_ids id_tab_t;
    v_salaries salary_tab_t;
BEGIN
    OPEN c_emp;
    LOOP
        FETCH c_emp BULK COLLECT
        INTO v_ids, v_salaries
        LIMIT 200;

        EXIT WHEN v_ids.COUNT = 0;

        DBMS_OUTPUT.PUT_LINE('Fetched batch=' || v_ids.COUNT);
    END LOOP;
    CLOSE c_emp;
EXCEPTION
    WHEN OTHERS THEN
        IF c_emp%ISOPEN THEN
            CLOSE c_emp;
        END IF;
        RAISE;
END;
/
```

Try different LIMIT values and record time and memory usage.

### Step 9. View Session Statistics

```sql
SELECT n.name, s.value
FROM v$sesstat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
WHERE s.sid = TO_NUMBER(SYS_CONTEXT('USERENV', 'SID'))
  AND LOWER(n.name) LIKE '%context switch%'
ORDER BY n.name;
```

Capture statistics before and after each test segment. Requires privileges to read V$ views.

### Step 10. Clean Up Lab Functions

Only when you are sure these are functions you created and are no longer needed:

```sql
DROP FUNCTION lab_salary_band;
DROP FUNCTION lab_salary_band_udf;
```

## 22. Rules to Remember

| Issue | Approach |
|---|---|
| Multiple UPDATEs in a loop | Try a single set-based UPDATE |
| Multiple INSERTs from a query | Use `INSERT INTO ... SELECT` |
| Source/target synchronization | Consider MERGE |
| Group or adjacent-row calculations | GROUP BY or analytic functions |
| PL/SQL function in SELECT | Try replacing with SQL built-ins, JOIN, or CASE |
| Function genuinely needed from SQL | Consider `PRAGMA UDF` after measuring |
| Repeated calls with same parameters | Evaluate `RESULT_CACHE` if semantics fit |
| Reading many rows into PL/SQL | `BULK COLLECT` |
| Large data sets | Cursor + `FETCH BULK COLLECT ... LIMIT n` |
| Collection-based DML | `FORALL` |
| Some iterations may fail | `SAVE EXCEPTIONS` and `SQL%BULK_EXCEPTIONS` |
| Checking row counts per DML in FORALL | `SQL%BULK_ROWCOUNT(i)` |
| Measuring context switches | Session statistics, SQL Trace, profiler |
| Verifying SQL execution plan | `DBMS_XPLAN.DISPLAY_CURSOR` |
| Confirming benefit | Benchmark with the same data, binds, and transactions |

## 23. Self-Check Questions

**Question 1.** What is a context switch between SQL and PL/SQL?

**Answer:** The transfer of execution control between the SQL engine and the PL/SQL engine when one engine invokes processing handled by the other.

**Question 2.** Why can row-by-row DML be slow?

**Answer:** Each iteration may invoke a separate SQL statement, creating many context switches and per-execution/bind overhead.

**Question 3.** What is the first solution when business logic can be expressed in SQL?

**Answer:** Write a single set-based SQL statement such as UPDATE, MERGE, or INSERT SELECT.

**Question 4.** What overhead can SQL calling a PL/SQL function create?

**Answer:** The SQL engine must switch to the PL/SQL engine to run the function and receive the result; if called repeatedly across many rows, cost can increase.

**Question 5.** Can you assume a function is called exactly once per row?

**Answer:** No. The number of evaluations depends on the query plan and Oracle's optimizations.

**Question 6.** What does PRAGMA UDF do?

**Answer:** It hints to the compiler to optimize a function primarily called from SQL, potentially reducing overhead without guaranteeing elimination of context switches.

**Question 7.** Is DETERMINISTIC a result cache?

**Answer:** No. DETERMINISTIC is a developer promise regarding result determinism, not a general-purpose caching mechanism.

**Question 8.** What is BULK COLLECT used for?

**Answer:** Fetching multiple rows from the SQL engine into PL/SQL collections in a single batch.

**Question 9.** Why use LIMIT with BULK COLLECT?

**Answer:** To cap the number of rows per batch in order to control PGA memory and processing chunk size.

**Question 10.** How does FORALL differ from a FOR loop?

**Answer:** FORALL bulk-binds a single DML statement using values from collections; a FOR loop runs PL/SQL statements iteration by iteration.

**Question 11.** Why is set-based SQL usually better than FORALL?

**Answer:** Set-based SQL lets the SQL engine process the entire data set in one statement; FORALL still requires PL/SQL to prepare collections and is used when bulk binding is needed.

**Question 12.** What does SAVE EXCEPTIONS do?

**Answer:** It allows FORALL to continue executing remaining iterations, saves errors, and raises ORA-24381 after completion.

**Question 13.** What does SQL%BULK_EXCEPTIONS provide?

**Answer:** The iteration index and error code for each failed DML iteration in a FORALL statement with SAVE EXCEPTIONS.

**Question 14.** Does LIMIT automatically COMMIT after each batch?

**Answer:** No. LIMIT only controls how many rows are fetched each time; transaction boundaries are managed by the program/caller.

**Question 15.** Does a cursor FOR loop eliminate row-by-row DML?

**Answer:** No. The runtime may optimize fetching, but individual DML statements inside each iteration still carry overhead.

**Question 16.** Which tool is used to see which PL/SQL subprogram consumes time?

**Answer:** You can use DBMS_HPROF or an appropriate profiler; SQL Trace/TKPROF analyzes SQL calls and SQL execution time.

**Question 17.** Does native compilation eliminate context switches?

**Answer:** No. It can speed up compute-intensive PL/SQL code, but it does not eliminate repeated SQL calls.

## 24. Conclusion

A context switch is the coordination cost incurred when execution control transfers between the SQL engine and the PL/SQL engine. A single switch is typically small, but loops that issue row-by-row SQL or PL/SQL functions invoked repeatedly in queries can generate large overhead. When tuning PL/SQL, look at the number of SQL/function calls and determine whether the logic can be handled on a set basis.

Prefer set-based SQL such as UPDATE, MERGE, INSERT SELECT, JOIN, CASE, GROUP BY, and analytic functions whenever the business logic can be expressed directly. When row-by-row procedural handling is required, `BULK COLLECT` batches data during fetches and `FORALL` batches bind values for DML; use LIMIT to control PGA memory and `SAVE EXCEPTIONS` when collecting per-iteration errors. Cursor FOR loops keep code concise and benefit from fetch optimization, but they do not automatically turn row-by-row DML into set-based operations.

When a PL/SQL function genuinely needs to be called from SQL, consider `PRAGMA UDF` or `RESULT_CACHE` according to proper semantics and after measurement. `DETERMINISTIC` is not a cache and does not guarantee a function runs only once. Use session statistics, SQL Trace, DBMS_HPROF, and DBMS_XPLAN to pinpoint bottlenecks, then benchmark with the same data and transactions. Effective optimization reduces back-and-forth work while preserving correct business results, data integrity, and transaction boundaries.
