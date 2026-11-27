# Package specification, package body, and public interface in PL/SQL

## 1. What is a package and why separate the specification from the body?

In PL/SQL, a package is a schema object used to group related components into a single unit: procedures, functions, cursors, types, exceptions, constants, and variables. Instead of creating dozens of standalone procedures, we can group them by a business domain such as orders, customers, payments, or reporting.

A package typically has two parts:

- **Package specification:** declares the interface that external code is allowed to use.
- **Package body:** implements the declared procedures/functions and contains internal components visible only to the package itself.

Example:

~~~text
ORDER_API
  |
  +-- PACKAGE SPECIFICATION
  |      +-- approve_order(...)
  |      +-- cancel_order(...)
  |      +-- get_order_total(...)
  |
  +-- PACKAGE BODY
         +-- implementation of approve_order
         +-- implementation of cancel_order
         +-- implementation of get_order_total
         +-- validate_order_state       (private)
         +-- write_audit                (private)
         +-- package initialization
~~~

The caller only needs to know the package name, routine name, parameters, data types, modes, and result. They do not need to know how many tables the routine reads, which cursor it uses, or which internal helpers it calls.

This separation creates a stable **public interface**. The development team can change the algorithm inside the package body without requiring the caller to change, as long as the public contract remains compatible.

## 2. Package specification: the public contract

The package specification is the part that declares components that can be referenced from outside the package, depending on access privileges and visibility scope.

A specification can declare:

- Package-level constants and variables.
- Types and subtypes.
- Exceptions.
- Cursor specifications.
- Procedure and function declarations.
- Pragmas or attributes permitted in the specification.

Example:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    c_status_pending  CONSTANT VARCHAR2(20) := 'PENDING';
    c_status_approved CONSTANT VARCHAR2(20) := 'APPROVED';

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

Other code in the schema can reference it:

~~~sql
BEGIN
    order_api.approve_order(
        p_order_id => 1001,
        p_user_id  => 501
    );
END;
/
~~~

If the caller has EXECUTE privilege on the package, it can invoke the public routine according to PL/SQL rules. The routine name does not need to be redeclared in the caller.

### 2.1. The specification is not the place for algorithms

The specification should focus on the contract:

- What does the routine do?
- Which parameters must the caller pass?
- Is a parameter IN, OUT, or IN OUT?
- What type does the function return?
- Which business exceptions are exposed?
- Which types does the caller need to pass or receive data?

Do not put complex queries, loops, or multi-step workflows into the specification. Implementation belongs in the package body.

### 2.2. Only expose what the caller needs

If a helper only serves a routine inside the package, keep the helper in the body:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    PROCEDURE approve_order (
        p_order_id IN orders.order_id%TYPE,
        p_user_id  IN orders.approved_by%TYPE
    );
END order_api;
/
~~~

The caller only sees APPROVE_ORDER. Validation steps, audit logging, or calculations can be private subprograms in the body.

A small public API is usually easier to learn, test, grant privileges on, and keep compatible than a specification that exposes every helper.

## 3. Package body: where implementation and private components reside

The package body contains the actual definitions for the subprograms declared in the specification. The body can also declare variables, types, cursors, exceptions, and helpers for internal use only.

Example:

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

        IF l_status <> c_status_pending THEN
            RAISE_APPLICATION_ERROR(-20001, 'Order is not pending');
        END IF;
    END validate_order_state;

    PROCEDURE approve_order (
        p_order_id IN orders.order_id%TYPE,
        p_user_id  IN orders.approved_by%TYPE
    ) IS
    BEGIN
        validate_order_state(p_order_id);

        UPDATE orders
        SET status = c_status_approved,
            approved_by = p_user_id,
            approved_at = SYSTIMESTAMP
        WHERE order_id = p_order_id;
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
    END get_order_total;
END order_api;
/
~~~

In the example:

- APPROVE_ORDER and GET_ORDER_TOTAL are exposed in the specification.
- VALIDATE_ORDER_STATE only appears in the body, so the caller cannot invoke it directly via ORDER_API.VALIDATE_ORDER_STATE.
- The body can use public constants from the specification.
- The caller does not know how the status is checked or how the total amount is read.

### 3.1. The package body is where private helpers belong

Private helpers are suitable for:

- Validating input conditions shared within the package.
- Transforming or normalizing internal data.
- Executing a SQL step used by multiple public routines.
- Writing logs/audits following a common rule.
- Breaking down long code so public routines remain readable.

Do not create a helper just to rename a very short statement if it does not clarify responsibility or provide reusability.

### 3.2. The body can contain private variables and types

~~~sql
CREATE OR REPLACE PACKAGE BODY order_api AS
    c_max_attempts CONSTANT PLS_INTEGER := 3;

    TYPE t_validation_result IS RECORD (
        is_valid BOOLEAN,
        reason   VARCHAR2(200)
    );

    l_last_processed_order_id NUMBER;

    ...
END order_api;
/
~~~

These declarations are used only by the package body. The caller cannot reference them directly.

### 3.3. Is a package body mandatory?

