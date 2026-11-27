# Database API design, transaction boundaries, and error contracts

A database API is the interface an application uses to ask the database to perform a business operation. In Oracle, this API is typically built with packages, procedures, and functions. A good API does not just have easy-to-call parameter signatures; it must also clearly define who owns the transaction, which data is modified, when changes are committed, which errors can occur, and how callers must react.

Three decisions must be designed together:

1. **API contract:** operation name, inputs, outputs, validity conditions, and business outcomes.
2. **Transaction boundary:** where the transaction starts and ends; whether the procedure commits/rolls back or leaves management to the caller.
3. **Error contract:** how errors are detected, translated, propagated, and handled; and what state the data is in after an error.

If these three parts are inconsistent, applications easily run into issues such as a sub-procedure accidentally committing the caller's work, swallowed errors making the caller think an operation succeeded, transactions leaving partial DML behind, or retries creating duplicate transactions. This lesson focuses on how to design package APIs that compose safely across multiple business flows.

## 1. What is a database API?

Instead of letting every application write numerous direct SQL statements against tables, you can expose a business interface:

~~~sql
BEGIN
    order_api.create_order(
        p_customer_id => 101,
        p_request_id  => 'REQ-2026-0001',
        p_order_id    => :new_order_id
    );
END;
/
~~~

The application invokes CREATE_ORDER without needing to know all table details, customer status checks, header writes, detail writes, or auditing.

A database API can be responsible for:

- Validating inputs and business rules.
- Reading and updating related tables.
- Ensuring the steps of an operation execute consistently.
- Returning identifiers or results.
- Raising errors with stable codes so callers can classify them.
- Recording appropriate operational information.

### 1.1 Why encapsulate SQL inside packages?

Packages help group operations belonging to the same business domain and control what is exposed publicly:

- Package specification is the public interface.
- Package body contains the internal implementation.
- Private procedures/functions assist processing without callers invoking them directly.
- Package constants, types, and exceptions can be shared within the API scope.

Example:

~~~sql
CREATE OR REPLACE PACKAGE inventory_api AS
    PROCEDURE reserve_stock(
        p_product_id IN products.product_id%TYPE,
        p_quantity   IN NUMBER
    );

    PROCEDURE release_stock(
        p_product_id IN products.product_id%TYPE,
        p_quantity   IN NUMBER
    );
END inventory_api;
/
~~~

Callers see only the two public operations. SQL details, auxiliary tables, logging mechanics, and row-locking workflows stay inside the package body.

### 1.2 APIs should represent business intent

An API like UPDATE_TABLE_ROW accepting a table name, column name, and condition string is hard to control for privileges, data types, and error contracts. A business API like APPROVE_ORDER clearly expresses intent and lets the database enforce consistent rules.

API names should describe meaningful actions or queries:

- CREATE_ORDER.
- APPROVE_ORDER.
- RESERVE_INVENTORY.
- CANCEL_PAYMENT.
- GET_ACCOUNT_BALANCE.

Avoid forcing callers to know the calling order of multiple internal procedures just to complete a single business operation.

## 2. Designing the package specification as a contract

The package specification is what callers depend on. Any change here can affect dependent programs, so the interface must remain stable and unambiguous.

An API contract should describe:

- Operation name and purpose.
- IN, OUT, and IN OUT parameters.
- Data types and value domains.
- Required and optional parameters.
- NULL rules.
- Preconditions before calling.
- Postconditions on success.
- Business and technical errors that may be raised.
- Transaction ownership.
- Behavior when an exception occurs.

Example package specification:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    PROCEDURE create_order(
        p_customer_id IN  customers.customer_id%TYPE,
        p_request_id  IN  VARCHAR2,
        p_order_id    OUT orders.order_id%TYPE
    );

    PROCEDURE approve_order(
        p_order_id IN orders.order_id%TYPE
    );
END order_api;
/
~~~

Callers know the inputs, outputs, and operation names. API documentation must supplement business preconditions and errors, because SQL/PLSQL signatures alone cannot express the entire contract.

### 2.1 Choosing parameter modes

| Mode | Use when | Example |
|---|---|---|
| IN | Caller supplies data to process | CUSTOMER_ID, ORDER_ID, AMOUNT |
| OUT | API returns a value it produces | New ORDER_ID |
| IN OUT | API receives and updates in-memory data state | Collection to transform |

Prefer IN for inputs and OUT for distinct outputs. Use IN OUT only when mutating the input value is the natural semantics of the API.

### 2.2 Do not use OUT to hide multiple statuses

If an operation can succeed, be rejected by business rules, or raise technical errors, clearly decide whether those states are represented by:

- A return value.
- An OUT parameter.
- An exception with an error code.

Do not both return an error code in an OUT parameter and raise an exception for the same situation unless callers have a clear rule prioritizing one over the other.

