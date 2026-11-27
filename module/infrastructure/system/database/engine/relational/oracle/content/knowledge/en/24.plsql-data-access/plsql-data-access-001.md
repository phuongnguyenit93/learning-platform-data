# SELECT INTO and NO_DATA_FOUND or TOO_MANY_ROWS Errors in PL/SQL

## 1. What is SELECT INTO used for?

In SQL, a `SELECT` statement returns a result set containing 0, 1, or many rows. When writing PL/SQL, if a program needs to place data from a single row into variables for calculation or decision-making, we use the **`SELECT ... INTO`** syntax.

`SELECT INTO` in PL/SQL has a very clear rule: the query must return **exactly one row**.

- Zero rows: PL/SQL raises `NO_DATA_FOUND`.
- Exactly one row: column values are assigned to the target variables.
- Two or more rows: PL/SQL raises `TOO_MANY_ROWS`.

Example:

```sql
DECLARE
    v_employee_id employees.employee_id%TYPE := 100;
    v_last_name   employees.last_name%TYPE;
    v_salary      employees.salary%TYPE;
BEGIN
    SELECT last_name, salary
    INTO v_last_name, v_salary
    FROM employees
    WHERE employee_id = v_employee_id;

    DBMS_OUTPUT.PUT_LINE(
        v_last_name || ' earns ' || v_salary
    );
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Employee does not exist');
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE('Query returned more than one employee');
END;
/
```

`EMPLOYEE_ID` is usually the primary key in the sample schema, so this condition expects at most one row. The two exception handlers still illustrate how to protect the block when the data or query does not match expectations.

This lesson belongs to the **PL/SQL and Data** chapter, focusing on how to use `SELECT INTO`, the single-row rule, the two exceptions `NO_DATA_FOUND` and `TOO_MANY_ROWS`, their root causes, appropriate handling strategies, and choosing a cursor or `BULK COLLECT` when a query may return multiple rows.

## 2. SELECT INTO Syntax

General syntax:

```sql
SELECT select_list
INTO variable_list
FROM table_or_view
[WHERE condition]
[GROUP BY ...]
[HAVING ...]
[ORDER BY ...];
```

The `INTO` clause is the key difference when used in PL/SQL: it specifies where to receive the result.

Example:

```sql
DECLARE
    v_department_name departments.department_name%TYPE;
BEGIN
    SELECT department_name
    INTO v_department_name
    FROM departments
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE(v_department_name);
END;
/
```

Basic rules:

1. The number of expressions in the SELECT list must match the number of variables in the INTO list.
2. The data type of each expression must be compatible with the corresponding target variable.
3. The query must return exactly one row for the remainder of the block to execute normally.
4. If the query does not return exactly one row, PL/SQL raises an exception and transfers control flow to the matching handler.
5. Each expression is assigned by position; column aliases in SELECT do not determine which target variable receives the value.

### 2.1. One column into one variable

```sql
DECLARE
    v_department_name departments.department_name%TYPE;
BEGIN
    SELECT department_name
    INTO v_department_name
    FROM departments
    WHERE department_id = 10;
END;
/
```

### 2.2. Multiple columns into multiple variables

```sql
DECLARE
    v_name   employees.last_name%TYPE;
    v_salary employees.salary%TYPE;
BEGIN
    SELECT last_name, salary
    INTO v_name, v_salary
    FROM employees
    WHERE employee_id = 100;
END;
/
```

SELECT has two expressions, so INTO has two variables. The value of the first expression goes into the first variable, and the second expression goes into the second variable.

### 2.3. Using %TYPE to declare target variables

```sql
DECLARE
    v_employee_id employees.employee_id%TYPE;
    v_salary      employees.salary%TYPE;
BEGIN
    SELECT employee_id, salary
    INTO v_employee_id, v_salary
    FROM employees
    WHERE employee_id = 100;
END;
/
```

`%TYPE` binds a variable's data type to a column. If the column type changes, the declaration can follow the new type when the block or program is recompiled. `%TYPE` does not guarantee that the query returns a single row; cardinality must still be designed separately.

### 2.4. Using %ROWTYPE to receive an entire row

```sql
DECLARE
    v_employee employees%ROWTYPE;
BEGIN
    SELECT *
    INTO v_employee
    FROM employees
    WHERE employee_id = 100;

    DBMS_OUTPUT.PUT_LINE(v_employee.last_name);
    DBMS_OUTPUT.PUT_LINE(v_employee.salary);
END;
/
```

`%ROWTYPE` creates a record whose fields correspond to the columns of a table. When using `SELECT * INTO record`, the column structure and order of the result must be compatible with the record. If only a few columns are needed, it is better to list the columns explicitly and use separate variables so the code is less coupled to table structure changes.

## 3. NO_DATA_FOUND: the query returns no rows

`NO_DATA_FOUND` is a predefined PL/SQL exception. It is raised when a `SELECT ... INTO` statement finds no matching rows.

Example:

```sql
DECLARE
    v_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE employee_id = -1;

    DBMS_OUTPUT.PUT_LINE('Name = ' || v_name);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('No employee matched the supplied ID');
END;
/
```

If no employee has ID `-1`, the line `DBMS_OUTPUT.PUT_LINE('Name = ...')` does not execute. Control transfers directly to the `NO_DATA_FOUND` handler.

### 3.1. Common causes

