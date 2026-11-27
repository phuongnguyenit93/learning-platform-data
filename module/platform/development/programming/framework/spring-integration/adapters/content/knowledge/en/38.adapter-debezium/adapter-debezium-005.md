# Snapshot vs. Streaming in Debezium

## 1. Why Does CDC Need Both Snapshot and Streaming?

In the **SPRING_INTEGRATION_ADAPTERS** module, applications use inbound/outbound adapters, gateways, pollers, and `MessageChannel`s to exchange data with external systems like Kafka, JMS, HTTP, or databases. When the data source is an operational database, **Debezium** captures changes via *Change Data Capture* (CDC) and forwards events into a Spring Integration flow for processing.

However, when first connecting to a `sales.orders` table that already holds 2 million orders, the transaction log typically contains only changes still within the retained log window. To build a complete replica and keep it continuously updated, we must answer two questions:

1. **How do we capture data that already existed before the connector started?** That is the typical job of a *snapshot*.
2. **How do we capture changes committed while the system is running?** That is the job of *streaming* from the transaction log.

Snapshot and streaming are **two complementary phases** of a CDC pipeline; an application can start with streaming alone in specific cases, or proactively capture a subset of data later using an incremental snapshot.

After this lesson, you will be able to:

- Distinguish the goals, data sources, events, consistency, latency, and costs of snapshots vs. streaming.
- Understand the transition from initial snapshot to streaming and the role of source offsets.
- Identify *blocking snapshots*, *incremental snapshots*, snapshot modes, and signals per connector capabilities.
- Establish CDC processing principles in Spring Integration: upserts, deletes, idempotency, message ordering, and error recovery.
- Choose an appropriate snapshot strategy for initial sync, adding new tables, fixing projections, or restarting connectors.

## 2. The Big Picture

~~~mermaid
flowchart TD
    A[(Operational database)] --> B{Valid source offset<br/>exists?}
    B -- No, snapshot.mode=initial --> C[Initial snapshot<br/>read existing state]
    C --> D[Checkpoint log boundary<br/>and snapshot progress]
    D --> E[Streaming<br/>read binlog / WAL]
    B -- Yes --> E
    B -- No-data mode selected --> E
    E --> F[Debezium change events]
    F --> G[(Kafka topic or sink)]
    G --> H[Spring Integration inbound adapter]
    H --> I[MessageChannel]
    I --> J[Handler updates projection]
    E -. May receive signal .-> K[Incremental snapshot<br/>selected tables / chunks]
    K --> F
~~~

The diagram illustrates a common scenario with Debezium running on Kafka Connect. **Actual execution branches depend on snapshot mode, connector, stored offsets, and Debezium version**. Debezium Engine or Debezium Server uses different offset/sink mechanisms but faces the same initialization and resumption challenges.

Three independent progress markers exist in this pipeline:

| Progress Marker | Belongs To | Meaning |
|---|---|---|
| Source position | MySQL binlog, PostgreSQL WAL/LSN, etc. | Where a change sits in the transaction log |
| Debezium source offset | Connector / offset store | State allowing the connector to resume snapshot or streaming after a restart |
| Kafka consumer offset | Spring Integration consumer group | How far the application has confirmed consuming in a Kafka partition |

You cannot derive one type of offset from another. When Debezium finishes a snapshot, that **does not prove** the entire snapshot has been successfully applied to the target database.

## 3. Snapshot: Reading Existing State

### 3.1. How Does an Initial Snapshot Work?

An *initial snapshot* lets the connector capture existing rows at a point in time or a consistent view determined by the database/connector. Debezium typically performs these logical steps:

1. Discover schemas and the configured list of captured tables.
2. Determine the log boundary or coordinate used to stitch the snapshot to streaming.
3. Read existing records from selected tables, emitting **read** events.
4. Persist snapshot state/progress using the connector's offset mechanism.
5. Switch to streaming, reading committed changes from the appropriate log boundary.

**Consistency note:** locking mechanisms, isolation levels, read passes, and boundary capture vary by DBMS, table engine, and snapshot mode. PostgreSQL typically leverages MVCC/replication slots; MySQL has binlog and consistent-read requirements. Never assume snapshots always "lock the entire database" or "never take locks".

Suppose at snapshot time, the `orders` table contains:

| id | status | total |
|---:|---|---:|
| 101 | NEW | 150000 |
| 102 | PAID | 250000 |

Debezium may emit two **`op = "r"`** (read) events corresponding to the current state of the two rows. A snapshot cannot reconstruct history such as "order 102 was previously in `NEW` status" if that history no longer exists in the scanned rows or retained logs.

Example envelope **simplified for readability**:

~~~json
{
  "before": null,
  "after": {
    "id": 102,
    "status": "PAID",
    "total": 250000
  },
  "source": {
    "connector": "mysql",
    "db": "sales",
    "table": "orders",
    "snapshot": "true"
  },
  "op": "r"
}
~~~

Some connectors mark the final snapshot record with a value like `"last"`; the representation of `source.snapshot` depends on the converter/schema. With incremental snapshots, `op = "r"` events can still appear **after streaming is already active**.

### 3.2. What Snapshots Solve and Where Their Limits Lie

A snapshot provides **initial state** to populate search indexes, caches, data warehouses, or projection tables. In return, it can consume substantial I/O, CPU, database connections, broker storage, and time when moving large data volumes. Long snapshots also increase how long transaction logs must be retained before streaming catches up.

A snapshot does not automatically guarantee two-way sync, cannot replay history prior to the capture boundary, and does not imply the sink has finished processing just because the connector emitted all `r` records.

## 4. Streaming: Reading Committed Changes from the Log

Once a valid log boundary is established, Debezium reads changes via the source's log mechanism:

- **MySQL:** binary log (*binlog*), typically in row-based format; positions involve binlog file, byte position, and optionally GTID.
- **PostgreSQL:** WAL via logical decoding and a replication slot; positions are typically LSNs.
- **Other sources:** SQL Server, Oracle, and MongoDB have their own logging and positioning mechanisms.

Streaming reflects **committed changes**, typically inserts, updates, and deletes. Typical `op` values in the envelope:

| `op` | Name | Meaning for Target Data |
|---|---|---|
| `r` | Read | Row read during snapshot; usually handled as initialization/upsert |
| `c` | Create | New row inserted; usually upsert/insert by key |
| `u` | Update | Row updated; apply new state or process diff |
| `d` | Delete | Row deleted; delete or soft-delete in projection |

Example streaming event after order 101 transitions from `NEW` to `PAID`:

~~~json
{
  "before": { "id": 101, "status": "NEW", "total": 150000 },
  "after":  { "id": 101, "status": "PAID", "total": 150000 },
  "source": {
    "connector": "mysql",
    "db": "sales",
    "table": "orders",
    "file": "mysql-bin.000021",
    "pos": 23456,
    "snapshot": "false"
  },
  "op": "u"
}
~~~

JSON examples illustrate logical structure and **do not guarantee** every field appears in all Debezium versions, all connectors, or after SMTs/converters. The presence of `before` also depends on source log capabilities and configuration.

### How Does Streaming Differ from Database Polling?

Traditional polling runs a periodic SQL query such as "fetch rows with `updated_at` newer than the last run". That approach requires a reliable tracking column, can miss rapid updates between polls, and struggles to detect DELETEs once rows are gone. Debezium streaming reads the transaction log directly according to source capabilities and capture settings, avoiding continuous full-table scans for new rows.

Even so, streaming **does not guarantee** zero latency: commit time, decoding, buffering, broker transit, and downstream processing all add time and potential lag. It also depends on log retention, replication privileges, and connector health.

### Delete Events and Tombstones

When a row is deleted, Debezium normally emits an `op = "d"` event. When the connector/config enables tombstones, Kafka may also receive a record with the **same key and a null value** for log compaction. A tombstone is not a second update event. When using the Spring Integration Kafka adapter, the application must understand how the converter/deserializer represents null values to avoid trying to parse null as a JSON envelope.

## 5. Snapshot vs. Streaming: Comparison Table

