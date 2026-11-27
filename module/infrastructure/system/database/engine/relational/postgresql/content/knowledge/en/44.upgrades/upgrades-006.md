# Zero-Downtime Migration with Logical Replication in PostgreSQL

Upgrading PostgreSQL or migrating a database to a new server often requires copying a large volume of data. If you rely solely on a logical dump and restore, application downtime can stretch across the entire dump, file transfer, and data load duration. For large databases, this downtime window can exceed operational targets.

Logical replication lets you maintain a continuous replica on the target server while the source server continues serving the application. PostgreSQL streams committed data changes from the publisher to the subscriber once the subscriber finishes initial table synchronization. When the data has caught up, operators pause writes, wait for a final synchronization point, handle sequence states, and switch the application to the target. This approach can shrink downtime to the cutover window rather than the time required to copy the entire database.

Logical replication does not replicate every database component. DDL, sequence state, large objects, and certain object types must be prepared or migrated separately. Therefore, a successful migration requires coordinating schemas, publications/subscriptions, WAL retention, privileges, validation, and a rollback plan.

~~~text
                  PostgreSQL source
                   (publisher)
                        |
                WAL level = logical
                        |
                 Publication
                        |
                Logical decoding
                        |
                 Replication slot
                        |
                 WAL changes stream
                        |
                        v
                 PostgreSQL target
                  (subscriber)
                        |
              Initial table synchronization
                        |
                 Apply changes
                        |
                  Catch up / validate
                        |
             Freeze writes at source
                        |
                Final sync barrier
                        |
              Sequence state sync
                        |
                 Application cutover
                        |
                        v
                  New primary
~~~

This lesson belongs to the **Upgrades** chapter of the *Database Engine Relational PostgreSQL* module, focusing on migrating via logical replication to minimize service disruption.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain logical replication and why it suits low-downtime migrations.
2. Distinguish between publisher, publication, subscriber, and subscription.
3. Compare logical replication with `pg_dump`/restore and physical replication.
4. Prepare the source and target for replication.
5. Configure `wal_level`, replication slots, WAL senders, and apply workers.
6. Create a replication role with least-privilege permissions.
7. Prepare schemas, roles, extensions, and database settings on the target.
8. Create a publication for the tables to migrate.
9. Create a subscription and understand initial table synchronization.
10. Monitor synchronization status per table.
11. Understand why DDL is not automatically replicated.
12. Handle sequences, identities, large objects, and out-of-scope objects.
13. Distinguish between `copy_data=true` and `copy_data=false`.
14. Monitor replication slots and WAL retention.
15. Handle apply errors, data conflicts, and schema mismatches.
16. Verify data via counts, aggregates, checksums, and business invariants.
17. Design a cutover barrier to confirm all prior changes have been applied.
18. Synchronize sequence state after the source stops accepting writes.
19. Switch the application to the target without creating dual writes.
20. Build a rollback plan before and after the target accepts writes.
21. Handle differences across major versions, extensions, collations, and data types.
22. Design migrations by table group or workload.
23. Monitor lag, slot retention, disk, workers, and apply throughput.
24. Build a migration, validation, and cutover runbook.

## 2. Why Use Logical Replication for Migration?

A standard logical dump takes a snapshot of the data at dump start time. Writes committed after the snapshot do not automatically appear in the artifact. If restoring takes many hours, the application must stop writing for that entire period or you need a separate delta synchronization mechanism.

Logical replication decouples initial copying from continuous change streaming.

### 2.1. Initial Copy

The subscriber creates an initial copy of the published tables. While this process may take a long time, the publisher continues serving the workload.

### 2.2. Continuous Replication

After each table's snapshot, logical replication streams subsequent changes via logical decoding and an apply worker. The subscriber gradually catches up with the publisher.

### 2.3. Short Cutover

Once the subscriber is nearly caught up, pause writes on the source, wait for remaining transactions to apply, synchronize non-replicated state, and switch the application over.

### 2.4. Downtime Still Exists

Logical replication does not eliminate downtime completely. A brief window is still needed to halt writes, verify the barrier, sync sequences, check the target, and switch endpoints.

### 2.5. Key Benefits

- Copy large datasets while the source remains active.
- Move across PostgreSQL major versions in a supported direction.
- Validate the target before cutover.
- Migrate by table group.
- Reduce application write-freeze duration compared to plain dump/restore.

### 2.6. Costs and Risks

- Increased WAL generation/decoding and network traffic.
- Replication slots can retain WAL on the source.
- Initial copy can increase I/O and load.
- DDL and sequence state require separate handling.
- Conflicts or schema mismatches can halt the apply worker.
- Cutover and rollback require clear procedures.

## 3. Logical Replication Components

| Component | Location | Role |
| --- | --- | --- |
| Publisher | Source | Database emitting changes |
| Publication | Source | Defines tables and types of changes sent |
| Logical replication slot | Source | Retains the WAL position needed by the subscriber |
| Subscriber | Target | Database receiving changes |
| Subscription | Target | Connects to the publication and manages apply |
| Table synchronization worker | Target | Copies initial data for each table |
| Apply worker | Target | Applies ongoing changes |
| Replication origin | Target | Tracks progress from the publisher |

### 3.1. Publisher

The publisher is the source database with `wal_level=logical` and a publication. It continues receiving INSERT/UPDATE/DELETE operations from applications during migration.

### 3.2. Publication

A publication is a set of tables and allowed operations to stream. You can publish specific tables, all tables, or a defined list of tables in a publication.

### 3.3. Logical Replication Slot

A slot tracks the WAL position confirmed by the subscriber. The publisher cannot recycle WAL still needed by the slot, allowing the subscriber to resume after interruptions while potentially retaining large amounts of WAL.

### 3.4. Subscriber

The subscriber is the target database. It holds a compatible schema and tables to receive changes. In a one-way migration, applications must not write directly to replicated tables on the target.

### 3.5. Subscription

A subscription stores the connection to the publisher, publication names, enabled status, and copy/apply options.

### 3.6. Initial Table Synchronization

When a subscription is created with `copy_data=true`, PostgreSQL copies existing data for each table using an appropriate snapshot and then transitions to applying streaming changes.

### 3.7. Apply Worker

The apply worker receives transaction changes and applies them on the subscriber. If it encounters errors such as duplicate keys, missing tables/columns, or constraint violations, the worker may stop and require intervention.

### 3.8. Replication Origin

The subscriber records apply progress from the remote publisher. This provides a way to inspect how far data has been applied.

## 4. Logical Replication vs. Physical Replication

| Criterion | Logical Replication | Physical Streaming Replication |
| --- | --- | --- |
| Unit of transfer | Logical row changes | Physical-level WAL records |
| Scope | Published tables | Entire cluster data |
| Schema/DDL | Not automatically replicated | Follows WAL |
| Sequence state | Not automatically replicated | Follows WAL |
| Large objects | Not replicated like table rows | Included in physical data |
| Cross-major migration | Possible along compatible paths | Usually requires same-major physical compatibility |
| Selective tables | Yes | Not at the table-publication level |
| Subscriber writable | Writable, though conflict risk exists | Standby is normally read-only |
| Use case | Migration, selective replication, integration | HA, failover, physical standby |

### 4.1. Choosing Logical Replication

Appropriate when migrating a single database or subset of tables, upgrading across major versions, or keeping the source active during the initial copy.

### 4.2. Choosing Physical Replication

Appropriate for HA/DR when you need an exact full-cluster physical replica on the same major version and want to replay all WAL.

### 4.3. Do Not Confuse Logical Replication with Logical Backup

`pg_dump` produces an artifact for restoration. Logical replication maintains a stream of changes between two databases. You can use `pg_dump` to prepare schemas or seed data, but the subscription must still be coordinated with the exact snapshot/slot.

## 5. Scope and Limitations of Logical Replication

Built-in logical replication focuses on table data. Before migrating, inventory every object the application depends on.

### 5.1. What Is Replicated

A publication can stream INSERT, UPDATE, DELETE, and TRUNCATE changes according to its configured publish options. Defaults typically include these operations, though you should verify the actual publication.

### 5.2. DDL Is Not Replicated

