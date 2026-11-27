# Building a Business Package with Parameter Contracts and Error Handling

An Oracle PL/SQL package can serve as a business API at the database layer. A package groups related procedures, functions, types, constants, and exceptions into a named unit. When Spring Boot or another system calls the package, the package specification acts as the public contract: it defines which routines can be called, what each parameter means, which data types are exchanged, and which errors can be raised.

A well-designed package gives callers a small, stable, and predictable interface. Callers do not need to know which tables a routine reads, which sequence it uses, or how many SQL statements the logic spans. To achieve this, four parts must be designed explicitly:

- **Parameter contract**: names, types, IN/OUT/IN OUT modes, default values, NULL semantics, units of measure, and compatibility rules.
- **Business behavior**: input preconditions, valid states, side effects, and guaranteed outcomes.
- **Error contract**: error codes, exceptions, trigger conditions, messages, and how clients should handle them.
- **Transaction boundaries and privileges**: who commits/rolls back, what data the routine locks, and whether the package executes with definer or invoker rights.

This lesson builds an order management package as an example. The focus is on designing a stable API that both PL/SQL callers and Java/JDBC callers can use consistently.

## 1. A Package as a Database Business API

A package consists of two parts:

- **Package specification**: declares public elements. Callers see the routines, types, constants, and exceptions declared here.
- **Package body**: implements the logic. The body can contain private procedures/functions and internal state that are not exposed externally.

Example:

    CREATE OR REPLACE PACKAGE customer_api AS
      PROCEDURE activate_customer(
        p_customer_id IN NUMBER
      );

      FUNCTION is_active(
        p_customer_id IN NUMBER
      ) RETURN BOOLEAN;
    END customer_api;
    /

    CREATE OR REPLACE PACKAGE BODY customer_api AS
      PROCEDURE activate_customer(
        p_customer_id IN NUMBER
      ) IS
      BEGIN
        UPDATE customer
        SET active_flag = 'Y'
        WHERE customer_id = p_customer_id;
      END activate_customer;

      FUNCTION is_active(
        p_customer_id IN NUMBER
      ) RETURN BOOLEAN IS
        l_flag customer.active_flag%TYPE;
      BEGIN
        SELECT active_flag
        INTO l_flag
        FROM customer
        WHERE customer_id = p_customer_id;

        RETURN l_flag = 'Y';
      END is_active;
    END customer_api;
    /

The specification tells callers how to invoke the package. The body can change algorithms, add helpers, or tune SQL without forcing callers to change, provided the public contract remains intact.

### 1.1. Why Not Let Applications Access Every Table Directly?

If applications issue raw SQL statements directly to create orders, business logic can end up duplicated across multiple services. One service checks whether the customer is active while another forgets; one batch job updates inventory without locking rows; another client updates order status using different rules.

A business package centralizes shared rules in one place. For example, `CREATE_ORDER` always validates the customer, checks inventory, creates the order header/lines, and deducts inventory within a single transaction.

However, a package does not automatically make a system better. If a package merely wraps a single `INSERT` and adds unnecessary call layers, the payoff is low. Put behaviors in packages when they require reuse, privilege encapsulation, or consistent execution close to the data.

### 1.2. Public API vs. Internal Details

Only expose routines that callers actually need. Helpers such as normalizing input, loading internal configuration, or computing intermediate values can remain private inside the body.

    CREATE OR REPLACE PACKAGE BODY order_api AS

      FUNCTION normalize_actor(
        p_actor IN VARCHAR2
      ) RETURN VARCHAR2 IS
      BEGIN
        RETURN UPPER(TRIM(p_actor));
      END normalize_actor;

      PROCEDURE write_audit(
        p_order_id IN NUMBER,
        p_actor    IN VARCHAR2
      ) IS
      BEGIN
        INSERT INTO order_audit(order_id, actor, action_time)
        VALUES (p_order_id, p_actor, SYSTIMESTAMP);
      END write_audit;

    END order_api;
    /

If callers do not need to call `normalize_actor` or `write_audit`, do not declare them in the specification. This keeps the public API minimal and reduces coupling.

## 2. Designing the Package Specification

The specification is the most critical part of the contract. Changes here can force dependent packages, Java code, batch jobs, and integration clients to recompile or redeploy.

A specification should:

- Use routine and parameter names that clearly describe business intent.
- Define parameter types with sufficient precision and consistency.
- Choose parameter modes matching the data flow.
- Specify NULL, default, and valid value rules clearly.
- Publish meaningful exceptions and error codes.
- Avoid exposing unnecessary internal structures.
- Avoid overloads that are ambiguous to JDBC or other clients.
- Include comments documenting the contract and transaction semantics.

Example:

    CREATE OR REPLACE PACKAGE order_api AS

      PROCEDURE create_order(
        p_customer_id IN  order_header.customer_id%TYPE,
        p_product_id  IN  order_line.product_id%TYPE,
        p_quantity    IN  order_line.quantity%TYPE,
        p_actor       IN  order_header.created_by%TYPE,
        p_order_id    OUT order_header.order_id%TYPE
      );

      FUNCTION calculate_total(
        p_order_id IN order_header.order_id%TYPE
      ) RETURN NUMBER;

      PROCEDURE approve_order(
        p_order_id IN order_header.order_id%TYPE,
        p_actor    IN order_header.approved_by%TYPE
      );

    END order_api;
    /

Callers only need to understand the meaning of `create_order`, `calculate_total`, and `approve_order`. Specific underlying tables remain an implementation detail, even when the specification uses `%TYPE` to stay aligned with column types.

### 2.1. Package and Routine Naming

Name packages by domain capability, such as `ORDER_API`, `CUSTOMER_API`, `INVENTORY_API`, `PAYMENT_API`, or `ACCOUNTING_API`. Avoid overly generic names like `UTIL`, `COMMON`, or `PKG1` for public business packages.

Routine names should use action verbs: `create_order`, `approve_order`, `cancel_order`, `get_balance`. Do not expose implementation-driven names like `update_status_flag` when callers need a business action like `approve_order`.

### 2.2. Contract Comments

Comments in the specification can document:

- Meaning of each parameter.
- Units of measure, such as which currency applies to an amount.
- Whether NULL is accepted or rejected.
- Under which success conditions OUT parameters are populated.
- Exceptions and error codes that may be raised.
- Whether the routine commits or leaves transaction management to the caller.
- Whether it locks rows or may block on locks.
- Idempotency and retry conditions.
- Required privileges.

Example:

    /*
      Creates one order line and reserves inventory.
      p_quantity must be greater than zero.
      p_actor is required and is stored for audit.
      p_order_id is populated only after successful creation.
      The procedure does not COMMIT; the caller owns the transaction.
      Business errors use the ORDER_API error range -20001 to -20009.
    */

Comments must accurately reflect the implementation. If the body changes transaction behavior, update the contract and corresponding tests.

## 3. Choosing Parameter Data Types

Data types are part of the API. Choosing the wrong type can cause precision loss, string truncation, or NLS-dependent conversions.

### 3.1. Using %TYPE When a Parameter Mirrors a Column

If customer ID shares the exact semantics of the `CUSTOMER_ID` column, you can declare:

    p_customer_id IN customer.customer_id%TYPE

