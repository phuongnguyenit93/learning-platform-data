# Upgrading PostgreSQL Using Dump and Restore

## 1. Method overview

Upgrading PostgreSQL via dump and restore is a method for transferring logical data from a source cluster to a target cluster. Instead of copying data files directly, the tools read schemas and data via SQL/logical representation, write them into an archive or script, and then recreate objects and rows on the new server.

Typical workflow:

1. Inventory the source cluster, databases, roles, extensions, and tablespaces.
2. Install the target PostgreSQL version and compatible extension packages.
3. Create backups using `pg_dump` or `pg_dumpall`.
4. Create roles, tablespaces, and databases on the target cluster.
5. Restore schemas/data using `pg_restore` or `psql`.
6. Run `ANALYZE` and verify data, sequences, permissions, and applications.
7. Cut over applications to the new cluster per the cutover plan.
8. Retain the old cluster and backups per the rollback/retention policy.

This method is typically suitable when changing major versions, switching operating systems/architectures, changing storage layouts, or wanting to rebuild a clean database. It is also useful when migrating a specific database rather than an entire cluster.

Dump/restore usually requires significant downtime for large databases because data must be exported and imported. If very low downtime is required, you may need to combine it with logical replication or another migration method to sync changes while dumping/restoring a baseline.

### 1.1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish `pg_dump`, `pg_dumpall`, `pg_restore`, and `psql`.
2. Choose between plain, custom, directory, or tar archives appropriately.
3. Plan dump/restore across PostgreSQL major versions.
4. Back up and restore roles, tablespaces, and global objects.
5. Handle extensions, large objects, sequences, ownership, and privileges.
6. Choose between sequential and parallel restore.
7. Understand consistency snapshots and limitations while a database continues receiving writes.
8. Plan the cutover window, validation, and rollback.
9. Protect dump files and credentials.
10. Practice the migration in a lab environment.

### 1.2. When to use dump/restore?

Suitable when:
- Upgrading major versions and wanting to create a fresh cluster.
- Migrating across operating systems or CPU architectures.
- Moving a database to new storage/hosts.
- Changing encoding, locale, or collation in a controlled migration.
- Migrating a specific subset of databases/schemas/tables.
- Dump, restore, and validation durations are acceptable.

Consider alternative methods when:
- The database is very large and downtime must be minimal.
- There is a continuous write workload where writes cannot be frozen long enough.
- There are many large objects or external dependencies requiring separate procedures.
- Difficult custom types/extensions pose compatibility challenges.
- A full-cluster upgrade with short downtime is required and `pg_upgrade` is a better fit.

### 1.3. Dump/restore is a logical migration

A dump contains commands to recreate objects and data in logical form. It is not a byte-for-byte copy of the data directory, nor is it a WAL archive.

Advantages:
- Does not depend directly on the source version's data file layout.
- Can restore into a newer PostgreSQL major version per compatibility rules.
- Can select specific databases/schemas/tables/objects to migrate.
- Can alter certain attributes during restore, such as owner or ACLs.
- Can run parallel restores with suitable archive formats.

Limitations:
- Export/import can be slower than physical copying.
- Does not automatically synchronize changes occurring after the snapshot.
- Does not automatically copy external resources, secrets, OS files, or cluster configuration.
- Requires handling global objects and dependencies outside the database.
- The restore must be compatible with SQL/features/extensions on the target server.

---

## 2. Tools and roles

### 2.1. `pg_dump`

`pg_dump` creates a dump of a single database. It can output:
- Plain SQL script.
- Custom archive.
- Directory archive.
- Tar archive.

A database dump contains supported database objects and data. It does not replace backing up roles, tablespaces, and cluster-wide global objects.

Plain SQL example:

~~~bash
pg_dump -h source-db -U backup_user -d appdb -F p > appdb.sql
~~~

Custom archive example:

~~~bash
pg_dump -h source-db -U backup_user -d appdb -F c -f appdb.dump
~~~

### 2.2. `pg_dumpall`

`pg_dumpall` dumps all databases in a cluster plus global objects such as roles and tablespaces. The output is a plain SQL script, usually executed with `psql`.

Example dumping globals only:

~~~bash
pg_dumpall -h source-db -U postgres --globals-only > globals.sql
~~~

Example dumping the entire cluster:

~~~bash
pg_dumpall -h source-db -U postgres > cluster.sql
~~~

For large databases needing parallel dump/restore, it is usually more convenient to run `pg_dump` per database in custom/directory format and use `pg_dumpall --globals-only` for globals.

### 2.3. `pg_restore`

`pg_restore` reads archives created by `pg_dump` in custom, directory, or tar format. It allows you to:
- Select schemas/data/tables/objects to restore.
- List archive contents.
- Restore in dependency order.
- Run multiple parallel jobs with custom/directory archives.
- Omit owners or ACLs.
- Clean old objects before restoring if requested.

Example:

~~~bash
pg_restore -h target-db -U restore_user -d appdb_new appdb.dump
~~~

### 2.4. `psql`

`psql` executes plain SQL dumps:

~~~bash
psql -X -h target-db -U restore_user -d appdb_new \
  -v ON_ERROR_STOP=1 -f appdb.sql
~~~

`-X` prevents `psql` from reading personal startup files, making restores more reproducible. `ON_ERROR_STOP=1` makes `psql` stop upon SQL errors instead of continuing as if nothing happened.

Plain SQL restores cannot use `pg_restore`'s parallel restore mechanism.

### 2.5. Related tools

- `createdb`: creates the target database.
- `dropdb`: drops a database; use with caution as it is destructive.
- `vacuumdb`: runs `VACUUM`/`ANALYZE` on databases.
- `pg_isready`: checks whether the server accepts connections.
- `pg_restore --list`: views the TOC (table of contents) inside an archive.
- `pg_verifybackup`: verifies physical backup manifests; not used to verify `pg_dump` archives.
- `pg_dump --version` / `pg_restore --version`: checks client tool versions.

---

## 3. Choosing a dump format

### 3.1. Plain SQL format

Plain format is a human-readable SQL script, restored via `psql`.

~~~bash
pg_dump -F p -f appdb.sql appdb
~~~

Advantages:
- Easy to read and inspect.
- Can edit the script if consequences are well understood.
- Easy to integrate into SQL-client-only workflows.
- Does not require `pg_restore`.

Disadvantages:
- Does not support parallel restore.
- Cannot selectively pick objects as flexibly as a custom archive.
- Files can be large and require ample disk space.
- Manual script edits can break dependencies or data.

Use when the database is small, a readable script is needed, or the restore pipeline is simple.

### 3.2. Custom format

Custom format uses `-F c` or `--format=custom`:

~~~bash
pg_dump -Fc -f appdb.dump appdb
~~~

Advantages:
- Compressed archive.
- Can list objects.
- Selective schema/data/table restore.
- Supports parallel restore via `pg_restore -j`.
- Ideal for backing up an individual database.

Disadvantages:
- Not directly human-readable like an SQL script.
- Requires `pg_restore`.
- Does not support parallel dump via `pg_dump`; parallel dump requires directory format.

This is typically the most versatile choice for an individual database.

### 3.3. Directory format

Directory format creates an archive directory containing multiple files:

~~~bash
pg_dump -Fd -j 4 -f appdb_dir appdb
~~~

Advantages:
- Supports parallel dump via `pg_dump -j`.
- Supports parallel restore via `pg_restore -j`.
- Each table/data object can be stored in its own file.
- Suitable for large databases and migrations needing high throughput.

Disadvantages:
- Must preserve the entire directory, not just a single file.
- Copying/uploading must keep all files and permissions intact.
- Managing multi-file artifacts is more complex than a single custom archive.

### 3.4. Tar format

Tar format uses `-F t`:

~~~bash
pg_dump -Ft -f appdb.tar appdb
~~~

It produces a tar-based archive usable with `pg_restore` and selective object restoration, but does not support parallel restore like custom/directory formats. Check compatibility and format limitations in release documentation.

### 3.5. Comparison

| Format | Output | Parallel dump | Parallel restore | Restore tool |
|---|---|---:|---:|---|
| Plain | SQL script | No | No | `psql` |
| Custom | Single archive file | No | Yes | `pg_restore` |
| Directory | Multi-file directory | Yes | Yes | `pg_restore` |
| Tar | Single tar archive | No | No | `pg_restore` |

### 3.6. Choosing a format by goal

- Need readable/editable SQL: plain.
- Need a single compressed file with selective restore: custom.
- Need parallel dump and parallel restore: directory.
- Need a tar-compatible archive: tar.
- Need to dump multiple databases plus globals: `pg_dumpall`, noting the output is an SQL script without the parallel restore of a directory archive.

### 3.7. Listing an archive before restoring

~~~bash
pg_restore --list appdb.dump > appdb.toc
~~~

The TOC shows objects in the archive and is helpful for review. You can edit the TOC and pass it via `--use-list`, though only do so when you understand dependencies; omitting the wrong object can cause restore failures or missing data.

---

## 4. Version compatibility and major version upgrades

### 4.1. Using the right client tools

To dump from a source server, use an appropriately versioned `pg_dump`. `pg_dump` cannot dump from a server whose major version is newer than its own; it generally supports servers of the same or older major versions within documented ranges.

To upgrade to a new major version, the standard practice is:
- Use the `pg_dump` client from the target version (or a client new enough to read the source server).
- Use `pg_restore`/`psql` compatible with the target server.
- Verify output SQL and extension compatibility.

Do not assume an old client version can read a newer server.

### 4.2. Dump format is not strictly version-neutral

An archive contains metadata and SQL generated by that `pg_dump` version. The target server must understand the emitted commands, types, functions, and options. PostgreSQL generally supports dumping/restoring into a newer server, though compatibility for all custom objects/extensions is not guaranteed.

Restoring from a newer version back to an older server is not a guaranteed downgrade path. If forced to downgrade, custom migration logic and per-feature testing are required.

### 4.3. Major upgrades

An upgrade workflow may move from PostgreSQL 14 to 15, 15 to 16, or other pairs. Numbers are examples only; check your exact version pair.