A package requires a body when the specification declares subprograms that need implementation or cursors that need definitions. If a package only declares declarative items that do not require an implementation part, a body may not be necessary.

In practice, an API package with procedures/functions usually has a body. If the body is missing or a public routine is not defined, the package cannot operate as expected and will result in a compile/invalid error.

## 4. Comparing specification and body

| Aspect | Specification | Body |
| --- | --- | --- |
| Role | Expose the API | Implement the API |
| Direct caller access | Yes, with appropriate privileges | No |
| Procedure/function | Declare signature | Write implementation |
| Private helper | Do not place here | Yes |
| Internal variables | No | Yes |
| Public constants | Can be declared | Can be used |
| Private constants | No | Yes |
| Business SQL | Should not be placed here | Place here |
| Package initialization | No | Yes |
| Changing implementation | No change needed if API stays the same | Usually only recompile the body |

A useful way to remember:

- The specification answers: “What does the package provide?”
- The body answers: “How does the package accomplish those things?”

## 5. Full package syntax

### 5.1. Package specification

~~~sql
CREATE [OR REPLACE] PACKAGE package_name
    [AUTHID {DEFINER | CURRENT_USER}]
    [ACCESSIBLE BY (...)]
AS
    -- Public declarations
END [package_name];
/
~~~

Optional clauses depend on the version and features used. AUTHID determines the execution privileges of the package. ACCESSIBLE BY is a mechanism to restrict which program units are allowed access in cases Oracle supports; it does not replace GRANT EXECUTE.

### 5.2. Package body

~~~sql
CREATE [OR REPLACE] PACKAGE BODY package_name AS
    -- Private declarations

    -- Public subprogram implementations

BEGIN
    -- Optional package initialization section
END [package_name];
/
~~~

The BEGIN section at the end of the body is the initialization section. It differs from the BEGIN inside each procedure/function: the initialization section runs when the package is initialized in a session, following the package state lifecycle.

### 5.3. Do not put BEGIN at the end of the specification

The specification only declares the interface; it has no executable part and no initialization section. If statements need to run when the package is initialized, place them at the end of the package body.

## 6. Declaring routines in the specification and defining them in the body

The signature in the body must match the declaration in the specification. Parameter names can be considered an important part of the interface when callers use named notation; keep both names and modes consistent.

Specification:

~~~sql
CREATE OR REPLACE PACKAGE customer_api AS
    PROCEDURE change_email (
        p_customer_id IN customers.customer_id%TYPE,
        p_new_email   IN customers.email%TYPE
    );
END customer_api;
/
~~~

Body:

~~~sql
CREATE OR REPLACE PACKAGE BODY customer_api AS
    PROCEDURE change_email (
        p_customer_id IN customers.customer_id%TYPE,
        p_new_email   IN customers.email%TYPE
    ) IS
    BEGIN
        UPDATE customers
        SET email = p_new_email
        WHERE customer_id = p_customer_id;
    END change_email;
END customer_api;
/
~~~

Caller:

~~~sql
BEGIN
    customer_api.change_email(
        p_customer_id => 200,
        p_new_email   => 'new@example.com'
    );
END;
/
~~~

Named notation makes the call site more self-descriptive and reduces the risk of swapping positions when multiple parameters share the same data type.

### 6.1. Do not declare a public routine and forget to define it

If the specification exposes a procedure but the body lacks a corresponding implementation, the package cannot be used normally. When completing a package, ensure every subprogram requiring a body has a matching definition.

### 6.2. Do not define a public implementation only in the body

If a procedure is only defined in the body without being declared in the specification, it is private. Callers cannot invoke it through the package name.

Example:

~~~sql
CREATE OR REPLACE PACKAGE BODY customer_api AS
    PROCEDURE normalize_email (
        p_email IN VARCHAR2
    ) IS
    BEGIN
        NULL;
    END normalize_email;
END customer_api;
/
~~~

NORMALIZE_EMAIL is a private helper if it is not declared in the specification.

## 7. Public interface and API design principles

The package specification is the contract between the package and the caller. When multiple applications depend on a package, each specification change can affect many modules.

A good public interface should:

- Have just enough routines for actual use cases.
- Use names that describe actions or outcomes.
- Have clear parameters and stable data types.
- Clearly define side effects.
- Clearly define transaction ownership.
- Document exceptions that may be raised.
- Avoid exposing unnecessary internal structures.
- Be extensible without breaking existing callers.

### 7.1. Do not turn a package into a table API

Do not expose a procedure for every small SQL statement if callers do not need access to those operations. A public API should represent use cases or business capabilities.

For example, instead of exposing:

~~~sql
PROCEDURE update_order_status(...);
PROCEDURE update_order_user(...);
PROCEDURE update_order_timestamp(...);
~~~

you can expose a business operation:

~~~sql
PROCEDURE approve_order (
    p_order_id IN orders.order_id%TYPE,
    p_user_id  IN orders.approved_by%TYPE
);
~~~

The body decides which columns need to be updated together. The caller does not need to know the detailed storage steps.

### 7.2. Expose data types when callers need them

