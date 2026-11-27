# Predefined Exceptions, User-Defined Exceptions, and PRAGMA EXCEPTION_INIT in PL/SQL

PL/SQL uses exceptions to signal and handle abnormal situations during execution. A `SELECT INTO` statement that finds no rows, division by zero, a unique constraint violation, or an invalid business rule can all transfer control to an exception handler.

Oracle provides **predefined exceptions** for common errors. When you need to describe an application-specific situation, developers can declare a **user-defined exception** and explicitly raise it. When an Oracle error has a specific ORA code but does not yet have a suitable predefined exception name in PL/SQL, **PRAGMA EXCEPTION_INIT** lets you associate that error code with an exception name so it can be handled with `WHEN`.

These three mechanisms address three different needs:

- Predefined exception: uses names Oracle has already defined for common errors.
- User-defined exception: names an abnormal condition detected by application logic.
- PRAGMA EXCEPTION_INIT: associates a declared exception with an Oracle error code so you can catch that error by a meaningful name.

In addition, `RAISE_APPLICATION_ERROR` allows returning an error code and application message in a reserved range. It must be distinguished from `RAISE` and `PRAGMA EXCEPTION_INIT` to design a consistent error contract across procedures, triggers, and calling applications.

## 1. What Is an Exception?

An exception is an abnormal event that causes PL/SQL to leave the sequential execution flow at the point where the error occurs and search for a matching handler. If the current block has no matching handler, the exception propagates to the calling block or calling environment.

A PL/SQL block has three sections:

~~~sql
DECLARE
    -- Declare variables, cursors, exceptions, data types...
BEGIN
    -- Normal executable statements.
EXCEPTION
    -- Exception handlers.
END;
/
~~~

The `DECLARE` section is optional. The `EXCEPTION` section is also optional if the block does not need to handle errors locally.

### 1.1 Execution Flow When an Exception Occurs

~~~text
Start block
     |
     v
Run normal statements
     |
     v
Exception raised?
   /     \
  No      Yes
  |        |
  v        v
Continue  Search for matching handler
          in current block
               |
          +----+----+
          |         |
       Handler    No handler
        found       |
          |         v
          v     Propagate exception
     Run handler  to calling block
          |
          v
       End block
~~~

After a handler finishes running, PL/SQL does not return to the statement that caused the error to continue with the next statement in the executable section. Execution continues after the block that handled the exception, or the exception propagates further if the handler uses `RAISE`.

### 1.2 Exceptions vs. Return Values

A procedure can return a business status such as `NOT_FOUND` via an `OUT` parameter, or raise an exception. The two approaches have different contracts:

- Return values are suitable when the situation is a normal outcome that the caller needs to branch on.
- Exceptions are suitable when the current flow cannot continue under the defined conditions or when an error needs to propagate across multiple layers.

Exceptions should not be used as control flow for every normal branch, for example using `NO_DATA_FOUND` solely to check existence when a `SELECT COUNT` or `EXISTS` query is more appropriate.

## 2. Predefined Exceptions

Predefined exceptions are exceptions that Oracle has declared in the `STANDARD` package. They can be used directly in PL/SQL without redeclaring them.

Example:

~~~sql
BEGIN
    -- Statements that may raise an error.
    NULL;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('No data found');
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE('Query returned more than one row');
END;
/
~~~

### 2.1 Common Predefined Exceptions

| Exception Name | Common Oracle Code | Situation |
|---|---:|---|
| NO_DATA_FOUND | +100 in PL/SQL | SELECT INTO returns no rows |
| TOO_MANY_ROWS | -1422 | SELECT INTO returns more than one row |
| ZERO_DIVIDE | -1476 | Division of a number by 0 |
| DUP_VAL_ON_INDEX | -1 | INSERT/UPDATE violates a unique constraint or unique index |
| INVALID_NUMBER | -1722 | Invalid string-to-NUMBER conversion in an SQL context |
| VALUE_ERROR | -6502 | Conversion, assignment, or value-limit error in PL/SQL |
| INVALID_CURSOR | -1001 | Invalid cursor operation |
| CURSOR_ALREADY_OPEN | -6511 | Opening an explicit cursor that is already open |
| LOGIN_DENIED | -1017 | Login denied |
| NOT_LOGGED_ON | -1012 | Operation requires a logged-in session |
| TIMEOUT_ON_RESOURCE | -51 | Resource wait timeout in certain operations |

The codes in the table are the commonly associated Oracle error codes; the `SQLCODE` of some predefined exceptions follows special conventions, most notably `NO_DATA_FOUND` returning `+100`. When handling a specific ORA code, verify against the actual error raised and the Oracle version.

