# Extensions, Installation Schemas, and the CREATE or ALTER EXTENSION Lifecycle

A PostgreSQL extension is a mechanism for packaging and managing a related set of database objects such as functions, operators, data types, casts, index operator classes, tables, views, and supporting components. Instead of manually executing multiple SQL files in the exact right order, an administrator can install an extension with a single `CREATE EXTENSION` command, inspect the active version in the catalog, and upgrade it using `ALTER EXTENSION UPDATE` when the extension provides a corresponding upgrade path.

An extension may consist solely of SQL objects or combine SQL with shared libraries written in C. Consequently, the extension lifecycle does not reside solely inside the database. Control/SQL script files and binary libraries must be installed in the proper PostgreSQL installation on the server; only then can the extension be registered within each database. An extension installed in database A does not automatically appear in database B, even if both databases reside in the same cluster. In an HA environment, nodes must have compatible packages and binaries so that standbys can replay WAL or a promoted node can continue operating.

The installation schema is an important part of extension design. Some extensions are relocatable, allowing the user to choose the schema during `CREATE EXTENSION` or change the schema later. Other extensions require a fixed schema because their SQL scripts have specific dependencies or references. Schema ownership, `search_path`, privileges, and trusted installation also affect security. Placing an extension into an appropriate schema helps manage namespaces, but it does not replace controlling `EXECUTE`/`USAGE` privileges and package provenance.

This lesson belongs to the **Scaling** chapter of the **Database Engine Relational PostgreSQL** module. It covers package structure, control files and version scripts, `CREATE EXTENSION`, schemas, dependencies, `ALTER EXTENSION UPDATE`, object management, backup/restore, upgrade compatibility, and operating extensions in production.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain which PostgreSQL objects an extension packages and how it differs from a schema.
- Distinguish between an extension package on the server and an extension installed in a database.
- Identify the control file, installation script, update script, and shared library.
- Use `pg_available_extensions`, `pg_available_extension_versions`, and `pg_extension` to inspect status.
- Execute `CREATE EXTENSION` with an appropriate schema/version.
- Understand relocatable, fixed schema, trusted, and superuser requirements.
- Control privileges, `search_path`, and extension dependencies.
- Upgrade an extension using `ALTER EXTENSION UPDATE`.
- Understand update paths, version labels, and SQL migration steps.
- Manage `SET SCHEMA`, `ADD`/`DROP` object, and `DROP EXTENSION`.
- Handle extension config tables, `pg_dump`/restore, and major PostgreSQL upgrades.
- Build an inventory, verify compatibility, and establish an extension lifecycle runbook.

## 2. What Is an Extension?

An extension is a unit managed by PostgreSQL in the catalog, representing the database objects installed from an extension package.

### 2.1. A Related Set of Objects

An extension can provide functions, types, operators, aggregates, casts, tables, views, indexes, operator classes, procedural languages, or other objects depending on the package.

### 2.2. A Registered Name and Version

After installation, PostgreSQL records the extension name, version, associated schema, and owner in the `pg_extension` catalog. Extensions can be inspected using SQL.

### 2.3. Dependency Tracking

Objects managed by an extension have a dependency on the extension. This allows PostgreSQL to know they belong to the same installation unit and handle them during updates/drops.

### 2.4. An Extension Is Not a Schema

A schema is a namespace containing objects. An extension is a package/lifecycle unit that manages a set of objects; an extension's objects may reside in one or more schemas depending on its design.

### 2.5. An Extension Is Not a Database-Wide Package Registry

A package may be present on the server, but `CREATE EXTENSION` must be run in each database that needs it. Each database has its own catalog entry and extension version.

## 3. Two Layers: Server Package and Database Installation

To use an extension, both the package files and the catalog installation are required.

~~~text
PostgreSQL server installation
  ├── extension control file
  ├── install SQL script(s)
  ├── update SQL script(s)
  └── optional shared library (.so / .dll)
             |
             | CREATE EXTENSION
             v
Database catalog
  ├── pg_extension row
  ├── extension member objects
  └── dependency records
~~~

### 3.1. Package Files

Control files and SQL scripts typically reside in the `extension` directory under the PostgreSQL shared data directory. Shared libraries reside in the PostgreSQL library directory.

### 3.2. SQL-Only Extensions

An extension containing only SQL may not need a shared library. The package still requires a control file and installation/update scripts.

### 3.3. C Extensions

An extension with C functions typically requires a shared library built for the matching PostgreSQL major version/ABI. Control/SQL files cannot replace the binary.

### 3.4. Installing a Package Does Not Equal Installing Database Objects

Installing an OS package or copying extension files only makes the extension available on the server. `CREATE EXTENSION` is what creates the objects and catalog record inside the database.

### 3.5. Installing in One Database Does Not Propagate to Others

If an application uses multiple databases, each database must have the extension installed separately. Inventory per database, not just per cluster.

## 4. Components of an Extension Package

A package typically has a control file and one or more SQL scripts.

### 4.1. Control File

A file named `extension.control` describes metadata and installation behavior: default version, comment, schema, relocatability, privileges, and dependencies.

### 4.2. Installation Script

A file named in the form `extension--version.sql` creates the objects for a specific version. This is the content executed when `CREATE EXTENSION` selects that version.

### 4.3. Update Scripts

Files in the form `extension--oldversion--newversion.sql` describe the changes to apply when upgrading between versions.

### 4.4. Shared Library

A C extension may provide a `.so` file on Unix-like systems or a `.dll` file on Windows. SQL functions reference the library via `MODULE_PATHNAME`/control metadata.

### 4.5. Documentation and Package Metadata

OS packages may provide a README, upgrade notes, license, and build metadata. These files assist operations but are not always stored by the PostgreSQL catalog.

## 5. Control File

The control file tells PostgreSQL how an extension can be installed and which version is the default.

Illustrative example of a control file:

~~~ini
comment = 'Example extension'
default_version = '1.2'
module_pathname = '$libdir/example'
relocatable = true
superuser = true
~~~

### 5.1. default_version

Specifies the version chosen if `CREATE EXTENSION` omits `VERSION`. It does not mean the extension automatically upgrades whenever a new package is installed.

### 5.2. comment

A short description of the extension, displayed in metadata views such as `pg_available_extensions`.

### 5.3. module_pathname

Provides the token/path so installation scripts can reference the shared library. SQL scripts commonly use the `MODULE_PATHNAME` placeholder in `CREATE FUNCTION`.

### 5.4. relocatable

Indicates whether the extension can be installed into/moved to a user-chosen schema. This value must match the design of the scripts and object dependencies.

### 5.5. superuser and trusted

`superuser` controls the superuser requirement during installation. `trusted` allows a user with the `CREATE` privilege on the database to install the extension according to trusted-installation rules; only safely designed packages should be declared `trusted`.

## 6. Other Metadata in the Control File

In addition to common fields, the control file can describe requirements and installation details.

### 6.1. requires

Lists required dependency extensions. PostgreSQL can install dependencies in the appropriate order when using `CASCADE` if package versions are compatible.

### 6.2. schema

Specifies a fixed installation schema for non-relocatable extensions or those with schema requirements. You cannot arbitrarily choose another schema if the control file requires a specific schema.

### 6.3. directory

Specifies the subdirectory containing extension scripts within `sharedir/extension`. The default is usually the standard `extension` directory.

### 6.4. encoding

Can restrict the database encodings supported by the extension scripts. Check control metadata when an extension is unavailable in the current database encoding.

### 6.5. Per-Version Control Files

A package may include control files for specific versions with metadata overrides. When investigating version behavior, inspect both the base control file and version-specific metadata if provided by the package.

## 7. Installation Scripts

The installation script creates the objects belonging to the extension in the database.

~~~sql
-- Example extension--1.2.sql
CREATE FUNCTION example_add(integer, integer)
RETURNS integer
AS 'MODULE_PATHNAME', 'example_add'
LANGUAGE C
IMMUTABLE
STRICT;
~~~

### 7.1. File Naming