Benefits:

- Keeps data types synchronized with the column.
- If the column datatype changes, the package specification updates via dependency tracking and recompilation.
- Reduces redundant repetition of `NUMBER`/`VARCHAR2` lengths.
- Expresses the relationship between the parameter and stored data.

However, `%TYPE` does not replace business documentation. If a column is `NUMBER(10)`, callers still need to know it represents an ID rather than a quantity or monetary amount.

### 3.2. Using Explicit Types for Table-Independent APIs

In some cases, a public API should not depend directly on a physical table. In those cases, use explicit types such as `NUMBER`, `VARCHAR2`, `DATE`, or subtypes declared in the package.

    SUBTYPE t_order_id IS NUMBER;
    SUBTYPE t_currency_code IS VARCHAR2(3);
    SUBTYPE t_actor IS VARCHAR2(128);

    PROCEDURE approve_order(
      p_order_id IN t_order_id,
      p_actor    IN t_actor
    );

PL/SQL subtypes improve readability and reuse, though they do not create a new JDBC type. Java clients still bind according to the underlying SQL type of the parameter.

### 3.3. NUMBER and Currency

Use `NUMBER` for exact numeric values. For monetary amounts, specify precision and scale based on business and currency requirements. Avoid `BINARY_FLOAT`/`BINARY_DOUBLE` for monetary calculations requiring exact decimal arithmetic unless there is a clear reason.

    amount NUMBER(18, 2)

However, not every currency uses two decimal places. Some currencies use different scales; the system needs currency-aware rules and explicit rounding policies.

In Java, use `BigDecimal`. Avoid converting amounts through `double` before creating a `BigDecimal`, as that can introduce binary floating-point representation errors into the database.

### 3.4. VARCHAR2 and Length

Choose lengths according to the contract and target columns. Do not declare `VARCHAR2(4000)` for every parameter simply to avoid thinking about length. Determine:

- Whether length is measured in `BYTE` or `CHAR`.
- Database character set.
- Whether Unicode is allowed.
- How empty strings are handled.
- Whether whitespace is trimmed/normalized or preserved verbatim.
- Domain limits such as actor, code, or description.

Oracle treats empty `VARCHAR2` strings as `NULL` in many contexts. Therefore, if an API must distinguish an empty string from a missing value, define a separate representation or explicit convention.

### 3.5. DATE and TIMESTAMP

Oracle `DATE` stores date and time down to seconds without a timezone. `TIMESTAMP` adds fractional seconds without a timezone. `TSTZ` and `TSLTZ` have distinct timezone semantics.

Choose the type based on meaning:

| Meaning | Recommended Oracle Type | Notes |
|---|---|---|
| Business date | `DATE` | Establish a time-of-day convention, typically midnight |
| Local date/time without timezone | `TIMESTAMP` | Caller must know the timezone per contract |
| Event timestamp with offset | `TIMESTAMP WITH TIME ZONE` | Suitable when representing an instant with an offset |
| Displayed in session timezone | `TIMESTAMP WITH LOCAL TIME ZONE` | Output depends on `SESSIONTIMEZONE` |

Do not accept timestamps as free-form strings parsed via default NLS formats. Prefer typed parameter bindings and define timezone handling at the boundary.

### 3.6. BOOLEAN and SQL/JDBC Compatibility

PL/SQL has `BOOLEAN`, though SQL type support depends on the Oracle version. Do not assume every JDBC driver or SQL context can bind PL/SQL `BOOLEAN` directly like `NUMBER` or `VARCHAR2`.

If the package needs broad SQL/JDBC compatibility, use `NUMBER(1)` or `VARCHAR2(1)` with a clear contract such as `1`/`0` or `Y`/`N`. For PL/SQL-only APIs, `BOOLEAN` may be more natural when supported by the version and callers.

### 3.7. Collections, Records, and Object Types

Packages can declare `RECORD` and collection types. They are convenient for PL/SQL callers, though not always ergonomic for JDBC/ORM clients.

If Java needs to pass a large list, consider schema-level SQL collection types supported by Oracle JDBC, GTT/staging tables keyed by request ID, validated JSON payloads, or bulk operations via staging APIs.

Choose the data-passing mechanism based on payload size, transaction semantics, driver binding support, and version compatibility. Do not expose PL/SQL-only record types if Java clients cannot consume them cleanly.

## 4. IN, OUT, and IN OUT

PL/SQL supports three primary parameter modes.

| Mode | Passed by Caller | Returned by Routine | When to Use |
|---|---|---|---|
| IN | Yes | Does not modify caller's variable | Input data |
| OUT | No initial value needed | Yes | Returning IDs, statuses, or additional outputs |
| IN OUT | Yes | May modify and return | Normalizing or updating a caller-supplied value |

### 4.1. IN

`IN` is the default mode. The caller supplies a value and the routine reads it. Inside the routine, you cannot assign a new value to an `IN` parameter.

    PROCEDURE approve_order(
      p_order_id IN NUMBER
    );

`IN` is appropriate for customer IDs, quantities, amounts, actors, and business options.

### 4.2. OUT

`OUT` is used to return additional data beyond a function return value. For example, creating an order and returning the order ID:

    PROCEDURE create_order(
      p_customer_id IN NUMBER,
      p_order_id OUT NUMBER
    );

An `OUT` parameter should be assigned on every success path. If a routine raises an exception, callers must not rely on partially assigned `OUT` values; the contract should state that output values are valid only upon successful completion.

`OUT` works well for returning a few values, but if an API returns complex multi-field payloads, consider a result type, cursor, or function returning a suitable object instead of excessive `OUT` parameters.

### 4.3. IN OUT

`IN OUT` accepts an initial value and returns the modified value from the routine.

    PROCEDURE normalize_order_code(
      p_code IN OUT VARCHAR2
    );

Example body:

    PROCEDURE normalize_order_code(
      p_code IN OUT VARCHAR2
    ) IS
    BEGIN
      p_code := UPPER(TRIM(p_code));
    END;

Use `IN OUT` when the caller genuinely needs the normalized version back. If the routine simply computes a new output, `OUT` or a function return usually makes the contract clearer.

### 4.4. Do Not Use OUT Parameters to Convey Errors

Do not return error status codes via an `OUT` parameter while the routine can also raise exceptions without a consistent rule. Having two error channels forces callers to guess which result takes precedence.

Choose one clear model:

- Success: return value / `OUT` parameters hold the result.
- Business or technical failure: raise an exception with a contracted error code.
- If an API must return multiple validation errors at once, design a dedicated result structure and document explicitly that the routine does not raise exceptions for those validation failures.

Never mix “return -1” and “raise exception” ad hoc without documentation.

## 5. Default Parameters and Call Notation

PL/SQL allows default values for `IN` parameters. This lets you add optional filters or settings that callers can omit.

    PROCEDURE search_orders(
      p_customer_id IN NUMBER,
      p_status      IN VARCHAR2 DEFAULT NULL,
      p_from_date   IN DATE DEFAULT NULL
    );

Callers can invoke:

    order_api.search_orders(p_customer_id => 7001);

Or:

    order_api.search_orders(
      p_customer_id => 7001,
      p_status => 'NEW'
    );

