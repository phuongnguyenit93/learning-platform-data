# search_path, the Public Schema, and Object Hijacking Risks in PostgreSQL

An application may use the same table or function name across multiple schemas. For example, the statement `SELECT * FROM accounts` does not specify which schema `accounts` belongs to. PostgreSQL must resolve this name using the session's `search_path` configuration. While convenient, this is also a **security boundary**: if an untrusted role has privileges to create objects in a schema searched earlier, its object may be resolved instead of the one the developer intended to call.

The risk becomes far more severe when unqualified references execute inside a `SECURITY DEFINER` function, a migration run by a privileged account, or an administrative job. In such cases, name resolution flaws can create an opportunity for **object hijacking**, resulting in untrusted logic executing within a higher-privilege security context.

This article belongs to the **Security** chapter of the *Database Engine Relational PostgreSQL* module. It focuses on understanding the name resolution mechanism, analyzing privileges on the `public` schema, constructing trusted search paths, and auditing high-privilege code paths.

After this lesson, you will be able to:

- Understand the roles of **schemas**, `USAGE`, `CREATE`, owners, and `PUBLIC`.
- Explain `search_path`, `current_schema()`, `current_schemas()`, and the impact of unqualified object names.
- Distinguish how `pg_catalog` and `pg_temp` are searched; recognize risks of shadowing tables, functions, data types, and operators.
- Understand the difference between the **schema named `public`** and the **pseudo-role `PUBLIC`**.
- Know why `CREATE` privilege on the `public` schema can be dangerous and why the default changed in PostgreSQL 15 for new databases.
- Write `SECURITY DEFINER` functions with a trusted `SET search_path`, restricted `EXECUTE` privileges, and schema-qualified object names.
- Analyze risks from function/operator overloading, extensions, migrations, connection pooling, and user-controlled search paths.
- Practice simulating name shadowing **without using another role's privileges and without modifying the actual public schema**.
- Audit schema privileges, roles, and functions, and build a safe remediation plan for live databases.

> **Safety scope:** Runnable examples use the test schemas `sp_sec_lab_private` and `sp_sec_lab_untrusted`. The second schema only **simulates** a location where an untrusted role could write, without acquiring unintended access rights. System-wide commands altering `public`/role privileges are presented as administrative examples with warnings; do not run them in production without evaluating dependencies first.

---

## 1. A Schema Is a Namespace, but Also a Privilege Boundary

### 1.1. A Single Database Can Contain Multiple Schemas

```text
database: shopdb
│
├── pg_catalog
│   ├── pg_class
│   ├── pg_namespace
│   └── system functions/operators
│
├── public
│   └── objects created in public
│
├── app
│   ├── accounts
│   ├── orders
│   └── calculate_total(...)
│
└── app_private
    ├── payment_secrets
    └── privileged_workflow(...)
```

Two schemas can contain relations with identical names:

```sql
CREATE TABLE app.accounts (...);
CREATE TABLE public.accounts (...);
```

This is a syntax illustration, not DDL to run immediately. `app.accounts` and `public.accounts` are two **distinct** objects.

### 1.2. Qualified and Unqualified Names

A **qualified** name includes the schema:

```sql
SELECT * FROM app.accounts;
```

An **unqualified** name contains only the object name:

```sql
SELECT * FROM accounts;
```

In the second case, PostgreSQL must determine which schemas to search and in what order.

### 1.3. A Schema Does Not Automatically Grant Data Access

A role may have `USAGE` on a schema without having `SELECT` on tables inside it. Conversely, holding `GRANT SELECT` on a table is not enough to access it by name if `USAGE` on its schema is missing.

Key privileges:

| Privilege | Target | Primary Meaning |
|---|---|---|
| `USAGE` | Schema | Allows looking up/accessing objects in the schema, subject to individual object privileges |
| `CREATE` | Schema | Allows creating eligible objects inside the schema |
| `SELECT` | Table/view | Allows reading data subject to privilege and RLS rules |
| `INSERT/UPDATE/DELETE` | Table | Allows the corresponding data modification operations |
| `EXECUTE` | Function/procedure | Allows executing the routine |
| Ownership | Schema/object | Grants special administrative rights over owned objects per PostgreSQL rules |

**Core security point:** Having `CREATE` on a schema present in the `search_path` of privileged code can be far more dangerous than simply "being allowed to create tables/functions in a namespace".

### 1.4. A Schema Is Not an Isolated Database

Schemas within the same database share connections and system catalogs. Never treat a public schema as a strong enough sandbox for untrusted SQL code, especially when roles can create functions, operators, casts, or extensions according to their privileges.

---

## 2. What Is search_path?

### 2.1. Definition

`search_path` is a configuration parameter listing the schemas PostgreSQL searches when resolving an object name that has **no explicit schema qualifier**.

Example:

```sql
SET search_path = app, public;

SELECT * FROM orders;
```

If `app.orders` exists and the role can access it, `orders` is typically resolved to `app.orders` before `public.orders`.

### 2.2. Viewing the Configuration

```sql
SHOW search_path;

SELECT current_setting('search_path') AS raw_path;
```

The raw setting string does not necessarily equal the list of schemas **actually** used; it may contain non-existent names, schemas without `USAGE`, or omit implicitly searched schemas.

### 2.3. current_schema()

```sql
SELECT current_schema();
```

Returns the first schema in the current search path that can serve as the default target for creating objects, according to PostgreSQL rules. If no suitable schema exists, creating an object with an unqualified name may fail.

### 2.4. current_schemas()

```sql
SELECT
    current_schemas(false) AS explicitly_resolved_schemas,
    current_schemas(true) AS including_implicit_schemas;
```

- `current_schemas(false)` shows the resolved path schemas, excluding implicit schemas.
- `current_schemas(true)` includes **implicitly** searched schemas such as `pg_catalog` and the temporary schema when present.

This is a more reliable inspection tool than just reading the `SHOW search_path` string.

### 2.5. A Schema in the Path Without USAGE

A schema name that does not exist or lacks `USAGE` privilege is typically skipped during object lookup rather than acting as configured. Therefore, running:

```sql
SET search_path = app_private, public;
```

does not automatically grant access to `app_private`. Always check the executing role's privileges.

### 2.6. The Path Is a Session Parameter

`search_path` can be influenced by database defaults, role defaults, session settings, transaction-local settings, connection options, or explicit `SET` statements in code. Do not inspect a single server configuration file and assume every connection uses that value.

---

## 3. Simple Example: Same Table Name, Different Results

### 3.1. Simulating Two Schemas

```sql
CREATE SCHEMA sp_sec_lab_private;
CREATE SCHEMA sp_sec_lab_untrusted;

CREATE TABLE sp_sec_lab_private.sample_items (
    item_id INTEGER PRIMARY KEY,
    label TEXT NOT NULL
);

CREATE TABLE sp_sec_lab_untrusted.sample_items (
    item_id INTEGER PRIMARY KEY,
    label TEXT NOT NULL
);

INSERT INTO sp_sec_lab_private.sample_items
VALUES (1, 'TRUSTED DATA');

INSERT INTO sp_sec_lab_untrusted.sample_items
VALUES (1, 'UNTRUSTED DATA');
```

**Note:** The schema `sp_sec_lab_untrusted` is **created by you solely for simulation**; this lab does not grant `CREATE` to other roles or create decoy objects inside an active `public` schema.

### 3.2. Path Prioritizing the Trusted Schema

```sql
BEGIN;
SET LOCAL search_path =
    pg_catalog, sp_sec_lab_private, sp_sec_lab_untrusted, pg_temp;

SELECT item_id, label
FROM sample_items;

ROLLBACK;
```

The unqualified query resolves `sp_sec_lab_private.sample_items` and returns `TRUSTED DATA`.

### 3.3. Changing the Path Order

```sql
BEGIN;
SET LOCAL search_path =
    pg_catalog, sp_sec_lab_untrusted, sp_sec_lab_private, pg_temp;

SELECT item_id, label
FROM sample_items;

ROLLBACK;
```

This time, unqualified `sample_items` resolves to the table in the simulated untrusted schema and returns `UNTRUSTED DATA`.

### 3.4. Qualified Names Are Unaffected by Path

```sql
SELECT item_id, label
FROM sp_sec_lab_private.sample_items;
```

A schema-qualified query targets that exact object without relying on `search_path` to pick between identically named tables.

### 3.5. Lesson Learned

If a program assumes `FROM sample_items` always refers to the trusted table, someone allowed to create an identically named table in an earlier schema can cause the program to **read or write the wrong object**. When privileged code executes it, the impact can exceed the privileges the object creator was supposed to hold.

---

## 4. Default Elements: "$user", public, pg_catalog

### 4.1. Common Default

In many PostgreSQL databases, `SHOW search_path` returns:

```text
"$user", public
```

This is a common example, **not a guarantee** that your database has the exact same value.

### 4.2. What Does "$user" Mean?

`"$user"` is a special placeholder representing a schema having the same name as `CURRENT_USER` if such a schema exists and is accessible. It is not a literal schema named `$user`.

For example, if role `alice` has an accessible schema `alice`, then `alice` can be searched before `public`. If the schema does not exist or lacks appropriate privileges, this entry has no effect.

