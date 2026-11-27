# Inventorying Extensions, Data Types, and Dependent Tools When Upgrading PostgreSQL

Upgrading PostgreSQL, especially a major-version upgrade, is not just installing a new server binary and starting the database. A cluster may depend on extensions, shared libraries, custom data types, collations, foreign data wrappers, procedural languages, event triggers, client drivers, backup tools, monitoring agents, and external operational programs. If a dependency does not have a compatible build on the target version, the database may fail to start, extensions may fail to load, queries may change results, or applications may fail to connect after cutover.

Before upgrading, you need to build a **verifiable inventory**. The inventory must answer:

- Which extensions are installed in the cluster, at which versions, and which extensions exist only on the host without being installed in a database?
- Which extensions require shared libraries, OS packages, preloading, or external services?
- Which user-defined or extension-defined data types exist in the database?
- Are there any special enums, domains, composites, ranges, multiranges, collations, or casts/operators?
- Which objects depend on extensions, and which extensions depend on other extensions?
- Are there any C-language functions, procedural languages, FDWs, event triggers, or background workers that require external binaries?
- Which tools read from or write to the cluster: `pg_upgrade`, `pg_dump`, `pg_restore`, backup agents, poolers, drivers, ORMs, CDC, monitoring, HA managers, and schedulers?
- Is each dependency compatible with the source version, target version, OS, architecture, and deployment model?

A good inventory combines catalog queries inside PostgreSQL with package manifests, the filesystem, deployment manifests, and confirmations from each application owner. Catalogs only describe what the database knows; they cannot automatically list every library or executable located outside the server.

~~~text
                PostgreSQL source cluster
                         |
       +-----------------+------------------+
       |                 |                  |
       v                 v                  v
    Extensions       Data types          Database objects
       |                 |                  |
       +-----------------+------------------+
                         |
                         v
                Dependency graph
                         |
       +-----------------+------------------+
       |                 |                  |
       v                 v                  v
   Server/OS         Client/tools       External services
   libraries         drivers/agents     FDW/CDC/HA/ETL
       |                 |                  |
       +-----------------+------------------+
                         |
                         v
             Compatibility matrix + rehearsal
                         |
                         v
                 Upgrade / rollback plan
~~~

This lesson belongs to the **Database Engine Relational PostgreSQL** module, **Upgrades** chapter, with the topic **“Inventorying Extensions, Data Types, and Dependent Tools”**. The focus is on building a pre-upgrade inventory, identifying dependencies and compatibility, and turning the findings into an actionable testing and cutover plan.

---

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why dependencies must be inventoried before a major-version upgrade.
2. Distinguish between PostgreSQL core objects, extension objects, and external dependencies.
3. List installed extensions using pg_extension.
4. Distinguish installed extensions from extension packages available on the server.
5. Look up default_version, installed_version, requires, and relocatable.
6. Inspect extension update paths and determine whether an extension has an upgrade path.
7. List objects belonging to an extension via pg_depend.
8. Check shared_preload_libraries and preload requirements.
9. Inventory user-defined base types, domains, enums, composites, ranges, and multiranges.
10. Inspect casts, operators, operator classes, access methods, and collations.
11. Identify C-language functions and the libraries they require.
12. Inventory procedural languages, FDWs, foreign servers, and user mappings.
13. Check event triggers, publications, subscriptions, and logical replication dependencies.
14. Distinguish catalog inventory from package/filesystem inventory.
15. Inventory client tools, drivers, ORMs, poolers, and operational agents.
16. Build a compatibility matrix for source/target versions and OS/architecture.
17. Understand the differences between pg_upgrade and dump/restore regarding extensions and data types.
18. Build a pre-upgrade checklist and a dependency owner list.
19. Rehearse the upgrade in a staging environment with the same dependency set.
20. Handle extension updates, library replacement, and post-upgrade validation.
21. Document risks, rollback requirements, and cutover criteria.
22. Avoid common pitfalls such as missing packages, wrong library paths, collation drift, or outdated client drivers.

**Scope:** Modern PostgreSQL, primarily major-version upgrades. Catalog columns, extension packaging, and tools may vary by version, OS, distribution, and managed service. Inventory queries should be run against each individual database and cross-checked with the target major version's documentation.

---

## 2. Why Is Inventorying a Mandatory Step?

### 2.1. A Database Is More Than Tables and Indexes

A PostgreSQL application may depend on:
- Extensions providing functions, types, operators, or index access methods.
- Shared libraries loaded by the server.
- Custom types and casts.
- Collations from libc or ICU.
- Procedural languages such as PL/Perl, PL/Python, or PL/v8.
- Foreign data wrappers connecting to other systems.
- Event triggers and background workers.
- Client drivers, ORMs, migration tools, and connection poolers.
- Backup, monitoring, HA, and CDC tools.

### 2.2. Upgrades Change Binary Interfaces and Catalog Behavior

A major version can change the server ABI, catalog schema, planner/executor behavior, SQL features, data format assumptions, or extension APIs. A C extension compiled for an older major version typically requires a binary build compatible with the target version.

### 2.3. An Extension May Be Installed in the Database While Its Package Is Missing on the Target

pg_extension records extensions that were installed via CREATE EXTENSION in the database. It does not prove that the control file, SQL scripts, or shared libraries are installed on the target server.

### 2.4. A Package May Exist on the Server Without Being Used by Any Database

pg_available_extensions shows the extension packages visible to the PostgreSQL instance. An extension may not yet be installed in any database, yet an application might plan to enable it after the upgrade.

### 2.5. A Missing Dependency May Only Surface at Startup or Query Time

For example:
- The server fails to load a library listed in shared_preload_libraries.
- CREATE EXTENSION or ALTER EXTENSION UPDATE fails due to missing control/SQL scripts.
- A C function calls a library that does not exist.
- A collation version change causes indexes to require a rebuild.
- A driver does not understand protocol/authentication behavior.
- A backup agent does not support the target major version.

### 2.6. Every Inventory Item Needs an Owner

Each dependency should have:
- Name and version.
- Where it is used.
- Owner/responsible team.
- Target compatibility evidence.
- Upgrade action.
- Testing method.
- Rollback/restore plan.

Without an owner, a rarely used yet critical dependency can easily be overlooked.

---

## 3. Inventory Scope: Layers to Inspect

| Layer | Examples | Inventory Source |
| --- | --- | --- |
| Extensions | PostGIS, pg_stat_statements, pg_cron | pg_extension, pg_available_extensions |
| Extension binaries | .so, .dll, shared libraries | pg_config, package manager, filesystem |
| Data types | enum, domain, composite, range | pg_type, pg_enum, pg_range |
| Functions | SQL, PL/pgSQL, C | pg_proc, pg_language |
| Operators/casts | custom operators, casts | pg_operator, pg_cast |
| Collations | libc, ICU | pg_collation |
| Index dependencies | opclass, access method | pg_opclass, pg_am |
| FDW | postgres_fdw, file_fdw | pg_foreign_data_wrapper |
| External connections | servers, user mappings | pg_foreign_server, pg_user_mapping |
| Triggers | event triggers | pg_event_trigger |
| Replication | publications, subscriptions | pg_publication, pg_subscription |
| Server settings | preload libraries, custom GUCs | pg_settings, config files |
| Client stack | libpq, JDBC, Npgsql, psycopg | application manifests |
| Operational tools | pg_upgrade, dump/restore, backup agent | hosts, CI/CD, runbooks |
| Infrastructure | OS, architecture, libc, ICU | host/package inventory |

The inventory must cover **every database in the cluster**. Extensions are installed per database, whereas package binaries are typically installed at the server/host level.

---

## 4. Defining the Source and Target Environments

Before inspecting dependencies, document the environments being upgraded.

### 4.1. Source Cluster

Collect:
- PostgreSQL major/minor version.
- OS distribution/version.
- CPU architecture.
- Package source and build flags.
- Data directory, tablespaces, and storage layout.
- Encoding, locale, collation provider.
- Installed extensions and versions.
- Server configuration and preload settings.
- Replication topology and external integrations.

### 4.2. Target Cluster

Document the corresponding details:
- Target PostgreSQL major/minor version.
- Target OS and architecture.
- Extension package repositories.
- Shared library paths.
- libc/ICU versions.
- Supported client/driver versions.
- Backup/restore tool versions.
- HA/monitoring/CDC compatibility.

### 4.3. Major Upgrades Differ from Minor Updates

Minor updates within the same major version generally preserve better compatibility, though you should still check release notes and extension packaging. Major upgrades typically require checking the ABI, catalog changes, extension update scripts, and migration paths.

### 4.4. Managed PostgreSQL

With a managed service, the provider controls server packages and the upgrade process. Your inventory still needs to identify the extension allowlist, supported versions, parameter groups, drivers, backup/restore behavior, and service limitations.

---

## 5. Listing Installed Extensions in a Database

An extension is a collection of database objects managed as a single unit via CREATE EXTENSION, ALTER EXTENSION, and DROP EXTENSION.

### 5.1. Viewing Installed Extensions

