# Batch, CDC, and Real-Time Streaming Ingestion

> **Chapter:** Data Platform  
> **Scope:** Architecting cloud applications from business requirements to networking, compute, data, and deployment models. This lesson focuses on data ingestion via batch, Change Data Capture (CDC), and streaming, along with trade-offs in latency, correctness, reliability, security, cost, and operations from a Well-Architected perspective.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish batch ingestion, CDC, and streaming by source, latency, volume, ordering, and business objective.
2. Design ingestion flows from source systems through landing/raw, processing, curated storage, and consuming systems.
3. Choose between polling, log-based CDC, event brokers, and scheduled batch based on source capabilities.
4. Understand at-most-once, at-least-once, and exactly-once semantics; design idempotency, deduplication, checkpointing, and replay.
5. Manage schema evolution, invalid data, event ordering, late-arriving data, and backfills.
6. Evaluate security, access control, data quality, recoverability, and total cost of ownership (TCO) for ingestion.

## 1. Why Design Data Ingestion Flows?

A cloud data platform ingests data from many sources: transactional databases, applications, SaaS platforms, IoT devices, partner files, logs, and legacy systems. These sources vary in protocol, generation rate, export capabilities, data quality, and security requirements.

For example, a booking platform needs to pull service catalogs and reconciliation data from an ERP every night; sync bookings and payments to a warehouse within minutes; analyze user behavior for near-real-time fraud alerting; ingest daily partner files; and retain change history for auditing or report reproduction.

Poor ingestion design can cause data to arrive too late, overload source databases, lose or duplicate events, apply updates out of order, leak sensitive data, or drive unpredictable cloud costs.

**Batch, CDC, and streaming are not mutually exclusive replacements for one another.** A real-world architecture often combines all three depending on data type and use case.

## 2. Three Primary Ingestion Approaches

### 2.1. Batch Ingestion

Batch collects data over a time window or a set of files and processes it as a single unit of work. Examples include running ETL daily at 01:00, ingesting hourly partner CSV files, or syncing transactional data using a watermark.

Characteristics:

- Latency is typically minutes, hours, or days; micro-batch can run more frequently.
- Easy to process large datasets via scans, sorts, joins, and aggregations.
- Resources can be scheduled efficiently, leveraging low-traffic source windows.
- Generally straightforward to backfill and reprocess by partition or time range.
- Requires handling duplicate files, missing files, modified/deleted records, and watermarks.

Batch fits periodic reporting, reconciliation, historical data, partner files, and cases where bounded staleness is acceptable to the business.

### 2.2. CDC — Change Data Capture

CDC captures changes occurring in a data source, usually from the database's transaction log, and forwards them downstream. A change record can represent an insert, update, or delete, along with log position, timestamp, primary key, and source metadata.

Two common approaches:

- **Log-based CDC:** reads the transaction log or replication log. Usually avoids full table scans and can capture deletes if supported by the connector.
- **Query/polling-based CDC:** periodically queries changed records using `updated_at`, a version column, or a watermark. Simpler to implement for some sources, but can miss hard deletes, relies on timestamps, and adds query load.

CDC fits syncing databases to a data lake/warehouse, updating read models, caches, search indexes, or near-real-time system integration.

**CDC does not automatically equal complete business events.** A row update alone may not explain business intent: did a booking transition from `PENDING` to `CONFIRMED` because the customer paid or because support staff manually edited it? Consumers must understand change record semantics.

### 2.3. Streaming — Event Stream Processing

Streaming processes events continuously, typically flowing through a message broker or event streaming platform. Consumers read events as they arrive, track offsets/checkpoints, and update target systems.

Examples: `BookingCreated`, `PaymentAuthorized`, `InventoryReserved`; web/mobile clickstreams; telemetry; IoT; security logs; and alerting signals.

Streaming fits scenarios where the business requires rapid reaction, continuous processing, event-time analytics, alerting, or fan-out to multiple consumers. In return, the system must handle duplicates, ordering, late events, backpressure, schema evolution, partitioning, and replay.

### 2.4. High-Level Comparison

| Criterion | Batch | CDC | Streaming |
| --- | --- | --- | --- |
| Unit of processing | Files, partitions, record sets | Change records from database | Continuous events/messages |
| Typical latency | Minutes to days | Seconds to minutes depending on connector | Milliseconds to minutes depending on system |
| Typical sources | Files, exports, snapshots, APIs | Transaction logs or query watermarks | Brokers, event producers, telemetry |
| Load on source | Can spike on schedule | Log-based generally avoids full scans | Producers emit continuously |
| Ordering | By partition/file or processing logic | Usually per log/partition; no global order | Usually guaranteed only within a partition/key |
| Reprocessing | By file, partition, or time range | By log offset/snapshot and connector state | Replay by offset/retention or archive |
| Delete handling | Needs tombstones, soft deletes, or reconciliation | Can capture deletes if connector supports it | Producer must emit delete events |
| Best suited for | BI, reconciliation, history, partner files | Synchronizing database state | Event reaction, near-real-time analytics |
| Complexity | Low to medium | Medium to high | Medium to high |

There is no universal latency threshold for classification. Define the business **freshness objective** before selecting technology.

## 3. Cloud Reference Ingestion Architecture

A general-purpose platform can be structured into the following layers:

