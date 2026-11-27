# Trusted Extensions, Installation Privileges, and PostgreSQL Server-Side Code

PostgreSQL can be extended with extensions, procedural languages, functions, triggers, and native modules. These components enable processing close to the data, but they also create critical security boundaries: **who can install extensions, which privileges installation scripts run under, and which resources server-side code can access**.

An extension may only add SQL objects, or it may load C code directly into the backend process. A procedural language may be designed for regular users, or it may allow executing arbitrary code with operating system privileges. Therefore, not all extensions or procedural languages can be treated as equivalent.

The lesson **“Trusted Extensions, Installation Privileges, and Server-Side Code”**, part of the **Scaling** chapter of the **Database Engine Relational PostgreSQL** module, explains:

- Extension structure: control files, SQL scripts, update scripts, and shared libraries.
- Differences between trusted and untrusted extensions.
- `CREATE` privilege conditions and superuser requirements.
- How the `trusted` attribute affects installation scripts and extension ownership.
- Distinguishing OS package installation from `CREATE EXTENSION` in the database.
- Procedural languages, C functions, `SECURITY DEFINER`, and server-side code.
- Access to files, programs, and external resources.
- Applying least privilege, verifying extension provenance, and auditing changes.

> **Principle:** extension installation privileges strongly affect database security. Only install extensions from trusted sources, inspect code and native libraries, understand the `trusted` flag, and limit the privileges of the executing role.

---

## 1. What Is an Extension in PostgreSQL?

An extension is a package of database objects managed as a single unit. It can provide:

- SQL functions and operators.
- Data types and casts.
- Index access methods or operator classes.
- Views and catalog objects.
- Procedural languages.
- C functions loaded into the server.
- Background workers or other native components depending on the extension.

Common examples of extensions include `pg_stat_statements`, `pgcrypto`, `uuid-ossp`, `hstore`, and PostGIS.

Not all extensions carry the same risk level. An extension that only creates SQL views differs from an extension that loads native C code into the backend.

## 2. What Does CREATE EXTENSION Do?

The `CREATE EXTENSION` command installs the objects defined by an extension into the current database.

~~~sql
CREATE EXTENSION pgcrypto;
~~~

PostgreSQL locates the extension control file, determines the version and installation script, and executes the SQL script to create the objects.

Inspect installed extensions:

~~~sql
SELECT
    extname,
    extversion,
    extowner::regrole AS owner,
    extnamespace::regnamespace AS schema_name
FROM pg_extension
ORDER BY extname;
~~~

Extensions are installed at the database scope. Installing an extension in one database does not mean the extension automatically appears in every other database of the cluster.

## 3. What Does an Extension Package Contain?

| Component | Role |
|---|---|
| Control file | Metadata and extension properties |
| SQL installation script | Creates functions, types, operators, and objects |
| Update scripts | Transitions the extension between SQL versions |
| Shared library | Native code if required by the extension |
| Supporting files | Headers, configuration, or other resources |

On Linux, the package manager typically installs files into PostgreSQL-specific directories. On Windows, the corresponding installer/package installs binaries and SQL files for the matching PostgreSQL build.

A database role does not automatically install native libraries into operating system directories. These are two distinct administrative layers.

## 4. Control File

The control file typically follows the naming pattern `extension_name.control`.

Example:

~~~text
comment = 'Example extension'
default_version = '1.0'
module_pathname = '$libdir/example_extension'
relocatable = true
superuser = true
trusted = false
~~~

Important properties:

- `default_version`: the default version.
- `module_pathname`: the library path referenced by the SQL script.
- `relocatable`: whether the extension can change schemas.
- `schema`: the default or required installation schema.
- `requires`: dependent extensions.
- `superuser`: whether superuser is required for installation.
- `trusted`: whether non-superuser users are allowed to install via the trusted extension mechanism.

Not every extension declares every property. Default values and semantics should be checked for your PostgreSQL version.

## 5. What Is a Trusted Extension?

An extension marked `trusted = true` in its control file can be installed by a non-superuser if that user holds the `CREATE` privilege on the current database.

This mechanism allows DBAs to delegate installation of certain vetted extensions without granting superuser to application users.

`trusted` does not mean the extension has been certified safe by the PostgreSQL security team, has no bugs, or cannot be abused. It is an attribute declared by the extension author/package maintainer in the control file.

Therefore, the DBA must still evaluate the provenance and contents of the extension.

## 6. Conditions for a User to Install a Trusted Extension

A non-superuser can install a trusted extension if:

1. The extension's control file sets `trusted = true`.
2. The user has the `CREATE` privilege on the current database.
3. The extension package and SQL scripts are available on the server.
4. Dependencies and versions match.
5. The user holds any other required privileges dictated by the extension and created objects.

Example of granting the database privilege:

~~~sql
GRANT CREATE ON DATABASE appdb TO app_extension_admin;
~~~

Then `app_extension_admin` connects to `appdb` and installs the supported trusted extension:

~~~sql
CREATE EXTENSION some_trusted_extension;
~~~

Do not grant this privilege to every application role. The database `CREATE` privilege allows creating schemas and can impact namespaces; use a dedicated deployment role.

## 7. Trusted Does Not Mean the Installation Script Runs with Regular Privileges

An important detail to understand accurately: for a trusted extension, if the installation script needs privileges only a superuser has, PostgreSQL can run that portion of the script with bootstrap superuser privileges under the trusted extension mechanism.

The user invoking `CREATE EXTENSION` is still the requester and becomes the extension owner per PostgreSQL rules. However, parts of the script may execute with elevated privileges to create special objects.

This creates a critical security requirement: a trusted extension's installation script must be designed safely against non-superuser callers authorized to install it.

