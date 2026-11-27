# RAISE, RAISE_APPLICATION_ERROR, and Preserving Root Cause Information in Oracle

## 1. Why Do We Need to Raise and Preserve Exceptions?

In PL/SQL, an exception signals that an operation cannot continue along its normal execution path. Errors can originate from Oracle Database—such as a unique constraint violation, no rows found, or a conversion error—or from application-defined business rules, such as order quantity exceeding inventory or a closed account.

When handling errors, a program needs to answer three questions:

1. **What error occurred?** Which error code and message describe the issue?
2. **Where did the error start?** Which PL/SQL line or call originally raised the error?
3. **Which layers did the error pass through?** Which procedures, packages, triggers, or applications caught it, added context, or propagated it further?

PL/SQL provides two common ways to raise errors:

- `RAISE`: raises a declared exception or re-raises the current exception inside a handler.
- `RAISE_APPLICATION_ERROR`: raises an application-defined error code and message, commonly used to report business errors to the caller.

Example:

```sql
CREATE OR REPLACE PROCEDURE validate_order_amount (
    p_amount IN NUMBER
) AS
BEGIN
    IF p_amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Order amount cannot be negative'
        );
    END IF;
END validate_order_amount;
/
```

When the caller passes a negative amount, the procedure raises application error `ORA-20001`. The caller can catch this error, display an appropriate message, or log it.

However, when an exception has already occurred and the program only wants to add context, how it re-raises matters greatly. Using `RAISE;` inside a handler re-raises the current exception and preserves the original error details. Using `RAISE_APPLICATION_ERROR(..., TRUE)` can append an application error onto the existing error stack. Replacing the original error with a generic message without preserving the stack or backtrace can wipe out diagnostic information.

This lesson belongs to the **Exceptions and Triggers** chapter, focusing on `RAISE`, `RAISE_APPLICATION_ERROR`, exception propagation, the error stack, backtrace, logging practices, adding context while preserving root cause, and handling errors raised from triggers.

## 2. Exceptions in PL/SQL

An exception is an abnormal condition that interrupts normal execution flow. When an exception is raised, PL/SQL searches for a matching handler in the current block. If none is found, the exception propagates to the enclosing block or caller.

A block has the following structure:

```sql
DECLARE
    -- Variables and exception declarations
BEGIN
    -- Executable statements
EXCEPTION
    WHEN some_exception THEN
        -- Handle the exception
    WHEN OTHERS THEN
        -- Handle remaining exceptions
END;
/
```

Exception categories:

- **Predefined exceptions:** names defined by Oracle, such as `NO_DATA_FOUND`, `TOO_MANY_ROWS`, `DUP_VAL_ON_INDEX`, and `ZERO_DIVIDE`.
- **User-defined exceptions:** declared by the developer with `EXCEPTION` in PL/SQL.
- **Non-predefined Oracle errors:** Oracle errors that have an error code but no corresponding predefined name in the program; they can be mapped using `PRAGMA EXCEPTION_INIT`.

### 2.1. How Are Exceptions Raised?

Exceptions can be raised automatically:

```sql
DECLARE
    v_result NUMBER;
BEGIN
    v_result := 10 / 0;
EXCEPTION
    WHEN ZERO_DIVIDE THEN
        DBMS_OUTPUT.PUT_LINE('Cannot divide by zero');
END;
/
```

Or raised explicitly by the program:

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
        DBMS_OUTPUT.PUT_LINE('Quantity must be non-negative');
END;
/
```

`RAISE` does not create an arbitrary ORA code. It raises a declared exception. If you need an application error code recognizable through SQL/JDBC, use `RAISE_APPLICATION_ERROR`.

## 3. RAISE: Raising a Declared Exception

### 3.1. Syntax

```sql
RAISE exception_name;
```

`exception_name` must be an exception declared in the current scope or validly referenced from an outer scope.

Example:

```sql
DECLARE
    e_insufficient_stock EXCEPTION;
    v_available NUMBER := 2;
    v_requested NUMBER := 5;
BEGIN
    IF v_requested > v_available THEN
        RAISE e_insufficient_stock;
    END IF;
EXCEPTION
    WHEN e_insufficient_stock THEN
        DBMS_OUTPUT.PUT_LINE('Not enough stock');
END;
/
```

### 3.2. User-Defined Exceptions Have No Custom Business ORA Code

User-defined exceptions help name business conditions inside PL/SQL:

```sql
DECLARE
    e_account_closed EXCEPTION;
    v_status VARCHAR2(20) := 'CLOSED';
BEGIN
    IF v_status = 'CLOSED' THEN
        RAISE e_account_closed;
    END IF;
EXCEPTION
    WHEN e_account_closed THEN
        DBMS_OUTPUT.PUT_LINE('Account is closed');
END;
/
```

If the exception is unhandled in PL/SQL, the caller may receive a generic error for an unhandled user-defined exception, typically `ORA-06510`. If you need a stable application code, use `RAISE_APPLICATION_ERROR` or map the exception to an error code by design.

### 3.3. Using RAISE Inside a Handler to Re-Raise the Current Error

This is the most important way to preserve the original error:

```sql
BEGIN
    -- An operation that may raise an exception.
    NULL;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Error=' || SQLCODE || ': ' || SQLERRM
        );
        RAISE;
END;
/
```

Inside an exception handler, `RAISE;` without an exception name re-raises the exception currently being handled. It preserves the current exception instead of creating a new named exception.

Use the bare form when your goal is to:

- Log the error and let the caller handle it further.
- Perform cleanup and propagate the error to an upper layer.
- Add observability without changing the error's meaning.
- Ensure the transaction or external API knows the operation failed.

### 3.4. Distinguishing RAISE; from RAISE exception_name;

The two statements have different purposes:

```sql
EXCEPTION
    WHEN OTHERS THEN
        RAISE;
```

Re-raises the current exception in the handler. This is the right choice when preserving the error being handled.

```sql
EXCEPTION
    WHEN OTHERS THEN
        RAISE e_another_error;
```

Raises the exception named `e_another_error`. This is a newly named exception, which can alter the error's meaning and backtrace location. Do not treat the second form as equivalent to `RAISE;`.

If you need to translate the error type, do so intentionally and preserve the root cause via the error stack or logging.

### 3.5. Raising Exceptions on Any Appropriate Logic Branch

```sql
CREATE OR REPLACE PROCEDURE validate_transfer (
    p_amount IN NUMBER,
    p_balance IN NUMBER
) AS
    e_invalid_amount EXCEPTION;
    e_insufficient_balance EXCEPTION;
