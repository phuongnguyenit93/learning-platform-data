# WHEN OTHERS, Re-Raising Errors, and Avoiding Masked Failed Transactions in PL/SQL

PL/SQL uses exceptions to signal that an operation cannot continue along its normal flow. When an error occurs, Oracle searches for a matching exception handler in the current block and propagates the error up to calling blocks if no handler catches it. How a handler is written determines whether the error is recorded, whether it reaches the caller, and whether the application accidentally treats a failed transaction as successful.

The **WHEN OTHERS** clause catches any exception not handled by a specific handler in the block. It is a useful tool at a final boundary, but it becomes very dangerous if the handler merely logs the error and continues as if the work succeeded. In most cases, after capturing the required diagnostic details, use **RAISE** to re-raise the current exception.

This lesson covers exception scope, handler ordering, `RAISE` and `RAISE_APPLICATION_ERROR`, error details and backtrace, the difference between statement rollback and transaction rollback, `SAVEPOINT`, logging, errors in triggers, and code patterns that prevent masking failed transactions.

## 1. Exceptions in PL/SQL

An exception is an abnormal event that causes execution flow to leave the current statement. Examples:

- `SELECT INTO` finds no rows.
- `SELECT INTO` returns more than one row.
- `INSERT` violates a `PRIMARY KEY` or `UNIQUE` constraint.
- Division by zero.
- The program explicitly calls `RAISE` or `RAISE_APPLICATION_ERROR`.
- A trigger detects invalid data and rejects the DML.

PL/SQL can handle exceptions using the `EXCEPTION` section of a block:

~~~sql
DECLARE
    v_salary NUMBER;
BEGIN
    SELECT salary
    INTO v_salary
    FROM employees
    WHERE employee_id = -1;

    DBMS_OUTPUT.PUT_LINE(v_salary);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Employee not found');
END;
/
~~~

If the `SELECT` returns no rows, Oracle transfers control to the `NO_DATA_FOUND` handler. Statements after `SELECT` in the `BEGIN` section are not executed.

### 1.1. Structure of a Block with an Exception Handler

~~~sql
DECLARE
    -- Variable, cursor, and exception declarations.
BEGIN
    -- Normal statements.
EXCEPTION
    WHEN exception_name THEN
        -- Handle specific error.
    WHEN OTHERS THEN
        -- Handle remaining errors.
END;
/
~~~

The `EXCEPTION` section is optional. A block can contain multiple handlers, but each exception transfers control only to the first matching handler under PL/SQL matching rules.

### 1.2. Exceptions Are Not Normal Return Values

When an exception is caught and the handler completes normally, execution resumes after the `END` of the block that handled the error. If the exception is not handled in that block, it propagates to the enclosing block or caller.

This matters when a nested block sits inside a procedure or loop: catching the error in the inner block may allow the program to continue, whereas letting it propagate outward can terminate the entire current call.

## 2. Types of Exceptions

PL/SQL typically encounters three categories:

1. Predefined exceptions: Oracle has already defined the exception name.
2. Non-predefined Oracle errors: Oracle errors that have a code without a corresponding predefined name in the program.
3. User-defined exceptions: declared and raised by developers according to business rules.

### 2.1. Predefined Exceptions

| Exception | Common Scenario |
|---|---|
| NO_DATA_FOUND | SELECT INTO returns no rows |
| TOO_MANY_ROWS | SELECT INTO returns multiple rows |
| ZERO_DIVIDE | Division by zero |
| DUP_VAL_ON_INDEX | Unique index/constraint violation |
| INVALID_CURSOR | Invalid cursor operation |
| CURSOR_ALREADY_OPEN | Opening an already open cursor |
| VALUE_ERROR | Invalid conversion or value size |
| STORAGE_ERROR | PL/SQL memory error |

Example:

~~~sql
DECLARE
    v_result NUMBER;
BEGIN
    v_result := 10 / 0;
EXCEPTION
    WHEN ZERO_DIVIDE THEN
        DBMS_OUTPUT.PUT_LINE('Cannot divide by zero');
END;
/
~~~

### 2.2. User-Defined Exceptions

Declare the exception in `DECLARE` and raise it with `RAISE`:

~~~sql
DECLARE
    e_invalid_amount EXCEPTION;
    v_amount NUMBER := -10;
BEGIN
    IF v_amount < 0 THEN
        RAISE e_invalid_amount;
    END IF;

    DBMS_OUTPUT.PUT_LINE('Amount accepted');
EXCEPTION
    WHEN e_invalid_amount THEN
        DBMS_OUTPUT.PUT_LINE('Amount must not be negative');
END;
/
~~~

User-defined exceptions express named business conditions clearly. If the caller needs a specific Oracle error code, map it with `PRAGMA EXCEPTION_INIT` or use `RAISE_APPLICATION_ERROR`.

### 2.3. Non-Predefined Oracle Errors and EXCEPTION_INIT

`PRAGMA EXCEPTION_INIT` binds a program-declared exception name to an Oracle code:

~~~sql
DECLARE
    e_child_records_exist EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_child_records_exist, -2292);
BEGIN
    DELETE FROM departments
    WHERE department_id = 10;
EXCEPTION
    WHEN e_child_records_exist THEN
        DBMS_OUTPUT.PUT_LINE(
            'Department still has dependent rows'
        );
END;
/
~~~

