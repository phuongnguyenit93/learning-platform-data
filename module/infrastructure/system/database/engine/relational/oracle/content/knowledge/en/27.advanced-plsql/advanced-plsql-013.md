# Package Privileges, Resource Management, and Testability

In PL/SQL, a package is typically the boundary an application uses to invoke a group of related operations. A package can read or modify multiple tables, call other packages, hold session state, and perform resource-intensive operations. Therefore, package design must answer three questions simultaneously:

- Who is allowed to call the package's API, and when called, whose privileges govern the statements inside?
- How does the package consume session and database resources, especially when the application uses connection pooling?
- Can the package's behavior, access permissions, and resource bounds be tested repeatably and independently of live production data?

These three questions are directly interconnected. A package running with owner rights can let the application need only `EXECUTE`, yet overly broad grants turn the package into a dangerous data-access bypass. A package keeping global variables might pass a single-session test yet leak state between two requests when a pooled session is reused. A package that commits on its own can prevent tests from rolling back data after each test run.

## 1. A Package as an API Boundary and a Security Boundary

A PL/SQL package usually consists of two parts:

- **Package specification (spec):** declares the procedures, functions, data types, constants, and variables accessible externally. This is the package's public contract.
- **Package body:** implements the procedures and functions in the spec, and may also contain private procedures, functions, variables, and cursors for internal use only.

For instance, an application only needs to know how to create an order. It does not need to know which tables the package queries, how it checks inventory, or where it writes history.

```sql
CREATE OR REPLACE PACKAGE app_owner.order_api
AUTHID DEFINER
AS
    PROCEDURE create_order(
        p_customer_id IN NUMBER,
        p_product_id  IN NUMBER,
        p_quantity    IN NUMBER
    );
END order_api;
/
```

```sql
CREATE OR REPLACE PACKAGE BODY app_owner.order_api
AS
    PROCEDURE create_order(
        p_customer_id IN NUMBER,
        p_product_id  IN NUMBER,
        p_quantity    IN NUMBER
    )
    IS
    BEGIN
        -- Validate data and execute business logic here.
        NULL;
    END create_order;
END order_api;
/
```

External users see only `create_order` because it is the public element in the spec. Internal procedures in the body cannot be invoked directly from another schema. Keeping the spec small and stable narrows the security surface: publish only the operations the application truly needs.

Oracle grants `EXECUTE` at the package level. When a user is granted `EXECUTE` on a package, that user can call its public subprograms; this privilege does not directly expose private body components. If two user groups require two distinct sets of operations, split the API into smaller packages rather than placing sensitive operations in one package and granting `EXECUTE` to everyone.

## 2. Package Invocation Privileges vs. Inner Statement Execution Privileges

When analyzing privileges on a package call, separate two privilege layers:

1. **Caller privileges:** which user or role is allowed to invoke the package.
2. **Executing code privileges:** whether internal SQL statements and nested package calls are checked against the owner's privileges or the caller's privileges.

These two layers are not identical. A caller may be allowed to invoke the package without having direct `SELECT` privilege on the tables the package reads. That is often an intentional design when the package serves as a controlled business API.

### 2.1. Granting EXECUTE Under Least Privilege

Suppose there are three schemas:

| Schema | Role |
|---|---|
| `DATA_OWNER` | Owns the business data tables |
| `APP_OWNER` | Owns the API packages |
| `APP_RUNTIME` | Application account used when connecting to the database |

The package owner requires direct privileges on objects in other schemas used by its code. Then the application runtime account needs only API invocation privileges if the package uses definer rights.

```sql
-- Grant direct privileges to the schema owning the package.
GRANT SELECT, INSERT, UPDATE
ON data_owner.orders
TO app_owner;

-- Create a role representing the group allowed to call the API.
CREATE ROLE order_api_executor;

GRANT EXECUTE
ON app_owner.order_api
TO order_api_executor;

GRANT order_api_executor TO app_runtime;
```