~~~sql
SELECT
    e.extname,
    e.extversion,
    n.nspname AS extension_schema,
    pg_catalog.pg_get_userbyid(e.extowner) AS extension_owner,
    e.extrelocatable
FROM pg_catalog.pg_extension AS e
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = e.extnamespace
ORDER BY e.extname;
~~~

Run this query in every database that needs to be upgraded. A cluster may have different extension sets across different databases.

### 5.2. Column Meanings

| Column | Meaning |
| --- | --- |
| extname | Extension name |
| extversion | Currently installed SQL extension version |
| extension_schema | Schema containing the objects belonging to the extension |
| extension_owner | Role that owns the extension |
| extrelocatable | Whether the extension can be moved to another schema according to metadata |

### 5.3. Do Not Record Only the Extension Name

The version is mandatory information. The same extension name can have different SQL objects and binaries across versions.

### 5.4. Extension Owner

The owner may need privileges to execute ALTER EXTENSION UPDATE or migration steps. Record the role and how privileges are granted on the target.

### 5.5. Per-Database Extensions

You can iterate the query across every database using controlled automation. Do not use a single result from the default database to represent the entire cluster.

---

## 6. Distinguishing Installed Extensions from Available Packages

### 6.1. Available Extension Packages

~~~sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_catalog.pg_available_extensions
ORDER BY name;
~~~

This view reflects the extension control files visible to the PostgreSQL server.

### 6.2. Available Package Versions

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
FROM pg_catalog.pg_available_extension_versions
ORDER BY name, version;
~~~

### 6.3. Interpretation

- installed_version is not NULL: the extension is currently installed in the current database.
- default_version: the version that CREATE EXTENSION typically selects when no version is specified.
- version: the extension versions provided by the server packages.
- requires: extension dependencies declared in the control metadata.
- trusted/superuser: information about installation privilege requirements according to package metadata.
- relocatable/schema: metadata regarding schema placement.

### 6.4. Having a Package Does Not Mean It Is Installed

pg_available_extensions only indicates that the server sees the package. It does not mean the extension is currently used by the database.

### 6.5. Being Installed Does Not Guarantee a Target Package Exists

The source database may record extversion, but the target host still needs a matching package version and shared library to load/upgrade.

### 6.6. Checking Extensions That Are Installed Without a Default Package

If installed_version has a value but the target package does not provide that version, you must determine the upgrade path and package source. Never assume the extension was deprecated or is no longer used.

---

## 7. Checking Extension Update Paths

Moving an extension from its current version to a new version usually requires a matching update script path.

### 7.1. Viewing Update Paths

On versions that support this function:

~~~sql
SELECT *
FROM pg_catalog.pg_extension_update_paths('postgis');
~~~

Replace the extension name with the extension you want to inspect. Verify the function and output schema on your specific server version.

### 7.2. Meaning of Update Paths

A path represents a chain of update scripts that can bring an extension from a source version to a target version. It may need to step through multiple intermediate versions if the package does not provide a direct script.

### 7.3. Missing Path

If there is no update path, a direct ALTER EXTENSION UPDATE may not be possible. Check vendor guidance, intermediate releases, dump/restore, or a separate migration procedure.

### 7.4. Extension Version Is Not PostgreSQL Version

For example, extension version 3.4.2 does not mean server version 3.4.2. Record the server major version and the extension's extversion separately.

### 7.5. Update Scripts Can Modify Schema and Data

An extension update may:
- Create/drop/alter objects.
- Rebuild metadata.
- Convert internal data.
- Change function signatures.
- Require a maintenance window.
- Require owner/superuser privileges.

Read the release notes and test on a clone before running in production.

### 7.6. Extensions With Pre-Upgrade and Post-Upgrade Steps

Some extensions require running scripts before pg_upgrade or after the upgrade. Do not skip the extension vendor's documentation.

---

## 8. Inventorying Objects Belonging to an Extension

Extension membership is recorded in pg_depend with the corresponding dependency type.

### 8.1. Counting Objects by Extension

~~~sql
SELECT
    e.extname,
    count(*) AS member_objects
FROM pg_catalog.pg_depend AS d
JOIN pg_catalog.pg_extension AS e
    ON d.refclassid = 'pg_catalog.pg_extension'::regclass
   AND d.refobjid = e.oid
WHERE d.deptype = 'e'
GROUP BY e.extname
ORDER BY member_objects DESC;
~~~

### 8.2. Listing Object Descriptions

~~~sql
SELECT
    e.extname,
    pg_catalog.pg_describe_object(
        d.classid,
        d.objid,
        d.objsubid
    ) AS extension_object
FROM pg_catalog.pg_depend AS d
JOIN pg_catalog.pg_extension AS e
    ON d.refclassid = 'pg_catalog.pg_extension'::regclass
   AND d.refobjid = e.oid
WHERE d.deptype = 'e'
ORDER BY e.extname, extension_object;
~~~

### 8.3. Why Inventory Member Objects?

Knowing how many objects an extension owns helps you understand the blast radius of changes and spot extension-owned objects that the application uses. However, object count does not indicate criticality.

### 8.4. Object Dependencies Outside Extension Membership

An object created by an extension may be referenced by an application view, function, column type, or index. Check dependencies in both directions and verify with the application schema.

### 8.5. Do Not Directly Modify Extension-Owned Objects

If an object belongs to an extension, manual modifications can cause metadata drift or cause ALTER EXTENSION UPDATE to fail. Use extension-supported configuration/APIs and migration scripts.

---

## 9. Extensions That Depend on Other Extensions

An extension can declare `requires` in its control file. During installation, PostgreSQL can install dependencies according to metadata.

### 9.1. Viewing `requires`

~~~sql
SELECT
    name,
    version,
    requires
FROM pg_catalog.pg_available_extension_versions
WHERE requires IS NOT NULL
ORDER BY name, version;
~~~

### 9.2. Dependency Chains

For example, extension A requires extension B; extension B may require extension C. Your inventory must preserve the dependency chain rather than just listing A.

### 9.3. Upgrade Order

The vendor may stipulate that a dependency extension must be upgraded first. Do not infer the order solely from extension names; consult control metadata, update scripts, and release notes.

### 9.4. Optional Dependencies

Some extension integrations are only needed when a specific feature is enabled. Record the actual status: required, optional, installed-but-unused, or unknown.

### 9.5. Extensions Used Indirectly via SQL Objects

An extension might be installed with no queries calling it directly anymore, yet still be referenced by views, triggers, indexes, or functions; check dependencies before marking it unused.

---

## 10. Inventorying User-Defined Data Types

PostgreSQL allows creating custom data types. Extensions can also create types. A type can appear in table columns, function signatures, arrays, casts, indexes, and serialized data.

### 10.1. Viewing User-Defined Types

~~~sql
SELECT
    n.nspname AS schema_name,
    t.typname AS type_name,
    t.typtype,
    t.typcategory,
    t.typisdefined,
    t.typbyval,
    t.typlen,
    t.typalign,
    t.typstorage,
    t.typnamespace::regnamespace AS type_schema
FROM pg_catalog.pg_type AS t
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.typnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND t.typisdefined
ORDER BY n.nspname, t.typname;
~~~

### 10.2. Common typtype Values

| Code | Type Kind |
| --- | --- |
| b | Base type |
| c | Composite type |
| d | Domain |
| e | Enum |
| m | Multirange |
| p | Pseudo-type |
| r | Range |

Some specialized kinds may depend on the version. The type system also includes array types automatically generated by PostgreSQL.

### 10.3. typcategory

typcategory is a parser/type-system classification useful for analyzing behavior. It does not replace typtype.

### 10.4. typbyval and typlen

These fields describe how values are stored and passed internally. This is an important detail for C extensions/custom base types and binary compatibility.

### 10.5. typstorage

For varlena types, typstorage describes the storage strategy. Implementation changes must follow binary format and extension upgrade rules.

### 10.6. Type Names Can Overlap Across Schemas

Do not store only typname. Record the schema, owner, extension membership, and dependent columns/functions.

---

## 11. Inventorying Columns Using Custom Types

### 11.1. Finding Columns Using User-Defined Types

~~~sql
SELECT
    table_schema,
    table_name,
    column_name,
    udt_schema,
    udt_name,
    data_type
FROM information_schema.columns
WHERE udt_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, ordinal_position;
~~~

### 11.2. Combining Table Metadata

You can join pg_attribute, pg_class, pg_namespace, and pg_type to retrieve relation kind, nullability, typmod, and column details that information_schema does not fully expose.

### 11.3. Partitioned Tables

Check both parent tables and partitions. Types on the parent may be inherited by partition columns, yet physical relation inventories still need to record them explicitly.

### 11.4. Function Arguments and Returns

Custom types may appear only in function signatures rather than table columns. Inventorying pg_proc is also necessary.

### 11.5. Views and Materialized Views

Views have output columns carrying specific types. Materialized views store physical data; check their dependencies and refresh behavior after the upgrade.

---

## 12. Enum Types

An enum is a type with a defined, ordered set of labels.

### 12.1. Listing Enum Labels

