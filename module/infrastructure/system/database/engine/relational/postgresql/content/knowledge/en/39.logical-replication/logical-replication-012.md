# Online Data Migration and Pre-Cutover Verification in PostgreSQL

Migrating a PostgreSQL database online means transferring data and workloads to a target system while the source system continues serving applications throughout most of the preparation phase. The goal is to minimize downtime, preserve data consistency, and gather reliable verification evidence before switching applications over to the target.

A common method is **logical replication**: creating compatible schemas on the subscriber, loading initial data, continuing to stream changes generated on the publisher, verifying data completeness and correctness, and establishing a synchronization barrier for cutover. This approach is valuable when upgrading major versions, moving to new infrastructure, changing storage, isolating workloads, or migrating to an independent cluster.

An online migration is more than creating a publication and subscription. You must prepare schemas, indexes, constraints, sequences, roles, extensions, large objects, jobs, application configurations, and external dependencies outside the database. You must measure replication lag, control writes at cutover time, and maintain a realistic rollback plan.

This lesson presents an end-to-end workflow for PostgreSQL native logical replication, pre-cutover verification methods, limitations requiring separate handling, and conditions under which a migration cannot complete safely.

## 1. Learning objectives

After this lesson, you will be able to:

1. Define the scope and requirements of an online PostgreSQL migration.
2. Distinguish online migration from physical failover, backup restore, and offline dump/restore.
3. Evaluate version compatibility and logical replication capabilities.
4. Inventory schemas, tables, data types, extensions, sequences, and external dependencies.
5. Prepare publisher, subscriber, publication, and subscription.
6. Plan initial data copy while the source continues accepting writes.
7. Monitor logical changes and replication lag.
8. Verify schemas, row counts, keys, aggregates, and data chunk-by-chunk.
9. Verify sequences, roles, grants, extensions, indexes, and constraints.
10. Create a barrier/marker to confirm the subscriber has applied all pre-cutover changes.
11. Execute cutover with a controlled write freeze and endpoint switch.
12. Prevent dual writes and split-brain after cutover.
13. Design rollback plans both before and after the target begins accepting writes.
14. Handle apply errors, schema drift, slot retention, and resynchronization.
15. Build checklists, monitoring, runbooks, and 80 practice exercises.

## 2. What is an online migration?

An online migration transfers data and workload from source to target with downtime confined to a brief window—typically used to halt writes, finalize replication, run final checks, and switch endpoints.

~~~text
Application writing
       |
       v
Source PostgreSQL (publisher)
       |
       +---- Initial data copy ----------------------+
       |                                             |
       +---- Logical changes / CDC ------------------+
                                                     |
                                                     v
Target PostgreSQL (subscriber)
       |
       v
Validate schema + data + metadata
       |
       v
Freeze writes -> catch up -> barrier -> cutover
       |
       v
Application writes to target
~~~

### 2.1. Source and target

- **Source/publisher**: the cluster serving current workloads and emitting published changes.
- **Target/subscriber**: the new cluster receiving initial data and logical changes.
- **Cutover**: the moment applications stop writing to the source and begin writing to the target.
- **Catch-up**: the process by which the subscriber applies remaining queued changes.
- **Rollback window**: the timeframe during which reverting to the source remains feasible under a defined procedure.

### 2.2. Online migration does not mean zero downtime

A migration can dramatically reduce downtime, yet still requires a write freeze or maintenance window to finalize data consistency. If an application cannot pause writes or lacks a fencing mechanism, guaranteeing a consistent switchover point becomes far harder.

### 2.3. Migration moves more than rows

A PostgreSQL system also includes schemas, indexes, constraints, sequences, roles, grants, extensions, configuration, jobs, secrets, certificates, connection pools, and integrations. Inventory everything the application needs to run.

## 3. Choosing a migration strategy

Not every migration requires logical replication.

| Strategy | Suitable when | Downtime and limitations |
| --- | --- | --- |
| Logical replication | Continuous sync to an independent cluster, selective tables, or cross-major-version upgrades needed | DDL/sequences/large objects and cutover require separate handling |
| Physical replication | Same-major-version compatible standby or infrastructure swap keeping physical cluster | Copies entire cluster; not a direct upgrade path across major versions |
| `pg_dump`/`pg_restore` | Small/medium database, tolerable downtime, simpler workflow preferred | Downtime is usually longer due to dump and restore duration |
| Backup + PITR | Point-in-time reconstruction or DR required | Does not continuously sync to a live target |
| Specialized migration tools | Advanced orchestration, parallel copy, CDC, and validation needed | Depends on tool capabilities and semantics |

### 3.1. When to use logical replication?

- Upgrading to a newer PostgreSQL major version with a supported version pair.
- Moving from bare metal to cloud or managed PostgreSQL.
- Migrating only a subset of database tables.
- Splitting a workload into a dedicated cluster.
- Keeping the source online while the target loads data.
- Needing a CDC stream during migration.

### 3.2. When to use physical replication?

- Promoting a standby on the same major version.
- Providing cluster-wide HA/failover.
- Preserving exact physical cluster state.
- No major version or schema changes needed.

### 3.3. When to use dump/restore?

- Data fits comfortably within the maintenance window.
- Transferring full schemas and data via a single logical dump workflow.
- Writes can stop during export/import.
- No need to keep the source online for long.

### 3.4. Decide based on RPO/RTO and downtime budget

Document maximum allowed downtime, RPO during migration, RTO if cutover fails, data volume and churn rate, network bandwidth, target provisioning capacity, rollback window, and the point of no easy return.

## 4. Surveying the source system

Begin with discovery. Never create a publication before knowing what data needs moving and which objects lie outside logical replication.

### 4.1. PostgreSQL versions

~~~sql
SELECT version();

SHOW server_version;
SHOW server_version_num;
SHOW wal_level;
~~~

Record versions of source, target, `pg_dump`, `pg_restore`, `pg_basebackup`, and extensions. Check compatibility documentation for the exact major version pair.

### 4.2. Database inventory

~~~sql
SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS database_size
FROM pg_database
WHERE datallowconn
ORDER BY pg_database_size(datname) DESC;
~~~

Logical publications and subscriptions operate within a single database. If the source contains multiple databases, plan separately per database or choose another strategy.

### 4.3. Table inventory

~~~sql
SELECT
    schemaname,
    tablename,
    n_live_tup,
    pg_size_pretty(
        pg_total_relation_size(
            format('%I.%I', schemaname, tablename)::regclass
        )
    ) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(
    format('%I.%I', schemaname, tablename)::regclass
) DESC;
~~~

`n_live_tup` is a statistical estimate, not an exact row count. Use it to sort inventory; final validation needs exact counts or controlled checksums.

### 4.4. Tables requiring special handling

Inventory:
- Tables without primary keys.
- Tables with UPDATE/DELETE lacking a suitable replica identity.
- Partitioned tables.
- Unlogged tables.
- Temporary tables.
- Tables containing generated columns or special data types.
- Large objects.
- Tables written by extensions or background processes.
- Tables with complex triggers and foreign keys.
- Very large tables needing chunking or dedicated bulk loads.

### 4.5. Schema objects

List and record:
- Schemas and tables.
- Views and materialized views.
- Functions, procedures, and triggers.
- Sequences and identity columns.
- Types, domains, and collations.
- Indexes, constraints, and partition definitions.
- Existing publications and subscriptions.
- Extensions and versions.
- Roles, memberships, grants, and default privileges.

### 4.6. External dependencies

