# Cursor FOR LOOP, parameterized cursors, and resource scope in PL/SQL

PL/SQL allows processing the result set of a query using a cursor. When a query returns multiple rows, a program may need to read each row to perform calculations, check conditions, or invoke processing procedures. A cursor FOR LOOP accomplishes this with less boilerplate code: PL/SQL automatically opens the cursor, fetches each row, assigns the row to the loop record, and closes the cursor when the loop finishes.

With a **parameterized cursor**, the same query definition can be opened multiple times with different input values. This approach is useful when processing each department, customer, order, or data group without rewriting the SELECT statement for each iteration.

This lesson belongs to the **PL/SQL and Data** topic of *Database Engine Relational Oracle*. It focuses on:

- Cursor FOR LOOPs with inline queries and explicit cursors.
- Parameterized cursors and passing values when opening a cursor.
- The OPEN, FETCH, CLOSE lifecycle and automatic resource management.
- Scope of cursors, loop records, and nested loops.
- Cursor attributes such as `%FOUND`, `%NOTFOUND`, `%ROWCOUNT`, and `%ISOPEN`.
- Exception handling, nested cursors, performance, and common mistakes.
- Distinguishing regular cursors from `REF CURSOR` and choosing the right tool.

## 1. What is a cursor?

A cursor is the name for the context area Oracle uses to process a SQL statement and its result set. In PL/SQL, a cursor lets a program access each row of a query in processing order.

There are two common forms:

- **Implicit cursor:** Managed automatically by Oracle for SQL statements such as INSERT, UPDATE, DELETE, and SELECT INTO.
- **Explicit cursor:** Declared by the developer to process queries returning multiple rows, then controlled via opening, fetching, and closing, or via a cursor FOR LOOP.

Example of a multi-row query:

~~~sql
SELECT employee_id, last_name, salary
FROM employees
WHERE department_id = 50
ORDER BY employee_id;
~~~

A SELECT statement can return 0, 1, or many rows. `SELECT INTO` in PL/SQL is suitable when expecting exactly one row; if it returns zero rows, Oracle raises `NO_DATA_FOUND`; if it returns more than one row, it raises `TOO_MANY_ROWS`. A cursor is suitable when processing a result set with multiple rows.

## 2. Cursor FOR LOOP with an inline query

The shortest way to iterate through results is to place the SELECT directly inside the FOR LOOP:

~~~sql
BEGIN
    FOR emp IN (
        SELECT employee_id, last_name, salary
        FROM employees
        WHERE department_id = 50
        ORDER BY employee_id
    )
    LOOP
        DBMS_OUTPUT.PUT_LINE(
            emp.employee_id || ' ' ||
            emp.last_name || ' ' ||
            emp.salary
        );
    END LOOP;
END;
/
~~~

PL/SQL automatically performs the necessary steps:

1. Opens the cursor for the query.
2. Fetches each row.
3. Populates the loop record variable `emp` with the columns of the current row.
4. Executes the loop body.
5. Fetches the next row until no data remains.
6. Closes the cursor when the loop completes, including when exiting due to an exception or control flow leaving the loop.

There is no need to declare a separate record variable for `emp`, nor write OPEN, FETCH, or CLOSE. `emp` is an implicit record scoped only to the FOR LOOP.

### Loop record

Each column in the select list becomes a field of the record:

~~~sql
FOR r_order IN (
    SELECT order_id, order_date, amount
    FROM orders
    WHERE customer_id = 100
)
LOOP
    DBMS_OUTPUT.PUT_LINE(
        r_order.order_id || ': ' || r_order.amount
    );
END LOOP;
~~~

Field names are taken from the column names or aliases in the select list. If two expressions have the same name or ambiguous names, provide explicit aliases:

~~~sql
FOR r_total IN (
    SELECT customer_id,
           SUM(amount) AS total_amount
    FROM orders
    GROUP BY customer_id
)
LOOP
    DBMS_OUTPUT.PUT_LINE(r_total.total_amount);
END LOOP;
~~~

The loop record is read-only within a cursor FOR LOOP: do not assign new values to the fields of the loop record. If intermediate calculations are needed, declare a separate variable:

~~~sql
DECLARE
    l_tax NUMBER(12,2);
BEGIN
    FOR r_order IN (
        SELECT order_id, amount
        FROM orders
        WHERE status = 'PAID'
    )
    LOOP
        l_tax := r_order.amount * 0.08;
        DBMS_OUTPUT.PUT_LINE(r_order.order_id || ': ' || l_tax);
    END LOOP;
END;
/
~~~

### When there are no rows

If the SELECT in a cursor FOR LOOP returns 0 rows, the loop body does not execute at all. This does not raise a `NO_DATA_FOUND` error:

~~~sql
BEGIN
    FOR r_emp IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = -1
    )
    LOOP
        DBMS_OUTPUT.PUT_LINE(r_emp.employee_id);
    END LOOP;

    DBMS_OUTPUT.PUT_LINE('Loop finished');
END;
/
~~~

The program still prints `Loop finished`. If business logic requires reporting that no rows were found, you can use a counter variable:

~~~sql
DECLARE
    l_count PLS_INTEGER := 0;
