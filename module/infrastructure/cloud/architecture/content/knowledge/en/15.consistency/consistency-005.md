# Transactional Outbox, Inbox, and CDC Synchronization

In cloud applications, a service frequently updates its own data while needing to notify other services. For example, Booking Service confirms a reservation in its database and then emits a `BookingConfirmed` event so Notification can send an email, Search can update its index, and Analytics can record the transaction. These two actions live in two separate systems: the database and the message broker. If the database commits successfully but the application stops before publishing, the data changed while the event never reaches consumers. If it publishes first and the database rolls back, consumers receive a notification for a change that never occurred.

This is the **dual-write** problem. Three techniques are commonly combined to solve it:

- **Transactional outbox:** writes the business change and the event record to be published within the same database transaction.
- **Transactional inbox / deduplication:** records processed events within the same transaction as the consumer's data changes, tolerating redelivered messages.
- **Change Data Capture (CDC):** detects data changes from a database—typically by reading the transaction log or a platform-provided change-capture mechanism—and forwards those changes to a broker or target system.

These techniques complement one another. The outbox ensures the intent to emit an event is saved alongside the source data; CDC can transport outbox records without continuous polling; the inbox lets consumers handle duplicates safely. They do not by themselves create an ACID transaction spanning multiple databases, nor do they inherently guarantee end-to-end exactly-once processing.

This lesson belongs to the **Consistency** chapter of the **CLOUD_ARCHITECTURE** module. When designing cloud application architectures, the goal is to keep business data accurate while services exchange events asynchronously, balancing reliability, security, scalability, cost, and operations with a Well-Architected mindset.

## 1. Learning objectives

After this lesson, learners will be able to:

1. Explain why dual-writing between a database and a broker can drop or emit false events.
2. Design a transactional outbox to persist business state and event records in the same transaction.
3. Design an inbox/deduplication mechanism so consumers safely handle duplicate or redelivered messages.
4. Distinguish transaction-log-based CDC from polling, triggers, and timestamp-based extraction.
5. Choose an appropriate outbox transport mechanism: polling publisher, CDC connector, or platform-native integration.
6. Handle ordering, replay, schema evolution, deletes/tombstones, snapshots, and checkpoints.
7. Design retries, reconciliation, observability, security, and recovery for event pipelines.
8. Evaluate consistency lag, correctness, and cost of the pattern in cloud architectures.

## 2. The dual-write problem: why two separate operations are unsafe

### 2.1. Update database then publish event

An intuitive implementation:

~~~text
1. UPDATE bookings SET status = 'CONFIRMED'
2. COMMIT database transaction
3. PUBLISH BookingConfirmed to broker
~~~

If the service crashes between steps 2 and 3, the booking is confirmed while consumers never receive the event. The search index, notifications, or downstream systems may never learn the change occurred.

### 2.2. Publish event then update database

Reversing the order does not solve the problem either:

~~~text
1. PUBLISH BookingConfirmed to broker
2. UPDATE bookings SET status = 'CONFIRMED'
3. COMMIT database transaction
~~~

If step 2 or 3 fails after the event was published, consumers may act on state that does not exist in the authoritative data source.

### 2.3. Dual-write failure matrix

| Database commit | Publish event | Outcome |
|---|---|---|
| Succeeded | Succeeded | State and event match |
| Succeeded | Failed | Lost notification; consumers do not update |
| Failed | Succeeded | Event describes uncommitted data |
| Unknown due to timeout | Unknown | Retries may duplicate or drop |

A normal database transaction protects only changes inside that database. The broker is an independent system, so a single `COMMIT` cannot be assumed to span both database and broker without a supported and actively configured distributed transaction protocol. Even when a platform provides transactional brokers, external API side effects remain a separate boundary.

## 3. Transactional outbox

### 3.1. Concept

An outbox is a table or storage area storing events waiting to be published. Within the **same transaction** as the business update, the service inserts an outbox record:

1. Validate and update authoritative data.
2. Insert an event record into the outbox.
3. Commit the transaction.
4. A separate publisher reads the outbox and forwards events to the broker.

~~~mermaid
flowchart LR
    APP[Booking Service] --> TX[Database transaction]
    TX --> B[(Bookings table)]
    TX --> O[(Outbox table)]
    O --> PUB[Outbox publisher / CDC]
    PUB --> BUS[(Message broker)]
    BUS --> C[Consumers]
~~~

If the database transaction rolls back, neither the booking update nor the event record exists. If the transaction commits, the event record remains in the outbox for the publisher to emit later. The gap between database commit and broker publish becomes retryable and reconcilable work.

### 3.2. Reference outbox schema

~~~sql
CREATE TABLE outbox_events (
    event_id       VARCHAR(80) PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id   VARCHAR(120) NOT NULL,
    aggregate_seq  BIGINT,
    event_type     VARCHAR(120) NOT NULL,
    event_version  INTEGER NOT NULL,
    occurred_at    TIMESTAMP NOT NULL,
    payload        JSON NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    published_at   TIMESTAMP NULL
);