When privileges are granted via roles, administrators can manage API access by group. If an account needs only specific APIs, grant the corresponding role instead of granting `EXECUTE` on every package in the schema.

Do not grant to `PUBLIC` by default:

```sql
-- Think carefully before granting privileges to every user in the database.
GRANT EXECUTE ON app_owner.order_api TO PUBLIC;
```

Granting to `PUBLIC` exposes the API much more broadly than intended. If a package performs administrative operations, handles personal data, or carries sensitive business logic, `PUBLIC` grants can turn the package into an unintended access point.

Revoke privileges when no longer needed:

```sql
REVOKE EXECUTE
ON app_owner.order_api
FROM order_api_executor;
```

**Synonyms do not replace access privileges.** A public or private synonym merely allows referencing an object by a shorter name. The user still needs appropriate privileges on the target package. Likewise, knowing a schema, package, or procedure name grants no invocation rights.

### 2.2. AUTHID DEFINER: Running with Owner Privileges

`AUTHID DEFINER` is the default mode when a package omits an `AUTHID` clause. In this mode, statements inside the package execute with the privileges of the schema owning the package, called the *definer*.

For example, `APP_RUNTIME` has `EXECUTE` on `APP_OWNER.ORDER_API`, while `APP_OWNER` holds direct privileges on `DATA_OWNER.ORDERS`. When `APP_RUNTIME` calls `ORDER_API.CREATE_ORDER`, the package executes statements using `APP_OWNER`'s privileges. `APP_RUNTIME` does not need direct `INSERT` privilege on `DATA_OWNER.ORDERS` just to invoke the operation exposed by the package.

This is a common pattern for data APIs: applications cannot access tables arbitrarily and can only invoke operations controlled by the package. However, remember that the owner's privileges may exceed the caller's. Every public procedure must validate inputs and enforce business rules properly; never allow callers to pass arbitrary table names, SQL statements, or expressions to exploit definer rights.

A common pitfall is that **roles are disabled inside PL/SQL units running under definer rights**. Consequently, privileges on tables or helper packages needed by the code must be granted directly to the schema owning the package. Granting them only to a role held by the owner is usually insufficient to compile or run static SQL inside a definer-rights unit.

For example, if the body queries `DATA_OWNER.CUSTOMERS`, grant directly:

```sql
GRANT SELECT
ON data_owner.customers
TO app_owner;
```

After changing privileges, recompile the package if needed and check compilation errors in `USER_ERRORS` or `ALL_ERRORS`. Never resolve privilege errors by granting broad access to `PUBLIC`.

### 2.3. AUTHID CURRENT_USER: Running with Caller Privileges

Declare `AUTHID CURRENT_USER` so the package uses the *invoker*'s privilege context at runtime:

```sql
CREATE OR REPLACE PACKAGE app_owner.report_api
AUTHID CURRENT_USER
AS
    PROCEDURE show_my_report;
END report_api;
/
```

This mode suits situations where one package must operate on different datasets each caller is authorized to access. For example, a reporting utility might query views granted selectively to each caller. In that case, the caller must hold the required privileges on objects actually accessed by the code.

Key differences:

| Aspect | `AUTHID DEFINER` | `AUTHID CURRENT_USER` |
|---|---|---|
| Runtime privilege context | Package owner | Current caller |
| Session roles inside unit | Disabled, except roles granted to program units in supported versions | Enabled roles of the invoker participate in privilege checks |
| Does caller need privileges on internal tables? | Usually no, if definer has required privileges and API exposes operation | Yes, as required by executed statements |
| Typical use case | Business APIs controlling data access | Utilities that must respect each caller's own privileges |

`CURRENT_USER` and `CURRENT_SCHEMA` are two distinct concepts. `CURRENT_USER` determines the user context for privilege checks; `CURRENT_SCHEMA` affects resolution of unqualified object names. Changing `CURRENT_SCHEMA` grants no extra privileges and does not make a user an object owner.

