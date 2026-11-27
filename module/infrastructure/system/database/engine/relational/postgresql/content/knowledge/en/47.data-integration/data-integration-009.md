# CDC, Data Events, and Consumer Processing Guarantees in PostgreSQL

When a transaction modifies data in PostgreSQL, downstream systems often need to learn about that change to update search indexes, caches, data warehouses, billing systems, reports, or domain services. **Change Data Capture (CDC)** propagates committed changes to receiving systems. **Event-driven integration** delivers business-meaningful events so other services can react to them.

Reading changes out of PostgreSQL is only half the problem. The receiving system must also behave properly when messages are redelivered, consumers crash, networks time out, events arrive out of order, schemas evolve, or a single source transaction produces multiple events. A solid design explicitly defines event identity, ordering, delivery semantics, checkpoints, retries, deduplication, and data reconciliation.

This lesson focuses on two integration layers:

- **Data-level CDC:** capturing row-level changes from PostgreSQL WAL/logical decoding and turning them into change records.
- **Business events:** emitting events describing what happened in the business domain, typically via a transactional outbox so the event and data mutation commit together.

The receiving side must be engineered to handle repeated deliveries of an event without duplicating its effect. In the standard pattern, the consumer records the event ID and applies the business effect within a single transaction, committing its checkpoint/acknowledgment only after that transaction commits. This is the practical foundation for safely handling at-least-once delivery.

~~~mermaid
flowchart LR
    A["PostgreSQL transaction"] --> B["WAL"]
    B --> C["Logical decoding / slot"]
    C --> D["CDC connector"]
    D --> E["Event broker"]
    E --> F["Consumer"]
    F --> G["Inbox / dedup"]
    G --> H["Business effect"]
    H --> I["Commit"]
    I --> J["Checkpoint / ACK"]
~~~

This lesson belongs to the **Data Integration** chapter, **Database Engine Relational PostgreSQL** module.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Distinguish row-level CDC from domain/business events.
2. Explain the roles of WAL, logical decoding, output plugins, replication slots, and publications.
3. Configure PostgreSQL for logical decoding according to its version.
4. Create publications and understand the limitations of logical replication.
5. Monitor slots, WAL retention, LSNs, and replication lag.
6. Design an event envelope with ID, source, transaction metadata, and schema version.
7. Choose at-most-once, at-least-once, or appropriate effectively-once mechanisms.
8. Design an inbox/idempotency key to prevent duplicate processing.
9. Use a transactional outbox to bind business events to the source transaction.
10. Handle ordering, partitioning, duplicates, retries, and dead-letter queues.
11. Commit business effects and consumer checkpoints in the right order.
12. Bootstrap a snapshot and resume streaming without introducing data gaps.
13. Reconcile source and sink after incidents.
14. Manage schema evolution, deletes, tombstones, and event versioning.
15. Monitor lag, throughput, retries, poison events, and WAL growth.
16. Protect credentials, PII, and replication privileges.
17. Build runbooks for CDC outages, replays, and consumer recovery.

## 2. How Do CDC and Business Events Differ?

CDC and business events may originate from the same PostgreSQL transaction, yet they represent two distinct perspectives.

**Row-level CDC** describes data that changed in a table. For example, a row in public.orders was INSERTed, UPDATEd, or DELETEd. The event typically includes table name, operation, before/after values, primary key, source position, and transaction metadata depending on the connector.

**Business events** describe what happened in the domain. Examples:

- OrderPlaced.
- PaymentAuthorized.
- ShipmentDispatched.
- CustomerEmailChanged.
- InventoryReserved.

A business event may span multiple tables or internal operations and is emitted only when a business condition is satisfied.

| Criterion | Row-level CDC | Business Event |
| --- | --- | --- |
| Meaning | A row/table changed | A business occurrence took place |
| Source | WAL/logical decoding or audit/change log | Application transaction/domain logic |
| Payload | Table, operation, before/after | Event type and business facts |
| Coupling | Coupled to database schema | Coupled to business contract |
| Consumer | Typically must understand source schema | Can be independent of internal schema |
| Use cases | Replication, cache, warehouse, search index | Workflows, integration, notifications |
| Schema change | Can impact consumers directly | Managed through event contracts |

CDC fits when the receiving system mirrors data or builds a read model. Business events fit when communicating stable domain semantics over time.

Do not stream raw row changes externally and force consumers to reverse-engineer business intent if the application can emit cleaner domain events.

## 3. General CDC Flow

A typical CDC pipeline includes:

1. PostgreSQL writes transactions to WAL.
2. Logical decoding reads WAL and converts changes into logical records.
3. The replication slot tracks progress so the consumer can resume.
4. The output plugin formats logical changes.
5. The connector reads changes and emits messages.
6. The broker stores messages by partition/offset.
7. The consumer reads, validates, and applies effects.
8. The consumer commits its checkpoint/offset after successful processing.
9. Monitoring tracks lag, retries, slot retention, and sink health.

~~~mermaid
flowchart TD
    A["Application COMMIT"] --> B["PostgreSQL WAL"]
    B --> C["Logical decoding"]
    C --> D["Replication slot"]
    D --> E["Connector / output plugin"]
    E --> F["Broker topic"]
    F --> G["Consumer group"]
    G --> H{"Valid event?"}
    H -->|"Yes"| I["Deduplicate + apply"]
    H -->|"Transient error"| J["Retry"]
    H -->|"Poison event"| K["DLQ / quarantine"]
    I --> L["Commit sink transaction"]
    L --> M["Commit offset"]
    J --> G
~~~

Logical decoding emits committed transaction changes according to the output plugin's semantics. Consumers must still handle duplicates, retries, and sink failures because the connector or broker can redeliver messages whenever a checkpoint was not recorded.

## 4. WAL Is the Foundation of Logical Decoding

WAL (Write-Ahead Log) is PostgreSQL's write-ahead journal. Data modifications are written to WAL before corresponding pages are flushed to data files, enabling crash recovery and replication.

Logical decoding reads WAL and interprets changes into logical operations such as INSERT/UPDATE/DELETE rather than shipping raw physical page diffs.

Related concepts:

- **WAL record:** a record describing physical/logical operations needed for recovery.
- **LSN:** Log Sequence Number, a position in WAL.
- **Commit record:** marks transaction commit.
- **Logical decoding:** decodes WAL into logical change streams.
- **Output plugin:** formats changes into a protocol or wire format.
- **Replication slot:** persists consumer progress and retains needed WAL.
- **Publication:** defines tables and operations published by native logical replication.

LSN is a technical position, not a business event ID. A single transaction can produce multiple WAL records and multiple row changes; connectors may attach the same transaction metadata to multiple emitted events.

## 5. Preparing PostgreSQL for Logical Decoding

To use logical decoding, the server must be configured appropriately. The core setting is wal_level.

~~~sql
SHOW wal_level;
SHOW max_replication_slots;
SHOW max_wal_senders;
SHOW max_slot_wal_keep_size;
~~~

Typical requirements:

- wal_level = logical.
- max_replication_slots sized for expected slots.
- max_wal_senders sized for logical/physical replication connections.
- Adequate disk capacity and WAL retention policy.
- Network/firewall access for the connector.
- A replication role and snapshot read privileges if the connector takes initial snapshots.

wal_level, max_replication_slots, and max_wal_senders require a server restart depending on PostgreSQL version. Check pg_settings.context and your version's documentation before changing settings.

Example checking setting and context:

~~~sql
SELECT
    name,
    setting,
    unit,
    context,
    source,
    pending_restart
FROM pg_settings
WHERE name IN (
    'wal_level',
    'max_replication_slots',
    'max_wal_senders',
    'max_slot_wal_keep_size'
)
ORDER BY name;
~~~

Do not set max_replication_slots or max_wal_senders arbitrarily high. Every slot/connection consumes resources, and abandoned slots can hold WAL indefinitely.

## 6. Creating a Replication Role

Create a dedicated role for the connector with only required privileges.