The initial version script is typically named `extension--version.sql`. The version label is a string defined by the extension author; it does not necessarily follow semantic versioning.

### 7.2. Objects Belonging to the Extension

`CREATE EXTENSION` executes the script and registers the created objects as extension members via dependency metadata.

### 7.3. Schema Substitution

Extension scripts can use tokens such as `@extschema@` to reference the target schema. Do not hard-code `public` if the package needs to support selectable schemas.

### 7.4. Search Path Safety

Scripts should schema-qualify critical references and avoid relying on an uncontrolled `search_path`. Extension installation is a privileged operation and must be treated as code execution within the database.

### 7.5. Transaction Behavior

`CREATE EXTENSION` normally performs installation within a single transaction. Certain special SQL operations are disallowed inside transaction blocks, so extension authors must design scripts to fit the extension mechanism.

## 8. Update Scripts and the Version Graph

Upgrading an extension uses update scripts instead of re-running the installation script.

For example, a package might contain:

~~~text
example.control
example--1.0.sql
example--1.0--1.1.sql
example--1.1--1.2.sql
example--1.0--1.2.sql
~~~

### 8.1. Source and Target Versions

The update script filename identifies the starting version and the ending version. Its contents transition the schema/objects from the source state to the target state.

### 8.2. Direct Update Path

If a `1.0--1.2.sql` script exists, PostgreSQL can use the direct upgrade path from `1.0` to `1.2`.

### 8.3. Multi-Step Path

If no direct script exists, PostgreSQL can find a path through `1.1` provided the required scripts are present.

### 8.4. Version Labels

Version labels are identifiers chosen by the package author. Do not infer ordering solely through numeric or string comparison; rely on PostgreSQL update path metadata.

### 8.5. Missing Update Path

If there is no upgrade path from the installed version to the target, `ALTER EXTENSION UPDATE` cannot infer the migration automatically. A supporting package/script or a separate migration plan from the vendor/author is required.

## 9. Extension Catalog and Inspection Views

PostgreSQL provides views to distinguish extensions available on the server from extensions installed in the database.

~~~sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
ORDER BY name;
~~~

### 9.1. pg_available_extensions

Lists extensions whose package/control files are recognized by PostgreSQL in the server installation, along with the default and installed versions for the current database.

### 9.2. pg_available_extension_versions

Lists available versions and metadata such as `superuser`, `trusted`, `relocatable`, `schema`, and `requires`.

~~~sql
SELECT
    name,
    version,
    installed,
    superuser,
    trusted,
    relocatable,
    schema,
    requires
FROM pg_available_extension_versions
ORDER BY name, version;
~~~

### 9.3. pg_extension

Lists extensions currently installed in the current database:

~~~sql
SELECT
    extname,
    extversion,
    extowner::regrole AS owner,
    extnamespace::regnamespace AS extension_schema,
    extrelocatable
FROM pg_extension
ORDER BY extname;
~~~

### 9.4. Per-Database Scope

These views reflect the current database. For a cluster-wide inventory, you must connect to each database individually or use inventory automation.

### 9.5. Package Availability Does Not Guarantee Runtime Compatibility

An extension appearing in `pg_available_extensions` does not prove that its shared library can load or that the extension is compatible with the workload/version. Install and test in staging.

## 10. Checking Extension Update Paths

The `pg_extension_update_paths` function shows the update paths recognized by PostgreSQL from the existing scripts.

~~~sql
SELECT
    source,
    target,
    path
FROM pg_extension_update_paths('example')
ORDER BY source, target;
~~~

### 10.1. Path Metadata

`path` indicates the sequence of version transitions PostgreSQL can use. A `NULL` path generally indicates there is no valid update path between that pair of versions.

### 10.2. Pre-Maintenance Verification

Verify the current source version and intended target version before running `ALTER EXTENSION UPDATE`.

### 10.3. Direct and Indirect Paths

An update path can be a single direct script or a chain of multiple steps. The number of scripts and operations determines duration and locks.

### 10.4. Scripts on the Filesystem

SQL scripts must be present in the correct PostgreSQL installation. Installing a new package may add update paths, but it does not execute them automatically.

### 10.5. Do Not Edit the Catalog to Fake a Version

Do not directly `UPDATE pg_extension.extversion`. Use `ALTER EXTENSION UPDATE` so that objects and version metadata are modified consistently.

## 11. Basic CREATE EXTENSION

`CREATE EXTENSION` installs a package into the current database.

~~~sql
CREATE EXTENSION hstore;
~~~

### 11.1. Default Version

If `VERSION` is omitted, PostgreSQL uses `default_version` from the control file. Explicitly specify the version when deployments require exact pinning.

### 11.2. IF NOT EXISTS

~~~sql
CREATE EXTENSION IF NOT EXISTS hstore;
~~~

`IF NOT EXISTS` avoids an error when the extension already exists, but it does not verify that the installed version or schema matches expectations.

### 11.3. Specific VERSION

~~~sql
CREATE EXTENSION hstore VERSION '1.8';
~~~

The version must be available and have a corresponding installation script. Pinning the version makes migrations reproducible.

### 11.4. Specific SCHEMA

~~~sql
CREATE EXTENSION hstore WITH SCHEMA extensions;
~~~

Only works when the extension supports appropriate schema selection/relocation and the schema already exists.

### 11.5. CASCADE

~~~sql
CREATE EXTENSION extension_name CASCADE;
~~~

`CASCADE` allows installing missing required extensions according to dependencies. Review the dependency tree and package availability before using it.

## 12. CREATE EXTENSION and Required Privileges

Installation privileges depend on extension metadata and database/schema privileges.

### 12.1. CREATE Privilege on the Database

A regular user needs the `CREATE` privilege on the database to install a trusted extension; untrusted packages or those requiring superuser will need higher privileges.

### 12.2. Superuser Requirement

The control file can declare `superuser=true`. Many extensions require high privileges because they create C functions, access privileged facilities, or execute scripts with security implications.

### 12.3. Trusted Extensions

`trusted=true` allows a role with the `CREATE` privilege on the database to install the extension under trusted extension rules. The script runs with an elevated installation context, while objects are owned according to the invoking user semantics of a trusted install.

### 12.4. Schema Privileges

The user needs appropriate privileges to create objects in the target schema; schema ownership and `CREATE` grants must be designed beforehand.

### 12.5. Least Privilege

Do not grant permanent superuser privileges to an application role solely to install extensions. Use a time-bound, audited DBA/migration role, after which the application receives only the privileges it needs.

## 13. Trusted Extensions and Security

Trusted is a commitment by the extension package that its installation mechanism is safe for non-superuser users under documented conditions.

### 13.1. Do Not Mark Trusted Arbitrarily

Extension authors must review SQL scripts, functions, file access, external calls, and privilege boundaries before marking an extension as trusted.

### 13.2. Installation Scripts Run with Elevated Privileges

Trusted installation has special execution semantics. A buggy script can create objects with unintended permissions/ownership; only use packages from trusted sources.

### 13.3. Extension Update Scripts Are Also Code

`ALTER EXTENSION UPDATE` executes SQL migration scripts. Verify the package source/release notes and test on staging.

### 13.4. C Functions

C shared libraries execute inside the PostgreSQL server process. Bugs or malicious code can impact the entire server/host according to the process's privileges.

### 13.5. Security Review

Inventory extensions, versions, package sources, owners, privileges, shared libraries, and update cadence. Review vulnerability advisories before upgrading.

## 14. Choosing an Installation Schema

The schema serves as the namespace for extension objects and affects how applications call them.

### 14.1. Dedicated Schema

A schema such as `extensions` separates extension functions/types from application tables and reduces clutter in `public`.

~~~sql
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION hstore WITH SCHEMA extensions;
~~~

### 14.2. The public Schema

Many extensions are installed by default into `public` or a schema specified by the control file. `public` is convenient, but `CREATE` privileges and `search_path` must be controlled.

### 14.3. Pre-Existing Schema

Create the schema and configure its owner/grants beforehand. Do not rely on `CREATE EXTENSION` to create a namespace with unexpected security policies.

