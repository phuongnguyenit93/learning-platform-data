# Initial Data Synchronization and the Change Apply Process in PostgreSQL Logical Replication

PostgreSQL logical replication streams data changes from a **publisher** to one or more **subscribers**. When creating a new subscription, PostgreSQL typically performs two tasks:

1. **Initial table synchronization:** copies existing rows from the publisher into the corresponding tables on the subscriber.
2. **Continuous change apply:** streams and applies subsequent transactions so the subscriber continues keeping up with the publisher.

These two phases must coordinate with each other. If you only COPY old data and start receiving changes afterward, transactions occurring during the COPY could be missed. If you COPY and apply the same change simultaneously without a coordination mechanism, data can be duplicated or conflict.

Logical replication solves this problem using snapshots, replication slots, table synchronization workers, LSNs, and the apply worker. The lesson **“Initial Data Synchronization and Change Apply”**, part of the **Logical Replication** chapter in the **Database Engine Relational PostgreSQL** module, explains how these components coordinate, how to configure subscriptions, monitor status, handle errors, and cut over applications to a subscriber.

> **Mental model:** initial synchronization copies the state already present at a snapshot; meanwhile, PostgreSQL retains and replays changes generated around the copy window. As each table catches up with the main apply stream, it transitions to normal replication state.

---

## 1. Publisher and subscriber

Logical replication has two roles:

- **Publisher:** the database that publishes changes through one or more publications.
- **Subscriber:** the database that subscribes to a publication through a subscription and applies the received changes.

~~~text
Application writes data
        |
        v
    Publisher
        |
        | WAL logical decoding
        v
   Publication stream
        |
        | network / replication protocol
        v
    Subscriber
        |
        v
    Apply worker
        |
        v
  Subscriber tables
~~~

A publication defines which tables and operation types are published. A subscription stores the connection to the publisher, publication names, replication slot, and operational options.

Logical replication is a unidirectional mechanism following the publisher/subscriber configuration. It does not automatically form a multi-master system.

## 2. Publication and subscription

Create a publication on the publisher:

~~~sql
CREATE PUBLICATION app_publication
FOR TABLE public.customers, public.orders;
~~~

Create a subscription on the subscriber:

~~~sql
CREATE SUBSCRIPTION app_subscription
CONNECTION 'host=publisher.example port=5432 dbname=appdb user=repl_user'
PUBLICATION app_publication;
~~~

When the subscription is enabled and the `copy_data` option keeps its default value, PostgreSQL starts initial synchronization for the tables requiring sync, then continues applying changes.

These examples are illustrative configurations. Use hostnames, databases, roles, TLS, and secret handling appropriate for your actual environment.

### 2.1. Prerequisite conditions

On the publisher, you typically need:

- `wal_level = logical`.
- Sufficient `max_replication_slots`.
- Sufficient `max_wal_senders`.
- A publication containing the exact tables to synchronize.
- A connection role with replication privilege and read privilege on the data to copy.
- `pg_hba.conf` allowing replication connections from the subscriber.

On the subscriber, you need:

- Target database and tables already created.
- Compatible schemas.
- Privileges to create subscriptions and write to target tables.
- Sufficient logical replication workers.
- Stable connectivity to the publisher.

Some parameters require a restart to take effect; check the setting's context before making changes.

## 3. What is initial synchronization?

Initial synchronization is the process of copying data that already exists on the publisher at the time a snapshot is established.

For example, suppose a publisher table has 10 million rows when the subscription is created. The subscriber needs to receive those 10 million rows before it can be considered fully synchronized.

~~~text
Publisher table at snapshot S
       |
       | COPY existing data
       v
Subscriber table
~~~

Initial synchronization is not just a standalone COPY statement. PostgreSQL must also handle changes generated while COPY is running so the subscriber does not miss data.

## 4. Why is a snapshot needed?

Suppose the initial copy starts at 10:00 and finishes at 10:20. During that window, the publisher continues receiving INSERT, UPDATE, and DELETE operations.

If you only copy a snapshot at 10:00 without retaining post-snapshot changes, the subscriber will miss transactions committed during those 20 minutes.

If you recopy data after every change without a clear boundary, duplicate rows or out-of-order application can occur.

A snapshot provides a consistent view for COPY. The WAL logical stream records changes after that boundary. PostgreSQL coordinates both sources to produce a continuous state.

## 5. Initial table synchronization flow

Conceptually, a table is synchronized through the following steps:

1. The subscriber identifies a table that needs initial sync.
2. PostgreSQL spawns a table synchronization worker.
3. The worker obtains a consistent snapshot from the publisher.
4. The worker COPYs snapshot data into the subscriber table.
5. Changes generated after the snapshot are retained in the appropriate WAL/replication slot stream.
6. The worker applies the remaining changes to catch up to the main apply stream.
7. Once the table is synchronized to a safe handoff point, the table state becomes ready.
8. The main apply worker continues processing new changes for that table.

~~~text
Publisher snapshot
       |
       v
Table sync worker
       |
       +------ COPY snapshot rows ------> Subscriber table
       |
       +------ Stream changes after snapshot
                         |
                         v
                 Catch-up / apply
                         |
                         v
                 Table state = ready
                         |
                         v
                 Main apply worker
~~~

PostgreSQL manages LSNs, replication origins, and internal states so there is no gap between COPY and streaming apply.

## 6. Table synchronization worker

A subscription has a main apply worker. During initial sync, PostgreSQL can launch additional table synchronization workers to synchronize individual tables.

These workers:

- Connect to the publisher.
- Obtain a snapshot and COPY the table's data.
- Track the WAL changes relevant to the snapshot/COPY window.
- Catch up with the apply stream.
- Hand the table over to the main apply worker.

Each table sync worker handles one table during the initial synchronization phase. The number of parallel workers is bounded by subscription configuration and the server's total worker capacity.

### 6.1. Initial sync can run in parallel

If a publication has multiple tables, PostgreSQL can synchronize multiple tables simultaneously. This reduces total duration on clusters with sufficient CPU, network, disk, and worker capacity.

Parallel table sync also increases:

- Number of connections to the publisher.
- Number of temporary replication slots during sync.
- Network throughput.
- Disk writes and WAL activity on the subscriber.
- CPU for COPY, decoding, and apply.

