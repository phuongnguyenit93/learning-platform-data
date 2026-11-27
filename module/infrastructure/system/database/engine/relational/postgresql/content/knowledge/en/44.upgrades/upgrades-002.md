# Reading Release Notes and Building a Compatibility Change List for PostgreSQL Upgrades

Upgrading PostgreSQL is broader in scope than replacing binaries or moving a data directory to a new version. A major release can change SQL syntax, function behavior, system catalogs, configuration, security defaults, the planner, extension interfaces, and how operational tools behave. A small note in the release notes can directly affect applications, migration scripts, backup jobs, or failover procedures.

Release notes are the first source for identifying changes between the current version and the target version. However, skimming the list of new features is not enough. Someone preparing an upgrade must also look for backward-incompatible changes, removed features, fixed behaviors, new defaults, new limits, security changes, and migration notes. Then each item must be linked to actual components in the system, assessed for risk, assigned an owner, and paired with tests proving the system still works.

This lesson belongs to the **Upgrades** chapter of the *Database Engine Relational PostgreSQL* module. It guides you through collecting release notes across the exact version range, analyzing changes, inventorying applications and infrastructure, building a compatibility register, identifying blockers, designing tests, and finalizing the pre-upgrade task list.

> **Principle:** Every change in the release notes must be linked to a specific component or explicitly recorded as having an undetermined impact scope. A list that merely copies release notes is not yet a compatibility assessment.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish major releases, minor releases, and categories of changes in PostgreSQL.
2. Identify the complete range of release notes to read from the source version to the target version.
3. Locate the Migration, Server, SQL, Utilities, Client Interfaces, Extensions, and Security sections.
4. Distinguish new features from changes that can break compatibility.
5. Recognize changes in syntax, semantics, defaults, configuration, catalogs, and the planner.
6. Assess the impact of security, authentication, and TLS changes.
7. Verify compatibility of extensions, drivers, poolers, and backup tools.
8. Inventory server configuration, SQL, stored procedures, jobs, and migration scripts.
9. Evaluate collation, locale, encoding, time zone, and operating system dependencies.
10. Identify changes that can affect replication, backup, recovery, and HA.
11. Build a compatibility register with severity, owner, evidence, and validation.
12. Distinguish blockers, high risks, conditional changes, and informational items.
13. Use PostgreSQL queries to capture a pre-upgrade baseline.
14. Search for usage of old settings/APIs in repositories and deployment automation.
15. Design regression tests and a staging upgrade rehearsal.
16. Distinguish minor updates from major upgrades and choose the appropriate migration approach.
17. Establish cutover, rollback, and acceptance criteria.
18. Create checklists to review and approve the compatibility change list.

## 2. What are release notes?

Release notes are documentation describing the changes included in a software release. For PostgreSQL, release notes typically organize content by version and change category, such as server, SQL, utilities, client interfaces, extensions/contrib, build/platform, and migration.

Release notes may mention:
- New features.
- Bug fixes.
- Behavioral changes.
- Deprecated features or APIs.
- Removed features.
- Default value changes.
- Configuration changes.
- Catalog or system view changes.
- Planner/executor changes.
- Security fixes.
- Requirements for extensions, compilers, operating systems, or tools.

### 2.1. Release notes are not an upgrade runbook

Release notes explain how the product changed. They do not necessarily describe in full how to prepare backups, run `pg_upgrade`, shift traffic, migrate extensions, handle application cutover, or roll back after the target has accepted writes.

You must also read the official upgrade documentation and extension/vendor guides.

### 2.2. Release notes are not an exhaustive list of every difference

Not every behavioral difference is listed as a separate item. The planner may choose a different execution plan, a bug fix may correct results that were previously wrong, and an extension may change independently of PostgreSQL core.

Therefore, release notes are an input to the assessment, while system inventory and testing determine the actual impact.

### 2.3. Read release notes across the version range

A system upgrading from PostgreSQL 15 to 18 must read the changes for 16, 17, and 18—not just the page for 18. Intermediate major versions can contain configuration or behavioral changes that the system currently uses.

You should also review relevant minor releases for both source and target to capture bug fixes, security fixes, known issues, and changes included in the binaries being deployed.

## 3. Distinguishing major and minor releases

From PostgreSQL 10 onward, the standard numbering scheme is major version and minor version, such as `16.1`, `16.2` or `17.0`, `17.1`.

- **Major release:** the first number changes, e.g., 16 to 17. A major upgrade can change internal catalog/storage compatibility and usually requires a supported migration method.
- **Minor release:** the second number changes, e.g., 17.1 to 17.2. Minor releases primarily contain bug fixes and security fixes, typically preserving data compatibility within the same major version.

### 3.1. Minor upgrades still require reading release notes

Minor releases usually do not require dump/restore or `pg_upgrade`, but they can fix behavior an application was unintentionally relying on, fix a bug causing a query to return different results from the buggy behavior, alter security behavior, fix crash/corruption bugs, require a restart to swap binaries, or affect extension/client packages.

### 3.2. Major upgrades require a broader assessment

A major upgrade can involve catalog changes, removed parameters/SQL features, data type or function behavior, extension binary compatibility, planner changes, collation versions, authentication defaults, backup/replication tooling, upgrade method, and downtime.

### 3.3. Do not infer compatibility from version numbers alone

Two releases within the same major version generally carry higher compatibility expectations, yet still require checking bug/security notes and extension compatibility. Two releases across different major versions cannot be treated as binary/data-directory interchangeable.

## 4. Identifying source and target versions

Before reading release notes, record the actual current version and the target version.

On the server:

```sql
SELECT
    version() AS full_version,
    current_setting('server_version') AS server_version,
    current_setting('server_version_num') AS server_version_num;
```

Record:
- Current PostgreSQL major/minor version.
- Exact target PostgreSQL major/minor version.
- Operating system and version.
- CPU architecture.
- Package source/repository.
- Extension versions.
- Driver/client versions.
- HA manager and DCS versions.
- Backup tooling versions.
- Deployment topology.

### 4.1. Target must be a specific version

Do not write "upgrade to latest PostgreSQL" in the compatibility register. Record the exact major/minor version, such as `17.4` or the organization-approved version. If the target changes during preparation, re-review release notes and test scope.

### 4.2. Identify every cluster in the environment

Production, staging, DR, reporting, development, and local test clusters may not run the same version. Do not inspect a single primary's version and apply it to all environments.

### 4.3. Distinguish server and client versions

PostgreSQL server, libpq, `psql`, `pg_dump`, `pg_restore`, `pg_basebackup`, JDBC driver, psycopg, Npgsql, PgBouncer, and monitoring exporters have independent version lifecycles. Record them as separate inventory rows.

## 5. Determining the release notes range to read

Suppose the source is PostgreSQL 14.9 and the target is 17.4. The major notes scope includes changes in PostgreSQL 15, 16, and 17.

