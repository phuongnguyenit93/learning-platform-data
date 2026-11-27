# Differences Between Logical and Physical Replication in PostgreSQL

PostgreSQL has two main ways to stream changes from one database server to another: **physical replication** and **logical replication**. Both can use WAL and the replication protocol, but they transmit information at different levels and address different needs.

Physical replication transfers WAL records so that the standby reproduces changes at the storage level. The result is a physical copy of the entire PostgreSQL cluster, commonly used for high availability (HA), failover, disaster recovery, and read-only hot standby.

Logical replication decodes changes from WAL into data operations at the table and row level, then applies them to the subscriber. It allows selecting publications, tables, and in supported versions, rows or columns. This mechanism is well suited for selective replication, data integration, CDC, and migrations across major versions.

Neither option is always better than the other. Choose based on this question: do you need a standby that replaces the entire cluster, or do you need to stream a selective set of data changes to another database?

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain physical replication and logical replication in PostgreSQL.
2. Describe the WAL sender/receiver and logical decoding/apply flows.
3. Distinguish the scope of data replicated in each mechanism.
4. Explain the roles of wal_level, replication slots, publications, and subscriptions.
5. Configure a basic physical standby.
6. Configure a basic publication/subscription.
7. Understand initial copy, streaming changes, and replication progress.
8. Distinguish a read-only hot standby from a logical subscriber that can accept local writes.
9. Understand the limitations of logical replication regarding DDL, sequences, large objects, and schema compatibility.
10. Choose a replica identity for tables with UPDATE/DELETE.
11. Analyze replication lag, conflicts, and WAL retention.
12. Monitor physical/logical replication using system views.
13. Choose the appropriate mechanism for HA, DR, selective replication, CDC, and major-version migration.
14. Design cutover, failover, resynchronization, and security procedures.

## 2. Two Mechanisms at Two Different Levels

### 2.1. Physical Replication

Physical replication transmits WAL so the standby replays changes on a compatible copy of the cluster. The standby receives the same physical change history and maintains a data directory corresponding to the primary.

~~~text
Application
    |
    v
Primary PostgreSQL
    |
    | WAL records
    v
WAL sender / replication connection
    |
    v
WAL receiver on standby
    |
    v
Write and replay WAL
    |
    v
Physical standby
~~~

The standby can run hot standby to serve read queries while replaying WAL. When the primary fails, a suitable standby can be promoted to become the new primary.

### 2.2. Logical Replication

Logical replication decodes changes from WAL into logical data changes. The publisher defines the published tables; the subscriber receives initial table data if requested and continues applying changes.

~~~text
Publisher database
    |
    v
WAL at logical level
    |
    v
Logical decoding
    |
    v
Publication / logical replication protocol
    |
    v
Subscriber apply worker
    |
    v
Subscriber tables
~~~

The subscriber has its own schema and storage. It can contain a selected subset of tables from the publisher and can serve its own workload, depending on how write permissions are designed.

### 2.3. Core Differences

- Physical replication replicates cluster state at the physical level via WAL.
- Logical replication replicates logical data changes of published tables.
- A physical standby is a copy of the cluster; a logical subscriber is an independent database receiving changes by publication.
- Physical replication is suited for replacing the primary; logical replication is suited for sharing or transferring data selectively.

## 3. WAL Is the Foundation of Both

PostgreSQL uses Write-Ahead Log (WAL) to record changes needed for recovery. Physical replication sends WAL records for the standby to replay. Logical replication also relies on WAL, but the publisher needs to record enough information for logical decoding.

### 3.1. wal_level

Main levels:

| Value | Purpose |
| --- | --- |
| minimal | Information needed for local crash recovery |
| replica | Information for WAL archiving and physical replication |
| logical | Adds information for logical decoding |

Physical replication requires wal_level=replica or logical. Logical replication requires wal_level=logical on the publisher.

Example:

~~~conf
# Physical replication
wal_level = replica

# Logical replication or combined physical + logical
wal_level = logical
~~~

wal_level is a setting that requires a PostgreSQL restart to take effect. Check on the server:

~~~sql
SHOW wal_level;

SELECT name, setting, context, pending_restart
FROM pg_settings
WHERE name = 'wal_level';
~~~

### 3.2. WAL Sender and Receiver

The primary uses WAL sender processes to serve replication connections. A physical standby has a WAL receiver to receive the stream. A logical subscriber also connects to the publisher using the replication protocol, but data is sent as logical changes.

### 3.3. Replication Slots

A replication slot tracks a consumer's progress and retains WAL that the consumer still needs. There are two common types:

- Physical slot: retains WAL for a physical standby.
- Logical slot: retains WAL for logical decoding/subscriber.

Slots allow a consumer to reconnect without losing needed WAL, but an inactive slot can retain WAL for too long and fill up the disk. You need to monitor restart_lsn, consumer lag, and retention limits.

### 3.4. Archiving Still Has Its Own Role

WAL archiving stores segments in an independent location for PITR and recovery. A replication slot or streaming connection does not replace a base backup and WAL archive. A production architecture typically combines replication with backup/PITR.

## 4. Scope of Replicated Data

| Component | Physical replication | Native logical replication |
| --- | --- | --- |
| Table rows | Entire cluster state is replayed | Only tables belonging to the publication |
| Schema/DDL | Reflected via physical WAL/system catalogs | Does not automatically replicate DDL; schema must be deployed separately |
| Indexes | Yes, as part of the physical database | Does not replicate index definitions; subscriber needs its own schema/indexes |
| Constraints | Present in physical state | Schema/constraints must be created on the subscriber |
| Roles and grants | Cluster-level catalog changes are replayed | Must be managed separately |
| Sequences | Physical state is replayed | Sequence state is not synchronized like table row changes |
| Large objects | Included in physical cluster state | Not replicated like tables by native logical replication |
| Extensions | Catalog state is replayed; binaries/config are still needed on the host | Must be installed/configured appropriately on the subscriber separately |
| Other databases in the same cluster | Also included in the physical cluster copy | Publication/subscription are configured per database |
| Server configuration files | Does not automatically copy configuration files outside the data directory | Does not automatically copy |
| WAL history | Physical WAL stream | Logical changes decoded from WAL |

### 4.1. Physical Replication Is Cluster-Wide

A PostgreSQL instance can contain multiple databases. A physical standby reproduces the cluster at the physical level; it cannot selectively pick a single database or a few tables.

It also does not automatically copy everything outside the PostgreSQL data directory, such as configuration files placed at custom paths, certificates, scripts, service definitions, secrets, or application files. These parts require separate configuration management and backup.