BEGIN
    FOR r_emp IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = -1
    )
    LOOP
        l_count := l_count + 1;
        DBMS_OUTPUT.PUT_LINE(r_emp.employee_id);
    END LOOP;

    IF l_count = 0 THEN
        DBMS_OUTPUT.PUT_LINE('No employees found');
    END IF;
END;
/
~~~

## 3. Explicit cursors and cursor FOR LOOPs

An explicit cursor is declared in the DECLARE section of a block or in the specification/body of a subprogram. It has a name and can be opened with OPEN, read with FETCH, and closed with CLOSE, or used with a cursor FOR LOOP.

Syntax:

~~~sql
CURSOR cursor_name IS
    select_statement;
~~~

Example:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, last_name, salary
        FROM employees
        WHERE department_id = 50
        ORDER BY employee_id;
BEGIN
    FOR emp IN c_employees
    LOOP
        DBMS_OUTPUT.PUT_LINE(
            emp.employee_id || ' ' || emp.last_name
        );
    END LOOP;
END;
/
~~~

A cursor FOR LOOP can reference a declared explicit cursor by name. Even though the cursor has a name, PL/SQL still automatically handles OPEN, FETCH, and CLOSE inside this loop.

### When to use an inline query vs. declaring a cursor?

| Style | Appropriate when |
| --- | --- |
| FOR r IN (SELECT ...) | The query is used in only one place and you want concise, clear code. |
| CURSOR c IS SELECT ...; FOR r IN c | You want to name the query, reuse the definition within the block, or add parameters. |
| Manual OPEN/FETCH/CLOSE | You need control over cursor lifecycle, step-by-step fetching, or special logic integration. |
| REF CURSOR | You need to pass a result set via parameters or return a result set from a subprogram. |

A cursor FOR LOOP is usually the most readable option when you only need to process rows sequentially and do not need manual control over fetching.

## 4. Parameterized cursors

A parameterized cursor is an explicit cursor that receives input values when opened. Parameters are used in the cursor's SELECT statement just like input variables of a reusable query.

Syntax:

~~~sql
CURSOR cursor_name (
    parameter_name [IN] datatype
    [, parameter_name [IN] datatype ...]
) IS
    select_statement;
~~~

Example of a cursor filtering employees by department:

~~~sql
DECLARE
    CURSOR c_employees (p_department_id NUMBER) IS
        SELECT employee_id, last_name, salary
        FROM employees
        WHERE department_id = p_department_id
        ORDER BY employee_id;
BEGIN
    FOR emp IN c_employees(50)
    LOOP
        DBMS_OUTPUT.PUT_LINE(
            emp.employee_id || ' ' ||
            emp.last_name || ' ' ||
            emp.salary
        );
    END LOOP;
END;
/
~~~

Each time the cursor is opened, the argument value is assigned to the cursor parameter. Inside the query, `p_department_id` references the cursor parameter, not a column of the `EMPLOYEES` table.

### Passing multiple parameters

~~~sql
DECLARE
    CURSOR c_orders (
        p_customer_id NUMBER,
        p_min_amount  NUMBER
    ) IS
        SELECT order_id, order_date, amount
        FROM orders
        WHERE customer_id = p_customer_id
          AND amount >= p_min_amount
        ORDER BY order_date, order_id;
BEGIN
    FOR r_order IN c_orders(100, 500)
    LOOP
        DBMS_OUTPUT.PUT_LINE(
            r_order.order_id || ': ' || r_order.amount
        );
    END LOOP;
END;
/
~~~

Arguments can be passed positionally:

~~~sql
FOR r_order IN c_orders(100, 500) LOOP
    NULL;
END LOOP;
~~~

Or by name:

~~~sql
FOR r_order IN c_orders(
    p_min_amount => 500,
    p_customer_id => 100
)
LOOP
    NULL;
END LOOP;
~~~

Named notation helps prevent order mistakes when a cursor has many parameters or multiple parameters of the same data type.

### Opening the same cursor multiple times with different values

~~~sql
DECLARE
    CURSOR c_employees (p_department_id NUMBER) IS
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = p_department_id;
BEGIN
    FOR emp IN c_employees(10)
    LOOP
        DBMS_OUTPUT.PUT_LINE('D10: ' || emp.last_name);
    END LOOP;

    FOR emp IN c_employees(20)
    LOOP
        DBMS_OUTPUT.PUT_LINE('D20: ' || emp.last_name);
    END LOOP;
END;
/
~~~

Each cursor FOR LOOP opens the cursor with the corresponding parameter, processes the result set, and closes the cursor upon completion. The same query definition is reused with two different datasets.

### Data types of cursor parameters

Declare parameter types compatible with the compared columns. You can use anchored types:

~~~sql
DECLARE
    CURSOR c_employees (
        p_department_id employees.department_id%TYPE
    ) IS
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = p_department_id;
BEGIN
    FOR emp IN c_employees(50)
    LOOP
        DBMS_OUTPUT.PUT_LINE(emp.last_name);
    END LOOP;
END;
/
~~~

A cursor parameter defaults to `IN`; it receives a value for the query to use. A cursor parameter is not an `OUT` parameter to return data to the caller; results are read through the cursor's rows.

### Default values for cursor parameters