Differences may exist in:
- System catalogs.
- SQL syntax and reserved keywords.
- Data type behavior.
- Collation providers/versions.
- Extension versions.
- Planner/executor behavior.
- Authentication defaults.
- Replication features.
- Parameter names/defaults.
- Removed/deprecated features.

### 4.4. Client and server versions

Check:

~~~bash
pg_dump --version
pg_restore --version
psql --version
~~~

On source and target:

~~~sql
SELECT version();
SHOW server_version;
SHOW server_version_num;
~~~

Do not confuse `psql` client version with server version. Client and server are independent binaries/versions.

### 4.5. Extensions

A dump can contain `CREATE EXTENSION` or extension-owned objects as managed by PostgreSQL. However, it does not carry extension shared library binaries.

On the target:
1. Install extension packages compatible with the target major version and OS.
2. Check extension control/SQL files.
3. Identify the extension version on the source.
4. Install the matching version on the target.
5. Restore and verify `CREATE EXTENSION`/extension-owned objects.
6. Run `ALTER EXTENSION UPDATE` if required by the migration plan.
7. Test functions, operators, types, and indexes using the extension.

Do not copy `.so`/`.dll` files from an older major version into the new directory unless compatibility is confirmed by packaging.

### 4.6. Collation and locale

The target database needs encoding/locale/collation matching application requirements. Different libc/ICU versions can alter sorting/equality behavior and affect indexes. Before cutover:
- Record database encoding and locale.
- Check collation provider/version.
- Read warnings during restore.
- Determine reindex requirements.
- Test unique constraints and ordering logic.

### 4.7. Parameter changes

Do not copy the entire old `postgresql.conf` onto the new server. Some settings are renamed, have changed defaults, or are removed. Build a parameter inventory, compare target defaults, and configure deliberately. Check `pg_settings` and release notes.

### 4.8. SQL/feature compatibility

A restore may succeed while applications still fail because:
- Queries use changed syntax.
- An extension function no longer exists.
- New reserved keywords conflict.
- The planner chooses a different plan.
- Collation/sort results changed.
- Authentication/TLS defaults changed.

Therefore, run application smoke tests and workload regression tests after restoring.

---

## 5. Dump scope: database and cluster globals

### 5.1. `pg_dump` dumps only one database

`pg_dump` operates at the single-database level. It can dump an entire database or select specific schemas/tables/objects. It does not automatically back up cluster-wide roles, tablespaces, and global objects.

### 5.2. Global objects

Cluster-wide shared objects include:
- Roles and role memberships.
- Tablespaces.
- Certain cluster-level privileges/attributes.
- Global settings/metadata not owned by a single database.

Use:

~~~bash
pg_dumpall --globals-only -f globals.sql
~~~

Then restore globals before restoring databases so owners and tablespaces already exist.

### 5.3. Roles and passwords

A globals dump may contain role definitions and password verifiers if privileges/settings permit. This file is highly sensitive:
- Restrict file permissions.
- Encrypt at rest and in transit.
- Do not commit to source control.
- Do not paste into tickets/chat.
- Plan secret rotation and role ownership.
- Review `SUPERUSER`/`CREATEDB`/`CREATEROLE`/`REPLICATION` privileges.

If you do not want to carry password verifiers directly to the target, provision roles per policy and use `--no-owner`/ACL options as appropriate for database restore.

### 5.4. Tablespaces

If the source uses tablespaces, the globals dump may contain definitions with filesystem paths. The target needs:
- Directories created on the target host.
- Appropriate owner and permissions set.
- Verified mounts/storage.
- New paths chosen if the layout differs.
- Tablespaces created before restoring database objects that use them.

If you do not want to preserve tablespace mappings, use appropriate restore options such as `--no-tablespaces` or remap per plan; verify option support in your `pg_restore` version.

### 5.5. Cluster-wide `pg_dumpall`

`pg_dumpall` invokes `pg_dump` for each database and outputs globals in one SQL script. It is convenient for small clusters, but:
- Output is plain SQL, with no custom/directory archive.
- Restore is normally sequential.
- Harder to run parallel restores.
- Each database dump takes its own snapshot; it is not one cluster-wide snapshot across multiple databases.
- Requires reviewing global objects/roles/tablespaces and privileges.

For large clusters, dump globals separately and dump each database in custom/directory format.

### 5.6. Cross-database consistency

PostgreSQL transactions do not span multiple databases. When dumping multiple databases separately, each database gets a snapshot at its own dump start time. If applications enforce business invariants across databases, stop writes/quiesce or coordinate a consistent cutover boundary.

### 5.7. Replication objects

Dump/restore does not replace planning for replication slots, logical subscriptions, physical replication configuration, WAL archive settings, and external replication consumers. Some publication definitions are dumped as database objects; subscription/slot connection states and secrets need separate handling per version and runbook.

### 5.8. Out-of-scope objects

Inventory separately:
- `postgresql.conf`, `pg_hba.conf`, TLS certificates.
- OS users, filesystem paths, service units.
- Cron/jobs/schedulers.
- External tables/data sources, FDW endpoints.
- Secrets and credentials.
- Monitoring/backup agents.
- Replication slots and downstream consumers.
- Application connection strings/DNS/load balancers.

A database dump is not a backup of the entire infrastructure.

---

## 6. Consistency, snapshots, and downtime

### 6.1. `pg_dump` snapshots

`pg_dump` takes a consistent snapshot of a single database at the time the dump starts. While the dump runs, other transactions may continue committing; the dump sees an MVCC snapshot rather than randomly mixing rows from different points in time.

This guarantees internal consistency of the database dump, not that the dump contains writes committed after the snapshot began.

### 6.2. Writes during a dump

Suppose a dump starts at 10:00 and finishes at 11:30. A row committed at 10:45 after the snapshot will not appear in the dump. If the application keeps writing and the DBA restores only this archive, that row will be missing on the target.

Hence there are two main deployment approaches:

- **Offline migration:** stop writes before dumping and maintain the write freeze until restore/validation/cutover completes.
- **Online/low-downtime migration:** take a baseline dump and synchronize post-snapshot changes via logical replication or a designed, verified delta mechanism.

Never open the target as primary if post-snapshot writes have not been transferred.

### 6.3. Cutover boundary

For an offline migration:
1. Announce the maintenance window.
2. Block application writes and background jobs.
3. Wait for open transactions to finish.
4. Take the final dump.
5. Restore and validate.
6. Synchronize sequences and external state.
7. Switch connection routing.
8. Open writes on the target.

If dump/restore takes too long, downtime scales accordingly. Measure rehearsals on production-like data to estimate accurately.

### 6.4. Consistency across multiple databases

Each `pg_dump` has its own snapshot for its database. `pg_dumpall` does not create a single global transaction snapshot across all databases. If an application maintains logical relationships across multiple databases, stop writes system-wide or use a coordination marker/quiesce protocol.

### 6.5. Sequence values

Database dumps normally contain sequence definitions and sequence state exported via `setval` commands in the archive/script. When restored properly, sequence state is restored per the dump.

However:
- Sequence operations do not follow MVCC semantics like table rows.
- Writes continuing after the snapshot can advance sequence values with no corresponding row in the dump.
- If an application uses sequences outside the dumped database or shares a sequence across multiple tables, inventory them separately.
- Before opening writes on the target, confirm next values do not collide with restored keys.

### 6.6. Large objects

`pg_dump` supports large objects and generally includes them unless excluded by an option. When using table/schema-specific dumps or data-only selections, verify whether large objects are included and reference OIDs are preserved.

You can use `--blobs` to explicitly include large objects and `--no-large-objects` to exclude them. Verify options for your `pg_dump` version and test application LO reads on the target.

### 6.7. Consistency with external systems

Dumping does not freeze:
- Message queues.
- Object storage.
- Search indexes.
- Payment providers.
- Caches.
- External APIs.
- Filesystem uploads.

If database rows reference these systems, the cutover plan must synchronize event offsets, object paths, consumer checkpoints, and corresponding application state.

---

## 7. Preflight inventory before dumping

### 7.1. Confirm versions

On source and target, record:
- PostgreSQL major/minor version.
- `pg_dump`/`pg_restore`/`psql` client versions.
- OS/architecture.
- Database encoding.
- Locale and collation provider/version.
- Installed extensions and versions.

~~~sql
SELECT version();
SHOW server_version;
SHOW server_version_num;
SHOW server_encoding;
SHOW lc_collate;
SHOW lc_ctype;
~~~

Some collation details require inspecting catalogs and OS/provider metadata.

### 7.2. Inventory databases

~~~sql
SELECT
    datname,
    pg_get_userbyid(datdba) AS owner,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate,
    datctype,
    datallowconn,
    datistemplate
FROM pg_database
ORDER BY datname;
~~~

Identify databases to migrate and system databases that must not be dumped/restored as application databases.

### 7.3. Inventory roles

~~~sql
SELECT
    rolname,
    rolsuper,
    rolinherit,
    rolcreaterole,
    rolcreatedb,
    rolcanlogin,
    rolreplication,
    rolconnlimit,
    rolvaliduntil
FROM pg_roles
ORDER BY rolname;
~~~

Do not export password hashes into public documents. Check role memberships, default privileges, and in-database grants.

### 7.4. Inventory extensions

~~~sql
SELECT
    e.extname,
    e.extversion,
    n.nspname AS extension_schema
FROM pg_extension AS e
JOIN pg_namespace AS n
    ON n.oid = e.extnamespace
ORDER BY e.extname;
~~~

Check extension packages on the target before restoring. For extensions with native libraries, install packages matching the target PostgreSQL major version.

### 7.5. Inventory tablespaces

~~~sql
SELECT
    spcname,
    pg_get_userbyid(spcowner) AS owner,
    pg_tablespace_location(oid) AS location
FROM pg_tablespace
ORDER BY spcname;
~~~

Record paths, owners, and filesystem dependencies. Default tablespaces have empty locations; do not try to recreate `pg_default`/`pg_global` as user-defined tablespaces.

### 7.6. Inventory storage capacity

~~~sql
SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS database_size
FROM pg_database
WHERE datallowconn
ORDER BY pg_database_size(datname) DESC;
~~~

Estimate:
- Dump archive size.
- Target database size after restore.
- Temporary files.
- Index build overhead.
- WAL/archive growth.
- Disk headroom while source and target coexist.

