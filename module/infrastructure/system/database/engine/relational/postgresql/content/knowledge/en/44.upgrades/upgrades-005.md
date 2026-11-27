# Upgrading with pg_upgrade and Choosing a Data Transfer Mode

`pg_upgrade` is the PostgreSQL utility used to upgrade a database cluster between **major versions** without traditionally dumping and restoring all data. The tool checks compatibility, prepares the new cluster, transfers relation files, and updates system catalogs so the new cluster can run with the target version's PostgreSQL binaries.

A key decision when running `pg_upgrade` is choosing how to transfer relation data files:

- **Copy:** copies data files to the new cluster; the old cluster remains intact.
- **Link:** creates hard links between old and new files; fast and consumes minimal extra space, but the old cluster is no longer safe to use once the new cluster is started.
- **Clone:** uses filesystem copy-on-write/reflink if supported; creates fast, space-efficient logical copies while keeping the old cluster independent.
- **Copy-file-range:** on supported versions and operating systems, uses a kernel-level copy mechanism to speed up copying while still producing independent files.

The lesson **“Upgrading with pg_upgrade and Choosing a Data Transfer Mode”**, part of the **Upgrades** chapter of the **Database Engine Relational PostgreSQL** module, explains how to choose a transfer method, prepare old/new clusters, run pre-checks, execute the upgrade, handle extensions/configuration, validate data, and plan rollback.

> **Decision rule:** if retaining the ability to fall back to the old cluster is a priority, use copy or clone. Choose link only when you accept that after starting the new cluster, the old cluster can no longer serve as an independent rollback target. Regardless of the mode chosen, you must have backups and verified restore tests before upgrading production.

---

## 1. Major Upgrades vs. Minor Upgrades

PostgreSQL distinguishes between a major version and a minor release.

- **Major upgrade:** moving between major versions, such as PostgreSQL 15 to 16 or 16 to 17. Major upgrades can change system catalogs and internal data formats.
- **Minor upgrade:** moving between minor releases within the same major version, such as 16.2 to 16.4. Typically, you only replace binaries/packages following the appropriate procedure; `pg_upgrade` is not required.

`pg_upgrade` is intended for major-version upgrades. Do not treat it as a required step for routine security/bug-fix updates within the same major version.

## 2. What Problem Does pg_upgrade Solve?

A traditional upgrade workflow looks like:

1. Export data from the old cluster using `pg_dump`/`pg_dumpall`.
2. Initialize a new cluster.
3. Restore schemas, roles, and data.
4. Rebuild indexes and necessary objects.
5. Test the application and switch endpoints.

The dump/restore approach is flexible and useful when changing encoding, data architecture, or filtering/transforming data, but it can take a long time for large databases.

`pg_upgrade` leverages binary compatibility of relation files to migrate a cluster faster. It updates the system catalogs required for the new major version and avoids exporting and importing every row.

It is not an arbitrary schema or data-model conversion tool. If an application requires schema redesign, encoding/collation changes, or complex data transformations, dump/restore or a separate migration may be necessary.

## 3. Old Cluster and New Cluster

`pg_upgrade` operates across two separate data directories:

~~~text
Old PostgreSQL cluster
  old binaries
  old data directory
        |
        | pg_upgrade
        v
New PostgreSQL cluster
  new binaries
  new data directory
~~~

Typically required:

- Binaries for the old version.
- Binaries for the new version.
- Data directory of the old cluster.
- Newly initialized data directory for the new cluster.
- An appropriate operating-system user to run the process.
- Access permissions to tablespaces, sockets, and related directories.

Do not run both clusters against the same data directory. Do not start the new cluster before the upgrade process finishes.

## 4. pg_upgrade Is Not a Logical Migration

`pg_upgrade` moves an existing cluster to a new major version by processing catalogs and relation files according to compatibility rules.

It does not automatically:

- Redesign schemas.
- Change data types per application requirements.
- Migrate business logic.
- Recreate all configuration files as a full migration.
- Install binaries for external extensions.
- Verify every application query.
- Create an independent backup in place of a backup strategy.
- Replace an HA/failover plan.

After the upgrade, you still need to review configuration, update extensions, analyze statistics, test, and cut over applications.

## 5. Compatibility Requirements

Before starting, review the `pg_upgrade` documentation for the exact target major version. Specific requirements change from release to release.

Typical key conditions include:

- The old version is a source version supported by the target version.
- The new cluster is initialized with the target version's `initdb`.
- Both clusters use compatible architectures, including required word size and endianness.
- Locale, encoding, and key `initdb` settings are compatible.
- Data checksums and cluster attributes meet upgrade requirements.
- Required extensions have binaries/control files for both versions.
- Tablespaces and symbolic links are accessible.
- Sufficient disk space is available for the chosen mode.
- No remaining transactions or processes prevent a clean cluster shutdown.

Do not assume every source version can upgrade directly to the target. If the target does not support a direct upgrade from the source, upgrade through an intermediate major version along a documented supported path.

## 6. Checking Versions and Binaries

Verify binary versions:

~~~bash
/path/to/old/bin/postgres --version
/path/to/new/bin/postgres --version
/path/to/new/bin/pg_upgrade --version
~~~

Use `pg_upgrade` from the target version. You must specify the binary directories so the tool knows the executables for both old and new clusters.

You can check help output:

~~~bash
/path/to/new/bin/pg_upgrade --help
~~~