Other predefined exceptions include `ACCESS_INTO_NULL`, `CASE_NOT_FOUND`, `COLLECTION_IS_NULL`, `PROGRAM_ERROR`, `ROWTYPE_MISMATCH`, `SELF_IS_NULL`, `STORAGE_ERROR`, `SUBSCRIPT_BEYOND_COUNT`, `SUBSCRIPT_OUTSIDE_LIMIT`, and `SYS_INVALID_ROWID`.

### 2.2 NO_DATA_FOUND

`NO_DATA_FOUND` is raised when a `SELECT INTO` statement returns no rows:

~~~sql
DECLARE
    l_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO l_name
    FROM employees
    WHERE employee_id = -1;

    DBMS_OUTPUT.PUT_LINE(l_name);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('No matching employee found');
END;
/
~~~

`SELECT INTO` is designed to fetch exactly one row. If there are no rows, PL/SQL raises `NO_DATA_FOUND`. If there is more than one row, the error is `TOO_MANY_ROWS`.

If a not-found situation is a normal outcome, consider returning a status through an `OUT` parameter or using a cursor/other logic so the caller handles it explicitly.

### 2.3 TOO_MANY_ROWS

~~~sql
DECLARE
    l_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO l_name
    FROM employees
    WHERE department_id = 10;
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Query condition does not uniquely identify a single employee'
        );
END;
/
~~~

If the business logic requires a single row, ensure the condition uses a unique key or has a clear row-selection rule. Do not arbitrarily use `ROWNUM = 1` to hide non-unique data.

### 2.4 ZERO_DIVIDE

~~~sql
DECLARE
    l_total NUMBER := 100;
    l_count NUMBER := 0;
    l_average NUMBER;
BEGIN
    l_average := l_total / l_count;
EXCEPTION
    WHEN ZERO_DIVIDE THEN
        DBMS_OUTPUT.PUT_LINE('Cannot divide by 0');
END;
/
~~~

If the denominator can legitimately be 0 according to business rules, you can check before dividing and return an appropriate result. The exception remains useful as a safeguard against unexpected cases.

### 2.5 DUP_VAL_ON_INDEX

~~~sql
BEGIN
    INSERT INTO departments (
        department_id,
        department_name
    )
    VALUES (
        10,
        'New department'
    );
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        DBMS_OUTPUT.PUT_LINE(
            'Department ID already exists'
        );
END;
/
~~~

Do not assume by default that every duplicate error is a valid repeated request. Identify which constraint was violated, inspect the existing data, and apply the business policy.

### 2.6 VALUE_ERROR and INVALID_NUMBER

`VALUE_ERROR` is typically related to conversion or data type size limits in PL/SQL:

~~~sql
DECLARE
    l_small VARCHAR2(3);
BEGIN
    l_small := 'ORACLE';
EXCEPTION
    WHEN VALUE_ERROR THEN
        DBMS_OUTPUT.PUT_LINE('Value exceeds variable limit');
END;
/
~~~

`INVALID_NUMBER` usually occurs when an SQL expression attempts to convert an invalid string to `NUMBER`:

~~~sql
DECLARE
    l_value NUMBER;
BEGIN
    SELECT TO_NUMBER('ABC')
    INTO l_value
    FROM dual;
EXCEPTION
    WHEN INVALID_NUMBER THEN
        DBMS_OUTPUT.PUT_LINE('String is not a valid number');
END;
/
~~~

The boundary between conversion errors in SQL and PL/SQL can affect which specific exception is raised. When exact classification is needed, use the actual error code and message from the runtime environment.

## 3. Declaring and Using User-Defined Exceptions

A user-defined exception is an exception declared by the developer to describe a business condition or a custom situation.

### 3.1 Declaring an Exception

Declare it in the `DECLARE` section:

~~~sql
DECLARE
    e_invalid_amount EXCEPTION;
BEGIN
    NULL;
END;
/
~~~

An exception is scoped to the block in which it is declared. A child block can see exceptions declared in a parent block, whereas an outer block cannot see exceptions declared only locally inside a child block.

### 3.2 Raising an Exception with RAISE

~~~sql
DECLARE
    e_invalid_amount EXCEPTION;
    l_amount NUMBER := -50;
BEGIN
    IF l_amount <= 0 THEN
        RAISE e_invalid_amount;
    END IF;

    DBMS_OUTPUT.PUT_LINE('Amount is valid');
EXCEPTION
    WHEN e_invalid_amount THEN
        DBMS_OUTPUT.PUT_LINE('Amount must be greater than 0');
END;
/
~~~

`RAISE e_invalid_amount` explicitly raises the declared exception. It does not automatically create a distinct application ORA code. If a user-defined exception is not mapped with `PRAGMA EXCEPTION_INIT`, `SQLCODE` is typically `+1` and `SQLERRM` returns the message `User-Defined Exception`.

