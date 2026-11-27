# Verifying Data, Permissions, Performance, and Backups After a PostgreSQL Upgrade

A PostgreSQL upgrade is complete only when the new system runs properly, data remains intact, access permissions preserve their intended design, applications run stably, and backups are restorable. A successful server startup or an upgrade command returning exit code 0 proves only part of the process.

After an upgrade, verification must span multiple layers:

- **Platform and version:** the server runs the expected binary, major/minor version, extensions, and configuration.
- **Data and database objects:** schemas, rows, indexes, constraints, sequences, large objects, and metadata are intact.
- **Permissions and security:** roles, memberships, ownership, grants, default privileges, row-level security, and authentication remain accurate.
- **Performance:** planner statistics are refreshed, query plans are sound, latency/throughput show no regressions, and resource usage stays within bounds.
- **HA and backups:** replication works, WAL archiving continues, a fresh backup is taken, and a restore test succeeds.
- **Applications and operations:** clients/drivers are compatible, smoke tests pass, monitoring/alerting recognize the new server, and evidence is archived.

This lesson outlines post-upgrade verification workflows for both minor updates and major upgrades, including SQL queries, OS-level checks, baseline comparisons, and change-closure criteria.

~~~mermaid
flowchart TD
    A["Upgrade complete"] --> B["Verify version and cluster identity"]
    B --> C["Check extensions, catalogs, and configuration"]
    C --> D["Reconcile schemas and data"]
    D --> E["Verify roles, grants, and security"]
    E --> F["Analyze and evaluate query plans"]
    F --> G["Check HA, WAL, and replication"]
    G --> H["Take new backup"]
    H --> I["Restore test and application smoke tests"]
    I --> J{"All criteria met?"}
    J -->|"No"| K["Hold change closure, investigate / recover"]
    J -->|"Yes"| L["Archive evidence and sign-off"]
~~~

This lesson belongs to the **Upgrades** chapter, **Database Engine Relational PostgreSQL** module.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish post-upgrade verification for minor updates vs. major upgrades.
2. Confirm the PostgreSQL server, client tools, cluster, and endpoints run the expected versions.
3. Verify extension versions and shared library compatibility.
4. Verify schemas, tables, indexes, constraints, sequences, and large objects.
5. Reconcile data between source and target using counts, aggregates, and checks.
6. Detect invalid indexes, unvalidated constraints, and mismatched object ownership.
7. Verify roles, role memberships, ACLs, default privileges, and RLS.
8. Verify `pg_hba.conf`, TLS, authentication, and security-sensitive settings.
9. Check collation versions and handle `REINDEX` requirements when needed.
10. Refresh planner statistics after a major upgrade.
11. Compare query plans and performance against pre-upgrade baselines.
12. Verify physical replication, logical replication, slots, and WAL archiving.
13. Take a new post-upgrade backup and verify restore capability.
14. Run application smoke tests and verify driver compatibility.
15. Collect evidence with clear timestamps, context, and sources.
16. Establish acceptance criteria, rollback/recovery steps, and change closure.

## 2. How Do Minor Updates and Major Upgrades Differ?

Verification scope depends on the upgrade type.

### Minor Update

Minor updates typically increment the minor/release digits within the same major series—for example, from a PostgreSQL 16.x release to a newer 16.y release. These updates normally preserve on-disk data formats within the same major version, yet still require checking:

- The actual server binary was updated.
- Service restart succeeded.
- Extension packages/binaries are compatible.
- Configuration has no errors or unexpected parameter shifts.
- Application connections and queries function normally.
- Backup and WAL archiving continue.
- Logs show no new post-restart errors.

A minor update does not mean skipping checks. An update may fix a bug, patch a security flaw, or change behavior in a specific component.

### Major Upgrade

A major upgrade moves from one major version to another, such as PostgreSQL 15 to 16. Major upgrades can involve:

- Changes to catalogs and internal data structures.
- Changes to planner/executor behavior.
- Extensions requiring reinstallation or upgrades.
- Changes to default configurations.
- Changes to statistics views and system catalogs.
- Collation/library version differences.
- Driver/client compatibility shifts.
- Replication topology and logical replication behavior changes.
- Rebuilding backup chains compatible with the new cluster.

Common major upgrade methods:

| Method | How It Works | What to Verify |
| --- | --- | --- |
| `pg_upgrade` | Converts an existing cluster to new major-version binaries | Catalog compatibility, extension binaries, post-upgrade analyze |
| Dump/restore | Exports logical data and imports into a fresh cluster | Object completeness, data reconciliation, ownership, duration |
| Logical replication migration | Syncs data to a new cluster before cutover | Schema parity, replication lag, sequence state, final consistency |
| Managed service upgrade | Provider orchestrates the upgrade | Provider logs, version, extensions, endpoints, backups, and HA |

Do not apply the exact same detailed checklist blindly across every method. For instance, dump/restore demands thorough object and data reconciliation; `pg_upgrade` requires special care for extension binaries, collations, and statistics; logical replication requires handling final writes, sequences, and the cutover watermark.

## 3. Upgrade Completion Criteria

Before executing, define concrete acceptance criteria. Examples:

| Category | Sample Acceptance Criterion |
| --- | --- |
| Version | Server reports the approved major/minor version |
| Cluster identity | Connected to the right environment, database, and node |
| Database availability | All required databases accept connections |
| Objects | Required schemas, tables, views, functions, triggers, and indexes exist |
| Data integrity | Row counts/aggregates/checks match policy |
| Indexes | No invalid indexes outside documented exceptions |
| Constraints | Required constraints exist and are validated |
| Sequences | Sequence states do not lag behind existing data |
| Permissions | Roles, ownership, and effective privileges are accurate |
| Security | Authentication, TLS, HBA, RLS, and audit settings match |
| Performance | Latency/throughput stay within regression budget |
| Replication | Standbys/consumers are streaming with lag within bounds |
| Backups | New backup succeeds, archiving works, and restore test passes |
| Applications | Smoke tests and critical workflows succeed |
| Monitoring | Metrics/alerts recognize the new cluster |
| Evidence | Complete outputs, logs, metrics, and sign-off archived |

Thresholds such as latency regression, replication lag, and observation duration must be defined beforehand by service owners. Never apply one blanket threshold to all systems.

## 4. Confirming the Right Server and Cluster

Post-upgrade, first confirm you are connected to the right cluster. When routing through proxies, load balancers, or DNS aliases, never infer the physical node solely from the hostname used by applications.

~~~sql
SELECT
    version() AS server_version,
    current_setting('server_version') AS server_version_setting,
    current_setting('server_version_num') AS server_version_num,
    current_database() AS database_name,
    current_user AS database_user,
    inet_server_addr() AS server_address,
    inet_server_port() AS server_port,
    pg_postmaster_start_time() AS server_started_at,
    pg_is_in_recovery() AS is_standby;
~~~

Check additional runtime settings:

~~~sql
SHOW data_directory;
SHOW config_file;
SHOW hba_file;
SHOW port;
SHOW listen_addresses;
~~~

Path values may expose infrastructure layout; store them only in an access-controlled evidence repository.

### OS-Level Binary Checks

On Linux, inspect binary versions and paths:

~~~bash
postgres --version
psql --version
pg_ctl --version
pg_config --version
which postgres
which psql
~~~

A running service might execute a different binary than the first one found in `PATH`. Inspect the unit/service definition, running process command line, and package manager to verify the actual executable.

On Windows, inspect the PostgreSQL service configuration and executable path. On managed databases, use the console/API and provider events.

### Why Check Client Tools Separately?

The server may be upgraded while `psql`, `pg_dump`, `pg_restore`, `pg_basebackup`, or extension build tools remain on an older version. Certain client tools can connect to a different major server version, yet not every tool operation is compatible in every direction. Use the recommended tool versions for your upgrade/backup workflow.