BEGIN
    IF p_amount <= 0 THEN
        RAISE e_invalid_amount;
    END IF;

    IF p_amount > p_balance THEN
        RAISE e_insufficient_balance;
    END IF;
END validate_transfer;
/
```

An exception handler can be placed in the procedure or in the caller. If the procedure does not catch the exception, it propagates to the caller.

## 4. RAISE_APPLICATION_ERROR: Raising Application Errors with Custom Codes

### 4.1. Syntax

```sql
RAISE_APPLICATION_ERROR(
    error_code,
    message
    [, keep_errors]
);
```

Where:

- `error_code`: a negative integer in the range `-20000` to `-20999`.
- `message`: the application error message, up to 2048 bytes.
- `keep_errors`: optional Boolean. `TRUE` pushes the application error onto the current error stack; `FALSE` replaces the current error stack. The default is `FALSE`.

Example:

```sql
BEGIN
    RAISE_APPLICATION_ERROR(
        -20001,
        'Customer is not eligible for this operation'
    );
END;
/
```

The caller receives Oracle error code `ORA-20001` along with the message.

### 4.2. Application Error Code Range

| Range | Meaning |
|---|---|
| `-20000` to `-20999` | Code range reserved for application-defined errors via `RAISE_APPLICATION_ERROR` |
| Other ORA codes | Oracle errors or errors from other components; do not pick arbitrarily as application codes |

Do not pass codes outside the allowed range to `RAISE_APPLICATION_ERROR`; Oracle will raise an invalid argument error.

### 4.3. Business Validation Example

```sql
CREATE OR REPLACE PROCEDURE create_payment (
    p_amount IN NUMBER
) AS
BEGIN
    IF p_amount IS NULL THEN
        RAISE_APPLICATION_ERROR(
            -20010,
            'Payment amount is required'
        );
    END IF;

    IF p_amount <= 0 THEN
        RAISE_APPLICATION_ERROR(
            -20011,
            'Payment amount must be greater than zero'
        );
    END IF;

    -- Execute payment creation steps here.
END create_payment;
/
```

The two business conditions have distinct codes, allowing the caller to distinguish missing input from an invalid value.

### 4.4. Choosing Stable Error Codes

Application error codes should follow a centralized convention, for example:

| Example Code | Meaning |
|---:|---|
| `-20010` | Missing required input |
| `-20011` | Invalid input value |
| `-20020` | Business entity not found |
| `-20021` | Current state does not allow the operation |
| `-20030` | Business limit violation |

This is only an illustrative convention. In real systems, manage codes in API documentation or a constants package so two modules do not assign the same code to different meanings.

### 4.5. Do Not Include Sensitive Data in Messages

Error messages may appear in SQL clients, database logs, applications, or API responses. Do not put passwords, tokens, card data, sensitive identifiers, or entire payloads in error messages. Use an error code and a concise message sufficient for the caller to act on.

## 5. The keep_errors Parameter: Replacing vs. Adding to the Error Stack

The third parameter controls how `RAISE_APPLICATION_ERROR` handles the existing error stack.

### 5.1. Default FALSE: Replaces the Current Error Stack

```sql
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20020,
            'Customer record is missing'
        );
```

Because the third parameter defaults to `FALSE`, the new application error replaces the existing error stack. The caller primarily sees `ORA-20020`. This can be appropriate when the explicit goal is to map a technical error to a defined API error and the system does not need to surface the underlying error on the stack.

However, if the goal is to preserve the technical root cause, do not rely on this default unintentionally.

### 5.2. TRUE: Appends the Application Error to the Error Stack

```sql
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20020,
            'Customer record is missing',
            TRUE
        );
```

`TRUE` tells Oracle to retain the errors already on the stack and add the application error. This lets the caller see business context at the outer layer while keeping the original error in the error stack.

This is useful when:

- A PL/SQL layer wants to add a business code while preserving the original ORA error.
- A trigger wants to add context to an error that occurred during DML.
- An API wants to express an error in business terms while preserving technical details for operations teams.

### 5.3. Illustrating Both Approaches

Suppose a query finds no rows:

```sql
CREATE OR REPLACE PROCEDURE find_customer (
    p_customer_id IN NUMBER
) AS
    v_name VARCHAR2(100);
BEGIN
    SELECT customer_name
    INTO v_name
    FROM customers
    WHERE customer_id = p_customer_id;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20020,
            'Customer ' || p_customer_id || ' was not found',
            TRUE
        );
END find_customer;
/
```

With `TRUE`, the application error is added to the existing stack instead of erasing the original error details. The caller still needs to read the full error stack/backtrace rather than only taking a single message line.

### 5.4. TRUE Does Not Automatically Create a Complete Log Record

`keep_errors => TRUE` only controls the exception's error stack. It does not:

- Write the error to a log table.
- Save payloads or bind values.
- Save the application's request ID.
- Record the history of preceding successful calls.
- Guarantee logs persist after the session ends.

To retain persistent investigative data, a dedicated logging mechanism is required.

## 6. Preserving Root Cause When Catching and Re-Throwing Errors

### 6.1. Good Pattern: Log Then RAISE

```sql
CREATE OR REPLACE PROCEDURE process_invoice (
    p_invoice_id IN NUMBER
) AS
BEGIN
    -- Invoice processing steps.
    NULL;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Invoice=' || p_invoice_id ||
            ', error=' || SQLCODE ||
            ', message=' || SQLERRM
        );
        RAISE;
END process_invoice;
/
```

`RAISE;` preserves the current exception and propagates it to the caller. The caller can still classify the error by its original Oracle error code.

### 6.2. Dangerous Pattern: Replacing with a Generic Error

```sql
EXCEPTION
    WHEN OTHERS THEN
        RAISE_APPLICATION_ERROR(
            -20099,
            'Processing failed'
        );
