# Message Ordering Scopes and Handling Late Events

In a distributed system, a message sent earlier is not guaranteed to be processed or committed earlier. An event can arrive late due to retries, network delays, partition rebalances, consumer restarts, or historical data replays. If an application assumes events always arrive in order, business state can regress, newer data can be overwritten by older data, or critical state transitions can be missed.

When integrating Spring Boot with Azure Service Bus, Event Hubs, AWS SQS, Kinesis, or Google Cloud Pub/Sub, clearly define **the scope within which ordering is guaranteed** and **what the application does when an event arrives late or out of order**. Ordering within a queue, partition, session, or ordering key does not equal system-wide ordering. Likewise, broker delivery order does not automatically guarantee handler completion order or database commit order.

This lesson belongs to the **Reliability** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module: practicing the integration of Spring Boot with managed services from AWS, Azure, and Google Cloud via the corresponding Spring Cloud libraries; learning identity and permissions configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences across cloud providers.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish publish order, delivery order, processing order, commit order, and business sequence.
2. Identify ordering scopes: global, queue, partition, session, message group, ordering key, or aggregate.
3. Choose partition keys/session IDs/ordering keys aligned with business invariants.
4. Explain why consumer concurrency, retries, and checkpoints can alter the order of effects.
5. Distinguish event time, ingestion time, and processing time.
6. Design late-event handling: sequence/version guards, reorder buffers, watermarks, allowed lateness, and correction events.
7. Handle duplicates, missing sequences, gaps, replays, and out-of-order events without state regression.
8. Understand ordering differences across Azure Service Bus/Event Hubs, AWS SQS/Kinesis, and Google Cloud Pub/Sub.
9. Test out-of-order delivery, late arrivals, rebalances, retries, and concurrency.
10. Monitor latency, event age, sequence gaps, late-event rates, and reorder counts.

## 2. Ordering Has Multiple Layers

An event travels through multiple steps:

~~~text
Producer creates event
    → Publish request
    → Broker accepts event
    → Broker stores per queue/partition/key
    → Consumer receives event
    → Handler starts
    → Handler finishes
    → Database commit
    → External side effect
    → ACK / Complete / Checkpoint
~~~

Ordering layers to distinguish:

| Layer | Question | Example |
| --- | --- | --- |
| **Publish order** | In what order did the producer call publish? | Producer sends OrderCreated then OrderPaid |
| **Broker append order** | In what order did the broker append messages to the log/queue? | Two events with sequence 10 and 11 in the same partition |
| **Delivery order** | In what order did the consumer receive messages? | Message 10 delivered before 11 |
| **Processing start order** | Which handler started first? | Workers process 10 and 11 concurrently |
| **Processing completion order** | Which handler finished first? | Event 11 finishes before event 10 |
| **Commit order** | In what order did database transactions commit? | State version 12 written before version 11 |
| **Business order** | In what order does business logic allow state transitions? | Cannot pay before the order is created |

A broker may guarantee append/delivery order within a scope, yet the application still breaks order at the processing layer by running concurrent handlers. Conversely, a consumer may receive events in the right order while database transactions finish out of order.

**An ordering guarantee must always be paired with its scope, conditions, and failure behavior.** Never claim a service offers global ordering if documentation guarantees order only per partition, session, or key.

## 3. Ordering Scopes: Global, Partition, Session, and Key

### 3.1. Global Ordering

Global ordering means every event in the system has a single total order observed consistently by all consumers.

This is expensive as throughput and scale grow. Maintaining a single global order typically requires a single serialization point or single log. A single queue/partition simplifies ordering but limits throughput, concurrency, and scalability.

Require global ordering only when business rules truly demand it. Most systems need ordering only per order, account, device, or aggregate.

### 3.2. Partition Ordering

A partition is an ordered sub-stream inside a stream/log. Events in the same partition are appended in partition order. Multiple partitions can be processed in parallel.

Example:

~~~text
Partition 0: E1 → E2 → E3
Partition 1: E4 → E5
Partition 2: E6 → E7
~~~

Ordering holds within each partition, but there is no total order between E3 and E4, or between E5 and E6, unless the application assigns an explicit global sequence.

### 3.3. Session or Message Group

Some brokers group messages by session/message group. Consumers can process sequentially within a group while multiple groups run in parallel.

Example:

~~~text
Session ORDER-100: Created → Confirmed → Paid
Session ORDER-200: Created → Cancelled
Session ORDER-300: Created → Shipped
~~~

Ordering within ORDER-100 says nothing about ordering between ORDER-100 and ORDER-200. This usually fits well when each aggregate has its own stream of events.

### 3.4. Ordering Key / Aggregate Key

An ordering key is a value the producer uses to group events that must be processed in order—such as order ID, account ID, or device ID.

If all events for an order share the same key, they can be routed to the same ordering scope. However, a key does not enforce order by itself if the broker feature is disabled or the consumer processes concurrently without coordination.

### Choosing Scope by Invariant