### 3.3 Custom Business Scenarios

For example, an order cannot be confirmed if its quantity is 0:

~~~sql
DECLARE
    e_empty_order EXCEPTION;
    l_quantity NUMBER := 0;
BEGIN
    IF l_quantity = 0 THEN
        RAISE e_empty_order;
    END IF;

    DBMS_OUTPUT.PUT_LINE('Confirm order');
EXCEPTION
    WHEN e_empty_order THEN
        DBMS_OUTPUT.PUT_LINE(
            'Cannot confirm an order with no items'
        );
END;
/
~~~

Exception names should describe the condition clearly, such as `e_invalid_order_state`, `e_credit_limit_exceeded`, or `e_missing_approval`, rather than a generic name like `e_error`.

### 3.4 User-Defined Exceptions Do Not Automatically Have Custom Messages

Declaring `e_invalid_amount EXCEPTION` does not attach an arbitrary business message. You can:

- Write the message inside the handler.
- Use `RAISE_APPLICATION_ERROR` to return a structured code and message to the caller.
- Log the error with a request ID and context, then re-raise it.

Do not rely on `SQLERRM` of a plain user-defined exception to display business error messages.

## 4. Scope of Exceptions

An exception is declared in the declarative section of a block, procedure, function, or package. The exception name is valid in scope from its declaration until the end of the block and within nested child blocks inside it.

### 4.1 Exception Declared in a Parent Block

~~~sql
DECLARE
    e_invalid_state EXCEPTION;
BEGIN
    BEGIN
        RAISE e_invalid_state;
    EXCEPTION
        WHEN OTHERS THEN
            DBMS_OUTPUT.PUT_LINE('Inner block caught error');
            RAISE;
    END;
EXCEPTION
    WHEN e_invalid_state THEN
        DBMS_OUTPUT.PUT_LINE('Outer block handled error');
END;
/
~~~

A child block can use an exception declared in a parent block. The inner handler catches the error with `WHEN OTHERS`, and then a bare `RAISE;` re-raises the current exception so the parent block can catch it by its specific name.

### 4.2 Exception Declared in a Child Block

~~~sql
BEGIN
    DECLARE
        e_local_error EXCEPTION;
    BEGIN
        RAISE e_local_error;
    END;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('Error propagated from child block');
END;
/
~~~

The parent block can catch it with `OTHERS`, or use an exception with broader scope if a named error contract is required.

### 4.3 Shared Exceptions Between a Package and Callers

If multiple procedures need to return the same kind of business error, exceptions can be declared in a package specification:

~~~sql
CREATE OR REPLACE PACKAGE order_errors AS
    e_invalid_order_state EXCEPTION;
    e_credit_limit_exceeded EXCEPTION;
END order_errors;
/
~~~

A caller can handle them as follows:

~~~sql
BEGIN
    order_service.confirm_order(1001);
EXCEPTION
    WHEN order_errors.e_invalid_order_state THEN
        DBMS_OUTPUT.PUT_LINE('Order is not in an allowed state');
    WHEN order_errors.e_credit_limit_exceeded THEN
        DBMS_OUTPUT.PUT_LINE('Credit limit exceeded');
END;
/
~~~

This example assumes the `order_service` package raises the corresponding published exceptions. The package specification serves as an error contract between modules; there is no need to expose every internal exception externally.

## 5. Exception Propagation Across Blocks

If a block has no matching handler, the exception propagates to the enclosing block or caller. This is called exception propagation.

### 5.1 Do Not Handle Errors at a Low Layer Without a Recovery Strategy

Example:

~~~sql
CREATE OR REPLACE PROCEDURE update_order (
    p_order_id IN NUMBER
)
AS
BEGIN
    UPDATE orders
    SET status = 'CONFIRMED'
    WHERE order_id = p_order_id;

    IF SQL%ROWCOUNT = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20011,
            'Order does not exist'
        );
    END IF;
END;
/
~~~

The procedure does not `COMMIT` on its own and does not swallow errors. The caller can decide the transaction boundary and notify the application.

### 5.2 Catch and Re-Raise

~~~sql
BEGIN
    update_order(999999);
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('Order update failed');
        RAISE;
END;
/
~~~

A bare `RAISE` inside an exception handler re-raises the exception currently being handled, preserving the original error so upper layers can classify it.

### 5.3 Raising a Different Exception

A layer can translate a technical error into a different business error, but preserving the root cause should be considered. If the original exception is replaced by another exception, the caller may lose root-cause information. When the stack needs to be preserved, consider `RAISE_APPLICATION_ERROR` with the third parameter `TRUE`, or log the error stack/backtrace before translating.

## 6. What Is PRAGMA EXCEPTION_INIT?

