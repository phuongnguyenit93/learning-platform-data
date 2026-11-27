# Queues, Publish–Subscribe, Event Buses, and Event Streams

In cloud applications, components often need to coordinate without necessarily calling one another directly within the same request. When a customer books a room, the Booking Service may emit a notification so Payment can process the charge, Notification can send an email, Search can update its index, and Analytics can record user behavior. If Booking had to wait for each system to finish, latency and coupling would increase; if it emitted notifications without a mechanism to retain and redeliver them, a brief outage could cause lost work.

Technologies such as **queues**, **publish–subscribe (pub/sub)**, **event buses**, and **event streams** solve different parts of the messaging problem. They help decouple producers from consumers, absorb load spikes, distribute events, and build asynchronous processing flows. However, they differ in their semantics for delivery, ordering, retention, replay, and scalability. Choosing the wrong model can cause lost events, duplicate processing, growing backlogs, inconsistent data, or unnecessary operational overhead.

This lesson belongs to the **Event Architecture** chapter of the **CLOUD_ARCHITECTURE** module. The goal is to select an event delivery mechanism suited to business requirements, and then design for correctness, security, reliability, performance, scalability, cost, and operations using Well-Architected thinking.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Distinguish message queues, pub/sub, event buses, and event streaming by delivery model and data retention.
2. Explain the roles of producer, consumer, broker, topic, subscription, partition, offset, and consumer group.
3. Choose a delivery mechanism suited to requirements for single consumers, multiple consumers, fan-out, buffering, replay, and continuous processing.
4. Design idempotent consumers and handle duplicates, ordering, retries, and dead-letter queues.
5. Distinguish commands from events, define event contracts, and manage schema versions.
6. Design event flows with security, observability, load limits, recovery, and cost control.
7. Evaluate trade-offs across latency, throughput, durability, consistency, and operability in cloud architectures.

## 2. Four Common Models

### 2.1. Message Queue: Dispatching Work to Consumers

A queue is where producers send messages for one or more consumers to process. In the common competing-consumers model, each message is picked up by one consumer in the group for processing; the broker or queue protocol manages delivery state and can make the message available again if the consumer does not acknowledge it according to the service's semantics.

~~~mermaid
flowchart LR
    P[Producer] --> Q[(Message Queue)]
    Q --> C1[Consumer 1]
    Q --> C2[Consumer 2]
    Q --> C3[Consumer 3]
~~~

Example: Booking Service sends an invoice generation request into a queue. A worker picks up the message, calls the invoicing service, saves the result, and acknowledges that the message has been processed. Other workers pick up other messages as capacity allows.

A queue is well suited when:

- Work can be processed asynchronously.
- You need to absorb spikes and pace consumer throughput.
- Each message represents a unit of work to be completed.
- The producer does not need to know which specific worker will execute it.

A queue does not inherently deliver the same message to every consumer. If multiple systems need to receive the same event, you need a pub/sub model or multiple subscriptions/queues configured so each consumer receives its own copy.

### 2.2. Publish–Subscribe: One Event, Multiple Subscribers

In pub/sub, a publisher sends events to a topic or channel; the broker distributes copies to registered subscribers. Each subscriber can process independently at its own pace and with its own retry mechanism, depending on platform capabilities.

~~~mermaid
flowchart LR
    P[Publisher] --> T((Topic))
    T --> S1[Subscription A]
    T --> S2[Subscription B]
    T --> S3[Subscription C]
    S1 --> A[Notification]
    S2 --> B[Analytics]
    S3 --> C[Search projection]
~~~

Example: after a booking is confirmed, Booking Service emits BookingConfirmed. Notification sends an email, Analytics records the conversion, and Search updates its projection. Booking Service does not need to call each system directly.

Pub/sub is well suited when:

- One event needs to trigger multiple consumers.
- Consumers need to scale or be deployed independently.
- The publisher does not need to know the exact list of subscribers.
- There is a need to isolate receive permissions, retries, and backlogs for each consumer group.

Pub/sub still requires clearly defining whether a new subscriber receives past events or only events from the time of subscription; this depends on the broker, retention, and subscription type.

### 2.3. Event Bus: Rule-Based Event Routing

An event bus is a layer that receives events and routes them to targets according to rules. Rules can be based on source, event type, attributes, or payload patterns. It is commonly used to connect services and applications in an event-driven architecture.

