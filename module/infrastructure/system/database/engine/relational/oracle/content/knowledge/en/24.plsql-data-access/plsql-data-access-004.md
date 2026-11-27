# Explicit cursor: declaration, opening, fetching, and closing

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** PL/SQL and Data  
> **Objective:** Understand and use explicit cursors in PL/SQL: declare queries, open cursors, fetch rows one by one, and close cursors. Know how to declare parameterized cursors, receive data using variables or records, use cursor attributes, handle end-of-data and exceptions safely; apply FOR UPDATE and WHERE CURRENT OF when updating the currently fetched row; and choose between explicit cursors, cursor FOR LOOPs, and set-based SQL according to requirements.

## 1. What is a cursor?

A SELECT statement can return zero, one, or many rows. When PL/SQL needs to process each row of the result, a cursor provides a way to work with that result set.

You can think of a cursor as a work area associated with an executing query:

1. Declare the cursor to define the SELECT statement.
2. Open the cursor so Oracle executes the query and establishes the result set.
3. FETCH to retrieve each row into PL/SQL variables or a record.
4. Check cursor attributes to know whether rows remain or all rows have been fetched.
5. Close the cursor to release associated resources.

An **explicit cursor** is a cursor explicitly declared and controlled by the developer using OPEN, FETCH, and CLOSE. It is commonly used when fine-grained control over the cursor lifecycle or row-by-row PL/SQL processing logic is needed.

General example:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, employee_name, salary
        FROM employees
        WHERE department_id = 10
        ORDER BY employee_id;

    l_employee_id employees.employee_id%TYPE;
    l_employee_name employees.employee_name%TYPE;
    l_salary employees.salary%TYPE;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees
        INTO l_employee_id, l_employee_name, l_salary;

        EXIT WHEN c_employees%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            l_employee_id || ' - ' ||
            l_employee_name || ' - ' ||
            l_salary
        );
    END LOOP;

    CLOSE c_employees;
END;
/
~~~

This example demonstrates all four operations: declaring, opening, fetching, and closing.

## 2. Declaring an explicit cursor

A cursor is declared in the declarative section of a PL/SQL block, procedure, function, or package.

Basic syntax:

~~~sql
CURSOR cursor_name IS
    select_statement;
~~~

Example:

~~~sql
DECLARE
    CURSOR c_open_orders IS
        SELECT order_id,
               customer_id,
               order_date,
               total_amount
        FROM orders
        WHERE status = 'OPEN';
BEGIN
    NULL;
END;
/
~~~

Declaring a cursor only defines the query. It does not execute the SELECT statement or fetch any rows. The query is executed when the program opens the cursor with OPEN.

### 2.1. The cursor must return columns matching FETCH

If fetching into individual variables:

~~~sql
DECLARE
    CURSOR c_dept IS
        SELECT department_id, department_name
        FROM departments;

    l_department_id departments.department_id%TYPE;
    l_department_name departments.department_name%TYPE;
BEGIN
    OPEN c_dept;

    FETCH c_dept
    INTO l_department_id, l_department_name;

    CLOSE c_dept;
END;
/
~~~

The number, order, and data types of the target variables must be compatible with the cursor's select list. If the query returns two columns while FETCH only receives one variable, the program fails to compile or raises a corresponding error.

To reduce dependency on column data types and lengths, use the `%TYPE` attribute instead of manually declaring `NUMBER`/`VARCHAR2` with arbitrary sizes.

### 2.2. Using cursor %ROWTYPE

When a query returns multiple columns, you can declare a record based on the cursor:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, employee_name, salary
        FROM employees
        WHERE department_id = 10;

    l_employee c_employees%ROWTYPE;
BEGIN
    OPEN c_employees;

    FETCH c_employees INTO l_employee;

    IF c_employees%FOUND THEN
        DBMS_OUTPUT.PUT_LINE(l_employee.employee_name);
    END IF;

    CLOSE c_employees;
END;
/
~~~

A `c_employees%ROWTYPE` record has fields corresponding to the cursor's select list. Field names are based on the column names or aliases of the query.

Example using aliases to give clear field names:

~~~sql
DECLARE
    CURSOR c_sales IS
        SELECT sale_id AS id,
               amount AS sale_amount
        FROM sales;

    l_sale c_sales%ROWTYPE;
BEGIN
    OPEN c_sales;
    FETCH c_sales INTO l_sale;

    IF c_sales%FOUND THEN
        DBMS_OUTPUT.PUT_LINE(
            l_sale.id || ': ' || l_sale.sale_amount
        );
    END IF;

    CLOSE c_sales;