~~~sql
SELECT
    n.nspname AS schema_name,
    t.typname AS enum_type,
    e.enumsortorder,
    e.enumlabel
FROM pg_catalog.pg_type AS t
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.typnamespace
JOIN pg_catalog.pg_enum AS e
    ON e.enumtypid = t.oid
ORDER BY n.nspname, t.typname, e.enumsortorder;
~~~

### 12.2. Why Do Enums Matter During Upgrades?

Enum labels may be stored in table data, function logic, and application code. A migration must preserve labels and ordering semantics.

### 12.3. Enum Ordering

Enum comparisons follow enum sort order, not the lexical order of the labels. Applications may rely on that order in ORDER BY or range comparisons.

### 12.4. Adding Labels

ALTER TYPE ... ADD VALUE has semantics and transactional restrictions that depend on the PostgreSQL version. Check migration scripts if the upgrade is accompanied by enum changes.

### 12.5. Removing or Renaming Labels

PostgreSQL does not provide a simple operation to remove an existing enum label. It usually requires creating a new type, casting/migrating columns, and updating dependencies. Do not treat enum labels as arbitrary strings.

---

## 13. Domain Types

A domain is a type based on a base type, with optional NOT NULL and CHECK constraints.

### 13.1. Listing Domains

~~~sql
SELECT
    n.nspname AS schema_name,
    t.typname AS domain_name,
    bt.typname AS base_type,
    t.typnotnull,
    t.typdefault
FROM pg_catalog.pg_type AS t
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.typnamespace
JOIN pg_catalog.pg_type AS bt
    ON bt.oid = t.typbasetype
WHERE t.typtype = 'd'
ORDER BY n.nspname, t.typname;
~~~

### 13.2. Domain Constraints

~~~sql
SELECT
    n.nspname AS schema_name,
    t.typname AS domain_name,
    c.conname,
    pg_catalog.pg_get_constraintdef(c.oid) AS constraint_definition,
    c.convalidated
FROM pg_catalog.pg_constraint AS c
JOIN pg_catalog.pg_type AS t
    ON t.oid = c.contypid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.typnamespace
WHERE c.contypid <> 0
ORDER BY n.nspname, t.typname, c.conname;
~~~

### 13.3. Upgrade Considerations

- Is the domain's base type supported on the target?
- Do constraint expressions call extension functions?
- Are the constraints validated?
- Does the default expression depend on custom functions/operators?
- Do applications serialize domain values using a custom format?

### 13.4. A Domain Is Not Just an Alias

Domains carry constraint semantics. If a dump/restore or migration drops constraints or defaults, application behavior may change.

---

## 14. Composite Types

A composite type describes a structure consisting of multiple fields, created either via CREATE TYPE AS or automatically generated for a table row type.

### 14.1. Listing Composite Types

~~~sql
SELECT
    n.nspname AS schema_name,
    t.typname AS composite_type,
    a.attnum,
    a.attname AS attribute_name,
    format_type(a.atttypid, a.atttypmod) AS attribute_type,
    a.attnotnull
FROM pg_catalog.pg_type AS t
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.typnamespace
JOIN pg_catalog.pg_class AS c
    ON c.oid = t.typrelid
JOIN pg_catalog.pg_attribute AS a
    ON a.attrelid = c.oid
WHERE t.typtype = 'c'
  AND a.attnum > 0
  AND NOT a.attisdropped
ORDER BY n.nspname, t.typname, a.attnum;
~~~

### 14.2. Table Row Types

Every table has a corresponding row type. The query above may return many table row types; when you need standalone custom composites, filter by relation kind and type ownership.

### 14.3. Dependencies

Composite types can be used in function return types, parameters, table columns, and arrays. Check those dependencies and the clients consuming those result shapes.

### 14.4. Binary/API Compatibility

Changing field order or types can affect clients reading composite records, function signatures, and serialized representations.

---

## 15. Range and Multirange Types

Range types represent an interval over a subtype with appropriate ordering. Multiranges represent sets of non-overlapping ranges according to PostgreSQL semantics.

### 15.1. Listing Range Types

~~~sql
SELECT
    r.rngtypid::regtype AS range_type,
    r.rngsubtype::regtype AS subtype,
    r.rngcollation::regcollation AS collation,
    r.rngcanonical::regproc AS canonical_function,
    r.rngsubdiff::regproc AS subtype_diff_function
FROM pg_catalog.pg_range AS r
ORDER BY r.rngtypid::regtype::text;
~~~

### 15.2. Multirange

PostgreSQL versions that support multiranges store linked metadata in pg_range. Check the schema and catalog of the target version.

### 15.3. Custom Range Types

CREATE TYPE ... AS RANGE may depend on a subtype, collation, canonical function, and subtype difference function. All of those functions and types must be present and compatible.

### 15.4. Use Cases

- Date/time intervals.
- Numeric intervals.
- Scheduling windows.
- Exclusion constraints.
- Resolving overlaps in temporal data.

### 15.5. Upgrade Tests

Test operators, indexes, GiST/SP-GiST opclasses, exclusion constraints, and application serialization of ranges.

---

## 16. Array, Pseudo-Type, and Base Types

### 16.1. Array Types

PostgreSQL automatically creates an array type for many base and composite types. typcategory and type naming conventions can help identify them, though you should not rely solely on names starting with an underscore.

### 16.2. Pseudo-Types

Types like record, anyelement, anyarray, void, and trigger are used in function signatures or polymorphic functions. They are not regular data columns.

### 16.3. Custom Base Types

An extension can define a base type with input/output, receive/send, typmod, comparison, and storage functions. These functions may be written in C.

### 16.4. Binary Representation

If a custom type has its own binary representation, the extension must support the target server and all migration requirements. Do not assume dump/restore text format is always sufficient for every integration or binary protocol.

### 16.5. Inventorying Functions Attached to a Type

Inspect pg_type input/output/receive/send/typmod functions as well as the operators and opclasses that use that type. These are frequently missed when listing only type names.

---

## 17. Functions and C-Language Dependencies

Functions can be written in SQL, PL/pgSQL, C, or other procedural languages. C functions usually depend on shared libraries outside the database.

### 17.1. Listing Functions by Language

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    l.lanname AS language,
    pg_catalog.pg_get_function_identity_arguments(p.oid) AS arguments,
    pg_catalog.pg_get_function_result(p.oid) AS result_type,
    p.probin AS library_name,
    p.prosrc AS source_or_symbol
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
JOIN pg_catalog.pg_language AS l
    ON l.oid = p.prolang
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, p.proname;
~~~

### 17.2. Finding C Functions

~~~sql
SELECT
    n.nspname,
    p.proname,
    pg_catalog.pg_get_function_identity_arguments(p.oid) AS arguments,
    p.probin AS library_name,
    p.prosrc AS symbol_name
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
JOIN pg_catalog.pg_language AS l
    ON l.oid = p.prolang
WHERE l.lanname = 'c'
ORDER BY n.nspname, p.proname;
~~~

### 17.3. probin and prosrc

For C-language functions, probin typically indicates the library path/name and prosrc typically indicates the symbol name. Packaging may use `$libdir` or an explicit path.

### 17.4. Binary Compatibility

C extensions/libraries are typically built for a specific PostgreSQL major version and OS/architecture. You need a binary package matching the target server, not just a copy of the old `.so` file.

### 17.5. External Shared Library Dependencies

A `.so` file may depend on libxml2, GEOS, PROJ, GDAL, OpenSSL, or other system libraries. Check package dependencies and dynamic linker resolution on the target.

### 17.6. SQL Functions Also Have Dependencies

SQL/PLpgSQL functions can call custom types, operators, collations, extension functions, and tables. Inventory function bodies and dependencies when the upgrade involves schema changes.

---

## 18. Procedural Languages

### 18.1. Listing Languages

~~~sql
SELECT
    lanname,
    lanpltrusted,
    lanispl,
    lanvalidator::regproc AS validator,
    laninline::regproc AS inline_handler,
    lancompiler
FROM pg_catalog.pg_language
ORDER BY lanname;
~~~

Some fields may be inapplicable or differ across versions; verify against the actual schema.

### 18.2. PL/pgSQL

PL/pgSQL is typically distributed with PostgreSQL. Even so, test function behavior and syntax after a major upgrade.

### 18.3. PL/Python, PL/Perl, PL/Tcl, and Other Languages

These languages may require packages, interpreters, ABIs, and runtime libraries compatible with the target OS and server.

### 18.4. Trusted/Untrusted

Trust status governs who can create functions in the language. Do not alter the trust model during an upgrade without a security review.

### 18.5. Function Dependencies

Inspect functions written in that language, imported modules, and external packages invoked by the code.

---

## 19. Collations: An Easily Overlooked Dependency

Collation determines how text is compared and sorted. Results depend on the provider (such as libc or ICU) and the version of the locale data.

### 19.1. Listing Collations

~~~sql
SELECT
    n.nspname AS schema_name,
    c.collname,
    c.collprovider,
    c.collisdeterministic,
    c.collcollate,
    c.collctype,
    c.collversion
FROM pg_catalog.pg_collation AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.collnamespace
ORDER BY n.nspname, c.collname;
~~~