```

Without `keep_errors => TRUE`, the original error is replaced in the error stack. The caller only sees a generic message and cannot easily tell whether the original error was `NO_DATA_FOUND`, `DUP_VAL_ON_INDEX`, a conversion error, or something else.

If the API truly must map all errors to a single general code, record the original stack/backtrace before translating, and consider preserving the stack:

```sql
EXCEPTION
    WHEN OTHERS THEN
        -- Log SQLCODE, SQLERRM, error stack, and backtrace here.
        RAISE_APPLICATION_ERROR(
            -20099,
            'Processing failed; contact support with the request ID',
            TRUE
        );
```

### 6.3. Do Not Use RAISE exception_name Instead of Bare RAISE

For example:

```sql
EXCEPTION
    WHEN OTHERS THEN
        RAISE;
```

re-raises the current error.

Whereas:

```sql
EXCEPTION
    WHEN OTHERS THEN
        RAISE e_processing_failed;
```

raises the named exception. This changes the error type. If you intentionally want to translate the error type, preserve the root cause via logging or `RAISE_APPLICATION_ERROR(..., TRUE)` according to the API contract.

### 6.4. Cleanup While Preserving the Original Error

If you need to close a cursor or release resources:

```sql
DECLARE
    CURSOR c_orders IS
        SELECT order_id
        FROM orders
        WHERE status = 'NEW';
BEGIN
    OPEN c_orders;

    -- Operation that may fail.
    FETCH c_orders INTO v_order_id;

    CLOSE c_orders;
EXCEPTION
    WHEN OTHERS THEN
        IF c_orders%ISOPEN THEN
            CLOSE c_orders;
        END IF;
        RAISE;
END;
/
```

Cleanup happens inside the handler, and then `RAISE;` propagates the original exception. If the cleanup itself could raise an error, guard the cleanup in a nested block so a secondary error does not mask the original one.

## 7. SQLCODE and SQLERRM

Inside an exception handler, these two functions provide basic diagnostic information:

- `SQLCODE`: numeric code of the current exception.
- `SQLERRM`: message of the current exception.

Example:

```sql
BEGIN
    RAISE_APPLICATION_ERROR(-20010, 'Invalid payment amount');
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('SQLCODE=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('SQLERRM=' || SQLERRM);
        RAISE;
END;
/
```

The `SQLCODE` of an application error is typically `-20010`. `SQLERRM` returns the corresponding message.

### 7.1. Limitations of SQLERRM

`SQLERRM` is useful for reading the current error message, but it is not an API that stores the full causal chain. When an error is wrapped across multiple layers, `SQLERRM` typically reflects only the current/top error in context; it should not be used in place of the error stack and backtrace.

Do not parse messages to drive logic because:

- Messages can depend on session language.
- Wording can change across versions.
- Messages can embed runtime data values.
- An error stack can contain multiple errors.

Branch on exception names or well-defined `SQLCODE` values instead.

### 7.2. SQLCODE Outside Exception Handlers

`SQLCODE` and `SQLERRM` are only diagnostically meaningful inside an exception handler. Do not read them in normal execution flow and assume they reflect the outcome of the preceding SQL statement. To check whether DML affected any rows, use `SQL%ROWCOUNT`, not `SQLCODE`.

## 8. FORMAT_ERROR_STACK, FORMAT_ERROR_BACKTRACE, and FORMAT_CALL_STACK

Oracle provides functions in `DBMS_UTILITY` to retrieve more detailed diagnostics.

### 8.1. FORMAT_ERROR_STACK

```sql
DBMS_UTILITY.FORMAT_ERROR_STACK
```

Returns the current error stack as a string. This is useful when an exception has passed through multiple layers and the stack holds multiple error codes.

### 8.2. FORMAT_ERROR_BACKTRACE

```sql
DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
```

Returns the location in the PL/SQL call stack where the exception was raised. Call it inside an exception handler to capture the backtrace of the error being handled, especially before raising a new exception.

The backtrace answers the question: which line did the error originate on? This is crucial when an exception is caught in an outer procedure.

### 8.3. FORMAT_CALL_STACK

```sql
DBMS_UTILITY.FORMAT_CALL_STACK
```

Returns the current call stack, showing which subprograms are active on the call chain at the moment of the call. Call stack differs from error backtrace:

- Error backtrace focuses on where the exception was raised.
- Call stack focuses on the call chain at the time the function is invoked.

### 8.4. Example of Capturing Diagnostic Information

```sql
DECLARE
    v_code NUMBER;
    v_message VARCHAR2(4000);
    v_stack VARCHAR2(4000);
    v_backtrace VARCHAR2(4000);
    v_call_stack VARCHAR2(4000);
BEGIN
    RAISE_APPLICATION_ERROR(-20030, 'Order validation failed');
EXCEPTION
    WHEN OTHERS THEN
        v_code := SQLCODE;
        v_message := SQLERRM;
        v_stack := DBMS_UTILITY.FORMAT_ERROR_STACK;
        v_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;
        v_call_stack := DBMS_UTILITY.FORMAT_CALL_STACK;

        DBMS_OUTPUT.PUT_LINE('Code=' || v_code);
        DBMS_OUTPUT.PUT_LINE('Message=' || v_message);
        DBMS_OUTPUT.PUT_LINE('Error stack=' || v_stack);
        DBMS_OUTPUT.PUT_LINE('Backtrace=' || v_backtrace);
        DBMS_OUTPUT.PUT_LINE('Call stack=' || v_call_stack);
        RAISE;
END;
/
```

In production systems, store these fields in a structured log rather than only printing them with `DBMS_OUTPUT`.

## 9. Preserving Backtrace Across Multiple Layers

Suppose we have the call chain:

```text
Application
    |
    v
ORDER_API.PROCESS_ORDER
    |
    v
INVENTORY_API.RESERVE_STOCK
    |
    v
INVENTORY_API.CHECK_AVAILABLE
```

The actual error occurs in `CHECK_AVAILABLE`, but is caught in `PROCESS_ORDER`. If an intermediate layer logs only a generic message and raises a new exception, the original location can become difficult to trace.

### 9.1. Do Not Catch Errors If No Action Is Needed

If a layer needs to take no action, let the exception propagate naturally. There is no need to write `WHEN OTHERS THEN RAISE;` in every procedure, as that only adds code without adding value.

### 9.2. Catch for Cleanup or Logging, Then RAISE

```sql
CREATE OR REPLACE PROCEDURE process_order (
    p_order_id IN NUMBER
) AS
BEGIN
    inventory_api.reserve_stock(p_order_id);
    payment_api.authorize_payment(p_order_id);
EXCEPTION
    WHEN OTHERS THEN
        -- Capture diagnostic information before doing other work.
        DBMS_OUTPUT.PUT_LINE(
            'Order=' || p_order_id ||
            ', stack=' || DBMS_UTILITY.FORMAT_ERROR_STACK
        );
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END process_order;
/
```

The orchestration layer adds the order ID to the log output while preserving the original exception via `RAISE;`.

### 9.3. Adding Business Context While Keeping the Error Stack

```sql
CREATE OR REPLACE PROCEDURE process_order (
    p_order_id IN NUMBER
) AS
BEGIN
    inventory_api.reserve_stock(p_order_id);
EXCEPTION
    WHEN OTHERS THEN
        RAISE_APPLICATION_ERROR(
            -20040,
            'Unable to process order ' || p_order_id,
            TRUE
        );
END process_order;
/
```

`TRUE` adds the business message onto the existing stack. The original error remains visible in the stack. If a full backtrace is needed for investigation, capture `FORMAT_ERROR_BACKTRACE` before calling `RAISE_APPLICATION_ERROR`.

### 9.4. Saving Root Cause Before Translating Errors

```sql
EXCEPTION
    WHEN OTHERS THEN
        v_original_code := SQLCODE;
        v_original_message := SQLERRM;
        v_original_stack := DBMS_UTILITY.FORMAT_ERROR_STACK;
        v_original_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;

        -- Persist diagnostic data or attach a request identifier.
        RAISE_APPLICATION_ERROR(
            -20099,
            'Order processing failed; reference=' || v_request_id,
            TRUE
        );
```

The `v_original_*` variables can be used for logging. There is no need to expose the full technical stack to end users; the caller can receive an application error code and request ID while operations teams look up the full stack in logs.

## 10. Exception Mapping with PRAGMA EXCEPTION_INIT

Some Oracle errors do not have convenient predefined exception names. `PRAGMA EXCEPTION_INIT` maps an Oracle error code to a program-declared exception.

### 10.1. Syntax

```sql
DECLARE
    e_resource_busy EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_resource_busy, -54);