### 4.2. Logical Replication Is Publication-Based

A publication belongs to one database and defines which tables/changes are sent. A subscriber can receive a subset of data instead of the entire cluster.

Logical replication does not automatically carry all cluster metadata. Schemas, roles, grants, extension binaries, functions, and dependencies must be managed through separate procedures.

## 5. Overview Comparison

| Criterion | Physical replication | Logical replication |
| --- | --- | --- |
| Unit of replication | Physical cluster | Changes of published tables |
| Transmitted data | WAL records | Logical row changes |
| Key configuration | wal_level=replica, sender/receiver | wal_level=logical, publication/subscription |
| Initial setup | Base backup | Pre-created schema, optional initial table copy |
| Read behavior | Hot standby is normally read-only | Subscriber is an independent database, can accept local writes |
| Table selection | No | Yes |
| Row/column filtering | No | Yes in supported versions |
| Automatic DDL | Yes via physical WAL | No |
| Sequence state | Yes | Not automatically synchronized |
| Cross-major migration | Cannot use physical WAL directly between different major versions | Can use logical replication with appropriate version direction/compatibility |
| HA failover | Primary use case | Not a physical standby replacement |
| Selective data sharing | No | Suitable |
| CDC/integration | Requires another decoder/consumer | Suitable with logical decoding |
| Lag monitoring | WAL sent/write/flush/replay | Slot LSN and subscription apply progress |
| Disk retention risk | Slot/archive/standby lag | Logical slot can retain WAL and catalog history |
| Conflict type | Recovery conflicts on standby | Apply conflicts with subscriber data/schema |
| Typical use cases | HA, DR, read replicas | CDC, migration, data distribution |

## 6. How Does Physical Replication Work?

Physical replication keeps a standby synchronized with the primary by sending WAL. The standby is initialized from a compatible base backup and then continues receiving WAL.

### 6.1. Initial Base Backup

A new standby cannot simply connect to the primary and automatically receive all historical data. It needs a base backup or a compatible consistent physical copy.

Example of creating a base backup:

~~~bash
pg_basebackup \
  --host=primary.example.internal \
  --port=5432 \
  --username=replicator \
  --pgdata=/var/lib/postgresql/standby \
  --format=plain \
  --wal-method=stream \
  --progress \
  --write-recovery-conf
~~~

The option name can be shortened to -R. The binary must be compatible with the cluster's PostgreSQL major version.

### 6.2. WAL Streaming

After the base backup completes, the standby connects to the primary, receives WAL from the required position, and replays it.

### 6.3. Hot Standby

If hot_standby is enabled and the recovery state is appropriate, the standby can serve read-only queries while replaying WAL.

~~~sql
SELECT pg_is_in_recovery();
~~~

On a standby currently in recovery, the result is normally true. The standby does not accept regular application writes.

### 6.4. Promote

When deciding to fail over, the standby can be promoted. It exits recovery mode and starts operating as the new primary, writing WAL on a new timeline.

Promotion requires a fencing procedure to ensure the old primary does not continue accepting writes.

## 7. Basic Physical Replication Configuration

### 7.1. Primary Configuration

Example:

~~~conf
wal_level = replica
max_wal_senders = 10
max_replication_slots = 10
wal_keep_size = 2GB
~~~

The numbers are illustrative only. Size senders/slots according to the number of standbys, backup clients, and other replication connections.

### 7.2. Replication Role

~~~sql
CREATE ROLE replicator
WITH LOGIN REPLICATION PASSWORD 'use-a-secret-manager';
~~~

The password is a placeholder only. Production should use secret management or an appropriate authentication mechanism, and never commit secrets to Git.

### 7.3. pg_hba.conf

Example for an internal subnet:

~~~conf
host  replication  replicator  10.20.0.0/24  scram-sha-256
~~~

Restrict network sources and use TLS according to security requirements.

### 7.4. Create Physical Slot

On the primary:

~~~sql
SELECT *
FROM pg_create_physical_replication_slot('standby_a');
~~~

### 7.5. Standby Configuration

Example:

~~~conf
primary_conninfo = 'host=primary.example.internal port=5432 user=replicator application_name=standby_a'
primary_slot_name = 'standby_a'
~~~

The base backup workflow or -R can create standby.signal and appropriate recovery connection settings. Do not create a new data directory by copying files while the primary is writing without using a consistent backup procedure.

### 7.6. Check the Primary

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
FROM pg_stat_replication;
~~~

If there are no rows, check the standby connection, authentication, pg_hba.conf, network, and logs.

## 8. Physical Replication Modes

### 8.1. Asynchronous Replication

The primary does not wait for the standby to acknowledge WAL before returning on commit. Latency is lower, but if the primary fails, commits that have not reached the promoted standby may be lost.

### 8.2. Synchronous Replication

The primary can wait for the standby to acknowledge WAL according to the synchronous replication configuration. This reduces data loss for acknowledged commits according to the chosen sync level, but can increase latency or impact availability when a synchronous standby is unavailable.

Example:

~~~conf
synchronous_standby_names = 'FIRST 1 (standby_a, standby_b)'
synchronous_commit = on
~~~

This is an illustrative configuration only; you need to clearly understand synchronous_commit, synchronous_standby_names, and the failover policy.

### 8.3. Cascading Replication

One standby can forward WAL to other standbys:

~~~text
Primary
  |
  +---- Standby A
           |
           +---- Standby B
           |
           +---- Standby C
~~~

Cascading reduces the number of direct connections to the primary and can distribute replicas by region. Each tier needs sufficient WAL, network, and capacity for downstream nodes to keep up.

### 8.4. WAL Archive and Streaming

A standby can receive WAL via streaming, fetch segments from an archive, or combine both. The archive serves as a recovery path when required segments are no longer in pg_wal on the upstream.

## 9. How Does Logical Replication Work?

Logical replication uses logical decoding to convert WAL records into table/row-level changes. The publisher emits changes according to the publication; the subscriber applies changes into the corresponding tables.

### 9.1. Publisher

The publisher is the database that owns the publication and is the source of logical changes.

### 9.2. Publication

A publication defines the tables and types of operations to publish, such as INSERT, UPDATE, DELETE, and TRUNCATE.

### 9.3. Logical Replication Slot

The slot tracks the logical decoding position that must be retained. It allows the subscriber to resume from the confirmed position upon reconnecting, provided the necessary WAL still exists.

### 9.4. Subscriber

The subscriber creates a subscription to connect to the publisher. The apply worker receives changes and updates the corresponding tables.

### 9.5. Initial Table Synchronization