If a caller needs to pass or receive a collection or record, the package can expose the type:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    TYPE t_order_id_list IS TABLE OF orders.order_id%TYPE;

    PROCEDURE close_orders (
        p_order_ids IN t_order_id_list
    );
END order_api;
/
~~~

The caller can use the type via the package name:

~~~sql
DECLARE
    l_order_ids order_api.t_order_id_list :=
        order_api.t_order_id_list(100, 101, 102);
BEGIN
    order_api.close_orders(l_order_ids);
END;
/
~~~

If a type is only needed inside the body, declare it in the body so as not to expand the API unnecessarily.

### 7.3. Expose business exceptions

A package can expose exceptions so callers can catch them by name:

~~~sql
CREATE OR REPLACE PACKAGE payment_api AS
    e_payment_declined EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_payment_declined, -20071);

    PROCEDURE charge (...);
END payment_api;
/
~~~

Caller:

~~~sql
BEGIN
    payment_api.charge(...);
EXCEPTION
    WHEN payment_api.e_payment_declined THEN
        -- Handle payment decline
        NULL;
END;
/
~~~

For a public API, error codes and exception meanings must be stable. If the exception code or name changes, dependent callers may have to be updated.

## 8. Parameter modes, default values, and named notation

### 8.1. IN

IN passes data into the routine. This is the default mode:

~~~sql
PROCEDURE find_order (
    p_order_id IN orders.order_id%TYPE
);
~~~

Do not modify an IN parameter inside the routine expecting the caller to rely on that change; use OUT or IN OUT when the contract requires returning data.

### 8.2. OUT

OUT returns data to the caller:

~~~sql
PROCEDURE get_order_summary (
    p_order_id IN  orders.order_id%TYPE,
    p_total    OUT orders.total_amount%TYPE,
    p_status   OUT orders.status%TYPE
);
~~~

OUT is suitable when a routine needs to return multiple values. If the result is a single value, a function may be easier to use. With OUT parameters, the caller should treat the output values as reliable only when the routine completes successfully according to the contract.

### 8.3. IN OUT

IN OUT receives an initial value and returns the value after processing:

~~~sql
PROCEDURE normalize_code (
    p_code IN OUT VARCHAR2
);
~~~

IN OUT can be useful for certain data-transformation APIs, but it makes the call site less explicit than separate input/output parameters. Use it when the semantics truly mean “pass a value in and receive back the modified value.”

### 8.4. Default parameters

Defaults can be declared:

~~~sql
PROCEDURE search_orders (
    p_status IN orders.status%TYPE DEFAULT 'OPEN',
    p_limit  IN PLS_INTEGER DEFAULT 100
);
~~~

Callers can omit parameters that have defaults:

~~~sql
BEGIN
    order_api.search_orders;
END;
/
~~~

Or pass using named notation:

~~~sql
BEGIN
    order_api.search_orders(
        p_limit => 50
    );
END;
/
~~~

Defaults make the API convenient to use, but changing a default can alter the behavior of existing callers without requiring changes to the caller's source code. Treat defaults as part of the contract.

### 8.5. Parameter order and compatibility

With positional notation, parameter order matters:

~~~sql
order_api.create_order(100, 'OPEN', 500);
~~~

If a parameter is inserted into the middle of the list, positional callers may fail or pass values with the wrong meaning. Named notation reduces this risk:

~~~sql
order_api.create_order(
    p_customer_id => 100,
    p_status      => 'OPEN',
    p_amount      => 500
);
~~~

When designing a widely used package, prefer named notation in internal code and consider adding new parameters at the end with defaults when extending the API in a compatible way.

## 9. Overloading in packages

PL/SQL allows multiple subprograms with the same name if their signatures can be distinguished according to overloading rules.

Example:

~~~sql
CREATE OR REPLACE PACKAGE report_api AS
    PROCEDURE print_summary (
        p_department_id IN NUMBER
    );

    PROCEDURE print_summary (
        p_department_code IN VARCHAR2
    );
END report_api;
/
~~~

Caller:

~~~sql
BEGIN
    report_api.print_summary(p_department_id => 10);
    report_api.print_summary(p_department_code => 'SALES');
END;
/
~~~

### 9.1. When is overloading useful?

- The same action supports multiple input data types.
- The same API has versions accepting a record or a scalar.
- Callers can choose the natural way to pass data for their use case.

### 9.2. When does overloading cause ambiguity?

If overloads differ only in data types that undergo implicit conversion, a literal NULL or a positional call can make resolution ambiguous.

Example:

~~~sql
report_api.print_summary(NULL);
~~~

Oracle may not be able to determine the intended overload if multiple signatures match. Use explicitly typed variables or named notation, or rename the routine if the two behaviors differ in meaning.

### 9.3. Signatures that cannot be arbitrarily overloaded

You cannot distinguish overloads solely by a function's return type. Two functions with the same name and the same parameter types but different return types do not form a valid overload.

Differences in parameter mode or parameter name are not always sufficient to create distinct overloads. Follow PL/SQL overloading rules and avoid designing APIs that rely on overly subtle differences.