END;
/
~~~

When using a `%ROWTYPE` record, FETCH must receive the entire row shape of the cursor. You cannot fetch only a subset of the record's fields in a standard FETCH statement; if you only need certain columns, declare separate target variables or an appropriate record.

## 3. OPEN: executing the query and opening the cursor

Syntax:

~~~sql
OPEN cursor_name;
~~~

OPEN instructs Oracle to execute the SELECT statement declared in the cursor and establish the context for fetching rows.

Example:

~~~sql
DECLARE
    CURSOR c_products IS
        SELECT product_id, product_name
        FROM products
        WHERE active_flag = 'Y';

    l_product_id products.product_id%TYPE;
    l_product_name products.product_name%TYPE;
BEGIN
    OPEN c_products;

    FETCH c_products
    INTO l_product_id, l_product_name;

    CLOSE c_products;
END;
/
~~~

OPEN does not load all rows into PL/SQL variables. Each FETCH retrieves the next row in the order of the query result. If a deterministic processing order is required, the SELECT statement should include an ORDER BY clause with criteria sufficient to distinguish rows.

### 3.1. Opening a cursor multiple times

An explicit cursor can be reopened after it has been closed. Each OPEN starts a new cursor execution with the appropriate parameters and snapshot.

~~~sql
OPEN c_products;
-- FETCH and process
CLOSE c_products;

OPEN c_products;
-- A new read pass
CLOSE c_products;
~~~

Do not OPEN a cursor that is already open. Reopening a cursor before calling CLOSE raises `INVALID_CURSOR`.

### 3.2. The query is executed at OPEN time

If the source table changes between two openings, each OPEN can observe committed data according to the corresponding statement snapshot. An already open cursor continues to represent that execution; it does not automatically become a new query after each FETCH.

This is important when handling concurrent data. A cursor is not a mechanism that automatically refreshes its result set when another session modifies the table.

## 4. FETCH: retrieving rows one by one

Syntax:

~~~sql
FETCH cursor_name INTO variable_1, variable_2, ...;
~~~

Each FETCH retrieves the next row from the result set and assigns its columns to the target variables in the order of the select list.

Example:

~~~sql
DECLARE
    CURSOR c_departments IS
        SELECT department_id, department_name
        FROM departments
        ORDER BY department_id;

    l_id departments.department_id%TYPE;
    l_name departments.department_name%TYPE;
BEGIN
    OPEN c_departments;

    FETCH c_departments INTO l_id, l_name;

    IF c_departments%FOUND THEN
        DBMS_OUTPUT.PUT_LINE('First department: ' || l_name);
    END IF;

    CLOSE c_departments;
END;
/
~~~

If the cursor returns no rows, FETCH does not raise `NO_DATA_FOUND` like `SELECT INTO`. Instead, the cursor attribute `%NOTFOUND` becomes `TRUE` and `%FOUND` becomes `FALSE` after a FETCH that retrieves no row.

### 4.1. Common FETCH loop

~~~sql
OPEN c_employees;

LOOP
    FETCH c_employees INTO l_employee;

    EXIT WHEN c_employees%NOTFOUND;

    -- Process current row
    DBMS_OUTPUT.PUT_LINE(l_employee.employee_name);
END LOOP;

CLOSE c_employees;
~~~

The key point is to check `%NOTFOUND` immediately after FETCH and before processing the record. The final FETCH may not find a row; do not process the stale record as if it were a new row.

### 4.2. Using EXIT WHEN %NOTFOUND

This is a readable and commonly used pattern:

~~~sql
LOOP
    FETCH c_orders INTO l_order;
    EXIT WHEN c_orders%NOTFOUND;

    process_order(l_order.order_id);
END LOOP;
~~~

You can also use `EXIT WHEN NOT c_orders%FOUND` after FETCH. Both express the same intent once the cursor is open and has been fetched.

### 4.3. Why not check %NOTFOUND before FETCH?

After OPEN, no row has been fetched yet. `%FOUND` and `%NOTFOUND` do not yet evaluate to TRUE/FALSE in the sense of having fetched a row; their value is in a NULL state. If you write:

~~~sql
WHILE c_orders%NOTFOUND LOOP
    FETCH c_orders INTO l_order;
END LOOP;
~~~

the loop will not run as expected because the WHILE condition is not TRUE initially. The proper pattern is to FETCH first and then `EXIT WHEN %NOTFOUND`.

### 4.4. Fetching into individual variables vs. fetching into a record

Fetching into individual variables:

~~~sql
FETCH c_employees
INTO l_employee_id, l_employee_name, l_salary;
~~~

