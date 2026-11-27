# ORA-04063, ORA-06508, ORA-04068, and PL/SQL Object / Package State Errors

Oracle Database stores procedures, functions, packages, triggers, views, and other PL/SQL components as stored program units. Before running, these objects must compile cleanly and remain in a valid state. When source code references nonexistent objects, lacks privileges, mismatches signatures, or contains syntax errors, Oracle marks the object `INVALID`. Invoking an invalid or unloadable object leads to errors such as ORA-04063 and ORA-06508.

A separate class of errors involves per-session package state. A package can hold global variables, cursors, and state in session memory. When a package is recompiled or invalidated, state already initialized in existing sessions is discarded. The next call from a session that had initialized the package can raise ORA-04068.

Three errors to distinguish:

- **ORA-04063**: the referenced object has errors, such as a package body or view with compilation errors. Locate the underlying error in `USER_ERRORS`/`ALL_ERRORS` and dependencies.
- **ORA-06508**: PL/SQL could not find an executable program unit at call time. The object may not exist, may be invalid, cannot be loaded, or its dependencies have errors.
- **ORA-04068**: existing package state in the session has been discarded. This is typically an invalidation/recompilation event on a stateful package; it does not mean the package itself is currently `INVALID`.

Proper investigation examines object status in the data dictionary, compile errors, dependencies, privileges, and which sessions have initialized the package. Simply running `COMPILE` and declaring victory misses broken dependencies or pooled sessions holding stale state.

## 1. Package Specification, Package Body, and Object Status

A package groups related procedures, functions, types, cursors, exceptions, constants, and shared variables. A package typically has two parts:

- **Package specification (spec)** declares the public interface: callable procedures/functions, data types, constants, types, and public variables.
- **Package body** holds implementations of procedures/functions, private variables, cursors, helper subprograms, and an optional initialization block.

Example:

~~~sql
CREATE OR REPLACE PACKAGE app.order_api AS
  PROCEDURE mark_paid(
    p_order_id IN NUMBER,
    p_status   OUT VARCHAR2
  );

  FUNCTION get_total(
    p_order_id IN NUMBER
  ) RETURN NUMBER;
END order_api;
/
~~~

Package body:

~~~sql
CREATE OR REPLACE PACKAGE BODY app.order_api AS

  g_call_count NUMBER := 0;

  PROCEDURE mark_paid(
    p_order_id IN NUMBER,
    p_status   OUT VARCHAR2
  ) AS
  BEGIN
    UPDATE app.orders
    SET    status = 'PAID'
    WHERE  order_id = p_order_id;

    IF SQL%ROWCOUNT = 1 THEN
      p_status := 'UPDATED';
    ELSE
      p_status := 'NOT_FOUND';
    END IF;

    g_call_count := g_call_count + 1;
  END mark_paid;

  FUNCTION get_total(
    p_order_id IN NUMBER
  ) RETURN NUMBER AS
    l_total NUMBER;
  BEGIN
    SELECT total_amount
    INTO   l_total
    FROM   app.orders
    WHERE  order_id = p_order_id;

    RETURN l_total;
  END get_total;

BEGIN
  -- Initialization block executes when the package is instantiated in a session.
  g_call_count := 0;
END order_api;
/
~~~

Spec and body are two distinct objects in the data dictionary. A package can have a `VALID` spec while its body is `INVALID`. Clients can see the public declarations yet fail when executing any procedure/function because the implementation is invalid.

Common object types:

| Object Type | Meaning |
|---|---|
| `PACKAGE` | Package specification |
| `PACKAGE BODY` | Package implementation |
| `PROCEDURE` | Standalone stored procedure |
| `FUNCTION` | Standalone stored function |
| `TRIGGER` | Trigger |
| `VIEW` | View |
| `TYPE` / `TYPE BODY` | SQL object type and type method implementation |

Common statuses:

- **VALID**: object compiled successfully against current dependencies.
- **INVALID**: object needs recompilation or cannot compile cleanly.
- **N/A** or other statuses: depends on object type and Oracle internal handling.

An `INVALID` object does not always mean bad syntax. Causes include dropped/altered dependencies, revoked grants, changed types, misdirected synonyms, or recreated objects with altered signatures.

## 2. ORA-04063: Package or Object Has Errors

ORA-04063 occurs when Oracle attempts to use an object containing compilation errors. For packages, the error message usually specifies whether the package body or package has errors. Example:

~~~text
ORA-04063: package body "APP.ORDER_API" has errors
ORA-06508: PL/SQL: could not find program unit being called: "APP.ORDER_API"
ORA-06512: at line ...
~~~

ORA-04063 signals that the object cannot be used as expected. Inspect exact compiler errors—usually `PLS-xxxx` or `ORA-xxxx`—in `USER_ERRORS`/`ALL_ERRORS`. The first error in the list can cascade into subsequent errors; read all messages in line/position order.

### 2.1. Valid Package Spec with Invalid Body

For example, the spec declares a procedure:

~~~sql
CREATE OR REPLACE PACKAGE app.inventory_api AS
  PROCEDURE reserve_stock(
    p_product_id IN NUMBER,
    p_quantity   IN NUMBER
  );
END inventory_api;
/
~~~

Yet the body references a nonexistent table or column:

~~~sql
CREATE OR REPLACE PACKAGE BODY app.inventory_api AS
  PROCEDURE reserve_stock(
    p_product_id IN NUMBER,
    p_quantity   IN NUMBER
  ) AS
  BEGIN
    UPDATE app.product_stock
    SET    reserved_qty = reserved_qty + p_quantity
    WHERE  product_id = p_product_id;
  END reserve_stock;
END inventory_api;
/
~~~

If `PRODUCT_STOCK` does not exist, `RESERVED_QTY` does not exist, or schema `APP` lacks required privileges, the body becomes `INVALID`. The spec stays `VALID` because the public declaration does not depend on that implementation detail.

When the application calls `APP.INVENTORY_API.RESERVE_STOCK`, Oracle must load the package body. Because the body has errors, the call fails with ORA-04063 and/or ORA-06508 in the stack.

### 2.2. Common Causes

- PL/SQL syntax errors in the package spec or body.
- Procedure/function body mismatches spec declaration: wrong name, parameter count, `IN`/`OUT` mode, type, or return type.
- Referenced table, view, sequence, synonym, or type was dropped or renamed.
- Column or data type on a dependent object changed.
- Another called package or function is `INVALID`.
- Package owner lacks privileges on a referenced object.
- Privileges were granted only via a role, whereas definer-rights stored PL/SQL requires direct grants to compile and run.
- Synonym points to the wrong owner or nonexistent object.
- A SQL object type changed, invalidating dependent packages.
- An incomplete migration created objects partially or out of order.

Never edit the package before verifying dependencies. If the root cause is a missing table column or revoked grant, recompiling the package alone will not fix the dependency.

## 3. ORA-06508: Could Not Find Program Unit Being Called

ORA-06508 is a runtime error: PL/SQL cannot locate or load the called program unit. A program unit can be a package procedure/function, standalone procedure, or other PL/SQL unit.

Example where Package A calls Package B:

~~~sql
CREATE OR REPLACE PACKAGE app.order_api AS
  PROCEDURE create_order(p_order_id OUT NUMBER);
END order_api;
/

CREATE OR REPLACE PACKAGE BODY app.order_api AS
  PROCEDURE create_order(p_order_id OUT NUMBER) AS
  BEGIN
    app.sequence_api.next_order_id(p_order_id);
  END create_order;
END order_api;
/
~~~

If `SEQUENCE_API` is dropped, invalid, or inaccessible, calling `CREATE_ORDER` fails when Oracle resolves the dependency.

### 3.1. Distinguishing Compile Errors from Runtime Errors

| Scenario | Typical Symptoms | Action Required |
|---|---|---|
| Package body has compile errors | ORA-04063, `PLS-xxxx` in `USER_ERRORS` | Read compile errors and fix source/dependencies |
| Caller references unloadable program unit | ORA-06508 | Check object existence, status, dependencies, edition, and grants |
| Package state invalidated | ORA-04068, possibly with ORA-04061/04065 | Understand session state and handle interrupted call |
| Missing `EXECUTE` privilege | ORA-01031 or matching PL/SQL/SQL error | Check grants, owner, and direct privileges |
| Object missing or misspelled | ORA-06550/`PLS-00201` or resolution error | Check schema, synonyms, and identifiers |

When an `INVALID` object is invoked, Oracle may attempt automatic recompilation. If compilation succeeds, the call proceeds; if compilation fails or the object cannot be loaded, an error is returned. Do not rely on auto-recompilation in place of controlled deployments, as the first application call pays compilation cost or fails.

### 3.2. Checking Procedure/Function Signatures

If the spec changed while a caller or synonym still uses an old signature, inspect public definitions:

~~~sql
SELECT owner,
       package_name,
       object_name,
       argument_name,
       position,
       sequence,
       data_type,
       in_out,
       overload
FROM all_arguments
WHERE owner = 'APP'
  AND package_name = 'ORDER_API'
ORDER BY object_name, overload, sequence;
~~~

For standalone procedures/functions, `PACKAGE_NAME` is `NULL`. `ALL_ARGUMENTS` shows published dictionary signatures; inspect package spec source when checking custom types, default parameters, and full declarations.

### 3.3. Checking Object Existence and Edition

~~~sql
SELECT owner,
       object_name,
       object_type,
       status,
       edition_name
FROM all_objects
WHERE owner = 'APP'
  AND object_name IN ('ORDER_API', 'SEQUENCE_API')
ORDER BY object_name, object_type;
~~~

`EDITION_NAME` exists only in configurations/releases supporting Edition-Based Redefinition; omit that column if unavailable in your version. In edition-enabled databases, verify both the session's current edition and the object edition visible to the application.