Logical replication does not transfer PostgreSQL configuration files, TLS certificates and secrets, application binaries/configurations, external scheduled jobs, object storage contents, message queues, foreign servers/credentials, or external service state. Include these dependencies in the migration checklist.

## 5. Checking version compatibility

Logical replication can assist migrations across certain major versions, yet you must not assume every direction and feature is compatible.

Check:
1. Source and target major versions.
2. Publisher/subscriber version direction.
3. Logical replication protocol compatibility.
4. Publication features supported on both sides.
5. Data type, collation, and extension compatibility.
6. Generated column, partitioning, and identity behavior.
7. DDL differences across versions.
8. Slot failover/synchronization capabilities if needed by topology.
9. Minor-version bug fixes and known limitations.

### 5.1. Older source to newer target

This is the common direction for major-version migrations. A newer subscriber can receive logical changes from an older publisher when the version pair is supported. Verify PostgreSQL documentation for your exact version pair before deploying.

### 5.2. Using compatible binaries

Use `psql`, `pg_dump`, `pg_restore`, and replication tools from client packages compatible with target/source. Never use an older binary assuming it understands newer options.

### 5.3. Extension compatibility

Extensions may require:
- A version compatible with the target.
- Installing shared libraries before restoring schemas.
- Appropriate upgrade scripts.
- Checking operator classes, data types, and functions.
- Checking whether the extension spawns background workers or stores data outside tables.

## 6. Building a migration inventory and mapping

Create a mapping table detailing how each object is handled.

| Object | Source | Target | Method | Validation |
| --- | --- | --- | --- | --- |
| Table rows | `app.orders` | `app.orders` | Initial copy + logical changes | Counts, keys, totals |
| Table schema | `app.orders` | `app.orders` | DDL migration | Schema diff |
| Sequence | `orders_id_seq` | `orders_id_seq` | Synchronized separately | `last_value`/`max(id)` |
| Roles | `app_writer` | `app_writer` | Provisioning | Memberships/grants |
| Extension | `pgcrypto` | `pgcrypto` | Install/upgrade | Version and function tests |
| Large objects | LO catalog | LO catalog | Copied separately | OID/content checks |
| Scheduled jobs | Scheduler | Scheduler | Recreated | Job inventory |
| Configuration | Source config | Target config | Config management | Parameter diff |

### 6.1. Object owners

Assign owners per domain: database team, application team, security, platform, operations.

### 6.2. Dependencies

For example, `orders` depends on `customers` and `order_items`. Migrate schemas and data along the dependency graph; avoid cutting over while parent/child tables are inconsistent.

### 6.3. Scope freeze

Lock in the publication table list before initial sync. If tables are added mid-flight, follow dedicated procedures for adding the table, schema, initial copy, and validation.

## 7. Preparing the target cluster

Provision the target before starting the initial copy.

### 7.1. Infrastructure

Check CPU, RAM, storage capacity, IOPS and throughput, network routing from target to source, disk space for data/WAL/temporary files, backup destinations, monitoring/alerting, TLS certificates and secrets, and maintenance/upgrade policies.

### 7.2. PostgreSQL settings

Tune parameters for the target workload: `max_connections`, `shared_buffers`, `work_mem`, `maintenance_work_mem`, `effective_cache_size`, `max_worker_processes`, `max_wal_size`, checkpoint settings, autovacuum settings, logging, and monitoring.

Do not blindly copy the source config if hardware, storage, or managed service tiers differ.

### 7.3. Schema

Create compatible schemas and table definitions before the subscription applies data. Use versioned, reviewed migration scripts. Inspect types, columns, defaults, generated expressions, and collations.

### 7.4. Indexes

Indexes on the target can slow initial loads and add I/O during apply. Decide whether to:
- Create indexes beforehand to preserve read paths and constraint behavior.
- Or build secondary indexes after bulk loading to accelerate sync, if the initial copy workflow allows and the target serves no live traffic yet.
- Retain necessary unique indexes to prevent duplicates.
- Never drop constraints without a validation/re-enable plan.

### 7.5. Roles and privileges

Create roles, memberships, grants, default privileges, and ownership. Never rely on logical replication to bring roles from source to target.

### 7.6. Extensions

Install extension binaries before creating dependent objects. Create extensions on the target at compatible versions and run smoke tests.

## 8. Preparing the publisher

Logical replication requires `wal_level=logical` on the publisher.

~~~conf
wal_level = logical
max_wal_senders = 20
max_replication_slots = 20
~~~

Values are illustrative; size for subscriptions, synchronization workers, and CDC consumers. `wal_level` requires a PostgreSQL restart to take effect.

Verify:

~~~sql
SHOW wal_level;
SHOW max_wal_senders;
SHOW max_replication_slots;
~~~

### 8.1. Replication role

Create a role with appropriate privileges for logical replication and initial table copy per your version:

~~~sql
CREATE ROLE migration_reader
WITH LOGIN REPLICATION PASSWORD 'managed-outside-source-control';
~~~

`SELECT` privileges on tables being copied must also be granted per workflow. Avoid using superuser merely for convenience if unnecessary.

### 8.2. pg_hba.conf

Example:

~~~conf
host  appdb  migration_reader  10.30.0.0/24  scram-sha-256
~~~

Actual configuration must match database, source IP, TLS policy, and authentication method.

### 8.3. Firewall and TLS

Open replication ports only to required target/worker hosts. Enforce TLS certificate validation and protect credentials. Never paste replication passwords into tickets or logs.

### 8.4. Capacity

Size `max_wal_senders` for subscriptions and other clients, `max_replication_slots` for logical slots, `max_sync_workers_per_subscription`, `max_parallel_apply_workers_per_subscription` if supported by version, and disk space for retained WAL across your outage budget.

## 9. Creating the publication

On the source database:

~~~sql
CREATE PUBLICATION app_migration_pub
FOR TABLE
    app.customers,
    app.orders,
    app.order_items;
~~~

The publication defines which tables are published. It does not automatically create schemas on the target.

### 9.1. Publication for all tables

~~~sql
CREATE PUBLICATION app_all_pub
FOR ALL TABLES;
~~~

Use only when you genuinely intend to publish every eligible table in the database. Broad scope can expose unnecessary data and increase load/retention.

### 9.2. Publication operations

~~~sql
CREATE PUBLICATION app_changes_pub
FOR TABLE app.orders
WITH (publish = 'insert, update, delete, truncate');
~~~

Select operations as needed. If the target must mirror exact table state, omitting an operation type can cause both sides to diverge.

### 9.3. Row filters and column lists

Supporting versions can publish a subset of rows or columns. This aids selective distribution, yet adds a validation requirement: the target is expected to contain only data matching the filter.

### 9.4. Verifying publication scope

~~~sql
SELECT *
FROM pg_publication_tables
WHERE pubname = 'app_migration_pub'
ORDER BY schemaname, tablename;
~~~

Save the output as the baseline migration scope.

## 10. Replica identity for UPDATE and DELETE

The subscriber must locate the matching row when applying UPDATE or DELETE.

### 10.1. Primary key

~~~sql
ALTER TABLE app.customers
REPLICA IDENTITY DEFAULT;
~~~

Tables with primary keys typically use the primary key as replica identity.

### 10.2. Unique index

~~~sql
ALTER TABLE app.customers
REPLICA IDENTITY USING INDEX customers_external_id_key;
~~~

The index must meet PostgreSQL criteria for uniqueness, nullability, and validity.

### 10.3. FULL

~~~sql
ALTER TABLE app.audit_items
REPLICA IDENTITY FULL;
~~~