BEGIN
    -- Operation that may raise ORA-00054.
    NULL;
EXCEPTION
    WHEN e_resource_busy THEN
        DBMS_OUTPUT.PUT_LINE('Resource is busy');
END;
/
```

The code passed to the pragma is the negative integer corresponding to the ORA code, for example `-54` for `ORA-00054`.

### 10.2. Mapping vs. Raising

`PRAGMA EXCEPTION_INIT` only binds an exception name to an error code; it does not raise an error itself. To explicitly raise a declared exception, use `RAISE e_resource_busy;`.

### 10.3. When to Use Mapping

- When you need to catch a specific Oracle error that lacks a suitable predefined name.
- When you want code that is cleaner to read than `WHEN OTHERS` with `SQLCODE` comparisons.
- When you want to group error handling by meaningful error categories.

Do not create duplicate mappings or bind a code that does not match the expected error. Exception names should clearly express the technical or business cause.

## 11. How Error Stack and Backtrace Differ

| Information | Question Answered | How to Retrieve |
|---|---|---|
| SQLCODE | What is the current error code? | `SQLCODE` |
| SQLERRM | What is the current error message? | `SQLERRM` |
| Error stack | Which errors are currently on the stack? | `DBMS_UTILITY.FORMAT_ERROR_STACK` |
| Error backtrace | Where was the exception raised? | `DBMS_UTILITY.FORMAT_ERROR_BACKTRACE` |
| Call stack | Which subprogram is calling which at this moment? | `DBMS_UTILITY.FORMAT_CALL_STACK` |

Do not use one field to replace all the others. A solid log captures the code, message, stack, backtrace, call stack, and selected business context.

### 11.1. Multi-Layer Example

```sql
CREATE OR REPLACE PROCEDURE inner_step AS
BEGIN
    RAISE_APPLICATION_ERROR(-20051, 'Inner operation failed');
END inner_step;
/

CREATE OR REPLACE PROCEDURE middle_step AS
BEGIN
    inner_step;
END middle_step;
/

