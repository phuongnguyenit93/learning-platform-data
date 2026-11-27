# Managing Extensions and Installation Privileges in PostgreSQL

PostgreSQL extensions are a mechanism for packaging additional features into a database. An extension can create functions, operators, data types, casts, indexes, views, tables, configuration parameters, or other objects to extend PostgreSQL's capabilities. Common examples include PostGIS for spatial data, `pg_stat_statements` for statement statistics, `pgcrypto` for cryptographic functions, and `uuid-ossp` for UUIDs.

Extension management requires understanding two parts: **the files installed on the PostgreSQL server** and **the extension objects created inside each database**. The `CREATE EXTENSION` command only works when the server already has the corresponding control file and installation scripts. If the extension includes C functions, the appropriate shared library must also exist on the server. These files are not installed via SQL alone.

Installation privileges must also be controlled. By default, many extensions require superuser privileges. Certain extensions marked as trusted by their authors allow users with the `CREATE` privilege on the database to install them under PostgreSQL's trusted extension mechanism. Privileges to create an extension, extension ownership, privileges to use objects after installation, and OS package management permissions are distinct privileges.

This lesson explains extension structure, how to check available extensions, install and update them, manage schemas/owners/dependencies, delegate privileges safely, handle backup/restore and HA, and mitigate risks when installing extensions from untrusted sources.

## 1. Learning Objectives

After this lesson, you can:

1. Explain what an extension is and why PostgreSQL uses extensions instead of installing loose objects.
2. Distinguish server-side packages/binaries from extensions installed inside a database.
3. Check available extensions via `pg_available_extensions`.
4. View versions and installation status via `pg_available_extension_versions` and `pg_extension`.
5. Understand control files, installation scripts, update scripts, and shared libraries.
6. Install extensions with `CREATE EXTENSION` and choose appropriate schemas and versions.
7. Understand trusted extensions, superuser requirements, and the database `CREATE` privilege.
8. Manage extension owners, object ownership, and grants.
9. Track dependencies and extension membership.
10. Update extensions with `ALTER EXTENSION UPDATE`.
11. Handle non-relocatable extensions, missing update paths, or missing server packages.
12. Safely remove extensions and evaluate the impact of `RESTRICT`/`CASCADE`.
13. Manage extensions across backups, restores, replication, failover, and major-version upgrades.
14. Apply least privilege and supply-chain security practices.
15. Build inventories, change controls, monitoring, and 80 practice exercises.

## 2. What Is an Extension?

An extension is a collection of database objects managed by PostgreSQL as a single unit. Instead of installing individual functions, types, operators, or tables with standalone statements, users install an extension with a version and metadata.

For instance, PostGIS provides numerous types and functions for storing, querying, and processing spatial data. `pg_stat_statements` provides query statistics views and related functions. Objects created by an extension are linked to that extension in the system catalogs.

### 2.1. Benefits

- Bundles multiple objects into one installation unit.
- Tracks extension versions.
- Manages dependencies between extensions.
- Supports updates via migration scripts.
- Helps `pg_dump`/`pg_restore` recognize objects belonging to an extension.
- Allows DBAs to inspect owners, schemas, and installation status.
- Reduces the risk of manually managing an inconsistent set of objects.

### 2.2. An Extension Is Not a Database-Wide Toggle

Extensions are installed inside a specific database. A cluster may contain multiple databases; if an extension is needed in three databases, `CREATE EXTENSION` must generally be executed in each of those three databases.

### 2.3. Extensions Are Not Necessarily Pure SQL

An extension may contain only SQL objects, or it may depend on a shared library written in C or another language. Some extensions also require background workers, preload configurations, or components outside PostgreSQL.

### 2.4. An Extension Is Not an OS Package

The OS package manager installs server-side files into the appropriate PostgreSQL directories. `CREATE EXTENSION` registers and creates objects inside the database. These two steps are related, not interchangeable.

## 3. Two Installation Layers to Distinguish

~~~text
Operating system / PostgreSQL distribution
    |
    +-- Extension control file
    +-- Installation SQL scripts
    +-- Update SQL scripts
    +-- Shared library (.so / .dll)
    |
    v
PostgreSQL server can discover extension
    |
    v
Connect to a database
    |
    +-- CREATE EXTENSION
    |
    v
System catalogs record extension
    |
    +-- SQL functions/types/operators/tables
    +-- Dependencies and ownership
    +-- Installed extension version
~~~

### 3.1. Server-Side Files

Files typically reside in PostgreSQL installation directories—such as extension control files, SQL scripts, and dynamic libraries. Exact paths depend on OS, package, PostgreSQL major version, build, and container image.

### 3.2. Database-Side Objects

After running `CREATE EXTENSION`, PostgreSQL creates objects from the installation script and records the extension in the `pg_extension` catalog.

### 3.3. Why Can CREATE EXTENSION Fail?

Possible causes:
- The extension package is not installed on the server.
- The extension was not built for the current PostgreSQL major version.
- A shared library dependency is missing.
- No installation script exists for the requested version.
- The user lacks required privileges.
- A required dependency extension is not yet installed.
- The managed service disallows that extension.
- Preload or restart requirements have not been met.

### 3.4. Every Server Node Needs Compatible Files

With physical replication, catalog/database changes replicate via WAL, whereas package files on the filesystem are not synchronized like database objects. Primary, standby, and DR nodes must all have matching extension binaries installed before promotion or invoking library-dependent functions.

## 4. Checking Available Extensions

The `pg_available_extensions` view lists extensions that the PostgreSQL server can discover via control files.

~~~sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
ORDER BY name;
~~~

### 4.1. Columns

- `name`: extension name.
- `default_version`: default version provided by the server package.
- `installed_version`: version currently installed in the current database; NULL if not installed.
- `comment`: short description from the control file.

### 4.2. Checking a Specific Extension

~~~sql
SELECT *
FROM pg_available_extensions
WHERE name = 'pg_stat_statements';
~~~

If no row returns, the server may lack the package/control file, or the extension is not in the paths PostgreSQL searches.

### 4.3. Availability Does Not Imply Permission to Install

`pg_available_extensions` only shows what the server detects. Managed services may enforce allowlists, role restrictions, or custom configuration requirements.

### 4.4. Default Version

`default_version` is the default version declared by the package/control file. It is not necessarily the latest version on the internet, the latest vendor-supported version, or the currently installed version.

## 5. Viewing Available Versions

`pg_available_extension_versions` lists versions for which the server has scripts along with installation attributes.

~~~sql
SELECT
    name,
    version,
    installed,
    superuser,
    trusted,
    relocatable,
    schema,
    requires,
    comment
FROM pg_available_extension_versions
ORDER BY name, version;
~~~

Some columns can differ by PostgreSQL major version; check the view definition on your running server before embedding queries in automation.

### 5.1. installed

