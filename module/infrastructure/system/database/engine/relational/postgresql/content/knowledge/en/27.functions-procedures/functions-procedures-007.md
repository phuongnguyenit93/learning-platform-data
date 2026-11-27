# SECURITY INVOKER, SECURITY DEFINER, and Safe search_path in PostgreSQL

## 1. Why can a small function become a database security boundary?

Imagine an application with a `customers` table holding credit limits, emails, and internal data. Application users do not have direct `SELECT` privileges on this table, yet they are allowed to call a function to retrieve the **approved credit limit** for a customer within their authorized scope.

PostgreSQL provides two primary mechanisms to determine **whose privileges** are used when executing a function or procedure:

- `SECURITY INVOKER`: executes with the privileges of the **calling user**; this is the default.
- `SECURITY DEFINER`: executes with the privileges of the **function/procedure owner** within that object's execution scope.

`SECURITY DEFINER` is valuable for granting controlled access through a database API. However, a definer function containing an unqualified `SELECT ... FROM customers`—or calling another function without schema qualification—can have its **meaning altered by `search_path`**. If an untrusted object takes precedence during name resolution, elevated-privilege code can end up accessing the wrong table, function, or operator.

```text
                       Application / calling role
                                |
                          GRANT EXECUTE
                                |
                  +-------------+-------------+
                  |                           |
            SECURITY INVOKER           SECURITY DEFINER
                  |                           |
          Caller's privileges         Function owner's privileges
                  |                           |
           Direct SELECT?           Permitted actions only
                  |                           |
                  +-------------+-------------+
                                |
                      Object name resolution
                         via search_path
                                |
           +--------------------+-------------------+
           |                                        |
      Unsafe path                              Safe path
  attacker schema / pg_temp           pg_catalog, trusted, pg_temp
           |                                        |
   Can shadow objects                  Controlled object lookup
           |                                        |
  Risk of data leak/corruption        Least-privilege routine API
```

**Core challenge:** grant enough privileges for the application to do its job, **without letting callers choose which objects are accessed under the function's privileges**.

> **Golden rule:** `SECURITY DEFINER` is a privilege boundary. Use a least-privilege owner role, schema-qualify trusted objects, set a safe `SET search_path` directly in the function definition, revoke default `EXECUTE` from `PUBLIC`, and validate authorization and business logic on every input.

## 2. Learning objectives

After this lesson, you can:

1. Distinguish login roles, effective roles, routine owners, and table privileges.
2. Understand `CURRENT_USER`, `SESSION_USER`, `SET ROLE`, privilege inheritance, and role memberships as needed.
3. Explain why default `SECURITY INVOKER` requires caller privileges on the objects accessed by a function.
4. Explain how `SECURITY DEFINER` enables controlled operations without granting direct table access to callers.
5. Distinguish schema `USAGE`, routine `EXECUTE`, and table `SELECT/UPDATE` privileges.
6. Read and set `search_path`; distinguish `current_schema()` and `current_schemas(true)`.
7. Understand why `pg_catalog` and `pg_temp` are especially critical in definer functions.
8. Identify schema shadowing, temporary-table shadowing, and function/operator name hijacking.
9. Write safe `CREATE FUNCTION ... SECURITY DEFINER SET search_path = ...` definitions.
10. Write queries inside routines using explicit schema-qualified table and object names.
11. Revoke `EXECUTE` from `PUBLIC` without leaving an accidental privilege-exposure window.
12. Use dedicated least-privilege `NOLOGIN` owner roles.
13. Analyze Row-Level Security (RLS) effects when running under a definer owner.
14. Design dynamic SQL with `format('%I', ...)` and `EXECUTE ... USING`, while still enforcing authorization.
15. Distinguish functions and procedures, particularly transaction-control restrictions in `SECURITY DEFINER` procedures.
16. Write tests for permissions, search-path shadowing, tenant isolation, and negative cases.
17. Inventory routines with `prosecdef`, `proconfig`, and effective privileges using system catalogs.
18. Structure migrations, logging, and operations for privileged routines with minimal risk.

## 3. Privilege model: who calls, who owns, who gets EXECUTE?

Key participants:

| Component | Example | Effect |
| --- | --- | --- |
| Login role | `app_login` | Role that opened the PostgreSQL connection |
| Effective role | After `SET ROLE app_reader` | Role currently used for most privilege checks |
| Routine owner | `sec348_owner` | Owner of the function or procedure |
| Routine caller | `sec348_reader` | Principal requesting routine execution |
| Data owner | `sec348_owner` or another role | Holds privileges on tables accessed by the routine |
| Schema owner | `sec348_owner` | Manages objects inside the schema |
| `PUBLIC` | Special pseudo-role | Represents all roles for applicable `GRANT`s |
| `pg_temp` | Session temporary schema | Participates in name resolution |

A connection can run `SET ROLE` to switch its effective role, though doing so does not change every session attribute into a fresh login user.

### 3.1. `CURRENT_USER`

`CURRENT_USER` returns the effective role used for permission checks and name resolution where evaluated. Inside a `SECURITY DEFINER` function, it reflects **the function's owner** for the duration of the definer execution context.

### 3.2. `SESSION_USER`

`SESSION_USER` is typically the role established at session login (changeable only by permitted administrative actions) and **does not automatically change when a client runs `SET ROLE`**.

### 3.3. `CURRENT_ROLE`

In PostgreSQL, `CURRENT_ROLE` is generally equivalent to `CURRENT_USER`. Do not rely on it as the "original caller" inside a definer routine.

### 3.4. `SET ROLE` and testing

```sql
SELECT
    current_user,
    session_user,
    current_role;

-- In a session with privileges to switch roles:
SET ROLE some_app_role;

SELECT current_user, session_user, current_role;

RESET ROLE;
```

After `SET ROLE`, `current_user` switches to the chosen role, while `session_user` typically remains the original login role.

**Important consequence:** authorization checks relying on `SESSION_USER` cannot be fully simulated via `SET ROLE` assuming `session_user` changed. To accurately test a "one DB login per user" model, connect using actual distinct login connections.

## 4. SECURITY INVOKER is the default

An SQL function declared as:

```sql
CREATE FUNCTION sample_read()
RETURNS integer
LANGUAGE sql
AS $body$
    SELECT 1
$body$;
```

behaves by default as:

```sql
CREATE FUNCTION sample_read()
RETURNS integer
LANGUAGE sql
SECURITY INVOKER
AS $body$
    SELECT 1
$body$;
```

If an invoker function accesses a table, the caller needs appropriate privileges on that table, unless another view or routine along the call chain provides its own security context.

### 4.1. When should you use INVOKER?

- String, numeric, or date transformations requiring no extra privileges.
- Calculation or validation helpers operating on data the caller is already permitted to access.
- Queries that should respect the caller's direct privileges and RLS policies.
- Whenever there is no business reason for the routine to elevate privileges.

### 4.2. Privileges still required to call a function

Holding `EXECUTE` on a routine does **not** grant the caller:

- `USAGE` on schemas containing objects referenced from application SQL.
- `SELECT` on restricted tables.
- Permission to arbitrarily `CREATE` functions or schemas.
- Permission to switch roles or bypass RLS.

Always distinguish **permission to invoke a routine** from **permissions inside the routine**.

### 4.3. INVOKER does not make a query automatically safe

An invoker function using dynamic SQL with unsafe string concatenation can still suffer SQL injection under the caller's privileges, corrupting or leaking anything the caller can access. Parameterization and input validation are still essential.

## 5. SECURITY DEFINER: using owner privileges for controlled execution

Typical goals:

- Callers lack direct `SELECT` on financial tables.
- Callers may only call an API returning specific approved fields.
- The API runs under an owner role with read access strictly to required tables.
- The function enforces business conditions so callers cannot query arbitrary tenants.

With `SECURITY DEFINER`:

```sql
CREATE FUNCTION some_schema.some_api(...)
RETURNS ...
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, some_schema, pg_temp
AS $body$
BEGIN
    -- Validate inputs and authorization conditions.
    -- Operate only on permitted objects.
END
$body$;
```

### 5.1. The owner must not be a superuser

A common mistake is creating definer functions owned by a superuser or a `BYPASSRLS` role just "for convenience."

If the logic is ever abused, the owner's privileges define the blast radius.

**Use a dedicated `NOLOGIN` owner role** granted strictly the minimum privileges needed by the function—such as reading one table or updating a tightly scoped set of rows.

### 5.2. SECURITY DEFINER does not know who may view which customer

If a routine runs:

```sql
SELECT credit_limit
FROM private_customers
WHERE customer_id = p_id;
```

and any caller can pass any `p_id`, it becomes an oracle exposing other users' data.

Elevating execution privileges **never replaces business authorization checks**. Tenant/user scoping and ownership mappings must be verified from a trusted source.

### 5.3. Privileges across nested call chains

An invoker helper called from a definer function runs under the active definer effective role. Another helper marked `SECURITY DEFINER` switches to its own owner.

Never assume privileges depend only on the top-level caller/owner pair; audit the entire call chain and all elevated routines.

## 6. Multi-role lab: preparing the test environment

Creating roles and schemas requires administrative privileges. **Run only in a test database.** Never copy `GRANT`/`REVOKE` scripts to production without a reviewed plan.

Use three roles:

- `sec348_owner`: `NOLOGIN`, owns tables and privileged functions.
- `sec348_reader`: `NOLOGIN`, represents callers granted only API `EXECUTE`.
- `sec348_other`: `NOLOGIN`, represents roles denied access to restricted APIs.

In the lab, a DBA or suitably privileged role runs:

```sql
CREATE ROLE sec348_owner NOLOGIN;
CREATE ROLE sec348_reader NOLOGIN;
CREATE ROLE sec348_other NOLOGIN;

CREATE SCHEMA sec348 AUTHORIZATION sec348_owner;

REVOKE ALL ON SCHEMA sec348 FROM PUBLIC;
GRANT USAGE ON SCHEMA sec348 TO sec348_reader;
GRANT USAGE ON SCHEMA sec348 TO sec348_other;
```

### 6.1. Why give reader USAGE but not CREATE?

`USAGE` permits looking up objects inside a schema where allowed. It **does not grant permission to create objects**.

Never run:

```sql
GRANT CREATE ON SCHEMA sec348 TO sec348_reader;
```

when that schema holds objects that definer functions will resolve.

### 6.2. Creating the table as owner

In an administrative session permitted to `SET ROLE sec348_owner`:

```sql
SET ROLE sec348_owner;

CREATE TABLE sec348.customers (
    tenant_id integer NOT NULL,
    customer_id integer NOT NULL,
    full_name text NOT NULL,
    credit_limit numeric(12,2) NOT NULL,
    PRIMARY KEY (tenant_id, customer_id)
);

INSERT INTO sec348.customers
    (tenant_id, customer_id, full_name, credit_limit)
VALUES
    (10, 1, 'Tenant 10 - Customer 1', 1000.00),
    (10, 2, 'Tenant 10 - Customer 2', 2500.00),
    (20, 1, 'Tenant 20 - Customer 1', 9000.00);

RESET ROLE;
```

If the admin login is not a superuser, it must hold membership permitting `SET ROLE sec348_owner` under your PostgreSQL version's role-administration rules.

### 6.3. Do not grant table read rights to reader

In this lab, `sec348_owner` owns the table; `sec348_reader` has no `SELECT` privilege.

Verify:

```sql
SELECT
    has_table_privilege(
        'sec348_reader',
        'sec348.customers',
        'SELECT'
    ) AS reader_can_select,
    has_schema_privilege(
        'sec348_reader',
        'sec348',
        'USAGE'
    ) AS reader_schema_usage;
```

Expected in a clean lab:

- `reader_can_select = false`.
- `reader_schema_usage = true`.

If your database has pre-existing role memberships or grants outside the lab, results may differ; verify against the actual environment.

## 7. SECURITY INVOKER demo: caller cannot read the restricted table

Create an invoker routine as owner:

```sql
SET ROLE sec348_owner;

BEGIN;

CREATE FUNCTION sec348.invoker_limit(
    p_customer_id integer
)
RETURNS numeric
LANGUAGE sql
SECURITY INVOKER
SET search_path = pg_catalog, sec348, pg_temp
AS $fn$
    SELECT c.credit_limit
    FROM sec348.customers AS c
    WHERE c.tenant_id = 10
      AND c.customer_id = p_customer_id
$fn$;

REVOKE ALL ON FUNCTION sec348.invoker_limit(integer)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION sec348.invoker_limit(integer)
TO sec348_reader;

COMMIT;

RESET ROLE;
```

### 7.1. Testing as caller

In an admin session able to `SET ROLE`:

```sql
SET ROLE sec348_reader;

SELECT current_user, session_user;

SELECT sec348.invoker_limit(1);

RESET ROLE;
```

Because `sec348_reader` holds `USAGE` on the schema and `EXECUTE` on the function yet **lacks `SELECT` on `sec348.customers`**, the call fails with `permission denied for table customers`.

This is the **expected behavior** demonstrating `SECURITY INVOKER`.

If an error occurs inside an explicit transaction, issue `ROLLBACK` before running further statements in that transaction.

### 7.2. What changes if SELECT is granted?

```sql
GRANT SELECT ON sec348.customers TO sec348_reader;
```

Once reader has direct `SELECT`, the invoker function succeeds under caller privileges. Because that defeats our owner-only table model, **do not run this GRANT** if you want to keep the table restricted.

### 7.3. Why is default INVOKER usually the right choice?

Whenever callers are already authorized to read the underlying tables under grants and RLS, invoker functions avoid unnecessary privilege elevation. Consider definer only when a clear access-control boundary demands it.

## 8. SECURITY DEFINER demo: caller invokes only a restricted API

Create a definer function returning **one** limit for tenant 10:

```sql
SET ROLE sec348_owner;

BEGIN;

CREATE FUNCTION sec348.definer_limit(
    p_customer_id integer
)
RETURNS numeric
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, sec348, pg_temp
AS $fn$
    SELECT c.credit_limit
    FROM sec348.customers AS c
    WHERE c.tenant_id = 10
      AND c.customer_id = p_customer_id
$fn$;

REVOKE ALL ON FUNCTION sec348.definer_limit(integer)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION sec348.definer_limit(integer)
TO sec348_reader;

COMMIT;

RESET ROLE;
```

### 8.1. Testing as reader

```sql
SET ROLE sec348_reader;

SELECT sec348.definer_limit(1) AS allowed_limit;

RESET ROLE;
```

With the lab schema, data, and grants above, the expected result is `1000.00`.

Reader **cannot `SELECT` the table**, yet holds `EXECUTE` on an owner-defined API.

### 8.2. Why isn't this API a general multi-tenant model yet?

The function hardcodes:

```sql
WHERE c.tenant_id = 10
```

to keep the privilege check easy to verify. To serve multiple tenants, you need a **trusted mechanism** identifying which tenant the caller is authorized to access.

Never change it to:

```sql
WHERE c.tenant_id = p_tenant_id
```

and let any caller pass arbitrary `p_tenant_id` without verification. That turns the function into a **universal limit reader across all tenants**.

### 8.3. What EXECUTE grants

Reader is permitted to run **strictly the logic inside the function**, never becoming the owner for the rest of the session after the function returns.

PostgreSQL scopes the owner privilege context to routine execution; once the call finishes, the caller returns to its outer context.

### 8.4. INVOKER vs. DEFINER does not change row counts when authorized

Both functions return the exact same value when the caller holds sufficient rights. The difference lies purely in **whose identity is checked for permissions** when accessing tables.

## 9. `CURRENT_USER` inside INVOKER and DEFINER

Create two identity-inspecting functions:

```sql
SET ROLE sec348_owner;

BEGIN;

CREATE FUNCTION sec348.who_invokes()
RETURNS name
LANGUAGE sql
SECURITY INVOKER
AS $fn$
    SELECT current_user
$fn$;

CREATE FUNCTION sec348.who_defines()
RETURNS name
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, sec348, pg_temp
AS $fn$
    SELECT current_user
$fn$;

REVOKE ALL ON FUNCTION sec348.who_invokes()
FROM PUBLIC;

REVOKE ALL ON FUNCTION sec348.who_defines()
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION sec348.who_invokes()
TO sec348_reader;

GRANT EXECUTE ON FUNCTION sec348.who_defines()
TO sec348_reader;

COMMIT;

RESET ROLE;
```

Test:

```sql
SET ROLE sec348_reader;

SELECT
    current_user AS caller_now,
    session_user AS session_login,
    sec348.who_invokes() AS invoker_sees,
    sec348.who_defines() AS definer_sees;

RESET ROLE;
```

Expected in the lab:

| Expression | Typical value |
| --- | --- |
| Outer `current_user` | `sec348_reader` |
| Outer `session_user` | Connection's actual login, not necessarily reader |
| `who_invokes()` | `sec348_reader` |
| `who_defines()` | `sec348_owner` |

### 9.1. Do not use CURRENT_USER inside a definer to identify the caller

Dangerous pattern:

```sql
-- Inside SECURITY DEFINER:
SELECT current_user;
```

It returns the owner, not the external caller. If you need the caller's identity, obtain it from an **unforgeable** source while accounting for session, proxy, and connection-pool trust boundaries.

### 9.2. SESSION_USER does not solve application user authentication

If all web users share one database login, `SESSION_USER` is always that shared login, offering no distinction among thousands of end users.

A definer function cannot rely solely on `SESSION_USER` to identify web users when connection pooling uses a shared role. Use a properly protected authorization context across the application and database layers.

## 10. Three privilege layers to check together

Calling `sec348.definer_limit(1)` involves:

1. Database `CONNECT` privilege.
2. Schema `USAGE` on `sec348` and `EXECUTE` on the function.
3. Inside-routine privileges to access `sec348.customers`.

### 10.1. Checking schema and routine privileges

```sql
SELECT
    has_schema_privilege(
        'sec348_reader',
        'sec348',
        'USAGE'
    ) AS schema_usage,
    has_function_privilege(
        'sec348_reader',
        'sec348.definer_limit(integer)',
        'EXECUTE'
    ) AS can_execute,
    has_table_privilege(
        'sec348_reader',
        'sec348.customers',
        'SELECT'
    ) AS can_select_table;
```

Expected:

```text
schema_usage     = true
can_execute      = true
can_select_table = false
```

### 10.2. Why checking EXECUTE alone isn't enough

A role might have `EXECUTE` yet lack schema `USAGE`. Or it might have `USAGE` and `EXECUTE` on an invoker routine while lacking underlying table rights.

Never conclude "the function is broken" before checking which privilege layer is missing.

### 10.3. Schema CREATE is dangerous alongside definer routines

If a caller holds `CREATE` on a schema searched **ahead of trusted objects**, they can create confusingly named functions, operators, or tables.

Even without `SELECT` on the real table, a definer function relying on unqualified names can be hijacked by caller-created objects.

## 11. What is `search_path`?

`search_path` is the ordered list of schemas PostgreSQL searches when resolving unqualified object names.

Inspect:

```sql
SHOW search_path;

SELECT
    current_schema() AS first_usable_schema,
    current_schemas(true) AS effective_schema_list;
```

Suppose:

```sql
SET search_path = app, public;
```

then a query:

```sql
SELECT *
FROM customers;
```

resolves to `app.customers` if a matching visible object exists there.

Whereas:

```sql
SELECT *
FROM sec348.customers;
```

explicitly specifies `sec348`, independent of whether `sec348` appears first in `search_path`.

### 11.1. search_path applies to more than tables

It also governs unqualified names of:

- Functions and procedures.
- Operators.
- Types.
- Sequences.
- Other schema-scoped objects depending on SQL syntax.

Therefore, qualifying table names alone is insufficient if the routine also invokes unqualified functions or operators.

### 11.2. search_path is a resolution rule, not a GRANT

Having a schema in `search_path` **never grants `SELECT` or `EXECUTE`** on its objects.

Conversely, even if a schema is absent from `search_path`, a caller with proper privileges can always access objects using fully qualified names.

### 11.3. Session-level path changes

```sql
SET search_path = sec348, public;

SHOW search_path;

RESET search_path;
```

Connection pools reuse sessions across requests. If session state isn't reset cleanly, a `search_path` left over from one request affects subsequent queries.

That is why definer functions must **pin `SET search_path` directly in their own definitions**.

## 12. `pg_catalog`: prioritizing built-in objects

`pg_catalog` houses PostgreSQL's built-in functions, operators, types, and system catalogs.

When `pg_catalog` is **not listed explicitly** in `search_path`, PostgreSQL searches it implicitly ahead of listed schemas for eligible object lookups.

When **listed explicitly**, `pg_catalog`'s position in `search_path` controls lookup priority.