## 4. ORA-04068: Existing State of Packages Has Been Discarded

PL/SQL packages can hold global variables, constants, cursors, and other state persisted in each session's memory. The first time a session invokes a package, Oracle instantiates package state for that session. Subsequent calls in the same session reuse that state.

Example:

~~~sql
CREATE OR REPLACE PACKAGE app.session_counter AS
  PROCEDURE increment;
  FUNCTION current_value RETURN NUMBER;
END session_counter;
/

CREATE OR REPLACE PACKAGE BODY app.session_counter AS
  g_counter NUMBER := 0;

  PROCEDURE increment AS
  BEGIN
    g_counter := g_counter + 1;
  END increment;

  FUNCTION current_value RETURN NUMBER AS
  BEGIN
    RETURN g_counter;
  END current_value;
END session_counter;
/
~~~

In each separate database session, `g_counter` starts at `0` when the package is instantiated. If Session A calls `increment` three times, Session A sees `3`; Session B has its own state and does not see Session A's value of `3`.

Packages holding state like this are called **stateful packages**.

### 4.1. What Invalidates Package State?

Package state is discarded when the package is recompiled or invalidated, such as when:

- A DBA runs `ALTER PACKAGE ... COMPILE` or `CREATE OR REPLACE PACKAGE BODY`.
- The package specification is modified.
- A dependent object invalidates the package.
- A referenced type or dependency changes.
- Certain deployments, upgrades, or edition switches require sessions to reload objects.

Once a stateful package is invalidated, sessions that had already instantiated it can no longer retain their old state. On the next call to the package, Oracle reports:

~~~text
ORA-04068: existing state of packages has been discarded
ORA-04061: existing state of package body "APP.SESSION_COUNTER" has been invalidated
ORA-04065: not executed, altered or dropped package body "APP.SESSION_COUNTER"
ORA-06508: PL/SQL: could not find program unit being called: "APP.SESSION_COUNTER"
~~~

Accompanying errors and stack ordering vary by scenario and release. ORA-04068 is the key signal that the session's package state was discarded.

### 4.2. ORA-04068 Does Not Necessarily Mean the Package Is Still INVALID

This is critical when investigating production incidents.

Suppose a DBA recompiled a package body cleanly. In the data dictionary, `PACKAGE BODY` is `VALID`. Yet a pooled session that instantiated the package before the recompile still holds stale state. When that session calls the package next, Oracle detects the invalidated state and raises ORA-04068.

Therefore:

- The package itself may currently be `VALID`.
- Existing sessions still hit ORA-04068 on their next call.
- Once state is discarded, subsequent calls re-instantiate fresh package state and succeed if the package and dependencies are valid.
- Different sessions hit the error at different times depending on which sessions instantiated the package and when they next invoke it.

Checking only `DBA_OBJECTS` after an incident may show the package as `VALID` and mislead you into thinking nothing is wrong. Correlate deployment timestamps, connection pools, and client error logs.

### 4.3. How Package Initialization Re-Runs

When a package is instantiated for the first time in a session, Oracle initializes package variables and runs the initialization block at the end of the package body. After state is discarded, the next instantiation re-runs initialization and resets package variables to initial values.

This means:

- In-package counters or caches lose their values.
- Open package cursors are closed/discarded.
- Package variables no longer retain temporary values from prior calls.
- Initialization logic runs again.
- If initialization has side effects, design carefully because it may run multiple times over a session's lifetime.

Never use package variables to store durable business state or data expected to survive deployments. Store critical state in tables with proper transactions and locking.

## 5. Stateful vs. Stateless Packages

### Stateful Packages

Packages with variables or cursors that mutate within a session maintain package state. Example:

~~~sql
CREATE OR REPLACE PACKAGE app.request_context AS
  PROCEDURE set_user(p_user_id NUMBER);
  FUNCTION get_user RETURN NUMBER;
END request_context;
/

CREATE OR REPLACE PACKAGE BODY app.request_context AS
  g_user_id NUMBER;

  PROCEDURE set_user(p_user_id NUMBER) AS
  BEGIN
    g_user_id := p_user_id;
  END set_user;

  FUNCTION get_user RETURN NUMBER AS
  BEGIN
    RETURN g_user_id;
  END get_user;
END request_context;
/
~~~

This state can help within a single session, yet demands strict session hygiene. If a connection pool reuses the physical session for another request, package variables retain values from the previous request unless explicitly reset.

### Stateless Packages

Packages without mutable state across calls are far easier to operate. Instead of storing user IDs in global variables, pass the user ID as a parameter:

~~~sql
CREATE OR REPLACE PACKAGE app.request_api AS
  PROCEDURE get_orders(
    p_user_id IN NUMBER,
    p_result  OUT SYS_REFCURSOR
  );
END request_api;
/
~~~

Each call receives explicit inputs, eliminating dependence on session history and preventing data from leaking between pooled requests.

Packages can still contain constants or strictly local/internal declarations; what matters is that logic does not rely on mutable state across calls.