When a subscription is created with copy_data enabled, PostgreSQL can copy existing data of the published tables and then transition to applying changes generated during synchronization. If copy_data=false, initial data must be loaded by another method and must be consistent with the replication start position.

### 9.6. Schema Must Exist First

Native logical replication does not automatically create the full schema on the subscriber. Tables, columns, and required structures must be created beforehand using migration/deployment tooling.

## 10. Basic Logical Replication Configuration

### 10.1. Publisher Configuration

~~~conf
wal_level = logical
max_wal_senders = 10
max_replication_slots = 10
~~~

The values must be sufficient for subscriptions, table synchronization workers, and other replication clients. wal_level requires a restart.

### 10.2. Create Publication

On the publisher database:

~~~sql
CREATE PUBLICATION sales_publication
FOR TABLE
    sales.orders,
    sales.order_items;
~~~

The publication includes only the two specified tables.

To publish all existing tables and tables created later according to FOR ALL TABLES semantics:

~~~sql
CREATE PUBLICATION all_tables_publication
FOR ALL TABLES;
~~~

FOR ALL TABLES has a broad scope; check permissions and which data is allowed to leave the publisher.

### 10.3. Create Subscriber Schema

Create the database, schemas, tables, and required indexes/constraints on the subscriber via migration tooling. A compatible schema is a prerequisite for applying changes successfully.

### 10.4. Create Subscription

On the subscriber database:

~~~sql
CREATE SUBSCRIPTION sales_subscription
CONNECTION 'host=publisher.example.internal port=5432 dbname=salesdb user=logical_reader'
PUBLICATION sales_publication
WITH (copy_data = true);
~~~

The example requires an appropriate role and authentication. Manage passwords with a secret store/credential mechanism; do not write real secrets into documentation, shell history, or repositories.

### 10.5. Check Subscription

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

Columns may vary by version. Use \d+ pg_stat_subscription or the documentation for the exact major version to understand the view schema.

### 10.6. Manual Slot Creation

A subscription usually manages the publisher-side logical slot. If a workflow creates a slot manually, you must align the slot name, plugin, LSN, and subscription options; do not create duplicate slots or leave orphaned slots without consumers.

## 11. What Can a Publication Publish?

A publication can specify operations:

~~~sql
CREATE PUBLICATION orders_changes
FOR TABLE sales.orders
WITH (publish = 'insert, update, delete, truncate');
~~~

### 11.1. INSERT

New rows are sent to the subscriber.

### 11.2. UPDATE

Row changes are sent. The subscriber must have a way to identify the old row via replica identity.

### 11.3. DELETE

Information needed to identify the deleted row is sent. Replica identity is especially important.

### 11.4. TRUNCATE

TRUNCATE can be published in supported versions. Check semantics, published tables, and cascade effects; do not assume all related objects are automatically synchronized.

### 11.5. Row Filters and Column Lists

Newer PostgreSQL versions support row filters and column lists in publications. This allows limiting the rows/columns published, but you must evaluate version compatibility and filter consistency across publisher/subscriber.

Conceptual example with a row filter:

~~~sql
CREATE PUBLICATION active_customers
FOR TABLE app.customers
WHERE (active = true);
~~~

Check exact syntax and limitations for your major version. Row filtering does not replace an overall security policy; the subscriber still needs access controls.

## 12. Replica Identity in Logical Replication

When the publisher sends UPDATE or DELETE, the subscriber needs to identify the corresponding row. PostgreSQL uses replica identity for this purpose.

### 12.1. DEFAULT

By default, PostgreSQL uses the primary key if the table has a primary key.

~~~sql
ALTER TABLE app.customers
REPLICA IDENTITY DEFAULT;
~~~

### 12.2. USING INDEX

You can choose a unique index that satisfies PostgreSQL's requirements as the replica identity.

~~~sql
ALTER TABLE app.customers
REPLICA IDENTITY USING INDEX customers_external_id_key;
~~~

The index must meet the version's requirements, including uniqueness and required attributes.

### 12.3. FULL

REPLICA IDENTITY FULL requires using the entire old row as identity information for UPDATE/DELETE.

~~~sql
ALTER TABLE app.audit_items
REPLICA IDENTITY FULL;
~~~

FULL can increase WAL/decoding/network data volume and row-lookup cost on the subscriber. Use it only when needed and after evaluating performance.

### 12.4. NOTHING

REPLICA IDENTITY NOTHING provides no identity to locate the old row. The table can publish INSERT, but UPDATE/DELETE require an appropriate identity; these operations may cause apply errors.

### 12.5. Check Identity

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relreplident AS replica_identity
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1, 2;
~~~

Values in relreplident are internal codes; consult the catalog documentation or psql to interpret them for your version.

## 13. What Native Logical Replication Does Not Automatically Replicate

This is an important distinction when designing a migration or a subscriber that might be promoted.

### 13.1. DDL

CREATE TABLE, ALTER TABLE, CREATE INDEX, and schema changes are not automatically sent as logical row changes. DDL must be deployed separately on the subscriber in a compatible order.

### 13.2. Sequence State

Sequence increments/state are not replicated like table row changes. If the subscriber is used as an independent writable database or becomes the write source after cutover, sequence values must be synchronized to avoid ID collisions.

### 13.3. Large Objects

Large objects are not published like regular tables by native logical replication. A separate copy/transfer mechanism is required.

### 13.4. Roles and Grants

Role definitions, passwords, and cluster-wide permissions are not automatically replicated through a publication. Manage them via provisioning/identity tooling.

### 13.5. Extension Binaries and Server Configuration

The subscriber host must install compatible extension binaries, configure parameters, and manage external dependencies separately.

### 13.6. Materialized Views and Other Objects

Objects not included in the publication's set of table changes are not automatically synchronized. Identify objects that need to be created/rebuilt separately.

### 13.7. Schema Evolution

When the publisher changes its schema, the subscriber must be migrated in a safe sequence. If the publisher sends a row shape that the subscriber does not yet support, the apply worker can stop with an error.

## 14. Can a Logical Subscriber Accept Data Writes?

The subscriber is a separate PostgreSQL database and is not placed in physical recovery read-only mode solely because it is receiving logical replication. Users can write local data if permissions and architecture allow it.

However, writes to tables currently being replicated can conflict with changes from the publisher.

### 14.1. Conflict Example

The publisher inserts customer_id=100. The subscriber already has a local row with customer_id=100. Applying the INSERT can encounter a unique constraint violation and the subscription worker stops applying until resolved.

### 14.2. Conflict from Local Update

The publisher updates a row, but the subscriber has also modified that row. Native logical replication does not automatically resolve every business conflict with generic merge logic.