1. **Sources:** transactional databases, SaaS, files, applications, IoT, partner systems.
2. **Capture/connectors:** batch extractors, CDC connectors, event producers/consumers.
3. **Transport:** object storage landing, message brokers, event streaming platforms, or managed transfer services.
4. **Raw/landing zone:** retains received data and metadata sufficient for audit/replay.
5. **Processing:** validate, normalize, deduplicate, enrich, transform, route, and quarantine.
6. **Curated storage:** lakehouse, warehouse, search/read models, or operational stores.
7. **Consumers:** dashboards, BI, machine learning, APIs, alerting, and downstream applications.
8. **Control/observability:** schema registry, orchestration, catalog, lineage, IAM, metrics, logs, and audits.

~~~mermaid
flowchart LR
    subgraph SRC["Sources"]
      DB[("OLTP database")]
      FILE["Files / partner export"]
      APP["Application events"]
      EXT["SaaS / external APIs"]
    end
    subgraph CAP["Capture"]
      CDC["CDC connectors"]
      BATCH["Batch extractor"]
      PRODUCER["Event producers"]
    end
    DB --> CDC
    FILE --> BATCH
    EXT --> BATCH
    APP --> PRODUCER
    subgraph TRANS["Transport"]
      BROKER["Event broker / stream"]
      LAND[("Object storage landing")]
    end
    CDC --> BROKER
    PRODUCER --> BROKER
    BATCH --> LAND
    BROKER --> LAND
    subgraph PROC["Processing"]
      VALID["Validate / schema / deduplicate"]
      TRANSFORM["Normalize / enrich / aggregate"]
      QUAR["Quarantine / DLQ"]
    end
    LAND --> VALID
    BROKER --> VALID
    VALID -->|"Valid"| TRANSFORM
    VALID -->|"Invalid"| QUAR
    TRANSFORM --> CUR[("Curated lake / warehouse")]
    TRANSFORM --> READ["Operational read model"]
    CUR --> BI["BI / ML / analytics"]
    READ --> API["Application APIs"]
~~~

This is a conceptual architecture. Not every flow needs both object storage and a broker simultaneously. You can batch directly into a warehouse, run CDC into a broker, or stream directly into a processing engine and archive raw data based on replay and audit needs.

### 3.1. Control Plane vs. Data Plane

- **Data plane** moves and processes actual data: connectors, brokers, object storage, compute, and sinks.
- **Control plane** manages pipeline configs, schemas, permissions, schedules, checkpoints, catalogs, lineage, and policies.

When the control plane fails, the data plane may keep running for some time using existing configurations and checkpoints; however, deploying new pipelines, schema changes, or recovery operations can be impacted. Design appropriate backups and HA for metadata/control state.

## 4. Designing Batch Ingestion

### 4.1. Snapshots, Incremental Loads, and Watermarks

Three common patterns:

- **Full snapshot:** loads the entire dataset each run. Easy to understand and verify, but expensive in time, bandwidth, and source load on large tables.
- **Incremental load:** extracts only new/changed data since a saved watermark.
- **Partitioned batch:** splits data by day, month, tenant, or partition key for parallel processing and targeted reruns.

Example incremental load using `updated_at`:

~~~sql
SELECT id, customer_id, status, updated_at
FROM booking
WHERE updated_at > :last_successful_watermark
  AND updated_at <= :upper_bound
ORDER BY updated_at, id;
~~~

Caveats with this approach:

- Timestamps can collide; use a secondary key like `id` for deterministic ordering.
- Late-updated rows or clock skew can fall outside the window.
- Physical deletes will not appear in this query.
- In-flight transactions may commit after the upper-bound watermark is chosen.
- Use an appropriate overlap window and idempotent upserts to catch late-arriving records.

Do not advance the watermark just because a job started. Advance the watermark only after the corresponding batch is processed, validated, and committed successfully.

### 4.2. Manifests and File Completion

For file ingestion, avoid processing a file while the producer is still writing it. A helpful convention:

1. Producer writes to a temporary path or performs multipart upload.
2. Once upload completes, producer emits a manifest or completion marker.
3. Manifest contains file name, size, checksum, schema version, record count, source, and creation timestamp.
4. Consumer processes only completed files; verifies checksum and size.
5. Writes output using a stable `batch_id` to prevent duplicate ingestion.

Example manifest:

~~~json
{
  "batch_id": "partner-2026-11-18-001",
  "source": "partner_booking",
  "schema_version": 3,
  "object_uri": "s3://example-landing/partner/2026/11/18/data-001.parquet",
  "record_count": 125000,
  "checksum": "sha256:example",
  "created_at": "2026-11-18T01:00:00Z"
}
~~~

Illustrative data. Never include secrets or raw PII in a manifest if metadata is shared more broadly than the underlying data object.

### 4.3. Orchestration and Scheduling

~~~mermaid
flowchart TD
    A["Receive file / snapshot"] --> B["Verify manifest and checksum"]
    B --> C["Validate schema and data"]
    C --> D["Load staging"]
    D --> E["Merge/upsert curated tables"]
    E --> F["Reconcile counts / quality checks"]
    F --> G["Commit watermark and mark complete"]
    C -->|"Invalid"| Q["Quarantine + alert"]
    D -->|"Failure"| R["Retry / resume by batch_id"]
~~~