### SERIALLY_REUSABLE Packages

Oracle supports the `SERIALLY_REUSABLE` pragma for appropriate packages. A serially reusable package retains state only for the duration of a single server call rather than the entire session; state is reclaimed when the call ends and reinitialized on the next call.

Example:

~~~sql
CREATE OR REPLACE PACKAGE app.temp_work AS
  PRAGMA SERIALLY_REUSABLE;

  PROCEDURE process_one(p_id NUMBER);
END temp_work;
/

CREATE OR REPLACE PACKAGE BODY app.temp_work AS
  PRAGMA SERIALLY_REUSABLE;

  g_counter PLS_INTEGER := 0;

  PROCEDURE process_one(p_id NUMBER) AS
  BEGIN
    g_counter := g_counter + 1;
    -- Process a single call.
  END process_one;
END temp_work;
/
~~~

The pragma must appear in both the package specification and body per Oracle rules. Not all packages qualify; state cannot persist across server calls, and restrictions apply when calling from SQL or combining with certain package features. Check release documentation before using it.

`SERIALLY_REUSABLE` is not a universal fix for ORA-04068 across all applications. It changes state lifecycle semantics and requires auditing existing callers.

## 6. Diagnosing Object Status via the Data Dictionary

Start by checking object statuses.

### 6.1. Check PACKAGE and PACKAGE BODY

For the current schema:

~~~sql
SELECT object_name,
       object_type,
       status,
       last_ddl_time
FROM user_objects
WHERE object_type IN ('PACKAGE', 'PACKAGE BODY')
ORDER BY object_name, object_type;
~~~

For owner `APP`:

~~~sql
SELECT owner,
       object_name,
       object_type,
       status,
       last_ddl_time
FROM all_objects
WHERE owner = 'APP'
  AND object_type IN ('PACKAGE', 'PACKAGE BODY')
ORDER BY object_name, object_type;
~~~

DBAs can use `DBA_OBJECTS` for full visibility. `LAST_DDL_TIME` helps correlate when objects changed with deployments or incidents. It does not capture every runtime event; combine it with audit and deployment logs.

### 6.2. Read Compile Errors in USER_ERRORS/ALL_ERRORS

Current schema:

~~~sql
SELECT name,
       type,
       line,
       position,
       attribute,
       message_number,
       text
FROM user_errors
WHERE name = 'ORDER_API'
ORDER BY type, sequence;
~~~

Another owner:

~~~sql
SELECT owner,
       name,
       type,
       line,
       position,
       attribute,
       message_number,
       text
FROM all_errors
WHERE owner = 'APP'
  AND name = 'ORDER_API'
ORDER BY type, sequence;
~~~

Key columns:

- `NAME`: object name.
- `TYPE`: `PACKAGE`, `PACKAGE BODY`, `PROCEDURE`, `FUNCTION`, etc.
- `LINE`/`POSITION`: error location in source.
- `ATTRIBUTE`: `ERROR` or `WARNING`.
- `TEXT`: compiler error message.
- `SEQUENCE`: message order within the object.

If `USER_ERRORS`/`ALL_ERRORS` returns no rows yet the object stays `INVALID`, verify exact owner, edition, dictionary visibility, and object type. `DBA_ERRORS` can be queried with proper privileges.

### 6.3. Check Dependencies

A package can depend on tables, views, sequences, types, synonyms, or other packages. Check dependencies:

~~~sql
SELECT owner,
       name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type,
       dependency_type
FROM all_dependencies
WHERE owner = 'APP'
  AND name = 'ORDER_API'
ORDER BY referenced_owner, referenced_name;
~~~

Check reverse dependencies—which objects depend on the package:

~~~sql
SELECT owner,
       name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM all_dependencies
WHERE referenced_owner = 'APP'
  AND referenced_name = 'ORDER_API'
ORDER BY owner, type, name;
~~~

`ALL_DEPENDENCIES` reflects dependencies tracked statically by Oracle. Dynamic SQL, concatenated object names, and certain runtime dependencies are not captured in the dictionary. When a package uses `EXECUTE IMMEDIATE`, inspect the source code and trace dynamically constructed object names.

### 6.4. Inspect Source Code

Use `USER_SOURCE` or `ALL_SOURCE`:

~~~sql
SELECT line,
       text
FROM all_source
WHERE owner = 'APP'
  AND name = 'ORDER_API'
  AND type = 'PACKAGE BODY'
ORDER BY line;
~~~

Read both `PACKAGE` spec and `PACKAGE BODY` to inspect public declarations, global variables, initialization blocks, and dependency calls. If source is wrapped, it cannot be read directly; consult the original artifacts in source control.

## 7. Finding the Root Error and Recompilation Order

When multiple objects are `INVALID`, do not recompile packages randomly. Trace dependencies and fix from the root object outward.

Example dependency chain:

~~~text
APP.ORDER_API
      |
      +----> APP.CUSTOMER_API
      |             |
      |             +----> APP.CUSTOMERS (table/view)
      |
      +----> APP.ORDER_TYPES (SQL type)
      |
      +----> APP.PRICING_API
~~~

If `CUSTOMER_API` fails due to a missing column in `CUSTOMERS`, fix the schema or migration first. Then compile `CUSTOMER_API`, and then `ORDER_API` if it remains `INVALID`.

### 7.1. Compiling Package Spec and Body

Compile the entire package:

~~~sql
ALTER PACKAGE app.order_api COMPILE;
~~~

Compile spec only:

~~~sql
ALTER PACKAGE app.order_api COMPILE SPECIFICATION;
~~~

Compile body only:

~~~sql
ALTER PACKAGE app.order_api COMPILE BODY;
~~~

Use `COMPILE SPECIFICATION` when public declarations need recompiling; use `COMPILE BODY` when only implementation needs compiling and the spec is unchanged. When unsure, check status and source before choosing. Compiling the spec affects dependent callers far more broadly than compiling only the body.

After compiling, verify again:

~~~sql
SELECT object_name,
       object_type,
       status
FROM user_objects
WHERE object_name = 'ORDER_API'
ORDER BY object_type;
~~~

And:

~~~sql
SELECT type,
       line,
       position,
       text
FROM user_errors
WHERE name = 'ORDER_API'
ORDER BY type, sequence;
~~~

### 7.2. SQL*Plus SHOW ERRORS

In SQL*Plus or SQLcl:

~~~sql
ALTER PACKAGE app.order_api COMPILE BODY;
SHOW ERRORS PACKAGE BODY app.order_api;
~~~

Or:

~~~sql
SHOW ERRORS PACKAGE app.order_api;
~~~

`SHOW ERRORS` is a client command, not a SQL statement sent over JDBC. In SQL Developer, check the Errors tab or query `USER_ERRORS`/`ALL_ERRORS`.

### 7.3. Compiling an Entire Schema

When many objects are `INVALID` after migration/upgrade, you can use `DBMS_UTILITY.COMPILE_SCHEMA`:

~~~sql
BEGIN
  DBMS_UTILITY.COMPILE_SCHEMA(
    schema         => 'APP',
    compile_all    => FALSE,
    reuse_settings => TRUE
  );
END;
/
~~~

`COMPILE_SCHEMA` requires appropriate privileges and attempts to compile objects in the schema. If root dependencies still have errors, dependent objects will remain `INVALID`. Afterward, re-query `USER_OBJECTS`/`DBA_OBJECTS` and `*_ERRORS`; never assume success simply because the procedure completed without throwing an exception.

### 7.4. Recompiling After Upgrade or Patch

Oracle provides the `utlrp.sql` script to recompile `INVALID` objects after upgrades or patches. It resides in the Oracle Home `rdbms/admin` directory and runs per Oracle instructions with `SYSDBA` privileges in the appropriate environment.

Never run `utlrp.sql` casually in production just because one package has an error. It is intended for post-upgrade/patch workflows following release guidance, database state checks, and maintenance windows.

## 8. Privileges and Synonyms Causing Compile Errors

A subtle issue arises when the package owner holds privileges via a role rather than direct grants on referenced objects.

Stored PL/SQL runs with definer rights or invoker rights depending on `AUTHID`. In definer-rights units (the default), roles are disabled at execution; privileges on referenced objects must be granted directly to the owner per Oracle rules.

Example:

~~~sql
GRANT SELECT ON data_owner.customers TO app;
GRANT EXECUTE ON common_owner.customer_types TO app;
~~~

If `APP.ORDER_API` accesses `DATA_OWNER.CUSTOMERS`, verify direct grants to `APP`, not just roles granted to a logged-in user.

Check granted object privileges:

~~~sql
SELECT owner,
       table_name,
       grantee,
       privilege,
       grantable
FROM all_tab_privs
WHERE grantee = 'APP'
ORDER BY owner, table_name, privilege;
~~~

For `EXECUTE` privileges on packages/types, inspect `ALL_TAB_PRIVS` or `DBA_TAB_PRIVS` depending on object and visibility.

### Synonyms

Synonyms are only aliases for objects; they grant no privileges and do not guarantee the target exists.

Check synonyms:

~~~sql
SELECT owner,
       synonym_name,
       table_owner,
       table_name,
       db_link
FROM all_synonyms
WHERE synonym_name IN ('CUSTOMERS', 'ORDER_API')
ORDER BY owner;
~~~

If a synonym points to the wrong owner/object, fix the synonym or qualify the schema explicitly. For critical packages, explicit owner qualification in source code reduces dependence on `CURRENT_SCHEMA` and synonym resolution.

## 9. Package State and Connection Pools

Java applications typically use connection pools such as HikariCP, UCP, or application server pools. A connection borrowed for a request may reuse a physical database session previously used by an earlier request.

When packages hold global state, a request can see leftover state from a prior request after the connection returned to the pool. This causes two problems:

1. Stateful data leaks across requests/users unless reset.
2. When a package is recompiled, pooled sessions encounter ORA-04068 intermittently on their next calls.

### 9.1. Why Errors Appear Sporadically After Deployment

Suppose a pool holds 20 physical sessions. Only 12 sessions invoked `ORDER_API` before the DBA recompiled the body. After deployment:

- Sessions that previously instantiated the package hold stale state and hit ORA-04068 on their next call.
- Sessions that never instantiated it instantiate the fresh version cleanly without stale-state errors.
- A session only fails when a later request actually invokes that specific package.
- Errors trickle in over several minutes or longer depending on traffic and pool dispatch order.

Therefore, errors do not necessarily appear immediately upon migration completion and do not affect every request.

### 9.2. Managing Package State in Pools

Guidelines:

- Prefer stateless packages: pass data via parameters rather than storing business state in global variables.
- If stateful packages are required, define clear lifecycles and reset state at request/transaction boundaries.
- Never assume closing a connection clears package state; in pools, `close()` merely returns the physical session to the pool.
- After deployments altering stateful packages, consider draining/recycling pools per operational procedures to prevent scattered errors.
- To reset package state in the current session, `DBMS_SESSION.RESET_PACKAGE` frees session package state; it does not fix `INVALID` objects and must run at safe session boundaries.
- Never kill sessions or restart the entire database solely for ORA-04068 when pool/session recycling handles it cleanly.

Example resetting package state in the current session:

~~~sql
BEGIN
  DBMS_SESSION.RESET_PACKAGE;
END;
/
~~~

This affects only the current session's package state, not all sessions in the database. It does not compile packages or repair broken dependencies.

### 9.3. Draining and Recycling Pools

When a release changes stateful package spec/body behavior, drain traffic, let active requests finish, and recycle application pools to open fresh sessions. Implementation depends on the platform:

- With HikariCP, manage DataSource/pool lifecycle via application rollout/refresh mechanisms.
- With UCP, use supported pool management APIs to drain/refresh connections.
- With application servers, use platform-supported redeploys or pool resets.

Never arbitrarily kill active database sessions using the package during peak traffic. Sessions with active transactions will roll back and fail user requests. Coordinate deployment windows and inspect active transactions first.

## 10. Handling ORA-04068 in Applications

ORA-04068 reports that stale package state was discarded. The current call fails; subsequent calls in that session can re-instantiate fresh package state if the object is valid.

Applications must decide whether to retry based on idempotency and transaction semantics.

### 10.1. Never Retry Blindly

Example procedure that both debits a balance and logs a transaction:

~~~sql
PROCEDURE debit_account(
  p_account_id IN NUMBER,
  p_amount     IN NUMBER
) AS
BEGIN
  UPDATE accounts
  SET    balance = balance - p_amount
  WHERE  account_id = p_account_id;

  INSERT INTO account_transactions(
    account_id, amount, transaction_type
  )
  VALUES (
    p_account_id, p_amount, 'DEBIT'
  );
END;
~~~

Before retrying automatically after an error, understand how far the transaction rolled back and whether external side effects occurred. In standard Oracle transactions, a statement error rolls back that statement while the caller's prior transaction statements may remain open; autonomous transactions or external calls may also have persisted.

Never commit immediately just to "clear the error." The caller owning the transaction must decide whether to roll back or proceed per the business contract.

### 10.2. Safe Retry Strategy

- Check vendor error code `4068` to recognize state-discard errors.
- Ensure the failed call finishes and handle the transaction per application rules.
- If the unit of work is safely retryable, retry after state re-instantiation or on a fresh session per pool policy.
- Use idempotency keys / unique business keys to prevent duplicate business execution.
- Cap maximum retry attempts; never loop infinitely.
- Log correlation ID, package name, database/session context, and release version.
- If the retry returns ORA-04063/06508, stop retrying and fix the package/dependencies; the issue is no longer just stale package state.

Illustrative Java snippet catching the Oracle vendor code:

~~~java
try {
    callOrderPackage(connection, orderId);
} catch (SQLException e) {
    if (e.getErrorCode() == 4068) {
        // Handle transaction per unit-of-work rules.
        // Retry only if the operation is idempotent and permitted.
        throw e;
    }
    throw e;
}
~~~

This snippet detects the error only; it is not a complete retry implementation. In Spring transactions, an exception may mark the transaction rollback-only; do not retry inside a transaction already marked rollback-only. Place retry orchestration outside the failed transaction so each retry starts a fresh transaction.

### 10.3. Transaction Boundaries in Spring

One pattern places retry logic outside the transactional method so each attempt runs in its own transaction. Use a separate bean/proxy or properly ordered retry/transaction advice; self-invocation inside the same bean will not start a new transaction.

Never wrap calls with external side effects in automatic retries without idempotency. For payments, emails, or REST API calls, use proper idempotency or outbox mechanisms.

## 11. Fixing Invalid Packages and Verifying After Compilation

