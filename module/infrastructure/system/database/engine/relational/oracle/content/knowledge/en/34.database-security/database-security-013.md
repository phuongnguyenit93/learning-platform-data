# Virtual Private Database, application context, and DBMS_RLS in Oracle

## 1. What problem does VPD solve?

In a database where multiple business units or multiple customers share tables, applications often need to restrict each user to seeing only rows within their authorized scope. For example, tenant A users should only see tenant A orders; North branch staff should only access North branch data; HR staff should only view records within their assigned organizational unit.

If filtering relies only on conditions written inside every SQL statement, a single query that forgets the filter can leak data. **Virtual Private Database (VPD)** pushes security conditions down into the database: Oracle automatically appends predicates to SQL statements accessing policy-protected objects.

VPD is often referred to as row-level security or fine-grained access control (FGAC). Key components:
- **Application context:** holds session security attributes such as tenant, user, region, or business role.
- **Policy function:** generates a SQL predicate based on the context and accessed object.
- **`DBMS_RLS`:** policy administration package that attaches policies to tables/views and manages policy lifecycles.
- **Database optimizer/execution engine:** enforces the predicate as part of the SQL statement.

For example, the application executes:

```sql
SELECT order_id, customer_id, amount
FROM app.orders;
```

If a policy generates the predicate `tenant_id = ...`, Oracle processes the query scoped to the current tenant without requiring the application to append the filter manually in every SQL statement.

VPD is a crucial protection layer for shared data. However, a policy is only secure when context is populated from authenticated identities, predicates are designed fail-closed, and accounts holding bypass privileges are tightly controlled.

This lesson belongs to the **Security** chapter in the **Database Engine Relational Oracle** module, focusing on Virtual Private Database, application context, and `DBMS_RLS`.

## 2. Multi-tenant data model

Suppose an order management application shares a single table across multiple tenants:

```sql
CREATE TABLE app.orders (
    order_id      NUMBER PRIMARY KEY,
    tenant_id     NUMBER NOT NULL,
    customer_id   NUMBER NOT NULL,
    order_date    DATE NOT NULL,
    status        VARCHAR2(20) NOT NULL,
    amount        NUMBER(12,2) NOT NULL
);
```

Each row has `TENANT_ID` identifying the data owner. If tenant A has ID 10 and tenant B has ID 20, queries for tenant A must return only rows with `tenant_id = 10`.

If the application writes manually:

```sql
SELECT order_id, customer_id, amount
FROM app.orders
WHERE tenant_id = :tenant_id;
```

every access path must remember to pass the right bind variable. A new report, stored procedure, or SQL query could forget the filter. Users could attempt to tamper with the bind value to read another tenant if the application fails to enforce authorization.

VPD places the condition on the database object itself, ensuring the policy applies to SQL statements within policy scope even when the SQL statement does not explicitly include a tenant predicate.

### 2.1. Tenant isolation principles

- Every row must carry a valid tenant key.
- Tenant keys must never be taken directly from unauthenticated input.
- Policies must deny access when context is missing or invalid.
- Application accounts must not hold policy bypass privileges.
- All data access paths must be verified, including views, procedures, jobs, and reports.
- Cross-tenant testing must prove tenant A cannot read or modify tenant B data.

VPD does not invent a tenant model on its own. It enforces rules designed from the application's identity and data model.

## 3. How VPD works

When a session executes a SQL statement against an object with a VPD policy, Oracle invokes the policy function according to policy type and cursor/context state. The function returns a SQL predicate string. Oracle appends that predicate to the statement prior to optimization and execution.

General flow:

```text
User logs in
        |
        v
Application authenticates identity
        |
        v
Trusted package sets application context
        |
        v
Session queries APP.ORDERS
        |
        v
Oracle finds VPD policy attached to object
        |
        v
DBMS_RLS policy function reads context
        |
        v
Returns predicate, e.g., tenant_id = ...
        |
        v
Oracle applies predicate to SQL
        |
        v
Optimizer generates plan and returns authorized data
```

### 3.1. Predicates are enforced inside the database

Suppose the policy returns:

```sql
tenant_id = TO_NUMBER(SYS_CONTEXT('APP_CTX', 'TENANT_ID'))
```

The application query:

```sql
SELECT *
FROM app.orders
WHERE status = 'OPEN';
```

is logically processed as if it included the tenant condition:

```sql
SELECT *
FROM app.orders
WHERE status = 'OPEN'
  AND tenant_id = TO_NUMBER(SYS_CONTEXT('APP_CTX', 'TENANT_ID'));
```

This is a logical illustration to understand the policy. Oracle manages predicate attachment during parse/optimization; do not expect the SQL text sent by the application to visibly show the appended clause verbatim.

### 3.2. Which statement types does VPD apply to?

Policies can be configured for statement types such as:
- `SELECT`
- `INSERT`
- `UPDATE`
- `DELETE`
- Certain index operations or other statements per release and API support.

When creating a policy, explicitly declare `statement_types` so the policy protects all required operations. Do not assume a `SELECT` policy automatically protects DML.

### 3.3. VPD and object privileges are two separate layers

VPD filters which rows a user can see or manipulate. It does not replace `SELECT`, `INSERT`, `UPDATE`, `DELETE` privileges on the object.

A user must hold the required object privileges before executing SQL. VPD then restricts the row set within those privileges.

## 4. What is an application context?

An application context is a set of session attributes stored by the database and accessed via `SYS_CONTEXT`. For example, namespace `APP_CTX` might contain:
- `TENANT_ID`
- `APP_USER_ID`
- `REGION_ID`
- `BUSINESS_UNIT`
- `ACCESS_LEVEL`

Reading a context:

```sql
SELECT SYS_CONTEXT('APP_CTX', 'TENANT_ID') AS tenant_id
FROM dual;
```

`SYS_CONTEXT` returns character values. When comparing against a `NUMBER` column, perform explicit conversion or ensure comparison semantics are appropriate.

### 4.1. Namespace and attribute

- **Namespace:** context group, e.g., `APP_CTX`.
- **Attribute:** attribute name, e.g., `TENANT_ID`.
- **Value:** value set in the session.

A context is session state, not a table storing user profiles. Context values can be updated during the session lifecycle through the designated package specified when creating a secure application context.

### 4.2. Secure application context

A secure application context is created with `CREATE CONTEXT ... USING package`. Only the designated trusted package can set attributes in that namespace via `DBMS_SESSION.SET_CONTEXT`.

Example:

```sql
CREATE CONTEXT app_ctx USING sec.app_context_pkg;
```

`SEC.APP_CONTEXT_PKG` is the trusted package authorized to set the context. Creating contexts requires appropriate system privileges, usually performed by a security administrator/DBA.

Never use an unprotected context namespace for authorization decisions. Context values are safe only when the path setting them is strictly controlled.

## 5. Designing context from authenticated identities

The most critical aspect of VPD is the origin of the context. If a user can arbitrarily set `TENANT_ID = 20`, the policy executes the predicate faithfully yet protects the wrong tenant.

### 5.1. Do not trust client-supplied tenant IDs

Avoid writing a naive procedure like:

```sql
-- Unsafe design: caller picks any tenant.
PROCEDURE set_tenant(p_tenant_id NUMBER) IS
BEGIN
    DBMS_SESSION.SET_CONTEXT(
        'APP_CTX',
        'TENANT_ID',
        TO_CHAR(p_tenant_id)
    );
END;
```

If an application can call the procedure with any number, users can request other tenants. A secure application context only restricts which package may set the context; it does not by itself prove the package properly authenticated the user.

### 5.2. Dedicated DB principal per tenant model

A straightforward pattern uses a separate database principal per tenant or trusted group, with a database table mapping principals to tenants. Example:

```sql
CREATE TABLE sec.db_principal_tenant (
    db_username VARCHAR2(128) PRIMARY KEY,
    tenant_id   NUMBER NOT NULL
);
```

The trusted package derives the tenant from the logged-in principal:

```sql
CREATE OR REPLACE PACKAGE sec.app_context_pkg
AUTHID DEFINER
AS
    PROCEDURE set_for_session;
    PROCEDURE clear_for_session;
END;
/
```

```sql
CREATE OR REPLACE PACKAGE BODY sec.app_context_pkg
AS
    PROCEDURE set_for_session
    IS
        l_tenant_id sec.db_principal_tenant.tenant_id%TYPE;
    BEGIN
        SELECT tenant_id
        INTO l_tenant_id
        FROM sec.db_principal_tenant
        WHERE db_username = SYS_CONTEXT('USERENV', 'SESSION_USER');

        DBMS_SESSION.SET_CONTEXT(
            'APP_CTX',
            'TENANT_ID',
            TO_CHAR(l_tenant_id)
        );
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            DBMS_SESSION.CLEAR_CONTEXT('APP_CTX', NULL, NULL);
            RAISE_APPLICATION_ERROR(
                -20001,
                'No tenant mapping for authenticated database principal'
            );
    END set_for_session;

    PROCEDURE clear_for_session
    IS
    BEGIN
        DBMS_SESSION.CLEAR_CONTEXT('APP_CTX', NULL, NULL);
    END clear_for_session;
END;
/
```

This illustrates a database principal model with explicit tenant mapping. The application account needs `EXECUTE` on the package within appropriate scope:

```sql
GRANT EXECUTE ON sec.app_context_pkg TO order_app;
```

Create the context referencing the trusted package:

```sql
CREATE CONTEXT app_ctx USING sec.app_context_pkg;
```

### 5.3. Applications sharing a single service account

Many multi-tenant systems use one shared database account for all requests. In that setup, `SESSION_USER` identifies only the service account, not the end user or tenant.

You cannot safely infer the tenant from a shared service account alone. A trusted authentication mechanism between the application tier and database is required, such as:
- Proxy authentication or database-authenticated connection identities.
- A signed assertion/token verified by a trusted mechanism.
- A package accepting only authenticated identities from trusted middleware, with tightly controlled execute privileges and transport channels.
- Separate identity architectures per workload/tenant where appropriate.

Never treat `CLIENT_IDENTIFIER` or a client-supplied tenant value as authentication proof. Such attributes are helpful for traceability, but if callers can set them freely, they cannot serve alone as authorization grounds.

### 5.4. Fail closed

If the tenant cannot be determined, the package should leave the context unset and the policy must return a predicate permitting zero rows, such as `1=0`.

Never return an empty predicate, `1=1`, or skip the policy when context is missing. In data security, authentication failures must result in access denial.

## 6. Policy functions for VPD

A policy function is called by `DBMS_RLS` to obtain a predicate. The basic signature receives the schema and object name and returns a SQL predicate string.

Example:

```sql
CREATE OR REPLACE FUNCTION sec.orders_tenant_predicate(
    object_schema IN VARCHAR2,
    object_name   IN VARCHAR2
)
RETURN VARCHAR2
AUTHID DEFINER
AS
    l_tenant_id VARCHAR2(128);
BEGIN
    l_tenant_id := SYS_CONTEXT('APP_CTX', 'TENANT_ID');

    IF l_tenant_id IS NULL THEN
        RETURN '1=0';
    END IF;

    RETURN
        'tenant_id = TO_NUMBER(SYS_CONTEXT(''APP_CTX'', ''TENANT_ID''))';
END;
/
```

