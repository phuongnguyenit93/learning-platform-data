# Implicit Cursors and SQL%FOUND, SQL%NOTFOUND, and SQL%ISOPEN Attributes

Whenever PL/SQL executes a SQL statement within the scope managed by PL/SQL, Oracle uses an implicit cursor named `SQL`. The developer does not need to declare, `OPEN`, `FETCH`, or `CLOSE` this cursor. After the statement finishes, you can use the attributes of `SQL` to know whether the statement affected any rows and how many rows were processed.

Four commonly used attributes:

- `SQL%FOUND`: indicates whether the most recent SQL statement affected or returned at least one row.
- `SQL%NOTFOUND`: indicates whether the most recent SQL statement affected or returned no rows.
- `SQL%ISOPEN`: indicates whether the implicit cursor is open; for the implicit `SQL` cursor, this attribute is always `FALSE` after the statement finishes.
- `SQL%ROWCOUNT`: the number of rows processed by the most recent SQL statement.

These attributes are especially useful after `INSERT`, `UPDATE`, `DELETE`, `MERGE`, and `SELECT INTO`. The most important rule is that they always reflect the most recent SQL statement. If you execute another SQL statement, the value you need may be overwritten. Therefore, read or save the attribute immediately after the statement you want to inspect.

## 1. What is an implicit cursor?

A cursor is a mechanism for PL/SQL to work with the results of a SQL query. There are two common ways to use cursors:

1. Implicit cursor: automatically managed by Oracle when running a SQL statement in PL/SQL.
2. Explicit cursor: declared by the developer, who then explicitly performs `OPEN`, `FETCH`, and `CLOSE`, or uses a cursor `FOR` loop.

Implicit cursor example:

~~~sql
BEGIN
    UPDATE employees
    SET salary = salary * 1.05
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE('Rows updated: ' || SQL%ROWCOUNT);
END;
/
~~~

Oracle automatically creates and manages the cursor for the `UPDATE` statement. There is no need to declare a cursor name or call `OPEN`/`CLOSE`.

### 1.1 Lifecycle of an implicit cursor

For an executed SQL statement:

1. Oracle opens the implicit cursor to execute the statement.
2. Oracle processes the statement and determines the result or number of affected rows.
3. The statement completes.
4. Oracle automatically closes the implicit cursor.
5. PL/SQL can read the `SQL%` attributes to retrieve the status and row count of the statement that just ran.

Overview diagram:

~~~text
PL/SQL executes SQL statement
            |
            v
Oracle opens implicit cursor
            |
            v
Execute / process rows
            |
            v
Statement completes
            |
            v
Oracle closes implicit cursor
            |
            v
Read SQL%FOUND / NOTFOUND / ISOPEN / ROWCOUNT
~~~

A developer cannot keep an implicit cursor open to `FETCH` row by row like an explicit cursor. If a query returns multiple rows, use a cursor `FOR` loop, explicit cursor, or `BULK COLLECT` depending on requirements.

### 1.2 SQL is the implicit cursor name

In PL/SQL, `SQL` is the implicit cursor name provided by Oracle. Do not declare a variable named `SQL` and do not write:

~~~sql
OPEN SQL;
FETCH SQL INTO ...;
CLOSE SQL;
~~~

That is not how implicit cursors are used. Only access the attributes:

~~~sql
SQL%FOUND
SQL%NOTFOUND
SQL%ISOPEN
SQL%ROWCOUNT
~~~

## 2. SQL%FOUND

`SQL%FOUND` returns a `BOOLEAN`:

- `TRUE` if the most recent SQL statement affected or returned at least one row.
- `FALSE` if the most recent SQL statement did not affect or return any rows.
- `NULL` if no SQL statement has been executed yet in the state scope being examined.

Example of an `UPDATE` with matching rows:

~~~sql
BEGIN
    UPDATE employees
    SET salary = salary + 100
    WHERE employee_id = 1001;

    IF SQL%FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Employee was updated.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('No employee matched.');
    END IF;
END;
/
~~~

If `EMPLOYEE_ID` 1001 exists and the `UPDATE` affects one row, `SQL%FOUND` is `TRUE`.

### 2.1 SQL%FOUND with an UPDATE that finds no rows

An `UPDATE` that matches no rows is still a successfully executed SQL statement. Oracle does not raise an exception just because the updated row count is 0.