### 12.1. Dangerous configuration

```sql
SET search_path = untrusted_schema, pg_catalog;
```

Here, a schema where users can create objects is searched **before** `pg_catalog` for eligible lookups, opening shadowing attacks.

### 12.2. Safer, controllable configuration

```sql
SET search_path = pg_catalog, sec348, pg_temp;
```

This ordering reflects clear intent:

1. PostgreSQL built-in objects.
2. Trusted application schema.
3. Session temporary namespace, placed last.

Definer functions should still **fully qualify** sensitive tables and routines rather than relying solely on path order.

### 12.3. Fully qualified names

```sql
SELECT pg_catalog.current_user;
```

You don't need to schema-qualify every built-in in ordinary code, yet in security-critical functions, qualifying key calls and pinning `pg_catalog` ahead of untrusted schemas greatly reduces resolution hijacking risk.

### 12.4. Operators can also be shadowed

Even everyday operators are resolved via `search_path`. To schema-qualify an operator explicitly:

```sql
SELECT 1 OPERATOR(pg_catalog.+) 2;
```

In normal code, qualifying every operator is unnecessary once `search_path` contains only trusted schemas. The `OPERATOR(schema.operator)` syntax helps illustrate why custom operators are part of the attack surface.

## 13. `pg_temp`: an easy-to-miss pitfall

PostgreSQL creates a per-session temporary schema (internally e.g. `pg_temp_NNN`).

A critical rule:

> If `pg_temp` is omitted from `search_path`, it is searched implicitly **ahead** of all listed schemas when resolving **relation names and type names**.

That means setting:

```sql
SET search_path = sec348;
```

is **not sufficient** to guarantee unqualified table names inside a definer function resolve to `sec348.table`.

### 13.1. How to place pg_temp

```sql
SET search_path = pg_catalog, sec348, pg_temp;
```

With `pg_temp` placed explicitly at the end, matching tables in `sec348` are resolved ahead of temporary tables.

### 13.2. `pg_temp` is not searched identically for functions/operators

The temporary schema is searched implicitly for **relation and type names**, not in the same way for unqualified function or operator names.

Distinguish two risks:

- Temporary-table shadowing: primary risk via relations and types.
- Function/operator hijacking: typically via **another schema in `search_path` where an attacker holds `CREATE`**.

### 13.3. Checking the effective path

```sql
SHOW search_path;

SELECT current_schemas(true);
```

`SHOW` prints the setting string, whereas `current_schemas(true)` shows the effective list including implicit schemas in resolution order.

### 13.4. Temporary tables are session-scoped

Temporary tables are not visible database-wide to other backends.

However, **the very session calling your definer function** can create a temporary object (if its role holds `TEMP` privilege) and invoke the function on the same connection—making shadowing a real threat.

## 14. Risk of misplacing pg_temp

Consider this function (**unsafe** pattern, for illustration only):

```sql
CREATE FUNCTION sec348.unsafe_limit(
    p_customer_id integer
)
RETURNS numeric
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = sec348
AS $fn$
DECLARE
    v_limit numeric;
BEGIN
    SELECT credit_limit
      INTO v_limit
    FROM customers
    WHERE tenant_id = 10
      AND customer_id = p_customer_id;

    RETURN v_limit;
END
$fn$;
```

Two flaws:

1. `FROM customers` is **not schema-qualified**.
2. `SET search_path = sec348` **omits `pg_temp` at the end**.

### 14.1. Concerning scenario

If the caller holds `TEMP` privilege, they can create a temporary table named `customers` before invoking the function. Depending on lookup, plan caching, and permissions, the unqualified relation name can resolve to the temporary table instead of the owner's table.

Potential consequences:

- The function reads unintended data.
- Logic breaks or returns forged values.
- Permission or type errors occur.
- Multi-step privileged code runs off attacker-controlled table data.

**Do not claim every temp-table creation lets an attacker steal table rows:** actual impact depends on permissions on the temp table, plan caching timing, and routine code. Regardless, letting a definer routine resolve the wrong relation is a security design flaw.

### 14.2. Creating a temporary object in the lab

In a session with `TEMP` privilege:

```sql
CREATE TEMP TABLE customers (
    tenant_id integer,
    customer_id integer,
    credit_limit numeric(12,2)
);

INSERT INTO customers
    (tenant_id, customer_id, credit_limit)
VALUES (10, 1, 999999.00);
```

**Shadowing illustration only:** never deploy `unsafe_limit` in production. A definer function querying unqualified `customers` without `pg_temp` pinned last is a dangerous pattern.

### 14.3. Defenses

- Pin `SET search_path = pg_catalog, sec348, pg_temp` in the function definition.
- Explicitly qualify sensitive tables as `sec348.customers`.
- Keep untrusted `CREATE`-enabled schemas out of `search_path`.
- Use a least-privilege owner role.
- Revoke `EXECUTE` from `PUBLIC`.
- Test scenarios where callers create same-named temp tables.

### 14.4. Do not rely on setting search_path on the caller side

```sql
SET search_path = sec348;
```

in the application is a session setting that can be mutated or leaked across pooled connections. Definer functions must **lock down their own resolution environment**.

## 15. Writing safe functions: routine-level SET search_path

Safe definition pattern:

```sql
CREATE FUNCTION sec348.safe_example(
    p_customer_id integer
)
RETURNS numeric
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, sec348, pg_temp
AS $fn$
    SELECT c.credit_limit
    FROM sec348.customers AS c
    WHERE c.tenant_id = 10
      AND c.customer_id = p_customer_id
$fn$;
```

This provides defense in depth:

1. **Qualified table reference:** `sec348.customers`.
2. **Routine-pinned search path:** `pg_catalog, sec348, pg_temp`.

### 15.1. Why use both?

Schema-qualified relation names prevent table shadowing.

Yet SQL/PL/pgSQL bodies may still contain:

- Unqualified function calls.
- Types or operators.
- Object names inside dynamic SQL.
- Helper routines or references added in future edits.

A safe `SET search_path` establishes a hardened baseline across the entire routine body.

### 15.2. Only include trusted schemas in the path

`SET search_path = pg_catalog, sec348, pg_temp` is only safe when **`sec348` genuinely forbids untrusted users from creating or altering objects**.

If `sec348_reader` held `CREATE` on `sec348`, `sec348` would no longer be trusted.

### 15.3. Using only `pg_catalog, pg_temp`

If a function fully qualifies **every application object**, an even tighter setting is:

```sql
SET search_path = pg_catalog, pg_temp
```

Then every non-built-in table, type, and function must include an explicit schema name. Pick the minimal path that stays maintainable.

### 15.4. Never include `public` out of habit

If untrusted users can create objects in `public`, it must never appear in a definer function's `search_path`.

While newer PostgreSQL versions revoke `CREATE` on `public` from `PUBLIC` on fresh databases, upgraded or customized databases may still grant it. **Verify actual ACLs**, never assume from server version.

## 16. Why is schema qualification more important than tidy aliases?

Compare:

```sql
-- Hard to control if search_path changes:
SELECT credit_limit
FROM customers
WHERE customer_id = p_customer_id;
```

with:

```sql
-- Clear target object:
SELECT c.credit_limit
FROM sec348.customers AS c
WHERE c.customer_id = p_customer_id;
```

### 16.1. Aliases do not replace schema qualification

`customers AS c` only creates an alias; if `customers` resolved to the wrong table, `c` cannot save you.

### 16.2. Qualification does not solve row-level authorization

Even when `sec348.customers` is exact, filtering only by `customer_id` without tenant/user checks exposes out-of-scope rows.

These are two separate layers:

- **Object resolution:** targeting the right table/function.
- **Row authorization:** returning only rows the caller is permitted to view.

### 16.3. Never let callers choose arbitrary table names

A definer function taking `p_table_name text` and querying that table is dangerously broad without a strict allowlist.

Even with flawless identifier quoting and zero SQL injection, callers could select **valid tables they have no right to see**.

## 17. Attacker-writable schemas and function/operator hijacking

Suppose an `untrusted` schema exists:

```sql
-- Illustrating an unsafe configuration only:
SET search_path = untrusted, pg_catalog, sec348;
```

If untrusted users hold `CREATE` there, they can define objects whose names and signatures shadow or compete with calls inside a definer function.

### 17.1. Function name collisions

A call:

```sql
SELECT helper_process(value);
```

is not matched by string name alone; PostgreSQL evaluates:

- Schema search order.
- Argument types.
- Overloads and default arguments.
- Visibility and privileges.
- Version-specific resolution rules.

An untrusted schema placed earlier can redirect which function executes or render calls ambiguous.

### 17.2. Operators are also schema objects

For example:

```sql
a + b
```

resolves operators by operand types and `search_path`. PostgreSQL allows custom operators, so any untrusted schema ahead in `search_path` exposes operator resolution as an attack vector.

### 17.3. `pg_catalog` must take explicit precedence

```sql
SET search_path = pg_catalog, sec348, pg_temp;
```

This prevents hijacking built-ins and excludes untrusted schemas.

### 17.4. Never rely on "obscure" function names for security

Attackers can read catalogs or logs rather than guessing helper names. Security must rest on ownership, `CREATE` restrictions, and schema qualification—never secrecy of names.

### 17.5. PL/pgSQL plan caching is not a security control

PL/pgSQL caches query plans, and schema/`search_path` invalidations determine when statements re-parse.

Never assume a previously planned statement is immune to shadowing. Fix the root cause with a trusted `search_path` and explicit qualification.

## 18. PUBLIC EXECUTE: a surprising default

In PostgreSQL, **newly created functions normally grant `EXECUTE` to `PUBLIC` by default** unless default privileges have been changed.

This is critical for `SECURITY DEFINER` routines because:

- They may be owned by a privileged role.
- Any caller with schema `USAGE` and `EXECUTE` can call them even if you never wrote a `GRANT`.
- Running `CREATE` and `REVOKE` in separate transactions opens a temporary exposure window.

### 18.1. Create, REVOKE, and GRANT in the same transaction

Recommended pattern:

```sql
BEGIN;

CREATE FUNCTION sec348.example_api(
    p_id integer
)
RETURNS integer
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, sec348, pg_temp
AS $fn$
    SELECT p_id
$fn$;

REVOKE ALL ON FUNCTION sec348.example_api(integer)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION sec348.example_api(integer)
TO sec348_reader;

COMMIT;
```

