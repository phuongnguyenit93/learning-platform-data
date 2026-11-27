# Bidirectional Replication, Loops, and Conflict Risks

PostgreSQL logical replication is commonly used to stream data changes from a publisher to a subscriber. In the standard model, one system acts as the primary write node and one or more systems receive replicas for migration, integration, reporting, or workload separation. When two systems both accept local writes and send changes to each other, the architecture becomes **bidirectional logical replication**. This model enables multi-site writes, but introduces harder problems: a change can return to its source through a loop, two sites can modify the same row, primary keys can collide, and independent transactions can create inconsistent states.

PostgreSQL logical replication provides publication/subscription primitives and replication origin metadata to transmit changes. Starting in PostgreSQL 16, subscriptions support an origin filtering option to receive only locally originated changes, helping prevent forwarding a transaction already received from another subscription. However, this mechanism **does not resolve data conflicts**. If two nodes update the same row or insert the same key concurrently, the apply worker can still error and halt change application.

Therefore, bidirectional replication requires explicit data design and write rules. You must define which node is permitted to write each row/tenant/key range, how collision-free keys are generated, how conflicts are detected and handled, how schemas stay synchronized, and how to recover when a subscription stalls. If business requirements demand concurrent writes to the same data across nodes with automatic merging, an explicit conflict-resolution model or a dedicated multi-master solution is needed; merely creating two subscriptions is insufficient.

This lesson belongs to the **Logical Replication** chapter of the **Database Engine Relational PostgreSQL** module. It focuses on bidirectional replication architecture, loop prevention, conflict types, ownership policies, and safe operational procedures.

## 1. Learning objectives

After this lesson, you will be able to:

- Describe publisher, publication, subscriber, and subscription in logical replication.
- Design a two-node topology that both publishes and subscribes.
- Explain why replicated changes can loop back to the source node.
- Use origin filtering on PostgreSQL 16+ to prevent forwarding loops.
- Distinguish loop prevention from conflict detection and conflict resolution.
- Identify duplicate-key, missing-row, constraint, and concurrent-update conflicts.
- Design keyspaces/ownership to minimize two nodes writing the same row.
- Understand native logical replication limitations regarding DDL, sequences, large objects, and schema drift.
- Build workflows for initial sync, cutover, and enabling bidirectional replication.
- Monitor subscriptions, apply errors, replication origins, and lag.
- Troubleshoot stalled apply workers and evaluate the risks of skipping transactions.
- Design failover, resubscription, resynchronization, and data reconciliation.
- Assess when bidirectional logical replication fits and when a different solution is required.

## 2. Logical replication: publisher and subscriber

Logical replication transmits changes at the logical row-operation level via publications and subscriptions.

~~~text
Publisher database
      |
      | publication
      v
WAL logical decoding
      |
      | replication protocol
      v
Subscriber apply worker
      |
      v
Subscriber tables
~~~

### 2.1. Publication

A publication defines which tables and operation types are published. It can publish INSERT, UPDATE, DELETE, and TRUNCATE as configured. A publication is not a full copy of all database object metadata.

### 2.2. Subscription

A subscription connects to a publisher, subscribes to publications, creates a replication slot on the publisher, and runs an apply worker on the subscriber. The subscriber receives changes and applies them to matching target tables.

### 2.3. Initial table synchronization

When a subscription is created with default `copy_data`, PostgreSQL can copy existing data of published tables before switching to the continuous change stream. Snapshot timing, concurrent writes during sync, and potential conflicts must be managed.

### 2.4. Apply worker

The apply worker reads the logical change stream and applies operations on the subscriber. Errors such as duplicate keys or missing rows can stop the apply worker for the affected subscription/table until resolved.

### 2.5. Logical replication is not a physical standby

A subscriber is a database containing corresponding logical tables. It is not a physical copy of the entire cluster; schemas and many global objects must be managed separately.

## 3. Unidirectional vs. bidirectional replication

In a unidirectional model, one publisher sends changes to a subscriber:

~~~text
Node A (writes)
      |
      v
Node B (read copy)
~~~

In a bidirectional model, both nodes have publications and subscriptions:

~~~text
       Publication A
Node A ---------------> Node B
  ^                       |
  |                       |
  +-----------------------+
       Publication B
~~~

### 3.1. Each node both publishes and subscribes

Node A publishes local changes for B to receive. Node B also publishes local changes for A to receive.

### 3.2. Each direction is a separate replication stream

A→B and B→A have separate subscriptions, slots, apply workers, origins, and lag. One healthy direction does not prove the other direction is healthy.

### 3.3. Bidirectional does not create a single global transaction

A transaction commits on A and is later applied on B after some delay. There is no automatic distributed commit or consensus between two databases merely from reciprocal subscriptions.

### 3.4. Both nodes can accept concurrent writes

If A and B both allow writes to the same table/keyspace, changes can collide. Ownership rules and conflict policies are required before production deployment.

### 3.5. Bidirectional is not full multi-master

Native logical replication provides transport/apply primitives. It does not provide complete conflict resolution, global uniqueness, distributed locking, or transaction coordination.

## 4. Why do replication loops occur?

Suppose A inserts a row. A publishes the transaction to B. B applies that transaction. If B also publishes the newly applied change back to A, A can receive its own transaction again via another path.

~~~text
A local INSERT
    |
    v
A publishes to B
    |
    v
B applies INSERT
    |
    v
B publishes applied change to A
    |
    v
A receives the same logical change again
~~~

### 4.1. A change can be forwarded

In a multi-node topology, a transaction can traverse multiple subscriptions. Without origin filtering, a node can receive changes it originated itself.

### 4.2. Consequences go beyond duplicate INSERTs

Loops can cause duplicate-key errors, apply worker failures, inflated WAL/network load, repeated updates, or cascading errors that are difficult to diagnose.

### 4.3. Replication origin

PostgreSQL tracks the origin of transactions applied via logical replication. Origin metadata distinguishes whether a change came from a local transaction or from another subscription.

### 4.4. Origin filtering

PostgreSQL 16+ supports the `origin` option on subscriptions. With `origin = none`, the subscription receives only changes that originated locally at the publisher and skips changes already replicated from another origin.

### 4.5. Loop prevention is not conflict resolution

Origin filtering prevents a transaction from forwarding in a loop in an appropriate topology. It does not decide which transaction wins when two independent local transactions modify the same row.

## 5. Bidirectional topology on PostgreSQL 16+

A simple two-node design creates publications on both A and B, with each node subscribing to its peer's publication using appropriate origin filtering.

~~~text
Node A                                      Node B
+----------------------+          +----------------------+
| publication pub_a    | -------> | subscription sub_ba  |
| subscription sub_ab  | <------- | publication pub_b    |
| local writes         |          | local writes         |
+----------------------+          +----------------------+
       origin=none on each subscription
~~~

### 5.1. Creating the publication on A

~~~sql
CREATE PUBLICATION pub_a
FOR TABLE public.customer, public.order_header
WITH (publish = 'insert, update, delete');
~~~

### 5.2. Creating the publication on B

~~~sql
CREATE PUBLICATION pub_b
FOR TABLE public.customer, public.order_header
WITH (publish = 'insert, update, delete');
~~~

Tables require compatible schemas on both sides. Publications do not create schemas automatically.

### 5.3. Subscription on B receiving from A

~~~sql
CREATE SUBSCRIPTION sub_ba
CONNECTION 'host=node-a.example.internal dbname=appdb user=replicator sslmode=verify-full'
PUBLICATION pub_a
WITH (origin = none);
~~~

### 5.4. Subscription on A receiving from B

~~~sql
CREATE SUBSCRIPTION sub_ab
CONNECTION 'host=node-b.example.internal dbname=appdb user=replicator sslmode=verify-full'
PUBLICATION pub_b
WITH (origin = none);
~~~

This example illustrates PostgreSQL 16+; manage connection secrets per security policy rather than hardcoding passwords in scripts or source control.

### 5.5. Check version before using

The subscription `origin` option arrived in PostgreSQL 16. On older versions, do not assume an equivalent native mechanism exists. Never deploy reciprocal subscriptions mechanically without a verified loop-prevention design.