### 5.1. Positional Notation

Positional notation passes arguments in the exact declaration order:

    order_api.approve_order(900001, 'SERVICE_API');

This is concise but error-prone when multiple parameters share the same type. Changing parameter order or inserting parameters in the specification can break callers.

### 5.2. Named Notation

Named notation explicitly specifies parameter names:

    order_api.approve_order(
      p_order_id => 900001,
      p_actor => 'SERVICE_API'
    );

This improves readability and reduces mix-ups between parameters of the same type. For routines with multiple parameters, prefer named notation in PL/SQL callers.

JDBC `CallableStatement` binds by position or by name depending on driver and API support; do not assume PL/SQL named notation automatically translates to named binds in every JDBC call. A PL/SQL block with positional bind placeholders can also be used.

### 5.3. Is Adding a Default Parameter Backward Compatible?

Appending a trailing parameter with a default value often keeps existing callers working, but it is not universally safe. Factors to verify:

- Overload resolution.
- Callers using positional notation.
- Java/JDBC binding by exact parameter count.
- Dynamic SQL or generated client stubs.
- Package dependencies and invalidation/recompilation.
- Edition-based deployment and active package editions.

Do not treat default parameters as an absolute guarantee of backward compatibility. Test all critical callers before changing a specification.

### 5.4. Defaults Do Not Replace Validation

If `p_status DEFAULT NULL`, the routine must define whether `NULL` means no filter, falling back to a default status, or invalid input. Never let `NULL` carry inconsistent interpretations across routines.

For required parameters, check for `NULL` explicitly and raise a contract error. Oracle does not automatically enforce `NOT NULL` on `IN` parameters.

## 6. Defining Semantics for NULL and Empty Values

`NULL` can mean “not provided”, “unknown”, “not applicable”, or “clear existing value”. These meanings differ and must be defined per parameter.

Example of updating an address:

- Does `NULL` keep the existing address?
- Does `NULL` clear the address?
- Is `NULL` rejected?
- Is an empty string treated as `NULL`?
- Is a separate flag needed to distinguish “field omitted” from “field explicitly set to null”?

For update APIs, a single `IN` parameter is often insufficient to distinguish “no change” from “set to NULL”. You can use explicit flags, overloads, a JSON patch model, or dedicated procedures per operation.

Example:

    PROCEDURE update_customer_email(
      p_customer_id IN NUMBER,
      p_email       IN VARCHAR2,
      p_clear_email IN NUMBER DEFAULT 0
    );

The contract should state:
- `p_clear_email = 1`: clear the email.
- `p_clear_email = 0` and `p_email` is not NULL: set the new email.
- `p_clear_email = 0` and `p_email` is NULL: no change or rejected, per documented choice.

Never design an API where callers must guess `NULL` semantics.

## 7. Designing the Error Contract

Errors need stable codes so callers can classify them programmatically. Never force Java to parse Oracle message text or rely on full `ORA` message formatting.

A package can define application error codes in the `-20000` to `-20999` range using `RAISE_APPLICATION_ERROR`. Reserve sub-ranges by package or domain to avoid code collisions across modules.

Example:

| Error Code | Logical Name | Condition |
|---:|---|---|
| -20001 | INVALID_INPUT | Required parameter missing or invalid |
| -20002 | CUSTOMER_NOT_FOUND | Customer does not exist |
| -20003 | CUSTOMER_INACTIVE | Customer is inactive |
| -20004 | PRODUCT_NOT_FOUND | Product does not exist |
| -20005 | INSUFFICIENT_STOCK | Insufficient inventory |
| -20006 | ORDER_NOT_FOUND | Order does not exist |
| -20007 | INVALID_ORDER_STATE | Order state does not permit the operation |
| -20008 | DUPLICATE_REQUEST | Request has already been processed |
| -20009 | INTERNAL_ERROR | Unclassified internal error |

Logical names and codes are examples. Organizations should maintain an error code registry and never reuse a code for different meanings.

### 7.1. Declaring Public Exceptions

The specification can declare named exceptions bound to error codes:

    CREATE OR REPLACE PACKAGE order_api AS
      e_invalid_input EXCEPTION;
      PRAGMA EXCEPTION_INIT(e_invalid_input, -20001);

      e_customer_not_found EXCEPTION;
      PRAGMA EXCEPTION_INIT(e_customer_not_found, -20002);

      e_insufficient_stock EXCEPTION;
      PRAGMA EXCEPTION_INIT(e_insufficient_stock, -20005);

      PROCEDURE create_order(
        p_customer_id IN NUMBER,
        p_product_id  IN NUMBER,
        p_quantity    IN NUMBER,
        p_order_id    OUT NUMBER
      );
    END order_api;
    /

PL/SQL callers can catch exceptions by package-qualified name:

    BEGIN
      order_api.create_order(7001, 100, 2, :order_id);
    EXCEPTION
      WHEN order_api.e_insufficient_stock THEN
        -- handle stock conflict
        NULL;
    END;
    /

Java callers typically receive a `SQLException` with the corresponding vendor error code. Error codes form a far more stable contract than message text.

### 7.2. RAISE_APPLICATION_ERROR

Use `RAISE_APPLICATION_ERROR` to raise business errors within the application error range:

    RAISE_APPLICATION_ERROR(
      -20005,
      'Insufficient stock for requested quantity'
    );

Messages should be concise, meaningful, and free of sensitive data. Never embed passwords, tokens, full SQL statements containing personal data, or internal infrastructure details in error messages returned to clients.

The optional third parameter controls whether the error is appended to the error stack under Oracle semantics. Use it only when preserving the stack is required and you understand how callers and monitoring display it.

### 7.3. Input Validation

Validate inputs immediately at the package boundary so all callers observe consistent behavior:

    IF p_customer_id IS NULL THEN
      RAISE_APPLICATION_ERROR(
        -20001,
        'Customer ID is required'
      );
    END IF;

    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RAISE_APPLICATION_ERROR(
        -20001,
        'Quantity must be greater than zero'
      );
    END IF;

Do not rely solely on table constraints to report errors. Constraints remain the final safety net, while the package provides clearer business messages and avoids executing unnecessary work before catching invalid input.

### 7.4. Distinguishing Business Errors from Technical Errors

Business errors are predictable contract outcomes, such as a missing customer or insufficient stock. Technical errors are failures outside business conditions, such as full tablespaces, network disconnects, invalid objects, or unexpected internal bugs.

Never collapse all exceptions into a single generic business error. If you catch `WHEN OTHERS` and raise `-20001`, callers will mistake a database outage for invalid input and may skip retries or return the wrong HTTP status code.

One classification scheme:

- Invalid input: dedicated code, typically non-retryable.
- Resource not found: dedicated code, typically non-retryable.
- State conflict / insufficient stock: business error code; client may prompt the user to adjust.
- Deadlock / transient lock: technical error or designated code eligible for bounded retry.
- Connectivity / storage / internal Oracle error: preserve original details for internal logs/monitoring, return a safe error via the API.

## 8. Proper Exception Handling in the Package Body

A sound exception handler preserves root cause, transaction semantics, and diagnostic context.

### 8.1. Catching Specific Exceptions

