# Private members, package state, and initialization in PL/SQL

A package is a PL/SQL code organization unit that groups related data types, constants, variables, cursors, exceptions, procedures, and functions into a single namespace. A package typically has two parts: the **package specification** exposes the members that other programs are allowed to use, while the **package body** contains the implementation and private members used only inside the package.

A package can also maintain **state (package state)** in the memory of a database session. Package variables, constants, cursors, and related state can persist across multiple procedure calls within the same session. When a package is referenced for the first time in a session, Oracle initializes that package instance; the initialization section in the package body is executed according to the lifecycle of the instance. Understanding this mechanism is crucial in applications using a connection pool, because multiple requests can successively reuse the same database session.

This lesson belongs to the **Procedures and packages** topic of *Database Engine Relational Oracle*. The content focuses on:

- Roles and structure of the package specification and package body.
- Public and private members, access scope, and encapsulation.
- Package state and lifetime per database session.
- Timing of package initialization and initialization order.
- The initialization section in the package body.
- Impact of connection pools, package invalidation, and recompilation.
- Stateless packages, session state, and SERIALLY_REUSABLE.
- Querying package metadata, error handling, and SQL hands-on practice.

## 1. What is a package?

A package is a PL/SQL schema object that contains related components. Instead of creating many standalone schema-level procedures/functions, we can group them by a business domain.

For example, an order management package might contain:

- Constants representing order statuses.
- Record and collection types used in business logic.
- Module-specific exceptions.
- Procedures to create, confirm, or cancel orders.
- Functions to calculate total amounts.
- Private variables used to store per-session caches or configuration.

A package creates a namespace, allowing structured calls such as `order_api.create_order` or `order_api.calculate_total`.

### Two main parts

~~~text
ORDER_API
|
+-- Package specification
|   +-- Public types
|   +-- Public constants and variables
|   +-- Public cursors
|   +-- Public exceptions
|   +-- Procedure/function declarations
|
+-- Package body
    +-- Private types, variables, cursors
    +-- Private procedures/functions
    +-- Implementations of public subprograms
    +-- Optional initialization section
~~~

The package specification is the interface of the package. The package body is the implementation. External programs can only access members declared in the specification, subject to appropriate privileges.

### A package is not a transaction

Package state resides in session memory, not in a transaction or persistent table storage. Calling a procedure in a package does not automatically create an independent transaction; DML still participates in the session's current transaction unless the code issues COMMIT/ROLLBACK or uses a separate mechanism. Ending a transaction does not automatically clear package variables.

## 2. Package specification: the public interface

The package specification declares the members that callers can reference. It does not need to contain procedure/function bodies; the subprograms declared here usually have their implementations in the package body.

Syntax:

~~~sql
CREATE OR REPLACE PACKAGE package_name AS
    -- Public declarations
END package_name;
/
~~~

Example:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    c_default_currency CONSTANT VARCHAR2(3) := 'VND';

    e_invalid_order EXCEPTION;

    PROCEDURE confirm_order(
        p_order_id IN NUMBER
    );

    FUNCTION order_total(
        p_order_id IN NUMBER
    ) RETURN NUMBER;
END order_api;
/
~~~

Callers can reference public members using the package name:

~~~sql
BEGIN
    order_api.confirm_order(1001);
    DBMS_OUTPUT.PUT_LINE(order_api.order_total(1001));
    DBMS_OUTPUT.PUT_LINE(order_api.c_default_currency);
END;
/
~~~

The package name serves as a qualifier for public members. This avoids conflicts with variable or procedure names in other schemas and clearly shows which API the program is using.

### What can be declared in the specification?

The specification can expose:

- Public constants and variables.
- PL/SQL data types such as RECORD, TABLE, VARRAY, and subtypes.
- Cursor specifications.
- Exceptions.
- Procedure and function signatures.
- Pragmas or declarations supported by PL/SQL in a package spec depending on the version.

Do not put unnecessary implementation details into the specification. Any change to the public spec can affect callers and require dependent objects to recompile.

### Package specification containing only public data

If a package only exposes constants, types, or variables without subprograms needing implementation, a package body may not be required:

~~~sql
CREATE OR REPLACE PACKAGE app_constants AS
    c_max_attempts CONSTANT PLS_INTEGER := 5;
    c_default_language CONSTANT VARCHAR2(5) := 'vi';
END app_constants;
/
~~~

This package has no procedure/function bodies and no separate initialization section. Constant values are initialized according to the package declarations.

## 3. Package body: implementation and private members

The package body contains the bodies of the declared procedures/functions, along with declarations needed only inside the package.

Syntax:

~~~sql
CREATE OR REPLACE PACKAGE BODY package_name AS
    -- Private declarations

    -- Public subprogram implementations

    -- Optional initialization section