Indicates whether that version row matches the version currently installed in the current database.

### 5.2. superuser and trusted

These two attributes describe installation privileges per the control file. `trusted` is not an independent guarantee from PostgreSQL that the extension is safe; it is a declaration by the extension author or package maintainer that DBAs must still review.

### 5.3. relocatable and schema

Indicate whether the extension can be installed in or moved to a different schema per the extension's rules.

### 5.4. requires

List of prerequisite extensions. Dependencies must be installed in compatible versions/paths before the main extension can function.

## 6. Checking Installed Extensions

`pg_extension` is the catalog recording installed extensions in the current database.

~~~sql
SELECT
    e.extname,
    e.extversion,
    e.extowner::regrole AS extension_owner,
    n.nspname AS extension_schema,
    e.extrelocatable,
    e.extconfig,
    e.extcondition
FROM pg_extension AS e
JOIN pg_namespace AS n
  ON n.oid = e.extnamespace
ORDER BY e.extname;
~~~

### 6.1. extname

Extension name, such as `pgcrypto` or `pg_stat_statements`.

### 6.2. extversion

Version currently installed in the database. This is what the catalog currently records, not the newest version in the package repository.

### 6.3. extowner

Role owning the extension. The owner is usually the role that ran `CREATE EXTENSION`, unless provisioning/ownership is managed separately. The owner holds management rights per PostgreSQL's privilege rules.

### 6.4. extnamespace

The schema recorded as the extension's primary schema. An extension may create objects in that schema; some extensions or objects may follow different layouts depending on scripts and the `relocatable` attribute.

### 6.5. extrelocatable

Indicates whether the extension can be moved to another schema using `ALTER EXTENSION SET SCHEMA`.

### 6.6. extconfig and extcondition

These catalog fields describe configuration tables and dump filter conditions declared by the extension. They control how `pg_dump` preserves extension configuration data.

## 7. Installing an Extension with CREATE EXTENSION

Basic syntax:

~~~sql
CREATE EXTENSION pgcrypto;
~~~

This instructs the server to locate the extension control file, check dependencies and privileges, and execute the installation script in the current database.

### 7.1. Installing into a Specific Schema

~~~sql
CREATE SCHEMA IF NOT EXISTS extensions;

CREATE EXTENSION pgcrypto
WITH SCHEMA extensions;
~~~

Specify a schema when the extension permits it and the schema already exists or can be created under appropriate privileges and semantics.

### 7.2. Installing a Specific Version

~~~sql
CREATE EXTENSION some_extension
WITH VERSION '1.4';
~~~

The version must exist in the server package with a matching installation script.

### 7.3. IF NOT EXISTS

~~~sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
~~~

`IF NOT EXISTS` avoids errors if the extension already exists, but does not verify that the existing extension matches the expected version, schema, or configuration. Always inspect `pg_extension` and catalog objects afterward.

### 7.4. Checking Extensions Before Installing

~~~sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
WHERE name IN ('pgcrypto', 'pg_stat_statements', 'uuid-ossp');
~~~

### 7.5. Installing via Migration Scripts

In production, place `CREATE EXTENSION` inside versioned migrations with reviews and rollback plans. Document the database, schema, requested version, owner, and server package version.

## 8. Extension Control Files

Control files provide metadata telling PostgreSQL that an extension is available, along with its default version, install scripts, privileges, and dependencies.

Filenames typically follow the pattern `extension_name.control` inside PostgreSQL's extension directory.

An illustrative control file:

~~~ini
comment = 'Example extension'
default_version = '1.2'
module_pathname = '$libdir/example_extension'
relocatable = true
superuser = true
~~~

This is solely a structural example; real values depend on the extension.

### 8.1. Common Attributes

- `comment`: extension description.
- `default_version`: default version.
- `module_pathname`: library path referenced in SQL scripts.
- `relocatable`: whether the extension can be moved between schemas.
- `schema`: fixed or default schema per extension design.
- `requires`: dependencies.
- `superuser`: whether superuser is required to install.
- `trusted`: whether non-superusers with database `CREATE` privilege can install via the trusted extension mechanism.
- `directory`: scripts directory if non-default.
- `encoding`: script encoding requirement if declared.
- `no_relocate`: schema restrictions for dependencies in certain designs.

Not every extension uses every attribute. Read the control file and documentation of the installed package.

### 8.2. Control Files Are Not SQL Scripts

The control file declares metadata. The installation SQL script creates objects and may reference a shared library. Having only a control file without scripts will still fail `CREATE EXTENSION`.

### 8.3. Control Files and Versions

PostgreSQL locates the installation script matching the chosen version, typically following the extension's naming convention. Package maintainers must provide consistent files.

### 8.4. Do Not Edit Control Files Arbitrarily

Editing control files directly in production causes package drift, gets overwritten on upgrades, and breaks assumptions about trust and permissions. Manage changes through reviewed package/build pipelines.

## 9. Installation Scripts and Update Scripts

An extension typically includes:
- An installation script for each supported version.
- Update scripts to transition between versions.
- A control file declaring metadata and default version.

Example filenames:

~~~text
example_extension.control
example_extension--1.0.sql
example_extension--1.1.sql
example_extension--1.0--1.1.sql
example_extension--1.1--1.2.sql
~~~

### 9.1. Installation Scripts

Scripts create objects such as functions, types, operators, tables, views, indexes, and privileges. Commands inside scripts execute within a transaction context per `CREATE EXTENSION` mechanics; operations that cannot run inside a transaction block require special design and do not fit standard extension install scripts.

### 9.2. Update Scripts

Update scripts describe schema and object changes between two extension versions. Do not assume PostgreSQL deduces conversion steps from version numbers alone.

### 9.3. Direct Update Paths

If the package ships a script from the current version to the target version, PostgreSQL can take that direct path. Without a direct path, a chain of intermediate paths may exist depending on the update script graph.

### 9.4. Version Naming

Extension version strings are labels defined by the extension author. Not every extension follows strict `x.y.z` semantic versioning.

### 9.5. Script Idempotency and Upgrade Safety

Extension authors are responsible for crafting scripts aligned with supported paths. DBAs should read release notes, test on a clone, and inspect data transformations before updating production.

## 10. Extension Installation Privileges

By default, `CREATE EXTENSION` requires superuser if the control file specifies `superuser=true` or the extension is not declared `trusted` under supported mechanisms. Some extensions allow non-superusers to install when the user holds the `CREATE` privilege on the database.

### 10.1. Superuser Requirement

Extensions may contain C code or perform operations requiring special privileges. PostgreSQL restricts installation by default to stop ordinary users from loading privileged code into the server.

### 10.2. Trusted Extensions

An extension can declare `trusted=true` in its control file. When set, a non-superuser holding `CREATE` privilege on the database can install the extension under the trusted extension mechanism.