## 5. Verifying All Databases

List databases:

~~~sql
SELECT
    datname,
    datallowconn,
    datistemplate,
    pg_get_userbyid(datdba) AS owner,
    pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database
ORDER BY datname;
~~~

Compare against the pre-upgrade inventory:

- Which databases must be retained?
- Which databases were created by applications or extensions?
- Did any owner change?
- Does `datallowconn` match expectations?
- Are encoding and locale accurate?
- Were template databases altered unexpectedly?

Check encoding and locales:

~~~sql
SELECT
    datname,
    pg_encoding_to_char(encoding) AS encoding,
    datcollate,
    datctype,
    datlocprovider,
    datcollversion
FROM pg_database
ORDER BY datname;
~~~

Some columns, such as locale provider/collation version, depend on major version. If a query is unsupported on a specific version, adjust to match the server's catalog and use `SHOW` or `psql` meta-commands accordingly.

### Connect to Every Database

A query succeeding in the `postgres` database does not prove business databases work. Runbooks must connect to each critical database and run at minimum:

- `SELECT current_database()`.
- Schema inventory check.
- Extension check.
- Application role privilege check.
- Representative smoke query.

## 6. Verifying Extensions

Extensions span both in-database metadata and filesystem shared libraries/control files. Major upgrades must ensure both sides align.

List installed extensions:

~~~sql
SELECT
    e.extname,
    e.extversion,
    n.nspname AS extension_schema,
    pg_get_userbyid(e.extowner) AS extension_owner
FROM pg_extension AS e
JOIN pg_namespace AS n
    ON n.oid = e.extnamespace
ORDER BY e.extname;
~~~

Compare against the pre-upgrade approved extension list.

Inspect extension versions available on the server:

~~~sql
SELECT
    name,
    default_version,
    installed_version
FROM pg_available_extensions
ORDER BY name;
~~~

If an extension is installed in the catalog while its shared library or control file is missing, calling functions or running upgrade scripts will fail.

### Checking Extension Packages

For self-managed PostgreSQL:

- Install matching extension packages for the new major version.
- Install shared libraries matching architecture and ABI.
- Verify control files and SQL upgrade scripts.
- Verify dependencies such as PostGIS, PL/Python, FDWs, or internal extensions.
- Restart if the extension requires preloading.
- Run `ALTER EXTENSION UPDATE` per documentation and plan.

Never blindly run `UPDATE` on every extension. Some extensions require multi-step upgrade paths or specialized procedures.

### `shared_preload_libraries`

~~~sql
SHOW shared_preload_libraries;
SHOW session_preload_libraries;
SHOW local_preload_libraries;
~~~

If an extension requires preloading, verify the module loaded cleanly after restart and startup logs show no library-load errors. Check every database individually because `CREATE EXTENSION` is database-scoped.

## 7. Checking Schemas and Database Objects

With dump/restore or logical migration, reconcile object inventories between source and target. With `pg_upgrade`, catalogs are converted directly, yet critical objects still merit verification.

### Tables and Partitions

~~~sql
SELECT
    schemaname,
    tablename,
    tableowner
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename;
~~~

Check partitions:

~~~sql
SELECT
    parent.relid::regclass AS partitioned_table,
    parent.isleaf,
    parent.level
FROM pg_partition_tree('public.events') AS parent
ORDER BY parent.level, parent.relid;
~~~

Replace `public.events` with an actual partitioned table. If your version lacks `pg_partition_tree`, query `pg_inherits` and related catalogs.

### Views and Materialized Views

~~~sql
SELECT
    schemaname,
    viewname,
    viewowner
FROM pg_views
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, viewname;
~~~

Verify materialized views exist and have been refreshed if required by the migration/restore procedure.

### Functions and Procedures

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS routine_name,
    p.prokind,
    pg_get_userbyid(p.proowner) AS owner,
    p.prosecdef AS security_definer
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, p.proname;
~~~

Test critical functions/procedures via safe smoke calls. A routine can exist in catalogs yet fail at runtime due to extension, `search_path`, type, or permission shifts.

### Triggers

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    t.tgname AS trigger_name,
    t.tgenabled
FROM pg_trigger AS t
JOIN pg_class AS c
    ON c.oid = t.tgrelid
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE NOT t.tgisinternal
ORDER BY n.nspname, c.relname, t.tgname;
~~~

Compare trigger enabled states against baseline. Never manually enable triggers intentionally disabled by the application or migration.

## 8. Detecting Invalid or Unready Indexes

An index can exist in the catalog while being invalid for planner use—for example after a failed or interrupted `CREATE INDEX CONCURRENTLY`.

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indrelid::regclass AS table_name,
    i.indisvalid,
    i.indisready,
    i.indislive
FROM pg_index AS i
WHERE NOT i.indisvalid
   OR NOT i.indisready
   OR NOT i.indislive
ORDER BY i.indrelid::regclass::text;
~~~

Investigate any results. Certain invalid indexes may be known intentional exceptions during special workflows; document them explicitly. Otherwise, remediate per runbook: inspect build logs, check dependencies, and safely recreate or drop the index.

### Checking Important Indexes

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename, indexname;
~~~

Compare definitions, uniqueness, predicates, included columns, tablespaces, and storage parameters. Matching index names alone is insufficient.

## 9. Verifying Constraints

List unvalidated constraints:

~~~sql
SELECT
    conrelid::regclass AS table_name,
    conname,
    contype,
    convalidated,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE NOT convalidated
ORDER BY conrelid::regclass::text, conname;
~~~

A `NOT VALID` constraint may be intentional by design—for instance, added to enforce new rows before validating historical data. Do not blindly validate every constraint without assessing runtime, locking, and data quality.

Verify critical constraints:

- Primary keys.
- Unique constraints.
- Foreign keys.
- Check constraints.
- Exclusion constraints.

With dump/restore, verify both constraint definitions and data compliance. With migrations, verify newly added constraints were validated as planned.

## 10. Verifying Sequences and Identity Columns

Sequence state is easily overlooked in dump/restore or logical replication workflows. If a sequence lags behind the table's maximum key, the next `INSERT` can trigger a duplicate key error.

List sequences:

~~~sql
SELECT
    schemaname,
    sequencename,
    data_type,
    start_value,
    min_value,
    max_value,
    increment_by,
    cycle,
    last_value
FROM pg_sequences
ORDER BY schemaname, sequencename;
~~~

`last_value` may be `NULL` if the sequence has not been called in the current state or if the user lacks viewing privileges per version semantics. Do not misinterpret `NULL` as an upgrade error.

### Reconciling Sequences Against Data

For sequences bound to `serial`/`identity` columns, locate the sequence with `pg_get_serial_sequence`:

~~~sql
SELECT pg_get_serial_sequence('public.orders', 'order_id');
~~~

Then compare sequence state against the table's maximum value. Account for negative increments, cycling, caching, and active writers. Never call `setval` casually in production, as it can race with active writers.

If sequences must be synced after a logical migration, perform it inside the cutover window after stopping writers, targeting the exact sequence and `setval` arguments. Record old/new values and test with an appropriate transaction.

### Identity Columns

Identity columns use internal sequences with different metadata from `serial`. Inspect `information_schema.columns` and `pg_attribute`/`pg_depend` when deeper checks are needed. Test generated identity behavior via an insert test in staging or a rolled-back transaction in a safe environment.

## 11. Large Objects and Out-of-Table Data

PostgreSQL large objects are managed separately from regular table rows. Dump/restore must include large objects if applications rely on them.

Check large object count:

~~~sql
SELECT count(*) AS large_object_count
FROM pg_largeobject_metadata;
~~~

