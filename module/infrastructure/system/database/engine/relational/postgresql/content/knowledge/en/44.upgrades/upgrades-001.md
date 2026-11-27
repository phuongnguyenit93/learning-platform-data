# Distinguishing PostgreSQL Minor Updates and Major Upgrades

## 1. Why distinguish between a minor update and a major upgrade?

PostgreSQL releases updates at two levels. A **minor release update** updates a server within the same major version line, typically to receive bug fixes and security fixes. A **major version upgrade** moves a cluster from one major version to another, for example from PostgreSQL 16 to PostgreSQL 17.

These two operations differ in compatibility, data directory, downtime, extensions, replication, and rollback. Installing new binaries does not mean the old data has been converted. A PostgreSQL cluster has a data directory created by a specific major version; you cannot by default start a new major binary directly on an old major data directory.

| Item | Minor update | Major upgrade |
|---|---|---|
| Example | 17.2 → 17.3 | 16 → 17 |
| Goal | Bug/security fixes within the same major line | Move to a new major line |
| Data directory format | Remains compatible within the major line | May change |
| pg_upgrade | Normally not needed | Commonly usable |
| Dump/restore | Not needed for a minor update itself | A common method |
| Logical migration | Normally not needed | Can reduce downtime |
| Application compatibility | Usually fewer changes, still needs checking | Needs thorough testing |
| Downtime | Usually requires a server restart | Depends on the method |
| Rollback | Do not treat binary downgrade as a rollback plan | Needs a backup or failback strategy |

```text
Minor update:
  PostgreSQL 17.2
       |
       | install compatible 17.3 binaries
       | stop / replace / start
       v
  PostgreSQL 17.3
  Same major data format

Major upgrade:
  PostgreSQL 16 cluster
       |
       | pg_upgrade OR dump/restore
       | OR logical replication migration
       v
  PostgreSQL 17 cluster
  New major data directory / catalogs
```

A minor update is usually simpler, yet still requires backups, package checks, and a restart plan. A major upgrade is a database platform change project: it requires evaluating applications, extensions, drivers, HA topology, data migration, performance, and rollback.

### Learning Objectives

After this lesson, you will be able to:

1. Read PostgreSQL version numbers accurately and classify minor vs. major releases.
2. Explain how a minor update differs from a major upgrade in data format and compatibility.
3. Plan package/binary updates without confusing them with cluster conversion.
4. Choose between `pg_upgrade`, dump/restore, and logical replication.
5. Understand `pg_upgrade` copy, link, and clone modes.
6. Prepare extension, collation, driver, and application compatibility.
7. Plan for physical replication, logical replication, and CDC consumers.
8. Define downtime, cutover, and rollback strategies.
9. Run preflight checks and `pg_upgrade --check`.
10. Verify extensions, indexes, sequences, statistics, jobs, and permissions after an upgrade.
11. Build a performance baseline and regression tests.
12. Manage managed PostgreSQL, containers, and package-managed clusters.
13. Design a backup, PITR, and recovery plan.
14. Avoid starting a major binary on an old data directory or deleting the old cluster too early.
15. Complete checklists and runbooks for both minor updates and major upgrades.

---

## 2. How to read PostgreSQL version numbers

For PostgreSQL 10 and later, the version number has the form `major.minor`, for example `16.4` or `17.2`:
- The first number is the major version.
- The second number is the minor release within that major line.

Examples:
- 16.1 → 16.2: minor update.
- 16.2 → 17.0: major upgrade.

Before PostgreSQL 10, numbering worked differently. For example, `9.6.24` belongs to the `9.6` major line; the last number is the minor release. Do not apply modern numbering rules to misread older versions.

### 2.1. Checking a running server

```sql
SELECT version();

SHOW server_version;
SHOW server_version_num;
```

`server_version` is the server's version string. `server_version_num` is an integer useful for version-comparison scripts.

### 2.2. Client version is not server version

```bash
psql --version
pg_dump --version
pg_config --version
```

These commands report the version of the client/tool being invoked. They do not prove that the server the application connects to is running the same version.

### 2.3. Checking the right endpoint

In environments with proxies, poolers, primaries, and standbys, connect to each endpoint and record the server version, role, and cluster identity. Avoid checking a single node and assuming the result applies to the entire topology.

### 2.4. Extension versions are separate information

A server may run PostgreSQL 17.2 while extensions such as PostGIS, `pg_stat_statements`, or internal extensions have their own versions. Record the server major version, package version, and extension versions.

## 3. What is a minor release update?

A minor release is an update within the same major line. The PostgreSQL project releases minor updates to fix bugs, security vulnerabilities, and identified operational issues.

A typical minor update:
- Keeps the same major data directory format.
- Does not require dump/restore.
- Does not require `pg_upgrade`.
- Requires replacing binaries/packages according to OS or vendor procedures.
- Usually requires restarting the server so the new process runs with the new binaries.
- Should update nodes in an HA topology following a supported procedure.

### 3.1. Minor does not mean risk-free

A bug fix can change the behavior of a code path that previously had a bug. A security fix may require configuration or client behavior changes. Review release notes and test critical workloads.

### 3.2. A minor update does not migrate the data directory

If you are running major 16, updating from 16.2 to 16.3 still remains on major 16. Do not create a major 17 cluster and expect a package update to automatically migrate the data.

### 3.3. Restart and downtime

The PostgreSQL server process must be restarted to load the new binaries. Actual downtime depends on HA, orchestration, connection draining, and startup/recovery time.

### 3.4. Do not arbitrarily delay security fixes

Follow release announcements and your organization's patching policy. Plan regular updates, verify backups, and apply security updates according to risk level.

## 4. What is a major version upgrade?

A major upgrade moves a cluster to a new major version, for example PostgreSQL 15 to 16 or 16 to 17.

A major release can change:
- System catalogs and internal metadata.
- Data representation or storage behavior.
- SQL syntax/semantics and reserved keywords.
- Planner/executor behavior.
- Replication, monitoring, and configuration parameters.
- Extension APIs/ABI.
- Defaults and operational behavior.

Therefore, a new major binary must not be assumed able to open an old major data directory directly.

### 4.1. Common methods

- `pg_upgrade`: converts cluster files/catalogs to the new major version along a supported upgrade path.
- Dump/restore: exports logical objects/data and loads them into a new cluster.
- Logical replication or migration pipeline: synchronizes changes to a new cluster and then cuts over.
- Managed service workflow: the provider orchestrates a supported upgrade process.

### 4.2. Major upgrades may require application changes

Drivers, ORMs, extensions, SQL behavior, planner plans, and configuration defaults may change. Test the application as part of the upgrade.

### 4.3. Not every major version can jump directly

`pg_upgrade` supports specific source versions according to each release's documentation. If the source is too old or a direct upgrade path is unsupported, you must upgrade through an intermediate version or use dump/restore.

### 4.4. Not just upgrading the binary

A major upgrade is a conversion of the cluster, data, and ecosystem. The plan must include backup, validation, cutover, and recovery.

## 5. Data directory compatibility

The data directory contains database files, system catalogs, WAL, and cluster metadata. PostgreSQL major versions can change internal formats and catalogs.

### 5.1. Do not start a new major binary directly on an old data directory

For example, do not run a PostgreSQL 17 binary on a PostgreSQL 16 data directory as if it were a minor update. The server may refuse to start, or the cluster may be damaged if mishandled.