~~~sql
BEGIN
    UPDATE employees
    SET salary = salary + 100
    WHERE employee_id = -999;

    IF SQL%FOUND THEN
        DBMS_OUTPUT.PUT_LINE('At least one row updated.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('No row updated.');
    END IF;
END;
/
~~~

In this example, `SQL%FOUND` is `FALSE` and `SQL%ROWCOUNT` is 0.

### 2.2 SQL%FOUND after INSERT

A successful `INSERT ... VALUES` affects one row:

~~~sql
BEGIN
    INSERT INTO departments(department_id, department_name)
    VALUES (900, 'Training');

    IF SQL%FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Insert affected a row.');
    END IF;
END;
/
~~~

If the `INSERT` succeeds, `SQL%FOUND` is `TRUE` and `SQL%ROWCOUNT` equals 1.

If `INSERT ... SELECT` inserts no rows because the source `SELECT` is empty, the `INSERT` completes without adding rows; in that case, `SQL%FOUND` is `FALSE` and `SQL%ROWCOUNT` equals 0.

### 2.3 SQL%FOUND after DELETE

~~~sql
BEGIN
    DELETE FROM employees
    WHERE department_id = -999;

    IF SQL%FOUND THEN
        DBMS_OUTPUT.PUT_LINE('At least one employee deleted.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('No employee matched the DELETE.');
    END IF;
END;
/
~~~

If no rows match, `DELETE` does not raise an error; `SQL%FOUND` is `FALSE`.

### 2.4 SQL%FOUND is a BOOLEAN, not a string

Do not compare against a string:

~~~sql
-- Incorrect:
IF SQL%FOUND = 'TRUE' THEN
    NULL;
END IF;
~~~

Use it directly in a PL/SQL condition:

~~~sql
IF SQL%FOUND THEN
    ...
END IF;
~~~

`SQL%FOUND` can be `NULL` if no SQL statement has been executed yet. In PL/SQL, `IF` only enters the `THEN` branch when the condition evaluates to `TRUE`; `FALSE` or `NULL` will not enter that branch.

## 3. SQL%NOTFOUND

`SQL%NOTFOUND` is the opposite attribute of `SQL%FOUND`:

- `TRUE` if the most recent SQL statement did not affect or return any rows.
- `FALSE` if the most recent SQL statement affected or returned at least one row.
- `NULL` if no SQL statement has been executed yet.

Example:

~~~sql
BEGIN
    DELETE FROM employees
    WHERE employee_id = 1001;

    IF SQL%NOTFOUND THEN
        DBMS_OUTPUT.PUT_LINE('Employee does not exist.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Employee deleted.');
    END IF;
END;
/
~~~

### 3.1 SQL%NOTFOUND does not mean the SQL statement failed

The attribute name can be misleading. `SQL%NOTFOUND = TRUE` only means no rows were affected or returned. It does not mean the statement encountered an error.

Example:

~~~sql
UPDATE employees
SET salary = salary + 500
WHERE employee_id = -1;
~~~

The statement succeeds with no exception, yet `SQL%NOTFOUND` is `TRUE`. If the `UPDATE` violates a `CHECK` constraint or triggers an error, Oracle raises an exception; control flow jumps to the exception handler instead of continuing to the normal `IF` statement.

### 3.2 Using NOTFOUND to detect a DELETE with no rows

~~~sql
DECLARE
    l_deleted PLS_INTEGER;
BEGIN
    DELETE FROM employees
    WHERE employee_id = 1001;

    IF SQL%NOTFOUND THEN
        DBMS_OUTPUT.PUT_LINE('Nothing was deleted.');
    ELSE
        l_deleted := SQL%ROWCOUNT;
        DBMS_OUTPUT.PUT_LINE('Deleted rows: ' || l_deleted);
    END IF;
END;
/
~~~

In this example, `SQL%ROWCOUNT` is read immediately after `DELETE` in the `ELSE` branch, before any other SQL statement runs.

### 3.3 Relationship between FOUND and NOTFOUND

Once the attributes have a `TRUE`/`FALSE` state:

| SQL%FOUND | SQL%NOTFOUND |
|---|---|
| TRUE | FALSE |
| FALSE | TRUE |

Before any SQL executes, both can be `NULL`. Therefore, do not assume in comparisons that they are always two defined opposite boolean values.

## 4. SQL%ISOPEN

`SQL%ISOPEN` indicates whether the implicit `SQL` cursor is currently open. For an implicit cursor, this attribute always returns `FALSE` when PL/SQL checks it after the statement finishes, because Oracle automatically closes the cursor after execution.

Example:

~~~sql
BEGIN
    UPDATE employees
    SET salary = salary + 100
    WHERE employee_id = 1001;

    IF SQL%ISOPEN THEN
        DBMS_OUTPUT.PUT_LINE('Implicit cursor is open.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Implicit cursor is closed.');
    END IF;
END;
/
~~~

The result enters the cursor-closed branch. This is normal behavior.

### 4.1 Do not use SQL%ISOPEN to check whether a SELECT returned data

A common misconception:

~~~sql
IF SQL%ISOPEN THEN
    DBMS_OUTPUT.PUT_LINE('Query returned rows.');
END IF;
~~~

The condition above does not check whether the query returned rows. The implicit cursor has already been closed by Oracle after the SQL statement completed.

To check whether DML affected rows, use `SQL%FOUND` or `SQL%ROWCOUNT`. For `SELECT INTO`, handle `NO_DATA_FOUND` and `TOO_MANY_ROWS`. For multi-row queries, use an appropriate cursor.

### 4.2 SQL%ISOPEN differs from cursor_name%ISOPEN

An explicit cursor has a lifecycle controlled by the program:

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id
        FROM employees;
BEGIN
    OPEN c_employees;

    IF c_employees%ISOPEN THEN
        DBMS_OUTPUT.PUT_LINE('Explicit cursor is open.');
    END IF;

    CLOSE c_employees;
END;
/
~~~

Here `c_employees%ISOPEN` can be `TRUE` between `OPEN` and `CLOSE`. This differs from `SQL%ISOPEN` on an implicit cursor.

## 5. SQL%ROWCOUNT

`SQL%ROWCOUNT` returns the number of rows processed by the most recent SQL statement. This is usually the most useful attribute when verifying DML results.

Example:

~~~sql
DECLARE
    l_rows_updated PLS_INTEGER;
BEGIN
    UPDATE employees
    SET salary = salary * 1.10
    WHERE department_id = 10;

    l_rows_updated := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE(
        'Updated rows: ' || l_rows_updated
    );
END;
/
~~~

If there are 25 employees in department 10, `SQL%ROWCOUNT` equals 25.

### 5.1 SQL%ROWCOUNT equal to 0 is not an exception

~~~sql
BEGIN
    UPDATE employees
    SET salary = salary + 100
    WHERE employee_id = -999;

    DBMS_OUTPUT.PUT_LINE(
        'Affected rows: ' || SQL%ROWCOUNT
    );
END;
/
~~~

If no employee matches, the statement still succeeds and prints 0.

If the business logic requires updating exactly one row:

~~~sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE employees
    SET salary = salary + 100
    WHERE employee_id = 1001;

    l_rows := SQL%ROWCOUNT;

    IF l_rows <> 1 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Expected exactly one employee row to be updated'
        );
    END IF;
END;
/
~~~

Note: this example only illustrates checking the row count. A real application must decide whether the transaction should be rolled back on business errors and who owns the `COMMIT` decision.

### 5.2 SQL%ROWCOUNT after INSERT

Single-row `INSERT`:

~~~sql
BEGIN
    INSERT INTO departments(department_id, department_name)
    VALUES (901, 'Operations');

    DBMS_OUTPUT.PUT_LINE(SQL%ROWCOUNT);
END;
/
~~~

The result is 1 if the `INSERT` succeeds.

Multi-row `INSERT` using `INSERT ... SELECT`:

~~~sql
BEGIN
    INSERT INTO employee_archive (
        employee_id,
        employee_name,
        department_id
    )
    SELECT employee_id,
           employee_name,
           department_id
    FROM employees
    WHERE status = 'INACTIVE';

    DBMS_OUTPUT.PUT_LINE(
        'Inserted rows: ' || SQL%ROWCOUNT
    );
END;
/
~~~

`SQL%ROWCOUNT` indicates how many rows were inserted by the statement. If the source `SELECT` returns no rows, the count is 0.

### 5.3 SQL%ROWCOUNT after DELETE

~~~sql
BEGIN
    DELETE FROM employee_archive
    WHERE archived_at < DATE '2020-01-01';

    DBMS_OUTPUT.PUT_LINE(
        'Deleted rows: ' || SQL%ROWCOUNT
    );
END;
/
~~~

The number of deleted rows is returned immediately after `DELETE`.

### 5.4 SQL%ROWCOUNT after MERGE

`MERGE` can `INSERT` or `UPDATE` rows depending on the match condition. `SQL%ROWCOUNT` reports the total number of rows affected by the `MERGE` statement, not the insert count or update count separately.

~~~sql
BEGIN
    MERGE INTO employee_summary target
    USING employee_stage source
       ON (target.employee_id = source.employee_id)
    WHEN MATCHED THEN
        UPDATE SET target.salary = source.salary
    WHEN NOT MATCHED THEN
        INSERT (employee_id, salary)
        VALUES (source.employee_id, source.salary);

    DBMS_OUTPUT.PUT_LINE(
        'Rows affected by MERGE: ' || SQL%ROWCOUNT
    );
END;
/
~~~

If you need separate `INSERT` and `UPDATE` counts, `SQL%ROWCOUNT` alone does not provide two separate numbers. Design an appropriate measurement strategy—such as a staging source with classification flags, auditing, or separate DML steps when reporting requires exact group counts.

### 5.5 SQL%ROWCOUNT after SELECT INTO

`SELECT ... INTO` is a single-row query. When the query returns exactly one row, the statement succeeds and `SQL%ROWCOUNT` is 1:

~~~sql
DECLARE
    l_name employees.employee_name%TYPE;
BEGIN
    SELECT employee_name
    INTO l_name
    FROM employees
    WHERE employee_id = 1001;

    DBMS_OUTPUT.PUT_LINE('Rows fetched: ' || SQL%ROWCOUNT);
END;
/
~~~

Do not use `SELECT INTO` like a multi-row cursor. If there are no rows, Oracle raises `NO_DATA_FOUND`; if there is more than one row, Oracle raises `TOO_MANY_ROWS`. Handle those exceptions rather than expecting execution to continue to an `IF` statement checking `SQL%NOTFOUND`.

### 5.6 SQL%ROWCOUNT after an aggregate SELECT

An aggregate without `GROUP BY` normally returns one row even when the source has no rows:

~~~sql
DECLARE
    l_count PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM employees
    WHERE department_id = -999;

    DBMS_OUTPUT.PUT_LINE('Count value: ' || l_count);
    DBMS_OUTPUT.PUT_LINE('Rows fetched: ' || SQL%ROWCOUNT);
END;
/
~~~

Here `COUNT(*)` returns the value 0, yet `SELECT INTO` still retrieves one result row. Thus `SQL%ROWCOUNT` is 1. Distinguish carefully:

- `SQL%ROWCOUNT`: number of result rows retrieved by `SELECT INTO`.
- `l_count`: value of `COUNT(*)` in the result row, which can be 0.

These two numbers answer two different questions.

### 5.7 SQL%ROWCOUNT and SELECT BULK COLLECT INTO

`SELECT BULK COLLECT INTO` fetches multiple rows into a collection and does not raise `NO_DATA_FOUND` simply because the result is empty:

~~~sql
DECLARE
    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    l_employee_ids t_employee_ids;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_employee_ids
    FROM employees
    WHERE department_id = -999;

    DBMS_OUTPUT.PUT_LINE(
        'Rows fetched: ' || SQL%ROWCOUNT
    );
    DBMS_OUTPUT.PUT_LINE(
        'Collection count: ' || l_employee_ids.COUNT
    );
END;
/
~~~

If there are no rows, the collection is empty and `SQL%ROWCOUNT` equals 0. This differs from `SELECT COUNT(*) INTO` a scalar variable, because `COUNT` still returns one result row.

## 6. SQL% attributes always reflect the most recent SQL statement

This is the most important rule when using implicit cursors.

~~~sql
BEGIN
    UPDATE employees
    SET salary = salary + 100
    WHERE department_id = 10;

    -- SQL%ROWCOUNT here is the UPDATE row count.
    DBMS_OUTPUT.PUT_LINE('Updated: ' || SQL%ROWCOUNT);

    DELETE FROM employee_archive
    WHERE department_id = 10;

    -- SQL%ROWCOUNT is now the DELETE row count,
    -- no longer the UPDATE row count.
    DBMS_OUTPUT.PUT_LINE('Deleted: ' || SQL%ROWCOUNT);
END;
/
~~~

If you need to use the `UPDATE` row count at the end of the block, save it right after `UPDATE`:

~~~sql
DECLARE
    l_updated_rows PLS_INTEGER;
    l_deleted_rows PLS_INTEGER;
BEGIN
    UPDATE employees
    SET salary = salary + 100
    WHERE department_id = 10;

    l_updated_rows := SQL%ROWCOUNT;

    DELETE FROM employee_archive
    WHERE department_id = 10;

    l_deleted_rows := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE('Updated=' || l_updated_rows);
    DBMS_OUTPUT.PUT_LINE('Deleted=' || l_deleted_rows);
END;
/
~~~

### 6.1 Read attributes before the next SQL statement

Avoid:

~~~sql
UPDATE employees
SET salary = salary + 100
WHERE department_id = 10;

SELECT COUNT(*)
INTO l_count
FROM employees;

-- SQL%ROWCOUNT here belongs to SELECT COUNT(*), no longer to UPDATE.
DBMS_OUTPUT.PUT_LINE(SQL%ROWCOUNT);
~~~

If you need the `UPDATE` row count, capture it right after `UPDATE`:

~~~sql
UPDATE employees
SET salary = salary + 100
WHERE department_id = 10;

l_updated_rows := SQL%ROWCOUNT;

SELECT COUNT(*)
INTO l_count
FROM employees;
~~~

### 6.2 Called procedures can also execute SQL

When a sub-procedure executes SQL, the implicit cursor state can change. If the caller needs to preserve the row count of a DML statement before calling a sub-procedure, save it into a local variable before the call.

~~~sql
UPDATE employees
SET salary = salary + 100
WHERE department_id = 10;

l_rows_updated := SQL%ROWCOUNT;

write_audit_log(...);

-- Use l_rows_updated; do not re-read SQL%ROWCOUNT
-- because the log procedure may have run other SQL.
~~~

This is why code should capture attributes right where the DML runs instead of reading them farther down.

## 7. Combining FOUND, NOTFOUND, and ROWCOUNT

The attributes can be used together:

~~~sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE employees
    SET salary = salary * 1.05
    WHERE department_id = 10;

    l_rows := SQL%ROWCOUNT;

    IF SQL%FOUND THEN
        DBMS_OUTPUT.PUT_LINE(
            'Updated ' || l_rows || ' employees.'
        );
    ELSIF SQL%NOTFOUND THEN
        DBMS_OUTPUT.PUT_LINE('No employees matched.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Cursor state is unknown.');
    END IF;
END;
/
~~~

In this example, `UPDATE` ran beforehand so the `FOUND`/`NOTFOUND` state is defined. The `ELSE` branch mainly illustrates the case where the boolean state is unknown; in this normal flow it is not taken.

For DML, checking `SQL%ROWCOUNT` is often sufficient:

~~~sql
IF SQL%ROWCOUNT = 0 THEN
    ...
ELSIF SQL%ROWCOUNT = 1 THEN
    ...
ELSE
    ...
END IF;
~~~

However, if you need to use the row count multiple times or after another SQL statement, assign it to a local variable.

## 8. Exception handling and implicit cursor attributes

If a SQL statement fails due to a constraint, conversion, trigger, or other runtime error, PL/SQL transfers to the exception handler. Do not rely on `SQL%FOUND`/`NOTFOUND`/`ROWCOUNT` to interpret a SQL statement that did not complete normally.

Duplicate-key `INSERT` example:

~~~sql
BEGIN
    INSERT INTO departments(department_id, department_name)
    VALUES (10, 'Duplicate');

    DBMS_OUTPUT.PUT_LINE('Inserted rows: ' || SQL%ROWCOUNT);
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        DBMS_OUTPUT.PUT_LINE('Department ID already exists.');
END;
/
~~~

If the `INSERT` encounters a unique violation, the `DBMS_OUTPUT` line after `INSERT` does not execute. The exception handler processes the error. If you need to log row counts before an error, save metrics from previously completed SQL statements into separate variables.

### 8.1 NO_DATA_FOUND is not the same as SQL%NOTFOUND after DML

`UPDATE` finding no rows:

~~~sql
UPDATE employees
SET salary = salary + 100
WHERE employee_id = -999;
~~~

Does not raise `NO_DATA_FOUND`; `SQL%ROWCOUNT` equals 0.

`SELECT INTO` finding no rows:

~~~sql
SELECT employee_name
INTO l_name
FROM employees
WHERE employee_id = -999;
~~~

Raises `NO_DATA_FOUND`. These are two distinct mechanisms:

| Operation | Zero rows |
|---|---|
| `UPDATE`/`DELETE` with no match | Succeeds, rowcount 0 |
| `INSERT ... SELECT` with empty source | Succeeds, rowcount 0 |
| `SELECT ... INTO` | `NO_DATA_FOUND` |
| `SELECT ... BULK COLLECT INTO` | Succeeds, empty collection |
| `SELECT COUNT(*) INTO` | Fetches one row with value 0 |

### 8.2 SELECT INTO handling pattern

~~~sql
DECLARE
    l_name employees.employee_name%TYPE;
BEGIN
    SELECT employee_name
    INTO l_name
    FROM employees
    WHERE employee_id = 1001;

    DBMS_OUTPUT.PUT_LINE(l_name);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Employee not found.');
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE('Query returned more than one employee.');
END;
/
~~~

If the business logic requires exactly one row, ensure the predicate uses a unique key or explicitly handle the two exceptions above.

## 9. Implicit cursors across different DML statements

### 9.1 Conditional UPDATE

~~~sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE products
    SET unit_price = unit_price * 1.03
    WHERE category_id = 5
      AND discontinued = 'N';

    l_rows := SQL%ROWCOUNT;

    IF l_rows = 0 THEN
        DBMS_OUTPUT.PUT_LINE('No active products in category.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Updated products: ' || l_rows);
    END IF;
END;
/
~~~

### 9.2 Batch DELETE

~~~sql
DECLARE
    l_deleted PLS_INTEGER;
BEGIN
    DELETE FROM audit_events
    WHERE created_at < ADD_MONTHS(SYSDATE, -24);

    l_deleted := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE('Deleted events: ' || l_deleted);
END;
/
~~~

In large data systems, deleting a huge number of rows can generate heavy undo/redo and impact indexes. If a table is time-partitioned, partition maintenance operations may be an alternative; that is a separate design and operational decision, not an effect of `SQL%ROWCOUNT`.

### 9.3 MERGE

~~~sql
DECLARE
    l_affected PLS_INTEGER;
BEGIN
    MERGE INTO product_price target
    USING product_price_stage source
       ON (target.product_id = source.product_id)
    WHEN MATCHED THEN
        UPDATE SET target.price = source.price
    WHEN NOT MATCHED THEN
        INSERT (product_id, price)
        VALUES (source.product_id, source.price);

    l_affected := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE(
        'MERGE affected rows: ' || l_affected
    );
END;
/
~~~

The rowcount is the total number of rows affected by `MERGE`. If separate insert/update statistics are required, design an additional classification mechanism.

### 9.4 DML with RETURNING INTO

`RETURNING INTO` brings modified column values back into PL/SQL variables:

~~~sql
DECLARE
    l_new_salary employees.salary%TYPE;
    l_rows       PLS_INTEGER;
BEGIN
    UPDATE employees
    SET salary = salary + 500
    WHERE employee_id = 1001
    RETURNING salary INTO l_new_salary;

    l_rows := SQL%ROWCOUNT;

    IF l_rows = 1 THEN
        DBMS_OUTPUT.PUT_LINE('New salary: ' || l_new_salary);
    ELSE
        DBMS_OUTPUT.PUT_LINE('No employee updated.');
    END IF;
END;
/
~~~

This example assumes `UPDATE` affects at most one row. With multiple rows, `RETURNING INTO` requires an appropriate collection/bulk binding; do not use a scalar variable for multi-row results.

## 10. FORALL and bulk cursor attributes

`FORALL` is a bulk binding mechanism to submit multiple DML executions from a collection, reducing round-trips between the PL/SQL engine and the SQL engine.

Example:

~~~sql
DECLARE
    TYPE t_id_list IS TABLE OF employees.employee_id%TYPE;
    l_ids t_id_list := t_id_list(1001, 1002, 1003);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employees
        SET salary = salary + 100
        WHERE employee_id = l_ids(i);

    DBMS_OUTPUT.PUT_LINE(
        'Total rows affected: ' || SQL%ROWCOUNT
    );
END;
/
~~~

After `FORALL`, `SQL%ROWCOUNT` reflects the total number of rows affected across all DML executions in the `FORALL` statement just run.

### 10.1 SQL%BULK_ROWCOUNT

If you need to know how many rows each execution inside `FORALL` affected, use `SQL%BULK_ROWCOUNT`:

~~~sql
DECLARE
    TYPE t_id_list IS TABLE OF employees.employee_id%TYPE;
    l_ids t_id_list := t_id_list(1001, 1002, 9999);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT
        UPDATE employees
        SET salary = salary + 100
        WHERE employee_id = l_ids(i);

    FOR i IN 1 .. l_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Input index ' || i ||
            ' affected ' || SQL%BULK_ROWCOUNT(i) || ' rows'
        );
    END LOOP;
