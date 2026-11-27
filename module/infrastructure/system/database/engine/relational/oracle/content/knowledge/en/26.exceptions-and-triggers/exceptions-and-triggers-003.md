# SQLCODE, SQLERRM, FORMAT_ERROR_STACK, and FORMAT_ERROR_BACKTRACE

When an SQL statement or PL/SQL block raises an error, Oracle provides several tools to retrieve diagnostic information. Four tools commonly used in exception handlers are:

- **SQLCODE**: returns the numeric error code of the current exception.
- **SQLERRM**: returns the error message corresponding to the current exception or a specified error code.
- **DBMS_UTILITY.FORMAT_ERROR_STACK**: returns the error stack, i.e., the chain of error messages currently on the stack.
- **DBMS_UTILITY.FORMAT_ERROR_BACKTRACE**: returns the backtrace path from the location where the exception was raised to the handler currently processing it.

These tools complement one another. `SQLCODE` helps classify errors by numeric code; `SQLERRM` provides a short message for the current error; `FORMAT_ERROR_STACK` exposes the error chain; and `FORMAT_ERROR_BACKTRACE` helps locate the PL/SQL line where the error originated, even when the exception is caught in an outer procedure or block.

In triggers, this information is particularly useful because errors can originate inside the trigger itself or inside a procedure called by the trigger, and then propagate back to the triggering `INSERT`/`UPDATE`/`DELETE` statement. A well-designed exception handler captures the necessary diagnostics, preserves the original error when required, and ensures the caller receives an accurate failure signal.

## 1. Exceptions and Exception Handlers

PL/SQL uses exceptions to represent abnormal situations during execution. An exception can come from:
- Oracle Database, such as division by zero or a unique constraint violation.
- A named exception declared in PL/SQL.
- A `RAISE_APPLICATION_ERROR` call explicitly raised by the application.
- An exception re-thrown from a lower-level procedure or function.

Basic structure:

~~~sql
BEGIN
    -- Statements that may raise an error.
EXCEPTION
    WHEN ZERO_DIVIDE THEN
        DBMS_OUTPUT.PUT_LINE('Cannot divide by 0');
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('Other error');
        RAISE;
END;
/
~~~

The `EXCEPTION` section only executes when an exception is raised in the corresponding `BEGIN` section and was not already handled by an inner block.

### 1.1. Exception Handlers Are Scoped by Block

~~~sql
BEGIN
    BEGIN
        -- Inner block.
        RAISE ZERO_DIVIDE;
    EXCEPTION
        WHEN ZERO_DIVIDE THEN
            DBMS_OUTPUT.PUT_LINE('Handled in inner block');
    END;

    DBMS_OUTPUT.PUT_LINE('Outer block continues');
END;
/
~~~

The inner block catches the exception and does not re-raise it, so the outer block continues normally.

If the inner block logs the error and then re-raises it:

~~~sql
BEGIN
    BEGIN
        RAISE ZERO_DIVIDE;
    EXCEPTION
        WHEN OTHERS THEN
            DBMS_OUTPUT.PUT_LINE('Recorded in inner block');
            RAISE;
    END;
EXCEPTION
    WHEN ZERO_DIVIDE THEN
        DBMS_OUTPUT.PUT_LINE('Outer block received ZERO_DIVIDE');
END;
/
~~~

`RAISE` without an exception name inside a handler re-raises the current exception. This is how to preserve the original error when you only want to add logging.

### 1.2. OTHERS Is the Catch-All Handler

`WHEN OTHERS` receives exceptions not handled by the specific branches above it. It is useful for centralized logging, but should not be used to hide errors:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        -- Record error details.
        RAISE;
~~~

If a handler merely prints a message and exits without `RAISE`, the exception is considered handled and the caller may continue as though the subprogram completed normally. Only do that when the program genuinely has a recovery path and the returned result accurately reflects the state.

## 2. SQLCODE

`SQLCODE` is a PL/SQL function that returns the numeric code of the current exception. It is normally called inside an exception handler:

~~~sql
DECLARE
    l_result NUMBER;
BEGIN
    l_result := 10 / 0;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('SQLCODE=' || SQLCODE);
END;
/
~~~

Typical output:

~~~text
SQLCODE=-1476
~~~

Code `-1476` corresponds to `ORA-01476: divisor is equal to zero`.

### 2.1. SQLCODE Inside an Exception Handler

Inside a handler, `SQLCODE` reflects the exception currently being handled. For example:

~~~sql
BEGIN
    INSERT INTO employees(employee_id, full_name)
    VALUES (101, 'An');

EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        DBMS_OUTPUT.PUT_LINE('Code=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('Duplicate key');
END;
/
~~~

If the actual error is a unique constraint violation, `SQLCODE` is typically `-1` (`ORA-00001`).

Do not rely solely on message text to classify errors when error codes are clearer and far more stable for handling logic.

### 2.2. SQLCODE Outside an Exception Handler

If no exception is currently being handled, `SQLCODE` returns `0`:

~~~sql
BEGIN
    DBMS_OUTPUT.PUT_LINE('SQLCODE=' || SQLCODE);
END;
/
~~~

Output:

~~~text
SQLCODE=0
~~~

Therefore, do not use `SQLCODE` as a status variable anywhere to check whether the preceding SQL statement succeeded. It is designed specifically to retrieve the code of the active exception.

### 2.3. Codes of User-Defined Exceptions

An exception declared in PL/SQL:

~~~sql
DECLARE
    e_invalid_state EXCEPTION;
BEGIN
    RAISE e_invalid_state;
EXCEPTION
    WHEN e_invalid_state THEN
        DBMS_OUTPUT.PUT_LINE('SQLCODE=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('SQLERRM=' || SQLERRM);
END;
/
~~~

A user-defined exception not mapped to a specific Oracle error code typically has `SQLCODE = +1` and `SQLERRM` equal to the generic message `"User-Defined Exception"`.

If you want the exception tied to a specific ORA code, use `PRAGMA EXCEPTION_INIT` or `RAISE_APPLICATION_ERROR`.

### 2.4. Exceptions Mapped with EXCEPTION_INIT

~~~sql
DECLARE
    e_business_error EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_business_error, -20041);
BEGIN
    RAISE_APPLICATION_ERROR(-20041, 'Order state is invalid');
EXCEPTION
    WHEN e_business_error THEN
        DBMS_OUTPUT.PUT_LINE('Code=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('Message=' || SQLERRM);
END;
/
~~~

`PRAGMA EXCEPTION_INIT` binds a named exception to an Oracle error code. When a handler catches that exception, `SQLCODE` returns the mapped code.

### 2.5. Using SQLCODE to Classify Errors

You can inspect the code and decide how to handle it:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE = -1 THEN
            DBMS_OUTPUT.PUT_LINE('Duplicate unique key');
        ELSIF SQLCODE = -2291 THEN
            DBMS_OUTPUT.PUT_LINE('Missing parent key');
        ELSE
            RAISE;
        END IF;
~~~

Only handle specific codes that the application clearly understands. All other errors should propagate to the caller so information is not lost.

## 3. SQLERRM

`SQLERRM` returns the error message. Without arguments, it retrieves the message for the current exception:

~~~sql
DECLARE
    l_result NUMBER;
BEGIN
    l_result := 10 / 0;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
END;
/
~~~

Typical output:

~~~text
ORA-01476: divisor is equal to zero
~~~

`SQLERRM` is useful when you need a message for logging or displaying a technical error. However, messages can be localized according to the session's NLS language; do not use the entire message string as a logic key.

### 3.1. SQLERRM Outside an Exception Handler

When calling `SQLERRM` with no active exception, the function returns the message for code `0`, typically:

~~~text
ORA-0000: normal, successful completion
~~~

This does not mean `SQLERRM` can be used to check the success or failure of the previous SQL statement. Call it inside an exception handler to retrieve details of the exception being handled.

### 3.2. SQLERRM with a Specified Error Code

`SQLERRM` can accept an error number to return the corresponding message:

~~~sql
BEGIN
    DBMS_OUTPUT.PUT_LINE(SQLERRM(-1));
    DBMS_OUTPUT.PUT_LINE(SQLERRM(-2291));
END;
/
~~~

This is useful when you want to look up the message for a known Oracle code. It does not reconstruct the stack of a previous failed execution and does not replace `FORMAT_ERROR_STACK`.

### 3.3. SQLERRM Is Not the Full Error Stack

Suppose an error propagates through several layers of procedures. `SQLERRM` generally returns the message for the current exception, such as `ORA-01476`. It is not a complete tool for viewing all `ORA-06512` lines or the entire related error chain.

To retrieve the error chain, use `DBMS_UTILITY.FORMAT_ERROR_STACK`.

### 3.4. Do Not Use SQLERRM String Comparisons for Business Decisions

Avoid writing:

~~~sql
IF SQLERRM = 'ORA-00001: unique constraint violated' THEN
    ...
END IF;
~~~

Messages can vary by language, version, or context. Use `SQLCODE` or catch named exceptions like `DUP_VAL_ON_INDEX` for classification. Use `SQLERRM` to provide diagnostic text for humans.

### 3.5. Message Length

`SQLERRM` returns a message string subject to the API's length limit. When fuller diagnostics are needed, especially with stacked errors, use `FORMAT_ERROR_STACK` and store the result in a sufficiently large `VARCHAR2` variable in PL/SQL.

## 4. DBMS_UTILITY.FORMAT_ERROR_STACK

`DBMS_UTILITY.FORMAT_ERROR_STACK` returns the current error stack as a string. It is helpful when the exception stack contains multiple messages, such as an application error appended on top of an original error.

Syntax:

~~~sql
DBMS_UTILITY.FORMAT_ERROR_STACK
~~~

Example:

~~~sql
DECLARE
    l_result NUMBER;
BEGIN
    l_result := 10 / 0;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_STACK
        );
END;
/
~~~

The output may include `ORA-01476` along with related PL/SQL location lines.

### 4.1. Difference from SQLERRM

| Tool | Primary Information |
| --- | --- |
| SQLCODE | Numeric code of the current exception |
| SQLERRM | Message of the current exception or specified code |
| FORMAT_ERROR_STACK | Current error stack string |
| FORMAT_ERROR_BACKTRACE | Path from the error origin to the handler |

`SQLERRM` is suited when you need a short message. `FORMAT_ERROR_STACK` is suited when you need to record a fuller error chain for diagnostics.

### 4.2. The Error Stack Can Contain Appended Errors

A procedure can catch an error and call `RAISE_APPLICATION_ERROR` to add business context. The third parameter of `RAISE_APPLICATION_ERROR` controls whether the new error is added onto the current error stack or replaces the existing stack.

~~~sql
BEGIN
    RAISE_APPLICATION_ERROR(
        -20041,
        'Unable to complete payment',
        TRUE
    );
END;
/
~~~

When the third parameter is `TRUE`, the application error is appended to the stack. When it is `FALSE` or omitted, the new error replaces the existing stack according to `RAISE_APPLICATION_ERROR` behavior.

When you need to preserve the original error as-is, bare `RAISE` inside the exception handler is usually the simplest approach. If you need to translate the error to a new application code, save the original details before calling `RAISE_APPLICATION_ERROR`.

### 4.3. Do Not Call FORMAT_ERROR_STACK Outside an Error Context to Inspect Preceding Statements

`FORMAT_ERROR_STACK` is designed to retrieve the current error stack. Calling it outside an exception context does not provide a session error history log. To keep a history, the application must write logs at the moment an error is caught.

## 5. DBMS_UTILITY.FORMAT_ERROR_BACKTRACE

`FORMAT_ERROR_BACKTRACE` returns backtrace information from where the exception was raised to the point currently handling the exception.

Syntax:

~~~sql
DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
~~~

Key point: an exception may be caught in an outer procedure, yet the backtrace still pinpoints the inner PL/SQL line where the error started.

### 5.1. Example of an Error Raised in a Child Procedure

Create the child procedure:

~~~sql
CREATE OR REPLACE PROCEDURE divide_demo (
    p_numerator IN NUMBER,
    p_denominator IN NUMBER
) AS
    l_result NUMBER;
BEGIN
    l_result := p_numerator / p_denominator;

    DBMS_OUTPUT.PUT_LINE('Result=' || l_result);
END divide_demo;
/
~~~

Create the calling procedure:

~~~sql
CREATE OR REPLACE PROCEDURE run_divide_demo AS
BEGIN
    divide_demo(10, 0);
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('Code=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('Message=' || SQLERRM);
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END run_divide_demo;
/
~~~

Invoke:

~~~sql
BEGIN
    run_divide_demo;
END;
/
~~~

`SQLCODE` and `SQLERRM` describe the division-by-zero error. `FORMAT_ERROR_BACKTRACE` points to the line in `DIVIDE_DEMO` where the division raised the error and the related call sites. The exact line numbers depend on the actual source stored after creating the procedure.

### 5.2. Backtrace vs. Call Stack

Do not confuse three concepts:

- **Error stack**: the error messages currently held.
- **Error backtrace**: where the exception was raised and its propagation path to the handler.
- **Call stack**: the subprograms active at the moment the call-stack function is invoked.

`DBMS_UTILITY` also provides `FORMAT_CALL_STACK` to inspect the current call stack. `FORMAT_CALL_STACK` answers "which layers are currently calling which"; `FORMAT_ERROR_BACKTRACE` answers "where was the exception raised". The two results can differ if the exception has propagated across multiple layers or the handler runs in a different location.

### 5.3. Capture the Backtrace While Handling the Exception

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        l_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;
        -- Log or propagate the information onward.
        RAISE;
~~~

If you catch an exception without saving its details, do not expect that calling `FORMAT_ERROR_BACKTRACE` elsewhere after leaving the exception handler will recover the old error's backtrace.

### 5.4. Backtrace Helps Locate Errors in Packages and Triggers

A DML statement may pass through:
1. An `UPDATE` statement from the application.
2. A `BEFORE UPDATE` trigger.
3. A procedure called by the trigger.
4. A business validation function.
5. An SQL statement that raises an error.

If the exception is caught in an outer caller layer, the backtrace can identify the relevant PL/SQL lines, helping you pinpoint the right trigger or procedure instead of only seeing that the `UPDATE` failed.

## 6. Comparing the Four Tools

| Tool | Returns | Question Answered |
| --- | --- | --- |
| SQLCODE | NUMBER | What is the error code? |
| SQLERRM | VARCHAR2 | What is the current error message? |
| FORMAT_ERROR_STACK | VARCHAR2 | What is currently in the error message stack? |
| FORMAT_ERROR_BACKTRACE | VARCHAR2 | Which line raised the exception and how did it reach the handler? |

A solid logging handler usually captures all four pieces of information:

~~~sql
DECLARE
    l_code      NUMBER;
    l_message   VARCHAR2(4000);
    l_stack     VARCHAR2(32767);
    l_backtrace VARCHAR2(32767);
BEGIN
    -- Work that may raise an error.
    RAISE_APPLICATION_ERROR(-20041, 'Invalid order state');

EXCEPTION
    WHEN OTHERS THEN
        l_code      := SQLCODE;
        l_message   := SQLERRM;
        l_stack     := DBMS_UTILITY.FORMAT_ERROR_STACK;
        l_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        DBMS_OUTPUT.PUT_LINE('Code: ' || l_code);
        DBMS_OUTPUT.PUT_LINE('Message: ' || l_message);
        DBMS_OUTPUT.PUT_LINE('Error stack: ' || l_stack);
        DBMS_OUTPUT.PUT_LINE('Backtrace: ' || l_backtrace);

        RAISE;
END;
/
~~~

Local variables preserve the diagnostic data before performing further actions. In real applications, write logs to a system-managed logger; `DBMS_OUTPUT` is only appropriate for demos or debugging in interactive tools.

## 7. Order of Capturing Information in WHEN OTHERS

When an exception occurs, capture diagnostics right at the top of the handler:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        l_code      := SQLCODE;
        l_message   := SQLERRM;
        l_stack     := DBMS_UTILITY.FORMAT_ERROR_STACK;
        l_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        -- Only afterward call the logger or perform additional handling.
        RAISE;
~~~

Reasons:
- This is the point where the exception context is clearest.
- The logger or auxiliary procedures might raise another error.
- If a new error replaces the old one, the original details are already saved in variables.
- You can pass the captured diagnostic data to the logger instead of calling `SQLCODE`/`SQLERRM` again in a different context.

### 7.1. Do Not Let the Logger Mask the Original Error

Suppose an exception handler calls a logging procedure, and that procedure also raises an error. If the logging error escapes, the caller may only see the logger error instead of the original business error.

You can isolate logger errors:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        l_code      := SQLCODE;
        l_message   := SQLERRM;
        l_stack     := DBMS_UTILITY.FORMAT_ERROR_STACK;
        l_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        BEGIN
            error_log_api.write_error(
                p_code      => l_code,
                p_message   => l_message,
                p_stack     => l_stack,
                p_backtrace => l_backtrace
            );
        EXCEPTION
            WHEN OTHERS THEN
                NULL; -- Logger failed; do not replace the original error.
        END;

        RAISE;
~~~

This is an illustrative pattern. In production, ignoring logger errors must be a deliberate decision: another monitoring channel is needed so logs are never silently lost altogether. After logging or handling logger failure, bare `RAISE` preserves the outer handler's original exception.

### 7.2. Do Not Log and Then Swallow the Error

Dangerous pattern:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
        -- No RAISE, no failure status returned.
END;
~~~

The caller may assume the operation succeeded even though data was only partially updated or not updated at all. If you intend to handle the error and continue, define the output, state, and transaction boundaries explicitly.

## 8. RAISE and RAISE_APPLICATION_ERROR

These two statements have different roles.

### 8.1. Bare RAISE (Without Arguments)

Inside an exception handler:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        -- Record diagnostics.
        RAISE;
~~~

Bare `RAISE` re-throws the current exception. This is the right choice when you only want to log or clean up and then let the caller handle the original error.

### 8.2. RAISE with a Named Exception

You can explicitly raise a declared exception:

~~~sql
DECLARE
    e_invalid_amount EXCEPTION;
BEGIN
    RAISE e_invalid_amount;
EXCEPTION
    WHEN e_invalid_amount THEN
        DBMS_OUTPUT.PUT_LINE(SQLCODE);
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
END;
/
~~~

A user-defined exception does not have its own Oracle error code by default. If you need a specific application code, use `RAISE_APPLICATION_ERROR` or `EXCEPTION_INIT`.

### 8.3. RAISE_APPLICATION_ERROR

Syntax:

~~~sql
RAISE_APPLICATION_ERROR(
    error_code,
    message,
    keep_errors
);
~~~

- `error_code` must be in the range `-20000` to `-20999`.
- `message` is the application message.
- `keep_errors` is optional, defaulting to `FALSE`. `TRUE` adds the new error onto the existing error stack; `FALSE` replaces the existing stack per the command's behavior.

Example:

~~~sql
IF p_amount <= 0 THEN
    RAISE_APPLICATION_ERROR(
        -20041,
        'Amount must be greater than zero'
    );
END IF;
~~~

Using dedicated error codes helps the caller distinguish business errors from Oracle system errors.

### 8.4. Wrapping the Original Error with a Business Code

~~~sql
BEGIN
    perform_payment;
EXCEPTION
    WHEN OTHERS THEN
        l_stack     := DBMS_UTILITY.FORMAT_ERROR_STACK;
        l_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        -- You can log l_stack and l_backtrace before wrapping the error.
        RAISE_APPLICATION_ERROR(
            -20050,
            'Payment processing failed',
            TRUE
        );
END;
~~~

When `TRUE` is used, the application error is pushed onto the stack rather than discarding prior errors. The caller receives the business message while the error stack retains previously added error details. Verify the actual stack behavior in your Oracle version and client.

If you only need to pass the original exception upward as-is, use bare `RAISE` instead of raising a new error.

## 9. Exceptions in Triggers

A trigger is a PL/SQL subprogram automatically invoked by Oracle when the corresponding event occurs. A trigger can raise exceptions in cases such as:
- Invalid business rule checks.
- Constraint violations or DML errors inside the trigger.
- Errors raised by a procedure or function called by the trigger.
- Data conversion errors or other runtime failures.

Example of a `BEFORE INSERT` trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_validate_amount
BEFORE INSERT OR UPDATE OF amount ON orders
FOR EACH ROW
BEGIN
    IF :NEW.amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20041,
            'Order amount cannot be negative'
        );
    END IF;
END;
/
~~~

If the application inserts an order with a negative `AMOUNT`, the trigger raises an error and the DML statement fails.

### 9.1. Catching Trigger Errors at the DML Caller Layer

~~~sql
BEGIN
    INSERT INTO orders(order_id, amount)
    VALUES (9001, -100);
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('Code=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('Message=' || SQLERRM);
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_STACK
        );
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END;
/
~~~

The backtrace can point to the `RAISE_APPLICATION_ERROR` line inside the trigger and related PL/SQL locations. The error returned to the client remains the failure of the `INSERT` statement that fired the trigger.

### 9.2. Exceptions Raised from a Procedure Called by a Trigger

Example of a trigger calling a procedure:

~~~sql
CREATE OR REPLACE PROCEDURE validate_order_amount (
    p_amount IN NUMBER
) AS
BEGIN
    IF p_amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20042,
            'Invalid amount from validation procedure'
        );
    END IF;