Run this as the owner role or a role permitted to create routines in the schema. Keeping `CREATE`, `REVOKE`, and `GRANT` in **one transaction** prevents exposing `PUBLIC EXECUTE` before revocation takes effect.

### 18.2. REVOKE targets the exact signature

PostgreSQL allows **overloaded functions** sharing a name with different parameter types.

```sql
REVOKE ALL ON FUNCTION sec348.example_api(integer)
FROM PUBLIC;
```

revokes only that specific signature, leaving other same-named overloads untouched.

### 18.3. PUBLIC is a pseudo-role

`PUBLIC` represents all roles for privilege grants. It is **not** a login user named "public."

Revoking from `PUBLIC` does not remove privileges explicitly granted to specific roles or inherited via role membership.

### 18.4. Verify final effective privileges

```sql
SELECT
    has_function_privilege(
        'sec348_reader',
        'sec348.example_api(integer)',
        'EXECUTE'
    ) AS reader_allowed,
    has_function_privilege(
        'sec348_other',
        'sec348.example_api(integer)',
        'EXECUTE'
    ) AS other_allowed;
```

Verify schema `USAGE` and role memberships too when auditing effective access.

## 19. ALTER DEFAULT PRIVILEGES to reduce future exposure

If an owner role creates many routines, configure default privileges:

```sql
-- Run as the appropriate owner role:
ALTER DEFAULT PRIVILEGES
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
```

This alters defaults for **future functions** created in that role's scope—it does not retroactively revoke grants on existing functions.

### 19.1. Watch the creator role scope

Default privileges apply to the **object-creating role**, not automatically to routines merely because another role owns the schema.

If migrations run as one role and then call `ALTER OWNER`, remember defaults apply at `CREATE` time.

### 19.2. Per-schema REVOKE does not replace global REVOKE

A subtle PostgreSQL detail: per-schema default privileges **combine** with global default privileges. Revoking in a schema does not undo a global default grant.

To suppress `PUBLIC EXECUTE` by default, configure `REVOKE` **at the global scope of the creator role**, then grant selectively.

### 19.3. Never omit explicit REVOKE in critical migrations

For security-sensitive definer routines, still include:

```sql
REVOKE ALL ON FUNCTION ...
FROM PUBLIC;
```

right next to `CREATE` inside the same transaction and verify with `has_function_privilege`, rather than relying blindly on environment-dependent default privileges.

### 19.4. Schema defaults differ from EXECUTE

`GRANT USAGE ON SCHEMA` governs name visibility, whereas `EXECUTE ON FUNCTION` governs execution. Design both explicitly.

## 20. Least-privilege owner: what rights should the owner hold?

Architecture pattern:

```text
app_reader (LOGIN / or application role)
          |
          | Schema USAGE + API EXECUTE
          v
api_schema.get_balance(...)
          |
          | SECURITY DEFINER
          v
api_owner (NOLOGIN)
          |
          | SELECT on exact tables, UPDATE on exact columns/objects
          v
private_data.orders / balances
```

### 20.1. Owner does not need superuser

If a function only reads `private_data.customers.credit_limit`, never give its owner `DROP DATABASE`, `CREATEROLE`, `BYPASSRLS`, or privileges across unrelated schemas.

### 20.2. Separate owner roles by responsibility

An owner role can be dedicated solely to:

- Reading aggregated balances.
- Appending audit events to an audit table.
- Updating statuses under business invariants.

When privilege requirements diverge widely, split into separate owner roles and API schemas rather than pooling all permissions into one god-role.

### 20.3. Use NOLOGIN to shrink attack surface

`CREATE ROLE sec348_owner NOLOGIN` still allows authorized DBAs/members to run `SET ROLE`, while preventing direct client logins as the owner role.

### 20.4. Separate application execution roles from code-owning roles

Roles invoking APIs must never hold:

- `CREATE` on trusted schemas.
- `ALTER FUNCTION`.
- Ownership transfer rights.
- Direct write access to restricted tables.
- Role membership allowing `SET ROLE` into the owner role.

### 20.5. Privileges can be inherited

Role memberships and inheritance can grant unexpected permissions beyond direct `GRANT` statements. Always inspect effective privileges with `has_*_privilege` and role memberships rather than reading migration files alone.

## 21. Row-Level Security (RLS) and SECURITY DEFINER

RLS restricts which rows a role can see or modify via configured policies.

Under `SECURITY INVOKER`, queries follow the caller's effective privileges and RLS policies (unless the caller holds bypass privileges).

Under `SECURITY DEFINER`, internal queries run as the **function owner**. If that owner also owns the table or holds bypass rights, **RLS is bypassed** under PostgreSQL rules.

### 21.1. Table owners bypass RLS by default

Unless `FORCE ROW LEVEL SECURITY` is enabled on the table, table owners bypass RLS policies.

`SUPERUSER` and `BYPASSRLS` roles also bypass policies; `FORCE RLS` does not constrain those roles equally.

### 21.2. Why is this dangerous?

Suppose an app calls a definer function:

```sql
SELECT credit_limit
FROM sec348.customers
WHERE customer_id = p_customer_id;
```

If the owner bypasses RLS and multiple tenants share `customer_id = 1`, the API can return rows belonging to the wrong tenant.

Never assume "RLS is enabled on the table, so the definer function doesn't need a `WHERE tenant` filter."

### 21.3. Choose your architecture deliberately

Options include:

- Use `INVOKER` when caller RLS should apply directly.
- Use `DEFINER` with explicit, **trusted authorization checks** and a minimal owner role.
- Use an owner role that is not the table owner and lacks `BYPASSRLS`, paired with appropriate policies.
- Evaluate `FORCE ROW LEVEL SECURITY` carefully and test all paths.

No single flag replaces thorough tenant-isolation testing of the API.

### 21.4. Custom GUCs are not automatically trustworthy

A policy like:

```sql
USING (
    tenant_id =
    current_setting('app.tenant_id')::integer
)
```

works only if the application and database **strictly protect how that session variable is set**. If untrusted callers can run arbitrary SQL or `SET app.tenant_id`, they can spoof any tenant.

**A value in a custom session variable is never proof of authorization by itself.**

## 22. Tenant authorization: verify from a trusted source

In multi-tenant applications, a definer API must answer: "Which tenant may this caller access?"

### 22.1. Wrong: trusting a caller-supplied parameter

```sql
CREATE FUNCTION app_api.get_customer(
    p_tenant_id integer,
    p_customer_id integer
)
RETURNS ...
SECURITY DEFINER
...
```

If the function merely filters `WHERE tenant_id = p_tenant_id`, callers can probe any other tenant's `p_tenant_id`.

### 22.2. A design when each user has a dedicated DB login

A trusted mapping table:

```sql
-- Illustrative design only; do not run in the lab without creating the schema.
CREATE TABLE auth_private.login_tenants (
    login_name name NOT NULL,
    tenant_id integer NOT NULL,
    PRIMARY KEY (login_name, tenant_id)
);
```

Inside a definer function, you can inspect `SESSION_USER` and join that mapping **only if every principal genuinely has a distinct DB login and `SESSION_USER` is trustworthy in that architecture**.

### 22.3. Do not apply blindly with shared application connections

When millions of web users share one `app_database_login`, `SESSION_USER` is identical for everyone.

You need a different authorization architecture—for example, an application server connecting via a trusted DB role, enforcing domain permissions against mapping tables using authenticated security contexts, restricting direct SQL access, or securing session context integrity appropriately.

Passing an unverified `p_user_id` **from a client** into a definer function proves nothing about identity.

### 22.4. Fail closed when context is missing

If no trusted identity or tenant context is present, the function must **deny access** (or return only explicitly public data)—never default to returning all rows.

## 23. How do PROCEDUREs and FUNCTIONs compare?

PostgreSQL supports:

- `CREATE FUNCTION`: invoked in SQL expressions such as `SELECT schema.func(args)`.
- `CREATE PROCEDURE`: invoked via `CALL schema.proc(args)`.

Both support `SECURITY INVOKER` and `SECURITY DEFINER` declarations where applicable.

### 23.1. Invoker procedure example

```sql
CREATE PROCEDURE some_schema.log_attempt(
    p_message text
)
LANGUAGE plpgsql
SECURITY INVOKER
AS $proc$
BEGIN
    -- Illustrative logic.
    RAISE NOTICE 'Event received';
END
$proc$;
```

This is a syntax illustration only, not a production security routine.

### 23.2. Definer procedure example

```sql
CREATE PROCEDURE some_schema.run_limited_task()
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, some_schema, pg_temp
AS $proc$
BEGIN
    -- Authorized operations only.
    RAISE NOTICE 'Task started';
END
$proc$;
```

Requires valid owner, grants, and existing schema. Never assume a definer procedure can execute arbitrary server-admin commands.

### 23.3. Transaction control restrictions

A crucial PostgreSQL restriction:

> **A `SECURITY DEFINER` procedure cannot execute transaction control statements (`COMMIT`/`ROLLBACK`).**

Never write:

```sql
-- DO NOT use inside a SECURITY DEFINER procedure:
COMMIT;
ROLLBACK;
```

expecting it to manage transactions like an invoker top-level procedure.

### 23.4. SET clauses also block transaction control

PostgreSQL likewise restricts transaction control in procedures declared with a `SET` clause, even outside `SECURITY DEFINER`. Thus `SECURITY DEFINER SET search_path = ...` reinforces keeping transaction-control logic out of the routine.

### 23.5. Functions cannot act as top-level transaction managers

Functions run inside the caller's statement/transaction; commits and rollbacks belong to the client session or eligible invoker procedures.

### 23.6. Choose function vs. procedure by task

Use functions when returning scalars, rows, or sets in SQL expressions. Use procedures for workflows invoked via `CALL`. In both, reserve `SECURITY DEFINER` for explicit privilege-boundary needs while respecting its restrictions.

## 24. Writing a PL/pgSQL definer function for controlled updates

A common requirement: allow updating a customer's credit limit within a specific tenant **without granting direct `UPDATE` on the table**.

### 24.1. Wrong: updating by customer ID unconditionally

```sql
-- Dangerous authorization pattern:
UPDATE sec348.customers
SET credit_limit = p_new_limit
WHERE customer_id = p_customer_id;
```

If `customer_id` appears across multiple tenants, this updates rows in other tenants.

### 24.2. Better: enforce scope and invariants

```sql
-- Illustrative snippet inside a protected routine:
IF p_new_limit < 0 THEN
    RAISE EXCEPTION
        'Invalid credit limit';
END IF;

UPDATE sec348.customers AS c
SET credit_limit = p_new_limit
WHERE c.tenant_id = 10
  AND c.customer_id = p_customer_id;
```