`PRAGMA EXCEPTION_INIT` associates a declared exception with a specific Oracle error code. This allows code to catch an Oracle error by a meaningful name rather than checking `SQLCODE` inside `WHEN OTHERS`.

Syntax:

~~~sql
exception_name EXCEPTION;
PRAGMA EXCEPTION_INIT(exception_name, error_code);
~~~

Where:

- `exception_name` is a user-defined exception previously declared in the same scope.
- `error_code` is a negative integer Oracle error code, for example `-2292` for `ORA-02292`.

`PRAGMA` is a compiler directive, not a runtime statement, and it does not raise an exception by itself.

### 6.1 Example: Catching ORA-02292 by a Dedicated Name

`ORA-02292` occurs when deleting a parent row that is still referenced by child rows in a foreign key relationship.

~~~sql
DECLARE
    e_child_records_exist EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_child_records_exist, -2292);
BEGIN
    DELETE FROM departments
    WHERE department_id = 10;

    DBMS_OUTPUT.PUT_LINE('Department deleted');
EXCEPTION
    WHEN e_child_records_exist THEN
        DBMS_OUTPUT.PUT_LINE(
            'Cannot delete department because child records still exist'
        );
    WHEN OTHERS THEN
        RAISE;
END;
/
~~~

If the `DELETE` violates the foreign key because child records exist, Oracle raises `ORA-02292`. PL/SQL recognizes error code `-2292` and routes it to the handler named `e_child_records_exist`.

A descriptive exception name expresses the business meaning of the error much better than forcing callers to know ORA codes.

### 6.2 PRAGMA Does Not Change the Original Error

`PRAGMA EXCEPTION_INIT` does not change the Oracle error code and does not change the root cause. It only binds a PL/SQL name to the error code so you can write:

~~~sql
WHEN e_child_records_exist THEN
~~~

instead of:

~~~sql
WHEN OTHERS THEN
    IF SQLCODE = -2292 THEN
        ...
    ELSE
        RAISE;
    END IF;
~~~

Using a named exception makes code clearer, avoids mistyping error codes, and separates specific handling logic from numeric comparisons inside a catch-all handler.

### 6.3 Choosing Error Codes Without a Suitable Predefined Exception

Use `PRAGMA EXCEPTION_INIT` for a specific ORA error for which PL/SQL does not have an appropriate predefined name, such as a constraint error or lock error that requires dedicated handling.

Do not redeclare exceptions that already have predefined names like `DUP_VAL_ON_INDEX` or `NO_DATA_FOUND`. Using standard built-in names helps readers recognize the intent immediately and preserves consistency.

### 6.4 PRAGMA Is Not RAISE_APPLICATION_ERROR

| Mechanism | Purpose |
|---|---|
| PRAGMA EXCEPTION_INIT | Binds an exception name to an existing error code |
| RAISE e_name | Explicitly raises a declared exception |
| RAISE; | Re-raises the current exception inside a handler |
| RAISE_APPLICATION_ERROR | Raises an application error code and message |

`PRAGMA` does not create a new error code. `RAISE_APPLICATION_ERROR` is the API for raising application errors in the reserved code range.

## 7. RAISE_APPLICATION_ERROR and Application Error Codes

`RAISE_APPLICATION_ERROR` belongs to the `DBMS_STANDARD` package and is used in PL/SQL to return an application-defined error code.

Syntax:

~~~sql
RAISE_APPLICATION_ERROR(
    error_code,
    message
    [, {TRUE | FALSE}]
);
~~~

Rules:

- `error_code` must be in the range `-20000` to `-20999`.
- `message` is the message explaining the error.
- Optional third parameter: `TRUE` pushes the new error onto the error stack; `FALSE` replaces the current error stack. The default is `FALSE`.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE validate_transfer (
    p_amount IN NUMBER
)
AS
BEGIN
    IF p_amount <= 0 THEN
        RAISE_APPLICATION_ERROR(
            -20020,
            'Transfer amount must be greater than zero'
        );
    END IF;
END;
/
~~~

The caller receives `ORA-20020` along with the message. The error code can be used in the API contract, logs, or mapped to HTTP status codes in the application tier.

### 7.1 Combining PRAGMA with Application Error Codes

You can assign a name to an application error code so callers can catch it as a named exception:

~~~sql
DECLARE
    e_invalid_transfer_amount EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_invalid_transfer_amount, -20020);
BEGIN
    validate_transfer(-50);
EXCEPTION
    WHEN e_invalid_transfer_amount THEN
        DBMS_OUTPUT.PUT_LINE(
            'Invalid transfer amount'
        );
END;
/
~~~

Here:

1. The procedure raises `ORA-20020` using `RAISE_APPLICATION_ERROR`.
2. `PRAGMA` associates code `-20020` with the name `e_invalid_transfer_amount`.
3. The caller catches the error by exception name.

This is a clean way to establish a named, stable error contract. The `-20000..-20999` range must be managed carefully so two modules do not reuse the same code for different meanings.

### 7.2 When to Use the TRUE Parameter

If you are handling an exception and need to add an application error while preserving the previous error information on the stack, you can use:

~~~sql
RAISE_APPLICATION_ERROR(
    -20030,
    'Order processing failed',
    TRUE
);
~~~

`TRUE` pushes the new error on top of the existing stack. `FALSE` (default) replaces the current stack with the new error. Choose based on diagnostic needs; do not treat `TRUE` as an automatic way to preserve all context if code has already caught and altered the flow earlier.

## 8. SQLCODE and SQLERRM

These two functions allow reading the error code and message inside an exception handler.

### 8.1 SQLCODE

`SQLCODE` returns the code of the exception currently being handled:

- Oracle errors typically return negative numbers.
- `NO_DATA_FOUND` has PL/SQL code `+100`.
- A plain user-defined exception typically returns `+1`.
- An exception mapped with `PRAGMA EXCEPTION_INIT` returns the bound error code.

### 8.2 SQLERRM

`SQLERRM` returns the message of the current exception inside a handler. You can call:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('Code=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('Message=' || SQLERRM);
        RAISE;
~~~

Do not log only the message without the error code, because the message can depend on language or version; the error code provides more reliable classification.

### 8.3 Logging Exceptions and Preserving the Original Error

~~~sql
BEGIN
    perform_business_operation;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'SQLCODE=' || SQLCODE ||
            ', SQLERRM=' || SQLERRM
        );
        RAISE;
END;
/
~~~

In production applications, replace `DBMS_OUTPUT` with a proper logger. After logging, `RAISE;` re-raises the original error so the caller still knows the operation failed.

### 8.4 Error Stack and Backtrace

`SQLERRM` generally provides the message of the current exception. When deeper diagnostics are needed, you can use:

~~~sql
DBMS_UTILITY.FORMAT_ERROR_STACK
DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
DBMS_UTILITY.FORMAT_CALL_STACK
~~~

- `FORMAT_ERROR_STACK`: returns the current error stack.
- `FORMAT_ERROR_BACKTRACE`: shows the execution path down to the line where the exception was raised.
- `FORMAT_CALL_STACK`: describes the call stack at the time of invocation.

Example:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_STACK
        );
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END;
~~~

The backtrace is especially useful when an exception is raised in a deeply nested procedure but only handled at a higher layer.

## 9. Order and Scope of Exception Handlers

### 9.1 Each Handler Covers a Group of Exceptions

~~~sql
BEGIN
    -- Business logic statements.
    NULL;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        -- Handle missing row.
        NULL;
    WHEN DUP_VAL_ON_INDEX THEN
        -- Handle duplicate.
        NULL;
    WHEN OTHERS THEN
        -- Handle unclassified errors.
        RAISE;
END;
/
~~~

`WHEN OTHERS` must be placed last in the handler list. It acts as the fallback branch that catches any remaining exceptions not handled by specific handlers above it.

### 9.2 Do Not Place WHEN OTHERS Before Specific Handlers

A catch-all handler at the end protects against unexpected errors. Placing it in the middle makes subsequent handlers invalid in PL/SQL structure.

### 9.3 A Handler Does Not Catch Errors Raised Inside Itself

If code inside a handler raises another error, the new error is not caught by other handlers in the same `EXCEPTION` section. It propagates to the enclosing block. Therefore, loggers, cleanup logic, and recovery actions inside a handler also need their own error design.

### 9.4 Do Not Swallow Exceptions with NULL

The following pattern is usually dangerous:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        NULL;
~~~

It leads the caller to believe the procedure succeeded even though the operation may have failed. Only ignore an exception when the situation is clearly known to have no business impact, and record both the reason and the state.

## 10. Transactions and Exceptions

Exception handling is not the same as transaction handling. When an SQL statement fails, Oracle typically rolls back the changes of that individual statement; earlier changes in the transaction may still remain pending.

Example:

~~~sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 10;

    -- The following INSERT may violate a constraint.
    INSERT INTO transfer_log (
        transfer_id,
        account_id,
        amount
    )
    VALUES (
        -1,
        10,
        100
    );
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        DBMS_OUTPUT.PUT_LINE('Duplicate transfer id');
        -- The earlier UPDATE is not automatically rolled back here.
END;
/
~~~

If both changes belong to the same business operation and must succeed or fail together, the caller must `ROLLBACK` the transaction when handling the error:

~~~sql
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        ROLLBACK;
        RAISE;
~~~