### 4.3. public Is a Real Schema

`public` is a real namespace typically created by default in many databases. It can contain tables, views, functions, types, and other objects. **The name `public` does not make it inherently safe or unsafe; object-creation privileges and its position in the path determine the risk.**

### 4.4. pg_catalog Contains System Objects

`pg_catalog` contains most system catalog tables, built-in types, functions, and operators.

If `pg_catalog` is **not explicitly listed** in `search_path`, PostgreSQL generally searches it **before** the schemas listed in the path.

For example:

```sql
SET search_path = sp_sec_lab_untrusted, sp_sec_lab_private;
```

does not mean every function in `sp_sec_lab_untrusted` takes precedence over a matching function signature in `pg_catalog`: `pg_catalog` is still searched implicitly first under this rule.

### 4.5. However, pg_catalog Can Be Placed in an Unfavorable Position

If `pg_catalog` is **explicitly listed**, its position in the list matters:

```sql
-- Do not use as a production config for privileged code:
SET search_path =
    sp_sec_lab_untrusted, pg_catalog, sp_sec_lab_private;
```

Placing an untrusted schema before `pg_catalog` can increase shadowing risks for certain function, operator, or type names. **Never assume PostgreSQL always ignores the position of `pg_catalog`.**

### 4.6. A Readable Safe Configuration

```sql
SET search_path = pg_catalog, sp_sec_lab_private, pg_temp;
```

In a code path using only `sp_sec_lab_private` managed by trusted roles, this configuration is a sound example:

- `pg_catalog` first for built-in names.
- Trusted schema placed ahead of any untrusted namespace.
- `pg_temp` placed last to minimize temporary objects shadowing trusted tables or types.

Security still depends on **who has `CREATE` privileges in each schema**, not on the `SET` string alone.

---

## 5. pg_temp: A Special Resolution Path

### 5.1. Session-Scoped Temporary Schemas

When a session creates a temporary table:

```sql
CREATE TEMP TABLE temp_example (id INTEGER);
```

PostgreSQL assigns a session-private temporary schema (internally named like `pg_temp_N`). `pg_temp` is a convenient alias referring to the current session's temporary schema.

### 5.2. pg_temp Can Be Searched First If Unlisted

For relations and certain data type names, when a temporary schema exists and `pg_temp` is **not explicitly listed** in the path, PostgreSQL may prioritize searching the temporary schema before other schemas.

This is a notorious trap for `SECURITY DEFINER` functions referencing unqualified tables.

### 5.3. Practicing Safe Temporary Table Shadowing

With `sp_sec_lab_private.sample_items` already created, run:

```sql
BEGIN;

CREATE TEMP TABLE sample_items (
    item_id INTEGER,
    label TEXT
) ON COMMIT DROP;

INSERT INTO pg_temp.sample_items
VALUES (1, 'TEMP DATA');

SET LOCAL search_path = sp_sec_lab_private;

SELECT item_id, label
FROM sample_items;

ROLLBACK;
```

Under relation lookup rules when the temp schema exists without being explicitly listed in the path, `sample_items` resolves to the **temporary table**, returning `TEMP DATA`.

### 5.4. Placing pg_temp at the End of the Path

```sql
BEGIN;

CREATE TEMP TABLE sample_items (
    item_id INTEGER,
    label TEXT
) ON COMMIT DROP;

INSERT INTO pg_temp.sample_items
VALUES (1, 'TEMP DATA');

SET LOCAL search_path = pg_catalog, sp_sec_lab_private, pg_temp;

SELECT item_id, label
FROM sample_items;

ROLLBACK;
```

Now PostgreSQL finds `sp_sec_lab_private.sample_items` before the temporary table because `pg_temp` is explicitly placed **after** the trusted schema.

### 5.5. pg_temp Is Not Searched Uniformly for All Object Types

Important distinction:

- The temporary schema has special priority lookup behavior for **relations** and **data types**.
- PostgreSQL **does not search the temporary schema for functions or operators** the same way it does for ordinary tables/types.

Do not wrongly conclude that a function can be shadowed simply by placing a function in `pg_temp` under the exact same rules as temporary tables.

### 5.6. Why Must pg_temp Still Go Last in SECURITY DEFINER?

A privileged function may reference unqualified tables or data types. Placing `pg_temp` explicitly at the end of the search path prevents temporary relations or types from taking precedence over trusted schemas.

---

## 6. The public Schema and the PUBLIC Role Are Different Concepts

### 6.1. The Schema Named public

`public` is a namespace inside a database:

```sql
SELECT oid, nspname
FROM pg_namespace
WHERE nspname = 'public';
```

### 6.2. The Pseudo-Role PUBLIC

In privilege syntax, `PUBLIC` represents the group of **all roles** for shared grants:

```sql
GRANT USAGE ON SCHEMA public TO PUBLIC;
```

This is an illustrative administrative statement; **there is no need to run it** in a lab database without reason.

### 6.3. Both "public" Terms in a Single Statement

```sql
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
```

Meaning:

- `SCHEMA public`: the schema object named `public`.
- `FROM PUBLIC`: revokes the `CREATE` privilege previously granted to all roles.

This **does not drop the `public` schema** and **does not revoke grants** explicitly given to individual roles directly.

### 6.4. USAGE Is Not CREATE

A common configuration:

```text
PUBLIC role:
  USAGE on schema public
  NO CREATE on schema public
```

Allows looking up permitted objects in `public` without allowing every role to create new objects there.

### 6.5. Never Blindly Run REVOKE ALL

The command:

```sql
-- Not recommended directly without prior evaluation:
-- REVOKE ALL ON SCHEMA public FROM PUBLIC;
```

also revokes `USAGE`, breaking applications that call `public.some_function` or query `public.some_table` if they have no other grants. If the goal is solely to stop object creation, evaluate **`REVOKE CREATE` first**.

---

## 7. How Did PostgreSQL 15 Change the Default for public?

### 7.1. Before PostgreSQL 15

In the traditional default configuration of many PostgreSQL databases prior to version 15, the `public` schema commonly had:

- `USAGE` for `PUBLIC`.
- `CREATE` for `PUBLIC`.

That meant an untrusted role able to connect to the database could potentially create objects in `public`, unless a DBA revoked that privilege.

### 7.2. PostgreSQL 15+ for Newly Created Databases

Starting in PostgreSQL 15, the defaults for **newly created databases using the standard template** became safer:

- The `public` schema is typically owned by the special role **`pg_database_owner`**.
- The `CREATE` privilege on `public` is **no longer granted to `PUBLIC` by default**.
- `USAGE` for `PUBLIC` may still be granted by default.

`pg_database_owner` is a predefined role designed to bind database ownership to appropriate objects; it does not represent all database users.

### 7.3. Never Infer ACLs From server_version

A server running PostgreSQL 16/17/18 may still host a database upgraded from an older version, cloned from a customized template, or manually modified by a DBA. Therefore:

> **Never assume "we are on PostgreSQL 15+, so PUBLIC definitely cannot CREATE in public." Always audit the actual ACL of each database.**

### 7.4. Why Do Upgraded Databases Still Need Auditing?

When upgrading a cluster or database, PostgreSQL does not automatically strip previously configured schema privileges. Legacy permissions persist, and extensions or application migrations may also alter grants.

### 7.5. Recommended Privilege Model

A typical clean design:

```text
public:
    USAGE for application roles only when genuinely needed
    CREATE reserved strictly for owner / trusted migration role

app:
    owned by trusted migration role
    explicit read/write granted to runtime roles

app_private:
    CREATE reserved for trusted owner
    minimal USAGE/EXECUTE granted to roles that need it
```

Never grant `CREATE` on a schema included in the search path of privileged code to any role you do not fully trust.

---

## 8. Why Can CREATE Privilege in search_path Become a Security Issue?

### 8.1. Creating Objects Goes Beyond Storing Data

A role with `CREATE` on a schema can create various object types subject to applicable privileges, such as tables, views, functions, or operators.

If privileged code uses unqualified names and its search path includes that schema, newly created objects can interfere with name resolution.

### 8.2. Typical Risk Chain

```text
Low-privilege role
    |
    v
Has CREATE on an earlier schema in search_path
    |
    v
Creates identically named object / overload
    |
    v
Privileged code uses unqualified names
    |
    v
PostgreSQL selects object per lookup rules
    |
    v
Privileged code may access the wrong table /
invoke the wrong function, operator, or type
```

This is a threat model for **prevention**, not instructions for exploiting unauthorized systems.

### 8.3. Name Shadowing and Object Hijacking

- **Name shadowing:** a new object with the same name hides another object during lookup.
- **Overloading:** identical function/operator names with different parameter signatures; routine selection rules go beyond simple schema order.
- **Object hijacking:** code intending to call a trusted object is redirected to an untrusted object.

### 8.4. Routine EXECUTE Privileges and Escalation

A `SECURITY DEFINER` function runs with the privileges of the **function owner**. If its body invokes an untrusted function through name resolution, unintended behavior can execute inside a higher-privilege security context than the author intended.

A single unqualified call inside privileged code can introduce a vulnerability, even when **SQL parameters are properly bound and there is no string-concatenation SQL injection**.