| Criterion | Snapshot | Streaming |
|---|---|---|
| Goal | Capture current state of existing records | Continuously track changes after the log boundary |
| Primary data source | Reads tables/schemas via connector snapshot mechanism | Reads transaction log or change stream |
| Common events | `op = r` | `op = c/u/d`, occasionally with extra metadata |
| When it occurs | Connector initialization or explicit snapshot request | After initial capture or in streaming-only configurations |
| Primary costs | Data scan, I/O load, capture duration, large initial backlog | Log decoding, maintaining replication, continuous event stream |
| Unchanged rows | Included if within snapshot scope | Never emitted merely because the row exists |
| Changes before capture boundary | Shows only surviving state, not full history | Cannot read changes from already purged logs |
| Consistency | Depends on snapshot mechanism, transaction isolation, and connector | Follows log commits; global sink order still depends on partitions/routing |
| Restart | May resume or restart partially/fully depending on mode, offset, and connector | Resumes from valid checkpoint if required logs still exist |
| Impact on sink | Can produce huge bursts of `r`, requiring upserts/bulk loads | Applies `c/u/d` sequences, requiring retries and idempotency |

You cannot pick one mode purely on speed: if you need **a full sync of existing data**, streaming from now onward is insufficient; if you need **a near-real-time replica**, a one-time snapshot is also insufficient.

## 6. Transitioning from Initial Snapshot to Streaming Without Missing Changes

The hardest part of an initial snapshot is that the database **continues committing new transactions while millions of rows are being read**. Debezium must coordinate a consistent read point with a log boundary. Logical example:

~~~mermaid
sequenceDiagram
    participant DB as Database
    participant DZ as Debezium connector
    participant OUT as Kafka / Sink
    DZ->>DB: Establish consistent snapshot + log boundary P
    DZ->>DB: Read existing rows
    DB-->>DB: Transaction T1 updates order 101, commits after P
    DZ->>OUT: Emit r events from snapshot
    DZ->>DZ: Finish snapshot; persist state/offset
    DZ->>DB: Start streaming from appropriate position
    DB-->>DZ: Log event for T1
    DZ->>OUT: Emit u event for order 101
~~~

For example, if the snapshot sees order 101 as `NEW` and transaction `T1` updates it to `PAID` after the snapshot boundary, the receiver may observe:

1. `r`: order 101 = `NEW`;
2. `u`: order 101 = `PAID`.

This logical sequence leaves the projection in the final state `PAID`. Exact snapshot isolation, table ordering, and transaction scoping depend on the connector and database. **Never build your own transition by running `SELECT *` alongside log reading without a boundary-synchronization algorithm**: you risk both missing and double-counting changes.

### When Does a Subsequent Restart Re-Snapshot from Scratch?

With `snapshot.mode = initial`, the connector normally executes an initial snapshot **when no valid source offset exists**. If the offset exists and the snapshot state is complete, a restart resumes from the saved state rather than rescanning entire tables. If the offset store is deleted, the connector's source identity changes, or a recovery event occurs, the application may restart according to the mode and connector rules.

A source offset may include **snapshot state** alongside the log position. A raw LSN or binlog position extracted from an event **is not enough** to reconstruct all snapshot state on its own. Because source offsets are flushed periodically, crashes can also cause the connector to replay some events; this is why sinks require idempotency.

## 7. Incremental Snapshots: Capturing in Chunks While Streaming Runs

Scanning millions of rows in a single initial snapshot is not always practical. Many Debezium connectors support **incremental snapshots**: splitting one or more tables into *chunks* along an appropriate key, reading them sequentially while continuing to process the live change stream throughout the snapshot.

Example `orders` table with primary key `id`:

~~~text
Chunk 1: id 1..1000    -> emit r events
Chunk 2: id 1001..2000 -> emit r events
Chunk 3: id 2001..3000 -> emit r events
...
Streaming c/u/d events continue interleaved with chunks.
~~~

### The Problem of Rows Changing While a Chunk Is Read

Suppose while an incremental snapshot reads a chunk containing `orders.id = 101`, the application concurrently updates that order. If the connector blindly emitted the older snapshot row after the update event, the sink could **overwrite newer state with stale state**.

To mitigate this conflict, Debezium uses a *snapshot window* mechanism to detect collisions between keys being snapshotted and streaming events; exact watermark/signal coordination varies by connector and version. Conflicting snapshot rows are discarded from the window so log changes take precedence. This mechanism helps **prevent stale overwrites during the incremental snapshot itself**, without eliminating the need for downstream idempotency across retries or restarts.

Operational factors to consider include: a suitable chunking key on the table, chunk size, DB load, snapshot control signals, persisted progress, schema changes mid-run, new data inserted in the same key range, and sink application order.