- The supplied ID or business code does not exist.
- The WHERE filter is too restrictive.
- Data has not yet been created or committed in another transaction.
- A JOIN or additional condition filters out the expected row.
- The caller passed an incorrect bind value.
- Data was deleted or modified between application operations.

Do not automatically assume `NO_DATA_FOUND` is always a data error. In some business scenarios, not finding a row is a normal state—for example, looking up an optional setting that has not been configured yet. How you handle it depends on the meaning of the operation.

### 3.2. Handling when not found is a valid state

If an optional configuration may not exist yet, you can assign a default value:

```sql
DECLARE
    v_discount_rate NUMBER;
BEGIN
    SELECT discount_rate
    INTO v_discount_rate
    FROM customer_discounts
    WHERE customer_id = 501;

    DBMS_OUTPUT.PUT_LINE('Discount=' || v_discount_rate);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        v_discount_rate := 0;
        DBMS_OUTPUT.PUT_LINE('No discount configured; use 0');
END;
/
```

Here, the business rule states that a customer without a configuration receives no discount. Therefore, the handler converts the not-found state into a default value of 0.

If not finding a row is a business error, report it clearly or raise an application error instead of silently assigning a default:

```sql
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Customer discount configuration is required'
        );
```

### 3.3. A handler can set a status flag so the caller can continue

```sql
DECLARE
    v_department_name departments.department_name%TYPE;
    v_found BOOLEAN := TRUE;
BEGIN
    BEGIN
        SELECT department_name
        INTO v_department_name
        FROM departments
        WHERE department_id = 999;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            v_found := FALSE;
    END;

    IF v_found THEN
        DBMS_OUTPUT.PUT_LINE(v_department_name);
    ELSE
        DBMS_OUTPUT.PUT_LINE('Department is optional and was not found');
    END IF;
END;
/
```

The nested sub-block scopes where `NO_DATA_FOUND` is caught. After the sub-block finishes, the outer block checks the `v_found` flag and continues processing.

### 3.4. Error code of NO_DATA_FOUND

Inside a handler:

```sql
BEGIN
    RAISE NO_DATA_FOUND;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('SQLCODE=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('SQLERRM=' || SQLERRM);
END;
/
```

`NO_DATA_FOUND` typically has `SQLCODE` equal to `+100`. The displayed message typically corresponds to `ORA-01403: no data found`. In PL/SQL, catch the exception by its name `NO_DATA_FOUND` rather than comparing error message strings.

## 4. TOO_MANY_ROWS: the query returns more than one row

`TOO_MANY_ROWS` is a predefined exception raised when `SELECT ... INTO` returns two or more rows.

Example:

```sql
DECLARE
    v_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE(v_name);
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE(
            'The department has more than one employee'
        );
END;
/
```

If department 10 has multiple employees, the query cannot fit multiple `LAST_NAME` values into a single scalar variable. PL/SQL raises `TOO_MANY_ROWS`.

### 4.1. Common causes

- The WHERE condition is not selective enough.
- The developer assumed a column is unique, but the schema has no constraint enforcing it.
- Joining a parent table with multiple child rows duplicates the result rows.
- The query returns multiple effective versions because a time-validity predicate is missing.
- Duplicate data exists due to imports or data-writing processes.
- Using `SELECT INTO` when the business requirement actually calls for a list.

### 4.2. Checking cardinality with COUNT

During investigation, you can run a count query:

```sql
SELECT COUNT(*)
FROM employees
WHERE department_id = 10;
```

If the result is greater than 1, the condition does not match a single-row assumption. However, you should not routinely write application logic that runs `COUNT(*)` first and then runs `SELECT` again. Those two SQL statements are separate statements; data may change between the two reads due to transaction isolation and concurrency.

If the goal is to fetch one row, design the predicate/constraint to guarantee a single row. If the goal is to fetch multiple rows, use a cursor or collection.

### 4.3. Do not use DISTINCT arbitrarily to hide cardinality errors

```sql
SELECT DISTINCT department_id
INTO v_department_id
FROM employees
WHERE department_id = 10;
```

`DISTINCT` may return one value if every row shares the same `DEPARTMENT_ID`, but that does not mean the original query selected a single employee. If you need each employee's name or salary, `DISTINCT` does not resolve the business ambiguity.

Only use `DISTINCT` when deduplication is a legitimate part of the query's semantics, not to make `TOO_MANY_ROWS` disappear.

### 4.4. Error code of TOO_MANY_ROWS

`TOO_MANY_ROWS` corresponds to `ORA-01422: exact fetch returns more than requested number of rows`; `SQLCODE` is typically `-1422`.

Example:

```sql
BEGIN
    DECLARE
        v_name employees.last_name%TYPE;
    BEGIN
        SELECT last_name
        INTO v_name
        FROM employees
        WHERE department_id = 10;
    END;
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE(
            'SQLCODE=' || SQLCODE || ', ' || SQLERRM
        );
END;
/
```

The outer block's handler catches the exception propagated from the inner block.

## 5. Why must exactly one row be guaranteed?

`SELECT INTO` is appropriate when a program needs a single unique value to continue its logic. For example:

- Looking up a customer by primary key.
- Reading a unique configuration setting by configuration key.
- Retrieving the current tax rate by a uniquely defined effective key.
- Reading the status of an order by ID.

The WHERE condition should rely on a primary key, unique key, or a business rule that can prove there is at most one row.