Do not increase workers solely based on table count. Measure actual resources and catch-up throughput.

## 7. Snapshots and concurrent changes

Suppose the `orders` table is currently being copied:

| Time | Publisher | Subscriber |
|---|---|---|
| T0 | Snapshot is established | No initial data yet |
| T1 | COPY is running | Receiving rows from snapshot |
| T2 | Transaction inserting a new order commits | Change is retained in the sync stream |
| T3 | Transaction updating an order commits | UPDATE waits to be applied via stream |
| T4 | COPY finishes | Subscriber applies remaining missing changes |
| T5 | Table catches up | Main apply worker continues synchronization |

Without a mechanism to retain and replay changes during the COPY window, the subscriber could finish initial sync with an older state than the publisher.

## 8. Replication slots in logical replication

A subscription typically uses a **logical replication slot** on the publisher to retain the WAL needed by the subscriber.

The slot tracks consumer progress. If the subscriber disconnects, the publisher continues retaining the WAL still needed by the slot, within retention policy limits.

This allows the subscriber to reconnect without restarting the entire replication from scratch, provided the necessary WAL is still available.

### 8.1. Permanent slot and temporary table sync slots

During initial sync, PostgreSQL can use temporary synchronization slots for each table being copied, in addition to the subscription's main slot.

Temporary slots serve to retain WAL across the snapshot/COPY/catch-up window. Once the table transitions to the ready state, the temporary slot is cleaned up according to internal lifecycle management.

Do not manually drop slots with internal names while initial sync is running. Let PostgreSQL manage them.

## 9. How does a logical slot retain WAL?

On the publisher, inspect:

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
WHERE slot_type = 'logical';
~~~

Columns may vary by PostgreSQL version. `restart_lsn` indicates the oldest WAL the slot may still need; `confirmed_flush_lsn` shows progress confirmed by the consumer under the logical slot protocol.

If a subscriber stops for a long time, the slot can retain a large amount of WAL and cause `pg_wal` to grow. This is a critical aspect of operating logical replication.

## 10. What is change apply?

After initial data is synchronized, the subscriber receives logical changes from the publisher and applies them to target tables.

Operations typically emitted by a publication include:

- INSERT.
- UPDATE.
- DELETE.
- TRUNCATE.

The set of operations depends on publication configuration. By default, a standard publication includes insert, update, delete, and truncate; a smaller subset can be chosen when creating the publication.

The apply worker receives transaction changes and executes them on the subscriber in the commit order sent by the publisher within that subscription stream.

## 11. Main apply worker

The main apply worker maintains the subscription after initial sync.

Its responsibilities include:

- Receiving the logical replication stream.
- Decoding protocol messages on the subscriber side.
- Applying row changes to subscriber tables.
- Committing the corresponding transactions.
- Updating replication origin/progress.
- Handling table membership and subscription state.

If an apply transaction fails, that transaction is not considered successfully applied. You must inspect logs, identify conflicts or permission/schema errors, fix the root cause, and recover the worker according to the subscription state.

## 12. Transaction order

Logical replication preserves transaction commit order within a single subscription. This allows the subscriber to observe changes in the order the publisher committed them within that stream.

However:

- There is no global order across multiple independent subscriptions.
- You should not assume transactions from multiple publishers are applied in a shared business order.
- DDL is not automatically transmitted along the row-change stream.
- A single transaction may update multiple tables; per-table initial sync must complete before the subscriber can be considered synchronized across the entire publication.

If an application depends on cross-table invariants, design controlled cutover and validation procedures.

## 13. Per-table synchronization state

The `pg_subscription_rel` catalog tracks table synchronization state.

Common states include:

| State | Meaning |
|---|---|
| `i` | Initialize: table was just registered for sync |
| `d` | Data copy is in progress |
| `f` | Finished copy: COPY is complete, catch-up phase remains |
| `s` | Synchronized: table reached intermediate synchronized state awaiting handoff |
| `r` | Ready: table is processed normally by the main apply worker |

These states are PostgreSQL implementation details and may be added or changed across versions. Use the catalog for observation; do not manually UPDATE catalog rows.

### 13.1. Viewing per-table state

On the subscriber:

~~~sql
SELECT
    s.subname,
    sr.srrelid::regclass AS relation_name,
    sr.srsubstate,
    sr.srsublsn
FROM pg_subscription_rel AS sr
JOIN pg_subscription AS s
  ON s.oid = sr.srsubid
ORDER BY s.subname, relation_name;
~~~

`srsubstate` shows which phase the table is in. `srsublsn` is internal LSN information associated with synchronization progress; consult the documentation for your running major version for exact interpretation.

## 14. Monitoring subscription workers

On the subscriber:

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
FROM pg_stat_subscription
ORDER BY subname, relid;
~~~

This view can display both the apply worker and table synchronization workers.

- A row with a NULL `relid` is typically the main apply worker.
- A row where `relid` is a table typically represents the worker synchronizing that table.
- `received_lsn` and `latest_end_lsn` help track stream reception progress.
- Timestamps help distinguish an active stream from an idle stream with no new messages.

The view schema may include additional columns such as worker type on newer versions. Use the schema description command in psql to inspect it before writing queries that depend on version-specific columns.

## 15. Monitoring replication origin

The subscriber stores logical replication progress via replication origins.

You can observe it with:

~~~sql
SELECT
    local_id,
    external_id,
    remote_lsn,
    local_lsn
FROM pg_replication_origin_status;
~~~

- `remote_lsn`: publisher-side WAL progress processed under this origin.
- `local_lsn`: corresponding local WAL position on the subscriber.

Replication origins help PostgreSQL track progress and avoid reapplying already-processed changes during recovery/restart scenarios.

Do not manually edit replication origin state to “skip past” apply errors. Incorrect changes can cause data loss or duplicate applies.

## 16. Viewing progress on the publisher

On the publisher, the logical slot indicates consumer progress:

~~~sql
SELECT
    slot_name,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_type = 'logical';
~~~

`confirmed_flush_lsn` can be used as a signal of consumer-confirmed progress. `restart_lsn` may be older because the decoder needs to retain WAL to continue decoding.

The distance from the current WAL position to these LSNs is an approximate indicator, not the sole measurement of end-to-end latency.

## 17. Creating a subscription and the copy_data option

Example:

~~~sql
CREATE SUBSCRIPTION app_subscription
CONNECTION 'host=publisher.example dbname=appdb user=repl_user'
PUBLICATION app_publication
WITH (
    copy_data = true,
    create_slot = true,
    enabled = true,
    connect = true
);
~~~

Meaning:

- `copy_data = true`: copies existing data for tables that need sync.
- `create_slot = true`: creates the logical replication slot on the publisher.
- `enabled = true`: enables the subscription so it begins operating.
- `connect = true`: connects to the publisher during subscription creation.

These are common defaults for CREATE SUBSCRIPTION. Verify exact options and behaviors against your PostgreSQL version.

## 18. copy_data=false

If the subscriber has already been seeded via another process, you can skip the initial copy:

~~~sql
CREATE SUBSCRIPTION app_subscription
CONNECTION 'host=publisher.example dbname=appdb user=repl_user'
PUBLICATION app_publication
WITH (copy_data = false);
~~~

In this case, PostgreSQL starts receiving new changes from the subscription initialization point, without copying existing rows.

Critical prerequisite: initial data on the subscriber must match the publisher at an appropriate consistent boundary. If the subscriber is empty or missing rows, future UPDATE/DELETE operations may fail to find matching rows; INSERTs may produce an incomplete state or conflicts.

`copy_data=false` is not a shortcut to skip initial sync and immediately get a complete replica.

## 19. Preparing a pre-seeded subscriber

An external seeding workflow might look like:

1. Stop or control writes at a cutover boundary.
2. Create a consistent snapshot/export from the publisher.
3. Load the snapshot into the subscriber.
4. Determine the appropriate LSN/starting point for replication.
5. Create the subscription using a procedure designed to start from that point.
6. Verify there are no gaps or duplicates between the snapshot and the change stream.

This is an advanced procedure. Do not simply run `pg_dump` at one point and create a subscription afterward without a way to anchor the WAL boundary. If there is a gap between the snapshot and slot start, the subscriber will miss changes.

## 20. Synchronizing tables added to a publication

When tables are added to a publication, the subscriber needs to refresh the publication:

~~~sql
ALTER SUBSCRIPTION app_subscription
REFRESH PUBLICATION;
~~~

By default, newly discovered tables undergo initial sync if `copy_data` is enabled during the refresh.

You can skip copying initial data:

~~~sql
ALTER SUBSCRIPTION app_subscription
REFRESH PUBLICATION WITH (copy_data = false);
~~~

Use this option only if the new table's data has already been seeded and synchronized consistently by another process.

### 20.1. Removing a table from a publication

When a table is removed from a publication and the subscriber refreshes membership, future changes for that table are no longer applied through the subscription. The existing table and its data on the subscriber are not automatically dropped.

DDL and cleanup of subscriber tables must be handled separately according to migration policy.

## 21. DDL is not automatically replicated

Logical replication transmits row changes. It does not automatically transmit DDL commands such as:

- CREATE TABLE.
- ALTER TABLE.
- CREATE INDEX.
- ALTER TYPE.
- CREATE FUNCTION.
- CREATE EXTENSION.

Therefore, the schema on the subscriber must be prepared via migrations or a separate schema deployment tool.

If the publisher adds a column and begins emitting rows with that column before the subscriber has a compatible structure, apply can fail.

### 21.1. Schema change workflow

A safe workflow typically:

1. Designs backward-compatible changes.
2. Applies the appropriate DDL on subscriber and publisher in a tested order.
3. Verifies column/type compatibility.
4. Deploys the application.
5. Monitors apply errors.
6. Removes legacy columns/logic only once all consumers have transitioned.

Do not assume logical replication carries migrations from the publisher to the subscriber.

## 22. Table compatibility requirements

Publisher and subscriber tables do not have to be identical in physical layout, but they must be compatible for applying row changes.

You must check:

- Column names and mapping.
- Compatible data types.
- Defaults for subscriber-only columns.
- Constraints capable of accepting the same data.
- Schema and object dependencies.
- Partitioning strategy if using partitioned tables.

Logical replication maps columns by name. A subscriber can have extra columns if those columns have defaults or allow NULL so INSERTs remain valid; publisher and subscriber must have the corresponding columns required by the published operations.

Avoid arbitrary schema drift.

## 23. Replica identity for UPDATE and DELETE

The publisher needs to identify which row changed when emitting UPDATE/DELETE operations.

By default, PostgreSQL uses the primary key as replica identity. You can inspect it with:

~~~sql
SELECT
    n.nspname,
    c.relname,
    c.relreplident
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema');
~~~

If a table lacks a primary key or a suitable unique replica identity, UPDATE/DELETE may not be published as required.

### 23.1. REPLICA IDENTITY FULL

You can configure:

~~~sql
ALTER TABLE public.audit_events
REPLICA IDENTITY FULL;
~~~

FULL instructs PostgreSQL to use the entire old row as identity. This can increase WAL/logical message volume and the cost of locating rows on the subscriber.

Prefer a primary key or suitable unique index whenever possible.

## 24. Publication operations

A publication determines which operations are emitted:

~~~sql
CREATE PUBLICATION insert_only_pub
FOR TABLE public.events
WITH (publish = 'insert');
~~~

You can select insert, update, delete, and truncate as needed. If a publication does not publish a given operation type, the subscriber will not receive that type of change.

For example, an insert-only publication cannot be used to keep a subscriber reflecting full source UPDATE/DELETE activity.

## 25. Row filters and column lists

A publication can restrict which rows or columns are published on supported PostgreSQL versions.

This affects both initial copy and change apply:

- Only rows matching the row filter are copied/emitted.
- Column lists restrict which columns are sent.
- Changing filters/column lists may require refreshing the subscription and resynchronizing affected data depending on version/operation.

If the subscriber only holds a subset of data, do not compare full-table row counts as though both sides should be identical.

## 26. TRUNCATE in logical replication

If a publication emits TRUNCATE, the subscriber can receive the corresponding truncate operation.

Be careful with:

- Foreign key dependencies.
- Multiple related tables.
- TRUNCATE CASCADE and its semantics on the subscriber.
- Row filters, partitioned tables, and publication membership.

Do not allow TRUNCATE on the publisher if the subscriber cannot accept its corresponding impact.

## 27. Sequences are not synchronized like row data