### 2.3 Use stable data types

%TYPE keeps parameter types aligned with columns:

~~~sql
PROCEDURE approve_order(
    p_order_id IN orders.order_id%TYPE
);
~~~

However, a package specification directly referencing table structures creates compile-time dependencies. If you want the API to be less coupled to physical schemas, you can use subtypes or public types defined by the package:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    SUBTYPE t_order_id IS NUMBER(12);

    PROCEDURE approve_order(
        p_order_id IN t_order_id
    );
END order_api;
/
~~~

Which approach to pick depends on schema conventions and versioning goals. If a column type changes, verify that packages and dependent objects are recompiled.

### 2.4 Do not expose internal details

Do not put every table, internal record, cursor, and helper function into the package specification. The wider the public API, the harder it becomes to change the implementation without impacting callers.

Expose only the operations callers genuinely need, the data types required to call the API, exceptions or error codes callers need to classify, and constants meaningful to the contract. Place helper procedures/functions in the package body when they only serve implementation.

## 3. What is a transaction boundary?

A transaction boundary defines which group of database operations must commit together or roll back together.

For example, creating an order might include:

1. Validating the customer.
2. Creating the order header.
3. Creating order details.
4. Reserving inventory.
5. Recording status history.

If these steps belong to an indivisible business operation, they must normally sit in the same transaction. If one step fails, earlier steps must not be accidentally committed in isolation.

### 3.1 Transactions belong to the session, not to individual procedures

Oracle manages transactions per session/connection. Multiple procedures invoked sequentially on the same connection can participate in the same transaction:

~~~text
Application obtains connection
          |
          v
      API A DML
          |
          v
      API B DML
          |
          v
      API C DML
          |
          v
     Caller COMMIT
          |
          v
   All transaction work commits
~~~

A procedure does not own an independent transaction merely because it is a PL/SQL unit. A COMMIT inside a procedure ends the session's current transaction, including changes made earlier by the caller or other procedures.

### 3.2 Example of a committing procedure affecting the caller

Suppose the caller runs:

~~~sql
BEGIN
    UPDATE customer_profile
    SET phone_number = '0900000000'
    WHERE customer_id = 101;

    order_api.create_order(
        p_customer_id => 101,
        p_request_id  => 'REQ-001',
        p_order_id    => :order_id
    );

    ROLLBACK;
END;
/
~~~

If CREATE_ORDER executes COMMIT internally, the caller's PHONE_NUMBER update is committed too. The final ROLLBACK cannot undo that committed change.

This is why low-level business procedures should generally not COMMIT or ROLLBACK the entire transaction on their own.

## 4. Two transaction ownership models

There are two primary models. Choose one model per API and state it explicitly in the contract.

### 4.1 Caller-managed transaction

The caller is responsible for:

- Starting the unit of work with the first DML statements.
- Calling one or more APIs.
- Deciding to COMMIT when the entire business operation succeeds.
- Issuing ROLLBACK when any part of the business operation fails.

Called procedures do not COMMIT and do not ROLLBACK the entire transaction.

Example:

~~~sql
BEGIN
    order_api.create_order(
        p_customer_id => 101,
        p_request_id  => 'REQ-002',
        p_order_id    => :order_id
    );

    payment_api.reserve_payment(
        p_order_id => :order_id
    );

    inventory_api.reserve_order(
        p_order_id => :order_id
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

Callers can compose multiple packages within a single transaction. This model is flexible and generally fits APIs meant to be reused across multiple business flows.

### 4.2 API-owned transaction

A high-level API can be designed to complete the transaction itself:

~~~sql
PROCEDURE submit_order(...) AS
BEGIN
    -- Validate, insert order, reserve stock...
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
~~~

This model is appropriate only when the contract explicitly states the operation is a standalone unit and callers accept that the procedure ends the session's transaction.

Risks:

- COMMIT also commits uncommitted changes the caller made prior to calling.
- ROLLBACK also rolls back uncommitted changes made by the caller.
- The procedure cannot be composed into a larger caller-controlled transaction.
- Callers struggle to coordinate multiple APIs if each API commits on its own.

Therefore, API-owned transactions should typically only be used at high-level entry points called standalone, with a connection/session dedicated to that unit of work.

### 4.3 Practical rules

| Procedure type | Typically appropriate transaction rule |
|---|---|
| Internal helper | Never COMMIT/ROLLBACK |
| API handling part of a workflow, composable with others | Caller manages the transaction |
| High-level API defined as an entire standalone use case | May COMMIT/ROLLBACK if explicitly specified in contract |
| Independent logging/auditing procedure | Consider autonomous transaction only for genuinely independent diagnostic data |
| Procedure used in a trigger | Never COMMIT the caller's transaction; transaction belongs to statement/session |

Do not put COMMIT inside a procedure merely because "the procedure finished running." Completing one call does not equal completing the business transaction.

## 5. Atomicity of an API and SAVEPOINT

Caller-managed transactions do not mean a procedure must leave partial DML behind when it fails. An API can guarantee atomicity for its own portion of work using SAVEPOINT.

SAVEPOINT marks a point within a transaction. ROLLBACK TO SAVEPOINT undoes changes after that marker, without ending the overall transaction or undoing work performed before the marker.

### 5.1 Example using a savepoint inside an API

~~~sql
CREATE OR REPLACE PROCEDURE create_order_api (
    p_customer_id IN  customers.customer_id%TYPE,
    p_order_id    OUT orders.order_id%TYPE
) AS
BEGIN
    SAVEPOINT create_order_api_sp;
    p_order_id := NULL;

    INSERT INTO orders(customer_id, status, created_at)
    VALUES (p_customer_id, 'NEW', SYSTIMESTAMP)
    RETURNING order_id INTO p_order_id;

    INSERT INTO order_audit(order_id, action_name, action_time)
    VALUES (p_order_id, 'CREATED', SYSTIMESTAMP);

EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO create_order_api_sp;
        RAISE;
END create_order_api;
/
~~~

If the audit INSERT fails, the order INSERT after the savepoint is rolled back. The caller still owns the transaction and can decide whether to continue with prior work or roll back the entire transaction.

### 5.2 Savepoints do not commit

SAVEPOINT does not create an independent transaction and does not commit data. After ROLLBACK TO:

- The transaction remains open.
- Changes made before the savepoint remain pending.
- The caller must still decide whether to COMMIT or ROLLBACK the entire transaction.
- Savepoints created after the target savepoint are erased.

### 5.3 Savepoint names and nested calls

Savepoint names are transaction-scoped. If another procedure reuses the same name, the older savepoint can be overwritten. This happens easily when procedures call each other in nested or recursive flows.

Use savepoint names namespaced by package/operation, avoid reusing identical names across nested calls, document which helpers are allowed to create savepoints, and never let sub-procedures COMMIT/ROLLBACK the entire transaction because that destroys the caller's savepoints.

Oracle does not have a separate RELEASE SAVEPOINT command. A savepoint remains valid until the transaction ends or it is overwritten/removed according to savepoint rules.

### 5.4 When is an internal savepoint unnecessary?

If callers always roll back the entire transaction whenever any API fails, the API may not need its own savepoint. However, the contract must clearly state that when an exception escapes, the caller must roll back the entire transaction before reusing the connection or continuing work.

Savepoints are valuable when callers want to preserve work done prior to the API call. In exchange, savepoint naming and intentional rollback scope must be managed carefully.

### 5.5 Do not run DDL inside business APIs

Oracle DDL typically performs an implicit COMMIT before and after the operation. Statements like CREATE TABLE, ALTER TABLE, and DROP TABLE can terminate the caller's transaction.

Therefore, avoid running DDL in business APIs:

~~~sql
-- Do not place inside an order-processing procedure:
EXECUTE IMMEDIATE 'CREATE TABLE temp_order_work (...)';
~~~

If a temporary table is needed, create the object beforehand and use a Global Temporary Table or an appropriate staging mechanism. Never use SAVEPOINT assuming you can roll back across DDL.

## 6. Error contract

The error contract specifies which errors callers may receive and how they must interpret them.

A good contract distinguishes:

1. Input/validation errors.
2. Business states that disallow the operation.
3. Missing data or non-unique data.
4. Data/constraint conflicts.
5. Retryable concurrency errors.
6. Infrastructure errors or unexpected programming bugs.

Example public error code table:

| Application error code | Meaning | Caller action |
|---|---|---|
| -20001 | Invalid CUSTOMER_ID | Fix input |
| -20002 | Customer not found | Return business error |
| -20003 | Customer is inactive | Reject operation |
| -20004 | Order is not in an allowed state | Re-read state or return conflict |
| -20005 | Request ID already used with different content | Reject request |
| ORA-08177 | Serialization conflict | Roll back and consider retrying entire transaction |
| ORA-00060 | Deadlock | Handle per concurrency policy |
| ORA-00001 | Unique constraint violation | Distinguish duplicate request from invalid data |
| ORA-06502 | Numeric/string or conversion error in PL/SQL | Investigate data and code |

Callers should classify errors using stable error codes, not by matching English or localized error message text.

## 7. Using RAISE_APPLICATION_ERROR for business errors

PL/SQL provides RAISE_APPLICATION_ERROR to raise application errors with codes in the range -20000 to -20999:

~~~sql
RAISE_APPLICATION_ERROR(
    -20002,
    'Customer does not exist'
);
~~~

This error is sent back to the caller as an Oracle exception. Callers can inspect SQLCODE and SQLERRM.

### 7.1 Centralized error code declarations

A package can expose exception names and error codes publicly:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    e_customer_not_found EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_customer_not_found, -20002);

    PROCEDURE create_order(
        p_customer_id IN customers.customer_id%TYPE,
        p_order_id OUT orders.order_id%TYPE
    );