### 5.1. Using a primary key

```sql
SELECT customer_name
INTO v_customer_name
FROM customers
WHERE customer_id = p_customer_id;
```

If `CUSTOMER_ID` is a PRIMARY KEY, the query returns at most one row. It can still return 0 rows if the ID does not exist, so `NO_DATA_FOUND` can still occur.

### 5.2. Using a unique key

```sql
SELECT email
INTO v_email
FROM customers
WHERE normalized_email = p_normalized_email;
```

A query can only be considered at-most-one-row if the schema has a UNIQUE constraint matching the expression and NULL rules. Do not rely on the assumption that "users never enter duplicates" if the database does not enforce it.

Note: An Oracle UNIQUE constraint allows multiple NULLs under unique key semantics; the predicate `column = NULL` finds no rows because comparing with NULL evaluates to UNKNOWN. If the business rule requires an email to be mandatory and unique, both NOT NULL and UNIQUE are typically needed.

### 5.3. JOINs can multiply row counts

Suppose a customer has multiple orders:

```sql
SELECT c.customer_name,
       o.order_id
INTO v_customer_name,
     v_order_id
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
WHERE c.customer_id = p_customer_id;
```

Even though `CUSTOMER_ID` is the primary key of the customers table, joining with `ORDERS` can return multiple rows. Filtering to a single parent row does not guarantee the entire query returns one row when the child table has a one-to-many relationship.

If you only need customer information, query the `CUSTOMERS` table separately. If you need multiple orders, use a cursor. If you only need the latest order, define the selection rule using `ORDER BY` and a tie-breaker.

## 6. When the business rule requires exactly one row, more than one row is a data error

If a query is designed to look up a unique setting or a single record by key, `TOO_MANY_ROWS` usually indicates an issue that needs investigation.

For example, a settings table:

```sql
CREATE TABLE app_settings (
    setting_key VARCHAR2(100) NOT NULL,
    setting_value VARCHAR2(4000),
    CONSTRAINT uq_app_settings_key UNIQUE (setting_key)
);
```

Query:

```sql
SELECT setting_value
INTO v_setting_value
FROM app_settings
WHERE setting_key = 'PAYMENT_MODE';
```

The UNIQUE constraint guarantees there are no two rows with the same `SETTING_KEY`. If the application receives `TOO_MANY_ROWS`, check whether the actual query has a JOIN or UNION that duplicates rows, or whether the actual schema/object matches expectations.

Do not handle the error by picking an arbitrary row, because that can mask data integrity violations or JOIN bugs.

## 7. When the business logic allows multiple rows: use a cursor

If a query can return multiple rows, do not use scalar `SELECT INTO`. Using a cursor FOR loop is a straightforward way to read row by row:

```sql
BEGIN
    FOR r_employee IN (
        SELECT employee_id, last_name, salary
        FROM employees
        WHERE department_id = 10
        ORDER BY employee_id
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r_employee.employee_id || ' - ' ||
            r_employee.last_name || ' - ' ||
            r_employee.salary
        );
    END LOOP;
END;
/
```

A cursor FOR loop automatically opens the cursor, fetches the rows, and closes the cursor when it finishes normally or exits the loop. If there are no rows, the loop executes 0 times; it does not raise `NO_DATA_FOUND`.

### 7.1. Explicit cursor

When you need explicit control over OPEN/FETCH/CLOSE:

```sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = 10
        ORDER BY employee_id;

    v_employee_id employees.employee_id%TYPE;
    v_last_name employees.last_name%TYPE;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees
        INTO v_employee_id, v_last_name;

        EXIT WHEN c_employees%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            v_employee_id || ' - ' || v_last_name
        );
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

When an explicit cursor returns 0 rows, the first `FETCH` sets `%NOTFOUND` to TRUE. `NO_DATA_FOUND` is not raised simply because the cursor has no rows.

### 7.2. Cursor with LIMIT and BULK COLLECT

For large result sets, you can fetch in batches to avoid holding the entire result set in memory:

```sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, last_name
        FROM employees
        ORDER BY employee_id;

    TYPE employee_batch_t IS TABLE OF c_employees%ROWTYPE;
    v_batch employee_batch_t;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees
        BULK COLLECT INTO v_batch
        LIMIT 100;

        EXIT WHEN v_batch.COUNT = 0;

        FOR i IN 1 .. v_batch.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                v_batch(i).employee_id || ' - ' ||
                v_batch(i).last_name
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

`BULK COLLECT ... LIMIT` retrieves a batch of rows per `FETCH`. For the final batch with fewer than 100 rows, the collection contains the remaining rows; on the next `FETCH`, the collection is empty and the loop terminates.

## 8. When multiple rows are needed in a collection: SELECT BULK COLLECT INTO

`BULK COLLECT INTO` is how you load multiple rows into a PL/SQL collection:

```sql
DECLARE
    TYPE employee_id_list_t IS TABLE OF employees.employee_id%TYPE;
    v_employee_ids employee_id_list_t;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO v_employee_ids
    FROM employees
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE('Count=' || v_employee_ids.COUNT);
END;
/
```

Unlike scalar `SELECT INTO`, `BULK COLLECT` can receive multiple rows. If the query returns no rows, the collection is emptied; it does not raise `NO_DATA_FOUND` simply because there are no rows.

### 8.1. Multiple columns into multiple collections

