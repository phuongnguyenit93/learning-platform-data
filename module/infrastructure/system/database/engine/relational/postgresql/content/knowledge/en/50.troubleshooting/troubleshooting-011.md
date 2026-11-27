# Incidents After Upgrades, Collation Changes, or Extension Updates in PostgreSQL

A PostgreSQL upgrade or operating system library update can alter database behavior even when data opens cleanly and the server starts successfully. Applications may encounter missing functions, unloadable shared libraries, changed query sort orders, unique indexes no longer matching string equality semantics, or extensions incompatible with the new major version.

Three categories of change must be distinguished:

- **PostgreSQL upgrade:** changing the binary/server version, catalog, or data directory through a major or minor upgrade procedure.
- **Collation change:** updating the provider or libc/ICU library version, altering text comparison and sorting rules.
- **Extension change:** updating host packages/binaries, SQL objects inside individual databases, or preload settings.

All three can occur within the same maintenance window. Therefore, when an incident occurs after an upgrade, determine which component changed, which databases are impacted, which objects depend on it, and the cluster's current state before running repair commands.

This lesson focuses on investigating and recovering from upgrade regressions, collation drift, and extension incompatibilities. The emphasis is on preserving evidence, verifying compatibility, rebuilding affected objects, and returning databases and applications to a verifiable healthy state.

~~~mermaid
flowchart TD
    A["Post-upgrade / collation / extension incident"] --> B["Contain: halt rollout and further changes"]
    B --> C["Verify cluster, version, packages, logs"]
    C --> D{"Cause category"}
    D -->|"PostgreSQL upgrade"| E["Binary, catalog, config, app compatibility"]
    D -->|"Collation drift"| F["Provider version, dependent indexes"]
    D -->|"Extension"| G["Package, shared library, SQL version, preload"]
    E --> H["Select recovery plan"]
    F --> H
    G --> H
    H --> I["Repair / reindex / update / restore"]
    I --> J["Schema, data, app, replication checks"]
    J --> K{"Acceptance criteria met?"}
    K -->|"No"| L["Keep incident open and escalate"]
    K -->|"Yes"| M["Sign off and close change"]
~~~

This lesson belongs to the **Troubleshooting** chapter of the **Database Engine Relational PostgreSQL** module.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Distinguish incidents caused by PostgreSQL upgrades, collation version drift, and extension incompatibility.
2. Gather cluster identity, server version, package versions, and upgrade evidence.
3. Recognize common symptoms following major and minor upgrades.
4. Understand how `libc` and `ICU` collation providers affect text comparison.
5. Compare recorded collation versions against actual provider versions.
6. Identify indexes and objects dependent on changed collations.
7. Plan `REINDEX` and collation version refreshes in a safe order.
8. Distinguish extension packages, shared libraries, and SQL extension versions.
9. Check extension availability, update paths, and dependencies.
10. Troubleshoot missing shared libraries, undefined symbols, and update script failures.
11. Manage `shared_preload_libraries` and restart requirements.
12. Structure post-`pg_upgrade` or post-dump/restore verification workflows.
13. Verify configuration, roles, grants, sequences, replication, and CDC.
14. Choose between rollback, forward-fix, and restore based on data state.
15. Design post-maintenance monitoring and acceptance checks.
16. Collect evidence and build runbooks with clear stop conditions.

## 2. Classifying Post-Upgrade Incidents

An error appearing right after maintenance does not necessarily come from PostgreSQL core. It may stem from the OS, extensions, application drivers, collation providers, or configuration.

| Category | Common Change | Symptoms |
| --- | --- | --- |
| PostgreSQL major upgrade | Binary and catalog/data format | Startup, catalog, SQL behavior, or extension errors |
| PostgreSQL minor update | Bug fixes, binary/package | Crashes, behavior shifts, or package mismatches |
| OS/library upgrade | libc, ICU, OpenSSL, timezone data | Collation mismatch, TLS/auth errors |
| Collation update | Sort/equality semantics | Warnings, index inconsistency, unique conflicts |
| Extension package update | Shared libraries, control files, SQL scripts | Missing library, symbol errors, missing update path |
| Extension SQL update | Extension catalog objects | Missing functions/types/operators or dependency errors |
| Configuration migration | Renamed or removed parameters | Startup warnings/errors, ignored settings |
| Application upgrade | Driver/ORM/query behavior | Prepared statements, type mapping, query regressions |
| Replication/CDC | Protocol, schema, slot state | Subscriber/connector lag or apply failures |

Never deduce the root cause solely from error timing. Correlate maintenance timelines, server logs, package changes, migration records, and application rollouts.

## 3. First Rule: Contain and Preserve Evidence

When an incident is detected:

1. Halt further rollouts and unrelated changes.
2. Determine whether to keep traffic on a compatible version or enter maintenance mode.
3. Do not reflexively run `REINDEX`, `ALTER EXTENSION`, `REFRESH COLLATION VERSION`, or `DROP EXTENSION`.
4. Save PostgreSQL logs, OS/package logs, upgrade logs, and application errors.
5. Record cluster/database identity, server version, and extension versions.
6. Check backup, WAL archive, and PITR readiness.
7. Identify primary/standby roles, replication slots, and CDC consumers.
8. Record the exact time of the first error and the immediately preceding change.

If the database is running yet returning wrong results or showing signs of corruption, prioritize preserving state and escalating. Never run bulk repair commands before understanding the blast radius.

## 4. Verifying the Right Cluster and PostgreSQL Version

Before investigating, confirm your session is connected to the intended target:

~~~sql
SELECT
    current_database() AS database_name,
    current_user AS database_user,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    version() AS server_version,
    current_setting('server_version_num') AS server_version_num,
    pg_is_in_recovery() AS is_standby,
    pg_postmaster_start_time() AS server_started_at;
~~~

Inspect cluster control metadata on the host with the matching binary:

~~~bash
pg_controldata /path/to/data-directory
~~~

`pg_controldata` provides the system identifier, catalog version, cluster state, checkpoint info, and checksum metadata. Point it at the exact data directory using the matching tool version.

Record:

- Cluster/system identifier.
- Before/after PostgreSQL major and minor versions.
- Database name and role.
- Primary/standby state.
- Server start timestamp.
- Data directory and package source.
- Upgrade method.
- Release/change ID.

Never rely solely on hostname or database name to identify a cluster.

## 5. Distinguishing Major Upgrades from Minor Updates

**Minor updates** generally preserve the data directory format within the same major release and deliver bug/security fixes. However, extension packages and OS libraries may also change during the same maintenance window.

**Major upgrades** change the major version and require a data/catalog upgrade procedure, typically `pg_upgrade` or dump/restore/logical migration.

Never use a newer major version binary to open an older major version's data directory directly. Always follow a PostgreSQL-supported upgrade procedure.

### `pg_upgrade`