### 5.2. Minor releases within the same major line

Minor releases are designed to be compatible with that major line's data format. The package/binary update procedure does not require converting the cluster with `pg_upgrade`.

### 5.3. Data directory paths may differ

Package managers or distributions may use different cluster directories per major version. Verify `data_directory`, the service unit, and the cluster manager before stopping or starting.

### 5.4. Do not delete the old data directory too early

Keep the old cluster/backup until the upgrade is verified, the rollback window has ended, and the retention policy allows cleanup.

## 6. Building an inventory before upgrading

A good inventory should include:
- PostgreSQL server version and package/build.
- Operating system, architecture, and filesystem.
- Data directory, tablespaces, and WAL directory.
- Database names, owners, sizes, and encodings.
- Roles, memberships, grants, and tablespaces.
- Extensions and versions.
- Collations/locales.
- Replication slots, publications, subscriptions, and downstream consumers.
- Backup/PITR/archive status.
- Application drivers, ORMs, and connection poolers.
- Scheduled jobs, cron, extensions, and external integrations.
- Configuration files, include directories, and custom settings.
- Monitoring/exporters and backup agents.
- Current performance baseline and SLOs.

### 6.1. Server and database inventory

```sql
SELECT version();

SELECT
    datname,
    pg_get_userbyid(datdba) AS owner,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate,
    datctype,
    pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database
WHERE datallowconn
ORDER BY pg_database_size(datname) DESC;
```

### 6.2. Extensions

```sql
SELECT
    e.extname,
    e.extversion,
    n.nspname AS schema_name
FROM pg_extension AS e
JOIN pg_namespace AS n
  ON n.oid = e.extnamespace
ORDER BY e.extname;
```

### 6.3. Replication topology

```sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
```

Run on the primary; results depend on role and version. Inventory logical slots, publications/subscriptions, and CDC consumers separately.

### 6.4. Configuration inventory

```sql
SELECT
    name,
    setting,
    unit,
    source,
    pending_restart
FROM pg_settings
ORDER BY name;
```

Do not copy the entire old configuration into the new major version without reviewing it. Some parameters may be renamed, removed, have changed defaults, or no longer be meaningful.

## 7. Reading release notes and compatibility changes

Before upgrading, read:
- Release notes for every major version you will pass through.
- Upgrade documentation for the target major version.
- Extension compatibility matrix.
- OS/package release notes.
- Cloud provider maintenance/upgrade documentation if using a managed service.
- Driver/ORM release notes.
- HA manager/proxy/pooler compatibility.

### 7.1. Removed/renamed parameters

An old parameter may be removed or replaced. The server may log a warning or fail to start if the configuration contains an invalid setting depending on how it is managed.

### 7.2. SQL behavior

Reserved keywords, planner behavior, function signatures, and type behavior may change. Run integration tests and a query corpus.

### 7.3. Authentication/TLS

Check password encryption, authentication methods, certificates, TLS libraries, and client compatibility.

### 7.4. Defaults

A new default may affect memory, the planner, parallelism, WAL, or maintenance. Compare old and new `pg_settings` instead of copying the old config verbatim.

## 8. Method 1: minor release update

General procedure:

1. Confirm the current major line and target minor release.
2. Read release notes and security advisories.
3. Verify backup and restore readiness.
4. Check the package/binary matches the OS/architecture.
5. Plan the restart/failover.
6. Drain or shift traffic according to the HA runbook.
7. Update binaries/packages.
8. Start the server using the same major data directory.
9. Verify server version, logs, extensions, and connectivity.
10. Verify replication, backups, jobs, and application health.
11. Update the remaining nodes according to the topology plan.
12. Record the results and close the change.

### 8.1. Backups are still necessary

Even though minor releases are data-format compatible, backups/PITR provide protection against operational errors, package issues, or bug regressions.

### 8.2. Do not change many things at once

Avoid combining a minor update with an OS upgrade, major extension upgrade, schema migration, and config overhaul without separate testing. Isolated changes make rollback and root-cause analysis clearer.

### 8.3. Verify the package source

Use a supported repository/package and verify the binary path. A single machine can have multiple major versions installed side by side.

### 8.4. Verify the service actually runs the new binary

`psql --version` only tells you the client version. Use `SELECT version()` from the server and check the process/service executable when needed.

## 9. Minor updates in an HA topology

With physical streaming replication, primary and standby generally need to remain on the same major line. Minor updates can be rolled out sequentially to minimize downtime, but the order and ability to run different minor builds temporarily must follow PostgreSQL, HA manager, and vendor documentation.

A common plan in systems that support rolling minor updates:
1. Confirm the standby is healthy, replay lag is low, and it is failover-ready.
2. Update the standby according to the procedure.
3. Verify standby reconnect/replay.
4. Perform a switchover/failover if supported by the design and tested.
5. Update the node that became the standby.
6. Verify the entire topology is on the target minor release.

### 9.1. Do not assume rolling updates are supported

Some orchestration/providers have specific procedures. If a mixed minor state is unsupported or a cluster-wide restart is required, follow that guidance.

### 9.2. Synchronous replication

Monitor `synchronous_standby_names`, `sync_state`, and commit availability while restarting each node. Stopping a synchronous standby can cause commits to wait or reduce redundancy.

### 9.3. Failover readiness

Check fencing, promotion policy, replication slots, archiving, and application routing. Do not look only at whether the node process is running.

### 9.4. Complete across all nodes

After the change window, record the version of every primary, standby, backup server, and logical consumer. Avoid leaving part of the topology behind on an older release.

## 10. Major upgrade: choosing a method

| Method | How it works | Downtime | Advantages | Trade-offs |
|---|---|---|---|---|
| `pg_upgrade` | Converts cluster files/catalogs to the new major version | Requires a cutover window | Fast for large clusters | Requires source/target, extension, and storage compatibility |
| Dump/restore | Exports logical objects/data, imports into a new cluster | Can be long | Portable, rebuilds logical data | Slow for large datasets, requires handling globals/ownership |
| Logical replication | Copies baseline then applies changes continuously | Can reduce downtime | Flexible blue-green/cutover | DDL/sequences and some objects must be managed separately |
| Managed upgrade | Provider orchestrates the upgrade | Per service workflow | Integrated with service infrastructure | Less control, provider-dependent |

### 10.1. There is no single best method for every cluster

The decision depends on data size, downtime budget, version path, extensions, replication topology, disk capacity, and testing capability.

### 10.2. `pg_upgrade` is suitable when

Source/target versions are supported, extensions are compatible, and you want fast conversion without dumping/restoring all data.

### 10.3. Dump/restore is suitable when

You want portability, layout/schema changes, platform/architecture changes, or `pg_upgrade` does not support the source path. Restore time can be long.

### 10.4. Logical replication is suitable when

You need to sync changes to the new cluster while the old cluster continues accepting writes, and you can design DDL/sequence/cutover handling and address its limitations.

## 11. Method 2: `pg_upgrade`

`pg_upgrade` upgrades a cluster's data files to the new major version's format along a supported upgrade path. It is not simply copying the entire directory.

General procedure:
1. Install target major binaries.
2. Install target-compatible extension libraries.
3. Create/initialize the target cluster with an appropriate configuration.
4. Stop the old cluster as required.
5. Run preflight/`pg_upgrade --check`.
6. Run `pg_upgrade` with the chosen mode.
7. Run post-upgrade scripts generated/recommended by the tool.
8. Start the target cluster.
9. Validate and switch application traffic.