### 14.4. Schema Qualification

Applications should invoke extension functions/types using schema-qualified names if `search_path` may vary across sessions.

### 14.5. Multiple Extensions in One Schema

Multiple extensions can be installed in a single schema if the packages support it and there are no object-name conflicts. Using a separate schema per extension isolates namespaces but makes `search_path` management more complex.


## 15. Relocatable and Non-Relocatable Extensions

Schema mobility is determined by the control file and how extension scripts create objects.

### 15.1. Relocatable Extensions

The control file sets `relocatable=true`. The user can select a schema at installation time and, under certain conditions, move the entire extension to another schema.

### 15.2. Non-Relocatable Extensions

The control file sets `relocatable=false` or specifies a fixed schema. The extension may depend on a specific schema, multiple schemas, or object references that make relocation unsafe.

### 15.3. CREATE with Schema

For a relocatable extension, `WITH SCHEMA` can be used to pick the namespace. For a non-relocatable extension, a schema can only be specified if it matches the schema required by the control file.

### 15.4. Do Not Guess from the Extension Name

Not every extension can be installed into an arbitrary schema. Check `relocatable`/`schema` in `pg_available_extension_versions` and the package documentation.

### 15.5. Design Upfront

Select the schema, owner, grants, and `search_path` before installing. Moving a schema later may require locks and affect application references.

## 16. Search Path and Namespace Security

`search_path` affects how PostgreSQL resolves names of functions, types, operators, and relations.

### 16.1. Avoid Relying on Default public

Applications using extensions in a dedicated schema should use schema-qualified names or configure `search_path` explicitly.

### 16.2. Do Not Allow Untrusted Users CREATE in Schemas on search_path

If an untrusted user can create objects in a schema that precedes a trusted schema on `search_path`, they can shadow function/type names and cause unintended behavior.

### 16.3. Schema Owner

Grant `CREATE` on the extension schema only to necessary DBA/deployment roles. Runtime application roles typically only need `USAGE` and required object privileges.

### 16.4. Function Privileges

Installing an extension does not mean every role should have `EXECUTE` on every function. Review default privileges and function grants, especially for functions accessing files, networks, or the OS.

### 16.5. Inspecting search_path

~~~sql
SHOW search_path;

SELECT
    current_schema(),
    current_schemas(true);
~~~

Evaluate results under the application role, not solely from an admin session.

## 17. Extension Ownership and Object Membership

PostgreSQL tracks objects belonging to an extension via dependency records.

### 17.1. Extension Owner

`pg_extension.extowner` identifies the role that owns the extension. The owner affects `ALTER`/`DROP` extension privileges and metadata administration.

### 17.2. Member Objects

Objects created by extension scripts are attached via a dependency to the extension. When an extension is updated or dropped, PostgreSQL knows which objects belong to the package.

### 17.3. Dependency Type

In `pg_depend`, dependency type `'e'` denotes extension membership. This is an internal dependency mechanism; do not modify catalogs directly.

### 17.4. Do Not Arbitrarily Drop Member Objects

PostgreSQL normally rejects dropping an object that is a member of an extension. Use `ALTER EXTENSION ... DROP` on the object if you want to detach it from the package before managing it separately.

### 17.5. Extension Owner vs. Object Owners

Do not assume changing the extension owner automatically changes the owner of all member objects. Inspect object ownership and privileges separately if the security model needs to change.

## 18. Inspecting Objects Belonging to an Extension

You can query `pg_depend` joined with `pg_extension` to see objects managed by extensions.

~~~sql
SELECT
    e.extname,
    e.extversion,
    d.classid::regclass AS catalog,
    d.objid,
    d.objsubid,
    d.refclassid::regclass AS referenced_catalog,
    d.deptype
FROM pg_depend AS d
JOIN pg_extension AS e
  ON d.refclassid = 'pg_extension'::regclass
 AND d.refobjid = e.oid
WHERE d.deptype = 'e'
ORDER BY e.extname, catalog::text, d.objid;
~~~

### 18.1. Object Catalog

`classid` identifies the catalog containing the object, such as `pg_class`, `pg_proc`, or `pg_type`.

### 18.2. Object Identity

`objid` is the OID in the corresponding catalog. Use system functions like `pg_describe_object` to display human-readable names.

~~~sql
SELECT
    e.extname,
    pg_describe_object(d.classid, d.objid, d.objsubid) AS member_object
FROM pg_depend AS d
JOIN pg_extension AS e
  ON d.refclassid = 'pg_extension'::regclass
 AND d.refobjid = e.oid
WHERE d.deptype = 'e'
ORDER BY e.extname, member_object;
~~~

### 18.3. Version-Dependent Catalog Queries

Internal catalogs and object classes may change across major versions. Use queries for inspection, not as a substitute for official DDL APIs.

### 18.4. Do Not Update pg_depend Directly

Manually altering the dependency catalog can leave extension updates/drops inconsistent or cause database catalog corruption.

### 18.5. Pre-Migration Inventory

Record extension name/version/schema/owner and necessary member objects prior to an upgrade or restore rehearsal.

## 19. Extension Dependencies

An extension can declare required extensions in its control file.

### 19.1. requires Metadata

The control file lists the names of extensions required by the package. PostgreSQL checks dependencies during installation.

### 19.2. CREATE CASCADE

`CREATE EXTENSION ... CASCADE` allows installing missing dependencies. Do not use `CASCADE` without knowing which additional packages will be installed.

### 19.3. Version Compatibility

A dependency name may be required, but versions must still remain compatible. Read extension release notes and update scripts.

### 19.4. Dependency Chain

One extension may depend on another, forming a multi-layer chain. Inventory the entire graph before removing or upgrading a package.

### 19.5. Dropping a Dependency

You cannot drop an extension required by another extension without addressing the dependency. `CASCADE` can drop dependent extensions along with their objects; evaluate carefully.

## 20. CREATE EXTENSION and IF NOT EXISTS

`IF NOT EXISTS` helps make migration scripts repeatable in certain cases, but it can mask state drift.

### 20.1. Does Not Verify Version

If an extension is already installed at an older version, `CREATE EXTENSION IF NOT EXISTS` does not upgrade it. Use `ALTER EXTENSION UPDATE` separately.

### 20.2. Does Not Verify Schema

If the extension already exists in a different schema than expected, `IF NOT EXISTS` still only emits a notice. Verify `extnamespace`.

### 20.3. Does Not Verify Package Integrity

A successful command or notice does not prove that the shared library, binary package, and extension scripts are artifacts from the right source.

### 20.4. Migration Idempotency

Use `IF NOT EXISTS` for controlled bootstrapping, then assert version/schema/owner to detect drift.

### 20.5. Failure Handling

If `CREATE EXTENSION` fails mid-installation, transaction semantics normally roll back changes. Inspect the server log and catalog state before retrying.


## 21. ALTER EXTENSION UPDATE

`ALTER EXTENSION UPDATE` applies update scripts to transition an installed extension to another version.

~~~sql
ALTER EXTENSION hstore UPDATE;
~~~

### 21.1. Default Target

If `TO` is omitted, PostgreSQL uses `default_version` available in the current package.

### 21.2. Specific Target

~~~sql
ALTER EXTENSION hstore UPDATE TO '1.8';
~~~

The target version must have an update path from the currently installed version.

### 21.3. Updating One Extension at a Time

`ALTER EXTENSION UPDATE` upgrades only the specified extension. It does not automatically upgrade every extension in the database.

### 21.4. Unchanged Version

If the installed version is already the target/default, the command may report that no update is needed. Check `installed_version` and command output.

### 21.5. Do Not Modify extversion Directly

Only `ALTER EXTENSION UPDATE` executes migration scripts and updates membership/dependencies according to the lifecycle. Updating the catalog column via SQL is unsafe.

## 22. What Does an Update Script Do?

An update script is a migration between two extension versions.

### 22.1. Function Changes

The script may run `CREATE OR REPLACE FUNCTION`, alter signatures, or switch implementations to a new library.

### 22.2. Type/Operator Changes