Trust is a commitment by the extension author or package maintainer that the install script is safe to run under this mechanism. DBAs must still verify provenance, versions, and security history.

### 10.3. CREATE Privilege on the Database

The `CREATE` privilege on a database permits creating objects in the database per PostgreSQL's privilege model. It is broader than merely invoking a specific function.

~~~sql
GRANT CREATE ON DATABASE appdb TO extension_installer;
~~~

Grant only as needed and revoke once finished if the role does not need to retain it.

### 10.4. Schema Privileges

Creating objects inside a schema also involves `USAGE`/`CREATE` privileges on the schema, ownership, and extension rules. `CREATE` on a database does not automatically grant permissions on every schema.

~~~sql
GRANT USAGE, CREATE ON SCHEMA extensions TO extension_installer;
~~~

This example only applies when the user needs to create objects directly in that schema and the extension/DDL path allows it.

### 10.5. Do Not Grant Superuser Just to Install Any Extension

Use a controlled DBA/provisioning role or the trusted extension mechanism when appropriate. Never turn an application runtime role into a superuser.

## 11. Managing Installer Roles and Extension Owners

Separate the installer role from the application runtime role.

A common model:

| Role | Responsibility |
| --- | --- |
| platform_admin | Manages PostgreSQL server and packages |
| database_owner | Manages databases/schemas per policy |
| extension_installer | Installs/updates approved extensions |
| application_owner | Owns application objects |
| application_runtime | Reads/writes data per grants |
| monitoring_reader | Reads required statistics |

### 11.1. Extension Owner

The role owning an extension holds privileges to manage it. Avoid leaving production extensions owned by an individual developer long-term if their lifecycle should be operated by a stable role.

### 11.2. Transferring Ownership

Extension ownership can be transferred using `ALTER EXTENSION ... OWNER TO` in PostgreSQL versions supporting that syntax. Check version and permissions; internal extension objects carry their own ownership and dependency semantics, so do not assume every object owner changes identically.

### 11.3. Missing Owner Role

If an owner role is dropped, PostgreSQL may refuse because dependent objects remain. Transfer ownership or resolve dependencies before dropping roles.

### 11.4. Do Not Use Runtime Roles as Extension Owners

Application runtime roles need data access, not privileges to install, update, or drop extensions. Separating privileges limits the blast radius if application credentials leak.

## 12. Extension Schemas

Many extensions create objects in a dedicated schema or a schema chosen by the installer.

### 12.1. Dedicated Schema

Example:

~~~sql
CREATE SCHEMA extensions AUTHORIZATION database_owner;
CREATE EXTENSION pgcrypto WITH SCHEMA extensions;
~~~

A dedicated schema separates extension objects from application objects and makes grants clearer to manage.

### 12.2. Search Path

Applications can call functions without schema qualification if the extension schema is in `search_path`. This is convenient, yet can introduce shadowing risk if untrusted users hold `CREATE` privilege in an earlier schema.

~~~sql
SHOW search_path;
~~~

Prefer schemas with controlled ownership and `CREATE` privileges. Avoid placing schemas writable by untrusted users ahead of schemas holding trusted functions.

### 12.3. SET SCHEMA

For relocatable extensions, you can move the extension:

~~~sql
ALTER EXTENSION pgcrypto SET SCHEMA extensions;
~~~

This command is only valid if the extension permits relocation and the target schema meets prerequisites. It moves member objects according to extension semantics; not all extensions are relocatable.

### 12.4. Non-Relocatable Extensions

Some extensions require a fixed schema or place objects across multiple schemas. Do not force relocation by running `ALTER` on individual objects, as that can break extension membership.

### 12.5. Schema Grants

After installation, grant `USAGE` on the schema and necessary `EXECUTE`/`SELECT` privileges to application roles. Do not grant broad `CREATE` if the application only needs to call functions.

## 13. Dependencies Between Extensions

An extension can declare `requires` in its control file to depend on other extensions.

### 13.1. Checking Requirements

~~~sql
SELECT
    name,
    version,
    requires
FROM pg_available_extension_versions
WHERE name = 'target_extension';
~~~

### 13.2. CREATE EXTENSION ... CASCADE

PostgreSQL can automatically install needed dependencies with `CASCADE` if versions and permissions allow:

~~~sql
CREATE EXTENSION target_extension CASCADE;
~~~

Use with care. `CASCADE` can install additional extensions that the DBA did not anticipate. Review the dependency list beforehand.

### 13.3. Dependency Graph

An extension can depend on another extension, which in turn has its own dependencies. Inventory the graph before updating or dropping.

### 13.4. DROP Dependencies

`DROP EXTENSION` is blocked if objects outside the extension depend on its objects, unless `CASCADE` is used. `CASCADE` can drop dependent objects outside the extension. Inspect the plan/dependencies and take a backup beforehand.

### 13.5. pg_depend

The `pg_depend` system catalog stores dependency records between objects. It is a low-level catalog; use `pg_describe_object` or appropriate catalog views to interpret OIDs rather than manipulating it directly.

## 14. Updating Extensions

Update an extension inside a database using `ALTER EXTENSION UPDATE`.

~~~sql
ALTER EXTENSION pgcrypto UPDATE;
~~~

This uses the default version available in the server package if a valid update path exists.

### 14.1. Specifying a Target Version

~~~sql
ALTER EXTENSION some_extension UPDATE TO '2.1';
~~~

The target version must exist in the server package with a valid update path from the currently installed version.

### 14.2. Checking Versions Before and After

~~~sql
SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
~~~

Compare against `pg_available_extensions` and `pg_available_extension_versions`.

### 14.3. Update Paths

~~~sql
SELECT *
FROM pg_extension_update_paths('some_extension');
~~~

This function shows the update paths PostgreSQL can locate in the current package. Schema and output columns may vary by version.

### 14.4. Missing Update Path

If no update path exists:
- Check whether the package is missing intermediate scripts.
- Read the extension's release notes.
- Determine whether intermediate versions need to be installed.
- Review dump/recreate/migration guidance from the extension author.
- Never manually `UPDATE` `extversion` in the catalog.

### 14.5. Extension Updates vs. Package Updates

Installing a newer package on the server only makes new scripts and libraries available. The database extension version may stay on the old version until `ALTER EXTENSION UPDATE` is executed.

### 14.6. Can Updates Require a Restart?

`ALTER EXTENSION UPDATE` typically alters database objects per update scripts. If the extension requires a new shared library or preload configuration, a restart or reload may be required per its specific instructions. Package upgrades may also require a server restart depending on the extension and OS package.

## 15. Safe Extension Upgrade Procedure