How to define the reading range:

1. Confirm source major/minor from production.
2. Confirm the chosen target major/minor.
3. List every major version between source and target, inclusive of target.
4. Read the migration notes of each major version.
5. Read all relevant major-release note sections for each version involved.
6. Read minor-release notes relevant to the source/target deployment and the patches the system will traverse.
7. Record the date, URL, version, and reviewer.

### 5.1. Do not skip intermediate major versions

A change introduced in an intermediate major version can still affect a direct upgrade to the target. You do not need to install every major version sequentially just to read their notes.

### 5.2. Read migration notes first

The Migration section typically contains changes that must be addressed before or during an upgrade. Flag items with phrasing such as:
- no longer supported;
- removed;
- must be changed;
- incompatible;
- requires;
- cannot be used;
- default has changed;
- behavior has changed.

These are screening keywords, not the sole proof of impact severity.

### 5.3. Read all relevant sections after screening

Do not search only for the word "removed". A bug fix can alter query results, a planner improvement can cause a performance regression, and a new default can affect authentication or memory usage even if it is not labeled a breaking change.

## 6. How to read a release note entry

For each item, break the content into questions:

1. **What changed?** Which component or behavior changed?
2. **When?** From which version did the change appear?
3. **Why?** Is this a feature, bug fix, security fix, or compatibility change?
4. **Who is affected?** Server, DBA, application, extension, client, OS, or automation?
5. **Is it conditional?** Does it apply only when a specific setting is enabled or a specific API is used?
6. **What is the old behavior?** How does the current system behave today?
7. **What is the new behavior?** How will the target behave differently?
8. **What must change?** Does code, config, data, an extension, or a process need updating?
9. **How to prove it?** Which test proves it has been handled?
10. **What if it fails?** Is there a workaround, fallback, or rollback path?

### 6.1. Do not copy long verbatim paragraphs into the register

Write a short summary sentence in your operations team's language, pointing to the original URL and section. Save the version and heading so reviewers can open the exact source text.

### 6.2. Distinguish fact from hypothesis

Example:
- Fact: the target release changes the default of a setting.
- Hypothesis: the application may be affected because it relies on the old default.
- Evidence: production config does not set that setting and integration tests rely on the old behavior.
- Action: set explicit configuration or update code, then run tests.

Do not record a hypothesis as a confirmed conclusion.

## 7. Classifying compatibility changes

| Type | Description | Example impact |
|---|---|---|
| Removed | Feature/API/setting removed | Old config is no longer accepted |
| Deprecated | Feature still works but should no longer be relied upon | Need a replacement plan |
| Behavior | Semantics or processing result changed | Query/application logic needs testing |
| Default | Default value changed | Systems without explicit settings are affected |
| SQL/API | Syntax, function, operator, or type changed | Stored procedure/client query fails |
| Catalog | System catalog/view/function changed | Monitoring or admin scripts fail |
| Security | Authentication, privilege, TLS, or policy changed | Clients cannot connect |
| Performance | Planner, executor, memory, or I/O behavior changed | Query latency/throughput changes |
| Extension | Extension API, version, or build requirement changed | Extension fails to load/upgrade |
| Utility | Tool option, output, or behavior changed | Backup/deployment automation fails |
| Platform | OS, compiler, architecture, or library dependency changed | Package/build incompatible |
| Replication/Recovery | WAL, slot, backup, or standby behavior changed | DR/failover process affected |
| Bug fix | Previous bug fixed | Result or timing differs from prior behavior |

### 7.1. Breaking change

A breaking change is a change that causes a previously working component to stop working or require modification to continue working.

Not every removed feature is a blocker for every system. If the system does not use that feature, the impact may be none, though evidence is required to conclude so.

### 7.2. Behavioral change

An API that still exists while its semantics change can be more dangerous than a compile error. For instance, a query still executes, yet its results, ordering, rounding, timezone interpretation, or privilege checks differ.

### 7.3. Default change

If configuration is not explicit, the system inherits the release default. Therefore, default changes must be compared against effective production values, not merely config files stored in Git.

### 7.4. Bug fixes also need checking

If an application relies on an old bug, a bug fix can alter behavior. Do not treat a bug as a contract; determine how the application must adapt to comply with correct semantics.

## 8. Building a compatibility inventory

Release notes are only useful when you know what your system uses. Build an inventory by layer.

**Database**
- Database names, owners, encodings, locales.
- Schemas, tables, views, materialized views.
- Functions, procedures, triggers, operators, types.
- Extensions and versions.
- Collations and ICU/libc providers.
- Roles, grants, row-level security policies.
- Foreign data wrappers and foreign servers.

**Application**
- Services, batch jobs, ETL/CDC consumers.
- SQL embedded in code.
- ORM and migration framework.
- Connection pools.
- Driver/client library versions.
- Query builders and generated SQL.

**Operations**
- `postgresql.conf`, include files, `pg_hba.conf`, `pg_ident.conf`.
- Backup/PITR scripts.
- Replication/HA configuration.
- Monitoring exporters, dashboards, and alerts.
- Deployment scripts, service units, container images.
- Cron jobs, maintenance jobs, and failover runbooks.

**Platform**
- OS, architecture, kernel.
- Locale packages, ICU, OpenSSL, LDAP/Kerberos.
- Filesystem, storage, mount options.
- Package repository and compiler/runtime dependencies.

## 9. Capturing a baseline from PostgreSQL

The following queries help record the source cluster state. Run them with an appropriately privileged role and store results by date/cluster.

### 9.1. Version and cluster identity

```sql
SELECT
    version() AS full_version,
    current_setting('server_version') AS server_version,
    current_setting('server_version_num') AS server_version_num,
    pg_postmaster_start_time() AS postmaster_started_at;
```

### 9.2. Database encodings and collations

```sql
SELECT
    datname,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate,
    datctype
FROM pg_database
ORDER BY datname;
```

Some versions provide additional metadata about locale providers. Adjust the query to match the source cluster schema.

### 9.3. Installed extensions

```sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS extension_schema
FROM pg_extension
ORDER BY extname;
```

### 9.4. Available extension versions

```sql
SELECT
    name,
    default_version,
    installed_version
FROM pg_available_extensions
ORDER BY name;
```

This list reflects extension control files installed on the current server, not what is guaranteed to exist in the target package. Check the target environment separately.

### 9.5. Effective configuration

```sql
SELECT
    name,
    setting,
    unit,
    source,
    sourcefile,
    sourceline,
    pending_restart
FROM pg_settings
ORDER BY name;
```

Record both the effective value and source. A config file may contain values overridden by command-line flags, `ALTER SYSTEM`, or include files.

### 9.6. Config parse errors

```sql
SELECT
    sourcefile,
    sourceline,
    name,
    setting,
    applied,
    error
FROM pg_file_settings
WHERE error IS NOT NULL
   OR applied = false
ORDER BY sourcefile, sourceline;
```