`pg_upgrade` moves a cluster across major versions by initializing a new cluster compatible with the target binaries/catalogs and migrating data via a supported mechanism.

Before running:

- Read release notes for both source and target major versions.
- Check operating system, architecture, and binary paths.
- Install extension packages compatible with the target version.
- Run `pg_upgrade --check`.
- Verify tablespaces, locales, encodings, and shared libraries.
- Confirm backup/restore paths.
- Check disk space and downtime windows.
- Save upgrade outputs and logs.

Example pre-check:

~~~bash
pg_upgrade --check \
  --old-datadir=/path/to/old/data \
  --new-datadir=/path/to/new/data \
  --old-bindir=/path/to/old/bin \
  --new-bindir=/path/to/new/bin
~~~

Syntax above is illustrative; options and invocation depend on platform and version. Check `pg_upgrade --help` on your target binary.

### Copy Mode vs. Link Mode

- **Copy mode:** copies data files; takes more disk and time, but leaves the source cluster intact for planned rollback.
- **Link mode:** uses hard links to reduce time and disk usage. Once the new cluster starts and modifies shared files, the old cluster can no longer serve as a safe independent rollback copy.

Never rely on a link-mode source directory as a backup once the upgraded cluster begins writing. Always maintain an independent backup or snapshot.

## 6. Post-`pg_upgrade` Tasks

After `pg_upgrade` completes, do not immediately open full production traffic. Steps typically required include:

1. Review all upgrade logs and generated scripts.
2. Verify target cluster identity and version.
3. Confirm configuration files were merged properly.
4. Install and verify extension binaries for the target major version.
5. Update SQL extension versions along supported update paths.
6. Resolve collation version mismatches and rebuild dependent objects.
7. Run `ANALYZE` to generate fresh optimizer statistics.
8. Verify roles, ownership, grants, and authentication.
9. Verify sequences and identity values.
10. Verify replication, logical slots, subscriptions, and CDC.
11. Run application smoke tests.
12. Run post-upgrade data and schema checks.
13. Open traffic via a staged rollout.

`pg_upgrade` does not replace a full operational checklist. In particular, optimizer statistics must be regenerated; review any generated analyze scripts before running them.

## 7. Checking Configuration After an Upgrade

Parameters can be renamed, deprecated, or removed across major versions. Old configuration can emit warnings, be ignored, or prevent server startup.

Inspect:

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context,
    pending_restart
FROM pg_settings
ORDER BY name;
~~~

Verify critical settings for your workload:

- `shared_buffers`.
- `work_mem`.
- `maintenance_work_mem`.
- `max_connections`.
- `wal_level`.
- `max_wal_senders`.
- `max_replication_slots`.
- `shared_preload_libraries`.
- `archive_mode` and `archive_command`.
- `ssl`, authentication, and logging settings.
- `autovacuum` parameters.
- Locale and collation settings.

Compare configuration files against the actual live values reported by the server. A setting appearing in a file does not prove the server loaded it cleanly.

Check startup warnings and settings pulled from included files. Never copy an old `postgresql.conf` verbatim to a target version without checking release notes.

## 8. What Is Collation?

A collation defines string comparison and sorting rules per locale and provider. It governs operations such as `ORDER BY`, comparisons, equality semantics in certain collations, unique indexes, and text-based expressions.

PostgreSQL supports providers such as:

- **`libc`:** relies on the operating system's locale support.
- **`ICU`:** relies on International Components for Unicode when built and supported by the server.
- **`builtin`:** built-in collations with version-specific behavior.

Collation is not merely text display formatting. If the provider changes how two strings compare or sort, existing indexes built under the old rules may no longer match current comparison rules.

For example, locales can handle these differently:

- Uppercase vs. lowercase.
- Diacritics and accents.
- Ordering of accented characters.
- Unicode normalization or equivalence.
- Language-specific sorting rules.

Never guess exact behavior from a locale name; test with real data and your actual provider.

## 9. When Does a Collation Version Mismatch Occur?

PostgreSQL records the collation provider's version when a database or collation is created or refreshed. If `libc` or `ICU` is upgraded, the actual provider version can differ from the recorded version.

PostgreSQL then emits a collation version mismatch warning. This signals that sorting or equality rules may have changed while existing indexes or dependent objects were built under the older rules.

Common causes:

- OS package update to `glibc`.
- Upgraded `ICU` package.
- New container image bundling different libraries.
- Cluster restored onto a host with a different locale provider version.
- Database migrated to a different Linux distribution.
- Collation definitions changing across environments.

A mismatch does not mean every table is corrupted. Identify which collations changed and which objects depend on them.

## 10. Checking Database Collation Versions

For the database default collation:

~~~sql
SELECT
    d.datname,
    d.datcollate,
    d.datctype,
    d.datcollversion AS recorded_version,
    pg_database_collation_actual_version(d.oid) AS actual_version
FROM pg_database AS d
WHERE d.datname = current_database();
~~~

If `recorded_version` differs from `actual_version`, the database's default collation may have changed.

Check every database impacted by maintenance, not just the currently connected one. Connect to each database or use appropriate catalog visibility to verify all of them.

### Checking Collation Objects

~~~sql
SELECT
    n.nspname AS schema_name,
    c.collname,
    c.collprovider,
    c.collisdeterministic,
    c.collversion AS recorded_version,
    pg_collation_actual_version(c.oid) AS actual_version
FROM pg_collation AS c
JOIN pg_namespace AS n
    ON n.oid = c.collnamespace
WHERE c.collversion IS DISTINCT FROM pg_collation_actual_version(c.oid)
ORDER BY n.nspname, c.collname;
~~~

Columns and provider codes vary by PostgreSQL version. Check your current server's catalog definition before automating queries.

If the actual version is `NULL`, that provider may not supply a version string under that version/build's semantics. Never treat `NULL` as proof of mismatch or health without understanding the provider.

## 11. Finding Indexes Dependent on Collations

Indexes on `text`/`varchar`/`char` or collated expressions may need rebuilding after a provider update. Indexes with key expressions like `lower(name)`, custom sort keys, or collation-specific operator classes must also be reviewed.

Start with an inventory:

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    pg_get_indexdef(i.indexrelid) AS index_definition
FROM pg_index AS i
JOIN pg_class AS idx
    ON idx.oid = i.indexrelid
JOIN pg_class AS tbl
    ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns
    ON ns.oid = tbl.relnamespace
WHERE ns.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY ns.nspname, tbl.relname, idx.relname;
~~~

Review index definitions to spot collatable keys, expressions, and predicates. Catalog dependencies help narrow the scope, though never rely on one simple query alone when indexes use expressions or collations inherited from types or operators.

### Notes on Unique Indexes

After a collation change, two text values previously treated as distinct can become equal under the new provider. When rebuilding a unique index, PostgreSQL may report duplicate keys.

This is a data and semantics issue, not merely an index bug. You must:

1. Query duplicate candidates under the new collation.
2. Determine the business rule for selecting or merging values.
3. Resolve data through approved business procedures.
4. Verify uniqueness.
5. Rebuild the index.
6. Proceed only once constraint semantics are guaranteed.

Never drop a unique constraint just to make `REINDEX` pass without an explicit plan protecting uniqueness.

## 12. Why Must You `REINDEX` After a Collation Update?

A B-tree index stores its sorted structure using the comparison semantics in effect when the index was built. When the collation provider changes, ordering or equality semantics can shift. The old index may no longer align with PostgreSQL's current comparisons.

Rebuilding the index recreates index ordering under the new provider.

Objects commonly requiring evaluation:

- B-tree indexes with text keys.
- Indexes on collated expressions.
- Unique indexes using collations.
- Indexes on columns or domains of collatable types.
- Partitioned indexes and individual partition indexes.
- Other objects with persisted collation-dependent semantics.

Do not assume every index in the cluster is affected. Scope work by database, collation, and index definition.

## 13. Safe Order: Rebuild First, Then Refresh Version

Crucial point: `REFRESH COLLATION VERSION` updates only the recorded version metadata. It does not rebuild indexes and does not repair stored key ordering.

General workflow:

1. Identify the provider/version mismatch.
2. Identify affected databases and collations.
3. Inventory dependent indexes and objects.
4. Assess duplicate key risks, locks, disk space, and runtime.
5. Rebuild affected indexes and objects.
6. Verify index validity and application behavior.
7. Run `REFRESH COLLATION VERSION` for the specific database or collation.
8. Re-check recorded vs. actual versions.
9. Save evidence and close the change.

Never refresh the version before rebuilding dependent objects; doing so silences the warning while leaving indexes ordered under old rules.

### Refreshing a Database Default Collation

After dependent objects have been rebuilt:

~~~sql
ALTER DATABASE sales REFRESH COLLATION VERSION;
~~~

Execute with proper privileges and connection rules. This updates the recorded version of the database's default collation.

### Refreshing a Named Collation

~~~sql
ALTER COLLATION public.customer_sort REFRESH VERSION;
~~~

This updates the recorded version for that specific collation object. It does not rebuild indexes depending on that collation.

If multiple databases define separate copies of the same named collation, process each database individually.

## 14. `REINDEX` by Scope

### Single Index

~~~sql
REINDEX INDEX public.orders_customer_name_idx;
~~~

Rebuilds a single index and may acquire locks affecting concurrent access.

### Single Table

~~~sql
REINDEX TABLE public.orders;
~~~

Rebuilds indexes on the table per command scope and version semantics.

### Schema or Database

~~~sql
REINDEX SCHEMA public;
~~~

~~~sql
REINDEX DATABASE sales;
~~~

Broad-scope commands consume substantial I/O, disk, and locks. Use them only when the scope genuinely requires it; never reindex an entire database just because one collation object has a mismatch.

### Concurrent Reindex

For eligible indexes, consider:

~~~sql
REINDEX INDEX CONCURRENTLY public.orders_customer_name_idx;
~~~

`CONCURRENTLY` has specific limitations, cannot run inside an ordinary transaction block, and can leave an invalid index behind if it fails. It minimizes write-blocking time at the cost of longer runtime, higher I/O, and extra disk space.

Check version documentation and plan for invalid-index recovery. Never run concurrent rebuilds in bulk without bounding concurrency.

## 15. Verifying Indexes After `REINDEX`

Check index validity:

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indrelid::regclass AS table_name,
    i.indisvalid,
    i.indisready,
    i.indislive,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_index AS i
WHERE i.indrelid = 'public.orders'::regclass
ORDER BY i.indexrelid::regclass::text;
~~~

If `REINDEX CONCURRENTLY` failed, inspect and clean up invalid indexes before retrying. Never drop an index by name alone; verify its definition, dependencies, and owner.

Run `amcheck` when suitable for the index type and operational window. Then run test queries exercising collation-sensitive predicates and sort orders.

## 16. Testing Collation Behavior with Representative Data

Before and after provider changes, test representative strings for your locale and business data:

~~~sql
SELECT
    value,
    value COLLATE "en-x-icu" AS test_value
FROM (
    VALUES
        ('a'),
        ('A'),
        ('á'),
        ('ä'),
        ('ae'),
        ('Å'),
        ('ß'),
        ('ss')
) AS samples(value)
ORDER BY test_value;
~~~

The collation name is an example; use a collation that actually exists in your database. Output depends on provider, locale, and options.

You can also test equality/ordering behavior:

~~~sql
SELECT
    'a' COLLATE "some_collation"
        = 'A' COLLATE "some_collation" AS equal_under_collation;
~~~

Never rely on a single toy string to represent an entire language's rules. Identify business-critical cases: customer names, addresses, lookup codes, sort keys, uniqueness, and case/accent sensitivity.

## 17. Collation and Database Creation

A database's default collation and ctype are fixed at database creation from the template and chosen provider/options.

Inspect:

~~~sql
SELECT
    datname,
    datlocprovider,
    datcollate,
    datctype,
    daticulocale,
    datcollversion
FROM pg_database
ORDER BY datname;
~~~

Columns like `datlocprovider` and `daticulocale` may not exist in older PostgreSQL versions. Adapt queries to your catalog version.

Changing a database's default locale is not a simple config toggle. Switching collation providers or options typically requires creating a new database and migrating data and indexes via a supported procedure.

## 18. What Version Layers Does an Extension Have?

A PostgreSQL extension typically has three layers to manage:

1. **OS package / shared library:** binary files, control files, and SQL scripts installed on the host.
2. **SQL extension version:** version recorded in `pg_extension` inside each database.
3. **Server compatibility:** the extension binary compiled for the matching PostgreSQL major version and ABI.

Updating one layer does not automatically update the others.

For example, an extension package built for PostgreSQL 17 will not work on PostgreSQL 16. Installing a new host package also does not update SQL objects inside existing databases. Conversely, `ALTER EXTENSION UPDATE` cannot conjure up a missing shared library.

## 19. Inspecting Extension Inventory

Inside each database:

~~~sql
SELECT
    e.extname,
    e.extversion AS installed_version,
    n.nspname AS extension_schema,
    pg_get_userbyid(e.extowner) AS extension_owner
FROM pg_extension AS e
JOIN pg_namespace AS n
    ON n.oid = e.extnamespace
ORDER BY e.extname;
~~~

Check extensions available on the server:

~~~sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
ORDER BY name;
~~~

Check versions provided by installed packages:

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

Inventory every relevant database. Extension SQL objects are installed per database even though shared libraries live at the server level.

## 20. Checking Extension Update Paths

PostgreSQL exposes SQL upgrade paths between extension versions:

~~~sql
SELECT *
FROM pg_extension_update_paths('postgis');
~~~