The policy function does not need to concatenate the tenant value into the predicate string. The predicate references `SYS_CONTEXT` to read the session value when SQL is processed.

### 6.1. Why return `1=0` when context is missing?

If the function returns `1=1` when context is null, every row could become visible. If the function returns an empty string or no predicate, the policy may become ineffective or raise errors depending on API semantics.

`1=0` is an always-false predicate, so zero rows are returned. This is a straightforward fail-closed pattern for the tenant example.

### 6.2. Do not concatenate context directly into predicates

Avoid:

```sql
-- Avoid building SQL predicates by concatenating untrusted values.
RETURN 'tenant_id = ' || l_tenant_id;
```

If values can be manipulated, string concatenation can cause SQL injection or type conversion errors. Reference `SYS_CONTEXT` inside the predicate, or build predicates only from validated, type-checked, properly formatted values.

### 6.3. Policy functions must be simple and stable

A well-designed policy function:
- Reads only required context and metadata.
- Returns a short, clear predicate.
- Never executes DDL or transaction control.
- Avoids querying complex tables on every parse whenever possible.
- Never calls remote services inside the policy function.
- Never writes secrets or sensitive data to logs.
- Handles missing context fail-closed.

`object_schema` and `object_name` are parameters passed by Oracle to the function. They can be used if one function serves multiple objects, but never concatenate application-supplied object names into SQL.

## 7. Attaching policies with DBMS_RLS.ADD_POLICY

`DBMS_RLS` is the PL/SQL package used to manage VPD policies. Example attaching a tenant policy to `APP.ORDERS`:

```sql
BEGIN
    DBMS_RLS.ADD_POLICY(
        object_schema   => 'APP',
        object_name     => 'ORDERS',
        policy_name     => 'ORDERS_TENANT_POLICY',
        function_schema => 'SEC',
        policy_function => 'ORDERS_TENANT_PREDICATE',
        statement_types => 'SELECT,INSERT,UPDATE,DELETE',
        update_check    => TRUE,
        enable          => TRUE
    );
END;
/
```

This statement is run by a schema/administrator with appropriate policy and object management privileges. Verify `EXECUTE` on `DBMS_RLS` and required administrative privileges per release.

### 7.1. Key parameters

| Parameter | Role |
|---|---|
| `object_schema` | Schema owning the table/view |
| `object_name` | Name of the table/view protected by the policy |
| `policy_name` | Policy name |
| `function_schema` | Schema owning the policy function |
| `policy_function` | Function returning the predicate |
| `statement_types` | Protected statement types |
| `update_check` | Validates resulting rows after INSERT/UPDATE against the predicate |
| `enable` | Enables the policy immediately upon creation |
| `policy_type` | Policy evaluation/caching mode |
| `sec_relevant_cols` | Sensitive columns for column-level VPD |
| `sec_relevant_cols_opt` | Row/column handling option for column-level policies |

Not every parameter is needed for every policy. Choose settings based on the semantics requiring protection and the Oracle documentation for your deployment version.

### 7.2. SELECT

For `SELECT`, the predicate limits returned rows:

```sql
SELECT order_id, tenant_id, amount
FROM app.orders;
```

If the context holds tenant 10, the user sees only tenant 10 rows per policy.

### 7.3. UPDATE and DELETE

The policy predicate restricts which rows the statement can locate and modify. A statement:

```sql
UPDATE app.orders
SET status = 'CLOSED'
WHERE order_id = 500;
```

affects only rows within the current tenant scope. If order 500 belongs to another tenant, the statement cannot update that row through the policy.

### 7.4. INSERT and update_check

`update_check => TRUE` instructs Oracle to check whether the new row after `INSERT` or `UPDATE` satisfies the policy predicate. This prevents a tenant 10 application from inserting a row with `tenant_id = 20` or reassigning a tenant key to another tenant.

If a policy filters existing rows without checking new values, users may be restricted on reads yet still able to write out-of-scope data. For tenant isolation, checking new rows is essential.

### 7.5. Tenant columns must be protected

Do not allow applications to arbitrarily modify `TENANT_ID`. In addition to VPD, consider:
- Not granting `UPDATE` privilege on the tenant key column.
- Using appropriate triggers/constraints or write APIs.
- Setting tenant ID from context inside stored procedures.
- Testing `INSERT`/`UPDATE` with spoofed tenant IDs.

VPD and column privileges complement each other; never rely solely on UI forms to lock the tenant key.

## 8. Policy types and caching

Policy type governs when Oracle calls the policy function and how predicates are reused. Choosing the wrong type can cause stale predicates to be used after context changes.

Common types in `DBMS_RLS`:

| Policy type | General meaning | When to consider |
|---|---|---|
| `DYNAMIC` | Evaluates policy function per statement parse lifecycle; common default | When predicates depend on session/request and correctness is prioritized |
| `STATIC` | Predicate is cached because the policy function always returns the same predicate for the object | Only when predicates truly do not depend on user/session/context |
| `SHARED_STATIC` | Allows sharing static policy functions/predicates across eligible objects | When identical static logic/predicates apply broadly and remain stable |
| `CONTEXT_SENSITIVE` | Monitors declared application contexts and refreshes the policy when relevant context changes | When predicates depend on session context |
| `SHARED_CONTEXT_SENSITIVE` | Shares context-sensitive policies where eligible | When multiple objects share identical context-based policy logic |

Caching details, invalidation, and support conditions must be confirmed for your Oracle version. When unsure, start with `DYNAMIC` by default, measure overhead, and only then optimize with caching policy types.

### 8.1. DYNAMIC

This is the straightforward choice when a policy depends on context. The function is evaluated during parse under dynamic policy semantics. Re-parsed SQL receives a predicate reflecting current context state.