Example:

    BEGIN
      SELECT active_flag
      INTO l_active_flag
      FROM customer
      WHERE customer_id = p_customer_id;
    EXCEPTION
      WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
          -20002,
          'Customer does not exist'
        );
    END;

Do not use `WHEN OTHERS` when you only intend to handle `NO_DATA_FOUND`. Specific handlers let unexpected errors propagate rather than masking them.

### 8.2. Never Swallow Errors

Anti-pattern to avoid:

    EXCEPTION
      WHEN OTHERS THEN
        NULL;

This misleads callers into thinking the routine succeeded even though data may not have been updated. If an error occurs, callers must receive an exception or a contracted error result.

### 8.3. Logging and Re-Raising

When logging is required, ensure the original exception is preserved. Example:

    EXCEPTION
      WHEN OTHERS THEN
        error_log_api.write_error(
          p_module => 'ORDER_API',
          p_code   => SQLCODE,
          p_text   => SQLERRM
        );
        RAISE;

`RAISE` inside an exception handler re-throws the active exception. Avoid calling `RAISE_APPLICATION_ERROR` with a new code unless intentionally mapping errors, as it can mask or alter the error code callers depend on.

If the logging procedure uses an autonomous transaction so logs survive caller rollbacks, recognize that log entries persist independently. Logging must never mask the original error with a secondary failure; if the logger fails, do not accidentally replace the original exception with a logging exception.

### 8.4. DBMS_UTILITY Error Stack

For diagnostics, you can capture:

    DBMS_UTILITY.FORMAT_ERROR_STACK
    DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
    DBMS_UTILITY.FORMAT_CALL_STACK

These functions record the error stack and exact line where the error originated. They belong in internal logs, not returned verbatim to public clients.

### 8.5. Keeping Error Codes Stable

If Java clients map `ORA-20005` to insufficient stock, never repurpose that code for a different meaning in a future release. You can add new codes, while keeping existing codes stable across compatibility windows or explicit API versions.

Messages may be refined over time, but clients should never parse message text to drive business logic. Rely on vendor error codes and explicit mappings.

## 9. Transaction Boundaries: Who COMMITs and Who ROLLBACKs?

A business package must explicitly declare transaction ownership. This is often overlooked yet directly impacts how Java/Spring integrates with the package.

Two common models exist:

1. **Caller-owned transaction**: the package performs DML without `COMMIT` or `ROLLBACK`; the application or caller controls commit/rollback.
2. **Package-owned transaction**: the routine commits or rolls back internally per contract and owns unit-of-work completion.

For Spring/JPA/JDBC applications, caller-owned transactions are usually more flexible because Spring's transaction manager can coordinate multiple repository calls inside one transaction on the same connection.

### 9.1. Caller-Owned Transactions

Example package body:

    PROCEDURE create_order(...) IS
    BEGIN
      INSERT INTO order_header(...);
      INSERT INTO order_line(...);
      UPDATE inventory ...;
      -- No COMMIT here.
    END;

Java:

    @Transactional
    public Long createOrder(CreateOrderRequest request) {
        Long orderId = orderRepository.createThroughPackage(request);
        auditRepository.writeCreatedEvent(orderId);
        return orderId;
    }

If the package raises an exception, the transaction manager can roll back all transactional changes on that connection. Ensure the package never commits internally or uses autonomous transactions for core business writes.

### 9.2. Package Self-Commit

If a package commits internally, it terminates the active session transaction. This breaks the caller's assumption that everything inside `@Transactional` commits or rolls back atomically.

    @Transactional
    public void process() {
        repository.updateA();
        orderApi.createOrder(); // package COMMITs internally
        repository.updateB();
        throw new RuntimeException();
    }

When the exception occurs, `updateA`/`updateB` may roll back while the changes committed inside `createOrder` remain persisted. The caller loses expected atomicity.

Only use package-owned transactions when it is an intentional, standalone API contract managing an entire unit of work. Document it clearly and never invoke it as part of a larger transaction expecting full rollback.

### 9.3. Do Not Arbitrarily Roll Back the Caller's Transaction

A package should not catch an error and execute a session-wide `ROLLBACK` if the caller may have prior uncommitted work in the same transaction. `ROLLBACK` wipes out all uncommitted work by the caller, including changes outside the package.

If a package must undo its own partial work on error, it can use a `SAVEPOINT` and `ROLLBACK TO SAVEPOINT` within an agreed scope. However, savepoints also belong to the session transaction and must be coordinated with the caller; do not use them if disallowed by the package contract.

### 9.4. Autonomous Transactions Only for Independent Side Effects

`PRAGMA AUTONOMOUS_TRANSACTION` creates an independent transaction. It is useful for audit or error logs that must persist even if the main transaction rolls back, but it should not be used for business data requiring atomicity with the caller's transaction.

For instance, error logs can commit independently. If a package writes orders inside an autonomous transaction while the caller rolls back related steps, data diverges. Reserve autonomous transactions strictly for truly independent, documented side effects.

## 10. Data Locking and Concurrency in Business Packages

A business API must specify how concurrent callers are handled. For example, two requests try to buy the last unit in stock. If both read the balance first and update later, both can see one unit remaining and sell it twice.

### 10.1. SELECT FOR UPDATE

The package can lock the inventory row before checking and decrementing quantity:

    SELECT available_qty
    INTO l_available_qty
    FROM inventory
    WHERE product_id = p_product_id
    FOR UPDATE;

    IF l_available_qty < p_quantity THEN
      RAISE_APPLICATION_ERROR(
        -20005,
        'Insufficient stock'
      );
    END IF;

    UPDATE inventory
    SET available_qty = available_qty - p_quantity
    WHERE product_id = p_product_id;

`FOR UPDATE` holds the row lock until commit or rollback. Other sessions attempting to lock the same row will wait or raise errors according to `NOWAIT`/`WAIT`/`SKIP LOCKED` semantics if specified.

### 10.2. Atomic Conditional Update

An alternative is a conditional update:

    UPDATE inventory
    SET available_qty = available_qty - p_quantity
    WHERE product_id = p_product_id
      AND available_qty >= p_quantity;

    IF SQL%ROWCOUNT = 0 THEN
      RAISE_APPLICATION_ERROR(
        -20005,
        'Insufficient stock or product not found'
      );
    END IF;

This combines check and update in a single SQL statement, minimizing race windows. If you need to distinguish a missing product from insufficient stock, perform a separate check or use `RETURNING`/supplementary logic.

Choose the approach based on locking requirements, error reporting granularity, and contention. Never read quantity with an unlocked `SELECT` and then update without protection.

### 10.3. Consistent Lock Ordering

If a routine locks multiple tables or rows, establish a consistent lock order across all routines. For example, always lock the order header first, then inventory rows in ascending `product_id` order. Inconsistent ordering can trigger deadlocks.

An `ORA-00060` deadlock is not always a simple logic bug; inspect trace logs to identify which locks the two sessions held and awaited. Callers can execute bounded full-transaction retries if the operation is idempotent and the error is transient.

### 10.4. Idempotency and Duplicate Requests

A client can retry a request after a timeout even though the database already committed. If `create_order` lacks an idempotency key, retries can create duplicate orders.