CREATE TABLE, ALTER TABLE, CREATE INDEX, GRANT, CREATE FUNCTION, CREATE EXTENSION, and other schema changes must be applied separately on the subscriber.

### 5.3. Sequence State Is Not Replicated

Sequence definitions can be created on the target via schema migration, but current values/`last_value` are not continuously synced by logical replication. They must be synchronized at cutover.

### 5.4. Large Objects Are Not Replicated

Large objects are managed through LO catalogs/APIs rather than normal table row changes. If the application uses large objects, copy them separately and keep OIDs/references consistent per plan.

### 5.5. Views and Materialized Views

View definitions are not table data streams. Recreate definitions on the target; materialized views may need a refresh after data settles.

### 5.6. Foreign Tables and Remote Data

Foreign table definitions and remote data are not automatically copied like local published tables. Migrate external sources and FDW configurations separately.

### 5.7. Roles and Privileges

Roles, memberships, database privileges, ownership, and tablespaces must be prepared separately. Publication/subscription is not a cluster-global migration tool.

### 5.8. Unlogged and Temporary Tables

Tables outside the publication scope or ineligible for logical replication must be handled separately. Temporary tables are not persistent migration data.

### 5.9. Generated Columns

Generated column values are not transmitted like ordinary columns in logical replication; the target needs a compatible generated expression to compute its values.

### 5.10. Extensions and Server Configuration

Install extension binaries/packages and configure `shared_preload_libraries`, locale/collation, SSL, authentication, `postgresql.conf`, and external secrets on the target through separate procedures.

## 6. Migration Planning

A sound migration begins with an inventory and cutover objectives.

### 6.1. Define Source and Target

Record host, port, database, PostgreSQL versions, network path, storage, extension versions, and owners for each system.

### 6.2. Define Downtime Objectives

Define maximum write-freeze duration, RPO/RTO, validation time, and rollback window.

### 6.3. Analyze Workload

Analyze database size, write rate, WAL generation, busiest tables, long transactions, large objects, sequence usage, and DDL frequency.

### 6.4. Select Tables

The publication must cover all tables that need to be migrated. Identify tables excluded from replication, partitioned tables, and tables lacking a primary key.

### 6.5. Dependency Inventory

Document foreign keys, views, functions, triggers, types, extensions, sequences, large objects, FDWs, and application dependencies.

### 6.6. Schema Change Freeze

During migration, avoid ad-hoc DDL. Any schema changes must be applied consistently on both publisher and subscriber in a compatible order.

### 6.7. Cutover Owner

Designate a single decision-maker authorized to freeze writes, confirm the barrier, and switch traffic. Avoid multiple teams changing endpoints independently.

### 6.8. Rollback Boundary

Identify the exact moment the target begins accepting writes. Past this milestone, returning to the source requires reverse sync or reconciliation; merely reverting connection strings will lose new target writes.

## 7. Checking Version Compatibility

Logical replication supports certain cross-major scenarios, provided compatibility rules are followed.

### 7.1. Older Publisher, Newer Subscriber

A common upgrade pattern uses an older major version as the publisher and a newer (or compatible) major version as the subscriber per PostgreSQL documentation.

### 7.2. Subscriber Should Not Be Older Than Publisher

Do not assume logical replication supports every version direction. Check the compatibility matrix for both major versions before designing the migration.

### 7.3. Data Types

Data types and representations must be compatible. Newer types/extensions on the source may not exist or may behave differently on an older target.

### 7.4. Collations and Locales

Different collation providers or versions can affect sort order and index validity. Prepare database encoding/locale and verify indexes on the target.

### 7.5. Extensions

Install extension packages compatible with the target major version. Verify upgrade scripts and extension schema objects before creating the subscription.

### 7.6. Feature Differences

Generated columns, partitioning, identity behavior, publication options, and statistics views can differ by version. Test the migration in staging using the exact version pair.

### 7.7. Do Not Use Logical Replication for Arbitrary Downgrades

If the target is older than the publisher or lacks understanding of schema/data semantics, choose an alternative export/transform strategy or upgrade the target version.

## 8. Preparing the Publisher

The publisher must emit logical WAL and have enough resources for slots, senders, and decoding.

### 8.1. wal_level

~~~conf
wal_level = logical
~~~

This is a startup parameter requiring a PostgreSQL restart when changed.

### 8.2. max_replication_slots

~~~conf
max_replication_slots = 10
~~~

Ensure enough slots for subscriptions, table synchronization, and any other consumers. Size based on topology and migration concurrency.

### 8.3. max_wal_senders

~~~conf
max_wal_senders = 10
~~~

Ensure enough WAL sender processes for logical replication connections plus any physical or backup consumers.

### 8.4. max_worker_processes

Logical decoding and background processes consume worker resources. Check the server's worker limits.

### 8.5. Restart

After changing startup parameters, restart the source per the maintenance plan. Verify effective settings using `SHOW` and `pg_settings`.

### 8.6. Inspect Settings

~~~sql
SELECT name, setting, unit, context, pending_restart
FROM pg_settings
WHERE name IN (
    'wal_level',
    'max_replication_slots',
    'max_wal_senders',
    'max_worker_processes'
)
ORDER BY name;
~~~

### 8.7. WAL Capacity

Logical slots can retain WAL while a subscriber is slow or offline. Ensure the `pg_wal` filesystem has ample headroom and alert on retained WAL.

## 9. Preparing the Subscriber

The subscriber needs sufficient workers, connections, and storage to receive and apply changes.

### 9.1. Worker Settings

Parameters commonly reviewed:
- `max_replication_slots`.
- `max_logical_replication_workers`.
- `max_sync_workers_per_subscription`.
- `max_worker_processes`.

### 9.2. Apply Workers

One apply worker handles the subscription; table synchronization can spawn dedicated workers. Worker limits bound parallel copy concurrency.

### 9.3. Connection Capacity

The subscriber needs connections for apply/sync workers as well as applications and monitoring. Leave appropriate headroom.

### 9.4. Disk Capacity

Initial copying can grow target disk usage rapidly. Ensure space for table data, indexes, WAL, temporary operations, and concurrent workloads.

### 9.5. Keep Application Writes Off the Subscriber Early On

In a one-way migration, prevent applications from writing to replicated tables on the target before cutover. Local writes can cause conflicts or diverge the target from the source.

### 9.6. Inspect Settings

~~~sql
SHOW max_logical_replication_workers;
SHOW max_sync_workers_per_subscription;
SHOW max_worker_processes;
SHOW max_replication_slots;
~~~

## 10. Creating the Replication Role and Access Permissions

The publisher needs a role able to establish replication connections and read tables for initial synchronization.

### 10.1. Create the Role

~~~sql
CREATE ROLE migration_repl
    WITH LOGIN REPLICATION PASSWORD 'replace-with-secret';
~~~

Supply a real secret via a secret manager or passfile; placeholders are not production passwords.

### 10.2. SELECT Privileges

Grant `SELECT` on the tables to be initially copied:

~~~sql
GRANT SELECT ON TABLE app.customers, app.orders, app.order_items
TO migration_repl;
~~~

You can grant at the schema/table level as appropriate, but avoid granting privileges beyond migration scope.

### 10.3. pg_hba.conf

Example entry for replication connections:

~~~conf
hostssl replication migration_repl 10.40.0.0/24 scram-sha-256
~~~

Initial table copying also requires a standard database connection and matching `SELECT` privileges; `pg_hba` must permit connections to that database.

### 10.4. TLS

Use an appropriate SSL mode and verify hostnames and CA certificates. Never disable certificate validation to bypass configuration issues.

### 10.5. Subscription Owner

The role creating the subscription on the target needs appropriate permissions on the target database/tables and subscription management privileges per major version. The apply worker must be able to write to subscriber tables.

### 10.6. Secrets

The connection string is stored in the subscription catalog. Restrict catalog read access and use a passfile or secret mechanism where appropriate to avoid storing passwords directly.

### 10.7. Test Connectivity

From the target, test connecting to the publisher over the exact network path, TLS settings, and authentication method the subscription will use.

## 11. Preparing the Target Schema

Logical replication requires target tables to be compatible with source tables.

### 11.1. Schema-Only Dump

One way to bootstrap the schema:

~~~bash
pg_dump --schema-only --no-owner --no-privileges \
  -d sourcedb -f sourcedb_schema.sql
~~~

### 11.2. Restore the Schema

~~~bash
psql -X -v ON_ERROR_STOP=1 -d targetdb \
  -f sourcedb_schema.sql
~~~

Prepare required roles, extensions, and tablespaces before restoring the schema.

### 11.3. DDL Compatibility

Ensure tables, column names/types, constraints, and required objects match. Logical replication does not automatically create or ALTER schemas when the source changes.

### 11.4. Indexes and Constraints

Primary keys/unique constraints may be needed for replica identity and integrity. Secondary indexes can follow your migration strategy; deferring secondary indexes can boost apply throughput, provided query and cutover readiness are ensured.

### 11.5. Triggers

Inspect triggers on the subscriber. Logical apply does not behave identically to regular application `INSERT`s across all trigger modes; triggers configured as `ENABLE REPLICA` or `ENABLE ALWAYS` have distinct behavior. Avoid unintended side effects or double-processing.

### 11.6. Foreign Keys

Foreign keys must align with the data and apply order. Multi-table initial copies can create brief windows where one table finishes copying before a referenced table; test schemas and constraints on the target version.

### 11.7. Default Values

The subscriber could apply different defaults if columns are omitted or extra columns exist. Keep schemas compatible and verify rows after apply.

### 11.8. DDL Freeze

After creating the subscription, never modify columns or tables arbitrarily on either side. When changes are unavoidable, apply them per migration plan on both sides so the apply worker never receives an incompatible row shape.

## 12. Replica Identity and Tables Without a Primary Key

`UPDATE`/`DELETE` operations need a way to identify the matching row on the subscriber.

### 12.1. Primary Key

By default, PostgreSQL uses the primary key as the replica identity when present.

### 12.2. REPLICA IDENTITY FULL

If no primary key or suitable unique index exists, you can use:

~~~sql
ALTER TABLE app.audit_events REPLICA IDENTITY FULL;
~~~

PostgreSQL then uses the entire row to identify the old tuple. This can increase WAL, network, and apply costs and depends on data comparability.

### 12.3. Missing Replica Identity

If a publication sends `UPDATE`/`DELETE` for a table without an appropriate replica identity, the operation may fail or be rejected depending on configuration and version.

### 12.4. Unique Index

You can designate a suitable unique index with `REPLICA IDENTITY USING INDEX` if it meets non-nullable and PostgreSQL requirements.

### 12.5. Insert-Only Tables

Tables publishing only `INSERT` do not need to identify old rows for `UPDATE`/`DELETE`, though you must ensure the publication genuinely excludes those operations.

### 12.6. Check Inventory

List published tables and inspect primary keys, replica identity, partitioning, and operations performed by the application.

## 13. Creating a Publication

A publication defines which data is sent from the publisher.

### 13.1. Publish Specific Tables

~~~sql
CREATE PUBLICATION app_migration_pub
FOR TABLE app.customers, app.orders, app.order_items;
~~~

### 13.2. Publish All Tables

~~~sql
CREATE PUBLICATION app_migration_pub
FOR ALL TABLES;
~~~

`FOR ALL TABLES` requires higher privileges and may include tables that do not need migrating. Use an explicit table list when you want tight scope control.

### 13.3. Publish Options

You can filter which insert/update/delete/truncate operations are published:

~~~sql
CREATE PUBLICATION app_insert_update_pub
FOR TABLE app.events
WITH (publish = 'insert, update');
~~~

Only omit `DELETE`/`TRUNCATE` if the application and migration plan explicitly account for how target data will differ from source.

### 13.4. Row Filters and Column Lists

Supported versions allow row filters and column lists to restrict streamed data. These alter replica semantics; verify that the target is intentionally a subset rather than a full replica.

### 13.5. Partitioned Tables

Check whether the publication publishes the partitioned root or individual partitions based on `publish_via_partition_root` and the PostgreSQL version. Source and target partition layouts may differ if compatible with version and publication semantics.

### 13.6. Inspect Publications

~~~sql
SELECT pubname, puballtables, pubinsert, pubupdate, pubdelete, pubtruncate
FROM pg_publication;
~~~

### 13.7. Inspect Tables in a Publication

~~~sql
SELECT *
FROM pg_publication_tables
WHERE pubname = 'app_migration_pub'
ORDER BY schemaname, tablename;
~~~

## 14. Creating a Subscription

A subscription is created on the subscriber and points to a publisher's publication.

### 14.1. Basic Command

~~~sql
CREATE SUBSCRIPTION app_migration_sub
CONNECTION 'host=source-db.internal port=5432 dbname=sourcedb user=migration_repl sslmode=verify-full'
PUBLICATION app_migration_pub
WITH (
    copy_data = true,
    create_slot = true,
    enabled = true
);
~~~

The publication name must exist on the publisher. The connection string must reach the exact database containing the publication.

### 14.2. copy_data=true

By default, PostgreSQL copies existing data from published tables before applying streamed changes. This is the simplest approach for an initial migration when target tables start empty.

### 14.3. create_slot=true

Creates a logical replication slot on the publisher to track WAL position for the subscription. The slot name typically matches the subscription name unless configured otherwise.

### 14.4. enabled=true

Enables the subscription so workers connect and begin synchronizing immediately. In some workflows, you may create a disabled subscription and enable it later.

### 14.5. Create the Subscription Outside a Transaction Block

`CREATE SUBSCRIPTION` creates a replication slot/connection and should not run inside an ordinary transaction block. Execute it as a standalone `psql` command.

### 14.6. Connection String

Never hardcode passwords in repositories or logs. If using a passfile, ensure the PostgreSQL OS user can read the file with proper permissions.

### 14.7. Inspect Subscriptions

~~~sql
SELECT subname, subenabled, subslotname, subpublications
FROM pg_subscription;
~~~

### 14.8. Verify Workers

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

Columns in this view vary across major versions; inspect the view schema before building dashboards around it.

## 15. Initial Table Synchronization

When `copy_data=true`, PostgreSQL synchronizes each table before transitioning that table to normal streaming apply.

### 15.1. Snapshot

The table synchronization worker takes a consistent snapshot for the table and copies rows to the subscriber.

### 15.2. Changes During Copying

Changes committed after the snapshot are buffered in the logical stream/slot and applied once the copy completes so the subscriber misses no commits.

### 15.3. Multiple Tables

Tables can synchronize in parallel up to `max_sync_workers_per_subscription` and available worker capacity. Not all tables finish at the same time.

### 15.4. Table States

`pg_subscription_rel` tracks per-relation synchronization state. Common states represent initialize, data copy, copy done, synchronized, and ready.

~~~sql
SELECT
    srrelid::regclass AS relation,
    srsubstate,
    srsublsn
FROM pg_subscription_rel
ORDER BY relation::text;
~~~

### 15.5. Worker Capacity

Too few sync workers can prolong the initial copy. Too many can trigger I/O contention and high load on source and target.

### 15.6. Target Data

With `copy_data=true`, target tables should be in the expected initial state—typically empty. Pre-existing rows can trigger duplicate key or constraint errors during initial copy.

### 15.7. Initial Copy and Application Writes

Do not allow applications to write to the target during initial sync. Logical replication is a one-way stream; it does not merge local writes with applied changes.

### 15.8. Large Tables

One very large table can dominate total initial copy time. Track each relation individually and evaluate parallelism, network throughput, disk I/O, and index overhead.

## 16. copy_data=false and Pre-Seeding

`copy_data=false` skips initial table copying and begins applying changes only from the subscription's starting point.

### 16.1. When to Use

Used when the subscriber has already been loaded with a consistent data copy via a procedure that coordinates the snapshot and replication slot.

### 16.2. Do Not Use After an Arbitrary pg_dump

If you merely run `pg_dump`, restore to the target, and create a subscription with `copy_data=false`, gaps or duplicates can appear between the dump snapshot and the logical slot. The two steps do not automatically share a consistency point.

### 16.3. Consistent Snapshot

Pre-seeding requires aligning the data copy's snapshot point with the logical replication slot's consistent point. Use a verified procedure/tool designed for this purpose.

