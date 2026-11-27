# DML in PL/SQL and Reading SQL%ROWCOUNT

PL/SQL allows SQL statements to be placed directly inside a block, procedure, function, trigger, or package. When a DML statement executes, Oracle modifies data within the current transaction and exposes implicit SQL cursor attributes so the program can tell how many rows the statement just affected. The most commonly used attribute is `SQL%ROWCOUNT`.

`SQL%ROWCOUNT` returns the number of rows affected by the most recently executed SQL statement in the session. For INSERT, UPDATE, DELETE, and MERGE, this value helps verify whether an operation affected any data, log the number of processed rows, distinguish the case where no rows were found, and control business logic.

An important point is that `SQL%ROWCOUNT` changes after every SQL statement. If you run a `SELECT`, call another procedure that executes SQL, or insert a log record after the main DML before reading the attribute, the value may no longer reflect the row count of the original DML. Always capture the value into a PL/SQL variable immediately before executing the next SQL statement.

After this lesson, you will be able to:

- Execute INSERT, UPDATE, DELETE, and MERGE in PL/SQL.
- Read `SQL%ROWCOUNT` immediately after DML and understand the meaning of the returned row count.
- Distinguish `SQL%ROWCOUNT` from `SQL%FOUND`, `SQL%NOTFOUND`, and `SQL%ISOPEN`.
- Handle the case where DML affects 0 rows without confusing it with an exception.
- Save the row count before running other SQL or calling another procedure.
- Return the affected row count from a procedure via an OUT parameter.
- Use `RETURNING INTO` to retrieve column values of rows affected by DML.
- Use dynamic SQL and `FORALL`, and understand `SQL%BULK_ROWCOUNT` and `SAVE EXCEPTIONS`.
- Distinguish the number of affected rows from a committed transaction.
- Write blocks with clear checks, logging, and exception handling.

> The examples use `LAB_` tables for practice in your own schema. Issuing `COMMIT`/`ROLLBACK` is an application transaction decision; it does not happen automatically simply because a PL/SQL block finishes.

## 1. What is DML in PL/SQL?

DML (Data Manipulation Language) is the group of statements that manipulate data in tables or views. Common statements include:

| Statement | Purpose |
| --- | --- |
| INSERT | Insert new rows |
| UPDATE | Modify existing rows |
| DELETE | Delete rows matching a condition |
| MERGE | Combine INSERT and UPDATE based on a matching condition |

PL/SQL allows writing DML directly inside the executable section of a block:

```sql
BEGIN
    UPDATE employees
    SET salary = salary * 1.05
    WHERE department_id = 50;
END;
/
```

The `UPDATE` statement above runs like a normal SQL statement. PL/SQL simply adds the ability to use variables, conditions, loops, exception handlers, and cursor attributes to control program flow.

### 1.1. PL/SQL block structure

A block has the following structure:

```sql
DECLARE
    -- Declare variables, constants, cursors, exceptions
BEGIN
    -- Executable statements: DML, SELECT INTO, procedure calls...
EXCEPTION
    -- Handle exceptions if any
END;
/
```

`DECLARE` and `EXCEPTION` are optional; `BEGIN` and `END` are mandatory. DML statements are placed in the `BEGIN...END` section, not in the `DECLARE` section.

### 1.2. DML in a block does not auto-commit

Ending a PL/SQL block does not mean committing the transaction:

```sql
BEGIN
    UPDATE lab_accounts
    SET balance = balance - 100
    WHERE account_id = 10;
END;
/
```

Without a `COMMIT`, the change remains part of the session's transaction. The client can commit or roll back afterward; another block in the same session can also continue the transaction. `SQL%ROWCOUNT` only reports the number of rows affected by the SQL statement, not whether the transaction has been committed or whether the data is visible to other sessions.

### 1.3. DML affecting 0 rows is not a syntax error

An UPDATE or DELETE can run successfully without finding any rows matching the WHERE clause:

```sql
BEGIN
    UPDATE lab_employees
    SET status = 'INACTIVE'
    WHERE employee_id = -1;

    DBMS_OUTPUT.PUT_LINE('Rows affected = ' || SQL%ROWCOUNT);
END;
/
```

If there is no `EMPLOYEE_ID = -1`, the UPDATE affects 0 rows. It does not automatically raise `NO_DATA_FOUND`. `SQL%ROWCOUNT` will be 0.

This differs from `SELECT ... INTO`: `SELECT INTO` is designed to fetch exactly one row; if there are no rows, PL/SQL raises `NO_DATA_FOUND`.

## 2. Implicit SQL cursor and SQL% attributes

When PL/SQL executes a SQL statement without using a programmer-declared explicit cursor, Oracle manages an implicit cursor named `SQL`. You can read this cursor's attributes using the `SQL%...` syntax.

### 2.1. SQL%ROWCOUNT

`SQL%ROWCOUNT` returns the number of rows processed by the most recent SQL statement. For DML, this is the number of rows inserted, updated, deleted, or affected by `MERGE`.

Example:

```sql
BEGIN
    UPDATE lab_employees
    SET salary = salary + 500
    WHERE department_id = 20;

    DBMS_OUTPUT.PUT_LINE(
        'Updated rows: ' || SQL%ROWCOUNT
    );
END;
/
```

If 7 rows match the condition, the result is 7. If no rows match, the result is 0.

### 2.2. SQL%FOUND

`SQL%FOUND` is TRUE if the most recent SQL statement affected or returned at least one row; FALSE if there were no rows. Before the first SQL statement is executed in the relevant session/context, the attribute may be NULL.

With DML:

```sql
BEGIN
    DELETE FROM lab_sessions
    WHERE expires_at < SYSTIMESTAMP;

    IF SQL%FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Expired sessions were deleted.');
    ELSE
        DBMS_OUTPUT.PUT_LINE('No expired sessions found.');
    END IF;
END;
/
```

### 2.3. SQL%NOTFOUND

`SQL%NOTFOUND` is TRUE if the most recent SQL statement did not affect or return any rows. With DML, it can be used to check whether the statement just executed affected zero rows:

```sql
BEGIN
    UPDATE lab_orders
    SET status = 'CLOSED'
    WHERE order_id = 900001;

    IF SQL%NOTFOUND THEN
        DBMS_OUTPUT.PUT_LINE('Order does not exist or does not match the condition.');
    END IF;
END;
/
```

In practice, `SQL%ROWCOUNT = 0` is often easier to read and more convenient for logging when a specific count is needed.

### 2.4. SQL%ISOPEN

`SQL%ISOPEN` always returns FALSE because Oracle automatically closes the implicit cursor after executing the SQL statement. There is no need to `CLOSE` an implicit SQL cursor:

```sql
BEGIN
    UPDATE lab_employees
    SET status = 'ACTIVE'
    WHERE employee_id = 101;

    DBMS_OUTPUT.PUT_LINE(
        'Implicit SQL cursor open? ' ||
        CASE WHEN SQL%ISOPEN THEN 'YES' ELSE 'NO' END
    );
END;
/
```

If you need manual control over OPEN, FETCH, and CLOSE, use an explicit cursor or cursor variable; in that case, read `cursor_name%ROWCOUNT`, `cursor_name%FOUND`, `cursor_name%NOTFOUND`, and `cursor_name%ISOPEN`.

### 2.5. Summary table

| Attribute | Meaning | Common usage |
| --- | --- | --- |
| SQL%ROWCOUNT | Row count of the most recent SQL statement | Count rows affected by DML |
| SQL%FOUND | At least one row was affected/returned | Check if there is a result |
| SQL%NOTFOUND | No rows were affected/returned | Check if there is no result |
| SQL%ISOPEN | Whether the implicit cursor is currently open | Always FALSE |

The `SQL%` attributes always refer to the implicit `SQL` cursor, not an explicit cursor that you declared yourself.

## 3. Reading SQL%ROWCOUNT after INSERT

### 3.1. Single-row INSERT