~~~mermaid
flowchart LR
    A[Booking Service] --> BUS[(Event Bus)]
    B[Payment Service] --> BUS
    C[Inventory Service] --> BUS
    BUS -->|BookingConfirmed| N[Notification]
    BUS -->|PaymentFailed| R[Reconciliation]
    BUS -->|InventoryChanged| S[Search Indexer]
~~~

An event bus is well suited when multiple sources emit different event types and need policy-driven routing to targets. A bus can support many rules and targets, but it generally should not be treated as a long-term event store or an arbitrary replay platform unless the product explicitly provides those capabilities.

### 2.4. Event Stream: A Sequence of Events Readable by Position

Event streaming treats events as a continuous data stream appended to a log/stream ordered within a defined scope, typically a partition. Consumers read events by offset or cursor; multiple consumer groups can read the same stream independently. Retention allows consumers to reread data within the configured time window.

~~~mermaid
flowchart LR
    P[Producers] --> K[(Stream / Topic)]
    K --> PG1[Partition 0]
    K --> PG2[Partition 1]
    K --> PG3[Partition 2]
    PG1 --> CG1[Consumer Group A]
    PG2 --> CG1
    PG3 --> CG1
    PG1 --> CG2[Consumer Group B]
    PG2 --> CG2
    PG3 --> CG2
~~~

Example: the system writes clickstream events, price changes, and booking state transitions to a stream. One consumer analyzes data in near real time; another builds an analytics warehouse. Each group advances its own offset and can reread data when results need to be recomputed within the retention window.

Streaming is well suited when:

- Data is generated continuously at high throughput.
- Multiple consumer groups need to read the same data independently.
- Ordered processing is needed within a partition scope.
- You need to replay/reprocess a range of historical data.
- You need to integrate stream processing, analytics, or materialized views.

A stream does not automatically guarantee that every consumer sees a global order; ordering is typically guaranteed only within a partition or a platform-defined scope.

## 3. Comparing Queues, Pub/Sub, Event Buses, and Streams

| Criterion | Queue | Pub/sub | Event bus | Event stream |
|---|---|---|---|---|
| Primary goal | Distribute work | Broadcast an event to multiple subscribers | Route events based on rules | Record and read a continuous sequence of events |
| Consumer model | Competing consumers are common | Multiple independent subscriptions | Multiple targets per rule | Multiple consumer groups |
| Retention | Per retention/visibility/dead-letter policy | Depends on broker/subscription | Depends on service; usually not a long-term replay store by default | Time- or size-based retention |
| Replay | Depends on service and message copies | Depends on subscription and retention | May be limited; check archive/replay capabilities | Usually supports rereading by offset within retention |
| Ordering | Can be FIFO or key-grouped depending on queue type | Depends on broker and subscription | Global ordering should not be assumed | Ordered within a partition |
| Consumer scaling | Multiple workers pull messages concurrently | Each subscription scales independently | Targets scale per service mechanism | Consumer groups share partitions |
| Use case | Background jobs, task processing | Notifications, fan-out | Cross-service integration | Clickstream, audit/event pipelines, analytics |

**Naming is not completely uniform across providers.** A pub/sub product might store messages and allow replay; an event bus service might support archiving; a queue might support fan-out via subscriptions. Compare concrete semantics and limits rather than relying solely on the service name.

## 4. Components in an Event Delivery Architecture

| Component | Role | Example |
|---|---|---|
| **Producer / publisher** | Creates messages or events | Booking Service emits BookingConfirmed |
| **Broker** | Receives, stores/buffers, and distributes messages | Managed queue, event bus, or streaming cluster |
| **Queue / topic / stream** | Logical destination receiving messages/events | booking-events, invoice-jobs |
| **Subscription** | Defines how a consumer or consumer group receives deliveries | Notification subscription |
| **Consumer / subscriber** | Receives and processes messages | Email worker |
| **Partition** | Splits a stream to scale and define ordering scope | Partitioned by bookingId |
| **Offset / cursor** | Position a consumer has read or committed in a stream | Offset 1,250 |
| **Consumer group** | Group of consumers sharing partition reads | Search indexer group |
| **DLQ (dead-letter queue)** | Holds messages that could not be processed after retry policy | booking-events-dlq |
| **Schema registry / contract store** | Manages event schemas and versions | BookingConfirmed v2 |

A simple architecture:

~~~mermaid
flowchart TB
    APP[Application services] --> PUB[Producer client]
    PUB --> BROKER[(Broker / Topic)]
    BROKER --> SUB[Subscription / Consumer group]
    SUB --> WORKER[Worker / Function]
    WORKER --> STORE[(Consumer data store)]
    WORKER -->|Retryable failure| RETRY[Retry policy / delayed queue]
    RETRY --> BROKER
    WORKER -->|Poison message| DLQ[(Dead-letter queue)]
    DLQ --> OPS[Alert + controlled redrive]