Some columns may not exist on older PostgreSQL versions; inspect the schema before running.

### 19.2. libc and ICU

- libc collations depend on the OS locale implementation and data.
- ICU collations depend on the ICU library and collation rules/version.
- Providers and versions may differ between the source and target hosts.

### 19.3. Why Does Collation Drift Matter?

If sorting or equality behavior changes, B-tree indexes created under the old collation may no longer reflect the current ordering. This can cause queries to return incorrect results or require rebuilding indexes following PostgreSQL's recommended procedure.

### 19.4. Checking Collation Version Mismatches

On supported versions:

~~~sql
SELECT
    n.nspname,
    c.collname,
    c.collversion,
    pg_catalog.pg_collation_actual_version(c.oid) AS actual_version
FROM pg_catalog.pg_collation AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.collnamespace
WHERE c.collversion IS DISTINCT FROM
      pg_catalog.pg_collation_actual_version(c.oid)
ORDER BY n.nspname, c.collname;
~~~

### 19.5. Refreshing Version Does Not Rebuild Indexes

ALTER COLLATION ... REFRESH VERSION updates metadata about the provider version. It does not automatically rebuild indexes that depend on the collation. You must identify dependent indexes and run REINDEX according to your plan.

### 19.6. Collation Dependencies

Text columns, indexes, constraints, unique indexes, expression indexes, and application ordering can all depend on collations. Your inventory should include locales/providers and dependent objects.

---

## 20. Casts, Operators, and Operator Classes

Custom types often come with casts, operators, and index support methods.

### 20.1. User-Defined Casts

~~~sql
SELECT
    s.typname AS source_type,
    t.typname AS target_type,
    c.castcontext,
    c.castmethod,
    c.castfunc::regprocedure AS cast_function
FROM pg_catalog.pg_cast AS c
JOIN pg_catalog.pg_type AS s
    ON s.oid = c.castsource
JOIN pg_catalog.pg_type AS t
    ON t.oid = c.casttarget
ORDER BY s.typname, t.typname;
~~~

The catalog contains both built-in and user-defined casts. Combine namespace/type ownership and extension membership to classify them.

### 20.2. User-Defined Operators

~~~sql
SELECT
    n.nspname AS schema_name,
    o.oprname,
    o.oprleft::regtype AS left_type,
    o.oprright::regtype AS right_type,
    o.oprcode::regprocedure AS implementation,
    o.oprrest::regprocedure AS restriction_estimator,
    o.oprjoin::regprocedure AS join_estimator
FROM pg_catalog.pg_operator AS o
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = o.oprnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, o.oprname;
~~~

### 20.3. Operator Classes

~~~sql
SELECT
    n.nspname AS schema_name,
    am.amname AS access_method,
    opc.opcname,
    opc.opcintype::regtype AS input_type,
    opc.opcdefault,
    opc.opcfamily::regclass AS operator_family
FROM pg_catalog.pg_opclass AS opc
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = opc.opcnamespace
JOIN pg_catalog.pg_am AS am
    ON am.oid = opc.opcmethod
ORDER BY n.nspname, am.amname, opc.opcname;
~~~

### 20.4. Why Inventory These?

Extensions can provide operators and opclasses for GiST, GIN, SP-GiST, BRIN, or custom access methods. If a binary or opclass is incompatible, index creation or query behavior may fail.

### 20.5. Indexes Depending on Opclasses

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    am.amname AS access_method,
    opc.opcname AS operator_class
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_class AS tbl
    ON tbl.oid = i.indrelid
JOIN pg_catalog.pg_namespace AS ns
    ON ns.oid = tbl.relnamespace
JOIN pg_catalog.pg_class AS idx
    ON idx.oid = i.indexrelid
JOIN pg_catalog.pg_am AS am
    ON am.oid = (SELECT relam FROM pg_catalog.pg_class WHERE oid = idx.oid)
JOIN LATERAL unnest(i.indclass) WITH ORDINALITY AS opco(opclass_oid, ord)
    ON true
JOIN pg_catalog.pg_opclass AS opc
    ON opc.oid = opco.opclass_oid
ORDER BY ns.nspname, tbl.relname, idx.relname, opco.ord;
~~~

This query illustrates inventorying opclasses per index column; across different PostgreSQL versions, how the access method is read from the index relation may need adjustment. Test the query on the target/source versions and distinguish indexes using default opclasses from those using custom opclasses.

---

## 21. Foreign Data Wrappers and External Connections

FDWs connect PostgreSQL to other data systems. Upgrades may require compatible extension packages, client libraries, remote server compatibility, and credentials.

### 21.1. Listing FDWs

~~~sql
SELECT
    fdwname,
    fdwowner::regrole AS owner,
    fdwhandler::regproc AS handler,
    fdwvalidator::regproc AS validator
FROM pg_catalog.pg_foreign_data_wrapper
ORDER BY fdwname;
~~~

### 21.2. Foreign Servers

~~~sql
SELECT
    s.srvname,
    f.fdwname,
    s.srvtype,
    s.srvversion,
    s.srvoptions
FROM pg_catalog.pg_foreign_server AS s
JOIN pg_catalog.pg_foreign_data_wrapper AS f
    ON f.oid = s.srvfdw
ORDER BY s.srvname;
~~~

### 21.3. User Mappings

~~~sql
SELECT
    s.srvname,
    u.umuser::regrole AS local_user,
    u.umoptions
FROM pg_catalog.pg_user_mapping AS u
JOIN pg_catalog.pg_foreign_server AS s
    ON s.oid = u.umserver
ORDER BY s.srvname, local_user;
~~~

User mapping options may contain credentials or secret references. Do not place raw output into widely shared inventory documents; mask them or record only their presence/secret reference.

### 21.4. Foreign Tables

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS foreign_table,
    s.srvname AS server_name,
    f.fdwname
FROM pg_catalog.pg_foreign_table AS ft
JOIN pg_catalog.pg_class AS c
    ON c.oid = ft.ftrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_catalog.pg_foreign_server AS s
    ON s.oid = ft.ftserver
JOIN pg_catalog.pg_foreign_data_wrapper AS f
    ON f.oid = s.srvfdw
ORDER BY n.nspname, c.relname;
~~~

### 21.5. FDW Upgrade Questions

- Does the FDW extension have a target package?
- Do the handler/validator functions exist?
- Are client libraries and TLS dependencies compatible?
- Has the remote database/service changed version or protocol?
- Are user mappings and credentials migrated securely?
- Have query pushdown and transaction semantics changed?
- Are foreign table options still valid?

---

## 22. Event Triggers and Database Hooks

Event triggers can execute code when DDL events occur.

### 22.1. Listing Event Triggers

~~~sql
SELECT
    evtname,
    evtevent,
    evtenabled,
    evttags,
    evtfoid::regprocedure AS trigger_function
FROM pg_catalog.pg_event_trigger
ORDER BY evtname;
~~~

### 22.2. Why Do They Matter?

An event trigger can fire during CREATE/ALTER/DROP operations. Upgrade tools or extension scripts executing DDL may trigger it and produce side effects.

### 22.3. Inspecting Trigger Functions

Check the function language, owner, source/library, and dependencies. C-language event trigger functions require a compatible shared library.

### 22.4. Extension-Owned Event Triggers

Determine whether an event trigger belongs to an extension or was created by the application. Changes to extension-owned triggers must follow the extension upgrade path.

### 22.5. Rehearsal

Run the upgrade rehearsal with the same event triggers enabled. Observe DDL side effects, locks, duration, and logs.

---

## 23. Publications, Subscriptions, and Logical Replication

Logical replication has its own catalog objects and workers.

### 23.1. Publications

~~~sql
SELECT *
FROM pg_catalog.pg_publication;
~~~

### 23.2. Publication Tables

~~~sql
SELECT *
FROM pg_catalog.pg_publication_tables;
~~~

### 23.3. Subscriptions

~~~sql
SELECT
    subname,
    subowner::regrole AS owner,
    subenabled,
    subslotname,
    subpublications,
    subconninfo
FROM pg_catalog.pg_subscription;
~~~

`subconninfo` may contain sensitive information; inspect securely and mask secrets in the inventory.

### 23.4. Upgrade Considerations

- Source/target logical replication compatibility.
- Subscription apply worker behavior.
- Replication slots and WAL retention.
- Publication table/column filters.
- DDL/schema synchronization.
- Sequence state.
- Large objects and objects outside publications.
- CDC consumers and downstream schemas.

### 23.5. Do Not Assume pg_upgrade Transfers All Replication Topologies

Some replication objects, slots, or external CDC states require separate migration steps. Read the guide for your exact PostgreSQL version and rehearse thoroughly.

---

## 24. Server Settings and Preload Libraries

Some extensions must be loaded before the server accepts connections.

### 24.1. Viewing shared_preload_libraries

~~~sql
SHOW shared_preload_libraries;
SHOW session_preload_libraries;
SHOW local_preload_libraries;
~~~

### 24.2. Viewing Related Settings

~~~sql
SELECT
    name,
    setting,
    context,
    source,
    pending_restart