Replace `postgis` with your actual extension. The function returns source/target versions and upgrade paths supported by currently installed server packages.

If no direct path exists from the installed version to the target version, you may need to step through intermediate versions or install a package supplying missing scripts.

Never edit `pg_extension.extversion` directly. Version metadata must be updated via `ALTER EXTENSION` and official scripts.

## 21. Updating SQL Extension Versions

Example:

~~~sql
ALTER EXTENSION hstore UPDATE;
~~~

Or specify a target version:

~~~sql
ALTER EXTENSION hstore UPDATE TO '1.8';
~~~

Version numbers are illustrative. Choose targets from `pg_available_extension_versions` and real update paths.

Notes:

- `ALTER EXTENSION UPDATE` applies only within the current database.
- Run it in every database containing the extension.
- Update scripts can create or modify functions, types, operators, views, or catalog metadata.
- Dependencies on other extensions may enforce a strict update order.
- Extension-specific upgrade guides may require extra steps.
- Some extensions require a restart or background worker configuration.

`CREATE EXTENSION IF NOT EXISTS` does not upgrade an already-installed extension. It merely suppresses errors when the extension already exists.

## 22. Missing Extension Control File or SQL Script Errors

Symptoms include:

- Extension control file does not exist.
- Extension version not found.
- Update script not found.
- `CREATE EXTENSION` reports extension unavailable.
- `ALTER EXTENSION` reports no update path.

Common causes:

- The OS package was never installed.
- The package was installed only for the old PostgreSQL major version.
- The package repository lacks the target extension version.
- Control/script files sit outside the extension directory used by the server.
- Container image changed from pre-upgrade image.

Resolution:

1. Confirm PostgreSQL binary and package versions.
2. Identify the extension package matching the target major version.
3. Check package manager inventory.
4. Verify extension control and SQL files per package policy.
5. Install the right package through your change process.
6. Verify `pg_available_extensions`.
7. Check update paths.
8. Run SQL extension updates per plan.

Never manually copy stray extension files from another host into PostgreSQL's `lib`/`share` directories. Packages must match ABI, dependencies, and server version.

## 23. Shared Library Load Failures

Common errors:

- `could not access file "$libdir/extension_name"`.
- `undefined symbol`.
- `symbol lookup error`.
- `incompatible library version`.
- `cannot load library`.
- `shared object dependency not found`.

Causes:

- Shared library is not installed.
- Binary was compiled for a different PostgreSQL major version.
- Package is missing a shared library dependency.
- Library path is wrong.
- Server was not restarted after package/config update.
- Architecture or OS mismatch.

Workflow:

1. Save verbatim server logs and error output.
2. Confirm extension name and library path.
3. Check server major version.
4. Check package build version and architecture.
5. Check OS-level shared library dependencies.
6. Install a compatible package.
7. Restart if required by extension documentation.
8. Verify extension functions and loading behavior.

Never run `ALTER EXTENSION UPDATE` to fix a binary load error while the package library is still missing.

## 24. `shared_preload_libraries` and Restarts

Some extensions must be loaded at server startup via `shared_preload_libraries`—for example, `pg_stat_statements` or extensions running background workers.

Check:

~~~sql
SHOW shared_preload_libraries;
~~~

And:

~~~sql
SELECT
    name,
    setting,
    context,
    pending_restart
FROM pg_settings
WHERE name = 'shared_preload_libraries';
~~~

Adding an extension to `shared_preload_libraries` requires a server restart. Running `CREATE EXTENSION` inside a database is a separate step; SQL objects generally still need to be created after the library loads.

Never overwrite the existing preload list when adding a new extension. Keep existing libraries intact and check load order and compatibility in extension docs.

If the server fails to start after adding a library, inspect startup logs and restore the prior configuration per your change plan.

## 25. Extension Dependencies and Update Order

An extension can depend on other extensions, types/functions, or shared libraries. Updating out of order can cause update scripts to fail.

Inspect `requires` metadata:

~~~sql
SELECT
    name,
    version,
    requires
FROM pg_available_extension_versions
WHERE name IN ('extension_a', 'extension_b')
ORDER BY name, version;
~~~

Extension names above are placeholders.

Before updating:

- Inspect the extension dependency graph.
- Read release notes.
- Confirm target versions.
- Verify update paths.
- Check external objects depending on extension functions, types, or operators.
- Check transactional behavior of update scripts.
- Back up and test on a clone.

Never run `DROP EXTENSION ... CASCADE` to bypass dependency errors without knowing every dependent object that will be dropped.

## 26. Extension Update Failing Mid-Way

Many extension update scripts run inside a transaction, though never assume every extension or every step is atomic across all versions and tools.

If an update fails:

1. Save the full error output and current extension version.
2. Check transaction and session state.
3. Verify `pg_extension.extversion`.
4. Check how far functions/types/operators were modified.
5. Read the update SQL script and extension release notes.
6. Verify dependencies and package versions.
7. Assess whether retrying is safe.
8. Retry update, repair per vendor guide, or restore from backup.

Never manually alter `pg_extension` to make the version appear upgraded. If SQL objects were not properly upgraded, fake metadata hides an inconsistent catalog state.

## 27. Extensions Can Change Behavior Without Changing SQL APIs

An extension update can preserve function signatures while changing:

- Algorithms.
- Planner integration.
- Operator semantics.
- Background worker behavior.
- Storage formats or internal metadata.
- Performance profiles.
- Memory/resource usage.
- Compatibility with server versions.

Hence, merely confirming a function call succeeds is not enough. Run extension-specific regression tests and critical application queries.

For extensions providing index/data types or background workers, verify index/operator compatibility and worker health.

## 28. Extension Upgrades During a Major PostgreSQL Upgrade

Before a major upgrade:

1. Inventory every extension in every database.
2. Verify target PostgreSQL version supports all extensions.
3. Install packages and shared libraries for the target major version.
4. Check extension update paths.
5. Read extension upgrade notes.
6. Identify which extensions require preloading.
7. Test `pg_upgrade --check` or dump/restore on a clone.
8. Plan the sequence of SQL extension updates once the target cluster is up.

After the major upgrade:

- Verify extension packages are present.
- Check `pg_extension` versions.
- Run update scripts in order.
- Restart if preload or configuration changes require it.
- Run extension-specific checks.
- Test application queries and background workers.

Never assume `pg_upgrade` automatically updates all SQL extension versions or installs new shared libraries.

## 29. Incidents After OS or Container Image Upgrades

A new image can alter:

- `glibc`/`libc`.
- `ICU`.
- `OpenSSL`.
- Locale data.
- Timezone databases.
- Shared library dependencies.
- PostgreSQL/extension packages.

When running in containers, the image digest is critical evidence. Record before/after image digests, package versions, and runtime architecture.

For `libc`/`ICU`, check for collation mismatches. For `OpenSSL`/auth, check TLS handshakes, certificate chains, and authentication methods. For extension binaries, verify dynamic library dependencies.