The package can accept `p_request_id` or `p_idempotency_key` and persist it in a table with a unique constraint. When the key already exists, the routine returns the prior result or raises `DUPLICATE_REQUEST` per contract.

Never rely on a naive “does it exist yet?” check before inserting without a matching unique constraint or locking; two concurrent sessions can both pass the check.

## 11. Complete Example: The ORDER_API Package

This section provides an illustrative example featuring a specification, error contract, validation, locking, DML, and transaction ownership. Table/column names and error codes are samples to demonstrate design; adapt them to your actual schema.

### 11.1. Sample Schema

    CREATE TABLE customer (
      customer_id NUMBER(12) PRIMARY KEY,
      active_flag  CHAR(1) NOT NULL
        CHECK (active_flag IN ('Y', 'N'))
    );

    CREATE TABLE product (
      product_id NUMBER(12) PRIMARY KEY,
      active_flag CHAR(1) NOT NULL
        CHECK (active_flag IN ('Y', 'N')),
      unit_price NUMBER(18, 2) NOT NULL
    );

    CREATE TABLE inventory (
      product_id NUMBER(12) PRIMARY KEY
        REFERENCES product(product_id),
      available_qty NUMBER(12) NOT NULL
        CHECK (available_qty >= 0)
    );

    CREATE SEQUENCE order_seq;

    CREATE TABLE order_header (
      order_id NUMBER(18) PRIMARY KEY,
      customer_id NUMBER(12) NOT NULL
        REFERENCES customer(customer_id),
      status VARCHAR2(20) NOT NULL,
      total_amount NUMBER(18, 2) NOT NULL,
      created_by VARCHAR2(128) NOT NULL,
      created_at TIMESTAMP(6) WITH TIME ZONE NOT NULL,
      approved_by VARCHAR2(128),
      approved_at TIMESTAMP(6) WITH TIME ZONE
    );

    CREATE TABLE order_line (
      order_id NUMBER(18) NOT NULL
        REFERENCES order_header(order_id),
      line_no NUMBER(6) NOT NULL,
      product_id NUMBER(12) NOT NULL
        REFERENCES product(product_id),
      quantity NUMBER(12) NOT NULL
        CHECK (quantity > 0),
      unit_price NUMBER(18, 2) NOT NULL,
      line_total NUMBER(18, 2) NOT NULL,
      CONSTRAINT order_line_pk PRIMARY KEY(order_id, line_no)
    );

In this example, an order has one line to keep focus on the package contract. Production systems can accept multi-line collections and compute taxes, discounts, shipping, and currency. When extending, define transaction boundaries, lock order, and error behavior across all line items.

### 11.2. Package Specification

    CREATE OR REPLACE PACKAGE order_api AS

      c_status_new       CONSTANT VARCHAR2(20) := 'NEW';
      c_status_approved  CONSTANT VARCHAR2(20) := 'APPROVED';
      c_status_cancelled CONSTANT VARCHAR2(20) := 'CANCELLED';

      c_err_invalid_input      CONSTANT PLS_INTEGER := -20001;
      c_err_customer_not_found CONSTANT PLS_INTEGER := -20002;
      c_err_customer_inactive  CONSTANT PLS_INTEGER := -20003;
      c_err_product_not_found  CONSTANT PLS_INTEGER := -20004;
      c_err_insufficient_stock CONSTANT PLS_INTEGER := -20005;
      c_err_order_not_found    CONSTANT PLS_INTEGER := -20006;
      c_err_invalid_state      CONSTANT PLS_INTEGER := -20007;

      e_invalid_input EXCEPTION;
      PRAGMA EXCEPTION_INIT(e_invalid_input, -20001);

      e_customer_not_found EXCEPTION;
      PRAGMA EXCEPTION_INIT(e_customer_not_found, -20002);

      e_customer_inactive EXCEPTION;
      PRAGMA EXCEPTION_INIT(e_customer_inactive, -20003);

      e_product_not_found EXCEPTION;
      PRAGMA EXCEPTION_INIT(e_product_not_found, -20004);

      e_insufficient_stock EXCEPTION;
      PRAGMA EXCEPTION_INIT(e_insufficient_stock, -20005);

      e_order_not_found EXCEPTION;
      PRAGMA EXCEPTION_INIT(e_order_not_found, -20006);

      e_invalid_state EXCEPTION;
      PRAGMA EXCEPTION_INIT(e_invalid_state, -20007);

      /*
        Creates an order with one product line.
        Quantity must be a positive integer.
        p_actor is required.
        p_order_id is set on successful completion.
        The caller owns COMMIT and ROLLBACK.
      */
      PROCEDURE create_order(
        p_customer_id IN  customer.customer_id%TYPE,
        p_product_id  IN  product.product_id%TYPE,
        p_quantity    IN  order_line.quantity%TYPE,
        p_actor       IN  order_header.created_by%TYPE,
        p_order_id    OUT order_header.order_id%TYPE
      );

      FUNCTION calculate_total(
        p_order_id IN order_header.order_id%TYPE
      ) RETURN order_header.total_amount%TYPE;

      PROCEDURE approve_order(
        p_order_id IN order_header.order_id%TYPE,
        p_actor    IN order_header.approved_by%TYPE
      );

      PROCEDURE cancel_order(
        p_order_id IN order_header.order_id%TYPE,
        p_actor    IN order_header.created_by%TYPE
      );

    END order_api;
    /

The specification publishes status constants and error codes so callers can use them consistently. In multi-schema applications, you may choose not to expose every constant if clients only need error codes; however, never let individual callers hard-code conflicting meanings.