END;
/
~~~

Trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_validate_amount
BEFORE INSERT OR UPDATE OF amount ON orders
FOR EACH ROW
BEGIN
    validate_order_amount(:NEW.amount);
END;
/
~~~

When the procedure raises an error, the exception propagates through the trigger back to the DML statement. `FORMAT_ERROR_BACKTRACE` helps trace the location inside both the procedure and the trigger.

### 9.3. Triggers Can Handle Internal Exceptions

A trigger may catch a specific exception if it has a valid recovery path. However, if the error represents a business rule violation under which the DML must not proceed, the trigger must propagate the error to the caller.

Do not write `WHEN OTHERS` and ignore the exception inside a trigger merely to let `INSERT`/`UPDATE` succeed. Doing so can allow invalid data violating business rules to be written to the table.

### 9.4. Do Not COMMIT or ROLLBACK Inside a Normal Trigger

A normal trigger executes inside the transaction of the DML statement that fired it. Do not `COMMIT` or `ROLLBACK` the transaction inside a normal trigger; Oracle does not allow ending the caller's transaction from a trigger in that way.

If independent auditing is needed even when DML fails, consider an autonomous transaction for a dedicated logger. This is a special design choice requiring care because the independent log persists even if the parent DML rolls back. Never use autonomous transactions to write primary business changes.