BEGIN
    -- Initialization statements
END package_name;
/
~~~

Example:

~~~sql
CREATE OR REPLACE PACKAGE BODY order_api AS
    FUNCTION is_valid_order(p_order_id NUMBER)
        RETURN BOOLEAN
    IS
        l_count PLS_INTEGER;
    BEGIN
        SELECT COUNT(*)
        INTO l_count
        FROM orders
        WHERE order_id = p_order_id;

        RETURN l_count = 1;
    END is_valid_order;

    PROCEDURE confirm_order(p_order_id IN NUMBER) IS
    BEGIN
        IF NOT is_valid_order(p_order_id) THEN
            RAISE e_invalid_order;
        END IF;

        UPDATE orders
        SET status = 'CONFIRMED'
        WHERE order_id = p_order_id;
    END confirm_order;

    FUNCTION order_total(p_order_id IN NUMBER)
        RETURN NUMBER
    IS
        l_total NUMBER;
    BEGIN
        SELECT NVL(SUM(quantity * unit_price), 0)
        INTO l_total
        FROM order_lines
        WHERE order_id = p_order_id;

        RETURN l_total;
    END order_total;
END order_api;
/
~~~

`is_valid_order` is defined only in the package body and not declared in the specification, so it is a private helper. Callers cannot invoke `order_api.is_valid_order` directly. Procedure `confirm_order` can call the helper because both belong to the package body.

### How do public and private differ?

| Member | Where is it declared? | Who can access it? |
| --- | --- | --- |
| Public constant/variable/type | Package specification | Callers with access privileges and code inside the package |
| Public procedure/function | Signature in specification, body in package body | Callers with EXECUTE privilege and code inside the package |
| Private variable/type/cursor | Package body only | Code inside the package body |
| Private procedure/function | Package body only | Code inside the package body |
| Initialization section | End of package body | Oracle runs it when initializing the package instance; callers do not invoke it directly |

Private members hide implementation details and allow internal changes without altering the public interface. This is the principle of encapsulation.

### Private members cannot be called from outside

Suppose the body has:

~~~sql
CREATE OR REPLACE PACKAGE BODY order_api AS
    PROCEDURE write_internal_log(p_message VARCHAR2) IS
    BEGIN
        INSERT INTO app_log(message, created_at)
        VALUES (p_message, SYSTIMESTAMP);
    END write_internal_log;
END order_api;
/
~~~

Callers cannot execute `order_api.write_internal_log(...)` because the procedure is not declared in the specification. If callers need the functionality, expose an appropriate public procedure and keep the helper private.

## 4. Declaration order in the package body

PL/SQL needs to know a declaration before a subprogram calls that name, unless a forward declaration is used. Therefore, private helpers are usually declared before the public subprograms that use them.

~~~sql
CREATE OR REPLACE PACKAGE BODY order_api AS
    PROCEDURE write_internal_log(p_message VARCHAR2) IS
    BEGIN
        INSERT INTO app_log(message, created_at)
        VALUES (p_message, SYSTIMESTAMP);
    END write_internal_log;

    PROCEDURE confirm_order(p_order_id IN NUMBER) IS
    BEGIN
        UPDATE orders
        SET status = 'CONFIRMED'
        WHERE order_id = p_order_id;

        write_internal_log('Confirmed order ' || p_order_id);
    END confirm_order;
END order_api;
/
~~~

If two private subprograms call each other and cannot be ordered linearly, a forward declaration can be used:

~~~sql
CREATE OR REPLACE PACKAGE BODY sample_pkg AS
    PROCEDURE step_b(p_value NUMBER);

    PROCEDURE step_a(p_value NUMBER) IS
    BEGIN
        IF p_value > 0 THEN
            step_b(p_value - 1);
        END IF;
    END step_a;

    PROCEDURE step_b(p_value NUMBER) IS
    BEGIN
        IF p_value > 0 THEN
            step_a(p_value - 1);
        END IF;
    END step_b;
END sample_pkg;
/
~~~

A forward declaration provides the signature upfront so the compiler knows the subprogram will be defined later.

## 5. What is package state?

Package state is the runtime value of variables, constants, cursors, and related state belonging to a package instance within a session. For stateful packages, Oracle preserves this state across multiple package calls within the same database session.

Example:

~~~sql
CREATE OR REPLACE PACKAGE request_counter AS
    PROCEDURE increment;
    FUNCTION current_value RETURN PLS_INTEGER;
END request_counter;
/

CREATE OR REPLACE PACKAGE BODY request_counter AS
    g_count PLS_INTEGER := 0;

    PROCEDURE increment IS
    BEGIN
        g_count := g_count + 1;
    END increment;

    FUNCTION current_value RETURN PLS_INTEGER IS
    BEGIN
        RETURN g_count;
    END current_value;