END order_api;
/
~~~

Callers can catch the exception by name:

~~~sql
BEGIN
    order_api.create_order(999999, :order_id);
EXCEPTION
    WHEN order_api.e_customer_not_found THEN
        DBMS_OUTPUT.PUT_LINE('Customer is not available.');
END;
/
~~~

Naming exceptions makes code easier to read and avoids duplicating numeric codes across many places.

### 7.2 Using the third parameter of RAISE_APPLICATION_ERROR

Syntax:

~~~sql
RAISE_APPLICATION_ERROR(error_code, message, [keep_errors]);
~~~

The third parameter defaults to FALSE. When set to TRUE, the new application error is appended to the error stack rather than replacing the current stack. This is useful when translating a technical error into a business-domain error while keeping the original error in the stack for diagnostics.

Example:

~~~sql
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        RAISE_APPLICATION_ERROR(
            -20005,
            'Request has already been processed',
            TRUE
        );
~~~

Only translate an error when you understand its cause. Do not convert every DUP_VAL_ON_INDEX into "request already processed" if a unique constraint could be violated by another column.

## 8. Preserving original errors and propagating exceptions

### 8.1 Use RAISE to re-raise the current error

Inside an exception handler:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        -- Optionally record diagnostic information.
        RAISE;
END;
~~~

RAISE without an exception name inside a handler re-raises the currently active exception, preserving the original error and backtrace per Oracle mechanisms.

### 8.2 Do not replace the original error with a generic one

Harmful pattern:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        RAISE_APPLICATION_ERROR(
            -20099,
            'Operation failed'
        );
END;
~~~

The caller receives only -20099 and cannot distinguish duplicates, timeouts, deadlocks, or programming errors. If error normalization is needed, translate selectively and preserve the original stack when appropriate.

### 8.3 Do not swallow exceptions

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        NULL;
END;
~~~

This pattern hides failure from the caller. If the procedure performed some DML, the caller may proceed and commit partial data.

Only catch and suppress an error when the API genuinely defines that condition as a normal outcome, has fully handled state, and returns a clear result.

### 8.4 Catch only errors the API can meaningfully handle

Example:

~~~sql
BEGIN
    SELECT status
    INTO l_status
    FROM orders
    WHERE order_id = p_order_id;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20004,
            'Order does not exist'
        );
END;
~~~

If there is only one table SELECT and NO_DATA_FOUND clearly means the order does not exist, this translation makes sense. If multiple different SELECTs in the same block could raise NO_DATA_FOUND, separate the blocks or handle at the specific location so errors are never misattributed.

## 9. Error diagnostics and backtrace

Useful functions in PL/SQL:

- SQLCODE: code of the exception being handled.
- SQLERRM: error message.
- DBMS_UTILITY.FORMAT_ERROR_STACK: full error stack.
- DBMS_UTILITY.FORMAT_ERROR_BACKTRACE: where the exception originally occurred.
- DBMS_UTILITY.FORMAT_CALL_STACK: call stack at the time of invocation.

Example:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('SQLCODE=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('SQLERRM=' || SQLERRM);
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_STACK
        );
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END;
~~~

DBMS_OUTPUT is suitable for learning examples or manual debugging. In production applications, use structured logging and never let logging mask the original exception.

### 9.1 Recording useful context

An error log can include:

- Package/procedure name.
- Request ID/correlation ID.
- Required customer ID or business key.
- SQLCODE and error stack.
- Error backtrace.
- Timestamp, module/action, and session context.
- Retry count if applicable.

Never log passwords, access tokens, card data, or sensitive personal data. Log bind values only when permitted and properly sanitized.

### 9.2 Loggers themselves can fail

If a procedure invokes a logger inside an exception handler and the logger fails, the logger's exception can mask the original exception. Decide whether the logger is permitted to fail silently without hiding the business error, whether an autonomous transaction is used, and whether logging can happen at the application tier instead of the database.

Avoid calling a complex logger inside an exception handler without understanding transaction impact and secondary errors.

## 10. Autonomous transactions and logging

PRAGMA AUTONOMOUS_TRANSACTION creates a transaction independent of the main transaction. It can COMMIT or ROLLBACK independently without committing/rolling back the caller's transaction.

Illustrative example of an independent logger:

~~~sql
CREATE OR REPLACE PROCEDURE write_error_log (
    p_request_id IN VARCHAR2,
    p_error_code IN NUMBER,
    p_message    IN VARCHAR2
) AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO application_error_log(
        request_id,
        error_code,
        error_message,
        logged_at
    )
    VALUES (
        p_request_id,
        p_error_code,
        p_message,
        SYSTIMESTAMP
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END write_error_log;
/
~~~

Using an autonomous transaction means logs can survive even when the business transaction rolls back. This can be useful for error diagnostics.

### 10.1 Do not use autonomous transactions for core business data

If order details are written via an autonomous transaction and the transaction creating the order header rolls back, orphan details without a header can be left behind. Business data requiring consistency must normally stay in the same transaction.

Autonomous transactions should be used only for genuinely independent data such as diagnostic logs or separately defined telemetry.

### 10.2 Avoid deadlocks with the main transaction

An autonomous transaction does not share transaction locks with the main transaction. If an autonomous logger attempts to access a row locked by the main transaction, it can block or deadlock depending on the scenario. Loggers should write to independent tables and avoid depending on the caller's uncommitted data.

## 11. Defining the post-error state contract

Callers need to know after an exception:

- Was the API's DML rolled back to a savepoint?
- Is the caller's transaction still open?
- Must the caller roll back the entire transaction?
- Are any output values reliable?
- Can the call be retried immediately?

A contract table might look like:

| Outcome | Data state | Caller action |
|---|---|---|
| API returns normally | API's changes are pending in caller's transaction | Continue business flow; COMMIT at overall boundary |
| Validation error before DML | No changes made by API | Fix input or return error |
| Error after DML, API rolls back to savepoint | API's DML is undone; work before savepoint remains pending | Handle error; decide to continue or roll back entire transaction |
| Error after DML, API has no savepoint | Partial DML may remain in transaction | Caller must ROLLBACK per contract |
| Serialization error | Transaction must be rolled back and entire unit re-run | Retry with limit if error is classified |
| Connection lost during COMMIT | Commit outcome may be unknown to client | Query status using request ID/idempotency key before resending |

Never leave callers guessing transaction state from error messages.

## 12. Complete example: order creation API

Suppose we have an orders table:

~~~sql
CREATE TABLE orders (
    order_id     NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id  NUMBER NOT NULL,
    request_id   VARCHAR2(64) NOT NULL,
    status       VARCHAR2(20) NOT NULL,
    created_at   TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_orders_request UNIQUE (request_id)
);
~~~

Audit table:

~~~sql
CREATE TABLE order_audit (
    audit_id    NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id    NUMBER NOT NULL,
    action_name VARCHAR2(30) NOT NULL,
    action_time TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

Package specification:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    e_customer_not_found EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_customer_not_found, -20002);

    e_request_conflict EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_request_conflict, -20005);

    PROCEDURE create_order(
        p_customer_id IN  customers.customer_id%TYPE,
        p_request_id  IN  orders.request_id%TYPE,
        p_order_id    OUT orders.order_id%TYPE
    );
END order_api;
/
~~~

Package body:

~~~sql
CREATE OR REPLACE PACKAGE BODY order_api AS
    PROCEDURE create_order(
        p_customer_id IN  customers.customer_id%TYPE,
        p_request_id  IN  orders.request_id%TYPE,
        p_order_id    OUT orders.order_id%TYPE
    ) AS
        l_customer_status customers.status%TYPE;
    BEGIN
        SAVEPOINT order_api_create_sp;
        p_order_id := NULL;

        IF p_customer_id IS NULL OR p_request_id IS NULL THEN
            RAISE_APPLICATION_ERROR(
                -20001,
                'Customer ID and request ID are required'
            );
        END IF;

        SELECT status
        INTO l_customer_status
        FROM customers
        WHERE customer_id = p_customer_id;

        IF l_customer_status <> 'ACTIVE' THEN
            RAISE_APPLICATION_ERROR(
                -20003,
                'Customer is not active'
            );
        END IF;

        INSERT INTO orders(
            customer_id,
            request_id,
            status,
            created_at
        )
        VALUES (
            p_customer_id,
            p_request_id,
            'NEW',
            SYSTIMESTAMP
        )
        RETURNING order_id INTO p_order_id;

        INSERT INTO order_audit(
            order_id,
            action_name,
            action_time
        )
        VALUES (
            p_order_id,
            'CREATED',
            SYSTIMESTAMP
        );

        -- No COMMIT: caller owns the transaction.

    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            ROLLBACK TO order_api_create_sp;
            RAISE_APPLICATION_ERROR(
                -20002,
                'Customer does not exist'
            );

        WHEN DUP_VAL_ON_INDEX THEN
            ROLLBACK TO order_api_create_sp;
            RAISE_APPLICATION_ERROR(
                -20005,
                'Request ID already exists',
                TRUE
            );

        WHEN OTHERS THEN
            ROLLBACK TO order_api_create_sp;
            RAISE;
    END create_order;
END order_api;
/
~~~

This is a structural example. In a real application, determine which unique constraint could raise DUP_VAL_ON_INDEX; if multiple unique constraints exist, do not assume every duplicate is a duplicate request ID. Also handle NULL values in CUSTOMER_STATUS, access privileges, input validation, and how results are returned for already-existing requests.