| Business Invariant | Typical Appropriate Scope |
| --- | --- |
| Every balance change for an account must be sequential | Account ID |
| Every event for an order must be in order | Order ID |
| Events from a device must follow device sequence | Device ID |
| Independent events can run in parallel | Multiple partitions/keys |
| A workflow needs one unique global step | Workflow ID or coordinator |
| All system events must share one total order | Global sequencer/log, only when genuinely necessary |

**The partition key must match the unit that requires serialization.** Picking too broad a key crowds unrelated events into one partition and cuts throughput. Picking too narrow a key scatters related events and breaks ordering.

## 4. Partition Keys and the Hot Partition Problem

A partition key is typically hashed or mapped to a partition/shard. All events with the same key enter the same ordering scope per service mechanics.

Examples:

- Using tenant ID preserves order across all events of a tenant, but a large tenant creates a hot partition.
- Using order ID distributes load better while preserving per-order ordering.
- Using a random UUID per event spreads load evenly but loses ordering across events of the same order.
- Using account ID fits when balance changes on an account must be sequential.

### Hot Partitions

If one key receives far more events than others, the partition holding that key becomes a bottleneck:

~~~text
Partition A: 90% traffic from one large tenant
Partition B:  5% traffic
Partition C:  3% traffic
Partition D:  2% traffic
~~~

Adding partitions does not necessarily fix a hot key if every event for that key must still land in the same partition. Options:

- Serialize at a finer-grained aggregate if invariants allow.
- Split independent event types onto separate keys.
- Reduce payload size, batching, or per-event processing cost.
- Scale consumers and partition capacity within service limits.
- Use database sequence/version guards to protect state when parallelizing.

Do not split one aggregate across multiple partitions solely for throughput if the business requires strict ordering and has no reordering mechanism.

## 5. Delivery Order Does Not Guarantee Processing Order

Suppose the broker delivers events 41, 42, 43 in order. The consumer has concurrency 3:

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant W1 as Worker 1
    participant W2 as Worker 2
    participant W3 as Worker 3
    participant DB as Database
    B->>W1: Event 41
    B->>W2: Event 42
    B->>W3: Event 43
    W1->>DB: Slow processing
    W2->>DB: Commit event 42
    W3->>DB: Commit event 43
    W1->>DB: Commit event 41
    Note over DB: Commit order 42 → 43 → 41
~~~

If each event overwrites state with a snapshot, event 41 can overwrite newer state. If events are deltas, out-of-order execution can produce wrong calculations.

### Sources of Out-of-Order Execution

- Consumer processes multiple messages with the same key concurrently.
- Handlers have varying processing latencies.
- Retries redeliver an older event after a newer event.
- Workers crash and messages are redelivered.
- Partition ownership shifts during scaling/rebalancing.
- Batch listeners process items within a batch in parallel.
- Multiple producers emit for the same key without coordinating sequences.
- Publisher retries append an older event after a newer event.
- Checkpoints are saved out of sync with actual processing order.

### Preserving Order on the Consumer

If sequential processing per key is required:

1. Use the appropriate broker partition/session/ordering key.
2. Allow only one sequential execution path per key/partition, or use a keyed executor/scheduler that preserves order.
3. Never ACK/complete before required transactions finish.
4. Never let a retried old event run concurrently with a newer event for the same aggregate if it can corrupt state.
5. Enforce sequence/version guards at the state store as the final safety net.
6. Check whether the binder unexpectedly raises concurrency or prefetch settings.

Serialization lowers throughput within a single key, while different keys can still run concurrently.

## 6. Event Time, Ingestion Time, and Processing Time

A "late" event often simply means it arrived after another event in the consumer's observed order. To reason accurately about "late," distinguish three timestamps:

| Time | Meaning | Source |
| --- | --- | --- |
| **Event time** | When the event actually occurred in the business domain | Device, domain service, or data source |
| **Ingestion time** | When the broker/ingestion layer received the event | Broker or collector |
| **Processing time** | When the consumer processed the event | Consumer runtime |

For example, a sensor measures temperature at 10:00, loses network connectivity, and sends the reading at 10:07:

- Event time: 10:00.
- Ingestion time: 10:07.
- Processing time: 10:07 or later.

If a dashboard buckets data by event time, the record belongs in the 10:00 window even though it arrived at 10:07. If the system uses processing time only, the data appears in the 10:07 window.

### Event Timestamp Is Not a Sequence

Timestamps can collide, suffer clock skew, or originate from unsynchronized clocks. Never rely on timestamps as a strict total order when business rules demand deterministic ordering.

Prefer:

- Authoritative aggregate sequences/versions issued by the source.
- Database commit versions or log offsets within an ordered scope.
- UTC timestamps for analyzing real-world occurrence times.
- Deterministic tie-breakers when sorting events with equal timestamps.

Use UTC wall clocks for exchanging event times. Inside a single JVM process, use a monotonic clock to measure wait/timeout durations; never use monotonic timestamps as shared cross-service event times.

