# Anonymous Blocks, DECLARE, BEGIN, EXCEPTION, and END in PL/SQL

## 1. The PL/SQL Block Is the Fundamental Structural Unit

PL/SQL is Oracle's procedural extension to SQL. SQL describes the data to be queried or modified; PL/SQL adds variables, conditionals, loops, error handling, and the ability to group multiple statements into a single execution unit.

The fundamental unit of PL/SQL is the **block**. A block can declare variables, execute statements, and handle exceptions. A block can be:

- **Anonymous block:** an unnamed block not stored as a standalone procedure/function in the schema. Commonly used for testing, running a short task, invoking logic, or deployment scripts.
- **Named block:** a named program stored in the schema, such as a procedure, function, package, or trigger. These objects can be invoked by name and have their own lifecycle in the database.

A typical anonymous block:

```sql
DECLARE
    v_message VARCHAR2(100);
BEGIN
    v_message := 'Hello PL/SQL';
    DBMS_OUTPUT.PUT_LINE(v_message);
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('An error occurred: ' || SQLERRM);
        RAISE;
END;
/
```

A block has four sections:

| Section | Required? | Purpose |
|---|---|---|
| `DECLARE` | No | Declares local variables, constants, types, cursors, and exceptions |
| `BEGIN` | Yes | Contains the executable statements |
| `EXCEPTION` | No | Handles exceptions raised in the executable section |
| `END` | Yes | Ends the block |

Key point to remember: `DECLARE` and `EXCEPTION` are optional; `BEGIN` and `END` are always required. The `/` on its own line in the example is a command for clients such as SQL*Plus/SQLcl to send the entered block to Oracle, not part of PL/SQL syntax.

This lesson belongs to the **PL/SQL Basics** chapter, focusing on anonymous block structure and the roles of `DECLARE`, `BEGIN`, `EXCEPTION`, and `END`; how to declare variables/constants, execute SQL and PL/SQL statements, handle errors, nest blocks, variable scope, transaction management, and running blocks from tools or Java.

## 2. General Structure of an Anonymous Block

Syntax:

```sql
[DECLARE
    -- declarations
]
BEGIN
    -- executable statements
[EXCEPTION
    -- exception handlers
]
END;
/
```

Rules:

1. `DECLARE` appears only when the block needs to declare local elements.
2. The declarative section ends when `BEGIN` is encountered.
3. All executable statements lie between `BEGIN` and `EXCEPTION` or `END`.
4. `EXCEPTION` begins the error-handling section; handlers are not a continuation of the `BEGIN` section.
5. `END;` closes the block.
6. Semicolons terminate PL/SQL statements; `/` is a client script terminator in certain tools.

### 2.1. Minimal block

If no variable declarations are needed, `DECLARE` can be omitted:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('PL/SQL is running');
END;
/
```

This block has one executable statement and no custom handler.

### 2.2. Block with DECLARE

```sql
DECLARE
    v_count NUMBER := 0;
BEGIN
    v_count := v_count + 1;
    DBMS_OUTPUT.PUT_LINE('Count = ' || v_count);
END;
/
```

`v_count` exists only during execution of the block, and child blocks can access it according to scope rules.

### 2.3. Block with EXCEPTION

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE(10 / 0);
EXCEPTION
    WHEN ZERO_DIVIDE THEN
        DBMS_OUTPUT.PUT_LINE('Cannot divide by zero');
END;
/
```

When division causes `ZERO_DIVIDE`, execution leaves the `BEGIN` section and transfers to the matching handler. Once the handler completes normally, the block ends.

### 2.4. Block without EXCEPTION

```sql
BEGIN
    UPDATE accounts
    SET status = 'ACTIVE'
    WHERE account_id = 100;
END;
/
```

If the UPDATE statement raises an error, the exception propagates to the caller because the block has no handler. Omitting `EXCEPTION` does not make errors disappear.

## 3. Role of DECLARE

`DECLARE` opens the declarative section. This section can contain:

- Variables and constants.
- Local data types and record types.
- Explicit cursors.
- User-defined exceptions.
- Local subprograms (procedures/functions).
- Pragmas permitted in a declarative context.

Declarations are written before `BEGIN`. Do not place regular executable statements such as `UPDATE`, `IF`, or `DBMS_OUTPUT.PUT_LINE` directly in this section.

### 3.1. Declaring variables

```sql
DECLARE
    v_employee_id NUMBER;
    v_employee_name VARCHAR2(100);
    v_salary NUMBER(10, 2);
BEGIN
    v_employee_id := 100;
    v_employee_name := 'An Nguyen';
    v_salary := 25000;

    DBMS_OUTPUT.PUT_LINE(
        v_employee_name || ' has salary ' || v_salary
    );
END;
/
```

Naming conventions like `v_` for variables are purely conventions, not an Oracle requirement. Variable names should not collide with or create ambiguity with column names in embedded SQL.

### 3.2. Declaring variables with default values

Variables can be initialized using `:=` or `DEFAULT`:

```sql
DECLARE
    v_attempts NUMBER := 0;
    v_status VARCHAR2(20) DEFAULT 'NEW';
BEGIN
    v_attempts := v_attempts + 1;
    DBMS_OUTPUT.PUT_LINE(v_status || ', attempts=' || v_attempts);
END;
/
```

If uninitialized, scalar variables typically start with a NULL value. Operations with NULL generally produce NULL, so proactively assign initial values when logic requires them.

### 3.3. Declaring constants

Constants use the `CONSTANT` keyword and must be initialized in the declaration:

```sql
DECLARE
    c_tax_rate CONSTANT NUMBER := 0.10;
    v_amount NUMBER := 1000;
    v_tax NUMBER;
BEGIN
    v_tax := v_amount * c_tax_rate;
    DBMS_OUTPUT.PUT_LINE('Tax = ' || v_tax);
END;
/
```

After declaration, a new value cannot be assigned to `c_tax_rate`. Constants help express values that must not change within the block's scope.

### 3.4. NOT NULL variables

A variable declared `NOT NULL` must have a non-NULL initial value:

```sql
DECLARE
    v_department_id NUMBER NOT NULL := 10;
BEGIN
    DBMS_OUTPUT.PUT_LINE(v_department_id);
END;
/
```

If you omit the initializer or assign NULL to a NOT NULL variable, PL/SQL will raise an error. Use NOT NULL only when a value is genuinely always required.

### 3.5. Using %TYPE to anchor to a column type

`%TYPE` declares a variable with the same type as a column or another variable:

```sql
DECLARE
    v_employee_id employees.employee_id%TYPE;
    v_salary employees.salary%TYPE;
BEGIN
    v_employee_id := 100;
    v_salary := 30000;
END;
/
```

Benefits:

- Reduces repetition of data types in code.
- When a column type changes, the declaration can pick up the new type after recompilation.
- Helps keep variables more compatible with the source column.

`%TYPE` does not automatically copy all column constraints; for example, a NOT NULL constraint is not necessarily inherited as NOT NULL variable behavior. If a variable must be NOT NULL, declare it explicitly.

### 3.6. Using %ROWTYPE to hold a row

`%ROWTYPE` declares a record structured after a table row or cursor row:

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
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Employee not found');
END;
/
```

Record `v_employee` has fields corresponding to the columns of `EMPLOYEES`. Using `%ROWTYPE` is useful when you need an entire row; if you only need a few columns, declare individual variables and SELECT only those columns.

## 4. Data Types and Records in the Declarative Section

### 4.1. Common scalar types

| Type | Used for |
|---|---|
| `NUMBER` | Integers and decimal numbers |
| `VARCHAR2(n)` | Variable-length character string with a maximum length |
| `CHAR(n)` | Fixed-length character string |
| `DATE` | Date and time down to seconds |
| `TIMESTAMP` | Date and time with fractional second precision |
| `BOOLEAN` | TRUE/FALSE/NULL values in PL/SQL |
| `CLOB` | Large character data |
| `BLOB` | Large binary data |

`BOOLEAN` is a PL/SQL type; it was not a traditional SQL column type in many Oracle versions prior to 23c/23ai. SQL BOOLEAN support depends on the Oracle Database version. When writing code compatible across multiple versions, do not assume a BOOLEAN column exists in a table.

### 4.2. Creating local record types

```sql
DECLARE
    TYPE employee_summary_t IS RECORD (
        employee_id NUMBER,
        full_name VARCHAR2(150),
        annual_salary NUMBER
    );

    v_summary employee_summary_t;
BEGIN
    v_summary.employee_id := 100;
    v_summary.full_name := 'An Nguyen';
    v_summary.annual_salary := 360000;

    DBMS_OUTPUT.PUT_LINE(v_summary.full_name);
END;
/
```

`RECORD` groups multiple fields, potentially of different types, into a structured variable. This is a local PL/SQL record, distinct from an object type created at the schema level with `CREATE TYPE`.

### 4.3. Record assignment

Two records of compatible types can be assigned according to PL/SQL rules:

```sql
DECLARE
    TYPE amount_info_t IS RECORD (
        net_amount NUMBER,
        tax_amount NUMBER
    );

    v_a amount_info_t;
    v_b amount_info_t;
BEGIN
    v_a.net_amount := 1000;
    v_a.tax_amount := 100;

    v_b := v_a;
END;
/
```

Do not assume that any two independently declared records with identical field names can be assigned directly to each other. Use the same record type or assign fields individually when needed.

## 5. Role of BEGIN

`BEGIN` starts the executable section. This is the mandatory section of every PL/SQL block and contains statements executed sequentially.

Common statements:

- Variable assignment with `:=`.
- Calling a procedure or function.
- `SELECT ... INTO`.
- DML: `INSERT`, `UPDATE`, `DELETE`, `MERGE`.
- Conditionals `IF`, `CASE`.
- Loops `LOOP`, `WHILE`, `FOR`.
- The `NULL` statement.
- Nested PL/SQL blocks.

### 5.1. Assignment and calculation

```sql
DECLARE
    v_quantity NUMBER := 3;
    v_unit_price NUMBER := 15000;
    v_total NUMBER;
BEGIN
    v_total := v_quantity * v_unit_price;
    DBMS_OUTPUT.PUT_LINE('Total = ' || v_total);
END;
/
```

In PL/SQL, `:=` is used for variable assignment. `=` is used in comparison conditions; do not use `=` instead of `:=` for assignment.

### 5.2. SELECT INTO

`SELECT ... INTO` places query results into PL/SQL variables:

```sql
DECLARE
    v_name employees.last_name%TYPE;
    v_salary employees.salary%TYPE;
BEGIN
    SELECT last_name, salary
    INTO v_name, v_salary
    FROM employees
    WHERE employee_id = 100;

    DBMS_OUTPUT.PUT_LINE(v_name || ': ' || v_salary);
END;
/
```

For a standard SELECT INTO:

- Returns exactly one row: assigns values to the variables.
- Returns no rows: raises `NO_DATA_FOUND`.
- Returns more than one row: raises `TOO_MANY_ROWS`.

The number of columns in the SELECT list must match the number of variables in INTO, and their data types must be compatible.

### 5.3. Using aggregates to always receive one row

An aggregate without GROUP BY, such as `COUNT(*)`, normally returns one row even when there are no source rows:

```sql
DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM employees
    WHERE department_id = 999;

    DBMS_OUTPUT.PUT_LINE('Employees = ' || v_count);
END;
/
```

The result is 0 if no employees match. For `SUM`, `AVG`, `MIN`, and `MAX`, when there are no input values, the result can be NULL; only `COUNT` returns 0.

### 5.4. Executing DML

```sql
BEGIN
    UPDATE employees
    SET salary = salary * 1.05
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE(
        'Updated rows = ' || SQL%ROWCOUNT
    );
END;
/
```

`SQL%ROWCOUNT` returns the number of rows affected by the most recent implicit cursor SQL statement. Read it immediately after the DML you want to check; if another SQL statement runs before reading it, the attribute reflects the new statement.

### 5.5. INSERT and RETURNING INTO

```sql
DECLARE
    v_new_id employees.employee_id%TYPE;
BEGIN
    INSERT INTO employee_audit (
        employee_id,
        action_name,
        action_time
    )
    VALUES (
        100,
        'REVIEWED',
        SYSTIMESTAMP
    )
    RETURNING employee_id INTO v_new_id;

    DBMS_OUTPUT.PUT_LINE('Employee = ' || v_new_id);
END;
/
```

`RETURNING INTO` retrieves values from the row just affected by the DML. The example assumes a single-row INSERT; for multi-row DML, an appropriate mechanism such as `RETURNING BULK COLLECT INTO` in PL/SQL is needed where supported.

### 5.6. IF and ELSIF

```sql
DECLARE
    v_score NUMBER := 82;
    v_result VARCHAR2(20);