`FULL` logs the entire old row as identity data, increasing WAL, network traffic, and target row lookup cost. Evaluate carefully for large or update-heavy tables.

### 10.4. Finding tables lacking identity

~~~sql
SELECT
    n.nspname,
    c.relname,
    c.relreplident
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1, 2;
~~~

List all tables receiving UPDATE/DELETE without a suitable identity before creating publications.

## 11. Creating the subscription and initial copy

On the target database, after schemas are ready:

~~~sql
CREATE SUBSCRIPTION app_migration_sub
CONNECTION 'host=source.example.internal port=5432 dbname=appdb user=migration_reader'
PUBLICATION app_migration_pub
WITH (
    copy_data = true,
    create_slot = true,
    enabled = true
);
~~~

This is an example; manage passwords through secure credential mechanisms. The subscription creates a logical replication slot on the publisher and initiates table synchronization.

### 11.1. Initial table synchronization

With `copy_data=true`, PostgreSQL copies existing data for published tables while tracking changes to continue applying afterward. The synchronization mechanism coordinates transition from snapshot to stream per PostgreSQL semantics.

### 11.2. copy_data=false

Use only when data was already loaded by another process consistent with the logical replication start position. Preloading arbitrarily and enabling a subscription without aligning snapshot/LSN can miss or duplicate changes.

### 11.3. Initial copy impact on the source

Initial sync reads source tables, generating network traffic and I/O load. For large databases, test and benchmark throughput before the production migration.

### 11.4. Synchronizing multiple tables

PostgreSQL uses table synchronization workers. Balance worker count between copy speed and contention on source/target. Adding workers does not always improve throughput.

### 11.5. Checking table sync state

~~~sql
SELECT
    srsubid,
    srrelid::regclass AS table_name,
    srsubstate,
    srsublsn
FROM pg_subscription_rel
ORDER BY srrelid::regclass::text;
~~~

Interpret state codes and catalog columns according to your version. Consult catalog docs to determine which tables are copying, synchronized, or streaming changes.

## 12. Monitoring the initial load

### 12.1. Subscription status

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

This view shows worker PIDs and receive/apply progress by version. Verify workers are active and last message timestamps advance.

### 12.2. Copy progress

~~~sql
SELECT *
FROM pg_stat_progress_copy;
~~~

This view displays progress of active COPY operations. Not every version or worker exposes identical detail.

### 12.3. Source load

Monitor CPU and storage I/O, query latency, connection counts, WAL generation rate, replication slot retained WAL, free disk space, and long-running transactions.

### 12.4. Target load

Monitor COPY throughput, apply worker CPU, index maintenance, constraint checks, disk write latency, temporary files, autovacuum, and replication apply lag.

### 12.5. Initial sync timeouts

If a table is huge or a worker errors, identify the exact table, error logs, and slot state. Never repeatedly drop/recreate subscriptions without understanding side effects and how far copying progressed.

## 13. Logical changes after initial copy

Once initial sync completes, the subscriber continues applying logical changes generated on the publisher.

### 13.1. Change stream

The publisher writes WAL, logical decoding extracts row changes, and the apply worker applies them on the subscriber.

### 13.2. Transaction boundaries

Changes are transmitted with transaction semantics. A single source transaction may modify multiple tables; understand apply ordering and subscriber consistency when inspecting mid-migration.

### 13.3. Apply rate

If the source generates changes faster than the subscriber applies them, lag grows. Identify whether the bottleneck lies in decoding, network, target indexes, constraints, locks, or CPU.

### 13.4. Long transactions

Large transactions generate massive change volumes and slow apply/feedback. Avoid running major migrations, bulk updates, or risky DDL in the cutover window unless benchmarked.

### 13.5. Subscription errors

An apply error can halt the worker or prevent the subscription from advancing. Inspect subscriber logs, `pg_stat_subscription`, and slot state before proceeding.

## 14. Components logical replication does not transfer automatically

| Component | Automatically transferred by logical replication? | Required action |
| --- | --- | --- |
| Rows of published tables | Yes | Initial copy + stream |
| DDL/schemas | No | Migration scripts |
| Index definitions | No | Create on target |
| Constraints | No | Create and validate |
| Sequence state | No | Sync prior to cutover |
| Roles/passwords | No | Provision separately |
| Grants/default privileges | No | Apply permissions |
| Extensions/binaries | No | Install/upgrade |
| Large objects | No | Copy separately |
| Materialized view contents | Not auto-updated with table changes | Refresh/rebuild |
| Server configuration | No | Configuration management |
| Scheduled jobs | No | Recreate and verify |
| External files/secrets | No | Transfer/provision separately |

### 14.1. DDL

Adding, dropping, or renaming columns, tables, indexes, or constraints must be deployed separately. The subscriber must have a schema compatible with incoming changes.

### 14.2. Sequences

Sequence state is not replicated like row changes. Before cutover, synchronize sequence/identity generators so next values do not collide with existing IDs.

### 14.3. Large objects

Large objects are not transferred like tables by native logical replication. Use a separate export/import step and verify OIDs/contents per design.

### 14.4. Roles and grants

Use provisioning scripts or identity management. Check object ownership, schema USAGE, table privileges, sequence privileges, and default privileges.

### 14.5. Materialized views

Materialized view contents do not automatically follow logical changes on source tables. Schedule refreshes and verify results prior to cutover.

## 15. Schema migrations while the source remains live

DDL and logical apply must be coordinated.

### 15.1. Expand-and-contract

A safer pattern:
1. Add the new nullable/default-compatible column on the target.
2. Add the compatible column on the source.
3. Confirm subscriber schema readiness.
4. Deploy an application version able to read both old and new schemas.
5. Backfill in batches if needed.
6. Validate data.
7. Switch the application to the new column.
8. Drop the old column only after all consumers have transitioned.

### 15.2. Renaming columns

Renames on the source are not sent automatically to the subscriber by logical replication. Use a compatibility phase: add the new column, controlled dual-read/dual-write if needed, backfill, and remove the old column afterward.

### 15.3. Type changes

Evaluate cast semantics and target types. Type changes can break apply or alter data. Test with representative real data.

### 15.4. DDL freeze

During migration, restrict unplanned DDL. Record every schema change in a migration log and apply it in the proper order on source and target.

### 15.5. Publication changes

When adding a table to a publication, create its schema on the target and handle initial data copy/replication state for that table. Never just run `ALTER PUBLICATION` and assume the subscriber already received rows.

## 16. Partitioned tables

Partitioned tables require checking behavior by PostgreSQL version and publication settings.

### 16.1. Publishing the partition root

Some versions allow publishing changes via the root partitioned table or per individual partition using `publish_via_partition_root`. This affects table mapping on the subscriber.

### 16.2. Subscriber partitioning

The target can use the same or a different partition layout depending on compatibility. However, schema/partition routing must be thoroughly tested; never assume arbitrary differing layouts apply cleanly.

### 16.3. Partition attach/detach

DDL operations like `ATTACH`/`DETACH PARTITION` do not replicate automatically like logical row changes. Deploy DDL synchronously and verify table membership.

### 16.4. Per-partition validation

Compare row counts and aggregates per partition to pinpoint missing data regions. For large partitions, subdivide validation by key or time range.

## 17. Pre-cutover schema verification

Schema validation proves the target has a structure compatible with applications and publications.

### 17.1. Comparing columns

~~~sql
SELECT
    table_schema,
    table_name,
    ordinal_position,
    column_name,
    data_type,
    udt_name,
    is_nullable,
    column_default,
    is_identity,
    identity_generation,
    is_generated,
    generation_expression
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name, ordinal_position;
~~~