Do not interpret "dynamic" as re-running the function for every row. The policy function generates a predicate; the optimizer embeds that predicate into the SQL plan.

### 8.2. STATIC

Use only when the predicate never changes by session, user, or context. If a static policy returns a session-dependent tenant predicate, predicate caching can break data boundaries.

Static policies require refreshing when underlying logic or referenced data changes as required by Oracle.

### 8.3. CONTEXT_SENSITIVE

Use when the predicate depends on an application context. When creating the policy, declare the namespace and attribute the policy depends on:

```sql
BEGIN
    DBMS_RLS.ADD_POLICY(
        object_schema   => 'APP',
        object_name     => 'ORDERS',
        policy_name     => 'ORDERS_TENANT_CTX_POLICY',
        function_schema => 'SEC',
        policy_function => 'ORDERS_TENANT_PREDICATE',
        statement_types => 'SELECT,INSERT,UPDATE,DELETE',
        update_check    => TRUE,
        enable          => TRUE,
        policy_type     => DBMS_RLS.CONTEXT_SENSITIVE,
        namespace       => 'APP_CTX',
        attribute       => 'TENANT_ID'
    );
END;
/
```

This example replaces the dynamic policy above rather than creating two identical tenant policies on the same table. When using context-sensitive policies, declare every context attribute affecting the predicate and test changing context within the same session.

### 8.4. Refreshing and modifying policies

When modifying the function or needing to refresh policy caches, DBAs can use management procedures such as `DBMS_RLS.REFRESH_POLICY`, `ENABLE_POLICY`, or `DISABLE_POLICY`. Refresh syntax and scope should be checked against your release.

Never edit a policy function and assume all already open cursors immediately use the new predicate. Plan proper invalidation/refresh and verify sessions/cursors after changes.

## 9. Column-level VPD with sec_relevant_cols

VPD can scope enforcement to sensitive columns. For instance, an employee may view general information for all staff while viewing salary only for their own managed group.

When creating the policy, specify:

```sql
sec_relevant_cols => 'SALARY,SSN'
```

When a query references the marked columns, the policy is applied according to column-level rules.

### 9.1. Default behavior

With column-level VPD, when SQL references a sensitive column, the predicate can filter rows to return only rows satisfying the policy. This helps when viewing that column must restrict row visibility as well.

### 9.2. ALL_ROWS

The `DBMS_RLS.ALL_ROWS` option allows returning all rows while sensitive column values are returned as `NULL` for rows not matching the predicate. Example:

```sql
BEGIN
    DBMS_RLS.ADD_POLICY(
        object_schema         => 'HR',
        object_name           => 'EMPLOYEES',
        policy_name           => 'EMP_SALARY_MASK_POLICY',
        function_schema       => 'SEC',
        policy_function       => 'EMP_SALARY_PREDICATE',
        statement_types       => 'SELECT',
        sec_relevant_cols     => 'SALARY',
        sec_relevant_cols_opt => DBMS_RLS.ALL_ROWS
    );
END;
/
```

Illustrative example: users see names and departments of all employees, while `SALARY` holds values only for rows permitted by the predicate. Verify exact version semantics and check whether the application handles SQL `NULL` properly.

### 9.3. Column-level VPD does not replace Data Redaction

- Row-level VPD filters rows via predicates.
- Column-level VPD can filter rows when sensitive columns are queried or return `NULL` for those columns under `ALL_ROWS`.
- Data Redaction masks/transforms column values in results per policy.
- Object privileges govern whether a user may access the object/columns at all.

Choose the technology matching the requirement. If part of a card or ID number must be masked in query output, Data Redaction may fit better; if tenant isolation is required, VPD row predicates are central.

## 10. Multiple policies on the same object

A single table may require multiple rules:
- Tenant isolation.
- Region restriction.
- Department restriction.
- Status-based data restriction.
- Group-specific business conditions.

With multiple policies, understand how Oracle combines predicates and policy groups per configuration. Normally, active policy predicates on an object are combined with logical `AND`. This means rows must satisfy every applied condition.

Example:
- `tenant_id = 10`
- `region_id IN (1,2)`
- `status <> 'RESTRICTED'`

Results contain only rows matching all three predicates.

If business logic requires `OR` semantics or per-application-group policies, design policy groups/driving application contexts per `DBMS_RLS` documentation instead of assuming multiple policies automatically `OR` together.

Never create overlapping or conflicting policies without inspecting the resulting predicate and execution plan.

## 11. Managing policies with DBMS_RLS

Beyond `ADD_POLICY`, the package provides policy lifecycle procedures. Check parameter names and overloads in the exact release documentation.

### 11.1. Disabling a policy

```sql
BEGIN
    DBMS_RLS.DISABLE_POLICY(
        object_schema => 'APP',
        object_name   => 'ORDERS',
        policy_name   => 'ORDERS_TENANT_POLICY'
    );
END;
/
```

Disabling a policy removes its VPD filtering layer. Perform only inside an approved change window. Never use it casually to debug in production.

### 11.2. Enabling a policy

```sql
BEGIN
    DBMS_RLS.ENABLE_POLICY(
        object_schema => 'APP',
        object_name   => 'ORDERS',
        policy_name   => 'ORDERS_TENANT_POLICY'
    );
END;
/
```

After enabling, confirm the policy is enabled and test with an unprivileged user.

### 11.3. Dropping a policy

```sql
BEGIN
    DBMS_RLS.DROP_POLICY(
        object_schema => 'APP',
        object_name   => 'ORDERS',
        policy_name   => 'ORDERS_TENANT_POLICY'
    );
END;
/
```

Dropping a policy removes the protective predicate attached to that object. Before dropping, confirm a replacement policy exists or the removal is explicitly approved.