END;
/
~~~

`SQL%BULK_ROWCOUNT(i)` reports the number of rows affected by the i-th DML execution. This provides finer-grained detail than the total `SQL%ROWCOUNT`.

### 10.2 SAVE EXCEPTIONS and SQL%BULK_EXCEPTIONS

`FORALL` can use `SAVE EXCEPTIONS` to continue processing the remaining DML iterations when some encounter errors. Afterward, `SQL%BULK_EXCEPTIONS` provides the list of errors:

~~~sql
DECLARE
    TYPE t_id_list IS TABLE OF employees.employee_id%TYPE;
    l_ids t_id_list := t_id_list(1001, 1002, 1003);

    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
        UPDATE employees
        SET salary = salary + 100
        WHERE employee_id = l_ids(i);

EXCEPTION
    WHEN e_bulk_errors THEN
        FOR j IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Failed input index: ' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_INDEX
            );
            DBMS_OUTPUT.PUT_LINE(
                'Oracle error code: ' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_CODE
            );
        END LOOP;
END;
/
~~~

`SQL%BULK_EXCEPTIONS` is a dedicated attribute of bulk DML, not one of the four `SQL%FOUND`/`NOTFOUND`/`ISOPEN`/`ROWCOUNT` attributes. Distinguish per-execution failures from the total number of successfully updated rows. `COMMIT`/`ROLLBACK` policy is still governed by transaction logic.