Code `-2292` corresponds to an integrity constraint error when deleting a parent record that still has referencing child rows. Catching exceptions by name makes code much easier to read than comparing `SQLCODE` in multiple places.

## 3. What Is WHEN OTHERS?

`WHEN OTHERS` is a catch-all handler that catches every exception not already handled by a preceding specific handler in the same block:

~~~sql
BEGIN
    -- Operations.
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Unexpected error: ' || SQLERRM
        );
END;
/
~~~

This handler does not distinguish errors caused by data, privileges, configuration, programming bugs, or system failures. Therefore, using `WHEN OTHERS` to record or add context can be reasonable; using it to turn every error into a successful outcome is a serious design flaw.

### 3.1. WHEN OTHERS Must Be Placed After Specific Handlers

Example:

~~~sql
BEGIN
    -- Work.
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        -- Handle not-found case.
    WHEN DUP_VAL_ON_INDEX THEN
        -- Handle duplicate key.
    WHEN OTHERS THEN
        -- Handle remaining errors.
        RAISE;
END;
/
~~~

`WHEN OTHERS` is the catch-all branch, so it must appear last in the handler list. Do not place specific handlers after it.

### 3.2. Do Not Add WHEN OTHERS If There Is No Appropriate Action

If a block does not need to add diagnostic context or restore state, letting the exception propagate naturally is usually better:

~~~sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 10;
END;
/
~~~

If the `UPDATE` fails, the caller receives the original error. There is no need to catch and re-`RAISE` only to add boilerplate code.

## 4. Why Catching WHEN OTHERS and Ignoring Errors Is Dangerous

Consider this example:

~~~sql
CREATE OR REPLACE PROCEDURE transfer_money_bad (
    p_from_account IN NUMBER,
    p_to_account   IN NUMBER,
    p_amount       IN NUMBER
)
AS
BEGIN
    UPDATE accounts
    SET balance = balance - p_amount
    WHERE account_id = p_from_account;

    UPDATE accounts
    SET balance = balance + p_amount
    WHERE account_id = p_to_account;

EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('Transfer failed: ' || SQLERRM);
        -- No RAISE; the error is swallowed.
END;
/
~~~

If the second `UPDATE` fails, the procedure catches the error and exits normally. The caller may never realize the transfer failed. If the caller relies solely on the procedure returning normally, the system can falsely report success.

In particular, the first `UPDATE` may already have succeeded and its change remains in the transaction. Ignoring the exception in the handler does not automatically undo the first `UPDATE`.

### 4.1. Consequences of Swallowing Exceptions

- The caller receives no error to decide whether to retry, roll back, or report failure.
- The application may return `SUCCESS` even though the data operation is incomplete.
- Partial changes may remain active in the transaction.
- A batch job may mark records as processed despite a critical step failing.
- A trigger may hide data rejection and allow invalid DML to proceed.
- Logs contain only a generic message, without error codes or backtrace for investigation.

Rule: if a business operation does not complete, the error must reach the layer responsible for deciding the transaction outcome and business status.

## 5. Using RAISE to Re-Raise the Current Exception

Inside an exception handler, a `RAISE` statement without an exception name re-raises the exception currently being handled:

~~~sql
BEGIN
    -- Work.
EXCEPTION
    WHEN OTHERS THEN
        -- Record diagnostics or add context.
        RAISE;
END;
/
~~~

Bare `RAISE` inside a handler preserves the current exception and lets it propagate to the caller. This is the standard pattern when logging is needed without altering the error outcome.

### 5.1. Pattern: Log Then RAISE

~~~sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 10;

    UPDATE accounts
    SET balance = balance + 100
    WHERE account_id = 20;

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

In real applications, replace `DBMS_OUTPUT` with a properly designed logging mechanism. `RAISE` ensures the caller still receives the original error.

### 5.2. Difference Between RAISE and RAISE exception_name

~~~sql
RAISE;
~~~

Re-raises the exception currently being handled; used inside an exception handler.

~~~sql
RAISE e_invalid_amount;
~~~

Explicitly raises a named user-defined exception. Used in the executable section or inside a handler when intending to raise a declared exception.

Do not confuse these two forms. When handling a root error and intending to preserve that same error, use bare `RAISE`.

### 5.3. Do Not Use RAISE SQLERRM

`SQLERRM` returns a character error message; it is not an exception name to pass to `RAISE`. The proper way to re-raise the current exception is:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        -- Log SQLERRM if needed.
        RAISE;
~~~

If replacing an error with a new business error, use `RAISE_APPLICATION_ERROR` deliberately and clearly document its relationship to the root cause.

## 6. RAISE_APPLICATION_ERROR

`RAISE_APPLICATION_ERROR` raises an application error with a code in the range `-20000` to `-20999`:

~~~sql
RAISE_APPLICATION_ERROR(
    -20001,
    'Amount must be greater than zero'
);
~~~

This is the common way to return a business error with an explicit code to the caller.

### 6.1. Parameter Validation Example

~~~sql
CREATE OR REPLACE PROCEDURE create_order (
    p_order_id IN NUMBER,
    p_amount   IN NUMBER
)
AS
BEGIN
    IF p_order_id IS NULL THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Order ID is required'
        );
    END IF;

    IF p_amount IS NULL OR p_amount <= 0 THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Amount must be greater than zero'
        );
    END IF;

    INSERT INTO orders (order_id, amount)
    VALUES (p_order_id, p_amount);