### 11.4. Refreshing a policy

```sql
BEGIN
    DBMS_RLS.REFRESH_POLICY(
        object_schema => 'APP',
        object_name   => 'ORDERS',
        policy_name   => 'ORDERS_TENANT_POLICY'
    );
END;
/
```

Use refresh when policy/predicate caches need updating within the semantics and limits of the policy type. Do not treat refresh as a substitute for testing cursors or sessions.

## 12. Inspecting VPD metadata

### 12.1. DBA_POLICIES

DBAs can inspect declared policies:

```sql
SELECT object_owner,
       object_name,
       policy_name,
       pf_owner,
       function,
       sel,
       ins,
       upd,
       del,
       enable,
       policy_type
FROM dba_policies
WHERE object_owner = 'APP'
ORDER BY object_name, policy_name;
```

`ALL_POLICIES` or corresponding views can be used without DBA privileges. Column names and visibility depend on version and privileges.

### 12.2. Viewing active predicates

On supported releases, `V$VPD_POLICY` shows policies and predicates applied to cursors:

```sql
SELECT sql_id,
       child_number,
       object_owner,
       object_name,
       policy,
       predicate
FROM v$vpd_policy
WHERE object_owner = 'APP';
```

Reading dynamic performance views requires appropriate privileges. This is a useful diagnostic tool to verify which predicate the policy function returns; never dump sensitive test output into public logs.

### 12.3. Checking current context

```sql
SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV', 'CLIENT_IDENTIFIER') AS client_identifier,
       SYS_CONTEXT('APP_CTX', 'TENANT_ID') AS tenant_id
FROM dual;
```

This checks session state. `CLIENT_IDENTIFIER` assists correlation/auditing but does not by itself prove tenant identity.

## 13. Optimizing VPD performance

VPD appends predicates to SQL. If the predicate is simple and well-indexed, overhead can be minimal. If the policy function is complex or the predicate prevents index usage, cost can be significant.

### 13.1. Indexing for tenant and workload

For example, queries frequently filter by tenant, status, and date:

```sql
SELECT order_id, amount
FROM app.orders
WHERE status = 'OPEN'
  AND order_date >= DATE '2026-01-01';
```

The policy adds the tenant predicate. Evaluate a composite index:

```sql
CREATE INDEX app.orders_tenant_status_date_ix
ON app.orders (tenant_id, status, order_date);
```

Column ordering should be based on selectivity, common predicates, sorting, clustering factor, and DML workload. Do not blindly create indexes just because VPD has `tenant_id`; benchmark on representative data.

### 13.2. Keep predicates sargable

Prefer predicates that can use indexes:

```sql
tenant_id = TO_NUMBER(SYS_CONTEXT('APP_CTX', 'TENANT_ID'))
```

Avoid wrapping the column in unnecessary functions:

```sql
TO_CHAR(tenant_id) = SYS_CONTEXT('APP_CTX', 'TENANT_ID')
```

Applying a function to the table column can prevent the optimizer from using an existing B-tree index unless a matching function-based index exists.

### 13.3. Avoid querying tables inside policy functions on every parse

If the function queries multiple tables to look up tenant/region on each parse, parse overhead rises. You can:
- Place verified attributes into a secure application context.
- Keep policy functions minimal.
- Use a policy type suited to the context.
- Cache reference data safely at the appropriate layer.
- Measure parse rates and shared cursor behavior.

Never cache authorization data in a way that lets revoked permissions remain effective.

### 13.4. Inspecting plans and runtime stats

After attaching a policy, check the execution plan:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

Check:
- Does the VPD predicate appear properly?
- Is the expected index access path used?
- E-Rows and A-Rows.
- Buffer gets and physical reads.
- Parse time and execution time.
- Policy function invocation count per policy type.
- Impact on other queries touching the object.

Compare before/after using identical data and bind/context groups.

## 14. Connection pools and cross-request context leakage risk

Java/JDBC applications commonly reuse database sessions via connection pools. Application contexts belong to the session; when a connection returns to the pool, the context may persist.

This is a severe risk: a tenant A request uses a connection, setting `TENANT_ID=10`, and later the connection is reused for tenant B without resetting context. Without proper reinitialization, B could read A's data or fail under stale context state.

### 14.1. Checkout workflow

1. Borrow connection from pool.
2. Clear old context or initialize session via trusted package.
3. Authenticate request identity at the application tier.
4. Call trusted package to set new context.
5. Run business SQL only after context setup succeeds.
6. If context setup fails, abort the request and run no queries.

### 14.2. Return workflow

- Clear the application context.
- Reset module/action/client identifier if used.
- Reset any other session state modified by the request.
- If clean state cannot be guaranteed, evict the connection from the pool instead of reusing it.

The earlier package includes `clear_for_session`. Applications should invoke it in `finally`/cleanup paths so exceptions are handled too.

### 14.3. Do not rely on cleanup only on success paths

If cleanup runs only when a request succeeds, exceptions or timeouts can leave stale context behind. Guarantee cleanup on every exit branch and enable pool validation mechanisms.

### 14.4. Testing context leakage

Test sequentially on the same physical connection:
1. Request A sets tenant 10 and reads data.
2. Return connection to pool.
3. Request B borrows the same connection and sets tenant 20.
4. Confirm B sees only tenant 20.
5. A subsequent request that skips setting context must be denied/see zero rows.
6. Repeat the test when request A throws an exception mid-flight.

This is mandatory testing for session pooling with VPD.

## 15. VPD and other Oracle security layers