BEGIN
    IF v_score >= 90 THEN
        v_result := 'EXCELLENT';
    ELSIF v_score >= 75 THEN
        v_result := 'GOOD';
    ELSIF v_score >= 50 THEN
        v_result := 'PASS';
    ELSE
        v_result := 'FAIL';
    END IF;

    DBMS_OUTPUT.PUT_LINE(v_result);
END;
/
```

Every `IF` must have an `END IF;`. Conditions can combine `AND`, `OR`, `NOT`, and comparison operators.

### 5.7. Loops

Basic loop:

```sql
DECLARE
    v_counter PLS_INTEGER := 1;
BEGIN
    LOOP
        DBMS_OUTPUT.PUT_LINE(v_counter);
        v_counter := v_counter + 1;
        EXIT WHEN v_counter > 3;
    END LOOP;
END;
/
```

WHILE loop:

```sql
DECLARE
    v_counter PLS_INTEGER := 1;
BEGIN
    WHILE v_counter <= 3 LOOP
        DBMS_OUTPUT.PUT_LINE(v_counter);
        v_counter := v_counter + 1;
    END LOOP;
END;
/
```

FOR loop:

```sql
BEGIN
    FOR i IN 1..3 LOOP
        DBMS_OUTPUT.PUT_LINE('Iteration ' || i);
    END LOOP;
END;
/
```

The FOR loop variable `i` is implicitly declared within the loop's scope; it does not need to be declared in DECLARE and should not be reassigned inside the loop.

### 5.8. NULL statement

`NULL;` is a valid statement that performs no action:

```sql
BEGIN
    IF 1 = 1 THEN
        NULL;
    END IF;
END;
/
```

It is useful when a valid empty branch is needed or when scaffolding code during development. Do not confuse the `NULL;` statement with the `NULL` value.

## 6. Role of EXCEPTION

`EXCEPTION` starts the error-handling section of a block. When an exception is raised in the executable section or in a call made from it, PL/SQL searches for a matching handler.

If a handler is found:

1. The remaining executable part of the block is skipped.
2. Oracle runs the matching handler.
3. If the handler finishes normally, the block ends.
4. If the handler raises or re-raises an exception, the error propagates to the outer block/caller.

If no matching handler exists, the exception propagates to the enclosing block or calling environment.

### 6.1. Handler syntax

```sql
BEGIN
    -- executable statements
EXCEPTION
    WHEN exception_name THEN
        -- handling statements
    WHEN another_exception THEN
        -- another handling path
    WHEN OTHERS THEN
        -- catch remaining exceptions
END;
/
```

Each handler begins with `WHEN`. `OTHERS` catches exceptions not handled by specific handlers and should be placed last.

### 6.2. Handling NO_DATA_FOUND

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
        DBMS_OUTPUT.PUT_LINE('No employee matched the ID');
END;
/
```

If the SELECT returns no rows, the next statement in the BEGIN section is not executed; flow transfers to the handler.

### 6.3. Handling TOO_MANY_ROWS

```sql
DECLARE
    v_salary employees.salary%TYPE;
BEGIN
    SELECT salary
    INTO v_salary
    FROM employees
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE(v_salary);
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE(
            'The query returned more than one employee'
        );
END;
/
```

If business logic expects multiple rows, do not catch `TOO_MANY_ROWS` and arbitrarily pick a result. Use a cursor, a cursor FOR loop, or conditions that guarantee a single row.

### 6.4. Common predefined exceptions

| Exception | Common Scenario |
|---|---|
| `NO_DATA_FOUND` | SELECT INTO returns no rows |
| `TOO_MANY_ROWS` | SELECT INTO returns more than one row |
| `ZERO_DIVIDE` | Division by zero |
| `DUP_VAL_ON_INDEX` | INSERT/UPDATE violates a unique index or constraint |
| `VALUE_ERROR` | Conversion error or value does not fit the variable |
| `INVALID_NUMBER` | Invalid string-to-number conversion in certain contexts |
| `CURSOR_ALREADY_OPEN` | Opening an already open explicit cursor |
| `INVALID_CURSOR` | Invalid cursor operation |
| `COLLECTION_IS_NULL` | Calling a method on an atomically NULL collection |
| `CASE_NOT_FOUND` | CASE statement has no matching branch and no ELSE |

Oracle defines many predefined exceptions in the `STANDARD` package; they can be used directly in handlers without declaration.

### 6.5. Handling DUP_VAL_ON_INDEX

```sql
BEGIN
    INSERT INTO departments (department_id, department_name)
    VALUES (10, 'Engineering');
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        DBMS_OUTPUT.PUT_LINE(
            'A row with the same unique key already exists'
        );
END;
/
```

This exception can occur due to a duplicate primary key or unique key. In real applications, determine whether this represents valid existing data or a business error; do not silently ignore every duplicate without checking.

### 6.6. Using WHEN OTHERS

```sql
BEGIN
    -- statements that may fail
    NULL;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Error ' || SQLCODE || ': ' || SQLERRM
        );
        RAISE;
END;
/
```

`WHEN OTHERS` catches remaining exceptions. When you log an error and then `RAISE;`, the original exception is re-thrown so the caller knows the operation failed.

Do not use handlers like:

```sql
WHEN OTHERS THEN
    NULL;
```

unless there is a very specific intention and its consequences are handled. Swallowing errors makes the application believe the operation succeeded even though data may not have been updated.

## 7. SQLCODE and SQLERRM

Inside an exception handler:

- `SQLCODE` returns the numeric code of the current exception.
- `SQLERRM` returns the error message.

Example:

```sql
BEGIN
    DECLARE
        v_result NUMBER;
    BEGIN
        v_result := 10 / 0;
    END;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('SQLCODE=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('SQLERRM=' || SQLERRM);
        RAISE;
END;
/
```

`SQLERRM` is useful for diagnostics, but message strings should not be used for business logic because their text can vary by language or version. Handle errors by exception name or appropriate error code.

### 7.1. Log and re-raise

A pattern:

```sql
DECLARE
    v_order_id NUMBER := 1001;
BEGIN
    UPDATE orders
    SET status = 'PAID'
    WHERE order_id = v_order_id;

    IF SQL%ROWCOUNT = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Order does not exist: ' || v_order_id
        );
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Failed order=' || v_order_id ||
            ', code=' || SQLCODE ||
            ', message=' || SQLERRM
        );
        RAISE;
END;
/
```

The example uses `DBMS_OUTPUT` for illustration. In production, logs should be recorded using a well-designed logging mechanism; do not assume `DBMS_OUTPUT` is persistent logging.

## 8. User-Defined Exceptions