### 11.1. Check the upgrade path

Read the `pg_upgrade` documentation for the target version to confirm the source major version is supported. Do not assume you can jump directly across multiple major versions.

### 11.2. Two binary directories

`pg_upgrade` needs to know the old and new executable directories as well as the old/new data directories. Ensure the correct binaries for each major version are used without `PATH` confusion.

### 11.3. The old cluster must be properly prepared

Stop the server, confirm no writing processes remain, handle prepared transactions, and follow `pg_upgrade`/version requirements.

### 11.4. Preflight before the maintenance window

Run `--check` and resolve all failures before cutover day. Do not make the outage window the first time you run `pg_upgrade`.

## 12. `pg_upgrade --check`

Illustrative command example:

```bash
pg_upgrade \
  --old-bindir=/usr/lib/postgresql/16/bin \
  --new-bindir=/usr/lib/postgresql/17/bin \
  --old-datadir=/var/lib/postgresql/16/main \
  --new-datadir=/var/lib/postgresql/17/main \
  --check
```

Paths are examples; substitute your actual package layout. On Windows or in managed environments, invocation and paths may differ.

### 12.1. `--check` does not convert the cluster

This is a preflight mode to verify upgrade prerequisites. It does not replace backups, rehearsals, or post-upgrade validation.

### 12.2. Read the entire output

A missing extension library, unsupported data type, or failed prerequisite can prevent the upgrade from proceeding. Save the output and fix every blocker.

### 12.3. Re-check after fixing

After installing extension packages, fixing configuration, or handling objects, re-run `--check` to confirm.

### 12.4. Do not ignore warnings

Some warnings require manual review or running a script. Assign an owner and action before cutover.

## 13. `pg_upgrade` copy, link, and clone modes

`pg_upgrade` provides different ways to transfer data files, depending on version/platform:

| Mode | How it works | Characteristics |
|---|---|---|
| Copy | Copies files to the new cluster | Uses more disk/time; old cluster files remain independent |
| Link | Hard-links files when filesystem conditions are met | Fast, saves disk space; old cluster is no longer safe to run once the new cluster starts writing |
| Clone | Uses filesystem reflink/clone when supported | Can be fast and initially block-efficient; filesystem/platform dependent |

### 13.1. Copy mode

Copy is usually the most straightforward choice for storage rollback because old data files do not share inodes with the new cluster. It requires sufficient disk space and copy time.

### 13.2. Link mode

Hard links enable fast conversion, but once the new cluster writes to the shared files, the old cluster is no longer a safe rollback copy. Do not start the old cluster as if its data were independent.

### 13.3. Clone mode

Clone/reflink depends on filesystem and `pg_upgrade`/platform support. Verify actual support; do not assume every volume or cloud filesystem supports it.

### 13.4. Choose the mode based on the rollback plan

If you need to keep the old cluster to fall back to, copy or clone is more suitable than link, though you still must understand that new writes after cutover do not automatically appear in the old cluster.

## 14. Dump/restore for major upgrades

Dump/restore transfers logical schema and data from the old cluster to the new cluster.

Example creating a custom-format dump:

```bash
pg_dump -Fc -d appdb -f appdb.dump
```

Create the new database and restore:

```bash
createdb -T template0 appdb
pg_restore -d appdb --jobs=4 appdb.dump
```

Global objects such as roles and tablespaces need to be handled separately, for example:

```bash
pg_dumpall --globals-only > globals.sql
```

Commands are illustrative; verify tool versions, connections, permissions, owners, and environment.

### 14.1. Dump format

Custom/directory formats support parallel restore via `pg_restore`. Plain SQL suits simple pipelines but lacks the same parallel restore capability.

### 14.2. Roles and grants

A database dump does not automatically cover global objects completely. Inventory roles, memberships, password/auth settings, and tablespaces.

### 14.3. Extensions

Install compatible extension binaries on the target before restoring extension objects. You may need to create extensions and restore data according to each extension's instructions.

### 14.4. Downtime

If the dump is taken while the old cluster continues accepting writes, you need a consistency/cutover strategy. A single dump does not automatically sync writes occurring after the snapshot.

## 15. Logical replication migration

Logical replication can help build a new major cluster while the old cluster continues serving writes:
1. Prepare a compatible schema on the target.
2. Create a publication on the source.
3. Create a subscription on the target.
4. Copy initial data.
5. Apply changes continuously.
6. Monitor lag and errors.
7. Prepare the cutover window.
8. Stop writes to the source.
9. Wait for the target to apply all remaining changes.
10. Sync sequence state and objects outside the publication.
11. Switch the application to the target.
12. Verify before retiring the source.

### 15.1. DDL is not automatically propagated by logical replication

Schema changes must be applied manually or via a migration pipeline on the target in a compatible order.

### 15.2. Sequence state needs separate handling

Logical replication does not automatically sync sequence values like table rows. Before cutover, determine and synchronize sequence state to avoid duplicate IDs.

### 15.3. Object limitations

Some objects/data paths are not covered by logical table replication, such as large objects and global objects. Verify limitations by version and extension.

### 15.4. Initial sync and data validation

Copy completion does not prove every business invariant is intact. Compare row counts, key ranges, checksums/aggregates, and constraints.

## 16. Blue-green upgrade

Blue-green is an approach running two environments:
- Blue: the current cluster serving traffic.
- Green: the new major cluster being prepared and synchronized.
- Cutover: switching application traffic to green once conditions are met.

Logical replication or another migration pipeline can keep green caught up near blue.

### 16.1. Blue continues serving during preparation

Reduces downtime but adds complexity: replication lag, DDL compatibility, writes, and cutover coordination.

### 16.2. Freeze writes

Before cutover, stop/queue writes to blue according to plan to establish the final synchronization point.

### 16.3. Drain connections

Switch application pools, background workers, scheduled jobs, and external integrations to green. Do not only change the endpoint for web servers.

### 16.4. Do not dual-write arbitrarily

Writing simultaneously to both blue and green can create divergence and ordering problems. Use a single source of truth during the migration window.

## 17. Preparing extensions

Extensions can contain SQL objects, shared libraries, C functions, background workers, types/operators, index access methods, and upgrade scripts.

### 17.1. Binary compatibility

Extension shared libraries typically require a build/package compatible with the new PostgreSQL major version. Old binaries cannot be assumed to load on a new major version.

### 17.2. Install packages before `pg_upgrade`

If `pg_upgrade` requires extension libraries on the target, install the right package/version before running preflight checks.

### 17.3. SQL extension version

Check `extversion` on the old cluster and available extension versions on the target.

```sql
SELECT
    extname,
    extversion
FROM pg_extension
ORDER BY extname;
```

### 17.4. `ALTER EXTENSION UPDATE`

After installing binaries and corresponding update scripts:

```sql
ALTER EXTENSION extension_name UPDATE;
```

Substitute the extension name and target version according to extension documentation. Not every extension supports every upgrade path.

### 17.5. Extension-specific upgrade paths

PostGIS, TimescaleDB, `pg_partman`, and internal extensions have their own procedures. Follow compatibility matrices, intermediate steps, and required maintenance.

## 18. Collation and locale changes

Collation determines text ordering/comparison. A new OS libc or ICU version can change collation behavior.

### 18.1. Why pay attention?

Indexes built under an old collation may no longer match the sort order of the new collation. This can cause incorrect sort/lookup results if unaddressed.