Do not `COMMIT` or `ROLLBACK` on your own inside a shared procedure if the caller owns a larger transaction, unless the procedure's contract explicitly states that it owns the transaction. Transaction ownership must remain consistent across layers.

## 11. Combining Predefined, User-Defined, and EXCEPTION_INIT in One Module

A business procedure may handle three groups of errors:

1. Oracle errors that already have a predefined name.
2. Oracle errors that have an ORA code without a suitable predefined name.
3. Business conditions detected by application logic.

Example of a procedure checking inventory:

~~~sql
CREATE OR REPLACE PROCEDURE reserve_inventory (
    p_product_id IN NUMBER,
    p_quantity   IN NUMBER
)
AS
    e_invalid_quantity EXCEPTION;
    l_available inventory.available_qty%TYPE;
BEGIN
    IF p_quantity <= 0 THEN
        RAISE e_invalid_quantity;
    END IF;

    SELECT available_qty
    INTO l_available
    FROM inventory
    WHERE product_id = p_product_id
    FOR UPDATE;

    IF l_available < p_quantity THEN
        RAISE_APPLICATION_ERROR(
            -20041,
            'Insufficient inventory'
        );
    END IF;

    UPDATE inventory
    SET available_qty = available_qty - p_quantity
    WHERE product_id = p_product_id;

EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20042,
            'Product does not exist'
        );
    WHEN e_invalid_quantity THEN
        RAISE_APPLICATION_ERROR(
            -20043,
            'Quantity must be greater than zero'
        );
    WHEN OTHERS THEN
        RAISE;
END;
/
~~~

The procedure above uses `NO_DATA_FOUND` when the product is not found, a user-defined exception for invalid quantity, and `RAISE_APPLICATION_ERROR` for business errors with custom codes. It does not `COMMIT` on its own; the caller owns the transaction.

A specific ORA error without a suitable predefined exception can be added via an exception declaration and `PRAGMA EXCEPTION_INIT` in the same declarative section. Do not add handlers for errors that the procedure cannot actually raise.

## 12. Designing an Exception Contract for a Package

A package can publish business exceptions so multiple callers can handle them consistently.

### 12.1 Declaring Public Exceptions and Mapped Codes

~~~sql
CREATE OR REPLACE PACKAGE inventory_errors AS
    e_invalid_quantity EXCEPTION;
    e_insufficient_stock EXCEPTION;
    e_product_not_found EXCEPTION;

    PRAGMA EXCEPTION_INIT(e_invalid_quantity, -20051);
    PRAGMA EXCEPTION_INIT(e_insufficient_stock, -20052);
    PRAGMA EXCEPTION_INIT(e_product_not_found, -20053);
END inventory_errors;
/
~~~

### 12.2 Service Package Raising Corresponding Error Codes

~~~sql
CREATE OR REPLACE PACKAGE inventory_service AS
    PROCEDURE reserve (
        p_product_id IN NUMBER,
        p_quantity   IN NUMBER
    );
END inventory_service;
/

CREATE OR REPLACE PACKAGE BODY inventory_service AS
    PROCEDURE reserve (
        p_product_id IN NUMBER,
        p_quantity   IN NUMBER
    )
    AS
        l_available NUMBER;
    BEGIN
        IF p_quantity <= 0 THEN
            RAISE_APPLICATION_ERROR(
                -20051,
                'Quantity must be greater than zero'
            );
        END IF;

        SELECT available_qty
        INTO l_available
        FROM inventory
        WHERE product_id = p_product_id
        FOR UPDATE;

        IF l_available < p_quantity THEN
            RAISE_APPLICATION_ERROR(
                -20052,
                'Insufficient stock'
            );
        END IF;

        UPDATE inventory
        SET available_qty = available_qty - p_quantity
        WHERE product_id = p_product_id;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(
                -20053,
                'Product not found'
            );
    END reserve;
END inventory_service;
/
~~~

### 12.3 Caller Handling by Exception Name

~~~sql
BEGIN
    inventory_service.reserve(100, -5);
EXCEPTION
    WHEN inventory_errors.e_invalid_quantity THEN
        DBMS_OUTPUT.PUT_LINE('Invalid quantity');
    WHEN inventory_errors.e_insufficient_stock THEN
        DBMS_OUTPUT.PUT_LINE('Insufficient stock');
    WHEN inventory_errors.e_product_not_found THEN
        DBMS_OUTPUT.PUT_LINE('Product not found');
END;
/
~~~

The caller does not need to hard-code `-20051`, `-20052`, or `-20053` across modules. The package specification publishes the error names, and `PRAGMA` binds those names to the application error codes.

## 13. Exceptions in Procedures, Functions, and Triggers

### 13.1 Procedures and Functions