END request_counter;
/
~~~

G_COUNT is a private package variable. Within the same session:

~~~sql
BEGIN
    request_counter.increment;
    request_counter.increment;
    DBMS_OUTPUT.PUT_LINE(request_counter.current_value);
END;
/
~~~

The result is 2. Calling `request_counter.increment` again in the same session increments the value further. If another session calls the package for the first time, it gets its own package state initialized to 0.

### Package state is not shared across sessions

Suppose Session A executes increment twice, while Session B executes it once:

~~~text
Session A                         Session B
-------------------------         -------------------------
request_counter.g_count = 0       request_counter.g_count = 0
increment                         increment
increment
current_value = 2                 current_value = 1
~~~

Two sessions cannot see each other's package variables. A package variable is not a database-wide global variable; it belongs to a package instance tied to a session.

### Package state differs from table data

- Package variables live in session memory and are not automatically persisted to datafiles.
- COMMIT/ROLLBACK does not automatically reset package variable values.
- When a session ends, that session's package state is released.
- Other sessions cannot automatically see the package state.
- To share persistent data across sessions, use tables or an appropriate storage mechanism.

Do not use package variables to store business state that must survive after a session ends or remain consistent across multiple sessions.

## 6. Package initialization process

A stateful package is initialized when a session first references that package. Creating a package with CREATE PACKAGE/CREATE PACKAGE BODY only compiles and stores the schema object definition; it does not run the initialization section for all sessions.

When a session first references a package member, Oracle creates a package instance for that session. Variable declarations are initialized according to their default values/declaration expressions; then the optional initialization section at the end of the package body is executed. Package state is retained for subsequent calls in the same session, unless released or invalidated by Oracle mechanisms.

### Initialization section

The initialization section is the BEGIN ... END block at the end of the package body, after all declarations and subprogram definitions. It is not a public procedure and callers cannot invoke it directly.

~~~sql
CREATE OR REPLACE PACKAGE session_settings AS
    FUNCTION current_region RETURN VARCHAR2;
    PROCEDURE set_region(p_region IN VARCHAR2);
END session_settings;
/

CREATE OR REPLACE PACKAGE BODY session_settings AS
    g_region VARCHAR2(10) := 'APAC';
    g_initialized_at TIMESTAMP;

    FUNCTION current_region RETURN VARCHAR2 IS
    BEGIN
        RETURN g_region;
    END current_region;

    PROCEDURE set_region(p_region IN VARCHAR2) IS
    BEGIN
        g_region := p_region;
    END set_region;

BEGIN
    g_initialized_at := SYSTIMESTAMP;
    DBMS_OUTPUT.PUT_LINE('session_settings initialized');
END session_settings;
/
~~~

In a new session, on the first call:

~~~sql
BEGIN
    DBMS_OUTPUT.PUT_LINE(session_settings.current_region);
END;
/
~~~

Oracle initializes the package instance and runs the initialization section before executing the call requiring the package. Subsequent calls in the same session do not re-run the initialization section; the g_region value retains its modified state.

### When does the initialization section run?

- When a session first references the package instance, such as calling a public procedure/function or referencing a public variable.
- Runs once per package instance in that session.
- Does not re-run after each procedure call in the package.
- Does not run at CREATE/COMPILE time for all sessions.
- Another session has its own package instance and initializes separately on its first reference.

If package state is invalidated/discarded, the session may need to recreate the state and run initialization when the package is used again. Applications must handle invalidation errors that can occur during deployment/recompilation.

### Initialization order

When a package is instantiated, package variables are initialized according to their declarations; the initialization section runs after the package declarations have been set up. Therefore, the initialization section can read/write package variables:

~~~sql
CREATE OR REPLACE PACKAGE init_demo AS
    FUNCTION effective_count RETURN PLS_INTEGER;
END init_demo;
/

CREATE OR REPLACE PACKAGE BODY init_demo AS
    g_start_count PLS_INTEGER := 10;
    g_effective_count PLS_INTEGER;

    FUNCTION effective_count RETURN PLS_INTEGER IS
    BEGIN
        RETURN g_effective_count;
    END effective_count;
BEGIN
    g_effective_count := g_start_count + 5;
END init_demo;
/
~~~

After the package is initialized, g_effective_count is 15 in the session's package state. Ordering between declarations and their dependencies should be kept simple, avoiding complex initialization chains across multiple packages.

The first reference can be made via a public function:

~~~sql
BEGIN
    DBMS_OUTPUT.PUT_LINE(init_demo.effective_count);
END;
/
~~~

### Initialization can execute SQL

The initialization section can execute PL/SQL statements, including querying data to load configuration into package state:

~~~sql
CREATE OR REPLACE PACKAGE runtime_config AS
    FUNCTION tax_rate RETURN NUMBER;