Options such as `--clone` or `--copy-file-range` are usable only if the current binary supports them. Do not copy command lines from another major version without reviewing help and documentation.

## 7. Inspecting the Current Cluster

On the old cluster, record:

- PostgreSQL version.
- Data directory.
- Port and socket directory.
- Database list.
- Tablespaces.
- Extensions.
- Roles and memberships.
- Replication slots/subscriptions if present.
- Configuration overrides.
- SSL certificates and key permissions.
- Backup/WAL archive status.
- Scheduled jobs and external integrations.

SQL examples:

~~~sql
SELECT version();

SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS database_size
FROM pg_database
ORDER BY pg_database_size(datname) DESC;

SELECT
    spcname,
    pg_tablespace_location(oid) AS location
FROM pg_tablespace;
~~~

This serves as your inventory for planning and post-upgrade verification.

## 8. Backing Up Before the Upgrade

Before a production major upgrade, you need a restorable backup.

A typical plan includes:

- Full base backup.
- Continuous, verified WAL archiving.
- Backups of configuration, certificates, and secrets per policy.
- Backup/record of extension packages and versions.
- Consistent storage snapshots if supported by infrastructure and consistency procedures.
- Restore test in an isolated environment.

A backup is only useful if you can restore it and start a cluster from it. Check checksums, WAL continuity, and recovery duration.

Never treat the old data directory as your sole backup, especially when using `--link`.

## 9. Planning the Maintenance Window

`pg_upgrade` generally requires stopping application writes and related PostgreSQL services to execute the upgrade step.

Maintenance duration depends on:

- Total size of relation files.
- Copy/link/clone transfer mode.
- Number of databases and objects.
- Number of parallel jobs.
- Number of extensions and checks.
- Post-upgrade `ANALYZE` duration.
- Validation and smoke test duration.
- Storage and network speed if tablespaces reside on separate volumes.

Run a rehearsal on a production-like clone to measure timing. Never estimate the maintenance window solely from `pg_upgrade` execution time while ignoring analyze, validation, and application cutover.

## 10. Relation File Transfer Modes

`pg_upgrade` offers several options depending on version:

| Mode | Mechanism | Speed/Space | Old Cluster After New Starts |
|---|---|---|---|
| Copy | Independent file copy | Consumes extra space, throughput-bound | Original copy preserved |
| Link | Hard link to same inode | Very fast, minimal extra blocks | No longer safe to run |
| Clone | Reflink/copy-on-write | Often fast, saves initial blocks | Remains independent |
| Copy-file-range | Kernel-assisted file copy | Can be faster than standard copy | Remains independent |

Support depends on the PostgreSQL version, OS, and filesystem. Confirm available options with `pg_upgrade --help` on the target binaries.

## 11. Copy Mode

Copy is the standard method and is typically the default if no other mode is specified.

In copy mode:

1. `pg_upgrade` prepares relation files for the new cluster.
2. Data is copied to new files.
3. The old cluster retains its original files.
4. The new cluster has an independent copy of the files.

Advantages:

- The old cluster retains the original data.
- Easy to keep a frozen fallback for comparison or rollback before the new cluster accepts writes.
- Does not require filesystem support for hard links or reflinks.
- No shared inodes between the two clusters.

Disadvantages:

- Requires enough space for both old and new data to coexist.
- Duration depends on data volume to copy and storage throughput.
- Large copies can generate heavy I/O and lengthen the maintenance window.

Copy is the most straightforward choice when safety and fallback capability are top priorities.

## 12. Link Mode

`--link` instructs `pg_upgrade` to use hard links for eligible files instead of copying file contents.

Example:

~~~bash
pg_upgrade \
  -b /usr/lib/postgresql/16/bin \
  -B /usr/lib/postgresql/17/bin \
  -d /var/lib/postgresql/16/main \
  -D /var/lib/postgresql/17/main \
  --link
~~~

A hard link is another filename pointing to the same inode. The old and new paths do not represent two independent copies of data.

Advantages:

- Very fast on large clusters.
- Avoids copying all relation data.
- Minimal initial storage overhead.

Disadvantages and risks:

- Old and new data files share inodes.
- Both data directories must reside on a filesystem that permits hard links between them; typically this means the same filesystem.
- Once the new cluster starts and writes data, shared files are modified.
- The old cluster cannot be started as an independent rollback target after the new cluster has run.

**Do not use link mode if you need to keep the old cluster runnable after the new cluster begins accepting writes.**

## 13. Rollback Boundary in Link Mode

Distinguish two points in time:

1. `pg_upgrade` has finished, but the new cluster has not yet been started.
2. The new cluster has been started and begun operating.

With link mode, before starting the new cluster, it may still be possible to discard the new cluster and revert to the old cluster following the version/tool's recovery procedure. However, once the new cluster begins writing to hard-linked files, the old cluster is no longer an independent dataset.

Therefore, do not assume link mode provides ordinary fallback rollback. You must have independent backups and clearly define the point of no return beforehand.

## 14. Clone Mode

`--clone` uses filesystem copy-on-write (reflink) if supported by the filesystem.

Example:

~~~bash
pg_upgrade \
  -b /usr/lib/postgresql/16/bin \
  -B /usr/lib/postgresql/17/bin \
  -d /var/lib/postgresql/16/main \
  -D /var/lib/postgresql/17/main \
  --clone
~~~

With reflink, the filesystem creates a new logical file copy that initially shares physical extents. When either side writes, the filesystem allocates copy-on-write blocks for modified ranges.