The orchestrator should support retries, timeouts, dependencies, concurrency limits, backfills, parameterization, and auditing. Prevent two runs on the same partition from writing concurrently without locking or safe upsert mechanisms.

### 4.4. Pros and Cons of Batch

Batch is straightforward to implement and validate per dataset, though freshness depends on the schedule. Large jobs can create load spikes on sources or target warehouses; if a job fails near the end, re-running everything is costly. Partitioning and checkpointing keep reprocessing bounded.

## 5. Designing CDC

### 5.1. How Does Log-Based CDC Work?

Databases record transactional mutations in a transaction log to support recovery and replication. A CDC connector reads this log, parses mutations, and emits records to a broker or sink.

~~~mermaid
flowchart LR
    APP["Application writes transaction"] --> DB[("Primary database")]
    DB --> LOG["Transaction log / WAL / binlog"]
    LOG --> CDC["CDC connector"]
    CDC --> BR["Broker / stream"]
    BR --> SINK["Warehouse / search / read model"]
    CDC --> STATE[("Connector offset / schema state")]
~~~

Metadata may include operation type, key, before/after images, source database/table, transaction ID, log sequence/offset, timestamp, and schema version. Field names and semantics vary across connectors; never assume every source provides a before image.

### 5.2. Initial Snapshots and Streaming Changes

When initializing CDC, systems typically need an **initial snapshot** to capture current state, then resume streaming changes from the corresponding log position. Snapshots and change streams must coordinate so there are no gaps or unintended duplicates.

Clarify the following:

- At which point-in-time/LSN is the snapshot taken?
- Does the connector record the log position before, during, or after the snapshot?
- How are updates occurring during the snapshot read handled?
- On restart, do checkpoints/state persist so streaming can resume?
- If log retention expires, is a re-snapshot or archive recovery required?

A healthy connector status does not guarantee zero data loss. Always monitor offsets, lag, transaction log retention, snapshot state, schema history, and sink acknowledgements.

### 5.3. Polling-Based CDC via Timestamps

If a source lacks log-based CDC support, you can poll records using `updated_at` or a version column. This is simpler, but:

- Cannot capture hard deletes without tombstones or an audit table.
- Multiple updates sharing a timestamp can be skipped if the watermark relies solely on timestamps.
- Repeated polling queries can increase source database load.
- Audit columns might be missing or bypassed by certain write paths.

You can use soft deletes, change tables, sequences/versions, or overlap windows; verify that every write path honors these conventions.

### 5.4. CDC Does Not Automatically Generate Domain Events

Row-level updates represent data state, not necessarily business events. For example, CDC shows `booking.status` changing from `HELD` to `CONFIRMED`; a `BookingConfirmed` domain event might be emitted only after payment, reservation, and ownership rules are validated.

If consumers need explicit business semantics, prefer application/domain-published event contracts. If you need data synchronization or lakehouse ingestion, CDC fits better. Both can be used together for distinct purposes.

### 5.5. Log Retention and Connector Lag

If a connector stops long enough for the required transaction logs to be purged or recycled, CDC may be unable to resume from its old offset. You must:

- Monitor connector lag and log position relative to retention limits.
- Alert before lag approaches the safety margin.
- Define procedures to extend retention, recover connectors, or trigger re-snapshots.
- Plan capacity for brokers, sinks, and networking.
- Rehearse connector restarts, network partitions, and sink outages.

Do not set log retention to infinite: large transaction logs increase storage usage and can impact source database operations.

## 6. Designing Streaming/Event Ingestion

### 6.1. Producers, Brokers, and Consumers

Producers emit events, brokers store/route them, and consumers process them. Brokers typically provide partitioning, replication, retention, consumer groups, acknowledgements, and security controls.

~~~mermaid
flowchart LR
    P1["Booking producer"] --> TOP["Topic: booking-events"]
    P2["Payment producer"] --> TOP
    TOP --> CG1["Consumer group: analytics"]
    TOP --> CG2["Consumer group: notification"]
    TOP --> CG3["Consumer group: fraud"]
    CG1 --> DWH[("Warehouse")]
    CG2 --> MSG["Notification service"]
    CG3 --> ALERT["Fraud alerts"]
~~~

Consumer groups typically maintain independent offsets, allowing multiple consumers to read the same stream independently. Consumer parallelism is bounded by partition count and ordering semantics.

### 6.2. Event Contracts

A well-designed event should include:

- A unique `event_id` that remains stable across retries of the same event.
- `event_type`, schema version, `occurred_at`, and `source`.
- Aggregate/entity key for partitioning and scoped ordering.
- Minimal payload needed by consumers; avoid secrets and unnecessary PII.
- Correlation ID/causation ID for distributed tracing.
- Schema compatibility rules and version deprecation timelines.

Example:

~~~json
{
  "event_id": "evt-8f14",
  "event_type": "BookingConfirmed",
  "event_version": 2,
  "occurred_at": "2026-11-18T03:20:00Z",
  "producer": "booking-service",
  "aggregate_type": "booking",
  "aggregate_id": "bkg-204",
  "correlation_id": "req-91ac",
  "tenant_id": "tenant-08",
  "data": {
    "booking_id": "bkg-204",
    "status": "CONFIRMED",
    "currency": "VND"
  }
}
~~~

Illustrative data. Tenant ID and business data should only be emitted when necessary, classified, and authorized by the data contract.