### 18.2. Checking collation versions

On supported versions:

```sql
SELECT
    oid,
    collname,
    collversion,
    pg_collation_actual_version(oid) AS actual_version
FROM pg_collation
WHERE collversion IS DISTINCT FROM pg_collation_actual_version(oid);
```

The query should be adjusted for actual catalog/version and privileges.

### 18.3. Reindex affected objects

When collation versions change, identify indexes depending on collations and reindex according to documentation. Do not merely refresh metadata and assume the index has been rebuilt.

### 18.4. Database default collation

Database locale and column-specific collations may differ. Inventory all critical collations.

## 19. Application, driver, and ORM compatibility

A major upgrade requires testing:
- Drivers: libpq/JDBC/Npgsql/psycopg/Node clients.
- ORM dialects and generated SQL.
- Prepared statements.
- Connection poolers/proxies.
- Authentication/TLS.
- SQL syntax and reserved words.
- Data types, timestamps, JSON, arrays, ranges.
- Error handling and SQLSTATE.
- Transaction isolation assumptions.
- COPY/import/export workflows.

### 19.1. Driver support

Update drivers according to the version matrix and verify TLS/authentication. Do not assume an old client binary is compatible with every new major server.

### 19.2. Prepared statements

Changes in planner or server behavior can affect prepared statements/generic plans. Test query paths and pooler modes.

### 19.3. ORM generated SQL

An ORM upgrade or PostgreSQL dialect change may generate different SQL. Capture a query corpus and run integration tests.

### 19.4. Authentication

Check password encryption, SCRAM, certificate validation, `pg_hba.conf`, and client library support.

## 20. Configuration review

Do not copy the old `postgresql.conf` file verbatim to the target.

Groups to review:
- Memory: `shared_buffers`, `work_mem`, `maintenance_work_mem`.
- WAL/checkpoints: `max_wal_size`, `checkpoint_timeout`, `wal_compression`.
- Replication: `max_wal_senders`, `max_replication_slots`, `wal_level`.
- Connections: `max_connections`, reserved connection settings.
- Parallelism: worker limits, parallel costs.
- Vacuum: autovacuum settings, freeze thresholds.
- Logging: `log_line_prefix`, duration, lock waits.
- Planner: cost parameters, statistics targets.
- SSL/authentication.
- Extension-specific settings.

### 20.1. Removed parameters

Remove or replace settings that are no longer supported according to target release notes.

### 20.2. Changed defaults

Compare old effective values against new defaults. You do not need to override every old default if the target has better behavior, but you must test.

### 20.3. `pending_restart`

`pg_settings.pending_restart` helps identify settings that require a restart after changing. Not every setting requires a restart.

### 20.4. Configuration files

Verify include files, ownership, permissions, secrets, service environment, and configuration management.

## 21. Replication and HA after a major upgrade

Physical streaming replication across different major versions is not a standard upgrade mechanism. A standby on an old major version cannot continue using its data directory as a physical standby of a new major primary.

### 21.1. Rebuild physical standbys

After the primary is upgraded, plan to create/rebuild physical standbys using a base backup or supported HA tooling from the new major cluster.

### 21.2. Synchronous configuration

Recreate `synchronous_standby_names` and verify `sync_state` and quorum/priority behavior. Do not copy old topology configs without verifying node identities.

### 21.3. Replication slots

Inventory physical/logical slots and downstream consumers. Slot compatibility/state across a major upgrade depends on version/method; do not assume all slots continue working.

### 21.4. CDC consumers

Debezium, logical decoding consumers, and data pipelines need plugin, slot state, schema change, and offset checks. A resnapshot/reconfiguration may be needed.

## 22. Backup and recovery plan before upgrading

Before both minor updates and major upgrades:
- Verify the most recent backup.
- Check continuous WAL archiving.
- Verify the restore procedure.
- Record the recovery point/objective.
- Identify an independent storage location.
- Ensure backups do not depend solely on the cluster being upgraded.
- Rehearse a restore in a separate environment.

### 22.1. An untested backup is not proof of recovery

Checking that a file exists does not prove a backup is usable. Perform a restore test and validation.

### 22.2. Base backup and WAL

PITR requires a base backup along with continuous WAL up to the recovery target. Verify archive status and retention.

### 22.3. Back up the old cluster before `pg_upgrade`

Keep an independent backup. The old data directory does not replace a backup, especially when using link mode.

### 22.4. Back up configuration and global objects

Save configuration, roles, grants, tablespaces, certificates, secret references, and service definitions per policy.

## 23. Minor update rollback

Minor releases in the same major line have compatible data formats, yet reinstalling the old binary should not be treated as a supported rollback in all situations.

### 23.1. Read vendor/project guidance

If you hit a regression, follow release- and package-specific guidance. A rollback may require restoring a backup or downgrading packages via a supported procedure.

### 23.2. Do not downgrade binaries arbitrarily

Even when the data format is unchanged, bug fixes or catalog behavior can make reverting to old binaries unsupported as an operational option.

### 23.3. Rollback via restore

If certainty is needed, restore a backup/PITR to a suitable cluster and verify the data loss window. This is a recovery operation, not merely a package rollback.

### 23.4. Decide before maintenance

Document rollback conditions, decision maker, maximum time allowed, and how traffic will be switched.

## 24. Major upgrade rollback

Major upgrades are harder to roll back because the new cluster may accept writes after cutover.

### 24.1. Keeping the old cluster

With copy/clone mode or dump/restore, the old cluster can be kept independent during the rollback window. Link mode does not keep the old cluster safe once the new cluster begins writing.

### 24.2. Writes after cutover

If the application has written to the new cluster, the old cluster does not automatically receive those writes. Reverting to the old cluster can lose new data.

### 24.3. Failback strategy

If rollback is required after opening writes, you must have a pre-designed reverse replication/change capture or business reconciliation plan. You cannot simply switch the connection string back.

### 24.4. Rollback decision deadline

Set a rollback cutoff point. Once passed, you may choose forward-fix rather than reverting to the old cluster.

## 25. Downtime planning

Downtime consists of multiple phases:
- Stop writes/drain traffic.
- Stop the database or freeze the source.
- Upgrade/copy/restore/catch-up.
- Start the target.
- Run scripts/`ANALYZE`.
- Validate critical paths.
- Switch application endpoints.
- Warm caches/connection pools.
- Resume background jobs.
- Monitor stabilization.

### 25.1. `pg_upgrade`

Typically shortens time compared to full dump/restore, but still requires downtime for cutover and final conversion steps.

### 25.2. Dump/restore

Duration depends on database size, network, compression, restore parallelism, index builds, and extension setup.

### 25.3. Logical replication

Can move most of the copy/catch-up outside the maintenance window, though cutover still requires stopping writes and verifying the target has caught up.

### 25.4. Rehearsal

Run a trial on a production-sized copy and time each phase. Use real measurements to set the maintenance window.

## 26. Preparing the `pg_upgrade` target cluster

Before upgrade day:
1. Install target major binaries.
2. Install compatible extension libraries.
3. Create the target data directory.
4. Initialize the target cluster per `pg_upgrade` requirements.
5. Review locale/encoding/checksum compatibility.
6. Identify tablespaces and filesystems.
7. Prepare the new configuration.
8. Run `pg_upgrade --check`.
9. Read the generated post-upgrade scripts.
10. Rehearse on a copy.