Follow this sequence when resolving broken packages:

1. Capture the complete error stack from client and Oracle.
2. Identify object name, owner, type, and edition.
3. Check `USER_OBJECTS`/`ALL_OBJECTS`/`DBA_OBJECTS`.
4. Read `USER_ERRORS`/`ALL_ERRORS`/`DBA_ERRORS` ordered by `sequence`.
5. Inspect spec/body source and dependencies.
6. Verify referenced objects, synonyms, grants, and signatures.
7. Fix the root cause in source, migrations, or privileges.
8. Compile dependent objects in dependency order.
9. Re-check statuses and error views.
10. Test invoking the package in a fresh session.
11. Assess older pooled sessions if the package is stateful.
12. Monitor for ORA-04068/04063/06508 post-deployment.

Example compilation and verification:

~~~sql
ALTER PACKAGE app.order_api COMPILE BODY;

SELECT object_name,
       object_type,
       status
FROM all_objects
WHERE owner = 'APP'
  AND object_name = 'ORDER_API'
ORDER BY object_type;

SELECT owner,
       name,
       type,
       line,
       position,
       text
FROM all_errors
WHERE owner = 'APP'
  AND name = 'ORDER_API'
ORDER BY type, sequence;
~~~

Consider the fix complete only when both `PACKAGE` and `PACKAGE BODY` are `VALID`, zero compile errors remain, and a test call succeeds. If an object stays `INVALID`, never mask the error with broad grants or ad-hoc synonyms before understanding dependencies.

## 12. Inspecting Runtime Sessions and Package State

When errors occur only on certain connections, identify which sessions use the package. DBAs can inspect sessions:

~~~sql
SELECT sid,
       serial#,
       username,
       status,
       machine,
       program,
       module,
       action,
       logon_time
FROM v$session
WHERE username = 'APP'
ORDER BY logon_time;
~~~

In RAC, use `GV$SESSION` across instances:

~~~sql
SELECT inst_id,
       sid,
       serial#,
       username,
       status,
       machine,
       program,
       module,
       action,
       logon_time
FROM gv$session
WHERE username = 'APP'
ORDER BY inst_id, logon_time;
~~~

Inspect active SQL, wait events, and transactions with DBA privileges. Not every session will be calling the package at the exact moment of your query; sessions retain state in UGA/PGA after calls finish.

Oracle exposes certain views on package/session state depending on release and setup. Consult official dynamic performance view documentation for your release; avoid relying on undocumented internal columns.

For connection pools, log connection/session identifiers in application logs whenever possible. This correlates ORA-04068 failures with `SID`/`SERIAL#`, service, module, instance, and recompilation timestamps.

## 13. Package Spec Changes vs. Body Changes

Spec changes and body changes carry different blast radii.

### Body Changes

Modifying only internal body logic without altering the public spec minimizes compile dependency impact on callers. However, sessions that already instantiated package state can still be invalidated and hit ORA-04068. The body itself may also depend on other objects and must be compiled and verified.

### Specification Changes

The spec is the public contract. Modifying the spec—adding/removing procedures, changing parameter types, altering public types/constants—invalidates dependent packages, procedures, functions, triggers, and views.

After spec changes, trace the dependency graph and recompile in order. Callers compiled against the old signature may need source updates and recompilation.

### Backward Compatibility During Deployments

With multiple live application instances, avoid breaking public signatures needed by older code during rolling deployments. Instead:

- Add new overloads rather than immediately altering existing signatures.
- Keep deprecated procedures through a transition release.
- Deploy application versions supporting both old and new interfaces.
- Shift traffic to the new code.
- Remove legacy APIs in a later migration once no callers remain.

Design overloads carefully to avoid ambiguous calls, especially with default parameters or implicitly convertible types.

## 14. Using Edition-Based Redefinition for Minimal-Disruption Deployments

Oracle Edition-Based Redefinition (EBR) maintains multiple editions of supported database objects, allowing database code deployments while older applications continue using the previous edition and new instances use the new edition.

EBR typically involves:

- Edition-enabled schemas.
- Editioned PL/SQL packages, procedures, functions, and views where supported.
- Editioning views abstracting table structure changes.
- Services/sessions configured to run in specific editions.
- Cutover and old-edition cleanup workflows.

EBR mitigates the impact of spec/body changes on active sessions in older editions, though it requires upfront design and dependency testing. It does not fix compile errors, replace migration history, or handle every type of DDL/schema change.

If your system does not already use EBR, do not introduce EBR into an urgent hotfix solely for ORA-04068. For most applications, disciplined migrations, backward-compatible deploys, and planned pool recycling are sufficient.

## 15. Common Issues During Remediation

### Compilation Succeeds Yet Application Still Gets ORA-04068

The package is `VALID`, but older pooled sessions lost their state. Correlate recompilation timestamps, pooled sessions, and subsequent calls. Consider draining/recycling pools or safe unit-of-work retries.

### Remains INVALID After Recompiling