Fetching into a record:

~~~sql
FETCH c_employees INTO l_employee;
~~~

A record is usually cleaner when the query has many columns and the entire row needs to be processed together. Individual variables are suitable when only a few columns are needed or when you want to make the data used explicit.

## 5. CLOSE: closing the cursor

Syntax:

~~~sql
CLOSE cursor_name;
~~~

CLOSE ends the use of an open cursor and releases associated cursor resources. After closing, you cannot fetch again until the cursor is reopened.

Complete example:

~~~sql
DECLARE
    CURSOR c_customers IS
        SELECT customer_id, customer_name
        FROM customers
        ORDER BY customer_id;

    l_customer c_customers%ROWTYPE;
BEGIN
    OPEN c_customers;

    LOOP
        FETCH c_customers INTO l_customer;
        EXIT WHEN c_customers%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            l_customer.customer_id || ': ' ||
            l_customer.customer_name
        );
    END LOOP;

    CLOSE c_customers;
END;
/
~~~

### 5.1. Why must a cursor be closed?

Closing a cursor upon completion releases resources and avoids keeping the cursor open longer than necessary. If a cursor is no longer needed, do not keep it open while the program waits for user input or calls external services.

Ending a PL/SQL block usually releases local cursors according to the block lifecycle, but you should still write an explicit CLOSE to control resources and clarify intent.

### 5.2. Do not close an unopened cursor or close twice

Incorrect operations:

~~~sql
CLOSE c_orders; -- when cursor has not been opened
~~~

or:

~~~sql
OPEN c_orders;
CLOSE c_orders;
CLOSE c_orders; -- closing a second time
~~~

These can raise `INVALID_CURSOR`. Use `%ISOPEN` to check the state before closing in exception handling sections.

## 6. Cursor attributes

Explicit cursors provide attributes to inspect their state and the number of rows fetched.

| Attribute | Meaning |
|---|---|
| %ISOPEN | TRUE if the cursor is currently open; FALSE if unopened or closed |
| %FOUND | TRUE if the most recent FETCH retrieved a row; FALSE otherwise |
| %NOTFOUND | TRUE if the most recent FETCH retrieved no row; FALSE if it did |
| %ROWCOUNT | Number of rows successfully fetched since the current OPEN |

Example:

~~~sql
DECLARE
    CURSOR c_products IS
        SELECT product_id
        FROM products;

    l_product_id products.product_id%TYPE;
BEGIN
    OPEN c_products;

    DBMS_OUTPUT.PUT_LINE(
        'Is open: ' ||
        CASE WHEN c_products%ISOPEN THEN 'YES' ELSE 'NO' END
    );

    LOOP
        FETCH c_products INTO l_product_id;
        EXIT WHEN c_products%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            'Fetched rows: ' || c_products%ROWCOUNT
        );
    END LOOP;

    DBMS_OUTPUT.PUT_LINE(
        'Total fetched: ' || c_products%ROWCOUNT
    );

    CLOSE c_products;
END;
/
~~~

### 6.1. %ISOPEN

`%ISOPEN` checks whether the cursor is currently open. This attribute can be used to safely check before closing.

~~~sql
IF c_orders%ISOPEN THEN
    CLOSE c_orders;
END IF;
~~~

`%ISOPEN` returns `FALSE` if the cursor has not been opened or has already been closed.

### 6.2. %FOUND and %NOTFOUND

These two attributes describe the result of the most recent FETCH:

- After a FETCH that retrieves a row: `%FOUND = TRUE`, `%NOTFOUND = FALSE`.
- After a FETCH that retrieves no row: `%FOUND = FALSE`, `%NOTFOUND = TRUE`.
- After OPEN but before the first FETCH: there is no FETCH result to inspect yet; these attributes are NULL.

Do not use `%FOUND`/`%NOTFOUND` before the first FETCH to control the loop.

### 6.3. %ROWCOUNT

`%ROWCOUNT` starts at 0 after OPEN and increments by one after each successful FETCH. A FETCH that finds no row does not increment the count.

~~~sql
OPEN c_orders;

LOOP
    FETCH c_orders INTO l_order;
    EXIT WHEN c_orders%NOTFOUND;

    DBMS_OUTPUT.PUT_LINE(
        'Current row number: ' || c_orders%ROWCOUNT
    );
END LOOP;

DBMS_OUTPUT.PUT_LINE(
    'Rows fetched: ' || c_orders%ROWCOUNT
);

CLOSE c_orders;
~~~