END;
/
~~~

The caller can receive error code `-20001` or `-20002` and display an appropriate message according to the API contract.

### 6.2. Third Parameter TRUE/FALSE

`RAISE_APPLICATION_ERROR` has an optional third parameter:

- `FALSE` or omitted: replaces the current error stack with the new application error.
- `TRUE`: appends the application error onto the current error stack.

Example:

~~~sql
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        RAISE_APPLICATION_ERROR(
            -20010,
            'Order already exists',
            TRUE
        );
END;
~~~

`TRUE` can retain previous error information on the stack while adding a business message. Still, if the goal is to propagate the current exception unchanged, bare `RAISE` remains the clearest choice.

### 6.3. Do Not Collapse Every Error into a Single Business Code

Avoid catching every exception and re-raising the same generic `-20000` code. Doing so destroys the ability to distinguish:

- Invalid input data.
- Entity not found.
- Duplicate key.
- Out of space.
- Missing privileges.
- Connection or system errors.

Only map errors when the application tier genuinely requires a new error contract. Otherwise, propagate the original exception so the caller has complete information.

## 7. SQLCODE and SQLERRM

Inside an exception handler, PL/SQL provides two commonly used functions:

- `SQLCODE`: numeric code of the current exception.
- `SQLERRM`: corresponding error message.

Example:

~~~sql
BEGIN
    INSERT INTO departments (department_id, department_name)
    VALUES (10, 'Duplicate');
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('Code: ' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('Message: ' || SQLERRM);
        RAISE;
END;
/
~~~

`SQLCODE`/`SQLERRM` are useful for logging and classifying errors, but are not sufficient to pinpoint the exact PL/SQL line that raised the error.

### 7.1. Do Not Call SQLCODE/SQLERRM After Leaving the Handler

Current exception information is meaningful inside the exception handler. If you need it afterward, save the code and message into local variables immediately upon catching the error.

~~~sql
DECLARE
    v_error_code NUMBER;
    v_error_text VARCHAR2(4000);
BEGIN
    -- Work.
EXCEPTION
    WHEN OTHERS THEN
        v_error_code := SQLCODE;
        v_error_text := SQLERRM;
        -- Use both variables to log before re-raising.
        RAISE;
END;
/
~~~

## 8. Error Stack, Backtrace, and Call Stack

A single `SQLERRM` message may tell you what kind of error occurred, but it is not always enough to find where it originated. Oracle provides additional diagnostic functions.

| Function | Purpose |
|---|---|
| SQLCODE | Current error code |
| SQLERRM | Current error message |
| DBMS_UTILITY.FORMAT_ERROR_STACK | Error stack string |
| DBMS_UTILITY.FORMAT_ERROR_BACKTRACE | PL/SQL location where the exception was raised |
| DBMS_UTILITY.FORMAT_CALL_STACK | Call stack at the time the function is invoked |

Example:

~~~sql
BEGIN
    -- Statement that may fail.
    DELETE FROM departments
    WHERE department_id = -999;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_STACK
        );
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_CALL_STACK
        );
        RAISE;
END;
/
~~~

### 8.1. Error Stack vs. Backtrace

- Error stack shows the current error chain, which may include multiple messages.
- Backtrace pinpoints the PL/SQL location where the exception was raised, even after propagating across multiple blocks.
- Call stack describes the call chain at the moment of inspection; it helps understand the call path, but does not replace the backtrace.

When logging errors, save the error code, error stack, and backtrace if logging policies allow. Do not log only `SQLERRM` and lose the origin line.

### 8.2. Capture Backtrace Before Calling the Logger

If the logger calls additional subprograms or handles its own exceptions, retrieve the error details before invoking the logger:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        v_code      := SQLCODE;
        v_message   := SQLERRM;
        v_err_stack := DBMS_UTILITY.FORMAT_ERROR_STACK;
        v_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        log_error(
            p_code      => v_code,
            p_message   => v_message,
            p_stack     => v_err_stack,
            p_backtrace => v_backtrace
        );

        RAISE;
~~~

This example is an illustrative structure; variable declarations and the `LOG_ERROR` signature must fit your application. `RAISE` must still reside inside the handler processing the original exception.

## 9. Exception Scope and Propagation Across Blocks

PL/SQL searches for a handler in the current block first. If no matching handler exists, the exception propagates to the enclosing block. This process continues until a handler is found or the exception exits the call to the caller.

Example:

~~~sql
DECLARE
    e_problem EXCEPTION;
BEGIN
    BEGIN
        RAISE e_problem;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            DBMS_OUTPUT.PUT_LINE('Inner: no data');
    END;

    DBMS_OUTPUT.PUT_LINE('After inner block');
EXCEPTION
    WHEN e_problem THEN
        DBMS_OUTPUT.PUT_LINE('Outer: handled problem');
END;
/
~~~

The inner block's handler does not match `E_PROBLEM`, so the exception propagates to the outer block. The outer block catches it; the line `After inner block` does not run because control left the inner block via an exception.

### 9.1. If a Handler Completes Normally, Execution Continues After That Block

~~~sql
BEGIN
    BEGIN
        RAISE NO_DATA_FOUND;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            DBMS_OUTPUT.PUT_LINE('Handled inside');
    END;

    DBMS_OUTPUT.PUT_LINE('Continue outer block');
END;
/
~~~

Because the handler handled `NO_DATA_FOUND` and did not re-raise it, the outer block continues running.

