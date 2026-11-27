# SECURITY DEFINER Function Privileges and Protecting Privilege Escalation Boundaries in PostgreSQL

An application should not be allowed to directly read tables holding inventory quantities, cost prices, or customer information. However, the application still needs to invoke a function like `get_available_stock('KB-001')` to retrieve **a strictly permitted piece of public information**. PostgreSQL supports building such restricted APIs via **`SECURITY DEFINER`**: the function executes its internal SQL under the privileges of the **function owner**, rather than only the caller's privileges.

This introduces an **intentional privilege escalation boundary**. Written securely, callers can perform solely the operations the function permits. Written carelessly—such as resolving table names through an untrusted `search_path`, concatenating dynamic SQL from inputs, granting overly broad `EXECUTE` rights, or owning the function with a superuser—it can become an execution path for operations the caller was supposed to be forbidden from performing.

~~~sql
-- Illustrates a function running with owner privileges.
-- The roles/schemas/tables will be created in full in the lab:
CREATE FUNCTION sec389_api.get_available_stock(p_sku text)
RETURNS integer
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, sec389_private, pg_temp
AS $$
    SELECT available_units
    FROM sec389_private.inventory
    WHERE sku = p_sku
      AND is_public = true
$$;
~~~

**The `SECURITY DEFINER` keyword does not guarantee safety on its own.** You must simultaneously safeguard the owner role, `EXECUTE` grants, object names referenced by the function, inputs, schema `CREATE` privileges, authorization correctness, and testing under low-privilege callers.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish `SECURITY INVOKER` (default) from `SECURITY DEFINER`.
2. Explain `current_user`, `session_user`, and the effect of `SET ROLE` in function contexts.
3. Identify the privileges needed to call a function versus the privileges checked when SQL inside the function runs.
4. Understand that `EXECUTE` is normally granted to `PUBLIC` by default for newly created functions.
5. Restrict invocation via `REVOKE ... FROM PUBLIC` and `GRANT EXECUTE` to designated roles.
6. Eliminate exposure windows on newly created functions by creating the function and updating grants **within the same transaction**.
7. Intentionally configure `SET search_path = pg_catalog, trusted_schema, pg_temp`.
8. Identify risks of **object shadowing**, fake functions/operators, temporary-table hijacking, and schemas with untrusted `CREATE` grants.
9. Combine schema-qualified names, trusted search paths, and parameterized dynamic SQL.
10. Design a definer role with **no `LOGIN`, no `SUPERUSER`, no `BYPASSRLS`**, holding only minimal required rights.
11. Separate the data owner from the function owner to avoid overly broad read/write rights.
12. Enforce privileges across schemas, tables, columns, and functions following the principle of **least privilege**.
13. Understand differences among `USAGE ON SCHEMA`, `EXECUTE ON FUNCTION`, and table `SELECT`/`UPDATE` privileges.
14. Evaluate RLS (*Row-Level Security*) and risks of table owners or `BYPASSRLS` bypassing policies.
15. Avoid confusing `current_user` inside a definer function with the caller's identity.
16. Design bounded read APIs and write APIs with validation, authorization, and proper auditing.
17. Write `SECURITY DEFINER` functions that do not leak sensitive data via errors, logs, or outputs.
18. Diagnose `permission denied`, `function does not exist`, `search_path` bugs, and post-migration incidents.
19. Inspect metadata using `pg_proc`, `pg_namespace`, `pg_roles`, and privilege grants.
20. Establish review checklists, migrations, low-privilege testing, and incident response when definer flaws arise.

## 2. Why Use SECURITY DEFINER?

Imagine an internal table:

~~~text
private.inventory
  sku
  available_units
  cost_price        <- must not be exposed
  is_public
~~~

A storefront application needs to know `available_units` for products where `is_public=true` to display stock availability. It **does not need** to read `cost_price`, see inventory for confidential products, or modify stock levels directly.

If you grant:

~~~sql
GRANT SELECT ON private.inventory TO app_role;
~~~

the application can read **all columns and rows** permitted by grants/policies, exceeding its actual requirements. Instead, you can:

1. Keep the table in a private schema without granting the application direct access.
2. Create `get_available_stock(text)` returning only a single checked value.
3. Give a dedicated, restricted owner role `SELECT` on **only the required columns**.
4. Declare the function `SECURITY DEFINER`.
5. Grant `EXECUTE` solely on that function to the application role.

When invoked, callers receive the function's output without being able to run `SELECT * FROM private.inventory` directly.

### 2.1. SECURITY DEFINER Is a Privileged API Boundary

~~~text
Application / low-privilege role
       |
       | USAGE on API schema + EXECUTE on specific function
       v
   SECURITY DEFINER function
       |
       | Internal SQL runs with definer owner privileges
       v
  Internal tables or business logic
       |
       v
  Restricted result returned to application
~~~

**The function is the control point**—the entire underlying table is not "unlocked" for callers.

### 2.2. When Is SECURITY DEFINER Unnecessary?

If the application already holds appropriate privileges for the table and operation, leave functions as the default `SECURITY INVOKER`. Every privilege boundary adds review, testing, monitoring, and maintenance overhead.

A pure calculation function:

~~~sql
CREATE FUNCTION public.calculate_total(p_price numeric, p_qty integer)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_price * p_qty
$$;
~~~

needs no special privileges to touch internal tables; marking it `SECURITY DEFINER` introduces risk with zero benefit.

### 2.3. Definer Does Not Mean Unlimited Power

A function holds only the privileges belonging to its **owner role** (directly or via inherited memberships/policies). If the owner lacks `SELECT` on an internal table, `SECURITY DEFINER` does not invent that privilege.

### 2.4. Intentional Privilege Escalation Can Be Sound

A least-privilege API with thorough review and constrained inputs/outputs is a clean design. The danger lies not in privilege escalation itself, but in letting **callers steer the function outside its intended contract**.

## 3. SECURITY INVOKER vs. SECURITY DEFINER

PostgreSQL supports two execution security modes:

| Property | `SECURITY INVOKER` | `SECURITY DEFINER` |
| --- | --- | --- |
| Default | **Yes** | No |
| Whose rights govern SQL inside the function? | The caller's | The function owner's |
| Escalation blast radius if exploited | Normally bounded by caller rights | Can exceed caller rights up to definer rights |
| Appropriate for | Normal functions adhering to caller rights | Narrowly scoped privileged APIs |
| Needs `search_path`/dynamic SQL hardening? | Yes | **Critically important** |
| Owner role | Object owner | Object owner also acts as privileged execution identity |

### 3.1. Creating an Invoker Function

~~~sql
CREATE FUNCTION public.try_read_count()
RETURNS bigint
LANGUAGE sql
SECURITY INVOKER
AS $$
    SELECT COUNT(*) FROM sensitive_schema.hidden_table
$$;
~~~

This is an **illustrative example**: the schema/table does not exist yet. If the caller lacks necessary rights, invoking the function fails under internal SQL privilege checks.

### 3.2. Creating a Definer Function

~~~sql
CREATE FUNCTION public.try_read_count_privileged()
RETURNS bigint
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, sensitive_schema, pg_temp
AS $$
    SELECT COUNT(*) FROM sensitive_schema.hidden_table
$$;
~~~

If the owner holds read access to the table and the caller holds `EXECUTE`, the query succeeds even though the caller lacks direct `SELECT` privilege.

### 3.3. Key Privilege Distinctions

| Privilege / Attribute | When Is It Checked? |
| --- | --- |
| `USAGE` on schema containing function | Needed by caller to resolve/call the function by name |
| `EXECUTE` on function | Needed by caller to invoke the function |
| `SELECT/INSERT/UPDATE/DELETE` on inner tables | Under `SECURITY DEFINER`, checked against the definer owner |
| Owner role memberships and grants | Determine actual effective internal privileges |
| RLS policies | Depend on effective role, table owner/`BYPASSRLS`, and policy rules |
| Runtime schema/object name resolution | Depends on statements, resolution order, and ownership |

Granting `EXECUTE` does not grant direct table `SELECT`. Conversely, even without direct `SELECT`, if a function dumps sensitive data in its return value, **the function still leaks data through its output**.

### 3.4. Full Signatures and Overloaded Functions

PostgreSQL supports function overloading:

~~~sql
get_stock(text)
get_stock(integer)
~~~

`GRANT EXECUTE ON FUNCTION` requires specifying the exact signature, such as `get_stock(text)`. When multiple overloads share a name, never assume granting or revoking one signature covers all of them.

## 4. CURRENT_USER, SESSION_USER, and SET ROLE

Three related but distinct concepts:

- `session_user`: the original session identity per PostgreSQL rules (usually the login role), mutable only through permitted operations.
- `current_user`: the active role checked for SQL permissions; changes via `SET ROLE` or while executing a `SECURITY DEFINER` function.
- `current_role`: in PostgreSQL, generally synonymous with `current_user`.

### 4.1. Inspecting Current Identity

~~~sql
SELECT
    session_user,
    current_user,
    current_role;
~~~

Without `SET ROLE` and outside definer functions, all three usually match the login role.

### 4.2. SET ROLE

~~~sql
-- Only when the current role is allowed to SET ROLE:
SET ROLE some_allowed_role;
SELECT session_user, current_user;
RESET ROLE;
~~~

`SET ROLE` depends on role membership and authorization; roles cannot arbitrarily switch to any role they please. It changes the effective role for statements executed outside definer functions.

### 4.3. Inside SECURITY DEFINER