CREATE OR REPLACE PROCEDURE outer_step AS
BEGIN
    middle_step;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Stack: ' || DBMS_UTILITY.FORMAT_ERROR_STACK
        );
        DBMS_OUTPUT.PUT_LINE(
            'Backtrace: ' || DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END outer_step;
/
```

Call:

```sql
BEGIN
    outer_step;
END;
/
```

The exception is raised in `INNER_STEP`, propagates through `MIDDLE_STEP`, and is caught in `OUTER_STEP`. `RAISE;` re-raises the exception being handled. The backtrace pinpoints where the error originated rather than only identifying the final handler.

## 12. Logging Errors Without Losing the Original Error

In production systems, `DBMS_OUTPUT` is not a durable logging mechanism. Diagnostic details can be written to a dedicated log table while preserving the original exception.

### 12.1. Creating the Log Table

```sql
CREATE TABLE app_error_log (
    log_id RAW(16) DEFAULT SYS_GUID() PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE
        DEFAULT SYSTIMESTAMP NOT NULL,
    error_code NUMBER,
    error_message VARCHAR2(4000),
    error_stack CLOB,
    error_backtrace CLOB,
    call_stack CLOB,
    module_name VARCHAR2(64),
    action_name VARCHAR2(64)
);
```

Columns:

- `LOG_ID`: log identifier.
- `CREATED_AT`: timestamp of recording.
- `ERROR_CODE`, `ERROR_MESSAGE`: summary error details.
- `ERROR_STACK`: full error chain.
- `ERROR_BACKTRACE`: location where the error originated.
- `CALL_STACK`: call chain.
- `MODULE_NAME`, `ACTION_NAME`: module/action information if the application has set them via `DBMS_APPLICATION_INFO`.

Avoid storing full input payloads, passwords, access tokens, or unnecessary personal data in logs.

### 12.2. Logging Procedure Using an Autonomous Transaction

```sql
CREATE OR REPLACE PROCEDURE write_app_error_log (
    p_error_code      IN NUMBER,
    p_error_message   IN VARCHAR2,
    p_error_stack     IN CLOB,
    p_error_backtrace IN CLOB,
    p_call_stack      IN CLOB
) AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO app_error_log (
        error_code,
        error_message,
        error_stack,
        error_backtrace,
        call_stack,
        module_name,
        action_name
    )
    VALUES (
        p_error_code,
        p_error_message,
        p_error_stack,
        p_error_backtrace,
        p_call_stack,
        SYS_CONTEXT('USERENV', 'MODULE'),
        SYS_CONTEXT('USERENV', 'ACTION')
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END write_app_error_log;
/
```

`PRAGMA AUTONOMOUS_TRANSACTION` gives the logging operation an independent transaction separate from the caller's business transaction. The `COMMIT` inside the logger persists the log entry even if the business transaction subsequently rolls back.

### 12.3. Calling the Logger Inside an Exception Handler

```sql
CREATE OR REPLACE PROCEDURE process_demo_order (
    p_order_id IN NUMBER
) AS
    v_error_code NUMBER;
    v_error_message VARCHAR2(4000);
    v_error_stack VARCHAR2(4000);
    v_error_backtrace VARCHAR2(4000);
    v_call_stack VARCHAR2(4000);
BEGIN
    -- Replace with actual business logic.
    RAISE_APPLICATION_ERROR(-20061, 'Demo processing failure');
EXCEPTION
    WHEN OTHERS THEN
        v_error_code := SQLCODE;
        v_error_message := SQLERRM;
        v_error_stack := DBMS_UTILITY.FORMAT_ERROR_STACK;
        v_error_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;
        v_call_stack := DBMS_UTILITY.FORMAT_CALL_STACK;

        write_app_error_log(
            p_error_code      => v_error_code,
            p_error_message   => v_error_message,
            p_error_stack     => v_error_stack,
            p_error_backtrace => v_error_backtrace,
            p_call_stack      => v_call_stack
        );

        RAISE;
END process_demo_order;
/
```

The information is captured before calling the logger. After writing the log, `RAISE;` propagates the original exception back to the caller.

### 12.4. Logger Failures Must Not Mask the Original Business Error

If the logger itself can fail, an error from the logger risks replacing the original error. When the logging policy is best-effort, you can guard the logger call in a nested block:

```sql
EXCEPTION
    WHEN OTHERS THEN
        v_error_code := SQLCODE;
        v_error_message := SQLERRM;
        v_error_stack := DBMS_UTILITY.FORMAT_ERROR_STACK;
        v_error_backtrace := DBMS_UTILITY.FORMAT_ERROR_BACKTRACE;
        v_call_stack := DBMS_UTILITY.FORMAT_CALL_STACK;

        BEGIN
            write_app_error_log(
                v_error_code,
                v_error_message,
                v_error_stack,
                v_error_backtrace,
                v_call_stack
            );
        EXCEPTION
            WHEN OTHERS THEN
                -- Best-effort logging: do not replace the original exception.
                NULL;
        END;

        RAISE;
```

Here only the secondary error from the logging operation is ignored; the original business/technical error is still re-raised via `RAISE;`. If the system requires mandatory logging, do not silently ignore logger errors; design an alerting channel or an appropriate fail-closed policy.

### 12.5. Notes on Autonomous Transactions

An autonomous logger has important characteristics to understand:

- Logs can `COMMIT` even when the business transaction rolls back.
- The logger cannot see uncommitted changes made by the parent transaction.
- Do not create foreign keys from the log table to uncommitted business rows; an autonomous transaction cannot rely on the caller's uncommitted data.
- The logger should only write independent diagnostic data and not update rows locked by the parent transaction.
- Autonomous transactions consume resources and can encounter their own errors; plan capacity, retention, and privileges accordingly.

Do not use autonomous transactions as a shortcut to commit part of a business operation.

## 13. RAISE_APPLICATION_ERROR in Triggers

Triggers are often used to enforce data rules at `INSERT`, `UPDATE`, or `DELETE` time. When data violates a rule, a trigger can raise an application error to reject the statement.

### 13.1. Trigger Validating an Amount

```sql
CREATE OR REPLACE TRIGGER trg_demo_order_amount
BEFORE INSERT OR UPDATE OF amount
ON demo_orders
FOR EACH ROW
BEGIN
    IF :NEW.amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20070,
            'Order amount must not be negative'
        );
    END IF;
END trg_demo_order_amount;
/
```

The trigger runs before writing the row. If `:NEW.amount` is negative, the trigger raises `ORA-20070` and the DML is rejected.

### 13.2. Adding Context from a Trigger While Keeping the Original Error

If a trigger calls another procedure and that procedure raises an error, the trigger can add context:

```sql
CREATE OR REPLACE TRIGGER trg_demo_order_check
BEFORE INSERT
ON demo_orders
FOR EACH ROW
BEGIN
    validate_order_amount(:NEW.amount);
EXCEPTION
    WHEN OTHERS THEN
        RAISE_APPLICATION_ERROR(
            -20071,
            'Order validation failed for customer ' ||
            :NEW.customer_id,
            TRUE
        );
END trg_demo_order_check;
/
```

`TRUE` preserves the current error stack and appends the trigger's application error. When deep investigation is required, a logger should save `FORMAT_ERROR_STACK` and `FORMAT_ERROR_BACKTRACE` where the exception is caught.

### 13.3. Triggers Should Not Mask Root Causes with Generic Messages

Avoid:

```sql
EXCEPTION
    WHEN OTHERS THEN
        RAISE_APPLICATION_ERROR(
            -20099,
            'Database operation failed'
        );
```

Without preserving the stack, detailed errors from inside the procedure can be overwritten. Decide explicitly: either re-raise the original error with `RAISE;`, or add context with `RAISE_APPLICATION_ERROR(..., TRUE)`.

### 13.4. How Trigger Errors Are Returned to the Caller

When a trigger raises an error while a DML statement is running:

- The DML statement fails.
- Oracle rolls back the statement's changes under statement-level atomicity.
- The exception propagates to the session/client that issued the DML.
- The client can receive the application error code along with trigger execution details.

The actual message may include `ORA-04088: error during execution of trigger ...` together with the original or application error. Always keep the entire stack when investigating rather than copying only the `ORA-04088` line.

### 13.5. Triggers Must Not COMMIT or ROLLBACK the Parent Transaction

A normal trigger cannot `COMMIT` or `ROLLBACK` the transaction executing the DML. If independent logging is needed, a separate autonomous transaction design may be used, provided uncommitted data visibility and log independence are clearly understood.

Do not turn triggers into orchestrators of multiple business transactions. Triggers should keep narrow, well-defined responsibilities and avoid unpredictable side effects.

## 14. Preserving Root Cause Information Across Multiple Layers

A well-designed error strategy preserves three layers of information:

1. **Root cause code:** the original Oracle code or specific application error code.
2. **Business context:** order ID, customer ID, operation, or request ID.
3. **Technical location:** error stack, backtrace, and call stack.

### 14.1. Data Layer Example

```sql
CREATE OR REPLACE PROCEDURE reserve_stock (
    p_product_id IN NUMBER,
    p_quantity IN NUMBER
) AS
    v_available NUMBER;
BEGIN
    SELECT available_quantity
    INTO v_available
    FROM inventory
    WHERE product_id = p_product_id;

    IF p_quantity > v_available THEN
        RAISE_APPLICATION_ERROR(
            -20080,
            'Insufficient stock for product ' || p_product_id
        );
    END IF;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20081,
            'Inventory record not found for product ' || p_product_id,
            TRUE
        );