## 11. Comparing implicit cursors and explicit cursors

| Feature | Implicit cursor `SQL` | Explicit cursor |
|---|---|---|
| Declare cursor name | No | Yes |
| `OPEN` | Automatically managed by Oracle | Managed by developer or cursor `FOR` loop |
| `FETCH` row by row | Not directly | Yes |
| `CLOSE` | Automatically closed by Oracle after statement | Must be closed if manually opened |
| Attributes | `SQL%FOUND`, `SQL%NOTFOUND`, `SQL%ISOPEN`, `SQL%ROWCOUNT` | `cursor_name%FOUND`, `%NOTFOUND`, `%ISOPEN`, `%ROWCOUNT` |
| Suitable for | DML, `SELECT INTO`, single-row queries, bulk collect | Multi-row queries requiring sequential processing |

### 11.1 Explicit cursor template

~~~sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, employee_name
        FROM employees
        WHERE department_id = 10;

    l_employee_id   employees.employee_id%TYPE;
    l_employee_name employees.employee_name%TYPE;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees
        INTO l_employee_id, l_employee_name;

        EXIT WHEN c_employees%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            l_employee_id || ' - ' || l_employee_name
        );
    END LOOP;

    DBMS_OUTPUT.PUT_LINE(
        'Rows fetched: ' || c_employees%ROWCOUNT
    );

    CLOSE c_employees;