### 11.3. Package Body: create_order

    CREATE OR REPLACE PACKAGE BODY order_api AS

      PROCEDURE create_order(
        p_customer_id IN  customer.customer_id%TYPE,
        p_product_id  IN  product.product_id%TYPE,
        p_quantity    IN  order_line.quantity%TYPE,
        p_actor       IN  order_header.created_by%TYPE,
        p_order_id    OUT order_header.order_id%TYPE
      ) IS
        l_customer_active customer.active_flag%TYPE;
        l_product_active  product.active_flag%TYPE;
        l_unit_price      product.unit_price%TYPE;
        l_available_qty   inventory.available_qty%TYPE;
        l_order_id        order_header.order_id%TYPE;
        l_actor           order_header.created_by%TYPE;
        l_total           order_header.total_amount%TYPE;
      BEGIN
        p_order_id := NULL;

        IF p_customer_id IS NULL
           OR p_product_id IS NULL
           OR p_quantity IS NULL
           OR p_actor IS NULL THEN
          RAISE_APPLICATION_ERROR(
            c_err_invalid_input,
            'Required order input is missing'
          );
        END IF;

        IF p_quantity <= 0 OR p_quantity <> TRUNC(p_quantity) THEN
          RAISE_APPLICATION_ERROR(
            c_err_invalid_input,
            'Quantity must be a positive integer'
          );
        END IF;

        l_actor := TRIM(p_actor);

        IF l_actor IS NULL THEN
          RAISE_APPLICATION_ERROR(
            c_err_invalid_input,
            'Actor must not be blank'
          );
        END IF;

        BEGIN
          SELECT active_flag
          INTO l_customer_active
          FROM customer
          WHERE customer_id = p_customer_id;
        EXCEPTION
          WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(
              c_err_customer_not_found,
              'Customer does not exist'
            );
        END;

        IF l_customer_active <> 'Y' THEN
          RAISE_APPLICATION_ERROR(
            c_err_customer_inactive,
            'Customer is inactive'
          );
        END IF;

        BEGIN
          SELECT active_flag, unit_price
          INTO l_product_active, l_unit_price
          FROM product
          WHERE product_id = p_product_id;
        EXCEPTION
          WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(
              c_err_product_not_found,
              'Product does not exist'
            );
        END;

        IF l_product_active <> 'Y' THEN
          RAISE_APPLICATION_ERROR(
            c_err_product_not_found,
            'Product is not available'
          );
        END IF;

        BEGIN
          SELECT available_qty
          INTO l_available_qty
          FROM inventory
          WHERE product_id = p_product_id
          FOR UPDATE;
        EXCEPTION
          WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(
              c_err_product_not_found,
              'Inventory record does not exist'
            );
        END;

        IF l_available_qty < p_quantity THEN
          RAISE_APPLICATION_ERROR(
            c_err_insufficient_stock,
            'Insufficient stock'
          );
        END IF;

        l_order_id := order_seq.NEXTVAL;
        l_total := l_unit_price * p_quantity;

        INSERT INTO order_header(
          order_id,
          customer_id,
          status,
          total_amount,
          created_by,
          created_at
        )
        VALUES (
          l_order_id,
          p_customer_id,
          c_status_new,
          l_total,
          l_actor,
          SYSTIMESTAMP
        );

        INSERT INTO order_line(
          order_id,
          line_no,
          product_id,
          quantity,
          unit_price,
          line_total
        )
        VALUES (
          l_order_id,
          1,
          p_product_id,
          p_quantity,
          l_unit_price,
          l_total
        );

        UPDATE inventory
        SET available_qty = available_qty - p_quantity
        WHERE product_id = p_product_id;

        p_order_id := l_order_id;
      END create_order;

      FUNCTION calculate_total(
        p_order_id IN order_header.order_id%TYPE
      ) RETURN order_header.total_amount%TYPE IS
        l_total order_header.total_amount%TYPE;
      BEGIN
        IF p_order_id IS NULL THEN
          RAISE_APPLICATION_ERROR(
            c_err_invalid_input,
            'Order ID is required'
          );
        END IF;

        BEGIN
          SELECT total_amount
          INTO l_total
          FROM order_header
          WHERE order_id = p_order_id;
        EXCEPTION
          WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(
              c_err_order_not_found,
              'Order does not exist'
            );
        END;

        RETURN l_total;
      END calculate_total;

      PROCEDURE approve_order(
        p_order_id IN order_header.order_id%TYPE,
        p_actor    IN order_header.approved_by%TYPE
      ) IS
        l_status order_header.status%TYPE;
        l_actor  order_header.approved_by%TYPE;
      BEGIN
        IF p_order_id IS NULL OR p_actor IS NULL THEN
          RAISE_APPLICATION_ERROR(
            c_err_invalid_input,
            'Order ID and actor are required'
          );
        END IF;

        l_actor := TRIM(p_actor);

        IF l_actor IS NULL THEN
          RAISE_APPLICATION_ERROR(
            c_err_invalid_input,
            'Actor must not be blank'
          );
        END IF;

        BEGIN
          SELECT status
          INTO l_status
          FROM order_header
          WHERE order_id = p_order_id
          FOR UPDATE;
        EXCEPTION
          WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(
              c_err_order_not_found,
              'Order does not exist'
            );
        END;

        IF l_status <> c_status_new THEN
          RAISE_APPLICATION_ERROR(
            c_err_invalid_state,
            'Only NEW orders can be approved'
          );
        END IF;

        UPDATE order_header
        SET status = c_status_approved,
            approved_by = l_actor,
            approved_at = SYSTIMESTAMP
        WHERE order_id = p_order_id;
      END approve_order;

      PROCEDURE cancel_order(
        p_order_id IN order_header.order_id%TYPE,
        p_actor    IN order_header.created_by%TYPE
      ) IS
        l_status order_header.status%TYPE;
      BEGIN
        IF p_order_id IS NULL OR p_actor IS NULL
           OR TRIM(p_actor) IS NULL THEN
          RAISE_APPLICATION_ERROR(
            c_err_invalid_input,
            'Order ID and actor are required'
          );
        END IF;

        BEGIN
          SELECT status
          INTO l_status
          FROM order_header
          WHERE order_id = p_order_id
          FOR UPDATE;
        EXCEPTION
          WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(
              c_err_order_not_found,
              'Order does not exist'
            );
        END;

        IF l_status <> c_status_new THEN
          RAISE_APPLICATION_ERROR(
            c_err_invalid_state,
            'Only NEW orders can be cancelled'
          );
        END IF;

        UPDATE inventory i
        SET available_qty = available_qty + (
          SELECT SUM(ol.quantity)
          FROM order_line ol
          WHERE ol.order_id = p_order_id
            AND ol.product_id = i.product_id
        )
        WHERE EXISTS (
          SELECT 1
          FROM order_line ol
          WHERE ol.order_id = p_order_id
            AND ol.product_id = i.product_id
        );

        UPDATE order_header
        SET status = c_status_cancelled
        WHERE order_id = p_order_id;
      END cancel_order;

    END order_api;
    /

This body illustrates the contract and transaction boundaries. Before using it in production, add audit rules, actor authorization, currency/rounding rules, multi-line support, idempotency, and inventory policies. Routines do not `COMMIT` so callers can combine multiple operations within a single transaction.

### 11.4. Calling the Package from PL/SQL

Use named notation:

    DECLARE
      l_order_id NUMBER;
      l_total NUMBER;
    BEGIN
      order_api.create_order(
        p_customer_id => 7001,
        p_product_id  => 1001,
        p_quantity    => 2,
        p_actor       => 'ORDER_SERVICE',
        p_order_id    => l_order_id
      );

      l_total := order_api.calculate_total(
        p_order_id => l_order_id
      );

      order_api.approve_order(
        p_order_id => l_order_id,
        p_actor    => 'SUPERVISOR'
      );

      COMMIT;
    EXCEPTION
      WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
    END;
    /

The caller owns `COMMIT`/`ROLLBACK`. In this example, if `approve_order` fails, creating the order and deducting inventory are also rolled back within the same transaction.

### 11.5. Calling a Procedure from Java/JDBC

Java invokes procedures with `IN` and `OUT` parameters via `CallableStatement`:

    String sql = "{ call order_api.create_order(?, ?, ?, ?, ?) }";

    try (CallableStatement statement =
             connection.prepareCall(sql)) {

        statement.setLong(1, 7001L);
        statement.setLong(2, 1001L);
        statement.setBigDecimal(3, new BigDecimal("2"));
        statement.setString(4, "ORDER_SERVICE");
        statement.registerOutParameter(5, Types.NUMERIC);

        statement.execute();

        BigDecimal orderId = statement.getBigDecimal(5);
    }

When using Spring `@Transactional`, use the connection obtained from the transaction-managed `DataSource` consistently. Never open an independent connection inside the same workflow if it is expected to participate in the same transaction.