### 6.3. Partition Keys and Ordering

In a partitioned stream, brokers typically guarantee ordering only within a single partition, not across the entire topic. If per-booking change order matters, use `booking_id` as the partition key so events for the same booking route deterministically.

Trade-offs:

- Skewed keys create hot partitions.
- Increasing partition count can alter key-to-partition mapping depending on the hashing algorithm, affecting order during migration.
- A consumer group generally cannot parallelize beyond the number of available partitions.
- Global ordering limits parallelism and is rarely needed across all business domains.

Enforce ordering only within the scope the business truly requires.

### 6.4. Event Time, Processing Time, and Watermarks

- **Event time:** when the event actually occurred at the source.
- **Processing time:** when the system processes the event.
- **Ingestion time:** when the platform receives the event.

These three timestamps diverge due to network latency, offline producers, clock skew, or backlogs. Windowed analytics must specify whether calculations use event time or processing time.

Streaming engines can use watermarks to estimate event-time completeness within a window. Events arriving after the watermark may be dropped, routed to a side output, or used to emit updated results depending on engine policy.

For example, hourly revenue aggregations might receive payment events delayed by 10 minutes. A 15-minute watermark can balance result latency and late data; actual thresholds should reflect observed latency distributions and business needs.

Clarify whether late events can update already published aggregates, whether reports emit revision/correction records, whether overly late events go to quarantine/replay or batch reconciliation, and whether idle partitions can stall watermarks.

## 7. Delivery Semantics and Correctness

### 7.1. At-Most-Once, At-Least-Once, and Exactly-Once

| Semantics | Meaning | Trade-offs |
| --- | --- | --- |
| At-most-once | Messages may go unprocessed without retries under these semantics | Potential data loss; suited for non-critical metrics |
| At-least-once | Retries conditionally until acknowledged/checkpointed | Possible duplicates; consumers must be idempotent |
| Exactly-once | Guaranteed within a specific processing/commit boundary | Does not automatically span external databases, APIs, and side effects |

Always ask: **at which boundary is exactly-once guaranteed?** A stream processor can guarantee transactional processing between an input offset and an output topic within one ecosystem; it does not automatically guarantee an email is sent once or a payment gateway charges once.

Practical architectures typically rely on at-least-once delivery + idempotent processing + reconciliation rather than assuming cross-system exactly-once promises.

### 7.2. Idempotency and Deduplication

An idempotent operation produces the same final effect for the same logical input even if executed multiple times.

Consumers can store `processed_event_id` with a unique constraint inside the same transaction as the target data update. If a previously processed event arrives again, skip side effects and commit the acknowledgement cleanly.

Determine the uniqueness scope of the event ID, how long deduplication state is retained, whether database updates and processed markers share one transaction, how external APIs support idempotency keys, and whether replays are permitted to re-trigger emails, invoices, or payment charges.

### 7.3. Checkpoints and Offsets

Stream consumers maintain offsets/checkpoints. Recording a checkpoint before completing side effects risks data loss on crash; recording it afterward without idempotency risks duplicate processing.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant D as Target DB
    B->>C: Event at offset 101
    C->>D: Begin transaction
    C->>D: Check event_id / apply update
    C->>D: Commit data + processed_event_id
    C->>B: Commit offset 101
    Note over B,D: If crash before offset commit, event may be redelivered; consumer deduplicates
~~~

Not every broker and database can commit offsets and database changes in a single atomic transaction. Without distributed transactions, rely on idempotency, the outbox/inbox pattern, or reconciliation.

## 8. Schema Evolution and Data Contracts

Producers and consumers frequently deploy on independent schedules. Breaking schema changes can halt pipelines or corrupt downstream reads.

Principles:

- Enforce schema versioning and a review process.
- Prefer adding optional fields with sensible defaults while keeping existing semantics stable.
- Avoid deleting or changing types of fields actively used by consumers before migrations finish.
- Consumers should tolerate unknown fields where contracts allow.
- Check compatibility in CI, a schema registry, or the pipeline.
- Support multiple concurrent versions during transition periods.
- Retain raw payloads where needed for auditing/replay while controlling retention and security.

Version 1:

~~~json
{
  "booking_id": "bkg-204",
  "status": "CONFIRMED"
}
~~~

Version 2 adds optional `currency`:

~~~json
{
  "booking_id": "bkg-204",
  "status": "CONFIRMED",
  "currency": "VND"
}
~~~

Adding an optional field is generally far more compatible than changing `booking_id` from a string to an object or altering the meaning of `status`. Compatibility also depends on serialization format, defaults, consumer behavior, and schema registry policies.

A schema registry manages schemas and compatibility policies in many streaming platforms. A data contract is broader than a schema: it covers owners, business field meanings, classification, freshness SLAs, quality rules, retention, and access rights.

Do not validate only whether JSON parses. A negative `amount` is syntactically valid JSON yet invalid business data if transactions cannot be negative.

## 9. Data Quality, Quarantine, and Error Handling

Ingestion pipelines must clearly distinguish valid records, records repairable under controlled rules, and records requiring isolation.

Validation layers:

- **Schema validation:** required fields, data types, enums, versions.
- **Completeness:** no missing primary keys, timestamps, sources, or partitions.
- **Uniqueness:** business keys or event IDs do not duplicate outside policy.
- **Validity:** values within allowed domains; valid timestamps and currencies.
- **Referential integrity:** referenced entities exist or follow a late-arrival policy.
- **Freshness:** data arrives within SLA.
- **Volume/anomaly:** unexpected record counts, null rates, or value distributions.
- **Reconciliation:** comparing record counts/monetary totals with source systems.

### 9.1. DLQ and Quarantine

Events that still fail after bounded retries can be routed to a dead-letter queue (DLQ) or quarantine store along with metadata: error details, event ID, source, offset, schema version, timestamp, and retry count.

Guidelines:
- Retry transient failures with backoff and jitter; never infinitely retry invalid data.
- Store payloads under strict access controls; avoid turning DLQs into unmonitored PII dumps.
- Maintain dashboards tracking DLQ volume, record age, and error categories.
- Establish procedures to fix data/schemas and execute controlled replays.
- Mark replayed records, maintain audit trails, and prevent duplicate side effects.

A single poison message can trap a consumer on the same offset indefinitely. Use bounded retries, DLQs, partition pausing with alerts, or record-level isolation depending on broker/engine capabilities. Skipping errors requires explicit policy to prevent silent data loss.

## 10. Backpressure, Throughput, and Capacity

Backpressure regulates producers/consumers when processing rates fall out of balance. If producers outpace consumers, backlogs grow, data ages, and storage/retention fills up.

Monitor producer rates, consumer throughput, consumer lag by count and time, oldest message age, partition skew, hot keys, retries, DLQ growth, broker disk, network, and sink saturation.

Hypothetical example: producers generate an average of 5,000 events/second at 2 KB each:

\[
R_{\text{raw}} = 5{,}000 \times 2\text{ KB} = 10\text{ MB/s}
\]

In one hour, raw payload volume is approximately:

\[
10\text{ MB/s} \times 3{,}600\text{ s} = 36{,}000\text{ MB} \approx 36\text{ GB}
\]

This excludes protocol overhead, replication, compression, indexes, and metadata. With a replication factor of 3, physical broker storage usage can be substantially higher.

If consumers process 3,000 events/second, backlog grows by 2,000 events/second—accumulating roughly 1.2 million events in 10 minutes. Plan capacity, load-shedding policies, consumer scaling, buffers, and alerts before retention runs out.

Mitigations:
- Scale consumer parallelism within partition and sink limits.
- Optimize per-record processing, batch commits, and I/O.
- Increase partition counts when key distribution and ordering allow.
- Size broker capacity and retention to cover expected outage and recovery times.
- Apply producer throttling, quotas, or prioritize critical streams.
- Scale sinks/databases to match sustained load.
- Isolate low-priority telemetry from transactional event streams.
- Use circuit breakers/backpressure instead of unbounded in-memory buffers.

Consumer autoscaling only works if partition counts allow scaling, sinks are not bottlenecked, and workers initialize quickly enough.

## 11. Security and Data Governance in Ingestion

Data crosses multiple trust boundaries: sources, connectors, brokers, object storage, processing engines, catalogs, and consumers.

Essential controls:

1. **Identity and least privilege:** connectors read only required tables/logs; consumers read only authorized topics/buckets; sinks write only to approved destinations.
2. **Encryption:** TLS in transit and encryption at rest for brokers, object storage, checkpoints, schema registries, and backups.
3. **Secret management:** retrieve database credentials, API keys, and certificates from a secrets manager with rotation and auditing.
4. **Data classification:** tag PII, payment, and confidential fields; minimize payloads or apply masking/tokenization as appropriate.
5. **Data residency:** verify regions across sources, brokers, landing zones, processing, backups, logs, and DR.
6. **Network isolation:** private endpoints, egress allowlists, VPC/VNet segmentation, security groups, and firewalls.
7. **Auditing:** log who reads, writes, alters schemas, replays, exports, or modifies pipelines.
8. **Retention/deletion:** enforce retention limits, deletion workflows, and legal holds across raw archives, DLQs, logs, and replay stores.
9. **Tenant isolation:** enforce authenticated tenant context, partitioned buckets/topics, and policies; never trust client-supplied `tenant_id` blindly.

CDC captures before/after row images that may contain sensitive data. Event streams persist for the full retention period, requiring careful access and storage controls.

~~~mermaid
flowchart LR
    S["Database source\nPII / payment"] --> C["Connector identity\nleast privilege"]
    C --> B["Private broker\nTLS + encryption"]
    B --> P["Processing\nvalidate / mask"]
    P --> R[("Raw restricted zone")]
    P --> K[("Curated zone")]
    R --> AUD["Catalog / lineage / audit"]
    K --> CONS["Authorized consumers"]
~~~

Masking during processing does not remove the obligation to secure the raw landing zone if raw payloads still contain PII.

## 12. Reliability, Recovery, and Replay

Failure modes to plan for:

- Source database failover, transaction log rotation, or connector losing its log position.
- Broker node/partition loss or disk exhaustion.
- Consumer crash after writing to the sink but before committing its offset.
- Sink throttling or write failures.
- New schema incompatible with older consumers.
- Network partitions causing message redelivery.
- Pipeline executing the same batch/partition twice.
- Producers emitting duplicate or out-of-order events.

Recovery design:

- Persist checkpoints/offsets and back up recoverable connector metadata.
- Retain raw archives long enough to support policy-defined replays.
- Size broker retention based on expected outage and backfill durations.
- Build idempotent sinks using upserts keyed by business key/version/event ID.
- Isolate replays from live traffic when necessary to avoid exhausting capacity.
- Reconcile against sources to detect gaps and corrupted records.
- Rehearse connector, broker, sink, and regional failures.
- Measure pipeline RTO/RPO separately from freshness; do not conflate them into one platform metric.

Replay is not always safe. It can re-trigger side effects like sending emails, charging payments, placing orders, calling partner APIs, or billing. Separate projection-only consumers that can safely rerun from side-effecting consumers that need dedicated idempotency or replay modes.

When backfilling, write to separate namespaces/topics/outputs or versioned tables if appropriate; validate results before replacing live production datasets.

## 13. Choosing Batch, CDC, or Streaming by Business Goal

| Need | Initial Recommended Fit | Rationale / Checks Required |
| --- | --- | --- |
| End-of-day financial reports | Batch | Complete daily reconciliation; cleanly rerunnable |
| Syncing bookings to data lake within minutes | Log-based CDC | Avoids polling; requires schema, log retention, snapshot plan |
| Fraud alerts as transactions occur | Streaming events | Fast reaction; needs event contract and late-event policy |
| Hourly partner file ingestion | Batch/micro-batch | Manifest, checksum, duplicate detection |
| Syncing search index after profile edits | CDC or domain events | Choose based on semantics and history requirements |
| Dashboards updating every 15 minutes | Micro-batch or CDC | Weigh continuous stream cost against freshness needs |
| Near-real-time clickstream analytics | Streaming | High throughput, event-time, and backpressure |
| Multi-year historical data backfill | Batch | Partitioning, source rate limiting, and checkpointing |
| Signaling when a booking is confirmed | Domain event | Clearer business semantics than row-level CDC |

Do not pick streaming simply because data needs to be fresh. If a 15-minute dashboard refresh suffices, batch or micro-batch is often cheaper and simpler to operate. Conversely, if fraud decisions must happen before authorizing a payment, hourly batch will not meet requirements.

## 14. Real-World Scenario: Booking and Analytics Platform

### 14.1. Sources and Requirements

A booking platform has a Booking DB, a Payment DB, daily logistics partner CSV files, web/mobile clickstreams generating thousands of events/second during campaigns, and an ERP providing scheduled catalogs/reconciliation data.

Requirements:
- Booking operations dashboards must update within a few minutes.
- Fraud alerts must trigger within seconds.
- Financial reports must complete after end-of-day reconciliation.
- Transactional databases must not be overloaded.
- Source data must be retained sufficiently for audits and pipeline error replays.

### 14.2. Hybrid Architecture

~~~mermaid
flowchart TB
    DB1[("Booking DB")] --> CDC1["Log-based CDC"]
    DB2[("Payment DB")] --> CDC2["Log-based CDC"]
    CDC1 --> BROKER["Managed stream / broker"]
    CDC2 --> BROKER
    CLICK["Web/mobile clickstream"] --> BROKER
    ERP["ERP API"] --> BATCH["Scheduled extractor"]
    PARTNER["Partner CSV"] --> LAND[("Object storage landing")]
    BATCH --> LAND
    BROKER --> RAW[("Raw event archive")]
    BROKER --> RT["Stream processing"]
    RT --> FRAUD["Fraud alerts"]
    RT --> OPS[("Operational analytics store")]
    LAND --> BATCHPROC["Batch validation / transform"]
    RAW --> BATCHPROC
    BATCHPROC --> WH[("Warehouse / lakehouse")]
    OPS --> DASH["Operations dashboard"]
    WH --> BI["Financial / BI reports"]
~~~

### 14.3. Rationale Behind Choices

- **Booking/Payment:** CDC updates data state within minutes and builds raw history. Requires PII filtering, delete handling, and an explicit allowlist of captured tables.
- **Clickstream:** streaming handles continuous traffic and fraud alerts. Requires entity/session partitioning per ordering needs, event IDs, sampling, and retention.
- **ERP/CSV:** scheduled batch simplifies reconciliation and file tracking; manifests catch missing/duplicate files.
- **Operational dashboards:** consume CDC/events and update read models; explicitly surface freshness and late-data possibilities.
- **Financial reports:** rely on batch reconciliation against authoritative sources rather than summing raw event streams alone when audit-grade accuracy is required.

### 14.4. Illustrative Metrics and Verification Tests

| Assumed Target | Verification Method |
| --- | --- |
| CDC lag p95 under 2 minutes | Compare source commit time vs. sink availability under normal/peak load |
| Fraud alerts under 5 seconds from event time | End-to-end timestamps under peak traffic |
| Zero missed files with completion markers | Manifest/checksum/record-count reconciliation |
| Zero duplicate booking/payment projections on replay | Duplicate/restart/replay tests |
| Zero unauthorized PII exposure | IAM negative tests and access audits |
| Recovery within approved RTO/RPO | Broker/sink outage and restore/replay drills |

These thresholds are exercise assumptions that Product, Security, and SRE must validate before adopting them as formal SLOs or acceptance criteria.

## 15. Cost and Trade-Offs of the Ingestion Platform

