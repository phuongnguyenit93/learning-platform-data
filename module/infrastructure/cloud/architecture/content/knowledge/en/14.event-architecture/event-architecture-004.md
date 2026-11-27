# Delivery Semantics, Duplicates, and the Limits of Exactly-Once

## Learning Objectives

In an *event-driven architecture*, components communicate through events stored, transmitted, and processed via brokers, queues, or event logs. Whether a message has been sent, acknowledged by the broker, received by a consumer, or completed at the business level are distinct milestones. Failing to distinguish them makes systems prone to losing events, duplicating processing, or falsely claiming that transactions occurred exactly once.

This lesson belongs to the **Event Architecture** chapter, focusing on **delivery semantics, duplicate delivery, processing order, and the limits of exactly-once**. This is the foundation for designing systems that recover cleanly when processes crash, networks flake, consumers time out, brokers redeliver messages, or downstream services fail to return clear outcomes.

After this lesson, you will be able to:

- Distinguish at-most-once, at-least-once, and exactly-once according to their guaranteed scope.
- Describe the milestones of publish, persist, deliver, acknowledge, commit, and business completion.
- Explain why a message can be delivered or processed multiple times even when a producer sends it only once.
- Design idempotent consumers, deduplication, inbox/outbox patterns, and transactional boundaries.
- Distinguish broker/stream-processor-scoped exactly-once from end-to-end business effects.
- Handle ordering, retries, poison messages, visibility timeouts, rebalances, and replays.
- Define SLIs/SLOs, fault testing, observability, and cost models for event-driven systems.
- Evaluate solutions across reliability, security, performance, cost, and operability in **Cloud Architecture**.

## 1. Why Do Delivery Semantics Matter?

Suppose a booking application records a paid booking. After the database transaction commits, the system emits BookingConfirmed to send an email, update inventory, and record analytics data.

Several scenarios can happen:

- The producer writes the booking, then the process crashes before publishing the event.
- The broker stores the event, but the publish acknowledgment is lost; the producer does not know whether the event was persisted.
- The broker delivers the event to a consumer; the consumer executes the side effect, then crashes before acknowledging.
- The consumer acknowledges before the database transaction commits; the process crashes and the event is never redelivered.
- The consumer finishes processing, but the network ACK is lost, so the broker redelivers the event.
- The consumer receives two copies due to producer retries or broker redelivery.
- Two events for the same booking arrive out of business order.

Therefore, "sending an event once" is not synonymous with "every subscriber executes its side effect once."

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant B as Broker
    participant C as Consumer
    participant D as Database
    P->>B: Publish event E
    B-->>P: Publish ack
    B->>C: Deliver E
    C->>D: Commit side effect
    Note over C,D: Process can crash after commit
    C--xB: ACK lost
    B->>C: Redeliver E
    C->>D: Detect duplicate
    C-->>B: ACK after confirming already processed
~~~

The crux is that **the broker and consumers do not share a single transaction with all external systems**. A lost ACK leaves the broker uncertain whether the consumer finished. From the broker's viewpoint, redelivery protects the message; from the business viewpoint, redelivery causes duplicates if the consumer is not safe to re-run.

## 2. Distinguishing Publish, Deliver, Acknowledge, and Business Processing

An event passes through many milestones. You must define what each component commits to at each milestone.

| Milestone | Meaning | What cannot be concluded yet |
| --- | --- | --- |
| Event created | Producer creates the event in memory or prepares the payload | The event is not necessarily durable yet |
| Publish sent | Producer sends the request to the broker | The broker may not have recorded it yet |
| Broker confirms publish | Broker returns ACK per configured semantics | Consumers have not necessarily received or processed it |
| Broker persists | Message is stored per durability policy | Does not guarantee all subscribers have processed it |
| Deliver | Broker transfers the message to a consumer | The consumer may not have finished |
| Consumer receives message | Process has received the payload | Side effects have not necessarily committed |
| Side effect committed | Database or external system has applied the change | ACK may not have been sent/recorded yet |
| Acknowledge/offset commit | Consumer tells the broker the message was processed up to a point | Downstream business steps are not necessarily finished |
| Business completion | Final business condition is achieved and verified | Must rely on business state, not just broker metrics |

For example, a queue may be configured to delete a message when the consumer ACKs. If the consumer ACKs before committing to the database, a crash can lose the side effect because the broker will not redeliver. If the consumer commits to the database before ACKing, a crash in between can cause duplicate delivery. Consumers must handle that second scenario safely.

### 2.1. ACKs Are Not Always the Same

Some brokers use per-message ACK/NACK; some use visibility timeouts and message deletion; log/partition systems like Kafka use offset commits. Some brokers confirm publishes, while consumer acknowledgment is a separate flow.

When reading service documentation, distinguish:

- **Publisher confirm:** under what configuration did the broker accept/persist the publish?
- **Consumer acknowledgement:** under what conditions can a message be deleted or never redelivered?
- **Offset commit:** up to which offset has the consumer recorded read progress?
- **Replication acknowledgement:** how many replicas or what durability level is confirmed?
- **Transaction commit:** within what scope are outputs and progress committed atomically?