In addition to predefined exceptions, you can define business-specific exceptions.

### 8.1. Declaring and raising an exception

```sql
DECLARE
    e_invalid_salary EXCEPTION;
    v_salary NUMBER := -100;
BEGIN
    IF v_salary < 0 THEN
        RAISE e_invalid_salary;
    END IF;

    DBMS_OUTPUT.PUT_LINE('Salary is valid');
EXCEPTION
    WHEN e_invalid_salary THEN
        DBMS_OUTPUT.PUT_LINE('Salary cannot be negative');
END;
/
```

`e_invalid_salary` is declared in DECLARE and triggered using `RAISE`. The handler matches the exact exception name.

### 8.2. Using RAISE_APPLICATION_ERROR

If you want to return an application error code and clear message:

```sql
BEGIN
    RAISE_APPLICATION_ERROR(
        -20010,
        'The requested quantity exceeds available stock'
    );
END;
/
```

Application-defined error codes must fall within `-20000` to `-20999`. `RAISE_APPLICATION_ERROR` is commonly used to report business errors from PL/SQL to the caller.

Quantity check example:

```sql
DECLARE
    v_requested_qty NUMBER := 5;
    v_available_qty NUMBER := 3;
BEGIN
    IF v_requested_qty > v_available_qty THEN
        RAISE_APPLICATION_ERROR(
            -20011,
            'Insufficient stock'
        );
    END IF;
END;
/
```

### 8.3. Mapping an Oracle error code to an exception name with PRAGMA EXCEPTION_INIT

You can associate an exception name with an Oracle error code:

```sql
DECLARE
    e_resource_busy EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_resource_busy, -54);
BEGIN
    -- An operation that might raise ORA-00054.
    NULL;
EXCEPTION
    WHEN e_resource_busy THEN
        DBMS_OUTPUT.PUT_LINE('Resource is busy');
END;
/
```

`PRAGMA EXCEPTION_INIT` lets handlers use meaningful names instead of relying on `WHEN OTHERS`. The code passed in is the negative integer corresponding to the Oracle error, for example ORA-00054 uses `-54`.

## 9. Exception Propagation and Nested Blocks

PL/SQL allows placing one block inside another. A child block has its own DECLARE, BEGIN, EXCEPTION, and END sections.

```sql
DECLARE
    v_message VARCHAR2(100) := 'Outer block';
BEGIN
    DBMS_OUTPUT.PUT_LINE(v_message);

    DECLARE
        v_count NUMBER := 10;
    BEGIN
        DBMS_OUTPUT.PUT_LINE('Inner count=' || v_count);
    END;

    DBMS_OUTPUT.PUT_LINE('Back to outer block');
END;
/
```

A child block can access the parent block's variables according to scope rules; the parent block cannot access local variables declared only inside the child block after the child block finishes.

### 9.1. Child block handler

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Outer begins');

    BEGIN
        DBMS_OUTPUT.PUT_LINE(10 / 0);
    EXCEPTION
        WHEN ZERO_DIVIDE THEN
            DBMS_OUTPUT.PUT_LINE('Handled in inner block');
    END;

    DBMS_OUTPUT.PUT_LINE('Outer continues');
END;
/
```

The exception is handled in the child block, so the parent block continues running after the child block completes normally.

### 9.2. Unhandled exception in a child block

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Outer begins');

    BEGIN
        DBMS_OUTPUT.PUT_LINE(10 / 0);
    END;

    DBMS_OUTPUT.PUT_LINE('This line is skipped');
EXCEPTION
    WHEN ZERO_DIVIDE THEN
        DBMS_OUTPUT.PUT_LINE('Handled by outer block');
END;
/
```

Because the child block has no handler, the exception propagates to the parent block. The line `This line is skipped` is not executed; the parent block's handler processes the error.

### 9.3. Exception raised inside a handler

If a handler raises a new exception, the new exception propagates to the enclosing block; the same block does not look for another handler within its own EXCEPTION section.

A nested block can be used to handle errors within the error-handling logic itself:

```sql
BEGIN
    -- Main work
    NULL;
EXCEPTION
    WHEN OTHERS THEN
        BEGIN
            -- Attempt secondary logging.
            DBMS_OUTPUT.PUT_LINE(SQLERRM);
        EXCEPTION
            WHEN OTHERS THEN
                NULL; -- Only if logging failure is deliberately ignored.
        END;

        RAISE;
END;
/
```

In the example, a child block wraps logging so a logging failure can be handled separately; then `RAISE` in the outer handler re-throws the main error. In real systems, design logging so the original error is never lost.

### 9.4. Exception in the DECLARE section

An exception raised during variable initialization in the declarative section is not handled by that block's own EXCEPTION handler; it propagates to the enclosing block. If you need to handle initialization errors, use a separate child block:

```sql
BEGIN
    DECLARE
        v_number NUMBER := TO_NUMBER('not-a-number');
    BEGIN
        DBMS_OUTPUT.PUT_LINE(v_number);
    EXCEPTION
        WHEN OTHERS THEN
            DBMS_OUTPUT.PUT_LINE('Inner executable handler');
    END;
EXCEPTION
    WHEN INVALID_NUMBER THEN
        DBMS_OUTPUT.PUT_LINE('Handled by outer block');
END;
/
```

In the example, the conversion error occurs when initializing `v_number`, before the child block's BEGIN section starts. The child block's handler cannot catch it; the outer block can handle it under the appropriate exception.

## 10. Variable Scope and Block Labels

### 10.1. Variable scope

A variable declared in a block is valid only within that block and any nested child blocks inside it.

```sql
DECLARE
    v_value NUMBER := 10;
BEGIN
    DECLARE
        v_inner NUMBER := 20;
    BEGIN
        DBMS_OUTPUT.PUT_LINE(v_value); -- outer variable
        DBMS_OUTPUT.PUT_LINE(v_inner); -- inner variable
    END;

    DBMS_OUTPUT.PUT_LINE(v_value);
    -- v_inner is no longer in scope here.
END;
/
```

### 10.2. Same-named variables in nested blocks

If a child block declares a variable with the same name, the child block's local variable shadows the outer block's variable within the child block's scope:

```sql
<<outer_block>>
DECLARE
    v_status VARCHAR2(20) := 'OUTER';
BEGIN
    DECLARE
        v_status VARCHAR2(20) := 'INNER';
    BEGIN
        DBMS_OUTPUT.PUT_LINE(v_status);
        DBMS_OUTPUT.PUT_LINE(outer_block.v_status);
    END;
END outer_block;
/
```