## 6. Meaning of origin = none

Origin filtering distinguishes transactions generated locally on the publisher from transactions received from a replication origin.

### 6.1. Local transaction on A

A performs a local INSERT. When A publishes this transaction, its origin is local. B receives and applies it.

### 6.2. B applies the transaction from A

B records the transaction's origin as coming from A. The change was replicated, not created locally by B.

### 6.3. B publishes to A

If B's publication covers that change, A's subscription from B with `origin = none` filters out transactions with remote origins, avoiding forwarding A's own transaction back to A.

### 6.4. Local transactions on B are still transmitted

An INSERT executed directly by an application on B has a local origin. Subscription A receiving from B with `origin = none` can receive and apply that change.

### 6.5. Configuration must be symmetric and verified

Set origin filtering on every subscription that could receive forwarded changes. Verify actual behavior in labs and via metrics; do not rely solely on the option name.

## 7. Limitations of origin filtering

Origin filtering helps prevent loops, but does not turn PostgreSQL into a distributed database with conflict resolution.

### 7.1. Does not prevent concurrent local writes

If A and B both update row `id=10`, each transaction has a local origin on its originating node. Both will be transmitted and conflict when applied on the peer.

### 7.2. Does not create global uniqueness

Two nodes can independently generate the same primary key. Origin filtering does not coordinate global key allocation.

### 7.3. Does not resolve cross-stream ordering

Each subscription has its own stream and apply order. There is no automatic global ordering for transactions originating independently on two nodes.

### 7.4. Does not synchronize DDL

`ALTER TABLE` on A does not automatically run on B. Schema drift can break apply or cause data to be interpreted differently.

### 7.5. Does not replace application ownership

Applications still need to know which node is permitted to write which rows/tenants, or enforce rules for handling concurrent changes.

## 8. Common conflict types

| Conflict type | Example | Common consequence |
|---|---|---|
| Duplicate key | Two nodes INSERT the same `id` | Unique violation |
| Missing row | DELETE/UPDATE on receiving node finds no row | Apply error |
| Concurrent update | Two nodes modify the same row | Change applies onto altered state or conflicts |
| Unique constraint | Two rows with different `id` share same `email` | Unique violation |
| Foreign key | Referenced row does not exist yet | FK violation |
| Check/exclusion constraint | Data from peer violates constraint | Apply error |
| Schema mismatch | Column/type mismatch | Decode/apply error |
| Truncate interaction | TRUNCATE mismatches publication/relationships | Widespread data deletion or apply failure |

### 8.1. INSERT duplicate key

A and B both insert customer `id=500`. When A's change arrives at B to apply, B already has key `500` from a local write, so the unique constraint fails.

### 8.2. UPDATE on an already-changed row

A updates `status='paid'`, B updates `status='cancelled'`. As streams arrive, each side may apply changes over different row states; native apply does not automatically merge both values.

### 8.3. DELETE of a nonexistent row

A deletes a row while B already deleted it locally or lacks it due to sync/filtering. Apply DELETE may fail to locate the target row by expected identity.

### 8.4. Distinct primary keys colliding on a business key

A creates user `id=101` with email `x@example.com`; B creates user `id=202` with the same email. Primary keys do not collide, yet the unique email constraint still conflicts.

### 8.5. Constraint errors halt apply

When the apply worker hits a transaction error, it can stop processing the subscription. Subsequent transactions cannot proceed down that stream until the error is resolved.

## 9. How does PostgreSQL handle conflicts?

Native logical replication does not automatically apply “last write wins” or merge fields on conflict. The subscriber executes operations from the stream; constraint/apply errors are raised and require operator or application intervention.

### 9.1. The apply worker can stop

A transaction error can halt the apply worker for that subscription. Subsequent transactions cannot advance along the same stream until the error is resolved.

### 9.2. Infinite retries do not fix conflicts

If the conflicting row/key/constraint remains in conflict, retries repeat the same error. Inspect current data and make the right decision.

### 9.3. Conflicts cannot always be solved by DELETE

Deleting the conflicting row to let apply continue can destroy valid data on the receiving node. Determine the business owner and merge rules.

### 9.4. Logs are a critical diagnostic source

PostgreSQL logs usually report duplicate keys, relations, constraints, and apply context. Record the LSN/transaction context for cross-checking.

### 9.5. Subscriber data may have already diverged

After a transaction fails, nodes may continue accepting local writes. Divergence widens over time unless writes are paused or a reconciliation plan is executed.

## 10. Establishing data ownership rules

The most effective way to minimize conflicts is to restrict which node is allowed to write each slice of data.

### 10.1. Single-writer per table

Some tables allow writes only on A; B reads the replica. Other tables are owned by B.

### 10.2. Single-writer per tenant

Each tenant is assigned a home region/node. Only the owning node accepts writes for that tenant; changes replicate to the peer for reads.

### 10.3. Keyspace partitioning

A generates keys in one range/prefix, while B generates keys in another range/prefix—for example, A uses node prefix 1 and B uses node prefix 2, or both use UUIDs.

### 10.4. Ownership transfer

Moving a tenant from A to B requires a protocol: freeze writes on A, sync remaining changes, switch owner, confirm B caught up, and only then open writes on B.

### 10.5. Enforce ownership in both application and database

Documenting a policy is not enough. Enforce it via service routing, role privileges, row-level security, stored procedures, or validation triggers where suitable. Ensure replication apply is not inadvertently blocked by local policies.

## 11. Primary keys and global uniqueness

Bidirectional nodes must generate non-colliding identifiers.

### 11.1. UUID

Random or standards-compliant UUIDs dramatically reduce key collision risk across nodes. Keep unique constraints and collision handling in place even when probability is tiny.

### 11.2. Node-specific ranges

Each node uses a disjoint sequence range—such as A issuing even numbers and B issuing odd numbers, or non-overlapping blocks. Define an allocation policy and procedures for node loss or role changes.

### 11.3. Composite keys

Include a node/tenant/region identifier in the primary key, such as `(origin_node, local_id)`. All foreign keys and API references must carry all components.

### 11.4. Sequences are not replicated like table data

Logical replication does not sync sequence states to guarantee global uniqueness. Two nodes sharing identical sequence start/increment settings will allocate duplicate IDs.

### 11.5. Business keys can still collide

Emails, usernames, invoice numbers, or external references may be globally unique. Enforce central allocation, ownership, or a conflict-resolution policy for those keys.

## 12. Update conflicts and merge semantics

A row modified independently on two nodes is a business problem, not purely a technical one.

### 12.1. Last-write-wins

You can build a rule picking the version with the higher timestamp/version, though wall clocks can skew and commit order across two nodes is not globally linear. Deterministic tie-breakers and auditing are needed.

### 12.2. Field-level merge

If A updates `phone` while B updates `address`, fields can be merged individually if business semantics permit. However, both nodes editing the same field still requires a rule.

### 12.3. Version columns

A `version`/`updated_at` column helps detect stale updates or establish policy ordering. It does not automatically resolve conflicts unless versions are allocated globally or deterministically.

### 12.4. Append-only events

Instead of updating the same row in place, store immutable events with unique event IDs and derive state. This reduces overwrite conflicts, but still requires idempotency and an ordering model.

### 12.5. CRDTs or domain-specific merges

Some domains can use commutative operations (counters/sets/mergeable state). Use these only when merging fits business semantics and rules are well defined; do not treat every relational table as an automatic CRDT.


## 13. Replica identity and applying UPDATE/DELETE

Logical replication must identify which row on the subscriber corresponds to a row updated or deleted on the publisher. PostgreSQL uses replica identity to determine the lookup key for these operations.

### 13.1. Default primary key

If a table has a primary key, the primary key is normally the default replica identity. The subscriber needs the matching key to locate the row to modify.

### 13.2. REPLICA IDENTITY USING INDEX

An eligible, non-partial unique index meeting PostgreSQL criteria can serve as replica identity:

~~~sql
ALTER TABLE public.customer
REPLICA IDENTITY USING INDEX customer_replica_key;
~~~

The index must satisfy uniqueness, NOT NULL, and supported index type requirements.