Compare against the source baseline. You may also need to check large object ownership and ACLs, not just count.

External data outside the database—such as filesystem files, object storage, foreign data sources, secrets, and external services—does not move automatically merely because the PostgreSQL cluster was upgraded. Verify those dependencies against the application inventory.

## 12. Reconciling Data Between Source and Target

Comparison methods depend on the upgrade path.

### With `pg_upgrade`

`pg_upgrade` converts the cluster via physical/catalog upgrade mechanics rather than dumping and restoring every row. Even so, verify database/object inventories, table readability, constraints, indexes, and application behavior.

### With Dump/Restore or Logical Migration

Use a consistent cutover point. If the source keeps accepting writes while the target is inspected, counts will diverge solely from new transactions.

Common checks:

- Row counts per table/partition.
- Min/max primary keys.
- Min/max timestamps.
- Aggregates on key business columns.
- Duplicate key checks.
- NULL/range checks.
- Referential integrity.
- Checksums per key range or partition.
- Large object counts.

Example:

~~~sql
SELECT
    count(*) AS row_count,
    min(order_id) AS min_order_id,
    max(order_id) AS max_order_id,
    min(created_at) AS first_order,
    max(created_at) AS last_order,
    sum(total_amount) AS total_amount
FROM public.orders;
~~~

Duplicate check:

~~~sql
SELECT order_id, count(*) AS occurrences
FROM public.orders
GROUP BY order_id
HAVING count(*) > 1
LIMIT 100;
~~~

NULL/range check:

~~~sql
SELECT
    count(*) FILTER (WHERE order_id IS NULL) AS null_ids,
    count(*) FILTER (WHERE total_amount < 0) AS negative_amounts
FROM public.orders;
~~~

### Do Not Rely Solely on Row Counts

Two tables can share identical row counts while holding different values. For critical data, compare aggregates/checksums across key ranges or partitions and document the method. Full-table hashing consumes CPU/I/O and requires a consistent snapshot.

### Ensure a Consistent Snapshot

Whenever possible, pause writes or use an engineered snapshot/watermark mechanism. With logical replication, wait for the subscription to catch up, record the final LSN/watermark, and coordinate cutover so no writes are missed.

## 13. Verifying Ownership

After dump/restore, object ownership may differ if roles were not created or mapped properly.

Check table owners:

~~~sql
SELECT
    schemaname,
    tablename,
    tableowner
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
ORDER BY schemaname, tablename;
~~~

Check database owners:

~~~sql
SELECT
    datname,
    pg_get_userbyid(datdba) AS database_owner
FROM pg_database
ORDER BY datname;
~~~

Check schema owners:

~~~sql
SELECT
    nspname AS schema_name,
    pg_get_userbyid(nspowner) AS schema_owner
FROM pg_namespace
WHERE nspname NOT LIKE 'pg_%'
  AND nspname <> 'information_schema'
ORDER BY nspname;
~~~

Compare against the ownership baseline and role mappings. Never run `REASSIGN OWNED` blindly without understanding scope; it affects all objects owned by that role in the current database.

## 14. Verifying Roles and Attributes

~~~sql
SELECT
    rolname,
    rolsuper,
    rolinherit,
    rolcreaterole,
    rolcreatedb,
    rolcanlogin,
    rolreplication,
    rolbypassrls,
    rolconnlimit,
    rolvaliduntil
FROM pg_roles
ORDER BY rolname;
~~~

Verify key role categories:

- Superuser/admin roles.
- Application login roles.
- Read-only/reporting roles.
- Replication roles.
- Backup/monitoring roles.
- Migration/deployment roles.
- Locked or expired roles per policy.

A role existing does not guarantee its password/secret was synced properly. Never export password hashes into evidence. Verify authentication via secret management and safe login tests.

### Role Memberships

~~~sql
SELECT
    member.rolname AS member_role,
    granted.rolname AS granted_role,
    grantor.rolname AS grantor_role,
    m.admin_option
FROM pg_auth_members AS m
JOIN pg_roles AS member
    ON member.oid = m.member
JOIN pg_roles AS granted
    ON granted.oid = m.roleid
JOIN pg_roles AS grantor
    ON grantor.oid = m.grantor
ORDER BY member.rolname, granted.rolname;
~~~

Role membership semantics and optional columns may vary by version. Confirm required memberships and test inheritance/`SET ROLE` behavior used by applications.

## 15. Verifying Grants and Effective Privileges

PostgreSQL enforces multiple privilege layers:

- Database `CONNECT`/`TEMP`/`CREATE`.
- Schema `USAGE`/`CREATE`.
- Table `SELECT`/`INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`/`REFERENCES`/`TRIGGER`.
- Sequence `USAGE`/`SELECT`/`UPDATE`.
- Function `EXECUTE`.
- Type `USAGE`.
- Tablespace `CREATE`.
- Role memberships and ownership.

### Table Grants

~~~sql
SELECT
    grantee,
    table_schema,
    table_name,
    privilege_type,
    is_grantable
FROM information_schema.role_table_grants
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, grantee, privilege_type;
~~~

`information_schema` views may show only grants visible to the current user. For comprehensive audits, inspect catalogs/ACLs using an appropriately privileged audit role.

### Effective Privilege Checks

~~~sql
SELECT
    has_database_privilege('orders_app', 'sales', 'CONNECT') AS can_connect,
    has_schema_privilege('orders_app', 'public', 'USAGE') AS can_use_public,
    has_table_privilege('orders_app', 'public.orders', 'SELECT') AS can_read_orders,
    has_table_privilege('orders_app', 'public.orders', 'INSERT') AS can_insert_orders;
~~~

Substitute your environment's roles, databases, and objects. Effective privilege functions verify actual permissions after evaluating memberships and ownership in the test context.

### Default Privileges

Default privileges govern objects created in the future. A restore may preserve existing grants while missing default privileges for newly created objects.

Check:

~~~sql
SELECT
    defaclrole::regrole AS owner_role,
    defaclnamespace::regnamespace AS schema_name,
    defaclobjtype,
    defaclacl
FROM pg_default_acl
ORDER BY owner_role, schema_name, defaclobjtype;
~~~

Compare default privileges by creator role and schema. `ALTER DEFAULT PRIVILEGES` applies per executing role and target role/schema, so verify by creating a test object in staging or an appropriate transaction.

## 16. Verifying Row-Level Security and Security Settings

### Row-Level Security

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relrowsecurity AS rls_enabled,
    c.relforcerowsecurity AS rls_forced
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname;
~~~

Check policies:

~~~sql
SELECT *
FROM pg_policies
ORDER BY schemaname, tablename, policyname;
~~~

Test using the actual application role. Superusers and `BYPASSRLS` roles bypass RLS, so testing as an admin does not prove application roles are properly constrained.

### Security Definer Functions

Functions defined with `SECURITY DEFINER` execute with the owner's privileges. Inspect these routines, owners, and `search_path`:

~~~sql
SELECT
    n.nspname,
    p.proname,
    pg_get_userbyid(p.proowner) AS owner,
    p.proconfig
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE p.prosecdef
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, p.proname;
~~~

Confirm a safe `search_path` per policy and ensure owning roles do not hold unnecessarily broad privileges.

### HBA and TLS

Inspect rules:

~~~sql
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
~~~

Inspect TLS settings:

~~~sql
SHOW ssl;
SHOW ssl_min_protocol_version;
SHOW ssl_cert_file;
SHOW ssl_ca_file;
~~~

Certificate paths can be sensitive. Test TLS connections from application and monitoring clients and verify certificate chain/hostname validation. Do not rely solely on `SHOW ssl = on`.

## 17. Checking Collation and Locale Versions

A major upgrade or OS/ICU/glibc update can alter collation behavior. Changed collations can change text comparison/sorting order and impact collation-dependent indexes.