### 9.5. Statement Rollback vs. Transaction Rollback

If a trigger raises an error, the DML statement that fired the trigger fails and changes belonging to that statement are rolled back under statement atomicity. This does not automatically mean the entire preceding transaction is rolled back.

Example:
1. `UPDATE A` succeeds but has not been committed yet.
2. `INSERT B` fires a trigger and fails.
3. `INSERT B` and changes belonging to that statement are rolled back.
4. The earlier `UPDATE A` can still remain active in the transaction.
5. The caller decides whether to continue or `ROLLBACK` the entire transaction.

The application must manage errors and transaction boundaries explicitly; do not assume a trigger failure automatically undoes all earlier DML.

## 10. Structured Error Logging

A useful logger should capture at least:
- Timestamp of logging.
- Error code.
- Message.
- Error stack.
- Backtrace.
- Module/procedure name or correlation ID, if available.
- Non-sensitive business context, such as order ID.
- Appropriate session/application identifier.

Example log table:

~~~sql
CREATE TABLE application_error_log (
    log_id       NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    logged_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    error_code   NUMBER,
    error_message VARCHAR2(4000),
    error_stack  CLOB,
    error_backtrace CLOB,
    module_name  VARCHAR2(128),
    reference_id VARCHAR2(100)
);
~~~