### 8.5. The Root Cause Is the Trust Boundary

Placing a schema into the `search_path` of a privileged routine means **trusting everyone who can create objects in that schema**. It is not merely a stylistic choice for shorter SQL.

---

## 9. Lab: Simulating Function Shadowing Without Elevated Privileges

### 9.1. Create a Function in the Trusted Schema

```sql
CREATE FUNCTION sp_sec_lab_private.format_label(p_text TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $function$
    SELECT 'TRUSTED: ' || p_text;
$function$;
```

### 9.2. Create an Identically Named Function in the Simulated Untrusted Schema

```sql
CREATE FUNCTION sp_sec_lab_untrusted.format_label(p_text TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $function$
    SELECT 'UNTRUSTED: ' || p_text;
$function$;
```

Both functions are harmless examples; they merely concatenate strings and access no sensitive data.

### 9.3. Changing Only the Path Changes Which Function Runs

```sql
BEGIN;

SET LOCAL search_path =
    pg_catalog, sp_sec_lab_private, sp_sec_lab_untrusted, pg_temp;

SELECT format_label('hello'::text) AS selected_function;

ROLLBACK;
```

Result:

```text
TRUSTED: hello
```

Flip the order:

```sql
BEGIN;

SET LOCAL search_path =
    pg_catalog, sp_sec_lab_untrusted, sp_sec_lab_private, pg_temp;

SELECT format_label('hello'::text) AS selected_function;

ROLLBACK;
```

Result:

```text
UNTRUSTED: hello
```

### 9.4. Qualified Calls Produce Deterministic Results

```sql
SELECT
    sp_sec_lab_private.format_label('hello'::text)
        AS trusted_result,
    sp_sec_lab_untrusted.format_label('hello'::text)
        AS untrusted_result;
```

The output does not depend on how the two schemas are ordered in the session search path.

### 9.5. Takeaway from the Experiment

This is solely a demonstration of **name resolution**, not actual privilege escalation. However, the same mechanism becomes critical if the call sits inside privileged code, especially when a low-privilege role can create functions in a schema searched earlier.

---

## 10. Function Overloading Complicates the Risk

### 10.1. Same Name Does Not Always Mean Same Signature

PostgreSQL supports function overloading:

```sql
CREATE FUNCTION sp_sec_lab_private.show_value(p_value INTEGER)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $function$
    SELECT 'integer: ' || p_value::text;
$function$;

CREATE FUNCTION sp_sec_lab_private.show_value(p_value TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $function$
    SELECT 'text: ' || p_value;
$function$;
```

A call like:

```sql
SELECT sp_sec_lab_private.show_value(10);
```

has a clearer signature than a call passing an untyped string literal:

```sql
SELECT sp_sec_lab_private.show_value('10');
```

### 10.2. A Routine Can Be Intercepted Without an Identical Signature

If an untrusted schema is on the path, a role may be able to create a **function with the same name and a different signature** depending on privileges. Function resolution considers argument types, implicit casts, variadic/default arguments, and type match specificity.

Therefore, never assume:

> "The system/trusted function always wins because it appears earlier in the path; overloads in other schemas are surely harmless."

That statement is overly simplistic. A better-matching overload or a call with an `unknown`-type literal can complicate candidate selection.

### 10.3. Implicit pg_catalog Does Not Replace Other Defenses

`pg_catalog` is generally searched first when unlisted in the path, which helps protect matching built-in names and signatures. However, **function resolution is not simply "check the first schema for the name and stop"**. With overloading and casts, you must control routine creation privileges across searchable schemas and prefer qualified names and explicit casts in sensitive code.

### 10.4. Do Not Dishonestly Mark Wrappers IMMUTABLE

A security routine can use `SET search_path` to stabilize resolution. Never try to work around name resolution quirks by falsely declaring a function `IMMUTABLE` if it actually reads data or depends on session environment. Wrong volatility metadata causes the optimizer to plan queries on false assumptions.

---

## 11. Operators and Data Types Also Undergo Name Resolution

### 11.1. Not Just FROM Clauses and Function Names

SQL constructs subject to name lookup include:

- Tables, views, sequences, data types.
- Functions/procedures.
- Operators.
- Objects with specific lookup rules such as collations and domains.

Security risk is not confined to `SELECT * FROM orders`.

### 11.2. Qualified Operators

PostgreSQL supports schema-qualifying operators:

```sql
SELECT 1 OPERATOR(pg_catalog.=) 1 AS equals_one;
```

In ultra-sensitive code requiring strict control over operator resolution, this syntax can be used; however, normally combining a **trusted search_path + explicit argument types + no CREATE for untrusted roles** is more readable and effective.

### 11.3. Type Shadowing and pg_temp

The temporary schema can be searched earlier for **type names** when `pg_temp` is not explicitly placed last. A privileged function constructing or casting to an unqualified type must be reviewed just like unqualified relations.

### 11.4. Qualification Does Not Replace Type Safety

`SELECT 1 OPERATOR(pg_catalog.=) 1` illustrates operator qualification; it does not replace data type checks, input validation, parameterized queries, or SELECT/EXECUTE privileges.

---

## 12. SECURITY DEFINER: Purpose, Benefits, and Risks

### 12.1. SECURITY INVOKER

Regular functions default to `SECURITY INVOKER`: data access inside the function executes with the caller's privileges, under applicable security rules.

```sql
CREATE FUNCTION some_schema.public_helper(...)
RETURNS ...
LANGUAGE plpgsql
SECURITY INVOKER
AS $function$
BEGIN
    ...
END;
$function$;
```

This is a syntax illustration, not a complete function.

### 12.2. SECURITY DEFINER

`SECURITY DEFINER` causes the function to run with the **owner's** privileges rather than the caller's normal execution privileges. This is useful for exposing a tightly scoped operation over data that application roles cannot access directly.

For example: allowing calls to `close_period(p_id)` instead of granting direct UPDATE on all underlying accounting tables.

### 12.3. Why Is It Dangerous With an Untrusted search_path?

Consider a conceptual privileged routine:

```sql
-- DO NOT deploy this unsafe pattern:
-- CREATE FUNCTION privileged_action(...)
-- RETURNS ...
-- LANGUAGE plpgsql
-- SECURITY DEFINER
-- AS $function$
-- BEGIN
--     SELECT ... FROM accounts; -- unqualified name
--     PERFORM validate_record(...); -- unqualified function
-- END;
-- $function$;
```

If the function does not lock down a trusted search path and the caller can influence `search_path` (or a schema on the path permits untrusted `CREATE`), resolving `accounts` or `validate_record` can be hijacked.

### 12.4. Multi-Layered Defense

1. **Pin a safe search_path on the function** using the `SET search_path` clause.
2. Include only **trusted** schemas before `pg_temp`.
3. Use schema-qualified names for critical tables, functions, and types.
4. Never grant `CREATE` on trusted schemas to untrusted roles.
5. Revoke `EXECUTE` from `PUBLIC` if the function is intended only for specific roles.
6. Audit the function owner, `SECURITY DEFINER`, and RLS interactions.
7. Test under actual calling roles and intentionally adversarial search paths.

No single measure replaces the others in every scenario.

---

## 13. Lab: Writing a Safe SECURITY DEFINER Function

### 13.1. Trusted Data Table

```sql
CREATE TABLE sp_sec_lab_private.accounts (
    account_id INTEGER PRIMARY KEY,
    account_name TEXT NOT NULL
);

INSERT INTO sp_sec_lab_private.accounts
VALUES (1, 'demo-account');
```

This article illustrates syntax and name resolution only, containing no real personal data or secrets.

### 13.2. Function With Function-Level SET search_path

```sql
BEGIN;

CREATE FUNCTION sp_sec_lab_private.describe_account(
    p_account_id INTEGER
)
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, sp_sec_lab_private, pg_temp
AS $function$
DECLARE
    v_name TEXT;
BEGIN
    IF p_account_id IS NULL THEN
        RAISE EXCEPTION 'Account ID is required'
            USING ERRCODE = '22023';
    END IF;

    SELECT a.account_name
    INTO STRICT v_name
    FROM sp_sec_lab_private.accounts AS a
    WHERE a.account_id = p_account_id;

    RETURN sp_sec_lab_private.format_label(v_name);
END;
$function$;

REVOKE ALL ON FUNCTION
    sp_sec_lab_private.describe_account(INTEGER)
FROM PUBLIC;

COMMIT;
```

### 13.3. Why Set SET search_path on the Function?

Adding `SET search_path = ...` to the function definition ensures PostgreSQL applies that path whenever the function runs, rather than trusting whatever path the calling session happens to have.

This is essential protection for `SECURITY DEFINER` routines because the code must know **which schemas are allowed to participate in name resolution**.

### 13.4. Why Put pg_catalog First?

`pg_catalog` provides standard system functions, operators, and types. Placing it first ensures an untrusted application schema is never inadvertently prioritized ahead of built-ins.

### 13.5. Why Put pg_temp Last?

Because temporary tables and types have special priority lookup rules, explicitly listing `pg_temp` last prevents temporary objects from shadowing trusted tables or types referenced unqualified inside the function.

### 13.6. Why Still Schema-Qualify Tables and Functions?