~~~

## 5. Messages, Commands, and Events

### 5.1. Message Is the Broad Concept

A message is the unit of data sent through a communication mechanism. It can be a command, event, request, response, or job. The message content alone does not determine semantics; producer and consumer must agree on its meaning.

### 5.2. Commands Request Actions

A command describes an action a consumer is asked to perform, usually directed at a specific owner.

Examples: ReserveAvailability, GenerateInvoice, SendEmail. The consumer can accept or reject the command after validating business rules.

### 5.3. Events Announce Facts That Have Occurred

An event describes a business occurrence that has already happened, usually named in the past tense:

- BookingConfirmed
- PaymentAuthorized
- CustomerProfileUpdated
- InventoryReleased

Consumers react to an event, but must not interpret an event as a directive forcing them to make an arbitrary change. BookingConfirmed means the booking has been confirmed by its owner; BookingConfirmationRequested is only a request to be processed.

### 5.4. Sample Event Envelope

~~~json
{
  "eventId": "evt_01JXY99",
  "eventType": "BookingConfirmed",
  "eventVersion": 1,
  "occurredAt": "2026-12-01T09:16:22Z",
  "producer": "booking-service",
  "tenantId": "tenant_7",
  "correlationId": "req_548",
  "data": {
    "bookingId": "booking_913",
    "listingId": "listing_42",
    "checkIn": "2026-12-10",
    "checkOut": "2026-12-12"
  }
}
~~~

An event contract should specify:

- **eventId:** unique identifier for a logical event, supporting deduplication.
- **eventType / eventVersion:** identifies the event type and schema version.
- **occurredAt:** time the business occurrence happened, with an explicit timezone; distinct from publish or consume time.
- **producer:** the system emitting the event.
- **tenantId:** data scope; consumers must still validate authorization and origin.
- **correlationId:** links steps belonging to the same business flow.
- **data:** contains only the fields consumers genuinely need.

Do not publish entire database records onto a topic. Oversized payloads containing unnecessary data increase costs, coupling, and data exposure risks.

## 6. Delivery Semantics: At-Most-Once, At-Least-Once, and Exactly-Once

### 6.1. At-Most-Once

A message is delivered at most once under the mechanism's semantics. If a failure occurs at an unfortunate moment, the message may be lost or left unprocessed. This model can be acceptable for ephemeral data, non-critical telemetry, or cases where losing some records is tolerable.

### 6.2. At-Least-Once

The system attempts to deliver a message at least once. If a consumer succeeds in processing but the acknowledgment is lost, the broker may redeliver it. This is the common semantics for queues and many event systems.

Consumers must tolerate duplicates. For instance, receiving the same BookingConfirmed twice should not issue two invoices or charge twice.

### 6.3. Exactly-Once

Some streaming/broker systems provide transactional or exactly-once mechanisms within a specific scope, such as between read and write operations inside the same platform. This **does not automatically guarantee end-to-end exactly-once** when a consumer calls a payment API, writes to a different database, or sends an email.

Practical designs typically combine:

1. Delivery that may repeat.
2. Events with stable identifiers.
3. Consumers recording processed markers.
4. Idempotent side effects.
5. State reconciliation when outcomes are uncertain.

### 6.4. Idempotent Consumer

A consumer can use an inbox table to record processed events within the same transaction as its data mutations:

~~~sql
BEGIN;

INSERT INTO processed_events(event_id, processed_at)
VALUES ('evt_01JXY99', CURRENT_TIMESTAMP)
ON CONFLICT (event_id) DO NOTHING;

-- Only execute business changes if the processed_events record
-- was newly inserted in this transaction.
-- If the event already exists, skip the duplicate side effect.

COMMIT;
~~~

The SQL snippet only illustrates the idea; exact syntax and how affected row counts are retrieved depend on the database. For external side effects like sending email or calling payment APIs, a local database transaction cannot span that external API. You need provider idempotency keys, outbox/inbox patterns, intermediate states, or reconciliation processes.

## 7. Acknowledgements, Visibility Timeouts, and Offsets

### 7.1. Acknowledgements in Queues

Some queues use a mechanism where the consumer receives a message and then acknowledges deletion/completion after processing. If the consumer crashes or fails to acknowledge before the deadline, the message can become available again for delivery to another consumer.