Logical replication does not automatically replicate sequence state.

Rows may be copied/applied while a sequence's `last_value` on the subscriber does not automatically follow the publisher. This is critical when the subscriber is being prepared for promotion or to accept writes.

Before a write-accepting cutover/failover, synchronize sequence values manually or via a verified migration/runbook.

Example sequence check:

~~~sql
SELECT
    schemaname,
    sequencename,
    last_value
FROM pg_sequences
WHERE schemaname = 'public';
~~~

Do not mechanically set a sequence to `MAX(id)`: sequences may increment by steps other than 1, use caching, or have allocated values whose transactions never inserted a row. Use proper sequence mapping and `setval` procedures.

## 28. Large Objects and other objects

Logical replication does not synchronize every kind of database object.

Items requiring separate handling include:

- Large Objects.
- DDL and schema definitions.
- Sequence state.
- Cluster-wide roles and grants.
- Extensions and server-side files.
- Foreign servers/user mappings and certain metadata.

Inventory everything the application requires before treating a subscriber as a full replacement.

## 29. Apply conflicts

Logical replication does not automatically resolve all data conflicts.

Common scenarios include:

- Duplicate key during INSERT into the subscriber.
- UPDATE/DELETE unable to find the matching row.
- Unique/check/foreign key constraint violations.
- Subscriber data diverging from the publisher.
- Incompatible schema or data types.
- Errors caused by triggers/functions/permissions.
- A user writing directly to a subscriber table and causing a collision.

When an apply transaction errors, the subscriber cannot treat that transaction as applied. Check logs and subscription worker state, resolve the root cause, and let the worker resume via the server's restart mechanism.

## 30. Do not treat logical replication as multi-master

If applications write concurrently to both publisher and subscriber on the same replicated tables, duplicate keys or conflicting data can result.

Standard logical replication is unidirectional. The subscriber should be protected from writes outside replication apply, unless the architecture explicitly implements dedicated ownership/conflict resolution rules.

Do not enable two bidirectional subscriptions expecting PostgreSQL to merge data automatically like a multi-master system.

## 31. Apply worker and subscriber privileges

The apply worker needs appropriate privileges to write to target tables and perform replication operations.

Check:

- Subscriber table owners.
- Subscription owner.
- INSERT/UPDATE/DELETE/TRUNCATE privileges.
- Role memberships.
- RLS policies.
- Constraints and triggers.
- Extension/function dependencies.

When privileges change after a subscription is already running, apply can start failing. Publisher privileges for copying initial data also differ from apply privileges on the subscriber; verify both sides.

## 32. RLS and trigger behavior

Row-Level Security and triggers on the subscriber can affect apply depending on configuration and trigger type.

The apply worker uses its own replication session mechanism. Do not assume every standard business trigger on the subscriber fires identically to a direct application INSERT.

If the subscriber requires specific trigger or RLS behavior, test your PostgreSQL version's semantics, trigger enable mode, and subscription owner privileges in a test environment first.

## 33. Worker limits

Important settings include:

~~~sql
SHOW max_logical_replication_workers;
SHOW max_sync_workers_per_subscription;
SHOW max_worker_processes;
SHOW max_replication_slots;
SHOW max_wal_senders;
~~~

- `max_sync_workers_per_subscription`: limits the number of table sync workers for a single subscription.
- `max_logical_replication_workers`: logical replication worker capacity on the subscriber.
- `max_worker_processes`: total background worker capacity limit.
- `max_replication_slots`: slot capacity on the publisher.
- `max_wal_senders`: WAL sender process capacity on the publisher.

Values must be large enough for apply workers, table sync workers, physical standbys, logical consumers, and backup connections in your topology.

## 34. Initial sync can increase load

Copying a large table generates read I/O on the publisher and write I/O on the subscriber. Simultaneously, the publisher continues serving workload and generating WAL.

Load sources include:

- Sequential scans/reads on the publisher.
- Network transfer.
- COPY inserts on the subscriber.
- WAL writes on the subscriber.
- Index maintenance and constraints.
- Table sync workers.
- Main apply worker processing new changes.
- Vacuum/maintenance and application queries.

Schedule initial sync at an appropriate window, monitor disk/network, and set concurrency limits.

## 35. Table sync and locks on the subscriber

Initial table synchronization must write data into the target table. During this process, PostgreSQL uses locking to ensure COPY/sync operations do not conflict with incompatible changes.

This can cause queries or DDL on the subscriber to wait, depending on the operation type and version. Do not run schema migrations or allow application writes directly to a table undergoing initial sync without checking lock behavior.

Use `pg_locks`, `pg_stat_activity`, and logs to diagnose waits.

## 36. Monitoring subscription errors

On the subscriber, you can view error statistics on supported versions:

~~~sql
SELECT *
FROM pg_stat_subscription_stats;
~~~

Fields such as apply error count and sync error count help detect apply or initial sync failures. View names and structures depend on the major version.

Combine this with PostgreSQL server logs; statistics do not replace detailed error messages in the logs.

## 37. Checking subscription state

~~~sql
SELECT
    subname,
    subenabled,
    subslotname,
    subpublications
FROM pg_subscription
ORDER BY subname;
~~~

The `pg_subscription` catalog stores subscription configuration. Some fields and visibility privileges may vary by version.

Check enabled state and publication names when investigating a stopped subscription or new tables not yet being replicated.

## 38. Disabling and enabling a subscription

You can pause a subscription:

~~~sql
ALTER SUBSCRIPTION app_subscription DISABLE;
~~~

Re-enable it:

~~~sql
ALTER SUBSCRIPTION app_subscription ENABLE;
~~~

When disabled, the subscriber does not apply new changes. The publisher slot may continue retaining WAL for the subscription, causing WAL retention to grow.

Do not leave a subscription disabled for long without monitoring the slot and publisher disk space.

## 39. Refreshing a publication

When publication membership changes, the subscriber needs to refresh:

~~~sql
ALTER SUBSCRIPTION app_subscription
REFRESH PUBLICATION WITH (copy_data = true);
~~~

PostgreSQL detects new tables and can run initial sync for them. Tables already in the ready state are generally not recopied solely due to a normal refresh.

If skipping `copy_data`, ensure the new data has been seeded consistently.

## 40. Pausing writes for cutover

