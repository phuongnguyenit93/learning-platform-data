# Extension Compatibility During PostgreSQL Backup, Restore, and Upgrade

Extensions expand PostgreSQL with SQL objects, types, functions, operators, and sometimes native libraries running inside the backend process. Consequently, a database backup may record that an extension was installed, yet still lack the packages, shared libraries, configuration files, and extension-specific data needed to restore a fully working system.

When backing up, restoring, or upgrading, distinguish three layers:

1. **Extension package on the server:** control file, SQL installation/update scripts, shared libraries, and OS/provider-installed dependencies.
2. **Extension metadata and objects inside the database:** extension name/version, ownership, schema, and objects marked as extension members.
3. **Extension configuration/state data:** runtime data or settings stored by the extension in tables, files, external services, or catalog objects.

These layers have distinct lifecycles and backup mechanisms. `pg_dump` captures extension creation commands and certain configuration table data, yet does not bundle native libraries. Physical backups preserve cluster data files, yet do not automatically guarantee OS packages, binaries, or files outside data directories are restored.

This lesson, **“Extension Compatibility During Backup, Restore, and Upgrade”**, belonging to the **Scaling** chapter of the **Database Engine Relational PostgreSQL** module, covers inventorying, choosing backup methods, preparing extension packages on targets, restoring in proper order, upgrading extension SQL versions, using `pg_upgrade`, validating HA, and verifying post-recovery state.

> **Principle:** Backing up a database and backing up the ability to run its extensions are related yet distinct tasks. Preserve metadata, package/version inventories, configurations, extension-owned configuration data, and recovery instructions; then test restores in an isolated environment.

---

## 1. Three Layers to Protect

A system using extensions has at least three layers that must be managed:

| Layer | Examples | Where managed |
|---|---|---|
| Package/runtime | Control files, SQL scripts, shared libraries, dependencies | OS image / package manager / provider |
| Extension metadata/objects | `pg_extension`, functions, types, operators | Database catalogs |
| Extension state/configuration | Config tables, files, external state | Database or external systems |

A `pg_dump` does not reinstall packages. Copying a data directory does not necessarily carry over OS-packaged shared libraries. Installing a fresh package does not automatically restore extension configuration data.

Your recovery plan must cover all three layers.

## 2. Distinguishing PostgreSQL Versions and Extension Versions

There are multiple independent versions:

- **PostgreSQL server major version:** for example 15, 16, or 17.
- **Extension SQL version:** for example 1.4, 1.5, or 2.0.
- **Package/build version:** the package or native library build distributed by the OS/provider.

These numbers need not match. An extension may have SQL version 2.1 while its package is built separately for PostgreSQL 16 and PostgreSQL 17. Matching SQL versions do not mean a shared library can be shared across two major versions.

When checking compatibility, record the server version, extension SQL version, package version, and native library build.

## 3. How Extensions Are Stored Inside a Database

When you run:

~~~sql
CREATE EXTENSION pgcrypto;
~~~

PostgreSQL reads the control file and SQL installation script on the server, then creates the extension metadata and database objects.

Inspect extensions installed in a database:

~~~sql
SELECT
    extname,
    extversion,
    extowner::regrole AS owner,
    extnamespace::regnamespace AS schema_name
FROM pg_extension
ORDER BY extname;
~~~

Extensions are installed per database. If a cluster contains multiple databases, inventory and backup must examine each database individually.

## 4. Extension Packages Do Not Live Inside pg_extension

`pg_extension` is a catalog recording extension metadata in the database. It does not contain copies of control files, SQL scripts, or native libraries.

Files are normally installed inside PostgreSQL installation directories:

- Extension control files.
- SQL installation scripts.
- SQL update scripts.
- Shared libraries.
- Supporting files and dependencies.

Exact paths depend on OS, PostgreSQL build, packaging, and provider. Never infer paths solely from the extension name.

## 5. Control Files and Compatibility Metadata

A control file may declare:

~~~text
comment = 'Example extension'
default_version = '1.0'
module_pathname = '$libdir/example_extension'
relocatable = true
superuser = true
trusted = false
requires = 'another_extension'
~~~

These attributes tell PostgreSQL the default version, library path, schema behavior, privilege requirements, and dependencies.

A control file is not complete proof that the native library works on the target. A package may be present yet miss dependencies, target the wrong architecture, or be built for another PostgreSQL major version.

## 6. SQL Objects Owned by Extensions

Objects created by an installation script can be marked as members of the extension. PostgreSQL tracks membership via dependency catalogs.

This matters for dump/restore: `pg_dump` normally emits the extension creation statement rather than dumping each member object as an independent object.

During restore, the extension's SQL installation script recreates member objects. If the target lacks the package or version script, the restore can fail.

## 7. How pg_dump Handles Extensions

A logical dump via `pg_dump` records the extension object and the `CREATE EXTENSION` statement needed on restore.

Objects belonging to an extension are not dumped individually as standalone schema objects in the usual way, because they are recreated by the extension installation script.

Consequently, a dump retains extension metadata yet **contains neither native libraries nor full implementation code**.

When restoring to another server, prepare compatible extension packages beforehand.

## 8. Inspecting Extensions Inside an Archive Dump

For a custom-format archive:

~~~bash
pg_dump -Fc -f appdb.dump appdb
~~~

You can list archive contents:

~~~bash
pg_restore --list appdb.dump
~~~

The listing shows extension entries along with other dumped objects and data. However, it does not verify that package files or native libraries exist on the target.

Keep the archive listing as part of your evidence, while maintaining a separate package inventory.

## 9. Extension Configuration Tables

Some extensions create tables holding settings or user data that must survive dump/restore.

An extension can mark those tables using:

~~~sql
SELECT pg_extension_config_dump(
    'extension_schema.settings',
    ''
);
~~~

Inside the installation script, the extension author can call `pg_extension_config_dump()` to register a table as an extension configuration table. A filter condition can also be supplied to dump only a subset of rows.

`pg_dump` processes data for marked configuration tables according to this metadata.

## 10. Not All Extension Table Data Is Automatically Dumped

This is a critical distinction:

- Extension member objects are normally recreated from extension scripts.
- Contents of configuration tables marked via `pg_extension_config_dump()` can be included in dumps.
- Contents of other extension tables may not be dumped as ordinary application data.

If an extension stores user-defined state in a table without marking it properly, a logical backup may omit that data.

Read the extension documentation and inspect installation scripts to determine which state requires separate backup.

## 11. Configuration Data and Runtime State

Not all state resides in SQL tables.

An extension may store state in:

- SQL tables.
- Large objects.
- Files outside `PGDATA`.
- Shared memory or runtime state.
- WAL or replication metadata.
- External services.
- Object storage or remote endpoints.

Some runtime state can be regenerated after restart; other state requires dedicated backup tools. Identify exactly which mechanisms each extension relies on.

## 12. Extension Backup Inventory

A minimal inventory should record:

| Attribute | Example |
|---|---|
| Extension name | `postgis` |
| SQL version | `3.x` |
| PostgreSQL major | `16` |
| Package name/version | Distro package |
| Native library | Library name/path |
| Dependencies | GDAL, GEOS, PROJ... |
| Schema | `public` or dedicated schema |
| Owner | Deployment role |
| Configuration tables | Marked tables |
| Preload requirement | `shared_preload_libraries` if any |
| Update path | Supported version transitions |
| Provider support | Allowlist / version constraints |

This information is required to recreate the target environment and troubleshoot restore failures.

## 13. Logical Backups vs. Physical Backups

| Characteristic | Logical backup | Physical backup |
|---|---|---|
| Common tools | `pg_dump`, `pg_dumpall` | `pg_basebackup`, storage snapshots |
| Data level | SQL objects and data | Cluster data files / WAL |
| Restore | Recreates objects/data from dump | Restores data directory |
| Cross-major version | Generally more flexible, requires compatibility | Not a direct major-upgrade path |
| Extension package | Not bundled | Does not guarantee OS packages |
| Database/object selection | Flexible | Normally cluster-wide |

Both backup types serve different goals. Many systems require both logical backups and physical backups/PITR.

## 14. Logical Dumps Do Not Bundle Native Code

`pg_dump` does not bundle `.so`/`.dll` files, OS dependencies, or PostgreSQL server binaries.

If a dump contains:

~~~sql
CREATE EXTENSION example_extension;
~~~

then the target server must already have the required control file, SQL scripts, and libraries before restore runs.

If the package is missing, restore can fail reporting the extension is unavailable or the library cannot be loaded.

## 15. Physical Backups Do Not Replace Package Inventories

A physical backup captures cluster data files within the backup tool's scope. It is not an OS-wide package manager snapshot.

If extension libraries reside outside `PGDATA`, restoring the data directory to a fresh host will not recreate those libraries.

Back up and record:

- OS package list.
- PostgreSQL packages.
- Extension package versions.
- Native dependencies.
- Configuration files outside `PGDATA`.
- Certificates, service units, and environment settings.
- External files required by extensions.

## 16. Cluster-Wide Backups vs. Per-Database Backups

`pg_dump` operates on a single database. If a cluster holds multiple databases, dump each database or use `pg_dumpall` as appropriate.

Roles and tablespaces are cluster-wide objects; they can be saved with:

~~~bash
pg_dumpall --globals-only > globals.sql
~~~

Extensions are installed per database, so `globals.sql` does not replace per-database dumps.

A recovery runbook must specify which database uses which extensions and the restore sequence.

## 17. pg_dumpall and Extensions

`pg_dumpall` produces logical dumps for multiple databases and cluster globals. It includes extension creation statements inside each corresponding database dump.

However, it still does not bundle native libraries or OS dependencies.

If an extension requires superuser or a special predefined role, the restore user must hold appropriate privileges. For trusted extensions, verify `CREATE` conditions and extension behavior.

## 18. pg_dump Version

Use a `pg_dump` major version equal to or newer than the source server per PostgreSQL support rules. An older `pg_dump` cannot dump a newer major server version.

Dumps are generally designed to load into newer servers, yet compatibility still depends on SQL features and extensions.

Record:

~~~bash
pg_dump --version
psql --version
pg_restore --version
~~~

Never confuse client utility versions with server versions.

## 19. Restoring a Logical Dump in the Right Order

A typical sequence:

1. Install target PostgreSQL binaries.
2. Install extension packages for the exact target major version.
3. Prepare roles and tablespaces.
4. Create the database with matching encoding/locale.
5. Verify available extension control files and versions.
6. Restore the dump.
7. Run extension SQL updates if required.
8. Verify owners, grants, and configuration data.
9. Run `ANALYZE` and validation.