```sql
BEGIN
    INSERT INTO lab_departments (
        department_id,
        department_name,
        created_at
    )
    VALUES (
        90,
        'Data Platform',
        SYSTIMESTAMP
    );

    DBMS_OUTPUT.PUT_LINE(
        'Inserted rows = ' || SQL%ROWCOUNT
    );
END;
/
```

A successful single-row INSERT typically sets `SQL%ROWCOUNT` to 1.

### 3.2. Multi-row INSERT using INSERT ... SELECT

```sql
BEGIN
    INSERT INTO lab_employee_archive (
        employee_id,
        department_id,
        archived_at
    )
    SELECT
        employee_id,
        department_id,
        SYSTIMESTAMP
    FROM lab_employees
    WHERE status = 'INACTIVE';

    DBMS_OUTPUT.PUT_LINE(
        'Archived rows = ' || SQL%ROWCOUNT
    );
END;
/
```

`SQL%ROWCOUNT` is the total number of rows inserted by the statement. If the source SELECT returns no rows, `INSERT ... SELECT` still succeeds and the row count is 0.

### 3.3. INSERT ... SELECT is not the same as SELECT INTO

The two constructs have different semantics:

```sql
-- INSERT ... SELECT: can insert 0, 1, or many rows.
INSERT INTO lab_archive (employee_id)
SELECT employee_id
FROM lab_employees
WHERE department_id = -1;

-- SELECT INTO: requires exactly one row.
SELECT employee_id
INTO l_employee_id
FROM lab_employees
WHERE employee_id = -1;
```

`INSERT ... SELECT` with an empty source produces a row count of 0. `SELECT INTO` with an empty source raises `NO_DATA_FOUND`; with more than one row, it raises `TOO_MANY_ROWS`.

### 3.4. INSERT and duplicate keys

If an INSERT violates a PRIMARY KEY/UNIQUE constraint, Oracle raises an exception (typically `ORA-00001`). When a statement fails, do not use `SQL%ROWCOUNT` to assume a subset of rows was inserted. With a standard INSERT statement, a constraint error causes the statement to fail; handle the error according to exception and transaction semantics.

Do not catch all exceptions and log the row count as if the INSERT succeeded. Distinguish expected duplicate key errors from connection, NOT NULL, CHECK, foreign key, or other errors.

## 4. Reading SQL%ROWCOUNT after UPDATE

### 4.1. Multi-row UPDATE

```sql
DECLARE
    l_rows_updated PLS_INTEGER;
BEGIN
    UPDATE lab_employees
    SET salary = salary * 1.10
    WHERE department_id = 30;

    l_rows_updated := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE(
        'Rows updated = ' || l_rows_updated
    );
END;
/
```

The variable `l_rows_updated` stores the row count immediately after the UPDATE. If the program later runs a SELECT or an audit INSERT, `SQL%ROWCOUNT` will change; the local variable preserves the captured value.

### 4.2. UPDATE that does not change values

If an UPDATE matches a row and assigns a value equal to its current value, `SQL%ROWCOUNT` still counts the row affected by the statement. It does not count only rows whose values actually changed.

Example:

```sql
UPDATE lab_employees
SET status = 'ACTIVE'
WHERE employee_id = 101;
```

If `EMPLOYEE_ID = 101` exists and the statement updates that row, the row count is 1 even if `STATUS` was already `ACTIVE`. If you only want to count rows whose values differed prior to the update, include the inequality condition in the WHERE clause and handle NULL properly:

```sql
UPDATE lab_employees
SET status = 'ACTIVE'
WHERE employee_id = 101
  AND (status <> 'ACTIVE' OR status IS NULL);
```

For multiple nullable columns, express an appropriate null-safe comparison. Oracle's `DECODE` treats two NULLs as equal; you can use that expression when appropriate:

```sql
UPDATE lab_employees
SET status = 'ACTIVE'
WHERE employee_id = 101
  AND DECODE(status, 'ACTIVE', 0, 1) = 1;
```

### 4.3. UPDATE affecting 0 rows

```sql
BEGIN
    UPDATE lab_employees
    SET status = 'INACTIVE'
    WHERE employee_id = -1;

    IF SQL%ROWCOUNT = 0 THEN
        DBMS_OUTPUT.PUT_LINE('No rows were updated.');
    END IF;
END;
/
```

No exception is automatically raised just because an UPDATE affects 0 rows. If the business logic requires that exactly one row must be updated, check the row count explicitly and raise an exception yourself:

```sql
DECLARE
    e_employee_not_updated EXCEPTION;
    l_rows PLS_INTEGER;
BEGIN
    UPDATE lab_employees
    SET status = 'INACTIVE'
    WHERE employee_id = 101;

    l_rows := SQL%ROWCOUNT;

    IF l_rows <> 1 THEN
        RAISE e_employee_not_updated;
    END IF;
EXCEPTION
    WHEN e_employee_not_updated THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Expected exactly one employee row to be updated.'
        );
END;
/
```

This is a row count check, not a check that the transaction has been committed. The caller still decides whether to commit or roll back based on business boundaries.

## 5. Reading SQL%ROWCOUNT after DELETE

### 5.1. Multi-row DELETE

```sql
DECLARE
    l_deleted_rows PLS_INTEGER;
BEGIN
    DELETE FROM lab_sessions
    WHERE expires_at < SYSTIMESTAMP;

    l_deleted_rows := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE(
        'Deleted rows = ' || l_deleted_rows
    );
END;
/
```

`SQL%ROWCOUNT` returns the total number of rows deleted by the DELETE. If there are no expired sessions, the value is 0.

### 5.2. Conditional DELETE and checking for exactly one row

If the business rule requires deleting exactly one order:

```sql
DECLARE
    l_deleted_rows PLS_INTEGER;
BEGIN
    DELETE FROM lab_orders
    WHERE order_id = 5001
      AND status = 'CANCELLED';

    l_deleted_rows := SQL%ROWCOUNT;

    IF l_deleted_rows = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20011,
            'Order was not found or is not cancellable.'
        );
    ELSIF l_deleted_rows > 1 THEN
        RAISE_APPLICATION_ERROR(
            -20012,
            'Unexpectedly deleted more than one order.'
        );
    END IF;
END;
/
```

If `ORDER_ID` is a primary key, a count greater than 1 cannot theoretically occur. The check can still help catch an incorrect predicate or faulty schema assumption when operating on a table without a unique key.

### 5.3. DELETE and foreign keys

If a deleted row is referenced by a foreign key, `DELETE` can fail with a constraint error (for example `ORA-02292`) unless the relationship is configured with `ON DELETE CASCADE` or the child data has already been handled. When a statement fails due to a constraint, execution enters the exception handler; do not treat `SQL%ROWCOUNT` as the count of successfully deleted rows.

### 5.4. DELETE is not like TRUNCATE

`DELETE` is DML; it can filter rows with `WHERE`, generates undo within the transaction, and can be rolled back before commit. `TRUNCATE` is DDL; it empties the specified segment/extent, performs an implicit commit, and cannot use `SQL%ROWCOUNT` as an equivalent DML counter. If you need to know how many rows were deleted by `DELETE`, capture `SQL%ROWCOUNT` immediately after the `DELETE` statement.

## 6. Reading SQL%ROWCOUNT after MERGE

### 6.1. MERGE is an upsert

`MERGE` compares source rows against the target table using the `ON` condition:

- `WHEN MATCHED`: executes `UPDATE` according to the declared branch.
- `WHEN NOT MATCHED`: executes `INSERT` according to the declared branch.

Example:

```sql
DECLARE
    l_rows_affected PLS_INTEGER;
BEGIN
    MERGE INTO lab_products t
    USING (
        SELECT
            101 AS product_id,
            'Keyboard' AS product_name,
            850000 AS unit_price
        FROM dual
    ) s
    ON (t.product_id = s.product_id)
    WHEN MATCHED THEN
        UPDATE SET
            t.product_name = s.product_name,
            t.unit_price = s.unit_price
    WHEN NOT MATCHED THEN
        INSERT (product_id, product_name, unit_price)
        VALUES (s.product_id, s.product_name, s.unit_price);

    l_rows_affected := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE(
        'MERGE rows affected = ' || l_rows_affected
    );
END;
/
```