| Mechanism | Primary goal | Relationship to VPD |
|---|---|---|
| Object privileges | Who can access an object/column | Base privilege layer; VPD does not replace it |
| Views | Provide an interface and fixed column/row limits | Can be combined with VPD |
| VPD / DBMS_RLS | Filter rows with dynamic predicates | Suited for tenant/row isolation |
| Column-level VPD | Apply policy when sensitive columns are accessed | Part of VPD |
| Data Redaction | Mask column values in results | Complementary to VPD |
| Oracle Label Security | Classify and control data by labels | Suited for label-based models |
| Database Vault | Control privileged access and realms | Adds administrative protection |
| Real Application Security | Deeper application/database security model for users/sessions/roles | Option for architectures needing rich identity management |

Choose mechanisms per requirement. VPD does not mask data itself; Data Redaction does not replace tenant row filters; Database Vault focuses on privileged access control and realms.

## 16. Bypasses and limitations to understand

VPD is not a barrier against all administrative accounts or physical access paths.

### 16.1. EXEMPT ACCESS POLICY

An account holding the `EXEMPT ACCESS POLICY` system privilege bypasses VPD policies. This privilege is highly sensitive and must never be granted to application accounts or regular users.

Check privileges:

```sql
SELECT grantee, privilege
FROM dba_sys_privs
WHERE privilege = 'EXEMPT ACCESS POLICY'
ORDER BY grantee;
```

Review granted roles and effective privileges under governance policy. Keep only exceptions with documented owners, justification, and auditing.

### 16.2. SYS and administrative accounts

Privileged paths like `SYS`/`SYSDBA` can bypass many SQL-layer protections. Never use `SYS` for applications. Separate administrative accounts, restrict logins, audit usage, and protect credentials.

### 16.3. Non-SQL access paths

VPD controls access via supported SQL operations. It does not replace:
- OS permissions on datafiles/backups.
- RMAN backup and export protection.
- Encryption at rest/in transit.
- Log, trace, and data copy protection.
- Controls over database host administrators.

A DBA can access datafiles or backups through privileged utilities if holding underlying infrastructure access. Defense in depth is essential.

### 16.4. Version and feature checks

Parameters, policy types, column-level options, supported object types, and required privileges must be confirmed against your Oracle Database release/edition. Never copy examples from another environment without testing in staging.

## 17. Common design mistakes

| Mistake | Risk | Fix |
|---|---|---|
| Taking tenant ID straight from request | Users can spoof tenants | Authenticate at trusted tier/package |
| Null context returning `1=1` | Exposes all rows | Fail-closed with `1=0` |
| Using shared account while trusting `SESSION_USER` to distinguish end users | `SESSION_USER` is just the service account | Use proper identity assertions/proxy auth |
| Not resetting context in pool | Cross-request data leakage | Clear and set context on every checkout |
| Attaching `SELECT` policy only | DML can write/modify out of scope | Specify `statement_types` and `update_check` |
| Omitting `update_check` | Unauthorized row insertion/tenant reassignment | Validate new rows on INSERT/UPDATE |
| Policy function concatenating input strings | SQL injection or predicate errors | Use `SYS_CONTEXT` and bind/runtime expressions |
| Using `STATIC` for session-dependent predicates | Cached predicates mismatch user/context | Use dynamic/context-sensitive appropriately |
| Overly complex policy function | Increased parse overhead | Minimize logic and measure |
| Not auditing `EXEMPT ACCESS POLICY` | Users bypass VPD | Review special privileges |
| Testing only through the UI | Other SQL paths may lack protection | Test directly via SQL across multiple principals |
| Ignoring views/procedures/jobs | Unintended access paths may exist | Inventory all consumers/objects |
| Treating VPD as data masking | Sensitive values still visible in permitted rows | Use Data Redaction or column privileges when needed |

## 18. Systematic VPD testing

Do not test only that valid users see expected rows. Also test missing context, spoofed context, context changes, and DML.

### 18.1. Positive tests

- Tenant 10 sees only tenant 10 rows.
- Tenant 20 sees only tenant 20 rows.
- Predicates combined with application filters return accurate results.
- Views and stored procedures continue functioning properly.
- Authorized reports see their intended scope.

### 18.2. Negative tests

- Unset context: zero rows visible.
- Empty context: zero rows visible.
- Invalid tenant ID: rejected or zero rows visible.
- Tenant 10 user accessing tenant 20 order: cannot read.
- Tenant 10 user `UPDATE`/`DELETE` on tenant 20 row: modifies zero rows.
- Tenant 10 user `INSERT` with `tenant_id` 20: rejected when `update_check` is enabled.
- Regular users cannot call APIs to set arbitrary tenants.
- Application users do not hold `EXEMPT ACCESS POLICY`.

### 18.3. Connection pool tests

- Two tenants reuse the same physical connection.
- First request throws an exception before cleanup.
- Connection times out or is aborted mid-request.
- Context changes multiple times in the same session.
- Cleanup fails and connection is evicted from the pool.
- Zero context leaks from prior requests.

### 18.4. Performance tests

Measure:
- Parse time.
- Elapsed and CPU time.
- Buffer gets.
- Execution plans and predicates.
- Policy function invocation counts.
- Performance for small vs. large tenants.
- Performance under high session concurrency.

A tenant owning most of the data may get a different plan from a small tenant. Evaluate data skew and bind/context distribution.

## 19. Step-by-step policy deployment

A controlled rollout sequence:

1. Identify tables, views, and columns containing data to protect.
2. Identify principals and how end users/tenants are authenticated.
3. Design namespaces/attributes and the trusted package.
4. Build a fail-closed policy function.
5. Verify predicates using test contexts.
6. Create the context and grant package privileges.
7. Attach the policy in staging.
8. Test `SELECT`/`INSERT`/`UPDATE`/`DELETE` and pool reuse.
9. Read execution plans, measure overhead, and create appropriate indexes.
10. Review bypass privileges and privileged accounts.
11. Deploy during a change window with rollback ready.
12. Monitor policy errors, performance, and audits post-deployment.