Never hot-patch a production container image by manually installing packages outside the build pipeline. Build a reproducible image, test it, and promote it through your release process.

## 30. Post-Upgrade Application Errors

Applications may encounter:

- Undefined functions or operators.
- Type conversion errors.
- Prepared statement errors.
- ORM migration mismatches.
- Changed query plans.
- Collation-sensitive ordering differences.
- Authentication or TLS failures.
- Driver incompatibilities.
- Changed extension function behavior.

Collect:

- Application build and driver versions.
- SQLSTATE and full server error messages.
- Query ID / normalized query text.
- Database version.
- Extension versions.
- `search_path` and role.
- Prepared statement and session behavior.
- Before/after query plans if available.

Never blame the application solely because the server upgrade finished. Reproduce using the exact application role, settings, and parameter values.

## 31. Checking Collations Across Multiple Databases

Collation metadata and extension SQL objects must be checked per database.

Build a database inventory:

~~~sql
SELECT
    datname,
    datlocprovider,
    datcollate,
    datctype,
    datcollversion,
    pg_database_collation_actual_version(oid) AS actual_version
FROM pg_database
WHERE datallowconn
ORDER BY datname;
~~~

Locale provider columns depend on major version. If the query fails on an older server, adapt it to match that catalog version.

For each database:

- Identify default collation.
- List mismatched named collations.
- Inventory dependent indexes.
- Record schema/table/index owners.
- Identify applications and consumers using those collations.
- Build a per-database rebuild plan.

Never refresh database A and assume database B has been handled.

## 32. Finding Collation Dependencies in Catalogs

`pg_depend` can help identify objects depending on collations. Exploratory query example:

~~~sql
SELECT DISTINCT
    idx.oid::regclass AS index_name,
    tbl.oid::regclass AS table_name,
    coll.oid::regcollation AS collation_name
FROM pg_depend AS d
JOIN pg_class AS idx
    ON d.classid = 'pg_class'::regclass
   AND d.objid = idx.oid
JOIN pg_index AS i
    ON i.indexrelid = idx.oid
JOIN pg_class AS tbl
    ON tbl.oid = i.indrelid
JOIN pg_collation AS coll
    ON d.refclassid = 'pg_collation'::regclass
   AND d.refobjid = coll.oid
WHERE idx.relkind = 'i'
ORDER BY index_name::text, collation_name::text;
~~~

Use this as one inventory aid and verify results with `pg_get_indexdef`, expressions/predicates, and your running PostgreSQL version's catalog. Do not treat it as an exhaustive list covering every dependency form or version.

## 33. Unique Index Conflicts After a Collation Change

If `REINDEX` on a unique index fails with a duplicate key error, the new collation may treat two previously distinct strings as equal under new comparison semantics.

Examples include strings differing in case, diacritics, or locale-specific equivalence. Never assume a specific pair is always equal; behavior depends on the collation.

Recovery:

1. Preserve existing data and error output.
2. Identify the unique index and collation.
3. Reproduce the comparison under the new collation.
4. List duplicate groups using the exact index expression/key.
5. Work with the data owner to decide whether to merge, rename, or retain rows.
6. Check downstream references.
7. Remediate data under an approved change.
8. Rebuild the unique index.
9. Verify uniqueness and application behavior.

Never leave a unique index dropped long-term if applications rely on it to enforce business invariants.

## 34. Collation Warnings Are Not Fixed by Refreshing Alone

`REFRESH VERSION` updates the recorded version in the catalog. It does not scan data, rebuild indexes, or prove objects were repaired.

An incorrect workflow looks like:

1. Receive warning.
2. Run `ALTER DATABASE ... REFRESH COLLATION VERSION`.
3. Warning disappears.
4. Ignore old indexes.

The result is clean metadata hiding indexes still sorted under the old provider.

The correct workflow is identifying and rebuilding dependent objects first, verifying them, and only then refreshing metadata.

## 35. Checking Indexes After Collation Rebuilds

Beyond `pg_index` validity, verify:

- Index definitions match expectations.
- Unique constraints remain enforced.
- Partitioned indexes and child indexes are valid.
- Query plans use the expected indexes.
- `ORDER BY` and comparisons behave properly.
- Application search and sort tests pass.
- `amcheck` finds no errors on selected B-tree indexes.
- No invalid indexes remain behind.

When reindexing a partitioned table, verify both the parent index and each partition index according to your version's semantics.

## 36. Post-Upgrade: `ANALYZE` and Query Plans

Optimizer statistics may need regeneration after a major upgrade. Once the database stabilizes and within workload plans, run `ANALYZE` or scripts generated by `pg_upgrade`.

~~~sql
ANALYZE;
~~~

Or for a specific table:

~~~sql
ANALYZE public.orders;
~~~

For large databases, use `vacuumdb --all --analyze-in-stages` per version docs and appropriate resource limits.

Check critical queries:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM public.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 50;
~~~

`EXPLAIN ANALYZE` executes the statement. Use representative queries, avoid side effects, and control load.

Compare actual rows, estimated rows, buffers, sort/hash spills, execution times, and plan shapes. Never force planner knobs just to restore an old plan without understanding the underlying cause.

## 37. Post-Upgrade: Sequences and Identity Columns

With dump/restore, bulk loads, or custom migrations, sequence state may need verification. Native logical replication also does not synchronize sequence state automatically like row changes.

Locate the sequence tied to a column:

~~~sql
SELECT
    pg_get_serial_sequence('public.orders', 'order_id') AS sequence_name;
~~~

After identifying specific sequences, compare sequence state against table data and increment policies. Never run a blanket script calling `setval` across all sequences without accounting for concurrent writes, caches, cycling, and ownership.

During primary/sink cutovers, sequence synchronization is a distinct step requiring explicit verification.

## 38. Post-Upgrade: Roles, Grants, and Authentication

Verify:

- Roles and memberships.
- `LOGIN`/`NOLOGIN` and role attributes.
- Ownership of databases, schemas, and tables.
- Grants and default privileges.
- RLS policies.
- `SECURITY DEFINER` functions.
- `pg_hba.conf`.
- TLS/certificate settings.
- Password/SCRAM authentication.
- Service account credentials.

Example query checking role attributes:

~~~sql
SELECT
    rolname,
    rolsuper,
    rolinherit,
    rolcreaterole,
    rolcreatedb,
    rolcanlogin,
    rolreplication,
    rolbypassrls
FROM pg_roles
ORDER BY rolname;
~~~

Do not test connectivity solely as superuser. Run smoke tests using exact application and connector roles to catch permission regressions.

## 39. Post-Upgrade: Replication, Subscriptions, and CDC

Major upgrades or OS changes can disrupt replication topologies and connectors.

Check physical replication:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
~~~

Check logical slots:

~~~sql
SELECT
    slot_name,
    plugin,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Check logical subscriptions:

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