1. Inventory extension names, versions, owners, schemas, and dependencies.
2. Check the PostgreSQL major version and package versions.
3. Read the extension's release notes and changelog.
4. Check update paths from the current version to the target.
5. Identify shared library, preload, and restart requirements.
6. Take a valid backup and verify the restore path.
7. Clone the database or use a staging environment.
8. Run `ALTER EXTENSION UPDATE` on the clone.
9. Verify objects, functions, types, indexes, and application behavior.
10. Measure lock, downtime, and performance impact.
11. Schedule a maintenance/change window if needed.
12. Install the compatible package version on all nodes.
13. Perform restarts/reloads as required.
14. Run the extension update in the target database(s).
15. Verify `pg_extension`, extension functions, and application smoke tests.
16. Monitor logs, query plans, and error rates.
17. Document the new version and rollback/recovery notes.

### 15.1. Multiple Databases

Extensions are installed per database. A cluster can have differing extension versions across databases if provisioning fell out of sync. Inventory every database individually.

### 15.2. Multiple Extension Dependencies

Update dependencies in an order consistent with the dependency graph and release notes. Avoid updating one dependency in a way that breaks another extension's compatibility.

### 15.3. Rollback

Not every extension update ships a downgrade script. Some schema or data transformations cannot be reversed via `ALTER EXTENSION UPDATE`. Prepare a backup restore or migration-specific rollback before updating.

## 16. Removing Extensions

Basic command:

~~~sql
DROP EXTENSION some_extension;
~~~

By default PostgreSQL uses `RESTRICT` behavior: it refuses to drop if external objects still depend on it.

### 16.1. DROP EXTENSION ... RESTRICT

~~~sql
DROP EXTENSION some_extension RESTRICT;
~~~

This is the safer option to surface dependencies blocking removal.

### 16.2. DROP EXTENSION ... CASCADE

~~~sql
DROP EXTENSION some_extension CASCADE;
~~~

`CASCADE` can drop objects depending on the extension's objects, including application-created tables, views, or columns. Never use `CASCADE` as a quick fix for dependency errors.

### 16.3. Removing the Package Does Not Remove Extension Objects

Uninstalling an OS package while the database still records the extension can leave functions unloadable or cause restores and upgrades to fail. Dropping the database extension and removing the server package are two distinct lifecycle steps.

### 16.4. Removing Extensions from Multiple Databases

You must run `DROP EXTENSION` in every database where the extension is installed. Check your inventory before removing packages.

### 16.5. Back Up Before Dropping

If the extension created tables containing data, or functions/types needed by applications, dropping it can destroy objects and data. Verify data ownership and export beforehand if needed.

## 17. Inspecting Objects Belonging to an Extension

`pg_depend` records dependency relationships, where extension member objects carry a specific dependency type.

You can join `pg_extension` and `pg_depend` for discovery; avoid relying on hard-coded OIDs.

~~~sql
SELECT
    e.extname,
    e.extversion,
    d.classid::regclass AS catalog,
    d.objid,
    d.objsubid,
    d.deptype
FROM pg_extension AS e
JOIN pg_depend AS d
  ON d.refclassid = 'pg_extension'::regclass
 AND d.refobjid = e.oid
WHERE d.deptype = 'e'
ORDER BY e.extname, catalog::text, d.objid;
~~~

### 17.1. deptype e

Dependency type `e` indicates the object is a member of the extension under catalog semantics. Other dependency types carry distinct meanings.

### 17.2. Do Not Modify Catalogs Directly

Never `UPDATE` or `DELETE` rows in `pg_extension` or `pg_depend` to force extension versions or ownership. Use PostgreSQL-supported DDL; manual catalog edits can corrupt database metadata consistency.

### 17.3. ALTER EXTENSION ADD/DROP

PostgreSQL provides `ALTER EXTENSION ... ADD/DROP` object commands to manage membership in certain cases. Use them only when you understand extension packaging and object ownership; they are not a general fix for a broken extension installation.

## 18. Extension Configuration Tables and pg_dump

Some extensions create tables holding configuration or data that must be dumped alongside the database.

### 18.1. pg_extension_config_dump

An extension installation script can call `pg_extension_config_dump` to register table data to include in dumps, optionally specifying a filter condition.

### 18.2. extconfig and extcondition

`pg_extension` stores metadata about configuration tables and conditions. Inspect:

~~~sql
SELECT
    extname,
    extconfig,
    extcondition
FROM pg_extension
ORDER BY extname;
~~~

### 18.3. Why Does This Matter?

`pg_dump` normally dumps the `CREATE EXTENSION` statement and handles config table data per this metadata. If a package/script failed to declare it properly, restores may lack needed configuration data or dump unexpected data.

### 18.4. Server Binaries Are Not Dumped

`pg_dump` does not bundle shared libraries, control files, or installation/update scripts. The target server must have compatible packages installed before restoring `CREATE EXTENSION`.

## 19. Extensions and Backup/Restore

### 19.1. pg_dump

A logical dump records `CREATE EXTENSION` commands and extension-declared config table data. It does not contain server-side packages.

~~~bash
pg_dump -Fc -d appdb -f appdb.dump
~~~

### 19.2. Restore

Before restoring:
1. Install compatible extension packages on the target.
2. Verify the target PostgreSQL major version.
3. Verify shared library dependencies.
4. Check extension versions and update paths.
5. Restore schema/data per plan.
6. Verify extension objects and application behavior.

### 19.3. Restoring into an Environment Without the Extension

`CREATE EXTENSION` in the dump will fail if the target lacks control/script files or the extension is unsupported. Do not ignore errors and declare the restore complete.

### 19.4. Physical Backups

Physical backups include database catalogs and relation files, but do not replace managing OS packages, shared libraries, and runtime dependencies. On standby or restore hosts, install matching packages before needing extension-dependent objects.

### 19.5. PITR

PITR recovers database state and extension catalog state via WAL. Binary and library files must still match the server version and recovered database state.

## 20. Extensions in Physical Replication and HA

### 20.1. Catalog Objects Replicate

When `CREATE`/`ALTER EXTENSION` runs on the primary, database catalog and object changes are logged to WAL and replicated to physical standbys.

### 20.2. Package Files Do Not Replicate

OS-level package files are not carried in WAL. Every node must have compatible extension binaries, control files, and scripts.

### 20.3. Promotion

Before failover, verify that standbys have all required shared libraries. If a standby promotes without the package or with a mismatched version, application queries invoking extension functions will fail.

### 20.4. Rolling Upgrades

During rolling upgrades or standby replacements, verify compatibility between extension binaries, PostgreSQL major versions, and database extension versions on each node.

### 20.5. Extension Preloading

If an extension requires `shared_preload_libraries`, configuration must be consistent across all nodes eligible to become primary. Some extensions load only at session/backend level; others require server preload.

## 21. Extensions in Logical Replication

Logical replication primarily streams row changes for published tables. It does not automatically replicate DDL or install server-side extensions.

### 21.1. Provisioning the Target