It may add/modify types, casts, operators, and operator classes. These changes can affect application SQL and query plans.

### 22.3. Transforming Extension Data

If the extension has tables/configuration data, the update script may transform data. Duration, locks, and rollback semantics must be evaluated.

### 22.4. Dependency Changes

The script may add/drop objects or alter dependencies among extension objects. Extension authors must maintain proper ownership/dependency metadata.

### 22.5. Do Not Re-Run the Install Script

Do not run the new version's installation script via `psql` to simulate an update. Doing so can create duplicate objects or skip migration steps.

## 23. Update Paths and Pre-Upgrade Checks

Before updating, determine the installed version, available target, and path.

~~~sql
SELECT
    name,
    default_version,
    installed_version
FROM pg_available_extensions
WHERE name = 'hstore';

SELECT source, target, path
FROM pg_extension_update_paths('hstore')
ORDER BY source, target;
~~~

### 23.1. Source Version

Read from `pg_extension.extversion`. This is the actual state currently installed in the database.

### 23.2. Target Version

Read from `pg_available_extension_versions` or `default_version`. Do not assume the newest package version is always the appropriate target version.

### 23.3. Missing Path

If `path` is `NULL`, inspect package files, version-specific scripts, and release notes. Upgrading through an intermediate version may be required if a path is supported.

### 23.4. Test on a Clone

Run the update on a database clone with equivalent data size/extensions. Record duration, locks, errors, and post-update query behavior.

### 23.5. Production Sequencing

Choose an appropriate window, pause incompatible workloads if needed, and establish a backup/recovery point per change policy before risky updates.

## 24. ALTER EXTENSION SET SCHEMA

A relocatable extension can be moved to another schema using `ALTER EXTENSION SET SCHEMA`.

~~~sql
ALTER EXTENSION hstore SET SCHEMA extensions;
~~~

### 24.1. Relocatable Requirement

The extension must be declared relocatable. You cannot use this command to force a non-relocatable extension to move.

### 24.2. Member Objects in the Same Schema

Objects belonging to the extension must meet relocation conditions; if member objects reside in different schemas or have incompatible structures, the operation may be rejected.

### 24.3. Destination Schema

The target schema must exist and have appropriate permissions/ownership. Check for object name conflicts before moving.

### 24.4. Application References

Schema-qualified references, `search_path`, functions/views, and prepared statements may need updating. Applications using unqualified names will change behavior.

### 24.5. Post-Relocation Verification

Check `extnamespace`, object schemas, grants, and application smoke tests. Changing the schema is not a way to change extension ownership.

## 25. ALTER EXTENSION ADD and DROP Object

These two forms modify an object's membership in an extension; they do not create or delete the object.

~~~sql
ALTER EXTENSION extension_name ADD FUNCTION
    public.custom_helper(integer);

ALTER EXTENSION extension_name DROP FUNCTION
    public.custom_helper(integer);
~~~

### 25.1. ADD Object

`ADD` registers an existing object as a member of the extension. The object must be of a supported type and meet dependency/schema requirements.

### 25.2. DROP Object

`DROP` removes the object from extension membership. The object continues to exist in the database and can be managed independently.

### 25.3. Difference from DROP FUNCTION

`ALTER EXTENSION ... DROP FUNCTION` does not delete the function. `DROP FUNCTION` is the command that actually deletes the object and may require handling dependencies.

### 25.4. Use Cases

This can be used when an extension is forked/customized or when detaching an administrator-added object from the package's lifecycle.

### 25.5. Avoid Arbitrary Membership Edits

During an extension update, scripts may assume an object is still a member. Detaching an object can cause future updates to fail or skip updating that object.

## 26. DROP EXTENSION

`DROP EXTENSION` removes an extension and the objects that are members of it.

~~~sql
DROP EXTENSION hstore;
~~~

### 26.1. Default RESTRICT

If objects outside the extension depend on member objects, `DROP EXTENSION` defaults to `RESTRICT` and will reject the operation.

### 26.2. CASCADE

~~~sql
DROP EXTENSION extension_name CASCADE;
~~~

`CASCADE` can delete dependent objects and dependent extensions. This is a destructive operation; review the dependency graph carefully.

### 26.3. Schema Is Not Automatically Deleted

`DROP EXTENSION` removes member objects, but the schema containing them usually remains. Dropping the schema is a separate decision.

### 26.4. Data Loss

Tables belonging to an extension may contain essential data. `DROP EXTENSION` can delete those tables and their data as well; export/back up config data before removing.

### 26.5. Do Not Use DROP/CREATE to Update

Dropping and recreating can lose data, privileges, dependent objects, and configuration. Use `ALTER EXTENSION UPDATE` when supported by the package.

## 27. Extension Configuration Tables

Some extensions provide tables holding configuration data edited by administrators. Extension authors can mark them so `pg_dump` preserves the data.

### 27.1. pg_extension_config_dump

An extension installation script can call `pg_extension_config_dump(regclass, condition)` to register table data that should be dumped with the database.

~~~sql
SELECT pg_extension_config_dump(
    'public.example_settings',
    'WHERE setting_scope = ''user'''
);
~~~

### 27.2. Structure and Data

`CREATE EXTENSION` creates the table structure; `pg_dump` saves the registered config data. On restore, the extension package must be present to create the objects before data is loaded.

### 27.3. Condition Filter

The condition can restrict which rows are dumped—for example, saving only user-modified configuration instead of built-in defaults.

### 27.4. Not Every Extension Table Is Dumped Like an Application Table

Extension member tables do not automatically have all their data dumped. Check the extension documentation and config dump registration.

### 27.5. Restore Verification

Test dump/restore on staging and verify the extension version, config table structure, retained rows, and object dependencies.

## 28. Backing Up and Restoring Databases with Extensions

Backups must reproduce both the extension package requirements and the database installation state.

### 28.1. pg_dump

`pg_dump` emits `CREATE EXTENSION` commands for installed extensions rather than dumping all member object definitions as user-created objects.

### 28.2. Package Availability on Target

Before restoring, install compatible extension packages and shared libraries on the target PostgreSQL server. If a package is missing, `CREATE EXTENSION` during restore will fail.

### 28.3. Version Behavior

A restore may require a version compatible with the dump or an appropriate update path. Check target extension versions and release notes.

### 28.4. Roles and Schemas

Create required roles/owners/schemas/privileges in restore order. Extension ownership and schema grants can affect `CREATE EXTENSION`.

### 28.5. Restore Test

Restore into an isolated database/cluster and verify extension versions, schemas, member objects, config data, and application queries.

## 29. Major PostgreSQL Upgrades and Extension Packages

The extension lifecycle is a distinct part of a major upgrade.

### 29.1. Target-Version Packages

Install extension packages built for the target PostgreSQL major version. C library binaries from an older major version usually cannot be used directly with the new server.

### 29.2. Control/SQL Files

Ensure the target installation has the control files, installation scripts, and update scripts needed for the extension versions.

### 29.3. pg_upgrade

`pg_upgrade` migrates the database cluster, but extension package/binary compatibility and SQL extension version updates are tasks that must be handled according to the upgrade procedure.

### 29.4. ALTER EXTENSION UPDATE

Once the target server and packages are ready, run `ALTER EXTENSION UPDATE` for extensions needing SQL-level version upgrades. Do not assume a major upgrade automatically updates all extensions.

### 29.5. Standby/HA Nodes

Install the same package versions on all nodes eligible to run PostgreSQL. If a node is promoted while missing a shared library or with a version mismatch, extension functions may fail.

## 30. Shared Preload Libraries and Extension Initialization

Some extensions require server configuration before `CREATE EXTENSION`.

### 30.1. shared_preload_libraries

For example, `pg_stat_statements` must be added to `shared_preload_libraries` and PostgreSQL restarted before full functionality can be used.

~~~conf
shared_preload_libraries = 'pg_stat_statements'
~~~

### 30.2. Restart Requirement

`shared_preload_libraries` is a setting that requires a restart. Check `pending_restart` and execute according to the maintenance plan.