### 9.2. RAISE Causes the Error to Continue Propagating

~~~sql
BEGIN
    BEGIN
        RAISE NO_DATA_FOUND;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            DBMS_OUTPUT.PUT_LINE('Logging inner error');
            RAISE;
    END;

    DBMS_OUTPUT.PUT_LINE('This line is skipped');
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Handled by outer block');
END;
/
~~~

The inner handler logs and then executes `RAISE`. The outer block catches the exception and continues after the outer handler. The line `This line is skipped` is not executed.

## 10. Statement Rollback vs. Transaction Rollback

This is a critical distinction when handling transaction errors. Distinguish between:

- **Statement-level rollback**: Oracle undoes the effects of the individual failing SQL statement.
- **Transaction rollback**: undoes uncommitted changes across the entire transaction, or back to a `SAVEPOINT`.

A single failing DML statement does not mean the entire transaction automatically rolls back.

### 10.1. One INSERT Fails

Suppose:

~~~sql
INSERT INTO accounts (account_id, balance)
VALUES (1, 1000);

INSERT INTO accounts (account_id, balance)
VALUES (1, 2000);
~~~

If the second `INSERT` violates the primary key, Oracle undoes only the effects of that second `INSERT`. The row with `account_id = 1` inserted by the first statement remains in the current transaction and does not vanish on its own.

The caller can decide to:

- `COMMIT` the earlier valid change.
- `ROLLBACK` the entire transaction.
- `ROLLBACK TO SAVEPOINT` to undo only changes after a marker.

### 10.2. Exceptions in a Stored Procedure

If a procedure executes multiple DML statements and a later DML fails, earlier successful DML statements are not rolled back automatically just because an exception exited the procedure. The caller must decide the transaction outcome.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE lab_two_steps
AS
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 1;

    UPDATE accounts
    SET balance = balance + 100
    WHERE account_id = -1;
END;
/
~~~

If the second statement updates zero rows, no exception is raised automatically; if it raises an error, the failing DML is rolled back at the statement level, while the first `UPDATE` can remain active in the transaction. The procedure must not swallow errors and let the caller assume both steps completed.

### 10.3. Trigger Exceptions and Statement Rollback

If a trigger raises an exception while an `INSERT`/`UPDATE`/`DELETE` statement is executing, the triggering statement fails. Oracle undoes the effects of that statement, including changes made by the trigger within the same statement. Transaction changes performed before that statement can still remain.

This differs from a procedure running multiple separate DML statements and failing on the last one. Clarify statement versus transaction boundaries before deciding on rollback behavior.

## 11. SAVEPOINT for Partial Transaction Control

`SAVEPOINT` marks a point inside a transaction. `ROLLBACK TO SAVEPOINT` undoes changes made after that marker without rolling back the entire transaction.

Example:

~~~sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 1;

    SAVEPOINT after_debit;

    UPDATE accounts
    SET balance = balance + 100
    WHERE account_id = 2;

    -- Simulate needing to undo work after the savepoint.
    ROLLBACK TO after_debit;

    -- Continue other work or let the caller decide.
END;
/
~~~

In this example, the first `UPDATE` occurred before the `SAVEPOINT` and remains in the transaction after `ROLLBACK TO`. The second `UPDATE` is undone.

### 11.1. SAVEPOINT Inside an Exception Handler

~~~sql
DECLARE
    v_amount NUMBER := 100;
BEGIN
    SAVEPOINT before_transfer;

    UPDATE accounts
    SET balance = balance - v_amount
    WHERE account_id = 1;

    UPDATE accounts
    SET balance = balance + v_amount
    WHERE account_id = -1;

EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO before_transfer;
        RAISE;
END;
/
~~~

The handler undoes the work performed after the `SAVEPOINT` and propagates the error to the caller. The caller still receives the exception and can decide whether to roll back the entire transaction or handle it per business rules.

### 11.2. Do Not Automatically Roll Back the Entire Transaction in Every Handler

A procedure may be called inside a larger transaction managed by the caller. If the procedure executes a full `ROLLBACK` on a minor failure, it can wipe out valid changes the caller already made earlier.

Only execute a full transaction `ROLLBACK` when the procedure explicitly owns the transaction under a clear contract. For reusable procedures, keep transaction control in the calling layer; if needed, use a well-defined `SAVEPOINT` to roll back only the procedure's own work.

## 12. WHEN OTHERS in Triggers

A trigger is PL/SQL code automatically invoked by Oracle when a corresponding event occurs, such as `INSERT`, `UPDATE`, or `DELETE` on a table. Exceptions inside a trigger directly affect the statement that fired the trigger.

### 12.1. Trigger Rejecting Invalid Data

~~~sql
CREATE OR REPLACE TRIGGER trg_check_order_amount
BEFORE INSERT OR UPDATE OF amount
ON orders
FOR EACH ROW
BEGIN
    IF :NEW.amount IS NULL OR :NEW.amount <= 0 THEN
        RAISE_APPLICATION_ERROR(
            -20020,
            'Order amount must be greater than zero'
        );
    END IF;
END;
/
~~~

If the amount is invalid, the trigger raises an error. The `INSERT` or `UPDATE` that fired the trigger fails, and the caller receives the application error code. Do not catch and ignore this error inside the trigger, as doing so lets DML proceed with invalid data.

### 12.2. WHEN OTHERS Followed by RAISE in a Trigger