If a source row matches a target row, `MERGE` can update one row and the row count is 1. If it does not match, `MERGE` inserts one row and the row count is also 1. If the source is empty or no rows are processed, the row count can be 0.

### 6.2. SQL%ROWCOUNT does not distinguish INSERT from UPDATE

For a `MERGE` with both branches, `SQL%ROWCOUNT` is the total number of rows affected by the statement. It does not separately report how many rows were inserted versus updated.

For example, suppose the source has 10 rows: 6 rows match the target and are updated, while 4 rows do not match and are inserted. The total row count is 10. If the application needs the two separate counts, you must design a separate measurement mechanism—for example, classifying the source before `MERGE` under an appropriate snapshot, recording audit/action details in a carefully designed process, or splitting the operations when business rules allow. Do not infer the INSERT count from `SQL%ROWCOUNT`.

### 6.3. MERGE does not necessarily update every MATCHED row

`MERGE` can include a `WHERE` clause in the `UPDATE` branch:

```sql
MERGE INTO lab_products t
USING (
    SELECT
        :product_id AS product_id,
        :unit_price AS unit_price
    FROM dual
) s
ON (t.product_id = s.product_id)
WHEN MATCHED THEN
    UPDATE SET t.unit_price = s.unit_price
    WHERE t.unit_price <> s.unit_price
WHEN NOT MATCHED THEN
    INSERT (product_id, unit_price)
    VALUES (s.product_id, s.unit_price);
```

If the target already has the product with the same price as the source, the `UPDATE` condition is not met, so that row is not updated. The row count does not count this row. If `UNIT_PRICE` can be NULL, the inequality condition should be replaced with a null-safe expression so transitions from NULL to non-NULL or vice versa are not missed.

### 6.4. MERGE source must follow a one-row-per-target-key rule

If multiple source rows match the same target row, `MERGE` can fail with `ORA-30926` (unable to get a stable set of rows). If multiple source rows fail to match the same key, a duplicate key error can occur during insert. Normalize/deduplicate the source before `MERGE`.

### 6.5. MERGE and the DELETE branch

Oracle allows `MERGE` to include a `DELETE WHERE` clause inside the `UPDATE` branch in supported versions/syntax. `SQL%ROWCOUNT` is still the total number of rows affected by the `MERGE` statement; do not use it to distinguish how many rows were updated versus deleted. Check the specific syntax and `DELETE WHERE` semantics in the Oracle SQL Language Reference for your release.

## 7. SQL%ROWCOUNT changes after every SQL statement

This is the most important rule when using this attribute: `SQL%ROWCOUNT` describes the most recent SQL statement, not a history of an earlier DML statement.

### 7.1. Example of a wrong read caused by running SELECT first

```sql
BEGIN
    UPDATE lab_employees
    SET status = 'INACTIVE'
    WHERE department_id = 40;

    SELECT COUNT(*)
    INTO l_total
    FROM lab_employees;

    DBMS_OUTPUT.PUT_LINE(
        'Updated rows = ' || SQL%ROWCOUNT
    );
END;
/
```

After `SELECT INTO` succeeds, `SQL%ROWCOUNT` reflects the `SELECT` that just ran (`SELECT INTO` returns one row into the variable), no longer the `UPDATE` row count. To avoid this bug, save the row count immediately after `UPDATE`:

```sql
DECLARE
    l_updated_rows PLS_INTEGER;
    l_total PLS_INTEGER;
BEGIN
    UPDATE lab_employees
    SET status = 'INACTIVE'
    WHERE department_id = 40;

    l_updated_rows := SQL%ROWCOUNT;

    SELECT COUNT(*)
    INTO l_total
    FROM lab_employees;

    DBMS_OUTPUT.PUT_LINE(
        'Updated rows = ' || l_updated_rows
    );
    DBMS_OUTPUT.PUT_LINE(
        'Total rows = ' || l_total
    );
END;
/
```

### 7.2. Logging statements can overwrite SQL%ROWCOUNT

The following snippet is error-prone:

```sql
UPDATE lab_orders
SET status = 'CLOSED'
WHERE order_date < DATE '2025-01-01';

INSERT INTO lab_audit_log (
    event_name,
    affected_rows,
    created_at
)
VALUES (
    'CLOSE_OLD_ORDERS',
    SQL%ROWCOUNT,
    SYSTIMESTAMP
);
```

Inside `VALUES`, `SQL%ROWCOUNT` is evaluated before the log `INSERT` executes, so it can record the `UPDATE` row count. However, after the log `INSERT`, `SQL%ROWCOUNT` reflects the log `INSERT` (typically 1). If you want to print or reuse the `UPDATE` row count, you must save it into a variable first:

```sql
DECLARE
    l_updated_rows PLS_INTEGER;
BEGIN
    UPDATE lab_orders
    SET status = 'CLOSED'
    WHERE order_date < DATE '2025-01-01';

    l_updated_rows := SQL%ROWCOUNT;

    INSERT INTO lab_audit_log (
        event_name, affected_rows, created_at
    )
    VALUES (
        'CLOSE_OLD_ORDERS',
        l_updated_rows,
        SYSTIMESTAMP
    );

    DBMS_OUTPUT.PUT_LINE(
        'Orders closed = ' || l_updated_rows
    );
END;
/
```

### 7.3. Called procedures may execute SQL

If you call a procedure after your main DML and that procedure executes SELECT/INSERT/UPDATE/DELETE, do not rely on `SQL%ROWCOUNT` after the call to get the row count of the earlier DML. Capture the value before calling the procedure, or pass the row count via a parameter.

### 7.4. SQL%ROWCOUNT is not a historical variable

`SQL%ROWCOUNT` does not retain a list of row counts from multiple earlier DML statements. If you need statistics across multiple steps, use separate PL/SQL variables:

```sql
DECLARE
    l_inserted PLS_INTEGER := 0;
    l_updated  PLS_INTEGER := 0;
    l_deleted  PLS_INTEGER := 0;
BEGIN
    INSERT INTO lab_archive (employee_id)
    SELECT employee_id
    FROM lab_employees
    WHERE status = 'INACTIVE';
    l_inserted := SQL%ROWCOUNT;

    UPDATE lab_employees
    SET status = 'ARCHIVED'
    WHERE status = 'INACTIVE';
    l_updated := SQL%ROWCOUNT;

    DELETE FROM lab_sessions
    WHERE expires_at < SYSTIMESTAMP;
    l_deleted := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE('Inserted = ' || l_inserted);
    DBMS_OUTPUT.PUT_LINE('Updated  = ' || l_updated);
    DBMS_OUTPUT.PUT_LINE('Deleted  = ' || l_deleted);
END;
/
```

Each variable is a snapshot of a specific DML statement; they are not affected by subsequent SQL statements.

## 8. SQL%ROWCOUNT with SELECT INTO

`SQL%ROWCOUNT` can also reflect the most recent `SELECT INTO`, but result handling for `SELECT INTO` differs from DML:

- Returns exactly one row: `SELECT INTO` succeeds.
- Returns no rows: PL/SQL raises `NO_DATA_FOUND`.
- Returns more than one row: PL/SQL raises `TOO_MANY_ROWS`.

Do not use `SELECT INTO` as a query that could return an arbitrary number of rows hoping `SQL%ROWCOUNT` will tell you the count. Use an explicit cursor, cursor FOR loop, or `BULK COLLECT` if you need to process multiple rows.

Example:

```sql
DECLARE
    l_employee_name lab_employees.employee_name%TYPE;
    l_rows PLS_INTEGER;
BEGIN
    SELECT employee_name
    INTO l_employee_name
    FROM lab_employees
    WHERE employee_id = 101;

    l_rows := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE(
        'Rows fetched by SELECT INTO = ' || l_rows
    );
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Employee not found.');
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE('Query returned more than one row.');
END;
/
```