END reserve_stock;
/
```

This layer understands inventory data and can distinguish a missing record from insufficient stock.

### 14.2. Orchestration Layer Example

```sql
CREATE OR REPLACE PROCEDURE process_order_stock (
    p_order_id IN NUMBER,
    p_product_id IN NUMBER,
    p_quantity IN NUMBER
) AS
BEGIN
    reserve_stock(p_product_id, p_quantity);
EXCEPTION
    WHEN OTHERS THEN
        RAISE_APPLICATION_ERROR(
            -20082,
            'Stock reservation failed for order ' || p_order_id,
            TRUE
        );
END process_order_stock;
/
```

The orchestration layer adds the order ID while preserving the existing error stack. When the caller receives the error, both the order context and the inventory root cause are visible.

### 14.3. In the Application Layer

The application should:

- Record the request/correlation ID.
- Capture the Oracle error code and full error chain provided by the driver when permitted.
- Distinguish expected business errors from system errors.
- Return a user-friendly message without exposing internal stacks.
- Store technical stacks in access-controlled logs.

Do not return raw `SQLERRM`, schema names, internal SQL statements, or database stacks to all end users. Preserving root cause in logging systems does not mean exposing all internal details to clients.

## 15. UTL_CALL_STACK and Detailed Diagnostics

In Oracle versions supporting `UTL_CALL_STACK` (starting in Oracle Database 12c), this package provides a structured API for reading the call stack, error stack, and backtrace.

Available functions include:

- `UTL_CALL_STACK.ERROR_DEPTH`: number of errors in the error stack.
- `UTL_CALL_STACK.ERROR_NUMBER(n)`: error code at position `n`.
- `UTL_CALL_STACK.ERROR_MSG(n)`: error message at position `n`.
- `UTL_CALL_STACK.BACKTRACE_DEPTH`: number of frames in the backtrace.
- `UTL_CALL_STACK.BACKTRACE_UNIT(n)`: unit at the backtrace frame.
- `UTL_CALL_STACK.BACKTRACE_LINE(n)`: corresponding line number in the backtrace.
- `UTL_CALL_STACK.DYNAMIC_DEPTH`: depth of the dynamic call stack.
- `UTL_CALL_STACK.CONCATENATE_SUBPROGRAM(n)`: subprogram name at the corresponding frame.

Illustrative example:

```sql
BEGIN
    RAISE_APPLICATION_ERROR(-20090, 'Diagnostic example');
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Error depth=' || UTL_CALL_STACK.ERROR_DEPTH
        );

        FOR i IN 1 .. UTL_CALL_STACK.ERROR_DEPTH LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Error ' || i ||
                ': ' || UTL_CALL_STACK.ERROR_NUMBER(i) ||
                ' - ' || UTL_CALL_STACK.ERROR_MSG(i)
            );
        END LOOP;

        FOR i IN 1 .. UTL_CALL_STACK.BACKTRACE_DEPTH LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Backtrace ' || i ||
                ': ' || UTL_CALL_STACK.BACKTRACE_UNIT(i) ||
                ' line ' || UTL_CALL_STACK.BACKTRACE_LINE(i)
            );
        END LOOP;

        RAISE;
END;
/
```

Only index within the returned depth range. Execution privileges and exact APIs should be verified for your Oracle version. `DBMS_UTILITY.FORMAT_ERROR_STACK` and `FORMAT_ERROR_BACKTRACE` remain simple, widely used ways to log diagnostic strings.

## 16. Error Handling in Triggers: Key Principles

### 16.1. Use Triggers Only When Rules Must Be Enforced in the Database

Triggers are appropriate for rules that must hold across every DML path, including writes from SQL clients, batch jobs, or other applications. However, if a rule can be expressed using a `CHECK`, `NOT NULL`, `UNIQUE`, or `FOREIGN KEY` constraint, a constraint is usually simpler and clearer than a trigger.

For example, a non-negative amount should prefer:

```sql
ALTER TABLE demo_orders
ADD CONSTRAINT ck_demo_order_amount_nonnegative
CHECK (amount >= 0);
```

Triggers can enforce more complex checks, but should not replace simple constraints.

### 16.2. Avoid Catching and Ignoring Errors in Triggers

If a trigger catches an error and does not re-raise it, the DML statement may continue or complete according to the coded behavior, leaving data inconsistent with the rule. Do not write:

```sql
EXCEPTION
    WHEN OTHERS THEN
        NULL;
