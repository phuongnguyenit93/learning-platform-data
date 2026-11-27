# Naming Conventions, Block Organization, and Writing Maintainable PL/SQL

## 1. Why Do We Need Conventions When Writing PL/SQL?

PL/SQL often starts with small anonymous blocks: declare variables, run SELECT INTO, update a table, and COMMIT. As an application grows, logic gets split into procedures, functions, packages, triggers, and multiple processing layers. A single module may be modified by many developers over many years and executed in batch jobs or OLTP applications.

If everyone names things differently, structures blocks in their own style, and handles errors arbitrarily, the codebase becomes hard to read and hard to change. Common problems include:

- Not knowing which variable is a parameter and which is a local variable.
- Overly short variable names or names identical to columns, making SQL statements ambiguous.
- A single procedure reading data, performing calculations, writing to multiple tables, sending notifications, and COMMITting.
- Exceptions being caught and ignored, making the application believe an operation succeeded.
- A small error mid-block leaving the transaction in an unclear state.
- Duplicated logic in multiple places, with each copy modified differently.
- Comments no longer matching actual behavior.

Writing maintainable code is not about decorating code. The goal is for readers to understand intent quickly, identify the scope of changes, predict impact, and verify results.

This lesson focuses on three foundations:

1. **Naming conventions:** consistent naming for schema objects, program units, parameters, variables, constants, cursors, and exceptions.
2. **Block organization:** cleanly separating the declarative section, executable section, exception-handling section, and nested blocks.
3. **Code design:** separating responsibilities, controlling transactions, handling errors, using SQL safely, and commenting in the right places.

> This content uses Oracle Database 19c and standard PL/SQL syntax. The prefixes shown are team conventions, not mandatory Oracle syntax. Pick a convention for your project and apply it consistently.

## 2. Basic Shape of a PL/SQL Block

A PL/SQL block has three sections:

~~~sql
DECLARE
    -- Declarative section: variables, constants, cursors, exceptions, types...
BEGIN
    -- Executable section: PL/SQL and SQL statements
EXCEPTION
    -- Error-handling section (optional)
END;
/
~~~

DECLARE and EXCEPTION are optional; BEGIN and END are mandatory. The declarative section has no separate END keyword. A block can nest other blocks inside it.

### 2.1. Anonymous Block

An anonymous block has no stored name in the database:

~~~sql
DECLARE
    l_total NUMBER := 0;
BEGIN
    SELECT COUNT(*)
    INTO l_total
    FROM employees;

    DBMS_OUTPUT.PUT_LINE('Employee count: ' || l_total);
END;
/
~~~

Anonymous blocks are suited for learning syntax, controlled administrative scripts, quick logic tests, or invoking stored program units. Do not keep all long-term business logic inside an anonymous block script. When logic needs reuse, testing, and privilege management, consider a procedure, function, or package.

### 2.2. Named Procedure

~~~sql
CREATE OR REPLACE PROCEDURE print_employee_count
AS
    l_total PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO l_total
    FROM employees;

    DBMS_OUTPUT.PUT_LINE('Employee count: ' || l_total);
END print_employee_count;
/
~~~

A procedure has a name and can be called from multiple places:

~~~sql
BEGIN
    print_employee_count;
END;
/
~~~

The name after END is syntactically optional, but repeating the block name helps catch mismatches in long or nested blocks.

### 2.3. Function

A function returns a value:

~~~sql
CREATE OR REPLACE FUNCTION calculate_tax (
    p_taxable_amount IN NUMBER
)
RETURN NUMBER
IS
    c_tax_rate CONSTANT NUMBER := 0.10;
BEGIN
    RETURN p_taxable_amount * c_tax_rate;
END calculate_tax;
/
~~~

A function's name should describe the result it provides. Functions called from SQL are also subject to specific rules and restrictions regarding side effects, transaction control, and data types.

### 2.4. Package

A package groups related types, constants, variables, cursors, procedures, and functions into a single API:

~~~sql
CREATE OR REPLACE PACKAGE employee_api AS
    PROCEDURE change_salary (
        p_employee_id IN employees.employee_id%TYPE,
        p_new_salary  IN employees.salary%TYPE
    );
END employee_api;
/

CREATE OR REPLACE PACKAGE BODY employee_api AS
    PROCEDURE change_salary (
        p_employee_id IN employees.employee_id%TYPE,
        p_new_salary  IN employees.salary%TYPE
    ) IS
    BEGIN
        UPDATE employees
        SET salary = p_new_salary
        WHERE employee_id = p_employee_id;

        IF SQL%ROWCOUNT = 0 THEN
            RAISE_APPLICATION_ERROR(-20001, 'Employee not found');
        END IF;
    END change_salary;
END employee_api;
/
~~~

The package specification is the public interface. The package body contains the implementation and may include private helpers that do not appear in the specification.

## 3. Syntax Rules and Statement Termination

Some PL/SQL syntax errors stem from confusing statement terminators with block terminators or client commands.

### 3.1. Semicolons

PL/SQL statements end with a semicolon:

~~~sql
l_count := 0;
SELECT COUNT(*) INTO l_count FROM employees;
DBMS_OUTPUT.PUT_LINE(l_count);
~~~

END; terminates the PL/SQL block. A forward slash on its own line is a command for tools like SQL*Plus, SQLcl, or SQL Developer in script mode; it instructs the client to send the current buffer to the database. The slash is not a PL/SQL statement and is not always needed when calling via drivers/APIs.

### 3.2. Distinguishing Semicolons from the Forward Slash

Example running in SQL*Plus/SQLcl:

~~~sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello');
END;
/
~~~

When a JDBC/ODP.NET application sends an anonymous block, it typically sends the text from BEGIN through END; without the slash line. Copying the slash into an API call as part of the SQL statement can cause a syntax error from the driver.

### 3.3. Writing Multi-Line Statements

SQL and PL/SQL do not require each statement to fit on one line. Break lines structurally:

~~~sql
UPDATE orders
SET    status       = 'APPROVED',
       approved_at  = SYSTIMESTAMP,
       approved_by  = p_user_id
WHERE  order_id     = p_order_id;
~~~

The goal is for readers to recognize the table, updated columns, and predicate without scanning a long single line.

## 4. Identifier Naming Conventions