The function explicitly writes:

```sql
FROM sp_sec_lab_private.accounts

RETURN sp_sec_lab_private.format_label(v_name);
```

This minimizes reliance on lookup order and makes the code straightforward to audit. `SET search_path` remains valuable for built-ins and any references not easily schema-qualified everywhere.

### 13.7. Why REVOKE EXECUTE in the Same Transaction as CREATE FUNCTION?

By default, PostgreSQL typically grants `EXECUTE` to `PUBLIC` when creating a new function. A privileged routine should not experience even a brief window where unintended callers can invoke it.

Putting `CREATE FUNCTION` and `REVOKE ... FROM PUBLIC` inside **the same transaction** eliminates that unintended exposure window between commits.

For production, also explicitly `GRANT EXECUTE` to the intended role and `GRANT USAGE` on the schema if needed.

### 13.8. Calling With an Adversarial Caller search_path

```sql
BEGIN;

SET LOCAL search_path =
    sp_sec_lab_untrusted, pg_catalog, sp_sec_lab_private, pg_temp;

SELECT sp_sec_lab_private.describe_account(1);

ROLLBACK;
```

This tests the function using the role that created it in the lab. The function still resolves the schema-qualified table and helper; its trusted function-level search path also isolates it from the caller's path.

### 13.9. Other Roles Require Explicit Grants

If an `app_runtime` role has been created beforehand by an administrator, administrative grants might look like:

```sql
-- Only use when the role exists and policy permits:
-- GRANT USAGE ON SCHEMA sp_sec_lab_private TO app_runtime;
-- GRANT EXECUTE ON FUNCTION
--     sp_sec_lab_private.describe_account(INTEGER)
-- TO app_runtime;
```

Do not automatically grant `SELECT` on `sp_sec_lab_private.accounts` if the goal is to restrict access strictly through the controlled function.

### 13.10. SECURITY DEFINER Does Not Make a Function Safe by Itself

The function still requires:

- Caller-identity authorization checks when business logic demands them.
- Input validation.
- Limiting the blast radius of operations.
- No dynamic SQL concatenating raw user input.
- A function owner less privileged than superuser whenever possible.
- Careful review of RLS, grants, and side effects.

`SECURITY DEFINER` only switches the privilege context; **it can amplify risk** if poorly designed.

---

## 14. Why Not Simply Use SET search_path Inside the Function Body?

### 14.1. Function-Level SET

Prefer:

```sql
CREATE FUNCTION app_private.sensitive_action(...)
RETURNS ...
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app_private, pg_temp
AS $function$
BEGIN
    ...
END;
$function$;
```

This pattern declares the path as a **security property of the routine**.

### 14.2. SET Inside the Body

If a function executes `SET search_path = ...` part-way through its body, earlier statements or expressions may already have been resolved under another search path, and restoring state becomes more error-prone.

For critical functions, define the path declaratively in the function header and use schema-qualified names instead of scattered imperative `SET` statements.

### 14.3. Never Trust Caller-Controlled Configuration Variables

Do not write patterns like:

```text
SECURITY DEFINER function
  -> reads arbitrary path or schema name supplied by caller
  -> concatenates into SQL statement
  -> runs under owner privileges
```

That can combine both a **name-resolution vulnerability** and **SQL injection** if string concatenation is unsafe.

### 14.4. When Dynamic SQL Is Truly Necessary

With `EXECUTE` in PL/pgSQL, dynamic schema/table names must be strictly validated and properly quoted with `format('%I.%I', schema_name, table_name)` for identifiers, alongside `USING` for data values.

However, **proper quoting alone is not enough**: an untrusted caller could still supply the name of a legitimate table that the privileged function is not supposed to expose for that business operation. Combine quoting with allowlist and authorization validation.

---

## 15. search_path Changes by Clients and Connection Pools

### 15.1. SET Affects the Session

```sql
SET search_path = sp_sec_lab_private, public;
```

A plain `SET` alters session state until reset or until the session ends, subject to PostgreSQL's transaction/configuration rules.

### 15.2. SET LOCAL Affects the Transaction

```sql
BEGIN;

SET LOCAL search_path = pg_catalog, sp_sec_lab_private, pg_temp;

SELECT current_schemas(true);

COMMIT;
```

`SET LOCAL` remains active for the duration of the current transaction, then reverts according to configuration semantics. It works well when one transaction needs a temporary path without leaking state to subsequent requests.

### 15.3. Session Pooling

If a connection pool reuses sessions:

```text
Request A: SET search_path = tenant_a, public
              |
              v
      Return connection to pool
              |
              v
Request B: borrows same connection
              |
              v
    search_path may still be tenant_a
```

If the pool does not properly reset session state, subsequent requests may access the wrong schema or tenant. Never rely on user-mutable `search_path` as your sole tenant isolation boundary.

### 15.4. Recommendations

- Configure deterministic startup defaults at connection/session initialization.
- When using transaction-local context, use `SET LOCAL` and ensure transactions complete cleanly.
- Reset and verify state upon returning connections to the pool per your driver/pool design.
- Keep using schema-qualified names in sensitive code.
- Never tie role or tenant authorization solely to `search_path`.

### 15.5. search_path Hijacking Is Not SQL Injection

SQL injection generally involves untrusted input being concatenated into SQL syntax; object hijacking via `search_path` is an **object resolution** risk even when query text is static and all parameters are properly bound.

Both issues can compound each other, though they are distinct; applications require **both parameterization and trusted namespace resolution**.

---

## 16. Unqualified CREATE Operations Also Depend on search_path

### 16.1. CREATE TABLE Without a Schema

```sql
CREATE TABLE new_records (id bigint);
```

Without a schema qualifier, PostgreSQL creates the object in the current target schema determined by `search_path`, subject to `CREATE` privileges.

A migration running with an unexpected path can create tables in the wrong schema.

### 16.2. Transaction Experiment

```sql
BEGIN;

SET LOCAL search_path =
    pg_catalog, sp_sec_lab_untrusted, sp_sec_lab_private, pg_temp;

SELECT current_schema() AS creation_target;

CREATE TABLE created_by_unqualified_name (
    id INTEGER PRIMARY KEY
);

ROLLBACK;
```

This demonstrates that `search_path` affects not only `SELECT` lookups, but also the target namespace when `CREATE` uses an unqualified name. `ROLLBACK` keeps the lab clean.

### 16.3. Migrations Should Use Qualified Names

```sql
CREATE TABLE app.orders (...);
CREATE INDEX orders_created_at_idx ON app.orders(created_at);
CREATE FUNCTION app_private.calculate_total(...) ...;
```

These are syntax patterns. Explicitly stating schemas in migrations reduces dependence on the default search path of whichever account runs the migration.

### 16.4. Extensions Also Have Installation Schemas

`CREATE EXTENSION` follows specific schema-selection rules depending on the extension and syntax. Installed objects live in a particular namespace, which interacts with `search_path` and create/lookup privileges.

Never grant extension installation privileges or choose extension target schemas arbitrarily. For extensions containing SQL scripts, follow PostgreSQL and extension security guidance closely and ensure the target schema is trusted.

### 16.5. Schema-Qualification Does Not Bypass Missing Privileges

`CREATE TABLE app.orders` still checks appropriate privileges. Qualification only fixes the **target**; it does not bypass permission checks.

---

## 17. Views and Stored Object Definitions: Do Not Overgeneralize

### 17.1. Upon CREATE VIEW

PostgreSQL parses the view query, resolves referenced objects, and stores dependency records in the system catalogs.

```sql
CREATE VIEW sp_sec_lab_private.v_items AS
SELECT item_id, label
FROM sp_sec_lab_private.sample_items;
```

### 17.2. Be Careful About Claiming "Changing the Path Changes Every View"

An already-created view is **not equivalent** to storing raw SQL text and re-resolving every table name from scratch against the caller's `search_path` on every `SELECT`. PostgreSQL stores the parsed query tree and object OID dependencies for the view.

Key audit questions:

- What path was active **when the view was created** if its definition used unqualified names?
- Which object OIDs does the view actually depend on?
- Who owns the view and what are its read permissions?
- Do underlying functions or operators have safe resolution semantics?

### 17.3. Functions Vary in How Bodies Are Stored and Compiled

PL/pgSQL functions, SQL functions, and other languages have distinct parse, plan, and cache behaviors. Do not make blanket claims that every unqualified name inside every routine is re-resolved on every invocation.

The practical defense remains: **pin a trusted `search_path` on privileged routines and schema-qualify critical references**, then verify dependencies and behavior on your target PostgreSQL version.

### 17.4. CREATE VIEW in an Untrusted Schema

If a role can create a view inside a schema trusted by privileged code, that code may be impacted if it references that view/table name unqualified. However, view execution permissions and owner/invoker/RLS semantics must be analyzed individually; do not assume every view executes with owner rights across all versions and configurations.

---

## 18. Auditing the public Schema and CREATE Privileges

**Never modify privileges before inspecting the current state.**

### 18.1. Database and Version Being Audited

```sql
SELECT
    current_database() AS database_name,
    current_user AS effective_user,
    session_user AS session_user,
    current_setting('server_version') AS server_version,
    current_setting('search_path') AS configured_search_path;
```