### Example: Requesting an Incremental Snapshot via Signal

In a Debezium MySQL deployment supporting table-based signaling, assume the signal data collection is configured as `sales.debezium_signal` and created with the schema required by your connector version. An **illustrative** command:

~~~sql
INSERT INTO sales.debezium_signal (id, type, data)
VALUES (
    'snap-orders-20261123',
    'execute-snapshot',
    '{"data-collections": ["sales.orders"], "type": "incremental"}'
);
~~~

Debezium observes the committed signal and snapshots the requested data collection according to connector capabilities. You must properly configure the signal channel/table, read/write permissions, capture filters, table keys, and supported modes. Signal syntax, property names, and features can change across versions; **test in staging before applying in production**.

Incremental snapshots are ideal when **adding tables to capture scope**, resynchronizing a dataset, or reducing the blast radius of a full-table scan. They do not repair a streaming offset pointing to purged logs, nor do they guarantee every target handler tolerates large volumes of `r` events if handlers only accept `c/u/d`.

## 8. Choosing a Snapshot Mode for the Problem

Not every snapshot mode exists or carries the exact same name/meaning across all Debezium versions and connectors. Common choices:

| Need | Configuration / Action Direction | What to Verify |
|---|---|---|
| First-time full projection build | `snapshot.mode=initial` followed by streaming | Captured tables, consistency, log retention, DB load |
| Only changes from start time onward | No-snapshot mode, e.g., `no_data` on supporting connectors/versions | Does sink already have a complete baseline? Missing old data is an intentional consequence |
| Backfill specific active tables | Signal-driven incremental snapshot if supported | Table keys, chunking, filters, and `r` event handling at sink |
| One-time data export snapshot | Snapshot-only mode if supported by connector/version | Whether connector continues streaming or stops afterward |
| Intentionally re-snapshot everything on restart | Intentional re-snapshot mode if supported | System load, duplicate events, idempotency |
| Saved log position no longer readable | Evaluated recovery or resnapshot procedure | Potential missed change window; target reconciliation needed |

### Example Initial Snapshot Configuration for PostgreSQL

The JSON snippet below shows **connector configuration on Kafka Connect**, not a Spring Integration configuration bean:

~~~json
{
  "name": "sales-orders-cdc",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "tasks.max": "1",
    "topic.prefix": "sales-cdc",
    "database.hostname": "postgres.example.internal",
    "database.port": "5432",
    "database.user": "cdc_reader",
    "database.password": "<set-using-secret-management>",
    "database.dbname": "sales",
    "plugin.name": "pgoutput",
    "slot.name": "sales_orders_slot",
    "publication.name": "sales_orders_pub",
    "table.include.list": "public.orders",
    "snapshot.mode": "initial"
  }
}
~~~

This is a **reference example**. To run in practice, you still need WAL/logical replication settings, publication, slot, user privileges, credential security, Kafka Connect worker config, and requirements specific to your Debezium version. `snapshot.mode=initial` only controls initial capture behavior; it does not replace WAL retention settings or replication slot monitoring.

For MySQL, configuration uses the MySQL connector, binlog, and dedicated properties like server ID and schema history. **Never copy a PostgreSQL configuration to run MySQL**.

## 9. Handling Snapshot and Streaming in Spring Integration

Typical architecture with Kafka:

~~~mermaid
flowchart LR
    DB[(MySQL / PostgreSQL)] --> DZ[Debezium<br/>snapshot + streaming]
    DZ --> K[(Kafka CDC topic)]
    K --> IN[Spring Integration<br/>Kafka inbound adapter]
    IN --> CH[MessageChannel]
    CH --> TRANS[Transformer<br/>normalize envelope]
    TRANS --> H[Service activator<br/>upsert / delete]
    H --> PROJ[(Projection / cache)]
    H -. Failure .-> ERR[Retry / error channel / DLQ]
~~~

Spring Integration receives messages from Kafka through an inbound adapter or gateway, forwards them to a `MessageChannel`, applies transformers/filters/routers, and updates the target system. Business logic must distinguish **Debezium change type** from **Kafka consumer metadata**. Never turn `op=r` into "create a new order and send customer email": it may simply be re-reading a row that has existed for years.

### 9.1. Example Handler Updating State Without Re-Running Side Effects