Columns vary by version. Check slot ownership, connector versions, schema history, publication scope, and subscriber schemas.

Never drop/recreate slots just to tidy inventory. Slots may retain WAL critical for CDC; losing a slot forces re-bootstrapping or reconciliation.

## 40. Checking Extensions and Collations on Standbys

Physical standbys receive data files and catalog changes via WAL, yet binary packages and OS libraries must be compatibly installed on every node. Upon failover, a standby needs matching extension shared libraries and configuration to continue serving the workload.

For logical subscribers, DDL and extension packages typically must be deployed separately. Ensure subscriber schemas and extensions are compatible before the publisher emits row changes tied to new schemas.

Verify failover candidates too, not just the current primary.

## 41. Post-Upgrade Monitoring

Dashboards should track:

| Group | Signals |
| --- | --- |
| Server | Startup/restart errors, uptime, crash recovery |
| Query | Error rate, p95/p99 latency, top query deltas |
| Planner | Plan changes, row estimates, buffer/temp activity |
| Storage | Disk free, WAL growth, I/O latency |
| Locks | Blocked sessions, deadlocks, lock wait durations |
| Maintenance | Autovacuum, analyze progress, dead tuples |
| Collation | Recorded/actual version mismatches |
| Extensions | Installed/available versions, worker health, library errors |
| Replication | Replay lag, inactive slots, retained WAL |
| Application | Smoke tests, connection failures, business errors |

Compare against pre-upgrade and post-upgrade baselines. Some counters reset on restarts, so capture pre-maintenance snapshots and mark reset timestamps clearly.

## 42. Post-Upgrade Release Gates

Define acceptance criteria prior to maintenance:

- Target server version is correct.
- Cluster identity is correct.
- Server starts cleanly with zero fatal extension/config errors.
- Extension packages and SQL versions are compatible.
- Collation mismatches are resolved or covered by explicit exceptions.
- Dependent indexes are rebuilt.
- Indexes and constraints are in expected states.
- `ANALYZE` completed per plan.
- Application smoke tests pass.
- Roles, grants, and authentication pass.
- Replication and CDC are healthy.
- Backup/PITR paths are verified.
- Query latency and error rates are within thresholds.
- Data reconciliation passes.

If any gate fails, keep the change open and execute a recovery path. Never mark maintenance successful solely because the server process is running.

## 43. Rollback or Forward-Fix?

After a major upgrade, rolling back is not like swapping an application binary back to an earlier version.

| Scenario | Recommended Action |
| --- | --- |
| Upgrade has not started new cluster and source is intact | Cancel per `pg_upgrade`/maintenance procedure |
| Copy-mode upgrade, new cluster has accepted no writes | Fall back to source per tested plan |
| Link-mode new cluster already started | Do not treat source directory as an independent rollback |
| Extension package missing while data state is intact | Install matching package / restore config per change |
| Extension SQL update failed | Check transaction/version/dependencies; repair or restore |
| Collation mismatch, indexes not yet rebuilt | Rebuild dependent objects then refresh metadata |
| Unique index rebuild conflict | Resolve data semantics before rebuilding |
| New cluster already accepted writes | Rollback requires reverse-sync or write reconciliation |
| Data corruption or data loss | Backup/PITR/incident recovery per RPO/RTO |

Never run old binaries against an upgraded data directory. Never route traffic back to an old cluster if it missed writes committed on the new cluster.

## 44. Backups, PITR, and Recovery Readiness

Before risky upgrades or collation/extension changes:

- Have a base backup or managed snapshot.
- Ensure contiguous, verified WAL archiving.
- Document the restore procedure clearly.
- Confirm encryption keys and credentials are accessible.
- Have a recent restore test.
- Confirm RPO/RTO targets.
- Snapshot configuration and package inventory.
- Snapshot extension versions and collation versions.
- Plan how to handle writes occurring after cutover.

A pre-upgrade backup is your baseline recovery point, yet if the upgraded target already accepted writes, rolling back to the old backup loses those writes unless a reverse-sync or replay strategy exists.

## 45. Runbook: Collation Version Mismatch

### Contain

- Halt related schema changes.
- Record affected databases and mismatched collations.
- Save warning logs and provider package versions.
- Check backups and disk capacity.

### Determine Scope

- Check database default collation versions.
- List mismatched named collations.
- Inventory dependent indexes and expressions.
- Identify unique indexes and duplicate risks.
- Identify applications and consumers relying on those indexes.

### Recover

- Choose maintenance window and concurrency limits.
- Rebuild dependent indexes.
- Resolve unique conflicts per business rules.
- Verify index validity and application sort/equality behavior.
- Only then run `REFRESH COLLATION VERSION`.
- Re-check recorded vs. actual versions.

### Close

- Save index lists and `REINDEX` logs.
- Save before/after collation versions.
- Run query and business validation tests.
- Check monitoring and replication.
- Obtain reviewer sign-off.

## 46. Runbook: Extension Incompatibility After Upgrade

### Contain

- Halt further extension updates or deployments.
- Save full errors and server startup logs.
- Identify affected databases and extensions.
- Record package, binary, and SQL versions.

### Determine Cause

- Check `pg_extension`.
- Check `pg_available_extensions`.
- Check `pg_available_extension_versions`.
- Check `pg_extension_update_paths`.
- Check `shared_preload_libraries`.
- Confirm package build targets the running PostgreSQL major version.
- Read extension release notes and dependencies.

### Recover

- Install the compatible package.
- Fix config/preload settings if needed.
- Restart per maintenance plan.
- Run `ALTER EXTENSION UPDATE` along supported paths.
- Verify functions, types, and operators.
- Run extension-specific tests.
- Check application and background worker health.

### Close

- Save package and build versions.
- Save before/after SQL extension versions.
- Confirm zero missing library or symbol errors.
- Verify replication and failover nodes.
- Obtain reviewer sign-off.

## 47. Runbook: Application Errors After a Major Upgrade

1. Confirm target database and server version.
2. Capture SQLSTATE, query ID, and full error context.
3. Identify application, driver, and ORM versions.
4. Inspect involved extension functions, types, and operators.
5. Check collation-sensitive queries.
6. Check prepared statements and connection pools.
7. Check grants, `search_path`, and RLS.
8. Check query plans and statistics.
9. Reproduce using the actual application role.
10. Remediate app, config, or schema via a forward-compatible plan.
11. Run smoke tests and canary checks.
12. Preserve evidence and monitor post-rollout.

Never run smoke tests solely as superuser, as that masks permission errors encountered by real application roles.

## 48. Evidence and Change Records

An evidence package should contain:

- Change/incident ID.
- Cluster/system identifier.
- Source and target PostgreSQL versions.
- OS/container image and package versions.
- Upgrade method and logs.
- Database and extension inventory.
- Recorded vs. actual collation versions.
- Dependent index list.
- `REINDEX`/update commands and outputs.
- Migration and extension ledger state.
- Backup, PITR, and WAL archive status.
- Application and driver versions.
- Replication and CDC state.
- Smoke test and reconciliation results.
- Recovery decision, owner, and reviewer.