The `outer_block` label allows explicitly referencing the outer block's variable when shadowed. Avoid overusing identical variable names across multiple scopes, as it makes code harder to read.

### 10.3. Labeling blocks

You can place a label before a block and repeat the label at END:

```sql
<<process_order>>
DECLARE
    v_order_id NUMBER := 1001;
BEGIN
    DBMS_OUTPUT.PUT_LINE('Order ' || v_order_id);
END process_order;
/
```

Block names are optional. Labels are useful with nested blocks or when referencing variables in an outer scope.

## 11. Cursors in Anonymous Blocks

When a SELECT returns multiple rows, a cursor can be used. A cursor FOR loop automatically opens, fetches, and closes the cursor:

```sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, last_name, salary
        FROM employees
        WHERE department_id = 10
        ORDER BY employee_id;
BEGIN
    FOR r_employee IN c_employees LOOP
        DBMS_OUTPUT.PUT_LINE(
            r_employee.employee_id || ': ' ||
            r_employee.last_name || ' - ' ||
            r_employee.salary
        );
    END LOOP;
END;
/
```

`r_employee` is implicitly declared for the loop and has fields matching the SELECT list. A cursor FOR loop is suitable when you only need to read results sequentially.

### 11.1. Cursor FOR loop with an inline query

You do not necessarily have to declare a separate cursor:

```sql
BEGIN
    FOR r IN (
        SELECT department_id, department_name
        FROM departments
        ORDER BY department_id
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r.department_id || ' - ' || r.department_name
        );
    END LOOP;
END;
/
```

### 11.2. Manual explicit cursor

When you need control over OPEN/FETCH/CLOSE:

```sql
DECLARE
    CURSOR c_departments IS
        SELECT department_id, department_name
        FROM departments;

    v_department_id departments.department_id%TYPE;
    v_department_name departments.department_name%TYPE;
BEGIN
    OPEN c_departments;

    LOOP
        FETCH c_departments
        INTO v_department_id, v_department_name;

        EXIT WHEN c_departments%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            v_department_id || ' - ' || v_department_name
        );
    END LOOP;

    CLOSE c_departments;
EXCEPTION
    WHEN OTHERS THEN
        IF c_departments%ISOPEN THEN
            CLOSE c_departments;
        END IF;
        RAISE;
END;
/
```

A cursor FOR loop usually requires less code and carries less risk of forgetting to close the cursor. Explicit cursors are useful when fetching in batches or using specific cursor attributes.

### 11.3. Implicit cursor attributes

After DML or SELECT INTO, you can use:

| Attribute | Meaning |
|---|---|
| `SQL%FOUND` | Most recent SQL statement affected/returned at least one row in context |
| `SQL%NOTFOUND` | No rows were affected/returned |
| `SQL%ROWCOUNT` | Number of rows affected or returned |
| `SQL%ISOPEN` | Open status of the implicit cursor; implicit cursors are managed by Oracle and closed after the statement |

With SELECT INTO, if there are no rows, `NO_DATA_FOUND` is raised before code can continue to read `SQL%NOTFOUND`. With multiple rows, `TOO_MANY_ROWS` is raised.

## 12. Execution Order and Control Flow

An anonymous block executes in sequence:

```text
Start block
    |
    v
Run DECLARE section (initialize declarations)
    |
    v
Run statements in BEGIN
    |
    +---- No error ------------------------+
    |                                      |
    |                                      v
    |                                  END block
    |
    +---- Exception raised
              |
              v
       Search for matching WHEN
              |
        +-----+-----+
        |           |
   Handler found   No handler
        |           |
        v           v
   Run handler   Propagate error out
        |
        +-- handler ends normally --------> END block
        |
        +-- handler RAISEs/new error -----> Propagate error out
```

The diagram helps distinguish the declarative, executable, and error-handling sections. An exception is not a regular IF branch; when an exception occurs, the remaining statements in the executable section of the block are skipped.

## 13. EXCEPTION and Transactions

Handling an exception does not automatically mean rolling back the entire transaction.

### 13.1. Blocks do not auto-COMMIT

```sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 1;

    UPDATE accounts
    SET balance = balance + 100
    WHERE account_id = 2;
END;
/
```

An anonymous block does not automatically COMMIT when it finishes. DML changes remain part of the session/caller's transaction. The application can COMMIT or ROLLBACK according to business boundaries.

### 13.2. Exceptions do not automatically roll back all prior changes

If the second statement fails, the first statement is not automatically rolled back across the whole transaction simply because an exception propagated out. Oracle guarantees statement-level rollback for the failing statement, while prior changes in the transaction can remain pending.

Example:

```sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 1;

    UPDATE accounts
    SET balance = balance + 100
    WHERE account_id = -1;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
```

Here the handler explicitly rolls back the entire current transaction and then re-throws the error. Only use a full-transaction `ROLLBACK` if the block genuinely owns the transaction boundary; in multi-layered applications, a rollback can undo prior changes made by the caller before invoking the block.

### 13.3. Using SAVEPOINT for partial rollback

```sql
BEGIN
    SAVEPOINT before_adjustment;

    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 1;

    UPDATE accounts
    SET balance = balance + 100
    WHERE account_id = -1;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO before_adjustment;
        RAISE;
END;
/
```

`ROLLBACK TO SAVEPOINT` only undoes changes made after the savepoint within the current transaction. A savepoint does not end the transaction.

### 13.4. COMMIT in an anonymous block

You can write COMMIT inside PL/SQL:

```sql
BEGIN
    UPDATE employees
    SET status = 'ACTIVE'
    WHERE employee_id = 100;

    COMMIT;
END;
/
```

However, transaction boundaries should be managed by the appropriate business layer. A block called from another service that commits on its own can deprive the caller of the ability to roll back the entire operation sequence.

### 13.5. DDL and implicit commits

DDL such as `CREATE TABLE`, `ALTER TABLE`, and `DROP TABLE` performs an implicit commit under Oracle rules. DDL cannot be written directly as a static SQL statement in standard PL/SQL; if you need to run DDL from PL/SQL, use dynamic SQL such as `EXECUTE IMMEDIATE`.

Do not treat an anonymous block as a way to bundle multiple DDL/DML statements into a single completely rollbackable transaction.

## 14. DBMS_OUTPUT and Viewing Results

`DBMS_OUTPUT.PUT_LINE` writes messages to the session's output buffer. Client tools must enable or read DBMS_OUTPUT to display the content.