```

inside a trigger to "avoid interrupting" DML, unless business requirements explicitly design for ignoring that error.

### 16.3. Do Not Arbitrarily Change Error Types

If a trigger calls a procedure and receives a specific ORA error, use `RAISE;` to propagate the original error or `RAISE_APPLICATION_ERROR(..., TRUE)` to add context. Use `FALSE` only when you intentionally replace the error stack with another API code and have already persisted the root cause elsewhere.

### 16.4. Triggers and Mutating Table Errors Are a Separate Issue

Certain row-level triggers cannot directly query or modify the same table currently being modified by the triggering statement, which can lead to `ORA-04091: table is mutating`. This is a consistency/trigger-timing restriction, not an error solved by `RAISE` or `RAISE_APPLICATION_ERROR`. You need to redesign the logic, use a compound trigger, or apply another mechanism suited to the Oracle version and business rules.

## 17. Common Pitfalls When Raising or Propagating Exceptions

| Symptom | Cause | How to Fix |
|---|---|---|
| `ORA-06510` | Unhandled user-defined exception | Catch the exception or map it to an appropriate application code |
| `ORA-20000` to `ORA-20999` | Application error raised | Look up the error code in the API contract |
| `ORA-21000` / invalid error number | Code passed to `RAISE_APPLICATION_ERROR` is out of range | Use a negative integer from `-20000` to `-20999` |
| Original error disappears | Default `FALSE` in `RAISE_APPLICATION_ERROR` inside handler | Use `RAISE;` or `keep_errors => TRUE` |
| Backtrace only points to handler | Created a new exception or captured info too late | Capture `FORMAT_ERROR_BACKTRACE` before translating the error |
| Logger error masks main error | Logger raises a new exception | Guard logger in a nested block or define clear logging policy |
| No log after rollback | Log ran in business transaction and rolled back | Consider an autonomous logger if logs must persist independently |
| Trigger returns ORA-04088 | Trigger raised an error during DML | Read the entire stack to find the original error code and backtrace |
| Caller only sees generic message | Handler replaced original error without saving stack | Preserve the stack and log with context |
| Message truncated | Message exceeds 2048-byte limit | Keep message concise and write details to a log table |
| Log contains sensitive data | Unfiltered payload/SQLERRM logged | Log only necessary context, enforce access control and retention |
| Using SQLERRM to classify errors | Depends on message wording/language | Use exception names or `SQLCODE` |

### 17.1. Out-of-Range Error Codes

`RAISE_APPLICATION_ERROR` requires a code from `-20000` to `-20999`. Passing a code outside this range causes Oracle to raise an invalid error number parameter error. Never use `-1`, `-54`, or arbitrary ORA codes as custom application codes; those codes belong to Oracle's internal error space.

### 17.2. Message Too Long

The `RAISE_APPLICATION_ERROR` message has a 2048-byte limit. Unicode strings can use multiple bytes per character, so do not rely solely on character count. Keep the message short and write detailed diagnostics to a log table.

### 17.3. Catching OTHERS Without RAISE

```sql
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
        NULL;
```

The block may exit as if the error were handled, leaving the caller with no sign of failure. Unless you genuinely recover to a valid state, re-raise the exception.

## 18. Error Handling Design Workflow

A practical workflow:

1. **Identify expected errors:** data errors, business errors, or system errors.
2. **Choose representation:** predefined exception, user-defined exception, or `RAISE_APPLICATION_ERROR` code.
3. **Define the API contract:** which error codes the caller needs to distinguish.
4. **Catch at the right layer:** catch only where that layer can recover, clean up, or add context.
5. **Capture root cause info:** `SQLCODE`, `SQLERRM`, error stack, and backtrace before raising a new error.
6. **Log safely:** retain request ID and necessary business context while avoiding sensitive data.
7. **Propagate the error:** use `RAISE;` or append an application error with `keep_errors => TRUE`.
8. **Control transactions:** clearly decide whether the statement/transaction rolls back or the caller is responsible.
9. **Test from clients:** verify actual error codes and stacks through SQL Developer, SQLcl, or JDBC.

### 18.1. When Should an Error Be Translated to a Business Code?

Translate an error when the caller needs a stable API, such as mapping `NO_DATA_FOUND` to `ORA-20020 CUSTOMER_NOT_FOUND`. However, when helpful for troubleshooting, keep the original stack with `TRUE` and save the backtrace.

### 18.2. When Should the Original Error Be Re-Raised As-Is?

If the current layer has no way to handle the error and only needs the caller to know the operation failed, use `RAISE;`. Do not add a handler merely to print `SQLERRM` and replace it with a generic message.

### 18.3. Where Should Logging Happen?

Log at one or a few meaningful boundaries where sufficient context and operational ownership exist. If every layer logs the same exception and re-raises it, a single error creates duplicate log records. Choose a primary logging layer and pass the request ID across layers.

## 19. Comprehensive Lab

The examples below create dedicated objects in a lab schema. Run them only when you have privileges to create tables, procedures, and triggers, and avoid naming collisions with business objects.

### Step 1. Create the Lab Orders Table

```sql
CREATE TABLE lab_error_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12, 2) NOT NULL,
    status VARCHAR2(20) DEFAULT 'NEW' NOT NULL
);
```

### Step 2. Test Raising a User-Defined Exception

```sql
DECLARE
    e_invalid_amount EXCEPTION;
    v_amount NUMBER := -10;
BEGIN
    IF v_amount < 0 THEN
        RAISE e_invalid_amount;
    END IF;
EXCEPTION
    WHEN e_invalid_amount THEN
        DBMS_OUTPUT.PUT_LINE('Invalid amount');
END;
/
```

### Step 3. Test RAISE_APPLICATION_ERROR

```sql
BEGIN
    RAISE_APPLICATION_ERROR(
        -20010,
        'Lab validation failed'
    );
END;
/
```

Observe the ORA code and message on the client side.

### Step 4. Test Bare RAISE; Preserving the Original Error

```sql
BEGIN
    DECLARE
        v_amount NUMBER;
    BEGIN
        v_amount := 1 / 0;
    END;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(SQLCODE || ': ' || SQLERRM);
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END;
/
```

Observe that the final exception remains the division-by-zero error.

### Step 5. Test Adding Context While Preserving the Stack

```sql
BEGIN
    BEGIN
        RAISE_APPLICATION_ERROR(-20021, 'Original inventory error');
    EXCEPTION
        WHEN OTHERS THEN
            RAISE_APPLICATION_ERROR(
                -20022,
                'Order 1001 could not reserve inventory',
                TRUE
            );
    END;
END;
/
```

Compare with the same example using `FALSE` as the third parameter or omitting the third parameter. Observe the difference in the client's error stack and `FORMAT_ERROR_STACK`.

### Step 6. Create a Trigger to Reject Negative Amounts

```sql
CREATE OR REPLACE TRIGGER trg_lab_error_orders
BEFORE INSERT OR UPDATE OF amount
ON lab_error_orders
FOR EACH ROW
BEGIN
    IF :NEW.amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20030,
            'Amount must be non-negative'
        );
    END IF;