Extension packages must be present before restore if the archive executes `CREATE EXTENSION`.

## 20. Creating the Database Before Restore

Example:

~~~bash
createdb \
  --template=template0 \
  --encoding=UTF8 \
  appdb_restore
~~~

Locale, collation provider, and encoding must align with application and source requirements. Do not treat this snippet as a substitute for a real inventory.

If restoring into an existing database, consider `--clean`, dependencies, and accidental object drops. Test on staging first.

## 21. Restoring a Custom-Format Archive

Example:

~~~bash
pg_restore \
  --dbname=appdb_restore \
  --verbose \
  --exit-on-error \
  appdb.dump
~~~

`--exit-on-error` halts on failure rather than continuing past errors that leave the restored database incomplete.

`--jobs` can parallelize certain restore steps. This does not mean every extension script or object creation runs safely in parallel for every archive.

## 22. Restore and Extension Privileges

If an untrusted extension requires superuser, the restoring role must hold privileges sufficient to run `CREATE EXTENSION`.

A trusted extension can be installed by a role with `CREATE` privilege on the database if other conditions are satisfied. However, some extensions or scripts impose additional requirements.

Never fix restore failures by permanently granting superuser to application roles. Use a privileged deployment identity during restore and revoke elevated access per policy.

## 23. Extension Versions Inside Dumps

A dump may record the source-installed extension version in `CREATE EXTENSION ... VERSION ...`.

If the target package lacks that exact version, restore can fail.

Options to evaluate:

- Install a target package containing the source version.
- Restore using a vendor-supported compatible version.
- After successful restore, run an extension update path.
- Follow a custom migration procedure if no direct update path exists.

Never edit archive SQL to strip the version clause without understanding the impact on schema objects and extension state.

## 24. Checking Available Versions Before Restore

On the target server, inspect:

~~~sql
SELECT
    name,
    default_version,
    installed_version,
    comment
FROM pg_available_extensions
ORDER BY name;
~~~

Inspect available versions:

~~~sql
SELECT
    name,
    version,
    superuser,
    trusted,
    relocatable,
    schema,
    requires
FROM pg_available_extension_versions
ORDER BY name, version;
~~~

These views reflect control files visible to the server. They do not prove native dependencies load cleanly; test installation on staging.

## 25. Checking Extension Update Paths

PostgreSQL can list available update paths for an extension:

~~~sql
SELECT *
FROM pg_extension_update_paths('example_extension');
~~~

The output shows whether script paths exist for version transitions.

An update path listed in catalogs does not replace the vendor support matrix. For native extensions, confirm both SQL migrations and binary libraries are compatible together.

## 26. ALTER EXTENSION UPDATE After Restore

If restore installs the extension at the source version and the target supports an update path:

~~~sql
ALTER EXTENSION example_extension UPDATE;
~~~

Or specify a target version:

~~~sql
ALTER EXTENSION example_extension UPDATE TO '2.0';
~~~

Before running, read release notes, identify schema changes, verify backups, test on a staging restore, measure duration/locks, and verify dependent objects.

Not every extension supports direct updates from every older version.

## 27. SQL Updates vs. Native Library Updates

Both may need updating:

1. Install the new native package/library on the server.
2. Run `ALTER EXTENSION ... UPDATE` to update SQL objects.

The exact order depends on the extension vendor and release design. Some extensions require the new library to be present before the SQL update runs; others define custom pre/post-upgrade steps.

Never swap a library while the server is actively using it outside a supported deployment and restart procedure.

## 28. Extension Updates Are Not PostgreSQL Major Upgrades

These are three distinct operations:

- PostgreSQL major upgrade: transitions the server major version and catalog/data format via `pg_upgrade` or dump/restore.
- Extension SQL update: executes scripts migrating extension objects/version.
- Extension package update: replaces files and native libraries at the OS/provider layer.

A PostgreSQL major upgrade may require all three, yet they are not automatically the same step.

## 29. Physical Backups and PITR

Physical backups such as `pg_basebackup` combined with WAL archiving enable cluster-level physical recovery.

Example creating a base backup:

~~~bash
pg_basebackup \
  --host=db-primary \
  --username=replication_user \
  --pgdata=/backup/base \
  --format=plain \
  --wal-method=stream
~~~

Physical backups generally restore to the same PostgreSQL major version and a compatible environment. Never treat a base backup from an older major version as directly runnable with a newer major version's binaries.

Extension packages and native dependencies must be provisioned separately on the recovery host.

## 30. PITR and Extension State

PITR recovers a database to a point in time from a base backup and WAL.

It recovers extension catalog changes and table data as long as those changes occurred within the recovered WAL timeline.

However, PITR does not reinstall OS packages or native libraries. If an extension binary is missing or changed externally, recovery may still fail to start or load the extension.

Back up package inventories and configurations alongside physical backups.

## 31. Physical Restore and Platform Compatibility

Physical data directories have compatibility requirements around:

- PostgreSQL major version.
- Architecture and build characteristics.
- Endianness and block size requirements.
- Filesystem and tablespace paths.
- Checksums/build options where applicable.
- WAL compatibility.

Never copy a data directory across incompatible platforms assuming PostgreSQL can open it.

When moving across incompatible OSes or architectures, consider logical dump/restore or a supported migration method.