If logging or extra context is needed:

~~~sql
CREATE OR REPLACE TRIGGER trg_check_order_amount
BEFORE INSERT OR UPDATE OF amount
ON orders
FOR EACH ROW
BEGIN
    IF :NEW.amount IS NULL OR :NEW.amount <= 0 THEN
        RAISE_APPLICATION_ERROR(
            -20020,
            'Order amount must be greater than zero'
        );
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        -- Only add diagnostics here if necessary.
        RAISE;
END;
/
~~~

`RAISE` propagates the error so the DML statement is rejected. If the trigger needs no catch-all action, do not add `WHEN OTHERS` solely to write `RAISE`.

### 12.3. Do Not COMMIT or ROLLBACK Inside a Normal Trigger

A trigger runs within the context of the statement that invoked it. Normal triggers cannot `COMMIT` or `ROLLBACK` the caller's transaction; attempting to do so causes errors such as `ORA-04092`. Never use a trigger to commit part of a business operation on its own.

For auditing, audit rows are usually written in the same transaction so the audit and DML commit or roll back together. If failed attempts must be recorded even when the transaction rolls back, consider transaction-independent logging while understanding the implications and limits of autonomous transactions.

## 13. Error Logging: Normal Transaction vs. Autonomous Transaction

There are two common ways to structure logging:

### 13.1. Logging in the Same Transaction

The logger inserts records into the log table using the current transaction. The advantage is consistency with the business transaction:

- If business work commits, the log commits.
- If business work rolls back, the log rolls back.

Drawback: if you want to retain an error trail after the caller rolls back, the log entry is also rolled back and lost.

### 13.2. Logging via an Autonomous Transaction

A procedure declared with `PRAGMA AUTONOMOUS_TRANSACTION` has a transaction independent of the caller. It can write logs and `COMMIT` independently, even if the business transaction later rolls back.

Example log table:

~~~sql
CREATE TABLE app_error_log (
    log_id       NUMBER GENERATED BY DEFAULT AS IDENTITY,
    logged_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    error_code   NUMBER,
    error_message VARCHAR2(4000),
    error_stack  CLOB,
    backtrace    CLOB,
    module_name  VARCHAR2(128)
);
~~~

Autonomous logger:

~~~sql
CREATE OR REPLACE PROCEDURE log_application_error (
    p_error_code    IN NUMBER,
    p_error_message IN VARCHAR2,
    p_error_stack   IN CLOB,
    p_backtrace     IN CLOB,
    p_module        IN VARCHAR2
)
AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO app_error_log (
        error_code,
        error_message,
        error_stack,
        backtrace,
        module_name
    )
    VALUES (
        p_error_code,
        p_error_message,
        p_error_stack,
        p_backtrace,
        p_module
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        -- Do not let logger errors mask the original error.
        -- Monitoring should have a way to detect logger failures.
END;
/
~~~

This is an illustrative example. In production systems, decide how to handle logging failures, size limits on stack/backtrace, write privileges on the log table, and monitoring when the logger fails to write.

### 13.3. Calling the Logger and Propagating the Original Error

~~~sql
CREATE OR REPLACE PROCEDURE process_order (
    p_order_id IN NUMBER
)
AS
    v_code      NUMBER;
    v_message   VARCHAR2(4000);
    v_stack     CLOB;
    v_backtrace CLOB;
BEGIN
    UPDATE orders
    SET status = 'PROCESSING'
    WHERE order_id = p_order_id;

    -- Other business steps.

EXCEPTION
    WHEN OTHERS THEN
        v_code      := SQLCODE;
        v_message   := SQLERRM;
        v_stack     := DBMS_UTILITY.FORMAT_ERROR_STACK;
        v_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        log_application_error(
            p_error_code    => v_code,
            p_error_message => v_message,
            p_error_stack   => v_stack,
            p_backtrace     => v_backtrace,
            p_module        => 'PROCESS_ORDER'
        );

        RAISE;
END;
/
~~~

The logger commits independently in its autonomous transaction. After the logger finishes, `RAISE` propagates the business exception back to the caller. The caller must still decide whether to roll back the main transaction per the application's contract.

### 13.4. Warning When Using an Autonomous Logger in Triggers

An autonomous transaction sees a different data state from the calling transaction because uncommitted changes from the caller are not visible as committed data to the autonomous transaction. If the logger queries or locks rows currently held by the main transaction, blocking or deadlocks can occur.

An autonomous logger should write only the diagnostic data passed into it and avoid reading or updating business rows currently being processed by the main transaction. Use it intentionally to record an independent trail, not to bypass transaction rules.

## 14. Preserving the Original Error When the Logger Fails

A subtle bug occurs when a handler calls a logger, and the logger itself raises an exception. If the logger's exception escapes, the caller may see only the logging error instead of the original business error.

The logger pattern in the previous section catches internal errors, rolls back the autonomous transaction, and does not re-raise the logging error. This preserves the propagation path of the original exception in the calling handler.

Another way to structure this is to wrap the logger call in a nested block:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        v_code := SQLCODE;
        v_message := SQLERRM;
        v_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        BEGIN
            log_application_error(
                v_code,
                v_message,
                DBMS_UTILITY.FORMAT_ERROR_STACK,
                v_backtrace,
                'PROCESS_ORDER'
            );
        EXCEPTION
            WHEN OTHERS THEN
                -- Record that logging failed via an appropriate monitoring channel.
                NULL;
        END;

        RAISE;
~~~

The inner handler only prevents a secondary logger failure from replacing the original error; the final `RAISE` still resides in the outer handler processing the original exception. Never apply `WHEN OTHERS THEN NULL` to ordinary business logic.

If logging is mandatory for audit compliance, do not silently ignore logger failures. Design proper monitoring/guaranteed-logging mechanisms and explicitly decide whether business operations may proceed when logging is unavailable.

## 15. Do Not Confuse Errors with 0-Row DML Results

An `UPDATE` that matches no rows does not raise an exception automatically:

~~~sql
UPDATE orders
SET status = 'SHIPPED'
WHERE order_id = -1;
~~~

If there is no `order_id = -1`, the statement succeeds with `SQL%ROWCOUNT = 0`. This is not an exception.

If the business rule requires exactly one row to be updated:

~~~sql
UPDATE orders
SET status = 'SHIPPED'
WHERE order_id = p_order_id;

IF SQL%ROWCOUNT = 0 THEN
    RAISE_APPLICATION_ERROR(
        -20030,
        'Order does not exist'
    );
END IF;
~~~

If you require exactly one row and also want to detect multiple rows, design an appropriate constraint or check row counts as required. Do not rely on `WHEN OTHERS` to detect DML affecting zero rows.

## 16. Failed Transactions and Business Status

An API or batch job should distinguish at least:

- Succeeded and committed.
- Succeeded within the transaction, not yet committed.
- Failed and rolled back the relevant work.
- Failed, leaving earlier partial changes in the transaction.
- Failed on a single record while the batch continues per policy.

Never mark status as `SUCCESS` merely because a procedure returned without an exception if code can swallow exceptions.

### 16.1. Example of an Explicit Transaction Contract

The procedure performs only DML and propagates errors:

~~~sql
CREATE OR REPLACE PROCEDURE reserve_inventory (
    p_product_id IN NUMBER,
    p_quantity   IN NUMBER
)
AS
BEGIN
    IF p_quantity <= 0 THEN
        RAISE_APPLICATION_ERROR(-20040, 'Invalid quantity');
    END IF;

    UPDATE inventory
    SET available_qty = available_qty - p_quantity
    WHERE product_id = p_product_id
      AND available_qty >= p_quantity;

    IF SQL%ROWCOUNT = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20041,
            'Insufficient inventory or product not found'
        );
    END IF;