### 19.1. Plan rollback in advance

If a policy must be disabled to restore service, follow an approved procedure with strict operator control. Disabling VPD can immediately widen read/write access.

You can roll back policy code or configuration versions. Never leave a policy disabled outside the incident window; audit the action and confirm re-enabling before closing the incident.

### 19.2. Multi-object rollout

If a tenant key appears across multiple tables, policies are needed on all relevant access paths. One unprotected table can create a join or direct-query path leaking data.

Build an inventory of objects, policy names, function owners, statement types, and enabled status. Check views/materialized views, synonyms, and stored procedures following real application access paths.

## 20. Comprehensive lab example

The example below illustrates the concept with two tenants and a database principal mapped to one tenant. This is a lab exercise requiring suitable schemas/privileges and adjustment per release.

### Step 1. Create the data table

```sql
CREATE TABLE app.orders (
    order_id NUMBER PRIMARY KEY,
    tenant_id NUMBER NOT NULL,
    status VARCHAR2(20) NOT NULL,
    amount NUMBER(12,2) NOT NULL
);

INSERT INTO app.orders VALUES (101, 10, 'OPEN', 250);
INSERT INTO app.orders VALUES (102, 10, 'CLOSED', 400);
INSERT INTO app.orders VALUES (201, 20, 'OPEN', 900);
COMMIT;
```

### Step 2. Create the principal mapping table

```sql
CREATE TABLE sec.db_principal_tenant (
    db_username VARCHAR2(128) PRIMARY KEY,
    tenant_id NUMBER NOT NULL
);

INSERT INTO sec.db_principal_tenant
VALUES ('ORDER_APP_TENANT10', 10);

COMMIT;
```

In this lab, each tenant has a separate database principal. If production uses a shared service account, replace the mapping mechanism with trusted identities/assertions as explained; never accept arbitrary tenant IDs from clients.

### Step 3. Create the context package

```sql
CREATE OR REPLACE PACKAGE sec.app_context_pkg
AUTHID DEFINER
AS
    PROCEDURE set_for_session;
    PROCEDURE clear_for_session;
END;
/
```

```sql
CREATE OR REPLACE PACKAGE BODY sec.app_context_pkg
AS
    PROCEDURE set_for_session
    IS
        l_tenant_id sec.db_principal_tenant.tenant_id%TYPE;
    BEGIN
        SELECT tenant_id
        INTO l_tenant_id
        FROM sec.db_principal_tenant
        WHERE db_username = SYS_CONTEXT('USERENV', 'SESSION_USER');

        DBMS_SESSION.SET_CONTEXT(
            'APP_CTX',
            'TENANT_ID',
            TO_CHAR(l_tenant_id)
        );
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            DBMS_SESSION.CLEAR_CONTEXT('APP_CTX', NULL, NULL);
            RAISE_APPLICATION_ERROR(-20001, 'No tenant mapping');
    END;

    PROCEDURE clear_for_session
    IS
    BEGIN
        DBMS_SESSION.CLEAR_CONTEXT('APP_CTX', NULL, NULL);
    END;
END;
/
```

### Step 4. Create the secure application context

```sql
CREATE CONTEXT app_ctx USING sec.app_context_pkg;
```

### Step 5. Create the policy function

```sql
CREATE OR REPLACE FUNCTION sec.orders_tenant_predicate(
    object_schema IN VARCHAR2,
    object_name IN VARCHAR2
)
RETURN VARCHAR2
AUTHID DEFINER
AS
BEGIN
    IF SYS_CONTEXT('APP_CTX', 'TENANT_ID') IS NULL THEN
        RETURN '1=0';
    END IF;

    RETURN
        'tenant_id = TO_NUMBER(SYS_CONTEXT(''APP_CTX'', ''TENANT_ID''))';
END;
/
```

### Step 6. Attach the policy

```sql
BEGIN
    DBMS_RLS.ADD_POLICY(
        object_schema   => 'APP',
        object_name     => 'ORDERS',
        policy_name     => 'ORDERS_TENANT_POLICY',
        function_schema => 'SEC',
        policy_function => 'ORDERS_TENANT_PREDICATE',
        statement_types => 'SELECT,INSERT,UPDATE,DELETE',
        update_check    => TRUE,
        enable          => TRUE
    );
END;
/
```

### Step 7. Grant package and object privileges per lab model

```sql
GRANT EXECUTE ON sec.app_context_pkg TO order_app_tenant10;
GRANT SELECT, INSERT, UPDATE, DELETE ON app.orders TO order_app_tenant10;
```

Do not grant `EXEMPT ACCESS POLICY` to application accounts.

### Step 8. Set context before querying

Log in using the mapped principal:

```sql
BEGIN
    sec.app_context_pkg.set_for_session;
END;
/
```

Verify context:

```sql
SELECT SYS_CONTEXT('APP_CTX', 'TENANT_ID')
FROM dual;
```

Query:

```sql
SELECT order_id, tenant_id, status, amount
FROM app.orders
ORDER BY order_id;
```

Only tenant 10 rows are returned via the policy.

### Step 9. Test DML

Attempt to insert a row for another tenant:

```sql
INSERT INTO app.orders (order_id, tenant_id, status, amount)
VALUES (301, 20, 'OPEN', 100);
```

With the policy and update check properly configured, the operation must be rejected because the new row violates the tenant predicate. Check the exact Oracle error on your running release.

### Step 10. Check metadata and execution plan

```sql
SELECT object_owner,
       object_name,
       policy_name,
       enable,
       policy_type
FROM dba_policies
WHERE object_owner = 'APP'
  AND object_name = 'ORDERS';
```

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