Redact credentials, connection strings, PII, and raw business data. Evidence requires timestamps, timezones, and target identity for reproducibility.

## 49. Common Mistakes

1. **Checking only that the server starts**, ignoring extension, collation, and application compatibility.
2. **Opening an old data directory with a new major binary**, bypassing the upgrade procedure.
3. **Treating a link-mode source cluster as a backup after target starts**, risking data corruption.
4. **Failing to save upgrade logs and package inventory**, losing root-cause evidence.
5. **Refreshing collation versions before rebuilding indexes**, silencing warnings while indexes keep old ordering.
6. **Assuming every index in the database needs rebuilding**, skipping collation dependency scoping.
7. **Ignoring unique conflicts after collation updates**, breaking business invariants by dropping constraints carelessly.
8. **Treating `REINDEX` as a cure for all corruption**, when the fault lies in the heap or storage.
9. **Running `REINDEX DATABASE` during peak hours**, causing severe I/O and lock contention.
10. **Assuming `REINDEX CONCURRENTLY` is risk-free**, overlooking runtime, disk, and invalid-index recovery.
11. **Installing extension packages without updating SQL versions**, leaving binaries and catalogs mismatched.
12. **Running `ALTER EXTENSION UPDATE` while shared libraries are missing**, failing to resolve the OS package issue.
13. **Using extension binaries built for another major version**, causing undefined symbol/ABI failures.
14. **Using `CREATE EXTENSION IF NOT EXISTS` to upgrade**, since it does not update existing extensions.
15. **Editing `pg_extension.extversion` directly**, desynchronizing metadata from actual SQL objects.
16. **Running `DROP EXTENSION CASCADE` to clear update errors**, inadvertently dropping dependent objects.
17. **Updating `shared_preload_libraries` without restarting**, leaving libraries unloaded.
18. **Overwriting the existing preload list**, accidentally dropping extensions needed by other workloads.
19. **Updating an extension in only one database**, overlooking other databases.
20. **Skipping extension update path checks**, targeting versions lacking upgrade scripts.
21. **Forgetting packages on standby/failover nodes**, causing extension load failures post-failover.
22. **Skipping `ANALYZE` after a major upgrade**, leaving the optimizer with missing or stale stats.
23. **Skipping sequence state checks**, causing duplicate key errors on post-cutover inserts.
24. **Testing only with superuser**, missing grant or application-role permission failures.
25. **Skipping locale-specific string tests**, missing sort or equality regressions.
26. **Overlooking logical subscriber/CDC schemas**, breaking downstream apply after DDL.
27. **Rolling back to an old cluster after the target accepted writes**, losing new data.
28. **Treating existing backup files as restore readiness**, without running restore tests.
29. **Ignoring WAL/disk growth during `REINDEX` or backfills**, risking disk exhaustion.
30. **Closing an incident merely because warnings disappeared**, without validating indexes, applications, and data accuracy.

## 50. Practice Exercises with Answers

### Exercise 1. What are the three main incident categories in this lesson?

**Answer:** PostgreSQL upgrades, collation version drift, and extension incompatibility.

### Exercise 2. How does a major upgrade differ from a minor update?

**Answer:** A major upgrade changes the major version and requires data/catalog conversion; a minor update preserves the data format within the same major release.

### Exercise 3. What is `pg_upgrade --check` used for?

**Answer:** Checking upgrade prerequisites before executing the actual upgrade.

### Exercise 4. Why must an old data directory never be opened directly with a new major binary?

**Answer:** Data/catalog formats are not guaranteed compatible; `pg_upgrade` or dump/restore must be used per documentation.

### Exercise 5. How do copy mode and link mode differ?

**Answer:** Copy mode copies data files; link mode uses hard links, meaning the source is no longer a safe independent rollback copy once the target starts and writes.

### Exercise 6. What is a collation?

**Answer:** String comparison and sorting rules defined by a provider and locale.

### Exercise 7. What are common collation providers?

**Answer:** `libc` and `ICU`; some PostgreSQL versions also include a `builtin` provider.

### Exercise 8. When does a collation version mismatch occur?

**Answer:** When the recorded provider version differs from the actual provider version, typically after an OS/`libc`/`ICU` upgrade or migrating to another host.

### Exercise 9. Why can a collation mismatch affect indexes?

**Answer:** Indexes were built under old comparison/sort semantics; a newer provider may produce different ordering or equality.

### Exercise 10. What does `ALTER DATABASE REFRESH COLLATION VERSION` do?

**Answer:** It updates the recorded version of the database's default collation; it does not rebuild indexes.

### Exercise 11. When do you use `ALTER COLLATION REFRESH VERSION`?

**Answer:** After handling dependent objects of a named collation, to update that collation object's recorded version.

### Exercise 12. What is the correct order between `REINDEX` and `REFRESH COLLATION VERSION`?

**Answer:** Identify and rebuild dependent objects first, verify them, and only then refresh the recorded version.

### Exercise 13. What error can a unique index hit after a collation update?

**Answer:** Two previously distinct strings may become equal under the new collation, causing duplicate-key conflicts during rebuild.

### Exercise 14. What does `pg_extension` store?

**Answer:** Installed SQL extension versions, schemas, and owners within the current database.

### Exercise 15. What is `pg_available_extensions` used for?

**Answer:** Inspecting extension packages/control files and default/installed versions recognized by the server.

### Exercise 16. What does `pg_extension_update_paths` help with?

**Answer:** Listing available SQL upgrade paths between extension versions.

### Exercise 17. Does `CREATE EXTENSION IF NOT EXISTS` upgrade versions?

**Answer:** No. It only prevents errors if the extension already exists.

### Exercise 18. What scope does `ALTER EXTENSION UPDATE` run in?

**Answer:** The current database; every database containing the extension must be updated individually.

### Exercise 19. What does an `undefined symbol` error usually suggest?

**Answer:** A shared library/ABI or dependency mismatch with the running server or package.

### Exercise 20. What does changing `shared_preload_libraries` usually require?

**Answer:** A server restart to load the library at startup.

### Exercise 21. Why doesn't installing an OS package automatically update SQL extension versions?

**Answer:** The package delivers binaries/control/scripts; SQL objects inside each database still require `ALTER EXTENSION UPDATE`.

### Exercise 22. Why must `pg_extension.extversion` never be edited directly?

**Answer:** Catalog metadata would diverge from actual SQL objects and mask an inconsistent state.

### Exercise 23. What must be done for optimizer statistics after a major upgrade?

**Answer:** Run `ANALYZE` per plan to gather statistics for the planner.

### Exercise 24. Why must sequences be checked after dump/restore or cutover?