A migration from publisher to subscriber usually requires a clear cutover point.

A general procedure:

1. Complete initial sync for all tables.
2. Verify the subscription has no apply errors.
3. Quiesce or stop writes on the publisher.
4. Wait for the subscriber to apply up to the final required LSN.
5. Verify data and constraints.
6. Synchronize sequence states and non-replicated metadata.
7. Cut over the application to the subscriber.
8. Re-open writes according to plan.
9. Monitor the application and keep an appropriate rollback path.

Do not cut over writes while any table is still in initial sync or apply lag is uncontrolled.

## 41. Initial data verification

You can check row counts on both sides:

~~~sql
SELECT count(*) FROM public.customers;
SELECT count(*) FROM public.orders;
~~~

However, if the publisher is still accepting writes, two counts taken at different instants can differ even when replication is functioning properly.

To verify rigorously:

- Pick a point-in-time/LSN boundary.
- Pause writes or use a consistent snapshot procedure.
- Wait for the subscriber to apply up to the boundary.
- Compare row counts and business invariants.
- Check critical tables using key ranges/checksums/sampling.
- Verify non-replicated objects separately.

Do not rely on a standalone row count as comprehensive proof.

## 42. Troubleshooting failed initial sync

If a table fails to complete sync:

1. Check `pg_subscription_rel` state.
2. Determine whether the table is in `i`, `d`, `f`, or another state.
3. Check `pg_stat_subscription` to locate the table sync worker.
4. Read publisher and subscriber logs.
5. Verify SELECT privileges on the publisher.
6. Verify privileges/constraints/schema on the subscriber.
7. Check network, disk space, and worker capacity.
8. Fix the root cause before retrying.

Do not directly UPDATE `pg_subscription_rel` to mark a table ready.

## 43. Troubleshooting a stalled apply worker

If the apply worker is not progressing:

- Verify the subscription is enabled.
- Check the worker PID in `pg_stat_subscription`.
- Inspect logs for the first failing transaction error.
- Check subscriber locks and long-running transactions.
- Verify schema, constraints, and role permissions.
- Check publisher slot activity and WAL retention.
- Verify network connectivity and publisher availability.

After fixing the root cause, you can disable/enable the subscription per your runbook to prompt the worker to restart if needed. Before doing so, verify the slot and progress to avoid accidentally dropping or recreating the subscription.

## 44. WAL retention on the publisher when the subscriber is offline

A logical replication slot can retain WAL while the subscriber is offline.

On the publisher:

~~~sql
SELECT
    slot_name,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
WHERE slot_type = 'logical';
~~~

If the subscriber remains stopped for too long, `restart_lsn` can stall and `pg_wal` grows. If the slot retention limit is exceeded, the slot may become invalidated on versions supporting retention limits.

Monitor archiving, disk capacity, and subscription availability. Never delete WAL files manually.

## 45. Do not arbitrarily drop/recreate a slot to fix apply errors

Dropping a logical slot can lose WAL that the subscriber needs. Recreating a new slot at the current position does not automatically recover changes the subscriber missed.

If a slot is lost:

- Verify whether complete WAL archives exist from the required position.
- Verify whether the subscriber can resume from archive.
- If continuous WAL is unavailable, reseed/recreate subscriber data following a proper procedure.
- Drop an old slot only when you fully understand its consumers and retention impact.

## 46. Using copy_data=false in a pre-seeded migration

One data migration approach uses an external snapshot/backup and then creates a subscription without copying data. However, there must be a well-defined LSN boundary.

~~~text
Lock in snapshot + WAL boundary on publisher
             |
             v
Seed subscriber from snapshot
             |
             v
Start logical stream from matching boundary
             |
             v
Apply post-snapshot changes
             |
             v
Subscriber catches up to publisher
~~~

Without coordinating the snapshot and slot start point, transactions in between can be lost. This is an advanced workflow; test it in staging and use tools supporting consistent logical backups/LSNs where appropriate.

## 47. Direct writes on the subscriber

If the subscriber receives direct writes while being replicated, those rows can:

- Cause duplicate keys when the publisher INSERTs the same key.
- Be updated/deleted by the publisher via replica identity.
- Trigger constraint conflicts.
- Cause both sides to diverge out of sync.

In a unidirectional model, keep the subscriber free from application writes on replicated tables. If write traffic is required on both sides, a dedicated multi-master/conflict-resolution design is necessary.

## 48. Large transactions and streaming

A large transaction on the publisher can generate substantial changes before committing. The apply worker must process that transaction according to the replication protocol and subscriber resources.

Potential impacts include:

- Increased WAL retention.
- Increased apply lag.
- Network bursts.
- Disk/WAL pressure on the subscriber.
- Long-running apply transactions.

Logical replication supports options for streaming in-progress transactions on supported PostgreSQL versions; behavior and configuration depend on version. Do not assume a large transaction will be applied row by row and committed independently.

## 49. Monitoring end-to-end lag

No single column describes every kind of lag.

Combine:

- Publisher current WAL LSN.
- Logical slot `restart_lsn` and `confirmed_flush_lsn`.
- Subscriber `pg_stat_subscription.latest_end_lsn`.
- Subscriber `pg_replication_origin_status.remote_lsn`.
- Send/receive timestamps.
- Table sync state.
- Filesystem usage and WAL retention.

LSN distance reflects the volume of WAL in between, whereas timestamps reflect the time of the most recent message/transaction. When the publisher is idle, an old timestamp does not necessarily mean the subscriber is lagging.

## 50. Separating initial sync lag from apply lag

These two issues must be diagnosed separately:

| Symptom | Meaning | What to check |
|---|---|---|
| Table stays in state `d` long | Initial COPY not yet finished | Table size, network, disk, workers |
| Table stays in state `f` long | COPY finished, catch-up not done | WAL rate, slot, apply throughput |
| All tables ready but LSN lags | Continuous apply is slow | Apply worker, transaction volume, locks |
| No sync worker present | Worker capacity or sync finished/errored | pg_stat_subscription, logs, catalog state |
| Slot WAL retention growing | Consumer not confirming fast enough | Subscriber, network, apply errors |

Do not just look at total row counts; inspect the exact phase where the table is slowing down.

## 51. Worker capacity and configuration

Key settings to evaluate:

~~~sql
SHOW max_sync_workers_per_subscription;
SHOW max_logical_replication_workers;
SHOW max_worker_processes;
~~~

If there are multiple subscriptions and many large tables, total requested sync workers can exceed capacity. Workers must wait for a resource slot before starting.

Increasing `max_sync_workers_per_subscription` without increasing/checking `max_logical_replication_workers` and `max_worker_processes` may yield no actual concurrency gain.

## 52. Lab: creating a publication and subscription

In two PostgreSQL lab databases.

**Publisher:**

~~~sql
CREATE TABLE public.inventory (
    item_id BIGINT PRIMARY KEY,
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL
);

INSERT INTO public.inventory VALUES
    (1, 'Keyboard', 20),
    (2, 'Mouse', 35);

CREATE PUBLICATION inventory_pub
FOR TABLE public.inventory;
~~~

**Subscriber:**

~~~sql
CREATE TABLE public.inventory (
    item_id BIGINT PRIMARY KEY,
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL
);

CREATE SUBSCRIPTION inventory_sub
CONNECTION 'host=publisher.example dbname=appdb user=repl_user'
PUBLICATION inventory_pub;
~~~

If `copy_data` remains at its default `true`, the subscriber will initially copy the two existing rows and then continue receiving changes.

## 53. Lab: observing initial sync

On the subscriber, run while the subscription is initializing:

~~~sql
SELECT
    s.subname,
    sr.srrelid::regclass AS table_name,
    sr.srsubstate,
    sr.srsublsn
FROM pg_subscription_rel AS sr
JOIN pg_subscription AS s
  ON s.oid = sr.srsubid;
~~~

For small tables, states may transition too quickly to observe easily. Test with a larger lab table and appropriate worker limits in an isolated environment.

Once the table is ready, check:

~~~sql
SELECT * FROM public.inventory ORDER BY item_id;
~~~

## 54. Lab: changes during initial copy

With a sufficiently large lab table:

1. Start creating the subscription and monitor table sync state.
2. While COPY is running, execute INSERT/UPDATE/DELETE operations on the publisher.
3. Wait for initial sync to complete.
4. Check whether the subscriber reflects changes committed during the copy window.
5. Compare state after the apply stream catches up.

The goal is to observe how snapshot COPY and the change stream coordinate to prevent missing changes.

## 55. Lab: copy_data=false

Create a subscriber table pre-seeded with consistent data via a separate procedure. Then create the subscription with `copy_data=false`.

~~~sql
CREATE SUBSCRIPTION inventory_sub
CONNECTION 'host=publisher.example dbname=appdb user=repl_user'
PUBLICATION inventory_pub
WITH (copy_data = false);
~~~

Perform INSERT/UPDATE operations on the publisher and observe the subscriber.

Do not run this lab with an empty subscriber and conclude that `copy_data=false` produces a full replica. It only skips the initial copy.

## 56. Lab: adding a table and refreshing the publication

On the publisher:

~~~sql
CREATE TABLE public.warehouses (
    warehouse_id BIGINT PRIMARY KEY,
    warehouse_name TEXT NOT NULL
);

ALTER PUBLICATION inventory_pub
ADD TABLE public.warehouses;
~~~

On the subscriber, create the matching schema and refresh:

~~~sql
CREATE TABLE public.warehouses (
    warehouse_id BIGINT PRIMARY KEY,
    warehouse_name TEXT NOT NULL
);

ALTER SUBSCRIPTION inventory_sub
REFRESH PUBLICATION WITH (copy_data = true);
~~~

Observe `pg_subscription_rel` to see the new table progress through the initial sync states.

## 57. Lab: monitoring apply progress

On the subscriber:

~~~sql
SELECT
    subname,
    pid,
    relid,
    received_lsn,
    latest_end_lsn,
    last_msg_receipt_time,
    latest_end_time
FROM pg_stat_subscription;
~~~

On the publisher:

~~~sql
SELECT
    slot_name,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_type = 'logical';
~~~

Compare progress over time rather than relying on a single sample.

## 58. Lab: handling an apply conflict

In an isolated lab:

1. Seed the subscriber with a row whose key will conflict.
2. Perform an INSERT with the same key on the publisher.
3. Observe the error in the subscriber logs.
4. Inspect subscription worker state.
5. Identify the conflicting row and how to repair the data.
6. Restart/let the worker retry per your runbook.
7. Confirm that the transaction and subsequent changes are applied.

Never test conflicts on a production subscription.

## 59. Cutover checklist

Before switching the application to the subscriber:

- All publication tables are in the ready state.
- No unresolved apply/sync errors remain.
- The subscriber has caught up to the publisher up to the chosen LSN boundary.
- Row counts and business invariants have been reconciled.
- Schemas/DDL and extensions are compatible.
- Sequence states have been handled.
- Roles, grants, RLS, and application connections are prepared.
- Writes on the publisher are stopped or coordinated per plan.
- A rollback plan is in place and post-cutover replication direction is clearly defined.

Logical replication does not automatically reverse direction after the application moves to the subscriber. Making the subscriber the new publisher requires configuring new publications/subscriptions and an appropriate data workflow.

## 60. Common misconceptions

### 60.1. Initial sync is just COPY and done

False. PostgreSQL must also handle changes generated during COPY and catch up before the table becomes ready.

### 60.2. Once a subscription is created, all tables are already synchronized

False. Tables may be in different initial sync states.

### 60.3. copy_data=false still copies old rows

False. It skips initial data copy; the subscriber must be seeded by another means.

### 60.4. DDL replicates automatically

False. Logical replication primarily transmits row changes; DDL must be managed separately.

### 60.5. Sequence state synchronizes automatically

False. Sequence values are not replicated like row data.

### 60.6. The subscriber can be written to freely

Unsafe in a unidirectional model. Direct writes can cause apply conflicts or divergence.

### 60.7. An inactive slot means it is not retaining WAL

False. A logical slot can retain WAL while the subscriber is disconnected.

### 60.8. Increasing sync workers always makes sync faster

Not guaranteed. Publisher, subscriber, network, disk, and worker capacity can become bottlenecks.

### 60.9. Matching row counts prove data is completely identical

False. You must compare at the same boundary and verify keys, constraints, and business invariants.

### 60.10. One subscription can automatically merge writes from both sides