### 16.4. Benefits

For very large databases, pre-seeding can reduce initial copy duration via replication workers and let you use faster data transfer tools.

### 16.5. Risks

If the snapshot and slot are misaligned, the subscriber may miss transactions or apply changes onto the wrong baseline—a severe consistency failure.

### 16.6. Validation

Before enabling a subscription with `copy_data=false`, prove there is no gap between snapshot and stream, confirm schemas match, and verify every published table has an exact baseline.

## 17. Monitoring Replication Progress

A migration can cut over only once the subscriber has received and applied all required changes.

### 17.1. Subscriber: pg_stat_subscription

~~~sql
SELECT
    subname,
    pid,
    relid,
    received_lsn,
    latest_end_lsn,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_time
FROM pg_stat_subscription;
~~~

Columns may vary by PostgreSQL version. Check `\d+ pg_stat_subscription` before embedding queries into automation.

### 17.2. Subscriber: Table States

~~~sql
SELECT
    srrelid::regclass AS relation,
    srsubstate,
    srsublsn
FROM pg_subscription_rel;
~~~

Ensure every table in migration scope has reached the ready state per version semantics.

### 17.3. Subscriber: Replication Origin

~~~sql
SELECT
    external_id,
    remote_lsn,
    local_lsn
FROM pg_replication_origin_status;
~~~

`remote_lsn` reflects remote progress applied per replication origin. Use it alongside a barrier/cutover protocol for confirmation.

### 17.4. Publisher: Replication Slots

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status
FROM pg_replication_slots
WHERE slot_type = 'logical';
~~~

### 17.5. Publisher: WAL Sender

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_stat_replication;
~~~

### 17.6. Do Not Rely Only on Connection State

A `streaming` state indicates the connection is active; it does not guarantee initial copies have finished or that the subscriber is caught up.

### 17.7. Table Sync vs. Apply Lag

Separate initial copy progress from apply lag. A table not yet marked ready may still be missing full stream changes even while the subscription worker is connected.

## 18. WAL Retention and Replication Slots

A logical replication slot retains WAL needed by the subscriber.

### 18.1. Why Do Slots Retain WAL?

If a subscriber disconnects, the publisher must keep WAL from the slot's required position so the subscriber can resume. WAL is released only once no slot or consumer needs it.

### 18.2. Disk Growth

If a subscriber lags or stops for an extended period, `pg_wal` can grow rapidly and fill the source filesystem.

### 18.3. restart_lsn

`restart_lsn` is the earliest WAL point still needed by the slot. Comparing current WAL LSN to `restart_lsn` helps estimate retained WAL, though other slots must also be accounted for.

### 18.4. confirmed_flush_lsn

For logical slots, `confirmed_flush_lsn` reflects the position confirmed by the subscriber over the protocol. This is a key progress signal.

### 18.5. max_slot_wal_keep_size

You can configure a cap on WAL retained by slots. If the cap is exceeded, the slot may be invalidated and the subscriber forced to resync. Never set this limit too low relative to migration duration and WAL rate.

### 18.6. Inactive Slots

An inactive slot left behind for a long time continues retaining WAL. Alert on active state, retained bytes, and inactive duration.

### 18.7. Never Drop an Active Migration Slot

Never drop a replication slot just to free disk space while the migration still relies on it. Doing so prevents the subscriber from resuming and forces a full re-copy.

### 18.8. Capacity Planning

Estimate retained WAL as peak WAL generation rate × maximum expected subscriber downtime/lag, plus headroom. Monitor free disk space on the source throughout the migration.

## 19. DDL and Schema Changes During Migration

Logical replication does not automatically replicate DDL. Schemas on both sides must be kept compatible manually.

### 19.1. Freeze DDL

The simplest practice is freezing schema changes during the migration window from target schema creation until cutover completes.

### 19.2. Planned Changes

When DDL deployment is unavoidable, apply changes in compatible order:
1. Create the required column/object on the subscriber.
2. Verify the subscriber schema is ready.
3. Apply the change on the publisher.
4. Verify the apply worker remains healthy.
5. Update applications using an expand/contract strategy.

### 19.3. Adding Columns

If the source starts sending a column missing on the subscriber, apply will fail. Prepare the column on the subscriber before the source writes data into it.

### 19.4. Dropping or Renaming Columns

Never rename or drop a column on the publisher before updating the subscriber accordingly. Logical replication maps data by schema/table contract; uncoordinated changes halt apply.

### 19.5. Type Changes

Data types and cast semantics must be compatible. Major type changes may require a separate data migration or new table.

### 19.6. Index Changes

Index DDL is not replicated. Create/drop indexes separately on the target and weigh their impact on initial copy and apply throughput.

### 19.7. Constraints

Unique, check, and foreign key constraints must match incoming data. Stricter constraints on the target than on the source can cause the apply worker to fail.

### 19.8. Functions and Triggers

Create functions and triggers on the target before switching applications. Inspect trigger behavior to avoid re-firing side effects twice.

## 20. Sequences and Identity Columns

Sequence state is not continuously synchronized by built-in logical replication.

### 20.1. Sequence Definitions

A schema-only dump creates sequences, ownership, and defaults, but does not ensure the source's current sequence value is reflected on the target.

### 20.2. Values in Rows

ID values stored in table rows are replicated as column data. However, the sequence generating the next ID on the target may still sit at its initial value.

### 20.3. Duplicate Key Risk

If the target starts writing before sequences are synchronized, `nextval` can generate an already-existing value and cause a unique violation.

### 20.4. Syncing at Cutover

Once the source stops accepting writes and all transactions have been applied, read `last_value`/`is_called` for each sequence on the source and set them accordingly on the target.

### 20.5. Finding the Sequence Owned by a Column

~~~sql
SELECT pg_get_serial_sequence('app.orders', 'id');
~~~

### 20.6. Reading Sequence State

~~~sql
SELECT last_value, is_called
FROM app.orders_id_seq;
~~~

Run this after stopping all writers capable of calling the sequence. If sequence caching is used, drain/close application sessions so no cached, unused values remain in flight.

### 20.7. Setting Sequence State on the Target

~~~sql
SELECT setval('app.orders_id_seq', 900500, true);
~~~

The value above is illustrative. Replace it with the actual `last_value`/`is_called` captured from the source. If `is_called=false`, pass `false` so the next `nextval` returns the sequence's current value.

### 20.8. Identity Columns

Use `pg_get_serial_sequence` to locate the sequence bound to a `serial`/`identity` column. Check `GENERATED ALWAYS`/`BY DEFAULT` and ensure generation modes match the migration design.

### 20.9. Unattached Sequences

Standalone sequences, sequences invoked inside functions, or sequences shared across multiple tables must be inventoried separately. Do not sync only sequences discovered from primary key columns.

### 20.10. Sequences Advancing Without Table Inserts

If an application calls `nextval` and the transaction rolls back without inserting a row, the sequence still advances. Therefore, never rely solely on `MAX(id)` to infer sequence state.

## 21. Large Objects and Out-of-Table Data

Large objects are not part of standard logical table replication.

### 21.1. OID References

A table may store an OID pointing to a large object. Logical replication transfers the OID column value if published, yet the LO content itself is not copied automatically.

### 21.2. Copy Large Objects Separately

Use an appropriate tool or application process to read large object contents from the source and create them on the target. Maintain an OID mapping or update reference columns per plan.

### 21.3. Avoid OID Collisions

Creating new large objects on the target can yield different OIDs than on the source. Never assume copying content preserves identical OIDs. Design safe mapping and reference updates.

### 21.4. bytea

If binary data is stored in a `bytea` column of a published table, the column value is replicated like ordinary row data. This is a crucial difference compared to large object OID references.

### 21.5. External Files

Files on local filesystems, object storage, remote services, or application hosts must be migrated separately. Logical replication does not track them.

### 21.6. FDWs and Secrets

Foreign servers, user mappings, credentials, and remote data sources must be provisioned on the target. Never put secrets into SQL dumps or unprotected logs.

## 22. Publication Filters and Migration Scope

Publications can restrict tables, rows, or columns depending on version capabilities.

### 22.1. Table Lists

Explicit table lists keep the migration focused strictly on required tables and make scope easy to review.