## 10. Public and private components: access scope

### 10.1. Public

Components declared in the specification are public to anyone who can access the package:

~~~sql
CREATE OR REPLACE PACKAGE customer_api AS
    c_active_status CONSTANT VARCHAR2(20) := 'ACTIVE';

    PROCEDURE activate_customer (
        p_customer_id IN customers.customer_id%TYPE
    );
END customer_api;
/
~~~

Callers can use it:

~~~sql
BEGIN
    customer_api.activate_customer(100);
END;
/
~~~

Callers can also reference the public constant if they have appropriate privileges:

~~~sql
IF l_status = customer_api.c_active_status THEN
    ...
END IF;
~~~

### 10.2. Private

Components declared only in the body are private:

~~~sql
CREATE OR REPLACE PACKAGE BODY customer_api AS
    c_inactive_status CONSTANT VARCHAR2(20) := 'INACTIVE';

    PROCEDURE validate_customer (
        p_customer_id IN customers.customer_id%TYPE
    ) IS
    BEGIN
        ...
    END validate_customer;

    PROCEDURE activate_customer (
        p_customer_id IN customers.customer_id%TYPE
    ) IS
    BEGIN
        validate_customer(p_customer_id);
        ...
    END activate_customer;
END customer_api;
/
~~~

Callers cannot invoke CUSTOMER_API.VALIDATE_CUSTOMER or read CUSTOMER_API.C_INACTIVE_STATUS.

### 10.3. Private helpers cannot be accessed from other packages

If another package needs to use the same logic, there are three options:

- Make the routine part of the public API if it is truly a shared capability.
- Move the logic into a shared service package with a clearly designed interface.
- Create a separate schema-level routine if it is an independent API.

Do not attempt to access private routines via dynamic SQL or tricks that rely on implementation details.

## 11. Package initialization and package state

### 11.1. Initialization section

A package body can have a final BEGIN section:

~~~sql
CREATE OR REPLACE PACKAGE session_context_api AS
    FUNCTION get_start_time RETURN TIMESTAMP;
END session_context_api;
/

CREATE OR REPLACE PACKAGE BODY session_context_api AS
    g_start_time TIMESTAMP;

    FUNCTION get_start_time RETURN TIMESTAMP IS
    BEGIN
        RETURN g_start_time;
    END get_start_time;

BEGIN
    g_start_time := SYSTIMESTAMP;
END session_context_api;
/
~~~

The initialization section runs when the package is initialized in a session. It is typically executed once per session package state instance, after the package is loaded/instantiated.

### 11.2. Package state lives per session

Package variables are not global variables shared across all sessions. Each database session has its own package state:

~~~text
Session A                     Session B
---------                     ---------
ORDER_API.g_count = 2         ORDER_API.g_count = 0
ORDER_API.g_mode = 'BATCH'    ORDER_API.g_mode = 'ONLINE'
~~~

Two sessions do not share the same package variable values. This is important when an application uses a connection pool: multiple different requests may successively use the same database session and see leftover package state.

### 11.3. Risks of long-lived state

If a package holds:

- Customer ID from the previous request.
- An enabled debug flag.
- A cached list of privileges.
- Filter values or tenant context.

then a subsequent request reusing the session may be affected if the state is not reset properly.

Prefer parameters and clearly scoped data. If package state is intentional, there must be an explicit reset/init API and verification of how the connection pool returns sessions to the pool.

### 11.4. Package initialization is not the place for heavy work

Avoid running large queries, updating data, or calling external services in the initialization section. Package initialization happens when a session first touches the package; it can make the first request slow or fail due to external dependencies.

The initialization section should be short, deterministic, and have minimal side effects. If configuration data needs to be loaded, consider an explicit init routine with error handling and a caching policy.

### 11.5. Package state invalidation

When a package or dependency is recompiled/invalidated, a session using the package may encounter an error such as ORA-04068 reporting that package state has been discarded. The application may need to handle retries at an appropriate request boundary, while ensuring the business operation can be safely retried.

Do not blindly retry a transaction that has already produced side effects or partially committed. Idempotency and transaction boundaries must be designed properly.

## 12. PRAGMA SERIALLY_REUSABLE

Normal package state persists for the duration of the session. Oracle provides the SERIALLY_REUSABLE mechanism to keep package state per server call instead of retaining state across the entire session like a normal package.

Example:

~~~sql
CREATE OR REPLACE PACKAGE batch_scratch
IS
    PRAGMA SERIALLY_REUSABLE;
    g_counter PLS_INTEGER := 0;
    PROCEDURE increment_counter;
END batch_scratch;
/

CREATE OR REPLACE PACKAGE BODY batch_scratch
IS
    PRAGMA SERIALLY_REUSABLE;

    PROCEDURE increment_counter IS
    BEGIN
        g_counter := g_counter + 1;
    END increment_counter;
END batch_scratch;
/
~~~

SERIALLY_REUSABLE changes the state lifecycle and how the package is initialized/reused. It is not a universal trick to fix every connection pool bug; callers must not rely on package state surviving across server calls.