Do not assume the script can only do what the invoking user can do directly.

## 8. Untrusted Extensions

Extensions not marked trusted usually require superuser to install if the control file defaults to `superuser = true`.

~~~text
superuser = true
trusted = false
~~~

A regular role with `CREATE` on the database is not sufficient. A superuser or privileged deployment process must execute:

~~~sql
CREATE EXTENSION example_extension;
~~~

Some extensions may declare `superuser = false` yet still not be marked trusted. Check the control file and extension documentation rather than relying on names or assumptions.

## 9. Distinguishing Superuser from the CREATE Privilege

| Privilege | Scope | Meaning |
|---|---|---|
| SUPERUSER | Entire PostgreSQL instance | Bypasses most permission checks |
| CREATE on database | One database | Allows creating schemas and certain objects |
| CREATE on schema | One schema | Allows creating objects within the schema |
| Extension ownership | One extension | Manages certain `ALTER`/`DROP` operations |
| USAGE on schema | One schema | Allows accessing/looking up objects per related grants |

`CREATE` on a database is not equivalent to superuser. Nevertheless, this privilege is still broader than read-only access or calling a single function.

Grant privileges per specific database and role; never use `GRANT CREATE ON DATABASE ... TO PUBLIC`.

## 10. Checking the CREATE Privilege

Check the current role:

~~~sql
SELECT
    current_user,
    session_user,
    has_database_privilege(
        current_user,
        current_database(),
        'CREATE'
    ) AS can_create_in_database;
~~~

Inspect the database ACL:

~~~sql
SELECT datname, datacl
FROM pg_database
WHERE datname = current_database();
~~~

You can use `\l+` in `psql` to inspect database privileges. Do not judge solely by role name; privileges can come from role membership or `PUBLIC`.

## 11. Separating the Deployment Role from the Application Role

A practical model:

- `app_owner`: owner of schemas/application objects.
- `app_runtime`: role used by the application at runtime.
- `app_extension_admin`: role for deploying approved extensions.
- `db_admin`: DBA with higher administrative privileges.

Example:

~~~sql
CREATE ROLE app_runtime LOGIN;
CREATE ROLE app_extension_admin LOGIN;

GRANT CONNECT ON DATABASE appdb TO app_runtime;
GRANT CONNECT, CREATE ON DATABASE appdb TO app_extension_admin;
~~~

After installing the extension and completing migrations, you can revoke `CREATE` if the role no longer needs it:

~~~sql
REVOKE CREATE ON DATABASE appdb FROM app_extension_admin;
~~~

The specific design must consider schema ownership, the migration framework, and the deployment workflow. Never grant the extension administration role to an account continuously used by a web application.

## 12. OS Package Installation vs. CREATE EXTENSION

There are two separate operations:

**Package/binary installation:** the OS administrator installs control files, SQL scripts, and native libraries into PostgreSQL directories.

**Database extension installation:** a database role runs `CREATE EXTENSION` to create SQL objects in the current database.

Debian/Ubuntu example (package name varies by PostgreSQL major version and repository):

~~~bash
sudo apt install postgresql-17-pg-stat-statements
~~~

Then connect to the database and run:

~~~sql
CREATE EXTENSION pg_stat_statements;
~~~

The package name is illustrative only. Check the repository and package naming of your operating system.

A database superuser does not automatically have root permissions to install OS packages. Conversely, an OS administrator does not automatically hold database superuser credentials.

## 13. Why Must Native Libraries Be Installed First?

If an extension requires a shared library, control file, or SQL scripts that the server cannot find, `CREATE EXTENSION` can fail.

Example:

~~~text
ERROR: could not access file "$libdir/example_extension":
No such file or directory
~~~

This error usually relates to package/library path, PostgreSQL major version, architecture, or dynamic linker dependencies.

Verify the package matches the major version, shared library path, control file, SQL scripts, native dependencies, and read permissions for the PostgreSQL process.

Do not fix this by arbitrarily copying a library from another server version.

## 14. Extensions and PostgreSQL Major Versions

Native extensions are usually built for a specific PostgreSQL major version, because server APIs/ABI can change.

When upgrading major versions:

- Install the extension package built for the target major version.
- Verify vendor support for the target.
- Verify the library path.
- Inspect extension update scripts.
- Run `ALTER EXTENSION ... UPDATE` when needed.
- Test functions and query plans.

A pure SQL extension may have different requirements than a native C extension. Never assume binaries from an older version work on a new server.

## 15. Inspecting Available Extensions

The `pg_available_extensions` view lists extensions that have control files in the server installation along with their installation status in the current database:

~~~sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
ORDER BY name;
~~~

This view does not prove that all native dependencies load cleanly or that the extension is safe. It is strictly an inventory step.

## 16. Checking Extension Versions and Dependencies

~~~sql
SELECT
    name,
    version,
    installed
FROM pg_available_extension_versions
ORDER BY name, version;
~~~

Some extensions depend on other extensions. The control file may declare `requires`, though external dependencies outside the database such as OS libraries, services, or external data may also exist.

Read vendor documentation and package metadata before installing.

## 17. Installing an Extension into a Specific Schema

If an extension is relocatable and allows specifying a schema:

~~~sql
CREATE SCHEMA extensions AUTHORIZATION app_owner;

CREATE EXTENSION hstore
WITH SCHEMA extensions;
~~~

The schema must exist beforehand, and the executing user needs appropriate privileges. Not all extensions are relocatable or allow specifying a schema.

Verify:

~~~sql
SELECT
    extname,
    extrelocatable,
    extnamespace::regnamespace AS schema_name
FROM pg_extension
ORDER BY extname;
~~~