After a successful `SELECT INTO`, the row count is 1. For `NO_DATA_FOUND` or `TOO_MANY_ROWS`, handle the specific exception; do not read a stale row count inside the exception handler as if it belonged to an earlier DML statement. If you need the row count of an earlier DML before running `SELECT INTO`, save it into a variable first.

## 9. SQL%ROWCOUNT and explicit cursors

PL/SQL has two groups of cursor attributes that are often confused:

- `SQL%ROWCOUNT`: row count of the most recent SQL statement executed through the implicit SQL cursor.
- `cursor_name%ROWCOUNT`: number of rows fetched so far through a declared explicit cursor.

Explicit cursor example:

```sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, employee_name
        FROM lab_employees
        WHERE department_id = 20;

    l_employee_id lab_employees.employee_id%TYPE;
    l_employee_name lab_employees.employee_name%TYPE;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees
        INTO l_employee_id, l_employee_name;

        EXIT WHEN c_employees%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            c_employees%ROWCOUNT || ': ' ||
            l_employee_id || ' - ' || l_employee_name
        );
    END LOOP;

    DBMS_OUTPUT.PUT_LINE(
        'Fetched rows = ' || c_employees%ROWCOUNT
    );

    CLOSE c_employees;
END;
/
```

`cursor_name%ROWCOUNT` increments with the number of rows fetched, not the total rows affected by DML. After `OPEN` and before `FETCH`, its value is typically 0. When all rows have been fetched, it holds the total number of rows fetched.

### 9.1. Comparing cursor attributes

| Scenario | Attribute to read |
| --- | --- |
| UPDATE/INSERT/DELETE/MERGE just ran | `SQL%ROWCOUNT` |
| SELECT INTO just succeeded | `SQL%ROWCOUNT` (typically 1) |
| Explicit cursor has fetched rows | `c_name%ROWCOUNT` |
| Check if explicit cursor is still open | `c_name%ISOPEN` |
| Check if DML just affected any rows | `SQL%FOUND` or `SQL%ROWCOUNT` |

### 9.2. Cursor FOR loop

A cursor FOR loop automatically opens, fetches, and closes the cursor:

```sql
BEGIN
    FOR r IN (
        SELECT employee_id, employee_name
        FROM lab_employees
        WHERE department_id = 20
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r.employee_id || ' - ' || r.employee_name
        );
    END LOOP;
END;
/
```

If you need to count how many rows were processed inside the loop, use a manually incremented PL/SQL variable. Do not use `SQL%ROWCOUNT` as a row counter for a cursor FOR loop.

## 10. Returning row count from a procedure

### 10.1. Why use an OUT parameter?

A procedure can execute DML, but the caller should not depend on `SQL%ROWCOUNT` after the call. The procedure might execute additional SQL for logging, querying data, or calling sub-procedures. An `OUT` parameter clearly expresses the result the procedure commits to returning.

### 10.2. Procedure that updates and returns row count

```sql
CREATE OR REPLACE PROCEDURE deactivate_department (
    p_department_id IN  NUMBER,
    p_rows_updated  OUT PLS_INTEGER
)
AS
BEGIN
    UPDATE lab_employees
    SET status = 'INACTIVE'
    WHERE department_id = p_department_id
      AND status <> 'INACTIVE';

    p_rows_updated := SQL%ROWCOUNT;
END;
/
```

Caller:

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    deactivate_department(
        p_department_id => 30,
        p_rows_updated  => l_rows
    );

    DBMS_OUTPUT.PUT_LINE(
        'Rows deactivated = ' || l_rows
    );
END;
/
```

The `OUT` parameter preserves the count captured by the procedure right after `UPDATE`, even if the caller runs other SQL afterward.

### 10.3. Procedure that logs and preserves the right row count

```sql
CREATE OR REPLACE PROCEDURE close_old_orders (
    p_cutoff_date  IN  DATE,
    p_rows_closed  OUT PLS_INTEGER
)
AS
    l_rows PLS_INTEGER;
BEGIN
    UPDATE lab_orders
    SET status = 'CLOSED'
    WHERE order_date < p_cutoff_date
      AND status = 'OPEN';

    l_rows := SQL%ROWCOUNT;
    p_rows_closed := l_rows;

    INSERT INTO lab_job_log (
        job_name,
        affected_rows,
        logged_at
    )
    VALUES (
        'CLOSE_OLD_ORDERS',
        l_rows,
        SYSTIMESTAMP
    );
END;
/
```

The `INSERT` into `LAB_JOB_LOG` changes `SQL%ROWCOUNT`, but `p_rows_closed` still holds the `UPDATE` row count. The main DML and the log insert belong to the caller's transaction; if the caller rolls back, both changes can be rolled back.

### 10.4. Designing OUT parameters and exceptions

Conventions should be clear:

- The `OUT` parameter should only be relied upon when the procedure establishes a valid result.
- If DML fails and an exception is raised, the caller receives the exception; do not treat the `OUT` value as a successful result.
- Do not swallow exceptions and return 0, because 0 means the statement succeeded and affected zero rows.
- If you need to report status, row count, and error information, design a clear contract (`OUT` status/message or an exception with a business error code).

## 11. RETURNING INTO and SQL%ROWCOUNT

`RETURNING INTO` allows you to retrieve column values from rows just inserted, updated, or deleted without running a separate `SELECT` afterward.

### 11.1. INSERT ... RETURNING INTO

```sql
DECLARE
    l_new_employee_id lab_employees.employee_id%TYPE;
BEGIN
    INSERT INTO lab_employees (
        employee_id,
        employee_name,
        department_id,
        status
    )
    VALUES (
        lab_employee_seq.NEXTVAL,
        'Mai Tran',
        20,
        'ACTIVE'
    )
    RETURNING employee_id INTO l_new_employee_id;

    DBMS_OUTPUT.PUT_LINE(
        'Created employee ID = ' || l_new_employee_id
    );
    DBMS_OUTPUT.PUT_LINE(
        'Inserted rows = ' || SQL%ROWCOUNT
    );
END;
/
```

`RETURNING` retrieves the newly inserted ID. `SQL%ROWCOUNT` still indicates the row count of the DML statement.

### 11.2. UPDATE ... RETURNING INTO

```sql
DECLARE
    l_new_salary lab_employees.salary%TYPE;
BEGIN
    UPDATE lab_employees
    SET salary = salary * 1.05
    WHERE employee_id = 101
    RETURNING salary INTO l_new_salary;

    DBMS_OUTPUT.PUT_LINE(
        'New salary = ' || l_new_salary
    );
    DBMS_OUTPUT.PUT_LINE(
        'Updated rows = ' || SQL%ROWCOUNT
    );
END;
/
```

This example assumes `EMPLOYEE_ID` identifies at most one row. If DML can affect multiple rows, a single scalar variable cannot receive multiple returned values.

### 11.3. Multi-row DELETE with RETURNING BULK COLLECT

```sql
DECLARE
    TYPE t_order_ids IS TABLE OF lab_orders.order_id%TYPE;
    l_deleted_ids t_order_ids;
    l_deleted_count PLS_INTEGER;
BEGIN
    DELETE FROM lab_orders
    WHERE status = 'CANCELLED'
      AND created_at < DATE '2025-01-01'
    RETURNING order_id BULK COLLECT INTO l_deleted_ids;

    l_deleted_count := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE(
        'Deleted rows = ' || l_deleted_count
    );

    FOR i IN 1 .. l_deleted_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Deleted order = ' || l_deleted_ids(i)
        );
    END LOOP;
END;
/
```

`BULK COLLECT` loads multiple returned values into a collection. `SQL%ROWCOUNT` is still the number of deleted rows. With an empty result, the collection has no elements and the loop does not execute; check `COUNT` beforehand if needed.

### 11.4. RETURNING does not commit

`RETURNING INTO` only returns values from the rows just affected by the DML. It does not commit the transaction and does not guarantee durability yet. The caller still manages `COMMIT`/`ROLLBACK`.

## 12. Dynamic DML and SQL%ROWCOUNT

Dynamic SQL lets you construct SQL statements at runtime. When `EXECUTE IMMEDIATE` runs DML, you can read `SQL%ROWCOUNT` right after the statement.

### 12.1. Dynamic UPDATE with bind variables

```sql
DECLARE
    l_sql VARCHAR2(1000);
    l_rows PLS_INTEGER;