Procedures and functions can declare local exceptions or use a shared exceptions package. If unhandled, the error propagates to the caller. For a function called inside an SQL statement, an exception can cause the invoking SQL statement to fail.

### 13.2 Triggers

Triggers can use predefined exceptions, user-defined exceptions, and `PRAGMA EXCEPTION_INIT` like any other PL/SQL block.

Example of a rule validation check:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_validate
BEFORE INSERT OR UPDATE ON orders
FOR EACH ROW
DECLARE
    e_invalid_amount EXCEPTION;
BEGIN
    IF :NEW.total_amount < 0 THEN
        RAISE e_invalid_amount;
    END IF;
EXCEPTION
    WHEN e_invalid_amount THEN
        RAISE_APPLICATION_ERROR(
            -20061,
            'Order amount cannot be negative'
        );
END;
/
~~~

A trigger raising an exception causes the triggering DML statement to fail. That DML statement is rolled back according to statement-level atomicity. Do not use a trigger to swallow constraint errors or mask invalid data states.

### 13.3 Do Not Commit Inside a Normal Trigger

Triggers execute within the transaction context of the statement that fires them. Do not perform normal `COMMIT`/`ROLLBACK` inside a trigger; transaction control operations are restricted and can cause errors. Let the caller manage the transaction and use exceptions to report errors.

## 14. Proper Error Logging

A logging handler should capture enough information for investigation:

- `SQLCODE` and `SQLERRM`.
- `FORMAT_ERROR_STACK`.
- `FORMAT_ERROR_BACKTRACE`.
- Module/procedure name and business step.
- Request ID or non-sensitive business key.
- Timestamp and correlation ID.

Example:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        error_logger.write_error(
            p_error_code => SQLCODE,
            p_error_text => SQLERRM,
            p_error_stack =>
                DBMS_UTILITY.FORMAT_ERROR_STACK,
            p_backtrace =>
                DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END;
~~~

`ERROR_LOGGER.WRITE_ERROR` is a hypothetical application procedure. If the logger writes in the same transaction, the log record may be rolled back along with the business transaction. If logs must persist independently, a separate mechanism must be designed with a clear understanding of transaction boundaries; never commit business changes from an exception handler.

Do not log passwords, access tokens, payment data, or sensitive personal information. `SQLERRM` sometimes contains values or object names useful for diagnostics; apply appropriate masking policies.

## 15. Common Mistakes and How to Fix Them

| Design Mistake | Consequence | How to Improve |
|---|---|---|
| Using WHEN OTHERS for all cases | Loses ability to classify errors | Catch specific predefined/user-defined exceptions first |
| Missing handlers for expected errors | Errors leak unexpectedly to caller | Define an exception contract |
| Declaring an exception without RAISE | Handler never runs | Raise when the condition actually occurs |
| Using RAISE e_name expecting a custom message | SQLERRM is only User-Defined Exception without mapping | Use RAISE_APPLICATION_ERROR or a logger |
| Comparing SQLCODE across branches in OTHERS | Hard to read and easy to miss cases | Use PRAGMA EXCEPTION_INIT to name errors |
| Using PRAGMA for errors with predefined names | Redundant and confusing | Use standard exception names |
| Confusing PRAGMA with RAISE_APPLICATION_ERROR | PRAGMA does not raise errors on its own | Use each API for its intended purpose |
| Catching an error without re-raising | Caller may think operation succeeded | RAISE if current layer has not fully recovered |
| Using RAISE e_other to translate errors and losing origin | Loses original code and backtrace | Log stack/backtrace or use stack-preserving strategy |
| Placing WHEN OTHERS before specific handlers | Invalid handler structure/intent | Place OTHERS last |
| Swallowing errors with NULL | Hides failures | Only ignore with clear policy and logging |
| Assuming exceptions roll back the whole transaction | Earlier DML may remain pending | Caller rolls back at the right scope |
| Using ROLLBACK in a shared procedure | May cancel caller's changes | Define clear transaction ownership |
| Translating all errors to a generic ORA-20000 | Caller loses classification ability | Maintain distinct, stable error codes |
| Logging and committing inside a handler | May commit business data unintentionally | Separate logging transaction by design |

## 16. Lab: Three Ways to Handle Errors

The following blocks use PL/SQL and can be run in a practice schema with `SET SERVEROUTPUT ON`. Examples performing DML on sample tables only run if the corresponding tables/constraints exist and data modifications are permitted.

### 16.1 Catching a Predefined Exception

~~~sql
SET SERVEROUTPUT ON

DECLARE
    l_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO l_name
    FROM employees
    WHERE employee_id = -999;

    DBMS_OUTPUT.PUT_LINE(l_name);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('NO_DATA_FOUND was handled');
END;
/
~~~

Observe that `SELECT INTO` finds no rows and the `NO_DATA_FOUND` handler runs.

### 16.2 Raising a User-Defined Exception

~~~sql
DECLARE
    e_invalid_quantity EXCEPTION;
    l_quantity NUMBER := -3;
BEGIN
    IF l_quantity <= 0 THEN
        RAISE e_invalid_quantity;
    END IF;
EXCEPTION
    WHEN e_invalid_quantity THEN
        DBMS_OUTPUT.PUT_LINE('Quantity must be positive');
END;
/
~~~

Change `l_quantity` to `3` to see the execution flow without raising an exception.

### 16.3 Mapping ORA-02292

~~~sql
DECLARE
    e_child_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_child_exists, -2292);