~~~sql
CREATE ROLE cdc_reader
    WITH LOGIN REPLICATION
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE;
~~~

The replication role must be allowed to connect to the database and configured in pg_hba.conf. If the connector takes an initial snapshot, the role also needs SELECT on snapshotted tables and metadata read access.

Example:

~~~sql
GRANT CONNECT ON DATABASE sales TO cdc_reader;
GRANT USAGE ON SCHEMA public TO cdc_reader;
GRANT SELECT ON TABLE public.orders TO cdc_reader;
~~~

For multiple tables, grant privileges explicitly per scope. You can use default privileges for future objects if policy allows, ensuring they target the exact object-owning role.

Never grant SUPERUSER just to make a connector work. Some connectors/versions have specific privilege requirements; consult official connector and PostgreSQL documentation to grant exact role attributes and permissions.

Credentials must live in a secret manager, rotate per policy, and never appear in migration files, logs, or event payloads.

## 7. Publications in PostgreSQL

A publication is the set of tables and operations published by native logical replication. CDC connectors using pgoutput can rely on publications to define scope, depending on connector configuration.

Example single-table publication:

~~~sql
CREATE PUBLICATION orders_cdc_pub
FOR TABLE public.orders
WITH (publish = 'insert, update, delete');
~~~

Or a multi-table publication:

~~~sql
CREATE PUBLICATION app_cdc_pub
FOR TABLE public.orders, public.order_items, public.customers;
~~~

Publications can filter INSERT, UPDATE, DELETE, and TRUNCATE as supported by version. Inspect publications:

~~~sql
SELECT
    pubname,
    puballtables,
    pubinsert,
    pubupdate,
    pubdelete,
    pubtruncate
FROM pg_publication
ORDER BY pubname;
~~~

View tables in publications:

~~~sql
SELECT
    p.pubname,
    n.nspname AS schema_name,
    c.relname AS table_name
FROM pg_publication_tables AS p
JOIN pg_namespace AS n
    ON n.nspname = p.schemaname
JOIN pg_class AS c
    ON c.relname = p.tablename
   AND c.relnamespace = n.oid
ORDER BY p.pubname, p.schemaname, p.tablename;
~~~

A publication is not a complete event schema. It selects what data is published; the output plugin/connector defines the envelope and message format.

### Row Filters and Column Lists

Recent PostgreSQL versions support publication row filters and column lists for certain use cases. Syntax and limitations depend on major version.

Row filters can reduce transmitted data, though UPDATE/DELETE filtering has specific semantics and replica identity remains required. Column lists reduce published fields, but can leave consumers missing fields needed to reconstruct state or run logic.

Never treat publication filters as the sole security boundary. Combine role privileges, network rules, connector policies, and data classification.

## 8. Replica Identity: How PostgreSQL Identifies Updated/Deleted Rows

To describe UPDATE/DELETE in logical replication, PostgreSQL needs to identify the old row. Replica identity controls what identifying information is logged to WAL for logical decoding.

Check settings:

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relreplident AS replica_identity
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, c.relname;
~~~

Common values:

- d: DEFAULT, typically uses the primary key if one exists.
- n: NOTHING, no replica identity.
- f: FULL, logs the entire old row image for updates/deletes.
- i: USING INDEX, uses a suitable unique index.

If a table lacks a primary key or suitable replica identity, UPDATE/DELETE changes may not publish as expected or replication may error.

### Using FULL

~~~sql
ALTER TABLE public.audit_events REPLICA IDENTITY FULL;
~~~

FULL increases WAL volume and exposes more old values in CDC payloads. Use it only when necessary after evaluating storage, network, and privacy impacts.

### Using a Specific Index

~~~sql
ALTER TABLE public.orders
REPLICA IDENTITY USING INDEX orders_replica_identity_key;
~~~

The index must satisfy PostgreSQL's requirements for being unique, non-partial, and over non-null columns. Check documentation for your version before using it.

## 9. Replication Slots and WAL Retention

A replication slot tracks consumer progress and prevents PostgreSQL from removing WAL still needed by an unread consumer. It is essential for avoiding lost change records, yet an abandoned slot can cause unbounded WAL growth.

Inspect slots:

~~~sql
SELECT
    slot_name,
    plugin,
    slot_type,
    database,
    active,
    active_pid,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Some PostgreSQL versions expose additional columns such as wal_status, safe_wal_size, invalidation_reason, or failover metadata. Verify the actual view schema before automating queries.

Key fields:

- slot_name: name of the slot.
- plugin: output plugin for logical slots.
- slot_type: physical or logical.
- database: database associated with a logical slot.
- active: whether a consumer is currently attached.
- restart_lsn: earliest WAL position still required.
- confirmed_flush_lsn: position confirmed processed/received by the consumer per protocol.

restart_lsn and confirmed_flush_lsn differ. The gap between them reflects WAL still retained for slot/decoding state; it is not simply the count of messages queued in the broker.

### Estimating WAL Retention

On the primary, check the distance from current WAL LSN to restart_lsn:

~~~sql
SELECT
    slot_name,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    CASE
        WHEN restart_lsn IS NULL THEN NULL
        ELSE pg_size_pretty(
            pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
        )
    END AS retained_wal_distance
FROM pg_replication_slots
WHERE slot_type = 'logical'
ORDER BY slot_name;
~~~

This is an LSN distance, not an exact measurement of physical bytes on the filesystem due to segment boundaries, shared retention, and archival behavior. Cross-check filesystem and monitoring metrics.

### Bounding WAL Retained by Slots

max_slot_wal_keep_size can cap WAL retained per slot in supported versions. If exceeded, the slot may become invalidated because required WAL was recycled; the consumer must then follow a recovery plan, potentially recreating the slot and bootstrapping/reconciling.

Do not set the limit so low that normal consumers regularly lose their slots. Do not leave it unlimited without alerting and capacity planning.

## 10. Logical Decoding and Output Plugins

Logical decoding transforms WAL into changes via an output plugin.

Common built-in plugin:

- pgoutput: output plugin used by native logical replication and many CDC connectors.
- External plugins can output JSON, text, or binary formats depending on package and version.

Not every output plugin is preinstalled. Connectors may manage slots and plugins themselves. Do not create a slot manually if the connector is configured to create it; both sides may contend for it or create duplicate slots.

### Illustrative Logical Slot Creation

~~~sql
SELECT *
FROM pg_create_logical_replication_slot(
    'orders_cdc_slot',
    'pgoutput'
);
~~~

This creates a slot in the current database. It does not create a broker, connector, or consumer. With pgoutput, consumers use the logical replication protocol and specify publications/options per protocol.

In production, connectors usually manage slot lifecycles so they can coordinate snapshots, offsets, and restarts. If slots are created manually, maintain a runbook governing ownership, drop/recreate, and recovery.

### Listing Slots

~~~sql
SELECT
    slot_name,
    plugin,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_type = 'logical';
~~~

Never drop a slot actively used by a connector. Dropping a slot destroys decoding progress and allows WAL recycling, forcing the consumer to re-bootstrap/recover.

## 11. Native Logical Replication vs. CDC Connectors

Two common approaches:

**Native logical replication:** A PostgreSQL publisher streams changes via a publication; a PostgreSQL subscriber applies them to matching tables. This is database-to-database replication.

**CDC connector:** A connector uses the logical replication protocol/slot to turn changes into event messages for a broker or external sink. A common stack is Debezium with Kafka Connect and Kafka, though other connectors share the same PostgreSQL foundation.

| Criterion | Native Logical Replication | CDC Connector |
| --- | --- | --- |
| Sink | PostgreSQL subscriber | Broker, warehouse, search, cache, service |
| Payload | Logical row changes | Connector-defined event envelope |
| Apply | PostgreSQL apply worker | Consumer/application |
| Offset | Subscription/slot state | Connector offsets and slot progress |
| Schema evolution | Schema managed separately | Connector schema/history + consumer contract |
| Transformation | More limited | Can transform/filter/route |
| Delivery handling | PostgreSQL-managed apply | Must design sink idempotency/retries |
| Business semantics | Row changes | Can map into domain events |