BEGIN
    l_sql :=
        'UPDATE lab_employees ' ||
        'SET status = :1 ' ||
        'WHERE department_id = :2';

    EXECUTE IMMEDIATE l_sql
        USING 'INACTIVE', 40;

    l_rows := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE(
        'Dynamic update rows = ' || l_rows
    );
END;
/
```

`EXECUTE IMMEDIATE` runs DML just like a regular SQL statement; `SQL%ROWCOUNT` reflects the number of affected rows. Use bind variables for varying values to reduce parsing and prevent SQL injection.

### 12.2. Dynamic DELETE

```sql
DECLARE
    l_table_name VARCHAR2(30) := 'LAB_SESSIONS';
    l_rows PLS_INTEGER;
BEGIN
    EXECUTE IMMEDIATE
        'DELETE FROM ' || DBMS_ASSERT.SQL_OBJECT_NAME(l_table_name) ||
        ' WHERE status = :1'
        USING 'EXPIRED';

    l_rows := SQL%ROWCOUNT;
    DBMS_OUTPUT.PUT_LINE('Deleted = ' || l_rows);
END;
/
```

Table and column names cannot be passed as bind variables like data values. If you must concatenate an identifier into a SQL statement, validate it using a whitelist or an appropriate `DBMS_ASSERT` function; never concatenate untrusted input directly.

### 12.3. Dynamic SELECT

For a dynamic SELECT returning one row, use `INTO`:

```sql
DECLARE
    l_count NUMBER;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM lab_employees WHERE status = :1'
        INTO l_count
        USING 'ACTIVE';

    DBMS_OUTPUT.PUT_LINE('Active employees = ' || l_count);
END;
/
```

`SELECT COUNT(*)` always returns one aggregate row, even when no employees match the condition. If a dynamic SELECT returns multiple rows, use a `BULK COLLECT` collection or `DBMS_SQL`/ref cursor as appropriate.

### 12.4. Dynamic DDL has no meaningful DML row count

`EXECUTE IMMEDIATE` can run DDL such as `CREATE TABLE` or `ALTER TABLE`. Do not use `SQL%ROWCOUNT` to count rows for DDL; DDL is not a row-level DML operation in that sense. Use the data dictionary and check object status after DDL.

## 13. FORALL and SQL%BULK_ROWCOUNT

When you need to execute the same DML statement for many elements in a collection, `FORALL` can send bind values in bulk, reducing context switches between the PL/SQL engine and the SQL engine. This is bulk DML.

`FORALL` is not a regular PL/SQL loop. It iterates a single DML statement over collection indices and allows reading per-execution row counts via `SQL%BULK_ROWCOUNT`.

### 13.1. FORALL UPDATE example

```sql
DECLARE
    TYPE t_employee_ids IS TABLE OF NUMBER
        INDEX BY PLS_INTEGER;

    l_employee_ids t_employee_ids;
    l_total_rows PLS_INTEGER;
BEGIN
    l_employee_ids(1) := 101;
    l_employee_ids(2) := 102;
    l_employee_ids(3) := 999999;

    FORALL i IN 1 .. l_employee_ids.COUNT
        UPDATE lab_employees
        SET status = 'INACTIVE'
        WHERE employee_id = l_employee_ids(i);

    l_total_rows := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE(
        'Total rows affected by FORALL = ' || l_total_rows
    );

    FOR i IN 1 .. l_employee_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Input index ' || i ||
            ' affected rows = ' || SQL%BULK_ROWCOUNT(i)
        );
    END LOOP;
END;
/
```

Suppose IDs 101 and 102 exist, and ID 999999 does not exist. `SQL%BULK_ROWCOUNT` yields 1, 1, and 0 respectively; `SQL%ROWCOUNT` is the total number of rows affected across all executions, which is 2 in this example.

### 13.2. SQL%ROWCOUNT and SQL%BULK_ROWCOUNT

| Attribute | Meaning after FORALL |
| --- | --- |
| `SQL%ROWCOUNT` | Total number of rows affected by all DML executions in `FORALL` |
| `SQL%BULK_ROWCOUNT(i)` | Number of rows affected by the i-th DML execution |

`SQL%ROWCOUNT` gives the overall total; `SQL%BULK_ROWCOUNT` helps identify which input element affected 0, 1, or multiple rows.

### 13.3. Handling individual bulk results

If each ID must identify exactly one row:

```sql
DECLARE
    TYPE t_ids IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    l_ids t_ids;
BEGIN
    l_ids(1) := 101;
    l_ids(2) := 102;
    l_ids(3) := 999999;

    FORALL i IN 1 .. l_ids.COUNT
        UPDATE lab_employees
        SET status = 'ACTIVE'
        WHERE employee_id = l_ids(i);

    FOR i IN 1 .. l_ids.COUNT LOOP
        IF SQL%BULK_ROWCOUNT(i) = 0 THEN
            DBMS_OUTPUT.PUT_LINE(
                'Employee ID not found: ' || l_ids(i)
            );
        ELSIF SQL%BULK_ROWCOUNT(i) > 1 THEN
            DBMS_OUTPUT.PUT_LINE(
                'Non-unique ID: ' || l_ids(i)
            );
        END IF;
    END LOOP;
END;
/
```

The loop reading `SQL%BULK_ROWCOUNT` must run before another `FORALL` overwrites the previous bulk metadata. If you need to keep the results longer, copy each value into a separate PL/SQL collection before executing the next SQL statement.

### 13.4. FORALL with sparse collections

An associative array collection can have non-contiguous indices. Using a `1..COUNT` range on a sparse collection can reference a non-existent element. Use appropriate indexing forms such as:

```sql
FORALL i IN INDICES OF l_ids
    DELETE FROM lab_sessions
    WHERE session_id = l_ids(i);
```

Or `VALUES OF` with an index collection when specifying a subset of elements. Consult the PL/SQL `FORALL` documentation for the syntax and restrictions of the collection type you use. `SQL%BULK_ROWCOUNT` is accessed using the corresponding iteration index.

### 13.5. FORALL does not replace a transaction

`FORALL` reduces the overhead of repeated SQL calls; it does not auto-commit and does not make the batch an independent transaction. Changes remain part of the current transaction. The caller can `COMMIT` or `ROLLBACK` according to business boundaries.

## 14. FORALL SAVE EXCEPTIONS and SQL%BULK_EXCEPTIONS

By default, an error in any single DML execution inside `FORALL` causes `FORALL` to stop and raise an exception. When you want to continue processing remaining elements and collect errors, use `SAVE EXCEPTIONS`.

### 14.1. Declaring the ORA-24381 exception

`SAVE EXCEPTIONS` raises the composite error `ORA-24381` after all iterations have been attempted. You can name this exception:

```sql
DECLARE
    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    NULL;
END;
/
```

### 14.2. Example of bulk DML with an element-level error

Assume `LAB_BONUSES` has `EMPLOYEE_ID` as an appropriate foreign key or primary key. The example below illustrates processing multiple IDs:

```sql
DECLARE
    TYPE t_ids IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    l_ids t_ids;
    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    l_ids(1) := 101;
    l_ids(2) := 102;
    l_ids(3) := 103;

    FORALL i IN 1 .. l_ids.COUNT SAVE EXCEPTIONS
        INSERT INTO lab_bonuses (
            employee_id,
            bonus_amount,
            created_at
        )
        VALUES (
            l_ids(i),
            1000,
            SYSTIMESTAMP
        );

    DBMS_OUTPUT.PUT_LINE(
        'Rows inserted = ' || SQL%ROWCOUNT
    );