Cursor parameters can have default expressions:

~~~sql
DECLARE
    CURSOR c_orders (
        p_status VARCHAR2 DEFAULT 'OPEN'
    ) IS
        SELECT order_id, amount
        FROM orders
        WHERE status = p_status;
BEGIN
    FOR r IN c_orders
    LOOP
        DBMS_OUTPUT.PUT_LINE(r.order_id);
    END LOOP;

    FOR r IN c_orders('PAID')
    LOOP
        DBMS_OUTPUT.PUT_LINE('Paid: ' || r.order_id);
    END LOOP;
END;
/
~~~

The call without arguments uses the default value `OPEN`; the second call uses `PAID`. When designing cursors with multiple default parameters, use named notation if you want to omit leading parameters or clarify intent.

## 5. Parameterized cursors with manual OPEN/FETCH/CLOSE

A parameterized cursor can also be managed manually:

~~~sql
DECLARE
    CURSOR c_employees (p_department_id NUMBER) IS
        SELECT employee_id, last_name, salary
        FROM employees
        WHERE department_id = p_department_id
        ORDER BY employee_id;

    l_employee_id employees.employee_id%TYPE;
    l_last_name   employees.last_name%TYPE;
    l_salary      employees.salary%TYPE;
BEGIN
    OPEN c_employees(50);

    LOOP
        FETCH c_employees
        INTO l_employee_id, l_last_name, l_salary;

        EXIT WHEN c_employees%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            l_employee_id || ' ' || l_last_name || ' ' || l_salary
        );
    END LOOP;

    CLOSE c_employees;
END;
/
~~~

In this approach, the developer is responsible for:

1. Opening the cursor with the required arguments.
2. Fetching each row into the corresponding variable list.
3. Checking `%NOTFOUND` after each FETCH.
4. Exiting the loop when no rows remain.
5. Closing the cursor to release cursor state.

The order of checking is very important. If `%NOTFOUND` is checked before the first FETCH, the attribute does not yet reflect a fetch result; always FETCH first and then check.

### Using cursor%ROWTYPE to reduce variable list mismatch errors

Instead of declaring individual variables for each column, you can declare a record based on the cursor:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, last_name, salary
        FROM employees
        WHERE department_id = 50;

    r_employee c_employees%ROWTYPE;
BEGIN
    OPEN c_employees;
    LOOP
        FETCH c_employees INTO r_employee;
        EXIT WHEN c_employees%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            r_employee.employee_id || ' ' || r_employee.last_name
        );
    END LOOP;
    CLOSE c_employees;
END;
/
~~~

`cursor%ROWTYPE` creates a record with fields matching the cursor's select list. If the select list changes, the record follows the cursor structure after the program is recompiled.

## 6. Resource scope and automatic cursor closing

An explicit cursor has two distinct aspects:

- **Scope of the cursor name:** where PL/SQL code can reference the declared cursor.
- **Open state of the cursor:** whether the cursor has been opened and not yet closed.

A cursor declared in the DECLARE section of a block can be used in the execution section and nested sub-blocks. When the block ends, a local cursor is no longer within that block's scope. However, during execution, a manually opened explicit cursor must be properly closed.

### Cursor FOR LOOP manages OPEN/FETCH/CLOSE automatically

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = 50;
BEGIN
    FOR emp IN c_employees
    LOOP
        DBMS_OUTPUT.PUT_LINE(emp.last_name);

        IF emp.employee_id = 100 THEN
            EXIT;
        END IF;
    END LOOP;

    -- Cursor c_employees has been closed automatically.
    IF c_employees%ISOPEN THEN
        DBMS_OUTPUT.PUT_LINE('Still open');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Closed');
    END IF;
END;
/
~~~

When the loop finishes naturally, hits `EXIT`, or exits via an exception, PL/SQL automatically closes the cursor opened for the loop. Do not call `CLOSE` on a cursor managed by a cursor FOR LOOP; doing so is unnecessary and will cause an error because the cursor is already closed.

### Manual cursors must be closed in both success and error paths

If using manual OPEN/FETCH/CLOSE, ensure `CLOSE` is called even if processing a row raises an exception:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = 50;

    r_employee c_employees%ROWTYPE;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees INTO r_employee;
        EXIT WHEN c_employees%NOTFOUND;

        -- Replace with actual business processing.
        DBMS_OUTPUT.PUT_LINE(r_employee.last_name);
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

The handler checks `%ISOPEN` before calling `CLOSE` so it does not attempt to close an unopened or already closed cursor. `RAISE` propagates the error to the caller instead of silently ignoring it. If the code has multiple `RETURN`/`EXIT` points or error branches, inspect every execution path to avoid leaving the cursor open.

### When OPEN fails

If opening the cursor raises an error, the cursor state may remain unopened. In the exception handler, checking `%ISOPEN` before `CLOSE` is the safe approach:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        IF c_employees%ISOPEN THEN
            CLOSE c_employees;
        END IF;
        RAISE;
~~~

Do not call FETCH or read `%FOUND`/`%NOTFOUND` on an unopened cursor. `%ISOPEN` is the attribute to use for checking open state.

## 7. Cursor attributes