Archive compression shrinks backup size, yet restoring still requires full disk space for database objects.

### 7.7. Inventory special objects

Look for:
- Large objects.
- Partitioned tables.
- Foreign tables/FDW servers.
- Publications/subscriptions.
- Event triggers.
- Custom types/domains/enums.
- Extensions.
- Materialized views.
- Security labels.
- Row-level security policies.
- Unlogged tables.
- Scheduled jobs and application-owned metadata.

Mark which objects dump/restore handles and which require separate migration.

### 7.8. Check active transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    clock_timestamp() - xact_start AS transaction_age,
    backend_xmin,
    query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Long-running transactions can affect snapshot horizons and complicate cutover. Identify owners and workloads before starting the maintenance window.

### 7.9. Preflight checklist

- [ ] Version pair and client tools confirmed.
- [ ] Compatible extension packages available on target.
- [ ] Roles/tablespaces inventoried.
- [ ] Encoding/locale/collation decided.
- [ ] Source, archive, target, and temp disk space budgeted.
- [ ] Plan in place for large objects and external dependencies.
- [ ] Application write freeze or delta sync strategy chosen.
- [ ] Backup encryption, retention, and access controls ready.
- [ ] Restore rehearsal completed.
- [ ] Validation queries and rollback owner identified.

---

## 8. Creating dumps with `pg_dump`

### 8.1. Custom format dump

~~~bash
pg_dump \
  -h source-db.example.net \
  -p 5432 \
  -U backup_user \
  -d appdb \
  --format=custom \
  --file=/backup/appdb.dump
~~~

Custom format works well when you want a single archive file, selective restore, and parallel restore.

### 8.2. Parallel directory format dump

~~~bash
pg_dump \
  -h source-db.example.net \
  -p 5432 \
  -U backup_user \
  -d appdb \
  --format=directory \
  --jobs=4 \
  --file=/backup/appdb_dir
~~~

Parallel dump is supported only with directory format. Size the job count based on source CPU, I/O, network, and connection capacity. Parallel dump uses snapshot coordination; it does not lock the entire source database throughout the process.

### 8.3. Plain SQL dump

~~~bash
pg_dump \
  -h source-db.example.net \
  -U backup_user \
  -d appdb \
  --format=plain \
  --file=/backup/appdb.sql
~~~

You can compress with an external tool afterward, though restore will require appropriate decompression/piping. If you need object selection or parallel restore, custom/directory formats are more convenient.

### 8.4. Dumping a single schema

~~~bash
pg_dump \
  -h source-db \
  -U backup_user \
  -d appdb \
  --schema=app \
  --format=custom \
  --file=app_schema.dump
~~~

Schema-only dumps are useful for preparing the target beforehand or reviewing DDL:

~~~bash
pg_dump --schema-only -Fc -d appdb -f schema.dump
~~~

### 8.5. Data-only dump

~~~bash
pg_dump --data-only -Fc -d appdb -f data.dump
~~~

A data-only dump does not create complete schema definitions. The target must already have the required tables, types, sequences, and constraints; otherwise, restore may fail.

### 8.6. Selecting tables

~~~bash
pg_dump -Fc -d appdb \
  --table=app.customers \
  --table=app.orders \
  -f selected_tables.dump
~~~

Selecting specific tables can omit dependencies such as types, functions, or referenced tables. Review the archive TOC and prepare the full target schema.

### 8.7. Excluding objects

You can exclude tables/schemas or data as needed. Be careful with:
- Excluding table data while keeping table definitions.
- Excluding a schema containing objects referenced by another schema.
- Excluding large objects.
- Excluding extension-owned objects.
- Excluding sequences used by tables.

Selective dumping is a migration plan, not merely file filtering.

### 8.8. Blobs/large objects

If the application uses large objects, confirm the archive includes them. Example:

~~~bash
pg_dump -Fc --blobs -d appdb -f appdb_with_blobs.dump
~~~

Do not use `--no-large-objects` if the target needs LOs. With table-specific/schema-specific dumps, verify exact behavior and test referential integrity.

### 8.9. Logging and exit codes

In automation:
- Capture stdout/stderr and exit codes.
- Use strict shell error handling appropriate for your environment.
- Do not treat archive file existence as a successful dump.
- Verify size, checksum, and `pg_restore --list`.
- Only mark the backup complete after the command exits 0 and the artifact is verified.

### 8.10. Dumping globals

~~~bash
pg_dumpall \
  -h source-db.example.net \
  -U cluster_backup \
  --globals-only \
  --file=/backup/globals.sql
~~~

Store the globals file alongside the database backup, encrypted with restricted access. Review role/tablespace definitions before restoring to the target.

### 8.11. Passwords and authentication

Never pass passwords directly on the command line as they can leak in process lists/history. Use:
- `.pgpass` with proper file permissions on Unix.
- Safely managed `PGPASSFILE`.
- Platform-specific secret manager/injected environment variables.
- TLS and certificate verification.

Never store connection strings containing passwords in shell history or public dump manifests.

### 8.12. Compression

Custom/directory formats can compress archives; supported compression levels and algorithms depend on `pg_dump` version. High compression saves network/storage at the cost of CPU and may slow dump/restore. Benchmark against actual CPU, I/O, and archive size.

---

## 9. Creating the target database and preparing globals

### 9.1. Creating the target cluster

Install the target PostgreSQL major version on the host/managed service. Before restoring:
- Confirm the server starts and accepts connections.
- Configure authentication, TLS, and `pg_hba`.
- Install extension packages.
- Create filesystem directories/tablespace paths.
- Configure disks, WAL, backups, and monitoring.
- Confirm the target has adequate RAM/CPU/I/O for restoring.

Never restore onto a production cluster already holding data without a clean/reconcile plan.

### 9.2. Restoring global objects first

Globals dumps generally require superuser or sufficiently high privileges to create roles/tablespaces:

~~~bash
psql -X \
  -h target-db \
  -U postgres \
  -d postgres \
  -v ON_ERROR_STOP=1 \
  -f /backup/globals.sql
~~~

If you do not want to carry source roles/passwords verbatim, create roles per the new policy and adjust restore options. Inspect the globals script before executing.

### 9.3. Tablespace directories

Create filesystem paths before restoring globals if the script contains `CREATE TABLESPACE`. Directories must exist on the target host with ownership/permissions matching the PostgreSQL server process.

Do not create tablespace paths on an unmounted or ephemeral mount; if restore succeeds and the mount later disappears, the database will be unable to access objects in that tablespace.

### 9.4. Handling role conflicts

If a role already exists on the target:
- Compare attributes/memberships.
- Decide whether to keep the target role or use the source definition.
- Avoid accidentally downgrading privileges or granting superuser.
- Handle ownership/default privileges.
- Only edit the globals script when you understand all references.

`pg_dumpall --globals-only` can produce duplicate role definitions. Do not run it blindly on a pre-provisioned target cluster.

### 9.5. Creating the database from `template0`

If custom encoding/locale/owner is needed, create the target database first:

~~~bash
createdb \
  -h target-db \
  -U postgres \
  --template=template0 \
  --owner=app_owner \
  --encoding=UTF8 \
  appdb_new
~~~

`template0` creates a clean database without inheriting local objects from `template1`. Configure locale/collation per requirements and options supported by client/server versions.

### 9.6. Checking the target database

~~~sql
SELECT
    datname,
    pg_get_userbyid(datdba) AS owner,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate,
    datctype
FROM pg_database
WHERE datname = 'appdb_new';
~~~

Ensure target encoding/locale are correct before restoring. Not every source locale exists on the target OS.

### 9.7. Role ownership and ACL strategy

Two common approaches:

**Preserve ownership/ACLs:** restore globals first, create roles and memberships identical to source, then restore the archive as-is.

**Apply new ownership/ACLs:** restore with `--no-owner` and `--no-acl`/`--no-privileges`, then run provisioning scripts to assign owners/grants. You can use `--role` to execute the restore under a chosen role if privileges allow.

Pick one consistent strategy. Avoid restoring with missing owners and patching objects manually one by one.

---

## 10. Restoring custom/directory archives with `pg_restore`

### 10.1. Basic restore

With the target database created and roles/schema prerequisites ready:

~~~bash
pg_restore \
  -h target-db.example.net \
  -p 5432 \
  -U restore_user \
  -d appdb_new \
  --verbose \
  /backup/appdb.dump
~~~

`pg_restore` reads the archive and creates objects/data following the dependency order in the archive TOC.

### 10.2. Parallel restore

~~~bash
pg_restore \
  -h target-db.example.net \
  -U restore_user \
  -d appdb_new \
  --jobs=4 \
  --verbose \
  /backup/appdb_dir
~~~

Parallel restore is supported for custom and directory archives. Tar/plain formats lack this capability. Increasing jobs can reduce elapsed time but increases:
- Concurrent connections.
- CPU and I/O.
- Index build memory.
- Lock activity.
- Temporary files.
- WAL generation and checkpoint pressure.

Start with a moderate job count, measure, and then scale up.

### 10.3. Restoring with new owner/ACLs

~~~bash
pg_restore \
  -h target-db \
  -U restore_admin \
  -d appdb_new \
  --no-owner \
  --no-acl \
  --verbose \
  appdb.dump
~~~

After restoring, run provisioning scripts to assign ownership, grants, and default privileges per target policy.

### 10.4. Running under a specific role

`--role=app_owner` instructs `pg_restore` to connect as a suitably privileged role and then issue `SET ROLE` to the selected role. Ensure the initial login role can `SET ROLE` and has sufficient privileges to create objects/data.

### 10.5. Restoring with create database

Use `--create` when you want `pg_restore` to create the database using the definition stored in the archive:

~~~bash
pg_restore \
  -h target-db \
  -U postgres \
  --create \
  -d postgres \
  appdb.dump
~~~

With `--create`, `-d` is the initial database to connect to, typically `postgres`. If you need a target database with custom encoding/locale/owner or want to control its name, create the database manually and restore without `--create`.

### 10.6. Cleaning existing objects

`--clean` tells `pg_restore` to drop objects before recreating them. `--if-exists` avoids errors when an object does not yet exist:

~~~bash
pg_restore \
  -h target-db \
  -U postgres \
  -d appdb_new \
  --clean \
  --if-exists \
  --exit-on-error \
  appdb.dump
~~~

This is destructive to existing objects. Never use it on a target holding data you need to keep. For large migrations, a fresh empty database is usually easier to control than cleaning objects individually.

### 10.7. Stopping on errors

`--exit-on-error` makes `pg_restore` halt on the first error. Without it, `pg_restore` may continue and report many errors, leaving the final database missing objects/data.

In production migrations, save complete logs and resolve all errors before cutover. Do not treat exit code 0 as sufficient if a wrapper hid errors or logs were truncated.

### 10.8. Single transaction

`--single-transaction` runs the entire restore inside one transaction; on error, changes roll back together. It is incompatible with parallel jobs (`-j`) and unsuitable for all archives/operations.

For large databases needing parallel restore, use a fresh target database and a failed-restore cleanup procedure instead of forcing everything into one transaction.

### 10.9. Restoring by sections

An archive has three main sections:
- `pre-data`: schema definitions and objects needed before data.
- `data`: table data, large objects, and sequence values from the archive.
- `post-data`: indexes, triggers, constraints, and post-data objects.

You can restore each section individually:

~~~bash
pg_restore --section=pre-data -d appdb_new appdb.dump
pg_restore --section=data -d appdb_new appdb.dump
pg_restore --section=post-data -d appdb_new appdb.dump
~~~

This technique helps customize index/constraint timing, but you must preserve dependency order and avoid re-running on targets that already contain objects.

### 10.10. Selective restore using a TOC

~~~bash
pg_restore --list appdb.dump > appdb.list
pg_restore --use-list=appdb.list -d appdb_new appdb.dump
~~~

You can comment out or remove TOC entries to skip specific objects. Understand dependencies, ownership, sequence/table relationships, and data completeness before omitting items.

### 10.11. Schema-only/data-only restore

~~~bash
pg_restore --schema-only -d appdb_new appdb.dump
pg_restore --data-only -d appdb_new appdb.dump
~~~

Use only when schema and data are intentionally separated. Data-only restore requires a compatible target schema and may require disabling/recreating constraints/indexes under a specific plan.

### 10.12. Restoring into an empty database

This is usually the easiest approach to control:
1. Create a new target database.
2. Restore globals/prerequisites.
3. Restore the archive.
4. Run validation.
5. Switch applications after passing the readiness gate.

If restore fails, preserve logs, investigate, and recreate a clean lab/target database per the runbook. Do not delete the old database before the migration is accepted.

---

## 11. Restoring plain SQL with `psql`

### 11.1. Basic restore

~~~bash
psql \
  -X \
  -h target-db \
  -U restore_user \
  -d appdb_new \
  -v ON_ERROR_STOP=1 \
  -f appdb.sql
~~~

Plain SQL dumps may include `CREATE` statements, `COPY`/`INSERT`, `ALTER OWNER`, and `GRANT` commands. The restore user must have the required privileges, or the script must be generated with an appropriate ownership/privileges strategy.

### 11.2. Restoring with logs

~~~bash
psql -X \
  -h target-db \
  -U restore_user \
  -d appdb_new \
  -v ON_ERROR_STOP=1 \
  -f appdb.sql \
  > restore.stdout.log 2> restore.stderr.log
~~~

Check both `psql`'s exit code and logs. In PowerShell/bash/CI, write wrappers that preserve exit codes rather than just checking whether log files exist.

### 11.3. Restoring via pipe

You can pipe compressed plain dumps into `psql`. Verify exit codes of both the decompressor and `psql`; a pipeline may return only the last command's exit code depending on shell configuration.

### 11.4. Plain SQL has no parallel restore

An SQL script has a sequential statement order executed serially by `psql`. For parallel restore, use custom/directory archives with `pg_restore -j`, or split the migration into independent parts with controlled dependencies.

### 11.5. Scripts may contain destructive commands

If the dump was created with clean options or custom SQL, the script may `DROP`/`CREATE` objects. Inspect headers and review contents before running on a target database containing existing data. Restore only into the confirmed target database.

---

## 12. Restore performance and resources

### 12.1. Parallel jobs

The optimal job count depends on:
- Source archive read throughput.
- Target CPU.
- Target storage IOPS/throughput.
- Network bandwidth.
- Index build workload.
- Memory budget and `maintenance_work_mem`.
- WAL/checkpoint configuration.
- Number/size of tables and indexes.

Adding more jobs does not guarantee faster restores; storage saturation can lower throughput.

### 12.2. `maintenance_work_mem`

Index creation during restore uses `maintenance_work_mem`. You can raise it for the restore session or a dedicated role if memory budget permits. Because `pg_restore -j` runs multiple jobs concurrently, account for parallel index builds plus autovacuum/query workloads.

### 12.3. `work_mem`

Restores are not typically heavy sort/hash query workloads, though maintenance scripts/triggers/functions may run SQL. Do not raise `work_mem` excessively just because a restore is slow; measure which operation consumes resources.

### 12.4. WAL and checkpoints

Bulk restores generate heavy WAL. Monitor:
- WAL generation rate.
- Checkpoint frequency/duration.
- Disk throughput.
- WAL archive backlog.
- Replication lag if the target already has downstream replicas.
- Free space on `pg_wal` and data volumes.

Adjust checkpoint/WAL settings temporarily only under a measured plan with backups and rollback. Never disable durability settings arbitrarily on a production target.

### 12.5. Indexes and constraints

Archive restores order objects by dependencies by default. For some migrations, you can restore `pre-data`/`data`/`post-data` separately so indexes build after data loads. Building indexes after loading data can be faster than maintaining indexes row by row, but requires disk headroom and validation.

### 12.6. Triggers and foreign keys

Triggers/constraints can increase restore cost or fail if the target schema differs. Do not use `--disable-triggers` as a default workaround; it requires high privileges and can leave constraint-violating data behind if not revalidated.

### 12.7. `ANALYZE` after restore

After restoring, planner statistics may not reflect the new data distribution. Run `ANALYZE` or the appropriate tool:

~~~bash
vacuumdb -h target-db -U maintenance_user \
  --analyze-in-stages appdb_new
~~~

`--analyze-in-stages` runs progressive analyze stages so the planner gets basic statistics quickly, which is helpful for newly restored databases. Verify option support in your `vacuumdb` version.

### 12.8. Restore progress

`pg_restore` offers verbose output, though not every command has a uniform progress view. Monitor:
- Active sessions and query text.
- `pg_stat_progress_create_index`.
- `pg_stat_progress_copy` where supported by version.
- CPU/memory/IO/network.
- Database size growth.
- WAL and checkpoint metrics.
- Restore job logs.

### 12.9. When to reduce jobs

Decrease parallel jobs when:
- Target storage latency spikes sharply.
- Host/container memory pressure rises.
- CPU saturates.
- WAL disk nears capacity.
- Competing application workloads suffer.
- Lock contention increases.
- Total throughput drops as jobs increase.

### 12.10. Restore rehearsal

Run at least one rehearsal on production-like data and configuration. Record:
- Dump duration.
- Transfer duration.
- Restore duration.
- Analyze duration.
- Validation duration.
- Peak RAM/CPU/IO.
- Archive size.
- Estimated cutover downtime.

Never use a small database benchmark to predict exact production timings.

---

## 13. Post-restore validation

### 13.1. Checking the restore command

Confirm:
- Command exit code is 0.
- No ignored errors in logs.
- All jobs finished.
- No hung restore sessions remain.
- Database accepts connections.
- Target database size is reasonable.
- No invalid/incomplete objects remain from failed commands.

If errors occurred, triage and fix them before cutover. A "mostly finished" restore can still be missing indexes, constraints, or rows.

### 13.2. Checking database and schemas

~~~sql
SELECT
    current_database(),
    current_user,
    version();

SELECT
    schemaname,
    count(*) AS table_count
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
GROUP BY schemaname
ORDER BY schemaname;
~~~

Compare the table/schema inventory against the source. Exclude system objects/version-specific objects when diffing.

### 13.3. Checking row counts

For critical tables, compare source/target row counts:

~~~sql
SELECT count(*) FROM app.customers;
SELECT count(*) FROM app.orders;
SELECT count(*) FROM app.order_items;
~~~

For large databases, counting every table can take considerable time and I/O. You can pick critical tables, partition-level counts, or validation aggregates by business keys.

### 13.4. Checking business invariants

Examples:
- Orders must reference valid customers.
- Daily order amount totals must match.
- No duplicate business keys.
- Status values belong to allowed domains.
- Timestamps fall within expected ranges.
- Record counts by tenant/region match.
- Ledger/debit-credit tables balance.

Business validation often catches discrepancies missed by raw row counts.

### 13.5. Checking constraints and indexes

~~~sql
SELECT
    conrelid::regclass AS table_name,
    conname,
    contype,
    convalidated
FROM pg_constraint
WHERE connamespace NOT IN (
    'pg_catalog'::regnamespace,
    'information_schema'::regnamespace
)
ORDER BY conrelid::regclass::text, conname;
~~~

Verify constraints are validated and indexes are valid. Use version-appropriate catalog queries; partitioned indexes and extension objects have distinct metadata.

### 13.6. Checking sequence state

Inspect sequence state using appropriate per-sequence queries. Example:

~~~sql
SELECT last_value, is_called
FROM app.orders_order_id_seq;
~~~

Compare max table key against next sequence value. Do not call `nextval` just to "test" in production if you do not want to consume an ID; sequence values do not roll back like table changes.

### 13.7. Checking large objects

If the application uses large objects:
- Check LO counts via appropriate catalog/API queries.
- Check references in application tables.
- Open/read sample objects via the application.
- Check permissions/ownership.
- Confirm they were not excluded from the dump.

### 13.8. Checking roles and permissions

Test connecting with the actual application role. Verify:
- `LOGIN` and database `CONNECT`.
- Schema `USAGE`/`CREATE`.
- Table/sequence privileges.
- Function `EXECUTE`.
- Default privileges.
- RLS policies.
- Ownership and role memberships.

Do not test only as superuser; superuser bypasses permission checks and hides application privilege errors.

### 13.9. Checking extensions