### 13.3. REPLICA IDENTITY FULL

Without a suitable key, `FULL` logs the entire old row in WAL logical decoding:

~~~sql
ALTER TABLE public.audit_item REPLICA IDENTITY FULL;
~~~

This enlarges WAL volume and makes row lookup on the subscriber costlier, especially for large tables.

### 13.4. Lacking an appropriate replica identity

A table without a suitable replica identity can publish INSERTs, but UPDATE/DELETE will not be supported as needed. Verify configuration before enabling bidirectional publications.

### 13.5. Identities must match on both sides

If A and B have different keys/replica identities, apply can fail or match unintended rows. Manage schema contracts jointly.

## 14. Publication scope, row filters, and column lists

Publications define what data is transmitted. In a bidirectional topology, scope must be designed to avoid emitting rows a node does not own or should not forward.

### 14.1. Publishing an explicit table list

~~~sql
CREATE PUBLICATION pub_orders
FOR TABLE public.orders, public.order_items
WITH (publish = 'insert, update, delete');
~~~

This is explicit for a small set of tables. New tables must be added intentionally.

### 14.2. FOR ALL TABLES

A publication can publish all eligible tables, but broad scope raises the risk of inadvertently sending sensitive data, unsuitable tables, or tables whose semantics cannot handle multi-writer setups. Use only when inventory and schema governance are strict.

### 14.3. Row filters

PostgreSQL supports row filters on publications in modern releases. Filters can restrict emitted rows—for example, publishing only tenants belonging to one region:

~~~sql
CREATE PUBLICATION pub_region_a
FOR TABLE public.orders
WHERE (region_id = 1);
~~~

Row filters are replication filters, not a security boundary replacing RLS/IAM.

### 14.4. Column lists

Column lists can restrict published columns. The subscriber must have matching columns for operations and schema. Primary/replica identity columns must meet version rules.

### 14.5. Bidirectional filters must be designed consistently

If A publishes tenant 1 and B publishes tenant 2, filters and ownership rules must ensure every row has one authoritative writer. Never allow local writes to the same row on both sides simply because two filters fail to be mutually exclusive.

## 15. Row ownership via publication filters

One pattern partitions data by tenant or region so each node writes its own row subset while both hold replicas of each other.

~~~text
Node A owns region_id = 1
Node B owns region_id = 2

A -- publish region 1 --> B
B -- publish region 2 --> A
~~~

### 15.1. Each node publishes its local rows

A publishes only rows owned by A; B publishes only rows owned by B. When A receives rows from B, origin filtering prevents them from looping back.

### 15.2. Received data can be policy-enforced read-only

Applications may read all regions locally while writing only the node's owned region. Enforce ownership at the service/DB layer.

### 15.3. Cross-region foreign keys

A row for tenant 1 might reference tenant 2. If the two rows replicate at different times or via different filters, FKs can fail. Design data models and ordering accordingly.

### 15.4. Row filters do not solve concurrent ownership transfers

When moving a tenant from A to B, freeze writes and transfer ownership in a controlled manner. Changing a filter alone does not prevent in-flight writes.

### 15.5. Global tables

Country codes, product catalogs, or shared configuration tables can be written on a single designated node and replicated unidirectionally. Not every table needs bidirectional publishing.

## 16. Partitioned tables in bidirectional logical replication

Partitioning can help divide workloads or keyspaces, but requires attention to how publications represent partition roots versus leaf tables.

### 16.1. Publishing via partition root

With `publish_via_partition_root` set appropriately, changes from partitions are sent as changes on the root table. This lets the subscriber maintain its own partition structure as designed.

### 16.2. Publishing leaf partitions

Partitions can be published individually, provided topology and mappings align. A row moving across partitions due to an UPDATE of the partition key may appear as DELETE/INSERT depending on behavior.

### 16.3. Partition ownership

You can partition by region/tenant so each node owns specific partitions. However, replication apply and table identity must be tested against your exact schema/partition layout.

### 16.4. Do not equate partition pruning with replication filtering

Partitioning organizes storage and row routing inside a database. Publication filters and row ownership are separate mechanisms that must be configured explicitly.

### 16.5. Schema changes on partitions

Creating, dropping, attaching, or detaching partitions is DDL and is not automatically sent to peers by logical replication. Execute synchronized migrations under schema governance.

## 17. TRUNCATE and broad-scope operations

`TRUNCATE` is special because it affects an entire table rather than individual rows.

### 17.1. Publications can enable TRUNCATE publishing

If a publication includes `truncate`, `TRUNCATE` on a publisher can be forwarded to subscribers. Check `publish` options before using.

### 17.2. Risk in bidirectional topologies

One node might `TRUNCATE` a table while its peer holds valid unsent local rows. When the operation applies, those rows can be wiped from the peer.

### 17.3. TRUNCATE is not a row-level conflict

Origin filtering stops transactions from looping, but does not stop `TRUNCATE` from deleting rows owned by another node if publication scope permits it.

### 17.4. Do not publish TRUNCATE if semantics are unsafe

Publish only `insert, update, delete` for sensitive tables, or coordinate truncates during a maintenance window with freezes.

### 17.5. Foreign keys and cascades

`TRUNCATE` has specific rules for referenced tables and `CASCADE`. Check schemas on both sides and never use `CASCADE` as a conflict workaround.

## 18. Objects not synchronized automatically by logical replication

Logical replication focuses on row changes of published tables. Many metadata types and objects must be managed separately.

| Object | Native logical replication |
|---|---|
| Table row changes | Yes, if table is published |
| DDL/schema changes | Not automatically replicated |
| Sequence state | Not automatically replicated like row changes |
| Roles/global privileges | No |
| Tablespaces | No |
| Large objects | Not replicated like table rows |
| Views/functions/triggers | Definitions not automatically replicated |
| Materialized view contents | Not automatically synced like published tables |
| Extensions/binaries | No |
| Server configuration | No |

### 18.1. DDL requires a schema migration pipeline

Use migration tools or deployment workflows to apply matching schema versions across both nodes. Migration order must stay compatible with the running stream.

### 18.2. Sequences need an allocation policy

Never let two nodes use sequences with identical start/increment settings for the same keyspace. Use UUIDs, disjoint ranges, or central key allocation.

### 18.3. Roles and grants require IaC/configuration

Manage roles, ownership, and grants via dedicated scripts/migrations. Never expect subscriptions to create login roles automatically.

### 18.4. Large objects require a separate solution

If applications use PostgreSQL large objects, plan how to back up and replicate them. Moving binary content to object storage or a `bytea` table may fit better if appropriate for the domain.

### 18.5. Trigger behavior must be understood

Logical apply uses replication role semantics; regular triggers do not necessarily fire the same as local DML. Triggers configured as `REPLICA` or `ALWAYS` behave differently. Avoid trigger side effects that generate extra writes or loops.

## 19. Schema evolution and bidirectional rollouts

Schema drift is a common cause of logical apply failures or semantic divergence between nodes.

### 19.1. Expand-and-contract

A safe migration typically adds nullable/compatible columns first, deploys application code compatible with both schemas, backfills, switches reads/writes, and removes old columns only after all nodes are synchronized.

### 19.2. DDL ordering

Apply schema changes to subscribers before publishers start sending rows requiring new columns, or follow a tested rollout sequence. DDL does not replicate automatically.

### 19.3. Type changes

Changing types, renaming/dropping columns, or altering collations can break apply compatibility. Split migrations into separate additive and destructive phases.

### 19.4. Publication refresh

When adding a table to a publication, subscriptions may need `REFRESH PUBLICATION` to pick up the new table. Refreshing can trigger table synchronization depending on options.

### 19.5. Schema version checks

Record schema migration versions on each node and alert on drift. Never open bidirectional writes unless schemas satisfy the compatibility contract.

## 20. Initial sync for two nodes

Bidirectional initialization is the most sensitive phase because both sides may already contain data and independent writes.

### 20.1. Never blindly enable bidirectional copy_data

If both A and B already hold overlapping rows, two initial table syncs can try to insert duplicate keys. Apply conflicts can erupt immediately upon initialization.

### 20.2. Select a baseline