FROM pg_catalog.pg_settings
WHERE name LIKE '%preload%'
ORDER BY name;
~~~

### 24.3. Extensions May Require Preloading

For example, pg_stat_statements and certain extensions require `shared_preload_libraries`. The extension may still exist in pg_extension, yet server startup fails if the library is missing or incompatible.

### 24.4. Custom GUCs

Extensions can define custom configuration parameters. Record the setting, scope, value, and file/source. Do not copy an old parameter to the target if the new extension version changed or removed the setting.

### 24.5. Parameter Files

Your inventory should include:
- postgresql.conf.
- included configuration files.
- postgresql.auto.conf.
- service/environment settings.
- cloud parameter groups.
- systemd/container arguments.

### 24.6. Restart Requirements

`shared_preload_libraries` and several other settings require a server restart. Schedule downtime/rolling procedures according to your HA topology and verify `pending_restart`.

---

## 25. External Binary and Package Inventory

Catalogs cannot fully identify OS packages or dynamic libraries. You must inspect the host or container image.

### 25.1. pg_config

~~~bash
pg_config --version
pg_config --sharedir
pg_config --pkglibdir
pg_config --configure
~~~

These paths help locate extension control/SQL files and shared libraries belonging to the installation.

### 25.2. Package Manager

On Debian/Ubuntu, you can use `dpkg-query` or `apt` to inventory packages. On RHEL/Fedora, use `rpm`/`dnf`. Record the package name, version, architecture, and repository.

### 25.3. Dynamic Library Dependencies

On Linux, `ldd` can help inspect shared library dependencies of an extension `.so`. Never run untrusted binaries; inspect only files from verified packages.

### 25.4. Container Images

Record the image digest/tag, OS base, installed packages, build arguments, and extension build artifacts. Rebuilding the target image from a Dockerfile and lockfiles helps reproduce the environment reliably.

### 25.5. Never Copy Libraries from Source to Target

A C extension must match the PostgreSQL server ABI, architecture, libc, and dependent libraries. Install packages or build artifacts specifically for the target.

### 25.6. Build Toolchain

If an extension is built from source, inventory the compiler, make, PostgreSQL server headers, `pg_config`, C/C++ libraries, and source version. Build on the target environment or a vendor-supported compatible environment.

---

## 26. Client Drivers, Applications, and ORMs

The database server may upgrade successfully while clients still fail due to driver or protocol assumptions.

### 26.1. libpq

Many drivers and tools use libpq. Check the client library version, SSL/authentication support, and connection behavior.

### 26.2. JDBC

Java applications may use the PostgreSQL JDBC driver. Inventory the artifact version, JDK version, connection properties, prepared statements, and type mappings.

### 26.3. psycopg and the Python Ecosystem

Record the driver version, Python runtime, binary/wheel dependencies, async APIs, and type adapters.

### 26.4. Npgsql / .NET

Record the Npgsql version, .NET runtime, type mappings, enum/composite registrations, and connection pool behavior.

### 26.5. Node.js, Go, and Other Drivers

Record package/module versions, runtime versions, TLS/authentication support, and custom codecs.

### 26.6. ORMs

ORMs can generate SQL or migration DDL that depends on the PostgreSQL version. Check:
- Dialect/version support.
- Enum/domain/custom type mappings.
- JSON/JSONB, arrays, ranges, and composite mappings.
- Generated SQL.
- Identity/sequence behavior.
- Migration framework version.

### 26.7. Do Not Just Ask Whether the Driver Can Connect

A driver might connect successfully yet serialize/deserialize custom types or handle protocol features incorrectly. Test application workflows and type round trips.

---

## 27. Operational Tools and Automation

Inventory every tool that touches the cluster or data directory.

### 27.1. Upgrade Utilities

- `pg_upgrade` binary from the target installation.
- `pg_dump`/`pg_restore` versions.
- `pg_dumpall` for global objects.
- `pg_checksums`/`pg_controldata` if used in the workflow.
- `pg_config` and build toolchain.

### 27.2. Backup/Recovery Tools

- `pg_basebackup`.
- pgBackRest, Barman, or an equivalent solution.
- Cloud snapshot/backup agents.
- WAL archive/restore scripts.
- Encryption/KMS clients.
- Restore orchestration.

### 27.3. HA/Failover Tools

- Patroni.
- repmgr.
- pg_auto_failover.
- Cloud failover managers.
- DCS/consensus services.
- Proxy/service discovery.

### 27.4. Monitoring/Logging

- Prometheus exporters.
- Grafana agents.
- Log collectors.
- APM/tracing agents.
- Custom SQL monitoring jobs.

### 27.5. Poolers/Proxies

- PgBouncer.
- Pgpool-II.
- Cloud proxies.
- Service mesh/network gateways.

### 27.6. CDC and Integration

- Debezium.
- Kafka Connect.
- Logical decoding consumers.
- ETL/ELT tools.
- Data warehouse connectors.
- Foreign data integrations.

### 27.7. Scheduled Jobs

- pg_cron.
- OS cron/systemd timers.
- Kubernetes CronJobs.
- Airflow/other orchestrators.
- Application background workers.

### 27.8. Upgrade Compatibility

Each tool requires confirmation of source/target major version support, protocol compatibility, catalog assumptions, extension dependencies, backup formats, replication slot behavior, and failover/reconnect behavior.

---

## 28. Inventorying Global Objects and Cluster-Level Dependencies

Some objects do not belong to a single database.

### 28.1. Roles

~~~sql
SELECT
    rolname,
    rolsuper,
    rolinherit,
    rolcreaterole,
    rolcreatedb,
    rolreplication,
    rolbypassrls,
    rolcanlogin
FROM pg_catalog.pg_roles
ORDER BY rolname;
~~~

Do not export password hashes into broadly shared inventories.

### 28.2. Tablespaces

~~~sql
SELECT
    spcname,
    pg_catalog.pg_get_userbyid(spcowner) AS owner,
    pg_catalog.pg_tablespace_location(oid) AS location
FROM pg_catalog.pg_tablespace
ORDER BY spcname;
~~~

The target host must have the corresponding storage paths and permissions.

### 28.3. Database Properties

~~~sql
SELECT
    datname,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate,
    datctype
FROM pg_catalog.pg_database
ORDER BY datname;
~~~

Locale provider/version columns depend on the PostgreSQL version. Inspect the schema before running on older sources.

### 28.4. Replication Configuration

Record `primary_conninfo`, `primary_slot_name`, `archive_command`/`restore_command`, `synchronous_standby_names`, and replication slots. Secrets in connection strings must be masked.

### 28.5. Config Dependencies

Record config include paths, TLS cert/key files, authentication configs, service environment variables, and secret references. Never store private keys or passwords in the inventory.

---

## 29. Identifying Object Dependencies and Application Usage

An object may exist without active application usage; conversely, an object may be invoked indirectly via a view, function, or trigger.

### 29.1. Finding Dependencies of an Object

pg_depend stores dependency edges between catalog objects. Use `pg_describe_object` to read object identities.

~~~sql
SELECT
    pg_catalog.pg_describe_object(
        d.classid, d.objid, d.objsubid
    ) AS dependent_object,
    pg_catalog.pg_describe_object(
        d.refclassid, d.refobjid, d.refobjsubid
    ) AS referenced_object,
    d.deptype
FROM pg_catalog.pg_depend AS d
WHERE d.refobjid = 'public.some_type'::regtype
ORDER BY dependent_object;
~~~

Adjust the object reference for the specific type/table/function you are checking. Not every dependency can be queried with a `regtype` cast.

### 29.2. Dependency Types

pg_depend includes dependency types such as normal, automatic, internal, extension membership, and others. How an object is dropped or upgraded depends on its dependency type.

### 29.3. Dependencies Do Not Equal Runtime Usage

Catalog dependencies show relationships recorded by PostgreSQL; they do not prove whether the object is called by applications in production.

### 29.4. Runtime Usage Evidence

Combine:
- pg_stat_statements.
- Application logs/traces.
- Query logs.
- Database audit logs.
- Deployment/config repositories.
- Owner interviews.
- Scheduled jobs and ETL definitions.

### 29.5. Do Not Mark Something Unused Just Because It Was Not Seen in a Short Window

A function might only run at month-end or during DR. Check business cycles and telemetry retention windows.

---

## 30. Building a Compatibility Matrix

The compatibility matrix is the document that decides which dependencies are cleared to move to the target.

### 30.1. Dimensions to Compare

- PostgreSQL source major/minor.
- PostgreSQL target major/minor.
- Extension name/version.
- Extension package/binary build.
- OS distribution/version.
- CPU architecture.
- libc/ICU/OpenSSL/GEOS/PROJ/GDAL or related libraries.
- Client driver/runtime.
- Backup/HA/monitoring tool version.
- External service/remote database version.

### 30.2. Compatibility Statuses

| Status | Meaning | Action |
| --- | --- | --- |
| Supported | Vendor/project confirms target support | Plan testing |
| Tested internally | Successfully rehearsed with a representative workload | Document evidence and limitations |
| Conditional | Requires pre/post steps or specific configuration | Fulfill conditions |
| Unknown | No evidence yet | Do not treat as ready |
| Unsupported | Vendor does not support or known incompatibility | Upgrade dependency / redesign |
| Retired | No longer maintained | Find replacement or migration path |

