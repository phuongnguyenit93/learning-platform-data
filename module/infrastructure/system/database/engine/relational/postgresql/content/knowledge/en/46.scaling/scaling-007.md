# Additional Procedural Languages and Execution Privilege Risks in PostgreSQL

PostgreSQL can execute logic inside the database using SQL functions, procedures, triggers, and procedural languages such as PL/pgSQL, PL/Python, PL/Perl, or PL/Tcl. These languages expand data-processing capabilities, business automation, and system integration. However, a function is not merely a snippet of code stored in the database: it runs under a specific security context, may be invoked by many roles, and in certain cases can access operating system resources.

Major risks often emerge when the privilege to create functions, the privilege to use a procedural language, the privilege to call a function, and the privileges of the function owner are conflated into a single concept. PostgreSQL governs these via separate mechanisms. A role may lack permission to create functions yet still be allowed to `EXECUTE` a function created by someone else. A function runs with the caller's privileges by default, whereas a function declared `SECURITY DEFINER` runs with the owner's privileges. A function using dynamic SQL or an unsafe `search_path` can open the door to SQL injection or object-shadowing attacks.

This lesson belongs to the **Scaling** chapter and focuses on:

- Distinguishing SQL language, PL/pgSQL, and additional procedural languages.
- Understanding trusted vs. untrusted languages and the limits of language sandboxes.
- Installing, upgrading, and removing procedural language extensions.
- Separating database, schema, language, and function privileges.
- Understanding default `EXECUTE` for `PUBLIC` and how to restrict routine invocation privileges.
- Distinguishing `SECURITY INVOKER` from `SECURITY DEFINER`.
- Preventing `search_path` hijacking, temporary-schema shadowing, and SQL injection.
- Designing dynamic SQL with identifier quoting and parameter binding.
- Mitigating risks from C functions, untrusted languages, and extension installation.
- Inspecting RLS, ownership, function configuration, volatility, and parallel properties.
- Auditing language/function privileges, routine owners, and `SECURITY DEFINER` code.
- Building a least-privilege model, deployment checklist, and incident runbook.

> **Security principle:** Permission to create a function, permission to call a function, and permissions used by the function while running are three separate questions. Never grant broad `EXECUTE` on sensitive functions, never use `SECURITY DEFINER` unless privilege elevation is required, and never allow untrusted roles `CREATE` privilege on schemas appearing in a privileged function's `search_path`.

## 1. Language Categories in PostgreSQL

PostgreSQL supports multiple ways to define routines. A routine can use SQL, PL/pgSQL, or an additionally installed procedural language.

### 1.1. SQL Language

SQL functions use SQL statements/expressions to define behavior:

```sql
CREATE FUNCTION app.order_total(p_order_id bigint)
RETURNS numeric
LANGUAGE SQL
STABLE
AS $function$
    SELECT COALESCE(sum(oi.quantity * oi.unit_price), 0)
    FROM app.order_items AS oi
    WHERE oi.order_id = p_order_id;
$function$;
```

The SQL language fits well when logic is primarily an expression or query. It can declare function properties such as volatility, strictness, parallel safety, and security mode.

### 1.2. PL/pgSQL

PL/pgSQL is a procedural language tightly integrated with PostgreSQL. It supports variables, control flow, loops, exceptions, cursors, and dynamic SQL.

```sql
CREATE FUNCTION app.calculate_discount(p_amount numeric)
RETURNS numeric
LANGUAGE plpgsql
IMMUTABLE
AS $function$
BEGIN
    IF p_amount < 0 THEN
        RAISE EXCEPTION 'amount must be nonnegative';
    END IF;

    IF p_amount >= 1000 THEN
        RETURN p_amount * 0.10;
    END IF;

    RETURN 0;
END;
$function$;
```

PL/pgSQL suits business logic requiring multi-step SQL and control flow. It still executes inside the PostgreSQL backend process and remains subject to database transaction and privilege rules.

### 1.3. Additional Procedural Languages

Common languages:

| Language | Example extension/language name | Purpose |
| --- | --- | --- |
| PL/pgSQL | `plpgsql` | Procedural logic tightly bound to SQL |
| PL/Python | `plpython3u` | Using Python inside routines |
| PL/Perl | `plperl`, `plperlu` | Using Perl inside routines |
| PL/Tcl | `pltcl`, `pltclu` | Using Tcl inside routines |
| PL/Java | Third-party extension | Using Java inside the database |
| PL/R | Third-party extension | Statistical analysis with R |
| PL/V8 | Third-party extension | Using JavaScript/V8 inside the database |
| C | `LANGUAGE C` | Invoking native shared libraries |

Exact names, versions, trusted status, and packaging depend on the PostgreSQL build, OS packages, and installed extensions. Not every language is available in every managed database service.

### 1.4. A Language Is Not Identical to an Extension

Procedural languages are typically packaged and managed via extensions. Some languages can be registered with the older `CREATE LANGUAGE` command, though modern management prefers `CREATE EXTENSION`.

An extension may contain:

- A language handler.
- An inline handler for anonymous code blocks.
- A validator checking function bodies.
- Supporting functions/types/operators.
- A control file and SQL installation scripts.
- Shared libraries loaded by PostgreSQL.

A language may be just one piece of a larger extension. Removing the extension can affect other objects owned by that extension.

### 1.5. A Language Is Not a Separate Process

Procedural functions generally run inside the backend process serving the session. They do not automatically run in an isolated sandbox process. Consequently, a native-code bug or runaway function can affect the backend and server resources.

Some extensions may launch or communicate with external runtimes, yet you should never assume all procedural languages are OS-isolated.

## 2. Trusted and Untrusted Procedural Languages

PostgreSQL classifies procedural languages using a `trusted` attribute. This attribute indicates how strictly the language handler restricts what code written in that language can do.

### 2.1. Trusted Languages

A trusted language is designed to allow users with appropriate privileges to create functions without requiring superuser status. The handler must restrict dangerous operations per the language contract.

PL/pgSQL is a trusted language. PL/Perl has the trusted variant `plperl`. PL/Tcl has the trusted variant `pltcl`.

Trusted does not mean code is always safe. A function can still:

- Read or modify data the caller can access.
- Invoke other functions.
- Run resource-intensive queries.
- Cause lock contention.
- Introduce business logic flaws.
- Execute with owner privileges if declared `SECURITY DEFINER`.
- Be exploited via SQL injection or broken authorization logic.

Trusted speaks only to language-level restrictions, not a security review for every function.

### 2.2. Untrusted Languages

Untrusted languages do not provide a sandbox strong enough to let ordinary users author code. Creating functions in these languages is typically restricted to superusers.

Examples:

- `plpython3u` is untrusted PL/Python.
- `plperlu` is untrusted PL/Perl.
- `pltclu` is untrusted PL/Tcl.
- C language is a native-code interface not treated as a trusted sandbox.

Untrusted code may access the filesystem, processes, network, or runtime APIs with the privileges of the OS account running PostgreSQL. In many deployments, the server process runs under the PostgreSQL service OS account, commonly the `postgres` user.

### 2.3. Superuser-Only Creation Does Not Mean Callers Must Be Superusers

A superuser can create a function in an untrusted language and grant `EXECUTE` to another role. When that role calls the function, the function body still executes.

This is especially dangerous if the function can perform OS-level actions. Treat `EXECUTE` on untrusted-language functions as granting access to a privileged capability, not merely calling an ordinary stored query.

### 2.4. Trusted Languages Do Not Bypass Database Privileges

For example, trusted PL/pgSQL can contain:

```sql
DELETE FROM app.customers;
```

A `SECURITY INVOKER` function succeeds only if the effective user holds `DELETE` privilege on the table. If the function is `SECURITY DEFINER` and its owner holds `DELETE`, a caller can trigger that deletion even without having direct `DELETE` privilege.

Language trust does not alter this rule.

### 2.5. Checking Trusted Status

The `pg_language` catalog stores procedural language metadata:

```sql
SELECT
    l.lanname AS language_name,
    l.lanpltrusted AS is_trusted,
    l.lanispl AS is_procedural,
    l.lanowner::regrole AS owner,
    l.lanacl AS language_acl,
    l.laninline::regproc AS inline_handler,
    l.lanvalidator::regproc AS validator
FROM pg_language AS l
ORDER BY l.lanname;
```

Certain system languages have specialized catalog metadata. Do not assume every field or handler carries uniform values.

### 2.6. Trusted Language Is Not the Extension Trusted Flag

There are two distinct concepts:

- `pg_language.lanpltrusted`: whether the language handler is marked trusted.
- The `trusted` attribute in an extension control file: whether PostgreSQL permits non-superusers to install that extension via supported mechanisms.

A procedural language may be trusted while the extension installing it still has separate installation requirements. Conversely, a trusted extension does not make all function code inside it safe.

## 3. Installing Procedural Language Extensions

Before creating functions, the language handler and shared libraries must exist on the server.

### 3.1. Check Available Languages

```sql
SELECT
    lanname,
    lanpltrusted,
    lanispl
FROM pg_language
ORDER BY lanname;
```

If PL/pgSQL is already installed by default in the database, no reinstall is required. Other languages may need separate OS or extension packages.

### 3.2. Installing PL/Python

On a server with the compatible package installed:

```sql
CREATE EXTENSION plpython3u;
```

The extension must be present on the host and built for the running PostgreSQL major version. On managed services, installation may be governed by provider allowlists or parameter/configuration settings.

`plpython3u` is untrusted. Only superusers or equivalent administrative mechanisms may create functions in this language.

### 3.3. Installing PL/Perl

The extension name is typically `plperl`, though the language may offer both trusted and untrusted variants:

```sql
CREATE EXTENSION plperl;
```

Inspect catalogs after installation to verify language names and trusted flags. Never infer trusted status purely from package names.

### 3.4. CREATE LANGUAGE vs. CREATE EXTENSION

In modern PostgreSQL versions, manage procedural languages using extension commands whenever an extension provides the language.

```sql
CREATE EXTENSION IF NOT EXISTS plpgsql;
```

`IF NOT EXISTS` only avoids errors if an extension with that name already exists. It does not prove version, schema, or objects are in the expected state. Inspect `pg_extension` and the extension version.

### 3.5. Extension Installation Privileges

Non-trusted extensions typically require superuser. Extensions with `trusted = true` in their control file may allow non-superusers with `CREATE` privilege on the database to install them, per PostgreSQL rules.

Not every extension is marked trusted. Inspect control files, installation scripts, and extension documentation before granting broad database `CREATE` privileges.

### 3.6. Extension Scripts Are Executable Code

When installing or upgrading an extension, PostgreSQL executes the extension's SQL scripts. Scripts can create functions, types, operators, casts, views, and other objects.

For extensions with native libraries, code can be loaded into the server process. Only install extensions from trusted sources, and verify versions, package provenance, and compatibility.

### 3.7. Upgrading Extensions

```sql
ALTER EXTENSION plpython3u UPDATE;
```

The exact command depends on whether the extension provides an update path from the current version. Inspect:

```sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS extension_schema,
    extowner::regrole AS owner
FROM pg_extension
ORDER BY extname;
```

Never swap shared libraries on the host while databases remain on an older version without a deployment and compatibility plan.

### 3.8. Removing Extensions

```sql
DROP EXTENSION plpython3u RESTRICT;
```

`RESTRICT` refuses the drop if dependent objects exist. `CASCADE` can drop objects across the dependency tree. Before removing a language extension, inventory functions using that language and evaluate dependent applications and objects.

## 4. Privileges Required to Create and Call Routines

PostgreSQL separates multiple privilege layers. A developer might need permission to create functions in a schema without needing permission to install languages or extensions.

### 4.1. Database CREATE

To create a new schema, a role needs `CREATE` privilege on the database. However, to create a function inside an existing schema, a role generally needs `CREATE` privilege on that schema and `USAGE` on the language.

Never grant `CREATE` on the database merely to let a developer add a function to an existing schema.

### 4.2. Schema USAGE and CREATE

- `USAGE` allows resolving/accessing objects in the schema subject to object privileges.
- `CREATE` allows creating new objects in the schema.

Example:

```sql
GRANT USAGE ON SCHEMA app TO app_runtime;
GRANT USAGE, CREATE ON SCHEMA app_dev TO app_developer;
```

Runtime roles typically need only `USAGE`, not `CREATE`. Developer or migration roles can be granted `CREATE` on controlled schemas.

### 4.3. Language USAGE

To create a function in a trusted procedural language, a role needs `USAGE` privilege on the language and `CREATE` privilege on the target schema.

```sql
GRANT USAGE ON LANGUAGE plpgsql TO app_developer;
```

For untrusted languages, the superuser restriction still applies regardless of language ACLs.

### 4.4. Function EXECUTE

Permission to invoke a function is managed separately:

```sql
GRANT EXECUTE
ON FUNCTION app.calculate_discount(numeric)
TO app_runtime;
```

Function overloads are distinguished by argument types. Grant permissions on the exact signature rather than relying on the bare function name.

### 4.5. Procedure EXECUTE

Procedures are invoked with `CALL` and likewise have an `EXECUTE` privilege:

```sql
GRANT EXECUTE
ON PROCEDURE app.rebuild_summary(date)
TO batch_runner;
```

Functions and procedures differ in invocation syntax, return behavior, and transaction control. Specify the matching object kind when granting or revoking.

### 4.6. Execution Privilege Is Not Ownership

A role with `EXECUTE` cannot automatically `ALTER` or `DROP` a function. Only the owner or an appropriately privileged role can administer the object. Avoid using owner roles as application runtime identities.

### 4.7. Four Questions When Reviewing Privileges

For every routine, determine:

1. Who is permitted to create code in this language?
2. Who owns the function/procedure after creation?
3. Who is permitted to invoke the routine?
4. Does the routine run with caller or owner privileges?

Unless each question has a separate answer, the privilege model is not yet clear enough.

## 5. Default Privileges on Functions

By default, PostgreSQL grants `EXECUTE` on newly created functions and procedures to `PUBLIC`. `PUBLIC` is a pseudo-role representing all database roles.

### 5.1. Risks of Default EXECUTE

If a new function performs sensitive behavior and a developer forgets to revoke `EXECUTE`, any role may be able to invoke it depending on schema visibility and other conditions.

Risk increases when the function:

- Runs as `SECURITY DEFINER`.
- Reads sensitive data.
- Writes data with higher privileges than the caller.
- Calls untrusted-language code.
- Performs administrative actions.
- Uses dynamic SQL driven by caller input.

### 5.2. Revoking PUBLIC Privileges on Existing Functions

```sql
REVOKE EXECUTE
ON ALL FUNCTIONS IN SCHEMA app
FROM PUBLIC;
```

This command affects all functions in the specified schema. Before running it, inventory callers and grants to avoid breaking applications.

If procedures must also be handled, use routine syntax appropriate for your PostgreSQL version or revoke per procedure signature.

### 5.3. Default Privileges for New Functions

Set default privileges for the role that creates routines:

```sql
ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
```

Default privileges apply only to objects created by the specified role within the corresponding scope. If multiple owner roles create functions, configure defaults for each creator role.

### 5.4. Granting to Runtime Roles

After revoking `PUBLIC`, grant permissions explicitly:

```sql
GRANT EXECUTE
ON FUNCTION app.calculate_discount(numeric)
TO app_runtime;
```

Use group roles to manage permissions by application capability rather than granting directly to numerous login roles.

### 5.5. Checking Effective Privileges

```sql
SELECT
    has_function_privilege(
        'app_runtime',
        'app.calculate_discount(numeric)',
        'EXECUTE'
    ) AS runtime_can_execute;
```

You can also inspect language/schema/database privileges via corresponding helper functions:

```sql
SELECT
    has_language_privilege('app_developer', 'plpgsql', 'USAGE')
        AS can_use_plpgsql,
    has_schema_privilege('app_developer', 'app_dev', 'CREATE')
        AS can_create_in_schema,
    has_database_privilege('app_developer', current_database(), 'CREATE')
        AS can_create_schema;
```

### 5.6. Function ACL Inventory

```sql
SELECT
    n.nspname AS schema_name,
    p.oid::regprocedure AS routine_identity,
    p.proowner::regrole AS owner,
    p.prosecdef AS security_definer,
    p.proacl AS explicit_acl
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'app'
ORDER BY p.oid::regprocedure::text;
```

`proacl` can be `NULL` when an object relies on default ACL behavior. `NULL` does not mean nobody has access. Use privilege helper functions or expand ACLs with `acldefault`/`aclexplode` when an exact audit is needed.

## 6. SECURITY INVOKER vs. SECURITY DEFINER

This is the single most important distinction when evaluating a function's execution context.

### 6.1. SECURITY INVOKER

By default, a function runs with the privileges of the user who calls it:

```sql
CREATE FUNCTION app.get_my_orders()
RETURNS SETOF app.orders
LANGUAGE sql
SECURITY INVOKER
AS $function$
    SELECT *
    FROM app.orders
    WHERE customer_id = current_user_id();
$function$;
```

The caller needs the privileges required to execute the underlying statements. This is usually the safest choice for functions that do not need privilege elevation.

### 6.2. SECURITY DEFINER

A function declared `SECURITY DEFINER` executes with the privileges of the function owner:

```sql
CREATE FUNCTION app_private.close_expired_orders()
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
AS $function$
DECLARE
    affected_rows integer;
BEGIN
    UPDATE app.orders
    SET status = 'expired'
    WHERE status = 'pending'
      AND expires_at < clock_timestamp();

    GET DIAGNOSTICS affected_rows = ROW_COUNT;
    RETURN affected_rows;
END;
$function$;
```

If the owner has `UPDATE` privilege on the table, a caller can trigger that `UPDATE` without holding direct `UPDATE` privilege.

This is a capability boundary. The function body must strictly limit actions, inputs, and affected rows.

### 6.3. SECURITY DEFINER Is Not Automatically Safe Once Caller Has EXECUTE

When `EXECUTE` is granted to a caller, the caller can supply arguments and trigger code running under the owner's privileges. If the function accepts a table name, SQL fragment, or role name as input, an attacker can turn it into a confused deputy.

Expose only operations with narrow contracts, strict validation, and no arbitrary caller control over SQL.

### 6.4. Use a Dedicated Owner Role

A `SECURITY DEFINER` function should not be owned by a superuser if it only needs access to a few tables.

Create a `NOLOGIN` owner role:

```sql
CREATE ROLE app_function_owner NOLOGIN;
GRANT USAGE ON SCHEMA app_private TO app_function_owner;
GRANT UPDATE ON app.orders TO app_function_owner;
```

Transfer ownership:

```sql
ALTER FUNCTION app_private.close_expired_orders()
OWNER TO app_function_owner;
```

The owner role receives only necessary privileges. Never grant this role to application login roles or unnecessary developer roles.

### 6.5. Owners Should Not Hold Excess Privileges

Avoid:

- `SUPERUSER`.
- `CREATEROLE`.
- `CREATEDB`.
- `BYPASSRLS`.
- Write privileges across all schemas.
- Membership in broad administrative roles.

If a function needs to read/write one table, grant privileges solely on that table. If it needs a sequence, schema, or type, grant only those exact privileges.

## 7. Search Path and Object-Shadowing Attacks

`search_path` determines the order in which PostgreSQL resolves unqualified object names. A `SECURITY DEFINER` function can be tricked if an attacker creates a similarly named object in a schema searched before the trusted object.

### 7.1. Dangerous Example

Suppose a function contains an unqualified function call:

```sql
CREATE FUNCTION app_private.transfer_credit(
    p_from bigint,
    p_to bigint,
    p_amount numeric
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $function$
BEGIN
    PERFORM validate_transfer(p_from, p_to, p_amount);

    UPDATE app.accounts
    SET balance = balance - p_amount
    WHERE id = p_from;
END;
$function$;
```

If an attacker holds `CREATE` privilege in a schema appearing ahead of the real function's schema, they can create a function or operator with the same name so it resolves instead via `search_path`.

The privileged function may unwittingly execute attacker-controlled code.

### 7.2. Pin search_path on the Function

One defense is setting a function-local `search_path` containing only trusted schemas, with `pg_temp` placed last:

```sql
CREATE FUNCTION app_private.safe_transfer(
    p_from bigint,
    p_to bigint,
    p_amount numeric
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app_private, app, pg_temp
AS $function$
BEGIN
    PERFORM app_private.validate_transfer(
        p_from,
        p_to,
        p_amount
    );

    UPDATE app.accounts
    SET balance = balance - p_amount
    WHERE id = p_from;
END;
$function$;
```

`pg_catalog` is explicitly placed first. The `app_private` and `app` schemas are safe only if untrusted roles cannot `CREATE`/`REPLACE` objects inside them. `pg_temp` is placed last so temporary objects cannot take precedence over trusted objects.

Select the schema list per routine. Never include schemas writable by application users.

### 7.3. Schema-Qualify Object Names

Inside privileged functions, prefer:

```sql
UPDATE app.accounts
SET balance = balance - p_amount
WHERE id = p_from;
```

over:

```sql
UPDATE accounts
SET balance = balance - p_amount
WHERE id = p_from;
```

Schema qualification reduces `search_path` reliance. For built-in functions, keep `pg_catalog` first in the path or qualify sensitive calls when appropriate.

### 7.4. Temporary Schemas

PostgreSQL assigns a temporary schema per session. If `pg_temp` is not explicitly placed last in a `SECURITY DEFINER` function's `search_path`, temporary objects can take precedence when resolving relation or type names per search-path rules.

Do not assume an attacker needs `CREATE` on the `app` schema to shadow an object; temporary objects must also be accounted for.

### 7.5. Schema CREATE Privileges

Check who can create objects in schemas referenced by privileged functions:

```sql
SELECT
    n.nspname AS schema_name,
    pg_get_userbyid(n.nspowner) AS owner,
    has_schema_privilege(
        'app_runtime',
        n.oid,
        'CREATE'
    ) AS runtime_can_create,
    has_schema_privilege(
        'app_runtime',
        n.oid,
        'USAGE'
    ) AS runtime_can_use
FROM pg_namespace AS n
WHERE n.nspname IN ('public', 'app', 'app_private')
ORDER BY n.nspname;
```

Never assume `PUBLIC` always has—or lacks—`CREATE` on the `public` schema. Defaults have changed across PostgreSQL versions and upgrade histories; inspect the actual ACLs.

### 7.6. Protecting the public Schema

When policy requires it, revoke `CREATE` from `PUBLIC`:

```sql
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
```

Check whether extension installers, migration tools, or applications depend on `CREATE` in `public` before applying this change.

## 8. SQL Injection in Procedural Functions

PL/pgSQL allows constructing and executing dynamic SQL. Concatenating untrusted input into an SQL string exposes the function to SQL injection.

### 8.1. Direct String Concatenation Is Dangerous

Unsafe example:

```sql
EXECUTE 'SELECT * FROM app.customers WHERE email = '''
    || p_email
    || '''';
```

Input containing quotes or SQL fragments can alter the statement's meaning.

### 8.2. Use USING for Values

Safe handling for data values:

```sql
EXECUTE
    'SELECT id FROM app.customers WHERE email = $1'
INTO customer_id
USING p_email;
```

`USING` bind parameters separate values from SQL syntax. Manual quote escaping is unnecessary.

### 8.3. Use format('%I') for Identifiers

Identifiers such as schema, table, and column names cannot be passed as bind parameters. Use identifier quoting:

```sql
EXECUTE format(
    'SELECT count(*) FROM %I.%I WHERE status = $1',
    p_schema,
    p_table
)
INTO row_count
USING p_status;
```

`%I` safely quotes identifiers. `%L` quotes literals, though for values prefer `USING` parameters.

### 8.4. Quoting Does Not Replace Allowlists

If a caller can ask a function to query any table, `format('%I')` only prevents breaking SQL syntax; it does not stop the caller from accessing out-of-scope objects.

Enforce an allowlist:

```sql
IF p_table NOT IN ('orders', 'order_items') THEN
    RAISE EXCEPTION 'table is not allowed';
END IF;
```

Schema/table allowlists must be controlled by code, not read from tables modifiable by callers.

### 8.5. Never Accept Raw WHERE/ORDER BY Fragments

A function taking `p_filter text` and concatenating it into a `WHERE` clause is an arbitrary SQL execution interface. Never expose raw SQL fragments to runtime roles. Replace them with typed parameters, enum choices, or code-constructed predicates.

### 8.6. SQL Injection in Other Languages

PL/Python, PL/Perl, and other procedural languages can also assemble SQL strings. Use language driver/parameter APIs when supported, or invoke SPI parameterized execution per the extension's API.

The rules remain identical: values must be bound, identifiers must be validated/quoted, and execution privileges must be restricted.

## 9. Risks of Untrusted Languages and C Functions

Untrusted languages extend code capabilities beyond the standard database privilege model.

### 9.1. PL/PythonU

PL/PythonU can use Python runtime capabilities such as importing modules, accessing files, or calling OS APIs depending on environment and installed packages.

Example function:

```sql
CREATE FUNCTION admin.read_server_file(p_path text)
RETURNS text
LANGUAGE plpython3u
AS $python$
with open(p_path, "r", encoding="utf-8") as source:
    return source.read()
$python$;
```

This illustrates the risk. If `EXECUTE` is granted broadly, callers can read any file readable by the PostgreSQL OS account. Never deploy such functions as general utilities for application users.

### 9.2. PL/PerlU and PL/TclU

Untrusted variants can access capabilities restricted in trusted variants. Review module loading, filesystem/network calls, and process execution.

### 9.3. C-Language Functions

C functions run native code inside the PostgreSQL backend process. A bug can:

- Crash the backend.
- Corrupt memory.
- Destabilize the server process.
- Bypass SQL-level validation assumptions.
- Access OS resources with the server process's privileges.
- Create severe security vulnerabilities.

Use C functions only from reviewed sources with compatible builds and verified package provenance. Never permit ordinary users to create or replace native code.

### 9.4. OS-Level Permissions Still Apply

Functions execute under the PostgreSQL service's OS account, not the OS account of the calling database role. Database `GRANT` statements do not restrict the OS user's filesystem permissions.

Use OS sandboxing, container/VM isolation, filesystem permissions, and network policies to limit blast radius. The database privilege model is one defense layer, not a substitute for OS security.

### 9.5. EXECUTE on an Untrusted Function Is a Capability

An untrusted function may be created by a superuser while `EXECUTE` is granted to an ordinary role. Before granting permissions, audit every input and constrain what the function can do. Never grant `EXECUTE` to `PUBLIC` or broad runtime roles merely because a function looks like a helper.

## 10. Function Properties Affecting Execution

Functions have several attributes beyond language and security mode. These affect the planner, runtime behavior, and certain security assumptions.

### 10.1. Volatility

| Property | Meaning |
| --- | --- |
| `IMMUTABLE` | Result depends solely on arguments and never changes with database state |
| `STABLE` | Result is consistent within a single statement per PostgreSQL contract |
| `VOLATILE` | May vary across calls, have side effects, or depend on changing state |

Never mark a `VOLATILE` function as `IMMUTABLE` to force planner optimizations. The planner may constant-fold or cache values based on the declared property.

Volatility is not a privilege boundary. An `IMMUTABLE` function can still contain bugs or SQL injection if poorly implemented.

### 10.2. STRICT

`STRICT` (also written `RETURNS NULL ON NULL INPUT`) skips calling the function body whenever any input argument is `NULL`; PostgreSQL immediately returns `NULL`.

Use it when semantically valid for all inputs. Never use `STRICT` as a substitute for validating complex business rules.

### 10.3. PARALLEL Safety

- `PARALLEL SAFE`: function may run inside parallel workers per contract.
- `PARALLEL RESTRICTED`: runs only in the parallel leader.
- `PARALLEL UNSAFE`: cannot execute in parallel queries.

Misdeclaring parallel safety can cause runtime errors or unsafe behavior. Parallel safety is an execution property, not a security sandbox.

### 10.4. LEAKPROOF

`LEAKPROOF` promises that a function reveals no information about its arguments beyond its defined return value, including via side effects or error behavior per planner semantics. Only superusers can mark a function `LEAKPROOF`.

Never mark a function `LEAKPROOF` merely to improve query plans. A function that leaks information can undermine row-level security and security barrier views.

### 10.5. COST and ROWS

`COST` and `ROWS` help the planner estimate function execution cost and cardinality. Misdeclaring them can produce suboptimal plans, though they do not directly alter function privileges.

### 10.6. Per-Function SET Configuration

A function can declare configuration settings applied during execution:

```sql
CREATE FUNCTION app_private.secure_lookup(p_id bigint)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app_private, app, pg_temp
SET statement_timeout = '3s'
AS $function$
BEGIN
    RETURN (
        SELECT customer_name
        FROM app.customers
        WHERE id = p_id
    );
END;
$function$;
```

Function-local settings help constrain the execution environment. Choose settings appropriate for the routine and avoid arbitrary `SET` clauses that break caller semantics.

## 11. Row-Level Security and SECURITY DEFINER

Row-Level Security (RLS) controls which rows a role can view or modify. `SECURITY DEFINER` can alter the effective user and thus policy evaluation.

### 11.1. Table Owners Typically Bypass RLS

Table owners normally bypass row security policies unless `FORCE ROW LEVEL SECURITY` is enabled on the table. Superusers and roles with `BYPASSRLS` also bypass RLS.

If a `SECURITY DEFINER` function is owned by the table owner, the function may access more rows than the caller expects.

### 11.2. Inspecting RLS

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relrowsecurity AS rls_enabled,
    c.relforcerowsecurity AS force_rls
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname = 'app'
ORDER BY c.relname;
```

### 11.3. Policy Evaluation

RLS policies often reference `current_user` or session context. Inside `SECURITY DEFINER`, `current_user` reflects the effective owner during execution, whereas `session_user` remains the original session identity. Choose the identity aligning with your authorization design.

Never rely on `current_user` to identify end users if all requests share one database login.

### 11.4. Designing Functions with RLS

When a function must honor RLS:

- Choose an owner role that does not own the target table when appropriate.
- Do not grant `BYPASSRLS`.
- Consider `FORCE ROW LEVEL SECURITY`.
- Verify policy evaluation under the actual effective user.
- Test using runtime roles, not only superuser.
- Never let callers spoof user identity through unvalidated inputs.

## 12. Triggers, Event Triggers, and Implicit Execution

Functions do not run solely when users call `SELECT` or `CALL`. PostgreSQL can invoke functions implicitly as part of other operations.

### 12.1. Trigger Functions

A trigger function runs when table events occur:

```sql
CREATE FUNCTION app_private.audit_order_change()
RETURNS trigger
LANGUAGE plpgsql
AS $function$
BEGIN
    INSERT INTO audit.order_changes (
        order_id,
        changed_at,
        operation
    )
    VALUES (
        NEW.id,
        clock_timestamp(),
        TG_OP
    );

    RETURN NEW;