Advantages:

- Faster than a full copy in many scenarios.
- Does not share inodes like hard links.
- The old cluster can remain intact in terms of data.
- Initial disk usage can be low, growing only as blocks diverge.

Disadvantages:

- Requires filesystem and storage stack support for reflink/copy-on-write cloning.
- Not all mounts, volumes, network filesystems, or storage drivers support it.
- Space usage can grow significantly once both clusters modify many blocks.
- You must test actual filesystem behavior, not just filesystem type in theory.

Clone is an attractive option when you want near-link speed while keeping the two clusters independent.

## 15. Copy-File-Range Mode

Some versions of `pg_upgrade` support `--copy-file-range` to use a kernel syscall/mechanism to copy file ranges.

Example:

~~~bash
pg_upgrade \
  -b /usr/lib/postgresql/16/bin \
  -B /usr/lib/postgresql/17/bin \
  -d /var/lib/postgresql/16/main \
  -D /var/lib/postgresql/17/main \
  --copy-file-range
~~~

This mechanism requires appropriate kernel and filesystem support. It still produces independent file copies, unlike hard-link sharing.

Actual benefit depends on the kernel, filesystem, storage backend, and file sizes. If the option is unsupported by the binary or the filesystem does not meet requirements, the upgrade can fail. Do not assume an automatic fallback to copy mode.

## 16. Choosing a Mode by Priority

| Scenario | Typically Appropriate Choice |
|---|---|
| Prioritize rollback and have ample disk | Copy |
| Need fast upgrade, accept losing old cluster after new starts | Link |
| Filesystem supports reflink and want independent old cluster | Clone |
| Want independent copy with kernel-assisted transfer | Copy-file-range if supported |
| Unsure what the filesystem supports | Copy |

Do not pick a mode on speed alone. Weigh backups, rollback requirements, filesystem capabilities, free space, and recovery objectives.

## 17. Estimating Disk Space

Before upgrading, estimate:

- Total relation data files.
- Index files.
- TOAST relations.
- Tablespaces.
- WAL required for old and new clusters.
- Temporary files and logs.
- Backup/snapshot overhead.
- Growth once the new cluster is active.

Copy mode generally requires space for both datasets. Link mode saves initial blocks but carries rollback constraints. Clone mode shares extents copy-on-write and grows as blocks diverge. Copy-file-range creates independent files and therefore still requires space for the new copy.

To check database sizes:

~~~sql
SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database
ORDER BY pg_database_size(datname) DESC;
~~~

Database size excludes operational factors such as WAL archives, logs, external tablespaces, and backup retention. Check filesystems separately.

## 18. Tablespaces

Tablespaces can place relation files across different filesystems or volumes.

Before upgrading:

- Document every tablespace and its location.
- Verify old/new OS accounts have access permissions.
- Ensure volumes have enough free space.
- Verify link mode can create hard links on every involved location.
- Check reflink support if using clone.
- Never move or delete tablespace directories during the upgrade.

Filesystem capabilities may differ between the data directory and tablespace mounts. Check every location, not just the filesystem hosting PGDATA.

## 19. Preparing the New Cluster with initdb

Initialize the new data directory using the target version's `initdb`.

Illustrative example:

~~~bash
/usr/lib/postgresql/17/bin/initdb \
  -D /var/lib/postgresql/17/main \
  --encoding=UTF8 \
  --locale=en_US.UTF-8
~~~

Key `initdb` parameters must be compatible with the old cluster as required by the target version:

- Encoding.
- Locale/collation provider and locale settings.
- Data checksums.
- WAL segment size where compatibility is required.
- Block size and other build-time characteristics.
- Authentication bootstrap and matching superuser.

Do not apply the example locale above verbatim to every environment. Read the values from the old cluster and consult the target version's documentation.

## 20. Do Not Blindly Copy postgresql.conf

The old cluster's configuration files do not automatically make a good configuration for the new cluster.

After the upgrade, review:

- `postgresql.conf`.
- `pg_hba.conf`.
- `pg_ident.conf`.
- `postgresql.auto.conf`.
- SSL certificates/keys.
- `shared_preload_libraries`.
- Extension-specific settings.
- Replication settings.
- Archive/restore commands.
- Logging settings.
- Memory/cost parameters.
- Deprecated/removed parameters.

Some settings may have been renamed, removed, or changed semantics. Use startup logs and `pg_settings` to verify the new configuration.

## 21. Extensions Must Have Target-Version Binaries

An extension typically includes:

- SQL scripts.
- Control file.
- Shared library / native binary.
- Version-specific dependencies.

Before running `pg_upgrade`, install extension versions compatible with the target PostgreSQL version. If a library or control file is missing, checks/upgrades may fail or the extension may fail to load at startup.

Inventory extensions:

~~~sql
SELECT
    e.extname,
    e.extversion,
    n.nspname AS schema_name
FROM pg_extension AS e
JOIN pg_namespace AS n
  ON n.oid = e.extnamespace
ORDER BY e.extname;
~~~

After the upgrade, inspect extension update paths and run `ALTER EXTENSION ... UPDATE` when needed and supported by the versions.

## 22. Checking Extension Update Paths

On the new cluster, after installing the matching extension packages, check available versions via the catalog:

~~~sql
SELECT
    name,
    default_version,
    installed_version
FROM pg_available_extensions
ORDER BY name;
~~~