### 30.3. Evidence to Record

- Link/version of release notes.
- Package build identifier.
- Test date/environment.
- SQL smoke test results.
- Binary load test.
- Performance comparison.
- Known limitations.
- Owner approval.

### 30.4. Do Not Default to the Latest Version Automatically

The newest extension release may drop support for the source version or require an intermediate upgrade. Choose versions based on the compatibility matrix and vendor guidance.

### 30.5. Compatibility Has Multiple Layers

An extension may have compatible SQL scripts while having an incompatible C binary, missing remote libraries, changed index opclasses, or changed performance characteristics. Mark it "compatible" only once all relevant layers are verified.

---

## 31. How Do pg_upgrade and Dump/Restore Affect Dependencies?

### 31.1. pg_upgrade

pg_upgrade converts cluster data files between major versions under supported conditions, reducing downtime compared to dump/restore for large clusters.

Dependency requirements:
- Target server binaries.
- Target extension shared libraries.
- Matching extension packages/SQL scripts.
- OS/architecture requirements.
- Tablespace paths.
- Upgrade checks and pre/post steps.

### 31.2. pg_upgrade --check

Run check mode to detect certain incompatibilities before executing. This is an important check, but it does not replace the compatibility matrix, vendor docs, and application tests.

### 31.3. pg_upgrade Does Not Automatically Resolve Every Extension Update

The extension SQL version may remain at the old version after conversion. You must run ALTER EXTENSION UPDATE according to the extension documentation and your rehearsed plan.

### 31.4. Dump/Restore

`pg_dump`/`pg_restore` recreates schemas and data through a logical representation. This can be useful when changing OS/architecture or performing major migrations, though it can take longer and requires checking custom types, extension objects, ownership, and restore ordering.

### 31.5. Extension Binaries Still Require Target Packages

Whether you use `pg_upgrade` or dump/restore, the target server still requires the extension packages/libraries if database objects invoke them.

### 31.6. Global Objects

Roles, tablespaces, and certain cluster-wide settings require separate procedures. `pg_dumpall --globals-only` can help export global objects, though it must be reviewed before applying.

### 31.7. Do Not Treat One Upgrade Method as a Cure-All for Every Dependency

Choose your method based on database size, downtime budget, platform changes, extension support, data transformations, and rollback strategy.

---

## 32. Checking pg_upgrade Before Rehearsal

### 32.1. Identify the Target Binary

Use `pg_upgrade` from the target installation and verify the matching version/help output.

### 32.2. Run --check

~~~bash
pg_upgrade --check \
  --old-datadir=/path/to/old/data \
  --new-datadir=/path/to/new/data \
  --old-bindir=/path/to/old/bin \
  --new-bindir=/path/to/new/bin
~~~

Exact options and paths depend on the platform and installation layout. Read the `pg_upgrade` documentation for the target major version.

### 32.3. Inspect Extension Warnings

If the tool warns about missing or incompatible extensions/libraries, resolve them before performing the actual upgrade. Do not ignore warnings just because the cluster still runs on the source.

### 32.4. Check Locale/Collation

Evaluate locale changes and dependent indexes. Plan REINDEX/refresh steps according to PostgreSQL guidance.

### 32.5. Check Data Type Usage

Cross-check custom types, functions, operators, and extension versions against the target packages. Run application-specific tests.

### 32.6. Check Mode Does Not Replace Rehearsal

`--check` does not prove that backup/restore, application drivers, FDWs, HA, monitoring, and scheduled jobs work properly.

---

## 33. Extension Upgrade Planning

### 33.1. Identify Source/Target Versions

Gather `extversion` from `pg_extension` and target package versions from `pg_available_extension_versions` on the target.

### 33.2. Read Vendor Release Notes

Identify supported PostgreSQL majors, minimum/maximum extension versions, intermediate update paths, pre/post scripts, binary ABI/build requirements, breaking SQL/API changes, and index rebuild requirements.

### 33.3. Inspect Update Paths

Use `pg_extension_update_paths` if available. Record the chosen path and the scripts that will execute.

### 33.4. Test ALTER EXTENSION UPDATE

On a clone/staging environment, run the concrete command:

~~~sql
ALTER EXTENSION extension_name UPDATE TO 'target_extension_version';
~~~

Do not run this placeholder verbatim; substitute the verified extension/version and use the appropriate owner/privileges.

### 33.5. Update Order

If extension A requires B, follow the dependency order specified by the vendor/documentation. Do not assume all extensions can be updated in parallel.

### 33.6. Extensions Without an Update Path

These may require dump/restore, an intermediate release, a migration script, or vendor support. Do not casually DROP/CREATE an extension if it manages data or configuration.

### 33.7. Post-Update Verification

- extversion.
- Objects/functions/operators/types.
- Extension-owned indexes.
- Query behavior.
- Application type mappings.
- Logs and extension background workers.

---

## 34. Testing Data Types and Application Compatibility

### 34.1. Type Round-Trip

For every critical custom type, test:
- Insert.
- Select.
- Cast.
- Comparison.
- Sort.
- Index lookup.
- Binary/text serialization.
- Null/edge values.
- Array/composite nesting if applicable.

### 34.2. Enum

Test all labels, ordering, casts, constraints, and application deserialization.

### 34.3. Domain

Test CHECK/NOT NULL/default constraints and validation failures.

### 34.4. Composite

Test field order, null handling, function return values, and client driver mappings.

### 34.5. Range/Multirange

Test inclusive/exclusive bounds, empty ranges, overlaps, operators, indexes, and timezone/date semantics.

### 34.6. Collation

Test ORDER BY, equality, unique constraints, case/accent behavior, and indexes after a collation provider upgrade.

### 34.7. Custom C Types

Test input/output, binary send/receive, comparison/hash, indexes, and extension shared library loading.

### 34.8. Do Not Test Only Schema Creation

A schema may restore cleanly while the application driver fails to serialize a type or query plans shift. End-to-end application tests are required.

---

## 35. Special Risks to Check

### 35.1. Unmaintained Extensions

Look up release history, supported PostgreSQL versions, security fixes, and migration paths. If target support is absent, find a replacement or remain on the source version until a plan is ready.

### 35.2. C Extension Build Mismatches

Verify the server major version, architecture, compiler ABI, and dependent libraries. Never copy old binaries.

### 35.3. Preloaded Extensions

The server can fail at startup if `shared_preload_libraries` contains a library missing on the target.

### 35.4. Collation Drift

OS/ICU updates can alter sorting behavior. Inventory collation-dependent indexes and establish a REINDEX plan.

### 35.5. Custom Types With Binary Storage

If a type stores data in a custom binary representation, a vendor-confirmed upgrade path or migration procedure is required.

### 35.6. User Mappings and Secrets

FDW connection strings may contain credentials. The inventory must record the secret reference and owner, never plaintext secrets.

### 35.7. Drivers Missing Support for New/Old Types

Some drivers require explicit registration for enums/composites/ranges or experience type OID/mapping changes. Test client round trips.

### 35.8. Incompatible Backup Tools

A tool may not support the target major version or backup format. Test restores on the target version.

### 35.9. Monitoring Queries Failing After Upgrade

Statistics view columns may change. Check exporter SQL collectors, dashboards, and alerts.

### 35.10. Replication/CDC Slot State

Logical decoding plugins and CDC connectors require target compatibility. Check slot `restart_lsn`, plugin, consumer offsets, and rebootstrap plans.

---

## 36. Creating a Reproducible Inventory

### 36.1. Save Raw Query Outputs

Save the timestamp, cluster identity, database name, PostgreSQL version, and the command/query used. Do not simply copy a few result rows into a ticket.

### 36.2. Record OS Packages

Save package names, versions, architectures, and repositories. For containers, save image digests and lockfiles.

### 36.3. Record Binary Locations

Save `pg_config` sharedir/pkglibdir and the list of extension `.control`, SQL scripts, and shared libraries. On the target, compare against the package manifest.

### 36.4. Record Configuration

Save effective settings, source files, and `pending_restart`. Mask secrets.

### 36.5. Record Application Inventory

Save services, runtimes, drivers, ORMs, poolers, scheduled jobs, and owners.

### 36.6. Record Evidence

Each row in the inventory should include:
- Compatibility status.
- Evidence URL/document.
- Tested version.
- Test result.
- Owner.
- Required action.
- Cutover/rollback notes.

### 36.7. Version-Control the Inventory

Store the inventory in a repository or secure documentation with revision history. Secrets and credentials must be referenced via a secret manager, never committed in plaintext.

---

## 37. Inventory and Compatibility Matrix Templates

### 37.1. Extension Inventory

| Database | Extension | Installed Version | Target Package Version | Preload | Dependencies | Owner | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| appdb | extension_a | 1.4 | 1.6 | yes/no | extension_b | team | Unknown |
| analytics | extension_c | 2.1 | 2.3 | no | OS library | team | Tested |