Caller:

~~~sql
DECLARE
    l_order_id orders.order_id%TYPE;
BEGIN
    order_api.create_order(
        p_customer_id => 101,
        p_request_id  => 'REQ-2026-0001',
        p_order_id    => l_order_id
    );

    -- Can call additional APIs in the same transaction.
    -- payment_api.reserve_payment(l_order_id);

    COMMIT;
    DBMS_OUTPUT.PUT_LINE('Created order ' || l_order_id);
EXCEPTION
    WHEN order_api.e_customer_not_found THEN
        ROLLBACK;
        DBMS_OUTPUT.PUT_LINE('Customer not found');
    WHEN order_api.e_request_conflict THEN
        ROLLBACK;
        DBMS_OUTPUT.PUT_LINE('Request was already used');
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

The API creates the order and audit row within the caller's transaction. The savepoint rolls back the API's DML if an error occurs, while the caller decides to COMMIT the entire business operation.

## 13. Idempotency and retries

Applications may send the same request multiple times due to timeouts, HTTP retries, or lost connections. Write APIs need a way to detect requests that have already been processed.

### 13.1 Idempotency key

A stable request ID for a single request and a unique constraint:

~~~sql
request_id VARCHAR2(64) NOT NULL
~~~

~~~sql
CONSTRAINT uq_orders_request UNIQUE (request_id)
~~~

help the database prevent creating two orders with the same request ID.

However, a unique violation alone is not enough to return an idempotent result. The API must:

1. Detect that the request ID already exists.
2. Check whether the current payload matches the already-processed payload.
3. If identical, return the existing order ID/result.
4. If different, return a clear conflict error.

Simply catching DUP_VAL_ON_INDEX and returning "request already exists" does not give the caller the prior order result.

### 13.2 Retrying serialization errors

For ORA-08177, you typically must roll back the entire transaction and re-run the whole business unit against a fresh snapshot. Do not just re-run the last SQL statement.

Retries should:

- Apply only to errors classified as transient.
- Have a maximum retry limit.
- Use exponential backoff and jitter.
- Re-read data and re-check business rules after starting each new transaction.
- Use a request ID/idempotency key to prevent duplicate effects.

### 13.3 Unknown COMMIT outcomes

If the connection drops right when sending COMMIT, the client may not know whether the transaction committed. Do not immediately generate a new request ID and resend the business operation. Use the same idempotency key to query status and determine the outcome before proceeding.

## 14. Transaction boundaries with external systems

A database transaction cannot automatically roll back emails, HTTP requests, messages already sent to a broker, or operations on external payment systems.

Unsafe example:

~~~text
BEGIN DATABASE TRANSACTION
  Insert order
  Call payment provider
  Send email
  Update inventory
COMMIT
~~~

If the last step fails, a database rollback cannot undo the email or payment request already sent.

### 14.1 Transactional outbox

Outbox pattern:

1. Write business data and an outbox row in the same database transaction.
2. COMMIT.
3. A separate worker reads the outbox and sends messages/emails.
4. The worker marks rows as sent or retries using an idempotency key.

Thus, the event to send exists only if the business change committed.

### 14.2 Sagas and compensation

For workflows spanning multiple systems, a saga can be used: each step has a corresponding compensating action. For example, if inventory reservation succeeds but payment fails, the system issues a command to release inventory.

Compensation is a new business operation, not a database ROLLBACK. It can fail and requires its own retries and monitoring.

## 15. Execution privileges and API security

A package API is also a security boundary.

### 15.1 Definer's rights and invoker's rights

Oracle stored procedures/packages default to running with the owner's privileges (definer's rights). AUTHID CURRENT_USER can be declared to use invoker's rights:

~~~sql
CREATE OR REPLACE PACKAGE reporting_api
AUTHID CURRENT_USER
AS
    PROCEDURE show_summary;
END reporting_api;
/
~~~

Overview:

- Definer's rights: code runs with the privileges of the schema defining the program, suitable when granting EXECUTE on the API instead of granting direct table privileges.
- Invoker's rights: code runs in the caller's privilege context, suitable for utility libraries and cases requiring caller privileges.

Effective privileges are also influenced by roles, direct grants, object resolution, and dynamic SQL. Design following least privilege and test on the exact schema setup.

### 15.2 Do not use dynamic SQL with uncontrolled object names

If an API accepts table/column names from callers and concatenates them into SQL, SQL injection or unintended object access can occur.

When dynamic SQL is unavoidable:

- Bind data values using bind variables.
- Validate object names with an allowlist or appropriate DBMS_ASSERT checks.
- Never concatenate user input directly into SQL text.
- Restrict the executing schema's privileges.

### 15.3 Partitioning is not a security boundary