**Visibility timeout** is the duration during which a message is temporarily hidden from other consumers after being received, in services that support this model. If processing takes longer than the timeout without extending it, the message may be redelivered while the first consumer is still working.

Therefore:

- Set the visibility timeout appropriately relative to p95/p99 processing times and deadlines.
- Extend the timeout when legitimate work takes longer, if the service supports it.
- Acknowledge only after required side effects have committed according to the rules.
- Keep handlers idempotent because duplicates can still occur.

### 7.2. Offsets in Streams

In streaming, a consumer group typically tracks an offset/cursor. Consumers read from the next position and commit offsets according to client/broker semantics. Committing an offset before processing completes risks losing the ability to reprocess; committing only after processing can cause records to be reread if the consumer crashes.

A common approach is idempotent processing followed by committing the offset once results are durably persisted. When reading and writing are not in the same transaction, a failure window remains that must be handled.

### 7.3. Processing Order

FIFO queues or stream partitions can provide ordering within a defined scope. However, parallel consumers, retries, and separate partitions can cause completion order to differ from publish order.

If business logic requires ordering per bookingId, you can use bookingId as the message group/partition key as supported by the broker. Events with the same key then have the opportunity to be processed in order within a partition/group, though one slow consumer can bottleneck throughput for that key.

Do not rely solely on timestamps to establish business order when machine clocks can drift or events arrive late. You may need an aggregate version/sequence issued by the service owner.

## 8. Retries, Dead-Letter Queues, and Poison Messages

### 8.1. Controlled Retries

Transient errors such as network resets, 429, or 503 can be retried. Errors that waiting cannot fix—such as invalid schemas, missing permissions, or malformed data—should take a different handling path.

A retry policy typically needs:

- Classification of retryable vs. non-retryable errors.
- A maximum retry count or total duration limit.
- Exponential backoff and jitter.
- Concurrency limits to avoid overwhelming downstream services.
- Metrics for retry count, age, and post-retry success rate.

Unbounded retries can keep a message circulating indefinitely, creating backlogs and significant costs.

### 8.2. Poison Messages

A poison message is one that repeatedly fails due to its content or an unrecoverable processing condition. For example, a consumer cannot parse a new event version, data is missing a required field, or a record triggers a recurring logic error.

Without retry limits, a single poison message can tie up workers, block a FIFO group, or stall a partition.

### 8.3. Dead-Letter Queue (DLQ)

A DLQ holds messages that exceed delivery/retry policies for separate investigation and handling.

~~~mermaid
flowchart TD
    Q[(Main Queue)] --> C[Consumer]
    C --> OK{Processed?}
    OK -->|Yes| ACK[Acknowledge]
    OK -->|Transient error| RETRY[Retry with backoff]
    RETRY --> Q
    OK -->|Attempts exceeded| DLQ[(Dead-letter Queue)]
    DLQ --> ALERT[Alert / Inspect]
    ALERT --> FIX[Fix code, data or dependency]
    FIX --> REDRIVE[Controlled redrive]
    REDRIVE --> Q
~~~

A DLQ is not a place to forget messages. You must have:

1. An owner and alerts when the DLQ grows.
2. The ability to inspect metadata and errors without exposing sensitive data.
3. A process to determine root causes and fix code, configuration, or data.
4. Verification that consumers are idempotent before redriving.
5. Redrive rate limits to avoid overloading downstream systems.
6. Auditing of who redrove which messages, when, and with what outcome.

Do not bulk-redrive messages before verifying whether previous side effects already succeeded.

## 9. Ordering, Partitioning, and Consumer Scaling

### 9.1. Partition Keys

In an event stream, the partition key determines which partition a record enters according to the broker's algorithm. Key selection affects three things:

- **Ordering:** the same key typically lands in the same partition and preserves order within that partition.
- **Scalability:** evenly distributed keys help utilize multiple partitions.
- **Hot partitions:** an overly popular key can concentrate load onto a single partition.

For example, keying by bookingId works well if you need per-booking event ordering. Keying by a constant value puts every event into the same partition and breaks horizontal scaling.

### 9.2. Partition Count and Consumers

In common models, a consumer group generally cannot process in parallel beyond the number of assigned partitions; adding more consumers than partitions can leave consumers idle. Conversely, too few partitions limit throughput and parallelism.

Do not simply increase partition counts to handle more load without evaluating:

- Does the ordering key mapping change when partitions increase?
- Do consumers have enough capacity to process each partition?
- Can the broker handle the replication, storage, and network load?
- How does rebalancing affect latency and in-flight processing?
- Do quotas and retention need to be adjusted?

### 9.3. Queues and Competing Consumers

With queues, adding workers can increase throughput if tasks are independent and downstream systems have spare capacity. If every message updates the same record or calls a low-rate-limit API, adding workers will not fix the bottleneck; you need batching, concurrency limits, or workload partitioning.

## 10. Event Schemas and Evolution

### 10.1. Versioning

Event schemas need clear versions and compatibility policies. Some changes can be compatible depending on consumers:

- Adding optional fields with clear defaults/semantics.
- Adding new event types that older consumers are allowed to ignore.
- Extending an enum if consumers have safe handling for unknown values.

Changes that commonly break contracts:

- Removing or renaming a field currently in use.
- Changing a data type, unit of measurement, or currency.
- Changing the meaning of an event or state.
- Turning an optional field into a required field.
- Changing the partition key or ordering semantics consumers rely on.

### 10.2. Expand–Migrate–Contract

1. **Expand:** add new fields/event versions while preserving the ability to read old ones.
2. **Migrate:** update consumers incrementally, testing against both old and new data.
3. **Observe:** check whether legacy consumers are still reading old events and monitor parsing errors.
4. **Contract:** after the announced support period, stop emitting the old schema and retire legacy consumers.

Events stored within retention may be replayed days or weeks later. Consumers must know how to read older versions or have an appropriate translation step; you cannot assume every record in a topic uses the latest schema.

### 10.3. Schema Registry

A schema registry stores event definitions and versions, validating producers and consumers against compatibility policies. A registry helps catch schema errors early, though it cannot verify that business semantics are right. Consumers still need contract and behavior tests.

## 11. Transactional Outbox and Guaranteed Event Publishing

### 11.1. The Dual-Write Gap

Suppose Booking Service writes the CONFIRMED status to its database and then publishes BookingConfirmed to the broker. Two failure scenarios arise:

- The database commit succeeds, but the service crashes before publishing: consumers never receive the event.
- Publishing succeeds, but the database transaction rolls back: consumers receive an event describing a state that was never committed.

This is the **dual-write** problem between two systems not participating in the same transaction.

### 11.2. Transactional Outbox

An outbox stores both the business record and the event record to be published within the same transaction of the service's database:

~~~sql
BEGIN;

UPDATE bookings
SET status = 'CONFIRMED'
WHERE booking_id = 'booking_913';

INSERT INTO outbox_events(event_id, event_type, payload, created_at)
VALUES (
  'evt_01JXY99',
  'BookingConfirmed',
  '{"bookingId":"booking_913"}',
  CURRENT_TIMESTAMP
);

COMMIT;
~~~

A separate publisher or CDC process reads the outbox and sends events to the broker. If sending succeeds but the publisher crashes before marking it as sent, the event may be sent again. Consumers therefore still need idempotency/deduplication.

A transactional outbox prevents business state from committing while an event is lost in the dual-write gap; it **does not automatically guarantee end-to-end exactly-once delivery**.

### 11.3. Inbox and Deduplication

A consumer can record eventId in an inbox/processed_events table within the same transaction as its local data update. When receiving a duplicate event, the consumer skips side effects that have already completed.

For side effects outside the database (email, payment, SMS), you also need idempotent APIs, a subsequent outbox, or reconciliation. An external call may succeed while its response is lost; relying on the consumer's database transaction alone is insufficient.

## 12. Security and Event Data Governance

### 12.1. Authentication and Authorization

- Producers may only publish to required topics/queues.
- Consumers may only subscribe to appropriate streams.
- Isolate permissions by environment, tenant, and event type where the platform supports it.
- Protect broker connections with TLS and credentials/workload identities.
- Rotate secrets and avoid storing credentials in payloads.
- Audit changes to topics, subscriptions, retention, ACLs, and consumer configurations.

Do not grant a worker permission to read every topic simply because they are deployed in the same cloud account.

### 12.2. Payload Minimization

Events should contain only the attributes consumers need—not full customer profiles, payment details, or identity documents. When complete data is needed, consumers can call the owner service after authorization or use a suitably scoped, time-bound reference.

### 12.3. Retention and Data Residency

Event streams, queues, DLQs, archives, logs, and backups can all contain business data. You must define:

- Regions storing brokers/topics and replicas.
- Retention durations and deletion mechanisms.
- Who can read or replay historical data.
- Which contents are encrypted and who manages the keys.
- Which payloads are permitted to flow to consumers or third parties in other regions.