Native logical replication still requires handling sequences, DDL, large objects, and non-row objects. CDC connectors add formatting and metadata but do not automatically guarantee business correctness.

## 12. Logical Replication Does Not Automatically Replicate Everything

Several items are not automatically propagated via logical row replication the way users often assume:

- DDL/schema changes.
- Sequence states.
- Roles and grants.
- Large objects in common configurations.
- Server configuration and extension packages.
- External side effects.
- Tables omitted from the publication.

Schemas must be deployed consistently on the subscriber/consumer before events referencing new schemas arrive. Sequence states must be synced explicitly during cutovers. For business events, applications must explicitly define event contracts.

Check documentation for your specific PostgreSQL version and connector, as capabilities expand over releases.

## 13. Designing the Event Envelope

An event should use a stable envelope separating metadata from business payload.

JSON example:

~~~json
{
  "id": "0192f2d0-7e51-7b6a-9d31-1c5d6b7e8f90",
  "type": "com.example.orders.order-status-changed",
  "version": 2,
  "source": "postgres://sales/public.orders",
  "subject": "orders/ORD-1042",
  "time": "2026-11-14T08:30:00Z",
  "transaction": {
    "id": "tx-88421",
    "commit_lsn": "0/16B6C50",
    "sequence": 3
  },
  "correlation_id": "req-5f42",
  "causation_id": "cmd-9a18",
  "data": {
    "order_id": "ORD-1042",
    "old_status": "paid",
    "new_status": "shipped"
  }
}
~~~

Key fields:

- id: unique identifier, stable across retries.
- type: namespaced event type.
- version: contract version.
- source: originating system/table/aggregate.
- subject: related entity/aggregate.
- time: business or commit timestamp, with clearly defined semantics.
- transaction: transaction/LSN/sequence metadata if available.
- correlation_id: links a workflow or request.
- causation_id: event/command that triggered this event.
- data: payload.

Do not use LSN alone as the unique event ID if a transaction modifies multiple rows under one LSN or the connector emits multiple records per commit. Use a dedicated stable ID or a well-defined composite identity.

## 14. CDC Event Envelopes and Before/After Images

A CDC event typically specifies an operation:

- c: create/insert.
- u: update.
- d: delete.
- r: snapshot/read event.

Exact codes and shapes depend on the connector. In Debezium, envelopes may include before, after, source metadata, op, timestamp, and transaction metadata.

Conceptual example:

~~~json
{
  "before": {
    "id": 42,
    "status": "pending"
  },
  "after": {
    "id": 42,
    "status": "paid"
  },
  "source": {
    "schema": "public",
    "table": "orders",
    "lsn": "0/16B6C50"
  },
  "op": "u"
}
~~~

Do not treat this as a universal JSON schema for every connector. Consult the actual schema of your connector/version and converter/serializer settings.

### Deletes and Tombstones

A delete event may carry the old key/before image or just the key depending on replica identity and connector settings. Some brokers/connectors emit a tombstone record (key with null value) to support log compaction. Consumers must distinguish business delete events from broker-level tombstones.

If downstream consumers require old field values, configure replica identity accordingly and verify connector payloads. REPLICA IDENTITY FULL increases WAL size and data exposure; weigh carefully.

## 15. Business Events and the Transactional Outbox

A classic bug occurs when an application commits the database and then publishes a message afterward:

1. UPDATE orders SET status = 'paid'.
2. COMMIT.
3. Publish OrderPaid to the broker.

If the process crashes between steps 2 and 3, the database updated but the event was never sent. If published before commit, the transaction might roll back after the event already went out.

The transactional outbox closes this gap by writing business data and the event record inside the same database transaction.

~~~mermaid
flowchart TD
    A["Application command"] --> B["BEGIN"]
    B --> C["Update business tables"]
    C --> D["Insert outbox event"]
    D --> E["COMMIT"]
    E --> F["CDC / outbox relay"]
    F --> G["Broker"]
    G --> H["Consumer"]
~~~

Example outbox table:

~~~sql
CREATE TABLE integration_outbox (
    event_id uuid PRIMARY KEY,
    aggregate_type text NOT NULL,
    aggregate_id text NOT NULL,
    aggregate_version bigint,
    event_type text NOT NULL,
    schema_version integer NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    payload jsonb NOT NULL
);
~~~

Within the same transaction:

~~~sql
BEGIN;

UPDATE public.orders
SET status = 'paid',
    updated_at = now()
WHERE order_id = 'ORD-1042';

INSERT INTO integration_outbox (
    event_id,
    aggregate_type,
    aggregate_id,
    aggregate_version,
    event_type,
    schema_version,
    payload
)
VALUES (
    gen_random_uuid(),
    'Order',
    'ORD-1042',
    7,
    'OrderPaid',
    1,
    '{"order_id":"ORD-1042","status":"paid"}'::jsonb
);

COMMIT;
~~~

If the transaction rolls back, both the business update and outbox row roll back. If it commits, the event is durably persisted for the relay/CDC to deliver.

Ensure the UPDATE actually affected the intended order before inserting the event; the snippet illustrates the pattern, while real applications must check affected row counts and construct events from confirmed state.

## 16. Outbox Relay: Polling vs. CDC

Two common patterns:

### Polling Relay

A worker periodically reads unsent rows, publishes them, and marks them sent.

Advantages:
- Easy to understand, no logical decoding required.
- Batching and retries can be controlled in application code.
- Easy to inspect individual event status.

Challenges:
- Needs safe locking/claiming across multiple workers.
- Publishing successfully before marking sent can cause duplicates.
- Polling adds query load and requires cleanup.
- Cannot guarantee an atomic commit between PostgreSQL and the broker without a distributed transaction.

### CDC Relay

A connector reads the outbox table via logical decoding and emits events.

Advantages:
- Leverages WAL and replication slots.
- Reduces polling query load.
- Preserves commit order and transaction metadata.
- Fits neatly into an existing CDC pipeline.

Challenges:
- Must operate slots and WAL retention.
- Outbox schema must stay stable.
- Event cleanup must align with retention and recovery policies.
- Connector restarts can replay records.
- Must handle outbox snapshots and consumer deduplication.

Whether using polling or CDC, consumers still need idempotency. No standard relay mechanism eliminates all possibility of duplicates across the PostgreSQL-to-broker boundary.

## 17. At-Most-Once, At-Least-Once, and Exactly-Once

### At-Most-Once

The consumer checkpoints/acks before applying the effect. If the process crashes after checkpointing and before the effect commits, the event can be lost.

Suitable when occasional missed updates are tolerable or data can be easily regenerated.

### At-Least-Once

The consumer checkpoints only after the effect commits. If it crashes after committing and before checkpointing, the event is redelivered and may be processed twice.

This is the standard choice because received events are not dropped, provided the source/connector retains data and retries cleanly.

### Exactly-Once

Exactly-once means a logical event produces exactly one observable effect at the sink. Achieving it requires atomic coordination between the event offset/checkpoint and the business effect, or an idempotent sink with durable deduplication.

Enabling producer idempotence or broker transactions alone does not guarantee end-to-end exactly-once if the consumer writes to an external database or API.

In most systems, the practical target is **at-least-once delivery + idempotent processing**. Observable business outcomes are then equivalent to once-only execution within the designed idempotency-key and transaction boundary.

## 18. Consumer Inbox and Deduplication

An inbox is a table recording processed event IDs. Event IDs must remain stable across retries and unique within the defined scope.

Example:

~~~sql
CREATE TABLE consumer_inbox (
    event_id uuid PRIMARY KEY,
    event_type text NOT NULL,
    payload_hash text,
    received_at timestamptz NOT NULL DEFAULT now()
);
~~~

Consumer processes inside a single transaction:

~~~sql
BEGIN;

INSERT INTO consumer_inbox (
    event_id,
    event_type,
    payload_hash
)
VALUES (
    '0192f2d0-7e51-7b6a-9d31-1c5d6b7e8f90',
    'OrderPaid',
    'sha256:example'
)
ON CONFLICT (event_id) DO NOTHING
RETURNING event_id;
~~~