Explicit cursors provide attributes to inspect cursor state and FETCH results:

| Attribute | Meaning |
| --- | --- |
| %ISOPEN | TRUE if the cursor is open; FALSE if closed. |
| %FOUND | TRUE if the most recent FETCH returned a row; FALSE if no row was returned. |
| %NOTFOUND | TRUE if the most recent FETCH returned no row; FALSE if a row was returned. |
| %ROWCOUNT | Number of rows fetched from the cursor since OPEN. |

Example:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = 50;

    r_employee c_employees%ROWTYPE;
BEGIN
    OPEN c_employees;

    DBMS_OUTPUT.PUT_LINE(
        'Open? ' || CASE WHEN c_employees%ISOPEN THEN 'YES' ELSE 'NO' END
    );

    LOOP
        FETCH c_employees INTO r_employee;
        EXIT WHEN c_employees%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            'Fetched ' || c_employees%ROWCOUNT ||
            ': ' || r_employee.last_name
        );
    END LOOP;

    DBMS_OUTPUT.PUT_LINE('Total fetched: ' || c_employees%ROWCOUNT);
    CLOSE c_employees;
END;
/
~~~

### Attribute values before and after FETCH

- After OPEN but before the first FETCH, `%ROWCOUNT` is 0; `%FOUND` and `%NOTFOUND` have no fetch result yet and are NULL.
- After a successful FETCH, `%FOUND` is TRUE, `%NOTFOUND` is FALSE, and `%ROWCOUNT` increments.
- After a FETCH with no more rows, `%FOUND` is FALSE, `%NOTFOUND` is TRUE, and `%ROWCOUNT` does not increment further.
- After CLOSE, only use `%ISOPEN` to check status; accessing attributes that require an open cursor raises `INVALID_CURSOR`.

Therefore, the standard loop pattern is:

~~~sql
LOOP
    FETCH c_employees INTO r_employee;
    EXIT WHEN c_employees%NOTFOUND;

    -- Process the fetched row.
END LOOP;
~~~

Do not write `EXIT WHEN %NOTFOUND` before FETCH, because the program must attempt to retrieve a row before knowing whether that fetch succeeded.

### Implicit SQL cursor attributes

DML SQL statements use the implicit `SQL` cursor. You can inspect attributes such as `SQL%ROWCOUNT` immediately after the statement:

~~~sql
BEGIN
    UPDATE employees
    SET salary = salary * 1.05
    WHERE department_id = 50;

    DBMS_OUTPUT.PUT_LINE(
        'Updated rows: ' || SQL%ROWCOUNT
    );
END;
/
~~~

`SQL%ROWCOUNT` is the number of rows affected by the most recent SQL statement. If you run another SQL statement before reading the attribute, the attribute value will have changed. `SQL%ISOPEN` is always `FALSE` because implicit cursors are automatically closed by Oracle after the statement; do not use `SQL%ISOPEN` to manage explicit cursors.

## 8. Scope of cursors and loop records

A cursor declared in a block can only be referenced within that block and its nested sub-blocks. An outer block cannot reference a cursor declared only inside an inner sub-block.

~~~sql
DECLARE
    CURSOR c_outer IS
        SELECT employee_id FROM employees;
BEGIN
    DECLARE
        CURSOR c_inner IS
            SELECT department_id FROM departments;
    BEGIN
        OPEN c_outer;
        CLOSE c_outer;

        OPEN c_inner;
        CLOSE c_inner;
    END;

    -- c_outer is still in scope here.
    -- c_inner is out of scope here.
END;
/
~~~

The loop record is implicitly declared for the FOR loop and is scoped only within the loop:

~~~sql
BEGIN
    FOR emp IN (
        SELECT employee_id, last_name
        FROM employees
    )
    LOOP
        DBMS_OUTPUT.PUT_LINE(emp.last_name);
    END LOOP;

    -- emp is no longer visible here.
END;
/
~~~

If you need to retain a value after the loop, copy the required field into a variable declared in the outer block:

~~~sql
DECLARE
    l_last_employee_id employees.employee_id%TYPE;
BEGIN
    FOR emp IN (
        SELECT employee_id
        FROM employees
        ORDER BY employee_id
    )
    LOOP
        l_last_employee_id := emp.employee_id;
    END LOOP;

    DBMS_OUTPUT.PUT_LINE(l_last_employee_id);
END;
/
~~~

If there are no rows, `l_last_employee_id` remains NULL because it was never assigned inside the loop.

## 9. Nested cursor FOR LOOP with parameterized cursors

Parameterized cursors are especially useful when an outer loop identifies a data group and an inner loop fetches the rows belonging to that group.

Example iterating over each department and then each employee in that department:

~~~sql
DECLARE
    CURSOR c_departments IS
        SELECT department_id, department_name
        FROM departments
        ORDER BY department_id;

    CURSOR c_employees (
        p_department_id employees.department_id%TYPE
    ) IS
        SELECT employee_id, last_name, salary
        FROM employees
        WHERE department_id = p_department_id
        ORDER BY employee_id;
BEGIN
    FOR d IN c_departments
    LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Department: ' || d.department_name
        );

        FOR e IN c_employees(d.department_id)
        LOOP
            DBMS_OUTPUT.PUT_LINE(
                '  ' || e.employee_id || ' ' ||
                e.last_name || ' ' || e.salary
            );
        END LOOP;
    END LOOP;