Run on source and target, save outputs, and compare. `information_schema` columns vary by version; use a query compatible with both sides.

### 17.2. Comparing constraints

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    con.conname,
    con.contype,
    pg_get_constraintdef(con.oid) AS definition
FROM pg_constraint AS con
JOIN pg_class AS c ON c.oid = con.conrelid
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1, 2, 3;
~~~

### 17.3. Comparing indexes

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

### 17.4. Comparing functions and views

Use `pg_dump --schema-only` or catalog queries to compare DDL. Note that normalized DDL may differ due to version-generated clauses, owners, tablespaces, or formatting.

### 17.5. Comparing extensions

~~~sql
SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
~~~

Do not compare extension names alone; check versions and shared library compatibility.

## 18. Verifying row counts

Row counts are an intuitive check, though by themselves they do not prove data equality.

### 18.1. Exact counts

~~~sql
SELECT count(*) FROM app.orders;
~~~

Run on source and target after the target catches up at a shared logical point. If the source is still accepting writes, two separate counts can differ simply due to new writes.

### 18.2. Counts by partition/key range

~~~sql
SELECT
    date_trunc('day', created_at) AS day,
    count(*) AS row_count
FROM app.orders
GROUP BY 1
ORDER BY 1;
~~~

For large tables, break counts down by day, tenant, or key range to isolate missing regions.

### 18.3. Approximate counts

`pg_class.reltuples` and `n_live_tup` are helpful for sizing/monitoring, not as proof of exact equality.

### 18.4. Snapshot consistency

When comparing source and target, establish a shared replication barrier or equivalent logical snapshot. If the source keeps mutating between reads, checks can yield false mismatches.

## 19. Verifying keys and detailed data

Equal counts can still hide a missing row paired with a duplicate row.

### 19.1. Primary key coverage

For small or medium tables, compare key sets using `EXCEPT`:

~~~sql
SELECT order_id
FROM source_copy.orders
EXCEPT
SELECT order_id
FROM target_copy.orders;
~~~

The result should be empty if key sets match. This pattern assumes both datasets are accessible within one validation database or equivalent query mechanism.

### 19.2. Reverse comparison

~~~sql
SELECT order_id
FROM target_copy.orders
EXCEPT
SELECT order_id
FROM source_copy.orders;
~~~

### 19.3. Nulls and composite keys

When a table uses a composite primary key, compare all components completely. Check nullability and uniqueness against actual constraints.

### 19.4. Data types and collations

Text comparisons can differ by collation/locale. Timestamps, numeric precision, timezones, enums, and custom types must be compared under equivalent semantics.

## 20. Verifying aggregates and business invariants

Aggregates catch certain forms of data drift at lower cost than row-by-row comparisons.

~~~sql
SELECT
    count(*) AS order_count,
    sum(total_amount) AS total_amount,
    min(created_at) AS first_order,
    max(created_at) AS last_order
FROM app.orders;
~~~

### 20.1. Grouping by status

~~~sql
SELECT status, count(*), sum(total_amount)
FROM app.orders
GROUP BY status
ORDER BY status;
~~~

### 20.2. Grouping by tenant

~~~sql
SELECT tenant_id, count(*) AS rows_per_tenant
FROM app.customers
GROUP BY tenant_id
ORDER BY tenant_id;
~~~

### 20.3. Business invariants

Examples: daily transaction totals, currency totals, order counts by status, non-negative inventory if required by domain, zero orphan references per business rules, active tenant counts, and sequence IDs higher than all used IDs.

### 20.4. Aggregates do not replace row comparisons

Two datasets can share identical counts and sums while containing different rows. Combine multiple checks and validate critical tables at the key/content level.

## 21. Chunk-based data hashing/checksums

For large tables, compute digests per key range or partition. Never aggregate an entire huge table into one massive string/array, as memory spikes can harm production.

### 21.1. Canonical representation

A checksum is meaningful only when both sides serialize data identically:
- Select columns in a fixed order.
- Normalize timestamps and timezones.
- Standardize NULL representation.
- Preserve numeric precision.
- Normalize text and encoding.
- Sort by unique key.
- Include the key to distinguish rows.

### 21.2. Chunk hashing

Illustrative example for a small key range:

~~~sql
SELECT md5(
    string_agg(
        row_to_json(t)::text,
        E'\\n'
        ORDER BY t.order_id
    )
) AS chunk_digest
FROM app.orders AS t
WHERE t.order_id >= 100000
  AND t.order_id < 110000;
~~~

Run the identical query on source and target at the same barrier. This is an illustration; `row_to_json` text formatting, data types, and schemas must be compatible. For very large tables, use smaller ranges to avoid oversized aggregates.

### 21.3. Hashes are not tamper-proof evidence

Digests compare bytes/representations. They do not authenticate origin if an actor could alter both data and digest. Protect reports and metadata via access control and immutable storage.

### 21.4. Choosing a chunk key

Use a stable primary key or partition key. Avoid `OFFSET` pagination on changing tables because inserts/deletes shift positions.

### 21.5. Creating a validation manifest

Record table name, chunk boundaries, row count, digest algorithm, digest value, barrier ID/LSN, source/target versions, timestamp, and validation status.

## 22. Verifying foreign keys and constraints

Native logical apply does not equate to an independent verification of every constraint on the subscriber.

### 22.1. Foreign keys

~~~sql
SELECT o.customer_id
FROM app.orders AS o
LEFT JOIN app.customers AS c
  ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL
LIMIT 100;
~~~

### 22.2. Unique constraints

Check for duplicates against key/index definitions, especially if target schemas were built separately or constraints were added after initial copy.

### 22.3. Check constraints

Compare definitions and run queries searching for rows violating predicates. `NOT VALID` constraints may not check all older rows until validated.

### 22.4. Validating constraints

If constraints were created `NOT VALID` to reduce rollout impact, plan `VALIDATE CONSTRAINT` before cutover where appropriate.

### 22.5. Index validity

Verify index valid status and query plans for critical workloads. An index can exist yet be marked invalid if a concurrent build failed.

## 23. Verifying sequences and identity columns

Logical replication does not synchronize sequence state like table rows. This step is easily overlooked before the target accepts writes.

### 23.1. Inventorying sequences

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
    cache_size
FROM pg_sequences
ORDER BY schemaname, sequencename;
~~~

### 23.2. Comparing sequence definitions

Compare start, increment, min/max, cache, cycle, and ownership. Matching sequence names do not prove matching definitions.

### 23.3. Reading current values

Read `last_value`/`is_called` from each sequence using a method suited to your permissions and version. Never call `nextval` solely to inspect because it mutates sequence state.

### 23.4. Synchronizing before cutover

During the write freeze:
1. Stop writers.
2. Wait for active transactions to finish.
3. Read source sequence values.
4. Read maximum keys on the target.
5. Compute safe next values respecting increment/cycle semantics.
6. Set target sequences accordingly.
7. Verify sequence ownership and identity dependencies.

### 23.5. Never rewind sequences backward

The target might already have local writes or higher IDs than the source. Never set a sequence lower than used values. If both source and target received writes, reconcile keyspaces first.

## 24. Verifying roles, grants, and security

### 24.1. Roles

Create roles and memberships via provisioning scripts. Do not copy password hashes arbitrarily; apply the new environment's identity/security policies.

### 24.2. Grants