`%ROWCOUNT` is the number of rows fetched, not necessarily the number of rows updated or deleted. If the program processes only part of the result set, this value only reflects the number of rows fetched.

### 6.4. Cursor state after CLOSE

After CLOSE, the cursor is no longer open. `%ISOPEN` returns `FALSE`. Other attributes such as `%FOUND`, `%NOTFOUND`, or `%ROWCOUNT` should not continue to be referenced; accessing a closed cursor can raise `INVALID_CURSOR`.

## 7. Parameterized cursors

A cursor can accept parameters so the same SELECT statement can be reused with different input values.

Syntax:

~~~sql
CURSOR cursor_name (
    parameter_name datatype
) IS
    SELECT ...;
~~~

Example:

~~~sql
DECLARE
    CURSOR c_employees_by_dept (
        p_department_id employees.department_id%TYPE
    ) IS
        SELECT employee_id, employee_name, salary
        FROM employees
        WHERE department_id = p_department_id
        ORDER BY employee_id;

    l_employee c_employees_by_dept%ROWTYPE;
BEGIN
    OPEN c_employees_by_dept(10);

    LOOP
        FETCH c_employees_by_dept INTO l_employee;
        EXIT WHEN c_employees_by_dept%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            l_employee.employee_id || ': ' ||
            l_employee.employee_name
        );
    END LOOP;

    CLOSE c_employees_by_dept;
END;
/
~~~

`P_DEPARTMENT_ID` is a cursor parameter. When calling OPEN, pass the actual value. The query uses that parameter as a filter condition.

### 7.1. Reopening with different parameters

You can reuse the cursor after closing it:

~~~sql
OPEN c_employees_by_dept(10);
-- Fetch and process
CLOSE c_employees_by_dept;

OPEN c_employees_by_dept(20);
-- Fetch result set for department 20
CLOSE c_employees_by_dept;
~~~

On each OPEN, pass the set of parameters needed for the new execution.

### 7.2. Using multiple parameter types

~~~sql
DECLARE
    CURSOR c_orders (
        p_customer_id orders.customer_id%TYPE,
        p_min_total NUMBER
    ) IS
        SELECT order_id, total_amount
        FROM orders
        WHERE customer_id = p_customer_id
          AND total_amount >= p_min_total;
BEGIN
    OPEN c_orders(100, 500);
    -- FETCH...
    CLOSE c_orders;
END;
/
~~~

You should use `%TYPE` for parameters that share the same semantics as a column to avoid type mismatches when the schema changes. Cursor parameters are inputs to the query; they are not variables updated from inside the cursor.

## 8. Exception handling and ensuring CLOSE

An error can occur after OPEN and before CLOSE, such as a type conversion error, an error inside a row-processing procedure, or a DML error. If the cursor is not closed, the program may hold resources longer than necessary.

Safe pattern:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, employee_name
        FROM employees;

    l_employee c_employees%ROWTYPE;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees INTO l_employee;
        EXIT WHEN c_employees%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(l_employee.employee_name);
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
~~~

If an exception occurs while the cursor is open, the `WHEN OTHERS` branch checks `%ISOPEN` and closes the cursor. `RAISE` propagates the original error to the caller so the caller can decide how to handle it.

Do not catch all errors only to print a message and ignore them. Swallowing exceptions can mislead the caller into thinking processing succeeded.

### 8.1. Using a nested block to scope cleanup

~~~sql
DECLARE
    CURSOR c_orders IS
        SELECT order_id
        FROM orders
        WHERE status = 'OPEN';

    l_order_id orders.order_id%TYPE;
BEGIN
    OPEN c_orders;

    BEGIN
        LOOP
            FETCH c_orders INTO l_order_id;
            EXIT WHEN c_orders%NOTFOUND;

            process_order(l_order_id);
        END LOOP;
    EXCEPTION
        WHEN OTHERS THEN
            IF c_orders%ISOPEN THEN
                CLOSE c_orders;
            END IF;
            RAISE;
    END;

    IF c_orders%ISOPEN THEN
        CLOSE c_orders;
    END IF;
END;
/
~~~

A nested block keeps cleanup close to the code that might raise an error. In real-world programs, you can isolate cursor processing into a dedicated procedure to make lifecycle and exception management easier.

## 9. Cursor FOR LOOP: a more concise syntax

PL/SQL supports the cursor FOR LOOP. Oracle automatically opens the cursor, fetches each row, checks for end-of-data, and closes the cursor when the loop ends or exits via an exception.

Example using a declared cursor:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, employee_name
        FROM employees
        WHERE department_id = 10
        ORDER BY employee_id;