A logging procedure can accept the captured diagnostics:

~~~sql
CREATE OR REPLACE PROCEDURE write_application_error (
    p_error_code      IN NUMBER,
    p_error_message   IN VARCHAR2,
    p_error_stack     IN VARCHAR2,
    p_error_backtrace IN VARCHAR2,
    p_reference_id    IN VARCHAR2
) AS
BEGIN
    INSERT INTO application_error_log (
        error_code,
        error_message,
        error_stack,
        error_backtrace,
        reference_id
    )
    VALUES (
        p_error_code,
        p_error_message,
        p_error_stack,
        p_error_backtrace,
        p_reference_id
    );
END;
/
~~~

Example call inside a handler:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        l_code      := SQLCODE;
        l_message   := SQLERRM;
        l_stack     := DBMS_UTILITY.FORMAT_ERROR_STACK;
        l_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        write_application_error(
            l_code,
            l_message,
            l_stack,
            l_backtrace,
            p_order_id
        );

        RAISE;
~~~

This snippet illustrates the capture flow. Because the log `INSERT` belongs to the current transaction, if the caller executes `ROLLBACK`, the log record will also roll back. If logs must survive independently of the business transaction, design an autonomous transaction logger or ship logs to an external logging system.

### 10.1. Logging in the Same Transaction

Advantages:
- Logs and business data `COMMIT`/`ROLLBACK` together.
- No misleading logs remain if the parent transaction rolls back.
- Does not require an autonomous transaction.

Limitations:
- When the transaction rolls back, logs in the same transaction disappear as well.
- Unsuitable if the goal is to retain records of every failure even when the caller rolls back.

### 10.2. Logging Using an Autonomous Transaction

An independent logger can be declared as:

~~~sql
CREATE OR REPLACE PROCEDURE write_error_independent (
    p_error_code IN NUMBER,
    p_message IN VARCHAR2
) AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO application_error_log (
        error_code,
        error_message
    )
    VALUES (
        p_error_code,
        p_message
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

An autonomous transaction has its own transaction boundary. The `COMMIT` inside the logger does not commit the parent transaction.

Keep in mind:
- An independent logger can record errors even if the parent transaction rolls back.
- Do not access or wait on resources locked by the parent transaction in a way that could cause a deadlock.
- The logger must be brief and reliable.
- If the logger fails, decide whether the logging error should replace the original error.
- Do not use autonomous transactions for business DML that should roll back along with the parent statement.

## 11. Nested Exceptions and Preserving Error Details

An exception may be caught at multiple layers. If each layer catches it and throws a new exception, the error stack/backtrace can change.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE step_three AS
BEGIN
    RAISE_APPLICATION_ERROR(-20061, 'Failure in step three');
END;
/

CREATE OR REPLACE PROCEDURE step_two AS
BEGIN
    step_three;
EXCEPTION
    WHEN OTHERS THEN
        -- Log at the intermediate layer.
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END;
/

CREATE OR REPLACE PROCEDURE step_one AS
BEGIN
    step_two;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(SQLCODE);
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_STACK
        );
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END;
/
~~~