The control file and extension docs govern exact behavior.

## 18. Schemas and search_path

`search_path` determines how PostgreSQL resolves non-schema-qualified object names.

~~~sql
SHOW search_path;
~~~

If a role can create objects in a schema appearing in the `search_path` of privileged code, an attacker can create a spoofed object to alter how a function resolves names.

For security-sensitive code:

- Schema-qualify object references.
- Keep `CREATE` privileges on schemas in `search_path` strictly controlled.
- Set a safe `search_path` on `SECURITY DEFINER` functions.
- Avoid using schemas writable by untrusted users.

## 19. Trusted Extension Does Not Equal Trusted Schema

Two distinct concepts:

- **Trusted extension:** the control file allows non-superusers to install the extension via PostgreSQL's mechanism.
- **Trusted schema:** a schema trusted for privileged code to look up objects, typically withholding `CREATE` from untrusted users.

A trusted extension can still be installed into an inappropriate schema if deployment policy is too lax. A secure schema does not make an untrusted extension safe.

## 20. Extension Ownership

The extension owner is stored in `pg_extension.extowner`.

~~~sql
SELECT
    extname,
    extowner::regrole AS extension_owner,
    extnamespace::regnamespace AS schema_name,
    extversion
FROM pg_extension
ORDER BY extname;
~~~

The owner can perform extension management operations according to PostgreSQL privileges and rules. For a trusted extension, the non-superuser installer normally becomes the extension owner.

Choose a stable deployment role as the owner, rather than a personal account or easily deleted application login.

## 21. ALTER EXTENSION and UPDATE

To upgrade an extension to a new version that has an update path:

~~~sql
ALTER EXTENSION pgcrypto UPDATE;
~~~

Or specify a target version:

~~~sql
ALTER EXTENSION example_extension UPDATE TO '2.0';
~~~

A corresponding update script must exist on the server. The executing user must hold required privileges; updating may require superuser depending on the extension and script.

Verify the version after updating:

~~~sql
SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
~~~

Do not confuse a PostgreSQL major upgrade with an extension SQL update. These are two different procedures.

## 22. DROP EXTENSION and Dependencies

~~~sql
DROP EXTENSION example_extension;
~~~

If other objects depend on the extension's objects, the command may fail. `CASCADE` can drop dependent objects:

~~~sql
DROP EXTENSION example_extension CASCADE;
~~~

Do not use `CASCADE` just to make the command succeed. Inventory dependencies and prepare a backup/migration plan before removing an extension.

## 23. Installation Scripts Are Executable Code

Extension SQL scripts can create functions, grant privileges, create operators/types, create event triggers, call existing functions, load native libraries, or perform catalog/DDL operations.

Consequently, reviewing installation/update scripts is part of security review.

Particularly for trusted extensions, check whether the script uses superuser privileges during installation and whether it could be influenced by objects pre-created by the installer.

Do not install an extension merely because it exists in a package repository; verify vendor, provenance, source, and release history.

## 24. Native C Extensions

A C extension can declare functions in SQL and map them to symbols in a shared library.

Conceptual example:

~~~sql
CREATE FUNCTION example_add(integer, integer)
RETURNS integer
AS '$libdir/example_extension', 'example_add'
LANGUAGE C
STRICT;
~~~

When the function is invoked, native code runs inside the PostgreSQL backend process.

Risks include memory corruption, backend/server crashes, buffer overruns, arbitrary code execution in process context, reading/writing OS resources accessible to the process, and concurrency/transaction semantics bugs.

A C extension must be treated as code running inside the database server's trusted computing base.

## 25. OS Privileges of the PostgreSQL Process

The PostgreSQL server normally runs under a dedicated OS account, such as `postgres` on Linux.

Native code loaded into the backend process typically inherits the OS privileges of that process. This means a native extension does not automatically run with root privileges, but it can access every resource the PostgreSQL OS account is permitted to access.

Therefore:

- Never run the PostgreSQL server as root.
- Restrict file permissions and service account privileges.
- Do not leave unnecessary secrets readable by the `postgres` OS user.
- Isolate network egress where appropriate.
- Keep native packages and dependencies updated.
- Only install reviewed code.

Database superuser and OS root are two different privilege boundaries, yet native code can bridge them at the level of the server process's privileges.

## 26. Procedural Languages

PostgreSQL supports procedural languages for writing server-side functions and procedures.

Examples:

- `plpgsql`: the common default language, marked trusted.
- `plpython3u`: untrusted PL/Python.
- `plperl`: trusted PL/Perl in supported configurations.
- `plperlu`: untrusted PL/Perl.
- `pltcl`: trusted PL/Tcl.
- `pltclu`: untrusted PL/Tcl.

Available languages and packages depend on the PostgreSQL build/distribution. Check the catalog and environment documentation.

## 27. Trusted and Untrusted Procedural Languages

A trusted procedural language is designed to be used by users with function-creation privileges in a database without requiring superuser for every operation.

Untrusted languages allow broader capabilities, typically including accessing resources outside the database or executing arbitrary code. Creating functions in an untrusted language normally requires superuser.

Language names with a `u` suffix often indicate untrusted in certain PLs, such as `plpython3u` and `plperlu`.

Do not rely absolutely on naming suffixes; check `pg_language.lanpltrusted` and documentation.

## 28. Viewing Installed Languages and Trust Status

~~~sql
SELECT
    lanname,
    lanpltrusted,
    lanowner::regrole AS owner
FROM pg_language
ORDER BY lanname;
~~~

`lanpltrusted = true` indicates the language is marked trusted in the catalog.

A trusted language still requires reviewing its implementation and version. This flag does not replace security testing.

## 29. PL/pgSQL