```sql
DECLARE
    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    TYPE name_list_t IS TABLE OF employees.last_name%TYPE;

    v_ids id_list_t;
    v_names name_list_t;
BEGIN
    SELECT employee_id, last_name
    BULK COLLECT INTO v_ids, v_names
    FROM employees
    WHERE department_id = 10;

    FOR i IN 1 .. v_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(v_ids(i) || ' ' || v_names(i));
    END LOOP;
END;
/
```

The collections receive data by position. The number of expressions and target collections must match.

### 8.2. Memory considerations

`SELECT BULK COLLECT INTO` without `LIMIT` loads the entire result set into the collection. With large datasets, this can consume significant PGA memory. Use an explicit cursor with `FETCH BULK COLLECT ... LIMIT n` when you need to control batch size.

## 9. When only one row among many is needed: select with deterministic rules

There are valid business cases where you need one representative row from a multi-row set—such as the latest order, the newest effective version, or the highest-priority price.

In those cases, you must define a **row selection rule** using `ORDER BY`, then limit the result.

### 9.1. FETCH FIRST 1 ROW ONLY

Oracle Database 12c Release 1 and later support the row-limiting clause:

```sql
DECLARE
    v_order_id orders.order_id%TYPE;
    v_order_date orders.order_date%TYPE;
BEGIN
    SELECT order_id, order_date
    INTO v_order_id, v_order_date
    FROM orders
    WHERE customer_id = 501
    ORDER BY order_date DESC, order_id DESC
    FETCH FIRST 1 ROW ONLY;

    DBMS_OUTPUT.PUT_LINE(
        'Latest order=' || v_order_id
    );
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Customer has no orders');
END;
/
```

`ORDER BY order_date DESC, order_id DESC` picks the latest order; `ORDER_ID` acts as a tie-breaker so the result is deterministic if two orders share the same timestamp.

If there are no rows, `SELECT INTO` still raises `NO_DATA_FOUND`. If there is at least one row, `FETCH FIRST 1 ROW ONLY` limits the result to one row.

### 9.2. FETCH FIRST 1 ROW ONLY does not fix duplicate data

If a query is supposed to return a single row by unique key but has duplicate data, adding `FETCH FIRST 1 ROW ONLY` can hide a bug. Only use row limiting when "pick the best row" is an actual business requirement.

### 9.3. WITH TIES may still return multiple rows

`FETCH FIRST 1 ROW WITH TIES` can return multiple rows if several rows share the same last sort key value. Therefore, using it with scalar `SELECT INTO` can still raise `TOO_MANY_ROWS`. If you must guarantee a single row, use `ONLY` and an ordering with an appropriate tie-breaker.

### 9.4. Using ROWNUM in older versions

Before the row-limiting clause existed, you could wrap the sorted query in an inline view and filter with `ROWNUM`:

```sql
SELECT order_id, order_date
INTO v_order_id, v_order_date
FROM (
    SELECT order_id, order_date
    FROM orders
    WHERE customer_id = 501
    ORDER BY order_date DESC, order_id DESC
)
WHERE ROWNUM = 1;
```

Do not write `WHERE ROWNUM = 1` in the same query block as `ORDER BY` when the goal is to get the first row in sorted order, because `ROWNUM` is assigned before the `ORDER BY` step in the same query block. The inline view ensures sorting happens first before limiting.

## 10. Aggregates and SELECT INTO when there are no source rows

A common point of confusion: `SELECT INTO` does not always raise `NO_DATA_FOUND` when the table has no matching rows. Aggregate functions without `GROUP BY` typically return exactly one result row.

### 10.1. COUNT returns 0

```sql
DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM employees
    WHERE department_id = 999;

    DBMS_OUTPUT.PUT_LINE('Count=' || v_count);
END;
/
```

If there are no employees in department 999, `COUNT(*)` returns 0. The SELECT still returns one aggregate row, so `NO_DATA_FOUND` is not raised.

### 10.2. SUM, AVG, MIN, MAX can return NULL

```sql
DECLARE
    v_total_salary NUMBER;
BEGIN
    SELECT SUM(salary)
    INTO v_total_salary
    FROM employees
    WHERE department_id = 999;

    IF v_total_salary IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('No salary values');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Total=' || v_total_salary);
    END IF;
END;
/
```

When there are no input rows, `SUM`, `AVG`, `MIN`, and `MAX` usually return NULL in a single result row. `COUNT` returns 0. If `GROUP BY` is present, the query may produce no groups and thus return zero rows; in that case, scalar `SELECT INTO` can raise `NO_DATA_FOUND`.

### 10.3. GROUP BY can produce multiple rows

```sql
SELECT department_id, COUNT(*)
INTO v_department_id, v_count
FROM employees
GROUP BY department_id;
```

If there are multiple departments, the query returns multiple groups and causes `TOO_MANY_ROWS`. If the goal is to count per department, use a cursor or `BULK COLLECT`.

## 11. Using a cursor to distinguish "no rows" from "one or more rows"

A cursor is appropriate when the number of rows can vary and the program needs to process each row.

Example:

```sql
BEGIN
    FOR r IN (
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = 999
        ORDER BY employee_id
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r.employee_id || ' ' || r.last_name
        );
    END LOOP;

    DBMS_OUTPUT.PUT_LINE('Loop completed');
END;
/
```