For invoker-rights units in Oracle versions enforcing `INHERIT PRIVILEGES`, the unit owner must also hold permission to inherit the invoker's privileges per database policy. Administrators can grant this with explicit scope, for example:

```sql
-- Illustrative example: APP_OWNER is allowed to inherit privileges of APP_RUNTIME.
GRANT INHERIT PRIVILEGES
ON USER app_runtime
TO app_owner;
```

Check your Oracle version and actual security policy before granting inherit privileges. Do not broaden inheritance to every user when a package only serves a specific caller group.

### 2.4. Roles Granted to Program Units and Dynamic SQL

In Oracle versions supporting *Code Based Access Control* (CBAC), a role can be granted to a program unit. The role is enabled within that unit's execution scope, scoping privileges per package instead of granting them broadly to the package-owning schema.

Example syntax on supported versions:

```sql
GRANT order_data_reader TO PACKAGE app_owner.order_api;
```

This is an advanced mechanism. Verify exact syntax and support conditions in your running Oracle version, and verify effective privileges during package execution. Do not introduce CBAC merely to avoid understanding `AUTHID` or as a substitute for least-privilege design.

Dynamic SQL requires separate scrutiny. For statements executed via `EXECUTE IMMEDIATE` or `DBMS_SQL`, privilege checks occur at execution time under the unit's privilege context. Never concatenate input data directly into SQL strings:

```sql
-- Use bind variables for data values.
EXECUTE IMMEDIATE
    'SELECT status FROM data_owner.orders WHERE order_id = :1'
    INTO l_status
    USING p_order_id;
```

Bind variables cannot substitute for table names, column names, or SQL keywords. If dynamic SQL must use identifiers, validate them against an allowlist and use verification utilities such as `DBMS_ASSERT` where appropriate. Never let callers supply arbitrary SQL fragments for a definer-rights package to execute.

## 3. Resource Management in Packages

A package does not have an isolated CPU or memory quota simply because it is a package. Resources are consumed through sessions, SQL statements, transactions, and database services invoked by the package. Thus, resource management combines code design with session configuration and Oracle Database Resource Manager.

### 3.1. Package State Persists per Session

Variables declared at the package body or spec level constitute session-scoped package state. This state can persist across multiple package calls within the same session.

```sql
CREATE OR REPLACE PACKAGE app_owner.request_context
AS
    g_request_count PLS_INTEGER := 0;

    PROCEDURE next_request;
END request_context;
/

CREATE OR REPLACE PACKAGE BODY app_owner.request_context
AS
    PROCEDURE next_request
    IS
    BEGIN
        g_request_count := g_request_count + 1;
    END next_request;
END request_context;
/
```

Within one session, `g_request_count` keeps incrementing across calls. Other sessions maintain independent package state. This has a crucial consequence for applications using connection pools: one physical connection can sequentially serve multiple logical requests from different users. If a package stores `customer_id`, temporary privileges, filters, or request data in global variables, a subsequent request can see leftover state from the previous request.

Safe practices:

- Prefer passing required data through procedure and function parameters.
- Keep package state only with a clear reason and a defined state lifecycle.
- If session state is unavoidable, provide an explicit initialization or reset procedure and call it at appropriate connection lifecycle boundaries.
- When a pool reuses sessions, reset context, roles, package state, and session attributes per the application's connection management workflow.
- Never treat package variables as shared memory across sessions; every session has its own state.

`DBMS_SESSION.RESET_PACKAGE` can be used to reset package state in a session when appropriate. Because it affects session-wide package state, coordinate with connection pooling and check overhead before calling it frequently. Another option is designing stateless packages that retain no request state across calls.

Oracle also supports `PRAGMA SERIALLY_REUSABLE` for packages needing temporary state scoped to a single server call. This alters package state lifecycle and is unsuitable if logic must preserve variables across multiple server calls. Use it only after understanding session/server-call lifecycles and the pragma's restrictions in your version.