### 30.3. CREATE EXTENSION After Preload

After the server restarts and the library is loaded, connect to each database needing statistics and run:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

### 30.4. Cluster-Level Setting, Database-Level Installation

Preloading configures the server/cluster, whereas `CREATE EXTENSION` creates SQL objects within a single database. The two steps have different scopes.

### 30.5. Extension-Specific Settings

Read documentation regarding GUCs, background workers, hooks, memory requirements, and monitoring. Not every extension requires preloading.


## 31. Installing Extension Packages at the OS Level

Extensions not bundled with the PostgreSQL distribution require packages matching the OS, PostgreSQL version, and architecture.

### 31.1. Inspecting PostgreSQL Installation Paths

`pg_config` provides the directories used by the PostgreSQL build/installation.

~~~bash
pg_config --version
pg_config --sharedir
pg_config --pkglibdir
pg_config --includedir-server
~~~

### 31.2. Extension Control Directory

Control files and SQL scripts are typically placed under `sharedir/extension` or a directory specified by package/control metadata.

### 31.3. Shared Library Directory

C extension libraries typically reside under `pkglibdir` or the corresponding library path. Filenames and ABI must be compatible with the server.

### 31.4. Package Manager

Install extensions using a trusted OS/vendor package repository or a controlled build process. Avoid copying loose files from a server of unknown build/version.

### 31.5. Restart and Library Loading

If an extension requires `shared_preload_libraries` or a module is already loaded in backend processes, follow restart/reconnect requirements. Replacing a binary on disk does not ensure all running backends automatically load the new code.

## 32. Installing Extensions from Source

Some extensions must be built from source instead of a prebuilt package.

### 32.1. Source Compatibility

Choose a source release compatible with the PostgreSQL major version, compiler, OS libraries, and extension dependencies.

### 32.2. Build Toolchain

C extensions typically require PostgreSQL server development headers, a compiler, make/build system, and external libraries.

### 32.3. Correct Target pg_config

When building, ensure `pg_config` points to the target PostgreSQL installation. If multiple major versions exist on the machine, using the wrong `pg_config` can install binaries into the wrong directory.

### 32.4. Reproducible Builds

Record the source version/commit, build flags, compiler, dependency versions, and artifact checksums. Build separately for each target platform/major version when required.

### 32.5. Deployment Consistency

Bundle control files, SQL scripts, and shared libraries into the same release artifact/package. Install uniformly across primary, standby, replicas, and DR nodes.

## 33. Extension Inventory for a Database

An inventory shows which extensions are installed, who owns them, and which schemas they use.

~~~sql
SELECT
    e.extname,
    e.extversion,
    e.extowner::regrole AS owner,
    n.nspname AS schema_name,
    e.extrelocatable,
    a.default_version,
    a.comment
FROM pg_extension AS e
JOIN pg_namespace AS n
  ON n.oid = e.extnamespace
LEFT JOIN pg_available_extensions AS a
  ON a.name = e.extname
ORDER BY e.extname;
~~~

### 33.1. Installed Version

`extversion` is the SQL-level version currently installed in the database.

### 33.2. Default Version

`default_version` reflects the default package version currently available on the server. It may differ from the installed version.

### 33.3. Owner/Schema

Record the owner and namespace to detect extensions installed under a role or schema that violates policy.

### 33.4. Availability Gap

If an installed extension does not appear in `pg_available_extensions`, package files may be missing or the server installation has changed. Do not delete the catalog entry to mask the error.

### 33.5. Multi-Database Inventory

Run the query against each database and aggregate externally. A cluster may have different extensions across databases.

## 34. Server-Level Extension Package Inventory

Available extensions do not equate to extensions installed in a database.

### 34.1. List Available

~~~sql
SELECT name, default_version, comment
FROM pg_available_extensions
ORDER BY name;
~~~

### 34.2. List All Versions

~~~sql
SELECT
    name,
    version,
    installed,
    superuser,
    trusted,
    relocatable,
    schema,
    requires
FROM pg_available_extension_versions
ORDER BY name, version;
~~~

### 34.3. Installed vs. Available

`installed=true` indicates the version installed in the current database. Multiple versions may be available simultaneously, but only one version of an extension is installed in a database.

### 34.4. Missing Package

If an extension does not appear, check the OS package, `sharedir` path, file permissions, server process installation, and logs. Restarting does not automatically install a missing package.

### 34.5. Managed Services

Cloud-managed PostgreSQL only supports a provider-approved set of extensions and versions. Check allowlists/parameter groups and service documentation.

## 35. Procedure for Installing a New Extension

A safe deployment requires packages, permissions, schemas, and testing before enabling for applications.

1. Identify the requirement and the exact extension package.
2. Check the source, license, security advisories, and PostgreSQL compatibility.
3. Install the package into the right server installation and all HA/DR nodes.
4. Verify control files, SQL scripts, shared libraries, and available versions.
5. Determine `superuser`/`trusted` requirements and dependencies.
6. Create the schema/owner/grants if needed.
7. Apply server settings/preload and restart if required by the extension.
8. Run `CREATE EXTENSION` in the proper database/version/schema.
9. Verify the catalog, objects, privileges, and representative function behavior.
10. Update the inventory, backup/restore runbook, and monitoring.

### 35.1. Install in Staging First

Test the extension on the same PostgreSQL major version and OS as production. Inspect performance, locks, background workers, and failure behavior.

### 35.2. Pin the Version

In migration/deployment artifacts, specify the version explicitly when reproducibility matters.

### 35.3. Schema Policy

Do not let schemas depend on an implicit `search_path` if the application requires a stable namespace.

### 35.4. Post-Install Grants

Review object privileges; grant only `USAGE`/`EXECUTE`/`SELECT` as required by application roles.

### 35.5. Operational Readiness

Add the extension to the inventory, patch schedule, backup/restore tests, HA node package list, and security review cadence.


## 36. Procedure for Upgrading an Extension

Upgrading an extension requires distinguishing package deployment from SQL catalog migration.

1. Read the extension's release notes and compatibility matrix.
2. Identify the current `extversion` in each database.
3. Deploy the target package/control/scripts/shared library onto server nodes.
4. Inspect `pg_available_extension_versions` and `pg_extension_update_paths`.
5. Test `ALTER EXTENSION UPDATE` on a clone/staging environment.
6. Assess locks, runtime, data migrations, and restart/preload requirements.
7. Establish a backup/recovery point and schedule an appropriate maintenance/change window.
8. Run `ALTER EXTENSION UPDATE` to the target version.
9. Verify `extversion`, objects, privileges, function behavior, and query plans.
10. Monitor logs, application errors, replication, and performance.

### 36.1. Package First, SQL Update Second

If the update scripts do not exist on the server, PostgreSQL cannot perform the update. Deploy the target package before running `ALTER EXTENSION`.

### 36.2. Binary and SQL Versions

The shared library package version and the SQL extension version may have separate lifecycles. Follow the vendor procedure to avoid SQL objects calling an incompatible binary API.

### 36.3. Database-by-Database

If the extension is installed across multiple databases, update each database according to the sequence/maintenance policy. Track which databases are completed.

### 36.4. Restart Requirement

If the extension changes a preload library or needs to load a new binary, perform the required restart. `ALTER EXTENSION UPDATE` does not restart PostgreSQL automatically.

### 36.5. Post-Update Validation

Test critical functions, operators, indexes, custom types, query plans, grants, and background workers.

## 37. Extension Compatibility Matrix

Before deployment, verify the server, package, extension SQL version, and dependencies.

| Dimension | What to Confirm |
|---|---|
| PostgreSQL major | Does the extension support the target major version? |
| PostgreSQL minor | Are there specific bug fixes or requirements? |
| OS/architecture | Does the package/binary match the platform? |
| Shared library ABI | Built against the right target PostgreSQL? |
| Extension SQL version | Are required install/update scripts present? |
| Dependencies | Are required extensions/libraries compatible? |
| Collation/type | Are there assumptions about ordering/types? |
| HA/DR | Do all nodes have the same packages and settings? |
| Managed service | Does the provider allow the extension/version? |
| Application | Is SQL/API behavior backward compatible? |