Do not use the generic term ACK in ADRs or runbooks. Specify who acknowledges, what is being acknowledged, and when a message is considered safe to drop.

## 3. Three Fundamental Delivery Semantics

### 3.1. At-Most-Once: Up to One Time

With at-most-once, the system prioritizes avoiding repeated messages. When failures occur at certain points, messages may be lost or go unprocessed.

For example, a consumer reads a message and ACKs/deletes it before executing side effects. If the process crashes after the ACK but before writing to the database, the broker has no reason to redeliver the message.

**Benefits:** avoids or minimizes duplicate processing and can be simpler for workloads that tolerate dropping occasional samples.

**Trade-offs:** messages/side effects can be lost on failure. Unsuitable for financial transactions, reservations, or critical events without another reconciliation mechanism.

At-most-once does not mean every message is always processed once. It can be **zero times** if a message is lost or skipped.

### 3.2. At-Least-Once: One or More Times

With at-least-once, the broker/consumer is designed to redeliver when proper confirmation is not received. This lowers the risk of losing messages, though duplicates can occur.

Example:

1. Consumer receives an event.
2. Consumer writes a payment record to the database successfully.
3. Consumer crashes before ACKing.
4. Broker redelivers the event.
5. A second consumer receives the same event again.

If the side effect is not idempotent, a balance or invoice count could increment twice.

**Benefits:** suited for critical business operations when paired with deduplication, idempotency, and reconciliation.

**Trade-offs:** requires designing for duplicate handling, retries, poison messages, and tracking processed state. This is the standard semantics in most queue systems because avoiding lost messages takes priority.

### 3.3. Exactly-Once: Specify "Once" Within What Scope

Exactly-once typically describes a stronger guarantee: an outcome is reflected exactly once within **a defined transaction and system boundary**. However, it does not automatically span across every broker, consumer, database, external API, and human operator.

Different scopes exist:

- The broker avoids creating duplicates under specific configuration conditions.
- The producer retries, while the broker recognizes the same producer sequence/transaction.
- A stream processor commits output once via the framework's checkpoints/transactions.
- A consumer updates a single database once using unique keys/idempotency.
- End-to-end business logic issues only one invoice or records only one debit.

These guarantees are not equivalent. Ask: **exactly-once with respect to which entity, within which transaction boundary, under which failure modes, and including which downstream systems?**

### 3.4. Comparison

| Criterion | At-most-once | At-least-once | Exactly-once within a defined scope |
| --- | --- | --- | --- |
| Duplicate delivery | Usually avoided by not redelivering | Can occur | Eliminated within the guaranteed mechanism's scope |
| Message loss on failure | Can occur | Bounded by durability/retention and recovery policies | Depends on transaction scope and durability |
| Idempotent consumer | Still helpful | Critical | Still needed for effects outside the boundary |
| Complexity | Can be lower | Higher due to retries/dedup | High and conditional |
| Suitable example | Telemetry where some sample loss is tolerable | Booking events, invoices, data updates | Stream transactions or DB operations with unique keys |
| What must be clarified | Acceptable loss rate? | How are duplicates prevented? | At which layer is exactly-once enforced, and does it include external side effects? |

No option is universally best. The goal is to choose semantics matching data criticality and build the safeguards needed to uphold business invariants.

## 4. How Does Duplicate Delivery Happen?

### 4.1. Producer Retries After Lost Responses

A producer sends an event, the broker persists it successfully, but the ACK response is lost over the network. The producer times out and resends. The broker may see two independent publishes if the protocol lacks an idempotent producer or proper deduplication key.

### 4.2. Consumer Finishes Processing but ACK Fails

The consumer commits to the DB, but the ACK never reaches the broker or is lost. Seeing the message unacknowledged, the broker redelivers it.

### 4.3. Visibility Timeout Expiration

In some queues, a message becomes invisible for a lease/visibility timeout after being received. If a worker takes longer than that duration without extending the lease, the message can reappear and be picked up by another worker while the first is still running.

### 4.4. Consumer Rebalances or Restarts

In partitioned/offset systems, a consumer processes a record without yet committing its offset. When the process restarts or the partition is reassigned to another consumer, the record is reread from the old offset. If output was already committed earlier, duplicate side effects can occur.

### 4.5. Replay, Redrive, and Backfill

Operators deliberately replay events from a DLQ, archive, or earlier offset. Some events may already have succeeded during the initial run. Without distinguishing replays from fresh events, the system can double side effects.

### 4.6. Producer Emits a New Event for the Same Operation

Even when the broker never duplicates a message, a producer might emit two distinct event IDs for the same operation due to client retries. Deduplicating solely by message ID will miss two events that carry different IDs but represent the same business intent.

At least two layers of duplicates must be handled: duplicates at the **message/event ID** level and duplicates at the **business operation/key** level.