END;
/
~~~

Here you must use `c_employees%NOTFOUND` and `c_employees%ROWCOUNT`, not `SQL%NOTFOUND`, to control the `FETCH` loop. `SQL%` attributes reflect the most recent SQL statement, which could be overwritten by other SQL inside the loop or a called procedure.

### 11.2 Cursor FOR loop

If you only need to read and process each row, a cursor `FOR` loop handles `OPEN`, `FETCH`, and `CLOSE` automatically:

~~~sql
BEGIN
    FOR rec IN (
        SELECT employee_id, employee_name
        FROM employees
        WHERE department_id = 10
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            rec.employee_id || ' - ' || rec.employee_name
        );
    END LOOP;
END;
/
~~~

No manual cursor lifecycle management is required. If you need to count the rows processed in the loop, create a PL/SQL counter variable:

~~~sql
DECLARE
    l_count PLS_INTEGER := 0;
BEGIN
    FOR rec IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = 10
    ) LOOP
        l_count := l_count + 1;
    END LOOP;

    DBMS_OUTPUT.PUT_LINE('Processed rows: ' || l_count);
END;
/
~~~

## 12. Common points of confusion

### 12.1 SELECT INTO and SQL%NOTFOUND

Do not write:

~~~sql
SELECT employee_name
INTO l_name
FROM employees
WHERE employee_id = -999;