BEGIN
    FOR r_employee IN c_employees LOOP
        DBMS_OUTPUT.PUT_LINE(
            r_employee.employee_id || ': ' ||
            r_employee.employee_name
        );
    END LOOP;
END;
/
~~~

There is no need to declare a separate record variable or write manual OPEN/FETCH/CLOSE statements. The `R_EMPLOYEE` variable is implicitly declared by PL/SQL and is scoped only inside the loop.

### 9.1. Cursor FOR LOOP with parameters

~~~sql
DECLARE
    CURSOR c_employees (
        p_department_id employees.department_id%TYPE
    ) IS
        SELECT employee_id, employee_name
        FROM employees
        WHERE department_id = p_department_id;
BEGIN
    FOR r_employee IN c_employees(20) LOOP
        DBMS_OUTPUT.PUT_LINE(r_employee.employee_name);
    END LOOP;
END;
/
~~~

PL/SQL automatically opens the cursor with parameter 20 and closes it when the loop completes.

### 9.2. Cursor FOR LOOP with an inline query

You can omit the explicit cursor declaration if you only need a single loop:

~~~sql
BEGIN
    FOR r_order IN (
        SELECT order_id, total_amount
        FROM orders
        WHERE status = 'OPEN'
        ORDER BY order_id
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r_order.order_id || ': ' || r_order.total_amount
        );
    END LOOP;
END;
/
~~~

This is an implicit cursor FOR LOOP: Oracle manages the cursor internally. This syntax is concise and readable when the query is used in only one place.

### 9.3. When is explicit OPEN/FETCH/CLOSE still needed?

Explicit OPEN/FETCH/CLOSE is useful when:

- You need to fetch step by step in multiple different places.
- You need exact control over when the cursor is opened and closed.
- You need to use cursor attributes between operations.
- You need to coordinate the cursor with specific transaction or locking logic.
- You need to pass a cursor or manage its lifecycle within a complex structure.

If you only iterate over all rows once, a cursor FOR LOOP is usually easier to read and less prone to cleanup bugs.

## 10. Cursor FOR UPDATE and row locking

An explicit cursor can declare `SELECT FOR UPDATE` to lock selected rows, enabling safe read-modify-write operations within a transaction.

Example:

~~~sql
DECLARE
    CURSOR c_accounts IS
        SELECT account_id, balance
        FROM accounts
        WHERE status = 'ACTIVE'
        FOR UPDATE OF balance;

    l_account c_accounts%ROWTYPE;
BEGIN
    OPEN c_accounts;

    LOOP
        FETCH c_accounts INTO l_account;
        EXIT WHEN c_accounts%NOTFOUND;

        UPDATE accounts
        SET balance = balance + 100
        WHERE CURRENT OF c_accounts;
    END LOOP;

    CLOSE c_accounts;
    COMMIT;
END;
/
~~~

`FOR UPDATE` locks the selected rows for the transaction. Other sessions attempting to modify those rows must wait or receive an error depending on how locks are acquired.

### 10.1. WHERE CURRENT OF

`WHERE CURRENT OF cursor_name` updates or deletes the current row pointed to by a `FOR UPDATE` cursor:

~~~sql
UPDATE accounts
SET balance = balance + 100
WHERE CURRENT OF c_accounts;
~~~

There is no need to manually extract the primary key from the record and rewrite a WHERE clause. Oracle identifies the current row from the open cursor.

`WHERE CURRENT OF` can only be used with an appropriate cursor declared with `FOR UPDATE` that is in a valid state. Do not use it with a closed cursor or a cursor not declared with `FOR UPDATE`.

You can also DELETE the current row:

~~~sql
DELETE FROM staging_orders
WHERE CURRENT OF c_staging_orders;
~~~

### 10.2. OF column

In `FOR UPDATE OF`, the column name indicates which columns/tables are locked in certain join queries. It does not mean only that specific column is locked; Oracle locks the corresponding row. The listed column helps identify the table to lock when the query involves multiple tables.

### 10.3. NOWAIT, WAIT, and SKIP LOCKED

You can add a wait policy:

~~~sql
CURSOR c_accounts IS
    SELECT account_id, balance
    FROM accounts
    WHERE status = 'ACTIVE'
    FOR UPDATE NOWAIT;
~~~

`NOWAIT` requests the lock immediately; if unavailable, the statement returns a resource busy error.

~~~sql
CURSOR c_accounts IS
    SELECT account_id, balance
    FROM accounts
    WHERE status = 'ACTIVE'
    FOR UPDATE WAIT 5;
~~~

`WAIT 5` waits up to approximately five seconds.