False. Native logical replication does not automatically provide multi-master conflict resolution.

## 61. Troubleshooting checklist

**Initial sync**

1. Is the subscription enabled?
2. Does the publication contain the table?
3. Is `copy_data` enabled?
4. Does the target table have a compatible schema?
5. What is the current table sync state?
6. Does the sync worker have a PID?
7. Are publisher SELECT privileges correct?
8. Do subscriber disk and network have enough capacity?
9. Is worker capacity available?

**Continuous apply**

10. Is the apply worker running?
11. Is `pg_stat_subscription` LSN advancing?
12. Is `pg_replication_origin_status` advancing?
13. Is the publisher logical slot active?
14. Are `restart_lsn`/`confirmed_flush_lsn` advancing?
15. Are there duplicate keys or missing rows?
16. Are there constraint/permission/schema errors?
17. Are there non-replication writes on the subscriber?
18. Are large transactions or locks slowing apply down?

**Cutover**

19. Are all tables ready?
20. Has the subscriber caught up to the boundary?
21. Have sequence states been handled?
22. Have DDL/extensions/roles been synchronized?
23. Do smoke tests and business invariants pass?
24. Is there a rollback/failback plan?

## 62. Practice exercises

### Exercise 1 — Publisher

What is the publisher's role?

**Hint:** publishing row changes.

### Exercise 2 — Subscriber

What is the subscriber's job?

**Hint:** receiving and applying changes.

### Exercise 3 — Initial sync

Which data does initial table synchronization copy?

**Hint:** rows existing at the initial snapshot.

### Exercise 4 — Snapshot

Why does initial copy need a snapshot?

**Hint:** to have a consistent view of the data.

### Exercise 5 — Concurrent changes

Why must changes generated during COPY be retained?

**Hint:** to avoid missing transactions after the snapshot.

### Exercise 6 — Table sync worker

What does this worker do?

**Hint:** COPYs the table and catches up to the main apply stream.

### Exercise 7 — Apply worker

What does the main apply worker do after initial sync?

**Hint:** continuously receives and applies logical changes.

### Exercise 8 — Table states

What does state `d` indicate?

**Hint:** data copy is in progress.

### Exercise 9 — State f

What does state `f` indicate?

**Hint:** copy finished, catch-up remains.

### Exercise 10 — State r

What does state `r` indicate?

**Hint:** the table is ready for normal apply.

### Exercise 11 — pg_subscription_rel

What does this catalog track?

**Hint:** per-table initial sync state.

### Exercise 12 — pg_stat_subscription

What does this view track?

**Hint:** apply/sync workers and LSN progress.

### Exercise 13 — Replication origin

What does replication origin status help with?

**Hint:** tracking remote/local LSN progress.

### Exercise 14 — copy_data

What is its typical default value?

**Hint:** true.

### Exercise 15 — copy_data=false

When can it be used?

**Hint:** when the subscriber has already been consistently seeded externally.

### Exercise 16 — refresh publication

Which command updates membership from a publication?

**Hint:** ALTER SUBSCRIPTION ... REFRESH PUBLICATION.

### Exercise 17 — DDL

Does logical replication replicate ALTER TABLE?

**Hint:** no.

### Exercise 18 — Sequence

Why must sequences be handled during cutover?

**Hint:** sequence state does not replicate automatically.

### Exercise 19 — Replica identity

Why do UPDATE/DELETE require a replica identity?

**Hint:** to identify the old row on the subscriber.

### Exercise 20 — REPLICA IDENTITY FULL

What is the main trade-off?

**Hint:** uses the entire old row, increasing WAL/message volume and cost.

### Exercise 21 — Logical slot

What does the slot retain for the subscriber?

**Hint:** WAL required to continue logical decoding.

### Exercise 22 — Inactive slot

Does the slot disappear if the subscriber goes offline?

**Hint:** no.

### Exercise 23 — WAL retention

Why can an offline subscriber cause `pg_wal` to grow?

**Hint:** the logical slot retains WAL not yet confirmed by the consumer.

### Exercise 24 — Apply order

In what order are transactions within a subscription applied?

**Hint:** the commit order of the publisher stream.

### Exercise 25 — Multi-master

Does native logical replication automatically resolve bidirectional conflicts?

**Hint:** no.

### Exercise 26 — Conflict

Name three causes of apply conflicts.

**Hint:** duplicate key, missing row, constraint violation.

### Exercise 27 — Worker capacity

Which setting limits table sync workers per subscription?

**Hint:** `max_sync_workers_per_subscription`.

### Exercise 28 — max_logical_replication_workers

What does this setting control?

**Hint:** logical replication worker capacity.

### Exercise 29 — Subscriber schema

Why must DDL be prepared on the subscriber?

**Hint:** DDL does not replicate automatically.

### Exercise 30 — Column mapping

By what factor does logical replication primarily map columns?

**Hint:** column names.

### Exercise 31 — TRUNCATE

Can a publication emit TRUNCATE?

**Hint:** yes, if the operation is published.

### Exercise 32 — Large Objects

Do Large Objects replicate automatically?

**Hint:** no.

### Exercise 33 — Table sync lag

What does staying in state `d` for a long time suggest?

**Hint:** COPY is not yet finished; check table size, network, disk, workers.

### Exercise 34 — Catch-up lag

What does staying in state `f` for a long time suggest?

**Hint:** copy is finished, but WAL changes remain to be applied.

### Exercise 35 — Apply lag

What could cause `latest_end_lsn` not to advance when all tables are ready?

**Hint:** apply worker, network, transactions, locks, or publisher activity.

### Exercise 36 — Cutover

Why must writes be stopped/coordinated before cutover?

**Hint:** to create a verifiable LSN/data boundary.

### Exercise 37 — Count validation

Why can row counts on both sides differ even when replication is healthy?

**Hint:** writes continue and queries run at different times.

### Exercise 38 — Slot lost

What happens if a logical slot loses needed WAL?

**Hint:** complete archive recovery or reseed/rebuild the subscriber.

### Exercise 39 — Disable subscription

Why can disabling for a long time cause WAL retention?

**Hint:** the publisher slot still retains WAL for the consumer.

### Exercise 40 — Migration

What does an externally seeded subscriber need for `copy_data=false` to be safe?

**Hint:** a consistent snapshot and a WAL start boundary with no gap.