### 22.2. FOR ALL TABLES

Use only when every eligible table is truly needed and required privileges are appropriate. Watch for newly added tables during migration; a `FOR ALL TABLES` publication may automatically cover new tables per its semantics, yet subscriber schemas still must be created manually.

### 22.3. Row Filters

Row filters replicate only rows matching a predicate. When used, the target is intentionally a subset; do not treat equal row counts with the source as a validation criterion.

### 22.4. Column Lists

Column lists restrict which columns are transmitted. Ensure the subscriber has the required columns, defaults, or generated columns to receive data and support target applications.

### 22.5. Multiple Publications

A subscription can subscribe to multiple publications. Avoid publishing the same table across multiple publications in ways that create duplicate or confusing semantics; inspect effective publication scope.

### 22.6. Schema Evolution

New tables added to a publication must be created on the subscriber and handled via appropriate subscription/table synchronization refresh steps. Never assume DDL auto-follows.

## 23. Data Conflicts and Apply Errors

The logical replication apply worker must apply changes under the subscriber's constraints and schema.

### 23.1. Duplicate Key

The target already has a row with the same primary key when the source sends an `INSERT`. Check whether the target contains pre-seeded data or unauthorized application writes.

### 23.2. Missing Row

The source sends an `UPDATE`/`DELETE`, yet the subscriber cannot find the matching row. Check initial copy consistency, manual edits, and replica identity.

### 23.3. Schema Mismatch

Missing columns/tables, incompatible types, or differing constraints can cause apply failures.

### 23.4. Permission Errors

The subscription owner or apply worker lacks required permissions on the target table or schema.

### 23.5. Trigger Side Effects

Triggers on the subscriber may alter data or invoke external side effects. Inspect trigger firing modes and application logic.

### 23.6. TRUNCATE

If the publication transmits `TRUNCATE`, confirm the target shares the same expectations for related tables and foreign key dependencies. Test truncate behavior in staging.

### 23.7. Apply Worker Stops

Check PostgreSQL logs, subscription worker state, and error details. After fixing the root cause, verify the worker resumes or re-enable the subscription cleanly.

### 23.8. Never Skip Errors Arbitrarily

Never skip a transaction just to make a dashboard look green. Identify missing rows/objects, repair data, or rebuild the table/subscription through a controlled procedure.

## 24. Validation During Migration

Validation should happen repeatedly, not just at cutover.

### 24.1. Schema Validation

Compare table/column definitions, types, constraints, indexes, triggers, defaults, ownership, and grants.

### 24.2. Row Counts

Compare row counts per table on source and target. While replication is active, counts may differ due to ongoing writes; exact comparisons must wait until after the barrier.

### 24.3. Aggregate Checks

Compare totals, min/max IDs, daily/partition counts, sums, and business invariants. Choose checks that reflect data semantics.

### 24.4. Hash/Chunk Validation

For large tables, partition by primary key ranges or partitions and compute checksums at a matching snapshot/cutover point. Avoid scanning entire source/target tables too frequently during peak hours.

### 24.5. Referential Integrity

Verify foreign key relationships, orphan rows, and business constraints after initial sync completes.

### 24.6. Sequence Validation

Compare `last_value`/`is_called` and confirm target `nextval` will not generate duplicate IDs after cutover.

### 24.7. Large Objects

Verify OID references and test reading LO contents after copying them separately.

### 24.8. Application Validation

Run read-only smoke tests, critical query plans, permission checks, and connection tests on the target before opening write traffic.

### 24.9. Extension Behavior

Verify extensions are loaded, functions/operators/types exist, and query results match expectations.

## 25. Cutover Barrier and Final Synchronization

Cutover requires proof that every write committed before closing the source has been applied on the target.

### 25.1. Freeze Application Writes

Put applications into maintenance/read-only mode or block write endpoints. Stop background jobs, workers, schedulers, and integration consumers capable of writing to the source.

### 25.2. Drain Transactions

Wait for open transactions to commit or roll back. Check prepared transactions and sessions that can still write. Do not merely stop a load balancer while connection pools still hold active sessions.

### 25.3. Write a Marker Transaction

A clear technique uses a migration marker table included in the publication. Once writers are stopped and transactions drained, insert a unique marker on the source:

~~~sql
INSERT INTO admin.migration_barrier (migration_id, created_at)
VALUES ('cutover-2026-01', clock_timestamp());
~~~

The `migration_id` above is an example. The marker must commit, and the table must be published, subscribed, and in ready sync state.

### 25.4. Wait for the Marker on the Target

Poll the target until the marker row appears. Because the marker committed after source writers drained and travels down the same logical stream, its arrival proves all transactions published ahead of it have been applied in stream order.

### 25.5. Use LSNs as Complementary Signals

You can cross-check `pg_replication_origin_status.remote_lsn` and `pg_stat_subscription.latest_end_lsn` against the publisher LSN. However, a barrier row is easier to interpret when unrelated WAL activity exists and provides a clear application-level condition.

### 25.6. Do Not Rely Solely on Lag Time Metrics

A zero lag metric or `streaming` state does not prove every transaction is applied. Use the marker and table readiness to confirm the cutover point.

### 25.7. Disable the Subscription

Once the marker appears and all final validations pass, you can disable the subscription to halt apply during traffic switching:

~~~sql
ALTER SUBSCRIPTION app_migration_sub DISABLE;
~~~

Keep the subscription and slot per the rollback plan. Do not drop the slot until you are certain neither replication nor rollback will need it.

## 26. Syncing Sequences at Cutover

Once the source stops accepting writes, synchronize all relevant sequences.

### 26.1. Inventory Sequences

List sequences across migrated schemas. Record sequence name, owner, increment, start/min/max, cache, cycle, and current state.

### 26.2. Read Source State

For each sequence, read `last_value` and `is_called`. Do this only after every application session capable of calling `nextval` has stopped.

### 26.3. Record State

Save sequence states in a restricted-access migration artifact recording explicit source-to-target mapping. Do not store secrets in this file.

### 26.4. Set Target Values

Call `setval` on the target with the corresponding value and `is_called`. Never hardcode `MAX(id)+1` for every sequence, since sequences may have non-1 increments/starts or standalone usage.

### 26.5. Identity Columns

Use `pg_get_serial_sequence` to find identity/serial sequences. Verify target identity definitions and sequence ownership.

### 26.6. Verify nextval

Before opening writes, confirm the next generated value does not collide with replicated keys. For a sequence incrementing by 1 with `is_called=true`, `nextval` returns the value after `last_value`.

### 26.7. Never Allow Concurrent Writers

If sessions on either source or target still call sequences during sync, state can drift after capture. Hold the write freeze until sync completes.

## 27. Application Cutover

Once the barrier and sequence sync finish, switch applications to the target.

### 27.1. Confirm Target Readiness

Verify subscription status, schemas, indexes, constraints, privileges, extensions, sequence states, large objects, and application smoke tests.

### 27.2. Switch Connection Endpoints

Update service discovery, DNS, proxies, connection strings, or secret configurations so applications connect to the target.

### 27.3. Recycle Connection Pools

Close stale connections and open fresh ones. Ensure no application sessions remain writing to the source.

### 27.4. Keep Only One Writer Active

During cutover, the source must remain fenced/read-only or unable to accept application writes. Prevent dual-write between the two databases.

### 27.5. Enable Writes on the Target

Once routing is confirmed, enable application writes and monitor database errors, latency, constraints, and sequence generation.

### 27.6. Background Jobs

Move scheduled jobs, workers, ETL pipelines, cron tasks, and consumers to the target. Ensure jobs do not hardcode the old hostname.

### 27.7. Observability

Update dashboards and alerts to recognize the target as the new primary. Avoid hardcoding roles to old hostnames.

### 27.8. Monitor Stability

Watch application errors, connection counts, transaction rate, query latency, replication/slot status, and database logs throughout the cutover window.

## 28. Rollback Strategy

Rollback must be designed before starting the migration.

### 28.1. Before the Target Accepts Writes

If writes have not yet opened on the target, you can keep the source as primary and point endpoints back after confirming the source remains consistent. The subscription/slot can be kept for investigation or retry.

### 28.2. After the Target Accepts Writes