The rows above are formatting examples only, not data from a real cluster.

### 37.2. Data Type Inventory

| Schema | Type | Kind | Extension-Owned | Used By | Compatibility Evidence |
| --- | --- | --- | --- | --- | --- |
| app | order_status | enum | no | orders.status | Type round-trip |
| app | currency_amount | domain | no | invoices | Constraint test |
| geo | geometry | base/extension | yes | spatial tables | Vendor support |

### 37.3. External Tools Inventory

| Tool | Version | Runs Where | Connects To | Target Support | Owner |
| --- | --- | --- | --- | --- | --- |
| JDBC driver | version | application | PostgreSQL | confirmed/pending | app team |
| Backup agent | version | backup host | cluster/storage | confirmed/pending | DBA |
| Exporter | version | monitoring | pg_catalog | confirmed/pending | SRE |
| Pooler | version | proxy host | PostgreSQL | confirmed/pending | platform |

### 37.4. Risk Register

| Dependency | Failure Mode | Impact | Mitigation | Test | Owner |
| --- | --- | --- | --- | --- | --- |
| C extension | library fails to load | Server/function unavailable | Target build | Startup + SQL test | DBA/vendor |
| ICU collation | index order mismatch | Query/unique behavior | REINDEX plan | Collation tests | DBA |
| Driver | custom type decode fails | App errors | Driver upgrade | Round-trip test | App team |
| FDW | remote library/protocol fails | Integration unavailable | Upgrade package/endpoint | Remote query test | Integration team |

---

## 38. Pre-Upgrade Inventory Process

### Step 1: Define Scope

Document source/target major versions, databases, hosts, OS/architecture, topology, and downtime objectives.

### Step 2: Collect Catalog Inventory

Run queries for extensions, available versions, extension objects, types, functions, languages, collations, operators, opclasses, FDWs, event triggers, and replication objects.

### Step 3: Collect Server Configuration

Gather `shared_preload_libraries`, settings with custom values, config include files, authentication, TLS, archive, and replication settings. Mask secrets.

### Step 4: Collect Host/Package Inventory

List PostgreSQL packages, extension packages, shared libraries, dependent OS packages, build toolchains, and container images.

### Step 5: Collect Application/Tool Inventory

List drivers, ORMs, migration tools, poolers, backup, monitoring, HA, CDC, ETL, and scheduled jobs.

### Step 6: Build the Dependency Graph

Connect database objects to extensions, extensions to shared libraries, applications to types/functions, FDWs to remote services, and tools to PostgreSQL versions.

### Step 7: Assess Compatibility

Every dependency must have a status and evidence. Mark as Unknown if unverified.

### Step 8: Determine Migration Actions

Upgrade packages, rebuild C extensions, run ALTER EXTENSION UPDATE, REINDEX, refresh collation versions, update drivers, replace tools, or prepare data conversions.

### Step 9: Rehearse

Use a clone/restore of production with the same package/config/extension set. Run the upgrade and application tests.

### Step 10: Freeze and Cutover Readiness

Lock the inventory, package versions, artifact hashes, backups, runbooks, owners, and rollback criteria. Allow no package drift after rehearsal.

---

## 39. Runbook: Handling Missing Extensions on the Target

### Step 1: Identify the Extension

Record the database, extname, extversion, owner, schema, and object dependencies.

### Step 2: Inspect the Target Package

Use `pg_available_extensions` and the host package manager. Identify whether the control file, SQL scripts, or shared library is missing.

### Step 3: Verify Target Support

Read vendor release notes, supported PostgreSQL majors, OS/architecture, and dependency libraries.

### Step 4: Install the Right Package for the Target

Use a package/build verified for the target installation. Never copy binaries from the source host.

### Step 5: Check Preload

If the extension requires preloading, update the target config and restart according to plan before serving workload.

### Step 6: Check the Extension Update Path

Identify the version path and pre/post steps.

### Step 7: Rehearse

Restore/clone the database onto the target, load the extension, run the update, and execute application tests.

### Step 8: Record Evidence

Save the package version, library path, extension version, test output, and owner approval.

---

## 40. Runbook: Collation Version Mismatch

### Step 1: List Collations

Gather provider, locale, and recorded collation version.

### Step 2: Compare Actual Version

Use `pg_collation_actual_version` on supported versions and identify mismatches.

### Step 3: Find Dependent Indexes

Check indexes, constraints, and expressions using that collation. Identify table scope and business-critical uniqueness.

### Step 4: Read Release Guidance

Review PostgreSQL and OS/ICU vendor instructions. Determine the order of REINDEX and REFRESH VERSION.

### Step 5: Plan the Rebuild

Estimate disk, I/O, locks, and downtime/concurrency. Choose REINDEX or an appropriate method based on requirements.

### Step 6: Test Comparison Semantics

Test ORDER BY, equality, unique indexes, and application sorting.

### Step 7: Refresh Metadata After Rebuild

Update the recorded collation version only after all dependent objects have been handled according to procedure.

---

## 41. Lab 1: Inventorying Extensions in a Database

Use a lab or staging database.

### 41.1. List Extensions

~~~sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS extension_schema,
    extowner::regrole AS owner,
    extrelocatable
FROM pg_catalog.pg_extension
ORDER BY extname;
~~~

### 41.2. List Available Versions

~~~sql
SELECT
    name,
    version,
    installed,
    requires,
    trusted,
    relocatable
FROM pg_catalog.pg_available_extension_versions
ORDER BY name, version;
~~~

### 41.3. Count Objects

Use `pg_depend` to count extension members.

### 41.4. Compare with Target

Run the queries on the target clone and compare installed vs. available versions.

### 41.5. Record Results

Create an inventory with extension name, source version, target package version, dependencies, preload, owner, and compatibility status.

---

## 42. Lab 2: Inventorying Custom Types and Dependencies

### 42.1. List User-Defined Types

Use `pg_type`/`pg_namespace` and classify by `typtype`.

### 42.2. List Enum Labels

Use `pg_enum` and record sort order.

### 42.3. List Domains

Use `pg_type`/`pg_constraint` and record base type, defaults, and constraints.

### 42.4. List Composite Attributes

Use `pg_class`/`pg_attribute`/`pg_type` and record field ordering.

### 42.5. Find Columns Using Custom Types

Use `information_schema.columns` or catalog joins.

### 42.6. Conclusion

Cross-reference types with extension ownership, application mappings, and migration test cases.

---

## 43. Lab 3: Finding C Functions and Preload Requirements

### 43.1. List C Functions

Join `pg_proc` with `pg_language` to retrieve `probin`/`prosrc`.

### 43.2. View Preload Settings

~~~sql
SHOW shared_preload_libraries;
SHOW session_preload_libraries;
~~~

### 43.3. View Library Paths

On the host:

~~~bash
pg_config --pkglibdir
pg_config --sharedir
~~~

### 43.4. Check Packages

Cross-reference library files with the OS package manifest and target installation. On Linux, check dynamic dependencies using the appropriate tool.

### 43.5. Rehearsal

Start the target server with the exact preload list and run smoke tests invoking the C functions.

### 43.6. Conclusion

A catalog function can exist in the database while its library implementation fails to load on the target.

---

## 44. Lab 4: Inventorying Collations and Indexes

### 44.1. List Collations

Gather provider, locale, recorded version, and actual version if available.

### 44.2. Find Mismatches

Compare `collversion` against `pg_collation_actual_version`.

### 44.3. Identify Dependent Objects

Find indexes/constraints using the collation. Use catalog dependencies and index definitions.

### 44.4. Test Semantics

Create a dataset containing uppercase/lowercase characters, accents, and locale-specific characters in the lab. Compare sorting and equality on source and target.

### 44.5. Rebuild Rehearsal

On the clone, execute REINDEX according to plan and then refresh the collation version per documentation.

### 44.6. Conclusion

Locale/provider changes are a dependency of data semantics and indexes, not merely an OS configuration detail.

---

## 45. Lab 5: Compatibility Rehearsal

### 45.1. Prepare a Clone

Restore a recent production-like backup into staging. Keep the package, config, and extension set equivalent.

### 45.2. Install Target Binaries and Packages

Install target PostgreSQL, extension packages, dependent libraries, and operational tools.

### 45.3. Run Upgrade Check

Use `pg_upgrade --check` or the check procedure matching your upgrade method.

### 45.4. Execute Rehearsal

Run extension updates, the collation plan, and all identified migration steps.

### 45.5. Test Clients

Connect using each driver/ORM/pooler version; test custom types, functions, transactions, authentication, and TLS.

### 45.6. Test Operations

Run backups, restores, monitoring collectors, HA/failover, CDC, and scheduled jobs.

### 45.7. Record Timings and Issues

Record downtime, per-step duration, warnings, manual actions, and the rollback point. Do not finalize a production plan if any critical dependency remains Unknown.

---

## 46. Practice Exercises

### Exercise 1 — Dependency Scope

List the dependency layers beyond tables and indexes that must be inventoried before a major upgrade.

### Exercise 2 — Installed vs. Available