`STEP_THREE` raises the error. `STEP_TWO` catches and re-`RAISE`s it. `STEP_ONE` catches it next, extracts diagnostics, and re-`RAISE`s it. The final caller still receives the exception.

### 11.1. RAISE Preserves the Current Exception

Inside a handler:

~~~sql
RAISE;
~~~

should be used when passing the current exception up to a higher layer without changing the error type.

### 11.2. RAISE with a Different Exception Changes the Propagating Error

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        RAISE e_application_failure;
~~~

This statement raises `E_APPLICATION_FAILURE` at the `RAISE` line. If the goal is to preserve the original error, do not replace it with a different exception. Save diagnostics before translating and use `RAISE_APPLICATION_ERROR` with `keep_errors` appropriately when adding context.

### 11.3. Capture Backtrace Before Wrapping the Error

If a handler calls `RAISE_APPLICATION_ERROR` to raise a new code, the backtrace afterward may reflect the new raise point. Therefore, if you need the original failure line, capture `FORMAT_ERROR_BACKTRACE` before wrapping.

## 12. FORMAT_ERROR_STACK and FORMAT_ERROR_BACKTRACE in Packages

A package can provide a shared helper to read diagnostics:

~~~sql
CREATE OR REPLACE PACKAGE error_diagnostics AS
    PROCEDURE print_current_error;
END error_diagnostics;
/
~~~

Body:

~~~sql
CREATE OR REPLACE PACKAGE BODY error_diagnostics AS
    PROCEDURE print_current_error IS
        l_code      NUMBER;
        l_message   VARCHAR2(4000);
        l_stack     VARCHAR2(32767);
        l_backtrace VARCHAR2(32767);
    BEGIN
        l_code      := SQLCODE;
        l_message   := SQLERRM;
        l_stack     := DBMS_UTILITY.FORMAT_ERROR_STACK;
        l_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        DBMS_OUTPUT.PUT_LINE('Code=' || l_code);
        DBMS_OUTPUT.PUT_LINE('Message=' || l_message);
        DBMS_OUTPUT.PUT_LINE('Stack=' || l_stack);
        DBMS_OUTPUT.PUT_LINE('Backtrace=' || l_backtrace);
    END print_current_error;
END error_diagnostics;
/
~~~

Call the helper inside an exception handler:

~~~sql
BEGIN
    -- Work.
    RAISE ZERO_DIVIDE;
EXCEPTION
    WHEN OTHERS THEN
        error_diagnostics.print_current_error;
        RAISE;
END;
/
~~~

The helper is invoked while the exception is active. In production applications, pass the already captured values into the logger to avoid depending on exception context state across nested calls.

## 13. SQLCODE/SQLERRM and Exception Mapping

Oracle defines several predefined exceptions, for example:
- `NO_DATA_FOUND`.
- `TOO_MANY_ROWS`.
- `ZERO_DIVIDE`.
- `DUP_VAL_ON_INDEX`.
- `INVALID_NUMBER`.
- `VALUE_ERROR`.
- `OTHERS` is the catch-all handler, not a specific exception.

You can catch exceptions by name:

~~~sql
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        ...
    WHEN DUP_VAL_ON_INDEX THEN
        ...
    WHEN OTHERS THEN
        ...
~~~

For Oracle error codes without a suitable predefined exception, declare an exception and map it using `PRAGMA EXCEPTION_INIT`:

~~~sql
DECLARE
    e_parent_missing EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_parent_missing, -2291);
BEGIN
    -- DML that may violate a foreign key.
    NULL;
EXCEPTION
    WHEN e_parent_missing THEN
        DBMS_OUTPUT.PUT_LINE(SQLCODE);
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
END;
/
~~~

Do not map an arbitrary exception to an unrelated code. The code must reflect the Oracle error the handler intends to catch.

### 13.1. SQLCODE and SQLERRM in OTHERS

Inside `WHEN OTHERS`, the two functions retrieve details of the active exception:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        l_code := SQLCODE;
        l_message := SQLERRM;
        RAISE;
~~~

There is no need to check `SQLCODE` before calling `SQLERRM`. Capturing both right at the start of the handler is usually the clearest approach.

### 13.2. SQLERRM with User-Defined Errors

For an exception raised via `RAISE e_name` without a mapped code, `SQLERRM` typically returns only `"User-Defined Exception"`. If a specific message is needed, use `RAISE_APPLICATION_ERROR` or store the business code/message in variables or context.

## 14. Error Stack, Backtrace, and Call Stack: Example Distinction

Suppose the call flow is:

~~~text
CLIENT
  |
  v
PROCEDURE PROCESS_ORDER
  |
  v
PACKAGE VALIDATION_PKG.CHECK_ORDER
  |
  v
TRIGGER TRG_ORDER_VALIDATE
  |
  v
FUNCTION CHECK_LIMIT
  |
  v
ORA-20071 is raised
~~~

If the error propagates up to `PROCESS_ORDER`:

- `SQLCODE`: numeric code of the exception being caught, e.g., `-20071`.
- `SQLERRM`: message of the current exception.
- `FORMAT_ERROR_STACK`: error messages currently on the stack.
- `FORMAT_ERROR_BACKTRACE`: PL/SQL locations from where the exception was raised to the handler.
- `FORMAT_CALL_STACK`: subprograms active at the moment the function is called; this may differ from the backtrace.

### 14.1. Do Not Confuse Error Stack with Backtrace

Error stack answers: **Which errors is Oracle currently reporting?**

Backtrace answers: **Which line did the error start on?**

Call stack answers: **Through which layers is the code currently being called?**

When investigating complex failures, log both the error stack and the backtrace. If you also need to understand the current execution context, record `FORMAT_CALL_STACK` as well.

## 15. Notes on Logging in Triggers

Triggers execute within the context of the caller's DML statement. Logging inside triggers requires careful design.

### 15.1. DBMS_OUTPUT Is Not a Production Logging System

`DBMS_OUTPUT`:
- Does not write to a log table automatically.
- May not be enabled or read by the client.
- Is not a reliable monitoring channel for background applications.
- Should not be the sole way production errors are stored.

Use a logging API or monitoring mechanism appropriate for your system.

### 15.2. Triggers Should Not Hide Errors

If a trigger detects invalid data, it can raise an application code:

~~~sql
RAISE_APPLICATION_ERROR(
    -20071,
    'Order state transition is not allowed'
);
~~~

Do not catch `OTHERS` and continue writing data if the condition must be enforced.

### 15.3. Avoid Side Effects That Cannot Roll Back

If a trigger sends an email or makes an HTTP call and the DML statement later fails, external side effects cannot be rolled back by Oracle. A safer design is to write an event into an outbox table in the same transaction; a worker sends it only after the transaction commits.

### 15.4. Autonomous Logging Can Persist After Rollback

An autonomous logger can record an error even if the parent DML fails. However, the log should clearly indicate that the business transaction failed or did not commit. Do not record a log entry as if the data change had been confirmed.

## 16. Comprehensive Practical Example: Trigger Errors and Backtrace

Create the sandbox table:

~~~sql
CREATE TABLE error_demo_orders (
    order_id NUMBER PRIMARY KEY,
    amount   NUMBER NOT NULL
);
~~~

Create the validation procedure:

~~~sql
CREATE OR REPLACE PROCEDURE validate_demo_amount (
    p_amount IN NUMBER
) AS
BEGIN
    IF p_amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20081,
            'Amount must not be negative'
        );
    END IF;
END;
/
~~~

Create the trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_error_demo_orders
BEFORE INSERT OR UPDATE OF amount
ON error_demo_orders
FOR EACH ROW
BEGIN
    validate_demo_amount(:NEW.amount);
END;
/
~~~

Try a valid DML statement:

~~~sql
INSERT INTO error_demo_orders(order_id, amount)
VALUES (1, 100);

COMMIT;
~~~

Try an invalid DML statement:

~~~sql
DECLARE
    l_code      NUMBER;
    l_message   VARCHAR2(4000);
    l_stack     VARCHAR2(32767);
    l_backtrace VARCHAR2(32767);
BEGIN
    INSERT INTO error_demo_orders(order_id, amount)
    VALUES (2, -50);

EXCEPTION
    WHEN OTHERS THEN
        l_code      := SQLCODE;
        l_message   := SQLERRM;
        l_stack     := DBMS_UTILITY.FORMAT_ERROR_STACK;
        l_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        DBMS_OUTPUT.PUT_LINE('SQLCODE=' || l_code);
        DBMS_OUTPUT.PUT_LINE('SQLERRM=' || l_message);
        DBMS_OUTPUT.PUT_LINE('STACK=' || l_stack);
        DBMS_OUTPUT.PUT_LINE('BACKTRACE=' || l_backtrace);

        RAISE;
END;
/
~~~

Expected result:
- `SQLCODE` is `-20081`.
- `SQLERRM` contains the message `Amount must not be negative`.
- Error stack contains the application error and related Oracle error details.
- Backtrace helps locate the raising line inside the procedure or trigger.

The second `INSERT` fails. Row `ORDER_ID=2` is not inserted. Row `ORDER_ID=1`, previously committed, still remains.

### 16.1. Verify the Data

~~~sql
SELECT *
FROM error_demo_orders
ORDER BY order_id;
~~~

Only row `1` is returned.

### 16.2. Clean Up the Sandbox

~~~sql
DROP TRIGGER trg_error_demo_orders;
DROP PROCEDURE validate_demo_amount;
DROP TABLE error_demo_orders PURGE;
~~~

Only drop the sandbox objects created by this lesson when you are sure the data is no longer needed. `DROP` is DDL and follows implicit commit rules; perform cleanup separately.

## 17. Exception Handling Workflow in Procedures, Packages, and Triggers

A practical workflow may include:

1. Catch specific exceptions when there is a clear recovery strategy.
2. For unexpected errors, use `WHEN OTHERS` at an appropriate boundary.
3. Right at the top of the handler, capture `SQLCODE` and `SQLERRM`.
4. Capture `FORMAT_ERROR_STACK` to preserve the error chain.
5. Capture `FORMAT_ERROR_BACKTRACE` to preserve the origin location.
6. Log alongside the correlation ID and required business context.
7. If the logger might fail, protect the original error according to logging policy.
8. Use `RAISE` to propagate the original exception if the layer cannot handle it.
9. Use `RAISE_APPLICATION_ERROR` only when translating to an application error code or adding a business message.
10. Do not `COMMIT`/`ROLLBACK` inside a normal trigger.
11. Clearly distinguish statement rollback from transaction rollback.
12. Let the caller or transaction manager decide `COMMIT`/`ROLLBACK` per business unit of work.