The source is now stale. Merely switching applications back to the source will lose new target writes.

### 28.3. Reverse Replication

You can design a reverse logical replication stream or a reconciliation mechanism, but this requires schema compatibility, dedicated publications/subscriptions, and conflict handling. It does not materialize automatically just because an initial subscription existed.

### 28.4. Write Freeze During Rollback

If rolling back to the source after the target has accepted writes, freeze writes on the target, sync deltas backward or export/reconcile new data, and only then switch traffic.

### 28.5. Sequence Reconciliation

Rolling back after target writes requires syncing sequences in the reverse direction and checking for duplicate IDs.

### 28.6. External Side Effects

Emails, payments, queue messages, object storage, and external APIs are not rolled back by logical replication. Reconciliation must account for those systems too.

### 28.7. Rollback Deadline

Define when the rollback window ends. Beyond that point, the source can be retired via its own procedure and any rollback becomes a restore/recovery project.

## 29. Logical Replication and pg_dump: Combining Properly

The two tools complement each other.

### 29.1. Schema Bootstrap

`pg_dump --schema-only` generates schema definitions to prepare the target. Roles/globals and extensions must be handled separately.

### 29.2. Initial Copy via Subscription

Use `copy_data=true` so PostgreSQL automatically copies tables and applies changes from a consistent stream.

### 29.3. Pre-Seeded Data

If using `pg_dump` to preload data, coordinate the snapshot and logical slot. Set `copy_data=false` only after proving the baseline and stream share the exact consistency point.

### 29.4. Large Objects

If using `pg_dump` to copy large objects, logical replication still does not update LO content after the snapshot. If the application mutates LOs during migration, sync deltas separately or freeze LO modifications.

### 29.5. Sequences

A dump captures sequence state at dump time, yet the logical stream does not update it. Re-synchronize at cutover after writes stop.

### 29.6. Validation

Use dump/restore or SQL queries for out-of-publication objects and logical replication for continuous table changes. Keep a clear inventory of which tool handles each part.

## 30. Migrating by Table Group

For large databases, you can split the migration into groups based on dependencies and workload.

### 30.1. Core Tables

Start with lightly coupled tables or tables verifiable independently. Monitor initial copy duration and apply throughput.

### 30.2. High-Write Tables

High-write tables require adequate slot capacity, network bandwidth, and apply workers. If apply cannot keep up, lag grows.

### 30.3. Large Tables

Schedule during off-peak hours or use pre-seeding with a verified consistent snapshot procedure.

### 30.4. Reference Tables

Low-churn tables can be copied early to reduce work at cutover.

### 30.5. Foreign Key Groups

Group tightly coupled tables and validate them together. Never cut over one group while the application still depends on cross-table consistency with a group remaining on the source.

### 30.6. Publication Boundaries

A subscription can consume multiple publications; maintain clear naming and ownership. Ensure every table has one intended replication path without accidental duplicate publishing.

### 30.7. All-or-Nothing Cutover

If the application requires transactional consistency across table groups, do not cut over groups independently unless the application architecture explicitly supports dual-database operation.

## 31. Partitioned Tables and Special Table Behavior

### 31.1. Partitioned Tables

Check whether the publication publishes the partitioned root or individual partitions depending on `publish_via_partition_root` and the PostgreSQL version.

### 31.2. Subscriber Partition Layout

The target may mirror the partition layout or differ per supported behavior. Test inserts/updates/deletes and partition routing on the exact version pair.

### 31.3. Table Filters

Row filters on a publication yield a data subset. Do not use them for full-fidelity migrations unless a subset is an explicit goal.

### 31.4. TRUNCATE

Verify publish options for `TRUNCATE` and foreign key dependencies. If the application executes `TRUNCATE`, test it in staging.

### 31.5. Replica Identity FULL

For tables without keys, `FULL` increases transmitted/compared data and hurts performance. Consider adding an appropriate primary/unique key before migration if feasible.

### 31.6. Identity/Generated Columns

Check explicit identity values and generated column definitions. The subscriber must produce equivalent row state even though generated values are computed on the target.

## 32. Performance and Capacity During Migration

Logical replication adds workload to both source and target.

### 32.1. Source CPU

Logical decoding and WAL senders consume CPU. Monitor CPU, active sessions, and application query latency.

### 32.2. Source I/O

Initial copying reads table data; WAL decoding reads WAL; applications continue reading and writing. Account for I/O contention.

### 32.3. Network

Initial copying and the change stream share network bandwidth. Monitor throughput, retransmissions, latency, and bandwidth caps.

### 32.4. Target I/O

The subscriber writes initial data, indexes, and its own WAL. Disk write throughput can become the bottleneck.

### 32.5. Apply Throughput

Compare WAL change generation rate against subscriber apply speed. If the source produces changes faster than the target processes them, lag rises.

### 32.6. Worker Parallelism

Adding sync workers can boost initial copy throughput while raising source/target load. Tune based on benchmarks.

### 32.7. Indexes

Indexes on the subscriber increase insert/update overhead. Keep required constraints and plan secondary indexes using a tested strategy completed before cutover.

### 32.8. Large Transactions

Large transactions may need to apply as a single commit unit, causing sudden lag spikes. Watch long transactions and batch sizes.

### 32.9. Vacuum and Bloat

Initial loading and ongoing apply increase table churn. Monitor autovacuum, dead tuples, table bloat, and vacuum progress on the target.

## 33. Monitoring and Alerting for Migration

### 33.1. Subscription State

Track enabled state, worker PIDs, last message timestamps, and table synchronization state.

### 33.2. Table Readiness

Count tables not yet in ready state. Never cut over while any table in scope is still in initial copy.

### 33.3. Slot State

Track logical slot active state, `restart_lsn`, `confirmed_flush_lsn`, and `wal_status`.

### 33.4. Retained WAL

Estimate WAL bytes held by slots alongside publisher filesystem free space.

### 33.5. Replication Lag

Monitor received/applied progress and the barrier. Lag-time metrics can be misleading when the publisher is idle or has no transactions.

### 33.6. Apply Errors

Alert if the apply worker stops, the subscription lacks a worker, or logs show repeated apply errors.

### 33.7. Resource Metrics

Monitor source/target CPU, disk, network, connections, WAL generation, checkpoints, and autovacuum.

### 33.8. Migration Dashboard

A practical dashboard displays:
- Initial sync progress per table.
- Subscription worker state.
- Source logical slot state.
- Retained WAL and free disk space.
- Apply lag/progress.
- Apply errors.
- Source/target transaction rates.
- CPU, I/O, network.
- Cutover marker state.
- Validation status.

## 34. Troubleshooting

### Error 1. CREATE SUBSCRIPTION Reports Publisher Disallows Replication

Check `wal_level=logical`, `pg_hba.conf`, role `REPLICATION` attribute, network connectivity, and source database connection settings.

### Error 2. Initial Copy Permission Denied

Grant `SELECT` on the copied tables to the replication role and verify schema/database permissions.

### Error 3. Apply Worker Stops Due to Duplicate Key

Check whether the target had pre-existing data or application writes, identify conflicting rows, and restore a clean baseline. Never delete rows arbitrarily.

### Error 4. UPDATE/DELETE Cannot Find Row

Check initial copy completeness, manual modifications, replica identity, and target drift.

### Error 5. Relation Does Not Exist

The schema has not been created or DDL was not applied on the target. Create the compatible object and recover the worker per state.

### Error 6. Column Does Not Exist

Schema mismatch. Align the target schema with the contract before resuming apply.

### Error 7. Unsupported Replica Identity

Add an appropriate primary/unique key or configure `REPLICA IDENTITY FULL` if the overhead is acceptable.

### Error 8. Subscription Worker Not Running

Inspect `subenabled`, connectivity, PostgreSQL logs, worker limits, and permissions.

### Error 9. WAL Disk Growing on Source

Check slot active state, subscriber lag, retained WAL, apply errors, and `max_slot_wal_keep_size`. Never drop the slot if the migration still depends on it.

### Error 10. Initial Copy Too Slow

Check table sizes, worker count, network, disk I/O, indexes, and source workload. Increase workers only after measuring resource headroom.