~~~sql
CREATE FUNCTION public.inspect_execution_identity()
RETURNS TABLE (
    session_identity name,
    effective_identity name
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT session_user, current_user
$$;
~~~

When a low-privilege role calls this function (if granted `EXECUTE`), `current_user` inside becomes **the function owner**, while `session_user` reflects the session identity.

### 4.4. Authorization Trap With current_user

**Misguided** design pattern:

~~~sql
-- Inside SECURITY DEFINER:
-- WHERE resource_owner = current_user
~~~

If the goal was restricting rows to the caller, this expression evaluates against the **definer owner**, not the caller—causing broken behavior or resource exposure.

### 4.5. SESSION_USER Does Not Represent Web End Users Either

In applications using connection pools, thousands of HTTP users share **one database service login role**. Here `session_user` is merely the service role, not the website user's `user_id`. Never rely on `session_user` for end-user authorization unless DB connections map 1:1 to individual users.

### 4.6. Custom GUCs Are Not Automatically Trustworthy

Some frameworks pass `user_id` via `current_setting('app.user_id')`. If a caller can execute arbitrary SQL and alter that custom GUC, they can spoof identities. Before using GUCs inside `SECURITY DEFINER` authorization, verify **who can set the value**, middleware trustworthiness, and protection against injection/escalation.

### 4.7. Safe Direction

Base authorization on a verified identity source (the caller's true DB role, authenticated service context, token validated by a trusted tier, or database-enforced policy). Never treat a plain caller-supplied string as proof of authorization.

## 5. Default EXECUTE Privileges: A Commonly Overlooked Risk

By default, PostgreSQL typically grants **`EXECUTE` on newly created functions to `PUBLIC`**. `PUBLIC` is the conceptual set of all roles—not the `public` schema.

### 5.1. Two Different Meanings of "public"

| Concept | Meaning |
| --- | --- |
| Role `PUBLIC` in `GRANT/REVOKE` | All roles |
| Schema `public` | An actual schema inside the database |

`REVOKE EXECUTE ON FUNCTION ... FROM PUBLIC` revokes the default execution grant from **all roles** in the ACL without affecting the `public` schema.

### 5.2. Avoid Leaving Unintended Execution Windows

Risky pattern:

~~~sql
CREATE FUNCTION sensitive_api.do_privileged_work(...)
RETURNS ...
LANGUAGE plpgsql
SECURITY DEFINER
AS $$ ... $$;

-- Only later:
REVOKE ALL ON FUNCTION sensitive_api.do_privileged_work(...) FROM PUBLIC;
~~~

Between those two separately committed statements, the function may temporarily carry broader default execution permissions than intended (depending on schema, database, and role grants).

### 5.3. Create and Revoke Within the Same Transaction

~~~sql
BEGIN;

CREATE FUNCTION sensitive_api.read_limited_data(p_id bigint)
RETURNS bigint
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, trusted_private, pg_temp
AS $$
    SELECT id
    FROM trusted_private.records
    WHERE id = p_id
$$;

REVOKE ALL ON FUNCTION
    sensitive_api.read_limited_data(bigint)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
    sensitive_api.read_limited_data(bigint)
TO designated_app_role;

COMMIT;
~~~

This is a **deployment syntax template**; the schemas, roles, and tables shown are not created yet. Keeping DDL and privilege updates in one transaction prevents exposing the function under default grants between commits.

### 5.4. EXECUTE Does Not Replace Schema USAGE

To invoke `sensitive_api.read_limited_data(...)` by name, the caller also needs `USAGE` on schema `sensitive_api`. However, withholding schema `USAGE` **must not be your sole control**, since function ACLs themselves would remain overly permissive and a future `GRANT USAGE` could inadvertently expose unrelated functions.

### 5.5. GRANT EXECUTE Only for Exact Signatures

~~~sql
GRANT EXECUTE ON FUNCTION
    sensitive_api.read_limited_data(bigint)
TO designated_app_role;
~~~

Avoid running `GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA ... TO PUBLIC` on schemas holding privileged routines without thorough review.

### 5.6. ALTER DEFAULT PRIVILEGES

For a role dedicated to deploying sensitive functions, consider configuring:

~~~sql
-- Executed by DBA/owner for the role creating functions:
ALTER DEFAULT PRIVILEGES FOR ROLE designated_function_owner
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
~~~

This alters **default privileges for future functions created by that role**; it does not revoke permissions on existing functions.

Distinguish **global default privileges** from schema-specific default privileges: revoking solely at a per-schema layer may not override global defaults. Audit the actual default ACL rules and whichever role **creates** functions—especially if deployments execute `SET ROLE`.

### 5.7. Functions vs. Procedures

`SECURITY DEFINER` also applies to procedures, yet **`SECURITY DEFINER` procedures cannot execute internal transaction-control statements (`COMMIT`/`ROLLBACK`)** under PostgreSQL rules. Never try to use a definer procedure to escape caller transaction control.

## 6. Threat Model: What Can Callers Control?

Before introducing `SECURITY DEFINER`, document **every input or surface under caller control**.

| Input / Surface | Risk |
| --- | --- |
| `text`, `jsonb`, `uuid` parameters | SQL injection if concatenated; manipulable authorization logic |
| Session `search_path` | Unqualified object names may resolve to untrusted objects unless pinned |
| Temporary tables | Can shadow unqualified tables unless `pg_temp` is safely positioned |
| Schemas allowing untrusted `CREATE` | Forged tables/functions/operators injected into name resolution |
| Dynamic schema/table/column parameters | Dynamic SQL identifier injection |
| Owner role | Excessive privileges (`SUPERUSER`/`BYPASSRLS`/all-table owner) amplify blast radius |
| `EXECUTE`/`USAGE` grants | Function callable by unauthorized roles |
| Function overloads or default arguments | Invoking unintended overloads or bypassing ACLs on one signature |
| Return values / exceptions / logs | Leaking confidential columns or row existence |
| Nested `SECURITY DEFINER` helpers | Unintended chained privilege escalation |
| RLS / table ownership | Bypassing policies when executing as owner |
| Triggers / views / FDWs | Indirect SQL causing side effects or out-of-scope reads |

### 6.1. What Needs Protection?

**Not just confidential columns**, but also transaction state, locks, CPU resources, logs, and auxiliary tables. Even a function returning a single integer poses risk if callers can trigger unbounded updates, lock thousands of rows, or exploit timing channels.

### 6.2. Boundaries PostgreSQL Cannot Infer Automatically

The database does not inherently know which web user placed an order, which tenant owns which resource, or per-customer quotas. Your function must enforce those business rules explicitly or rely on a trusted authorization layer. `SECURITY DEFINER` changes **the SQL execution role**, not application policy.

## 7. search_path: The Highest-Risk Surface of SECURITY DEFINER

`search_path` lists the schemas PostgreSQL searches when resolving **object names lacking a schema prefix**. For example:

~~~sql
SELECT available_units FROM inventory;
~~~

`inventory` has no explicit schema. PostgreSQL resolves it using `search_path`. Inside a low-privilege function, resolving the wrong name usually fails or hits caller data. Inside **`SECURITY DEFINER`**, resolving to an attacker-controlled object executes inside an elevated security context.

### 7.1. Mechanics of Object Shadowing

~~~text
SECURITY DEFINER function runs SQL:
    SELECT value FROM inventory;
                  (not schema-qualified)
         |
         +-- search_path contains untrusted schema
         |
         +-- another relation named "inventory" exists
         |
         +-- name resolves to unintended object
~~~

This is **name-resolution hijacking**. If the privileged routine acts on data returned by a spoofed object, the impact can be severe.

### 7.2. Any Schema Allowing CREATE Can Be Manipulated

A schema is untrusted if untrusted roles can `CREATE` or replace objects inside it. Leaving such a schema in a `SECURITY DEFINER` function's `search_path` allows external actors to influence object resolution.

Areas to audit:

- The `public` schema or shared namespaces;
- Schemas where applications allow tenants/users to create objects;
- Extension schemas writable by multiple roles;
- Session temporary schemas;
- Any schema with overly broad `CREATE` grants.

### 7.3. Distinguishing USAGE vs. CREATE on Schemas

| Privilege | Meaning |
| --- | --- |
| `USAGE ON SCHEMA` | Allows looking up/resolving objects in the schema, subject to object privileges |
| `CREATE ON SCHEMA` | Allows creating objects inside the schema |
| `SELECT ON TABLE` | Allows reading table data subject to column/RLS rules |
| `EXECUTE ON FUNCTION` | Allows calling a specific function |

**Never grant `CREATE` on schemas trusted by privileged code** to untrusted roles. Grant only `USAGE` where callers need access to reviewed functions.

### 7.4. PostgreSQL 15 and the public Schema

Versions and upgraded databases vary in **default `CREATE` permissions on `public`**. PostgreSQL 15 tightened defaults for newly created databases, whereas databases upgraded from older major versions retain historical ACLs. **Always inspect live ACLs** instead of assuming `public` is safe based on server version.

### 7.5. Safe SET search_path Pattern

A standard pattern recommended by PostgreSQL documentation:

~~~sql
SECURITY DEFINER
SET search_path = trusted_schema, pg_temp
~~~

Here:

- `trusted_schema` contains only objects controlled by trusted roles.
- `pg_temp` is placed **last** so temporary tables cannot override trusted relations.
- `pg_catalog` follows special rules; listing it **explicitly first** makes auditing clearer.

An even more explicit form used throughout this article:

~~~sql
SECURITY DEFINER
SET search_path = pg_catalog, sec389_private, pg_temp
~~~

### 7.6. Why Include pg_temp Even When No Temp Tables Are Used?

If a session's temporary schema exists and `pg_temp` is **not explicitly listed** in `search_path`, PostgreSQL applies special priority rules: the temporary schema can be searched **ahead of** other schemas when resolving **relation and data type names**.

Explicitly listing `pg_temp` **last** fixes the lookup order for tables and data types, stopping temporary relations from shadowing trusted relations ahead of them.

### 7.7. pg_temp Does Not Apply Equally to Function/Operator Lookup

The temporary schema's special priority applies primarily to relations and data types; PostgreSQL does not search `pg_temp` the same way for **function and operator names**. Still, function and operator hijacking remains a real risk from **other schemas holding `CREATE` grants** earlier in `search_path`.

### 7.8. Protecting pg_catalog

`pg_catalog` holds built-in system functions, operators, and catalog objects. PostgreSQL normally searches `pg_catalog` implicitly before other schemas when unlisted. However, explicitly putting `pg_catalog` after an untrusted schema lets objects in that earlier schema shadow built-ins.

Clear, transparent form:

~~~sql
SET search_path = pg_catalog, sec389_private, pg_temp
~~~

Never put an untrusted schema **ahead of `pg_catalog`** in a `SECURITY DEFINER` function.

### 7.9. Schema-Qualified Names Add Defense-in-Depth

~~~sql
-- Unclear which schema holds inventory:
SELECT available_units FROM inventory;

-- Explicitly qualified relation:
SELECT available_units FROM sec389_private.inventory;
~~~

Even with `search_path` pinned, **schema-qualifying key tables and functions** simplifies auditing and code review. Still, qualification does not cure SQL injection, over-privileged owners, or broken authorization checks.

### 7.10. Risks From Functions, Operators, Casts, and Overload Resolution

Tables are not the only lookup targets:

~~~sql
SELECT transform_input(p_text);
~~~

If `transform_input` resolves through a schema writable by untrusted users, execution can divert to malicious code. Operators, overloads, and default arguments undergo complex resolution rules. Defend with **trusted search paths, strongly typed arguments, and explicit function/operator qualification where needed**, not merely quoting input strings.

### 7.11. Never Include Client-Writable Schemas in search_path

Even a read-only `SELECT` function turns dangerous if an object or function resolves to user-controlled code while executing under definer privileges. Never let callers choose `search_path` schemas or object names arbitrarily.

## 8. Three-Role Separation Lab

Let us build an **educational-only** inventory example using three roles with distinct responsibilities:

| Role | Responsibility | Intended Privileges |
| --- | --- | --- |
| `sec389_data_owner` | Internal table owner | Owns private schema and table |
| `sec389_fn_owner` | `SECURITY DEFINER` API owner | Allowed to read only required columns |
| `sec389_app` | API caller role | Holds only `USAGE` on API schema and `EXECUTE` on one function |

All three roles are created **`NOLOGIN`** in the lab to demonstrate role/privilege boundaries. In real deployments, the service login role may inherit `sec389_app`, never `sec389_fn_owner` or `sec389_data_owner`.

**Environment prerequisites:** a DBA or role holding `CREATEROLE`, schema creation, and `SET ROLE` capabilities is required to run full provisioning. If you are practicing in a limited student lab database, treat the role-creation commands as reference design and ask your DBA to provision roles safely. Never run lab scripts in production without change approval.

### 8.1. DBA Creates Roles

~~~sql
-- Run with appropriate administrative rights in a lab database.
CREATE ROLE sec389_data_owner NOLOGIN;
CREATE ROLE sec389_fn_owner NOLOGIN;
CREATE ROLE sec389_app NOLOGIN;
~~~

Never assign `SUPERUSER`, `BYPASSRLS`, or `CREATEROLE` to a definer owner. Deployment accounts permitted to `SET ROLE` into owners should be tightly restricted to controlled CI/CD/DBA workflows, never granted to runtime apps.

### 8.2. Create Private and API Schemas

~~~sql
-- Executed by DBA in lab database:
CREATE SCHEMA sec389_private AUTHORIZATION sec389_data_owner;
CREATE SCHEMA sec389_api AUTHORIZATION sec389_fn_owner;

REVOKE ALL ON SCHEMA sec389_private FROM PUBLIC;
REVOKE ALL ON SCHEMA sec389_api FROM PUBLIC;

GRANT USAGE ON SCHEMA sec389_api TO sec389_app;
~~~

The app role can resolve objects in `sec389_api`, yet holds **no `USAGE` on `sec389_private`**. Note that schema `USAGE` alone does not grant `EXECUTE` on functions inside—function ACLs (especially default `PUBLIC EXECUTE`) must be configured explicitly.

### 8.3. Data Owner Creates the Internal Table

~~~sql
-- Deployment session permitted to assume data owner.
SET ROLE sec389_data_owner;

CREATE TABLE sec389_private.inventory (
    sku text PRIMARY KEY,
    available_units integer NOT NULL
        CHECK (available_units >= 0),
    cost_price numeric(12,2) NOT NULL
        CHECK (cost_price >= 0),
    is_public boolean NOT NULL DEFAULT false
);

INSERT INTO sec389_private.inventory(
    sku, available_units, cost_price, is_public
)
VALUES
    ('KB-001', 17, 350000, true),
    ('MS-002', 0, 120000, true),
    ('INTERNAL-001', 200, 98000, false);

RESET ROLE;
~~~

If `SET ROLE` fails due to lack of privilege, halt provisioning and fix deployment role memberships properly; **never** work around it with `GRANT SUPERUSER` or giving owner roles to runtime accounts.

### 8.4. Grant Column-Level Privileges Only to the Function Owner

~~~sql
-- Executed by DBA or authorized data owner:
GRANT USAGE ON SCHEMA sec389_private
TO sec389_fn_owner;

GRANT SELECT (sku, available_units, is_public)
ON TABLE sec389_private.inventory
TO sec389_fn_owner;
~~~

`sec389_fn_owner` cannot `SELECT` `cost_price` under these grants, nor can it `INSERT`, `UPDATE`, or `DELETE` on the table.

**Note:** real effective privileges can also come from role memberships or other grants. A clean lab with three fresh roles isolates behavior clearly, whereas in production you must audit all **inherited** grants on the definer owner, not only the statements in one script.

### 8.5. Function Owner Creates API, Revokes PUBLIC, and Grants Execute Atomically

~~~sql
-- Deployment identity authorized to SET ROLE sec389_fn_owner.
SET ROLE sec389_fn_owner;

BEGIN;

CREATE FUNCTION sec389_api.get_available_stock(p_sku text)
RETURNS integer
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, sec389_private, pg_temp
AS $$
    SELECT i.available_units
    FROM sec389_private.inventory AS i
    WHERE i.sku = p_sku
      AND i.is_public = true
$$;

REVOKE ALL ON FUNCTION
    sec389_api.get_available_stock(text)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
    sec389_api.get_available_stock(text)
TO sec389_app;

COMMIT;

RESET ROLE;
~~~

If your session lacks `SET ROLE`, a DBA should execute this through an approved deployment pipeline; these examples never grant owner membership to runtime accounts.

### 8.6. Why Separate the Function Owner From the Table Owner?

If `sec389_fn_owner` also owned the table with full privileges, any flaw in the function would expose **full owner control**. Separating owners shrinks blast radius:

~~~text
sec389_app
  |
  +-- EXECUTE get_available_stock(text)
         |
         +-- SECURITY DEFINER -> sec389_fn_owner
                |
                +-- USAGE sec389_private
                +-- SELECT sku, available_units, is_public
                X  No SELECT on cost_price
                X  No UPDATE/DELETE on inventory
~~~

This is **defense in depth**: even if the function were tricked into running unintended SQL, the owner role itself lacks full table rights (assuming no hidden inherited memberships grant them).

### 8.7. Calling as the Application Role

~~~sql
-- Run only in a lab session authorized for SET ROLE sec389_app:
SET ROLE sec389_app;

SELECT sec389_api.get_available_stock('KB-001')
    AS available_units;

SELECT sec389_api.get_available_stock('MS-002')
    AS available_units;

SELECT sec389_api.get_available_stock('INTERNAL-001')
    AS available_units;

RESET ROLE;
~~~

Expected output: **17**, **0**, and **SQL NULL** respectively. `INTERNAL-001` exists, yet `is_public=false`, so the function suppresses stock availability just as if the SKU did not exist.

### 8.8. Attempting Direct Table Access as the App Role

~~~sql
-- Run separately in lab to observe denial, then RESET ROLE:
SET ROLE sec389_app;

SELECT * FROM sec389_private.inventory;
-- Expected schema/table permission denied error.

RESET ROLE;
~~~

This is an **authorization test**, not a valid query for applications to attempt. Inside an explicit transaction, a failed statement puts the transaction into an aborted state requiring `ROLLBACK` before issuing more commands.

### 8.9. What This Lab Proves

- The app can **invoke a specific approved function**.
- The app cannot read the internal table directly.
- The function exposes **strictly one attribute** and only for public rows.
- Even the function owner cannot select `cost_price`.
- Owner roles, schemas, and function ACLs form distinct layers of control.
- Security does not depend on client code "politely refraining from selecting the table".

### 8.10. What This Lab Does Not Prove Automatically

This minimal setup **does not** automatically guarantee:

- Per-HTTP-user or per-tenant authorization;
- Rate limiting against millions of calls;
- Side-channel immunity against timing/error inference;
- Protection if another role holds broad inherited privileges;
- Controls preventing deployment accounts from modifying the function maliciously;
- Multi-tenant RLS or row ownership checks;
- Immutable audit trails and compliance retention.

Those architectural and operational concerns are covered in the sections below.

## 9. Classic Mistake: Unqualified Table Reads Inside a Function

### 9.1. Pattern Vulnerable to search_path Manipulation

~~~sql
-- Never write a SECURITY DEFINER function like this:
CREATE FUNCTION sec389_api.unsafe_stock_lookup(p_sku text)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_stock integer;
BEGIN
    SELECT available_units INTO v_stock
    FROM inventory
    WHERE sku = p_sku;

    RETURN v_stock;
END;
$$;
~~~

This function **does not pin `search_path`**, and `inventory` has no schema qualifier. If the caller controls `search_path` or creates temporary relations, `inventory` can resolve to an unintended table.

### 9.2. Conceptual Attack Flow

~~~text
Caller creates identically named object in a caller-controlled namespace
       |
Caller alters search_path / creates temporary relation
       |
CALL security-definer function
       |
Function references "inventory" unqualified
       |
Name resolution picks caller's object
       |
Privileged logic reads/processes spoofed data
~~~

In simple queries, shadowing merely corrupts results; in complex routines, it can drive downstream privileged SQL actions. **Never wait for an exploit to treat missing `search_path` hardening as a defect.**

### 9.3. Fixed Scoped Version

~~~sql
CREATE FUNCTION sec389_api.safe_stock_lookup(p_sku text)
RETURNS integer
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, sec389_private, pg_temp
AS $$
DECLARE
    v_stock integer;
BEGIN
    SELECT i.available_units INTO v_stock
    FROM sec389_private.inventory AS i
    WHERE i.sku = p_sku
      AND i.is_public = true;

    RETURN v_stock;
END;
$$;
~~~

**Deployment reminder:** if deploying this function for real, remember to `REVOKE EXECUTE FROM PUBLIC` and grant the appropriate role **in the same transaction** just like in the lab.

### 9.4. Never Treat Schema Qualification as Complete Security

Even after writing `sec389_private.inventory`, still audit:

- Is the function owner over-privileged?
- Does the function run dynamic SQL via `EXECUTE`?
- Are any helper function calls unqualified?
- Does it expose rows across all tenants?
- Can return values or exceptions leak `cost_price`?
- Is `EXECUTE` still open to `PUBLIC`?
- Are untrusted schemas or extension objects reachable?

A one-line fix closes one risk vector, not an entire security review.

## 10. SQL Injection Inside SECURITY DEFINER: Two Distinct Layers

A privileged function may be invoked safely via bound parameters:

~~~sql
SELECT sec389_api.get_available_stock($1);
~~~

Parameterized calls block injection at the caller boundary. However, if **inside the function body** parameters get concatenated into dynamic SQL executed via `EXECUTE`, SQL injection re-emerges inside the definer context.

### 10.1. Wrong Pattern: Concatenating Values into Query Strings

~~~sql
-- Never deploy this pattern:
--
-- EXECUTE
--     'SELECT available_units FROM sec389_private.inventory
--      WHERE sku = ''' || p_sku || '''';
~~~

If `p_sku` contains quotes or SQL syntax, the generated statement breaks out of the literal. Inside a `SECURITY DEFINER` routine, attacker-controlled SQL runs under **the owner's privileges**, making impact worse than in a typical invoker query.

### 10.2. Right Pattern: Parameterized Static SQL

When tables and columns are fixed, **avoid dynamic SQL altogether**:

~~~sql
SELECT i.available_units INTO v_stock
FROM sec389_private.inventory AS i
WHERE i.sku = p_sku
  AND i.is_public = true;
~~~

PL/pgSQL binds `p_sku` natively as a typed variable without string concatenation.

### 10.3. Right Pattern When Dynamic SQL Is Truly Necessary

~~~sql
-- Inside a PL/pgSQL function:
EXECUTE
    'SELECT available_units
     FROM sec389_private.inventory
     WHERE sku = $1
       AND is_public = true'
INTO v_stock
USING p_sku;
~~~

`USING p_sku` passes a **data value**, not concatenated SQL text. `$1` is bound natively by PL/pgSQL `EXECUTE ... USING`, not manual string replacement.

### 10.4. Identifiers Cannot Be Bound as Values

Table or column names **cannot be substituted via `$1`** in syntactic identifier slots. If selecting a relation dynamically is genuinely required:

~~~sql
-- Conceptual pattern; p_table has already passed an allowlist:
EXECUTE format(
    'SELECT available_units FROM %I.%I
     WHERE sku = $1 AND is_public = true',
    'sec389_private',
    p_table
)
INTO v_stock
USING p_sku;
~~~

`%I` applies identifier quoting in `format()`. While it stops strings from breaking out into SQL syntax, **it is not authorization**: validate `p_table` against an explicit **allowlist of permitted tables**.

### 10.5. Why Identifier Quoting Alone Is Insufficient

If callers can supply any table name accessible to a broad owner role, a safely quoted identifier can still target an internal table **never meant to be exposed**. Always enforce both an **allowlist and business authorization**, not just SQL injection syntax defense.

### 10.6. Combining format %L and USING

`format('%L', p_value)` safely quotes SQL literals, though for regular values in PL/pgSQL `EXECUTE ... USING` is cleaner and preserves data types better. Never mix identifiers and values indiscriminately in unformatted strings.

### 10.7. Never Let Users Choose Arbitrary Schema or Function Names

An API accepting `target_function text` and executing it with definer rights effectively becomes an **arbitrary privileged operation dispatcher**. If three operations are allowed, model them as three explicit branches or three separately granted functions.

## 11. Separate Privileges by Function Role, Not Owner Convenience

A common anti-pattern:

~~~text
security_definer_owner
  ├── SUPERUSER
  ├── BYPASSRLS
  ├── owns every table
  ├── can create extensions, schemas, roles
  └── owns every privileged function
~~~

If one function has a flaw, the attacker gains leverage over nearly the entire database. Separating owners and grants **limits blast radius**.

### 11.1. Attributes to Avoid on Function Owners

- `SUPERUSER`;
- `BYPASSRLS`, unless explicitly required and audited;
- `CREATEROLE`, `CREATEDB`, `REPLICATION`, or unrelated infrastructure privileges;
- Membership in broad admin roles;
- `CREATE` on unused schemas;
- `SELECT` on sensitive columns outside the output contract;
- `UPDATE`/`DELETE` when the function only needs `SELECT`.

### 11.2. Inspecting Role Attributes

~~~sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreaterole,
    rolcreatedb,
    rolreplication,
    rolbypassrls,
    rolinherit
FROM pg_catalog.pg_roles
WHERE rolname IN (
    'sec389_data_owner',
    'sec389_fn_owner',
    'sec389_app'
)
ORDER BY rolname;
~~~

This returns role metadata visible to the session. Evaluate `rolinherit` alongside memberships and direct grants; an owner that looks "restricted" may **inherit** broad privileges from another group role.

### 11.3. NOLOGIN Does Not Mean Unusable for Escalation

`NOLOGIN` stops direct authentication as that role. However, if any login role can `SET ROLE` into it or a `SECURITY DEFINER` function runs as that owner, its privileges remain active. **`NOLOGIN` reduces direct attack surface**, without replacing membership and `EXECUTE` governance.

### 11.4. Separate Read Owners From Write Owners

If one function reads public stock while another deducts inventory, **avoid sharing a single owner role needlessly**. Giving the read API owner strictly `SELECT` and giving the stock-reservation owner minimal `UPDATE`/`SELECT` contains damage if either routine is flawed.

### 11.5. Separate Deployers From Callers

Deployment roles create or alter functions; runtime roles only `EXECUTE` them. Never grant the runtime role:

~~~sql
GRANT sec389_fn_owner TO sec389_app;
~~~

because membership inheritance or `SET ROLE` defeats role separation. To let an app call a function, **`GRANT EXECUTE`**—never make the app a member of the owner.

### 11.6. Changing Ownership Is a Security-Critical Change

~~~sql
-- Run only by an authorized role following security review:
ALTER FUNCTION sec389_api.get_available_stock(text)
OWNER TO some_other_role;
~~~

Changing a `SECURITY DEFINER` function's owner changes **the exact privileges active inside its SQL**, including RLS and table-ownership behavior. It is never a harmless metadata tweak. Audit the new owner's privileges, dependencies, and grants before and after migration.

### 11.7. Never Use SECURITY DEFINER to Mask Every "permission denied"

When you hit `permission denied`, find the root cause: missing schema `USAGE`? missing table `SELECT`? view security settings? RLS policy? missing function grants? Use `SECURITY DEFINER` strictly when designing a purposefully restricted privileged API. Flipping random functions to `SECURITY DEFINER` just to "make errors disappear" opens unintended privilege escalation paths.

## 12. RLS and SECURITY DEFINER: A Critical Warning

**Row-Level Security** (*RLS*) restricts which rows a role can view or modify per policies. Because `SECURITY DEFINER` switches the effective execution role, **RLS will evaluate against a different role than the caller**.

### 12.1. Table Owners Bypass RLS by Default

PostgreSQL normally lets a table owner **bypass row security** on tables they own unless `FORCE ROW LEVEL SECURITY` is active. Superusers and `BYPASSRLS` roles also bypass RLS under PostgreSQL privilege rules.

### 12.2. Typical Risk Scenario

~~~text
Caller restricted to tenant A by RLS
        |
        +-- calls SECURITY DEFINER function
              |
              +-- function owner owns the table or holds BYPASSRLS
              |
              +-- inner SQL can read tenant B rows
~~~

Unless the function enforces tenant filtering itself, it can expose data outside the caller's authorized scope.

### 12.3. What Defense Does Our Lab Already Have?

`sec389_fn_owner` **does not own** `sec389_private.inventory`; it holds only column-level `SELECT`. This prevents accidental default owner bypass; if RLS is turned on for that table, explicit policies for `sec389_fn_owner` are required rather than assuming rows will stay visible.

### 12.4. Optional Example Enabling RLS on the Lab Table

~~~sql
-- Only in the lab database, executed by table owner or DBA:
ALTER TABLE sec389_private.inventory
ENABLE ROW LEVEL SECURITY;

CREATE POLICY p_public_inventory_for_fn_owner
ON sec389_private.inventory
FOR SELECT
TO sec389_fn_owner
USING (is_public = true);
~~~

Now the function owner—neither table owner nor `BYPASSRLS`—must satisfy the policy to read rows, adding defense-in-depth alongside the `is_public = true` filter inside the function.

### 12.5. FORCE ROW LEVEL SECURITY Is Not a Silver Bullet

~~~sql
-- Optional depending on business needs and privileges:
ALTER TABLE sec389_private.inventory
FORCE ROW LEVEL SECURITY;
~~~

`FORCE` subjects normal table owners to RLS, yet **does not stop `BYPASSRLS`/superusers or fix flawed policies**. It can also impact owner maintenance jobs; always test operational workflows.

### 12.6. Beware Policies Relying on current_user

Inside a `SECURITY DEFINER` function, `current_user` is **the function owner**, not the caller. An RLS policy referencing `current_user` evaluates against the definer identity when invoked from definer SQL. Never build tenant isolation assuming `current_user` equals the HTTP caller inside definer code.

### 12.7. Never Accept tenant_id Blindly

~~~sql
-- Risky if lacking real authorization checks:
-- SELECT * FROM private.orders WHERE tenant_id = p_tenant_id;
~~~

If callers can pass arbitrary `p_tenant_id` values, they can read another tenant's orders. Validate against a **trusted identity source**, DB-enforced policy, or verified backend context.

### 12.8. SECURITY DEFINER Does Not Uniformly Disable or Enforce RLS

Depending on the owner and table ownership, a definer function may obey RLS, bypass RLS, or hit different policies than the caller. **Never assume "SECURITY DEFINER always bypasses RLS" or "it always inherits caller RLS"**.

## 13. Views, Triggers, and Helper Functions Under Definer Rights

A `SECURITY DEFINER` function may call helper SQL functions, `UPDATE` a table (firing triggers), or query views.

### 13.1. Privileges Evaluate Across Multiple Layers

~~~text
SECURITY DEFINER api_function()
  |
  +-- SELECT view_x
  |      └── view's own owner/invoker/RLS rules apply
  |
  +-- UPDATE table_y
  |      └── trigger functions run under their own SECURITY INVOKER/DEFINER
  |
  +-- CALL helper_function()
         └── if helper is INVOKER, runs under current definer context
~~~

A `SECURITY INVOKER` helper invoked inside a definer function runs under the **active effective role** (the definer owner), not the original HTTP user. Therefore, audit the entire **call graph**, not just the top-level function.

### 13.2. Triggers Can Expand Side Effects

If a definer function updates a table, an `AFTER` trigger on that table might write audit rows or invoke procedures. Total execution effects may exceed what the top-level SQL visibly shows.

During review, inspect:

- Triggers on all modified tables;
- Foreign key cascades;
- View definitions;
- Invoked functions and operators;
- Default expressions and generated columns calling functions;
- RLS policies and relation owners.

### 13.3. SECURITY DEFINER on Trigger Functions

Trigger functions can also be declared `SECURITY DEFINER`, such as writing audit logs with dedicated privileges. Each such trigger is another privilege boundary needing safe `search_path`, minimal owner privileges, and controlled management. Note that it does not gain an independent transaction; rolling back the triggering statement rolls back trigger writes too.

### 13.4. Never Turn SECURITY DEFINER into a "Backend Admin Proxy"

A function taking arbitrary table names or actions:

~~~sql
-- Never do this:
-- EXECUTE 'DELETE FROM ' || p_table_name;
~~~

effectively exposes an administrative shell running with definer privileges. Build narrow, strongly typed APIs with allowlists, authorization checks, and quotas.

### 13.5. SECURITY DEFINER and Procedure Transaction Control

Regular PostgreSQL functions cannot issue `COMMIT`/`ROLLBACK`. Even `SECURITY DEFINER` procedures **cannot execute internal transaction control**. Never attempt to "persist writes even when the caller rolls back" using a definer wrapper; that belongs to transaction/outbox architecture, not privilege elevation.

## 14. Privileged Write APIs: Authorization Matters Beyond SQL Injection

Suppose you write:

~~~sql
-- Pseudocode; not a production-ready API:
-- UPDATE sec389_private.inventory
-- SET available_units = available_units - p_qty
-- WHERE sku = p_sku;
~~~

If `sec389_app` can invoke this unrestricted, callers can **drain inventory arbitrarily** even without direct table `UPDATE` privileges.

### 14.1. Input Bounds Alone Are Not Enough

Adding:

~~~sql
IF p_qty < 1 OR p_qty > 20 THEN
    RAISE EXCEPTION 'invalid quantity';
END IF;
~~~

blocks extreme values, yet a caller can still **call it repeatedly** or deduct stock for SKUs unrelated to any authorized order.

### 14.2. Business Authorization Is Mandatory

A stock-reservation API needs at minimum:

- A valid order owned/authorized for the caller;
- A unique request/idempotency key;
- Verification that the SKU belongs to that order;
- Quantities within allowed bounds;
- Order status permitting reservation;
- Idempotency protection against double deduction;
- Atomic `UPDATE` preventing negative stock races;
- Full transaction rollback on downstream order/reservation failures;
- Audit logs free of sensitive data leaks.

### 14.3. Atomic UPDATE Preventing Negative Stock

One piece of the logic looks like:

~~~sql
UPDATE sec389_private.inventory
SET available_units = available_units - p_qty
WHERE sku = p_sku
  AND available_units >= p_qty
  AND is_public = true
RETURNING available_units;
~~~

The guard prevents concurrency races far better than read-then-update, yet **still does not prove the caller is authorized to reserve stock**. Business authorization, idempotency, and workflow consistency remain essential.

### 14.4. Separate Write Owners Dedicated per Operation

For protected write APIs, consider a dedicated `sec389_reservation_owner` holding strictly `UPDATE (available_units)` and minimal reads, rather than reusing the stock-reading owner for sensitive mutations.

### 14.5. Never Leak Cost Price Through Error Messages

Avoid:

~~~sql
RAISE EXCEPTION 'cost_price=%', v_cost_price;
~~~

Return observable contract errors without exposing private table layouts or values. Apply strict access control and retention policies to DB logs as well.

### 14.6. Do Not Rely Strictly on SQLSTATE for Enumeration Prevention

Clear SQLSTATE codes help categorize failures, yet returning "SKU exists but you lack access" leaks record existence to unauthorized callers. Where anti-enumeration applies, prefer uniform messages like "not found or unavailable" aligned with product threat models.

## 15. Session State and Caller-Controlled Settings

Beyond function arguments, sessions carry configuration state:

- `search_path`;
- `role`/`current_user`;
- `row_security` (within role permissions);
- `TimeZone`, `DateStyle`, formatting settings;
- Temporary relation names;
- Custom application GUCs;
- Prepared statements and pooled session state.

### 15.1. Pin search_path Directly on the Function

~~~sql
SET search_path = pg_catalog, sec389_private, pg_temp
~~~

in the function definition establishes function-level configuration during execution, independent of the caller's session `search_path`.

### 15.2. Function-Level SET Clauses Wrap the Call

PostgreSQL applies settings declared on the function definition for the call duration and restores prior GUC state afterward per GUC rules. This isolates `search_path`, though it does not automatically sanitize unrelated caller-supplied settings.

### 15.3. Session Pooling

An HTTP request may receive a pooled connection retaining `SET ROLE` or custom GUCs from an earlier request. Without proper pool state reset, authorization context leaks across requests. Enforce transaction-scoped state, reliable pool cleanup, and minimal service-role privileges—never trust an arbitrary caller-writable GUC inside a `SECURITY DEFINER` routine as proof of identity.

### 15.4. Never Lower Guards With Dynamic SET search_path From Input

A function must not do:

~~~sql
-- Never do this inside SECURITY DEFINER:
-- PERFORM set_config('search_path', p_schema_from_user, true);
~~~

as that hands name resolution control back to the caller inside privileged code. If multi-tenant schema selection is truly required, use a strict allowlist and verified ownership mapping—though most systems are far safer using **a single controlled schema paired with verified `tenant_id` scoping**.

### 15.5. Cross-Tenant Leakage via Pooled Connections

Even with a locked `search_path`, relying on an un-reset or caller-modifiable session variable exposes cross-tenant data. Hardening a privilege boundary protects **context data** as well as object names.

## 16. Data Can Leak Through Multiple Channels

Direct `SELECT` access is not the only leakage channel:

| Channel | Example |
| --- | --- |
| Return value | Function exposes `cost_price` outside its contract |
| Row counts | Reveals how many confidential orders exist |
| Error messages | `RAISE EXCEPTION 'user X exists'` leaks account existence |
| Response latency | Timing differences reveal whether a matching row exists |
| `NOTICE`/logs | Logging SQL, secrets, keys, or private field values |
| Side effects | Writing auxiliary tables, emitting messages, touching external systems |
| Expensive queries | Repeated calls cause lock contention or DoS |
| Metadata exposure | Exposing internal schemas or signatures aids reconnaissance |

### 16.1. Define a Tight Output Contract

For instance, `get_available_stock(text) RETURNS integer` should return only:

- Available units for public SKUs;
- SQL `NULL` for nonexistent or non-public SKUs;
- Predictable validation errors revealing no internal data.

Never return `ROW(*)` or `to_jsonb(private_table)` when the contract asks for one integer.

### 16.2. Guard Against Enumeration

If a role can probe arbitrary SKUs repeatedly and observe counts or timings, it can harvest catalog inventory via dictionary attacks. Apply query scope limits, quotas/rate limits, and pre-read authorization checks where needed.

### 16.3. Logs Also Hold Sensitive Information

Database logs and application traces can capture:

- Function call arguments;
- SQL statements;
- Error context stacks;
- `RAISE NOTICE` messages;
- User/session identifiers.

Treat log access and retention with sensitive-data rigor. Never assume omitting a field from a result set keeps it inside the database.

### 16.4. External Side Effects Are Not Transaction-Safe

Table writes inside a `SECURITY DEFINER` function participate in the caller's transaction. However, if a function or helper invokes external systems via extensions or UDFs, external actions will not roll back if the DB transaction aborts. Use transactional outbox workers for post-commit side effects.

## 17. Transactions and SECURITY DEFINER

Functions run inside SQL statements **within the caller's active transaction**:

~~~sql
BEGIN;

SELECT sec389_api.get_available_stock('KB-001');

ROLLBACK;
~~~

A read function does not commit on its own. Even when a definer function writes to a table, those changes stay uncommitted inside the caller's transaction and **are undone if the caller rolls back**.

### 17.1. Higher Privileges Do Not Mean an Independent Transaction

~~~text
Caller BEGIN
   |
   +-- CALL/SELECT SECURITY DEFINER function
   |       └── inner SQL runs under definer privileges
   |
Caller ROLLBACK
   |
   └── Uncommitted data changes are discarded
~~~

**Privilege boundaries** and **transaction boundaries** are orthogonal mechanisms.

### 17.2. Functions Cannot Issue COMMIT

Regular PostgreSQL functions cannot execute `COMMIT` or `ROLLBACK`. A `SECURITY DEFINER` function has no special ability to terminate the caller's transaction.

### 17.3. SAVEPOINTs and Subtransactions

Callers may use savepoints in explicit transactions. Inside PL/pgSQL functions, `BEGIN ... EXCEPTION ... END` creates an internal subtransaction for local error handling. However, an `EXCEPTION` block cannot make prior statements commit independently of the outer transaction.

### 17.4. Handling Errors

If a definer function throws an unhandled exception inside an explicit caller transaction, the transaction enters an aborted state requiring `ROLLBACK` (or rollback to a prior savepoint). Do not issue further privileged calls inside an aborted transaction.

### 17.5. External Connections via Extensions

Some extensions open separate DB connections or trigger out-of-band side effects outside local transaction control. Never grant definer owners privileges to invoke such extensions unnecessarily, as they undermine rollback and authorization guarantees—another reason owners must remain minimal.

## 18. Function Attributes: VOLATILITY, LEAKPROOF, and PARALLEL

Functions carry attributes beyond `SECURITY DEFINER`:

~~~sql
CREATE FUNCTION ...
RETURNS ...
LANGUAGE ...
STABLE
SECURITY DEFINER
SET search_path = ...
AS $$ ... $$;
~~~

### 18.1. STABLE / VOLATILE / IMMUTABLE

| Attribute | Core Semantics |
| --- | --- |
| `VOLATILE` | Output can vary across calls; permits side effects where language/SQL allow |
| `STABLE` | Reads consistently within a single statement snapshot; must not cause write side effects |
| `IMMUTABLE` | Output depends purely on inputs and unchanging contract state |

A function reading `inventory` as data changes over time is **never `IMMUTABLE`**. Our lab marks it `STABLE` because it performs read-only lookups without modifying tables.

### 18.2. Never Falsely Declare IMMUTABLE for Optimization

Marking a function `IMMUTABLE` when it actually depends on permissions, session settings (`current_setting`), or mutable tables causes stale cached results in prepared plans or expression indexes. Declare accurate volatility first, then tune with real metrics.

### 18.3. LEAKPROOF Is Not an "Audited" Badge

`LEAKPROOF` is a highly sensitive attribute allowing the optimizer to evaluate the function ahead of security-barrier and RLS filters. Normally only superusers can set it, and it imposes strict requirements against leaking information via errors or timing.

**Never mark custom functions `LEAKPROOF` merely because you used `SECURITY DEFINER` or validated inputs.**

### 18.4. PARALLEL SAFE

Functions causing side effects, altering session state, or accessing parallel-restricted constructs must not casually be declared `PARALLEL SAFE`. Follow PostgreSQL's `PARALLEL UNSAFE`/`RESTRICTED`/`SAFE` rules carefully to prevent broken results or runtime failures.

### 18.5. COST / ROWS Are Planner Hints, Not Security

`COST` and `ROWS` help the planner estimate execution costs; they enforce no authorization, strip no owner privileges, and replace no validation. Even a scalar function requires `EXECUTE` ACLs and a safe `search_path`.

### 18.6. SQL Function Inlining Does Not Relax Privilege Contracts

Never rely on optimizer inlining or caching assumptions when reasoning about privilege checks. Design `SECURITY DEFINER` functions strictly around declared privilege semantics and `SET` isolation regardless of planner optimizations.

## 19. Migrating an Existing Function From INVOKER to DEFINER

PostgreSQL lets you modify existing functions via `ALTER FUNCTION`:

~~~sql
-- Only after full privilege audit, in a controlled migration:
ALTER FUNCTION sec389_api.get_available_stock(text)
SECURITY DEFINER;
~~~

However, **this is a major security shift**. SQL previously constrained by caller rights will now run under owner privileges. Latent flaws like dynamic SQL, unpinned `search_path`, or broad returns suddenly carry far greater impact.

### 19.1. Pre-ALTER Checklist

1. Who currently owns the function?
2. Which privileges does the owner hold on tables, sequences, and functions?
3. Does the body contain any unqualified object references?
4. Is a safe `SET search_path` pinned?
5. Is there any dynamic SQL or caller-supplied identifier?
6. Does it call helper functions or fire triggers?
7. Do `PUBLIC` or broad roles currently hold `EXECUTE`?
8. How do RLS, table ownership, and tenant policies interact?
9. Could outputs or exceptions leak sensitive data?
10. Have you tested under a low-privilege caller lacking direct table rights?

### 19.2. Avoid Multi-Commit Migration Gaps

Unsafe rollout sequence:

~~~text
ALTER FUNCTION ... SECURITY DEFINER; COMMIT;
-- Later commit: lock search_path / revoke PUBLIC EXECUTE.
~~~

Between those commits, the function runs as an unhardened privilege escalation point.

Prefer an atomic migration:

~~~sql
BEGIN;

-- Reviewed ALTER/CREATE OR REPLACE changes:
ALTER FUNCTION sec389_api.get_available_stock(text)
SET search_path = pg_catalog, sec389_private, pg_temp;

ALTER FUNCTION sec389_api.get_available_stock(text)
SECURITY DEFINER;

REVOKE ALL ON FUNCTION
    sec389_api.get_available_stock(text)
FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
    sec389_api.get_available_stock(text)
TO sec389_app;

COMMIT;
~~~

In practice, ownership changes or cross-owner grants may span separate administrative steps; ensure the privileged routine never goes live in an unprotected state.

### 19.3. CREATE OR REPLACE Preserves Existing ACLs

`CREATE OR REPLACE FUNCTION` preserves existing ownership and function ACLs; never assume replacing a function resets grants to safe defaults or reassigns ownership to the deployer. Re-verify ACLs, security mode, function-level `SET` settings, and owner after every replacement.

### 19.4. Overloading Can Leave Unintended Entry Points

Suppose a schema contains:

~~~text
sec389_api.get_stock(text)
sec389_api.get_stock(varchar)
sec389_api.get_stock(text, boolean DEFAULT true)
~~~

Multiple signatures complicate overload resolution and carry independent `EXECUTE` ACLs. Audit **every callable signature**, not just the primary overload documented for developers.

### 19.5. Changing Function Ownership Can Alter RLS Behavior

Running `ALTER FUNCTION ... OWNER TO new_owner` changes the effective execution role and RLS context. Even with identical SQL text, query output can change. Re-test under caller roles before and after ownership migrations.

## 20. Privileges on public and Extension Schemas

Many databases place shared functions, views, and extensions inside `public`. If a `SECURITY DEFINER` function uses unqualified names or relies on extension helpers inside user-writable schemas, hijacking surface grows.

### 20.1. Inspecting Schema ACLs

~~~sql
SELECT
    n.nspname AS schema_name,
    n.nspowner::regrole AS owner_role,
    n.nspacl
FROM pg_catalog.pg_namespace AS n
WHERE n.nspname IN (
    'public',
    'sec389_api',
    'sec389_private'
)
ORDER BY schema_name;
~~~

`nspacl` can be `NULL` (representing default privileges, not "zero access"); use privilege inquiry functions instead of misinterpreting `NULL`.

### 20.2. has_schema_privilege

~~~sql
SELECT
    has_schema_privilege(
        'sec389_app',
        'sec389_api',
        'USAGE'
    ) AS app_can_use_api_schema,
    has_schema_privilege(
        'sec389_app',
        'sec389_api',
        'CREATE'
    ) AS app_can_create_in_api,
    has_schema_privilege(
        'sec389_app',
        'sec389_private',
        'USAGE'
    ) AS app_can_use_private_schema;
~~~

In our clean lab, this expects `true`, `false`, `false`. In production, inherited memberships and historical grants can change effective results.

### 20.3. Extensions and Trusted Schemas

If a privileged function calls extension routines, install extensions in controlled schemas and qualify calls when needed. Never move an extension into a world-writable schema just to silence `search_path` errors; design clean namespaces and grants instead.

### 20.4. Exercise Caution When Changing public CREATE Grants

~~~sql
-- DBA-reviewed policy change; never run blindly:
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
~~~

This blocks workflows expecting to create tables or objects in `public`. Audit existing applications and migrations first and point DDL to dedicated schemas.

### 20.5. What Defines a "Trusted Schema"?

Only list a schema as trusted when:

- Its owner and every role holding `CREATE`/`ALTER` rights are fully trusted;
- Object migrations undergo code review;
- No untrusted shadowing functions or operators exist inside it;
- No untrusted input drives DDL inside it;
- All effective rights—including inherited memberships—have been audited.

## 21. Security Barrier Views Do Not Replace SECURITY DEFINER Audits

Views with `security_barrier` restrict certain planner predicate pushdowns that could leak rows. View security options (such as `security_invoker` on supported PostgreSQL versions) also control how underlying permissions and RLS apply.

### 21.1. Two Controls Operating at Different Layers

- `SECURITY DEFINER` on a **function**: switches the SQL execution identity.
- `security_barrier` / `security_invoker` on a **view**: governs planner ordering and view security context.

Neither eliminates risks in the other. A definer function querying a view must still be audited for view owner, `security_invoker`, RLS, and underlying base tables.

### 21.2. Prevent Backdoors Wrapping Functions in Views

A view calling a privileged function and granted `SELECT` to the app creates another **execution path** into that function. Verify grants across the view, function, and underlying tables; never assume `GRANT SELECT` on a view automatically validates everything the function reveals.

### 21.3. Sensitive Functions and Expression Evaluation Order

The SQL optimizer may reorder predicates when semantically permitted. Never write a secret-exposing function and assume a short-circuit `WHERE` clause prevents calling it. Enforce authorization **inside the function, API, and RLS policy**, not by relying on planner evaluation order.

## 22. Common Anti-Patterns in Privileged Functions

| Anti-Pattern | Why It Is Dangerous | Better Alternative |
| --- | --- | --- |
| Definer function owned by superuser | Massive blast radius | Dedicated least-privilege `NOLOGIN` owner |
| Creating function, revoking `PUBLIC` in later transaction | Temporary `PUBLIC EXECUTE` window | CREATE + REVOKE + GRANT in one transaction |
| Omitting `SET search_path` | Object-name hijacking | Pin trusted path with `pg_temp` last |
| Including writable `public` schema in path | Function/operator shadowing | Dedicated trusted schemas |
| Unqualified references to critical tables | Ambiguous relation lookup | Schema-qualified `schema.table` |
| Letting callers specify table/schema/function freely | Arbitrary out-of-contract access | Fixed SQL templates or strict allowlists |
| Concatenating `p_input` into dynamic SQL | SQL injection inside definer context | Static SQL or `EXECUTE ... USING` |
| Quoting identifiers without authorization | Reading unauthorized valid tables | Quoting + allowlist + privilege checks |
| Using `current_user` to identify HTTP end users | Evaluates to function owner inside definer | Verified end-user identity context |
| Blindly trusting caller-passed `p_tenant_id` | Cross-tenant data exposure | Verify tenant authorization server-side |
| Trusting caller-writable custom GUCs | Session-state identity spoofing | Protected context or verified role mapping |
| Same role owns function and all underlying tables | Can bypass RLS and read all columns | Separate data owner and function owner |
| Returning `SELECT *` | Newly migrated columns leak automatically | Explicit output column projection |
| Logging raw parameters/rows | Leaking secrets and PII | Sanitization and access-controlled logs |
| Returning raw SQL errors externally | Enumeration and schema disclosure | Sanitized API errors |
| Using `SECURITY DEFINER` to dodge auth design | Arbitrary privilege escalation | Narrow capability APIs plus proper policies |
| `GRANT EXECUTE` on all functions to `PUBLIC` | Over-exposed escalation points | Per-signature least-privilege grants |
| Skipping tests with low-privilege roles | Owner tests pass deceptively | Negative tests as real app runtime roles |
| Overlooking function overloads | Alternate signatures retain broad ACLs | Audit every signature and default argument |
| `current_user` RLS policies ignoring definer calls | Evaluates against definer owner | Verify security context and role grants |
| Casually setting `LEAKPROOF` | Breaks optimizer/RLS security assumptions | Omit unless strictly qualified |
| Testing exploits directly in production | Risks data exposure or corruption | Isolated labs and authorized test roles |

## 23. Inventorying SECURITY DEFINER Functions in a Database

When taking over a multi-schema database, the first step is **discovering every privilege boundary and who owns it**. PostgreSQL stores function metadata in `pg_proc`, schemas in `pg_namespace`, and roles in `pg_roles`.

### 23.1. Listing SECURITY DEFINER Functions

~~~sql
SELECT
    n.nspname AS function_schema,
    p.proname AS function_name,
    p.oid::regprocedure AS signature,
    owner.rolname AS owner_role,
    p.prosecdef AS is_security_definer,
    p.proconfig AS function_settings,
    p.proacl AS function_acl
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
JOIN pg_catalog.pg_roles AS owner
    ON owner.oid = p.proowner
WHERE p.prosecdef
ORDER BY n.nspname, p.oid::regprocedure::text;
~~~

Key columns:

- `prosecdef`: `true` for `SECURITY DEFINER`.
- `proowner`: owner OID mapped to role name.
- `proconfig`: function-level `SET` clauses (when set).
- `proacl`: explicit ACL; `NULL` indicates default privileges apply.

### 23.2. Interpreting NULL proacl

`proacl IS NULL` does not mean nobody can call the function. It indicates no custom ACL has been stored yet, meaning **default privileges** govern access. Use `has_function_privilege`, `aclexplode`, or `information_schema` to check effective rights.

### 23.3. Checking Who Has EXECUTE

~~~sql
SELECT
    has_function_privilege(
        'sec389_app',
        'sec389_api.get_available_stock(text)',
        'EXECUTE'
    ) AS app_can_execute,
    has_function_privilege(
        'sec389_data_owner',
        'sec389_api.get_available_stock(text)',
        'EXECUTE'
    ) AS data_owner_can_execute;
~~~

With `NOLOGIN` roles, this reports **the named role's effective permissions**, not whether that role logs in directly. Remember to also inspect inherited memberships of real client login roles.

### 23.4. Verifying PUBLIC Execute After REVOKE

To verify direct grants to `PUBLIC`, expand the effective ACL. In catalog ACLs, `grantee = 0` denotes `PUBLIC`:

~~~sql
SELECT
    EXISTS (
        SELECT 1
        FROM pg_catalog.aclexplode(
            COALESCE(
                p.proacl,
                pg_catalog.acldefault('f', p.proowner)
            )
        ) AS a
        WHERE a.grantee = 0
          AND a.privilege_type = 'EXECUTE'
    ) AS public_has_execute
FROM pg_catalog.pg_proc AS p
WHERE p.oid =
    'sec389_api.get_available_stock(text)'::regprocedure;
~~~

`PUBLIC` is an **ACL grantee pseudo-role**, not a login role name to pass to standard user lookups. Combine this `PUBLIC` check with **live invocation attempts from an unprivileged test role**.

Never confuse "role A lacks a direct `GRANT`" with "role A cannot execute": A may inherit privileges from a group role or `PUBLIC`.

### 23.5. Inspecting Function ACLs Post-Creation

~~~sql
SELECT
    p.oid::regprocedure AS function_signature,
    p.proacl,
    p.proconfig,
    p.prosecdef
FROM pg_catalog.pg_proc AS p
WHERE p.oid =
    'sec389_api.get_available_stock(text)'::regprocedure;
~~~

Verify that `EXECUTE` is granted to `sec389_app` and revoked from `PUBLIC` per contract. Never rely solely on raw `proacl` to infer inherited rights; combine with privilege inquiry checks.

### 23.6. Dumping Definitions for Code Review

~~~sql
SELECT
    p.oid::regprocedure AS signature,
    pg_catalog.pg_get_functiondef(p.oid) AS definition
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE p.prosecdef
  AND n.nspname = 'sec389_api'
ORDER BY signature::text;
~~~

Review the body, `SET search_path`, volatility, dynamic SQL, helpers, and return structure. Avoid publishing full definitions broadly if they reveal proprietary logic or internal table structures.

### 23.7. Auditing CREATE Privileges in the API Schema

~~~sql
SELECT
    has_schema_privilege(
        'sec389_app', 'sec389_api', 'CREATE'
    ) AS app_can_create,
    has_schema_privilege(
        'sec389_fn_owner', 'sec389_api', 'CREATE'
    ) AS definer_can_create;
~~~

In our clean lab, the app cannot `CREATE` while the function owner can (as schema owner). **Because a schema owner has full rights to replace objects inside its schema**, never share definer owner passwords or login credentials broadly.

### 23.8. Auditing Private Column Privileges

~~~sql
SELECT
    has_column_privilege(
        'sec389_fn_owner',
        'sec389_private.inventory',
        'available_units',
        'SELECT'
    ) AS can_read_stock,
    has_column_privilege(
        'sec389_fn_owner',
        'sec389_private.inventory',
        'cost_price',
        'SELECT'
    ) AS can_read_cost;
~~~

In our clean lab, expect `true` and `false`. If `can_read_cost` evaluates to `true`, trace inherited memberships or unexpected table grants rather than assuming everything is fine just because `GRANT SELECT (cost_price)` was not in your script.

### 23.9. Auditing Role Memberships

~~~sql
SELECT
    r.rolname AS granted_role,
    m.member::regrole AS member_role,
    m.grantor::regrole AS grantor_role
FROM pg_catalog.pg_auth_members AS m
JOIN pg_catalog.pg_roles AS r
    ON r.oid = m.roleid
WHERE r.rolname IN (
    'sec389_data_owner',
    'sec389_fn_owner',
    'sec389_app'
)
ORDER BY granted_role, member_role::text;
~~~

Newer PostgreSQL versions include `INHERIT`, `SET`, and `ADMIN` membership options; review the role graph according to your version. Membership in an owner role often overrides table-level restrictions far more dramatically than an individual `GRANT SELECT`.

### 23.10. Note on Restricted Catalog Visibility

Some catalog columns, role details, or function definitions may be hidden from unprivileged sessions. Production audits should be run by DBA/security teams using approved access workflows—never grant superuser to an application just to run audit queries.

## 24. Negative Testing With Low-Privilege Roles

Sound security tests combine **positive tests** (allowed behavior succeeds) and **negative tests** (forbidden behavior fails).

### 24.1. Lab Test Matrix

| Call / Operation | Role | Expected Outcome |
| --- | --- | --- |
| `SELECT sec389_api.get_available_stock('KB-001')` | `sec389_app` | `17` |
| `SELECT sec389_api.get_available_stock('MS-002')` | `sec389_app` | `0` |
| `SELECT sec389_api.get_available_stock('INTERNAL-001')` | `sec389_app` | SQL `NULL` |
| `SELECT * FROM sec389_private.inventory` | `sec389_app` | Denied |
| `UPDATE sec389_private.inventory ...` | `sec389_app` | Denied |
| `CREATE FUNCTION sec389_api.some_fn(...)` | `sec389_app` | Denied |
| `SELECT sec389_api.get_available_stock(...)` | Role without EXECUTE/USAGE | Denied |
| `SELECT cost_price ...` | `sec389_fn_owner` | Denied in clean lab |

### 24.2. Testing With the Real Calling Role

In real environments, test directly as the **actual service login role** through the real transaction manager and connection pool rather than relying solely on DBA `SET ROLE`.

In an authorized lab session:

~~~sql
SET ROLE sec389_app;
SELECT sec389_api.get_available_stock('KB-001');
RESET ROLE;
~~~

If your test role cannot `SET ROLE sec389_app`, do not grant membership haphazardly; have your DBA provision a realistic test account matching runtime effective privileges.

### 24.3. Cross-Tenant Authorization Tests

If the API takes a `tenant_id`, create tenants A and B, authorize caller only for tenant A, and assert:

1. Tenant A resources can be read;
2. Tenant B resources cannot be read even when guessing valid IDs;
3. Error messages do not confirm tenant B's existence;
4. Caller attempts to alter `SET ROLE` or GUCs cannot subvert authorization;
5. Pooled connection reuse never mixes tenant identities.

### 24.4. Testing Name Shadowing in an Isolated Lab

Create a decoy relation with the same name in the test session's **temporary schema**, then call the search-path-pinned function. It must return data from `sec389_private.inventory`, ignoring the temporary table.

~~~sql
-- Lab session only (never in production):
CREATE TEMP TABLE inventory (
    sku text,
    available_units integer,
    is_public boolean
);

INSERT INTO inventory(sku, available_units, is_public)
VALUES ('KB-001', 999999, true);

-- Safe function must read from sec389_private.inventory:
SELECT sec389_api.get_available_stock('KB-001');
~~~

With `EXECUTE` granted, the expected result is **17**, not 999999. Note that this tests one name-resolution layer; it does not automatically prove every helper or dynamic SQL query is safe.

### 24.5. Testing Under an Adversarial Caller search_path

~~~sql
-- Test only in an authorized session:
SET search_path = pg_temp, public;

SELECT sec389_api.get_available_stock('KB-001');

RESET search_path;
~~~

Because the function pins `search_path` and schema-qualifies the relation, the output remains unaffected by the caller's path.

### 24.6. Treating SQL-Like Strings Strictly as Data

If an API accepts `p_sku` text, test with controlled inputs containing quotes and SQL-like characters. The function must evaluate them strictly as SKU values without altering query syntax.

### 24.7. Testing NULL and Invalid Inputs

~~~sql
SELECT sec389_api.get_available_stock(NULL::text);
SELECT sec389_api.get_available_stock('');
SELECT sec389_api.get_available_stock('NON-EXISTENT');
~~~

With standard SQL equality in our lab function, all three return SQL `NULL`. Production code may prefer explicit validation errors—just ensure errors never leak private values.

### 24.8. Automate Negative Tests

Never run privilege tests just once at initial release. Re-run regression suites under realistic caller roles after any change to owners, views, RLS policies, schema grants, function definitions, or role memberships.

## 25. Auditing SECURITY DEFINER Invocations

Auditing addresses two separate goals:

1. **Auditing successful business operations:** who requested reads/mutations and which changes committed.
2. **Auditing failed or unauthorized access attempts:** rejected calls, errors, and abuse signals.

### 25.1. In-Transaction Audit INSERTs Roll Back With Caller Transactions

Writing an audit row into a DB table within the caller's transaction rolls back whenever that transaction rolls back. While ACID-correct, it may fail compliance needs requiring **recording denied/rolled-back attempts**.

### 25.2. Capturing Failed Attempts

Depending on compliance requirements, capture denied or rolled-back attempts via application gateway logs, PostgreSQL server logging, or out-of-band telemetry. Never attempt to force independent log commits inside a `SECURITY DEFINER` function.

### 25.3. Minimize Sensitive Data in Audit Logs

Record:

- API/function name or action type;
- Request/correlation identifier;
- Timestamp and outcome;
- Verified DB/service role identity;
- Sanitized resource identifiers;
- Error category or SQLSTATE where helpful.

Never log raw secrets, tokens, passwords, full card numbers, or unnecessary PII.

### 25.4. Keep Audit Mutation Rights Away From Apps

To keep audit tables tamper-evident, allow runtime app roles strictly append/call rights via a narrow interface—never arbitrary `UPDATE`/`DELETE`. Still remember in-transaction audit writes remain subject to caller rollbacks; address tamper resistance and rollback durability separately.

### 25.5. Minimize Information in Errors

If account enumeration violates your threat model, ensure unauthorized callers cannot distinguish "does not exist", "locked", and "belongs to another tenant" via detailed exceptions.

## 26. Operational Controls and Availability

`SECURITY DEFINER` routines can experience high request rates even when returning a single row.

### 26.1. Rate Limits and Query Cost

Any API with `EXECUTE` granted to an application role can be abused via:

- Millions of rapid calls;
- Inputs forcing non-indexed scans inside the routine;
- Wide scans over massive tables;
- Heavy locking or write amplification;
- Unintended tables targeted via dynamic SQL.

Protect with API/gateway rate limits, proper indexes, `statement_timeout`, pool sizing budgets, and query telemetry.

### 26.2. Do Not Rely on STABLE for DoS Protection

`STABLE` describes snapshot consistency and absence of write side effects, not CPU or call-rate caps. A `STABLE` definer function can still run an expensive scan.

### 26.3. Observability Tools

Key signals:

- `pg_stat_activity`: active queries, sessions, wait events;
- `pg_locks` and `pg_blocking_pids`: lock contention;
- `pg_stat_statements` (when enabled): query execution statistics;
- Application traces: endpoint, latency, request IDs;
- Policy-compliant audit logs;
- DDL migration history tracking changes to owners and function ACLs.

### 26.4. EXPLAIN Is Not a Security Verification Tool

`EXPLAIN` shows planner costs and access paths, not authorization guarantees. `EXPLAIN (ANALYZE)` **executes the statement**, mutating data when run against DML or side-effecting routines. Run it only in controlled labs/benchmarks and never equate a fast plan with proper security.

### 26.5. Configuring statement_timeout

Timeouts protect cluster capacity against runaway queries without replacing quotas or authorization. Note that session-level GUC overrides persist across pooled connections if un-reset; configure consistent policies at the datasource, role, or transaction-local level.

## 27. Incident Runbook: Suspected Privilege Escalation Abuse

When a privileged function returns anomalous data, gets called by unexpected roles, or causes unexpected writes:

### Phase 1 — Scope the Impact

- Which function and signature?
- Current owner role vs. pre-migration owner?
- Who holds `EXECUTE` (including `PUBLIC` and inherited memberships)?
- Which helpers, views, or triggers execute downstream?
- Was cross-tenant data or sensitive columns accessed?
- Did external side effects or DML writes occur?
- When did exposure begin and which versions are affected?

### Phase 2 — Cut Off Unintended Invocation Paths

Following approved incident-response procedures, consider **revoking `EXECUTE`** from unauthorized roles, disabling the endpoint at the API gateway, or rolling back deployment. Avoid dropping production tables or functions impulsively while forensic evidence and business state must be preserved.

### Phase 3 — Inspect Name-Resolution Surface

Inspect `pg_get_functiondef` alongside:

- Function-level `SET search_path`;
- Schemas holding `CREATE` privileges;
- Temporary-table exposure;
- Dynamic SQL;
- Unqualified table/function/operator names;
- Role inheritance chains;
- Overloads and default arguments.

### Phase 4 — Audit Data and Privileges

Cross-reference audit/query logs, accessed rows, mutated tables, owner privileges, and RLS rules. Determine whether secrets, cost prices, or tenant records were exposed—never assume zero exposure simply because no errors were logged.

### Phase 5 — Remediate and Verify

Fix the root cause (authorization, name resolution, SQL injection, or excessive privileges), deploy atomically, and verify using low-privilege caller tests, temporary-table shadowing tests, and cross-tenant negative assertions.

### Phase 6 — Recover and Monitor

If secrets may have leaked, rotate credentials/tokens and execute security notifications per policy. Monitor anomalous calls, permission failures, latency, and role changes post-deployment.

### Phase 7 — Plan Data Reconciliation Alongside Code Rollback

Rolling back function code **does not undo** committed `UPDATE`/`DELETE` mutations applied earlier. Perform business-level data reconciliation rather than stopping at code rollback.

## 28. Pull Request / Migration Review Checklist

| Item | Question to Answer |
| --- | --- |
| Use case | Why is `SECURITY DEFINER` needed over `INVOKER`, column grants, views, or RLS? |
| Owner | Is it a dedicated minimal role rather than superuser/table owner? |
| Privileges | Does the owner hold strictly the necessary `SELECT`/`UPDATE`/`USAGE` rights? |
| Schema | Are any untrusted schemas present in `search_path`? |
| `pg_temp` | Is `pg_temp` explicitly listed last in `search_path`? |
| Object names | Are critical tables, functions, and operators schema-qualified? |
| Function args | Are types, `NULL`, bounds, identifiers, and JSON validated? |
| Dynamic SQL | Are values passed via `USING` and identifiers strictly allowlisted? |
| Authorization | Where are caller, tenant, and resource permissions verified? |
| ACLs | Was `PUBLIC EXECUTE` revoked and `EXECUTE` granted per exact signature? |
| DDL atomicity | Do CREATE/ALTER + REVOKE/GRANT run without an insecure exposure window? |
| RLS | Does the owner bypass RLS? Do policies misuse `current_user`? |
| Data output | Could outputs, row counts, or errors leak sensitive fields? |
| Dependencies | Were helpers, views, triggers, FDWs, and extensions audited? |
| Volatility | Are `STABLE`/`IMMUTABLE`/`PARALLEL SAFE` accurate and `LEAKPROOF` avoided? |
| Side effects | Are external calls, outbox/audit writes, or lock amplification bounded? |
| Testing | Are there positive and negative tests as realistic caller roles? |
| Monitoring | Are logs, error metrics, latency, and resource budgets covered? |
| Migration | Were owner/ACL/schema dependencies and rollback behavior reviewed? |

## 29. Deciding Between SECURITY DEFINER and Alternatives

### 29.1. Reading Strictly a Subset of Columns

Prefer **column-level `GRANT`** on the table or an appropriately scoped view. Use `SECURITY DEFINER` only when procedural logic or tight encapsulation cannot be expressed cleanly via grants or views.

### 29.2. Restricting Reads to Current Tenant Rows

Row-Level Security is usually the right foundation whenever the DB trusts the verified tenant context. Because `SECURITY DEFINER` can alter or bypass RLS evaluation, evaluate carefully before using it as a shortcut.

### 29.3. Automated Audit Logging

Trigger functions can record audit trails safely when owner, `search_path`, PII retention, and transaction semantics are hardened. Not every audit trigger needs `SECURITY DEFINER` if callers already hold `INSERT` on an append-only audit table.

### 29.4. Controlled Business State Transitions

A compact `SECURITY DEFINER` function with a narrow signature, validation, authorization, and minimal `UPDATE` grants works well here. However, workflows spanning external services, outbox events, and retries often fit better at the service orchestration layer.

### 29.5. Letting Clients Run Arbitrary Queries Against Private Tables

Never wrap arbitrary SQL execution inside `SECURITY DEFINER` as a proxy. That defeats capability-based API design.

### 29.6. Enforcing Permissions of the Original Calling Role

`SECURITY INVOKER` paired with table grants and RLS keeps caller identity intact. Since `SECURITY DEFINER` overrides effective identity, do not add it when caller-based enforcement is what you actually want.

## 30. Practice Exercises — Core Privileges and search_path

These exercises reference the three roles and two schemas from the lab. Steps involving `CREATE ROLE`, `ALTER FUNCTION OWNER`, or `GRANT` require a DBA or authorized account. Never run exploit tests in production; snippets labeled "unsafe" are for analysis only. **Not every exercise requires running SQL**—several ask you to explain semantics or review pseudocode.

### Exercise 1 — Comparing Execution Modes

Can a default `SECURITY INVOKER` function read a table on which the caller lacks `SELECT`? What happens if you switch it to `SECURITY DEFINER` while the owner also lacks `SELECT`?

**Answer:** Invoker uses caller rights; definer uses owner rights, yet never invents missing privileges for the owner.

### Exercise 2 — Purpose of a Privileged API

The app role needs available stock for public SKUs, while the table also stores `cost_price`.

**Task:** Design the API boundary so the app can call the function yet cannot `SELECT` the table or `cost_price`.

### Exercise 3 — CURRENT_USER Inside Definer

A service role calls a function owned by `sec389_fn_owner`.

**Question:** Who is `current_user` inside the function? Does it match the website login user?

**Answer:** The effective role is the function owner; it cannot identify HTTP end users.

### Exercise 4 — SESSION_USER and SET ROLE

Where permitted, run `SET ROLE sec389_app` and query:

~~~sql
SELECT session_user, current_user;
~~~

**Question:** Why can these two values differ, and what happens once execution enters a `SECURITY DEFINER` function?

### Exercise 5 — Default Function EXECUTE

Why is `REVOKE EXECUTE ON FUNCTION ... FROM PUBLIC` required when creating sensitive functions?

**Answer:** Newly created functions normally grant `EXECUTE` to `PUBLIC` by default, so it must be revoked and granted selectively.

### Exercise 6 — CREATE and REVOKE in One Transaction

~~~sql
BEGIN;
CREATE FUNCTION ... SECURITY DEFINER ...;
REVOKE ALL ON FUNCTION ... FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ... TO sec389_app;
COMMIT;
~~~

**Question:** Why is this safer than committing `CREATE FUNCTION` first and revoking `PUBLIC` in a later migration?

### Exercise 7 — PUBLIC Role vs. public Schema

Explain the difference between `REVOKE ... FROM PUBLIC` and `REVOKE CREATE ON SCHEMA public FROM PUBLIC`. What does "public" refer to in each case?

### Exercise 8 — Schema USAGE

If the app holds `EXECUTE` on a function yet lacks **`USAGE`** on the API schema, what happens when it invokes the function by its fully qualified name?

### Exercise 9 — Private Schema

In the lab, does the app role need `USAGE ON SCHEMA sec389_private` to call `sec389_api.get_available_stock(...)`?

**Answer:** No; SQL inside the definer function executes under the definer owner's privileges, which include `USAGE` on `sec389_private`.

### Exercise 10 — Column Grants

~~~sql
GRANT SELECT (sku, available_units, is_public)
ON sec389_private.inventory TO sec389_fn_owner;
~~~

**Question:** Can the function owner read `cost_price` assuming no other grants or memberships exist?

### Exercise 11 — Separating Owners

Compare two designs:

1. The function owner also owns the table with `UPDATE`/`DELETE` rights.
2. The function owner holds strictly `SELECT` on three required columns.

**Task:** Analyze the blast radius if SQL inside the function is subverted.

### Exercise 12 — NOLOGIN

Does `sec389_fn_owner NOLOGIN` stop a `SECURITY DEFINER` function from using that role?

**Answer:** No; `NOLOGIN` only blocks direct login, while role privileges still apply during definer execution or allowed `SET ROLE`.

### Exercise 13 — Role Membership

A DBA accidentally grants the app role membership allowing `SET ROLE sec389_fn_owner`. How does this defeat the "app can only EXECUTE" goal?

### Exercise 14 — Untrusted search_path

A function runs:

~~~sql
SELECT available_units FROM inventory;
~~~

without `SET search_path`. The caller can create a temporary table named `inventory`.

**Question:** How can relation resolution be hijacked?

### Exercise 15 — Pinning search_path

Write a function header containing:

~~~sql
SECURITY DEFINER
SET search_path = pg_catalog, sec389_private, pg_temp
~~~

**Question:** Why must listed schemas be trusted, and why does `pg_temp` belong at the end?

### Exercise 16 — pg_temp Precedence

When `pg_temp` is omitted from `search_path`, where can the temporary schema be searched during relation/type lookup?

**Answer:** PostgreSQL applies special priority searching the temporary schema early when unlisted; therefore put `pg_temp` explicitly last.

### Exercise 17 — pg_temp and Function Lookup

**Question:** Does PostgreSQL apply that same temp-first rule when resolving functions and operators as for tables and types?

**Answer:** No; that is an important boundary of search path resolution.

### Exercise 18 — pg_catalog Placement

A function specifies:

~~~sql
SET search_path = untrusted_schema, pg_catalog
~~~

**Question:** Why is putting a schema with untrusted `CREATE` grants ahead of `pg_catalog` dangerous?

### Exercise 19 — Qualified Names

Compare:

~~~sql
SELECT available_units FROM inventory;
SELECT available_units FROM sec389_private.inventory;
~~~

**Question:** Which is easier to audit and resistant to table-name shadowing? Does both still require privileges?

### Exercise 20 — Function/Operator Hijacking

A function invokes `transform_input(p_sku)` unqualified while an earlier schema lets clients `CREATE` objects.

**Task:** Describe how resolution could hit an untrusted helper, and list two defensive layers: trusted `search_path` + qualified helpers/explicit argument types.

### Exercise 21 — String-Concatenation SQL Injection

Inside a PL/pgSQL `SECURITY DEFINER` function:

~~~sql
-- Wrong:
-- EXECUTE 'SELECT ... WHERE sku = ''' || p_sku || '''';
~~~

**Task:** Explain why calling this function from Java via a `PreparedStatement` fails to prevent SQL injection inside the function body.

### Exercise 22 — EXECUTE USING

Rewrite as:

~~~sql
EXECUTE 'SELECT available_units
         FROM sec389_private.inventory
         WHERE sku = $1 AND is_public = true'
INTO v_stock
USING p_sku;
~~~

**Question:** Why can `p_sku` no longer turn into SQL syntax?

### Exercise 23 — Identifiers and %I

A function chooses between two reviewed reporting tables.

**Task:** Combine a table allowlist, `format('%I.%I', schema, table)` for identifiers, and `USING` for values. Why is quoting alone unsafe if callers can pick arbitrary tables?

### Exercise 24 — Tenant-Per-Schema Selection

An application has 200 tenant schemas, and an API lets callers pass `p_schema` to owner-privileged dynamic SQL.

**Task:** Identify the cross-tenant risk and propose safer designs using verified tenant authorization or a trusted allowlist registry.

### Exercise 25 — Temp Table Shadowing Test

In a lab session, create `TEMP TABLE inventory` with a fake row having `available_units=999999`, then call `get_available_stock('KB-001')`.

**Question:** Which number should a hardened function return and why?

**Answer:** `17` from `sec389_private.inventory`, because the SQL uses a schema-qualified name and a trusted function-level `search_path`.

### Exercise 26 — Altering Caller search_path

~~~sql
SET search_path = pg_temp, public;
SELECT sec389_api.get_available_stock('KB-001');
~~~

**Question:** Should the output change when calling a function with pinned `search_path` and schema-qualified tables?

### Exercise 27 — Protected Column Access

`sec389_app` successfully calls the stock lookup function. Does that imply it can read `cost_price` directly?

**Answer:** No; `EXECUTE` on a function does not grant `SELECT` on the table, and even the function owner lacks grants on `cost_price`.

### Exercise 28 — Can a SQL View Replace the Function?

Suppose the only requirement is listing public SKUs with `available_units`.

**Task:** Compare a properly configured view, column-level `GRANT`, RLS, and a `SECURITY DEFINER` function; when is each most appropriate?

### Exercise 29 — RLS Table Owner

Suppose the function owner also owns a table with RLS enabled (but not `FORCE`).

**Question:** Does the function bypass RLS under PostgreSQL rules? What changes if the function owner is a separate non-owner role with `SELECT` subject to policies?

### Exercise 30 — BYPASSRLS

A definer role holds `BYPASSRLS`. Why is this dangerous when querying multi-tenant data, and does `FORCE ROW LEVEL SECURITY` fully prevent it?

**Answer guide:** `BYPASSRLS` overrides row policies; `FORCE` does not block `BYPASSRLS` or superuser roles.

### Exercise 31 — current_user Inside an RLS Policy

A policy checks `resource_owner = current_user`, and the table is queried inside a `SECURITY DEFINER` function.

**Question:** Which effective role does `current_user` evaluate to, and why does that break "caller-owned rows"?

### Exercise 32 — Untrusted Tenant Inputs

A function takes `p_tenant_id` and executes:

~~~sql
SELECT * FROM private.orders
WHERE tenant_id = p_tenant_id;
~~~

**Task:** Add verification proving the caller is authorized for that tenant. Why isn't knowing a tenant UUID proof of authorization?

### Exercise 33 — Connection Pooling and Session Identity

An application shares one DB login role across thousands of HTTP end users.

**Question:** Can `session_user` inside a definer function distinguish web users? How should verified user context be passed without spoofing?

### Exercise 34 — Custom GUCs

A function filters by `current_setting('app.user_id')`, yet the service role can invoke `set_config('app.user_id', ...)` arbitrarily.

**Task:** Analyze the spoofing risk and identify a trustworthy architecture for binding caller identity.

### Exercise 35 — Default Privileges

~~~sql
ALTER DEFAULT PRIVILEGES FOR ROLE sec389_fn_owner
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
~~~

**Question:** Does this affect existing functions? If another deployment role creates a function without `SET ROLE`, whose default privileges apply?

### Exercise 36 — Overloading

Given:

~~~text
get_stock(text)
get_stock(integer)
get_stock(text, boolean DEFAULT true)
~~~

**Task:** Explain why revoking `PUBLIC` on just one signature leaves exposure gaps, and outline an audit plan across all overloads.

### Exercise 37 — CREATE OR REPLACE

A team runs `CREATE OR REPLACE FUNCTION` assuming all old `EXECUTE` grants are wiped.

**Question:** Is that assumption safe? What metadata should be re-checked after replacement?

### Exercise 38 — Owner Change

~~~sql
ALTER FUNCTION sec389_api.get_available_stock(text)
OWNER TO some_powerful_owner;
~~~

**Task:** Explain why this constitutes a security change even though the SQL body stays identical. How can grants and RLS change?

### Exercise 39 — Leaking Cost Price in JSON Output

A definer function pins `search_path` cleanly yet returns `cost_price` inside a JSON payload.

**Question:** Is it still secure? Why can't `search_path` replace output minimization?

### Exercise 40 — Expensive Queries

An app role can freely invoke a function running a heavy `SELECT` over a 100-million-row table.

**Task:** Propose defenses combining rate limiting, input bounds, indexes, `statement_timeout`, monitoring, and resource budgets.

### Exercise 41 — SECURITY DEFINER Triggers

An audit trigger runs as `SECURITY DEFINER` so it can insert audit rows without giving callers direct `INSERT`.

**Question:** How should owner rights, `search_path`, side effects, PII retention, and rollback semantics be audited?

### Exercise 42 — Helper Function Call Chains

`api_fn` calls `helper_fn`, which updates a table firing a trigger.

**Task:** Trace the call graph and identify active roles, permissions, views/triggers, RLS, and side effects at each stage.

### Exercise 43 — Exceptions Leaking Internal Values

A function raises `RAISE EXCEPTION 'cost for SKU X is ...'`.

**Question:** Even when queries return no rows, how does data leak? Design a sanitized error response.

### Exercise 44 — Negative Test Suite

Write tests asserting failure when the app role tries to:

1. `SELECT * FROM sec389_private.inventory`;
2. `UPDATE` the private table;
3. `CREATE FUNCTION` inside `sec389_api`;
4. Call a privileged function without `EXECUTE`.

**Question:** Why are negative tests just as critical as positive functional tests?

### Exercise 45 — LEAKPROOF

A developer marks a custom definer function `LEAKPROOF` hoping for faster planner execution.

**Task:** Explain why `LEAKPROOF` affects optimizer/RLS security guarantees, requires elevated privileges, and must never be added arbitrarily.

### Exercise 46 — Volatility

`get_available_stock` reads mutable table rows. Should you mark it `IMMUTABLE` to speed up indexing or caching?

**Answer:** No; underlying data changes over time. `STABLE` accurately models read-only snapshot lookups in the lab.

### Exercise 47 — Transaction Rollback

A definer function updates a private table, then the caller issues `ROLLBACK`.

**Question:** Do the owner's elevated privileges keep the update committed?

**Answer:** No; internal SQL still executes inside the caller's transaction.

### Exercise 48 — Security Incident

You discover an over-privileged `SECURITY DEFINER` function with `PUBLIC EXECUTE` and suspicious calls in logs.

**Task:** Write an incident runbook covering owner/ACL inventory, approved `EXECUTE` revocation, exposure assessment, `search_path`/SQL injection fixes, low-privilege testing, and post-deploy monitoring.

### Exercise 49 — Pull Request Review

A PR introduces:

~~~sql
CREATE FUNCTION public.admin_query(p_sql text)
RETURNS SETOF text
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY EXECUTE p_sql;
END;
$$;
~~~

**Task:** Explain why this creates a dangerous privileged arbitrary-SQL backdoor; propose narrowly typed functions using static SQL and least privilege instead. Never deploy this.

### Exercise 50 — Capstone: Secure Multi-Tenant API

A SaaS app wants to expose three operations:

- Read available stock for public products.
- Reserve stock for an authorized order.
- Fetch aggregate statistics for the current tenant.

The `cost_price` column must never leak via the public API. Runtime traffic flows through a connection pool sharing one DB login role across HTTP users.

**Implementation / documentation requirements:**

1. Diagram the roles: data owner, read-function owner, write-function owner, app role.
2. Specify private/API schemas, `CREATE`/`USAGE`/`EXECUTE` rights, and column-level grants.
3. Write a `SECURITY DEFINER` read function with a trusted `search_path` and schema-qualified tables.
4. Deploy `CREATE` + `REVOKE PUBLIC` + `GRANT` atomically.
5. Design verified tenant identity enforcement—never trust raw caller `p_tenant_id` or writable GUCs alone.
6. Analyze RLS: can owners bypass it or must policies apply?
7. Implement conditional `UPDATE` preventing negative stock, paired with idempotency keys and authorization.
8. Ensure neither `cost_price` nor confidential SKU existence leaks via errors.
9. Reject arbitrary table or function names in dynamic SQL.
10. Specify positive and negative tests covering tenants A/B, temp-table shadowing, schema injection, retries, and pooled connection reuse.
11. Document explicitly what each owner role is **prohibited** from doing.
12. Plan logging, monitoring, rate limits, migration rollbacks, and incident response.

**Passing criteria:** clearly explain **who calls the function, whose privileges run inside it, which objects resolve under which names, why callers cannot break out of the SQL contract, and why out-of-scope data cannot leak**.

## 31. Security Checklist for Every SECURITY DEFINER Function

### 31.1. Is Privilege Escalation Truly Necessary?

- [ ] Functionality cannot be achieved more cleanly with `SECURITY INVOKER`, column grants, views, or RLS.
- [ ] Input/output contract, side effects, and authorization rules are documented.
- [ ] Only logic requiring elevated access runs inside the definer routine.
- [ ] The function is not an arbitrary SQL executor or generic admin proxy.

### 31.2. Roles and ACLs

- [ ] Function owner is a dedicated non-`SUPERUSER` role.
- [ ] Function owner lacks `BYPASSRLS`/`CREATEROLE`/`CREATEDB` unless explicitly reviewed.
- [ ] Owner does not automatically own all sensitive tables; data owner is separated.
- [ ] Owner holds strictly required `SELECT`/`UPDATE` privileges on needed columns/tables.
- [ ] Inherited role memberships were audited in addition to direct grants.
- [ ] Runtime roles cannot `SET ROLE` into the definer owner.
- [ ] Runtime roles have no `CREATE` in trusted schemas.
- [ ] `PUBLIC EXECUTE` has been revoked.
- [ ] `EXECUTE` is granted strictly to intended roles across exact signatures/overloads.
- [ ] `CREATE`/`ALTER` and `REVOKE`/`GRANT` deploy atomically with no exposure gap.
- [ ] `ALTER DEFAULT PRIVILEGES` was checked for the exact deploying role.

### 31.3. Name Resolution

- [ ] Trusted `SET search_path` is pinned on the function.
- [ ] `pg_catalog` precedes untrusted schemas (preferably explicit first).
- [ ] `pg_temp` is explicitly listed last.
- [ ] No client-writable schemas appear in the trusted search path.
- [ ] Key tables and functions are schema-qualified.
- [ ] No untrusted shadowing functions/operators or unexpected dependencies exist.
- [ ] Temporary-table shadowing has been tested.
- [ ] Extension and helper schemas have safe owners and grants.

### 31.4. Inputs and Dynamic SQL

- [ ] Input values are never concatenated into SQL strings.
- [ ] Static SQL or `EXECUTE ... USING` is used.
- [ ] Dynamic identifiers use `format('%I', ...)` / identifier quoting.
- [ ] Dynamic identifiers also pass an explicit allowlist, not quoting alone.
- [ ] `NULL`, empty strings, lengths, bounds, and types are validated.
- [ ] User/tenant/resource identities are verified from a trusted source.
- [ ] Arbitrary custom GUCs or unverified client `tenant_id` parameters are never trusted alone.

### 31.5. RLS, Outputs, and Side Effects

- [ ] Clear understanding of which effective role RLS evaluates against.
- [ ] Table-owner bypass and `BYPASSRLS` interactions audited.
- [ ] `current_user` inside definer is never mistaken for the HTTP end user.
- [ ] Return values omit any out-of-contract columns or rows.
- [ ] Errors avoid leaking sensitive values or resource existence.
- [ ] Logs and `NOTICE` messages scrub PII and secrets.
- [ ] External side effects requiring post-commit guarantees avoid in-function execution.
- [ ] Full call graph (helpers, views, triggers) is reviewed.
- [ ] Volatility and parallel safety are accurate, with `LEAKPROOF` avoided unless qualified.

### 31.6. Operations

- [ ] Positive tests cover authorized app roles.
- [ ] Negative tests cover unauthorized roles and cross-tenant boundaries.
- [ ] Tests re-run after owner, grant, overload, schema, or RLS changes.
- [ ] Version control and migration rollback procedures exist.
- [ ] Error/latency/abuse telemetry and audit access controls are configured.
- [ ] Rate limits and query budgets protect public API entry points.
- [ ] Incident response runbook exists for potential definer compromises.

## 32. Frequently Asked Questions

### 32.1. Does SECURITY DEFINER allow callers to SELECT the table directly?

No. Callers can `EXECUTE` the function running under owner privileges, without gaining direct `SELECT` on underlying tables. Still, if the function outputs unrestricted rows, it **leaks data through its return value**, so keep outputs tightly scoped.

### 32.2. Why can the app still read stock after I ran REVOKE SELECT on the table?

Because the `SECURITY DEFINER` function reads the table under its owner's rights while the app still holds `EXECUTE` on the function. That is often the exact intended API behavior rather than a bug.

### 32.3. Is PUBLIC the same as the public schema?

No. `PUBLIC` in `GRANT`/`REVOKE` refers to all roles; schema `public` is a database namespace.

### 32.4. After revoking EXECUTE from PUBLIC, is schema USAGE still needed?

Yes, if callers resolve/invoke the function by name inside that schema. Still, those grants stay independent: schema `USAGE` never grants function `EXECUTE`, and function `EXECUTE` never grants table reads.

### 32.5. Is pinning a safe SET search_path enough by itself?

No. You still must audit owner privileges, dynamic SQL, caller authorization, RLS, outputs/errors, helper routines, and `EXECUTE` ACLs. A safe `search_path` is **one defensive layer**.

### 32.6. Why must pg_temp go last?

When `pg_temp` is omitted, PostgreSQL may prioritize searching it first for relations and types. Putting `pg_temp` last prevents temporary tables or types from shadowing trusted objects.

### 32.7. Does formatting dynamic SQL with %I stop every attack?

No. `%I` safely quotes identifiers syntactically; callers could still pass **syntactically valid yet unauthorized identifiers**. Pair `%I` with allowlists/authorization and bind values via `USING`.

### 32.8. Should SESSION_USER be used as user_id?

Only when your architecture genuinely ties DB sessions 1:1 to verified identities. With connection pools sharing a single DB login across web traffic, `session_user` cannot identify HTTP users.

### 32.9. Does SECURITY DEFINER always bypass RLS?

No. RLS depends on the effective role, table ownership, policies, and `BYPASSRLS`/`SUPERUSER`. A definer routine may obey or bypass RLS depending on those attributes.

### 32.10. Can a function COMMIT audit logs so they survive caller ROLLBACK?

No. Regular functions lack transaction control. Any writes inside the function share the caller's transaction; capturing rolled-back attempts requires out-of-transaction logging or telemetry.

### 32.11. Should we re-test after changing a function's owner?

Yes. `SECURITY DEFINER` executes with the new owner's privileges, potentially altering visible data, RLS evaluation, or side effects.

### 32.12. Can we just mark every function SECURITY DEFINER for convenience?

No. Each definer routine creates a privilege boundary requiring threat modeling, tight ACLs, safe `search_path`, and regression tests. Default to `SECURITY INVOKER` whenever elevation is unnecessary.

### 32.13. Why test with low-privilege roles instead of DBA accounts?

DBAs bypass normal restrictions, hiding both missing grants and unintended data leaks. Testing as real caller roles confirms permitted calls work **and** out-of-contract actions are rejected.

### 32.14. Should privileged functions live in the public schema?

Functions can exist in many schemas, yet privileged APIs usually belong in a **dedicated protected schema** with selective `USAGE`/`EXECUTE`. Default `CREATE` permissions on `public` vary across versions and legacy ACLs.

### 32.15. How do I check whether a new function still grants EXECUTE to PUBLIC?

Inspect `pg_proc.proacl`/`aclexplode` alongside default ACLs, and test calling it from an ungranted role. Never assume `proacl IS NULL` means no one can run it.

## 33. Official PostgreSQL Documentation

Always consult documentation for your **exact major PostgreSQL version**; links below point to current docs:

- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html): `SECURITY INVOKER`/`SECURITY DEFINER`, function-level `SET`, volatility, parallel safety, leakproof, cost, and privileges.
- [Writing SECURITY DEFINER Functions Safely](https://www.postgresql.org/docs/current/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY): trusted `search_path`, `pg_temp` last, and atomic create/revoke.
- [GRANT](https://www.postgresql.org/docs/current/sql-grant.html): `EXECUTE`, schema `USAGE`/`CREATE`, table and column privileges.
- [REVOKE](https://www.postgresql.org/docs/current/sql-revoke.html): revoking privileges from `PUBLIC` and specific roles.
- [ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html): default `EXECUTE` for future functions and creator-role/schema scope.
- [ALTER FUNCTION](https://www.postgresql.org/docs/current/sql-alterfunction.html): changing owners, security mode, and function `SET` settings.
- [Role Attributes](https://www.postgresql.org/docs/current/role-attributes.html): `LOGIN`, `SUPERUSER`, `BYPASSRLS`, and role capabilities.
- [Role Membership](https://www.postgresql.org/docs/current/role-membership.html): inherited grants, `SET ROLE`, and membership options.
- [Role System](https://www.postgresql.org/docs/current/user-manag.html): managing roles and object ownership.
- [Schemas](https://www.postgresql.org/docs/current/ddl-schemas.html): `search_path`, namespace privileges, and object resolution.
- [Function Security](https://www.postgresql.org/docs/current/perm-functions.html): managing untrusted functions and privilege boundaries.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): RLS, policy role context, table owners, and `FORCE ROW LEVEL SECURITY`.
- [PL/pgSQL EXECUTE](https://www.postgresql.org/docs/current/plpgsql-statements.html#PLPGSQL-STATEMENTS-EXECUTING-DYN): `USING` parameterization, identifiers, and dynamic SQL.
- [String Functions and format](https://www.postgresql.org/docs/current/functions-string.html): `format('%I', ...)` and `format('%L', ...)`.
- [SET ROLE](https://www.postgresql.org/docs/current/sql-set-role.html): switching effective roles within a session.
- [System Information Functions](https://www.postgresql.org/docs/current/functions-info.html): `current_user`, `session_user`, and privilege inquiry functions.
- [System Catalog pg_proc](https://www.postgresql.org/docs/current/catalog-pg-proc.html): owner, `prosecdef`, `proconfig`, and `proacl`.
- [System Catalog pg_namespace](https://www.postgresql.org/docs/current/catalog-pg-namespace.html): schema owners and ACLs.
- [System Catalog pg_roles](https://www.postgresql.org/docs/current/view-pg-roles.html): non-password role metadata.
- [Function Volatility Categories](https://www.postgresql.org/docs/current/xfunc-volatility.html): proper `STABLE`/`VOLATILE`/`IMMUTABLE` semantics.
- [CREATE VIEW](https://www.postgresql.org/docs/current/sql-createview.html): `security_invoker`/`security_barrier` and versioned view semantics.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity` and observability views.

## 34. Summary

**`SECURITY DEFINER`** lets a PostgreSQL function run under its **owner's privileges** instead of the caller's. While powerful for building narrow APIs over private data, it creates a **privilege escalation boundary** that must be reviewed like any privileged interface.

Three non-negotiable defensive pillars:

1. **Least-privilege owner:** use a dedicated role avoiding `SUPERUSER`, `BYPASSRLS`, and excessive table rights; separate the data owner from the function owner wherever possible.
2. **Safe name resolution:** pin a trusted `search_path` with `pg_catalog` explicit first, `pg_temp` last, schema-qualify critical objects, and avoid untrusted dynamic SQL.
3. **Selective execution rights:** remember default `PUBLIC EXECUTE` on new functions; create, revoke, and grant **in the same transaction**, scoped strictly to authorized roles and signatures.

Supporting layers make the function genuinely secure: verified caller/tenant authorization, accurate RLS behavior under the effective role, strict output/error minimization, static SQL or `EXECUTE ... USING`, reviewed role memberships, views/helpers/triggers/side effects, and positive/negative testing under low-privilege roles.

Finally, **elevated privileges never create an independent transaction**. Writes inside `SECURITY DEFINER` functions stay within the caller's transaction and roll back with it. When engineered properly, applications receive strictly a scoped capability—never a blank check to read or mutate the owner's data. That is the core principle for using `SECURITY DEFINER` safely in PostgreSQL.