Oracle allows object names and PL/SQL identifiers under its own rules. A project should adopt a readable, stable style and avoid relying on special names.

### 4.1. Use Meaningful Names

~~~sql
-- Hard to understand
x NUMBER;
tmp NUMBER;
v1 VARCHAR2(100);

-- Easier to understand
l_order_total NUMBER(12,2);
l_customer_email VARCHAR2(320);
l_retry_count PLS_INTEGER;
~~~

Short names remain reasonable for very small-scope loop indices like i and j, but do not use single-letter names for business data.

### 4.2. Choose One Case Style

Unquoted Oracle names are case-insensitive. A project might use UPPER_SNAKE_CASE for SQL objects and keywords and lower_snake_case for PL/SQL variables, or another convention as long as it is consistent.

~~~sql
CREATE OR REPLACE PROCEDURE close_expired_orders ...
~~~

~~~sql
l_expired_order_count PLS_INTEGER;
~~~

Do not enclose object names in double quotes just to preserve lowercase letters:

~~~sql
-- Avoid creating unnecessary quoted identifiers
CREATE TABLE "SalesOrders" (...);
~~~

Quoted identifiers are case-sensitive when referenced and can cause friction with tools, SQL, and code generators. Use unquoted identifiers unless there is a specific requirement.

### 4.3. Avoid Keywords and Confusing Names

Avoid naming identifiers the same as SQL/PLSQL keywords or functions with special meanings when possible. For example, use order_status instead of order, user_name instead of user, created_at instead of date.

Avoid overly generic names like VALUE, TYPE, LEVEL, COMMENT, or STATUS when a more specific name works. Some names may still be syntactically valid in certain contexts, but specific names make code clearer and reduce collisions.

### 4.4. Identifier Length

In Oracle Database 19c with an appropriate COMPATIBLE setting (12.2 or higher), most identifiers have a maximum length of 128 bytes. Some identifier types retain their own limits. If an environment requires compatibility with older releases, the limit may be lower.

Do not use up the entire length limit for names. Overly long names make SQL hard to read and write. Use clear names, avoid arbitrary abbreviations, and verify limits for specific object types.

### 4.5. Use Consistent Terminology

Column and table names should be stable and not tied to a single screen or language. For example, customer_id, invoice_date, and payment_status are more durable than ma_kh, ngay_hd, and stt1 when the codebase uses English consistently.

Crucially, do not mix cust_id, customerNo, customer_number, and c_id for the same concept across different modules.

## 5. Naming Conventions by Object Type

A sample convention you can use:

| Object | Illustrative Convention | Example |
| --- | --- | --- |
| Table | Plural noun or collective noun | ORDERS, CUSTOMERS |
| Column | Clear noun | ORDER_DATE, CUSTOMER_ID |
| Primary key | PK_<TABLE> | PK_ORDERS |
| Foreign key | FK_<CHILD>_<PARENT> | FK_ORDERS_CUSTOMERS |
| Unique constraint | UK_<TABLE>_<KEY> | UK_CUSTOMERS_EMAIL |
| Check constraint | CK_<TABLE>_<RULE> | CK_ORDERS_AMOUNT |
| Index | IX_<TABLE>_<COLUMNS> | IX_ORDERS_CUSTOMER_DATE |
| Sequence | SEQ_<ENTITY> | SEQ_ORDER_ID |
| View | V_<PURPOSE> or VW_<PURPOSE> | VW_OPEN_ORDERS |
| Procedure | Verb + object | CLOSE_EXPIRED_ORDERS |
| Function | Verb/phrase describing the result | CALCULATE_TAX |
| Package | Business domain group | ORDER_API, CUSTOMER_RULES |
| Trigger | Table + event + purpose | TRG_ORDERS_AUDIT |

Prefixes are only suggestions. If a project already follows another convention, stick with the project's convention rather than changing part of it and leaving the codebase inconsistent.

### 5.1. Procedure Names Start with a Verb

Procedures perform actions: CREATE_ORDER, APPROVE_ORDER, CANCEL_ORDER, RECALCULATE_INVOICE, LOAD_DAILY_SALES. Names should state both action and object. PROCESS_DATA is too vague; RECONCILE_DAILY_PAYMENTS describes the job clearly.

### 5.2. Function Names Describe the Result

Functions usually return a value: GET_CUSTOMER_STATUS, CALCULATE_NET_AMOUNT, IS_VALID_EMAIL, COUNT_OPEN_ORDERS. GET suggests a read operation, CALCULATE suggests a computation. Avoid functions whose name implies a pure read while secretly writing data or committing transactions.

### 5.3. Package Names by Business Domain

Packages should group related operations: ORDER_API, ORDER_VALIDATION, ORDER_REPORTING, PAYMENT_RECONCILIATION. Do not create a giant UTILS or COMMON package holding hundreds of unrelated procedures. Large catch-all packages are hard to grant privileges on, test, and manage state for.

## 6. Naming Variables, Parameters, and Constants

### 6.1. Prefixes for Parameters and Variables

A recognizable convention:

- p_: parameter.
- l_: local variable.
- c_: constant.
- g_: package/global variable.
- r_: record variable.
- t_: collection/type, if the project uses this convention.
- e_: exception variable.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE update_order_status (
    p_order_id IN orders.order_id%TYPE,
    p_status   IN orders.status%TYPE
)
IS
    l_updated_at TIMESTAMP;
BEGIN
    l_updated_at := SYSTIMESTAMP;

    UPDATE orders
    SET status = p_status,
        updated_at = l_updated_at
    WHERE order_id = p_order_id;
END update_order_status;
/
~~~

Readers can tell parameters and local variables apart right at the point of use.

### 6.2. Parameter Modes

PL/SQL supports:

- IN: reads the passed-in value only; this is the default mode.
- OUT: returns a value to the caller.
- IN OUT: receives an input value and returns a modified value.

Declaring the mode explicitly makes APIs easier to read:

~~~sql
PROCEDURE calculate_invoice (
    p_invoice_id IN  invoices.invoice_id%TYPE,
    p_total      OUT invoices.total_amount%TYPE
);
~~~

Do not use OUT or IN OUT just to avoid a return value. Design interfaces so callers clearly see what is input, what is output, and how error states are communicated.

### 6.3. Constants Instead of Magic Numbers

~~~sql
DECLARE
    c_max_retry_count CONSTANT PLS_INTEGER := 5;