## 7. Why Do Events Arrive Late or Out of Order?

Common causes:

- Offline devices buffer locally and upload later.
- Flaky networks or multiple retries.
- Multi-instance producers lacking coordinated sequence assignment.
- Broker partitions/sessions keyed inconsistently with business keys.
- Consumer scaling/rebalancing causing reprocessing.
- Old events routed to a DLQ and replayed hours or days later.
- Batch uploads containing historical data.
- An upstream service emits an event after the workflow already moved to a new state.
- Device clock skew or client-generated timestamps.
- An event depends on a prior event that was delayed or lost.

Not every late event is an error. Historical backfills, offline devices, and event sourcing can all generate legitimate late events. Applications need explicit policies defining which events are accepted, updated, ignored, or routed for investigation.

## 8. Sequence Numbers and Per-Aggregate Versions

An event can carry metadata:

~~~json
{
  "eventId": "evt-7c9d",
  "aggregateType": "Order",
  "aggregateId": "ORD-10025",
  "aggregateVersion": 12,
  "eventType": "OrderPaid",
  "occurredAt": "2026-11-24T09:15:30Z",
  "schemaVersion": 2
}
~~~

Where:

- eventId: unique identifier of the event.
- aggregateId: business entity affected by the event.
- aggregateVersion: order of the event within the aggregate.
- occurredAt: business occurrence timestamp.
- schemaVersion: payload schema version.

Sequences should be assigned by the authoritative source and persisted atomically alongside the business change. If two independent producers increment sequences without atomic coordination, they can produce duplicate versions or inverted ordering.

### Do Not Use a Global Sequence If Only Per-Aggregate Order Is Needed

A global counter can become a bottleneck. If ordering is needed per order, maintain sequences per order. If needed per account, maintain sequences per account. Sequence scope must match the invariant.

### Version Guard in the Database

Example projection table with a last_event_version column:

~~~sql
UPDATE order_projection
SET status = :new_status,
    last_event_version = :incoming_version
WHERE order_id = :order_id
  AND last_event_version = :incoming_version - 1;
~~~

If one row updates, the event is the exact next version. If zero rows update, possible causes include:

- Duplicate/old event: current version is already equal to or greater than the incoming version.
- Missing event/gap: incoming version is higher than the next expected version.
- Aggregate has not been created yet.
- Competing concurrent transaction.

Read current state to classify the case; never assume every zero-row update is a duplicate.

### Distinguishing Duplicates from Gaps

Suppose current last version is 10:

| Incoming Version | Interpretation | Suggested Action |
| ---: | --- | --- |
| 10 | Likely duplicate of an already-applied event | Compare event ID/hash; ignore if identical event |
| 9 | Older stale event | Ignore or audit per policy |
| 11 | Valid next event | Apply |
| 12 | Missing version 11 | Buffer/retry/reconcile |
| 15 | Large gap | Inspect source, replay, or quarantine |

If version 10 can cover multiple events on an aggregate, you need a per-event sequence or explicit version semantics. Never assume aggregate version always increments by exactly one for every event type unless your domain model defines it that way.

## 9. Strategies for Handling Late Events

No single strategy fits all cases. Choose based on data type, reversibility, and latency requirements.

| Strategy | Approach | Best Fit |
| --- | --- | --- |
| **Reject/quarantine** | Reject or route late events to an investigation queue | Irreversible state transitions |
| **Ignore stale event** | Drop events with a version older than current state | Versioned snapshot/state projections |
| **Buffer and reorder** | Hold events awaiting missing sequences, then process in order | Sequenced events requiring strict order |
| **Apply with compensation** | Apply late events via compensating transactions | Workflows supporting state correction |
| **Recompute from history** | Replay log to rebuild projections | Analytics, event-sourced projections |
| **Late correction event** | Emit an adjustment event instead of rewriting history | Ledgers, reporting, and audits |

### Choosing by Business Semantics

- **Ledger/financial:** never delete or overwrite history; use correction/reversal events and reconciliation.
- **Order state:** version guard; an old event must not regress state from PAID back to CREATED.
- **Telemetry/analytics:** accept late events within an allowed-lateness window and update aggregates.
- **Inventory:** protect deltas with sequences or transactions; do not drop a delta just because it arrived late.
- **Notifications:** check current state before sending; do not send a stale notification if a newer state superseded it.

## 10. Buffers and Reorder Windows

When events carry sequences, a consumer can hold early-arriving events in a buffer until gaps fill.

Example: last applied version = 20, consumer receives version 22 before 21:

~~~text
Receive version 22
    → Detect gap: missing 21
    → Store 22 in pending buffer
    → Wait for 21 within reorder window
Receive version 21
    → Apply 21
    → Apply 22
~~~

### Reorder Buffers Must Be Bounded

Every buffer should define:

- Keying by aggregate/partition.
- Maximum event count and total byte limits.
- Maximum wait duration.
- Retention for waiting events.
- Duplicate handling.
- Policy when a gap is never filled.
- Durable persistence if process restarts must not lose pending events.

Never hold buffered events solely in RAM and ACK the broker. If the process crashes, RAM is lost and events vanish. Store pending events in a database or let the broker keep redelivering, depending on your design.

### When the Reorder Window Expires

When the wait time runs out without the missing event arriving:

- Request the producer/source to replay the missing version.
- Fetch the latest snapshot and rebuild the projection if the domain allows.
- Mark the aggregate as needing reconciliation.
- Quarantine the event if safe state cannot be determined.
- Never silently skip over a gap if missing events may contain mandatory side effects.

A reorder window is a latency/reliability trade-off policy, not a guarantee that the event will arrive within that window.

## 11. Watermarks and Allowed Lateness in Stream Processing

In stream processing, a **watermark** estimates event-time progress: the system assumes most events earlier than a given timestamp have arrived. Watermarks let engines close or emit results for event-time windows even when data arrives out of order.

Example: window 10:00–10:05, watermark is currently at 10:06:

- An event with event time 10:03 arriving before the watermark passes can enter the current window normally.
- An event with event time 10:03 arriving after the watermark is treated as a late event.
- If allowed lateness is 2 minutes, the engine can continue updating the window up to 10:08 per engine semantics.

### Event-Time Windows vs. Processing-Time Windows

| Window Type | Based On | Result |
| --- | --- | --- |
| **Event-time window** | Event occurrence timestamp | Reflects when business events happened, but needs watermarks/late handling |
| **Processing-time window** | When consumer processes the event | Simple, fits operational metrics; offline data lands in the wrong window |
| **Ingestion-time window** | When the system ingested the event | Reflects pipeline arrival, not necessarily business occurrence |

### Allowed Lateness

Allowed lateness is how long a system continues accepting late events for a window after the watermark passes it. Depending on the engine, late events can update results, emit retractions/updates, or route to a side output.

There is no single watermark/allowed-lateness setting shared across brokers. Azure Event Hubs, Kinesis, and Pub/Sub provide streams/transports; watermark/window semantics typically live in stream processing engines like Apache Flink, Kafka Streams, Beam/Dataflow, or custom application logic. Do not confuse broker retention or ack deadlines with watermarks.

### Choosing Allowed Lateness

- Telemetry from mobile/offline devices may need longer lateness windows.
- Payment/order events typically need state transitions and sequence guards rather than timestamp windowing alone.
- Real-time dashboards can emit provisional results and update them when late events arrive.
- Accounting close reports may require a cutoff time followed by correction entries afterward.

Too short an allowed-lateness window drops delayed data; too long a window inflates state retention, memory/storage, and result finalization delay.

## 12. Handling Late Events in Spring Boot

A Spring Boot consumer does not automatically gain a watermark engine just by using Spring Cloud Stream. The application must define event metadata, sequences, and policies.

Illustrative event model:

~~~java
import java.time.Instant;
import java.util.UUID;

public record DomainEvent<T>(
        UUID eventId,
        String aggregateType,
        String aggregateId,
        long aggregateVersion,
        Instant occurredAt,
        int schemaVersion,
        T payload) {
}
~~~

The application service should validate sequence before mutating state:

~~~java
public enum ApplyResult {
    APPLIED,
    DUPLICATE,
    STALE,
    GAP,
    UNKNOWN_AGGREGATE
}
~~~

Pseudo-implementation:

~~~java
@Transactional
public ApplyResult apply(DomainEvent<OrderPaid> event) {
    OrderProjection current =
            repository.findForUpdate(event.aggregateId());

    if (current == null) {
        return ApplyResult.UNKNOWN_AGGREGATE;
    }

    long last = current.lastEventVersion();

    if (event.aggregateVersion() <= last) {
        return inbox.hasSameEvent(
                event.eventId(), event.aggregateId())
                ? ApplyResult.DUPLICATE
                : ApplyResult.STALE;
    }

    if (event.aggregateVersion() > last + 1) {
        pendingEvents.store(event);
        return ApplyResult.GAP;
    }

    repository.apply(event);
    inbox.markApplied(event.eventId(), event.aggregateId());
    return ApplyResult.APPLIED;
}
~~~

This is directional pseudocode; design transactions carefully:

- findForUpdate requires a row lock or equivalent optimistic concurrency check.
- The inbox record and business state should commit in the same transaction.
- Pending events must be durably persisted before ACKing if the consumer cannot receive the message again.
- When the missing next version arrives, drain contiguous pending events in the same transaction or via a controlled worker.
- If an event shares a version with a different ID, decide whether the domain permits multiple events per version.
- Never ACK a gapped message unless the event is durably saved or a reliable replay mechanism exists.

## 13. Azure Service Bus: Sessions and In-Session Ordering

Azure Service Bus supports **Sessions** to group messages by SessionId and process sequentially within a session per service semantics.

Example:

- SessionId = order ID.
- Events for the same order are sent with the same session.
- A consumer acquires a session lock and processes the session's messages in order.
- Different sessions can be processed concurrently by multiple consumers.

### What Sessions Solve

- Grouping related messages into an ordered stream.
- Supporting sequential per-session processing.
- Holding session state via broker capabilities to assist workflows.
- Reducing the chance of two consumers processing the same session concurrently while the lock holds.

### What Sessions Do Not Solve

- They do not create global ordering across all sessions.
- They do not protect databases/Blobs/payment side effects from duplicates.
- Session locks can expire and messages can be redelivered.
- Multi-instance publishers must still produce events in domain order.
- Consumers can still break order if they dispatch messages from one session into a parallel executor.
- Event replay/republish must preserve identity and version.

### When Using Sessions

1. Pick SessionId based on the aggregate requiring serialization.
2. Ensure producers send all events for the same aggregate with the same SessionId.
3. Enable a session-aware receiver/processor and verify binder/native SDK settings.
4. Keep processing within a session sequential if state depends on order.
5. Use idempotency/inbox to handle redelivery.
6. Configure appropriate lock renewal, processing deadlines, and DLQ policies.

If one session receives too many messages or one aggregate is very hot, that session can become a bottleneck. Split sessions only when business invariants allow.

## 14. Azure Event Hubs: Partition Ordering

Event Hubs is a partitioned event streaming platform. Events within the same partition have an append/sequence order in the partition log. Producers can specify a partition key so related events route to the same partition per service behavior.

### Partition Key Design

- Use aggregate ID when per-aggregate ordering is needed.
- Use a stable key for the same event source.
- Never use a random key when ordering across events of the same entity is required.
- Avoid overly hot keys if single-aggregate throughput is huge.
- Do not expect ordering across partitions.

### Consumers and Checkpoints

Consumer groups read partitions independently. When partition ownership moves across processors, a consumer resumes from its saved checkpoint. If multiple events from the same partition are processed in parallel and checkpoints do not accurately reflect committed events, replays or skipped events can occur.

Rules:

- Commit business state before checkpointing.
- Checkpoint only up to the point where every preceding event in the partition has been durably processed per policy.
- If processing in parallel, track the contiguous completion offset; never checkpoint past an in-flight event.
- Use inbox/version guards to handle replays after crashes/rebalances.
- Enforce per-aggregate ordering at the application layer if multiple aggregates share a partition and need concurrent handling.

Event Hubs partition ordering does not automatically preserve business commit ordering when a consumer processes multiple events concurrently.

## 15. AWS SQS: Standard and FIFO

### SQS Standard

SQS Standard provides at-least-once delivery and best-effort ordering. Duplicate or out-of-order delivery can happen. If business rules require ordering, use sequence/version guards and idempotent processing.

Never assume a Standard queue preserves business order merely because the producer called SendMessage in sequence.

### SQS FIFO

SQS FIFO supports ordering within a **MessageGroupId**:

- Messages in the same group are processed in FIFO order per service semantics.
- Different groups can be processed in parallel.
- MessageGroupId should correspond to the aggregate needing serialization.
- Deduplication IDs/mechanisms reduce duplicate sends within the service's deduplication window.

FIFO does not establish global ordering across groups. Consumers still must handle visibility timeouts, redelivery, delete failures, and business side effects. If the application processes multiple messages from the same group in parallel, it must guard against inverting commit order.

### Choosing MessageGroupId

| MessageGroupId | Result |
| --- | --- |
| One fixed ID for the entire queue | Broad ordering, but low throughput/concurrency |
| Tenant ID | Sequential per tenant; large tenants can create hot groups |
| Order ID | Sequential per order; different orders run in parallel |
| Random ID per message | Good load distribution, but loses per-aggregate ordering |

## 16. AWS Kinesis Data Streams: Shards and Sequence Numbers

Kinesis Data Streams splits a stream into shards. Records carry sequence numbers within a shard and are read in shard order.

- Partition keys determine which shard a record routes to.
- Identical partition keys typically map to the same shard under current hash mapping.
- There is no global ordering across shards.
- Consumers checkpoint sequence numbers per shard.
- Resharding changes shard topology and must be handled by the consumer library.

### Concurrent Processing

If a consumer receives records in order but submits handlers to a parallel thread pool, commits can invert order. If a checkpoint advances past a newer record while an older record has not committed, a restart can skip the older record's effect.

Use one of these approaches:

- Process sequentially per shard when invariants require it.
- Use a keyed executor to serialize per aggregate.
- Persist sequences/versions in the database to catch gaps/stale events.
- Advance checkpoints strictly by contiguous completed sequences, never past incomplete records.
- Use inbox/idempotency to handle replays.

Kinesis per-shard ordering is the transport foundation; application processing and commits still require explicit control.

## 17. Google Cloud Pub/Sub: Ordering Keys