## 5. Idempotent Consumers: The Foundation for At-Least-Once

An idempotent consumer can receive a message multiple times while leaving the final business state identical to processing it once.

### 5.1. Designing an Inbox/Deduplication Table

Sample inbox table:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    received_at TIMESTAMP NOT NULL,
    processed_at TIMESTAMP NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Within the same database transaction:

1. Attempt to insert the consumer_name + event_id pair.
2. If a unique constraint indicates it already exists and the event was already processed, skip the side effect.
3. If the insert succeeds, apply the business changes.
4. Mark processed and commit.
5. Only after committing, ACK the message / commit the offset according to broker semantics.

A unique constraint acts as synchronization across workers; merely running a SELECT before INSERT is insufficient because two consumers can both read "not found" and both write. Database uniqueness constraints resolve the race condition at the storage layer.

### 5.2. Same Transaction Is Essential

If a consumer writes the inbox in database A and updates business state in database B, the two operations are not atomic. It could write the inbox successfully and then fail updating B; the next redelivery would be skipped even though the business change never completed.

Conversely, updating business state first and then failing to write the inbox allows redeliveries to repeat side effects.

Remediation options:

- Keep the inbox record and business state inside the same database transaction.
- Use a transaction coordinator if supported and its trade-offs are acceptable.
- Use workflows/outbox/sagas to coordinate explicit, recoverable steps.
- Design business operations to be naturally idempotent via unique keys or conditional updates.

### 5.3. Booking State Update Example

~~~sql
BEGIN;

INSERT INTO consumer_inbox (
    consumer_name, event_id, received_at, processed_at
)
VALUES (
    'inventory-projection', 'evt-booking-1842', CURRENT_TIMESTAMP, NULL
)
ON CONFLICT (consumer_name, event_id) DO NOTHING;

-- Application checks whether the insert actually created a new row.
-- Only if it is a new event, update the projection.

UPDATE inventory_projection
SET confirmed_bookings = confirmed_bookings + 1
WHERE room_id = 'room-28';

UPDATE consumer_inbox
SET processed_at = CURRENT_TIMESTAMP
WHERE consumer_name = 'inventory-projection'
  AND event_id = 'evt-booking-1842';

COMMIT;
~~~

This is a pseudo-example using PostgreSQL-like syntax; real code must inspect the row count/RETURNING clause to determine whether the insert succeeded or conflicted, and run the UPDATE only if the event has not yet been processed. Do not run the UPDATE unconditionally as shown in the simplified snippet if you want duplicate protection; that check belongs in application logic or a specific CTE/transaction.

## 6. Idempotency Keys and Business Invariants

### 6.1. Message ID Alone Is Not Enough for Every Flow

Suppose a client submits an invoice issuance request twice, and the producer creates two events:

- eventId = evt-A, orderId = order-123
- eventId = evt-B, orderId = order-123

A consumer deduplicating purely by eventId will process both. If the business rule says each order has only one valid invoice, you need a **business key** such as orderId + invoice type or an agreed idempotency key.

| ID/Key | Purpose | Example |
| --- | --- | --- |
| eventId | Identifies one specific event instance | evt-2026-0001 |
| correlationId | Links activities across the same journey | corr-checkout-91 |
| causationId | Identifies the event/command that caused the current event | cmd-create-booking-42 |
| aggregateId | Identifies the business entity | booking-123 |
| businessKey | Prevents repeating a business operation | invoice:order-123 |
| idempotencyKey | Identifies retries of the same request/task | client-request-9e2 |

These fields relate to one another but do not replace each other. Do not use correlationId as a unique key if one journey legitimately spawns multiple business operations.

### 6.2. Unique Constraints and Conditional Writes

Example invoice table enforcing one invoice type per order:

~~~sql
CREATE UNIQUE INDEX uq_invoice_order_type
ON invoices(order_id, invoice_type);
~~~

When two workers try to issue the invoice concurrently, one transaction commits first; the other hits a conflict and can read the existing result. This enforces the invariant right where data lives.

For inventory, you can use conditional updates such as decrementing quantity only when sufficient stock remains. For money transfers, you need a unique ledger entry ID or transaction key; never perform unchecked balance additions.

**Idempotency should reflect business invariants**, not merely the mechanics of storing event IDs.

## 7. Transactional Outbox: Preventing Lost Events After Database Writes

A common bug occurs when an application does:

1. Commit booking in the database.
2. Publish BookingCreated to the broker.

If the process crashes between steps 1 and 2, the booking exists but the event is never emitted. If it publishes first and the database rolls back, consumers receive an event for a booking that does not exist.

### 7.1. The Outbox Pattern

Within the same transaction that writes the booking, the producer inserts a row into an outbox table:

~~~sql
BEGIN;

INSERT INTO bookings(id, status)
VALUES ('booking-123', 'CONFIRMED');