In the lab, tenant 10 is hardcoded for illustration. Production must verify authorization from a trusted source, enforce upper bounds, write audit logs, and protect invariants.

### 24.3. Do not mistake RAISE EXCEPTION for authorization

`RAISE EXCEPTION` merely rejects invalid inputs. Real security lies in **accurate authorization checks** and data privileges.

### 24.4. Check affected row counts

In PL/pgSQL:

```sql
GET DIAGNOSTICS v_rows = ROW_COUNT;
```

reports how many rows the `UPDATE` modified. For routines expecting exactly one customer, handle `0` and `> 1` explicitly per business rules.

### 24.5. Never trust a prior SELECT followed by an unconditional UPDATE

Concurrent transactions can alter rows between statements. Protect invariants with conditional `WHERE` predicates, locking, or suitable transaction isolation.

## 25. Dynamic SQL: where search_path and SQL injection collide

PL/pgSQL supports dynamic SQL:

```sql
EXECUTE dynamic_sql;
```

Inside `SECURITY DEFINER`, this is a high-risk zone because dynamic SQL executes in a privileged context.

### 25.1. Wrong: concatenating input into SQL strings

```sql
-- Do not use with user-supplied input:
EXECUTE
    'SELECT credit_limit FROM sec348.customers ' ||
    'WHERE customer_id = ' || p_customer_id;
```

Even when `p_customer_id` is numeric here, string concatenation easily spreads to text/table names and abandons type-safe binding.

### 25.2. Better: EXECUTE ... USING for values

```sql
EXECUTE
    'SELECT c.credit_limit ' ||
    'FROM sec348.customers AS c ' ||
    'WHERE c.tenant_id = $1 ' ||
    'AND c.customer_id = $2'
INTO v_limit
USING 10, p_customer_id;
```

`$1` and `$2` in the dynamic command are placeholders for PL/pgSQL `EXECUTE ... USING`.

### 25.3. Value parameters are not identifiers

You cannot use `USING` to substitute table, schema, or column names:

```sql
-- Not a valid way to bind a table identifier:
EXECUTE 'SELECT * FROM $1' USING p_table_name;
```

Object names are **identifiers**, not SQL values.

### 25.4. Quote identifiers when dynamic object names are truly needed

```sql
EXECUTE format(
    'SELECT COUNT(*) FROM %I.%I',
    v_schema_name,
    v_table_name
)
INTO v_count;
```

`%I` in `format` quotes identifiers per PostgreSQL syntax, preventing identifier-based SQL injection.

### 25.5. Proper quoting is not authorization

If a caller can supply:

```text
schema = finance_private
table  = salaries
```

`format('%I.%I')` builds **syntactically valid** SQL accessing a table the caller shouldn't read, using the definer owner's privileges.

Always enforce an **explicit allowlist of permitted objects**, not just identifier escaping.

### 25.6. Avoid `%s` for untrusted input

`format('%s', input)` does not quote identifiers or literals like `%I` and `%L`. Using it carelessly in dynamic SQL reintroduces SQL injection.

### 25.7. `%L` vs. USING?

`%L` safely quotes SQL literals when building SQL text, yet whenever `USING` can bind values, prefer `USING` to cleanly separate data from SQL structure.

### 25.8. Schema-qualify inside dynamic SQL

```sql
EXECUTE
    'UPDATE sec348.customers ' ||
    'SET credit_limit = $1 ' ||
    'WHERE tenant_id = $2 AND customer_id = $3'
USING p_new_limit, 10, p_customer_id;
```

Never let dynamic commands rely on unqualified table names that callers could shadow.

## 26. SECURITY DEFINER and function overloading

PostgreSQL allows multiple functions sharing a name with different signatures:

```sql
some_schema.get_value(integer)
some_schema.get_value(text)
```

### 26.1. Privileges apply per exact signature

`GRANT EXECUTE ON FUNCTION some_schema.get_value(integer)` does not grant access to `get_value(text)`.

### 26.2. Overload resolution and implicit casts

A statement:

```sql
SELECT get_value('123');
```

undergoes type resolution and can become ambiguous or pick an unintended overload depending on signatures and `search_path`.

In privileged SQL:

- Schema-qualify function calls.
- Cast argument types explicitly.
- Exclude untrusted schemas from `search_path`.
- Audit overloads, defaults, and variadic arguments.
- Never assume "the built-in in `pg_catalog` always wins" when `search_path` is misconfigured.

### 26.3. Default arguments add confusion

An overload with default parameters can compete with shorter calls—another reason never to expose attacker-writable schemas in privileged `search_path` settings.

### 26.4. Inventory by exact signature rather than bare name

```sql
SELECT
    p.oid::regprocedure AS routine_identity,
    pg_get_function_identity_arguments(p.oid)
        AS identity_arguments
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'sec348'
ORDER BY routine_identity::text;
```

Always target exact OIDs or signatures when auditing or modifying grants.

## 27. Routines, trigger functions, and implicit privileges

A trigger function runs automatically when users `INSERT`/`UPDATE` a table, even though callers never invoke `SELECT my_trigger_func()` directly.

### 27.1. Definer triggers are major privilege boundaries

If a trigger function is `SECURITY DEFINER` and updates an audit or financial table, it runs with the owner's privileges.

That is helpful for appending audit records without letting app roles alter audit history, yet creates risks if:

- The trigger processes untrusted input data.
- Table or function names resolve through an unsafe `search_path`.
- The owner holds excessive privileges.
- Dynamic SQL is used.
- Error messages leak sensitive data.

### 27.2. Never let callers create triggers on sensitive tables

Any role permitted to attach triggers or alter trigger functions can escalate its reach drastically. Keep DDL rights strictly separate from application `INSERT`/`UPDATE` privileges.

### 27.3. Triggers alone do not guarantee tamper-proof audits

Protecting audit trails also requires proper ownership, append-only grants, retention controls, log shipping, and tamper-resistance controls.

### 27.4. SECURITY DEFINER functions are not exempt from all checks

They remain subject to constraints, transaction rules, owner privileges, and applicable triggers or policies. They do not grant "temporary superuser mode."

## 28. Where is `SET search_path` stored?

PostgreSQL stores routine-level configuration in `pg_proc.proconfig`.

Example:

```sql
SELECT
    p.oid::regprocedure AS routine_name,
    p.prosecdef AS security_definer,
    p.proconfig AS routine_settings
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'sec348'
ORDER BY routine_name::text;
```

### 28.1. `prosecdef`

- `true`: routine is `SECURITY DEFINER`.
- `false`: routine is `SECURITY INVOKER`.

### 28.2. `proconfig`

An array holding `SET` options attached to the routine, if any.

For a hardened definer function:

```text
{search_path=pg_catalog, sec348, pg_temp}
```

appears as the text representation of the setting.

### 28.3. NULL proconfig warrants investigation

A `SECURITY DEFINER` routine with `proconfig IS NULL` isn't automatically exploitable if everything inside is qualified, yet it is an immediate signal to audit `search_path` and object references.

### 28.4. Do not audit solely by grepping source text

Search-path risks can stem from:

- Function bodies.
- Routine-level `SET` configs.
- Owner role or session defaults.
- Nested helper functions.
- Dynamic SQL.
- Schema `CREATE` privileges.

Inspect the complete threat model.

## 29. Inventorying all SECURITY DEFINER routines

A useful audit query for the current database:

```sql
SELECT
    n.nspname AS routine_schema,
    p.proname AS routine_name,
    p.oid::regprocedure AS identity,
    r.rolname AS owner_role,
    p.prosecdef AS security_definer,
    p.proconfig AS settings
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
JOIN pg_roles AS r
  ON r.oid = p.proowner
WHERE p.prosecdef
  AND n.nspname NOT IN (
      'pg_catalog',
      'information_schema'
  )
ORDER BY routine_schema, identity::text;
```

### 29.1. Questions to ask during review

1. Does the routine genuinely need `DEFINER`?
2. Is the owner a superuser or `BYPASSRLS` role?
3. Does the owner hold overly broad schema or table privileges?
4. Does the function pin its own `SET search_path`?
5. Is `pg_temp` placed last?
6. Are any attacker-writable schemas in the path?
7. Are any table or function names unqualified in the body?
8. Does it use dynamic SQL?
9. Can caller inputs choose target objects?
10. Are tenant and user authorization checks enforced?
11. Is `EXECUTE` granted to `PUBLIC`?
12. Are there overloads with default arguments?
13. Do triggers or procedures invoke this routine?
14. Is RLS bypassed unintentionally?
15. Are there integration tests for negative cases?

### 29.2. Inspecting the routine definition

```sql
SELECT pg_get_functiondef(
    'sec348.definer_limit(integer)'::regprocedure
);
```

`pg_get_functiondef` shows the DDL representation including `SECURITY DEFINER`, `SET search_path`, and body where privileges allow.

### 29.3. Visibility limits

Catalog and source visibility can be restricted by role permissions. Conduct security audits using an appropriate administrative role and never expose sensitive DDL or secrets in public reports.

## 30. Checking CREATE privileges on schemas

A schema included in a definer's `search_path` is only trustworthy if untrusted roles **lack `CREATE`** on it.

Example:

```sql
SELECT
    n.nspname,
    has_schema_privilege(
        'sec348_reader',
        n.oid,
        'USAGE'
    ) AS reader_usage,
    has_schema_privilege(
        'sec348_reader',
        n.oid,
        'CREATE'
    ) AS reader_create,
    has_schema_privilege(
        'sec348_other',
        n.oid,
        'CREATE'
    ) AS other_create
FROM pg_namespace AS n
WHERE n.nspname IN ('sec348', 'public')
ORDER BY n.nspname;
```

### 30.1. Check current privileges, not historical assumptions

In older or upgraded databases, `public` may still grant `CREATE` broadly. While PostgreSQL 15 changed defaults for `public` on new databases, never guess permissions from server version alone.

### 30.2. REVOKE CREATE on public where appropriate

```sql
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
```

This is an **administrative change that can break apps or migrations** relying on `public`. Audit who creates objects in `public` and migrate them to dedicated schemas first.

### 30.3. A trusted schema can be undermined by role memberships

Even when `PUBLIC` lacks `CREATE`, a role can inherit `CREATE` via memberships or direct grants. Audit role hierarchies and ownership carefully.