END;
$function$;
```

When creating a trigger, the function must satisfy the trigger-function contract. If a trigger function is `SECURITY DEFINER`, any matching DML event triggers execution under the owner's privileges.

### 12.2. Event Triggers

Event triggers run when DDL events occur. They have broad impact because a DDL statement automatically triggers custom code.

Only trusted administrative roles should manage event triggers. Audit function bodies, owners, `search_path`, and handled event tags.

### 12.3. Functions in Expressions

Functions can be invoked through:

- `DEFAULT` expressions.
- `CHECK` constraints.
- Generated columns.
- Index expressions.
- Views.
- RLS policies.
- Operators and casts.
- Triggers.
- Rules.

A function may execute during a query even when application code does not mention the function name explicitly. When auditing `EXECUTE` grants and security contexts, trace both static dependencies and runtime call paths.

### 12.4. Function EXECUTE Privilege and Trigger Setup

PostgreSQL checks appropriate `EXECUTE` privilege when creating a trigger referencing a trigger function. Runtime execution afterward depends on the function's security mode and trigger execution context.

Never grant broad trigger-creation privileges that allow application users to attach arbitrary privileged code.

## 13. Safe SECURITY DEFINER Functions: Design Pattern

A privileged routine should expose a narrow interface with explicit assumptions.

### 13.1. Create a Dedicated Owner Role

```sql
CREATE ROLE order_maintenance_owner NOLOGIN;

GRANT USAGE ON SCHEMA app_private TO order_maintenance_owner;
GRANT SELECT, UPDATE ON app.orders TO order_maintenance_owner;
```

The owner needs no `LOGIN`. Only migration or administrative roles may `SET ROLE` or transfer ownership per policy.

### 13.2. Create the Function in a Protected Schema

```sql
CREATE FUNCTION app_private.expire_one_order(p_order_id bigint)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app_private, app, pg_temp
AS $function$
DECLARE
    changed_count integer;
BEGIN
    IF p_order_id IS NULL THEN
        RAISE EXCEPTION 'order id is required';
    END IF;

    UPDATE app.orders
    SET status = 'expired',
        updated_at = clock_timestamp()
    WHERE id = p_order_id
      AND status = 'pending'
      AND expires_at < clock_timestamp();

    GET DIAGNOSTICS changed_count = ROW_COUNT;

    RETURN changed_count = 1;
END;
$function$;

ALTER FUNCTION app_private.expire_one_order(bigint)
OWNER TO order_maintenance_owner;
```

The function scopes the operation to a single order ID and validates current state. Business authorization must still govern which caller is permitted to expire which order.

### 13.3. Revoke PUBLIC EXECUTE

```sql
REVOKE ALL
ON FUNCTION app_private.expire_one_order(bigint)
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION app_private.expire_one_order(bigint)
TO order_job_runner;
```

The schema must also be protected so runtime roles cannot `CREATE`/`REPLACE` objects inside it.

### 13.4. Test with Runtime Roles

Test:

- Authorized and unauthorized callers.
- `NULL`/invalid inputs.
- Orders already paid or canceled.
- Concurrent calls.
- RLS behavior.
- Lock waits and transaction rollbacks.
- Altered `search_path`.
- Temporary objects sharing the same name.
- Verifying the function owner holds strictly minimal privileges.

### 13.5. A Function Is Not Automatically an Authorization Policy

If all authenticated users have `EXECUTE` on a function, the function itself must verify whether the caller is authorized to act on the target row. Never rely on callers lacking direct table privileges if the function performs no business authorization checks.

## 14. Auditing Functions and Security Configuration

Periodic audits help uncover routines with elevated execution contexts or unusual configuration.

### 14.1. SECURITY DEFINER Inventory

```sql
SELECT
    n.nspname AS schema_name,
    p.oid::regprocedure AS routine_identity,
    p.proowner::regrole AS owner,
    l.lanname AS language,
    p.prosecdef AS security_definer,
    p.proconfig AS function_settings,
    p.proacl AS acl
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
JOIN pg_language AS l
    ON l.oid = p.prolang
WHERE p.prosecdef
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, p.oid::regprocedure::text;
```

### 14.2. Functions by Language

```sql
SELECT
    l.lanname AS language_name,
    l.lanpltrusted AS trusted_language,
    n.nspname AS schema_name,
    count(*) AS routine_count
FROM pg_proc AS p
JOIN pg_language AS l
    ON l.oid = p.prolang
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
GROUP BY l.lanname, l.lanpltrusted, n.nspname
ORDER BY l.lanname, n.nspname;
```

### 14.3. SECURITY DEFINER Functions Missing a Function-Local search_path

```sql
SELECT
    n.nspname AS schema_name,
    p.oid::regprocedure AS routine_identity,
    p.proowner::regrole AS owner,
    p.proconfig
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE p.prosecdef
  AND NOT EXISTS (
      SELECT 1
      FROM unnest(COALESCE(p.proconfig, ARRAY[]::text[])) AS setting
      WHERE setting LIKE 'search_path=%'
  )
ORDER BY n.nspname, p.oid::regprocedure::text;
```

This serves as a review queue, not proof that a function is definitely vulnerable. A function might schema-qualify every object and never touch an untrusted search path. Still, explicitly setting a function-local `search_path` generally lowers risk.

### 14.4. Routines Using Untrusted Languages

```sql
SELECT
    n.nspname AS schema_name,
    p.oid::regprocedure AS routine_identity,
    p.proowner::regrole AS owner,
    l.lanname AS language_name,
    l.lanpltrusted AS is_trusted,
    p.prosecdef AS security_definer,
    p.proacl
FROM pg_proc AS p
JOIN pg_language AS l
    ON l.oid = p.prolang
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE NOT l.lanpltrusted
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY l.lanname, n.nspname, p.oid::regprocedure::text;
```

Functions written in untrusted languages require owner review and `EXECUTE` ACL review. Never grant `EXECUTE` broadly by schema if the schema contains untrusted routines.

### 14.5. Routine Properties

```sql
SELECT
    n.nspname AS schema_name,
    p.oid::regprocedure AS routine_identity,
    p.provolatile,
    p.proisstrict,
    p.proparallel,
    p.proleakproof,
    p.prosecdef,
    p.proconfig
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'app'
ORDER BY p.oid::regprocedure::text;
```

Catalog columns can change across major versions. For multi-version automation, inspect server version and catalog definitions before executing queries.

## 15. Inspecting Language Privileges

Language ACLs reside in `pg_language.lanacl`. Use helper functions to confirm effective privileges.

### 15.1. Language ACLs

```sql
SELECT
    lanname,
    lanpltrusted,
    lanacl
FROM pg_language
ORDER BY lanname;
```

A `NULL` `lanacl` can represent default ACL behavior. Never interpret `NULL` as meaning nobody has access.

### 15.2. Checking USAGE

```sql
SELECT
    rol.rolname,
    lang.lanname,
    has_language_privilege(
        rol.rolname,
        lang.lanname,
        'USAGE'
    ) AS can_use_language
FROM pg_roles AS rol
CROSS JOIN pg_language AS lang
WHERE rol.rolname IN (
    'app_developer',
    'app_runtime',
    'migration_runner'
)
ORDER BY rol.rolname, lang.lanname;
```

The result reports effective PostgreSQL privileges. For untrusted languages, superuser-only creation restrictions still apply separately.

### 15.3. Revoking Language USAGE

```sql
REVOKE USAGE ON LANGUAGE plpython3u FROM PUBLIC;
```

This statement is meaningful only where language/ACL semantics apply and does not replace superuser restrictions. Inspect owners and ACLs before modifying; some languages have differing default grants.

### 15.4. Creating a Function Requires Multiple Privileges Together

A role may need:

- `USAGE` on target schemas to resolve referenced objects.
- `CREATE` on the schema where the function is created.
- `USAGE` on the language.
- `EXECUTE` on functions invoked inside the body depending on execution context.
- Required table/sequence/type privileges if `SECURITY INVOKER`.
- Ownership or administrative rights if altering owners or security properties.

Never resolve a `CREATE FUNCTION` error by granting `SUPERUSER` to a developer.

## 16. Default Privileges and Deployment Ownership

A sustainable privilege model specifies which role creates objects and what default privileges new objects receive.

### 16.1. Creator Role

Designate a role that owns schemas and functions—for example `app_owner`. A migration runner can `SET ROLE app_owner` during deployment if allowed by policy.

Runtime roles receive only required `USAGE`/`EXECUTE`. Never let individual developers create production routines under personal logins and end up owning production objects.

### 16.2. Default Privileges

```sql
ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