Establish a canonical source per table/tenant/key range or use a snapshot taken from a consistent state. Document snapshot/LSN and ownership.

### 20.3. Freeze or fence writes during bootstrap

For tables needing a shared baseline, pause writes during snapshot/copy and transition. If freezing is impossible, design a careful capture/catch-up protocol.

### 20.4. Preload then use copy_data=false

One pattern preloads baseline data into the subscriber from a verified backup/ETL, then creates the subscription with `copy_data=false` starting from the matching replication slot/consistent point. Align LSNs/slots accurately; never skip initial copy arbitrarily.

### 20.5. Enable the second direction after verifying the first

Bring one direction to steady state, verify origin behavior, row ownership, and conflict monitoring, and only then enable the reverse direction per plan. For active bidirectional writes, ownership rules must already be enforced before opening both sides.

## 21. Replication slots and WAL retention in logical replication

Each subscription typically uses a logical replication slot on its publisher to retain WAL needed for decoding/apply.

### 21.1. Slots on the publisher

Subscription B receiving from A has a corresponding slot on A. Subscription A receiving from B has a separate slot on B.

### 21.2. Inactive slots can retain WAL

If a subscriber stops operating, the slot retains WAL and drives up disk usage on the publisher. Monitor slot activity and retained WAL.

### 21.3. Both directions fail independently

A→B can run cleanly while B→A stops. Monitor each slot/subscription and alert per direction.

### 21.4. max_replication_slots and max_wal_senders

Provision enough slots and senders for subscriptions, physical standbys, backup tools, and maintenance. Size each node independently.

### 21.5. Lost slots

If a slot is dropped or the publisher loses needed WAL, the subscriber cannot resume from its old position. Resyncing/reseeding or creating a new slot after establishing a consistency boundary may be required.



## 22. Monitoring subscriptions and apply workers

Logical replication provides statistics views to observe each subscription and worker. Monitor A→B and B→A directions separately.

### 22.1. pg_stat_subscription

On the subscriber, query:

~~~sql
SELECT
    subname,
    pid,
    relid,
    received_lsn,
    last_msg_send_time,
    last_msg_receipt_time,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription
ORDER BY subname, relid;
~~~

This view shows subscription workers and message receipt progress. Columns may vary by PostgreSQL version.

### 22.2. Subscription without a worker

If `pid` is NULL or no expected row appears, the subscription may be disabled, the worker has not started, or it is in another table synchronization state. Check `pg_subscription` and logs.

### 22.3. pg_stat_subscription_stats

PostgreSQL versions supporting this view expose counters such as `apply_error_count` and `sync_error_count`:

~~~sql
SELECT
    subname,
    apply_error_count,
    sync_error_count,
    stats_reset
FROM pg_stat_subscription_stats
ORDER BY subname;
~~~

Counters must be read alongside server logs; resetting stats does not remove the root cause of errors.

### 22.4. pg_replication_origin_status

On the subscriber, this view reports progress by replication origin:

~~~sql
SELECT
    external_id,
    remote_lsn,
    local_lsn
FROM pg_replication_origin_status
ORDER BY external_id;
~~~

This helps cross-check remote progress against local WAL positions.

### 22.5. pg_replication_slots on the publisher

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status,
    safe_wal_size
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Some columns exist only in newer versions. Use catalog queries matching your running major version.

## 23. Monitoring lag and freshness

Bidirectional replication has at least two lag directions, and each direction may spawn separate table sync workers.

### 23.1. Last message receipt

Compare `last_msg_receipt_time` against current time to detect stalled message delivery. During idle workloads, an old timestamp does not necessarily mean failure; use heartbeats or synthetic writes to measure freshness.

### 23.2. Latest end LSN

Track `latest_end_lsn` and `latest_end_time` per subscription. This is the latest reported stream checkpoint, not proof that every table has fully applied.

### 23.3. Origin progress

`remote_lsn` shows remote progress per origin; compare it against `local_lsn` and publisher-side WAL positions.

### 23.4. Apply error counters

Rising `apply_error_count` or `sync_error_count` signals you must inspect logs and worker status. Do not alert solely on worker PID.

### 23.5. Business freshness

A subscription may appear healthy while a critical table is unpublished or filtered out by a row filter. Verify business freshness using heartbeat rows or canary records per policy.

## 24. Troubleshooting a stalled apply worker

When a subscription stops due to a conflict, stop guessing and identify the exact transaction, row, and constraint.

### 24.1. Read PostgreSQL logs

Look for duplicate keys, missing rows, foreign keys, check constraints, relation/schema mismatches, and transaction context. Record the LSN/commit LSN if logged.

### 24.2. Identify the failing direction

Distinguish A→B from B→A. Check the corresponding publisher, subscriber, slot, and origin. Never mistake a single-direction error for a cluster-wide failure.

### 24.3. Capture data state on both sides

Fetch involved rows from A and B along with primary keys, versions, timestamps, and business metadata. Preserve evidence before modifying data.

### 24.4. Quiesce writes if divergence is growing

If conflicts may repeat or widen divergence, pause related writes or disable the subscription per runbook. Do not let nodes keep creating dependent records against disputed rows.

### 24.5. Repair per business rules then resume

Select the canonical state or merge according to approved rules. After repairing, enable the subscription, confirm the apply worker advances past the failing LSN, and verify the reverse direction.

## 25. Skip transaction: use only as a controlled measure

Some PostgreSQL versions support skipping a failing transaction via `ALTER SUBSCRIPTION ... SKIP` with a specific commit LSN. This is a dangerous operational tool if used as a substitute for conflict resolution.

### 25.1. When is skipping considered?

Only after investigating the transaction, understanding its full impact, obtaining approval to bypass it, and having a plan to reconcile missing data. Never skip solely to get the worker running again.

### 25.2. Skipping loses a transaction on the subscriber

The publisher committed that transaction. Skipping means the subscriber will omit all changes in that transaction while subsequent transactions continue applying.

### 25.3. Transactions can modify multiple tables

Skipping an entire transaction can drop many row changes and break business invariants or foreign keys. Inspect the full transaction scope before deciding.

### 25.4. Version and syntax

Availability and syntax of subscription skip depend on PostgreSQL version. Verify exact major-version documentation and the failing transaction's commit LSN before executing.

### 25.5. Reconcile after skipping

Log the skipped transaction/LSN, affected data, repairs applied on both nodes, and verification results. Skipping alone does not establish a consistent state.

## 26. Conflict resolution runbook

A conflict-handling workflow may follow these steps:

1. Record incident ID, subscription direction, and timestamp.
2. Identify the failing transaction/LSN and relation.
3. Capture involved rows on both publisher and subscriber.
4. Determine the row owner and business source of truth.
5. Select the merge rule: keep A, keep B, merge fields, or reconstruct from event logs.
6. Pause affected writes and necessary subscription directions.
7. Apply audited repairs on nodes per plan.
8. If skipping is unavoidable, record the bypassed transaction and reconcile all omitted changes.
9. Resume subscriptions/apply workers.
10. Confirm LSNs advance and both directions are healthy.
11. Run unique/FK/business invariant checks on both nodes.
12. Document root cause and ownership/schema updates to prevent recurrence.

### 26.1. Do not use “newer node” as a default rule

Clocks can skew; a later timestamp update might be derived from stale state. Use explainable version, ownership, or domain rules.

### 26.2. Do not fix one side and forget the reverse direction

A local repair transaction may replicate back to the peer. Control subscriptions and writes so repairs do not trigger new conflicts.

### 26.3. Audit before deleting

If deleting a duplicate row, save snapshots/exports and justification. A `DELETE` can propagate to the peer once replication resumes.

### 26.4. Handle idempotency

Application events and reconciliation jobs require event IDs/checkpoints so retries never produce duplicate side effects.

### 26.5. Verify data after the worker resumes

A running worker proves only that apply resumed; verify business correctness of the data.

## 27. Pausing and re-enabling subscriptions

Subscriptions can be disabled/enabled for maintenance or incident handling.

~~~sql
ALTER SUBSCRIPTION sub_ab DISABLE;
ALTER SUBSCRIPTION sub_ab ENABLE;
~~~