If there are no rows, the loop does not execute and the block still prints `Loop completed`. This behavior differs from `SELECT ... INTO`, which raises `NO_DATA_FOUND`.

### 11.1. Checking if a cursor has rows with %NOTFOUND

With an explicit cursor:

```sql
DECLARE
    CURSOR c_orders IS
        SELECT order_id, total_amount
        FROM orders
        WHERE customer_id = 501;

    v_order_id orders.order_id%TYPE;
    v_total orders.total_amount%TYPE;
BEGIN
    OPEN c_orders;
    FETCH c_orders INTO v_order_id, v_total;

    IF c_orders%NOTFOUND THEN
        DBMS_OUTPUT.PUT_LINE('No orders');
    ELSE
        DBMS_OUTPUT.PUT_LINE(
            'First order=' || v_order_id
        );
    END IF;

    CLOSE c_orders;
END;
/
```

If you need to process all rows, you must continue calling `FETCH` in a loop until `%NOTFOUND`, rather than fetching only once.

## 12. JOINs and the risk of TOO_MANY_ROWS

A query may have a WHERE clause that selects exactly one row from a parent table yet still return multiple rows due to a one-to-many JOIN.

Suppose:

- `CUSTOMERS.CUSTOMER_ID` is the primary key.
- A customer can have multiple orders in `ORDERS`.

Query:

```sql
SELECT c.customer_name,
       o.order_id
INTO v_customer_name,
     v_order_id
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
WHERE c.customer_id = 501;
```

If customer 501 has three orders, the query returns three rows and raises `TOO_MANY_ROWS`.

### 12.1. Fetching only parent table data

If the goal is the customer name:

```sql
SELECT customer_name
INTO v_customer_name
FROM customers
WHERE customer_id = 501;
```

Do not JOIN the child table if child table data is not needed.

### 12.2. Using EXISTS when you only need to check for child records

```sql
SELECT c.customer_name
INTO v_customer_name
FROM customers c
WHERE c.customer_id = 501
  AND EXISTS (
      SELECT 1
      FROM orders o
      WHERE o.customer_id = c.customer_id
  );
```

`EXISTS` checks existence without multiplying the parent row by the number of child rows. However, if the customer has no orders, `SELECT INTO` will raise `NO_DATA_FOUND`; whether that is desired depends on the business logic.

### 12.3. Fetching only one child row by rule

```sql
SELECT order_id
INTO v_order_id
FROM orders
WHERE customer_id = 501
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 1 ROW ONLY;
```

Only use this approach if the business rule needs the latest order. If all orders are needed, use a cursor.

## 13. Avoid checking COUNT and then running SELECT a second time

A commonly seen pattern:

```sql
SELECT COUNT(*)
INTO v_count
FROM customers
WHERE customer_id = p_customer_id;

IF v_count > 0 THEN
    SELECT customer_name
    INTO v_customer_name
    FROM customers
    WHERE customer_id = p_customer_id;
END IF;
```

This pattern executes two queries. Beyond the redundant overhead, the two statements can observe different data states when concurrent transactions modify the table. Getting `COUNT > 0` does not guarantee the subsequent `SELECT` will still find a row.

If the goal is to read a row and handle the missing case, execute `SELECT INTO` once and catch `NO_DATA_FOUND`:

```sql
BEGIN
    SELECT customer_name
    INTO v_customer_name
    FROM customers
    WHERE customer_id = p_customer_id;

    v_found := TRUE;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        v_found := FALSE;
END;
```

If you only need to know whether a row exists without reading its data, use `EXISTS` or `COUNT` depending on the purpose. If you need to read the data, avoid running a redundant pre-check query.

## 14. Concurrency and read consistency

Oracle provides statement-level read consistency under the default `READ COMMITTED` isolation level. Each `SELECT` statement sees data committed as of the consistent point in time when that statement begins, along with uncommitted changes made by the current transaction.

### 14.1. No row at the statement's snapshot

A session may execute `SELECT INTO` and receive `NO_DATA_FOUND` because the row has not yet been committed in another session when the statement begins. If that other session commits afterward, a subsequent `SELECT` can see the row.

### 14.2. Two SELECT statements can see two different states

Example:

1. Session A runs `COUNT(*)` and gets 1.
2. Session B deletes the row and issues `COMMIT`.
3. Session A runs `SELECT INTO` and gets `NO_DATA_FOUND`.

In `READ COMMITTED`, each statement has its own snapshot. Therefore, checking `COUNT` first does not guarantee the subsequent `SELECT` returns the same row count.

### 14.3. SELECT INTO does not lock rows

A standard `SELECT INTO` only reads data under read consistency; it does not lock rows to prevent other sessions from updating or deleting them after the read.

If the business logic needs to read and then update while preventing concurrent modifications to the row, consider `SELECT ... FOR UPDATE` within the same transaction. `FOR UPDATE` is a locking and concurrency mechanism; only use it when locking is truly required, as it holds row locks until `COMMIT` or `ROLLBACK`.

## 15. Responsible exception handling

### 15.1. Catch specific exceptions

```sql
BEGIN
    SELECT department_name
    INTO v_department_name
    FROM departments
    WHERE department_id = p_department_id;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        -- Handle the case where the department does not exist.
        NULL;
    WHEN TOO_MANY_ROWS THEN
        -- The query was expected to be unique.
        RAISE_APPLICATION_ERROR(
            -20002,
            'Department lookup returned duplicate rows'
        );
END;
```