This view reflects config files read by PostgreSQL; also inspect startup logs and how the service passes command-line options.

### 9.7. `pg_hba` rules

```sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_hba_file_rules
ORDER BY line_number;
```

Do not export passwords or secrets into the inventory. Record the authentication method and rule scope.

### 9.8. Shared preload libraries

```sql
SHOW shared_preload_libraries;
```

Each library must be confirmed to have a target-compatible binary and load cleanly after restart.

## 10. Inventorying application SQL and database objects

Locate all SQL that can run against the target:
- Queries in source code.
- Stored procedures/functions.
- Trigger bodies.
- Views/materialized views.
- Migration scripts.
- Scheduled SQL jobs.
- Reporting queries.
- Administrative scripts.
- Ad hoc scripts used in production runbooks.

### 10.1. Searching repositories

Use repository search tools to look for removed/deprecated SQL syntax, removed configuration names, function/operator names mentioned in release notes, system catalog/view names, authentication options, extension-specific APIs, and SQL patterns affected by planner or type semantics.

Example:

```bash
rg -n -i "recovery\.conf|wal_keep_segments|old_setting_name" .
```

Replace sample names with real keywords from the release notes. Exclude generated files or vendor code where appropriate, but document the excluded scope.

### 10.2. Search results do not prove runtime usage

A setting name may appear in old docs or test fixtures. Conversely, SQL may be constructed dynamically and never appear as a literal. Combine source search, query logs, application tracing, and owner interviews.

### 10.3. Finding dynamic SQL

Check:
- `EXECUTE` in PL/pgSQL.
- SQL built via string concatenation.
- ORM-generated SQL.
- Query templates.
- Stored procedures invoked by applications.
- ETL/BI tools that generate SQL dynamically.

### 10.4. Inventorying system catalog dependencies

Applications that frequently query `pg_catalog` or `information_schema` directly may depend on internal columns/semantics. Identify which queries use catalogs for monitoring, migrations, or application logic.

Prefer supported views/functions and check release notes for catalog changes. Do not treat catalog layouts as stable APIs unless documented as such.

## 11. SQL syntax and semantics changes

Read release note items relating to:
- Parser and grammar.
- Reserved keywords.
- Data types.
- Operators.
- Built-in functions.
- Casts and implicit conversions.
- Aggregate/window functions.
- JSON/JSONB.
- Date/time.
- Numeric and floating-point behavior.
- Collation and string operations.
- DDL/DML behavior.
- Privileges and RLS.

### 11.1. Reserved words

A previously valid identifier may become a keyword or be parsed differently. Check schema/table/column/function names and dynamic SQL.

### 11.2. Function signatures

A function may change overloads, argument types, return type, or volatility/strictness behavior. Compile stored procedures and test client deserialization.

### 11.3. Implicit casts

Changes in cast resolution can cause a query to no longer resolve a function overload, pick a different overload, fail due to an ambiguous operator, or change its execution plan/result.

### 11.4. Date/time and timezone

Test timestamp conversions, timezone database, daylight saving rules, interval arithmetic, and date string parsing. Avoid relying on implicit session timezones in business logic.

### 11.5. Ordering and collation

String sort order can change with libc/ICU versions. `ORDER BY` queries, unique indexes, and application pagination can be affected.

### 11.6. Numeric and floating-point

Test rounding, overflow, division by zero, NaN/infinity comparisons, aggregate precision, and client serialization. Test boundary values rather than just typical data.

### 11.7. JSON and JSONB

Test function/operator semantics, path expressions, indexing, ordering assumptions, and client decoding. Do not assume all JSON text retains identical formatting after parsing/serialization.

## 12. Configuration parameter changes

Cross-check source effective settings against target release notes and target `postgresql.conf.sample`.

Change types:
- Setting removed.
- Setting renamed.
- Setting deprecated.
- New setting.
- Default changed.
- Unit/range changed.
- Context changed (reload/restart).
- Semantics changed.
- Setting moved to another component/tool.

### 12.1. Removed settings

If a setting is removed, remove it from config templates and automation after replacing its behavior. An obsolete line can cause startup warnings/errors or create the illusion of an active setting that is actually ignored.

### 12.2. Renamed settings

Do not just rename it. Compare old and new units and semantics. If units changed from segment count to bytes, convert according to the actual WAL segment size.

### 12.3. Default changed

Record the source effective value, target default, planned explicit target value, rationale, and verification test.

If the organization wants to preserve old behavior, an explicit target setting may be needed. Do not blindly carry over old values when the new default fixes a bug or improves security.

### 12.4. Context changed

A setting may change from reloadable to restart-required or vice versa. Deployment automation must know when a restart is needed.

### 12.5. Sample config is not production config

The target's `postgresql.conf.sample` provides reference names and defaults. It does not replace an inventory of effective configuration, include files, `ALTER SYSTEM`, or service arguments.

## 13. Historical examples of compatibility changes

The following examples illustrate turning a release note entry into action. They apply only if your actual upgrade range spans the relevant versions.

### 13.1. PostgreSQL 12: `recovery.conf` removed

PostgreSQL 12 removed standby/recovery configuration via `recovery.conf`. Recovery parameters moved into server configuration, and selecting standby/recovery mode uses signal files such as `standby.signal` or `recovery.signal`.

Assessment:
- Search for `recovery.conf` in automation, images, Ansible/Chef/Puppet, scripts, and runbooks.
- Review standby creation and restore workflows.
- Move recovery settings into the appropriate server config.
- Create the right signal file for the intended mode.
- Test standby startup, archive restore, and PITR.

### 13.2. PostgreSQL 13: `wal_keep_segments` replaced by `wal_keep_size`

PostgreSQL 13 changed minimum WAL retention configuration from `wal_keep_segments` to `wal_keep_size`, expressed in storage size.

Assessment:
- Search for `wal_keep_segments` in config templates, Terraform/Ansible, scripts, and monitoring.
- Check the old cluster's segment size.
- Convert the value to bytes/MB/GB according to the new semantics.
- Verify standby outage window and WAL disk budget.
- Test catch-up and disk headroom.

### 13.3. How to use examples

Do not apply these two examples if your source/target does not traverse those major releases. Always open the official release notes for your specific versions to confirm exact behavior, migration instructions, and any exceptions.

## 14. System catalogs, monitoring views, and admin scripts

Many systems have monitoring queries directly dependent on:
- `pg_stat_activity`.
- `pg_stat_replication`.
- `pg_stat_wal_receiver`.
- `pg_stat_archiver`.
- `pg_stat_database`.
- `pg_stat_user_tables`.
- `pg_stat_io`.
- `pg_replication_slots`.
- `pg_class`, `pg_attribute`, `pg_proc`, `pg_namespace`.
- `information_schema`.