Pub/Sub supports ordering keys when publishers and subscriptions are configured appropriately. Messages with the same ordering key can be delivered in publish order within the scope and conditions supported by the service.

### Conditions and Scope

- Ordering must be enabled on the appropriate subscription/client.
- Producers must supply consistent ordering keys for related messages.
- Ordering guarantees are conditional on region and publishing patterns; check current service docs.
- There is no global ordering across different ordering keys.
- Redelivery/retries can affect progression of messages sharing a key.
- Consumer concurrency must preserve effect order if handlers have side effects depending on earlier events.

### When Using Ordering Keys

Use order ID for order events, account ID for account events. Do not use a single shared key for all messages if you need parallel throughput. If one key receives excessive traffic, it can become a hot key.

Exactly-once delivery and ordering keys are distinct features with different scopes. Enabling ordering does not automatically shield business state from duplicates or external side effects outside Pub/Sub.

## 18. Spring Cloud Stream: Partitioning and Consumer Concurrency

Spring Cloud Stream provides function/consumer abstractions and binders. Partitioning, ordering, retries, and settlement depend on the binder and broker.

Example function consumer:

~~~java
import java.util.function.Consumer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;

@Configuration
public class OrderEventsConfiguration {

    @Bean
    Consumer<Message<DomainEvent<OrderChanged>>> orderChanged(
            OrderEventHandler handler) {
        return message -> handler.apply(message.getPayload());
    }
}
~~~

The function defines how the handler is invoked. It does not enforce ordering by itself. Configure producer partition keys or native session/ordering keys per binder support.

### What Must Be Verified

- Does the binder support partition key expressions?
- Is partition count pre-provisioned or created by the binder?
- How are keys serialized/hashed?
- Is consumer concurrency bounded per partition/session?
- Can one key be processed by multiple threads simultaneously?
- Do retries preserve order or send messages to the back of the queue?
- On exceptions, does the binder ACK, nack, abandon, or retry?
- During rebalances, how are in-flight handlers and checkpoints handled?
- Are provider-native session/ordering keys supported?

Do not assume Kafka binder partitioning settings apply directly to Azure Service Bus, SQS, or Pub/Sub binders. Check your exact binder/version documentation and run integration tests.

### Handler Design Rules

- Handlers should delegate events to an application service with a sequence guard.
- Do not split one message into multiple asynchronous side effects and ACK before those side effects are durably persisted.
- If the binder invokes handlers concurrently, enforce aggregate-level concurrency control.
- On a gap event, persist pending state before ACKing or let the broker redeliver per policy.
- On a stale event, record metrics/audit and ignore per domain rules.

## 19. Handling Late Events Across Domain Types

### Orders and Payments

An OrderPaid version 8 arriving after OrderShipped version 9 should not automatically be ignored. Version 9 might be invalid without payment, or an upstream sequence may be broken. The consumer must read state, check invariants, and quarantine/reconcile.

Never use timestamps to automatically revert status back to an older state. Use valid state transitions and aggregate versions.

### Inventory

Events incrementing/decrementing stock are deltas. If an older event is dropped just because its timestamp is smaller, stock counts drift. Use event ID deduplication and sequences/transactions to apply every delta once.

### Telemetry

Event time is usually more important than arrival time. Use event-time windows, watermarks, and allowed lateness. Late events can update statistical aggregates or emit corrections per policy.

### Audit/Ledger

Never overwrite history to "fix order." Record new adjustment/correction events, keep the audit trail, and reconcile. Display order can follow authoritative sequences while keeping actual timestamps separately.

### Notifications

Before sending a delayed notification, check the latest state. For instance, if OrderReady arrives after OrderCancelled, do not send an "order ready" notification when the order is already canceled unless business rules mandate historical notices.

## 20. Replays, DLQs, and Historical Events

Replays can reintroduce old events after state has already moved forward. This is an intentional source of late events.

### Replays Must Preserve Identity

- Keep the original event ID if replaying the exact same event.
- Keep aggregate ID and aggregate version.
- Record separate replay metadata: replay batch ID, operator, timestamp, reason.
- Do not overwrite occurredAt with the replay timestamp.
- Use a dedicated consumer/new projection if the goal is rebuilding read models.
- Avoid replaying directly into non-idempotent side effects like payments or emails.

### Two Types of Replay

| Replay Type | Goal | Handling |
| --- | --- | --- |
| **Operational retry** | Retry events that failed to process | Preserve event identity; inbox/sequence guards remain active |
| **Projection rebuild** | Recompute read models from history | Use a dedicated projection/version or controlled reset; suppress external side effects |

DLQ replays are not always safe. Before replaying, verify whether the event already caused side effects, whether the current consumer version understands its schema, and whether the event remains valid against current business state.

### Event Schema Evolution

An older event may arrive after consumers upgraded schemas. Ensure:

- Explicit schema versions.
- Upcasters/adapters when needed.
- Preserved semantics of old events.
- No alteration of timestamp/sequence meaning during conversion.
- Incompatible payloads routed to quarantine/DLQ rather than misinterpreted.