The application inspects the RETURNING result:

- Row returned: new event; apply the business effect in the same transaction.
- No row returned: event already processed; skip the effect and commit/no-op.
- Same event ID with different payload hash: integrity or producer bug; quarantine and alert instead of silently ignoring.

After applying the effect:

~~~sql
UPDATE customer_order_summary
SET paid_orders = paid_orders + 1
WHERE customer_id = 42;

COMMIT;
~~~

This is an illustrative example. The consumer must execute the inbox insert and business update in the same database transaction. If the effect calls an external API, the inbox transaction cannot atomically wrap that API call; use an outbox/command workflow or API-side idempotency keys.

### Why Must the Inbox Commit with the Effect?

If the inbox commits before the effect, a crash can mark an event processed even though the effect never occurred. If the effect commits before the inbox, a crash can cause the effect to run again. Sharing one transaction removes that gap when both write to the same transactional database.

## 19. Idempotency Keys for Business Effects

Event IDs are one deduplication mechanism, though not always sufficient. A single business command might be emitted under multiple event IDs due to producer bugs or retries. A unique business key is then also required.

Payment example:

~~~sql
CREATE TABLE payment_effects (
    payment_id text PRIMARY KEY,
    order_id text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);
~~~

The consumer inserts payment_id with ON CONFLICT DO NOTHING before applying the effect. This guarantees a payment ID is applied at most once transactionally.

Choose keys matching business invariants:

- payment_id for payment authorization/capture.
- order_id + transition_version for order state transitions.
- aggregate_id + aggregate_version for an aggregate's event stream.
- event_id for per-event deduplication.

Never use timestamps or freshly generated random keys per retry as idempotency keys.

## 20. Offsets/Checkpoints Must Commit After Sink Effects

Suppose a consumer reads a message from a broker and writes to a PostgreSQL sink:

1. Read event and offset.
2. Begin sink transaction.
3. Insert inbox/dedup record.
4. Apply business effect.
5. Commit sink transaction.
6. Commit broker offset/ack.

If the process crashes between steps 5 and 6, the broker redelivers the event; the inbox catches the duplicate and the consumer avoids repeating the effect.

If the offset commits at step 2 before the sink transaction commits, a crash can lose the event effect permanently.

### Batch Processing Caveats

When processing batches of messages:

- Track the highest contiguous completed offset, not merely any highest completed offset.
- Never commit an offset past an in-flight message.
- If processing concurrently, track completion per partition/sequence.
- You can commit inbox/effects in batch transactions, keeping transaction size and lock bounds in mind.
- Retrying one event must not skip an earlier event if ordering is required.

## 21. Event Ordering and Transaction Boundaries

WAL has a physical order, and logical decoding preserves transaction/commit order per protocol. However, consumer-observed order also depends on the connector, broker partitioning, parallelism, and retries.

### Ordering by Aggregate Key

If all events for the same order/customer/account publish to the same broker partition keyed by aggregate ID, a consumer can process them sequentially within that partition.

Example key:

~~~text
key = aggregate_type + ":" + aggregate_id
~~~

This preserves ordering within a partition, not global ordering across all aggregates.

### Aggregate Version

Attach a monotonically increasing version:

~~~json
{
  "aggregate_id": "ORD-1042",
  "aggregate_version": 8,
  "event_type": "OrderShipped"
}
~~~

Consumers can detect gaps or stale events:

- version = last + 1: process normally.
- version <= last: duplicate/stale, skip per policy.
- version > last + 1: missing event; buffer/retry/reconcile.

Do not assume every CDC row change carries an aggregate version. If business versioning is needed, generate it in the application/outbox.

### Multi-Row Transactions

A single PostgreSQL transaction can update multiple tables/rows. A connector may emit multiple separate messages. If consumers require source-transaction atomicity, use transaction metadata and buffering/staging until the transaction end marker arrives, or design aggregate-level business events that do not depend on stitching row changes back together.

Never scatter records from one transaction across multiple partitions and assume consumers will observe them simultaneously.

## 22. Retry Strategy

Retries fit transient failures:

- Network timeouts.
- Broker unavailability.
- Sink database failovers.
- Rate limits.
- Temporary dependency outages.
- Transient serialization service errors.

Use exponential backoff with jitter:

~~~text
delay = min(max_delay, base_delay * 2^attempt) + random_jitter
~~~

Requirements:

- Cap retry attempts or elapsed retry time.
- Separate retryable from non-retryable errors.
- Limit concurrency.
- Avoid tight infinite retry loops that amplify load.
- Preserve event ID and original payload.
- Record attempt counts and last error.
- Never checkpoint an unprocessed event if semantics forbid loss.

Permanent schema or validation errors do not resolve on retry. Route them to quarantine/DLQ to fix the consumer or contract and replay afterward.

## 23. Dead-Letter Queues and Poison Events

A poison event repeatedly fails due to malformed payloads, schema/logic mismatches, or edge-case data.

A DLQ/quarantine record should retain:

- Original event ID.
- Source topic/partition/offset or source LSN.
- Event type/schema version.
- Protected payload.
- First/last failure timestamps.
- Attempt count.
- Error category/message.
- Consumer version.
- Correlation/causation IDs.
- Replay status.

Never route an event to a DLQ and silently commit the offset if doing so drops a business obligation. Policies must define DLQ entries as pending items with alerts and clear ownership.

### Replay

Replaying requires:

1. Fixing the root cause.
2. Checking whether the event remains valid against current state.
3. Keeping the original event ID.
4. Running through the same idempotency/dedup mechanism.
5. Preserving ordering if sequence-dependent.
6. Recording the replay operator/change ID.
7. Reconciling the sink after replay.

Never replay an entire DLQ into production without evaluating duplicates, ordering, and event expiration.

## 24. Snapshot Bootstrapping and Avoiding Data Gaps

CDC often needs an initial snapshot so consumers have baseline state before streaming incremental changes.

The greatest risk is a gap between snapshot and stream:

- Snapshot starts.
- A row changes during copying.
- Connector begins streaming from an inconsistent position.
- Consumer misses or double-applies changes.

Proper connectors coordinate a consistent snapshot with the logical slot/WAL position. Never run an ad-hoc full-table SELECT and create a slot afterward without snapshot/LSN coordination.

### Bootstrap Strategy

- Choose the connector's snapshot mode.
- Record the snapshot watermark/LSN.
- Determine whether consumers start from snapshot or stream.
- Use upsert/idempotent sinks when snapshot records may overlap with stream events.
- Reconcile counts/checksums after bootstrapping.
- Expose downstream reads only once snapshot and stream have caught up.

### Incremental Snapshots

For large tables, incremental snapshots chunk data while WAL streaming continues. Connectors rely on watermarking/deduplication to handle rows modified mid-snapshot. Verify exact connector/version semantics without guessing.

## 25. Source-to-Sink Reconciliation

CDC pipelines can suffer outages, misconfigured filters, or consumer bugs. Reconciliation verifies that the sink accurately reflects the source.

Reconciliation checks:

- Row counts by partition/key range.
- Min/max primary keys.
- Max updated_at or source watermarks.
- Aggregate totals.
- Chunk hashes/checksums.
- Missing keys.
- Extra keys.
- Duplicate business keys.
- Aggregate versions/watermarks.
- Delete/tombstone coverage.

If the source is actively accepting writes, compare against a shared logical watermark or consistent snapshot. Comparing two different instants creates false mismatches.

### Aggregate Check Example

~~~sql
SELECT
    count(*) AS order_count,
    sum(total_amount) AS total_amount,
    max(updated_at) AS latest_update
FROM public.orders;
~~~

Run matching logic on the sink and record timestamps/watermarks. Matching aggregates alone do not prove every row matches; combine with chunk checks or key-level reconciliation for critical datasets.

## 26. Consumer Transactions When the Sink Is PostgreSQL