### 30.4. Never let callers alter helper definitions

Beyond `CREATE`, an attacker able to `ALTER` or own a helper routine called by a definer can subvert execution. Trusted paths require trusted **object ownership**.

## 31. Updating search_path on an existing function

PostgreSQL supports:

```sql
ALTER FUNCTION sec348.definer_limit(integer)
SET search_path = pg_catalog, sec348, pg_temp;
```

This requires ownership or administrative privileges.

### 31.1. Do not assume ALTER SET fixes everything

If the body builds dynamic SQL from unvalidated caller identifiers or grants `EXECUTE` too broadly, pinning `search_path` alone does not eliminate all vulnerabilities.

### 31.2. Always specify the exact signature

When overloads exist, provide exact argument types in `ALTER FUNCTION` so you modify the intended routine.

### 31.3. For PROCEDUREs

```sql
ALTER PROCEDURE some_schema.some_proc(integer)
SET search_path = pg_catalog, some_schema, pg_temp;
```

Match the routine kind; `ALTER FUNCTION` does not replace `ALTER PROCEDURE`.

### 31.4. Verify after migration

Check:

```sql
SELECT
    p.oid::regprocedure,
    p.prosecdef,
    p.proconfig
FROM pg_proc AS p
WHERE p.oid =
    'sec348.definer_limit(integer)'::regprocedure;
```

alongside `has_function_privilege` and negative tests.

## 32. Never trust search_path from a connection pool

A pooled backend reused across HTTP requests may retain session settings such as:

```sql
SET search_path = tenant_schema, public;
```

If code forgets `RESET` or the pooler fails to reset state, subsequent requests can resolve the wrong tables or functions.

### 32.1. Use SET LOCAL inside transactions when appropriate

```sql
BEGIN;

SET LOCAL search_path = pg_catalog, some_schema;

-- Statements within the same transaction.

COMMIT;
```

`SET LOCAL` resets when the transaction ends. However, it **does not protect** a definer function against attacker-writable objects on its own; routine-level `SET search_path` is what matters.

### 32.2. Do not run SET LOCAL outside an explicit transaction

Under autocommit, a standalone `SET LOCAL` finishes its own implicit transaction immediately, leaving subsequent `SELECT` or `CALL` statements unaffected.

### 32.3. SECURITY DEFINER must lock its own path

A function declared:

```sql
SECURITY DEFINER
SET search_path = pg_catalog, sec348, pg_temp
```

is insulated from whatever session `search_path` a web request modified.

### 32.4. Connection pooling means SESSION_USER is not the web user

Many HTTP users share one DB login. `SESSION_USER` identifies the database connection, not the JWT subject or email address.

### 32.5. Never allow SET ROLE to impersonate the definer owner

Any caller allowed to run `SET ROLE sec348_owner` holds owner privileges outside the routine, bypassing the API boundary completely. Ensure role memberships prevent apps from switching into privileged owner roles.

## 33. Errors and exceptions must not leak data

A definer function can inadvertently leak details via errors containing:

- Secret key values.
- SQL text with sensitive inputs.
- Private schema or table names.
- Raw exception messages from nested helpers.
- Row contents or authorization state.

### 33.1. Never print full dynamic SQL

```sql
RAISE NOTICE 'SQL: %', v_dynamic_sql;
```

can expose sensitive data if the dynamic SQL contains secrets.

### 33.2. Distinguish permission errors from not-found errors carefully

Public APIs often return a uniform "not found or not authorized" response to avoid leaking whether a customer ID exists in another tenant.

Error semantics depend on security requirements; test timing and side channels as well for highly sensitive data.

### 33.3. Never swallow all exceptions and return defaults

Patterns like:

```sql
EXCEPTION WHEN OTHERS THEN
    RETURN 0;
```

hide permission failures, broken `search_path` resolution, and database corruption. Catch only expected exceptions with proper security logging and observability.

### 33.4. Privileged routines need a clear error strategy

Financial write routines must define atomicity, rollback/error codes, audit trails, retry semantics, and duplicate-request handling. `SECURITY DEFINER` does not fix broken transaction design.

## 34. Performance: SECURITY DEFINER is not a query optimization shortcut

When invoking:

```sql
SELECT sec348.definer_limit(1);
```

the server still must:

- Check `EXECUTE` permission.
- Switch and restore security context and routine GUCs.
- Execute internal SQL.
- Read required tables and indexes.
- Enforce MVCC visibility.
- Return the result.

### 34.1. Security boundaries affect inlining

Simple SQL functions can often be inlined by PostgreSQL. **`SECURITY DEFINER` and routine-level `SET` clauses prevent that inlining** compared to pure `SECURITY INVOKER` SQL functions.

Never assume a definer function produces the same query plan as an inlined outer query. Measure when called millions of times.

### 34.2. Per-row function calls

```sql
SELECT
    c.customer_id,
    sec348.definer_limit(c.customer_id)
FROM sec348.customers AS c;
```

evaluates per row, creating context-switch overhead and N+1-style repeated lookups. Avoid calling it across millions of rows when a set-based query or API is available.

### 34.3. Indexes still matter

In our lab, `sec348.customers` has a primary key on `(tenant_id, customer_id)` aligned with the query. Never expect a definer wrapper to make missing indexes fast.

### 34.4. EXPLAIN and function observability

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sec348.definer_limit(1);
```

For functions executing internal queries, outer `EXPLAIN` will not automatically display every nested SQL plan node. Use dedicated instrumentation, logging, or test profiling.

### 34.5. Tracking calls when enabled

PostgreSQL offers `pg_stat_user_functions`, controlled by `track_functions` and server settings:

```sql
SELECT
    funcid::regprocedure AS function_name,
    calls,
    total_time,
    self_time