In production code, replace `NULL` with the appropriate business action: assign a default, flag as not found, or propagate an error to the caller.

### 15.2. WHEN OTHERS does not replace specific handlers

```sql
BEGIN
    SELECT employee_id
    INTO v_employee_id
    FROM employees
    WHERE employee_id = p_employee_id;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20003,
            'Employee not found'
        );
    WHEN TOO_MANY_ROWS THEN
        RAISE_APPLICATION_ERROR(
            -20004,
            'Employee ID is not unique'
        );
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Unexpected error: ' || SQLCODE || ' ' || SQLERRM
        );
        RAISE;
END;
```

Specific handlers clearly express the two cardinality cases. `WHEN OTHERS` only handles unexpected errors, logs details, and re-raises so the caller does not mistakenly think the operation succeeded.

### 15.3. Do not use exceptions to replace normal control flow

If a query can routinely return 0 to many rows, a cursor or collection usually expresses the intent more clearly. Exceptions are suited for handling deviations from the expectation of an exact fetch operation.

For example, looking up an employee by primary key and finding no employee is a situation where `NO_DATA_FOUND` makes sense. However, fetching a department's employee list with a scalar `SELECT INTO` is structurally wrong from the start; do not use `TOO_MANY_ROWS` as a way to check for a list.

## 16. SELECT INTO and SQLCODE/SQLERRM

You can record the error code and message inside an exception handler:

```sql
DECLARE
    v_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE employee_id = -1;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Code=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('Message=' || SQLERRM);
END;
/
```

Common values:

| Exception | Oracle error | Common SQLCODE |
|---|---|---:|
| `NO_DATA_FOUND` | ORA-01403 | `+100` |
| `TOO_MANY_ROWS` | ORA-01422 | `-1422` |

Error messages can vary by language or version. Use exception names or error codes to branch logic, and do not parse `SQLERRM` strings as a stable API.

## 17. SELECT INTO in named procedures and anonymous blocks

The exact fetch rules are the same whether the statement resides in an anonymous block, procedure, function, or trigger.

Procedure example:

```sql
CREATE OR REPLACE PROCEDURE get_employee_name (
    p_employee_id IN employees.employee_id%TYPE,
    p_last_name OUT employees.last_name%TYPE
) AS
BEGIN
    SELECT last_name
    INTO p_last_name
    FROM employees
    WHERE employee_id = p_employee_id;
END;
/
```

If the ID does not exist, the procedure propagates `NO_DATA_FOUND` to the caller because there is no handler. If the query returns multiple rows, `TOO_MANY_ROWS` is propagated. The caller can handle it, or the procedure can translate it into a clear business error.

Calling the procedure:

```sql
DECLARE
    v_last_name employees.last_name%TYPE;
BEGIN
    get_employee_name(100, v_last_name);
    DBMS_OUTPUT.PUT_LINE(v_last_name);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Employee not found');
END;
/
```

## 18. SELECT INTO and Java/JDBC

Java applications often call procedures or submit PL/SQL blocks containing `SELECT INTO`. When `SELECT INTO` raises an unhandled error in PL/SQL, the Oracle JDBC driver translates the error into a `SQLException`.

Example calling the created procedure:

```java
String sql = "{ call get_employee_name(?, ?) }";

try (CallableStatement cs = connection.prepareCall(sql)) {
    cs.setLong(1, employeeId);
    cs.registerOutParameter(2, java.sql.Types.VARCHAR);

    cs.execute();

    String lastName = cs.getString(2);
} catch (SQLException ex) {
    int oracleCode = ex.getErrorCode();
    String message = ex.getMessage();

    // Classify the error by Oracle code or mapped business error.
    throw ex;
}
```

If the procedure lets `NO_DATA_FOUND` or `TOO_MANY_ROWS` propagate, the application can inspect the corresponding Oracle error code. If the procedure catches the error and returns an OUT status instead of re-raising, Java must check that status.

Do not let Java receive an unassigned OUT value and guess that it means "not found". Define an explicit contract: exception, OUT status, or result set.

### 18.1. When to return a result set instead of SELECT INTO?

If the application needs a list, return multiple rows via a ResultSet/ref cursor or query directly with JDBC:

```java
String sql =
    "SELECT employee_id, last_name " +
    "FROM employees " +
    "WHERE department_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, departmentId);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("EMPLOYEE_ID");
            String name = rs.getString("LAST_NAME");
            // Process each row.
        }
    }
}
```

A JDBC `ResultSet` naturally represents 0, 1, or many rows; there is no need for scalar variables and PL/SQL's two exact-fetch exceptions.

## 19. Common errors and misconceptions