Putting each tenant in its own partition does not automatically prevent a caller from reading another tenant's data. The API must still enforce tenant context, authorization, and data predicates according to the security model.

## 16. Versioning and API compatibility

The package specification is a public contract. Changing signatures can invalidate dependent objects or force application code updates.

Principles:

- Prefer adding new procedures instead of changing semantics of old procedures.
- Do not reuse old error codes for different meanings.
- Keep NULL and transaction rules stable.
- Evaluate existing callers before altering OUT parameters.
- Do not expose internal table structures in the public API unnecessarily.
- Check dependent objects after compiling a package.

For major changes, create a new API package version, such as ORDER_API_V2, and maintain V1 during the transition period.

## 17. Testing API contracts and transactions

Do not test only the happy path. Test post-error state as well.

### 17.1 Success-path testing

- Valid inputs.
- Correct OUT results.
- Related tables contain pending data per contract.
- Caller commits and another session sees the data.

### 17.2 Testing errors before DML

- Nonexistent ID.
- NULL parameters.
- Invalid business state.
- Caller checks error code and transaction state.

### 17.3 Testing errors after partial DML

Intentionally trigger an error in an audit or detail step:

- Verify the savepoint rolls back the API's portion of work.
- Verify data created by the caller before the savepoint remains pending.
- Verify the caller can choose to COMMIT earlier work or ROLLBACK everything per business rules.

### 17.4 Testing that a procedure does not commit

1. Caller updates a table before calling the API.
2. Call the API to create data.
3. Caller issues ROLLBACK.
4. Verify from another session that neither change exists.

This test catches procedures that COMMIT outside the contract.

### 17.5 Testing multiple APIs in the same transaction

Call the order creation, inventory reservation, and payment reservation APIs in the same transaction. Intentionally fail the last step. Verify the caller rolls back everything and no partial data remains.

### 17.6 Testing idempotency

Send the same request ID twice:

- Same payload must return the same result or same order ID per contract.
- Different payload must return a conflict.
- Must not create two orders or deduct inventory twice.

### 17.7 Testing privileges

Use a caller schema granted only EXECUTE on the package. Verify the caller can execute permitted operations and cannot directly access tables without direct grants.

## 18. Transaction boundary decision diagram

~~~mermaid
flowchart TD
    A["Design procedure/package API"] --> B{"Is API part of a larger use case?"}
    B -->|Yes| C["Caller owns the transaction"]
    B -->|No, API is a standalone unit| D["May choose API-owned transaction"]
    C --> E{"Need to roll back only the API's DML?"}
    E -->|Yes| F["Create SAVEPOINT and rollback to savepoint on error"]
    E -->|No| G["Require caller to roll back entire transaction on error"]
    F --> H["Do not COMMIT inside API"]
    G --> H
    D --> I["Document that COMMIT/ROLLBACK ends session transaction"]
    H --> J["Standardize error contract"]
    I --> J
    J --> K["Test data state after success and exceptions"]
~~~

## 19. Common design mistakes

| Design mistake | Consequence | Fix |
|---|---|---|
| Sub-procedure commits on its own | Commits the caller's work too | Let caller manage the transaction |
| Sub-procedure rolls back everything | Loses caller changes made before the call | Use savepoints when local rollback is needed |
| Unspecified post-exception state | Caller does not know if partial DML remains | Define error/transaction contract |
| Catching WHEN OTHERS and doing NULL | Errors are hidden; caller assumes success | Handle specifically or re-RAISE |
| Translating all errors to one generic code | Loses ability to classify/retry | Use a stable error taxonomy |
| Classifying errors by message text | Messages change by language/version | Rely on SQLCODE/application error codes |
| Using autonomous transactions for business data | Data may persist when main transaction rolls back | Keep business data in the same transaction |
| Calling external APIs before COMMIT | Side effects cannot be rolled back | Use outbox/saga |
| Retrying with a new request ID | Can create duplicate effects | Keep idempotency key stable |
| Reusing SAVEPOINT names in nested calls | Outer savepoint may be overwritten | Namespace and design savepoints clearly |
| Running DDL inside business APIs | Implicit commit breaks transaction boundary | Prepare objects beforehand |
| Public API exposes too many internal tables/records | Hard to evolve implementation | Keep specification small and stable |

## 20. Self-check practice exercises

Run exercises in a test schema with dedicated tables and packages.

### Exercise 1 — Caller-managed API

Write a procedure that inserts an order and audit row without committing. Call it from an anonymous block, then ROLLBACK. Verify from another session that no new data exists.

### Exercise 2 — COMMIT inside a procedure

Create a procedure that issues COMMIT. Have the caller UPDATE a table before calling the procedure, then ROLLBACK after the call. Observe which changes survive and explain how transactions belong to the session.

### Exercise 3 — Local savepoints