### 37.1. Do Not Look Only at Package Version

An OS package may be installed, yet the binary could be built for the wrong PostgreSQL major version or lack a runtime dependency.

### 37.2. Check Release Notes

Read breaking changes, deprecated functions, renamed objects, new defaults, and migration requirements.

### 37.3. External Dependencies Outside the Database

Some extensions depend on OS libraries, executable tools, locale packages, or external services. Installing the SQL package alone is not enough.

### 37.4. Test Rollback

Determine whether package downgrade is supported and whether the SQL update has a reversible path. Do not assume `ALTER EXTENSION UPDATE` has a downgrade script.

### 37.5. Provider-Specific Behavior

Managed services may prohibit shared library loading, superuser operations, or specific extension versions. Design according to actual capabilities.

## 38. Extensions on an HA Cluster

Extension packages and settings must be consistent across nodes eligible to run PostgreSQL.

### 38.1. Primary and Standby

Standbys replay WAL for extension-created objects, but upon promotion, functions backed by a C library require compatible binaries on the new node.

### 38.2. Install Packages Uniformly

Install the same compatible package versions on the primary, standbys, and DR nodes before failover can occur.

### 38.3. Shared Preload Settings

If an extension requires preloading, configure it consistently across nodes. After failover, the new node must have the required settings and binaries.

### 38.4. Extension SQL Update

`ALTER EXTENSION UPDATE` runs on the primary/database. Standbys receive catalog/object changes via WAL; do not run the same SQL update independently on a physical standby.

### 38.5. Failover Validation

After promotion, verify library loading, function execution, background workers, logs, and extension versions.

## 39. Extensions and Logical Replication

Logical replication can replicate database objects/data, but it does not automatically install extension packages on the subscriber.

### 39.1. Schema Prerequisites

Create the required extensions/schemas/types/functions on the subscriber per the deployment procedure before replicated tables or application queries depend on them.

### 39.2. DDL Propagation

Logical replication does not automatically replicate all DDL. Extension install/update operations must be coordinated separately on publisher and subscriber.

### 39.3. Data Types/Operators

If replicated tables use extension types/operators, the subscriber must have compatible definitions before applying changes.

### 39.4. Version Alignment

Publisher and subscriber may run different versions during upgrade scenarios, but logical data representations and function semantics must be compatible.

### 39.5. Cutover

Before switching the application to the subscriber, verify the extension inventory, versions, schemas, functions, operators, and indexes.

## 40. Extensions in Backup/PITR and Disaster Recovery

The recovery target needs packages and extension state compatible with the database backup/WAL.

### 40.1. Base Backups Do Not Bundle OS Extension Binaries

Physical backups contain the data directory, but they do not replace installing the right server binaries/shared libraries on the restore host.

### 40.2. WAL Replay

If WAL contains catalog/object changes from an extension update, the target needs compatible server binaries/packages so the database can start and functions work after recovery.

### 40.3. PITR Target

Restoring to a point before/after an extension update requires packages/runtime compatible with that state. Maintain a version inventory for recovery points.

### 40.4. DR Rehearsal

Restore physical/logical backups onto a DR environment and test extension functions, C libraries, preload settings, config data, and application queries.

### 40.5. Recovery Documentation

Record package repositories/artifacts, versions, checksums, installation steps, settings, and SQL extension versions alongside backup metadata.


## 41. Example: Installing the hstore Extension into a Dedicated Schema

This example illustrates an SQL/data-type extension installed in an application database.

### 41.1. Check Availability

~~~sql
SELECT name, default_version, installed_version
FROM pg_available_extensions
WHERE name = 'hstore';
~~~

### 41.2. Create Schema

~~~sql
CREATE SCHEMA IF NOT EXISTS extensions
AUTHORIZATION db_owner;
~~~

### 41.3. Install Extension

~~~sql
CREATE EXTENSION hstore
WITH SCHEMA extensions
VERSION '1.8';
~~~

The example version must exist in the server's package. If the package has a different version, choose an actually supported version.

### 41.4. Verify Installation

~~~sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS schema_name,
    extrelocatable
FROM pg_extension
WHERE extname = 'hstore';
~~~

### 41.5. Verify Function/Type Usage

Use schema-qualified names in application SQL when needed to avoid `search_path` dependence. Grant appropriate privileges on the schema and objects per policy.

## 42. Example: Installing pg_stat_statements

`pg_stat_statements` illustrates the difference between server-level preloading and database-level extension installation.

### 42.1. Configure the Server

Add the library to `shared_preload_libraries` in your managed configuration source:

~~~conf
shared_preload_libraries = 'pg_stat_statements'
~~~

If the setting already contains other libraries, keep them in the list rather than overwriting them.

### 42.2. Restart PostgreSQL

This setting requires a restart. Check `pending_restart` and execute according to the maintenance procedure.

### 42.3. Install in the Database

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

Repeat in each database where the extension's views/functions are needed.

### 42.4. Configure Tracking

Set `pg_stat_statements.track` and related settings according to workload/privacy/overhead requirements.

### 42.5. Validate

Query `pg_stat_statements` and verify permissions, query tracking, and monitoring. An extension that is installed without preloading may not work as expected.

## 43. Example: Checking and Upgrading an Extension

Suppose the database is currently running version `1.0` and the server package provides version `1.2`.

### 43.1. Read Installed Version

~~~sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'example';
~~~

### 43.2. Check Target Version

~~~sql
SELECT name, version, installed
FROM pg_available_extension_versions
WHERE name = 'example'
ORDER BY version;
~~~

### 43.3. Check Update Path

~~~sql
SELECT source, target, path
FROM pg_extension_update_paths('example')
WHERE source = '1.0'
  AND target = '1.2';
~~~

### 43.4. Test Update

On a clone/staging environment, run:

~~~sql
ALTER EXTENSION example UPDATE TO '1.2';
~~~

Record duration, locks, logs, object changes, and application behavior.

### 43.5. Production Update

After backup/approval/maintenance checks, run the update in the target database. Verify `pg_extension.extversion` and smoke tests before opening traffic.

## 44. Inspecting Extension Configuration Tables

The `pg_extension` catalog contains `extconfig`/`extcondition` to record configuration tables and dump conditions.

~~~sql
SELECT
    extname,
    extconfig,
    extcondition
FROM pg_extension
WHERE extconfig IS NOT NULL;
~~~

### 44.1. extconfig

Stores OIDs of tables registered as extension configuration tables.

### 44.2. extcondition

Stores corresponding conditions to determine which rows need to be dumped under the extension config dump mechanism.

### 44.3. Data Ownership

An extension may own the table structure while the administrator/application manages configuration rows. Distinguish package defaults from user-customized data.

### 44.4. Dump Semantics

`pg_dump` uses this metadata to save required data for config tables. Do not assume all extension tables have their full data dumped.

### 44.5. Restore Validation

Compare config rows before/after restore and test the extension's behavior with the restored configuration.

## 45. Troubleshooting: Extension Not Available

`CREATE EXTENSION` reports that the extension is not available in the server installation.

### 45.1. Check Catalog Availability

Query `pg_available_extensions` and `pg_available_extension_versions` in the correct database.

### 45.2. Check Control File

Confirm `extension.control` exists in `sharedir/extension` or the directory configured by the package.

### 45.3. Check the Correct PostgreSQL Installation

The server may be running binaries from one installation while the package was installed into another. Cross-check using `pg_config`/service configuration.

### 45.4. Package Repository

Confirm the OS package matches the PostgreSQL major version, OS release, and architecture.

### 45.5. Managed Service Allowlist

If using managed PostgreSQL, the extension might not be supported by the provider or may not yet be enabled in the service configuration.

## 46. Troubleshooting: Permission Denied or Requires Superuser

### 46.1. Read Control Metadata

Check `superuser` and `trusted` in `pg_available_extension_versions`.

### 46.2. Database CREATE Privilege