INSERT INTO outbox_events(
    event_id, aggregate_id, event_type, payload, created_at
)
VALUES (
    'evt-001',
    'booking-123',
    'BookingConfirmed',
    '{"bookingId":"booking-123"}',
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

A relay reads unpublished outbox rows and sends them to the broker. After receiving appropriate publisher confirmation, the relay marks them published or advances a watermark. If the relay crashes after the broker receives the event but before updating the outbox, the relay may publish again. Consumers therefore still need idempotency.

~~~mermaid
flowchart LR
    APP["Command handler"] --> TX["DB transaction"]
    TX --> B[("Business state")]
    TX --> O[("Outbox table")]
    O --> RELAY["Outbox relay / CDC"]
    RELAY --> BROKER[("Event broker")]
    BROKER --> C["Consumers"]
    C --> INBOX[("Inbox + business state")]
~~~

The outbox solves **atomicity between business state and the intent to emit an event** within the same database transaction. It does not create end-to-end exactly-once delivery on its own, because the publish/relay can still repeat and consumers can still reprocess.

### 7.2. Polling Relay vs. CDC

- **Polling relay:** a worker periodically queries unpublished outbox rows, fetches in batches, and publishes. Requires indexes, locking/claiming, state management, and cleanup.
- **Change Data Capture (CDC):** reads database transaction logs to emit events. Reduces polling overhead, but requires managing connectors, offsets, schema evolution, lag, and recovery.
- **Managed integration:** cloud services may support change capture or event routing; verify actual delivery semantics, retries, ordering, and durability.

Do not delete outbox rows immediately after publishing if you need auditing or replay. Retention and archiving must balance storage size, cost, and investigation needs.

## 8. Timely Consumer ACK and Offset Commits

General principle: **never ACK/commit progress before the outcomes you want to protect are durably committed.**

### 8.1. Message Queues with Visibility Timeouts

For queues using visibility timeouts:

1. Consumer receives the message; broker temporarily hides it.
2. Consumer processes and commits business state.
3. Consumer deletes/ACKs the message.
4. If processing exceeds the timeout, consumer extends visibility if the platform supports it.
5. If the consumer crashes, the message reappears after the lease expires.

A lease that is too short causes duplicates; a lease that is too long delays crash recovery. Choose timeouts based on duration distributions and add lease extension for long-running jobs. Note that a lease is not an absolute exclusive lock if a stalled worker keeps running after its lease expires.

### 8.2. Logs/Partitions and Offsets

With append-only log brokers, consumers read records per partition. Offset commits mark progress; if committed after side effects, restarts may reread records. This is standard at-least-once behavior.

Committing offsets before side effects reduces duplicates but risks losing processing on crashes. Only use that approach when at-most-once is acceptable or state can be reconstructed from another source.

### 8.3. Batch Acknowledgements

When a consumer processes a batch, some records may succeed while others fail. Define whether ACKs happen per message, per batch, or by contiguous offset. For ordered logs, never commit an offset past an unfinished record if you need to preserve ordering semantics. Test mid-batch failures, partial successes, and replays.

## 9. Ordering: Ordered Processing Is Not Default

An event broker may guarantee order within a scope such as a partition, message group, or session, though not necessarily system-wide.

Consider two events: BookingCreated and BookingCancelled. If Cancelled reaches the consumer before Created, a projection can end up in the wrong final state unless versions and valid state transitions are enforced.

| Scope | Characteristics | Trade-off |
| --- | --- | --- |
| Entire topic/queue | Global ordering if supported by service | Hard to scale in parallel; lower throughput |
| Per partition/key | Order preserved within a partition/key | Requires choosing the right partition key; risk of hot partitions |
| Per entity/aggregate | Events for the same booking stay sequential | Different entities can run in parallel |
| Unordered | Consumers tolerate events arriving in any order | Requires versioning, state machines, and reconciliation |

### 9.1. Partition Keys

Choosing aggregateId as the partition key routes events for the same booking into the same partition in models supporting per-partition ordering. However, skewed partition keys can create hot partitions. Increasing partition counts can also alter key mappings in some systems and disrupt ordering unless migration is carefully planned.

### 9.2. Versioning and Optimistic Concurrency

Each aggregate can carry a monotonically increasing version:

~~~json
{
  "eventId": "evt-103",
  "aggregateId": "booking-123",
  "aggregateVersion": 7,
  "eventType": "BookingCancelled"
}
~~~

Consumers apply only the expected next version; stale or duplicate events are ignored, while events with version gaps can be held or trigger a state reload/replay. Exact rules depend on the domain. Never rely solely on timestamps because clock skew, event time, and commit order can diverge.

## 10. Poison Messages, Retries, and DLQs

A poison message is a message that consistently fails due to invalid payloads, unsupported schemas, missing data, or processing bugs. Endless retries will not make it succeed and can block an entire partition or inflate queue backlogs.

| Failure type | Example | Handling approach |
| --- | --- | --- |
| Transient | Timeout, HTTP 503, temporary throttling | Retry with backoff and jitter |
| Permanent data | Malformed schema, missing required field | DLQ, investigate and fix at source |
| Business rejection | Booking already cancelled, invalid state | Record business outcome or skip with audit |
| Authorization | Expired credentials, missing permissions | Alert and fix policy/secrets |
| Dependency overload | Exhausted DB pool, saturated downstream API | Backpressure, concurrency caps, longer retry spacing |
| Version mismatch | Consumer does not yet support new event schema | Compatibility policy, quarantine, or upgrade consumer |

### 10.1. Backoff and Retry Limits

~~~text
delay(n) = min(maxDelay, baseDelay × 2^n) + randomJitter
~~~

Backoff with jitter prevents many consumers from retrying simultaneously. Bound retry attempts, total retry duration, retryable error types, and retention. Retries must not exceed payment windows or business deadlines.

### 10.2. DLQs and Controlled Replay

A DLQ must retain the failure reason, eventId, correlationId, attempt count, timestamp, consumer version, and enough original context to investigate. Sensitive payloads must be protected.

Replay procedure:

1. Classify the failure and identify the root cause.
2. Determine whether the event already produced any side effects.
3. Fix the data or deploy a compatible consumer.
4. Verify idempotency/business keys.
5. Replay in small batches with rate limits.
6. Monitor outcomes and reconcile.
7. Audit who executed the replay, its scope, and its results.

Do not automatically redrive the entire DLQ the instant a dependency recovers; doing so can trigger a secondary burst and overload the system.

## 11. Exactly-Once in Stream Systems

Some stream processors/brokers support transactions or exactly-once mechanisms across reading input, updating state, and writing output within the same system.

For example, a framework may tie output records and input offsets together in a transaction: either both the output and the committed progress succeed, or neither is treated as committed. Idempotent producers can prevent publish retries from creating duplicate records within broker-supported bounds.

These mechanisms are useful for stream processing, but their boundaries must be clear:

- Supported only on specific brokers, clients, connectors, and versions.
- Transactions stay scoped inside the broker/stream processor; external REST API calls do not automatically join the transaction.
- Writing to external databases requires transactional connectors, sink semantics, or separate idempotency.
- Exactly-once may require proper isolation levels, transaction IDs, checkpoints, and timeout tuning.
- Reprocessing from external sources or non-idempotent side effects can still produce duplicates.
- "Once" typically means outputs are committed once within managed logic, not that code physically executes only once.

### 11.1. Distinguishing Processing from Effect

A record may be **read/processed again** after a rollback or recovery while the committed result still appears only once within the transaction boundary. Distinguish:

- **Execution count:** how many times the code ran.
- **Delivery count:** how many times the broker delivered the message.
- **Committed output count:** how many results were durably committed.
- **Business side effect count:** how many external effects actually occurred.

Exactly-once typically aims to control committed outputs or state within a specific boundary, not necessarily keeping execution count equal to one.

## 12. External Side Effects: The Most Important Boundary

Suppose a consumer calls a payment gateway API to charge 500,000 VND. The gateway processes the charge successfully, but the response is lost. Unsure of the outcome, the consumer retries. If the payment API does not support idempotency keys, the customer may be charged twice.

### 12.1. Downstream Idempotency

If an external API supports idempotency keys, pass the same key across every retry of the same business operation. Downstream can then return the prior outcome instead of executing the side effect again.

Verify:

- Is the key scoped per merchant/account or system-wide?
- How long is the key retained?
- Does sending a different payload with the same key return an error or reuse the first request?
- Are transient failure results cached under that key?
- Is there a lookup API to query status by key/transaction ID?

Never assume all external APIs share identical semantics. Read the service contract and test failures occurring after the side effect happens but before the response returns.

### 12.2. When Downstream Does Not Support Idempotency

Use intermediate states and reconciliation:

1. Persist the operation with a unique business key in PENDING state.
2. Send the request downstream with a queryable reference ID.
3. Upon receiving confirmation, mark SUCCEEDED.
4. On an ambiguous timeout, mark UNKNOWN/PENDING_RECONCILIATION instead of blindly retrying.
5. Query downstream or reconcile against statements/webhooks.
6. Retry only once there is evidence the prior operation did not occur.

Distributed systems sometimes must accept an **uncertain outcome** state until reconciliation finishes. That is safer than assuming a timeout means failure.

### 12.3. Sagas and Compensation

In multi-step processes, Sagas allow each step to record state and execute compensating actions when a flow fails. For example, if inventory reservation succeeds but payment fails, cancel the reservation. Compensation is **a new business action** that restores an equivalent business state, not a physical rollback of an already-committed transaction.

Sagas still require idempotency, retries, ordering, timeouts, and reconciliation. Do not use the phrase exactly-once to gloss over intermediate states or incomplete compensations.

## 13. Reference Architecture: Outbox + At-Least-Once + Idempotent Consumer

For critical business events, a well-controlled structure is:

~~~mermaid
flowchart TB
    CMD["Command/API"] --> TX["Transaction"]
    TX --> AGG[("Business state")]
    TX --> OB[("Outbox")]
    OB --> RELAY["Publisher relay"]
    RELAY --> BROKER[("At-least-once broker")]
    BROKER --> C1["Consumer A"]
    BROKER --> C2["Consumer B"]
    C1 --> TX1["DB transaction"]
    TX1 --> I1[("Inbox + state A")]
    C2 --> TX2["DB transaction"]
    TX2 --> I2[("Inbox + state B")]
~~~

Key properties:

- Business state and outbox event commit in the same source transaction.
- The relay may republish when unsure whether a previous publish succeeded.
- Consumers deduplicate by event ID and/or business key.
- Consumer inbox records and business state commit in the same transaction when residing in the same DB.
- External side effects use idempotency keys, intermediate states, or reconciliation.
- DLQs and replays operate under strict controls.
- Monitoring separates publish, delivery, processing, and business completion.

This is not the only implementation approach. For log-centric architectures, broker transactions and stream processors may fit better; for simpler workloads, managed queues with conditional writes may suffice. Choose tools based on required semantics and the complexity worth defending against.

## 14. Failure Matrix by Crash Point

| Failure point | Risk | Risk mitigation |
| --- | --- | --- |
| Before producer persists event | Event never exists | Retry command with idempotency/business key |
| After DB commit, before publish | Lost event without outbox | Transactional outbox/CDC |
| After broker persists, before publisher ACK | Producer republishes | Idempotent producer or consumer dedup |
| After consumer receives, before side effect | Message redelivered | Retry/visibility policy |
| After side effect, before ACK | Duplicate side effect | Inbox/unique key/downstream idempotency |
| After ACK, before side effect | Lost side effect | ACK only after durable commit |
| After DB update, before checkpoint/offset commit | Record reread | Transactional output/offset or idempotent writes |
| Mid-batch processing | Partial completion | Checkpoints and chunk idempotency |
| During DLQ replay | Side effect already happened earlier | Business keys, auditing, and controlled replay |
| When events arrive out of order | Invalid state transition | Aggregate versions, ordering keys, reconciliation |

No single mechanism protects against every row. Designs must combine transaction boundaries, durable state, retry policies, and reconciliation.

## 15. Ordering, Concurrency, and Partitions in the Cloud

Adding consumers increases throughput, but also increases concurrent execution. If two events for the same aggregate run concurrently, business order can break even when the broker delivers them in order.

Options:

- Partition by aggregate key so events for the same entity stay on the same partition.
- Allow only one consumer to process each partition at a time per broker semantics.
- Use version checks/optimistic concurrency in the DB.
- For work queues, use message group/session keys if the service supports per-group ordering.
- For order-dependent operations, ACK an event only after a valid state transition.
- For late-arriving events, quarantine/retry or reload state per domain rules.

### 15.1. Hot Keys and Trade-offs

If 40% of traffic belongs to a single tenant or aggregate key, partitioning by key can make one partition hot while others stay idle. Adding workers will not help if that partition only runs sequentially.

You can split keys if business logic permits, but if aggregate-wide ordering is required, you cannot split them arbitrarily. Sometimes lower throughput is the price paid to protect an invariant.

## 16. Observing and Operating Delivery Semantics

### 16.1. Measuring Each Stage

| Metric | Meaning |
| --- | --- |
| Publish success/failure | Can producers successfully send events to the broker? |
| Publish confirm latency | Time for the broker to acknowledge publishes |
| Consumer delivery count | Number of times a message is delivered |
| Redelivery/duplicate rate | Rate of redeliveries or detected duplicates |
| Consumer processing duration | Processing time per event |
| ACK/offset commit lag | Delay in confirming progress |
| Consumer lag / oldest message age | Backlog size and unprocessed delay |
| Retry count and DLQ depth | Persistent errors/poison messages |
| Outbox backlog age | Events not yet relayed |
| Inbox dedup hits | Number of events skipped as already processed |
| Business completion rate | Operations actually reaching business completion |
| Reconciliation mismatch | Discrepancies between source and downstream |

Do not look solely at queue depth. A queue can look empty while consumers ACK too early and drop side effects; or a broker may show zero backlog while business records remain unreconciled. Combine technical metrics with business metrics.

### 16.2. Logs and Traces

Events should carry eventId, aggregateId, aggregateVersion, correlationId, causationId, eventType, occurredAt, and schemaVersion where appropriate.

Logs should not contain full sensitive payloads. Trace context can travel via message metadata to connect producer and consumer spans; business correlation IDs remain useful when trace sampling drops spans.

Also track consumer version, schema version, deployment ID, partition, retry attempt, and DLQ reasons to debug issues after upgrades.

### 16.3. Impact-Based Alerting

- Outbox events remaining unpublished beyond a time threshold.
- Oldest message age exceeding processing SLO.
- Sudden spike in duplicate/redelivery rate.
- Consumer lag growing despite low worker CPU.
- Payment/booking flow events appearing in the DLQ.
- Rising reconciliation mismatches.
- External operations stuck in UNKNOWN state past timeout.
- A partition experiencing hot-key skew or continuous consumer rebalances.

Every alert needs an owner, dashboard, and concrete runbook. Avoid paging on every duplicate if consumers deduplicate safely and the rate stays within baseline; sudden anomalies still warrant investigation.

## 17. Quality Scenarios and Measurement Criteria

The following thresholds are **illustrative examples**. When applying them, specify valid events, measurement points, time windows, workloads, and failure types.

| ID | Scenario | Expected response | Illustrative measure |
| --- | --- | --- | --- |
| QA-EVT-01 | Producer crashes after DB commit but before publish | Event is still relayed from outbox | 100% of business state changes have matching outbox rows; 99.9% of valid events published within 60 seconds |
| QA-EVT-02 | Consumer crashes after side effect before ACK | Message is redelivered without repeating business effect | Zero duplicate invoices/bookings/payments in test suite |
| QA-EVT-03 | Events for same aggregate arrive concurrently or out of order | Valid state transitions per version/domain rules | Older version events not applied; version gaps handled per policy |
| QA-EVT-04 | External payment times out after gateway processed charge | System queries/reconciles status before retrying | Zero duplicate charges in fault-injection suite |
| QA-EVT-05 | Unprocessable poison message | Routed to DLQ while other events continue per policy | Failing message does not stall queue past threshold; alert and audit present |
| QA-EVT-06 | Replay of already-processed events | Projection rebuilds without duplicating business side effects | Unique business keys hold; post-replay counts match snapshot |

Scenarios must answer: what stimulus source, what event, what environment, which affected component, what response, and how it is measured. "Zero duplicates" must be defined precisely by invoice ID, order ID, or charge ID for consistent testing.

## 18. Fault Injection and Recovery Testing

Valuable tests deliberately inject failures right at the boundaries needing verification.

### 18.1. Cases to Test

1. Producer timeout immediately after publish to test retries and duplicate publishes.
2. Broker persists event while publisher misses the confirmation.
3. Kill consumer process right before side effect.
4. Kill consumer process right after DB commit but before ACK.
5. Force ACK/offset commit to fail.
6. Stretch processing duration past the visibility timeout.
7. Restart consumer during a rebalance.
8. Replay messages from DLQ/older offsets.
9. Send events for the same aggregate out of order.
10. Downstream side effect succeeds while its response is dropped.
11. Change event schema while older consumer versions remain running.
12. Fill queues or hit quotas to test backpressure.

### 18.2. Evidence to Capture

- Event ID, business key, correlation ID, and version.
- Timestamps for publish, broker confirm, delivery, side effect commit, and ACK/offset commit.
- Number of deliveries/attempts.
- Number of business records created/updated.
- Count of duplicates detected.
- DLQ, replay, and reconciliation outcomes.
- Queue age, consumer lag, p95/p99 latency, and test cost.

Never treat a single passing test as proof against all failure modes. Repeat tests across multiple crash points and realistic concurrency.

## 19. Cost and Impact of Delivery Semantics

Stronger semantics carry infrastructure and operational costs:

- Broker durability, replication, and retention.
- Transaction/checkpoint state and metadata.
- Inbox/outbox tables, indexes, cleanup, and storage.
- Deduplication lookups, conditional writes, and transaction contention.
- Retries, duplicate deliveries, DLQs, and replays.
- Reconciliation jobs and exception operations.
- Tracing/logging/auditing and data retention.
- Reduced throughput when broad ordering or transactions are enforced.

Do not pick exactly-once at every layer just because it sounds safer. Choose the guarantee level needed for each event class. Telemetry may accept at-most-once; booking events may need at-least-once + idempotent consumers; stream aggregations may need processor-bounded exactly-once transactions; payment APIs need idempotency keys and reconciliation.

### 19.1. Cost per Successfully Applied Event

~~~text
Cost per successfully applied event
  = (Broker + compute + database + network
     + observability + retry/DLQ + reconciliation cost)
    / Number of business events applied correctly
~~~

The denominator is not the number of messages delivered. An event may be delivered three times while only applied validly once, or ACKed without updating business state. Economic metrics must be grounded in **correct business effects**.

## 20. Case Study: Booking Confirmation and Invoice Issuance

### 20.1. Context

A booking platform uses Java/Spring Boot, PostgreSQL, and a managed message broker. When a booking is confirmed, the system emits an event to three consumers:

- Inventory projection updates reserved counts.
- Notification worker sends an email.
- Billing worker issues an invoice.

Assumed requirements:

- Never create duplicate bookings or invoices.
- Valid events are received by consumers within 30 seconds at target load.
- If a worker crashes after commit but before ACK, the event is redelivered without duplicating side effects.
- Payment/invoice discrepancies are detected and reconciled.
- Historical events can be replayed to rebuild projections without sending emails or issuing invoices a second time.

### 20.2. Design Decisions

**Producer:** The API commits the booking and an outbox row in the same transaction. A relay publishes with at-least-once semantics; publisher confirms are tracked per broker semantics. If the relay crashes after publishing, the event may be resent.

**Inventory consumer:** Inbox + business update share a database transaction; booking version detects stale events or gaps.

**Notification consumer:** Persists notification intent with a unique business key; calls the email provider with an idempotency key where supported. On ambiguous timeouts, stores UNKNOWN and reconciles before resending if needed.

**Billing consumer:** Each invoice has a unique key by booking and invoice type. Invoice state is stored before/alongside issuance; the external billing provider is called using a queryable idempotency key/reference.

**Replay:** Replayed events reuse the original eventId and business key; projections can rebuild in an isolated mode, while email/billing side effects are disabled or gated by replay policy.

~~~mermaid
flowchart TB
    API["Booking API"] --> TX["DB transaction"]
    TX --> B[("Booking")]
    TX --> O[("Outbox")]
    O --> R["Relay"]
    R --> Q[("Broker")]
    Q --> I["Inventory consumer"]
    Q --> N["Notification consumer"]
    Q --> BILL["Billing consumer"]
    I --> IDB[("Inbox + Inventory projection")]
    N --> NDB[("Notification intent")]
    N --> EMAIL["Email provider"]
    BILL --> BDB[("Invoice state + unique key")]
    BDB --> PAY["Billing provider"]
~~~

### 20.3. Failures and Handling

| Failure | Behavior |
| --- | --- |
| Relay publishes but has not marked outbox yet | Republishes; consumers deduplicate |
| Inventory worker crashes after DB commit | Event redelivered; inbox identifies already processed |
| Email times out with unknown send status | Query provider if available; use idempotency; reconcile |
| Billing event arrives twice with different event IDs | Unique business key prevents second invoice |
| Event version 5 arrives before version 4 | Consumer applies version policy, refuses backward overwrite |
| Full historical event replay | Projection rebuild decoupled from external side effects |

### 20.4. Evaluation

Do not claim a "fully exactly-once system." The system uses at-least-once delivery, a durable outbox, an inbox, unique business keys, idempotent side effects where supported, and reconciliation for uncertain outcomes. That yields **measurable business guarantees** even when code or consumers execute or receive an event more than once.

## 21. Design Checklist

- [ ] Defined semantics for publish, broker persist, delivery, ACK/offset, and business completion.
- [ ] Selected at-most-once, at-least-once, or scoped exactly-once appropriately.
- [ ] Included event ID, aggregate ID/version, correlation ID, and business keys where needed.
- [ ] Producer retries do not accidentally create duplicate business operations.
- [ ] Business state and events are persisted consistently via outbox/CDC or equivalent.
- [ ] Consumers use inbox/dedup and unique constraints/conditional writes.
- [ ] Inbox and business state share a transaction when atomicity is required.
- [ ] External side effects have idempotency keys or UNKNOWN/reconciliation states.
- [ ] ACK/offset commits happen only after protected outcomes are durable.
- [ ] Visibility timeouts/leases, heartbeats, and graceful shutdown match processing duration.
- [ ] Ordering and partition keys reflect business invariants.
- [ ] Retries classify errors, use backoff and caps, and DLQ/replay processes are audited.
- [ ] Schema evolution, consumer versions, and compatibility are tested.
- [ ] Metrics cover publish/delivery/duplicates/lag/business completion.
- [ ] Fault injection tests cover crash points before/after side effects and ACKs.
- [ ] Reconciliation exists alongside pass/fail SLO evidence.
- [ ] TCO accounts for brokers, state stores, duplicates/retries, logs/traces, and operations.

## 22. Well-Architected Review

| Pillar | Questions when reviewing event semantics |
| --- | --- |
| **Operational Excellence** | Can events be traced, duplicates investigated, replays controlled, and consumers recovered? |
| **Security** | Do events follow data minimization, producer/consumer verification, tenant isolation, and DLQ protection? |
| **Reliability** | At which points do publish, delivery, ACK, checkpoints, idempotency, and reconciliation tolerate failures? |
| **Performance Efficiency** | How do ordering, transactions, dedup lookups, and concurrency affect throughput/p95? |
| **Cost Optimization** | What is the cost of durability, retention, inbox/outbox, retries, traces, and reconciliation per successful event? |
| **Sustainability** | Are unnecessary replays/duplicates, redundant storage, and repeated processing minimized? |

**Conclusion:** At-most-once reduces repetition while accepting risk of loss; at-least-once reduces message loss by permitting redelivery; exactly-once is meaningful only when the transaction boundary and guaranteed outcome are explicitly stated. For business-critical systems, the practical foundation is typically **at-least-once + idempotency + durable state + reconciliation**, combined with broker/processor-scoped exactly-once transactions where appropriate. Measure final business outcomes and test crash boundaries rather than relying on a single service's semantics label.