On the subscriber:
- Install compatible extension packages.
- Create required extensions.
- Create schemas, functions, types, and indexes per migration plan.
- Verify owners and grants.
- Ensure the target schema is compatible with incoming changes.

### 21.2. Extension Tables

If an extension creates tables included in a publication, row changes can replicate under logical replication rules. That does not mean full extension metadata or functions are transferred.

### 21.3. Version Mismatches

Source and target extension versions may differ if data types and behavior remain compatible and the migration is explicitly designed for it. Never assume every version pair is safe.

### 21.4. CDC Consumers

Logical decoding plugins are another extension-related component; packages, output plugins, and server configuration must be installed and verified where needed. A decoding plugin is not the same as a SQL extension installed inside every database.

## 22. shared_preload_libraries and Extensions

Some extensions must be loaded when the PostgreSQL server starts.

Example for `pg_stat_statements`:

~~~conf
shared_preload_libraries = 'pg_stat_statements'
~~~

After installing the package and restarting the server, create the extension in each database where statistics are needed:

~~~sql
CREATE EXTENSION pg_stat_statements;
~~~

### 22.1. Two Separate Steps

- `shared_preload_libraries` loads the module at server startup.
- `CREATE EXTENSION` creates the SQL objects and catalog metadata inside the database.

Missing either step can prevent the feature from working properly.

### 22.2. Restart Requirement

`shared_preload_libraries` requires a server restart to take effect. Running `ALTER SYSTEM` or editing the config followed only by a reload is not enough.

### 22.3. Multiple Libraries

Multiple modules can be configured as a comma-separated list. When editing, preserve existing required libraries and check configuration syntax and precedence.

### 22.4. Not Every Extension Needs Preloading

Read the extension's documentation. Do not add a module to `shared_preload_libraries` simply because you installed its package.

## 23. Extension Privileges After Installation

Installing an extension does not automatically mean every application role is permitted to use all objects according to your desired policy.

### 23.1. USAGE on the Schema

If extension objects live in a dedicated schema, roles need `USAGE` on the schema to resolve objects under appropriate privileges.

~~~sql
GRANT USAGE ON SCHEMA extensions TO app_runtime;
~~~

### 23.2. EXECUTE on Functions

Functions have their own ACLs. Check default privileges and grants after installation or update.

~~~sql
GRANT EXECUTE ON FUNCTION extensions.some_function(text)
TO app_runtime;
~~~

The function signature is illustrative; use the exact real overload.

### 23.3. Tables and Sequences

If an extension creates tables or sequences, grant `SELECT`/`INSERT`/`UPDATE` or `USAGE`/`SELECT` as required. Do not grant `ALL PRIVILEGES` by default.

### 23.4. PUBLIC Privileges

Some extension scripts create objects with grants to `PUBLIC`. Inspect ACLs and security policies; do not assume all extensions share identical default grants.

### 23.5. SECURITY DEFINER Functions

If an extension provides `SECURITY DEFINER` functions, check the owner, `search_path`, and documented behavior. This is a sensitive area because the function can execute with the owner's privileges.

## 24. Search Path and Extension Security

`search_path` governs how PostgreSQL resolves unqualified schema and object names.

### 24.1. Schema Shadowing

If an untrusted role holds `CREATE` privilege in a schema appearing before the schema holding extension functions, that role can create identically named objects and hijack name resolution in unsafe contexts.

### 24.2. Schema Ownership

Restrict `CREATE` on schemas containing trusted extension objects to trusted DBAs/owners. Application roles typically only need `USAGE` and object-specific privileges.

### 24.3. Qualify Object Names

In security-sensitive SQL, use schema-qualified function and table names where appropriate.

### 24.4. Function search_path

For custom `SECURITY DEFINER` code, set a safe `search_path` and schema-qualify dependencies. Never modify extension function definitions directly unless guided by the vendor.

## 25. Security and Supply Chain

Extensions run inside the PostgreSQL server process itself. Extensions containing C code or elevated privileges can deeply impact the database server.

### 25.1. Package Sources

Install only from:
- Official PostgreSQL distributions/repositories matching your deployment.
- Trusted OS vendor repositories.
- Official managed-service catalogs.
- Extension maintainer/release channels with clear provenance.
- Controlled internal artifact registries.

### 25.2. Checking Compatibility

Verify PostgreSQL major version, OS architecture, ABI, compiler/runtime dependencies, and extension release compatibility.

### 25.3. Security Advisories

Monitor CVEs, release notes, and extension security advisories. Extensions can have vulnerabilities independent of PostgreSQL core.

### 25.4. Least Privilege

Never grant superuser to application roles. Restrict database `CREATE`, schema `CREATE`, extension ownership, and signaling privileges.

### 25.5. Artifact Integrity

Pin package versions, verify repository signatures and checksums per OS/vendor procedures, maintain an SBOM or inventory, and govern artifact promotion across environments.

### 25.6. Production Change Control

Require:
- Ticket/change record.
- Extension name and version.
- Source/provenance.
- Compatibility evidence.
- Required privileges.
- Backup/restore validation.
- Rollback plan.
- Owner and approval.

## 26. Common Extensions and Operational Requirements

### 26.1. pg_stat_statements

Collects query statistics. Typically requires the package, `shared_preload_libraries`, and `CREATE EXTENSION` in each database where views/functions are used. Control query text visibility and stats reset semantics.

### 26.2. PostGIS

Provides geometry/geography types, spatial functions, and operator/index support. Requires packages compatible with PostgreSQL/OS; version upgrades may involve SQL scripts and data/object transformations. Check the PostGIS extension family/version per documentation.

### 26.3. pgcrypto

Provides cryptographic functions. Review key management and threat models; extension functions do not replace secure key/secret management architectures.

### 26.4. uuid-ossp

Provides UUID generation functions. Check package availability, privileges, and environment compatibility.

### 26.5. hstore

Provides a key/value data type and operators. Ensure schema/type compatibility during dump/restore and application migrations.

### 26.6. postgres_fdw

Provides a foreign data wrapper for remote PostgreSQL servers. Manage foreign servers, user mappings, network routes, and credentials; do not assume connection metadata is migrated merely because the extension is installed.

### 26.7. Citus and Architectural Extensions

Some extensions alter data distribution, planner/executor behavior, or cluster topology. They require deployment-specific installation and upgrade procedures; never apply a generic SQL extension runbook while ignoring vendor instructions.

## 27. Extensions on Managed PostgreSQL

Managed providers often restrict installable extensions because they control server packages, shared libraries, background workers, and the security surface.

### 27.1. Allowlists

Check provider documentation/consoles for:
- Supported extensions.
- Supported versions.
- Required parameter groups.
- Permitted installer roles.
- Extensions requiring restarts.
- Restrictions by instance tier, region, or engine version.

### 27.2. Parameter Groups