Distinguish between `pg_extension`, `pg_available_extensions`, and `pg_available_extension_versions`.

### Exercise 3 — Extension Inventory

Write a query to retrieve extension name, `extversion`, schema, owner, and relocatable flag.

### Exercise 4 — Multi-Database

Why must the extension inventory be run in every database of the cluster?

### Exercise 5 — Update Path

Explain why having the target package does not prove there is an `ALTER EXTENSION UPDATE` path.

### Exercise 6 — Extension Dependencies

Find extensions with `requires` and describe how to represent the dependency chain.

### Exercise 7 — Extension-Owned Objects

Use `pg_depend` and `pg_describe_object` to list the member objects of an extension.

### Exercise 8 — Preload

Inspect `shared_preload_libraries` and describe the risk when a target library is missing.

### Exercise 9 — Type Taxonomy

Distinguish base, composite, domain, enum, range, multirange, and pseudo-types.

### Exercise 10 — Custom Columns

Write a query to find table columns using user-defined types.

### Exercise 11 — Enum Ordering

Why must enum sort order be preserved? List post-upgrade tests.

### Exercise 12 — Domain Constraints

Inventory the base type, default, and CHECK constraints of domains.

### Exercise 13 — Composite Types

Find the fields of composite types and explain why field order matters to clients.

### Exercise 14 — Range Types

List the subtype, collation, canonical function, and subtype diff function of ranges.

### Exercise 15 — C Functions

Find C-language functions, library names, and symbols. Explain why binaries must be built for the target.

### Exercise 16 — Procedural Languages

Inventory the language and runtime dependencies of PL/Python or PL/Perl.

### Exercise 17 — Collations

List collations by provider and locale. Explain recorded vs. actual versions.

### Exercise 18 — Collation Mismatch

An ICU upgrade changes collation versions. Create a dependent index rebuild and validation plan.

### Exercise 19 — Casts

Inventory user-defined casts and the functions performing the conversions.

### Exercise 20 — Operators

Inventory operators outside `pg_catalog` along with their implementation functions.

### Exercise 21 — Operator Classes

Explain why extension opclasses/access methods require target binaries and index tests.

### Exercise 22 — FDW

Inventory FDWs, foreign servers, foreign tables, and user mappings. Describe how to protect secrets.

### Exercise 23 — Event Triggers

Find event triggers and explain the risks when upgrade scripts execute DDL.

### Exercise 24 — Logical Replication

Inventory publications/subscriptions, slots, plugins, and CDC consumers.

### Exercise 25 — OS Packages

Design a package inventory for PostgreSQL extensions on Linux/containers.

### Exercise 26 — Client Drivers

Inventory JDBC, psycopg, Npgsql, or the driver in use along with custom type mappings.

### Exercise 27 — Operational Tools

List backup, monitoring, HA, pooler, CDC, ETL, and scheduler tools requiring target support confirmation.

### Exercise 28 — pg_upgrade

Explain what `pg_upgrade --check` detects and which tests it cannot replace.

### Exercise 29 — Dump/Restore

Compare dump/restore against `pg_upgrade` regarding dependencies, downtime, and platform changes.

### Exercise 30 — Extension Update

Write a runbook from source `extversion` to target package, update path, rehearsal, and post-upgrade validation.

### Exercise 31 — Unknown Dependency

An extension has no release notes for the target version. Decide its compatibility status and next steps.

### Exercise 32 — Missing Library

The target server fails to load a C library at startup. Outline the sequence to check package, path, ABI, and dependent libraries.

### Exercise 33 — Driver Mismatch

The database was upgraded, but the ORM cannot read a custom enum/composite. Propose checks and tests.

### Exercise 34 — Collation and Uniqueness

How can a collation change affect a unique index? Build a validation plan.

### Exercise 35 — Dependency Graph

Draw a graph: application → function/type → extension → shared library → OS package.

### Exercise 36 — Ownership

Design an owner/escalation table for dependencies not owned by the DBA team.

### Exercise 37 — Inventory Drift

After rehearsal, a package version on the target changes. Why must you freeze artifacts and re-run compatibility checks?

### Exercise 38 — Security

An FDW user mapping contains a password in its options. How do you inventory it without putting plaintext secrets into documentation?

### Exercise 39 — Rollback

State the conditions needed to retain the source cluster, backups, extension packages, and application deployment to roll back after a failed cutover.

### Exercise 40 — End-to-End Upgrade

A cluster uses PostGIS, pg_cron, pg_stat_statements, a custom C extension, enum/domain types, an ICU collation, postgres_fdw, JDBC/Npgsql clients, PgBouncer, a backup agent, and CDC. Build the inventory, dependency graph, compatibility matrix, rehearsal plan, upgrade steps, validation, and rollback criteria for a major-version upgrade.

---

## 47. Pre-Readiness Sign-Off Checklist

| Item | What to Confirm |
| --- | --- |
| Source/target | PostgreSQL versions, OS, and architecture |
| Databases | All databases inventoried |
| Extensions | extname/extversion/owner/schema |
| Available packages | Target packages and versions available |
| Update paths | Source-to-target extension paths |
| Extension dependencies | requires chain and order |
| Extension objects | pg_depend membership |
| Preload | shared/session/local preload libraries |
| Custom types | Base/composite/domain/enum/range/multirange |
| Type usage | Columns, function arguments/returns, indexes |
| Enum labels | Values and sort order |
| Domain constraints | Base type, default, validation |
| Composite fields | Field names/order/types |
| C functions | probin, prosrc, and library ABI |
| Procedural languages | Runtime/interpreter packages |
| Casts/operators | Implementation functions |
| Operator classes | Access methods and dependent indexes |
| Collations | Provider, locale, recorded/actual versions |
| Collation indexes | REINDEX plan and validation |
| FDW | Wrapper/handler/validator packages |
| Foreign servers | Remote endpoint compatibility |
| User mappings | Secret references and owners |
| Event triggers | DDL side effects |
| Publications/subscriptions | Logical replication/CDC plan |
| Global objects | Roles, tablespaces, and privileges |
| Configuration | Preload, custom GUCs, config includes |
| OS packages | Versions, architecture, repositories |
| Shared libraries | Paths and dependent libraries |
| Client drivers | Version/runtime/type mapping support |
| ORMs/migrations | Dialect and generated SQL support |
| Poolers/proxies | Protocol, reconnect, and auth support |
| Backup tools | Target version support and restore test |
| HA tools | Failover and rejoin support |
| Monitoring | Exporter queries and dashboard compatibility |
| CDC/ETL | Plugins, slots, offsets, and schema evolution |
| Scheduled jobs | pg_cron/external scheduler owners |
| Compatibility evidence | Vendor docs and internal tests |
| Rehearsal | Same packages/config/data shape |
| Rollback | Backup, source retention, and trigger conditions |
| Owners | Named team/contact for each dependency |
| Freeze | Package/image/config artifacts pinned |

## Conclusion

Inventorying extensions, data types, and dependent tools is the foundational step for upgrading PostgreSQL safely. `pg_extension` reveals extensions installed in each database; `pg_available_extensions` and `pg_available_extension_versions` show packages visible to the server; `pg_depend` helps trace objects owned by extensions. `pg_type` and related catalogs describe custom types, while `pg_proc`/`pg_language`, `pg_collation`, FDWs, event triggers, and replication catalogs uncover deeper dependencies.

Key principles to remember:

1. **Inventory every database.** Extensions are installed per database; you cannot infer the whole cluster from a single database result.
2. **Separate installed extensions from server packages.** Database metadata does not prove the target host has control files, SQL scripts, and shared libraries.
3. **Record versions and update paths.** Extensions need target packages and a vendor-supported upgrade path.
4. **Trace extension-owned objects.** Use `pg_depend` to understand object scope and dependencies.
5. **Inventory all custom types.** Enums, domains, composites, ranges, and base types can appear in columns, functions, indexes, and application protocols.
6. **Check C libraries and preloads.** Binaries must match the target PostgreSQL major version, OS, architecture, and dependent libraries.
7. **Do not overlook collations.** libc/ICU version drift may require rebuilding indexes before refreshing metadata.
8. **FDWs and user mappings depend on external systems.** Check remote endpoints, libraries, protocols, and secret references.
9. **The client stack also needs upgrading.** Drivers, ORMs, poolers, backup, HA, monitoring, CDC, and ETL can become failure points after cutover.
10. **pg_upgrade --check does not replace rehearsal.** It does not prove that all applications and external tools work correctly.
11. **Every dependency needs an owner and evidence.** Unknown must never be treated as compatible.
12. **Freeze artifacts after rehearsal.** Package/image/config drift can invalidate rehearsal results.
13. **Test type behavior end-to-end.** Successful schema restore is not enough; test serialization, operators, indexes, constraints, and application workflows.
14. **Keep the rollback path viable.** Backups, the source cluster, packages, and application deployments must align with rollback conditions.

An upgrade is ready when every critical dependency has a target version, migration path, owner, compatibility evidence, and passing tests. A thorough inventory turns an upgrade from a mere server binary swap into a controlled change across the entire PostgreSQL ecosystem.