## 63. Frequently asked questions

### Does initial synchronization lock the entire database?

No. It operates per table and uses snapshot/COPY; locking and impact depend on the table, operations, and PostgreSQL version. Check `pg_locks` if queries are waiting.

### Can writes continue on the publisher during initial sync?

Yes. PostgreSQL coordinates the snapshot with the change stream so changes during COPY are not missed.

### How many table sync workers does a subscription have?

It depends on worker capacity configuration and the number of tables needing sync. `max_sync_workers_per_subscription` limits the number of table sync workers per subscription.

### When is a table considered ready?

After snapshot COPY and catch-up have completed to a safe handoff point; its state in `pg_subscription_rel` transitions to `r`.

### Is copy_data=false suitable for a new empty subscriber database?

No, if the goal is a full replica. It does not copy existing rows.

### Can a publication be modified while a subscription is running?

Yes. Membership changes on the publisher require refreshing the publication on the subscriber to update replicated tables.

### Does adding a table to a publication automatically copy its data?

When refreshing with `copy_data` enabled, PostgreSQL can run initial table sync for the new table. If skipping `copy_data`, the data must be seeded separately.

### Is DDL sent over logical replication?

No. DDL must be deployed separately while keeping both schemas compatible.

### Why are sequences on the subscriber lagging behind?

Sequence state is not synchronized like row changes by logical replication. Sequences must be updated as part of the cutover procedure.

### Does subscriber apply conflict handling automatically pick a winner?

No. The DBA/application owner must resolve the conflict and recover the apply worker.

### Can a logical slot fill up the disk?

Yes. An offline subscriber or slow apply can cause the slot to retain WAL. Retention limits, archiving, and disk monitoring are required.

### Is it possible to write directly to the subscriber?

Technically possible if permissions allow, but unsafe in a unidirectional model because it can create conflicts/divergence.

### What if pg_stat_subscription has no rows?

The subscription may be disabled, the worker has not started yet, is erroring, or no worker is active in that state. Check catalogs, logs, and subscription enabled state.

### How do I know initial sync is complete?

Check that all tables to be replicated in `pg_subscription_rel` have state `r`, and confirm the apply worker is active and LSNs continue advancing.

### When is rebuilding a subscriber necessary?

When the subscriber lacks required WAL and has no complete archive to resume from, or when data/schema has diverged in a way that cannot be safely fixed by continuing apply.

## 64. Summary

Key observation and operational statements:

~~~sql
-- On publisher: publication.
SELECT pubname, puballtables, pubinsert, pubupdate, pubdelete, pubtruncate
FROM pg_publication;

-- On subscriber: subscription.
SELECT subname, subenabled, subslotname, subpublications
FROM pg_subscription;

-- On subscriber: per-table initial sync state.
SELECT
    s.subname,
    sr.srrelid::regclass AS relation_name,
    sr.srsubstate,
    sr.srsublsn
FROM pg_subscription_rel AS sr
JOIN pg_subscription AS s
  ON s.oid = sr.srsubid;

-- On subscriber: workers and progress.
SELECT
    subname,
    pid,
    relid,
    received_lsn,
    latest_end_lsn,
    last_msg_receipt_time,
    latest_end_time
FROM pg_stat_subscription;

-- On subscriber: replication origin.
SELECT local_id, external_id, remote_lsn, local_lsn
FROM pg_replication_origin_status;

-- On publisher: logical slots.
SELECT
    slot_name,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_type = 'logical';

-- Update publication membership.
ALTER SUBSCRIPTION app_subscription REFRESH PUBLICATION;

-- Pause/resume subscription with an appropriate runbook.
ALTER SUBSCRIPTION app_subscription DISABLE;
ALTER SUBSCRIPTION app_subscription ENABLE;
~~~

Key principles to remember:

1. Initial synchronization copies existing data at a snapshot; change apply transmits transactions occurring afterward.
2. The snapshot and WAL stream must coordinate so there is no gap between COPY and apply.
3. Table sync workers handle initial copy/catch-up; the main apply worker maintains continuous replication.
4. `pg_subscription_rel` tracks per-table synchronization state; `r` indicates ready.
5. `pg_stat_subscription` helps observe workers and LSN progress.
6. Replication origins store remote/local progress.
7. Logical replication slots retain needed WAL when a subscriber is offline; slots can cause `pg_wal` to grow.
8. `copy_data=true` copies existing data; `copy_data=false` requires a consistently pre-seeded subscriber.
9. New tables in a publication require refreshing the subscription and may trigger initial sync.
10. DDL, sequence state, Large Objects, roles, and many cluster objects must be managed separately.
11. UPDATE/DELETE require an appropriate replica identity.
12. Subscriber schemas, types, constraints, permissions, and extensions must be compatible.
13. Apply conflicts are not automatically resolved by PostgreSQL using business rules.
14. Native logical replication is not multi-master.
15. Monitor initial sync lag and continuous apply lag separately.
16. Increase worker concurrency only when publisher, subscriber, network, and disk have sufficient capacity.
17. Cutover requires an LSN boundary, caught-up data, sequence handling, and validation.
18. Never drop slots or edit replication origins to skip errors without understanding WAL continuity.
19. If a slot loses needed WAL, complete archives or subscriber reseeding is required.
20. Restore/cutover tests prove the subscriber can replace the publisher as planned.

Diagram of the complete lifecycle:

~~~text
Publication on publisher
          |
          v
Create subscription
          |
          v
Create logical replication slot
          |
          v
Register tables to synchronize
          |
          v
Table sync workers acquire snapshot
          |
          v
COPY initial data
          |
          v
Catch-up changes generated during COPY
          |
          v
Each table transitions to ready
          |
          v
Main apply worker receives continuous stream
          |
          v
Monitor LSN, errors, slot, and lag
          |
          v
Validation + sequence/DDL preparation
          |
          v
Controlled cutover
~~~

**Conclusion:** Initial data synchronization and change apply are two continuous parts of PostgreSQL logical replication. Snapshot/COPY establishes the initial state; table synchronization workers catch up on changes generated during copy; the main apply worker sustains the subsequent transaction stream. Proper operation requires **compatible schemas, adequate slot/WAL retention, appropriate worker capacity, per-table state and LSN monitoring, deliberate conflict handling, and verified cutovers**.