BEGIN
    IF l_retry_count > c_max_retry_count THEN
        ...
    END IF;
END;
/
~~~

Constants clarify the meaning of a value and centralize policy changes in one place. If a value is an operational setting, store it in a configuration table or appropriate configuration mechanism instead of compiling it into code.

### 6.4. Using Subtypes to Express Value Domains

~~~sql
DECLARE
    SUBTYPE t_order_id IS orders.order_id%TYPE;
    l_order_id t_order_id;
BEGIN
    ...
END;
/
~~~

A subtype does not create a completely new datatype; it creates a named subtype of a base type and can constrain precision/range per its declaration.

### 6.5. Avoid Variable Names Identical to Column Names

Parameter names matching column names can make SQL statements ambiguous:

~~~sql
-- Prone to confusion
PROCEDURE find_order (order_id IN NUMBER) IS
BEGIN
    SELECT ...
    FROM orders
    WHERE order_id = order_id;
END;
~~~

The predicate order_id = order_id does not clearly indicate whether the column or the variable is referenced. Use prefixes:

~~~sql
PROCEDURE find_order (p_order_id IN orders.order_id%TYPE) IS
BEGIN
    SELECT order_id
    INTO l_order_id
    FROM orders o
    WHERE o.order_id = p_order_id;
END;
~~~

Always qualify columns with table aliases in multi-table queries or whenever a name might collide with a PL/SQL identifier.

## 7. Using %TYPE and %ROWTYPE to Reduce Datatype Coupling

### 7.1. %TYPE

%TYPE declares a variable with a type compatible with another column or variable:

~~~sql
DECLARE
    l_employee_id employees.employee_id%TYPE;
    l_salary      employees.salary%TYPE;
BEGIN
    ...
END;
/
~~~

If the column's data type changes, %TYPE-based declarations synchronize when the program unit is recompiled. This reduces the risk of a local variable using NUMBER(8) after a column has grown to NUMBER(12).

### 7.2. %ROWTYPE

%ROWTYPE declares a record whose structure corresponds to a table or cursor row:

~~~sql
DECLARE
    l_employee employees%ROWTYPE;
BEGIN
    SELECT *
    INTO l_employee
    FROM employees
    WHERE employee_id = 100;

    DBMS_OUTPUT.PUT_LINE(l_employee.last_name);
END;
/
~~~

%ROWTYPE is convenient when fetching an entire row. If only a few columns are needed, declaring a custom record or individual variables usually makes dependencies clearer and avoids pulling unneeded data.

### 7.3. Anchor to the Schema Instead of Guessing Lengths

Instead of declaring VARCHAR2(100) for an email, if the column is already defined, use customers.email%TYPE. This prevents length mismatches between code and schema. However, %TYPE does not automatically replace business validation; data must still be validated against domain rules.

## 8. Organizing the DECLARE Section

The declarative section should be grouped by purpose so readers can find items quickly:

1. Constants and subtypes/types.
2. Cursor declarations.
3. Exceptions.
4. Variables and records.
5. Collection variables.

Example:

~~~sql
DECLARE
    -- Constants and types
    c_batch_size CONSTANT PLS_INTEGER := 500;
    SUBTYPE t_order_id IS orders.order_id%TYPE;

    -- Exceptions
    e_order_not_found EXCEPTION;

    -- Variables
    l_order_id    t_order_id;
    l_order_total orders.total_amount%TYPE;
    l_processed   PLS_INTEGER := 0;
BEGIN
    ...
END;
/
~~~

You do not have to follow this exact order strictly, but keep one consistent order across the project.

Unassigned PL/SQL variables start with NULL. If logic requires a default value, initialize it immediately:

~~~sql
l_processed_count PLS_INTEGER := 0;
l_started_at      TIMESTAMP := SYSTIMESTAMP;
~~~

For variables that must always hold a value, you can use NOT NULL with an initializer:

~~~sql
l_batch_size PLS_INTEGER NOT NULL := 500;
~~~

A NOT NULL variable must be initialized; it cannot be left NULL. Do not declare unused variables, and do not use package globals in place of parameters without an explicit state requirement.

## 9. Organizing the BEGIN Section: A Clear Execution Flow

The executable section should clearly reflect the business steps:

1. Validate inputs.
2. Read required data.
3. Check business conditions.
4. Apply changes.
5. Return results or finish.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE approve_order (
    p_order_id IN orders.order_id%TYPE,
    p_user_id  IN orders.approved_by%TYPE
)
IS
    l_status orders.status%TYPE;
BEGIN
    IF p_order_id IS NULL THEN
        RAISE_APPLICATION_ERROR(-20001, 'Order ID is required');
    END IF;

    SELECT status
    INTO l_status
    FROM orders
    WHERE order_id = p_order_id;

    IF l_status <> 'PENDING' THEN
        RAISE_APPLICATION_ERROR(-20002, 'Order is not pending');
    END IF;

    UPDATE orders
    SET status = 'APPROVED',
        approved_by = p_user_id,
        approved_at = SYSTIMESTAMP
    WHERE order_id = p_order_id;
END approve_order;
/
~~~

This snippet illustrates the sequence of validate, read, and update. In a multi-session system, add locking or a conditional UPDATE to protect state between SELECT and UPDATE; this example focuses on block organization.

### 9.1. Use Aliases and Explicit Column Lists

~~~sql
SELECT o.order_id,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.status = p_status;
~~~

In application code, avoid SELECT * if only a subset of columns is needed. An explicit column list reduces sensitivity to schema changes and makes intent clearer. %ROWTYPE is a reasonable exception when the full row is genuinely needed.

### 9.2. Use SQL%ROWCOUNT

After DML, check the affected row count when business logic depends on the outcome:

~~~sql
UPDATE orders
SET status = 'CANCELLED'
WHERE order_id = p_order_id
  AND status = 'PENDING';

IF SQL%ROWCOUNT = 0 THEN
    RAISE_APPLICATION_ERROR(-20003, 'Order not found or not pending');
END IF;
~~~

SQL%ROWCOUNT is an implicit cursor attribute of the most recent SQL statement in the current session. Read it immediately after the statement being checked; another SQL statement will overwrite the implicit cursor attributes.

## 10. Organizing Nested Blocks and Scope