Verify `CONNECT` on databases, `USAGE` on schemas, `SELECT`/`INSERT`/`UPDATE`/`DELETE` on tables, `USAGE`/`SELECT`/`UPDATE` on sequences, `EXECUTE` on functions, and default privileges for future objects.

### 24.3. Ownership

Object ownership affects `ALTER`/`DROP` capabilities and certain operations. Standardize ownership per target policy rather than keeping source usernames if inappropriate.

### 24.4. Row-level security

Verify RLS policies, role memberships, `FORCE ROW LEVEL SECURITY`, and application session settings. A table can contain all rows while an application sees fewer due to RLS.

### 24.5. Security smoke tests

Test key queries under every application role. Confirm users can read/write only data within their authorized scope.

## 25. Verifying functions, triggers, and jobs

### 25.1. Functions/procedures

Compare definitions, languages, volatility, `SECURITY DEFINER`, `search_path`, and dependencies. A function may compile while behaving differently across extensions or versions.

### 25.2. Triggers

Logical apply has specific semantics around trigger firing. Inspect triggers on the subscriber to avoid duplicate side effects or missed business logic.

### 25.3. Event triggers

Event triggers are not transferred automatically by logical replication. Provision them separately and verify execution privileges.

### 25.4. Scheduled jobs

Recreate cron/pgAgent/application scheduler jobs. During migration, avoid running the same side-effecting job on both source and target simultaneously.

### 25.5. Outboxes and event consumers

If the source publishes an outbox table, ensure consumers do not process the same event twice during migration/cutover. Use idempotency keys and checkpoints.

## 26. Verifying large objects and out-of-table data

Large objects are not copied like table rows by native logical replication.

### 26.1. Inventory

Check whether the system uses large objects—for example, binary data referenced via OID in application tables.

### 26.2. Export/import

Use appropriate tools like `pg_dump`/`pg_restore` or large-object APIs to transfer contents. Choose a workflow preserving OIDs if applications depend on them, or update references if OIDs change.

### 26.3. Validation

Compare large object counts, OIDs if preserved, byte sizes, byte digests, and references from application tables.

### 26.4. External blobs

If applications store files in object storage and keep only URLs/keys in PostgreSQL, database migration does not transfer object bytes. Verify bucket replication, ACLs, encryption, and URL semantics.

## 27. Monitoring replication lag

On the publisher:

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_type = 'logical';
~~~

On the subscriber:

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

### 27.1. LSN progress

The logical slot retains WAL from `restart_lsn` and the consumer confirms progress via `confirmed_flush_lsn`. Subscriber views expose worker/progress status per version.

### 27.2. Lag in bytes

~~~sql
SELECT
    slot_name,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
    ) AS wal_distance
FROM pg_replication_slots
WHERE slot_type = 'logical'
  AND restart_lsn IS NOT NULL;
~~~

This is an approximate LSN distance, not storage exclusively owned by one slot.

### 27.3. Lag in time

Monitor last message send/receipt/apply timestamps via available version views. Low write traffic can make timestamps appear stale without significant backlog; correlate with LSNs.

### 27.4. Slot retention

Logical slots retain WAL when subscribers stop. Monitor inactive slots, `restart_lsn`, retained WAL, `safe_wal_size` if available, and free disk space.

### 27.5. WAL capacity planning

Estimate WAL generation rate multiplied by outage duration budget, plus headroom for bursts and incident response. Do not rely solely on `wal_keep_size`; slot retention can grow `pg_wal` substantially.

## 28. Creating a pre-cutover barrier

Cutover requires proof that every valid change prior to halting the source has reached the target.

A practical method is **write freeze + drain + marker transaction**.

### 28.1. Freezing writers

Stop or block all write paths:
- Web/API writers.
- Background workers.
- Scheduled jobs.
- ETL/import jobs.
- Admin scripts.
- External integrations.
- Other service accounts.

Ensure no active transaction can commit after the barrier.

### 28.2. Draining in-flight transactions

Monitor `pg_stat_activity`, application queues, and transaction states. Wait for writers to finish or handle them per runbook. Never just disable a load balancer assuming all DB sessions have stopped.

### 28.3. Marker table

Create a marker table included in the publication:

~~~sql
CREATE TABLE migration_control.cutover_markers (
    marker_id text PRIMARY KEY,
    created_at timestamptz NOT NULL,
    source_lsn pg_lsn
);
~~~

Create the matching schema/table on the target before the subscription needs it.

### 28.4. Writing the marker after freeze

Once all writers have stopped and running transactions have drained, write a marker on the source:

~~~sql
INSERT INTO migration_control.cutover_markers
    (marker_id, created_at, source_lsn)
VALUES
    ('cutover_2026_11_14_01', clock_timestamp(), pg_current_wal_lsn());
~~~

The marker must belong to the monitored publication/subscription. This statement is illustrative; an LSN read inside a transaction may differ from its final commit LSN. The primary goal is inserting an ordered marker row into the logical stream.

### 28.5. Waiting for the marker to appear on the target

~~~sql
SELECT *
FROM migration_control.cutover_markers
WHERE marker_id = 'cutover_2026_11_14_01';
~~~

Once the marker is applied on the target, all changes preceding it in that logical stream have been applied in transaction order. With multiple subscriptions or publications, write/confirm markers for every stream and verify all of them.

### 28.6. Barriers do not replace validation

The marker proves the stream passed the synchronization point; it does not prove schemas, sequences, large objects, or business data were verified. Complete all validation before switching writes.

## 29. Cutover runbook

A controlled cutover can follow this sequence:

1. Confirm target schema/data validation passed.
2. Confirm zero apply errors and lag within threshold.
3. Put applications into maintenance/read-only mode.
4. Stop writers and background jobs on the source.
5. Drain in-flight transactions.
6. Write the cutover marker on the source.
7. Wait for the marker to apply on the target.
8. Verify counts, aggregates, and critical keys one final time.
9. Synchronize sequences and remaining metadata.
10. Verify roles, grants, extensions, and connection settings.
11. Fence the source against writes.
12. Switch application endpoints to the target.
13. Run smoke tests against the target.
14. Open writes on the target.
15. Monitor error rates, latency, locks, and data consistency.
16. Keep the source read-only/isolated during the rollback window per policy.

### 29.1. Endpoint switch order

Switch via DNS, proxy, service discovery, or connection configuration. Account for DNS TTLs, connection pool lifetimes, prepared statements, and lingering sessions connected to the source.

### 29.2. Fencing the source

Once the target accepts writes, the source must accept zero application writes. Use firewalls, credential revocation, read-only mode, or infrastructure controls. Updating DNS alone does not guarantee every client switched.

### 29.3. Avoid arbitrary dual-writes

If both source and target accept writes, histories diverge. Unidirectional native logical replication does not automatically merge both sides.

### 29.4. Smoke tests

Test login and authorization, key read queries, a controlled test write transaction, sequence-generated inserts, foreign-key transactions, application health endpoints, background worker status, outbox/event processing, query latency, and error rates.

## 30. Rollback plan before and after cutover

Design rollback before starting the migration.

### 30.1. Before the target accepts writes

If validation or cutover fails before the target accepts writes:
- Keep the source as system of record.
- Disable the subscription or keep the target isolated per runbook.
- Fix schema, data, or lag issues.
- Re-run validation.
- Schedule a new cutover window.

This is the simplest rollback.

### 30.2. After the target accepts writes

Once the target accepts new writes, the old source becomes stale. You cannot simply point endpoints back to the source without losing writes committed on the target.

### 30.3. Reverse replication