PL/pgSQL is the procedural language usually installed by default in new databases.

Example function:

~~~sql
CREATE OR REPLACE FUNCTION public.order_total(p_order_id bigint)
RETURNS numeric
LANGUAGE plpgsql
AS $$
DECLARE
    v_total numeric;
BEGIN
    SELECT total_amount
      INTO v_total
      FROM public.orders
     WHERE order_id = p_order_id;

    RETURN v_total;
END;
$$;
~~~

PL/pgSQL suits business logic close to the data, flow control, and SQL operations. Even though it is a trusted language, functions still execute with `SECURITY INVOKER` or `SECURITY DEFINER` privilege semantics.

## 30. Untrusted PL/Python

PL/Python is commonly provided under the name `plpython3u` and is an untrusted procedural language.

Functions can execute Python code within the backend context and potentially access the OS environment under the server process's privileges, depending on implementation and sandboxing.

Installing the language and creating functions require elevated privileges because code can bypass database object permissions.

Install only when there is a clear use case, a trusted package, and an acceptable threat model. Do not allow application users to create or modify untrusted-language functions.

## 31. SECURITY INVOKER and SECURITY DEFINER

By default, functions execute with the privileges of the calling user: `SECURITY INVOKER`.

A `SECURITY DEFINER` function runs with the privileges of the function owner.

Example:

~~~sql
CREATE FUNCTION public.get_private_balance(p_account_id bigint)
RETURNS numeric
LANGUAGE sql
SECURITY DEFINER
AS $$
    SELECT balance
    FROM finance.accounts
    WHERE account_id = p_account_id;
$$;
~~~

If the owner has read access to the table, the caller can use the function to access data within the scope permitted by the function.

`SECURITY DEFINER` is useful for exposing narrowly scoped APIs, but flaws in the function can turn into privilege escalation.

## 32. Protecting SECURITY DEFINER with search_path

A privileged function can be attacked if it resolves object names from a schema where untrusted users hold `CREATE` privileges.

Example of a safer declaration:

~~~sql
CREATE FUNCTION admin_api.read_setting(p_name text)
RETURNS text
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, admin_api, pg_temp
AS $$
BEGIN
    RETURN (
        SELECT setting_value
        FROM admin_api.settings
        WHERE setting_name = p_name
    );
END;
$$;
~~~

Principles:

- Schema-qualify sensitive objects.
- Ensure schemas preceding `pg_temp` are not writable by untrusted users.
- Set `search_path` explicitly.
- Avoid uncontrolled dynamic SQL calls.
- Review function owner and grants.
- Revoke `EXECUTE` from `PUBLIC` if unnecessary.

The exact order and schemas must be designed for the specific function; do not copy sample `search_path` settings without understanding object resolution.

## 33. Revoking PUBLIC EXECUTE

New functions often receive `EXECUTE` privilege for `PUBLIC` by default in many cases. For sensitive functions, revoke and grant explicitly:

~~~sql
REVOKE ALL ON FUNCTION admin_api.read_setting(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION admin_api.read_setting(text) TO app_runtime;
~~~

Verify grants via `psql` or the ACL catalog. Do not grant `EXECUTE` to an application role if the function is not part of the application's API.

## 34. Dynamic SQL and Server-Side SQL Injection

PL/pgSQL can construct dynamic SQL using `EXECUTE`.

Never concatenate untrusted string input directly into SQL:

~~~sql
-- Dangerous if p_name comes from untrusted input:
EXECUTE 'SELECT * FROM users WHERE name = ''' || p_name || '''';
~~~

Use parameters for values:

~~~sql
EXECUTE
    'SELECT count(*) FROM public.users WHERE name = $1'
USING p_name;
~~~

Identifiers cannot be bound with `$1`; use `format('%I', identifier)` to quote identifiers properly and validate against an allowlist whenever possible.

SQL injection inside a `SECURITY DEFINER` function can have far more severe consequences because the function runs with the owner's privileges.

## 35. Server-Side File Access

Certain SQL commands/functions can read or write files on the database server's filesystem.

Examples:

- `COPY ... FROM '/server/path/file.csv'`.
- `COPY ... TO '/server/path/file.csv'`.
- Large object functions that access server-side files.

These operations differ from `psql`'s `\copy`. `\copy` reads/writes files on the client machine, whereas SQL `COPY` with a filename accesses the server's filesystem.

Do not grant file access privileges merely for import/export convenience. Prefer client-side transfers or controlled staging locations.

## 36. Predefined Roles for Server File Access

PostgreSQL provides predefined roles with special privileges, depending on version:

- `pg_read_server_files`: read files on the server accessible to the PostgreSQL process.
- `pg_write_server_files`: write files on the server accessible to the PostgreSQL process.
- `pg_execute_server_program`: execute programs on the server via protected features.

Example:

~~~sql
GRANT pg_read_server_files TO controlled_import_role;
~~~

These are broad privileges that can expose configuration, data files, or secrets readable by the OS account. Grant them only to trusted operators within controlled scopes.

## 37. COPY PROGRAM and Program Execution

`COPY ... PROGRAM` can execute a server-side shell command on supported systems.

Syntax example:

~~~sql
COPY (
    SELECT order_id, total_amount
    FROM public.orders
) TO PROGRAM 'some_command';
~~~

This capability is highly sensitive because the command runs on the database host with the OS privileges of the PostgreSQL process.

Permission is typically gated by superuser or the `pg_execute_server_program` role. Never grant this role to application accounts or untrusted users.

Never build commands by concatenating user input. If exports are needed, prefer client-side tools or dedicated services.

## 38. Server-Side Code and Network Access

Some extensions or procedural languages can open network connections, call external services, or read files.

This capability depends on the language/runtime, native library, OS permissions, network policy, and container/VM isolation.

Do not assume a database function is confined inside the database. Native code or untrusted languages can affect the host within the bounds of process privileges.

Design appropriate egress firewalls and service identities for database hosts.

## 39. Event Triggers

Event triggers are database-level DDL triggers that can run a function when certain DDL events occur.

~~~sql
CREATE EVENT TRIGGER audit_ddl
ON ddl_command_end
EXECUTE FUNCTION audit.capture_ddl();
~~~

An event trigger can observe or react to DDL. The backing function must be protected because it executes during command processing and can alter behavior or write audit data.

Do not let untrusted roles create event triggers affecting the entire database. Check owner, function security, and DDL permissions.

## 40. Background Workers

Some extensions register background workers that run within the PostgreSQL server process lifecycle.

Background workers can poll queues/tables, perform maintenance, emit metrics, run replication/coordination tasks, or open internal connections.

Review worker lifecycle, restart behavior, shared memory, signal handling, error handling, and logging.

A worker running inside the database server is not an independent sandboxed service. Bugs in native code can impact server stability.

## 41. How Can an Extension Change Privileges?

An installation script can create objects and grant privileges. After installation, inspect:

- Extension owner.
- Object owners.
- Function `EXECUTE` grants.
- Schema `CREATE`/`USAGE`.
- Default privileges.
- `SECURITY DEFINER` functions.
- Event triggers.
- Native libraries.
- Required role memberships.

Do not assume an extension only creates an isolated namespace. Read installation scripts and catalog changes according to risk level.

## 42. Reviewing an Extension Before Installation

Review checklist:

1. What is the package/repository source?
2. Are the maintainer and release history trustworthy?
3. Is the source code public and reviewed?
4. Does the extension contain native C code?
5. Does the extension have procedural language dependencies?
6. Are there `SECURITY DEFINER` functions?
7. Do installation scripts create roles/grants?
8. Does it read/write files or access the network?
9. Does it run background workers?
10. Does it support the target PostgreSQL version?
11. Are there CVEs or security advisories?
12. Is there an update/rollback path?
13. Can it be tested in staging?

Never install a production extension based solely on a blog post or package name.

## 43. Provenance and Supply Chain

Extensions can come from the PostgreSQL distribution, OS vendor, cloud provider, extension author, or third-party repositories.

Supply chain controls:

- Use organization-approved repositories.
- Verify package signatures/checksums per OS procedures.
- Pin versions where needed.
- Monitor security advisories.
- Review source/release notes.
- Restrict who can install packages onto database hosts.
- Never arbitrarily download shared libraries from the Internet into `$libdir`.

Installing an extension is a code change on the server, not merely a schema change.

## 44. Least Privilege for Extension Deployment

Recommended privilege model:

- DBA/superuser is responsible for installing privileged extensions.
- The deployment role holds database `CREATE` only when needed to install approved trusted extensions.
- Application roles hold only `CONNECT` and privileges to use necessary objects.
- Runtime roles have no permissions to install/remove extensions.
- OS package installation is handled by system administrators or controlled automation.

Revoke temporary privileges after deployment once no longer needed.

## 45. Auditing Extension Changes

Inventory extensions:

~~~sql
SELECT
    current_database() AS database_name,
    extname,
    extversion,
    extowner::regrole AS owner,
    extnamespace::regnamespace AS schema_name
FROM pg_extension
ORDER BY extname;
~~~

Check languages:

~~~sql
SELECT
    lanname,
    lanpltrusted,
    lanowner::regrole AS owner
FROM pg_language
ORDER BY lanname;
~~~

Combine database logs, DDL auditing, change records, and package management logs to know who installed what, when, and from which package version.

`pg_extension` only shows current state; it is not a complete audit history.

## 46. Distinguishing Trusted Extensions from Safe SQL Functions

An extension having `trusted = true` does not make every function inside it safe for all users.

A function might return sensitive data, call another privileged function, use `SECURITY DEFINER`, accept dynamic SQL input, modify objects, or cause resource exhaustion.

Evaluate each API/function for permissions and data access. Extension trust only addresses part of the installation prerequisites.

## 47. CREATE Privileges in Databases vs. Schemas

`CREATE ON DATABASE` allows creating schemas and database-scoped objects per the privilege model. `CREATE ON SCHEMA` allows creating objects within a schema.

Example:

~~~sql
GRANT CREATE ON SCHEMA extensions TO app_extension_admin;
~~~

Schema privileges do not replace the database `CREATE` condition for trusted extension installation. Check the privilege requirements of the specific command and extension.

After installation, `CREATE` on the schema can be revoked to curb arbitrary object creation.

## 48. SECURITY DEFINER and Extension APIs

An extension may install `SECURITY DEFINER` functions to provide an API running with owner privileges.

When using them:

- Verify the function owner.
- Inspect the definition.
- Check `prosecdef`.
- Check `proconfig` and `search_path`.
- Check `PUBLIC EXECUTE`.
- Identify accessed data objects.
- Test with the least-privileged application role.

Inventory example:

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    p.proowner::regrole AS owner,
    p.prosecdef AS security_definer,
    p.proconfig
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE p.prosecdef
ORDER BY n.nspname, p.proname;
~~~

This is a starting point for review, not a replacement for source review or security testing.

## 49. Untrusted Languages and the Superuser Boundary

A superuser can install an untrusted procedural language and create functions using that language. Such functions can execute code inside the backend process.

Risks include reading server files, making network calls, spawning subprocesses, or accessing other OS resources under process privileges, depending on language/runtime.

Only trusted DBAs should install or create untrusted-language functions. Never grant application users `CREATE` on schemas holding privileged code or permission to create languages.

## 50. Resource Exhaustion

Server-side code can consume CPU, memory, backend slots, locks, temporary disk, shared memory, and I/O.

An infinite-looping function or heavy query can slow down the database or exhaust resources.

Apply:

- `statement_timeout`.
- `lock_timeout`.
- `idle_in_transaction_session_timeout` where appropriate.
- OS/container-level resource governance.
- Workload isolation.
- Monitoring and cancellation policies.

SQL timeouts are not a complete sandbox for native code or external processes.

## 51. Extensions in Managed PostgreSQL

Managed database services may restrict extensions via an allowlist or provider-supported versions.

Some extensions require superuser, shared preloading, OS packages, or background workers that customers cannot install themselves.

Before designing a dependency on an extension:

- Check the provider's allowlist.
- Check supported versions.
- Check parameter groups/flags.
- Check extension creation privileges.
- Determine who installs native packages.
- Verify backup/restore and upgrade support.

Do not assume every extension in upstream PostgreSQL is supported on a managed service.

## 52. Extensions in Containers and Kubernetes

In containerized PostgreSQL:

- The image must contain the appropriate extension packages.
- Native libraries must match the PostgreSQL major version and architecture.
- Persistent volumes hold only data; they do not carry the image's package files.
- Image upgrades must verify extension binaries.
- Init scripts must be idempotent and must not grant superuser to applications.
- Security contexts should restrict OS privileges.

If using an operator, manage packages and `shared_preload_libraries` through operator-supported mechanisms. Never install packages manually into an ephemeral container and assume they survive restarts.

## 53. Controlled Extension Installation Workflow

A safe workflow:

1. Request use case and owner.
2. Review extension source, package, and security notes.
3. Verify PostgreSQL version/OS compatibility.
4. Install the package on staging.
5. Review the control file and SQL scripts.
6. Query `pg_available_extensions`.
7. Check `trusted`/`superuser` flags from the package source.
8. Select the deployment role.
9. Run `CREATE EXTENSION` in a test database.
10. Review owner, schema, grants, and functions.
11. Test application behavior.
12. Promote the package/config/database change through the change process.
13. Audit results and schedule updates.

## 54. Example: Installing a Trusted Extension

Suppose the package has been installed by the OS administrator and the extension is confirmed by the vendor as `trusted = true`.

The DBA grants temporary privileges:

~~~sql
GRANT CONNECT, CREATE ON DATABASE appdb TO app_extension_admin;
~~~

The deployment role connects to `appdb`:

~~~sql
CREATE EXTENSION approved_trusted_extension;
~~~

Verify:

~~~sql
SELECT
    extname,
    extversion,
    extowner::regrole,
    extnamespace::regnamespace
FROM pg_extension
WHERE extname = 'approved_trusted_extension';
~~~

Once completed, revoke privileges no longer needed:

~~~sql
REVOKE CREATE ON DATABASE appdb FROM app_extension_admin;
~~~

An extension having the `trusted` flag does not replace reviewing the package and installation script.

## 55. Example: An Extension Requiring Superuser

If an extension is untrusted and requires superuser, an application migration role cannot install it with just the database `CREATE` privilege.

The DBA or privileged deployment pipeline executes:

~~~sql
CREATE EXTENSION approved_native_extension;
~~~

Then grant permissions to use required objects to the runtime role:

~~~sql
GRANT USAGE ON SCHEMA extension_api TO app_runtime;
GRANT EXECUTE ON FUNCTION extension_api.calculate_value(integer)
TO app_runtime;
~~~

Schema/function names are illustrative; take exact object names from extension docs and the catalog.

Do not grant superuser to the application just to run a migration that installs an extension.

## 56. Post-Install Function Security Checks

~~~sql
SELECT
    n.nspname,
    p.proname,
    p.proowner::regrole,
    p.prosecdef,
    p.prolang,
    p.proconfig
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
ORDER BY n.nspname, p.proname;
~~~

In practice you can filter by the extension schema. Inspect function definitions using `pg_get_functiondef()` when appropriately authorized and review functions with `SECURITY DEFINER` or native languages.

## 57. Security Checklist

**Before Installation**

- Package source is approved.
- Version is compatible.
- Control file reviewed.
- `trusted` and `superuser` flags understood.
- Native libraries verified.
- Installation scripts reviewed.
- Dependencies and update path clear.

**Privileges**

- Application role does not have superuser.
- Database `CREATE` is not granted to `PUBLIC`.
- Trusted extension deployment uses a dedicated role.
- Untrusted extensions are controlled by DBAs.
- OS package installation is separated from database deployment.
- Server file/program roles are not granted arbitrarily.

**After Installation**

- Owner and schema are correct.
- Function grants are accurate.
- `SECURITY DEFINER`/`search_path` are safe.
- Languages and event triggers inspected.
- Monitoring/auditing has evidence.
- Update/rollback procedure documented.

## 58. Practical Exercises

### Exercise 1 — Extension

What is an extension?

**Hint:** a package of database objects managed by PostgreSQL as a single unit.

### Exercise 2 — CREATE EXTENSION

What does this command create?

**Hint:** installs the objects defined by the extension into the current database.

### Exercise 3 — Control File

What is the role of the control file?

**Hint:** metadata, version, and installation properties.

### Exercise 4 — trusted

What does `trusted = true` mean?

**Hint:** a user with the `CREATE` privilege on the database can install the extension via the trusted mechanism.

### Exercise 5 — Superuser

What privilege does an untrusted extension typically require?

**Hint:** superuser if required by the control file.

### Exercise 6 — CREATE Privilege

Is the database `CREATE` privilege the same as superuser?

**Hint:** no.

### Exercise 7 — Script Execution

Why do trusted extension installation scripts require careful review?

**Hint:** parts of the script can run as bootstrap superuser when special privileges are needed.

### Exercise 8 — Extension Ownership

Which catalog stores the extension owner?

**Hint:** `pg_extension`.

### Exercise 9 — OS Package

Who normally installs native extension packages?

**Hint:** an OS administrator or controlled deployment automation.

### Exercise 10 — Library Version

Why does a C extension require the exact PostgreSQL major version?

**Hint:** native API/ABI compatibility.

### Exercise 11 — Available Extensions

Which view lists extensions available to install?

**Hint:** `pg_available_extensions`.

### Exercise 12 — Extension Versions

Which view lists available extension versions?

**Hint:** `pg_available_extension_versions`.

### Exercise 13 — Schema

Is every extension relocatable?

**Hint:** no; check `extrelocatable`/control file.

### Exercise 14 — trusted Schema

Are a trusted extension and a trusted schema the same thing?

**Hint:** no, they are two separate concepts.

### Exercise 15 — ALTER EXTENSION

Which command updates an extension?

**Hint:** `ALTER EXTENSION ... UPDATE`.

### Exercise 16 — DROP CASCADE

Why is caution needed with `CASCADE`?

**Hint:** it can drop dependent objects.

### Exercise 17 — Native C

Where does a C extension run?

**Hint:** inside the PostgreSQL backend process.

### Exercise 18 — OS Privilege

Which privileges does native code inherit?

**Hint:** the privileges of the OS process running PostgreSQL.

### Exercise 19 — PL/pgSQL

What is the common trust status of this language?

**Hint:** trusted.

### Exercise 20 — PL/Python

Is `plpython3u` trusted or untrusted?

**Hint:** untrusted.

### Exercise 21 — pg_language

Which column indicates a trusted language?

**Hint:** `lanpltrusted`.

### Exercise 22 — SECURITY INVOKER

Whose privileges does a function run with by default?

**Hint:** the caller.

### Exercise 23 — SECURITY DEFINER

Whose privileges does the function run with?

**Hint:** the function owner.

### Exercise 24 — search_path

Why does `SECURITY DEFINER` need a safe `search_path`?

**Hint:** to prevent object substitution from schemas writable by untrusted users.

### Exercise 25 — PUBLIC EXECUTE

Why revoke `PUBLIC EXECUTE` on sensitive APIs?

**Hint:** to restrict who can call the function.

### Exercise 26 — Dynamic SQL

What is the safe way to bind input values in PL/pgSQL?

**Hint:** `EXECUTE ... USING`.

### Exercise 27 — COPY

Where does SQL `COPY` with a filename access files?

**Hint:** the server's filesystem.

### Exercise 28 — psql \copy

Where does `\copy` access files?

**Hint:** the client machine running `psql`.

### Exercise 29 — pg_read_server_files

What privilege does this role grant?

**Hint:** reading server files accessible to the PostgreSQL process.

### Exercise 30 — pg_execute_server_program

Why is this role sensitive?

**Hint:** it allows executing programs on the server through protected features.

### Exercise 31 — Event Triggers

Which group of events does an event trigger react to?

**Hint:** DDL events.

### Exercise 32 — Background Workers

Within what boundary does a background worker run?

**Hint:** the PostgreSQL server process lifecycle.

### Exercise 33 — Managed Databases

Why can't every extension be installed on a cloud managed service?

**Hint:** the provider restricts packages, privileges, preloading, and native code.

### Exercise 34 — Containers

Why must extension packages be inside the container image?

**Hint:** the data volume does not contain binaries/control files on its own.

### Exercise 35 — Least Privilege

Does the application runtime need superuser to use an extension?

**Hint:** usually not; grant only privileges on the required schemas/functions.

### Exercise 36 — Audit

Is `pg_extension` a history of who installed extensions?

**Hint:** no, it shows the current state.

### Exercise 37 — Supply Chain

Name two package control measures.

**Hint:** approved repositories, signatures/checksums, version pinning, source review.

### Exercise 38 — Resource Exhaustion

Which resources can a server-side function affect?

**Hint:** CPU, memory, locks, temp disk, I/O, and backend slots.

### Exercise 39 — Untrusted Languages

Who should be permitted to create functions in an untrusted language?

**Hint:** trusted DBAs/administrators.

### Exercise 40 — Deployment Workflow

List the key steps before and after `CREATE EXTENSION`.

**Hint:** review package/control/scripts, test on staging, install with an appropriate role, audit owner/grants, and test the application.

## 59. Frequently Asked Questions

### Does PostgreSQL guarantee a trusted extension is safe?

No. `trusted` is an attribute in the control file that governs installation privileges. It is not a security certification or a substitute for code review.

### Which extensions can a non-superuser install?

Extensions marked `trusted` when the user has the `CREATE` privilege on the database, along with meeting other required conditions.

### Why can a trusted extension script run as bootstrap superuser?

To perform installation operations requiring elevated privileges that normal users lack. Consequently, the installation script must be safe against users authorized to request installing the extension.

### Does CREATE on a database grant read access to all tables?

No. This privilege allows creating objects in the database; table read permissions remain controlled separately via ownership and grants.

### Does installing an extension require OS root permissions?

Not for `CREATE EXTENSION` in the database. However, installing packages/native libraries onto the server usually requires OS administrator privileges or equivalent automation.

### Can a superuser install any native library on their own?

No. A PostgreSQL superuser does not automatically have permission to write to the filesystem or install OS packages. The package must already exist on the server.

### Can a native C extension crash PostgreSQL?

Yes. Native code runs inside the backend process, and memory/segmentation faults can crash the backend or server.

### Is SECURITY DEFINER an untrusted language?

No. It is a mechanism where a function runs with owner privileges; trusted/untrusted is a property of a procedural language. The two concepts are independent but can combine to create risk.

### Why can search_path be a vulnerability?

If privileged code resolves an object from a schema where an attacker holds `CREATE`, the attacker can create a spoofed object to alter the code path or access data.

### Should an application role be given CREATE EXTENSION privileges?

Generally no. Separate the deployment role from the runtime role, and grant privileges only when needed for approved trusted extensions.

### Can pg_read_server_files be granted to an analyst?

Only with an approved use case and understanding of the scope. The role can read many files accessible to the PostgreSQL OS account, not just one specific CSV.

### How do \copy and COPY differ?

`\copy` is a `psql` meta-command and handles files on the client. SQL `COPY` with a filename or `PROGRAM` performs server-side access.

### Does installing an extension in one database make it appear in other databases?

No. Installing an extension is a per-database operation, even though the package/control files are available at the server level.

### Is ALTER EXTENSION UPDATE needed after pg_upgrade?

It depends on the extension and update paths. A major server upgrade does not automatically ensure extension SQL objects are at the latest version. Check vendor docs and the catalog.

### Does pg_extension record update history?

No. It shows the current version and owner. Use logs/auditing/change management to preserve history.

## 60. Summary

Essential inspection queries:

~~~sql
-- Extensions installed in the current database.
SELECT
    extname,
    extversion,
    extowner::regrole AS owner,
    extnamespace::regnamespace AS schema_name
FROM pg_extension
ORDER BY extname;

-- Extensions available to install from files on the server.
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
ORDER BY name;

-- Available extension versions.
SELECT
    name,
    version,
    installed
FROM pg_available_extension_versions
ORDER BY name, version;

-- Procedural languages and trusted flag.
SELECT
    lanname,
    lanpltrusted,
    lanowner::regrole AS owner
FROM pg_language
ORDER BY lanname;

-- Does the current role have the CREATE privilege on the database?
SELECT
    current_user,
    current_database(),
    has_database_privilege(
        current_user,
        current_database(),
        'CREATE'
    ) AS can_create;

-- SECURITY DEFINER functions.
SELECT
    n.nspname,
    p.proname,
    p.proowner::regrole AS owner,
    p.prosecdef,
    p.proconfig
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE p.prosecdef
ORDER BY n.nspname, p.proname;
~~~

Principles to remember:

1. An extension is a package of database objects managed as a single unit.
2. The control file declares version, dependencies, `relocatable`, `superuser`, and `trusted` flags.
3. A trusted extension can be installed by a non-superuser when the user holds the `CREATE` privilege on the database.
4. `trusted` is not a safety certification; installation scripts still require review.
5. Portions of a trusted script can run as bootstrap superuser when special privileges are needed.
6. The extension owner is the installer per PostgreSQL rules; verify in `pg_extension`.
7. Untrusted extensions typically require superuser when the control file sets `superuser = true`.
8. The `CREATE` privilege on a database is not equivalent to superuser.
9. OS package installation and `CREATE EXTENSION` are two separate operations.
10. Native libraries must match the PostgreSQL major version, architecture, and runtime dependencies.
11. `pg_available_extensions` lists extension packages visible to the server, not proof that they are safe.
12. Extensions can create SQL objects, `SECURITY DEFINER` functions, event triggers, and background workers.
13. C extensions run inside the PostgreSQL backend and inherit the process's OS privileges.
14. Trusted and untrusted procedural languages have different privileges and threat models.
15. `SECURITY DEFINER` executes with owner privileges; it requires a safe `search_path` and minimal grants.
16. Use parameter binding for dynamic SQL values and quote identifiers properly.
17. SQL `COPY` with a server filename/`PROGRAM` differs from `psql \copy` and carries server-side risks.
18. Predefined roles for reading/writing files or executing programs carry broad privileges.
19. Never grant superuser or server-file roles to the application runtime.
20. Control package provenance, updates, auditing, and compatibility.
21. Managed PostgreSQL and container images may restrict extensions.
22. Grant only required function/schema usage privileges after a DBA installs the extension.
23. Verify owner, schema, grants, and extension version after deployment.
24. Separate OS administrator, database superuser, extension deployment, and application runtime privileges.

Installation privilege diagram:

~~~text
OS administrator / package automation
                |
                v
    Install control files, SQL scripts,
        shared libraries and dependencies
                |
                v
          PostgreSQL server
                |
                v
         CREATE EXTENSION request
                |
                v
       Read extension control file
                |
          +-----+------+
          |            |
          v            v
      trusted=true   untrusted/default
          |            |
          v            v
 CREATE privilege?   Superuser required?
      |                   |
   +--+--+             +--+--+
   |     |             |     |
  Yes    No           Yes    No
   |     |             |     |
   v     v             v     v
Install  Denied       Install Denied
   |
   v
SQL installation scripts
   |
   v
Extension objects + owner/grants
   |
   v
Review functions, languages,
native code and server privileges
   |
   v
Grant least privilege to runtime role
~~~

**Conclusion:** PostgreSQL enables highly flexible database extensibility, yet extensions and server-side code reside within the system's trust boundary. Distinguish the `trusted` flag from a security certification, the database `CREATE` privilege from superuser, OS package installation from database extension installation, and SQL functions from native/untrusted code. A secure workflow begins with package provenance and script review, proceeds with a least-privilege deployment role, and concludes by verifying owner, grants, `search_path`, native libraries, and runtime permissions after installation.