Both the package specification and body must declare the corresponding pragma as required by Oracle. You should also check the restrictions when the package is called from SQL or combined with other constructs. Use it only when you fully understand its semantics and have measured the memory benefit.

## 13. AUTHID: package execution privileges

A package can run with definer's rights or invoker's rights.

### 13.1. AUTHID DEFINER

This is the default if AUTHID is not specified. Code runs with the privileges of the owner/definer according to definer's rights rules.

~~~sql
CREATE OR REPLACE PACKAGE payroll_api
AUTHID DEFINER
AS
    PROCEDURE calculate_payroll;
END payroll_api;
/
~~~

Definer's rights are useful when a package provides a controlled API to data that callers do not have direct access to. The owner must be granted the necessary privileges directly for stored code according to Oracle rules.

### 13.2. AUTHID CURRENT_USER

Invoker's rights change the privilege context to match the caller:

~~~sql
CREATE OR REPLACE PACKAGE reporting_api
AUTHID CURRENT_USER
AS
    PROCEDURE show_accessible_orders;
END reporting_api;
/
~~~

The package runs with the invoker's privileges in the contexts specified by Oracle. This is useful when the same logic needs to apply each caller's own privileges.

### 13.3. AUTHID is part of the interface

AUTHID is declared in the package specification and affects how the package behaves. Changing from DEFINER to CURRENT_USER can alter object access privileges, name resolution, dynamic SQL behavior, and whether callers can execute it.

Do not change AUTHID just to work around an ORA-01031 error without analyzing the security model. This is a security and compatibility decision.

### 13.4. Definer's rights do not mean callers have DBA privileges

A definer's rights package only uses the owner's privileges according to stored PL/SQL rules; it does not automatically grant all of the owner's privileges to the caller outside the scope of package execution. API design must still restrict operations and validate inputs to avoid turning the package into a privilege escalation path.

### 13.5. Privileges via roles and direct grants

Definer-rights stored PL/SQL typically requires object/system privileges granted directly to the owner rather than only through roles, following Oracle's privilege resolution rules. Check grants and compile errors when a package references objects in another schema.

## 14. EXECUTE privilege and package usage scope

A package is not automatically public to all users. The owner can grant EXECUTE:

~~~sql
GRANT EXECUTE ON order_api TO app_user;
~~~

The caller can then do:

~~~sql
BEGIN
    owner_name.order_api.approve_order(
        p_order_id => 1001,
        p_user_id  => 501
    );
END;
/
~~~

A DBA or the owner can revoke it:

~~~sql
REVOKE EXECUTE ON order_api FROM app_user;
~~~

### 14.1. EXECUTE on a package differs from direct privileges on tables

If a package uses definer's rights, the caller can perform operations permitted by the package without needing direct object privileges on every underlying table, according to the definer-rights model and required privileges.

This makes the public API a security boundary. Do not expose procedures that can arbitrarily modify data or accept arbitrary identifiers without validation.

### 14.2. PUBLIC grant

You can GRANT EXECUTE to PUBLIC, but doing so allows any user to invoke the package if other conditions are met:

~~~sql
GRANT EXECUTE ON utility_api TO PUBLIC;
~~~

Only use this when the package is genuinely a shared general-purpose API and its contents, definer privileges, and risks have been evaluated. Do not grant to PUBLIC just to avoid managing privileges by role/user.

## 15. Dependencies and the impact of changing the specification

### 15.1. Callers depend on the specification

Another package or stored procedure calling ORDER_API.APPROVE_ORDER depends on the specification of ORDER_API.

If only the package body changes while keeping the specification compatible, caller dependencies generally do not need to change in the same way as when a public signature changes.

If the specification changes, Oracle may invalidate dependent objects and require recompilation. Applications may encounter errors if objects have not been recompiled or if the new interface is incompatible.

### 15.2. Body changes usually have less impact

For example, changing how the total amount is calculated inside GET_ORDER_TOTAL while keeping intact:

- Routine name.
- Parameter list.
- Parameter modes.
- Return type.
- Dependent public types.

The caller continues using the same invocation.

### 15.3. Specification changes require version management

Changes that can break callers:

- Renaming a public procedure/function.
- Removing a parameter.
- Changing data type or mode.
- Changing return type.
- Changing a public type/record/collection.
- Renaming a parameter when callers use named notation.
- Changing a default in a way that alters behavior.
- Changing AUTHID.

Before making changes, find dependent objects and applications calling the package. You can add a new overload or a new routine instead of modifying the old signature immediately.

### 15.4. Viewing dependencies and status

~~~sql
SELECT name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM user_dependencies
WHERE referenced_name = 'ORDER_API'
ORDER BY name, type;
~~~

Check invalid objects:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE status = 'INVALID'
ORDER BY object_type, object_name;
~~~

With DBA privileges, DBA_DEPENDENCIES and DBA_OBJECTS can be used for a broader view.

## 16. Compiling, replacing, and managing source

### 16.1. Creating or replacing a specification

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    PROCEDURE approve_order (
        p_order_id IN orders.order_id%TYPE
    );