### 18.2. Inspecting the Owner and ACL of public

```sql
SELECT
    n.nspname AS schema_name,
    pg_get_userbyid(n.nspowner) AS schema_owner,
    n.nspacl AS acl
FROM pg_namespace AS n
WHERE n.nspname = 'public';
```

`nspacl` shows the privileges stored in the catalog. A `NULL` value indicates default privileges are in effect, **not necessarily zero privileges**.

### 18.3. Checking Effective Privileges of current_user

```sql
SELECT
    has_schema_privilege('public', 'USAGE')
        AS can_use_public,
    has_schema_privilege('public', 'CREATE')
        AS can_create_in_public;
```

If a role can `CREATE`, determine **where that privilege comes from**:

- Owns the schema or database where applicable.
- Member of a role holding the privilege.
- Direct grant to the role.
- Privilege granted to `PUBLIC`.
- Broader administrative rights (such as superuser).

A `true` value alone does not prove the grant came from **`PUBLIC`**.

### 18.4. Auditing All Login Roles Able to CREATE in public

```sql
SELECT
    r.rolname,
    r.rolcanlogin,
    has_schema_privilege(
        r.oid,
        'public',
        'CREATE'
    ) AS can_create_in_public
FROM pg_roles AS r
WHERE r.rolcanlogin
ORDER BY r.rolname;
```

This query finds login roles holding effective `CREATE` privileges on `public` given catalog data, role memberships, and the current database context. In real-world assessments, also audit `SET ROLE`, ownership, group memberships, and alternative privilege paths.

### 18.5. Checking Privileges in psql

In `psql`:

```text
\dn+
```

This `psql` meta-command lists schemas, owners, and access privileges according to your client version. Do not run `\dn+` as a SQL statement over JDBC.

### 18.6. Structured ACL Analysis

```sql
SELECT
    n.nspname,
    x.grantee,
    x.privilege_type,
    x.is_grantable
FROM pg_namespace AS n
CROSS JOIN LATERAL aclexplode(
    COALESCE(
        n.nspacl,
        acldefault('n', n.nspowner)
    )
) AS x
WHERE n.nspname = 'public'
ORDER BY x.grantee, x.privilege_type;
```

In ACLs, a special grantee value (`0`) represents `PUBLIC`; the `grantee` column holds a role OID rather than the string "everyone". This query helps inspect explicit and default ACL entries. To evaluate **actual effective privileges** of a specific role, still rely on `has_schema_privilege` and inspect role memberships and ownership.

---

## 19. Revoking CREATE from PUBLIC: Doing It Safely

### 19.1. Core Command

```sql
-- Only run after auditing and obtaining approval:
-- REVOKE CREATE ON SCHEMA public FROM PUBLIC;
```

This is a critical hardening step for databases where every role currently holds `CREATE` on `public`.

### 19.2. Never Run Blindly in Production

Legacy applications or migrations may rely on creating objects in `public`. Revoking `CREATE` can break workflows such as:

- Creating non-TEMP staging tables directly inside `public`.
- Deploying helper functions on startup.
- Extensions or ETL jobs writing tables into `public`.
- Migrations running under a low-privilege application role.

### 19.3. Safe Rollout Process

1. Inventory all roles and effective `CREATE` privileges.
2. Identify schemas and objects created routinely.
3. Separate trusted migration roles, runtime roles, and service accounts.
4. Move DDL into dedicated schemas owned/operated by appropriate administrative roles.
5. Test revoking the privilege in staging with matching ACLs and data shapes.
6. Apply the revocation during an approved maintenance window.
7. Monitor permission errors, deployments, and scheduled jobs.
8. Ensure legacy provisioning scripts do not re-grant `CREATE` to `PUBLIC`.

### 19.4. Direct CREATE Grants Still Remain

`REVOKE CREATE ... FROM PUBLIC` **does not automatically revoke** explicit direct grants assigned to individual roles, nor does it strip ownership privileges. To restrict an untrusted role completely, audit every source of effective privilege.

### 19.5. Separating Runtime Roles from Migration Roles

A solid model:

```text
db_owner / migration_owner:
    DDL inside trusted schemas

app_runtime:
    USAGE on required schemas
    SELECT/INSERT/UPDATE/DELETE on appropriate tables
    EXECUTE on approved routines
    NO CREATE in trusted schemas

report_reader:
    Required read-only privileges only
```

Never run web applications as superuser or schema owner just to avoid configuring grants.

---

## 20. Configuring search_path on Roles and Databases

### 20.1. ALTER ROLE SET

```sql
-- Administrative example when app_runtime already exists:
-- ALTER ROLE app_runtime
-- SET search_path = pg_catalog, app, pg_temp;
```

This sets the session default for that role on connection per configuration precedence rules. It does **not** replace attaching `SET search_path` directly to `SECURITY DEFINER` functions.

### 20.2. ALTER DATABASE SET

```sql
-- Syntax example; replace appdb with the real database name:
-- ALTER DATABASE appdb
-- SET search_path = pg_catalog, app, pg_temp;
```

This sets a database-level default, which higher-precedence settings can override.

### 20.3. ALTER ROLE IN DATABASE

```sql
-- Syntax example:
-- ALTER ROLE app_runtime IN DATABASE appdb
-- SET search_path = pg_catalog, app, pg_temp;
```

Useful when the same role connects to multiple databases using different namespace layouts.

### 20.4. Warning About Existing Sessions

Changing role or database defaults normally affects **new sessions** established afterward; long-lived pooled connections may retain their prior session state. Plan rollouts to account for pool recycling or reconnects.

### 20.5. Never Rely on Path Order as Your Sole Security Control

If a low-privilege role holds `CREATE` on `app` or `public` and that schema is on a `SECURITY DEFINER` path, merely putting `app` first does not make it safe. You must evaluate **trust of object creators**.

---

## 21. Search Path for Sensitive Functions: Selection Rules

### 21.1. A Reliable Pattern

```sql
SECURITY DEFINER
SET search_path = pg_catalog, app_private, pg_temp
```

Prerequisites:

- `app_private` is owned/managed by trusted owner/migration roles.
- No untrusted role holds `CREATE` in it.
- The function does not invoke untrusted objects via dynamic SQL.
- Critical tables and functions are schema-qualified wherever feasible.

### 21.2. Why Omit public from the Path?

`public` may be a legitimate application schema, yet in legacy databases it often accumulates objects created by diverse roles. In privileged functions, avoid putting `public` in the search path merely to save typing schema prefixes.

If a function must call `public.some_function`, consider:

- Migrating the function to a trusted schema.
- Qualifying the object name and reviewing its owner and signature.
- Ensuring untrusted roles cannot `CREATE` in `public`.

### 21.3. Never Use "$user" in Privileged Code Paths

`"$user"` can resolve to different schemas depending on the effective user. Inside `SECURITY DEFINER`, the effective user may be the function owner. Regardless of context specifics, a user-dependent path is harder to audit than an explicit list of trusted schemas.

### 21.4. Watch search_path Across Nested Function Calls

If `definer_a` calls `definer_b` or another helper, inspect:

- Does `definer_b` define its own function-level `SET search_path`?
- Who owns the helper?
- Does the helper contain dynamic SQL or unqualified references?
- Is the helper `SECURITY DEFINER` or `SECURITY INVOKER`?

Never assume a top-level function being hardened makes deeper functions in the call chain automatically safe.

### 21.5. Default EXECUTE on Functions

PostgreSQL's `GRANT EXECUTE` is not inferred from table `SELECT` privileges. Explicitly design execution permissions for every privileged routine:

```sql
-- Administrative pattern:
-- REVOKE ALL ON FUNCTION app_private.sensitive_action(integer)
-- FROM PUBLIC;
--
-- GRANT EXECUTE ON FUNCTION app_private.sensitive_action(integer)
-- TO app_runtime;
```

Do not grant broad `EXECUTE` merely because a function lives in a schema accessed by the application.

---

## 22. Application Authorization, RLS, and Definer Privileges

### 22.1. Schema Privileges Do Not Replace Row-Level Authorization

A role with `USAGE` on a schema and `SELECT` on a table may still need RLS to prevent reading other tenants' rows.

`search_path` is neither a `tenant_id` filter nor an RLS policy.

### 22.2. SECURITY DEFINER and RLS

`SECURITY DEFINER` executes with owner rights; if the function owner is the table owner or holds RLS bypass privileges, the function can observe different rows than the caller under RLS rules.

For multi-tenant functions:

- Verify caller identity from a trusted source.
- Enforce tenant and data scope explicitly in SQL.
- Test behavior under real runtime roles.
- Inspect table ownership and `FORCE ROW LEVEL SECURITY` settings where relevant.

### 22.3. Never Blindly Trust Client-Supplied tenant_id

A privileged routine accepting a `p_tenant_id` parameter from the application may need to verify that the caller is authorized for that tenant. Safely binding a SQL parameter does not prove the caller owns that tenant.

### 22.4. Keep Definer Function Owners Least-Privileged

If a routine only needs to read an authorization table and update one business table, its owner should not be a superuser. The broader the owner's privileges, the greater the blast radius of any name resolution bug.