END runtime_config;
/

CREATE OR REPLACE PACKAGE BODY runtime_config AS
    g_tax_rate NUMBER;

    FUNCTION tax_rate RETURN NUMBER IS
    BEGIN
        RETURN g_tax_rate;
    END tax_rate;
BEGIN
    SELECT config_number
    INTO g_tax_rate
    FROM application_config
    WHERE config_key = 'TAX_RATE';
END runtime_config;
/
~~~

This example assumes the APPLICATION_CONFIG table has exactly one row for the TAX_RATE key. If there is no row, NO_DATA_FOUND occurs; if there is more than one row, TOO_MANY_ROWS occurs and initialization fails. Initialization can add latency to the first request and create dependencies on tables/configuration; consider caching, default values, and error handling.

The caller triggers initialization when referencing the public function:

~~~sql
BEGIN
    DBMS_OUTPUT.PUT_LINE(runtime_config.tax_rate);
END;
/
~~~

Do not place heavy work, external service calls, or logic with hard-to-control side effects in the initialization section. Initialization occurs implicitly when the package is referenced, so even a call that appears to merely read a constant can trigger initialization if the package body has an initialization section.

### Specification-only packages

A package containing only declarations that does not require a package body has no initialization section. Initial values of public variables/constants are still tied to the package instance per their declarations, but there is no separate BEGIN block in a body to execute.

## 7. Package state and connection pools

Package state belongs to a database session, whereas a connection pool reuses sessions across multiple application requests. These two concepts create risk if a package retains request data without being reset.

Example:

~~~sql
CREATE OR REPLACE PACKAGE request_context AS
    g_user_id NUMBER;
    g_tenant_id NUMBER;

    PROCEDURE set_context(
        p_user_id IN NUMBER,
        p_tenant_id IN NUMBER
    );

    PROCEDURE clear_context;
END request_context;
/

CREATE OR REPLACE PACKAGE BODY request_context AS
    PROCEDURE set_context(
        p_user_id IN NUMBER,
        p_tenant_id IN NUMBER
    ) IS
    BEGIN
        g_user_id := p_user_id;
        g_tenant_id := p_tenant_id;
    END set_context;

    PROCEDURE clear_context IS
    BEGIN
        g_user_id := NULL;
        g_tenant_id := NULL;
    END clear_context;
END request_context;
/
~~~

Suppose request A borrows connection/session 1, sets user_id = 100 and tenant_id = 10, and returns the connection to the pool. If request B later receives the exact same session 1 without resetting package state, B can see request A's values. This is a cross-request state leakage bug.

### Rules when using package state in a pool

- Set state at the start of each request, before calling business logic that needs it.
- Reset state in the finally/cleanup path before returning the connection to the pool.
- Ensure mid-request errors do not bypass the reset step.
- Do not treat COMMIT/ROLLBACK as a way to clear package state.
- Whenever possible, pass context via explicit parameters instead of keeping implicit state.
- Check the pool's policies on session reuse and session reset.

Application-tier example:

~~~java
try (Connection connection = dataSource.getConnection()) {
    try {
        setRequestContext(connection, userId, tenantId);
        processRequest(connection);
        connection.commit();
    } catch (Exception ex) {
        connection.rollback();
        throw ex;
    } finally {
        clearRequestContext(connection);
    }
}
~~~

This is a conceptual pattern; production code must ensure cleanup runs before the connection is returned to the pool and handle cases where the reset operation itself fails. Do not assume closing the logical connection clears state if the pool merely returns the session to its queue.

### Package state can outlive a request

A pooled session can serve hundreds of requests over time. Thus, a package variable can outlive a single request and retain stale data. Distinguish between:

- Request lifetime: the duration of handling one application request.
- Session lifetime: how long the database session remains alive in the pool.
- Package state lifetime: tied to the package instance in the session, often spanning multiple requests that reuse the session.

If data is only meaningful for a single request, prefer parameters or context with an explicit reset mechanism.

## 8. Recompilation, invalidation, and existing package state

A package is a schema object that can be recompiled when a DBA deploys a new version, modifies the specification/body, or alters dependent objects. When a package changes, package state in sessions currently using that package may be invalidated/discarded. This is especially important for packages holding caches or request state.

Oracle errors that may occur during invalidation/recompilation include:

| Error code | Common meaning |
| --- | --- |
| ORA-04061 | Existing state of package has been invalidated. |
| ORA-04065 | Not executed, altered or dropped stored procedure/package. |
| ORA-04068 | Existing state of packages has been discarded. |
| ORA-06508 | PL/SQL could not find program unit being called. |

Exact messages depend on how the package was changed, dependencies, and when the session calls the package again.

### Why can active sessions be affected?