### 14.3. Avoid Uncontrolled Dual-Write

If both sides write to the same set of tables, you need to design ownership, keyspace, conflict resolution, and loop prevention. Unidirectional native publication/subscription does not automatically create a safe multi-master system.

### 14.4. Separate Local Tables

A subscriber can hold local tables outside the publication or tables designed specifically for the subscriber application. Clear ownership separation helps avoid conflicts.

## 15. Physical Replication and Logical Replication in HA

### 15.1. Physical Standby Is the Common Choice for HA

A standby receives physical WAL, maintains corresponding cluster state, and can be promoted. This is the familiar model for primary/standby.

### 15.2. A Logical Subscriber Is Not a Hot Standby

A subscriber is not a physical copy of the cluster. It does not automatically have all databases, roles, sequence states, extension states, and DDL of the publisher.

### 15.3. Physical Failover

When the primary fails, promote a physical standby after fencing and evaluating replication lag. Then rebuild replicas against the new primary.

### 15.4. Logical Cutover

Logical replication is commonly used for migrations: synchronize data to the target cluster, check lag, stop writes or establish a cutover point, wait for all changes to be applied, synchronize remaining metadata, and switch the application.

### 15.5. Do Not Call Logical Cutover a Standby Promotion

Logical cutover means switching the application to an independent database that has received the data. It involves schema, sequence, permissions, validation, and routing steps that differ from physical promotion.

## 16. Logical Replication for Major-Version Migration

Physical WAL is not a mechanism for directly transferring a data directory between two different PostgreSQL major versions. Logical replication can support migrating from an older publisher to a newer subscriber if versions and features are compatible.

### 16.1. Migration Flow

~~~text
Old PostgreSQL cluster
  Publisher / publication
          |
          | Initial copy + logical changes
          v
New PostgreSQL cluster
  Subscriber
          |
          v
Validate schema and data
          |
          v
Catch up to cutover point
          |
          v
Switch application writes
~~~

### 16.2. Schema Preparation

Deploy a compatible schema to the subscriber before replicating. Ensure types, columns, constraints, and indexes match the incoming data.

### 16.3. Initial Copy

The subscription can copy initial table data. For large databases, account for copy duration, network, disk I/O, locks, and the publisher's ability to continue serving writes.

### 16.4. Monitoring Catch-Up

Monitor slot LSN, subscription progress, and apply rate. Do not cut over while the subscriber still has lag or apply errors.

### 16.5. DDL During Migration

Apply DDL on both sides following a tested sequence. Avoid changing column/table shapes on the publisher before the subscriber is compatible.

### 16.6. Sequences and Metadata

Before switching writes, synchronize sequence values, roles, grants, extensions, functions, triggers, indexes, and objects outside the publication.

### 16.7. Cutover

Stop writes on the publisher or put the application into maintenance/read-only mode, wait for the subscriber to apply all changes, verify counts/aggregates, perform final sequence/metadata synchronization, and switch the connection endpoint.

### 16.8. Rollback Plan

Once the subscriber begins receiving new writes, rolling back to the old publisher is no longer straightforward. You must define a reverse data flow or keep the old publisher read-only and have a way to reconcile post-cutover changes.

## 17. Logical Replication for CDC and Data Integration

Logical decoding can supply row changes to subscribers or other consumers via an output plugin/replication protocol.

Use cases:

- Syncing selected tables to an analytics database.
- Streaming changes into Kafka or an event pipeline via a connector.
- Syncing data to a search/indexing system.
- Building a read model for another workload.
- Data integration across services.
- Downstream audit/change processing.

### 17.1. CDC Is Not Event Sourcing

WAL-derived row changes reflect database mutations. They do not automatically explain business intent such as "customer approved contract" if the schema does not store that business event.

### 17.2. Ordering and Transactions

Logical replication preserves transaction semantics at the appropriate protocol/apply level. External consumers must understand commit boundaries, ordering, duplicate/retry, and connector checkpoint behavior.

### 17.3. Idempotency

Downstream consumers may retry or reprocess events. Use event identity, source LSN/transaction metadata, and idempotent writes to avoid duplicate effects.

### 17.4. Schema Changes

CDC consumers must handle schema evolution. If the downstream schema registry or topic format is incompatible, the pipeline can stop even though the PostgreSQL publisher is still running.

## 18. Performance and Resource Comparison

There is no fixed overhead ratio for every workload. Impact depends on write volume, row width, indexes, replica identity, network, subscriber apply rate, and retention.

| Resource | Physical replication | Logical replication |
| --- | --- | --- |
| Primary CPU | WAL generation, sender/network | WAL generation, decoding, filtering/encoding |
| Network | WAL stream | Logical changes; may be less or more depending on data/schema |
| Primary disk | WAL and slot retention | WAL/slot retention, potentially additional catalog retention |
| Standby/subscriber CPU | WAL write/replay | Apply row changes, maintain indexes/constraints |
| Storage | Physical cluster copy | Based on subscribed schema/data and local indexes |
| Apply behavior | Replay physical WAL | Execute logical changes |
| Lag bottleneck | Network, write, flush, replay | Decode, network, apply, locks/indexes |
| Scaling | Can add physical read replicas | Select multiple subscribers/projections per workload |

### 18.1. Physical Replay

Physical replay is usually efficient for maintaining a physical copy because it does not convert each row into a SQL statement on the subscriber. However, replay is still affected by storage I/O, WAL rate, network, and recovery conflicts.

### 18.2. Logical Apply

Logical apply executes changes on the subscriber, maintains indexes/constraints, and can consume significant CPU/I/O. A subscriber with local workloads or heavy indexes may apply slower than the publisher generates changes.

### 18.3. Row Width and Replica Identity

REPLICA IDENTITY FULL can make logical changes larger. Wide tables/full-row updates and frequent UPDATE workloads need benchmarking.

### 18.4. Initial Sync

Initial table copy can place heavy load on publisher/subscriber. Schedule carefully, limit workers, and measure disk/network before migrating.

## 19. Replication Lag: Two Mechanisms, Two Perspectives

### 19.1. Physical Lag

On the primary:

~~~sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
~~~

The LSNs represent milestones for sent, write, flush, and replay. You can compute byte gaps:

~~~sql
SELECT
    application_name,
    pg_wal_lsn_diff(sent_lsn, write_lsn) AS bytes_not_written,
    pg_wal_lsn_diff(write_lsn, flush_lsn) AS bytes_not_flushed,
    pg_wal_lsn_diff(flush_lsn, replay_lsn) AS bytes_not_replayed
FROM pg_stat_replication;
~~~

### 19.2. Standby Receive/Replay

On the standby:

~~~sql
SELECT
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn,
    pg_last_xact_replay_timestamp() AS last_replayed_commit;
~~~

The last timestamp can look stale when the primary has few writes; combine LSN delta and WAL activity.

### 19.3. Logical Subscription Progress

On the subscriber:

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

The view provides worker status and receive/apply progress depending on the version. Inspect the actual schema with psql or catalog docs before building dashboards tied to specific columns.

### 19.4. Logical Slot Progress

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
ORDER BY slot_type, slot_name;
~~~

restart_lsn indicates the earliest WAL the slot still requires; confirmed_flush_lsn indicates the position the logical consumer has confirmed. The two values are not necessarily equal.

### 19.5. Measure Lag Beyond Time Alone

Use byte/LSN gaps, WAL generation rate, consumer apply rate, and time since last progress. A replay_lag figure can be NULL or misleading during low-write workloads.

## 20. WAL Retention and Replication Slots

Both physical and logical slots can retain WAL on the publisher.

### 20.1. Physical Slot

Retains WAL needed for the standby. If the standby goes offline, the primary can retain segments until the standby reconnects or the slot is capped/invalidated.

### 20.2. Logical Slot

Retains WAL needed for logical decoding. If a CDC consumer stops, the slot can retain WAL and catalog history, causing disk growth or vacuum retention.

### 20.3. max_slot_wal_keep_size

Limits the amount of WAL retained by replication slots. If exceeded, the slot may lose the ability to resume from its previous position once needed WAL is removed. This is a trade-off between disk protection and resumability.

### 20.4. wal_keep_size

Retains a minimum amount of WAL in pg_wal to support standbys. This is not a total WAL cap or a fixed retention duration.

### 20.5. max_wal_size

Is a soft target related to checkpoints, not a hard cap on pg_wal. Slots and archive backlogs can still grow the WAL directory beyond it.

### 20.6. Monitoring Slots

Monitor active, restart_lsn, confirmed_flush_lsn, retained WAL estimate, safe_wal_size, and owner. Do not drop a slot solely because it is inactive without verifying its consumer.

## 21. Conflicts and Apply Errors

### 21.1. Physical Recovery Conflicts

A hot standby serves read queries while replaying WAL. A long-running query can conflict with cleanup/replay on the standby. PostgreSQL may delay replay or cancel the query depending on recovery conflict settings.

Settings such as max_standby_streaming_delay and hot_standby_feedback affect the trade-off between query availability and replay/vacuum behavior.

### 21.2. Logical Apply Conflicts

Logical apply can encounter unique violations, missing target rows, incompatible schemas, permission errors, or constraint failures. The apply worker can stop applying until the error is resolved.

### 21.3. Do Not Arbitrarily Modify Subscriber Data

If the subscriber has local writes on replicated tables, conflicts can recur. Identify ownership and the source of truth before making fixes.

### 21.4. Skipping Transactions Is Not the Default Solution

Some workflows allow skipping a failing transaction, but doing so causes the subscriber to diverge. Only do this when you understand the exact transaction, accept the consequences, and have a resync/validation procedure.

### 21.5. Resyncing Tables

If a subscriber table diverges or initial sync fails, you may need to re-copy the table using the subscription/table synchronization procedure or rebuild subscriber data. Do not delete the slot before knowing the publisher/subscriber state.

## 22. Logical Replication and Schema Evolution

Because DDL does not replicate automatically, schema rollouts require coordination.

### 22.1. Additive Change

A generally safer procedure:

1. Add a compatible column on the subscriber.
2. Add the column on the publisher.
3. Update the publication/column list if needed.
4. Deploy the application compatible with both schemas.
5. Backfill if needed.
6. Monitor apply.
7. Remove the old column after all consumers no longer need it.

### 22.2. Rename Column

Renames are not automatically transmitted as DDL by logical replication. Deploy compatible changes on both sides and check mapping/column lists.

### 22.3. Drop Column

Do not drop a publisher column while subscribers/consumers still need it. Perform deprecation and removal in rollout stages.

### 22.4. Type Change

Check type conversion compatibility and the subscriber column. A type change can cause the apply worker to error or produce different semantics.

### 22.5. DDL Deployment Order

For changes required by apply, prepare the subscriber schema before the publisher begins sending the new row shape. Plan migrations with a rollback/reconciliation plan.

## 23. Sequences and Logical Cutover

Sequence state is not synchronized like table rows by native logical replication.

### 23.1. Why Does This Matter?

Suppose the publisher has generated order_id up to 500000, the subscriber's initial copy has data up to 499000, but the subscriber's sequence is still at a lower value. After cutover, new inserts can collide with existing primary keys.

### 23.2. Synchronizing Sequences

Before cutover, stop writes or establish a consistent point, retrieve sequence values from the publisher, and set sequences on the subscriber higher than all used IDs.

Example check:

~~~sql
SELECT last_value, is_called
FROM sales.orders_order_id_seq;
~~~

Adjustment examples must be based on the actual sequence, ID column, cache, and concurrency. Do not apply a generic setval statement without determining a safe value.

### 23.3. Identity Columns

Identity columns also rely on sequence semantics. Check the underlying sequence and ownership.

### 23.4. Other ID Sources

If the application uses UUIDs or an external ID generator, check generator/clock/worker coordination and unique constraints before switching writes.

## 24. Replication Security

### 24.1. Replication Role

Grant least privilege for the replication connection. Do not use superuser for every subscriber/standby unless required.

### 24.2. Network

Restrict pg_hba.conf by IP/subnet and role. Expose the replication port only on necessary networks; use TLS and appropriate network segmentation.

### 24.3. Physical Data Access

A physical standby contains a copy of the entire cluster, so host/volume/backup access on the standby can be equivalent to very broad data access.

### 24.4. Logical Data Scope

Publications can restrict tables/rows/columns depending on feature/version. Even so, logical replication remains a data export channel; protect credentials, subscription connections, slot ownership, and subscriber storage.

### 24.5. Credentials

Do not hard-code passwords in Git, command history, or logs. Use .pgpass with proper permissions, a secret manager, or the environment's credential mechanism.

### 24.6. Subscriber Permissions

Control who can read/write on the subscriber. Do not assume publication filtering is the sole authorization layer.

## 25. When to Choose Physical Replication?

Choose physical replication when:

- You need a standby that can replace the primary.
- You need HA/failover for the entire cluster.
- You need a read-only hot standby.
- You need a physical replica nearly identical to the primary.
- You need cascading physical replicas.
- You need DR with WAL shipping/streaming.
- You need a physical clone for appropriate operational purposes.