Check database collation versions:

~~~sql
SELECT
    datname,
    datcollate,
    datctype,
    datlocprovider,
    datcollversion,
    pg_database_collation_actual_version(oid) AS actual_collation_version
FROM pg_database
ORDER BY datname;
~~~

Check collations in the current database:

~~~sql
SELECT
    n.nspname AS schema_name,
    c.collname,
    c.collprovider,
    c.collversion,
    pg_collation_actual_version(c.oid) AS actual_version
FROM pg_collation AS c
JOIN pg_namespace AS n
    ON n.oid = c.collnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.collname;
~~~

Some columns/functions depend on major version and locale provider. Adjust the query if the running server lacks a specific column.

### When Collation Versions Differ

Never ignore a collation version mismatch warning. Follow these steps:

1. Identify the provider (`libc`/ICU) and before/after versions.
2. List affected indexes and collation-dependent objects.
3. Plan `REINDEX` for affected objects.
4. Choose a rebuild approach matching lock/downtime constraints.
5. Refresh the recorded collation version only after rebuilding affected objects per documentation.
6. Re-run checks and archive evidence.

`REFRESH VERSION` commands only update recorded metadata; they do not rebuild indexes automatically. Refreshing too early masks mismatches while old index orderings remain broken.

## 18. Verifying Post-Upgrade Configuration

Compare effective configuration against baselines and configuration management.

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

Focus on:

- `max_connections` and reserved slots.
- `shared_buffers`, `work_mem`, `maintenance_work_mem`.
- WAL/checkpoint settings.
- logging settings.
- autovacuum.
- SSL/authentication.
- replication settings.
- planner cost constants.
- locale/collation.
- preload libraries.
- extension-specific settings.

### Detecting Configuration Errors

~~~sql
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
~~~

Some unapplied lines reflect legitimate overrides from later files, command-line flags, or sessions. Check source and precedence before treating an unapplied line as an error.

### New Parameters and Changed Defaults

Major upgrades may introduce settings or alter defaults. Comparing the full `pg_settings` table can surface many legitimate differences. Review settings affecting durability, memory, the planner, authentication, and logging per release notes.

Never copy an old `postgresql.conf` verbatim into a new major version without review. Parameters may be renamed, removed, or have altered semantics.

## 19. Refreshing Planner Statistics After a Major Upgrade

Planner statistics may not transfer or may no longer accurately represent the new cluster. After `pg_upgrade`, run analyze as instructed in `pg_upgrade` output.

Example:

~~~bash
vacuumdb --all --analyze-in-stages
~~~

This analyzes databases progressively so the planner gets basic statistics quickly before refining detail. Run with an appropriately privileged role and client tools matching the server version.

On large databases, analyze can generate significant I/O and CPU load. Monitor progress, system load, and application latency. Do not open full peak workload if the system lacks headroom.

### Verifying Statistics

~~~sql
SELECT
    schemaname,
    relname,
    last_analyze,
    last_autoanalyze,
    n_live_tup,
    n_mod_since_analyze
FROM pg_stat_user_tables
ORDER BY n_mod_since_analyze DESC;
~~~

Analyze timestamps may be `NULL` if a table has not been analyzed yet. Evaluate key tables according to query workload rather than expecting identical timestamps on every table.

## 20. Verifying Query Plans and Performance

A new major version can change the planner, executor, and costing behavior. Queries fast on the old version might select different plans.

For critical queries, capture before/after plans:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, WAL, SETTINGS)
SELECT
    order_id,
    created_at,
    total_amount
FROM public.orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 50;
~~~

`EXPLAIN ANALYZE` executes the statement. For DML, it modifies data unless run in staging or rolled back cleanly. Never run heavy ad-hoc benchmarks on production during peak hours.

Compare:

- Plan nodes and join strategies.
- Estimated rows vs. actual rows.
- Execution time.
- Shared/local/temp buffers.
- I/O timings when enabled.
- Sort methods and disk spills.
- Hash batches.
- Rows removed by filters.
- WAL generated.
- Parallel workers.
- Settings influencing the plan.

A different plan is not automatically a regression. Compare latency and resource usage across a representative workload.

## 21. Using `pg_stat_statements` to Compare Workloads

If the extension is installed and preloaded properly:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_read,
    temp_blks_written,
    left(query, 180) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Column names may vary across extension versions. Inspect the actual `pg_stat_statements` schema post-upgrade.

### Before/After Comparison

- Save pre-upgrade snapshots if available.
- Record stats reset timestamps.
- Compare matching observation windows.
- Normalize by call counts and workload volume.
- Check p95/p99 from APM if the extension lacks percentiles.
- Distinguish cache warm-up from persistent regressions.
- Never compare counters if an unnoticed reset occurred between snapshots.

`pg_stat_statements` may need resetting or reinitializing per policy. Do not reset stats immediately after upgrading if baseline comparison evidence is still needed.

## 22. Warm-Up and Cache Behavior

After a restart or upgrade, `shared_buffers` and the OS page cache start colder than before. Initial queries may run slower while reading pages from storage.

Controlled warm-up practices:

- Run representative read-only queries.
- Use `pg_prewarm` if installed and needed.
- Ramp application pools gradually.
- Monitor storage latency and cache hit ratios.
- Avoid warm-up load exceeding capacity.

Never judge steady-state performance from the first few minutes after restart. Conversely, never dismiss a genuine regression as "just cold cache." Define the observation window upfront.

## 23. Checking Database Health and Transaction Behavior

### Long-Running Transactions

~~~sql
SELECT
    pid,
    usename,
    datname,
    application_name,
    state,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 160) AS query_sample
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Check for long-running transactions, `idle in transaction` sessions, and blocked sessions.

### Locks

~~~sql
SELECT
    a.pid,
    a.usename,
    a.application_name,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    left(a.query, 160) AS query_sample
FROM pg_stat_activity AS a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0;
~~~

Syntax and columns may differ across versions. Watch lock contention throughout the observation window and check server logs for deadlocks.

### Database Statistics

~~~sql
SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    temp_files,
    temp_bytes,
    deadlocks,
    stats_reset
FROM pg_stat_database
ORDER BY datname;
~~~

Use counters to compare deltas over equal time windows. Never draw conclusions from cumulative totals without checking `stats_reset` and workload volume.

## 24. Verifying Replication and HA

After upgrading, verify the topology matches your plan.

On the primary:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication
ORDER BY application_name;
~~~

On standbys:

~~~sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn;
~~~

Check the WAL receiver:

~~~sql
SELECT
    status,
    sender_host,
    sender_port,
    received_tli,
    written_lsn,
    flushed_lsn,
    latest_end_lsn,
    last_msg_receipt_time
FROM pg_stat_wal_receiver;
~~~

Verify:

- Expected number of standbys.
- Replication state.
- Sync state.
- LSN progress.
- Replication lag.
- Network errors.
- Replication slots.
- HA manager / DCS health.
- Fencing / leader state if orchestrated.

### Replication Slots

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_type, slot_name;
~~~

Logical and physical slot handling can vary by version and upgrade method. Never assume all logical slots, subscriptions, or downstream consumers resume automatically. Verify consumer status, slot validity, restart LSN, and WAL retention.

## 25. Verifying Logical Replication and Subscriptions

If using logical replication, check publisher and subscriber:

~~~sql
SELECT
    subname,
    subenabled,
    subslotname,
    subpublications
FROM pg_subscription
ORDER BY subname;
~~~

On the subscriber, check worker status and subscription stats per version:

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

Verify:

- Subscription is enabled.
- Apply workers are running.
- Replication slot exists and is properly active.
- Table synchronization finished.
- No persistent apply errors exist.
- Schemas on both sides match.
- Sequence values were synced separately at cutover when needed.
- Any conflicts or data drift are investigated.