EXCEPTION
    WHEN e_bulk_errors THEN
        DBMS_OUTPUT.PUT_LINE(
            'Successful rows affected = ' || SQL%ROWCOUNT
        );

        FOR j IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Failed iteration = ' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_INDEX ||
                ', Oracle error = ' ||
                SQL%BULK_EXCEPTIONS(j).ERROR_CODE
            );
            DBMS_OUTPUT.PUT_LINE(
                SQLERRM(-SQL%BULK_EXCEPTIONS(j).ERROR_CODE)
            );
        END LOOP;
END;
/
```

This example only illustrates the structure. If all rows are valid and no errors occur, the exception handler does not run. If errors occur, `SAVE EXCEPTIONS` lets Oracle continue the remaining iterations and then raises `ORA-24381`.

### 14.3. SQL%BULK_EXCEPTIONS

Key attributes:

| Attribute | Meaning |
| --- | --- |
| `SQL%BULK_EXCEPTIONS.COUNT` | Number of collected errors |
| `SQL%BULK_EXCEPTIONS(i).ERROR_INDEX` | Index of the failed iteration |
| `SQL%BULK_EXCEPTIONS(i).ERROR_CODE` | Positive Oracle error code, without the minus sign |

To retrieve the error message, call `SQLERRM` with the negated code: `SQLERRM(-ERROR_CODE)`.

### 14.4. SAVE EXCEPTIONS does not automatically roll back the entire batch

With `SAVE EXCEPTIONS`, iterations that succeeded remain active changes in the current transaction; failed iterations are recorded in `SQL%BULK_EXCEPTIONS`. The `ORA-24381` exception signals that one or more iterations failed—it does not automatically decide whether to commit or roll back the successful iterations.

The application must choose a policy:

- Roll back the entire transaction if the batch must be atomic.
- Keep the successful rows and log the errors to retry failed items if business rules allow.
- Use `SAVEPOINT` and clearly designed transaction boundaries.

Do not swallow `ORA-24381` and commit without inspecting `SQL%BULK_EXCEPTIONS`. Doing so could partially apply a batch while the caller assumes everything succeeded.

### 14.5. Distinguishing SAVE EXCEPTIONS from LOG ERRORS

`SAVE EXCEPTIONS` is PL/SQL's error-handling mechanism for `FORALL`. DML error logging (`LOG ERRORS INTO ... REJECT LIMIT`) is a SQL mechanism that logs certain DML errors into an error logging table in supported scenarios. The two approaches have different purposes and limitations; choose based on batch requirements and how errors need to be traced.

## 15. FORALL, BULK COLLECT, and batch processing

### 15.1. BULK COLLECT is used to fetch multiple rows

`BULK COLLECT` fetches multiple rows into a collection:

```sql
DECLARE
    TYPE t_ids IS TABLE OF lab_employees.employee_id%TYPE;
    l_ids t_ids;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_ids
    FROM lab_employees
    WHERE department_id = 20;

    DBMS_OUTPUT.PUT_LINE(
        'Fetched rows = ' || l_ids.COUNT
    );
END;
/
```

This prints the number of elements fetched into the collection. If `SELECT BULK COLLECT` returns no rows, the collection is empty. `SQL%ROWCOUNT` after the `SELECT` can reflect the number of rows fetched; when you need the current element count, `l_ids.COUNT` directly expresses the collection size.

### 15.2. Combining BULK COLLECT and FORALL

```sql
DECLARE
    TYPE t_ids IS TABLE OF lab_employees.employee_id%TYPE;
    l_ids t_ids;
    l_rows PLS_INTEGER;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO l_ids
    FROM lab_employees
    WHERE status = 'PENDING';

    IF l_ids.COUNT > 0 THEN
        FORALL i IN 1 .. l_ids.COUNT
            UPDATE lab_employees
            SET status = 'READY'
            WHERE employee_id = l_ids(i);

        l_rows := SQL%ROWCOUNT;
    ELSE
        l_rows := 0;
    END IF;

    DBMS_OUTPUT.PUT_LINE(
        'Rows updated = ' || l_rows
    );
END;
/
```

`SELECT BULK COLLECT` loads IDs into the collection; `FORALL` uses those IDs to execute bulk DML. `SQL%ROWCOUNT` after `FORALL` is the total number of rows affected by the bulk DML, while `collection.COUNT` is the number of IDs fetched. These two numbers can differ if some IDs no longer exist or do not match the `UPDATE` predicate.

### 15.3. Memory limits and LIMIT

For large tables, bulk-collecting the entire dataset into a collection can consume excessive PGA memory. Use a cursor to fetch in batches with `LIMIT`:

```sql
DECLARE
    CURSOR c_pending IS
        SELECT employee_id
        FROM lab_employees
        WHERE status = 'PENDING';

    TYPE t_ids IS TABLE OF lab_employees.employee_id%TYPE;
    l_ids t_ids;
    l_total_updated PLS_INTEGER := 0;
BEGIN
    OPEN c_pending;

    LOOP
        FETCH c_pending BULK COLLECT INTO l_ids LIMIT 500;
        EXIT WHEN l_ids.COUNT = 0;

        FORALL i IN 1 .. l_ids.COUNT
            UPDATE lab_employees
            SET status = 'READY'
            WHERE employee_id = l_ids(i);

        l_total_updated := l_total_updated + SQL%ROWCOUNT;
    END LOOP;

    CLOSE c_pending;

    DBMS_OUTPUT.PUT_LINE(
        'Total updated = ' || l_total_updated
    );
END;
/
```

Each `FORALL` processes at most 500 IDs in this example. The variable `l_total_updated` accumulates the affected row counts across batches because `SQL%ROWCOUNT` only retains the result of the most recent `FORALL`.

### 15.4. Choosing a batch size

A batch size that is too small increases internal round-trips and overhead; one that is too large can consume too much PGA, hold transactions/undo for too long, and increase rollback duration. Measure with realistic data, row sizes, indexes, and system resources. 500 is only an illustrative number, not a default optimal value.

## 16. SQL%ROWCOUNT and transactions

`SQL%ROWCOUNT` is information about the SQL statement just executed. It does not tell you whether the transaction has been committed, whether it might be rolled back, or whether changes are visible to other sessions.

### 16.1. Successful DML that is not yet committed

```sql
BEGIN
    UPDATE lab_accounts
    SET balance = balance - 100
    WHERE account_id = 10;

    DBMS_OUTPUT.PUT_LINE(
        'Rows updated = ' || SQL%ROWCOUNT
    );

    -- No COMMIT here.
END;
/
```

If the `UPDATE` affects one row, `SQL%ROWCOUNT` is 1 right after the statement. The change remains in the current transaction until `COMMIT` or `ROLLBACK`. Ending the block does not auto-commit.

### 16.2. Rollback does not turn row count into committed rows

```sql
BEGIN
    UPDATE lab_accounts
    SET balance = balance - 100
    WHERE account_id = 10;

    DBMS_OUTPUT.PUT_LINE(
        'Rows affected before rollback = ' || SQL%ROWCOUNT
    );

    ROLLBACK;
END;
/
```

The printed row count is the number of rows updated before the rollback. After `ROLLBACK`, the data changes are undone, so the printed number does not mean 1 row was committed. Use variable names and log messages that express the truth accurately: rows affected by statement, rows committed, and batch status are distinct concepts.

### 16.3. Statement-level rollback and transaction rollback

If a DML statement fails due to a constraint or runtime error, Oracle rolls back the effects of that statement. Earlier DML statements in the same transaction are not automatically rolled back just because a later statement failed. The application decides whether to roll back the entire transaction, roll back to a `SAVEPOINT`, or proceed according to business policy.

Example:

```sql
BEGIN
    UPDATE lab_accounts
    SET balance = balance - 100
    WHERE account_id = 10;

    -- Suppose this INSERT violates a constraint.
    INSERT INTO lab_payments (
        payment_id, account_id, amount
    )
    VALUES (
        1, 10, -100
    );
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
```

The example explicitly rolls back the entire transaction in the exception handler. Without `ROLLBACK`, changes from the earlier statement could remain pending in the transaction depending on the calling context. Never write an exception handler that only prints an error while ignoring transaction state.

### 16.4. SAVEPOINT and row count

`SAVEPOINT` creates a rollback marker within a transaction:

```sql
BEGIN
    SAVEPOINT before_batch;

    UPDATE lab_employees
    SET status = 'READY'
    WHERE status = 'PENDING';

    DBMS_OUTPUT.PUT_LINE(
        'Rows changed = ' || SQL%ROWCOUNT
    );

    -- If a subsequent check fails:
    ROLLBACK TO before_batch;