~~~sql
CURSOR c_jobs IS
    SELECT job_id, payload
    FROM job_queue
    WHERE status = 'READY'
    FOR UPDATE SKIP LOCKED;
~~~

`SKIP LOCKED` skips rows that are currently locked so a worker can pick up other rows. Use this only when queue semantics and retry/claim mechanisms are appropriate.

### 10.4. Lock duration

Locks are held until `COMMIT` or `ROLLBACK`. If a `FOR UPDATE` cursor reads millions of rows and processes them slowly, the transaction may hold many row locks for a long time and increase blocking.

Filter the scope properly, process quickly, avoid calling external services while holding locks, and choose transaction boundaries according to business requirements.

## 11. Do not arbitrarily COMMIT inside a FETCH FOR UPDATE loop

A common design mistake is committing after each row inside a `FOR UPDATE` cursor loop:

~~~sql
-- Do not use this pattern for a FOR UPDATE cursor
LOOP
    FETCH c_accounts INTO l_account;
    EXIT WHEN c_accounts%NOTFOUND;

    UPDATE accounts
    SET balance = balance + 100
    WHERE CURRENT OF c_accounts;

    COMMIT;
END LOOP;
~~~

`COMMIT` releases row locks and can render the `FOR UPDATE` cursor unusable for subsequent FETCH calls; the program may receive `ORA-01002` (fetch out of sequence).

In addition, per-row commits break batch atomicity and increase commit overhead. If an error occurs mid-loop, part of the data is already committed while the rest remains unprocessed.

If you need to split a large batch, design independent batches with clear key ranges, progress state, and rerunnability. Do not simply add `COMMIT` inside the loop to "release locks".

For regular read cursors without `FOR UPDATE`, behavior when committing between fetches and consistent read capability depend on transaction/query lifetime; you should still avoid keeping queries open too long when undo may be reused. Do not rely on a cursor remaining open after commit as a safe batching strategy.

## 12. Explicit cursors and implicit cursors

Oracle automatically creates an implicit cursor for SQL statements such as INSERT, UPDATE, DELETE, and SELECT INTO. PL/SQL provides the attributes `SQL%FOUND`, `SQL%NOTFOUND`, `SQL%ROWCOUNT`, and `SQL%ISOPEN` to inspect the state of the most recent SQL statement.

Explicit cursors are declared and controlled by the developer, using a named cursor:

~~~sql
c_employees%ROWCOUNT
~~~

Implicit cursor attributes use the `SQL` prefix:

~~~sql
SQL%ROWCOUNT
~~~

Example of an implicit cursor after UPDATE:

~~~sql
BEGIN
    UPDATE employees
    SET salary = salary * 1.05
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE(
        'Updated rows: ' || SQL%ROWCOUNT
    );
END;
/
~~~

This is not an explicit cursor. The UPDATE statement executes directly; there is no developer-written OPEN/FETCH/CLOSE.

### 12.1. Differences between SELECT INTO and explicit cursors

`SELECT INTO` is appropriate when expecting exactly one row:

~~~sql
SELECT employee_name
INTO l_employee_name
FROM employees
WHERE employee_id = 100;
~~~

If there is no row, `SELECT INTO` raises `NO_DATA_FOUND`. If there is more than one row, it raises `TOO_MANY_ROWS`.

An explicit cursor is appropriate when iterating over multiple rows. FETCH does not raise `NO_DATA_FOUND` at the end of the result set; check `%NOTFOUND` to exit the loop.

| Requirement | Approach |
|---|---|
| Fetch exactly one row | SELECT INTO |
| Run a single DML statement and check row count | SQL%ROWCOUNT |
| Iterate over multiple rows with a self-managed loop | Explicit cursor |
| Iterate over multiple rows with automatic management | Cursor FOR LOOP |

## 13. Cursors and performance: avoid row-by-row processing when possible

Cursors enable row-by-row processing, but row-by-row loops can be slower than a set-based SQL statement because PL/SQL must switch context back and forth with the SQL engine repeatedly.

Example of raising salaries for all employees in department 10:

Row-by-row approach:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = 10;

BEGIN
    FOR r IN c_employees LOOP
        UPDATE employees
        SET salary = r.salary * 1.05
        WHERE employee_id = r.employee_id;
    END LOOP;
END;
/
~~~

If every row applies the same rule, use a single UPDATE:

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 10;
~~~

A set-based UPDATE statement is usually simpler, requires fewer context switches, and lets the optimizer process the row set.

### 13.1. When a cursor is appropriate

An explicit cursor is appropriate when each row needs:

- Processing decisions based on multi-step PL/SQL logic.
- Calling another procedure with the current row's data.
- Applying rules that cannot be concisely expressed in a single set-based SQL statement.
- Using `SELECT FOR UPDATE` and `WHERE CURRENT OF`.
- Recording per-row results or errors by design.

Even when row-level processing is required, consider `BULK COLLECT` and `FORALL` to reduce context switches when data volumes are large and operations suit bulk processing.

### 13.2. BULK COLLECT and FORALL as an advanced step

`BULK COLLECT` fetches multiple rows into a collection in a single fetch; `FORALL` executes DML across multiple collection elements. This technique differs from traditional row-by-row FETCH.

Illustrative example:

~~~sql
DECLARE
    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    l_ids id_list_t;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_ids
    FROM employees
    WHERE department_id = 10;

    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employees
        SET status = 'REVIEWED'
        WHERE employee_id = l_ids(i);
END;
/
~~~

For large sets, unbounded `BULK COLLECT` can consume significant PGA memory. You can use `LIMIT` with cursor bulk fetching in a loop. Apply this only when justified by measurement; a single set-based DML statement is still usually the first choice.

## 14. Common mistakes with explicit cursors

| Mistake | Consequence | Resolution |
|---|---|---|
| Forgetting OPEN before FETCH | INVALID_CURSOR | Open the cursor before fetching |
| Opening an already open cursor | INVALID_CURSOR | CLOSE before reopening |
| Fetching after CLOSE | INVALID_CURSOR | Only FETCH while the cursor is open |
| Closing an unopened or already closed cursor | INVALID_CURSOR | Check %ISOPEN |
| Not checking %NOTFOUND after FETCH | Processing stale record when out of rows | FETCH then EXIT WHEN %NOTFOUND |
| Checking %NOTFOUND before the first FETCH | Loop does not execute as expected | Place FETCH before the EXIT condition |
| FETCH variable count mismatches select list | Compile/runtime error | Match count, order, and datatype |
| Not closing cursor on exception | Holds resources longer than needed | Clean up using %ISOPEN and RAISE |
| Using SELECT INTO for multiple rows | TOO_MANY_ROWS | Use a cursor or aggregate query |
| Expecting end-of-data FETCH to raise NO_DATA_FOUND | Loop does not catch end of data as expected | Check %NOTFOUND |
| Committing inside a FOR UPDATE cursor | Possible ORA-01002 and early lock release | Choose a different transaction boundary |
| Iterating a cursor to apply the same UPDATE to every row | Slow, many context switches | Use set-based DML |
| Forgetting ORDER BY while expecting fixed order | FETCH order is not guaranteed | Add ORDER BY if required by business logic |
| Keeping cursors/transactions open too long | Increases resources, locks, and undo risk | Limit scope, process fast, close cursor |

## 15. Practice exercises

Run these exercises on an authorized lab schema. Enable `DBMS_OUTPUT` in your SQL tool to view output messages.

### Exercise 1 — Declare a cursor

Declare a cursor retrieving `EMPLOYEE_ID`, `EMPLOYEE_NAME`, and `SALARY` from `EMPLOYEES`. Do not open it yet; explain why declaring a cursor does not execute the SELECT statement.

### Exercise 2 — OPEN and FETCH a single row

Open the cursor, FETCH one row into `%TYPE` variables, print the data, and close the cursor. Add an `ORDER BY` clause to determine which row comes first according to a criterion.

### Exercise 3 — Iterate over the entire result set

Use `LOOP`, `FETCH`, and `EXIT WHEN c_cursor%NOTFOUND`. Track the row count using `%ROWCOUNT` and print the total after the loop.

### Exercise 4 — Empty cursor result

Add a predicate that matches no data. Confirm that the first FETCH does not raise `NO_DATA_FOUND` and that `%NOTFOUND` becomes `TRUE`.

### Exercise 5 — Cursor %ROWTYPE record

Replace individual variables with a `c_cursor%ROWTYPE` record variable. Access fields by column name or alias from the select list.

### Exercise 6 — Parameterized cursor

Declare a cursor taking `DEPARTMENT_ID`. Open the same cursor with two different departments, close it between the two OPEN calls, and compare the results.

### Exercise 7 — Cursor attributes

Print `%ISOPEN` after OPEN, `%ROWCOUNT` after each FETCH, and `%FOUND`/`%NOTFOUND` after a successful FETCH and after the final FETCH. Close the cursor and check `%ISOPEN`.

### Exercise 8 — Exception cleanup