Logical replication does not automatically replicate objects such as roles, DDL, sequences, or large objects. Those require separate workflows.

## 26. Verifying WAL Archiving

Check configuration:

~~~sql
SHOW archive_mode;
SHOW archive_command;
SHOW wal_level;
~~~

Check statistics:

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

After a major upgrade, archive destinations, paths, permissions, or tool integrations may change. Confirm new WAL segments generated post-upgrade archive cleanly. Do not rely on a pre-upgrade archive timestamp.

If using an archive module or dedicated backup tool, check its logs/metadata and run a restore/PITR test in an isolated environment.

## 27. Taking a New Backup After Upgrading

A cluster after a major upgrade represents a new operational state. Take a fresh backup using tooling compatible with the new major version rather than relying solely on old backups.

The new backup should include:

- Physical base backup compatible with the new version.
- WAL archive following the backup timestamp.
- Backup metadata/manifest.
- Required PostgreSQL configuration.
- Extension packages and version inventory.
- Roles/global objects per procedure.
- Tablespace mappings.
- TLS/certificates/secrets managed in a secret manager per policy.
- HA manager configuration and service inventory where needed.

### Why Are Old Backups Still Important?

Pre-upgrade backups may be your recovery path back to the old cluster. Retain them per retention and rollback policies. Never delete old backups simply because a new backup ran; track when the rollback window closes and maintain independent recoverability.

### Physical vs. Logical Backups

- Physical backups suit full-cluster restores on the same major version and WAL-based recovery.
- Logical dumps help with portability, object-level recovery, and data checks.
- Configuration/role backups may require separate steps depending on tooling.
- Managed services define their own snapshot and automated backup semantics.

Read your backup tool and provider documentation to confirm support for the new PostgreSQL major version.

## 28. Post-Upgrade Restore Testing

A completed backup does not prove restorability. Execute a restore drill in an isolated environment.

Procedure:

1. Select a post-upgrade backup ID.
2. Verify manifest/checksums and WAL coverage.
3. Prepare the matching target PostgreSQL version.
4. Restore onto an isolated test host/volume.
5. Run recovery to the desired target.
6. Verify PostgreSQL startup and database inventory.
7. Run object/data integrity checks.
8. Verify extensions and roles.
9. Run application smoke tests if appropriate.
10. Measure restore duration and achieved recovery point.
11. Archive logs, output, and evidence.

### Actual RPO and RTO

- Actual RPO is measured by the gap between the recovery point and the incident/policy requirement.
- Actual RTO is elapsed time from recovery start until the service is verified operational.

Record measurements from the restore test rather than merely copying target values from design docs.

## 29. Backups and `pg_upgrade`

If using `pg_upgrade`, retain the old cluster per plan until acceptance criteria pass and the rollback window expires.

Important notes for hard-link mode:

- `pg_upgrade` can use hard links to reduce migration time and copy space.
- Once the new cluster starts writing, hard-linked files can share inodes with the old cluster.
- After the new cluster runs and writes data, the old cluster is no longer a safe independent fallback.
- Never start the old cluster as if it were an untouched backup after a hard-link upgrade has begun operating.

When independent fallback is required, use copy/clone mode or planned backups. Read `pg_upgrade` docs for your exact version and record the exact transfer mode used.

### Do Not Treat `pg_upgrade --check` as Post-Upgrade Validation

`--check` verifies select pre-upgrade conditions. It does not prove post-upgrade data, extensions, applications, or backups are healthy.

## 30. Checking Application and Client Compatibility

Post-upgrade, run smoke tests using the exact application roles and production connection paths.

Areas to verify:

- Driver version and wire protocol.
- Authentication method and TLS.
- Prepared statements.
- Parameter types/casting.
- Date/time and timezone handling.
- Numeric/JSON/array/range types.
- Transaction isolation behavior.
- Error handling and retries.
- Stored procedures/functions.
- Extensions/FDWs.
- ORM-generated SQL.
- Connection pool reset/reconnect.
- Read/write routing.
- Batch jobs, scheduled jobs, and background workers.

### Smoke Tests

Sample operations to verify in the application:

1. Open a connection as the service role.
2. Run a health query.
3. Read a known business record.
4. Write a test record that can be rolled back or cleaned up.
5. Verify transaction commit and rollback.
6. Run critical queries involving joins, indexes, and filters.
7. Call critical functions/procedures.
8. Check queue/worker pipelines or ETL if applicable.
9. Confirm application logs show no new errors.
10. Confirm request latency and error rates stay within bounds.

Do not test solely as superuser or admin `psql`. Applications must be validated with real roles, drivers, network paths, and connection pools.

## 31. Checking Timezone, Encoding, and Data Type Behavior

Inspect server, database, and client settings:

~~~sql
SHOW server_encoding;
SHOW client_encoding;
SHOW timezone;
SHOW DateStyle;
SHOW lc_messages;
SHOW lc_monetary;
SHOW lc_numeric;
SHOW lc_time;
~~~

Compare against baselines and application requirements.

Environmental changes can affect:

- Timestamp rendering and timezone conversions.
- Date parsing.
- Text sorting and case folding.
- Numeric formatting.
- Encoding conversion.
- Collation-sensitive uniqueness/ordering.
- Client driver type mappings.

Test edge values: timestamps near midnight/DST if relevant, Unicode, numeric precision, JSON, arrays, and NULLs.

## 32. Checking Prepared Statements and Query Behavior

Drivers and ORMs using prepared statements can be affected by planner statistics, parameter types, or plan caching.

Verify:

- Parameter binding works properly.
- Prepared statements do not lock onto poor generic plans.
- `search_path` and schema resolution match expectations.
- Function/operator overload resolution picks expected candidates.
- Transaction isolation introduces no regressions.
- Query/statement timeouts did not shift unexpectedly.

When using `EXPLAIN` to inspect parameterized queries, reproduce with the application's exact role, `search_path`, and parameter types. Admin `psql` sessions may pick different plans.

## 33. Checking Connection Limits and Pools

~~~sql
SHOW max_connections;
SHOW superuser_reserved_connections;
~~~

Some versions introduce additional reserved slots for specialized roles. Check actual parameters and connection privileges per version.

Count active sessions:

~~~sql
SELECT
    datname,
    usename,
    application_name,
    state,
    count(*) AS sessions
FROM pg_stat_activity
GROUP BY datname, usename, application_name, state
ORDER BY sessions DESC;
~~~

Verify:

- Connection pools point to the new endpoint.
- Pool sizes stay within capacity.
- Applications reconnect cleanly after restarts.
- No stale sessions remain connected to the old endpoint.
- Retries/backoff do not trigger connection storms.
- Reserved administrative access remains available.

## 34. Checking Monitoring and Alerting

Post-upgrade, dashboards may break if system views or column names changed. Older exporters may run queries incompatible with new catalogs.

Verify:

- PostgreSQL exporter version.
- SQL queries and custom collectors.
- Metric names and labels.
- Dashboard panels.
- Alert rules.
- Log parsers/schemas.
- HA manager metrics.
- Backup/restore monitoring.
- Replication lag alerts.
- Disk/WAL/connection alerts.

Run an end-to-end test: trigger or observe a suitable event, confirm metrics/logs appear, dashboards render, and alert routing works. Confirming the exporter process is running is not enough.

## 35. Inspecting Post-Upgrade Logs

Review logs from startup and the observation window for:

- Removed, renamed, or ignored configuration parameters.
- Extension library load failures.
- Collation version warnings.
- Invalid indexes or constraints.
- Authentication/TLS failures.
- Query errors or SQLSTATE shifts.
- Deadlocks and lock waits.
- WAL/archiving errors.
- Replication disconnects.
- Checkpoint/I/O warnings.
- Autovacuum issues.
- Crashes, `PANIC`s, or recovery loops.