### 26.1. Tablespace paths

Verify tablespace paths and permissions on the target. Do not let the upgrade succeed only for the service to fail accessing a mount.

### 26.2. Disk capacity

Copy mode requires extra storage. Clone/link have their own conditions. Account for WAL, temporary files, logs, and the rollback copy.

### 26.3. Port and service isolation

Old and new clusters must be started on the proper ports/endpoints during rehearsal. Avoid having applications accidentally connect to an unvalidated target.

### 26.4. Ownership/permissions

The service user needs read/write permissions on the data directory and tablespaces. Check owner/group before startup.

## 27. Cutover checklist for `pg_upgrade`

1. Announce maintenance and stop writes.
2. Drain application connections/jobs.
3. Verify no client sessions remain except the operator.
4. Check prepared transactions.
5. Stop the old PostgreSQL cleanly as required.
6. Run `pg_upgrade` with the selected mode.
7. Read the output and resolve any errors.
8. Run generated post-upgrade scripts.
9. Start the target cluster.
10. Verify server version, logs, and database connectivity.
11. Run `ANALYZE`/statistics scripts.
12. Validate extensions, indexes, sequences, roles, and applications.
13. Rebuild/rejoin HA replicas.
14. Switch traffic and monitor.
15. Retain the old cluster/backup until the rollback window ends.

### 27.1. Do not skip post-upgrade scripts

`pg_upgrade` may generate scripts such as `analyze_new_cluster` or `delete_old_cluster`. Read their contents and execute them in the right order. Do not run cleanup scripts before the rollback window closes.

### 27.2. Statistics

Planner statistics should not be assumed to transfer completely. Run `ANALYZE` as instructed so the planner has accurate statistics.

### 27.3. Application traffic

Open traffic only after smoke tests and validation of critical operations.

### 27.4. Old cluster cleanup

Deleting the old cluster is not easily reversible. Clean up only after backup, rollback window, and approval/policy conditions are satisfied.

## 28. Post-upgrade extension validation

Check:

```sql
SELECT
    extname,
    extversion
FROM pg_extension
ORDER BY extname;
```

Then:
- Confirm shared libraries are present and match the new major version.
- Check extension version scripts.
- Run `ALTER EXTENSION UPDATE` when required.
- Test extension functions/operators/indexes.
- Check background workers and jobs.
- Review server logs for load errors.
- Confirm backup/restore supports the new extension version.

### 28.1. Extension package and SQL version are different

Installing the binary package does not necessarily update SQL objects inside the database. Check both.

### 28.2. Unsupported extensions

If an extension has no build for the target major version, you must replace it, upgrade along an intermediate path, or remain on the old cluster until a solution exists.

### 28.3. Extensions with their own data migration

Some extensions require running migration scripts or storage changes. Read vendor/project guidance.

### 28.4. Testing index access methods

Extensions with custom index access methods/operator classes need their indexes and query plans tested after the upgrade.

## 29. Post-upgrade sequence validation

Logical migration/blue-green requires special attention to sequence state. `pg_upgrade` normally handles sequence data during cluster conversion, though verification is still needed; dump/restore and logical replication workflows have their own procedures.

List sequences:

```sql
SELECT
    schemaname,
    sequencename,
    start_value,
    min_value,
    max_value,
    increment_by,
    cycle,
    cache_size,
    last_value
FROM pg_sequences
ORDER BY schemaname, sequencename;
```

### 29.1. Sequences are not like table rows

Logical replication does not automatically sync sequence progression like table changes. A target can have the latest rows while a sequence's next value is still lower than existing keys.

### 29.2. Sequence cutover

Stop source writes, determine safe sequence values, and set target state according to the migration procedure. Watch for sequence caches and sessions holding cached values.

### 29.3. Identity columns

Identity columns use underlying sequences. Check ownership/dependency and the next generated value.

### 29.4. Practical `INSERT` testing

Use an appropriate transaction/test table to verify generated IDs do not collide; do not test by arbitrarily creating production data.

## 30. Post-upgrade index and constraint validation

Check invalid indexes:

```sql
SELECT
    n.nspname,
    c.relname AS index_name,
    i.indisready,
    i.indisvalid
FROM pg_index AS i
JOIN pg_class AS c
  ON c.oid = i.indexrelid
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE NOT i.indisready OR NOT i.indisvalid
ORDER BY n.nspname, c.relname;
```

### 30.1. Indexes after collation changes

Identify indexes depending on changed collations and reindex per documentation.

### 30.2. Constraints

Check primary keys, unique, foreign keys, check constraints, and validation states.

### 30.3. Extension indexes

Indexes using extension operator classes/access methods must be tested and rebuilt if required by the extension.

### 30.4. Query plan regression

A valid index does not guarantee the planner picks a good plan. Run representative queries and compare `EXPLAIN` output.

## 31. Post-upgrade `ANALYZE` and planner statistics

After upgrading, run `ANALYZE` so the planner has appropriate statistics for the target major version and current data distribution.

A commonly used tool:

```bash
vacuumdb --all --analyze-in-stages
```

Verify options and workflow according to target version, database size, and maintenance window.

### 31.1. Analyze in stages

The tool can gather statistics in stages so the planner gets basic information sooner while completing full statistics.

### 31.2. Statistics targets

Some columns with special skew/cardinality need custom statistics targets or extended statistics. Reapply necessary configuration.

### 31.3. Do not run heavy full maintenance concurrently without planning

`ANALYZE`, vacuum, index rebuilds, and peak application traffic all consume resources. Schedule and monitor them.

### 31.4. Performance baseline

Compare latency, TPS, query plans, I/O, CPU, and temp spills before/after. Do not conclude the upgrade succeeded just because the server started.

## 32. Planner and performance regression

A major upgrade can change planner estimates, cost models, and execution strategies. Some queries get faster; some queries get slower.

### 32.1. Query corpus

Collect top queries from `pg_stat_statements` and critical business operations. Run them on staging with similar data volume.

### 32.2. Compare plans

Save `EXPLAIN (ANALYZE, BUFFERS, SETTINGS)` before/after. Compare estimated/actual rows, join order, scans, sorts, hash batches, and parallelism.

### 32.3. Do not force global planner settings immediately

If a query regresses, investigate statistics/indexes/query rewrites first. Planner GUC overrides should only be used targetedly with an assigned owner.

### 32.4. SLO regression gate

Set p95/p99, error rate, and throughput thresholds for canary/cutover. If breached, trigger the mitigation/rollback decision.

## 33. Major upgrade with logical replication: sequences and DDL

Logical replication supports row changes per publication. It does not automatically replace schema deployment or sequence synchronization.

### 33.1. Schema-first

Create a compatible target schema before copying/applying. DDL must be deployed on both sides in a safe order.

### 33.2. DDL freeze

During the migration window, restrict schema changes or have a process to apply them simultaneously to the target. Out-of-sync DDL can cause the apply worker to fail.

### 33.3. Sequence freeze

Before cutover, stop writes, determine final source sequence state, and update the target. Watch for concurrent sessions/sequence caches.

### 33.4. Non-table objects

Roles, grants, functions, procedures, extensions, large objects, and configuration must be handled separately per the replication/migration scope.

## 34. CDC and logical replication slots

If downstream systems read WAL/logical decoding, a major upgrade can affect slots, plugins, and offsets.

### 34.1. Inventory consumers