### Step 11. Clear context before returning connection

```sql
BEGIN
    sec.app_context_pkg.clear_for_session;
END;
/
```

In pooled applications, invoke cleanup on every request exit path and evict connections from the pool if clean state cannot be guaranteed.

### Step 12. Clean up the lab

Drop only objects you created and when no longer needed:

```sql
BEGIN
    DBMS_RLS.DROP_POLICY(
        object_schema => 'APP',
        object_name => 'ORDERS',
        policy_name => 'ORDERS_TENANT_POLICY'
    );
END;
/
```

Afterward, you can drop the tables, function, package, and context according to dependencies, privileges, and lab policy. Never run cleanup DDL on production business objects.

## 21. VPD operations checklist

### Identity and context
- Tenant/user source is authenticated.
- Clients cannot set arbitrary tenants.
- Context is a secure application context.
- Missing or invalid context fails closed.
- Context is set before any business SQL runs.
- Context is cleared/reset in connection pools.

### Policy
- Correct object and schema.
- Correct statement types.
- `update_check` enabled for DML requiring protection.
- Policy type matches context/caching needs.
- Policy function is simple and never concatenates untrusted input.
- Column-level options tested if used.
- Policy enabled after deployment.

### Privileges and bypasses
- Application accounts lack `EXEMPT ACCESS POLICY`.
- `SYS`/`SYSDBA` separated from application workloads.
- Object and package privileges minimized.
- All objects/views/procedures/jobs with access paths reviewed.

### Performance and monitoring
- Predicates can use appropriate indexes.
- Before/after baselines established.
- Execution plans and VPD predicates verified.
- Small/large tenants and concurrency measured.
- Auditing/alerts configured for policy changes and bypass privileges.
- Approved rollback plan ready and re-enabling verified.

## 22. Self-check questions

**Question 1.** What is Virtual Private Database?

**Answer:** An Oracle mechanism that automatically applies security predicates to SQL accessing policy-protected objects, commonly used to restrict rows by user, tenant, or context.

**Question 2.** What is `DBMS_RLS` used for?

**Answer:** Managing VPD policies, attaching policy functions to tables/views, and enabling, disabling, refreshing, or dropping policies.

**Question 3.** What is an application context?

**Answer:** A set of session attributes stored under a namespace/attribute and read via `SYS_CONTEXT`.

**Question 4.** Why use a secure application context?

**Answer:** Only the designated trusted package can set the context, controlling the origin of security attributes.

**Question 5.** Why not take the tenant ID directly from the request?

**Answer:** Clients could spoof tenant IDs and access out-of-scope data if the package does not authenticate identity.

**Question 6.** What does a policy function return?

**Answer:** A SQL predicate string that Oracle applies to statements accessing the object.

**Question 7.** Why should missing context return `1=0`?

**Answer:** It is fail-closed: without valid context, zero rows are returned.

**Question 8.** What does `update_check => TRUE` mean?

**Answer:** Oracle verifies whether new rows after INSERT/UPDATE satisfy the policy predicate, preventing out-of-scope writes.

**Question 9.** How do `DYNAMIC` and `STATIC` policies differ?

**Answer:** Dynamic evaluates the function during parse lifecycles; Static caches the predicate when it truly does not depend on session/context.

**Question 10.** When should `CONTEXT_SENSITIVE` be considered?

**Answer:** When the predicate depends on an application context and the policy should refresh when relevant context changes.

**Question 11.** What is `sec_relevant_cols` used for?

**Answer:** Specifying sensitive columns to trigger column-level VPD when statements reference those columns.

**Question 12.** What does `DBMS_RLS.ALL_ROWS` do?

**Answer:** Allows returning all rows while sensitive column values are returned as `NULL` for rows not satisfying the predicate under column-level VPD semantics.

**Question 13.** Does VPD replace object privileges?

**Answer:** No. Users still need object access privileges; VPD restricts rows after the base privilege layer.

**Question 14.** Why must connection pools reset context?

**Answer:** Context belongs to the session and can persist when connections are reused, leaking data across requests/tenants.

**Question 15.** What risk does `EXEMPT ACCESS POLICY` pose?

**Answer:** This privilege allows bypassing VPD policies and must be restricted to controlled privileged accounts.

**Question 16.** Is VPD data masking?

**Answer:** No. VPD primarily filters rows; Data Redaction handles masking column values in results.

**Question 17.** Why test `INSERT`/`UPDATE` in addition to `SELECT`?

**Answer:** Filtering reads without validating new rows allows users to write or reassign data to other tenants.

**Question 18.** How can you verify a policy is actually applied?

**Answer:** Check policy metadata, session context, predicates via diagnostic views when supported, and execution plans with `DBMS_XPLAN`.

## 23. Conclusion

Virtual Private Database provides row-level security inside the database by attaching policy functions to tables or views. Application contexts hold session security attributes; `DBMS_RLS` manages policies; Oracle automatically applies predicates when executing statements within policy scope. This protects data even when multiple applications or SQL paths access the same object.

Security depends on context provenance. Context must be set by a trusted package after identity authentication; never accept arbitrary tenant IDs from clients. When context is missing, policies must fail closed. For DML, declare statement types and consider `update_check` to block out-of-scope inserts or updates. Column-level VPD can help guard sensitive columns, but must be distinguished from Data Redaction.

In connection pool environments, context must be set for each request and cleared before reusing connections. Policy types, caching, predicates, and indexes should be measured on real workloads. Audit `EXEMPT ACCESS POLICY`, `SYS`/`SYSDBA`, and all privileged access paths because VPD does not replace infrastructure security. Deploy only after testing cross-tenant isolation, DML, context leakage, execution plans, and rollback procedures.