Pseudocode for a `reporting.orders` projection:

~~~text
handleCdcEvent(message):
    event = decodeDebeziumEnvelope(message)
    if event is a Kafka tombstone:
        processAccordingToTombstonePolicy(message.key)
        return

    key = extractPrimaryKey(message.key, event)

    if event.op in ["r", "c", "u"]:
        desiredState = event.after
        transaction:
            applyIdempotentUpsert(key, desiredState, sourceVersion(event))
            recordProcessingCheckpointIfNeeded(event)

    else if event.op == "d":
        transaction:
            applyIdempotentDelete(key, sourceVersion(event))
            recordProcessingCheckpointIfNeeded(event)

    else:
        routeToUnsupportedEventPolicy(event)

    acknowledgeBrokerConsumptionAfterSuccessfulProcessing()
~~~

This is **pseudocode**, not the Java API of a specific adapter. `sourceVersion(event)` must be designed around the actual connector and source contract; never assume a standalone `ts_ms`, `lsn`, or `binlog.pos` is globally comparable across all tables, partitions, or transactions.

For systems that only need final state, an **idempotent upsert by business key** is usually appropriate for `r/c/u`. For systems triggering payments, sending emails, or accumulating counters, repeated processing requires a durable deduplication key or an appropriate outbox/transactional design. If `r` events are misinterpreted as "newly occurred" events, side effects will re-fire during snapshots or resnapshots.

### 9.2. Common Sources of Divergence

1. **Ordering:** in Kafka, ordering is guaranteed per partition; key messages appropriately for changes to the same record and control concurrency inside Spring Integration. Cross-partition order cannot be inferred from arrival times.
2. **Commit/ack:** confirm consumption offsets only after target persistence succeeds per application policy. Enqueuing a message in memory does not mean the projection committed; verify ACK modes, async handoffs, and error flows.
3. **Replays:** unflushed source offsets, uncommitted consumer offsets, or retries can all cause an event to reappear. Snapshot completion does not create end-to-end exactly-once semantics.
4. **Schema changes:** events before and after DDL may differ in structure; transformers/validators must account for schema evolution, converters, and active SMTs.
5. **Deletes:** establish clear rules for hard deletes, soft deletes, and tombstones; compacted topics use tombstones to clean keys, while business logic still needs to handle `op=d`.
6. **Throughput:** initial snapshots can emit bursts of data, creating Kafka lag or overwhelming downstream sinks. Backpressure/rate limits, batching, or scaling bottleneck tiers may be necessary.

### 9.3. Error Flows and Responsibilities

| Error | Which Layer? | Appropriate Handling |
|---|---|---|
| PostgreSQL slot/WAL no longer usable | Database + Debezium | Check checkpoints, WAL retention, and source recovery runbook |
| Burst of snapshot events causes consumer lag | Debezium/Kafka/Spring Integration | Measure throughput, allocate resources, chunk/throttle if supported |
| Transformer does not understand `op=r` | Spring Integration | Add read-event handling branch; test with snapshot payloads |
| Projection written but consumer dies before commit | Consumer + sink | Idempotency to handle redelivery safely |
| `d` events ignored | Target application | Define delete policy and verify consistency |
| Snapshot misses tables due to filters | Connector configuration | Verify `table.include.list` and related filters before running |

Other adapters such as file, HTTP, JMS, AMQP, or database can participate **later in the flow** via outbound handlers or gateways. Snapshot/streaming semantics remain governed by Debezium and the source database; adding a poller in Spring Integration does not turn query polling into transaction-log CDC.

## 10. Practical Design Scenarios

### Scenario A — Initializing a New Reporting Store

The `sales` database already holds 500,000 orders; the analytics team needs existing historical data plus future changes.

**Choice:** initial snapshot + streaming. The projection handles `r` via upsert, then applies `c/u/d`. Verify full table coverage, consistency, and row/amount reconciliation before publishing reports.

### Scenario B — Feeding a Target That Already Has a Trusted Baseline

The reporting store was already synced via another mechanism and only needs changes starting from a well-defined boundary.

**Choice:** a streaming-only/no-data snapshot mode supported by the connector if skipping existing rows is acceptable. Verify the handoff boundary, target data, and log retention; if the baseline is incomplete, unchanged records will not appear on their own.