Compare against pre-upgrade baselines. Certain `INFO`/`LOG` messages may change across versions; focus on new errors, rising frequencies, and operational impact.

## 36. Checking Background Maintenance

Post-upgrade, confirm routine maintenance continues:

- Autovacuum and autoanalyze.
- Checkpoints.
- WAL archiving.
- Backup jobs.
- Replication.
- Scheduled jobs.
- Statistics collection.
- Monitoring collectors.

Inspect autovacuum progress:

~~~sql
SELECT
    pid,
    datname,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed
FROM pg_stat_progress_vacuum;
~~~

Check table statistics:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_analyze,
    last_autoanalyze,
    last_vacuum,
    last_autovacuum
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;
~~~

Statistics are estimates and can reset. Compare across matching observation windows.

## 37. Differences Specific to Each Upgrade Method

### `pg_upgrade`

Focus on:

- Binary paths and cluster identity.
- Extension shared libraries and SQL update scripts.
- Collation version mismatches.
- Statistics needing re-analyzing.
- Invalid indexes/constraints.
- Config file differences and removed parameters.
- Logical replication slots/subscriptions per version support.
- Fresh backups for the new cluster.
- Old-cluster rollback policy, especially for link mode.

### Dump/Restore

Focus on:

- All databases and globals dumped.
- Roles, ownership, grants, and default privileges.
- Large objects.
- Sequences and identity state.
- Extensions installed properly before restore.
- Object creation order/dependencies.
- Data counts/checksums/aggregates.
- Invalid objects and restore warnings.
- Database encoding/locale.
- Application cutover watermark.

### Logical Replication

Focus on:

- Schema parity.
- Publication/subscription state.
- Table synchronization.
- Replication lag and final LSN/watermark.
- Non-replicated DDL.
- Sequence synchronization.
- Large objects and non-replicated objects.
- Final write freeze/cutover.
- Reverse replication or rollback data path.

### Managed Service

Focus on:

- Provider upgrade events/logs.
- Engine version and parameter group.
- Extension support matrix.
- Endpoint/DNS changes.
- Replicas/failover state.
- Automated backup/snapshot status.
- Provider-specific restore points.
- Monitoring/exporter compatibility.
- Maintenance window and rollback limitations.

## 38. When Post-Checks Fail

Do not open full traffic or close the change if any critical criterion remains unmet.

### Data Mismatch

- Preserve source/backups per policy.
- Halt writers if cutover is incomplete.
- Establish the snapshot/watermark.
- Isolate differing tables, partitions, or key ranges.
- Check sequences, triggers, generated columns, and logical replication.
- Reconcile or restore per recovery plan.
- Never run mass corrective updates before finding the root cause.

### Permission Regression

- Identify affected roles and objects.
- Compare ownership, ACLs, memberships, and default privileges.
- Test using the application role.
- Grant/revoke per least privilege.
- Capture effective privilege checks.
- Never "fix" permissions by granting `SUPERUSER` to applications.

### Performance Regression

- Check analyze/statistics.
- Diff `EXPLAIN` plans.
- Check collations and index validity.
- Check cache warm-up and I/O.
- Inspect wait events, locks, temp files, WAL, and connection counts.
- Apply controlled changes, keep baselines, and roll back if budgets are breached.

### Backup/Restore Failure

- Do not delete pre-upgrade backups.
- Check backup tool version, manifests, WAL coverage, and credentials.
- Take a new backup after resolving the issue.
- Test restoring onto an isolated target.
- Record actual RPO/RTO.
- Escalate if recoverability cannot be proven.

### Replication Failure

- Verify primary/standby versions and topology.
- Inspect receiver/sender states, slots, and WAL availability.
- Check HBA, TLS, and networking.
- Check extension/replication compatibility.
- Rebuild standbys per runbook if required WAL is gone.
- Verify HA manager leader state.

## 39. Post-Upgrade Rollback

Rollback plans must be designed ahead of the upgrade. Options depend on method:

- Minor update: usually allows reverting packages/binaries via supported steps, though check for catalog/data changes and never start old binaries against incompatible data state.
- `pg_upgrade` copy mode: old cluster may remain intact for restart if the new cluster has not altered external dependencies or data routing; still control writes carefully.
- `pg_upgrade` link mode: once the new cluster begins writing, the old cluster is no longer an independent rollback copy.
- Dump/restore: rollback can revert apps to the source if intact and the target took no writes; once the target accepts writes, reverse sync/reconciliation is required.
- Logical replication: rollback depends on retaining the source, reverse synchronization, and cutover write state.

Never merely flip DNS back to the old server. Once the target commits new transactions, reverting loses data. Runbooks must address data divergence and recovery strategies.

## 40. Post-Upgrade Evidence

An evidence package should include:

- Change ID, runbook version, and operator.
- Source/target PostgreSQL versions.
- Upgrade method and tool versions.
- Start/end timestamps and timezone.
- Cluster/database identity.
- Extension inventory.
- Object/schema inventory.
- Data reconciliation results.
- Index/constraint/sequence checks.
- Role/membership/grant/RLS checks.
- Collation checks and `REINDEX` evidence if applicable.
- Configuration diff and `pending_restart`.
- Analyze completion.
- Query plan/performance comparisons.
- Replication/HA status.
- WAL archive status.
- New backup ID/manifest.
- Restore test output.
- Application smoke tests.
- Monitoring snapshots.
- Deviations, exceptions, and approvals.
- Reviewer sign-off.

Never place passwords, tokens, private keys, or sensitive query literals into evidence. Redact sensitive values while keeping timestamps, environments, object names, and SQLSTATEs intact for auditing.

## 41. Sample Runbook: Post-Upgrade Verification

~~~text
RUNBOOK: PostgreSQL Post-Upgrade Verification

A. IDENTIFY
   - Change ID:
   - Environment:
   - Cluster / endpoint:
   - Source version:
   - Target version:
   - Upgrade method:
   - Operator / verifier:

B. PRE-UPGRADE BASELINE
   - Database inventory:
   - Extensions:
   - Object inventory:
   - Data checks:
   - Roles / grants:
   - Query latency / throughput:
   - Replication / slots:
   - Backup ID / restore point:

C. POST-UPGRADE PLATFORM
   - Server version:
   - Client tools:
   - Cluster identity:
   - Startup logs:
   - Effective configuration:
   - Extension binaries and SQL versions:

D. DATA AND OBJECTS
   - Schema/object inventory:
   - Invalid indexes:
   - Unvalidated constraints:
   - Sequence state:
   - Large objects:
   - Row counts / aggregates / checksums:

E. SECURITY
   - Roles / memberships:
   - Ownership / grants:
   - Default privileges:
   - RLS / policies:
   - HBA / TLS:
   - Security definer routines:

F. PERFORMANCE
   - Analyze completed:
   - Query plan comparison:
   - Latency / throughput:
   - CPU / memory / I/O:
   - Temp files / locks / deadlocks:

G. HA AND BACKUP
   - Replication:
   - Slots / subscriptions:
   - WAL archive:
   - New backup:
   - Restore test:
   - RPO / RTO evidence:

H. APPLICATION
   - Driver / connection:
   - Read smoke test:
   - Write smoke test:
   - Critical workflows:
   - Error rate / latency:
   - Monitoring and alerts:

I. DECISION
   - Acceptance criteria:
   - Exceptions:
   - Rollback/recovery decision:
   - Reviewer:
   - Closure timestamp:
~~~

## 42. Quick Verification SQL Reference