When a package or its dependencies are invalidated/recompiled, existing package state can be discarded. Applications may encounter errors such as `ORA-04068` or `ORA-04061` while calling stateful packages. Therefore, avoid relying on package state for critical business data or durable state. On errors during a call, retry only when the operation is idempotent or the prior transaction is confirmed incomplete; blind retries can create duplicate records or double-execute business actions.

### 3.2. Closing Cursors and Releasing Temporary Resources

Resources commonly requiring management inside packages include:

- Explicit cursors and `REF CURSOR`s.
- Cursors opened via `DBMS_SQL`.
- Large collections populated with `BULK COLLECT`.
- Temporary LOBs.
- Long-held locks and transactions.

Manually opened cursors must be closed along both the normal path and exception paths. When using a cursor `FOR` loop, Oracle manages opening and closing automatically for that loop; with explicit cursors or `REF CURSOR`s, clearly define which component owns closing responsibility.

Example managing an explicit cursor:

```sql
DECLARE
    CURSOR c_orders IS
        SELECT order_id
        FROM data_owner.orders
        WHERE status = 'PENDING';

    l_order_id data_owner.orders.order_id%TYPE;
BEGIN
    OPEN c_orders;

    LOOP
        FETCH c_orders INTO l_order_id;
        EXIT WHEN c_orders%NOTFOUND;

        -- Process one order.
        NULL;
    END LOOP;

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

With `DBMS_SQL`, call `DBMS_SQL.CLOSE_CURSOR` on completion and on error. For temporary LOBs created by your code, release them via `DBMS_LOB.FREETEMPORARY` when no longer needed and when your code owns the LOB lifecycle. Never free a LOB still owned by a caller or another component.

Avoid loading huge datasets into collections just to process row by row. Use `BULK COLLECT ... LIMIT` to cap rows per batch, paired with `FORALL` for bulk DML. Choose `LIMIT` based on row size and environment memory limits, not a fixed constant applied blindly to every system.

If a package returns a `REF CURSOR`, the API contract must specify that the caller fetches and closes the cursor. A package that opens and returns a cursor should generally not close it before returning. Conversely, if the package fetches all data itself, it must close the cursor across all execution paths.

### 3.3. Transactions and Locks

A business package should generally let the caller or transaction coordinator decide when to `COMMIT` and `ROLLBACK`. If a library procedure commits internally, callers lose the ability to roll back an entire multi-package workflow.

For example, an application creates an order, deducts inventory, and records payment in one transaction. If `ORDER_API.CREATE_ORDER` commits immediately after inserting the order, a failure in the inventory step leaves partial, inconsistent data behind.

Use `PRAGMA AUTONOMOUS_TRANSACTION` only when an operation is genuinely independent of the main transaction, such as writing an audit record that must persist even if the business transaction rolls back. Understand clearly that autonomous transactions commit independently and see data under separate transaction rules. Never use it as a workaround for transaction errors or to make tests easier to run.

Hold locks for the shortest possible duration. Never call slow network services or wait on user input while a transaction holds row locks. For long-running workflows, consider breaking work into stateful steps with short transactions, depending on business consistency requirements.

### 3.4. Workload Identification and Throttling

Oracle Database Resource Manager governs workloads at the session/consumer-group level using resource plans. Depending on configuration and version, resource plans can allocate CPU, limit resource consumption, cap concurrent active sessions, or switch groups when thresholds are exceeded.

Packages do not create their own consumer groups. To regulate work performed by a package, the application must help the database identify the session or operation. `DBMS_APPLICATION_INFO` attaches module and action tags to the session:

```sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_SERVICE',
        action_name => 'CREATE_ORDER'
    );