For each extension, verify target version compatibility. Do not assume that a successful `pg_upgrade` means extension SQL objects have automatically been upgraded to the newest version.

## 23. Pre-Checking with --check

Run `pg_upgrade --check` before the maintenance window to uncover incompatibilities.

~~~bash
/usr/lib/postgresql/17/bin/pg_upgrade \
  -b /usr/lib/postgresql/16/bin \
  -B /usr/lib/postgresql/17/bin \
  -d /var/lib/postgresql/16/main \
  -D /var/lib/postgresql/17/main \
  --check
~~~

`--check` performs upgrade readiness checks without completing data migration. Some checks may briefly start internal temporary server instances.

Re-run `--check` after resolving blockers and right before the actual upgrade. Read the full output/logs instead of checking only the exit code.

## 24. Common Blockers

- Old version unsupported by the target.
- Extension missing library or update path.
- Remaining prepared transactions.
- Logical replication objects/slots with version-specific conditions.
- Invalid indexes or catalog inconsistencies.
- Inaccessible tablespace paths.
- Locale/collation mismatch.
- User-defined data types or objects requiring handling.
- Insufficient free disk space.
- Cluster unable to shut down cleanly.

`pg_upgrade` may report version-specific conditions. Resolve them according to the message and corresponding documentation; never ignore warnings.

## 25. Prepared Transactions

Prepared transactions can exist when using two-phase commit.

Check:

~~~sql
SELECT *
FROM pg_prepared_xacts;
~~~

Before upgrading, resolve prepared transactions according to business decisions: `COMMIT PREPARED` or `ROLLBACK PREPARED` as appropriate.

Do not blindly roll back all prepared transactions just to make `pg_upgrade` proceed; coordinate with the transaction coordinator and application.

## 26. Large Objects and Database Objects

Build an inventory of objects to verify:

- Databases and schemas.
- Tables, indexes, and constraints.
- Sequences.
- Large objects.
- Roles, memberships, and grants.
- Tablespaces.
- Extensions.
- Foreign data wrappers/servers.
- Publications/subscriptions and replication slots.
- Event triggers and procedural languages.
- Collations and operator classes.

`pg_upgrade` handles many database objects during a cluster upgrade, but certain external dependencies and extension-specific behaviors require separate preparation. Read the release notes for every major version spanned.

## 27. Stopping Workloads Before the Actual Upgrade

Before executing:

1. Stop application writes.
2. Stop background workers/jobs that may connect.
3. Disable schedulers or ETL jobs.
4. Confirm no client writes remain.
5. Shut down the old PostgreSQL cluster cleanly.
6. Ensure the new cluster has not been started as a service.
7. Verify data directories and tablespaces are correct.

Do not allow connection managers to automatically reconnect to the old cluster while the upgrade is in progress.

## 28. Stopping PostgreSQL

How you stop the server depends on your installation method.

Example using `pg_ctl`:

~~~bash
/usr/lib/postgresql/16/bin/pg_ctl \
  -D /var/lib/postgresql/16/main \
  -m fast stop
~~~

Or use the operating system's service manager. After stopping, verify the process has exited and no other PostgreSQL process is accessing the data directory.

Never delete the PID file or arbitrarily kill processes to simulate a clean shutdown.

## 29. Running the Actual Upgrade in Copy Mode

Illustrative example:

~~~bash
/usr/lib/postgresql/17/bin/pg_upgrade \
  -b /usr/lib/postgresql/16/bin \
  -B /usr/lib/postgresql/17/bin \
  -d /var/lib/postgresql/16/main \
  -D /var/lib/postgresql/17/main \
  --jobs=4 \
  --copy
~~~

Options:

- `-b`: old binary directory.
- `-B`: new binary directory.
- `-d`: old data directory.
- `-D`: new data directory.
- `--jobs`: number of parallel jobs for steps supporting parallelism.
- `--copy`: explicitly requests copy mode if supported by the binary.

You can omit `--copy` if it is the version's default. Always verify with the target binary's help output and documentation.

## 30. Running the Actual Upgrade in Link Mode

Use only when rollback implications have been explicitly decided:

~~~bash
/usr/lib/postgresql/17/bin/pg_upgrade \
  -b /usr/lib/postgresql/16/bin \
  -B /usr/lib/postgresql/17/bin \
  -d /var/lib/postgresql/16/main \
  -D /var/lib/postgresql/17/main \
  --jobs=4 \
  --link
~~~

Before running, verify that old/new data directories and relation locations satisfy hard-link requirements.

Never start the old cluster once the new cluster has begun writing to linked files.

## 31. Running the Actual Upgrade in Clone Mode

If the filesystem supports reflink:

~~~bash
/usr/lib/postgresql/17/bin/pg_upgrade \
  -b /usr/lib/postgresql/16/bin \
  -B /usr/lib/postgresql/17/bin \
  -d /var/lib/postgresql/16/main \
  -D /var/lib/postgresql/17/main \
  --jobs=4 \
  --clone
~~~

Test the filesystem and storage backend in staging. If clone is unsupported, switch to copy mode after cleaning up cluster state and re-preparing per the tool's guidance.

Do not assume `--clone` automatically falls back to `--copy` when reflink is unavailable.

## 32. Running the Actual Upgrade with copy-file-range

If the target `pg_upgrade` supports it:

~~~bash
/usr/lib/postgresql/17/bin/pg_upgrade \
  -b /usr/lib/postgresql/16/bin \
  -B /usr/lib/postgresql/17/bin \
  -d /var/lib/postgresql/16/main \
  -D /var/lib/postgresql/17/main \
  --jobs=4 \
  --copy-file-range
~~~

This mode still creates independent files. Actual speed depends on the kernel, filesystem, and storage. Confirm the option and support via `pg_upgrade --help` and target version docs.

## 33. Jobs and Parallelism

`--jobs` allows multiple upgrade steps to run in parallel where supported by the tool.

Increasing jobs can reduce elapsed time, but also increases:

- Disk I/O concurrency.
- CPU utilization.
- Memory pressure.
- Metadata operations.
- Load on tablespace volumes.

Do not default jobs to the CPU core count. Measure throughput and latency in staging; on constrained storage, too many jobs can lengthen total runtime.

## 34. pg_upgrade Logs and Output

Read both terminal output and log files generated by `pg_upgrade`.

Details to archive:

- Old/new versions.
- Command line and mode.
- Start/end timestamps.
- Job count.
- Check results.
- Warnings/errors.
- Objects requiring manual handling.
- Generated scripts.

Keep logs as part of the upgrade record. Do not delete the log directory before validation and the rollback window finish.

## 35. Post-Upgrade Generated Scripts

`pg_upgrade` often generates helper scripts for post-upgrade steps, such as:

- A script to run `ANALYZE` and rebuild planner statistics.
- A script to delete the old cluster once the operator determines it is safe.

Exact filenames and contents vary by version and OS. Read the actual generated files rather than assuming filenames or running them blindly.

Never run the script that deletes the old cluster before verifying the new cluster and passing the rollback decision point.

## 36. Starting the New Cluster for the First Time

After `pg_upgrade` reports success:

1. Review the new configuration.
2. Verify `shared_preload_libraries` and extension libraries.
3. Check port/socket and data directory.
4. Ensure application traffic is not yet routed here.
5. Start the new cluster with the target binaries.
6. Read startup logs.
7. Verify `SELECT version()` and `pg_is_in_recovery()` per topology.

Example:

~~~bash
/usr/lib/postgresql/17/bin/pg_ctl \
  -D /var/lib/postgresql/17/main \
  -l /var/log/postgresql/postgresql-17.log \
  start
~~~

Do not open application writes until mandatory checks complete.

## 37. Verifying Version and Database List

On the new cluster:

~~~sql
SELECT version();

SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database
ORDER BY datname;
~~~

Compare the inventory against the old cluster:

- Database names.
- Database owners.
- Tablespaces.
- Roles.
- Extension list.
- Object counts and business invariants.

Sizes may differ due to catalog/index representation or post-upgrade activity; discrepancies should be explained rather than judged by size alone.

## 38. Running ANALYZE After Upgrade

Planner statistics must be regathered so the planner selects good execution plans.

A common approach:

~~~bash
/usr/lib/postgresql/17/bin/vacuumdb \
  --all \
  --analyze-in-stages \
  --jobs=4
~~~

`--analyze-in-stages` collects statistics progressively so the database quickly gets usable statistics while a thorough pass continues.

Check options via `vacuumdb --help` on the target version. For large databases, `ANALYZE` can generate substantial load; monitor CPU/I/O and tune jobs accordingly.

## 39. Updating Extensions After Upgrade

Once the new server is running and extension libraries are installed:

~~~sql
SELECT
    extname,
    extversion
FROM pg_extension
ORDER BY extname;
~~~

If an extension has an update script to apply:

~~~sql
ALTER EXTENSION extension_name UPDATE;
~~~

Extension names and versions must be verified from package/vendor documentation. Do not blindly run `UPDATE` on every extension if no valid update path exists.

Verify functions, operators, types, and dependent applications.

## 40. Collation Versions and Reindex Considerations

Changes in OS libraries or collation providers/versions can affect text sorting order.

After the upgrade:

- Inspect collation version metadata.
- Check startup/runtime logs for collation mismatch warnings.
- Identify indexes depending on affected collations.
- Perform refresh/reindex per PostgreSQL guidance and the maintenance plan.

Never ignore collation warnings, as index ordering may no longer match current collation behavior.

## 41. Configuration Review

Compare old and new settings:

- Memory: `shared_buffers`, `work_mem`, `maintenance_work_mem`.
- Planner: `effective_cache_size`, `random_page_cost`, `seq_page_cost`.
- Connections: `max_connections`.
- WAL: `wal_level`, `max_wal_size`, `checkpoint_timeout`.
- Replication: `max_wal_senders`, `max_replication_slots`, `hot_standby`.
- Logging: `log_min_duration_statement`, `log_line_prefix`.
- Autovacuum.
- SSL/authentication.
- Extensions and custom GUCs.

Do not copy old values solely because the old cluster used them for a long time. Defaults and behaviors can change across major versions; review release notes and benchmark.

## 42. Checking Schemas and Objects

You can check object counts at the database level:

~~~sql
SELECT
    schemaname,
    count(*) AS table_count
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
GROUP BY schemaname
ORDER BY schemaname;
~~~

Check for invalid indexes:

~~~sql
SELECT
    ns.nspname AS schema_name,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    i.indisvalid,
    i.indisready
FROM pg_index AS i
JOIN pg_class AS idx
  ON idx.oid = i.indexrelid
JOIN pg_class AS tbl
  ON tbl.oid = i.indrelid