When a consumer writes to a PostgreSQL sink, the standard pattern is:

~~~sql
BEGIN;

INSERT INTO consumer_inbox (event_id, event_type)
VALUES ('0192f2d0-7e51-7b6a-9d31-1c5d6b7e8f90', 'OrderPaid')
ON CONFLICT (event_id) DO NOTHING
RETURNING event_id;

-- Only when INSERT returns a new row:
-- apply business changes within the same transaction.

COMMIT;
~~~

The application decides whether to apply effects based on RETURNING. If the event is a duplicate, the transaction finishes without reapplying effects.

Ensure:

- Inbox has a unique constraint.
- Business update and inbox reside in the same database.
- Errors before COMMIT roll back both.
- Consumer acks only after COMMIT.
- External calls are offloaded to a separate outbox/worker.
- Event payload validation runs before writing effects.

If the sink database and broker support specific transactional integration features, verify the connector/framework semantics. Do not assume two independent systems automatically form a distributed transaction.

## 27. Consumer Transactions When the Sink Is an External API

If a consumer calls a REST API, email provider, or payment gateway, a PostgreSQL transaction cannot roll back the external side effect.

Approach:

- Pass an idempotency key to the API when supported.
- Persist command state in the database.
- Use an outbox to dispatch retryable commands.
- Record responses/remote references.
- Reconcile on timeouts because the request may have succeeded even if the reply was lost.
- Never resend with a new key.
- Maintain a compensation workflow if side effects cannot be undone.

A timeout does not mean the API never processed the request. Query status by idempotency key or remote reference before retrying.

## 28. Schema Evolution for CDC and Event Consumers

Consumers may run older code while the source adds columns or evolves event contracts.

Principles:

- Add optional fields first.
- Consumers ignore unknown fields if the contract permits.
- Never make breaking changes to existing field types/meanings.
- Version event schemas explicitly.
- Enforce compatibility checks in CI.
- Plan sink schema migrations.
- Coordinate producer and consumer rollouts.
- Maintain backward/forward compatibility during rolling deployments.

### Adding Fields

Older consumers must tolerate newly added fields. Serializers and schema registries must enforce appropriate compatibility modes.

### Renaming Fields

Never rename directly while consumers still read the old field. Use a dual-field transition:

1. Producer adds the new field.
2. Consumers switch to reading the new field.
3. Monitor legacy consumers.
4. Producer removes the old field after the compatibility window.

### Removing Fields

Remove fields only after zero consumers read them and schema history/retention allows.

### Changing Types

Even type widening requires checking serializers and sink mappings. Semantic changes are riskier than type changes; introduce a new event type or version if the semantic contract changes.

## 29. Delete Events, Replica Identity, and Tombstones

DELETE handling requires explicit design:

- Key of the deleted row.
- Is a before image required?
- Do consumers need old values to compute compensations?
- Should the sink delete the record or flag it deleted?
- Does the broker use log compaction?
- Is the tombstone broker-level or domain-level?

If old row values are required, verify replica identity. DEFAULT typically logs the primary key; FULL logs the entire old row image and enlarges WAL.

At the sink, delete handling must be idempotent: deleting an already-deleted row should be a valid no-op. For downstream aggregates, delete events may need to decrement counters or reverse effects transactionally while preventing duplicate processing.

## 30. Truncate and Bulk Changes

TRUNCATE has very different semantics from row-by-row DELETEs. Publications must enable truncate publishing to emit it, and connectors must represent it appropriately.

Consumers must determine:

- Whether the entire table or a partition was truncated.
- Whether applying a sink truncate is safe.
- Whether caches/indexes must be rebuilt.
- Whether the event includes transaction metadata.
- Which consumers are authorized to execute destructive operations.

Do not expand a truncate event into millions of synthetic delete events unless the connector is explicitly designed for it. Conversely, never ignore truncates if the sink requires parity.

## 31. Ordering, Concurrency, and Partitioning

Brokers typically partition messages to scale throughput. Ordering is generally guaranteed only within a single partition, not across an entire topic.

Choosing a partition key:

- Aggregate ID for business events.
- Primary key for row-level CDC.
- Tenant ID if per-tenant ordering is needed.
- A composite key if transactions/aggregates require specific ordering rules.

If events for one aggregate scatter across partitions, consumers may observe them out of order. If multiple consumer threads process the same partition, serialize effects or enforce aggregate version checks.

Never raise partition counts arbitrarily when systems rely on key-to-partition ordering. Some brokers remap keys when partition counts change; plan a migration strategy first.

## 32. Backpressure and Consumer Lag

When consumers process slower than producers, lag grows. In PostgreSQL CDC, lag can build at several layers:

- Slot confirmed_flush_lsn falls behind.
- Connector queue grows.
- Broker topic lag grows.
- Consumer processing backlog grows.
- Sink write latency increases.
- DLQ/retry backlog grows.

Measure every layer; a single generic "lag" metric cannot pinpoint the bottleneck.

### Reducing Backpressure

- Increase consumer concurrency within sink capacity limits.
- Batch writes sensibly.
- Use bulk upserts where safe.
- Optimize sink indexes.
- Trim unnecessary payload fields/columns.
- Isolate workloads by topic/partition.
- Curb retry storms.
- Scale the sink before scaling consumers indefinitely.
- Tune connector queue/batch sizes carefully.

If the connector reads quickly while the sink lags, the slot may advance while the broker backlog grows. In that case, WAL retention and consumer lag are two separate issues.

## 33. Monitoring Replication Slots and Lag

Slot inventory:

~~~sql
SELECT
    slot_name,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
~~~

Replication sender state:

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication
ORDER BY application_name;
~~~

Not every logical connector appears as a row in pg_stat_replication at all times or under every connection mode. Check slot active status and connector metrics.

### Recommended Alerts

- Slot inactive longer than threshold.
- Restart LSN failing to advance.
- Retained WAL exceeding capacity budget.
- Slot nearing WAL loss under max_slot_wal_keep_size.
- Connector disconnected/restarting.
- Broker lag rising continuously.
- Consumer error/retry rate climbing.
- New events entering DLQ.
- Event-to-effect latency breaching SLA.
- Sudden spike in duplicate rate.
- Reconciliation mismatches.

## 34. Monitoring Native Logical Subscriptions

For native logical replication subscribers, check:

~~~sql
SELECT *
FROM pg_stat_subscription;
~~~

Inspect subscription configuration state:

~~~sql
SELECT
    subname,
    subenabled,
    subslotname,
    subpublications
FROM pg_subscription
ORDER BY subname;
~~~

Also inspect worker processes, logs, and publisher-side replication slots. View columns vary across versions; inspect with SELECT * first and tailor queries to your schema.

A native subscriber may run initial table copy, apply workers, and table synchronization workers. Never equate subscription enabled with all tables being fully synced.

## 35. Event Schema Registry and Contract Ownership

In multi-producer/multi-consumer environments, event schemas should be governed like public APIs.

A contract should specify:

- Event type and version.
- Required/optional fields.
- Field types/formats.
- Nullability.
- Semantics and units.
- Ordering/partition key.
- Delivery guarantees.
- Retention/replay policy.
- PII classification.
- Owner/contact.
- Compatibility rules.

Options include JSON Schema, Avro, Protobuf, or a schema registry. Choose formats based on your ecosystem and compatibility requirements.

Never treat ad-hoc JSON snippets in a wiki as a contract. Contracts must be versioned and validated automatically in CI.

## 36. CDC Filtering and Data Minimization

Capture only required tables and columns. Streaming an entire database can:

- Inflate WAL/connector/broker traffic.
- Complicate consumers.
- Increase PII exposure risk.
- Couple consumers to internal schemas.
- Drive up storage and replay costs.

Use publication table scoping, row filters/column lists where supported, connector transforms, and broker ACLs. Keep in mind that transforms applied after the connector reads WAL do not reduce WAL generation at the source.

If events require sensitive data, consider tokenization or masking at the source or prior to the broker. Never rely on consumers to strip PII after data has already fanned out across topics.