### Error 11. Subscriber Apply Lag Increasing

Compare WAL generation to apply throughput; look for large transactions, target indexes, triggers, constraints, and CPU/I/O bottlenecks.

### Error 12. Sequence Generates Duplicate Keys After Cutover

Sequence state was not synced or the target accepted writes before syncing. Freeze writes, inspect sequences, and apply `setval` safely.

### Error 13. Large Object Missing Content

Row OIDs were replicated while LO contents were not. Copy large objects separately and verify OID mappings.

### Error 14. DDL Deployment Breaks Subscription

Uncoordinated schema change. Follow expand/contract and apply target schema changes before the publisher emits new row shapes.

### Error 15. Slot Invalidated

Required WAL was recycled due to retention limits or the slot lost validity. You must resync/recreate the subscription per procedure; gaps cannot be skipped.

### Error 16. Cutover Marker Does Not Appear

Check that the marker table is in the publication, subscription is enabled, table is ready, apply worker is running, and the source transaction committed.

### Error 17. Marker Present Yet Validation Differs

There may be unpublished tables, filters, large objects, sequences, DDL differences, or out-of-band writes. Cross-check the inventory and transaction boundary.

### Error 18. Target Receives Writes from Old Application

Inspect DNS, connection pools, background jobs, and service discovery. Fence source or target per the cutover plan to guarantee a single writer.

### Error 19. Rollback Loses Writes

Once the target accepted writes, the source lacks new deltas. Perform reverse sync or reconciliation before switching back to the source.

### Error 20. Extension/Function Behavior Differs

Install the matching extension version, run migration scripts, and verify collation/type/function behavior on the target.

## 35. Low-Downtime Migration Runbook

1. Confirm version targets, RPO/RTO, and downtime window.
2. Inventory database objects, tables, sequences, large objects, and external dependencies.
3. Verify the target version is equal to or newer than the publisher per compatibility rules.
4. Install extensions and prepare roles, privileges, tablespaces, and locale/collation.
5. Prepare the target database and schema.
6. Define publication table scope and replica identities.
7. Freeze DDL or establish an expand/contract migration plan.
8. Configure publisher `wal_level=logical`, slots, and senders.
9. Restart the publisher if needed and verify settings.
10. Create the replication role, `SELECT` grants, and `pg_hba`/TLS.
11. Configure subscriber worker capacity and disk/network.
12. Create the publication.
13. Create the subscription with `copy_data=true` for a standard baseline.
14. Monitor initial table synchronization.
15. Monitor apply lag, logical slot, and WAL retention.
16. Validate schemas, counts, aggregates, and business invariants.
17. Copy large objects and external data separately.
18. Prepare the sequence inventory and sync script.
19. Test application reads on the target and check permissions/extensions.
20. Finalize cutover communication and the rollback plan.
21. Pause source writes, schedulers, and consumers.
22. Drain active/long transactions.
23. Insert and commit the migration marker into a published table.
24. Wait for the marker to appear on the target.
25. Confirm all tables are ready and apply errors are zero.
26. Sync sequence states from source to target.
27. Run final validations and smoke tests.
28. Disable the subscription if required by the cutover procedure.
29. Fence the source so no further application writes occur.
30. Switch application endpoints/credentials to the target.
31. Recycle connection pools and switch background jobs.
32. Open writes on the target.
33. Monitor errors, latency, connections, storage, and business invariants.
34. Retain the source and slot for the defined rollback window.
35. Clean up the source subscription/slot only after deciding to retire and confirming no rollback dependency remains.

## 36. Practice Exercises

Run these exercises on two isolated PostgreSQL lab instances. Never create/drop replication slots or switch production endpoints without an approved change plan.

### Exercise 1. Logical Replication

Why does logical replication reduce downtime compared to plain dump/restore?

### Exercise 2. Components

Distinguish publisher, publication, subscriber, and subscription.

### Exercise 3. Slot

What role does a logical replication slot play?

### Exercise 4. Version

In a cross-major migration, which version direction is typically supported?

### Exercise 5. wal_level

What value must `wal_level` be set to on the publisher?

### Exercise 6. Restart

Why does changing `wal_level` require a restart?

### Exercise 7. Replication Role

Which SQL creates a role with `LOGIN` and `REPLICATION`?

### Exercise 8. SELECT Privilege

Why does the replication role need `SELECT` on initially copied tables?

### Exercise 9. Publication

Write the command to create a publication for three tables: `app.customers`, `app.orders`, and `app.order_items`.

### Exercise 10. FOR ALL TABLES

When should `FOR ALL TABLES` be avoided?

### Exercise 11. Subscription

Write the command to create a subscription with `copy_data=true`.

### Exercise 12. Initial Copy

How does initial table synchronization work?

### Exercise 13. copy_data=false

Why should you not run an ordinary `pg_dump`/restore and enable `copy_data=false` without snapshot coordination?

### Exercise 14. DDL

Does logical replication replicate `CREATE`/`ALTER TABLE`?

### Exercise 15. Sequence

Why must sequences be synchronized at cutover?

### Exercise 16. Large Object

Why is a table's OID reference replicated while LO content is not?

### Exercise 17. Replica Identity

Why do `UPDATE`/`DELETE` require a replica identity?

### Exercise 18. FULL

What trade-offs does `REPLICA IDENTITY FULL` carry?

### Exercise 19. Table State

Which view tracks per-table synchronization state?

### Exercise 20. Subscription Stats

Which view provides subscription worker status?

### Exercise 21. Replication Origin

What does `pg_replication_origin_status` help inspect?

### Exercise 22. WAL Retention

Why can a slot cause `pg_wal` to grow?

### Exercise 23. max_slot_wal_keep_size

How does this parameter protect the filesystem, and what risk does it introduce?

### Exercise 24. Apply Error

Name three reasons an apply worker can stop.

### Exercise 25. Target Writes

Why should applications not write to the target while the subscription is applying?

### Exercise 26. DDL Freeze

Why is freezing or coordinating DDL across both sides necessary?

### Exercise 27. Validation

Name four ways to verify data between source and target.

### Exercise 28. Barrier

Why must the marker row belong to a published table?

### Exercise 29. Cutover

State the correct order of write freeze, marker, sequence sync, and endpoint switch.

### Exercise 30. Sequence State

What information should be recorded when syncing a sequence?

### Exercise 31. Rollback

Why can you not merely point endpoints back to the source once the target has accepted writes?

### Exercise 32. Reverse Replication

When is designing reverse replication necessary?

### Exercise 33. Partitioning

Which setting controls publishing the partition root?

### Exercise 34. Generated Columns

How must generated columns be handled on the subscriber?

### Exercise 35. TRUNCATE

Why must `TRUNCATE` behavior and foreign key dependencies be tested?

### Exercise 36. Monitoring

Name five metrics or states to monitor during migration.

### Exercise 37. Performance

List resources that can become bottlenecks during initial copy.

### Exercise 38. Slot Invalidation

If a slot is invalidated due to missing WAL, can apply simply resume as normal?

### Exercise 39. Large Objects

Propose a method to migrate large objects along with their table references.

### Exercise 40. Design

Propose a logical replication migration plan for a large database with one primary, many tables, and a tight downtime requirement.

## 37. Reference Solutions

### Exercises 1–4. Concepts

Logical replication copies a baseline and then continuously streams changes, allowing the source to keep serving applications during the initial copy. The publisher emits changes; the publication defines scope; the subscriber receives; the subscription connects to the publication. Slots retain required WAL. Cross-major migrations typically use an older publisher and newer subscriber per compatibility requirements.

### Exercises 5–8. Preparation

The publisher needs `wal_level=logical` and a restart if changed. Create the role:

~~~sql
CREATE ROLE migration_repl LOGIN REPLICATION PASSWORD 'replace-with-secret';
~~~

The role needs `SELECT` on tables so the initial table copy can read data. Protect credentials and use TLS.

### Exercises 9–13. Publication and Subscription

~~~sql
CREATE PUBLICATION app_migration_pub
FOR TABLE app.customers, app.orders, app.order_items;
~~~

Avoid `FOR ALL TABLES` when migrating only a subset of tables or wanting strict scope control. Subscription:

~~~sql
CREATE SUBSCRIPTION app_migration_sub
CONNECTION 'host=source-db.internal dbname=sourcedb user=migration_repl sslmode=verify-full'
PUBLICATION app_migration_pub
WITH (copy_data = true, create_slot = true, enabled = true);
~~~

Initial copy takes a per-table snapshot and then applies post-snapshot changes. `copy_data=false` is safe only when baseline data and the slot's consistent point are coordinated; an ordinary `pg_dump` does not establish this alignment automatically.

### Exercises 14–18. Schema and Replica Identity

DDL is not automatically replicated. Sequence state is not replicated either. Large object contents are not replicated even though OID columns may be sent. `UPDATE`/`DELETE` must locate old rows using a primary key/unique index or `REPLICA IDENTITY FULL`. `FULL` increases WAL, network, and apply costs.

### Exercises 19–24. Monitoring and Errors

`pg_subscription_rel` tracks table sync state; `pg_stat_subscription` tracks workers; `pg_replication_origin_status` tracks remote/local apply progress. Slots retain WAL when a subscriber lags or disconnects. `max_slot_wal_keep_size` caps retained WAL, though exceeding it can invalidate the slot and force a resync. Apply workers can stop due to duplicate keys, missing rows, schema mismatches, permission errors, or constraint violations.

### Exercises 25–30. Cutover

The target should not accept application writes because the stream is one-way and conflicts can occur. Freeze DDL so schemas stay compatible. Validation includes schema comparison, row counts, aggregates/checksums, and business invariants. The marker table must be published so the marker commit travels down the exact same stream. Cutover sequence: freeze/drain source writes, commit marker, wait for marker on target, sync sequences, final validation, fence source, and switch endpoints. Record sequence `last_value`, `is_called`, increment/start, and ownership mappings.

### Exercises 31–35. Rollback and Special Tables

Once the target accepts writes, the source lacks those changes; rollback requires reverse replication or reconciliation. Partitioned tables require checking `publish_via_partition_root`. Generated columns are computed on the subscriber according to matching definitions. `TRUNCATE` must be tested because publication options and foreign key dependencies govern apply outcomes.

### Exercises 36–40. Operations

Monitor table readiness, worker state, slot retained WAL, apply lag, errors, CPU, I/O, network, and disk. Initial copy bottlenecks may be source read I/O, target write I/O, network, indexes, or worker limits. An invalidated slot cannot simply resume; resync/rebuild per plan. Large objects must be copied separately while maintaining OID mappings and updating references as needed.

Large database migration requires inventorying, preparing schemas/roles/extensions, logical publication/subscription, initial copying, continuous catch-up, validation, write freeze, marker barrier, sequence/LO sync, endpoint cutover, monitoring, and a rollback window. Keep the source fenced after cutover to prevent split-brain dual writers.

## 38. Quick Reference Table

| Need | Tool / View |
| --- | --- |
| Enable logical WAL | `wal_level = logical` |
| Create replication role | `CREATE ROLE ... REPLICATION` |
| Grant initial copy read access | `GRANT SELECT` |
| Permit replication connections | `pg_hba.conf` |
| Create publication | `CREATE PUBLICATION` |
| Inspect publications | `pg_publication` |
| Inspect publication tables | `pg_publication_tables` |
| Create subscription | `CREATE SUBSCRIPTION` |
| Pause subscription | `ALTER SUBSCRIPTION ... DISABLE` |
| Enable subscription | `ALTER SUBSCRIPTION ... ENABLE` |
| Inspect subscriptions | `pg_subscription` |
| Worker state | `pg_stat_subscription` |
| Table sync state | `pg_subscription_rel` |
| Logical slot state | `pg_replication_slots` |
| WAL sender state | `pg_stat_replication` |
| Apply origin progress | `pg_replication_origin_status` |
| Find column sequence | `pg_get_serial_sequence()` |
| Read sequence state | `SELECT last_value, is_called` |
| Set sequence state | `setval()` |
| Verify target | SQL counts/aggregates/checksums |
| Cutover barrier | Published marker table |
| Schema bootstrap | `pg_dump --schema-only` |
| Logical initial copy | `copy_data = true` |
| Pre-seeded subscription | `copy_data = false` (consistent snapshot required) |
| Slot WAL cap | `max_slot_wal_keep_size` |
| Worker capacity | `max_logical_replication_workers` / `max_sync_workers_per_subscription` |
| Target version | Same or newer supported subscriber |
| Large objects | Separate copy/mapping workflow |

## 39. Logical Replication Migration Checklist

1. Confirm source, target, PostgreSQL versions, and downtime objectives.
2. Inventory tables, partitions, types, functions, views, triggers, and constraints.
3. Inventory sequences, identity columns, large objects, and external files.
4. Inventory roles, memberships, grants, tablespaces, and extensions.
5. Verify subscriber version compatibility with the publisher.
6. Prepare the target database, encoding, locale, and collation.
7. Install extension packages and create schemas.
8. Verify primary keys/replica identity for `UPDATE`/`DELETE`.
9. Freeze DDL or prepare an expand/contract plan.
10. Configure publisher `wal_level=logical`.
11. Configure `max_replication_slots` and `max_wal_senders`.
12. Configure subscriber logical and sync workers.
13. Restart the publisher if needed and check settings.
14. Create the replication role and `SELECT` grants.
15. Configure `pg_hba`, TLS, secrets, and network connectivity.
16. Create the publication with an explicit table scope.
17. Verify publication tables and published operations.
18. Prepare compatible subscriber tables.
19. Create the subscription with `copy_data=true` or verified consistent pre-seeding.
20. Monitor initial table synchronization until ready.
21. Monitor apply workers and errors.
22. Monitor logical slot retained WAL and source disk headroom.
23. Monitor apply lag and throughput.
24. Validate schemas, counts, aggregates, and business invariants.
25. Copy large objects and external data separately.
26. Prepare the sequence inventory and cutover sync script.
27. Test application reads, permissions, extensions, and query plans on the target.
28. Pause writes/background jobs on the source at cutover.
29. Drain transactions and block new writers.
30. Commit the marker in a published table.
31. Wait for the marker to apply on the target.
32. Confirm all tables are ready with zero apply errors.
33. Sync `last_value`/`is_called` for all sequences.
34. Run final validations and smoke tests.
35. Disable the subscription if required for cutover.
36. Fence the source and confirm only the target accepts writes.
37. Switch endpoints, connection pools, jobs, and consumers.
38. Open writes on the target.
39. Monitor latency, errors, capacity, and business invariants.
40. Maintain the rollback window; drop the slot and retire the source only after the final decision.

## 40. Summary

Logical replication minimizes downtime by copying initial data while the source continues serving traffic, then continuously streaming committed changes to the subscriber. Once the target is nearly caught up, operators can pause writes for a brief window, use a marker to prove the stream has applied up to the cutover point, synchronize sequences, and switch the application.

The migration requires preparing publications/subscriptions, `wal_level=logical`, replication roles, slots, WAL senders, apply workers, schemas, and target privileges. Monitor initial table sync, apply lag, and slot retention throughout the process. Slots retain WAL for the subscriber but can fill disks if the target lags or disconnects; never drop a slot while the migration stream still depends on it.

Logical replication handles only table changes within the publication. DDL, sequence state, large objects, roles, extensions, FDWs, and external files must be handled separately. Schema mismatches, unsuitable replica identities, duplicate keys, missing rows, and subscriber-only writes can halt the apply worker or cause divergence between sides. Always validate schemas, row counts, aggregates, business invariants, and out-of-scope objects before cutover.

A safe cutover requires freezing writers, draining transactions, committing a marker in a published table, waiting for the marker to appear on the target, synchronizing sequence states, running final checks, and only then switching endpoints. Keep the source blocked from writes to prevent split-brain. Once the target accepts writes, rollback requires reverse synchronization or reconciliation; pointing connection strings back to the source will not carry new writes backward.

Test the entire procedure in staging with the exact version pair and representative data. Measure initial copy, apply throughput, WAL retention, validation duration, and cutover time. A runbook with clear owners, barriers, sequence sync, a large-object plan, rollback boundaries, and monitoring turns logical replication into a low-downtime, controllable migration strategy.