END;
/
```

At business transition points, update the action to distinguish operations such as `CREATE_ORDER`, `REBUILD_REPORT`, or `BATCH_CLOSE`. Administrators can use module/action tags for monitoring and for configuring Resource Manager mapping rules appropriately.

Standardize responsibility for setting and restoring module/action. If the application layer sets the module for a request, a child package should not arbitrarily overwrite the module and wipe the caller's metadata. Let the application layer own the module while packages update action by convention; at request end, the context owner restores initial values.

Profiles and quotas also have distinct scopes:

| Mechanism | Primary Scope |
|---|---|
| Database Resource Manager | Throttles workload and resources per session/consumer group |
| Database profile | User/session-level resource limits and policies; enforcement depends on database settings such as `RESOURCE_LIMIT` |
| Tablespace quota | Storage limit a schema/user may allocate within a tablespace |
| In-code limits | Batch sizes, processed row caps, business timeouts, retry limits, and data scope |

Do not confuse tablespace quotas with PL/SQL memory limits, nor user profiles with per-package quotas. If multiple packages run in the same session, Resource Manager sees workload by session/consumer group unless the application attaches identifying tags.

## 4. Designing Packages for Testability

A package is testable when its inputs, outputs, side effects, and required privileges are observable. The goal is for each test case to set up preconditions, invoke an API, and assert outcomes without depending on leftover state from prior runs.

### 4.1. Keep Specs Small and Separate Business Rules from Data Access

Avoid stuffing business calculations, multi-table queries, notifications, file writes, and transaction control into one package. When responsibilities are tangled together, even a tiny test requires standing up nearly the entire environment.

You can separate responsibilities into focused groups:

| Package Group | Responsibility |
|---|---|
| `ORDER_RULES` | Calculates and validates business rules; prefer pure functions |
| `ORDER_REPOSITORY` | Reads and writes order data |
| `ORDER_NOTIFICATION` | Sends or queues notification requests |
| `ORDER_API` | Orchestrates steps and exposes the application API |

This is separation by responsibility, not a rigid rule requiring one package per table. Keep package counts reasonable so boundaries stay meaningful without bloating specs.

Pure functions accept data via parameters and return results without depending on session state, database tables, system time, or external services. Such functions are typically the easiest to test.

```sql
CREATE OR REPLACE PACKAGE app_owner.order_rules
AS
    FUNCTION net_amount(
        p_gross         IN NUMBER,
        p_discount_pct  IN NUMBER
    ) RETURN NUMBER;
END order_rules;
/
```

```sql
CREATE OR REPLACE PACKAGE BODY app_owner.order_rules
AS
    FUNCTION net_amount(
        p_gross         IN NUMBER,
        p_discount_pct  IN NUMBER
    ) RETURN NUMBER
    IS
    BEGIN
        IF p_gross IS NULL OR p_gross < 0 THEN
            RAISE_APPLICATION_ERROR(-20001, 'Gross amount must be non-negative');
        END IF;

        IF p_discount_pct IS NULL
           OR p_discount_pct < 0
           OR p_discount_pct > 100
        THEN
            RAISE_APPLICATION_ERROR(-20002, 'Discount must be between 0 and 100');
        END IF;

        RETURN ROUND(p_gross * (1 - p_discount_pct / 100), 2);
    END net_amount;
END order_rules;
/
```

This function reads no tables, makes no `SYSDATE` calls, uses no package variables, and never commits. Output depends solely on its two parameters. It can be tested directly:

```sql
DECLARE
    l_actual NUMBER;
BEGIN
    l_actual := app_owner.order_rules.net_amount(100, 10);

    IF l_actual <> 90 THEN
        RAISE_APPLICATION_ERROR(-20990, 'Expected net amount 90');
    END IF;