END order_api;
/
~~~

CREATE OR REPLACE replaces the existing definition. Changing the specification can affect dependent objects; do not treat it like a routine body update.

### 16.2. Replacing a package body

~~~sql
CREATE OR REPLACE PACKAGE BODY order_api AS
    PROCEDURE approve_order (
        p_order_id IN orders.order_id%TYPE
    ) IS
    BEGIN
        UPDATE orders
        SET status = 'APPROVED'
        WHERE order_id = p_order_id;
    END approve_order;
END order_api;
/
~~~

If the specification is unchanged, replacing only the body generally helps keep the API more stable.

### 16.3. Viewing compile errors

~~~sql
SHOW ERRORS PACKAGE order_api;
SHOW ERRORS PACKAGE BODY order_api;
~~~

Or:

~~~sql
SELECT type, line, position, text
FROM user_errors
WHERE name = 'ORDER_API'
ORDER BY type, sequence;
~~~

### 16.4. Checking package status

~~~sql
SELECT object_name, object_type, status, last_ddl_time
FROM user_objects
WHERE object_name = 'ORDER_API'
  AND object_type IN ('PACKAGE', 'PACKAGE BODY');
~~~

The package specification and package body are two separate dictionary objects. Both need to be in a valid state for the package to operate normally.

### 16.5. Recompiling

~~~sql
ALTER PACKAGE order_api COMPILE;
ALTER PACKAGE order_api COMPILE BODY;
~~~

Recompiling does not fix logic errors. If dependencies or source code are invalid, check USER_ERRORS and fix the root cause.

## 17. Dropping a package and changing the API

Dropping a package:

~~~sql
DROP PACKAGE order_api;
~~~

The DROP PACKAGE command drops both the package specification and body. It is not a way to drop only the body. If you want to remove the implementation while keeping the API, do not use DROP PACKAGE; replace the body or handle it according to deployment requirements.

You can drop only the body:

~~~sql
DROP PACKAGE BODY order_api;
~~~

The specification remains, but the package may not work if public subprograms requiring a body no longer have an implementation. Only use this intentionally for administrative or deployment purposes.

Do not drop a shared package before checking dependencies, grants, jobs, and applications calling it.

## 18. Packages and data security

A package can serve as an API layer to control access:

~~~text
Application User
      |
      | EXECUTE
      v
ORDER_API (definer rights)
      |
      +-- validate order ID
      +-- validate state
      +-- update allowed columns
      +-- write audit
      |
      v
ORDERS / ORDER_AUDIT
~~~

Callers may not have direct UPDATE privileges on ORDERS but are granted EXECUTE on ORDER_API. The package exposes only the allowed operations.

To keep this boundary secure:

- Validate all inputs.
- Do not concatenate input into uncontrolled dynamic SQL.
- Do not accept arbitrary table names and execute them with definer privileges.
- Do not expose dangerous helpers unnecessarily.
- Do not return sensitive data beyond what is needed.
- Write audit records according to policy.
- Review AUTHID and direct grants.

A definer-rights package with an overly broad API can create a privilege escalation path. Designing the public interface is part of security design.

## 19. Testing packages

The package specification and body should be tested through the public API, because that is how callers actually use them.

### 19.1. Testing the success path

- Call the routine with valid data.
- Verify that rows changed correctly.
- Verify the return value.
- Check whether the transaction is left for the caller to commit.

### 19.2. Testing failure paths

- NULL or out-of-domain inputs.
- Row not found.
- Unique constraint violation.
- Invalid business state.
- Missing privileges or unavailable dependencies.
- Errors when calling private helpers.

### 19.3. Testing API compatibility

When changing a package specification:

- Compile dependent callers.
- Check both positional and named notation.
- Check overload resolution.
- Check default parameters.
- Check public types and exceptions.
- Check EXECUTE grants.

### 19.4. Testing session-scoped state

If a package has package variables:

1. Open session A and call a routine that changes state.
2. Open session B and read the state.
3. Verify that state is not shared between the two sessions.
4. Run multiple requests on the same session/connection pool.
5. Check whether state is properly reset.

### 19.5. Using a test framework

You can use utPLSQL or the project's PL/SQL test framework to test procedures/functions, set up/tear down data, and assert exceptions. Tests should call the public interface just like the application does; private helpers should only be tested indirectly through public behavior unless there is a specific testing strategy.

## 20. Complete example: customer API with public and private routines

This example illustrates a package with one public procedure, one public function, a public constant, and a private helper.

### 20.1. Table assumption

~~~sql
CREATE TABLE customers_pkg_lab (
    customer_id NUMBER PRIMARY KEY,
    email       VARCHAR2(320 CHAR) NOT NULL,
    status      VARCHAR2(20 CHAR) NOT NULL,
    updated_at  TIMESTAMP
);
~~~

### 20.2. Package specification