~~~sql
SELECT
    extname,
    extversion
FROM pg_extension
ORDER BY extname;
~~~

Confirm versions are correct, extension functions/operators work, and index methods/types are recognized.

### 13.10. Checking applications

Smoke tests should cover:
- Login/connectivity.
- Reading critical records.
- Insert/update/delete within a test transaction.
- Queries with joins/sorts/aggregates.
- Stored functions/triggers.
- Background jobs.
- Reports/exports.
- Transactions and rollbacks.
- Authentication/TLS/connection pools.

Run workload regression tests to uncover planner/extension/collation changes.

### 13.11. Analyze and vacuum

After restoring, run `ANALYZE` or §vacuumdb --analyze-in-stages§ so the planner has statistics. If needed, run `VACUUM` per policy. Do not default to running `VACUUM FULL` after a restore.

### 13.12. Checking monitoring/backups

Before opening traffic:
- Target monitoring is receiving metrics.
- Alert rules and dashboards point to the right cluster.
- Backup jobs succeed.
- WAL archiving/PITR is configured if required.
- A restore test of the new backup is scheduled.
- Downstream replication/standbys are rebuilt if needed.

---

## 14. Cutover, downtime, and rollback

### 14.1. Preparing cutover

Before the maintenance window:
- Rehearse dump/restore on production-like data.
- Measure total required downtime.
- Define the freeze window and owner.
- Prepare DNS/connection string/load balancer changes.
- Identify jobs/workers/consumers to stop.
- Prepare validation queries.
- Define the rollback deadline and decision maker.
- Ensure source backups remain recoverable.

### 14.2. Offline cutover runbook

1. Announce the maintenance window.
2. Stop application writes.
3. Stop background workers, scheduled jobs, and writable integrations.
4. Wait for open transactions to finish or roll back per policy.
5. Take the final dump and globals if changed.
6. Verify archive, checksum, and TOC.
7. Restore into the target database/cluster.
8. Run `ANALYZE` and validation.
9. Synchronize external state and confirm sequence values.
10. Switch application connections to the target.
11. Run smoke tests.
12. Open writes.
13. Monitor errors, latency, locks, replication, and business metrics.

If the source continues accepting writes after the dump snapshot starts, those writes will be absent on the target. The freeze must start before the snapshot, or delta sync must be used.

### 14.3. Cutover with baseline + delta

If downtime must be minimized:
1. Create a baseline dump while the source runs.
2. Restore the baseline onto the target.
3. Establish logical replication/delta capture from source to target per design.
4. Monitor apply lag and verify schema compatibility.
5. Stop source writes during the cutover window.
6. Wait for the target to apply all changes up to the final marker/LSN.
7. Check sequences and external state.
8. Switch applications to the target.
9. Allow target writes only after verification.

This migration is more complex than offline dump/restore. Verify logical replication support, DDL coordination, sequence handling, and cutover correctness; never assume a dump snapshot automatically syncs deltas.

### 14.4. Rollback before the target accepts writes

If writes have not yet been opened on the target:
- Switch applications back to the source.
- Verify the source remains intact.
- Decommission/disable the target per change plan.
- Save logs and archives for investigation.
- Fix root causes and rehearse again.

This is the simplest rollback point because the source remains the write authority.

### 14.5. Rollback after the target accepts writes

Once the target accepts new writes, the source lacks those changes. You cannot simply point the connection string back to the source while keeping all data.

You need one of the pre-planned strategies:
- Reverse replication if designed and tested.
- Data reconciliation by keys/transactions.
- Restore/replay from target backups/WAL if architecture permits.
- Forward-fix on the target instead of rolling back.

Never open writes simultaneously on both source and target without a conflict resolution strategy.

### 14.6. Retaining the source during the rollback window

After cutover, keep the source in a read-only or fenced state per policy:
- Prevent applications from accidentally writing to the source.
- Do not drop the source cluster immediately.
- Retain backups and logs.
- Record the final source snapshot/LSN.
- Monitor target stability before retiring the source.

### 14.7. RTO/RPO

Offline dump/restore typically achieves RPO = 0 for writes frozen and fully dumped/restored; it does not protect writes occurring after the snapshot without delta sync. RTO depends on dump, transfer, restore, validation, and cutover durations.

Base RPO/RTO on actual workload testing, not on the speed of a small test run.

---

## 15. Security, integrity, and retention of dump files

### 15.1. Dumps can contain all sensitive data

Archives can hold PII, credentials inside table data, password verifiers in globals, application secrets, and business records. Protect dumps with the same rigor as production databases.

### 15.2. File permissions

- Grant read access only to backup/restore service accounts.
- Avoid world-readable directories.
- Separate operator and application privileges.
- Restrict downloads to personal workstations.
- Delete temporary copies per retention policy after migration completes.

### 15.3. Encryption

Encrypt archives at rest and in transit. Manage encryption keys separately from backup files; verify restore access before migration. Never store keys in the same directory or inside an unprotected artifact manifest.

### 15.4. Integrity checksums

Generate a checksum after dumping and verify it again after transfer:

~~~bash
sha256sum appdb.dump > appdb.dump.sha256
sha256sum -c appdb.dump.sha256
~~~

On other operating systems, use the corresponding hash tool. A checksum proves the file was unchanged in transit; it does not prove the logical dump is complete or that restore will succeed.

### 15.5. Inspecting archives

~~~bash
pg_restore --list appdb.dump > appdb.toc
~~~

This command reads metadata/TOC and helps detect unreadable archives. It does not replace a restore test.

### 15.6. Restore testing

A backup is only trustworthy when it can be restored. Schedule a restore test into an isolated environment:
- Verify archive integrity.
- Restore using the exact target major version.
- Run schema/data validation.
- Record duration and resource usage.
- Check extensions/large objects.
- Save results and owner.

### 15.7. Retention

Define:
- Number of dump copies retained.
- Retention duration before/after cutover.
- Backup encryption key retention.
- Offsite/immutable copies if required.
- Secure deletion method.
- Legal/compliance retention.
- Who is authorized to restore/download.

### 15.8. Trust boundaries

A dump is input that can contain SQL definitions, functions, triggers, and commands. Restore archives only from trusted sources into controlled environments. Never restore untrusted dumps into clusters holding sensitive credentials or network access.

---

## 13. Post-restore validation

### 13.1. Checking the restore command

Confirm:
- Command exit code is 0.
- No ignored errors in logs.
- All jobs finished.
- No hung restore sessions remain.
- Database accepts connections.
- Target database size is reasonable.
- No invalid/incomplete objects remain from failed commands.

If errors occurred, triage and fix them before cutover. A "mostly finished" restore can still be missing indexes, constraints, or rows.

### 13.2. Checking database and schemas

~~~sql
SELECT
    current_database(),
    current_user,
    version();

SELECT
    schemaname,
    count(*) AS table_count
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
GROUP BY schemaname
ORDER BY schemaname;
~~~

Compare the table/schema inventory against the source. Exclude system objects/version-specific objects when diffing.

### 13.3. Checking row counts

For critical tables, compare source/target row counts:

~~~sql
SELECT count(*) FROM app.customers;
SELECT count(*) FROM app.orders;
SELECT count(*) FROM app.order_items;
~~~

For large databases, counting every table can take considerable time and I/O. You can pick critical tables, partition-level counts, or validation aggregates by business keys.

### 13.4. Checking business invariants

Examples:
- Orders must reference valid customers.
- Daily order amount totals must match.
- No duplicate business keys.
- Status values belong to allowed domains.
- Timestamps fall within expected ranges.
- Record counts by tenant/region match.
- Ledger/debit-credit tables balance.

Business validation often catches discrepancies missed by raw row counts.

### 13.5. Checking constraints and indexes

~~~sql
SELECT
    conrelid::regclass AS table_name,
    conname,
    contype,
    convalidated
FROM pg_constraint
WHERE connamespace NOT IN (
    'pg_catalog'::regnamespace,
    'information_schema'::regnamespace
)
ORDER BY conrelid::regclass::text, conname;
~~~

Verify constraints are validated and indexes are valid. Use version-appropriate catalog queries; partitioned indexes and extension objects have distinct metadata.

### 13.6. Checking sequence state

Inspect sequence state using appropriate per-sequence queries. Example:

~~~sql
SELECT last_value, is_called
FROM app.orders_order_id_seq;
~~~

Compare max table key against next sequence value. Do not call `nextval` just to "test" in production if you do not want to consume an ID; sequence values do not roll back like table changes.

### 13.7. Checking large objects

If the application uses large objects:
- Check LO counts via appropriate catalog/API queries.
- Check references in application tables.
- Open/read sample objects via the application.
- Check permissions/ownership.
- Confirm they were not excluded from the dump.

### 13.8. Checking roles and permissions

Test connecting with the actual application role. Verify:
- `LOGIN` and database `CONNECT`.
- Schema `USAGE`/`CREATE`.
- Table/sequence privileges.
- Function `EXECUTE`.
- Default privileges.
- RLS policies.
- Ownership and role memberships.

Do not test only as superuser; superuser bypasses permission checks and hides application privilege errors.

### 13.9. Checking extensions

~~~sql
SELECT
    extname,
    extversion
FROM pg_extension
ORDER BY extname;
~~~

Confirm versions are correct, extension functions/operators work, and index methods/types are recognized.

### 13.10. Checking applications

Smoke tests should cover:
- Login/connectivity.
- Reading critical records.
- Insert/update/delete within a test transaction.
- Queries with joins/sorts/aggregates.
- Stored functions/triggers.
- Background jobs.
- Reports/exports.
- Transactions and rollbacks.
- Authentication/TLS/connection pools.

Run workload regression tests to uncover planner/extension/collation changes.

### 13.11. Analyze and vacuum

After restoring, run `ANALYZE` or `vacuumdb --analyze-in-stages` so the planner has statistics. If needed, run `VACUUM` per policy. Do not default to running `VACUUM FULL` after a restore.

### 13.12. Checking monitoring/backups

Before opening traffic:
- Target monitoring is receiving metrics.
- Alert rules and dashboards point to the right cluster.
- Backup jobs succeed.
- WAL archiving/PITR is configured if required.
- A restore test of the new backup is scheduled.
- Downstream replication/standbys are rebuilt if needed.