| Error/Symptom | Cause | Resolution |
|---|---|---|
| `NO_DATA_FOUND` / ORA-01403 | SELECT INTO returns no rows | Check bind/predicate; handle optional case or raise business error |
| `TOO_MANY_ROWS` / ORA-01422 | SELECT INTO returns two or more rows | Check cardinality, JOIN, constraints; use a cursor if multiple rows are needed |
| `ORA-00947: not enough values` | Number of SELECT expressions does not match INTO variables | Balance SELECT and INTO lists |
| `ORA-00913: too many values` | SELECT returns more expressions than target variables | Declare enough variables or reduce SELECT list |
| `PLS-00306` | Wrong number/types of arguments or incompatible target variable in a call | Check target types and structures |
| Incorrect results due to JOIN | One-to-many JOIN duplicates rows | Check cardinality; use EXISTS or a cursor depending on goal |
| Using COUNT then SELECT | Two separate queries, may observe different snapshots | Execute SELECT INTO once and catch NO_DATA_FOUND if data is needed |
| Using DISTINCT to avoid TOO_MANY_ROWS | Masks unexpected multiple rows | Define business rules and constraints properly |
| Picking an arbitrary row with ROWNUM | Limiting before proper sorting | Sort in an inline view or use FETCH FIRST |
| Aggregate returns NULL without error | SUM/AVG/MIN/MAX on an empty set returns one NULL row | Check IS NULL; COUNT returns 0 |
| Empty cursor treated as NO_DATA_FOUND | Confusing cursor semantics with SELECT INTO | Check `%NOTFOUND` or use a FOR loop |
| BULK COLLECT with no rows | Empty collection, not scalar NO_DATA_FOUND | Check `collection.COUNT` |
| Catching WHEN OTHERS and ignoring | Hides unexpected errors | Log cleanly and `RAISE` |

### 19.1. Distinguishing ORA-01403 and ORA-01422

- `ORA-01403` means an exact fetch found no rows.
- `ORA-01422` means an exact fetch received more rows than requested.

These two errors point to different investigation paths: one indicates no data matched the condition; the other indicates the query or uniqueness assumption is incorrect.

### 19.2. Checking data types

Example:

```sql
DECLARE
    v_salary NUMBER(8, 2);
BEGIN
    SELECT salary
    INTO v_salary
    FROM employees
    WHERE employee_id = 100;
END;
/
```

If a value cannot be converted or exceeds the target variable's precision/range, conversion or value errors such as `VALUE_ERROR` may occur. Using `%TYPE` reduces the risk of mismatch between variables and columns.

## 20. Comprehensive hands-on lab

The examples below use the sample `EMPLOYEES` table in the Oracle sample schema. Verify your schema and privileges before running. These examples primarily read data; INSERT/UPDATE operations are unnecessary for this lesson.

### Step 1. SELECT INTO a single row by key

```sql
DECLARE
    v_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE employee_id = 100;

    DBMS_OUTPUT.PUT_LINE(v_name);
END;
/
```

### Step 2. Trigger a NO_DATA_FOUND scenario

```sql
DECLARE
    v_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE employee_id = -1;

    DBMS_OUTPUT.PUT_LINE(v_name);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('No employee found');
END;
/
```

### Step 3. Trigger a TOO_MANY_ROWS scenario

```sql
DECLARE
    v_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE(v_name);
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE('More than one employee');
END;
/
```

The result depends on the sample schema data; if department 10 has only one row, the handler will not run. You can choose a condition known to return multiple rows in your lab schema.

### Step 4. Receive multiple columns using %TYPE

```sql
DECLARE
    v_id employees.employee_id%TYPE;
    v_name employees.last_name%TYPE;
    v_salary employees.salary%TYPE;
BEGIN
    SELECT employee_id, last_name, salary
    INTO v_id, v_name, v_salary
    FROM employees
    WHERE employee_id = 100;

    DBMS_OUTPUT.PUT_LINE(
        v_id || ' ' || v_name || ' ' || v_salary
    );
END;
/
```

### Step 5. Aggregates on an empty set

```sql
DECLARE
    v_count NUMBER;
    v_total_salary NUMBER;
BEGIN
    SELECT COUNT(*), SUM(salary)
    INTO v_count, v_total_salary
    FROM employees
    WHERE department_id = 999;

    DBMS_OUTPUT.PUT_LINE('Count=' || v_count);

    IF v_total_salary IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('SUM is NULL for this empty set');
    END IF;
END;
/
```

### Step 6. Use a cursor when multiple rows are needed

```sql
BEGIN
    FOR r IN (
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = 10
        ORDER BY employee_id
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r.employee_id || ' ' || r.last_name
        );
    END LOOP;
END;
/
```

### Step 7. Select the latest row deterministically

```sql
DECLARE
    v_order_id orders.order_id%TYPE;
    v_order_date orders.order_date%TYPE;
BEGIN
    SELECT order_id, order_date
    INTO v_order_id, v_order_date
    FROM orders
    WHERE customer_id = 501
    ORDER BY order_date DESC, order_id DESC
    FETCH FIRST 1 ROW ONLY;

    DBMS_OUTPUT.PUT_LINE('Latest order=' || v_order_id);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('No order found');
END;
/
```

This example assumes an `ORDERS` table with the corresponding columns and Oracle 12c Release 1 or later.

### Step 8. Use BULK COLLECT for a list

```sql
DECLARE
    TYPE id_list_t IS TABLE OF employees.employee_id%TYPE;
    v_ids id_list_t;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO v_ids
    FROM employees
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE('Rows=' || v_ids.COUNT);
END;
/
```

If no employees match, `v_ids.COUNT` is 0.

### Step 9. Observe error codes

```sql
BEGIN
    DECLARE
        v_name employees.last_name%TYPE;
    BEGIN
        SELECT last_name
        INTO v_name
        FROM employees
        WHERE employee_id = -1;
    END;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE(
            'Code=' || SQLCODE || ', message=' || SQLERRM
        );
END;
/
```

### Step 10. Enable DBMS_OUTPUT