JOIN pg_namespace AS ns
  ON ns.oid = tbl.relnamespace
WHERE NOT i.indisvalid
   OR NOT i.indisready
ORDER BY ns.nspname, tbl.relname, idx.relname;
~~~

Combine this with application-level validation and your pre-upgrade catalog inventory.

## 43. Checking Roles and Privileges

`pg_upgrade` transfers many cluster-wide objects, yet you should still verify:

- Roles and role memberships.
- Database owners.
- Schema/table/sequence grants.
- Default privileges.
- Tablespace privileges.
- Replication roles.
- Login attributes.
- Password/authentication behavior.

Example:

~~~sql
SELECT
    rolname,
    rolsuper,
    rolinherit,
    rolcreaterole,
    rolcreatedb,
    rolreplication,
    rolcanlogin
FROM pg_roles
ORDER BY rolname;
~~~

Do not export passwords or secrets into logs. Inspect grants via catalogs/`psql` and test logging in with application roles.

## 44. Replication and HA After Major Upgrade

If the cluster participates in an HA topology:

- Plan upgrading primary and standbys according to your HA manager's supported procedure.
- Never allow an old standby to connect to the new primary assuming WAL formats are compatible.
- Determine whether standbys can be reused/rebuilt or must be recreated from a base backup.
- Update replication slots and connection strings to match the topology.
- Verify `archive_command`/`restore_command`.
- Update the HA manager, monitoring, and service endpoints.
- Rehearse failover after the upgrade.

A common approach is to upgrade/promote the primary per procedure and then rebuild/reseed standbys from the new primary. Exact steps depend on the replication setup and HA tool; never upgrade nodes independently without a runbook.

## 45. Logical Replication and External Consumers

If the cluster uses logical replication or CDC:

- Inventory publications and subscriptions.
- Inspect logical replication slots.
- Confirm connectors/CDC tools support the target major version.
- Check replication protocol and plugin compatibility.
- Verify consumer offsets/LSNs.
- Monitor retention and WAL growth during downtime.
- Plan restarting/recreating consumers if needed.

Do not assume external consumers will simply resume just because the database started.

## 46. Checking Application Compatibility

A running database server is not enough. Verify:

- Driver/JDBC/libpq versions.
- ORM behavior.
- Deprecated SQL features.
- Data type and protocol behavior.
- Query plans and latency.
- Authentication/TLS.
- Connection pools.
- Stored procedures/extensions.
- Background jobs.
- Backup/monitoring agents.

Run smoke tests and a representative workload in staging before shifting production traffic.

## 47. Rollback with Copy Mode

Copy mode keeps old cluster files independent. If validation fails before allowing writes on the new cluster:

1. Stop the new cluster.
2. Preserve the new data directory for investigation.
3. Start the old cluster using the old binaries.
4. Point endpoints back to the old cluster.
5. Restore application services per the runbook.

Once the new cluster has accepted writes, the old cluster lacks those new changes. Rolling back then requires data reconciliation or restore/replay per design; you cannot simply switch endpoints back and expect zero write loss.

Copy mode preserves the ability to return to **the old state at the time of upgrade**; it does not synchronize writes generated on the new cluster.

## 48. Rollback with Clone Mode

Clone mode creates an independent copy-on-write clone. The old cluster can be retained as a frozen fallback.

However, once the new cluster accepts writes, the old cluster still lacks those changes. You must establish authoritative data and handle write divergence before switching back.

Do not confuse being able to start the old cluster with being able to roll back the application without data loss.

## 49. Rollback with Link Mode

Link mode has a strict rollback boundary:

- Before the new cluster starts: there may still be an option to discard the new cluster and return to the old cluster following an appropriate recovery procedure.
- After the new cluster starts/writes data: the old cluster is no longer independent because files share hard links.

Never attempt to start the old cluster after the new cluster has written to hard-linked files. Use an independent backup for recovery if needed.

## 50. Testing Rollback Before Production

During rehearsal:

1. Restore the old cluster backup.
2. Run `pg_upgrade --check`.
3. Execute the upgrade with the planned mode.
4. Start the new cluster.
5. Run smoke tests.
6. Simulate a failure per the rollback plan.
7. Measure rollback duration.
8. Verify data consistency.
9. Document the point of no return for the chosen mode.

If using link mode, the rehearsal must prove the independent backup/restore procedure rather than relying on the old data directory after the new cluster starts.

## 51. Signs an Upgrade Is Incomplete

Do not open production writes if any of the following remain:

- Startup logs show extension/library errors.
- Databases or tablespaces are missing.
- Role/application login fails.
- Invalid indexes or broken object dependencies exist.
- Unresolved collation mismatches exist.
- Planner statistics have not been adequately collected.
- Replication, backups, or monitoring are not functioning.
- Application smoke tests have not passed.
- The rollback boundary is unclear.

Mark the upgrade complete only after database, application, and operations owners sign off on the checklist.

## 52. Common Mistakes

### 52.1. Using pg_upgrade for Minor Updates

Incorrect. Minor releases within the same major version typically do not require migrating data directories with `pg_upgrade`.

### 52.2. Running pg_upgrade Without a Backup

High risk. Upgrades modify the new cluster and can render the old cluster unusable depending on the mode.

### 52.3. Choosing Link Mode Solely for Speed

Incorrect. Link mode removes the ability to use the old cluster independently after the new cluster starts.

### 52.4. Thinking Clone Works Like a Hard Link