ALTER DEFAULT PRIVILEGES
FOR ROLE app_owner
IN SCHEMA app
GRANT EXECUTE ON FUNCTIONS TO app_runtime;
```

Default privileges do not apply retroactively to existing functions. Nor do they apply to objects created by a different role.

### 16.3. Auditing Default ACLs

```sql
SELECT
    defaclrole::regrole AS creator_role,
    defaclnamespace::regnamespace AS schema_name,
    defaclobjtype,
    defaclacl
FROM pg_default_acl
ORDER BY creator_role, schema_name, defaclobjtype;
```

When schema-specific default privileges exist, they combine with global defaults according to PostgreSQL rules. Check both scopes during audits.

### 16.4. Existing Objects Must Be Revoked Explicitly

After setting defaults, review and revoke privileges on existing functions:

```sql
REVOKE EXECUTE
ON ALL FUNCTIONS IN SCHEMA app
FROM PUBLIC;
```

Then grant access to runtime roles following an approved list of function signatures.

### 16.5. CREATE OR REPLACE FUNCTION

`CREATE OR REPLACE FUNCTION` preserves the function's identity and may preserve existing ownership and permissions. However, the body or properties can change. Deployment reviews must inspect `SECURITY DEFINER`, `SET` clauses, language, volatility, and ACLs after replacement.

Never grant runtime roles `CREATE` in production schemas just so they can self-update function bodies.

## 17. Extension Installation and Supply-Chain Risk

Extensions can introduce native code, procedural languages, and elevated-privilege functions. Extension management is therefore part of the security boundary.

### 17.1. Inspect Installed Extensions

```sql
SELECT
    e.extname,
    e.extversion,
    e.extowner::regrole AS owner,
    n.nspname AS extension_schema
FROM pg_extension AS e
JOIN pg_namespace AS n
    ON n.oid = e.extnamespace
ORDER BY e.extname;
```

### 17.2. Inspect Extension Availability

```sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
ORDER BY name;
```

`pg_available_extensions` reflects extensions available in the current server/package environment. Not all of them are permitted on managed services.

### 17.3. Trusted Extension Installation

An extension control file can declare `trusted = true`. That allows a non-superuser holding `CREATE` privilege on the database to install the extension via supported PostgreSQL mechanisms.

Trusted extensions still warrant review. Any extension granted special installation eligibility should be evaluated by reading its installation scripts and executed code.

### 17.4. Extension Package Provenance

Verify:

- Publisher and source repository.
- Release tags and checksums.
- Compatibility with the PostgreSQL major version.
- Shared library dependencies.
- Security advisories.
- Update and rollback paths.
- OS package ownership and installation permissions.

Never install an extension from an unverified file merely because it provides a convenient function.

### 17.5. Extension Ownership and Dependencies

Extension objects carry membership dependencies. Never drop individual member objects via catalog edits or ad-hoc DDL. Use extension update/drop commands and inspect `CASCADE` impact.

### 17.6. Managed Database Restrictions

Cloud providers may restrict procedural languages/extensions and replace superuser with a managed administrative role. Check provider allowlists, parameter groups, and supported versions. Never assume self-hosted PostgreSQL superuser rights exist.

## 18. Function Owners and Code Modification Privileges

A function may have broad `EXECUTE` access, yet only its owner can alter its code or security properties.

### 18.1. Owner Inventory

```sql
SELECT
    n.nspname AS schema_name,
    p.oid::regprocedure AS routine_identity,
    p.proowner::regrole AS owner,
    l.lanname AS language,
    p.prosecdef AS security_definer
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
JOIN pg_language AS l
    ON l.oid = p.prolang
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY owner, routine_identity::text;
```

### 18.2. Owner Roles Should Not Be Runtime Logins

A `NOLOGIN` owner role lowers the chance an application session ever acquires ownership privileges. Migration runners receive controlled membership to deploy objects.

### 18.3. Ownership Transfer

```sql
ALTER FUNCTION app.calculate_discount(numeric)
OWNER TO app_owner;
```

Changing ownership requires appropriate privileges on both the function and the new role. Ownership changes do not automatically redesign caller grants; inspect ACLs afterward.

### 18.4. Drop/Recreate vs. Grants

Dropping and recreating a function can lose grants, comments, or dependencies and change its OID. `CREATE OR REPLACE` is generally better when preserving identity, though signatures and properties must still be checked.

## 19. Function Code Review Checklist

Review routines like security-sensitive code paths.

### 19.1. Identity and Ownership

- Is the schema properly protected?
- Is the owner a least-privilege `NOLOGIN` role?
- Is the language trusted?
- Does the function genuinely need `SECURITY DEFINER`?
- Who is allowed to `ALTER`/`REPLACE` the function?

### 19.2. Caller Privileges

- Who holds `EXECUTE`?
- Does `PUBLIC` hold `EXECUTE`?
- Does the runtime role actually need this function?
- Are grants scoped to the exact signature?
- Could the function be invoked indirectly via triggers, views, or policies?

### 19.3. Execution Context

- Is `search_path` safely pinned?
- Is `pg_temp` placed appropriately?
- Are objects schema-qualified?
- Does the function `SET` sensitive configuration values?
- Does RLS behavior match the effective user?

### 19.4. Input Handling

- Does it use dynamic SQL?
- Are values bound using parameters/`USING`?
- Are identifiers quoted with `%I` and checked against an allowlist?
- Does it accept raw SQL fragments?
- Are `NULL`/range/format validations in place?

### 19.5. Side Effects and Resources

- Does the function write data or call external APIs?
- Can it run unbounded loops or hang?
- Does it have transaction or lock side effects?
- Can it be called repeatedly or concurrently?
- Are idempotency and authorization checks present?

## 20. Monitoring and Auditing Routine Execution

PostgreSQL maintains function statistics when tracking is enabled. Logs and audit extensions add caller and query context.

### 20.1. Function Statistics

```sql
SHOW track_functions;
```

Values can include `none`, `pl`, and `all` depending on version and configuration. PL/pgSQL and other procedural functions can be tracked when configured appropriately.

```sql
SELECT
    schemaname,
    funcname,
    calls,
    total_time,
    self_time
FROM pg_stat_user_functions
ORDER BY total_time DESC;
```

Statistics are aggregate counters over a stats window, not a complete security audit log.

### 20.2. Limitations of Function Statistics

- Stats can be reset.
- Nested calls differentiate `total_time` from `self_time`.
- Function tracking adds overhead.
- Not every language/extension is instrumented identically.
- Caller identity is not recorded in the view.

### 20.3. Logging

Settings like `log_min_duration_statement` capture slow statements, and `pg_stat_statements` aggregates query fingerprints. If you need to audit who invoked which routine, use an appropriate logging/auditing architecture and scrub sensitive log data.

### 20.4. Security Audit Extensions

Some environments deploy `pgAudit` or database activity monitoring tools. Audit extension settings must be reviewed separately; audit logs can capture sensitive SQL, parameters, or identifiers.

### 20.5. Never Log Secrets in Function Errors

Avoid placing credentials, tokens, or raw sensitive inputs into `RAISE EXCEPTION`, `NOTICE`, or application logs. Error contexts may be persisted across multiple systems.

## 21. Common Privilege Patterns

### 21.1. Runtime Role Only Invokes Routines

```sql
CREATE ROLE app_runtime NOLOGIN;