END;
/
~~~

The outer loop opens the departments cursor. For each department, the inner loop opens the employees cursor using the `department_id` of the current row. When the inner loop finishes, the employees cursor is closed; the outer loop advances to the next department. When the outer loop finishes, the departments cursor is closed as well.

### Scope of loop records in nested loops

- `d` exists only within the department FOR loop.
- `e` exists only within the employee FOR loop.
- The inner loop can reference `d.department_id` because `d` belongs to the enclosing scope.
- After each respective loop ends, its loop record is no longer visible.

Do not declare a variable with the same name as a loop record in an inner scope unnecessarily; shadowing makes references harder to read.

### Watch out for query execution count

In the example above, the employee cursor query is opened once per department. If there are thousands of departments, that can result in many query executions. This is a nested cursor loop pattern and is not always the most efficient approach.

If the goal is simply to retrieve departments along with their employees, a JOIN query can be simpler and more efficient:

~~~sql
SELECT d.department_id,
       d.department_name,
       e.employee_id,
       e.last_name,
       e.salary
FROM departments d
LEFT JOIN employees e
  ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
~~~

Only use nested cursors when each group genuinely requires separate processing logic or the query depends on group values in a way not easily expressed in a single SQL statement. Consider the number of groups, parse/execute overhead, and execution plans.

## 10. Exceptions in cursor FOR LOOPs

A cursor FOR LOOP automatically closes the cursor if an exception causes control flow to exit the loop. However, an exception does not automatically roll back DML changes already executed by the loop body.

Example:

~~~sql
BEGIN
    FOR emp IN (
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = 50
    )
    LOOP
        DBMS_OUTPUT.PUT_LINE(emp.employee_id);

        IF emp.salary < 0 THEN
            RAISE_APPLICATION_ERROR(
                -20001,
                'Invalid salary'
            );
        END IF;
    END LOOP;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
        RAISE;
END;
/
~~~

When the exception exits the loop, the loop-managed cursor is closed automatically. If any UPDATE/INSERT statements ran before the exception occurred, those changes still belong to the current transaction and must be committed or rolled back by the caller according to business rules.

### Exception handler in an inner block

You can place an exception handler in a block inside the loop body to handle per-row errors and continue to the next row:

~~~sql
BEGIN
    FOR emp IN (
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = 50
        ORDER BY employee_id
    )
    LOOP
        BEGIN
            IF emp.salary < 0 THEN
                RAISE_APPLICATION_ERROR(
                    -20001,
                    'Invalid salary for employee ' || emp.employee_id
                );
            END IF;

            DBMS_OUTPUT.PUT_LINE(
                'Processed employee ' || emp.employee_id
            );
        EXCEPTION
            WHEN OTHERS THEN
                DBMS_OUTPUT.PUT_LINE(
                    'Skipped employee ' || emp.employee_id ||
                    ': ' || SQLERRM
                );
        END;
    END LOOP;
END;
/
~~~

The inner handler processes the error for the current row, allowing the loop to continue. Use this pattern only when business logic permits skipping erroneous rows; do not swallow errors if doing so produces incorrect results or hides failures.

### DML inside loops and transaction boundaries

Example:

~~~sql
BEGIN
    FOR emp IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = 50
    )
    LOOP
        UPDATE employee_audit
        SET processed_flag = 'Y'
        WHERE employee_id = emp.employee_id;
    END LOOP;
END;
/
~~~

A cursor FOR LOOP does not automatically `COMMIT` after each row, nor does it automatically `ROLLBACK` upon completion. All DML remains part of the session's transaction. The caller decides `COMMIT`/`ROLLBACK`; if per-batch commits are needed, explicit transaction boundaries must be designed.

## 11. Distinguishing cursor FOR LOOP from REF CURSOR

A static explicit cursor has its SELECT statement fixed in PL/SQL code. A `REF CURSOR` is a cursor variable that can point to a result set opened with `OPEN FOR`; it can be passed as a parameter or returned to a caller.

Example using `SYS_REFCURSOR`:

~~~sql
CREATE OR REPLACE PROCEDURE open_employee_result (
    p_department_id IN NUMBER,
    p_result OUT SYS_REFCURSOR
) AS
BEGIN
    OPEN p_result FOR
        SELECT employee_id, last_name, salary
        FROM employees
        WHERE department_id = p_department_id
        ORDER BY employee_id;
END;
/
~~~

The caller receives the cursor variable and is responsible for reading/closing it according to the API in use. `REF CURSOR` is suitable when returning a result set to an application or passing results between subprograms. It has its own resource lifecycle; do not confuse it with the automatic loop record of a cursor FOR LOOP.

### Choosing the cursor type

| Requirement | Suitable approach |
| --- | --- |
| Iterate over a local query in PL/SQL | Cursor FOR LOOP with inline SELECT |
| Reuse query in block, pass conditions | Parameterized explicit cursor |
| Need manual control over each FETCH | OPEN/FETCH/CLOSE |
| Return result set to client/caller | REF CURSOR or SYS_REFCURSOR |
| Simply update/delete by a SQL condition | Set-based DML, no cursor needed |