Having the primary database in one region does not automatically guarantee that the event bus or DLQ stays within that boundary. If data has geographic constraints, evaluate the entire event path and all replicas.

## 13. Backpressure, Flow Control, and Overload Handling

### 13.1. Queue Depth Is a Key Signal

If producers generate 900 messages/second while consumers process 700 messages/second:

~~~text
Backlog growth = 900 - 700 = 200 messages/second

After 10 minutes:
Backlog ≈ 200 * 600 = 120,000 messages
~~~

If load remains constant with no limits, the backlog will keep growing. Only scale consumers when downstream dependencies have sufficient capacity; otherwise, adding workers can overload databases or external APIs.

### 13.2. Backpressure and Rate Limiting

Common measures include:

- Capping concurrency/worker counts.
- Rate-limiting producers or ingress APIs.
- Batching messages when business semantics permit.
- Pausing subscriptions/consumers during downstream outages, if supported.
- Using retries with backoff and circuit breakers.
- Prioritizing critical messages and deferring lower-urgency background work.
- Setting alerts on backlog depth and oldest-message age thresholds.

### 13.3. Queue Buffering Differs from Long-Term Processing Capacity

Queues help absorb short spikes, but if average ingress rate consistently exceeds processing rate, the queue only delays an incident by accumulating backlog. You must increase capacity, optimize processing, eliminate redundant events, or adjust business requirements.

## 14. Observing and Operating Event-Driven Systems

### 14.1. Metrics to Monitor

| Category | Metric | Purpose |
|---|---|---|
| Producer | Publish rate, publish errors, latency | Detect when producers fail to send events |
| Broker | Queue depth, ingress/egress throughput, throttling | Monitor capacity and backlog |
| Consumer | Processing rate, error rate, retry count | Evaluate processing health and failures |
| Lag | Consumer lag, age of oldest message | Know how far behind consumers are |
| Delivery | Redelivery count, ack timeout, DLQ depth | Detect duplicates and poison messages |
| Stream | Offset, partition utilization, rebalance | Track progress and load distribution |
| Data quality | Schema failure, invalid events, duplicate events | Detect contract violations |
| Cost | Storage, retention, requests, throughput, egress | Track spending |
| Security | Unauthorized publish/consume, ACL changes | Detect anomalous access |

### 14.2. Correlation and Tracing

Every event should carry an eventId and correlationId. Trace context can be propagated using a suitable tracing standard to link producer, broker, and consumer. Do not use eventId as a business key if a single business operation emits multiple events.

Logs should include enough information for investigation while avoiding sensitive payloads. Metric labels should avoid high-cardinality values such as userId, bookingId, or eventId.

### 14.3. Runbook for Handling Backlogs and DLQs

A runbook should specify:

1. Identify the affected topic/queue, subscription, consumer group, and environment.
2. Check publish rate, processing rate, lag, and oldest message age.
3. Inspect error types, schema versions, dependencies, and recent deployments.
4. Decide whether to scale, throttle input, pause, roll back, or fix dependency failures.
5. Verify idempotency before redriving the DLQ or replaying the stream.
6. Monitor backlog reduction, business catch-up, and data reconciliation.

Do not redrive an entire DLQ before identifying the root cause or verifying prior side effects.

## 15. Choosing a Model by Problem Statement

| Need | Suitable starting model | Rationale |
|---|---|---|
 Send an email when a booking is confirmed | Queue or dedicated subscription | Can be processed asynchronously, retried, and worker-scaled |
 Multiple systems receive BookingConfirmed | Pub/sub or event bus | Fan-out to independent consumers |
 Route many domain event types to many targets | Event bus | Rule-based routing by type/source/attribute |
 Store clickstream for analytics to reread | Event stream | Retention, partitions, consumer groups, and replay |
 Process independent jobs with a worker pool | Queue | Competing consumers and buffering |
 Build multiple projections from the same event history | Event stream or broker with suitable retention | Independent consumers and reprocessing capability |
 Coordinate stateful business flows with compensation | Workflow service combined with queues/events | Workflow tracks progress; broker delivers messages/events |

Do not force every flow onto a single messaging platform just to reduce service count. Conversely, do not create a new queue/topic for every tiny function if governance and observability overhead outweighs the value.

## 16. Architecture Example: Booking Platform

Suppose when a booking is confirmed, the system needs to send notifications, update search, record analytics, and send data to a customer care system.