## 32. pg_upgrade and Extensions

`pg_upgrade` transitions a cluster between major versions by migrating catalogs and relation files. It does not automatically install extension packages on the new host.

Before running:

- Install extension packages compatible with the target major version.
- Install shared libraries and dependencies.
- Stage control files and SQL scripts.
- Verify preloaded extensions.
- Run `pg_upgrade --check`.
- Inspect warnings regarding extensions/modules.

If the target lacks a native library, the new server may fail to start or function calls may fail.

## 33. Old and New Extension Libraries

During an upgrade, the old cluster uses binaries/libraries for the old major version, while the new cluster requires packages built for the target major version.

Never overwrite the old library with a binary built for the new major version while the old cluster may still need to run.

Parallel package installation per major version may be required depending on OS package layout. Use package managers and vendor repositories to manage files cleanly.

## 34. pg_upgrade Does Not Upgrade Extension SQL Versions

After `pg_upgrade` finishes, extension catalogs may still record old SQL versions.

Inspect:

~~~sql
SELECT
    extname,
    extversion,
    extowner::regrole AS owner
FROM pg_extension
ORDER BY extname;
~~~

Consult target extension documentation and run `ALTER EXTENSION ... UPDATE` when needed.

Never assume a newer server major version means extensions are already at their latest SQL versions.

## 35. shared_preload_libraries and Startup Dependencies

Some extensions require declaration in:

~~~text
shared_preload_libraries = 'pg_stat_statements,example_extension'
~~~

During recovery or upgrade:

- Ensure the library exists on the target.
- Verify module names and compatibility.
- Configure target `postgresql.conf` / parameter groups.
- Restart when required by the setting.
- Inspect startup logs.
- Verify the extension is active.

A missing module listed in `shared_preload_libraries` can prevent the server from starting if configuration requires loading it.

## 36. Background Workers and Shared Memory

Extensions may register background workers or allocate shared memory at startup.

These components depend on server version, package build, and startup configuration.

After restore or upgrade:

- Check worker processes.
- Check logs.
- Verify required GUCs.
- Review memory and worker limits.
- Check extension health endpoints or catalog state.
- Verify restart behavior.

Do not conclude an extension is fully operational merely because `CREATE EXTENSION` succeeded.

## 37. Extension Config Tables After Logical Restore

If an extension registers configuration tables via `pg_extension_config_dump()`, data is dumped and restored.

After restore, verify config tables and row counts:

~~~sql
SELECT count(*)
FROM extension_schema.settings;
~~~

The table name is illustrative. Compare critical configuration values against your baseline.

If an extension does not mark tables whose data must be preserved, export/import them via vendor-supported tools or separate backups prior to migration.

## 38. Restore Dependency Order

Some extensions declare `requires` to depend on other extensions. Application SQL objects may also depend on extension types or functions.

The restore workflow must ensure:

1. Native packages/dependencies exist on the server.
2. Required extensions can be installed.
3. Database and schema prerequisites exist.
4. Extension objects are created.
5. Configuration data is restored.
6. Dependent application objects are created/restored.
7. Grants and ownership are restored.

Archive restores manage internal dependency ordering, yet external packages and OS dependencies must still be staged first.

## 39. Logical Replication and Extensions

Logical replication does not replicate extension installation metadata or DDL in general.

It replicates row changes for tables included in configured publications, but does not automatically:

- Install extensions on subscribers.
- Provision native libraries.
- Synchronize `CREATE EXTENSION`.
- Propagate all schema/DDL changes.
- Guarantee identical extension SQL versions.

Provision extension packages and objects on subscribers as part of your migration plan. If extension-owned tables contain data needing replication, verify publication/subscription support and table eligibility separately.

## 40. Cross-Major Migration via Logical Replication

Logical replication can minimize downtime across major-version upgrades, yet extension compatibility must be prepared on both source and target.

Ensure you:

- Install compatible extension packages on the target.
- Create schemas and extension objects on the subscriber.
- Verify types, operators, and functions used by schemas.
- Identify which extension tables need replication.
- Synchronize DDL separately.
- Verify sequences and non-table state.
- Monitor replication lag and cutover consistency.

Never assume logical replication replaces extension installation or configuration migration.

## 41. High Availability and Standbys

In physical streaming replication, standbys must match the primary's major version per supported topology and carry compatible binaries/extensions to run the workload after failover.

Before a major upgrade:

- Inventory extension packages across all nodes.
- Prepare target packages for primary and standbys.
- Verify `shared_preload_libraries`.
- Plan standby rebuild/reseed steps if needed.
- Update monitoring and backup agents.
- Rehearse failover post-upgrade.

A successful primary upgrade alone does not prove standbys can promote safely.

## 42. Replication Slots and Extension-Specific Replication

Some extensions provide output plugins, logical decoding, or replication helpers.

Verify:

- Is the plugin binary compatible with the target?
- Are slots preserved or must they be recreated?
- Do consumers support the target major version?
- Is WAL retention sufficient during downtime?
- Is extension state migrated?
- Can consumer offsets resume cleanly?

Never drop replication slots or reset consumer offsets just to push an upgrade through without a recovery plan.

## 43. Managed PostgreSQL Services

Managed providers maintain their own extension allowlists and package versions.

Differences across providers can include supported extensions, allowed versions, enablement workflows, restricted superuser access, shared preload configuration, maintenance/upgrade flows, and backup/PITR semantics.