## 37. Security for CDC Pipelines

Secure every hop:

**PostgreSQL:**
- Dedicated replication role.
- HBA rules restricting source addresses.
- TLS with certificate validation.
- SELECT restricted to tables needing snapshots.
- Minimal publication scope.
- Slot inventory and cleanup policy.

**Connector:**
- Secret manager integration.
- TLS to source and broker.
- Never log passwords or sensitive payloads.
- Restrict plugins and transforms.
- Access-controlled offsets and config.

**Broker:**
- Per-topic/group ACLs.
- Encryption in transit and at rest.
- Retention and deletion policies.
- Access auditing.
- PII classification.

**Consumer:**
- Least privilege on the sink.
- Payload and schema validation.
- Never trust unverified source metadata.
- Idempotency and replay controls.
- Audit logging of event processing.

A CDC role often accesses broader data than an ordinary application role. Subject it to dedicated security reviews.

## 38. WAL Retention and Lost Slot Incidents

An inactive slot still pins WAL. If a connector stops for hours or days, pg_wal can grow until disks fill up.

When a slot is retaining WAL:

1. Identify the slot owner/connector.
2. Check active/inactive status and last progress.
3. Measure retained WAL and free disk space.
4. Inspect connector offsets and broker backlog.
5. Restart the connector if it can still resume.
6. Never drop the slot just to free disk space before understanding the consumer recovery path.
7. If the slot is invalidated/lost WAL, create a new slot per connector procedure and bootstrap/reconcile.
8. Document the event gap and verify sink parity before closing the incident.

Dropping a slot may forfeit the ability to read recycled WAL. There is no way to reconstruct CDC records from purged WAL; rely on snapshotting/reconciliation or archive restoration depending on the scenario.

## 39. Replay and Rebuilding Consumers

A consumer may need replay when:

- A consumer bug corrupted sink state.
- Schema mappings were fixed.
- The sink was restored to an earlier point in time.
- DLQ items need reprocessing.
- Consumer offsets were lost or untrusted.

Before replaying:

- Select the starting offset/LSN.
- Check sink state and idempotency retention.
- Verify event ordering.
- Assess external side effects.
- Take a snapshot/backup of the sink.
- Estimate replay throughput and sink capacity.
- Record replay ID and owner.

If replaying from the start while the inbox table remains intact, duplicate events are skipped; however, if the sink was restored to a point prior to those inbox entries, deduplication state must be restored consistently too. Inbox and business state should be backed up and restored within the same transaction boundary.

## 40. Event Retention and Inbox Cleanup

The inbox table grows with processed events. Partition it by received_at or purge old rows under a retention policy.

Before purging, evaluate:

- Event replay window.
- Broker retention.
- Source slot/re-bootstrap strategy.
- Business idempotency horizon.
- External API idempotency retention.
- Legal/audit retention.
- Event ID uniqueness lifetime.

Purging an inbox record before an old event replays can re-trigger duplicate effects. Retain deduplication state for at least the replay horizon or rely on long-lived business uniqueness constraints.

Outbox rows also need cleanup. Delete them only after the connector/relay confirms progress past those rows and retention permits. With CDC, deleting outbox rows also generates WAL delete events; filter or route appropriately to avoid feedback loops.

## 41. Handling Multi-Event Transactions

A single source transaction may generate many row-level events. Consumers must decide:

- Do they need to observe every individual event?
- Must they apply all events or none?
- Do they require transaction boundaries?
- Can each aggregate be processed independently?

If consumers require source-transaction atomicity, they need transaction metadata (transaction ID, event count, ordering, END marker) from a supporting connector/output format. Consumers can stage events per transaction and apply them upon receiving the commit boundary.

This increases latency and memory/storage demands. If cross-table atomicity is unnecessary, per-aggregate/key processing is usually simpler and scales better.

## 42. Snapshot Consistency and Initial Load

A large initial snapshot can take hours while the source continues accepting writes. Connectors must align the snapshot point with a WAL position so every change is captured.

Questions to answer:

- Does the snapshot represent a consistent point in time?
- Is the WAL slot created before or during the snapshot workflow?
- How long does the connector hold an exported snapshot?
- Are transaction age limits configured?
- Can consumers receive snapshot rows overlapping with stream updates?
- Does the sink use upserts/aggregate versions to handle overlap?
- Can a snapshot resume after a crash?

Never construct a snapshot by running SELECT * across tables at different times and treating it as a consistent baseline. Use a connector-supported snapshot mode or a proven snapshot/slot export workflow.

## 43. Native Logical Replication: Subscriber-Side Checks

When using a native PostgreSQL subscription:

~~~sql
CREATE SUBSCRIPTION orders_sub
CONNECTION 'host=<publisher-host> port=5432 dbname=sales user=replication_user'
PUBLICATION orders_cdc_pub
WITH (copy_data = true, create_slot = true, enabled = true);
~~~

The connection string here is a placeholder; real credentials must come from a secret manager/connection policy. Creating a subscription connects to the publisher and creates a slot. Never share the same slot managed by another connector.

Before creating the subscription:

- Create schemas/tables on the subscriber.
- Verify owners and data types.
- Check publication scope.
- Verify network/TLS/HBA.
- Ensure sufficient replication slots/senders.
- Confirm copy_data and initial sync behavior.
- Define conflict policy.

After creation:

~~~sql
SELECT
    subname,
    pid,
    relid::regclass AS relation_name,
    received_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_stat_subscription;
~~~

View columns differ across versions. Check subscription state and per-table sync state in the relevant system catalogs.

### Subscribers Do Not Auto-Sync Schemas

Creating publications and subscriptions does not auto-create full subscriber schemas. Tables must exist and be compatible. Publisher DDL changes must be rolled out independently on the subscriber before row changes requiring the new schema arrive.

## 44. CDC for Partitioned Tables

Partitioned tables require reviewing publication behavior and connector metadata:

- Publish via partition root vs. individual leaves.
- Table filters applied at parent vs. partition level.
- Consumer key/schema naming.
- Partition attach/detach events.
- DDL/partition maintenance is not propagated like row changes.
- Partition routing when the sink is also partitioned.

PostgreSQL supports the publish_via_partition_root option in supported versions. This setting affects relation identity/schema in logical change streams. Verify behavior on your exact PostgreSQL version and connector.

Do not assume partition attach/detach operations automatically appear as INSERT/DELETE row events to CDC consumers.

## 45. Event Processing When the Sink Is a Search Index or Cache

A consumer may update Elasticsearch/OpenSearch, Redis, or a cache service. These sinks generally do not participate in PostgreSQL transactions.

Design practices:

- Use a stable document key derived from the aggregate/row primary key.
- Use idempotent upserts/document replacements.
- Use versions/LSNs to ignore stale updates across ordering gaps.
- Make deletes idempotent.
- Retry transient network errors.
- Rebuild the index/cache from a snapshot when needed.
- Reconcile between source and sink.
- Never checkpoint before the sink confirms success.

For caches, you can invalidate keys instead of pushing full row payloads. Invalidation reduces coupling, though cache repopulation and duplicate invalidations must be handled.

## 46. Event Processing When the Sink Is a Data Warehouse

Data warehouses typically ingest append-only CDC logs and transform them into current-state or history tables.

Key design points:

- Raw event retention.
- Deduplication key.
- Source commit LSN/transaction ID.
- Late/out-of-order event handling.
- Delete representation.
- Schema evolution.
- Snapshot vs. streaming merge.
- Effectively-once merge semantics.
- Reconciliation and backfills.

For current-state tables, use MERGE/upsert keyed by primary key and source version/LSN so older events never overwrite newer state. For history/SCD tables, preserve event order and transaction metadata.

## 47. Observability Across Producer, Connector, Broker, and Consumer

Monitor every layer:

| Layer | Key Metrics / Logs |
| --- | --- |
| PostgreSQL | WAL generation, slot restart_lsn, confirmed_flush_lsn, retained WAL, active slots |
| Connector | last processed LSN, source lag, queue size, task state, snapshot progress |
| Broker | records in/out, partition lag, under-replicated partitions, produce errors |
| Consumer | processing rate, commit latency, retries, DLQ, duplicate count, sink errors |
| Sink | write latency, connection pool, locks, storage, error rate |
| Business | event-to-effect latency, missing transitions, reconciliation mismatches |

Synchronize clocks via NTP/time policy. End-to-end latency can be computed from event/source timestamp to sink applied_at, accounting for clock skew and timestamp semantics.

### Critical Alerts

- Prolonged inactive slot.
- Retained WAL exceeding threshold.
- Connector failing to advance LSN.
- Continuously growing broker lag.
- Rising consumer error/retry rates.
- New events landing in DLQ.
- Event-to-effect latency exceeding SLA.
- Sudden spike in duplicate rate.
- Reconciliation mismatches.

## 48. Runbook: Handling a Stalled CDC Pipeline

### Step 1: Scope the Incident

- Database/cluster and publication.
- Slot name and connector.
- Topic/partition.
- Consumer group.
- Sink tables/services.
- Timestamp of the last successful event.

### Step 2: Inspect PostgreSQL

~~~sql
SELECT
    slot_name,
    plugin,
    slot_type,
    database,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
WHERE slot_type = 'logical';
~~~

Check disk space, WAL retention, server logs, and replication connections.

### Step 3: Inspect Connector and Broker

- Task states and error logs.
- Last source LSN.
- Connector queues.
- Broker offsets/lag.
- Serialization/schema errors.
- Credentials/networking.

### Step 4: Inspect Consumer and Sink

- Last committed offset.
- Last successful event.
- Inbox/dedup records.
- Sink transaction errors.
- DLQ/retry backlog.
- Application version.

### Step 5: Recover

- Restart the connector if the slot is still valid.
- Fix schema/credential/network issues.
- Replay events by offset if within retention.
- If the slot lost WAL, bootstrap/reconcile from a snapshot.
- Run sink reconciliation.
- Record incident evidence and verify end-to-end latency returns within SLA.

Never drop/recreate a slot simply because a connector disconnected. Check slot state and WAL availability first.

## 49. Runbook: Handling Duplicate or Out-of-Order Events

1. Capture event ID, source LSN, transaction metadata, partition/offset, and aggregate key.
2. Check whether the producer emits stable event IDs.
3. Check connector restarts and offset commits.
4. Check consumer commit ordering.
5. Inspect inbox unique constraints and retention.
6. Check partition keys and parallel processing.
7. Check for aggregate version gaps or stale events.
8. Verify whether the business effect already occurred.
9. Replay/reconcile per policy.
10. Fix producer/consumer bugs and add regression tests.

If an event is duplicated and the effect is idempotent, it can safely no-op. If out-of-order events cause state regressions, add version guards or per-key sequencing.

## 50. Common Mistakes

1. **Treating CDC and business events as identical**, coupling consumers directly to internal schemas.
2. **Publishing messages after database commit without an outbox**, creating a gap on process crashes.
3. **Using at-most-once yet expecting zero lost events**, as pre-effect checkpoints can drop changes.
4. **Checkpointing before sink commit**, losing events if the consumer crashes.
5. **Committing sink effects without deduplication**, producing duplicate side effects on redeliveries.
6. **Putting inbox and business effects in separate transactions**, opening a window for lost or duplicated effects.
7. **Generating a new event ID on each retry**, defeating deduplication.
8. **Treating Kafka transactions as end-to-end exactly-once across external databases/APIs**, ignoring cross-system transaction boundaries.
9. **Lacking a proper replica identity**, preventing UPDATE/DELETE capture.
10. **Applying REPLICA IDENTITY FULL to every table**, inflating WAL and data exposure unnecessarily.
11. **Creating a slot manually while letting the connector create another**, leaving orphaned slots retaining WAL.
12. **Ignoring inactive logical slots**, letting pg_wal grow until disks fill up.
13. **Dropping a slot to free disk without evaluating recovery**, losing the ability to resume cleanly.
14. **Failing to sync subscriber schemas before publisher changes**, breaking apply workers.
15. **Assuming logical replication replicates DDL, sequences, and large objects**, leaving missing sink state.
16. **Taking snapshots and starting streams without a shared watermark**, causing uncontrolled gaps or duplicates.
17. **Monitoring only broker lag**, missing slot lag and connector queue backlogs.
18. **Retrying poison events indefinitely**, causing retry storms and blocking partitions.
19. **Sending events to a DLQ and forgetting them**, leaving obligations unmet while reporting success.
20. **Replaying without preserving original event IDs**, breaking deduplication.
21. **Failing to preserve per-aggregate ordering**, letting older events overwrite newer state.
22. **Increasing partition counts without reviewing key ordering**, altering event distribution.
23. **Purging inbox rows too early**, letting old replays trigger duplicate effects.
24. **Deleting outbox rows before relays/connectors read them**, losing events.
25. **Skipping source-to-sink reconciliation**, missing event gaps or consumer bugs.
26. **Exposing uncontrolled PII in event topics**, spreading sensitive data across systems.
27. **Failing to version event schemas**, breaking old consumers when producers evolve.
28. **Confusing slot confirmed_flush_lsn with broker offsets**, conflating two different checkpoints.
29. **Lacking a runbook for slot WAL loss**, extending outage recovery time.
30. **Testing only the happy path**, skipping crashes between sink commit and offset commit.

## 51. Practice Exercises with Answers

### Exercise 1. What is CDC?

**Answer:** A mechanism that captures committed data changes and forwards them to other systems for synchronization or processing.

### Exercise 2. How does row-level CDC differ from a business event?

**Answer:** CDC describes row/table mutations; a business event describes a meaningful domain occurrence.

### Exercise 3. What does logical decoding read?

**Answer:** It reads WAL and translates changes into logical records via an output plugin.

### Exercise 4. What is an LSN?

**Answer:** Log Sequence Number, a position in WAL; it is not by default a unique business event ID.

### Exercise 5. What is a replication slot used for?

**Answer:** Preserving decoding/replication progress and retaining WAL needed by the consumer.

### Exercise 6. What is the role of a publication?

**Answer:** Defining which tables and operations are published by native logical replication.

### Exercise 7. What value must wal_level have for logical decoding?

**Answer:** logical.

### Exercise 8. Why use a dedicated replication role?

**Answer:** To restrict privileges, support auditing, and limit the connector's blast radius.

### Exercise 9. What does REPLICA IDENTITY DEFAULT typically use?

**Answer:** The primary key, if present, to identify old rows for UPDATE/DELETE.

### Exercise 10. What is the tradeoff of REPLICA IDENTITY FULL?

**Answer:** It captures complete old row images at the cost of larger WAL volume and greater data exposure.

### Exercise 11. Does logical replication automatically replicate DDL?

**Answer:** Not by default; schema changes must be deployed separately.

### Exercise 12. What problem does the transactional outbox solve?

**Answer:** Writing business state and event records in the same transaction, preventing database commits with lost events.

### Exercise 13. Can at-least-once delivery produce duplicates?

**Answer:** Yes; crashing after sink commit and before offset commit causes events to be redelivered.

### Exercise 14. What does end-to-end exactly-once require?

**Answer:** Atomic coordination between the effect and checkpoint, or an idempotent sink with durable deduplication.

### Exercise 15. What does the inbox pattern do?

**Answer:** Records processed event IDs and applies business effects within the same transaction.

### Exercise 16. When should offsets be checkpointed?

**Answer:** After the sink transaction has successfully committed.

### Exercise 17. Should an event ID change on retries?

**Answer:** No; it must remain stable to enable deduplication.

### Exercise 18. Why use aggregate ID as the partition key?

**Answer:** To preserve event ordering for a single aggregate within one partition.

### Exercise 19. At what scope do brokers typically guarantee ordering?

**Answer:** Usually per partition, not globally across an entire topic.

### Exercise 20. What is a poison event?