Incorrect. Copy-on-write cloning creates logically independent files; hard links share the same inode.

### 52.5. Thinking Copy Mode Automatically Rolls Back New Writes

Incorrect. The old cluster is a snapshot at upgrade time; it does not receive writes made on the new cluster.

### 52.6. Ignoring Tablespace Filesystems

Incorrect. Each tablespace can reside on a different volume with its own link/clone constraints.

### 52.7. Failing to Install Target Extension Binaries

Incorrect. SQL objects may remain while shared libraries or control files are incompatible or missing.

### 52.8. Skipping ANALYZE After Upgrade

Planner statistics may be absent or stale; query plans can be poor until statistics are regathered.

### 52.9. Copying the Old Configuration Verbatim

Incorrect. Settings may change semantics or be removed across major versions.

### 52.10. Opening Traffic Immediately After postgres Starts

Incorrect. You must validate extensions, roles, schemas, replication, backups, and application behavior first.

## 53. Lab: Preparing Two Clusters

Across two PostgreSQL lab installations:

1. Install old and target binaries.
2. Create the old cluster and add a database/table/index.
3. Take a restorable backup.
4. Initialize the new cluster using target `initdb`.
5. Install extension packages for the target.
6. Record ports, data directories, and tablespaces.

Verify `pg_upgrade --help` lists the required options.

## 54. Lab: Running --check

~~~bash
/path/to/new/bin/pg_upgrade \
  -b /path/to/old/bin \
  -B /path/to/new/bin \
  -d /path/to/old/data \
  -D /path/to/new/data \
  --check
~~~

Record:

- Check result.
- Warnings/errors.
- Log file path.
- Extensions or objects requiring attention.
- Disk/filesystem requirements.

Fix blockers and re-run `--check`.

## 55. Lab: Comparing Copy and Link

Perform on two separate lab copies, each restored from the same backup:

- Lab A: use `--copy`.
- Lab B: use `--link`.

Record elapsed time, filesystem space before/after, and behavior of the old cluster.

Do not reuse the same old data directory for consecutive runs if the link run caused old/new files to share inodes and the new cluster was started.

## 56. Lab: Testing Clone

If the filesystem supports reflink:

1. Create two clusters on clone-capable storage.
2. Run `pg_upgrade --check`.
3. Run the actual upgrade with `--clone`.
4. Observe space usage before/after.
5. Observe copy-on-write growth after the new cluster modifies data.
6. Verify the old cluster remains independent under filesystem semantics.

If the storage lacks support, record the error and test copy mode.

## 57. Lab: Post-Upgrade Validation

On the new cluster:

~~~sql
SELECT version();

SELECT
    datname,
    pg_size_pretty(pg_database_size(datname))
FROM pg_database
ORDER BY datname;

SELECT extname, extversion
FROM pg_extension
ORDER BY extname;

SELECT pg_is_in_recovery();
~~~

Run `ANALYZE`, check roles, tablespaces, indexes, representative queries, and application smoke tests.

## 58. Lab: Rehearsing Rollback

With copy mode:

1. Upgrade from a restored copy.
2. Keep application writes off the new cluster.
3. Stop the new cluster.
4. Start the old cluster.
5. Verify the application can connect and old data is intact.

Then run another rehearsal for the scenario where the new cluster has already accepted writes and document how data will be reconciled.

With link mode, test the old cluster only before starting the new cluster; once the new cluster starts, do not start the old cluster.

## 59. Production Upgrade Checklist

**Before maintenance**

1. Confirm supported source/target major versions.
2. Read release notes and `pg_upgrade` docs.
3. Inventory databases, roles, tablespaces, and extensions.
4. Verify backup/restore and WAL archiving.
5. Rehearse on a production-like clone.
6. Choose copy/link/clone/copy-file-range based on rollback, disk, and filesystem.
7. Install target binaries and extension packages.
8. Run `initdb` on the new cluster with compatible settings.
9. Run `pg_upgrade --check`.
10. Finalize the maintenance window and rollback boundary.

**During maintenance**

11. Stop writes and scheduled jobs.
12. Shut down the old cluster cleanly.
13. Verify data directories and tablespaces.
14. Run the actual `pg_upgrade`.
15. Save logs and generated scripts.
16. Review the new configuration.
17. Start the new cluster and read logs.

**After upgrade**

18. Run `ANALYZE` per plan.
19. Update extensions where needed.
20. Verify roles, grants, databases, tablespaces, and objects.
21. Check collation/index warnings.
22. Restore backups, monitoring, and replication.
23. Run application smoke tests and representative workloads.
24. Switch traffic after validation sign-off.
25. Delete the old cluster only after the rollback window closes.

## 60. Frequently Asked Questions

### Is pg_upgrade used for minor-version upgrades?

Usually not. Minor releases within the same major version generally swap binaries/packages following standard procedures without `pg_upgrade`.

### Does pg_upgrade copy every row via SQL?

Not in the traditional dump/restore sense. It transfers compatible relation files and updates catalog metadata for the target major version.

### Does copy mode preserve the old cluster?

Yes. It keeps the old data files independent, though the old cluster reflects only the pre-upgrade state and receives no writes from the new cluster.

### Does link mode require the same filesystem?

Hard links require old and new file locations to support linking on the same filesystem. Check both the data directory and tablespaces.

### Can the old cluster be started after the new cluster starts in link mode?