END;
/
```

Beyond nominal cases, test boundary cases such as discount `0`, discount `100`, amount `0`, negative values, and `NULL` parameters. If business rules specify different `NULL` semantics, state them clearly in the API contract and test against that contract.

### 4.2. Make Dependencies and Time Explicit

Hidden dependencies that undermine repeatable tests include:

- `SYSDATE` or `SYSTIMESTAMP` scattered throughout code.
- `SYS_CONTEXT` reading user, tenant, or request context.
- `DBMS_RANDOM` or sequence generation assumed to follow fixed values.
- Package variables holding configuration or state from previous calls.
- Direct table queries or external service calls embedded inside calculation functions.

When logic depends on time, pass the timestamp into the business API or isolate time retrieval behind a dedicated adapter. When random values are required, separate value generation from business decision logic. With sequences, tests should verify that an ID is generated and linked properly rather than assuming a sequence starts at a fixed number.

PL/SQL lacks interface/mock objects like some object-oriented languages. You can introduce substitution seams by separating data-access packages from business-rule packages, passing required data via parameters, or compiling test-specific adapters in an isolated test schema. Avoid swapping synonyms or editing shared packages during parallel test runs, as doing so creates global state and breaks test isolation.

### 4.3. Let Callers Control Transactions

When a business package does not commit internally, tests can prepare data, invoke the API, assert outcomes, and roll back:

```sql
SAVEPOINT before_order_test;

BEGIN
    app_owner.order_api.create_order(
        p_customer_id => 1001,
        p_product_id  => 501,
        p_quantity    => 2
    );

    -- Query and assert data created by the test.
    -- Specific assertions depend on the testing framework.
END;
/