| Target | Query or Tool |
| --- | --- |
| Server version | `version()`, `SHOW server_version` |
| Cluster role | `pg_is_in_recovery()` |
| Startup time | `pg_postmaster_start_time()` |
| Database inventory | `pg_database` |
| Extensions | `pg_extension`, `pg_available_extensions` |
| Table inventory | `pg_tables` |
| Index definitions | `pg_indexes` |
| Invalid indexes | `pg_index` |
| Constraints | `pg_constraint` |
| Sequences | `pg_sequences` |
| Large objects | `pg_largeobject_metadata` |
| Roles | `pg_roles` |
| Memberships | `pg_auth_members` |
| Table grants | `information_schema.role_table_grants` |
| Effective privileges | `has_database_privilege()`, `has_schema_privilege()`, `has_table_privilege()` |
| Default privileges | `pg_default_acl` |
| RLS policies | `pg_policies` |
| HBA parsing | `pg_hba_file_rules` |
| Effective config | `pg_settings` |
| Config errors | `pg_file_settings` |
| Collations | `pg_database`, `pg_collation` |
| Table statistics | `pg_stat_user_tables` |
| Query statistics | `pg_stat_statements` |
| Current sessions | `pg_stat_activity` |
| Locks | `pg_locks`, `pg_blocking_pids()` |
| Replication | `pg_stat_replication` |
| WAL receiver | `pg_stat_wal_receiver` |
| Replication slots | `pg_replication_slots` |
| WAL archive | `pg_stat_archiver` |
| Vacuum progress | `pg_stat_progress_vacuum` |

Views and columns can change across major versions. Verify actual schemas before embedding queries in automated scripts.

## 43. Common Mistakes

1. **Treating server startup as upgrade completion**, skipping data, permission, performance, and backup checks.
2. **Checking version only via the `psql` client**, without verifying the server binary and cluster endpoint.
3. **Forgetting to install extension binaries for the new major version**, causing function/library load failures.
4. **Checking only extension names**, ignoring `extversion` and OS package/shared libraries.
5. **Skipping analyze after `pg_upgrade`**, leaving the planner with missing or unrepresentative statistics.
6. **Ignoring collation versions**, allowing indexes to mismatch new sort semantics.
7. **Refreshing collation versions before rebuilding indexes**, silencing warnings while broken indexes remain.
8. **Comparing only row counts**, ignoring row contents, aggregates, keys, and large objects.
9. **Failing to sync sequence state after logical migration**, causing duplicate keys on insert.
10. **Ignoring invalid indexes**, leaving the planner unable to use them or causing DML issues.
11. **Ignoring `NOT VALID` constraints**, unaware which constraints have not validated historical rows.
12. **Checking only role existence**, skipping memberships, ownership, grants, and default privileges.
13. **Testing permissions as superuser**, bypassing RLS and least-privilege constraints enforced on app roles.
14. **Ignoring `SECURITY DEFINER` and `search_path`**, introducing privilege escalation risks post-upgrade.
15. **Copying old configs verbatim into a new major version**, overlooking removed/renamed settings and changed defaults.
16. **Not testing drivers and ORMs**, exposing applications to type, protocol, or prepared statement errors.
17. **Evaluating performance right after restart**, confusing cold cache warm-up with regressions or missing real regressions.
18. **Comparing cumulative counters without checking `stats_reset`**, drawing flawed conclusions.
19. **Ignoring replication slots/subscriptions**, stalling downstream consumers.
20. **Not verifying WAL archiving post-upgrade**, breaking the new recovery chain.
21. **Relying solely on old backups**, failing to create a backup compatible with the new cluster.
22. **Treating backup exit code 0 as restore proof**, without running a restore drill.
23. **Discarding the old cluster prematurely or misunderstanding `pg_upgrade` link mode risks**.
24. **Pointing endpoints back to the source after the target accepted writes**, causing data loss or business split-brain.
25. **Testing only via admin `psql`**, rather than real application roles and drivers.
26. **Ignoring monitoring/exporter compatibility**, losing dashboard metrics post-upgrade.
27. **Omitting evidence and timestamps**, leaving reviewers unable to verify system state.
28. **Closing the change right after simple smoke tests**, before observing replication, backups, and peak workloads.

## 44. Practice Exercises with Answers

### Exercise 1. Why is a successful server startup insufficient to declare an upgrade complete?

**Answer:** Because you must still verify data, objects, permissions, extensions, performance, replication, backups, and application behavior.

### Exercise 2. How do minor updates and major upgrades differ?

**Answer:** Minor updates stay within the same major series; major upgrades transition to a new major version and can change catalog/data formats, the planner, extensions, and defaults.

### Exercise 3. Which queries confirm the server version?

~~~sql
SELECT version();
SHOW server_version;
SHOW server_version_num;
~~~

**Answer:** These commands display the version of the connected server.

### Exercise 4. Which query lists installed extensions?

**Answer:** `pg_extension` joined with `pg_namespace`.

### Exercise 5. Why must extension shared libraries be checked?

**Answer:** In-database extension metadata does not prove filesystem binaries/control files are compatible with the new major version.

### Exercise 6. Which query finds invalid indexes?

**Answer:** `pg_index` filtering on `indisvalid = false` or `indisready = false`.

### Exercise 7. What does `convalidated = false` mean?

**Answer:** The constraint has not yet been validated across all existing rows; this may be intentional, yet requires verification.

### Exercise 8. Why check sequences after logical migration?

**Answer:** Sequences may not be synced by logical replication and could trail behind the table's maximum key.

### Exercise 9. What does `pg_largeobject_metadata` check?

**Answer:** Metadata and counts of PostgreSQL large objects.

### Exercise 10. Why are row counts insufficient to prove data correctness?

**Answer:** Two tables with matching row counts can still contain different values; aggregates, checksums, and key checks are needed.

### Exercise 11. Which view shows role attributes?

**Answer:** `pg_roles`.

### Exercise 12. Why verify default privileges?

**Answer:** They govern permissions on objects created in the future, not just existing objects.

### Exercise 13. Why does testing RLS as superuser fail to validate application behavior?

**Answer:** Superusers and `BYPASSRLS` roles bypass row-level security.

### Exercise 14. What must be checked on `SECURITY DEFINER` functions?

**Answer:** Owner, `EXECUTE` grants, and a safe `search_path`.

### Exercise 15. What can collation version mismatches affect?

**Answer:** Comparison/sorting order may shift and collation-dependent indexes may require rebuilding.

### Exercise 16. Does `ALTER DATABASE REFRESH COLLATION VERSION` rebuild indexes?

**Answer:** No. It updates metadata version; affected indexes must be handled separately.

### Exercise 17. Why run analyze after `pg_upgrade`?

**Answer:** The planner needs statistics matching the new cluster to estimate rows and pick good query plans.

### Exercise 18. What does `vacuumdb --all --analyze-in-stages` do?

**Answer:** Analyzes databases in progressive stages to deliver usable basic statistics quickly and refine detail afterward.

### Exercise 19. Does `EXPLAIN ANALYZE` execute the query?

**Answer:** Yes. For DML, run in staging or roll back transactions cleanly.

### Exercise 20. Is a shared read in `EXPLAIN` guaranteed to be a physical disk read?

**Answer:** No. The OS page cache may serve the page.

### Exercise 21. What does `pg_stat_statements` require?

**Answer:** The extension must be installed and preloaded properly; schemas/columns must match the version.

### Exercise 22. Why compare `stats_reset`?

**Answer:** Counters can reset, meaning before/after deltas or totals may cover different durations.

### Exercise 23. Which query confirms a node is a standby?

**Answer:** `SELECT pg_is_in_recovery();` — `true` indicates recovery/standby mode.

### Exercise 24. Which node runs `pg_stat_replication`?

**Answer:** The primary, to inspect connected standbys.

### Exercise 25. Does logical replication automatically sync sequences and DDL?