Read all `USER_ERRORS`/`ALL_ERRORS` entries, find the first root error, and check dependencies, direct grants, synonyms, types, and referenced objects. Repeatedly recompiling will not create missing objects or missing grants.

### Only PACKAGE BODY Is INVALID

Inspect body source, referenced tables/views/types/packages, and direct grants. The spec can stay `VALID` while procedures fail due to body errors.

### ORA-06508 After Drop/Create Package

Verify the recreated object has the exact owner/name, right edition, and both spec and body exist and are `VALID`. Confirm callers reference the right schema and hold `EXECUTE`.

### Errors Appear Only on Certain Requests

Most likely physical sessions in the pool have differing package-state histories. Record session identifiers and deployment times. Inspect stateful packages and recent invalidations/recompilations.

### Errors Return After Migration

Check migration ordering, package creation scripts, dependency compilation, grants, and synonyms. If pipelines run concurrently or applications auto-compile objects at startup, serialize deployments and eliminate competing DDL.

### DBA Edited Package Directly Without Updating Source Control

The live schema now drifts from deployment artifacts. Backport approved changes into source control via official migration scripts and audit for drift. Never treat production objects as the sole source of truth for rebuilding environments.

## 16. Safe Package Deployment Procedure

A reliable package deployment workflow:

1. **Review source**: confirm package spec/body and dependencies are tracked in source control.
2. **Test compilation**: compile in a test environment matching production grants, synonyms, types, and objects.
3. **Assess invalidation scope**: identify body vs. spec changes, stateful behavior, and dependents.
4. **Plan ordering**: deploy DDL/types/tables first, then dependent packages, then callers.
5. **Coordinate migrations**: allow only one migration runner per schema scope and record history.
6. **Compile and check errors**: verify via `ALL_OBJECTS`/`ALL_ERRORS` or deployment tooling.
7. **Smoke test**: invoke representative procedures/functions in a fresh session and verify transactions.
8. **Handle existing sessions**: drain/recycle pools if changes discard package state or break older callers.
9. **Monitor post-release**: watch for ORA-04063, ORA-06508, ORA-04068, invalid objects, and app errors.
10. **Retain audit trail**: store commits, migration versions, compile logs, and smoke-test results.

Never recompile an entire schema during peak hours without impact analysis. Mass recompilation consumes CPU, invalidates state, and can trigger transient errors in active sessions.

## 17. Error-Code Investigation Checklist

| Error | First Check | Resolution Direction |
|---|---|---|
| ORA-04063 | Object status and `USER_ERRORS`/`ALL_ERRORS` | Fix compile errors/dependencies, then compile |
| ORA-06508 | Object existence, status, owner, edition, dependencies | Restore/compile program unit and callers |
| ORA-04068 | Recompile time, package state, sessions/pools | Handle discarded state, transaction, and safe retry |
| ORA-04061 | Current package state invalidated | Inspect invalidation/recompile and older sessions |
| ORA-04065 | Object altered/dropped or not executable | Check deployment and object versions |
| `PLS-00302` | Referenced component missing in package/type | Check spec, version, and signatures |
| `PLS-00306` | Wrong number or types of arguments | Compare `ALL_ARGUMENTS` and caller |
| `PLS-00201` | Undeclared/unresolved identifier | Check owner, synonyms, direct grants, and object names |

Multiple error codes often appear together in one stack. Always read the root error and full stack rather than catching only the outermost code.

## 18. Core Operational Principles

- Check `PACKAGE` and `PACKAGE BODY` separately; one being `VALID` does not guarantee the other is valid.
- Use `USER_ERRORS`/`ALL_ERRORS`/`DBA_ERRORS` to inspect line, position, and compiler messages.
- Verify dependencies, synonyms, object types, and direct grants before recompiling.
- Fix root errors first, then compile in dependency order.
- Distinguish ORA-04063/06508 (unloadable/broken object) from ORA-04068 (discarded session package state).
- Package global state is session-scoped; never store durable business data in package variables.
- Connection pools keep old physical sessions across deployments; `close()` usually only returns the session to the pool.
- When updating stateful packages, plan session handling, pool draining/recycling, or controlled retries.
- Never blindly retry operations with side effects; place retries outside failed transactions and enforce idempotency where needed.
- Never kill sessions or release locks without verifying active transactions and runner state.
- After compiling, verify object status, error views, and test in a fresh session.
- When changing specs, evaluate dependencies and caller backward compatibility.
- Remember Oracle DDL commits implicitly and can leave migrations partially applied.
- Keep package source, migrations, compile logs, and deployment metadata in source control and audit trails.

ORA-04063, ORA-06508, and ORA-04068 all appear around PL/SQL changes, yet point to distinct problem classes: an uncompilable object, an unloadable program unit at runtime, or discarded session package state. Combining dictionary checks, compile error inspection, dependency graphs, and session lifecycle management pinpoints the true cause, restores packages safely, and minimizes post-deployment errors.