CREATE INDEX ix_outbox_pending
    ON outbox_events (created_at, event_id)
    WHERE published_at IS NULL;
~~~

This schema is illustrative; JSON types, partial indexes, timestamps, and syntax depend on the database. You may also need `tenant_id`, `correlation_id`, lease status, attempt counts, and tracing metadata. Do not store secrets or unnecessary sensitive payloads just because the outbox resides in an internal database.

### 3.3. Writing business data and outbox in the same transaction

~~~sql
BEGIN;

UPDATE bookings
SET status = 'CONFIRMED',
    version = version + 1
WHERE booking_id = 'booking_913'
  AND status = 'PENDING';

INSERT INTO outbox_events (
    event_id, aggregate_type, aggregate_id, aggregate_seq,
    event_type, event_version, occurred_at, payload, created_at
)
VALUES (
    'evt_01JXY99', 'Booking', 'booking_913', 7,
    'BookingConfirmed', 1, CURRENT_TIMESTAMP,
    '{"bookingId":"booking_913","status":"CONFIRMED"}',
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

In production code, check the updated row count or prior state so that only a valid transition is recorded. If the update fails because the booking is no longer `PENDING`, never insert a confirmation event. Use conditional transactions, constraints, or appropriate locking to protect invariants.

### 3.4. Outbox records publication intent, not business state

The outbox typically has a shorter lifecycle than business data: created in the same transaction, transported shortly after, retained long enough for retries/reconciliation, and purged/archived per policy. The authoritative source remains the tables or aggregates owned by the service.

Do not use `published_at IS NOT NULL` to conclude that all consumers have finished processing. It only indicates that the publisher recorded publication per its chosen semantics; consumer state, delivery, and downstream side effects belong to separate flows.

## 4. Transporting the outbox: polling or CDC?

There are two common ways to deliver outbox records to a broker.

### 4.1. Polling publisher

A periodic process queries unpublished rows, claims processing rights, and dispatches messages:

~~~mermaid
flowchart TD
    TIMER[Timer / Worker] --> Q[Query pending outbox]
    Q --> CLAIM[Claim batch / lease]
    CLAIM --> SEND[Publish to broker]
    SEND -->|Acknowledged| MARK[Mark published]
    SEND -->|Error / timeout| RETRY[Keep pending / retry]
    RETRY --> Q
~~~

**Advantages:**

- Easy to understand and implement at moderate volume.
- No need to read transaction logs or operate CDC connectors.
- Batch size, polling cadence, and publish state can be controlled directly in the database.

**Trade-offs:**

- Polling latency between commit and the next query.
- Continuous queries add database load, index maintenance, and contention.
- Multiple publishers may contend for the same rows without safe claiming/leasing.
- Must handle crashes after publishing but before marking published.

One strategy uses `SELECT ... FOR UPDATE SKIP LOCKED` or an equivalent lease mechanism, depending on the database, so multiple workers claim batches with low contention. However, do not assume syntax or lock semantics are identical across all DBMSs.

### 4.2. Transaction-log-based CDC

Change Data Capture records database changes and forwards them to downstream systems. With log-based CDC, a connector reads the transaction log (e.g., binlog, WAL, or equivalent), extracts committed changes, and emits them according to checkpoints/offsets.

~~~mermaid
flowchart LR
    APP[Application transaction] --> DB[(Database)]
    DB --> LOG[(Transaction log)]
    LOG --> CDC[CDC connector]
    CDC --> ROUTE[Filter / Transform]
    ROUTE --> BUS[(Broker / Stream)]
    BUS --> CONSUMERS[Consumers]
~~~

**Advantages:**

- Can detect changes in near real time without polling individual rows.
- Eliminates repeated outbox table scans at high volume.
- Can capture committed inserts/updates/deletes per log and connector semantics.
- Supports streaming changes to multiple consumers.

**Trade-offs:**

- Requires configuring log-read permissions and sufficient log retention.
- Connectors maintain checkpoints, offsets, schema history, and separate operational state.
- Database schema changes, failovers, and connector recovery require procedures.
- CDC can emit many change types; filter tables/operations properly so internal updates do not leak as integration events.

### 4.3. CDC is not synonymous with outbox

CDC is a technique for observing data changes. It can read business tables directly, audit tables, or outbox tables. Transactional outbox is a **data and transaction pattern** ensuring event emission intent commits with business data. Log-based CDC is a **change observation/transport mechanism**.

Combining outbox + CDC provides:

- An explicitly designed event contract in the outbox table instead of inferring events from individual business columns.
- Atomicity between business updates and event emission intent.
- Post-commit change transport via the transaction log.

Direct CDC from business tables can fit data replication or analytics, but if used to generate domain events for integration, be careful about semantics, ordering, intermediate states, and whether an internal change truly represents a business event.

### 4.4. Comparing polling, CDC, and triggers

| Mechanism | How changes are detected | Advantages | Limitations |
|---|---|---|---|
| Polling | Scheduled queries for unprocessed rows | Simple, easy to control with SQL | Polling latency, DB load, claiming/locking |
| Log-based CDC | Reads committed transaction log | Near real-time, reduces table polling | Connector, log retention, schema, and offset complexity |
| Database trigger | Trigger inserts another record or invokes internal mechanism on DML | Same transaction and close to data writes | Can increase coupling and hurt write latency; trigger logic is hard to version/review |
| Timestamp polling | Filters records with newer `updated_at` | Easy to start for batch sync | Easily misses concurrent/skewed timestamps, hard to detect deletes, lacks true transaction sequence |

Timestamp polling cannot replace log-based CDC when full update/delete capture and transaction ordering are required. Triggers should also never make network API calls inside a database transaction; doing so extends locks and couples transactions to external services.

## 5. Publisher: emitting events safely

### 5.1. Send-and-mark sequence

With a polling publisher, a common flow is:

1. Claim pending rows via a lease or lock.
2. Publish events to the broker.
3. Wait for acknowledgment per broker semantics.
4. Mark rows published and record timestamp/attempt.

There is a failure window: the broker received the event, but the publisher crashes before updating `published_at`. Upon restart, the publisher may emit the event again. That is why consumers must tolerate duplicates.

If the publisher marks rows before broker acknowledgment and then sends, a crash after marking can lose the event. Therefore, ordering and state must prioritize never losing emission intent, accepting possible redelivery and designing for idempotency.

### 5.2. Safe claiming with multiple publishers

If multiple workers process the outbox concurrently:

- Each record needs temporary exclusive claiming or stable work partitioning.
- Leases must expire so crashed workers do not hold records forever.
- Workers must verify lease/owner when updating status.
- Batch size and concurrency must be bounded according to broker and database throughput.
- Processing time must account for network timeouts and lease expiry.

Avoid holding a database transaction open for the entire broker call if it causes long locks and reduces throughput. A claim-lease pattern can commit quickly, publish outside the transaction, and then update results using an owner token/version. Accept the possibility of a lease expiring while a request is still in flight, resulting in consumer duplicates.

### 5.3. Per-aggregate event ordering

If a booking transitions `PENDING` → `CONFIRMED` → `CANCELLED`, consumers may need to receive events in order for that booking. You can record a monotonically increasing `aggregate_seq` or version during the business transaction and use the aggregate ID as the partition/message-group key.

Decisions to make:

- Does the publisher preserve per-aggregate ordering when sending in parallel?
- Within which queue group or partition does the broker preserve ordering?
- Does retrying an older event block newer events for the same aggregate?
- Does the consumer reject events with sequences older than current state?

Do not assume system-wide global event ordering. Ordering is usually needed only within a single aggregate/entity.

## 6. Transactional inbox and consumer-side deduplication

### 6.1. Why can consumers still receive duplicates?

A consumer may process a message, commit its data, and crash before acknowledging. Unaware that side effects completed, the broker redelivers the message. A stream consumer may write data successfully and crash before committing its offset, then re-read the record after restarting.

At-least-once delivery therefore requires consumers to handle redelivery safely.

### 6.2. What is an inbox?

An inbox is a table or store recording events already received/processed by a consumer. The consumer inserts the event ID into the inbox and updates its data in the same transaction:

~~~mermaid
flowchart TD
    BROKER[(Broker)] --> C[Consumer]
    C --> TX[Consumer DB transaction]
    TX --> CHECK{eventId already exists?}
    CHECK -->|Yes| SKIP[Skip duplicate side effect]
    CHECK -->|No| INBOX[Insert inbox record]
    INBOX --> UPDATE[Update consumer data]
    UPDATE --> COMMIT[Commit]
    COMMIT --> ACK[Acknowledge / commit progress]
~~~

If the event was processed previously, the consumer skips repeating the side effect and acknowledges the duplicate delivery. If the transaction rolls back, both the inbox record and data update roll back; the broker redelivers per its semantics.

### 6.3. Reference inbox schema

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id      VARCHAR(80) NOT NULL,
    processed_at  TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

The primary key includes both consumer name and event ID because the same event can be processed independently by multiple consumers. If all subscribers shared one dedup table without distinguishing consumers, the first subscriber could cause others to mistakenly skip the event.

### 6.4. Consumer pseudocode

~~~text
receive(message)

BEGIN DATABASE TRANSACTION
    inserted = INSERT processed_events(consumer_name, event_id)
               ON CONFLICT DO NOTHING

    IF inserted:
        apply_business_update(message.data)
    ELSE:
        do_not_repeat_business_update()
COMMIT

ACK message only after commit succeeds
~~~

This pseudocode illustrates the principle. Use transaction isolation and insert-checking statements appropriate to your database. If `apply_business_update` calls an external API, that side effect is outside the inbox transaction; add an outbox, API idempotency, or intermediate state.

### 6.5. Inbox retention policy

The inbox does not necessarily need to store every event forever. Retention must exceed the possible replay/redelivery window and reconciliation requirements. If dedup records are deleted too early and the broker replays an old event, the consumer may re-execute side effects. Define:

- Broker retention or the window within which a DLQ can be redriven.
- Retry and replay windows in operational procedures.
- Which operations require long-term deduplication via business unique keys.
- How to archive/purge inbox rows per data policy.

For financial transactions or non-repeatable operations, the event inbox can be paired with unique constraints on payment reference / order ID for business-level protection.

## 7. CDC: snapshots, transaction logs, offsets, and checkpoints

### 7.1. Initial snapshot and subsequent changes

When starting CDC, the connector may need to take a snapshot of existing data so downstream has an initial baseline before applying incremental changes. This process must coordinate the snapshot boundary with the transaction log position to avoid missing changes or applying them out of order.

Some connectors support initial snapshots, incremental snapshots, or starting from a saved log position. Specific behavior varies by database and connector. Test:

- How does the snapshot lock or read consistently?
- How are new writes handled during the snapshot?
- If the snapshot fails mid-way, where can it resume?
- How do you verify downstream received the complete initial state?

### 7.2. Offsets and checkpoints

A CDC connector stores the read position in the transaction log, such as a binlog position, WAL LSN, or corresponding cursor. When the connector restarts, it resumes from its checkpoint or committed offset.

If a checkpoint is saved before the event is durably sent to the broker, changes can be skipped. If sending succeeds before the checkpoint is saved, events may be re-emitted. Thus, offset/checkpoint semantics and duplicate potential must be clearly understood.

### 7.3. Transaction boundaries and commit order

Database logs contain transactions and commit ordering. Depending on the platform, a connector may emit change records per row or wrapped in a transaction envelope. When a single transaction updates multiple tables, consumers must know how related records are grouped and ordered.

If downstream needs only post-commit outbox events, connector filters should target the outbox table and use transaction metadata as needed for ordering. When applying CDC directly to multiple business tables, do not infer a domain event from every row change without defining invariants and business meaning.

### 7.4. Inserts, updates, deletes, and tombstones

CDC can capture:

- **INSERT:** a new row is created.
- **UPDATE:** certain columns change; connectors may emit before/after images or after-only depending on configuration.
- **DELETE:** a row is deleted; may be represented by a delete record or a tombstone.
- **TRUNCATE/DDL:** schema changes or bulk deletes; support varies by connector.

Consumers must know how to interpret tombstones and deletes. If only inserts/updates are synced, downstream may retain records deleted at the source. For data with deletion obligations, check replicas, archives, search indexes, and caches.

### 7.5. Transaction log retention

If a connector stays down longer than the database retains transaction logs, the checkpointed position may no longer exist. The connector cannot resume from pruned logs; a fresh snapshot or separate recovery procedure may be required.

Therefore, CDC capacity and operations must account for:

- Log generation rate and retention period.
- Outage duration the connector must survive.
- Bandwidth and consumption rate when the connector restarts.
- Snapshot duration and impact on database load.
- Storing schema history, offsets, and connector configurations.

## 8. CDC and outbox together in cloud architecture

### 8.1. Reference architecture flow

~~~mermaid
flowchart TB
    API[Booking API] --> TX[DB transaction]
    TX --> BOOK[(Bookings)]
    TX --> OUT[(Outbox events)]
    DBLOG[(Transaction log)] --> CDC[CDC connector]
    OUT --> DBLOG
    CDC --> FILTER[Filter outbox + serialize]
    FILTER --> TOPIC[(Booking events topic)]
    TOPIC --> CONSUMER[Consumer group]
    CONSUMER --> INBOX[(Inbox / processed events)]
    INBOX --> PROJ[(Search projection)]
    TOPIC --> NOTIFY[Notification consumer]
~~~

The outbox is written in the same transaction as booking state. CDC reads the log to emit committed outbox records; the connector maps event records to the topic contract. Consumers maintain their own inbox/deduplication.

### 8.2. Distinct layers of guarantees

| Layer | Mechanism | Target guarantee | Not guaranteed automatically |
|---|---|---|---|
| Source domain | Database transaction + outbox row | Event intent commits with source data | Broker has received the event |
| Transport | Poller or CDC connector + broker ack/checkpoint | Durable event emission per pipeline semantics | Zero duplicates |
| Consumer | Inbox + business update in same transaction | No duplicate internal updates for the same event ID | External non-DB side effects |
| External integration | Idempotency reference + reconciliation | Reduces duplicate side effects and handles ambiguous outcomes | Absolute exactly-once across all systems |
| Operations | Retries, DLQ, replay, alerts, and runbooks | Controlled failure detection and recovery | Never having failures or data loss |

### 8.3. Do not confuse CDC with event sourcing

**CDC** captures changes that occurred in a database for synchronization or downstream processing. **Event sourcing** uses events as the primary storage model for business state; current state is reconstructed from the sequence of events per domain rules.

A CDC pipeline from a bookings table does not turn an application into an event-sourced system. Similarly, an outbox table is a queue of events to publish, not necessarily the authoritative source to rebuild full business state.

## 9. Ordering, duplicates, and consistency

### 9.1. Event version and aggregate sequence

Events should carry:

- Stable `eventId` for deduplication.
- `aggregateId` or entity ID to group events for the same entity.
- `aggregateVersion`/`sequence` to detect stale or missing events.
- `occurredAt` as a business timestamp reference, not as sole proof of ordering.
- `correlationId` to trace a processing flow.

If a consumer receives sequence 9 after sequence 7, it must know whether sequence 8 was missed or event 9 is a complete newer update. Depending on the model, the consumer can buffer, query the owning service, retry, or route the event for reconciliation.

### 9.2. At-least-once is the safe assumption

Even if a broker or connector offers strong delivery mechanisms, publishers/consumers can still crash at the boundary between side effects and acknowledgments/checkpoints. Designs should assume an event may appear multiple times and protect via idempotency/deduplication.

### 9.3. Eventual consistency and lag

Outbox + CDC creates an asynchronous update stream. The time from database commit to consumer completion depends on:

- Log flush and connector polling/streaming.
- Connector lag and batch size.
- Broker throughput, partitions, and throttling.
- Consumer capacity, retries, and downstream dependencies.
- Backlogs, rebalances, and error handling.

Therefore, the system needs an SLO or freshness threshold per stream: for example, search projections update within a few seconds under normal load; analytical reports may lag longer. Do not enforce one blanket number for every event.

### 9.4. Read-after-write

If a user confirms a booking and immediately views history, a CDC-updated read model may not have caught up yet. Approaches include:

- Returning state from the authoritative Booking source right after commit.
- Querying the authoritative source for a short window after a write.
- Passing aggregate version and waiting for the projection to reach the required version.
- Returning a "syncing" status when the business allows it.

Do not report failure just because a projection has not seen the new event yet; doing so can prompt clients to resend an already-succeeded operation.

## 10. Error handling and recovery

### 10.1. Publisher failures

| Scenario | Required behavior |
|---|---|
| Database transaction rolls back | No outbox record; no event emitted |
| Commit succeeds, broker temporarily errors | Outbox stays pending; retry per policy |
| Broker receives event, publisher crashes before marking | May republish; consumers deduplicate |
| Record claimed by dead worker | Lease expires and another worker reclaims |
| Invalid payload | Move to error/DLQ state per procedure; do not retry forever |
| Publisher overloaded | Limit batch/concurrency; monitor backlog and oldest age |

### 10.2. CDC connector failures

When a connector fails to read logs, lacks permissions, hits a schema error, or loses its checkpoint:

1. Identify the last checkpointed log position and whether existing logs still cover it.
2. Check broker state: was the last record emitted, and are duplicates possible?
3. Inspect connector config, schema history, credentials, network, and quotas.
4. Never arbitrarily reset offsets or re-run snapshots without assessing downstream impact.
5. If re-snapshotting is required, define how to handle duplicate/overwritten data and deletes/tombstones.
6. After recovery, verify lag returns to normal and reconcile counts/versions between source and target.

### 10.3. Consumer failures

Consumers must retry transient errors, route poison messages to DLQs, keep inbox and processing state consistent, and never commit offsets before data is durably written per design. When redriving, verify whether side effects already occurred and reuse the same idempotency key.

### 10.4. Reconciliation as an additional safety layer

For critical data, run periodic reconciliation jobs:

- Compare committed booking counts/sequences with emitted events.
- Find aged outbox records that remain unpublished.
- Detect consumer lag or missing events in projections.
- Reconcile payment status with providers by reference.
- Rebuild projections from the source or retained streams when needed.

Reconciliation does not replace transactions and idempotency, but it catches residual discrepancies from rare bugs or observability blind spots.

## 11. Schema management and structural changes

### 11.1. Outbox payloads should be integration contracts

You do not need to serialize an entire database row into the payload. If consumers depend directly on every internal column, a database migration becomes a system-wide breaking change. Design integration events with only meaningful business fields and publish them with versions.

### 11.2. Schema evolution

Typically, adding optional fields with clear semantics and defaults is more compatible than deleting/renaming fields or changing types. However, compatibility depends on serializers/deserializers and consumer behavior; test thoroughly.

When running CDC directly on tables, DDL changes can affect connectors, schema history, and consumers. Follow an expand–migrate–contract workflow, testing both old and new schemas with a rollback plan.

### 11.3. Do not emit every internal change as a public event

A row might change to fix a typo, touch a timestamp, or update a technical column. If every update emits an integration event, consumers receive noise and become coupled to internal schemas. Use an outbox so the owner explicitly decides which business events are published; use direct CDC for replication/analytics where appropriate.

## 12. Security and data governance

### 12.1. Database and log access permissions

CDC connectors typically require permission to read transaction logs and schema metadata. This access can be more sensitive than standard `SELECT` permissions. Best practices:

- Provision a dedicated account for the connector with the minimum permissions required by the platform.
- Restrict which databases/schemas/tables are tracked.
- Protect credentials with a secret manager and rotation.
- Encrypt transit to the database, broker, and schema registry.
- Audit connector changes, offset resets, snapshots, publications, and replication slots.
- Do not share database admin credentials across consumers.

### 12.2. Event payloads and history

Outboxes, brokers, inboxes, DLQs, connector logs, and backups may contain personal data or transaction details. Classify payloads, minimize fields, encrypt, control read/replay permissions, and set appropriate retention.

### 12.3. Regions and data sovereignty

If the source database resides in one region while the broker, CDC connector, archive, or analytics pipeline runs in another, data still crosses boundaries. Evaluate the full pipeline:

Database → transaction log → connector → broker → consumer → projection / archive / logs

Do not check only the database location. Regions storing logs, backups, checkpoints, DLQs, and telemetry may also fall under policy scope. Specific regulatory obligations must be verified by data type, contract, and actual processing locations.

## 13. Performance, capacity, and cost

### 13.1. Outbox table growth

If the publisher never cleans up emitted records, the outbox grows unboundedly. Implement retention, partitioning/archiving, or cleanup jobs per policy. Do not delete records too early when needed for investigation, replay, or reconciliation.

### 13.2. Polling cost

Polling too frequently runs queries even when no events exist. Polling too infrequently increases event latency. Large batches improve throughput but hold locks/leases longer and consume more memory; tiny batches increase round trips.

### 13.3. CDC throughput and log retention

CDC needs enough bandwidth to keep pace with log generation. If a connector falls behind, logs can accumulate and outgrow retention. Large snapshots can create read load on the database; connector restarts may need to catch up on long backlogs.

### 13.4. Broker and consumer capacity

Partitions, replication factor, retention, message size, compression, subscriptions, and consumer concurrency affect storage, CPU, network, and cost. Slow consumers increase lag; adding workers helps only if partitions and dependencies allow parallelism.

### 13.5. Operational comparison table

| Criterion | Polling outbox | Outbox + CDC |
|---|---|---|
| Latency | Driven by polling interval / batch | Can be lower, depends on connector/log |
| Database load | Repeated queries on pending rows | Reads transaction log; still incurs connector load |
| Infrastructure complexity | Usually lower | Higher due to connector, offsets, and schema history |
| Publisher scaling | Workers / leases / batches | Partitions / connector tasks and log throughput |
| Recovery | Reclaim pending records | Resume offset or re-snapshot |
| Observability | Pending count, oldest pending age, publish errors | Connector lag, log position, offsets, broker lag |
| Best fit | Moderate volume, simplicity preferred | High volume/latency demands, CDC ops capability available |

There is no fixed volume threshold for switching from polling to CDC. Decide based on target latency, throughput, DB load, connector management capability, cost, and acceptable risk.

## 14. End-to-end example: syncing bookings to Search

Suppose Booking Service owns booking state. Search Service maintains a projection for searching/filtering history. When a booking is confirmed, the system must update the projection within a few seconds under normal conditions.

### 14.1. Data flow

~~~mermaid
sequenceDiagram
    participant API as Booking API
    participant DB as Booking DB
    participant LOG as Transaction log
    participant CDC as CDC connector
    participant BUS as Event broker
    participant S as Search consumer
    participant IDX as Search index
    API->>DB: BEGIN
    API->>DB: Update booking = CONFIRMED
    API->>DB: Insert BookingConfirmed into outbox
    API->>DB: COMMIT
    DB-->>LOG: Committed changes
    LOG-->>CDC: Outbox row change
    CDC->>BUS: Publish BookingConfirmed
    BUS->>S: Deliver event
    S->>S: Inbox dedup by eventId
    S->>IDX: Update projection
    S-->>BUS: Acknowledge / commit progress
~~~

### 14.2. Component responsibilities

| Component | Responsibility | Evidence / metrics |
|---|---|---|
| Booking API | Validate transitions, write booking + outbox | Transaction commits, versions |
| Booking DB | Authoritative source and change log | Backups, log retention, transaction health |
| CDC connector | Read outbox changes and emit matching contracts | Connector status, offsets, lag |
| Event broker | Persist/route events to consumers | Produce/consume rates, retention, delivery errors |
| Search consumer | Deduplicate and update projection | Inbox, processing lag, errors/DLQ |
| Search index | Serve eventually consistent queries | Projection version, freshness, rebuilds |

### 14.3. Failure scenarios

**Scenario A – Booking commits, connector stops:** the outbox row is already in the transaction log. When the connector recovers, it resumes from its checkpoint if logs are still retained. Monitor connector lag and log retention.

**Scenario B – Connector publishes but crashes before checkpoint:** the event may be re-emitted. Search consumer uses `eventId`/inbox to prevent duplicate updates and unintended side effects.

**Scenario C – Consumer updates index but crashes before ack:** the broker redelivers the event. Consumer checks the inbox; if data and inbox commit atomically in a single supporting datastore transaction, redelivery does not repeat the update. If the index does not support transactions alongside the inbox, use idempotent document updates by version or an intermediate state store.

**Scenario D – New event version:** old consumer cannot parse it. Contract tests and compatibility policies must block incompatible releases; malformed messages go to DLQ instead of infinite retries.

**Scenario E – Search lags significantly:** UI may display stale data. For operations requiring immediate post-write state, query Booking API as the authoritative source or provide read-your-writes by version; never conclude a booking does not exist solely because Search has not updated.

## 15. Testing and drills

### 15.1. Source transaction tests

- Booking and outbox commit together: both must exist.
- Transaction rolls back: neither booking transition nor event exists.
- Invalid transition or 0-row update: no event is created.
- Concurrent requests: do not emit two confirmation events for the same transition.

### 15.2. Publisher / CDC tests

- Broker stops and recovers.
- Publisher crashes after publish but before marking.
- Two publishers claim the same batch.
- Lease expires while publish is still running.
- Connector restarts from checkpoint.
- Connector loses log retention.
- Snapshot while new writes arrive.
- DDL/schema changes and new event versions.

### 15.3. Consumer tests

- Deliver the same event multiple times.
- Consumer commits data but loses ack.
- Events arrive out of order or with sequence gaps.
- Inbox commit fails.
- Downstream experiences transient errors, overload, or timeout after side effect.
- DLQ redrive and replay.

### 15.4. Consistency verification

Measure end-to-end timing:

source commit → outbox publish → broker delivery → consumer commit → projection visible

Track p50/p95/p99 event lag, oldest pending outbox age, connector lag, broker lag, and consumer processing duration. Set freshness targets per use case rather than counting only published events.

## 16. Observability and runbooks

### 16.1. Key metrics

| Layer | Metrics | Alert when |
|---|---|---|
| Outbox | Pending rows, oldest pending age, publish attempts | Pending grows or aged records exceed deadline |
| Publisher | Publish success/errors, batch duration, lease expirations | Persistent errors or workers contending for leases |
| CDC | Connector health, log position, source lag, offset age | Connector stops or lag spikes rapidly |
| Database log | Log growth, retained bytes, replication slot lag | Running out of space or logs held too long |
| Broker | Produce/consume rates, throttling, storage, partition health | Broker falls behind producers |
| Consumer | Processing rate, retries, errors, inbox duplicate count | Consumer slows or errors rise |
| DLQ | Message count, oldest age, schema/error types | Messages require owner intervention |
| Projection | Version lag, freshness, reconciliation mismatches | Read model fails to keep up with source |

### 16.2. Runbook: stuck publisher

1. Check pending count and oldest record age.
2. Determine whether broker/network/credentials are failing or workers cannot claim batches.
3. Inspect leases, locks, query plans, and outbox indexes.
4. Check whether `eventId` was already received by the broker before resending.
5. Restore publisher with bounded batch size and concurrency.
6. Reconcile published records and consumer lag.

### 16.3. Runbook: CDC lag or lost checkpoint

1. Check connector state, last committed offset, and whether transaction logs still cover that position.
2. Verify log-read permissions, schema history, network, and broker.
3. Estimate backlog and catch-up speed; ensure logs do not expire retention mid-recovery.
4. Never reset offsets or re-snapshot without evaluating duplicate and data-loss risks.
5. After resuming, verify ordering/versions and reconcile counts.

### 16.4. Runbook: consumer / DLQ

1. Classify errors by schema, permissions, dependencies, data, and code.
2. Verify the consumer safely handles duplicates; inspect inbox and actual side effects.
3. Fix the bug and test against the failing payload in a controlled environment.
4. Redrive with bounded batch/rate while monitoring lag and downstream health.
5. Close the incident after projections or target systems are reconciled.

## 17. Common mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Update DB then publish event separately | Events can be lost after commit | Transactional outbox |
| Publish before DB commit | Consumers receive events for invalid/uncommitted state | Emit only committed intent |
| Treat outbox as exactly-once | Crashes can cause duplicate publishes | Idempotent consumers and deduplication |
| Use direct CDC on every table as domain events | Exposes internal structure, wrong event semantics | Design event contracts via outbox |
| Acknowledge before consumer commits | Processing lost on crash | Commit data/inbox before ack |
| Purge inbox too early | Old replays re-trigger side effects | Align retention with replay window and business rules |
| Arbitrarily reset CDC offsets | Drops records or emits massive duplicates | Check logs/offsets and snapshot plan |
| Neglect transaction log retention | Connector cannot resume after long downtime | Size log capacity and alert on connector lag |
| Use timestamp as sole checkpoint | Drops records or mishandles deletes | Use CDC log/sequence or cursor with clear semantics |
| Skip event versioning | Old consumers break on schema changes | Contracts, compatibility tests, and rollouts |
| Ignore deletes / tombstones | Target systems retain deleted records | Define delete semantics and propagation |
| Lack reconciliation | Rare discrepancies persist indefinitely | Periodic reconciliation and corrective evidence |

## 18. Well-Architected assessment

| Pillar | Questions | Measures / trade-offs |
|---|---|---|
| **Operational Excellence** | Who owns the outbox, connector, topics, consumers, and runbooks? | Service catalog, dashboards, replay procedures; CDC adds operational components |
| **Security** | Who can read transaction logs, payloads, inboxes, and DLQs? | Least privilege, secret rotation, encryption, data minimization, and auditing |
| **Reliability** | Which failure windows exist across commit, publish, ack/checkpoint, and side effects? | Outbox/inbox, idempotency, bounded retries, DLQ, and reconciliation |
| **Performance Efficiency** | Are polling load, log throughput, partitions, and consumer capacity sufficient? | Batching, indexing, partitioning, connector scaling; tune latency per workload |
| **Cost Optimization** | What do outbox storage, log retention, broker, connectors, egress, and history cost? | Reasonable retention, cleanup, choose polling vs. CDC by value |
| **Sustainability** | Are we polling too frequently, emitting redundant events, or replaying unnecessarily? | Appropriate CDC/polling cadence, lean payloads, cleanup, and efficient batching |

Outbox/inbox/CDC improve consistency and resilience, but they add tables, connectors, brokers, offsets, storage, and operational processes. Adopt only the level of complexity justified by business value and dual-write risk.

## 19. Practice exercises

### Exercise A – Dual-write gap

Booking Service commits `CONFIRMED` and crashes before publishing `BookingConfirmed`.

**Question:** Why is having the client retry the request not a complete fix? What must be designed?

**Hint:** The client may not know the commit already succeeded; resending can duplicate work. You need idempotency for the command plus an outbox inside the source transaction so emission intent survives the crash.

### Exercise B – Publisher crash

The publisher successfully sends an event to the broker, then crashes before marking the outbox row published.

**Question:** What can happen on restart? How do you protect consumers?

**Hint:** The event may be republished. Use a stable `eventId` and consumer-side inbox/dedup; never mark published before broker acknowledgment per semantics.

### Exercise C – CDC log loss

A connector stops for 18 hours. The database retains transaction logs for only 12 hours. The last offset is no longer in the remaining logs.

**Question:** Can you simply restart the connector?

**Hint:** It likely cannot resume from the old offset. You need a snapshot/rebootstrap or recovery procedure, evaluating duplicates, deletes/tombstones, and downstream reconciliation; increase retention and alert on lag to prevent recurrence.

### Exercise D – Consumer external side effect

A consumer sends an email successfully, then the database inbox commit fails. The broker redelivers the event.

**Question:** Does a plain inbox prevent sending the email twice?

**Hint:** No, because sending the email and writing the inbox are not in the same transaction. Use the provider's idempotency API if supported, an intermediate delivery record/outbox, and reconciliation state; accept that external outcomes can be indeterminate after timeouts.

### Exercise E – Direct CDC on business tables

A connector emits an event whenever `updated_at` or an internal column changes. Consumers treat every record update as `BookingUpdated`.

**Question:** What is the risk?

**Hint:** Events may lack business meaning, emit noise, and couple consumers to internal schemas. Use an outbox so the service owner defines integration events, or define explicit mapping/filtering and contracts when using CDC for replication.

### Exercise F – Aggregate ordering

A booking has sequence 11 `CONFIRMED` and 12 `CANCELLED`. A consumer receives 12 before 11.

**Question:** How should the consumer handle this?

**Hint:** Use aggregate sequence/version to detect ordering; partition by `bookingId` if the platform guarantees in-partition ordering; ignore or reconcile stale events per state transition rules instead of relying solely on receipt timestamps.

## 20. Pre-production checklist for outbox/inbox/CDC

- [ ] Events are defined with business semantics, owners, `eventId`, version, and aggregate keys.
- [ ] Source data updates and outbox inserts execute in the same transaction.
- [ ] Events are created only when a valid business transition succeeded.
- [ ] Publishers have safe leasing/claiming, bounded batch/concurrency, and crash-after-publish handling.
- [ ] CDC connectors have least-privilege access, managed offsets/checkpoints, schema history, and log retention.
- [ ] Polling vs. CDC is chosen based on latency, volume, DB load, and operational capability.
- [ ] Consumers write inbox/dedup records in the same transaction as local data updates.
- [ ] Non-database external side effects have idempotency keys or reconciliation.
- [ ] Duplicates, ordering, retries, poison messages, DLQs, and replay are tested.
- [ ] Runbooks exist for snapshots, deletes/tombstones, schema evolution, and offset resets.
- [ ] Metrics cover oldest pending outbox age, connector lag, broker lag, consumer lag, and reconciliation mismatches.
- [ ] Retention/cleanup policies are defined for outbox, inbox, logs, broker, and DLQs.
- [ ] Payloads, checkpoints, connector credentials, and stored data are protected.
- [ ] Regions for source, connector, broker, backups, logs, and consumers comply with data policies.
- [ ] Capacity for database, transaction logs, broker, partitions, network, and consumers is benchmarked.
- [ ] Owners, budgets, alerts, recovery drills, and periodic reconciliation processes are in place.

**Key takeaway:** transactional outbox keeps **event emission intent** in the same transaction as source data; inbox ensures consumers **do not repeat internal processing** when messages are redelivered; CDC transports **committed changes** from databases to other systems using logs/checkpoints. Combining all three properly makes event pipelines more reliable, while still requiring idempotency for external side effects, ordering and lag management, replay handling, data security, and recovery drills.