Some extensions require `shared_preload_libraries` or custom parameters. Managed services may require modifying a parameter group and triggering a reboot/failover.

### 27.3. Role Models

Managed superusers are often not true PostgreSQL superusers. Providers may grant specialized administrative roles and restrict certain commands. Never assume privileges on self-managed PostgreSQL match managed services.

### 27.4. Upgrade Windows

Extension versions may be controlled by the provider alongside engine upgrades. Check compatibility before upgrading the major engine version.

### 27.5. No Custom Binary Installation

If a provider disallows a package, `CREATE EXTENSION` cannot upload or install a shared library on its own. Pick a supported extension or a vendor-approved architectural alternative.

## 28. Extensions and PostgreSQL Major-Version Upgrades

When upgrading PostgreSQL across major versions, extension binaries must be compiled for the new major version and database extension objects must have valid upgrade paths.

### 28.1. Pre-Upgrade Inventory

Record extension name, `extversion`, owner, schema, dependencies, package versions, and preload settings for every database.

### 28.2. Target Packages First

Install matching extension packages for the target major version. Never reuse shared libraries compiled for an older PostgreSQL major version.

### 28.3. pg_upgrade

`pg_upgrade` checks several compatibility conditions and extension requirements. Read its output/logs and extension vendor guidance; never assume every extension upgrades seamlessly on its own.

### 28.4. Post-Upgrade SQL Updates

Some extensions require `ALTER EXTENSION UPDATE` after an engine upgrade to migrate database objects to the corresponding version.

### 28.5. Test on a Clone

Run a `pg_upgrade` or migration rehearsal with real extension packages, representative data volumes, and application queries.

## 29. Extensions and Containers

In containerized PostgreSQL, extension files are part of the server container image and filesystem.

### 29.1. Immutable Images

Bake version-pinned extension packages into the Docker image or build artifact. Never install packages manually inside a running container and expect files to survive container recreation.

### 29.2. Primary and Standby Images

Use compatible images across all nodes that may serve as primary or standby. Check architecture, library dependencies, and PostgreSQL major version.

### 29.3. Image Upgrades

When upgrading the PostgreSQL image, verify extension packages are present and compatible before starting the cluster or promoting a node.

### 29.4. Security Scanning

Scan base images and extension packages, pin versions, and update according to your vulnerability management process.

## 30. Extension Inventory and Auditing

Inventories should be gathered per database and per server node.

In-database query:

~~~sql
SELECT
    current_database() AS database_name,
    e.extname,
    e.extversion,
    e.extowner::regrole AS owner,
    n.nspname AS schema_name,
    e.extrelocatable
FROM pg_extension AS e
JOIN pg_namespace AS n
  ON n.oid = e.extnamespace
ORDER BY e.extname;
~~~

Server availability:

~~~sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
ORDER BY name;
~~~

### 30.1. Inventory Fields

Record:
- Cluster and environment.
- PostgreSQL version.
- OS or container image.
- Database name.
- Extension name and version.
- Owner and schema.
- Dependencies.
- Trusted/superuser/relocatable flags.
- Package version and provenance.
- Preload requirements.
- Approval/change reference.
- Last reviewed date.

### 30.2. Drift Detection

Compare extension inventories across dev, staging, production, and HA nodes. Spot missing extensions, version mismatches, differing schemas, wrong owners, or missing server packages.

### 30.3. Auditing Changes

Track `CREATE`/`ALTER`/`DROP EXTENSION` and package updates through change logs and audit systems. PostgreSQL logs can help trace DDL when logging policies are configured appropriately.

## 31. Post-Installation Extension Health Checks

After `CREATE EXTENSION` or `UPDATE`:
1. Check `pg_extension.extversion`.
2. Check extension schema and owner.
3. Confirm required shared libraries load cleanly.
4. Run a function/type/operator smoke test.
5. Check application role privileges.
6. Check logs for library load errors.
7. Confirm preload parameters and restarts took effect if required.
8. Check replication and standby compatibility.
9. Verify backup/restore paths.
10. Monitor query plans and performance if the extension affects the planner.

### 31.1. Checking Functions

Use `pg_proc` and namespace catalogs to list functions in the extension schema; do not assume every extension places all objects inside a single schema.

### 31.2. Checking Types

Use `pg_type`, `pg_namespace`, and extension dependencies to identify types created by the extension.

### 31.3. Application-Level Smoke Tests

An extension function succeeding in `psql` as the owner does not prove `application_runtime` has sufficient privileges. Test using the actual application role.

## 32. Troubleshooting: Extension Not Available

Common errors often report that the extension control file does not exist.

Causes:
- Package not installed.
- Package built for a different PostgreSQL major version.
- Extension not built for the OS or architecture.
- Extension missing from the managed-service allowlist.
- PostgreSQL running a different binary installation than the one the package targeted.
- Container image lacks the package.

Remediation:
1. Confirm `SHOW server_version`.
2. Identify the PostgreSQL installation/package path.
3. Check for the extension control file inside the exact extension directory.
4. Inspect package repositories and package names.
5. Verify the package build targets the current PostgreSQL major version.
6. On managed services, check the allowlist and provider policy.
7. Never copy files manually from another server without verifying ABI and dependencies.

## 33. Troubleshooting: Permission Denied on CREATE EXTENSION

Causes:
- Extension requires superuser.
- Extension is not marked `trusted`.
- User lacks `CREATE` on the database.
- User lacks required schema privileges.
- Managed service restricts the extension installer role.
- Extension dependencies require higher privileges.

Remediation:
1. Check `pg_available_extension_versions.superuser`/`trusted`.
2. Check database privileges.
3. Check schema ownership/`CREATE`.
4. Use a DBA/provisioning role per policy if the extension requires superuser.
5. Never grant permanent superuser to an application user just to bypass the error.

## 34. Troubleshooting: Shared Library Fails to Load

Causes:
- Missing `.so`/`.dll`.
- Library compiled for a different PostgreSQL version.
- Missing system library dependency.
- Incorrect `module_pathname`/control file.
- Library missing from the server's library path.
- Package upgrade missing a restart or an un-updated node.

Remediation:
1. Read server logs for the exact library path and error.
2. Verify the package on the exact host, node, or container.
3. Check architecture, ABI, and dependencies.
4. Inspect the control file and `module_pathname`.
5. Check preload settings if required by the extension.
6. Restart/reload as required.
7. Test on standbys and promotion targets.

## 35. Troubleshooting: ALTER EXTENSION UPDATE Fails

Causes:
- Missing update script/path.
- Extension package version lacks the target script.
- Incompatible dependency version.
- Update script encounters legacy data or object conflicts.
- Insufficient owner/superuser privileges.
- Extension in use or DDL lock contention.