You can design a reverse logical replication stream before or after cutover, but you must address publication/subscription direction, schema compatibility, replica identity, conflicts, sequence state, tables/rows written per side, and loop prevention.

Do not assume the old subscription automatically reverses direction.

### 30.4. Rollback window

Set an explicit duration. During the window, keep the source read-only and retain enough state for reconciliation. Define exit criteria for closing the rollback window and retiring the source.

### 30.5. When no reverse path exists

If the target accepted writes and no reverse replication exists, rolling back may require exporting changes from the target, restoring the source via a new workflow, or accepting a longer maintenance window. This decision requires explicit data-owner sign-off and clear RPO.

## 31. Handling apply errors during migration

### 31.1. Unique violation

Usually caused by target holding colliding local data or an inconsistent initial load. Identify the row and source of truth before fixing.

### 31.2. Missing row on UPDATE/DELETE

Can happen if the row was skipped during initial copy, deleted locally, or the subscriber diverged. Inspect replica identity and table sync state.

### 31.3. Schema mismatch

Compare columns, types, defaults, and generated expressions. Deploy matching DDL and resume via tested procedures.

### 31.4. Permission errors

Verify publisher connection role, `SELECT` privileges for initial copy, and subscriber apply role/ownership. Read version-specific error logs.

### 31.5. Worker stopped

Inspect `pg_stat_subscription`, PostgreSQL logs, and slot activity. Never drop slots or recreate subscriptions before identifying which changes applied and what data requires resyncing.

### 31.6. Resyncing a single table

If a table diverges:
1. Ensure the table receives no local writes.
2. Establish snapshot/LSN consistency.
3. Use a PostgreSQL-supported table synchronization workflow or recopy the table per plan.
4. Ensure changes occurring during resync are not missed.
5. Compare counts, keys, and aggregates.
6. Confirm subscription apply resumes.

## 32. Partitioned tables and table additions

### 32.1. Adding tables to a publication

Create target schemas first, then update the publication and trigger initial data synchronization for new tables per version/workflow.

### 32.2. Partition routing

Verify `publish_via_partition_root` and target partition layouts. Test INSERT/UPDATE/DELETE across boundary partitions.

### 32.3. Attach/detach

Partition DDL does not replicate automatically. Deploy on target and source in compatible order so the source never emits rows into a layout the target is unprepared for.

### 32.4. Partition validation

Compare counts, min/max keys, and aggregates per partition. Focus on newest partitions, which typically carry the highest churn.

## 33. High-write-volume tables

Some tables can prevent the subscriber from catching up.

### 33.1. Identifying write hot spots

Use `pg_stat_user_tables`, workload metrics, and WAL generation to find tables with high insert/update/delete rates.

### 33.2. Bulk operations

Bulk UPDATE/DELETE jobs generate huge WAL volumes and backlogs. Avoid running large cleanups during initial sync/cutover windows when possible.

### 33.3. Index overhead

The subscriber must maintain indexes. Excessive or unused indexes slow apply. Tune only after benchmarking and preserve necessary constraints/validation.

### 33.4. Parallel apply

Newer versions may support parallel apply or streaming for certain workloads. Features and settings depend on major version. Increase workers only after identifying bottlenecks and testing contention.

### 33.5. Network throughput

Measure actual bandwidth and latency between source and target. Transport compression can help network limits at the cost of CPU.

## 34. Initial copy for large databases

### 34.1. Estimating duration

Estimate total bytes to copy, source read throughput, usable network throughput, target write throughput, index/constraint overhead, and retry/validation time.

### 34.2. Largest tables

Plan per table/partition. A single massive table can dominate total migration duration.

### 34.3. External preloading

Dump/restore or bulk loading can run beforehand followed by logical changes, provided snapshot and replication start positions align. Never pair `copy_data=false` with an ad-hoc preload lacking a consistency protocol.

### 34.4. Pre-testing

Rehearse on a representative dataset or clone. Measure throughput, WAL retention, source impact, apply lag, and cutover duration.

### 34.5. Temporary storage

Provision disk space for dump files, staging, sort/hash validation, indexes, WAL, and temporary files. Keep enough headroom for autovacuum and checkpoints.

## 35. Security during migration

### 35.1. Data in transit

Use TLS, verify server certificates, and restrict network access. Never treat a private subnet as a substitute for encryption.

### 35.2. Data at rest

Protect target volumes, snapshots, export files, and temporary directories with appropriate encryption.

### 35.3. Least privilege

Separate replication roles, schema migration roles, application runtime roles, validation/read-only roles, cutover operators, and backup/restore roles.

### 35.4. PII and data minimization

If the target needs only a subset, restrict publications by table/row/column where supported and permitted by policy. Confirm no sensitive tables are accidentally published.

### 35.5. Auditing

Log who created publications/subscriptions, altered schemas, rotated credentials, approved cutover, enabled target writes, plus validation reports and timestamps.

### 35.6. Secret cleanup

After migration, rotate/revoke unneeded credentials, delete temporary exports per retention policy, and confirm target logs contain no secrets.

## 36. Monitoring throughout the migration

Set up dashboards before starting initial copy.

### Source

- CPU, memory, storage I/O.
- Active connections.
- Query latency.
- WAL generation rate.
- Replication slot activity.
- Retained WAL estimate.
- Free disk space.
- Long-running transactions.
- Publication scope.

### Target

- CPU, memory, disk I/O.
- Initial table sync state.
- Apply worker state.
- Subscription errors.
- Lag/LSN progress.
- Index/constraint state.
- Free disk space.
- Autovacuum and bloat.
- Application smoke tests.

### Migration process

- Tables copied/remaining.
- Bytes copied.
- Rows validated.
- Chunk checksums passed/failed.
- Schema diff status.
- Sequence sync status.
- Barrier marker status.
- Cutover readiness.
- Rollback window expiry.

## 37. Useful system views

### 37.1. Publication tables

~~~sql
SELECT *
FROM pg_publication_tables
ORDER BY pubname, schemaname, tablename;
~~~

### 37.2. Replication slots

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

### 37.3. Subscription workers

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

### 37.4. Table synchronization state

~~~sql
SELECT
    srrelid::regclass AS relation,
    srsubstate,
    srsublsn
FROM pg_subscription_rel
ORDER BY srrelid::regclass::text;
~~~

### 37.5. Active sessions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Views and catalogs may vary by version and privileges. Query only columns present in your running major version.

## 38. Pre-cutover verification checklist

### Schema

- [ ] Tables, columns, and types are compatible.
- [ ] Indexes exist and are valid.
- [ ] Constraints and foreign keys have been checked.
- [ ] Functions, triggers, and views are deployed.
- [ ] Extensions are compatible.
- [ ] Partition definitions and mappings are accurate.

### Data

- [ ] Initial table sync is complete.
- [ ] Replication apply has zero errors.
- [ ] Row counts match at the same barrier.
- [ ] Key sets are reconciled for critical tables.
- [ ] Aggregates and business invariants pass.
- [ ] Chunk checksums pass per policy.
- [ ] Large objects and external files are transferred.
- [ ] No out-of-scope tables are missing.

### Metadata/security

- [ ] Roles and memberships are complete.
- [ ] Grants and default privileges are accurate.
- [ ] RLS policies are accurate.
- [ ] Ownership and sequence privileges are accurate.
- [ ] Secrets, certificates, and configuration are ready.
- [ ] Jobs are not running simultaneously on both sides.

### Cutover