List consumer name, slot, plugin, `restart_lsn`, `confirmed_flush_lsn`, and owner.

```sql
SELECT
    slot_name,
    slot_type,
    plugin,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

Some columns depend on version/slot type.

### 34.2. Slots are not just metadata

Slots can retain WAL or catalog state. Losing a slot may require consumer resnapshot/resync.

### 34.3. Plugin compatibility

Logical decoding plugins must have a build compatible with the target major version and appropriate protocol/behavior.

### 34.4. Consumer offset coordination

Align the target cluster with consumer offsets according to the migration plan. Avoid letting old and new clusters emit the same stream and cause duplicate side effects if the consumer does not deduplicate.

## 35. Managed PostgreSQL upgrades

Managed database providers usually have dedicated workflows for minor patching and major upgrades.

Check:
- Supported source/target versions.
- Maintenance window.
- Backup/snapshot behavior.
- Failover/replica upgrade order.
- Extension availability.
- Parameter group changes.
- Endpoint behavior.
- Downtime estimates.
- Rollback/restore options.
- Cross-region replicas/read replicas.
- CDC/replication integrations.

### 35.1. Provider-managed does not mean validation-free

The provider may handle infrastructure/cluster conversion, but application, SQL, extension, and business validation remain your system's responsibility.

### 35.2. Read replicas

Verify how the provider upgrades/rebuilds read replicas. Endpoints may change or replicas may need to be recreated.

### 35.3. Parameter groups

An old major parameter group may not apply to a new major version. Compare and create a target parameter set.

### 35.4. Restore paths

Snapshot restores across different major versions may have limitations. Read provider documentation and test restore/cutover.

## 36. PostgreSQL in containers/Kubernetes

Container image version and data directory version are two separate things.

### 36.1. Pin image tags

Avoid floating tags in production. Pin major/minor tags or immutable image digests per your release process.

### 36.2. Volume persistence

Changing the image from major 16 to 17 does not automatically convert the data volume. The entrypoint may reject the old data directory or cause undesired behavior.

### 36.3. StatefulSet rollouts

A rolling pod restart is not a major upgrade. Physical replicas require the same major data format and proper orchestration.

### 36.4. Volume backup/restore

Snapshot volumes before maintenance and test restores. Storage snapshots do not replace logical validation or an application cutover plan.

## 37. OS packages and multiple PostgreSQL versions

A host can have multiple major binaries installed side by side. A package manager can update binary packages without automatically converting a data cluster.

### 37.1. Binary paths

Check `which postgres`, `pg_config --bindir`, the service unit, and the actual executable. `PATH` may point to a different client/tool version.

### 37.2. Cluster manager

Some distributions have a cluster manager handling multiple clusters/ports. Use the distribution's official commands; do not assume `systemctl restart postgresql` controls the right cluster.

### 37.3. Service identity

Ensure the service runs with the right user, data directory, and config file. Do not change owners/permissions arbitrarily.

### 37.4. Package repository

Use a trusted package source, verify signing keys, and check security updates. Record package versions for auditing.

## 38. Security and compliance during upgrades

Major/minor updates may contain security fixes or change cryptographic/authentication behavior.

Check:
- Security advisories.
- CVEs and fixed versions.
- TLS protocols/ciphers/certificates.
- Password authentication methods.
- `pg_hba.conf` rules.
- Role privileges.
- Extension security updates.
- Audit logging.
- Backup encryption.
- Secret rotation.
- Network access/firewall rules.

### 38.1. Do not update only the server package

Client drivers, extension libraries, backup tools, and monitoring agents may also have vulnerabilities or compatibility requirements.

### 38.2. Least privilege

Review roles after migration. Do not grant superuser to an application just to work around a permission mismatch.

### 38.3. Data handling

Dump files may contain all production data. Encrypt them, restrict access, and delete them per retention policy.

### 38.4. Change evidence

Save versions, package checksums, backup IDs, approvals, commands, timestamps, and validation outcomes.

## 39. Preflight checklist

Before starting:

- [ ] Identify exact source/target major/minor versions.
- [ ] Read release notes and upgrade documentation.
- [ ] Confirm a supported upgrade path.
- [ ] Inventory databases, sizes, roles, tablespaces, and collations.
- [ ] Inventory extensions and target binaries.
- [ ] Verify driver, ORM, pooler, and application compatibility.
- [ ] Check physical/logical replicas, slots, and CDC consumers.
- [ ] Verify backups, WAL archiving, and restore tests.
- [ ] Rehearse on a production-sized copy.
- [ ] Run `pg_upgrade --check` if using `pg_upgrade`.
- [ ] Confirm disk, temp, and rollback capacity.
- [ ] Review target configuration/parameter groups.
- [ ] Set the downtime window and communication plan.
- [ ] Document owner, stop conditions, and rollback decision maker.
- [ ] Prepare validation queries and smoke tests.

## 40. Cutover checklist

During the upgrade window:

1. Freeze schema changes and announce maintenance.
2. Stop/queue writes per migration strategy.
3. Drain application pools, jobs, and external writers.
4. Verify the source has no unplanned writes.
5. Record final LSN/backup/snapshot identifiers.
6. Perform `pg_upgrade`, restore, or logical cutover.
7. Start the target and check logs.
8. Verify roles/version/database connectivity.
9. Verify extensions, indexes, constraints, and sequences.
10. Run `ANALYZE` per plan.
11. Verify replication/CDC/backups.
12. Run smoke tests and critical transactions.
13. Switch application traffic.
14. Monitor latency, errors, throughput, and resource headroom.
15. Retain the old cluster/backup during the rollback window.

## 41. Post-upgrade validation

### 41.1. Server identity and version

```sql
SELECT version();
SHOW server_version;
SHOW server_version_num;
SELECT pg_is_in_recovery();
```

### 41.2. Database accessibility

Connect to each required database; check owners, grants, schemas, tablespaces, and critical queries.

### 41.3. Extensions

Compare the extension inventory against the target compatibility plan. Test extension functions and background workers.

### 41.4. Indexes/constraints

Check invalid indexes, constraint validation, collation-dependent indexes, and application query plans.

### 41.5. Sequences

Check sequence state and generated IDs, especially after dump/restore or logical migration.

### 41.6. Jobs and external integrations

Verify cron/schedulers, backups, monitoring, CDC, ETL, queue consumers, notifications, and reporting.

### 41.7. Application smoke tests

Execute create/read/update/delete against test data, login/authentication, transaction rollback, prepared statements, and critical business flows.

## 42. Performance validation

Compare old/new baselines:
- p50/p95/p99 query/API latency.
- TPS and business throughput.
- Error/timeout/deadlock rates.
- CPU, memory, swap, and disk I/O.
- Connection pool acquire wait.
- Top query plans/durations.
- Temp files and blocks.
- Checkpoint/WAL rate.
- Autovacuum progress and XID age.
- Replication lag/freshness.
- Backup/archive completion.

### 42.1. Warm-up

The new target has a different cache state. Distinguish cold-cache startup effects from steady-state regressions.

### 42.2. Query plans

A query changing plans after an upgrade may need `ANALYZE` or query-specific optimization. Do not immediately revert the entire major upgrade if only one query regresses.

### 42.3. Representative workload

Run peak/batch/reporting workloads under controlled conditions. A smoke test with a few queries is insufficient.

### 42.4. SLO gate

Set criteria to continue traffic, throttle traffic, or roll back based on metrics and business impact.

## 43. Disaster recovery and PITR after upgrading

After upgrading, update the backup system to create base backups compatible with the target major version and archive the target cluster's WAL.

### 43.1. Back up the new target

Do not rely indefinitely on old-major backups. Take a new backup once the target is verified.

### 43.2. Target restore test

Test restoring the target's backup into an isolated environment and verify application connectivity.

### 43.3. WAL archive path

Verify archive command, credentials, object storage permissions, retention, and monitoring on the target.

### 43.4. Recovery documentation

Update runbooks: binary path, data directory, service name, version, extension packages, replication topology, and PITR instructions.

## 44. Common failure modes

- Starting a new major binary directly on an old data directory.
- Choosing wrong source/target paths in `pg_upgrade`.
- Running `pg_upgrade` for the first time during the maintenance window.
- Missing extension shared libraries on the target.
- Skipping extension SQL updates.
- Using an incompatible `pg_dump`/`pg_restore` version.
- Forgetting roles/global objects/tablespaces.
- Not synchronizing sequences before logical cutover.
- Not handling collation version changes.
- Not rebuilding physical standbys.
- Overlooking logical slots/CDC consumers.
- Copying old config verbatim to the target.
- Skipping `ANALYZE` after upgrading.
- Deleting the old cluster before the rollback window ends.
- Reverting to the old cluster after the target received writes without reconciling.
- Not testing drivers, poolers, and authentication.
- Not checking invalid indexes.
- Confirming only that the server starts without testing business transactions.
- Failing to update backup/PITR and monitoring.
- Failing to store change evidence.

## 45. Example method selection

### Scenario A: small cluster, a few hours of downtime acceptable

Dump/restore can fit if extensions and global objects are supported. Rehearse dump/restore duration and validate ownership.

### Scenario B: large cluster, short downtime

`pg_upgrade` can fit if the source/target path is supported and extension binaries are available. Rehearse with a copy to measure conversion time.

### Scenario C: workload requiring a short cutover

Logical replication/blue-green can fit if the application allows schema compatibility, sequence synchronization, and a brief write freeze. Design DDL and CDC beforehand.

### Scenario D: managed database

Use the provider-supported major upgrade workflow; read limitations regarding extensions, replicas, parameter groups, snapshots, and endpoints. Test on staging.

### Scenario E: source major version is too old

Verify the `pg_upgrade` path. An intermediate major upgrade or dump/restore may be required. Do not arbitrarily bypass version constraints.

## 46. Practice exercises with answers

### Exercise 1. What is a minor update?

**Answer:** An update within the same major version line, typically containing bug fixes and security fixes, keeping the data format compatible within that major line.

### Exercise 2. What is a major upgrade?

**Answer:** Moving a cluster to a new major version, which may require converting the data directory/catalog format and verifying compatibility.

### Exercise 3. What kind of change is 16.2 to 16.3?

**Answer:** Minor update.

### Exercise 4. What kind of change is 16 to 17?

**Answer:** Major upgrade.

### Exercise 5. How is PostgreSQL 9.6.24 read?

**Answer:** The major line is 9.6; 24 is the minor release within that line.

### Exercise 6. Does a minor update normally require `pg_upgrade`?

**Answer:** No. It is designed to use the same major data directory format.

### Exercise 7. Does a minor update require a server restart?

**Answer:** Usually yes, so the process uses the new binaries; downtime depends on the HA/provider workflow.

### Exercise 8. Can a PostgreSQL 16 data directory be opened directly with a PostgreSQL 17 binary?

**Answer:** No. A supported major upgrade procedure must be used.

### Exercise 9. What does `pg_upgrade` do?

**Answer:** Converts cluster files/catalogs from an old major version to a new major version along a supported upgrade path.

### Exercise 10. What does `pg_upgrade --check` do?

**Answer:** Checks prerequisites/compatibility without performing the final conversion.

### Exercise 11. What is the advantage of `pg_upgrade` copy mode?

**Answer:** Old data files remain independent from the new cluster, which is more convenient for storage rollback; the trade-off is disk space and time.

### Exercise 12. What is the risk of link mode?

**Answer:** Old and new clusters hard-link shared files; once the new cluster begins writing, the old cluster is no longer safe to run.

### Exercise 13. What does clone mode require?

**Answer:** A filesystem/platform supporting reflink/clone and a `pg_upgrade` version that supports that mode.

### Exercise 14. What can dump/restore transfer?

**Answer:** Logical schema/data and object definitions within the dump/restore scope; global objects need separate handling.

### Exercise 15. Are roles/tablespaces automatically complete in a `pg_dump` database dump?

**Answer:** No. Inventory and dump/restore global objects separately when needed.

### Exercise 16. What format does `pg_dump -Fc` create?

**Answer:** Custom archive format, usable with `pg_restore` and parallel restore.

### Exercise 17. Why must `pg_dump` version be checked?

**Answer:** Tool versions have compatibility rules; `pg_dump` does not support dumping a server newer than its own major version.

### Exercise 18. Does logical replication replicate DDL automatically?

**Answer:** No. Schema changes require separate migration.

### Exercise 19. Does logical replication automatically synchronize sequence state?

**Answer:** Not in a way that guarantees next values; a sequence cutover procedure is required.

### Exercise 20. Why can blue-green reduce downtime?

**Answer:** Green is prepared/caught up while blue continues serving, cutting over only after freezing writes and finishing synchronization.

### Exercise 21. Should you arbitrarily dual-write to blue and green?

**Answer:** No. It can cause divergence/order conflicts; a single source of truth or a designed protocol is needed.

### Exercise 22. Do extension binaries need to be compatible with the new major version?

**Answer:** Yes. Shared libraries generally need a build/package matching the target major version.

### Exercise 23. What is `ALTER EXTENSION UPDATE` used for?

**Answer:** Running the extension SQL update path when the corresponding version script is available.

### Exercise 24. Does installing an extension package automatically update SQL objects?

**Answer:** Not necessarily. Binary packages and SQL extension versions are two separate things to verify.

### Exercise 25. What might a collation version change require?

**Answer:** Identifying/rebuilding indexes that depend on the collation according to documentation.

### Exercise 26. Why should old `postgresql.conf` not be copied verbatim?

**Answer:** Some parameters may be renamed, removed, have changed defaults, or no longer fit the target major version.

### Exercise 27. What does `pg_settings.pending_restart` indicate?

**Answer:** The setting has been changed but requires a restart to take effect.

### Exercise 28. Can an old-major physical standby continue serving as a standby for a new-major primary?

**Answer:** No, not under standard physical streaming replication; it must be rebuilt/rejoined from the new major cluster.

### Exercise 29. Should replication slots be assumed to persist across an upgrade?

**Answer:** No. Inventory and verify behavior by version/method; downstream consumers may require resyncing.

### Exercise 30. Why check CDC consumers?

**Answer:** Slots/plugins/protocols/offsets may change or require a snapshot/resync after a major upgrade.

### Exercise 31. Does the existence of a backup file prove it can be restored?

**Answer:** No. A restore test and validation are required.

### Exercise 32. Why keep the old cluster after a major upgrade?

**Answer:** As a rollback/recovery source for a defined window, though writes occurring on the target must be handled.

### Exercise 33. Can you roll back simply by switching the endpoint back to the old cluster after the target has accepted writes?

**Answer:** Not safely without reverse replication/reconciliation; new writes may be lost.

### Exercise 34. Why is link mode unsuitable if you want an independent old cluster?

**Answer:** Files use hard links; new cluster writes can render the old cluster unusable.

### Exercise 35. Why run `ANALYZE` after `pg_upgrade`?

**Answer:** The planner needs accurate statistics to choose good plans; old statistics should not be assumed complete.

### Exercise 36. How can `pg_stat_statements` help after an upgrade?

**Answer:** Comparing query calls, total/mean execution time, and temp activity to detect regressions.

### Exercise 37. Why test query plans?

**Answer:** The planner/executor may choose different plans across major versions.

### Exercise 38. What does `indisvalid = false` on an index mean?

**Answer:** The index is not considered valid for normal planner usage; it needs investigation/rebuilding per the runbook.

### Exercise 39. Which methods require special attention to sequence state?

**Answer:** Dump/restore and logical replication migration; `pg_upgrade` also needs validation but normally handles sequence data during cluster conversion.

### Exercise 40. Does a managed provider upgrade eliminate validation responsibility?

**Answer:** No. Application, extension, SQL, performance, and business validation still must be performed.

### Exercise 41. Does a new major container image automatically upgrade a persistent volume?

**Answer:** No. Image binaries and data directory versions are separate.

### Exercise 42. Why rehearse on a production-sized copy?

**Answer:** To measure duration, disk usage, extension issues, plan behavior, and validation with realistic data volumes.

### Exercise 43. How much downtime does a major upgrade require?

**Answer:** It depends on method, size, network, index builds, extensions, and cutover plan; it must be measured via rehearsal.

### Exercise 44. Why test drivers/ORMs?

**Answer:** Client protocols, auth, generated SQL, prepared statements, and type handling can be affected.

### Exercise 45. When is an intermediate major upgrade needed?

**Answer:** When `pg_upgrade` does not support a direct source-to-target path or release documentation requires an intermediate step.

### Exercise 46. Does logical replication replace backups/PITR?

**Answer:** No. It is a migration/replication mechanism, not a substitute for a backup and restore strategy.

### Exercise 47. Does a minor update require reading release notes?

**Answer:** Yes. Bug/security fixes and behavior changes can affect workloads.

### Exercise 48. What should be checked after cutover?

**Answer:** Version/role, extensions, indexes/constraints, sequences, application smoke tests, performance, replication, backups, and logs.

### Exercise 49. When should the old cluster be cleaned up?

**Answer:** Only after validation, the rollback window, backups, and retention policy allow it.

### Exercise 50. What are the completion criteria for a major upgrade?

**Answer:** Target cluster is stable, application/business tests pass, performance/SLOs are met, HA/backups/CDC operate properly, the recovery plan is verified, and the old cluster is cleaned up per policy.

## 47. Post-upgrade checklist and closing the change

| Group | Verification |
|---|---|
| Version | Is the server version on the right target across all nodes? |
| Role | Are primary/standby/managed endpoints matching the topology? |
| Data | Are databases, schemas, owners, and tablespaces intact? |
| Extensions | Are binary and SQL extension versions compatible? |
| Collation | Have version mismatches been handled and necessary indexes reindexed? |
| Indexes | Are there no unplanned invalid indexes? |
| Constraints | Are FK/unique/check constraints valid? |
| Sequences | Are next generated values safe? |
| Config | Have parameters been reviewed, with no deprecated/unknown settings? |
| Application | Do drivers, ORMs, auth, pools, and smoke tests pass? |
| Performance | Do query plans, p95/p99, TPS, and resource headroom meet targets? |
| HA | Have standbys been rebuilt/rejoined and is replication healthy? |
| CDC | Have slots, plugins, and consumers caught up? |
| Backup | Has a new base backup/PITR run? |
| Restore | Did the target restore test pass? |
| Jobs | Are schedulers, ETL, backup, and maintenance jobs running? |
| Security | Are TLS, roles, secrets, and auditing configured properly? |
| Rollback | Are the rollback window and data reconciliation finalized? |
| Cleanup | Is the old cluster deleted only per policy? |
| Evidence | Are change logs, versions, backup IDs, and validation results saved? |

## 48. Official PostgreSQL documentation

- [Release Versioning Policy](https://www.postgresql.org/support/versioning/) — major/minor releases and support lifecycle.
- [PostgreSQL Release Notes](https://www.postgresql.org/docs/release/) — changes, bug fixes, and security fixes per release.
- [pg_upgrade](https://www.postgresql.org/docs/current/pgupgrade.html) — upgrading clusters across major versions.
- [Upgrading a PostgreSQL Cluster](https://www.postgresql.org/docs/current/upgrading.html) — upgrade methods.
- [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html) — logical dump.
- [pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html) — archive restore and parallel jobs.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — publisher/subscriber and restrictions.
- [Logical Replication Restrictions](https://www.postgresql.org/docs/current/logical-replication-restrictions.html) — DDL, sequences, and limitations.
- [ALTER EXTENSION](https://www.postgresql.org/docs/current/sql-alterextension.html) — extension updates.
- [Collation Support](https://www.postgresql.org/docs/current/collation.html) — collation behavior/versioning.
- [Backup and Restore](https://www.postgresql.org/docs/current/backup.html) — backups, PITR, and recovery.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — replication and database health.

Always open documentation matching your exact source/target major versions rather than reading only `current`. Extension vendors and managed service providers may have their own compatibility/upgrade procedures.

## 49. Summary: choosing a method based on compatibility and recovery

```text
Identify current version and target
             |
             v
       Same major line?
         /       \
       Yes        No
        |          |
        v          v
   Minor update  Major upgrade
        |          |
        v          v
  Backup +       Choose method
  release notes     |
  package/restart   +-- pg_upgrade
  verify            +-- dump/restore
                    +-- logical replication
                    +-- managed workflow
                         |
                         v
                Preflight + rehearsal
                         |
                         v
                 Cutover + validation
                         |
                         v
             Backup/HA/CDC + rollback window
                         |
                         v
                  Close change safely