Remediation:
1. Record the current `extversion`.
2. Check `pg_available_extension_versions`.
3. Query `pg_extension_update_paths`.
4. Read release notes and upgrade instructions.
5. Test on a clone or backup restore.
6. Identify required intermediate versions.
7. Never edit `extversion` manually in catalogs.
8. If an update fails midway, inspect transaction/error semantics and object state before retrying.

## 36. Troubleshooting: DROP EXTENSION Blocked

Causes:
- Application objects depend on extension functions, types, or operators.
- Views, generated columns, or indexes reference extension objects.
- Another extension depends on the extension being dropped.
- `CASCADE` policy is not approved.

Remediation:
1. Read the dependency error.
2. Identify dependent objects.
3. Use `pg_depend`/catalog inspection to build a dependency map.
4. Decide which objects to replace or retain.
5. Export needed data or configuration.
6. Use `CASCADE` only after reviewing every object that will be dropped and obtaining backup/approval.

## 37. Change Management Process

### Before Installing

- Define the business requirement.
- Verify extension support on PostgreSQL/OS/provider.
- Assess security, provenance, and CVEs.
- Define owner, schema, and privileges.
- Check dependencies and preload/restart needs.
- Assess impact on HA, replication, and backups.
- Test in development/staging.
- Create a change record and rollback plan.

### During Installation

- Install the package on the right nodes/images.
- Verify control files, scripts, and libraries.
- Configure preloading if needed.
- Restart/reload as required.
- Run `CREATE EXTENSION` with explicit version and schema.
- Record owner and grants.
- Run smoke tests.

### After Installation

- Update the inventory.
- Check standby nodes.
- Verify application permissions.
- Monitor logs and performance.
- Verify backup/restore.
- Record version and provenance.

## 38. Production Extension Update Procedure

1. Freeze the extension inventory and PostgreSQL version baseline.
2. Confirm the vendor/provider-supported target version.
3. Check control files and update paths on the server.
4. Read changelogs, CVEs, and breaking changes.
5. Identify DDL locks and data transformations.
6. Check dependencies between extensions.
7. Create a backup and verify restore.
8. Install the compatible package version across all HA nodes.
9. Perform required restarts if any.
10. Run `ALTER EXTENSION UPDATE` in the right database.
11. Verify `extversion`, schema, owner, and function signatures.
12. Run application smoke and regression tests.
13. Check replica health and failover readiness.
14. Update the inventory and change record.
15. Monitor logs and performance after the change.

## 39. Common Anti-Patterns

| Anti-pattern | Consequence | Correct Practice |
| --- | --- | --- |
| Running `CREATE EXTENSION` without installing the package | Missing control file or library | Install server package first |
| Confusing package upgrade with extension update | Database stays on old version | Run `ALTER EXTENSION UPDATE` along valid path |
| Installing extensions as superuser for convenience | Expands blast radius | Use installer role/approved process |
| Granting database `CREATE` to runtime roles | Runtime can create unintended objects | Separate provisioning and runtime roles |
| Assuming every extension is safe if `trusted` | Risks running unsafe code | Review control file and provenance |
| Installing packages only on primary | Failover node lacks library | Sync packages across all nodes |
| Ignoring managed allowlists | `CREATE EXTENSION` fails | Verify provider support |
| Running `IF NOT EXISTS` without verifying | Wrong version or schema | Inspect `pg_extension` |
| Updating without testing on a clone | Production update errors or long locks | Rehearse and back up |
| Editing `extversion` directly in catalog | Inconsistent metadata | Use `ALTER EXTENSION` |
| Unreviewed `DROP ... CASCADE` | Deletes application objects | Analyze dependencies first |
| Removing package before `DROP EXTENSION` | Functions fail to load | Follow proper lifecycle order |
| Ignoring `search_path` | Object shadowing/security risk | Lock schema ownership and qualify names |
| Forgetting preload/restart | Extension features fail to work | Check startup requirements |
| Forgetting target packages on restore | Restore `CREATE EXTENSION` fails | Provision target packages first |
| Assuming logical replication ships DDL | Subscriber lacks extension objects | Provision separately on target |
| Failing to pin package versions | Environment drift | Versioned artifacts and inventories |
| Ignoring CVEs | Old extension carries vulnerabilities | Track security lifecycle |

## 40. PostgreSQL Practice Exercises

Perform these in lab/staging or an appropriately authorized environment. Never install/remove extensions, grant superuser, or run `CASCADE` in production merely for experimentation.