Physical replication is usually the primary choice for traditional PostgreSQL HA.

### 25.1. Not Suitable When Selecting Only a Few Tables

A physical standby carries the entire cluster. If you only want to share the customers and orders tables with an analytics database, logical replication is more suitable.

### 25.2. Major-Version Migration

Physical WAL is not a direct mechanism for replicating between two different major versions. Use logical replication or an appropriate upgrade/migration tool.

## 26. When to Choose Logical Replication?

Choose logical replication when:

- You only need a subset of tables or selected data.
- You need CDC to another system.
- You need to migrate to an independent cluster or a newer major version.
- The subscriber needs its own schema/storage.
- You need data distribution by tenant/table/row filter in supported versions.
- You need to build a read model or downstream database.

### 26.1. Do Not Replace Physical HA When Full-Cluster Failover Is Required

A logical subscriber does not automatically contain all cluster metadata and objects. If used as a failover target, you must build out the full schema, roles, sequences, extensions, DDL, permissions, and cutover/reconciliation process.

### 26.2. Do Not Use When Schema Drift Is Unmanaged

If both sides change DDL independently, apply errors and divergence occur easily. Schema migration discipline is required.

## 27. Can Physical and Logical Be Combined?

Yes. A single primary can serve physical standbys for HA and logical slots/publications for CDC or selective replication.

~~~text
                    +--> Physical standby A
                    |
Primary PostgreSQL -+--> Physical standby B
                    |
                    +--> Logical subscriber / analytics
                    |
                    +--> CDC connector / event pipeline
~~~

When combining:

- The publisher needs wal_level=logical because that level is required for logical decoding.
- Size max_wal_senders and max_replication_slots sufficiently for both types of consumers.
- Monitor each slot and consumer lag.
- Provision WAL disk space for standby/CDC outages.
- Archive WAL for independent PITR.
- Define failover behavior for logical consumers and slot synchronization according to version/tooling.
- Do not let a CDC outage fill up the primary disk.

## 28. Version Compatibility

### 28.1. Physical Replication

Physical replication requires physical WAL/data format compatibility, typically the same PostgreSQL major version. Minor versions within the same major series are designed for compatibility, but upgrade guidance must be followed.

Do not directly copy WAL/data directories between two different major versions and expect the standby to operate as a physical replica.

### 28.2. Logical Replication

Logical replication can connect a publisher and subscriber on different major versions within PostgreSQL's supported limits. A common migration direction is an older major version publisher to a newer major version subscriber.

Check:

- Publisher/subscriber version pair.
- Logical protocol/output plugin compatibility.
- Publication features such as row filters/column lists.
- Data type compatibility.
- DDL/schema differences.
- Extension behavior.
- Slot/failover capabilities of the versions.

### 28.3. Do Not Assume All Features Coexist

Logical replication features are added across major versions. Consult documentation for both publisher and subscriber versions, and test on the exact planned version pair.

## 29. Monitoring Physical Replication

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
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
~~~

On the standby:

~~~sql
SELECT *
FROM pg_stat_wal_receiver;
~~~

Monitor:

- Connection state and sender count.
- WAL sent/write/flush/replay LSNs.
- Byte lag and time lag.
- Last receive/last replay.
- Replication slot activity and retained WAL.
- Filesystem free space.
- Recovery conflicts/cancelled queries.

## 30. Monitoring Logical Replication

On the subscriber:

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

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

Monitor:

- Subscription enabled/disabled.
- Apply worker state.
- Last received/applied progress by version.
- Slot active/inactive.
- restart_lsn and confirmed_flush_lsn.
- Retained WAL estimate.
- Apply errors and conflicts.
- Table synchronization progress.
- Consumer/downstream checkpoint if using CDC.

### 30.1. Retained WAL Estimate

Example LSN gap estimate:

~~~sql
SELECT
    slot_name,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
    ) AS retained_wal_estimate
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL;
~~~

This is an LSN gap estimate, not exclusive disk usage of a single slot; multiple consumers can share required segments.

### 30.2. Inactive Slots

active=false does not mean the slot is not retaining WAL. Identify the owner and consumer before dropping it.

### 30.3. Apply Lag

A logical subscriber may receive WAL yet apply slowly. Monitor apply progress and error logs, not just network connectivity.

## 31. Troubleshooting Physical Replication

### 31.1. Standby Cannot Connect

Check primary_conninfo, network/DNS/firewall, pg_hba.conf, replication role/password, TLS certificates, max_wal_senders, and PostgreSQL logs on both nodes.

### 31.2. Requested WAL Segment Has Been Recycled

The standby needs WAL that is no longer in pg_wal. Check the physical slot, wal_keep_size, and archive. If the archive has the segment, configure the restore path. If the required WAL no longer exists, you may have to rebuild the standby from a base backup.

### 31.3. Replay Lag Increasing

Check storage I/O, network throughput, WAL generation bursts, long-running queries/conflicts, and standby CPU.

### 31.4. Primary Disk Growing

Check inactive slots, archive failures, and standby lag. Do not manually delete files in pg_wal.

### 31.5. Unsafe Promotion

Verify the old primary has been fenced and determine RPO before promoting. Avoid split brain.

## 32. Troubleshooting Logical Replication

### 32.1. Subscription Cannot Connect

Check the connection string, pg_hba, role, password, network, publisher database, and publication name.

### 32.2. Apply Worker Schema Error

Compare table definitions, column names/types, replica identity, and DDL rollout order.

### 32.3. Unique Violation

Look for local writes or initial copy data colliding with the publisher. Identify the source of truth and resolve conflicts in a controlled manner.

### 32.4. UPDATE/DELETE Not Applying

Check replica identity, whether the row exists on the subscriber, and whether the subscriber has diverged.

### 32.5. Slot Retaining Too Much WAL

Check active state, restart_lsn, confirmed_flush_lsn, consumer logs, and max_slot_wal_keep_size. Recover the consumer or plan a resnapshot if the slot loses WAL.

### 32.6. Subscriber Cannot Keep Up

Check apply CPU, indexes, constraints, locks, network, initial sync, and worker count. Benchmark before increasing workers because more workers can increase contention.

## 33. Designing a Migration with Logical Replication

A controlled migration typically consists of the following phases:

### Phase 1: Discovery

Inventory databases/tables, sizes, write rates, DDL, extensions, large objects, sequences, roles, grants, jobs, and external dependencies.

### Phase 2: Compatibility

Verify publisher/subscriber versions, data types, collation, extensions, schema, and publication features.

### Phase 3: Provision Subscriber

Create the target cluster/database, configure network/security, schema, indexes, constraints, and roles.