GRANT CONNECT ON DATABASE appdb TO app_runtime;
GRANT USAGE ON SCHEMA app TO app_runtime;
GRANT EXECUTE ON FUNCTION app.calculate_discount(numeric)
TO app_runtime;
```

Application login roles can become members of the `app_runtime` group role. Do not grant schema `CREATE` or `USAGE` on untrusted languages unless required.

### 21.2. Developer Role Creates Functions in a Development Schema

```sql
CREATE ROLE app_developer NOLOGIN;

GRANT USAGE, CREATE ON SCHEMA app_dev TO app_developer;
GRANT USAGE ON LANGUAGE plpgsql TO app_developer;
```

Developer roles never need `SUPERUSER`, `CREATEROLE`, or production extension installation rights.

### 21.3. Migration Owner Manages Production Functions

```sql
CREATE ROLE app_owner NOLOGIN;

GRANT USAGE, CREATE ON SCHEMA app TO app_owner;
GRANT USAGE ON LANGUAGE plpgsql TO app_owner;
```

Migration runners receive controlled membership in `app_owner` and deploy through reviewed migration scripts.

### 21.4. Privileged Maintenance Function

Create a dedicated `NOLOGIN` owner, grant privileges on exact tables, pin `search_path`, revoke `PUBLIC` `EXECUTE`, and grant access to a dedicated job role.

### 21.5. Avoid Schema-Wide Routine Grants with Mixed Sensitivity

`GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app TO app_runtime` can accidentally expose newly added or sensitive routines. Prefer explicit grants or separate schemas along trust boundaries.

## 22. Separating Schemas by Trust Boundary

Organizing schemas reduces `search_path` and `CREATE` privilege risks.

### 22.1. Example Layout

| Schema | Contents | Runtime access |
| --- | --- | --- |
| `app` | Business tables/views | `USAGE`, appropriate table grants |
| `app_api` | Callable API functions | `USAGE`, selective `EXECUTE` |
| `app_private` | Internal helpers and `SECURITY DEFINER` routines | No runtime `CREATE`; restricted `EXECUTE` |
| `audit` | Audit records/functions | Tightly restricted access |
| `extensions` | Extension objects if policy requires | Per extension owner/ACL |

### 22.2. A Private Schema Is Not Automatically Safe

If a runtime role holds `CREATE` on `app_private`, an attacker can shadow objects resolved by privileged functions. Protect schema ACLs and owners.

### 22.3. search_path Defaults

Configure `search_path` per role or database for convenience, yet privileged functions must still pin a function-local `search_path` and schema-qualify objects. Never trust a caller's session configuration.

## 23. Common Mistakes

| Assumption or symptom | Risk | Remediation |
| --- | --- | --- |
| Trusted language means safe function | Trusted covers only language sandboxing | Review code, owner, ACLs, and execution context |
| Only superusers can call PL/PythonU | Superuser rule mainly restricts creation; `EXECUTE` can be granted | Audit callers and `EXECUTE` ACLs |
| `SECURITY DEFINER` is just a permission shortcut | Function runs with owner privileges | Use a minimal `NOLOGIN` owner and narrow interface |
| Function without explicit `EXECUTE` grant cannot be called | `PUBLIC` may have default `EXECUTE` | Revoke `PUBLIC` and inspect ACLs |
| Caller `search_path` is always trustworthy | Caller can shadow unqualified names | Function-local `search_path`, trusted schemas, `pg_temp` last |
| Quoting identifiers makes dynamic SQL safe | Caller can still pick out-of-scope objects | Enforce identifier allowlist and authorization |
| Bind parameters work for table names | Bind parameters only represent values | Use `format('%I')` for identifiers |
| C language behaves like PL/pgSQL | Native code runs inside the backend process | Review binaries/source and restrict to superuser |
| RLS always constrains `SECURITY DEFINER` | Owner/`BYPASSRLS` may bypass policies | Check owner, `FORCE RLS`, and policy context |
| Trusted extension means audited code | `trusted` flag only controls install eligibility | Audit source, scripts, and package provenance |
| `CREATE OR REPLACE` never affects security | Body and properties can change | Inspect diffs, owner, ACLs, and `SET` clauses |
| Runtime needs schema `CREATE` to call functions | `EXECUTE` and schema `USAGE` usually suffice | Remove unnecessary `CREATE` grants |
| Function stats serve as an audit log | Counters are aggregated and resettable | Use auditing/logging when caller history is needed |
| Dropping a language removes only its handler | Extensions may own multiple objects | Inventory dependencies and use `RESTRICT` |
| `public` schema permissions match every version | Default ACLs vary across versions/upgrades | Inspect actual ACLs |

## 24. Incident Response for Function Privilege Abuse

If unexpected function execution or a vulnerable `SECURITY DEFINER` routine is discovered:

**Step 1 — Contain.** Revoke `EXECUTE` on the function or disable the entry point following change procedures. Assess impact on callers and background jobs.

**Step 2 — Preserve evidence.** Capture the function definition, owner, ACLs, language, `proconfig`, grants, logs, and timestamps before modifying anything.

**Step 3 — Determine execution context.** Identify `SECURITY INVOKER`/`DEFINER`, effective owner, language trust, and OS-level capabilities.

**Step 4 — Identify callers.** Inspect logs, application traces, `pg_stat_statements`, audit extensions, and scheduled jobs.

**Step 5 — Inspect dependencies.** Locate triggers, views, policies, defaults, operators, and other routines calling the function.

**Step 6 — Check impact.** Determine which rows, files, or network resources were read or modified. Check for external side effects and exposed credentials.

**Step 7 — Repair privileges and code.** Move ownership to an appropriate `NOLOGIN` role, pin `search_path`, fix dynamic SQL, revoke `PUBLIC`, and re-grant `EXECUTE` per an allowlist.

**Step 8 — Rotate exposed secrets.** If the function could read secrets or credentials, rotate and revoke affected credentials.

**Step 9 — Verify.** Test using runtime roles, verify RLS/ownership, and confirm callers cannot exceed intended scope.

**Step 10 — Record and monitor.** File the incident record, update inventories, and monitor for unexpected `EXECUTE` activity.

Never patch only the function body while ignoring grants, ownership, or `search_path`. A privileged routine spans multiple security dimensions that must be remediated together.

## 25. Practice Exercises

Perform these in a dedicated PostgreSQL lab. Never install untrusted languages, build C functions, or test privilege escalation in production.

### Exercise 1 — List Languages

Query `pg_language` and explain `lanpltrusted`, `lanispl`, owner, and ACLs.

### Exercise 2 — SQL vs. PL/pgSQL

Create an SQL function and a PL/pgSQL function performing the same calculation. Compare code, planner behavior, and use cases.

### Exercise 3 — Language USAGE

Create a developer role, grant `USAGE` on `plpgsql` and `CREATE` on a lab schema, and confirm the role can create functions.

### Exercise 4 — Schema CREATE

Revoke `CREATE` on the schema and attempt `CREATE FUNCTION`. Explain the difference between `USAGE` and `CREATE`.

### Exercise 5 — Function EXECUTE

Create a function, revoke `EXECUTE` from `PUBLIC`, grant it to one role, and verify with `has_function_privilege`.

### Exercise 6 — Default Privileges

Configure `ALTER DEFAULT PRIVILEGES` for the function owner. Create a new function and inspect its ACL.

### Exercise 7 — Existing Grants

Run `REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA` in the lab. Identify which callers lose access.

### Exercise 8 — Function Overloads

Create two functions with the same name but different argument types. Grant/revoke by signature and verify independent permissions.

### Exercise 9 — SECURITY INVOKER

Create a function reading a table. Invoke it with a role lacking `SELECT` and observe the permission error.

### Exercise 10 — SECURITY DEFINER

Create a dedicated `NOLOGIN` owner with `SELECT` on a table. Create a `SECURITY DEFINER` function and verify whether callers can invoke it without direct `SELECT`.

### Exercise 11 — Least-Privilege Owner

Create an owner with access to one table. Attempt to query a different table to demonstrate the function owner lacks broad privileges.

### Exercise 12 — Search Path

Create a trusted schema and an untrusted schema containing functions with the same name. Change `search_path` and observe name resolution in the lab.

### Exercise 13 — Temporary Object Shadowing

Create a temporary table/function sharing the name of an unqualified target object. Compare a function without a pinned `search_path` against one putting `pg_temp` last.

### Exercise 14 — Schema Qualification

Convert unqualified names in a function to schema-qualified names. Retest with altered `search_path` values.

### Exercise 15 — Dynamic SQL Injection

Create a function concatenating values into an SQL string in the lab. Test an input containing quotes, then fix it using `USING` parameters.

### Exercise 16 — Identifier Quoting

Create a function querying a table by input identifier. Use `format('%I')` and an allowlist; test schema/table names with special characters.

### Exercise 17 — Raw SQL Fragments

Design a function that avoids accepting raw `WHERE` clauses, replacing them with typed parameters and predefined predicates.

### Exercise 18 — Trusted vs. Untrusted

Inspect package/language availability in the lab. Review documentation on trusted status; no OS command execution is needed to complete this exercise.

### Exercise 19 — Extension Inventory

Query `pg_extension` and `pg_available_extensions`. Compare installed versions against default versions.

### Exercise 20 — Extension Dependencies

Safely install a lab extension, inspect `pg_depend` membership, and test `DROP EXTENSION ... RESTRICT` in a test database.

### Exercise 21 — Function Language Inventory

List routines grouped by `pg_language` and identify untrusted-language candidates.

### Exercise 22 — SECURITY DEFINER Audit

Query `pg_proc.prosecdef`, owner, and `proconfig`. Identify routines missing a function-local `search_path`.

### Exercise 23 — RLS Context

Create a table with RLS, a policy referencing `current_user`, and a `SECURITY DEFINER` function. Observe effective user behavior and `FORCE ROW LEVEL SECURITY`.

### Exercise 24 — Trigger Function

Create a trigger function writing audit rows. Compare `SECURITY INVOKER`/`DEFINER` and inspect owner privileges.

### Exercise 25 — Functions in CHECK Constraints

Create an immutable function used in a `CHECK` constraint. Modify the function in the lab and examine why changing function semantics affects already-validated data.

### Exercise 26 — Volatility

Create `IMMUTABLE`/`STABLE`/`VOLATILE` functions and observe planner behavior. Never misdeclare volatility to force optimizations.

### Exercise 27 — Parallel Safety

Create a function with side effects and explain why it must not be marked `PARALLEL SAFE`.

### Exercise 28 — LEAKPROOF

Read documentation and inspect the catalog property. Explain why only superusers can mark functions leakproof and how this relates to RLS and security barrier views.

### Exercise 29 — Ownership Transfer

Transfer function ownership to a `NOLOGIN` role. Verify ACLs, `EXECUTE`, and `SECURITY DEFINER` behavior afterward.

### Exercise 30 — Default Privileges Across Owners

Create two creator roles with differing default privileges. Confirm one role's settings do not automatically apply to the other.

### Exercise 31 — Extension Installation Trust

Read the control file of an available extension in the lab. Identify its `trusted` flag and installation privilege requirements.

### Exercise 32 — Search Path ACL Audit

Query schema owners and `CREATE` grants for schemas appearing in privileged functions' `search_path`. Report schemas with untrusted writers.

### Exercise 33 — Function Code Review

Review a sample `SECURITY DEFINER` function. Document owner, language, ACLs, `search_path`, dynamic SQL, RLS behavior, and input validation.

### Exercise 34 — Incident Containment

Simulate a function with overly broad `EXECUTE` in the lab. Revoke access, audit callers, and re-grant via an allowlist.

### Exercise 35 — Production Security Runbook

Write a runbook for deploying a procedural language extension and privileged function covering package provenance, trusted status, ownership, schema ACLs, language `USAGE`, `EXECUTE`, `search_path`, RLS, monitoring, and rollback.

## 26. Summary

Core takeaways for managing **additional procedural languages and execution privilege risks**:

1. PostgreSQL supports SQL, PL/pgSQL, and multiple additional procedural languages.
2. Procedural languages are typically installed/managed via extensions; package availability depends on server build and environment.
3. Trusted languages enforce only language-level restrictions; they do not guarantee safe function code.
4. Untrusted languages and C functions can expose filesystem, process, network, or native-code execution under PostgreSQL's OS account.
5. Superuser restrictions on creating untrusted functions do not stop non-superusers from calling them if `EXECUTE` is granted.
6. Creating functions requires schema and language privileges; installing extensions is a separate privilege boundary.
7. Function/procedure `EXECUTE` defaults to `PUBLIC`, so revoke it and configure default privileges.
8. `SECURITY INVOKER` uses caller privileges; `SECURITY DEFINER` uses function owner privileges.
9. `SECURITY DEFINER` requires a minimal `NOLOGIN` owner, narrow interface, safe `search_path`, and an `EXECUTE` allowlist.
10. `search_path` hijacking and temporary-schema shadowing can trick privileged functions into calling the wrong object.
11. Dynamic SQL must bind values with `USING`, quote identifiers with `%I`, and validate against allowlists.
12. RLS can be bypassed or affected by owner/`BYPASSRLS` contexts inside `SECURITY DEFINER` functions.
13. Functions can be invoked indirectly via triggers, policies, defaults, views, constraints, and operators.
14. Volatility, parallel safety, and leakproof are execution/planner contracts, not authorization mechanisms.
15. Periodically audit routine owners, languages, ACLs, `proconfig`, dependencies, and extension provenance.

A secure procedural function must be reviewed like a privileged API. Language determines how code runs; owner and security mode determine effective privileges; `EXECUTE` ACLs determine who can trigger it; `search_path` and input handling determine which objects are resolved and executed. Governing each layer independently extends PostgreSQL without turning stored routines into privilege-escalation shortcuts.

## 27. Official PostgreSQL Documentation

- [Procedural Languages](https://www.postgresql.org/docs/current/xplang.html)
- [PL/pgSQL](https://www.postgresql.org/docs/current/plpgsql.html)
- [PL/Python](https://www.postgresql.org/docs/current/plpython.html)
- [PL/Perl](https://www.postgresql.org/docs/current/plperl.html)
- [PL/Tcl](https://www.postgresql.org/docs/current/pltcl.html)
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html)
- [CREATE PROCEDURE](https://www.postgresql.org/docs/current/sql-createprocedure.html)
- [Function Security](https://www.postgresql.org/docs/current/perm-functions.html)
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html)
- [GRANT](https://www.postgresql.org/docs/current/sql-grant.html)
- [ALTER DEFAULT PRIVILEGES](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html)
- [Schemas and Search Path](https://www.postgresql.org/docs/current/ddl-schemas.html)
- [Writing SECURITY DEFINER Functions Safely](https://www.postgresql.org/docs/current/sql-createfunction.html)
- [CREATE EXTENSION](https://www.postgresql.org/docs/current/sql-createextension.html)
- [Extension Packaging](https://www.postgresql.org/docs/current/extend-extensions.html)
- [pg_language](https://www.postgresql.org/docs/current/catalog-pg-language.html)
- [pg_proc](https://www.postgresql.org/docs/current/catalog-pg-proc.html)
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [Function Volatility Categories](https://www.postgresql.org/docs/current/xfunc-volatility.html)
- [Parallel Safety](https://www.postgresql.org/docs/current/parallel-safety.html)
- [Dynamic SQL in PL/pgSQL](https://www.postgresql.org/docs/current/plpgsql-statements.html#PLPGSQL-STATEMENTS-EXECUTING-DYN)

The `current` links point to current PostgreSQL documentation. Procedural language names, trusted flags, extension availability, privilege behavior, and catalog fields can vary across PostgreSQL major versions, OS packages, and managed-service policies. Before installing a language or granting production privileges, inspect server version, `pg_language`, `pg_extension`, extension control files, and privilege behavior in the exact target environment.