~~~mermaid
flowchart TB
    B[Booking Service] --> DB[(Booking DB)]
    DB --> OUT[Transactional Outbox / CDC]
    OUT --> BUS[(Event Bus)]
    BUS -->|BookingConfirmed| NQ[(Notification Queue)]
    BUS -->|BookingConfirmed| SEARCH[Search Projection Consumer]
    BUS -->|BookingConfirmed| ANALYTICS[Analytics Stream]
    BUS -->|BookingConfirmed| CRM[CRM Integration]
    NQ --> NW[Notification Workers]
    NW --> EMAIL[Email provider]
    NW --> SMS[SMS provider]
~~~

### 16.1. Division of Responsibilities

| Component | Responsibility | Mechanisms to consider |
|---|---|---|
| Booking Service | Decides booking state and emits events after commit | Outbox/CDC, event contract |
| Event Bus | Routes events to appropriate targets | Rules by eventType/tenant/attribute |
| Notification Queue | Buffers notification delivery jobs | Retries, visibility timeout, DLQ |
| Search consumer | Updates search projection | Idempotency, event versioning, rebuilds |
| Analytics stream | Stores event sequence for analysis | Partitioning, retention, consumer groups |
| CRM integration | Transforms and sends data to partner system | Schema mapping, rate limits, auditing, data minimization |

### 16.2. Why Not Have Booking Call Everything?

If Booking called Notification, Search, Analytics, and CRM synchronously:

- Booking request latency depends on all those systems.
- A failure in an auxiliary system could prevent booking from responding even after committing.
- Booking would have to manage retries and state for multiple services it does not own.
- Adding more integrated systems increases coupling and makes independent scaling difficult.

Emitting an event after a booking is confirmed decouples post-processing tasks. However, core business steps like reserving inventory/payment still need coordination and confirmation before emitting BookingConfirmed. Events do not replace business transactions.

### 16.3. Sample Failure Handling

- **Notification provider failure:** the queue retains the job, workers perform bounded retries; once exceeded, route to DLQ and alert.
- **Search consumer schema error:** pause or move failing messages to DLQ per policy; deploy a compatible consumer and perform a controlled redrive.
- **Slow analytics consumer:** increase partitions/consumers if broker and downstream allow; monitor lag and retention to prevent records from expiring before processing.
- **Booking commits but publishing is delayed:** outbox publisher keeps emitting; consumers tolerate duplicates.
- **CRM quota exhausted:** rate-limit calls, retry per Retry-After, and buffer backlog; do not let CRM slow down booking transactions.

## 17. Trade-offs Under Well-Architected Principles

| Pillar | Design question | Trade-offs to weigh |
|---|---|---|
| **Operational Excellence** | Who owns topics, schemas, consumers, DLQs, and runbooks? | More brokers/topics increase flexibility but also increase resources to monitor |
| **Security** | Who can publish/consume, what data do events contain, and where are they stored? | Broad fan-out eases integration but widens the data access surface |
| **Reliability** | How are duplicates, ordering, retries, broker outages, and replays handled? | Higher durability/replication improves reliability but can increase latency and cost |
| **Performance Efficiency** | Are throughput, partitioning, consumer concurrency, and payloads well-sized? | Batching/fan-out boost throughput but can raise latency or create hot partitions |
| **Cost Optimization** | What do retention, storage, requests, egress, DLQs, and idle consumers cost? | Longer retention supports replay but increases storage; more subscriptions multiply deliveries |
| **Sustainability** | Are duplicate/redundant events, polling, and bloated payloads avoided? | Eliminating wasteful events and retention saves compute and network transfer |

A managed broker reduces infrastructure administration, but customers still must manage schemas, permissions, retries, consumers, retention, and business error handling.

## 18. Common Mistakes

| Mistake | Consequence | Improvement |
|---|---|---|
| Treating queues and pub/sub as identical | Consumers miss event copies or jobs are processed wrongly | Clarify competing consumers vs. fan-out subscriptions |
| Assuming brokers never deliver duplicates | Repeated side effects, duplicate emails or double charges | Idempotency and deduplication |
| Committing state then publishing events in two separate operations | Lost events or phantom events | Transactional outbox/CDC |
| Using timestamps to guarantee order | Late-arriving events overwrite newer state | Versions/sequences and ordering keys |
| Retrying indefinitely | Poison messages cause backlogs and rising costs | Retry budgets, DLQs, and alerts |
| Redriving DLQs without checks | Repeated side effects or downstream overload | Verify idempotency, fix root cause, and rate-limit redrive |
| Choosing a heavily skewed partition key | Hot partitions and low throughput | Evaluate key distribution and load per tenant/entity |
| Storing unnecessary sensitive payloads | Data exposure risks and increased retention obligations | Data minimization, encryption, and access control |
| Not monitoring consumer lag | Stale data or retention expiration before processing | Alert on lag/oldest-message age |
| Using an event stream as the default operational database | Hard to update, query, and enforce invariants | Separate system of record from event log |