Suppose session A has already called the package and the package instance holds cached values. A DBA deploys CREATE OR REPLACE PACKAGE BODY. The dictionary definition changes; the old state in the session may no longer match the new code. When session A calls the package again, Oracle may report that the package state was invalidated/discarded and needs to be reinitialized.

Do not treat package state as a durable cache across deployments. If cached data must survive recompilations or be synchronized across sessions, store it in a tier with an appropriate lifecycle.

### Recompiling body and specification

- Changing the package body typically affects internal implementation, yet it can still invalidate package state in sessions.
- Changing the package specification can cause dependent objects to require recompilation because the public interface changed.
- Modifying objects that the package depends on can also invalidate the package.
- Recompilation does not mean every session immediately re-runs initialization at the moment the DBA runs DDL; reinitialization happens on the next use after the state is discarded.

Deploy packages via a controlled process, monitor invalid objects, and prepare the application to handle errors on calls immediately following deployment.

### Retrying after ORA-04068 requires caution

Some applications handle ORA-04068 by discarding old state, acquiring a fresh connection, or retrying the call. However, never automatically replay a non-idempotent request without determining how far DML in the previous call progressed. Distinguish package state errors from transaction errors and design retries at business boundaries that can be safely repeated.

## 9. Resetting package state

Normal package state persists across calls in a session. When state needs to be cleared, you can design a reset procedure in the package or use session management APIs at the application tier.

Example state reset procedure:

~~~sql
CREATE OR REPLACE PACKAGE request_context AS
    PROCEDURE set_context(
        p_user_id IN NUMBER,
        p_tenant_id IN NUMBER
    );
    PROCEDURE clear_context;
    FUNCTION current_user_id RETURN NUMBER;
END request_context;
/

CREATE OR REPLACE PACKAGE BODY request_context AS
    g_user_id NUMBER;
    g_tenant_id NUMBER;

    PROCEDURE set_context(
        p_user_id IN NUMBER,
        p_tenant_id IN NUMBER
    ) IS
    BEGIN
        g_user_id := p_user_id;
        g_tenant_id := p_tenant_id;
    END set_context;

    PROCEDURE clear_context IS
    BEGIN
        g_user_id := NULL;
        g_tenant_id := NULL;
    END clear_context;

    FUNCTION current_user_id RETURN NUMBER IS
    BEGIN
        RETURN g_user_id;
    END current_user_id;
END request_context;
/
~~~

Callers invoke CLEAR_CONTEXT in the cleanup path before returning the session to the pool. The reset procedure only needs to clear state owned by that package; it does not necessarily reset other packages in the session.

### DBMS_SESSION.MODIFY_PACKAGE_STATE

Oracle provides DBMS_SESSION.MODIFY_PACKAGE_STATE to change how session package state is managed:

- DBMS_SESSION.REINITIALIZE: package state is reinitialized when the package is referenced again according to the API mechanism.
- DBMS_SESSION.FREE_ALL_RESOURCES: frees package state resources; packages are reinitialized when needed again.

Conceptual example:

~~~sql
BEGIN
    DBMS_SESSION.MODIFY_PACKAGE_STATE(
        DBMS_SESSION.REINITIALIZE
    );
END;
/
~~~

This API affects package state in the session, so do not call it arbitrarily in the middle of a unit of work that depends on preserved state. Check the Oracle documentation for your exact version and connection pool conventions before applying it.

### DBMS_SESSION.RESET_PACKAGE

Some legacy systems may use DBMS_SESSION.RESET_PACKAGE to reset package state. For new code, evaluate DBMS_SESSION.MODIFY_PACKAGE_STATE and session reset APIs provided by the pool. Both affect session package state; do not view them as a replacement for COMMIT/ROLLBACK.

### Reset must cover all paths

If state is reset only when a request succeeds, an exception can leave stale data in the pooled session. Cleanup must run on both success and failure paths, and must execute before the session is handed out to another request.

## 10. SERIALLY_REUSABLE packages

Normally, package state persists in a session across multiple calls. With a package marked SERIALLY_REUSABLE, Oracle keeps state only for the duration of a single server call; when the server call ends, the package work area is released and can be reused. The next call creates/initializes fresh state.

Declare the pragma in both the package specification and package body:

~~~sql
CREATE OR REPLACE PACKAGE batch_helpers AS
    PRAGMA SERIALLY_REUSABLE;
    PROCEDURE increment;
    FUNCTION current_value RETURN PLS_INTEGER;
END batch_helpers;
/

CREATE OR REPLACE PACKAGE BODY batch_helpers AS
    PRAGMA SERIALLY_REUSABLE;

    g_count PLS_INTEGER := 0;

    PROCEDURE increment IS
    BEGIN
        g_count := g_count + 1;
    END increment;

    FUNCTION current_value RETURN PLS_INTEGER IS
    BEGIN
        RETURN g_count;
    END current_value;