---

## 23. Security Auditing of Functions and Routines

### 23.1. Listing SECURITY DEFINER Functions

```sql
SELECT
    n.nspname AS function_schema,
    p.proname AS function_name,
    pg_get_function_identity_arguments(p.oid) AS args,
    pg_get_userbyid(p.proowner) AS owner,
    p.prosecdef AS security_definer,
    p.proconfig AS function_settings
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE p.prosecdef
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, p.proname;
```

`prosecdef=true` indicates `SECURITY DEFINER`; `proconfig` lists function-local GUC overrides when configured.

### 23.2. NULL proconfig Does Not Automatically Prove a Vulnerability

If `proconfig` does not list `search_path`, the function may be affected by the caller's path. That is a **review indicator**, not immediate proof of exploitability—the body might fully schema-qualify everything or execute no risky lookups, though it must still be verified.

### 23.3. Inspecting Function Definitions

```sql
SELECT pg_get_functiondef(
    'sp_sec_lab_private.describe_account(integer)'::regprocedure
);
```

`pg_get_functiondef` lets you inspect the routine body and configuration. Remember that PL/pgSQL bodies may call helper functions or construct dynamic SQL, so follow dependencies along the full call chain.

### 23.4. Checking EXECUTE Privileges

```sql
SELECT
    has_function_privilege(
        'sp_sec_lab_private.describe_account(integer)',
        'EXECUTE'
    ) AS current_role_can_execute;
```

This checks the **current role**. To audit other roles, use the overload taking a role identifier and also examine role memberships and indirect grants.

### 23.5. Viewing Routines With search_path Configuration

```sql
SELECT
    p.oid::regprocedure AS routine,
    p.prosecdef,
    p.proconfig
FROM pg_proc AS p
JOIN pg_namespace AS n ON n.oid = p.pronamespace
WHERE n.nspname = 'sp_sec_lab_private'
ORDER BY p.oid::regprocedure::text;
```

For `describe_account`, `proconfig` is expected to show `search_path=pg_catalog, sp_sec_lab_private, pg_temp` as defined.

---

## 24. CREATE Privileges on Trusted Schemas and Default Privileges

### 24.1. Runtime Roles Should Not Create Objects in Code Schemas

Safe separation:

```text
app_runtime:
  USAGE on app
  SELECT/INSERT/UPDATE/DELETE on required tables
  EXECUTE on required routines
  NO CREATE on app_private
```

Reserve `CREATE` for trusted migration or owner roles.

### 24.2. Default Privileges Do Not Govern Schema CREATE

`ALTER DEFAULT PRIVILEGES` sets default object grants for **future** objects created by the target role; it is not a direct substitute for:

```sql
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
```

Those operate at two distinct layers.

### 24.3. Restricting Default EXECUTE on Newly Created Routines

When managing many privileged routines, consider:

```sql
-- Administrative pattern applied to the role creating functions:
-- ALTER DEFAULT PRIVILEGES
-- REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
```

Understand the scope of **creator role and default privileges**; do not assume this statement retroactively alters existing functions or applies to every creator role automatically.

### 24.4. GRANT USAGE Does Not Secure a Schema With Broad CREATE

If untrusted roles hold `CREATE` on a schema in privileged code's search path, adding `GRANT USAGE` for additional roles does not remove the risk.

Securing the trust boundary requires controlling **who can create objects** and **which objects get resolved**.

---

## 25. Object Types and Commonly Overlooked Audit Points

| Context | Risk When Unqualified | Defense |
|---|---|---|
| `FROM accounts` | Reads shadowing table or view | `app.accounts` |
| `UPDATE balances` | Modifies wrong relation | `app.balances` plus privilege checks |
| `PERFORM helper(...)` | Resolves untrusted helper or overload | `app_private.helper(...)`, explicit arg types |
| `SELECT x + y` | Operator resolution influenced in edge contexts | Trusted path, explicit types, qualification if needed |
| Unqualified type cast | Type shadowing | Qualified type / trusted path |
| `nextval('sequence_name')` | Depends on sequence resolution path | `'schema.sequence_name'::regclass` as appropriate |
| Unqualified CREATE TABLE | Creates table in unintended schema | `CREATE TABLE app.name` |
| Extension objects | Installed or resolved in unintended schema | Install into trusted schema per docs |
| Dynamic SQL with schema/table names | Wrong object selection or injection | Allowlist, `format('%I',...)`, bind parameters |
| `SECURITY DEFINER` trigger function | Runs as owner; exposed to path issues | Function-level `SET search_path` and code audit |

### 25.1. regclass and Sequence Names

For a trusted sequence, explicitly include the schema name inside the cast literal:

```sql
-- Example when app.order_id_seq exists:
-- SELECT nextval('app.order_id_seq'::regclass);
```

Some `regclass` expressions resolve at parse/plan time according to cast semantics; do not equate that safety with dynamically concatenated unvalidated strings.

### 25.2. Dynamic Identifiers Require Business-Level Validation

`format('%I.%I', schema_name, table_name)` only **quotes identifiers**; it does not ensure the requested schema or table is authorized for the task. In privileged routines, verify the origin of identifiers and enforce an allowlist.

---

## 26. Security Testing by Role and Path

### 26.1. Never Test Exclusively as the Database Owner

Database owners typically hold broad privileges, so testing solely as the owner misses `permission denied` errors and RLS behavior that only surface under runtime roles.

### 26.2. Test Matrix

| Scenario | What to Verify |
|---|---|
| Caller with standard path | Queries/functions behave properly |
| Caller intentionally puts untrusted-sim schema first | Sensitive routines still resolve intended objects |
| Caller creates TEMP TABLE matching trusted table name | Definer routine does not read the temp table |
| Role without CREATE on public | Cannot create objects in public |
| Role without EXECUTE on privileged routine | Call is denied |
| Role with EXECUTE but without direct table SELECT | Only scoped routine operations succeed |
| Tenant A role queries with tenant B ID | Denied properly by authorization/RLS |
| Migrations run under altered path | Objects still land in intended schemas |
| Pooled session reused | Does not carry over path/tenant from prior request |

### 26.3. Simulating Adversarial Paths Without Lasting Session Side Effects

```sql
BEGIN;

SET LOCAL search_path =
    sp_sec_lab_untrusted, pg_catalog, sp_sec_lab_private, pg_temp;

SELECT
    current_setting('search_path') AS configured,
    current_schemas(true) AS resolved;

SELECT sp_sec_lab_private.describe_account(1);

ROLLBACK;
```

All path changes here are transaction-local. The function itself still must be invoked with its explicit schema prefix.

### 26.4. Testing Temp Tables Against the Right Object Class

`pg_temp` takes priority for tables and types, not functions or operators. Test using a temporary table matching the name of a relation used by the definer function; do not draw conclusions from tests targeting a different object class.

### 26.5. Recording Test Results

Document:

- PostgreSQL version.
- Active role and `session_user`.
- Configured path and resolved schemas.
- Schema owner and ACL.
- Routine definition and `proconfig`.
- Expected vs. actual outcomes and SQLSTATE codes.

Never store secrets, tokens, or connection passwords in test logs.

---

## 27. Hardening Plan for Long-Running Databases

### Phase 1 — Inventory

1. List all databases and PostgreSQL versions.
2. Audit the owner and ACL of `public` in every database.
3. List all login roles with effective `CREATE` in `public`.
4. List every schema appearing in application and job search paths.
5. List all `SECURITY DEFINER` routines and their `EXECUTE` grants.
6. Search critical code for unqualified references and dynamic SQL.

### Phase 2 — Define Target State

1. Runtime roles have no `CREATE` in trusted schemas.
2. DDL executes through controlled migration owner roles.
3. Privileged routines pin a trusted function-level `search_path`.
4. Critical objects are schema-qualified.
5. Privileged routine `EXECUTE` is granted strictly to required roles.
6. All pools and connections establish deterministic startup paths.

### Phase 3 — Rollout

1. Create trusted schemas if required.
2. Move routines and tables out of `public` if they do not belong in a shared namespace.
3. Update references, grants, and application queries.
4. Add function-level `search_path` clauses.
5. Revoke `CREATE` from `PUBLIC` or untrusted roles per policy.
6. Deploy migrations in tested dependency order.
7. Verify objects and role privileges post-rollout.

### Phase 4 — Operations

1. Automate audits for `CREATE` and `EXECUTE` privileges.
2. Review new privileged routines prior to deployment.
3. Monitor changes to owners, extensions, and default privileges.
4. Alert on unexpected permission errors.
5. Validate pool reset behavior and multi-tenant isolation boundaries.
6. Maintain a migration rollback plan that does not blindly reopen broad privileges.

### 27.1. Moving Objects Out of public Requires Planning

`ALTER ... SET SCHEMA` changes qualified names referenced by applications, catalog dependencies, grants, and search paths. Never mass-move all objects out of `public` via script without analyzing application queries, dependencies, extensions, RLS, and permissions.

### 27.2. Revoking CREATE Does Not Remove Existing Objects

Even after locking down `CREATE`, unfamiliar tables or functions created earlier may remain inside `public`. A complete audit inspects **existing objects, their owners, and their definitions**, not solely current ACLs.