## 21. Ordering, Idempotency, and Concurrency Must Work Together

A solid design layers multiple defenses:

| Risk | Mechanism |
| --- | --- |
| Broker delivers out of order outside guarantee scope | Partition/session/ordering key or sequence guard |
| Handlers finish out of order | Sequential executor or keyed serialization |
| Event is redelivered | Inbox/idempotency key |
| Old event overwrites newer state | Aggregate version/optimistic concurrency |
| Missing event in sequence | Gap detection, buffer, replay/reconciliation |
| Event arrives late in event time | Watermarks/allowed lateness/corrections |
| Replay duplicates side effects | Stable event ID, side-effect idempotency |
| Stale worker writes after lease expires | Fencing/version check |
| Checkpoint advances past uncommitted event | Contiguous completion tracking |

Never use locks to replace every mechanism. Locks coordinate concurrency for a window; sequences/versions and unique constraints protect durable state.

## 22. Observability: Measuring Order and Latency

Metrics to track:

| Metric | Meaning |
| --- | --- |
| event_delivery_lag_seconds | Time from broker publish/ingest to delivery |
| event_processing_lag_seconds | Time from delivery to handler start/commit |
| event_age_seconds | Time from occurredAt to processing |
| late_event_total | Events arriving past event-time threshold or watermark |
| out_of_order_event_total | Events with sequence lower or higher than expected |
| sequence_gap_total | Missing sequence detections |
| stale_event_ignored_total | Stale events skipped per policy |
| reorder_buffer_depth | Events waiting for preceding sequences |
| reorder_wait_seconds | Time events spend in the buffer |
| partition_hotspot | Load imbalance across partitions/keys |
| checkpoint_lag | Distance between committed events and checkpoint |
| replay_total | Replayed events |

Standardize timestamp definitions and metric semantics. Event age uses authoritative event time; delivery lag uses broker timestamps if available; processing duration uses an in-process monotonic clock.

### Logs/Traces

Log in a controlled way:

- Event ID, aggregate ID, and aggregate version.
- Masked or bounded partition/session/ordering key.
- OccurredAt, ingestion time, and processing time.
- Delivery count, retry attempt, and replay batch ID.
- Last applied version and incoming version when detecting gaps/stale events.
- Handler duration, commit result, and checkpoint/ACK outcome.

Never use aggregate ID, message ID, or tenant ID as high-cardinality metric labels. Place detailed fields in logs/traces with proper retention and masking.

## 23. Testing Ordering and Late Events

A test that sends messages sequentially and asserts the handler succeeded does not prove correct ordering behavior. Deliberately inject out-of-order scenarios.

### Test Matrix

| Scenario | Expected Outcome |
| --- | --- |
| Two events for same aggregate, consecutive versions | Commit in order or version guard blocks out-of-order write |
| Version 12 arrives before version 11 | Gap detected; buffered/retried/reconciled per policy |
| Version 10 arrives when state is already at 12 | Ignored/audited if stale duplicate |
| Same event ID redelivered | Inbox recognizes duplicate |
| Same version with different event ID | Apply domain rule; do not silently treat as duplicate |
| Two different aggregates | Can process concurrently |
| One hot-key aggregate | Observe throughput/lag without losing order |
| Consumer restart/rebalance | Replay causes no duplicate side effects |
| Checkpoint fails after DB commit | Event may be re-read, yet inbox protects state |
| Late telemetry within allowed lateness | Window updated per policy |
| Event arrives past watermark and allowed lateness | Side output/correction/quarantine per policy |
| DLQ replay of old event | Event identity preserved and no repeated side effects |

### Fault Injection

1. Make event version 2 finish faster than version 1.
2. Kill a worker after commit but before ACK/checkpoint.
3. Let lock/visibility/ack deadlines expire while a handler runs.
4. Send an old event after the aggregate moved to a newer state.
5. Create a gap by withholding the next version.
6. Replay an event from the DLQ hours later.
7. Increase consumer concurrency and trigger scale/rebalance.
8. Simulate clock skew between producer and consumer.
9. Send heavy traffic on a single ordering key to measure hot-key behavior.
10. Verify watermarks and allowed lateness with controlled event times.

### Testing on Managed Services

- Use dedicated test queues/topics/streams.
- Run the real binder/native SDK and partition/session/key configuration.
- Verify broker-observed ordering using sequence/offset/delivery metadata.
- Query the database to confirm commit order and aggregate versions.
- Test redelivery, checkpoints, DLQ, and replays.
- Never use production queues/streams to deliberately inject gaps, replays, or lock expirations.

## 24. Lab Exercise: Handling Out-of-Order Order Events

**Context:** The Spring Boot Order Projection receives OrderCreated, OrderConfirmed, OrderPaid, and OrderCancelled from a managed broker. Each event carries order ID, event ID, aggregate version, and occurredAt. Events may be retried, redelivered, or arrive out of order.