- [ ] Write freeze has been rehearsed.
- [ ] In-flight transactions have drained.
- [ ] Marker table is included in the publication.
- [ ] Barrier marker has appeared on the target.
- [ ] Sequences are synchronized.
- [ ] Source is fenced against writes.
- [ ] Endpoint switch and connection pool refresh tested.
- [ ] Smoke tests and rollback decision owner are ready.

## 39. Runbook: migration rehearsal

A rehearsal should run the complete workflow in staging:

1. Provision a source clone and target.
2. Inventory schemas, data, and dependencies.
3. Create target schemas and roles.
4. Create publication and subscription.
5. Run initial copy.
6. Generate representative write workload on the source.
7. Monitor lag and WAL retention.
8. Perform a sample DDL change using expand-and-contract.
9. Validate counts, keys, aggregates, and hashes.
10. Synchronize sequences.
11. Freeze writers.
12. Drain transactions.
13. Write marker and wait for target apply.
14. Execute endpoint switch.
15. Run smoke tests.
16. Test rollback both before and after the target accepts writes.
17. Measure downtime/RTO and validation duration.
18. Document issues, owners, and remediation times.

## 40. Runbook: production migration

### Before cutover day

- Complete discovery and compatibility reviews.
- Rehearse at least once on representative data.
- Provision target and set up target backups.
- Create publication and subscription.
- Complete initial sync and catch-up.
- Finalize schemas and metadata.
- Run baseline validations.
- Prepare dashboards, alerts, and incident contacts.
- Lock maintenance window and decision owner.

### During cutover

- Announce freeze.
- Stop writers, jobs, and integrations.
- Drain active transactions.
- Write the marker.
- Wait for marker apply.
- Run final validation.
- Synchronize sequences.
- Fence the source.
- Switch endpoints.
- Run smoke tests.
- Open writes on the target.

### After cutover

- Monitor errors, latency, locks, and application behavior.
- Verify target backups/PITR.
- Establish HA/replicas if needed.
- Keep source read-only throughout the rollback window.
- Revoke/rotate legacy credentials.
- Close the rollback window upon approval.
- Retire the source per retention policy.
- Update documentation and lessons learned.

## 41. Rollback decision matrix

| Stage | Condition | Action |
| --- | --- | --- |
| Before initial sync | Target has no data yet | Fix provisioning and re-run |
| During initial sync | Some tables not copied yet | Stop/fix per table sync state; do not cut over |
| After sync, before freeze | Source still writing, target applying | Keep source as primary, address lag/errors |
| During freeze, before marker | Writers not yet drained | Hold off cutover; maintain or abort freeze cleanly |
| Marker not yet visible | Subscriber still catching up | Wait/investigate apply; do not switch |
| Final validation fails | Data/schema mismatch | Abort cutover, keep source as system of record |
| Target accepted writes | Two histories began diverging | Reverse sync/reconciliation required; do not merely flip endpoints |
| Past rollback window | Source already retired | Recover via new target DR/backup plan |

## 42. Troubleshooting: subscriber failing to catch up

Causes:
- Initial copy still running.
- High source write rate.
- Slow target apply due to indexes/constraints.
- Low network throughput.
- Long transactions.
- Apply errors.
- Insufficient target disk/CPU.
- Slot/WAL retention or connectivity issues.

Resolution:
1. Identify whether table sync or streaming apply is slow.
2. Read subscriber logs and `pg_stat_subscription`.
3. Check slot LSN and retained WAL.
4. Measure CPU, disk, network, and lock waits.
5. Identify which table or transaction drives the backlog.
6. Reduce unnecessary migration/background load.
7. Scale resources/workers after benchmarking.
8. Never reflexively drop slots or recreate subscriptions.

## 43. Troubleshooting: mismatched counts

Causes:
- Source continued accepting writes during counts.
- Target has not finished applying changes.
- A table is missing from the publication.
- Initial copy is incomplete.
- Row filters/column lists give the target a different scope.
- Subscriber-local writes.
- DDL/schema mismatch.
- Count queries executed against different snapshots.

Resolution:
1. Establish a barrier and freeze writers.
2. Confirm the marker applied.
3. Verify publication scope.
4. Check table sync states.
5. Compare key ranges and partition counts.
6. Check for apply errors and local writes.
7. Resync diverged tables if needed.
8. Re-run validation.

## 44. Troubleshooting: post-cutover sequence collisions

Causes:
- Sequence state is not synchronized by logical replication.
- Target sequence sits below the maximum key.
- Target had local writes before cutover.
- Sequence caches in active sessions hold stale values.

Resolution:
1. Halt affected writes if collisions are occurring.
2. Identify sequence ownership and increments.
3. Read current sequence state and maximum keys.
4. Choose a safe next value.
5. Synchronize the sequence.
6. Check concurrent sessions/caches.
7. Run a test insert and verify uniqueness.

## 45. Troubleshooting: apply worker errors after DDL

Causes:
- New column missing on target.
- Differing column types.
- Uncoordinated column rename/drop.
- Replica identity/index changed.
- Publication column list no longer compatible.

Resolution:
1. Keep the source as system of record.
2. Read the exact apply error.
3. Identify the DDL change and failing transaction.
4. Deploy compatible schema on the target.
5. Check table state and divergence.
6. Resume apply via supported procedure or resync the table.
7. Re-run schema/data validation.

## 46. Common anti-patterns

| Anti-pattern | Consequence | Correct approach |
| --- | --- | --- |
| Creating subscription before target schema is ready | Apply fails | Provision schema first |
| Using `copy_data=false` without a consistent preload | Missing/duplicate rows | Align snapshot and replication start position |
| Checking only row counts | Misses row mismatches | Check keys, aggregates, and chunk hashes |
| Comparing source/target while source still writes | False mismatches | Compare at shared barrier/snapshot |
| Forgetting DDL | Apply worker stops | Coordinate schema migrations |
| Forgetting sequences | Primary key collisions | Synchronize prior to cutover |
| Forgetting large objects | Missing file/object data | Copy and verify separately |
| Failing to check roles/grants | Application cannot access DB | Provision and smoke test every role |
| Ignoring logical slots | Retained WAL fills disk | Monitor retention and consumer lag |
| Increasing workers without measuring | Higher contention/I/O | Benchmark bottlenecks |
| Switching DNS without fencing source | Both clusters accept writes | Enforce fencing and session drain |
| Using a marker outside the publication | No barrier proof | Publish marker table and verify |
| Switching writes with in-flight transactions | Lost commit ordering | Freeze and drain before marker |
| Assuming synced target is rollback-ready | Target writes absent on source | Prepare reverse sync/reconciliation plan |
| Running jobs on both clusters | Duplicate side effects | Enforce single active scheduler |
| Skipping target backup tests | New target lacks DR | Verify backups/PITR |
| Skipping rehearsals | Downtime exceeds budget | Rehearse entire workflow |
| Retiring source right after cutover | Lose comparison/rollback path | Keep read-only throughout rollback window |

## 47. PostgreSQL practice exercises

Perform on two lab/staging clusters. Never run migration or cutover experiments on production.