---

## 28. Common Misconceptions and Mistakes

**1. "search_path only affects SELECT FROM."** False. It also affects functions, types, operators, and object-creation namespaces.

**2. "public is a role."** False. `public` is a schema; `PUBLIC` in GRANT/REVOKE is a pseudo-role representing all roles.

**3. "USAGE on a schema means SELECT on every table."** False. Schema privileges and object privileges are separate layers.

**4. "CREATE on a schema only lets you create harmless tables."** False. Creating objects resolved by privileged code poses significant security risks.

**5. "PostgreSQL 15+ defaults mean all upgraded databases are safe."** No. Audit the ACL of every individual database.

**6. "REVOKE CREATE FROM PUBLIC revokes all direct grants."** No.

**7. "REVOKE ALL on public won't impact applications."** It can revoke `USAGE` and break running code.

**8. "If pg_catalog isn't listed, it isn't searched."** False. It is normally searched implicitly.

**9. "pg_catalog is always searched first regardless of configuration."** False. When explicitly listed, its position in the path takes effect.

**10. "pg_temp is only searched if explicitly named."** False. For relations and types, it may be searched implicitly first.

**11. "pg_temp shadows functions and operators under the same rule as temp tables."** No.

**12. "SECURITY DEFINER functions don't need SET search_path."** Very risky whenever unqualified references and untrusted schemas exist.

**13. "SECURITY DEFINER means a function is automatically safe."** No. It widens risk surface via the owner's privileges.

**14. "Setting search_path eliminates the need for qualified names."** False. Qualification reduces lookup ambiguity and simplifies auditing.

**15. "Putting pg_temp before trusted schemas is a safe default."** No; temporary relations or types can shadow trusted objects.

**16. "Functions with different signatures have no overloading risk."** False. Function resolution evaluates argument types, casts, variadics, and defaults.

**17. "PreparedStatements prevent object hijacking."** No. Parameter binding does not lock down object name resolution.

**18. "current_setting('search_path') always equals the resolved path."** No. Implicit schemas, non-existent entries, and inaccessible schemas create differences.

**19. "current_schema() is always public."** No; it depends on the path and accessible schemas.

**20. "Listing a schema in search_path automatically grants USAGE to the role."** No.

**21. "SET LOCAL preserves the path after COMMIT on a pooled connection."** No; it is transaction-scoped.

**22. "Session SET automatically resets when a connection returns to the pool."** Not guaranteed; depends on pool configuration and reset commands.

**23. "Separate tenant schemas guarantee isolation even if everyone has CREATE."** No. Proper grants, authorization, RLS, and namespace control are required.

**24. "Code without SQL string concatenation has no object-name risk."** False. `search_path` and overloading risks still exist.

**25. "Changing a function owner to superuser fixes permission errors safely."** On the contrary, it maximizes damage if a bug exists.

**26. "Every SECURITY DEFINER routine should have PUBLIC EXECUTE."** No. Apply least-privilege grants.

**27. "Creating a function and revoking PUBLIC the next day leaves no gap."** False. Perform both in the same transaction.

**28. "ALTER DEFAULT PRIVILEGES revokes CREATE on schema public."** No.

**29. "REVOKE CREATE removes objects already placed in public earlier."** No.

**30. "ALTER ROLE SET search_path immediately updates existing pooled sessions."** Do not assume that.

**31. "Existing views re-resolve all tables against the caller's path on every SELECT."** Generally false; views store parsed definitions and object OID dependencies.

**32. "Routine bodies always bind all names once at CREATE time regardless of language."** False. Understand body/language/plan semantics and pin namespaces explicitly.

**33. "format('%I', input) guarantees the caller is authorized for any schema."** No. It only quotes identifiers.

**34. "Schema-qualified SQL names bypass GRANT/REVOKE."** No. Privilege checks still apply.

**35. "Enabling RLS on base tables automatically makes every SECURITY DEFINER function tenant-safe."** No. Owner privileges and RLS bypass must be reviewed.

**36. "Testing as the database owner represents all roles."** No. Runtime role privileges differ.

**37. "Installing an extension into any schema is equally safe."** No. Target schema, owner, and extension scripts affect the trust boundary.

**38. "Having CREATE on public is merely cosmetic."** No. With privileged unqualified lookups, it can become a security flaw.

**39. "Legacy databases need no audit once the server version is upgraded."** False. Old ACLs and objects remain.

**40. "A good app runtime search_path automatically secures SECURITY DEFINER paths."** No. Each privileged routine needs its own locked-down path.

---

## 29. Practice Exercises and Answers

### Exercise 1 — What Is search_path For?

**Question:** Why can `SELECT * FROM sample_items` return different rows when `search_path` changes?

**Answer:** Because unqualified names are resolved across accessible schemas in search path order. When two schemas both contain `sample_items`, which schema gets selected determines the result.

### Exercise 2 — Qualified Name

**Task:** Read the trusted table regardless of session search path.

```sql
SELECT *
FROM sp_sec_lab_private.sample_items;
```

### Exercise 3 — SHOW and current_schemas

```sql
SHOW search_path;
SELECT current_schema(), current_schemas(true);
```

**Answer:** `SHOW` displays the configured setting string, `current_schema` returns the current creation target schema, and `current_schemas(true)` lists resolved schemas including implicit ones.

### Exercise 4 — public and PUBLIC

**Question:** In `REVOKE CREATE ON SCHEMA public FROM PUBLIC`, do the two words mean the same thing?

**Answer:** No. One is the schema name; the other is the pseudo-role matching all roles.

### Exercise 5 — USAGE vs CREATE

**Question:** Can a role with only `USAGE` on `public` execute `CREATE TABLE public.x`?

**Answer:** Not from `USAGE` alone. Effective `CREATE` privilege (or ownership/superuser privileges) is required.

### Exercise 6 — PostgreSQL 15 Defaults

**Question:** What default improvement for `public` was introduced for newly created databases in PostgreSQL 15?

**Answer:** `CREATE` on `public` is no longer granted to `PUBLIC` by default, and `public` is typically owned by `pg_database_owner`.

### Exercise 7 — Upgraded Databases

**Question:** On a PostgreSQL 16 server, is `PUBLIC` guaranteed to lack `CREATE` on `public`?

**Answer:** No. Upgraded or customized databases may retain legacy ACLs; audit the actual ACL.

### Exercise 8 — Checking CREATE

```sql
SELECT has_schema_privilege('public', 'CREATE');
```

**Answer:** Checks the effective `CREATE` privilege of `current_user` on `public`; it does not by itself prove the privilege was granted to `PUBLIC`.

### Exercise 9 — Direct Grants

**Question:** Does `REVOKE CREATE ... FROM PUBLIC` remove a `CREATE` grant assigned directly to role `app_deployer`?

**Answer:** No, it leaves direct grants intact; audit and handle every privilege source individually.

### Exercise 10 — Implicit pg_catalog

**Question:** If `SHOW search_path` outputs `"$user", public`, does PostgreSQL ignore `pg_catalog`?

**Answer:** No. `pg_catalog` is normally searched implicitly ahead of path schemas when not explicitly listed.

### Exercise 11 — Explicit pg_catalog

**Question:** Why is `SET search_path = untrusted, pg_catalog` dangerous?

**Answer:** When `pg_catalog` is listed explicitly after an untrusted schema, certain names can resolve with unintended priority; privileged code must never trust an untrusted schema earlier in the path.

### Exercise 12 — pg_temp

**Question:** When `pg_temp` is omitted from the path, which object classes can be shadowed by the temporary schema?

**Answer:** Relations and data types under special lookup priority rules. Functions and operators are not searched in the temporary schema the way tables are.

### Exercise 13 — Secure Path

```sql
SET search_path = pg_catalog, sp_sec_lab_private, pg_temp;
```

**Answer:** Places built-ins first, the trusted schema next, and the temporary schema last; also requires ensuring no untrusted role holds `CREATE` on the trusted schema.

### Exercise 14 — SECURITY DEFINER

**Question:** Whose privileges does a `SECURITY DEFINER` function run under?

**Answer:** The function owner's privileges under PostgreSQL rules, not simply the caller's privileges as in `SECURITY INVOKER`.

### Exercise 15 — Function-Level Path

**Task:** Write the namespace-hardening attributes for a privileged function.

```sql
SECURITY DEFINER
SET search_path = pg_catalog, sp_sec_lab_private, pg_temp
```

### Exercise 16 — Why Schema-Qualify Tables?

**Answer:** `FROM sp_sec_lab_private.accounts` pins the intended namespace and reduces exposure to caller search path changes.

### Exercise 17 — Dynamic SQL

**Question:** Does using `format('%I.%I',schema,table)` make every caller-chosen object safe to access?

**Answer:** No. It only quotes identifiers; allowlists and authorization checks are still required.

### Exercise 18 — PUBLIC EXECUTE

**Question:** Why run `REVOKE EXECUTE ... FROM PUBLIC` immediately after creating a privileged function in the same transaction?

**Answer:** To eliminate any window where unintended roles could invoke the new routine, ensuring it becomes visible only with proper permissions already applied.

### Exercise 19 — Connection Pool