## 12. Performance and choosing set-based processing

Cursor FOR LOOPs make cursor management code cleaner and safer, but they do not make row-by-row processing faster than set-based SQL statements.

### Prefer a single SQL statement when logic can be expressed set-based

Instead of:

~~~sql
BEGIN
    FOR emp IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = 50
    )
    LOOP
        UPDATE employees
        SET salary = salary * 1.05
        WHERE employee_id = emp.employee_id;
    END LOOP;
END;
/
~~~

You can usually use a single statement:

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 50;
~~~

A set-based UPDATE statement typically reduces context switching between the PL/SQL and SQL engines while giving the optimizer the opportunity to optimize the entire operation.

### When is a cursor loop reasonable?

- Each row needs to invoke custom PL/SQL logic not easily expressed in SQL.
- You need to process each record and call another API row by row.
- The dataset is small or business logic requires a specific processing order.
- Per-row error control or per-row result logging is needed.

When processing large volumes, consider `BULK COLLECT` with `LIMIT` and `FORALL` to reduce context switching, while managing batch size and memory.

### BULK COLLECT and FORALL

Illustrative example fetching data in batches:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id
        FROM employees
        WHERE department_id = 50;

    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    l_employee_ids t_employee_ids;
BEGIN
    OPEN c_employees;
    LOOP
        FETCH c_employees
        BULK COLLECT INTO l_employee_ids
        LIMIT 500;

        EXIT WHEN l_employee_ids.COUNT = 0;

        FORALL i IN 1 .. l_employee_ids.COUNT
            UPDATE employee_audit
            SET processed_flag = 'Y'
            WHERE employee_id = l_employee_ids(i);
    END LOOP;
    CLOSE c_employees;
END;
/
~~~

`LIMIT 500` is an example; choose it based on row size, PGA memory, and workload. In production code, also add exception handling to ensure the cursor is closed if an error occurs, or use an appropriate cursor FOR LOOP structure. If the UPDATE can be done directly as set-based SQL, that is still usually the preferred option.

## 13. Cursor FOR UPDATE and WHERE CURRENT OF

A cursor can lock selected rows so the program can process and then update the exact current row. Use the `FOR UPDATE` clause in the cursor query and `WHERE CURRENT OF` in DML:

~~~sql
DECLARE
    CURSOR c_orders IS
        SELECT order_id, status
        FROM orders
        WHERE status = 'PENDING'
        FOR UPDATE OF status;
BEGIN
    FOR r_order IN c_orders
    LOOP
        UPDATE orders
        SET status = 'PROCESSING'
        WHERE CURRENT OF c_orders;
    END LOOP;
END;
/
~~~

The cursor FOR LOOP automatically opens the cursor and closes it at the end; row locks are held by the transaction until `COMMIT` or `ROLLBACK`. Closing the cursor does not automatically release row locks if the transaction remains open.

### NOWAIT, WAIT, and SKIP LOCKED

You can control behavior when a row is already locked by another session:

~~~sql
CURSOR c_orders IS
    SELECT order_id, status
    FROM orders
    WHERE status = 'PENDING'
    FOR UPDATE SKIP LOCKED;
~~~

- NOWAIT: if a row to be locked is held by another session, raise an error instead of waiting.
- WAIT n: wait up to the specified number of seconds and then raise a timeout error if still locked.
- SKIP LOCKED: skip rows that are currently locked and continue retrieving other rows.

`SKIP LOCKED` is useful when multiple workers process a queue concurrently, provided the design ensures skipped rows will be handled later by another worker. Do not use it if skipping rows compromises report or business completeness.

### Limitations of FOR UPDATE

`FOR UPDATE` cannot be applied arbitrarily to every query. Queries with `DISTINCT`, `GROUP BY`, aggregates, set operators, or complex views may not allow row locking as desired. Verify syntax and execution plans against the actual query. The `OF` clause specifies columns/tables involved in locking; it is not a list of columns that will be updated.

## 14. Scope of cursor parameters and passed values

A cursor parameter is used inside the cursor's SELECT statement and receives its value when the cursor is opened. Each OPEN can use a different value; a cursor FOR LOOP performs OPEN/CLOSE implicitly for each execution.

~~~sql
DECLARE
    l_department_id NUMBER := 10;

    CURSOR c_employees(p_department_id NUMBER) IS
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = p_department_id;
BEGIN
    FOR emp IN c_employees(l_department_id)
    LOOP
        DBMS_OUTPUT.PUT_LINE(emp.last_name);
    END LOOP;

    l_department_id := 20;

    FOR emp IN c_employees(l_department_id)
    LOOP
        DBMS_OUTPUT.PUT_LINE(emp.last_name);
    END LOOP;
END;
/
~~~

The two invocations open the cursor with two different values. The parameter value is used for the corresponding open; changing the PL/SQL variable after the first loop does not alter the already processed result set.

### Parameterless cursors vs. parameterized cursors

An explicit cursor without parameters can still reference in-scope variables at its declaration site, but doing so creates an implicit dependency on block state. A parameterized cursor makes its inputs explicit at the call site, making it easier to reuse and understand.