### 14.1. Column additions/removals

`SELECT *` queries against views can break exporter parsing when columns change. Prefer explicitly listing required columns.

### 14.2. Type changes

A driver/monitoring parser may assume a column is integer/text while the target returns a different type. Check schema and output types.

### 14.3. Privilege changes

A view/function may require different privileges or return restricted data. Test monitoring roles after upgrading; do not grant superuser just to make a dashboard work.

### 14.4. Internal catalog queries

If application logic relies on catalog internals, flag it as a high-risk dependency and evaluate replacing it with supported interfaces where feasible.

### 14.5. Exporter compatibility

Exporters may contain version-specific logic. Check the exporter compatibility matrix and test against the target server before upgrading production.

## 15. Extensions and modules

Extensions often have binaries/libraries tied to a PostgreSQL major version. An extension installed on the source may not yet have a package/build for the target.

Inventory:
- Extension name.
- Installed version.
- Schema.
- Owner.
- Shared preload requirements.
- Target package availability.
- Supported PostgreSQL major versions.
- Upgrade path.
- Dependencies.
- License/support status.
- Vendor release notes.

### 15.1. Extension inventory

```sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS extension_schema
FROM pg_extension
ORDER BY extname;
```

### 15.2. Checking update paths

For extensions supporting update paths, you can inspect:

```sql
SELECT *
FROM pg_extension_update_paths('extension_name');
```

Both the function and its output should be checked on the current version. Listing paths does not prove the target package is installed or that the upgrade will succeed.

### 15.3. Extension binaries

Confirm the target OS package includes shared libraries/control files/SQL scripts compatible with the target major version. Install binaries before running upgrade steps that require the extension, following extension and PostgreSQL documentation.

### 15.4. `shared_preload_libraries`

Extensions requiring preload must be configured on the target before starting if required by the migration/upgrade procedure. Verify exact library names, load order, dependencies, and restarts.

### 15.5. Extension SQL updates

Some extensions require `ALTER EXTENSION ... UPDATE` after the server upgrade. Confirm the target version, update path, and update order among interdependent extensions.

### 15.6. Do not check only extensions listed in `pg_extension`

A module can be preloaded without having an extension created in a database; a shared library can be invoked manually by a function. Inventory `shared_preload_libraries`, `session_preload_libraries`, `local_preload_libraries`, and function dependencies where appropriate.

## 16. Drivers, client libraries, and connection poolers

Check clients connecting to PostgreSQL:
- libpq.
- JDBC driver.
- psycopg/psycopg2.
- Npgsql.
- pgx.
- Node PostgreSQL clients.
- Go/Rust clients.
- ODBC drivers.
- BI/reporting connectors.
- PgBouncer and other poolers/proxies.

### 16.1. Wire protocol

The PostgreSQL protocol has broad compatibility, yet server features, authentication methods, data types, error fields, and protocol extensions may depend on client versions.

### 16.2. SCRAM and authentication

If the target or policy uses a new authentication method, verify that drivers support it, stored passwords are in a compatible format, `pg_hba.conf` rules align, poolers support the auth flow, and connection strings/secret rotation are tested.

### 16.3. TLS and certificates

Check TLS versions, cipher policies, CA chains, hostname verification, client certificates, and OpenSSL/runtime libraries. Test connections from both application containers and admin workstations.

### 16.4. Type mapping

Check driver mapping for numeric, UUID, JSON/JSONB, arrays, enums, ranges, timestamps, intervals, and custom types. A type/format change can cause serializers or ORMs to fail.

### 16.5. Connection poolers

PgBouncer and other poolers may need an updated version to understand authentication, protocol behavior, or server parameters. Test transaction pooling/session pooling, prepared statements, query cancellation, and failover reconnect.

### 16.6. Client tool versions

`psql`, `pg_dump`, `pg_restore`, `pg_basebackup`, and `pg_rewind` require separate version compatibility checks. Do not use old binaries without verifying target server support.

## 17. Authentication, roles, and security defaults

Release notes and security documentation may include changes to:
- Password encryption defaults.
- Authentication methods.
- TLS behavior.
- SCRAM support.
- Certificate validation.
- Role attributes.
- Privilege defaults.
- Row-level security.
- Security definer behavior.
- Extension security restrictions.
- Password/credential tooling.

### 17.1. Inventory `pg_hba.conf`

Record each rule: connection type, database, user, address, auth method, and order. The first matching rule determines the authentication method; a misordered new rule can break client connections.

### 17.2. Do not export password hashes

Compatibility assessment only needs auth methods, role attributes, and client capabilities. Never put password hashes/secrets into spreadsheets, Markdown, or tickets.

### 17.3. SCRAM readiness

If the target or policy uses SCRAM, verify that all drivers, poolers, monitoring tools, backup clients, and administrative tools can authenticate.

### 17.4. TLS validation

Test certificate expiry, SAN/hostname, CA rotation, client cert mapping, and minimum TLS version. Connecting from a laptop does not prove all application pods have the right trust store.

### 17.5. Least privilege

If the target changes privilege defaults or security checks, test application roles and maintenance roles. Avoid fixing errors by granting `SUPERUSER`.

## 18. Collation, locale, and encoding

Locale/collation is an area easily overlooked because it can depend on the OS and external libraries outside PostgreSQL.

### 18.1. Database encoding

Record the encoding of every database. Do not assume all databases share the same encoding or that the target can automatically convert encodings without data migration.

### 18.2. libc and ICU

Collation behavior can depend on libc/ICU versions. After an OS upgrade or PostgreSQL upgrade, sort order may change.

### 18.3. Collation version mismatch

A different collation version can cause indexes built on the old collation to no longer match the new ordering. Check collation metadata and actual versions on the target.

### 18.4. Rebuild affected indexes

If collation behavior changes, evaluate indexes and constraints using that collation. A `REINDEX` following the proper procedure may be needed. Only refresh the recorded collation version after handling dependent indexes per PostgreSQL guidance.

### 18.5. Pagination and uniqueness

Sort order changes can affect keyset pagination, `ORDER BY`, unique indexes, deduplication, and application code assuming string order.

### 18.6. Time zone database

OS/tzdata updates can alter historical or DST rules for certain timezones. Test timestamp conversions and scheduled jobs running across DST boundaries.

## 19. Planner and performance compatibility

Planner changes rarely cause queries to fail, but they can increase latency significantly.

Check:
- Join order/algorithms.
- Index selection.
- Cardinality estimates.
- Parallel queries.
- Partition pruning.
- CTE inlining/materialization.
- JIT.
- Statistics behavior.
- Memory settings.
- Sort/hash spills.
- Prepared statements/generic plans.

### 19.1. Capture a baseline

Before upgrading, capture query latency p50/p95/p99, calls/rows/blocks, `EXPLAIN ANALYZE BUFFERS` for critical queries in staging, `pg_stat_statements` snapshots, CPU, memory, I/O, and temp file usage.