## 19. Applied Exercises

### Exercise A — Queue or Pub/Sub?

A booking needs one invoice generated. Only one worker in a pool should perform the task, with workers sharing the load.

**Question:** Which model should you start with?

**Hint:** A queue with competing consumers is suitable when each job only needs to be processed by one consumer. Consumers must still be idempotent because duplicate deliveries can occur.

### Exercise B — One Event, Three Consumers

When a booking is confirmed, Notification, Search, and Analytics all need to receive the event independently.

**Question:** How do you prevent one slow consumer from blocking the others?

**Hint:** Use pub/sub or an event bus with independent subscriptions, or a stream with separate consumer groups. Each consumer has its own backlog, retries, and monitoring per broker capabilities.

### Exercise C — Duplicate After Timeout

A consumer updates its database successfully, but the acknowledgment is lost. The broker redelivers the same event.

**Question:** What should the consumer do?

**Hint:** Store eventId in an inbox/processed_events table within the same transaction as the business update; if the event was already processed, skip repeating the side effect. For external APIs, use idempotency keys or reconciliation.

### Exercise D — Booking Ordering

A booking emits BookingConfirmed and then BookingCancelled. The two events can be processed in parallel, and the consumer receives Cancelled before Confirmed.

**Question:** How do you prevent the projection from reverting to an older state?

**Hint:** Partition by bookingId, use aggregate versions/sequences, validate legal state transitions, and handle late-arriving older events. Do not rely solely on arrival time.

### Exercise E — Growing Backlog

A producer emits 1,200 messages/s while consumers process 900 messages/s for 15 minutes.

**Question:** Roughly how many messages are added to the backlog?

**Hint:** The difference is 300 messages/s; over 900 seconds, the backlog grows by roughly 270,000 messages assuming no change in input, processing rate, or message drops. Address the bottleneck and check retention limits.

### Exercise F — Unparseable Event

A producer emits a new schema version; an older consumer does not recognize a required field and fails repeatedly.

**Question:** What process is required before redriving?

**Hint:** Route failing messages to the DLQ per policy, inspect schema compatibility, deploy a compatible consumer, test both old and new versions, then redrive with bounded concurrency and verify idempotency.

## 20. Pre-Deployment Checklist for Event Architecture

- [ ] Identified whether each message is a command, event, request, or job, along with its emitting/receiving owners.
- [ ] Selected queue, pub/sub, event bus, or stream based on delivery, fan-out, replay, ordering, and retention needs.
- [ ] Events include required schema/version, eventId, occurredAt, producer, and correlation IDs.
- [ ] Payloads are minimized and contain no secrets or unnecessary sensitive data.
- [ ] Producers/consumers have least-privilege IAM/ACL permissions and secured connections.
- [ ] Consumers are idempotent; duplicates, post-commit timeouts, and external side effects are reconciled.
- [ ] Bounded retries, backoff/jitter, and visibility timeout/ack or offset semantics are clearly understood.
- [ ] Ordering/partition keys are appropriate; hot partitions and consumer scaling have been evaluated.
- [ ] DLQs have owners, alerts, investigation procedures, fixes, and controlled redrive processes.
- [ ] Outbox/CDC has been evaluated for critical dual-write paths.
- [ ] Metrics cover publish rate, consumer lag, oldest-message age, retries, DLQ depth, and error rates.
- [ ] Retention, archiving, backups, regions, and data deletion policies are defined.
- [ ] Quotas, throughput, concurrency, storage, egress, and costs have been estimated.
- [ ] Tested duplicates, out-of-order events, broker outages, poison messages, replays, and traffic spikes.
- [ ] Runbooks, service owners, and schema/contract review cycles are established.

**Core takeaway:** queues typically distribute work; pub/sub broadcasts events to multiple subscribers; event buses route events by rules; event streams store event sequences so multiple consumers can read at their own pace and replay within retention. Whichever model you choose, the system still requires clear contracts, idempotent consumers, duplicate and error handling, data governance, backlog observability, and recovery testing. That is the foundation for scaling an event architecture while preserving correctness and operability.