END;
/
~~~

The procedure does not `COMMIT`. The caller controls the transaction:

~~~sql
BEGIN
    reserve_inventory(100, 2);
    -- Execute other related business steps.
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

In this pattern, the caller owns the transaction and rolls back everything if any step fails. If the caller wants to keep changes made before the procedure, use `SAVEPOINT` and `ROLLBACK TO` rather than rolling back the entire transaction.

### 16.2. Do Not COMMIT Inside Shared Procedures If the Caller Needs Control

A procedure that commits on its own strips the caller of the ability to roll back multiple steps as a single business unit. Unless the procedure's contract explicitly says it owns the transaction, keep transaction control in the orchestration layer.

## 17. Row-by-Row Error Handling in Batch Processing

A batch job may need to continue processing subsequent records after one record fails. This is a business requirement distinct from swallowing all errors.

Conceptual example:

~~~sql
BEGIN
    FOR rec IN (
        SELECT order_id
        FROM staging_orders
        ORDER BY order_id
    ) LOOP
        SAVEPOINT before_one_order;

        BEGIN
            process_one_order(rec.order_id);
        EXCEPTION
            WHEN DUP_VAL_ON_INDEX THEN
                ROLLBACK TO before_one_order;
                -- Record duplicate entry per batch policy.
            WHEN OTHERS THEN
                ROLLBACK TO before_one_order;
                -- If error cannot be skipped, propagate to caller.
                RAISE;
        END;
    END LOOP;
END;
/
~~~

This example skips only duplicate-key errors per policy; other errors are still propagated. If business rules allow continuing on other errors as well, record `FAILED` status for each individual order and ensure the overall batch does not falsely report complete success.

For large volumes, consider `FORALL SAVE EXCEPTIONS` or DML error logging where suitable. Regardless of the tool used, distinguish per-row success from overall batch status.

## 18. DML Error Logging and Bulk Error Handling

Oracle supports DML error logging via `DBMS_ERRLOG` and the `LOG ERRORS` clause in certain DML statements. This mechanism lets DML continue processing valid rows while writing failing rows into an error table.

Example creating the error table:

~~~sql
BEGIN
    DBMS_ERRLOG.CREATE_ERROR_LOG(
        dml_table_name => 'ORDERS',
        err_log_table_name => 'ERR$_ORDERS'
    );
END;
/
~~~

Then, in an appropriate case:

~~~sql
INSERT INTO orders (order_id, amount)
SELECT order_id, amount
FROM staging_orders
LOG ERRORS INTO err$_orders ('IMPORT_2026')
REJECT LIMIT UNLIMITED;
~~~

This is a specialized technique for set-based DML; it does not replace proper exception handler design for all errors. Consider which error types are logged, the reject limit, transaction behavior, and business atomicity requirements.

If the business requires the entire batch to succeed or fail together, continuing past failing rows is inappropriate. When using `LOG ERRORS`, the caller must inspect the error table and determine batch status before reporting success.

## 19. Triggers and Business Errors