Write an API creating a header and detail. Intentionally fail the detail INSERT. Use SAVEPOINT/ROLLBACK TO to undo the API's part, then verify caller changes prior to the savepoint remain.

### Exercise 4 — Nested savepoint names

Write two procedures using the same savepoint name. Call them nested and observe the effect when the inner procedure rolls back to the savepoint. Fix the names to avoid collision and document the contract.

### Exercise 5 — Error codes

Declare a public exception with PRAGMA EXCEPTION_INIT. Use RAISE_APPLICATION_ERROR to raise the error code. Have the caller catch it by exception name and classify the outcome.

### Exercise 6 — Preserving exceptions

Write a procedure triggering a constraint error, catch WHEN OTHERS, and re-RAISE. Compare SQLCODE/error stack with a version that translates every error into one generic code.

### Exercise 7 — Error backtrace

Create three procedure layers: A calls B calls C. C raises an error. Print FORMAT_ERROR_BACKTRACE and FORMAT_CALL_STACK. Identify where the error originally occurred.

### Exercise 8 — Autonomous logger

Write an autonomous logger that writes only to an independent log table. Call the logger and then roll back the main transaction. Confirm the log survives while business data is rolled back. Explain why this pattern must not be used for order details.

### Exercise 9 — Idempotency

Create an API accepting a request ID with a unique constraint. Send the same request twice and design the second call to return the prior result. Send the same ID with a different payload and return a conflict.

### Exercise 10 — Composing multiple APIs

Call order, inventory, and payment reservation APIs in one transaction. Intentionally fail the final step and roll back. Confirm no partial data remains.

### Exercise 11 — DDL and implicit commit

In a test schema, UPDATE a row and then execute DDL. Try ROLLBACK and observe the transaction boundary. Explain why DDL does not belong in business APIs.

### Exercise 12 — Testing package privileges

Create an owner schema and a caller schema. Grant EXECUTE on the package without granting direct table privileges. Test behavior with definer's rights and try designing a separate invoker's rights case.

## 21. Production API design checklist

**Interface**

- Do procedure/function names express business intent?
- Are IN/OUT/IN OUT chosen appropriately?
- Are data types, NULL rules, and value domains defined?
- Does the package specification expose only what is necessary?
- Are public error codes stable?

**Transaction**

- Is transaction ownership clearly documented?
- Can the procedure accidentally COMMIT/ROLLBACK the whole session?
- Does the API need a savepoint to roll back its own DML?
- Can savepoint names collide in nested calls?
- Is there any DDL or implicit commit in the business flow?
- Do callers know they must COMMIT/ROLLBACK on success/failure?

**Errors**

- Are validation, conflict, not-found, and technical errors distinguished?
- Are original exceptions preserved when needed?
- Does WHEN OTHERS re-RAISE or return an intentional error outcome?
- Can error backtraces and request IDs be recorded?
- Does the logger risk masking exceptions or causing deadlocks?

**Correctness**

- Can the API leave partial DML after an exception?
- Are OUT parameters relied upon only on normal return?
- Are retries idempotent?
- How are unknown COMMIT outcomes handled?
- Do external side effects have an appropriate outbox/saga?

**Security and operations**

- Is definer/invoker rights chosen deliberately?
- Does dynamic SQL bind values and validate object names?
- Do logs exclude sensitive data?
- Have transactions and exceptions been tested across multiple sessions?
- Is there a plan for versioning and compile dependencies?

## 22. Key takeaways

| Topic | Principle |
|---|---|
| Package specification | Public contract of the database API |
| Package body | Implementation and internal helpers |
| Transaction | Belongs to the session/connection |
| Caller-managed | Caller decides COMMIT/ROLLBACK |
| API-owned | Use only when the operation is defined as a standalone transaction |
| COMMIT in procedure | Commits the session's entire transaction |
| ROLLBACK in procedure | Rolls back the session's entire transaction |
| SAVEPOINT | Creates a local rollback marker, does not commit |
| DDL | Can trigger implicit commits; avoid in business APIs |
| Error contract | Error codes and post-error state must be clear |
| RAISE | Re-raises the current exception |
| RAISE_APPLICATION_ERROR | Raises application error codes from -20000 to -20999 |
| Autonomous transaction | Reserved for genuinely independent data such as logs |
| Idempotency | Same request does not produce duplicate effects |
| Outbox/Saga | Handles side effects and multi-system coordination |
| Definer/Invoker rights | Determines the execution privilege context |

A reliable database API clearly states what it does, which data it changes, who owns the transaction, and what state callers receive on error. Keeping COMMIT/ROLLBACK responsibility at the right layer enables multiple APIs to compose within one use case; using SAVEPOINT ensures local atomicity; preserving original exceptions or translating selectively aids diagnosis; and designing for idempotency makes retries safe. When these rules are codified as a contract, applications handle the database more consistently and are easier to test.