Before migrating, compare the source and target provider support matrices. An extension available in upstream PostgreSQL may not exist on the target managed service.

## 44. Containers and Kubernetes

In containerized PostgreSQL, extension packages normally live in the container image while data resides on persistent volumes.

When changing images or upgrading major versions:

- The target image must contain compatible extension packages.
- Shared libraries must match architecture and server ABI.
- ConfigMaps and parameter settings must be updated.
- Persistent volumes do not carry over packages from old images.
- Init scripts must be idempotent.
- Operators must support the version transition.
- Backup/restore workflows must record image digests and package lists.

Never install packages manually into an ephemeral container and assume they survive pod rescheduling or recreation.

## 45. Collations, Types, and Indexes of Extensions

Extensions can supply custom types, operator classes, or index access methods. Upgrades may alter behavior, serialization, or semantics of those objects.

Read release notes to determine:

- Whether type representations change.
- Whether data dump/reload is required.
- Whether `REINDEX` is required.
- Whether operator class semantics change.
- Whether `ALTER EXTENSION ... UPDATE` is required before or after another step.
- Whether collation dependencies exist.

Never reindex or rewrite data blindly without checking the extension's exact requirements.

## 46. Extension Updates May Not Be Reversible

`ALTER EXTENSION ... UPDATE` runs SQL migration scripts. Not every extension supplies downgrade scripts.

Once an update modifies catalog objects or data, merely downgrading the OS package will not restore the prior state.

Before updating:

1. Back up the database.
2. Record the extension version.
3. Read update scripts and release notes.
4. Test on a clone or restored copy.
5. Measure locks and duration.
6. Define rollback via restore or forward-fix.
7. Keep compatible rollback packages available.

Never remove old packages before the rollback window closes if policy requires preserving recovery capability.

## 47. Extension Configuration and Secrets

Some extensions store credentials or endpoints in database settings, tables, or external files.

Never place secrets into unencrypted dumps or logs.

Your backup plan must identify:

- Which secrets live in the database.
- Which secrets live in configuration files.
- Which secrets live in a secret manager.
- How identities and permissions are restored.
- Post-recovery rotation requirements.
- How to verify secrets are not leaked in archives.

A database restore that succeeds yet lacks credentials or certificates can still leave an extension non-functional.

## 48. Controlled Restore Procedure

A practical workflow:

1. Identify source PostgreSQL and extension versions.
2. Read the package inventory and backup manifest.
3. Provision target PostgreSQL binaries.
4. Install target extension packages and native dependencies.
5. Configure preloads and external services.
6. Create roles, tablespaces, and databases.
7. Verify extension versions and control files.
8. Restore the logical dump or physical backup.
9. Run extension SQL updates if needed.
10. Restore/verify extension configuration state.
11. Verify owners, grants, and `search_path`.
12. Run `ANALYZE`.
13. Test extension APIs and the application.
14. Verify fresh backups and replication.

Exact ordering must follow extension vendor instructions and backup type.

## 49. Controlled Major Upgrade Procedure

With `pg_upgrade`, the workflow typically includes:

1. Inventory extensions on the old cluster.
2. Identify target-compatible packages.
3. Install old/new packages side-by-side per OS requirements.
4. Verify preload libraries and dependencies.
5. Initialize the new cluster with target `initdb`.
6. Run `pg_upgrade --check`.
7. Take backups and rehearse rollback.
8. Stop the old cluster.
9. Execute the actual `pg_upgrade`.
10. Start the new cluster.
11. Inspect extension versions and logs.
12. Run `ALTER EXTENSION ... UPDATE` where supported.
13. Run `ANALYZE` and verify objects.
14. Test the application and HA.

`pg_upgrade` does not replace package management or extension-specific migration instructions.

## 50. Post-Restore and Post-Upgrade Verification

Inventory extensions:

~~~sql
SELECT
    extname,
    extversion,
    extowner::regrole AS owner,
    extnamespace::regnamespace AS schema_name
FROM pg_extension
ORDER BY extname;
~~~

Check available packages/versions:

~~~sql
SELECT
    name,
    default_version,
    installed_version
FROM pg_available_extensions
ORDER BY name;
~~~

Check languages if extensions rely on procedural languages:

~~~sql
SELECT
    lanname,
    lanpltrusted
FROM pg_language
ORDER BY lanname;
~~~

Compare results against the pre-backup/pre-upgrade manifest.

## 51. Checking Native Libraries and Startup Logs

SQL catalogs cannot prove every shared library loads cleanly across every code path.

Check:

- PostgreSQL startup logs.
- Undefined symbol or library errors.
- Missing dependency messages.
- Background worker startup failures.
- Preload warnings or errors.
- Representative function invocations.
- Native package versions on the OS.

For modules loaded lazily on first function call, run smoke tests that actually invoke key functions.

## 52. Checking Extension Configuration State

If an extension has config tables or external state, verify:

- Tables exist.
- Required rows are present.
- Ownership and grants are accurate.
- Config values match the baseline.
- External endpoints are reachable.
- Credentials and certificates are valid.
- State can be regenerated if not backed up.

Do not compare `extversion` alone; identical extension versions can hold completely different configuration or state data.

## 53. Checking Functional Behavior

Build test cases for the extension APIs used by your application.

Example for an extension providing functions:

~~~sql
SELECT extension_schema.example_function('test-input');
~~~

For extensions providing index access methods or operator classes, inspect query plans and query outputs. For background-worker extensions, verify workers are running and logs show no errors.

Test actual functionality rather than merely checking for a row in `pg_extension`.

## 54. Taking Fresh Backups After Recovery

After a successful restore or upgrade:

- Take a new base backup matching the target major version.
- Verify WAL archiving.
- Back up the extension package inventory.
- Store extension versions and package manifests.
- Test an independent restore.
- Record configuration and secret references.
- Update the disaster recovery runbook.

Never continue relying on an old backup from the source version as the sole backup for the new system.

## 55. Common Failure Modes

### 55.1. Extension Not Available

The target lacks the control file/SQL package, or the provider does not support the extension.

### 55.2. Shared Library Not Found

The native library is not installed, the library path is wrong, or it targets the wrong PostgreSQL major version.

### 55.3. Undefined Symbol

The library was built against a different ABI or has a dependency mismatch.

### 55.4. Extension Version Unavailable

The dump requests a source version absent from the target package's installation scripts.

### 55.5. Missing Update Path

No direct SQL update script exists from the current version to the target version.

### 55.6. Empty Config Tables After Restore

The extension failed to register tables via `pg_extension_config_dump()`, or external state was backed up separately and not yet restored.

### 55.7. Preload Failure

`shared_preload_libraries` references a missing or incompatible module, causing server startup to fail.

### 55.8. Missing Extension Objects After Logical Restore

The extension script failed or archive restore errored out; check restore logs and verify objects.

### 55.9. Standby Fails to Promote

The standby lacks packages, binaries, or config, or was not rebuilt for the target major version.

### 55.10. Managed Provider Rejects CREATE EXTENSION

The extension or version is outside the provider's allowlist, or the role lacks required privileges.

## 56. Lab: Inventorying and Backing Up Extensions

In a lab database:

~~~sql
SELECT
    extname,
    extversion,
    extowner::regrole,
    extnamespace::regnamespace
FROM pg_extension
ORDER BY extname;

SELECT
    name,
    default_version,
    installed_version
FROM pg_available_extensions
ORDER BY name;
~~~

Record the server version, package versions, shared libraries, preload settings, and external dependencies.

Create a logical dump:

~~~bash
pg_dump -Fc -f appdb.dump appdb
~~~

List archive contents:

~~~bash
pg_restore --list appdb.dump
~~~

Record extension entries and identify which packages must be installed on the target.

## 57. Lab: Restoring with Packages Pre-Installed

1. Create a target lab database.
2. Install compatible extension packages.
3. Inspect `pg_available_extensions`.
4. Restore the archive using `pg_restore`.
5. Inspect `pg_extension`.
6. Check extension config tables.
7. Call representative extension functions.
8. Compare results against the source baseline.

Never use production credentials or live external services in the lab.

## 58. Lab: Extension Update Paths

Inspect versions and update paths:

~~~sql
SELECT *
FROM pg_extension_update_paths('example_extension');
~~~

If a vendor-supported update path exists:

~~~sql
ALTER EXTENSION example_extension UPDATE;
~~~

Record before/after versions, script output, locks, elapsed time, and application query behavior.

Test on a restored copy before applying to production.

## 59. Lab: pg_upgrade and Extension Packages

Across two separate PostgreSQL installations:

1. Install the source major version and matching extension package.
2. Initialize the old cluster, install the extension, and create test data.
3. Rehearse backup/restore.
4. Install the target major version and target extension package.
5. Prepare the target cluster.
6. Run `pg_upgrade --check`.
7. Rehearse the actual upgrade.
8. Start the new cluster.
9. Verify extension versions, native libraries, and preload behavior.
10. Run extension updates as needed.
11. Verify functions, configuration tables, and application behavior.

Never overwrite the old-version package while the old cluster may still be needed for rollback.

## 60. Practice Exercises

### Exercise 1 — Three Extension Layers

Name the three layers that must be backed up.

**Hint:** package/runtime, database metadata/objects, and configuration/state data.

### Exercise 2 — pg_dump

Does `pg_dump` bundle native shared libraries?

**Hint:** no.

### Exercise 3 — CREATE EXTENSION

Which files does restore rely on when creating an extension?

**Hint:** control files and SQL installation scripts on the target server.

### Exercise 4 — Extension Membership

Why does `pg_dump` not dump every member object individually as a standalone object?

**Hint:** the installation script recreates member objects.

### Exercise 5 — Configuration Tables

Which function registers extension configuration tables?

**Hint:** `pg_extension_config_dump`.

### Exercise 6 — Extension State

Is all extension table data automatically dumped?

**Hint:** no; inspect config table declarations and extension behavior.

### Exercise 7 — Physical Backups

Does a physical backup automatically install OS packages?

**Hint:** no.

### Exercise 8 — Cluster Globals

Which command is commonly used to dump roles and tablespaces?

**Hint:** `pg_dumpall --globals-only`.

### Exercise 9 — Per-Database Extensions

Does an extension installed in one database automatically appear in other databases?

**Hint:** no.

### Exercise 10 — pg_dump Version

Can a `pg_dump` older than the source server major version dump a newer server?

**Hint:** unsupported.

### Exercise 11 — Restore Order

Why must packages be installed before `pg_restore`?