### 19.2. Do not compare plan text mechanically

A plan may change while performing better. Compare runtime, rows, buffers, I/O, temp spills, and workload distribution.

### 19.3. `ANALYZE` after a major upgrade

After upgrading, statistics may need to be re-collected. Plan `ANALYZE` according to the upgrade method's instructions and cluster size. Assess autovacuum/analyze activity before opening full traffic.

### 19.4. Query regressions

Choose a representative workload including frequent queries, slow queries, batch jobs, reporting, DDL-heavy operations, and peak concurrency. A single query running fast in staging does not prove the whole workload is healthy.

### 19.5. Planner settings are not the default workaround

Do not disable planner features or alter global cost parameters just because of one query regression. Find the root cause, update statistics/indexes/query shape, and use scoped setting overrides when needed.

## 20. Data type, index, and storage compatibility

Read notes related to:
- Type representation/validation.
- Index access methods.
- Operator classes/families.
- Constraints.
- Partitioning.
- TOAST.
- Large objects.
- Generated columns.
- Identity columns.
- Sequence behavior.
- Vacuum/freeze.
- WAL/recovery.

### 20.1. Indexes and operator classes

Extensions or custom operator classes must be built/tested on the target. Verify index validity after migration and inspect collation-dependent indexes.

### 20.2. Partitioning

Test attach/detach, pruning, constraint exclusion, unique constraints, and partitioned index behavior. Planner improvements can change query plans.

### 20.3. Sequences and identity

Test sequence ownership, cache behavior, `nextval`/`currval`, identity insert rules, and migration scripts. Do not assume sequence state is restored identically to table data across all migration methods.

### 20.4. Large objects and custom types

Check serialization, backup/restore, extension dependencies, and application mapping. Ensure dump/restore or logical migration includes required objects.

## 21. Replication, backup, and recovery compatibility

An upgrade plan must evaluate:
- Physical replication.
- Logical replication.
- Replication slots.
- WAL level and WAL parameters.
- Archive command/library.
- Restore command.
- Backup software.
- `pg_basebackup`.
- `pg_upgrade`.
- `pg_dump`/`pg_restore`.
- `pg_rewind`.
- HA manager/DCS.
- Monitoring and alerting.

### 21.1. Physical replication across major versions

Do not assume physical streaming replication can connect freely between two major versions. Check version and migration method limitations for source/target.

### 21.2. Logical replication for migration

Logical replication can be used in some major upgrade/cutover designs, but requires checking publication/subscription support, DDL handling, sequence synchronization, large objects, extension objects, and conflict handling.

### 21.3. Replication slots

Check physical/logical slot compatibility, failover slot support, slot synchronization, and WAL retention parameters. Slots may need to be recreated or consumers reinitialized after migration.

### 21.4. Backup software

Confirm the backup tool supports the target major version, backup format, catalog migration, and restore version. Having a successful backup job is not enough; you must run a restore test.

### 21.5. `pg_upgrade`

Run `pg_upgrade --check` with the exact source/target binaries and data directories to detect incompatible conditions. This is not a full application compatibility test and does not replace extension/operational readiness checks.

### 21.6. Rollback backup

Retain source base backups/snapshots and WAL/archives per the retention plan. Once the target has accepted writes, reverting to the source requires a synchronization/reconciliation plan; a binary downgrade cannot be treated as a complete rollback.

## 22. Utilities and automation

Read release notes for:
- `pg_dump`/`pg_restore`.
- `pg_upgrade`.
- `pg_basebackup`.
- `pg_rewind`.
- `psql`.
- `vacuumdb`.
- `reindexdb`.
- `clusterdb`.
- `createdb`/`dropdb`.
- `initdb`.
- `pg_ctl`.
- `pg_config`.
- Backup vendor tools.

### 22.1. Binary paths

Automation may invoke binaries via `PATH` and accidentally run an old version after new packages are installed. Specify absolute paths or verify `--version`.

### 22.2. Option changes

Look for removed/renamed options, default output formats, exit codes, warnings, environment variables, and config file locations.

### 22.3. Output parsing

Scripts parsing text output can fail when formats/columns change. Prefer machine-readable output or verify version-specific output.

### 22.4. Shell and OS dependencies

An archive/backup script may rely on bash, tar, gzip, openssl, rsync, filesystem semantics, or cloud CLIs. Verify both tool versions and permission models on the target host.

## 23. Operating system and package compatibility

A PostgreSQL major version may change requirements for supported operating systems, CPU architectures, compiler/toolchain, OpenSSL/LDAP/Kerberos libraries, ICU/libxml/libxslt, Python/Perl/Ruby extensions, filesystem/kernel features, package repositories, and container base images.

### 23.1. Package sources

Record whether PostgreSQL packages come from the distro repository, the PostgreSQL community repository, a vendor image, or a custom build.

### 23.2. Extension packages

Extension package names may differ by major version or distro. Install the proper package for the target before running extension upgrades.

### 23.3. Container images

Pin image tag/digest, OS base, extension packages, CA certificates, and runtime dependencies. Do not use a floating `latest` tag for production upgrades.

### 23.4. System libraries

An extension may load on the source host yet fail on the target due to a missing shared library or ABI mismatch. Check package dependencies and startup logs.

## 24. Turning release notes into a compatibility register

A compatibility register is a structured list that turns each change into actionable work and verification evidence.

| Field | Content |
|---|---|
| ID | Unique item identifier |
| Source/target | Relevant version range |
| Release note | URL and section/heading |
| Change summary | Short description of the change |
| Change class | Removed, behavior, default, security, performance... |
| Component | Server, SQL, app, extension, driver, OS, tooling |
| Current usage | Evidence the system uses it |
| Target behavior | New behavior/version requirement |
| Impact | Affected components and business flows |
| Severity | Blocker, High, Medium, Low, Info |
| Action | Fix code/config/package/process |
| Owner | Responsible person/team |
| Validation | Test and expected result |
| Status | Open, Investigating, Planned, Fixed, Tested, Accepted |
| Evidence | PR, test run, config diff, approval |

### 24.1. Every item must have an action or a no-impact rationale

If a change could apply yet the system does not use it, document the usage searches performed, inventories inspected, lack of dependency found, confirmer, and evidence link.

Do not mark `N/A` without justification.

### 24.2. Split a single release note entry into multiple impacts

One change can affect application config, monitoring, backup automation, and staging. Create child actions or multiple register rows so each owner can act independently.

### 24.3. Do not lump disparate changes together

A single row saying "PostgreSQL 17 changes" is insufficient for review. Each item should point to a specific release note/behavior.

## 25. Severity and priority