In SQL*Plus or SQLcl:

```sql
SET SERVEROUTPUT ON;
```

In SQL Developer, enable the DBMS Output panel for the appropriate connection. The `/` on its own line is a client command to submit the block, not part of the PL/SQL statement itself.

## 21. Key takeaways to remember

| Requirement | Approach |
|---|---|
| Read exactly one row | `SELECT ... INTO ...` |
| No row found | Catch `NO_DATA_FOUND` or convert to a business error |
| Query unexpectedly returns multiple rows | Catch `TOO_MANY_ROWS`, investigate predicate/JOIN/constraint |
| Read a multi-row list | Cursor FOR loop or explicit cursor |
| Load multiple rows into a collection | `SELECT ... BULK COLLECT INTO ...` |
| Fetch in batches | Cursor with `FETCH BULK COLLECT ... LIMIT n` |
| Pick one row by priority | `ORDER BY ... FETCH FIRST 1 ROW ONLY` |
| Count matching rows | `COUNT(*) INTO`; without GROUP BY, returns 0 if source set is empty |
| Aggregate on empty set | `SUM`/`AVG`/`MIN`/`MAX` usually return NULL |
| Guarantee at most one row | PRIMARY KEY/UNIQUE constraint and appropriate predicate |
| Avoid JOIN row multiplication | Understand 1-1 and 1-n relationships; consider EXISTS or separate query |
| General error handling | `WHEN OTHERS` logs and re-raises with `RAISE` if caller needs to know |

## 22. Self-check questions

**Question 1.** How many rows does `SELECT INTO` in PL/SQL require the query to return?

**Answer:** Exactly one row to assign the result into the target variables.

**Question 2.** If the query returns no rows, which exception is raised?

**Answer:** `NO_DATA_FOUND` (ORA-01403).

**Question 3.** If the query returns two or more rows, which exception is raised?

**Answer:** `TOO_MANY_ROWS` (ORA-01422).

**Question 4.** Does `SELECT INTO` require the number of target variables to equal the number of columns in the SELECT list?

**Answer:** Yes. Each expression is assigned to its corresponding variable by position, and the data types must be compatible.

**Question 5.** Why use `%TYPE` for target variables?

**Answer:** So the variable tracks the data type of the source column/variable and reduces duplicate type declarations.

**Question 6.** Does `COUNT(*) INTO` on an empty dataset raise `NO_DATA_FOUND`?

**Answer:** No. A `COUNT` aggregate without `GROUP BY` returns one row with a value of 0.

**Question 7.** What does `SUM(salary)` return on an empty set?

**Answer:** Usually a single row with a `NULL` value; you need to check `IS NULL`.

**Question 8.** If you need to process multiple employees, should you use `SELECT INTO` or a cursor?

**Answer:** Use a cursor FOR loop, an explicit cursor, or `BULK COLLECT`.

**Question 9.** Does a cursor FOR loop with zero rows raise `NO_DATA_FOUND`?

**Answer:** No. The loop executes 0 times.

**Question 10.** Does `BULK COLLECT` with zero rows raise `NO_DATA_FOUND`?

**Answer:** Not just for having no rows; the resulting collection is empty.

**Question 11.** Why can a JOIN cause `TOO_MANY_ROWS` even when filtering by the parent table's primary key?

**Answer:** The child table can have multiple rows for a single parent row, causing the JOIN result to multiply.

**Question 12.** Should you add `FETCH FIRST 1 ROW ONLY` to fix every `TOO_MANY_ROWS` error?

**Answer:** No. Only use it when the business logic genuinely requires picking one row based on a sorting rule; if the query should be unique, fix the predicate or constraint.

**Question 13.** Why can running `COUNT` and then running `SELECT` again be unsafe?

**Answer:** The two queries are separate statements with separate snapshots in `READ COMMITTED`; data can change between them, and it also incurs redundant query overhead.

**Question 14.** Does a standard `SELECT INTO` lock rows?

**Answer:** No. It reads under read consistency; if you need to lock rows for a read-then-update flow, consider `SELECT FOR UPDATE`.

**Question 15.** What is the common `SQLCODE` for `TOO_MANY_ROWS`?

**Answer:** `-1422`; `NO_DATA_FOUND` typically has `SQLCODE` `+100`.

## 23. Conclusion

`SELECT ... INTO` is the way to transfer data from SQL into PL/SQL variables when a program expects exactly one row. A query with zero rows raises `NO_DATA_FOUND`; a query with multiple rows raises `TOO_MANY_ROWS`. These two exceptions are not mere syntax errors: they reflect the actual cardinality of the data compared to the program's expectations.

Use a primary key or unique key to guarantee at most one row, while still handling the not-found case. When multiple rows are needed, use a cursor or `BULK COLLECT`; when picking one row among many, define the business rule with `ORDER BY` and explicit deterministic row limiting. Aggregates without `GROUP BY` are a special case: `COUNT` returns 0 on an empty set, while `SUM`, `AVG`, `MIN`, and `MAX` usually return NULL in a single result row.

Finally, understanding the impact of JOINs, read consistency, and transactions helps prevent subtle bugs such as counting before querying or picking an arbitrary row to hide duplicate data. Catch `NO_DATA_FOUND` and `TOO_MANY_ROWS` according to their true business meaning, keep `WHEN OTHERS` responsible, and let the caller know when an operation genuinely fails.