### Scenario C — Adding a Products Table After Three Months in Production

The connector is already streaming `orders`, and now needs `products` without halting the orders pipeline.

**Choice:** update the capture table/schema lists per connector procedure; if supported, trigger an incremental snapshot for `products`. Check permissions, primary keys, schema history, signal settings, snapshot progress, and downstream `r` handling.

### Scenario D — Sink Failure Right After Snapshot Completes

Debezium has emitted all 500,000 `r` events to Kafka, but the reporting app has persisted only 420,000.

**Choice:** fix the consumer/sink issue, inspect the consumer group offset, and retry or replay from Kafka per policy. Never rush to delete Debezium offsets and re-snapshot the database: connector checkpoints do not represent consumer progress.

### Scenario E — Connector Stopped for Many Days

The saved source offset points to an old log position, but MySQL already purged those binlogs or PostgreSQL no longer retains the required WAL.

**Choice:** assess recovery feasibility and potential data gaps. A controlled reconciliation/resnapshot may be required; a simple restart cannot guarantee resumption. Monitor log retention and maximum recoverable downtime proactively.

## 11. Practice: Reasoning About Events and Final State

Consider the `orders` table when an initial snapshot begins:

| id | status |
|---:|---|
| 11 | NEW |
| 12 | PAID |

Assume the snapshot establishes a consistent log boundary at position `P`. While capturing, two transactions commit after `P`:

- `T1` updates `orders.id = 11` from `NEW` to `PAID`.
- `T2` deletes `orders.id = 12`.

After the snapshot ends, streaming reads those transactions.

**Questions:**

1. Which event types can appear for the two orders during the snapshot and streaming phases?
2. After applying them in proper logical order, what rows should exist in the final projection?
3. If the app receives `r` for order 11 again due to a retry, how do you prevent resending a "new order" email?
4. If using an incremental snapshot while streaming is active, what must be watched if an update occurs mid-chunk?

<details>
<summary>Solution Hints</summary>

1. The snapshot may emit `r(11, NEW)` and `r(12, PAID)`. Streaming then emits `u(11, PAID)` and `d(12)`. Kafka may also receive a separate tombstone for order 12 if enabled.
2. The final projection contains order 11 with status `PAID`; order 12 is deleted or marked deleted per sink policy.
3. Separate **state synchronization** from **business side effects**. `r` only upserts state without sending emails; for tasks requiring once-only effects, use appropriate deduplication or an outbox.
4. Rely on the incremental snapshot's window/collision resolution alongside ordered, idempotent sink processing so stale snapshot reads never overwrite newer updates.

</details>

**Extension:** keep the Debezium offset at `P`, while the consumer has already written order 11 before crashing. On restart, **two layers of replay** can occur: the connector replays change events if source offsets weren't flushed, and the consumer re-reads Kafka records if group offsets weren't committed. Ensure target data remains safe under both cases.

## 12. Pre-Production Checklist

- [ ] Determine whether you need to sync **existing state**, **new changes**, or both.
- [ ] Confirm the snapshot mode is actually supported by your connector/version; inspect current offset state.
- [ ] Choose a consistent snapshot mechanism suited to the database, data volume, and load capacity.
- [ ] Verify MySQL binlog / PostgreSQL WAL / replication slot retention across long snapshots and outages.
- [ ] When using incremental snapshots, verify suitable keys, chunk sizes, signals, and interleaved `r` handling with streaming.
- [ ] Build Spring Integration handlers distinguishing `r/c/u/d`, tombstones, schema evolution, and deserialization errors.
- [ ] Ensure projection upserts/deletes are idempotent; ACK Kafka consumers only based on actual processing outcomes.
- [ ] Monitor snapshot progress, source lag, Kafka consumer lag, target record counts, and end-to-end latency.
- [ ] Rehearse restarts mid-snapshot, mid-streaming, and right after writing target data before committing consumer offsets.
- [ ] Maintain a controlled reconciliation/resnapshot runbook when offsets or source logs become invalid.

**Core Point:** snapshots deliver an **initial state image** (or a portion needing resynchronization), whereas streaming delivers the **committed change stream** that keeps that image up to date. Debezium bridges the two phases using log positions and connector state; Spring Integration moves each message through `MessageChannel`s to target systems with proper business logic and replay tolerance.