### 11.6. Calling a Function from Java/JDBC

The function return value is bound at the first parameter position:

    String sql = "{ ? = call order_api.calculate_total(?) }";

    try (CallableStatement statement =
             connection.prepareCall(sql)) {

        statement.registerOutParameter(1, Types.NUMERIC);
        statement.setLong(2, 900001L);
        statement.execute();

        BigDecimal total = statement.getBigDecimal(1);
    }

Inspect the error code from `SQLException` if the function raises a business error. Never parse the message text to determine the error category.

## 12. Mapping PL/SQL Errors to Java and REST APIs

Java callers should use an adapter layer to translate Oracle errors into application-layer exceptions. Never let controllers depend directly on scattered `ORA` codes throughout the codebase.

Example:

    try {
        statement.execute();
    } catch (SQLException ex) {
        if (ex.getErrorCode() == 20005) {
            throw new InsufficientStockException(
                "Requested quantity is unavailable", ex
            );
        }
        throw new DatabaseOperationException(
            "Order creation failed", ex
        );
    }

Oracle JDBC vendor error codes are typically returned as positive integers matching `ORA-xxxxx`. Verify the actual values returned by your driver and version with integration tests.

The REST layer can map domain exceptions:

| Domain Exception | Typical Appropriate HTTP Status |
|---|---:|
| InvalidOrderInputException | 400 |
| CustomerNotFoundException | 404 |
| InsufficientStockException | 409 |
| InvalidOrderStateException | 409 |
| DatabaseUnavailableException | 503 |
| UnexpectedDatabaseException | 500 |

This mapping is a reference; your organization's API contract may differ. Never return raw SQL, schema details, stack traces, or full Oracle messages to clients. Log technical details securely and return a correlation ID.

### 12.1. Do Not Retry Every Error

Invalid input or customer-not-found errors cannot be resolved by retrying. Insufficient stock might change after a user edits their cart, but an immediate retry will rarely succeed. Deadlocks or transient connectivity errors may be retried with bounds if the entire operation is idempotent.

Before retrying:

- Determine whether the prior transaction already committed.
- Use an idempotency key whenever requests may be resent.
- Only retry error codes classified as transient.
- Apply backoff and a maximum retry limit.
- Never retry constraint or business conflict errors as if they were network timeouts.

## 13. Execution Privileges: AUTHID DEFINER vs. AUTHID CURRENT_USER

A package can run with the owner's privileges (definer rights) or the caller's privileges (invoker rights).

### 13.1. AUTHID DEFINER

This is the default unless another `AUTHID` is specified. The package executes under the owner's privileges subject to Oracle rules. Callers can be granted `EXECUTE` on the package without receiving direct DML privileges on all internal tables.

    CREATE OR REPLACE PACKAGE order_api
      AUTHID DEFINER
    AS
      PROCEDURE create_order(...);
    END order_api;
    /

This model fits when the package serves as a controlled access API for a schema. The owner must hold required privileges on dependent objects according to stored PL/SQL rules; privileges granted via roles do not apply in the same way as in interactive SQL.

### 13.2. AUTHID CURRENT_USER

Invoker rights cause routines to execute under the caller's privileges per Oracle semantics. It fits utilities that must honor the caller's permissions and schema context.

    CREATE OR REPLACE PACKAGE report_api
      AUTHID CURRENT_USER
    AS
      PROCEDURE run_report(...);
    END report_api;
    /

Do not pick `CURRENT_USER` simply hoping to make a package “safer”. It changes name resolution, privilege checking, and object visibility. Understand its effects on current schema, roles, and dynamic SQL.

### 13.3. Least Privilege

An application user may only require:

    GRANT EXECUTE ON order_api TO app_user;

If the package uses definer rights, the caller does not necessarily need direct `INSERT`/`UPDATE` privileges on business tables. This narrows privileges, though the package must thoroughly validate inputs and avoid unsafe dynamic SQL.

Never grant `CREATE ANY PROCEDURE`, `DBA`, or broad DML privileges to an application user just to make a package run.

## 14. Versioning and Changing the Package Contract

The package specification is the API. Body changes generally affect callers less than specification changes, though they can still alter behavior, locking, or transaction duration.

### 14.1. Lower-Risk Changes

- Optimizing SQL in the body while preserving exact results.
- Adding private helpers.
- Refactoring internal algorithms without altering the contract.
- Adding logging without affecting transaction boundaries.
- Tuning index access paths while keeping semantics identical.

These changes still require regression testing because runtime behavior and performance can shift.

### 14.2. Changes That Can Break Callers

- Changing parameter types or return types.
- Changing parameter order when callers use positional notation.
- Changing `IN` to `OUT` or `IN OUT`.
- Changing default/NULL semantics.
- Changing error codes.
- Adding `COMMIT` to a routine that was previously caller-owned.
- Altering status transitions or exception behavior.
- Changing package `AUTHID`.
- Modifying public record/collection types.
- Altering `REF CURSOR` column shapes.

Before changing anything, search all callers across database schemas and application repositories per code management procedures. Specification changes must be reviewed as breaking API changes.

### 14.3. Overloading Requires Caution

PL/SQL supports overloading procedures/functions with the same name and different signatures. Overloading is convenient for PL/SQL callers but can cause ambiguity with named notation, default parameters, implicit conversions, and JDBC metadata.

If Java/JDBC is a primary client, distinct routine names such as `create_order_v2` or `create_order_from_request` are easier to bind than complex overloads. Avoid overloading solely to bundle variants with unrelated contracts.

### 14.4. Expand-and-Contract

When an API must evolve:

1. Add the new compatible routine or parameter.
2. Deploy updated clients.
3. Monitor callers still invoking the old API.
4. Migrate all callers.
5. Remove the legacy API only in a managed release.

You can keep the old routine as a wrapper calling the new routine during migration. The wrapper must preserve legacy semantics and be marked deprecated in documentation.

## 15. Dependencies, Compilation, and Package Deployment

Packages depend on tables, views, sequences, synonyms, types, and other packages. When a dependent object changes, the package can become `INVALID` and require recompilation.

### 15.1. Checking Status

    SELECT
      owner,
      object_name,
      object_type,
      status
    FROM all_objects
    WHERE owner = 'APP_SCHEMA'
      AND object_name = 'ORDER_API'
    ORDER BY object_type;

Checking compilation errors:

    SELECT
      name,
      type,
      line,
      position,
      text
    FROM user_errors
    WHERE name = 'ORDER_API'
    ORDER BY sequence;

### 15.2. Recompiling

    ALTER PACKAGE order_api COMPILE;
    ALTER PACKAGE order_api COMPILE BODY;

If the specification changes, the body may require recompilation. Successful compilation does not prove business behavior is correct; run tests.

### 15.3. Deploying Specifications and Bodies

In migration scripts, create the specification before the body. Store DDL in version control, execute migrations in order, and check object status after deployment.

Never edit packages directly in production without updating source/migration repositories. If an emergency hotfix is applied, port the change back to the source of truth and test it in the proper environments.

## 16. Testing the Package Contract

A business package must be tested against its contract, not just with a single happy-path run.

### 16.1. Parameter Testing