~~~sql
CREATE OR REPLACE PACKAGE customer_api_lab AS
    c_status_active CONSTANT VARCHAR2(20) := 'ACTIVE';

    PROCEDURE activate_customer (
        p_customer_id IN customers_pkg_lab.customer_id%TYPE
    );

    FUNCTION is_active (
        p_customer_id IN customers_pkg_lab.customer_id%TYPE
    ) RETURN BOOLEAN;
END customer_api_lab;
/
~~~

### 20.3. Package body

~~~sql
CREATE OR REPLACE PACKAGE BODY customer_api_lab AS
    PROCEDURE ensure_customer_exists (
        p_customer_id IN customers_pkg_lab.customer_id%TYPE
    ) IS
        l_count PLS_INTEGER;
    BEGIN
        SELECT COUNT(*)
        INTO l_count
        FROM customers_pkg_lab
        WHERE customer_id = p_customer_id;

        IF l_count = 0 THEN
            RAISE_APPLICATION_ERROR(-20080, 'Customer not found');
        END IF;
    END ensure_customer_exists;

    PROCEDURE activate_customer (
        p_customer_id IN customers_pkg_lab.customer_id%TYPE
    ) IS
    BEGIN
        ensure_customer_exists(p_customer_id);

        UPDATE customers_pkg_lab
        SET status = c_status_active,
            updated_at = SYSTIMESTAMP
        WHERE customer_id = p_customer_id;
    END activate_customer;

    FUNCTION is_active (
        p_customer_id IN customers_pkg_lab.customer_id%TYPE
    ) RETURN BOOLEAN IS
        l_status customers_pkg_lab.status%TYPE;
    BEGIN
        SELECT status
        INTO l_status
        FROM customers_pkg_lab
        WHERE customer_id = p_customer_id;

        RETURN l_status = c_status_active;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RETURN FALSE;
    END is_active;
END customer_api_lab;
/
~~~

### 20.4. Calling the public API

~~~sql
BEGIN
    customer_api_lab.activate_customer(100);
    COMMIT;
END;
/
~~~

PL/SQL BOOLEAN is not a SQL scalar type that can be selected directly in regular SQL in Oracle 19c. Therefore, the function IS_ACTIVE returning BOOLEAN is suitable for PL/SQL callers:

~~~sql
DECLARE
    l_active BOOLEAN;
BEGIN
    l_active := customer_api_lab.is_active(100);

    IF l_active THEN
        DBMS_OUTPUT.PUT_LINE('Active');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Not active');
    END IF;
END;
/
~~~

If it needs to be called from SQL or JDBC as a scalar type, expose a function returning NUMBER/CHAR with a clear convention instead of BOOLEAN in an Oracle 19c environment.

### 20.5. Private helpers cannot be called directly

The following statement is invalid because ENSURE_CUSTOMER_EXISTS only exists in the body:

~~~sql
BEGIN
    customer_api_lab.ensure_customer_exists(100);
END;
/
~~~

This is intentional: callers only use the operations exposed by the package.

## 21. Common errors and scenarios

| Error/symptom | Possible cause | Resolution |
| --- | --- | --- |
| PLS-00302: component must be declared | Caller invokes a routine/variable not in the specification or misspelled | Check public declarations and package qualifier |
| PLS-00323 | Subprogram is declared in the specification but not properly defined in the body | Compare signatures in the spec and body |
| ORA-04063 | Package has errors or is invalid | Check USER_ERRORS and recompile after fixing |
| ORA-04068 | Existing state of packages has been discarded | Package/dependency was recompiled or invalidated; handle session/retry safely |
| ORA-06508 | Program unit could not be found/invalid when called | Check object status and dependencies |
| ORA-06550 | Compile/parse error in PL/SQL block or call | Check accompanying PLS-xxxxx and USER_ERRORS |
| ORA-01031 | Missing required privilege | Check AUTHID, direct grants, EXECUTE, and object privileges |
| Caller cannot see helper | Helper is declared only in the body | Move to spec only if you intend to expose it as public API |
| Body change breaks caller compilation | Spec/dependencies may also have changed or object became invalid | Compare signatures and compile dependencies |
| State from previous request remains | Package variables live per session | Reset state, use parameters, or redesign |
| Ambiguous overload call | Signatures are too similar or literal NULL is used | Use explicit types, named notation, or a different routine name |
| Caller loses privileges after deploy | GRANT was changed or object was recreated via a different process | Verify grants after deployment |

## 22. Package API design checklist

1. **Does the package have cohesion?** Do the routines belong to the same business domain and reason for change?
2. **Does the specification expose only what is necessary?** Keep internal helpers in the body.
3. **Are signatures clear?** Names, types, modes, and default parameters should be documented.
4. **Can callers use named notation?** Keep parameter names stable.
5. **Are overloads easy to resolve?** Avoid ambiguous signatures with NULL or implicit conversions.
6. **Are public types/exceptions necessary?** Do not expose internal types.
7. **Is transaction ownership clear?** Specify whether the package commits or leaves it to the caller.
8. **Is AUTHID set appropriately?** Treat definer/invoker rights as a security decision.
9. **Are EXECUTE grants assigned to the right targets?** Avoid PUBLIC grants unless needed.
10. **Is package state necessary?** If so, define its lifecycle and reset mechanism.
11. **Does the initialization section have side effects?** Keep it short and deterministic.
12. **Have dependencies been checked?** Find callers before modifying the specification.
13. **Does the body compile cleanly?** Check USER_ERRORS and object status.
14. **Are success/failure paths and API compatibility tested?** Test the way callers actually use it.
15. **Does deployment preserve grants and source versions?** Verify after replace/compile.