IF SQL%NOTFOUND THEN
    DBMS_OUTPUT.PUT_LINE('Not found');
END IF;
~~~

When there are no rows, `SELECT INTO` raises `NO_DATA_FOUND` and control never reaches `IF`. Catch the exception or use a query structured to return one row such as `COUNT(*)` if that is what needs to be measured.

### 12.2 COUNT(*) returns 0 but SQL%FOUND is still TRUE

~~~sql
SELECT COUNT(*)
INTO l_count
FROM employees
WHERE department_id = -999;
~~~

The aggregate query returns one row with the value 0. Therefore `SQL%FOUND` is `TRUE` and `SQL%ROWCOUNT` is 1. The variable `l_count` holds the number of rows matching the predicate.

### 12.3 SQL%ISOPEN is always FALSE

Do not use `SQL%ISOPEN` to determine whether a `SELECT` returned rows. Use `FOUND`/`NOTFOUND` for appropriate DML, exceptions for `SELECT INTO`, or explicit cursor attributes for `FETCH`.

### 12.4 A subsequent SQL statement overwrites the state

~~~sql
UPDATE employees
SET salary = salary + 100
WHERE department_id = 10;

SELECT COUNT(*)
INTO l_count
FROM departments;

-- SQL%ROWCOUNT at this point is 1 from SELECT COUNT(*),
-- not the number of updated employees.
~~~

Save the attribute into a variable before the next SQL statement.

### 12.5 Zero affected rows vs. constraint errors

An `UPDATE` affecting 0 rows is not an error. An `UPDATE` violating a constraint is a SQL error and jumps to the exception handler. The application must separately decide whether a rowcount of 0 is a business error or a valid state.

## 13. Practical pattern: updating status and checking row count

A business operation often needs to know whether a record existed and transitioned state:

~~~sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE orders
    SET status = 'APPROVED',
        approved_at = SYSTIMESTAMP
    WHERE order_id = 5001
      AND status = 'PENDING';

    l_rows := SQL%ROWCOUNT;

    IF l_rows = 1 THEN
        DBMS_OUTPUT.PUT_LINE('Order approved.');
    ELSIF l_rows = 0 THEN
        DBMS_OUTPUT.PUT_LINE(
            'Order not found or not in PENDING state.'
        );
    ELSE
        RAISE_APPLICATION_ERROR(
            -20002,
            'Unexpected number of orders updated.'
        );
    END IF;
END;
/
~~~

The `STATUS = 'PENDING'` condition checks and transitions the state within the same DML statement. If another session already changed the status earlier, the `UPDATE` affects 0 rows. This is usually a clearer optimistic state-transition check than running a `SELECT` for status followed by an unconditional `UPDATE`.

If you need to distinguish "does not exist" from "already processed," an additional query or result model is needed; a rowcount of 0 alone does not tell you which of those two causes occurred.

## 14. Practical scenario: checking availability before logging

~~~sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE inventory
    SET quantity = quantity - 1
    WHERE product_id = 100
      AND quantity > 0;

    l_rows := SQL%ROWCOUNT;

    IF l_rows = 1 THEN
        INSERT INTO inventory_log(
            product_id, action_name, action_time
        )
        VALUES (
            100, 'DECREASE', SYSTIMESTAMP
        );
    ELSIF l_rows = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20010,
            'Product is missing or inventory is insufficient.'
        );
    END IF;
END;
/
~~~

The `UPDATE` and log `INSERT` belong to the same session transaction. If the log `INSERT` fails and the exception is unhandled in the block, the application must apply an appropriate rollback policy. `SQL%ROWCOUNT` must be saved immediately after `UPDATE`, because after `INSERT` it reflects the inserted row count rather than the updated row count.

## 15. Performance and how to use cursor attributes

The `SQL%` attributes have very low usage cost; they simply read status metadata of the most recent SQL statement. However, how you structure the program still impacts performance:

- Do not run `SELECT COUNT(*)` solely to check whether an `UPDATE` affected rows; use `SQL%ROWCOUNT`.
- Do not `SELECT` first and then `UPDATE` just to confirm a row exists when a conditional DML statement can safely handle it.
- Use `BULK COLLECT`/`FORALL` for multi-row workloads when appropriate instead of row-by-row SQL loops.
- Save the rowcount into a variable when needed after another SQL statement.
- Use a cursor `FOR` loop or explicit cursor when processing multiple rows.

Example without an extra query:

~~~sql
-- No need to run SELECT COUNT(*) beforehand to measure updated rows.
UPDATE employees
SET salary = salary + 100
WHERE department_id = 10;

l_rows := SQL%ROWCOUNT;
~~~

A separate `SELECT COUNT(*)` can incur extra I/O and can also observe a different state if data changes concurrently between the `SELECT` and the `UPDATE`.

## 16. Summary table of the four attributes

| Attribute | Return type | Meaning | Usage example |
|---|---|---|---|
| `SQL%FOUND` | `BOOLEAN` | `TRUE` if most recent SQL affected/returned at least one row | Check if `UPDATE` matched a row |
| `SQL%NOTFOUND` | `BOOLEAN` | `TRUE` if most recent SQL affected/returned no rows | Detect a `DELETE` with no match |
| `SQL%ISOPEN` | `BOOLEAN` | `FALSE` for implicit `SQL` cursor after statement completion | Rarely used to check results |
| `SQL%ROWCOUNT` | Integer | Number of rows processed by the most recent SQL | Count `INSERT`/`UPDATE`/`DELETE`/`MERGE` |

State before any SQL executes:

| Attribute | State |
|---|---|
| `SQL%FOUND` | `NULL` |
| `SQL%NOTFOUND` | `NULL` |
| `SQL%ISOPEN` | `FALSE` |
| `SQL%ROWCOUNT` | `NULL` |

After a DML statement completes normally:

| DML result | SQL%FOUND | SQL%NOTFOUND | SQL%ROWCOUNT |
|---|---|---|---|
| Affected 0 rows | `FALSE` | `TRUE` | 0 |
| Affected 1 row | `TRUE` | `FALSE` | 1 |
| Affected multiple rows | `TRUE` | `FALSE` | Number of affected rows |

`SQL%ISOPEN` remains `FALSE` because the implicit cursor has already closed automatically.

## 17. Common errors

| Symptom | Cause | Resolution |
|---|---|---|
| `SQL%ROWCOUNT` returns 1 even though prior `UPDATE` modified many rows | Another `SELECT` or DML ran after `UPDATE` | Save rowcount immediately after `UPDATE` |
| `IF SQL%NOTFOUND` does not run when `SELECT INTO` finds no rows | `SELECT INTO` raises `NO_DATA_FOUND` before reaching `IF` | Catch `NO_DATA_FOUND` |
| `SQL%ISOPEN` is always `FALSE` | Implicit cursor auto-closes after statement | Use `SQL%FOUND`/`ROWCOUNT` or an explicit cursor |
| `UPDATE` finds no rows yet raises no exception | 0-row DML is syntactically and executionally valid | Check `SQL%ROWCOUNT` and apply business rules |
| `COUNT(*)` is 0 yet `SQL%FOUND` is `TRUE` | `SELECT COUNT(*)` still returns one result row | Distinguish `COUNT` value from `SELECT INTO` row count |
| Lost DML row count after calling a procedure | Sub-procedure executed other SQL | Save `SQL%ROWCOUNT` before the call |
| Using `SQL%NOTFOUND` in an explicit cursor loop | Confusing implicit cursor with named cursor | Use `cursor_name%NOTFOUND` |
| `SQL%ROWCOUNT` does not separate `INSERT` and `UPDATE` in `MERGE` | `MERGE` returns total affected rows | Design separate measurement if breakdown is needed |
| Using a scalar variable for multi-row `RETURNING` | Result can contain multiple rows | Use an appropriate collection/bulk `RETURNING` |