**Hint:** `CREATE EXTENSION` requires control files and scripts.

### Exercise 12 — Extension Version

Why can a dump requesting a source version fail on the target?

**Hint:** the target lacks the installation script for that version.

### Exercise 13 — Update Paths

Which function lists extension update paths?

**Hint:** `pg_extension_update_paths`.

### Exercise 14 — ALTER EXTENSION

Which command executes an extension's SQL migration?

**Hint:** `ALTER EXTENSION ... UPDATE`.

### Exercise 15 — Native ABI

Why must native extensions be built for the exact major version?

**Hint:** server ABI/APIs can change.

### Exercise 16 — pg_upgrade

Does `pg_upgrade` install extension packages automatically?

**Hint:** no.

### Exercise 17 — Extension SQL Version

After `pg_upgrade`, is an extension's SQL version automatically the latest?

**Hint:** not necessarily; inspect `extversion` and update paths.

### Exercise 18 — Preload

Why must `shared_preload_libraries` be verified after an upgrade?

**Hint:** missing or mismatched modules can cause startup failures.

### Exercise 19 — PITR

Does PITR restore OS shared libraries?

**Hint:** no.

### Exercise 20 — Logical Replication

Does logical replication automatically replicate `CREATE EXTENSION`?

**Hint:** no.

### Exercise 21 — Extension Config State

How do you check whether a config table is handled by `pg_dump`?

**Hint:** check the extension installation script and `pg_extension_config_dump` declarations.

### Exercise 22 — Standbys

Why do standbys need extension packages?

**Hint:** when promoted or running extension-dependent workloads, matching native files and config are required.

### Exercise 23 — Managed Services

Why check the extension allowlist?

**Hint:** providers may restrict packages, versions, and privileges.

### Exercise 24 — Containers

Why must extension packages be baked into the target image?

**Hint:** data volumes do not supply binaries or control files.

### Exercise 25 — Extension Rollback

Can `ALTER EXTENSION ... UPDATE` always downgrade?

**Hint:** no; many extensions do not ship downgrade scripts.

### Exercise 26 — Backup Manifest

List the critical fields in an extension inventory.

**Hint:** name, SQL version, server major, package, library, dependencies, config tables, preload.

### Exercise 27 — Restore Validation

Why is checking `pg_extension` alone insufficient?

**Hint:** native libraries, background workers, config state, and functional behavior must also be tested.

### Exercise 28 — Package Provenance

Why pin and record package versions?

**Hint:** to reproduce the exact runtime and verify binary provenance.

### Exercise 29 — External State

What else must be backed up for an extension calling an external service?

**Hint:** endpoints, credentials, certificates, service state, and recovery instructions.

### Exercise 30 — New Backups

What backup should be created after a major upgrade?

**Hint:** a base backup/WAL strategy matching the target major version alongside package/config inventories.

### Exercise 31 — Update Order

Why read vendor instructions before replacing a library and running `ALTER EXTENSION`?

**Hint:** some extensions require a specific sequence or restart.

### Exercise 32 — Config Data

Why might a config table pass a filter condition to `pg_extension_config_dump`?

**Hint:** to dump only rows that must be preserved while omitting default or regenerable rows.

### Exercise 33 — Restore Permissions

Why can restoring an untrusted extension require superuser?

**Hint:** the control file may require privileged installation.

### Exercise 34 — Collations/Indexes

When an extension modifies an operator class, what must be checked?

**Hint:** index validity/semantics and vendor `REINDEX` requirements.

### Exercise 35 — Replication Plugins

What must be checked for an extension providing a logical decoding plugin?

**Hint:** target binary, slot compatibility, consumers, and offsets.

### Exercise 36 — Physical Version

Can a physical backup from an older major version start directly on a newer major version server?

**Hint:** no; `pg_upgrade` or an appropriate migration is required.

### Exercise 37 — Archive Inspection

Which command lists contents of a custom-format dump?

**Hint:** `pg_restore --list`.

### Exercise 38 — Startup Errors

What happens if `shared_preload_libraries` references a missing file?

**Hint:** server startup failure or module load error.

### Exercise 39 — Recovery Testing

What must an extension recovery rehearsal prove?

**Hint:** packages, metadata, config state, functions, permissions, and external dependencies all work together.

### Exercise 40 — Backup Strategy

Why combine database backups with package/config inventories?

**Hint:** database data alone cannot recreate the extension runtime environment.

## 61. Frequently Asked Questions

### Does pg_dump back up extensions?

It saves extension metadata, extension creation statements, and configuration table data registered by the extension. It does not bundle native libraries or OS dependencies.

### Why does restore fail saying an extension is not available?

The target lacks the control file/SQL scripts or the provider does not support the extension. Install the package for the exact PostgreSQL major version and retry.

### Does pg_dump save every extension function individually?

Member objects are normally recreated by the extension installation script rather than dumped individually like ordinary application objects.

### How are extension config tables backed up?

Extension authors can mark them using `pg_extension_config_dump`. Inspect the script and verify data after restore.

### Do physical backups contain extension binaries?

Normally no. They protect cluster data files; native libraries and packages must be managed separately.

### Does pg_upgrade automatically update extension versions?

Never assume it does. Check `extversion` post-upgrade and run `ALTER EXTENSION ... UPDATE` along a vendor-supported path when needed.

### Can a dump from PostgreSQL 16 be restored into 17?