1. **Discovery:** read source and target PostgreSQL versions.
2. **Inventory:** list databases and sizes.
3. **Tables:** inventory tables by size and write rate.
4. **Schema:** export schema-only using `pg_dump`.
5. **Dependencies:** list extensions, roles, sequences, and large objects.
6. **Compatibility:** verify a publisher/subscriber version pair.
7. **Target:** provision target database and schemas.
8. **Roles:** create a least-privilege migration role.
9. **Network:** configure `pg_hba` and firewall rules in the lab.
10. **TLS:** set up TLS for replication connections.
11. **`wal_level`:** set `logical` and verify after restart.
12. **Capacity:** size `max_wal_senders` and `max_replication_slots`.
13. **Publication:** create a publication for two tables.
14. **Scope:** inspect `pg_publication_tables`.
15. **Replica identity:** locate tables lacking primary keys.
16. **FULL:** test `REPLICA IDENTITY FULL` and observe behavior.
17. **Subscription:** create a subscription with `copy_data=true`.
18. **Initial copy:** monitor `pg_subscription_rel`.
19. **Copy progress:** read `pg_stat_progress_copy` during initial sync.
20. **Streaming:** insert/update/delete on source and verify on target.
21. **Apply status:** monitor `pg_stat_subscription`.
22. **Slot:** check `pg_replication_slots` on the publisher.
23. **Lag:** calculate LSN distance and retained WAL estimate.
24. **Disk:** simulate an offline subscriber and observe WAL growth.
25. **Recovery:** restart the subscriber and confirm apply resumes.
26. **Schema:** add a new column and deploy DDL in proper order.
27. **Rename:** design expand-and-contract for a column rename.
28. **Type:** test a type change in the lab and check apply.
29. **Partition:** publish a partitioned table and inspect partition behavior.
30. **Table addition:** add a new table to the publication and sync initial data.
31. **Row filter:** create a row-filtered publication if supported by version.
32. **Column list:** restrict columns and verify target representation.
33. **Counts:** compare exact counts after a barrier.
34. **Partition counts:** compare counts per day/partition.
35. **Keys:** compare key sets using `EXCEPT`.
36. **Aggregates:** compare sums/counts grouped by status.
37. **Business invariant:** write queries validating business rules.
38. **Chunk digest:** compute hashes for small key ranges.
39. **Schema diff:** compare `information_schema.columns`.
40. **Constraints:** compare `pg_constraint` definitions.
41. **Indexes:** compare `pg_indexes`.
42. **Extensions:** compare `extname`/`extversion`.
43. **Foreign keys:** search for orphan rows on target.
44. **Unique:** search for duplicate business keys.
45. **RLS:** test policies and query visibility by role.
46. **Roles:** compare memberships and grants.
47. **Sequences:** inventory `pg_sequences` on both sides.
48. **Sequence sync:** synchronize target sequences after freeze.
49. **Large objects:** copy a set of large objects and compare digests.
50. **External blobs:** verify object storage keys and contents.
51. **Triggers:** check side effects on the subscriber.
52. **Jobs:** ensure schedulers run only on source prior to cutover.
53. **Outbox:** test event idempotency during migration.
54. **Barrier table:** create a marker table included in the publication.
55. **Write freeze:** stop application writers in the lab.
56. **Drain:** inspect `pg_stat_activity` and wait for transactions to finish.
57. **Marker:** write a marker after freeze.
58. **Wait:** confirm the marker appears on the subscriber.
59. **Final validation:** run counts/keys/aggregates after marker.
60. **Endpoint:** switch the application connection string to the target.
61. **Fencing:** block writes on the source after cutover.
62. **Smoke test:** run read/write tests on the target.
63. **Sequence insert:** verify insert-generated IDs after cutover.
64. **Rollback before writes:** abort cutover before the target accepts writes.
65. **Rollback after writes:** document data needing reconciliation if the target already wrote.
66. **Reverse replication:** design a reverse stream with loop prevention.
67. **Lag incident:** intentionally slow target apply in the lab.
68. **Apply error:** induce a schema mismatch and read logs.
69. **Resync:** build a procedure to resync a diverged table.
70. **Capacity:** benchmark initial copy on a large table.
71. **Workers:** vary sync/apply workers and measure contention.
72. **Network:** measure throughput and latency between clusters.
73. **Security:** confirm secrets never appear in command history or logs.
74. **Audit:** log publication/subscription/DDL/cutover actors.
75. **Rehearsal:** execute a complete migration rehearsal.
76. **RTO:** measure downtime and duration per step.
77. **RPO:** identify the data guarantee point at the barrier.
78. **Backup:** establish backup/PITR policies on the target after cutover.
79. **DR:** rehearse restoring the target into another failure domain.
80. **Synthesis design:** plan an online migration for a large database with initial copy, logical CDC, schema evolution, multi-layer validation, barrier markers, sequence sync, write freeze, cutover, rollback/reverse paths, security, monitoring, and DR.

## 48. Go/no-go decision checklist

### Readiness

- [ ] Source/target versions are compatible.
- [ ] Target capacity and network bandwidth measured.
- [ ] Schemas and dependencies inventoried.
- [ ] Roles, grants, extensions, and configs prepared.
- [ ] Publication scope reviewed.
- [ ] Replica identities suitable.
- [ ] Initial sync complete.
- [ ] Apply workers error-free.
- [ ] WAL retention headroom sufficient.
- [ ] Source and target backups/PITR verified.

### Validation

- [ ] Schema diff passes.
- [ ] Row counts pass at the same barrier.
- [ ] Key comparisons pass for critical tables.
- [ ] Aggregates/business invariants pass.
- [ ] Chunk digests pass per policy.
- [ ] Constraints/indexes valid.
- [ ] Sequences synchronized.
- [ ] Large objects/external files verified.
- [ ] Roles/RLS/application permissions tested.
- [ ] Jobs and integrations have a single-owner plan.

### Cutover

- [ ] Write freeze rehearsed.
- [ ] In-flight transactions drained.
- [ ] Marker published and applied.
- [ ] Final validation passes.
- [ ] Source fencing ready.
- [ ] Endpoint switch and connection refresh tested.
- [ ] Smoke tests and decision owner present.
- [ ] Rollback/reverse plan approved.

## 49. Summary

A successful online PostgreSQL migration requires three distinct phases:

~~~text
1. INITIAL COPY
   Source online
       |
       v
   Target schema + table data
       |
       v
2. CONTINUOUS CATCH-UP
   Logical changes
       |
       v
   Target apply + validation
       |
       v
3. CONTROLLED CUTOVER
   Freeze writers + drain
       |
       v
   Marker/barrier + final checks
       |
       v
   Sequence sync + fence source
       |
       v
   Switch endpoint + smoke tests
~~~

Key principles:

- **Discovery precedes replication.** Know schemas, data scope, extensions, sequences, large objects, and external dependencies upfront.
- **Initial copy needs a consistency protocol.** Never preload arbitrarily and enable a subscription with `copy_data=false`.
- **Logical replication transfers row changes, not all database metadata.** DDL, roles, grants, sequences, and many objects require separate steps.
- **Validation requires multiple layers.** Row counts, key sets, aggregates, chunk hashes, constraints, and application tests catch different classes of divergence.
- **Compare at a shared barrier.** While the source is writing, two independent queries do not prove data equality.
- **Freeze and drain before the marker.** A marker in the publication proves the stream crossed the checkpoint; multiple streams need separate verification.
- **Synchronize sequences before the target accepts writes.** Otherwise, primary key collisions can happen immediately after cutover.
- **Fencing the source is mandatory when transferring write ownership.** Changing DNS alone does not stop stale clients from writing to the source.
- **Rolling back after the target accepts writes requires reverse sync or reconciliation.** You cannot simply point applications back to the old source.
- **Rehearsals establish true downtime.** Measure initial copy, lag, validation, freeze, cutover, and rollback on representative data.

Online migration is a controlled transfer of data ownership. When source/target scope, schemas, stream positions, validation evidence, and write ownership are clearly defined, cutover can happen within a brief window while retaining control and recoverability.