Triggers are commonly used for auditing, validation, or maintaining logic tied to DML events. When a trigger raises an exception:

- The statement that fired the trigger receives the error.
- The DML statement fails.
- Effects of that statement and the trigger within that statement are undone.
- The caller can catch the exception or let it propagate.

### 19.1. Triggers Must Not Hide Business Constraint Errors

Bad example:

~~~sql
CREATE OR REPLACE TRIGGER trg_validate_order_bad
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    IF :NEW.amount <= 0 THEN
        RAISE_APPLICATION_ERROR(-20050, 'Invalid amount');
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        NULL;
END;
/
~~~

The trigger catches the error and ignores it. The `INSERT` can continue even though the trigger detected an invalid amount. This defeats data validation completely.

Correct version:

~~~sql
CREATE OR REPLACE TRIGGER trg_validate_order
BEFORE INSERT ON orders
FOR EACH ROW
BEGIN
    IF :NEW.amount IS NULL OR :NEW.amount <= 0 THEN
        RAISE_APPLICATION_ERROR(-20050, 'Invalid amount');
    END IF;
END;
/
~~~

There is no need for `WHEN OTHERS` if no extra handling is required. If adding a logger, log the details and then `RAISE` to reject the DML.

### 19.2. Audit Triggers and Transactions

Audit rows inserted by a normal trigger belong to the same transaction as the DML:

- If DML commits, the audit commits.
- If DML rolls back, the audit rolls back.
- If the trigger raises an error causing the DML statement to fail, the audit row from that statement is also undone.

This is usually the desired behavior when auditing records data changes that succeeded.

If failed attempts must also be stored, design an independent error log and clearly understand that an autonomous log record does not prove the business change committed.

## 20. Anti-Patterns to Avoid

| Anti-Pattern | Problem | Fix |
|---|---|---|
| WHEN OTHERS THEN NULL | Swallows every error | `RAISE` or handle explicitly per business rules |
| WHEN OTHERS with only DBMS_OUTPUT | Log is not durable and caller sees no error | Use proper logger then `RAISE` |
| Catching error and returning SUCCESS | Misleading application status | Return error or explicit `FAILED` status |
| RAISE_APPLICATION_ERROR for every error | Loses root error distinction | Map only when a new error contract is needed |
| Full transaction ROLLBACK in shared procedure | Wipes out caller's changes | Let caller own transaction or use `SAVEPOINT` |
| COMMIT inside trigger | Trigger must not control caller transaction | Remove `COMMIT`/`ROLLBACK` from normal triggers |
| Autonomous logger querying caller-locked rows | Can cause blocking/deadlock | Write only passed-in diagnostics |
| Logger failure masking root error | Caller sees secondary error | Guard logger call, then `RAISE` original error |
| Logging only SQLERRM | Missing origin location | Also record error stack and backtrace |
| Swallowing per-row errors without marking batch | Batch falsely reports success | Track per-row and overall batch status |

## 21. Recommended Exception Handling Patterns

### 21.1. No Handling Needed: Let the Error Propagate

~~~sql
BEGIN
    UPDATE orders
    SET status = 'PAID'
    WHERE order_id = p_order_id;
END;
/
~~~

This is the simplest approach when the caller can handle the exception.

### 21.2. Handle One Expected Error, Keep Others

~~~sql
BEGIN
    INSERT INTO orders (order_id, amount)
    VALUES (p_order_id, p_amount);
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        RAISE_APPLICATION_ERROR(
            -20060,
            'Order ID already exists'
        );
END;
/
~~~

Only the duplicate-key error is mapped to a business message. All other errors propagate naturally.

### 21.3. Log Every Error Then Propagate

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        v_code := SQLCODE;
        v_message := SQLERRM;
        v_stack := DBMS_UTILITY.FORMAT_ERROR_STACK;
        v_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        BEGIN
            log_application_error(
                v_code,
                v_message,
                v_stack,
                v_backtrace,
                'MODULE_NAME'
            );
        EXCEPTION
            WHEN OTHERS THEN
                -- Logging error handled separately; do not replace original error.
                NULL;
        END;

        RAISE;
~~~

This pattern is for a boundary layer responsible for catch-all error logging. Suppressing propagation applies only to secondary logger errors; the original business exception is still re-raised via `RAISE`.

### 21.4. Undo Only the Procedure's Work Then Propagate

~~~sql
BEGIN
    SAVEPOINT before_procedure_work;

    -- Multiple DML steps belonging to the procedure.

EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO before_procedure_work;
        RAISE;
END;
/
~~~

Use this when the procedure's contract is to undo its own changes while preserving changes made prior to the caller's savepoint.

## 22. Checking Transaction Outcomes in the Application Layer

The caller should not only check whether a procedure threw an exception if the procedure is designed to return a status. Clearly define:

- Which steps must finish before the procedure returns normally?
- Has the transaction already committed?
- Does the caller still need to `COMMIT`?
- Which errors are converted into business outcomes?
- Which errors must fail the batch?
- What is the behavior if the logger fails to write?

For example, an API may return a status code, but should return `SUCCESS` only after the transaction has completed per contract. If the procedure does not `COMMIT`, the status should state "DML executed in transaction" rather than claiming data is durable.

## 23. Practice Exercises

### Exercise 1 — WHEN OTHERS

Write a block that divides 10 by 0. Catch `WHEN OTHERS`, print `SQLCODE` and `SQLERRM`, and then `RAISE`.