---

## 14. Cutover, downtime, and rollback

### 14.1. Preparing cutover

Before the maintenance window:
- Rehearse dump/restore on production-like data.
- Measure total required downtime.
- Define the freeze window and owner.
- Prepare DNS/connection string/load balancer changes.
- Identify jobs/workers/consumers to stop.
- Prepare validation queries.
- Define the rollback deadline and decision maker.
- Ensure source backups remain recoverable.

### 14.2. Offline cutover runbook

1. Announce the maintenance window.
2. Stop application writes.
3. Stop background workers, scheduled jobs, and writable integrations.
4. Wait for open transactions to finish or roll back per policy.
5. Take the final dump and globals if changed.
6. Verify archive, checksum, and TOC.
7. Restore into the target database/cluster.
8. Run `ANALYZE` and validation.
9. Synchronize external state and confirm sequence values.
10. Switch application connections to the target.
11. Run smoke tests.
12. Open writes.
13. Monitor errors, latency, locks, replication, and business metrics.

If the source continues accepting writes after the dump snapshot starts, those writes will be absent on the target. The freeze must start before the snapshot, or delta sync must be used.

### 14.3. Cutover with baseline + delta

If downtime must be minimized:
1. Create a baseline dump while the source runs.
2. Restore the baseline onto the target.
3. Establish logical replication/delta capture from source to target per design.
4. Monitor apply lag and verify schema compatibility.
5. Stop source writes during the cutover window.
6. Wait for the target to apply all changes up to the final marker/LSN.
7. Check sequences and external state.
8. Switch applications to the target.
9. Allow target writes only after verification.

This migration is more complex than offline dump/restore. Verify logical replication support, DDL coordination, sequence handling, and cutover correctness; never assume a dump snapshot automatically syncs deltas.

### 14.4. Rollback before the target accepts writes

If writes have not yet been opened on the target:
- Switch applications back to the source.
- Verify the source remains intact.
- Decommission/disable the target per change plan.
- Save logs and archives for investigation.
- Fix root causes and rehearse again.

This is the simplest rollback point because the source remains the write authority.

### 14.5. Rollback after the target accepts writes

Once the target accepts new writes, the source lacks those changes. You cannot simply point the connection string back to the source while keeping all data.

You need one of the pre-planned strategies:
- Reverse replication if designed and tested.
- Data reconciliation by keys/transactions.
- Restore/replay from target backups/WAL if architecture permits.
- Forward-fix on the target instead of rolling back.

Never open writes simultaneously on both source and target without a conflict resolution strategy.

### 14.6. Retaining the source during the rollback window

After cutover, keep the source in a read-only or fenced state per policy:
- Prevent applications from accidentally writing to the source.
- Do not drop the source cluster immediately.
- Retain backups and logs.
- Record the final source snapshot/LSN.
- Monitor target stability before retiring the source.

### 14.7. RTO/RPO

Offline dump/restore typically achieves RPO = 0 for writes frozen and fully dumped/restored; it does not protect writes occurring after the snapshot without delta sync. RTO depends on dump, transfer, restore, validation, and cutover durations.

Base RPO/RTO on actual workload testing, not on the speed of a small test run.

---

## 15. Security, integrity, and retention of dump files

### 15.1. Dumps can contain all sensitive data

Archives can hold PII, credentials inside table data, password verifiers in globals, application secrets, and business records. Protect dumps with the same rigor as production databases.

### 15.2. File permissions

- Grant read access only to backup/restore service accounts.
- Avoid world-readable directories.
- Separate operator and application privileges.
- Restrict downloads to personal workstations.
- Delete temporary copies per retention policy after migration completes.

### 15.3. Encryption

Encrypt archives at rest and in transit. Manage encryption keys separately from backup files; verify restore access before migration. Never store keys in the same directory or inside an unprotected artifact manifest.

### 15.4. Integrity checksums

Generate a checksum after dumping and verify it again after transfer:

~~~bash
sha256sum appdb.dump > appdb.dump.sha256
sha256sum -c appdb.dump.sha256
~~~

On other operating systems, use the corresponding hash tool. A checksum proves the file was unchanged in transit; it does not prove the logical dump is complete or that restore will succeed.

### 15.5. Inspecting archives

~~~bash
pg_restore --list appdb.dump > appdb.toc
~~~

This command reads metadata/TOC and helps detect unreadable archives. It does not replace a restore test.

### 15.6. Restore testing

A backup is only trustworthy when it can be restored. Schedule a restore test into an isolated environment:
- Verify archive integrity.
- Restore using the exact target major version.
- Run schema/data validation.
- Record duration and resource usage.
- Check extensions/large objects.
- Save results and owner.

### 15.7. Retention

Define:
- Number of dump copies retained.
- Retention duration before/after cutover.
- Backup encryption key retention.
- Offsite/immutable copies if required.
- Secure deletion method.
- Legal/compliance retention.
- Who is authorized to restore/download.

### 15.8. Trust boundaries

A dump is input that can contain SQL definitions, functions, triggers, and commands. Restore archives only from trusted sources into controlled environments. Never restore untrusted dumps into clusters holding sensitive credentials or network access.

---

## 16. Troubleshooting dump/restore

### 16.1. `pg_dump` reports unsupported server version

Usually the `pg_dump` client is older than the source server's major version. Use a client version new enough to read that server and verify release compatibility. Never spoof version strings or force old binaries to proceed.

### 16.2. Permission denied during dump

Check:
- Role has `CONNECT` on the database.
- `SELECT` privileges on tables/sequences to dump.
- Privileges to read large objects if used by the application.
- Row-level security and dump options.
- Permissions to inspect objects/metadata.
- Role memberships and default privileges.

Use a dedicated backup role granted the required privileges; do not default to superuser unless needed.

### 16.3. Corrupt or unreadable archive

Check:
- `pg_dump` exit code.
- Disk full or filesystem errors.
- Network disconnects.
- Partially copied/truncated archive.
- Compression/decompression errors.
- Checksums before/after transfer.

Use `pg_restore --list` to inspect the TOC. If the archive is corrupt, take a new dump from the source or restore from a verified backup; never cut over using a truncated file.

### 16.4. Role does not exist during restore

Restoring a database archive may reference nonexistent owners/grantees. Restore globals first, or use `--no-owner`/`--no-acl` and then provision roles/privileges per target policy. Verify default privileges and role memberships after restore.

### 16.5. Tablespace location does not exist

The globals script may create tablespaces with source paths. Create the paths on the target with proper permissions, or remap/omit tablespaces per plan. Never let objects attempt to restore into a nonexistent tablespace path.

### 16.6. Missing extension control file

The target lacks the compatible extension package or has an incorrect package path. Install the extension package for the target major version, restart if required by libraries/configuration, and restore onto a clean database.

### 16.7. Collation/locale errors

The source locale is missing on the target OS or the provider/version differs. Check database locale, encoding, ICU/libc support, and collation definitions. You may need to create the target database intentionally with a different locale and verify/rebuild indexes; do not alter locale arbitrarily after restore.

### 16.8. Duplicate key or unique violation

Possible causes:
- Target table already had data before restore.
- Restore was run twice.
- Archive data contains conflicting rows.
- Target schema has a different unique constraint than source.
- An application/job is writing to the target during restore.

Prefer a fresh empty database, stop local writes, and confirm the authoritative source. Do not drop constraints to hide conflicts without a reconciliation plan.

### 16.9. Foreign key violation

Check restore ordering, target baseline, excluded tables/data, differing constraints, and triggers. With partial dumps, referenced rows may be missing. Never permanently disable FKs just to make a restore "succeed".

### 16.10. Function/language errors

The target may lack a procedural language, extension, function dependency, or OS library. Check function definitions, language packages, permissions, and extension versions before running the restore.

### 16.11. Slow restore

Classify the bottleneck:
- Archive read/decompression.
- Network transfer.
- Target storage writes.
- Index builds.
- WAL/checkpoints.
- Constraint validation.
- Lock waits.
- Too many/too few parallel jobs.
- CPU/memory pressure.

Use logs/progress views/OS metrics to tune the right component.

### 16.12. Restore succeeds but application fails

Check application roles, schema `search_path`, ownership/grants, sequences, extensions, collations, functions, connection parameters, and query plans. Database-level restore success does not prove application behavior is compatible.

### 16.13. Sequences issue duplicate IDs after cutover

Check sequence current state, maximum keys, `is_called`, increment/cache, and shared sequences. Synchronize sequences after writes are frozen and before opening traffic. Do not call `setval` based on a single table if a sequence is shared across multiple tables.

### 16.14. Dump is missing latest writes

`pg_dump` captures only a snapshot at start time. Post-snapshot writes are absent from the archive. Hold a write freeze before the snapshot or implement a tested delta sync/replication pipeline; never open the target before processing the delta.

---

## 17. Comparing dump/restore with other upgrade methods

### 17.1. `pg_upgrade`

`pg_upgrade` converts data files/catalog structures via a supported workflow between compatible major versions. Usually faster than dump/restore because it avoids exporting/importing all rows, though it has requirements for binary compatibility, extension binaries, OS/layout, and preparation.

Choose `pg_upgrade` when:
- You want an in-place/side-by-side major upgrade along a supported path.
- You can satisfy binary and filesystem requirements.
- You want to minimize data transfer time.
- You have a clear rollback/backup strategy.

### 17.2. Physical backup/restore

Physical backup/replication transfers data files and WAL via physical mechanisms. It is generally tied to the same major version/physical compatibility rules and is not a general way to change major versions outside supported upgrade workflows.

### 17.3. Logical replication

Logical replication can stream changes from an old publisher to a new subscriber to reduce downtime. It requires schema coordination, sequence handoff, DDL management, and a failover/cutover plan. Baseline dumps can be combined with logical replication in certain migration designs.

### 17.4. Dump/restore

Dump/restore is flexible across objects, encodings, and environments, but can be slow due to export/import and requires downtime without a delta mechanism.

### 17.5. Comparison table