Call a procedure that may raise an error inside the FETCH loop. Use `WHEN OTHERS`, check `%ISOPEN`, CLOSE, and `RAISE`. Confirm that the original error is still propagated to the caller.

### Exercise 9 — Cursor FOR LOOP

Rewrite the full-iteration exercise using `FOR r IN c_cursor LOOP`. Compare lines of code and OPEN/FETCH/CLOSE management responsibilities.

### Exercise 10 — WHERE CURRENT OF

Create a `FOR UPDATE` cursor for staging rows. Fetch each row, UPDATE or DELETE using `WHERE CURRENT OF`, and then `COMMIT` once at the end of the transaction.

### Exercise 11 — Blocking

Session A opens a `FOR UPDATE` cursor and holds the transaction. Session B attempts to UPDATE the same row. Observe Session B waiting, then have Session A `COMMIT`/`ROLLBACK` and observe how Session B proceeds.

### Exercise 12 — Comparing set-based vs. cursor

Create sufficiently large lab data. Perform the same update using a cursor loop and a single set-based UPDATE statement. Compare elapsed time, number of SQL executions, and code complexity.

## 16. Checklist when using explicit cursors

- [ ] Cursor query returns the exact columns needed for processing.
- [ ] Use `%TYPE` or cursor `%ROWTYPE` to reduce datatype mismatch errors.
- [ ] OPEN before FETCH.
- [ ] FETCH and check `%NOTFOUND` before processing the record.
- [ ] Use `%ROWCOUNT` for fetched rows, do not confuse with DML row count.
- [ ] CLOSE upon completion.
- [ ] Close the cursor in the exception path if still open.
- [ ] Do not reopen an already open cursor.
- [ ] Use cursor parameters when the same query needs to run with multiple input values.
- [ ] Use `ORDER BY` if processing order matters.
- [ ] Use `FOR UPDATE`/`WHERE CURRENT OF` only when locking and updating the current row is needed.
- [ ] Do not arbitrarily `COMMIT` inside a `FOR UPDATE` cursor loop.
- [ ] Prefer set-based SQL if every row applies the same transformation.
- [ ] Consider `BULK COLLECT`/`FORALL` when processing many rows in PL/SQL.
- [ ] Test empty cursors, single-row results, multi-row results, and mid-loop exceptions.

## 17. Key takeaways

- An explicit cursor is declared and its lifecycle is controlled by the developer.
- Declaring a cursor defines the SELECT statement; OPEN executes the query and opens the result set.
- FETCH retrieves each row in select-list order into compatible variables or a record.
- A FETCH that finds no row does not raise `NO_DATA_FOUND`; use `%NOTFOUND` to terminate the loop.
- `%FOUND`/`%NOTFOUND` describe the most recent FETCH; `%ROWCOUNT` counts fetched rows; `%ISOPEN` checks open state.
- After OPEN but before the first FETCH, `%FOUND` and `%NOTFOUND` do not yet hold TRUE/FALSE values for controlling a loop.
- CLOSE terminates the cursor; only reopen after closing.
- Cursor parameters allow reusing the same SELECT statement with different input values.
- Cursor FOR LOOPs automatically manage OPEN/FETCH/CLOSE and are usually suitable for single-pass iteration.
- `SELECT FOR UPDATE` locks rows; `WHERE CURRENT OF` updates or deletes the current row of an open cursor.
- Committing inside a `FOR UPDATE` loop can release locks and cause subsequent FETCH calls to fail; design clear transaction boundaries.
- Prefer set-based SQL for uniform transformations across many rows; use cursors when logic genuinely requires row-by-row processing.
- Exception cleanup, limiting cursor/lock hold time, and testing empty result sets keep PL/SQL programs reliable.

### Oracle documentation to cross-reference

- [Oracle Database PL/SQL Language Reference](https://docs.oracle.com/en/database/) — Explicit cursors, cursor FOR LOOP, cursor variables, and cursor attributes.
- [Oracle Database PL/SQL Language Fundamentals](https://docs.oracle.com/en/database/) — Cursor declarations, records, %TYPE, %ROWTYPE, and exception handling.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — SELECT FOR UPDATE, WHERE CURRENT OF, NOWAIT, WAIT, and SKIP LOCKED.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/) — SQL/PLSQL context switching, bulk processing, and execution performance.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — BULK COLLECT, FORALL, and related PL/SQL utilities.

Details of locking, cursor behavior, bulk processing, and datatype support may vary by Oracle release. Cross-reference the documentation for your specific version and run the examples on a lab schema, especially testing empty cursors, mid-loop exceptions, and transactions using `FOR UPDATE`.