Nested blocks limit variable scope and isolate local exception handling:

~~~sql
DECLARE
    l_total PLS_INTEGER := 0;
BEGIN
    DECLARE
        l_department_count PLS_INTEGER;
    BEGIN
        SELECT COUNT(*)
        INTO l_department_count
        FROM departments;

        l_total := l_department_count;
    END;

    DBMS_OUTPUT.PUT_LINE('Total: ' || l_total);
END;
/
~~~

l_department_count exists only inside the nested block. After the inner block's END, the variable is out of scope.

- Variables declared in an outer block can be referenced by inner blocks.
- Variables declared in an inner block cannot be referenced by outer blocks.
- If two blocks declare identifiers with the same name, the inner identifier shadows the outer identifier.

Avoid shadowing when it obscures which variable is being used. You can label blocks:

~~~sql
<<order_processing>>
DECLARE
    l_order_id NUMBER := 100;
BEGIN
    DECLARE
        l_order_id NUMBER := 200;
    BEGIN
        DBMS_OUTPUT.PUT_LINE(order_processing.l_order_id);
        DBMS_OUTPUT.PUT_LINE(l_order_id);
    END;
END order_processing;
/
~~~

Labels let you qualify an outer block's shadowed identifier. Still, avoiding duplicate names across nested scopes is usually cleaner.

Use nested blocks when a small operation needs its own exception handler, a group of variables only needs a short lifetime, or a section of logic needs isolated scope. Do not nest too deeply; if a block is long and has an independent responsibility, extracting a private procedure/function is usually more maintainable.

## 11. Responsible Exception Handling

The EXCEPTION section is part of the behavioral contract. It should clarify which errors are handled locally, which are propagated to the caller, and what state the transaction remains in.

### 11.1. Catch Specific Exceptions

~~~sql
BEGIN
    SELECT salary
    INTO l_salary
    FROM employees
    WHERE employee_id = p_employee_id;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(-20010, 'Employee not found');
    WHEN TOO_MANY_ROWS THEN
        RAISE_APPLICATION_ERROR(-20011, 'Employee key is not unique');
END;
~~~

Common predefined exceptions:

| Exception | Meaning |
| --- | --- |
| NO_DATA_FOUND | SELECT INTO returned no rows |
| TOO_MANY_ROWS | SELECT INTO returned more than one row |
| ZERO_DIVIDE | Division by zero |
| DUP_VAL_ON_INDEX | Unique index/constraint violation |
| INVALID_NUMBER | Invalid string-to-number conversion |
| VALUE_ERROR | Conversion or value bounds error |
| CURSOR_ALREADY_OPEN | Opening an already-open cursor |
| INVALID_CURSOR | Invalid cursor operation |

### 11.2. WHEN OTHERS Must Be Used Carefully

Do not write:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        NULL;
END;
~~~

This swallows errors. The caller may believe the operation succeeded even though the data was never processed.

If you need a catch-all to log an error before re-raising:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        log_error(
            p_module  => 'APPROVE_ORDER',
            p_code    => SQLCODE,
            p_message => SQLERRM
        );
        RAISE;
END;
~~~

RAISE inside a handler re-raises the current exception and preserves error context. If there is no business reason to handle an exception, letting it propagate naturally to the caller is also a clean choice.

### 11.3. Defining Custom Exceptions

~~~sql
DECLARE
    e_invalid_order_state EXCEPTION;
BEGIN
    IF l_status NOT IN ('PENDING', 'APPROVED') THEN
        RAISE e_invalid_order_state;
    END IF;
EXCEPTION
    WHEN e_invalid_order_state THEN
        RAISE_APPLICATION_ERROR(-20020, 'Invalid order state');
END;
/
~~~

### 11.4. Mapping Oracle Errors with PRAGMA EXCEPTION_INIT

~~~sql
DECLARE
    e_resource_busy EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_resource_busy, -54);
BEGIN
    ...
EXCEPTION
    WHEN e_resource_busy THEN
        RAISE_APPLICATION_ERROR(-20030, 'Resource is busy; retry later');
END;
/
~~~

Error codes should be taken from Oracle documentation and actual scenarios. Do not use custom exception names to obscure the underlying error that callers need to know.

### 11.5. RAISE_APPLICATION_ERROR

RAISE_APPLICATION_ERROR returns business errors in the code range -20000 to -20999:

~~~sql
RAISE_APPLICATION_ERROR(-20001, 'Order ID is required');
~~~

Messages should clearly state the unmet condition, contain no passwords/tokens/sensitive data, use stable error codes for application recognition, and avoid collapsing all technical failures into a single generic message.

### 11.6. Preserving Original Error Information