FROM pg_stat_user_functions
WHERE schemaname = 'sec348'
ORDER BY total_time DESC;
```

Never conclude a function never ran just because no row appears if `track_functions` is off.

## 35. Migration workflow for SECURITY DEFINER routines

A safe migration typically includes:

1. Defining a least-privilege owner role.
2. Creating a private/trusted schema or verifying existing schemas forbid untrusted `CREATE`.
3. Creating base objects with explicit ownership and grants.
4. Writing the function with `SECURITY DEFINER` and routine-level `SET search_path`.
5. Schema-qualifying sensitive tables and helper calls.
6. Avoiding dynamic SQL, or enforcing allowlists and `USING`.
7. Running **CREATE + REVOKE FROM PUBLIC + GRANT** in the same transaction.
8. Verifying exact signatures, owner, and `proconfig`.
9. Testing invoker/definer behavior using roles without direct table privileges.
10. Testing unauthorized callers lacking `EXECUTE`.
11. Testing temp-table shadowing and schema shadowing.
12. Testing row and tenant isolation.
13. Testing RLS and pooled connection state.
14. Measuring performance to avoid per-row overhead.
15. Deploying with canary checks and a rollback plan.

### 35.1. Never replace a routine without re-auditing grants

`CREATE OR REPLACE FUNCTION` preserves existing ownership and privileges per PostgreSQL rules—it does not reset grants or swap owners.

After any migration changing body, owner, signature, or security mode, re-audit effective privileges.

### 35.2. Changing a signature creates a new overload

Adding a parameter in `CREATE OR REPLACE FUNCTION` creates a **brand-new function** rather than replacing the old one—and the new overload inherits default `EXECUTE` privileges.

Always inspect the catalog after migrations.

### 35.3. Protect CREATE FUNCTION credentials

Migrations should run under a deployment role allowed to create routines in trusted schemas; runtime application roles must never hold permission to alter definer functions.

### 35.4. Rollback must account for data and grants

Changing security modes or owners affects more than source code. Rollbacks must track schema ownership, default privileges, grants, and API compatibility.

## 36. Quick checklist: when to use SECURITY INVOKER?

Default to `INVOKER` when:

- Callers already hold privileges on the required data.
- Caller-scoped RLS is desired.
- The routine simply encapsulates calculations or reusable SQL.
- Direct table privileges do not need to be hidden.
- No narrow privilege elevation is required.

Invoker functions still require safe code, proper schema qualification, and input validation.

## 37. Quick checklist: when to use SECURITY DEFINER?

Choose `DEFINER` only when:

- You must grant **indirect, narrowly scoped** access to an operation.
- Callers must not hold direct table privileges.
- The API enforces all required authorization checks reliably.
- The owner role holds minimal privileges.
- Trusted schemas and `pg_temp` placement are strictly controlled.
- `EXECUTE` is granted exclusively to authorized roles.
- No unchecked dynamic SQL or ambiguous overloads exist.
- RLS interactions are understood and tested.
- Auditing, logging, and monitoring are in place.
- Migrations and negative regression tests exist.

If you cannot clearly answer "Which rows and operations is the caller restricted to?", do not expose elevated privileges with `DEFINER`.

## 38. Common misconceptions and mistakes

| Misconception / Mistake | Reality |
| --- | --- |
| Functions default to DEFINER | They default to `INVOKER` |
| Granting EXECUTE grants table SELECT | False; they are separate privileges |
| SECURITY DEFINER runs as superuser | Runs as the function owner, not automatically superuser |
| Having a superuser owner is harmless | Creates an unnecessarily huge blast radius |
| NOLOGIN owners cannot be accessed via SET ROLE | Memberships and role grants must still be restricted |
| CURRENT_USER inside definer is the caller | Reflects the routine owner in definer context |
| SESSION_USER changes on SET ROLE | Remains the session login role |
| SESSION_USER is always the web user | Connection pools typically share one DB login |
| Filtering by `WHERE customer_id` suffices | May miss tenant and authorization checks |
| `search_path` only affects tables | Also affects functions, operators, and types |
| `SET search_path=trusted_schema` is safe alone | `pg_temp` is searched first for relations/types unless pinned last |
| `pg_temp` is always searched last | False; must be placed explicitly |
| `pg_temp` resolves functions/operators like tables | Temporary schema lookup differs by object type |
| `pg_catalog` position doesn't matter | Explicit placement affects lookup precedence |
| `public` is always safe by default | Depends on schema ACLs, version, and upgrade history |
| Schema USAGE implies CREATE | They are two separate privileges |
| Leaving table names unqualified in definer is fine | Vulnerable to object shadowing |
| Table aliases replace schema qualification | False |
| Caller `SET search_path` protects definer | Pin `search_path` in the routine definition |
| Obscure function names provide security | False; rely on privileges and namespaces |
| Granting EXECUTE after CREATE is always safe | Exposes `PUBLIC EXECUTE` window if in separate transactions |
| `PUBLIC` is a login role | It is a pseudo-role representing all roles |
| `REVOKE PUBLIC` removes membership grants | Explicit role/membership grants remain active |
| `ALTER DEFAULT PRIVILEGES` is retroactive | Applies only to future objects |
| Per-schema REVOKE removes global defaults | Not necessarily |
| Definer automatically obeys caller RLS | Owner/bypass privileges may skip RLS |
| `FORCE RLS` constrains superuser | Superusers and `BYPASSRLS` still bypass |
| Custom GUCs prove user identity | Callers can forge them unless protected |
| `format('%I')` alone guarantees safety | Quotes identifiers, does not authorize object selection |
| `EXECUTE ... USING` binds table names | Binds values only, not identifiers |
| DEFINER procedures can COMMIT arbitrarily | Transaction control is prohibited in definer procedures |
| Procedure `SET` clauses don't affect transactions | They also restrict transaction control |
| CTEs/VIEWs/functions are automatic security boundaries | Verify privilege semantics per object |
| Outer EXPLAIN always shows inner function SQL | Not necessarily |
| Replacing a function resets old GRANTs | Never assume; audit grants |
| Happy-path tests are enough | Must test negative access, RLS, and path shadowing |
| Absent from `pg_stat_user_functions` means never called | Tracking depends on configuration |

## 39. Practice exercises with answers

Exercises use schema `sec348`. Run DDL and role changes only on a lab database with appropriate admin rights. Snippets labeled "unsafe" are **anti-patterns for analysis**, never for production.

### Exercise 1. What is the default function security mode?

**Answer:** `SECURITY INVOKER`.

### Exercise 2. Whose privileges does SECURITY INVOKER use?

**Answer:** The caller's / effective role's privileges when invoking the routine under PostgreSQL rules.

### Exercise 3. Whose privileges does SECURITY DEFINER use?

**Answer:** The function/procedure owner's privileges during routine execution.

### Exercise 4. What happens if a caller has EXECUTE on an invoker function but lacks SELECT on the underlying table?

**Answer:** It fails with a permission error when attempting to read the table, unless privileges are obtained through another role or mechanism.

### Exercise 5. Can that same caller succeed with a definer function?

**Answer:** Yes, provided the owner holds table privileges, the function allows the action, and the caller holds `EXECUTE` and schema `USAGE`.

### Exercise 6. Why shouldn't a superuser own definer functions?

**Answer:** Any logic or resolution bug executes with unrestricted privileges. Use a dedicated least-privilege owner role instead.

### Exercise 7. Who is CURRENT_USER inside a definer function?

**Answer:** The routine's owner while the definer context is active.

### Exercise 8. Does SESSION_USER change after SET ROLE?

**Answer:** No; it generally remains the session's original login role.

### Exercise 9. Can SET ROLE fully test SESSION_USER-based login mappings?

**Answer:** Not completely. Connect using actual distinct DB logins if logic relies on `SESSION_USER`.

### Exercise 10. How does USAGE ON SCHEMA differ from CREATE?

**Answer:** `USAGE` permits resolving existing objects; `CREATE` permits creating new objects. Definer API callers generally need only `USAGE`.

### Exercise 11. Check reader's SELECT privilege

```sql
SELECT has_table_privilege(
    'sec348_reader',
    'sec348.customers',
    'SELECT'
);
```

**Answer:** Expected `false` in the lab without additional grants or memberships.

### Exercise 12. Check reader's EXECUTE privilege

```sql
SELECT has_function_privilege(
    'sec348_reader',
    'sec348.definer_limit(integer)',
    'EXECUTE'
);
```

**Answer:** `true` after executing the `GRANT` in Section 8.

### Exercise 13. Why isn't checking has_function_privilege sufficient?

**Answer:** You must also check schema `USAGE`, base-table rights under invoker/definer, role memberships, and business authorization.

### Exercise 14. What does SET search_path control?

**Answer:** How PostgreSQL resolves unqualified object names based on object kind, visible schemas, and resolution precedence.

### Exercise 15. Why is `SELECT * FROM customers` risky inside a definer function?

**Answer:** It can resolve to a different table if `search_path` exposes untrusted or temporary objects.

### Exercise 16. What is a fully qualified table name?

```sql
SELECT c.credit_limit
FROM sec348.customers AS c;
```

**Answer:** `sec348.customers` explicitly specifies both schema and relation.

### Exercise 17. Does `SET search_path = sec348` place pg_temp last?

**Answer:** No. When omitted, the temporary namespace is searched first for relation and type names.

### Exercise 18. What definer path configuration should usually be used?

**Answer:** `SET search_path = pg_catalog, sec348, pg_temp` when `sec348` is trusted and routines are written safely.

### Exercise 19. Why should pg_catalog precede untrusted schemas?

**Answer:** To reduce the risk of built-in functions or operators being shadowed or hijacked by attacker-created objects.

### Exercise 20. Is pg_temp searched for function names the same way as table names?

**Answer:** No. Implicit temporary-schema precedence applies primarily to relation and type names, not unqualified function/operator lookups.

### Exercise 21. Does CREATE TEMP TABLE overwrite database-wide tables?

**Answer:** No. It creates a session-local temporary table, which can still shadow unqualified relation names in that session.

### Exercise 22. If a definer always writes sec348.customers, does a temp table `customers` hijack that reference?

**Answer:** No, the fully qualified `sec348.customers` stays pinned. Still, check all unqualified helpers, types, and dynamic SQL inside the routine.

### Exercise 23. What risks arise from an attacker-writable schema in search_path?

**Answer:** Attackers can create colliding objects, overloads, or operators to hijack function, type, operator, or table resolution.

### Exercise 24. Should `public` be added to a definer's search_path?

**Answer:** Only if `public` is genuinely trusted and required. Dedicated, tightly controlled schemas are strongly preferred.

### Exercise 25. Does PostgreSQL 15 guarantee every `public` schema is locked down?

**Answer:** No; fresh databases, upgraded databases, and historical `GRANT`s differ. Always inspect actual ACLs.

### Exercise 26. What does PUBLIC EXECUTE mean?

**Answer:** Newly created functions commonly grant `EXECUTE` to pseudo-role `PUBLIC` by default, letting any role with schema `USAGE` invoke them.

### Exercise 27. How do you revoke from a single function overload?

```sql
REVOKE ALL ON FUNCTION sec348.definer_limit(integer)
FROM PUBLIC;
```

**Answer:** Specify the exact input signature to target the intended overload.

### Exercise 28. Why keep CREATE/REVOKE/GRANT in one transaction?

**Answer:** To eliminate any window where the new object has `PUBLIC EXECUTE` before privileges are restricted.

### Exercise 29. Does ALTER DEFAULT PRIVILEGES affect existing functions?

**Answer:** No. It applies only to objects created afterward within the applicable creator scope.

### Exercise 30. Does a per-schema default REVOKE override a global PUBLIC grant?

**Answer:** Never assume so; understand how global and per-schema default privileges combine.

### Exercise 31. What if a definer accepts arbitrary p_tenant_id without verification?

**Answer:** Callers can query other tenants' data if the owner holds broad privileges; verify authorization from a trusted source.

### Exercise 32. Does SECURITY DEFINER enforce the caller's RLS automatically?

**Answer:** Not by default. Definer runs under owner privileges, and table owners or bypass roles can skip RLS.

### Exercise 33. Does FORCE RLS force superusers to obey policies?

**Answer:** No; superusers and `BYPASSRLS` roles remain exempt.

### Exercise 34. Is a custom setting like app.tenant_id proof of authorization?

**Answer:** Only when architecture guarantees callers cannot spoof it; an unprotected custom GUC is not a security boundary.

### Exercise 35. How do you pass values safely in dynamic SQL?

```sql
EXECUTE
    'SELECT credit_limit ' ||
    'FROM sec348.customers ' ||
    'WHERE tenant_id = $1 AND customer_id = $2'
INTO v_limit
USING 10, p_customer_id;
```

**Answer:** Use placeholders and `USING` rather than concatenating values into SQL strings.

### Exercise 36. Can EXECUTE USING bind a table name?

**Answer:** No. Identifiers must be validated and quoted explicitly, e.g., `format('%I.%I', schema, table)`.

### Exercise 37. Is `format('%I.%I')` sufficient when callers pick arbitrary tables?

**Answer:** No. Quoting prevents SQL injection, not unauthorized access; enforce an allowlist and authorization checks.

### Exercise 38. Why is `format('%s', untrusted_input)` dangerous?

**Answer:** It does not quote as an identifier or literal, letting raw SQL syntax enter dynamic commands.

### Exercise 39. Can a SECURITY DEFINER PROCEDURE execute COMMIT arbitrarily?

**Answer:** No. PostgreSQL prohibits transaction control inside definer procedures.

### Exercise 40. Can a PROCEDURE with a SET clause COMMIT in all contexts?

**Answer:** No. Procedures declared with `SET` clauses also have transaction-control restrictions.

### Exercise 41. Can you create a SECURITY DEFINER trigger function?

**Answer:** Yes, and it forms a privileged boundary requiring proper owner, `search_path`, SQL safety, authorization, and auditing.

### Exercise 42. Which catalog lists definer routines?

**Answer:** `pg_proc` filtered by `prosecdef = true`, joined with `pg_namespace` and `pg_roles` for schemas and owners.

### Exercise 43. What can `proconfig` contain?

**Answer:** Routine-level `SET` options such as `search_path`; `NULL` indicates none were configured on the routine.

### Exercise 44. How do you inspect a function's full definition?

```sql
SELECT pg_get_functiondef(
    'sec348.definer_limit(integer)'::regprocedure
);
```

**Answer:** Reads the DDL representation to inspect body, `SECURITY` mode, and `search_path`.

### Exercise 45. Which command updates search_path on an existing function?

```sql
ALTER FUNCTION sec348.definer_limit(integer)
SET search_path = pg_catalog, sec348, pg_temp;
```

**Answer:** Target the exact signature and verify `proconfig` afterward.

### Exercise 46. Does CREATE OR REPLACE FUNCTION reset all grants?

**Answer:** Never assume it does. Audit owner, privileges, and security attributes after migrations.

### Exercise 47. Why can changing a signature be dangerous?

**Answer:** It can create a brand-new overload instead of replacing the old function, inheriting default `EXECUTE` privileges.

### Exercise 48. Does absence from `pg_stat_user_functions` prove a function never ran?

**Answer:** No. Statistics collection depends on `track_functions` and server configuration.

### Exercise 49. Why can calling a definer function per row be slow?

**Answer:** Function call overhead, security context switching, and repeated internal queries cause N+1 work even with indexes.

### Exercise 50. Build a secure deployment checklist

**Suggested answer:**

1. Identify which tasks truly need elevation and default to `INVOKER` elsewhere.
2. Create least-privilege `NOLOGIN` owner roles without superuser/`BYPASSRLS` unless unavoidable.
3. Place routines in trusted schemas where callers lack `CREATE`/`ALTER` on helpers.
4. Declare `SECURITY DEFINER SET search_path = pg_catalog, trusted, pg_temp`.
5. Schema-qualify sensitive tables and helper calls.
6. Revoke `EXECUTE` from `PUBLIC` and grant only required roles in the same transaction as `CREATE`.
7. Never trust unverified caller-supplied tenant or user IDs.
8. Verify RLS interactions, owner bypasses, and session identity.
9. Use `EXECUTE ... USING` for values, quote identifiers, and enforce object allowlists.
10. Test negative cases: unauthorized callers, cross-tenant probes, temp/schema shadowing.
11. Audit `pg_proc`/`proconfig`, schema/`EXECUTE` rights, and owner memberships.
12. Monitor errors/latency, review migrations, and prepare rollback plans.

## 40. Audit and hardening workflow in production systems

A routine that ran safely for months is not guaranteed safe after schema or role changes.

### Step 1. Inventory definer routines

```sql
SELECT
    p.oid::regprocedure,
    r.rolname AS owner,
    p.proconfig