BEGIN
    -- Run only if schema has a matching parent-child relationship.
    DELETE FROM departments
    WHERE department_id = 10;
EXCEPTION
    WHEN e_child_exists THEN
        DBMS_OUTPUT.PUT_LINE(
            'ORA-02292 caught by e_child_exists'
        );
    WHEN OTHERS THEN
        RAISE;
END;
/
~~~

To test this, pick a parent row that currently has child rows. Do not delete real data just to test exceptions.

### 16.4 Raising and Catching an Application Error Code

~~~sql
DECLARE
    e_invalid_amount EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_invalid_amount, -20071);
BEGIN
    RAISE_APPLICATION_ERROR(
        -20071,
        'Amount must be greater than zero'
    );
EXCEPTION
    WHEN e_invalid_amount THEN
        DBMS_OUTPUT.PUT_LINE(
            'Application error handled by named exception'
        );
END;
/
~~~

This example shows that an error code raised by `RAISE_APPLICATION_ERROR` can be bound to an exception name using `PRAGMA`.

### 16.5 Observing SQLCODE and SQLERRM

~~~sql
DECLARE
    e_invalid_state EXCEPTION;
BEGIN
    RAISE e_invalid_state;
EXCEPTION
    WHEN e_invalid_state THEN
        DBMS_OUTPUT.PUT_LINE('SQLCODE=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('SQLERRM=' || SQLERRM);
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
END;
/
~~~

Observe the code of a plain user-defined exception and the backtrace pointing to the raise location.

## 17. Exception Design Checklist

Before finalizing a procedure, function, or trigger, verify:

1. Which Oracle errors have corresponding predefined exceptions?
2. Which business conditions require user-defined exceptions?
3. Which ORA codes lack predefined names yet require dedicated handling?
4. Should those codes be mapped with `PRAGMA EXCEPTION_INIT`?
5. Which application error codes need to be raised with `RAISE_APPLICATION_ERROR`?
6. Are exception names meaningful and appropriately scoped?
7. Which exceptions are part of a package's public contract versus internal only?
8. Do handlers catch specific errors before `WHEN OTHERS`?
9. Does each handler recover completely, or should it `RAISE` again?
10. Are `SQLCODE`, `SQLERRM`, and backtrace logged adequately?
11. Could the logger accidentally mask the original error or commit the transaction?
12. Does the caller or the procedure own `COMMIT`/`ROLLBACK`?
13. When a statement fails, do earlier DML statements need to be rolled back?
14. Are codes in `-20000..-20999` managed to avoid colliding meanings?
15. Are exception contracts tested from both PL/SQL callers and external applications?

## 18. Summary

PL/SQL provides three essential ways to identify and handle errors:

- **Predefined exceptions** are built-in Oracle names such as `NO_DATA_FOUND`, `TOO_MANY_ROWS`, `ZERO_DIVIDE`, and `DUP_VAL_ON_INDEX`. Use them when the raised error belongs to an already defined category.
- **User-defined exceptions** are declared in PL/SQL with `exception_name EXCEPTION;` and explicitly raised with `RAISE exception_name;`. They suit business conditions defined by the application.
- **PRAGMA EXCEPTION_INIT** binds a user-defined exception to a negative Oracle error code, enabling catching ORA errors by meaningful names. `PRAGMA` does not raise errors on its own and does not alter the original error code.
- **RAISE_APPLICATION_ERROR** raises an application error code and message in the `-20000` to `-20999` range; it can be combined with `PRAGMA` so callers catch that code by exception name.
- **SQLCODE, SQLERRM, and FORMAT_ERROR_BACKTRACE** assist in classifying and investigating errors.
- **RAISE** inside a handler re-raises the current exception. Do not swallow errors unless the current layer has fully recovered.
- Exception handling does not manage transactions automatically. Callers must manage `COMMIT`/`ROLLBACK` according to the proper business boundaries.

A solid error design gives clear names to each situation, preserves the root cause, publishes a consistent contract across modules, and leaves transaction control to the layer that owns it.