## 23. Self-check questions

**Question 1.** How do the responsibilities of a package specification and a package body differ?

**Question 2.** Which components are commonly declared in a specification?

**Question 3.** Where are private helpers declared?

**Question 4.** Can a caller directly invoke a procedure defined only in the body?

**Question 5.** When might a package body not be needed?

**Question 6.** Why is the specification considered a public contract?

**Question 7.** Does changing the body while keeping the signature usually have less impact on callers than changing the specification?

**Question 8.** What roles do IN, OUT, and IN OUT play in a public interface?

**Question 9.** How can default parameters change the behavior of existing callers?

**Question 10.** Is an overload differing only by return type valid?

**Question 11.** Where is the package initialization section located and when does it run?

**Question 12.** Are package variables shared across all database sessions?

**Question 13.** Why must package state be controlled when using a connection pool?

**Question 14.** How does AUTHID DEFINER differ from AUTHID CURRENT_USER?

**Question 15.** Does EXECUTE on a package mean the caller can directly UPDATE the underlying table?

**Question 16.** Why can changing the specification invalidate dependent objects?

**Question 17.** What is ORA-04068 usually related to?

**Question 18.** Why is the public interface part of security design?

<details>
<summary>Answer hints</summary>

1. The specification exposes the interface; the body implements it and keeps private helpers hidden.
2. Public subprogram declarations, types, constants, variables, exceptions, and cursor declarations that callers need to use.
3. In the package body, without being declared in the specification.
4. No. Routines that are not exposed are private.
5. When a package only contains declarations that do not need an implementation body; packages with subprograms requiring implementation need a body.
6. Because callers compile and execute against the published names, types, modes, and semantics.
7. Yes. If the public contract does not change, callers usually do not need to modify call sites.
8. IN receives input, OUT returns output, and IN OUT receives and returns a value.
9. Callers omitting the parameter may receive new behavior when the default changes without modifying source code.
10. No. Return type alone is not enough to overload two functions with the same parameter signature.
11. At the end of the package body; it runs when the package is initialized in a session.
12. No. Each session has its own package state.
13. Because a subsequent request may reuse the session and see state from the previous request.
14. DEFINER uses the owner's privileges according to Oracle rules; CURRENT_USER uses the invoker's privilege context.
15. No. EXECUTE allows calling the package; direct privileges on tables are separate.
16. Because callers depend on public signatures/types and must be revalidated when the contract changes.
17. The current session's package state was discarded due to package/dependency invalidation or recompilation.
18. Because a package can execute with definer privileges and expose data/operations to callers; the API must restrict and validate them.

</details>

## 24. Official Oracle documentation

1. [Oracle Database 19c PL/SQL Language Reference — PL/SQL Packages](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-packages.html): package structure, specification, body, public/private declarations, and package state.
2. [Oracle Database 19c PL/SQL Language Reference — Package Specification](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/package-specification.html): syntax and public components.
3. [Oracle Database 19c PL/SQL Language Reference — Package Body](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/package-body.html): implementation, private declarations, and initialization section.
4. [Oracle Database 19c PL/SQL Language Reference — Package State](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/package-state.html): package state, session lifetime, and invalidation.
5. [Oracle Database 19c PL/SQL Language Reference — Invoker's Rights and Definer's Rights](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/invokers-rights-and-definers-rights-authid-property.html): AUTHID and privilege context.
6. [Oracle Database 19c PL/SQL Language Reference — Overloaded Subprograms](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/overloaded-subprograms.html): overloading rules and call resolution.
7. [Oracle Database 19c SQL Language Reference — CREATE PACKAGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-PACKAGE.html): creating a package specification and package body.
8. [Oracle Database 19c SQL Language Reference — ALTER PACKAGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-PACKAGE.html): compiling and managing packages.
9. [Oracle Database 19c SQL Language Reference — DROP PACKAGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/DROP-PACKAGE.html): dropping packages.
10. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_SESSION.html): resetting package state and managing sessions.
11. [Oracle Database 19c Database Error Messages — ORA-04068](https://docs.oracle.com/en/error-help/db/ora-04068/): package state has been discarded.
12. [Oracle Database 19c Database Error Messages — ORA-06508](https://docs.oracle.com/en/error-help/db/ora-06508/): program unit not found or invalid.

**Key takeaway:** The specification is the public contract, and the body is where implementation and private helpers live. Keep the API small, signatures clear, and transaction ownership transparent; replace the body when changing implementation, and only change the specification when the contract truly needs to change. Package state exists per session, AUTHID determines privilege context, and EXECUTE grants determine who can call the API. Every specification change must be evaluated for dependencies, compatibility, grants, and tests before deployment.