Not safely. Both clusters share inodes; the new cluster may have already modified files.

### How does clone differ from link?

Clone uses copy-on-write/reflink to create logically independent files; link uses hard links pointing to the same inode.

### Is clone supported on every filesystem?

No. The filesystem/storage must support reflink and the option must be present in the target `pg_upgrade` version.

### Does copy-file-range share data with the old cluster?

No. It is a kernel-assisted copy that creates independent files, unlike hard-link mode.

### Can multiple jobs be used?

You can use `--jobs` for steps supporting parallelism. Balance CPU and I/O capacity.

### Does pg_upgrade automatically copy postgresql.conf?

Do not assume configuration is migrated automatically. Review and prepare configuration files for the target version.

### Do extensions need to be reinstalled?

Compatible binaries/control files for the target must be present before upgrading. Afterward, `ALTER EXTENSION ... UPDATE` may be needed.

### Why is ANALYZE needed after upgrading?

Planner statistics must be regathered so row estimates and plan choices reflect current data.

### Can we roll back after the new cluster has accepted writes?

The old cluster lacks the new writes. You must reconcile/replay or restore per plan; you cannot merely switch endpoints.

### Does pg_upgrade automatically rebuild standbys?

Do not assume so. Your HA topology needs a dedicated procedure to rebuild/rejoin standbys per the target version and HA manager.

### When can the old cluster be deleted?

After the new cluster and applications are verified, new backups are validated, replication/monitoring are stable, and the rollback window has ended.

## 61. Summary

Key command patterns:

~~~bash
# Check options of the target binary.
/path/to/new/bin/pg_upgrade --help

# Check upgrade readiness.
/path/to/new/bin/pg_upgrade \
  -b /path/to/old/bin \
  -B /path/to/new/bin \
  -d /path/to/old/data \
  -D /path/to/new/data \
  --check

# Copy mode.
/path/to/new/bin/pg_upgrade \
  -b /path/to/old/bin \
  -B /path/to/new/bin \
  -d /path/to/old/data \
  -D /path/to/new/data \
  --jobs=4 \
  --copy

# Link mode: use only when accepting that the old cluster is unusable after the new starts.
/path/to/new/bin/pg_upgrade \
  -b /path/to/old/bin \
  -B /path/to/new/bin \
  -d /path/to/old/data \
  -D /path/to/new/data \
  --jobs=4 \
  --link

# Clone mode: requires reflink support.
/path/to/new/bin/pg_upgrade \
  -b /path/to/old/bin \
  -B /path/to/new/bin \
  -d /path/to/old/data \
  -D /path/to/new/data \
  --jobs=4 \
  --clone

# Post-upgrade statistics.
/path/to/new/bin/vacuumdb \
  --all \
  --analyze-in-stages \
  --jobs=4
~~~

Key principles to remember:

1. `pg_upgrade` is for major-version upgrades; minor updates normally do not need it.
2. Use the target version's `pg_upgrade` binary.
3. Old and new clusters must satisfy the target's compatibility requirements.
4. Run `--check` before the actual upgrade and resolve all blockers.
5. Copy mode creates independent files and leaves the old cluster intact.
6. Link mode is fast and space-efficient, but hard-link sharing renders the old cluster unsafe once the new cluster starts.
7. Clone mode uses reflink/copy-on-write when supported by the filesystem and keeps both clusters independent.
8. Copy-file-range accelerates file copying on supported environments while still creating independent files.
9. Factor in tablespaces and disk capacity when choosing a mode.
10. Backups and restore rehearsals are essential prerequisites before a production upgrade.
11. Install target-version extension binaries before running.
12. Review configuration files and deprecated settings after upgrading.
13. Run `ANALYZE` so the planner has accurate statistics.
14. Verify extensions, roles, privileges, collations, indexes, and application behavior.
15. Rebuild/rejoin standbys following the HA runbook.
16. The old cluster in copy/clone mode is a frozen fallback; new writes on the new cluster do not appear in the old one.
17. Link mode has a point of no return when the new cluster starts or writes data.
18. Delete the old cluster only after validation and the rollback window finish.

Decision diagram:

~~~text
Need a major-version upgrade?
             |
             v
    Backup + restore rehearsal
             |
             v
      pg_upgrade --check
             |
             v
    Choose file transfer mode
             |
       +-----+------+----------------+
       |            |                |
       v            v                v
     Copy          Link            Clone
       |            |                |
       v            v                v
  Independent    Hard links       Reflink/COW
  files          Very fast        Needs FS support
  Uses disk      Old loses        Old stays
  Old preserved  independence     independent
       |            |                |
       +-----+------+----------------+
             |
             v
        Actual pg_upgrade
             |
             v
    Start new cluster + logs
             |
             v
  Analyze + extensions + config
             |
             v
   Validate DB + application + HA
             |
             v
        Cutover traffic
             |
             v
   Rollback window over & backups ready?
             |
             v
       Controlled old cluster removal
~~~

**Conclusion:** `pg_upgrade` speeds up major-version upgrades by transferring relation files and updating catalogs. Choose a mode based on filesystem support, storage capacity, downtime budget, and rollback requirements: **copy prioritizes independence, link prioritizes speed while sacrificing old-cluster rollback after startup, clone balances speed and old-cluster retention where reflink is supported, and copy-file-range speeds up copying while keeping files independent**. An upgrade is complete only when the new cluster, extensions, configuration, planner statistics, replication, and applications are all verified.