END trg_lab_error_orders;
/
```

### Step 7. Test Valid DML

```sql
INSERT INTO lab_error_orders (
    order_id,
    customer_id,
    amount
)
VALUES (1, 501, 1000);

COMMIT;
```

### Step 8. Test Invalid DML

```sql
INSERT INTO lab_error_orders (
    order_id,
    customer_id,
    amount
)
VALUES (2, 501, -100);
```

Observe `ORA-20030` and the associated trigger execution error. Verify that the invalid row was not inserted.

### Step 9. Inspect Trigger Metadata

```sql
SELECT trigger_name,
       status,
       triggering_event,
       trigger_type
FROM user_triggers
WHERE trigger_name = 'TRG_LAB_ERROR_ORDERS';
```

### Step 10. Clean Up Lab Objects

Only when you are certain these are objects you created and the data does not need to be kept:

```sql
DROP TRIGGER trg_lab_error_orders;
DROP TABLE lab_error_orders PURGE;
```

`DROP TABLE ... PURGE` deletes the table and its data while bypassing the recycle bin per command behavior; DDL triggers an implicit commit. Do not run this on business tables or shared objects.

## 20. Quick Reference Rules

| Need | How to Do It |
|---|---|
| Raise a declared exception | `RAISE exception_name;` |
| Re-raise the current exception inside a handler | `RAISE;` |
| Return a business error code | `RAISE_APPLICATION_ERROR(-20000..-20999, message)` |
| Add application error while keeping current stack | `RAISE_APPLICATION_ERROR(code, message, TRUE)` |
| Replace the current error stack | `RAISE_APPLICATION_ERROR(code, message, FALSE)` or omit 3rd argument |
| Retrieve current code/message | `SQLCODE`, `SQLERRM` |
| Retrieve the full error stack | `DBMS_UTILITY.FORMAT_ERROR_STACK` |
| Find the line where the exception was raised | `DBMS_UTILITY.FORMAT_ERROR_BACKTRACE` |
| View the call stack at the current point | `DBMS_UTILITY.FORMAT_CALL_STACK` |
| Map an ORA code to an exception name | `PRAGMA EXCEPTION_INIT` |
| Log independently of business transaction | Consider an autonomous logger with clear design |
| Handle trigger errors | Read full stack; re-raise or add context while keeping stack |
| Protect root cause when logger fails | Wrap logger in a nested block, then `RAISE;` |

## 21. Self-Check Questions

**Question 1.** What is `RAISE exception_name;` used for?

**Answer:** Explicitly raising an exception that has been declared in scope.

**Question 2.** When is bare `RAISE;` without a name used?

**Answer:** Inside an exception handler to re-raise the current exception, preserving the error being handled.

**Question 3.** What code range does `RAISE_APPLICATION_ERROR` use?

**Answer:** Negative integers from `-20000` to `-20999`.

**Question 4.** What is the maximum byte length of a `RAISE_APPLICATION_ERROR` message?

**Answer:** 2048 bytes.

**Question 5.** What does the third parameter of `RAISE_APPLICATION_ERROR` mean?

**Answer:** `TRUE` appends the application error to the current error stack; `FALSE` replaces the current stack. The default is `FALSE`.

**Question 6.** Why can using `RAISE_APPLICATION_ERROR` with its default in a handler lose the root cause?

**Answer:** Because the default `FALSE` replaces the current error stack with the new application error.

**Question 7.** When you only need to log an error and pass it up to the caller, what should you use?

**Answer:** Capture the required information, log it, and use `RAISE;` inside the handler.

**Question 8.** How do `SQLCODE` and `SQLERRM` differ from `FORMAT_ERROR_STACK`?

**Answer:** `SQLCODE`/`SQLERRM` provide the current code and message; `FORMAT_ERROR_STACK` returns the error stack string, which may contain multiple errors.

**Question 9.** What does `FORMAT_ERROR_BACKTRACE` tell you?

**Answer:** The location in PL/SQL where the exception was raised, which is useful when the error is caught at an upper layer.

**Question 10.** How does `FORMAT_CALL_STACK` differ from error backtrace?

**Answer:** Call stack shows the call chain at the time it is invoked; error backtrace points to where the exception was raised.

**Question 11.** Does `PRAGMA EXCEPTION_INIT` raise an exception by itself?

**Answer:** No. It binds an Oracle error code to an exception name; to raise a declared exception, use `RAISE`.

**Question 12.** Why might a logger use an autonomous transaction?

**Answer:** So logs can `COMMIT` independently and survive even if the business transaction rolls back, while accepting limitations regarding uncommitted data and resources.

**Question 13.** If a logger fails inside a handler, how do you avoid masking the original error?

**Answer:** Wrap the logger in a nested block and handle logger errors separately, then `RAISE;` in the outer handler.

**Question 14.** When a trigger raises `RAISE_APPLICATION_ERROR`, what happens to the DML statement?

**Answer:** The statement fails and its changes are rolled back under statement-level atomicity; the error is returned to the caller.

**Question 15.** Should you use `WHEN OTHERS THEN NULL` in a trigger?

**Answer:** No, unless there is a very specific policy to ignore errors; normally you must handle or re-raise so DML does not succeed in an invalid state.

## 22. Conclusion

`RAISE` and `RAISE_APPLICATION_ERROR` serve two distinct purposes. `RAISE exception_name;` explicitly raises a declared exception; `RAISE;` inside a handler re-raises the current exception and is the proper approach when you only need to log, clean up, or propagate the error to the caller. `RAISE_APPLICATION_ERROR` creates business error codes in the `-20000` to `-20999` range, enabling database APIs to return meaningful messages to applications.

The key decision when preserving root cause is the `keep_errors` parameter: `TRUE` appends the application error to the current error stack, whereas `FALSE` or the default replaces the stack. For diagnostics, capture `SQLCODE`, `SQLERRM`, `DBMS_UTILITY.FORMAT_ERROR_STACK`, and `FORMAT_ERROR_BACKTRACE` before raising a new exception. The call stack adds information about the current call path, and a structured logger persists investigative data beyond the lifetime of the session.

In triggers, any raised error causes the DML statement to fail and propagates back to the caller. Prefer constraints for simple rules, keep triggers concise, never swallow errors, and read the full error stack instead of looking only at `ORA-04088`. A strong exception strategy preserves stable error codes, business context, and technical origin, while preventing secondary failures such as logging errors from obscuring the original root cause.