~~~sql
DECLARE
    l_department_id NUMBER := 10;

    CURSOR c_employees IS
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = l_department_id;
BEGIN
    FOR emp IN c_employees
    LOOP
        DBMS_OUTPUT.PUT_LINE(emp.last_name);
    END LOOP;
END;
/
~~~

This example is valid, though the query depends on an outer variable. When the same query needs to be opened for multiple departments, a parameterized cursor is clearer:

~~~sql
CURSOR c_employees(p_department_id NUMBER) IS
    SELECT employee_id, last_name
    FROM employees
    WHERE department_id = p_department_id;
~~~

## 15. Common errors and how to handle them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| SELECT INTO raises TOO_MANY_ROWS | Query returns multiple rows while using single-row form | Use a cursor FOR LOOP or refine the condition to return exactly one row. |
| Cursor FOR LOOP does not execute | Query returns 0 rows | Check predicate; use a counter variable if detecting an empty set is needed. |
| Loop record cannot be used after END LOOP | Record is scoped only to the loop | Copy fields you need to keep into variables declared in the outer block. |
| Cursor remains open and unclosed | Manual OPEN/FETCH/CLOSE with an error branch missing CLOSE | Use a cursor FOR LOOP or an exception handler that checks %ISOPEN before CLOSE. |
| INVALID_CURSOR | FETCH/CLOSE or attribute read when cursor is not in a valid state | Check OPEN/CLOSE sequence and use %ISOPEN before acting. |
| FETCH INTO reports wrong count/type | Target variable list does not match select list | Use cursor%ROWTYPE or synchronize variable count, order, and types. |
| Cursor parameter filters incorrectly | Wrong positional argument order or name collision with column | Use named notation and a p_ prefix for parameters. |
| %NOTFOUND checked incorrectly | Checked before FETCH | FETCH first, then EXIT WHEN cursor%NOTFOUND. |
| DML inside loop not automatically rolled back | Cursor lifecycle and transaction lifecycle are separate | Caller decides COMMIT/ROLLBACK. |
| Nested cursor is slow | Inner loop query executes many times | Consider JOIN/set-based SQL or batch processing. |
| Cursor loop processing large data is slow | Row-by-row processing, context switching, or heavy logic | Use set-based SQL, or BULK COLLECT/FORALL when appropriate. |
| Row locks persist after CLOSE cursor | Transaction has not ended | COMMIT/ROLLBACK to release locks. |

## 16. Comprehensive practice lab

These examples use sample tables in a learning schema with `CREATE TABLE` privileges and appropriate quota. DDL performs an implicit commit in Oracle; do not run table creation/deletion commands on production business schemas.

### Step 1: create sample data

~~~sql
CREATE TABLE lab_departments (
    department_id NUMBER PRIMARY KEY,
    department_name VARCHAR2(50) NOT NULL
);

CREATE TABLE lab_employees (
    employee_id NUMBER PRIMARY KEY,
    department_id NUMBER NOT NULL,
    employee_name VARCHAR2(80) NOT NULL,
    salary NUMBER(12,2) NOT NULL
);

INSERT INTO lab_departments VALUES (10, 'Sales');
INSERT INTO lab_departments VALUES (20, 'Engineering');
INSERT INTO lab_departments VALUES (30, 'Support');

INSERT INTO lab_employees VALUES (1, 10, 'Mai', 12000);
INSERT INTO lab_employees VALUES (2, 10, 'An', 13000);
INSERT INTO lab_employees VALUES (3, 20, 'Binh', 18000);
INSERT INTO lab_employees VALUES (4, 20, 'Lan', 19000);
INSERT INTO lab_employees VALUES (5, 30, 'Minh', 11000);
COMMIT;
~~~

### Step 2: cursor FOR LOOP with inline SELECT

~~~sql
SET SERVEROUTPUT ON;

BEGIN
    FOR r_emp IN (
        SELECT employee_id, employee_name, salary
        FROM lab_employees
        WHERE department_id = 10
        ORDER BY employee_id
    )
    LOOP
        DBMS_OUTPUT.PUT_LINE(
            r_emp.employee_id || ' ' ||
            r_emp.employee_name || ' ' || r_emp.salary
        );
    END LOOP;
END;
/
~~~

Try changing `department_id` to 999 and observe that the loop does not run while the block still completes normally.

### Step 3: parameterized explicit cursor

~~~sql
DECLARE
    CURSOR c_employees(p_department_id NUMBER) IS
        SELECT employee_id, employee_name, salary
        FROM lab_employees
        WHERE department_id = p_department_id
        ORDER BY employee_id;
BEGIN
    FOR r_emp IN c_employees(20)
    LOOP
        DBMS_OUTPUT.PUT_LINE(
            r_emp.employee_name || ': ' || r_emp.salary
        );
    END LOOP;
END;
/
~~~

Run again with 10 and 30. Explain why the same cursor can be used for multiple departments.

### Step 4: passing parameters by name

~~~sql
DECLARE
    CURSOR c_employees(
        p_department_id NUMBER,
        p_min_salary NUMBER
    ) IS
        SELECT employee_id, employee_name, salary
        FROM lab_employees
        WHERE department_id = p_department_id
          AND salary >= p_min_salary;