| Level | Definition | Example |
|---|---|---|
| Blocker | Upgrade cannot complete or system cannot run safely | Required extension has no target build |
| High | Likely to break core workloads/security/DR | Incompatible client authentication |
| Medium | Requires targeted change or testing; workaround exists | Config default alters performance |
| Low | Minor impact, limited scope | Admin script needs output parser fix |
| Info | No current usage, kept for reference | Unused new feature |

### 25.1. Severity is not priority

Severity measures consequence if an issue occurs. Priority determines execution order based on timeline, dependencies, and resources.

### 25.2. Risk score

You can evaluate likelihood, impact, detectability, and mitigation. Avoid overly complex numeric formulas if they waste team time debating scores. Consistency in definition and clear ownership matter most.

### 25.3. Blockers must have exit criteria

For example: "Extension X has no target package yet" can only be closed once the package is installed, the extension updates cleanly, and workload tests pass.

## 26. Example compatibility register

Suppose a system has source `12.x` and target `13.x`. Below are illustrative historical entries:

| ID | Change | Usage evidence | Impact | Action | Validation |
|---|---|---|---|---|---|
| PG-COMP-01 | `recovery.conf` removed in PG12 | File present in standby provisioning | Incorrect standby bootstrap | Migrate recovery settings and signal-file logic | Provision new standby, restart, replay WAL |
| PG-COMP-02 | `wal_keep_segments` replaced by `wal_keep_size` in PG13 | Present in config templates | Old setting no longer valid | Convert units and update templates | Check effective setting, standby catch-up |
| PG-COMP-03 | Target extension package unconfirmed | `pg_extension` shows extension installed | Cluster may not start or extension fails to load | Confirm vendor build and upgrade path | Restore staging, update extension, smoke test |
| PG-COMP-04 | Planner behavior changed | Report query is in top workload | Latency may change | Capture baseline and run regression tests | Compare runtime, buffers, p95/p99 |
| PG-COMP-05 | Driver SCRAM support unconfirmed | App uses an older driver | Clients may fail to authenticate | Upgrade driver/pooler if needed | Connection tests from each app runtime |

### 26.1. Separate fact from impact

Item `PG-COMP-01` records the fact from the release notes. "Incorrect standby bootstrap" is only marked as a confirmed impact when the inventory finds provisioning relying on `recovery.conf`.

### 26.2. A row may involve multiple owners

DBAs may handle config, Platform handles images, and the Application team handles drivers. Use child tasks so each owner has a distinct deadline and evidence.

## 27. Step-by-step assessment process

1. **Freeze scope:** record source version, target version, environments, topology, and target upgrade window.
2. **Collect release notes:** assemble official URLs for all major versions in range, relevant minor releases, and extension/vendor release notes.
3. **Read migration notes:** flag items requiring pre-upgrade actions, config changes, removed settings, and upgrade constraints.
4. **Read remaining sections:** review server, SQL, utilities, client interfaces, security, performance, platform, and extension-related notes.
5. **Extract change candidates:** each candidate includes version, heading, summary, and source link. Include bug/security fixes that could affect workloads.
6. **Capture baseline:** export versions, settings, extensions, collations, roles/auth methods, replication, backup, and monitoring inventories.
7. **Map changes to usage:** search code/config, inspect database metadata, review query logs, interview owners, and check vendor matrices.
8. **Classify impact:** mark as confirmed, likely, no usage found, or unknown. Assign severity and owner.
9. **Define remediation:** write concrete actions: config migration, code change, driver upgrade, extension package, reindex, backup procedure, or test.
10. **Design validation:** each action must define test inputs, expected results, environment, and evidence location.
11. **Rehearse:** restore staging from a backup or production-like clone, execute the upgrade rehearsal, run regression tests, and measure performance.
12. **Review and sign-off:** DBAs, application owners, platform, security, backup/DR, and product owners approve relevant items.

## 28. Creating a release notes reading log

In addition to the compatibility register, maintain a reading log to prove the reviewed scope.

| Field | Example |
|---|---|
| Product | PostgreSQL |
| Source version | 14.9 |
| Target version | 17.4 |
| Release family reviewed | 15, 16, 17 |
| Minor notes | Source/target minor notes in scope |
| Sections | Migration, Server, SQL, Utilities, Client, Security |
| Reviewer | DBA/engineer |
| Review date | YYYY-MM-DD |
| URL | Official release notes |
| Result | Reviewed / Follow-up required |

If the target minor version changes from 17.4 to 17.5, update the reading log and read the newly added notes. Record exclusions and their rationale. For compliance, save the URL/version/heading and review date; internal snapshots can be archived per policy.

## 29. Compatibility test strategy

Organize testing by layer:

**Static review**
- Search for removed settings/APIs.
- Parse config templates.
- Check extension package matrices.
- Review driver versions.
- Review SQL/catalog dependencies.

**Database tests**
- Restore source backup onto staging.
- Upgrade staging using the planned method.
- Validate database startup and catalogs.
- Reindex/`ANALYZE` if needed.
- Run schema and data checks.

**Application tests**
- Connection/authentication.
- CRUD and transaction semantics.
- Stored procedures/triggers.
- ORM migrations.
- Batch/ETL/reporting.
- Error handling and retries.

**Operational tests**
- Backup and restore.
- WAL archive and PITR.
- Replication and failover.
- Monitoring/exporters.
- Connection pooler behavior.
- Restart/reboot and service automation.

**Performance tests**
- Critical query plans.
- Throughput and latency percentiles.
- CPU, memory, I/O, temp files.
- Concurrent workload and peak load.

## 30. Regression test design

A good test links directly to a compatibility item.

Each test should specify the requirement/behavior, source version expected result, target version expected result, input data and boundary cases, SQL/application operation, expected output/state, runtime threshold if applicable, test owner, and evidence/timestamp.

### 30.1. Test business behavior

Do not merely test whether SQL executes. Verify business outcomes: amounts, ordering, permissions, timezones, uniqueness, retry semantics, and transaction boundaries.

### 30.2. Test boundary values

Prioritize `NULL`, empty strings/arrays/JSON, large numeric values, timestamps near DST transitions, Unicode/collation edge cases, duplicate keys, long-running transactions, concurrent DDL/DML, large objects/large rows, and high-volume WAL.

### 30.3. Test error behavior

Applications may rely on SQLSTATE, constraint names, error message parsing, or retry policies. Test authentication, serialization, deadlock, cancellation, and connection reset errors.

### 30.4. Test extensions

Run extension-specific tests and representative functions/indexes. Verify extension versions, schema objects, shared libraries, and startup logs.

## 31. Performance comparison

Performance testing requires an equivalent workload.

### 31.1. Source baseline

Record query fingerprints, calls/rows, mean/p95/p99 latency, shared/local/temp blocks, CPU utilization, storage IOPS/latency, WAL bytes/sec, lock waits, and connection counts.

### 31.2. Target environment