Usually yes for logical dumps with compatible SQL, provided compatible extension packages/versions exist on the target. Rehearse before production.

### Can a PostgreSQL 16 physical backup be restored directly into PostgreSQL 17?

Not as a direct startup. Physical backups are tied to the source major version; use `pg_upgrade` or logical migration to change major versions.

### Do identical extension versions mean identical native binaries?

No. The same SQL version can have distinct package builds per PostgreSQL major version and architecture.

### Does logical replication transfer extensions?

Not automatically. Provision extension packages and objects separately; replicate table data if needed and supported.

### Should ALTER EXTENSION UPDATE run immediately after restore?

Only after verifying packages, update paths, dependencies, backups, and vendor instructions. Test on staging first.

### How do I know if an extension needs shared_preload_libraries?

Read the extension documentation and package configuration. Inspect current settings and startup logs.

### What if an extension uses external files?

Back up those files, permissions, paths, certificates, and secrets through a dedicated process. Database dumps are not guaranteed to include them.

### Can old packages be removed after an upgrade?

Only after the old cluster is no longer needed, the rollback window has closed, and target extensions are verified. Follow package manager and deployment policies.

### When is extension recovery complete?

When packages/libraries load cleanly, metadata/versions match, config state is complete, permissions are valid, and extension APIs/workers pass application tests.

## 62. Summary

Key queries and commands:

~~~sql
-- Extensions installed in the current database.
SELECT
    extname,
    extversion,
    extowner::regrole AS owner,
    extnamespace::regnamespace AS schema_name
FROM pg_extension
ORDER BY extname;

-- Extension packages/versions visible to the server.
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
    superuser,
    trusted,
    relocatable,
    schema,
    requires
FROM pg_available_extension_versions
ORDER BY name, version;

-- Extension update paths.
SELECT *
FROM pg_extension_update_paths('example_extension');

-- After verifying a vendor-supported path:
ALTER EXTENSION example_extension UPDATE;
~~~

~~~bash
# Take a logical backup for one database.
pg_dump -Fc -f appdb.dump appdb

# Inspect archive contents.
pg_restore --list appdb.dump

# Restore into a database prepared with packages and roles.
pg_restore \
  --dbname=appdb_restore \
  --verbose \
  --exit-on-error \
  appdb.dump

# Back up cluster globals.
pg_dumpall --globals-only > globals.sql

# Physical base backup; package inventory must still be backed up separately.
pg_basebackup \
  --host=db-primary \
  --username=replication_user \
  --pgdata=/backup/base \
  --format=plain \
  --wal-method=stream
~~~

Key principles to remember:

1. Extension packages, database metadata/objects, and extension state are three separate layers.
2. `pg_dump` records extension metadata and creation commands; it does not bundle native libraries.
3. Member objects are recreated from extension installation scripts.
4. Extension configuration tables are dumped according to declarations like `pg_extension_config_dump()`.
5. Not all table data created by an extension is automatically backed up.
6. `pg_dumpall --globals-only` saves roles/tablespaces, whereas extensions are installed per database.
7. Physical backups preserve cluster files yet do not install OS packages or external dependencies.
8. PITR recovers database/WAL state, not missing native libraries.
9. Use a `pg_dump` version compatible with the source server.
10. Install target extension packages prior to logical restore.
11. Dumps may request the source extension SQL version; verify available versions.
12. `pg_extension_update_paths()` reveals SQL update paths.
13. `ALTER EXTENSION ... UPDATE` and package updates are two separate actions.
14. `pg_upgrade` neither installs packages nor guarantees extensions are at their latest SQL versions.
15. Native libraries must be built for the exact PostgreSQL major version and architecture.
16. Verify `shared_preload_libraries`, background workers, and startup logs.
17. Logical replication does not synchronize extension installation or DDL automatically.
18. HA nodes require matching packages/configs and rebuild/rejoin procedures.
19. Managed providers maintain specific extension allowlists.
20. Target container images must include compatible packages.
21. Extension updates may not be downgradable.
22. Back up secrets, external files, and service state through dedicated procedures.
23. Post-restore, verify metadata, configuration data, permissions, and functional behavior.
24. Take fresh backups for the target major version after recovery or upgrade.

Compatibility diagram:

~~~text
                 Extension inventory
                         |
             +-----------+-----------+
             |           |           |
             v           v           v
          Packages    DB metadata   State/config
          and libs    and objects   and external data
             |           |           |
             v           v           v
       Target OS/PG   pg_dump or   Config-table dump,
       version build  physical     files/secrets/service
             |        restore      backup
             |           |           |
             +-----------+-----------+
                         |
                         v
              Restore / pg_upgrade
                         |
                         v
             Extension SQL update path
                         |
                         v
           Startup, preload and dependencies
                         |
                         v
             Functional validation
                         |
                         v
             New backup + DR rehearsal
~~~

**Conclusion:** Extension compatibility during backup, restore, and upgrade requires preparing package/runtime, database metadata, and extension state together. Logical dumps recreate extension objects via installation scripts yet depend on compatible packages on the target; physical backups/PITR preserve database files yet never replace OS package inventories; `pg_upgrade` migrates clusters yet does not automatically install or update every extension. Document exact versions, dependencies, configuration tables, preload requirements, and recovery steps, then rehearse restores and upgrades to prove extensions work in the target environment.