A trusted extension still requires the invoking role to have the `CREATE` privilege on the database per trusted extension rules.

### 46.3. Schema Permissions

Verify that the schema exists and has the appropriate owner and `CREATE` privilege.

### 46.4. Dependencies

The extension may require other extensions to be installed or have available packages. Check `requires` metadata and the dependency chain.

### 46.5. Use a Privileged Deployment Role

If the package requires superuser, perform it via an audited DBA-controlled deployment identity. Do not elevate an application role just to install extensions.

## 47. Troubleshooting: Schema Conflict or Object Already Exists

An installation script may encounter an object with the same name that already exists.

### 47.1. Inspect Existing Objects

Determine whether the object was created by a prior manual install, another package, or the application.

### 47.2. Do Not Drop Immediately

The object might be in active use by the application or hold data. Record dependencies, owner, and grants before deciding.

### 47.3. Choose an Appropriate Schema

If the extension is relocatable, it can be installed into a prepared dedicated schema. Do not use a schema that conflicts with a non-relocatable package's requirements.

### 47.4. Resolve Conflicts Safely

Rename/migrate custom objects or use a package-supported migration. Avoid deleting objects solely to make `CREATE EXTENSION` succeed.

### 47.5. Retry After Understanding State

Inspect the catalog and transaction rollback after a failed installation. Do not assume partial objects remain or were removed without checking.

## 48. Troubleshooting: No Update Path or Update Script Failure

### 48.1. Check Source/Target

Confirm the exact installed version and requested target.

### 48.2. Check Update Paths

Use `pg_extension_update_paths` and verify that the SQL scripts are present on the filesystem.

### 48.3. Intermediate Versions

If paths only exist via an intermediate version, follow the path supported by the package. Do not manually run scripts in a guessed order.

### 48.4. Update Script Error

Read the server log and transaction state. `ALTER EXTENSION UPDATE` normally runs migrations inside a transaction; if it fails, the command transaction rolls back per semantics, though catalog/version should still be verified.

### 48.5. Vendor Guidance

Some releases require manual pre/post-update steps. Follow upgrade notes instead of editing `extversion` or the dependency catalog.


## 49. Troubleshooting: Shared Library Fails to Load

### 49.1. File Missing

Check the library path, file permissions, and package installation on the correct node.

### 49.2. ABI Mismatch

A binary built for a different PostgreSQL major version may fail to load. Rebuild/install the package targeting the right major version.

### 49.3. Missing OS Dependency

The shared library may depend on system libraries absent on the host. Use OS package metadata/tools to identify missing dependencies.

### 49.4. Preload Configuration

If the extension requires `shared_preload_libraries`, check the setting, `pending_restart`, and startup logs.

### 49.5. HA Consistency

If the primary has the library but a standby/DR node lacks it, failover can cause functions to fail. Verify every eligible node.

## 50. Procedure for Removing an Extension

Removing an extension requires evaluating objects, dependent objects, and configuration data.

1. Inventory extension version, schema, owner, and dependencies.
2. Identify applications/functions/tables using the extension.
3. Back up/export extension config data and dependent application data.
4. Remove references in the application/schema per the migration plan.
5. Inspect the dependency graph and choose `RESTRICT` or `CASCADE`.
6. Run `DROP EXTENSION` during a maintenance window if impact requires it.
7. Verify schema/object cleanup and application behavior.
8. Uninstall the OS package/shared library only when no database/node still needs it.
9. Update inventory, HA/DR images, and deployment manifests.

### 50.1. Prefer RESTRICT

Use the default `RESTRICT` so PostgreSQL reports remaining dependencies. Do not use `CASCADE` simply to force the command through.

### 50.2. Export Data First

If extension tables hold configuration/business data, export them before dropping. Member table data may be deleted along with the extension.

### 50.3. Multiple Databases

Check all databases before removing the package from the server. Another database might still have the extension installed.

### 50.4. Schema Cleanup

After `DROP EXTENSION`, inspect what objects remain in the schema. Only run `DROP SCHEMA` once confirmed no application objects need to be kept.

### 50.5. Package Cleanup

OS package removal is a separate step. Only remove it after database catalog installations and HA/DR requirements have been addressed.

## 51. Extension Governance and Version Policy

Extensions should be managed as part of the software supply chain.

### 51.1. Approved List

Maintain a list of approved extensions, along with owner, purpose, source repository/package, and risk classification.

### 51.2. Version Pinning

Record both the extension SQL version and OS package version. Avoid environment drift across staging/production/DR.

### 51.3. Security Updates

Track CVEs/advisories and vendor releases. Define timelines for security updates and testing requirements.

### 51.4. Compatibility Review

Each PostgreSQL major upgrade requires an extension compatibility matrix, package availability check, update paths, and rehearsal.

### 51.5. Ownership and Lifecycle

Assign an owner responsible for patching, upgrading, monitoring, backup/restore, and decommissioning the extension.

## 52. Common Extension Administration Mistakes

1. Assuming installing an OS package automatically creates extension objects in the database.
2. Assuming `CREATE EXTENSION` in one database applies to all databases.
3. Running `CREATE EXTENSION IF NOT EXISTS` and overlooking version/schema drift.
4. Installing extensions into `public` without reviewing schema privileges/`search_path`.
5. Assuming every extension is relocatable.
6. Granting superuser to an application just to install extensions.
7. Ignoring `trusted`/`superuser` metadata and package provenance.
8. Installing SQL scripts while missing the shared library.
9. Building a C extension with `pg_config` from the wrong PostgreSQL major version.
10. Installing packages only on the primary and forgetting standby/DR nodes.
11. Assuming `pg_upgrade` automatically upgrades the SQL version of every extension.
12. Running a new installation script instead of `ALTER EXTENSION UPDATE`.
13. Editing `pg_extension.extversion` or `pg_depend` directly.
14. Failing to check update paths before maintenance.
15. Assuming `ALTER EXTENSION UPDATE` has a downgrade script.
16. Using `CASCADE` without inspecting the dependency graph.
17. Running `DROP EXTENSION` without exporting configuration data.
18. Forgetting an extension's preload/restart requirements.
19. Skipping extension functions in application smoke tests.
20. Failing to test dump/restore and disaster recovery with the corresponding packages.

## 53. Practical Exercises

### Exercise 1 — Concept

How does an extension differ from a schema?

**Answer:** A schema is a namespace containing objects; an extension is a package/lifecycle unit managing a set of objects.

### Exercise 2 — Package

Does `CREATE EXTENSION` automatically install the OS package?

**Answer:** No; package files must already be present on the server beforehand.

### Exercise 3 — Database Scope

Does installing an extension in database A make it immediately usable in database B?

**Answer:** No; `CREATE EXTENSION` must be run in database B.

### Exercise 4 — Control File

What does `default_version` mean?

**Answer:** The default version chosen when `CREATE EXTENSION` does not specify `VERSION`.

### Exercise 5 — Update Scripts

When is the file `extension--1.0--1.1.sql` used?

**Answer:** To transition the extension from version `1.0` to `1.1`.

### Exercise 6 — Relocatable

What does `relocatable=true` permit?

**Answer:** Allows installing/moving the extension across schemas subject to relocation conditions.

### Exercise 7 — Trusted

Does `trusted=true` mean an extension is unconditionally safe?

**Answer:** No; it is metadata declared by the package author regarding trusted installation semantics, and source/code review is still required.

### Exercise 8 — Superuser

Why might an extension require superuser?

**Hint:** C functions, privileged operations, or scripts requiring elevated permissions.

### Exercise 9 — Availability

Which views list packages/versions available on the server?

**Answer:** `pg_available_extensions` and `pg_available_extension_versions`.

### Exercise 10 — Installed State

Which catalog stores extensions installed in the current database?

**Answer:** `pg_extension`.

### Exercise 11 — CREATE IF NOT EXISTS

Does this command upgrade an older extension version?

**Answer:** No; `ALTER EXTENSION UPDATE` is required.

### Exercise 12 — Schema

Can `WITH SCHEMA` be used for every extension?