Use equivalent hardware/storage/network or explicitly document differences. If staging is smaller than production, do not compare absolute latency directly.

### 31.3. `EXPLAIN`

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT ...
FROM ...
WHERE ...;
```

Only run `EXPLAIN ANALYZE` on safe queries in staging or in production under an approved procedure, since it executes the statement.

### 31.4. Query plan diffs

Record source and target plans, but evaluate based on actual runtime, rows, buffers, I/O, and workload. A different plan is not automatically a regression.

### 31.5. Cold/warm cache

Test both cold-start and steady-state when relevant. Do not let a single run dictate the result.

## 32. Staging upgrade rehearsal

The staging rehearsal should mirror production as closely as possible.

1. Create a representative backup/clone.
2. Mask sensitive data per policy if required.
3. Install target binaries and extension packages.
4. Run pre-upgrade checks.
5. Execute the upgrade using the planned method.
6. Handle extension upgrades and collation/index requirements.
7. Run `ANALYZE` per plan.
8. Run database/application regression tests.
9. Run backup, archive, replication, and failover tests.
10. Measure performance.
11. Record timing for each step and any issues.
12. Repeat after resolving blockers.

### 32.1. Rehearsals must be timed

Record durations for backup, `pg_upgrade`/dump restore, reindex, analyze, application smoke tests, and cutover. Use measured data to set the maintenance window.

### 32.2. Rehearsals must include a recovery path

Test restoring the source backup and recovering if the target fails to start. Do not practice only the happy-path upgrade.

### 32.3. Production-like configuration

Use the same config management, extension versions, service accounts, TLS, authentication, monitoring, and backup tools. A staging instance running only PostgreSQL core can miss critical dependencies.

## 33. Distinguishing compatibility assessment from upgrade method

Compatibility assessment answers "what needs to change and be tested?". Upgrade method answers "how do we move the database from source to target?".

Common methods:
- `pg_upgrade`.
- Dump/restore with `pg_dump`/`pg_restore`.
- Logical replication or migration tooling.
- Vendor/cloud-managed upgrade workflow.

### 33.1. `pg_upgrade`

Typically reduces migration time for large datasets by converting/reusing data files via supported mechanisms. Requires source/target binaries, extension compatibility, filesystem constraints, and pre-checks.

### 33.2. Dump/restore

Creates a logical dump and restores it into the target. Suitable when storage/encoding/schema changes are needed or `pg_upgrade` cannot be used, though duration depends on data size and index rebuilds.

### 33.3. Logical migration

Can reduce downtime, yet requires handling replication, DDL, sequences, large objects, extension objects, write freeze/cutover, and consistency. Not every workload is a fit.

### 33.4. Choose the method after the compatibility inventory

If an extension or data feature is unsupported by a method, mark it as a blocker and choose another approach. Do not select an upgrade method before knowing your dependencies.

## 34. Rollback and downgrade planning

Rollback must be designed before production cutover.

### 34.1. Keep the source recoverable

Retain source data directory/backup/snapshot, binaries, configuration, extension packages, and WAL/archives per policy.

### 34.2. Define the rollback boundary

Before the target accepts writes, reverting to the source can be relatively straightforward if the source was kept intact and cutover is incomplete. Once the target accepts writes, the source does not automatically receive new changes.

### 34.3. Do not treat binary downgrade as rollback

Do not start the target data directory with source binaries. PostgreSQL major upgrades do not provide a general downgrade by swapping binaries.

### 34.4. Reconciliation after writes

If you must revert to the source after the target has received writes, you need a pre-designed and tested synchronization/reconciliation strategy. This may require logical export, reverse replication if supported by topology/tooling, or recovery per plan. Never improvise during an incident.

### 34.5. Rollback criteria

Pre-define target startup failure, critical application test failure, data validation mismatch, authentication outage, performance outside SLA, non-working backup/replication, and cutover exceeding the maintenance window.

## 35. Change list for production cutover

Each item needs status and evidence.

**Pre-upgrade**
- Release notes review complete.
- Extension packages available.
- Drivers/poolers supported.
- Removed config settings replaced.
- Backup and restore verified.
- Source baseline captured.
- Target config reviewed.
- Maintenance window and owners confirmed.

**Upgrade execution**
- Source writes frozen/drained per method.
- Backup/snapshot verified.
- Target binaries/packages installed.
- Upgrade command/workflow completed.
- Extension SQL updates completed.
- Collation/index actions completed.
- `ANALYZE`/statistics plan executed.

**Post-upgrade**
- Server version confirmed.
- Database consistency checks complete.
- Roles/grants/authentication verified.
- Applications connected.
- Critical transactions pass.
- Query latency/throughput within SLA.
- Replication and archive healthy.
- Backup and PITR tested.
- Monitoring/alerts healthy.
- Old cluster retained per rollback policy.

## 36. Compatibility review meeting

An effective review requires representatives from DBA/database engineering, application owners, platform/infrastructure, security/IAM, backup/DR, SRE/Operations, data/BI/ETL owners, and extension/vendor owners.

### 36.1. Questions to answer

1. Have all intermediate major versions been reviewed?
2. Have minor/security notes in scope been reviewed?
3. Does every removed/deprecated setting have an owner?
4. Are extension packages and update paths confirmed?
5. Do drivers/poolers support the target?
6. Have locale/collation changes been evaluated?
7. Have query regressions been tested?
8. Have backup/PITR/replication/failover been rehearsed?
9. Are all blockers closed?
10. Who holds go/no-go decision authority?

### 36.2. Do not close items verbally

An item should be closed with evidence: test report, PR/config commit, vendor compatibility matrix, package build, restore log, or signed acceptance.

### 36.3. Intentional risk acceptance

If an item cannot be resolved before the upgrade, document the impact, workaround, owner, expiration date, and approver. Do not bury items in free-form notes.

## 37. Go/no-go criteria

An upgrade can be considered a go when:
- The release notes range is fully reviewed.
- No open blockers remain.
- High-risk items have remediation/testing/acceptance.
- Extension and client compatibility are confirmed.
- Backup restore/PITR evidence exists.
- Staging rehearsal succeeded.
- Performance meets SLA or has an approved mitigation.
- Cutover/rollback runbooks are reviewed.
- Owners and on-call coverage are confirmed.
- Monitoring and alerting are ready.

No-go when:
- Exact target version is unknown.
- No backup restore proof exists.
- A required extension is incompatible.
- Fencing/replication/DR behavior is unclear.
- Authentication path is untested.
- A blocker lacks an owner or mitigation.
- Staging rehearsal is incomplete.

## 38. Common mistakes when reading release notes

| Mistake | Consequence |
|---|---|
| Reading only target major release notes | Missing changes from intermediate major versions |
| Reading only new features | Skipping removed/default/behavior/security changes |
| Skipping minor release notes | Missing relevant bug/security fixes |
| Not inventorying current usage | Not knowing whether a change affects the system |
| Treating config file settings as effective values | Missing overrides from include/`ALTER SYSTEM`/CLI |
| Searching only source code | Missing dynamic SQL and runtime-generated queries |
| Ignoring extension vendors | Server upgrades cleanly but extensions fail to load |
| Ignoring client drivers/poolers | Applications fail to authenticate or type mapping breaks |
| Not checking collation/ICU | Ordering/index behavior changes |
| Assuming bug fixes do not affect compatibility | Applications depend on old buggy behavior |
| Testing only server startup | Failing to detect application/operational regressions |
| Not testing backup restore | Unable to prove the recovery path |
| Not recording evidence | Unable to review or audit decisions |
| Marking N/A without rationale | Unknown dependencies mistaken for no impact |
| Having no rollback boundary | Post-cutover incidents lack a clear recovery plan |

## 39. Compatibility register template

You can use the following Markdown structure as a starting point; in real projects, store it in an issue tracker or spreadsheet to manage owners/statuses.

| ID | Version | Release note / section | Change class | Component | Current usage/evidence | Impact | Severity | Action | Owner | Validation | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| PG-COMP-001 |  |  |  |  |  |  |  |  |  |  | Open |
| PG-COMP-002 |  |  |  |  |  |  |  |  |  |  | Open |
| PG-COMP-003 |  |  |  |  |  |  |  |  |  |  | Open |

### 39.1. Status conventions

- `Open`: not yet investigated.
- `Investigating`: verifying usage/impact.
- `Planned`: action/owner assigned.
- `Fixed`: code/config/package updated.
- `Tested`: validation passed with evidence.
- `Accepted`: risk accepted by an authorized owner.
- `Blocked`: cannot proceed due to dependency or missing support.

### 39.2. Impact confidence conventions

- `Confirmed`: usage evidence and tests exist.
- `Likely`: indicators exist but runtime usage is not yet proven.
- `No usage found`: searched across listed inventories.
- `Unknown`: insufficient data.

Do not use `No usage found` after searching only a single repository.

## 40. Release notes reading checklist

- [ ] Record exact source major/minor version.
- [ ] Record exact target major/minor version.
- [ ] List all intermediate major versions.
- [ ] Read Migration notes for each major version.
- [ ] Read Server changes.
- [ ] Read SQL/function/type/operator changes.
- [ ] Read configuration/default changes.
- [ ] Read system catalog and monitoring view changes.
- [ ] Read utilities/client interface changes.
- [ ] Read security/authentication/TLS changes.
- [ ] Read relevant planner/performance/bug fixes.
- [ ] Read platform/build requirements.
- [ ] Read extension/vendor release notes.
- [ ] Record URL, section, version, and review date.
- [ ] Record exclusions and rationale.

## 41. Inventory and compatibility checklist

- [ ] Server versions across all environments.
- [ ] Database encodings/locales/collations.
- [ ] Effective server configuration.
- [ ] `pg_hba` authentication methods.
- [ ] Extensions and target packages.
- [ ] `shared_preload_libraries` and related modules.
- [ ] Drivers, poolers, ORMs, and application runtimes.
- [ ] SQL, PL/pgSQL, dynamic SQL, and migration scripts.
- [ ] Direct catalog dependencies.
- [ ] Backup/restore tools and PITR archives.
- [ ] Replication slots/WAL/standbys/HA manager.
- [ ] Monitoring exporters and dashboards.
- [ ] OS, architecture, libraries, and package sources.
- [ ] Collation/ICU/tzdata dependencies.
- [ ] Jobs, cron, ETL, and BI clients.
- [ ] Owners and evidence for each dependency.

## 42. Validation and go/no-go checklist

- [ ] Every change candidate has an impact classification.
- [ ] Every affected component has an owner.
- [ ] Every blocker has remediation.
- [ ] Target config reviewed against effective values.
- [ ] Extensions installed/updated on staging.
- [ ] Client authentication tested.
- [ ] SQL/application regression suite passed.
- [ ] Critical query performance compared.
- [ ] Collation/index actions completed.
- [ ] Backup restore/PITR rehearsed.
- [ ] Replication/failover tested.
- [ ] Monitoring/alerts verified.
- [ ] Upgrade duration fits within the maintenance window.
- [ ] Rollback criteria and recovery path reviewed.
- [ ] Go/no-go owners signed off.

## 43. Official reference documentation

- [PostgreSQL Release Notes](https://www.postgresql.org/docs/release/): release notes across PostgreSQL versions.
- [PostgreSQL Documentation — Release Notes](https://www.postgresql.org/docs/current/release.html): release notes for the current documentation version.
- [PostgreSQL Documentation — Upgrading a PostgreSQL Cluster](https://www.postgresql.org/docs/current/upgrading.html): cluster upgrade methods.
- [PostgreSQL Documentation — pg_upgrade](https://www.postgresql.org/docs/current/pgupgrade.html): checking and upgrading with `pg_upgrade`.
- [PostgreSQL Documentation — pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html): logical backup and dump utility compatibility.
- [PostgreSQL Documentation — ALTER EXTENSION](https://www.postgresql.org/docs/current/sql-alterextension.html): updating extensions.
- [PostgreSQL Documentation — Collation Support](https://www.postgresql.org/docs/current/collation.html): locale/collation and version behavior.
- [PostgreSQL Documentation — Authentication](https://www.postgresql.org/docs/current/client-authentication.html): client authentication and `pg_hba`.
- [PostgreSQL Documentation — Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): baseline monitoring views.
- [PostgreSQL Documentation — Release Policy](https://www.postgresql.org/support/versioning/): support lifecycle and versioning policy.

For extensions, drivers, poolers, backup tools, and cloud services, also read each vendor's compatibility matrix/release notes. `/current/` paths change with the current documentation release; during an assessment, save the exact version-specific URLs reviewed.

## 44. Summary

Reading release notes is the starting point of a compatibility assessment. To turn that information into an executable upgrade plan, connect each change to your actual inventory, assess impact, assign owners, and require evidence.

1. **Version scope:** read notes for all intermediate major versions and the target, plus relevant minor/security notes.
2. **Classification:** identify removed, deprecated, behavior, default, SQL/API, catalog, security, performance, extension, utility, and platform changes.
3. **Inventory:** collect effective configs, database objects, extensions, drivers, application SQL, collations, backups, replication, and OS dependencies.
4. **Compatibility register:** record source links, usage evidence, target behavior, severity, actions, owners, validation, and status.
5. **Testing:** rehearse the upgrade on staging, run application regressions, query performance, backup/PITR, replication, and operational tests.
6. **Decision:** close blockers, document accepted risks, define rollback boundaries, and require go/no-go evidence.

A good compatibility list tells you which changes actually touch the system, who is responsible for handling them, how resolution is proven, and what conditions must be met before production is upgraded.