When logging errors, you can use SQLCODE, SQLERRM, DBMS_UTILITY.FORMAT_ERROR_STACK, DBMS_UTILITY.FORMAT_ERROR_BACKTRACE, and DBMS_UTILITY.FORMAT_CALL_STACK.

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        log_error(
            p_code      => SQLCODE,
            p_message   => DBMS_UTILITY.FORMAT_ERROR_STACK,
            p_backtrace => DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END;
~~~

FORMAT_ERROR_BACKTRACE pinpoints the line where the exception originated, even when caught in a different block. Logging routines must be designed not to mask the original error.

## 12. Transactions and COMMIT in PL/SQL

An important design decision is whether a procedure commits on its own or leaves transaction management to the caller.

### 12.1. Avoid Arbitrary COMMITs in Business Procedures

Hard-to-compose example:

~~~sql
PROCEDURE update_order IS
BEGIN
    UPDATE orders ...;
    COMMIT;
END;
~~~

If the caller wants to update ORDER, PAYMENT, and INVENTORY in the same transaction, a COMMIT inside UPDATE_ORDER breaks the caller's intended transaction boundary.

A common convention:

- Business procedures perform DML without committing themselves.
- The service layer or caller decides COMMIT/ROLLBACK once the entire use case succeeds or fails.
- Batch jobs may manage commits per batch if that is an explicit, documented design requirement.

There is no rigid rule banning COMMIT from every procedure; what matters is clear transaction ownership.

### 12.2. Exceptions Do Not Automatically Roll Back the Whole Transaction

When an exception occurs, Oracle does not automatically roll back all prior changes in the transaction. The caller can decide to ROLLBACK the whole transaction or handle partial rollback with savepoints.

~~~sql
SAVEPOINT before_order_update;

BEGIN
    UPDATE orders
    SET status = 'APPROVED'
    WHERE order_id = p_order_id;

    UPDATE inventory
    SET reserved_quantity = reserved_quantity + 1
    WHERE product_id = p_product_id;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO before_order_update;
        RAISE;
END;
~~~

Savepoints let you undo work after the marker while preserving earlier changes in the transaction. Use them only when business semantics allow it.

### 12.3. Autonomous Transactions for Logging

PRAGMA AUTONOMOUS_TRANSACTION creates a transaction independent of the calling transaction. It can be useful when persisting error logs even if the business transaction rolls back:

~~~sql
CREATE OR REPLACE PROCEDURE log_error (
    p_message IN VARCHAR2
)
IS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO application_error_log(message, logged_at)
    VALUES (p_message, SYSTIMESTAMP);

    COMMIT;
END log_error;
/
~~~

Autonomous transactions commit/roll back independently; logs survive even when the business transaction rolls back. Do not access rows locked by the parent transaction in a way that causes deadlocks/waits, and do not use autonomous transactions to bypass proper transaction design.

## 13. Modularizing into Procedures, Functions, and Packages

### 13.1. Give Each Routine One Primary Responsibility

A procedure thousands of lines long is hard to test. You can decompose the flow:

~~~text
PROCESS_ORDER
  |
  +-- VALIDATE_ORDER
  |
  +-- CALCULATE_ORDER_TOTAL
  |
  +-- RESERVE_INVENTORY
  |
  +-- WRITE_ORDER_AUDIT
~~~

Each routine has clear inputs, outputs, and side effects. Do not split into dozens of one-line procedures if doing so makes the execution flow harder to follow.

### 13.2. Package Specifications Are APIs

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    PROCEDURE approve_order (
        p_order_id IN orders.order_id%TYPE,
        p_user_id  IN orders.approved_by%TYPE
    );

    FUNCTION get_order_total (
        p_order_id IN orders.order_id%TYPE
    ) RETURN NUMBER;
END order_api;
/
~~~

Private helpers live in the package body:

~~~sql
CREATE OR REPLACE PACKAGE BODY order_api AS
    PROCEDURE validate_order_state (
        p_order_id IN orders.order_id%TYPE
    ) IS
        l_status orders.status%TYPE;
    BEGIN
        SELECT status
        INTO l_status
        FROM orders
        WHERE order_id = p_order_id;

        IF l_status <> 'PENDING' THEN
            RAISE_APPLICATION_ERROR(-20040, 'Order is not pending');
        END IF;
    END validate_order_state;

    PROCEDURE approve_order (
        p_order_id IN orders.order_id%TYPE,
        p_user_id  IN orders.approved_by%TYPE
    ) IS
    BEGIN
        validate_order_state(p_order_id);

        UPDATE orders
        SET status = 'APPROVED',
            approved_by = p_user_id,
            approved_at = SYSTIMESTAMP
        WHERE order_id = p_order_id;
    END approve_order;

    FUNCTION get_order_total (
        p_order_id IN orders.order_id%TYPE
    ) RETURN NUMBER IS
        l_total orders.total_amount%TYPE;
    BEGIN
        SELECT total_amount
        INTO l_total
        FROM orders
        WHERE order_id = p_order_id;

        RETURN l_total;
    END get_order_total;
END order_api;
/
~~~

Callers see only the two public APIs; VALIDATE_ORDER_STATE stays private in the body.

### 13.3. Limit Package State

Variables declared in a package specification or body can persist for the life of a session (package state). This can cause elusive bugs with connection pools because a subsequent request may reuse the same database session.

If state is needed, clearly define when it is initialized and reset; avoid holding sensitive data longer than necessary; do not assume every request gets a fresh session; consider package initialization sections and DBMS_SESSION.RESET_PACKAGE when required by the architecture.

Prefer parameters and configuration tables when data must persist cleanly across calls or sessions.

### 13.4. Separate Queries from Business Rules When Practical

You can create private helpers for reading data, checking state, calculating values, or writing audits. However, you do not need to wrap a trivial SELECT in its own function if doing so adds neither reuse nor clarity.

## 14. Cursors and Dataset Processing

### 14.1. Cursor FOR Loops

A cursor FOR loop manages OPEN, FETCH, and CLOSE automatically:

~~~sql
BEGIN
    FOR r_order IN (
        SELECT order_id, status
        FROM orders
        WHERE status = 'PENDING'
        ORDER BY order_id
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(
            r_order.order_id || ': ' || r_order.status
        );
    END LOOP;
END;
/
~~~

This is usually the shortest, safest option for iterating over query results. There is no need to declare an explicit cursor unless special lifecycle control is required.

### 14.2. Explicit Cursors

~~~sql
DECLARE
    CURSOR c_orders (p_status VARCHAR2) IS
        SELECT order_id, status
        FROM orders
        WHERE status = p_status;
BEGIN
    FOR r_order IN c_orders('PENDING') LOOP
        DBMS_OUTPUT.PUT_LINE(r_order.order_id);
    END LOOP;
END;
/
~~~

Use explicit cursors when you need parameters, explicit OPEN/FETCH/CLOSE control, FOR UPDATE/WHERE CURRENT OF, or cursor attribute inspection. A cursor FOR loop over an explicit cursor still manages the cursor lifecycle automatically.

### 14.3. Avoid Row-by-Row When Set-Based SQL Works

Instead of:

~~~sql
FOR r_order IN (
    SELECT order_id
    FROM orders
    WHERE status = 'EXPIRED'
) LOOP
    UPDATE orders
    SET status = 'CLOSED'
    WHERE order_id = r_order.order_id;
END LOOP;
~~~

You can write a single SQL statement:

~~~sql
UPDATE orders
SET status = 'CLOSED'
WHERE status = 'EXPIRED';
~~~

Set-based SQL is usually faster because Oracle processes multiple rows in one statement. Use a PL/SQL loop when each row genuinely requires distinct logic or individual API calls/side effects.

### 14.4. BULK COLLECT and FORALL

When data must be processed in PL/SQL and you want to reduce round-trips between the SQL engine and PL/SQL engine, use BULK COLLECT and FORALL:

~~~sql
DECLARE
    TYPE t_order_ids IS TABLE OF orders.order_id%TYPE;
    l_order_ids t_order_ids;
BEGIN
    SELECT order_id
    BULK COLLECT INTO l_order_ids
    FROM orders
    WHERE status = 'EXPIRED';

    FORALL i IN 1 .. l_order_ids.COUNT
        UPDATE orders
        SET status = 'CLOSED'
        WHERE order_id = l_order_ids(i);
END;
/
~~~

For large datasets, use BULK COLLECT ... LIMIT to bound memory and process in batches. FORALL is bulk binding, not a regular PL/SQL loop.

## 15. Dynamic SQL and SQL Injection Protection

### 15.1. Prefer Static SQL

When table/column names and statement structure are known at compile time, use static SQL:

~~~sql
SELECT salary
INTO l_salary
FROM employees
WHERE employee_id = p_employee_id;
~~~

Static SQL is syntax-checked and dependency-tracked at compile time, making it easier to read and optimize.

### 15.2. When Is Dynamic SQL Needed?

Use dynamic SQL when statement structure genuinely changes at runtime, such as selecting a table name from an allowlist or generating DDL from metadata.

~~~sql
DECLARE
    l_sql VARCHAR2(1000);
    l_count PLS_INTEGER;
BEGIN
    l_sql := 'SELECT COUNT(*) FROM employees WHERE department_id = :dept_id';

    EXECUTE IMMEDIATE l_sql
        INTO l_count
        USING p_department_id;
END;
/
~~~

Data values must be passed via bind variables. Never concatenate user input into SQL strings:

~~~sql
-- Unsafe
l_sql := 'SELECT * FROM employees WHERE last_name = '''
         || p_last_name || '''';
~~~

### 15.3. Bind Variables Do Not Substitute Identifiers

Bind variables are for values, not table or column names. If an identifier must vary, use an allowlist and appropriate DBMS_ASSERT checks:

~~~sql
l_table_name := DBMS_ASSERT.SIMPLE_SQL_NAME(p_table_name);
l_sql := 'SELECT COUNT(*) FROM ' || l_table_name;
EXECUTE IMMEDIATE l_sql INTO l_count;
~~~

DBMS_ASSERT validates identifier syntax, but it does not replace a business allowlist. A syntactically valid name can still be an object the caller is not permitted to query. Verify against an allowed table list before executing.

## 16. Comments and Documentation

Comments should explain why or state business rules that the code cannot express directly.

### 16.1. Useful Comments

~~~sql
-- Keep the last 90 days online because the reconciliation team
-- must compare current transactions with recent settlement files.
~~~

This comment explains the rationale behind the 90-day retention rule.

### 16.2. Unhelpful Comments

~~~sql
-- Increase retry count by one
l_retry_count := l_retry_count + 1;
~~~

Comments that merely restate the code quickly become noise.

### 16.3. Headers for Long-Lived Modules

~~~sql
/*
  Module : ORDER_API
  Purpose: Public operations for order lifecycle.
  Owner  : Data Applications
  Notes  : Caller owns the transaction; routines do not COMMIT.
*/
~~~

Avoid putting long change logs in file headers when your project uses source control. Git history and pull requests are better suited for tracking who changed what.

### 16.4. Documenting APIs

Package specifications should include comments describing what each routine does, parameter meanings, preconditions, side effects, potential exceptions, and transaction ownership.

~~~sql
/*
  Approves a pending order.
  The caller owns COMMIT/ROLLBACK.
  Raises -20001 when the order does not exist.
*/
PROCEDURE approve_order (
    p_order_id IN orders.order_id%TYPE,
    p_user_id  IN orders.approved_by%TYPE
);
~~~

An outdated comment is worse than no comment because it misleads maintainers. When changing conditions or business rules, update documentation, variable names, tests, and related comments together.

## 17. Formatting Conventions for Quick Reading

A consistent style should specify:

- 2 or 4 spaces indentation, without mixing tabs and spaces.
- Uppercase SQL keywords or a consistent casing style.
- One parameter per line when parameter lists are long.
- Clear placement of IS/AS, BEGIN, EXCEPTION, END.
- Splitting long predicates across multiple lines.
- Including END labels where helpful.
- Never putting multiple statements on a single line.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE transfer_balance (
    p_source_account_id IN account_balance.account_id%TYPE,
    p_target_account_id IN account_balance.account_id%TYPE,
    p_amount             IN account_balance.balance%TYPE
)
IS
    l_source_balance account_balance.balance%TYPE;
BEGIN
    IF p_amount <= 0 THEN
        RAISE_APPLICATION_ERROR(-20050, 'Amount must be positive');
    END IF;

    SELECT balance
    INTO l_source_balance
    FROM account_balance
    WHERE account_id = p_source_account_id
    FOR UPDATE;

    IF l_source_balance < p_amount THEN
        RAISE_APPLICATION_ERROR(-20051, 'Insufficient balance');
    END IF;

    UPDATE account_balance
    SET balance = balance - p_amount
    WHERE account_id = p_source_account_id;

    UPDATE account_balance
    SET balance = balance + p_amount
    WHERE account_id = p_target_account_id;
END transfer_balance;
/
~~~

This example illustrates formatting, not a complete money-transfer API: a production implementation must lock both accounts in a consistent order, verify target existence, validate currency/precision, and let the caller manage transactions.

## 18. Logging and Observability in Operations

### 18.1. DBMS_OUTPUT Is Only for Development

DBMS_OUTPUT.PUT_LINE is useful in labs and manual debugging. Production applications should not rely on DBMS_OUTPUT as their primary logging mechanism because output requires a client to enable and read it, rather than providing centralized logging.

### 18.2. DBMS_APPLICATION_INFO

You can tag module/action so DBAs can observe sessions:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_BATCH',
        action_name => 'CLOSE_EXPIRED'
    );

    -- Business work

    DBMS_APPLICATION_INFO.SET_ACTION(NULL);
    DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
END;
/
~~~

Module and action help trace workloads in session views and monitoring tools. Reset the context upon completion, especially when sessions are reused in connection pools.

### 18.3. Structured Logging

A useful error log can capture timestamp, module/action, application request ID or correlation ID, SQLCODE, error stack/backtrace, non-sensitive business keys, and the user/service account per audit policy.

Do not log passwords, access tokens, card numbers, or personal data beyond what is strictly needed.

## 19. Compile Warnings and Supporting Tools

### 19.1. Checking Compile Errors

~~~sql
SHOW ERRORS PROCEDURE approve_order;
~~~

Or:

~~~sql
SELECT line, position, text
FROM user_errors
WHERE name = 'APPROVE_ORDER'
  AND type = 'PROCEDURE'
ORDER BY sequence;
~~~

### 19.2. Enabling PL/SQL Warnings

~~~sql
ALTER SESSION SET PLSQL_WARNINGS = 'ENABLE:ALL';
~~~

After compiling, inspect USER_ERRORS or ALL_ERRORS for warnings. Some warnings flag unreachable code, unused variables, or constructs that can lead to bugs. Not every warning is a defect, but each should be reviewed rather than ignored by default.

### 19.3. PL/Scope

PL/Scope collects metadata about identifiers and SQL statements in PL/SQL source code, supporting source-level usage and dependency analysis.

~~~sql
ALTER SESSION SET PLSCOPE_SETTINGS = 'IDENTIFIERS:ALL, STATEMENTS:ALL';
~~~

Then recompile the program unit and query the corresponding dictionary views such as USER_IDENTIFIERS or USER_STATEMENTS where supported by version and privileges. PL/Scope does not replace runtime testing or business logic review.

## 20. Complete Example: A Well-Organized Order Processing Package

The example below combines naming, package APIs, %TYPE, validation, conditional DML, and exception handling. Table names are assumed to exist.

### 20.1. Package Specification

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    /*
      Approves an order in PENDING state.
      Caller owns transaction control.
    */
    PROCEDURE approve_order (
        p_order_id IN orders.order_id%TYPE,
        p_user_id  IN orders.approved_by%TYPE
    );

    FUNCTION get_order_total (
        p_order_id IN orders.order_id%TYPE
    ) RETURN orders.total_amount%TYPE;
END order_api;
/
~~~

### 20.2. Package Body

~~~sql
CREATE OR REPLACE PACKAGE BODY order_api AS
    c_order_pending  CONSTANT orders.status%TYPE := 'PENDING';
    c_order_approved CONSTANT orders.status%TYPE := 'APPROVED';

    PROCEDURE approve_order (
        p_order_id IN orders.order_id%TYPE,
        p_user_id  IN orders.approved_by%TYPE
    ) IS
    BEGIN
        IF p_order_id IS NULL THEN
            RAISE_APPLICATION_ERROR(-20060, 'Order ID is required');
        END IF;

        UPDATE orders
        SET status = c_order_approved,
            approved_by = p_user_id,
            approved_at = SYSTIMESTAMP
        WHERE order_id = p_order_id
          AND status = c_order_pending;

        IF SQL%ROWCOUNT = 0 THEN
            DECLARE
                l_exists PLS_INTEGER;
            BEGIN
                SELECT COUNT(*)
                INTO l_exists
                FROM orders
                WHERE order_id = p_order_id;

                IF l_exists = 0 THEN
                    RAISE_APPLICATION_ERROR(-20061, 'Order not found');
                ELSE
                    RAISE_APPLICATION_ERROR(-20062, 'Order is not pending');
                END IF;
            END;
        END IF;
    END approve_order;

    FUNCTION get_order_total (
        p_order_id IN orders.order_id%TYPE
    ) RETURN orders.total_amount%TYPE IS
        l_total orders.total_amount%TYPE;
    BEGIN
        SELECT total_amount
        INTO l_total
        FROM orders
        WHERE order_id = p_order_id;

        RETURN l_total;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(-20063, 'Order not found');
    END get_order_total;
END order_api;
/
~~~

### 20.3. Calling the Package

~~~sql
BEGIN
    order_api.approve_order(
        p_order_id => 1001,
        p_user_id  => 501
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

The caller owns the transaction. If approval fails, the caller rolls back and propagates the error upward. In real applications, avoid returning raw technical stacks directly to end users; the service layer can map error codes to user-friendly messages while keeping diagnostic details in logs.

This package example focuses on code organization. When state contention exists, an UPDATE with predicate status = 'PENDING' makes the state transition atomic and conditional. If you need to distinguish non-existence from invalid state accurately under high concurrency, design response semantics and locking per business requirements.

## 21. Common Anti-Patterns

| Anti-Pattern | Problem | Improvement |
| --- | --- | --- |
| Variables named x, a1, tmp2 for business data | Intent unclear when reading code | Use domain-meaningful names |
| Parameters and columns with the same name | SQL easily references the wrong identifier | Use p_ prefixes and table aliases |
| One procedure doing everything | Hard to test and modify | Split by responsibility |
| WHEN OTHERS THEN NULL | Swallows errors | Catch specific errors or log and RAISE |
| COMMIT inside helper procedures | Caller loses transaction control | Clarify transaction ownership |
| SELECT * everywhere | Schema coupling and fetches unneeded data | Select only required columns |
| Row-by-row UPDATE | High context-switch and round-trip cost | Use set-based SQL or FORALL |
| Concatenating input into dynamic SQL | SQL injection | Bind values, allowlist identifiers |
| Unreset package global state | Later requests reuse stale state | Use parameters or intentional resets |
| Comments repeating every line of code | Noise and quickly goes stale | Explain rationale and rules |
| DBMS_OUTPUT as production logging | No durable/centralized log | Structured logging table/service |
| Giant COMMON package | API lacks cohesion | Split packages by domain |
| Routine name hides side effects | Callers unaware data is modified | Name actions clearly and document transactions |

## 22. Workflow for Writing and Modifying a PL/SQL Module

A practical workflow may include:

1. Review the relevant schema and business contracts.
2. Define the public API and input/output data.
3. Choose names following project conventions.
4. Declare %TYPE, constants, and required exceptions.
5. Write a concise flow with explicit conditions.
6. Establish transaction ownership and rollback rules.
7. Handle specific exceptions; never swallow errors.
8. Use static SQL and bind variables whenever dynamic SQL is needed.
9. Compile with appropriate warnings enabled.
10. Test success, boundary, no-data, duplicate, and system-error cases.
11. Document side effects, required privileges, and transaction behavior.
12. Deploy via source control and repeatable migration scripts per project workflow.

## 23. Checklist for Reading and Maintaining PL/SQL Code

1. **Do names state intent clearly?** Procedures are actions; functions describe results; variables reflect domain concepts.
2. **Are parameters easy to distinguish?** Use prefixes or a consistent convention.
3. **Do any names collide with columns?** Qualify columns with aliases and name parameters clearly.
4. **Are data types anchored to the schema?** Prefer %TYPE/%ROWTYPE when appropriate.
5. **Are variables initialized properly?** Remember unassigned variables hold NULL.
6. **Are DECLARE, BEGIN, and EXCEPTION cleanly separated?** Use nested blocks purposefully.
7. **Does each routine have one main responsibility?** Extract helpers when they clarify flow.
8. **Can the SQL be set-based?** Avoid row-by-row loops when one SQL statement suffices.
9. **Is dynamic SQL safe?** Bind values and allowlist identifiers.
10. **Are exceptions swallowed?** WHEN OTHERS must handle errors intentionally.
11. **Who owns the transaction?** Avoid arbitrary COMMITs in helpers.
12. **Does logging preserve the original error?** Record backtraces and avoid sensitive data.
13. **Is package state controlled?** Especially under connection pooling.
14. **Do comments explain why?** Update them when logic changes.
15. **Have compile warnings and tests been checked?** Verify both success and failure paths.

## 24. Self-Check Questions

**Question 1.** What sections does a PL/SQL block have? Which ones are mandatory?

**Question 2.** Are DECLARE and EXCEPTION mandatory?

**Question 3.** Is the forward slash after END; PL/SQL syntax or a SQL*Plus/SQLcl command?

**Question 4.** Why should you avoid quoted identifiers unless specifically required?

**Question 5.** What do the prefixes p_, l_, and c_ mean?

**Question 6.** How do IN, OUT, and IN OUT differ?

**Question 7.** What kind of coupling do %TYPE and %ROWTYPE help reduce?

**Question 8.** Why is WHERE order_id = order_id prone to design bugs?

**Question 9.** How do nested blocks affect variable scope?

**Question 10.** Why should you never write WHEN OTHERS THEN NULL?

**Question 11.** How does RAISE differ from RAISE_APPLICATION_ERROR?

**Question 12.** Why do helper procedures typically avoid calling COMMIT on their own?

**Question 13.** When should you use a package specification vs. a package body?

**Question 14.** Why can package global state cause bugs with connection pools?

**Question 15.** When should you use BULK COLLECT and FORALL?

**Question 16.** Why does dynamic SQL require bind variables and identifier allowlists?

**Question 17.** What should good comments explain?

**Question 18.** How do PL/SQL warnings and PL/Scope support maintenance?

<details>
<summary>Answer Hints</summary>

1. DECLARE (optional), BEGIN (mandatory), EXCEPTION (optional), END (mandatory).
2. No. DECLARE and EXCEPTION are optional.
3. It is a client tool command to send the buffer; not a PL/SQL statement.
4. Because quoted identifiers are case-sensitive and cause friction when referencing or integrating.
5. Parameter, local variable, and constant by convention.
6. IN receives input; OUT returns output; IN OUT receives and returns a value.
7. Reduces duplicating types/lengths tied to table columns or row structures.
8. Unclear whether either side is a column or a PL/SQL variable; can become an always-true predicate or behave contrary to intent.
9. Variables in a block are visible only within that block and inner nested blocks; outer blocks cannot see inner variables.
10. Because it hides errors and makes callers think the operation succeeded.
11. RAISE re-raises the current exception or raises a declared exception; RAISE_APPLICATION_ERROR raises an application error in the -20000 to -20999 range.
12. Because the caller needs to control transactions spanning multiple business operations.
13. Specification publishes the API; body implements the API and holds private helpers.
14. Sessions are reused, so state from an earlier request can persist into a later request.
15. When data must be processed in PL/SQL and you want to reduce context switches and process in batches.
16. Binds protect values and improve cursor reuse; identifiers cannot be bound, so they must be validated and restricted via an allowlist.
17. Business rationale, design decisions, side effects, or preconditions not obvious from code alone.
18. Warnings alert you to compile-time issues; PL/Scope provides identifier/statement metadata for source analysis.

</details>

## 25. Official Oracle Documentation

1. [Oracle Database 19c PL/SQL Language Reference — PL/SQL Language Fundamentals](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-language-fundamentals.html): block structure, lexical units, declarations, scope, and identifiers.
2. [Oracle Database 19c PL/SQL Language Reference — PL/SQL Collections and Records](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-collections-and-records.html): records, collections, and organizing data in PL/SQL.
3. [Oracle Database 19c PL/SQL Language Reference — Error Handling](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-error-handling.html): exceptions, propagation, and exception handlers.
4. [Oracle Database 19c PL/SQL Language Reference — Subprograms](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-subprograms.html): procedures, functions, parameter modes, and subprogram design.
5. [Oracle Database 19c PL/SQL Language Reference — Packages](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-packages.html): package specifications, bodies, initialization, and package state.
6. [Oracle Database 19c PL/SQL Language Reference — Static SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/static-sql.html): SQL statements in PL/SQL.
7. [Oracle Database 19c PL/SQL Language Reference — Native Dynamic SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/native-dynamic-sql.html): EXECUTE IMMEDIATE, bind variables, and dynamic SQL.
8. [Oracle Database 19c PL/SQL Language Reference — Bulk SQL and Bulk Binding](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/bulk-sql-and-bulk-binding.html): BULK COLLECT and FORALL.
9. [Oracle Database 19c PL/SQL Language Reference — Conditional Compilation and Warnings](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/conditional-compilation1.html): compiler settings and PL/SQL warnings.
10. [Oracle Database 19c PL/SQL Language Reference — PL/Scope](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plscope.html): collecting source code metadata for identifier and statement analysis.
11. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_APPLICATION_INFO](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_APPLICATION_INFO.html): tagging module/action for session monitoring.
12. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_ASSERT](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_ASSERT.html): validating SQL object names and identifiers in dynamic SQL.

**Principle to remember:** Name identifiers so readers understand the role of data and actions; organize each block into clear declaration, execution, and error-handling sections; separate routines by responsibility; use %TYPE/%ROWTYPE, static SQL, and bind variables where appropriate; never swallow exceptions and never leave transaction ownership ambiguous. A convention has value only when the whole team applies it consistently and updates it alongside code when business rules change.