END batch_helpers;
/
~~~

If a server call executes:

~~~sql
BEGIN
    batch_helpers.increment;
    batch_helpers.increment;
    DBMS_OUTPUT.PUT_LINE(batch_helpers.current_value);
END;
/
~~~

The value within that call is 2. A subsequent separate server call starts with fresh package state rather than continuing from 2.

### When to consider SERIALLY_REUSABLE?

- The package holds temporary data needed only within a single server call.
- The application has many concurrent sessions and long-lived package state puts pressure on session memory.
- There is no need to retain package variables between client calls.

Do not use this pragma if logic requires maintaining state across multiple client round-trips. For example, if the application calls procedure A in one call, then procedure B in the next call expecting B to see a package variable set by A; with SERIALLY_REUSABLE, that assumption no longer holds.

SERIALLY_REUSABLE changes lifetime semantics, not a harmless optimization option. Verify the Oracle version, how the application invokes the server, and any dependent packages before applying it.

## 11. Designing safe package state

### Keep mutable variables private if callers do not need direct access

Avoid exposing mutable variables just for callers to read/write directly:

~~~sql
CREATE OR REPLACE PACKAGE app_session AS
    g_current_user_id NUMBER;
END app_session;
/
~~~

Any caller with package access can change the value, making it hard to control who sets state and when it is reset. It is usually better to keep variables private in the body and provide an API:

~~~sql
CREATE OR REPLACE PACKAGE app_session AS
    PROCEDURE set_user(p_user_id IN NUMBER);
    FUNCTION current_user RETURN NUMBER;
    PROCEDURE clear_user;
END app_session;
/
~~~

An API lets you validate inputs, write logs, reset state, and change internal storage without forcing callers to depend on specific variables.

### Package state does not replace parameters

If a value is only used within a single call, passing it via parameters is usually clearer:

~~~sql
order_api.confirm_order(
    p_order_id => 1001,
    p_actor_id => 500
);
~~~

Implicit state makes procedures depend on call ordering and leftover session state. Parameters make dependencies visible directly in the program signature.

### Package initialization is not for configuration needing immediate updates

If the initialization section reads configuration from a table and stores it in a package variable, that value is a per-session snapshot. When a DBA updates the configuration table, already-initialized package state in other sessions does not automatically update. You need a refresh mechanism, TTL/cache invalidation, or direct table reads if changes must take effect immediately.

### Avoid circular initialization dependencies between packages

If package A's initialization calls B while B's initialization references A, initialization can create unpredictable dependencies and runtime errors. Keep initialization lightweight and avoid unnecessary cross-package calls; move coordination logic into explicitly invoked procedures after packages are ready.

## 12. Querying packages in the data dictionary

Oracle provides USER_ views to inspect packages belonging to the current schema.

### Status of PACKAGE and PACKAGE BODY

~~~sql
SELECT object_name,
       object_type,
       status,
       last_ddl_time
FROM user_objects
WHERE object_type IN ('PACKAGE', 'PACKAGE BODY')
ORDER BY object_name, object_type;
~~~

STATUS indicates whether the object is VALID or INVALID. The package specification and package body are two separate metadata objects.

### Viewing compilation errors

~~~sql
SELECT name,
       type,
       line,
       position,
       text
FROM user_errors
WHERE type IN ('PACKAGE', 'PACKAGE BODY')
ORDER BY name, type, sequence;
~~~

USER_ERRORS displays compilation errors/warnings for objects in the current schema. If a package is INVALID, inspect the errors before attempting to call it again.

### Viewing source

~~~sql
SELECT name,
       type,
       line,
       text
FROM user_source
WHERE name = 'REQUEST_COUNTER'
  AND type IN ('PACKAGE', 'PACKAGE BODY')
ORDER BY type, line;
~~~

### Viewing Dependencies

~~~sql
SELECT name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type,
       dependency_type
FROM user_dependencies
WHERE name = 'ORDER_API'
ORDER BY referenced_owner, referenced_name;
~~~

`USER_` views only show objects belonging to the current schema. Use `ALL_` views to inspect objects accessible to the user or `DBA_` views when holding administrative privileges. For packages in another schema, schema-qualify the name and ensure appropriate privileges.

### Recompiling Packages

You can recompile a package specification or body:

~~~sql
ALTER PACKAGE request_counter COMPILE;
ALTER PACKAGE request_counter COMPILE BODY;
~~~

Recompiling does not fix source code bugs; it instructs Oracle to recompile the object. If dependencies are still invalid or privileges are missing, the object may remain INVALID. After recompiling, check USER_OBJECTS and USER_ERRORS. Recompiling a package currently used by active sessions can affect package state in those sessions.

## 13. Handling Errors During Package Initialization