ROLLBACK TO before_order_test;
```

This illustrates transaction lifecycle control; it only rolls back changes inside the current transaction. Autonomous transactions, DDL, and external side effects are not undone this way. Tests require dedicated cleanup steps for any such side effects.

### 4.4. Use a Testing Framework and Explicit Assertions

You can use `utPLSQL` to organize suites, test cases, and assertions for PL/SQL. A framework standardizes execution and reporting, though it does not substitute for designing packages with clear inputs and controlled side effects.

A test case should clearly show three parts:

1. **Arrange:** set up required data and preconditions.
2. **Act:** invoke the exact API under test.
3. **Assert:** verify returned values, data changes, and expected errors for invalid inputs.

Never test only that a procedure runs without raising an exception. Verify concrete business outcomes such as totals, order status, updated row counts, or contracted error codes.

### 4.5. Test Privileges as Part of Behavior

A package may succeed when run as the schema owner yet fail when invoked by the application user. Privilege tests must therefore run under schemas and roles matching the deployment model.

For definer-rights APIs, verify conditions such as:

- `APP_OWNER` holds required direct grants on tables and helper packages.
- `APP_RUNTIME` holds `EXECUTE` on the API.
- `APP_RUNTIME` lacks direct privileges on internal tables when disallowed by design.
- Callers can invoke public operations and cannot invoke private body subprograms.
- Callers are denied access once `EXECUTE` is revoked.

For invoker-rights APIs, also test whether callers have privileges on objects accessed by the unit. Test both authorized and unauthorized cases. If the application relies on roles, check active roles at call time; if code runs inside a definer-rights unit, test role-disabling rules or CBAC role grants to the program unit separately.

Never run security tests exclusively from a DBA account. DBA privileges far exceed application accounts and mask privilege configuration bugs.

## 5. Recommended Test Matrix

Critical packages should be tested across multiple layers. Not every project needs the same test count, yet these categories prevent overlooking privilege and resource behaviors.

| Category | Scenario | What to Verify |
|---|---|---|
| API | Call with valid inputs | Output matches contract |
| Data boundaries | `NULL`, negative, zero, max values | Clear boundary behavior and errors |
| Invocation privilege | Caller has `EXECUTE` | Public API succeeds |
| Invocation privilege | Caller lacks `EXECUTE` | Access denied |
| Definer rights | Owner has direct grant, caller lacks table grant | API operates within designed scope |
| Invoker rights | Caller holds or lacks object grants | Outcome reflects caller's privileges |
| Roles | Privileges granted only via role | Verify behavior under `AUTHID` and CBAC |
| State | Consecutive calls in the same session | No data leakage between requests |
| Connection pool | Session reused for another caller/request | Context and package state reset properly |
| Cursors/LOBs | Both success and exception paths | Resources closed or freed cleanly |
| Large data | Processing high row volumes | Memory and time remain within acceptable limits |
| Transactions | Downstream step fails | No partial commits violating contract |
| Concurrency | Multiple sessions call same API | No errors from assumed shared state |
| Invalidation | Package/dependencies recompiled | Application handles discarded package state safely |

Resource tests must run in an environment sufficiently close to production to observe session, cursor, and Resource Manager behavior. A unit test running a handful of rows cannot prove a package handles millions of rows or concurrent sessions.

## 6. Error Monitoring and Diagnostics

Common errors encountered during package deployment relate to privileges or state:

| Error | Common Cause | Diagnostic Steps |
|---|---|---|
| `PLS-00201: identifier must be declared` | Misspelled object name, invisible object, or missing compile-time privilege | Check schema, synonyms, object existence, and direct grants to owner |
| `ORA-01031: insufficient privileges` | Caller or executing code lacks runtime privileges | Check `AUTHID`, executing user, active roles, and object privileges |
| `ORA-04068: existing state of packages has been discarded` | Session package state discarded, typically after invalidation/recompile | Inspect package state and dependencies; ensure callers do not rely on stale state |
| `ORA-04061: existing state of package has been invalidated` | Stateful package was invalidated | Check recent compilations, dependencies, and application session handling |
| `ORA-06508: PL/SQL: could not find program unit being called` | Program unit unavailable or dependency invalid | Check `VALID/INVALID` status, compile errors, and deployment order |

When checking object status, query views matching your account's privileges:

```sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name = 'ORDER_API';
```

```sql
SELECT name, type, line, position, text
FROM user_errors
WHERE name = 'ORDER_API'
ORDER BY sequence;
```

If the package resides in another schema and your account has metadata privileges, use `ALL_OBJECTS`, `ALL_ERRORS`, or the corresponding DBA views. During diagnostics, record the connected user, `CURRENT_USER`, `CURRENT_SCHEMA`, active roles, and session module/action. Reading package source alone rarely suffices to explain a runtime privilege failure.

Never use `WHEN OTHERS THEN NULL` to hide errors. When extra handling is needed, capture context and re-raise via `RAISE`, unless the API contract explicitly defines another error translation. Swallowing exceptions hides failures from tests and prevents callers from knowing an operation failed.

## 7. Design and Deployment Workflow

When creating or modifying packages, follow this sequence:

1. **Define the API:** list only procedures, functions, and types to expose publicly; keep implementation inside the body.
2. **Choose AUTHID:** decide whether operations run under owner or invoker rights; document the rationale in design notes.
3. **Build the privilege matrix:** specify which callers get `EXECUTE`, which direct grants the owner needs, and whether CBAC is required.
4. **Audit dynamic SQL:** use bind variables for data values, validate identifiers, and never allow callers to inject arbitrary SQL into definer-rights APIs.
5. **Audit resource lifecycles:** define who closes cursors, who frees LOBs, batch sizes, transaction boundaries, and package state lifetimes.
6. **Audit session pooling:** ensure new requests never inherit context or package variables from prior requests.
7. **Design tests:** isolate pure logic, prepare fixtures, assert business outcomes and error paths.
8. **Test with real application accounts:** verify both allowed and denied privileges.
9. **Observe workloads:** tag module/action and measure timings and resources on realistic data volumes.
10. **Deploy with controls:** compile packages, inspect `USER_ERRORS`/`ALL_ERRORS`, check dependency status, and re-verify privileges post-deployment.

A well-designed package has a clear spec, least-privilege grants, a bounded session-state lifecycle, timely resource cleanup, and critical behaviors verifiable through repeatable tests. Designing these properties upfront makes packages straightforward to operate without relying on overly broad privileges or hidden database state.