## 18. Common Misconceptions

**SQLCODE always returns the session's most recent error code.** False. Outside an exception context, `SQLCODE` returns `0`; inside a handler, it describes the exception currently being handled.

**SQLERRM is the entire error stack.** False. It returns the message of the current exception or a specified code; use `FORMAT_ERROR_STACK` to obtain the full stack.

**FORMAT_ERROR_STACK tells you the exact line of code that caused the error.** That is not its primary purpose. Use `FORMAT_ERROR_BACKTRACE` to get the location where the exception was raised.

**FORMAT_ERROR_BACKTRACE is the same as FORMAT_CALL_STACK.** False. Backtrace describes the exception's propagation path; call stack describes active calls at the moment it is invoked.

**Catching OTHERS means the error is handled.** Only true if the handler genuinely recovers and accurately represents success/failure. Otherwise, re-`RAISE`.

**RAISE; and RAISE e_name; have the same effect.** False. Bare `RAISE` re-throws the current exception; `RAISE` with an exception name throws the specified exception.

**SQLERRM should be compared as a string to classify errors.** Avoid this. Use `SQLCODE` or named exceptions; messages can depend on NLS settings.

**NULL always selects a specific overload.** False. An untyped `NULL` can make overloaded calls ambiguous; use `CAST` or a typed variable.

**RAISE_APPLICATION_ERROR always keeps prior errors.** False. Its third parameter determines how the existing stack is handled; `TRUE` appends to the stack, while `FALSE` replaces the existing stack.

**Writing to DBMS_OUTPUT is enough for production.** False. `DBMS_OUTPUT` depends on the client and is not a durable logging system.

**It is safe for a trigger to catch OTHERS and ignore errors.** False if the error indicates a business rule violation; invalid data may be written in a corrupted state.

**A trigger can COMMIT to preserve logs.** False for normal triggers. If independent logs are needed, design an intentional autonomous logger.

**A trigger failure always rolls back the entire transaction.** False. The failing DML statement is rolled back by statement atomicity; earlier statements in the transaction may still persist.

**A caller's ROLLBACK always deletes autonomous logs.** False. An autonomous transaction commits independently, so the log remains.

**Calling backtrace after leaving a handler still recovers the old error.** Do not assume this. Capture the backtrace immediately inside the handler.

## 19. Self-Practice Exercises

1. Create an anonymous block that divides 10 by 0 and prints `SQLCODE`.
2. Print `SQLERRM` inside `WHEN OTHERS` and explain the message.
3. Call `SQLCODE` outside an exception handler. What is the result?
4. Call `SQLERRM` outside an exception handler. Why does the message not describe the previous error?
5. Create a user-defined exception and observe `SQLCODE`/`SQLERRM`.
6. Use `PRAGMA EXCEPTION_INIT` to map an exception to `-20041`.
7. Trigger an `ORA-00001` error and catch it with `DUP_VAL_ON_INDEX`.
8. Compare `SQLERRM` with `DBMS_UTILITY.FORMAT_ERROR_STACK`.
9. Create a child procedure that raises an error and a parent procedure that catches it.
10. Print `FORMAT_ERROR_BACKTRACE` in the parent procedure. Which location does it point to?
11. Compare `FORMAT_ERROR_BACKTRACE` and `FORMAT_CALL_STACK`.
12. Create two procedure layers and use `RAISE` to propagate the original exception.
13. Replace `RAISE` with `RAISE e_name`. Observe the difference.
14. Use `RAISE_APPLICATION_ERROR` with code `-20050`.
15. Test `TRUE` and `FALSE` as the third parameter when errors are already on the stack.
16. Why should you capture the backtrace before wrapping an exception?
17. Create a log table containing error code, message, stack, and backtrace.
18. Write a logger procedure that accepts diagnostics via named parameters.
19. Call the logger inside `WHEN OTHERS` and then re-`RAISE`.
20. Force an error inside the logger and verify how the original exception is protected.
21. Create a `BEFORE INSERT` trigger that rejects negative amounts using `RAISE_APPLICATION_ERROR`.
22. Catch the DML error from the trigger in an anonymous block and print all four diagnostic values.
23. Create a trigger that calls a validation procedure and raises the error inside the procedure. Which layers does the backtrace display?
24. Explain why you do not `COMMIT`/`ROLLBACK` inside a normal trigger.
25. An `INSERT` fails in a trigger. Are preceding successful DML statements in the transaction rolled back?
26. Compare same-transaction logging with autonomous transaction logging.
27. Why can an autonomous logger write logs even if the parent DML rolls back?
28. Design a way to record a correlation ID linking errors across the application, package, and trigger.
29. When should you catch specific exceptions rather than using only `OTHERS`?
30. Design a production handler that preserves the original error, saves the error stack/backtrace, and returns an appropriate business error code.

**SQLCODE provides the exception code, SQLERRM provides the message, FORMAT_ERROR_STACK preserves the error chain, and FORMAT_ERROR_BACKTRACE pinpoints where the exception was raised.** Capture these values immediately inside the handler, log them in a consistent structure, and use `RAISE` when propagating the original error to the caller. With triggers, remember that an error fails the triggering DML statement; the overall transaction remains managed by the caller.