## 18. Self-check lab exercises

The exercises assume a test schema with `EMPLOYEES`, `DEPARTMENTS`, `ORDERS`, and `INVENTORY` tables. Adjust column names to match your actual schema if needed.

### Exercise 1 — FOUND after UPDATE

`UPDATE` an existing `EMPLOYEE_ID`. Print `SQL%FOUND`, `SQL%NOTFOUND`, and `SQL%ROWCOUNT`. Repeat with a non-existent ID and compare.

### Exercise 2 — Non-matching DELETE

`DELETE` by a non-existent ID. Explain why the statement does not raise `NO_DATA_FOUND` while `SQL%NOTFOUND` is `TRUE`.

### Exercise 3 — ISOPEN

Run an `UPDATE` and check `SQL%ISOPEN`. Explain why the result is always `FALSE` after the statement finishes.

### Exercise 4 — Overwritten attribute

`UPDATE` multiple rows, then `SELECT COUNT(*) INTO` a variable, then print `SQL%ROWCOUNT`. Try saving the rowcount into a variable right after `UPDATE` and compare.

### Exercise 5 — SELECT INTO

Write `SELECT INTO` for an ID with one row, a non-existent ID, and a predicate returning multiple rows. Handle `NO_DATA_FOUND` and `TOO_MANY_ROWS`.

### Exercise 6 — Aggregate

`SELECT COUNT(*) INTO` a variable with a predicate matching no rows. Print the `COUNT` variable value and `SQL%ROWCOUNT`. Explain why the two results are 0 and 1.

### Exercise 7 — INSERT SELECT

Run `INSERT INTO ... SELECT` with a multi-row source and an empty source. Compare `SQL%ROWCOUNT`.

### Exercise 8 — MERGE

Run `MERGE` with both matching and non-matching rows. Record the total `SQL%ROWCOUNT`. Propose a way to track insert and update counts separately.

### Exercise 9 — FORALL

Use a collection of IDs to `UPDATE` with `FORALL`. Print `SQL%ROWCOUNT` and each `SQL%BULK_ROWCOUNT(i)`. Explain the difference between the total and per-execution counts.

### Exercise 10 — Explicit cursor

Declare a cursor, `OPEN`, `FETCH`, and check `cursor_name%NOTFOUND` and `cursor_name%ROWCOUNT`. Compare with `SQL%` attributes.

### Exercise 11 — State transition

`UPDATE` an order from `PENDING` to `APPROVED` with a status condition. Use `SQL%ROWCOUNT` to detect when the update request is no longer valid.

### Exercise 12 — Saving rowcount before a procedure call

`UPDATE` multiple rows, save `SQL%ROWCOUNT`, call a sub-procedure containing `SELECT`/`INSERT`, then print the saved variable. Compare with reading `SQL%ROWCOUNT` after the procedure.

## 19. Takeaways

- The implicit cursor `SQL` is automatically opened and closed by Oracle for SQL statements in PL/SQL.
- Do not declare, `OPEN`, `FETCH`, or `CLOSE` the implicit `SQL` cursor.
- `SQL%FOUND` is `TRUE` when the most recent SQL statement affected/returned at least one row.
- `SQL%NOTFOUND` is `TRUE` when the most recent SQL statement affected/returned no rows.
- `SQL%ISOPEN` is always `FALSE` after an implicit statement completes.
- `SQL%ROWCOUNT` reports the number of rows processed by the most recent SQL statement.
- Before any SQL statement executes, `FOUND`, `NOTFOUND`, and `ROWCOUNT` can be `NULL`.
- `UPDATE`/`DELETE` matching no rows normally do not raise an exception; rowcount is 0.
- `SELECT INTO` with no rows raises `NO_DATA_FOUND`; multiple rows raises `TOO_MANY_ROWS`.
- `SELECT COUNT(*) INTO` still returns one row with value 0 when no records match.
- `SELECT BULK COLLECT INTO` can return an empty collection without raising `NO_DATA_FOUND`.
- `SQL%` attributes always belong to the most recent SQL statement; save them into variables before running the next SQL.
- For explicit cursors, use `cursor_name%FOUND`/`NOTFOUND`/`ISOPEN`/`ROWCOUNT`.
- For `FORALL`, use `SQL%BULK_ROWCOUNT` and `SQL%BULK_EXCEPTIONS` when per-DML-execution details are needed.

Implicit cursor attributes provide a concise way for PL/SQL to know what the most recent SQL statement did. Use `FOUND`/`NOTFOUND` to check whether rows were affected, `ROWCOUNT` to know how many, and remember `ISOPEN` is always `FALSE` for implicit cursors. Read attributes immediately after the statement being measured, distinguish zero-row DML from `SELECT INTO` exceptions, and switch to explicit cursors when you need control over reading multiple rows.