### Phase 4: Start Replication

Create the publication/subscription, choose copy_data, verify initial table sync, and monitor WAL slots.

### Phase 5: Validate

Compare row counts, key sets, aggregates, constraints, application read paths, and apply lag.

### Phase 6: Cutover

Stop writes or control the write window, wait for the subscriber to catch up, synchronize sequences/metadata, switch the application endpoint, and verify.

### Phase 7: Stabilize

Monitor errors/latency, keep the old publisher read-only during the rollback window, and clearly document the conditions for closing the rollback window.

## 34. Designing HA with Physical Replication

A typical HA architecture:

~~~text
Application
     |
     v
Connection proxy / service endpoint
     |
     v
Primary PostgreSQL
     |
     +---- Physical standby A
     |
     +---- Physical standby B
     |
     +---- WAL archive / backup repository
~~~

You must design sync/async policy and RPO, fencing and leader election, promotion/rejoin procedures, replication slots and WAL capacity, independent archive/PITR, monitoring and alerts, restore/failover drills, and network/storage failure domains.

## 35. Backups Cannot Be Replaced by Replication

A physical standby can receive an accidental DELETE. A logical subscriber can also receive a DELETE if the publication allows it. Replication propagates changes; it does not automatically create an immutable history.

A backup strategy needs:

- Periodic base backups.
- Continuous WAL archiving if PITR is required.
- Backup copies in a different failure domain.
- An appropriate retention policy.
- Encryption and access controls.
- Verification and restore drills.

## 36. Design Decisions to Document

| Decision | Question |
| --- | --- |
| Replication type | Need a cluster copy or selective data? |
| Data scope | Entire cluster, database, table, or row? |
| Version | Do we need different major versions? |
| Initial copy | Base backup or logical table sync? |
| DDL | Who deploys schema changes and in what order? |
| Sequence | How are sequences synchronized at cutover? |
| Writes | Single primary or does the subscriber also write? |
| Conflicts | How are unique/missing-row conflicts handled? |
| Retention | What is the slot/WAL outage budget? |
| HA/DR | What are the failover/fencing and recovery targets? |
| Security | Who can read the replication stream and subscriber data? |
| Monitoring | How are LSN, apply lag, slots, and disk monitored? |

## 37. Common Anti-Patterns

| Anti-pattern | Consequence | Right approach |
| --- | --- | --- |
| Using a logical subscriber as a physical standby | Missing cluster metadata/objects and failover semantics | Use physical replication for HA or build a complete migration plan |
| Assuming physical replication can select a few tables | Replicates the entire cluster | Use logical publication |
| Assuming logical replication copies DDL automatically | Subscriber schema drift/apply failure | Manage schema migrations separately |
| Forgetting sequence state during cutover | ID collisions | Synchronize sequences before enabling writes |
| Not configuring replica identity | UPDATE/DELETE fails to apply | Primary key or appropriate identity |
| Using REPLICA IDENTITY FULL indiscriminately | WAL/network/apply overhead | Use an appropriate key/index when possible |
| Allowing both subscriber and publisher to write without ownership | Conflicts/divergence | Single-writer or clear conflict strategy |
| Not monitoring logical slots | WAL retained too long, disk fills up | Monitor restart_lsn/active/retention |
| Assuming wal_keep_size is a hard cap | pg_wal can still grow | Monitor slots/archive/disk |
| Assuming replication replaces backups | Accidental deletes are replicated | Base backup + WAL archive/PITR |
| Promoting standby when primary is not fenced | Split brain | Fencing and quorum |
| Using physical WAL across major versions | Incompatible | Upgrade tool or logical migration |
| Ignoring DDL ordering | Apply worker errors | Coordinated schema rollout |
| Setting copy_data=false when subscriber has no data | Subscriber misses initial rows | Consistent preload or initial copy |
| Increasing apply workers without measuring | Increased contention and I/O | Benchmark per workload |
| Dropping inactive slot without verifying owner | Consumer loses resumability | Inventory and lifecycle |
| Using publication ALL TABLES without controls | Unexpected data exposure | Scope publication per policy |
| Not testing failover/cutover | RTO/RPO does not meet expectations | Periodic drills |

## 38. PostgreSQL Practical Exercises

Perform these on two PostgreSQL clusters in a lab. Do not alter replication or failover in production without an operational plan.