### 14.1. Enabling output in SQL*Plus/SQLcl

```sql
SET SERVEROUTPUT ON;

BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello from Oracle');
END;
/
```

`SET SERVEROUTPUT ON` is a client command, not a PL/SQL statement.

### 14.2. SQL Developer

In Oracle SQL Developer, you can enable the DBMS Output panel and attach it to the active connection. Then run the block in script mode if `/` is on its own line.

Keyboard shortcuts may vary by configuration and version; what matters is using the appropriate script execution mode so the client submits the entire block and reads DBMS_OUTPUT.

### 14.3. DBMS_OUTPUT is not a persistent logging system

The output buffer:

- Is not automatically persisted to a log table.
- Does not replace an audit trail.
- May not be displayed by clients if not enabled.
- Is unsuitable as the sole communication channel between the database and a production application.

In applications, return results via OUT parameters, result sets/ref cursors, status tables, or a properly designed logging mechanism.

## 15. Running Anonymous Blocks with SQL Tools

### 15.1. SQL*Plus and SQLcl

Example:

```sql
SET SERVEROUTPUT ON;

DECLARE
    v_message VARCHAR2(100) := 'Hello';
BEGIN
    DBMS_OUTPUT.PUT_LINE(v_message);
END;
/
```

The client buffers the block until it sees `/` on its own line, then submits the block for execution.

### 15.2. SQL Developer

In SQL Worksheet:

- Run as script to execute both the block and the `/` in SQL*Plus style.
- Enable DBMS Output for the connection if you want to see `PUT_LINE`.
- If selecting only part of the code, ensure the selected portion is a complete block.

### 15.3. Do not send the slash over JDBC

When a Java application sends an anonymous PL/SQL block over JDBC, the SQL string is:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello');
END;
```

Do not append `/` at the end of the string passed to `PreparedStatement` or `CallableStatement`. The slash is a client script command separator, not a PL/SQL terminating token for JDBC to send.

## 16. Anonymous Blocks vs. Named PL/SQL Units

| Criterion | Anonymous block | Procedure/function/package |
|---|---|---|
| Has a schema object name | No | Yes |
| Stored in schema | Not stored as an independent unit | Can be stored/compiled in the schema |
| Re-invocation | Send the block each time or save script on client | Invoked by its defined name |
| Parameters | No parameter list of its own; can use bind variables | Supports IN/OUT/IN OUT parameters |
| Reuse | Typically lower, unless the client manages scripts | Suitable for reuse |
| Privileges | Executes according to session/context and related privileges | Can use definer's rights or invoker's rights |
| Purpose | Short tasks, scripts, experiments, calling PL/SQL APIs | Shared logic, business logic managed in the schema |

Example of an anonymous block calling an existing procedure:

```sql
BEGIN
    update_employee_salary(
        p_employee_id => 100,
        p_percent => 5
    );
END;
/
```

Anonymous blocks do not replace procedures. If the same logic is called frequently from multiple places, consider encapsulating it as a named procedure/function.

## 17. Calling Anonymous Blocks from Java/JDBC

Java can submit a PL/SQL block using `CallableStatement` or `PreparedStatement`, depending on whether OUT parameters are needed.

### 17.1. Simple block

```java
String plsql = """
    BEGIN
        UPDATE employees
        SET salary = salary * ?
        WHERE employee_id = ?;
    END;
    """;