1. **Inventory:** query `pg_available_extensions`.
2. **Installed:** query `pg_extension`.
3. **Versions:** list `pg_available_extension_versions`.
4. **Filter:** locate `pg_stat_statements` in available extensions.
5. **Owner:** display `extowner` as a role name.
6. **Schema:** display `extnamespace` and schema name.
7. **Relocatable:** find extensions with `relocatable` true/false.
8. **Trusted:** list `trusted` flags if supported by your version.
9. **Superuser:** compare superuser requirements.
10. **Requires:** inspect dependencies of an extension.
11. **Install:** install `pgcrypto` in a lab.
12. **Schema install:** install an extension into a dedicated schema.
13. **Version pin:** install a specific version if provided by the package.
14. **IF NOT EXISTS:** test the command and verify version afterward.
15. **Available vs installed:** distinguish package availability from database installation.
16. **Control file:** locate an extension's control file on the lab host.
17. **SQL scripts:** locate the corresponding installation script.
18. **Update scripts:** list version transition scripts.
19. **Shared library:** identify `module_pathname` for a C-based extension.
20. **Package manager:** identify which OS package provides an extension.
21. **Version compatibility:** verify the package targets the current PostgreSQL major version.
22. **Trusted install:** test installing a trusted extension as a non-superuser holding `CREATE` privilege in a lab.
23. **Untrusted install:** observe permission requirements for an extension requiring superuser.
24. **Database CREATE:** grant `CREATE` on a database to an installer role.
25. **Schema CREATE:** grant appropriate schema privileges and verify installation behavior.
26. **Least privilege:** create a dedicated `extension_installer` role.
27. **Runtime role:** confirm application roles lack `CREATE EXTENSION` privileges.
28. **Owner:** check the extension owner after installation.
29. **Ownership:** transfer ownership using supported syntax/version.
30. **Search path:** inspect `search_path` for the application role.
31. **Schema shadowing:** simulate object shadowing in a lab and analyze the risk.
32. **USAGE:** grant `USAGE` on the extension schema.
33. **EXECUTE:** grant `EXECUTE` on a specific function.
34. **ACL:** inspect privileges on extension objects.
35. **Dependencies:** inspect `requires` in available versions.
36. **CASCADE install:** install an extension with dependencies in a lab.
37. **pg_depend:** list member objects of an extension.
38. **Update paths:** call `pg_extension_update_paths`.
39. **Update:** upgrade an extension between two available versions in a lab.
40. **Version check:** confirm `extversion` after update.
41. **Missing path:** simulate a package missing an update script and inspect the error.
42. **Intermediate update:** test updating through an intermediate version if supported.
43. **Schema move:** test `ALTER EXTENSION SET SCHEMA` with a relocatable extension.
44. **Non-relocatable:** identify an extension that cannot change schemas.
45. **Config tables:** inspect `extconfig`/`extcondition`.
46. **Dump:** take a `pg_dump` and locate `CREATE EXTENSION` in the archive listing.
47. **Restore:** restore into a database that has compatible packages.
48. **Missing package:** simulate a restore when the target lacks extension files.
49. **Drop restrict:** test `DROP EXTENSION RESTRICT` when a dependent object exists.
50. **Drop cascade:** in a lab, observe which objects are removed by `CASCADE`.
51. **Preload:** configure `shared_preload_libraries` for `pg_stat_statements`.
52. **Restart:** verify the restart requirement for preloading.
53. **Create stats extension:** run `CREATE EXTENSION pg_stat_statements` in a lab database.
54. **Extension per database:** install an extension in two databases and compare catalogs.
55. **Physical standby:** install packages on a standby and verify failover readiness.
56. **Logical subscriber:** provision extension objects on a target before applying workload.
57. **Package drift:** compare extension package versions across nodes.
58. **Major upgrade:** inventory extensions before a PostgreSQL major-version upgrade.
59. **pg_upgrade:** run a rehearsal with compatible extension packages.
60. **PostGIS:** check version and smoke-test PostGIS in a lab if supported by packages.
61. **pgcrypto:** run a function test and evaluate key management boundaries.
62. **uuid-ossp:** test UUID functions in a lab.
63. **postgres_fdw:** install the extension and inventory foreign servers/user mappings.
64. **Managed service:** locate the provider's extension allowlist.
65. **Provider role:** identify managed-service extension installer privileges.
66. **CVE:** look up security advisories for an extension in use.
67. **Provenance:** record package source, version, and checksum.
68. **SBOM:** add extension packages to the software inventory.
69. **Image build:** add an extension package to a PostgreSQL container image.
70. **Image parity:** confirm primary and standby use images with matching extension binaries.
71. **Audit:** record `CREATE`/`ALTER`/`DROP EXTENSION` in a change log.
72. **Drift:** compare extension versions across dev/staging/production.
73. **Health:** create a post-install smoke test for functions/types.
74. **Privileges:** test an extension function using `application_runtime`.
75. **Failure:** investigate a missing control file error.
76. **Failure:** investigate a shared library load error.
77. **Failure:** investigate permission denied on `CREATE EXTENSION`.
78. **Failure:** investigate `ALTER EXTENSION UPDATE` with no update path.
79. **Runbook:** write a production extension install/update/drop procedure.
80. **Capstone design:** create an extension governance policy for a PostgreSQL fleet covering package provenance, allowlists, version pinning, owners/privileges, dependencies, HA/restore, security advisories, upgrade rehearsals, and auditing.

## 41. Extension Administration Checklist

### Availability and Compatibility

- [ ] Extension is in the server package/managed-service allowlist.
- [ ] Package matches PostgreSQL major version and OS/architecture.
- [ ] Control file, install scripts, and update scripts are complete.
- [ ] Shared library dependencies are installed.
- [ ] Required preload/restart settings are identified.
- [ ] Dependencies and update paths are verified.

### Privileges and Ownership

- [ ] Superuser/trusted requirements are verified.
- [ ] `CREATE` privilege is granted only to necessary installers.
- [ ] Schema `CREATE`/`USAGE` privileges are controlled.
- [ ] Extension owner is a stable operational role.
- [ ] Application runtime lacks privileges to install or drop extensions.
- [ ] Function/table/sequence grants follow least privilege.
- [ ] Search path and schema ownership are secure.

### Lifecycle

- [ ] Extension inventory is stored per database.
- [ ] Package versions are pinned/recorded.
- [ ] `CREATE EXTENSION` specifies intentional versions/schemas.
- [ ] `IF NOT EXISTS` is followed by verification.
- [ ] `ALTER EXTENSION UPDATE` is rehearsed.
- [ ] `DROP EXTENSION` dependencies are reviewed.
- [ ] System catalogs are never edited manually.

### HA, Backup, and Security

- [ ] Packages exist on all HA nodes.
- [ ] Restore targets have compatible packages.
- [ ] Logical subscribers are provisioned separately.
- [ ] Managed-service support is confirmed.
- [ ] CVEs/release notes are monitored.
- [ ] Artifact provenance and integrity are verified.
- [ ] Change records, backups, and rollback plans are ready.

## 42. Summary

Managing PostgreSQL extensions requires coordinating two lifecycles: server-side packages and database-side extension objects.

~~~text
APPROVE EXTENSION
       |
       v
VERIFY PACKAGE / VERSION / PROVENANCE
       |
       v
INSTALL FILES ON SERVER NODES
       |
       v
CONFIGURE PRELOAD / RESTART IF REQUIRED
       |
       v
CHECK DATABASE PRIVILEGES / SCHEMA
       |
       v
CREATE EXTENSION
       |
       v
VERIFY OWNER / VERSION / OBJECTS / GRANTS
       |
       v
MONITOR / BACKUP / UPGRADE / AUDIT
~~~

Key principles:

- **Package installation and `CREATE EXTENSION` are two separate steps.** The server needs control files, SQL scripts, and shared libraries before a database can install the extension.
- **Extensions are installed per database.** Inventory every database and never assume one installation applies cluster-wide.
- **`trusted` does not mean the extension underwent independent security auditing.** Verify authors, package provenance, CVEs, and security policies.
- **Superuser and `CREATE` privilege have different scopes.** Grant installation rights deliberately; keep application runtime roles minimal.
- **Owner, schema, and `search_path` are part of the security model.** Avoid schemas writable by untrusted roles and test with real application roles.
- **Package upgrades do not automatically update database extension catalog versions.** Use `ALTER EXTENSION UPDATE` and check update paths.
- **Not every extension is relocatable or has a downgrade path.** Rehearse on clones and maintain restore plans.
- **`DROP CASCADE` can remove application objects.** Analyze dependencies before removing an extension.
- **Binary files are not transferred by physical or logical replication like database objects.** Provision packages on HA nodes and subscribers appropriately.
- **Backups and restores require compatible extension packages.** `pg_dump` does not bundle server-side binaries.
- **Managed services have their own allowlists and role models.** Confirm provider support before designing migrations.
- **Extensions are code executing inside the database server trust boundary.** Pin versions, scan for vulnerabilities, audit changes, and govern artifacts.

A strong extension policy keeps a PostgreSQL fleet consistent across environments, restricts installation privileges, ensures controlled upgrades, and guarantees databases can be restored onto new servers without missing required libraries or extension objects.