| Method | Strengths | Primary limitations | Use case |
|---|---|---|---|
| `pg_dump`/`pg_restore` | Flexible, logical, object selection | Dump/restore time, downtime if offline | Major migration, platform move, selective migration |
| `pg_upgrade` | Usually fast, preserves data files via workflow | Binary/version/layout prerequisites | Major upgrade along supported paths |
| Physical backup/restore | Fast recovery, suits HA/DR | Physical compatibility, usually same major | Backup/DR, standbys |
| Logical replication | Can reduce downtime | DDL/sequence/schema coordination | Online migration, supported cross-version replication |

Do not choose a method based on speed alone. Weigh RPO/RTO, database size, extension compatibility, operating system, downtime budget, and rehearsal capability.

---

## 18. General dump/restore major upgrade runbook

### 18.1. Before the maintenance window

1. Inventory versions, databases, roles, tablespaces, extensions, and external dependencies.
2. Choose archive format and compression.
3. Estimate archive size, transfer, restore, and analyze durations.
4. Provision the target cluster and extension packages.
5. Create roles/tablespaces/databases per target policy.
6. Run a full rehearsal on production-like data.
7. Prepare validation queries, smoke tests, and rollback decision points.
8. Confirm backup retention and encryption.

### 18.2. Dump

1. Freeze DDL or control schema changes.
2. If offline, freeze application writes before the snapshot.
3. Dump globals.
4. Dump database(s) using custom/directory format.
5. Capture logs/exit codes.
6. Generate checksums.
7. Inspect archive TOC.
8. Copy archives securely to target storage.

### 18.3. Restore

1. Install target binaries/extensions.
2. Restore globals/tablespaces.
3. Create target databases with the right encoding/locale/owner.
4. Restore archives using `pg_restore`/`psql`.
5. Tune parallel jobs for memory/I/O.
6. Stop and resolve errors.
7. Run `ANALYZE`.
8. Check sequences, permissions, and large objects.

### 18.4. Validation

1. Compare schema/table inventories.
2. Compare row counts/critical aggregates.
3. Check constraints/indexes.
4. Check extensions and functions.
5. Test application roles.
6. Run application smoke/regression tests.
7. Confirm backups/monitoring/replication.
8. Pass the readiness gate before cutover.

### 18.5. Cutover

1. Stop writes/jobs.
2. Confirm final dump/delta completeness.
3. Switch application routing.
4. Run smoke tests on the target.
5. Open writes.
6. Monitor business metrics/latency/errors.
7. Keep the source fenced/read-only during the rollback window.
8. Retire the source after owner sign-off.

### 18.6. When to halt cutover

Do not open writes if:
- Unexplained restore errors remain.
- Critical table counts/business checks mismatch.
- Application roles lack access.
- Sequences risk issuing duplicate IDs.
- Critical extensions/functions fail.
- Post-snapshot writes have not been transferred.
- Backup/rollback paths are unavailable.
- The target lacks required monitoring/alerting.

---

## 19. Lab: dumping and restoring a database

Perform this on two lab PostgreSQL instances or an isolated source/target cluster. Use a test database; never drop a production database.

### 19.1. Preparing the source database

~~~sql
CREATE DATABASE dump_lab;
~~~

Connect to `dump_lab`:

~~~sql
CREATE SCHEMA app;