**Answer:** An event that consistently fails due to payload/schema/logic errors and will not succeed on retry.

### Exercise 21. What should a DLQ store?

**Answer:** Event ID, source offset/LSN, protected payload, attempt count, error details, and replay status.

### Exercise 22. Why shouldn't you take a snapshot manually and create a slot afterward?

**Answer:** It can leave a gap between the snapshot and the WAL stream; consistent snapshot/LSN coordination is needed.

### Exercise 23. What can an inactive slot cause?

**Answer:** Prolonged WAL retention that can fill up the filesystem.

### Exercise 24. Is confirmed_flush_lsn a broker offset?

**Answer:** No; it tracks PostgreSQL-side slot/logical replication progress.

### Exercise 25. What happens when a slot loses required WAL?

**Answer:** The consumer cannot resume from its old position; bootstrapping/reconciling or recovery per connector policy is required.

### Exercise 26. Why must inbox retention match the replay window?

**Answer:** Purging deduplication state too early allows replayed old events to trigger duplicate effects.

### Exercise 27. How should event schemas evolve?

**Answer:** Version contracts, add compatible fields first, roll out consumers, and only then remove deprecated fields.

### Exercise 28. Why is source-to-sink reconciliation necessary?

**Answer:** To detect missing, duplicate, stale, or corrupted data after connector outages or replays.

### Exercise 29. Do CDC delete events always include the old row?

**Answer:** No; it depends on replica identity, publication settings, and connector format.

### Exercise 30. What must a safe consumer guarantee?

**Answer:** Validate events, deduplicate, apply effects transactionally, checkpoint after commit, manage retries/DLQ cleanly, and reconcile.

## 52. CDC Design and Operations Checklist

### Source PostgreSQL

- [ ] wal_level = logical.
- [ ] Sufficient max_replication_slots/max_wal_senders.
- [ ] Restart performed if required by settings.
- [ ] Least-privilege replication role.
- [ ] HBA/TLS/network restricted.
- [ ] Accurate publication scope.
- [ ] Appropriate replica identity for UPDATE/DELETE.
- [ ] Clear slot owner and lifecycle.
- [ ] max_slot_wal_keep_size/capacity policy evaluated.
- [ ] Alerts for inactive slots and retained WAL.

### Connector and Broker

- [ ] Compatible output plugin/version.
- [ ] Consistent connector slot management.
- [ ] Clear snapshot mode and watermark.
- [ ] Clear event envelope/schema version.
- [ ] Defined topic/partition/key strategy.
- [ ] Proper broker ACLs/retention/encryption.
- [ ] Connector offsets protected.
- [ ] Connector lag/task state monitored.

### Consumer and Sink

- [ ] Stable event IDs.
- [ ] Inbox/unique idempotency key.
- [ ] Inbox and business effect in the same transaction where possible.
- [ ] Offset/ACK committed after sink commit.
- [ ] Retryable/non-retryable errors classified.
- [ ] Backoff/jitter and retry budget configured.
- [ ] DLQ/quarantine has an owner and replay plan.
- [ ] Per-aggregate ordering defined.
- [ ] Schema compatibility validated.
- [ ] External side effects use idempotency/compensation.
- [ ] Inbox retention covers the replay horizon.

### Recovery and Operations

- [ ] Gap-free initial snapshot and streaming.
- [ ] Source/sink reconciliation runnable.
- [ ] Slot loss/re-bootstrap runbook exists.
- [ ] Connector restart/replay runbook exists.
- [ ] WAL disk capacity and alerting active.
- [ ] Sink and offset backups/restores coordinated.
- [ ] PII/secret redaction in place.
- [ ] Event-to-effect latency and DLQ monitored.
- [ ] Incident evidence and owners defined.
- [ ] Recovery drills performed.

## 53. Official PostgreSQL Documentation

Consult the documentation for your deployed major version:

- [Logical Decoding](https://www.postgresql.org/docs/current/logicaldecoding.html) — architecture and concepts of logical decoding.
- [Logical Decoding Concepts](https://www.postgresql.org/docs/current/logicaldecoding-explanation.html) — slots, snapshots, output plugins, and consistency.
- [Logical Decoding Output Plugins](https://www.postgresql.org/docs/current/logicaldecoding-output-plugin.html) — plugin interface.
- [Logical Replication](https://www.postgresql.org/docs/current/logical-replication.html) — publisher, subscriber, and replication model.
- [Publications](https://www.postgresql.org/docs/current/logical-replication-publication.html) — publication scope and operations.
- [Subscriptions](https://www.postgresql.org/docs/current/logical-replication-subscription.html) — subscription configuration.
- [Replication Slots](https://www.postgresql.org/docs/current/logicaldecoding-explanation.html#LOGICALDECODING-REPLICATION-SLOTS) — slot behavior and WAL retention.
- [REPLICA IDENTITY](https://www.postgresql.org/docs/current/sql-altertable.html) — configuring row identity.
- [WAL Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html) — wal_level and WAL settings.
- [Replication Configuration](https://www.postgresql.org/docs/current/runtime-config-replication.html) — senders, slots, and replication settings.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_replication, pg_replication_slots, and monitoring views.
- [CREATE PUBLICATION](https://www.postgresql.org/docs/current/sql-createpublication.html) — creating publications.
- [CREATE SUBSCRIPTION](https://www.postgresql.org/docs/current/sql-createsubscription.html) — creating subscriptions.
- [CREATE ROLE](https://www.postgresql.org/docs/current/sql-createrole.html) — role attributes and replication privileges.
- [CREATE EXTENSION](https://www.postgresql.org/docs/current/sql-createextension.html) — installing extensions.
- [WAL Internals](https://www.postgresql.org/docs/current/wal-intro.html) — write-ahead logging.

Connector-specific snapshot, offset, schema history, event envelope, and exactly-once semantics must be verified in the documentation for your exact connector and broker versions. PostgreSQL logical decoding guarantees source-side decoding semantics; it does not automatically guarantee consumer side effects are applied exactly once.

## 54. Summary

**CDC gets committed changes out of PostgreSQL; consumers must turn potentially repeated deliveries into safe business effects.** Logical decoding, publications, and replication slots handle source capture. Event contracts, inbox/outbox, idempotency, ordering, retries, and checkpoints govern the integration.

1. **Distinguish row-level CDC from business events.** Choose event types based on consumer needs and desired coupling.
2. **Logical decoding relies on WAL.** wal_level, output plugins, publications, and replication slots must be properly configured.
3. **Replica identity governs UPDATE/DELETE capture.** FULL increases WAL volume and data exposure.
4. **Replication slots retain WAL for consumers.** Inactive or lagging slots can fill disks; maintain capacity planning and alerts.
5. **Logical replication does not replicate every object.** DDL, sequences, roles, grants, and large objects require separate processes.
6. **Transactional outbox binds business events to database commits.** Never emit events after commit without a durable outbox.
7. **At-least-once is the standard model.** Duplicates must be handled via event IDs/inbox/idempotency keys.
8. **Commit sink effects before checkpointing.** Inbox and business effects should share the same transaction.
9. **Ordering must be designed intentionally.** Partition by aggregate key and use aggregate versions to detect stale/gapped events.
10. **Retry with backoff; route poison events to a DLQ with an owner.** Replays must preserve event IDs and ordering semantics.
11. **Snapshots need a watermark aligned with the WAL stream.** Avoid gaps using connector-supported snapshot workflows.
12. **Reconcile source and sink.** Verify counts, keys, aggregates, and watermarks after outages or replays.
13. **Version event schemas.** Roll out producers and consumers within compatibility windows.
14. **Monitor slots, connectors, brokers, consumers, and sinks.** A single lag metric is insufficient for root-cause diagnosis.
15. **Protect event payloads and credentials.** CDC can broaden sensitive data exposure across downstream systems.

A reliable CDC pipeline does more than forward records. It sustains progress, handles duplicates safely, detects gaps, recovers from outages, and proves the receiving system applied the exact changes PostgreSQL committed.