The initialization section runs implicitly when a package instance is created. If a statement in this section fails, the first call referencing the package may receive an exception instead of entering the procedure/function the caller expected.

Common causes:

- Configuration query returns no rows or multiple rows.
- Missing privileges on a table/view read by the package.
- Dependent object does not exist or is INVALID.
- Invalid configuration value causes type conversion/variable initialization to fail.
- Initialization calls another package that has errors or circular dependencies.

### Keep Initialization Simple

A well-designed initialization section typically:

- Sets package variables to clear default states.
- Loads a small, stable amount of configuration with a fallback rule when not found.
- Avoids unnecessary DML or side effects.
- Does not leave open transactions or COMMIT just to initialize the package.
- Does not perform long-running work that unexpectedly slows down the first request.

Example handling missing configuration:

~~~sql
CREATE OR REPLACE PACKAGE runtime_config AS
    FUNCTION tax_rate RETURN NUMBER;
END runtime_config;
/

CREATE OR REPLACE PACKAGE BODY runtime_config AS
    g_tax_rate NUMBER := 0.08;

    FUNCTION tax_rate RETURN NUMBER IS
    BEGIN
        RETURN g_tax_rate;
    END tax_rate;
BEGIN
    BEGIN
        SELECT config_number
        INTO g_tax_rate
        FROM application_config
        WHERE config_key = 'TAX_RATE';
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            NULL; -- Keep the declared default value.
    END;
END runtime_config;
/
~~~

This example still requires the package specification to be created first and needs a clear rule on the default value. Do not catch all errors with WHEN OTHERS and ignore them; privilege errors, duplicate data, or system errors must be reported and handled properly.

When calling `runtime_config.tax_rate`, the package initializes and loads the configuration; if no row is found, the default value 0.08 is retained.

### Initialization and Transactions

If the initialization section runs DML, those changes join the session's transaction unless the code uses an autonomous transaction or another mechanism. Package initialization does not create an independent transaction and does not commit on its own. This is another reason to avoid DML in initialization unless genuinely necessary.

### Initialization Is Not a Per-Call Constructor

Do not use the initialization section to run logic that must execute for every request or every procedure call. It runs when the package instance is initialized, not every time a public procedure is called. Repeatable logic should be placed in an explicit procedure/function.

## 14. Hands-On Practice: Private Package State and Initialization

Execute in a study schema with CREATE PROCEDURE privileges and sufficient quota. CREATE OR REPLACE statements are DDL and can implicitly commit an open transaction.

### Step 1: Create the Package Specification

~~~sql
CREATE OR REPLACE PACKAGE lab_session_state AS
    PROCEDURE increment;
    FUNCTION current_count RETURN PLS_INTEGER;
    FUNCTION initialized_at RETURN TIMESTAMP;
    PROCEDURE reset_count;
END lab_session_state;
/
~~~

The specification publishes only the API. Callers cannot directly see private variables.

### Step 2: Create the Package Body and Initialization Section

~~~sql
CREATE OR REPLACE PACKAGE BODY lab_session_state AS
    g_count PLS_INTEGER := 0;
    g_initialized_at TIMESTAMP;

    PROCEDURE increment IS
    BEGIN
        g_count := g_count + 1;
    END increment;

    FUNCTION current_count RETURN PLS_INTEGER IS
    BEGIN
        RETURN g_count;
    END current_count;

    FUNCTION initialized_at RETURN TIMESTAMP IS
    BEGIN
        RETURN g_initialized_at;
    END initialized_at;

    PROCEDURE reset_count IS
    BEGIN
        g_count := 0;
    END reset_count;

BEGIN
    g_initialized_at := SYSTIMESTAMP;
    DBMS_OUTPUT.PUT_LINE('lab_session_state initialized');
END lab_session_state;
/
~~~

Variables G_COUNT and G_INITIALIZED_AT are private because they are declared only in the body. The initialization section sets the timestamp and prints a message when the package instance is initialized.

### Step 3: Test Multiple Calls in the Same Session

~~~sql
SET SERVEROUTPUT ON;

BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Initial count = ' || lab_session_state.current_count
    );

    lab_session_state.increment;
    lab_session_state.increment;

    DBMS_OUTPUT.PUT_LINE(
        'Current count = ' || lab_session_state.current_count
    );

    DBMS_OUTPUT.PUT_LINE(
        'Initialized at = ' ||
        TO_CHAR(lab_session_state.initialized_at, 'YYYY-MM-DD HH24:MI:SS.FF')
    );
END;
/
~~~

The initialized message appears on the first reference in the session. The initial count is 0, and after two increments it becomes 2.

Run the block again in the same session. The initialization section does not run again; count retains 2 before the block increments it further.

### Step 4: Test a Second Session

Open another database session and run:

~~~sql
SET SERVEROUTPUT ON;

BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Session B count = ' || lab_session_state.current_count
    );
    lab_session_state.increment;
    DBMS_OUTPUT.PUT_LINE(
        'Session B count = ' || lab_session_state.current_count
    );
END;
/
~~~

Session B sees its own initialization message and its count starts at 0, even though Session A incremented count to 2 or higher. This proves package state is maintained per session.

### Step 5: Reset a Package Variable

In Session A:

~~~sql
BEGIN
    lab_session_state.reset_count;
    DBMS_OUTPUT.PUT_LINE(lab_session_state.current_count);
END;
/
~~~

Count returns to 0, while the initialized_at timestamp remains unchanged because reset_count only resets g_count. Resetting one package variable does not mean reinitializing the entire package instance.

### Step 6: Inspect Metadata

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name = 'LAB_SESSION_STATE'
ORDER BY object_type;

SELECT name, type, line, text
FROM user_errors
WHERE name = 'LAB_SESSION_STATE'
ORDER BY type, sequence;
~~~

Both PACKAGE and PACKAGE BODY objects should be VALID; USER_ERRORS should show no compilation errors.

### Step 7: Clean Up the Package

~~~sql
DROP PACKAGE lab_session_state;
~~~

DROP PACKAGE deletes both the package specification and body. Run this only after completing the lab and no longer needing the object. DDL performs an implicit commit.

## 15. Common Errors and How to Handle Them

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| Caller cannot call helper | Helper exists only in package body | Publish a public API if callers genuinely need the functionality. |
| Package body fails to compile | Missing implementation for public subprogram or mismatched signature | Compare package spec/body and USER_ERRORS. |
| Initialization message appears on first call | Package instance was just initialized in the session | This is normal behavior; do not expect it to run on every call. |
| Different session sees different package values | Package state is per session | Use a table/shared context if cross-session data sharing is needed. |
| Subsequent request sees previous request's user/tenant | Connection pool reused a session with stale package state | Set/reset state on every request and clean up before returning connection. |
| Package state lost after deployment | Recompilation/invalidation discarded state | Do not use package state as a persistent cache; handle invalidation errors and reinitialize. |
| ORA-04068 after package change | Existing package state was discarded | Handle at the application tier, retrying only when the request is safe/idempotent. |
| Slow first request | Initialization section runs heavy queries or work | Reduce initialization logic, load data selectively, or lazy-load when needed. |
| Package fails to compile due to dependency | Dependent object is INVALID or privileges are missing | Check USER_ERRORS, USER_DEPENDENCIES, and grants. |
| State lost between two server calls with SERIALLY_REUSABLE | Package state only persists within a server call | Do not use the pragma if state must survive across round-trips. |
| COMMIT does not reset package variables | Transactions and package state have separate lifecycles | Call a reset API/procedure or end the session per design. |

## 16. Self-Check Questions

1. **What are the main parts of a package?** Package specification and package body.
2. **What is the specification used for?** Publishing the package's public interface.
3. **Where are private members declared?** Inside the package body, without appearing in the specification.
4. **Can a caller call a private procedure?** No; callers can only call published members with appropriate privileges.
5. **Is a package body always required?** Not always; a package with only declarations requiring no implementation may have no body.
6. **What is package state?** The runtime state of a package instance within a database session.
7. **Is package state shared across sessions?** No; each session has its own state.
8. **When is a package initialized?** When the session first references the package instance.
9. **When does the initialization section run?** Once when the package instance is initialized in a session.
10. **Where is the initialization section located?** At the end of the package body, after declarations and subprograms.
11. **Does CREATE PACKAGE run initialization for all sessions?** No; it creates/compiles the object, and initialization runs when each session references the package.
12. **Does COMMIT clear package state?** No; transactions and package state are independent.
13. **Why can a connection pool cause package state leakage between requests?** Multiple requests can reuse the same session.
14. **How do you reset package state for a request?** Call a reset procedure or session reset API in the cleanup path before returning the connection to the pool.
15. **What is ORA-04068 typically related to?** Package state being discarded, usually after invalidation/recompilation.
16. **What does SERIALLY_REUSABLE change?** Package state persists only for a single server call rather than across multiple calls in a session.
17. **When should variables be kept private?** When callers do not need direct read/write access and state is an implementation detail.
18. **Why should the initialization section be lightweight?** Because it runs implicitly on first reference and can make the first request slow or fail.

The package specification defines the public interface; the package body holds the implementation and private state. A package instance is initialized when a session first references the package, and retains state across calls in that session. The initialization section runs once for that instance. Because connection pools reuse sessions, applications must manage state per request and reset it before returning connections. Recompilation can invalidate package state; SERIALLY_REUSABLE shortens state lifetime to a single server call and is only appropriate when logic does not need to preserve state between calls.