### 27.1. Disabling one direction does not stop the other

If A→B is disabled, B→A can keep running. State can diverge further if both sides continue writing overlapping rows.

### 27.2. Slots may continue retaining WAL

While a subscription is disabled, the logical replication slot on the publisher can continue retaining WAL. Monitor disk space and slot retention during maintenance.

### 27.3. Do not drop slots arbitrarily

Dropping a slot can lose the ability to resume from the previous position. Before dropping, establish exactly how the subscription will be resynced/recreated.

### 27.4. Re-enable only after schemas are ready

Ensure tables, columns, types, and constraints match on both nodes before enabling.

### 27.5. Monitor catch-up

Watch slot `confirmed_flush_lsn`, subscription progress, apply errors, and business freshness until the stream catches up.

## 28. Resynchronization after severe divergence

If both nodes have drifted substantially or a slot/WAL was lost, per-conflict repair may become impractical.

### 28.1. Select the authoritative dataset

Determine the authoritative source of truth per table/tenant/key range. Never choose a node merely because it has more rows.

### 28.2. Pause writes

Freeze the ownership scope during snapshot/reseed to keep data from mutating mid-copy.

### 28.3. Create a consistent baseline

Use logical dump/ETL snapshots or another appropriate copy method. Record the snapshot boundary and how streaming starts afterward.

### 28.4. Recreate subscriptions/slots in a controlled manner

If new slots are required, align snapshots and replication start points. Never use `copy_data=false` without a baseline proving the subscriber is synced to the exact point.

### 28.5. Validate before opening writes

Verify row counts, checksums, business invariants, ownership, unique keys, and origin filtering. Open writes per region/scope only after confirmation.

## 29. Initial synchronization and concurrent writes

Initial table synchronization runs in dedicated workers. In a bidirectional topology, both sides copying data simultaneously must be tightly controlled.

### 29.1. Copying data from A to B

If B already holds locally created rows with colliding primary keys, initial copy fails with duplicate key errors. Use clean baselines or ownership rules to prevent collisions.

### 29.2. Copying data from B to A

If the reverse direction starts immediately, A may also receive rows it already owns or is actively updating. Never assume two concurrent initial syncs merge safely.

### 29.3. copy_data=false

Use when the subscriber was preloaded from a matching baseline and the replication start position is precisely aligned. It does not verify by itself that both datasets match.

### 29.4. Table sync progress

Monitor table synchronization state in the version's subscription relation catalog, logs, and worker state.

### 29.5. Opening writes per ownership

Once baseline and streams catch up, enable writes per region/tenant. Avoid opening concurrent writes for overlapping keys before conflict policies take effect.

## 30. Consistency model and applications

Logical replication is asynchronous by default. Subscribers can lag behind publishers, and bidirectional setup does not form a shared transaction boundary.

### 30.1. Eventual consistency

Once writes stop and replication catches up, both nodes can converge provided no unresolved conflicts exist and all changes are applied.

### 30.2. Read-your-writes

If a client writes on A and immediately reads from B, B may not yet have received/applied the transaction. Route reads to the node that accepted the write or wait for replication progress per policy.

### 30.3. Monotonic reads

Clients bouncing between two nodes with differing lag can observe older state. Sticky routing, version tokens, or read-source affinity mitigate this.

### 30.4. Cross-node transactions

A workflow writing to A and then to B does not become atomic merely because A and B replicate bidirectionally. If one half commits and the other fails, application-level sagas, outboxes, idempotency, or coordination are required.

### 30.5. Business consistency

Define invariants such as non-negative inventory, balanced ledgers, globally unique usernames, and valid order/payment transitions. Run checks after conflicts/resyncs and alert on violations.



## 31. Multi-node topologies and multi-hop loops

Two nodes is the simplest case. With A, B, C, and D, topologies become meshes or hub-and-spoke. Each added link increases paths a transaction can traverse.

~~~text
             A
           /   \
          B     C
           \   /
             D
~~~

### 31.1. Meshes easily form multiple loop paths

If every node publishes to every other node, a change can travel multiple paths. Origin filtering helps suppress remote-origin changes, yet the topology still must be designed and verified.

### 31.2. Hub-and-spoke

A hub can act as an exchange point for spokes. However, a hub does not automatically resolve conflicts when two spokes create the same business key or edit the same row.

### 31.3. Do not use origin as a global conflict key

Origins identify a transaction's source in the replication stream. They are neither a global transaction coordinator nor a row version usable for automatically picking a winner.

### 31.4. One node can receive from multiple origins

Track replication origins separately and map each to its publisher/peer. Name nodes and subscriptions clearly to simplify investigation.

### 31.5. Limit connection paths

Every publication/subscription adds slots, workers, network sessions, and operational state. Create only links necessary for ownership and failure domains.

## 32. Multi-region and network partitions

Bidirectional replication is often considered across regions, yet network partitions expose the trade-off between availability and consistency.

### 32.1. Both regions accept writes

When inter-region connectivity breaks, each node may continue accepting local writes. Upon network recovery, rows modified on both sides can conflict.

### 32.2. Network partitions do not arbitrate writers

Logical replication neither elects leaders nor grants write leases. An application or cluster control plane must enforce writer authority.

### 32.3. Fencing and ownership leases

Use leases, leader assignment, or fencing tokens at the orchestration layer so only the authorized node accepts writes for an ownership scope.

### 32.4. Split-brain writes

If two nodes both believe they are authoritative for the same tenant/row, they can commit incompatible states. When the stream reconnects, apply errors are only the symptom; ownership is the root problem.

### 32.5. Fail closed or accept local writes?

The business must decide during partitions: reject writes in the region lacking authority, or continue accepting writes with reconciliation afterward. No system can stay universally available and guarantee every write is conflict-free without appropriate coordination or domain models.

## 33. Publisher failover and subscription continuity

A logical subscription connects to a specific publisher. When a publisher fails over to another server, ensure subscribers can resume from a valid slot and position.

### 33.1. Do not assume logical slots fail over automatically

In many configurations/versions, logical slots live only on the old publisher. If that node is lost, subscribers may lose their slots or the new publisher endpoint may lack matching slots.

### 33.2. Failover slots by version

Newer PostgreSQL versions improve support for failover logical replication slots, but require specific configuration and synchronization. Check exact major-version and provider documentation before relying on this feature.

### 33.3. Evaluating slot state after promotion

Verify slot names, `restart_lsn`, `confirmed_flush_lsn`, failover/synced state if provided by the version, and whether the new publisher can serve subscriptions.

### 33.4. If a slot cannot resume

You may have to recreate subscriptions/slots and resynchronize data from a baseline. Never create a new slot and continue as if no gap occurred; reconciliation is required.

### 33.5. Subscriber HA must also be tested

If a subscriber is protected by a physical standby, verify subscription worker/slot states, origin progress, and apply behavior after promoting the subscriber standby before opening writes.

## 34. Synchronous commit and data durability

Native logical replication is asynchronous by default. Subscriber apply happens after publisher commit.

### 34.1. Commit on A does not mean B has applied

An application may receive commit success on A before B has received or applied the transaction. Reads from B can be stale.

### 34.2. Local synchronous_commit

The `synchronous_commit` setting controls durability on the committing server. It does not automatically turn two logical subscriptions into a distributed synchronous transaction.

### 34.3. No global atomic commit

If a workflow writes separately to A and B, one side can commit while the other fails. Use application-level transaction coordination, outbox/saga patterns, or a single-writer model as required.

### 34.4. Durability and convergence are distinct goals

WAL `fsync` on A protects local commits per configuration; it does not prove B has applied or that both nodes have converged.

### 34.5. Define freshness SLOs

Establish maximum allowed data staleness at each peer and alert on breaches. For read-after-write guarantees, route or wait on tokens rather than assuming immediate propagation.

## 35. Security and replication privileges

Logical replication can transmit sensitive data from one database to another. Protect publisher roles and subscriber identities.

### 35.1. Replication role

Use a dedicated role with required privileges to connect for replication and read published data. Never grant `SUPERUSER` without an approved justification.

### 35.2. Publication scope is data access scope