- `IN` accepts expected types and values.
- `OUT` is populated on success.
- `IN OUT` returns properly normalized values.
- Default parameters behave as documented.
- `NULL`/empty strings follow the contract.
- Boundary values, lengths, precision, and scale.
- Invalid parameters raise the exact contracted error code.

### 16.2. Business State Testing

- Active/inactive customer.
- Active/inactive product.
- Sufficient/insufficient inventory.
- Order `NEW`/`APPROVED`/`CANCELLED`/`DELIVERED`.
- Duplicate idempotency key requests.
- Two sessions concurrently updating the same order/inventory.
- Caller lacking `EXECUTE` privilege.

### 16.3. Transaction Testing

- Package does not commit when contract is caller-owned.
- Exception allows caller to roll back all operations.
- No unintended autonomous transactions.
- Sequence gaps are tolerated properly.
- Trigger/audit side effects are well understood.
- JDBC and Spring transactions share the same connection when atomicity is required.

### 16.4. Error Testing

- Exact error codes returned.
- Messages contain no secrets.
- No swallowed exceptions.
- Technical errors preserved or mapped accurately.
- Java mapping does not rely on message text.
- REST status codes match API contract.

### 16.5. Privilege Testing

Run tests as the application user. Testing as the schema owner does not prove callers have proper grants. Verify `AUTHID`, `EXECUTE` grants, and dependent object privileges.

## 17. Common Design Mistakes

### 17.1. Oversized Package Specifications

Exposing too many helpers and table-oriented routines couples callers to internal implementation. Keep the API small, domain-oriented, and move helpers privately into the body.

### 17.2. Ambiguous Parameter Semantics

A `p_status` parameter might accept `NULL`, empty strings, wildcards, or arbitrary values without documentation. Define allowed values, case sensitivity, `NULL` behavior, and validation rules.

### 17.3. Returning Arbitrary Negative Numbers or Strings for Errors

If one routine returns `-1`, another raises `ORA-20001`, and another sets an `OUT` status, callers must write custom handling per routine. Standardize error reporting through contracted application error codes and exceptions.

### 17.4. Catching WHEN OTHERS and Ignoring It

Swallowing errors leaves callers unaware that a transaction failed. Catch specific exceptions, log per policy, and `RAISE` when unrecoverable.

### 17.5. Unexpected Self-Commits Inside Packages

Callers lose the ability to roll back the entire business unit of work. Specify transaction ownership in the specification and verify from Spring/JDBC.

### 17.6. Dynamic SQL with Unvalidated Input

Concatenating client-supplied table/column names or filters into SQL creates SQL injection vulnerabilities. Use bind variables for values; for identifiers, enforce allowlists and validate using mechanisms such as `DBMS_ASSERT`.

### 17.7. Checking Then Updating Without Locking

This invites overselling or lost updates. Use `SELECT FOR UPDATE` or conditional `UPDATE` checking `SQL%ROWCOUNT`, paired with unique constraints where needed.

### 17.8. Overloads Hard to Call from JDBC

Overloading the same name with compatible types or defaults can confuse JDBC binding. Create distinctly named routines for client APIs when a stable contract is required.

### 17.9. Exposing Client-Incompatible PL/SQL Types

`RECORD`/`BOOLEAN`/PL/SQL collections can be difficult to bind over JDBC. Choose SQL types or data-transfer APIs compatible with your client and driver version.

## 18. Workflow for Building a Business Package

A repeatable workflow for new packages:

1. Identify business capabilities and callers.
2. List public use cases along with initial and terminal states.
3. Author the package specification before the implementation.
4. Define parameter names, modes, data types, and null/default semantics.
5. Define the error code range and exception mapping.
6. Choose transaction ownership and locking strategy.
7. Determine `AUTHID` and least-privilege grants.
8. Implement the package body with validation prior to DML.
9. Write tests for happy paths, boundary cases, failures, and concurrency.
10. Test with both PL/SQL and the JDBC application user.
11. Deploy via version-controlled migrations.
12. Check for invalid objects, grants, object status, and run application smoke tests.

### 18.1. Contract Table Template

Before writing the package, build a contract table for each routine:

| Routine | Input | Output | Business Errors | Transaction |
|---|---|---|---|---|
| create_order | customer, product, quantity, actor | order_id | invalid input, customer/product missing, stock insufficient | Caller-owned |
| calculate_total | order_id | total amount | invalid ID, order missing | Read-only |
| approve_order | order_id, actor | none | order missing, invalid state | Caller-owned |
| cancel_order | order_id, actor | none | order missing, invalid state | Caller-owned |

A contract table forces the development team to agree on behavior before writing the body. You can also add columns for lock behavior, idempotency, authorization, and retry classification.

## 19. Package Specification Review Checklist

- Package and routine names describe domain behavior.
- Public API contains only elements callers need.
- Parameter names are consistent and meaningful.
- Data types, precision, and lengths fit the data.
- `IN`/`OUT`/`IN OUT` modes are chosen appropriately.
- Default and `NULL` semantics are explicitly documented.
- Rules for `OUT` parameters on exceptions are defined.
- Error codes follow a registry and are never reused.
- Exception messages expose no sensitive information.
- Transaction ownership is explicitly declared.
- Locking and idempotency behavior are documented.
- `AUTHID` and required privileges are defined.
- Overloads do not introduce JDBC ambiguity.
- Public types are client-compatible.
- API changes have a versioning/migration plan.

## 20. Deployment and Operations Checklist

- Specification and body are stored in version control.
- Migrations create packages in dependency order.
- Package compiles `VALID`.
- Dependencies and grants are in place.
- Application user can execute the package.
- Both PL/SQL and JDBC tests pass on the target Oracle environment.
- Java/REST error code mapping is verified.
- Transaction commit/rollback honors the contract.
- Session state does not leak across connection pool requests.
- Logging includes correlation IDs and omits secrets.
- Performance and locking are measured under representative workload.
- Migration/package version rollback plan exists.

## 21. Key Principles to Remember

- The package specification is the public contract; the body is the implementation.
- Expose only the routines, types, and constants callers need.
- Use `%TYPE` when parameters mirror table columns directly; use explicit types when the API should remain table-independent.
- Choose `IN`, `OUT`, and `IN OUT` according to data flow; never abuse `OUT` to return ad-hoc error codes.
- Document `NULL`, empty string, default, precision, timezone, and unit-of-measure semantics clearly.
- Use stable application error codes with `RAISE_APPLICATION_ERROR`; callers classify by code, never by parsing message text.
- Catch specific exceptions; never swallow `WHEN OTHERS`; log and `RAISE` when unrecoverable.
- Declare transaction ownership; avoid `COMMIT`/`ROLLBACK` inside packages when callers own the transaction.
- Use locking/conditional updates and idempotency to protect business rules under concurrency and retries.
- Configure `AUTHID` and grants following least privilege.
- Treat specification changes as API changes; audit all callers and JDBC bindings.
- Test with both PL/SQL and the application user via JDBC to validate both logic and contract.

A well-crafted business package gives callers a small, understandable, and stable interface. When parameters, errors, transactions, and privileges are defined upfront, packages protect business data rules inside the database while allowing Spring Boot and other clients to integrate predictably.