**Scenario:** Request A runs `SET search_path=tenant_a` and returns the session to the pool. Request B reuses that session.

**Answer:** Without session state reset by the pool, Request B may inherit Request A's path. Use consistent startup/reset hooks and transaction-local settings per contract, never relying on `search_path` for tenant authorization.

### Exercise 20 — SQL Injection vs Object Hijacking

**Answer:** Prepared statements secure data parameterization, but do not stop unqualified object names from resolving to objects in untrusted schemas.

### Exercise 21 — Creation Target

**Task:** Inspect the default schema where unqualified CREATE creates objects.

```sql
SELECT current_schema();
```

### Exercise 22 — Existing Views

**Question:** When a caller changes `search_path`, do existing views automatically re-point their relation references to newly shadowed tables of the same name?

**Answer:** No; views store parsed query trees and dependencies on the object OIDs resolved when defined.

### Exercise 23 — RLS

**Question:** Can `SECURITY DEFINER` affect RLS behavior?

**Answer:** Yes; execution role/owner privileges and RLS bypass rules must be reviewed explicitly alongside tenant policies.

### Exercise 24 — Choosing an Owner

**Question:** Should a privileged function always be owned by a superuser just to make it work?

**Answer:** No unless strictly required. Use a least-privilege owner to limit the impact of any flaw inside the function.

### Exercise 25 — Auditing Functions

```sql
SELECT
    p.oid::regprocedure,
    p.prosecdef,
    p.proconfig
FROM pg_proc AS p
WHERE p.prosecdef;
```

**Answer:** Finds `SECURITY DEFINER` routines and their function-local configuration to evaluate `search_path`; do not treat `proconfig IS NULL` as automatic proof of exploitability.

### Exercise 26 — Auditing Roles

```sql
SELECT
    rolname,
    has_schema_privilege(oid, 'public', 'CREATE')
        AS can_create_public
FROM pg_roles
WHERE rolcanlogin;
```

**Answer:** Lists login roles holding effective `CREATE` privilege on `public` in the connected database.

### Exercise 27 — REVOKE CREATE

**Question:** What is the effect of `REVOKE CREATE ON SCHEMA public FROM PUBLIC`?

**Answer:** It revokes the blanket `CREATE` grant given to all roles on `public`, without dropping the schema or deleting existing objects.

### Exercise 28 — Moving Objects

**Question:** Can you simply script `ALTER ... SET SCHEMA` across every object in `public` without analyzing code?

**Answer:** No. You must evaluate dependencies, code references, extension ownership, grants, and migrations.

### Exercise 29 — Functions in pg_temp

**Question:** Can you create a function in `pg_temp` and rely on it shadowing regular functions on unqualified calls?

**Answer:** Not under the special lookup priority applied to temp relations/types; PostgreSQL does not search the temporary schema for functions and operators in that manner.

### Exercise 30 — Security Audit Rollout

**Task:** List at least four checks required before declaring a database hardened against `search_path` risks.

**Answer:** (1) ACLs/owners and effective `CREATE` on `public` and trusted schemas; (2) `SECURITY DEFINER` routines pinned with safe paths and qualified names; (3) `EXECUTE`/`USAGE` grants scoped strictly to intended roles; (4) practical tests covering altered caller paths, temporary table shadowing, and connection pool reuse. Also inspect RLS, extensions, migrations, and legacy object inventories.

---

## 30. Security Checklist for search_path and the public Schema

### Namespace Design

1. Know which schema every table, function, and type resides in.
2. Use schema-qualified names for critical objects.
3. Never treat `public` as inherently safe.
4. Distinguish the `public` schema from the `PUBLIC` pseudo-role.
5. Determine which schemas are **trusted** based on actual `CREATE` privileges.
6. Never include a schema allowing untrusted `CREATE` in the search path of privileged code.

### Roles and Grants

7. Inspect both the PostgreSQL version **and** the actual ACL of every database.
8. Audit `has_schema_privilege(...,'CREATE')` for all runtime roles.
9. Revoke blanket `CREATE` on `public` when policy requires it.
10. Never run `REVOKE ALL` without assessing `USAGE` impact.
11. Avoid making runtime roles schema owners or superusers unnecessarily.
12. Review direct grants, role memberships, and owner privileges.
13. Restrict `EXECUTE` on privileged routines.
14. Revoke accidental `PUBLIC EXECUTE` in the same transaction that creates a privileged routine.

### Search Path Configuration

15. Check both `SHOW search_path` and `current_schemas(true)`.
16. Verify which schema `"$user"` might expand to.
17. Remember `pg_catalog` is searched implicitly and explicit placement affects lookup.
18. Remember `pg_temp` is prioritized specially for relations/types, not functions/operators.
19. Place `pg_temp` last in the search path of `SECURITY DEFINER` functions.
20. Pin trusted function-level `SET search_path` clauses.
21. Never accept arbitrary caller-supplied schemas/paths in privileged code.
22. For dynamic SQL, quote identifiers properly and enforce an allowlist.

### Application and Operations

23. Never use `search_path` as tenant authorization.
24. Review RLS/ownership across `SECURITY DEFINER` call chains.
25. Verify connection pool reset logic or transaction-local path scoping.
26. Use schema-qualified target names in migrations.
27. Review extension installation schemas and owners.
28. Never assume server version upgrades automatically fix legacy ACLs.
29. Audit existing unfamiliar objects before revoking `CREATE`.
30. Test shadowing in harmless lab schemas rather than abusing production access.
31. Audit `pg_proc.prosecdef` and `proconfig`.
32. Verify both schema-level and object-level privileges.
33. Test runtime behavior under real app roles, not solely DBA roles.
34. Plan hardening rollouts with staging validation, rollback, and observability.
35. Require security review whenever adding new privileged routines or schemas.

---

## 31. Summary

`search_path` is a convenient name-resolution mechanism, not merely cosmetic configuration. **Any schema present in the search path of privileged code must be treated as part of your trust boundary**, because anyone able to create objects there can influence unqualified references.

Core principles to remember:

- **Schema `public`** is a namespace; **`PUBLIC`** in GRANT/REVOKE denotes the set of all roles.
- **`USAGE`** and **`CREATE`** on a schema are distinct. Holding `CREATE` on a schema in a privileged routine's search path can be dangerous.
- PostgreSQL 15 improved `public` defaults for **new databases**, yet upgraded or customized databases still require auditing actual privileges.
- When `pg_catalog` is unlisted, PostgreSQL typically searches it implicitly first; when explicitly listed, its position in the path matters.
- `pg_temp` receives special priority for **tables and data types** when unlisted. Always put `pg_temp` last in privileged routines' paths.
- `SECURITY DEFINER` routines need a **function-level trusted search_path**, schema-qualified names, least-privilege owners, and minimal `EXECUTE` grants.
- Function/operator overloading, extension objects, dynamic SQL, migrations, and connection pooling all introduce nuances beyond basic table lookups.
- **Prepared statements do not replace namespace hardening**, and `search_path` does not replace authentication, authorization, or RLS.
- Production hardening begins with inventory and ACL audits, followed by controlled rollout and testing under real runtime roles.

**Self-assessment question:** Given a `SECURITY DEFINER` function created by a privileged owner, if the caller alters `search_path` and a schema on that path permits untrusted `CREATE`, can you guarantee the function calls the exact table and helper its author intended? If you cannot prove this through **schema qualification, function-level search_path, and proper grants**, that represents a risk you must resolve before promoting the function to production.

### Official PostgreSQL Documentation

- [Schemas — search_path and Schema Usage](https://www.postgresql.org/docs/current/ddl-schemas.html).
- [Schemas — The Public Schema](https://www.postgresql.org/docs/current/ddl-schemas.html#DDL-SCHEMAS-PUBLIC).
- [Schemas — The Schema Search Path](https://www.postgresql.org/docs/current/ddl-schemas.html#DDL-SCHEMAS-PATH).
- [Function Security — SECURITY DEFINER](https://www.postgresql.org/docs/current/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY).
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html).
- [Function Type Resolution](https://www.postgresql.org/docs/current/typeconv-func.html).
- [Operator Type Resolution](https://www.postgresql.org/docs/current/typeconv-oper.html).
- [GRANT](https://www.postgresql.org/docs/current/sql-grant.html).
- [REVOKE](https://www.postgresql.org/docs/current/sql-revoke.html).
- [ALTER ROLE](https://www.postgresql.org/docs/current/sql-alterrole.html).
- [SET](https://www.postgresql.org/docs/current/sql-set.html).
- [SET LOCAL](https://www.postgresql.org/docs/current/sql-set.html).
- [Runtime Configuration — Client Connection Defaults (search_path)](https://www.postgresql.org/docs/current/runtime-config-client.html).
- [System Information Functions — current_schema/current_schemas](https://www.postgresql.org/docs/current/functions-info.html).
- [Privilege Inquiry Functions — has_schema_privilege](https://www.postgresql.org/docs/current/functions-info.html#FUNCTIONS-INFO-ACCESS-TABLE).
- [pg_namespace](https://www.postgresql.org/docs/current/catalog-pg-namespace.html).
- [pg_proc](https://www.postgresql.org/docs/current/catalog-pg-proc.html).
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).