CREATE TABLE app.customers (
    customer_id bigint PRIMARY KEY,
    full_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE app.orders (
    order_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES app.customers(customer_id),
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO app.customers(customer_id, full_name)
VALUES
    (1, 'An Nguyen'),
    (2, 'Binh Tran');

INSERT INTO app.orders(customer_id, amount)
VALUES
    (1, 125.50),
    (1, 80.00),
    (2, 240.00);
~~~

### 19.2. Custom format dump

~~~bash
pg_dump -Fc -d dump_lab -f dump_lab.dump
~~~

Check the exit code and archive:

~~~bash
pg_restore --list dump_lab.dump
~~~

### 19.3. Directory format dump

~~~bash
pg_dump -Fd -j 2 -d dump_lab -f dump_lab_dir
~~~

Directory output is a folder; preserve all contents when copying to the target.

### 19.4. Creating the target database

On the target cluster:

~~~bash
createdb -T template0 -E UTF8 dump_lab_new
~~~

If using a different owner/locale, add options matching the target environment.

### 19.5. Restore

~~~bash
pg_restore \
  -d dump_lab_new \
  --exit-on-error \
  --verbose \
  dump_lab.dump
~~~

Try a parallel restore on the directory archive into another fresh lab database:

~~~bash
pg_restore -j 2 -d dump_lab_parallel dump_lab_dir
~~~

### 19.6. Verifying data

~~~sql
SELECT count(*) FROM app.customers;
SELECT count(*) FROM app.orders;

SELECT
    c.customer_id,
    c.full_name,
    count(o.order_id) AS order_count,
    coalesce(sum(o.amount), 0) AS total_amount
FROM app.customers AS c
LEFT JOIN app.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
~~~

Run the same queries on source and target and compare results.

### 19.7. Checking sequence/identity

Inspect the sequence bound to the identity column and the maximum value in `orders`. After restoring, try inserting a lab row and confirm the new ID does not collide. Perform this in the test database; rolling back a transaction does not revert sequence values.

### 19.8. Testing plain SQL restore

~~~bash
pg_dump -Fp -d dump_lab -f dump_lab.sql
createdb dump_lab_plain
psql -X -v ON_ERROR_STOP=1 -d dump_lab_plain -f dump_lab.sql
~~~

Compare duration, script readability, and restore behavior between plain and custom formats.

### 19.9. Lab cleanup

After recording results, drop the lab databases safely. Never run `DROP DATABASE` if active sessions or data to retain exist.

---

## 20. Lab: globals, roles, and restore options

### 20.1. Creating test roles

On the source:

~~~sql
CREATE ROLE dump_lab_owner NOLOGIN;
CREATE ROLE dump_lab_app LOGIN;
GRANT dump_lab_owner TO dump_lab_app;
ALTER SCHEMA app OWNER TO dump_lab_owner;
GRANT USAGE ON SCHEMA app TO dump_lab_app;
GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA app
TO dump_lab_app;
~~~

In the lab, use secure passwords/secrets if login is required. Never hardcode real passwords in scripts.

### 20.2. Dumping globals

~~~bash
pg_dumpall --globals-only -f globals_lab.sql
~~~

Review the file to understand role/tablespace statements. The file may contain sensitive role metadata.

### 20.3. Restoring globals on the target

~~~bash
psql -X -v ON_ERROR_STOP=1 -d postgres -f globals_lab.sql
~~~

If roles already exist, resolve conflicts deliberately before executing.

### 20.4. Restoring without owner/ACLs

Create an empty target database and run:

~~~bash
pg_restore \
  -d dump_lab_no_acl \
  --no-owner \
  --no-acl \
  --exit-on-error \
  dump_lab.dump
~~~

Then run provisioning SQL to assign owners/grants per target policy. Test using the application role instead of superuser.

### 20.5. Controlled `--clean` test

On a disposable lab database:
- Restore once.
- Restore again with `--clean --if-exists`.
- Observe objects dropped/recreated.
- Note the effect on local-only objects.

Never use the clean option on a database containing data you need to keep.

---

## 21. Practice exercises

These exercises use a PostgreSQL lab. Never drop/clean a production database to test a hypothesis.

### Exercise 1 — Logical dump

How does dump/restore differ from physical backup?

### Exercise 2 — `pg_dump`

What is the scope of `pg_dump`? Does it automatically dump cluster-wide roles/tablespaces?

### Exercise 3 — `pg_dumpall`

What types of objects does `pg_dumpall --globals-only` contain?

### Exercise 4 — `pg_restore`

Which archive formats does `pg_restore` support?

### Exercise 5 — Plain format

Which tool restores a plain SQL dump? Does it support parallel restore?

### Exercise 6 — Custom format

What benefits does a custom archive offer compared to plain SQL?

### Exercise 7 — Directory format

Why is directory format suitable for parallel dump and parallel restore?

### Exercise 8 — Tar format

Does a tar archive support parallel restore like custom/directory?

### Exercise 9 — Version compatibility

Why can an older `pg_dump` client not dump a server with a newer major version?

### Exercise 10 — Upgrade direction

Why is dump/restore usually convenient for moving from an older major version to a newer one?

### Exercise 11 — Globals

Why should roles/tablespaces be restored before the database archive?

### Exercise 12 — Tablespaces

What happens if the target lacks a filesystem path declared in a tablespace definition?

### Exercise 13 — Extensions

Does a dump carry extension shared library binaries?

### Exercise 14 — Large objects

What needs to be done if an application uses large objects?

### Exercise 15 — Sequence state

How can a dump store sequence state? Why must it be verified before cutover?

### Exercise 16 — Snapshot

What does it mean that `pg_dump` creates a consistent snapshot?

### Exercise 17 — Writes after snapshot

Is a row committed after the dump snapshot starts guaranteed to appear in the archive?

### Exercise 18 — Multiple databases

Does `pg_dumpall` create a single snapshot across all databases?

### Exercise 19 — Parallel restore

Can a custom archive be restored with `-j`? Which resources does parallel restore impact?

### Exercise 20 — Single transaction

Why cannot `--single-transaction` be combined with parallel restore?

### Exercise 21 — `--clean`

What does `--clean` do? Why is caution required?

### Exercise 22 — `--no-owner`/`--no-acl`

In what scenarios are these two options useful?

### Exercise 23 — Restore errors

Why should `--exit-on-error` be used alongside checking logs/exit codes?

### Exercise 24 — `ANALYZE`

Why is `ANALYZE` needed after restoring?

### Exercise 25 — Validation

Are row counts sufficient to prove a migration is correct? List additional validations.

### Exercise 26 — Security

Why must dump archives and `globals.sql` be protected like production data?

### Exercise 27 — Rollback

Why is rollback simplest before the target accepts writes?

### Exercise 28 — Low downtime

How can a baseline dump be combined with logical replication to reduce downtime? What risks must be addressed?

### Exercise 29 — Cutover

Outline a safe offline cutover sequence.

### Exercise 30 — Synthesis

A restore finishes, yet the app role cannot access tables, sequences might generate duplicate IDs, and an extension function reports a missing library. State the investigation order and the conditions preventing opening writes.

---

## 22. Solutions — exercises 1 to 15

### Exercise 1 — Logical dump

Dump/restore transfers schemas and data logically via SQL/archives. Physical backups copy data files/WAL using physical mechanisms and have different version/layout compatibility requirements.

### Exercise 2 — `pg_dump`

`pg_dump` dumps a single database, either in full or selected schemas/tables/objects. It does not automatically dump cluster-wide roles/tablespaces; use `pg_dumpall --globals-only` or separate provisioning.

### Exercise 3 — `pg_dumpall`

A globals dump contains roles, memberships, tablespaces, and supported global definitions. Protect the file because it may contain password verifiers and sensitive metadata.

### Exercise 4 — `pg_restore`

`pg_restore` reads custom, directory, and tar archives produced by `pg_dump`. Plain SQL scripts are restored using `psql`.

### Exercise 5 — Plain format

Use `psql` to execute the script. Plain SQL restores sequentially and lacks `pg_restore`'s parallel restore mode.

### Exercise 6 — Custom format

Custom format compresses the archive, includes a TOC for listing/selecting objects, and supports parallel restore. It fits well when a single flexible archive file is desired.

### Exercise 7 — Directory format

Directory format stores objects/data across multiple files and supports both parallel dump and parallel restore. It is useful for large databases, though the entire directory must be copied.

### Exercise 8 — Tar format

No. Tar format uses `pg_restore` but does not support parallel restore like custom/directory.

### Exercise 9 — Version compatibility

The `pg_dump` client must understand the server's protocol/catalogs. Older clients are not designed to read newer major versions; use a sufficiently recent client per compatibility rules.

### Exercise 10 — Upgrade direction

Logical dumps decouple data from old physical file formats and can restore into a newer server if SQL/features/extensions are compatible. Downgrading to an older server is not supported by default.

### Exercise 11 — Globals

Database objects may reference owners/roles and tablespaces. Creating global objects first prevents missing role/tablespace errors during restore and preserves proper ownership.

### Exercise 12 — Tablespaces

`CREATE TABLESPACE` can fail if the path does not exist or permissions are wrong; objects depending on that tablespace will fail to restore. Create or remap paths before restoring.

### Exercise 13 — Extensions

No. A dump can contain `CREATE EXTENSION`/extension-owned SQL metadata, but does not include shared library binaries. Install compatible packages on the target before restoring.

### Exercise 14 — Large objects

Verify `pg_dump` includes large objects, avoid exclusion flags, and check references/OIDs. After restore, test reading/writing LOs with the application.

### Exercise 15 — Sequence state

Archives/scripts can store sequence definitions and `setval` states. Check max keys, `is_called`, increment/cache, and writes during snapshot/cutover so next values do not collide.

---

## 23. Solutions — exercises 16 to 30

### Exercise 16 — Snapshot

`pg_dump` uses an MVCC snapshot to see a consistent database state at the moment the dump starts. Commits after the snapshot do not appear in the dump.

### Exercise 17 — Writes after snapshot

No. A row committed after the snapshot starts is excluded from the archive. You must freeze writes before the snapshot or synchronize deltas after the baseline.

### Exercise 18 — Multiple databases

No. `pg_dumpall` dumps each database individually, each with its own snapshot; there is no single transaction snapshot across the entire cluster.

### Exercise 19 — Parallel restore

Yes. Custom archives can be restored with `pg_restore -j`. Parallel jobs increase connections, CPU, memory/index-build demand, storage I/O, WAL, and checkpoint pressure.

### Exercise 20 — Single transaction

Parallel restore uses multiple independent workers/transactions; single transaction requires one transaction. The two modes are incompatible, and a single transaction can become massive.

### Exercise 21 — `--clean`

It drops objects before recreating them. If misused, it can delete existing data/objects and local-only objects. Use only on confirmed targets or lab databases.

### Exercise 22 — `--no-owner`/`--no-acl`

Used when the target has a different role/ownership policy than the source or roles are provisioned separately. Afterward, assign owners/grants/default privileges per target policy.

### Exercise 23 — Restore errors

Not halting on errors can leave an archive only partially restored. `--exit-on-error` fails fast; logs and exit codes show whether the command succeeded or failed. Resolve all errors before cutover.

### Exercise 24 — `ANALYZE`

Restoring does not guarantee planner statistics reflect the new distribution. `ANALYZE` updates statistics so the planner selects good plans and reduces post-cutover query regressions.

### Exercise 25 — Validation

No. Row counts do not catch type/constraint/ownership/function/sequence errors or business semantics. Supplement with aggregates, referential checks, duplicate checks, extension/function tests, permissions, sequences, and application smoke/regression tests.

### Exercise 26 — Security

Dumps can contain PII, credentials in rows, password verifiers in globals, and business data. Restrict permissions, encrypt, enforce retention, verify checksums, and control restore access.

### Exercise 27 — Rollback

Before the target accepts writes, the source remains the write authority and can continue serving applications. After target writes, the source lacks new changes; rollback requires reverse sync or reconciliation.

### Exercise 28 — Low downtime

Dump a baseline while the source runs, restore onto the target, and configure logical replication/delta capture. Before cutover, freeze writes, wait for apply up to the final marker/LSN, verify sequences/DDL/schemas/external state, and switch traffic. Risks include DDL drift, slot retention, apply lag, sequence state, and conflict/rollback handling.

### Exercise 29 — Cutover

Freeze writes/jobs; drain transactions; take the final dump or verify delta completion; restore; validate schemas/data/business rules; sync sequences; switch connection routing; run smoke tests; open writes; monitor; keep the source fenced during the rollback window.

### Exercise 30 — Synthesis

1. Keep the target read-only and do not open writes yet.
2. Check role ownership, schema/table grants, sequence privileges, and default privileges; test using the app role.
3. Identify sequences tied to identity/serial columns, compare max keys, `last_value`/`is_called`, increment/cache, and synchronize before writes.
4. Install extension packages matching the target major version, check control/library paths and extension versions; confirm functions/types/operators work.
5. Run smoke tests using the app role, and verify data/business invariants plus backups/monitoring.
6. Open writes only when permissions, sequences, extensions, and validation all pass. If unfixable within the window, roll back before the target accepts writes.

---

## 24. Final cutover checklist

### Before dump
- [ ] Source/target versions and client tools verified.
- [ ] Roles, tablespaces, extensions, locales, and special objects inventoried.
- [ ] Write freeze or delta sync strategy defined.
- [ ] Archive, target disk, WAL, and temp space budgeted.
- [ ] Restore rehearsal executed and duration confirmed.

### After dump
- [ ] `pg_dump` exit code succeeded.
- [ ] Archive/SQL script is readable.
- [ ] TOC and checksum saved.
- [ ] Globals dump secured.
- [ ] Archive copied completely with matching checksum.

### After restore
- [ ] No unexplained restore errors remain.
- [ ] Roles/tablespaces/ownership/ACLs are correct.
- [ ] Extensions and large objects work.
- [ ] Tables, indexes, constraints, and sequences are valid.
- [ ] Row counts and business invariants pass.
- [ ] `ANALYZE` completed.
- [ ] App role and smoke tests succeed.

### Before opening writes
- [ ] No untransferred source writes remain after the final snapshot.
- [ ] External state and background jobs ready.
- [ ] Connection routing points to the target.
- [ ] Monitoring, alerting, and target backups operational.
- [ ] Rollback owner, window, and decision criteria clear.

---

## 25. PostgreSQL reference documentation

Prefer documentation matching the exact major version of `pg_dump`/`pg_restore` and servers:

- [PostgreSQL — pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html): formats, selection, snapshots, and dump options.
- [PostgreSQL — pg_dumpall](https://www.postgresql.org/docs/current/app-pg-dumpall.html): cluster dumps and globals.
- [PostgreSQL — pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html): archive restore, parallel jobs, clean/create/sections.
- [PostgreSQL — psql](https://www.postgresql.org/docs/current/app-psql.html): plain SQL restore and error handling.
- [PostgreSQL — CREATE DATABASE](https://www.postgresql.org/docs/current/sql-createdatabase.html): templates, encoding, and locale.
- [PostgreSQL — Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): `ANALYZE` and statistics.
- [PostgreSQL — Upgrading a PostgreSQL Cluster](https://www.postgresql.org/docs/current/upgrading.html): major upgrade methods.

`/current/` pages may point to the newest major version. Verify options, defaults, and version compatibility for the actual client/server versions in operation.

---

## 26. Summary

Dump and restore is a flexible logical migration method for PostgreSQL major upgrades, platform moves, and database migrations that can tolerate export/import time. It requires thorough preparation of global objects, extension binaries, tablespaces, locales, permissions, sequence state, and external dependencies.

Key principles to remember:

1. `pg_dump` dumps one database; `pg_dumpall` can dump multiple databases and global objects.
2. Plain SQL restores via `psql`; custom/directory/tar archives restore via `pg_restore`.
3. Directory format supports parallel dump and restore; custom format supports parallel restore.
4. The `pg_dump` client must be new enough to read the source server; never assume backward compatibility for downgrades.
5. Restore roles/tablespaces and install extensions before restoring database objects.
6. `pg_dump` takes a consistent snapshot of one database, not post-snapshot writes.
7. `pg_dumpall` does not take a single snapshot across all databases.
8. Sequence state can be stored in archives, yet next values must be confirmed before cutover.
9. Dumps do not copy cluster configuration, external systems, replication slots, or all secrets.
10. Parallel restore increases CPU, memory, I/O, WAL, and checkpoint pressure.
11. Use a fresh target database, check logs/exit codes, and never ignore restore errors.
12. Run `ANALYZE` and verify permissions, constraints, indexes, extensions, large objects, and business invariants.
13. Dump archives and globals must be encrypted, checksummed, and protected like production data.
14. Offline cutover requires freezing writes before the snapshot; low-downtime migrations require designed delta sync.
15. After target writes, rollback requires reverse sync or reconciliation; never merely swap the connection string.
16. Open writes only after validation, sequence handoff, application smoke tests, and rollback criteria are satisfied.

Overall workflow: **inventory → choose format/version → dump globals and database → verify archive/checksum → provision target → restore → analyze/validate → freeze writes or apply delta → sequence/external handoff → cutover → monitor and maintain rollback window**.