BEGIN
    FOR r_emp IN c_employees(
        p_min_salary => 15000,
        p_department_id => 20
    )
    LOOP
        DBMS_OUTPUT.PUT_LINE(r_emp.employee_name);
    END LOOP;
END;
/
~~~

### Step 5: using OPEN/FETCH/CLOSE and cursor attributes

~~~sql
DECLARE
    CURSOR c_employees(p_department_id NUMBER) IS
        SELECT employee_id, employee_name
        FROM lab_employees
        WHERE department_id = p_department_id
        ORDER BY employee_id;

    r_emp c_employees%ROWTYPE;
BEGIN
    OPEN c_employees(10);

    LOOP
        FETCH c_employees INTO r_emp;
        EXIT WHEN c_employees%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            c_employees%ROWCOUNT || ': ' || r_emp.employee_name
        );
    END LOOP;

    DBMS_OUTPUT.PUT_LINE(
        'Fetched rows = ' || c_employees%ROWCOUNT
    );
    CLOSE c_employees;
END;
/
~~~

### Step 6: nested cursor FOR LOOP

~~~sql
DECLARE
    CURSOR c_departments IS
        SELECT department_id, department_name
        FROM lab_departments
        ORDER BY department_id;

    CURSOR c_employees(p_department_id NUMBER) IS
        SELECT employee_id, employee_name
        FROM lab_employees
        WHERE department_id = p_department_id
        ORDER BY employee_id;
BEGIN
    FOR d IN c_departments
    LOOP
        DBMS_OUTPUT.PUT_LINE(d.department_name);

        FOR e IN c_employees(d.department_id)
        LOOP
            DBMS_OUTPUT.PUT_LINE('  ' || e.employee_name);
        END LOOP;
    END LOOP;
END;
/
~~~

### Step 7: observing exceptions and automatic cursor closing

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, employee_name
        FROM lab_employees;

    r_emp c_employees%ROWTYPE;
BEGIN
    OPEN c_employees;
    FETCH c_employees INTO r_emp;

    RAISE_APPLICATION_ERROR(-20010, 'Test cleanup');

    CLOSE c_employees;
EXCEPTION
    WHEN OTHERS THEN
        IF c_employees%ISOPEN THEN
            CLOSE c_employees;
        END IF;
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
END;
/
~~~

Observe the handler closing the cursor before the block ends. In a cursor FOR LOOP, PL/SQL performs the corresponding cleanup automatically.

### Step 8: clean up data

~~~sql
DROP TABLE lab_employees PURGE;
DROP TABLE lab_departments PURGE;
~~~

Run this only when you have finished the lab and no longer need the data. `DROP TABLE` is DDL with an implicit commit; `PURGE` bypasses the Recycle Bin.

## 17. Self-check questions

1. **What is a cursor used for?** Managing the processing context of a SQL statement and its result set, enabling row-by-row reading.
2. **What steps does a cursor FOR LOOP perform automatically?** OPEN, FETCH, iterating over rows, and CLOSE.
3. **Does a SELECT in a cursor FOR LOOP returning 0 rows raise NO_DATA_FOUND?** No; the loop body simply does not execute.
4. **Where is the loop record in scope?** Only inside the corresponding FOR loop.
5. **Where are explicit cursors declared?** In the declarative section of a block, subprogram, or package as appropriate.
6. **What is a parameterized cursor?** An explicit cursor that accepts input values when opened to filter or compute its result set.
7. **What is the default mode of a cursor parameter?** IN.
8. **Can the same parameterized cursor be opened with different values?** Yes; each OPEN passes its own arguments.
9. **What is the benefit of named notation?** It clarifies arguments and prevents parameter order errors.
10. **What should you pay attention to with manual OPEN/FETCH/CLOSE?** You must FETCH before checking `%NOTFOUND` and ensure CLOSE in error paths as well.
11. **What does %ROWCOUNT mean?** The number of rows fetched from the cursor since it was opened.
12. **What is %ISOPEN used for?** Checking whether a cursor is currently open or closed.
13. **Does a cursor FOR LOOP automatically COMMIT?** No; cursor cleanup is not transaction cleanup.
14. **Does closing a cursor release FOR UPDATE row locks?** Not necessarily; row locks are held until COMMIT/ROLLBACK.
15. **What performance risk does a nested cursor loop have?** The inner loop query may execute many times; JOIN/set-based SQL can be more efficient.
16. **When is REF CURSOR used?** When passing or returning a result set between subprograms or to a client.
17. **When should BULK COLLECT/FORALL be used?** When processing large volumes in batches where a single set-based SQL statement cannot replace it.
18. **Does an exception in a cursor FOR LOOP automatically roll back prior DML?** No; only the cursor is closed automatically, while the transaction remains managed by the caller.

Cursor FOR LOOPs make processing result sets concise and safe because PL/SQL manages OPEN, FETCH, and CLOSE automatically. Parameterized cursors allow reusing queries with clear inputs, especially in nested loops grouped by key. When manual fetch control is needed, you must manage cursor state and cleanup across error paths as well. Always distinguish cursor lifecycle from transaction lifecycle, and prefer set-based SQL or bulk processing when handling large data volumes.