### Part A — Define Ordering Scope

1. Identify the aggregate requiring serialization as Order ID.
2. Choose the appropriate Service Bus SessionId, SQS FIFO MessageGroupId, Event Hubs/Kinesis partition key, or Pub/Sub ordering key.
3. Document the broker's guarantee scope and conditions.
4. Define consumer concurrency within a single key/partition/session.
5. Specify which events can be processed in parallel.

### Part B — Build a Sequence Guard

1. Store last_event_version in the order projection.
2. Apply the next event via conditional update/transaction.
3. If incoming version is less than or equal to current, check for duplicate/stale.
4. If incoming version is greater than current + 1, store as pending event or trigger replay.
5. When the gap fills, drain pending events in order.
6. Prevent older events from overwriting newer state.

### Part C — Late Event Policy

1. If OrderPaid arrives after OrderCancelled, check domain invariants and route to reconciliation on conflict.
2. For telemetry events, use event time and allowed lateness.
3. For audit/ledger, emit correction events instead of rewriting history.
4. For notifications, check current state before sending.

### Part D — Testing and Operations

1. Send versions 1, 3, 2 and verify final state.
2. Send version 2 twice and verify idempotency.
3. Kill the consumer after commit before ACK/checkpoint.
4. Replay an old version from the DLQ.
5. Increase concurrency and verify commit order.
6. Monitor late-event rate, sequence gaps, reorder buffer depth, and processing lag.

### Deliverables

- Table of ordering guarantees by broker and key/partition/session scope.
- Event schema with event ID, aggregate ID, version, and occurredAt.
- Diagram of delivery/processing/commit/checkpoint.
- Sequence guard and gap/late-event policies.
- Test results for out-of-order, duplicates, replays, and consumer restarts.
- Dashboard metrics for event age, late events, sequence gaps, and partition hotspots.

### Self-Check Questions

1. Why does delivery order not guarantee commit order?
2. How does global ordering differ from partition ordering?
3. When should order ID be chosen as the partition/session/ordering key?
4. Why can a hot key throttle throughput?
5. How does event time differ from ingestion time and processing time?
6. Why are timestamps not always a reliable sequence?
7. How does a version guard distinguish duplicates, stale events, and gaps?
8. When version 12 arrives before version 11, why should you not always discard version 12?
9. Do watermarks and allowed lateness belong to the broker or the stream processing engine?
10. How do Azure Service Bus Sessions differ from Event Hubs partition ordering?
11. Within what scope does SQS FIFO MessageGroupId guarantee ordering?
12. Why does a Pub/Sub ordering key not create global ordering?
13. What consequences can checkpointing past an uncommitted event cause?
14. Which identities/metadata must replaying an old event preserve?
15. How do you handle late payment/order events without regressing state?

## 25. Takeaways

- Ordering must always be stated with its scope: global, partition, session, message group, ordering key, or aggregate.
- Publish order, broker append/delivery order, processing order, and database commit order are distinct layers.
- Consumer concurrency, retries, redelivery, and checkpoints can invert effect order even when the broker delivers in order.
- Choose keys matching the aggregate needing serialization; overly broad keys cause hot partitions, overly narrow keys lose required ordering.
- Event time, ingestion time, and processing time serve different purposes. Timestamps do not replace authoritative sequences/versions.
- Use aggregate versions, conditional updates, and gap detection to prevent old events from overwriting newer state.
- Late events can be buffered/reordered, dropped by version, corrected via new events, or reconciled; choose based on business invariants.
- Watermarks/allowed lateness are stream-processing concepts; do not equate them with broker retention, locks, or ack deadlines.
- Service Bus Sessions, Event Hubs partitions, SQS FIFO message groups, Kinesis shards, and Pub/Sub ordering keys all have distinct guarantee scopes.
- Test out-of-order events, duplicates, gaps, late arrivals, replays, rebalances, and commits/checkpoints; measure event age, processing lag, and sequence gaps.

## References

- [Azure Service Bus sessions](https://learn.microsoft.com/azure/service-bus-messaging/message-sessions)
- [Azure Event Hubs features and partitions](https://learn.microsoft.com/azure/event-hubs/event-hubs-features)
- [AWS SQS FIFO queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues.html)
- [Amazon Kinesis Data Streams partition keys](https://docs.aws.amazon.com/streams/latest/dev/key-concepts.html)
- [Google Cloud Pub/Sub message ordering](https://cloud.google.com/pubsub/docs/ordering)
- [Google Cloud Pub/Sub flow control](https://cloud.google.com/pubsub/docs/flow-control)
- [Spring Cloud Stream reference](https://docs.spring.io/spring-cloud-stream/reference/)
- [Apache Flink event time and watermarks](https://nightlies.apache.org/flink/flink-docs-stable/docs/concepts/time/)
- [Apache Beam programming guide: watermarks and late data](https://beam.apache.org/documentation/programming-guide/#watermarks-and-late-data)
- [Martin Fowler — Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html)