try (PreparedStatement ps = connection.prepareStatement(plsql)) {
    ps.setBigDecimal(1, new BigDecimal("1.05"));
    ps.setLong(2, 100L);
    ps.execute();
}
```

Text blocks `"""` require Java 15 or higher. For older Java versions, use string concatenation with `+`. Never concatenate input data directly into SQL; use bind parameters.

### 17.2. Block with an OUT parameter

```java
String plsql = """
    BEGIN
        SELECT COUNT(*)
        INTO ?
        FROM employees
        WHERE department_id = ?;
    END;
    """;

try (CallableStatement cs = connection.prepareCall(plsql)) {
    cs.registerOutParameter(1, java.sql.Types.NUMERIC);
    cs.setInt(2, 10);
    cs.execute();

    BigDecimal count = cs.getBigDecimal(1);
}
```

The example illustrates the concept of binding an OUT parameter; placeholder syntax in a PL/SQL block and bind registration must be verified against the Oracle JDBC driver in use. In practice, OUT parameters are often referenced explicitly inside the PL/SQL block:

```java
String plsql = """
    BEGIN
        :out_count := 0;
        SELECT COUNT(*)
        INTO :out_count
        FROM employees
        WHERE department_id = :department_id;
    END;
    """;
```

Named binding with `:out_count` and `:department_id` depends on Oracle JDBC APIs; `CallableStatement` typically uses positional placeholders with `?`, while named binding has driver-specific APIs. Follow driver documentation and avoid arbitrarily mixing named and positional binding syntax.

### 17.3. Exceptions from PL/SQL to Java

If the block does not handle an exception, the Oracle error is translated by the driver into a `SQLException`. The application can read:

- `getErrorCode()` for the Oracle error code.
- `getSQLState()` for the SQLState if provided by the driver.
- `getMessage()` to read the message.

If the block catches an error and does not re-raise it, Java may receive the result as if the block completed normally. Therefore, only catch errors in PL/SQL when you have appropriate handling or intentionally propagate the error to the caller.

## 18. Complete Example: Read, Validate, and Update an Employee

The following example demonstrates variables, `%TYPE`, SELECT INTO, IF, UPDATE, SQL%ROWCOUNT, and exceptions:

```sql
DECLARE
    v_employee_id employees.employee_id%TYPE := 100;
    v_salary employees.salary%TYPE;
    v_new_salary employees.salary%TYPE;
BEGIN
    SELECT salary
    INTO v_salary
    FROM employees
    WHERE employee_id = v_employee_id;

    IF v_salary IS NULL THEN
        RAISE_APPLICATION_ERROR(
            -20020,
            'Employee salary is not set'
        );
    END IF;

    v_new_salary := v_salary * 1.05;

    UPDATE employees
    SET salary = v_new_salary
    WHERE employee_id = v_employee_id;

    IF SQL%ROWCOUNT = 1 THEN
        DBMS_OUTPUT.PUT_LINE(
            'Updated employee ' || v_employee_id ||
            ', new salary=' || v_new_salary
        );
    ELSE
        RAISE_APPLICATION_ERROR(
            -20021,
            'Unexpected update count'
        );
    END IF;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Employee not found');
        RAISE;
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE('Employee ID is not unique');
        RAISE;
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Error ' || SQLCODE || ': ' || SQLERRM
        );
        RAISE;
END;
/
```

The example assumes `EMPLOYEE_ID` is guaranteed unique. The block does not auto-COMMIT; the caller decides whether to confirm or roll back the transaction. Since `NO_DATA_FOUND` is caught and re-raised, the client still receives the error.

## 19. Common Syntax and Logic Errors

| Error/Symptom | Cause | Resolution |
|---|---|---|
| `PLS-00103` near DECLARE/BEGIN/END | Missing keyword, semicolon, or statement placed in the wrong section | Check block structure and terminators |
| `PLS-00201: identifier must be declared` | Using an undeclared variable/exception/type or missing privileges | Declare in the proper scope and check privileges |
| `ORA-06550` | PL/SQL compilation error, usually accompanied by a specific PLS code | Read all error lines and the reported location |
| `NO_DATA_FOUND` | SELECT INTO returned no rows | Handle the exception or adjust the query for business logic |
| `TOO_MANY_ROWS` | SELECT INTO returned multiple rows | Use a cursor or ensure a unique condition |
| `VALUE_ERROR` | Incompatible conversion, length, or value | Check types, lengths, and input data |
| No DBMS_OUTPUT visible | Client has not enabled or read output | Enable DBMS Output/Serveroutput |
| Block fails to run in JDBC | Sending SQL*Plus `/` or malformed block string | Send block from BEGIN to END; omit the slash |
| Errors are hidden | WHEN OTHERS swallows the error | Log in a controlled manner and RAISE |
| Data remains modified after an error | Misunderstanding that exceptions roll back the whole transaction | Manage ROLLBACK/SAVEPOINT explicitly |
| Variable not visible | Variable is out of scope or child block has ended | Move declaration to an appropriate scope |
| Initialization error misses block's own handler | Exception occurred in the DECLARE section | Use a nested block and handle in the outer block |

### 19.1. Distinguishing compile errors and runtime errors

**Compile errors** occur when PL/SQL cannot compile the block, such as syntax errors or undeclared identifiers. Execution has not started yet.

**Runtime exceptions** occur while the block is executing, such as division by zero, SELECT INTO finding no rows, or constraint violations. A handler can process them if the exception is raised within the scope covered by that handler.

### 19.2. Read every error line

Oracle often returns multiple lines:

```text
ORA-06550: line 8, column 5:
PLS-00201: identifier 'V_TOTAL' must be declared
ORA-06550: line 8, column 5:
PL/SQL: Statement ignored
```

`ORA-06550` gives the error location in the block; `PLS-00201` explains that the identifier has not been declared. Read the detailed error code rather than looking only at the ORA-06550 line.

## 20. Best Practices When Writing Anonymous Blocks

1. Declare variables at the top of the block with meaningful names.
2. Use `%TYPE`/`%ROWTYPE` when variables correspond to table or cursor structures.
3. Keep the BEGIN section in a clear business sequence.
4. Use SELECT INTO only when exactly one row is expected.
5. Use a cursor when multiple rows must be processed.
6. Catch specific exceptions first; put `WHEN OTHERS` last.
7. Never swallow errors without alternative handling.
8. Log sufficient context without exposing sensitive data.
9. Clearly define who owns COMMIT/ROLLBACK.
10. Do not hold transactions open while waiting for users or external services.
11. Use bind variables for input data.
12. Refactor shared logic into procedures/functions when reuse is needed.

### 20.1. Name variables to avoid confusion with column names

Ambiguous example:

```sql
DECLARE
    employee_id NUMBER := 100;
BEGIN
    SELECT salary
    INTO employee_id
    FROM employees
    WHERE employee_id = employee_id;
END;
/
```

The name `employee_id` is both a variable and a column name; the WHERE expression is unclear in intent and may be resolved unexpectedly.

Prefer using a prefix:

```sql
DECLARE
    v_employee_id NUMBER := 100;
    v_salary employees.salary%TYPE;
BEGIN
    SELECT e.salary
    INTO v_salary
    FROM employees e
    WHERE e.employee_id = v_employee_id;
END;
/
```

Table aliases and variable prefixes make SQL statements clearer.

### 20.2. Keep handlers short and focused

A handler should:

- Record the necessary error information.
- Perform necessary cleanup.
- Translate the error into a business code if needed.
- Re-raise if the caller needs to know the operation failed.

Avoid putting excessive business logic inside `WHEN OTHERS`, as it blurs the distinction between success and failure paths.

## 21. Comprehensive Practice Exercise

The following examples can be run in a learning schema. If using Oracle sample tables such as `EMPLOYEES`, ensure the schema has the sample schema installed and appropriate DML privileges. UPDATE statements can modify data; run in a test transaction and ROLLBACK if you do not want to keep changes.

### Step 1. Run a minimal block

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('First PL/SQL block');
END;
/
```

### Step 2. Declare variables and constants

```sql
DECLARE
    c_rate CONSTANT NUMBER := 0.08;
    v_net_amount NUMBER := 250000;
    v_tax NUMBER;
BEGIN
    v_tax := v_net_amount * c_rate;
    DBMS_OUTPUT.PUT_LINE('Tax=' || v_tax);
END;
/
```

### Step 3. Use %TYPE and SELECT INTO

```sql
DECLARE
    v_employee_id employees.employee_id%TYPE := 100;
    v_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE employee_id = v_employee_id;

    DBMS_OUTPUT.PUT_LINE(v_name);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('No matching employee');
END;
/
```

### Step 4. Test TOO_MANY_ROWS

```sql
DECLARE
    v_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE department_id = 10;
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE('More than one row returned');
END;
/
```

The result depends on the number of employees in department 10; if there is only one row, the handler will not run.

### Step 5. Use IF and loops

```sql
DECLARE
    v_score NUMBER := 78;
BEGIN
    IF v_score >= 80 THEN
        DBMS_OUTPUT.PUT_LINE('Very good');
    ELSIF v_score >= 50 THEN
        DBMS_OUTPUT.PUT_LINE('Passed');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Failed');
    END IF;

    FOR i IN 1..3 LOOP
        DBMS_OUTPUT.PUT_LINE('Step ' || i);
    END LOOP;
END;
/
```

### Step 6. Use a cursor FOR loop

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

### Step 7. Create and catch a business exception

```sql
DECLARE
    e_invalid_quantity EXCEPTION;
    v_quantity NUMBER := -1;
BEGIN
    IF v_quantity < 0 THEN
        RAISE e_invalid_quantity;
    END IF;
EXCEPTION
    WHEN e_invalid_quantity THEN
        DBMS_OUTPUT.PUT_LINE('Quantity must not be negative');
END;
/
```

### Step 8. Test nested blocks

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Outer start');

    BEGIN
        RAISE_APPLICATION_ERROR(-20030, 'Inner failure');
    EXCEPTION
        WHEN OTHERS THEN
            DBMS_OUTPUT.PUT_LINE('Inner handler: ' || SQLERRM);
    END;

    DBMS_OUTPUT.PUT_LINE('Outer continues');
END;
/
```

### Step 9. Observe transactions and ROLLBACK

```sql
BEGIN
    UPDATE employees
    SET salary = salary + 1
    WHERE employee_id = 100;

    DBMS_OUTPUT.PUT_LINE('Rows=' || SQL%ROWCOUNT);
END;
/

ROLLBACK;
```

Run a SELECT before and after to observe that the data is rolled back. Do not run the example above in a production environment.

### Step 10. Test exception propagation

```sql
BEGIN
    BEGIN
        RAISE ZERO_DIVIDE;
    END;
EXCEPTION
    WHEN ZERO_DIVIDE THEN
        DBMS_OUTPUT.PUT_LINE('Outer block handled the exception');
END;
/
```

The child block does not catch the error; the parent block receives the exception and handles it.

## 22. Rules to Remember

| Element | Note |
|---|---|
| `DECLARE` | Optional; declares local variables, constants, types, cursors, exceptions, and subprograms |
| `BEGIN` | Required; starts the executable section |
| `EXCEPTION` | Optional; starts error handlers |
| `END;` | Required; closes the block |
| `/` | Client command to execute the buffer in SQL*Plus/SQLcl; do not send as a SQL token over JDBC |
| `:=` | Assigns a value to a PL/SQL variable |
| `%TYPE` | Anchors to a column/variable type |
| `%ROWTYPE` | Record structured after a row |
| `SELECT INTO` | Puts a single-row result into variables; zero or multiple rows raise an exception |
| `SQL%ROWCOUNT` | Number of rows affected by the most recent DML |
| `WHEN OTHERS` | Catches remaining errors; typically log then RAISE |
| `RAISE` | Raises or re-raises an exception |
| `RAISE_APPLICATION_ERROR` | Returns an application error code in the range -20000..-20999 |
| `SQLCODE`/`SQLERRM` | Current exception code and message |
| `COMMIT`/`ROLLBACK` | Transaction management; does not happen automatically just because a block ends |

## 23. Self-Check Questions

**Question 1.** What is an anonymous block?

**Answer:** A PL/SQL block without a schema object name, typically submitted directly from a client to perform a task or experiment.

**Question 2.** Which sections are mandatory in an anonymous block?

**Answer:** `BEGIN` and `END`; `DECLARE` and `EXCEPTION` are optional.

**Question 3.** What is `DECLARE` used for?

**Answer:** Declaring local variables, constants, types, cursors, exceptions, and subprograms before the executable section.

**Question 4.** How does `:=` differ from `=`?

**Answer:** `:=` is used for variable assignment; `=` is typically used for comparison in conditions or SQL expressions.

**Question 5.** How do `%TYPE` and `%ROWTYPE` differ?

**Answer:** `%TYPE` anchors to the type of a single column/variable; `%ROWTYPE` creates a record structured after a row of a table or cursor.

**Question 6.** Which exception is raised when SELECT INTO returns no rows?

**Answer:** `NO_DATA_FOUND`.

**Question 7.** Which exception is raised when SELECT INTO returns multiple rows?

**Answer:** `TOO_MANY_ROWS`.

**Question 8.** Can a cursor FOR loop be used when a SELECT returns multiple rows?

**Answer:** Yes. A cursor FOR loop automatically opens, fetches, and closes the cursor.

**Question 9.** Where should WHEN OTHERS be placed?

**Answer:** At the end of the handler list; use only after specific handlers and do not swallow errors without clear handling.

**Question 10.** What information do SQLCODE and SQLERRM provide?

**Answer:** The error code and message of the current exception.

**Question 11.** What range of codes does RAISE_APPLICATION_ERROR use?

**Answer:** From -20000 to -20999.

**Question 12.** Where does an unhandled exception in a child block go?

**Answer:** It propagates to the enclosing block; a matching handler in the parent block can catch it.

**Question 13.** Can a block's handler catch an error raised while initializing a variable in that same block's DECLARE section?

**Answer:** No. Errors in the declarative section propagate to the enclosing block; an outer block or separate child block is needed to handle them.

**Question 14.** When an anonymous block finishes, does Oracle automatically COMMIT?

**Answer:** No. DML remains part of the current transaction; the caller decides whether to COMMIT or ROLLBACK.

**Question 15.** Is the `/` character part of a PL/SQL block sent over JDBC?

**Answer:** No. The slash is a client script command such as in SQL*Plus/SQLcl; JDBC sends the block from BEGIN to END.

**Question 16.** Is DBMS_OUTPUT persistent logging?

**Answer:** No. It is an output buffer that requires the client to enable/read it and does not replace a log table or audit system.

## 24. Conclusion

An anonymous block is a direct way to group PL/SQL statements into an executable unit without creating a named procedure or function. Its structure consists of an optional declarative section `DECLARE`, a mandatory executable section `BEGIN`, an optional error-handling section `EXCEPTION`, and a mandatory closing `END;`. In `DECLARE`, you declare variables, constants, records, cursors, and exceptions; in `BEGIN`, you assign values, query using SELECT INTO, run DML, conditionals, and loops; in `EXCEPTION`, you handle specific errors or propagate errors back to the caller.

Distinguish compile errors from runtime exceptions, understand `NO_DATA_FOUND`/`TOO_MANY_ROWS` rules, use `WHEN OTHERS` responsibly, and never swallow errors. Nested blocks create separate scopes and allow exceptions to propagate upward to parent blocks. `SQLCODE`, `SQLERRM`, `RAISE`, and `RAISE_APPLICATION_ERROR` help diagnose or express errors in business terms.

Finally, anonymous blocks do not automatically COMMIT when finished. Transaction boundaries still need to be designed at the appropriate layer; the `/` character is a SQL client command, not content to send over JDBC. Once you understand the four sections—DECLARE, BEGIN, EXCEPTION, and END—you can write concise, readable, error-controlled PL/SQL scripts and build the foundation to promote shared logic into procedures, functions, or packages.