Costs include connector compute/licensing; broker throughput, partitions, storage, replication, and retention; object storage; batch/stream compute; cross-region/network egress; schema registry, catalog, monitoring, logs, and auditing; backfills, replays, DLQs, and operational effort.

\[
TCO = C_{\text{capture}} + C_{\text{transport}} + C_{\text{storage}}
+ C_{\text{processing}} + C_{\text{network}} + C_{\text{governance}}
+ C_{\text{operations}}
\]

| Approach | Major Cost Drivers | Optimization Levers |
| --- | --- | --- |
| Batch | Per-job compute, scans, storage, schedule frequency | Partition pruning, incremental loads, compression |
| CDC | Connectors, brokers, source log retention, sinks | Capture only required tables, tune snapshots, monitor lag |
| Streaming | Brokers, retention, partitions, continuous compute | Right-size partitions, micro-batching, use-case retention |
| Hybrid | Multiple semantics/tooling, duplicate storage | Standardize contracts, catalogs, IAM, and observability |

Continuous streaming requires persistent capacity and operations; if freshness objectives allow wider windows, batch can be more cost-effective. No universal cost conclusion applies without knowing throughput, retention, replication, managed-service pricing, and compute models.

FinOps should track daily bytes captured/brokered/replicated; raw scan frequency during backfills; cross-region egress; consumer lag duration; which datasets genuinely need long-term raw retention; cost per GB and cost per million events; and which telemetry can reduce sampling or retention.

## 16. Observability and Pipeline Operations

Pipelines require SLOs for freshness, data integrity, and recoverability.

| Category | Metrics / Signals | Purpose |
| --- | --- | --- |
| Source | Log position, source latency, query load, log retention | Is the source impacted or is the connector about to lose log access? |
| Capture | Connector status, snapshot progress, lag, error count | Are changes being read completely? |
| Broker | Throughput, partition skew, storage, replication, oldest age | Is transport stable with sufficient headroom? |
| Consumer | Consumer lag, processing latency, retries, checkpoint age | Is downstream keeping up? |
| Quality | Schema failures, null/duplicate rates, rejected records | Is data accurate and complete? |
| Sink | Commit duration, write failures, throttling, reconciliation | Is data landing properly? |
| Freshness | Event time vs. availability time | Is new data meeting SLA? |
| Cost | Cost/GB, cost/million events, storage growth | Are costs trending abnormally? |
| Security | Unauthorized access, secret rotation, policy violations | Is data properly protected? |

Never alert solely on event lag count. A lag of 100,000 events may be normal at high throughput, whereas 100 events delayed by 30 minutes can signal a severe incident. Track both record lag and **age of the oldest unprocessed event**.

Minimum runbooks:
- Connector stopped: check credentials, source log retention, schema changes, networking, and checkpoints.
- Broker backlog: inspect producer rates, consumer throughput, partition skew, storage, and sink throttling.
- Schema incompatibility: identify producer/consumer versions, halt rollout if needed, route invalid records, and fix the contract.
- Sink outage: bound retries/apply backpressure, retain messages within broker retention, ensure offsets are not falsely committed.
- Growing DLQ: categorize errors, isolate poison messages, fix data/schemas, and execute approved replays.
- Data mismatch: halt publishing erroneous reports, reconcile against source, identify affected windows, and run backfills.
- Regional failure: restore metadata, connector state, and brokers/landing per RTO/RPO, then check for gaps.

Every pipeline needs a technical owner, business owner, source of truth, consumers, classification, schema, freshness SLA, retention policy, and runbook. Lineage identifies which tables/dashboards depend on a given field or source when changes occur.

## 17. Sample Architecture Decision Record

~~~markdown
# ADR-052: Combining CDC and Batch for the Booking Data Platform

Status: Proposed / Conditionally Approved
Decision owner: Data Architect + Product + SRE
Date: YYYY-MM-DD

Context:
- Booking/Payment need to sync to analytics within a few minutes.
- Fraud alerts require rapid reaction to click/payment events.
- ERP and partners deliver reconciliation data on a schedule.
- Large scan loads on OLTP databases are prohibited.

Options:
A. Batch for all sources.
B. CDC for databases, streaming for events, batch for files/ERP.
C. Streaming for all data.

Decision:
- Select Option B; retain raw archives sufficiently for replay and audit.
- CDC captures only required tables; business events use dedicated contracts.
- Batch reconciliation serves as the verification baseline for financial reports.

Trade-offs:
- Operating multiple pipelines and delivery semantics.
- Requires schema management, deduplication, replay, and data lineage.

Acceptance Evidence:
- CDC lag and freshness meet approved SLOs.
- Zero data loss or duplication during restarts and replays.
- No overload on OLTP sources.
- Data quality/reconciliation meets criteria.
- TCO across steady state, peak, and backfill stays within budget.

Review Triggers:
- Freshness objectives change; source database changes;
  log retention becomes insufficient; costs or consumer count spike sharply.
~~~