**Task:** Observe how the caller receives the error.

### Exercise 2 — Swallowing Errors

Write two versions of a procedure: one with `WHEN OTHERS THEN NULL`, and one that logs and then executes `RAISE`.

**Question:** How does the caller distinguish success from failure?

### Exercise 3 — RAISE and RAISE_APPLICATION_ERROR

Create a user-defined exception for negative amounts. Test both `RAISE` with the declared exception and `RAISE_APPLICATION_ERROR` with a code between `-20000` and `-20999`.

### Exercise 4 — Backtrace

Create three nested procedures. Raise an error in the deepest procedure; use `FORMAT_ERROR_STACK`, `FORMAT_ERROR_BACKTRACE`, and `FORMAT_CALL_STACK` to observe the differences.

### Exercise 5 — Statement Rollback

Within the same transaction, `INSERT` a valid row and then `INSERT` a duplicate-key row. Catch the error in the caller and verify whether the first row still exists before rolling back.

### Exercise 6 — SAVEPOINT

Create two DML steps, place a `SAVEPOINT` between them, force an error on the second step, and `ROLLBACK TO`. Identify which changes remain in the transaction.

### Exercise 7 — Trigger

Create a `BEFORE INSERT` trigger rejecting negative amounts via `RAISE_APPLICATION_ERROR`. Test both valid and invalid `INSERT`s.

**Task:** Verify whether the DML statement and trigger data are undone when the trigger fails.

### Exercise 8 — Autonomous Logger

Create the `APP_ERROR_LOG` table and a logger procedure with `PRAGMA AUTONOMOUS_TRANSACTION`. Call the logger from an exception handler and then `RAISE` the original error.

**Question:** Does the log entry still exist after the caller executes `ROLLBACK` on the main transaction?

### Exercise 9 — Failing Logger

Temporarily make the logger raise an error. Wrap the logger call in a nested block, then `RAISE` the original exception. Observe the error code received by the caller.

### Exercise 10 — Row-by-Row Batch

Process a staging list. Allow skipping `DUP_VAL_ON_INDEX` but stop on any other error. Record `FAILED`/`SKIPPED`/`SUCCEEDED` status per record and the overall batch status.

## 24. Safe Error Handling Workflow

When writing an exception handler, follow this sequence:

1. Identify which errors are expected business scenarios.
2. Catch specific exceptions that have clear recovery logic separately.
3. For unexpected errors, use `WHEN OTHERS` at an appropriate boundary.
4. Capture `SQLCODE`, `SQLERRM`, error stack, and backtrace before calling the logger.
5. Write logs using a mechanism matching transaction requirements.
6. If the logger fails, prevent the secondary error from masking the original error while maintaining logging monitoring.
7. Use `RAISE` to propagate the original exception when the business operation has not completed.
8. Use `RAISE_APPLICATION_ERROR` only when returning a new business error code is needed.
9. Clarify whether to perform statement rollback, savepoint rollback, or full transaction rollback.
10. Let the transaction-owning layer decide `COMMIT`/`ROLLBACK` per contract.
11. In triggers, allow data validation errors to propagate to the DML statement; never swallow errors.
12. Mark a batch or API as successful only when every contract requirement for success has been met.

Diagram:

~~~text
Exception raised
        |
        v
Known business error?
       /          \
     Yes           No
      |             |
      v             v
Catch specific   WHEN OTHERS at boundary
      |             |
      v             v
Handle per       Capture SQLCODE/SQLERRM/
contract         stack/backtrace
      |             |
      |             v
      |          Log safely
      |             |
      |             v
      |          Did logger fail?
      |             |
      |             v
      |          Protect original error
      |             |
      +------+------+
             |
             v
      Business step complete?
          /          \
        Yes           No
        |              |
        v              v
 Return result per   RAISE or intentional
 transaction contract error mapping
                       |
                       v
             Caller decides rollback
~~~

## 25. Key Takeaways

- `WHEN OTHERS` catches errors not handled by specific handlers; it does not mean the error has been resolved.
- If a handler only logs and finishes, the exception is swallowed and the caller may mistakenly believe the operation succeeded.
- Bare `RAISE` inside an exception handler re-raises the current exception.
- `RAISE_APPLICATION_ERROR` is used to raise application error codes in the `-20000` to `-20999` range.
- `SQLCODE` and `SQLERRM` provide the code and message; `FORMAT_ERROR_STACK` and `FORMAT_ERROR_BACKTRACE` enable deeper tracing.
- A failing DML statement typically rolls back only that statement's effects; earlier changes in the transaction may remain.
- An exception exiting a procedure does not automatically mean the entire transaction was rolled back.
- A trigger raising an exception causes the triggering statement to fail; never swallow data validation errors.
- A same-transaction logger rolls back with the business transaction; an autonomous logger can persist independently but requires careful design.
- The transaction-owning layer must decide `COMMIT`/`ROLLBACK` and final success status.

`WHEN OTHERS` is useful when used as a final boundary to record and propagate errors. A solid handler ensures the caller knows the operation failed, has enough diagnostics to investigate, and can manage the transaction consistently. Never let a log message replace an exception, never treat a procedure returning normally as proof that data committed, and never let a trigger ignore validation failures. When errors propagate properly, rollbacks occur at the right boundaries, and business status reflects reality, the system avoids failed transactions being falsely reported as successful.