Overly broad publications can send more tables, columns, or rows than the peer application needs. Limit table lists, row filters, and column lists to the data contract.

### 35.3. TLS

Enforce TLS with proper certificate validation on publisher/subscriber connections. Manage certificate rotation and hostname verification.

### 35.4. Secret management

Never store plaintext passwords in repositories, logs, or shared configs. Use a secret manager or permission-restricted files with rotation workflows.

### 35.5. Network allowlists and auditing

Allow only authorized subscriber hosts to connect to the publisher. Audit publication/subscription changes, slot operations, role grants, and data exports.

## 36. Performance and capacity planning

Bidirectional replication places load on both nodes: logical decoding, WAL retention, networking, apply workers, and index/constraint maintenance.

### 36.1. Publisher workload

Logical decoding reads WAL and builds change streams. Many publications/subscriptions and high write rates raise CPU/I/O and WAL retention.

### 36.2. Subscriber apply workload

Apply workers execute row changes, check constraints, and update indexes. Subscribers accepting concurrent local writes compete for locks and I/O with apply.

### 36.3. Network bandwidth

Size bandwidth for actual WAL change volume, protocol/compression overhead, and bursts. Both directions generate independent traffic.

### 36.4. Index maintenance

Subscribers need appropriate indexes and constraints. Excessive secondary indexes slow apply writes, while missing unique constraints risk invalid data.

### 36.5. Backpressure

If apply slows down, the replication slot retains WAL on the publisher. Monitor disk growth and lag; never simply raise slot retention without fixing apply throughput.

## 37. Operational rules for bidirectional setups

Each node can act as both publisher and subscriber. Runbooks must specify which actions run on which node.

### 37.1. Changing publications

When adding or removing tables on A, evaluate subscriptions on B and refresh publications. Do the same for the B→A direction.

### 37.2. Schema changes

Apply DDL via controlled migration sequences across both nodes. Never let a publisher emit a new row shape to a subscriber lacking the matching column.

### 37.3. Pausing one direction

Document reason, expected duration, and WAL retention. If the peer keeps writing, divergence can grow.

### 37.4. Restarting workers

After fixing an error, enable the subscription and verify apply progress. Check the reverse direction to confirm repairs did not trigger new errors.

### 37.5. Concluding maintenance

Verify slot health, lag, business invariants, schema versions, duplicate keys, and audit trails.

## 38. When should bidirectional logical replication be used?

It can work well when two systems exchange a bounded dataset with clear ownership and low conflict rates.

### 38.1. Multi-region read/write with per-tenant ownership

Each tenant has one home write region; data replicates so other regions can read. Ownership transfers are coordinated.

### 38.2. Data exchange between two applications

Two databases own distinct tables and publish only shared tables/rows. Master tables retain a single writer.

### 38.3. Time-bounded parallel migration

During migrations, logical replication streams changes from source to target; the reverse direction is enabled only with a controlled rollback/dual-write plan and full understanding of conflict risks.

### 38.4. Edge sites

Edge nodes can write local datasets and forward events/rows to a central system. Offline duration, duplicate events, and conflicts must be handled.

### 38.5. Unsuitable when every node freely writes the same rows

If all nodes modify all tables without ownership, unique key strategies, or conflict resolution, native logical replication will frequently stall on apply errors and accumulate divergence.

## 39. When is another solution needed?

If requirements call for unrestricted active-active writes on the same data, evaluate alternative architectures.

### 39.1. Single-writer routing

Route writes to one primary/owner per data partition. This is usually the simplest way to prevent concurrent conflicts.

### 39.2. Event-driven integration

Publish domain events and process them idempotently in consumers. Event models often support reconciliation better than replicating raw row updates.

### 39.3. Application-level conflict resolution

Applications can store versions, origins, event IDs, and domain-specific merge policies. Database replication merely transports already-resolved changes.

### 39.4. Multi-master extensions/services

Some third-party solutions offer conflict handling, distributed key generation, or multi-master orchestration. Evaluate version compatibility, support models, failure semantics, and test recovery.

### 39.5. Distributed databases

If strong consistency, availability, and multi-region write semantics are core requirements, consider systems designed natively for distributed transactions/consensus or partitioned ownership from the ground up.



## 40. Lab: setting up two-node bidirectional logical replication

This lab uses two separate PostgreSQL instances on the same major version with matching schemas and an isolated network. Never use production data.

~~~text
Node A (port 5432) <------> Node B (port 5433)
       pub_a                    pub_b
       sub_ab                   sub_ba
~~~

### 40.1. Creating identical tables

Run on both A and B:

~~~sql
CREATE TABLE public.replication_lab (
    id UUID PRIMARY KEY,
    origin_node TEXT NOT NULL,
    payload TEXT NOT NULL,
    version_no BIGINT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

### 40.2. Creating replication roles

On each publisher, create a role with replication privilege and SELECT privileges needed for publication/table sync. Use isolated lab credentials and HBA rules restricted to the peer.

### 40.3. Creating publications on A and B

~~~sql
CREATE PUBLICATION pub_a
FOR TABLE public.replication_lab
WITH (publish = 'insert, update, delete');

CREATE PUBLICATION pub_b
FOR TABLE public.replication_lab
WITH (publish = 'insert, update, delete');
~~~

### 40.4. Creating subscriptions with origin filtering

On B:

~~~sql
CREATE SUBSCRIPTION sub_ba
CONNECTION 'host=127.0.0.1 port=5432 dbname=labdb user=replicator'
PUBLICATION pub_a
WITH (origin = none);
~~~

On A:

~~~sql
CREATE SUBSCRIPTION sub_ab
CONNECTION 'host=127.0.0.1 port=5433 dbname=labdb user=replicator'
PUBLICATION pub_b
WITH (origin = none);
~~~

Adjust host, port, database, and SSL for your lab environment. On empty tables, initial copy transfers little data; with baseline data, design `copy_data` and LSN alignment beforehand.

### 40.5. Verifying subscriptions

On each subscriber, inspect `pg_stat_subscription` and PostgreSQL logs. Confirm both directions have running workers and zero apply/sync errors.

## 41. Lab: proving origin filtering prevents forwarding loops

### 41.1. Local insert on A

~~~sql
INSERT INTO public.replication_lab
    (id, origin_node, payload)
VALUES
    ('10000000-0000-0000-0000-000000000001', 'A', 'created on A');
~~~

### 41.2. Confirming B receives the row

On B:

~~~sql
SELECT *
FROM public.replication_lab
WHERE id = '10000000-0000-0000-0000-000000000001';
~~~

### 41.3. Confirming A does not receive the same transaction back as a local change

Monitor origin progress and subscription logs. With proper origin filtering, the transaction replicated from A is not forwarded back by B as a local-origin transaction.

### 41.4. Local insert on B

~~~sql
INSERT INTO public.replication_lab
    (id, origin_node, payload)
VALUES
    ('20000000-0000-0000-0000-000000000001', 'B', 'created on B');
~~~

Confirm A receives this row. This proves origin filtering still allows transactions created locally on the peer to flow in the reverse direction.

### 41.5. Reconciling both nodes

Compare rows/IDs and check apply errors. Origin filtering must stop loops without blocking valid local writes.

## 42. Lab: simulating a duplicate-key conflict

Run only in a lab, never on production systems.

### 42.1. Preparing a conflict window

Temporarily block replication traffic or disable subscriptions per lab procedure so both nodes accept local writes before changes are exchanged.

### 42.2. Inserting the same UUID on both nodes

On A:

~~~sql
INSERT INTO public.replication_lab
    (id, origin_node, payload)
VALUES
    ('30000000-0000-0000-0000-000000000001', 'A', 'value from A');
~~~

On B:

~~~sql
INSERT INTO public.replication_lab
    (id, origin_node, payload)
VALUES
    ('30000000-0000-0000-0000-000000000001', 'B', 'value from B');
~~~

### 42.3. Re-enabling replication

Enable subscriptions and observe logs. One side will hit a unique violation when applying a row whose key already exists locally.

### 42.4. Recording data on both sides

`SELECT` the row on A and B, inspecting `payload`, `origin_node`, and `version`. Never delete rows for a “quick fix” before recording evidence.

### 42.5. Practicing resolution

Pick a winner per lab policy, freeze writes, reconcile both nodes, resume subscriptions, and confirm both converge. Record the changed transaction/rows.

## 43. Lab: testing row ownership and row filters

### 43.1. Adding a region key

~~~sql
ALTER TABLE public.replication_lab
ADD COLUMN region_id INTEGER;
~~~

Apply the schema change on both nodes before updating publications.

### 43.2. Creating a publication filter for A

~~~sql
CREATE PUBLICATION pub_a_region
FOR TABLE public.replication_lab
WHERE (region_id = 1);
~~~

Create the matching publication on B with `region_id = 2`. Use dedicated lab publications/subscriptions for testing.

### 43.3. Writing rows per owner

A writes only region 1; B writes only region 2. Confirm rows replicate to the peer for reads.

### 43.4. Testing a wrong-ownership write

Insert a `region_id = 2` row on A and verify the publication filter omits it per configuration. Also test whether application/database policies block wrong-ownership writes.

### 43.5. Ownership transfer

Practice freezing a tenant/region, catching up the stream, changing ownership, and opening writes on the new node. Never merely edit the filter while writes keep running.

## 44. Lab: monitoring apply errors and recovery

### 44.1. Collecting subscription stats

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

~~~sql
SELECT *
FROM pg_stat_subscription_stats;
~~~

The second view is available only on supporting versions. Record counters before and after the lab.

### 44.2. Viewing origin progress

~~~sql
SELECT *
FROM pg_replication_origin_status;
~~~

Compare `remote_lsn` and `local_lsn` per origin.

### 44.3. Reading server logs

Look for duplicate key or constraint errors. Record subscription, table, key, and transaction/LSN.

### 44.4. Disabling the failing direction

In the lab, disable the failing subscription, snapshot affected rows, and select a reconciliation method. Ensure you understand slot/WAL retention while disabled.

### 44.5. Enabling and verifying

Re-enable the subscription, confirm the apply worker runs, progress advances, and business data converges. Do not check merely whether a PID exists.

## 45. Operational runbook for bidirectional replication

A production runbook should include these steps:

1. Record incident/change ID, node names, subscription direction, and timestamp.
2. Identify PostgreSQL major versions and origin filtering capabilities.
3. Map publisher/subscriber topology, slots, and ownership scopes.
4. Identify the conflicting transaction/row/constraint from logs.
5. Capture affected data on both nodes and preserve evidence.
6. Determine the node/tenant/keyspace owner and business source of truth.
7. Pause writes or subscriptions by scope to prevent widening divergence.
8. Choose resolution rule: winner, field merge, event replay, or resync.
9. Apply audited repairs across nodes.
10. If skipping a transaction, record commit LSN and reconcile all omitted changes.
11. Resume subscriptions and check origin/slot/apply progress.
12. Run unique/FK/business invariant checks on both nodes.
13. Verify schema versions and publication scopes.
14. Re-open writes under ownership policies.
15. Document root cause, action items, and proof of convergence.

### 45.1. Incident owners

Assign a database operator, application owner, and business decision maker. DBAs should not unilaterally decide which value wins when data carries business meaning.

### 45.2. Stop conditions

Halt re-opening writes if row ownership is unclear, WAL is missing, schemas mismatch, conflicts recur, or business invariants fail.

### 45.3. Evidence

Save logs, LSNs, row snapshots, subscription stats, schema versions, and approvals. Never include credentials or unnecessary sensitive data.

### 45.4. Post-resolution verification

Confirm both directions operate, slots are not retaining abnormal WAL, lag returned within SLO, and backups/PITR remain recoverable.

### 45.5. Post-incident review

Identify root causes such as colliding key allocation, unenforced ownership, misordered schema rollouts, or non-idempotent application retries. Fix the design so conflicts are less likely to recur.

## 46. Common design mistakes

1. Creating reciprocal subscriptions without a loop-prevention mechanism.
2. Assuming origin filtering resolves concurrent updates.
3. Using identical sequence start/increment values on two nodes.
4. Allowing every node to write every row without ownership.
5. Using wall-clock timestamps as conflict winners without handling clock skew.
6. Enabling bidirectional `copy_data` when both sides already have overlapping data.
7. Assuming DDL replicates automatically.
8. Forgetting sequences, roles, grants, large objects, and extension dependencies.
9. Failing to set an appropriate replica identity for UPDATE/DELETE.
10. Publishing `TRUNCATE` while two nodes own independent rows.
11. Altering schema on one side before the subscriber is compatible.
12. Forgetting to refresh publications after adding tables.
13. Failing to monitor logical replication slots and retained WAL.
14. Disabling a subscription without monitoring disk growth.
15. Skipping transactions merely to get the apply worker running again.
16. Fixing a conflict on one side while forgetting the reverse direction.
17. Failing to verify row filters and tenant ownership.
18. Treating eventual consistency as immediate consistency.
19. Reading from a peer immediately after writing without a read-your-writes policy.
20. Assuming publisher failover automatically preserves logical slots.
21. Lacking a baseline/resync plan when a slot is lost.
22. Using native logical replication as a distributed transaction coordinator.
23. Failing to test network partitions and split-brain write behavior.
24. Lacking audit trails for manual conflict resolution.
25. Never rehearsing resync after schema/data divergence.

## 47. Practice exercises

### Exercise 1 — Concept

What is bidirectional logical replication?

**Answer:** Two databases both publish local changes and subscribe to changes from their peer.

### Exercise 2 — Publisher

What does a publication do?

**Answer:** Specifies which tables/operations/rows/columns are sent from the publisher.

### Exercise 3 — Subscriber

What does a subscription manage?

**Hint:** Publisher connection, slot, initial sync, and apply worker.

### Exercise 4 — Replication loop

Why can a transaction return to its originating node?

**Answer:** A receiving node applies the transaction and then publishes it back to the source or along another path.

### Exercise 5 — Origin filtering

Which `origin` option filters out changes with remote origins?

**Answer:** `origin = none` on PostgreSQL 16+.

### Exercise 6 — Version

Starting from which PostgreSQL major version is subscription origin filtering available?

**Answer:** PostgreSQL 16.

### Exercise 7 — Conflict resolution

Does origin filtering resolve duplicate keys caused by two local writes?

**Answer:** No.

### Exercise 8 — Duplicate key

What risk arises when two nodes insert the same primary key?

**Answer:** Unique constraint violation when the peer's transaction applies.

### Exercise 9 — Missing row

Why can UPDATE/DELETE fail on a subscriber?

**Hint:** Target row does not exist or replica identity cannot locate the row.

### Exercise 10 — Replica identity

What does a table use as its default replica identity if present?

**Answer:** The primary key.

### Exercise 11 — REPLICA IDENTITY FULL

What is the main trade-off?

**Hint:** Helps identify rows, but produces larger WAL and costlier row lookups.

### Exercise 12 — Ownership

What risk does single-writer per tenant reduce?

**Answer:** Two nodes concurrently editing rows belonging to the same tenant.

### Exercise 13 — UUID

What do UUIDs solve?

**Answer:** Drastically reduce primary-key collision risk; they do not resolve business-key conflicts.

### Exercise 14 — Sequences

Does logical replication sync sequence state to guarantee global uniqueness?

**Answer:** No.

### Exercise 15 — DDL

Does `ALTER TABLE` on a publisher run automatically on a subscriber?

**Answer:** No.

### Exercise 16 — TRUNCATE

Why can publishing `TRUNCATE` be dangerous in a bidirectional setup?

**Hint:** It wipes the entire table on the peer, including rows owned by the peer.

### Exercise 17 — Row filters

Do row filters replace security policies/RLS?

**Answer:** No.

### Exercise 18 — Initial sync

Why should you not blindly enable bidirectional `copy_data`?

**Answer:** It can copy keys that already exist on the peer and trigger duplicate conflicts.

### Exercise 19 — copy_data=false

When can it be used?

**Hint:** When the subscriber is preloaded from an accurate baseline and stream start positions are aligned.

### Exercise 20 — Slot

Where does a logical replication slot reside?

**Answer:** On the publisher corresponding to the subscription.

### Exercise 21 — Slot retention

What risk can a long-disabled subscription cause?

**Answer:** The slot retains WAL and can fill up the disk.

### Exercise 22 — Apply worker

What impact can a duplicate-key error have?

**Answer:** The apply worker stops and subscription lag grows until resolved.

### Exercise 23 — Monitoring

Which view shows apply/worker state on the subscriber?

**Answer:** `pg_stat_subscription`.

### Exercise 24 — Origin progress

Which view tracks remote/local LSNs per replication origin?

**Answer:** `pg_replication_origin_status`.

### Exercise 25 — Error counters

Which view provides `apply_error_count` on supported versions?

**Answer:** `pg_stat_subscription_stats`.

### Exercise 26 — Skip transaction

Why is skipping a transaction dangerous?

**Answer:** The subscriber drops all changes in that transaction, potentially breaking invariants and foreign-key/business state.

### Exercise 27 — Field-level merge

When can individual fields be merged separately?

**Hint:** When fields have independent semantics and the domain permits merging.

### Exercise 28 — Last-write-wins

What are the risks of timestamp-based winners?

**Answer:** Clock skew and non-global commit ordering.

### Exercise 29 — Event sourcing

What type of conflict can append-only events reduce?

**Hint:** Overwriting the same row; though unique event IDs, idempotency, and ordering are still required.

### Exercise 30 — Multi-region partition

Does a network partition automatically elect a writer node?

**Answer:** No.

### Exercise 31 — Fencing

How do fencing/leases help?

**Hint:** Enforce that only the current owner is permitted to write within an ownership scope.

### Exercise 32 — Synchronous commit

Does logical replication synchronize commits between two nodes by default?

**Answer:** No; subscribers apply asynchronously.

### Exercise 33 — Read-your-writes

What should a client do after writing on A and reading on B?

**Hint:** Route to A or wait until B applies up to the required transaction point.

### Exercise 34 — Schema rollout

What risk does expand-and-contract reduce?

**Answer:** A publisher emitting new schema/data before the subscriber is compatible.

### Exercise 35 — Large objects

Does native logical replication replicate large objects like table rows?

**Answer:** No.

### Exercise 36 — Failover slot

Does publisher failover always preserve logical slots?

**Answer:** No; it depends on PostgreSQL version, failover-slot configuration, and provider.

### Exercise 37 — Resync

When a slot is lost and WAL is gone, what may be needed?

**Answer:** Rebaselining/resynchronizing the subscriber from a consistent snapshot.

### Exercise 38 — Conflict ownership

Who decides the winner of a row conflict?

**Answer:** The business/data owner per domain rules, supported by DBAs/application owners.

### Exercise 39 — Monitoring

Why must both A→B and B→A be monitored?

**Answer:** Each subscription, slot, and apply worker can fail or lag independently.

### Exercise 40 — Synthesis design

Two regions must accept local orders, each tenant has a home region, loops must be avoided, and read copies must stay on both sides. Propose a design.

**Hint:** Per-tenant ownership enforced at app/DB layers; publication row filters per owner; bidirectional subscriptions with `origin=none` on PostgreSQL 16+; UUID/global key strategy; synchronized schema migrations; controlled initial baseline/LSN; monitoring slots, apply errors, and freshness; conflict runbook; failover/fencing and resync drills. If the same tenant must write concurrently in both regions, add domain conflict resolution or designate a single write authority.

## 48. Design checklist

### 48.1. Topology and version

- [ ] PostgreSQL major versions confirmed?
- [ ] Origin filtering supported and enabled properly on each subscription?
- [ ] Publisher/subscriber directions documented?
- [ ] Topology free of unintended forwarding loops?
- [ ] Failure domains and network paths defined?

### 48.2. Data ownership and keys

- [ ] Writer owner defined per table/tenant/keyspace?
- [ ] Primary keys collision-free?
- [ ] Business unique keys governed by allocation/ownership policy?
- [ ] Sequences managed independently?
- [ ] Concurrent update/merge rules approved?
- [ ] Foreign-key ordering/dependencies reviewed?

### 48.3. Schema and publications

- [ ] Schema versions compatible on both sides?
- [ ] Replica identity suitable for UPDATE/DELETE?
- [ ] Publication table/operation scope minimal?
- [ ] Row filters/column lists verified?
- [ ] `TRUNCATE` published only intentionally?
- [ ] Separate procedures for DDL/roles/extensions/large objects?

### 48.4. Initial sync and recovery

- [ ] Baseline snapshot/LSN clear?
- [ ] `copy_data` appropriate for subscriber state?
- [ ] Bidirectional initial sync avoids duplicate rows?
- [ ] Logical slots have owners and retention alerts?
- [ ] Runbook ready for resync if slot/WAL is lost?
- [ ] Publisher failover behavior tested?

### 48.5. Monitoring and operations

- [ ] `pg_stat_subscription` monitored?
- [ ] Apply/sync error counters and logs alerted?
- [ ] `pg_replication_origin_status` tracked?
- [ ] Freshness SLOs defined for both directions?
- [ ] Conflict runbook and business approver ready?
- [ ] Security/TLS/secret rotation/auditing configured?
- [ ] Network partition/fencing/resync drills rehearsed?

## 49. Quick reference table

| Concept | Meaning |
|---|---|
| Logical replication | Transmitting row changes via publication/subscription |
| Publisher | Database publishing changes |
| Publication | Scope of tables/operations/rows/columns transmitted |
| Subscriber | Database receiving and applying changes |
| Subscription | Connection, slot, sync, and apply configuration |
| Bidirectional replication | Both nodes publish and subscribe |
| Replication loop | Received change gets forwarded back to source |
| Replication origin | Origin metadata of replicated transactions |
| `origin = none` | Receive only changes with local origin on PostgreSQL 16+ |
| Apply worker | Process applying changes on subscriber |
| Conflict | Two states/operations incompatible with constraints |
| Replica identity | Key used to locate rows for UPDATE/DELETE |
| `REPLICA IDENTITY FULL` | Uses the entire row as identity |
| Row filter | Limits rows sent by a publication |
| `copy_data` | Controls initial table data copy |
| Logical slot | Retains WAL for logical decoding/subscription |
| Schema drift | Node schemas no longer compatible |
| Selective merge | Merging specific data per business rules |
| Skip transaction | Bypassing a failing transaction, risking data loss |
| Resync | Re-establishing baseline and replication stream |
| Fencing | Blocking a former owner from continuing writes |
| Eventual consistency | Nodes converge after streams catch up |
| Read-your-writes | Ensuring clients read their own writes |
| Expand-and-contract | Multi-step backward-compatible schema migration |
| Conflict resolution | Rules selecting/merging state on concurrent writes |

## 50. Conclusion

**Bidirectional replication is not merely creating two reciprocal subscriptions.** It requires controlling change origins, data ownership, global keys, schemas, transaction ordering, and conflict handling workflows. PostgreSQL 16+ provides origin filtering with `origin=none` to suppress replication loops: changes received from a peer are not forwarded back as local-origin transactions. This solves part of the forwarding problem, but does not merge concurrent writes automatically.

To minimize conflicts, design single-writer ownership per table/tenant/keyspace, use UUIDs or disjoint key allocation, govern business unique keys, and run synchronized schema migrations. Logical replication does not automatically synchronize DDL, sequence states, roles, large objects, or extension binaries; bidirectional initial sync requires controlled baselines/LSNs. When an apply worker stops, inspect transactions and rows on both sides, decide based on business ownership, and skip only when omitted data is fully understood with a reconciliation plan.

Bidirectional logical replication fits when two nodes exchange datasets with clear ownership and low conflict rates. If all nodes must freely write the same rows during network partitions, adopt a conflict-resolution model or multi-master platform built for those semantics. Monitor every direction, slot, apply error, origin, and business freshness; rehearse failover/resync and maintain independent backups/PITR.

Operational rule: **prevent loops through origin-aware topology, prevent conflicts through ownership/key design, resolve conflicts via domain rules, and prove convergence through monitoring and reconciliation drills.**