**Answer:** Not by default. Sequences and DDL require separate workflows.

### Exercise 26. What does `pg_stat_archiver` prove?

**Answer:** WAL archiving activity statistics, including successes and failures.

### Exercise 27. Why take a new backup after a major upgrade?

**Answer:** You need a recovery artifact compatible with the new cluster/version and post-upgrade WAL archive.

### Exercise 28. Does backup command exit code 0 prove restorability?

**Answer:** No. Metadata validation and a restore test are required.

### Exercise 29. Why does `pg_upgrade` link mode impact rollback?

**Answer:** New and old clusters can share inodes via hard links; once the new cluster writes, the old cluster is no longer an intact independent copy.

### Exercise 30. When can a change be closed?

**Answer:** Once all critical acceptance criteria pass, applications/monitoring are stable, replication/backups are verified, evidence is complete, and reviewers sign off.

## 45. Post-Upgrade Verification Checklist

### Platform and Version

- [ ] Confirm exact cluster, endpoint, database, and node.
- [ ] Confirm server major/minor version.
- [ ] Confirm binary/service paths and client tools.
- [ ] Check startup time and startup logs.
- [ ] Check configuration errors and `pending_restart`.
- [ ] Review parameter defaults and removed settings per release notes.

### Extensions and Objects

- [ ] Verify extension names, versions, schemas, and owners.
- [ ] Confirm matching extension binaries and control files.
- [ ] Verify preload libraries.
- [ ] Reconcile databases, schemas, tables, views, functions, and triggers.
- [ ] Verify partition inventory.
- [ ] Scan for invalid indexes.
- [ ] Check constraints and `convalidated`.
- [ ] Verify sequences and identity states.
- [ ] Verify large objects.
- [ ] Check tablespaces and external dependencies.

### Data Integrity

- [ ] Use a consistent snapshot/watermark when comparing.
- [ ] Reconcile row counts per table/partition.
- [ ] Compare min/max keys and timestamps.
- [ ] Compare aggregates/checksums on critical data.
- [ ] Check duplicate/null/range invariants.
- [ ] Verify referential integrity.
- [ ] Verify sequence states after logical migration.
- [ ] Document any exceptions.

### Permissions and Security

- [ ] Reconcile roles and attributes.
- [ ] Reconcile role memberships.
- [ ] Reconcile database/schema/table/sequence/function grants.
- [ ] Verify ownership.
- [ ] Verify default privileges.
- [ ] Check RLS policies and `FORCE RLS`.
- [ ] Inspect `SECURITY DEFINER` routines and `search_path`.
- [ ] Inspect `pg_hba_file_rules`.
- [ ] Test TLS/authentication using application roles.
- [ ] Exclude secrets from evidence.

### Performance and Applications

- [ ] Complete planned analyze runs.
- [ ] Verify statistics on critical tables.
- [ ] Compare `EXPLAIN` plans.
- [ ] Compare latency, throughput, and error rates against baseline.
- [ ] Account for cache warm-up and observation window.
- [ ] Monitor temp files, locks, deadlocks, and I/O.
- [ ] Test with real drivers, ORMs, and service roles.
- [ ] Execute read, write, and transaction smoke tests.
- [ ] Verify scheduled jobs, workers, and integrations.
- [ ] Confirm monitoring, exporters, dashboards, and alerts.

### HA and Backups

- [ ] Verify primary/standby roles.
- [ ] Verify streaming replication and lag.
- [ ] Check replication slots and subscriptions.
- [ ] Verify WAL archiving post-upgrade.
- [ ] Take a new backup suited to the new cluster.
- [ ] Validate manifests and checksums.
- [ ] Run a restore test in an isolated environment.
- [ ] Record actual RPO/RTO.
- [ ] Retain old backups/cluster per rollback policy.
- [ ] Confirm backup schedules and alerts keep running.

### Closure

- [ ] All acceptance criteria met.
- [ ] No critical unknown states remain.
- [ ] Deviations and risks documented.
- [ ] Evidence package includes context, timestamps, and sources.
- [ ] Reviewer and application owner sign-off obtained.
- [ ] Rollback window tracked clearly.
- [ ] Runbooks and inventories updated.
- [ ] Change closed in proper status.

## 46. Official PostgreSQL Documentation

Consult documentation matching both source and target major versions:

- [Upgrading a PostgreSQL Cluster](https://www.postgresql.org/docs/current/upgrading.html) — overview of upgrade methods.
- [pg_upgrade](https://www.postgresql.org/docs/current/pgupgrade.html) — checks, cluster conversion, and copy/link modes.
- [Backup and Restore](https://www.postgresql.org/docs/current/backup.html) — backup and restore strategies.
- [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html) — logical dumps.
- [pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html) — archive restoration.
- [pg_basebackup](https://www.postgresql.org/docs/current/app-pgbasebackup.html) — physical base backups.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — `pg_stat_activity`, `pg_stat_replication`, `pg_stat_wal`, and statistics views.
- [System Catalogs](https://www.postgresql.org/docs/current/catalogs.html) — database metadata.
- [Database Roles](https://www.postgresql.org/docs/current/user-manag.html) — roles and memberships.
- [Privileges](https://www.postgresql.org/docs/current/ddl-priv.html) — ownership and object privileges.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) — RLS and policy behavior.
- [Collation Support](https://www.postgresql.org/docs/current/collation.html) — locales, providers, and collation versions.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — `ANALYZE` and planner statistics.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — query plans and execution metrics.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — publications/subscriptions and replication limitations.
- [Continuous Archiving and PITR](https://www.postgresql.org/docs/current/continuous-archiving.html) — WAL archiving and point-in-time recovery.
- [Extension Packaging](https://www.postgresql.org/docs/current/extend-extensions.html) — extension control files and versioning.

`/current/` URLs point to the latest PostgreSQL release. `pg_upgrade` behavior, system catalogs, statistics views, collation support, extension compatibility, and backup tools change across major versions. Verify documentation for both source and target versions before proceeding.

## 47. Summary

**An upgrade is complete only when data, permissions, performance, HA, backups, and applications are all verified with auditable evidence.** A clean server startup or successful upgrade command is merely the starting point of post-upgrade verification.

1. **Distinguish minor updates from major upgrades.** Each upgrade method carries distinct risks and verification evidence.
2. **Verify the exact server, binary, cluster, and databases.** Never rely solely on client versions or endpoint aliases.
3. **Verify extension binaries and SQL versions.** Extension metadata does not prove shared library compatibility.
4. **Reconcile objects, indexes, constraints, sequences, and large objects.** Pay close attention to invalid indexes and sequence state.
5. **Reconcile data at a consistent snapshot or watermark.** Row counts alone do not prove data equivalence.
6. **Verify roles, memberships, ownership, grants, and default privileges.** Test with application roles and validate RLS.
7. **Check collation versions.** Rebuild affected indexes before refreshing recorded versions.
8. **Run analyze and compare query plans.** Stale or missing statistics can cause severe performance regressions.
9. **Validate application compatibility.** Drivers, ORMs, TLS, prepared statements, and background jobs all need smoke tests.
10. **Verify replication, slots, subscriptions, and WAL archiving.** Never assume logical replication state transfers automatically.
11. **Take a new backup and run a restore test.** A successful backup command does not prove recoverability.
12. **Keep rollback paths aligned with the upgrade method.** Pay close attention to `pg_upgrade` link-mode risks and post-cutover writes.
13. **Archive evidence with timestamps, context, and sources.** Close the change only after acceptance criteria pass and reviewers sign off.

A rigorous post-upgrade verification process turns an upgrade into a provable change: you know exactly what the cluster is running, that data and permissions remain intact, that applications sustain expected performance, and that operations can recover the new cluster whenever needed.