```

Key principles to remember:

1. **Minor updates preserve the same major data format.** Typically replace binaries/packages and restart, without needing `pg_upgrade`.
2. **A major upgrade is a cluster conversion.** Do not open an old data directory directly with a new major binary.
3. **Read release notes and verify the upgrade path.** Do not assume you can jump directly from any source major version.
4. **Choose `pg_upgrade`, dump/restore, or logical migration based on downtime and compatibility.**
5. **`pg_upgrade --check` must be run before the maintenance window.** Rehearse on a production-sized copy.
6. **Copy, link, and clone have different trade-offs.** Link mode does not keep the old cluster safe once the new cluster writes.
7. **Extension binaries and SQL versions must be compatible.** Install packages and run extension updates per documentation.
8. **Collations, sequences, DDL, and global objects need separate validation.** Especially with logical migration.
9. **Physical standbys must be rebuilt/rejoined for the new major version.** Do not assume an old-major standby continues streaming.
10. **Backup/restore testing is the foundation of rollback.** Keeping the old cluster does not resolve writes occurring after cutover.
11. **Post-upgrade `ANALYZE` and performance tests are crucial.** Query plans can change.
12. **Only close the change when HA, CDC, backups, applications, and business flows are all verified.**

**One sentence to remember:** *A minor update applies bug fixes within the same major line; a major upgrade converts the entire cluster to a new major line, so you must choose a migration method, prepare extensions/replication, test applications, and define rollback before cutover.*