**Answer:** Sequence state may lag behind existing table data and trigger duplicate-key errors on subsequent inserts.

### Exercise 25. Why should smoke tests use the application role?

**Answer:** Running as superuser hides permission errors that real applications will hit.

### Exercise 26. Does native logical replication propagate DDL automatically?

**Answer:** Not by default; schema changes must be deployed separately on subscribers.

### Exercise 27. Why must extensions be checked on standbys?

**Answer:** Standbys/failover nodes need matching packages, libraries, and configs to serve workloads after promotion.

### Exercise 28. When is rolling back to a source cluster unsafe?

**Answer:** When the target has already accepted new writes or a link-mode source is no longer independent; reverse-sync/reconciliation or recovery is required.

### Exercise 29. What does backup readiness require besides backup files?

**Answer:** Contiguous WAL/PITR chains, keys, documented restore procedures, restore tests, and validated RPO/RTO.

### Exercise 30. When should an incident after collation/extension upgrades be closed?

**Answer:** When recorded/actual versions match, dependent indexes/objects are resolved, binary/SQL extension versions align, app/data/replication checks pass, and evidence/sign-off are complete.

## 51. Post-Upgrade Troubleshooting Checklist

### Containment and Inventory

- [ ] Halted rollouts and further changes.
- [ ] Confirmed cluster/database identity.
- [ ] Recorded source and target PostgreSQL versions.
- [ ] Recorded OS/container image and package versions.
- [ ] Saved upgrade, server, and application logs.
- [ ] Identified primary/standby and replication topology.
- [ ] Confirmed backup, PITR, and WAL archive readiness.
- [ ] Identified application and driver versions.

### Collation

- [ ] Checked database recorded vs. actual collation versions.
- [ ] Checked named collation recorded vs. actual versions.
- [ ] Identified `libc`/`ICU`/`builtin` providers.
- [ ] Inventoried dependent indexes and expressions.
- [ ] Assessed unique conflict risk.
- [ ] Rebuilt objects per scope.
- [ ] Verified index validity and query behavior.
- [ ] Refreshed recorded versions only afterward.
- [ ] Re-checked mismatches and preserved evidence.

### Extensions

- [ ] Inventoried `pg_extension` in every database.
- [ ] Checked `pg_available_extensions`.
- [ ] Verified extension packages for target major version.
- [ ] Checked `pg_extension_update_paths`.
- [ ] Verified shared libraries and dependencies.
- [ ] Checked `shared_preload_libraries`.
- [ ] Ran `ALTER EXTENSION UPDATE` along supported paths.
- [ ] Verified function/type/operator/worker behavior.
- [ ] Checked standby and failover node packages.

### Post-Upgrade Acceptance

- [ ] Configuration and startup logs are clean.
- [ ] `ANALYZE` completed per plan.
- [ ] Sequences and identity columns are accurate.
- [ ] Roles, grants, RLS, and authentication are valid.
- [ ] Indexes and constraints are valid.
- [ ] Application smoke tests pass.
- [ ] Query latency and error rates are within thresholds.
- [ ] Replication and CDC are healthy.
- [ ] Data reconciliation passes.
- [ ] Backup/restore readiness is verified.
- [ ] Evidence and reviewer sign-off are complete.

## 52. Official PostgreSQL Documentation

Always consult documentation for your exact running major version:

- [Upgrading a PostgreSQL Cluster](https://www.postgresql.org/docs/current/upgrading.html) — cluster upgrade methods.
- [pg_upgrade](https://www.postgresql.org/docs/current/pgupgrade.html) — major version upgrades.
- [Collation Support](https://www.postgresql.org/docs/current/collation.html) — providers, locales, and collations.
- [ALTER COLLATION](https://www.postgresql.org/docs/current/sql-altercollation.html) — refreshing collation versions.
- [ALTER DATABASE](https://www.postgresql.org/docs/current/sql-alterdatabase.html) — database properties and refreshing default collation versions.
- [REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html) — rebuilding indexes and concurrent mode.
- [CREATE EXTENSION](https://www.postgresql.org/docs/current/sql-createextension.html) — installing extensions.
- [ALTER EXTENSION](https://www.postgresql.org/docs/current/sql-alterextension.html) — updating extension versions.
- [pg_available_extensions](https://www.postgresql.org/docs/current/view-pg-available-extensions.html) — extension inventory.
- [pg_extension](https://www.postgresql.org/docs/current/catalog-pg-extension.html) — installed extension metadata.
- [Extension Building Infrastructure](https://www.postgresql.org/docs/current/extend-pgxs.html) — extension packaging/build infrastructure.
- [Runtime Configuration](https://www.postgresql.org/docs/current/runtime-config.html) — server configuration.
- [Shared Library Preloading](https://www.postgresql.org/docs/current/runtime-config-client.html) — preload settings.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — server and replication monitoring.
- [Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html) — backup and recovery.
- [pg_controldata](https://www.postgresql.org/docs/current/app-pgcontroldata.html) — cluster control metadata.
- [ANALYZE](https://www.postgresql.org/docs/current/sql-analyze.html) — collecting planner statistics.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — publisher/subscriber behavior and schema coordination.

`/current/` URLs point to current PostgreSQL documentation. Catalog columns, extension update paths, provider support, command options, and locking behavior vary across PostgreSQL major versions, operating systems, and managed providers. Always check documentation for your exact server/tool version before running commands in production.

## 53. Summary

**Post-upgrade incidents must be classified before applying fixes.** PostgreSQL binary/data upgrades, collation provider changes, and extension package/SQL updates are distinct layers even when they happen simultaneously.

1. **Verify cluster, version, and maintenance timeline.** Never infer root cause solely from error timing.
2. **Major upgrades require supported conversion procedures.** Never open an old data directory with a new major binary.
3. **Collation mismatches can invalidate old index ordering or equality.** Identify dependent objects and rebuild first.
4. **`REFRESH COLLATION VERSION` updates metadata only.** It neither repairs nor rebuilds indexes.
5. **Unique indexes can uncover duplicates under new collations.** Resolve business data conflicts before rebuilding.
6. **Extensions have separate package/binary and SQL versions.** Verify both alongside server compatibility.
7. **`ALTER EXTENSION UPDATE` requires a valid update path.** Never edit the `pg_extension` catalog directly.
8. **`shared_preload_libraries` usually requires a restart.** Preserve existing preloaded libraries.
9. **After upgrading, run `ANALYZE` and verify sequences, roles, grants, replication, and applications.**
10. **Rollbacks must account for new writes and upgrade mode.** Link mode is not an independent backup.
11. **Monitoring and acceptance gates must cover both database and application.** A running server process is not enough to close maintenance.
12. **Preserve evidence prior to remediation.** Record versions, logs, object scope, commands, and verification outcomes.

An upgrade is complete only when the database, extensions, collations, applications, and downstream consumers all reach a verifiable compatible state.