FROM pg_proc AS p
JOIN pg_roles AS r
  ON r.oid = p.proowner
WHERE p.prosecdef
ORDER BY p.oid::regprocedure::text;
```

### Step 2. Audit schema scopes

- Which schemas host the routines?
- Can untrusted roles `CREATE` in any schema on the path?
- Are there legacy `public` schema grants?
- Is temp-relation shadowing possible if `pg_temp` isn't listed last?
- Is `search_path` overridden at role or session level?

### Step 3. Audit invocation privileges

```sql
SELECT
    has_function_privilege(
        'sec348_reader',
        'sec348.definer_limit(integer)',
        'EXECUTE'
    ) AS allowed_reader,
    has_function_privilege(
        'sec348_other',
        'sec348.definer_limit(integer)',
        'EXECUTE'
    ) AS unapproved_reader;
```

Expect `true`/`false` matching lab grants. If different, inspect `PUBLIC`, role memberships, and ACLs.

### Step 4. Inspect bodies and nested dependencies

Look for:

- Unqualified tables, functions, and types.
- Dynamic SQL.
- Inputs selecting tenants, tables, or columns.
- Calls to untrusted helpers.
- Authorization logic.
- Exception handlers leaking secrets.
- Data writes and row-count assumptions.

### Step 5. Remediate with focused changes

- Pin routine-level `search_path`.
- Qualify object names.
- Revoke unnecessary `EXECUTE`.
- Split overly broad owner roles.
- Add explicit tenant authorization if missing.
- Add tests and observability.

### Step 6. Test negative scenarios

Critical test cases:

| Scenario | Expected outcome |
| --- | --- |
| Caller lacks schema `USAGE` | Cannot resolve routine by schema name |
| Caller lacks `EXECUTE` | Denied execution |
| Caller has `EXECUTE` but no table `SELECT` | `INVOKER` fails; `DEFINER` performs only permitted API logic |
| Caller creates same-named temp table | Hardened definer still hits real target object |
| Caller alters session `search_path` | Hardened definer preserves routine-level path |
| Caller passes another tenant ID | Denied; no out-of-scope rows returned |
| Caller passes disallowed table name | Blocked by allowlist |
| `PUBLIC`/grants widened accidentally | Caught by privilege regression checks |
| RLS bypassed by owner | Enforced via explicit authorization |
| Dynamic input contains SQL syntax | Bound/quoted safely and unauthorized actions denied |
| Routine raises error | No sensitive data leaked |
| Connection pool reuse | No leaked invalid session context |

### Step 7. Monitor post-deployment

Track:

- Permission error rates.
- Function calls and latency.
- Changes to grants, owners, and routine definitions.
- Unusual query patterns.
- Security logs and anomaly reports.
- Database throughput and lock contention.
- Stability of the API contract.

Security reviews belong inside the **migration lifecycle**, not as a one-off check when first writing a function.

## 41. Pre-release checklist for functions and procedures

| Question | How to verify |
| --- | --- |
| Is `SECURITY DEFINER` truly required? | Specific privilege justification |
| Would `INVOKER` suffice? | Test with caller privileges |
| Is owner `NOLOGIN`? | `pg_roles` |
| Does owner hold excessive rights? | Grants and memberships |
| Does owner have superuser/`BYPASSRLS`? | Role attributes |
| Can attackers `CREATE` in trusted schemas? | `has_schema_privilege` |
| Is `search_path` pinned in the definition? | `pg_proc.proconfig` |
| Is `pg_catalog` prioritized first? | Routine `SET` clause |
| Is `pg_temp` placed last? | Routine `SET` clause |
| Are sensitive objects fully qualified? | SQL/PLpgSQL body review |
| Are helper routines equally safe? | Call graph audit |
| Are there overloaded functions? | Exact signatures |
| Are implicit casts or defaults involved? | Overload resolution tests |
| Does it use dynamic SQL? | `EXECUTE` review |
| Are values bound via `USING`? | Injection tests |
| Are dynamic identifiers quoted safely? | `format('%I')` |
| Are dynamic identifiers allowlisted? | Authorization tests |
| Can callers select other tenants? | Negative isolation tests |
| Is caller identity trustworthy? | DB login / app security context |
| Could RLS be bypassed? | Owner/role/policy tests |
| Is `PUBLIC EXECUTE` revoked? | ACL / `has_function_privilege` |
| Is `GRANT` in the same transaction as `CREATE`? | Migration review |
| Does the app role have schema `USAGE`? | Privilege checks |
| Does the app role lack `CREATE`/`ALTER`? | Privilege checks |
| Does a procedure control transactions? | Security mode / `SET` restrictions |
| Do triggers invoke the routine? | Dependency audit |
| Are per-row queries too costly? | `EXPLAIN` / metrics |
| Can errors leak secrets? | Exception and log review |
| Are unauthorized-caller tests present? | Negative tests |
| Are `pg_temp` shadowing tests present? | Fresh-session tests |
| Are schema shadowing tests present? | Untrusted `CREATE` tests |
| Is connection-pool isolation tested? | Multi-request tests |
| Audited after `CREATE OR REPLACE`? | Catalog diff |
| Is a rollback plan ready? | DDL/grants revert |
| Is post-deploy monitoring configured? | Alerts, latency, security events |

## 42. Summary

PostgreSQL lets functions and procedures serve as a secure data-tier API, provided **privileges, object resolution, and authorization** are all engineered properly.

Key takeaways:

1. **`SECURITY INVOKER` is the default** and fits whenever callers should operate under their own rights.
2. **`SECURITY DEFINER` runs with the owner's privileges** during the routine call, allowing callers to run defined operations without direct table access.
3. **`EXECUTE` differs from `SELECT` and schema `USAGE`**. Understand and configure all three layers.
4. **Routine owners must follow least privilege**, favoring dedicated `NOLOGIN` roles instead of superusers.
5. **`CURRENT_USER` inside a definer reflects the owner**, not the caller; `SESSION_USER` reflects the DB login and ignores `SET ROLE`.
6. **`search_path` governs object resolution** across tables, functions, types, and operators per PostgreSQL rules.
7. **`pg_catalog` should take precedence** to prevent untrusted schemas from shadowing built-in functions and operators.
8. **`pg_temp` must be handled explicitly**: for relation and type names, the temporary schema is searched first unless placed at the end of `search_path`.
9. **Safe definer definitions** combine `SET search_path = pg_catalog, trusted_schema, pg_temp` with fully qualified table references.
10. **Never include attacker-writable schemas in `search_path`** or let application roles modify trusted helpers.
11. **New functions often grant `PUBLIC EXECUTE` by default**; bundle `CREATE`, `REVOKE`, and `GRANT` in one transaction to prevent exposure windows.
12. **Default privileges are not retroactive**, and per-schema vs. global defaults follow specific creator-scope rules.
13. **RLS can be bypassed in definer contexts** if the owner owns the table or holds bypass attributes.
14. **Caller-supplied tenant/customer IDs are not proof of authorization**. Validate access against trusted identity sources on every operation.
15. **Dynamic SQL requires `EXECUTE ... USING` for values**, `format('%I')` for necessary identifiers, and strict object allowlists.
16. **`SECURITY DEFINER` procedures restrict transaction control**; never treat them as arbitrary transaction managers.
17. **Audit using `pg_proc.prosecdef`, `proconfig`, `pg_get_functiondef`, and `has_*_privilege`** to inspect actual server state rather than trusting source assumptions.
18. **Negative testing is mandatory**: test temp shadowing, unauthorized callers, cross-tenant access, session state, and RLS.
19. **Performance still matters**: definer does not replace indexes or query tuning, and per-row calls create heavy overhead.
20. **Long-term operations require monitoring and migration reviews** whenever roles, schemas, or routines evolve.

A memorable pattern for creating a definer API:

```sql
SET ROLE sec348_owner;

BEGIN;

CREATE FUNCTION sec348.get_limit(
    p_customer_id integer
)
RETURNS numeric
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, sec348, pg_temp
AS $fn$
    SELECT c.credit_limit
    FROM sec348.customers AS c
    WHERE c.tenant_id = 10
      AND c.customer_id = p_customer_id
$fn$;

REVOKE ALL ON FUNCTION sec348.get_limit(integer)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION sec348.get_limit(integer)
TO sec348_reader;

COMMIT;

RESET ROLE;
```

This template hardcodes **tenant 10 solely to demonstrate privilege scoping**. A real multi-tenant API must verify the caller's authorization for the requested tenant/customer rather than turning `10` into an unchecked parameter.

**Final rule:** for every `SECURITY DEFINER` routine, always ask: **"What privileges does the owner hold, which object names or parameters can the caller influence, what `search_path` does the routine use, and what enforces that callers stay within their authorized data scope?"** Only when DDL, ACLs, and negative tests answer all four questions can a privileged PostgreSQL routine be trusted.