END;
/
```

`SQL%ROWCOUNT` at the time of printing is still the `UPDATE` row count. `ROLLBACK TO SAVEPOINT` undoes changes after the savepoint, but does not turn the captured row count into a count of rows remaining in the database.

### 16.5. COMMIT is not a step to confirm row count

`COMMIT` ends the transaction and makes eligible changes durable. It is not a `SELECT` statement to count committed rows. If the application needs to persist the row count of each DML statement, capture `SQL%ROWCOUNT` before `COMMIT` and write the result to a variable or log within the same transaction or through a clearly designed audit mechanism.

## 17. Using SQL%ROWCOUNT for business control

### 17.1. Optimistic locking check

An application can use a `VERSION_NO` column to detect whether data has been modified by another session:

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE lab_documents
    SET document_text = :new_text,
        version_no = version_no + 1,
        updated_at = SYSTIMESTAMP
    WHERE document_id = :document_id
      AND version_no = :expected_version;

    l_rows := SQL%ROWCOUNT;

    IF l_rows = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20021,
            'Document was changed or no longer exists.'
        );
    END IF;
END;
/
```

If the row count is 1, the row with the expected version was updated. If it is 0, either the document does not exist or its version changed; the application needs to re-read the state and report an appropriate conflict. The `VERSION_NO` predicate in `WHERE` is what provides concurrency protection; merely reading `SQL%ROWCOUNT` after an `UPDATE` does not create optimistic locking by itself.

### 17.2. Distinguishing not found from condition not met

An `UPDATE` with multiple predicates:

```sql
UPDATE lab_orders
SET status = 'SHIPPED'
WHERE order_id = :order_id
  AND status = 'PAID';
```

If the row count is 0, either the order does not exist or it exists with a status other than `PAID`. The row count does not distinguish between those two causes. If business logic requires different error messages, you must query/check further in a concurrency-safe manner; do not guess the cause from 0.

### 17.3. Preventing duplicate processing with DML conditions

A state-transition operation can be designed so that a second run affects zero rows:

```sql
UPDATE lab_orders
SET status = 'CLOSED',
    closed_at = SYSTIMESTAMP
WHERE order_id = :order_id
  AND status <> 'CLOSED';
```

The first run may yield a row count of 1; a re-run after the status is already `CLOSED` yields a row count of 0. This is an idempotent pattern for simple state transitions, though you still need to account for NULLs, valid transitions, triggers, and external side effects according to business rules.

### 17.4. A row count greater than one may signal a wrong predicate

If the business logic expects one row but `UPDATE`/`DELETE` affects multiple rows, treat it as a signal requiring investigation:

```sql
UPDATE lab_users
SET locked_flag = 'Y'
WHERE email = :email;

IF SQL%ROWCOUNT > 1 THEN
    RAISE_APPLICATION_ERROR(
        -20022,
        'Email is not unique; more than one user was updated.'
    );
END IF;
```

Even better, enforce uniqueness with an appropriate constraint. Checking the row count is an extra control layer, not a substitute for data integrity constraints.

### 17.5. Do not use SELECT COUNT(*) instead of DML row count

If you only need to know how many rows an `UPDATE` just affected, read `SQL%ROWCOUNT` right after the `UPDATE`. Running an extra `SELECT COUNT(*)` afterward wastes a query and can count a different set of rows due to transactions/concurrency or differing predicates. If you need the count of rows still existing after an operation, that is a separate question requiring a separate query.

## 18. Comprehensive hands-on lab

The following examples run in a lab schema. Create the table and sequence once; if the names already exist, use a fresh test schema or clean up data according to your procedure.

### 18.1. Create table and sample data

```sql
CREATE TABLE lab_employee_dml (
    employee_id NUMBER(10)
        CONSTRAINT pk_lab_employee_dml PRIMARY KEY,
    employee_name VARCHAR2(100) NOT NULL,
    department_id NUMBER(5),
    status VARCHAR2(20),
    salary NUMBER(12, 2),
    version_no NUMBER(10) DEFAULT 1 NOT NULL
);

CREATE SEQUENCE lab_employee_dml_seq
START WITH 1000
INCREMENT BY 1;

INSERT INTO lab_employee_dml VALUES
(101, 'An Nguyen', 10, 'ACTIVE', 20000, 1);
INSERT INTO lab_employee_dml VALUES
(102, 'Binh Tran', 10, 'ACTIVE', 22000, 1);
INSERT INTO lab_employee_dml VALUES
(103, 'Chi Le', 20, 'PENDING', 24000, 1);
INSERT INTO lab_employee_dml VALUES
(104, 'Dung Pham', 20, 'PENDING', 26000, 1);

COMMIT;
```

### 18.2. UPDATE and capture row count

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE lab_employee_dml
    SET salary = salary * 1.05
    WHERE department_id = 10;

    l_rows := SQL%ROWCOUNT;

    DBMS_OUTPUT.PUT_LINE('Updated = ' || l_rows);
END;
/
```

Expected result with sample data: 2 rows updated.

### 18.3. Test a non-matching predicate

```sql
BEGIN
    DELETE FROM lab_employee_dml
    WHERE employee_id = -1;

    DBMS_OUTPUT.PUT_LINE(
        'Deleted = ' || SQL%ROWCOUNT
    );
END;
/
```

Expected result: 0, without raising `NO_DATA_FOUND`.

### 18.4. INSERT ... SELECT and row count

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    INSERT INTO lab_employee_archive (
        employee_id,
        employee_name,
        archived_at
    )
    SELECT
        employee_id,
        employee_name,
        SYSTIMESTAMP
    FROM lab_employee_dml
    WHERE status = 'INACTIVE';

    l_rows := SQL%ROWCOUNT;
    DBMS_OUTPUT.PUT_LINE('Archived = ' || l_rows);
END;
/
```

Create a matching `LAB_EMPLOYEE_ARCHIVE` table before running. With the current sample data having no `INACTIVE` rows, the expected row count is 0.

### 18.5. MERGE and total row count

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    MERGE INTO lab_employee_dml t
    USING (
        SELECT 101 AS employee_id, 'ACTIVE' AS status FROM dual
        UNION ALL
        SELECT 105, 'ACTIVE' FROM dual
    ) s
    ON (t.employee_id = s.employee_id)
    WHEN MATCHED THEN
        UPDATE SET t.status = s.status
    WHEN NOT MATCHED THEN
        INSERT (
            employee_id, employee_name, status,
            salary, version_no
        )
        VALUES (
            s.employee_id, 'New Employee', s.status,
            18000, 1
        );

    l_rows := SQL%ROWCOUNT;
    DBMS_OUTPUT.PUT_LINE('MERGE affected = ' || l_rows);
END;
/
```

With two source rows—one matching and one non-matching—the expected total affected rows is 2. `SQL%ROWCOUNT` does not separate the one `UPDATE` from the one `INSERT`.

### 18.6. Procedure returning OUT row count

```sql
CREATE OR REPLACE PROCEDURE set_department_status (
    p_department_id IN NUMBER,
    p_status        IN VARCHAR2,
    p_rows          OUT PLS_INTEGER
)
AS
BEGIN
    UPDATE lab_employee_dml
    SET status = p_status
    WHERE department_id = p_department_id;

    p_rows := SQL%ROWCOUNT;
END;
/

DECLARE
    l_rows PLS_INTEGER;
BEGIN
    set_department_status(20, 'ACTIVE', l_rows);
    DBMS_OUTPUT.PUT_LINE('Procedure changed = ' || l_rows);