**Answer:** No; it depends on `relocatable` and schema requirements.

### Exercise 13 — Search Path

Why should untrusted users not be allowed `CREATE` in schemas on `search_path`?

**Hint:** They can shadow the names of trusted objects.

### Exercise 14 — Dependencies

What does `requires` in a control file do?

**Answer:** Declares required extensions.

### Exercise 15 — CASCADE Install

What can `CREATE EXTENSION ... CASCADE` do?

**Answer:** Install missing dependencies according to dependency metadata.

### Exercise 16 — Update Path

Which function inspects extension update paths?

**Answer:** `pg_extension_update_paths(name)`.

### Exercise 17 — ALTER UPDATE

Does `ALTER EXTENSION UPDATE` automatically update all extensions?

**Answer:** No; only the specified extension.

### Exercise 18 — SET SCHEMA

What is the main condition for `ALTER EXTENSION SET SCHEMA`?

**Answer:** The extension must be relocatable and its member objects must satisfy relocation conditions.

### Exercise 19 — ADD/DROP Object

Does `ALTER EXTENSION DROP FUNCTION` delete the function?

**Answer:** No; it only removes membership from the extension.

### Exercise 20 — DROP EXTENSION

What does `DROP EXTENSION RESTRICT` do when dependent objects exist?

**Answer:** Rejects the drop if dependencies still exist.

### Exercise 21 — Config Tables

What is `pg_extension_config_dump` used for?

**Answer:** Marks extension configuration table data to be saved by `pg_dump`.

### Exercise 22 — Restore

Why must packages be installed on the target before `pg_restore`?

**Answer:** Restore requires `CREATE EXTENSION`, and the target server needs the control/SQL/shared library files.

### Exercise 23 — Major Upgrade

Does `pg_upgrade` automatically upgrade the SQL version of every extension?

**Answer:** No; extension packages/binaries and `ALTER EXTENSION UPDATE` must be handled per procedure.

### Exercise 24 — Preload

What configuration does `pg_stat_statements` need before `CREATE EXTENSION` to function fully?

**Answer:** Add it to `shared_preload_libraries` and restart the server, then run `CREATE EXTENSION` in the database.

### Exercise 25 — HA

Why must extension packages be present on standbys?

**Answer:** A node may be promoted; C functions/shared libraries must be loadable on the new node.

### Exercise 26 — Logical Replication

Does logical replication automatically replicate `CREATE EXTENSION`?

**Answer:** No; DDL/extension installation must be coordinated separately.

### Exercise 27 — Missing Library

SQL objects exist, but a C function reports a missing library. What should be checked?

**Hint:** Shared library package, path, ABI, dependencies, and preload requirements.

### Exercise 28 — Missing Update Path

`ALTER EXTENSION UPDATE` reports no path. What should you do?

**Answer:** Check package scripts, source/target versions, intermediate paths, and vendor guidance; do not edit the catalog version.

### Exercise 29 — Decommission

Why should `DROP EXTENSION RESTRICT` be used before `CASCADE`?

**Answer:** To detect dependent objects and avoid unintended deletions.

### Exercise 30 — Lifecycle

List the main stages in the extension lifecycle.

**Hint:** Approve/source, install package, inspect metadata, create/schema/privileges, monitor, update scripts/package, backup/restore, upgrade compatibility, and decommission.


## 54. Extension Installation and Management Checklist

- [ ] Does the extension have a clear business/technical owner and purpose?
- [ ] Have package source, license, and security advisories been reviewed?
- [ ] Has PostgreSQL major/OS/architecture compatibility been confirmed?
- [ ] Are control file, install/update scripts, and shared library complete?
- [ ] Are dependencies and `trusted`/`superuser` requirements understood?
- [ ] Have schema, owner, `search_path`, and grants been designed?
- [ ] Has the package been installed on primary/standby/DR nodes?
- [ ] Have preload/restart requirements been fulfilled?
- [ ] Has `CREATE EXTENSION` been run in the right databases/version/schema?
- [ ] Have catalog/member objects/function behavior been verified?
- [ ] Has backup/restore of config tables been tested?
- [ ] Have extension inventory and patch policy been updated?

## 55. Extension Upgrade or Removal Checklist

### Before Upgrade

- [ ] Have installed versions per database been inventoried?
- [ ] Have target package/shared library been deployed on all nodes?
- [ ] Have update paths from source to target been verified?
- [ ] Have release notes/dependencies/security changes been reviewed?
- [ ] Have staging clone testing and rollback boundaries been defined?
- [ ] Are the backup/recovery point and maintenance window ready?

### After Upgrade

- [ ] Has `ALTER EXTENSION UPDATE` completed in all required databases?
- [ ] Have `extversion`/schema/owner/member objects been confirmed?
- [ ] Have functions/types/operators/indexes been smoke tested?
- [ ] Are preload/library logs and restart requirements satisfied?
- [ ] Have application queries/performance and replication been verified?
- [ ] Have inventory/version manifests been updated?

### When Removing

- [ ] Have application references and dependencies been addressed?
- [ ] Has config/user data been exported?
- [ ] Has `RESTRICT` been used to check dependencies?
- [ ] Is `CASCADE` used only after impact review/approval?
- [ ] Have all databases/nodes been checked before uninstalling the package?

## 56. Quick Reference Table

| Component | Role |
|---|---|
| Extension | Lifecycle management unit for database objects |
| Schema | Namespace containing objects |
| Control file | Metadata and install behavior |
| Installation script | Creates objects for a single version |
| Update script | Migration between two versions |
| Shared library | Binary code for C functions |
| CREATE EXTENSION | Installs an extension in the current database |
| IF NOT EXISTS | Avoids error if extension already exists |
| VERSION | Selects extension SQL version |
| SCHEMA | Selects schema if package supports it |
| relocatable | Allows conditional relocation |
| trusted | Allows non-superuser install under trusted rules |
| superuser | Requires privileged installer |
| requires | Extension dependencies |
| pg_available_extensions | Packages/default/installed version in current DB context |
| pg_available_extension_versions | Versions and install metadata |
| pg_extension | Extensions installed in current database |
| pg_depend | Object dependency/membership records |
| pg_extension_update_paths | Available update script paths |
| ALTER EXTENSION UPDATE | Executes migration scripts |
| ALTER EXTENSION SET SCHEMA | Moves a relocatable extension |
| ALTER EXTENSION ADD/DROP | Modifies object membership |
| DROP EXTENSION | Removes extension and member objects |
| pg_extension_config_dump | Registers config table data for dump |
| shared_preload_libraries | Loads libraries on PostgreSQL start |
| pg_config | Displays build/install paths |
| pg_dump | Dumps extension installation and config data |
| pg_upgrade | Major version upgrade tool |

## 57. Conclusion

**An extension is a package with its own lifecycle, combining installation files on the server with catalog objects in each database.** The control file defines the default version, schema behavior, dependencies, and privilege requirements; installation scripts create objects; update scripts transition from one version to another. Installing an OS package does not create objects in the database, and running `CREATE EXTENSION` in one database does not install the extension for remaining databases.

Schemas should be selected based on `relocatable` metadata, ownership, `search_path`, and application references. `trusted`/`superuser` requirements are critical security boundaries; C shared libraries run inside the server process, so package provenance, ABI, dependencies, and patch cadence must be managed like a software supply chain. `pg_available_extensions`/versions report package availability, `pg_extension` reports installed state, and `pg_extension_update_paths` helps confirm upgrade paths.

`ALTER EXTENSION UPDATE` is the standard path for running migration scripts. `SET SCHEMA` only suits relocatable extensions meeting member-object conditions; `ADD`/`DROP` object only changes membership; `DROP EXTENSION` can delete member objects/data and `CASCADE` can remove additional dependencies. Backup/restore and major upgrades must prepare packages, libraries, preload settings, config table data, and SQL extension versions on the target.

Operational principle: **verify packages and compatibility first, design schemas/privileges at install time, use update scripts for version changes, keep binaries consistent across HA/DR nodes, and rehearse restores before treating an extension as production-ready.**