1. **Concept:** explain physical replication at the WAL level.
2. **Concept:** explain logical replication at the row-change level.
3. **Diagram:** draw primary, WAL sender, receiver, and physical standby.
4. **Diagram:** draw publisher, publication, logical slot, and subscriber.
5. **Scope:** demonstrate that physical replication carries the entire cluster.
6. **Scope:** create a publication containing only two tables.
7. **wal_level:** read the current wal_level value.
8. **Configuration:** explain why logical replication requires wal_level=logical.
9. **Restart:** identify which settings require a restart.
10. **Role:** create a replication role in the lab.
11. **pg_hba:** restrict replication connections by subnet.
12. **Physical slot:** create a physical replication slot.
13. **Base backup:** create a standby using pg_basebackup.
14. **Standby signal:** inspect the recovery/standby configuration created by -R.
15. **Physical status:** read pg_stat_replication.
16. **Receiver:** read pg_stat_wal_receiver on the standby.
17. **Replay:** compare receive LSN and replay LSN.
18. **Hot standby:** run SELECT on the standby and check pg_is_in_recovery().
19. **Read-only:** attempt a write on the standby and observe the behavior.
20. **Promote:** practice promoting a lab standby.
21. **Fencing:** draw a procedure ensuring the old primary does not write after failover.
22. **Async:** describe data loss risks when an asynchronous standby lags.
23. **Sync:** configure synchronous_standby_names in the lab.
24. **Commit:** compare synchronous_commit modes according to your version's documentation.
25. **Cascading:** create a primary → standby A → standby B diagram.
26. **Archive:** configure WAL archiving for physical recovery.
27. **Slot lag:** take a standby offline and observe retained WAL.
28. **wal_keep_size:** explain why this is not a time limit.
29. **max_slot_wal_keep_size:** set a cap in the lab and explain the invalidation risk.
30. **Logical prerequisites:** check max_wal_senders/max_replication_slots.
31. **Publication:** create a publication for the orders table.
32. **Subscription:** create a subscriber and subscription.
33. **Initial copy:** enable copy_data and observe table synchronization.
34. **Preload:** test copy_data=false after loading consistent data.
35. **INSERT:** insert a row on the publisher and verify on the subscriber.
36. **UPDATE:** update a row and observe logical apply.
37. **DELETE:** delete a row and verify behavior.
38. **TRUNCATE:** test a publication with/without publishing truncate according to your version.
39. **Replica identity:** inspect a table with a primary key.
40. **Identity index:** choose a unique index as replica identity in the lab.
41. **FULL:** enable REPLICA IDENTITY FULL and observe WAL/traffic changes.
42. **NOTHING:** explain the limitations on UPDATE/DELETE.
43. **Row filter:** create a publication row filter if supported by your version.
44. **Column list:** test a column list and check version compatibility.
45. **DDL:** add a column on one side and observe why DDL does not replicate automatically.
46. **Schema rollout:** deploy compatible DDL on both publisher/subscriber.
47. **Sequence:** compare sequence values on both sides.
48. **Sequence cutover:** synchronize sequences before enabling writes on the subscriber.
49. **Large objects:** plan a separate transfer for large objects.
50. **Roles:** create roles/grants on the subscriber via provisioning.
51. **Extension:** verify extension binaries on the subscriber.
52. **Local writes:** create a unique key conflict on the subscriber and observe the apply error.
53. **Conflict repair:** plan how to reconcile conflicted data.
54. **Loop prevention:** draw a bidirectional topology and point out loop risks.
55. **Physical vs logical:** compare a read-only hot standby and a writable subscriber.
56. **Major version:** explain why physical WAL is not a major-upgrade transport.
57. **Migration:** plan a logical migration from an older version to a newer version.
58. **Cutover:** stop writes, wait for apply, and switch endpoints in the lab.
59. **Rollback:** explain why returning to the old publisher after the subscriber receives writes requires reconciliation.
60. **CDC:** design a consumer using logical decoding to send changes into an event pipeline.
61. **Ordering:** describe transaction boundaries and ordering that a CDC consumer must preserve.
62. **Idempotency:** design downstream processing resilient to duplicate events.
63. **Monitoring:** query pg_stat_subscription.
64. **Slot monitoring:** read restart_lsn and confirmed_flush_lsn.
65. **Retention estimate:** estimate WAL bytes from current LSN to restart_lsn.
66. **Inactive slot:** find an inactive slot and identify its owner.
67. **Disk growth:** simulate a stopped logical consumer and observe WAL retention.
68. **Physical lag:** calculate sent/write/flush/replay LSN deltas.
69. **Logical lag:** compare publisher slot progress with subscriber apply progress.
70. **Apply worker:** locate errors in subscriber logs.
71. **Schema conflict:** create a type mismatch in the lab and resolve it.
72. **Missing row:** simulate an UPDATE/DELETE that cannot find the matching row.
73. **Resync:** build a table resynchronization procedure.
74. **Performance:** benchmark physical replay and logical apply on the same workload.
75. **Initial sync:** measure large table copy duration and network throughput.
76. **Security:** configure TLS and least-privilege replication access.
77. **Publication scope:** audit published tables before deployment.
78. **HA design:** design physical primary/standby with archiving and backups.
79. **Combined design:** add logical CDC to a physical HA architecture and size sender/slot capacity.
80. **Comprehensive design:** choose physical/logical replication for a system requiring HA, major-version migration, selective data sharing, CDC, cutover, backup/PITR, monitoring, and conflict management.

## 39. Selection and Deployment Checklist

### Mechanism Selection

- [ ] Determine whether you need a whole-cluster copy or selected table changes.
- [ ] Determine whether you need HA/failover or selective data distribution.
- [ ] Determine whether different PostgreSQL major versions are required.
- [ ] Determine whether the subscriber will accept local writes.
- [ ] Determine how DDL, sequences, roles, extensions, and large objects will be transferred.

### Physical Replication

- [ ] wal_level=replica or logical.
- [ ] Compatible base backup.
- [ ] Sufficient max_wal_senders/max_replication_slots.
- [ ] Correct pg_hba/network/TLS/replication role.
- [ ] Retention budget for slots/archive/wal_keep_size.
- [ ] Monitoring for receive/write/flush/replay lag.
- [ ] Fencing, promote, rejoin, and restore drills.

### Logical Replication

- [ ] Publisher wal_level=logical.
- [ ] Publication scope reviewed.
- [ ] Subscriber schema deployed beforehand.
- [ ] Replica identity satisfies UPDATE/DELETE.
- [ ] Initial copy or preload has consistency.
- [ ] DDL/sequences/roles/extensions synchronized separately.
- [ ] Sufficient subscription/slot/worker capacity.
- [ ] Conflict, resync, and cutover rehearsed.

### Data Protection

- [ ] Independent base backups.
- [ ] Continuous WAL archiving for PITR.
- [ ] Retention and disk alerts.
- [ ] Replication credentials protected.
- [ ] Subscriber access restricted.
- [ ] Periodic restore/failover/migration tests.

## 40. Summary

Physical replication and logical replication both transmit changes from a PostgreSQL publisher/primary to another server, but they differ in data level, scope, and purpose:

~~~text
PHYSICAL
Primary
  -> WAL records
  -> Physical standby
  -> Whole-cluster copy
  -> HA / failover / read-only standby

LOGICAL
Publisher
  -> WAL logical decoding
  -> Publication / slot
  -> Logical changes
  -> Subscriber tables
  -> Selective replication / CDC / migration
~~~

Key principles:

- **Physical replication replicates the cluster at the physical level.** It is well suited for standbys, HA, failover, cascading, and read scaling.
- **Logical replication replicates changes of published tables.** It is well suited for selective replication, CDC, data integration, and many major-version migration scenarios.
- **A physical standby is normally read-only in recovery; a logical subscriber is an independent database.** Local writes on the subscriber can conflict with apply.
- **Logical replication does not automatically replicate DDL, sequence state, roles, grants, or large objects.** Separate schema and metadata procedures are required.
- **Replica identity determines how UPDATE/DELETE finds rows on the subscriber.** Primary key is a good default when appropriate.
- **Replication slots retain WAL for consumers but can fill up the disk.** Monitor restart_lsn, confirmed_flush_lsn, inactive slots, and retained WAL.
- **HA does not replace backups.** Both physical and logical replication can propagate an erroneous change; base backups and WAL archives are required for PITR.
- **Migrating with logical replication requires schema compatibility, initial sync, sequence synchronization, cutover, and a rollback plan.**
- **Choose the mechanism based on operational goals.** If you need to replace the entire cluster, prioritize physical; if you need selective data sharing or CDC, consider logical; many systems need a combination of both.

A solid PostgreSQL design clearly defines the source of truth, data scope, write permissions, schema handling, retention, and recovery path for each consumer. Only when these decisions are tested alongside HA, backup, and migration drills does replication truly meet the system's goals.