END;
/
```

### 18.7. Verify results

```sql
SELECT
    department_id,
    status,
    COUNT(*) AS employee_count
FROM lab_employee_dml
GROUP BY department_id, status
ORDER BY department_id, status;
```

Compare the row counts reported by DML with the data state after `COMMIT`. Before committing, queries in the same session still see the session's uncommitted changes; other sessions will not see them yet.

## 19. Common errors and pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `SQL%ROWCOUNT` prints 1 despite multi-row `UPDATE` | A `SELECT INTO` or log `INSERT` ran after `UPDATE` | Save the row count immediately after DML |
| `UPDATE` affects 0 rows with no exception | Normal DML behavior | Check `SQL%ROWCOUNT = 0` and handle per business rules |
| `SELECT INTO` finds no rows | `SELECT INTO` raises `NO_DATA_FOUND` | Catch the exception or use an appropriate cursor/aggregate |
| `SQL%ROWCOUNT` after procedure does not match caller DML | The called procedure ran other SQL | Return an `OUT` parameter or capture before the call |
| `MERGE` row count does not separate INSERT/UPDATE | `SQL%ROWCOUNT` is only the total affected rows | Design separate audit/measurement if genuinely needed |
| `SQL%ROWCOUNT` after `FORALL` is only the total | Reading total instead of per-iteration count | Use `SQL%BULK_ROWCOUNT(i)` |
| `FORALL` stops on error | `SAVE EXCEPTIONS` was not used | Use `SAVE EXCEPTIONS` to continue and inspect `SQL%BULK_EXCEPTIONS` |
| Partially failed batch treated as success | Swallowing `ORA-24381` without checking errors | Inspect all of `SQL%BULK_EXCEPTIONS` and decide commit/rollback |
| `SQL%ROWCOUNT` lost after another SQL statement | Attribute only describes the most recent SQL statement | Copy into a PL/SQL variable |
| Row count is 1 but transaction rolled back | Row count measures the statement, not the commit | Log affected rows and transaction outcome clearly |
| 0-row DML treated as a database error | Confusing DML with `SELECT INTO` | Distinguish DML semantics from `SELECT INTO` |
| DML setting the same value still counts the row | Row count counts rows touched by the statement | Add an inequality predicate in `WHERE` if needed |
| Dynamic DML vulnerable to SQL injection | Concatenating input into SQL text | Bind values; use whitelist/`DBMS_ASSERT` for identifiers |
| `BULK COLLECT` uses too much memory | Fetching a large dataset all at once into a collection | Use `LIMIT` and process in batches |
| Using `SQL%ROWCOUNT` to count cursor fetches | Confusing implicit and explicit cursors | Use `cursor_name%ROWCOUNT` or a counter variable |

## 20. Best practice principles

1. **Capture row count immediately after DML.** Assign `SQL%ROWCOUNT` to a variable before running a `SELECT`, logging, or calling a procedure.
2. **Use descriptive variable names.** For example `l_rows_updated` or `l_rows_deleted`, rather than an ambiguous generic variable.
3. **Handle 0 rows according to business rules.** A 0-row DML is not automatically an error; determine whether it is normal, a conflict, or a missing record.
4. **Verify expected row counts.** If exactly one row must be affected, check `SQL%ROWCOUNT` and protect uniqueness with constraints.
5. **Do not confuse row count with commit.** Only `COMMIT`/`ROLLBACK` determines transaction outcome.
6. **Use OUT parameters for procedures.** Do not force callers to rely on implicit cursor state after a call.
7. **Use RETURNING INTO when you need modified row values.** Avoid a follow-up `SELECT` when DML can already return the data.
8. **Use bind variables for dynamic SQL.** Validate identifiers using a whitelist or `DBMS_ASSERT`.
9. **Use FORALL for appropriate bulk DML.** Read the total via `SQL%ROWCOUNT` and each iteration via `SQL%BULK_ROWCOUNT`.
10. **Handle SAVE EXCEPTIONS intentionally.** Do not ignore bulk errors; decide whether the batch must be atomic or allow partial success.
11. **Limit BULK COLLECT by batch.** Avoid unbounded PGA memory consumption.
12. **Separate SQL%ROWCOUNT from cursor_name%ROWCOUNT.** One tracks the implicit SQL statement; the other tracks rows fetched by an explicit cursor.
13. **Do not infer the cause from a 0 row count.** The row might not exist or the predicate might not match.
14. **Log row counts at the right time.** Logs should distinguish attempted/affected/committed/failed states if the system requires them.

## 21. Self-check questions

1. What is DML? Which DML statements are commonly used in PL/SQL?
2. What does `SQL%ROWCOUNT` return?
3. Why must `SQL%ROWCOUNT` be read immediately after DML?
4. How do `SQL%FOUND` and `SQL%NOTFOUND` differ from `SQL%ROWCOUNT`?
5. Why is `SQL%ISOPEN` always FALSE for the implicit SQL cursor?
6. Does an `UPDATE` that matches no rows raise `NO_DATA_FOUND`?
7. How does `INSERT ... SELECT` returning no rows differ from `SELECT INTO` finding no rows?
8. If an `UPDATE` matches a row and assigns the same value, what is `SQL%ROWCOUNT` usually?
9. When `MERGE` has both `UPDATE` and `INSERT`, what does `SQL%ROWCOUNT` represent?
10. Why does `SQL%ROWCOUNT` not separate inserted rows from updated rows in `MERGE`?
11. What problem happens if you run `SELECT INTO` after an `UPDATE` and then read `SQL%ROWCOUNT`?
12. Why should a procedure return its row count via an `OUT` parameter?
13. How does `RETURNING INTO` differ from running a `SELECT` again after DML?
14. Does `SQL%ROWCOUNT` indicate whether the transaction has been committed?
15. Which attribute does an explicit cursor use to count fetched rows?
16. Can dynamic DML using `EXECUTE IMMEDIATE` read `SQL%ROWCOUNT`?
17. How does `FORALL` differ from a regular `FOR` loop?
18. How do `SQL%BULK_ROWCOUNT(i)` and `SQL%ROWCOUNT` differ after `FORALL`?
19. What are `SAVE EXCEPTIONS` and `SQL%BULK_EXCEPTIONS` used for?
20. Why is `LIMIT` needed when using `BULK COLLECT` on large datasets?
21. If `SQL%ROWCOUNT` is 0 after an optimistic update, what could the causes be?
22. Why should logs distinguish rows affected from rows committed?

## 22. Mental model

```text
DML IN PL/SQL
   |
   +-- INSERT
   +-- UPDATE
   +-- DELETE
   +-- MERGE
   |
   v
IMPLICIT SQL CURSOR
   |
   +-- SQL%ROWCOUNT : row count of the most recent SQL
   +-- SQL%FOUND    : were any rows affected/returned?
   +-- SQL%NOTFOUND : no rows?
   +-- SQL%ISOPEN   : always FALSE
   |
   v
CAPTURE IMMEDIATELY AFTER DML
   |
   +-- Assign to a variable
   +-- Use an OUT parameter when returning from a procedure
   +-- RETURNING INTO to retrieve row values
   |
   v
BULK DML
   |
   +-- FORALL
   +-- SQL%ROWCOUNT: total affected rows
   +-- SQL%BULK_ROWCOUNT(i): per-iteration count
   +-- SAVE EXCEPTIONS / SQL%BULK_EXCEPTIONS
   |
   v
TRANSACTION
   |
   +-- DML does not auto-COMMIT
   +-- Row count is not commit status
   +-- Caller decides COMMIT / ROLLBACK
```

**Key takeaway:** `SQL%ROWCOUNT` is the result of the most recent SQL statement, not a historical counter and not a commit confirmation. Save the value immediately after DML, use an `OUT` parameter to pass results out of procedures, and use `SQL%BULK_ROWCOUNT` when you need per-execution counts in `FORALL`. Always separate the number of rows affected from the final transaction outcome.