The ADR should explicitly document exactly-once/at-least-once boundaries, captured datasets, access approvers, and re-snapshot procedures.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using batch for sub-second/second-level reactions | Alerts/decisions arrive too late | Define freshness objectives; use event/stream processing when needed |
| Using streaming for daily-only reports | Unnecessary cost and operational overhead | Use batch/micro-batch with reconciliation |
| Assuming CDC equals domain events | Consumers misinterpret business intent | Separate row mutations from business events |
| Relying solely on timestamps as watermarks | Skips records with identical timestamps or late commits | Compound cursors, overlap windows, versions, and reconciliation |
| Ignoring deletes | Downstream retains deleted records | Tombstones, soft deletes, or reconciliation |
| Committing offsets before sink commits | Crashes cause silent data loss | Enforce transaction boundaries, idempotency, and commit order |
| Skipping deduplication | Inflated metrics or duplicate side effects | Stable event IDs, inbox/unique constraints |
| Assuming end-to-end exactly-once everywhere | Duplicate emails/payments/API side effects | Clarify boundaries, add idempotency and reconciliation |
| Ignoring source log retention | CDC loses its log position | Alert on lag and rehearse re-snapshots |
| Lacking schema governance | Consumers break after upstream changes | Data contracts, compatibility tests, versioning |
| Infinite retries on poison messages | Partitions stall and backlogs grow | Bounded retries, DLQs, and quarantine |
| Ignoring late-arriving events | Inaccurate time-window reports | Event-time processing, watermarks, and correction policies |
| Monitoring only record lag count | Hours-old stuck events go unnoticed | Monitor oldest unprocessed event age and freshness |
| Unrestricted raw zone access | Uncontrolled PII sprawl | Classification, IAM, encryption, and retention |
| Replaying directly to side-effecting production paths | Re-sends notifications or charges | Replay modes, idempotency, and isolated projections |
| Skipping source reconciliation | Green pipelines producing wrong numbers | Count/total reconciliation and quality checks |

## 19. Practice Exercise

An e-commerce platform has three sources: a PostgreSQL orders database, a web application emitting clickstreams, and a logistics partner sending CSV files every 30 minutes. Product wants operations dashboards refreshed within 2 minutes; Fraud requires alerts within 5 seconds; Revenue reporting requires accurate end-of-day reconciliation. The orders database must not experience continuous full table scans.

Complete the following:

1. Classify each feed as batch, CDC, or streaming and explain why.
2. Diagram the architecture: source → capture → broker/landing → process → curated → consumers; distinguish the data plane and control plane.
3. Propose an event contract with `event_id`, `event_type`, `version`, `occurred_at`, entity key, and correlation ID.
4. Design incremental batch ingestion with watermarks, duplicate file handling, and deletes.
5. Describe snapshot + log-based CDC; identify conditions where the connector can lose its log position and how to recover.
6. Define at-least-once delivery, idempotency, checkpointing, and replay for a side-effecting consumer.
7. Design schema evolution and DLQ/quarantine; outline the controlled replay workflow for failed records.
8. Estimate throughput, backlog, and retention using explicit data assumptions.
9. List IAM, encryption, tenant isolation, data residency, and retention controls.
10. Set SLIs/SLOs for freshness, data quality, CDC lag, consumer lag, and reconciliation.
11. Compare TCO across batch-only, CDC + streaming, and hybrid architectures.
12. Write an ADR covering assumptions, residual risks, alternatives, owners, and review triggers.

**Self-assessment criteria:** a strong solution does more than move data fast. It proves data is accurate, complete, traceable, and safely rerunnable; protects sources from overload; safeguards sensitive data; and meets freshness targets at acceptable cost and operational complexity.

## 20. Production Readiness Checklist

- [ ] Every source has an owner, source of truth, and verified access permissions.
- [ ] Freshness objectives, SLOs, volumes, and retention are agreed upon by Product, Data, and SRE.
- [ ] Batch pipelines have manifests/checksums, watermarks, partitioning, retries, idempotent loads, and backfills.
- [ ] CDC pipelines have snapshot strategies, log position tracking, connector state, lag alerts, and re-snapshot plans.
- [ ] Streaming pipelines have event contracts, partition keys, ordering scopes, offsets/checkpoints, and backpressure.
- [ ] Delivery semantics are defined per boundary; consumers implement idempotency/deduplication.
- [ ] Schema evolution has compatibility testing, owners, and deprecation policies.
- [ ] Invalid data routes to quarantine/DLQ with auditing, retention, and controlled replay.
- [ ] Event-time, processing-time, watermarks, and late-arrival policies are explicit.
- [ ] Raw/curated storage enforces classification, IAM, encryption, retention, and lineage.
- [ ] Connectors/consumers have dashboards, logs, metrics, trace/correlation IDs, and runbooks.
- [ ] Fault testing covers source outages, broker outages, sink outages, duplicates, late data, and schema breaks.
- [ ] Reconciliation proves completeness and accuracy against sources.
- [ ] RTO/RPO, checkpoint backups, and replays have been rehearsed where applicable.
- [ ] TCO includes capture, transport, storage, processing, networking, governance, and operations.
- [ ] An ADR documents choices, assumptions, risks, trade-offs, and review triggers.

## Key Takeaways

**Batch** fits scheduled, set-based processing; **CDC** captures database mutations for near-real-time state synchronization; **streaming** processes continuous events for rapid reaction. These approaches combine naturally: CDC for OLTP changes, streaming for business events/clickstreams, and batch for files, backfills, and reconciliation.

Good ingestion design guarantees **the right data, at the right time, with the right permissions, and full recoverability**. Start from freshness, volume, semantics, and source constraints; then design contracts, checkpoints, idempotency, quality, security, observability, and TCO. Speed is only one dimension of data platform quality.
